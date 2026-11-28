# Liên kết trace với log correlation id

Khi một request đi qua nhiều application module, trace cho biết request đã đi qua đâu, còn log ghi lại thông tin chi tiết mà từng đoạn code phát ra. Nếu log có **trace ID** và **span ID**, ta có thể đi từ một dòng log tới đúng trace/span tương ứng để điều tra lỗi hoặc độ trễ. Đây là **log correlation**: liên kết log với dữ liệu tracing bằng định danh của hoạt động đang được quan sát.

Với **Micrometer Tracing**, Spring Boot tự đưa `traceId` và `spanId` vào **Mapped Diagnostic Context (MDC)** khi một span đang active, rồi dùng chúng tạo **correlation ID** trong log theo mặc định. Trong ứng dụng **Spring Modulith**, cơ chế này giúp lần theo các log của module `orders`, `payments` hoặc listener `inventory` trong cùng một trace. Bài học thuộc chương **Micrometer tracing** của mô-đun **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, hướng tới kết hợp module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun lúc chạy.

> Ví dụ cấu hình dưới đây dựa trên tài liệu Spring Boot 4.2.0 và Micrometer Tracing hiện hành. Spring Boot 3.x có cùng ý tưởng log correlation nhưng dependency, thuộc tính hoặc khả năng tùy chỉnh có thể khác theo phiên bản. Hãy dùng BOM và reference docs của phiên bản dự án.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `traceId`, `spanId`, MDC và correlation ID trong log.
2. Hiểu vì sao Spring Boot có thể tự thêm correlation ID khi Micrometer Tracing được cấu hình.
3. Tùy chỉnh định dạng log correlation bằng `logging.pattern.correlation`.
4. Đọc và truy vấn log theo trace ID hoặc cặp trace ID/span ID.
5. Phân biệt trace correlation ID với business/request correlation ID do ứng dụng tự định nghĩa.
6. Theo dõi một request qua nhiều module và service bằng cách kết hợp log với trace.
7. Giữ correlation đúng qua executor bất đồng bộ và HTTP client.
8. Xử lý các trường hợp thiếu MDC, sai trace context, custom logging pattern và dữ liệu nhạy cảm.

## 2. Ba định danh cần phân biệt

### 2.1. Trace ID

**Trace ID** định danh một trace, tức một chuỗi hoạt động có liên quan về mặt nhân quả. Nhiều span trong cùng trace dùng chung trace ID.

Ví dụ một request tạo đơn hàng:

~~~text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
  ├── HTTP POST /orders
  ├── orders.placeOrder
  ├── payments.charge
  └── HTTP POST /payment-gateway
~~~

Nếu cần tìm mọi log liên quan đến request đó, **trace ID là khóa tìm kiếm phù hợp nhất**.

### 2.2. Span ID

**Span ID** định danh một operation cụ thể trong trace. Mỗi span có span ID riêng; span con có span ID khác span cha nhưng giữ cùng trace ID.

~~~text
Trace ID = 4bf92f3577b34da6a3ce929d0e0e4736

HTTP POST /orders
  spanId = 00f067aa0ba902b7

orders.placeOrder
  spanId = 4c3f7a1b2d8e9f10

payments.charge
  spanId = 8a7b6c5d4e3f2019
~~~

Log phát ra khi span `orders.placeOrder` đang active có thể mang span ID của operation đó; khi code đi vào span `payments.charge`, MDC được cập nhật theo span hiện tại. Vì thế, **trace ID giữ nguyên trong trace còn span ID có thể thay đổi theo đoạn code**.

### 2.3. Correlation ID trong log

Trong Spring Boot khi Micrometer Tracing hoạt động, correlation ID mặc định được tạo từ hai giá trị MDC `traceId` và `spanId`, có định dạng:

~~~text
[traceId-spanId]
~~~

Ví dụ:

~~~text
[4bf92f3577b34da6a3ce929d0e0e4736-4c3f7a1b2d8e9f10]
~~~

Chuỗi này là **cách trình bày định danh để liên kết log**, không phải một trace ID mới do ứng dụng tự sinh. Nó kết hợp:

- `traceId`: xác định trace.
- `spanId`: xác định span đang active khi log được phát ra.

Độ dài phổ biến theo W3C Trace Context là 32 ký tự hex cho trace ID và 16 ký tự hex cho span ID. Spring Boot định dạng correlation ID mặc định theo các độ dài này.

