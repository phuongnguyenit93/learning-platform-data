# Collector và tùy chọn JVM theo môi trường triển khai

Bài học này hướng dẫn chọn **garbage collector (GC)** và cấu hình **HotSpot JVM** cho môi trường phát triển, kiểm thử, container, dịch vụ trực tuyến và xử lý theo lô. Mục tiêu là tạo một cấu hình có thể đo lường, lặp lại và vận hành an toàn; không có một bộ JVM flags tối ưu cho mọi ứng dụng.

> **Phạm vi phiên bản:** Java 15 là mốc của module học, nhưng khi triển khai hiện nay cần dùng bản JDK còn được nhà cung cấp hỗ trợ (ưu tiên nhánh LTS theo chính sách tổ chức) và xác minh flags trên đúng bản phân phối. Các ví dụ dùng những lựa chọn vẫn có giá trị trong HotSpot hiện đại. Một số mặc định, thuật toán và tùy chọn có thể đổi giữa các phiên bản: ví dụ từ JDK 27, G1 là mặc định trong mọi môi trường; từ JDK 24, ZGC hoạt động theo mô hình generational và không cần công tắc riêng để kích hoạt mô hình đó.

## 1. Hiểu điều cần tối ưu trước khi chọn collector

GC tự động tìm và thu hồi đối tượng không còn được chương trình truy cập. Bốn khía cạnh phải xem cùng nhau:

- **Throughput (thông lượng):** lượng công việc hoàn thành mỗi giây/phút; với batch có thể là số bản ghi xử lý/giờ.
- **Latency (độ trễ):** thời gian phản hồi, đặc biệt p95/p99/p99.9; các pha *stop-the-world* (STW) có thể làm tăng độ trễ đuôi.
- **Footprint (dấu chân bộ nhớ):** heap, bộ nhớ native, RSS của tiến trình và giới hạn RAM của container.
- **CPU và khả năng mở rộng:** GC chạy song song hoặc đồng thời với ứng dụng cũng tiêu tốn CPU; giới hạn CPU thấp có thể gây tranh chấp tài nguyên.

Thuật ngữ cơ bản:

- **Heap** chứa phần lớn đối tượng Java; `-Xmx` đặt giới hạn tối đa cho heap, **không** giới hạn tổng RAM của tiến trình.
- **Live set** là phần dữ liệu vẫn còn được tham chiếu sau GC. Heap phải đủ cho live set, đỉnh cấp phát và khoảng trống để collector hoạt động.
- **Allocation rate** là tốc độ tạo đối tượng; tăng cấp phát thường dẫn tới GC thường xuyên hơn.
- **Pause time** là thời gian ứng dụng bị dừng bởi một pha GC; **GC time** còn bao gồm việc collector chạy đồng thời với ứng dụng.
- **RSS** là số trang nhớ vật lý tiến trình đang giữ. RSS còn gồm metaspace, code cache, thread stacks, direct buffers, thư viện native và cấu trúc của JVM.

Không đánh giá collector chỉ bằng “số lần GC” hoặc dung lượng heap trống. Một ứng dụng có pause ngắn nhưng thiếu CPU, hoặc CPU thấp nhưng p99 cao, vẫn có thể không đạt yêu cầu triển khai.

## 2. Những collector phù hợp với HotSpot hiện đại

| Collector | Điểm mạnh | Đánh đổi | Khi nên thử |
| --- | --- | --- | --- |
| **G1 (`-XX:+UseG1GC`)** | Cân bằng throughput và pause; tự điều chỉnh nhiều tham số; mặc định phù hợp cho đa số dịch vụ | Vẫn có STW; mục tiêu pause không phải cam kết cứng | API, dịch vụ web, tác vụ đa năng; lựa chọn đo baseline đầu tiên |
| **Parallel GC (`-XX:+UseParallelGC`)** | Ưu tiên thông lượng tổng thể, tận dụng nhiều CPU | Các đợt STW có thể dài hơn; bất lợi cho p99 khắt khe | Batch/ETL, xử lý offline khi chấp nhận được pause |
| **ZGC (`-XX:+UseZGC`)** | GC đồng thời với pause rất ngắn, thích hợp yêu cầu độ trễ thấp | Cần đủ CPU và headroom heap; throughput/footprint có thể kém hơn G1 hoặc Parallel tùy tải | Dịch vụ nhạy p99/p99.9 hoặc heap lớn, sau khi benchmark |
| **Serial GC (`-XX:+UseSerialGC`)** | Cách triển khai đơn giản, ít luồng GC | Thu gom STW bằng một luồng; khó mở rộng trên heap/tải lớn | Chương trình nhỏ, môi trường rất hạn chế, khi phép đo chứng minh có lợi |
| **Shenandoah (`-XX:+UseShenandoahGC`)** | Thu gom phần lớn công việc đồng thời, hướng tới pause ngắn | Khả dụng và biến thể phụ thuộc bản build/JDK; chi phí phải đo thực tế | Phương án đánh giá riêng nếu JDK đang chạy hỗ trợ |

