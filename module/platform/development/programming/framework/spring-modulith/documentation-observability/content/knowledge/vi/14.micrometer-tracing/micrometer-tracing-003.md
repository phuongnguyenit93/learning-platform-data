# OpenTelemetry và OTLP
> **Chương:** Micrometer tracing
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.
> **Trọng tâm:** Kết nối Micrometer Tracing và Spring Modulith với OpenTelemetry, xuất trace bằng OTLP tới OpenTelemetry Collector hoặc backend tương thích, rồi xác minh trace end-to-end.

## 1. Từ module graph đến trace runtime

Giả sử ứng dụng thương mại điện tử có các application module `order`, `inventory`, `payment` và `notification`. Khi khách hàng hoàn tất đơn hàng, request có thể đi qua nhiều module và phát domain event để listener tiếp tục xử lý. Nhóm vận hành muốn xem hành trình đó trong một trace:

~~~text
POST /orders/42/complete
└── order: OrderManagement.complete(...)
    ├── inventory: InventoryManagement.reserve(...)
    ├── payment: PaymentManagement.capture(...)
    └── OrderCompleted event
        └── notification: OrderCompletedListener.on(...)
~~~

Module graph và tài liệu do Spring Modulith `Documenter` sinh ra cho biết **cấu trúc và quan hệ phụ thuộc**. Chúng không ghi lại thời gian thực thi của một request. Spring Modulith observability có thể instrument lời gọi vào API module và event listener phù hợp, tạo Micrometer Observation/span. Những span đó cần một tracing implementation và exporter để được gửi tới nơi lưu trữ, truy vấn và hiển thị.

~~~mermaid
flowchart LR
    App["Spring Boot + Spring Modulith"]
    Micrometer["Micrometer Observation / Tracing"]
    Bridge["OpenTelemetry bridge / SDK"]
    Exporter["OTLP exporter"]
    Collector["OpenTelemetry Collector"]
    Backend["Tempo / Jaeger / backend OTLP"]
    App --> Micrometer --> Bridge --> Exporter
    Exporter -->|"OTLP HTTP hoặc gRPC"| Collector
    Collector --> Backend
~~~

Ba khái niệm chính:
- **OpenTelemetry (OTel):** hệ sinh thái API, SDK, semantic conventions và mô hình dữ liệu observability.
- **Micrometer Observation/Tracing:** abstraction mà Spring Boot và Spring Modulith dùng để instrument ứng dụng.
- **OTLP (OpenTelemetry Protocol):** giao thức truyền traces, metrics và logs giữa ứng dụng, Collector và backend.

Spring Boot có thể kết nối Micrometer Tracing với OpenTelemetry, sau đó xuất trace qua OTLP. **Chỉ cài Insight starter của Spring Modulith chưa đủ để có trace trong giao diện Grafana/Tempo hoặc Jaeger**; còn cần tracer, exporter, Collector hoặc backend tiếp nhận và cấu hình tương ứng.

### Mục tiêu học tập

Sau bài này, người học có thể:
1. Phân biệt OpenTelemetry, Micrometer Tracing và OTLP.
2. Giải thích vai trò của bridge, exporter, Collector, receiver, processor và backend.
3. Chọn dependency đúng cho Spring Boot 4.x hoặc Spring Boot 3.5.
4. Cấu hình OTLP/HTTP hoặc OTLP/gRPC.
5. Nhận diện resource attributes, span attributes, trace ID và service identity.
6. Quan sát module-entry spans và event-listener spans của Spring Modulith.
7. Giữ trace context qua HTTP và xử lý bất đồng bộ.
8. Kiểm tra trace end-to-end, sampling và lỗi export.

## 2. Các thành phần trong đường đi của trace

| Thành phần | Vai trò |
|---|---|
| Spring Modulith observability | Instrument tương tác giữa application modules |
| Micrometer Observation | Mô tả operation cần quan sát |
| Micrometer Tracing | API tạo và quản lý trace/span |
| OpenTelemetry bridge/SDK | Kết nối Micrometer Tracing với OTel |
| OTLP exporter | Gửi telemetry theo giao thức OTLP |
| OpenTelemetry Collector | Nhận, xử lý và chuyển tiếp telemetry |
| Trace backend | Lưu, truy vấn và hiển thị traces |

Collector là thành phần tùy chọn. Ứng dụng có thể gửi OTLP trực tiếp tới backend có OTLP receiver. Trong hệ thống nhiều service, Collector thường giúp tập trung xử lý, batch, routing, xác thực và chuyển tiếp dữ liệu.

### 2.1. Trace, span và resource

- **Trace:** hành trình của một request hoặc operation xuyên qua các thành phần.
- **Span:** một đoạn công việc có thời gian, trạng thái, attributes và quan hệ cha-con hoặc link.
- **Trace ID:** định danh toàn hành trình.
- **Span ID:** định danh một span.
- **Resource:** mô tả thực thể phát telemetry, ví dụ service name, version và môi trường.
- **Span attributes:** mô tả operation, ví dụ module identifier, method hoặc HTTP route.
- **Baggage:** dữ liệu context có thể truyền qua process theo propagation đã cấu hình.

