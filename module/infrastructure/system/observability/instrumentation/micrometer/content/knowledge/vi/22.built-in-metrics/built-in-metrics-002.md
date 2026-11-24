# Phép đo GC, CPU, thời gian sống tiến trình và tài nguyên hệ thống

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, Micrometer không chỉ cung cấp API để tự instrument nghiệp vụ mà còn có các binder thu thập số liệu có sẵn từ JVM và hệ điều hành. Những binder này đọc thông tin từ các MXBean của JVM, API hệ thống hoặc nguồn dữ liệu mà nền tảng Java cung cấp, sau đó đăng ký chúng vào `MeterRegistry`.

Các nhóm số liệu quan trọng gồm bộ nhớ heap/non-heap, hoạt động garbage collection (GC), thread, classloader, CPU, uptime, file descriptor và dung lượng đĩa. Chúng giúp trả lời câu hỏi ứng dụng có đang chịu áp lực bộ nhớ, tốn thời gian cho GC, dùng CPU cao, rò rỉ thread hay sắp hết tài nguyên hệ thống hay không. Để diễn giải đúng, cần hiểu nguồn đo, đơn vị, giới hạn theo JVM/OS/container và mối liên hệ giữa các metric.

## 1. Built-in metrics và MeterBinder

Micrometer cung cấp các lớp triển khai `MeterBinder`. Mỗi binder đọc một nhóm thông tin từ JVM hoặc hệ thống rồi đăng ký meter vào registry được truyền cho `bindTo()`.

| Binder | Nhóm dữ liệu chính |
| --- | --- |
| `JvmMemoryMetrics` | Heap, non-heap và buffer pool |
| `JvmGcMetrics` | Thời gian pause GC, allocation và dữ liệu heap sau GC nếu JVM cung cấp |
| `JvmThreadMetrics` | Số thread theo trạng thái, thread live/daemon/peak |
| `ClassLoaderMetrics` | Số class đã load và unload |
| `ProcessorMetrics` | CPU process, CPU hệ thống, số processor và load average nếu nền tảng hỗ trợ |
| `UptimeMetrics` | Thời gian chạy và thời điểm bắt đầu tiến trình |
| `FileDescriptorMetrics` | Số file descriptor đang mở và giới hạn tối đa trên hệ điều hành hỗ trợ |
| `DiskSpaceMetrics` | Dung lượng trống và tổng dung lượng của một đường dẫn được chọn |

Khi sử dụng Spring Boot Actuator cùng Micrometer, nhiều binder JVM và system thường được auto-configure. Vì vậy, trước khi tự đăng ký binder, hãy kiểm tra các meter đã có trong registry. Đăng ký cùng binder thêm lần nữa có thể tạo đăng ký trùng, phát sinh cảnh báo hoặc xung đột meter tùy loại và cấu hình.

## 2. Spring Boot tự đăng ký JVM và system metrics

Với Spring Boot, thêm Actuator và registry exporter tương ứng:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Expose endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Sau khi ứng dụng khởi động, endpoint `/actuator/metrics` cho phép khám phá và đọc chi tiết một meter, ví dụ `/actuator/metrics/jvm.memory.used`. Endpoint `/actuator/prometheus` cung cấp định dạng exposition để Prometheus scrape nếu Prometheus registry có trong classpath và endpoint được expose.

Các meter chính xác phụ thuộc phiên bản Spring Boot, Micrometer, JVM và hệ điều hành. Một số meter có thể không xuất hiện nếu nền tảng không cung cấp nguồn dữ liệu, binder bị loại trừ hoặc cấu hình filter đã từ chối meter.

## 3. Đăng ký binder thủ công khi không dùng auto-configuration

Trong ứng dụng Java không dùng Spring Boot, có thể đăng ký binder trực tiếp vào registry:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.jvm.ClassLoaderMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmGcMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics;
import io.micrometer.core.instrument.binder.jvm.JvmThreadMetrics;
import io.micrometer.core.instrument.binder.system.ProcessorMetrics;
import io.micrometer.core.instrument.binder.system.UptimeMetrics;

