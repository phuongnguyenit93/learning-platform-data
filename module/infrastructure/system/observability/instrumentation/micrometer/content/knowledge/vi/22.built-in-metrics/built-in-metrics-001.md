# Phép đo bộ nhớ JVM, vùng nhớ, luồng và bộ nạp lớp

Micrometer cung cấp các `MeterBinder` dựng sẵn để thu thập trạng thái của JVM mà không cần tự viết Gauge cho từng MXBean. Ba binder quan trọng trong bài này là `JvmMemoryMetrics`, `JvmThreadMetrics` và `ClassLoaderMetrics`. Chúng lấy dữ liệu từ các API quản lý JVM như `MemoryPoolMXBean`, `BufferPoolMXBean`, `ThreadMXBean` và `ClassLoadingMXBean`, rồi đăng ký các meter vào `MeterRegistry`.

Nhóm metrics này giúp trả lời những câu hỏi vận hành thường gặp:

- Heap và non-heap đang sử dụng bao nhiêu bộ nhớ?
- Pool nào đang tăng nhanh hoặc gần chạm giới hạn?
- Direct buffer đang chiếm bao nhiêu bộ nhớ ngoài heap?
- JVM hiện có bao nhiêu thread, chúng đang ở trạng thái nào?
- Số class đang được load và số class đã unload thay đổi ra sao?

Các phép đo là ảnh chụp trạng thái hoặc bộ đếm trong vòng đời JVM. Chúng giúp phát hiện xu hướng và xác định khu vực cần điều tra; khi cần tìm object giữ bộ nhớ, thread đang chặn hoặc classloader bị giữ lại, vẫn cần heap dump, thread dump và công cụ chẩn đoán JVM.

## 1. Các binder JVM có sẵn

Micrometer cung cấp các binder cho các nguồn dữ liệu JVM:

~~~java
new ClassLoaderMetrics().bindTo(registry);
new JvmMemoryMetrics().bindTo(registry);
new JvmThreadMetrics().bindTo(registry);
~~~

Các binder này thuộc package `io.micrometer.core.instrument.binder.jvm`. Mỗi binder đăng ký một nhóm meter có tên và tag ổn định:

| Binder | Nguồn dữ liệu chính | Nhóm phép đo |
|---|---|---|
| `JvmMemoryMetrics` | `MemoryPoolMXBean`, `BufferPoolMXBean` | Used, committed, max của memory pool; count và dung lượng buffer |
| `JvmThreadMetrics` | `ThreadMXBean` | Live, daemon, peak, started và số thread theo state |
| `ClassLoaderMetrics` | `ClassLoadingMXBean` | Số class hiện đang load và tổng số class đã unload |

Đây là các `MeterBinder`, không phải một bộ scheduler độc lập. Sau khi bind, registry đọc các giá trị Gauge khi thu thập hoặc xuất metrics. Những giá trị tích lũy như tổng thread đã khởi tạo hoặc class đã unload được biểu diễn bằng meter có ngữ nghĩa counter.

## 2. Tích hợp trong Spring Boot và Micrometer độc lập

### Spring Boot Actuator

Với Spring Boot Actuator, JVM metrics được auto-configure bằng các lớp Micrometer core. Các meter được đăng ký dưới namespace `jvm.`; ứng dụng thường không cần tự tạo lại ba binder này.

Dependency phổ biến:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Khi thêm registry exporter, ví dụ Prometheus, Spring Boot cấu hình registry tương ứng dựa trên dependency có trong runtime classpath. JVM binders được auto-configure cùng registry do ứng dụng quản lý.

Nếu ứng dụng đã dùng Spring Boot auto-configuration, không đăng ký thêm `new JvmMemoryMetrics()`, `new JvmThreadMetrics()` hoặc `new ClassLoaderMetrics()` thủ công chỉ để có cùng các meter. Đăng ký trùng có thể tạo cấu hình khó hiểu hoặc xung đột khi meter cùng tên và tag được tạo từ nhiều nơi.

### Micrometer độc lập

Với ứng dụng Java không dùng Spring Boot, hãy bind rõ ràng vào registry:

~~~java
MeterRegistry registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);

new JvmMemoryMetrics().bindTo(registry);
new JvmThreadMetrics().bindTo(registry);
new ClassLoaderMetrics().bindTo(registry);
~~~

