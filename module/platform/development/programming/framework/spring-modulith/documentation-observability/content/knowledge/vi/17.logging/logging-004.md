# logging.pattern.correlation

Trong ứng dụng Spring Boot có tracing, log cần cho biết **dòng log này thuộc request hoặc thao tác nào**. Một request có thể đi qua module `order`, gọi API của `inventory` rồi phát application event để `billing` xử lý. Nhiều lớp và nhiều thread cùng ghi log; nếu mỗi dòng chỉ có timestamp, level và logger name, việc tìm các dòng thuộc cùng một lần thực thi sẽ khó khăn.

Spring Boot hỗ trợ **correlation ID** trong log thông qua Micrometer Tracing và MDC. Thuộc tính `logging.pattern.correlation` cho phép tùy chỉnh phần prefix được dùng để liên kết log với trace/span. Ta có thể giữ định dạng mặc định, hoặc đưa tên ứng dụng, `traceId`, `spanId` và business correlation ID vào cùng một cụm dễ tìm.

Bài học thuộc chương **Logging** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Nội dung đặt `logging.pattern.correlation` trong bối cảnh Spring Modulith: cùng một ứng dụng có nhiều application module, một trace có thể bao gồm nhiều module spans, event listener có thể chạy bất đồng bộ, và log chỉ tương quan đúng khi context được truyền tới đúng nơi thực thi.

> **Phạm vi phiên bản:** Ví dụ chính dùng Spring Boot 3.5.x với Logback mặc định. Spring Boot 4.2.x còn cho phép tùy chỉnh tên MDC keys của trace/span bằng `management.tracing.mdc.trace-id-key` và `management.tracing.mdc.span-id-key`. Hãy kiểm tra đúng phiên bản và logging backend của dự án trước khi copy pattern.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích correlation ID, `traceId`, `spanId` và MDC khác nhau thế nào.
2. Hiểu vì sao Spring Boot có thể tự thêm correlation ID khi Micrometer Tracing hoạt động.
3. Cấu hình `logging.pattern.correlation` trong `application.yml` hoặc `application.properties`.
4. Đọc cú pháp Logback `%X{...}`, Spring placeholder và khoảng trắng cuối pattern.
5. Tránh ghi trùng application name hoặc trace/span IDs trong log pattern.
6. Phân biệt trace correlation với business correlation ID và request ID.
7. Hiểu ảnh hưởng của context propagation tới log trong `@Async` và `@ApplicationModuleListener`.
8. Kiểm tra log ở các application module và chẩn đoán khi correlation ID bị thiếu.

## 2. Correlation ID giải quyết vấn đề gì?

Một request tạo đơn có thể sinh nhiều log:

~~~text
INFO  OrderController       - Received order request
INFO  OrderService          - Validating order
INFO  InventoryService     - Checking stock
INFO  OrderService          - Order saved
INFO  BillingEventListener  - Preparing invoice
~~~

Nếu hệ thống có hàng trăm request đồng thời, những dòng trên dễ bị xen kẽ. Correlation ID thêm thông tin liên kết vào mỗi log, giúp lọc các dòng thuộc cùng một lần thực thi.

Khi Micrometer Tracing hoạt động, Spring Boot mặc định đưa correlation ID vào log. Correlation ID mặc định được xây dựng từ hai giá trị trong **Mapped Diagnostic Context (MDC)**:

- `traceId`: định danh của toàn trace; giữ nguyên qua các spans thuộc trace đó.
- `spanId`: định danh của span hiện tại; thay đổi khi execution chuyển sang span khác.

Ví dụ:

~~~text
[803B448A0489F84084905D3093480352-3425F23BB2432450]
~~~

Phần trước dấu gạch ngang là trace ID, phần sau là span ID. Khi request đi từ module `order` sang module `inventory`, trace ID thường giữ nguyên nếu context được duy trì, trong khi span ID có thể đổi theo span đang hoạt động.

