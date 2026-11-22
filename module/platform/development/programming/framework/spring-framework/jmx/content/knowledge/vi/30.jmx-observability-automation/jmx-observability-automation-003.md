# Đồng bộ giá trị JMX vào hệ thống giám sát trong Spring Framework

## 1. Bài toán thực tế

Spring Framework cho phép export trạng thái ứng dụng thành JMX attributes và operations. Ví dụ một MBean quản lý hàng đợi có các attributes `PendingJobs`, `FailedJobs`, `Enabled` và `LastSuccessTimestamp`. Người vận hành có thể xem chúng bằng JConsole, nhưng việc mở JConsole thủ công không đủ để theo dõi hàng chục hoặc hàng trăm JVM.

Ta cần **đồng bộ các giá trị JMX thành dữ liệu giám sát**: lấy mẫu định kỳ, chuyển đổi định danh và kiểu dữ liệu, lưu chuỗi thời gian, dựng dashboard, phát cảnh báo và kiểm tra chất lượng dữ liệu thu thập.

```text
Spring application
    |
    +--> MBeanExporter
    |         |
    |         v
    |      MBeanServer
    |         |
    |         +--> JMX collector / javaagent
    |                    |
    |                    v
    |              metrics endpoint
    |                    |
    |                    v
    |               monitoring system
    |                    |
    |             dashboard / alerts
    |
    +--> Micrometer metrics (đường khác)
                     |
                     v
                metrics registry
```

Hai đường JMX và Micrometer có thể tồn tại song song. Cần biết metric nào là nguồn dữ liệu chính để tránh trùng lặp, chênh lệch naming, cardinality và ngữ nghĩa.

Sau bài học, bạn sẽ:

1. Thiết kế pipeline lấy JMX attributes vào hệ thống giám sát.
2. Phân biệt polling, scraping, notifications và push.
3. Chọn MBeans/attributes phù hợp cho metric.
4. Mapping `ObjectName` và attribute sang tên metric, labels và giá trị.
5. Phân biệt gauge, counter, timestamp, enum/status và histogram.
6. Hiểu vai trò của JMX Exporter, Prometheus, Micrometer và Spring Boot Actuator.
7. Kiểm soát độ trễ, dữ liệu thiếu, lỗi kết nối và bảo mật.
8. Viết kiểm thử xác minh contract JMX và pipeline thu thập.
9. Thiết kế dashboard và alert dựa trên tín hiệu vận hành thực sự.

## 2. “Đồng bộ” ở đây là gì?

Đồng bộ giá trị JMX không nhất thiết là replication tức thời. Trong hệ thống giám sát, phổ biến nhất là **lấy mẫu** theo khoảng thời gian.

Ví dụ:

```text
T=00s: PendingJobs = 12
T=15s: PendingJobs = 18
T=30s: PendingJobs = 7
T=45s: PendingJobs = 0
```

Hệ thống monitoring lưu các điểm đo này như một time series. Nếu queue tăng lên 100 rồi giảm xuống 18 trong khoảng giữa hai lần scrape, polling 15 giây có thể **không bao giờ thấy đỉnh 100**.

Phải phân biệt:

- **Current state:** giá trị attribute tại thời điểm đọc.
- **Sample:** giá trị đã quan sát ở một lần collection.
- **Time series:** các samples có cùng tên metric và nhãn.
- **Notification:** tín hiệu sự kiện/trạng thái chuyển đổi, không mặc định lưu bền vững.
- **Event/audit record:** lịch sử sự kiện nếu cần độ chính xác đầy đủ.

Không mô tả scrape metrics như cơ chế guaranteed delivery cho mọi biến động trạng thái.

## 3. Các kiến trúc thu thập phổ biến

### 3.1. JMX Exporter Java agent và Prometheus

Một kiến trúc thường gặp là chạy JMX Exporter như Java agent trong JVM ứng dụng, cho phép nó đọc JMX MBeans và xuất metrics ở endpoint HTTP dành cho Prometheus scrape.

```text
Spring JVM
   |
   +-- MBeans in platform MBeanServer
   |
   +-- JMX Exporter javaagent
          |
          v
   HTTP /metrics endpoint
          |
          v
      Prometheus
          |
          v
     Dashboard + alerts
```

Đây là mô hình thu thập **in-process**, khác với việc Prometheus trực tiếp kết nối JMX/RMI. Javaagent đọc MBeans bên trong process, không nhất thiết cần mở remote JMX connector.

### 3.2. Standalone collector qua remote JMX

Một collector riêng có thể kết nối qua `JMXConnector` tới JMX/RMI endpoint.

