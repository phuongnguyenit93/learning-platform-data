# Correlation ID trong log

## 1. Bối cảnh: tìm đúng log của một lần xử lý

Một ứng dụng Spring Boot chia thành các application module như `orders`, `inventory` và `payments` có thể ghi hàng nghìn dòng log mỗi phút. Khi một đơn hàng gặp lỗi, nhóm phát triển cần tìm các dòng log liên quan trong toàn bộ luồng xử lý: request đi vào module nào, module nào gọi module nào, listener nào xử lý event và bước nào phát sinh exception.

Tìm theo thời gian hoặc nội dung message thường không đủ chính xác khi nhiều request chạy đồng thời. **Correlation ID** giúp liên kết các log thuộc cùng một hoạt động. Khi ứng dụng dùng Micrometer Tracing, Spring Boot có thể đưa **trace ID** và **span ID** vào logging context để các dòng log liên kết được với trace tương ứng.

Bài **“Correlation ID trong log”** thuộc chương **Logging** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Học phần dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation.

Sau bài này, bạn sẽ có thể:

1. Phân biệt correlation ID do ứng dụng tạo, trace ID, span ID và request ID.
2. Hiểu Spring Boot đưa trace/span IDs vào MDC như thế nào.
3. Cấu hình log pattern để hiển thị correlation ID với Logback.
4. Tìm các log của cùng một trace và phân biệt các span trong trace.
5. Tạo request ID riêng khi nghiệp vụ cần một mã tương quan ngoài tracing.
6. Giữ MDC đúng vòng đời, tránh rò rỉ context giữa các request trên thread pool.
7. Truyền trace context qua HTTP, `@Async` và Reactor.
8. Kết hợp correlation ID với module metadata của Spring Modulith mà không đưa dữ liệu nhạy cảm vào log.
9. Kiểm thử và xử lý lỗi khi log thiếu correlation ID.

> **Phạm vi:** Ví dụ tập trung vào Spring Boot với Micrometer Tracing và logging mặc định dùng Logback. Các property tracing/logging có thể thay đổi giữa các dòng Spring Boot; hãy xác minh với phiên bản ứng dụng. Ví dụ log và ID trong bài là dữ liệu giả định, không phải log của một hệ thống thật.

## 2. Correlation ID, trace ID, span ID và request ID

### 2.1. Correlation ID là mục đích, không phải một chuẩn ID duy nhất

**Correlation ID** là một mã dùng để liên kết các bản ghi hoặc sự kiện có liên quan. Tùy hệ thống, mã này có thể là:

- Trace ID do distributed tracing tạo ra.
- Request ID do gateway hoặc ứng dụng sinh cho một HTTP request.
- Job ID để liên kết các bước của một tác vụ nền.
- Business correlation key để nối các sự kiện của một quy trình nghiệp vụ.

Do đó, khi một tài liệu nói “tìm correlation ID”, cần xác định **mã nào đang được sử dụng và được truyền qua những ranh giới nào**.

### 2.2. Trace ID liên kết toàn bộ trace

**Trace ID** nhận diện một trace, tức một hành trình xử lý có liên quan. Các spans thuộc cùng trace thường mang cùng trace ID, kể cả khi đi qua nhiều module hoặc nhiều service.

Ví dụ:

```text
traceId = 4bf92f3577b34da6a3ce929d0e0e4736

orders.placeOrder       traceId=4bf92f3577b34da6a3ce929d0e0e4736
inventory.reserve       traceId=4bf92f3577b34da6a3ce929d0e0e4736
payments.authorize      traceId=4bf92f3577b34da6a3ce929d0e0e4736
```

Khi cần tìm **tất cả log của một lần xử lý**, trace ID thường là khóa tìm kiếm phù hợp nhất.

### 2.3. Span ID phân biệt từng thao tác trong trace

Một **span ID** nhận diện một span cụ thể. Trong cùng một trace, mỗi span có span ID riêng; vì vậy span ID có thể thay đổi khi luồng xử lý đi từ thao tác cha sang thao tác con.

```text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736

Span ID       Operation
--------------------------------
a1b2c3d4      HTTP POST /orders
b2c3d4e5      orders.placeOrder
c3d4e5f6      inventory.reserve
d4e5f607      payments.authorize
```

Trong ví dụ, trace ID giữ nguyên còn span ID thay đổi. Điều này giúp trả lời hai câu hỏi khác nhau:

- **Trace ID:** Những log nào thuộc cùng một luồng xử lý?
- **Span ID:** Dòng log này được ghi trong thao tác/span cụ thể nào?

### 2.4. Request ID là mã riêng do hệ thống quy định

Một ứng dụng hoặc API gateway có thể tạo `requestId` và trả về header `X-Request-ID` cho client. Request ID có thể hữu ích khi:

- Hệ thống chưa bật tracing.
- Một yêu cầu nghiệp vụ cần mã tra cứu hiển thị cho bộ phận hỗ trợ.
- Một request đi qua thành phần chưa hỗ trợ W3C/B3 propagation.
- Cần đối chiếu log ở tầng gateway với log ứng dụng theo một hợp đồng riêng.

Request ID **không tự động trở thành trace ID**. Nếu tự sinh request ID ở mỗi service mà không truyền tiếp, mỗi service có thể ghi một mã khác nhau. Khi đã có distributed tracing, trace ID thường phù hợp hơn để liên kết xuyên service; request ID riêng chỉ nên bổ sung khi có nhu cầu nghiệp vụ rõ.

### 2.5. So sánh các loại ID

