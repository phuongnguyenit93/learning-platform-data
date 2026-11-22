# Phân biệt dữ liệu JMX với logs, traces và metrics

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **JMX** là cơ chế quản lý và giám sát tài nguyên Java, trong khi **logs**, **traces** và **metrics** là các loại tín hiệu quan sát có mục đích riêng.
- Phân biệt JMX **attribute**, **operation**, **notification** với bản ghi log, trace/span và điểm đo metric.
- Nhận biết dữ liệu số đọc từ JMX có thể được **chuyển thành metrics dạng time series**, nhưng JMX không đồng nghĩa với một hệ thống lưu trữ metrics.
- Chọn tín hiệu phù hợp để trả lời câu hỏi vận hành: *trạng thái hiện tại? có lỗi gì? request đi qua đâu? xu hướng và mức độ ảnh hưởng ra sao?*
- Hiểu cách JConsole, JMX exporter, Micrometer, Spring Boot Actuator và OpenTelemetry có thể cùng tham gia vào hệ thống quan sát.
- Liên hệ nhiều tín hiệu để điều tra một sự cố mà không nhầm lẫn **nguồn dữ liệu**, **giao thức thu thập** và **dạng dữ liệu lưu trữ**.

## 2. Một sự cố, nhiều cách quan sát

Giả sử dịch vụ xử lý đơn hàng bắt đầu chậm. Người vận hành có bốn nhu cầu:

1. Xem **thread pool hiện có bao nhiêu thread đang chạy**.
2. Biết **đã xảy ra lỗi gì** tại thời điểm tốc độ xử lý giảm.
3. Xác định **request chậm ở service hay dependency nào**.
4. Quan sát **tỷ lệ lỗi và thời gian đáp ứng tăng như thế nào trong 30 phút**.

Các câu hỏi này liên quan nhau nhưng không có một công cụ hay dạng dữ liệu nào tối ưu cho tất cả.

| Cần biết | Tín hiệu/cơ chế thường phù hợp | Ví dụ |
|---|---|---|
| Trạng thái tài nguyên Java hiện tại | JMX attribute | `ThreadCount`, `ActiveCount`, `QueueSize` |
| Một sự kiện lỗi cụ thể và ngữ cảnh của nó | Log | `ERROR Failed to process order` |
| Đường đi của một request và thời gian ở từng bước | Distributed trace | Span `POST /orders` → DB query → payment HTTP call |
| Xu hướng, tần suất, tỷ lệ theo thời gian | Metric time series | `http.server.requests`, error rate, JVM heap used |
| Thực hiện hành động quản trị được cho phép | JMX operation | `clearCache()`, `resetStatistics()` |
| Nhận sự kiện quản trị khi MBean phát ra | JMX notification | Queue vượt ngưỡng hoặc component chuyển trạng thái |

Điều đầu tiên phải phân biệt là **JMX là một management API/protocol ecosystem của Java**; còn logs, traces và metrics thường được gọi là những **observability signals**. Chúng có phần giao nhau: một số số đo từ JMX chính là nguồn cho metrics, và JMX notifications có thể được chuyển thành event/log ở hệ thống khác.

## 3. JMX cung cấp loại dữ liệu nào?

JMX, viết tắt của **Java Management Extensions**, cho phép công cụ quản trị truy cập các đối tượng quản lý **MBean** bên trong JVM. Một MBean được đăng ký trong `MBeanServer` dưới một `ObjectName`.

Ví dụ ObjectName:

```text
java.lang:type=Memory
java.lang:type=Threading
com.example.shop.orders:type=Queue,name=outbox
```

Dữ liệu JMX thường được chia thành ba nhóm.

### 3.1. Attributes — trạng thái hoặc số đo hiện tại

Một attribute có thể là số, boolean, chuỗi hoặc kiểu dữ liệu tương thích khác.

Ví dụ:

```text
MBean: java.lang:type=Threading
Attribute: ThreadCount
Giá trị tại lần đọc: 84
```

Điều này có nghĩa là client đã đọc số thread ở **thời điểm gọi**; bản thân attribute không cung cấp sẵn chuỗi lịch sử 84 → 90 → 120 qua nhiều phút. Muốn có lịch sử, một collector phải đọc định kỳ và lưu các mẫu theo thời gian.

JMX attributes cũng không nhất thiết là metric số. Ví dụ một MBean có attribute `State="PAUSED"` hoặc `Healthy=true`. Một số attribute chứa cấu trúc như `CompositeData`, không phải scalar metric có thể đưa thẳng vào biểu đồ.

### 3.2. Operations — hành động quản trị

MBean có thể công bố method dưới dạng JMX operation, chẳng hạn:

```text
clearCache()
pauseConsumer()
resetStatistics()
```

