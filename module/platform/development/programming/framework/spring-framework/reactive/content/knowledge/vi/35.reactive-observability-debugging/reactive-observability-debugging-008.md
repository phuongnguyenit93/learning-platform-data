# Giới hạn log body, chi phí quan sát và bảo vệ thông tin nhạy cảm trong Spring WebFlux

> **Module:** Spring Framework – reactive  
> **Chủ đề cha:** Quan sát và gỡ lỗi  
> **Trọng tâm:** thiết kế logs, metrics và traces đủ để điều tra sự cố mà không lưu toàn bộ request/response body; kiểm soát kích thước, tần suất và cardinality; tránh lộ token, cookie, PII, dữ liệu thanh toán và thông tin nội bộ; hiểu vòng đời `DataBuffer`; tích hợp `WebFilter`, `WebClient` filter và Micrometer Observation. Project mẫu dùng Spring Boot 4.0.9, Java 17+, JUnit 5 và WebTestClient.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt logs, metrics và traces, chọn đúng tín hiệu cho câu hỏi vận hành.
2. Ghi metadata request/response mà không cần đọc body.
3. Ước lượng chi phí CPU, memory, network, storage và indexing khi log body.
4. Chọn route/operation được phép ghi body; giới hạn byte, sampling, thời gian bật và retention.
5. Tạo safe projection theo allowlist thay vì serialize nguyên DTO hoặc dùng regex để che mọi secret.
6. Phân biệt giới hạn codec buffering với giới hạn body logger.
7. Hiểu request body là stream một lần; nếu interceptor consume body thì phải replay và quản lý `DataBuffer` đúng cách.
8. Dùng `WebFilter` ghi method, route template, status, duration, request ID và terminal signal.
9. Dùng `ExchangeFilterFunction` quan sát WebClient mà không consume response body hoặc log URL/query/headers nhạy cảm.
10. Dùng Spring Boot Actuator/Micrometer và kiểm soát low-cardinality/high-cardinality tags.
11. Bảo vệ logs khỏi secret leakage, PII, log injection, truy cập trái phép và lưu trữ quá hạn.
12. Viết tests chứng minh projection không chứa dữ liệu nhạy cảm, preview bị giới hạn byte và HTTP response không echo secret.

**Nguyên tắc chính:** observability cần đủ ngữ cảnh để trả lời “request nào, route nào, khi nào, kết quả gì và chậm ở đâu”. Nó không cần lưu bản sao của mọi dữ liệu người dùng gửi. Hãy bắt đầu bằng metadata và metrics; chỉ thu thập một phần body khi có lý do, allowlist rõ, byte cap và thời hạn ngắn.

## 2. Ba trụ cột observability

Spring Boot mô tả observability qua ba nhóm: logs, metrics và traces.

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Logs | Sự kiện cụ thể đã xảy ra thế nào? | `POST /api/orders` trả 422, duration 85 ms |
| Metrics | Xu hướng và mức độ của hệ thống? | p95 latency tăng, 5xx rate 3% |
| Traces | Một request đi qua service/dependency nào và chậm ở đâu? | Gateway 8 ms, catalog 20 ms, DB 210 ms |

Không biến logs thành metrics bằng cách tạo log cho mỗi phép đo. Không dùng metrics để lưu từng request ID hoặc order ID. Không đưa raw body vào trace chỉ để xem lại payload.

### 2.1. Một HTTP log hữu ích

Một event vận hành thường chỉ cần:
- Timestamp, severity, service, environment và version.
- Request/correlation ID hoặc trace ID.
- HTTP method và route template.
- Status/outcome và duration.
- Exception type hoặc error code đã chuẩn hóa.
- Body byte count nếu cần.
- Operation label hữu hạn do code định nghĩa.

Ví dụ:

~~~json
{
  "event": "http_request_completed",
  "requestId": "[a9c4e]",
  "method": "POST",
  "route": "/api/orders",
  "status": 202,
  "durationMs": 84,
  "outcome": "SUCCESS"
}
~~~

Log này không chứa raw path parameter, query string, cookie, authorization header hoặc body. Route template gom `/api/orders/1` và `/api/orders/2` thành cùng một route.

### 2.2. Không dùng thread ID làm correlation ID

WebFlux có thể xử lý một request qua nhiều thread. Thread name không đủ để nối log của cùng request. Spring cung cấp request-specific log ID và `ServerWebExchange.getLogPrefix()` để tạo prefix cho log. WebClient cũng có log prefix trên `ClientRequest`.

Dùng request ID/trace context do framework quản lý thay vì giả định request luôn chạy trên một thread.

### 2.3. Operational logs khác audit trail

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Operational log | Debug và vận hành | Request chậm, timeout, retry |
| Security event log | Phát hiện hành vi đáng ngờ | Access denied, login failure |
| Audit trail | Ghi nhận thay đổi có thể kiểm tra | Ai duyệt khoản thanh toán |
| Business event | Theo dõi trạng thái nghiệp vụ | `order_created`, `payment_authorized` |

Không dùng DEBUG log làm audit trail. Audit cần schema, quyền truy cập, retention, integrity và semantics giao dịch rõ ràng. Nếu audit phải tồn tại cùng transaction nghiệp vụ, cân nhắc transactional outbox hoặc cơ chế durable tương ứng.

## 3. Chi phí của việc log toàn bộ body

### 3.1. Ước lượng dung lượng

\[
\text{bytes/day} =
\text{requests/second}
\times \text{average logged bytes}
\times 86{,}400
\]

Ví dụ, 400 request/giây, mỗi request tạo thêm 1 KiB body log:

\[
400 \times 1{,}024 \times 86{,}400
= 35{,}389{,}440{,}000
\]

Tương đương khoảng **35.4 GB/ngày** dữ liệu thô, chưa tính response body, nhiều replica, metadata, index, replication và backup.

### 3.2. Chi phí không chỉ là disk

| Thành phần | Vì sao tăng chi phí |
| --- | --- |
| CPU | Serialize JSON, redact, format, encode và compress |
| Heap/direct memory | Buffer body, copy byte array, queue chờ appender |
| Event loop | Logging đồng bộ hoặc serialize payload lớn chiếm thời gian xử lý |
| Network | Gửi log lớn từ instance tới collector |
| Storage/index | Dung lượng và index field tăng |
| Tracing backend | Span attribute lớn, nhiều span và sampling không hợp lý |
| Cardinality | Tag động tạo nhiều time series |
| Nhân sự | Payload quá nhiều gây nhiễu, khó tìm tín hiệu quan trọng |

