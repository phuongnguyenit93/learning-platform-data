# Truyền Reactor Context và mã tương quan qua lời gọi HTTP

> **Chương:** WebClient  
> **Phạm vi:** Spring Boot Integration — tích hợp HTTP giữa các dịch vụ, truyền ngữ cảnh theo luồng reactive, hợp đồng header, xử lý lỗi và khả năng quan sát.

Khi một request đi qua API Gateway, dịch vụ đơn hàng, dịch vụ tồn kho rồi đến hệ thống thanh toán, các log và lỗi có thể xuất hiện trên nhiều máy, nhiều thread, nhiều kết nối HTTP. Một **correlation ID** giúp nối các sự kiện thuộc cùng một yêu cầu nghiệp vụ. Với Spring WebFlux và WebClient, ta cần truyền ID đó qua hai ranh giới khác nhau:

1. **Trong một tiến trình reactive:** lưu ID vào **Reactor Context** để các toán tử thuộc cùng subscription đọc được.
2. **Giữa hai dịch vụ:** lấy ID từ Reactor Context, đặt vào **HTTP request header**; ở đầu nhận, đọc header rồi đưa ID vào Reactor Context mới.

Reactor Context **không tự đi qua mạng**. Nó cũng không phải một biến toàn cục, ThreadLocal hay một cơ chế distributed tracing hoàn chỉnh.

## 1. Reactor Context giải quyết vấn đề gì?

Reactor Context là một cấu trúc dữ liệu theo cặp khóa–giá trị, gắn với **Subscriber/subscription**, dùng để truyền thông tin phụ trợ mà không phải thêm tham số vào mọi hàm. Các giá trị thường gặp gồm correlation ID, thông tin quan sát (observability) và metadata cần cho xử lý bất đồng bộ.

Giả sử một luồng gọi WebClient chuyển từ event-loop sang scheduler khác. Nếu lưu correlation ID bằng ThreadLocal hoặc MDC thủ công ngay trước khi tạo Mono, thread thực thi HTTP có thể khác thread gán giá trị. Log dễ bị thiếu hoặc nhầm ID giữa các request đồng thời. Reactor Context đi theo **chuỗi reactive** và có thể được đọc ở thời điểm subscription.

| Thành phần | Phạm vi | Có tự truyền qua HTTP? | Vai trò |
| --- | --- | --- | --- |
| Reactor Context | Một reactive subscription trong JVM | Không | Mang metadata qua các toán tử Reactor |
| HTTP header **X-Correlation-ID** | Một HTTP request/response | Có, khi ứng dụng chủ động gán | Hợp đồng liên dịch vụ cho ID nghiệp vụ |
| MDC / ThreadLocal | Thread hiện tại | Không | Bổ sung thuộc tính cho log trên thread đó |
| W3C **traceparent** / **tracestate** | Ngữ cảnh distributed tracing | Có, khi tracer/instrumentation cấu hình đúng | Liên kết các span giữa các dịch vụ |
| W3C **baggage** | Metadata truyền cùng trace | Có, với cấu hình propagation tương ứng | Mang một số thuộc tính được chọn qua ranh giới dịch vụ |

**Nguyên tắc:** một correlation ID có thể là khóa tìm kiếm log nghiệp vụ ổn định trong cả hành trình request; trace ID và span ID phục vụ distributed tracing. Chúng có thể liên hệ với nhau nhưng không nên mặc định đồng nhất.

## 2. Context được ghi và đọc theo chiều nào?

Hai API quan trọng nhất là:

- **Mono.deferContextual(...)** hoặc **Flux.deferContextual(...)**: đọc ContextView khi có subscription, phù hợp cho filter và gateway.
- **contextWrite(...)**: bổ sung/ghi đè context mà **các toán tử ở phía upstream** nhìn thấy trong cùng subscription. Theo hình thức viết chain, thao tác này thường đặt ở phía cuối để các bước nằm phía trước nhìn thấy dữ liệu.

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Object key = new Object();

Mono<String> operation = Mono.deferContextual(context ->
    Mono.just("correlationId=" + context.<String>get(key))
);

Mono<String> requestA = operation
    .contextWrite(Context.of(key, "req-101"));

Mono<String> requestB = operation
    .contextWrite(Context.of(key, "req-202"));

// Mỗi subscription đọc context riêng:
// requestA -> "correlationId=req-101"
// requestB -> "correlationId=req-202"
~~~

