# JFR, JMX và tương thích với công cụ giám sát

Trong chủ đề **Java Advance Compatibility Migration**, nâng JDK không chỉ làm thay đổi bytecode, thư viện và hành vi của ứng dụng. Nó còn có thể thay đổi **những gì hệ thống giám sát nhìn thấy**: tên bộ thu gom rác, tập MBean, thuộc tính JMX, loại sự kiện JFR, đơn vị đo, cách các tool kết nối tới JVM hoặc cách JVM nhận biết CPU và bộ nhớ trong container.

Bài học thuộc chương **JVM và hiệu năng**. Mục tiêu là hiểu hai cơ chế quan sát quan trọng của Java — **Java Flight Recorder (JFR)** và **Java Management Extensions (JMX)** — rồi thiết kế một quá trình migration sao cho dashboard, alert, profiler và công cụ vận hành vẫn đưa ra kết luận đúng sau khi runtime thay đổi.

Một lỗi đặc biệt nguy hiểm không phải là ứng dụng ngừng chạy, mà là **ứng dụng vẫn chạy nhưng hệ thống giám sát bị mù**: exporter không đọc được MBean, alert không còn dữ liệu, dashboard hiển thị 0 thay cho missing, hoặc cùng một tên metric nhưng ý nghĩa đã khác khi chuyển GC.

Các ví dụ tập trung vào ứng dụng Java hiện đại và HotSpot thường gặp. **Tính sẵn có, event metadata, MXBean mở rộng và tính năng của từng lệnh phụ thuộc JDK vendor, release, image và cấu hình runtime.** Khi triển khai thực tế cần kiểm tra bằng chính artifact sẽ chạy trong production.

## 1. JFR, JMX và các lớp quan sát khác nhau

### 1.1. JMX: trạng thái và thao tác quản lý

**Java Management Extensions (JMX)** cung cấp hạ tầng để chương trình và công cụ quản trị quan sát hoặc tác động lên thành phần runtime thông qua **MBean**.

Các thông tin thường có:

- Trạng thái heap và non-heap memory.
- Thread count và một số dữ liệu về CPU của thread.
- Thống kê garbage collection.
- Class loading.
- Compilation và memory pools.
- Thuộc tính cấu hình ứng dụng do đội phát triển tự công bố.
- Operation quản trị như bật/tắt một tính năng, nếu MBean có cung cấp và quyền truy cập cho phép.

JMX phù hợp với việc **lấy mẫu trạng thái hoặc counter theo chu kỳ**, ví dụ mỗi 15 hoặc 30 giây.

### 1.2. JFR: dòng sự kiện và dữ liệu chẩn đoán theo thời gian

**Java Flight Recorder (JFR)** là công nghệ thu thập sự kiện với overhead được thiết kế để phù hợp cho nhiều tình huống ghi nhận trên hệ thống đang chạy, tùy cấu hình và tần suất sự kiện.

Ví dụ sự kiện:

- Một lần garbage collection xảy ra.
- Hoạt động phân bổ đối tượng.
- Mẫu thực thi CPU.
- Thread bị chặn khi vào monitor.
- Đọc/ghi file hoặc socket.
- Class loading hoặc code compilation.
- Sự kiện ứng dụng tự định nghĩa.

JFR giúp trả lời câu hỏi **điều gì đã diễn ra trong khoảng thời gian đó**, thay vì chỉ biết một giá trị heap được lấy mẫu tại một thời điểm.

### 1.3. Monitoring, profiling và tracing không giống nhau

| Nhu cầu | JMX | JFR | Phương tiện khác |
|---|---|---|---|
| Đọc heap usage định kỳ | Phù hợp | Có thể dùng event | Metrics exporter |
| Theo dõi GC count/time | Thường dùng MXBean | Có sự kiện GC chi tiết | GC logs |
| Phân tích CPU hotspot | Không phải mục đích chính | Có execution samples | Async profiler |
| Phân tích latency end-to-end | Giới hạn | Có sự kiện hỗ trợ, cần ngữ cảnh | Distributed tracing |
| Alert threshold theo chu kỳ | Phù hợp qua exporter | Cần pipeline chuyển thành metric | Prometheus/OTel |
| Điều tra incident quá khứ | Chỉ có nếu metric đã lưu | Recording có timeline chi tiết | Logs/traces |
| Quản trị runtime qua MBean | Có thể | Không phải mục đích chính | Management API |
| Profiling với stack trace | Giới hạn | Có thể ghi stack trace theo event | Profiling tools |

Một kiến trúc observability tốt thường kết hợp nhiều nguồn thay vì ép JFR thay JMX hoặc ngược lại.

### 1.4. Sơ đồ tổng thể

~~~text
Ứng dụng Java + JVM
       |
       +--> JMX / MXBeans --> JMX Exporter --> Time-series DB --> Dashboard/Alert
       |
       +--> JFR events ----> .jfr recording --> JMC / jfr CLI / phân tích
       |              |
       |              +--> RecordingStream --> pipeline quan sát
       |
       +--> Application metrics --> Micrometer / OpenTelemetry --> Backend
       |
       +--> GC logs / application logs ------------------------> Log storage
       |
       +--> Distributed traces -------------------------------> Trace backend
~~~

Dữ liệu từ các nhánh có thể hỗ trợ nhau khi điều tra, nhưng **không nên giả định các phép đo là hoàn toàn tương đương**. Ví dụ thời gian GC từ JMX và tổng duration của các event JFR có thể khác phạm vi, cách tính và thời điểm cập nhật.

## 2. Điều gì có thể thay đổi khi nâng JDK?

Một migration có thể đổi nhiều thành phần cùng lúc:

1. JDK runtime và vendor.
2. GC algorithm hoặc default GC selection.
3. Kiểu heap, memory pool và cách đặt tên GC MBeans.
4. JFR events, metadata, settings và khả năng thu thập.
5. Command-line syntax hoặc tool package được cung cấp trong JDK image.
6. Module availability khi dùng **jlink**.
7. Cấu hình security, attach, RMI hoặc network.
8. Container CPU/memory accounting.
9. JMX exporter, JMC, profiler, Java agent và phiên bản dependency.
10. Cấu trúc metric name/labels qua exporter.
11. Dashboard và alert phụ thuộc trực tiếp vào các tên/đơn vị đo cũ.
12. Thời gian startup và mức tải do instrumentation gây ra.

### 2.1. Ma trận rủi ro

| Thay đổi | Tác động lên giám sát | Hướng kiểm chứng |
|---|---|---|
| Thay JDK/HotSpot build | Event/attribute và runtime flags có thể khác | So sánh discovery trên hai runtime |
| Thay GC từ G1 sang ZGC | GC MBean, event và semantics đổi | Không dựa vào tên collector cố định |
| Dùng jlink image tối giản | Thiếu module/tool cần cho JFR hoặc JMX | Kiểm tra module graph/runtime image |
| Deploy vào container | PID namespace, cgroup metrics, file path khác | Test trên image và orchestration thật |
| Tăng quyền bảo mật | JMX remote hoặc attach có thể bị chặn | Xác thực và kiểm thử quyền truy cập |
| Nâng exporter/agent | Metric names, labels, rule mapping đổi | Diff output scrape trước/sau |
| Đổi dashboard | Query không còn khớp series | Kiểm thử panel, rule và absence detection |
| Bật JFR profile liên tục | Overhead/dung lượng tăng tùy events | Đo dưới tải đại diện |
| Đổi sampling interval | Rate và độ nhạy alert thay đổi | Kiểm tra bước lấy mẫu và cửa sổ đánh giá |

