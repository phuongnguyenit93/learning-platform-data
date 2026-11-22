# Thiết lập CPU, memory limit và heap phù hợp trong container

Khi chạy Java 21 trong Docker hoặc Kubernetes, cần cấu hình CPU và memory limit sao cho JVM hiểu đúng tài nguyên container được cấp, đồng thời giữ đủ bộ nhớ cho heap và các vùng native. Heap không phải toàn bộ memory của process: metaspace, code cache, thread stack, direct buffer, thư viện native và hoạt động của garbage collector cũng tiêu thụ memory nằm trong giới hạn container.

Một cấu hình tốt bắt đầu từ resource limit của container, sau đó đo workload thực tế để chọn heap, số processor JVM nhìn thấy và kích thước thread pool. Không có một tỷ lệ heap hoặc số CPU cố định phù hợp cho mọi ứng dụng. Hãy kiểm tra hành vi của JVM trong đúng runtime Java 21, dưới cùng giới hạn tài nguyên mà production sử dụng.

## 1. Phân biệt CPU request, CPU limit, memory request và memory limit

Trong Kubernetes, `requests` và `limits` có vai trò khác nhau:

| Tài nguyên | Request | Limit |
|---|---|---|
| CPU | Lượng CPU dùng để lập lịch Pod và tính mức chia sẻ CPU khi tranh chấp | Giới hạn CPU qua quota; container có thể bị throttling khi vượt phần CPU được phép trong chu kỳ |
| Memory | Lượng memory dùng để lập lịch Pod và tính mức ưu tiên khi node thiếu memory | Giới hạn memory cgroup; vượt giới hạn có thể khiến process bị kernel OOM killer kết thúc |

Ví dụ:

- `requests.cpu: "500m"` tương đương nửa CPU theo đơn vị Kubernetes.
- `limits.cpu: "2"` cho phép container dùng tối đa tương đương hai CPU theo quota.
- `requests.memory: "512Mi"` dùng cho lập lịch.
- `limits.memory: "1Gi"` đặt giới hạn memory của container.

CPU limit thường tạo ra throttling thay vì kết thúc process. Memory limit là giới hạn cứng hơn: khi memory bị tính vào cgroup vượt mức cho phép, kernel có thể kill process trong container.

Không nhầm CPU request với số CPU JVM nhìn thấy. HotSpot thường dựa vào giới hạn CPU thực tế của container (quota/cpuset) để xác định processor count; request chủ yếu ảnh hưởng scheduler và CPU shares. Nếu request là 500m nhưng limit là 2 CPU, JVM có thể nhìn thấy giới hạn gần 2 CPU chứ không phải 0.5 CPU.

## 2. Docker và cgroup giới hạn tài nguyên như thế nào?

Docker và Kubernetes trên Linux sử dụng cgroups để giới hạn và thống kê tài nguyên. JVM cần đọc được cgroup để tính toán ergonomics phù hợp với container.

Ví dụ chạy container với giới hạn:

```bash
docker run --rm \
  --memory=1g \
  --cpus=2 \
  my-java-app:21
```

Trong ví dụ này, container có memory limit 1 GiB và CPU quota tương đương hai CPU. Docker cũng hỗ trợ cấu hình CPU affinity bằng `--cpuset-cpus` nếu cần giới hạn container chạy trên một tập CPU cụ thể.

Trên Linux, thông tin cgroup thường có các file như:

| cgroup v2 | cgroup v1 thường gặp | Ý nghĩa |
|---|---|---|
| `memory.max` | `memory.limit_in_bytes` | Giới hạn memory |
| `memory.current` | `memory.usage_in_bytes` | Memory đang được tính cho cgroup |
| `cpu.max` | `cpu.cfs_quota_us` và `cpu.cfs_period_us` | CPU quota và period |
| `cpu.stat` | `cpu.stat` | Thống kê sử dụng/throttling CPU |
| `cpuset.cpus.effective` | `cpuset.cpus` | Tập CPU được phép chạy |

Đường dẫn thực tế phụ thuộc cách runtime mount cgroup và namespace của container. Không nên giả định mọi image đều nhìn thấy cùng một cây thư mục cgroup.

