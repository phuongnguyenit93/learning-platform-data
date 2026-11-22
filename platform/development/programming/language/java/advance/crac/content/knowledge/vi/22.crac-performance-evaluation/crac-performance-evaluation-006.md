# Đo RSS, bộ nhớ container, CPU và dung lượng lưu trữ ảnh

Đánh giá hiệu năng Java CRaC không thể chỉ nhìn vào thời gian restore. Một checkpoint có thể rút ngắn thời gian khởi động JVM nhưng làm tăng bộ nhớ resident, dung lượng artifact, thời gian đọc storage hoặc mức sử dụng CPU trong giai đoạn phục hồi. Trong Kubernetes, giới hạn memory và CPU của container còn có thể khiến một Pod restore nhanh trên máy phát triển nhưng bị throttling hoặc OOM khi chạy dưới quota thực tế.

Để so sánh cold start với restore một cách có ý nghĩa, cần đo riêng ít nhất bốn nhóm: **RSS và bộ nhớ tiến trình**, **memory accounting của container**, **CPU usage/throttling**, và **dung lượng checkpoint trên storage**. Cần ghi nhận các số đo tại cùng mốc vòng đời, cùng workload và cùng giới hạn tài nguyên. Các chỉ số này có ý nghĩa khác nhau; RSS không bằng Java heap, memory usage của container không bằng RSS của một tiến trình, CPU percentage không phải CPU time, và kích thước archive không nhất thiết bằng dung lượng filesystem thực tế.

## 1. Xác định các đại lượng cần đo

Trước khi thu thập số liệu, hãy thống nhất tên và đơn vị để không so sánh nhầm các đại lượng khác nhau.

| Đại lượng | Ý nghĩa | Nguồn đo thường dùng |
|---|---|---|
| RSS (Resident Set Size) | Các trang bộ nhớ của tiến trình hiện đang resident trong RAM | `/proc/<pid>/status`, `smaps_rollup` |
| PSS (Proportional Set Size) | Bộ nhớ resident chia tỷ lệ theo số tiến trình cùng map một trang | `/proc/<pid>/smaps_rollup` |
| USS (Unique Set Size) | Các trang private chỉ thuộc tiến trình | Tổng private clean/dirty trong `smaps_rollup` |
| Java heap used/committed | Heap đang sử dụng và heap JVM đã commit | JMX `MemoryMXBean`, GC logs, JFR |
| Native memory | Bộ nhớ native JVM và một phần thư viện native | Native Memory Tracking (NMT), profiler, OS metrics |
| Container memory current | Bộ nhớ đang được tính cho cgroup/container | cgroup v2 `memory.current`, v1 `memory.usage_in_bytes` |
| Container working set | Ước lượng phần memory đang hoạt động, thường loại trừ một phần inactive file cache | cAdvisor / Kubernetes metrics |
| CPU time | Thời gian CPU thực sự được tiến trình hoặc cgroup sử dụng | `/proc`, cgroup `cpu.stat`, process metrics |
| CPU throttling | Thời gian hoặc số chu kỳ bị giới hạn bởi CPU quota | cgroup `cpu.stat`, cAdvisor |
| Checkpoint apparent size | Tổng kích thước logic của các file checkpoint | `du --apparent-size`, tổng file size |
| Checkpoint allocated size | Số block filesystem thực sự cấp phát | `du`, filesystem metrics |
| Archive/object size | Số byte sau đóng gói hoặc nén | `stat`, object storage metadata |

Không cộng RSS của mọi tiến trình rồi coi đó là memory của container nếu chúng có shared pages. Ngược lại, container có thể có nhiều tiến trình và page cache ngoài RSS của JVM. Khi đánh giá khả năng chạy dưới memory limit, số liệu cgroup thường là nguồn quyết định; RSS/PSS giúp giải thích tiến trình đang sử dụng phần nào.

## 2. RSS, PSS và USS của tiến trình Java

### 2.1. RSS

RSS là số trang của tiến trình hiện đang nằm trong RAM. Đây là chỉ số hữu ích để quan sát footprint resident của JVM, nhưng nó bao gồm cả shared pages và không cho biết trang nào thuộc heap, metaspace, code cache, thread stack hay mapping của file.

Trên Linux, có thể xem RSS bằng:

```bash
grep -E '^(VmRSS|VmHWM|VmSize|VmPeak):' /proc/<pid>/status
```

Các trường thường gặp:

- `VmRSS`: RSS hiện tại, thường được hiển thị theo kB.
- `VmHWM`: high-water mark của RSS kể từ khi tiến trình bắt đầu.
- `VmSize`: virtual address space, không phải RAM thực tế đang sử dụng.
- `VmPeak`: mức virtual memory lớn nhất đã quan sát.