public final class RuntimeMetrics implements AutoCloseable {
    private final JvmGcMetrics gcMetrics = new JvmGcMetrics();

    public void bindTo(MeterRegistry registry) {
        new ClassLoaderMetrics().bindTo(registry);
        new JvmMemoryMetrics().bindTo(registry);
        gcMetrics.bindTo(registry);
        new JvmThreadMetrics().bindTo(registry);
        new ProcessorMetrics().bindTo(registry);
        new UptimeMetrics().bindTo(registry);
    }

    @Override
    public void close() {
        gcMetrics.close();
    }
}
```

Tạo một `RuntimeMetrics`, gọi `bindTo(registry)` một lần trong lúc khởi tạo ứng dụng và gọi `close()` khi ứng dụng dừng để giải phóng listener GC. Nếu cần file descriptor hoặc disk metrics, đăng ký binder tương ứng theo hệ điều hành và đường dẫn mà ứng dụng muốn theo dõi. Với ứng dụng Spring Boot đã auto-configure các binder, không sao chép đoạn đăng ký thủ công này vào cấu hình mặc định.

Một số binder có tài nguyên hoặc listener cần được đóng khi ứng dụng dừng. Hãy tuân theo API vòng đời của phiên bản Micrometer đang dùng; không tạo binder lặp lại theo request hoặc mỗi lần chạy tác vụ.

## 4. Đọc bộ nhớ JVM: heap, non-heap và buffer

Các meter bộ nhớ thường gặp:

| Metric Micrometer | Ý nghĩa | Đơn vị |
| --- | --- | --- |
| `jvm.memory.used` | Bộ nhớ đang được sử dụng trong memory pool | byte |
| `jvm.memory.committed` | Bộ nhớ JVM đã cam kết có thể sử dụng cho pool | byte |
| `jvm.memory.max` | Giới hạn tối đa của pool nếu JVM xác định được | byte |
| `jvm.buffer.memory.used` | Bộ nhớ của buffer pool đang dùng | byte |
| `jvm.buffer.total.capacity` | Tổng capacity của buffer pool | byte |
| `jvm.buffer.count` | Số buffer trong pool | số lượng |

Các meter `jvm.memory.*` thường có tag `area` với giá trị `heap` hoặc `nonheap`, cùng tag `id` để nhận diện memory pool như Eden, Survivor, Old Gen, Metaspace hoặc Code Cache. Tên pool phụ thuộc JVM và garbage collector đang sử dụng.

Heap chứa các object Java được quản lý bởi GC. Non-heap bao gồm các vùng như Metaspace và Code Cache. Direct buffer có thể được phản ánh qua `jvm.buffer.*`; chúng không đồng nghĩa với toàn bộ native memory của tiến trình.

Ví dụ PromQL tính tỷ lệ heap đang dùng so với giới hạn tối đa:

```promql
sum(jvm_memory_used_bytes{area="heap"})
/
sum(jvm_memory_max_bytes{area="heap"} > 0)
```

Tên Prometheus ở đây là tên đã chuẩn hóa từ meter Micrometer. Nếu `max` không xác định hoặc không dương, tỷ lệ không có ý nghĩa; hãy kiểm tra series thực tế và cân nhắc dùng committed làm một góc nhìn khác. Heap usage cao chưa đủ kết luận memory leak: cần xem xu hướng sau GC, tốc độ allocation, live data và hành vi tải.

## 5. Theo dõi hoạt động Garbage Collection

`JvmGcMetrics` cung cấp thông tin về các lần GC và một số thống kê bộ nhớ liên quan. Các meter thường gặp gồm:

| Metric Micrometer | Ý nghĩa | Dạng dữ liệu |
| --- | --- | --- |
| `jvm.gc.pause` | Thời lượng các lần GC pause | Timer |
| `jvm.gc.memory.allocated` | Lượng bộ nhớ được cấp phát tích lũy theo nguồn JVM | Counter/function counter tùy implementation |
| `jvm.gc.memory.promoted` | Lượng dữ liệu được promote lên vùng sống lâu hơn | Counter/function counter tùy implementation |
| `jvm.gc.live.data.size` | Kích thước dữ liệu còn sống sau GC theo nguồn JVM | Gauge |
| `jvm.gc.max.data.size` | Mức dữ liệu live tối đa/ước lượng theo nguồn JVM | Gauge |

`jvm.gc.pause` có các tag như `action` và `cause` để phân biệt loại hành động và nguyên nhân GC. Timer cung cấp count và tổng thời gian pause; nếu histogram được bật, có thể tính percentile từ bucket. Tên action/cause và các meter bộ nhớ cụ thể phụ thuộc garbage collector cùng JVM.

Tổng thời gian pause tăng nhanh có thể cho thấy GC gây ảnh hưởng tới thời gian phản hồi. Tuy nhiên, không phải mọi hoạt động GC đều là stop-the-world pause; một số collector thực hiện công việc đồng thời với ứng dụng. Hãy kết hợp pause metrics với allocation rate, heap sau GC, CPU và log GC của JVM.

## 6. Tính tốc độ GC pause và allocation

Với Prometheus, tốc độ số lần pause trong 5 phút:

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_count[5m])
)
```

