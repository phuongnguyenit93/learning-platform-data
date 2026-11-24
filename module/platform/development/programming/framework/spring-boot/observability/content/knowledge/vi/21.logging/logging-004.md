# Trace ID và span ID trong MDC với Spring Boot

Khi request đi qua controller, service, repository và HTTP client, logs xuất hiện ở nhiều lớp và nhiều service. Nếu log event không có thông tin liên kết, người vận hành phải dò timestamp hoặc message để ghép các sự kiện thuộc cùng request. **Trace ID** liên kết các spans trong một trace; **Span ID** xác định thao tác cụ thể đang phát log. **MDC (Mapped Diagnostic Context)** cho phép logging framework gắn hai giá trị đó vào log event mà không phải truyền ID qua mọi method.

Trong module **SPRING_BOOT_OBSERVABILITY**, MDC kết nối distributed tracing với logs bên cạnh Micrometer Observation, metrics, baggage, exporter và sampling. Bài thuộc chương **Logging**, tập trung vào **Trace ID và span ID trong MDC**: cách Spring Boot/Micrometer Tracing cung cấp correlation fields, cách Logback hiển thị chúng, lifecycle của context, async/thread propagation, structured logs, bảo mật và kiểm thử.

## Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt Trace ID, Span ID, Parent Span ID và MDC.
2. Giải thích vì sao log event nên chứa cả trace ID lẫn span ID.
3. Cấu hình Spring Boot/Micrometer Tracing để correlation IDs xuất hiện trong logs.
4. Tùy chỉnh Logback pattern hoặc structured JSON logging.
5. Hiểu MDC scope và rủi ro khi thread pool tái sử dụng thread.
6. Truyền context qua executor, @Async, Reactor và messaging.
7. Kiểm thử correlation fields và cleanup sau scope.
8. Điều tra request bằng cách chuyển từ logs sang trace backend.

## 1. Trace ID và span ID

Một request tạo đơn hàng có thể đi qua order-service, inventory-service và payment-service. Mỗi request flow có một **Trace ID**; mỗi thao tác có một **Span ID** riêng.

| ID | Ý nghĩa | Phạm vi |
| --- | --- | --- |
| Trace ID | Định danh toàn bộ trace | Dùng chung giữa spans trong trace |
| Span ID | Định danh một thao tác | Khác nhau giữa các spans |
| Parent Span ID | Định danh span cha trực tiếp | Dựng quan hệ cha–con |
| MDC traceId | Correlation value logging framework đọc | Context hiện tại |
| MDC spanId | Span hiện hành khi ghi log | Có thể đổi khi child span active |

Ví dụ:

~~~text
2026-11-22 10:15:31.201 INFO [traceId=4bf92f... spanId=00f067...] OrderController - Request received
2026-11-22 10:15:31.207 INFO [traceId=4bf92f... spanId=8a31c2...] OrderService - Validating order
2026-11-22 10:15:31.229 WARN [traceId=4bf92f... spanId=1f42ad...] InventoryClient - Inventory response is slow
~~~

Các dòng có cùng trace ID thuộc một trace; span ID cho biết thao tác phát log. Trace ID được dùng để tìm trace; Span ID định vị span cụ thể. Correlation ID tự tạo trong hệ thống cũ không mặc nhiên là Trace ID. Không ghi đè Trace ID bằng order ID/customer ID.

## 2. MDC là gì?

**Mapped Diagnostic Context (MDC)** là API logging để gắn key-value với log event hiện tại. Với SLF4J, ứng dụng thường dùng API org.slf4j.MDC; Logback cung cấp implementation khi binding tương ứng được sử dụng.

~~~java
import org.slf4j.MDC;

MDC.put("request.channel", "web");
try {
    log.info("Processing order");
} finally {
    MDC.remove("request.channel");
}
~~~

Logback pattern lấy value qua %X{key}. Trong Spring Boot có Micrometer Tracing, logging integration có thể tự quản lý trace/span IDs trong MDC khi span active. Khi đó, không cần gọi MDC.put ở từng controller/service.