`VmSize` có thể lớn hơn RAM rất nhiều do JVM reserve vùng heap hoặc memory map. Không dùng `VmSize` thay cho RSS hay container memory.

### 2.2. PSS và USS

`/proc/<pid>/smaps_rollup` tổng hợp số liệu của các vùng memory map:

```bash
cat /proc/<pid>/smaps_rollup
```

Các trường đáng chú ý:

- `Rss`: tổng resident pages.
- `Pss`: shared pages được chia tỷ lệ theo số mapping/process cùng sử dụng.
- `Private_Clean` và `Private_Dirty`: trang private sạch và bẩn.
- `Shared_Clean` và `Shared_Dirty`: trang shared sạch và bẩn.
- `Anonymous`: anonymous resident memory.

Có thể ước lượng USS bằng `Private_Clean + Private_Dirty`. PSS hữu ích khi nhiều JVM cùng map thư viện hoặc file page cache; USS hữu ích khi ước lượng phần bộ nhớ chỉ thuộc một process. Các số này là snapshot tại thời điểm đọc và có thể thay đổi ngay sau đó.

Ví dụ lấy các trường chính:

```bash
awk '/^(Rss|Pss|Private_Clean|Private_Dirty|Shared_Clean|Shared_Dirty|Anonymous):/ { print }' \
  /proc/<pid>/smaps_rollup
```

Không phải mọi kernel hoặc quyền container đều cho phép đọc đầy đủ `smaps_rollup`. Nếu file không tồn tại hoặc bị permission denied, ghi nhận giới hạn này và dùng cgroup metrics cùng nguồn đo khác.

## 3. Phân biệt RSS với Java heap và native memory

JVM quản lý nhiều vùng bộ nhớ ngoài heap. Một process Java có thể dùng:

- Java heap chứa object.
- Metaspace và compressed class space chứa metadata lớp.
- JIT code cache chứa mã máy đã biên dịch.
- Thread stacks cho các thread Java/native.
- Direct buffers và memory mapping.
- Native allocations của JVM, JNI, TLS, compression, database driver và thư viện khác.
- File-backed mappings và page cache được kernel quản lý.

Vì vậy, `MemoryMXBean.getHeapMemoryUsage().getUsed()` không đại diện cho RSS. Heap committed cũng không bằng RSS: một phần heap committed có thể chưa được chạm tới, còn RSS có thể chứa nhiều native memory.

Đo heap qua JMX:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public final class MemorySnapshot {
    public static void printHeap() {
        MemoryUsage heap = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage();

        System.out.printf(
                "heap.used.bytes=%d heap.committed.bytes=%d heap.max.bytes=%d%n",
                heap.getUsed(), heap.getCommitted(), heap.getMax());
    }
}
```

JMX cho biết trạng thái heap ở góc nhìn JVM. Hãy ghi kèm RSS/PSS và cgroup memory để thấy phần chênh lệch nằm ở native/runtime, page cache hoặc tiến trình phụ trợ.

### 3.1. Native Memory Tracking

HotSpot Native Memory Tracking (NMT) có thể giúp phân loại một phần native memory do JVM quản lý. Bật NMT lúc khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Hoặc dùng `detail` khi cần thông tin chi tiết hơn, với chi phí theo dõi lớn hơn:

```bash
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Sau đó truy vấn:

```bash
jcmd <pid> VM.native_memory summary
```

NMT có thể báo các nhóm như Java Heap, Class, Thread, Code, GC, Compiler và Internal. Nó hữu ích để giải thích footprint JVM nhưng không phải bộ đếm tổng bộ nhớ hệ thống. NMT không bao phủ mọi allocation do thư viện native bên thứ ba hoặc mọi memory mapping bên ngoài JVM; hãy đối chiếu với `/proc` và cgroup.

NMT phải được bật khi JVM khởi động. Không thể bật đầy đủ NMT hồi tố cho một tiến trình đang chạy. Việc bật NMT cũng có overhead, vì vậy cần dùng nhất quán giữa các lần benchmark hoặc tách riêng lần chạy chẩn đoán.

### 3.2. Ghi nhận GC và JFR

GC logs giúp hiểu heap occupancy, pause và allocation pressure:

```bash
java -Xlog:gc*,safepoint:file=/var/log/app-gc.log:time,uptime,level,tags \
  -jar app.jar
```

JFR có thể cung cấp execution samples, allocation, thread, GC và compilation events. Khi so sánh restore, dùng cùng cấu hình ghi JFR ở cả hai nhánh. Công cụ quan sát cũng tiêu thụ CPU và bộ nhớ; đừng so sánh một lần chạy có profiler với một lần chạy không profiler rồi kết luận đó là chênh lệch CRaC.

## 4. Đo bộ nhớ container bằng cgroup