| Loại ID | Phạm vi | Thay đổi trong cùng trace? | Nguồn tạo thường gặp |
| --- | --- | --- | --- |
| `traceId` | Toàn bộ trace | Không | Tracer hoặc context nhận từ upstream |
| `spanId` | Một span/operation | Có, mỗi span một ID | Tracer |
| `parentSpanId` | Quan hệ span cha-con | Khác nhau theo span | Tracer |
| `requestId` | Một request theo hợp đồng ứng dụng | Tùy cách thiết kế | Gateway hoặc ứng dụng |
| `correlationId` nghiệp vụ | Một quy trình nghiệp vụ | Tùy domain | Hệ thống nghiệp vụ |

Không dùng một thuật ngữ chung để giả định mọi hệ thống đều lưu cùng một loại ID. Hãy ghi rõ tên field, nguồn tạo và quy tắc truyền trong tài liệu vận hành.

## 3. MDC: logging context hoạt động thế nào?

### 3.1. MDC lưu metadata gắn với dòng thực thi

**Mapped Diagnostic Context (MDC)** là một map key-value mà logging framework có thể đưa vào mỗi log event. Với SLF4J, mã ứng dụng truy cập MDC qua `org.slf4j.MDC`.

Ví dụ:

```java
import org.slf4j.MDC;

MDC.put("requestId", "req-7f2a");
logger.info("Starting order processing");
MDC.remove("requestId");
```

Nếu log pattern có `%X{requestId}`, dòng log có thể hiển thị giá trị request ID mà không cần truyền tham số đó vào từng câu lệnh logger.

MDC thường được triển khai dựa trên **ThreadLocal**. Điều này thuận tiện với xử lý đồng bộ trên cùng thread, nhưng cần chú ý khi công việc chuyển sang executor, thread pool hoặc reactive pipeline.

### 3.2. Spring Boot và Micrometer Tracing tự thêm trace/span IDs

Khi Micrometer Tracing được cấu hình, Spring Boot mặc định đưa correlation ID vào log. Correlation ID mặc định được tạo từ hai giá trị MDC:

- `traceId`
- `spanId`

Một log minh họa:

```text
[4bf92f3577b34da6a3ce929d0e0e4736-a1b2c3d4] INFO
c.e.shop.orders.OrderManagement - Order accepted
```

Định dạng trên có thể khác theo logging configuration và phiên bản. Ý nghĩa cốt lõi là trace ID giúp nhóm các spans, còn span ID chỉ ra ngữ cảnh thao tác đang ghi log.

**Không cần tự gọi `MDC.put("traceId", ...)` để ghi trace ID** khi Micrometer Tracing đã quản lý context. Việc tự đặt hoặc ghi đè các key này có thể làm log không còn khớp với span thật.

### 3.3. Context được cập nhật theo span hiện hành

Khi một span con bắt đầu, logging context có thể hiển thị cùng trace ID nhưng span ID của span con. Khi scope span con kết thúc, context được khôi phục về span cha.

Vì vậy, trong một trace:

```text
[trace-A-span-root] HTTP request received
[trace-A-span-order] Validating order
[trace-A-span-stock] Reserving stock
[trace-A-span-order] Order accepted
```

Một trace có thể có nhiều span ID. Khi tìm toàn bộ luồng, lọc theo **trace ID**; khi muốn tập trung vào một thao tác, lọc thêm **span ID**.

### 3.4. Log ngoài trace có thể không có ID

Các log ở startup, shutdown, scheduled job độc lập hoặc code chạy trước khi có tracing context có thể không có `traceId`/`spanId`. Pattern thường hiển thị dấu thay thế như `-` hoặc để trống.

Đây không tự động là lỗi. Chỉ coi là bất thường khi log thuộc một request/operation đáng lẽ được instrument nhưng lại không có context.

## 4. Cấu hình correlation ID trong Spring Boot

### 4.1. Dùng mặc định trước khi tùy chỉnh

Khi Micrometer Tracing đã được cấu hình, Spring Boot tự thêm correlation ID vào log mặc định. Trước khi thay đổi pattern, hãy chạy ứng dụng và xác nhận log có dạng:

```text
[traceId-spanId] INFO ... - message
```

Nếu đã có định dạng phù hợp, không cần tạo thêm filter chỉ để ghi trace ID. Việc bổ sung cấu hình không cần thiết có thể làm log khó đọc hoặc vô tình ghi trùng trường.

### 4.2. Tùy chỉnh format bằng `logging.pattern.correlation`

Nếu muốn hiển thị application name cùng trace/span IDs:

```yaml
spring:
  application:
    name: shop-service

logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
```

Kết quả minh họa:

```text
[4bf92f3577b34da6a3ce929d0e0e4736,a1b2c3d4] INFO ...
```

Trong ví dụ:

- `%X{traceId:-}` đọc MDC key `traceId`, dùng `-` nếu chưa có giá trị.
- `%X{spanId:-}` đọc MDC key `spanId`.
- Dấu cách ở cuối pattern giúp tách correlation ID khỏi logger name theo default logging pattern.

`logging.pattern.correlation` là property Spring Boot hỗ trợ cho correlation ID; nếu ứng dụng dùng cấu hình Logback tùy chỉnh hoàn toàn, phải kiểm tra pattern thực tế có sử dụng correlation pattern hay chưa.

### 4.3. Tùy chỉnh MDC key names

Spring Boot cho phép đổi tên MDC keys của trace ID và span ID:

```yaml
management:
  tracing:
    mdc:
      trace-id-key: trace_id
      span-id-key: span_id
```

Khi đó, log pattern tùy chỉnh phải tham chiếu đúng key mới:

```yaml
logging:
  pattern:
    correlation: "[%X{trace_id:-},%X{span_id:-}] "
```

Nếu chỉ đổi MDC key nhưng vẫn đọc `%X{traceId}`, correlation ID có thể trống. Khi đổi tên, hãy cập nhật cả log pattern, parser, dashboard, alert và các truy vấn tìm kiếm.

### 4.4. Lưu ý khi dùng Brave

