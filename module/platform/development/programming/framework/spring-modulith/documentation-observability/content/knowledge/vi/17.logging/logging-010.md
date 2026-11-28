# Truy tìm từ log sang trace và metric

> **Chương:** Logging  
> **Bối cảnh:** Spring Modulith Documentation & Observability — kết hợp log, distributed trace, module entry span và metrics của Spring Boot để điều tra một request xuyên qua nhiều application module.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò khác nhau của **log**, **trace/span** và **metrics** trong quá trình điều tra sự cố.
2. Dùng **traceId** và **spanId** trong log để mở đúng trace và xác định module operation liên quan.
3. Phân biệt trace correlation với correlation ID nghiệp vụ, request ID và baggage.
4. Cấu hình Spring Boot/Micrometer Tracing để đưa trace context vào MDC và log pattern.
5. Thiết kế structured logging có trường ổn định, dễ tìm kiếm, không làm lộ dữ liệu nhạy cảm.
6. Từ một trace xác định service/module/operation và đối chiếu với metrics theo thời gian, route, module hoặc event type.
7. Dùng trace exemplars nếu metrics backend hỗ trợ để nhảy từ một điểm dữ liệu metrics sang trace đại diện.
8. Xây dựng quy trình điều tra từ cảnh báo tổng hợp đến một request cụ thể rồi quay lại kiểm tra xu hướng toàn hệ thống.

## 2. Vì sao cần liên kết log, trace và metrics?

Trong ứng dụng Spring Modulith, một request có thể đi qua nhiều application module:

~~~mermaid
flowchart LR
    Client["Client"] --> API["HTTP API"]
    API --> Orders["orders"]
    Orders --> Payments["payments"]
    Orders --> Inventory["inventory"]
    Orders --> Notifications["notifications<br/>event listener"]
~~~

Khi người dùng báo một đơn hàng xử lý chậm, ba câu hỏi cần được trả lời ở ba mức:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Metrics** | Hệ thống đang có vấn đề trên diện rộng hay không? | p95 latency của operation orders tăng từ 100 ms lên 900 ms |
| **Traces** | Một request cụ thể đã đi qua những bước nào và chậm ở đâu? | Span payments.authorize chiếm 700 ms trong trace |
| **Logs** | Tại sao code ở một bước cụ thể đưa ra quyết định hoặc thất bại? | Log ghi mã lỗi từ cổng thanh toán và nhánh fallback |

Không có một tín hiệu nào thay thế được hai tín hiệu còn lại:

- Metrics tổng hợp tốt nhưng thường không giữ đủ chi tiết để tìm một request cụ thể.
- Trace cho thấy cấu trúc và thời lượng của một lần thực thi, nhưng có thể bị sampling và không phải mọi request đều được lưu.
- Log có thể chứa ngữ cảnh chi tiết, nhưng nếu thiếu trace correlation thì khó nối nhiều log thuộc cùng một request xuyên qua thread, module hoặc service.

Mục tiêu là **liên kết bằng các định danh phù hợp**, không biến mọi trường thành metric tag.

## 3. Phân biệt các loại ID trước khi cấu hình

| Giá trị | Ý nghĩa | Phạm vi | Dùng ở đâu? |
| --- | --- | --- | --- |
| **traceId** | Định danh một distributed trace | Xuyên qua các span có cùng trace context | Log MDC, trace backend, trace propagation |
| **spanId** | Định danh một span cụ thể | Một operation được instrument | Log MDC, trace backend |
| **parentSpanId** | Định danh span cha của span hiện tại | Quan hệ trong một trace | Trace tree/waterfall |
| **requestId** | ID của một HTTP request do ứng dụng/gateway tạo | Thường một request vào hệ thống | Log và header nếu có hợp đồng |
| **orderId** | Định danh đối tượng nghiệp vụ | Vòng đời một đơn hàng, có thể qua nhiều request | Log/audit có phân quyền, truy vấn nghiệp vụ |
| **correlationId** | Định danh liên hệ nghiệp vụ hoặc chuỗi message theo hợp đồng ứng dụng | Có thể kéo dài qua nhiều request/event | Log, event metadata, message header |
| **baggage** | Các key-value được propagation cùng trace context | Qua các ranh giới tracing được hỗ trợ | Span/log nếu được cấu hình; phải kiểm soát dữ liệu |