Client dùng `MBeanServer.invoke()` để gọi operation. **Operation không phải metric, log hoặc trace**. Nó là khả năng điều khiển, có thể tạo tác động thật lên trạng thái ứng dụng. Bảo vệ quyền truy cập và chỉ công bố các operation cần thiết.

### 3.3. Notifications — sự kiện quản trị

MBean có thể phát `javax.management.Notification` khi xảy ra một thay đổi quan trọng:

```text
type: com.example.shop.queue.threshold.exceeded
source: com.example.shop.orders:type=Queue,name=outbox
message: Queue size exceeded 1000
```

Notification là tín hiệu event theo cơ chế push tới listener đã đăng ký. Nó khác với log ở đối tượng nhận và API, đồng thời không mặc định có tính lưu bền, truy vấn lịch sử hay replay cho listener bị ngắt kết nối.

**Kết luận cho JMX:** Cơ chế này hỗ trợ **quan sát và điều khiển tài nguyên được quản lý**, trong đó dữ liệu có thể là giá trị hiện tại, operation hoặc event. Nó không phải một kho lưu trữ chung cho logs, traces và metrics.

## 4. Logs: những bản ghi cho biết điều gì đã xảy ra

**Log** là một bản ghi có nội dung mô tả một sự kiện hoặc hành vi trong ứng dụng. Trong Java/Spring, log thường được tạo qua SLF4J cùng logging backend như Logback.

Ví dụ:

```text
2026-11-11T10:01:32Z ERROR order-worker
trace_id=2ab9... order_id=ORD-1023
Failed to call inventory service: timeout after 3000ms
```

Một log hữu ích thường có:

- **Timestamp** và mức độ `INFO`, `WARN`, `ERROR`.
- **Logger/service/component** phát log.
- **Message** mô tả sự kiện.
- **Structured fields** như request ID, trace ID, error code, dependency.
- **Exception/stack trace** khi cần điều tra lỗi.

Log có thể nói *vì sao một thao tác lỗi* hoặc cung cấp chi tiết của trường hợp cụ thể mà một metric tổng hợp không thể phản ánh.

Ví dụ Java:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderWorker {
    private static final Logger log =
            LoggerFactory.getLogger(OrderWorker.class);

    public void process(String orderId) {
        try {
            // Xử lý đơn hàng.
            log.info("Order processed: orderId={}", orderId);
        } catch (RuntimeException ex) {
            log.error("Order failed: orderId={}", orderId, ex);
            throw ex;
        }
    }
}
```

Ví dụ chỉ minh họa lời gọi logger; ứng dụng thực tế cần cân nhắc dữ liệu nhạy cảm, tần suất log và việc tránh tạo nhiều bản ghi lỗi trùng lặp. Log không nhất thiết có cấu trúc chuẩn cho tính toán thống kê, dù hệ thống log hiện đại có thể trích xuất field và tổng hợp chúng.

### Log khác JMX ở đâu?

- Log thường được **phát thành bản ghi** mỗi khi code thực hiện hành động ghi log.
- JMX attribute thường được **đọc khi có yêu cầu** từ client.
- Log ghi lại ngữ cảnh của sự kiện; JMX có thể cho biết trạng thái hiện tại của một thành phần.
- Log có thể được lưu bền và tìm kiếm bởi logging platform; JMX MBeanServer tự nó không phải công cụ lưu log lịch sử.

Ví dụ, nếu một database pool cạn kết nối, log có thể có câu `Connection acquisition timed out`, còn JMX có thể cho biết `ActiveConnections=30` và `IdleConnections=0` ngay lúc điều tra.

## 5. Traces: request đã đi qua những bước nào?

**Distributed tracing** theo dõi đường đi và thời gian của một thao tác hoặc request qua nhiều thành phần. Một trace thường gồm nhiều **spans**.

Ví dụ request tạo đơn hàng:

```text
Trace: POST /orders                      620 ms
|
+-- Span: OrderController                620 ms
    |
    +-- Span: ValidateOrder               15 ms
    |
    +-- Span: InventoryClient             410 ms
    |   |
    |   +-- Span: HTTP GET /inventory     405 ms
    |
    +-- Span: OrdersRepository           130 ms