### 2.4. Bảng so sánh

| Giá trị | Phạm vi | Dùng để làm gì? |
| --- | --- | --- |
| `traceId` | Toàn bộ trace | Tìm mọi span và log thuộc cùng một request/workflow |
| `spanId` | Một span | Xác định operation đang phát log |
| Correlation ID mặc định | Một span trong một trace | Liên kết dòng log với đúng span |
| Business correlation ID | Theo quy tắc nghiệp vụ | Liên hệ nhiều request hoặc nhiều trace thuộc cùng một nghiệp vụ |

**Lưu ý:** Một đơn hàng có thể tạo nhiều trace khác nhau, ví dụ request đặt hàng, job gửi hóa đơn và tác vụ retry ngày hôm sau. Nếu muốn liên hệ tất cả hoạt động đó theo `orderId`, đó là bài toán business correlation; không dùng một trace ID như thể nó đại diện toàn bộ vòng đời nghiệp vụ.

## 3. MDC là gì và Micrometer Tracing đưa ID vào đó thế nào?

**MDC (Mapped Diagnostic Context)** là vùng dữ liệu theo thread do logging framework hỗ trợ. Với Logback, MDC cho phép code và logging pattern đọc các cặp key/value gắn với luồng xử lý hiện tại.

Khi Micrometer Tracing tạo và đặt span hiện hành vào scope, tích hợp tracing có thể đưa:

~~~text
MDC:
  traceId = 4bf92f3577b34da6a3ce929d0e0e4736
  spanId  = 4c3f7a1b2d8e9f10
~~~

vào MDC. Logging pattern sử dụng các giá trị đó để thêm correlation ID vào mỗi dòng log.

Mối liên hệ khái niệm:

~~~mermaid
flowchart LR
    A["HTTP request / operation"] --> B["Micrometer Tracing<br/>current span"]
    B --> C["MDC<br/>traceId + spanId"]
    C --> D["Logging pattern"]
    D --> E["Log line có correlation ID"]
    B --> F["Trace exporter"]
    F --> G["Trace backend"]
    E -. "tra cứu bằng traceId/spanId" .-> G
~~~

Sơ đồ có hai đường xuất dữ liệu độc lập:

- Log appender ghi dòng log vào console/file/log collector.
- Tracing exporter gửi spans tới backend như Zipkin, Tempo hoặc Jaeger.

Có cùng trace ID trong log và span **không có nghĩa log tự động được lưu trong trace backend**. Muốn xem log ngay trên trace UI cần tích hợp log storage hoặc cấu hình liên kết tương ứng. Nếu chưa tích hợp, ta dùng ID để truy vấn hai hệ thống riêng.

### 3.1. Spring Boot thêm correlation ID mặc định

Theo tài liệu Spring Boot, khi dùng Micrometer Tracing, Spring Boot **tự thêm correlation ID vào log theo mặc định**. Cơ chế mặc định sử dụng hai MDC keys:

- `traceId`
- `spanId`

Ví dụ log minh họa:

~~~text
2026-11-27T09:10:12.120+07:00 INFO [shop-modulith,4bf92f3577b34da6a3ce929d0e0e4736-4c3f7a1b2d8e9f10] 18240 --- [http-nio-8080-exec-1] c.e.shop.orders.OrderService : Creating order
~~~

Cách hiển thị đầy đủ phụ thuộc logging system, pattern, ứng dụng và phiên bản Spring Boot. Điểm cần tìm là cặp trace/span ID trong log record.

Nếu dự án đã có file `logback-spring.xml`, `logback.xml` hoặc cấu hình logging tùy chỉnh, pattern tự viết có thể thay thế pattern mặc định. Khi đó phải đưa MDC placeholders vào pattern của appender mà ứng dụng thực sự sử dụng.

## 4. Bật Micrometer Tracing để có log correlation

Log correlation cần **tracing instrumentation hoạt động**. Chỉ cấu hình `%X{traceId}` trong logging pattern không tự tạo trace ID.

### 4.1. Dependency minh họa với Spring Boot 4.2 và OpenTelemetry

Ví dụ Gradle:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Micrometer Tracing với OpenTelemetry và OTLP.
    runtimeOnly 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Dự án cần quản lý dependency versions bằng Spring Boot BOM hoặc dependency management tương thích. Spring Boot cũng hỗ trợ Brave với Zipkin qua starter tương ứng; chọn **một tracer implementation phù hợp** và cấu hình exporter/backend của nó.