Trace ID và span ID là định danh của tracing system theo mô hình W3C Trace Context. Trace ID được chia sẻ bởi các span trong cùng trace; span ID xác định một span riêng. Order ID không phải trace ID: một đơn hàng có thể được xử lý bởi nhiều trace khác nhau trong suốt vòng đời.

Một request có thể đồng thời mang:

~~~text
traceId       = 4bf92f3577b34da6a3ce929d0e0e4736
spanId        = 00f067aa0ba902b7
requestId     = req-7c2f
correlationId = checkout-flow-91
orderId       = ORD-2026-1042
~~~

Đây là các giá trị giả lập để minh họa. Không tự gán orderId làm trace ID; hãy giữ đúng ý nghĩa của từng trường.

## 4. Trace context xuất hiện trong log như thế nào?

Khi dùng Micrometer Tracing, Spring Boot tự thêm correlation ID vào log theo mặc định. Correlation ID được tạo từ hai giá trị MDC là traceId và spanId; với Logback, output mặc định có thể trông như sau:

~~~text
2026-11-27 10:12:44.210 INFO [http-nio-8080-exec-2]
[4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7]
com.example.shop.orders.OrderService : Order accepted
~~~

Trace ID giống nhau trên các span của cùng trace; span ID thay đổi theo operation. Nhờ vậy:

- Tìm traceId để lấy tất cả log thuộc một trace.
- Thêm spanId để thu hẹp log thuộc một span/operation cụ thể.
- Đối chiếu span đang mở trong trace backend với dòng log tạo ra ở thời điểm tương ứng.

Correlation ID mặc định dựa trên MDC key traceId và spanId. Tên MDC key có thể được đổi bằng hai thuộc tính:

- management.tracing.mdc.trace-id-key
- management.tracing.mdc.span-id-key

### 4.1. Tùy chỉnh correlation prefix

Nếu muốn dùng format riêng cho prefix, có thể cấu hình:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

Giá trị logging.pattern.correlation do ứng dụng tự đặt sẽ thay thế format correlation mặc định; nếu đổi tên MDC keys thì pattern tự khai báo phải dùng đúng các tên mới. Dấu cách ở cuối giúp tách prefix khỏi logger name trong format mặc định.

Không cần tự ghép traceId vào mọi message. Hãy để tracing integration quản lý MDC và để logging pattern đưa correlation prefix vào từng dòng.

### 4.2. Nếu log không có traceId/spanId

Kiểm tra lần lượt:

1. Request có được tracing instrumentation tạo span hay không.
2. Micrometer Tracing bridge và tracer/exporter có được cấu hình hay không.
3. Log được ghi trong scope của span hay sau khi scope đã đóng.
4. Logging integration có cập nhật MDC hay không.
5. Pattern tùy chỉnh có giữ correlation prefix hay đã ghi đè format mặc định.
6. Log có được ghi từ executor khác thread mà chưa propagate context hay không.

Với Brave, cấu hình management.tracing.baggage.enabled=false cũng có thể khiến trace/span IDs không còn được ghi vào MDC theo tích hợp của Spring Boot, làm mất log correlation. Kiểm tra hành vi theo tracer implementation đang dùng.

## 5. Structured logging: biến log thành dữ liệu có thể truy vấn

Log dạng text dễ đọc, nhưng log dạng cấu trúc như JSON thuận tiện hơn cho hệ thống tìm kiếm và cảnh báo. Spring Boot hiện hành hỗ trợ các format structured logging như ECS, GELF và Logstash.