Trong container, cgroup là nguồn quan trọng để biết kernel tính bao nhiêu bộ nhớ cho workload. Kubernetes có thể hiển thị memory usage qua metrics pipeline, nhưng đọc cgroup trực tiếp giúp hiểu giới hạn và trạng thái tại thời điểm đo.

### 4.1. Xác định cgroup version

Trên Linux, cgroup v2 thường mount tại `/sys/fs/cgroup` và có file `cgroup.controllers`. Có thể kiểm tra:

```bash
test -f /sys/fs/cgroup/cgroup.controllers && echo cgroup-v2
```

Nếu không có file đó, hệ thống có thể dùng cgroup v1 hoặc layout hybrid. Trong container, đường dẫn cgroup thực tế có thể được tìm từ `/proc/self/cgroup` và mount information.

### 4.2. cgroup v2

Các file thường hữu ích:

| File | Ý nghĩa |
|---|---|
| `memory.current` | Bộ nhớ hiện đang được tính cho cgroup |
| `memory.max` | Giới hạn memory; `max` nghĩa là không đặt limit ở cấp cgroup đó |
| `memory.peak` | Mức memory cao nhất đã ghi nhận nếu kernel hỗ trợ |
| `memory.stat` | Chi tiết anonymous, file, kernel, slab và các loại memory khác |
| `memory.events` | Bộ đếm sự kiện như `high`, `max`, `oom`, `oom_kill` |
| `cpu.stat` | CPU usage và thông tin throttling |
| `cpu.max` | Quota và period của CPU |

Đọc snapshot:

```bash
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/cpu.stat
cat /sys/fs/cgroup/cpu.max
```

`memory.current` tính memory của toàn cgroup, có thể bao gồm anonymous memory, file cache và một số kernel memory. Do đó nó thường khác RSS của JVM. `memory.events` giúp phát hiện áp lực memory và OOM; nếu `oom_kill` tăng sau restore, hãy kiểm tra peak memory và limit thay vì chỉ xem heap used.

`memory.peak` có thể không có trên kernel cũ hoặc không được expose trong namespace container. Nếu cần peak theo từng phase, hãy ghi mẫu `memory.current` định kỳ hoặc dùng metrics từ node/cAdvisor. Không reset high-water mark trong lúc benchmark nếu điều đó làm mất khả năng so sánh giữa các phase.

### 4.3. cgroup v1

Với cgroup v1, các file thường có tên khác:

| File | Ý nghĩa |
|---|---|
| `memory.usage_in_bytes` | Memory đang được tính cho cgroup |
| `memory.limit_in_bytes` | Giới hạn memory |
| `memory.max_usage_in_bytes` | High-water mark |
| `memory.stat` | Chi tiết memory và cache |
| `memory.failcnt` | Số lần vượt ngưỡng giới hạn |
| `cpuacct.usage` | CPU time tích lũy theo nanosecond |
| `cpu.stat` | Thống kê quota/throttling nếu controller được bật |
| `cpu.cfs_quota_us` / `cpu.cfs_period_us` | CPU quota và period |

Đường dẫn mount của v1 có thể khác giữa các bản phân phối container. Dùng `/proc/self/cgroup` và `/proc/mounts` để xác định đường dẫn thực tế thay vì hard-code mọi môi trường vào một script.

### 4.4. Container working set

Kubernetes metrics thường có `container_memory_working_set_bytes`, được cAdvisor tính từ memory usage sau khi trừ một phần inactive file cache. Đây là chỉ số hữu ích để quan sát áp lực memory của workload, nhưng cách tính phụ thuộc cAdvisor và kernel. Đừng coi working set là RSS hoặc tổng chính xác mọi byte mà container có thể dùng.

Đối chiếu tối thiểu ba số: process RSS/PSS, cgroup memory current/peak và container working set. Nếu cgroup memory cao hơn RSS đáng kể, kiểm tra file cache, native/kernel memory hoặc các tiến trình khác trong cùng cgroup.

## 5. Đo memory trong Kubernetes

Kubernetes phân biệt request và limit:

- `resources.requests.memory` ảnh hưởng scheduling và một số quyết định QoS.
- `resources.limits.memory` đặt giới hạn memory cho container; vượt giới hạn có thể dẫn tới OOM kill.
- `kubectl top pod` cung cấp snapshot từ Metrics Server, không thay thế time series hoặc high-water mark.

Ví dụ:

```yaml
resources:
  requests:
    cpu: "1"
    memory: "2Gi"
  limits:
    cpu: "2"
    memory: "3Gi"
```

Các giá trị chỉ minh họa. Chọn request/limit từ phân bố đo được trong điều kiện restore và steady-state, có tính đến peak, native memory, page cache và tiến trình phụ trợ.

Lấy snapshot:

```bash
kubectl top pod -n production
kubectl top pod orders-api-abc123 -n production --containers
kubectl describe pod orders-api-abc123 -n production
```

`kubectl top` có thể không phản ánh peak ngắn trong lúc restore. Với benchmark, nên thu thập Prometheus/cAdvisor time series hoặc đọc cgroup định kỳ trong container. `kubectl describe pod` giúp kiểm tra `OOMKilled`, restart count và events, nhưng không cung cấp toàn bộ lịch sử memory.

Một số metric cAdvisor/Prometheus hữu ích:

- `container_memory_usage_bytes`: memory usage theo cAdvisor.
- `container_memory_working_set_bytes`: working set.
- `container_memory_rss`: RSS theo container metrics.
- `container_cpu_usage_seconds_total`: CPU time tích lũy.
- `container_cpu_cfs_throttled_seconds_total` và `container_cpu_cfs_throttled_periods_total`: throttling với CFS quota khi được expose.

Tên và tính sẵn có của metric phụ thuộc phiên bản Kubernetes, kubelet, cAdvisor và cấu hình Prometheus. Xác nhận metric trong môi trường đang chạy trước khi viết dashboard hoặc alert.

## 6. Đo CPU usage và CPU throttling

CPU cần được đo dưới dạng thời gian CPU tích lũy và tốc độ sử dụng trong một khoảng thời gian. Một snapshot phần trăm CPU đơn lẻ không đủ để so sánh.

### 6.1. CPU time của process

Trên Linux, `/proc/<pid>/stat` chứa user CPU time và system CPU time dưới dạng tick. Công cụ như `pidstat` có thể hiển thị tỷ lệ CPU theo chu kỳ:

```bash
pidstat -p <pid> 1
```

Với process Java, `top -H` hoặc `pidstat -t` giúp xem thread nào đang tiêu thụ CPU. Tuy nhiên, PID có thể khác sau restore hoặc container restart; cần gắn số đo với Pod UID/container ID và timestamp.

### 6.2. CPU time của cgroup v2

`cpu.stat` thường có:

- `usage_usec`: tổng CPU time của cgroup tính bằng microsecond.
- `user_usec` và `system_usec`: thời gian user/system nếu kernel cung cấp.
- `nr_periods`, `nr_throttled`, `throttled_usec`: thống kê quota/throttling nếu có.

Để tính CPU cores trung bình trong khoảng đo:

\[
\text{CPU cores} = \frac{\Delta\text{usage\_usec}}{\Delta t_{usec}}
\]

Ví dụ, cgroup dùng 2.000.000 microsecond CPU trong khoảng 1.000.000 microsecond wall-clock tương đương trung bình 2 CPU cores. Nếu muốn biểu diễn phần trăm của một core, nhân kết quả với 100. Nếu muốn phần trăm quota, chia cho quota cores được cấp rồi nhân 100.

`cpu.max` có dạng `quota period` (microsecond) hoặc `max period`. Ví dụ `200000 100000` cho quota tương đương 2 CPU cores trong mỗi period. Nếu quota là `max`, cgroup không có quota cứng ở cấp đó, nhưng vẫn có thể chịu giới hạn CPU của node hoặc cấp cha.

### 6.3. Throttling

Một container có thể cần nhiều CPU trong lúc restore nhưng bị giới hạn bởi CPU limit. Khi đó thời gian restore tăng dù code không thay đổi. Hãy ghi cả `usage_usec`, `nr_throttled`, `throttled_usec` và CPU quota.

CPU throttling không giống CPU utilization thấp. Một container có thể muốn dùng nhiều CPU nhưng bị throttled; biểu đồ usage có thể bị chặn ở quota trong khi latency tăng. Nếu chỉ nhìn phần trăm CPU, dễ kết luận sai rằng restore không dùng hết CPU hoặc workload đã tối ưu.

### 6.4. Phân biệt CPU restore với CPU sau khi Ready

Ghi CPU theo các phase riêng:

1. Container start và đọc checkpoint artifact.
2. JVM restore.
3. `afterRestore` và reconnect.
4. Warm-up sau restore nếu có.
5. Request đầu tiên.
6. Steady-state workload.

Tổng CPU time của cả Pod không cho biết phase nào tiêu tốn nhiều. Dùng timestamp hoặc trace event để tách các đoạn. Với cold start, ghi cùng phase tương ứng như JVM startup, application initialization, warm-up và first request.

## 7. Đo dung lượng checkpoint trên storage

Checkpoint có thể là thư mục gồm nhiều file. Cần phân biệt ba loại dung lượng:

1. **Logical/apparent size:** tổng byte theo kích thước file mà ứng dụng nhìn thấy.
2. **Allocated size:** số block filesystem thực sự cấp phát; có thể khác logical size do sparse files, compression hoặc block size.
3. **Archive/object size:** số byte sau khi đóng gói, nén hoặc upload.