```

Mỗi span thường chứa:

- Một **operation name** và khoảng thời gian bắt đầu/kết thúc.
- **Trace ID** để ghép các span thuộc cùng trace.
- **Span ID** và thông tin quan hệ cha–con.
- Thuộc tính như HTTP method, route, database operation hoặc service.
- Trạng thái lỗi và đôi khi event/exception liên quan.

Traces hữu ích khi người vận hành hỏi: *request chậm ở đâu?* Một JMX MBean có thể hiển thị pool đang nghẽn nhưng thường không mô tả toàn bộ đường đi của request cụ thể từ controller qua database và HTTP client.

### Trace khác log và JMX

- Trace mô tả **đường đi và thời gian** của một execution flow.
- Log cung cấp **thông điệp sự kiện** từ một điểm trong code.
- JMX mô tả **trạng thái/khả năng quản lý** của một component Java.
- Tracing có thể bị **sampling**: không phải mọi request luôn có trace được lưu.
- Kết nối logs với traces thường dùng trường `trace_id`/`span_id`; không tự động suy ra mối liên hệ nếu ứng dụng không phát metadata tương ứng.

JMX `ObjectName` và trace ID là hai khái niệm khác nhau. ObjectName định danh một MBean trong MBeanServer; trace ID định danh một execution trace trong hệ thống tracing.

## 6. Metrics: giá trị định lượng thay đổi theo thời gian

**Metric** là phép đo định lượng dùng để phản ánh hành vi và hiệu năng hệ thống. Metric thường được lưu dưới dạng time series:

```text
Timestamp              queue_depth
10:00:00                12
10:00:15                48
10:00:30               105
10:00:45                93
10:01:00                28
```

Các dạng metric phổ biến:

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| **Gauge** | Giá trị tại thời điểm quan sát | Queue depth, heap used, active threads |
| **Counter** | Tổng tích lũy theo thời gian | Số request đã xử lý, số lỗi |
| **Histogram** | Phân bố các phép đo | Độ trễ HTTP theo bucket |
| **Timer** | Theo dõi số lần và thời gian thực hiện | Thời gian xử lý đơn hàng |

Tên, đơn vị và quy tắc xuất dữ liệu tùy framework/backend. Cần lưu ý bộ đếm có thể reset sau restart hoặc do hành vi của thư viện. Dashboard nên tính rate phù hợp thay vì suy ra mỗi chênh lệch đều là tăng trưởng liên tục.

Metric giúp trả lời:

- CPU usage có tăng theo giờ cao điểm không?
- Tỷ lệ request lỗi trong năm phút vừa qua là bao nhiêu?
- p95 latency có vượt mục tiêu dịch vụ không?
- Queue depth tồn tại trên ngưỡng bao lâu?
- Một deployment mới có làm tăng memory utilization không?

### Một JMX attribute có thể là nguồn của metric

Giả sử `QueueMonitorMBean` công bố:

```java
int getPendingCount();
```

JMX client đọc `PendingCount` và nhận giá trị `95`. Nếu một exporter đọc giá trị này mỗi 15 giây rồi công bố lên hệ thống metrics, nó có thể trở thành một gauge như:

```text
shop_queue_pending{service="orders",queue="outbox"} 95
```

Đây là **dữ liệu metric được lấy từ JMX**. JMX không đồng nghĩa với Prometheus hay bất kỳ time-series database nào; nó chỉ cung cấp một nguồn giá trị để exporter thu thập.

## 7. So sánh trực tiếp bốn khái niệm

| Tiêu chí | JMX | Logs | Traces | Metrics |
|---|---|---|---|---|
| Bản chất | API/framework quản lý Java | Bản ghi sự kiện | Chuỗi spans của execution | Phép đo định lượng |
| Câu hỏi chính | “Tài nguyên JVM đang ở trạng thái gì? Có thể quản lý ra sao?” | “Đã xảy ra chuyện gì?” | “Request đi qua đâu và chậm ở bước nào?” | “Hệ thống thay đổi theo thời gian ra sao?” |
| Đơn vị cơ bản | MBean / attribute / operation / notification | Log record | Trace / span | Sample / time series |
| Truy cập thường gặp | JMX local/remote client | Agent/collector/log store | Instrumentation + trace exporter/backend | Metrics registry/exporter/backend |
| Dữ liệu lịch sử tự có? | Không mặc định | Phụ thuộc pipeline lưu log | Phụ thuộc tracing backend | Phụ thuộc backend time series |
| Độ chi tiết | Tài nguyên/component Java | Sự kiện cụ thể | Request/operation | Tập hợp hoặc phép đo |
| Quan sát liên service | Cần kết nối từng JVM hoặc collector | Có nếu logs tập trung | Là mục đích chính của distributed tracing | Có nếu tổng hợp metrics nhiều service |
| Có khả năng điều khiển? | Có, qua operations | Không phải mục đích chính | Không phải mục đích chính | Không phải mục đích chính |
| Ví dụ | `java.lang:type=Memory` | Exception stack trace | HTTP → DB span | `jvm_memory_used_bytes` |

**Tránh nhầm trục so sánh:** JMX là nguồn/cơ chế truy cập tài nguyên; metrics là một loại dữ liệu. Có thể có **JMX metrics** khi collector chuyển attributes thành time series. Vì vậy hai từ không phải hai lựa chọn loại trừ nhau.

## 8. Phân biệt metric từ JMX và metric ứng dụng

Một ứng dụng Spring có thể phát metrics theo hai cách phổ biến:

**A. Đọc số đo vốn được MBean công bố.**

Ví dụ platform MBeans của JVM có `java.lang:type=Memory` hoặc `java.lang:type=Threading`. Collector/JMX exporter lấy attributes và ánh xạ thành các chuỗi metric.

**B. Instrument trực tiếp bằng metrics API.**

Ví dụ một ứng dụng dùng Micrometer để tạo counter và timer cho luồng xử lý đơn hàng:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class OrderMetrics {
    private final Counter processed;

    public OrderMetrics(MeterRegistry registry) {
        this.processed = Counter.builder("shop.orders.processed")
                .description("Total successfully processed orders")
                .register(registry);
    }

    public void onProcessed() {
        processed.increment();
    }
}
```

