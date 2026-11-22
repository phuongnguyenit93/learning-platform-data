# Chi phí đọc attribute và gọi operation qua JMX

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích luồng thực thi khi JMX client **đọc một attribute** hoặc **gọi một operation** của MBean.
- Phân biệt chi phí của **JMX dispatch, reflection/metadata, serialization, network round trip** và **logic nghiệp vụ trong getter/operation**.
- Hiểu vì sao getter nhìn đơn giản nhưng có thể gây blocking, allocation, lock contention hoặc truy vấn dữ liệu tốn kém.
- So sánh JMX local trong cùng JVM với remote JMX qua connector, nhất là RMI.
- Thiết kế MBean có getters nhanh, không gây tác dụng phụ và operations có giới hạn thời gian, tải và đồng thời.
- Tránh polling quá dày, gọi nhiều attributes thiếu kiểm soát và gây hiệu ứng thác tải vào ứng dụng.
- Viết ví dụ Java/Spring và đo thực tế bằng benchmark hoặc quan sát độ trễ, throughput và ảnh hưởng đến workload chính.
- Nhận diện tình huống cần dùng Micrometer/metrics thay vì liên tục gọi các thao tác JMX có chi phí cao.

## 1. JMX là kênh quản trị, không phải đường dữ liệu miễn phí

Java Management Extensions (JMX) cung cấp cơ chế truy cập các managed resources thông qua MBeanServer. Spring Framework có thể export Spring beans thành MBeans bằng MBeanExporter và metadata annotations như @ManagedResource, @ManagedAttribute, @ManagedOperation.

Mô hình:

\`\`\`text
Monitoring / Admin client
       |
       | getAttribute(...) / invoke(...)
       v
MBeanServer hoặc MBeanServerConnection
       |
       | tra ObjectName, MBean metadata, dispatch
       v
MBean adapter / target
       |
       | chạy getter hoặc operation thật
       v
Application state / database / queue / cache
\`\`\`

Gọi JMX **không giống đọc một bản snapshot có sẵn** trong mọi trường hợp. Nhiều MBeans tính toán dữ liệu ngay khi được hỏi. Một getter có thể chạy code Java, giữ lock, duyệt collection, hỏi database hoặc gọi network.

Điểm cần nhớ:

> Chi phí một lần gọi JMX thường là tổng chi phí hạ tầng JMX cộng với chi phí chính method được công bố. Trong nhiều tình huống, phần chi phí của getter/operation lớn hơn phần dispatch của JMX rất nhiều.

## 2. Attribute và operation có gì khác?

**Attribute** là thuộc tính quản trị. Với Spring:

\`\`\`java
@ManagedAttribute
public int getQueueDepth() {
    return queue.depth();
}
\`\`\`

Client gọi:

\`\`\`java
Object value = server.getAttribute(
    objectName,
    "QueueDepth"
);
\`\`\`

**Operation** là thao tác quản trị:

\`\`\`java
@ManagedOperation
public void refreshIndexes() {
    indexService.refresh();
}
\`\`\`

Client gọi:

\`\`\`java
server.invoke(
    objectName,
    "refreshIndexes",
    new Object[0],
    new String[0]
);
\`\`\`

Khác biệt cơ bản nằm ở contract và kỳ vọng sử dụng, **không phải JMX tự đảm bảo getter luôn rẻ còn operation luôn đắt**. Getter có thể rất tốn kém nếu implementation không được thiết kế tốt; operation có thể rất nhanh nếu chỉ cập nhật một flag.

Một attribute getter nên có tính quan sát, trả nhanh và tránh side effects. Một operation cần nêu rõ chi phí và tác động để caller không vô tình thực hiện thao tác nặng.

## 3. Các nguồn chi phí của một lần gọi JMX

Có thể phân tách sơ bộ:

\`\`\`text
Tổng thời gian một lời gọi
  = thời gian client chuẩn bị request
  + connector/transport overhead
  + tra cứu MBean và dispatch
  + xử lý trong getter/operation
  + chuyển đổi/serialize kết quả
  + transport chiều về
  + xử lý kết quả ở client
\`\`\`

Đây là mô hình khái niệm, không phải công thức đo chính xác cho mọi implementation.

### 3.1. Chi phí tìm MBean và dispatch

MBeanServer xác định registration qua ObjectName, xem metadata và chuyển lời gọi đến managed resource hoặc adapter. Có thể xuất hiện lookup, kiểm tra tên và signatures, reflection/proxy invocation hoặc interceptor.

Thông thường chi phí này nhỏ nếu getter đơn giản, nhưng nó không bằng 0. Không nên coi các lời gọi quản trị lặp hàng nghìn lần mỗi giây giống phép truy cập field Java.

### 3.2. Chi phí thực thi method

Getter có thể:

- Đọc AtomicLong hoặc một snapshot đã chuẩn bị.
- Giữ synchronized lock để đọc collection.
- Duyệt hàng triệu phần tử.
- Chạy SQL COUNT trên một bảng lớn.
- Gọi service khác qua HTTP.
- Tổng hợp nhiều metrics ngay tại thời điểm được hỏi.

Các trường hợp sau hoàn toàn khác nhau về CPU, I/O, latency và nguy cơ làm chậm workload chính.

### 3.3. Chi phí dữ liệu trả về

Trả về một số nguyên khác với trả về một danh sách hàng trăm nghìn phần tử. Với remote JMX, kết quả còn phải được marshal/serialize qua connector và có thể tạo áp lực memory, GC và network.

### 3.4. Chi phí trên client

JMX client cũng cần xử lý metadata, giải mã dữ liệu, cập nhật dashboard hoặc lưu kết quả. Khi polling rất nhiều MBeans và nhiều JVMs, tải tổng hợp có thể lớn dù mỗi request riêng lẻ không tốn nhiều.

## 4. Local JMX và remote JMX

Cần phân biệt các dạng truy cập:

| Hình thức | Đường gọi | Chi phí thường gặp |
|---|---|---|
| Gọi method trực tiếp | Java object → method | Chủ yếu logic Java |
| MBeanServer trong cùng JVM | Java → MBeanServer → MBean | Thêm registry/dispatch/adapter |
| Local monitoring tool qua attach/connector | Tool → local transport → JVM | Thêm transport và cơ chế quản trị |
| Remote JMX | Client → network connector → JVM → MBean | Thêm network, authentication, TLS, serialization, thời gian khứ hồi |

Trong cùng JVM:

\`\`\`java
MBeanServer server =
        ManagementFactory.getPlatformMBeanServer();

long count = (Long) server.getAttribute(
    name,
    "ProcessedJobs"
);
\`\`\`

Đây vẫn là lời gọi qua JMX API, nhưng không có một remote network round trip như khi dùng MBeanServerConnection qua RMI.

Remote JMX:

\`\`\`java
MBeanServerConnection connection =
        connector.getMBeanServerConnection();

Object value = connection.getAttribute(name, "ProcessedJobs");
\`\`\`

Tùy connector, phiên bản JDK, security, network và kiểu dữ liệu, chênh lệch về latency có thể đáng kể. Không đưa ra một tỷ lệ “remote chậm hơn X lần” nếu chưa đo trên môi trường cụ thể.

## 5. Ví dụ getter rẻ và getter đắt

### Getter rẻ: đọc giá trị đã được duy trì

\`\`\`java
import java.util.concurrent.atomic.AtomicLong;

public class QueueMetrics {
    private final AtomicLong processedJobs = new AtomicLong();

    public void recordProcessedJob() {
        processedJobs.incrementAndGet();
    }

    public long processedJobs() {
        return processedJobs.get();
    }
}
\`\`\`

MBean facade:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueMetrics,name=Primary"
)
public class QueueMetricsMBeanView {

    private final QueueMetrics metrics;

    public QueueMetricsMBeanView(QueueMetrics metrics) {
        this.metrics = metrics;
    }

    @ManagedAttribute(description = "Processed jobs since startup")
    public long getProcessedJobs() {
        return metrics.processedJobs();
    }
}
\`\`\`

Getter chủ yếu đọc AtomicLong, tương đối ít tốn kém.

### Getter đắt: quét toàn bộ dữ liệu mỗi lần poll

\`\`\`java
@ManagedAttribute
public long getPendingJobs() {
    return jobs.stream()
        .filter(job -> job.isPending())
        .count();
}
\`\`\`

Nếu jobs rất lớn, mỗi lần đọc attribute phải duyệt dữ liệu. Khi nhiều monitoring agents poll cùng lúc, chi phí có thể tăng theo số lần gọi và kích thước collection.

Một phương án có thể phù hợp hơn:

- Duy trì counter khi job thay đổi trạng thái.
- Tính một snapshot định kỳ ngoài đường gọi JMX.
- Dùng caching với giới hạn độ mới nếu dữ liệu cho phép.
- Tránh giữ lock lâu khi tính toán.

## 6. Tính toán trong getter cần có giới hạn

Một getter quản trị lý tưởng nên:

1. **Nhanh:** không truy vấn dữ liệu nặng trên request path.
2. **Không gây side effects:** không xóa cache, thay đổi config hoặc trigger job.
3. **Có semantics rõ:** type, đơn vị, độ mới và ý nghĩa giá trị.
4. **An toàn đồng thời:** dùng Atomic*, volatile, immutable snapshot hoặc synchronization hợp lý.
5. **Có hành vi lỗi dự đoán được:** không mắc kẹt vĩnh viễn.
6. **Không tạo khối dữ liệu khổng lồ:** giới hạn cardinality và dung lượng kết quả.

Ví dụ đọc snapshot:

\`\`\`java
public record QueueSnapshot(
        long pendingJobs,
        long processedJobs,
        long generatedAtMillis) {
}
\`\`\`

Service lưu snapshot đã được cập nhật:

\`\`\`java
private volatile QueueSnapshot latestSnapshot =
        new QueueSnapshot(0, 0, 0);

public QueueSnapshot latestSnapshot() {
    return latestSnapshot;
}
\`\`\`

Cần chú ý JMX serialization và khả năng tương thích type với remote clients. Không nhất thiết export trực tiếp một record custom nếu client ở JVM khác không có class đó. Có thể công bố các primitive attributes riêng hoặc Open Types phù hợp.

## 7. Chặn nguy cơ getter giữ lock quá lâu

Ví dụ không lý tưởng:

\`\`\`java
@ManagedAttribute
public synchronized String getFullReport() {
    // Duyệt dữ liệu lớn và tạo chuỗi dài
    return calculateLargeReport();
}
\`\`\`

Nếu cùng monitor lock được dùng bởi production threads, getter của một monitoring client có thể chặn nghiệp vụ.

Tách tính toán khỏi critical section:

\`\`\`java
private volatile String cachedReport = "not available";

@ManagedAttribute
public String getReportSummary() {
    return cachedReport;
}
\`\`\`

Một task riêng cập nhật cachedReport theo lịch hoặc sự kiện. Cần bảo đảm snapshot đủ mới theo nhu cầu vận hành và không expose dữ liệu nhạy cảm.

Không phải mọi synchronized getter đều sai; một critical section rất ngắn có thể phù hợp. Vấn đề là thời gian lock, mức độ contention và ảnh hưởng tới business threads.

## 8. MBean operation có thể gây tải lớn

Operation thường có tác dụng phụ:

\`\`\`java
@ManagedOperation
public void rebuildIndex() {
    indexService.rebuildAll();
}
\`\`\`

Nếu rebuildAll mất nhiều phút, việc gọi trực tiếp từ JMX có thể giữ thread xử lý và làm client chờ lâu, gây timeout hoặc mất kết nối.

Thiết kế tốt hơn khi tác vụ dài:

1. Operation chỉ **gửi yêu cầu** bắt đầu công việc.
2. Trả về job ID hoặc trạng thái khởi tạo.
3. Executor có concurrency limit rõ.
4. Attributes/metrics báo tiến trình, kết quả và lỗi.
5. Có timeout, cancellation policy hoặc backpressure nếu phù hợp.
6. Tránh cho phép gửi hàng loạt rebuild đồng thời.

Ví dụ đơn giản:

\`\`\`java
@ManagedOperation(description = "Start one index rebuild if idle")
public String requestRebuild() {
    if (!running.compareAndSet(false, true)) {
        return "ALREADY_RUNNING";
    }

    try {
        executor.execute(() -> {
            try {
                indexService.rebuildAll();
            } finally {
                running.set(false);
            }
        });
        return "ACCEPTED";
    } catch (RuntimeException ex) {
        running.set(false);
        throw ex;
    }
}
\`\`\`

Giả định running là AtomicBoolean và executor/indexService đã được inject. Trong production, cần lưu trạng thái kết quả, bảo vệ khi executor bị shutdown, xử lý exception, queue capacity và authorization.

Điểm cốt lõi: một operation dài không nên khiến JMX connector thread trở thành worker nghiệp vụ chạy vô hạn.

## 9. Polling và hiệu ứng nhân tải

Một công cụ giám sát thường gọi JMX theo chu kỳ.

Giả sử:

- 200 MBeans.
- Mỗi MBean có 5 attributes cần lấy.
- 1 agent poll mỗi 10 giây.

Số lần đọc attribute lý thuyết:

\`\`\`text
200 × 5 / 10 = 100 attribute reads/second
\`\`\`

Nếu 4 agents poll độc lập cùng một JVM, có thể thành 400 reads/second, chưa tính retry và metadata queries.

Con số này không tự nói lên CPU usage; chi phí thực tế phụ thuộc implementation. Nhưng nó cho thấy **tần suất và fan-out nhân tổng khối lượng công việc**.

Nguyên tắc:

- Chỉ poll attributes cần thiết.
- Chọn interval theo tốc độ thay đổi dữ liệu và giá trị vận hành.
- Tránh đồng bộ mọi client poll cùng thời điểm nếu gây spike.
- Dùng jitter và backoff hợp lý.
- Tránh retry dồn dập khi JVM đang chậm.
- Đo thời gian và mức độ ảnh hưởng trước khi tăng tần suất.
- Cân nhắc một collector rồi phân phối metrics thay vì nhiều clients hỏi trực tiếp cùng MBeans.

## 10. getAttribute so với getAttributes

JMX cung cấp:

\`\`\`java
Object value = connection.getAttribute(name, "QueueDepth");
\`\`\`

và:

\`\`\`java
AttributeList values = connection.getAttributes(
    name,
    new String[] { "QueueDepth", "ProcessedJobs", "Paused" }
);
\`\`\`

Gọi getAttributes có thể giảm số lần round trip khi client cần nhiều attributes của **cùng một MBean**. Với remote JMX, điều này thường là yếu tố quan trọng.

Nhưng cần hiểu:

- Những getter liên quan vẫn có thể được gọi để tạo từng giá trị.
- Một getter nặng không trở thành rẻ chỉ vì gộp request.
- Kết quả có thể không chứa mọi attribute nếu một số thuộc tính không đọc được hoặc lỗi.
- Phải kiểm tra tên/giá trị trả về trong AttributeList, không giả định đủ mọi phần tử theo thứ tự khi có lỗi.
- Batch request không mặc định cho snapshot nguyên tử của toàn bộ MBean; trạng thái có thể thay đổi giữa các getter.

## 11. Tránh gọi getMBeanInfo quá thường xuyên

\`getMBeanInfo\` rất hữu ích để khám phá attributes, operations và signatures:

\`\`\`java
MBeanInfo info = connection.getMBeanInfo(name);
\`\`\`

Tuy nhiên, nếu client gọi getMBeanInfo trước mỗi lần đọc metric, chi phí metadata và remote round trip có thể không cần thiết.

Một monitoring client thường có thể:

1. Discover MBeans/attributes khi kết nối hoặc định kỳ.
2. Lưu metadata trong phạm vi phiên làm việc.
3. Đọc những attributes đã biết theo lịch.
4. Refresh metadata khi MBean đăng ký lại, topology thay đổi hoặc lỗi chỉ ra contract đã đổi.

Không cache metadata vĩnh viễn nếu MBeans có thể được unregister/re-register hoặc application version thay đổi.

## 12. Chi phí lớn khi trả về nhiều dữ liệu

Một attribute dạng String dài hoặc custom object lớn có thể gây:

- Nhiều allocation và garbage collection.
- Serialization/deserialization overhead.
- Network bandwidth lớn.
- Độ trễ tăng khi nhiều clients poll.
- Log hoặc monitoring system phình to.
- Khó tương thích với remote clients thiếu class tương ứng.

Không export toàn bộ queue contents hoặc danh sách mọi request IDs thành một JMX attribute nếu mục tiêu chỉ cần vài số tổng hợp.

Thay vào đó, dùng:

- Count, utilization, min/max/average theo nhu cầu.
- Bounded summary hoặc số lượng phần tử tối đa.
- Open Types có cấu trúc và giới hạn hợp lý.
- Một API khác có pagination nếu cần truy xuất dữ liệu lớn, với authentication/authorization thích hợp.

Một MBean có thể thuận tiện cho quản trị nhưng không nên trở thành data-export endpoint không giới hạn.

## 13. Đo latency của lời gọi JMX

Đừng tối ưu dựa trên cảm giác. Đo nhiều lần, nhiều percentile và nhiều trạng thái tải.

Ví dụ mã thô đo local call:

\`\`\`java
long start = System.nanoTime();

Object value = server.getAttribute(
    objectName,
    "QueueDepth"
);

long elapsed = System.nanoTime() - start;

System.out.println("Elapsed ns: " + elapsed);
System.out.println("Value: " + value);
\`\`\`

Đây **không phải benchmark chuẩn** nếu chỉ chạy một lần. Lần đầu có thể chịu class loading, JIT warmup, initialization hoặc cache effects.

Quy trình đo nên:

1. Warm up hệ thống phù hợp.
2. Đo đủ số samples và các percentile như p50, p95, p99.
3. So sánh khi JVM rảnh và khi business load cao.
4. Đo local và remote riêng.
5. Theo dõi CPU, allocations, GC, lock contention và thread count.
6. Đo cả client-side round-trip time lẫn server-side method duration khi có thể.
7. Không để logging trong vòng lặp làm sai kết quả.
8. Dùng công cụ benchmark chuyên dụng như JMH nếu cần microbenchmark chính xác.

Đừng gán “JMX overhead” cho toàn bộ thời gian nếu getter thực hiện database query mất hàng trăm mili giây.

## 14. Đo phần chi phí của getter hoặc operation

Bạn có thể instrument business method để biết thời gian xử lý, độc lập với transport.

Ví dụ:

\`\`\`java
public long queueDepthMeasured() {
    long start = System.nanoTime();
    try {
        return queueService.depth();
    } finally {
        long elapsed = System.nanoTime() - start;
        methodDurationRecorder.record(elapsed);
    }
}
\`\`\`

Phép đo này có overhead riêng. Không nên instrument mọi lần bằng logging synchronous tốn kém, vì nó làm thay đổi workload đang quan sát.

Khi có cả client-side và server-side measurements:

\`\`\`text
Remote round-trip latency
    ≈ connector/network overhead
    + JMX dispatch
    + method execution
    + serialization/deserialization
\`\`\`

Đây chỉ là cách phân tích; phải đo thực tế để xác định bottleneck.

## 15. Kiểm soát đồng thời và backpressure

Một MBean operation được nhiều callers gọi cùng lúc có thể gây vấn đề:

- Hai tác vụ rebuild tranh cùng dữ liệu.
- Nhiều operations giữ chung lock.
- Monitoring clients retry liên tục khi thấy timeout.
- Thread pool quản trị hoặc nghiệp vụ bị chiếm hết.
- Một client ác ý hoặc lỗi cấu hình tạo nhiều requests.

Các biện pháp:

- Dùng AtomicBoolean, semaphore hoặc concurrency gate khi operation chỉ nên chạy một lần.
- Đặt timeout cho I/O và downstream calls.
- Giới hạn queue size của executor.
- Từ chối request khi hệ thống bận với trạng thái rõ ràng.
- Cho operations mang tính idempotent khi có thể.
- Có cơ chế audit cho lệnh quản trị nhạy cảm.
- Không giữ lock quan trọng trong lúc làm I/O kéo dài.

Ví dụ giới hạn một công việc:

\`\`\`java
private final Semaphore gate = new Semaphore(1);

@ManagedOperation
public String requestRefresh() {
    if (!gate.tryAcquire()) {
        return "BUSY";
    }

    try {
        executor.execute(() -> {
            try {
                refreshService.refresh();
            } finally {
                gate.release();
            }
        });
        return "ACCEPTED";
    } catch (RuntimeException e) {
        gate.release();
        throw e;
    }
}
\`\`\`

Ví dụ giả định executor nhận task thành công hoặc ném khi từ chối; ứng dụng thực cần xử lý shutdown, trạng thái thất bại, công bằng và khả năng retry.

## 16. Lưu ý với Spring @ManagedAttribute và @ManagedOperation

Ví dụ một management facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMetrics,name=Primary"
)
public class QueueManagement {

    private final QueueService service;

    public QueueManagement(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Current queue depth")
    public long getQueueDepth() {
        return service.cachedDepth();
    }

    @ManagedOperation(description = "Request metrics refresh")
    public String requestMetricsRefresh() {
        return service.requestRefresh();
    }
}
\`\`\`

Spring configuration có thể bật annotation-driven export:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    QueueManagement queueManagement(QueueService service) {
        return new QueueManagement(service);
    }
}
\`\`\`

Chú ý:

- @ManagedAttribute không giới hạn thời gian thực thi getter.
- @ManagedOperation không tự chuyển tác vụ nặng thành asynchronous job.
- MBeanExporter đảm nhận export metadata và registration, không tối ưu nghiệp vụ thay bạn.
- Những method có annotation trở thành bề mặt quản trị theo exporter configuration.
- Nếu service dùng AOP proxy, cần xác nhận advice không làm tăng latency bất ngờ hoặc bị bypass qua invocation path.

## 17. Kết nối remote: thêm network, serialization và bảo mật

Remote JMX thường có thêm các chi phí:

- TCP/RMI hoặc transport connector tương ứng.
- Mã hóa/giải mã khi TLS được bật.
- Authentication và context của kết nối.
- Marshaling và serialization của params/results.
- Network RTT, packet loss, retransmission.
- Connector thread scheduling và server-side queueing.

Không nên tắt TLS hoặc authentication chỉ để lấy performance tốt hơn. Bảo vệ remote JMX là yêu cầu quản trị riêng; tối ưu cần nằm trong thiết kế polling, batching, network placement và method cost.

Một custom MBean có thao tác write/invoke có thể gây ảnh hưởng nghiêm trọng nếu remote endpoint bị lộ, vì thế concurrency limiting còn gắn với security.

## 18. Độ trễ và timeout không đồng nghĩa thao tác đã thất bại

Trong một số tình huống, remote JMX client có thể timeout khi operation đang chạy. Điều đó **không tự chứng minh** operation trên server đã bị hủy hoặc rollback.

Ví dụ operation rebuildIndex đang chạy:

\`\`\`text
Client sends invoke
   |
   v
Server starts rebuild
   |
   +-- network timeout occurs
   |
   v
Rebuild may continue
\`\`\`

Do đó:

- Tránh retry operation không idempotent một cách mù quáng.
- Gắn request/job ID và trạng thái khi cần.
- Cho phép truy vấn kết quả/tiến trình bằng attribute hoặc operation nhẹ.
- Thiết kế cancellation/timeout ở tầng thực thi thật, không dựa vào client disconnect.
- Ghi audit để biết một operation đã bắt đầu và kết thúc hay chưa.

Một lần client nhận timeout có thể đồng thời là một tác vụ đang tiếp tục tiêu tốn CPU/I/O trong server.

## 19. So sánh JMX và metrics pipeline

JMX phù hợp với:

- Quan sát trạng thái Java runtime.
- Truy cập management operations.
- Đọc những attributes quản trị có tần suất thấp hoặc trung bình.
- Tích hợp công cụ JMX và MBeanServer sẵn có.

Metrics pipeline như Micrometer/Prometheus thường phù hợp khi:

- Thu thập counters, gauges, histograms liên tục.
- Cần aggregation/time-series và nhiều instances.
- Có lịch scrape rõ và backend chuyên lưu metrics.
- Muốn tránh remote JMX client tự poll một lượng lớn attribute tùy ý.

Tuy nhiên metrics exporter cũng có chi phí; gauge callback có thể thực hiện logic nặng. Không chuyển một getter đắt sang metrics mà giữ nguyên implementation rồi kỳ vọng overhead biến mất.

Nếu ứng dụng đã có Actuator/Micrometer, cân nhắc reuse counters/snapshots cho cả metrics và JMX facade để tránh tính toán trùng.

## 20. Tình huống thực tế

### Tình huống A — Dashboard poll mỗi giây

Một dashboard gọi \`getActiveSessions\` mỗi giây. Getter chạy truy vấn database COUNT(*) trên dữ liệu lớn.

Hậu quả: lượng query tăng theo số dashboards, gây tải và latency cho database. Giải pháp: duy trì counter hoặc cached snapshot, chọn interval hợp lý và đo độ mới.

### Tình huống B — JConsole làm ứng dụng chậm

Một MBean có attribute \`FullReport\` dựng báo cáo dài dưới synchronized lock. Khi operator mở tab MBeans, JConsole đọc attribute và giữ lock, gây gián đoạn business threads.

Giải pháp: thay bằng summary đã tính, tách computation, giới hạn output, tránh lock kéo dài.

### Tình huống C — RMI polling nhiều JVMs

Một collector quét hàng trăm JVM, mỗi JVM có hàng trăm attributes. Độ trễ và CPU tăng do số round trips, serialization và response size.

Giải pháp: giảm polling frequency, chọn attributes cần thiết, batch bằng getAttributes và đo mức tải.

### Tình huống D — Operation rebuild gây timeout

JMX client gọi operation rebuild kéo dài. Client timeout, retry và tạo hai công việc đồng thời.

Giải pháp: operation trả accepted/job ID nhanh, giới hạn concurrency, có trạng thái kết quả và quy tắc retry.

### Tình huống E — Truy vấn MBeanInfo mỗi lần

Monitoring agent gọi \`getMBeanInfo\` trước mọi \`getAttribute\`. Không cần thiết khi contract ổn định.

Giải pháp: cache metadata theo connection/instance, refresh khi lifecycle hoặc schema thay đổi.

## 21. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| CPU tăng khi bật JMX monitoring | Getter tính toán nặng hoặc poll quá dày | Profile getter, giảm tần suất, cache snapshot |
| JVM bị lock contention | Getter giữ synchronized lock dài | Giảm critical section, snapshot/atomic |
| Remote JMX latency cao | Network/serialization hoặc method cost | Đo client/server, batch, giảm payload |
| MBean operation timeout | Operation thực thi quá lâu | Async job/status/concurrency gate |
| Client timeout nhưng task vẫn chạy | Network timeout không hủy server-side execution | Kiểm soát lifecycle và idempotency |
| GC tăng sau polling | Getter tạo collection/string lớn | Trả summary nhỏ, giảm allocations |
| Monitoring data không nhất quán | Attributes được đọc ở các thời điểm khác nhau | Dùng snapshot có timestamp |
| Collector gây tải cao | Nhiều agents cùng poll | Điều phối polling, tránh duplicate reads |
| getAttributes vẫn chậm | Getter bên trong đắt | Tối ưu implementation |
| Metrics và JMX khác nhau | Cách lấy mẫu, độ mới hoặc đơn vị khác nhau | Chuẩn hóa semantics và snapshot |
| Operation bị gọi trùng | Retry hoặc nhiều clients | Idempotency, semaphore, audit |
| JMX remote bị mở rộng không an toàn | Tối ưu hiệu năng bằng cách tắt security | Giữ authentication/TLS và tối ưu phương pháp truy cập |

## 22. Checklist thiết kế một MBean có chi phí hợp lý

Trước khi công bố attribute:

1. Getter có thực hiện I/O hoặc gọi network không?
2. Có duyệt collection hoặc tạo object lớn không?
3. Có giữ lock ảnh hưởng nghiệp vụ không?
4. Giá trị có thể đọc từ Atomic*, volatile hoặc immutable snapshot không?
5. Cần độ mới bao nhiêu? Có thể cache an toàn không?
6. Output có giới hạn kích thước không?
7. Getter có side effects không?
8. Client dự kiến poll bao lâu một lần và có bao nhiêu clients?
9. Có metric tương đương sẵn có không?
10. Đã đo p95/p99 trong điều kiện tải thật chưa?

Trước khi công bố operation:

1. Có thể mất bao lâu?
2. Có thể block/giữ lock hoặc gọi downstream không?
3. Có làm thay đổi dữ liệu/availability không?
4. Có cần async job và status không?
5. Có concurrency limit và backpressure không?
6. Retry có an toàn và idempotent không?
7. Có timeout/cancellation phù hợp không?
8. Có authorization và audit không?
9. Nếu client disconnect, công việc trên server tiếp tục thế nào?
10. Có integration test qua MBeanServer không?

## 23. Bài tập thực hành

### Bài tập 1 — Getter rẻ và getter đắt

Tạo hai managed attributes:

- \`ProcessedJobs\`: đọc AtomicLong.
- \`PendingJobs\`: duyệt collection để đếm.

Dùng MBeanServer.getAttribute trong nhiều lần để quan sát thời gian xử lý và CPU. Ghi nhận số samples, phân biệt warmup và steady state. Không dùng kết quả một lần để kết luận.

### Bài tập 2 — getAttributes

Tạo MBean có \`QueueDepth\`, \`ProcessedJobs\` và \`Paused\`. So sánh đọc từng attribute qua getAttribute với đọc chung bằng getAttributes, đặc biệt nếu thử nghiệm bằng remote connector được bảo vệ.

### Bài tập 3 — Polling rate

Giả sử 300 MBeans, mỗi MBean 4 attributes, polling 15 giây. Tính tổng số reads/second; sau đó nhân với 3 independent collectors và thảo luận tác động khi getter tiêu tốn 2 ms CPU.

### Bài tập 4 — Operation dài

Tạo một operation giả lập công việc dài bằng test fixture, đo latency của JMX invoke và thử phương án trả \`ACCEPTED\` ngay rồi cập nhật trạng thái ở một attribute khác. Không chạy tác vụ nguy hiểm trên production.

### Bài tập 5 — Kiểm soát concurrency

Một operation \`rebuild\` được gọi đồng thời hai lần. Thiết kế Semaphore/AtomicBoolean gate để chỉ cho một request chạy. Test trạng thái \`BUSY\` của request thứ hai và cleanup flag khi task kết thúc.

## 24. Ghi nhớ cốt lõi

- **Đọc attribute và gọi operation qua JMX đều chạy code thật**; không có bảo đảm miễn phí về CPU, I/O, memory hoặc thời gian.
- Local MBeanServer có overhead quản trị; remote JMX thêm transport, serialization, network và security.
- Getter tốt thường nhẹ, đọc dữ liệu có sẵn, không side effects và tránh lock dài.
- Operation tốn nhiều thời gian nên có cơ chế async/status, concurrency limit và retry semantics rõ.
- Polling frequency × số attributes × số clients quyết định tổng lượng lời gọi.
- getAttributes có thể giảm remote round trips nhưng không loại bỏ chi phí bên trong getters.
- Đo p50/p95/p99 và profile ứng dụng trong điều kiện tải thật trước khi tối ưu.
- Không tắt JMX authentication/TLS để xử lý performance.
- Khi mục tiêu là high-volume metrics, cân nhắc Micrometer/metrics pipeline nhưng vẫn phải thiết kế callback/gauge nhẹ.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — ManagedAttribute: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — ManagedOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 API — MBeanServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 API — AttributeList: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/AttributeList.html