Lưu ý rằng `memory.current`/`memory.usage_in_bytes` là số liệu của cgroup, không chỉ riêng Java heap hay RSS của một process. Tùy cấu hình, memory được tính còn có thể bao gồm process khác trong cùng cgroup và page cache. Vì vậy, khi so sánh số liệu JVM với container metrics, hãy xác định rõ phạm vi của từng chỉ số.

## 3. Bật và xác minh container awareness của HotSpot

HotSpot trên Linux có hỗ trợ nhận biết giới hạn container. Tùy chọn `-XX:+UseContainerSupport` được bật mặc định trong các cấu hình HotSpot Linux hiện hành, bao gồm Java 21. Khi hoạt động, JVM có thể dùng giới hạn CPU và memory từ cgroup cho các quyết định ergonomics.

Có thể chỉ định tường minh khi cần làm rõ cấu hình:

```bash
java -XX:+UseContainerSupport -jar application.jar
```

Nếu tùy chọn này bị tắt bằng `-XX:-UseContainerSupport`, JVM có thể dựa trên tài nguyên host thay vì giới hạn container. Điều đó có thể khiến heap hoặc số thread JVM tính toán lớn hơn mức container thực sự được cấp.

Để xem thông tin hệ thống và container mà JVM nhận diện:

```bash
java -XshowSettings:system -version
```

Để kiểm tra khi ứng dụng đang chạy, có thể xem thông tin JVM:

```bash
jcmd <pid> VM.info
jcmd <pid> VM.flags
```

Khi cần chẩn đoán chi tiết quá trình phát hiện container, có thể bật unified logging trong một lần chạy điều tra:

```bash
java -Xlog:os+container=trace -jar application.jar
```

Mức trace tạo nhiều thông tin, vì vậy nên dùng trong thời gian chẩn đoán và giảm log sau khi đã xác nhận JVM nhận đúng giới hạn.

## 4. CPU limit ảnh hưởng đến JVM như thế nào?

CPU limit thường được thực thi bằng quota trong một khoảng thời gian. Nếu container dùng hết quota trước khi chu kỳ mới bắt đầu, các thread có thể bị throttled dù host vẫn còn CPU rảnh.

Điều này ảnh hưởng đến:

- Thread xử lý request và các executor của ứng dụng.
- Các thread GC chạy song song hoặc concurrent.
- JIT compiler và các tác vụ runtime.
- ForkJoinPool và những framework lấy số processor để chọn parallelism.
- Độ trễ khi tải tăng hoặc có nhiều thread cạnh tranh CPU.

Khi CPU quota quá thấp, pause GC có thể dài hơn do collector có ít CPU để hoàn thành pha song song. Tác vụ concurrent của GC cũng có thể cạnh tranh với business thread, khiến throughput và latency thay đổi.

CPU limit không phải là cấu hình số thread của ứng dụng. Một container có hai CPU vẫn có thể tạo hàng trăm thread; số thread cần được kiểm soát theo loại workload, blocking behavior và memory headroom.

## 5. Kiểm soát số processor JVM sử dụng

`Runtime.getRuntime().availableProcessors()` trả về số processor mà JVM đang sử dụng cho một số quyết định runtime. Đây là số hữu ích để kiểm tra JVM có nhận giới hạn container hay không:

```java
public class RuntimeResources {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        System.out.println(
                "Available processors: "
                        + runtime.availableProcessors());

        System.out.println(
                "Maximum heap (MiB): "
                        + runtime.maxMemory() / (1024 * 1024));
    }
}
```

Nếu JVM nhìn thấy số CPU lớn hơn mong đợi, hãy kiểm tra cgroup, CPU quota, cpuset và trạng thái `UseContainerSupport`.

### 5.1. Dùng ActiveProcessorCount khi cần override

`-XX:ActiveProcessorCount=N` cho phép chỉ định số processor mà JVM dùng cho ergonomics, kể cả khi JVM đang chạy trong container:

```bash
java -XX:ActiveProcessorCount=2 -jar application.jar
```