MDC không tự tạo trace, sinh span, truyền trace context qua HTTP hoặc export OTLP. Nó cung cấp key-value cho logger khi log event được tạo. Tracing instrumentation quản lý Trace/Span context; logging integration đọc context đó và đưa correlation fields vào MDC hoặc log event.

### 2.1. MDC và ThreadLocal

Nhiều logging implementation lưu MDC theo thread. Cách này thuận tiện cho xử lý đồng bộ nhưng có giới hạn khi dùng thread pool tái sử dụng, @Async/Executor, Reactor đổi thread, callback/event loop, messaging và batch worker. Nếu context không được capture/restore, MDC có thể mất trên thread mới hoặc còn giá trị cũ nếu cleanup sai.

## 3. Spring Boot/Micrometer Tracing tích hợp MDC

Spring Boot tích hợp Micrometer Observation và Micrometer Tracing. Với bridge phù hợp, active span context có thể được dùng để đưa trace ID/span ID vào logging correlation.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Giữ phiên bản theo Spring Boot BOM; không tự ghép version Micrometer/OpenTelemetry không tương thích.

### 3.1. Cấu hình tracing

~~~yaml
spring:
  application:
    name: order-service
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Trong production, endpoint OTLP phải trỏ tới Collector mà process/container có thể truy cập. Sampling probability là cấu hình head-based sampling; nó quyết định traces được ghi nhận/export chứ không quyết định MDC có được populate khi một span đã active hay không.

### 3.2. Logging correlation

Các cấu hình Spring Boot/Micrometer Tracing tương thích có thể thêm correlation IDs vào logging pattern mặc định hoặc hỗ trợ logging.pattern.correlation. Mẫu minh họa:

~~~yaml
logging:
  pattern:
    correlation: "[traceId=%X{traceId:-},spanId=%X{spanId:-}] "
~~~

Property và pattern được hỗ trợ có thể thay đổi theo Spring Boot version. Kiểm tra cấu hình của version đang dùng và quan sát log event thật. Nếu pattern mặc định đã có trace/span fields, tránh thêm lần nữa khiến ID bị lặp.

### 3.3. Logback pattern

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level [traceId=%X{traceId:-} spanId=%X{spanId:-}] [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ví dụ dùng MDC keys traceId và spanId như integration thường cung cấp. Nếu logging bridge đặt tên key khác, điều chỉnh theo MDC map thực tế. Tránh cấu hình pattern trùng lặp.

### 3.4. Khi không có active span

Log event có thể phát sinh trước khi tracing context được tạo, sau khi span đóng hoặc trong tác vụ background không gắn trace. Khi đó traceId/spanId có thể rỗng hoặc dùng fallback dấu gạch ngang. Đây là trạng thái hợp lệ. Đừng tự sinh UUID rồi ghi nó như trace thực; backend sẽ không có trace tương ứng.

## 4. Luồng correlation

~~~mermaid
sequenceDiagram
    participant Client
    participant Filter as Spring Web tracing
    participant Service as OrderService
    participant MDC
    participant Logger
    Client->>Filter: HTTP request + trace context
    Note over Filter: Extract/create context và server span
    Filter->>MDC: Correlation integration đặt traceId/spanId
    Filter->>Service: Gọi controller/service
    Service->>MDC: logger.info(...)
    MDC-->>Logger: Attach correlation fields
    Service-->>Filter: Hoàn tất xử lý
    Note over Filter: Span scope kết thúc, context được restore
~~~

HTTP instrumentation extract trace context từ request hoặc tạo root trace mới. Khi span active, logging integration cung cấp correlation IDs cho log event. Khi span kết thúc, context phải được restore/clear đúng lifecycle. Nếu không có instrumentation hoặc active span, log không tự có trace ID.

## 5. Ghi log trong code

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderApplicationService.class);

    public void createOrder() {
        log.info("Starting order creation");
        validateOrder();
        log.info("Order creation completed");
    }

    private void validateOrder() {
        log.debug("Validating order input");
    }
}
~~~

