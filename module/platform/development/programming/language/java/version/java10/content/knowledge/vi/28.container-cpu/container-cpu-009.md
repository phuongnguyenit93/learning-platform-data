# Java 10 – CPU trong container: Quan sát giới hạn container bằng nhật ký JVM hiện hành

> **Phạm vi bài học:** Java 10 → **CPU trong container** → **Quan sát giới hạn container bằng nhật ký JVM hiện hành**. Từ Java 10, HotSpot có cơ chế nhận diện giới hạn tài nguyên Linux container (`UseContainerSupport`, liên quan JDK-8146115). Bài tập trung vào các công cụ chẩn đoán **vẫn áp dụng trên JDK 17+ và các bản JDK hiện đại**: `-Xlog:os+container=trace`, `-XshowSettings:system`, `-Xlog:gc+init=info`, `-XX:+PrintFlagsFinal`, `jcmd ... VM.info`, API `Runtime.availableProcessors()` và các tệp cgroup v1/v2. Không dùng các tùy chọn container/GC cũ đã bị thay thế. **Điểm quan trọng:** thông tin JVM báo là **điều JVM nhận diện hoặc được cấu hình để dùng**; muốn khẳng định container có CPU quota nào thì còn phải kiểm **cgroup/Kubernetes thực tế**.

## 1. Mục tiêu và kết luận chính

Sau bài học, bạn có thể:

1. Hiểu vì sao CPU host có thể nhiều hơn CPU container được phép dùng.
2. Mô tả đường đi **Kubernetes/Docker → Linux cgroups → HotSpot container detection → JVM ergonomics → GC/concurrency**.
3. Đọc đúng **CPU request**, **CPU limit/quota**, **CPU weight/shares**, **cpuset/affinity**, **CPU usage** và **CPU throttling**.
4. Dùng `java -Xlog:os+container=trace -version` trên **Linux/HotSpot có hỗ trợ** để xem việc phát hiện cgroup và giới hạn.
5. Dùng `java -XshowSettings:system -version` để xem bảng thông số hệ thống/cgroup do JVM xuất.
6. Dùng `-Xlog:gc+init=info` để xác minh `CPUs: ... total, ... available` và số G1 workers.
7. Dùng `-XX:+PrintFlagsFinal` hoặc `jcmd` để tìm `UseContainerSupport`, `ActiveProcessorCount` và các cờ liên quan.
8. Nhận diện cgroup **v2** với `cpu.max`, `cpu.stat`, `cpu.weight`, `cpuset.cpus.effective`; hiểu sự khác biệt cgroup **v1**.
9. Biết cách tính quota tương đương CPU từ **microseconds quota / microseconds period**, không nhầm với số core vật lý chuyên dụng.
10. Hiểu `Runtime.availableProcessors()`, `OperatingSystemMXBean` và `-XX:ActiveProcessorCount=N` phản ánh gì và không phản ánh gì.
11. Phân biệt `UseContainerSupport=true` với việc **đã phát hiện một container hợp lệ**; flag có thể không tồn tại trên VM/platform khác.
12. Chẩn đoán trường hợp `No metrics available for this platform`, không có tag `os+container` hoặc quota hiển thị `-1`/`max`.
13. Liên hệ số CPU JVM nhận diện với mặc định số GC workers, ForkJoinPool và thread pools, nhưng không coi `ActiveProcessorCount` là cgroup limit.
14. Chạy ví dụ Java 17+ có kết quả xác định bằng những flags tường minh, tách **kiểm thử tính năng JVM** khỏi **thử nghiệm trên Linux container thật**.
15. Lập checklist log/metrics cho incident CPU throttling hoặc hiệu năng kém trong Docker/Kubernetes.

**Kết luận:** Để biết **CPU container đang bị giới hạn thế nào**, cần xem **cấu hình orchestration**, **cgroup đang có hiệu lực**, **JVM nhìn thấy gì** và **throttling/usage trong thực tế**. Một dòng `availableProcessors()=2` không chứng minh có đúng hai physical cores riêng; một dòng `UseContainerSupport=true` không chứng minh VM đã đọc được cgroup limit.

## 2. Java 10 bổ sung điều gì?

Trước khi JVM hiểu container tốt hơn, một tiến trình Java chạy trong Docker có thể nhận diện CPU/memory của **host** thay vì những giới hạn dành cho container. Khi đó các mặc định như số GC workers, cỡ heap hoặc concurrency pools có thể quá lớn so với ngân sách tài nguyên thực tế.

**JDK-8146115 – Java Improvements for Docker Containers** đưa khả năng container-aware resource detection vào **JDK 10**. Trên **HotSpot Linux được hỗ trợ**, tùy chọn `-XX:+UseContainerSupport` được bật mặc định và cho phép JVM dùng thông tin cgroup để ước tính số processors/bộ nhớ khả dụng. JVM cũng có `-XX:ActiveProcessorCount=N` để ghi đè con số CPU dùng cho heuristics.

Lộ trình hỗ trợ về sau tiếp tục thay đổi:

- **Java 10:** mốc quan trọng của nhận diện Linux Docker/cgroups ở HotSpot. Đây là **lịch sử nguồn gốc**, không phải khuyến nghị dùng JDK 10 để triển khai mới.
- **JDK 15:** có hỗ trợ cgroups **v2** trong OpenJDK; một số dòng JDK 8/11 nhận backport ở các bản update phù hợp. **Đúng update version** rất quan trọng.
- **JDK 17+ và các JDK hiện đại:** cơ chế chẩn đoán `-Xlog:os+container=trace` và `-XshowSettings:system` vẫn hữu ích trong môi trường Linux được hỗ trợ; mặc định và cách dùng CPU shares/weights đã có những thay đổi giữa các release.
- **JDK và OS khác nhau:** OpenJDK/HotSpot trên Windows không nhất thiết có tag `os+container` hoặc VM option `UseContainerSupport` như trên Linux. Không sao chép cờ Linux-only vào tất cả môi trường.

**Không dùng `-XX:+UseCGroupMemoryLimitForHeap` hoặc các workaround cũ làm hướng dẫn hiện hành.** Cần kiểm tài liệu của đúng Java distribution và release đang triển khai, đặc biệt với cgroups v2.