Tùy chọn này ảnh hưởng đến các quyết định như số worker của GC và parallelism mà một số API runtime báo cáo. Nó không tạo thêm CPU, không thay đổi quota cgroup và không ngăn container bị throttled.

Chỉ override khi có lý do đo được, chẳng hạn JVM nhận số CPU không phù hợp với quota thực tế hoặc ứng dụng cần cố định parallelism. Giá trị nên nhất quán với CPU limit và cách phân bổ tải. Không đặt số lớn hơn quota chỉ để tăng thread; nhiều thread hơn không làm tăng năng lực CPU khi container đã bị giới hạn.

### 5.2. CPU quota nhỏ hơn một core

Ví dụ Kubernetes đặt CPU limit `500m`. Đây là quota tương đương nửa CPU, nhưng `availableProcessors()` là số nguyên. JVM có thể biểu diễn năng lực CPU theo số processor nguyên dựa trên quy tắc ergonomics của phiên bản runtime.

Vì vậy, cần kiểm tra giá trị thực tế và hành vi throttling thay vì suy luận rằng `500m` chắc chắn làm `availableProcessors()` trả về 0.5. Nếu cần điều chỉnh parallelism cho phù hợp với quota, cân nhắc `-XX:ActiveProcessorCount=1`, sau đó đo throughput và latency dưới tải đại diện.

## 6. Heap không phải toàn bộ memory của container

Memory limit của container bao phủ nhiều loại bộ nhớ ngoài Java heap. Một process Java có thể dùng:

- **Java heap:** object được quản lý bởi garbage collector.
- **Metaspace:** metadata của class.
- **Code cache:** mã máy do JIT compiler sinh.
- **Thread stacks:** stack native của platform thread. Virtual thread không giữ một native stack riêng cho toàn bộ vòng đời; stack của chúng được lưu dưới dạng dữ liệu trên heap, còn carrier platform thread vẫn có native stack.
- **Direct buffers:** vùng memory ngoài heap, ví dụ NIO.
- **Native memory:** thư viện JNI, runtime, allocator và các thành phần native khác.
- **GC internal structures:** dữ liệu và cấu trúc phục vụ collector.
- **Agent và profiler:** bộ nhớ do công cụ giám sát hoặc instrumentation sử dụng.

Do đó, đặt `-Xmx` bằng memory limit của container là cấu hình nguy hiểm. Heap có thể chưa chạm Xmx nhưng tổng process memory vẫn vượt giới hạn cgroup, dẫn đến OOM kill.

Có thể hình dung ngân sách:

`Container memory limit >= heap + non-heap/native + safety headroom`

Trong đó non-heap/native phải được đo dưới workload gần production. Headroom dành cho dao động allocation, thread tăng, tải đột biến, JIT, GC và các thành phần native.

## 7. Chọn heap bằng Xms và Xmx

Hai tùy chọn phổ biến:

- `-Xms`: kích thước heap ban đầu.
- `-Xmx`: kích thước heap tối đa.

Ví dụ:

```bash
java -Xms256m -Xmx640m -jar application.jar
```

Trong cấu hình này, heap ban đầu là 256 MiB và không tăng vượt 640 MiB. Các giá trị trên chỉ minh họa; cần chọn dựa trên live set, allocation rate, GC behavior và memory limit.

Không nên đặt `-Xmx` bằng toàn bộ memory limit. Ví dụ container có limit 1 GiB nhưng heap max cũng 1 GiB thì JVM không còn đủ khoảng trống cho metaspace, thread stack, direct buffer và native memory.

Đặt `-Xms` bằng `-Xmx` có thể giảm việc thay đổi kích thước heap trong runtime, nhưng cũng có thể khiến JVM commit nhiều heap sớm hơn. Chỉ dùng khi đã hiểu tác động tới memory footprint và thời gian khởi động. Với container có memory limit chặt, cần kiểm tra mức memory thực tế sau startup.

## 8. Dùng MaxRAMPercentage để đặt heap theo memory container

Thay vì cố định `-Xmx`, HotSpot hỗ trợ các tùy chọn percentage:

- `-XX:MaxRAMPercentage`: tỷ lệ memory tối đa JVM dùng để tính maximum heap.
- `-XX:InitialRAMPercentage`: tỷ lệ dùng để tính initial heap khi không chỉ định `-Xms`.
- `-XX:MinRAMPercentage`: tỷ lệ tối đa dùng để tính heap trong các cấu hình memory nhỏ theo quy tắc ergonomics của HotSpot; đây không phải kích thước heap tối thiểu.

Ví dụ:

```bash
java \
  -XX:MaxRAMPercentage=60.0 \
  -jar application.jar
```

Với container memory limit 1 GiB, 60% tương đương khoảng 614 MiB maximum heap. Phần còn lại khoảng 410 MiB dành cho các vùng memory khác và headroom. Đây chỉ là ví dụ tính toán; tỷ lệ phù hợp phải dựa trên đo đạc.

Nếu chỉ định `-Xmx`, giá trị heap max tuyệt đối đó sẽ quyết định maximum heap; không nên kỳ vọng `MaxRAMPercentage` tiếp tục giới hạn thấp hơn `-Xmx`. Hãy chọn một chiến lược rõ ràng:

- Dùng `-Xmx` khi cần giới hạn heap tuyệt đối, có thể dự đoán.
- Dùng `MaxRAMPercentage` khi muốn heap tự điều chỉnh theo giới hạn memory container.
- Dùng `-Xms` hoặc `InitialRAMPercentage` để kiểm soát initial heap sau khi đã cân nhắc startup và memory commitment.

Không sao chép một tỷ lệ từ ứng dụng khác. Ứng dụng có nhiều thread, direct buffer, JNI hoặc agent có thể cần tỷ lệ heap thấp hơn ứng dụng thuần Java.

## 9. Ví dụ tính ngân sách memory cho container 1 GiB

Giả sử container có memory limit 1 GiB. Một cách bắt đầu để benchmark là dành khoảng 60% cho heap max:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Maximum Java heap | 614 MiB |
| Metaspace, code cache, GC native | 100 MiB |
| Thread stacks | 80 MiB |
| Direct buffers và native libraries | 100 MiB |
| Headroom cho biến động và overhead chưa dự đoán | 130 MiB |
| **Tổng** | **1.024 MiB** |

Đây là ví dụ phân bổ để minh họa cách suy nghĩ, không phải định mức JVM. Memory non-heap thay đổi theo số class được load, số platform thread, kích thước stack, direct buffer, agent và thư viện native.

Để chọn con số thực tế:

1. Chạy workload đại diện và đo RSS/container memory.
2. Theo dõi heap used, committed, max và mức heap sau GC.
3. Đo số thread và cấu hình stack.
4. Theo dõi direct buffer và native memory nếu ứng dụng sử dụng.
5. Tăng tải tới mức peak dự kiến và quan sát headroom.
6. Chọn Xmx hoặc MaxRAMPercentage sao cho vẫn còn khoảng an toàn dưới memory limit.

## 10. Ví dụ Docker cho Java 21

Một cấu hình đơn giản:

```bash
docker run --rm \
  --memory=1g \
  --cpus=2 \
  -e JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -XX:ActiveProcessorCount=2" \
  my-java-app:21
```

`JAVA_TOOL_OPTIONS` được JVM đọc khi khởi tạo, nên có thể dùng để truyền JVM flags khi entrypoint của image không hỗ trợ biến `JAVA_OPTS` theo cách mong muốn.

Trong ví dụ, JVM được cấu hình heap max theo 60% memory container và dùng hai processor cho ergonomics. Trên Linux với container support đang bật, JVM cũng có thể tự nhận giới hạn CPU; `ActiveProcessorCount` được đặt rõ để cố định số processor mà JVM sử dụng cho runtime ergonomics.

Trước khi áp dụng, xác minh rằng image thực sự chạy Java 21 và không có biến môi trường hoặc script khác thêm `-Xmx` hay override flags.

## 11. Ví dụ Kubernetes Deployment

