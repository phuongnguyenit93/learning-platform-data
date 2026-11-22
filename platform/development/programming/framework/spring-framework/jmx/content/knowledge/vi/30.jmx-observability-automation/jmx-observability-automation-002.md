# Kết hợp JMX với metrics registry trong Spring Framework

## 1. Mục tiêu: nối khả năng quản trị JMX với hệ thống metrics

Java Management Extensions (JMX) là cơ chế quản trị và quan sát của JVM. Ứng dụng Java có thể đăng ký **MBean** vào `MBeanServer`, công bố attribute và operation để JConsole hoặc client JMX đọc trạng thái, thay đổi cấu hình vận hành hoặc nhận notification.

Trong khi đó, một **metrics registry** như Micrometer `MeterRegistry` là nơi ứng dụng ghi nhận các phép đo chuẩn hóa: counter, gauge, timer, distribution summary và các thẻ phân loại (tags). Dữ liệu được xuất sang hệ thống như Prometheus, Datadog hoặc một backend giám sát khác theo registry/exporter đã chọn.

Hai cơ chế có mục đích chồng lấn một phần nhưng **không đồng nhất**:

- JMX phù hợp cho **quản trị và chẩn đoán runtime**, gồm read-only attributes và operations.
- Metrics registry phù hợp cho **time-series monitoring**, aggregation, dashboard, alert và phân tích xu hướng.
- Nhiều JVM/platform MXBeans đã cung cấp dữ liệu về heap, thread, GC, class loading.
- Spring Boot Actuator và Micrometer có thể đưa nhiều JVM metrics vào registry mà **không cần tự viết MBean cho từng phép đo**.
- JMX exporter/collector cũng có thể đọc attribute MBean và biến thành metrics nếu cần tương thích với hệ thống JMX hiện có.

Bài này hướng dẫn chọn đường tích hợp, xây dựng ví dụ Spring, hiểu trade-off và tránh đếm trùng hoặc đưa metric/cardinality không phù hợp vào dashboard.

## 2. Bốn mô hình tích hợp phổ biến

```text
                     Java / Spring Application
                               |
             +-----------------+------------------+
             |                                    |
     MBeanServer (JMX)                      MeterRegistry
             |                                    |
     JConsole / JMX client                 Micrometer meters
             |                                    |
      JMX collector                        Registry exporter
             |                                    |
             +---------------+--------------------+
                             |
                      Metrics backend
                             |
                    Dashboard / Alerts
```

Có bốn đường lựa chọn:

| Mô hình | Dữ liệu đi theo đường nào? | Phù hợp khi |
|---|---|---|
| **A. JMX → collector → metrics** | MBean attribute được scrape và chuyển thành time series | Ứng dụng cũ đã có MBean, khó sửa instrumentation |
| **B. Application → Micrometer → backend** | Code ghi counter/gauge/timer vào `MeterRegistry` | Ứng dụng Spring mới cần dashboard/alert |
| **C. JVM/Micrometer binders** | Runtime/JVM metrics vào registry trực tiếp | Cần metrics heap, GC, CPU, thread ở chuẩn registry |
| **D. Kết hợp JMX + registry** | JMX giữ management operations, registry giữ telemetry | Muốn vừa điều khiển runtime vừa có giám sát time series |

Không nên triển khai cả A và B cho **cùng một số đo** mà không có quy ước ownership. Ví dụ một counter được ghi trực tiếp vào Micrometer và đồng thời được JMX collector scrape có thể xuất hiện thành hai series; dashboard tổng hợp sai nếu cộng cả hai.

## 3. Phân biệt MBean attribute và metric

Ví dụ JMX:

```java
@ManagedAttribute
public long getCompletedJobs() {
    return completedJobs.get();
}
```

JMX client có thể gọi `getAttribute(ObjectName, "CompletedJobs")` để lấy giá trị hiện tại.

Ví dụ Micrometer:

```java
Counter completed = registry.counter(
    "worker.jobs.completed",
    "queue", "orders"
);
completed.increment();
```

Cả hai có thể phản ánh số job đã hoàn tất, nhưng hệ thống hiểu dữ liệu theo semantics khác nhau:

| Khía cạnh | JMX attribute | Metrics meter |
|---|---|---|
| Định danh | ObjectName + attribute | Metric name + tags |
| Đọc dữ liệu | JMX API | Backend/exporter/registry |
| Lịch sử | Không mặc định lưu | Backend thường lưu time series |
| Kiểu | Primitive, String, OpenData hoặc kiểu được JMX hỗ trợ | Counter/gauge/timer/summary/distribution |
| Aggregation | Client phải tự thiết kế | Backend hỗ trợ truy vấn và tổng hợp |
| Operation | MBean có thể gọi operation | Meter thường không phải control API |
| Đơn vị | Thường do contract MBean mô tả | Có metadata/base unit tùy registry |
| Cardinality | ObjectName có nhiều properties | Tags cần kiểm soát chặt |