```text
Application JVM
   |
   v
JMX/RMI connector
   |
   v
Standalone collector
   |
   v
Metrics backend
```

Cách này tách collector khỏi ứng dụng nhưng yêu cầu xử lý network, authentication, TLS, RMI ports, reconnect và authorization. Nếu collector ở bên ngoài JVM, cần bảo đảm connector thực sự gắn với `MBeanServer` chứa MBeans mong muốn.

### 3.3. Spring Boot Actuator và Micrometer

Spring Boot Actuator có tích hợp Micrometer để cung cấp metrics qua registry và endpoint phù hợp. Đây là đường instrumentation có thể tránh đọc JMX cho các metrics được ứng dụng ghi nhận trực tiếp.

```text
Spring component
    |
    v
Micrometer MeterRegistry
    |
    +--> /actuator/prometheus (nếu bật registry/endpoint)
    +--> other supported registries
```

**JMX Exporter và Micrometer không phải cùng một thành phần.** Nếu dữ liệu đang được ghi trực tiếp qua Micrometer, cân nhắc để Micrometer làm nguồn metric chính và chỉ dùng JMX để lấy những dữ liệu legacy hoặc JVM/library MBeans không có đường khác.

## 4. Thành phần Spring JMX trong pipeline

Spring Framework có thể export bean:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicLong;

@Component
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Checkout")
public class CheckoutQueueMonitor {

    private final AtomicLong enqueued = new AtomicLong();
    private final AtomicLong completed = new AtomicLong();

    @ManagedAttribute(
        description = "Current checkout jobs waiting")
    public long getPendingJobs() {
        return Math.max(0L, enqueued.get() - completed.get());
    }

    @ManagedAttribute(
        description = "Total enqueued jobs since process start")
    public long getEnqueuedTotal() {
        return enqueued.get();
    }

    @ManagedAttribute(
        description = "Total completed jobs since process start")
    public long getCompletedTotal() {
        return completed.get();
    }

    public void enqueued() {
        enqueued.incrementAndGet();
    }

    public void completed() {
        completed.incrementAndGet();
    }
}
```

Đây là mô hình minh họa; nếu số job có thể đồng thời enqueue/complete, công thức gauge cần phản ánh trạng thái chính xác của hệ thống. Nếu một tác vụ thất bại hoặc được hủy, counter hoàn thành không đủ để suy ra số pending; production cần định nghĩa semantics rõ và tránh dữ liệu âm/mất nhất quán.

Để annotation hoạt động, cần cấu hình exporter phù hợp, ví dụ Spring `@EnableMBeanExport` hoặc `AnnotationMBeanExporter` đúng ApplicationContext. Việc class có annotation không tự bảo đảm MBean đã đăng ký.

Một collector sau đó đọc:

```text
ObjectName:
  com.example.orders:type=Queue,name=Checkout

Attributes:
  PendingJobs
  EnqueuedTotal
  CompletedTotal