Async appender có thể giảm I/O trực tiếp trên thread request, nhưng thường có queue hữu hạn và policy khi queue đầy. Async logging không làm payload lớn trở nên miễn phí; nếu producer nhanh hơn consumer, queue vẫn đầy hoặc log bị drop theo policy.

### 3.3. Body logging làm tăng bề mặt rò rỉ

Request body có thể chứa:
- Password, OTP, recovery code.
- Bearer/access/refresh token, API key.
- Session ID, cookie, CSRF token.
- Email, điện thoại, địa chỉ hoặc ID định danh.
- Thông tin sức khỏe.
- Số tài khoản, thẻ thanh toán, CVV.
- Tài liệu nội bộ, prompt, nội dung khách hàng hoặc dữ liệu hợp đồng.
- File upload, binary và nội dung chat.

Log có thể được chuyển tới collector, dashboard, APM, SIEM, backup và môi trường hỗ trợ. Mỗi bản sao là một nơi cần bảo vệ. Token bị ghi vào log có thể tiếp tục hợp lệ sau khi request kết thúc.

## 4. Chính sách chọn dữ liệu cần ghi

### 4.1. Metadata-only là mặc định

Đối với đa số route, chỉ ghi method, route template, status/outcome, duration, request ID/trace ID, exception type/error code và operation label do code đặt.

Không log mặc định:
- `Authorization`, `Cookie`, `Set-Cookie`.
- Query string có thể chứa token, email hoặc dữ liệu cá nhân.
- Full URI nếu path có ID hoặc thông tin nhạy cảm.
- Raw request/response body.
- Raw exception message có thể chứa URL, SQL parameter hoặc credential.

### 4.2. Allowlist tốt hơn denylist

Denylist kiểu “che password, token, email” có thể bỏ sót field mới như `clientSecret`, `refresh_token`, `privateKey`, `bankAccount` hoặc field riêng của domain.

Allowlist chỉ ghi field đã được phê duyệt:

~~~java
public record OrderLogProjection(
    int itemCount,
    long totalQuantity
) {}
~~~

Projection này không có email, payment token, SKU, note hoặc raw order body. Nếu DTO sau này thêm `cardNumber`, projection không tự động ghi field mới đó.

### 4.3. Không dựa hoàn toàn vào regex để redact JSON

Regex có thể bỏ sót nested object/array, tên field khác kiểu viết, alias như `access_token`, giá trị đã encode hoặc token trong URL/header/free text.

Nếu cần giữ một phần payload, parse theo schema đã biết, tạo DTO/log projection riêng rồi serialize projection. Không serialize nguyên object rồi cố xóa secret sau cùng.

### 4.4. Body preview có giới hạn

Khi đã có projection an toàn và thực sự cần preview:
- Chỉ bật cho route/operation allowlist.
- Chỉ nhận media type và schema đã biết.
- Đặt byte cap nhỏ, ví dụ 128–512 bytes.
- Đánh dấu `truncated=true` và ghi original byte count.
- Không parse preview bị cắt như JSON đầy đủ.
- Không ghi body binary, multipart, file upload, SSE, NDJSON hoặc stream không giới hạn.
- Dùng sampling và thời hạn ngắn cho debug.

Byte cap phải tính theo UTF-8 bytes, không chỉ số ký tự. Một ký tự tiếng Việt có thể chiếm nhiều byte. Code mẫu ở mục 12 cắt tại ranh giới UTF-8 và chỉ nhận safe projection.

### 4.5. Không bật logging request details toàn cục ở production

Spring WebFlux có tùy chọn `enableLoggingRequestDetails(true)` cho codec. DEBUG/TRACE có thể ghi nhiều chi tiết request hơn; form parameters và headers được che mặc định, nhưng cấu hình bật full logging có thể làm lộ dữ liệu.

Đừng dùng cấu hình toàn cục này làm giải pháp body logging production. Nếu cần debug tạm thời, hãy xác định logger, route, dữ liệu được phép, thời gian tắt và policy của collector/APM.

## 5. Body trong WebFlux là stream

### 5.1. Request body chỉ được tiêu thụ một lần

Trong WebFlux, request body thường là `Flux<DataBuffer>`. Khi codec/controller đọc body, các buffer được tiêu thụ để decode DTO. Một filter tự subscribe hoặc đọc body trước controller có thể làm controller không còn dữ liệu.

~~~java
// Anti-pattern: tạo subscription riêng và consume body.
exchange.getRequest().getBody().subscribe(buffer -> {
    // log raw buffer
});
return chain.filter(exchange);
~~~

Đoạn này tách subscription khỏi filter chain, không replay body và có thể làm mất dữ liệu hoặc rò rỉ buffer.

### 5.2. DataBuffer có thể được pooled và reference-counted

Trên Netty, `DataBuffer` có thể bao bọc pooled `ByteBuf`. Buffer được giữ lại phải được release đúng lúc; buffer bị discard do filter/cancel/error cũng cần cleanup.

Khi tự đọc buffer, phải hiểu:
- Ai sở hữu buffer và khi nào release.
- Có cần `retain()` không.
- Buffer position có bị thay đổi không.
- Downstream nhận lại dữ liệu bằng cách nào.
- Error/cancel có giải phóng buffer chưa tiêu thụ không.

Spring cung cấp `DataBufferUtils` cho join, release, retain và thao tác byte stream. Dùng utility đúng cách vẫn không tự giải quyết việc replay request body.

### 5.3. Nếu thật sự phải capture body

Một implementation đầy đủ thường phải:
1. Kiểm tra route, media type, content length và policy trước khi đọc.
2. Aggregate có giới hạn byte, không join body vô hạn.
3. Nếu body vượt cap, bỏ capture theo policy và vẫn bảo đảm request được xử lý đúng.
4. Dùng `ServerHttpRequestDecorator` phát lại dữ liệu cho downstream.
5. Giải phóng buffer gốc và bản giữ lại đúng lifecycle.
6. Cleanup trên complete, error và cancel.
7. Xử lý body stream và trường hợp subscribe lại.
8. Kiểm thử body decoder, oversized request và pooled-buffer leak.