Đoạn code cần dependency của registry cụ thể và `micrometer-core`. Trong ứng dụng độc lập, ứng dụng chịu trách nhiệm quản lý vòng đời registry và đóng các tài nguyên cần thiết khi shutdown.

## 3. Bộ nhớ JVM: used, committed và max

`JvmMemoryMetrics` duyệt các `MemoryPoolMXBean` mà JVM cung cấp và đăng ký ba Gauge chính:

| Meter | Ý nghĩa | Đơn vị |
|---|---|---|
| `jvm.memory.used` | Số byte đang được sử dụng trong memory pool | bytes |
| `jvm.memory.committed` | Số byte JVM đã commit và bảo đảm có thể dùng cho pool | bytes |
| `jvm.memory.max` | Giới hạn tối đa mà pool có thể dùng nếu JVM xác định được | bytes |

Mỗi meter dùng hai tag phổ biến:

- `area`: `heap` hoặc `nonheap`.
- `id`: tên memory pool do JVM cung cấp, ví dụ `G1 Eden Space`, `G1 Old Gen`, `Metaspace`, `CodeHeap 'profiled nmethods'`.

Ví dụ một chuỗi thời gian:

~~~text
jvm.memory.used{area="heap",id="G1 Old Gen"} 734003200
jvm.memory.committed{area="heap",id="G1 Old Gen"} 1073741824
jvm.memory.max{area="heap",id="G1 Old Gen"} 2147483648
~~~

Các giá trị trên chỉ là ví dụ minh họa. Tên pool, số lượng pool và giới hạn phụ thuộc JVM, garbage collector và cấu hình runtime.

### Used

`used` là phần bộ nhớ hiện đang được pool sử dụng. Giá trị này biến động khi ứng dụng cấp phát object và khi garbage collector thu hồi object không còn được tham chiếu.

Heap thường có các pool tương ứng với thế hệ hoặc vùng cấp phát:

- Eden: nơi phần lớn object mới được cấp phát.
- Survivor: nơi object sống sót qua một số chu kỳ thu gom được giữ lại.
- Old generation: nơi object sống lâu hơn được lưu giữ.

Tên và cách chia pool thay đổi theo garbage collector. ZGC, Shenandoah, G1 và các collector khác không nhất thiết dùng cùng tên hoặc cùng cấu trúc pool.

Non-heap thường gồm các vùng như:

- Metaspace: metadata của class.
- Compressed Class Space: metadata class được nén trên một số cấu hình JVM.
- Code Cache: mã máy được JIT compiler sinh ra.

Không gộp non-heap với heap khi phân tích. Một ứng dụng có thể còn nhiều heap nhưng vẫn gặp vấn đề Metaspace, Code Cache hoặc native memory.

### Committed

`committed` là lượng bộ nhớ JVM đã commit để pool có thể sử dụng. Đây không phải lượng object đang chiếm chỗ. JVM có thể commit thêm hoặc trả bớt bộ nhớ tùy collector và cấu hình.

Nếu `used` tăng nhưng `committed` còn tăng theo, JVM đang mở rộng vùng bộ nhớ đã commit để đáp ứng cấp phát. Nếu `used` tiến sát `committed` trong thời gian dài, áp lực cấp phát có thể tăng, nhưng cần xem thêm GC và giới hạn max.

### Max

`max` là giới hạn pool nếu JVM xác định được. Một số pool không có giới hạn được xác định; trong trường hợp đó giá trị có thể là `-1`. Không diễn giải `-1` thành bộ nhớ âm hoặc coi nó là một ngưỡng hợp lệ để tính phần trăm.

Khi tính tỷ lệ sử dụng, chỉ dùng mẫu số dương và có ý nghĩa. Với heap, tổng theo `area=heap` thường hữu ích nếu tất cả pool có max xác định. Với non-heap, cần kiểm tra từng pool vì một số pool có thể không có max.

## 4. Phân biệt heap, non-heap và native memory

Heap là vùng chính chứa object Java. Non-heap chứa các vùng quản lý runtime như Metaspace và Code Cache. Tuy nhiên, cả hai không đại diện cho toàn bộ bộ nhớ tiến trình.

Một ứng dụng Java còn có thể dùng:

- Direct NIO buffers.
- Thread stacks.
- Bộ nhớ native từ JNI hoặc thư viện bên thứ ba.
- Bộ nhớ nội bộ của JVM và garbage collector.
- Memory-mapped files.