Điều quan trọng không phải cố giữ mọi chi tiết implementation của JVM, mà giữ được **các tín hiệu vận hành mà hệ thống đã cam kết dùng để phát hiện sự cố**.

## 3. JFR: kiến trúc và khái niệm quan trọng

JFR là công nghệ ghi nhận sự kiện tích hợp với HotSpot. Từ **JDK 11**, JFR được cung cấp trong OpenJDK theo **JEP 328**. Các release và runtime khác có thể có mức hỗ trợ riêng; cần xác minh trên bản JDK đang chạy.

Các khái niệm:

- **Event:** một loại thông tin được ghi nhận, ví dụ jdk.GarbageCollection.
- **Event type:** tên, field, annotation, category và metadata của event.
- **Recording:** một lần ghi nhận có cấu hình, thời điểm bắt đầu/kết thúc và dữ liệu.
- **Settings:** cấu hình event nào được bật, ngưỡng duration, period hoặc stack trace.
- **.jfr file:** file recording để phân tích.
- **JDK Mission Control (JMC):** công cụ GUI thường dùng để phân tích recording.
- **jfr CLI:** công cụ dòng lệnh xem summary, print và metadata.
- **RecordingStream:** API cho phép tiêu thụ một số sự kiện JFR đang được phát từ JVM.

### 3.1. Phân loại event

| Loại thông tin | Event minh họa | Công dụng |
|---|---|---|
| JVM CPU | **jdk.CPULoad** | Nhìn CPU load theo thời gian |
| GC | **jdk.GarbageCollection** | Xác định hoạt động GC |
| Heap | **jdk.GCHeapSummary** | Phân tích heap tại các mốc liên quan |
| Execution sampling | **jdk.ExecutionSample** | Tìm vùng code sử dụng CPU theo mẫu |
| Allocation | **jdk.ObjectAllocationSample** | Quan sát xu hướng allocation |
| Synchronization | **jdk.JavaMonitorEnter** | Điều tra thời gian chờ monitor |
| File I/O | Các sự kiện file read/write được runtime hỗ trợ | Nhìn độ trễ và kích thước I/O |
| Socket I/O | Các sự kiện socket read/write được runtime hỗ trợ | Điều tra network operations |

Tên event ở bảng mang tính minh họa phổ biến trên HotSpot. **Không nên hardcode danh sách này mà bỏ qua metadata của runtime mục tiêu**. Event có thể thay đổi trạng thái kích hoạt, field, subtype hoặc khả năng hỗ trợ theo JDK/vendor.

### 3.2. Recording không nhất thiết giống profiler chạy toàn lực

JFR thu thập nhiều loại dữ liệu với chi phí khác nhau. Một số event được ghi ở tần suất thấp hoặc dùng sampling; một số khác có thể tạo volume lớn nếu bật quá chi tiết.

Phải phân biệt:

- **default settings:** thường phù hợp để ghi nhận thông tin tổng quan với chi phí thấp hơn.
- **profile settings:** thường bật thêm thông tin phục vụ profiling và có thể tăng overhead.
- **custom settings:** điều chỉnh event, period, threshold, stack trace theo yêu cầu.

Một recording ngắn dùng cấu hình profile để điều tra incident không đồng nghĩa phù hợp chạy liên tục dưới mọi lưu lượng.

## 4. Dùng jcmd để ghi JFR

**jcmd** hỗ trợ gửi diagnostic commands tới JVM HotSpot mà người gọi có quyền tương ứng. Nó thường được cung cấp trong JDK distribution; một runtime image tối giản có thể không đi kèm executable này.

### 4.1. Khảo sát process

~~~bash
jcmd -l
~~~

Lệnh trả về JVM process mà công cụ có thể nhìn thấy và kết nối. Trong container, PID namespace và quyền thực thi có thể ảnh hưởng kết quả.

### 4.2. Bắt đầu recording

~~~bash
jcmd 12345 JFR.start \
  name=migration_check \
  settings=default \
  duration=2m \
  filename=/tmp/migration-check.jfr
~~~

Giả định **12345** là PID thực tế và runtime hỗ trợ các command này. Trên Windows có thể viết tất cả arguments trong một dòng.

Ý nghĩa:

- **name**: tên để quản lý recording.
- **settings=default**: sử dụng cấu hình event mặc định.
- **duration=2m**: giới hạn thời gian.
- **filename**: nơi ghi file kết quả.

Đường dẫn phải có quyền ghi trong filesystem của process/container. Trong môi trường orchestrated, file có thể bị mất khi pod bị thay thế; cần quy trình lưu trữ artifact theo chính sách bảo mật.

### 4.3. Kiểm tra trạng thái và dump

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=migration_check filename=/tmp/diagnostic.jfr
~~~

**JFR.dump** giúp lấy snapshot của recording đang hoạt động. Nếu recording đã tự dừng và được cấu hình file đầu ra, cần kiểm tra artifact tại nơi đã chỉ định.

### 4.4. Dừng recording

~~~bash
jcmd 12345 JFR.stop name=migration_check
~~~

Không nên để nhiều recording profile chạy không chủ đích trên cùng process. Ghi nhận ai bật, mục đích, duration, dung lượng dự kiến và cách thu hồi file.

### 4.5. Ghi từ lúc JVM khởi động

Một ví dụ JVM option:

~~~bash
java \
  -XX:StartFlightRecording=name=startup,settings=default,duration=120s,filename=/tmp/startup.jfr \
  -jar app.jar
~~~

Phù hợp khi cần quan sát startup hoặc lỗi xảy ra trước khi có thể attach **jcmd**. Cấu hình phải phù hợp Java launcher thực tế, container filesystem và mục tiêu bảo mật.

## 5. Đọc và phân tích recording bằng jfr CLI

JFR recording có thể được phân tích offline. Không cần mở JMX remote chỉ để đọc file .jfr đã thu thập.

### 5.1. Tóm tắt recording

~~~bash
jfr summary /tmp/migration-check.jfr
~~~

Dùng để xem thông tin chung, các loại event và số lượng bản ghi.

### 5.2. Lọc event cần quan tâm

~~~bash
jfr print \
  --events jdk.CPULoad,jdk.GarbageCollection \
  /tmp/migration-check.jfr
~~~

Khi phân tích, cần tránh kết luận chỉ từ event count. Một GC có duration khác nhau, hoặc event được enable với threshold khác, sẽ không tạo số lượng so sánh trực tiếp có ý nghĩa.

### 5.3. Xem metadata

~~~bash
jfr metadata /tmp/migration-check.jfr
~~~

Metadata rất quan trọng trong migration vì nó mô tả **event types và fields tồn tại trong recording thực tế**. Khi nâng JDK, không nên giả định một field mà parser cũ sử dụng vẫn có cùng tên và type.

### 5.4. JDK Mission Control (JMC)

JMC cung cấp giao diện phân tích timeline, threads, GC, allocation và code execution. JMC là công cụ có version và mức hỗ trợ riêng. Một bản JMC cũ có thể không hiểu đầy đủ metadata/event schema do JDK mới sinh ra.

Khi migration:

1. Ghi JDK tạo recording.
2. Ghi JMC version dùng để mở.
3. Mở recording baseline và target.
4. Kiểm tra các trang báo cáo quan trọng còn hoạt động.
5. Nếu UI không hiển thị một event, đối chiếu **jfr summary/metadata** trước khi kết luận runtime không tạo event.
6. Nâng JMC lên bản hỗ trợ recording của JDK target khi cần.

**Khả năng mở file .jfr** không đồng nghĩa mọi biểu đồ/heuristic trong công cụ sẽ có cùng ý nghĩa khi đổi collector hoặc event version.