Tài liệu Spring Boot hiện hành lưu ý rằng với **Brave**, MDC key names được áp dụng khi baggage được bật. Nếu đặt:

```yaml
management:
  tracing:
    baggage:
      enabled: false
```

Brave có thể ngừng ghi trace/span IDs vào MDC theo cơ chế mặc định, khiến log correlation không còn hoạt động như mong đợi. Nếu đang dùng Brave và log mất IDs sau khi thay cấu hình baggage, kiểm tra property này trước khi tự ghi trace ID bằng code.

Không nên bật baggage chỉ vì muốn log có thêm một field mà chưa hiểu tác động propagation. Hãy chọn cấu hình tracer và baggage theo nhu cầu, rồi kiểm thử cả log lẫn trace.

## 5. Thêm request ID riêng khi nghiệp vụ cần

### 5.1. Khi nào cần request ID ngoài trace ID?

Trace ID phù hợp để liên kết trace xuyên service. Request ID riêng có thể hữu ích nếu tổ chức cần:

- Mã tra cứu được trả cho người dùng hoặc support team.
- Liên kết request ở gateway và hệ thống không dùng cùng tracing protocol.
- Một mã theo hợp đồng API tồn tại ngay cả khi tracing bị tắt hoặc sampling loại trace.
- Đối chiếu một yêu cầu với hệ thống ticket/CS nội bộ.

Nếu không có nhu cầu như vậy, trace ID thường đã đáp ứng mục tiêu tìm log. Tránh tạo thêm nhiều ID cùng ý nghĩa khiến người vận hành không biết nên tìm theo trường nào.

### 5.2. Tạo request ID an toàn trong servlet filter

Ví dụ filter dùng Spring MVC/Servlet:

```java
package com.example.shop.logging;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        String supplied = request.getHeader("X-Request-ID");

        // Chỉ chấp nhận giá trị theo allowlist và độ dài giới hạn.
        // Nếu không hợp lệ, tạo ID mới ở phía server.
        String requestId = supplied != null
                && SAFE_ID.matcher(supplied).matches()
                ? supplied
                : UUID.randomUUID().toString();

        String previous = MDC.get("requestId");
        MDC.put("requestId", requestId);
        response.setHeader("X-Request-ID", requestId);

        try {
            filterChain.doFilter(request, response);
        }
        finally {
            // Khôi phục context trước đó để tránh rò rỉ
            // sang request tiếp theo dùng lại servlet thread.
            if (previous == null) {
                MDC.remove("requestId");
            }
            else {
                MDC.put("requestId", previous);
            }
        }
    }
}
```

Ví dụ cần các dependency Spring Web/Servlet tương ứng. Nếu ứng dụng dùng WebFlux, hãy dùng cơ chế reactive context/filter phù hợp, không bê nguyên servlet filter sang reactive stack.

Những điểm cần lưu ý:

- Không chấp nhận chuỗi tùy ý làm header value; validate allowlist và giới hạn độ dài.
- Nếu chỉ tin header từ gateway đã xác thực, hãy giới hạn mạng/nguồn gửi theo hợp đồng triển khai.
- Không dùng request ID làm bằng chứng xác thực hoặc phân quyền.
- Luôn khôi phục MDC trong `finally` vì servlet threads được tái sử dụng.
- Không ghi request ID chứa email, số điện thoại hoặc dữ liệu nhận diện cá nhân.

### 5.3. Đưa request ID vào log pattern

Có thể ghép request ID với trace/span IDs:

```yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-},requestId=%X{requestId:-}] "
```

Một log có thể trông như:

```text
[4bf92f3577b34da6a3ce929d0e0e4736-a1b2c3d4,requestId=req-7f2a]
INFO ... OrderManagement - Order accepted
```

Giá trị request ID và trace ID có thể khác nhau. Ghi rõ ý nghĩa từng trường để support team không nhầm lẫn.

### 5.4. Truyền request ID qua service khác

Request ID tùy chỉnh không tự được Micrometer Tracing truyền qua HTTP. Nếu cần giữ mã này xuyên nhiều service, cần một hợp đồng header rõ ràng và cơ chế truyền được kiểm soát.

Với trace context, hãy dùng W3C `traceparent` hoặc B3 qua HTTP client builder được Spring Boot auto-configure. Không tự sao chép trace ID vào header tùy chỉnh rồi ghi đè tracing context.

Nếu cần truyền một business correlation key, có thể dùng baggage có allowlist khi phù hợp. Baggage được truyền rộng, nên chỉ dùng field không nhạy cảm và có quy tắc giới hạn giá trị.

## 6. Ghi module metadata cùng correlation ID

### 6.1. Vì sao log nên cho biết module?

Trong Spring Modulith, module graph mô tả các application module và dependency giữa chúng. Khi điều tra một trace, ngoài trace ID/span ID, tên module giúp người đọc hiểu dòng log đến từ phần nào của ứng dụng.

Ví dụ:

```text
[trace-A-span-1] INFO module=orders method=placeOrder - Order accepted
[trace-A-span-2] INFO module=inventory method=reserve - Stock reserved
[trace-A-span-3] INFO module=payments method=authorize - Payment authorized
```

Các giá trị `module` và `method` là metadata có thể lấy từ code/module context. Hãy ưu tiên tên module và operation ổn định, không dùng order ID hoặc payload động làm module label.

### 6.2. Log có cấu trúc bằng SLF4J

Với SLF4J 2, có thể dùng fluent logging để thêm key-value:

```java
logger.atInfo()
    .addKeyValue("module", "orders")
    .addKeyValue("operation", "placeOrder")
    .addKeyValue("orderStatus", "accepted")
    .log("Order accepted");
```