Tên meter `shop.orders.processed` là tên trong Micrometer; khi xuất sang backend cụ thể, tên này có thể được chuẩn hóa hoặc biến đổi. Trong một ứng dụng Spring, `MeterRegistry` phải được cấu hình và truyền vào đối tượng trên.

Hai cách bổ sung nhau. JMX phù hợp các thuộc tính quản trị sẵn có; Micrometer tiện cho instrument các phép đo nghiệp vụ và hiệu năng trong code. Không cần tạo thêm một MBean cho mọi metric nếu đã có metrics registry phù hợp.

### Những thuộc tính JMX không nên chuyển thẳng thành metric

Không phải mọi attribute đều phù hợp với metric backend:

- Chuỗi dài hoặc nội dung lỗi hiện tại.
- Danh sách object kích thước không ổn định.
- Dữ liệu chứa ID động có cardinality cao.
- Dữ liệu bí mật hoặc thông tin cá nhân.
- Operation tạo side effect.

Exporter cần chọn trường hữu ích, định nghĩa đơn vị đo và giới hạn labels/tags để tránh số lượng time series bùng nổ.

## 9. Ví dụ Java: đọc JMX attributes trong cùng JVM

Đoạn dưới dùng platform MBeanServer để lấy trạng thái thread:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxSnapshotDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

        ObjectName threading =
                new ObjectName("java.lang:type=Threading");

        Object threadCount =
                server.getAttribute(threading, "ThreadCount");

        System.out.println("Current thread count: " + threadCount);
    }
}
```

Đây là **snapshot JMX**. Code không tạo log tập trung, span tracing hoặc time series chỉ bằng việc gọi `getAttribute`.

Nếu cần lịch sử, bạn có thể đọc theo chu kỳ và gửi dữ liệu sang hệ thống metrics; nhưng trong production nên dùng exporter hoặc metrics framework đã có thay vì viết một vòng lặp poll tùy tiện.

### Kết hợp với log để điều tra

Giả sử lúc 10:15 có cảnh báo số thread tăng mạnh. Sau khi đọc JMX và thấy `ThreadCount=420`, kỹ sư có thể xem log quanh thời điểm đó:

```text
10:15:03 WARN worker-pool Task queue saturated
10:15:05 ERROR downstream Timeout calling inventory API
```

JMX cho thấy **trạng thái thread**; log cung cấp **ngữ cảnh lỗi**. Nếu vẫn chưa biết request nào gây nghẽn, trace có thể hỗ trợ tìm dependency đang tốn thời gian.

## 10. Thực hành chẩn đoán: API chậm trong hệ thống Spring

Giả sử API `POST /checkout` có p95 latency tăng từ 250 ms lên 2,5 giây.

### Bước 1 — Metrics: xác định phạm vi ảnh hưởng

Quan sát:

- Request rate, error rate.
- p50/p95/p99 latency theo HTTP route, với quy tắc tổng hợp histogram/timer phù hợp.
- CPU, heap used, GC pauses.
- Thread pool active, queue depth và connection pool saturation.

Tín hiệu metrics cho biết hệ thống **chậm từ lúc nào**, mức độ và xu hướng, có liên quan tới deploy hay peak traffic không.

### Bước 2 — JMX: kiểm tra tài nguyên Java cụ thể

Dùng JConsole/JMC hoặc MBeanServer để xem:

```text
java.lang:type=Threading                 ThreadCount
java.lang:type=Memory                    HeapMemoryUsage
com.example.shop.checkout:type=Pool,...  ActiveConnections
com.example.shop.checkout:type=Queue,... PendingCount
```

Các ObjectName tùy chỉnh chỉ tồn tại nếu ứng dụng thực sự export các MBean tương ứng.

JMX cho biết tình trạng hiện tại và có thể cho phép thao tác quản lý được kiểm soát; **không suy ra nguyên nhân request chậm chỉ từ một attribute**.

### Bước 3 — Traces: xác định bước nghẽn

Một trace có thể cho thấy:

```text
checkout.request                2500 ms
  validate.cart                   20 ms
  reserve.inventory              120 ms
  authorize.payment             2250 ms
  write.order                     70 ms
