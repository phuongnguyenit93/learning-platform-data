# Chọn Java HttpClient, RestClient hoặc WebClient theo nhu cầu

## 1. Bài toán: chọn HTTP client theo luồng xử lý

Một dịch vụ đặt hàng cần gọi Catalog API để đọc sản phẩm, Payment API để thanh toán và hệ thống vận chuyển để nhận cập nhật liên tục. Cả ba dùng HTTP nhưng khác nhau về thời gian phản hồi, số lượng request đồng thời, khả năng retry và mô hình thực thi.

Java có **HttpClient** trong JDK; Spring cung cấp **RestClient** cho HTTP đồng bộ và **WebClient** cho mô hình reactive. Cả ba đều gửi được GET/POST, nhưng chọn client chỉ vì cú pháp sẽ dễ dẫn đến **blocking event-loop, thiếu timeout, tràn kết nối hoặc xử lý nhầm HTTP status**.

Bài thuộc chương **Client Java**, module **INTEGRATION_API_REST**: tích hợp REST API theo resource, URI, phương thức/mã HTTP, hợp đồng dữ liệu, cache, idempotency, OpenAPI, xác thực/phân quyền và kiểm thử. Ví dụ sử dụng **Java 17+**, **Spring Framework 6.1+/Spring Boot 3.2+** cho RestClient và Spring WebFlux/Reactor cho WebClient.

Sau bài, bạn có thể:

1. Phân biệt **synchronous**, **asynchronous** và **reactive** về luồng thực thi.
2. Chọn HttpClient, RestClient hoặc WebClient dựa trên yêu cầu thực.
3. Viết client có DTO, timeout, status handling, bảo mật và retry có giới hạn.
4. Quyết định khi nào cần streaming/SSE và khi nào blocking là phù hợp.
5. Kiểm thử HTTP contract bằng mock server và test tích hợp.

## 2. Bảng quyết định ban đầu

| Tiêu chí | Java HttpClient (JDK) | Spring RestClient | Spring WebClient |
| --- | --- | --- | --- |
| Dependency | JDK, package **java.net.http** | **spring-web** | **spring-webflux** và Reactor |
| Kiểu API | Request builder; send/sendAsync | Fluent **đồng bộ** | Fluent, trả **Mono/Flux** |
| Đồng bộ | **send** chặn thread | **retrieve().body** chặn thread | Chỉ chặn nếu caller ép **block()** |
| Bất đồng bộ | **CompletableFuture** từ sendAsync | Tự phối hợp executor nếu cần | Reactive stream/non-blocking I/O với connector phù hợp |
| JSON binding | Tự dùng Jackson/Gson | Spring HttpMessageConverters | Spring codecs |
| HTTP error | Tự kiểm tra status | Mặc định raise khi 4xx/5xx với retrieve | Mặc định signal error khi 4xx/5xx với retrieve |
| Streaming | Có BodyHandlers/InputStream/Publisher, tự quản lý | Có thể đọc stream đồng bộ | Flux/SSE/NDJSON thuận tiện |
| Bối cảnh phù hợp | SDK độc lập, CLI, ứng dụng không Spring | **Spring MVC** gọi API đồng bộ | **Spring WebFlux**, nhiều I/O hoặc stream dài |

**Quy tắc chọn nhanh:** Với backend Spring MVC chủ yếu request/response JSON, bắt đầu từ **RestClient**. Với WebFlux pipeline hoặc luồng dữ liệu streaming, xem xét **WebClient**. Với thư viện Java không phụ thuộc Spring, dùng **JDK HttpClient**.

**WebClient không tự động nhanh hơn RestClient.** Độ trễ phụ thuộc hệ thống đích, pool, timeout, serialization, thread và mức tải. Thêm Reactor vào ứng dụng blocking để làm một GET đơn giản có thể chỉ tăng độ phức tạp.

### Các yêu cầu cần hỏi trước khi chọn