Ví dụ cấu hình một container Java 21 với memory limit 1 GiB và CPU limit 2:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: java-api
  template:
    metadata:
      labels:
        app: java-api
    spec:
      containers:
        - name: app
          image: example/java-api:21
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=60.0 -XX:ActiveProcessorCount=2"
          resources:
            requests:
              cpu: "1"
              memory: "768Mi"
            limits:
              cpu: "2"
              memory: "1Gi"
```

Trong ví dụ:

- Kubernetes dành tài nguyên lập lịch theo request.
- CPU limit là hai CPU theo quota.
- Memory limit là 1 GiB.
- JVM được cấu hình heap max theo tỷ lệ 60% và sử dụng hai processor trong ergonomics.

Request memory nhỏ hơn limit không làm JVM tự lấy request làm heap limit. Với HotSpot container support, memory limit là dữ liệu quan trọng để tính heap ergonomics. Hãy đảm bảo request phản ánh mức memory mà workload thường cần để scheduler đặt Pod lên node phù hợp.

Trong môi trường production, nên quản lý JVM flags qua cấu hình deployment/version control, tránh chỉnh tay trong container đang chạy khiến các replica có hành vi khác nhau.

## 12. Điều chỉnh CPU và thread pool của ứng dụng

Sau khi xác định số processor JVM nhìn thấy, cần rà soát các thread pool do ứng dụng quản lý:

- Thread pool CPU-bound nên được thiết kế quanh số CPU thực tế và benchmark.
- Thread pool I/O-bound có thể có nhiều thread hơn vì phần lớn thời gian chờ I/O, nhưng cần giới hạn queue và concurrency.
- Connection pool phải phù hợp với giới hạn database và số replica.
- Không tạo thread platform không giới hạn theo số request.
- Theo dõi queue depth, rejected task, context switching và CPU throttling.

Virtual thread trong Java 21 có thể giúp triển khai mô hình thread-per-request cho workload blocking I/O. Tuy nhiên, virtual thread không làm tăng CPU quota. Các tác vụ CPU-bound vẫn cạnh tranh trên số CPU được cấp; giới hạn concurrency cho công việc CPU-heavy vẫn cần được kiểm soát.

Không dùng `availableProcessors()` như công thức duy nhất để đặt mọi thread pool. Nó là đầu vào hữu ích, nhưng số worker tối ưu còn phụ thuộc blocking ratio, latency dependency, queueing và memory mỗi task.

## 13. GC cần được đánh giá trong giới hạn CPU và memory

G1 và Generational ZGC có đặc tính sử dụng CPU và memory khác nhau. Khi container bị giới hạn CPU, các pha GC song song hoặc concurrent có thể bị ảnh hưởng bởi quota và throttling.

Với G1:

- Số GC worker chịu ảnh hưởng bởi processor count JVM nhận diện.
- CPU quota thấp có thể làm pha evacuation kéo dài.
- Heap quá nhỏ so với allocation rate có thể khiến GC xảy ra thường xuyên.

Với Generational ZGC:

- Phần lớn công việc thu gom diễn ra concurrent, nên cần CPU headroom để GC tiến triển trong khi ứng dụng vẫn chạy.
- Heap cần đủ khoảng trống để ứng dụng tiếp tục cấp phát trong lúc GC thu gom.
- Pause thấp không có nghĩa tổng CPU hoặc memory footprint thấp.

Trên Java 21, Generational ZGC được bật bằng:

```bash
-XX:+UseZGC -XX:+ZGenerational
```

Khi benchmark collector, giữ nguyên container limit và workload. Theo dõi GC log, pause, allocation stall, throughput, CPU throttling và memory usage cùng lúc. Không đổi GC chỉ để xử lý một container thiếu memory headroom.

## 14. Giám sát memory và CPU trong container

Cần theo dõi cả JVM metrics và container metrics.

| Chỉ số | Nguồn quan sát | Mục đích |
|---|---|---|
| Heap used/committed/max | MemoryMXBean, JFR, `jcmd GC.heap_info` | Theo dõi heap |
| Process RSS/working set | Container runtime, cAdvisor, hệ điều hành | Đo memory process/container thực tế |
| Cgroup memory current/limit | cgroup files, container metrics | Xem mức sử dụng so với giới hạn |
| CPU usage | Container metrics | Đo CPU thực dùng |
| CPU throttled periods/time | cgroup `cpu.stat`, cAdvisor/Prometheus | Phát hiện CPU quota gây throttling |
| Available processors | `Runtime.availableProcessors()` | Kiểm tra CPU count JVM nhìn thấy |
| Thread count | JMX, JFR, thread dump | Phát hiện thread tăng và stack memory |
| Direct buffer usage | BufferPoolMXBean | Theo dõi memory ngoài heap của NIO |

Có thể lấy heap info từ process:

```bash
jcmd <pid> GC.heap_info
```

Để xem thống kê direct buffer trong ứng dụng:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.printf(
            "%s: count=%d, used=%d MiB, capacity=%d MiB%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed() / (1024 * 1024),
            pool.getTotalCapacity() / (1024 * 1024)
    );
}
```