```

và chuyển thành metrics thích hợp.

## 5. Phân loại kiểu metric

| JMX attribute | Kiểu giá trị | Metric gợi ý | Ghi chú |
|---|---|---|---|
| `PendingJobs` | `long` | Gauge | Có thể tăng/giảm |
| `EnqueuedTotal` | `long` | Counter-like | Tăng dần theo process lifetime |
| `CompletedTotal` | `long` | Counter-like | Có thể reset khi JVM restart |
| `Enabled` | `boolean` | Gauge 0/1 | Cần định nghĩa rõ trạng thái |
| `LastSuccessTimestamp` | Epoch seconds | Gauge timestamp | Đơn vị và timezone rõ ràng |
| `State` | String/enum | Enum mapping hoặc info metric | Không biến arbitrary string thành label |
| `ProcessDuration` | `long` | Gauge nếu chỉ last duration | Không suy ra histogram từ một giá trị |
| `ErrorRate` | `double` | Gauge | Cần biết window và mẫu số |

Không thể tự biến một attribute chỉ chứa giá trị cuối cùng thành histogram có phân phối latency. Nếu muốn đo P95/P99, hãy instrument histogram/timer thực sự hoặc thu thập bucket/count/sum có semantics phù hợp.

### 5.1. Counter có thể reset

Counter JMX thường được tính từ lúc JVM khởi động. Khi process restart, giá trị trở về 0. Prometheus có những hàm như `rate()`/`increase()` để xử lý counter resets trong một số trường hợp, nhưng metric phải giữ kiểu ngữ nghĩa counter và các labels ổn định.

Không lấy hiệu của hai samples rồi coi giá trị âm là lỗi nghiệp vụ nếu xảy ra restart. Cần kết hợp process start time, reset semantics và tình trạng collector.

### 5.2. Gauge không phải counter

`PendingJobs` có thể giảm khi worker xử lý xong. Dùng counter cho nó sẽ tạo nhận định sai vì counter được kỳ vọng tăng trừ khi reset. Chọn đúng metric type giúp biểu đồ và alerts có nghĩa.

## 6. Mapping ObjectName và attribute sang metric

JMX identifier:

```text
com.example.orders:type=Queue,name=Checkout
```

có thể chuyển thành:

```text
app_queue_pending_jobs{queue="Checkout"} 12
app_queue_enqueued_total{queue="Checkout"} 1870
app_queue_completed_total{queue="Checkout"} 1858
```

Một mapping cần quyết định:

1. Metric namespace/prefix.
2. Tên metric có đơn vị.
3. Labels nào lấy từ ObjectName properties.
4. Attribute nào được chọn/loại.
5. Kiểu metric (gauge/counter).
6. Quy tắc chuẩn hóa tên.
7. Cách xử lý missing/null/non-numeric values.

**Không tự động biến mọi key property thành label.** ObjectName có thể chứa instance ID, UUID, session ID hoặc giá trị có cardinality cao.

### 6.1. Cardinality

Nếu `queue` có 5 giá trị, metrics tạo ít series. Nếu `requestId` có một triệu giá trị, việc gắn làm label có thể làm backend quá tải.

Quy tắc:

- Label cho nhóm ít biến thể: `module`, `queue`, `region`, `role`.
- Tránh `userId`, `requestId`, UUID, random instance identity.
- Không đưa token, email hoặc raw message vào label.
- Review mapping khi thêm MBeans hoặc key properties mới.
- Đặt giới hạn sample/series phù hợp ở collector/backend.

## 7. Ví dụ mapping cấu hình JMX Exporter

Một ví dụ YAML **minh họa cấu trúc** rule đọc attribute từ MBeans có domain và properties phù hợp:

```yaml
rules:
  - pattern: 'com.example.orders<type=Queue, name=([^,]+)><>PendingJobs'
    name: app_queue_pending_jobs
    type: GAUGE
    labels:
      queue: '$1'

  - pattern: 'com.example.orders<type=Queue, name=([^,]+)><>EnqueuedTotal'
    name: app_queue_enqueued_total
    type: COUNTER
    labels:
      queue: '$1'

  - pattern: 'com.example.orders<type=Queue, name=([^,]+)><>CompletedTotal'
    name: app_queue_completed_total
    type: COUNTER
    labels:
      queue: '$1'
```

Cú pháp pattern và cách JMX Exporter biểu diễn ObjectName/attributes phụ thuộc phiên bản, đặc biệt với ObjectName có thêm key properties, quoting và sanitization. Trong triển khai thực tế, phải chạy exporter phiên bản đang sử dụng và kiểm tra output `/metrics`; ví dụ này không thay việc xác nhận rules match. Với môi trường có metadata phức tạp, dùng rule cụ thể và giới hạn attributes để tránh expose ngoài ý muốn.

### 7.1. Javaagent startup

Ví dụ hình thức:

```bash
java -javaagent:/opt/jmx-exporter/jmx_prometheus_javaagent.jar=9404:/etc/jmx-exporter/config.yaml \
  -jar app.jar
```

Tên file và cú pháp flags cần đối chiếu phiên bản JMX Exporter được dùng. Khi triển khai container, port 9404 có thể bị publish ngoài ý định; cần giới hạn network exposure. Không dùng ví dụ này để tự động mở endpoint công khai.

### 7.2. Lấy mẫu output

```text
# HELP app_queue_pending_jobs Current pending jobs
# TYPE app_queue_pending_jobs gauge
app_queue_pending_jobs{queue="Checkout"} 12
# TYPE app_queue_enqueued_total counter
app_queue_enqueued_total{queue="Checkout"} 1870
```

Kiểm tra metric naming, labels, values, HELP/TYPE và số series thực tế. Nếu metric thiếu, phải tìm ở JMX registration, rule matching và collector logs trước khi sửa dashboard.

## 8. Polling trực tiếp bằng MBeanServerConnection

Không phải hệ thống nào cũng dùng Prometheus. Có thể viết một collector đọc JMX định kỳ.

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxSampler {
    private final MBeanServerConnection connection;
    private final ObjectName name;

    public JmxSampler(MBeanServerConnection connection,
                      ObjectName name) {
        this.connection = connection;
        this.name = name;
    }

    public long pendingJobs() throws Exception {
        Object value = connection.getAttribute(
            name, "PendingJobs");

        if (!(value instanceof Number number)) {
            throw new IllegalStateException(
                "PendingJobs is not numeric: " +
                (value == null ? "null" : value.getClass()));
        }
        return number.longValue();
    }
}
```