Cú pháp trên giúp logging backend có thể lưu field riêng thay vì phải parse nội dung message. Cách serialize key-values phụ thuộc logging provider và cấu hình encoder; kiểm tra output thực tế trước khi viết query cho log platform.

Nếu logger chỉ in chuỗi message, key-values có thể không xuất hiện theo định dạng mong muốn. Hãy cấu hình structured encoder hoặc pattern phù hợp với logging stack.

### 6.3. Đối chiếu với Spring Modulith module-entry spans

Khi Spring Modulith Observability instrument module API, span có thể mang metadata như:

| Attribute | Ý nghĩa |
| --- | --- |
| `module.identifier` | Technical identifier của module |
| `module.name` | Tên hiển thị module |
| `module.invocation-type` | Kiểu invocation, ví dụ bean/event listener |
| `module.method` | Method được gọi |

Log có thể ghi cùng module/method để người vận hành đối chiếu trace với module graph. Không cần tự ghi mọi attribute vào mọi dòng log nếu MDC hoặc trace backend đã cung cấp đủ thông tin.

### 6.4. Đừng biến logs thành bản sao của trace

Logs và traces phục vụ hai góc nhìn:

- **Log:** message, lỗi, trạng thái nghiệp vụ và ngữ cảnh cần thiết để giải thích.
- **Trace:** thời gian, parent-child, đường đi và metadata của từng span.
- **Metrics:** xu hướng, tần suất và phân phối tổng hợp.

Nếu mỗi dòng log chứa toàn bộ baggage, payload, tags và stack trace, hệ thống sẽ tăng chi phí và có nguy cơ lộ dữ liệu. Ghi đủ thông tin để hiểu sự kiện, rồi dùng trace ID để mở trace chi tiết.

## 7. Correlation ID khi gọi HTTP service khác

### 7.1. Dùng HTTP client builder do Spring Boot cấu hình

Micrometer Tracing tự truyền trace context khi sử dụng các HTTP client đã được Spring Boot instrument. Ví dụ `RestClient`:

```java
@Bean
RestClient inventoryClient(RestClient.Builder builder) {
    return builder
        .baseUrl("http://inventory-service")
        .build();
}
```

Hoặc `WebClient`:

```java
@Bean
WebClient inventoryWebClient(WebClient.Builder builder) {
    return builder
        .baseUrl("http://inventory-service")
        .build();
}
```

Với Spring Boot 3.x, `RestTemplateBuilder` auto-configured cũng là lựa chọn cho `RestTemplate`. Hãy dùng builder được inject từ Spring thay vì tự tạo client rời.

### 7.2. Không tự truyền trace ID bằng cách copy MDC

Không làm theo kiểu:

```java
// Không nên: tự copy traceId vào header tùy chỉnh.
String traceId = MDC.get("traceId");
request.header("X-Trace-Id", traceId);
```

Cách này bỏ qua tracer context, span hiện tại, sampling flags và propagation format. Dùng builder auto-configured để Micrometer Tracing tạo đúng `traceparent` hoặc B3 headers.

Nếu đối tác yêu cầu `X-Request-ID` riêng, truyền request ID theo hợp đồng riêng; đừng nhầm nó với W3C/B3 trace context.

### 7.3. Xác minh hai service cùng trace

Giả sử `orders` gọi `inventory-service`:

```text
orders-service:
  traceId = abc...
  spanId  = 111...

inventory-service:
  traceId = abc...
  spanId  = 222...
```

Trace ID giống nhau chứng tỏ hai log có thể được liên kết vào cùng trace. Span ID khác nhau là bình thường vì mỗi service có span riêng.

Nếu trace ID khác, kiểm tra client builder, propagation headers, định dạng W3C/B3 mà hai bên consume/produce và tracing context tại thời điểm gọi.

## 8. Correlation ID qua @Async, executor và Reactor

### 8.1. MDC không tự truyền qua thread pool

MDC thường dựa trên ThreadLocal. Khi request thread gửi task sang thread khác, thread mới không tự có cùng MDC context. Log trong task có thể thiếu trace ID/request ID, hoặc tệ hơn, dùng giá trị còn sót lại nếu code tự quản lý MDC sai.

Ví dụ tình huống:

```text
HTTP thread:
  traceId=abc
  spanId=111
  requestId=req-7f2a

Async worker:
  traceId=-
  spanId=-
  requestId=-
```

Đây là dấu hiệu context chưa được propagate. Không sửa bằng cách đọc MDC ở thread cha rồi ghi vĩnh viễn vào thread worker; phải dùng cơ chế capture/restore context theo vòng đời task.

### 8.2. Auto-configured AsyncTaskExecutor

Với Spring Boot hiện hành, nếu dùng `AsyncTaskExecutor` auto-configured, có thể opt-in context propagation:

```yaml
spring:
  task:
    execution:
      propagate-context: true
```

Property này giúp truyền context phù hợp qua executor do Boot quản lý. Hãy xác nhận ứng dụng thực sự sử dụng auto-configured executor đó; nếu đã khai báo executor riêng, auto-configuration có thể lùi lại.

### 8.3. Executor tự cấu hình với ContextPropagatingTaskDecorator

Nếu ứng dụng tạo executor riêng, có thể đăng ký `ContextPropagatingTaskDecorator`:

```java
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
        return executor;
    }
}
```

Decorator capture context ở thread gửi task và khôi phục trong quá trình thực thi. Nó hỗ trợ cả logging context và observation context thông qua Micrometer Context Propagation.

Việc capture/restore có chi phí nhất định. Với các task cực nhỏ hoặc thông lượng rất cao, hãy đo overhead và chỉ bật ở executor thực sự cần context.

### 8.4. Reactor context propagation