Các lời gọi logger không cần nhận traceId/spanId. Logging integration lấy correlation context hiện hành. Chỉ log business identifiers khi đã đánh giá dữ liệu có nhạy cảm hay không; ưu tiên event code hoặc định danh giả danh khi phù hợp.

### 5.1. Structured logging

~~~json
{
  "timestamp": "2026-11-22T10:15:31.201Z",
  "level": "INFO",
  "service": "order-service",
  "message": "Order validation completed",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "event": "order_validation_completed"
}
~~~

Đây là schema minh họa. Tên field thực tế phụ thuộc encoder/appender, Spring Boot structured logging và collector. Cần thống nhất tên traceId/trace_id, spanId/span_id với backend. JSON không tự bảo đảm correlation; phải xác nhận values lấy từ active context.

## 6. Parent-child spans và span ID trong MDC

Trace ID giữ nguyên trong cùng trace; Span ID thay đổi theo span hiện hành.

~~~text
Trace ID: 4bf92f...
order-service
  SERVER span A: spanId=1111
    log: request received
    INTERNAL span B: spanId=2222
      log: validating order
      CLIENT span C: spanId=3333
        log: calling inventory
inventory-service
  SERVER span D: spanId=4444, parentSpanId=3333
    log: reserving stock
~~~

MDC correlation cần phản ánh active span tại thời điểm log event. Khi tracing scope chuyển sang child span, logging bridge có thể cập nhật span ID hiện hành. Khi child scope kết thúc, context parent được khôi phục. Không đọc trace/span ID một lần ở đầu request rồi copy vào object dùng cho mọi log.

## 7. MDC lifecycle và cleanup

Với code tự thêm MDC fields, luôn dùng try/finally:

~~~java
import org.slf4j.MDC;

public void processWithLocalContext(String channel) {
    MDC.put("orders.channel", channel);
    try {
        log.info("Processing order");
    } finally {
        MDC.remove("orders.channel");
    }
}
~~~

Nếu cần restore giá trị cũ, lưu giá trị trước đó rồi khôi phục trong finally. Không tự sửa traceId/spanId trong MDC khi tracing integration đang quản lý chúng. Không lưu MDC vào static field, singleton mutable map hoặc biến toàn cục.

## 8. Async và context propagation

MDC thường gắn với thread. Khi @Async hoặc executor chuyển việc sang thread khác, MDC không tự động được bảo đảm copy. Tracing context cũng cần capture/restore bằng cơ chế phù hợp.

~~~text
HTTP thread A:
  traceId = T1
  spanId  = S1
  submit task

Worker thread B:
  task runs
  MDC may be empty nếu context không được capture
~~~

Với Spring Framework 6.1+ và Micrometer Context Propagation, ContextPropagatingTaskDecorator giúp capture/restore những context accessor đã đăng ký:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Decorator không tự biến mọi ThreadLocal thành context có thể propagate. Tracing/MDC accessors tương ứng phải được đăng ký và cấu hình phù hợp.

Với @Async cần cấu hình @EnableAsync và executor bean. Reactor có execution context riêng; dùng Micrometer Context Propagation và tích hợp Reactor phù hợp version. Kafka/RabbitMQ cần inject/extract context qua message headers. Consumer phải restore context sau xử lý để worker không mang IDs của message trước.

## 9. Liên kết logs với trace backend

Khi log event có Trace ID:
1. Tìm log theo traceId và event/error code.
2. Mở trace backend và tìm trace tương ứng.
3. Xem span theo spanId để biết thao tác phát log.
4. Kiểm tra parent/child spans, latency, status và dependency attributes.
5. Quay lại logs theo Trace ID để xem sự kiện liên quan.

~~~mermaid
flowchart LR
    Log["Log event<br/>traceId + spanId"] --> Query["Search trace ID"]
    Query --> Trace["Trace backend"]
    Trace --> Span["Locate span ID"]
    Span --> Parents["Inspect parent/child spans"]
    Parents --> Logs["Search related logs"]
    Logs --> Diagnose["Diagnose request"]
~~~