Ví dụ cấu hình ECS cho console:

~~~yaml
logging:
  structured:
    format:
      console: ecs
~~~

ECS/Logstash structured logging của Spring Boot đưa các MDC key-value vào JSON record. Khi Micrometer Tracing ghi traceId và spanId vào MDC, các trường này có thể xuất hiện trong log JSON mà không cần nối chúng vào message.

Một record minh họa:

~~~json
{
  "@timestamp": "2026-11-27T10:12:44.210Z",
  "log": {
    "level": "INFO",
    "logger": "com.example.shop.orders.OrderService"
  },
  "service": {
    "name": "shop-service"
  },
  "message": "Order accepted",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "module.identifier": "orders",
  "event.type": "OrderPlaced",
  "correlationId": "checkout-flow-91"
}
~~~

Đây là ví dụ schema để minh họa; tên field và cấu trúc JSON thật phụ thuộc format, encoder và ingest pipeline. Nếu tự cấu hình logback-spring.xml hoặc logging encoder, cần đảm bảo MDC values vẫn được đưa vào output.

### 5.1. Thêm field nghiệp vụ có cấu trúc

Với SLF4J fluent logging API, có thể thêm key-value vào một record:

~~~java
log.atInfo()
    .addKeyValue("module.identifier", "orders")
    .addKeyValue("event.type", "OrderPlaced")
    .log("Order accepted");
~~~

Đây là cách thêm metadata cho log event. Nó không tự biến các key đó thành metric tags hoặc baggage. Hãy dùng tên field ổn định để hệ thống ingest có thể tìm kiếm nhất quán.

### 5.2. Trường log không đồng nghĩa metric tag

Log thường chấp nhận những trường có cardinality cao hơn metrics vì chúng được lưu thành các bản ghi riêng. Tuy nhiên, log volume, chi phí index và dữ liệu nhạy cảm vẫn cần giới hạn.

| Trường | Log | Metric tag |
| --- | --- | --- |
| module.identifier=orders | Có | Thường phù hợp |
| event.type=OrderPlaced | Có | Phù hợp nếu số event type hữu hạn |
| traceId | Có, rất hữu ích để tra trace | Không dùng làm tag |
| spanId | Có, để mở span cụ thể | Không dùng làm tag |
| orderId | Có thể dùng trong log nghiệp vụ có kiểm soát | Không dùng làm tag |
| customer.email | Tránh hoặc masking/tokenize theo chính sách | Không dùng |
| error.category=PAYMENT_TIMEOUT | Có | Phù hợp nếu tập giá trị hữu hạn |
| error.message | Có thể ghi có kiểm soát | Không dùng |

Nếu đưa traceId, orderId hoặc customerId thành metric labels, mỗi giá trị mới có thể tạo time series mới, gây cardinality explosion.

## 6. Cấu hình Spring Boot cho tracing và log correlation

Ví dụ dependency tối thiểu cho Actuator:

~~~xml
<!-- pom.xml; version do Spring Boot dependency management quản lý -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Với Spring Modulith, thêm Insight starter nếu ứng dụng cần module metadata, module entry observations và endpoint liên quan:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Để export traces, cấu hình Micrometer Tracing bridge và exporter theo **major version Spring Boot**. Spring Boot hỗ trợ OpenTelemetry với OTLP và Brave với Zipkin; chọn đúng dependency combination và property namespace theo version dự án.

Một ví dụ profile phát triển:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0

logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

Sampling 1.0 giúp nhìn thấy mọi trace được tạo trong bài thực hành; chỉ nên dùng ở môi trường test/local hoặc trong một khoảng kiểm soát vì lượng trace có thể tăng mạnh. Spring Boot mặc định sample khoảng 10% request để tránh làm quá tải trace backend.

Khi giảm sampling, metrics vẫn có thể ghi nhận các operation đầy đủ hơn trong khi trace backend chỉ có một phần traces. Do đó, có log correlation ID nhưng không tìm thấy trace tương ứng chưa chắc là lỗi log pattern: trace có thể đã bị sampler loại hoặc exporter/backend không nhận được.