- Endpoint được gọi là **một request ngắn**, nhiều request song song hay stream kéo dài?
- Dịch vụ hiện tại vận hành **Spring MVC/servlet**, **WebFlux** hay Java thuần?
- Có bao nhiêu lời gọi đồng thời; bao nhiêu connection/thread được phép giữ?
- Client phải nhận **200/201/202/204**, **ETag/Location/Retry-After**, Problem Details?
- HTTP call có tác dụng phụ như thanh toán, cần **Idempotency-Key**?
- Có yêu cầu proxy, mTLS, OAuth2, audit, monitoring và test hạ tầng chung?

## 3. Một REST contract dùng cho cả ba client

Lấy thông tin sản phẩm:

~~~http
GET /api/v1/products/prod-42 HTTP/1.1
Host: catalog.example.internal
Authorization: Bearer <access-token>
Accept: application/json
X-Request-Id: req-781
~~~

Phản hồi thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-42-v7"
Cache-Control: private, max-age=30

{
  "id": "prod-42",
  "name": "Java API Handbook",
  "priceVnd": 180000
}
~~~

Khi không tìm thấy:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.internal/problems/not-found",
  "title": "Product not found",
  "status": 404,
  "code": "PRODUCT_NOT_FOUND"
}
~~~

DTO Java:

~~~java
public record ProductView(String id, String name, long priceVnd) {}
~~~

**Không dùng một DTO success để parse body lỗi.** HTTP status, response headers, Content-Type và JSON schema cùng tạo thành hợp đồng. Response 404 từ Catalog có thể được mapping thành lỗi domain ở service gọi; không nhất thiết phải trả nguyên vẹn 404 đến client của API tổng hợp.

Các loại **ProductNotFoundException**, **UpstreamHttpException**, **CatalogProperties** bên dưới là thành phần ứng dụng tự xây dựng; ví dụ tập trung vào cơ chế client.

## 4. Java HttpClient: không phụ thuộc Spring

JDK **java.net.http.HttpClient** cung cấp HTTP/1.1 và HTTP/2 nếu thương lượng được, hỗ trợ **send** đồng bộ và **sendAsync** bất đồng bộ. JSON mapping do bạn quản lý.

~~~java
public final class JdkCatalogClient {
    private final HttpClient http;
    private final ObjectMapper mapper;
    private final URI baseUri;

    public JdkCatalogClient(URI baseUri, ObjectMapper mapper) {
        this.baseUri = baseUri;
        this.mapper = mapper;
        this.http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    }

    public ProductView find(String productId, String token)
            throws IOException, InterruptedException {

        // Chỉ nhận ID đã validate theo allowlist.
        URI uri = baseUri.resolve(
            "/api/v1/products/" + productId);

        HttpRequest req = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(6))
            .header("Authorization", "Bearer " + token)
            .header("Accept", "application/json")
            .GET()
            .build();

        HttpResponse<String> response = http.send(
            req, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

        int status = response.statusCode();
        if (status == 404) {
            throw new ProductNotFoundException(productId);
        }
        if (status < 200 || status >= 300) {
            throw new UpstreamHttpException(status);
        }
        return mapper.readValue(response.body(), ProductView.class);
    }
}
~~~

**Cảnh báo URI:** nối ID vào path như trên chỉ an toàn khi ID được xác minh là một path segment đơn giản (ví dụ chữ, số, gạch nối, gạch dưới). Nếu ID có slash, dấu hỏi hoặc ký tự đặc biệt, phải **encode path segment**, không để client kiểm soát endpoint URL. **baseUri** phải đến từ cấu hình tin cậy, không lấy trực tiếp từ người dùng.

**connectTimeout** giới hạn kết nối; **HttpRequest.timeout** giới hạn thời gian request theo JDK API. Đây là hai timeout có ý nghĩa khác nhau. **send** chặn thread hiện tại; nếu nhận InterruptedException, caller cần xử lý interrupt đúng chính sách.

### Không đồng bộ với sendAsync