Một request có thể có nhiều spans, nhưng mỗi span nên có phạm vi và ý nghĩa rõ ràng. Span trùng lặp làm trace khó đọc và tăng chi phí lưu trữ.

## 3. OTLP và các giao thức truyền telemetry

OTLP là giao thức truyền dữ liệu telemetry. Hai transport phổ biến:

| Transport | Cổng mặc định thường dùng | Địa chỉ traces |
|---|---:|---|
| OTLP/gRPC | 4317 | Kết nối gRPC tới host/port receiver |
| OTLP/HTTP | 4318 | HTTP POST tới `/v1/traces` |

Với OTLP/HTTP, các path chuẩn gồm:

| Signal | Path |
|---|---|
| Traces | `/v1/traces` |
| Metrics | `/v1/metrics` |
| Logs | `/v1/logs` |

Cổng 4317 và 4318 là mặc định phổ biến, không bắt buộc. Collector hoặc backend có thể được cấu hình cổng khác. Ứng dụng phải khớp transport, host, port và path với receiver thực tế.

### 3.1. Collector pipeline

~~~mermaid
flowchart LR
    Source["Spring Boot app"]
    Receiver["OTLP receiver"]
    Processor["Batch / memory limiter"]
    Exporter["Exporter"]
    Store["Trace backend"]
    Source --> Receiver --> Processor --> Exporter --> Store
~~~

- **Receiver:** lắng nghe và nhận telemetry.
- **Processor:** gom batch, giới hạn bộ nhớ hoặc chuẩn hóa thuộc tính.
- **Exporter:** gửi dữ liệu tới backend.
- **Pipeline:** nối receiver, processor và exporter cho từng signal như traces, metrics hoặc logs.

Collector chỉ kích hoạt component khi chúng được tham chiếu trong `service.pipelines`. Khai báo receiver mà không đưa nó vào pipeline traces không có nghĩa Collector đã tiếp nhận traces.

### 3.2. OTLP export khác trace propagation

OTLP **vận chuyển trace đã được tạo ra** tới Collector/backend. Propagation **truyền trace context giữa các process** để dịch vụ downstream tiếp tục cùng trace.

~~~text
Browser
  -> order-service
       -> payment-service
            -> inventory-service
~~~

Nếu HTTP client truyền header `traceparent`, dịch vụ downstream có thể tạo span thuộc cùng trace. Nếu chỉ cấu hình OTLP exporter mà không truyền context, backend có thể nhận nhiều trace rời rạc.

W3C Trace Context thường dùng header `traceparent` và có thể có `tracestate`. OTLP không thay thế cơ chế truyền các header đó.

## 4. Micrometer Tracing và OpenTelemetry

Spring Boot dùng Micrometer Observation cho phần lớn instrumentation metrics/traces. Khi Micrometer Tracing được cấu hình với OpenTelemetry bridge, observation có thể tạo span và span được export qua OpenTelemetry SDK.

~~~mermaid
flowchart TD
    Framework["Spring MVC / HTTP client / Spring Modulith"]
    Registry["ObservationRegistry"]
    Handler["Tracing-aware observation handler"]
    Tracer["Micrometer Tracer"]
    OTel["OpenTelemetry SDK"]
    Exporter["OTLP span exporter"]
    Framework --> Registry --> Handler --> Tracer --> OTel --> Exporter
~~~

Cách này cho phép code nghiệp vụ và các thành phần Spring tiếp tục dùng abstraction Micrometer thay vì trực tiếp gọi OTel SDK ở mọi nơi.

### 4.1. Spring Modulith tạo module spans

Spring Modulith observability có thể instrument Spring components thuộc API của application module để tạo Micrometer spans khi được gọi. Span module-entry có thể có các thuộc tính:

| Attribute | Ý nghĩa |
|---|---|
| `module.identifier` | Định danh module |
| `module.invocation-type` | Kiểu invocation, ví dụ bean hoặc event listener |
| `module.method` | Method được thực thi |
| `module.name` | Tên hiển thị của module |

Ví dụ trace minh họa:

~~~text
HTTP POST /orders/42/complete
└── order: OrderManagement.complete(...)
    ├── inventory: InventoryManagement.reserve(...)
    ├── payment: PaymentManagement.capture(...)
    └── OrderCompleted event
        └── notification: OrderCompletedListener.on(...)
~~~

Tên span và cấu trúc cha-con phụ thuộc version, convention, listener execution và instrumentation thực tế. Trace trên chỉ minh họa cách đọc.

### 4.2. Bật Spring Modulith observability

Dùng Insight starter tương thích với Spring Boot/Spring Modulith BOM:

~~~groovy
dependencies {
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"
}
~~~

Nếu chỉ cần module observability, có thể khai báo artifact chuyên biệt theo version:

~~~groovy
dependencies {
    runtimeOnly "org.springframework.modulith:spring-modulith-observability-core"
}
~~~

Không cần khai báo cả Insight starter và observability core chỉ để có cùng chức năng. Kiểm tra dependency tree để tránh dependency dư thừa hoặc version không tương thích.

**Insight starter chưa tự kết nối backend tracing.** Cần cấu hình OpenTelemetry/OTLP theo đúng dòng Spring Boot.