## 7. Từ log sang trace: quy trình điều tra một request

Giả sử log search tìm được:

~~~text
ERROR traceId=4bf92f3577b34da6a3ce929d0e0e4736
      spanId=00f067aa0ba902b7
      module.identifier=payments
      message="Authorization timed out"
~~~

Thực hiện:

1. Copy traceId từ log.
2. Mở trace backend, tìm trace theo chính xác traceId.
3. Kiểm tra root span: HTTP method, route, service, thời gian bắt đầu/kết thúc.
4. Xem waterfall để xác định module entry span có duration cao nhất.
5. Dùng spanId để định vị đúng operation đã phát log.
6. Mở các log có cùng traceId; nếu cần thu hẹp một operation, thêm spanId.
7. Đối chiếu exception, error category và các event/span events ở thời điểm xảy ra lỗi.

~~~mermaid
sequenceDiagram
    participant Log as Log search
    participant Trace as Trace backend
    participant Span as Span details
    Log->>Log: Tìm ERROR và copy traceId
    Log->>Trace: Search traceId
    Trace-->>Log: Trả trace tree
    Log->>Span: Dùng spanId để chọn operation
    Span-->>Log: Attributes, events, duration, parent
    Note over Log,Span: Mở các log cùng traceId để đọc chi tiết
~~~

### 7.1. Đọc trace trong ngữ cảnh Spring Modulith

Một trace có thể chứa module entry spans như:

~~~text
HTTP POST /orders
└── orders.placeOrder
    ├── inventory.reserve
    ├── payments.authorize
    └── notifications.onOrderPlaced
~~~

Tên span ở đây mang tính minh họa. Spring Modulith gắn metadata module cho các entry spans, chẳng hạn module.identifier, module.name, module.method và module.invocation-type theo convention/phiên bản.

Từ trace, bạn có thể trả lời:

- Module nào được gọi trong request?
- Lời gọi nào là child của operation nào?
- payments có thời lượng bất thường hay gặp exception?
- Event listener notifications có được thực thi trong cùng trace context hay trace đã bị tách?

Trace không thay thế module graph: graph mô tả dependency được phát hiện trong kiến trúc; trace mô tả đường thực thi đã xảy ra ở một lần chạy.

## 8. Từ trace sang metrics: đặt operation vào bối cảnh toàn hệ thống

Trace chỉ là một lần thực thi. Sau khi tìm thấy payments.authorize chậm, cần kiểm tra xem đây là trường hợp cá biệt hay vấn đề đang ảnh hưởng nhiều request.

Spring Boot Actuator cho phép xem meter qua endpoint /actuator/metrics. Nếu module entry observation đã được instrument và tạo meter module.invocations, có thể lọc theo module:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.invocations?tag=module.identifier:payments"
~~~

Tên meter và tag cần được xác nhận từ response availableTags của ứng dụng. Nếu không có module.invocations trong version hoặc cấu hình hiện tại, chọn meter thực tế tương ứng với operation đang điều tra.

Spring Modulith còn có các event publication counters:

- module.events.published: counter tổng hợp có tag module và event type.
- module.events.published.$moduleIdentifier.$simpleEventTypeName: counter riêng theo event type.

Đừng dùng event publication counter để suy ra latency của listener; nó đếm publication, không chứng minh listener hoàn tất.

### 8.1. Truy vấn Prometheus theo thời gian

Giả sử scrape output đã xác nhận Prometheus series là:

~~~text
module_invocations_seconds_count{
  module_identifier="payments"
} 1200
~~~

Truy vấn tốc độ invocation:

~~~promql
sum by (module_identifier) (
  rate(module_invocations_seconds_count[5m])
)
~~~

Truy vấn thời gian trung bình:

~~~promql
sum(rate(module_invocations_seconds_sum{
  module_identifier="payments"
}[5m]))
/
sum(rate(module_invocations_seconds_count{
  module_identifier="payments"
}[5m]))
~~~

Tên series trên chỉ là ví dụ. Micrometer/Prometheus có thể chuẩn hóa tên meter, tag và đơn vị khác nhau theo registry. Kiểm tra /actuator/prometheus trước khi copy PromQL vào dashboard.

Không thêm traceId hoặc spanId vào metric tag để nối trực tiếp từng sample với trace. Cách làm đó tạo cardinality rất cao và phá lợi thế của metrics.

## 9. Từ metrics sang trace bằng exemplars

Spring Boot hỗ trợ Prometheus exemplars. Exemplar là một sample của metric có thể gắn trace context, chẳng hạn trace_id và span_id, để người vận hành nhảy từ một điểm trên biểu đồ metrics sang trace đại diện.

~~~mermaid
flowchart LR
    Metric["Histogram / Timer bucket"] --> Sample["Exemplar sample"]
    Sample -->|"trace_id / span_id"| Trace["Trace backend"]
    Trace --> Span["Trace waterfall / span"]
~~~

Exemplar không phải metric label thông thường. Nó là metadata tùy chọn gắn với measurement sample; do đó không tạo một time series mới cho mỗi trace ID.

Để dùng được:

1. Có tracing context khi ghi metric sample.
2. Micrometer Tracing cung cấp span context cho exemplar; Spring Boot có thể tự cấu hình phần này khi tracing được bật.
3. Prometheus phải được cấu hình hỗ trợ OpenMetrics/exemplar và scrape đúng định dạng.
4. Grafana hoặc UI tương đương phải được cấu hình datasource liên kết sang tracing backend.
5. Trace tương ứng phải được sample, export và còn trong thời gian retention.

Mặc định, Spring Boot chỉ đưa sampled traces vào exemplars. Nếu một điểm metrics không có exemplar, vẫn có thể tìm trace bằng service/module/operation và khoảng thời gian gần đúng; exemplar là đường tắt, không phải điều kiện để correlation hoạt động.

## 10. Baggage và correlation ID: dùng đúng mục đích

### 10.1. Baggage là gì?

Baggage là tập key-value được truyền cùng trace context qua các ranh giới hỗ trợ propagation. Nó có thể giúp downstream biết một số thông tin chung như tenant tier hoặc experiment cohort, nhưng không phải nơi truyền payload nghiệp vụ.

Ví dụ các giá trị có thể cân nhắc nếu tổ chức cho phép:

~~~text
tenant.tier = premium
experiment = checkout-v2
~~~

Không đưa email, access token, số thẻ, địa chỉ hoặc toàn bộ orderId vào baggage một cách tùy tiện. Baggage có thể đi qua nhiều service và được đưa vào log/span theo cấu hình, nên phạm vi lộ dữ liệu rộng hơn một log local.

### 10.2. Cấu hình baggage trong Spring Boot

Spring Boot cho phép chỉ định baggage fields được propagation qua remote boundary, được đưa vào MDC và được gắn vào span:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant.tier
      correlation:
        fields:
          - tenant.tier
      tag-fields:
        - tenant.tier
~~~

- remote-fields: field được propagation qua network theo cơ chế baggage.
- correlation.fields: field được đưa vào logging context/MDC.
- tag-fields: field được gắn làm tag trên spans.

Các property này có ý nghĩa khác nhau. Chỉ bật những field thật sự cần thiết; baggage có thể làm tăng kích thước header và bị forward đến hệ thống không dự kiến. Với B3 propagation, baggage không tự động được truyền như W3C; kiểm tra cấu hình propagation type và hành vi của tracer.

### 10.3. Correlation ID nghiệp vụ không tự động là baggage