| Khái niệm | Phạm vi | Mục đích |
| --- | --- | --- |
| **Trace ID** | Toàn bộ trace | Tìm các spans thuộc cùng luồng thực thi phân tán |
| **Span ID** | Một span | Xác định thao tác cụ thể trong trace |
| **Correlation ID mặc định của Boot** | Một cặp trace/span trong log | Hiển thị trace ID và span ID để điều tra |
| **Business correlation ID** | Một quy trình nghiệp vụ kéo dài qua nhiều request/event | Nối các bước nghiệp vụ, kể cả retry hoặc trace mới |
| **Request ID** | Một HTTP request | Xác định request tại một boundary cụ thể |
| **Event ID** | Một event/publication | Đối soát và chống xử lý trùng theo nghiệp vụ |

**Correlation ID không nhất thiết là một định danh nghiệp vụ duy nhất.** Correlation ID mặc định của Spring Boot chứa cả span ID nên có thể thay đổi trong cùng trace. Nếu muốn nối một đơn hàng qua nhiều request và nhiều lần retry, cần thêm business correlation ID hoặc order/event ID phù hợp.

## 3. MDC và cách Spring Boot tạo correlation ID

MDC là vùng key–value mà logging framework có thể đưa vào log line. Với Logback và SLF4J, một giá trị MDC được đọc trong pattern bằng `%X{key}`.

Ví dụ, khi MDC có:

~~~text
traceId = 803B448A0489F84084905D3093480352
spanId  = 3425F23BB2432450
~~~

Pattern Logback:

~~~text
%X{traceId:-}
%X{spanId:-}
~~~

sẽ in các giá trị tương ứng. Cú pháp `:-` trong `%X{traceId:-}` là fallback của conversion word Logback khi MDC key chưa có. Nó khác cú pháp Spring placeholder `$spring.application.name:$`.

Spring Boot/Micrometer Tracing đưa trace/span IDs vào MDC khi span hiện hành hoạt động. `logging.pattern.correlation` chỉ quyết định **hiển thị các giá trị đã có**. Nếu MDC không có `traceId` hoặc `spanId`, pattern không thể tự tạo chúng.

Khi ứng dụng sử dụng Micrometer Tracing, Spring Boot mặc định thêm correlation ID vào log. Nếu chỉ cần định dạng mặc định, thường **không cần tự cấu hình** `logging.pattern.correlation`.

Để có MDC trace/span IDs, ứng dụng cần Spring Boot Actuator, tracer implementation phù hợp (ví dụ Micrometer Tracing bridge cho OpenTelemetry hoặc Brave), instrumentation tạo span và context được duy trì trên thread hoặc reactive pipeline.

Dependency minh họa cho Spring Boot 3.5.x và OpenTelemetry:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
</dependencies>
~~~

Nếu cần xuất trace ra backend, bổ sung exporter tương ứng, ví dụ `opentelemetry-exporter-otlp`. Tuy nhiên, **exporter không phải điều kiện để correlation ID xuất hiện trong log cục bộ**; việc tạo span và cập nhật MDC mới là điều cần thiết cho phần này.

## 4. Cấu hình logging.pattern.correlation

Giả sử ứng dụng có tên `shop-application`. Cấu hình sau đưa application name, trace ID và span ID vào một prefix:

~~~yaml
spring:
  application:
    name: shop-application

logging:
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

Trong `application.yml` thực tế, Spring placeholder phải có dạng `${spring.application.name:}` để lấy tên ứng dụng và dùng chuỗi rỗng nếu property chưa được đặt.

| Thành phần | Chức năng |
| --- | --- |
| `[ ... ]` | Bao correlation prefix trong ngoặc vuông |
| Spring placeholder cho application name | Lấy tên ứng dụng; nếu không có property thì dùng chuỗi rỗng |
| `%X{traceId:-}` | Đọc `traceId` từ MDC; để trống nếu chưa có |
| `%X{spanId:-}` | Đọc `spanId` từ MDC; để trống nếu chưa có |
| Dấu cách cuối chuỗi | Tách correlation prefix khỏi logger name |
| `logging.include-application-name: false` | Tránh tên ứng dụng bị in hai lần |

Kết quả minh họa:

~~~text
2026-11-27T10:12:40.123+07:00 INFO
[shop-application,803B448A0489F84084905D3093480352,3425F23BB2432450]
com.example.shop.order.OrderService - Order saved
~~~

Nếu không có span hiện hành, hai MDC values có thể rỗng:

~~~text
[shop-application,,] com.example.shop.health.HealthIndicator - Health check
~~~

Điều đó không nhất thiết là lỗi: log có thể được ghi lúc startup, shutdown hoặc từ tác vụ không nằm trong trace.

### Vì sao có khoảng trắng cuối?

Spring Boot dùng correlation pattern như một phần trong log format. Pattern được nối với logger name ở phía sau. Nếu thiếu dấu cách cuối, log có thể dính liền:

~~~text
[shop-application,traceId,spanId]com.example.shop.order.OrderService
~~~

Vì vậy, mẫu chính thức đặt một dấu cách sau dấu `]`.

## 5. Cấu hình bằng application.properties

Nếu dự án dùng properties thay cho YAML:

~~~properties
spring.application.name=shop-application
logging.pattern.correlation=[${spring.application.name:},%X{traceId:-},%X{spanId:-}] 
logging.include-application-name=false
~~~

Trong file properties, giữ nguyên Spring placeholder `${spring.application.name:}`. Giữ dấu cách cuối sau dấu `]` để logger name không dính vào prefix. Kiểm tra editor hoặc formatter không tự trim khoảng trắng cuối dòng.

Không đổi Spring placeholder thành cú pháp placeholder của Logback. Spring placeholder dùng dấu `:` làm delimiter cho giá trị mặc định; `%X{...}` là conversion word của logging pattern.

## 6. Chọn format phù hợp cho ứng dụng mô-đun

Một format tốt nên hỗ trợ người vận hành nhanh chóng trả lời log thuộc ứng dụng nào, trace nào, span nào, module/package nào và business correlation ID nào liên kết các bước event/retry.

| Format | Ví dụ | Phù hợp khi |
| --- | --- | --- |
| Mặc định Boot | `[traceId-spanId]` | Chỉ cần tìm log trong trace |
| Có application name | `[shop-application,traceId,spanId]` | Gom log từ nhiều ứng dụng/backend |
| Thêm business correlation | `[shop-application,traceId,spanId,businessId]` | Một quy trình nghiệp vụ đi qua nhiều trace/event |
| Chỉ trace ID | `[traceId]` | Muốn nhóm mọi span/log của cùng trace |

Ví dụ format có business correlation ID:

~~~yaml
logging:
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-},%X{businessCorrelationId:-}] "
  include-application-name: false
~~~

`businessCorrelationId` là MDC key do ứng dụng tự đưa vào. Spring Boot **không tự tạo** business correlation ID này chỉ vì nó xuất hiện trong pattern.

Trong modular monolith, logger name/package có thể cho biết module phát log:

~~~text
[shop-application,trace-A,span-O] com.example.shop.order.OrderService - Validating order
[shop-application,trace-A,span-I] com.example.shop.inventory.InventoryService - Checking stock
~~~

Đây là ví dụ minh họa: trace ID giữ nguyên, span ID thay đổi khi thao tác đi vào span khác. Logger name cho biết lớp/module phát log; không cần đặt `service.name` khác nhau cho mỗi application module nếu chúng cùng một tiến trình.

## 7. Tùy chỉnh MDC key trong Spring Boot 4.2.x

Spring Boot 4.2.x cho phép đổi tên MDC keys mà Micrometer Tracing dùng để ghi trace ID và span ID:

~~~yaml
management:
  tracing:
    mdc:
      trace-id-key: trace_id
      span-id-key: span_id
~~~

Khi dùng tên mới, correlation format mặc định của Boot sẽ theo các key này. Nếu tự đặt `logging.pattern.correlation`, phải tham chiếu đúng key:

~~~yaml
logging:
  pattern:
    correlation: "[${spring.application.name:},%X{trace_id:-},%X{span_id:-}] "
  include-application-name: false
~~~

