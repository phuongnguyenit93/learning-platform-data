# WebClient bất đồng bộ, hủy lời gọi và xử lý lỗi

Một REST API cần đọc giá và tồn kho từ hai dịch vụ có độ trễ khác nhau. Khi nhiều request chờ mạng, cách gọi đồng bộ gây áp lực lên thread pool. **Spring WebClient** cung cấp HTTP reactive để tổ hợp I/O không chặn, đặt deadline, xử lý lỗi và hủy subscription.

**Hủy Mono không bảo đảm server đích đã ngừng**, và **timeout không chứng minh operation thất bại**. Đặc biệt khi tạo đơn/hoàn tiền, cần idempotency và đối soát. Bài thuộc chương **Client Java** của **INTEGRATION_API_REST**, gắn HTTP, Java/Spring, bảo mật và kiểm thử.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Dùng **WebClient**, **Mono**, **Flux** để gửi HTTP bất đồng bộ mà không gọi **block()** trong pipeline reactive.
2. Phân biệt **subscription**, **cancellation**, **timeout**, **HTTP status lỗi** và **lỗi kết nối**; hiểu giới hạn hủy công việc ở bên kia mạng.
3. Thiết kế error mapping cho **4xx/5xx**, response body Problem Details, **429 Retry-After**, lỗi decode và lỗi downstream.
4. Thiết lập **connect timeout, response timeout, total deadline, connection pool, concurrency limit** theo SLO.
5. Retry có chọn lọc, backoff/jitter và bảo vệ **POST/PUT** bằng idempotency, precondition hoặc đối soát trạng thái.
6. Tránh rò token, SSRF, trộn dữ liệu tenant; giữ context bảo mật và trace qua pipeline.
7. Kiểm thử request/response, timeout, cancel, retry và kết quả không chắc chắn bằng **StepVerifier**, HTTP mock server và fault injection.

**WebClient xử lý HTTP; nghiệp vụ quyết định retry, quyền và kết quả commit.**

## 2. Mô hình bất đồng bộ: từ Publisher đến HTTP

**WebClient** tạo reactive publisher: **Mono<T>** có 0–1 phần tử, **Flux<T>** có nhiều phần tử. Với publisher “cold”, dựng pipeline **chưa gửi HTTP**; subscription mới kích hoạt.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Spring API
    participant W as WebClient
    participant P as Remote pricing API
    C->>W: Tạo Mono<Price>
    Note over W: Chưa gửi I/O khi chỉ dựng pipeline
    C->>W: HTTP framework subscribe
    W->>P: GET /v1/prices/{id}
    P-->>W: 200 + JSON
    W-->>C: onNext(Price), onComplete()
~~~

Trong **WebFlux**, controller trả Mono/Flux để framework quản lý subscription và cancellation. **MVC** cũng dùng WebClient được qua **CompletableFuture/DeferredResult/Mono** hoặc ranh giới blocking có chủ đích. Không **block()** trên event loop.

~~~java
// WebFlux: framework subscribe vào Mono để sinh HTTP response.
@GetMapping("/v1/products/{id}/price")
public Mono<PriceView> price(@PathVariable String id) {
    return pricingClient.findPrice(id);
}
~~~

Publisher cold được **subscribe hai lần** thường gửi **hai request**. Không gọi subscribe() trong controller rồi trả response ngay; hãy trả publisher hoặc quản lý job bền vững.

### 2.1. Async không có nghĩa mọi bước đều non-blocking

| Thành phần | Đặc tính | Lưu ý |
|---|---|---|
| WebClient + Reactor Netty | Gửi/nhận HTTP không chặn | Connection pool, network timeout vẫn giới hạn |
| Reactor operator map | Xử lý đồng bộ khi có tín hiệu | Không gọi JDBC, Thread.sleep hay CPU dài |
| RestTemplate/RestClient đồng bộ | Blocking đối với caller | Phù hợp ở MVC, không đặt trên event loop |
| JDBC/JPA, SDK chỉ có API sync | Blocking | Dùng scheduler thích hợp hoặc giữ mô hình imperative |
| R2DBC, reactive driver hỗ trợ thật | Non-blocking theo driver | Không tự bảo đảm truy vấn hoặc transaction tối ưu |