Trên Linux:

```bash
# Logical size (byte) của cây thư mục
du --apparent-size -B1 -s /var/lib/app/checkpoint

# Dung lượng block filesystem cấp phát
du -B1 -s /var/lib/app/checkpoint

# Kích thước từng file
find /var/lib/app/checkpoint -type f -printf '%s %p\n' | sort -nr
```

`du --apparent-size` phù hợp để biết tổng logical file size. `du` mặc định đo block được cấp phát. Với sparse file, hai con số có thể chênh lệch đáng kể. Nếu dùng filesystem có compression, deduplication hoặc reflink, dung lượng vật lý của storage backend còn có thể khác.

Sau khi tạo archive:

```bash
stat -c '%n %s bytes' checkpoint.tar.zst
```

Có thể tính compression ratio:

\[
\text{Compression ratio} = \frac{\text{archive size}}{\text{apparent payload size}}
\]

Ví dụ, payload 8 GiB được nén thành archive 3 GiB thì ratio là 0,375 (37,5%). Hãy ghi cả payload size và archive size; chỉ ghi archive size sẽ che mất chi phí storage nếu checkpoint được lưu ở dạng thư mục không nén.

### 7.1. Đo tốc độ ghi và đọc checkpoint

Thời gian tạo checkpoint và thời gian restore có thể bị chi phối bởi storage. Đo riêng:

- Thời gian runtime ghi checkpoint files.
- Thời gian tạo manifest và tính checksum.
- Thời gian nén archive.
- Thời gian upload hoặc copy tới storage.
- Thời gian download/copy về Pod mới.
- Thời gian giải nén hoặc chuẩn bị working copy.
- Thời gian JVM đọc và restore checkpoint.

Không gộp tất cả thành một con số “restore duration” nếu mục tiêu là tìm bottleneck. Nếu checkpoint được mount trực tiếp từ PVC hoặc network filesystem, đo throughput và latency đọc trên đúng storage class.

### 7.2. Storage của container và ephemeral storage

Kubernetes có thể tính ephemeral storage cho writable layer, logs và `emptyDir`. Checkpoint được ghi vào filesystem container có thể làm tăng ephemeral storage usage và vượt quota node/container. Nếu dùng PVC, dung lượng được tính theo storage backend và quota riêng.

Theo dõi:

- Kích thước checkpoint directory.
- Dung lượng archive trong registry/object storage.
- Dung lượng working copy trên `emptyDir` hoặc writable layer.
- Dung lượng log và file tạm trong lúc verify/restore.
- Số checkpoint cũ còn được giữ và retention policy.

Nếu mỗi Pod scale-out tạo một bản sao checkpoint lớn trên node local, tổng storage có thể tăng theo số replica. Dùng artifact bất biến và cache phù hợp trên node nếu nền tảng cho phép, nhưng phải kiểm soát quyền ghi và tính toàn vẹn.

## 8. Tính chi phí lưu trữ khi có nhiều replica

Một checkpoint dùng chung có thể được lưu một lần trong object storage, nhưng mỗi Pod vẫn có thể cần working copy riêng. Để ước lượng, cần tách:

- Dung lượng artifact gốc.
- Số bản sao tại node hoặc volume.
- Dung lượng working directory riêng từng Pod.
- Archive và bản giải nén đồng thời trong lúc rollout.
- Các phiên bản checkpoint được giữ theo retention.

Ví dụ, artifact 4 GiB, rollout có 6 Pod mới đồng thời và mỗi Pod cần working copy 4 GiB có thể cần tới 24 GiB working storage, chưa tính artifact gốc, archive và headroom. Đây chỉ là phép ước lượng tuyến tính; reflink, shared volume hoặc node-local cache có thể làm chi phí thực khác đi.

Khi nhiều version được giữ, ước lượng dung lượng lưu trữ:

\[
S_{total} = \sum_{v=1}^{N} S_{artifact,v} + S_{working} + S_{temporary}
\]

Trong đó `N` là số version checkpoint được giữ. Nếu object storage có versioning hoặc replication, cần tính thêm chi phí từ policy của storage provider.

## 9. So sánh cold start và CRaC restore

Một benchmark công bằng cần dùng cùng ứng dụng, cùng JDK/CRaC build, cùng node class, cùng CPU/memory limits, cùng dữ liệu và cùng workload. Nếu restore dùng checkpoint đã warm-up còn cold start không warm-up, phép đo đang so sánh hai quy trình khác nhau. Có thể đo hai kịch bản riêng:

- **Cold start baseline:** JVM khởi động từ đầu, application initialization và warm-up theo cấu hình baseline.
- **CRaC restore:** JVM phục hồi từ checkpoint đã được tạo theo quy trình xác định, chạy `afterRestore` và đạt readiness.