Một con số đọc được từ JMX **chưa tự động là counter**: cần biết nó tăng đơn điệu, reset khi nào và có thể giảm hay không. Một attribute `QueueDepth` là gauge, còn `CompletedJobsTotal` có thể là counter, nếu semantic thực tế phù hợp.

## 4. Chọn loại metric trước khi instrument

### 4.1. Counter

Counter biểu diễn tổng số sự kiện, thường tăng theo thời gian:

```java
Counter successCounter = registry.counter(
    "orders.processed",
    "outcome", "success"
);

successCounter.increment();
```

Không dùng Counter để biểu diễn queue depth, active thread hoặc số connection đang mở, vì các giá trị đó có thể tăng **và giảm**.

### 4.2. Gauge

Gauge biểu diễn một giá trị có thể tăng giảm:

```java
AtomicInteger queueDepth = new AtomicInteger();

Gauge.builder("orders.queue.depth", queueDepth, AtomicInteger::get)
    .description("Current number of waiting orders")
    .baseUnit("tasks")
    .register(registry);
```

Gauge thường đọc trạng thái object vào thời điểm scrape. Cần giữ tham chiếu mạnh đến object được gauge quan sát; tùy cơ chế registry, object không còn được giữ có thể bị GC và gauge không còn giá trị mong đợi.

### 4.3. Timer

Timer đo duration và số lần xảy ra:

```java
Timer timer = registry.timer(
    "orders.processing.duration",
    "result", "success"
);

timer.record(() -> processOrder());
```

Một Timer có thể xuất nhiều time series tùy registry/backend, chẳng hạn số lượng, tổng thời gian và histogram/percentiles khi cấu hình. Không tự cộng tất cả chúng như cùng một đại lượng.

### 4.4. DistributionSummary

Dùng khi đo kích thước/phân phối không nhất thiết là duration, ví dụ số byte mỗi message hoặc kích thước batch:

```java
DistributionSummary batchSizes = DistributionSummary.builder(
    "orders.batch.size"
).baseUnit("items").register(registry);

batchSizes.record(25);
```

**Metric type là quyết định về ngữ nghĩa**, không chỉ cách hiển thị. Một MBean getter có thể cung cấp raw value, còn registry cần xác định meter type cho phép backend tính rate, quantile hoặc histogram đúng.

## 5. Spring Boot Actuator và Micrometer

Trong Spring Boot, một hướng phổ biến là dùng Actuator + Micrometer để xuất metrics.

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

Version nên được quản lý bởi dependency management/BOM tương thích của dự án Spring Boot. Ví dụ này giả định ứng dụng dùng Boot phiên bản có hỗ trợ registry Prometheus tương ứng.

Cấu hình minh họa:

```properties
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.show-details=never
```

Khi registry và endpoint đã được auto-configure phù hợp, có thể quan sát dữ liệu qua:

```bash
curl http://localhost:8080/actuator/prometheus
```

Đường dẫn thực tế có thể thay đổi nếu cấu hình management base path/port riêng. Endpoint phải được bật và expose qua web; dependency chỉ là một phần điều kiện. Đồng thời cần áp dụng security policy và giới hạn quyền truy cập, không công khai endpoint quản trị bừa bãi.

**Lưu ý:** `/actuator/metrics` là API tra cứu metric theo tên, trong khi `/actuator/prometheus` là định dạng scrape Prometheus khi có registry tương ứng. Chúng không phải cùng một endpoint.

## 6. Ví dụ Spring: một trạng thái được xem qua JMX và Micrometer

Giả sử `QueueState` là nguồn dữ liệu duy nhất:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class QueueState {
    private final AtomicInteger depth = new AtomicInteger();
    private final AtomicLong processed = new AtomicLong();

    public void enqueued() {
        depth.incrementAndGet();
    }

    public void completed() {
        depth.updateAndGet(current -> Math.max(0, current - 1));
        processed.incrementAndGet();
    }

    public int depth() {
        return depth.get();
    }

    public long processedTotal() {
        return processed.get();
    }
}
```

State holder này giúp tránh hai phép đo độc lập mâu thuẫn nhau. Đưa nó vào Spring:

```java
@Configuration
public class QueueConfiguration {
    @Bean
    public QueueState queueState() {
        return new QueueState();
    }
}
```

Tiếp theo, tạo một MBean facade:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "company.queue:type=QueueMonitor,name=orders"
)
public class QueueJmxMonitor {
    private final QueueState state;

    public QueueJmxMonitor(QueueState state) {
        this.state = state;
    }

    @ManagedAttribute
    public int getQueueDepth() {
        return state.depth();
    }

    @ManagedAttribute
    public long getProcessedTotal() {
        return state.processedTotal();
    }
}
```

