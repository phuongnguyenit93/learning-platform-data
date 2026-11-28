# Luồng từ lời gọi ứng dụng đến hệ thống thu thập telemetry

Trong một ứng dụng Spring Boot dùng **Spring Modulith**, ta có thể mô tả các application module và quan hệ phụ thuộc giữa chúng bằng mô hình kiến trúc. Nhưng khi hệ thống phục vụ người dùng thật, còn một nhóm câu hỏi khác: yêu cầu đã đi qua module nào, bước nào chậm, lỗi phát sinh ở đâu, và sự kiện giữa các module đã được xử lý chưa?

Để trả lời, ứng dụng cần tạo **telemetry** — dữ liệu cho phép quan sát hành vi lúc chạy như metrics, traces và logs — rồi đưa dữ liệu này đến hệ thống thu thập, lưu trữ và truy vấn. Bài học này trình bày **toàn bộ đường đi từ một lời gọi thực tế đến dashboard**, nhấn mạnh vai trò của Spring Modulith Insight, Spring Boot Actuator, Micrometer Observation, tracing, event metrics, exporter, collector và context propagation.

> **Phạm vi phiên bản:** Các dependency và cấu hình dưới đây minh họa cho hệ sinh thái Spring Boot 3.x và phiên bản Spring Modulith tương thích. Tên endpoint, tên meter, khả năng tự động instrument và một số thuộc tính cấu hình có thể thay đổi theo phiên bản. Hãy kiểm tra dependency tree và tài liệu của phiên bản dự án đang dùng.

## 1. Bạn sẽ học được gì?

Kết thúc bài, bạn có thể:

1. Vẽ lại pipeline **lời gọi → instrumentation → Observation → metrics/spans/logs → export → hệ thống thu thập → dashboard**.
2. Phân biệt dữ liệu mô tả **kiến trúc module** với dữ liệu mô tả **lời gọi runtime**.
3. Giải thích cách Micrometer chuyển một observation thành các tín hiệu đo lường và vì sao không phải observation nào cũng tạo đủ metric, trace và log.
4. Phân biệt Prometheus **scrape/pull** với OTLP **export/push**.
5. Theo dõi cả lời gọi đồng bộ và consumer sự kiện bất đồng bộ, kể cả trường hợp trace context bị đứt.
6. Xác minh từng mắt xích khi dashboard không có dữ liệu hoặc telemetry không phản ánh đúng hoạt động nghiệp vụ.

## 2. Bức tranh tổng thể

Giả sử ứng dụng bán hàng có ba application module:

| Module | Trách nhiệm chính | Điểm quan sát gợi ý |
| --- | --- | --- |
| `order` | Tiếp nhận, lưu đơn và phát `OrderPlaced` | Độ trễ HTTP, thời gian tạo đơn, số lần phát event |
| `inventory` | Kiểm tra và giữ hàng | Độ trễ, tỷ lệ lỗi, số lượt xử lý event |
| `notification` | Phát thông báo cho khách | Số lượt gửi, tỷ lệ thất bại, độ trễ downstream |

Khi client gọi `POST /orders`, Spring Boot có thể tạo observation cho HTTP; Spring Modulith Insight có thể bổ sung khả năng quan sát tương tác qua ranh giới application module; ứng dụng có thể thêm observation nghiệp vụ tại các bước quan trọng. Dữ liệu được chuyển đến những handler phù hợp, rồi ra các hệ thống thu thập khác nhau:

~~~mermaid
flowchart TB
    Req["Client: POST /orders"] --> Call["Spring MVC → order → inventory / event"]
    Call --> Instr["Instrumentation: Spring Boot, Modulith, mã ứng dụng"]
    Instr --> Obs["Micrometer ObservationRegistry"]
    Obs --> MeterH["Metrics ObservationHandler"]
    Obs --> TraceH["Tracing ObservationHandler"]
    Instr -. "Log tại điểm nghiệp vụ" .-> Log["Logs + MDC traceId/spanId nếu có"]
    MeterH --> Meter["MeterRegistry: Timer, Counter, Gauge"]
    TraceH --> Span["Micrometer Tracing: spans"]
    Meter --> Actuator["/actuator/prometheus"]
    Actuator --> Prom["Prometheus scrape (pull)"]
    Span --> Exporter["OTLP exporter (push)"]
    Exporter --> Collector["OpenTelemetry Collector (tùy chọn)"]
    Collector --> TraceDB["Trace backend: Tempo/Jaeger/..."]
    Log --> LogAgent["Log shipper/collector"]
    LogAgent --> LogDB["Log backend"]
    Prom --> Dash["Dashboard / Alert"]
    TraceDB --> Dash
    LogDB --> Dash