~~~java
public CompletableFuture<ProductView> findAsync(
        String productId, String token) {

    URI uri = baseUri.resolve(
        "/api/v1/products/" + productId);
    HttpRequest req = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(6))
        .header("Authorization", "Bearer " + token)
        .header("Accept", "application/json")
        .GET().build();

    return http.sendAsync(
            req, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8))
        .thenApply(response -> {
            int code = response.statusCode();
            if (code == 404) {
                throw new ProductNotFoundException(productId);
            }
            if (code < 200 || code >= 300) {
                throw new UpstreamHttpException(code);
            }
            try {
                return mapper.readValue(
                    response.body(), ProductView.class);
            } catch (JsonProcessingException ex) {
                throw new CompletionException(ex);
            }
        });
}
~~~

**CompletableFuture không phải Reactive Streams Publisher**. Dùng sendAsync giúp caller không đợi đồng bộ nhưng không tự tạo backpressure, circuit breaker hoặc giới hạn số request đồng thời. Với nhiều cuộc gọi, dùng semaphore/bulkhead hoặc executor phù hợp. Dùng lại **một HttpClient** thay vì tạo mới liên tục để tránh quản lý tài nguyên thừa.

## 5. Spring RestClient: fluent và đồng bộ

**RestClient** có từ Spring Framework 6.1, phù hợp service **Spring MVC** đang dùng luồng request thông thường.

~~~java
@Configuration
public class CatalogHttpConfiguration {
    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            CatalogProperties cfg) {
        return builder
            .baseUrl(cfg.baseUrl())
            .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
            .build();
    }
}

@Service
public class RestCatalogClient {
    private final RestClient client;

    public RestCatalogClient(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    public ProductView find(String id, String token) {
        return client.get()
            .uri("/api/v1/products/{id}", id)
            .headers(h -> h.setBearerAuth(token))
            .retrieve()
            .onStatus(status -> status.value() == 404,
                (request, response) -> {
                    throw new ProductNotFoundException(id);
                })
            .body(ProductView.class);
    }
}
~~~

Spring **HttpMessageConverters** ánh xạ JSON với DTO. Với **retrieve**, phản hồi 4xx/5xx mặc định thường gây exception khi chưa được custom handler xử lý. **RestClient vẫn blocking:** lời gọi **body(...)** chờ HTTP và deserialize trước khi trở về.

Nếu cần headers:

~~~java
ResponseEntity<ProductView> response = client.get()
    .uri("/api/v1/products/{id}", id)
    .retrieve()
    .toEntity(ProductView.class);

String etag = response.getHeaders().getETag();
ProductView product = response.getBody();
~~~

ETag/Cache-Control của downstream không tự trở thành metadata đúng của resource tổng hợp ở service hiện tại. Phải tính lại theo representation, quyền và trạng thái nghiệp vụ của API mình.

## 6. Spring WebClient: non-blocking và reactive

**WebClient** thuộc WebFlux, trả **Mono** (không quá một giá trị) hoặc **Flux** (nhiều giá trị). Với connector I/O non-blocking như Reactor Netty, nó cho phép quản lý nhiều request đang chờ mà không giữ một platform thread cho mỗi request.

~~~java
@Configuration
public class ReactiveCatalogConfiguration {
    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogProperties cfg) {
        return builder
            .baseUrl(cfg.baseUrl())
            .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
            .build();
    }
}

@Service
public class ReactiveCatalogClient {
    private final WebClient client;