Nguồn chính thức: [Oracle Java 10 launcher](https://docs.oracle.com/javase/10/tools/java.htm), [Oracle Java 25 launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html), [Kubernetes – About cgroup v2](https://kubernetes.io/docs/concepts/architecture/cgroups/).

## 3. “CPU trong container” gồm những đại lượng khác nhau

| Thuật ngữ | Ý nghĩa | Có giới hạn CPU cứng không? |
| --- | --- | --- |
| **Host logical CPUs** | Số logical processors host sở hữu/OS nhìn thấy | Không thể suy quyền dùng của pod |
| **CPU affinity/cpuset** | Tập logical CPUs task được phép được scheduler chạy trên đó | Giới hạn **nơi** chạy, không tự nói CPU-time quota |
| **CPU quota/period** | Tổng CPU time cgroup được sử dụng trong mỗi chu kỳ | Có thể là **hard bandwidth limit** |
| **CPU request** (Kubernetes) | Lượng tài nguyên scheduler xét khi đặt pod; ảnh hưởng chia sẻ theo cấu hình | **Không tự là hard CPU cap** |
| **CPU limit** (Kubernetes) | Giới hạn CPU time container; thường thực thi bằng CFS bandwidth/quota | Có, tùy runtime/kernel policy |
| **CPU shares/weight** | Trọng số ưu tiên chia CPU khi có contention | Không phải số core cố định |
| **CPU usage** | CPU time đã dùng trong khoảng đo | Không phải quota đã cấp |
| **Throttling** | Thời gian/số lần workload bị giới hạn bởi bandwidth quota | Tín hiệu runtime bị hạn chế |
| **JVM active processors** | Số processors HotSpot dùng trong các heuristics; có thể override | Không phải bảo đảm sở hữu CPUs |
| **GC parallel workers** | Threads GC dừng ứng dụng có thể dùng | Không phải số CPU thực sự được scheduler cấp |

Một ứng dụng có thể **thấy 8 CPUs trong cpuset** nhưng có **CPU quota tương đương 2 CPU**; tức là được scheduler chạy trên một trong 8 logical CPUs cho phép nhưng tổng CPU time bị giới hạn theo quota. Không có mâu thuẫn: **cpuset và quota kiểm soát hai thứ khác nhau**.

### 3.1. Con số “CPU 2” cần gắn nguồn

Thấy chữ số `2` ở những nơi sau không đồng nghĩa:

- `resources.requests.cpu: "2"`: scheduling request.
- `resources.limits.cpu: "2"`: hard quota nếu được runtime thực thi.
- `cpu.max: 200000 100000`: bandwidth quota tương đương 2 CPU ở cgroup v2.
- `cpuset.cpus.effective: 0-1`: được chạy trên hai logical CPU IDs.
- `Runtime.availableProcessors(): 2`: JVM báo hai processors cho chương trình.
- `-XX:ActiveProcessorCount=2`: người vận hành yêu cầu JVM **giả định hai CPU** cho ergonomics.
- `ParallelGCThreads=2`: configured GC workers.

Có thể các giá trị này cùng bằng 2, nhưng một thí nghiệm tin cậy phải kiểm **từng nguồn**, không coi chúng là các biểu diễn tương đương.

## 4. Đường đi của thông tin giới hạn CPU

~~~text
Ứng dụng triển khai: Pod / Container
  ├─ CPU request: lượng scheduler dùng
  ├─ CPU limit: quota nếu cấu hình
  └─ cpuset / affinity / weights / node contention
                 │
                 ▼
Linux kernel / cgroups v1 hoặc v2
  ├─ Quota + period
  ├─ Cpuset được phép
  ├─ Shares / weight
  └─ Usage / throttling counters
                 │
                 ▼
HotSpot Linux container support
  ├─ Phát hiện cgroup path, provider, giới hạn
  ├─ Tính active processor count (theo VM release)
  └─ Chọn resource ergonomics
                 │
                 ▼
JVM/application
  ├─ Runtime.availableProcessors()
  ├─ OperatingSystemMXBean
  ├─ Default GC workers, ForkJoinPool, ...
  └─ Chẩn đoán bằng -Xlog / -XshowSettings / jcmd
~~~

**Hai mũi tên dễ hiểu sai:**

1. `UseContainerSupport` là **cơ chế phát hiện/tham khảo cgroup**, không phải nơi **đặt** limit. Kernel/container runtime mới là nơi thực thi quota.
2. `ActiveProcessorCount` ghi đè số CPU JVM dùng để tính một số mặc định, **không ghi thay file `cpu.max`** và không biến CPU request thành hard limit.

## 5. Lệnh quan sát đầu tiên: `-XshowSettings:system`

Trong một **container Linux chạy HotSpot/OpenJDK có hỗ trợ**:

~~~bash
java -XshowSettings:system -version
~~~

Đây là cách gọn để xem metrics do JVM phát hiện mà chưa cần sửa source code. Với cgroups v2, bạn có thể thấy một cấu trúc **minh họa** như sau:

~~~text
Operating System Metrics:
    Provider: cgroupv2
    Effective CPU Count: 2
    CPU Period: 100000us
    CPU Quota: 200000us
    List of Effective Processors, 4 total:
    0 1 2 3
~~~

**Quan trọng:** Đoạn trên mô phỏng **định dạng** được tài liệu ví dụ Red Hat/OpenJDK công bố, **không phải output đã đo từ Linux container của bài này**. Tên fields, giá trị và cách trình bày tùy JDK/OS/cgroup. Đừng ép unit test phải khớp nguyên văn toàn bộ đoạn.

Cách đọc:

- **Provider:** JVM xác định loại source metrics, ví dụ `cgroupv1` hoặc `cgroupv2`.
- **Effective CPU Count:** số processors JVM dự định dùng cho các ergonomics có liên quan.
- **CPU Quota / CPU Period:** các thông số bandwidth do cgroup cung cấp, nếu có.
- **List of Effective Processors:** cpuset/affinity CPUs có hiệu lực nếu có số liệu; con số này có thể **khác** Effective CPU Count.
- **Memory fields:** có thể xuất hiện nhưng không nên suy CPU quota từ memory limit.

### 5.1. Không thấy thông số không đồng nghĩa không có container

Trên Windows hoặc VM không hỗ trợ Linux container metrics, lệnh trên có thể in:

~~~text
Operating System Metrics:
    No metrics available for this platform
~~~

Trường hợp này đã được quan sát trên máy kiểm thử Windows JDK của bài. Nó **không** chứng minh host không chạy một container kiểu Windows, hoặc Java bị hỏng; chỉ có nghĩa **bộ metrics mà launcher yêu cầu không được cung cấp ở nền tảng/JDK đó**.

Trong Linux container, nếu xuất hiện thông báo tương tự dù cgroup đang áp giới hạn, cần kiểm **JDK version/update, cgroups v2 support, mount permissions/path, VM distribution và flags**. Đừng chỉ tăng heap hoặc đặt `ActiveProcessorCount` khi chưa biết nguyên nhân.

### 5.2. Kiểm tra startup trong image thực

Ví dụ Docker, thay `IMAGE` bằng image hợp lệ trong môi trường của bạn:

~~~bash
docker run --rm IMAGE java -XshowSettings:system -version
~~~

**Giả định:** image có Java launcher và entrypoint cho phép truyền lệnh như trên. Một image có `ENTRYPOINT` riêng có thể đòi `--entrypoint java` hoặc cách chạy khác. Cần đối chiếu lệnh thực sự được chạy trong image. **Không đổi image sang bản khác** chỉ vì lệnh kiểm tra trên host cho ra kết quả đẹp.

Với pod đang chạy, có thể sử dụng `kubectl exec` theo chính sách truy cập để chạy Java diagnostic **bên trong đúng container**. Bất kỳ output nào chạy **trên host** có thể khác với output chạy trong cgroup của pod.

## 6. Lệnh chi tiết: `-Xlog:os+container=trace`

Tài liệu Java launcher JDK 17/25 giới thiệu:

~~~bash
java -Xlog:os+container=trace -version
~~~

**Chỉ áp dụng khi HotSpot runtime cung cấp tag `os+container`**, chủ yếu trong hỗ trợ Linux. `trace` là mức chi tiết cao, hữu ích khi JVM cần xác định cgroup hierarchy, quota, period, cpuset, shares và paths. Dòng log cụ thể tùy version, không phải cấu trúc máy-máy ổn định.

### 6.1. Dùng cùng ứng dụng

~~~bash
java -Xlog:os+container=trace -jar app.jar
~~~

Các thông tin container thường xuất hiện trong giai đoạn **JVM khởi tạo**, trước khi ứng dụng in log nghiệp vụ. Vì vậy chạy riêng `java -version` cùng cờ là cách tốt để kiểm cấp VM, chưa cần khởi động service hoặc kết nối database.

### 6.2. Ghi log ra file và rotation khi cần

Ví dụ cho image Linux có filesystem cho phép ghi:

~~~bash
java \
  -Xlog:os+container=trace:file=container.log:uptime,level,tags:filecount=3,filesize=5M \
  -jar app.jar
~~~

Đây là cú pháp POSIX shell; dấu `\` ở cuối dòng **không** phải dấu nối lệnh của Windows PowerShell.

- `os+container`: tập tags, **không phải hai tags độc lập nối bởi dấu phẩy**.
- `trace`: nhiều thông tin hơn `debug` hoặc `info`.
- `file=container.log`: file log.
- `uptime,level,tags`: decorators.
- `filecount`/`filesize`: rotation/giới hạn file; các giá trị được đặt theo nhu cầu.
- Thử bằng `java -Xlog:help` để xem tags/levels mà **bản JDK đang chạy** hỗ trợ.
- Khi thu log trong pod, cân nhắc disk quota, log collection, retention và thông tin môi trường nhạy cảm.

### 6.3. Trường hợp tag không tồn tại

Trên môi trường kiểm thử **Windows** của bài này, dùng `-Xlog:os+container=trace` đã xuất cảnh báo dạng:

~~~text
No tag set matches selection: os+container
~~~

Thông báo cảnh báo **không phải bằng chứng container quota bằng 0**. Nó là dấu hiệu JVM build/OS đó **không đăng ký tag**. Hãy kiểm `java -Xlog:help` và dùng `-Xlog:gc+init=info` cùng các API portable thay vì gán ý nghĩa Linux cho Windows.

**Không thiết kế một health-check production bắt buộc mọi JDK trên mọi OS phải in tag này.** Nếu mục tiêu là Linux container, chỉ bật nó trong Linux image/VM đã được xác minh hỗ trợ.

### 6.4. Đọc đúng những nhóm thông tin trong trace

Tùy HotSpot version, có thể gặp thông tin về:

- Cgroup subsystem được phát hiện: v1, v2 hoặc không khả dụng.
- CPU quota và CPU period.
- CPU set/affinity/processor list.
- CPU shares hoặc weight.
- Memory limit/swap limit liên quan resource detection.
- Lỗi mở/đọc cgroup files, permission hoặc mount/hierarchy bất thường.
- Calculated active processors/đường fallback.

**Không mặc định mỗi trường luôn được in, tên dòng chính xác không đổi hoặc mỗi lần start JVM đều quét toàn bộ cgroup tree.** Log có thể thay khi VM cải tiến container support. Kết luận quan trọng phải được **đối chiếu với số liệu kernel và runtime**.

## 7. Lệnh kiểm tra GC ergonomics: `-Xlog:gc+init=info`

Ngay cả khi không có `os+container` (ví dụ trên Windows), bạn vẫn có thể hỏi JVM đang **dùng bao nhiêu processors cho GC ergonomics**:

~~~bash
java -XX:+UseG1GC -Xlog:gc+init=info -version
~~~

Khi ứng dụng chạy, log HotSpot có thể ghi những dòng như:

~~~text
[info][gc,init] CPUs: 28 total, 2 available
[info][gc,init] Parallel Workers: 2
[info][gc,init] Concurrent Workers: 1
~~~

Đây là **trích log đã được kiểm thử trong môi trường Windows hiện có với** `-XX:ActiveProcessorCount=2`, `-XX:ParallelGCThreads=2`, `-XX:ConcGCThreads=1`. Chữ số `28 total` là của máy thử, **không** phải thông số của container Linux, cũng không phải số phổ quát.

Cách hiểu:

- **Total CPUs:** CPUs tổng thể mà VM log theo nền tảng.
- **Available CPUs:** số processors JVM đang dùng theo detection/override.
- **Parallel Workers:** cỡ nhóm GC parallel workers được init cho G1.
- **Concurrent Workers:** cỡ nhóm GC concurrent workers.

### 7.1. Vì sao có thể khác tổng host?

Cấu hình thử:

~~~bash
java -XX:+UseG1GC \
     -XX:ActiveProcessorCount=2 \
     -XX:ParallelGCThreads=2 \
     -XX:ConcGCThreads=1 \
     -Xlog:gc+init=info -version
~~~

Với `ActiveProcessorCount=2`, JVM báo **2 available** ngay cả khi host có nhiều hơn, vì bạn đã **ghi đè giá trị JVM sử dụng**. Điều này **không chứng minh** cgroup limit đã đặt 2 CPUs.

Nếu muốn **kiểm xem container support tự phát hiện thế nào**, hãy **không đặt `ActiveProcessorCount` trong lượt đo đầu tiên**, kiểm các flags startup thực và đối chiếu `-XshowSettings:system`/cgroup. Sau đó mới thử overrides với mục tiêu tuning riêng.

### 7.2. Không dùng log GC để suy “CPU đã được cấp riêng”

GC init log nói JVM chọn số worker như thế nào; nó không chứng minh OS sẽ cấp N cores đồng thời, rằng pod không bị CPU throttling, hoặc rằng 100% thời gian CPU thuộc riêng JVM. Khi có request/limit và contention, cần metrics kernel/cgroup.

## 8. Cgroup v2: đọc nguồn dữ liệu của Linux kernel

Cgroups v2 dùng một hierarchy thống nhất. Khi đang ở **đúng container/cgroup namespace** được mount theo cách phổ biến, các tệp có thể nằm tại:

~~~text
/sys/fs/cgroup/cgroup.controllers
/sys/fs/cgroup/cpu.max
/sys/fs/cgroup/cpu.stat
/sys/fs/cgroup/cpu.weight
/sys/fs/cgroup/cpuset.cpus
/sys/fs/cgroup/cpuset.cpus.effective
~~~

**Đừng mặc định chúng nằm chính xác ở root `/sys/fs/cgroup` trên mọi host/pod.** Mount namespace, nested cgroups và delegation có thể khiến đường dẫn tương ứng với tiến trình khác đi. Khi nghi ngờ, kiểm `/proc/self/cgroup` và `/proc/self/mountinfo` hoặc công cụ hệ thống để xác định cgroup thật.

### 8.1. `cpu.max`: quota và period

Ví dụ:

~~~bash
cat /sys/fs/cgroup/cpu.max
~~~

Kết quả giả định:

~~~text
200000 100000
~~~

Diễn giải:

- `quota = 200000 μs` CPU time được cấp trong mỗi `period = 100000 μs` của cgroup.
- CPU bandwidth tương đương **2 CPU trung bình** trên một chu kỳ khi có đủ công việc.
- Điều này **không** chứng minh cgroup có hai dedicated physical cores.
- Cgroup có thể chạy trên nhiều logical CPUs cùng một lúc rồi hết quota trước khi hết period và bị throttled.

Công thức cho quota có giá trị hữu hạn:

~~~text
equivalent_cpu_budget = quota_microseconds / period_microseconds

200000 / 100000 = 2.0 CPU
150000 / 100000 = 1.5 CPU
50000  / 100000 = 0.5 CPU
~~~

Nếu output là:

~~~text
max 100000
~~~

thì **không có quota bandwidth hard limit tại cấp đó**. Không được hiểu “container đã được cấp vô hạn CPU”: còn giới hạn cấp cha (ancestor cgroups), cpuset, affinity, CPU contention và policy runtime.

### 8.2. `cpu.stat`: kiểm tra có bị throttling không

~~~bash
cat /sys/fs/cgroup/cpu.stat
~~~

Một file có thể chứa các keys như:

~~~text
usage_usec 12345678
user_usec 11223344
system_usec 1122334
nr_periods 900
nr_throttled 45
throttled_usec 1100000
~~~

**Chỉ là ví dụ cấu trúc, không phải output từ container thật trong bài.**

- `usage_usec`: tổng CPU time cgroup đã dùng, đo bằng microseconds.
- `user_usec` / `system_usec`: tách phần CPU time user/kernel khi được cung cấp.
- `nr_periods`: số accounting periods (khi controller báo).
- `nr_throttled`: số lần/chu kỳ gặp throttling do bandwidth controller theo định nghĩa kernel.
- `throttled_usec`: thời gian throttling theo cgroup accounting, không phải “latency tăng chính xác bằng từng đó” của mọi request.

**Quan trọng:** Với cgroup v2 hiện đại, một số throttling counters có ngữ nghĩa **non-hierarchical** đối với quota của chính cgroup. Việc bị giới hạn từ ancestor có thể cần số liệu cấp cha hoặc `cpu.stat.local` khi kernel hỗ trợ. Không kết luận “không throttling” chỉ vì một counter cgroup con bằng 0 nếu hệ thống còn các giới hạn cấp trên.

Cần đo **chênh lệch theo thời gian**, không chỉ một snapshot:

~~~text
Δnr_throttled = value_after - value_before
Δthrottled_usec = value_after - value_before
elapsed_seconds = end_time - start_time
~~~

Kết quả phải gắn với **khoảng đo, workload, CPU limit và cgroup đúng của tiến trình**. Một số counter không tồn tại nếu controller bị disable hoặc kernel khác, cần xử lý thiếu dữ liệu thay vì tự mặc định 0.

### 8.3. `cpuset.cpus.effective`: CPU IDs thực được cho phép

~~~bash
cat /sys/fs/cgroup/cpuset.cpus.effective
~~~

Ví dụ:

~~~text
0-3
~~~

Nghĩa là tập **4 logical CPU IDs** có hiệu lực theo cpuset của cgroup. Nó **không** đồng nghĩa quota=4. Một cgroup có thể có `cpuset 0-3` nhưng `cpu.max 200000 100000`, tức được chạy trên bốn CPU IDs nhưng tổng CPU time tương đương khoảng 2 CPUs.

`cpuset.cpus` có thể rỗng do kế thừa parent; hãy ưu tiên `cpuset.cpus.effective` khi muốn biết tập CPUs có hiệu lực.

### 8.4. `cpu.weight`: relative share, không phải quota

~~~bash
cat /sys/fs/cgroup/cpu.weight
~~~

`cpu.weight` ảnh hưởng **tỷ trọng chia CPU giữa các cgroups đang cạnh tranh**, **không** quy định container “chỉ được 2 CPUs” bằng một số tương đương trực tiếp. Với CPU rảnh, workload có thể tận dụng nhiều hơn tỷ trọng danh nghĩa (khi không có hard cap khác).

Không lấy `cpu.weight=100` rồi đặt `-XX:ActiveProcessorCount=100`. Một bên là relative scheduling weight; một bên là số CPU nguyên JVM dùng cho ergonomics.

### 8.5. Nguồn chính thống

Tham khảo [Linux Kernel – Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html) cho chính xác định dạng `cpu.max`, `cpu.stat`, `cpu.weight` và `cpuset.cpus.effective`. Không học cgroup file semantics từ một log JVM duy nhất.

## 9. Cgroup v1: các đường dẫn và field khác

Cgroup v1 thường dùng nhiều controller hierarchies riêng. Những tệp CPU quan trọng:

~~~text
cpu.cfs_quota_us
cpu.cfs_period_us
cpu.shares
cpu.stat
cpuset.cpus
~~~

Ví dụ vị trí được mount thường gặp (chỉ minh họa):

~~~bash
cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us
cat /sys/fs/cgroup/cpu/cpu.cfs_period_us
cat /sys/fs/cgroup/cpu/cpu.stat
cat /sys/fs/cgroup/cpuset/cpuset.cpus
~~~

Những path trên **không bảo đảm tồn tại** trong mọi Linux distribution/container; có thể là `/sys/fs/cgroup/cpu,cpuacct` hoặc nested paths. Luôn căn cứ mountinfo/cgroup membership.

### 9.1. Diễn giải v1

- `cpu.cfs_quota_us`: CPU-time quota theo microseconds, `-1` thường chỉ không có quota ở controller đó.
- `cpu.cfs_period_us`: period; ví dụ `100000` microseconds.
- `cpu.shares`: relative weight, không phải absolute CPU count.
- `cpu.stat`: có thể có `nr_periods`, `nr_throttled`, `throttled_time`; **đơn vị v1 `throttled_time` thường là nanoseconds**, khác cgroup v2 `throttled_usec`.
- `cpuset.cpus`: tập CPU IDs cho phép trong cpuset hierarchy.

Đừng copy parser v1 để đọc v2 và ngược lại. Key names và units **khác nhau**; đặc biệt nhầm **ns vs µs** có thể khiến báo cáo throttling sai 1000 lần.

### 9.2. Phiên bản JDK có đọc cgroup v2 không?

Không phải mọi Java 10–14 hoặc Java 11 update cũ đều có hỗ trợ cgroups v2 tương đương các bản hiện nay. Theo tài liệu Kubernetes, hãy ưu tiên JDK version/update có hỗ trợ đầy đủ cgroups v2, ví dụ **OpenJDK 15+**, hoặc bản backport tương ứng của 8/11. Với môi trường production mới, nên dùng **JDK được nhà cung cấp hỗ trợ hiện hành** thay vì giữ runtime cổ chỉ để thử container flags.

Khi `-XshowSettings:system` báo `No metrics available` trên Linux cgroups v2, đây là một giả thuyết quan trọng để kiểm, không nhất thiết là ứng dụng không nằm trong container.

## 10. Kubernetes requests và limits: khác nhau khi đọc log

Một ví dụ Pod manifest **thu gọn**:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-cpu-demo
spec:
  containers:
    - name: app
      image: your-registry/your-java-image:tag
      resources:
        requests:
          cpu: "500m"
        limits:
          cpu: "1500m"
~~~

Đây là **manifest cấu trúc minh họa**, không phải tên image tồn tại sẵn để copy/deploy. Khi triển khai thật, chọn image JDK được hỗ trợ, xác thực registry, security context và application command.

Giải thích:

- `500m` = **0,5 CPU** được request phục vụ scheduler/resource accounting.
- `1500m` = **1,5 CPU** maximum CPU bandwidth, thường được runtime diễn dịch ra cgroup quota.
- Hard CPU cap được kiểm bằng **cgroup trên container** chứ không suy từ request.
- JVM có thể báo một **số nguyên** qua `availableProcessors()`; với quota phân số, cách quy đổi/rounding tùy JDK version, cgroup/cpuset và flags.
- CPU request có thể được phản ánh thành shares/weight theo runtime, nhưng **không tự là hard cap**.

### 10.1. Xem Pod spec đã được admission xử lý

Ví dụ với quyền truy cập phù hợp:

~~~bash
kubectl get pod java-cpu-demo -n YOUR_NAMESPACE -o yaml
kubectl describe pod java-cpu-demo -n YOUR_NAMESPACE
~~~

`YOUR_NAMESPACE` là chỗ cần thay bằng namespace thực; lệnh được đưa ra như **mẫu cú pháp**, không chạy với một cluster thật. Admission controllers, LimitRanges hoặc policy của cluster có thể thêm/đổi defaults so với YAML ban đầu. Do đó kiểm **Pod spec thực tế** khi giải thích log.

### 10.2. Vào đúng container để đọc JVM và cgroup

~~~bash
kubectl exec -n YOUR_NAMESPACE java-cpu-demo -c app -- \
  java -XshowSettings:system -version
~~~

Đây là lệnh mẫu cho image có Java launcher tại PATH. Một distroless/JRE image có thể thiếu `sh`, `jcmd` hoặc tools; không vì thiếu shell mà kết luận container không có giới hạn CPU.

Nếu có shell và quyền đọc cgroup v2, có thể dùng:

~~~bash
kubectl exec -n YOUR_NAMESPACE java-cpu-demo -c app -- \
  sh -c 'cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/cpu.stat'
~~~

**Kiểm tra đúng container**: pod có thể có sidecars hoặc init containers với resources khác nhau. Cgroup path của container/ancestor có thể ảnh hưởng budget thực. Không chạy lệnh với một container khác rồi suy sang JVM chính.

### 10.3. CPU metrics sau khởi động

`kubectl top pod` hoặc Prometheus/container metrics có thể cho usage/working set; muốn chẩn đoán **CPU throttling**, cần time series tương ứng (ví dụ cAdvisor counters với quota/throttled time), không chỉ một mẫu CPU usage tức thời. CPU quota có thể làm tăng tail latency dù average usage trông không cao.

## 11. `UseContainerSupport`: hiểu đúng ý nghĩa

Trên HotSpot/Linux hỗ trợ container metrics:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 |
  grep -E 'UseContainerSupport|ActiveProcessorCount'
~~~

Thông thường `UseContainerSupport` được bật mặc định và có thể tắt bằng `-XX:-UseContainerSupport`. Nhưng việc flag **đang true** chỉ chứng minh **tính năng nhận diện được phép hoạt động**, không chứng minh:

- JVM chắc chắn đang ở Docker/Kubernetes.
- Runtime có cgroup CPU hard limit.
- JVM đã nhận đúng cgroups v2.
- Số CPU báo là quota chính xác của kernel.
- Các thread pools sử dụng chính xác từng CPU-time slot.

### 11.1. Không tắt container awareness chỉ để sửa một con số

~~~bash
java -XX:-UseContainerSupport -jar app.jar
~~~

Lệnh trên **vô hiệu container detection** trên nền tảng hỗ trợ, nên có thể khiến JVM dựa vào host resources và chọn heap/thread defaults không phù hợp container. Không coi nó là “mẹo tăng CPU cho app” trong production. Nếu cần so sánh, chỉ thử trong benchmark/diagnostics được kiểm soát.

### 11.2. Flag có thể không tồn tại ngoài Linux

Trên **Windows HotSpot JDK** đã dùng để kiểm thử bài này, `HotSpotDiagnosticMXBean.getVMOption("UseContainerSupport")` ném lỗi **option không tồn tại**, dù các options `ActiveProcessorCount` và GC worker settings vẫn có. Tương tự, `-Xlog:os+container` không được đăng ký ở bản VM ấy.

**Bài học:** một Java code hoặc startup script hỗ trợ nhiều OS phải **kiểm xem option/tag có tồn tại trước khi đọc/bật**. Không dùng lỗi thiếu flag để suy container CPU quota. Nếu thật sự cần chạy trên Linux, hãy thử trong đúng Linux image.

### 11.3. Cách xem flags trên Windows

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String "ActiveProcessorCount|ParallelGCThreads|ConcGCThreads"
~~~

Trên Linux, bổ sung `UseContainerSupport` vào pattern khi hỗ trợ. Kết quả flags cho biết **giá trị trong JVM**, không phải hoàn toàn thay thế cgroup files.

## 12. `ActiveProcessorCount`: override để chẩn đoán, không phải CPU limit

`-XX:ActiveProcessorCount=N` đặt số processors mà HotSpot dùng khi quyết định các default thread pools (GC, ForkJoinPool và một số thành phần khác). Oracle JDK 25 cũng nêu rõ cờ này **vẫn có hiệu lực khi container support bị tắt**.

Ví dụ:

~~~bash
java -XX:ActiveProcessorCount=2 -XX:+UseG1GC -jar app.jar
~~~

Lệnh này có thể làm:

- `Runtime.availableProcessors()` trả `2`;
- G1 chọn lượng parallel/concurrent workers mặc định theo mức CPU giả định ấy (nếu không override worker flags);
- Một số concurrency defaults thay đổi.

Nó **không**:

- Đặt `cpu.max` hoặc thay Kubernetes CPU limit.
- Cấp 2 cores riêng biệt.
- Ngăn OS throttling.
- Làm mọi Executor/thread pool buộc có đúng 2 threads.
- Thay thế việc theo dõi CPU request/limit thực tế.

### 12.1. Nếu cả `ActiveProcessorCount` và GC thread flags đều được đặt?

~~~bash
java -XX:+UseG1GC \
  -XX:ActiveProcessorCount=2 \
  -XX:ParallelGCThreads=4 \
  -XX:ConcGCThreads=1 \
  -jar app.jar
~~~

Ở đây JVM dùng **2 active processors** làm thông tin đầu vào cho một số ergonomics, nhưng **`ParallelGCThreads` đã được đặt rõ là 4**. Không thể suy “active CPU=2 nên mọi GC thread flag=2”. Và nếu container chỉ có quota tương đương 1 CPU, GC vẫn có thể bị throttled khi nhiều workers hoạt động.

### 12.2. Vì sao không dùng cờ này để “chữa” mọi trường hợp?

Khi giá trị JVM báo sai, việc đặt `ActiveProcessorCount` tạm thời có thể là **biện pháp kiểm soát ergonomics** phù hợp nếu đã có bằng chứng. Tuy vậy, phải tìm nguyên nhân: JDK thiếu cgroup v2 support, container không có limit, cpuset bị kế thừa, ancestor cgroup giới hạn, launcher đã truyền các flags cũ hoặc CPU request đang bị hiểu nhầm là quota.

Nếu không xác minh nguồn gốc, ghi đè một con số có thể che một lỗi cấu hình hoặc tạo thêm CPU contention.

## 13. Chương trình Java 17+ chạy được: quan sát JVM-visible CPUs

Bài thực hành cung cấp **một chương trình Java độc lập**. Nó cố ý không đọc trực tiếp `/sys/fs/cgroup` vì những files đó là **Linux-specific**, còn Java source cần chạy ổn trên cả máy phát triển Windows lẫn Linux.

Chương trình:

- In `Runtime.availableProcessors()`.
- In `OperatingSystemMXBean.getAvailableProcessors()` từ API Java Management.
- Đọc các HotSpot VM options `ActiveProcessorCount`, `ParallelGCThreads` và `ConcGCThreads` qua `HotSpotDiagnosticMXBean`.
- Kiểm `Runtime.maxMemory()` là số dương và không vượt giới hạn explicit `-Xmx128m`.
- **Không in `UseContainerSupport`**, vì option có thể vắng mặt trên Windows/VM khác.
- Dùng flags cố định để ví dụ có **stdout chính xác**; việc xác nhận CPU quota container thực tế thực hiện bằng **Linux logs/cgroups** ở phần 5–12.

**Giới hạn portability:** `com.sun.management.HotSpotDiagnosticMXBean` nằm trong module `jdk.management` và có mặt trên các JDK HotSpot tương ứng; các VM khác có thể không cung cấp cùng cờ. Đây là ví dụ diagnostic phù hợp với HotSpot, không phải cách lấy cgroup CPU limit portable cho mọi Java runtime.

Lưu đúng file **`ContainerCpuDiagnosticsDemo.java`**:

~~~java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.lang.management.ManagementFactory;

public final class ContainerCpuDiagnosticsDemo {
    static String option(String name) {
        HotSpotDiagnosticMXBean bean = ManagementFactory.getPlatformMXBean(
                HotSpotDiagnosticMXBean.class);
        return bean.getVMOption(name).getValue();
    }

    public static void main(String[] args) {
        int visibleCpus = Runtime.getRuntime().availableProcessors();
        int osBeanCpus = ManagementFactory.getOperatingSystemMXBean()
                .getAvailableProcessors();
        long heapCap = Runtime.getRuntime().maxMemory();
        System.out.println("runtime-cpus=" + visibleCpus);
        System.out.println("os-mxbean-cpus=" + osBeanCpus);
        System.out.println("active-processor-count=" +
                option("ActiveProcessorCount"));
        System.out.println("parallel-gc-threads=" +
                option("ParallelGCThreads"));
        System.out.println("concurrent-gc-threads=" +
                option("ConcGCThreads"));
        System.out.println("max-heap-positive=" + (heapCap > 0));
        System.out.println("max-heap-at-most-128MiB=" +
                (heapCap <= 128L * 1024 * 1024));
    }
}
~~~

### 13.1. Biên dịch

~~~bash
javac --release 17 -encoding UTF-8 ContainerCpuDiagnosticsDemo.java
~~~

### 13.2. Chạy với giá trị tường minh

~~~bash
java -XX:+UseG1GC \
     -XX:ActiveProcessorCount=2 \
     -XX:ParallelGCThreads=2 \
     -XX:ConcGCThreads=1 \
     -Xms64m -Xmx128m \
     -Xlog:gc+init=info:file=gc-init.log \
     ContainerCpuDiagnosticsDemo
~~~

Cú pháp trên là POSIX shell với `\` nối dòng. Trên Windows PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 ContainerCpuDiagnosticsDemo.java
java -XX:+UseG1GC -XX:ActiveProcessorCount=2 -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1 -Xms64m -Xmx128m "-Xlog:gc+init=info:file=gc-init.log" ContainerCpuDiagnosticsDemo
~~~

### 13.3. Stdout chính xác đã kiểm chứng

~~~text
runtime-cpus=2
os-mxbean-cpus=2
active-processor-count=2
parallel-gc-threads=2
concurrent-gc-threads=1
max-heap-positive=true
max-heap-at-most-128MiB=true
~~~

Chương trình đã được biên dịch thành công với `javac --release 17 -encoding UTF-8` và chạy trên HotSpot JDK hiện có; **bảy dòng** ở trên khớp output thực tế.

### 13.4. Cần hiểu đúng vì sao stdout này luôn là 2

Khi chạy lệnh trên, ta **cố ý đặt** `ActiveProcessorCount=2` và GC worker flags. Bảy dòng chỉ chứng minh JVM **nhận các flags và API trả giá trị phù hợp**. Chúng **không chứng minh** kernel cgroup CPU quota=2 hoặc machine chạy trong Docker.

Để xác minh container detection thật:

1. Trên Linux container, chạy **một lượt không có** `ActiveProcessorCount`.
2. Xem `-XshowSettings:system`.
3. Xem `-Xlog:os+container=trace` trên HotSpot có tag ấy.
4. Đối chiếu `cpu.max`/`cpu.stat`/`cpuset.cpus.effective` ở cgroup đúng.
5. Chỉ sau đó mới cân nhắc override cho benchmarking/tuning.

### 13.5. Xác minh qua GC init log

Sau demo:

~~~bash
grep -E 'CPUs:|Parallel Workers:|Concurrent Workers:' gc-init.log
~~~

Trong môi trường kiểm thử Windows JDK hiện có, logfile chứa các thông tin:

~~~text
CPUs: 28 total, 2 available
Parallel Workers: 2
Concurrent Workers: 1
~~~

Trích đoạn **đã bỏ các prefix timestamps/tags**, chỉ là quan sát môi trường, **không phải expected output cố định trên mọi host**. Nó chứng minh GC init xác nhận 2 CPUs được JVM coi là available, 2 parallel workers và 1 concurrent worker theo flags. **Số host 28** đến từ máy thử, không phải số CPUs được mọi JVM nhìn thấy.

## 14. Cách quan sát thực tế trong Docker/Linux mà không ghi đè CPU detection

### 14.1. Tạo đối chứng CPU có quota

Với môi trường Docker hợp lệ và quyền phù hợp:

~~~bash
docker run --rm --cpus=1.5 \
  YOUR_JDK_IMAGE \
  java -XshowSettings:system -version
~~~

- `--cpus=1.5` yêu cầu container engine đặt CPU bandwidth quota tương đương khoảng **1,5 CPU**.
- `YOUR_JDK_IMAGE` phải là tên image thực có Java launcher, hỗ trợ kiến trúc/nền tảng đang dùng.
- Ví dụ chỉ có tính **mẫu quy trình**, bài không tự chạy Docker Linux container trong môi trường kiểm chứng.
- Số `Effective CPU Count` thường là **số nguyên do JVM tính**, không phải output `1.5` dưới dạng float; cách tính phụ thuộc JVM/version.
- Thêm một lượt không có `--cpus`, giữ mọi yếu tố khác giống nhau để so.

### 14.2. Kiểm trace JVM trong cùng quota

~~~bash
docker run --rm --cpus=1.5 \
  YOUR_JDK_IMAGE \
  java -Xlog:os+container=trace -version
~~~

Chỉ dùng với image HotSpot/Linux hỗ trợ. Nếu output không thấy quota, hãy kiểm container thật đang được cấp limit nào, cgroup v1/v2 và quyền/mount.

### 14.3. Kiểm thêm từ cgroup

Nếu image có `sh` và file cgroup v2 ở location phù hợp:

~~~bash
docker run --rm --cpus=1.5 \
  --entrypoint sh YOUR_JDK_IMAGE \
  -c 'cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/cpu.stat'
~~~

Ví dụ này cần image có `/bin/sh`. Với distroless image, dùng một môi trường debug/cách đọc metrics được platform cho phép; **không thay container production** chỉ để truy cập shell. Không tự cho rằng file ở root cgroup nếu runtime mount khác.

### 14.4. Điều kiện so sánh công bằng

Không dùng:

- JDK 17 trên host và JDK 25 trong container;
- container có quota nhưng lượt đối chứng trên host không có CPU affinity tương tự;
- flags `ActiveProcessorCount` được bật ở một bên, tắt bên còn lại;
- workloads khác hoặc image dependencies khác;

rồi kết luận chênh lệch do container CPU detection. Chốt **JDK build, image, flags, CPU quota, cgroup mode và khoảng đo**.

## 15. Khi chương trình đã chạy: `jcmd` và VM diagnostics

Trong một JVM đang hoạt động, khi attach được cho phép:

~~~bash
jcmd PID VM.info
jcmd PID VM.flags
jcmd PID VM.command_line
~~~

**Thay `PID` bằng process ID thật**. Lệnh `jcmd` đòi runtime/tool/permissions phù hợp và thường phải chạy từ cùng host hoặc context được phép. Với Kubernetes, jcmd có thể không có trong minimal runtime image; có thể dùng diagnostic tooling ở môi trường đã được quản lý thay vì sửa image production.

### 15.1. `VM.info`

Trên HotSpot/Linux có container awareness, `VM.info` có thể bao gồm phần tương đương:

~~~text
container (cgroup) information:
    container_type: cgroupv2
    active_processor_count: 2
    cpu_quota: ...
    cpu_period: ...
~~~

Đây là **định dạng minh họa**, không phải dump thực tế đã chạy từ pod. Các trường/tên field phụ thuộc JDK. Nó giúp kiểm runtime **sau khi startup**, đặc biệt khi service entrypoint có nhiều flags/env khác với lệnh test.

### 15.2. `VM.flags`

Giúp xác định các flag values JVM đang dùng, trong đó có những override được hỗ trợ. Nếu một script thêm `ActiveProcessorCount` qua `JAVA_TOOL_OPTIONS`/`JDK_JAVA_OPTIONS`, giá trị runtime có thể khác dự tính ban đầu.

### 15.3. `VM.command_line`

Giúp kiểm command line JVM thực được dùng, nhưng có thể chứa **path/tokens/parameters nhạy cảm** tùy deployment. Thu thập/log command line phải tuân thủ quy định bảo mật; đừng gửi nguyên output chứa credentials lên kênh không được phép.

### 15.4. Không thay đổi settings trong lúc incident nếu chưa có căn cứ

Mục tiêu của bài là **quan sát**, không phải chỉnh JVM giữa lúc production đang chịu tải. `jcmd VM.log` có khả năng cấu hình logging động ở JVM hỗ trợ, nhưng cần phân quyền và kiểm overhead. Ưu tiên startup flags hoặc chiến dịch đo có giới hạn, không bật trace dài hạn vô điều kiện.

## 16. Đối chiếu bốn nguồn chẩn đoán

Lập một bảng cho **đúng process/container và cùng thời điểm**:

| Nguồn | Ví dụ giá trị | Kết luận cho phép |
| --- | --- | --- |
| Kubernetes Pod spec | `limits.cpu=1500m` | Kubernetes dự định áp CPU limit 1,5 CPU |
| Linux cgroup v2 `cpu.max` | `150000 100000` | Kernel quota ở cgroup đó tương đương 1,5 CPU |
| HotSpot `-XshowSettings:system` | `Effective CPU Count: 2` | JVM suy ra/đang dùng count 2 cho ergonomics |
| Java `availableProcessors()` | `2` | Application thấy JVM CPU count 2 |
| `-Xlog:gc+init` | `Parallel Workers: 2` | G1 khởi tạo mức parallel workers này |
| `cpu.stat` theo thời gian | `Δnr_throttled > 0` | Có tình trạng throttling trong khoảng đo tại cấp accounting liên quan |

Đây là các **giá trị giả định có logic nhất quán**, không phải quan sát trực tiếp của cùng một container đã triển khai.

### 16.1. Nếu chúng không khớp thì sao?

Sự khác nhau **không tự chứng minh lỗi**:

- Quota 1,5 CPU nhưng `availableProcessors` cần một số nguyên; có thể dùng 2 theo heuristic của một runtime.
- Cpuset có 4 logical CPUs nhưng quota chỉ 1,5 CPU.
- G1 có thể dùng ít hơn active count vì heap hoặc ergonomics.
- CPU request 0,5 khác CPU limit 1,5.
- `ActiveProcessorCount` được override nên `availableProcessors` không phản ánh cgroup detection ban đầu.
- Thông tin được đọc ở **cgroup cha hoặc container khác**.
- JDK update/version có algorithm tính active CPUs khác.

Hãy tìm **nguồn chênh lệch cụ thể** trước khi đổi flags.

## 17. CPU request/weight không tự là số CPU cứng

Nhiều tài liệu cũ mô tả cách JVM dùng `cpu.shares`/`cpu.weight` để ước lượng active processor count. **Hành vi này đã thay đổi qua các JDK releases và backports**, đặc biệt trong các bản JDK hiện đại mà shares/weight không còn được diễn giải như một hard CPU limit cho active processor count theo cách cũ.

Vì vậy:

- Không giả định `cpu.shares / 1024` luôn bằng `availableProcessors`.
- Không giả định `cpu.weight / 100` là số CPUs.
- Không giả định Kubernetes CPU **request** quyết định số GC threads theo một công thức cố định.
- Không lấy hướng dẫn dành cho Java 8 update cũ áp nguyên vào JDK 17/21/25.
- Không dùng các cờ compatibility nội bộ hoặc đã bị loại bỏ để khôi phục heuristic cũ.

### 17.1. Khi container chỉ có CPU request, không có CPU limit

Pod có thể được cấu hình request, ví dụ `500m`, mà **không có hard quota**. Trong môi trường có CPU rảnh, nó có thể dùng hơn 0,5 CPU. Nếu JVM dựa vào cpuset/host count, `availableProcessors()` có thể lớn hơn 1.

Điều đó không tự là “JVM không tôn trọng request”. Request là **tín hiệu scheduling/resource sharing**, không mặc định là hard cap. Nếu business muốn JVM concurrency thấp hơn dù không có hard quota, cân nhắc `ActiveProcessorCount=N` với đầy đủ performance testing, không giả vờ kernel đã enforce quota.

### 17.2. Khi một bản JDK cũ xử lý shares khác

Đừng đối chiếu từ trí nhớ. Ghi rõ `java -version`, vendor, update/build, cgroup v1/v2 và startup flags, rồi đọc tài liệu/issue của đúng bản. Một số thay đổi được **backport** nên không thể suy behavior chỉ từ major Java version.

## 18. Phân tích CPU throttling: log JVM chỉ là một nửa câu chuyện

### 18.1. Vì sao `availableProcessors()` không nói được throttling?

`availableProcessors()` là một **số mô tả khả năng CPU/ergonomics tại thời điểm đọc**. Throttling là **hiện tượng theo thời gian**: cgroup đã dùng hết CPU time quota ở một khoảng nào đó và bị giới hạn.

Một tiến trình có thể báo `availableProcessors()=2` nhưng:

- Không hề bị throttling vì workload nhẹ.
- Bị throttling liên tục vì CPU quota thực thấp hơn workload yêu cầu.
- Bị chậm vì tranh CPU host dù không có quota hard cap.
- Bị chậm vì database/network chứ không phải CPU.
- Bị giới hạn bởi cpuset/affinity khác với quota.
- Có nhiều threads runnable hơn số CPUs khả dụng.

### 18.2. Cần time series

Ví dụ đọc cgroup v2 trước/sau một workload có tải:

~~~bash
cat /sys/fs/cgroup/cpu.stat
# Chạy workload quan sát trong khoảng thời gian được kiểm soát
cat /sys/fs/cgroup/cpu.stat
~~~

So sánh `nr_throttled` và `throttled_usec` giữa hai mẫu. Không dùng một giá trị tích lũy từ lúc container start để suy rằng một request cụ thể bị chậm bao nhiêu. Khi có nhiều processes trong một cgroup, counters là của **cgroup**, không tách riêng Java process.

Với Prometheus/container monitoring, đối chiếu:

- Total CPU seconds/usage rate.
- CFS periods và throttled periods.
- Throttled time rate theo metrics tương ứng.
- CPU quota/limits/requests và node contention.
- Application p95/p99 latency.
- JVM GC pause/thread pool queues.

### 18.3. Throttling cao và GC

Nếu `ParallelGCThreads` hoặc các thread pools quá lớn so với CPU quota, nhiều threads runnable tranh cùng quota; GC stop-the-world pause có thể dài hơn theo wall time. Tuy nhiên không nên **ngay lập tức** giảm GC threads hoặc tăng `ActiveProcessorCount`. Cần xác định:

1. JVM nhìn thấy số CPU nào?
2. Có override không?
3. G1 thực dùng bao nhiêu workers?
4. Quota/cpuset từ cgroup là gì?
5. Có throttling theo counters không?
6. Heap pressure có tạo GC thường xuyên không?
7. Application thread pool có quá lớn không?

**CPU starvation** có thể làm cả application và concurrent GC chậm; giải pháp có thể nằm ở **CPU limit/request, heap sizing, thread pool, GC tuning hoặc workload design**, tùy đo đạc.

## 19. Kịch bản lỗi điển hình và cách xử lý

### Kịch bản A – Host 32 CPUs, pod limit 2 CPUs, JVM báo 32

**Khả năng:** HotSpot không đọc được quota; cgroups v2 không được JDK cũ hỗ trợ; `UseContainerSupport` bị tắt; cgroup mount/path không nhận diện; container không có quota như tưởng; hoặc output lấy nhầm từ host.

Điều tra:

1. Xác minh `java -version` trong chính pod.
2. Đọc Pod spec sau admission.
3. Đọc `cpu.max` hoặc v1 quota/period từ đúng cgroup.
4. Chạy `-XshowSettings:system` và `-Xlog:os+container=trace`.
5. Kiểm `UseContainerSupport` và `ActiveProcessorCount`.
6. Nếu runtime thiếu cgroups v2 support, nâng JDK tới bản được hỗ trợ/chứa backport phù hợp.
7. Nếu cần xử lý tạm resource ergonomics, cân nhắc `ActiveProcessorCount=2` sau khi kiểm chứng, **không coi đây là sửa cgroup**.

### Kịch bản B – JVM báo 2 CPUs, pod vẫn bị throttled

**Khả năng:** CPU load cao hơn quota, quá nhiều runnable threads, GC/concurrent work cạnh tranh, hoặc quota từ ancestor/pod level tác động. `availableProcessors()=2` không đảm bảo pod sẽ không bị throttled.

Hướng xử lý: đo `cpu.stat` time series, request latency, GC workers, thread pools và node contention. Nếu workload thật cần nhiều CPU hơn, tối ưu hoặc cấp thêm CPU theo policy; không chỉ sửa log flags.

### Kịch bản C – Chạy Windows: `No metrics available`

**Không mặc định là lỗi.** `-XshowSettings:system`/`-Xlog:os+container` có phạm vi hỗ trợ theo OS/JDK; trên Windows test đã thấy không có container metrics và tag os+container bị cảnh báo. Dùng GC init log, Java APIs và hệ thống metrics của Windows/Windows Containers nếu có, thay vì cố đọc `/sys/fs/cgroup`.

### Kịch bản D – Cgroup v2 `cpu.max = max 100000`

Ý nghĩa: **không có quota CPU bandwidth ở cấp cgroup đó**. Vẫn có thể có cpuset, node contention, CPU weights, ancestor constraints và application throttling ở cấp khác. Không suy “CPU vô hạn”. Kiểm các nguồn điều phối trước khi tự ghi đè `ActiveProcessorCount`.

### Kịch bản E – CPU request 500m, JVM trả 8 CPUs

Nếu pod không có CPU limit, JVM trả 8 có thể hợp lý theo **cpuset/host/VM heuristics hiện hành**. CPU request 500m không phải limit 0,5 CPU. Nếu muốn giới hạn default pool sizes để phù hợp performance profile, đó là quyết định tuning **khác** với container quota.

### Kịch bản F – Thấy `cpu.weight=100`, operator kết luận 100 CPU

Sai. Weight là trọng số tương đối giữa các cgroups khi tranh chấp. Cần `cpu.max` hoặc cpuset và thông số CPU thực, không lấy weight làm số cores.

### Kịch bản G – Pod đã được nâng CPU limit nhưng `availableProcessors()` không đổi

Khả năng: JVM tính count khi startup hoặc cache/ergonomics không tự cập nhật theo thay đổi cgroup; cũng có thể flags explicit đang override. **Không giả định mọi JVM thay ngay heap/worker counts khi cgroup quota thay đổi nóng**. Kiểm chính xác JDK version và test restart/quy trình rollout nếu policy yêu cầu.

### Kịch bản H – Chẩn đoán thiếu vì image distroless

Image không có `bash`/`jcmd`/`cat` không đồng nghĩa không có container support. Dùng startup logs, metrics từ orchestration/sidecar được phép hoặc debug container theo chính sách, nhưng **không sửa immutable runtime image** chỉ để một lệnh demo chạy.

## 20. CPU và memory detection là hai bài toán khác nhau

JVM container-aware còn có thể dùng cgroup **memory limits** để đặt ergonomics/heap size. Nhưng:

- CPU quota/limit không quyết định trực tiếp `-Xmx`.
- `memory.max` của cgroup v2 là giới hạn bộ nhớ, không phải CPU quota.
- `-Xmx` chỉ giới hạn Java heap; JVM còn metaspace, native memory, thread stacks, code cache, direct buffers.
- Đặt `-Xmx` bằng 100% container memory limit có thể gây OOMKill do native overhead.
- `UseContainerSupport` có thể ảnh hưởng cả CPU và memory detection, nên tắt nó có tác động rộng hơn việc “chỉnh số CPU”.
- Khi chỉ điều tra CPU, đừng thay heap flags nếu không có dữ liệu memory pressure.

Ví dụ chương trình phần 13 đặt `-Xmx128m` chỉ để kiểm **heap cap** dưới một số byte rõ ràng; nó không lấy mẫu memory limit của cgroup. Vì vậy `max-heap-at-most-128MiB=true` **không** chứng minh một container Linux được cấp 128 MiB RAM.

## 21. Xây quy trình kiểm thử tái lập được trong CI hoặc staging

Một quy trình tốt để kiểm JVM container awareness:

~~~text
1. Chọn đúng Linux JDK image và ghi version/vendor/build.
2. Ghi Docker/Kubernetes CPU request/limit, cpuset và policy.
3. Khởi chạy JVM không có ActiveProcessorCount override.
4. Thu -XshowSettings:system vào startup diagnostics.
5. Thu -Xlog:os+container=trace ngắn hạn khi cần phân tích sâu.
6. Thu -Xlog:gc+init=info để biết workers/CPU count JVM dùng.
7. Đọc cgroup v1/v2 CPU quota, cpuset và cpu.stat đúng process.
8. Chạy workload có tải, đo usage/throttling theo thời gian.
9. So JVM availableProcessors, CPU limit và request latency.
10. Nếu có mismatch, chẩn đoán JDK/cgroup/override trước khi tuning.
11. Thử ActiveProcessorCount chỉ như một biến độc lập có chủ đích.
12. Lưu kết quả, không log credentials hay dữ liệu vận hành nhạy cảm.
~~~

### 21.1. Ma trận thử đề nghị

| Trường hợp | Cgroup condition | Điều muốn xem |
| --- | --- | --- |
| A – Không hard quota | `cpu.max = max ...` hoặc v1 quota `-1` | JVM dựa vào cpuset/OS/heuristics thế nào |
| B – Quota 1 CPU | `100000 100000` | JVM effective count và GC worker defaults |
| C – Quota 1,5 CPU | `150000 100000` | Quy tắc làm tròn/active count của JDK cụ thể |
| D – Cpuset hẹp | Có thể chỉ có 2 logical CPU IDs | JVM và OS phản ánh affinity thế nào |
| E – Weight khác | Quota/cpuset không đổi, weight khác | Thông tin weight không đồng nghĩa hard limit |
| F – Manual override | `ActiveProcessorCount=2` | JVM APIs/GC flags thay dù kernel quota giữ nguyên |
| G – cgroup v1/v2 | Cùng quota danh nghĩa, kernel/provider khác | Detection và log formats có khớp không |
| H – CPU load cao | Cgroup có quota rõ ràng | Throttling tăng thế nào theo khoảng thời gian |

**Không cần** tạo các Pod thật trong môi trường production để làm bài học. Chạy CI/staging với quyền được phép; không ép CPU stress lên shared nodes hoặc customer workloads.

### 21.2. Vì sao phải kiểm sau khi nâng JDK?

Ergonomics và container support đã thay đổi giữa JDK releases. Khi nâng JDK 17 → JDK mới hơn, những thứ có thể thay:

- Cách đọc cgroups v1/v2.
- Quy tắc tính active CPU count từ quota/cpuset.
- Cách xem shares/weights và số processors khi không có quota.
- Mặc định GC/thread pool sizing.
- Log lines/diagnostic fields.
- JVM option availability theo OS.

Bài học bền vững không ghi cứng “Java N luôn lấy request.cpu chia 1000” hoặc “JDK nào cũng in một mẫu log như nhau”. Hãy coi **command + cgroup evidence + runtime metrics** là nguồn sự thật.

## 22. Những nhầm lẫn phổ biến cần loại bỏ

| Nhận định sai | Lý do sai | Cách kiểm đúng |
| --- | --- | --- |
| “`UseContainerSupport=true` nghĩa JVM đang ở container” | Flag chỉ cho phép detection | Xem provider/cgroup/Pod spec |
| “`-Xlog:os+container=trace` chạy mọi OS” | Tag/feature Linux-specific theo VM build | Kiểm `-Xlog:help`, chạy trong Linux HotSpot |
| “`No metrics available` nghĩa không có quota” | Có thể OS/JDK không hỗ trợ metrics | Kiểm kernel/runtime và đúng JDK update |
| “`availableProcessors=2` nghĩa 2 cores độc quyền” | Số JVM dùng cho heuristics | Đối chiếu quota/cpuset/scheduler |
| “`ActiveProcessorCount=2` đặt cgroup CPU limit=2” | Cờ chỉ override JVM count | Xem `cpu.max`/limits |
| “CPU request 500m là hard cap 0,5 core” | Request khác limit | Kiểm Pod requests/limits |
| “`cpu.weight=100` là 100 CPUs” | Weight là relative priority | Kiểm quota/cpuset |
| “`cpu.max = max 100000` nghĩa infinite hardware” | Chỉ không quota ở cgroup đó | Kiểm ancestor/cpuset/contending pods |
| “Cpuset 0-3 tức quota 4 CPUs” | Cpuset là tập CPUs được chạy | Đọc cả `cpu.max` |
| “Quota 150000/100000 phải in 1.5 processors” | JVM CPU count là nguyên | Xem actual JDK heuristics |
| “GC parallel workers luôn bằng available CPUs” | GC ergonomics/explicit flags khác | Xem GC init flags và worker logs |
| “`ParallelGCThreads=8` nghĩa 8 CPU thực” | Thread runnable khác CPU quota | Đo throttling/CPU time |
| “Thấy host CPU 28 nên pod có 28 CPU” | Host và container khác | Kiểm inside container |
| “Một lần `cpu.stat` đủ biết incident” | Counters tích lũy | Đo delta theo thời gian |
| “v1 `throttled_time` và v2 `throttled_usec` cùng unit” | Một cái thường ns, một cái µs | Đọc docs cgroup version |
| “Chỉ cần nâng JDK thì CPU throttling biến mất” | Quota/CPU contention vẫn tồn tại | Đo workloads và resources |
| “Không có `sh` trong image nghĩa không có cgroup” | Image tối giản thiếu tools | Dùng orchestration diagnostics |
| “Tắt `UseContainerSupport` giúp JVM tối ưu hơn trong pod” | Có thể dùng host ergonomics quá lớn | Đo và giữ detection phù hợp |
| “JDK 10 hỗ trợ cgroup v2 đầy đủ như JDK 25” | Support được bổ sung/backport sau này | Kiểm update/release |
| “GC log CPU available chính là quota” | Có thể bị `ActiveProcessorCount` override | Kiểm flags và cgroup |
| “Không throttling nhưng request chậm thì chắc CPU không liên quan” | CPU contention/affinity có thể vẫn ảnh hưởng | Đo OS scheduler/CPU usage và app profiling |
| “Kết quả Windows chứng minh Linux container behavior” | Windows không cung cấp cùng cgroup tags | Chạy Linux integration test |
| “Một CPU count đủ xác minh container awareness” | Cần nhiều nguồn bằng chứng | Pod spec + cgroup + JVM + metrics |

## 23. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Java version nào đánh dấu cải tiến container resource detection `UseContainerSupport` trong HotSpot?

**Đáp án:** **Java 10** (JDK-8146115) là mốc liên quan trong bài; cơ chế tiếp tục được cập nhật trên JDK hiện đại.

**Câu 2.** Lệnh nào được Oracle gợi ý cho log container chi tiết trên HotSpot/Linux?

**Đáp án:** `java -Xlog:os+container=trace -version`.

**Câu 3.** Có thể dùng `-Xlog:os+container=trace` trên Windows JDK như một yêu cầu bắt buộc không?

**Đáp án:** Không. Tag có thể không tồn tại; trên Windows JDK thử nghiệm đã xuất cảnh báo không tìm thấy tag set.

**Câu 4.** Lệnh nào cho bảng Operating System Metrics của JVM?

**Đáp án:** `java -XshowSettings:system -version`, khi VM/platform có hỗ trợ metrics thích hợp.

**Câu 5.** `No metrics available for this platform` có chứng minh container không có CPU quota không?

**Đáp án:** Không. Có thể JDK/OS/cgroups version không hỗ trợ, hoặc mount/permission không cho đọc; phải kiểm nguồn khác.

**Câu 6.** `cpu.max = 200000 100000` tương đương bao nhiêu CPU bandwidth?

**Đáp án:** Khoảng **2 CPU** (200000/100000), không phải hai CPU vật lý được dành riêng.

**Câu 7.** `cpu.max = max 100000` nghĩa gì?

**Đáp án:** Không có hard bandwidth quota ở cấp cgroup đó; vẫn có thể có giới hạn khác.

**Câu 8.** `cpu.max = 150000 100000`, JVM bắt buộc `availableProcessors()=1.5`?

**Đáp án:** Không. API trả một số nguyên; quy tắc quy đổi thuộc JDK/runtime cụ thể.

**Câu 9.** `cpu.weight` có phải absolute CPU limit không?

**Đáp án:** Không. Đây là relative weight chia CPU khi tranh chấp.

**Câu 10.** Kubernetes `requests.cpu: 500m` có phải limit 500m không?

**Đáp án:** Không; chỉ là request. Limit phải xem `limits.cpu`/cgroup và admission policy.

**Câu 11.** `cpuset.cpus.effective=0-3` nói gì?

**Đáp án:** Task được phép chạy trên bốn logical CPU IDs. Nó không xác định CPU time quota.

**Câu 12.** Chỉ nhìn `Runtime.availableProcessors()=2` có thể chứng minh Docker limit=2 không?

**Đáp án:** Không. Có thể do `ActiveProcessorCount`, affinity hoặc JVM heuristics.

**Câu 13.** `-XX:ActiveProcessorCount=2` có sửa Linux `cpu.max` không?

**Đáp án:** Không; đó là JVM-only override cho CPU count/ergonomics.

**Câu 14.** Trong Java demo có `parallel-gc-threads=2` vì sao?

**Đáp án:** Vì lệnh chạy **đặt tường minh** `-XX:ParallelGCThreads=2`.

**Câu 15.** `Runtime.maxMemory()` có tự cho biết CPU quota không?

**Đáp án:** Không. Đó là thông tin Java heap, không liên quan trực tiếp quota CPU.

**Câu 16.** Cgroup v2 dùng file nào theo dõi CPU throttling?

**Đáp án:** `cpu.stat`, xem `nr_throttled` và `throttled_usec` cùng các trường liên quan khi có.

**Câu 17.** Vì sao đọc `cpu.stat` hai lần tốt hơn một lần?

**Đáp án:** Để tính delta trong một khoảng workload; counters là tích lũy, không mô tả riêng request hiện tại.

**Câu 18.** Cgroup v1 `throttled_time` và cgroup v2 `throttled_usec` có cùng unit không?

**Đáp án:** Không. v1 thường báo nanoseconds; v2 báo microseconds.

**Câu 19.** Nếu Windows không có `UseContainerSupport` option, `ActiveProcessorCount` còn dùng được không?

**Đáp án:** Có thể có; trong JDK Windows đã kiểm thử, `ActiveProcessorCount` tồn tại và chương trình nhận giá trị 2. Chỉ cần không suy Linux container support từ đó.

**Câu 20.** Khi nào cần `jcmd PID VM.info`?

**Đáp án:** Khi cần xem thông tin JVM đang chạy, bao gồm container section nếu platform/JDK hỗ trợ; dùng đúng quyền và lưu ý thông tin nhạy cảm.

**Câu 21.** Vì sao một pod vẫn bị CPU throttling dù JVM báo đúng 2 CPUs?

**Đáp án:** Workload/GC/concurrency có thể cần nhiều hơn quota, hoặc có ancestor constraints; CPU count đúng không bảo đảm đủ CPU time.

**Câu 22.** Khi chỉ có CPU request mà không có limit, JVM báo host/cpuset count có tự sai không?

**Đáp án:** Không nhất thiết. Request không phải hard cap; phải xét policy/runtime/algorithm của JDK.

**Câu 23.** JDK 10 có thể nhận cgroups v2 y hệt JDK 17+ không?

**Đáp án:** Không. Hỗ trợ v2 được bổ sung về sau và backport theo những bản update cụ thể.

**Câu 24.** Cần những nguồn nào trước khi kết luận JVM đã hiểu đúng CPU limit?

**Đáp án:** **Pod/container config**, **cgroup v1/v2 thực tế**, **JVM diagnostics** và **usage/throttling metrics theo thời gian**, cùng JDK version/flags.

## 24. Checklist vận hành ngắn gọn

Trước khi báo cáo “JVM nhận sai CPU container”, xác minh:

1. **Đúng Java process/container/pod/namespace** chưa?
2. **JDK vendor/version/update và OS** đang là gì?
3. **JVM có hỗ trợ Linux container metrics/cgroup v2** không?
4. **`UseContainerSupport`** có khả dụng/đang bật trên HotSpot/Linux không?
5. **`ActiveProcessorCount`** có bị override qua args, env hoặc launcher không?
6. **CPU request và CPU limit thực** sau admission là bao nhiêu?
7. **Cgroup v1 hay v2**, path/mount đã xác định đúng chưa?
8. **Quota/period** hữu hạn hay unlimited?
9. **Cpuset/affinity** effective cho tiến trình là gì?
10. **Shares/weight** đang là relative priority hay bạn nhầm nó thành hard limit?
11. **`-XshowSettings:system`** có provider và CPU fields hợp lệ không?
12. **`-Xlog:os+container=trace`** có tag hỗ trợ và nội dung phát hiện cgroup không?
13. **`-Xlog:gc+init=info`** báo CPU available/GC workers bao nhiêu?
14. **`Runtime.availableProcessors()`** có khớp JVM flags không?
15. **Có số liệu `cpu.stat` delta/throttling** trong khoảng phát sinh chậm không?
16. **Có giới hạn cgroup parent/pod level** mà file con không mô tả hết không?
17. **Node CPU contention** có xảy ra không?
18. **GC/JIT/ForkJoin/executor thread pools** có quá mức CPU budget không?
19. **Có logging overhead/retention/security** khi bật trace không?
20. **Có test lại với JVM mặc định không override trước khi tuning** không?
21. **Có so sánh cùng JDK image, workload, quota và môi trường** không?
22. **Có ghi rõ phần nào là output đã chạy, phần nào là ví dụ minh họa** không?
23. **Có plan nâng JDK cũ lên bản đang được hỗ trợ** thay vì dựa flags lỗi thời không?
24. **Sau khi sửa cấu hình, có xác minh cả JVM count, cgroup limit, throttling và application latency** không?

## 25. Nguồn tham khảo chính thức còn áp dụng

1. [Oracle Java SE 10 – java launcher](https://docs.oracle.com/javase/10/tools/java.htm): tài liệu gốc về `UseContainerSupport` và `ActiveProcessorCount` tại mốc Java 10.
2. [Oracle Java SE 17 – java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): các tùy chọn JVM và unified logging liên quan.
3. [Oracle Java SE 25 – java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:-UseContainerSupport` Linux-only, `-Xlog:os+container=trace` và `-XX:ActiveProcessorCount` vẫn áp dụng.
4. [OpenJDK – JDK-8146115](https://bugs.openjdk.org/browse/JDK-8146115): container detection/resource configuration và nguồn gốc Java 10.
5. [OpenJDK – JDK-8230305](https://bugs.openjdk.org/browse/JDK-8230305): hỗ trợ cgroups v2 được bổ sung cho HotSpot.
6. [OpenJDK – JDK-8281571](https://bugs.openjdk.org/browse/JDK-8281571): thay đổi liên quan cách JVM xử lý CPU shares/cgroups và active processor count.
7. [Kubernetes – Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU requests/limits và enforcement.
8. [Kubernetes – About cgroup v2](https://kubernetes.io/docs/concepts/architecture/cgroups/): lưu ý cgroups v2, JDK versions tương thích và kernel requirements.
9. [Linux Kernel – Control Group v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `cpu.max`, `cpu.stat`, `cpu.weight`, `cpuset.cpus.effective`.
10. [Linux Kernel – CFS Bandwidth Control](https://docs.kernel.org/scheduler/sched-bwc.html): nguyên tắc quota/period, bandwidth và throttling trong Linux.
11. [Red Hat – Java 17: What's new in OpenJDK's container awareness](https://developers.redhat.com/articles/2022/04/19/java-17-whats-new-openjdks-container-awareness): ví dụ `-XshowSettings:system`/`VM.info`, cgroups v1/v2 và container-aware MXBeans.
12. [Red Hat – How to use Java container awareness in OpenShift 4](https://developers.redhat.com/articles/2024/03/14/how-use-java-container-awareness-openshift-4): đối chiếu output container-aware và output host như `lscpu`.
13. [Java SE 17 – Runtime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `availableProcessors()` và `maxMemory()`.
14. [Java SE 17 – OperatingSystemMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html): `getAvailableProcessors()`.
15. [Java SE 17 – HotSpotDiagnosticMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html): cách đọc các VM options có hỗ trợ.
16. [Oracle Java SE 17 – jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.info`, `VM.flags`, `VM.command_line`.

**Tóm tắt cuối:** Khả năng hiểu giới hạn CPU Docker/Linux container của HotSpot được cải tiến từ Java 10 và tiếp tục phát triển trên các JDK hiện đại. Để **quan sát** thay vì suy đoán, hãy dùng **`-XshowSettings:system`** và **`-Xlog:os+container=trace` trên Linux/HotSpot hỗ trợ**, rồi đối chiếu **`cpu.max`/`cpu.stat`/cpuset**, **`Runtime.availableProcessors()`**, **`-Xlog:gc+init=info`**, JDK flags và **Kubernetes requests/limits**. Phân biệt quota với weight, số CPU JVM nhìn thấy với CPU scheduler thực sự cấp, và CPU count với throttling theo thời gian. **`ActiveProcessorCount` chỉ ghi đè JVM ergonomics, không đặt hard CPU limit của container.**