Một bean configuration đăng ký facade và bật annotation export:

```java
@Configuration
@EnableMBeanExport
public class QueueJmxConfiguration {

    @Bean
    public QueueJmxMonitor queueJmxMonitor(QueueState state) {
        return new QueueJmxMonitor(state);
    }
}
```

Đoạn này minh họa Spring Framework JMX; cần import các annotation từ `org.springframework.context.annotation` và cấu hình một `MBeanServer` phù hợp trong ứng dụng. Với Spring Boot đã có auto-configuration, không nhất thiết thêm `@EnableMBeanExport` thủ công; tránh tạo hai exporter cùng đăng ký một ObjectName.

## 7. Đăng ký Gauge từ cùng QueueState

Một configuration dùng `MeterRegistry`:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueueMetricsConfiguration {

    @Bean
    public QueueMetricsBinder queueMetricsBinder(
            QueueState state,
            MeterRegistry registry) {

        return new QueueMetricsBinder(state, registry);
    }

    static final class QueueMetricsBinder {
        QueueMetricsBinder(QueueState state, MeterRegistry registry) {
            Gauge.builder("orders.queue.depth", state, QueueState::depth)
                .description("Current queue depth")
                .baseUnit("tasks")
                .tag("queue", "orders")
                .register(registry);
        }
    }
}
```

Code có tính minh họa: trong một dự án lớn, một `MeterBinder` riêng thường phù hợp hơn vì gom logic đăng ký các meter và cho phép test dễ hơn.

Lưu ý về lifecycle: `QueueMetricsBinder` giữ `QueueState` qua field hoặc tham chiếu khác để đảm bảo object đo được giữ sống. Với ví dụ trên, cần bảo đảm `QueueState` là Spring singleton và tồn tại trong vòng đời registry.

Cả MBean `QueueDepth` và Micrometer gauge `orders.queue.depth` cùng đọc một trạng thái. Khi dùng cả hai, chọn **registry metrics** làm nguồn cho dashboard time series, còn JMX getter làm đường kiểm tra quản trị local. Nếu lại scrape JMX attribute này thành metric thứ hai, cần quy hoạch tránh đếm trùng.

## 8. Counter nên increment tại event, không đọc một số cộng dồn tùy ý

Nếu `QueueState.processedTotal()` tăng khi hoàn tất job, đây là counter nội bộ. Bạn có hai hướng:

### Hướng 1: ghi Micrometer Counter ở đúng nơi sự kiện xảy ra

```java
@Service
public class QueueWorker {
    private final QueueState state;
    private final Counter processedCounter;

    public QueueWorker(QueueState state, MeterRegistry registry) {
        this.state = state;
        this.processedCounter = registry.counter(
            "orders.processed",
            "queue", "orders"
        );
    }

    public void completedOneJob() {
        state.completed();
        processedCounter.increment();
    }
}
```

Hướng này phù hợp khi tất cả event đi qua đường code được instrument và counter semantics rõ ràng.

### Hướng 2: expose cumulative state như FunctionCounter

Trong một số trường hợp có state counter sẵn, có thể dùng `FunctionCounter` với object giữ số lượng tăng dần:

```java
FunctionCounter.builder(
    "orders.processed",
    state,
    QueueState::processedTotal
).tag("queue", "orders")
 .register(registry);
```

FunctionCounter phù hợp khi giá trị nguồn có tính đơn điệu theo lifecycle. Nếu `processedTotal` có thể reset do operation hoặc tái khởi tạo object, backend phải hiểu counter reset và logic export phù hợp.

Đừng dùng `Gauge` cho cumulative count rồi kỳ vọng hệ thống automatically suy ra counter rate đúng trong mọi trường hợp. Chọn meter theo semantic số liệu.

## 9. Tích hợp MBean hiện có qua JMX collector

Nếu ứng dụng Java cũ đã có MBean nhưng chưa có Micrometer, có thể thu metrics từ JMX qua một collector/exporter.

```text
Legacy Java Application
   |
   +-- MBeanServer
          |
          +-- java.lang:type=Memory
          +-- company.queue:type=QueueMonitor,name=orders
          |
       JMX exporter / collector
          |
       Prometheus-compatible metrics
          |
       Metrics backend
