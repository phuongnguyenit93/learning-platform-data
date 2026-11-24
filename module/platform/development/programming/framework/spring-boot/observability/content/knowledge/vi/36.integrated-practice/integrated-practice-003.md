# Gắn correlation ID vào log

Khi một request đi qua nhiều lớp trong ứng dụng Spring Boot, log thường được ghi từ controller, service, repository và các thành phần gọi ra bên ngoài. Nếu mỗi dòng log không mang một định danh chung, người vận hành phải tìm theo timestamp, nội dung hoặc thread và rất dễ ghép nhầm các request chạy đồng thời. Correlation ID giải quyết vấn đề đó bằng cách gắn một mã nhận diện xuyên suốt vòng đời xử lý để các dòng log liên quan có thể được truy vấn cùng nhau.

Trong bài thực hành này, ta tạo hoặc tiếp nhận correlation ID ở request đầu vào, đưa giá trị vào MDC để logger ghi tự động, trả ID về client, truyền ID qua lời gọi HTTP và bảo đảm context được dọn khỏi thread sau khi xử lý. Bài cũng phân biệt correlation ID với trace ID của distributed tracing, vì hai giá trị này có mục đích liên quan nhưng không hoàn toàn thay thế cho nhau.

## 1. Correlation ID là gì?

Correlation ID là một định danh được gắn với một request hoặc một luồng công việc để liên kết các sự kiện phát sinh trong quá trình xử lý. Ví dụ, gateway nhận request đặt hàng với `X-Correlation-ID: order-req-42`; Order Service, Inventory Service và Payment Service có thể ghi cùng ID này vào log. Khi cần điều tra, đội vận hành tìm `order-req-42` để xem các log thuộc cùng hành trình.

Correlation ID thường được truyền qua:

- HTTP request và response headers.
- Lời gọi HTTP/gRPC giữa các service.
- Message headers khi publish và consume event.
- MDC của logging framework trong phạm vi xử lý hiện tại.
- Context của executor hoặc tác vụ bất đồng bộ khi công việc tiếp tục ở thread khác.

Một correlation ID nên ổn định trong phạm vi hành trình cần điều tra. Nếu mỗi service tự sinh một ID mới, các log sẽ không còn liên kết được với nhau. Điểm vào đáng tin cậy như API gateway hoặc service đầu tiên sẽ tiếp nhận ID hợp lệ hoặc sinh ID mới rồi chuyển tiếp.

## 2. Phân biệt correlation ID với trace ID

Correlation ID và trace ID đều giúp tìm các sự kiện liên quan, nhưng chúng có nguồn gốc và phạm vi khác nhau.

| Thuộc tính | Correlation ID | Trace ID |
|---|---|---|
| Mục đích | Gom log và sự kiện theo request/công việc | Liên kết các span thành một distributed trace |
| Nguồn tạo | Gateway, ứng dụng hoặc hệ thống gọi | Tracing SDK/bridge theo trace context |
| Cách truyền | Header hoặc message metadata do ứng dụng quy định | W3C Trace Context hoặc propagator tương ứng |
| Phạm vi | Theo quy ước của hệ thống, có thể vượt qua nhiều bước nghiệp vụ | Theo vòng đời trace được tracing system xác định |
| Thông tin đi kèm | Thường là một ID đơn giản | Trace ID, span ID, trace flags và quan hệ span |
| Khả năng quan sát | Tìm các log có cùng ID | Xem cây span, quan hệ parent-child, duration và trạng thái lỗi |

Nếu Micrometer Tracing đã được bật, trace ID và span ID thường có thể được đưa vào log correlation tự động. Với một hệ thống đã có distributed tracing đầy đủ, trace ID có thể đáp ứng phần lớn nhu cầu liên kết log của một request. Correlation ID riêng vẫn hữu ích khi cần giữ mã ticket/request do gateway, đối tác hoặc hệ thống nghiệp vụ cấp, hoặc khi muốn liên kết log ở những luồng chưa có trace.