Trong reactive pipeline, context không thể được xem như ThreadLocal thông thường vì một chuỗi xử lý có thể chuyển thread. Spring Boot hỗ trợ chế độ automatic context propagation:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Khi bật, context được truyền qua Reactor operators theo cơ chế hỗ trợ của Spring/Micrometer. Nếu ứng dụng dùng mode khác hoặc thư viện reactive riêng, cần kiểm tra tương thích và viết test ở đúng pipeline.

### 8.5. Event listener bất đồng bộ trong Spring Modulith

Nếu listener xử lý event trên executor khác, trace context có thể không tiếp tục như mong đợi nếu executor không propagate context hoặc cơ chế event publication không mang context theo.

Khi log listener thiếu correlation ID:

1. Xác định listener là đồng bộ hay bất đồng bộ.
2. Xác định executor thực tế được dùng.
3. Kiểm tra context propagation ở executor/reactive boundary.
4. So sánh trace ID ở publisher và listener.
5. Kiểm tra module-entry span và invocation type nếu có.
6. Không giả định event publication counter tăng đồng nghĩa listener đã có cùng trace.

Nếu listener cố ý chạy độc lập, có thể tạo một trace mới và ghi liên kết nghiệp vụ phù hợp. Việc này phải là quyết định rõ ràng, không phải lỗi cần che bằng cách copy ID vào MDC.

## 9. Truyền baggage vào MDC khi cần

### 9.1. Baggage là context có thể lan qua dịch vụ

Micrometer Tracing cho phép tạo baggage bằng `Tracer`. Baggage có thể mang một số metadata xuyên service; một số field có thể được đưa vào MDC để log.

Ví dụ cấu hình:

```yaml
management:
  tracing:
    baggage:
      remote-fields:
        - tenant-tier
      correlation:
        fields:
          - tenant-tier
```

Với cấu hình này, field `tenant-tier` có thể được truyền qua network theo propagation support và được đưa vào logging context. Baggage field chỉ nên chứa metadata đã được allowlist, có tập giá trị kiểm soát và không nhạy cảm.

### 9.2. Brave và B3 có khác biệt

Khi dùng W3C propagation, baggage có thể được truyền theo cơ chế W3C baggage. Khi dùng B3, baggage không tự được truyền giống W3C; cần khai báo `management.tracing.baggage.remote-fields` để truyền field theo cơ chế được Spring Boot hỗ trợ.

Nếu dùng Brave, việc ghi trace/span IDs vào MDC còn liên quan đến baggage setting của tracer. Đọc tài liệu đúng version trước khi tắt baggage; một thay đổi tưởng như chỉ giảm metadata có thể làm mất log correlation.

### 9.3. Không biến baggage thành kho dữ liệu

Không đưa các dữ liệu sau vào baggage chỉ để chúng xuất hiện trong log:

- Access token, cookie, password hoặc API key.
- Email, số điện thoại, địa chỉ hoặc dữ liệu cá nhân.
- Số thẻ, payment details hoặc payload nghiệp vụ nhạy cảm.
- Order ID/customer ID có giá trị riêng cho từng request nếu không có lý do và chính sách rõ.
- Nội dung do người dùng nhập chưa được kiểm soát.

Baggage được truyền qua nhiều dịch vụ và có thể được thêm vào spans hoặc MDC. Hãy coi nó là một phần của bề mặt dữ liệu observability.

## 10. Tìm log theo correlation ID

### 10.1. Tìm toàn bộ log của trace

Khi có trace ID, tìm theo chính xác trường trace ID trong log platform. Ví dụ một truy vấn khái niệm:

```text
traceId = "4bf92f3577b34da6a3ce929d0e0e4736"
```

Nếu log lưu correlation ID gộp `traceId-spanId` thành một chuỗi, có thể tìm theo phần trace ID hoặc parse thành hai field riêng. Structured logging với `traceId` và `spanId` riêng thường dễ truy vấn hơn.

### 10.2. Tìm log của một span

Khi cần xem riêng thao tác `inventory.reserve`, lọc:

```text
traceId = "4bf92f3577b34da6a3ce929d0e0e4736"
AND spanId = "c3d4e5f6"
```

Điều này giúp thu hẹp log theo operation cụ thể. Nếu span ID được thay đổi theo từng dòng log do span scope khác nhau, một thao tác con có thể có nhiều child spans; hãy dùng trace UI để xem quan hệ chính xác.

### 10.3. Tìm request ID nghiệp vụ

Nếu hệ thống dùng request ID riêng:

```text
requestId = "req-7f2a"
```

Hãy bảo đảm request ID được truyền và ghi nhất quán qua các service cần tìm. Nếu chỉ service đầu tiên ghi request ID, truy vấn toàn hệ thống sẽ không tìm đủ kết quả. Trace ID vẫn nên được dùng cho distributed trace khi có tracing.

### 10.4. Đối chiếu log với Zipkin/trace backend

Quy trình điều tra một request:

1. Tìm log đầu tiên theo request ID hoặc trace ID.
2. Lấy trace ID đầy đủ.
3. Mở trace backend và tìm trace theo ID.
4. Đọc spans, parent-child và thời lượng.
5. Quay lại log theo trace ID để xem message/exception chi tiết.
6. Dùng module attributes để nhận diện module.
7. Nếu thiếu log của listener async, kiểm tra propagation và executor.

Logs giải thích **điều gì được ghi nhận**, traces giải thích **các bước liên kết theo thời gian**.

## 11. Kiểm soát bảo mật và chất lượng correlation IDs

### 11.1. Không log dữ liệu nhạy cảm

Correlation IDs giúp tìm dữ liệu; chúng không phải lý do để log toàn bộ request/response. Không đưa vào MDC hoặc log:

- Password, access token, refresh token, API key.
- Cookie/session secret.
- Payment card data.
- PII không cần thiết.
- Nội dung request body có thể chứa bí mật.
- Raw baggage do người dùng tự gửi mà chưa được kiểm soát.