    public ReactiveCatalogClient(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    public Mono<ProductView> find(String id, String token) {
        return client.get()
            .uri("/api/v1/products/{id}", id)
            .headers(h -> h.setBearerAuth(token))
            .retrieve()
            .onStatus(status -> status.value() == 404,
                response -> Mono.error(
                    new ProductNotFoundException(id)))
            .bodyToMono(ProductView.class);
    }
}
~~~

**Mono chỉ bắt đầu HTTP khi có subscription**. Re-subscribe cùng một Mono lạnh có thể gửi lại request, đặc biệt nguy hiểm với POST có side effect. Không gọi **.block()** bên trong Reactor event-loop: việc đó có thể làm nghẽn hoặc gây lỗi runtime. Nếu một MVC service dùng .block() ở ranh giới imperative, thao tác đó vẫn **blocking** và cần timeout rõ.

Hai I/O độc lập có thể ghép:

~~~java
Mono<Tuple2<ProductView, InventoryView>> together = Mono.zip(
    catalogClient.find(productId, token),
    inventoryClient.read(productId, token));
~~~

Mono.zip thường cho phép hai nguồn chạy đồng thời khi subscribe. Cần quyết định hành vi nếu một nguồn lỗi hoặc hoàn thành rỗng. Không giấu lỗi/biến kết quả rỗng thành dữ liệu hợp lệ nếu contract không cho phép.

## 7. Streaming, SSE và payload lớn

Với JSON ngắn, cả ba client đều đáp ứng tốt. Nhưng file lớn, NDJSON hoặc SSE cần xử lý **theo phần**, không luôn đưa cả body vào một String/byte[].

| Nhu cầu | JDK HttpClient | RestClient | WebClient |
| --- | --- | --- | --- |
| JSON ngắn | ofString + ObjectMapper | body(DTO.class) | bodyToMono(DTO.class) |
| Tải file lớn | BodyHandlers.ofFile/ofInputStream | Đọc stream theo request factory | Flux/DataBuffer |
| NDJSON | Tự parse stream | Stream đồng bộ | bodyToFlux(DTO.class) |
| SSE có id/event/data | Tự parse hoặc thư viện hỗ trợ | Có thể nhưng kém thuận tiện | Flux của ServerSentEvent |

WebClient đọc SSE và giữ metadata:

~~~java
Flux<ServerSentEvent<ProductEvent>> stream = client.get()
    .uri("/api/v1/products/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .retrieve()
    .bodyToFlux(new ParameterizedTypeReference<
        ServerSentEvent<ProductEvent>>() {});
~~~

**SSE không tự bảo đảm client nhận mọi event.** Khi mất mạng cần reconnect, Last-Event-ID nếu server hỗ trợ durable replay và **GET trạng thái** làm fallback. Khi không cần id/cursor, có thể đọc bodyToFlux(ProductEvent.class); nhưng như vậy mất metadata của frame cần cho resume.

**Tránh collectList trên Flux vô hạn**: nó chờ kết thúc stream và tích trữ dữ liệu trong RAM. Dùng xử lý từng event, giới hạn size/time, checkpoint hoặc lưu theo lô có giới hạn. Reactor backpressure giúp phối hợp trong pipeline, không cam kết server HTTP từ xa luôn phát chậm lại.

Với file lớn, kiểm tra Content-Length khi có, giới hạn bytes thực nhận, đóng stream/cancel subscription và không tin filename ngoài từ Content-Disposition. Với CSV/PDF cần schema/media type phù hợp; không deserialize nhầm file lỗi Problem Details thành DTO thành công.

## 8. Timeout, pool, concurrency và kết nối

Phân biệt **connect timeout** (tạo kết nối), **response/read timeout** (đọc), **overall deadline** (ngân sách toàn workflow), **pool acquire timeout** (chờ connection) và **idle timeout** (kết nối không hoạt động). Một connect timeout 2 giây **không** ngăn downstream giữ connection quá lâu sau khi kết nối đã thành công.

### JDK HttpClient

~~~java
HttpClient http = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

HttpRequest req = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofSeconds(6))
    .GET().build();
~~~

Request timeout của JDK không thay tổng deadline của chuỗi retry. Không tạo HttpClient mới cho từng request; tái sử dụng để tận dụng quản lý kết nối.

### RestClient dùng JDK request factory

~~~java
HttpClient transport = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

JdkClientHttpRequestFactory factory =
    new JdkClientHttpRequestFactory(transport);
factory.setReadTimeout(Duration.ofSeconds(5));

RestClient rest = RestClient.builder()
    .baseUrl("https://catalog.example.internal")
    .requestFactory(factory)
    .build();
~~~

Spring có nhiều ClientHttpRequestFactory; timeout, TLS, proxy và connection pooling **phụ thuộc transport thực tế**. Không giả định một cấu hình RestClient tự áp cho mọi factory. Với tải lớn, xem giới hạn kết nối và thời gian acquire pool.

### WebClient dùng Reactor Netty

~~~java
reactor.netty.http.client.HttpClient netty =
    reactor.netty.http.client.HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
        .responseTimeout(Duration.ofSeconds(5));

WebClient web = WebClient.builder()
    .baseUrl("https://catalog.example.internal")
    .clientConnector(new ReactorClientHttpConnector(netty))
    .build();
~~~

Ví dụ cần Reactor Netty, **ChannelOption** và **ReactorClientHttpConnector**. Với connector khác, cấu hình timeout khác. **responseTimeout** ở transport và **Mono.timeout(Duration)** theo thời gian phát tín hiệu không hoàn toàn giống nhau. SSE có heartbeat thưa có thể bị ngắt sai nếu đặt read/response timeout quá ngắn.

**Concurrency limit quan trọng không kém timeout:** nếu downstream chỉ xử lý 30 request cùng lúc, cho 5.000 request cùng dồn vào pool sẽ gây queue/trễ. Dùng semaphore/bulkhead hoặc concurrency limit, queue bounded, connection pool phù hợp và metrics. Reactive không vô hiệu hóa giới hạn CPU, socket hoặc quota downstream.

## 9. HTTP status, Problem Details và lỗi mạng

Ba client khác nhau về exception, nhưng **hợp đồng HTTP giống nhau**:

| Kết quả | Cách hiểu |
| --- | --- |
| 200/201 | Đọc success DTO và metadata theo schema |
| 202 | Tác vụ đã nhận; tra operation status, không coi là hoàn tất |
| 204/304 | Không body; không cố parse JSON |
| 400/404/409/422 | Đọc lỗi hợp đồng, thường không retry tự động |
| 401/403 | Cần xử lý authentication/authorization, không retry mù |
| 429/503 | Có thể retry có giới hạn, tôn trọng Retry-After nếu hợp lệ |
| Timeout/connection reset | **Không rõ** đã có tác dụng phụ hay chưa, nhất là POST |
| Body 200 sai schema | Lỗi protocol của upstream, không âm thầm dùng DTO rỗng |

**JDK HttpClient không tự ném exception cho status 404/500**; phải tự đọc statusCode. Với **RestClient.retrieve** mặc định 4xx/5xx thường thành **RestClientResponseException**; với **WebClient.retrieve** thành **WebClientResponseException** hoặc tín hiệu error. Không bắt exception tổng rồi trả success mặc định.

Ví dụ WebClient chuyển 404 và 429 sang lỗi domain:

~~~java
Mono<ProductView> product = web.get()
    .uri("/api/v1/products/{id}", id)
    .retrieve()
    .onStatus(s -> s.value() == 404,
        resp -> Mono.error(new ProductNotFoundException(id)))
    .onStatus(s -> s.value() == 429,
        resp -> Mono.error(new RateLimitedException(
            resp.headers().asHttpHeaders()
                .getFirst(HttpHeaders.RETRY_AFTER))))
    .bodyToMono(ProductView.class);
~~~

Nếu downstream trả **application/problem+json**, map qua **type/code** thay vì so chuỗi **detail/title**. Có thể decode ProblemDetail trong **onStatus**, nhưng phải giới hạn body và có fallback nếu upstream gửi HTML/JSON sai. Đừng ghi raw body lỗi vào log khi có PII.

Đặc biệt, **HTTP 5xx sau POST không chứng minh DB chưa commit**. Server có thể commit rồi mất kết nối lúc trả response. Phải phối hợp với cơ chế idempotency/đối soát.

## 10. Retry và idempotency: quy tắc không phụ thuộc client

Một retry policy phải chỉ rõ **điều kiện**, **số lần thử tối đa**, **backoff + jitter**, **tổng deadline** và **idempotency**.

- **GET/HEAD** có ngữ nghĩa safe; retry lỗi tạm thời khi có ngân sách và giới hạn tải.
- **PUT/DELETE** idempotent theo HTTP nhưng implementation/downstream side effects vẫn cần kiểm tra; response lần lặp không nhất thiết giống lần đầu.
- **POST** mặc định không idempotent; muốn tự động retry cần hợp đồng **Idempotency-Key** hoặc business reference.
- **400/401/403/409/422** không retry mù. **429/503** có thể retry với Retry-After và giới hạn.
- **Retry-After** có thể là **số giây** hoặc **HTTP-date**; cần parse đúng và không vượt deadline.
- Không retry vô hạn nhiều tầng: SDK + gateway + service retry chồng nhau có thể khuếch đại tải.

Ví dụ thanh toán:

~~~http
POST /api/v1/payment-intents HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: order-501-charge-v1

{"orderId":"ord-501","amountMinor":180000,"currency":"VND"}
~~~

Nếu timeout, retry **cùng key và cùng payload** trong cửa sổ mà server công bố. **Không tạo key mới mỗi lần thử lại**, có thể sinh nhiều giao dịch. Nếu key đã hết TTL, dùng business reference hoặc tra trạng thái để đối soát.

Một thuật toán:

~~~text
deadline = now + 8s
attempts <= 3
success 200/201/202 -> xử lý theo đúng status
429/503 -> backoff có jitter, cân nhắc Retry-After
network timeout -> chỉ retry nếu request an toàn/idempotent
400/401/403/409 -> dừng và phân loại
trước mỗi retry -> kiểm tra deadline và cancellation
~~~

Với WebClient, **retryWhen** phải lọc loại lỗi cần retry, không bắt mọi Throwable. Với JDK/RestClient, đặt chính sách retry ở lớp riêng dễ kiểm thử. Đối với payment, nếu kết quả chưa rõ, ưu tiên truy vấn operation/payment status trước khi làm thêm việc có side effect.

## 11. Security: client là biên giới truyền dữ liệu và credential

Các rủi ro chính:

1. **SSRF và URL động:** base URL phải đến từ config tin cậy/allowlist. Nếu bắt buộc nhận endpoint động, kiểm tra scheme HTTPS, host, port, DNS rebinding, redirect và IP private/loopback/link-local/metadata; dùng egress policy.
2. **Redirect làm lộ token:** không tự chuyển Authorization qua origin khác. JDK ví dụ dùng Redirect.NEVER; Spring transport phải có redirect policy tương ứng.
3. **Bearer token:** không hard-code, không ghi log hoặc đặt trong query. Token phải đúng audience/scope/tenant; không dùng token T1 cho T2.
4. **Connection/TLS:** kiểm tra certificate/hostname, cấu hình trust store và mTLS nếu có; không tắt TLS verification để “sửa lỗi”.
5. **Response giả/malicious:** đặt giới hạn body size, JSON nesting, thời gian, connection, redirect. Không dùng dữ liệu upstream trực tiếp để dựng URL/callback/file path.
6. **Cô lập tenant:** client bean dùng chung được, nhưng Authorization và correlation context phải theo **từng request**, không lưu token trong mutable singleton field.
7. **Logs/observability:** chỉ log endpoint template, status, latency, requestId an toàn; redaction Authorization, cookies và payload nhạy cảm.

Nếu Spring dùng OAuth2 client credentials, token service-to-service và token người dùng **không mặc nhiên thay thế nhau**. Đừng forward user token sang downstream không cùng audience. Interceptor/ExchangeFilterFunction phải an toàn khi nhiều request đồng thời và không làm rò token qua retries hoặc tracing.

## 12. Quyết định theo kiến trúc đang chạy

| Bối cảnh | Khởi đầu phù hợp | Vì sao |
| --- | --- | --- |
| Spring MVC đọc JSON rồi xử lý ngay | **RestClient** | Đồng bộ rõ, Jackson/HTTP integration của Spring |
| Java CLI/SDK không dùng Spring | **JDK HttpClient** | Ít dependency, có sync và CompletableFuture |
| Spring WebFlux gọi 3 API song song | **WebClient** | Mono/Flux và non-blocking I/O |
| Nhận SSE/NDJSON dài | **WebClient** hoặc stream JDK | Xử lý tăng dần, không gom body |
| Spring MVC trên Java 21 virtual threads | **RestClient/HttpClient** | Blocking vẫn dễ hiểu, có thể mở rộng thread chờ I/O |
| POST thanh toán với retry | **Bất kỳ lựa chọn nào** | Cốt lõi là idempotency, timeout, retry contract |

**Virtual threads (Java 21)** giúp blocking code quản lý nhiều luồng chờ I/O thuận tiện hơn, nhưng không tăng giới hạn connection, throughput downstream hay thay thế rate limit. Đừng chuyển toàn ứng dụng MVC sang reactive chỉ vì WebClient có Mono. Một WebFlux handler gọi JDBC hoặc thư viện blocking ngay trong event-loop vẫn có thể làm nghẽn hệ thống.

## 13. Kiểm thử client: đừng chỉ mock service method

Kiểm thử HTTP client cần chứng minh **URI, method, headers, JSON schema, status, timeout và retry**. Unit test của service dùng mock client không thấy được lỗi thực tế khi serialize request hoặc đọc response.

### 13.1. RestClient với MockRestServiceServer

Spring Test có thể gắn **MockRestServiceServer** vào **RestClient.Builder** để không phải gọi mạng thật. Ví dụ:

~~~java
@Test
void restClientSendsExpectedRequestAndReadsJson() {
    RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://catalog.example.internal");

    MockRestServiceServer server =
        MockRestServiceServer.bindTo(builder).build();

    RestClient rest = builder.build();

    server.expect(requestTo(
            "https://catalog.example.internal/api/v1/products/prod-42"))
        .andExpect(method(HttpMethod.GET))
        .andExpect(header(HttpHeaders.ACCEPT,
            MediaType.APPLICATION_JSON_VALUE))
        .andRespond(withSuccess("""
            {"id":"prod-42","name":"Java API Handbook",
             "priceVnd":180000}
            """, MediaType.APPLICATION_JSON));

    ProductView product = rest.get()
        .uri("/api/v1/products/{id}", "prod-42")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(ProductView.class);

    assertThat(product.id()).isEqualTo("prod-42");
    assertThat(product.priceVnd()).isEqualTo(180000);
    server.verify();
}
~~~

Ví dụ cần import JUnit, AssertJ và Spring Test MockRestServiceServer, các request matchers/response creators. **Đừng đưa bearer token thật vào assertion/log**; dùng token giả ở test hoặc xác nhận header tồn tại mà không hiển thị secret.

Một test riêng phải trả **404 application/problem+json** và xác nhận **onStatus** tạo ProductNotFoundException; test khác trả 503, kiểm tra rằng retry policy (nếu cấu hình) được thực thi **đúng số lần**, không chỉ nuốt exception.

### 13.2. HttpClient và WebClient với local mock HTTP server

Với **JDK HttpClient** hoặc **WebClient**, dùng HTTP server giả lập như **OkHttp MockWebServer**, WireMock hoặc một server test nội bộ. Chọn port động, trả status/headers/body có kiểm soát và kiểm tra request thực được gửi.

Ví dụ ý tưởng với MockWebServer:

~~~java
@Test
void jdkClientHandlesNotFound() throws Exception {
    try (MockWebServer server = new MockWebServer()) {
        server.start();
        server.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/problem+json")
            .setBody("""
                {"type":"about:blank","title":"Not found",
                 "status":404}
                """));

        JdkCatalogClient client = new JdkCatalogClient(
            URI.create(server.url("/").toString()), objectMapper);

        assertThrows(ProductNotFoundException.class,
            () -> client.find("prod-missing", "test-token"));

        RecordedRequest sent = server.takeRequest(
            1, TimeUnit.SECONDS);
        assertNotNull(sent);
        assertEquals("GET",
            sent.getMethod());
        assertEquals("/api/v1/products/prod-missing",
            sent.getPath());
    }
}
~~~