Khi bắt buộc gọi blocking API, dùng **Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())** và giới hạn tải. Đây là cầu nối, **không biến JDBC thành non-blocking**.

## 3. Hợp đồng HTTP của một Java client

Ví dụ client đọc giá:

~~~http
GET /v1/prices/p-17 HTTP/1.1
Host: pricing.internal.example
Accept: application/json
Authorization: Bearer <service-token>
X-Request-Id: req-31
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=15
ETag: "price-p17-v8"

{"productId":"p-17","amountMinor":3590000,"currency":"VND"}
~~~

Phân biệt **200/204**, **401/403**, **404**, **409/412**, **429/503** theo contract; không map mọi non-2xx thành một lỗi rồi retry vô hạn.

| Phản hồi/điều kiện | Phân loại phía client | Hành động điển hình |
|---|---|---|
| 2xx + JSON hợp lệ | Success | Parse DTO, kiểm tra dữ liệu nghiệp vụ |
| 204 khi contract cho phép | Success không body | Trả Mono.empty hoặc trạng thái phù hợp |
| 400/422 | Request sai hoặc không xử lý được | Sửa payload, không retry tự động |
| 401/403 | Authentication/authorization | Xác minh credentials/quyền; không retry mù |
| 404 | Không tìm thấy/không công bố | Chỉ chuyển thành empty nếu contract cho phép |
| 409/412 | Conflict/precondition | Đọc lại trạng thái, xử lý xung đột |
| 429 | Rate limited | Tôn trọng Retry-After và retry budget |
| 500/502/503/504 | Lỗi server/gateway/dependency | Có thể retry có chọn lọc nếu operation an toàn |
| TCP/TLS/DNS timeout hoặc connection reset | Lỗi transport, **không có HTTP status** | Phân biệt chưa gửi/chưa nhận với commit không rõ |

**202 Accepted** chỉ xác nhận tiếp nhận; với **Location tới job**, client GET trạng thái thay vì gửi lại POST bằng key mới.

## 4. Cấu hình WebClient rõ timeout và nguồn tin cậy

Ví dụ **Spring Boot 3 / Java 17** sử dụng **Reactor Netty**. Các giá trị là giả định minh họa, cần chỉnh theo SLO và đo với downstream thật:

~~~java
import io.netty.channel.ChannelOption;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class PricingClientConfig {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider pricingPool() {
        return ConnectionProvider.builder("pricing-pool")
                .maxConnections(100)
                .pendingAcquireMaxCount(200)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .build();
    }

    @Bean
    WebClient pricingWebClient(
            ConnectionProvider pricingPool, Environment env) {
        String baseUrl = env.getRequiredProperty("pricing.base-url");
        HttpClient http = HttpClient.create(pricingPool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
                .responseTimeout(Duration.ofSeconds(2));
        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new ReactorClientHttpConnector(http))
                .defaultHeader(HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

**pricing.base-url** phải là HTTPS/host từ cấu hình trusted, không lấy từ query/body (**SSRF**). Giám sát pool active/idle/pending. Connect, response và pending-acquire timeout bảo vệ các bước khác nhau, **không thay deadline toàn workflow**.

### 4.1. Service client tạo và trả Mono

~~~java
import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

record PriceView(String productId, long amountMinor, String currency) {}

@Component
class PricingClient {
    private final WebClient webClient;

    PricingClient(@Qualifier("pricingWebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    Mono<PriceView> findPrice(String productId) {
        Objects.requireNonNull(productId);
        return webClient.get()
                .uri(uri -> uri.path("/v1/prices/{id}").build(productId))
                .retrieve()
                .bodyToMono(PriceView.class);
    }
}
~~~

Mẫu giả định auth đã cấu hình riêng. Production phải gắn token phù hợp, validate ID và **không đưa JWT vào URI/log**.

Mặc định, **retrieve()** tạo tín hiệu lỗi cho **HTTP 4xx/5xx**, thường dưới dạng **WebClientResponseException**. Với lỗi transport chưa có response, thường là **WebClientRequestException** hoặc lỗi nền tùy connector. **Không coi Mono.empty từ API lấy giá là “giá bằng 0”** nếu hợp đồng không cho phép.

## 5. Hủy lời gọi: cancellation là tín hiệu cục bộ

Reactive Streams cho phép **Subscriber** hủy **Subscription**. Trong Reactor, khi **Disposable.dispose()**, **take(n)**, client đóng kết nối hoặc **timeout()** xảy ra, tín hiệu cancel có thể lan upstream đến publisher của WebClient. Reactor Netty có thể ngừng đọc, giải phóng connection hoặc đóng request tùy trạng thái giao thức.

**Không có bảo đảm rằng server đích ngừng xử lý.** Các mốc khác nhau dẫn tới hậu quả khác nhau:

| Lúc hủy | Điều có thể đã xảy ra | Client biết chắc điều gì? |
|---|---|---|
| Trước subscription | Chưa kích hoạt cold publisher | Lời gọi từ publisher đó chưa được thực hiện |
| Đang đợi connection | Tác vụ chờ có thể bị hủy | Không phải đã nhận HTTP status |
| Sau khi gửi GET | Remote có thể đang xử lý | Không còn chờ kết quả; chưa biết remote xử lý đến đâu |
| Sau khi gửi POST | Remote có thể đã commit | Không được kết luận POST thất bại |
| Remote đã trả response, client chưa decode | Response có thể bị bỏ | Server có thể đã thành công |
| Publisher đã hoàn thành | Hủy muộn không làm đảo ngược kết quả | Không có rollback từ cancellation |

### 5.1. Hủy thủ công ở ranh giới imperative

~~~java
import reactor.core.Disposable;
import reactor.core.publisher.SignalType;

// Chỉ minh họa cho một tác vụ do code imperative sở hữu lifecycle.
Disposable running = pricingClient.findPrice("p-17")
        .doOnCancel(() -> metrics.incrementCancel())
        .doFinally(signal -> metrics.recordTermination(signal))
        .subscribe(
                price -> handlePrice(price),
                error -> handleError(error));

// Chỉ chủ sở hữu subscription mới quyết định hủy.
running.dispose();
~~~

Ví dụ giả định **metrics, handlePrice, handleError** có implementation. **Không dùng subscribe() thủ công trong WebFlux controller**: làm vậy tách task khỏi lifecycle request, làm mất error propagation và dễ tạo side effect chạy “mồ côi”. Khi controller trả Mono, framework quản lý subscription.

**doOnCancel** chỉ quan sát cancel, không xác nhận server dừng. **doFinally** phân biệt complete/error/cancel; cancel thường **không phát onError** cho subscriber đã hủy.

### 5.2. timeout() khác hủy chủ động

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<PriceView> withDeadline = pricingClient.findPrice("p-17")
        .timeout(Duration.ofSeconds(3))
        .onErrorMap(TimeoutException.class,
                ex -> new PricingDeadlineExceededException(ex));

class PricingDeadlineExceededException extends RuntimeException {
    PricingDeadlineExceededException(Throwable cause) {
        super("pricing deadline exceeded", cause);
    }
}
~~~

**timeout** phát onError downstream và cancel upstream, nhưng request có thể đã tới server. Connect/Netty response timeout có thể là lỗi connector khác với **java.util.concurrent.TimeoutException** của Reactor.

Deadline phải theo ngân sách **toàn request**; hai hop nối tiếp 2 giây có thể vượt budget 3 giây. Không để retry kéo dài vô hạn.

### 5.3. Streaming và cancel khi đã nhận đủ dữ liệu

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.core.ParameterizedTypeReference;
import reactor.core.publisher.Flux;

record StockEvent(String productId, long available) {}

Flux<ServerSentEvent<StockEvent>> firstTen =
        inventoryWebClient.get()
            .uri("/v1/stock-events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .retrieve()
            .bodyToFlux(new ParameterizedTypeReference<
                    ServerSentEvent<StockEvent>>() {})
            .take(10);
~~~

**take(10)** cancel upstream sau 10 event; SSE server có thể phát tiếp trước khi phát hiện. Giới hạn buffer/slow consumer; hỗ trợ **Last-Event-ID** nếu contract yêu cầu.

## 6. Phân biệt lỗi HTTP, transport, decode và cancel

WebClient có hai cấp API thường gặp:

- **retrieve()** thuận tiện khi response thành công có schema đơn giản và các status lỗi được map qua **onStatus**.
- **exchangeToMono()/exchangeToFlux()** phù hợp khi cần kiểm soát từng status, headers và cách tiêu thụ body. Hãy **consume hoặc release response body**, không giữ **ClientResponse** cho một luồng xử lý ngoài vòng đời do API quản lý.

### 6.1. retrieve() và mapping có chủ đích

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class PriceNotPublished extends RuntimeException {}
class RemoteRateLimited extends RuntimeException {
    final String retryAfter;
    RemoteRateLimited(String retryAfter) {
        this.retryAfter = retryAfter;
    }
}
class RemotePricingFailure extends RuntimeException {
    final int upstreamStatus;
    RemotePricingFailure(int status) {
        this.upstreamStatus = status;
    }
}

Mono<PriceView> query(WebClient webClient, String id) {
    return webClient.get()
            .uri("/v1/prices/{id}", id)
            .retrieve()
            .onStatus(s -> s.value() == 404,
                    response -> Mono.just(new PriceNotPublished()))
            .onStatus(s -> s.value() == 429,
                    response -> Mono.just(new RemoteRateLimited(
                            response.headers().asHttpHeaders()
                                    .getFirst(HttpHeaders.RETRY_AFTER))))
            .onStatus(HttpStatusCode::is5xxServerError,
                    response -> Mono.just(new RemotePricingFailure(
                            response.statusCode().value())))
            .bodyToMono(PriceView.class)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("empty price response")));
}
~~~

Ví dụ này không cố phản chiếu toàn bộ **body lỗi**. Các nhánh onStatus chỉ map exception; **retrieve** quản lý việc giải phóng body không được sử dụng theo lifecycle của nó. Nếu cần đọc lỗi dạng **application/problem+json**, đặt giới hạn kích thước/charset, parse qua DTO **được whitelist**, không lấy raw detail từ upstream làm nội dung công khai. Giá 404 từ dịch vụ định giá có thể mang nghĩa **giá chưa được phát hành**, **không tự đồng nghĩa sản phẩm của API tổng hợp phải trả 404**.

**WebClientResponseException** mang HTTP status và có thể chứa response body/headers; **WebClientRequestException** thường mô tả lỗi kết nối hoặc request không nhận được HTTP response. Cần phân biệt thêm **DecodingException**, lỗi schema, dữ liệu trái hợp đồng, và cancellation. Không log exception hoặc request đầy đủ khi chúng có thể chứa token, email, thông tin giá nội bộ.

### 6.2. exchangeToMono() khi cần phân nhánh status và headers

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

Mono<PriceView> loadExplicit(WebClient client, String id) {
    return client.get().uri("/v1/prices/{id}", id)
            .exchangeToMono(response -> {
                int code = response.statusCode().value();
                if (code == 200) {
                    return response.bodyToMono(PriceView.class)
                            .switchIfEmpty(Mono.error(
                                    new IllegalStateException(
                                            "200 without required body")));
                }
                if (code == 404) {
                    return response.releaseBody()
                            .then(Mono.error(new PriceNotPublished()));
                }
                if (code == 429) {
                    String retryAfter = response.headers()
                            .asHttpHeaders()
                            .getFirst(HttpHeaders.RETRY_AFTER);
                    return response.releaseBody()
                            .then(Mono.error(
                                    new RemoteRateLimited(retryAfter)));
                }
                // Lấy WebClientResponseException có status/headers/body
                // theo giới hạn buffer do codec/client cấu hình.
                return response.createException().flatMap(Mono::error);
            });
}
~~~

Ví dụ **không tự theo redirect 3xx**; nếu upstream trả 302, nhánh mặc định phát lỗi theo chính sách này. Với **204**, contract tìm giá bắt buộc có body nên cũng được xem là vi phạm giao thức. Trong thực tế nên map 2xx khác/redirect theo hợp đồng rõ ràng; không mặc định 3xx là JSON thành công. **Không trả ClientResponse để decode sau** khi exchangeToMono hoàn tất: body có thể đã được release.

### 6.3. Lỗi cục bộ không được biến thành dữ liệu giả

~~~java
// Anti-pattern: che mất phân biệt timeout với tồn kho thật bằng 0.
Mono<Long> stock = inventoryClient.loadStock(id)
        .onErrorReturn(0L);
~~~

Điều này có thể khiến hệ thống kết luận “hết hàng” thay vì “không đọc được tồn kho”, làm sai nghiệp vụ và số liệu. Nếu fallback là yêu cầu đã được chấp thuận (ví dụ bản cache còn hạn), trả kèm dấu **stale/degraded** theo contract, giới hạn tuổi dữ liệu và metric; không âm thầm làm lỗi biến mất.

## 7. Retry, deadline và tính đúng của tác động nghiệp vụ

**retryWhen** trong Reactor thường **subscribe lại nguồn**. Với WebClient cold publisher, mỗi lần retry có thể gửi **một HTTP request mới**. Nếu lần trước đã được server xử lý nhưng response mất, retry là lời gọi mới với hệ quả phải được kiểm soát.

### 7.1. GET an toàn để retry không có nghĩa retry vô hạn

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

boolean retryableGet(Throwable failure) {
    if (failure instanceof WebClientRequestException) {
        return true; // Cần lọc lỗi TLS/cấu hình cố định ở production.
    }
    if (failure instanceof RemotePricingFailure remote) {
        return remote.upstreamStatus == 502
                || remote.upstreamStatus == 503
                || remote.upstreamStatus == 504;
    }
    return false;
}

Mono<PriceView> findPriceReliably(String id) {
    return pricingClient.findPrice(id)
            .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .jitter(0.5)
                    .filter(this::retryableGet))
            .timeout(Duration.ofSeconds(3));
}
~~~

Đây là **đoạn minh họa trong một class service**, không phải tệp Java độc lập. **2 retry** nghĩa là tối đa hai lần thử thêm sau lần đầu. Timeout bên ngoài bao phủ chuỗi retry, trong khi connect/response timeout tầng Netty vẫn được cấu hình riêng. Production phải phân biệt lỗi transport tạm thời với TLS/host sai cố định, có retry budget và circuit breaker/admission control khi upstream quá tải.

### 7.2. Retry-After không chỉ là ngủ một số giây

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 5
Content-Type: application/problem+json

{"type":"about:blank","title":"Rate limit exceeded","status":429}
~~~

Theo HTTP, **Retry-After** có thể là **số giây không âm** hoặc **HTTP-date**. Client phải parse cả hai dạng; clamp theo deadline và clock skew; dùng jitter, rate limit/concurrency limit và không retry khi ngân sách thời gian đã hết. **Retry.backoff mặc định không tự đọc Retry-After**. Nếu không thể chờ an toàn, trả lỗi cho caller hoặc lập lịch công việc bền vững theo workflow; đừng giữ hàng nghìn subscription ngủ. Retry-After cũng có thể đi cùng **503**.

### 7.3. POST có side effect: dùng Idempotency-Key

~~~http
POST /v1/payments/refunds HTTP/1.1
Host: payments.internal.example
Authorization: Bearer <service-token>
Content-Type: application/json
Idempotency-Key: refund-order-918-001

{"paymentId":"pay-918","amountMinor":359000}
~~~

Giả sử downstream **commit hoàn tiền** nhưng đường truyền đứt trước khi client nhận response. Client thấy connection reset/timeout và **không biết hoàn tiền đã thực hiện hay chưa**. Hủy request, retryWhen hay Netty close connection **không hoàn tác** tác động đã commit.

Hợp đồng đúng cần **Idempotency-Key có scope/TTL**, fingerprint của payload, lưu kết quả logical operation, và phân biệt key trùng với payload khác. Retry bằng **cùng key và payload**, không tự tạo key mới. Phải có **GET operation/refund status** hoặc reconciliation nếu trạng thái chưa rõ; với PUT/PATCH cần xét semantics và **If-Match** để ngăn lost update. WebClient **không thể tạo exactly-once side effect** chỉ bằng operator. Với job dài, thiết kế **202 + Location**, operation bền vững và scanner.

### 7.4. Giới hạn fan-out và tổng thời gian

~~~java
import reactor.core.publisher.Flux;

Flux<PriceView> prices = Flux.fromIterable(productIds)
        .flatMap(id -> findPriceReliably(id), 8);
~~~

**8** giới hạn số publisher inner đồng thời tại operator này, không thay connection pool/rate limiter toàn dịch vụ. Với tập productIds lớn, cần giới hạn input và dùng chunking/pagination; không **collectList()** cho stream không giới hạn. Quản lý deadline theo **toàn workflow**, không chỉ cộng timeout của từng hop.

## 8. Bảo mật và observability cho Java HTTP client

### 8.1. Token, tenant và địa chỉ đích

~~~java
// Anti-pattern: SSRF nếu URL đến từ người gọi không đáng tin.
webClient.get().uri(requestUrl).retrieve().bodyToMono(String.class);
~~~

Dùng **baseUrl được allowlist và lấy từ cấu hình đáng tin**, **URI template** cho path/query; validate tenant/owner tại service. Dùng service-to-service OAuth2 với đúng **audience/scope**, TLS/mTLS theo kiến trúc; không forward inbound JWT sang một host khác theo mặc định. Ví dụ với token lấy từ nguồn đáng tin:

~~~java
interface ServiceTokenSource {
    Mono<String> tokenForPricing();
}

Mono<PriceView> authenticatedPrice(
        WebClient client, ServiceTokenSource tokens, String id) {
    return tokens.tokenForPricing()
            .flatMap(token -> client.get()
                    .uri("/v1/prices/{id}", id)
                    .headers(headers -> headers.setBearerAuth(token))
                    .retrieve().bodyToMono(PriceView.class));
}
~~~

Không log token, URL chứa query nhạy cảm hay toàn bộ **WebClientResponseException.getResponseBodyAsString()**. Nếu dùng auth filter, không refresh token vô hạn khi 401: phân biệt token hết hạn có thể refresh với thiếu quyền/sai audience. Với multi-tenant, downstream cũng phải kiểm tra scope/ownership; client chỉ gửi tenant được suy từ identity đáng tin.

### 8.2. Context và metrics trong reactive pipeline

Reactive pipeline có thể tiếp tục trên thread khác; **ThreadLocal/MDC thủ công** không mặc định đi theo tín hiệu. Dùng **Reactor Context**, Spring Security reactive context và thư viện tracing/context propagation được hỗ trợ, không giữ principal trong mutable field dùng chung.

Metric nên có **method, route template, upstream service, status family, retry reason, timeout, cancel, pool pending, p95/p99**. Không dùng raw URL có ID/secret hoặc userId làm metric tag. **doOnError** để telemetry, không đặt side effect nghiệp vụ có thể được subscribe lặp.

### 8.3. Giới hạn response body và streaming

WebClient codec có **maxInMemorySize** để tránh buffer quá lớn. Với file lớn/NDJSON/SSE, xử lý theo stream, không giữ toàn bộ response bằng byte array/collectList không giới hạn. Nếu tự xử lý **DataBuffer**, phải release/discard đúng API để tránh leak pooled buffer.

**Content-Type**, Content-Length và JSON body từ upstream đều là dữ liệu cần validate. Không phản chiếu error detail chưa lọc tới người dùng cuối; tại API của mình hãy tạo **Problem Details** với mã ổn định, HTTP status đúng và trace ID an toàn.

## 9. Kiểm thử: response, lỗi và hủy lời gọi

| Tình huống | Kỹ thuật | Điều phải chứng minh |
|---|---|---|
| GET 200 với JSON | HTTP mock server | Đúng method/path, parse PriceView |
| 404 hoặc 429 | Fake ClientResponse/HTTP stub | Mã lỗi riêng, Retry-After được giữ |
| 503 có body lỗi | HTTP stub | Không coi là thành công, không lộ raw detail |
| Server đóng kết nối giữa chừng | Socket fault injection | Transport error khác HTTP status |
| Response quá lớn/JSON sai | Stub body và codec limit | Không OOM hoặc trả dữ liệu giả |
| Mono được subscribe hai lần | Đếm request tới mock server | Hiểu cold publisher và tác động lặp |
| Cancel trước response | StepVerifier + ExchangeFunction | Upstream nhận tín hiệu cancel |
| Timeout sau POST đã commit | Mock server commit rồi ngắt mạng | Đối soát theo operation ID, không hoàn tiền trùng |
| 503/429 liên tục | Test retry + virtual time | Có max attempts, jitter/budget hợp lý |
| Tenant khác hoặc URL bị sửa | Security/integration test | Không lộ token, không gọi host tùy ý |

**StepVerifier** kiểm tra tín hiệu Reactor mà không cần bật HTTP server thật. Ví dụ dùng **ExchangeFunction** giả:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WebClientSignalTest {
    @Test
    void upstream503IsHttpError() {
        ExchangeFunction fake = request -> Mono.just(
                ClientResponse.create(HttpStatus.SERVICE_UNAVAILABLE)
                        .body("unavailable").build());
        WebClient client = WebClient.builder()
                .exchangeFunction(fake).build();

        StepVerifier.create(client.get()
                .uri("https://pricing.example.test/v1/prices/p-17")
                .retrieve().bodyToMono(PriceView.class))
                .expectErrorMatches(error ->
                        error instanceof WebClientResponseException ex
                        && ex.getStatusCode().value() == 503)
                .verify();
    }

    @Test
    void cancellationReachesExchangePublisher() {
        AtomicBoolean cancelled = new AtomicBoolean(false);
        ExchangeFunction neverResponds = request ->
                Mono.<ClientResponse>never()
                        .doOnCancel(() -> cancelled.set(true));
        WebClient client = WebClient.builder()
                .exchangeFunction(neverResponds).build();

        StepVerifier.create(client.get()
                .uri("https://pricing.example.test/v1/prices/p-17")
                .retrieve().bodyToMono(String.class))
                .thenCancel().verify();
        assertTrue(cancelled.get());
    }
}
~~~

Cần dependency **reactor-test**, JUnit 5 và spring-webflux cho mã trên; **PriceView** lấy từ phần 4. Test thứ hai **chỉ xác nhận tín hiệu cancel đến ExchangeFunction giả**, **không chứng minh server thật dừng xử lý**. Với I/O thật, dùng MockWebServer/WireMock hoặc server thử nghiệm để tạo delayed response, reset connection, HTTP 429 và 503. Dùng **StepVerifier.withVirtualTime** cho delay/backoff thuần Reactor; virtual time không thay thế network timeout thực của Netty.

## 10. Bài tập: client xử lý thanh toán và kho

Một API checkout phải gọi **GET tồn kho**, **POST giữ hàng**, sau đó **POST thanh toán**. Tồn kho có p99 800 ms, thanh toán có thể timeout sau khi commit. Gateway quy định tổng deadline **4 giây** và bên kho có thể trả **429 Retry-After: 3**.

Hãy thiết kế: **(1)** chuỗi WebClient Mono và deadline; **(2)** lỗi nào được retry; **(3)** khi nào cancel upstream; **(4)** idempotency key và tra trạng thái thanh toán sau timeout; **(5)** test cho client ngắt kết nối, 429, 503 và commit-mất-response; **(6)** cách bảo vệ token/tenant.

**Gợi ý:** GET kho có thể retry có giới hạn, nhưng 429 cần xem budget 4 giây có đủ chờ 3 giây hay không. POST giữ hàng/thanh toán phải có operation ID/key ổn định và endpoint tra trạng thái; cancellation **không hủy giao dịch đã commit**. Phát lỗi nghiệp vụ hoặc 202/job theo hợp đồng, không tự coi timeout là “chưa thanh toán”.

## 11. Checklist và tài liệu tham khảo

- [ ] Controller reactive **trả Mono/Flux**, không subscribe/block thủ công.
- [ ] Phân biệt status HTTP, transport failure, decode error, timeout và cancel.
- [ ] Có connect/response timeout, deadline tổng, pool và concurrency limit.
- [ ] Retry có max attempts/budget; 429/Retry-After được xử lý có chủ đích.
- [ ] POST side effect có idempotency và reconciliation khi response mất.
- [ ] Token, URI, tenant, body lỗi và telemetry được bảo vệ.
- [ ] Test tín hiệu Reactor và fault injection qua HTTP server thật.

Tham khảo: **Spring WebClient**, https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html; **Project Reactor Reference**, https://projectreactor.io/docs/core/release/reference/; **Reactor Netty HTTP Client**, https://projectreactor.io/docs/netty/release/reference/http-client.html; **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html.

**Kết luận:** WebClient giúp tổ hợp I/O HTTP **bất đồng bộ**, nhưng tính đúng đến từ **hợp đồng status/error, giới hạn tài nguyên, cancellation được hiểu đúng và idempotency của tác động nghiệp vụ**. Hủy subscription có thể ngừng chờ kết quả ở client, **không phải giao dịch đảo ngược ở server**.