**Điểm dễ nhầm:** Context bất biến về mặt ngữ nghĩa; **contextWrite** tạo một view được cập nhật cho subscription và không sửa một biến dùng chung. Việc gọi **Mono.just(...)** khi lắp pipeline không có nghĩa là đã thực hiện HTTP hay đọc được Context. Lấy dữ liệu bằng **deferContextual** bảo đảm đọc ở thời điểm phù hợp.

Một operator không thuộc luồng upstream của điểm **contextWrite** sẽ không tự nhìn thấy khóa mới. Các nhánh được tạo bằng **subscribe()** độc lập hoặc chuyển sang **CompletableFuture**/executor ngoài Reactor cũng cần cơ chế chuyển ngữ cảnh riêng.

## 3. Luồng truyền ID giữa Service A và Service B

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant A as Service A (WebFlux)
    participant W as WebClient trong A
    participant B as Service B
    C->>A: GET /api/inventory/42<br/>X-Correlation-ID: req-101
    Note over A: WebFilter kiểm tra header<br/>contextWrite(correlationId=req-101)
    A->>W: Gọi gateway qua Mono
    Note over W: deferContextual đọc req-101
    W->>B: GET /v1/inventory/42<br/>X-Correlation-ID: req-101
    Note over B: WebFilter tạo Reactor Context<br/>của subscription mới
    B-->>W: 200 OK
    W-->>A: Body phản hồi
    A-->>C: HTTP response<br/>X-Correlation-ID: req-101
~~~

Mỗi dịch vụ sở hữu một Reactor Context của riêng request/subscription. Cầu nối giữa hai Context là header được gửi qua HTTP. **Service B phải triển khai logic tiếp nhận riêng** nếu muốn giữ cùng correlation ID cho các lời gọi tiếp theo.

## 4. Hợp đồng correlation ID tại biên HTTP

Chọn tên header thống nhất cho các dịch vụ, ví dụ **X-Correlation-ID**. Đây là quy ước ứng dụng, không phải header chuẩn bắt buộc của HTTP. Định nghĩa rõ:

| Quy tắc | Lý do |
| --- | --- |
| Nếu request đầu vào có ID hợp lệ thì tái sử dụng; nếu không thì sinh ID mới | Cho phép tương quan trong hệ thống nhưng luôn có giá trị đáng tin cậy để ghi log |
| Chỉ chấp nhận ký tự trong tập cho phép và giới hạn độ dài | Tránh log injection, header bất thường và dữ liệu quá lớn |
| Giữ cùng ID qua các lời gọi con và retry của một request | Tìm được toàn bộ diễn biến liên quan |
| Trả ID trong response header | Cho phép client và đội vận hành tra cứu khi phát sinh lỗi |
| Không nhét token, email, dữ liệu cá nhân hoặc secret vào ID | Tránh đưa thông tin nhạy cảm vào log, trace và hệ thống downstream |
| Chỉ gửi header đến downstream được phép | Tránh rò rỉ metadata sang URL do người dùng điều khiển |

Ở môi trường có API Gateway, có thể **luôn sinh lại** ID tại biên tin cậy để tránh client tự chọn ID va chạm hoặc giả mạo. Ví dụ dưới đây tái sử dụng header **sau khi kiểm tra hợp lệ**; chính sách trust boundary cần thống nhất cho toàn hệ thống.

### 4.1. Khóa context và quy tắc xác thực

File **CorrelationId.java**:

~~~java
package example.integration;

import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationId {
    public static final String HEADER = "X-Correlation-ID";

    // Object riêng để không va chạm với key chuỗi từ thư viện khác.
    public static final Object CONTEXT_KEY = new Object();

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,64}");

    private CorrelationId() {
    }

    public static String fromIncomingHeader(String candidate) {
        if (candidate != null && SAFE_ID.matcher(candidate).matches()) {
            return candidate;
        }
        return UUID.randomUUID().toString();
    }
}
~~~

Tạo UUID khi thiếu/sai header giúp ứng dụng luôn có ID cho request. Regex chỉ là **ví dụ hợp đồng**; nếu dùng UUID chuẩn, ULID hoặc định dạng khác, hãy đổi quy tắc ở mọi dịch vụ và gateway cho nhất quán.

### 4.2. Nhận ID và ghi Reactor Context bằng WebFilter