Dependency mock server là test-only; sử dụng URI loopback **chỉ trong test**, không cho phép URL bất kỳ trong production. Với WebClient, test bằng **StepVerifier**:

~~~java
StepVerifier.create(
    reactiveCatalogClient.find("prod-42", "test-token"))
    .assertNext(p -> assertEquals("prod-42", p.id()))
    .verifyComplete();
~~~

Trước test cần cấu hình mock server trả JSON phù hợp. **StepVerifier** phải subscribe vào Mono/Flux, vì không subscribe có thể không có HTTP request nào được gửi. Với SSE, mock server phát nhiều frame **id/event/data** và ngắt kết nối giữa chừng để test reconnect/cursor hoặc fallback.

### 13.3. Ma trận kiểm thử chung

| Tình huống | Bằng chứng |
| --- | --- |
| 200 JSON / 404 Problem Details | Đọc đúng DTO hoặc lỗi, kiểm tra Content-Type |
| 204/304 | Không đọc body giả |
| Timeout / reset | Phân loại lỗi, không dùng DTO mặc định |
| 429/503 + Retry-After | Backoff và attempt/deadline giới hạn |
| POST retry | Giữ nguyên Idempotency-Key và payload |
| Token T1/T2, redirect host lạ | Không lộ credential giữa tenant/origin |
| Body quá lớn, stream bị ngắt | Giới hạn memory, cancellation và reconnect |
| Nhiều request đồng thời | Giới hạn concurrency, connection và thread |
| Metrics/log | Không xuất token hoặc PII |