Không chỉ dựa vào heap chart. Nếu heap ổn định nhưng RSS/container memory tăng, điều tra direct buffer, thread stack, metaspace, code cache và native allocations.

## 15. Phân biệt Java OutOfMemoryError và container OOM kill

Có ít nhất hai kiểu sự cố cần phân biệt:

**Java OutOfMemoryError:** JVM không thể cấp phát trong một vùng quản lý cụ thể, ví dụ `Java heap space`, `Metaspace`, `Direct buffer memory` hoặc không tạo được native thread. JVM có thể ném exception và ghi stack trace tùy trường hợp.

**Container bị OOM kill:** tổng memory bị tính vào cgroup vượt limit, kernel có thể gửi SIGKILL cho process. Ứng dụng có thể bị kết thúc mà không có cơ hội ném hoặc ghi `OutOfMemoryError`. Heap chưa chạm Xmx vẫn có thể xảy ra OOM kill nếu non-heap/native memory hoặc memory khác trong cgroup quá lớn.

Dấu hiệu cần kiểm tra:

- Kubernetes Pod có trạng thái `OOMKilled` hay không.
- Container exit code và event của Pod.
- Memory usage ngay trước thời điểm process kết thúc.
- cgroup memory usage và memory limit.
- Heap, metaspace, thread count, direct buffer và native memory.
- CPU throttling hoặc memory pressure đồng thời.

Exit code 137 thường tương ứng process bị SIGKILL, nhưng riêng con số này chưa đủ chứng minh nguyên nhân là OOM. Hãy đối chiếu Pod status, event và cgroup/kernel metrics.

## 16. Dùng Native Memory Tracking khi cần điều tra sâu

Native Memory Tracking (NMT) có thể giúp phân tích các nhóm native memory do JVM quản lý. Cần bật khi JVM khởi động:

```bash
java -XX:NativeMemoryTracking=summary -jar application.jar
```

Sau đó truy vấn:

```bash
jcmd <pid> VM.native_memory summary
```

Có thể tạo baseline và xem chênh lệch:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

NMT có overhead và không bao phủ mọi allocation native do thư viện bên thứ ba hoặc kernel thực hiện. Dùng nó cùng RSS, cgroup metrics và heap metrics; không coi NMT là phép đo tổng memory duy nhất.

Nếu cần heap dump để phân tích object retention, hãy kiểm tra dung lượng volume và chính sách dữ liệu trước khi bật `-XX:+HeapDumpOnOutOfMemoryError`. Heap dump có thể lớn, chứa dữ liệu nhạy cảm và không được tạo kịp nếu process bị SIGKILL bởi kernel.

## 17. Quy trình chọn CPU limit và heap

Một quy trình thực tế:

1. Xác định memory limit và CPU limit thực tế của container, không chỉ đọc request.
2. Xác minh HotSpot nhận container limits bằng `-XshowSettings:system`, `jcmd VM.info` và `availableProcessors()`.
3. Đo memory ngoài heap và RSS trong workload peak.
4. Chọn Xmx hoặc MaxRAMPercentage sao cho heap cộng non-heap/native và headroom vẫn nằm dưới memory limit.
5. Chọn CPU limit dựa trên throughput và latency mục tiêu; theo dõi throttling khi tải cao.
6. Điều chỉnh `ActiveProcessorCount` chỉ khi CPU count JVM nhận diện không phù hợp với cấu hình mong muốn.
7. Điều chỉnh thread pool, connection pool và concurrency theo CPU, I/O và memory mỗi task.
8. Chạy benchmark với G1 hoặc Generational ZGC dưới cùng resource limits.
9. Kiểm tra OOMKilled, Java OOME, GC pause, allocation stall và p99 latency.
10. Lưu JVM flags và resource configuration cùng version ứng dụng để mọi replica chạy nhất quán.

Khi nâng JDK hoặc thay đổi base image/container runtime, chạy lại kiểm tra container awareness. Không giả định CPU/memory detection giữ nguyên nếu thay đổi kernel, cgroup mode, JVM vendor hoặc runtime.

## 18. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đặt `-Xmx` bằng memory limit | Heap chiếm hết ngân sách, process có thể bị OOM kill | Dành headroom cho non-heap/native |
| Dùng CPU request như CPU limit | Hiểu sai quota thực tế | Kiểm tra cả request, limit và cgroup |
| Tắt `UseContainerSupport` mà không chủ đích | JVM có thể dùng thông tin host | Giữ container support bật và xác minh runtime |
| Đặt `ActiveProcessorCount` quá cao | Thread/GC parallelism vượt CPU được cấp, tăng contention | Căn theo quota và đo thực tế |
| Đặt `ActiveProcessorCount` quá thấp | Không tận dụng CPU quota | Benchmark và kiểm tra processor count |
| Chỉ xem heap usage | Bỏ qua direct/native/thread memory | Theo dõi RSS và cgroup memory |
| Tăng heap để chữa OOM kill | Có thể làm memory pressure nặng hơn | Xác định vùng memory thực sự tăng |
| Cho rằng virtual thread cần CPU riêng | Tính sai capacity cho CPU-bound task | Giới hạn CPU concurrency theo quota |
| Chỉ theo dõi CPU usage trung bình | Bỏ qua throttling theo chu kỳ | Theo dõi throttled periods/time |
| Dùng một tỷ lệ MaxRAMPercentage cho mọi service | Không tính đến native footprint khác nhau | Đo từng workload và đặt heap riêng |

## 19. Cấu hình khởi điểm và cách xác nhận

Với một container Linux chạy Java 21, có thể bắt đầu bằng cấu hình minh họa sau rồi điều chỉnh theo đo đạc:

```bash
java \
  -XX:+UseContainerSupport \
  -XX:MaxRAMPercentage=60.0 \
  -XX:ActiveProcessorCount=2 \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar application.jar
```

Ở đây:

- Container support giúp JVM nhận giới hạn cgroup.
- Maximum heap được tính theo tỷ lệ memory container.
- Active processor count được cố định ở hai cho ergonomics.
- GC log được lưu để kiểm tra hành vi thu gom.

Không dùng nguyên cấu hình này cho production nếu chưa đo memory headroom và CPU throttling. Nếu JVM đã tự nhận đúng hai CPU và không cần cố định processor count, có thể bỏ `ActiveProcessorCount`. Nếu heap cần giới hạn tuyệt đối, dùng `-Xmx` thay cho percentage. Nếu workload có native/direct memory lớn, giảm tỷ lệ heap.

Tiêu chí đạt nên bao gồm: không OOM kill, không Java OOME, RSS có headroom ở tải peak, CPU throttling nằm trong mức chấp nhận, throughput đáp ứng mục tiêu và p95/p99 latency nằm trong SLO.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Java launcher options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle Java SE 21 — Container Awareness](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#advanced-container-options)
- [Oracle Java SE 21 — Memory Management](https://docs.oracle.com/en/java/javase/21/gctuning/)
- [Oracle Java SE 21 API — Runtime.availableProcessors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html#availableProcessors())
- [Oracle Java SE 21 API — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Oracle Java SE 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