Đây là code hạ tầng dễ sai. Với JSON nghiệp vụ, cách đơn giản hơn thường là log safe projection sau khi controller đã decode DTO thay vì intercept raw bytes.

### 5.4. WebClient filter phải giữ response body

`ExchangeFilterFunction` có thể quan sát request/response metadata. Nếu filter đọc `ClientResponse` body để log rồi không propagate/replay body đã tiêu thụ, code phía sau như `bodyToMono()` sẽ không còn dữ liệu.

Filter metadata-only trong bài này không subscribe vào body nên không làm thay đổi lifecycle.

### 5.5. `maxInMemorySize` không phải body logger cap

`maxInMemorySize` giới hạn lượng dữ liệu codec có thể buffer trong một số thao tác decode/aggregate. Nó không tự giới hạn byte array của custom logger, queue của appender, trace attribute hoặc body copy do filter tự tạo. Hãy cấu hình codec limit và logging byte cap như hai controls riêng biệt.

## 6. Structured logging và chống log injection

### 6.1. Dùng message template cố định

~~~java
log.warn(
    "request_rejected requestId={} route={} reasonCode={}",
    requestId, route, reasonCode);
~~~

Tránh nối chuỗi trực tiếp:

~~~java
// Không nên: user input có thể chèn CR/LF vào log.
log.warn("Request failed: " + userInput);
~~~

Parameterized logging không tự động loại bỏ log injection. Nếu dữ liệu untrusted phải được ghi, sanitize/encode ký tự điều khiển, dùng JSON encoder chuẩn và giới hạn chiều dài field.

### 6.2. Không ghi raw exception message vô điều kiện

Exception message có thể chứa full URL/query, SQL statement/parameter, username/email, đường dẫn nội bộ hoặc header/credential do SDK đưa vào exception.

Ở request summary, thường chỉ cần exception type và error code. Stack trace đầy đủ có thể được ghi ở sink hạn chế quyền hơn khi có lý do. Không gửi stack trace cho client.

### 6.3. Correlation ID và session correlation

- Dùng request ID/trace ID do server hoặc tracing framework quản lý.
- Nếu nhận `X-Request-ID` từ client, validate chiều dài/ký tự và từ chối CR/LF.
- Không dùng raw session ID làm correlation key.
- Nếu cần đối chiếu session, cân nhắc HMAC/hash có key quản lý và rotation.
- Không đưa trace ID, request ID, user ID hoặc order ID thành metric tag.

## 7. Giới hạn chi phí metrics và traces

### 7.1. Cardinality

Một metric được phân biệt theo tổ hợp tag. Ví dụ:
- 6 HTTP methods.
- 30 route templates.
- 6 status groups.
- 4 regions.

Số tổ hợp lý thuyết là \(6 \times 30 \times 6 \times 4 = 4{,}320\) time series. Nếu thêm 100.000 user IDs, cardinality có thể tăng theo bậc lớn và làm monitoring backend tốn RAM, CPU, storage và query time.

### 7.2. Low cardinality và high cardinality

Spring Boot/Micrometer phân biệt:
- **Low cardinality:** tập giá trị hữu hạn như method, route template, outcome, status group.
- **High cardinality:** giá trị gần như không giới hạn như user ID, order ID hoặc request ID.

Trong Micrometer Observation, low-cardinality key-values được thêm vào metrics và traces; high-cardinality key-values chỉ thêm vào traces. Điều đó không có nghĩa mọi dữ liệu high-cardinality đều an toàn trong trace: privacy, access control, retention và chi phí trace vẫn cần kiểm soát.

### 7.3. Không dùng các giá trị này làm metric tags

- Full URL hoặc query string.
- Raw path có order/customer ID.
- Email, username, phone number.
- Request/trace/session ID.
- Search term, prompt hoặc body content.
- Exception message.
- Arbitrary header values.
- Token hoặc secret.

Dùng URI template như `/api/orders/{id}` thay cho `/api/orders/839174`. Dùng status/outcome thay vì exception message. Dùng operation name hữu hạn do code định nghĩa.

### 7.4. HTTP observations của Spring Boot

Spring Boot tự instrument WebFlux server requests với `http.server.requests`. WebClient được instrument khi tạo từ `WebClient.Builder` auto-configured của Spring Boot; metric mặc định là `http.client.requests`.

Tránh thêm timer thủ công cho cùng một request chỉ để ghi duration lần nữa, trừ khi đo một boundary khác có tên rõ ràng. Instrument trùng có thể làm dashboard đếm hai lần.

### 7.5. Tracing sampling

Một trace có thể chứa nhiều span, tags và events. Nếu 100% traffic tạo trace trong hệ thống RPS cao, chi phí tăng nhanh.

Policy thường gặp:
- Sample tỷ lệ thấp cho success traffic ổn định.
- Giữ tỷ lệ cao hơn cho error/latency vượt ngưỡng bằng tail sampling nếu collector hỗ trợ.
- Không ghi body/header nhạy cảm vào span attributes.
- Giới hạn số span events và độ dài attribute.
- Giữ trace ID để correlate với logs, không copy raw payload sang trace.

Sampling không thay thế security event logging bắt buộc; các sự kiện security/audit phải theo policy riêng.

## 8. Sampling, rate limit và retention

### 8.1. Một policy vận hành mẫu

| Route/traffic | Metadata | Body preview |
| --- | --- | --- |
| Health/readiness | Metrics thường là đủ | Không |
| CRUD thông thường | Có, theo mức phù hợp | Không |
| Login/token/credential | Security event đã chọn lọc | Không |
| Payment/PII/health | Metadata tối thiểu + audit có kiểm soát | Không |
| Upload/multipart/binary | Byte count, duration, outcome | Không |
| SSE/NDJSON/WebSocket | Connect/disconnect, duration, error, event count | Không aggregate |
| Route debug đã allowlist | Có, sampling | Safe projection có byte cap |

### 8.2. Sampling trước khi đọc body

Nếu đã đọc và serialize body rồi mới quyết định bỏ log, chi phí memory/CPU vẫn xảy ra. Hãy quyết định sampling/route allowlist trước bước capture.

Không sampling các audit/security events bắt buộc. Với success traffic lớn, sampling metadata theo tỷ lệ; với lỗi lặp liên tục, rate-limit log theo fingerprint nhưng vẫn giữ counters/metrics.