Khi đo hiệu năng, so **latency p95/p99, số socket, thread, memory, queue wait và throughput** dưới cùng workload; đừng kết luận dựa trên microbenchmark chỉ đo cú pháp gọi HTTP.

## 14. Bài tập: chọn client cho ba tích hợp

Bạn xây dựng hệ thống đặt hàng Java:

- **Catalog:** Spring MVC đọc Catalog GET, kỳ vọng độ trễ thấp.
- **Payment:** POST tạo payment intent; có thể mất response **sau commit**, cần chống tạo trùng.
- **Delivery:** dashboard theo dõi SSE, có thể mất kết nối.

Yêu cầu:

1. Chọn **HttpClient/RestClient/WebClient** cho từng mục theo stack, blocking, mức đồng thời, streaming và chi phí vận hành.
2. Viết HTTP transcript GET Catalog 200/404 và POST Payment dùng **Idempotency-Key**.
3. Cài một client với URI template, bearer token theo request, DTO, timeout, xử lý 404/429/503.
4. Thiết kế **retry có deadline, backoff+jitter**, giữ nguyên key/payload; nêu cách đối soát khi payment timeout.
5. Xử lý SSE bằng Flux và **Last-Event-ID + GET fallback**, không collectList vô hạn.
6. Viết tối thiểu **8 HTTP tests**: success, status lỗi, timeout, retry, tenant, redirect, stream bị ngắt và giới hạn tải.