## 5. Chọn dependency theo Spring Boot version

Spring Boot thay đổi cách đóng gói OpenTelemetry giữa dòng 3.x và 4.x. Không trộn hai cấu hình dưới đây trong cùng dự án.

### 5.1. Spring Boot 4.x

Với Spring Boot 4.0 trở lên:

~~~groovy
dependencies {
    runtimeOnly "org.springframework.boot:spring-boot-starter-opentelemetry"
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"
}
~~~

Starter OpenTelemetry cung cấp auto-configuration cho tracing qua Micrometer Tracing/OpenTelemetry và OTLP exporter. Quản lý version bằng Spring Boot BOM; Spring Modulith cần version tương thích với Boot đang dùng.

### 5.2. Spring Boot 3.5

Với Spring Boot 3.5, tài liệu chính thức dùng:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-actuator"
    runtimeOnly "io.micrometer:micrometer-tracing-bridge-otel"
    runtimeOnly "io.opentelemetry:opentelemetry-exporter-otlp"
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"
}
~~~

- `spring-boot-starter-actuator` cung cấp hạ tầng Actuator/auto-configuration.
- `micrometer-tracing-bridge-otel` nối Micrometer Tracing với OpenTelemetry.
- `opentelemetry-exporter-otlp` gửi spans đến Collector hỗ trợ OTLP.
- Insight starter bổ sung instrumentation module và endpoint Spring Modulith.

Nếu đã có Actuator qua starter khác, không khai báo trùng. Nếu BOM quản lý version, tránh chỉ định version riêng cho dependency con trừ khi có lý do cụ thể.

### 5.3. Bảng chọn nhanh

| Dự án | Dependency tracing OTLP | Namespace cấu hình |
|---|---|---|
| Spring Boot 4.x | `spring-boot-starter-opentelemetry` | `management.opentelemetry.tracing.export.otlp.*` |
| Spring Boot 3.5 | `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` + Actuator | `management.otlp.tracing.*` |
| Spring Modulith | Insight starter hoặc observability core phù hợp | Theo version Spring Modulith |

**Không sao chép namespace `management.otlp.tracing.*` của Boot 3.5 sang Boot 4.x.** Boot 4 dùng namespace mới cho tracing OpenTelemetry.

## 6. Cấu hình OTLP cho Spring Boot 4.x

Ví dụ dùng OTLP/HTTP tới Collector đang lắng nghe ở `localhost:4318`:

~~~yaml
spring:
  application:
    name: shop-service

management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    resource-attributes:
      service.namespace: acme-shop
      deployment.environment.name: dev
    tracing:
      export:
        otlp:
          endpoint: "http://localhost:4318/v1/traces"
          transport: http
          timeout: 10s
~~~

- `spring.application.name` đặt tên ứng dụng để nhận diện service.
- `service.namespace` nhóm các service cùng miền.
- `deployment.environment.name` phân biệt dev, staging và production.
- `sampling.probability: 1.0` thu thập toàn bộ trace trong môi trường phát triển. Không nên mặc định dùng 100% sampling cho production traffic lớn.
- `endpoint` trỏ tới OTLP HTTP traces endpoint.
- `transport: http` chọn HTTP/protobuf theo auto-configuration của Boot 4.
- `timeout` giới hạn thời gian export batch.

Nếu muốn gửi bằng gRPC:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: "http://localhost:4317"
          transport: grpc
~~~

Endpoint gRPC thường dùng host/port receiver, không thêm path `/v1/traces`.

### 6.1. Resource attributes

Resource mô tả service/process phát telemetry:

| Attribute | Ví dụ | Ý nghĩa |
|---|---|---|
| `service.name` | `shop-service` | Tên service |
| `service.namespace` | `acme-shop` | Nhóm service |
| `service.version` | `1.8.0` | Phiên bản triển khai |
| `deployment.environment.name` | `staging` | Môi trường |
| `service.instance.id` | `shop-instance-01` | Instance cụ thể |

Không gắn thuộc tính biến đổi theo từng request như order ID vào resource. Resource được dùng chung cho telemetry của một service instance.

S​​pring Boot hỗ trợ `management.opentelemetry.resource-attributes` và các biến môi trường `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` theo phạm vi version hỗ trợ. Nếu tự cung cấp `Resource` bean, hành vi gộp resource attributes auto-configured có thể thay đổi.

### 6.2. Quản lý credential

Không lưu token thật trong source control. Dùng biến môi trường hoặc secret management. Ví dụ dưới đây dùng chuỗi thay thế, không phải credential thật:

~~~yaml
management:
  opentelemetry:
    tracing:
      export:
        otlp:
          headers:
            Authorization: "Bearer TOKEN_FROM_SECRET_STORE"
~~~

Tên header, token và cơ chế auth phải đúng với Collector/backend nhận dữ liệu. Không đưa token vào log hoặc tài liệu chia sẻ.

## 7. Cấu hình OTLP cho Spring Boot 3.5

Với Boot 3.5, namespace tracing là `management.otlp.tracing.*`:

~~~yaml
spring:
  application:
    name: shop-service
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: "http://localhost:4318/v1/traces"
      transport: http
      timeout: 10s