```

Từ đó có bằng chứng rằng `authorize.payment` là thành phần chiếm phần lớn thời gian của request mẫu. Cần kiểm tra nhiều trace đủ đại diện, vì một trace đơn lẻ không luôn phản ánh toàn bộ phân bố latency.

### Bước 4 — Logs: tìm lỗi chi tiết và nguyên nhân gần

Log liên quan có thể chứa:

```text
ERROR payment-client trace_id=abc123
Payment gateway request timed out after 2000 ms
```

Nếu ứng dụng bật trace context injection trong logging, `trace_id` giúp liên kết log tới span và request tương ứng. Nếu không có correlation ID, vẫn có thể tìm theo thời gian, service và error code, nhưng độ chính xác thấp hơn.

### Bước 5 — Tổng hợp các bằng chứng

Một kết luận kỹ thuật cần dựa trên quan sát phối hợp:

- Metrics: latency và timeout tăng ngay sau một deployment.
- JMX: connection pool chạm giới hạn trong cùng khoảng thời gian.
- Traces: nhiều request phải đợi ở bước gọi payment gateway.
- Logs: client có timeout và retry liên tục.

Những bằng chứng này gợi ý điều tra timeout/retry/pool sizing hoặc dependency behavior. Không nên tăng pool size ngay chỉ vì JMX cho thấy pool đầy; có thể còn nguyên nhân gốc ở downstream.

## 11. JConsole, JMC và các công cụ metrics/logs/traces

### JConsole và Java Mission Control

**JConsole** là công cụ giám sát và quản lý JVM qua JMX. Nó hiển thị thông tin chuẩn của JVM và các MBean được export. **Java Mission Control (JMC)** hỗ trợ phân tích hoạt động JVM; Java Flight Recorder (JFR) là nguồn sự kiện profiling hiệu năng riêng, và JMC cũng có khả năng liên quan JMX tùy phiên bản/chức năng.

Các công cụ này rất hữu ích khi kiểm tra **một JVM hoặc một tập MBean cụ thể**, nhưng không mặc nhiên cung cấp một hệ thống thu thập metrics liên service, lưu log tập trung và distributed tracing.

### Prometheus-compatible monitoring

Hệ thống metrics có thể dùng JMX exporter hoặc Micrometer/Actuator để lấy giá trị. Một luồng thường gặp:

```text
JVM MBeans -> JMX exporter -> HTTP metrics endpoint
                                     |
                                     v
                              Metrics scraper
                                     |
                                     v
                              Time-series store
                                     |
                                     v
                              Dashboard / Alert
```

Đây là ví dụ pipeline; việc exporter hoạt động như Java agent, standalone client hay thành phần tích hợp còn tùy cách triển khai.

### Log aggregation

```text
Application logger -> stdout/file -> collector -> log backend
                                                   |
                                                   v
                                             Search & analysis
```

Log backend có thể là Elasticsearch/OpenSearch, Loki hoặc dịch vụ logging managed. Những công cụ này giải quyết bài toán tra cứu bản ghi theo thời gian và field.

### Distributed tracing

```text
Instrumented services -> OTLP exporter/collector -> tracing backend
                                                   |
                                                   v
                                             Trace waterfall
```

OpenTelemetry cung cấp API/SDK và hệ sinh thái instrumentation cho traces/metrics/logs, nhưng việc một ứng dụng Spring xuất đủ ba loại tín hiệu phụ thuộc cấu hình. Không nên nghĩ rằng chỉ bật JMX sẽ tự động có distributed traces.

## 12. Spring Boot Actuator và Micrometer liên quan thế nào?

Trong hệ sinh thái Spring, **Spring Boot Actuator** cung cấp các endpoint quản trị/quan sát khi được cấu hình, còn **Micrometer** là facade instrumentation metrics. Ví dụ một ứng dụng có thể có:

```text
/actuator/health
/actuator/metrics
/actuator/prometheus
```

Đây là các đường dẫn thường gặp, **không phải tất cả luôn được bật sẵn**; endpoint availability phụ thuộc dependency, cấu hình enable/exposure và security. `/actuator/prometheus` thường cần registry Prometheus.

Về mặt khái niệm:

- **JMX**: truy cập MBeans trong JVM, có thể công bố attributes, operations và notifications.
- **Actuator**: tập endpoint và tích hợp quản trị cho ứng dụng Spring Boot; có thể hỗ trợ HTTP hoặc JMX exposure tùy cấu hình.
- **Micrometer**: API đo lường và registry cho metrics như counter, timer, gauge.
- **Tracing instrumentation**: tạo spans và trace context để quan sát request paths.

Các công nghệ có thể cùng tồn tại trong một ứng dụng. Actuator JMX exposure không tự chuyển mọi endpoint HTTP thành một hệ thống tracing, và Micrometer metrics không tự lưu lịch sử nếu chưa có backend phù hợp.

### Ví dụ cấu hình Spring Boot minh họa

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
    jmx:
      exposure:
        include: health,info,metrics
```