Nếu muốn đo riêng lợi ích của snapshot, ghi rõ checkpoint đã bao gồm initialization nào, warm-up nào và resource nào được refresh sau restore.

### 9.1. Các mốc thời gian cần ghi

| Mốc | Ý nghĩa |
|---|---|
| `t0` | Container/Pod bắt đầu |
| `t1` | Entrypoint bắt đầu verify/chuẩn bị checkpoint |
| `t2` | JVM bắt đầu cold start hoặc restore |
| `t3` | JVM restore/start hoàn tất |
| `t4` | `afterRestore` và dependency refresh hoàn tất |
| `t5` | Readiness thành công |
| `t6` | Request đầu tiên hoàn tất |
| `t7` | Steady-state workload đạt mức ổn định |

Từ các mốc này, có thể tính:

- Restore duration: `t3 - t2`.
- Post-restore resource duration: `t4 - t3`.
- Restore-to-ready: `t5 - t0` hoặc `t5 - t2`, tùy câu hỏi đo.
- First-request latency: thời gian xử lý request đầu tiên sau `t5`.
- End-to-first-response: `t6 - t0`.

Định nghĩa mốc phải nhất quán giữa cold start và restore. Nếu cold start có application initialization còn restore bắt đầu ở một điểm khác trong tiến trình, hãy báo cáo cả tổng thời gian tới Ready và từng phase riêng.

### 9.2. Đo nhiều lần và báo cáo phân vị

Một lần chạy không đủ để kết luận. Thực hiện nhiều lần lặp trong điều kiện tương đương, ghi lại node, kernel, runtime, CPU quota, memory limit và storage class. Báo cáo:

- Median (p50) để mô tả lần chạy điển hình.
- p90/p95 hoặc p99 để thể hiện tail latency.
- Min/max để nhận biết outlier, nhưng không dùng chúng làm kết luận chính.
- Số lần thất bại, OOM, timeout hoặc restore error.
- RSS/memory peak và CPU time trong cùng phase.
- Payload/archive size và thời gian truyền tải.

Nếu dữ liệu có outlier do image pull, node scheduling hoặc cache storage, giữ lại và phân loại thay vì âm thầm loại bỏ. Có thể báo riêng thời gian từ container start và thời gian JVM restore để phân biệt chi phí Kubernetes với chi phí CRaC.

## 10. Thu thập snapshot Linux theo một PID

Một script shell đơn giản có thể ghi RSS và cgroup memory hiện tại trong lúc benchmark:

```bash
#!/usr/bin/env bash
set -euo pipefail

PID="$1"
OUT="${2:-memory-snapshot.txt}"

{
  date --iso-8601=ns
  echo "pid=$PID"
  grep -E '^(Name|VmRSS|VmHWM|VmSize):' "/proc/$PID/status"
  if [ -r "/proc/$PID/smaps_rollup" ]; then
    grep -E '^(Rss|Pss|Private_Clean|Private_Dirty|Anonymous):' \
      "/proc/$PID/smaps_rollup"
  fi
  if [ -r /sys/fs/cgroup/memory.current ]; then
    echo "cgroup_memory_current=$(cat /sys/fs/cgroup/memory.current)"
    echo "cgroup_memory_max=$(cat /sys/fs/cgroup/memory.max)"
  fi
} >> "$OUT"
```

Script giả định cgroup v2 mount ở `/sys/fs/cgroup`; với cgroup v1 hoặc nested cgroup, cần tìm đúng đường dẫn từ `/proc/self/cgroup`. `PID` phải là PID trong PID namespace nhìn thấy từ nơi chạy script. Nếu restore tạo PID khác, hãy lấy PID mới từ process supervisor hoặc container namespace.

Để quan sát peak, chạy sampling định kỳ trong suốt giai đoạn restore. Chụp một lần sau khi Pod Ready có thể bỏ lỡ peak xảy ra trong lúc JVM map image hoặc giải nén artifact.

## 11. Thu thập số liệu bằng Prometheus/cAdvisor

Trong Kubernetes, time series giúp so sánh nhiều Pod và phát hiện peak ngắn. Một PromQL minh họa CPU cores trung bình trong 1 phút:

```promql
rate(container_cpu_usage_seconds_total{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}[1m])
```

Working set:

```promql
container_memory_working_set_bytes{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}
```

CPU throttling ratio theo số period bị throttle (nếu metric có sẵn):

```promql
rate(container_cpu_cfs_throttled_periods_total{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}[5m])
/
clamp_min(rate(container_cpu_cfs_periods_total{
  namespace="production",
  pod=~"orders-api-.*",
  container="app"
}[5m]), 1)
```