Nếu cần nối event OrderPlaced với log của consumer sau nhiều giờ, hãy đưa correlationId vào event metadata hoặc message header theo hợp đồng ứng dụng. Trace context chỉ tồn tại theo lifecycle và propagation của trace; không nên mặc định một trace kéo dài suốt vòng đời đơn hàng.

Một message được retry hoặc phát lại có thể bắt đầu trace mới nhưng vẫn giữ correlation ID nghiệp vụ. Điều này giúp phân biệt **quan hệ nhân quả nghiệp vụ** với **quan hệ span cha–con trong một trace**.

## 11. Thiết kế log trong application module

Log tốt nên mô tả sự kiện ở đúng module, có thông tin giúp điều tra và tránh lặp những dữ liệu không cần thiết.

Ví dụ:

~~~java
package com.example.shop.payments;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private static final Logger log =
        LoggerFactory.getLogger(PaymentService.class);

    public void authorize(String orderId) {
        log.atInfo()
            .addKeyValue("module.identifier", "payments")
            .log("Payment authorization started");

        try {
            // Gọi payment provider qua client được cấu hình riêng.
            log.atInfo()
                .addKeyValue("module.identifier", "payments")
                .log("Payment authorization accepted");
        }
        catch (RuntimeException ex) {
            log.atError()
                .addKeyValue("module.identifier", "payments")
                .addKeyValue("error.category", "PROVIDER_ERROR")
                .setCause(ex)
                .log("Payment authorization failed");
            throw ex;
        }
    }
}
~~~

Khi tracing context hiện hành được tích hợp với MDC, logger pattern hoặc structured logging có thể tự thêm traceId và spanId. Không cần nối ID vào message bằng tay:

~~~java
// Tránh cách này: dễ tạo log format không thống nhất.
log.info("Payment failed traceId=" + traceId + " orderId=" + orderId);
~~~

Nếu cần ghi trường nghiệp vụ trong structured logging, dùng SLF4J fluent key-value hoặc encoder có hỗ trợ structured arguments; không nhồi object lớn hoặc secret vào message.

### 11.1. Log theo cấp độ

| Level | Dùng khi | Ví dụ |
| --- | --- | --- |
| ERROR | Operation thất bại và cần hành động/điều tra | Không thể authorize sau khi retry hết |
| WARN | Bất thường có xử lý tiếp hoặc fallback | Payment provider chậm, dùng provider dự phòng |
| INFO | Sự kiện nghiệp vụ quan trọng, tần suất vừa phải | Đơn hàng được chấp nhận |
| DEBUG | Chi tiết kỹ thuật phục vụ điều tra có kiểm soát | Chọn nhánh tính phí |
| TRACE | Chi tiết rất nhỏ, chỉ bật tạm khi cần | Dòng điều khiển nội bộ |

Không log mọi request/response ở INFO trong hệ thống lưu lượng cao. Nếu cần thống kê số lượng operation, dùng metrics; nếu cần đường đi của một lần thực thi, dùng trace; log dành cho sự kiện và chi tiết có ích.

## 12. Một quy trình điều tra hoàn chỉnh

Giả sử dashboard báo p95 latency của module payments tăng. Quy trình:

~~~mermaid
flowchart TD
    A["Alert: payments p95 tăng"] --> B["Mở metrics theo module/method"]
    B --> C["Xác định khoảng thời gian và operation"]
    C --> D["Mở exemplar hoặc tìm trace mẫu"]
    D --> E["Đọc module entry span và downstream spans"]
    E --> F["Copy traceId/spanId"]
    F --> G["Tìm log cùng traceId"]
    G --> H["Xác định lỗi/nhánh nghiệp vụ"]
    H --> I["Khắc phục và theo dõi metrics sau thay đổi"]
~~~

**Bước 1 — Metrics:** xác định thời điểm bắt đầu, tỷ lệ lỗi, p95/p99 và module/method bị ảnh hưởng. So sánh với baseline và deployment gần nhất.

**Bước 2 — Trace:** chọn trace đại diện qua exemplar hoặc trace search theo service, operation và thời gian. Kiểm tra span nào chiếm phần lớn duration.