### 11.2. Không tin correlation header tùy ý

Nếu nhận `X-Request-ID` từ client, validate độ dài và ký tự. Với hệ thống yêu cầu tin cậy cao, chỉ nhận giá trị từ gateway đáng tin hoặc tạo ID mới ở edge. Tránh cho phép header chứa ký tự điều khiển/newline có thể gây log injection.

Trace context cũng cần được xử lý theo tracing library; không tự dùng header tùy ý để ghi đè context hiện hành.

### 11.3. Cardinality và chi phí log

Trace ID/span ID là các giá trị có cardinality cao trong log, nhưng điều đó không giống metric tags. Logs được tìm kiếm theo ID là một mục đích bình thường của logging platform, song vẫn có chi phí indexing và retention.

Không đưa trace ID, span ID, request ID hoặc order ID vào **metric labels**. Metrics cần tags có tập giá trị thấp; logs/traces mới là nơi thích hợp hơn để điều tra từng hoạt động.

### 11.4. Giữ ID ổn định nhưng không dùng lại sai phạm vi

Một request ID không nên được tái sử dụng cho một request độc lập khác. Trace ID do tracer tạo/nhận theo propagation context. Không dùng lại trace ID của request cũ cho một job mới chỉ để log có vẻ liên tục.

Nếu một quy trình nghiệp vụ kéo dài qua nhiều request/event, hãy định nghĩa business correlation key riêng và ghi nó theo chính sách; không kéo dài một trace tùy tiện qua nhiều giờ/ngày nếu mô hình tracing không hỗ trợ mục đích đó.

## 12. Kiểm thử correlation ID

### 12.1. Kiểm thử filter tạo request ID

Với filter tự tạo request ID, kiểm tra các trường hợp:

| Đầu vào `X-Request-ID` | Kết quả kỳ vọng |
| --- | --- |
| Không có header | Server tạo ID mới |
| `req-123` hợp lệ | Giữ lại nếu chính sách cho phép |
| Chuỗi vượt 64 ký tự | Bỏ qua và tạo ID mới |
| Có ký tự newline/control | Bỏ qua và tạo ID mới |
| Header rỗng | Tạo ID mới |
| Hai request độc lập | Có hai request IDs khác nhau |

Test cần xác minh cả response header và MDC được dọn sau khi request kết thúc. Đừng chỉ assert ID xuất hiện ở một log mà bỏ qua trường hợp thread được tái sử dụng.

### 12.2. Kiểm tra MDC không bị rò rỉ

Một test ở cùng thread có thể đặt request ID, thực thi filter, sau đó kiểm tra MDC đã được khôi phục. Với executor, chạy hai task liên tiếp có context khác nhau và xác minh task thứ hai không nhìn thấy giá trị task thứ nhất.

Nếu dùng `ContextPropagatingTaskDecorator`, test cả hai điều:

- Task nhận đúng context được capture từ thread gửi.
- Context được khôi phục/xóa sau khi task hoàn tất.

### 12.3. Integration test với Micrometer Tracing

Để xác minh trace/span IDs xuất hiện trong log:

1. Khởi tạo Spring Boot test context với tracing support.
2. Gọi một endpoint hoặc service đã được instrument.
3. Capture log event bằng appender/test logging tool phù hợp.
4. Xác nhận MDC có trace ID/span ID hoặc log correlation field.
5. Gọi một operation con và xác nhận trace ID giữ nguyên, span ID phù hợp với span context.
6. Kiểm tra không có ID ở log ngoài request nếu không có context.

Không giả định `@SpringBootTest` luôn tự bật reporter/export. Nếu chỉ kiểm tra MDC, có thể dùng test tracer/observation handler phù hợp; nếu kiểm tra trace tới backend, cần test exporter/backend riêng.

### 12.4. Kiểm tra HTTP propagation

Dùng mock HTTP server hoặc request recorder để xác nhận HTTP client auto-configured gửi W3C `traceparent` hoặc B3 headers. Sau đó kiểm tra service nhận tạo log có cùng trace ID.

Không tự copy MDC trace ID sang header trong test vì điều đó bỏ qua cơ chế đang cần kiểm tra.

## 13. Tình huống thực tế: điều tra một đơn hàng

### 13.1. Bối cảnh

Một request đặt hàng đi qua ba module:

```text
orders
  -> inventory
  -> payments
```

Người dùng nhận thông báo lỗi “Không thể xác nhận đơn hàng”. Nhóm vận hành có request ID `req-7f2a` và trace ID `4bf92f...`.

### 13.2. Tìm log

Truy vấn theo trace ID cho thấy:

```text
[trace-A-span-1] INFO  orders.OrderManagement - Order accepted
[trace-A-span-2] INFO  inventory.InventoryOperations - Stock reserved
[trace-A-span-3] WARN  payments.PaymentService - Payment provider timeout
[trace-A-span-3] ERROR payments.PaymentService - Authorization failed
```

Log cho thấy inventory đã giữ hàng, còn payments gặp timeout. Trace UI cho biết span payments kéo dài 3.2 giây và có child HTTP client span.

### 13.3. Đối chiếu trace và module graph

- Module graph xác nhận `orders` có dependency tới `inventory` và event/listener dependency tới `payments` theo cấu trúc mã nguồn.
- Trace cho thấy một lần thực thi thực tế đã đi qua orders và inventory.
- Logs cho thấy message và exception của payments.
- Event publication counter chỉ cho biết event được công bố, không xác nhận payment listener thành công.

Nếu log payments có trace ID khác, kiểm tra listener chạy async và context propagation. Nếu log payments không có trace ID, kiểm tra MDC, executor và baggage setting trước khi thêm code tự ghi ID.

### 13.4. Kết luận điều tra