Với Spring Boot 3.x, dependency có thể dùng `micrometer-tracing-bridge-otel` hoặc `micrometer-tracing-bridge-brave` cùng exporter tương ứng. Không trộn ví dụ dependency giữa các major versions nếu chưa kiểm tra compatibility.

### 4.2. Cấu hình tracing và sampling

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0

  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
~~~

Giải thích:

- `spring.application.name` xác định tên service để dễ tìm trace/log.
- `management.tracing.sampling.probability: 1.0` yêu cầu lấy mẫu 100% trong lab.
- `management.opentelemetry.tracing.export.otlp.endpoint` là địa chỉ nhận traces qua OTLP/HTTP trong ví dụ.
- Cần có OpenTelemetry Collector hoặc backend nhận dữ liệu ở endpoint đó.

Spring Boot mặc định lấy mẫu khoảng 10% trace để giảm tải backend. Trong production, chọn sampling phù hợp lưu lượng và chi phí. **Sampling ảnh hưởng trace được gửi tới backend; nó không thay thế logging configuration.** Log correlation có thể xuất hiện trong ứng dụng trong khi trace tương ứng không được lưu ở backend do sampling hoặc lỗi export.

### 4.3. Kiểm tra log ngay sau khi bật

Gọi endpoint có instrumentation, ví dụ `GET /orders/123`, rồi xem log console. Nếu tracing và logging pattern mặc định hoạt động, log trong operation sẽ có cặp ID:

~~~text
[traceId-spanId]
~~~

Tiếp theo, tìm trace ID trên backend tracing. Nếu trace có mặt, mở span có span ID tương ứng để xem duration, parent/child và attributes.

**Không dùng một log line ngoài request context làm tiêu chí bắt buộc phải có trace ID.** Log khi startup, scheduler không được instrument hoặc code chạy ngoài active span có thể không có correlation ID.

## 5. Tùy chỉnh định dạng correlation ID

Spring Boot cho phép cấu hình `logging.pattern.correlation` để thay đổi format.

Ví dụ muốn đưa tên application vào trước trace/span IDs:

~~~yaml
logging:
  pattern:
    correlation: "[shop-modulith,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

Kết quả minh họa:

~~~text
[shop-modulith,4bf92f3577b34da6a3ce929d0e0e4736,4c3f7a1b2d8e9f10]
~~~

Một số chi tiết:

- `%X{traceId:-}` đọc MDC key `traceId`, dùng giá trị mặc định rỗng nếu không có.
- `%X{spanId:-}` đọc MDC key `spanId`.
- Khoảng trắng ở cuối pattern giúp tách correlation prefix khỏi tên logger đứng sau.
- `include-application-name: false` tránh in tên ứng dụng hai lần nếu pattern đã thêm tên app.

### 5.1. Đổi tên MDC keys

Spring Boot cho phép cấu hình key names trong các phiên bản hỗ trợ:

~~~yaml
management:
  tracing:
    mdc:
      trace-id-key: trace_id
      span-id-key: span_id
~~~

Khi đó, nếu tự định nghĩa correlation pattern, phải tham chiếu đúng tên mới:

~~~yaml
logging:
  pattern:
    correlation: "[%X{trace_id:-},%X{span_id:-}] "
~~~

Nếu custom pattern vẫn đọc `traceId` và `spanId`, log có thể trống dù tracing vẫn hoạt động và MDC đang dùng key khác.

**Lưu ý với Brave:** Theo tài liệu Spring Boot hiện hành, MDC key customization của Brave gắn với cấu hình baggage. Nếu tắt `management.tracing.baggage.enabled`, Brave có thể ngừng ghi trace/span IDs vào MDC, làm log correlation mất theo. Khi dùng Brave, kiểm tra riêng thuộc tính này và behavior của phiên bản.

### 5.2. Khi dùng logging configuration riêng

Nếu ứng dụng khai báo appender và encoder/layout trong file Logback riêng, hãy xác minh pattern cuối cùng có in correlation prefix. Chẳng hạn, một pattern Logback có thể sử dụng:

~~~xml
<pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%X{traceId:-}-%X{spanId:-}] [%thread] %logger{36} - %msg%n</pattern>
~~~