## 6. JFR API trong ứng dụng Java

JDK cung cấp API **jdk.jfr** để tạo recording theo chương trình.

Ví dụ:

~~~java
package example.monitoring;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Recording;

public final class JfrRecordingExample {
    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.setName("sample");
            recording.enable("jdk.ExecutionSample")
                .withPeriod(Duration.ofMillis(20));

            recording.start();

            runWorkload();

            recording.stop();
            recording.dump(Path.of("sample.jfr"));
        }
    }

    private static void runWorkload() throws InterruptedException {
        Thread.sleep(1_000);
    }
}
~~~

Với modular application, module sử dụng API này cần phụ thuộc module **jdk.jfr** theo cách phù hợp:

~~~java
module example.monitoring {
    requires jdk.jfr;
}
~~~

Trong runtime image tùy biến bằng **jlink**, module này có thể bị lược bỏ. Không thể chỉ thêm Maven dependency để thay thế một JDK runtime module không có trong image; cần điều chỉnh runtime packaging.

### 6.1. Custom events cho nghiệp vụ

Có thể tạo event riêng để ghi một thao tác có ý nghĩa:

~~~java
package example.monitoring;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("com.example.OrderProcessed")
@Label("Order Processed")
@Category({"Application", "Orders"})
public final class OrderProcessedEvent extends Event {
    @Label("Status")
    public String status;

    @Label("Item Count")
    public int itemCount;
}
~~~

Sử dụng:

~~~java
public void processOrder() {
    OrderProcessedEvent event = new OrderProcessedEvent();
    event.begin();
    try {
        // Thực hiện nghiệp vụ.
        event.status = "SUCCESS";
        event.itemCount = 3;
    } catch (RuntimeException ex) {
        event.status = "ERROR";
        throw ex;
    } finally {
        event.end();
        if (event.shouldCommit()) {
            event.commit();
        }
    }
}
~~~

Các class này được hiểu là ở cùng package hoặc có import tương ứng.

**Lưu ý thiết kế:**

- Không ghi token, password, thông tin khách hàng hoặc nội dung request nhạy cảm vào event.
- Đừng biến mỗi request thành nhiều event có stack trace nếu không đo overhead.
- Định nghĩa event name, category và các fields ổn định cho pipeline đang sử dụng.
- Không dùng một event field để chứa dữ liệu có cardinality quá lớn nếu downstream biến nó thành label metric.
- Nếu đổi ý nghĩa field, cân nhắc event version hoặc quy tắc chuyển đổi rõ ràng.

### 6.2. Custom event cũng là hợp đồng

Giả sử một pipeline lọc **com.example.OrderProcessed** và đọc field **itemCount**. Nếu ứng dụng đổi tên thành **numberOfItems** mà không cập nhật parser, pipeline có thể bỏ dữ liệu.

Đây là **data compatibility của telemetry**. Dù ứng dụng vẫn hoạt động, công cụ giám sát có thể mất một phần tín hiệu.

## 7. JFR Event Streaming

Từ JDK 14, **JEP 349** cung cấp JFR Event Streaming. API như **jdk.jfr.consumer.RecordingStream** có thể nhận event theo thời gian thực hoặc gần thời gian thực trong cùng JVM.

Ví dụ:

~~~java
package example.monitoring;

import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

public final class JfrStreamExample {
    public static void main(String[] args) throws Exception {
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                .withPeriod(Duration.ofSeconds(1));

            stream.onEvent("jdk.CPULoad", event -> {
                float jvmUser = event.getFloat("jvmUser");
                System.out.println("JVM user CPU load: " + jvmUser);
            });

            stream.startAsync();
            Thread.sleep(10_000);
        }
    }
}
~~~

Ví dụ minh họa API; event field và availability cần đối chiếu metadata/runtime mục tiêu.

### 7.1. Không dùng streaming để thay mọi loại metrics

Streaming phù hợp khi cần phản ứng với JFR events, nhưng một pipeline monitoring phải cân nhắc:

- Độ trễ delivery.
- Event volume.
- Sampling period và loss.
- Backpressure hoặc downstream chậm.
- Lifecycle của stream.
- Bảo vệ dữ liệu nhạy cảm.
- Chi phí chuyển event thành metric/tracing.
- Khả năng phục hồi khi JVM restart.

Nếu mục tiêu chỉ là lấy heap usage mỗi 30 giây, đọc MXBean hoặc dùng exporter có thể đơn giản hơn.

### 7.2. Schema của event cần được kiểm chứng

Code gọi trực tiếp:

~~~java
event.getFloat("jvmUser");
~~~

đang phụ thuộc vào field tên **jvmUser** có kiểu tương thích. Nếu JDK/vendor đổi event metadata hoặc event bị tắt, pipeline có thể không nhận dữ liệu hoặc ném exception.

Với collector/parser ngoài process, nên có bước **đọc metadata và kiểm tra event fields** khi khởi tạo hoặc trong bộ kiểm thử tương thích, thay vì im lặng bỏ qua tất cả lỗi.

## 8. JMX: MBean Server, ObjectName và thuộc tính

JMX cung cấp mô hình quản lý dựa trên **MBeans**.

Các thành phần:

- **MBean Server:** nơi đăng ký và truy vấn MBeans.
- **ObjectName:** tên định danh một MBean, có dạng domain và key properties.
- **Attribute:** giá trị có thể đọc/ghi theo quyền.
- **Operation:** thao tác quản trị được công bố.
- **Notification:** sự kiện quản trị có thể phát ra từ một MBean.
- **JMX Connector:** đường kết nối để công cụ từ xa truy cập MBean server.

Ví dụ ObjectName tiêu chuẩn:

~~~text
java.lang:type=Memory
java.lang:type=Threading
java.lang:type=ClassLoading
java.lang:type=Runtime
java.lang:type=OperatingSystem
java.lang:type=GarbageCollector,name=*
java.lang:type=MemoryPool,name=*
~~~

Tên **GarbageCollector** và **MemoryPool** phụ thuộc collector và JVM implementation. Việc wildcard theo ObjectName phù hợp hơn hardcode một tên collector trong mọi rule.

### 8.1. Platform MXBeans

Java cung cấp các interface tiêu chuẩn trong **java.lang.management**:

- **MemoryMXBean**
- **ThreadMXBean**
- **RuntimeMXBean**
- **ClassLoadingMXBean**
- **OperatingSystemMXBean**
- **GarbageCollectorMXBean**
- **MemoryPoolMXBean**
- **CompilationMXBean** nếu môi trường hỗ trợ
- **ManagementFactory** để lấy các beans

**java.management** là module chuẩn cung cấp các API này. Các extension có thể nằm trong module và package khác, chẳng hạn phần phụ thuộc HotSpot/vendor.

### 8.2. Sử dụng MXBean nội bộ JVM

Ví dụ:

~~~java
package example.monitoring;

import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

public final class JmxLocalExample {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();

        System.out.println("Heap used: " + heap.getUsed());
        System.out.println("Heap committed: " + heap.getCommitted());
        System.out.println("Heap max: " + heap.getMax());

        for (GarbageCollectorMXBean gc :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            System.out.println(
                gc.getName() + " collections=" + gc.getCollectionCount()
                    + " time(ms)=" + gc.getCollectionTime()
            );
        }
    }
}
~~~

Một số thống kê có thể trả về **-1** khi JVM không hỗ trợ giá trị cụ thể. Ứng dụng monitoring phải coi đó là **unknown/not supported**, không tự động coi là 0.

**Collection time** trong MXBean không nhất thiết là tổng thời gian JVM ngừng toàn bộ ứng dụng (stop-the-world) dưới mọi collector. Nó là thống kê theo implementation và có thể khác cách người đọc diễn giải tổng GC pause.