**Sản phẩm:** bảng quyết định, mã Java/Spring, contract HTTP, chính sách timeout/retry/security, kết quả test và nhận xét hiệu năng.

## 15. Checklist trước khi đưa vào production

- Client phù hợp với **mô hình thread hiện có**, không blocking event-loop.
- Có **connect, read/response timeout** và tổng deadline; đặt connection/concurrency limit.
- Base URL và path **được validate/encode**, không nhận arbitrary endpoint từ client.
- TLS, OAuth2/Bearer, audience/scope, tenant và redirect policy đã được kiểm tra.
- Dựa vào **status + Content-Type + schema**, không parse lỗi thành DTO thành công.
- **404/409/429/503/timeout** có mapping và retry rule cụ thể.
- **POST retry** chỉ khi có idempotency/business reference và cơ chế đối soát.
- **SSE/file lớn** không tích lũy vô hạn, có cancellation/fallback.
- Đã có mock HTTP tests, HTTP integration tests và kiểm thử security.
- Có metrics theo endpoint, status và latency; log không chứa secrets.

**Kết luận:** **Java HttpClient** phù hợp nơi cần một HTTP client chuẩn JDK, độc lập Spring; **RestClient** là lựa chọn thực dụng cho phần lớn ứng dụng Spring MVC đồng bộ; **WebClient** có lợi khi hệ thống đã reactive hoặc cần pipeline nhiều I/O và streaming. Nhưng client nào cũng phải tuân **HTTP contract, timeout, security, idempotency và giới hạn tài nguyên**. Công cụ phù hợp nhất là công cụ giữ cho hệ thống đúng, dễ kiểm thử và vận hành được dưới tải thực tế.