Thời gian pause trung bình của mỗi lần GC trong cửa sổ:

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum[5m])
)
/
sum by (instance) (
  rate(jvm_gc_pause_seconds_count[5m])
)
```

Tỷ lệ thời gian pause gần đúng trên mỗi giây thời gian thực:

```promql
sum by (instance) (
  rate(jvm_gc_pause_seconds_sum[5m])
)
```

Ví dụ, kết quả 0,03 có thể được đọc là khoảng 3% thời gian trong cửa sổ được ghi nhận là GC pause, theo phạm vi timer đang tổng hợp. Đây là tín hiệu gần đúng; cần xem phạm vi meter, số JVM và loại pause trước khi diễn giải.

Tốc độ cấp phát bộ nhớ, nếu series counter tương ứng được xuất:

```promql
rate(jvm_gc_memory_allocated_bytes_total[5m])
```

Tên series có thể khác theo phiên bản registry. Xác nhận tên và hậu tố thực tế tại `/actuator/prometheus`. Allocation rate cao kết hợp GC pause tăng có thể cho thấy ứng dụng tạo nhiều object hoặc workload thay đổi; nó không tự chứng minh có memory leak.

## 7. Thread và classloader

`JvmThreadMetrics` cung cấp số lượng thread và trạng thái thread. Các meter thường gặp:

- `jvm.threads.live`: số thread hiện đang sống.
- `jvm.threads.daemon`: số daemon thread.
- `jvm.threads.peak`: số thread sống lớn nhất kể từ mốc JVM theo dõi.
- `jvm.threads.states`: số thread theo trạng thái như `runnable`, `blocked`, `waiting`, `timed-waiting`.

Số thread tăng liên tục có thể là dấu hiệu tạo thread không giới hạn hoặc executor không được quản lý. Nhiều thread ở trạng thái `blocked` có thể gợi ý tranh chấp lock; nhiều thread `waiting` không nhất thiết là lỗi vì thread pool thường chờ công việc.

`ClassLoaderMetrics` thường cung cấp:

- `jvm.classes.loaded`: số class đang được load trong JVM.
- `jvm.classes.unloaded`: số class đã unload tích lũy.

Class loaded tăng dần có thể bình thường khi ứng dụng khởi động hoặc tải module. Nếu tăng liên tục trong một workload ổn định, hãy xem xét tạo class động, proxy hoặc classloader tồn tại quá lâu. Cần kết hợp heap dump và công cụ chẩn đoán JVM để xác nhận nguyên nhân.

## 8. CPU và tải hệ thống

`ProcessorMetrics` có thể cung cấp các meter:

| Metric | Ý nghĩa | Đơn vị/miền thường gặp |
| --- | --- | --- |
| `process.cpu.usage` | Tỷ lệ CPU mà tiến trình JVM sử dụng | tỷ lệ từ 0 đến 1 nếu nguồn hỗ trợ |
| `system.cpu.usage` | Tỷ lệ CPU toàn hệ thống đang sử dụng | tỷ lệ từ 0 đến 1 nếu nguồn hỗ trợ |
| `system.cpu.count` | Số processor JVM nhìn thấy | số lượng |
| `system.load.average.1m` | Load average trong một phút nếu OS hỗ trợ | giá trị load average |

`process.cpu.usage` phản ánh CPU của tiến trình Java; `system.cpu.usage` phản ánh hệ thống rộng hơn. Nếu process CPU cao nhưng system CPU thấp, tiến trình có thể đang chiếm phần lớn năng lực CPU được cấp cho nó. Nếu cả hai cao, máy hoặc node có thể đang chịu tải từ nhiều process.

Trong container, số processor mà JVM nhìn thấy có thể bị giới hạn bởi cgroup hoặc cấu hình runtime và không nhất thiết bằng số CPU vật lý của host. CPU quota, throttling và giới hạn container cần được đối chiếu với metrics của nền tảng. `system.load.average.1m` có thể không được hỗ trợ trên một số OS hoặc có cách diễn giải khác nhau; meter có thể không xuất hoặc trả giá trị không hữu ích.

Để hiển thị CPU process dưới dạng phần trăm, nhân tỷ lệ với 100:

```promql
process_cpu_usage * 100
```

Đọc tỷ lệ CPU toàn hệ thống:

```promql
system_cpu_usage * 100
```

Hai giá trị là tỷ lệ, không phải số core đã dùng. Khi cần đánh giá throttling hoặc mức sử dụng so với quota container, đối chiếu thêm metrics cgroup/container do nền tảng cung cấp.

## 9. Uptime và thời điểm khởi động tiến trình

`UptimeMetrics` thường đăng ký:

- `process.uptime`: thời gian tiến trình đã chạy, đơn vị giây.
- `process.start.time`: thời điểm tiến trình bắt đầu, thường được biểu diễn dưới dạng epoch seconds.

Uptime giúp phát hiện restart ngoài dự kiến và đối chiếu với deploy. Nếu `process.uptime` đột ngột trở về thấp, có thể JVM vừa khởi động lại hoặc một instance mới được tạo. Khi hệ thống có nhiều replica, cần giữ label `instance`/`pod` để phân biệt vòng đời của từng tiến trình.

Không dùng uptime đơn lẻ để kết luận ứng dụng khỏe. Một tiến trình chạy lâu vẫn có thể bị nghẽn hoặc rò rỉ tài nguyên; một tiến trình vừa khởi động có thể đang ở giai đoạn warm-up.

## 10. File descriptor và dung lượng đĩa

Trên hệ điều hành hỗ trợ, `FileDescriptorMetrics` có thể xuất:

- `process.files.open`: số file descriptor đang mở.
- `process.files.max`: giới hạn file descriptor tối đa mà process có thể sử dụng.

Tỷ lệ sử dụng file descriptor:

```promql
process_files_open / process_files_max
```

Tỷ lệ tăng liên tục có thể gợi ý file/socket không được đóng hoặc tải kết nối tăng. Cần so sánh với traffic, connection pool và giới hạn của container/OS.

`DiskSpaceMetrics` theo dõi dung lượng của một đường dẫn được cấu hình, thường có các meter `disk.free` và `disk.total` theo byte. Nó chỉ phản ánh path được binder theo dõi, không tự động đại diện cho mọi filesystem hoặc volume trong container.

Tỷ lệ dung lượng đã dùng của path:

```promql
1 - (disk_free_bytes / disk_total_bytes)
```

Metric disk thường có tag `path`; nếu theo dõi nhiều path, giữ tag này trong truy vấn để không cộng nhầm các filesystem khác nhau. Có thể nhân kết quả với 100 để hiển thị phần trăm.

Ví dụ đăng ký thủ công cho một đường dẫn:

```java
import io.micrometer.core.instrument.binder.system.DiskSpaceMetrics;
import java.io.File;

