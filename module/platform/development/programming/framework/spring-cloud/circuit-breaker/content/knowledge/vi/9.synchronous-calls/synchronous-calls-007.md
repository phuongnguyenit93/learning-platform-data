# Bảo toàn ngữ cảnh log, tracing và thông tin xác thực

Một lời gọi đồng bộ qua Spring Cloud CircuitBreaker thường bắt đầu trong quá trình xử lý một HTTP request, sau đó gọi đến dịch vụ phụ thuộc như Inventory hoặc Payment. Trong suốt luồng này, ứng dụng cần giữ được thông tin để trả lời ba câu hỏi: request nào đang được xử lý, lời gọi đã đi qua những dịch vụ nào và lời gọi đang thực hiện dưới danh tính nào.

Ba nhóm thông tin đó thường được gọi là ngữ cảnh (context):

- **Ngữ cảnh log:** correlation ID, request ID và các trường MDC giúp ghép các dòng log thuộc cùng một request.
- **Ngữ cảnh tracing:** trace ID, span ID và quan hệ giữa các span để theo dõi đường đi của request qua nhiều dịch vụ.
- **Ngữ cảnh xác thực:** Authentication, SecurityContext và thông tin OAuth2 cần thiết để dịch vụ đích xác định caller có quyền thực hiện thao tác hay không.

Khi lời gọi vẫn chạy đồng bộ trên cùng một thread, các cơ chế dựa trên ThreadLocal như MDC và SecurityContextHolder thường tiếp tục có giá trị. Tuy nhiên, thread pool bulkhead, executor hoặc một ranh giới bất đồng bộ có thể chuyển công việc sang thread khác. Khi đó, context không tự động đi theo nếu ứng dụng chưa cấu hình cơ chế truyền context phù hợp.

Bài học trình bày cách bảo toàn ba nhóm ngữ cảnh khi gọi đồng bộ bằng Spring Cloud CircuitBreaker và Resilience4j, cách truyền correlation ID đến dịch vụ phụ thuộc, cách để Micrometer Tracing tạo span và truyền trace context, cũng như cách chuyển thông tin xác thực có kiểm soát.

## 1. Một request mang theo những ngữ cảnh nào?

Giả sử người dùng gọi API xem tồn kho. API của Order gọi Inventory qua Circuit Breaker. Khi Inventory trả lỗi, Order có thể chạy fallback. Người vận hành cần tìm toàn bộ log của request, xem span gọi Inventory và biết request được thực hiện bằng danh tính người dùng hay danh tính dịch vụ.

| Loại ngữ cảnh | Ví dụ | Mục đích |
| --- | --- | --- |
| Correlation ID | X-Correlation-ID: req-7f2a | Tìm các log thuộc cùng một request qua nhiều dịch vụ. |
| Trace context | traceparent, trace ID, span ID | Xem quan hệ cha-con giữa các thao tác trong distributed trace. |
| Authentication | JWT, OAuth2 access token, service identity | Xác định caller và quyền mà dịch vụ đích cần kiểm tra. |
| Business context | Mã đơn hàng, tenant ID, mã giao dịch | Hỗ trợ chẩn đoán theo nghiệp vụ nếu dữ liệu được phép ghi nhận. |

Không phải mọi thông tin đều nên đưa vào log hoặc HTTP header. Access token, refresh token, mật khẩu, cookie phiên và dữ liệu cá nhân nhạy cảm không được ghi log. Tenant ID hoặc mã giao dịch cũng cần được kiểm tra theo chính sách dữ liệu của hệ thống.

Correlation ID và trace ID có mục đích gần nhau nhưng không thay thế nhau. Correlation ID thường do ứng dụng hoặc gateway tạo để liên kết log theo nghiệp vụ. Trace ID thuộc mô hình tracing, có span và quan hệ thời gian giữa các thao tác. Một request có thể mang cả hai.

## 2. Luồng đồng bộ và ranh giới thread

Một lời gọi đồng bộ cơ bản có thể được biểu diễn như sau:

~~~text
HTTP request
    |
    v
Servlet filter
  - xác định correlation ID
  - thiết lập SecurityContext
  - tạo trace/span cho request
    |
    v
Controller / Service
    |
    v
Spring Cloud CircuitBreaker
    |
    v
RestClient
    |
    v
Inventory service
~~~