Đây là ví dụ layout Logback. Nếu dùng Log4j2 hoặc structured JSON encoder, hãy cấu hình cách đọc MDC theo cú pháp tương ứng. Không giả định `logging.pattern.correlation` tự sửa mọi appender đã được định nghĩa hoàn toàn thủ công.

## 6. Tìm log theo trace ID và span ID

Khi có một trace ID từ dashboard hoặc từ log lỗi, quy trình điều tra:

1. Sao chép **trace ID** đầy đủ từ log.
2. Tìm trace đó trong Zipkin/Tempo/Jaeger hoặc backend tracing đang dùng.
3. Xác định span ID của log để biết log được phát trong operation nào.
4. Xem parent span, child span, duration, status và attributes.
5. Dùng trace ID tìm tất cả log thuộc trace; dùng cặp trace/span ID để khoanh vùng một span.

### 6.1. Vì sao tìm trace ID thường hữu ích hơn full correlation ID?

Giả sử một request đi qua ba span:

| Span | Trace ID | Span ID |
| --- | --- | --- |
| HTTP server | `abc...` | `111...` |
| `orders.placeOrder` | `abc...` | `222...` |
| `payments.charge` | `abc...` | `333...` |

Nếu tìm full correlation ID `[abc...-222...]`, ta chủ yếu tìm log phát ra khi span `orders.placeOrder` đang active. Nếu tìm `traceId=abc...`, ta có thể tìm log từ cả ba đoạn xử lý.

**Quy tắc sử dụng:**

- Điều tra toàn bộ request/workflow trace: tìm `traceId`.
- Điều tra log trong một operation cụ thể: tìm cả `traceId` và `spanId`.
- Điều tra một đơn hàng qua nhiều trace: dùng business correlation key có kiểm soát, chẳng hạn `orderRef` trong log nghiệp vụ hoặc kho dữ liệu.

### 6.2. Ví dụ truy vấn log

Nếu log collector parse correlation fields thành structured fields, truy vấn khái niệm có thể là:

~~~text
traceId = "abc..."
~~~

Hoặc nếu chỉ có chuỗi text:

~~~text
"abc..."
~~~

Tên field và cú pháp query tùy Elasticsearch, Loki, OpenSearch hoặc hệ thống log đang dùng. Nên parse `traceId` và `spanId` thành **field riêng** thay vì chỉ lưu một chuỗi correlation khó truy vấn.

## 7. Liên kết log và trace qua nhiều application module

Trong Spring Modulith, module entry span có thể mang metadata:

| Span attribute | Ý nghĩa |
| --- | --- |
| `module.identifier` | Technical ID của module, ví dụ `orders` |
| `module.name` | Tên hiển thị |
| `module.invocation-type` | `bean` hoặc `event listener` |
| `module.method` | Phương thức entry point |

Giả sử một request thực hiện:

~~~mermaid
sequenceDiagram
    participant C as HTTP client
    participant W as web
    participant O as orders
    participant P as payments
    C->>W: POST /orders
    W->>O: placeOrder()
    Note over O: module.identifier=orders
    O->>P: charge()
    Note over P: module.identifier=payments
    P-->>O: payment result
    O-->>W: order result
    W-->>C: HTTP response
~~~

Trong log:

~~~text
[trace=abc,span=111] web: Received order request
[trace=abc,span=222] orders: Creating order
[trace=abc,span=333] payments: Calling payment provider
[trace=abc,span=222] orders: Payment completed
~~~

Các giá trị rút gọn chỉ minh họa. `traceId` giữ nguyên trong các span cùng trace; `spanId` phản ánh span đang active khi từng log được phát ra. Trên tracing backend, dùng `module.identifier` để xác định module; trên log backend, dùng trace ID để tập hợp các dòng log liên quan.

**Module metadata không tự động trở thành MDC field.** Spring Modulith gắn metadata vào module observation/span. Nếu muốn mỗi dòng log có thêm `module=orders`, phải đưa thông tin đó vào logging context/pattern hoặc structured log bằng cơ chế riêng; correlation ID mặc định chỉ gồm trace ID và span ID.

### 7.1. Khi log phát ra ngoài module span

Một module có thể gọi nhiều helper method nội bộ. Nếu các helper không tạo span riêng, log của chúng có thể mang cùng span ID của module entry span. Đây là bình thường: log được liên kết với **span hiện hành**, không phải mỗi method có một span.