Do đó, không nên kết luận tổng RSS của process bằng heap used cộng non-heap used. Các phép đo này có phạm vi khác nhau.

## 5. Buffer pool: direct và mapped

Trong cùng `JvmMemoryMetrics`, Micrometer cũng duyệt các `BufferPoolMXBean` và đăng ký:

| Meter | Ý nghĩa | Đơn vị |
|---|---|---|
| `jvm.buffer.count` | Số buffer trong pool | buffers |
| `jvm.buffer.memory.used` | Bộ nhớ JVM đang sử dụng cho buffer pool | bytes |
| `jvm.buffer.total.capacity` | Tổng capacity của các buffer | bytes |

Tag `id` thường phân biệt:

- `direct`: direct byte buffers, thường dùng cho I/O để giảm copy giữa heap và native I/O.
- `mapped`: memory-mapped buffers gắn với vùng file được ánh xạ vào bộ nhớ.

Direct buffer có thể chiếm native memory dù heap vẫn thấp. Nếu `jvm.buffer.memory.used` tăng đều nhưng `jvm.memory.used{area="heap"}` ổn định, cần xem xét việc ứng dụng hoặc thư viện tạo quá nhiều direct buffer, giữ buffer quá lâu hoặc sử dụng Netty/NIO.

Các meter buffer chỉ phản ánh những buffer pool mà JVM công bố qua `BufferPoolMXBean`; chúng không phải bộ đo toàn bộ native memory của process.

## 6. Đọc các meter bộ nhớ qua Spring Boot Actuator

Endpoint `metrics` có thể dùng để chẩn đoán tên meter và các tag hiện có. Endpoint này cần được expose trong cấu hình:

~~~properties
management.endpoints.web.exposure.include=health,metrics
~~~

Ví dụ truy vấn toàn bộ heap:

~~~text
GET /actuator/metrics/jvm.memory.used?tag=area:heap
~~~

Truy vấn riêng một pool:

~~~text
GET /actuator/metrics/jvm.memory.used?tag=area:nonheap&tag=id:Metaspace
~~~

Tên dùng trong endpoint Actuator là tên meter của Micrometer, ví dụ `jvm.memory.used`. Exporter có thể chuẩn hóa tên khác đi; Prometheus thường đổi dấu chấm thành dấu gạch dưới và thêm hậu tố đơn vị như `jvm_memory_used_bytes`.

Kết quả endpoint Actuator tổng hợp các measurement của những meter khớp tên và tag. Nếu chỉ lọc `area=nonheap`, giá trị có thể là tổng các pool non-heap. Thêm `id` khi cần phân tích một pool cụ thể.

Không expose endpoint chẩn đoán ra Internet mà không có xác thực và kiểm soát truy cập. Endpoint metrics có thể tiết lộ thông tin vận hành của ứng dụng.

## 7. Phân tích xu hướng heap

Một biểu đồ heap hữu ích nên hiển thị ít nhất:

- Heap used.
- Heap committed.
- Heap max nếu có giới hạn hợp lệ.
- GC pause hoặc các metric GC liên quan.

Ví dụ một truy vấn Prometheus tính tỷ lệ heap đang dùng trên tổng max có giá trị dương:

~~~promql
sum(jvm_memory_used_bytes{area="heap"})
/
sum(jvm_memory_max_bytes{area="heap"} > 0)
~~~

Tên metric Prometheus phụ thuộc naming convention của registry. Biểu thức giả định exporter đã chuẩn hóa `jvm.memory.used` và `jvm.memory.max` theo dạng trên. Nếu max của pool không được xác định, bộ lọc `> 0` loại các mẫu đó khỏi mẫu số.

Một xu hướng used tăng trong lúc ứng dụng hoạt động là bình thường. Điều cần chú ý là baseline sau các chu kỳ GC lớn:

- Nếu used giảm đáng kể sau GC và dao động quanh baseline ổn định, đó có thể là hành vi bình thường.
- Nếu baseline sau GC tăng dần qua nhiều chu kỳ, ứng dụng có thể đang giữ lại nhiều object hơn theo thời gian.
- Nếu used tiến sát max và GC diễn ra dày hơn, nguy cơ allocation failure hoặc OutOfMemoryError tăng.

Không kết luận memory leak chỉ từ một lần heap used tăng. Hãy quan sát đủ lâu, xem baseline sau GC, workload và heap dump khi cần.