Các query cần điều chỉnh theo labels thực tế và metric được expose. Một số môi trường dùng metric tên khác hoặc không expose CFS throttling. Throttling ratio ở trên là tỷ lệ period bị throttle, không phải phần trăm CPU time bị mất.

Khi dashboard có nhiều Pod, gắn nhãn release/checkpoint version để so sánh cùng phiên bản. Pod name thay đổi trong rollout; hãy dùng label deployment/version để nhóm, và dùng Pod UID trong log/trace khi cần điều tra một replica cụ thể.

## 12. Thiết kế bảng kết quả benchmark

Nên lưu kết quả theo từng lần chạy và từng phase. Ví dụ schema CSV:

```text
run_id,mode,phase,pod_uid,jdk_version,crac_version,cpu_limit,memory_limit,rss_bytes,pss_bytes,cgroup_memory_bytes,cgroup_memory_peak_bytes,cpu_time_usec,throttled_usec,checkpoint_apparent_bytes,checkpoint_allocated_bytes,archive_bytes,duration_ms,result
run-001,cold,startup,...
run-002,crac,restore,...
```

Không điền số liệu ước lượng vào bảng. Ghi `NA` nếu một metric không có sẵn và thêm lý do, ví dụ kernel không expose `memory.peak`. Lưu metadata môi trường cùng kết quả để lần benchmark sau có thể tái lập.

## 13. Những yếu tố làm sai lệch phép đo

### Heap size và GC khác nhau

Khác `-Xms`, `-Xmx`, collector hoặc GC ergonomics có thể làm RSS và thời gian restore khác nhau. Giữ cấu hình giống nhau hoặc ghi rõ khác biệt.

### NMT/profiler chỉ bật ở một nhánh

NMT, JFR và profiler có overhead. Nếu cần dùng để phân tích, bật giống nhau ở cả hai nhánh hoặc tách lần chẩn đoán khỏi benchmark hiệu năng.

### File cache của node

Restore lần đầu có thể đọc checkpoint từ storage lạnh; lần sau dữ liệu đã nằm trong page cache. Ghi rõ cache state và thử cả cold-cache lẫn warm-cache nếu đó là hai tình huống production có thể gặp.

### CPU throttling và noisy neighbor

Pod khác trên cùng node có thể tranh CPU hoặc storage. Ghi node, quota và throttling. Chạy đủ lần lặp để thấy độ biến động.

### RSS và cgroup memory không cùng phạm vi

RSS chỉ một process; cgroup tính cả nhóm process và một số loại memory khác. Đừng coi chênh lệch là lỗi đo ngay lập tức.

### Sparse files và compression

Logical size, allocated size và archive size khác nhau. Báo cáo cả ba nếu storage cost là mục tiêu.

### Checkpoint không cùng mức warm-up

Một checkpoint tạo sau workload warm-up không thể so sánh công bằng với cold start chưa chạy warm-up nếu không ghi rõ mục tiêu benchmark.

### Đo thời gian không cùng điểm bắt đầu

Pod start, container start, JVM start, restore start và readiness là các mốc khác nhau. Chọn một định nghĩa và dùng giống nhau.

## 14. Quy trình benchmark đề xuất

Một quy trình thực nghiệm có thể thực hiện như sau:

1. Chọn một phiên bản ứng dụng, JDK/CRaC runtime, kernel, container runtime và storage class cố định.
2. Cấu hình cùng CPU request/limit và memory request/limit cho cold start và restore.
3. Xác định workload, dữ liệu, số request và tiêu chí readiness.
4. Chạy cold start nhiều lần; thu thập RSS/PSS, cgroup memory, CPU time/throttling, thời gian startup và first request.
5. Tạo checkpoint theo cùng quy trình initialization/warm-up đã mô tả; ghi thời gian checkpoint và inventory file.
6. Đo apparent size, allocated size, archive size, checksum duration và transfer duration.
7. Chạy restore nhiều lần trên cùng loại node; thu thập các metric cùng mốc như cold start.
8. Ghi riêng peak trong lúc restore, sau Ready và steady state.
9. Kiểm tra `memory.events`, OOM/restart, CPU throttling và storage pressure.
10. So sánh p50/p95/p99, peak memory, CPU time, checkpoint storage và thời gian tới Ready.
11. Lặp lại với storage lạnh/nóng hoặc mức concurrency khác nếu phù hợp production.
12. Lưu raw samples và metadata, không chỉ lưu số trung bình cuối cùng.

Nếu benchmark trong Kubernetes, nên đo cả Pod-level timeline và process-level metrics. Pod có thể mất thời gian scheduling hoặc image pull trước khi JVM bắt đầu; CRaC chỉ tác động một phần của tổng thời gian đó.

## 15. Đọc kết quả và xác định bottleneck