Nếu cần phân biệt operation nội bộ, có thể tạo observation/span tùy chỉnh có ý nghĩa. Không tạo span cho mọi helper chỉ để log có nhiều span ID hơn.

## 8. Correlation qua HTTP giữa các service

Khi module gọi một service khác qua HTTP, trace context cần được truyền qua request headers theo propagator đã cấu hình (thường là W3C Trace Context hoặc B3). Service nhận sẽ tiếp tục trace nếu instrumentation/propagator tương thích.

Spring Boot khuyến nghị dùng các client builder được auto-configure để tự động truyền trace:

- `RestClient.Builder`
- `WebClient.Builder`
- `RestTemplateBuilder` ở những phiên bản hỗ trợ

Ví dụ với `RestClient`:

~~~java
package com.example.shop.payments;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class PaymentGatewayClient {

    private final RestClient client;

    PaymentGatewayClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://payment-gateway.example")
                .build();
    }

    void charge(Object request) {
        client.post()
                .uri("/charges")
                .body(request)
                .retrieve()
                .toBodilessEntity();
    }
}
~~~

Đoạn code minh họa việc dùng builder do Spring Boot cung cấp. Trong thực tế cần cấu hình base URL, timeout, auth, error handling và request/response DTO phù hợp.

**Cảnh báo:** Nếu tự tạo `RestClient`, `RestTemplate` hoặc `WebClient` mà không dùng builder auto-configured, automatic trace propagation có thể không hoạt động. Khi đó service nhận có thể tạo trace mới thay vì tiếp tục trace hiện tại.

### 8.1. Trace propagation không phải truyền nguyên log context

Khi gửi HTTP request, tracing instrumentation truyền trace context theo headers. Nó không gửi nguyên MDC map của caller sang service nhận. Service nhận dựng current span và MDC cục bộ từ context được extract.

Vì vậy:

- Trace ID có thể được giữ xuyên service.
- Span ID của service nhận là ID của span mới.
- Các MDC fields tùy chỉnh như `region`, `operator` hoặc `businessRequestId` không tự truyền chỉ vì có trace ID.
- Nếu cần mang một giá trị xuyên service, hãy cân nhắc baggage hoặc header nghiệp vụ được xác thực/kiểm soát, theo chính sách dữ liệu.

## 9. Correlation ID nghiệp vụ và trace correlation ID

Một số hệ thống có header riêng như `X-Request-ID`, `X-Correlation-ID` hoặc `X-Order-Reference`. Những giá trị này **không tự động giống** trace ID của Micrometer.

| Loại | Nguồn | Vòng đời |
| --- | --- | --- |
| Trace ID | Tracing instrumentation hoặc trace context từ upstream | Một trace |
| Span ID | Tracing instrumentation | Một span |
| Default log correlation ID | Spring Boot kết hợp traceId + spanId | Một span trong một trace |
| Business/request correlation ID | API gateway, ứng dụng hoặc domain workflow | Có thể đi qua nhiều trace và nhiều lần retry |

Ví dụ, `orderRef` có thể được giữ từ lúc khách đặt hàng đến lúc hoàn tiền vài ngày sau, qua nhiều trace độc lập. Trace ID thường không đại diện toàn bộ vòng đời đó.

Nếu cần log thêm một request ID do hệ thống cấp:

1. Xác định nguồn tin cậy và quy tắc validation của header.
2. Đặt nó vào một MDC key riêng, ví dụ `requestId`.
3. Đưa key đó vào structured log/pattern.
4. Dọn MDC sau request/task.
5. Không ghi đè MDC keys `traceId` hoặc `spanId` do tracer quản lý.

Ví dụ thao tác MDC thủ công cần có cleanup:

~~~java
import org.slf4j.MDC;