Nếu pattern vẫn dùng `%X{traceId:-}` và `%X{spanId:-}` trong khi MDC đã đổi sang `trace_id`/`span_id`, các trường có thể trống.

**Lưu ý với Brave:** theo tài liệu Spring Boot hiện hành, cấu hình MDC keys của Brave chỉ được áp dụng khi baggage được bật. Nếu `management.tracing.baggage.enabled=false` làm Brave không ghi trace/span IDs vào MDC, correlation ID trong log cũng không còn hoạt động như mong đợi. Hãy xác minh tracer implementation trước khi đổi cấu hình.

Không áp dụng các property đổi tên MDC của Boot 4.2 cho dự án Boot 3.5 nếu phiên bản đó chưa hỗ trợ. Với Boot 3.5, nên dùng key mặc định `traceId` và `spanId`.

## 8. Correlation pattern không thay thế context propagation

`logging.pattern.correlation` chỉ đọc giá trị hiện có trong MDC. Để log ở thread khác vẫn có trace/span IDs, **context phải được truyền tới thread đó**.

~~~mermaid
flowchart LR
    HTTP["HTTP thread
    traceId=A, spanId=H"] --> Submit["Submit async task"]
    Submit --> Worker["Worker thread"]
    Worker --> Listener["Application event listener"]
    Missing["Không có propagation"] -.-> Worker
    Propagated["Capture / restore context"] -.-> Worker
~~~

Với `@Async` hoặc `AsyncTaskExecutor`, Spring Boot khuyến nghị đăng ký `ContextPropagatingTaskDecorator` trên executor để observation context được truyền qua thread switch. Nếu listener của Spring Modulith dùng executor không có decorator, log trong listener có thể thiếu trace ID hoặc không nằm cùng trace với request gốc.

Ví dụ cấu hình executor:

~~~java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncLoggingConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor(
            ContextPropagatingTaskDecorator decorator) {

        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("module-events-");
        executor.setTaskDecorator(decorator);
        return executor;
    }
}
~~~

Phải xác minh listener thực sự dùng executor này. Nếu ứng dụng có executor riêng hoặc cấu hình lựa chọn executor tùy chỉnh, chỉ khai báo decorator bean chưa đủ.

Với `@ApplicationModuleListener`, listener được xử lý bất đồng bộ theo transaction lifecycle của Spring Modulith. Khi listener chạy sau commit, request gốc có thể đã trả response. Nếu context propagation hoạt động, log listener có thể tiếp tục dùng trace context được capture; nếu publication được retry sau khi ứng dụng restart, context gốc có thể không còn và lần xử lý mới có thể có trace mới.

Vì vậy:

- Log không có trace ID không chứng minh event chưa được xử lý.
- Trace ID mới ở lần retry không nhất thiết là lỗi.
- Dùng event ID/business correlation ID để liên kết nghiệp vụ qua retry.
- Kiểm tra publication state, consumer metrics và dữ liệu nghiệp vụ riêng; correlation ID không chứng minh listener thành công.

## 9. Business correlation ID và request ID

Trong một số quy trình, trace ID không đủ để nối tất cả log. Một đơn hàng có thể được tạo hôm nay, xử lý thanh toán sau vài phút, retry qua message broker và phát thông báo vào ngày hôm sau. Những lần thực thi đó có thể có **nhiều trace IDs**.

Một business correlation ID có thể liên kết các bước nghiệp vụ dài hạn:

~~~text
businessCorrelationId = order-flow-2026-0042

Trace A: POST /orders
Trace B: payment authorization
Trace C: inventory retry
Trace D: notification delivery
~~~

Nếu muốn thêm business correlation ID vào log, ứng dụng cần:

1. Sinh hoặc xác nhận ID tại boundary tin cậy.
2. Validate chiều dài và bộ ký tự nếu ID đến từ request header.
3. Đưa ID vào event payload khi consumer cần dùng sau commit.
4. Đặt MDC value trong đúng scope thực thi.
5. Xóa/khôi phục MDC sau khi xử lý để thread pool không rò ID sang task kế tiếp.

Ví dụ filter minh họa:

~~~java
package com.example.shop.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
class BusinessCorrelationFilter extends OncePerRequestFilter {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String incoming = request.getHeader("X-Correlation-Id");
        String correlationId = incoming != null && SAFE_ID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        response.setHeader("X-Correlation-Id", correlationId);
        MDC.put("businessCorrelationId", correlationId);
        try {
            filterChain.doFilter(request, response);
        }
        finally {
            MDC.remove("businessCorrelationId");
        }
    }
}
~~~

Đây là ví dụ cho HTTP request; trong production, chỉ chấp nhận correlation ID từ proxy/gateway đáng tin cậy nếu hệ thống có chính sách như vậy. Với event listener, MDC cần được thiết lập theo event payload và dọn sau xử lý. Không giả định filter HTTP sẽ chạy lại cho listener bất đồng bộ.

**Không đưa request ID, tenant ID, order ID hoặc email vào metric labels chỉ vì đã có chúng trong log.** Logs có thể hỗ trợ điều tra theo ID, còn metrics cần các nhãn có cardinality được kiểm soát. Dữ liệu cá nhân trong log vẫn cần phân quyền, masking và retention phù hợp.

## 10. Custom logging configuration

Nếu dùng logging configuration mặc định của Spring Boot, `logging.pattern.correlation` được dùng trong appender pattern tương ứng.

Nếu ứng dụng có `logback-spring.xml` hoặc `log4j2-spring.xml` riêng, pattern của appender có thể do file đó kiểm soát. Spring Boot cung cấp logging system property `LOG_CORRELATION_PATTERN` để cấu hình native logging có thể tham chiếu.

Ví dụ Logback tối giản:

~~~xml
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %5p ${LOG_CORRELATION_PATTERN}%logger{36} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Trong `logback-spring.xml`, dùng cú pháp property của Logback `${LOG_CORRELATION_PATTERN}`. Với custom config, kiểm tra appender thực tế có dùng property này hay không; chỉ đặt property trong YAML chưa chắc thay đổi một pattern đã được hardcode trong file logging.

### Logback và Log4j2

`%X{...}` là cú pháp thường thấy trong pattern Logback và được dùng trong ví dụ chính thức của Spring Boot cho `logging.pattern.correlation`. Nếu ứng dụng dùng Log4j2 hoặc structured JSON logging, cần kiểm tra pattern/encoder tương ứng và bảo đảm MDC fields được serialize. Không sao chép nguyên conversion words của Logback vào mọi logging backend.

### Structured logging

Nếu log xuất dưới dạng JSON, correlation fields có thể được biểu diễn thành các field riêng như:

~~~json
{
  "timestamp": "2026-11-27T10:12:40.123+07:00",
  "level": "INFO",
  "service": "shop-application",
  "traceId": "803B448A0489F84084905D3093480352",
  "spanId": "3425F23BB2432450",
  "message": "Order saved"
}
~~~

JSON trên chỉ là cấu trúc minh họa. Khi dùng structured logging, hãy xác nhận encoder có xuất MDC/trace fields theo tên và schema mong muốn. `logging.pattern.correlation` là property về **pattern**, không tự bảo đảm mọi structured encoder tạo field JSON tương ứng.

## 11. Bảo mật và chất lượng correlation IDs

Correlation ID giúp điều tra nhưng cũng có thể bị lạm dụng nếu lấy trực tiếp từ input không tin cậy:

- **Header injection/log forging:** ID chứa ký tự xuống dòng hoặc control characters có thể làm giả nhiều log entries.
- **Thông tin nhạy cảm:** không dùng email, số điện thoại, access token hoặc dữ liệu cá nhân làm correlation ID.
- **ID quá dài:** có thể làm log phình to và tăng chi phí tìm kiếm.
- **Giả mạo nguồn:** client có thể gửi ID giống một request khác nếu hệ thống tin tưởng header mà không có chính sách gateway.
- **Cross-tenant exposure:** dashboard/log query cần phân quyền; correlation ID không phải security boundary.