~~~

Nếu dùng gRPC:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: "http://localhost:4317"
      transport: grpc
~~~

Các thuộc tính trên được tài liệu Spring Boot 3.5 mô tả cho OTLP tracing. Cấu hình chính xác có thể khác khi nâng cấp lên Boot 4.

### 7.1. Correlation ID trong log

Micrometer Tracing giúp gắn `traceId` và `spanId` vào MDC để log có correlation ID. Có thể tùy chỉnh format:

~~~yaml
logging:
  pattern:
    correlation: "[SHOP_SERVICE,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

Một dòng log minh họa:

~~~text
[shop-service,4bf92f3577b34da6a3ce929d0e0e4736,00f067aa0ba902b7]
INFO  OrderManagement - Order completed
~~~

Correlation ID phụ thuộc MDC và context propagation. Log có trace ID giúp tìm trace tương ứng nhưng không tự đảm bảo mọi log đã được gửi tới OpenTelemetry backend.

## 8. Cấu hình OpenTelemetry Collector

Collector nhận OTLP từ ứng dụng rồi chuyển tiếp telemetry tới backend. Để thử nghiệm, có thể dùng một pipeline chỉ xuất traces ra debug log.

Ví dụ `collector-config.yaml`:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
processors:
  batch:
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Cấu hình này mở receiver gRPC 4317 và HTTP 4318, dùng batch processor và debug exporter. Chỉ pipeline traces được khai báo; metrics và logs chưa được cấu hình.

Đây là cấu hình phục vụ kiểm tra local, không phải production hoàn chỉnh. Production cần xác thực, TLS/mTLS, giới hạn mạng, resource limits, batch/queue phù hợp, retry và exporter tới backend thật.

### 8.1. Chuyển tiếp tới backend

Sau khi xác nhận app gửi trace thành công, thay debug exporter bằng exporter phù hợp. Ví dụ cấu trúc khái niệm:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
processors:
  batch:
exporters:
  otlp/backend:
    endpoint: tempo:4317
    tls:
      insecure: true
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/backend]
~~~

`tempo:4317` và `tls.insecure: true` chỉ là ví dụ cho môi trường nội bộ không bật TLS. Production phải cấu hình endpoint, TLS certificate, authentication và exporter theo tài liệu backend.

### 8.2. Vì sao pipeline không nhận dữ liệu?

Collector chỉ kích hoạt component khi chúng được tham chiếu trong `service.pipelines`. Nếu receiver khai báo nhưng không nằm trong pipeline traces, dữ liệu trace không được xử lý qua pipeline đó.

Kiểm tra thêm:
- Collector có lắng nghe đúng interface và port không.
- Network policy có cho app kết nối tới host/port đó không.
- Ứng dụng dùng HTTP nhưng Collector chỉ bật gRPC, hoặc ngược lại.
- Endpoint có đúng path `/v1/traces` khi dùng HTTP không.
- Exporter Collector có kết nối tới backend và nhận auth/TLS đúng không.

## 9. Context propagation qua HTTP và bất đồng bộ

### 9.1. Truyền trace qua HTTP client

Spring Boot tự cấu hình các builder để thêm propagation headers cho HTTP client: `RestTemplateBuilder`, `RestClient.Builder` và `WebClient.Builder`.

Ví dụ với `RestClient`:

~~~java
package com.acme.shop.payment;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class PaymentGatewayClient {
    private final RestClient client;

    PaymentGatewayClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://payment-gateway")
                .build();
    }

    PaymentResult capture(PaymentRequest request) {
        return client.post()
                .uri("/payments/capture")
                .body(request)
                .retrieve()
                .body(PaymentResult.class);
    }
}
~~~

Hãy inject builder do Spring Boot auto-configure. Nếu tự tạo client bằng constructor hoặc builder không được auto-configure, propagation instrumentation có thể không được áp dụng. Khi downstream hỗ trợ W3C Trace Context, request mang header `traceparent` để liên kết spans cùng trace.

### 9.2. Async và event listener

Với `@Async` và executor do Spring Boot auto-configure, context propagation có thể cần bật rõ:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Nếu tự cấu hình executor, dùng `ContextPropagatingTaskDecorator` trên executor thực sự chạy tác vụ:

~~~java
package com.acme.shop.config;
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
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Ví dụ cần điều chỉnh theo executor thực tế. Spring Modulith event listener có thể sử dụng cơ chế thực thi riêng; phải xác nhận executor của listener có context propagation. Không giả định decorator của một executor bất kỳ tự áp dụng cho mọi tác vụ async.

### 9.3. Propagation không đồng nghĩa với export

Một trace context có thể được truyền qua nhiều service ngay cả khi mỗi service export trace tới backend khác nhau. Ngược lại, một service có thể export span thành công nhưng nếu context không được truyền, backend có thể hiển thị các trace rời rạc.

| Nhiệm vụ | Cơ chế |
|---|---|
| Giữ cùng trace qua HTTP | W3C Trace Context và client/server instrumentation |
| Giữ context qua thread/executor | Micrometer Context Propagation, task decorator hoặc cấu hình phù hợp |
| Gửi spans đến Collector | OTLP exporter |
| Lưu và truy vấn spans | Trace backend |
| Liên kết log với trace | MDC/correlation ID và log pattern |