```

Một collector có thể dùng JMX API đọc:

```java
ObjectName name = new ObjectName(
    "company.queue:type=QueueMonitor,name=orders"
);

Number depth = (Number) connection.getAttribute(
    name, "QueueDepth"
);
```

Sau đó chuyển thành sample metric dạng gauge. Cần map ObjectName/attribute sang metric name, labels và unit. Việc mapping này phụ thuộc loại collector. **Không có một cấu hình YAML universal** dùng được cho mọi JMX exporter.

Với Prometheus JMX exporter, có nhiều chế độ triển khai như Java agent hoặc standalone collector, tùy phiên bản và kiến trúc; mỗi kiểu có cách kết nối và bảo mật khác nhau. Chọn theo môi trường triển khai thay vì tự mở remote JMX port công khai.

### 9.1. Khi nào JMX collector tốt hơn sửa ứng dụng?

- Ứng dụng cũ ít thay đổi source code.
- JVM/library đã công bố MBean đầy đủ.
- Team muốn thu metrics nhanh từ nguồn đã có.
- Có yêu cầu giám sát platform MBeans của một service bên thứ ba.
- Cần liên kết vận hành hiện tại với monitoring backend mới.

### 9.2. Khi nào Micrometer trực tiếp tốt hơn?

- Có quyền sửa ứng dụng Spring.
- Cần timer/histogram/tags phong phú.
- Muốn kiểm soát metric naming và unit ngay trong code.
- Cần context như outcome/status mà MBean không cung cấp.
- Muốn reuse meter qua nhiều registry/backend.

Trong hệ thống mới, Micrometer thường là lựa chọn hợp lý cho instrumentation; JMX vẫn hữu ích cho management operations và runtime diagnostics.

## 10. Mapping ObjectName sang metric name và labels

JMX định danh bằng ObjectName:

```text
company.queue:type=QueueMonitor,name=orders
```

Một metrics backend có thể nhận:

```text
orders_queue_depth{queue="orders",service="checkout"} 12
```

Đây là một ví dụ mô tả, không có nghĩa mọi exporter tự sinh tên này. Cần quyết định mapping:

| Thành phần JMX | Thành phần metric | Ví dụ |
|---|---|---|
| Domain | Prefix hoặc namespace | `company.queue` → `orders_` |
| `type` | Meter family / label | `QueueMonitor` |
| `name` | Label nguồn | `queue="orders"` |
| Attribute | Metric semantic | `QueueDepth` → `queue_depth` |
| Unit | Metric unit/base unit | Tasks, seconds, bytes |
| ObjectName instance | Instance label | `instance="worker-1"` nếu cần |

Naming metric cần ổn định xuyên deploy và tránh đổi chỉ vì refactor tên Java class. Nếu một ObjectName đổi từ `name=orders` thành `name=primary`, collector rule hoặc labels có thể thay đổi; dashboard và alert cần migration plan.

## 11. Metric type, unit và OpenData

JMX attribute có nhiều dạng:

- `int`, `long`, `double`, `boolean`.
- `String`, enum hoặc giá trị trạng thái.
- `CompositeData` và `TabularData` từ MXBean/OpenType.
- Array hoặc object data được JMX chuyển đổi theo hợp đồng.

Không phải mọi giá trị đều chuyển thành numeric time series trực tiếp.

Ví dụ `java.lang:type=Memory` có `HeapMemoryUsage` kiểu `CompositeData`, chứa các trường như `used`, `committed`, `max`, `init`.

Một collector có thể chọn:

```text
jvm_memory_used_bytes{area="heap"}
jvm_memory_committed_bytes{area="heap"}
jvm_memory_max_bytes{area="heap"}
```

Nhưng cần kiểm tra từng trường: `max` có thể có giá trị đặc biệt khi giới hạn không xác định; không coi mọi giá trị đều là số byte hữu hiệu để biểu diễn phần trăm.

Với boolean, cách diễn giải là một quy ước metric, ví dụ `1` tương ứng true và `0` false. Với trạng thái nhiều giá trị như `RUNNING`, `PAUSED`, `FAILED`, nên sử dụng một encoding/tag có cardinality được kiểm soát, không đưa toàn bộ message tự do thành label.

## 12. Cardinality: rủi ro thường bị bỏ qua

Cardinality là số time series khác nhau sinh từ tổ hợp metric name và label values.

Ví dụ:

```text
orders_processed_total{queue="orders",outcome="success"}
orders_processed_total{queue="orders",outcome="failure"}
```

Cardinality nhỏ và có giới hạn.

Nhưng nếu thêm label `userId`, `orderId`, `requestId` hoặc `sessionToken`, số time series có thể tăng vô hạn theo số người dùng/giao dịch:

```text
orders_processed_total{orderId="O-000001"}
orders_processed_total{orderId="O-000002"}
...
```

Hậu quả là tăng bộ nhớ, chi phí lưu trữ, thời gian scrape và query; đồng thời có thể lộ dữ liệu nhạy cảm.

JMX ObjectName đôi khi chứa các key property sinh động theo từng instance/request. Khi biến ObjectName properties thành metric labels, **không copy vô điều kiện tất cả key**. Nên chọn nhãn có tập giá trị hữu hạn như `queue`, `outcome`, `region` hoặc `worker_pool` nếu cần.

Một chính sách label tốt:

1. Không chứa user ID, session ID, credential hoặc dữ liệu giao dịch.
2. Có số giá trị hợp lý và dự đoán được.
3. Tránh giá trị tự do như exception message.
4. Không lưu object ID của từng request.
5. Được tài liệu hóa và giữ ổn định khi nâng cấp.
6. Có giới hạn số series và cảnh báo cardinality khi vượt ngưỡng.

## 13. Tránh thu trùng JVM metrics

Một JVM có thể cung cấp memory/GC/thread metrics từ:

- Platform MXBeans qua JMX collector.
- Micrometer JVM binders trong Spring Boot Actuator.
- Một Java agent hoặc monitoring agent khác.

Nếu cả ba đường cùng export metric tương đương, backend có thể lưu ba bộ số liệu với tên và labels khác nhau. Việc này không nhất thiết gây lỗi ngay, nhưng dashboard có thể nhầm nguồn hoặc cộng trùng.

Ví dụ:

```text
JMX collector -> jvm_memory_used_bytes
Micrometer    -> jvm_memory_used_bytes
Agent khác    -> vendor_jvm_heap_used
```

Nếu cùng semantic và cùng target, hãy định nghĩa một owner chính cho dashboard/alert. Khi cần giữ nhiều pipeline để đối chiếu, dùng nhãn nguồn rõ và không tổng hợp chúng như ba JVM khác nhau.

### 13.1. Đối chiếu metric không có nghĩa cộng metric

Một cách migration an toàn:

```text
Trong staging:
  Micrometer series A
  JMX collector series B
  Compare A vs B theo thời điểm/scope