Kết luận có thể là: **request đặt hàng được tiếp nhận, inventory đã giữ hàng, bước authorize của payments timeout**. Cần dựa vào business state và retry policy để quyết định có giải phóng hàng hay thử lại. Correlation ID chỉ giúp tìm đúng bằng chứng; nó không tự quyết định trạng thái giao dịch.

## 14. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Log request không có trace ID | Tracing chưa bật, không có active span hoặc log ở ngoài scope | Dependency, sampling, observation, MDC |
| Trace UI có span nhưng log thiếu ID | Pattern không đọc MDC, logging config tùy chỉnh | `logging.pattern.correlation` và appender pattern |
| Correlation ID trống sau đổi MDC key | Pattern vẫn đọc tên key cũ | `management.tracing.mdc.*` và `%X{...}` |
| Brave không ghi IDs vào MDC | Baggage bị tắt | `management.tracing.baggage.enabled` |
| Log async không có correlation | Context không được propagate qua executor | Auto executor property hoặc TaskDecorator |
| Log reactive thiếu context | Reactor context propagation chưa bật/phù hợp | `spring.reactor.context-propagation` |
| Hai service có trace ID khác nhau | HTTP client không instrument hoặc propagation mismatch | Builder, `traceparent`, B3 headers |
| Request ID thay đổi giữa các service | Header riêng không được truyền theo hợp đồng | Gateway/client filters và allowlist |
| Log của request sau có ID request trước | MDC không được cleanup | `finally`, thread reuse, decorator |
| Tìm request ID nhưng thiếu một số logs | Chỉ một số service ghi ID | Kiểm tra propagation và field mapping |
| Có hai correlation IDs trong một log | Pattern ghi mặc định và custom field trùng | Kiểm tra logging pattern |
| Log chứa chuỗi header độc hại | Không validate request ID | Allowlist, length limit, log sanitization |
| Không thấy log trong cùng trace nhưng trace có span | Logger/appender/level hoặc log pipeline lọc mất | Log level, routing, ingestion |
| Một trace có nhiều span IDs | Bình thường: mỗi span có ID riêng | Lọc theo trace ID để xem toàn bộ trace |

### 14.1. Trình tự chẩn đoán

1. Xác nhận request thực sự có active trace.
2. Kiểm tra log raw có MDC `traceId`/`spanId` không.
3. Kiểm tra pattern có in các key đúng không.
4. Nếu dùng Brave, kiểm tra baggage enabled.
5. Nếu log trong async/reactive, kiểm tra context propagation.
6. Nếu qua HTTP, kiểm tra auto-configured client và propagation headers.
7. Nếu có request ID riêng, kiểm tra header contract và filter.
8. Đối chiếu trace backend với logs theo trace ID.
9. Kiểm tra log pipeline có parse/loại bỏ correlation field hay không.

Không sửa exporter nếu trace đã tồn tại trong backend nhưng appender không hiển thị correlation ID. Đây là hai chặng khác nhau.

## 15. Bài thực hành: bật và xác minh correlation ID

### 15.1. Bối cảnh

Ứng dụng Spring Boot có module `orders` gọi API `inventory` và phát event cho `payments`. Yêu cầu:

- Log có trace ID/span ID mặc định.
- Log có tên module ở các điểm nghiệp vụ quan trọng.
- HTTP client truyền trace context tự động.
- Async listener không mất correlation context nếu được thiết kế tiếp tục trace.
- Request ID riêng chỉ được dùng khi có nhu cầu API/support.

### 15.2. Các bước

1. Cấu hình Micrometer Tracing và backend phù hợp với Spring Boot version.
2. Gọi một endpoint đặt hàng với sampling phù hợp trong môi trường thử nghiệm.
3. Xem log đầu request, xác nhận trace ID và span ID.
4. Xem log trong `orders` và `inventory`, xác nhận trace ID giống nhau nếu cùng trace.
5. Xác nhận span ID đổi theo operation.
6. Nếu có listener async `payments`, kiểm tra trace ID và context propagation.
7. Tìm trace trong Zipkin/OTLP backend bằng trace ID.
8. Dùng log query theo trace ID để lấy toàn bộ message liên quan.
9. Kiểm tra không có order ID/email/token trong metric tags hoặc baggage ngoài chính sách.
10. Nếu có request ID riêng, xác minh header được validate, trả về và cleanup MDC.

### 15.3. Bảng kết quả mẫu

| Kiểm tra | Kỳ vọng | Trạng thái minh họa |
| --- | --- | --- |
| Log HTTP request | Có trace ID và span ID | PASS |
| Log orders | Cùng trace ID | PASS |
| Log inventory | Cùng trace ID, span ID riêng | PASS |
| Log payments listener async | Có context theo thiết kế | Cần kiểm tra |
| Trace backend | Tìm được trace theo ID | PASS |
| Request ID header | Giá trị hợp lệ và nhất quán | PASS |
| MDC cleanup | Không rò rỉ sang request khác | PASS |
| Dữ liệu nhạy cảm | Không xuất hiện trong correlation fields | PASS |

Các trạng thái chỉ là ví dụ để minh họa cách ghi kết quả. Phải thực hiện test trên ứng dụng thật trước khi kết luận.

## 16. Checklist vận hành

### Khi phát triển

- [ ] Dùng trace ID làm khóa tìm toàn bộ trace khi Micrometer Tracing đã bật.
- [ ] Hiểu span ID thay đổi theo span, không coi đó là request-wide ID.
- [ ] Dùng request ID riêng chỉ khi có hợp đồng nghiệp vụ/API rõ.
- [ ] Dùng module name/operation ổn định trong log có cấu trúc.
- [ ] Không tự ghi đè MDC traceId/spanId.
- [ ] Dùng builder auto-configured cho HTTP clients.
- [ ] Thiết lập context propagation cho executor/reactive khi cần.

### Trước production