Không nên tự ghi đè `traceparent` hay tự tạo trace ID để thay cho tracing instrumentation. Hãy để Micrometer Tracing hoặc OpenTelemetry quản lý trace context; correlation ID riêng chỉ là metadata bổ sung.

## 3. Đưa correlation ID vào MDC

MDC (Mapped Diagnostic Context) là vùng dữ liệu theo thread được các logging framework như Logback hỗ trợ. Khi đặt correlation ID vào MDC, log pattern có thể đọc giá trị này và tự thêm vào mỗi dòng log mà không cần truyền tham số ID qua mọi lời gọi logger.

Với ứng dụng Spring Boot dùng Spring MVC và servlet container, có thể dùng `OncePerRequestFilter` để thiết lập MDC ở đầu request và dọn dẹp trong `finally`.

Các ví dụ filter dưới đây dùng Spring MVC/Servlet và `jakarta.servlet` (Spring Boot 3 trở lên). Nếu ứng dụng dùng WebFlux, áp dụng Reactor Context thay vì đăng ký servlet filter.

### 3.1. Tạo filter nhận diện request

Ví dụ dưới đây dùng header `X-Correlation-ID`. ID được chấp nhận khi chỉ gồm chữ, số, dấu chấm, gạch dưới hoặc gạch ngang và có độ dài tối đa 64 ký tự. Nếu header vắng mặt hoặc không hợp lệ, ứng dụng sinh UUID mới. Việc giới hạn ký tự cũng ngăn newline và ký tự điều khiển lọt vào log.

```java
package com.example.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Correlation-ID";
    public static final String MDC_KEY = "correlationId";

    private static final Pattern VALID_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String correlationId = resolve(request.getHeader(HEADER_NAME));
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER_NAME, correlationId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            // Servlet container tái sử dụng thread cho request tiếp theo.
            // Luôn xóa giá trị để tránh log của request sau nhận nhầm ID.
            MDC.remove(MDC_KEY);
        }
    }

    private String resolve(String candidate) {
        if (candidate != null && VALID_ID.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }
}
```

Filter thực hiện bốn việc theo thứ tự:

1. Đọc `X-Correlation-ID` từ request.
2. Kiểm tra định dạng và sinh UUID nếu cần.
3. Đưa ID vào MDC và trả ID trong response header.
4. Chạy phần còn lại của filter chain rồi xóa MDC dù request thành công hay ném exception.

`OncePerRequestFilter` giúp filter không chạy lặp ngoài ý muốn trong cùng một dispatch thông thường. Với async dispatch hoặc các luồng xử lý tiếp tục trên thread khác, cần thiết kế truyền context riêng như phần 7; MDC của thread ban đầu không tự đi theo công việc.

### 3.2. Vì sao phải dọn MDC trong finally?

Servlet container thường dùng thread pool. Một thread có thể xử lý request A rồi được tái sử dụng cho request B. MDC dựa trên thread-local; nếu không xóa ID của A, log của B có thể mang sai correlation ID. Đây là lỗi rò rỉ context và có thể dẫn đến điều tra nhầm hoặc tiết lộ thông tin giữa các request.

Đặt `MDC.remove` trong `finally` bảo đảm dọn dẹp ngay cả khi controller hoặc service ném exception. Không chỉ xóa ở nhánh thành công và không giữ MDC bằng cách đặt một giá trị mặc định cho toàn bộ thread.

## 4. Cấu hình log pattern