Một caller có thể dùng `ScheduledExecutorService` để chạy định kỳ:

```java
ScheduledExecutorService scheduler =
    Executors.newSingleThreadScheduledExecutor();

scheduler.scheduleWithFixedDelay(() -> {
    try {
        long pending = sampler.pendingJobs();
        metricsRecorder.recordPending(pending);
    } catch (Exception ex) {
        metricsRecorder.recordCollectionFailure(ex);
    }
}, 0, 15, TimeUnit.SECONDS);
```

`sampler` và `metricsRecorder` cần được inject/định nghĩa. `scheduleWithFixedDelay` chạy lượt tiếp theo sau khi lượt trước hoàn tất và thời gian delay đã trôi qua; nó giảm nguy cơ chồng nhiều lượt trên một scheduler thread. Cần đóng scheduler đúng lifecycle và tránh logging payload nhạy cảm.

### 8.1. MBeanServerConnection local và remote

`MBeanServer` triển khai `MBeanServerConnection`, nên collector local có thể dùng:

```java
MBeanServerConnection connection =
    ManagementFactory.getPlatformMBeanServer();
```

Với remote connector, cần lấy connection qua `JMXConnector` và cấu hình bảo mật. Remote `getAttribute` có thể thất bại do TLS, RMI port, authentication, network partition hoặc server restart. Không mở remote JMX trên Internet chỉ để collector đọc một gauge.

## 9. Lựa chọn scrape interval

Tần suất thu thập phải cân bằng độ chính xác thời gian và chi phí.

| Khoảng lấy mẫu | Ưu điểm | Đổi lại |
|---|---|---|
| 1–5 giây | Nhạy với biến động ngắn | Tải đọc/JMX/metrics cao, nhiều samples |
| 15 giây | Phổ biến cho monitoring thực tế | Có thể bỏ qua spike ngắn |
| 30–60 giây | Giảm tải | Alert và phân tích kém nhanh hơn |
| 5 phút | Phù hợp chỉ số thay đổi chậm | Không phù hợp sự cố cần phát hiện sớm |

Không có interval đúng cho mọi metric. Nếu attribute getter đọc database hoặc thực hiện tính toán nặng, scrape mỗi giây có thể gây tải ngược lên ứng dụng.

Cần biết:

- Getter có O(1) hay thực hiện I/O?
- Có cache snapshot phù hợp không?
- Scrape duration có thấp hơn interval không?
- Có bao nhiêu targets và attributes?
- Dashboard/alert có yêu cầu độ phân giải cao không?
- Có cần lịch sử phân phối thay vì chỉ snapshot?

### 9.1. Tránh overlap và thundering herd

Hàng trăm collector cùng poll vào đầu mỗi phút có thể tạo spike. Có thể điều chỉnh stagger/jitter, scrape scheduling và giới hạn concurrency. Với Prometheus, scrape scheduling do server kiểm soát; với custom collector, cần chủ động lập lịch.

## 10. JMX getter phải an toàn cho polling

Một `@ManagedAttribute` getter có thể bị gọi nhiều lần không báo trước.

Anti-pattern:

```java
@ManagedAttribute
public int getPendingJobs() {
    return database.countPendingJobs(); // Có thể chậm.
}
```

Nếu database chậm, monitoring trở thành nguyên nhân tăng tải.

Một thiết kế cân nhắc cache/snapshot:

```java
private final AtomicInteger pendingSnapshot =
    new AtomicInteger();

@ManagedAttribute
public int getPendingJobs() {
    return pendingSnapshot.get();
}

public void updateSnapshot(int current) {
    pendingSnapshot.set(current);
}
```

Phải định nghĩa độ mới của snapshot và cơ chế cập nhật. Dữ liệu cũ nhưng ổn định không nên bị trình bày như dữ liệu real-time tuyệt đối.

### 10.1. Không có side effects trong getter

Một getter giám sát không nên xóa cache, trigger refresh hay tạo transaction ghi dữ liệu. Nếu cần refresh, tách operation rõ ràng với quyền riêng và tránh để scrape vô tình tạo thao tác nghiệp vụ.

## 11. Dữ liệu thiếu, stale và lỗi thu thập

Các tình huống:

- MBean chưa được đăng ký.
- MBean bị unregister khi context đóng.
- Collector không tìm thấy ObjectName.
- Attribute bị đổi tên hoặc type.
- Client thiếu quyền.
- JVM/connector không reachable.
- Scrape vượt timeout.
- Parser/mapping rule không match.
- Giá trị attribute không phải số.

Không nên thay lỗi thu thập bằng `0` một cách âm thầm. `0` có nghĩa “queue không có job”, còn “không lấy được dữ liệu” là trạng thái khác.

### 11.1. Ba tình trạng cần phân biệt

```text
Observed value = 0:
  collector thành công, queue thật sự có zero jobs

No sample:
  collector không lấy được dữ liệu

Stale sample:
  mẫu cũ còn được UI hiển thị nhưng đã lỗi thời
```

Dashboard nên cho thấy tình trạng target/collector và timestamp gần nhất. Một biểu đồ flat line sau khi JVM chết có thể là dấu hiệu hệ thống đang giữ mẫu cũ thay vì ingest dữ liệu mới.

### 11.2. Prometheus up metric

Prometheus dùng `up` để cho biết scrape target có thành công hay không. Tuy nhiên `up=1` chỉ cho biết target scrape được; nó **không bảo đảm mọi JMX rule đều match hoặc mọi MBean attribute được thu thập đúng**. Cần thêm checks cho sự hiện diện của metrics quan trọng và exporter errors nếu có.

## 12. Thiết kế alert có ý nghĩa

Một alert tốt cần có tín hiệu, điều kiện bền vững và ngữ cảnh:

```text
Queue backlog:
  app_queue_pending_jobs > 100
  duy trì 5 phút
```

PromQL minh họa:

```promql
app_queue_pending_jobs{queue="Checkout"} > 100
```

Một rule có thể dùng `for: 5m` để giảm cảnh báo khi spike ngắn:

```yaml
groups:
  - name: app-queues
    rules:
      - alert: CheckoutQueueBacklog
        expr: app_queue_pending_jobs{queue="Checkout"} > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Checkout queue backlog remains high"
```

Ngưỡng 100 và 5 phút là giả định bài tập, cần tuning theo tải và SLO thực tế. Nếu metric bị thiếu vì target down, rule này có thể không fire như kỳ vọng; phải có alert riêng cho scrape failure và metric absence.

### 12.1. Alert cho missing metrics

Một metric quan trọng biến mất có thể là sự cố export/mapping chứ không phải business value về zero. Prometheus hỗ trợ hàm như `absent()`, nhưng cách dùng cần tính đến labels và targets. Cần phân biệt target down, exporter lỗi và metric không match.

### 12.2. Alert theo tỷ lệ

Nếu `EnqueuedTotal` và `CompletedTotal` là counters đúng nghĩa, có thể theo dõi:

```promql
rate(app_queue_enqueued_total[5m])
-
rate(app_queue_completed_total[5m])
```

Khi có nhiều queues/instances, cần group labels phù hợp trước khi trừ. Kết quả là thay đổi throughput trung bình, không phải giá trị `PendingJobs` chính xác từng thời điểm. Không dùng một alert rate duy nhất thay cho gauge backlog nếu cần biết hàng chờ hiện tại.

## 13. Khi nào dùng JMX Notification thay polling?

Notification có thể báo khi ngưỡng hoặc trạng thái thay đổi:

```text
Queue crosses threshold
        |
        v
JMX Notification
        |
        v
Event listener
        |
        v
Trigger investigation
```

Nhưng remote notifications có thể bị mất khi disconnect, listener quá tải hoặc process restart. Vì thế pattern bền vững thường là:

1. Notification báo “state changed”.
2. Collector/client đọc lại attributes authoritative.
3. Time-series monitoring tiếp tục scrape định kỳ.
4. Nếu cần lịch sử sự kiện chính xác, lưu vào event log riêng.

Không đẩy mọi request thành JMX notification rồi mong monitoring backend dùng nó như hệ thống streaming bền vững.

## 14. So sánh JMX Exporter và Micrometer

| Tiêu chí | JMX Exporter | Micrometer |
|---|---|---|
| Đọc dữ liệu từ | Existing MBeans/JMX metadata | Instrumented meters trong app |
| Phù hợp | Legacy MBeans, JVM/third-party JMX | New application metrics |
| Naming | Rule-based ObjectName/attribute mapping | Meter names và tags |
| Metric types | Phụ thuộc mapping và JMX values | Counters, gauges, timers, distribution summaries |
| Cardinality | Cần giới hạn ObjectName-derived labels | Cần giới hạn tags |
| Overhead | JMX getter/collector overhead | Meter instrumentation/scrape overhead |
| Integration | Java agent/standalone exporter | Spring Boot Actuator/registries |
| Điểm yếu | Mapping phức tạp, có thể mất semantic | Cần instrument code và registry phù hợp |