**Bước 3 — Log:** lấy traceId/spanId của span lỗi, tìm các log cùng trace. Đọc exception, error category, retry và fallback.

**Bước 4 — Module architecture:** đối chiếu module graph để xem quan hệ phụ thuộc có phù hợp với ranh giới kiến trúc. Một trace dài không tự chứng minh dependency tĩnh sai.

**Bước 5 — Xác nhận:** sau khi sửa, quan sát metrics theo cùng dimension và thời gian; lấy trace mới để xác nhận đường đi; kiểm tra log không còn lỗi tương ứng.

## 13. Truy vấn log theo hệ thống tập trung

Ngôn ngữ truy vấn phụ thuộc backend (Loki, Elasticsearch/OpenSearch, Splunk hoặc hệ thống khác). Ý tưởng chung là lọc theo trường đã chuẩn hóa.

Ví dụ truy vấn dạng pseudocode:

~~~text
traceId = "4bf92f3577b34da6a3ce929d0e0e4736"
AND service.name = "shop-service"
~~~

Hoặc tìm lỗi của module payments trong khoảng thời gian:

~~~text
level = "ERROR"
AND module.identifier = "payments"
AND @timestamp BETWEEN T1 AND T2
~~~

Nếu dùng Loki với JSON logs, truy vấn minh họa:

~~~logql
{service_name="shop-service"} | json | traceId="4bf92f3577b34da6a3ce929d0e0e4736"
~~~

Tên label và parser cần khớp pipeline ingest của bạn. Không tạo label Loki cho mọi traceId nếu backend của bạn lưu label theo kiểu index cardinality cao; giữ traceId trong structured log field để lọc sau parse, hoặc dùng cơ chế query phù hợp.

## 14. Bảo mật và chi phí khi liên kết ba tín hiệu

Liên kết observability làm tăng khả năng điều tra, đồng thời mở rộng nơi dữ liệu có thể được lưu và truy cập.

| Rủi ro | Biện pháp |
| --- | --- |
| orderId/customerId lộ qua log | Mask/tokenize, phân quyền log search, retention phù hợp |
| Baggage bị forward sang downstream không mong muốn | Chỉ allowlist field, xác thực nguồn và giới hạn kích thước |
| Trace ID bị biến thành metric label | Không đưa trace/span IDs vào metric tags |
| Log volume tăng do INFO mọi request | Chọn log event có giá trị, sampling log nếu phù hợp, dùng metrics cho volume |
| Trace không có vì sampling | Giữ metrics đầy đủ hơn và dùng sampling policy có chủ đích |
| Correlation field không nhất quán giữa module | Định nghĩa schema/contract chung và test propagation |
| Log message tự nối dữ liệu đầu vào | Dùng structured fields, encode đúng và tránh log injection |

Trace ID không nhất thiết là bí mật, nhưng vẫn có thể liên kết đến một phiên làm việc hoặc dữ liệu nhạy cảm. Áp dụng quyền truy cập và retention cho trace/log như các nguồn dữ liệu vận hành khác.

## 15. Bài thực hành: từ log lỗi đến metric xu hướng

**Bối cảnh:** ứng dụng Spring Boot có các module orders, payments, notifications. Một request đặt hàng phát event OrderPlaced; module payments xử lý thanh toán và module notifications gửi thông báo.

Thực hiện:

1. Bật Spring Boot Actuator, Micrometer Tracing và Spring Modulith Insight/observability theo version tương thích.
2. Cấu hình log correlation prefix có traceId và spanId.
3. Cấu hình exporter và tracing backend; dùng sampling 100% ở profile local để bài thực hành dễ quan sát.
4. Tạo một request đặt hàng thành công. Ghi lại log có traceId và mở trace tương ứng.
5. Tạo một lỗi giả lập trong payments; ghi log ERROR trong span đang hoạt động.
6. Tìm log ERROR theo traceId, dùng spanId xác định module operation và đọc trace waterfall.
7. Mở Actuator metrics cho module invocation và event publication counters. Xác định metric nào đo latency operation, metric nào đếm event được publish.
8. Nếu backend hỗ trợ exemplars, kiểm tra một sample metrics có trace link. Nếu không, tìm trace theo service/operation/time window.
9. Tắt sampling một phần hoặc giảm tỷ lệ; xác nhận metrics vẫn cung cấp xu hướng trong khi một số traces không còn trong backend.
10. Thử log từ executor chưa propagate context rồi gắn ContextPropagatingTaskDecorator; so sánh traceId/spanId trên log worker.
11. Rà soát output để chắc chắn không có email, token, số thẻ hoặc payload nhạy cảm.

Mẫu bảng ghi kết quả:

| Câu hỏi | Nguồn | Kết quả cần ghi |
| --- | --- | --- |
| p95 payments tăng từ lúc nào? | Metrics dashboard | Thời gian bắt đầu, p95, error rate |
| Một request cụ thể chậm ở đâu? | Trace backend | Trace ID, span ID, module/method, duration |
| Vì sao thanh toán thất bại? | Log search | Error category, exception, fallback/retry |
| Event nào được công bố? | Modulith event metrics | Module identifier và event type |
| Worker có cùng trace context? | Log + trace | traceId/spanId trước và sau executor |
| Metrics có exemplar? | Metrics backend | Trace link hoặc phương án tìm theo thời gian |

**Tiêu chí đạt:** bắt đầu từ alert metrics, tìm được trace cụ thể, mở được log liên quan bằng traceId, phân biệt được event publish với listener execution, và giải thích được vì sao trace sampling không làm mất giá trị của metrics tổng hợp.

## 16. Ghi nhớ

Ba tín hiệu có vai trò bổ trợ:

~~~text
METRICS  → vấn đề phổ biến đến đâu, tăng từ khi nào?
   │
   └── exemplar hoặc operation/time window
          ↓
TRACE    → request đi qua module nào, chậm ở span nào?
   │
   └── traceId + spanId
          ↓
LOGS     → code ghi nhận lỗi/nhánh xử lý nào trong operation?
~~~

Với Spring Modulith, hãy dùng module identifier và module entry spans để đặt hành vi runtime vào ranh giới application module. Dùng event publication metrics để theo dõi domain event được công bố; dùng Timer/metrics để xem xu hướng; dùng traceId/spanId để nối log với trace; dùng correlation ID nghiệp vụ cho quan hệ kéo dài qua nhiều request hoặc event.

Không đưa định danh từng request vào metric tags. Không dùng baggage làm payload nghiệp vụ. Không mặc định một trace tồn tại suốt vòng đời đơn hàng. Một quy trình quan sát tốt giữ đúng ý nghĩa của từng tín hiệu và chỉ liên kết chúng bằng metadata được quản lý.

### Tài liệu tham khảo

- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) — logging patterns, correlation prefix và structured logging.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — Micrometer Tracing, sampling, baggage và log correlation.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Observation, low/high-cardinality key-values và context propagation.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Actuator metrics, registry và Prometheus exemplars.
- [Micrometer Tracing — Baggage](https://docs.micrometer.io/tracing/reference/api.html) — baggage, propagation và correlation.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — chuẩn traceparent/tracestate.
- [OpenTelemetry — Exemplars](https://opentelemetry.io/docs/specs/otel/metrics/data-model/#exemplars) — liên kết measurement sample với trace context.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — module entry spans và event publication metrics.

> **Lưu ý phiên bản:** tên property, logging pattern mặc định và cách cấu hình exporter có thể khác giữa các dòng Spring Boot/Micrometer. Hãy đối chiếu reference guide và output thực tế của ứng dụng đang chạy. Bài được soạn trong STEP 4; Content QA chuyên môn thuộc bước riêng.