Trong production:
  Chọn A làm nguồn chính
  B chỉ dùng diagnostic hoặc tắt collection dư
```

Counter có thể reset theo process restart, gauge lấy mẫu tại hai thời điểm khác nhau và timer histogram có cấu hình bucket khác nhau. Vì vậy không mong mọi giá trị luôn bằng tuyệt đối.

## 14. Metrics không thay thế JMX operations

MeterRegistry chủ yếu dành cho ghi nhận phép đo, không phải hệ thống gọi quản trị có side effect. JMX có thể cung cấp operation:

```java
@ManagedOperation
public void pauseConsumers() {
    queueController.pause();
}
```

Một `Counter` hoặc `Gauge` không thay thế được khả năng gọi `pauseConsumers()`. Nếu cần vừa xem trạng thái vừa thao tác quản trị, có thể:

- Dùng Micrometer cho metrics time series.
- Dùng JMX MBean hạn chế cho operation quản trị.
- Bảo vệ connector và operation bằng authorization.
- Ghi audit cho lệnh quan trọng.
- Không phơi bày operation nhạy cảm qua cùng quyền của tài khoản scraping nếu không cần.

Đây là lý do nên tách **monitoring plane** và **management plane** về mặt kiến trúc, dù cả hai cùng liên quan quan sát ứng dụng.

## 15. JMX notification và metrics registry

JMX notification là event push, không mặc định là time-series metric. Một listener có thể chuyển thông báo thành số đếm:

```java
NotificationListener listener = (event, handback) -> {
    if ("company.queue.threshold.exceeded".equals(event.getType())) {
        registry.counter(
            "queue.threshold.events",
            "queue", "orders"
        ).increment();
    }
};
```

Hướng này hữu ích khi event có ý nghĩa vận hành và không có nơi instrumentation trực tiếp. Nhưng cần xét:

- Notification có thể mất khi listener chưa đăng ký.
- Cùng một event có thể tới nhiều registration và bị đếm trùng.
- Reconnect không tự replay lịch sử.
- Event type và payload có thể thay đổi giữa các phiên bản.
- Listener callback không nên block hoặc truy vấn backend nặng.

Nếu sự kiện là giao dịch nghiệp vụ quan trọng, nên instrument ngay tại nơi event phát sinh hoặc dùng durable messaging thay vì dựa vào JMX notification làm nguồn counter duy nhất.

## 16. Metadata và cách kiểm tra qua MBeanServer

Để kiểm tra metric nguồn trước khi cấu hình collector:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "company.queue:type=QueueMonitor,name=orders"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "%s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
```