~~~

Đây là **một cách triển khai điển hình**, không phải bắt buộc mọi hệ thống đều dùng tất cả các thành phần. Prometheus có thể scrape ứng dụng trực tiếp. OTLP exporter có thể gửi trực tiếp đến tracing backend có OTLP receiver mà không qua Collector. Logs cần pipeline riêng; bật tracing không tự động gửi toàn bộ log đến trace backend.

Điều cần phân biệt ngay từ đầu:

- **Module graph / tài liệu mô-đun**: module nào tồn tại, phụ thuộc nào hợp lệ, API module là gì. Đây chủ yếu là kiến thức **tĩnh**.
- **Instrumentation / Observation**: thao tác nào đã được gắn điểm đo khi mã chạy.
- **Telemetry đã xuất**: những dữ liệu nào thực sự được gửi, nhận, lưu và có thể truy vấn. Chúng chịu ảnh hưởng của sampling, cấu hình exporter, thời gian thu thập và lỗi đường truyền.

Không thấy một tương tác trên tracing UI **không chứng minh** tương tác ấy chưa xảy ra; điểm gọi có thể không được instrument hoặc trace đã bị bỏ khi sampling.

## 3. Chặng 1 — Lời gọi thực thi và instrumentation

**Instrumentation** là cơ chế bao quanh một thao tác để ghi nhận lúc bắt đầu, khi hoàn tất, độ trễ, lỗi và thông tin ngữ cảnh. Nó có thể đến từ framework, thư viện hoặc mã tự viết:

1. **Spring Boot**: instrumentation HTTP server/client và các thư viện hỗ trợ Micrometer Observation.
2. **Spring Modulith Insight**: khả năng quan sát tương tác application module theo ranh giới được Spring Modulith nhận diện, khi phiên bản/starter tương ứng hỗ trợ.
3. **Business instrumentation**: các observation hay counter tự định nghĩa để theo dõi logic như giữ hàng hoặc xử lý sự kiện.
4. **Application logs**: log do lập trình viên hoặc thư viện chủ động ghi lại tại các thời điểm quan trọng.

Spring Modulith có thể tạo module graph/tài liệu ranh giới từ cấu trúc ứng dụng. Phần quan sát runtime giúp bổ sung góc nhìn “module đang được thực thi”, nhưng **module graph không phải dòng telemetry** và không tự chứng minh một module đã được chạy. Ngược lại, việc một trace có span của module cũng không thay thế kiểm tra ràng buộc kiến trúc bằng test.

Hãy xét các thao tác:

~~~text
HTTP POST /orders
    |
    v
order.placeOrder()           [được instrument nếu có hỗ trợ/cấu hình]
    |
    +--> inventory.check()   [lời gọi đồng bộ qua API module]
    |
    +--> publish OrderPlaced
             |
             +--> inventory listener   [có thể chạy async sau commit]
             +--> notification listener
~~~

Một lời gọi Java nội bộ cùng bean, việc tự gọi phương thức hoặc đoạn code không đi qua tầng instrumentation/proxy phù hợp có thể **không sinh span riêng**. Hãy kiểm tra chính điểm thực thi thay vì suy đoán từ sơ đồ source code.

## 4. Chặng 2 — Micrometer Observation làm cầu nối

**Micrometer Observation** cho phép mô tả một công việc theo mô hình chung, đồng thời gửi lifecycle của công việc đến các `ObservationHandler` đã đăng ký trong `ObservationRegistry`. Thông tin có thể gồm:

- **Name**: định danh loại thao tác, chẳng hạn `shop.inventory.reserve`.
- **Low-cardinality key values**: thuộc tính có ít giá trị khác nhau, ví dụ `application.module=inventory`, thích hợp để tạo metric tags.
- **High-cardinality key values**: thuộc tính nhiều giá trị khác nhau, có thể phù hợp hơn với trace nếu cần và được phép; tránh dùng làm metric tags.
- **Error, start/stop, context**: cho biết thao tác bắt đầu, kết thúc thế nào, và observation nào đang hoạt động.

Ví dụ tự thêm một observation cho bước giữ hàng:

~~~java
package com.example.shop.inventory;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class InventoryService {

    private final ObservationRegistry observations;

    public InventoryService(ObservationRegistry observations) {
        this.observations = observations;
    }

    public void reserve(UUID orderId) {
        Observation.createNotStarted("shop.inventory.reserve", observations)
                .lowCardinalityKeyValue("application.module", "inventory")
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(() -> persistReservation(orderId));
    }

    private void persistReservation(UUID orderId) {
        // Thao tác giữ hàng thật và xử lý lỗi nghiệp vụ tại đây.
    }
}
~~~

`observe(...)` bắt đầu và kết thúc observation quanh callback; nếu callback ném exception, vòng đời observation có thể ghi nhận lỗi theo cơ chế Micrometer. Đoạn `persistReservation` là placeholder cho mã thật, không phải giải pháp transaction, retry hay tính nhất quán dữ liệu.

**Đừng tự động bọc mọi phương thức.** Nếu instrumentation từ Spring Modulith hoặc framework đã đo cùng thao tác, thêm observation có thể làm xuất hiện span/timer trùng hoặc nhiều tầng lồng nhau không cần thiết. Chỉ thêm điểm đo khi giúp trả lời câu hỏi vận hành cụ thể.

### Từ observation thành những tín hiệu khác nhau

~~~mermaid
flowchart LR
    O["Observation: inventory.reserve"] --> R["ObservationRegistry"]
    R --> M["MeterObservationHandler"]
    R --> T["TracingObservationHandler"]
    M --> MR["MeterRegistry → Timer/metric"]
    T --> TR["Tracer → Span"]
~~~

Sự kiện bắt đầu/kết thúc observation được các handler chuyển thành telemetry. Nếu thiếu metric handler/registry, observation chưa chắc tạo meter. Nếu thiếu tracing bridge/exporter, observation chưa chắc xuất trace. **Observation cũng không tự động tạo log nghiệp vụ**.

## 5. Chặng 3A — Metrics được tổng hợp và scrape

Metrics trả lời câu hỏi tổng hợp theo thời gian, chẳng hạn có bao nhiêu request mỗi giây, tỷ lệ lỗi của listener, thời gian xử lý trung bình và p95 độ trễ.

| Meter | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Counter** | Đếm số lần phát sinh một sự kiện | Số lượt xử lý event thất bại |
| **Timer** | Ghi số lần và thời lượng thực thi | Thời gian `inventory.reserve` |
| **Gauge** | Giá trị tức thời | Số publication đang chờ, nếu có nguồn trạng thái |
| **DistributionSummary** | Phân bố một đại lượng không phải thời gian | Số item trong mỗi đơn |

Đoạn mã sau minh họa cách đếm riêng số lần xử lý event:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

class EventProcessingMetrics {

    private final MeterRegistry meters;

    EventProcessingMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    void record(String consumerModule, String outcome) {
        Counter.builder("shop.module.event.processed")
                .tag("consumer.module", consumerModule)
                .tag("outcome", outcome) // success | failure
                .register(meters)
                .increment();
    }
}
~~~

Giới hạn `consumerModule` trong danh sách module đã biết, `outcome` trong tập kết quả nhỏ, ví dụ `success` và `failure`. **Không** dùng `orderId`, `userId`, email, `traceId` hoặc exception message làm metric tag. Chúng có thể tạo số lượng chuỗi thời gian rất lớn và tăng chi phí bộ nhớ/lưu trữ.

Với `micrometer-registry-prometheus` và Actuator đã cấu hình, ứng dụng có thể công bố metrics tại `/actuator/prometheus`. Prometheus chủ động gửi HTTP GET để **scrape** endpoint này theo chu kỳ:

~~~text
Ứng dụng Spring Boot
  └─ MeterRegistry
      └─ /actuator/prometheus  <-- HTTP GET / scrape --  Prometheus
                                                       └─ time series / query / alert
~~~

`/actuator/metrics` hỗ trợ xem meter và đo kiểm nhanh dưới dạng dữ liệu Actuator; nó **khác** endpoint `/actuator/prometheus` có định dạng dành cho Prometheus scrape.

Một timer thường có số lượt và tổng thời gian; muốn tính percentiles bằng Prometheus histogram cần cấu hình distribution histogram phù hợp. Không được giả định mọi timer tự động xuất histogram bucket hoặc có thể query p95 toàn hệ thống.

## 6. Chặng 3B — Traces và spans đi theo một yêu cầu cụ thể

**Trace** thể hiện các đoạn công việc được instrument của một request hoặc hoạt động có ngữ cảnh chung. **Span** là một đoạn được ghi thời gian; span có `spanId`, thường liên quan đến `traceId` và có thể có quan hệ cha–con:

~~~text
traceId = 8be3... (minh họa)

HTTP POST /orders                  140 ms
└─ order.placeOrder                105 ms
   ├─ inventory.checkAvailability   30 ms
   └─ persistence.saveOrder         55 ms
~~~

Ví dụ trên mô tả **các bước đã được instrument**, không phải tên span hay thời gian cố định do Spring Modulith tạo ra. Tổng durations của các span lồng nhau có thể lớn hơn thời gian request nếu cộng trực tiếp vì có khoảng thời gian chồng lấp.

Khi một `TracingObservationHandler` hoạt động, Micrometer Tracing có thể chuyển observation thành span và mang ngữ cảnh tracing. Nếu dùng cầu nối OpenTelemetry, exporter sẽ gửi spans theo giao thức đã cấu hình, thường là **OTLP**.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant A as Spring Boot / Modulith
    participant O as ObservationRegistry
    participant T as Tracer / OTLP exporter
    participant C as Collector
    participant B as Tracing backend

    U->>A: POST /orders
    A->>O: HTTP observation start
    O->>T: Bắt đầu span HTTP
    A->>O: Module observation start
    O->>T: Bắt đầu span module
    A->>O: Module observation stop
    O->>T: Kết thúc span module
    A-->>U: HTTP response
    A->>O: HTTP observation stop
    O->>T: Kết thúc span HTTP
    T-->>C: Export spans qua OTLP
    C-->>B: Export đến backend
~~~

Điểm cần nhớ: **kết thúc span không đồng nghĩa backend đã nhận span**. Exporter có thể gửi theo batch, qua mạng và qua Collector. Với sampling, một phần trace có thể không được giữ lại để giảm chi phí. Ngay cả khi backend trống, nghiệp vụ vẫn có thể chạy bình thường.

## 7. Chặng 3C — Logs là một pipeline riêng

Log được ứng dụng ghi tại những điểm cần thông tin chi tiết: quyết định nghiệp vụ, exception, retry hoặc trạng thái event. Khi logging framework hỗ trợ MDC và tracing context được thiết lập, log có thể chứa `traceId`/`spanId`:

~~~text
INFO  traceId=8be3... module=order event=OrderPlaced result=published
WARN  traceId=8be3... module=inventory operation=reserve result=retryable-failure
~~~

Đây là ví dụ log mang tính minh họa; muốn có output tương tự cần cấu hình logging pattern/structured logging, MDC và context propagation thực tế.

~~~text
Logger trong ứng dụng
    → stdout / file / structured logs
    → log shipper hoặc collector
    → log backend
    → query theo traceId, module và thời điểm
~~~

Bật OTLP exporter cho traces **không tự động** chuyển toàn bộ logs sang tracing backend. Muốn tra cùng một giao dịch ở cả hai hệ thống, log pipeline phải giữ trường tương quan; nếu trace context đã mất khi đổi thread, log có thể không còn `traceId`.

Chỉ log những gì cần thiết; không đưa access token, mật khẩu, dữ liệu cá nhân hoặc nội dung đơn hàng nhạy cảm vào log/span attributes. Trace ID dùng để tương quan tín hiệu, không phải khóa idempotency của nghiệp vụ.