### 8.3. Retention và access control

- Tách retention cho operational logs, security logs, audit và traces.
- Chỉ nhóm có nhiệm vụ mới được đọc log nhạy cảm.
- Dùng TLS khi truyền log qua mạng không tin cậy.
- Mã hóa storage/backup.
- Ghi audit cho hoạt động truy cập log nhạy cảm.
- Xóa debug dump, bản export và backup theo chính sách khi hết hạn.
- Kiểm soát quyền ở dashboard, query API, export và backup.

## 9. Ghi log metadata ở WebFlux bằng `WebFilter`

Một `WebFilter` có thể quan sát request lifecycle mà không đọc body. Ví dụ ghi request ID, method, route template, status, terminal signal và duration.

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class RequestSummaryWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(RequestSummaryWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();
        String requestId = exchange.getLogPrefix();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
            .doOnError(error ->
                log.warn(
                    "http_request_failed requestId={} method={} exceptionType={}",
                    requestId,
                    method,
                    error.getClass().getSimpleName()))
            .doFinally(signal -> {
                String route = exchange.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                if (route == null) {
                    route = "unmatched";
                }

                var status = exchange.getResponse().getStatusCode();
                String statusValue =
                    status == null ? "unset" : Integer.toString(status.value());

                long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

                log.info(
                    "http_request_completed requestId={} method={} route={} status={} signal={} durationMs={}",
                    requestId,
                    method,
                    route,
                    statusValue,
                    signal.name(),
                    durationMs);
            });
    }
}
~~~

Điểm quan trọng:
- Filter không gọi `getBody()` và không consume request body.
- `getLogPrefix()` dùng request-specific identity; không dựa vào thread ID.
- `BEST_MATCHING_PATTERN_ATTRIBUTE` cho route template như `/api/orders/{id}` sau khi handler được chọn.
- Không log full URI, query string, headers, cookies hoặc exception message.
- `doFinally` ghi `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`; cancel không đồng nghĩa response thành công.
- Status có thể chưa set nếu lỗi xảy ra trước response commit, vì vậy ví dụ ghi `unset`.

Filter này không thay thế `http.server.requests` metrics hoặc tracing.

## 10. Ghi log metadata outbound bằng WebClient filter

Filter outbound có thể ghi operation label, method, status và duration. Gắn operation name do code quy định thay vì log full URL/query.

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(CatalogWebClientConfiguration.class);

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        ExchangeFilterFunction metadataLog = (request, next) -> {
            long startedAt = System.nanoTime();

            String operation = request.attribute("observability.operation")
                .map(Object::toString)
                .map(SafeLogValues::operation)
                .orElse("unclassified");

            return next.exchange(request)
                .doOnNext(response -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                        "outbound_http operation={} method={} status={} durationMs={}",
                        operation,
                        request.method().name(),
                        response.statusCode().value(),
                        durationMs);
                })
                .doOnError(error -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.warn(
                        "outbound_http_failed operation={} method={} exceptionType={} durationMs={}",
                        operation,
                        request.method().name(),
                        error.getClass().getSimpleName(),
                        durationMs);
                });
        };

        return builder.filter(metadataLog).build();
    }
}
~~~

Khi gọi WebClient:

~~~java
return catalogWebClient.get()
    .uri("/items/{id}", id)
    .attribute("observability.operation", "catalog.item_lookup")
    .retrieve()
    .bodyToMono(ItemView.class);
~~~

Không log `request.url()` một cách vô điều kiện. URL có thể chứa ID, query, user info hoặc token. Filter này không đọc response body nên `bodyToMono()` phía sau vẫn consume body bình thường.

## 11. Safe projection và body preview có giới hạn byte

### 11.1. Request DTO có thể chứa secret

~~~java
package com.example.observability;

import java.util.List;

public record CreateOrderRequest(
    String customerEmail,
    String paymentToken,
    List<LineItem> items,
    String customerNote
) {}

record LineItem(String sku, int quantity) {}
~~~

Không serialize nguyên `CreateOrderRequest` vào log. Tạo projection riêng:

~~~java
package com.example.observability;

import java.util.List;
import java.util.Objects;

public record OrderLogProjection(
    int itemCount,
    long totalQuantity
) {
    public static OrderLogProjection from(
            CreateOrderRequest request) {

        List<LineItem> items =
            request.items() == null ? List.of() : request.items();

        long totalQuantity = items.stream()
            .filter(Objects::nonNull)
            .mapToLong(LineItem::quantity)
            .sum();

        return new OrderLogProjection(
            items.size(),
            totalQuantity);
    }
}
~~~

Projection không chứa email, payment token, SKU hoặc note. Nếu DTO sau này thêm `cardNumber`, projection không tự động ghi field mới.

### 11.2. Utility giới hạn preview theo UTF-8 bytes

~~~java
package com.example.observability;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class SafeBodyPreview {

    private SafeBodyPreview() {}

    public record Preview(
        String text,
        int originalBytes,
        boolean truncated
    ) {}

    public static Preview from(
            Object allowlistedProjection,
            ObjectMapper mapper,
            int maxBytes) throws JsonProcessingException {

        if (maxBytes < 1) {
            throw new IllegalArgumentException(
                "maxBytes must be positive");
        }

        // Chỉ truyền projection đã allowlist, không truyền raw DTO.
        byte[] json = mapper.writeValueAsBytes(allowlistedProjection);
        int end = Math.min(json.length, maxBytes);

        // Không cắt giữa một ký tự UTF-8 đa byte.
        while (end > 0
                && end < json.length
                && (json[end] & 0xC0) == 0x80) {
            end--;
        }

        String preview = new String(
            json, 0, end, StandardCharsets.UTF_8);

        return new Preview(
            preview,
            json.length,
            json.length > maxBytes);
    }
}
~~~

`Preview.text` có thể là JSON prefix chưa hoàn chỉnh khi bị cắt; hãy xem nó là preview để đọc, không parse lại như JSON đầy đủ. `originalBytes` là kích thước projection trước khi cắt. Raw body không được đưa vào utility.

### 11.3. Safe label cho WebClient operation

~~~java
package com.example.observability;

public final class SafeLogValues {

    private SafeLogValues() {}