**Nguyên tắc chọn:** bắt đầu với G1 và heap hợp lý; chỉ đổi collector khi có yêu cầu đo được (thông lượng, p99, RAM hoặc CPU). Collector không giải quyết lỗi giữ tham chiếu làm live set tăng mãi. G1 cũng không bảo đảm mọi pause thấp hơn `MaxGCPauseMillis`.

**Cập nhật quan trọng:** ở JDK 27, G1 được chọn mặc định cả trên cấu hình tài nguyên nhỏ; vì thế không suy luận collector từ số CPU/RAM. Với ZGC trên JDK 24 trở lên, chỉ dùng `-XX:+UseZGC`, không chép các hướng dẫn bật chế độ thế hệ riêng của phiên bản cũ. Shenandoah phải được xác nhận trên đúng bản phân phối JVM; việc một tên collector có trong tài liệu không chứng minh image hiện tại hỗ trợ nó.

## 3. Quy trình chọn collector theo môi trường

| Môi trường | Ưu tiên và ràng buộc | Điểm xuất phát hợp lý |
| --- | --- | --- |
| Máy phát triển / chạy unit test | Dễ tái hiện lỗi, log vừa đủ, không chiếm toàn RAM máy | G1 mặc định; `-Xmx` giới hạn theo máy; bật GC log khi cần phân tích |
| CI/CD hoặc integration test | Tính ổn định, hạn chế OOM và flakiness do thiếu tài nguyên | Dùng cùng major JDK và collector với production khi test hiệu năng; giới hạn heap rõ ràng |
| Microservice trong Docker/Kubernetes | Giới hạn RAM/CPU theo cgroup; giữ headroom cho bộ nhớ ngoài heap | G1 trước; `-Xmx` **hoặc** `-XX:MaxRAMPercentage`; bật container awareness mặc định |
| API/web service thông thường | Thông lượng tốt, p95/p99 ổn định | G1, đo latency và pause; chỉ chỉnh mục tiêu pause khi có bằng chứng |
| Batch, ETL, xử lý nền | Tối đa bản ghi/giây; độ trễ từng yêu cầu ít quan trọng | So G1 với Parallel trên cùng dữ liệu, CPU và heap |
| API nhạy độ trễ / heap lớn | p99/p99.9 thấp, tránh pause dài | So G1 với ZGC; cấp đủ CPU, heap và đo ảnh hưởng throughput |
| Tiến trình nhỏ, 1 vCPU hoặc RAM rất thấp | Footprint quan trọng hơn hiệu năng đa luồng | Giữ G1 làm baseline; thử Serial nếu benchmark cho thấy lợi ích |

Không chọn theo nhãn “microservice”, “cloud” hay “production” đơn thuần. Hai dịch vụ cùng 1 GiB RAM có thể khác nhau rất nhiều về số thread, direct memory, tốc độ cấp phát và live set.

### Trình tự quyết định thực tế

1. Xác định **SLO**: yêu cầu/giây, p95/p99 tối đa, thời gian batch, giới hạn CPU/RAM và thời gian khởi động chấp nhận được.
2. Chạy ứng dụng với **JDK và image triển khai thật**, bắt đầu bằng G1 cùng cấu hình heap hợp lý.
3. Thu số liệu dưới tải đại diện: CPU, RSS/working set, heap sau GC, số lần/pause GC, throughput, p95/p99 và số lần container restart/OOMKilled.
4. Nếu chưa đạt yêu cầu, kiểm tra thiếu heap, allocation rate, leak, nghẽn CPU/I/O hoặc CPU throttling trước khi thay thuật toán GC.
5. Chỉ thay đổi **một nhóm tham số mỗi lần** (heap, collector, mục tiêu pause), chạy lại cùng workload và so kết quả.
6. Kiểm tra cold start, steady state, đỉnh tải, thời gian tăng tải và quá trình shutdown. Rollout từng bước với đường quay lại cấu hình cũ.