## 8. Context propagation giữ mối liên hệ giữa các bước

**Context propagation** là cơ chế mang ngữ cảnh của tracing/observation qua các ranh giới thực thi. Nó ảnh hưởng trực tiếp đến việc một span có nằm cùng trace với yêu cầu gốc hay không.

### Lời gọi đồng bộ

Nếu request đến với header W3C `traceparent` và instrumentation hỗ trợ, server có thể trích xuất trace context; các observation con cùng luồng thực thi có thể tiếp nối trace hiện hành:

~~~text
Request thread [traceId=A]
   order.placeOrder [traceId=A]
       inventory.checkAvailability [traceId=A]
~~~

Context tồn tại không có nghĩa mọi hàm Java đều được ghi thành span; vẫn cần instrumentation tại các điểm đo.

### Listener bất đồng bộ sau commit

Với event `OrderPlaced`, listener tại `inventory` có thể chạy trên executor khác sau khi transaction tạo đơn đã commit:

~~~mermaid
flowchart LR
    Order["Request thread: order, trace A"] --> Event["publish OrderPlaced"]
    Event --> Queue["Executor / task queue"]
    Queue --> Listener["inventory listener"]
    Event -. "Capture / restore tracing context" .-> Listener
~~~

Nếu không truyền context, log của listener có thể mất trace ID hoặc xuất hiện trace mới. Với các phiên bản Spring Framework/Micrometer hỗ trợ, `ContextPropagatingTaskDecorator` có thể giúp chuyển ngữ cảnh ở **executor thực sự chạy listener**. Nếu event đi qua Kafka/RabbitMQ, cần instrumentation producer/consumer inject/extract trace headers.

Phân biệt bốn khái niệm:

| Khái niệm | Giải quyết việc gì? | Không giải quyết việc gì? |
| --- | --- | --- |
| Trace context | Nối hoặc tương quan spans/logs | Không cam kết transaction thành công |
| Transaction context | Commit/rollback dữ liệu trong phạm vi giao dịch | Không tự theo thread async |
| Event ID / idempotency key | Nhận biết hoặc ngăn xử lý trùng theo quy tắc nghiệp vụ | Không thay thế trace của request |
| Event Publication Registry của Spring Modulith (nếu cấu hình) | Theo dõi publication còn chờ/đã hoàn tất và hỗ trợ xử lý sự kiện tin cậy | Không phải telemetry collector và không tự thay thế metrics/traces |

Với tác vụ bất đồng bộ tách khỏi vòng đời request ban đầu, có thể dùng trace link hoặc correlation key nghiệp vụ thay vì giả định luôn có một cây span cha–con liên tục. Tracing context không chuyển transaction và không bảo đảm xử lý event theo cơ chế exactly-once.

## 9. Chặng 4 — Đưa telemetry ra khỏi ứng dụng

Khi metrics và spans đã được tạo, cần kiểm tra **cơ chế vận chuyển**, không chỉ kiểm tra instrumentation.

| Thuộc tính | Metrics với Prometheus | Traces với OTLP |
| --- | --- | --- |
| Dữ liệu gốc | MeterRegistry | Tracer/span exporter |
| Điểm truyền | `/actuator/prometheus` | OTLP receiver endpoint |
| Chiều truyền | Prometheus chủ động scrape (pull) | Ứng dụng chủ động export (push) |
| Nhịp dữ liệu | Theo lịch scrape | Khi exporter gửi, thường theo batch |
| Nơi lưu thông dụng | Prometheus/backend tương thích | Tempo, Jaeger/backend tracing |
| Phân tích mạnh nhất | Tỷ lệ lỗi, độ trễ, xu hướng, cảnh báo | Đường đi và lỗi một request được lấy mẫu |

### Vai trò của OpenTelemetry Collector

Collector là thành phần trung gian tùy chọn để nhận, xử lý và xuất telemetry:

~~~text
OTLP Receiver  →  Processor (batch/filter/transform)  →  Exporter  →  Backend
~~~