Ví dụ này dành cho ứng dụng **Spring WebFlux**. Filter chạy tại biên HTTP server, gán header trong response và tạo Context cho phần xử lý tiếp theo.

File **CorrelationWebFilter.java**:

~~~java
package example.integration;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class CorrelationWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        String incoming = exchange.getRequest()
                .getHeaders()
                .getFirst(CorrelationId.HEADER);

        String correlationId =
                CorrelationId.fromIncomingHeader(incoming);

        exchange.getResponse()
                .getHeaders()
                .set(CorrelationId.HEADER, correlationId);

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put(CorrelationId.CONTEXT_KEY, correlationId));
    }
}
~~~

**Vì sao contextWrite nằm sau chain.filter?** Trong subscription, context do toán tử downstream cung cấp sẽ được nhìn thấy bởi phần xử lý upstream, gồm controller, service và WebClient nằm trong chuỗi đó. Không cần truyền correlation ID qua tham số mọi tầng.

**Giới hạn:** WebFilter chỉ áp dụng cho WebFlux server. Nếu ứng dụng dùng Spring MVC/Servlet, cần cơ chế filter và cầu nối context phù hợp với Servlet; chỉ thêm lớp WebFilter sẽ không kích hoạt nó cho request MVC.

### 4.3. Đọc Reactor Context trong ExchangeFilterFunction của WebClient

WebClient sử dụng **ExchangeFilterFunction** để chỉnh request trước khi gửi và xử lý response. Vì ClientRequest là bất biến, tạo bản sao bằng **ClientRequest.from(...)**, rồi bổ sung header.

File **CorrelationWebClientFilter.java**:

~~~java
package example.integration;

import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import reactor.core.publisher.Mono;

public final class CorrelationWebClientFilter {
    private CorrelationWebClientFilter() {
    }

    public static ExchangeFilterFunction outbound() {
        return (request, next) -> Mono.deferContextual(contextView -> {
            if (!contextView.hasKey(CorrelationId.CONTEXT_KEY)) {
                // Job/scheduler không có context cần được cấp ID riêng
                // tại nơi bắt đầu luồng nếu muốn có correlation.
                return next.exchange(request);
            }

            String correlationId =
                    contextView.get(CorrelationId.CONTEXT_KEY);

            ClientRequest withCorrelation = ClientRequest.from(request)
                    .headers(headers ->
                            headers.set(CorrelationId.HEADER, correlationId))
                    .build();

            return next.exchange(withCorrelation);
        });
    }
}
~~~

Ở đây **Mono.deferContextual** nằm **bên trong** filter, nên mỗi lần subscription/retry có thể đọc context của lời gọi hiện tại. Filter không dùng trường static kiểu **currentId**, không lấy MDC làm nguồn sự thật và không giữ ID của request trước.

Khi không có khóa context, ví dụ cố ý giữ nguyên request. Nếu một job nền cũng bắt buộc có correlation ID, hãy tạo ID và gán Context tại điểm khởi phát job (xem mục 6) thay vì cho từng filter ngẫu nhiên sinh các ID khác nhau.

### 4.4. Đăng ký WebClient và gọi dịch vụ downstream

File **HttpClientConfiguration.java**:

~~~java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {
    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .filter(CorrelationWebClientFilter.outbound())
                .build();
    }
}
~~~

Nên dùng **WebClient.Builder do Spring Boot quản lý** để nhận các customizer và cấu hình quan sát phù hợp với ứng dụng. Đặt filter trên client dành cho endpoint tin cậy; tránh dùng một filter phát tán header tới mọi URL tùy ý.

File **InventoryGateway.java**:

~~~java
package example.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryGateway {
    private final WebClient client;

    public InventoryGateway(
            @Qualifier("inventoryWebClient") WebClient client) {
        this.client = client;
    }

    public Mono<String> getInventory(String sku) {
        return client.get()
                .uri("/v1/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

File **InventoryController.java**:

~~~java
package example.integration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class InventoryController {
    private final InventoryGateway inventoryGateway;

    public InventoryController(InventoryGateway inventoryGateway) {
        this.inventoryGateway = inventoryGateway;
    }

    @GetMapping("/api/inventory/{sku}")
    public Mono<String> inventory(@PathVariable String sku) {
        return inventoryGateway.getInventory(sku);
    }
}
~~~

Controller chỉ trả về Mono; khi WebFlux subscribe vào chuỗi, **CorrelationWebFilter** cung cấp ID, **CorrelationWebClientFilter** đọc ID và gửi header tương ứng. Dùng **String** để rút ngắn ví dụ; khi tích hợp thực tế nên định nghĩa DTO, timeout, xử lý HTTP status và hợp đồng lỗi rõ ràng.

Một request minh họa:

~~~http
GET /api/inventory/SKU-42 HTTP/1.1
Host: service-a.internal
X-Correlation-ID: order-2026-00042
~~~

Lời gọi từ Service A sang Service B:

~~~http
GET /v1/inventory/SKU-42 HTTP/1.1
Host: inventory-service
X-Correlation-ID: order-2026-00042
~~~

Khi Service B cũng dùng logic tại mục 4.2, nó tạo **Reactor Context mới** mang cùng ID cho request nhận được. Response từ Service A có **X-Correlation-ID** để người gọi cung cấp cho đội vận hành.

## 5. Ghi log an toàn từ Reactor Context

Đọc ID trực tiếp trong **deferContextual** là cách rõ ràng khi cần vài điểm log:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Mono;

private static final Logger log =
        LoggerFactory.getLogger(InventoryGateway.class);

public Mono<String> getInventoryWithLog(String sku) {
    return Mono.deferContextual(context -> {
        String correlationId =
                context.getOrDefault(CorrelationId.CONTEXT_KEY, "missing");
        log.info("Calling inventory sku={}, correlationId={}",
                sku, correlationId);

        return client.get()
                .uri("/v1/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(String.class);
    });
}
~~~

**MDC là ThreadLocal**, nên gọi **MDC.put("correlationId", ...)** tại đầu controller rồi kỳ vọng mọi reactive callback đều thấy ID là không an toàn. Nếu cần tự động gắn context vào mọi log, hãy cấu hình và kiểm thử tích hợp **Micrometer Context Propagation / Reactor context propagation** phù hợp với phiên bản Spring Boot, Reactor, tracing và logging của hệ thống. Propagation của MDC/ThreadLocal và việc chuyển **khóa nghiệp vụ tùy chỉnh** ra HTTP header là hai trách nhiệm khác nhau.

Không log toàn bộ HTTP header, token hoặc body nhạy cảm chỉ để tìm correlation ID. Nên gắn **correlationId** thành một trường log có cấu trúc.

## 6. Chủ động tạo Context cho batch job hoặc scheduler

Đối với công việc không bắt đầu từ WebFlux request, sẽ không có **CorrelationWebFilter** cấp ID. Tạo context ở ranh giới công việc:

~~~java
import java.util.UUID;
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

public Mono<Void> refreshInventoryJob() {
    String correlationId = UUID.randomUUID().toString();

    return inventoryGateway.getInventory("SKU-42")
            .then()
            .contextWrite(Context.of(CorrelationId.CONTEXT_KEY,
                                     correlationId));
}
~~~

Một lần thực thi job dùng một ID; nếu job tạo nhiều nhánh cùng thuộc một nghiệp vụ, có thể áp Context ở ngoài nhóm nhánh. Đừng gọi **subscribe()** ngay trong service chỉ để kích hoạt HTTP: subscription tách rời dễ làm mất kiểm soát lỗi, huỷ và lifecycle. Hãy để tầng điều phối subscribe hoặc trả về Publisher cho framework xử lý.

## 7. Quan hệ với distributed tracing của Spring Boot

Trong hệ thống có Micrometer Observation/Tracing và tracer được cấu hình, instrumentation của HTTP client/server có thể tạo span và truyền **traceparent** theo W3C. Điều này phục vụ một mục tiêu liên quan nhưng khác correlation ID nghiệp vụ.

~~~text
X-Correlation-ID: order-2026-00042
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- **X-Correlation-ID**: một khóa nghiệp vụ mà ứng dụng quyết định tạo, kiểm tra, chuyển tiếp.
- **traceparent**: trace ID, span ID và cờ trace được instrumentation quản lý; không tự ghép hoặc sửa để trùng với correlation ID.
- **baggage**: chỉ đưa thuộc tính thật sự cần truyền xuyên dịch vụ, cân nhắc cardinality, độ dài header và bảo mật.

Sử dụng WebClient.Builder do Spring Boot cung cấp giúp giữ cấu hình observation cho WebClient. Không giả định chỉ thêm starter tracing là **mọi khóa Reactor Context** đều được gửi thành header: filter nghiệp vụ ở mục 4.3 vẫn cần thiết nếu chọn hợp đồng **X-Correlation-ID**. Khi triển khai, kiểm tra bằng HTTP thực tế rằng trace headers và correlation header cùng tồn tại và chính sách propagation qua gateway/proxy đúng như mong đợi.

## 8. Context trong retry, timeout, lỗi và xử lý song song

| Tình huống | Điều cần bảo đảm |
| --- | --- |
| **retryWhen** gọi lại downstream | Mỗi lần subscribe lại vẫn lấy cùng correlation ID của một request; đừng sinh ID mới trong mỗi retry |
| Timeout, 4xx, 5xx hoặc kết nối bị từ chối | ID vẫn phải có trong log lỗi và response lỗi của Service A nếu response chưa bị commit |
| **flatMap** thực hiện nhiều lời gọi đồng thời | Các nhánh cùng request có thể dùng cùng ID; hai request độc lập không được lẫn ID |
| **publishOn** / **subscribeOn** | Reactor Context đi cùng subscription thông qua các toán tử Reactor chuẩn; không phụ thuộc thread cố định |
| **Mono.cache()**, chia sẻ Publisher hoặc chủ động subscribe nhiều nơi | Xem lại phạm vi subscription và dữ liệu dùng chung; tránh cache phản hồi đã mang metadata của request khác |
| CompletableFuture, thư viện callback hoặc executor bên ngoài Reactor | Cần cầu nối ngữ cảnh explicit hoặc thư viện context propagation đã được kiểm thử |
| Streaming/SSE hoặc request bị cancel | Correlation ID vẫn dùng để tìm log, nhưng cleanup/metrics phải tôn trọng signal cancel |

Ví dụ gắn ID cho cả pipeline có retry:

~~~java
import java.time.Duration;
import reactor.util.context.Context;
import reactor.util.retry.Retry;

Mono<String> result = inventoryGateway.getInventory("SKU-42")
        .timeout(Duration.ofSeconds(3))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(error -> isTransientFailure(error)))
        .contextWrite(Context.of(CorrelationId.CONTEXT_KEY, "req-101"));
~~~

Ở đây **isTransientFailure(...)** đại diện cho chính sách phân loại lỗi của ứng dụng (chỉ retry lỗi tạm thời). Timeout là ví dụ cấu hình, không phải giá trị mặc định bắt buộc. Không retry các thao tác ghi không idempotent nếu chưa có hợp đồng idempotency/deduplication. **Correlation ID không thay thế idempotency key**: hai loại ID có chức năng khác nhau và không giải quyết việc ghi trùng.

## 9. Kiểm thử filter không cần mạng thật

Có thể tạo **ExchangeFunction** giả để quan sát ClientRequest sau khi qua filter. Ví dụ JUnit 5, Reactor Test và AssertJ:

~~~java
package example.integration;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

import static org.assertj.core.api.Assertions.assertThat;

class CorrelationWebClientFilterTest {
    @Test
    void addsCorrelationHeaderFromReactorContext() {
        AtomicReference<String> captured = new AtomicReference<>();

        ExchangeFunction fakeTransport = request -> {
            captured.set(request.headers()
                    .getFirst(CorrelationId.HEADER));

            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body("ok")
                    .build());
        };

        WebClient client = WebClient.builder()
                .exchangeFunction(fakeTransport)
                .filter(CorrelationWebClientFilter.outbound())
                .build();

        Mono<String> call = client.get()
                .uri("http://inventory.internal/test")
                .retrieve()
                .bodyToMono(String.class)
                .contextWrite(Context.of(CorrelationId.CONTEXT_KEY,
                                         "req-789"));

        StepVerifier.create(call)
                .expectNext("ok")
                .verifyComplete();

        assertThat(captured.get()).isEqualTo("req-789");
    }
}
~~~

Các trường hợp nên bổ sung trong bộ kiểm thử integration:

1. **Không có X-Correlation-ID đầu vào:** WebFilter sinh ID hợp lệ, response trả ID đó, downstream cũng nhận đúng ID.
2. **ID sai định dạng** (khoảng trắng, ký tự điều khiển, quá 64 ký tự): không chuyển tiếp nguyên xi; sinh ID mới hoặc từ chối theo hợp đồng.
3. **Hai request chạy đồng thời** với ID khác nhau: mỗi downstream request nhận chính xác ID của mình, kể cả khi có **flatMap**, thay scheduler hoặc retry.
4. **Không có Reactor Context** ở client nền: filter không tự thêm header theo chính sách ví dụ, sau đó xác nhận việc gán Context ở job sẽ tạo header.
5. **Lỗi downstream:** log và response lỗi có thể đối chiếu bằng ID; không đưa nội dung nhạy cảm của request vào thông điệp lỗi.
6. **Tracing đã bật:** xác minh W3C trace headers được instrumentation truyền riêng và không bị filter tùy chỉnh ghi đè.

Đối với kiểm thử HTTP end-to-end, dùng **WebTestClient** cho server WebFlux và một HTTP test server/stub cho downstream, kiểm tra cả request header thực gửi, response header và giá trị được log trong cùng request.

## 10. Các lỗi triển khai thường gặp

**Đọc Context lúc khởi tạo bean:** filter chạy khi build WebClient không đại diện cho một subscription. Hãy dùng **Mono.deferContextual(...)** bên trong lambda của filter.

**Đặt ID trong biến static hoặc một trường mutable của singleton:** các request đồng thời sẽ ghi đè lẫn nhau. Dùng Context theo subscription.

**Dùng MDC.get(...) làm nguồn header:** giá trị thread-local có thể trống hoặc bị rò giữa tác vụ khi chuyển thread. Lấy từ Reactor Context rồi mới gán vào ClientRequest.

**Chỉ dùng Reactor Context và chờ Service B tự nhận ID:** Context tồn tại trong JVM; cần biến nó thành HTTP header và xử lý lại ở đầu nhận.

**Chỉ cấu hình tracing rồi giả định X-Correlation-ID tự xuất hiện:** traceparent không đồng nghĩa với header nghiệp vụ. Nếu yêu cầu có X-Correlation-ID, phải quy định cách cấp và chuyển tiếp.

**Thêm ID một lần vào defaultHeader của WebClient singleton:** ID sẽ cố định cho nhiều request. Với correlation ID theo từng request, phải đọc Context khi thực thi exchange.

**Chuyển tiếp header bất kỳ từ Internet:** có nguy cơ chèn ký tự lạ, quá dài, vô tình mang thông tin nhạy cảm hoặc phát tán header sang miền không tin cậy. Kiểm tra tại biên và giới hạn downstream.

**Tạo ID mới ở mọi outbound retry:** cùng một nghiệp vụ xuất hiện thành nhiều chuỗi log không liên quan. Tạo ID tại biên request hoặc job, để filter đọc lại ID đó.

## 11. Checklist khi đưa vào sản xuất

- Các dịch vụ thống nhất tên header, giới hạn độ dài, định dạng ID và chính sách tái sử dụng/sinh mới ở trust boundary.
- WebFlux server đặt ID vào Reactor Context; WebClient đọc bằng **deferContextual** và gán vào ClientRequest theo từng subscription.
- HTTP client có timeout, phân loại lỗi, retry có điều kiện và xử lý hợp đồng lỗi; correlation ID được ghi ở điểm quan sát quan trọng.
- Không chứa token, user data hoặc nội dung nhạy cảm trong correlation ID, log, tracing baggage.
- Gateway/proxy không vô ý xóa header cần thiết và không chuyển metadata sang đích không đáng tin.
- Test đồng thời, test lỗi, test không có Context và test propagation qua HTTP thật đều đạt.
- Log/trace/metrics có thể được tra cứu theo ID, đồng thời phân biệt rõ correlation ID với trace ID và idempotency key.

## Tài liệu tham khảo

- [Project Reactor Reference — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Framework Reference — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html)
- [Spring Framework Reference — Context Propagation](https://docs.spring.io/spring-framework/reference/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)

**Ghi nhớ:** Reactor Context vận chuyển dữ liệu **bên trong** một subscription; ExchangeFilterFunction chuyển một giá trị được chọn thành **HTTP header**; dịch vụ nhận phải đọc header và thiết lập Context cho subscription của chính nó. Đó là chuỗi thao tác cần thiết để nối log một cách đáng tin cậy qua các lời gọi WebClient bất đồng bộ.
