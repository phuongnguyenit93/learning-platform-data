# Liên kết log với module span

## Mục tiêu học tập

Trong học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, Spring Modulith giúp sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Bài này hướng dẫn liên kết **log lines** với **module spans** để người vận hành có thể đi từ một thông báo lỗi tới trace chứa hoạt động liên quan, rồi quay lại các log chi tiết.

Sau bài học, bạn có thể:

1. Phân biệt log, trace, span, trace ID, span ID và correlation ID.
2. Giải thích cách Spring Boot đưa `traceId` và `spanId` vào **MDC** khi Micrometer Tracing hoạt động.
3. Cấu hình log pattern hoặc structured logging để hiển thị correlation fields.
4. Phân biệt **module attributes trên span** với **MDC fields trong log**.
5. Bổ sung module identifier vào log một cách có chủ đích và khôi phục MDC sau khi xử lý.
6. Truy tìm một lỗi từ log sang module span và từ trace sang log liên quan.
7. Duy trì correlation qua `@Async`, executor, Reactor và lời gọi HTTP.
8. Kiểm soát dữ liệu nhạy cảm, cardinality và retention trong log/trace.
9. Kiểm thử việc liên kết log-span và điều tra trường hợp correlation bị mất.

**Bối cảnh:** Module graph và Actuator cho biết cấu trúc application module; event metrics cho biết xu hướng publication; Micrometer Tracing ghi lại các hoạt động đã được instrument; Spring Modulith bổ sung module entry spans cho tương tác qua API module. Logging lưu thông điệp chi tiết. **Correlation ID giúp liên kết hai nguồn dữ liệu này.**

> **Phạm vi phiên bản:** Ví dụ chính tham chiếu Spring Boot 4.2 và Spring Modulith 2.2. Spring Boot 3.x cũng hỗ trợ correlation ID dựa trên MDC và property `logging.pattern.correlation`; các property tùy chỉnh MDC có thể khác theo release. Kiểm tra reference guide đúng phiên bản của dự án trước khi áp dụng.

## 1. Vì sao cần liên kết log với module span?

Giả sử request tạo đơn đi qua ba application module:

- `orders` tiếp nhận yêu cầu và điều phối đơn hàng;
- `inventory` giữ hàng qua API module;
- `payments` nhận event để chuẩn bị thanh toán.

Một trace có thể chứa HTTP server span, module entry span, database/client spans và event listener span. Trace cho biết **đoạn nào** chậm hoặc lỗi; log cung cấp **thông điệp cụ thể** mà code đã ghi tại thời điểm đó.

Ví dụ các log line:

~~~text
INFO  OrderService     - Order submitted
INFO  InventoryFacade  - Reservation started
WARN  InventoryFacade  - Reservation timed out
ERROR OrderService     - Checkout failed
~~~

Không có ID tương quan, người vận hành phải đoán các dòng trên có thuộc cùng một request hay không. Khi log chứa trace ID và span ID, có thể:

1. Tìm trace theo `traceId`.
2. Mở span có `spanId` tương ứng.
3. Xác nhận span thuộc module `inventory` qua `module.identifier` và `module.name`.
4. Xem span cha, span con, duration và lỗi.
5. Tìm các log khác có cùng trace ID để hiểu diễn biến toàn workflow.

**Log giải thích sự kiện ở cấp ứng dụng; span cho thấy quan hệ và thời gian giữa các hoạt động.**

## 2. Trace ID, span ID và correlation ID

| Khái niệm | Ý nghĩa | Dùng để |
| --- | --- | --- |
| **Trace ID** | Định danh của toàn trace. | Tìm các spans và logs thuộc cùng trace. |
| **Span ID** | Định danh của một span cụ thể. | Định vị hoạt động đang được log. |
| **Parent span ID** | Quan hệ cha–con giữa các spans. | Xem span được tạo từ hoạt động nào. |
| **Correlation ID** | Chuỗi hoặc trường được dùng để liên kết log với trace. | Tìm log và trace liên quan. |
| **orderId** | Định danh đơn hàng trong domain. | Liên kết dữ liệu nghiệp vụ qua nhiều trace. |
| **eventId** | Định danh event nghiệp vụ. | Đối soát hoặc deduplicate event. |