Collector có thể giảm tải cấu hình exporter tại ứng dụng, áp dụng chính sách xử lý dữ liệu và gửi tới nhiều backend. Nó **không tự suy ra module graph** của Spring Modulith hoặc tự biết nghiệp vụ `OrderPlaced` nghĩa là gì. Nó chỉ xử lý những thuộc tính/tín hiệu mà instrumentation gửi đến.

### Dependency và cấu hình minh họa

Ví dụ Maven dùng quản lý phiên bản thích hợp với Spring Boot và Spring Modulith:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Một số starter có thể đã kéo theo dependency liên quan, nên hãy kiểm tra dependency tree để tránh khai báo thừa. Ví dụ cấu hình **môi trường phát triển**:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Trong ví dụ này:

- Registry Prometheus và endpoint Actuator là điều kiện để scrape theo định dạng Prometheus.
- `sampling.probability: 1.0` giúp quan sát mọi trace trong bài thực hành; **production** thường phải điều chỉnh theo tải và chính sách chi phí.
- Endpoint OTLP/HTTP trên là nơi exporter gửi traces, giả sử có receiver đang lắng nghe tại địa chỉ đó. Chỉ thêm cấu hình mà không chạy Collector/backend tương ứng thì vẫn không xem được trace.
- Có thể bật endpoint `/actuator/modulith` khi dependency và phiên bản hỗ trợ, để xem thông tin application module; endpoint này **không phải** endpoint export metrics hoặc traces.

Các actuator endpoint cần được bảo vệ bằng xác thực/phân quyền hoặc giới hạn mạng phù hợp, đặc biệt trong production.

## 10. Theo dõi một giao dịch xuyên qua cả hệ thống

Tình huống: khách tạo đơn thành công, HTTP trả `201`, nhưng tác vụ giữ hàng của `inventory` thất bại sau commit.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order
    participant Inventory as inventory listener
    participant Obs as Micrometer
    participant Prom as Prometheus
    participant Trace as Tracing backend

    Client->>Order: POST /orders
    Order->>Obs: HTTP + order observations
    Order->>Order: Save, publish OrderPlaced, commit
    Order-->>Client: 201 Created
    Note over Order,Inventory: Listener có thể chạy async sau commit
    Order-->>Inventory: OrderPlaced
    Inventory->>Obs: inventory processing observation
    Inventory->>Inventory: reserve → exception
    Inventory->>Obs: Báo lỗi, kết thúc observation
    Note over Obs,Prom: Prometheus scrape MeterRegistry qua endpoint
    Note over Obs,Trace: Tracing exporter gửi spans qua OTLP pipeline
~~~

Hai chú thích cuối cố ý phân biệt việc **Prometheus scrape** với **tracing export**. `ObservationRegistry` không chủ động gửi HTTP sang Prometheus hay backend tracing.

Những dấu hiệu cần đối chiếu:

| Tầng | Bằng chứng cần tìm | Ý nghĩa và giới hạn |
| --- | --- | --- |
| HTTP | Status `201`, latency, HTTP span | Request thành công theo hợp đồng HTTP; **chưa chứng minh** listener sau commit thành công |
| `order` | Observation/log phát event | Thao tác tạo đơn được instrument; cần xác nhận việc phát/commit qua dữ liệu thực |
| Publication registry (nếu có) | Publication đang chờ, hoàn tất, lỗi | Giúp xem lifecycle sự kiện; không thay thế trạng thái giữ hàng |
| `inventory` | Timer/counter lỗi, exception log, listener span | Listener chạy và lỗi; số lượt có thể bao gồm retry |
| Prometheus | Tỷ lệ lỗi tăng, độ trễ xử lý thay đổi | Cho biết xu hướng, không xác định trực tiếp order ID nào lỗi |
| Trace backend | Span và thời gian các bước được ghi/lấy mẫu | Giúp xem một đường đi cụ thể, có thể thiếu nhánh async |
| Cơ sở dữ liệu nghiệp vụ | Trạng thái đơn/giữ hàng | Bằng chứng cuối cùng về kết quả nghiệp vụ |