Nếu các bước chạy trên cùng một thread, MDC và SecurityContextHolder dựa trên ThreadLocal có thể được đọc ở các bước tiếp theo. Micrometer Tracing duy trì current span trong execution context và tích hợp với các HTTP client đã được instrument để tạo span con, truyền trace context sang dịch vụ đích.

Tuy nhiên, cần xem xét loại bulkhead và executor đang dùng:

- **Không dùng thread pool bulkhead:** lời gọi đồng bộ thường chạy trên thread hiện tại.
- **Semaphore bulkhead:** giới hạn số lời gọi đồng thời nhưng thực thi supplier trên thread gọi.
- **Thread pool bulkhead:** đưa công việc vào thread của pool. MDC, SecurityContext và các ThreadLocal khác không tự được sao chép sang thread này nếu chưa cấu hình context propagation.
- **Executor hoặc tác vụ bất đồng bộ:** có cùng vấn đề khi chuyển công việc sang thread khác.

Vì vậy, không nên chỉ dựa vào chữ “đồng bộ” trong chữ ký phương thức để kết luận context chắc chắn được giữ. Hãy xác định chính xác đường thực thi có chuyển thread hay không.

## 3. Thiết lập correlation ID và MDC

MDC (Mapped Diagnostic Context) cho phép gắn các trường dữ liệu vào log của thread hiện tại. Với SLF4J, có thể dùng MDC.put, MDC.get và MDC.remove.

Một servlet filter có thể nhận correlation ID từ request, kiểm tra định dạng và đặt vào MDC trong thời gian xử lý:

~~~java
package com.example.order.logging;

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
public class CorrelationIdFilter extends OncePerRequestFilter {

    private static final String HEADER = "X-Correlation-ID";
    private static final String MDC_KEY = "correlationId";
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String incomingId = request.getHeader(HEADER);
        String correlationId = incomingId != null
                && SAFE_ID.matcher(incomingId).matches()
            ? incomingId
            : UUID.randomUUID().toString();

        String previousValue = MDC.get(MDC_KEY);
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER, correlationId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            if (previousValue == null) {
                MDC.remove(MDC_KEY);
            } else {
                MDC.put(MDC_KEY, previousValue);
            }
        }
    }
}
~~~

Filter chỉ chấp nhận ID có ký tự và độ dài cho phép. Điều này tránh đưa chuỗi tùy ý có ký tự xuống dòng vào log. Nếu hệ thống có gateway đáng tin cậy tạo correlation ID, có thể xác định rõ gateway nào được phép cung cấp giá trị này.

Phần finally rất quan trọng. Servlet container tái sử dụng thread cho nhiều request. Nếu không xóa hoặc khôi phục MDC, request tiếp theo có thể ghi log với correlation ID của request trước.

Có thể đưa correlation ID và trace ID vào log pattern trong application.yml:

~~~yaml
logging:
  pattern:
    level: "%5p [corr:%X{correlationId:-}] [trace:%X{traceId:-} span:%X{spanId:-}]"
~~~

Khi Micrometer Tracing được tích hợp với logging, các trường trace ID và span ID thường được đưa vào MDC. Nếu chưa bật tracing, phần trace có thể để trống; correlation ID vẫn hoạt động độc lập.

## 4. Truyền correlation ID qua RestClient

MDC chỉ tồn tại trong context của thread hiện tại. Để dịch vụ Inventory nhận được correlation ID, caller cần đưa giá trị này vào HTTP header của request đi ra.

Với Spring Boot, nên dùng RestClient.Builder được Spring quản lý để giữ các tích hợp observation và tracing tự động. Có thể thêm một ClientHttpRequestInterceptor để truyền correlation ID:

~~~java
package com.example.order.inventory;

import org.slf4j.MDC;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder) {

        return builder
            .baseUrl("http://localhost:8081")
            .requestInterceptor((request, body, execution) -> {
                String correlationId = MDC.get("correlationId");

                if (correlationId != null) {
                    request.getHeaders().set(
                        "X-Correlation-ID",
                        correlationId
                    );
                }

                return execution.execute(request, body);
            })
            .build();
    }
}
~~~

Dịch vụ Inventory có thể dùng filter tương tự để đặt correlation ID vào MDC của chính nó. Khi đó log của Order và Inventory có thể được tìm theo cùng một ID.