## 10. Bổ sung span nghiệp vụ bằng Micrometer Observation

Spring Modulith đã tạo span ở các module entry được instrument. Khi cần đo một bước nghiệp vụ riêng, dùng Micrometer Observation để thêm span có ý nghĩa khác thay vì instrument lặp lại cùng ranh giới.

~~~java
package com.acme.shop.order;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderPricingService {
    private final ObservationRegistry observations;

    OrderPricingService(ObservationRegistry observations) {
        this.observations = observations;
    }

    PriceQuote calculate(Order order) {
        return Observation.createNotStarted("order.price-calculation", observations)
                .lowCardinalityKeyValue("pricing.mode", "standard")
                .observe(() -> doCalculate(order));
    }

    private PriceQuote doCalculate(Order order) {
        // Logic tính giá thực tế được lược bỏ.
        return new PriceQuote();
    }
}
~~~

Khi tracing handler được cấu hình, observation này có thể tạo span. Low-cardinality key-value phù hợp cho cả metrics và traces. Thông tin định danh riêng của đơn hàng nếu cần correlation nên được cân nhắc ở high-cardinality trace attribute/log theo chính sách dữ liệu; không đưa ID riêng vào metric tags.

Spring Boot tự đăng ký `TracingAwareMeterObservationHandler` trên `ObservationRegistry` khi Micrometer Tracing được cấu hình. Observation hoàn tất có thể tạo span tương ứng. Nếu chỉ muốn span mà không tạo metric, có thể dùng API `Tracer` cấp thấp của Micrometer Tracing.

## 11. Metrics và logs qua OTLP: không đồng nhất với trace export

Cần phân biệt ba signal:

### 11.1. Traces

Đây là luồng chính của bài. Micrometer Tracing bridge kết nối với OpenTelemetry SDK; OTLP tracing exporter gửi spans tới Collector hoặc backend. Spring Modulith module spans và các observation khác có thể xuất theo cùng pipeline tracing.

### 11.2. Metrics

Spring Boot dùng **Micrometer** làm API metrics. Tracing bridge không tự biến mọi Micrometer meter thành trace hoặc bảo đảm mọi metric được xuất bằng OpenTelemetry SDK.

Nếu muốn gửi Micrometer metrics qua OTLP, dùng Micrometer OTLP registry và cấu hình endpoint metrics phù hợp. Ví dụ:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: "http://localhost:4318/v1/metrics"
        step: 30s
~~~

Dependency registry và cấu hình chính xác phụ thuộc Spring Boot/Micrometer version. Với các dòng Boot hỗ trợ auto-configuration OTLP metrics, kiểm tra `micrometer-registry-otlp` trong runtime classpath và `management.otlp.metrics.export.*`.

Các counter Spring Modulith như `module.events.published` là Micrometer metrics. Chúng có thể được xuất qua Micrometer registry tương ứng, độc lập với việc trace exporter đang hoạt động.

### 11.3. Logs

Có `traceId` và `spanId` trong log correlation không có nghĩa log đã được export qua OTLP. Việc xuất log cần appender/bridge hoặc logging exporter phù hợp. Spring Boot 4 cung cấp hỗ trợ OpenTelemetry SDK logging và OTLP log exporter, nhưng không tự động nối mọi logback/log4j2 log event vào SDK logger provider out of the box.

Vì vậy, khi kiểm tra backend:
- Không thấy trace: kiểm tra tracing exporter.
- Không thấy metric: kiểm tra Micrometer registry và metrics export.
- Không thấy log: kiểm tra logging appender/bridge và log exporter.

## 12. Sampling, resource và chất lượng trace

### 12.1. Sampling

Spring Boot mặc định lấy mẫu một phần request để giảm tải backend; tài liệu tracing mô tả mặc định phổ biến là 10%. Có thể tăng sampling trong môi trường local:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

`1.0` nghĩa là lấy mẫu 100% theo cấu hình sampling hiện hành. Dùng nó trong local/test để xác nhận luồng, sau đó chọn tỷ lệ phù hợp với traffic, chi phí và yêu cầu điều tra production.

Với OpenTelemetry, Boot hỗ trợ các sampler như `always-on`, `always-off`, `trace-id-ratio`, `parent-based-trace-id-ratio` và các biến thể parent-based. Cần chọn sampler và probability nhất quán với parent context; không giả định mọi trace đều được export chỉ vì exporter kết nối thành công.

### 12.2. Resource attributes và span attributes

| Loại thuộc tính | Ví dụ | Phạm vi |
|---|---|---|
| Resource | `service.name=shop-service` | Toàn service/process phát telemetry |
| Resource | `deployment.environment.name=prod` | Môi trường triển khai |
| Span | `module.identifier=order` | Module trong operation |
| Span | `module.method=complete` | Method được quan sát |
| Span | `http.request.method=POST` | HTTP operation |
| Baggage | `tenant-tier=gold` | Context có thể truyền theo request nếu được cấu hình |