    public static String operation(String raw) {
        if (raw == null || raw.isBlank()) {
            return "unclassified";
        }

        String safe = raw.replaceAll(
            "[^A-Za-z0-9_.-]", "_");

        return safe.substring(0, Math.min(60, safe.length()));
    }
}
~~~

Trong production, operation label nên là constant do code đặt. Hàm này là lớp bảo vệ bổ sung nếu attribute đến từ nguồn khác; nó không phải cơ chế redact raw user input.

## 12. Cấu hình Actuator và Micrometer

### 12.1. Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Khi tạo WebClient, inject `WebClient.Builder` do Spring Boot cấu hình để giữ instrumentation mặc định. Tự tạo `WebClient.create()` độc lập có thể bỏ qua customizer/observation mà Boot gắn vào builder.

### 12.2. `application.properties`

~~~properties
spring.application.name=webflux-safe-observability

management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.metrics.distribution.percentiles-histogram.http.server.requests=true

logging.level.com.example.observability=INFO
logging.level.org.springframework.web=INFO
~~~

Actuator endpoints cần được bảo vệ bằng authentication và network policy phù hợp; không expose metrics/prometheus công khai cho Internet nếu không có kiểm soát.

### 12.3. Các meter hữu ích

| Meter / nhóm | Câu hỏi |
| --- | --- |
| `http.server.requests` | Request inbound mất bao lâu, status/outcome thế nào? |
| `http.client.requests` | Outbound WebClient call chậm hoặc lỗi ở đâu? |
| JVM memory/buffer pools | Heap/direct memory có tăng không? |
| Process CPU/file descriptors | Instance có gần giới hạn tài nguyên không? |
| Logback event metrics | Log rate hoặc error logs tăng đột biến không? |
| Custom preview count | Bao nhiêu preview được ghi/truncate? |

Nếu cần custom metric, dùng tag hữu hạn như `operation`, `outcome`, `route`. Không dùng body, user ID, order ID hoặc request ID làm tag.

## 13. Sampling, rate limit và retention

- Log metadata cho mọi 5xx nếu policy vận hành yêu cầu.
- Sampling một tỷ lệ nhỏ success traffic trên route lớn.
- Giữ security/audit events bắt buộc theo policy riêng; không bỏ chúng do trace sampling.
- Rate-limit log theo fingerprint khi một lỗi lặp liên tục, nhưng vẫn giữ metric counter để biết tổng số lần.
- Quyết định sampling trước khi đọc body; nếu đã serialize body rồi mới bỏ log, chi phí memory/CPU vẫn xảy ra.
- Debug capture phải có route allowlist, byte cap, thời gian kết thúc và người chịu trách nhiệm.
- Tách retention cho operational logs, security logs, audit và traces.
- Chỉ nhóm có nhiệm vụ mới được đọc log nhạy cảm.
- Dùng TLS khi truyền log qua mạng không tin cậy; mã hóa storage/backup.
- Ghi audit cho hoạt động truy cập log nhạy cảm.
- Xóa debug dump, bản export và backup theo chính sách khi hết hạn.

## 14. Tình huống điều tra sự cố không cần raw body

Giả sử p99 của `POST /api/orders` tăng từ 150 ms lên 2 giây:

1. Mở dashboard `http.server.requests`, lọc route `/api/orders` và status.
2. Xác định thời điểm bắt đầu và phiên bản deployment.
3. Chọn trace đại diện cho request chậm.
4. Xem span outbound/database để biết thời gian nằm ở dependency nào.
5. Dùng request ID/trace ID tìm structured logs cùng request.
6. Kiểm tra error code, duration, operation label và byte count.
7. Nếu nghi payload lớn, so sánh request byte distribution hoặc `itemCount`/`totalQuantity` đã allowlist.
8. Chỉ bật capture tạm thời cho route/test account đã được duyệt nếu metadata chưa đủ.
9. Xóa/expire capture sau khi điều tra.

Trace và metrics cho biết vị trí chậm; metadata log nối request với kết quả. Raw body thường không giúp trả lời database query mất 1.8 giây ở đâu.

## 15. Project runnable: Spring Boot 4.0.9 + Java 17+

Project minh họa:
- `WebFilter` log HTTP metadata.
- `WebClient` filter log outbound metadata mà không đọc response body.
- Order request có email/token/note nhưng chỉ log projection `itemCount` và `totalQuantity`.
- Safe preview bị giới hạn 128 bytes.
- Tests xác nhận projection không chứa secret, truncation đúng byte và API không echo sensitive fields.

Đây là demo observability. Nó không bật raw body logging và không tự đọc `DataBuffer`.

### 15.1. Cấu trúc

~~~text
webflux-safe-observability/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/observability/
│   ├── ObservabilityApplication.java
│   ├── RequestSummaryWebFilter.java
│   ├── CatalogWebClientConfiguration.java
│   ├── SafeLogValues.java
│   ├── SafeBodyPreview.java
│   ├── CreateOrderRequest.java
│   ├── OrderLogProjection.java
│   ├── OrderResponse.java
│   ├── OrderService.java
│   └── OrderController.java
└── src/test/java/com/example/observability/
    ├── SafeBodyPreviewTest.java
    └── OrderApiIntegrationTest.java
~~~

### 15.2. `pom.xml`

Spring Boot 4.0.9 và Java 17+; version dependencies được quản lý bởi Boot parent.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-safe-observability</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-registry-prometheus</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 15.3. `ObservabilityApplication.java`

~~~java
package com.example.observability;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ObservabilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObservabilityApplication.class, args);
    }
}
~~~

### 15.4. `RequestSummaryWebFilter.java`

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.LOWEST_PRECEDENCE)
public class RequestSummaryWebFilter implements WebFilter {

    private static final Logger log =
        LoggerFactory.getLogger(RequestSummaryWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        long startedAt = System.nanoTime();
        String requestId = exchange.getLogPrefix();
        String method = exchange.getRequest().getMethod().name();

        return chain.filter(exchange)
            .doOnError(error ->
                log.warn(
                    "http_request_failed requestId={} method={} exceptionType={}",
                    requestId,
                    method,
                    error.getClass().getSimpleName()))
            .doFinally(signal -> {
                String route = exchange.getAttribute(
                    HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);

                if (route == null) {
                    route = "unmatched";
                }

                var status = exchange.getResponse().getStatusCode();
                String statusValue =
                    status == null ? "unset" : Integer.toString(status.value());

                long durationMs =
                    (System.nanoTime() - startedAt) / 1_000_000;

                log.info(
                    "http_request_completed requestId={} method={} route={} status={} signal={} durationMs={}",
                    requestId,
                    method,
                    route,
                    statusValue,
                    signal.name(),
                    durationMs);
            });
    }
}
~~~