Chỉ đưa những **readable attributes** phù hợp vào collector. Không đọc writable attribute chỉ vì writable; thuộc tính writable vẫn có thể đọc được nhưng có ý nghĩa điều khiển và có thể chứa dữ liệu nhạy cảm.

Tránh gọi JMX operations như `resetCounters`, `clearCache`, `restartService` để thu metric. Collector nên đọc trạng thái, không thay đổi trạng thái.

## 17. Kiểm tra qua MeterRegistry trong unit test

Với Micrometer, dùng `SimpleMeterRegistry` để test instrumentation mà không cần backend thật.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();

Counter counter = registry.counter(
    "worker.jobs.completed",
    "queue", "orders"
);

counter.increment();
counter.increment();

double value = registry.get("worker.jobs.completed")
    .tag("queue", "orders")
    .counter()
    .count();

assertEquals(2.0, value);
registry.close();
```

`assertEquals` cần import từ JUnit. Trong một test, nên đóng registry bằng `try-with-resources` nếu implementation hỗ trợ `AutoCloseable`, hoặc dùng `finally`.

Test này chứng minh meter được đăng ký và tăng như kỳ vọng; nó **không chứng minh Prometheus endpoint đã expose** hoặc collector thật đã scrape.

## 18. Integration test: JMX và registry cùng xem một state

Một test phù hợp:

1. Tạo `QueueState`.
2. Tạo Spring context với `QueueJmxMonitor` và exporter.
3. Dùng MBeanServer test riêng.
4. Đăng ký `Gauge` từ cùng `QueueState` vào `SimpleMeterRegistry`.
5. Thay đổi state bằng thao tác `enqueued()`/`completed()`.
6. Đọc `QueueDepth` qua JMX.
7. Đọc gauge `orders.queue.depth` qua registry.
8. Assert hai giá trị cùng phản ánh state sau cập nhật.
9. Đóng Spring context, registry và release MBeanServer.

Ví dụ ý tưởng:

```java
state.enqueued();
state.enqueued();

int jmxDepth = (Integer) server.getAttribute(
    objectName, "QueueDepth"
);

double micrometerDepth =
    registry.get("orders.queue.depth")
        .tag("queue", "orders")
        .gauge()
        .value();

assertEquals(2, jmxDepth);
assertEquals(2.0, micrometerDepth);
```

Vì đây là integration test với server/registry local, không cần bật JMX remote connector. Nếu dùng Spring Boot, `@SpringBootTest` có thể tạo thêm metrics tự động; cân nhắc dùng context nhỏ để cô lập đúng contract cần test.

## 19. Metrics pipeline và dashboard

Một hệ thống metrics đầy đủ có các bước:

```text
Application instrumentation
       |
MeterRegistry
       |
Registry export / scrape endpoint
       |
Collector (ví dụ Prometheus)
       |
Time-series storage
       |