new DiskSpaceMetrics(new File("/var/lib/app"))
    .bindTo(registry);
```

Trên Windows, đường dẫn phải là thư mục/ổ đĩa hợp lệ của môi trường triển khai. Với container, hãy theo dõi mount point chứa dữ liệu thực tế; filesystem của host và filesystem nhìn từ container có thể khác nhau.

## 11. Tổng hợp các meter và câu hỏi vận hành

Các metric có ý nghĩa nhất khi được đọc cùng nhau:

| Triệu chứng | Meter nên đối chiếu | Câu hỏi tiếp theo |
| --- | --- | --- |
| Heap usage tăng | `jvm.memory.used`, `jvm.memory.max`, `jvm.gc.live.data.size` | Heap sau GC có tăng qua nhiều chu kỳ không? |
| GC pause tăng | `jvm.gc.pause`, allocation rate, CPU | Có allocation burst hoặc collector đang chịu áp lực không? |
| CPU process cao | `process.cpu.usage`, `system.cpu.usage`, `system.cpu.count` | CPU đến từ workload, GC hay thread busy loop? |
| Thread tăng liên tục | `jvm.threads.live`, `jvm.threads.states` | Có executor không giới hạn hoặc thread không được giải phóng? |
| File descriptor gần giới hạn | `process.files.open`, `process.files.max` | Có socket/file bị giữ lại hoặc connection pool quá lớn? |
| Disk sắp đầy | `disk.free`, `disk.total` | Log, file tạm hay dữ liệu ứng dụng đang tăng? |
| Instance restart thường xuyên | `process.uptime`, `process.start.time` | Có OOM, liveness probe, deploy hoặc crash không? |

Metrics cung cấp tín hiệu để khoanh vùng. Để xác nhận nguyên nhân, có thể cần GC log, thread dump, heap dump, profiler, log ứng dụng hoặc metrics của container/orchestrator.

## 12. Kiểm tra qua Actuator và Prometheus

Với endpoint Actuator, có thể kiểm tra một meter cụ thể:

```text
GET /actuator/metrics/jvm.memory.used
GET /actuator/metrics/jvm.gc.pause
GET /actuator/metrics/process.cpu.usage
GET /actuator/metrics/process.uptime
```

Endpoint metrics thường trả tên meter, measurements và available tags. Có thể thêm query parameter `tag` để lọc theo một tag cụ thể, tùy endpoint và phiên bản Spring Boot.

Với Prometheus, kiểm tra exposition:

```text
GET /actuator/prometheus
```

Tên meter thường được chuẩn hóa thành dạng snake case và bổ sung hậu tố đơn vị, ví dụ `jvm_memory_used_bytes`, `process_cpu_usage`, `process_uptime_seconds` hoặc `jvm_gc_pause_seconds_count`. Không sao chép tên từ tài liệu một cách máy móc; hãy xác nhận metric và label thực tế được exporter tạo ra.

Khi kiểm tra, chú ý:

- Meter có xuất hiện sau khi ứng dụng khởi động không?
- Tag `area`, `id`, `state`, `action`, `cause` có giá trị như mong đợi không?
- Đơn vị là byte, giây, số lượng hay tỷ lệ?
- Giá trị có thay đổi khi tạo tải hoặc kích hoạt GC không?
- Meter có bị `MeterFilter` từ chối hoặc đổi tên không?

## 13. Cảnh báo và giới hạn khi diễn giải

Không nên đặt alert chỉ dựa trên một giá trị tức thời. Heap usage cao có thể bình thường trước GC; thread waiting có thể là trạng thái idle; CPU cao trong một khoảng ngắn có thể do warm-up hoặc batch. Alert nên xét xu hướng, thời gian kéo dài và ảnh hưởng tới SLO.

Một số giới hạn quan trọng:

- **GC phụ thuộc collector:** tên action/cause và số liệu có thể khác giữa G1, ZGC, Shenandoah hoặc collector khác.
- **CPU phụ thuộc OS/JVM:** một số nguồn MXBean không hỗ trợ hoặc trả giá trị không khả dụng.
- **Container giới hạn tài nguyên:** số CPU và bộ nhớ JVM nhìn thấy phụ thuộc cgroup, runtime và phiên bản Java.
- **Heap không phải toàn bộ memory:** native memory, thread stack, direct buffer và memory mapping có thể không nằm trong `jvm.memory.used`.
- **Disk path cụ thể:** `disk.free` chỉ nói về path đã đăng ký, không đại diện tất cả volume.
- **Metric vắng mặt không luôn là 0:** binder có thể không có dữ liệu trên nền tảng hiện tại hoặc metric bị filter.

Không đưa PID, tên file tùy ý, user ID hoặc dữ liệu biến thiên cao vào tag. Các binder chuẩn thường dùng tag có tập giá trị hữu hạn như `area`, `id`, `state`, `action` và `cause`; vẫn cần xem xét cardinality khi có nhiều memory pool hoặc collector-specific labels.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Không có `jvm.*` metrics | Thiếu Actuator/Micrometer binder, auto-configuration bị tắt hoặc filter từ chối meter |
| Heap max không có hoặc không hợp lệ | JVM không xác định giới hạn cho pool hoặc pool không có max cố định |
| GC pause bằng 0 | Chưa có GC pause trong khoảng quan sát, collector không cung cấp dữ liệu hoặc metric chưa được scrape |
| CPU usage là NaN/không xuất | OS/JVM không hỗ trợ nguồn đo hoặc chưa có mẫu hợp lệ |
| `system.cpu.count` khác số CPU host | JVM/container chỉ nhìn thấy CPU được cấp hoặc giới hạn |
| File descriptor metrics vắng mặt | Hệ điều hành không hỗ trợ API tương ứng hoặc binder không được đăng ký |
| Disk metrics không phản ánh volume cần xem | Binder theo dõi path khác với mount point chứa dữ liệu |
| Metric bị trùng hoặc cảnh báo đăng ký | Binder đã được Spring Boot đăng ký nhưng code lại bind thủ công |
| Heap cao bị kết luận ngay là leak | Chưa xem live data sau GC, allocation và xu hướng qua nhiều chu kỳ |

Khi điều tra, kiểm tra endpoint Actuator trước, xác định binder có hoạt động hay không, xem tag và đơn vị, sau đó đối chiếu với nguồn JVM/OS và trạng thái container. Dùng công cụ chẩn đoán chuyên sâu để xác nhận leak, deadlock hoặc CPU hotspot.

## 15. Nguyên tắc áp dụng

Ưu tiên binder JVM và system metrics có sẵn để thu thập GC, memory, thread, classloader, CPU, uptime, file descriptor và disk. Với Spring Boot Actuator, để auto-configuration quản lý các binder mặc định; chỉ đăng ký thủ công khi ứng dụng tự quản lý registry hoặc cần theo dõi một nguồn/path bổ sung.

Đọc metric cùng đơn vị và tag của nó, phân biệt heap với native memory, process CPU với system CPU, trạng thái gauge với counter tích lũy và dữ liệu có thể thiếu do giới hạn nền tảng. Kết hợp xu hướng GC, allocation, heap sau GC, CPU, thread và uptime để khoanh vùng vấn đề; sau đó dùng GC log, thread dump, heap dump hoặc profiler để xác nhận nguyên nhân. Metrics có sẵn tạo nền tảng quan sát runtime mà không cần tự viết instrumentation cho từng thông số JVM.