Log có trace ID nhưng không tìm thấy trace có thể do head sampler bỏ trace, exporter lỗi, Collector/backend drop hoặc retention/time range. MDC chứng minh logging integration nhìn thấy context tại thời điểm log; không chứng minh trace đã được export và lưu.

## 10. Bảo mật và dữ liệu trong MDC

| Dữ liệu | Chính sách | Nguyên tắc |
| --- | --- | --- |
| traceId | Có khi active | Tìm trace; không dùng làm metric label |
| spanId | Có khi active | Định vị span cụ thể |
| service.name | Có thể | Giá trị ổn định, chuẩn hóa |
| orders.channel | Cân nhắc | Field được duyệt, tập giá trị hữu hạn |
| user.email | Không mặc định | PII |
| Authorization/cookie | Không | Secret, tuyệt đối không log |
| Request/response body | Không mặc định | Có thể chứa PII/payment data |
| order.id/customer.id | Cân nhắc nghiêm ngặt | Có thể định danh và tăng cardinality |

Không đưa trace ID vào metric labels vì mỗi trace tạo giá trị mới, làm tăng time series. Nếu backend hỗ trợ exemplars, dùng exemplar để nối metric sample với trace. Không copy mọi baggage member vào MDC/JSON vì có thể chứa dữ liệu do caller kiểm soát, PII hoặc value quá dài. Áp dụng access control, retention, masking/redaction và audit.

## 11. Kiểm thử trace/span correlation trong MDC

Cần test tracing context tạo ID, MDC nhận ID, logger ghi ID và context được cleanup.

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class TraceMdcIntegrationTest {
    @Autowired
    Tracer tracer;

    @Test
    void exposesTraceAndSpanIdsWhileSpanIsActive() {
        Span span = tracer.nextSpan().name("test-operation");
        try (Tracer.SpanInScope scope = tracer.withSpan(span.start())) {
            assertNotNull(MDC.get("traceId"));
            assertNotNull(MDC.get("spanId"));
        } finally {
            span.end();
        }
    }
}
~~~

Đây là integration test cần tracing auto-configuration và logging correlation integration trong test context. Tên MDC keys phải được xác minh theo implementation/version. Test thêm Logback appender để capture event, xác minh fields trong output và cleanup khi scope đóng. Tạo parent/child để kiểm tra cùng Trace ID, Span ID khác nhau và parent được restore.

### 11.1. Test async cleanup

Dùng executor có một worker thread để buộc tái sử dụng:
1. Task A chạy trong span A và log IDs.
2. Task A hoàn tất, scope đóng.
3. Task B không có context không được mang IDs của A.
4. Task C có span C, log mang IDs của C.
5. Lặp để phát hiện rò rỉ/race.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log không có traceId/spanId | Không có active span hoặc logging integration không hoạt động | Kiểm tra tracing bridge, instrumentation và MDC |
| Chỉ có traceId nhưng thiếu spanId | Pattern/key mapping sai hoặc không có current span | Xem MDC map và active scope |
| Mọi log có cùng spanId | ID copy tĩnh hoặc MDC không cập nhật theo child scope | Kiểm tra integration, bỏ MDC tự quản lý |
| Span ID trống ở async | Context không được capture/restore | Cấu hình executor/context propagation |
| Log mang traceId request trước | ThreadLocal/MDC không cleanup | Kiểm tra scope close, finally và thread reuse |
| Có traceId nhưng backend trống | Sampling drop hoặc export/backend lỗi | Kiểm tra sampling, exporter, Collector |
| Trace có nhưng query log không ra | Encoder không xuất MDC field hoặc collector drop field | Kiểm tra JSON và pipeline logs |
| IDs xuất hiện hai lần | Default pattern và custom pattern cùng thêm correlation | Chỉ giữ một cấu hình |
| Trace ID sai giữa services | Propagation/context extraction sai | Kiểm tra traceparent và HTTP instrumentation |
| IDs mất trong Reactor | Context không propagate trong reactive chain | Kiểm tra Reactor/Micrometer integration |
| Logs lộ baggage/PII | Correlation map quá rộng | Allowlist, redaction và incident review |