### 15.5. `CatalogWebClientConfiguration.java`

~~~java
package com.example.observability;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class CatalogWebClientConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(CatalogWebClientConfiguration.class);

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        ExchangeFilterFunction metadataLog = (request, next) -> {
            long startedAt = System.nanoTime();

            String operation = request.attribute("observability.operation")
                .map(Object::toString)
                .map(SafeLogValues::operation)
                .orElse("unclassified");

            return next.exchange(request)
                .doOnNext(response -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.info(
                        "outbound_http operation={} method={} status={} durationMs={}",
                        operation,
                        request.method().name(),
                        response.statusCode().value(),
                        durationMs);
                })
                .doOnError(error -> {
                    long durationMs =
                        (System.nanoTime() - startedAt) / 1_000_000;

                    log.warn(
                        "outbound_http_failed operation={} method={} exceptionType={} durationMs={}",
                        operation,
                        request.method().name(),
                        error.getClass().getSimpleName(),
                        durationMs);
                });
        };

        return builder.filter(metadataLog).build();
    }
}
~~~

### 15.6. `SafeLogValues.java`

~~~java
package com.example.observability;

public final class SafeLogValues {

    private SafeLogValues() {}

    public static String operation(String raw) {
        if (raw == null || raw.isBlank()) {
            return "unclassified";
        }

        String safe = raw.replaceAll(
            "[^A-Za-z0-9_.-]", "_");

        return safe.substring(0, Math.min(60, safe.length()));
    }
}
~~~

### 15.7. `CreateOrderRequest.java`

~~~java
package com.example.observability;

import java.util.List;

public record CreateOrderRequest(
    String customerEmail,
    String paymentToken,
    List<LineItem> items,
    String customerNote
) {}

record LineItem(String sku, int quantity) {}
~~~

### 15.8. `OrderLogProjection.java`

~~~java
package com.example.observability;

import java.util.List;
import java.util.Objects;

public record OrderLogProjection(
    int itemCount,
    long totalQuantity
) {
    public static OrderLogProjection from(
            CreateOrderRequest request) {

        List<LineItem> items =
            request.items() == null ? List.of() : request.items();

        long totalQuantity = items.stream()
            .filter(Objects::nonNull)
            .mapToLong(LineItem::quantity)
            .sum();

        return new OrderLogProjection(
            items.size(),
            totalQuantity);
    }
}
~~~

### 15.9. `SafeBodyPreview.java`

~~~java
package com.example.observability;

import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class SafeBodyPreview {

    private SafeBodyPreview() {}

    public record Preview(
        String text,
        int originalBytes,
        boolean truncated
    ) {}

    public static Preview from(
            Object allowlistedProjection,
            ObjectMapper mapper,
            int maxBytes) throws JsonProcessingException {

        if (maxBytes < 1) {
            throw new IllegalArgumentException(
                "maxBytes must be positive");
        }

        byte[] json = mapper.writeValueAsBytes(allowlistedProjection);
        int end = Math.min(json.length, maxBytes);

        while (end > 0
                && end < json.length
                && (json[end] & 0xC0) == 0x80) {
            end--;
        }

        String preview = new String(
            json, 0, end, StandardCharsets.UTF_8);

        return new Preview(
            preview,
            json.length,
            json.length > maxBytes);
    }
}
~~~

### 15.10. `OrderResponse.java`

~~~java
package com.example.observability;

public record OrderResponse(
    String id,
    int itemCount
) {}
~~~

### 15.11. `OrderService.java`

~~~java
package com.example.observability;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

    private final ObjectMapper objectMapper;

    public OrderService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public Mono<OrderResponse> create(
            CreateOrderRequest request,
            String requestId) {

        return Mono.fromCallable(() -> {
            OrderLogProjection projection =
                OrderLogProjection.from(request);

            SafeBodyPreview.Preview preview =
                SafeBodyPreview.from(
                    projection, objectMapper, 128);

            log.info(
                "order_body_summary requestId={} preview={} originalBytes={} truncated={}",
                requestId,
                preview.text(),
                preview.originalBytes(),
                preview.truncated());

            return new OrderResponse(
                UUID.randomUUID().toString(),
                projection.itemCount());
        });
    }
}
~~~

### 15.12. `OrderController.java`

~~~java
package com.example.observability;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<OrderResponse>> create(
            @RequestBody CreateOrderRequest request,
            ServerWebExchange exchange) {

        return service.create(request, exchange.getLogPrefix())
            .map(response ->
                ResponseEntity.status(HttpStatus.ACCEPTED)
                    .body(response));
    }
}
~~~

### 15.13. `SafeBodyPreviewTest.java`

~~~java
package com.example.observability;

import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SafeBodyPreviewTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void projectionExcludesSensitiveRequestFields()
            throws Exception {

        CreateOrderRequest request = new CreateOrderRequest(
            "alice@example.test",
            "secret-payment-token",
            List.of(new LineItem("PRIVATE-SKU", 2)),
            "confidential customer note");

        OrderLogProjection projection =
            OrderLogProjection.from(request);

        SafeBodyPreview.Preview preview =
            SafeBodyPreview.from(projection, mapper, 128);

        assertTrue(preview.text().contains("itemCount"));
        assertTrue(preview.text().contains("totalQuantity"));
        assertFalse(preview.text().contains("alice@example.test"));
        assertFalse(preview.text().contains("secret-payment-token"));
        assertFalse(preview.text().contains("PRIVATE-SKU"));
        assertFalse(preview.text().contains("confidential customer note"));
    }

    @Test
    void previewDoesNotExceedUtf8ByteLimit()
            throws Exception {

        record SafeProjection(String label) {}

        SafeProjection projection =
            new SafeProjection("x".repeat(500));

        SafeBodyPreview.Preview preview =
            SafeBodyPreview.from(projection, mapper, 64);

        assertTrue(preview.truncated());
        assertTrue(preview.originalBytes() > 64);
        assertTrue(
            preview.text().getBytes(StandardCharsets.UTF_8).length <= 64);
    }

    @Test
    void operationLabelCannotInjectNewLogLines() {
        String safe =
            SafeLogValues.operation("catalog.lookup\nERROR forged");

        assertFalse(safe.contains("\n"));
        assertFalse(safe.contains("\r"));
        assertTrue(safe.matches("[A-Za-z0-9_.-]+"));
    }
}
~~~