## 4. Nhóm JVM options cần hiểu

### 4.1. Heap: giới hạn tuyệt đối hoặc theo RAM khả dụng

| Tùy chọn | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `-Xmx2g` | Heap tối đa xấp xỉ 2 GiB | Tổng RSS vẫn có thể cao hơn 2 GiB |
| `-Xms512m` | Heap khởi tạo | Đặt quá cao có thể tăng mức sử dụng tài nguyên và thời gian khởi động |
| `-XX:MaxRAMPercentage=60.0` | Đặt mức heap tối đa theo phần trăm RAM mà JVM nhận diện | Hữu ích trong container; nếu đã chỉ định `-Xmx`, giới hạn heap cố định là lựa chọn chính |
| `-XX:InitialRAMPercentage=10.0` | Điều chỉnh mức heap khởi tạo theo RAM khả dụng khi không đặt `-Xms` | Không phải yêu cầu cấp phát 10% RAM vật lý ngay tức thì |
| `-XX:MaxDirectMemorySize=...` | Giới hạn một phần bộ nhớ đệm trực tiếp ngoài heap | Chỉ đặt có chủ đích khi ứng dụng/thư viện cần kiểm soát direct buffers |

Trong container, phải dành bộ nhớ ngoài heap. Mô hình ngân sách:

`RAM limit > peak Java heap + metaspace + code cache + direct/native buffers + thread stacks + cấu trúc GC/JVM + dư địa OS`

Ví dụ container giới hạn **1 GiB**, chọn thử `-XX:MaxRAMPercentage=60.0` cho mức heap tối đa danh nghĩa quanh **614 MiB**; phần còn lại là ngân sách cho native, thread stacks, thư viện, page cache và đột biến. **60% chỉ là giả định ban đầu**: dịch vụ có nhiều thread hoặc xử lý direct buffers có thể cần heap nhỏ hơn. Không lấy tỷ lệ 60% làm quy tắc chung.

`-Xms` bằng `-Xmx` đôi khi giúp độ trễ ổn định hơn vì giảm thay đổi kích thước heap, nhưng đổi lại chiếm dụng bộ nhớ sớm và có thể không phù hợp container dày đặc. Đo cả startup và RSS trước khi áp dụng.

### 4.2. Chọn GC và điều chỉnh mục tiêu pause

```bash
# Dùng G1 rõ ràng; ở JDK 27 đây cũng là mặc định.
java -XX:+UseG1GC -Xmx1g -jar app.jar

# Batch ưu tiên throughput, nếu các pause dài được chấp nhận.
java -XX:+UseParallelGC -Xmx2g -jar batch.jar

# Dịch vụ có yêu cầu độ trễ rất thấp; cần benchmark và đủ headroom.
java -XX:+UseZGC -Xmx4g -jar api.jar
```

Ba lệnh là **ba cấu hình độc lập**; không bật nhiều collector cùng lúc. Thay `app.jar`, `batch.jar`, `api.jar` bằng artifact thật. Các ví dụ chỉ định `-Xmx` minh họa giới hạn heap, **không** phải kích thước khuyến nghị cho mọi workload.

Riêng G1 có thể điều chỉnh mục tiêu pause bằng `-XX:MaxGCPauseMillis=200`. Đây là **mục tiêu điều khiển thích nghi**, không phải hard deadline và không đảm bảo mọi đợt GC dưới 200 ms. Việc đặt mục tiêu quá thấp có thể tăng CPU/overhead và giảm throughput. Thường nên để G1 tự điều chỉnh young generation; không cố định `-Xmn` hoặc tỷ lệ young/old theo mẹo chung chung.

### 4.3. CPU và tài nguyên container

HotSpot trên Linux hiện đại tự nhận diện giới hạn tài nguyên container theo mặc định thông qua `UseContainerSupport`. Có thể kiểm tra bằng:

```bash
java -Xlog:os+container=info -version
```

`-XX:ActiveProcessorCount=2` cho phép JVM tính toán số CPU khả dụng khi lựa chọn kích thước các pool/luồng GC. Dùng khi số CPU JVM nhận diện không phản ánh chính sách triển khai mong muốn; **nó không tự tạo ra CPU quota hay cưỡng chế giới hạn CPU của hệ điều hành**. Hạn chế cấu hình tay `ParallelGCThreads`/`ConcGCThreads` trước khi có dữ liệu.