String previous = MDC.get("requestId");
try {
    MDC.put("requestId", validatedRequestId);
    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
~~~

Đây là ví dụ cho **business/request ID riêng**. Trong Spring MVC, nên đặt logic ở filter/interceptor có vòng đời request rõ ràng và xử lý async dispatch phù hợp. Không tự gán `traceId`/`spanId` bằng `MDC.put(...)`, vì chúng phải đồng bộ với current span của tracer.

## 10. Context propagation và log correlation trong async

MDC gắn với thread. Khi một task được submit sang executor, MDC và current span có thể không tự đi theo. Nếu không truyền context:

- Log trong worker có thể không có trace ID/span ID.
- Span được tạo ở worker có thể tách khỏi trace mong muốn.
- Một `ThreadLocal` tùy chỉnh có thể rò giá trị từ task trước nếu không được reset đúng cách.

Trong Spring Boot, context propagation có thể được cấu hình cho task execution. Ví dụ ở phiên bản hỗ trợ:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Với executor tự tạo, có thể gắn `ContextPropagatingTaskDecorator`:

~~~java
@Bean("applicationTaskExecutor")
ThreadPoolTaskExecutor applicationTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(12);
    executor.setQueueCapacity(200);
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    return executor;
}
~~~

Decorator dùng Micrometer Context Propagation để capture/restore các context đã đăng ký. Nó phải được gắn vào **executor thực sự chạy task**; một executor khác hoặc một message broker cần propagation mechanism riêng.

### 10.1. Spring Modulith event listener

`@ApplicationModuleListener` thường xử lý event bất đồng bộ và theo transaction. Khi listener chạy trong module `inventory`, Spring Modulith có thể tạo module entry span với `module.invocation-type=event listener`. Để log listener liên kết với trace của publisher, phải kiểm tra:

1. Listener đang sử dụng executor nào?
2. Executor đó có context propagation phù hợp không?
3. Trace context có được khôi phục sau khi event được dispatch không?
4. Trace ID và span ID trong log listener có tương ứng span trên backend không?

Không mặc định mọi event listener luôn chung trace với request publish. Transaction commit, async executor và cơ chế dispatch có thể tạo ranh giới trace khác nhau. Ngay cả khi listener ở trace khác, log của nó vẫn có thể có correlation ID riêng nếu một trace mới được tạo.

### 10.2. Log correlation trong async không tự chứng minh nghiệp vụ thành công

Một listener log có `[traceId-spanId]` chỉ cho thấy log được gắn với một span hiện hành. Nó không chứng minh Event Publication Registry đã đánh dấu publication `COMPLETED`. Để xác định trạng thái event, cần kết hợp registry, logs, metrics và outcome nghiệp vụ.

## 11. Baggage và MDC: khi nào nên dùng?

**Baggage** là các giá trị key/value được truyền cùng trace qua các service khi cấu hình propagator hỗ trợ. Baggage có thể dùng cho thông tin cần đi theo trace, ví dụ một nhóm phân loại hữu hạn hoặc locale đã được cho phép.

Spring Boot cho phép cấu hình baggage fields đưa vào MDC:

~~~yaml
management:
  tracing:
    baggage:
      correlation:
        fields:
          - region
          - client-tier
      remote-fields:
        - region
        - client-tier
~~~

`correlation.fields` yêu cầu các baggage fields tương ứng được đưa vào MDC; `remote-fields` chỉ định baggage được truyền qua biên service theo cấu hình hỗ trợ. Cần đối chiếu propagator: W3C hỗ trợ baggage propagation; B3 có các khác biệt và có thể cần cấu hình remote fields rõ ràng.

**Không truyền tùy tiện** dữ liệu nhạy cảm hoặc dữ liệu không tin cậy qua baggage. Giá trị có thể đi qua nhiều service, xuất hiện trong logs hoặc trace attributes tùy cấu hình. Tránh email, token, số tài khoản, dữ liệu cá nhân và payload lớn. Baggage cũng không phải nơi chứa dữ liệu nghiệp vụ cần lưu trữ bền vững.

## 12. Quy trình điều tra từ log tới trace

Khi người vận hành nhận được một log báo lỗi, hãy làm theo thứ tự:

1. **Tách định danh:** đọc `traceId`, `spanId` và business/request ID nếu có.
2. **Tìm toàn trace:** dùng `traceId` để mở trace trong backend.
3. **Định vị operation:** tìm span có `spanId` tương ứng với log.
4. **Đọc module metadata:** xem `module.identifier`, `module.method`, `module.invocation-type`.
5. **Đọc lỗi và thời gian:** kiểm tra span status, exception events, duration và parent/child.
6. **Tìm các log liên quan:** truy vấn toàn bộ log cùng trace ID để xem trước/sau thời điểm lỗi.
7. **Đối chiếu module graph:** xác nhận dependency module nếu nghi ngờ đường gọi không đúng kiến trúc.
8. **Kiểm tra async/remote:** nếu span bị tách, xác minh context propagation qua executor hoặc HTTP headers.