- [ ] Logging pattern hiển thị trace ID/span ID đúng.
- [ ] MDC key names và pattern khớp nhau.
- [ ] Baggage setting không vô tình làm mất correlation.
- [ ] Request ID header được validate và giới hạn độ dài.
- [ ] MDC được cleanup trong mọi đường kết thúc.
- [ ] Async listener được kiểm tra trên executor thực tế.
- [ ] Không log PII, secrets hoặc raw payload không cần thiết.
- [ ] Log platform parse được correlation fields.
- [ ] Có runbook tìm log theo trace ID và mở trace backend.

### Khi điều tra sự cố

- [ ] Ghi trace ID đầy đủ, không chỉ span ID.
- [ ] Lọc logs theo trace ID trước, sau đó thu hẹp bằng span ID.
- [ ] Mở trace và đối chiếu timestamps/parent-child.
- [ ] Dùng module attributes để xác định ranh giới.
- [ ] Kiểm tra listener async nếu trace bị tách.
- [ ] Phân biệt event publication với listener outcome.
- [ ] Ghi lại kết luận dựa trên log, trace và business state.

## 17. Những hiểu lầm cần tránh

1. **Correlation ID luôn là request ID.** Trong Spring Boot tracing, correlation ID mặc định thường được tạo từ trace ID và span ID.
2. **Trace ID và span ID giống nhau.** Trace ID chung cho trace; mỗi span có ID riêng.
3. **Chỉ cần thêm `%X{traceId}` vào pattern là tracing hoạt động.** Pattern chỉ đọc MDC; tracer vẫn phải tạo và đưa context vào MDC.
4. **MDC tự truyền qua mọi thread.** MDC thường gắn với thread; async/reactive cần context propagation.
5. **Tự copy trace ID vào HTTP header là cách propagation chuẩn.** Dùng HTTP client builder auto-configured và W3C/B3 propagation.
6. **Request ID riêng tự động có trên service khác.** Phải có hợp đồng truyền header hoặc cơ chế context riêng.
7. **Baggage có thể chứa mọi dữ liệu.** Baggage lan qua hệ thống và có thể xuất hiện trong log/span.
8. **Tắt baggage không ảnh hưởng log correlation khi dùng Brave.** Với Brave, setting này có thể khiến trace/span IDs không còn được ghi vào MDC theo mặc định.
9. **Mọi log đều phải có trace ID.** Startup, scheduled jobs và hoạt động ngoài trace có thể không có.
10. **Một trace chỉ có một span ID.** Mỗi span có span ID riêng; lọc toàn bộ luồng bằng trace ID.
11. **Đưa trace ID vào metric tag giúp truy vấn dễ hơn.** Điều đó làm cardinality metrics tăng mạnh; dùng logs/traces cho ID riêng.
12. **Có correlation ID đồng nghĩa nghiệp vụ thành công.** ID chỉ liên kết bằng chứng, không chứng minh transaction đã commit hay listener đã xử lý.

## 18. Câu hỏi tự đánh giá

1. Correlation ID là gì và tại sao nó không nhất thiết là một loại ID cố định?
2. Trace ID và span ID khác nhau như thế nào?
3. Vì sao Spring Boot có thể tự đưa trace/span IDs vào log khi Micrometer Tracing được cấu hình?
4. MDC lưu dữ liệu theo cơ chế nào và vì sao thread pool có thể làm mất context?
5. `logging.pattern.correlation` có vai trò gì?
6. Khi đổi `management.tracing.mdc.trace-id-key`, log pattern cần thay đổi thế nào?
7. Vì sao cấu hình `management.tracing.baggage.enabled=false` có thể ảnh hưởng log correlation với Brave?
8. Khi nào nên tạo request ID riêng thay vì chỉ dùng trace ID?
9. Vì sao request ID từ client cần được validate trước khi đưa vào MDC?
10. Cần làm gì để MDC không rò rỉ request ID sang request tiếp theo?
11. Vì sao dùng `RestClient.Builder`/`WebClient.Builder` do Boot cấu hình quan trọng cho trace propagation?
12. `ContextPropagatingTaskDecorator` giải quyết vấn đề gì?
13. Correlation fields trong baggage cần được chọn theo nguyên tắc nào?
14. Khi một trace có nhiều span IDs, nên tìm log toàn bộ request theo trường nào?
15. Correlation ID có chứng minh listener đã xử lý thành công hoặc transaction đã commit không?
16. Làm thế nào kết hợp log, trace và module graph để điều tra một lỗi xuyên module?

## 19. Tài liệu tham khảo chính thức

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): logging correlation IDs, MDC keys, `logging.pattern.correlation`, HTTP trace propagation và baggage.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): context propagation qua thread và reactive pipeline.
- [Spring Boot — Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): AsyncTaskExecutor và cấu hình executor.
- [Spring Framework — ContextPropagatingTaskDecorator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): capture/restore context cho task.
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/): tracer, baggage và propagation.
- [SLF4J — MDC](https://www.slf4j.org/manual.html#mdc): logging context map và cách sử dụng MDC.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): chuẩn `traceparent`/`tracestate` cho distributed tracing.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module-entry observability và metadata module.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình logging pattern và logging framework.

> **Ghi nhớ:** Correlation ID giúp tìm đúng log; với Micrometer Tracing, Spring Boot mặc định dùng **trace ID + span ID trong MDC** để liên kết log với spans. Dùng trace ID để tìm toàn bộ luồng, span ID để thu hẹp một thao tác, và chỉ tạo request ID riêng khi có hợp đồng rõ ràng. Hãy giữ MDC đúng vòng đời, truyền context qua HTTP/async/reactive bằng cơ chế được hỗ trợ, bảo vệ dữ liệu và đối chiếu logs với trace/module metadata khi điều tra sự cố.