Một đơn hàng có thể tồn tại nhiều ngày và đi qua nhiều request; do đó cùng `orderId` có thể liên quan nhiều trace ID. Không dùng trace ID làm khóa idempotency hoặc khóa chính của đơn hàng.

## 3. MDC là gì?

**MDC (Mapped Diagnostic Context)** là cơ chế lưu các cặp key-value gắn với ngữ cảnh logging hiện tại. Với SLF4J, ứng dụng có thể đọc/ghi MDC bằng `org.slf4j.MDC`; Logback và các logging framework có thể đưa các giá trị đó vào pattern hoặc structured output.

Ví dụ MDC:

~~~text
traceId           = 4bf92f3577b34da6a3ce929d0e0e4736
spanId            = 00f067aa0ba902b7
module.identifier = inventory
requestId         = req-7f82
~~~

MDC truyền thống dựa trên thread-local context. Log được ghi trên thread đang có tracing scope thường thấy trace/span tương ứng; khi chuyển sang thread khác, MDC không tự động được sao chép trong mọi trường hợp. Thread pool còn tái sử dụng thread, vì vậy phải khôi phục hoặc xóa giá trị MDC đúng cách.

## 4. Spring Boot tự thêm correlation ID

Khi Micrometer Tracing được cấu hình, Spring Boot đưa `traceId` và `spanId` vào MDC trong phạm vi span hiện tại. Logging mặc định dùng hai giá trị này để tạo correlation ID.

Dạng minh họa:

~~~text
[803B448A0489F84084905D3093480352-3425F23BB2432450]
~~~

Phần trước dấu gạch nối là trace ID; phần sau là span ID. Nếu tracing được cấu hình đúng, **không cần tự tạo trace ID hoặc tự ghi đè hai MDC keys này**.

Để correlation hoạt động, cần:

1. Có Micrometer Tracing implementation phù hợp, ví dụ Brave hoặc OpenTelemetry.
2. Hoạt động đang chạy được instrument và có current span.
3. Span được đưa vào scope trong lúc code ghi log.
4. Logging pattern hoặc encoder hiển thị correlation ID/MDC.
5. Context được propagate nếu công việc chuyển qua thread hoặc reactive boundary.

Spring Modulith Insight cung cấp module observability; muốn gửi spans tới Zipkin, Tempo hoặc backend khác vẫn cần tracer/exporter phù hợp theo Spring Boot.

### 4.1. Lưu ý với Brave

Tài liệu Spring Boot hiện hành lưu ý rằng với Brave, việc ghi trace/span IDs vào MDC liên quan đến cấu hình baggage. Nếu tắt `management.tracing.baggage.enabled`, Brave có thể ngừng ghi các ID này vào MDC và correlation ID không còn xuất hiện như mong đợi. Khi correlation biến mất sau thay đổi cấu hình baggage, hãy kiểm tra hành vi theo đúng phiên bản và tracer bridge trước khi thêm MDC code thủ công.

## 5. Cấu hình log pattern

Spring Boot cung cấp property `logging.pattern.correlation` để tùy biến format correlation ID.

~~~yaml
spring:
  application:
    name: shop-service

logging:
  pattern:
    correlation: "[shop-service,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

Kết quả minh họa:

~~~text
2026-11-27T09:12:01.101Z INFO [shop-service,4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7] c.e.shop.orders.OrderService : Order submitted
~~~

Dấu cách cuối trong correlation pattern giúp tách correlation ID khỏi tên logger. Vì application name đã nằm trong pattern, `logging.include-application-name: false` tránh lặp tên ứng dụng.

Nếu không cần format riêng, có thể giữ cấu hình mặc định của Spring Boot.

### 5.1. Tùy chỉnh tên MDC keys

Các phiên bản Spring Boot hiện hành có thể cho phép đổi tên keys:

~~~yaml
management:
  tracing:
    mdc:
      trace-id-key: trace_id
      span-id-key: span_id

logging:
  pattern:
    correlation: "[%X{trace_id:-},%X{span_id:-}] "
~~~

Khi đổi tên, correlation pattern phải tham chiếu đúng key mới. Kiểm tra property availability theo version; nếu không có nhu cầu đặc biệt, giữ tên mặc định `traceId` và `spanId` sẽ đơn giản hơn.

## 6. Metadata của Spring Modulith nằm trên span