Ví dụ:

~~~text
Log:
[4bf92f3577b34da6a3ce929d0e0e4736-8a7b6c5d4e3f2019]
ERROR PaymentService : Gateway timeout
~~~

Từ đây:

- Tìm `traceId=4bf92f...` trong tracing backend.
- Mở span `spanId=8a7b...`.
- Xem span có `module.identifier=payments` không.
- Kiểm tra child HTTP client span và exception.
- Tìm các log cùng trace ID để xác định module `orders` đã xử lý lỗi thế nào.

Correlation ID rút ngắn thời gian điều tra, nhưng **không thay thế nội dung log, span attributes hoặc trạng thái nghiệp vụ**.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Log không có trace/span ID | Micrometer Tracing chưa được cấu hình hoặc không có current span | Kiểm tra tracer dependency, sampling, instrumentation và request path |
| Có trace trên backend nhưng log không có correlation ID | Custom logging pattern bỏ qua MDC hoặc MDC key đã đổi | Kiểm tra `logging.pattern.correlation`, appender và MDC key names |
| Log có trace ID nhưng backend không tìm thấy trace | Trace bị sampling bỏ hoặc exporter/backend lỗi | Kiểm tra sampling, exporter, collector và thời điểm truy vấn |
| Chỉ log của module đầu tiên có ID | Context mất khi chuyển thread hoặc executor | Kiểm tra context propagation và executor thực tế |
| Service downstream tạo trace mới | HTTP client không truyền trace headers | Dùng auto-configured client builder và kiểm tra headers/propagator |
| Tìm full correlation ID không thấy log module khác | Span ID khác nhau giữa các operation | Tìm bằng trace ID thay vì cặp trace/span |
| Correlation ID bị lặp tên application | Pattern đã chứa app name nhưng `include-application-name` vẫn bật | Đặt `logging.include-application-name=false` khi cần |
| Đổi MDC key nhưng correlation prefix trống | Custom pattern vẫn đọc key cũ | Cập nhật `%X{trace_id:-}` và `%X{span_id:-}` tương ứng |
| Log listener có trace mới | Listener xử lý async trong trace riêng hoặc context không được nối | Kiểm tra dispatch, transaction, executor và trace propagation |
| Log chứa giá trị request cũ | MDC custom không được remove/restore | Dùng `try/finally`, filter/interceptor có cleanup hoặc accessor đúng |
| Có module span nhưng log không có module ID | Module metadata nằm trên span, không mặc định nằm trong MDC | Truy vấn span attribute hoặc thêm structured logging context riêng |

### 13.1. Sampling và log correlation là hai vấn đề khác nhau

Sampling quyết định trace nào được lưu/export. Logging pattern quyết định log có in MDC values hay không. Vì vậy có thể gặp:

- Log có trace/span ID nhưng backend không lưu trace tương ứng.
- Trace được lưu nhưng custom appender không in correlation ID.
- Log ngoài span có MDC trống dù tracing đã bật.

Khi điều tra, kiểm tra cả **tracer/current context**, **logging pattern**, **sampling** và **export pipeline**.

### 13.2. Không dùng log correlation như metric label

`traceId`, `spanId` và request IDs có cardinality rất cao. Chúng phù hợp để tìm log/trace cụ thể, không phù hợp làm labels của Prometheus metrics. Nếu muốn đếm lỗi theo module, hãy dùng metric tags có tập giá trị nhỏ như `module=payments`, `outcome=timeout`, còn ID cụ thể để trong log/trace có kiểm soát.

## 14. Bài thực hành

### Bài 1 — Đọc correlation prefix

Với log:

~~~text
[shop,4bf92f3577b34da6a3ce929d0e0e4736,8a7b6c5d4e3f2019] ERROR PaymentService : Gateway timeout
~~~

Hãy xác định application name, trace ID và span ID. Giải thích vì sao tìm trace ID có thể cho thấy cả log của `orders` và `payments`, trong khi tìm cả hai ID khoanh vùng một span.

### Bài 2 — Tùy chỉnh logging pattern

Thêm `logging.pattern.correlation` để tạo format:

~~~text
[application,traceId,spanId]
~~~

Tắt application name mặc định nếu đã đưa nó vào pattern. Chạy request và xác minh log thực tế. Sau đó đổi tên MDC keys và cập nhật pattern tương ứng.