Quy trình kiểm tra: xác minh request có server span; kiểm tra current span trong scope; đọc MDC map trước lệnh logger; kiểm tra event sau encoder/appender; xác minh async context propagation và cleanup; tìm Trace ID ở backend; cuối cùng kiểm tra log collector có giữ fields hay không. Đừng tự sinh UUID rồi gán vào traceId để che giấu lỗi propagation.

## 13. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Tracing được cấu hình | Spring Boot Actuator, Micrometer Tracing bridge và tracer hoạt động |
| Trace/span IDs có trong logs | Log event thực tế có correlation fields |
| MDC keys thống nhất | traceId/spanId khớp query schema backend |
| Không ghi ID giả | IDs đến từ active tracing context |
| Parent/child context đúng | log spanId đổi đúng khi child scope active |
| Scope cleanup đúng | Không còn context cũ khi scope đóng |
| Async propagation đã test | Executor/Reactor/messaging có context integration |
| JSON fields riêng | Backend parse được traceId/spanId |
| Bảo mật logs | Không token, cookie, PII hoặc payload |
| Cardinality metrics kiểm soát | Không đưa Trace ID/Span ID thành metric labels |
| Sampling/export được giám sát | Biết trace có thể bị drop dù log có ID |
| Access/retention có chính sách | Có phân quyền và thời hạn lưu |

## 14. Bài thực hành: điều tra lỗi từ log tới trace

**Bối cảnh:** người dùng báo tạo đơn chậm. Logs của order-service và inventory-service đến log backend; traces đến OTLP Collector. Nhóm vận hành muốn từ một dòng log mở được đúng span và xem toàn bộ trace.

**Nhiệm vụ:**
1. Thêm Actuator và Micrometer Tracing bridge OpenTelemetry theo BOM.
2. Cấu hình HTTP server/client instrumentation và OTLP exporter tới Collector.
3. Xác minh Logback correlation có cả traceId và spanId.
4. Tạo custom Observation orders.checkout và gọi inventory-service qua HTTP client đã instrument.
5. Ghi logs ở controller, business service và client call; kiểm tra trace ID chung và span ID tương ứng span hiện hành.
6. Dùng structured JSON hoặc pattern để output traceId/spanId thành fields riêng.
7. Tạo child span và xác minh span ID thay đổi trong log; sau child scope, parent span ID được restore.
8. Chuyển task sang executor, cấu hình context propagation và xác minh MDC trong worker.
9. Chạy task tiếp theo trên cùng thread nhưng không có context; xác nhận không còn IDs của task trước.
10. Tìm log event theo Trace ID, mở trace backend và xác định span theo Span ID.
11. Giảm sampling để quan sát trường hợp log có trace ID nhưng trace không được lưu; giải thích nguyên nhân.
12. Kiểm tra logs không có token, email, raw request body và Trace ID không xuất hiện trong metric labels.

**Kết quả mong đợi:** cấu hình correlation logging, log event mẫu có trace/span IDs, trace nhiều spans qua hai service, test MDC scope/async cleanup và runbook từ log tới trace.

## 15. Ghi nhớ

**Trace ID** liên kết các spans trong một trace; **Span ID** xác định thao tác cụ thể. **MDC** cho phép logging framework gắn hai giá trị này vào từng log event. Trong Spring Boot, Micrometer Tracing và logging integration có thể quản lý correlation fields theo active span, còn Logback/structured logging quyết định cách xuất chúng.

MDC không tạo trace và không thay thế W3C propagation hoặc OTLP export. Scope phải được restore khi span kết thúc; async, executor và Reactor cần context propagation phù hợp để tránh mất hoặc rò rỉ IDs giữa các request. Dùng Trace ID để đi từ logs tới trace backend, Span ID để định vị thao tác; bảo vệ logs bằng allowlist, redaction, retention và không đưa IDs thành metric labels.

**Tài liệu tham khảo:**
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [SLF4J — MDC](https://www.slf4j.org/manual.html#mdc)
- [Logback — Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)