Không dùng resource attribute cho dữ liệu riêng từng request. Không đưa mật khẩu, access token, dữ liệu thẻ thanh toán, payload nhạy cảm hoặc thông tin cá nhân không cần thiết vào span attributes hay baggage.

### 12.3. Semantic conventions

Spring/Micrometer có conventions riêng cho metric và span names/attributes. Spring Boot ở các phiên bản mới hỗ trợ lựa chọn OpenTelemetry stable semantic conventions bằng cấu hình:

~~~yaml
management:
  observations:
    conventions: open-telemetry
~~~

Chỉ dùng khi phiên bản Spring Boot hỗ trợ property này và đã đánh giá ảnh hưởng đến tên meter/tag hiện có. Một số tùy biến tên metric theo convention mặc định có thể không còn tác dụng khi chuyển sang OTel conventions. Nên thực hiện như thay đổi có kiểm soát vì dashboard và alert có thể phụ thuộc tên cũ.

## 13. Quy trình xác minh end-to-end

### Bước 1 — Xác nhận dependency
- Insight starter hoặc observability core phù hợp đã có trong runtime classpath.
- Tracer bridge/OTLP exporter phù hợp với Spring Boot version đã được resolve.
- Không có hai bộ instrumentation cạnh tranh cùng tạo span cho cùng điểm vào ngoài chủ đích.
- Phiên bản Spring Boot, Spring Modulith và Micrometer được quản lý tương thích.

### Bước 2 — Xác nhận Collector
- OTLP receiver đúng protocol đang lắng nghe.
- Nếu HTTP, cổng/path đúng (thường `4318` và `/v1/traces`).
- Nếu gRPC, cổng/endpoint đúng (thường `4317`).
- Pipeline `traces` đã tham chiếu receiver, processor và exporter.
- Backend/exporter của Collector hoạt động.

### Bước 3 — Gửi request thử nghiệm

Gọi một endpoint tạo tương tác qua ít nhất hai module, ví dụ hoàn tất đơn hàng. Ghi lại thời điểm request, service name/build ID, correlation ID nếu có và kết quả nghiệp vụ.

### Bước 4 — Xem trace trong backend
- HTTP server span có xuất hiện không.
- Module-entry spans có tag `module.identifier`, `module.method` phù hợp không.
- Span con có parent ID hợp lệ không.
- Event listener bất đồng bộ có được liên kết hoặc có trace riêng theo semantics thực tế không.
- Span có status/error và duration phù hợp không.

### Bước 5 — Đối chiếu với nguồn bằng chứng khác

| Nguồn | Câu hỏi |
|---|---|
| `/actuator/modulith` | Bản deploy nhận diện những module và dependency nào? |
| `/actuator/metrics` | Các Micrometer meters nào đang có? |
| `module.events.published` | Event publication được instrument có tăng không? |
| Trace backend | Lần thực thi đã được instrument đi qua span nào? |
| Event Publication Registry | Publication đến transactional listener đã hoàn tất/thất bại/chờ xử lý ra sao nếu registry bật? |
| Log và dữ liệu DB | Kết quả nghiệp vụ cuối cùng có đúng không? |

`/actuator/modulith` là metadata cấu trúc; nó không phải trace viewer. Metric publish cũng không chứng minh listener hoàn tất.

### Bước 6 — Kiểm tra propagation qua dịch vụ khác

Gọi một endpoint làm phát sinh HTTP client call tới downstream. Xác minh downstream nhận được trace context và span xuất hiện dưới cùng trace. Nếu trace bị tách, kiểm tra builder được inject, propagation headers, proxy/gateway và sampler ở cả hai phía.

## 14. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| App chạy nhưng không có trace | Thiếu bridge/exporter hoặc tracing auto-configuration chưa kích hoạt | Dependency tree, startup logs, tracer/registry beans |
| Collector không nhận span | Sai host/port, protocol hoặc path | So transport, endpoint, receiver protocol và network |
| HTTP export báo 404 | Thiếu `/v1/traces` hoặc dùng nhầm endpoint | Kiểm tra URL OTLP/HTTP đầy đủ |
| gRPC export không kết nối | App dùng HTTP nhưng receiver chỉ gRPC, hoặc ngược lại | Đối chiếu port 4317/4318 và transport |
| Trace chỉ có HTTP span, không có module span | Modulith observability chưa bật hoặc điểm gọi không thuộc phạm vi instrument | Insight/core dependency, module API, Spring bean/proxy |
| Module spans xuất hiện nhưng không có backend trace | Exporter/Collector/backend lỗi | Kiểm tra export errors và Collector logs |
| Chỉ thấy một phần request | Sampling probability dưới 1 hoặc parent sampling loại trace | Kiểm tra sampler và trace ID |
| Mỗi service có trace ID khác nhau | Trace context không được propagate | RestClient/WebClient builder, `traceparent`, gateway |
| Async listener không liên kết trace | Context không truyền qua executor | ContextPropagatingTaskDecorator hoặc executor thực tế |
| Span có nhưng metric thiếu | Tracing và Micrometer metrics export là hai pipeline | Kiểm tra MeterRegistry, OTLP metrics registry và endpoint |
| Metric có nhưng logs không có | Chưa có logging bridge/appender export | Kiểm tra Logback/Log4j2 integration và OTel logging |
| Có hai span gần như trùng cùng method | Spring Modulith và annotation/aspect khác cùng instrument | Kiểm tra `@Observed`, custom AOP và instrumentation tự động |
| Trace attributes chứa quá nhiều dữ liệu | Gắn payload/ID hoặc raw input vào span | Giới hạn attributes, bỏ dữ liệu nhạy cảm, dùng correlation có kiểm soát |
| Export chậm hoặc mất batch khi backend quá tải | Timeout/queue/export interval hoặc Collector/backend capacity | Queue, batch, retry, timeout và Collector health |
| `/actuator/modulith` có module nhưng trace không có | Metadata kiến trúc không phụ thuộc trace sampling/export | Kiểm tra riêng instrument, sampling và exporter |