Dashboard + Alert rules
```

Điểm kiểm tra ở từng tầng:

| Tầng | Kiểm tra |
|---|---|
| Application | Counter increment và gauge thay đổi đúng |
| MeterRegistry | Meter name/tags/type có tồn tại |
| Export endpoint | Dữ liệu xuất ra đúng định dạng |
| Scrape | Target UP và scrape thành công |
| Backend | Series xuất hiện, timestamp hợp lệ |
| Dashboard | Query đúng metric name/labels |
| Alert | Threshold và missing-data behavior đúng |

Với JMX collector, thay tầng đầu bằng `MBeanServer → JMX collector`, nhưng các tầng backend/dashboard vẫn tương tự.

**Một ứng dụng start thành công không chứng minh metrics đã tới backend.** Mỗi tầng có thể bị lỗi do security, config, naming, network hoặc selector.

## 20. Đơn vị, rate và reset

Các số đo thời gian có thể được lưu bằng nanoseconds trong code nhưng export theo seconds tại backend; memory bytes có thể xuất cùng tên với unit suffix như `_bytes`; counter Prometheus thường có suffix `_total`. Tên thực tế phụ thuộc registry/exporter và naming convention.

Không đoán đơn vị từ tên ngắn không có metadata.

### Counter reset

Khi JVM restart, một in-memory counter thường quay về 0. Backend time-series có thể cung cấp hàm `rate()` hoặc `increase()` xử lý reset theo phương pháp phù hợp. Không tự lấy `current - previous` mà bỏ qua restart.

### Gauge và rate

Gauge `queue_depth` có thể tăng giảm; lấy rate của gauge không có cùng ý nghĩa với tốc độ event. Nếu cần throughput, tạo counter `jobs_completed_total` rồi tính rate.

### Latency

Timer/histogram cần hiểu base unit và bucket configuration. Một `p99` được tính từ nhiều instance không thể luôn lấy trung bình các `p99` riêng lẻ để có p99 toàn hệ thống. Histogram bucket aggregation hoặc thống kê phù hợp có thể cần thiết.

## 21. Chi phí và nguy cơ performance

Giám sát không phải miễn phí:

- JMX getter có thể chạy trên thread của collector/JMX server và gây tải nếu nó truy vấn database hoặc tính toán object graph lớn.
- Micrometer gauge function có thể được gọi lúc scrape, nên logic phải nhanh và an toàn.
- Timer percentile/histogram tăng số series và chi phí bộ nhớ.
- High-cardinality tags tăng chi phí lưu trữ.
- Collector scrape quá dày làm tăng CPU/network.
- Nhiều exporter cùng đọc một resource có thể nhân tải quan sát.

Thiết kế tốt:

1. Getter/gauge lấy giá trị snapshot đã được cập nhật bởi luồng nghiệp vụ.
2. Không giữ lock dài trong callback metrics.
3. Giới hạn tag values.
4. Chọn scrape interval phù hợp.
5. Dùng sampling khi cần cho tracing/logging thay vì đưa mọi request vào metric labels.
6. Không export raw exception message hoặc user data.
7. Có timeout và trạng thái stale/unavailable khi nguồn không còn trả dữ liệu.

## 22. Security cho JMX và metrics endpoint

JMX có thể cung cấp operation thay đổi runtime, còn metrics endpoint có thể tiết lộ cấu trúc ứng dụng, tên service hoặc tình trạng phụ thuộc. Cả hai đều cần kiểm soát.

### JMX

- Không mở remote JMX port công khai.
- Dùng authentication và TLS/kênh bảo vệ phù hợp.
- Hạn chế quyền `invoke` và `setAttribute` của tài khoản monitoring.
- Chỉ export MBean cần thiết và tránh secret.
- Quản lý credential, truststore và network policy.

### Metrics endpoint

- Chỉ expose `/actuator/prometheus` đến collector/segment được phép.
- Có thể đặt management port/path riêng và bảo vệ bằng network rules.
- Không thêm user ID, token hoặc request payload vào tags.
- Giám sát số series và ingestion cost.
- Không coi metric endpoint hoàn toàn “không nhạy cảm” chỉ vì thường read-only.

Tách monitoring read-only khỏi management operations khi có thể. Một account scraping metrics không nên mặc định có quyền reset counters, reload config hoặc restart worker qua JMX.

## 23. Những lỗi thường gặp

### 23.1. JConsole thấy MBean nhưng Prometheus không có metric

MBean registration và metrics export là hai đường khác nhau. Cần cấu hình collector hoặc Micrometer registry để đưa số liệu tới Prometheus. Chỉ bật Spring JMX không tạo `/actuator/prometheus`.

### 23.2. /actuator/metrics có số nhưng /actuator/prometheus không hoạt động

Có thể thiếu Prometheus registry dependency, endpoint chưa expose, management port/path khác hoặc security chặn. Kiểm tra cấu hình hiệu lực và endpoint availability.

### 23.3. Gauge luôn 0 hoặc NaN

Kiểm tra object được gauge quan sát có còn sống, callback đọc đúng state, và nguồn số liệu thực sự thay đổi. Nếu state được tạo lại nhưng gauge vẫn giữ reference cũ, giá trị sẽ không như dự kiến.

### 23.4. Counter giảm sau restart

In-memory counter reset khi process restart. Dùng rate/increase phù hợp ở backend và phân biệt metric reset với lỗi nghiệp vụ.

### 23.5. Metric bị đếm đôi

Cùng số đo có thể được xuất qua Micrometer và JMX collector. Chọn ownership và mapping thống nhất; không cộng hai series phản ánh cùng nguồn.

### 23.6. Dashboard mất data sau đổi ObjectName

JMX collector selector có thể không match tên mới; metric label có thể đổi. Kiểm tra `queryNames`, collector rules, metric series và dashboard query.

### 23.7. Cardinality tăng vọt

Không đưa `orderId`, `userId`, `requestId` hoặc ObjectName dynamic properties vào metric labels. Dùng label hữu hạn, kiểm soát theo quy tắc.

### 23.8. JMX getter gây quá tải

Getter đọc dữ liệu nặng hoặc lấy lock dài khiến collector ảnh hưởng production. Thay bằng snapshot counter/gauge lightweight, caching và scrape interval có kiểm soát.

### 23.9. Đọc MXBean OpenData nhưng mapping sai

`CompositeData` và `TabularData` cần chọn trường cụ thể, kiểu và unit phù hợp. Không ép nguyên object thành numeric value.

### 23.10. Tưởng Micrometer thay thế toàn bộ JMX

Micrometer rất mạnh cho metrics nhưng không cung cấp thay thế trực tiếp cho mọi JMX management operation hoặc notification. Hai cơ chế giải quyết mục tiêu khác nhau.

## 24. Bài tập thực hành

**Bài 1 — Một state, hai góc quan sát.** Tạo `QueueState`, export `QueueDepth` qua JMX và gauge `orders.queue.depth` qua SimpleMeterRegistry. Thay đổi state và xác nhận hai giá trị.

**Bài 2 — Counter throughput.** Instrument `orders.processed` bằng Counter trong event path. Đọc counter trong test, rồi giải thích cách Prometheus có thể tính rate sau scrape.

**Bài 3 — JMX collector mapping.** Chọn `company.queue:type=QueueMonitor,name=orders` và `QueueDepth`. Thiết kế metric name, label, unit và type. Giải thích điều gì xảy ra nếu ObjectName đổi.

**Bài 4 — Cardinality.** So sánh label `queue=orders` với `orderId=<id>`; ước lượng số series khi số order tăng. Thiết kế cách thay bằng counter tổng hợp.

**Bài 5 — Double collection.** Giả lập cùng số đếm được xuất qua Micrometer và JMX exporter. Viết quy tắc chọn primary source cho dashboard để không đếm đôi.

**Bài 6 — Spring Boot Actuator.** Thêm Actuator + Prometheus registry, expose endpoint phù hợp và kiểm tra `/actuator/prometheus`. Đối chiếu với các MBean trong JConsole.

**Bài 7 — Event notification.** Tạo JMX notification threshold, listener chuyển event type thành counter. Thảo luận mất event và duplicate delivery.

**Bài 8 — Monitoring security.** Thiết kế policy read-only metrics endpoint và JMX operation quyền cao riêng biệt. Không sử dụng credential hard-coded.

**Bài 9 — JVM binders.** Kiểm tra memory/GC/thread metrics của Micrometer và platform MXBeans. Liệt kê cặp số đo trùng semantics để quyết định không thu trùng.

**Bài 10 — CI test.** Viết integration test dùng MBeanServer test riêng và SimpleMeterRegistry, kiểm tra ObjectName/attribute/metric name/tags cùng lifecycle cleanup.

## 25. Câu hỏi tự kiểm tra

1. JMX MBean và Micrometer MeterRegistry khác nhau ở mục tiêu nào?
2. Vì sao không phải mọi JMX attribute đều phù hợp làm counter?
3. QueueDepth nên là gauge hay counter?
4. Khi nào nên dùng FunctionCounter?
5. Vì sao một JMX collector có thể phù hợp với ứng dụng legacy?
6. Vì sao không nên xuất cùng một JVM metric qua nhiều pipeline rồi cộng chúng?
7. High-cardinality tags gây rủi ro gì?
8. `CompositeData` từ MXBean cần được xử lý như thế nào?
9. `/actuator/metrics` khác `/actuator/prometheus` ở đâu?
10. Khi nào nên giữ JMX operation thay vì thay bằng metrics?
11. Vì sao metric `queue_depth` bị mất không có nghĩa queue depth bằng 0?
12. Một test có thể xác minh JMX và Micrometer cùng đọc đúng state bằng cách nào?

## 26. Ghi nhớ

**JMX và metrics registry bổ sung cho nhau.** JMX cung cấp bề mặt quản trị của JVM, còn Micrometer/MeterRegistry giúp chuẩn hóa và xuất metrics thành time series phục vụ dashboard và alert. Có thể đọc các MBean hiện có qua JMX collector hoặc instrument trực tiếp bằng Micrometer.

Khi kết hợp, hãy chọn nguồn dữ liệu chính, định nghĩa đúng metric type và unit, kiểm soát tags/cardinality, tránh đếm trùng, kiểm tra toàn bộ pipeline tới backend và bảo vệ cả JMX connector lẫn metrics endpoint. Mục tiêu cuối cùng là quan sát chính xác mà không tạo gánh nặng hay bề mặt rủi ro không cần thiết.