Đây là cấu hình **minh họa** và cần điều chỉnh theo Spring Boot version, dependencies và security policy. Không mở toàn bộ endpoints trên môi trường production chỉ để thử nghiệm. Cũng cần hiểu `management.endpoints.jmx.exposure` kiểm soát Actuator endpoints qua JMX, còn MBeans custom bằng Spring JMX có lifecycle/configuration riêng.

## 13. Làm thế nào để kết nối dữ liệu giữa các tín hiệu?

Một observability stack hữu ích thường có thông tin chung:

| Thông tin | JMX | Log | Trace | Metric |
|---|---|---|---|---|
| Service/module | ObjectName domain/key | Structured field | Resource attribute | Tag/label |
| Environment | Cấu hình MBean/collector | Log field | Resource attribute | Tag/label |
| Instance | MBeanServer/target | Host/pod field | Resource attribute | Target/label |
| Request/trace ID | Không phải field chuẩn tự có trên mọi MBean | Có thể thêm vào log context | Định danh trace/span | Thường không dùng làm label vì cardinality |
| Timestamp | Thời điểm đọc hoặc notification timestamp | Timestamp bản ghi | Span start/end | Timestamp sample |
| Lỗi cụ thể | Attribute/notification tùy custom MBean | Exception/message | Span error/status | Counter hoặc tỷ lệ lỗi |

### Nguyên tắc correlation

1. Đặt tên service, module và environment nhất quán giữa hệ thống logging, tracing, metrics và JMX exporter.
2. Gắn trace ID vào logs ở request processing context nếu đang dùng distributed tracing.
3. Dùng labels/tags có cardinality kiểm soát (service, route template, outcome, environment).
4. **Không** đưa trace ID, order ID, user ID hoặc request ID tùy ý thành metric label, vì số lượng series có thể tăng rất nhanh.
5. JMX ObjectName của MBean không phải chỗ lưu danh sách request IDs. MBean được dùng để quản lý tài nguyên tương đối ổn định.
6. Khi dashboard hiển thị lỗi tăng, truy cập cùng service/time window trong log backend và trace backend.

Tương quan không đồng nghĩa với quan hệ nhân quả. Ví dụ heap tăng và latency tăng cùng lúc có thể liên quan, nhưng cần thêm GC evidence, traces hoặc profiling trước khi xác định nguyên nhân.

## 14. Một ví dụ nguồn dữ liệu JMX tạo metric

Giả sử có Standard MBean:

```java
public interface CacheStatusMBean {
    int getEntryCount();
    long getEvictionCount();
}

public class CacheStatus implements CacheStatusMBean {
    private int entryCount = 120;
    private long evictionCount = 25;

    @Override
    public int getEntryCount() {
        return entryCount;
    }

    @Override
    public long getEvictionCount() {
        return evictionCount;
    }
}
```

Đăng ký:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName cacheName = new ObjectName(
        "com.example.shop.catalog:type=Cache,name=products");

server.registerMBean(new CacheStatus(), cacheName);

try {
    System.out.println(
            server.getAttribute(cacheName, "EntryCount"));
    System.out.println(
            server.getAttribute(cacheName, "EvictionCount"));
} finally {
    server.unregisterMBean(cacheName);
}
```

Một JMX exporter có thể ánh xạ các giá trị thành:

```text
shop_cache_entries{cache="products"} 120
shop_cache_evictions_total{cache="products"} 25
```

Đây là **ví dụ tên metric sau ánh xạ**, không phải tên metric mà JMX hoặc một exporter tự tạo mặc định.

### Phân biệt gauge và counter ở ví dụ

- `EntryCount`: gauge; tăng hoặc giảm theo kích thước cache.
- `EvictionCount`: counter tích lũy; cần quản lý reset của process/cache khi tính rate.

Lưu ý Java `long` không đủ để đảm bảo một giá trị có counter semantics. Contract ứng dụng phải đảm bảo con số tích lũy tăng theo đúng ngữ nghĩa, hoặc giải thích rõ khi reset. Tránh dùng tên `_total` cho giá trị có thể tăng giảm tùy ý.

## 15. JMX Notification và log event khác nhau ra sao?

Hai cơ chế đều có thể biểu diễn *một sự kiện*, nhưng khác nhau về channel và consumer.

Ví dụ ứng dụng phát cả hai khi pool cạn kết nối:

```java
log.warn("Connection pool exhausted: active={}, idle={}",
        activeConnections, idleConnections);

Notification notification = new Notification(
        "com.example.shop.pool.exhausted",
        this,
        sequence.incrementAndGet(),
        System.currentTimeMillis(),
        "Pool exhausted");