Một dashboard HTTP trông ổn vẫn có thể che một luồng event hỏng sau commit. Vì thế cần **metric/trace/log riêng tại consumer**, và khi yêu cầu tính tin cậy cao cần có cách đối chiếu publication với trạng thái nghiệp vụ.

## 11. Kiểm tra pipeline theo từng chặng

Không nên chỉ thấy dependency có trong Maven rồi mặc định toàn bộ observability đã chạy. Hãy kiểm tra từ nguồn đến đích.

| Chặng | Cách kiểm tra | Kết quả dự kiến |
| --- | --- | --- |
| Lời gọi → observation | Kích hoạt một API đã instrument; xem log hoặc số đo cục bộ | Có thao tác được ghi nhận |
| Observation → meter | Xem `/actuator/metrics` | Meter liên quan xuất hiện sau khi thao tác chạy |
| Meter → scrape endpoint | Xem `/actuator/prometheus` | Có output định dạng Prometheus |
| Scrape → Prometheus | Kiểm tra target và query metric thật | Target hoạt động, time series thay đổi |
| Observation → span | Xác nhận tracing bridge, sampler và điểm đo | Có span cho request được lấy mẫu |
| Span → OTLP receiver | Kiểm tra endpoint, kết nối, log/metrics collector | Receiver nhận payload hoặc báo lỗi cụ thể |
| Collector → tracing backend | Tra cứu trace ID/thời điểm | Thấy span sau khoảng trễ export phù hợp |
| Log → kho log | Truy vấn theo trace ID hoặc correlation key | Log có trường liên kết được bảo toàn |
| Event → consumer | Kích hoạt thành công và lỗi trong môi trường test | Chỉ số, log, trạng thái publication/nghiệp vụ phản ánh đúng |

Ví dụ lệnh khi chạy local:

~~~bash
curl http://localhost:8080/actuator
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/prometheus
~~~

Nếu `/actuator/prometheus` trả `404`, có thể thiếu registry, endpoint chưa expose hoặc khác phiên bản. Nếu endpoint hoạt động nhưng chưa có meter tự định nghĩa, hãy chạy thao tác trước: nhiều meter chỉ được đăng ký khi có lần thực thi đầu tiên.

Để truy vấn Prometheus, phải dựa vào tên meter **thực tế đã export**. Chẳng hạn timer có thể cho phép truy số lượt bằng series dạng `*_seconds_count` và tổng thời gian bằng `*_seconds_sum`. Minh họa một truy vấn ý tưởng sau khi đã xác minh tên metric:

~~~promql
sum(rate(shop_inventory_reserve_seconds_count[5m]))
~~~

Đây là tên metric **minh họa**, không phải tên Spring Modulith mặc định. Cách đổi tên, suffix, tags và histogram phụ thuộc registry/cấu hình. Truy vấn `histogram_quantile` chỉ có ý nghĩa khi bucket histogram phù hợp thực sự được export.

## 12. Khi telemetry không xuất hiện: tìm lỗi ở đâu?

| Dấu hiệu | Khả năng cần kiểm tra | Bước tiếp theo |
| --- | --- | --- |
| Không có meter mới | Chưa instrument, observation chưa chạy, thiếu handler/registry | Chạy đúng nghiệp vụ, xem registry và meter tại ứng dụng |
| Có `/actuator/metrics` nhưng không thấy trên Prometheus | Registry Prometheus/endpoint/scrape target sai | Kiểm tra `/actuator/prometheus`, target và quyền truy cập |
| Có metrics nhưng không có traces | Chưa có tracing bridge, sampling, exporter hoặc receiver lỗi | Kiểm tra configuration, sampler, đường OTLP, backend |
| Chỉ có span HTTP, thiếu span module | Tích hợp Modulith chưa bật hoặc lời gọi ngoài phạm vi instrument | Kiểm tra starter, proxy, vị trí điểm gọi và phiên bản |
| Span đứt ở listener | Không propagate context qua executor/broker | Kiểm tra executor thật và cơ chế inject/extract context |
| Collector nhận mà backend trống | Pipeline exporter của Collector lỗi, auth hoặc backend từ chối | Kiểm tra receiver/processor/exporter và log backend |
| Có trace nhưng log không có `traceId` | MDC hoặc log pattern/pipeline thiếu trường | Xem cấu hình logging và propagation xuyên pipeline |
| Metric sinh quá nhiều series | Gắn user ID, order ID hoặc dữ liệu động thành tag | Thay tag bằng nhóm giá trị hữu hạn |
| HTTP thành công, listener lỗi | Xử lý bất đồng bộ sau commit | Đo riêng consumer và kiểm tra publication/nghiệp vụ |