Không nên tạo correlation ID mới ở mỗi tầng nếu mục tiêu là liên kết cùng một request. Nếu request đi vào không có ID hợp lệ, tầng đầu tiên tạo ID và các tầng sau tiếp tục truyền ID đó. Nếu cần phân biệt từng lần retry, có thể bổ sung attempt number riêng thay vì thay correlation ID gốc.

## 5. Truyền trace context bằng Micrometer Tracing

Tracing mô tả quan hệ giữa các thao tác trong một request. Ví dụ:

- Span đầu tiên đại diện cho request đến Order.
- Span tiếp theo đại diện cho lời gọi HTTP từ Order đến Inventory.
- Inventory tạo span server cho request nhận được.
- Nếu Inventory gọi tiếp một dịch vụ khác, lời gọi đó tạo span con tiếp theo.

Với Spring Boot, Micrometer Observation và Micrometer Tracing có thể tích hợp với server và HTTP client để tạo span và truyền trace context qua HTTP. Với W3C Trace Context, header traceparent mang thông tin cần thiết để dịch vụ đích tiếp tục cùng trace.

Các dependency thường dùng trong ứng dụng Spring Boot 3 gồm Actuator, một tracing bridge và exporter tương ứng. Ví dụ khi dùng OpenTelemetry:

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

    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Sử dụng Spring Boot dependency management để chọn phiên bản tương thích. Tùy hệ thống, có thể chọn bridge Brave thay cho OpenTelemetry; không thêm đồng thời nhiều bridge tracing cho cùng một ứng dụng nếu không có kiến trúc đặc biệt.

Cấu hình sampling và endpoint exporter tùy môi trường. Ví dụ cấu hình xác suất lấy mẫu:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Giá trị 1.0 phù hợp để quan sát trong lab vì mọi request đều được lấy mẫu. Với production có lưu lượng lớn, cần chọn sampling phù hợp với chi phí và mục tiêu quan sát.

Khi tạo HTTP client, tiêm RestClient.Builder do Spring Boot cung cấp rồi gọi build(). Builder được cấu hình để tích hợp Observation trong các phiên bản Spring Boot hỗ trợ. Nếu tự tạo client bằng RestClient.create() hoặc builder độc lập, có thể bỏ qua instrumentation mà ứng dụng đã cấu hình.

Không nên tự sao chép trace ID vào một header tùy chỉnh hoặc tự tạo traceparent nếu đã dùng HTTP client được instrument. Instrumentation sẽ tạo span client và inject trace context đúng định dạng. Sao chép trace ID thủ công có thể làm mất quan hệ span cha-con hoặc tạo trace không nhất quán.

## 6. Bảo toàn thông tin xác thực

Ngữ cảnh xác thực cho biết request đang được thực hiện bởi ai. Trong ứng dụng Spring Security, SecurityContextHolder giữ SecurityContext hiện hành. Với cấu hình mặc định của ứng dụng servlet, context thường được lưu trong ThreadLocal.

Khi lời gọi đồng bộ tiếp tục trên cùng thread, code có thể đọc Authentication từ SecurityContextHolder. Nhưng việc có Authentication trong caller không có nghĩa là HTTP client tự động gửi thông tin xác thực đến dịch vụ phụ thuộc.

Cần quyết định rõ danh tính mà dịch vụ đích phải nhìn thấy:

1. **Chuyển tiếp danh tính người dùng (token relay):** dịch vụ đích nhận access token của người dùng và tự xác thực, phân quyền theo token đó.
2. **Danh tính dịch vụ (service identity):** caller lấy access token riêng theo client credentials hoặc cơ chế workload identity; dịch vụ đích nhìn thấy caller là một service account.
3. **Không cần xác thực ở dịch vụ đích:** chỉ áp dụng khi kiến trúc và ranh giới mạng cho phép; không nên mặc định rằng mạng nội bộ là đáng tin cậy.

### 6.1. Token relay có chủ đích

Nếu caller là OAuth2 Resource Server và Inventory được phép nhận chính access token của người dùng, có thể đọc JWT đã xác thực và chuyển tiếp token đó:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication instanceof JwtAuthenticationToken jwtAuthentication) {
    String accessToken = jwtAuthentication.getToken().getTokenValue();
    request.getHeaders().setBearerAuth(accessToken);
}
~~~

Đây là ví dụ về token relay có điều kiện, không phải quy tắc áp dụng cho mọi lời gọi. Chỉ chuyển tiếp token khi:

- Inventory là audience hợp lệ của token.
- Scope hoặc authority trong token đủ cho thao tác cần thực hiện.
- Chính sách bảo mật cho phép dịch vụ Order chuyển tiếp danh tính người dùng.
- Token còn hiệu lực trong thời gian gọi.

Nếu token chỉ dành cho API Order, Inventory có thể từ chối token đó. Trong trường hợp này, caller cần lấy token phù hợp cho Inventory hoặc sử dụng danh tính dịch vụ.

### 6.2. Service-to-service OAuth2

Khi Inventory cần xác thực Order như một dịch vụ, nên dùng OAuth2 Client với client credentials hoặc cơ chế cấp token cho workload. Ứng dụng lấy token từ authorization server bằng client registration tương ứng, sau đó gắn access token vào outbound request.

Không nên tự tạo JWT, tự ký token bằng secret tùy tiện hoặc dùng access token của người dùng thay cho service identity khi kiến trúc yêu cầu danh tính dịch vụ. Cũng không nên ghi token vào log để chẩn đoán lỗi.

### 6.3. Không chuyển tiếp toàn bộ header một cách mù quáng

Không nên sao chép tất cả header từ inbound request sang outbound request. Một số header chỉ có ý nghĩa ở tầng trước, có thể chứa thông tin nhạy cảm hoặc không được dịch vụ đích tin cậy.

Hãy allowlist các header cần truyền, ví dụ:

- X-Correlation-ID để liên kết log.
- traceparent và tracestate do tracing instrumentation quản lý.
- Authorization chỉ khi đã xác định rõ token relay hoặc service token.
- Một số header nghiệp vụ đã được kiểm soát như tenant hoặc locale nếu API đích yêu cầu.

Cookie phiên, Set-Cookie, Host, Content-Length, header hop-by-hop và các header nội bộ khác không nên được chuyển tiếp tùy tiện.

## 7. Kết hợp Circuit Breaker với HTTP client

Circuit Breaker bao quanh lời gọi đồng bộ. HTTP client đảm nhiệm việc gửi correlation ID, tracing và thông tin xác thực đã được chọn.

Ví dụ một gateway đơn giản:

~~~java
package com.example.order.inventory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryGateway.class);

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RestClient inventoryRestClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RestClient inventoryRestClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryRestClient = inventoryRestClient;
    }

    public InventoryResponse getInventory(String sku) {
        String correlationId = MDC.get("correlationId");

        return circuitBreakerFactory.create("inventory").run(
            () -> {
                log.info(
                    "Calling Inventory for sku={}, correlationId={}",
                    sku,
                    correlationId
                );

                return inventoryRestClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class);
            },
            error -> {
                log.warn(
                    "Inventory call failed for sku={}, correlationId={}",
                    sku,
                    correlationId,
                    error
                );

                return InventoryResponse.unavailable(sku);
            }
        );
    }
}
~~~

Đoạn code minh họa phần log và fallback. RestClient được cấu hình riêng để truyền correlation ID và dùng tracing instrumentation. Nếu token relay hoặc service token cần thiết, cấu hình HTTP client phải bổ sung cơ chế xác thực đã chọn.

Fallback có thể chạy trong execution context khác tùy cách tích hợp bulkhead và phiên bản provider. Nếu fallback cần đọc MDC hoặc SecurityContext, hãy xác nhận context đã được truyền đến thread thực thi fallback. Cách an toàn hơn là truyền những giá trị không nhạy cảm mà fallback thực sự cần thành tham số tường minh, thay vì phụ thuộc vào ThreadLocal.

## 8. Khi thread pool bulkhead làm mất context

Thread pool bulkhead cô lập lời gọi bằng một pool riêng. Đây là cách hữu ích để giới hạn tài nguyên dành cho một dependency, nhưng có thể làm mất MDC và SecurityContext nếu không cấu hình truyền context.

Ví dụ, request bắt đầu trên thread http-nio-8080-exec-4, sau đó supplier được chạy trên thread inventory-bulkhead-2. Thread mới không tự có các giá trị ThreadLocal của thread nhận request.