Test thứ hai dùng safe projection giả lập có string dài để kiểm tra byte cap. Trong production, projection phải được allowlist trước khi gọi utility; byte cap không thay thế redaction.

### 15.14. `OrderApiIntegrationTest.java`

~~~java
package com.example.observability;

import java.time.Duration;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderApiIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private WebTestClient http() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .responseTimeout(Duration.ofSeconds(5))
            .build();
    }

    @Test
    void createOrderReturnsSummaryWithoutEchoingSecrets() {
        CreateOrderRequest request = new CreateOrderRequest(
            "alice@example.test",
            "secret-payment-token",
            List.of(new LineItem("PRIVATE-SKU", 2)),
            "confidential customer note");

        http().post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .exchange()
            .expectStatus().isAccepted()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.id").isNotEmpty()
                .jsonPath("$.itemCount").isEqualTo(1);
    }
}
~~~

HTTP test xác nhận response chỉ trả order ID và số item, không echo request DTO. `SafeBodyPreviewTest` kiểm tra projection log; nếu cần kiểm tra output logging backend, bổ sung test appender theo logging framework của dự án.

### 15.15. Chạy project

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Gửi request:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customerEmail":"alice@example.test","paymentToken":"secret-payment-token","items":[{"sku":"PRIVATE-SKU","quantity":2}],"customerNote":"confidential customer note"}'
~~~

Response minh họa:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"id":"<generated-uuid>","itemCount":1}
~~~

Log summary dự kiến chỉ có projection:

~~~text
order_body_summary requestId=[...] preview={"itemCount":1,"totalQuantity":2} originalBytes=... truncated=false
~~~

Request ID và UUID được sinh động; không assert giá trị cụ thể trong test. Log không chứa email, payment token, SKU hoặc customer note.

Có thể xem metrics nếu Actuator endpoints được expose và bảo vệ phù hợp:

~~~bash
curl http://localhost:8080/actuator/metrics/http.server.requests
curl http://localhost:8080/actuator/metrics/logback.events
curl http://localhost:8080/actuator/prometheus
~~~

Tên meter có thể được chuẩn hóa khác nhau khi export sang Prometheus. `/actuator/metrics` dùng tên meter Micrometer trước bước normalization.

## 16. Kiểm thử logging policy trong dự án thực

| Kiểm thử | Điều cần xác nhận |
| --- | --- |
| Secret canary | Token/password giả không xuất hiện trong log event |
| PII canary | Email/phone/address không xuất hiện nếu không được phép |
| CR/LF injection | User input không tạo thêm log line giả |
| Byte cap | Preview không vượt giới hạn |
| Oversized body | Request vẫn được xử lý khi không capture |
| Multipart/binary | Body không bị stringify hoặc aggregate |
| Streaming | SSE/NDJSON không bị gom thành một body lớn |
| Cancellation | Buffer/listener được cleanup khi client ngắt |
| DataBuffer leak | Không có pooled buffer leak sau nhiều request |
| Route exclusion | Login/payment/upload routes không có body preview |
| Sampling | Tỷ lệ log phù hợp policy |
| Retention | Debug capture hết hạn và bản export được xử lý |
| Access | Người không có quyền không thể query/export log nhạy cảm |

Có thể dùng Logback `ListAppender` hoặc appender test riêng để thu event và assert không có chuỗi canary. Không chỉ kiểm tra console vì appender/collector có thể format và forward dữ liệu theo cách khác.

## 17. Runbook khi phát hiện body hoặc secret đã bị ghi log

1. Xác định loại dữ liệu, route, thời gian, instance và nơi nhận log.
2. Tắt capture ở đúng logger/filter/agent và xác nhận không còn event mới.
3. Xác định credential có còn hiệu lực; rotate/revoke nếu cần.
4. Hạn chế quyền truy cập log index, export và backup liên quan.
5. Xác định các bản sao: stdout, container runtime, local files, collector, SIEM, APM, object storage và backup.
6. Giữ bằng chứng cần thiết theo incident/legal policy; không tự ý xóa audit evidence.
7. Xóa/redact bản sao theo quy trình retention và incident response được phê duyệt.
8. Kiểm tra truy cập bất thường vào log trong thời gian dữ liệu bị lộ.
9. Bổ sung test canary và policy check trong CI.
10. Ghi lại nguyên nhân, phạm vi, remediation và người chịu trách nhiệm.

Nếu dữ liệu đã được forward sang bên thứ ba, đánh giá theo data processing agreement và quy trình incident của tổ chức. Xóa ở dashboard không bảo đảm dữ liệu đã biến mất khỏi index, replica hoặc backup.

## 18. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Log nguyên request DTO | Lộ field mới hoặc secret hiện có | Tạo allowlisted projection |
| Chỉ redact bằng regex | Bỏ sót nested/alias/custom fields | Parse schema và allowlist |
| Cắt body rồi nghĩ dữ liệu an toàn | Secret có thể nằm ở phần đầu | Redact/allowlist trước, truncate sau |
| Subscribe request body trong WebFilter | Body bị consume trước controller | Không đọc body trong metadata filter |
| Join DataBuffer không giới hạn | Tăng memory, có thể OOM | Byte cap và route allowlist |
| Đọc DataBuffer nhưng không release | Pooled memory leak | Quản lý retain/release/discard |
| Consume WebClient response body trong filter | Downstream bodyToMono không còn dữ liệu | Propagate/replay body đúng hoặc chỉ log metadata |
| Log full URL/query | Lộ token/PII trong URL | Route template và operation label |
| Log raw exception message | Lộ SQL, host, credential | Exception type/error code |
| Dùng thread name làm request ID | Không correlate khi đổi thread | Request ID/trace context |
| Dùng userId/orderId làm metric tag | Cardinality tăng rất lớn | Route/operation/status hữu hạn |
| Ghi body vào trace span | Trace backend lưu payload nhạy cảm | Chỉ metadata an toàn |
| Bật TRACE/DEBUG toàn cục | Log volume và rò rỉ dữ liệu | Scope logger, route, sampling, TTL |
| Chỉ redact ở dashboard | Raw log đã nằm trong backend | Redact tại nguồn |
| Async appender không có queue policy | Queue đầy hoặc drop/block khó kiểm soát | Bounded queue, metrics và severity policy |
| Giữ debug dump vô thời hạn | Tăng rủi ro và chi phí | Retention có thời hạn |
| Gộp audit và operational logs | Mất semantics, retention không phù hợp | Tách mục đích và quyền |
| Không test secret canary | Regression lọt production | Unit/integration tests trên log event |