Nếu ứng dụng đã dùng Micrometer `Counter` và JMX cũng export `CompletedTotal`, có thể tạo hai metrics cùng ý nghĩa với tên và thời điểm cập nhật khác nhau. Nên chọn một nguồn metric chính hoặc tài liệu hóa rõ sự khác biệt để tránh double counting.

## 15. Kiểm thử contract JMX trước khi mapping

Một integration test có thể xác minh JMX attributes:

```java
import org.junit.jupiter.api.Test;
import javax.management.*;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class QueueJmxContractTest {

    @Test
    void expectedAttributesArePresent() throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("test");

        // Tạo Spring context và inject server này vào exporter.
        // Sau khi exporter đăng ký CheckoutQueueMonitor:

        ObjectName name = new ObjectName(
            "com.example.orders:type=Queue,name=Checkout");

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName().equals("PendingJobs")
                && a.isReadable()));

        Object value = server.getAttribute(name, "PendingJobs");

        assertTrue(value instanceof Number);
    }
}
```

Đây là khung minh họa: test phải thực sự tạo Spring context và exporter sử dụng cùng `server` trước assertions. Việc chỉ tạo server rỗng rồi assert sẽ không pass.

### 15.1. Test sau khi thay exporter/AOP

Thêm `@Transactional` hoặc thay proxy strategy có thể làm metadata export thay đổi tùy cấu hình. Test cần khẳng định ObjectName, attribute names và numeric types vẫn ổn định. Monitoring mapping phụ thuộc contract này.

## 16. Kiểm thử exporter output

Với JMX Exporter chạy trong lab, test nên kiểm tra HTTP output:

```bash
curl -fsS http://127.0.0.1:9404/metrics
```

Sau đó xác nhận:

- `app_queue_pending_jobs` tồn tại.
- Metric có value và labels dự kiến.
- Kiểu `gauge`/`counter` đúng semantics.
- Không có dynamic labels như request ID.
- Không có secret trong HELP, labels hoặc values.
- Khi MBean unregister, exporter không tiếp tục báo metric stale như dữ liệu mới.
- Khi attribute type thay đổi, collector error được nhận biết.
- Scrape duration và số series trong giới hạn.

Không sử dụng endpoint HTTP công khai để “kiểm tra nhanh” nếu nó chứa metrics nội bộ. Test local hoặc qua management network đã bảo vệ.

## 17. Test pipeline end-to-end

Một bài test tích hợp cần đi qua nhiều tầng:

```text
Spring test app
   |
   v
MBean registered
   |
   v
JMX Exporter mapping
   |
   v
HTTP metrics
   |
   v
Prometheus scrape (test stack)
   |
   v
Query result / alert
```

Một test fixture có thể:

1. Khởi động app với server và exporter cố định.
2. Đưa queue state từ 0 lên 5 bằng test API.
3. Xác minh JMX attribute trả 5.
4. Scrape exporter và xác minh gauge bằng 5.
5. Scrape qua Prometheus test container rồi query.
6. Đưa state về 0, xác minh metric cập nhật.
7. Restart app, kiểm tra counter reset và labels.
8. Thay đổi ObjectName có chủ đích để xác minh contract test phát hiện breakage.
9. Kiểm tra management endpoint không public.
10. Cleanup processes, ports và test data.

Không coi một `curl` trả HTTP 200 là end-to-end success nếu metric mapping chưa được kiểm tra.

## 18. Thời gian, timestamp và timezone

Time-series systems thường gắn timestamp lúc scrape/ingest. Một JMX attribute `LastSuccessTimestamp` mang ý nghĩa business timestamp riêng. Cần phân biệt:

```text
Sample timestamp:
  lúc collector thu thập giá trị

Business timestamp:
  lúc batch thành công lần cuối
```

Một metric:

```text
app_worker_last_success_timestamp_seconds 1794376800
```

nên dùng epoch seconds nếu tên metric kết thúc bằng `_seconds`. Không để milliseconds trong metric `_seconds`, vì sẽ làm biểu đồ và alert sai.

Độ trễ từ lần thành công cuối:

```promql
time() - app_worker_last_success_timestamp_seconds
```

Nếu timestamp chưa từng được thiết lập, cần convention rõ (metric absent hoặc sentinel value). Không dùng `0` mà không giải thích vì nó đại diện thời điểm epoch, không phải “chưa biết” theo mặc định.

## 19. Thu thập nhiều JVM và labels ổn định