### 8.3. ThreadMXBean và capability checking

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean threads = ManagementFactory.getThreadMXBean();

System.out.println("Threads: " + threads.getThreadCount());

if (threads.isThreadCpuTimeSupported()) {
    if (!threads.isThreadCpuTimeEnabled()) {
        System.out.println("Thread CPU time disabled");
    } else {
        long cpuNanos =
            threads.getThreadCpuTime(Thread.currentThread().getId());
        System.out.println("Current thread CPU ns: " + cpuNanos);
    }
}
~~~

Khi dùng thread CPU time, phải xác định JVM có hỗ trợ và đang bật hay không. Không dựa vào một giá trị -1 hoặc empty sample rồi gắn nhãn lỗi hiệu năng mà chưa kiểm tra capability.

### 8.4. JVM/vendor-specific MXBeans

Có các API mở rộng như **com.sun.management.OperatingSystemMXBean** hoặc các MBeans của HotSpot. Một số công cụ khai thác chúng để lấy CPU load, thread allocation hoặc diagnostics.

Nhưng không nên nhầm:

- **API chuẩn Java Management:** có hợp đồng được mô tả trong Java SE.
- **MXBean mở rộng của JDK/vendor:** mức hỗ trợ có thể khác nhau.
- **MBean do framework/ứng dụng đăng ký:** chịu lifecycle và version của framework.
- **MBean exporter:** ánh xạ dữ liệu vào định dạng ngoài JVM, có rule và version riêng.

Nếu pipeline chỉ hoạt động khi MBean thuộc **com.sun.management** tồn tại, đó là một giả định về JDK implementation cần ghi rõ trong support matrix.

## 9. Vì sao đổi GC có thể phá dashboard?

Giả sử dashboard đang truy vấn series chỉ dành cho G1:

~~~text
java.lang:type=GarbageCollector,name=G1 Young Generation
~~~

Khi chuyển sang collector khác, MBean với tên này có thể không còn. Ứng dụng vẫn chạy, nhưng biểu đồ có thể mất series.

Tương tự, tên các memory pool có thể khác:

- G1 có các pool liên quan tới G1 Eden, Survivor, Old Generation.
- Collector khác có thể công bố tên và cấu trúc pool khác.
- Metaspace, Code Cache hoặc pool riêng tùy implementation có cách phân chia/đặt tên khác nhau.

### 9.1. Không dùng tên memory pool cố định làm tổng heap

Một rule chỉ cộng pool có tên quen thuộc có thể bỏ sót pool ở JVM target. Nếu muốn giám sát **total heap used**, ưu tiên một nguồn có semantics tổng heap rõ như **MemoryMXBean.getHeapMemoryUsage().getUsed()**, rồi dùng pool metrics để phân tích chi tiết.

### 9.2. GC count không đồng nghĩa pause count

Một collector concurrent có thể thực hiện những loại hoạt động không tương đương với collector chủ yếu stop-the-world. Khi so sánh performance qua migration:

- Dùng các mục tiêu ứng dụng: latency, throughput, allocation, CPU, memory pressure.
- Quan sát GC pause distribution nếu dữ liệu hỗ trợ.
- Phân biệt concurrent phase với stop-the-world phase.
- So sánh đúng event/metric semantics theo GC cụ thể.
- Không đánh giá collector mới chỉ bằng tổng GC count hoặc tổng collector time.

### 9.3. Normalize metric theo ý nghĩa, không theo tên cũ

Ví dụ thiết kế metric mức ứng dụng:

~~~text
jvm_heap_used_bytes
jvm_heap_committed_bytes
jvm_thread_live_count
process_cpu_usage_ratio
application_request_duration_seconds
~~~

Các tên chỉ mang tính minh họa. Một pipeline thực tế có thể dùng naming conventions khác của Micrometer, OpenTelemetry, Prometheus hoặc JMX exporter.

Khi đổi runtime, cần xác nhận metric mới lấy từ nguồn nào, unit nào và semantics nào. Không nên đổi nhãn **G1 collection count** thành **all GC pauses** khi hai phép đo không đồng nhất.

## 10. JMX remote: kết nối và ranh giới bảo mật

JMX có thể được sử dụng tại cùng process hoặc qua network. Remote JMX thường sử dụng RMI connector, khiến cấu hình không chỉ là một port đơn giản.

Các yếu tố thường gặp:

- JMX registry port.
- RMI connector endpoint và port.
- Hostname/IP JVM quảng bá cho client.
- Authentication.
- TLS/SSL.
- Firewall và network policy.
- Quyền tạo connection và thao tác MBean.
- Container port mapping.
- Kết nối từ bastion/VPN hoặc mạng quản trị riêng.

### 10.1. Vì sao JMX local thành công nhưng remote thất bại?

Một công cụ JMX client có thể kết nối được registry nhưng thất bại khi RMI yêu cầu kết nối đến địa chỉ/port khác do JVM trả về.

Ví dụ hệ thống cấu hình:

~~~text
Registry endpoint: monitoring.example.internal:9010
RMI server quảng bá: localhost:random-port
Client ở máy khác:
  -> kết nối registry được
  -> cố kết nối localhost của chính client
  -> thất bại
~~~

Trong container/Kubernetes, NAT, hostname và port forwarding làm vấn đề phức tạp hơn.

### 10.2. Cấu hình tham khảo

Một số JVM options thường liên quan:

~~~text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=<host-duoc-client-truy-cap>
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
~~~

Đây **không phải cấu hình production hoàn chỉnh**. Để sử dụng cần thiết lập authentication/authorization, TLS certificates/keystore, quyền file và network policy theo tài liệu JDK/vendor và hạ tầng đang triển khai.

**Không tắt authentication hoặc SSL rồi mở JMX ra mạng công cộng để giải quyết vấn đề connectivity.** Một MBean có operation ghi hoặc thực thi tác vụ quản trị có thể tạo ra rủi ro nghiêm trọng.

### 10.3. Ưu tiên kênh quản trị hạn chế

Phương án vận hành thường phù hợp hơn là:

- Chỉ kết nối qua mạng quản trị riêng.
- Dùng tunnel hoặc port-forward được bảo vệ quyền.
- Restrict egress/ingress bằng firewall/network policy.
- Dùng TLS và authentication nếu JMX remote.
- Không expose JMX port trong public LoadBalancer.
- Tách quyền chỉ đọc và quyền thao tác nếu architecture hỗ trợ.
- Giữ secrets bên ngoài source code/command line công khai.

Bất kỳ ví dụ test nào vô hiệu hóa bảo mật cũng không được xem là phương án rollout cho production.

## 11. Client Java đọc JMX từ xa

Một JMX client dùng API chuẩn có thể kết nối remote bằng **JMXServiceURL** và **JMXConnectorFactory**.

~~~java
package example.monitoring;

import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public final class RemoteJmxRead {
    public static void main(String[] args) throws Exception {
        String url =
            "service:jmx:rmi:///jndi/rmi://monitoring.example.internal:9010/jmxrmi";

        Map<String, Object> env = new HashMap<>();

        // Credential phải lấy từ secret manager/config an toàn,
        // không hardcode trong source hoặc commit.
        String username = System.getenv("JMX_USER");
        String password = System.getenv("JMX_PASSWORD");

        if (username == null || password == null) {
            throw new IllegalStateException("Missing JMX credentials");
        }

        env.put(JMXConnector.CREDENTIALS,
            new String[] {username, password});

        try (JMXConnector connector = JMXConnectorFactory.connect(
                new JMXServiceURL(url), env)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName memory =
                new ObjectName("java.lang:type=Memory");

            Object usage =
                connection.getAttribute(memory, "HeapMemoryUsage");

            System.out.println(usage);
        }
    }
}
~~~