## 19. Checklist production

- [ ] Có mục đích rõ cho từng loại log, metric và trace.
- [ ] Metadata-only là mặc định cho HTTP request/response.
- [ ] Không log password, token, cookie, session ID, key hoặc payment data.
- [ ] Không serialize nguyên request/response DTO vào log.
- [ ] Body preview chỉ có trên route allowlist và schema được duyệt.
- [ ] Projection loại secret trước khi serialize.
- [ ] Byte cap tính theo UTF-8 bytes; preview có cờ truncated.
- [ ] Không aggregate multipart, binary, SSE, NDJSON hoặc stream không giới hạn để log.
- [ ] Không bật `enableLoggingRequestDetails(true)` toàn cục trong production.
- [ ] WebFilter không tự subscribe/consume request body.
- [ ] DataBuffer được release/retain/replay đúng khi có custom capture.
- [ ] WebClient filter không consume response body nếu downstream còn cần.
- [ ] Log có request ID/trace ID, method, route template, status và duration.
- [ ] Không dùng full URL/query hoặc exception message làm log field mặc định.
- [ ] Structured logging dùng template cố định và chống CR/LF injection.
- [ ] Metrics chỉ dùng low-cardinality tags.
- [ ] High-cardinality trace attributes cũng qua privacy review.
- [ ] Spring Boot HTTP observations không bị instrument trùng.
- [ ] Sampling không làm mất security/audit events bắt buộc.
- [ ] Async logging queue, overflow và dropped-event metrics được theo dõi.
- [ ] Log storage được mã hóa, phân quyền và có retention.
- [ ] Có test secret canary, PII canary, truncation, route exclusion và log injection.
- [ ] Có runbook khi secret bị ghi vào log.
- [ ] Có staging verification qua collector/APM thực tế, không chỉ console local.

## 20. Bài tập thực hành

**Bài 1 – Metadata filter.** Thêm `RequestSummaryWebFilter`, gửi 10 request và xác nhận mỗi event có request ID, method, route template, status và duration.

**Bài 2 – Route template.** Gọi `/api/orders/1`, `/api/orders/2`, `/api/orders/3`; xác nhận log/metrics dùng cùng route template.

**Bài 3 – Secret canary.** Gửi `paymentToken=CANARY_SECRET_123`; kiểm tra response và log projection không chứa chuỗi canary.

**Bài 4 – Allowlist.** Thêm `customerPhone` vào request DTO; xác nhận projection không tự động xuất hiện field mới.

**Bài 5 – UTF-8 byte cap.** Tạo safe projection có chuỗi tiếng Việt dài; xác nhận preview không cắt giữa ký tự và không vượt cap.

**Bài 6 – Log injection.** Gửi field có `\r\nERROR forged`; xác nhận không tạo log event giả.

**Bài 7 – WebClient filter.** Gắn operation `catalog.lookup`; xác nhận outbound log có method/status/duration và response body vẫn decode được.

**Bài 8 – DataBuffer.** Tạo request decorator trong test riêng; xác nhận body được replay chính xác và pooled buffer được release khi complete/error/cancel.

**Bài 9 – Cardinality.** Tạo dashboard với `route`, `method`, `status`; so sánh số series khi thêm user ID tag. Không triển khai user ID tag trong production.

**Bài 10 – Sampling.** Bật sampling cho success metadata, giữ error/security events theo policy; xác nhận counters vẫn phản ánh đầy đủ traffic.

**Bài 11 – Retention.** Tạo debug capture giả lập có TTL, xác nhận hết hạn thì không còn truy cập được qua search/export.

**Bài 12 – Incident drill.** Cố ý phát hiện secret canary trong log test; thực hành tắt logger, revoke secret, tìm bản sao và lập remediation.

## 21. Tài liệu tham khảo chính thức

1. Spring Boot 4.0 – Observability, Micrometer Observation, low/high cardinality và context propagation: https://docs.spring.io/spring-boot/4.0/reference/actuator/observability.html
2. Spring Boot 4.0 – Metrics và WebFlux `http.server.requests` / WebClient `http.client.requests`: https://docs.spring.io/spring-boot/4.0/reference/actuator/metrics.html
3. Spring Framework 7.1 – WebFlux Reactive Core, log ID, sensitive logging và DataBuffer: https://docs.spring.io/spring/reference/7.1/web/webflux/reactive-spring.html
4. Spring Framework – Data Buffers and Codecs, pooled buffer, release/retain và `DataBufferUtils`: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
5. Spring Framework – WebClient filters và response body lifecycle: https://docs.spring.io/spring/reference/7.1/web/webflux-webclient/client-filter.html
6. Spring Framework – WebClient API và non-blocking behavior: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
7. OWASP Logging Cheat Sheet – data to exclude, structured logging, access control, retention và log injection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
8. OWASP Session Management Cheat Sheet – không log raw session ID: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
9. RFC 5424 – The Syslog Protocol: https://www.rfc-editor.org/rfc/rfc5424
10. Micrometer Observation – concepts và key-value cardinality: https://docs.micrometer.io/micrometer/reference/observation.html

**Tự đánh giá cuối:** Vì sao body cap không thay thế redaction? Tại sao WebFilter không nên tự subscribe vào request body? Nếu filter đọc `ClientResponse` body rồi không replay, điều gì xảy ra với `bodyToMono()` downstream? Vì sao request ID phù hợp trong log nhưng không phù hợp làm metric tag? Khi nào nên log `itemCount` thay vì raw order JSON? Nếu bạn có thể correlate một request qua metadata, metrics và trace mà không lưu token, PII hoặc toàn bộ body, bạn đã thiết kế observability WebFlux với chi phí và rủi ro hợp lý.