### 14.1. Phân biệt 404 với lỗi Collector

Khi dùng OTLP/HTTP, 404 thường gợi ý URL/path sai hoặc receiver/proxy không phục vụ signal path đó. Khi dùng gRPC, cần kiểm tra gRPC receiver và port thay vì thử thêm `/v1/traces` vào URL. Một endpoint của UI backend không nhất thiết là OTLP ingest endpoint.

### 14.2. Kiểm tra lỗi export

Nếu app log cho thấy export thất bại, hãy kiểm tra DNS/route mạng, TLS trust chain, chứng thư client và mTLS, authentication header, quyền ingest, batch export timeout, queue size, retry, backend capacity và Collector logs. Không ghi token hoặc header Authorization vào log chẩn đoán.

## 15. Thực hành: từ Spring Modulith đến OpenTelemetry Collector

Dựng một ứng dụng mẫu có module `order`, `inventory`, `notification` và một endpoint hoàn tất đơn hàng.

### Phần A — Chuẩn bị
1. Chọn cấu hình dependency phù hợp với Boot 4.x hoặc Boot 3.5.
2. Thêm Insight starter của Spring Modulith.
3. Cấu hình OTLP/HTTP tới Collector ở `localhost:4318`.
4. Chạy Collector với OTLP receiver và debug exporter.
5. Bật sampling 100% trong profile local.

### Phần B — Gửi và quan sát
1. Khởi động Collector trước, xác nhận receiver lắng nghe.
2. Khởi động ứng dụng Spring Boot.
3. Gửi request hoàn tất một đơn hàng thử nghiệm.
4. Xem log Collector, tìm resource service name và trace spans.
5. Xác nhận có HTTP span và các module spans được instrument.
6. Nếu listener bất đồng bộ, kiểm tra context propagation và span liên kết.
7. Thay debug exporter bằng backend tracing trong môi trường thử nghiệm để xem timeline trực quan.

### Phần C — Thử lỗi có kiểm soát

| Tình huống | Điều cần quan sát |
|---|---|
| Sai port Collector | Exporter không kết nối được, trace không tới Collector |
| Sai HTTP path | Collector hoặc proxy trả lỗi endpoint |
| Tắt sampling | Trace không được lấy mẫu theo policy |
| Bỏ propagation trong HTTP client | Downstream có thể tạo trace mới, không nối parent |
| Không propagate context qua executor | Async listener có thể thiếu quan hệ trace |
| Tắt Modulith observability | HTTP span còn nhưng module spans có thể biến mất |
| Làm listener ném exception | Span/error và publication state (nếu registry bật) phản ánh lỗi |
| Backend dừng nhận dữ liệu | Collector/exporter ghi nhận lỗi gửi hoặc retry |

Sau mỗi thay đổi, khôi phục cấu hình ban đầu và ghi rõ build, thời điểm, protocol và kết quả.

### Bảng đánh giá kết quả

| Tiêu chí | Kết quả mong đợi |
|---|---|
| Collector nhận OTLP | Có request và spans trong debug output |
| Resource | Có service name và môi trường |
| HTTP span | Có route/method phù hợp |
| Module span | Có `module.identifier`, `module.method` và invocation type |
| Trace hierarchy | Parent/child hoặc links phù hợp với luồng thực tế |
| Correlation log | Log có trace/span ID nếu Micrometer Tracing/MDC được cấu hình |
| Event metrics | Counter publish phản ánh event được instrument, độc lập với listener success |
| Async propagation | Context được truyền theo executor đã cấu hình |
| Backend | Có thể tìm trace theo service name và khoảng thời gian |

Đây là kết quả mong đợi để người học kiểm thử, không phải báo cáo một Collector/backend đã được chạy trong repository.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** OpenTelemetry và OTLP có phải cùng một khái niệm không?

**Đáp án:** Không. OpenTelemetry là hệ sinh thái API/SDK/semantic conventions; OTLP là giao thức truyền telemetry.

**Câu 2.** Insight starter của Spring Modulith đã tự gửi trace tới Grafana Tempo chưa?

**Đáp án:** Chưa. Nó cung cấp actuator/observability module; cần tracing implementation, exporter và Collector/backend được cấu hình.

**Câu 3.** Vì sao cần Micrometer Tracing bridge khi dùng Spring Boot 3.5 với OpenTelemetry?