## 8. Theo dõi pool và Metaspace

Để xem từng pool heap:

~~~promql
sum by (id) (jvm_memory_used_bytes{area="heap"})
~~~

Để xem từng pool non-heap:

~~~promql
sum by (id) (jvm_memory_used_bytes{area="nonheap"})
~~~

Metaspace tăng có thể liên quan đến việc load thêm class, tạo proxy hoặc classloader mới. Tuy nhiên, số class hiện đang load không trực tiếp bằng dung lượng Metaspace. Một class có thể cần lượng metadata khác nhau và các classloader có thể giữ class sống lâu hơn dự kiến.

Khi điều tra Metaspace tăng kéo dài, kết hợp:

- `jvm.memory.used{id="Metaspace"}`.
- `jvm.memory.committed{id="Metaspace"}`.
- `jvm.classes.loaded`.
- `jvm.classes.unloaded`.

Nếu class loaded tăng liên tục mà unloaded gần như không tăng, đây là tín hiệu cần tìm hiểu thêm, không phải bằng chứng độc lập về classloader leak. Kiểm tra số lượng classloader, plugin reload, hot deployment và heap dump để xác định classloader nào còn được tham chiếu.

## 9. Metrics thread của JVM

`JvmThreadMetrics` đọc dữ liệu từ `ThreadMXBean` và đăng ký các meter chính:

| Meter | Loại | Ý nghĩa |
|---|---|---|
| `jvm.threads.live` | Gauge | Số thread đang sống, gồm daemon và non-daemon |
| `jvm.threads.daemon` | Gauge | Số daemon thread đang sống |
| `jvm.threads.peak` | Gauge | Số thread sống cao nhất kể từ khi JVM khởi động hoặc peak được reset |
| `jvm.threads.started` | FunctionCounter | Tổng số thread đã được khởi tạo từ khi JVM bắt đầu |
| `jvm.threads.states` | Gauge | Số thread ở từng trạng thái, có tag `state` |

Các meter này thường không có tag phân biệt từng thread. Chúng tổng hợp toàn JVM để tránh tạo một chuỗi thời gian cho mỗi thread.

### Live, daemon và peak

`jvm.threads.live` phản ánh số thread hiện đang tồn tại. Số lượng cao không tự động có nghĩa là lỗi: server có thể có thread pool, scheduler, driver và worker threads.

`jvm.threads.daemon` là tập con của live threads. Daemon thread không ngăn JVM thoát khi tất cả non-daemon thread đã kết thúc; tuy vậy, daemon thread vẫn có thể tiêu thụ CPU, stack memory và tài nguyên.

`jvm.threads.peak` là đỉnh số thread kể từ lúc JVM bắt đầu hoặc kể từ lần reset peak. Vì vậy, peak có thể giữ nguyên dù live count đã giảm.

`jvm.threads.started` là bộ đếm tích lũy. Tốc độ tạo thread có thể được theo dõi bằng `rate()` ở backend hỗ trợ Prometheus:

~~~promql
rate(jvm_threads_started_threads_total[5m])
~~~

Nếu tốc độ tạo thread cao bất thường, hãy kiểm tra việc tạo thread không giới hạn, tạo executor liên tục hoặc thread pool không được tái sử dụng.

## 10. Thread state

`jvm.threads.states` đăng ký một Gauge cho mỗi giá trị `Thread.State`, với tag `state`. Các trạng thái Java gồm:

| State | Ý nghĩa vận hành |
|---|---|
| `new` | Thread đã được tạo nhưng chưa bắt đầu chạy |
| `runnable` | Thread đang thực thi hoặc sẵn sàng được scheduler cấp CPU |
| `blocked` | Thread đang chờ monitor lock để vào hoặc tiếp tục một vùng synchronized |
| `waiting` | Thread đang chờ vô thời hạn một điều kiện hoặc tín hiệu |
| `timed-waiting` | Thread đang chờ trong một khoảng thời gian giới hạn |
| `terminated` | Thread đã kết thúc |

Ví dụ truy vấn số thread theo state:

~~~promql
sum by (state) (jvm_threads_states_threads)
~~~

Tên Prometheus trong ví dụ là dạng đã được chuẩn hóa từ meter `jvm.threads.states`.

Diễn giải cần có ngữ cảnh:

- Nhiều thread `blocked` có thể chỉ ra tranh chấp monitor hoặc critical section kéo dài.
- Nhiều thread `waiting` có thể là worker đang chờ queue, condition hoặc I/O; trạng thái này không mặc nhiên là lỗi.
- Nhiều thread `timed-waiting` có thể đến từ sleep, timeout hoặc scheduler.
- Nhiều thread `runnable` cùng CPU cao có thể cho thấy CPU contention hoặc workload tính toán lớn.

Thread state là snapshot tại thời điểm lấy mẫu. Nó không cung cấp stack trace hoặc cho biết thread đang chờ lock nào. Khi thấy bất thường, lấy thread dump để xác định call stack, lock owner và chuỗi chờ.

## 11. Thread deadlock và virtual threads

Micrometer còn có `JvmThreadDeadlockMetrics` để theo dõi số thread bị deadlock. Đây là binder riêng; không nên giả định chỉ vì đã đăng ký `JvmThreadMetrics` thì deadlock metric cũng tự xuất hiện trong mọi cấu hình.

Với Java 21 trở lên, Micrometer có module `micrometer-java21` và binder `VirtualThreadMetrics`:

~~~java
new VirtualThreadMetrics().bindTo(registry);
~~~

Binder này theo dõi thời lượng và số sự kiện virtual thread bị pin, cùng các lỗi khi bắt đầu hoặc unpark virtual thread. Trên Java 24 trở lên, nếu JVM cung cấp `jdk.management.VirtualThreadSchedulerMXBean`, có thể có thêm metrics về parallelism, pool size và số virtual thread đang mounted hoặc queued.

`jvm.threads.live` của `ThreadMXBean` không nên được dùng làm số lượng virtual thread đang hoạt động trong ứng dụng. Hãy dùng binder virtual thread tương ứng nếu cần quan sát virtual thread và xác minh các metric có được hỗ trợ bởi JDK đang chạy.

## 12. Metrics của class loader

`ClassLoaderMetrics` đọc dữ liệu từ `ClassLoadingMXBean` và cung cấp hai góc nhìn:

| Meter | Ngữ nghĩa | Ý nghĩa |
|---|---|---|
| `jvm.classes.loaded` | Gauge | Số class hiện đang được load trong JVM |
| `jvm.classes.unloaded` | FunctionCounter | Tổng số class đã được unload kể từ khi JVM bắt đầu |

`jvm.classes.loaded` có thể tăng khi ứng dụng load class mới và giảm khi class được unload. `jvm.classes.unloaded` là tổng tích lũy, không phải số class đang unload tại thời điểm lấy mẫu.

Tốc độ unload có thể quan sát bằng:

~~~promql
rate(jvm_classes_unloaded_classes_total[5m])
~~~

Tên Prometheus có thể khác theo registry và naming convention. Hãy kiểm tra scrape output để xác định tên thực tế.

ClassLoaderMetrics lấy thống kê tổng hợp của JVM thông qua ClassLoadingMXBean, không tạo meter cho từng class hoặc từng classloader. Muốn xác định classloader nào giữ class, cần dùng công cụ chẩn đoán JVM hoặc phân tích heap dump.

## 13. Đọc tín hiệu class loading cùng Metaspace

Một số mẫu hình có thể giúp định hướng điều tra:

| Quan sát | Câu hỏi tiếp theo |
|---|---|
| Loaded classes tăng trong giai đoạn startup rồi ổn định | Đây có thể là quá trình warm-up bình thường |
| Loaded classes tăng liên tục sau mỗi lần reload plugin | Classloader cũ có được giải phóng không? |
| Metaspace used tăng nhưng loaded class count ổn định | Metadata, proxy hoặc classloader nào đang giữ vùng nhớ? |
| Unloaded class counter tăng sau khi module dừng | Việc unload đang diễn ra; kiểm tra xu hướng dài hạn |
| Loaded count và Metaspace cùng tăng qua nhiều giờ | Có thể có dynamic class loading hoặc classloader giữ tham chiếu |

Đừng dùng một metric đơn lẻ để khẳng định classloader leak. Số class hiện tại có thể ổn định trong khi Metaspace vẫn tăng do metadata hoặc classloader khác nhau. Kết hợp class count, unload count, Metaspace và heap dump.

## 14. Dashboard và truy vấn Prometheus

Một dashboard nền tảng có thể chia thành ba hàng.

**Bộ nhớ**