Chẩn đoán theo **thứ tự dữ liệu di chuyển**: nếu ứng dụng chưa tạo meter/span thì hãy tìm tại instrumentation; nếu ứng dụng đã tạo nhưng Collector không nhận thì tìm ở exporter/mạng; nếu Collector nhận rồi mà dashboard không có thì tìm ở backend/query.

## 13. Bài thực hành tự kiểm chứng

Hãy tạo một ví dụ gồm ít nhất hai module, một API gọi module đồng bộ và một event được xử lý bất đồng bộ.

1. **Định nghĩa luồng nghiệp vụ:** phác họa ranh giới `order`, `inventory`, sự kiện `OrderPlaced` và điểm listener có thể chạy sau commit.
2. **Gắn điểm đo:** dùng instrumentation sẵn có, bổ sung `Observation` nếu cần. Chỉ dùng labels có tập giá trị nhỏ.
3. **Gửi request:** ghi lại thời điểm, HTTP status và một correlation key thử nghiệm. Tìm điểm đo trong Actuator.
4. **Kiểm chứng Prometheus:** xem `/actuator/prometheus`, target và truy vấn tốc độ thực thi một thao tác. Đối chiếu số lượt xử lý thật.
5. **Kiểm chứng tracing:** xem span HTTP và span ranh giới module; giải thích những bước không có span và khả năng sampling.
6. **Kiểm chứng async:** kích hoạt listener; xem trace ID/log có liên kết với request gốc hay cần propagation/correlation ID.
7. **Tạo lỗi có kiểm soát trong test:** cho listener ném exception; so metric lỗi, log, trạng thái publication (nếu cấu hình) và trạng thái dữ liệu nghiệp vụ.
8. **Thử ngắt một mắt xích thu thập:** tạm dùng OTLP endpoint sai hoặc dừng scrape ở test; xác định dấu hiệu và sửa, rồi kiểm tra dữ liệu xuất hiện trở lại.

Cuối bài, hãy lập bảng gồm **tín hiệu đã có**, **hệ thống quan sát thấy**, **kết luận được phép rút ra** và **điều chưa thể kết luận**.

### Câu hỏi tự kiểm tra

1. Tại sao `/actuator/prometheus` có metric nhưng tracing backend vẫn trống?
2. Khác biệt cơ bản giữa Prometheus scrape và OTLP exporter là gì?
3. Không có span `inventory` có đủ chứng minh module đó không chạy?
4. Vì sao consumer sự kiện có thể lỗi sau khi HTTP trả `201`?
5. `traceId` có thể dùng thay khóa idempotency cho retry hay không?
6. Lúc nào phải kiểm tra context propagation, và khi nào nguyên nhân thực sự là thiếu instrumentation?
7. Một Collector nhận được span nhưng backend không hiện trace: phải kiểm tra những chặng nào?

## 14. Tổng kết

Khả năng quan sát trong Spring Modulith là **một chuỗi xử lý và vận chuyển dữ liệu**:

**Lời gọi trong ứng dụng → instrumentation tại HTTP/module/event → Micrometer Observation → meter/span/log → exposition hoặc exporter → scraper/collector → backend → truy vấn và cảnh báo.**

Module graph cho biết ranh giới **dự kiến**; Actuator, Micrometer và tracing cho biết những hành vi **đã được đo**; exporter/collector đưa telemetry đến nơi phân tích; log và trạng thái nghiệp vụ giúp diễn giải sự cố. Hiểu từng chặng, cả lời gọi đồng bộ lẫn event bất đồng bộ, giúp tìm đúng nguyên nhân khi không thấy dữ liệu và dùng tín hiệu vận hành để kiểm chứng kiến trúc mô-đun một cách có căn cứ.