Một số mẫu diễn giải:

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| Restore nhanh nhưng RSS/cgroup peak tăng mạnh | Heap snapshot, native memory, thread stack, page mapping hoặc warm-up footprint |
| RSS ổn định nhưng cgroup memory tăng | File cache, native/kernel memory, process phụ trợ hoặc working copy |
| Heap used thấp nhưng RSS cao | Metaspace, code cache, direct/native buffers, stacks hoặc mapped pages |
| CPU usage chạm quota và throttling tăng | CPU limit quá thấp cho restore burst hoặc nhiều Pod restore đồng thời |
| CPU time thấp nhưng restore duration cao | I/O wait, storage latency, lock contention hoặc dependency reconnect |
| Checkpoint apparent size lớn nhưng allocated size nhỏ | Sparse files hoặc filesystem behavior |
| Archive nhỏ nhưng tạo/giải nén chậm | Compression CPU cost hoặc storage throughput |
| Pod Ready nhanh nhưng request đầu chậm | Lazy initialization, JIT, cache miss hoặc dependency path chưa warm |
| Một Pod restore nhanh, scale-out chậm khi nhiều Pod | Storage contention, connection storm, CPU/node capacity hoặc image pull |

Không kết luận chỉ từ một metric. Ví dụ, CPU usage thấp không tự động có nghĩa restore bị chặn bởi I/O; hãy đối chiếu block I/O, disk latency, thread states và timeline. RSS cao không nhất thiết gây OOM nếu cgroup headroom còn đủ, nhưng peak cgroup gần limit vẫn là rủi ro cần đo trong điều kiện tải cao.

## 16. Bảo mật và quyền truy cập khi đo

Checkpoint có thể chứa dữ liệu heap, token, session, credential và dữ liệu người dùng. File checkpoint, manifest và log chẩn đoán phải được bảo vệ như artifact nhạy cảm.

- Không đưa nội dung memory dump hoặc raw heap data vào log benchmark.
- Hạn chế quyền đọc `/proc/<pid>/mem`, `smaps` và checkpoint directory.
- Không lưu token hoặc secret trong CSV/metrics labels.
- Giữ checkpoint và archive trong storage có ACL/encryption phù hợp.
- Xóa artifact thử nghiệm theo retention policy.
- Khi dùng `strace`, NMT detail hoặc JFR, kiểm soát quyền truy cập file output.

## 17. Checklist thu thập số liệu

- [ ] RSS và VmHWM được ghi theo PID và timestamp.
- [ ] PSS/USS được thu thập nếu kernel cho phép.
- [ ] Java heap used/committed được ghi qua JMX hoặc JFR.
- [ ] NMT được bật nhất quán nếu cần phân tích native JVM memory.
- [ ] cgroup memory current/peak/max và events được lưu.
- [ ] Container working set được thu thập qua metrics pipeline nếu có.
- [ ] CPU time và quota được ghi cho từng phase.
- [ ] CPU throttling được đo và phân biệt với utilization.
- [ ] Checkpoint logical size, allocated size và archive size được ghi riêng.
- [ ] Transfer, checksum, compression và extraction duration được tách riêng.
- [ ] Cold start và restore dùng cùng resource limits và workload.
- [ ] Timeline từ Pod start tới Ready và first response được ghi.
- [ ] Có nhiều lần lặp và báo cáo median/p95/p99.
- [ ] OOM, restart, memory events và storage pressure được kiểm tra.
- [ ] Raw samples và metadata môi trường được lưu để tái lập.

## 18. Tài liệu tham khảo

- [Linux proc PID status](https://man7.org/linux/man-pages/man5/proc_pid_status.5.html): RSS, VmHWM và virtual memory của tiến trình.
- [Linux proc PID smaps](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html): RSS, PSS, private/shared memory và mapping details.
- [Linux cgroup v2 documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html): memory, CPU quota, usage và event counters.
- [OpenJDK Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): cách bật và đọc NMT.
- [Kubernetes Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): CPU/memory requests, limits và container resource behavior.
- [Kubernetes Resource Metrics Pipeline](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/): Metrics Server và `kubectl top`.
- [Prometheus cAdvisor metrics](https://github.com/google/cadvisor): container CPU, memory và throttling metrics.

Đánh giá CRaC cần nhìn đồng thời vào footprint resident, memory limit của container, CPU time/throttling và dung lượng checkpoint trên storage. RSS/PSS giải thích bộ nhớ của JVM; cgroup cho biết áp lực memory mà container thực sự chịu; CPU counters cho thấy chi phí và throttling; filesystem/archive metrics cho biết chi phí lưu trữ và truyền tải. So sánh cold start với restore chỉ có ý nghĩa khi cùng runtime, workload, quota, storage và mốc thời gian, đồng thời báo cáo cả peak và phân vị thay vì chỉ một snapshot hoặc giá trị trung bình.