~~~promql
sum by (area) (jvm_memory_used_bytes)
~~~

~~~promql
sum by (id) (jvm_memory_used_bytes{area="heap"})
~~~

~~~promql
sum by (id) (jvm_buffer_memory_used_bytes)
~~~

**Thread**

~~~promql
jvm_threads_live_threads
~~~

~~~promql
sum by (state) (jvm_threads_states_threads)
~~~

~~~promql
rate(jvm_threads_started_threads_total[5m])
~~~

**Class loading**

~~~promql
jvm_classes_loaded_classes
~~~

~~~promql
rate(jvm_classes_unloaded_classes_total[5m])
~~~

Đây là các tên phổ biến theo Prometheus naming convention. Nếu dùng registry hoặc convention khác, cần xem tên metric và tag thực tế. Không sao chép tên Prometheus đã chuẩn hóa vào selector của Actuator; Actuator dùng tên Micrometer có dấu chấm.

## 15. Tùy chỉnh binder và tag

Các binder JVM cho phép thêm tag chung hoặc tùy chỉnh convention theo phiên bản Micrometer. Ví dụ, một số phiên bản có builder cho `JvmMemoryMetrics`, `JvmThreadMetrics` và `ClassLoaderMetrics`; các API convention mới hơn có thể thay đổi giữa các phiên bản.

Nếu chỉ cần thêm tag cho binder, hãy dùng constructor hoặc builder được phiên bản đang dùng hỗ trợ:

~~~java
Iterable<Tag> commonTags = Tags.of(
        "application", "catalog-service",
        "environment", "production"
);

new JvmMemoryMetrics(commonTags).bindTo(registry);
new JvmThreadMetrics(commonTags).bindTo(registry);
new ClassLoaderMetrics(commonTags).bindTo(registry);
~~~

Đoạn code dùng constructor nhận `Iterable<Tag>` có trên các phiên bản Micrometer hỗ trợ API đó. Kiểm tra Javadoc của phiên bản dự án trước khi dùng builder hoặc convention mới.

Không thêm tag như thread ID, class name, classloader identity hoặc request ID. Những tag đó có thể tạo cardinality rất cao và không phù hợp với metrics tổng hợp JVM.

## 16. Chi phí thu thập và giới hạn nền tảng

Các binder đọc MXBean khi registry lấy mẫu. Phần lớn phép đo là Gauge đơn giản, nhưng việc đếm thread theo state có thể cần duyệt danh sách thread và lấy ThreadInfo. Ứng dụng có số thread rất lớn nên đánh giá tần suất scrape và overhead thực tế.

Một số phép đo chỉ tồn tại nếu JVM hoặc hệ điều hành cung cấp MXBean tương ứng. Tên pool, buffer pool và số thread cũng khác nhau giữa môi trường. Vì vậy:

- Không hard-code danh sách pool theo một garbage collector.
- Không giả định mọi JVM có cùng buffer pool.
- Không giả định mọi nền tảng hỗ trợ toàn bộ thread-management operations.
- Không coi một meter vắng mặt là số 0 nếu binder hoặc MXBean không cung cấp meter đó.
- Dùng cùng một phiên bản JDK và cấu hình collector khi so sánh baseline giữa môi trường.

## 17. Kiểm thử binder với SimpleMeterRegistry

Trong unit test, có thể bind ba binder vào registry trong bộ nhớ rồi xác minh meter được đăng ký:

~~~java
class JvmBuiltInMetricsTest {
    @Test
    void registersMemoryThreadAndClassLoaderMeters() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        new JvmMemoryMetrics().bindTo(registry);
        new JvmThreadMetrics().bindTo(registry);
        new ClassLoaderMetrics().bindTo(registry);

        assertThat(registry.find("jvm.memory.used").gauges()).isNotEmpty();
        assertThat(registry.find("jvm.threads.live").gauge()).isNotNull();
        assertThat(registry.find("jvm.classes.loaded").gauge()).isNotNull();
    }
}
~~~

Các giá trị cụ thể phụ thuộc JVM đang chạy test, vì vậy unit test nên xác minh meter tồn tại và có giá trị hợp lệ theo môi trường thay vì hard-code dung lượng heap hoặc số thread.

Với class unload counter, test không nên kỳ vọng một class cụ thể được unload trong thời gian chạy ngắn. Garbage collection và class unloading phụ thuộc JVM, collector, classloader và khả năng thu hồi tham chiếu. Kiểm thử loại meter và nguồn dữ liệu là đủ cho unit test binder.