Trong Kubernetes, `requests` ảnh hưởng lập lịch tài nguyên và `limits` có thể dẫn tới CPU throttling/OOM kill. Đừng xem một đỉnh p99 là lỗi GC khi thật ra container bị throttling. Theo dõi metric từ JVM **và** metrics cgroup/cluster.

### 4.4. Logging, chẩn đoán và hành vi khi thiếu bộ nhớ

```bash
# In log GC và safepoint ra stdout (phù hợp cho log collector của container).
java -Xlog:gc*,safepoint:stdout:time,uptime,level,tags -Xmx1g -jar app.jar

# Ghi log quay vòng vào thư mục hiện tại.
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -Xmx1g -jar app.jar
```

- `-Xlog:gc*` cho biết hoạt động collector, heap trước/sau GC và các pause; `safepoint` giúp phân biệt một số thời điểm dừng JVM với công việc GC.
- `-XX:+HeapDumpOnOutOfMemoryError` và `-XX:HeapDumpPath=/path/co-quyen-ghi` hữu ích khi điều tra heap OOM, nhưng heap dump có thể rất lớn và chứa dữ liệu nhạy cảm; kiểm soát ổ đĩa, phân quyền và thời gian lưu.
- `-XX:NativeMemoryTracking=summary` hỗ trợ đối chiếu bộ nhớ native bằng `jcmd`, nhưng có overhead; bật khi cần chẩn đoán.
- Với app dùng giao thức mạng, off-heap hoặc native library, phải đo bộ nhớ liên quan; tăng `-Xmx` có thể làm container bị OOM sớm hơn.

**Vị trí option:** truyền cờ JVM **trước** `-jar`. Đặt sau tên JAR sẽ truyền chúng vào `main(String[] args)` của ứng dụng, không cấu hình JVM.

## 5. Cấu hình triển khai tham khảo

### 5.1. Local/CI: giới hạn rõ và dễ chẩn đoán

```bash
java -XX:+UseG1GC -Xmx512m \
  -Xlog:gc*:stdout:uptime,level,tags \
  -jar app.jar
```

Lệnh trên dùng cú pháp shell POSIX để xuống dòng; trong PowerShell có thể đặt toàn bộ trên một dòng. Chạy cùng JDK major version và collector dự kiến ở production khi đang test hành vi hiệu năng/GC. Unit test logic không nhất thiết cần GC log liên tục.

### 5.2. Container 1 GiB: ưu tiên không vượt memory limit

```bash
java -XX:+UseG1GC \
  -XX:MaxRAMPercentage=60.0 \
  -Xlog:gc*,safepoint:stdout:time,uptime,level,tags \
  -jar app.jar
```

Đặt memory limit container bằng hệ thống triển khai (ví dụ Kubernetes) và xác thực mức JVM nhận diện thực tế. Ở cấu hình này không đặt thêm `-Xmx`; giá trị `MaxRAMPercentage` dùng để thiết lập giới hạn heap dựa trên RAM khả dụng. Nếu có nhiều thread, cache off-heap hoặc native allocations, phải giảm tỷ lệ heap hoặc tăng memory limit sau khi đo.

Với Docker/Kubernetes, có thể truyền các cờ qua biến môi trường **riêng cho container ứng dụng**:

```yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:+UseG1GC -XX:MaxRAMPercentage=60.0 -Xlog:gc*:stdout:uptime,level,tags"
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
  limits:
    cpu: "2"
    memory: "1Gi"
```

Đây là **đoạn cấu hình thuộc một container spec**, không phải manifest Kubernetes độc lập. `JAVA_TOOL_OPTIONS` được JVM đọc khi khởi chạy; kiểm tra log startup để chắc cờ đã có hiệu lực và tránh áp dụng biến này chung cho công cụ build không liên quan. CPU/memory ở đây là giả định minh họa, cần thay bằng nhu cầu đo được của ứng dụng.

### 5.3. Batch/ETL: throughput trước, pause sau

```bash
java -XX:+UseParallelGC -Xms2g -Xmx2g \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar batch.jar
```

Phù hợp để **thử nghiệm** trên máy có đủ CPU/RAM và khi dừng tạm thời không làm vi phạm deadline nghiệp vụ. So với G1 bằng **thời gian hoàn tất toàn batch, CPU tổng, đỉnh RSS và kích thước dữ liệu đã xử lý**; đừng mặc định Parallel luôn nhanh hơn.