Spring Modulith có thể instrument các Spring components thuộc **API của application module** để tạo Micrometer spans. Module Entry Span có các tag được tài liệu hóa:

| Attribute | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh kỹ thuật của application module. |
| `module.name` | Tên hiển thị của module. |
| `module.invocation-type` | Loại điểm vào, ví dụ `bean` hoặc `event listener`. |
| `module.method` | Method được thực thi tại module entry. |

Ví dụ span minh họa:

~~~text
Span name: inventory module entry
traceId: 4bf92f3577b34da6a3ce929d0e0e4736
spanId: 00f067aa0ba902b7
attributes:
  module.identifier = inventory
  module.name = Inventory
  module.invocation-type = bean
  module.method = InventoryFacade.reserve
~~~

### 6.1. Module attributes không tự động là MDC fields

Cần phân biệt:

- `module.identifier` là attribute/tag trên module observation/span theo Spring Modulith.
- `traceId` và `spanId` là correlation values mà Spring Boot/Micrometer Tracing đưa vào MDC.
- Hai nhóm metadata có mục đích khác nhau.

Vì vậy, không mặc định mỗi log line đều có `module.identifier` chỉ vì trace chứa module span. Nếu cần tìm log trực tiếp theo module trong log backend, ứng dụng phải thêm module identifier vào structured log/MDC theo một quy ước riêng. Nếu không, tìm trace theo ID rồi xem module attributes trên span thường đã đủ.

### 6.2. Log trong module method gắn với span nào?

Khi lời gọi đi vào module API và Spring Modulith tạo module entry span, code chạy trong phạm vi span đó có thể ghi log với current span tương ứng. Nếu instrumentation con đang hoạt động, ví dụ HTTP client hoặc database, log trong đoạn gọi con có thể mang span ID của child span đang current. Sau khi child span kết thúc, current span có thể trở lại module span.

Hãy xác minh trên trace thực tế; không giả định mọi method nội bộ đều có module span. Spring Modulith tập trung instrument các điểm vào API module được framework nhận diện.

## 7. Ví dụ log trong module API

Giả sử module `inventory` công khai bean API:

~~~java
package com.example.shop.inventory;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryFacade {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryFacade.class);

    public void reserve(UUID orderId) {
        log.info("Starting inventory reservation");

        boolean reserved = reserveStock(orderId);

        if (reserved) {
            log.info("Inventory reservation completed");
        } else {
            log.warn("Inventory reservation rejected");
        }
    }

    private boolean reserveStock(UUID orderId) {
        // Thay bằng logic domain và persistence thực tế.
        return true;
    }
}
~~~

Khi một module khác gọi `InventoryFacade.reserve` qua Spring-managed bean và instrumentation của Spring Modulith hoạt động, module entry span có thể bao quanh lời gọi. Log trong method được ghi khi tracing scope đang hoạt động; nếu MDC được cấu hình đúng, log line có correlation ID.

### 7.1. Bên gọi

~~~java
package com.example.shop.orders;

import com.example.shop.inventory.InventoryFacade;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    private final InventoryFacade inventory;

    public OrderService(InventoryFacade inventory) {
        this.inventory = inventory;
    }

    public void place(UUID orderId) {
        log.info("Order placement started");
        inventory.reserve(orderId);
        log.info("Order placement continued after inventory");
    }
}
~~~

Log ở `OrderService` có thể gắn với span của luồng orders; log bên trong `InventoryFacade` có thể gắn với module entry span của inventory. Hai nhóm log chia sẻ trace ID nếu nằm trong cùng trace và context được quản lý đúng.

### 7.2. Đọc log và trace

Giả sử log có correlation ID:

~~~text
[shop-service,4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7]
WARN InventoryFacade - Inventory reservation rejected
~~~

Từ log, lấy trace ID, tìm trace trong Zipkin/Tempo/Jaeger, rồi tìm span ID. Xác minh span có `module.identifier=inventory`, đọc parent span để biết orders gọi inventory từ đâu và xem các span con/lỗi liên quan.

Nếu log có trace ID nhưng backend không tìm thấy trace, kiểm tra sampling, exporter, retention và khoảng thời gian truy vấn.

## 8. Thêm module identifier vào log một cách chủ động