Sau khi filter ghi ID vào MDC, cấu hình Logback để in giá trị `correlationId` ở mỗi dòng log. Ví dụ trong `application.yml`:

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level [corr=%X{correlationId:-}] [trace=%X{traceId:-} span=%X{spanId:-}] %logger{36} - %msg%n"
```

Các biểu thức `%X{...}` đọc giá trị từ MDC. Nếu ứng dụng chưa bật tracing, `traceId` và `spanId` có thể trống; correlation ID vẫn hoạt động độc lập. Nếu Micrometer Tracing được cấu hình, các khóa trace thường được bridge đưa vào MDC theo cấu hình logging của phiên bản đang dùng.

Ví dụ log sau khi gọi endpoint:

```text
2026-11-22T14:30:00.123+07:00 INFO  [corr=order-req-42] [trace=4bf92f3577b34da6a3ce929d0e0e4736 span=00f067aa0ba902b7] OrderController - Creating order
2026-11-22T14:30:00.145+07:00 INFO  [corr=order-req-42] [trace=4bf92f3577b34da6a3ce929d0e0e4736 span=00f067aa0ba902b7] OrderService - Reserving inventory
```

Nếu dùng JSON logging, đưa `correlationId` thành một field riêng thay vì chỉ ghép vào message. Field có cấu trúc giúp hệ thống log truy vấn chính xác và tránh phải parse chuỗi.

Nếu client là JavaScript chạy trên trình duyệt và cần đọc response header, cấu hình CORS để expose `X-Correlation-ID` cho origin được phép. Nếu không, trình duyệt có thể nhận response nhưng không cho JavaScript truy cập header này.

## 5. Truyền correlation ID qua lời gọi HTTP

Filter chỉ thiết lập MDC trong service nhận request. Khi service gọi một service khác, cần chuyển correlation ID sang outbound request. Với Spring Boot và Spring Framework hỗ trợ `RestClient`, có thể thêm `ClientHttpRequestInterceptor` vào builder được Spring Boot inject.

`RestClient` có từ Spring Framework 6.1 (được hỗ trợ trong Spring Boot 3.2 trở lên). Với phiên bản cũ hơn, dùng `RestTemplate` và interceptor tương ứng.

```java
package com.example.observability;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://localhost:8081")
                .requestInterceptor((request, body, execution) -> {
                    String correlationId = MDC.get(CorrelationIdFilter.MDC_KEY);
                    if (correlationId != null) {
                        request.getHeaders().set(
                                CorrelationIdFilter.HEADER_NAME, correlationId);
                    }
                    return execution.execute(request, body);
                })
                .build();
    }
}
```

Sử dụng builder được Spring Boot cấu hình giúp giữ các customizer và instrumentation mà framework đã đăng ký. Tránh tạo client bằng `RestClient.create()` một cách tùy tiện nếu cần giữ cấu hình quan sát tự động của ứng dụng. Interceptor ở trên chỉ truyền correlation ID riêng; trace context như `traceparent` vẫn do Micrometer Tracing/HTTP instrumentation xử lý.

Ở service đích, `CorrelationIdFilter` đọc lại header và đặt cùng ID vào MDC. Như vậy log của cả service gọi và service nhận đều có cùng correlation ID. Trong môi trường thật, `baseUrl` nên được externalize qua cấu hình và service discovery.

Khi gọi client đã cấu hình, ứng dụng sử dụng nó như một `RestClient` bình thường:

```java
InventoryResponse reserve(ReservationRequest request) {
    return inventoryRestClient.post()
            .uri("/inventory/reservations")
            .body(request)
            .retrieve()
            .body(InventoryResponse.class);
}
```

Nếu dùng `RestTemplate`, có thể áp dụng `ClientHttpRequestInterceptor` tương tự. Với `WebClient` hoặc Spring WebFlux, không nên dựa trực tiếp vào MDC/ThreadLocal vì reactive pipeline có thể đổi thread; xem phần 7.

## 6. Truyền correlation ID qua message broker

Với tác vụ bất đồng bộ, producer cần ghi correlation ID vào message header. Consumer đọc header, đưa ID vào MDC trong phạm vi xử lý và xóa nó sau khi hoàn thành.

Ví dụ ở mức Spring Messaging:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.messaging.Message;

public class BillingConsumer {

    private static final Logger log = LoggerFactory.getLogger(BillingConsumer.class);
    private final BillingService billingService;

    public BillingConsumer(BillingService billingService) {
        this.billingService = billingService;
    }

    public void handle(Message<OrderCreated> message) {
        Object value = message.getHeaders().get(CorrelationIdFilter.HEADER_NAME);
        String correlationId = value instanceof String id ? id : null;

        if (correlationId == null || !correlationId.matches(
                "[A-Za-z0-9][A-Za-z0-9._-]{0,63}")) {
            correlationId = java.util.UUID.randomUUID().toString();
        }

        MDC.put(CorrelationIdFilter.MDC_KEY, correlationId);
        try {
            log.info("Processing order-created event");
            billingService.process(message.getPayload());
        } finally {
            MDC.remove(CorrelationIdFilter.MDC_KEY);
        }
    }
}
```