### 5.4. API nhạy p99: kiểm tra ZGC

```bash
java -XX:+UseZGC -Xmx4g \
  -Xlog:gc*,safepoint:stdout:uptime,level,tags \
  -jar api.jar
```

ZGC hướng tới pause cực ngắn bằng xử lý phần lớn công việc đồng thời. Cần chừa vùng heap cho ứng dụng tiếp tục cấp phát trong lúc GC chạy; thiếu headroom hoặc CPU làm giảm khả năng đạt SLO. Đánh giá cả p99, throughput, CPU, đỉnh RSS, số request timeout và chi phí tài nguyên. Với JDK hiện đại, không thêm tùy chọn chuyển ZGC sang generational theo tài liệu cũ.

### 5.5. Tác vụ rất nhỏ

```bash
java -XX:+UseSerialGC -Xmx256m -jar tool.jar
```

Đây là phương án **để benchmark** cho tiến trình nhỏ hoặc rất ít CPU. Không áp dụng cho web service tải cao chỉ vì nó chạy trong container nhỏ: pause STW của Serial có thể làm hỏng p99.

## 6. Kiểm chứng cấu hình JVM thực sự đang chạy

Cờ viết trong Dockerfile, Helm values hoặc script **chưa chứng minh** collector đang được dùng. Hãy kiểm chứng ở runtime.

```bash
# Kiểm tra phiên bản, vendor và các thiết lập VM.
java -version
java -XshowSettings:vm -version

# Quan sát log chọn collector khi bắt đầu tiến trình.
java -Xlog:gc=info -Xmx256m -version

# Khi JDK có công cụ jcmd, kiểm tra tiến trình đang chạy.
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info

# Chỉ có ý nghĩa nếu đã bật Native Memory Tracking lúc khởi chạy.
jcmd <PID> VM.native_memory summary
```

`<PID>` trong các dòng `jcmd` là **ID tiến trình thực tế**. Tên GC, dung lượng heap, cách hiển thị log và số lượng collector beans tùy JDK/flag, nên không chép một stdout cố định cho mọi máy. `jcmd` có thể cần JDK tools, quyền truy cập cùng user và khả năng attach trong image/container.

Có thể ghi JFR khi điều tra đỉnh CPU hoặc độ trễ:

```bash
jcmd <PID> JFR.start name=gc-check settings=profile duration=2m filename=gc-check.jfr
```

JFR và GC logs hỗ trợ phân biệt pause GC với ứng dụng bị chặn bởi lock, I/O, networking hoặc CPU throttling. `profile` có thể nhiều dữ liệu/overhead hơn `default`, nên chỉ bật có chủ đích và bảo vệ dữ liệu ghi nhận được.

### Ví dụ Java 17+ kiểm tra GC đang dùng

Lưu thành `GcInspector.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;

public class GcInspector {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("Java feature: " + Runtime.version().feature());
        System.out.println("Available processors: " + runtime.availableProcessors());
        System.out.println("Max heap MiB: " + runtime.maxMemory() / (1024 * 1024));

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println("GC bean: " + gc.getName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac GcInspector.java
java -XX:+UseG1GC -Xmx256m GcInspector
java -XX:+UseParallelGC -Xmx256m GcInspector
```

Chương trình in phiên bản Java, số CPU mà JVM nhận thấy, heap tối đa và các **GC MXBeans**. Kết quả cụ thể phụ thuộc JDK, nền tảng và flags; tên bean không nhất thiết trùng đúng tên collector trong tài liệu, và có thể xuất hiện nhiều bean (ví dụ young/old). Ví dụ chỉ dùng API chuẩn Java nên không cần thư viện ngoài. Để biết rõ flags JVM đã nhận, đối chiếu thêm `jcmd ... VM.flags` hoặc GC startup logs.

## 7. Đọc triệu chứng thay vì vội đổi collector