Đoạn này **chỉ minh họa API kết nối** và giả định server đã cấu hình TLS, xác thực và network an toàn. Trong hệ thống thực, cần thiết lập SSL socket factories/truststore phù hợp với triển khai, giới hạn timeout và xử lý lỗi. Không coi sự hiện diện của username/password là bằng chứng kênh truyền đã mã hóa.

### 11.1. Attribute có thể là CompositeData

Một số JMX attributes như **HeapMemoryUsage** được biểu diễn dưới dạng **CompositeData** khi truy cập qua MBeanServerConnection. Tool/exporter phải đọc trường **used**, **committed**, **max** theo schema của giá trị, không giả định mọi attribute luôn là một primitive number.

### 11.2. Phân biệt mất kết nối với metric 0

Khi connection thất bại, dashboard nên biểu diễn **absent/unavailable**. Không nên tự điền CPU usage = 0 hoặc GC count = 0, vì như vậy có thể che giấu việc exporter không kết nối được JVM.

Cần có alert riêng cho exporter scrape failure, target down và metric absence.

## 12. JMX và module system

JDK 9 trở lên hỗ trợ Java Platform Module System (JPMS). Với runtime image tùy biến, các module ảnh hưởng tính khả dụng của công cụ:

- **java.management**: API management và nhiều MXBean tiêu chuẩn.
- **java.management.rmi**: thành phần hỗ trợ JMX RMI connector.
- **jdk.management**: một số MXBeans/management functionality mở rộng của JDK.
- **jdk.jfr**: JFR API/runtime.
- **jdk.jcmd**: các công cụ diagnostic command trong JDK image, tùy cách đóng gói.

Một ứng dụng modular có thể khai báo:

~~~java
module example.monitoring {
    requires java.management;
    requires jdk.jfr;
}
~~~

Nếu cần remote JMX connector trong runtime image tùy chỉnh, phải bảo đảm các module liên quan thật sự có mặt. Cách đóng gói bằng **jlink** có thể bỏ một module/tool mà JDK đầy đủ trước đó luôn cung cấp.

### 12.1. Không nhầm Java module với Maven artifact

Không phải mọi module Java SE/JDK có thể thêm lại bằng một dependency trong pom.xml hoặc build.gradle. Nếu runtime image không có **jdk.jfr**, thay Maven dependency của ứng dụng không tự bổ sung được module này.

Kiểm tra:

~~~bash
java --list-modules
~~~

Với custom image, kiểm tra chính executable **java** trong image đó, không dùng **java** của máy developer để suy luận.

### 12.2. Tool có thể không được đóng gói

Container runtime image dạng tối giản có thể không chứa **jcmd**, **jfr**, **jstack** hoặc các executable hỗ trợ chẩn đoán.

Một giải pháp là:

- Thiết kế quy trình ghi JFR từ startup khi cần.
- Dùng API JFR trong ứng dụng nếu phù hợp.
- Sử dụng tooling/diagnostic image được phê duyệt.
- Tổ chức thu hồi .jfr file qua volume hoặc cơ chế bảo mật phù hợp.
- Không tự ý đưa full JDK và quyền attach rộng vào production nếu chưa đánh giá.

## 13. Attach và container: các nguyên nhân thường bị bỏ sót

### 13.1. PID namespace

Ở host có thể thấy PID 24107, nhưng trong container process Java mang PID 1. Lệnh **jcmd** chạy ở phạm vi namespace khác có thể không nhìn thấy hoặc không attach được process mong muốn.

Khi debug:

1. Xác định jcmd được chạy ở host hay container.
2. Xác định PID tương ứng trong namespace đó.
3. Kiểm tra process owner/permissions.
4. Kiểm tra JDK/JVM diagnostic capabilities.
5. Kiểm tra attach mechanism có bị vô hiệu hóa không.
6. Dùng phương án startup recording nếu attach không khả dụng.

### 13.2. Filesystem và quyền ghi

JFR dump có thể thất bại vì:

- Container chạy root filesystem read-only.
- Target directory không tồn tại.
- Process không được phép ghi.
- Volume đầy.
- Recording file bị thu hồi khi pod restart.
- Security policy chặn truy cập.

Không bật quyền root hoặc mount host filesystem rộng chỉ để ghi recording. Chọn thư mục có quyền phù hợp và chính sách lưu trữ/thu hồi bảo mật.

### 13.3. Cgroup CPU và memory

Từ các JDK hiện đại, JVM có nhiều cải tiến về việc nhận biết giới hạn tài nguyên trong container. Nhưng cách JVM báo số CPU, heap ergonomics và process load có thể khác theo JDK release, cgroup version, vendor và cấu hình.

Khi so sánh metric:

- Process CPU được đo theo đơn vị nào?
- CPU quota/request/limit là gì?
- JVM có nhận biết quota không?
- Số processor JVM thấy có đổi?
- Heap max tính theo container memory limit hay host?
- Có swap hoặc native memory pressure không?
- Dashboard đang normalize theo host CPU hay container CPU?

Một thay đổi ở mẫu số của CPU usage có thể làm biểu đồ tăng/giảm dù workload không thay đổi.

### 13.4. GC và process restart reset counters

JMX counters như collectionCount hoặc collectionTime thường gắn với vòng đời JVM. Khi rolling deployment, các counter có thể reset.

Nếu exporter chuyển counter thành metric dạng cumulative, cần tính rate/increase đúng theo semantics của hệ thống metrics và không nhầm counter reset với giá trị âm hoặc "GC đột ngột nhanh hơn".

## 14. JMX exporter và chuyển đổi sang time-series metrics

Trong nhiều hệ thống, công cụ Prometheus JMX Exporter đọc MBeans rồi biến attributes thành metrics. Micrometer/Actuator và OpenTelemetry cũng có các cách thu thập JVM metrics.

### 14.1. Tại sao exporter configuration cũng là compatibility contract?

Một rule có thể dựa trên:

- ObjectName domain.
- MBean key properties.
- Attribute name.
- CompositeData field.
- Tên MemoryPool/GC collector.
- Regex matching.
- Type/name/unit transformation.
- Labels được trích từ ObjectName.

Nếu JDK mới đổi ObjectName hoặc exporter mới đổi naming conventions, biểu đồ có thể không còn nhận dữ liệu.

### 14.2. Ví dụ rule mong manh

Một cấu hình chỉ match collector cụ thể:

~~~text
java.lang:type=GarbageCollector,name=G1 Young Generation
~~~

sẽ không còn mang ý nghĩa khi chuyển sang collector khác. Cách tiếp cận phù hợp hơn là:

- Dùng wildcard cho MBean object names có thuộc tính động.
- Giữ label collector/pool thay vì mặc định một tên.
- Xác định metrics chuẩn có semantic tổng hợp.
- Dùng recording/GC logs để phân tích chi tiết từng GC nếu cần.
- Kiểm thử alert/query với cả collector cũ và mới.

### 14.3. Metric name và unit có thể đổi dù JMX không đổi

Các library metrics có thể chuẩn hóa naming khác nhau:

~~~text
jvm.memory.used
jvm_memory_used_bytes
jvm.memory.used.bytes
~~~

Đây là ví dụ những kiểu naming có thể xuất hiện ở các hệ thống metrics; không được xem chúng là alias tự động.

Khi migration cần kiểm tra:

- Base unit: bytes, KiB, MB, seconds, milliseconds, nanoseconds.
- Metric type: gauge, cumulative counter, delta, histogram.
- Label set và value cardinality.
- Resource attributes như service.name và runtime version.
- Chu kỳ scrape/export.
- Cách xử lý series biến mất.
- Duplicate telemetry nếu hai agents cùng export cùng nguồn.

Nếu hai exporter đang phát cùng metric name nhưng semantics khác nhau, việc cộng chúng trong dashboard có thể đưa ra kết luận sai.

## 15. JFR events và tính tương thích của công cụ phân tích

JFR recording chứa metadata về event types và fields. Các công cụ custom phân tích .jfr có thể phụ thuộc vào cấu trúc đó.

### 15.1. Rủi ro khi parser hardcode schema

Giả sử một parser kỳ vọng:

~~~text
Event type: jdk.CPULoad
Fields: jvmUser, jvmSystem, machineTotal
~~~

Nếu một event field không tồn tại, khác type hoặc không được bật ở runtime target, parser có thể:

- Thất bại khi đọc field.
- Bỏ qua event.
- Ghi null/0 vào metric.
- Phân tích sai.
- Tạo báo cáo thiếu dữ liệu nhưng không cảnh báo.

Đọc được file .jfr không chứng minh pipeline xử lý đúng mọi event.

### 15.2. Thiết kế parser chịu thay đổi

Nên:

1. Đọc metadata của recording.
2. Kiểm tra có event type cần thiết không.
3. Kiểm tra field name/type cần thiết.
4. Có fallback hợp lệ cho optional field.
5. Không tự coi missing field là 0.
6. Phân biệt event không được bật với event không xảy ra.
7. Ghi cảnh báo khi schema ngoài support matrix.
8. Có test với recordings từ JDK baseline và target.

### 15.3. Không so sánh số event thô nếu settings khác

Hai recording dùng **default** và **profile** có thể tạo lượng event khác nhau. Event threshold và sampling period ảnh hưởng dữ liệu.

Ví dụ:

~~~text
JFR A: execution sample mỗi 20 ms
JFR B: execution sample mỗi 10 ms
~~~

Số sample của B có thể cao hơn chỉ vì sampling period ngắn hơn, không phải ứng dụng đột nhiên tiêu thụ CPU gấp đôi.

Khi so sánh phải ghi lại:

- JFR settings.
- Event enabled state.
- Sampling period/threshold.
- Recording duration.
- Workload.
- JVM flags.
- JDK/vendor.
- Container limits.
- Dữ liệu bị bỏ lỡ hoặc ghi không đầy đủ nếu có.

## 16. Profiling overhead và an toàn vận hành

Giám sát có overhead và có thể thay đổi kết quả đo. JFR được thiết kế cho hiệu năng tốt trong nhiều chế độ, nhưng chi phí phụ thuộc vào events và cấu hình.

### 16.1. Các yếu tố làm tăng overhead

- Tần suất event lớn.
- Bật stack traces cho nhiều event.
- Allocation profiling chi tiết.
- Sampling period quá dày.
- Ghi file liên tục lên storage chậm.
- Streaming consumer xử lý event chậm.
- Nhiều agent cùng instrument một JVM.
- Đồng thời chạy Java debugger, profiler và JFR.
- Workload nhạy latency hoặc container giới hạn CPU/I/O.

Không có một con số overhead cố định đúng cho mọi dự án. Cần đo trên workload đại diện.

### 16.2. Mẫu kế hoạch thu thập khi incident

~~~text
Incident ID:
Service / pod / JVM PID:
JDK vendor/version:
Collector:
JFR settings:
Recording name:
Expected duration:
File destination:
Expected size cap:
Operator / approval:
Sensitive-data policy:
Start time:
Stop time:
Storage/transfer policy:
Cleanup:
~~~

Nên dùng recording có thời hạn, giới hạn dung lượng/retention phù hợp và quy trình kiểm soát truy cập. Không lưu .jfr từ production trên máy cá nhân không được quản lý nếu recording có nguy cơ chứa thông tin nhạy cảm.

### 16.3. JFR không thay load test

Một recording từ workload thấp không chứng minh tác động khi hệ thống ở peak throughput. Trước khi bật profile lâu dài, kiểm chứng:

- Throughput và p95/p99 latency.
- CPU usage.
- Allocation/GC.
- Heap/native memory.
- Disk writes.
- Event volume.
- Ảnh hưởng đến autoscaling.
- Khả năng không giảm SLO theo ngưỡng được chấp nhận.

## 17. Kiến trúc giám sát có khả năng nâng cấp

Để tránh ràng buộc dashboard với implementation cụ thể của một JDK, nên tách các lớp:

~~~text
Raw JVM telemetry
   JMX beans / JFR events / GC logs
               |
               v
Exporter / Collector / Adapter
               |
               v
Normalized internal contract
   metric name + unit + labels + semantics
               |
               v
Time-series / Event storage
               |
               v
Dashboards, SLO, Alerts, Automation
~~~

### 17.1. Lợi ích của lớp adapter

Một adapter có thể chuyển hai nguồn JMX cũ/mới sang metric chung có semantic xác định, với các điều kiện:

- Không làm mất ý nghĩa quan trọng.
- Không gộp các đại lượng không tương đương.
- Có metadata về runtime/collector.
- Xử lý missing/unsupported đúng cách.
- Có contract tests.

Ví dụ, có thể xuất **jvm_heap_used_bytes** từ MemoryMXBean một cách tương đối nhất quán, nhưng không nên xuất một nhãn chung **gc_pause_seconds** từ mọi GC MXBean khi nguồn không thực sự đo pause.

### 17.2. Tách metric nghiệp vụ khỏi metric JVM

Để quyết định có rollback migration hay không, ưu tiên các tín hiệu người dùng cảm nhận được:

- Latency p50/p95/p99.
- Error rate.
- Throughput.
- Queue lag.
- Database connection saturation.
- Request timeout.
- Memory pressure.
- Crash/OOM/restarts.

JVM metrics giải thích nguyên nhân, nhưng **GC event count** tăng không tự đồng nghĩa ứng dụng tệ hơn nếu latency và throughput vẫn đạt mục tiêu.

## 18. Phân tích tình huống: đổi từ G1 sang ZGC

Giả sử dịch vụ Java nâng JDK và thay collector.

Trước migration:

~~~text
JDK baseline
GC: G1
Dashboard:
  - G1 Young Generation collection count
  - G1 Old Generation collection time
  - G1 heap pools
Alerts:
  - pause time > threshold
~~~

Sau migration:

~~~text
JDK target
GC: ZGC
Dashboard cũ:
  - Một số MBean/series G1 biến mất
  - Alert không đủ dữ liệu
  - Người vận hành tưởng GC hoạt động bình thường
~~~

Đây là lỗi **observability compatibility** chứ không nhất thiết là lỗi hiệu năng của GC mới.

### 18.1. Quy trình chuyển đổi

1. Chốt baseline latency, throughput, heap, CPU và pause distribution.
2. Khảo sát JMX beans và JFR events của runtime target.
3. Xác định metrics độc lập collector và metrics riêng từng collector.
4. Cập nhật exporter rules để không hardcode G1 khi không phù hợp.
5. Cập nhật dashboard/alerts theo semantics mới.
6. Chạy một workload đại diện với G1 và collector target.
7. So sánh application SLO và resource envelope.
8. Kiểm chứng alert thực sự kích hoạt khi telemetry mất hoặc vượt ngưỡng.
9. Rollout canary, theo dõi cả performance và scrape/recording health.
10. Chỉ xóa dashboard/rule G1 cũ sau khi không còn runtime cần nó.