Nếu log backend được truy vấn độc lập với tracing backend và nhóm vận hành cần lọc trực tiếp theo module, có thể thêm module identifier vào log record.

### 8.1. SLF4J fluent key-value logging

Với SLF4J 2.x:

~~~java
log.atInfo()
    .addKeyValue("module.identifier", "inventory")
    .addKeyValue("reservation.result", "RESERVED")
    .log("Inventory reservation completed");
~~~

Cách này thêm metadata cho một log event. Để các trường xuất hiện trong output, logging backend/encoder phải hỗ trợ key-value logging. Spring Boot structured logging có thể đưa các key-value này vào JSON.

### 8.2. MDC cho phạm vi xử lý đồng bộ

Nếu nhiều log trong một đoạn code cần cùng module identifier, đặt MDC key trong phạm vi ngắn và khôi phục giá trị cũ:

~~~java
import org.slf4j.MDC;

private void logReservation(UUID orderId) {
    String key = "module.identifier";
    String previous = MDC.get(key);

    MDC.put(key, "inventory");
    try {
        log.info("Reservation started");
        reserveStock(orderId);
        log.info("Reservation finished");
    } finally {
        if (previous == null) {
            MDC.remove(key);
        } else {
            MDC.put(key, previous);
        }
    }
}
~~~

Phải khôi phục MDC trong `finally`. Thread pool tái sử dụng thread; nếu đặt MDC mà không xóa/khôi phục, request sau có thể nhận nhầm module identifier của tác vụ trước. Ví dụ này chỉ áp dụng cho phạm vi đồng bộ; async cần context propagation hoặc đặt MDC scope trong thread thực thi.

### 8.3. Đưa module field vào plain text pattern

~~~yaml
logging:
  pattern:
    level: "%5p [module=%X{module.identifier:-}]"
~~~

Giá trị `module.identifier` chỉ xuất hiện khi code đã đưa key đó vào MDC. Pattern không tự suy ra module hiện tại từ Spring Modulith span. Giữ cả correlation pattern và module field nếu cả hai cần thiết.

### 8.4. Structured logging

Spring Boot hỗ trợ structured logging như ECS, GELF và Logstash. Ví dụ bật JSON console format:

~~~yaml
logging:
  structured:
    format:
      console: ecs
~~~

Structured logging giúp truy vấn từng field thay vì parse chuỗi. Một record minh họa:

~~~json
{
  "@timestamp": "2026-11-27T09:12:03.125Z",
  "log.level": "WARN",
  "message": "Inventory reservation rejected",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "00f067aa0ba902b7",
  "module.identifier": "inventory",
  "reservation.result": "REJECTED"
}
~~~

Tên field thực tế phụ thuộc encoder, MDC keys và cách structured logging chuẩn hóa dữ liệu. Hãy kiểm tra record thật trước khi viết truy vấn production.

## 9. Tìm log từ trace và trace từ log

### 9.1. Từ log tới trace

1. Tìm log có level WARN/ERROR hoặc message bất thường.
2. Lấy `traceId` và `spanId` từ correlation fields.
3. Mở tracing backend và tìm trace theo trace ID.
4. Tìm span theo span ID.
5. Kiểm tra module attributes và quan hệ parent-child.
6. Mở các span lân cận để tìm bước trước/sau.
7. Quay lại log store và lọc toàn bộ log cùng trace ID.

Ví dụ truy vấn khái niệm:

~~~text
traceId = "4bf92f3577b34da6a3ce929d0e0e4736"
AND level IN ("WARN", "ERROR")
~~~

Đây là pseudo-query; cú pháp thực tế phụ thuộc Elasticsearch, Loki, Splunk, Datadog hoặc hệ thống đang dùng.

### 9.2. Từ trace tới log

1. Mở trace có duration cao hoặc span status ERROR.
2. Chọn module entry span cần điều tra.
3. Sao chép trace ID và span ID.
4. Tìm log theo trace ID để lấy thông điệp trong toàn workflow.
5. Nếu log có span ID, lọc tiếp theo span ID.
6. Nếu log không có module identifier, dùng span attributes để xác định module.

Trace ID là khóa tìm kiếm rộng cho một trace; span ID thu hẹp về hoạt động cụ thể. Nếu log chỉ ghi trace ID, vẫn tìm được log của toàn trace nhưng khó phân biệt log thuộc module span nào.