Trong môi trường có nhiều instances, Prometheus thường bổ sung target labels như `job` và `instance`. JMX Exporter có thể bổ sung labels từ ObjectName.

Ví dụ:

```text
app_queue_pending_jobs{
  job="orders-service",
  instance="10.0.0.12:9404",
  queue="Checkout"
} 12
```

Khi autoscaling, `instance` có thể thay đổi. Dashboard cấp service nên aggregate theo `job`, `queue` hoặc labels bền vững khác.

Ví dụ:

```promql
sum by (job, queue) (app_queue_pending_jobs)
```

Không tổng hợp mọi instance nếu mỗi instance export cùng một global value được duplicate, vì sẽ double count. Cần hiểu metric mô tả **per-instance state** hay **cluster-wide state**.

### 19.1. Horizontal scaling

Khi có 10 replicas, mỗi replica có một local queue size và metric riêng, tổng có thể phản ánh backlog chung nếu các queues không trùng. Nhưng nếu mỗi replica query một central database và cùng report số pending toàn cụm, sum 10 replicas sẽ nhân 10. Chọn `max`, `avg` hoặc source duy nhất tùy semantics, không mặc định dùng sum.

## 20. Bảo mật pipeline monitoring

JMX có thể chứa thông tin nhạy cảm và operations thay đổi trạng thái. Collector chỉ cần đọc metrics không nên được trao quyền quản trị rộng.

Các nguyên tắc:

1. Ưu tiên lấy số liệu qua exporter in-process hoặc endpoint bảo vệ, tránh mở remote JMX nếu không cần.
2. Nếu dùng remote JMX, cấu hình authentication, TLS và network segmentation.
3. Dùng principal chỉ đọc khi phù hợp, không cho phép invoke destructive operations.
4. Giới hạn exposure của metrics endpoint tới monitoring network.
5. Không ghi secret trong ObjectName, attribute descriptions, metric labels.
6. Không expose toàn bộ MBeans bằng wildcard quá rộng nếu không cần.
7. Review third-party MBeans vì có thể chứa dữ liệu ngoài dự kiến.
8. Giới hạn request rate/scrape concurrency để tránh gây tải lên JVM.
9. Theo dõi failed authentication và metric scrape errors.
10. Kiểm tra effective configuration sau deployment; container ports có thể bị publish ngoài ý định.

Một `/metrics` endpoint không có authentication nhưng chỉ bind loopback có thể phù hợp cho sidecar trong môi trường được kiểm soát; không suy ra cách đó an toàn nếu network namespace được chia sẻ hoặc port bị forward.

## 21. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
|---|---|---|
| MBean hiển thị trong JConsole nhưng metric không có | Rule không match hoặc exporter đọc server khác | `MBeanInfo`, exporter logs, `/metrics` |
| Metric bị đổi tên sau update | ObjectName/attribute naming changed | Contract tests |
| Metric có giá trị 0 bất thường | Collector thay lỗi bằng zero | Logs và raw `getAttribute` |
| Metric biến mất sau restart | Exporter chưa register hoặc ObjectName đổi | Check lifecycle/identity |
| Alert không fire khi app chết | Condition chỉ xem business gauge | Alert `up`/absence |
| Scrape chậm | Getter làm I/O nặng hoặc quá nhiều MBeans | Thread dump và scrape duration |
| Backend tăng series nhanh | Labels cardinality cao | Count series by label |
| Counter giảm | JVM restart hoặc reset logic | Process start time và counter semantics |
| Tổng backlog quá lớn | Double count global metric ở nhiều replicas | Kiểm tra scope và aggregation |
| Remote collector lỗi kết nối | RMI host/port, TLS, auth, network | Connector diagnostics |
| Dashboard còn đường phẳng khi app down | Stale/cached data | Timestamp, `up` và ingest status |
| Alert lặp liên tục | Chọn ngưỡng/window không phù hợp | SLO, `for`, alert grouping |

### 21.1. Một quy trình chẩn đoán có thứ tự

```text
1. Spring bean/exporter có đăng ký MBean?
2. Đúng ObjectName/MBeanServer?
3. MBeanInfo có attribute?
4. getAttribute trả đúng kiểu và giá trị?
5. Collector/JMX Exporter rule match?
6. /metrics có metric và labels mong đợi?
7. Prometheus scrape có thành công?
8. Query/dashboard đã aggregate đúng?
9. Alert xử lý missing/stale data?
10. Security và resource cost có chấp nhận?
```

Không bắt đầu bằng việc sửa dashboard khi nguồn JMX chưa được xác minh.

## 22. Checklist thiết kế production