### Bài 3 — Theo dõi qua hai module

Tạo luồng đồng bộ `orders → payments`. Phát log trong hai module và kiểm tra:

- Cả hai log có cùng trace ID không?
- Span ID có thể khác nhau không?
- Span trên backend có `module.identifier` tương ứng không?
- Log correlation ID có liên kết đúng từng span không?

### Bài 4 — Theo dõi qua HTTP

Dùng `RestClient.Builder` do Spring Boot auto-configure để gọi một service khác có tracing. Tìm log ở cả hai service theo trace ID và đối chiếu span ID tại mỗi service. Thử thay bằng client tự tạo để quan sát khác biệt nếu propagation không được cài đặt.

### Bài 5 — Theo dõi event listener bất đồng bộ

Dùng `@ApplicationModuleListener` để module `inventory` nhận `OrderPlaced`. Cấu hình context propagation cho executor thực tế. Kiểm tra log listener có trace ID mong đợi không, rồi đối chiếu module entry span và Event Publication Registry.

### Bài 6 — Phân biệt trace ID với business correlation ID

Giả sử một `orderRef` xuất hiện trong request tạo đơn, tác vụ gửi hóa đơn và job hoàn tiền sau hai ngày. Giải thích vì sao các hoạt động đó có thể thuộc các trace ID khác nhau; thiết kế cách log `orderRef` như business correlation field mà không ghi nó thành metric label.

## 15. Câu hỏi ôn tập

1. `traceId` và `spanId` khác nhau như thế nào?
2. Correlation ID mặc định của Spring Boot được tạo từ những MDC values nào?
3. Vì sao correlation ID không phải một trace ID mới?
4. Khi muốn tìm tất cả log của một request, nên tìm trace ID hay full correlation ID?
5. `MDC` là gì và nó liên quan thế nào đến current span?
6. Vì sao custom logging pattern có thể làm mất correlation prefix?
7. `logging.pattern.correlation` có vai trò gì?
8. Nếu đổi MDC key names, cần cập nhật những cấu hình nào?
9. Vì sao log có trace ID nhưng backend không có trace tương ứng?
10. Tại sao HTTP client nên dùng auto-configured builder để propagate trace?
11. Vì sao module metadata trên span không tự động xuất hiện trong MDC?
12. `ContextPropagatingTaskDecorator` hỗ trợ điều gì đối với async logging?
13. Business correlation ID khác trace ID ở vòng đời nào?
14. Vì sao không dùng trace ID làm metric label?
15. Baggage có thể xuất hiện trong MDC và được truyền qua service như thế nào?

## 16. Ghi nhớ

**Log correlation liên kết một dòng log với span đang active bằng `traceId` và `spanId`.** Spring Boot khi dùng Micrometer Tracing đưa hai giá trị này vào MDC và tạo correlation prefix theo mặc định. Tìm bằng **trace ID** để xem toàn bộ log của trace; dùng cả **span ID** để xác định operation cụ thể.

Trong Spring Modulith, module entry span bổ sung metadata như `module.identifier`, `module.method` và `module.invocation-type`. Kết hợp metadata đó với log correlation giúp tìm nhanh module và đoạn code liên quan đến lỗi. Khi đi qua HTTP hoặc executor bất đồng bộ, cần context propagation phù hợp; log correlation không tự truyền qua mọi thread/service.

Phân biệt rõ **trace correlation ID**, **business/request correlation ID** và **metric labels**. Trace/request IDs phù hợp để truy vấn logs/traces; metrics nên dùng nhãn low-cardinality. Đừng tự ghi đè `traceId`/`spanId` trong MDC, và luôn dọn context tùy chỉnh sau request/task.

### Tài liệu tham khảo

- [Spring Boot 4.2 — Tracing: Logging Correlation IDs, MDC keys và logging pattern](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot — Task Execution and Scheduling: context propagation](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html).
- [Micrometer Tracing — Reference: trace/span context và propagation](https://docs.micrometer.io/tracing/reference/).
- [Micrometer Tracing — Span and Baggage Scopes](https://docs.micrometer.io/tracing/reference/context-contracts.html).
- [Micrometer Context Propagation — Reference](https://docs.micrometer.io/context-propagation/reference/).
- [Spring Modulith — Production-ready Features: Observing Application Modules](https://docs.spring.io/spring-modulith/reference/production-ready.html).