| Triệu chứng | Kiểm tra trước | Hướng xử lý có cơ sở |
| --- | --- | --- |
| GC chạy liên tục, throughput giảm | Allocation rate, heap sau GC, số object còn sống, CPU và live set | Giảm cấp phát/bộ nhớ giữ lâu; xem xét tăng heap trong RAM budget |
| G1 có pause dài hoặc Full GC | GC log, đỉnh tải, large objects, tốc độ tăng old generation, heap headroom | Xác định vì sao GC không theo kịp; điều chỉnh heap/tải và chỉ sau đó tinh chỉnh G1 |
| p99 cao nhưng GC pause nhỏ | CPU throttling, safepoints, lock contention, I/O, network, thread pools | Sửa đúng nút thắt; đổi GC có thể không giúp gì |
| `OutOfMemoryError: Java heap space` | Heap dump, live set sau Full GC, retention/leak, giới hạn `-Xmx` | Sửa leak/retention hoặc cấp heap phù hợp |
| Container bị `OOMKilled`/exit 137 | RSS, cgroup limit, direct/native memory, thread stacks, page cache; kiểm tra tín hiệu thực tế từ orchestrator | Chừa headroom ngoài heap, giảm đỉnh RSS hoặc tăng limit |
| `unable to create native thread` | Giới hạn thread/process, native memory, quá nhiều worker threads | Điều chỉnh thread pool và giới hạn hệ thống; không quy ngay cho GC heap |
| JVM báo “Unrecognized VM option” | `java -version`, vendor, cú pháp và flags của đúng JDK | Dùng tùy chọn được build đó hỗ trợ; không sao chép flags giữa các đời JDK |

Những lỗi thường gặp:

1. **Đặt `-Xmx` bằng 100% RAM container:** bỏ qua metaspace, native/off-heap và thread stacks.
2. **Đổi thẳng sang ZGC chỉ vì muốn nhanh:** ZGC ưu tiên latency, chưa chắc cho throughput hoặc chi phí tài nguyên tốt nhất.
3. **Ép G1 có pause mục tiêu cực nhỏ:** có thể làm CPU/GC overhead tăng và đạt SLO kém hơn.
4. **Dùng cấu hình local thay cho production:** CPU quota, memory limit, số request và alloc rate khác nhau.
5. **Không biết collector thực sự được bật:** cấu hình từ `JAVA_TOOL_OPTIONS`, entrypoint hoặc deployment có thể tạo ra flags khác mong đợi.
6. **Chỉ theo dõi heap usage mà bỏ qua RSS:** native allocation khiến container chết dù heap còn chỗ.
7. **Sao chép flags từng hợp lệ ở một phiên bản Java cũ:** kiểm tra lại trên bản JDK đang dùng, đặc biệt những cờ thử nghiệm, cờ đổi tên hoặc đã bị loại bỏ.

## 8. Checklist trước khi đưa vào production

- [ ] Chốt JDK vendor/major version được hỗ trợ và chạy thử trên đúng container image.
- [ ] Ghi rõ SLO (throughput, p95/p99), CPU request/limit và memory request/limit.
- [ ] Có baseline với G1, heap budget và workload đại diện.
- [ ] Xác minh collector, heap thực tế, số CPU JVM nhìn thấy từ startup log hoặc `jcmd`.
- [ ] Dành đủ RAM cho bộ nhớ **ngoài heap**; theo dõi RSS và OOMKilled.
- [ ] Thu GC/safepoint log, metrics ứng dụng và metrics container đồng thời.
- [ ] Benchmark cấu hình thay thế theo cùng tải; ghi kết quả trước/sau.
- [ ] Có cảnh báo cho p99, CPU throttling, heap sau GC, Full GC, RSS và restart.
- [ ] Thử rollout nhỏ, chuẩn bị rollback cấu hình và review lại mỗi lần đổi JDK.

## 9. Tài liệu chính thức nên đối chiếu với phiên bản đang chạy

- [JDK 27 — Available Collectors và tiêu chí chọn](https://docs.oracle.com/en/java/javase/27/gctuning/available-collectors.html)
- [JDK 27 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)
- [JDK 27 — JVM command options, heap, CPU/container và diagnostics](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [JDK 25 — ZGC và yêu cầu headroom](https://docs.oracle.com/en/java/javase/25/gctuning/z-garbage-collector.html)
- [JDK 27 — Thay đổi GC mặc định](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)

**Điểm cần nhớ:** hãy bắt đầu từ yêu cầu triển khai, ngân sách bộ nhớ và phép đo thực tế. G1 thường là lựa chọn xuất phát; Parallel phù hợp để thử cho batch ưu tiên throughput; ZGC phù hợp để đánh giá khi latency rất khắt khe; Serial chỉ có lợi ở một số cấu hình nhỏ; Shenandoah phụ thuộc JDK đang dùng. Cấu hình tốt là cấu hình thỏa SLO trong giới hạn CPU/RAM có thể chứng minh bằng dữ liệu.