Đây là ví dụ minh họa cho consumer dùng Spring Messaging; API đọc header có thể khác giữa Spring Kafka, AMQP hoặc broker client cụ thể. Ở producer, đặt cùng header vào message trước khi publish. Cần thống nhất tên header và quy tắc xác thực ở cả hai phía.

Ví dụ tạo message ở producer:

```java
import org.slf4j.MDC;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

String correlationId = MDC.get(CorrelationIdFilter.MDC_KEY);
Message<OrderCreated> message = MessageBuilder.withPayload(event)
        .setHeader(CorrelationIdFilter.HEADER_NAME, correlationId)
        .build();
messagePublisher.publish(message);
```

Trong code thực tế, chỉ thêm header khi `correlationId` khác `null`, hoặc bảo đảm producer luôn chạy trong context đã được thiết lập. `OrderCreated` và `messagePublisher` đại diện cho kiểu event và adapter broker của ứng dụng.

Correlation ID cho phép gom log của producer và consumer dù chúng chạy ở thời điểm khác nhau. Nếu message được retry, redeliver hoặc chuyển vào dead-letter queue, giữ ID gốc giúp lần theo nguồn phát sinh. Có thể bổ sung một `deliveryAttempt` hoặc message ID riêng để phân biệt từng lần giao nhận; không thay correlation ID mỗi lần retry.

Với distributed tracing qua messaging, trace context cần được inject/extract theo propagator riêng. Correlation ID không thay thế các header tracing tiêu chuẩn.

## 7. Context trong tác vụ bất đồng bộ

MDC không tự truyền từ thread gọi sang thread worker. Khi dùng `@Async`, `ExecutorService` hoặc thread pool, cần copy context vào tác vụ và khôi phục trạng thái thread sau khi chạy.

### 7.1. Dùng TaskDecorator cho Spring Task Executor

`TaskDecorator` cho phép bọc `Runnable` trước khi executor thực thi. Ví dụ:

Decorator này truyền các giá trị MDC như `correlationId`. Nó không thay thế việc truyền span context của Micrometer Tracing; với distributed tracing, cần bật cơ chế context propagation tương ứng của stack.

```java
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

import java.util.Map;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> callerContext = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> workerPreviousContext = MDC.getCopyOfContextMap();
            try {
                if (callerContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(callerContext);
                }
                task.run();
            } finally {
                if (workerPreviousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(workerPreviousContext);
                }
            }
        };
    }
}
```

Gắn decorator vào executor thực sự được ứng dụng sử dụng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-");
        executor.setTaskDecorator(new MdcTaskDecorator());
        return executor;
    }
}
```

`MdcTaskDecorator` ở ví dụ trước là lớp thực hiện việc copy và khôi phục MDC. Bean executor ở trên được Spring quản lý vòng đời; không cần gọi `initialize()` thủ công. Chỉ định rõ executor khi dùng `@Async`:

```java
@Async("applicationTaskExecutor")
public void sendOrderNotification(String orderId) {
    log.info("Sending notification for order {}", orderId);
}
```

Nếu ứng dụng dùng nhiều executor, phải gắn decorator vào từng executor liên quan. Không giả định cấu hình trên tự áp dụng cho mọi thread pool do thư viện khác tạo ra. Với tác vụ có vòng đời dài, chỉ truyền các key cần thiết và không copy dữ liệu nhạy cảm vào context.

### 7.2. Spring WebFlux và Reactor

Trong WebFlux, một request có thể đi qua nhiều thread trong cùng reactive pipeline. MDC dựa trên ThreadLocal nên cách đặt MDC trong servlet filter không đủ để bảo đảm correlation xuyên suốt. Dùng Reactor Context cùng cơ chế Micrometer Context Propagation được hỗ trợ trong phiên bản Spring Boot/Micrometer đang dùng; chỉ bridge sang MDC ở ranh giới logging phù hợp. Không gọi `MDC.put` trong một operator rồi giả định giá trị còn tồn tại ở operator chạy trên thread khác.

## 8. Kiểm thử correlation ID

Kiểm thử cần xác nhận cả việc tạo ID, giữ ID hợp lệ, truyền sang service khác và dọn context.

### 8.1. Gọi endpoint với ID do client gửi

Giả sử ứng dụng có endpoint `GET /api/orders`. Gửi request:

```bash
curl -i -H "X-Correlation-ID: order-req-42" \
  http://localhost:8080/api/orders