sendNotification(notification);
```

- **Log** đi qua logging pipeline của ứng dụng.
- **Notification** được chuyển cho JMX notification listeners đã đăng ký.
- **Metric** có thể phản ánh `active_connections` hoặc `acquire_timeout_total`.
- **Trace** có thể hiển thị request phải đợi connection bao lâu.

Một JMX notification không mặc định được ghi vào log backend, và một log không mặc định xuất hiện như JMX notification. Muốn chuyển đổi, hệ thống phải cấu hình hoặc viết bridge cụ thể.

Với event nghiệp vụ cần durable delivery, không dùng notification như một message broker có acknowledgement/replay. JMX notification là công cụ quản trị hữu ích, nhưng không có bảo đảm bền vững tương đương transactional messaging.

## 16. Những ngộ nhận thường gặp

| Ngộ nhận | Điều chính xác hơn |
|---|---|
| “JMX chính là metrics.” | JMX là management API; một số attributes là nguồn để tạo metrics. |
| “Có JMX thì tự có dashboard theo lịch sử.” | Cần exporter, collector, storage và dashboard. |
| “Có logs thì không cần metrics.” | Logs diễn tả sự kiện; metrics giúp đo xu hướng/tỷ lệ với chi phí và ngữ nghĩa phù hợp. |
| “Trace giống log có nhiều dòng.” | Trace có span tree, timing và quan hệ execution; log là bản ghi sự kiện riêng. |
| “JMX notification chắc chắn được nhận sau khi client reconnect.” | Không mặc định hỗ trợ durable replay. |
| “Mọi JMX attribute đều là số.” | Có attributes kiểu boolean, string, CompositeData và nhiều dạng khác. |
| “Metric label có thể dùng mọi request ID.” | Cardinality cao làm tăng chi phí lưu trữ/truy vấn. |
| “Actuator metrics và JMX luôn xuất cùng dữ liệu.” | Hai đường exposure khác nhau và phụ thuộc cấu hình/instrumentation. |
| “JMX operation là một cách thu thập metric.” | Operation là hành vi quản trị có thể tạo side effect. |
| “Nếu trace chậm thì đã biết nguyên nhân gốc.” | Trace chỉ rõ nơi thời gian được dùng; cần kết hợp logs, metrics và tài nguyên để xác định nguyên nhân. |

## 17. Thiết kế chiến lược quan sát cho một dịch vụ Spring

Với một service có database, HTTP clients, queue và cache, có thể phân công các tín hiệu như sau.

### Metrics: thông tin tổng hợp đáng theo dõi thường xuyên

- Throughput, error rate, latency distributions.
- Heap memory used, GC pauses, CPU usage.
- Thread pool active/queued.
- Database pool active/idle/pending.
- Cache hit/miss/evictions.
- Queue depth và consumer lag nếu hệ thống cung cấp.

### Logs: thông tin cần điều tra theo sự kiện

- Validation errors có giá trị chẩn đoán.
- Exception/stack trace ở điểm xử lý lỗi.
- Retry exhausted hoặc downstream timeout.
- Thay đổi cấu hình có kiểm soát hoặc lifecycle event.

### Traces: câu chuyện của từng request

- HTTP route vào ứng dụng.
- Operation DB/query.
- Call đến downstream service.
- Message consume/publish spans nếu instrumentation hỗ trợ.
- Span status và error attributes.

### JMX: khả năng quản trị JVM và component

- JVM thread/memory/classloading MBeans.
- Custom MBeans cho queue, cache, worker pool.
- Attributes phục vụ kiểm tra trạng thái tại chỗ.
- Operations quản lý được bảo vệ.
- Notifications cho sự kiện vận hành quan trọng.

Tùy stack, một vài số đo xuất hiện ở cả JMX và metrics. Nên xác định **nguồn đo chuẩn** và tránh tạo hai series với ngữ nghĩa không nhất quán; ví dụ một `ActiveConnections` JMX attribute và một Micrometer gauge cùng tên ý tưởng nhưng khác pool/mẫu đo có thể khiến dashboard gây hiểu nhầm.

## 18. Bài tập thực hành

### Bài tập A — Chọn tín hiệu đúng

Với mỗi câu hỏi dưới đây, hãy chọn tín hiệu ưu tiên:

1. Tại sao một request thanh toán cụ thể chậm 5 giây?
2. Có bao nhiêu thread JVM đang hoạt động ngay lúc này?
3. Tỷ lệ HTTP 5xx trong 10 phút vừa qua là bao nhiêu?
4. Lỗi exception chi tiết nào xảy ra trong tác vụ import?
5. Cache MBean có operation `clear()` hay không?
6. P95 latency thay đổi thế nào qua ba deployment?

**Đáp án gợi ý:** (1) traces và logs; (2) JMX attribute hoặc metric hiện tại; (3) metrics; (4) logs, có thể liên kết trace; (5) JMX MBeanInfo; (6) metrics theo thời gian.

### Bài tập B — Đọc JMX nhưng chưa có history

Chạy `JmxSnapshotDemo` nhiều lần trong vài phút. Ghi lại từng `ThreadCount` cùng timestamp. Vì sao một lần đọc không thể vẽ biểu đồ lịch sử? Bạn sẽ cần thêm thành phần nào để lưu và hiển thị dữ liệu theo thời gian?

**Gợi ý:** Một collector đọc định kỳ, time-series backend và dashboard.

### Bài tập C — Kết hợp evidence

Một dashboard cho thấy queue depth cao, nhưng không có request HTTP errors. Hãy đề xuất trình tự:

1. Kiểm tra gauge queue depth và processing rate.
2. Đọc JMX attributes của consumer/worker.
3. Tìm log lỗi processing/retry.
4. Dùng traces nếu hệ thống có instrument luồng message.
5. Xác nhận nguyên nhân trước khi gọi JMX operation như pause/resume.

### Bài tập D — Phân loại thuộc tính

Giả sử MBean công bố:

```text
EntryCount = 250
Enabled = true
LastError = "connection refused"
resetStatistics()
```

Hãy giải thích:

- `EntryCount` phù hợp làm gauge.
- `Enabled` là trạng thái boolean; có thể ánh xạ metric 0/1 nếu thật sự cần.
- `LastError` phù hợp thông tin chẩn đoán, nhưng không phải time-series số thông thường.
- `resetStatistics()` là operation, không phải metric.

### Bài tập E — Phân biệt cảnh báo

Một MBean phát notification `queue.threshold.exceeded` khi vượt 100. Dashboard thu thập `queue_depth` mỗi 30 giây. Hãy phân biệt điều notification có thể phát hiện ngay với điều metric giúp xác minh sau reconnect. Nêu trường hợp một spike chỉ kéo dài 2 giây có thể bị polling bỏ lỡ.

## 19. Câu hỏi tự kiểm tra

**1. JMX có tự lưu lịch sử thread count theo thời gian không?**

Không mặc định. Client đọc attribute tại thời điểm yêu cầu; collector cần lưu các mẫu để tạo time series.

**2. Có thể tạo metric từ JMX không?**

Có. Exporter có thể đọc attributes và ánh xạ sang metrics với tên/labels/units phù hợp.

**3. Log và trace khác nhau thế nào?**

Log là bản ghi sự kiện với thông điệp và ngữ cảnh; trace mô tả chuỗi spans và timing của một execution flow.

**4. Có phải mọi MBean đều có operations có thể thay đổi trạng thái?**

Không. Khả năng công bố operations tùy management interface/metadata. Có MBean chỉ cung cấp attributes đọc.

**5. Tại sao trace ID thường không nên là metric label?**

Mỗi request có thể có ID riêng, tạo cardinality cực lớn và làm tăng chi phí lưu trữ/truy vấn.

**6. JMX notification có thay thế hệ thống logging không?**

Không. Nó phục vụ callback sự kiện quản trị cho listeners, không tự động có pipeline log có lưu trữ và tìm kiếm lịch sử.

**7. Thấy `ActiveConnections` tăng và request latency tăng có đủ chứng minh database lỗi không?**

Không. Cần thêm logs, traces và các số đo liên quan để xác định nguyên nhân.

## 20. Ghi nhớ

- **JMX**: cơ chế quản lý Java qua MBeans, gồm attributes, operations và notifications.
- **Logs**: bản ghi sự kiện, lỗi và ngữ cảnh cụ thể.
- **Traces**: đường đi và thời gian của request/operation qua các thành phần.
- **Metrics**: phép đo định lượng để phân tích xu hướng, tỷ lệ và cảnh báo theo thời gian.
- JMX attributes có thể trở thành metric samples thông qua một collector/exporter, nhưng JMX tự nó không phải time-series database.
- Logs, traces, metrics và JMX hỗ trợ những câu hỏi khác nhau; kết hợp chúng thường mang lại bằng chứng mạnh hơn khi xử lý sự cố.
- Spring Actuator, Micrometer, JMX exporters và OpenTelemetry là các thành phần của một hệ sinh thái quan sát; sự hiện diện của một thành phần không tự kích hoạt những thành phần còn lại.
- Giữ dữ liệu nhạy cảm ngoài logs, ObjectName, metric labels và span attributes; kiểm soát exposure và quyền thao tác JMX.

## 21. Tài liệu tham khảo

- Java SE 21 — JMX `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Java SE 21 — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE 21 — `Notification`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/Notification.html
- Oracle JMX Tutorial: https://docs.oracle.com/javase/tutorial/jmx/
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Boot Reference — Actuator: https://docs.spring.io/spring-boot/reference/actuator/index.html
- Micrometer Documentation: https://docs.micrometer.io/micrometer/reference/
- OpenTelemetry Documentation — Observability signals: https://opentelemetry.io/docs/concepts/signals/