### 18.2. Không cố làm một metrics giả cho hai collector

Đôi khi hai collector có khái niệm phase/pause không tương đương. Không nên đổi tên hoặc cộng các counters chỉ để giữ nguyên query cũ.

Một giải pháp tốt hơn là:

- Dashboard cấp cao dùng heap, CPU, latency và metrics có định nghĩa thống nhất.
- Dashboard GC chuyên biệt có panel/rule theo collector.
- Label **collector** hoặc **runtime version** giúp phân loại.
- Alert vận hành ưu tiên application symptoms và tín hiệu lỗi quan trọng.

## 19. Phân tích tình huống: JMX exporter ngừng nhận dữ liệu sau container migration

Giả sử JMX exporter có thể scrape khi chạy trên VM, nhưng khi chuyển sang container không còn metric.

Các khả năng:

- RMI server quảng bá hostname không truy cập được từ client.
- JMX port hoặc RMI port bị chặn.
- Service account thiếu quyền.
- TLS hoặc credentials thay đổi.
- Exporter đang scrape sai process/JVM.
- Runtime image thiếu module cần thiết.
- Exporter process nằm ở network namespace khác.
- Firewall/service discovery hoặc port mapping không đúng.
- JVM đã tắt remote management.
- Container restart làm thay PID/hostname.

### 19.1. Triage có thứ tự

1. Xem target JVM còn chạy không.
2. Xem có quyền và đường mạng để truy cập không.
3. Kiểm tra registry/RMI endpoint và hostname quảng bá.
4. Kiểm tra auth/TLS với client tin cậy.
5. Kiểm tra MBean có tồn tại trên JVM đích không.
6. Kiểm tra exporter mapping rules.
7. Kiểm tra endpoint scrape trả dữ liệu không.
8. Kiểm tra time-series backend nhận metric có label đúng không.
9. Kiểm tra dashboard/alert query có khớp metric mới không.

Không xử lý bằng cách tắt SSL/auth rồi để port mở công khai. Nếu cần debug, dùng kênh quản trị hạn chế và quan sát log theo chính sách của tổ chức.

### 19.2. Đừng biến "missing" thành 0

Nếu exporter mất kết nối, một metric không tồn tại phải được nhận diện là telemetry unavailable. Nếu dashboard hiển thị 0, hệ thống có thể đưa ra kết luận sai: không có GC, không dùng CPU hoặc hết memory pressure.

Cần alert riêng cho **up/scrape health**, mất metric và target discovery.

## 20. Phân tích tình huống: JFR recording mở được nhưng báo cáo lệch

Giả sử một công cụ phân tích tự viết mở file JFR từ JDK mới, nhưng một báo cáo CPU bị sai.

Khả năng:

- Event **jdk.CPULoad** có field khác so với parser kỳ vọng.
- Event bị disable trong settings target.
- Sampling period thay đổi.
- Process chạy trong container với CPU quota khác.
- Tool quy đổi ratio thành percent sai.
- JDK thay đổi cách đo process/system CPU.
- Recording duration hoặc workload khác.
- Parser gộp mẫu không theo duration/weight.
- Recording bị thiếu một số event do policy hoặc overhead.

### 20.1. Cách xác minh

1. Dùng **jfr summary** để biết event thực sự có mặt.
2. Dùng **jfr metadata** xác nhận field và type.
3. Dùng **jfr print** kiểm tra vài mẫu đại diện.
4. Ghi rõ recording settings.
5. So sánh process/container CPU bằng nguồn độc lập.
6. Kiểm tra bước quy đổi unit.
7. Chạy lại với workload và sampling tương đương.
8. Cập nhật parser và hợp đồng metric nếu thay đổi thực sự tồn tại.

Một parser không lỗi runtime vẫn có thể diễn giải sai dữ liệu. Vì vậy acceptance phải bao gồm **tính đúng của metric**, không chỉ file đọc được.

## 21. Bảo mật và quyền riêng tư của telemetry

JFR recording, heap diagnostics và JMX management data có thể chứa thông tin nhạy cảm về hệ thống.

Rủi ro:

- Tên class/package nội bộ.
- Thread names có chứa request hoặc tenant ID.
- File path và socket host.
- System properties có cấu hình nhạy cảm.
- Custom event vô tình ghi PII.
- JMX operation cho phép thay đổi trạng thái dịch vụ.
- Agent hoặc công cụ từ xa có quyền truy cập quá rộng.
- Recording được chia sẻ ngoài nhóm được phép.
- Log chẩn đoán chứa credentials hoặc token.

### 21.1. Chính sách tối thiểu

- Giới hạn danh sách người và hệ thống được đọc recording.
- Không gửi thông tin nhạy cảm vào custom JFR events.
- Quản lý file .jfr theo retention và encryption policy.
- Cấu hình JMX remote có authentication, TLS và network isolation.
- Tách management endpoints khỏi public traffic.
- Không hardcode credentials trong code hoặc shell history.
- Ghi log việc truy cập công cụ quản trị nếu cần.
- Dùng quyền tối thiểu cho exporter và agents.
- Xóa recording tạm theo quy trình khi hết nhu cầu.
- Kiểm tra nội dung trước khi chia sẻ với nhà cung cấp hoặc ngoài tổ chức.

Bảo mật được áp dụng ở ranh giới thu thập, truyền, lưu, truy cập và chia sẻ telemetry.

## 22. Chiến lược kiểm thử tương thích công cụ giám sát

### 22.1. Chốt baseline trước migration

Lưu:

- JDK vendor, version và build.
- JVM flags, GC và memory settings.
- Container image, resource requests/limits.
- JFR recording settings.
- Danh sách event quan trọng và metadata.
- Danh sách MBean/ObjectName/attribute quan trọng.
- JMX exporter/agent/JMC versions.
- Scrape config và naming rules.
- Dashboard JSON/query, alert rules.
- Baseline metrics/recording dưới workload đại diện.
- Security/network config ở mức cần thiết, không lưu secrets.

### 22.2. Ma trận runtime và tooling

| Thành phần | Baseline | Target | Điều cần xác nhận |
|---|---|---|---|
| JVM | JDK A | JDK B | Startup, performance, modules |
| GC | Collector A | Collector B | MBeans, event semantics |
| JFR | Recording từ A | Recording từ B | File mở được, event schema |
| JMC/parser | Tool version cũ | Tool version hỗ trợ B | Phân tích đúng |
| JMX | Attributes A | Attributes B | ObjectName/type/availability |
| Exporter | Rule cũ | Rule mới | Metric names/units/labels |
| Dashboard | Query A | Query B | Panel hiển thị đủ và đúng |
| Alert | Rule A | Rule B | Trigger và missing-data behavior |
| Container | Image A | Image B | PID, cgroup, filesystem, ports |
| Security | Policy A | Policy B | Auth/TLS/permissions |

Đây là khung lập kế hoạch; không nhất thiết chạy mọi tổ hợp với mọi release. Ưu tiên các mối liên hệ thực sự tồn tại trong production.

### 22.3. Test cấp JMX

Một bài test có thể:

1. Khởi động JVM target với cấu hình gần production.
2. Truy cập platform MBean server.
3. Query wildcard cho GC và MemoryPool beans.
4. Xác nhận các attribute kỳ vọng có mặt.
5. Xác nhận kiểu dữ liệu và đơn vị.
6. Kiểm tra giá trị unavailable được xử lý đúng.
7. Nếu có remote JMX, test auth/TLS và port mapping.
8. Kiểm tra exporter output tương ứng.

Không yêu cầu tên collector cụ thể trừ khi support matrix cố định collector đó.