```

Kết quả mong đợi:

- Response có header `X-Correlation-ID: order-req-42`.
- Mọi log phát sinh trong request có `corr=order-req-42`.
- Nếu service gọi tiếp một service khác, outbound request có cùng header.
- Log ở service nhận cũng hiển thị `corr=order-req-42`.

### 8.2. Gọi request không có ID

```bash
curl -i http://localhost:8080/api/orders
```

Response phải có một UUID mới trong `X-Correlation-ID`. Các dòng log của request đó dùng cùng UUID. Gọi lần nữa sẽ nhận ID khác.

### 8.3. Gửi ID không hợp lệ

Thử một giá trị có khoảng trắng, ký tự điều khiển hoặc dài hơn giới hạn. Filter phải tạo ID mới (hoặc trả lỗi theo chính sách API đã chọn), và không ghi nguyên giá trị không hợp lệ vào log. Không echo header không được xác thực trở lại client.

### 8.4. Kiểm thử bằng MockMvc

Ví dụ kiểm tra ID được giữ và trả về:

```java
mockMvc.perform(get("/api/orders")
        .header(CorrelationIdFilter.HEADER_NAME, "order-req-42"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        CorrelationIdFilter.HEADER_NAME, "order-req-42"));
```

Thêm test cho request không có header và header sai định dạng. Với test chạy trên cùng thread, có thể xác minh `MDC.get(CorrelationIdFilter.MDC_KEY)` là `null` sau khi request kết thúc để phát hiện context bị rò rỉ. Test outbound cần kiểm tra request mà client gửi sang service giả lập có đúng header hay không.

## 9. Truy vấn log theo correlation ID

Khi log được xuất dưới dạng text, có thể tìm chuỗi ID bằng công cụ tìm kiếm log hoặc lệnh dòng lệnh. Với JSON logging, truy vấn theo field chính xác sẽ hiệu quả hơn.

Ví dụ truy vấn logic trong log backend:

```text
correlationId = "order-req-42"
```

Một quy trình điều tra thường là:

1. Tìm tất cả log có correlation ID.
2. Sắp xếp theo timestamp và phân nhóm theo `service.name`.
3. Tìm log đầu tiên báo lỗi hoặc có độ trễ bất thường.
4. Nếu có trace ID, mở trace tương ứng để xem span và dependency.
5. Đối chiếu request ID, message ID hoặc business ID khi cần xác định bước nghiệp vụ.

Correlation ID giúp tìm log; trace giúp hiểu quan hệ và thời gian giữa các thao tác. Kết hợp hai loại dữ liệu giúp điều tra nhanh hơn.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| Log không có correlation ID | Filter chưa đăng ký, thứ tự filter sai hoặc log pattern thiếu `%X` | Kiểm tra filter chain, MDC key và cấu hình Logback |
| Mỗi service có ID khác nhau | Outbound client không truyền header hoặc service đích không đọc header | Kiểm tra interceptor và inbound filter |
| Log của request sau mang ID request trước | Không xóa MDC trong `finally` | Dọn MDC ở mọi đường kết thúc và kiểm thử thread reuse |
| Controller có ID nhưng `@Async` không có | MDC không tự truyền qua thread pool | Gắn `TaskDecorator` vào executor sử dụng |
| WebFlux lúc có lúc không có ID | ThreadLocal/MDC không phù hợp với reactive context | Dùng Reactor Context và Micrometer Context Propagation |
| Trace ID có nhưng correlation ID không có | Chưa cài filter riêng hoặc chưa đưa ID vào pattern | Xác định có cần ID riêng; nếu có, thêm filter và propagation |
| Correlation ID có nhưng không tìm được trace | Tracing chưa bật, sampling bỏ trace hoặc propagation trace lỗi | Kiểm tra trace exporter, sampling và `traceparent` |
| Log chứa ID rất dài hoặc ký tự lạ | Không validate header đầu vào | Giới hạn độ dài, allowlist ký tự và sinh ID mới khi không hợp lệ |
| Tìm log trả về quá nhiều kết quả | Client tái sử dụng một ID cho nhiều request không liên quan | Quy định phạm vi duy nhất và cách gateway tạo ID |

## 11. Nguyên tắc bảo mật và vận hành

Correlation ID thường được gửi qua header do client kiểm soát, vì vậy không được xem nó là dữ liệu đáng tin cậy. Hãy kiểm tra độ dài, ký tự và định dạng; giới hạn ID để tránh log injection hoặc log flooding. Nếu hệ thống yêu cầu ID có định dạng UUID, hãy xác thực đúng định dạng đó. Nếu cần giữ ID từ đối tác, dùng allowlist quy tắc phù hợp và có thể ghi nhận ID nội bộ riêng khi ID ngoài không hợp lệ.

Không đưa correlation ID vào metric tag. Mỗi request thường có ID khác nhau; dùng ID này làm tag sẽ tạo cardinality gần bằng số request và làm tăng mạnh chi phí metrics. Correlation ID phù hợp với logs và có thể xuất hiện trong trace attributes khi có lý do, nhưng phải cân nhắc quyền riêng tư và retention.

Không dùng correlation ID để xác thực, phân quyền hoặc chứng minh một request đã được xử lý. ID chỉ là khóa tra cứu. Quyền truy cập phải dựa trên cơ chế authentication/authorization; chống gửi lặp phải dùng idempotency key hoặc cơ chế nghiệp vụ phù hợp.

Trong hệ thống nhiều service, cần thống nhất tên header, quy tắc sinh ID, giới hạn định dạng và trách nhiệm truyền tiếp. Gateway nên là điểm chuẩn hóa đầu vào; các service nội bộ phải giữ nguyên ID hợp lệ trong cùng hành trình. Nếu request tạo ra một workflow kéo dài nhiều giờ hoặc nhiều ngày, cân nhắc dùng workflow ID/business correlation key riêng thay vì giữ nguyên một request ID cho toàn bộ vòng đời nghiệp vụ.

## 12. Checklist hoàn thành bài thực hành

- [ ] Request có `X-Correlation-ID` hợp lệ được giữ nguyên.
- [ ] Request thiếu hoặc có ID không hợp lệ được sinh ID mới theo quy tắc.
- [ ] Response trả lại correlation ID để client hỗ trợ tra cứu.
- [ ] MDC được thiết lập trước khi code xử lý request ghi log.
- [ ] Log pattern hiển thị correlation ID ở mọi dòng liên quan.
- [ ] MDC luôn được dọn trong `finally` sau request.
- [ ] HTTP client truyền ID sang service tiếp theo.
- [ ] Message producer/consumer giữ ID qua message headers nếu có messaging.
- [ ] Executor bất đồng bộ truyền và khôi phục MDC đúng cách.
- [ ] WebFlux dùng Reactor Context/Micrometer Context Propagation thay cho giả định ThreadLocal.
- [ ] Trace ID/span ID vẫn do tracing instrumentation quản lý.
- [ ] Không đưa correlation ID vào metric tags hoặc dùng nó cho mục đích bảo mật.

Khi các bước trên hoạt động, một correlation ID có thể dẫn người vận hành từ log ở gateway đến log của các service phía sau và các tác vụ bất đồng bộ liên quan. Khi distributed tracing được bật, trace ID và span ID bổ sung cấu trúc thời gian và quan hệ giữa các thao tác; correlation ID tiếp tục đóng vai trò khóa tra cứu ổn định theo quy ước của hệ thống.