Hãy giới hạn độ dài và ký tự, xác định ai được phép tạo ID, đặt retention phù hợp và không dùng correlation ID để cấp quyền truy cập. Trace ID cũng là metadata vận hành; không xem nó như secret hoặc token xác thực.

## 12. Kiểm tra sau khi ứng dụng khởi động

Một ứng dụng chạy được chưa đủ chứng minh correlation pattern hoạt động. Kiểm tra lần lượt:

1. Xác nhận Actuator, Micrometer Tracing bridge và instrumentation tạo span.
2. Gửi request tới endpoint có HTTP observation, sau đó xem log ứng dụng.
3. Thực hiện request có luồng `order → inventory` và so sánh trace ID/span ID ở hai module.
4. Phát application event để listener chạy trên executor; kiểm tra MDC và context propagation.
5. Nếu có exporter, lấy trace ID từ log và tìm trace trong backend.

Ví dụ gọi endpoint:

~~~bash
curl -i http://localhost:8080/orders
~~~

Đường dẫn chỉ là ví dụ; dùng endpoint thực tế của dự án. Kết quả mong đợi là log trong request có correlation prefix chứa trace/span IDs.

Nếu module spans được instrument, span ID có thể khác nhau trong khi trace ID giữ nguyên. Nếu không có module span, logger name vẫn giúp xác định lớp phát log; cần kiểm tra instrumentation riêng nếu mục tiêu là có module-level spans.

Sampling ảnh hưởng việc trace được export tới backend; log MDC có thể được tạo trong scope span ngay cả khi trace không xuất hiện trong backend do sampling. Vì vậy, không kết luận pattern sai chỉ từ việc backend không có trace.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log không có correlation prefix | Không dùng Micrometer Tracing hoặc pattern custom không được áp dụng | Kiểm tra bridge, MDC và logging config |
| Có prefix nhưng trace/span rỗng | Log được ghi ngoài span hoặc MDC không được populate | Kiểm tra instrumentation và active context |
| Tên ứng dụng bị lặp hai lần | Đã đưa app name vào pattern nhưng vẫn bật include application name | Đặt `logging.include-application-name=false` |
| Logger name dính ngay sau dấu `]` | Thiếu khoảng trắng cuối pattern | Thêm một dấu cách sau dấu đóng |
| Đổi MDC key nhưng log trống | Custom pattern vẫn dùng tên key cũ | Cập nhật `%X{...}` theo key mới |
| Log HTTP có ID, listener không có | Context propagation qua executor chưa bật | Kiểm tra TaskDecorator/executor thực tế |
| Listener có trace ID khác | Listener chạy trong trace mới hoặc retry sau restart | Dùng business correlation/event ID và kiểm tra context lifecycle |
| Pattern hoạt động ở console nhưng không ở file | Console/file appender có pattern riêng | Kiểm tra cả `logging.pattern.file` và native appender |
| YAML đã đổi nhưng log không đổi | Custom `logback-spring.xml`/Log4j2 config đang kiểm soát pattern | Dùng `LOG_CORRELATION_PATTERN` hoặc cập nhật pattern native |
| Trace có trong log nhưng không có backend | Sampling, exporter hoặc Collector/backend lỗi | Kiểm tra đường xuất trace độc lập |
| Log JSON không có correlation field | Encoder không serialize MDC hoặc schema không ánh xạ field | Kiểm tra structured logging encoder |
| Log chứa ID do client gửi tùy ý | Header không được validate hoặc tin cậy sai nguồn | Validate, giới hạn ký tự/độ dài và đặt chính sách gateway |

## 14. Bài thực hành

Chuẩn bị ứng dụng Spring Boot có module `order` và `inventory`, Actuator, Micrometer Tracing bridge và logging backend mặc định Logback.