### 22.4. Test cấp JFR

Một bài test có thể:

1. Tạo recording bằng settings được công bố.
2. Kích hoạt workload có CPU, allocation và một số I/O đại diện.
3. Xác nhận file .jfr tồn tại, có thể mở bằng tool target.
4. Kiểm tra event type/field quan trọng.
5. Kiểm tra parser có xử lý missing/optional field.
6. Đối chiếu unit, sampling period và recording duration.
7. So sánh metric đã chuẩn hóa với một nguồn đáng tin cậy khác nếu cần.
8. Xác nhận recording cleanup và data-retention policy.

### 22.5. Test alert khi mất telemetry

Không chỉ test trường hợp JVM heap cao hoặc request latency tăng. Cần cố ý mô phỏng exporter down hoặc metric mất, rồi xác nhận:

- Dashboard không tự hiển thị 0 giả.
- Alert cho missing data hoạt động.
- Incident routing tới owner đúng.
- Recovery khi metric trở lại.
- Không tạo alert storm vô nghĩa trong rolling restart.

### 22.6. Canary và parallel monitoring

Một giai đoạn có thể chạy:

~~~text
Canary JDK target
      |
      +--> Collector/exporter target
      +--> JFR recording representative
      +--> Dashboard mới

Baseline JDK
      |
      +--> Collector/exporter cũ
      +--> JFR baseline
      +--> Dashboard cũ

So sánh:
  - SLO
  - Metrics coverage
  - Units/labels/semantics
  - Tool overhead
  - Alerts and gaps
~~~

Khi đặt hai dashboard cạnh nhau, không so sánh rate từ các cửa sổ thời gian khác nhau hoặc workload không tương đương.

## 23. Giai đoạn triển khai và điều kiện Go/No-Go

### Gate A — Inventory

- Biết tất cả đường thu thập JMX/JFR/agents.
- Biết dependency vào JDK vendor và GC.
- Có source của dashboards/alerts và owner.
- Có baseline telemetry và incident runbook.

**Go:** có thể kiểm tra những tín hiệu thực sự dùng để vận hành.

### Gate B — Tool readiness

- JMC và parser có thể xử lý JFR target.
- JMX exporter hiểu MBeans target.
- Runtime image có các modules/công cụ cần thiết.
- Remote management security/network được thiết kế.

**Go:** không có blocker đã biết ở tooling.

### Gate C — Staging/canary

- Ghi JFR và đọc file thành công.
- JMX metrics được scrape.
- Metric names, units, labels đã được xác nhận.
- Dashboard có dữ liệu đúng.
- Missing-telemetry alerts hoạt động.
- SLO/performance được kiểm tra.
- Overhead của recording/agents nằm trong budget.

**Go:** quan sát đáng tin cậy trên workload đại diện.

### Gate D — Rollout

- Có kế hoạch canary/rolling deployment.
- Có rollback-compatible exporter và dashboard.
- Có metric phân biệt runtime versions.
- Incident runbook mới đã được bàn giao.
- Có quy trình thu thập JFR khi attach không khả dụng.
- Không còn blind spots chưa được chấp nhận.

**Go:** đội vận hành có đủ tín hiệu để phát hiện và xử lý sự cố trong đợt chuyển đổi.

### Gate E — Cleanup

- Không còn instances cần rules cũ ngoài phạm vi hỗ trợ.
- Không còn dashboard/query legacy được dùng.
- Đã loại workaround và temporary ports/flags.
- Đã cập nhật documentation, owner và support matrix.
- Recording tạm đã được quản lý theo retention policy.

Không xóa monitoring configuration cũ trước khi chắc chắn các phiên bản chưa chuyển không còn cần nó.

## 24. Checklist thực hành

### JDK, runtime và GC

- [ ] Đã ghi JDK vendor, version, JVM flags và collector.
- [ ] Đã xác nhận container CPU/memory visibility.
- [ ] Đã kiểm tra modules trong runtime image.
- [ ] Đã xác định công cụ jcmd/jfr có sẵn hay dùng phương án khác.
- [ ] Đã đánh giá collector-specific names và semantics.

### JFR

- [ ] JFR có sẵn trên JDK/runtime target.
- [ ] Recording settings được xác định rõ.
- [ ] Có thể start/dump/stop recording phù hợp vận hành.
- [ ] .jfr file được công cụ phân tích target mở và đọc đúng.
- [ ] Các event và fields quan trọng được kiểm tra.
- [ ] Parser xử lý missing/optional events/fields.
- [ ] Đã kiểm tra overhead, dung lượng và retention.
- [ ] Custom events không chứa thông tin nhạy cảm.

### JMX và exporter

- [ ] MBeans/attributes cần thiết được phát hiện trên target.
- [ ] Không hardcode tên GC/MemoryPool ngoài support policy.
- [ ] Attribute unavailable được xử lý là unknown, không phải 0.
- [ ] Exporter rules được kiểm tra với MBeans target.
- [ ] Metrics units/types/labels được xác minh.
- [ ] JMX remote có auth/TLS/network isolation.
- [ ] RMI port, hostname và container connectivity được kiểm tra.

### Dashboards, alerts và rollout

- [ ] Dashboard không mất panels hoặc silently report 0.
- [ ] Alert rules có test với metric thật và metric missing.
- [ ] Có baseline và canary comparison.
- [ ] Application SLO được theo dõi cùng JVM metrics.
- [ ] Có test kết nối và dữ liệu trên production-like image.
- [ ] Có runbook thu thập diagnostic trên container.
- [ ] Có kế hoạch rollback tool/agent/config.
- [ ] Có owner cho từng telemetry contract quan trọng.

## 25. Tài liệu tham khảo

Tra cứu theo đúng JDK/vendor và tool version trong dự án:

- **JEP 328 – Flight Recorder:** https://openjdk.org/jeps/328
- **JEP 349 – JFR Event Streaming:** https://openjdk.org/jeps/349
- **JFR API (jdk.jfr):** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/module-summary.html
- **java.management module:** https://docs.oracle.com/en/java/javase/21/docs/api/java.management/module-summary.html
- **ManagementFactory API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- **javax.management.remote APIs:** https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/package-summary.html
- **jcmd command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **jfr command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
- **JDK Mission Control:** https://www.oracle.com/java/technologies/jdk-mission-control.html
- **Prometheus JMX Exporter:** https://github.com/prometheus/jmx_exporter
- **Micrometer:** https://docs.micrometer.io/micrometer/reference/
- **OpenTelemetry Java:** https://opentelemetry.io/docs/languages/java/

Không suy luận rằng tài liệu mô tả JDK 21 là đặc tả cho mọi vendor và release tương lai. Đối chiếu API, runtime flags, module availability và actual event/bean metadata của môi trường đích.

---

**Kết luận:** Trong Java migration, **JFR giúp hiểu diễn biến hiệu năng theo sự kiện**, còn **JMX giúp quan sát trạng thái và counters của JVM**. Cả hai đều có thể trở thành nguồn phụ thuộc ngầm: dashboard dựa vào tên GC MBean, parser dựa vào JFR event field, exporter dựa vào đơn vị và label hoặc JMX remote dựa vào một cấu hình mạng cụ thể. Muốn nâng JDK an toàn, cần inventory các telemetry contracts hiện có, thử chúng trên runtime target, phân biệt missing data với giá trị 0, đánh giá overhead và bảo mật, rồi triển khai đồng thời cả runtime lẫn công cụ giám sát. Một migration chỉ thực sự sẵn sàng vận hành khi **đội ngũ vẫn có khả năng quan sát và phát hiện sự cố đáng tin cậy sau khi JVM thay đổi**.