| Ngữ cảnh | Cùng thread | Chuyển sang thread pool |
| --- | --- | --- |
| MDC | Có thể đọc được nếu chưa bị xóa | Không tự động có |
| Correlation ID trong MDC | Có thể đọc được | Cần truyền hoặc thiết lập lại |
| Trace context | Được giữ trong execution context hiện tại | Cần context propagation hoặc instrumentation phù hợp |
| SecurityContextHolder | Thường có với chiến lược ThreadLocal mặc định | Không tự động có |
| HTTP header đã gắn vào request | Được gửi theo request | Vẫn gửi được nếu đã tạo request với header đó |

Có ba hướng xử lý phổ biến:

- Dùng semaphore bulkhead nếu muốn giới hạn concurrency mà vẫn chạy supplier trên thread gọi, và nếu mô hình tải của ứng dụng phù hợp.
- Cấu hình context propagation cho executor hoặc thread pool bulkhead. Micrometer Context Propagation có thể truyền các giá trị đã đăng ký thông qua ThreadLocalAccessor; Spring cung cấp ContextPropagatingTaskDecorator cho các task executor tương thích.
- Với SecurityContext, dùng cơ chế bọc executor hoặc task của Spring Security như DelegatingSecurityContextExecutor khi executor được ứng dụng quản lý. Nếu Resilience4j tạo thread pool riêng, cần dùng hook context propagator mà phiên bản tích hợp hỗ trợ hoặc truyền danh tính cần thiết một cách tường minh.

Không nên bật MODE_INHERITABLETHREADLOCAL như một cách chữa chung cho thread pool. Thread trong pool được tái sử dụng; context kế thừa có thể không phản ánh request hiện tại và có nguy cơ giữ lại danh tính cũ. Luôn bảo đảm context được dọn sạch sau mỗi task.

Trong Spring Cloud CircuitBreaker với Resilience4j, cần kiểm tra cấu hình bulkhead thực tế của ứng dụng. Tùy phiên bản và cấu hình, có thể chọn semaphore bulkhead làm mặc định bằng thuộc tính:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

Hãy xác nhận thuộc tính này được hỗ trợ trong phiên bản Spring Cloud đang sử dụng. Chọn semaphore không thay thế giới hạn thời gian chờ; timeout và bulkhead vẫn cần được thiết kế riêng theo tải của dependency.

## 9. Truyền context qua retry và fallback

Retry có thể tạo nhiều lần gọi đến cùng dependency. Correlation ID của request gốc nên được giữ nguyên qua các lần thử để có thể tìm toàn bộ chuỗi xử lý. Có thể bổ sung attempt number để phân biệt từng lần thử:

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    log.info(
        "Inventory attempt={}, correlationId={}",
        attempt,
        MDC.get("correlationId")
    );

    // Thực hiện lời gọi theo chính sách retry
}
~~~

Đây là đoạn minh họa cách ghi attempt; trong ứng dụng thực tế nên dùng Retry của Resilience4j hoặc cơ chế retry đã được chuẩn hóa, có giới hạn số lần thử, backoff và jitter.

Tracing instrumentation có thể tạo span cho từng HTTP attempt tùy cách cấu hình retry và HTTP client. Không nên tái sử dụng span ID bằng cách tự gắn header. Hãy để tracing library quản lý span và quan hệ giữa các lần thử.

Fallback cần giữ được thông tin tối thiểu để ghi log và tạo kết quả nghiệp vụ đúng. Nếu fallback chạy ở thread khác, không nên giả định rằng MDC và SecurityContext của request gốc còn hiện diện. Truyền correlation ID hoặc mã nghiệp vụ qua tham số nếu fallback cần chúng. Không truyền access token vào fallback trừ khi fallback thật sự cần gọi một dịch vụ khác và có cơ chế cấp token riêng.

## 10. Kiểm tra context propagation trong thực tế

Có thể kiểm tra bằng một request có correlation ID rõ ràng:

~~~bash
curl -H "X-Correlation-ID: lab-order-001" \
     "http://localhost:8080/orders/123/inventory"
~~~

Nếu API yêu cầu JWT, gửi một access token thử nghiệm có audience và scope hợp lệ:

~~~bash
curl -H "X-Correlation-ID: lab-order-001" \
     -H "Authorization: Bearer <access-token>" \
     "http://localhost:8080/orders/123/inventory"
~~~

Không dùng token production trong ví dụ hoặc log. Token placeholder cần được thay bằng token test do authorization server cấp cho đúng API.

Kiểm tra theo các điểm sau:

1. Log tại tầng nhận request của Order có correlation ID lab-order-001.
2. Log tại gateway gọi Inventory có cùng correlation ID.
3. Log tại Inventory có cùng correlation ID nếu header được truyền.
4. Trace backend hiển thị span server của Order, span client gọi Inventory và span server của Inventory trong cùng trace.
5. Inventory nhận đúng loại danh tính đã thiết kế: user token được relay có chủ đích hoặc service token của Order.
6. Khi Circuit Breaker OPEN và supplier không chạy, fallback vẫn ghi log được theo context đã truyền hoặc tham số tường minh.
7. Khi bật thread pool bulkhead, lặp lại các bước trên để xác nhận context propagation vẫn hoạt động.
8. Sau khi request kết thúc, thread xử lý request tiếp theo không được dùng lại correlation ID hoặc SecurityContext của request trước.

Để kiểm tra việc dọn MDC, gửi hai request liên tiếp với hai correlation ID khác nhau rồi so sánh log. Mỗi request chỉ được xuất hiện với ID tương ứng. Nếu ID đầu tiên xuất hiện trong log của request thứ hai, filter hoặc task cleanup chưa đúng.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Log ở caller có correlation ID nhưng provider không có | Chưa truyền X-Correlation-ID trong outbound client | Thêm request interceptor và filter ở provider |
| Log provider có ID khác caller | Một tầng tạo ID mới hoặc gateway ghi đè header | Xác định một nơi tạo ID và thống nhất quy tắc truyền |
| Trace bị tách thành hai trace | HTTP client chưa được instrument hoặc trace header bị ghi đè | Dùng builder được Spring Boot quản lý và để tracing library inject context |
| Không thấy trace ID trong log | Chưa bật Micrometer Tracing hoặc log pattern chưa có MDC fields | Kiểm tra tracing bridge, exporter và logging pattern |
| SecurityContext rỗng trong supplier | Supplier chạy trên thread pool khác | Cấu hình Security context propagation hoặc dùng execution model phù hợp |
| Inventory trả 401 hoặc 403 | Token không hợp lệ, sai audience hoặc thiếu scope | Kiểm tra resource server và quyền của token |
| Fallback không có correlation ID | Fallback chạy ở thread khác hoặc được gọi sau khi context đã bị dọn | Truyền correlation ID tường minh hoặc cấu hình propagation |
| Request sau dùng nhầm correlation ID | MDC không được xóa trong finally | Khôi phục hoặc xóa MDC sau mỗi request và task |
| Log vô tình chứa token | Log toàn bộ request header hoặc Authentication | Loại bỏ Authorization, Cookie và dữ liệu bí mật khỏi log |

## 12. Nguyên tắc thiết kế

- Tạo hoặc xác thực correlation ID ở ranh giới nhận request, sau đó truyền nhất quán qua các dịch vụ.
- Dùng MDC cho dữ liệu log gắn với thread hiện tại và luôn dọn context sau request hoặc task.
- Dùng Micrometer Tracing cùng HTTP client được instrument để truyền trace context.
- Không tự tạo hoặc ghi đè traceparent khi tracing library đã quản lý propagation.
- Chỉ relay access token khi token có audience, scope và chính sách phù hợp với dịch vụ đích.
- Dùng service identity riêng khi lời gọi cần danh tính của workload thay vì người dùng.
- Không ghi token, cookie phiên, mật khẩu hoặc bí mật vào log.
- Xác định bulkhead có chuyển thread hay không; truyền context cho executor khi cần.
- Không dựa vào InheritableThreadLocal để chia sẻ context qua thread pool.
- Kiểm tra cả supplier, fallback, retry và request tiếp theo để phát hiện context bị mất hoặc rò rỉ.

Khi gọi đồng bộ qua Spring Cloud CircuitBreaker, bảo toàn context giúp log có thể liên kết, trace thể hiện đúng đường đi và dịch vụ phụ thuộc nhận đúng danh tính cần thiết. Điều này phụ thuộc vào cách thực thi thực tế: cùng thread có thể giữ các ThreadLocal, còn thread pool cần context propagation rõ ràng. Kết hợp MDC, Micrometer Tracing, Spring Security và HTTP client được cấu hình đúng giúp việc chẩn đoán lỗi và kiểm soát quyền truy cập nhất quán qua các tầng dịch vụ.

## Tài liệu tham khảo

- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Boot tracing and observability](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Spring Security concurrency support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