Nếu cần xác minh output Prometheus, dùng `PrometheusMeterRegistry` và kiểm tra scrape text. Unit test bằng SimpleMeterRegistry không xác nhận naming convention hoặc format của exporter.

## 18. Các lỗi thường gặp

**Coi heap used là toàn bộ bộ nhớ process.** Heap không bao gồm toàn bộ non-heap và native memory. Theo dõi thêm Metaspace, Code Cache và buffer pool.

**Coi committed là used.** Committed là bộ nhớ JVM đã commit để pool có thể sử dụng; used là phần đang được dùng.

**Tính phần trăm khi max bằng -1.** Một số pool không có max xác định. Loại mẫu không hợp lệ khỏi phép chia và xem xét từng pool.

**Gộp mọi pool rồi kết luận pool nào gây áp lực.** Tổng theo area giúp nhìn tổng quan; thêm tag `id` để xác định pool cụ thể.

**Coi direct buffer là heap.** Direct và mapped buffer được đo riêng qua `jvm.buffer.*`; chúng không nằm trong heap used.

**Coi mọi thread waiting là thread bị treo.** Waiting và timed-waiting có thể là hành vi bình thường của worker hoặc scheduler. Dùng thread dump để xác định nguyên nhân.

**Dùng peak thay cho live.** Peak giữ giá trị cao nhất kể từ khi JVM khởi động hoặc reset; live phản ánh số thread hiện tại.

**Coi loaded class count là tổng số class từng được load.** Loaded là số class đang hiện diện; unloaded là tổng số class đã được unload.

**Đăng ký binder thủ công thêm vào Spring Boot.** JVM binders đã được auto-configure trong cấu hình Actuator thông thường. Kiểm tra registry trước khi bind thủ công.

**So sánh metric giữa JDK hoặc collector khác nhau mà không xét pool.** Pool name và cách quản lý bộ nhớ thay đổi theo runtime; so sánh theo ý nghĩa và tag thay vì giả định danh sách pool giống nhau.

## 19. Checklist vận hành

Khi triển khai built-in JVM metrics, hãy xác minh:

- [ ] Spring Boot Actuator đã auto-configure JVM binders hoặc ứng dụng độc lập đã bind đúng ba binder.
- [ ] Không đăng ký binder trùng với cấu hình auto-configuration.
- [ ] Dashboard phân biệt heap, non-heap và buffer memory.
- [ ] Used, committed và max được hiểu đúng ngữ nghĩa.
- [ ] Giá trị max không xác định được xử lý riêng.
- [ ] Memory pool được lọc theo `area` và `id`.
- [ ] Thread dashboard hiển thị live, daemon, peak và state.
- [ ] Thread state bất thường được điều tra bằng thread dump.
- [ ] Class loaded và class unloaded được xem như hai đại lượng khác nhau.
- [ ] Metaspace được theo dõi cùng class loading khi điều tra classloader.
- [ ] Tên meter thực tế được xác minh qua Actuator hoặc scrape output.
- [ ] Tần suất thu thập phù hợp với số lượng pool và thread của JVM.

## 20. Kết luận

`JvmMemoryMetrics`, `JvmThreadMetrics` và `ClassLoaderMetrics` cung cấp nền tảng quan sát JVM bằng các meter có sẵn. Memory binder cho biết used, committed và max theo từng pool, đồng thời theo dõi buffer pool. Thread binder cho biết số thread hiện tại, peak, daemon, tổng số đã bắt đầu và phân bố theo state. Class loader binder cho biết số class hiện đang load và tổng số đã unload.

Trong Spring Boot Actuator, các JVM metrics thường được auto-configure. Với ứng dụng Micrometer độc lập, bind các binder vào registry một lần. Khi phân tích, hãy giữ đúng ngữ nghĩa của từng meter, lọc theo tag `area`, `id` và `state`, đồng thời đối chiếu xu hướng với GC, heap dump hoặc thread dump. Các số đo này giúp khoanh vùng vấn đề bộ nhớ, thread và class loading mà không tạo thêm instrumentation thủ công cho từng MXBean.

## Tài liệu tham khảo

- [Micrometer – JVM Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Spring Boot – Metrics and JVM Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [OpenJDK – ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Java – MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html)
- [Java – ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Java – ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html)