- [ ] Inventory MBeans/attributes được thu thập.
- [ ] Mỗi metric có tên, đơn vị, type và mô tả rõ.
- [ ] ObjectName và attribute names có contract ổn định.
- [ ] Getter nhẹ, read-only và không gây side effect.
- [ ] Chỉ export metrics cần thiết; không scrape mọi thứ.
- [ ] Labels không có cardinality cao hoặc dữ liệu nhạy cảm.
- [ ] Counter reset/restart được hiểu đúng.
- [ ] Có metric scrape health và alert cho missing data.
- [ ] Interval/timeout phù hợp với chi phí getter.
- [ ] Không có duplicate metrics giữa Micrometer/JMX.
- [ ] Có integration test JMX → exporter → monitoring.
- [ ] Remote connector và metrics endpoint được bảo vệ.
- [ ] Có dashboard và alerts dựa trên semantics chính xác.
- [ ] Có quy trình đổi tên metrics và migration dashboard.
- [ ] Có rollback plan khi thay đổi exporter rules.

## 23. Bài tập thực hành

### Bài tập A — Tạo một JMX gauge

Tạo Spring bean `@ManagedResource` có `@ManagedAttribute getPendingJobs()`. Đăng ký bằng Spring JMX exporter, dùng `MBeanServerConnection.getAttribute` xác nhận giá trị.

### Bài tập B — Mapping exporter

Tạo rule JMX Exporter ánh xạ `PendingJobs` thành `app_queue_pending_jobs` với `queue` label. Scrape endpoint local và so sánh với raw JMX value. Kiểm tra behavior khi đổi ObjectName.

### Bài tập C — Counter reset

Tạo `CompletedTotal` tăng dần. Restart ứng dụng lab để mô phỏng reset, kiểm tra chart/query `rate` và giải thích vì sao không coi reset là business negative throughput.

### Bài tập D — Cardinality

Thêm `requestId` vào ObjectName của các MBeans thử nghiệm. Quan sát số series tăng khi collector dùng `requestId` làm label. Sửa mapping chỉ giữ `module` và `queue`.

### Bài tập E — Alert thiếu dữ liệu

Tạo alert backlog vượt ngưỡng và alert scrape failure. Dừng app rồi kiểm tra: chỉ condition backlog có thể không hoạt động, nhưng target health alert phải phát hiện sự cố.

### Bài tập F — JMX và Micrometer

Instrument cùng một counter nghiệp vụ bằng Micrometer và một JMX getter. So sánh names, reset semantics và thời gian cập nhật. Chọn một nguồn chính cho dashboard và nêu lý do.

### Bài tập G — Nhiều replicas

Cho ba instances cùng export queue gauge. Thực hành `sum by(queue)`, `max by(queue)` và `avg by(queue)` trên dataset lab. Giải thích phép tổng hợp nào phản ánh đúng business backlog.

## 24. Câu hỏi tự kiểm tra

1. Khác nhau giữa JMX polling và JMX notification là gì?
2. JMX Exporter javaagent có luôn cần remote JMX port không?
3. Vì sao `PendingJobs` nên là gauge?
4. Khi nào `CompletedTotal` có thể reset?
5. Vì sao không nên đưa request ID vào metric label?
6. `up=1` có bảo đảm mọi JMX metric được thu thập không?
7. Scrape interval quá ngắn gây rủi ro gì?
8. Vì sao getter JMX không nên gọi database nặng?
9. Khác nhau giữa sample timestamp và business timestamp?
10. Khi nào tổng metrics trên nhiều replicas gây double counting?
11. Micrometer và JMX Exporter khác nhau ở điểm nào?
12. Vì sao cần alert cho missing/stale data?

## 25. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Prometheus JMX Exporter: https://prometheus.github.io/jmx_exporter/
- JMX Exporter Configuration: https://prometheus.github.io/jmx_exporter/1.4.0/http-mode/rules/
- Prometheus Metrics Concepts: https://prometheus.io/docs/concepts/metric_types/
- Prometheus Querying Functions: https://prometheus.io/docs/prometheus/latest/querying/functions/
- Spring Boot Actuator Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer Documentation: https://docs.micrometer.io/micrometer/reference/
- Java SE 21 — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

**Ghi nhớ:** đồng bộ JMX sang hệ thống giám sát là chuyển **trạng thái JMX thành samples có semantics rõ**, không phải sao chép mọi event theo thời gian thực. Muốn pipeline tin cậy, hãy chuẩn hóa metric type và labels, giữ JMX getter nhẹ, theo dõi dữ liệu thiếu/stale, bảo vệ endpoints và kiểm thử từ MBean tới dashboard.