## 10. Context propagation qua @Async và executor

Khi code chuyển sang thread khác, tracing context và logging MDC có thể không tự động đi theo. Điều này thường xảy ra với `@Async`, executor, scheduler hoặc callback bất đồng bộ.

### 10.1. AsyncTaskExecutor auto-configured

Với `@Async` và `AsyncTaskExecutor` được Spring Boot auto-configure, có thể opt-in context propagation:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Property này giúp context hiện tại được khôi phục trong task execution theo hỗ trợ của Boot. Kiểm tra đúng phiên bản Boot và executor thực tế đang dùng.

### 10.2. Custom executor

Nếu tự tạo executor, gắn `ContextPropagatingTaskDecorator` vào executor:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("shop-async-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
~~~

Decorator hỗ trợ khôi phục context được đăng ký cho task khi chạy ở thread khác. Các MDC fields do ứng dụng tự thêm cần được kiểm tra riêng để chắc chắn chúng có accessor/cơ chế propagation phù hợp.

### 10.3. Async listener

~~~java
@Component
class PaymentPreparationListener {

    private static final Logger log =
        LoggerFactory.getLogger(PaymentPreparationListener.class);

    @Async
    @EventListener
    public void on(OrderPlaced event) {
        log.info("Preparing payment for order");
        // Xử lý theo chính sách thanh toán.
    }
}
~~~

Nếu async context được propagate, log trong listener có thể mang correlation ID liên quan tới trace đã phát event theo mô hình propagation đang dùng. Nếu không, trace/span fields có thể trống hoặc listener tạo một trace khác.

`@EventListener` mặc định thường xử lý đồng bộ; `@Async` hoặc executor mới thay đổi execution boundary.

## 11. Context propagation trong Reactor và HTTP

### 11.1. Reactor

Trong reactive pipeline, ThreadLocal không tự động được khôi phục ở mọi operator. Spring Boot cho phép cấu hình:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Khi bật chế độ phù hợp, context có thể được phục hồi trong reactive operators theo cơ chế Context Propagation. Kiểm tra các operator, scheduler và thư viện thực tế; không giả định toàn bộ pipeline chạy trên cùng thread.

### 11.2. HTTP giữa các service

Để log ở service downstream có trace ID tương ứng, client cần inject trace context và server cần extract nó. Với Spring Boot, dùng builder auto-configured:

~~~java
@Component
class InventoryHttpClient {

    private final RestClient client;

    InventoryHttpClient(RestClient.Builder builder) {
        this.client = builder
            .baseUrl("http://inventory-service")
            .build();
    }

    String reserve(String orderReference) {
        return client.post()
            .uri("/reservations")
            .body(orderReference)
            .retrieve()
            .body(String.class);
    }
}
~~~

Nếu tự tạo client mà không dùng builder đã được Boot cấu hình, automatic trace propagation có thể không hoạt động. Khi context được truyền đúng, logs ở service downstream có thể dùng cùng trace ID nhưng span ID khác nhau theo từng span.

### 11.3. Message broker và event processing

Với messaging qua broker, cần instrumentation/propagation tương ứng để trace context được ghi vào message headers và được consumer trích xuất. Không chỉ đặt `traceId` vào payload event rồi coi đó là propagation chuẩn.

Nếu message được xử lý sau một khoảng thời gian hoặc retry, quan hệ trace có thể dùng parent hoặc span link tùy instrumentation. Business event ID và order ID vẫn có vai trò riêng để đối soát.

## 12. Structured logging và các trường module hữu ích

| Field | Mục đích | Nguồn |
| --- | --- | --- |
| `timestamp` | Thời điểm log được ghi. | Logging framework. |
| `service.name` | Ứng dụng/service tạo log. | `spring.application.name` hoặc encoder config. |
| `traceId` | Liên kết tới toàn trace. | Micrometer Tracing MDC. |
| `spanId` | Liên kết tới span đang current. | Micrometer Tracing MDC. |
| `module.identifier` | Lọc log theo module. | Ứng dụng thêm có chủ đích, hoặc suy ra qua span. |
| `module.method` | Xác định method trong module. | Ứng dụng thêm nếu cần; span đã có module attribute. |
| `event.type` | Loại event nghiệp vụ liên quan. | Ứng dụng. |
| `event.id` | Tra cứu event cụ thể. | Domain/event infrastructure. |
| `order.id` | Liên kết log với đơn hàng. | Ứng dụng, theo chính sách dữ liệu. |
| `error.type` | Phân loại lỗi. | Exception mapping/logging. |

Không phải mọi field đều cần có ở mọi log line. Chọn tập field nhỏ, nhất quán, có ý nghĩa và được phép lưu trữ.

### 12.1. Correlation ID không phải metric tag

Trace ID, span ID, order ID và event ID thường có cardinality cao. Chúng có thể phù hợp làm trường trong log hoặc span attributes theo chính sách, nhưng **không nên đưa vào metric tags**.

Metrics cần nhóm theo các giá trị hữu hạn như module identifier, invocation type, outcome hoặc channel đã normalize. Log có thể lưu ID để tra cứu bản ghi cụ thể nhưng phải cân nhắc retention, phân quyền và dữ liệu cá nhân.

### 12.2. Không log toàn bộ event payload

Không nên:

~~~java
log.info("Received event: {}", event);
~~~

Nếu event chứa email, địa chỉ, payment token hoặc payload lớn, log có thể vô tình lưu dữ liệu nhạy cảm. Thay vào đó, ghi thông điệp ngắn và field được phê duyệt:

~~~java
log.atInfo()
    .addKeyValue("event.type", "OrderPlaced")
    .addKeyValue("event.id", event.eventId())
    .log("Order event received");
~~~

Ngay cả event ID cũng cần được quản lý theo chính sách dữ liệu; không ghi credential, token hoặc thông tin thanh toán nhạy cảm.

## 13. Troubleshooting: log không liên kết với module span

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Log không có trace ID/span ID | Chưa có Micrometer Tracing, không có current span, logging pattern không hiển thị MDC. | Kiểm tra tracing dependency, active span và correlation pattern. |
| Có trace ID nhưng span ID trống | MDC key tùy chỉnh sai, scope không current hoặc bridge/config có vấn đề. | Kiểm tra key names, tracing scope và output MDC. |
| Có correlation ID nhưng backend không có trace | Trace bị sampling, exporter lỗi, backend retention hoặc truy vấn sai. | Kiểm tra sampling, exporter logs, collector và time range. |
| HTTP logs có ID nhưng async listener không có | Context không propagate qua executor. | Kiểm tra `spring.task.execution.propagate-context` hoặc task decorator. |
| Reactive logs mất correlation | ThreadLocal không được khôi phục trong Reactor pipeline. | Kiểm tra `spring.reactor.context-propagation`. |
| Log có module identifier cũ | MDC không được khôi phục/xóa sau task, hoặc code dùng giá trị module sai. | Kiểm tra `finally`, thread reuse và MDC lifecycle. |
| Trace có module attributes nhưng log không có module field | Module metadata chỉ nằm trên span, chưa được thêm vào MDC/log record. | Tìm trace theo ID hoặc thêm structured module key có chủ đích. |
| Log ở child operation có span ID khác module span | Có child span đang current tại thời điểm ghi log. | Mở trace và kiểm tra span tree; đây có thể là hành vi đúng. |
| Một request có nhiều trace ID | Context propagation bị đứt hoặc có workflow mới độc lập. | Kiểm tra HTTP/message headers, executor và sampling decisions. |

### 13.1. Trình tự điều tra

~~~mermaid
flowchart TD
    A["Log không tìm được module span"] --> B{"Log có traceId?"}
    B -->|"Không"| C["Kiểm tra Micrometer Tracing,\ncurrent span và MDC pattern"]
    B -->|"Có"| D{"Backend có traceId này?"}
    D -->|"Không"| E["Kiểm tra sampling, exporter,\nretention và truy vấn"]
    D -->|"Có"| F{"Trace có module entry span?"}
    F -->|"Không"| G["Kiểm tra Modulith instrumentation,\nmodule API và execution path"]
    F -->|"Có"| H{"spanId trong log khớp span?"}
    H -->|"Có"| I["Đọc module attributes và log lân cận"]
    H -->|"Không"| J["Kiểm tra child span hiện hành,\nasync context và thời điểm log"]
~~~

Một log có thể không có trace ID vì code chạy ngoài request span, scheduler/background job không tạo observation, hoặc context bị mất qua thread. Một log có trace ID cũng có thể không tìm thấy trace trong backend vì trace bị sampling hoặc export thất bại. Kiểm tra MDC, active span, instrumentation, propagation và exporter trước khi kết luận về đường chạy nghiệp vụ.

## 14. Kiểm thử liên kết log-span

Kiểm thử cần xác minh cả hai phía: log có correlation fields và trace có module span phù hợp.

### 14.1. Kiểm thử trong môi trường local

1. Bật Micrometer Tracing với exporter/backend local.
2. Bật Spring Modulith Insight/observability để instrument module API.
3. Đặt sampling 100% cho kịch bản thử nghiệm.
4. Gọi một HTTP route đi qua API module.
5. Thu log từ console/file.
6. Xác minh log line trong module method có trace ID và span ID.
7. Tìm trace bằng trace ID.
8. Kiểm tra span ID tương ứng có module attributes đúng.
9. Thử nhánh async và xác minh context propagation.
10. Thử trường hợp lỗi để xác minh log WARN/ERROR vẫn liên kết được với trace khi trace được giữ và export thành công.

### 14.2. Kiểm tra MDC trong test

Có thể đọc MDC trong code chạy ở scope:

~~~java
String traceId = MDC.get("traceId");
String spanId = MDC.get("spanId");
~~~

Không gọi hai dòng này ngoài tracing scope rồi kết luận toàn ứng dụng không có tracing. Trong test, kích hoạt request/observation thật hoặc tạo span và đưa nó vào scope trước khi kiểm tra.

### 14.3. Phân biệt các loại test

- Test logging pattern xác minh formatter hiển thị đúng field.
- Test MDC xác minh current context có giá trị.
- Test instrumentation xác minh Spring Modulith tạo module span.
- Test exporter xác minh spans được gửi tới backend.
- Test propagation xác minh context đi qua thread hoặc service boundary.

Một test log line chứa trace ID không chứng minh Zipkin/Tempo đã nhận trace; một trace có span không chứng minh mọi log appender đã ghi correlation ID.

## 15. Bảo mật và chất lượng dữ liệu log

Log và trace thường được tập hợp ở hệ thống tập trung, có thời gian lưu dài và nhiều người có quyền truy vấn. Vì vậy, liên kết log-span phải đi cùng chính sách dữ liệu.

Không ghi nếu không có nhu cầu và quyền phù hợp:

- access token, refresh token, cookie hoặc API key;
- mật khẩu, secret hoặc credential;
- số thẻ và dữ liệu thanh toán nhạy cảm;
- email, số điện thoại, địa chỉ hoặc dữ liệu cá nhân không cần thiết;
- toàn bộ request/response body;
- dữ liệu định danh của người dùng trong metric tags.

Business ID có thể hữu ích để điều tra trong log nhưng vẫn cần phân loại dữ liệu, kiểm soát quyền và retention. Giữ timestamp chuẩn UTC, đồng bộ clock, service name rõ ràng, field name nhất quán và log level phù hợp.

## 16. Checklist triển khai

- [ ] Có Micrometer Tracing implementation phù hợp với Spring Boot.
- [ ] Có exporter/backend nếu cần mở trace trong Zipkin, Tempo hoặc công cụ khác.
- [ ] Đã bật Spring Modulith observability để tạo module entry spans.
- [ ] Đã xác minh span mang `module.identifier`, `module.name`, `module.invocation-type` và `module.method`.
- [ ] Log pattern hiển thị correlation ID hoặc structured fields tương ứng.
- [ ] Trace ID/span ID trong log đến từ MDC do tracing quản lý.
- [ ] Đã phân biệt module span attributes với MDC fields.
- [ ] Nếu cần module field trong log, đã thêm có chủ đích qua structured key-value hoặc MDC scope.
- [ ] MDC được khôi phục/xóa sau phạm vi xử lý đồng bộ.
- [ ] Async executor có context propagation.
- [ ] Reactive pipeline có cấu hình context propagation phù hợp.
- [ ] HTTP client dùng builder được Spring Boot auto-configure.
- [ ] Đã thử log-to-trace và trace-to-log trên một request thực.
- [ ] Đã hiểu sampling có thể làm trace không tồn tại trong backend dù log có ID.
- [ ] Không đưa secret/PII/payload lớn vào logs hoặc spans.
- [ ] Không dùng trace/span ID hoặc business ID làm metric tags.
- [ ] Log retention, quyền truy cập và timezone được quản lý.

## 17. Bài tập tự luyện

1. **Khái niệm:** Trace ID và span ID khác nhau như thế nào? Vì sao log cần cả hai khi muốn tìm đúng module span?
2. **MDC:** Spring Boot dùng MDC để tạo correlation ID ra sao khi Micrometer Tracing hoạt động?
3. **Cấu hình:** Viết `logging.pattern.correlation` để hiển thị application name, traceId và spanId.
4. **Module metadata:** Vì sao `module.identifier` có trong span không đồng nghĩa field đó tự xuất hiện trong mọi log line?
5. **Code:** Thêm `module.identifier=inventory` vào một log event bằng SLF4J fluent key-value logging.
6. **MDC lifecycle:** Vì sao phải khôi phục giá trị cũ trong `finally` khi tự đặt MDC trên thread pool?
7. **Async:** Một log trong `@Async` listener không có trace ID. Hãy kiểm tra property và executor decorator nào.
8. **Reactor:** Vì sao ThreadLocal MDC có thể không xuất hiện trong reactive operator? Cấu hình Spring Boot nào hỗ trợ propagation?
9. **Troubleshooting:** Log có trace ID nhưng backend không có trace. Hãy nêu các nguyên nhân khác nhau ngoài lỗi MDC.
10. **Sampling:** Vì sao không tìm thấy trace không chứng minh request chưa chạy?
11. **Structured logging:** Những lợi ích nào có được khi xuất traceId, spanId và module identifier thành JSON fields?
12. **Bảo mật:** Vì sao không nên log toàn bộ event payload hoặc token chỉ để dễ điều tra?
13. **Kiến trúc:** Một trace có module entry span của inventory nhưng không có log module field. Có cần sửa instrumentation không? Hãy cân nhắc cách truy vấn trace trước.
14. **Kiểm thử:** Thiết kế test tách biệt việc kiểm tra MDC, module instrumentation, exporter và async propagation.

## 18. Tổng kết

**Liên kết log với module span chủ yếu dựa vào trace ID và span ID do Micrometer Tracing quản lý trong MDC.** Spring Boot tự thêm correlation ID vào log khi tracing được cấu hình; mỗi log line được ghi trong một span scope có thể liên kết tới trace và span tương ứng.

Spring Modulith bổ sung metadata cho module entry spans như `module.identifier`, `module.name`, `module.invocation-type` và `module.method`. Những attributes này nằm trên span; nếu muốn truy vấn module trực tiếp từ log store, ứng dụng cần chủ động thêm module field vào structured log hoặc MDC với lifecycle được quản lý.

Context propagation giữ correlation khi xử lý chuyển qua executor, Reactor hoặc service boundary. Sampling, exporter và retention quyết định trace có xuất hiện trong backend hay không. Vì vậy, log có ID không luôn đồng nghĩa backend có trace, và trace có span không chứng minh giao dịch nghiệp vụ đã hoàn tất đúng.

Khi kết hợp log, module spans, event metrics, module graph và dữ liệu nghiệp vụ, nhóm phát triển có thể điều tra lỗi xuyên qua ranh giới module mà vẫn phân biệt rõ **bằng chứng quan sát** với **trạng thái nghiệp vụ có thẩm quyền**.

### Tài liệu tham khảo chính thức

1. [Spring Boot 4.2 — Tracing: Logging Correlation IDs, MDC và propagation](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
2. [Spring Boot 4.2 — Observability: Context Propagation qua @Async và Reactor](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
3. [Spring Boot 4.2 — Logging: Log patterns, MDC và Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html).
4. [Spring Modulith 2.2 — Production-ready Features: Module Entry Spans và Insight](https://docs.spring.io/spring-modulith/reference/production-ready.html).
5. [Micrometer Tracing — Reference Documentation](https://docs.micrometer.io/tracing/reference/).
6. [Micrometer Tracing — Span and Baggage Scopes, Context Propagation](https://docs.micrometer.io/tracing/reference/context-contracts.html).
7. [Spring Framework — ContextPropagatingTaskDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html).