**Đáp án:** Bridge nối Micrometer Observation/Tracing API của Spring với OpenTelemetry tracer; OTLP exporter sau đó gửi spans tới Collector.

**Câu 4.** OTLP/HTTP và OTLP/gRPC thường dùng cổng nào?

**Đáp án:** HTTP thường dùng 4318 với path `/v1/traces`; gRPC thường dùng 4317. Phải theo cấu hình receiver thật.

**Câu 5.** Nếu trace có HTTP span nhưng không có module span, có thể kết luận module không được gọi không?

**Đáp án:** Không. Cần kiểm tra Spring Modulith observability, module API instrumentation, bean/proxy và sampling/exporter.

**Câu 6.** OTLP exporter có tự truyền `traceparent` sang HTTP downstream không?

**Đáp án:** Không. Exporter gửi telemetry tới Collector; propagation được thực hiện bởi HTTP instrumentation/client builder và W3C Trace Context.

**Câu 7.** Nếu event publication counter tăng nhưng trace listener không có span, event chắc chắn chưa được xử lý?

**Đáp án:** Không. Sampling, exporter, listener instrumentation và context propagation có thể khiến span không xuất hiện. Cần đối chiếu log, Event Publication Registry và dữ liệu nghiệp vụ.

**Câu 8.** Spring Boot 4.x có cùng namespace OTLP tracing với Boot 3.5 không?

**Đáp án:** Không. Boot 4.x dùng `management.opentelemetry.tracing.export.otlp.*`; Boot 3.5 dùng `management.otlp.tracing.*`.

**Câu 9.** Chỉ cần thêm `micrometer-tracing-bridge-otel` là metrics của Micrometer tự được gửi qua OTLP?

**Đáp án:** Không. Bridge này phục vụ tracing; Micrometer metrics cần registry/export pipeline phù hợp, ví dụ OtlpMeterRegistry.

## 17. Checklist triển khai

- [ ] Phiên bản Spring Boot và Spring Modulith được quản lý bằng BOM tương thích.
- [ ] Insight starter/observability core đã có trong runtime classpath.
- [ ] Đã chọn đúng dependency OpenTelemetry theo Boot version.
- [ ] Đã cấu hình đúng namespace property và endpoint OTLP.
- [ ] Collector receiver bật đúng protocol/port và pipeline traces.
- [ ] Resource service name/version/environment được đặt rõ ràng.
- [ ] Sampling phù hợp với môi trường và lưu lượng.
- [ ] HTTP client dùng builder được auto-configure để truyền trace context.
- [ ] Async executor thực sự chạy listener có context propagation phù hợp.
- [ ] Không có duplicate instrumentation không chủ đích.
- [ ] Không đưa secrets/PII vào resource, baggage hoặc span attributes.
- [ ] Metrics và logs có pipeline riêng nếu cần xuất OTLP.
- [ ] Có kiểm tra export errors, queue, timeout, retry và Collector health.
- [ ] Có trace thử nghiệm end-to-end và so sánh với module graph/Actuator.

## 18. Ghi nhớ

- **OpenTelemetry là hệ sinh thái; Micrometer là abstraction mà Spring dùng; OTLP là giao thức truyền telemetry.**
- **Spring Modulith tạo module spans**, nhưng cần Micrometer Tracing/OpenTelemetry bridge, exporter và Collector/backend để xem traces.
- **Boot 4.x và Boot 3.5 có dependency/property namespaces khác nhau.** Không trộn cấu hình.
- **OTLP export và trace context propagation là hai cơ chế riêng.** Dùng builder và context propagation đúng cách để giữ trace xuyên service và executor.
- **Traces, metrics và logs là ba pipeline khác nhau.** Tracing bridge không tự bảo đảm mọi Micrometer metrics hoặc logback logs đều được xuất qua OTLP.
- Kiểm chứng bằng nhiều nguồn: module graph, `/actuator/modulith`, event metrics, traces, logs, publication state và kết quả nghiệp vụ.
- Sampling, resource attributes, cardinality, TLS/auth và khả năng chịu tải Collector/backend là phần của thiết kế vận hành, không chỉ là cấu hình để thấy một trace local.

## Tài liệu tham khảo

1. [Spring Boot 4.x — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — OpenTelemetry với OTLP, sampling, correlation IDs, propagation và custom spans.
2. [Spring Boot 4.x — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — ObservationRegistry, context propagation, OpenTelemetry resource và OTLP configuration.
3. [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html) — Dependency bridge/exporter và namespace `management.otlp.tracing.*`.
4. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Insight starter, module invocation spans và event metrics.
5. [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/) — Tracer API, bridge và propagation.
6. [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html) — ObservationRegistry, handlers và observations.
7. [OpenTelemetry Protocol Specification](https://opentelemetry.io/docs/specs/otlp/) — OTLP/gRPC, OTLP/HTTP và signal endpoints.
8. [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/) — Receivers, processors, exporters và service pipelines.
9. [OpenTelemetry Collector — Architecture](https://opentelemetry.io/docs/collector/architecture/) — Luồng dữ liệu qua Collector.
10. [Spring Boot — Metrics with OTLP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer OtlpMeterRegistry và metrics export endpoint.