1. **Tạo baseline:** chạy ứng dụng với cấu hình mặc định, gửi request và tìm correlation ID mặc định trong log.
2. **Tùy chỉnh pattern:** đặt `logging.pattern.correlation` để thêm `spring.application.name`, `traceId` và `spanId`; tắt application name mặc định để tránh lặp.
3. **Kiểm tra whitespace:** cố ý bỏ dấu cách cuối, quan sát logger name dính vào correlation prefix, rồi khôi phục.
4. **Gọi nhiều module:** gửi request qua `order → inventory` và so sánh trace ID/span ID trong log.
5. **Thêm business correlation ID:** đặt MDC key trong HTTP filter, thêm vào pattern, và bảo đảm MDC được xóa sau request.
6. **Kiểm tra event listener:** phát `OrderPlaced` và xem log của `inventory` listener; xác minh executor có context propagation.
7. **Thử mất context:** dùng executor thử nghiệm không có decorator, quan sát correlation fields bị thiếu hoặc trace bị tách; bật propagation và so sánh.
8. **Kiểm tra custom logging config:** nếu dự án có `logback-spring.xml`, xác minh appender dùng `LOG_CORRELATION_PATTERN`.
9. **Kiểm tra bảo mật:** gửi header correlation ID có ký tự không hợp lệ/độ dài quá mức; xác nhận ID được thay thế hoặc từ chối theo policy.
10. **Đối chiếu backend:** lấy trace ID từ log và tìm trace trong backend nếu exporter được cấu hình.

Mẫu ghi kết quả:

| Kịch bản | Log có correlation ID? | Trace ID | Span ID | Business ID | Kết luận |
| --- | --- | --- | --- | --- | --- |
| HTTP request bình thường | … | … | … | … | … |
| Gọi qua `order → inventory` | … | … | … | … | … |
| Listener async có propagation | … | … | … | … | … |
| Listener async không propagation | … | … | … | … | … |
| Event retry sau restart | … | … | … | … | … |

### Câu hỏi tự kiểm tra

1. Spring Boot lấy correlation ID mặc định từ những MDC keys nào?
2. Vì sao `traceId` giữ nguyên trong một trace nhưng `spanId` có thể đổi giữa module logs?
3. `logging.pattern.correlation` có tự tạo trace hay chỉ định dạng giá trị MDC?
4. Vì sao mẫu Logback có dấu cách cuối?
5. Khi thêm application name vào correlation pattern, tại sao cần xem xét `logging.include-application-name`?
6. Khác nhau giữa trace ID và business correlation ID là gì?
7. Tại sao listener async có thể không ghi được trace ID dù HTTP request ban đầu có correlation ID?
8. Trong Spring Boot 4.2, đổi MDC key sang `trace_id` mà pattern vẫn đọc `traceId` sẽ có kết quả gì?
9. Khi dùng custom `logback-spring.xml`, vì sao đổi YAML có thể chưa đủ?
10. Có nên dùng tenant ID hoặc order ID làm metric tag chỉ vì đã thêm chúng vào log không?

## 15. Tổng kết

`logging.pattern.correlation` là cách tùy chỉnh **phần correlation prefix trong log**, thường dựa trên `traceId` và `spanId` do Micrometer Tracing đặt vào MDC. Spring Boot đã có correlation ID mặc định khi tracing hoạt động; chỉ cần custom pattern khi muốn thêm application name, đổi cách hiển thị hoặc đưa business correlation ID do ứng dụng quản lý vào log.

Trong ứng dụng Spring Modulith, correlation prefix giúp nối log giữa các application module và hỗ trợ tìm trace tương ứng. Tuy nhiên, pattern không tạo trace, không xuất trace tới backend và không tự truyền context qua thread. Với event listener bất đồng bộ, cần cấu hình context propagation cho executor và mang business metadata cần thiết trong event payload. Kiểm tra MDC, logger/appender pattern, trace backend và kết quả nghiệp vụ riêng sẽ giúp phân biệt **log được liên kết**, **trace được thu thập** và **event thực sự được xử lý thành công**.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Tracing: Logging Correlation IDs](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
- [Spring Boot 4.2 — Tracing: Logging Correlation IDs và MDC keys](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot 3.5 — Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html).
- [Spring Boot 3.5 API — LoggingSystemProperty](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/logging/LoggingSystemProperty.html).
- [Spring Boot 3.5 — Context Propagation](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html).
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/).
