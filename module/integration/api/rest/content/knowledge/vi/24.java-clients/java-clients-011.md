# Connect timeout, response timeout và connection pool

## 1. Vấn đề: HTTP client chậm có thể làm nghẽn cả API

Trong module **INTEGRATION_API_REST**, client Java gọi REST API theo URI, phương thức HTTP, status và hợp đồng dữ liệu đã công bố. Ngoài thiết kế request/response, client phải có **time budget**, **connection pool** và cách xử lý lỗi mạng để không giữ vô hạn thread/socket khi upstream gặp sự cố.

Tình huống: **Order API** viết bằng Spring Boot gọi **Inventory API** để kiểm tra và giữ hàng. Nếu Inventory chậm:

- **Connect timeout** giúp không chờ mãi khi không thiết lập được connection mới.
- **Response timeout** giới hạn thời gian chờ phản hồi theo semantics transport.
- **Pool acquisition timeout** ngăn request đợi vô hạn khi mọi connection trong pool đều bận.
- **Read/socket timeout** giới hạn khoảng không nhận được dữ liệu khi đọc response.
- **Overall deadline** giới hạn tổng thời gian một logical operation, kể cả retry.

Thiếu những giới hạn này, thread pool của Order API có thể cạn trước cả khi Inventory lỗi hoàn toàn. Ngược lại, timeout quá ngắn tạo false failure, retry storm và lãng phí connection.

Sau bài học, bạn có thể phân biệt từng loại timeout, cấu hình **Java 17+ HttpClient**, **Apache HttpClient 5**, **Spring RestClient**, **Spring WebClient/Reactor Netty**, quản lý vòng đời connection, quan sát pool, kiểm thử fault và thiết kế retry an toàn.

## 2. Một HTTP request đi qua những giai đoạn nào?

~~~mermaid
sequenceDiagram
    participant C as Order API
    participant P as Connection Pool
    participant N as TCP/TLS
    participant U as Inventory API
    C->>P: Acquire connection
    Note over C,P: Pool acquisition timeout
    P->>N: Kết nối nếu cần
    Note over P,N: Connect timeout
    N->>U: Gửi HTTP request
    U-->>N: Response headers/body
    Note over N,U: Response và read timeout
    N-->>C: Status + body
    C->>P: Consume/close response
    Note over C,U: Overall deadline
~~~

| Giới hạn | Bắt đầu/kết thúc theo điều gì? | Vì sao cần? |
| --- | --- | --- |
| **Connection acquisition** | Chờ connection hoặc slot từ pool | Tránh queue tích tụ khi pool bão hòa |
| **Connect timeout** | Thiết lập connection mới | Đích không chấp nhận hoặc không phản hồi kết nối |
| **Response timeout** | Nhận response theo định nghĩa thư viện | Upstream nhận request nhưng xử lý/trả dữ liệu chậm |
| **Socket/read timeout** | Chờ dữ liệu trên connection đã thiết lập | Body đang stream rồi ngừng gửi |
| **Total/deadline** | Toàn bộ logic của một lần gọi, gồm queue, network, body, retry | Giữ trong ngân sách latency của request cha |

**Tên timeout không được chuẩn hóa giống nhau giữa các Java client.** Response timeout có thể gắn với thời gian chờ response hoặc inactivity giữa các lần đọc; **không mặc định là hard deadline cho toàn bộ body**. Connect timeout thường chỉ tác động **connection mới**, không có nghĩa bao trùm chắc chắn **DNS, TLS handshake, proxy CONNECT, redirect, retries**.

### 2.1. Timeout không phải HTTP status

Nếu Inventory không trả được HTTP response, client Java thường nhận **exception**, không nhận status 504 từ Inventory. **504 Gateway Timeout** là status mà **gateway/proxy** có thể trả khi chờ upstream quá lâu; **408 Request Timeout** là status server có thể trả khi chờ request. Khi Order API phục vụ caller, hãy ánh xạ lỗi mạng thành status và **Problem Details** theo vai trò gateway và hợp đồng API, không đồng nhất connect timeout với HTTP 408.

### 2.2. Kết nối được reuse thay đổi câu chuyện

HTTP/1.1 thường dùng một connection cho một request đang hoạt động; HTTP/2 có thể multiplex nhiều stream qua một connection nếu hai đầu hỗ trợ. Pool size **không tự là số request concurrent** trên mọi transport. Trên connection đã reuse, có thể không có TCP connect mới, nên connect timeout không kiểm soát một upstream đang giữ response quá lâu.

## 3. Time budget, pool size và lựa chọn giá trị

Ví dụ Order API có mục tiêu hoàn thành đường synchronous trong **1,5 giây**. Các giá trị minh họa dùng để test, **không phải preset production**:

| Thành phần | Giá trị thử |
| --- | ---: |
| Chờ lấy connection | **150 ms** |
| Connect mới | **300 ms** |
| Response/read theo client | **700 ms** |
| Overall Inventory call | **1.000 ms** |
| Retry POST giữ hàng chưa có idempotency guarantee | **0 lần** |
| Pool Apache HTTP/1.1 | **40 connections total, 20/route** |

Không cộng các con số rồi kết luận operation chắc chắn không vượt budget: timeout có thể lồng nhau, read timeout có thể được reset sau mỗi chunk, backoff và retries kéo dài tổng thời gian. **Deadline chung** cần được truyền vào orchestration và những request con còn đủ ngân sách.

Theo Little gần đúng, **concurrency = throughput × latency trung bình**. Nếu 100 call/s và mỗi call 200 ms, concurrency trung bình khoảng 20; upstream chậm tới 1 giây thì cần khoảng 100 call concurrent. Pool thiếu slot gây hàng đợi; mở pool vô hạn lại có thể làm upstream sập. Kết hợp pool với **bulkhead, queue cap, rate limit và backpressure**.

### 3.1. Timeout không tự hủy nghiệp vụ ở server

Nếu POST đã đến Inventory và commit nhưng response mất, client timeout không chứng minh nghiệp vụ chưa xảy ra. Retry POST cần **idempotency contract** thực sự ở upstream, ví dụ **Idempotency-Key** có scope theo tenant/operation/fingerprint/TTL. Chỉ retry an toàn về mặt ngữ nghĩa sau khi xem method, trạng thái kết nối, outcome ambiguity và deadline.

## 4. Java 17+: java.net.http.HttpClient

Java cung cấp **HttpClient** có connect timeout trên client và request timeout trên HttpRequest:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class InventoryJdkClient {
    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(300))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_2)
        .build();

    public String getStock(String sku) throws Exception {
        // Trong production: kiểm soát/encode sku thành path segment.
        URI uri = URI.create(
            "https://inventory.example.test/api/v1/stocks/" + sku);

        HttpRequest request = HttpRequest.newBuilder(uri)
            .GET()
            .header("Accept", "application/json")
            .timeout(Duration.ofMillis(900))
            .build();

        HttpResponse<String> response = http.send(
            request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new InventoryHttpException(response.statusCode());
        }
        return response.body();
    }
}
~~~

**InventoryHttpException** là exception riêng của ứng dụng, không phải lớp JDK. Cần parse/validate JSON thực, kiểm content-type, giới hạn response và xử lý InterruptedException phù hợp.

- **connectTimeout** áp cho việc **thiết lập connection mới**; không giúp giới hạn read trên connection reuse.
- **HttpRequest.timeout** định nghĩa timeout request theo JDK. Khi quá hạn có thể gặp **HttpTimeoutException**; ở giai đoạn connection có thể gặp **HttpConnectTimeoutException**. Đây là exception client, không phải status của upstream.
- JDK HttpClient có cơ chế reuse/pool kết nối nội bộ nhưng **không expose trực tiếp max-per-route/pool-acquire timeout trên builder chuẩn** như Apache HttpClient.
- **HTTP_2 là lựa chọn ưu tiên**, không bảo đảm server negotiation thành công; kiểm **response.version()**.
- **BodyHandlers.ofString** materialize response vào bộ nhớ; không dùng cho body không giới hạn hoặc file lớn nếu không có cơ chế giới hạn. Với streaming subscriber, phải close/cancel và giải phóng tài nguyên.
- Tái sử dụng HttpClient thay vì new cho mỗi request, vì tạo mới làm giảm connection reuse và tăng chi phí TLS.

### 4.1. Asynchronous timeout và cancellation

~~~java
CompletableFuture<HttpResponse<String>> future =
    http.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.orTimeout(1, TimeUnit.SECONDS)
    .whenComplete((result, failure) -> {
        if (failure != null) {
            // Phân loại timeout/transport/cancellation.
            return;
        }
        // Kiểm status, header, body.
    });
~~~

**orTimeout** làm future hoàn tất lỗi khi quá hạn, không chứng minh upstream đã hủy xử lý, transaction đã rollback hoặc connection lập tức được đóng. Kiểm thử behavior hủy và timeout của BodyHandler đang dùng; không retry một POST chỉ vì future thất bại.

## 5. Apache HttpClient 5: pool, acquire và response timeout

Với workload đồng bộ cần **pool size, per-route cap, pool wait và eviction**, có thể dùng **Apache HttpClient 5 Classic**. Imports thuộc **org.apache.hc.client5**/**org.apache.hc.core5**; không pha API HttpClient 4.

| Thiết lập | Cơ chế Apache HttpClient 5 |
| --- | --- |
| Max connections total/per route | PoolingHttpClientConnectionManagerBuilder |
| Timeout chờ connection từ pool | RequestConfig.setConnectionRequestTimeout |
| TCP connect timeout | ConnectionConfig.setConnectTimeout |
| Response timeout | RequestConfig.setResponseTimeout |
| Socket read/inactivity | ConnectionConfig.setSocketTimeout khi hỗ trợ |
| TTL và idle cleanup | ConnectionConfig.setTimeToLive, HttpClientBuilder eviction |

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

public final class InventoryApacheFactory {
    public static CloseableHttpClient create() {
        ConnectionConfig conn = ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofMilliseconds(300))
            .setSocketTimeout(Timeout.ofMilliseconds(700))
            .setTimeToLive(TimeValue.ofMinutes(5))
            .build();

        PoolingHttpClientConnectionManager pool =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(40)
                .setMaxConnPerRoute(20)
                .setDefaultConnectionConfig(conn)
                .build();

        RequestConfig request = RequestConfig.custom()
            .setConnectionRequestTimeout(Timeout.ofMilliseconds(150))
            .setResponseTimeout(Timeout.ofMilliseconds(700))
            .build();

        return HttpClients.custom()
            .setConnectionManager(pool)
            .setDefaultRequestConfig(request)
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .build();
    }
}
~~~

**Các builder phụ thuộc nhánh version thư viện**; compile/test với một phiên bản Apache 5 nhất quán. Response timeout của Apache Classic không thay deadline cho cả logical operation. Nếu dùng async/HTTP2, semantics pool/stream khác; cần kiểm riêng.

**Tạo HttpClient và pool một lần** theo application lifecycle, đóng khi shutdown. Eviction có thể dùng background threads; new client mỗi request vừa tốn socket/TLS vừa khó kiểm soát tài nguyên.

### 5.1. Close response, không leak pool

Giả sử **http** đã là singleton:

~~~java
HttpGet get = new HttpGet(
    "https://inventory.example.test/api/v1/stocks/SKU-001");

try (CloseableHttpResponse response = http.execute(get)) {
    if (response.getCode() != 200) {
        throw new InventoryHttpException(response.getCode());
    }
    HttpEntity entity = response.getEntity();
    String json = EntityUtils.toString(entity);
    // Kiểm body size và parse đúng DTO trong implementation thật.
}
~~~

**Không close singleton http client sau mỗi lời gọi**, chỉ close từng response và sau cùng shutdown client. **EntityUtils.toString** có thể đưa body lớn lên heap; tránh nếu payload không bị giới hạn. Khi đóng response chưa đọc hết, connection có thể bị đóng thay vì reuse; tuy nhiên bỏ quên response còn nguy hiểm hơn vì làm **leased** tăng và **pending** tích tụ.

## 6. Spring RestClient và RestTemplate: cấu hình request factory

**RestClient** (Spring Framework 6.1+) là client đồng bộ fluent; **RestTemplate** tồn tại ở dự án cũ. Timeout và pool của chúng thường đến từ **ClientHttpRequestFactory**, nên thay transport có thể đổi semantics.

Tích hợp Apache HttpClient đã cấu hình ở mục 5 vào Spring:

~~~java
@Configuration
public class InventoryClientConfig {
    @Bean(destroyMethod = "close")
    CloseableHttpClient inventoryApacheClient() {
        return InventoryApacheFactory.create();
    }

    @Bean
    RestClient inventoryRestClient(CloseableHttpClient inventoryApacheClient) {
        var requestFactory =
            new HttpComponentsClientHttpRequestFactory(
                inventoryApacheClient);
        return RestClient.builder()
            .baseUrl("https://inventory.example.test")
            .requestFactory(requestFactory)
            .build();
    }
}
~~~

~~~java
public InventoryStockDto findStock(String sku) {
    return inventoryRestClient.get()
        .uri("/api/v1/stocks/{sku}", sku)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(InventoryStockDto.class);
}
~~~

**InventoryStockDto** là DTO ứng dụng. URI templates giúp encode dữ liệu path, nhưng vẫn cần validate SKU và kiểm destination. **retrieve()** có behavior lỗi 4xx/5xx; cần xử lý **404, 409, 429, 503** và timeout riêng, không catch Exception rồi trả stock=0.

Với **RestTemplate**, dùng **new RestTemplate(requestFactory)** và giữ singleton tương tự. Các transport khác như JDK HttpClient hoặc Simple request factory có giới hạn pool/timeout khác, cần test lại sau khi thay. Không tạo RestClient/RestTemplate/pool bên trong handler mỗi request.

## 7. Spring WebClient và Reactor Netty

Với **WebClient** dùng transport **Reactor Netty**, pool được điều khiển qua **ConnectionProvider**, không lấy cấu hình Apache HttpClient.

~~~java
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class InventoryReactiveConfig {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryConnections() {
        return ConnectionProvider.builder("inventory")
            .maxConnections(40)
            .pendingAcquireTimeout(Duration.ofMillis(150))
            .maxIdleTime(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    WebClient inventoryWebClient(ConnectionProvider provider) {
        HttpClient netty = HttpClient.create(provider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
            .responseTimeout(Duration.ofMillis(700));

        return WebClient.builder()
            .baseUrl("https://inventory.example.test")
            .clientConnector(new ReactorClientHttpConnector(netty))
            .build();
    }
}
~~~

- **maxConnections** đặt giới hạn pool; với HTTP/2 cần xét cả **concurrent streams**.
- **pendingAcquireTimeout** giới hạn chờ pool khi hết slot.
- **CONNECT_TIMEOUT_MILLIS** là timeout connect của Netty.
- **responseTimeout** gắn với network response/read; **không phải tổng deadline** gồm backoff và retry.
- **maxIdleTime** tránh reuse connection idle quá lâu; eviction phải được hỗ trợ/cấu hình theo version.
- **Mono.timeout** có thể đặt một deadline cho reactive sequence.

~~~java
Mono<InventoryStockDto> getStock(String sku) {
    return inventoryWebClient.get()
        .uri("/api/v1/stocks/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryStockDto.class)
        .retryWhen(Retry.backoff(1, Duration.ofMillis(100))
            .filter(this::isSafeTransientFailure))
        .timeout(Duration.ofSeconds(1));
}
~~~

**isSafeTransientFailure** là logic do ứng dụng định nghĩa: không retry 401/403/404 hay POST chỉ vì timeout. Đặt **timeout sau retry** khiến deadline bao luôn thời gian backoff của sequence. Khi timeout/hủy subscription, **không mặc định upstream đã rollback**. Cấu hình codec/body-size limit để không giữ JSON lớn trong memory.

Không gọi **block()** trong Reactor event-loop. Trong Spring MVC servlet, có thể tích hợp WebClient nhưng phải xác định rõ điểm blocking và ngân sách thread. Pool và event-loop resources cần được dispose lúc shutdown theo đúng ownership, không tạo WebClient/provider mới mỗi request.

## 8. Pool sizing, keep-alive và quản lý vòng đời

| Thông số | Mục đích |
| --- | --- |
| Max total, max per route | Không mở socket vô hạn hoặc để một upstream chiếm pool |
| Pending acquire timeout/queue | Fail fast khi bão hòa thay vì xếp hàng mãi |
| Idle timeout, TTL, eviction | Tránh reuse socket chết do NAT/proxy/LB/pod restart |
| Connection validation | Phát hiện stale/closed connection đúng khả năng client |
| Bulkhead per dependency | Giới hạn số operation, kể cả HTTP/2 streams |
| Close response | Trả connection về pool hoặc giải phóng socket |

**Pool lớn không cứu được upstream đang quá tải.** Ví dụ latency tăng từ 200 ms lên 1 giây ở cùng 100 requests/s thì số call đồng thời trung bình tăng khoảng 20 → 100. Tăng pool bừa bãi có thể khiến Inventory sập nặng hơn. Thiết lập giới hạn truy cập, backpressure, quota và đo p95.

HTTP/1.1 thường một request đang hoạt động trên mỗi connection; **HTTP/2 multiplex** được nhiều streams và có flow control. Do đó số TCP connections không luôn bằng mức concurrency. **HTTP keep-alive** giúp giảm TCP/TLS handshake nhưng server có thể đóng idle connection trước client; cần xử lý stale socket và connection reuse có giới hạn.

**Tránh hai lỗi vòng đời:** tạo client/pool mới mỗi request; hoặc giữ singleton nhưng **không close response body**. Khi leaked response, pool có thể giữ **leased=max**, **idle=0**, **pending tăng** dù upstream không gặp lỗi. Với streaming, bảo đảm release/cancel khi caller ngừng dùng dữ liệu.

## 9. Retry, timeout và idempotency

Retry phải dựa trên **lỗi có tạm thời không**, **method có an toàn khi lặp không**, và **deadline còn bao nhiêu**.

| Loại operation | Hướng retry |
| --- | --- |
| **GET/HEAD** | Có thể retry ít lần, giới hạn thời gian và quota |
| **PUT/DELETE** | HTTP idempotent nhưng vẫn xét If-Match/concurrent changes và outcome |
| **PATCH** | Phụ thuộc semantics và precondition |
| **POST tạo đơn/giữ hàng** | Không mặc định; cần Idempotency-Key/operation ID tại server |

Không retry vô hạn trên **429/503**. Đọc **Retry-After** khi áp dụng, backoff có jitter, giới hạn attempts và không retry nếu overall deadline sắp hết. Nếu SDK, gateway và app cùng retry, một request có thể nhân thành nhiều attempts, gây **retry storm**. Dùng **circuit breaker** khi upstream lỗi kéo dài và **bulkhead** để giới hạn tải; các cơ chế này bổ sung chứ không thay timeout.

### 9.1. POST timeout sau commit: kết quả chưa xác định

~~~http
POST /api/v1/reservations HTTP/1.1
Authorization: Bearer <token>
Idempotency-Key: order-555-reservation
Content-Type: application/json

{"orderId":"555","sku":"SKU-001","quantity":2}
~~~

Inventory có thể commit reservation nhưng response mất trước khi về client. Nếu client gửi lại với key mới, có thể giữ hàng **hai lần**. Upstream cần dedup theo **tenant, operation, key, payload fingerprint, TTL** và lưu outcome; client giữ nguyên key hoặc tra business operation ID. **Timeout không chứng minh transaction đã rollback.**

## 10. Bảo mật và cách báo lỗi dependency

| Rủi ro | Phòng vệ |
| --- | --- |
| **SSRF** do nhận URL tùy ý | Base URL cố định, allowlist scheme/host/IP; xét DNS rebinding và proxy egress |
| Redirect mang Authorization sang host lạ | Tắt redirect tự động hoặc kiểm destination |
| TLS verification bị vô hiệu | Không dùng trust-all hoặc disable hostname verification |
| Log lộ credential/PII | Redact bearer token, cookies, signed URLs, body |
| Response JSON rất lớn | Giới hạn bytes, codec memory, depth, collection |
| Token tenant A dùng sai cho tenant B | Auth header theo request, không gắn vào mutable shared state |
| Pool bị coi như nơi giữ quyền | Server vẫn phải kiểm authn/authz/tenant từng request |

URI của client nên có **base origin cố định** và parameter được validate/encode, không nhận raw full URL rồi gọi trực tiếp. **Connect timeout không phòng chống SSRF.** CORS cũng không bảo vệ server-side Java client.

Khi Order API là gateway cho Inventory, **504 Gateway Timeout** có thể phù hợp khi chờ upstream quá hạn; **503 Service Unavailable** có thể phù hợp với bão hòa tại local pool/admission; **502 Bad Gateway** khi upstream trả response lỗi định dạng. Không tự trả 504 cho mọi lỗi ứng dụng: status public phải theo vai trò và contract.

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.test/problems/dependency-timeout",
  "title":"Inventory timeout",
  "status":504,
  "code":"INVENTORY_TIMEOUT",
  "detail":"Chưa xác nhận được tồn kho trong thời gian cho phép."
}
~~~

Không trả IP, hostname nội bộ, raw request chứa secret, token hoặc stack trace qua Problem Details. Ghi trace ID an toàn để điều tra.

## 11. Quan sát kết nối và timeout

Nếu chỉ đo tổng latency, khó biết request bị chặn ở **pool** hay đang đợi **upstream**. Nên thu thập metrics theo dependency và route template:

| Metric | Diễn giải |
| --- | --- |
| **Leased/active, idle/available** | Connection đang bận và có thể reuse |
| **Pending acquire, pool wait time** | Request chờ slot, phát hiện pool saturation |
| **Connect timeout count** | Không thiết lập connection mới kịp |
| **Response/read timeout count** | Upstream chậm hoặc body stall |
| **Latency p50/p95/p99** | Độ trễ caller thực chịu |
| **Retry attempts/successes** | Retry hữu ích hay tạo retry storm |
| **HTTP statuses / transport errors** | Server trả lỗi khác với exception mạng |
| **Socket, thread, heap usage** | Leak và áp lực tài nguyên |

**Leased=max, idle=0, pending cao** thường gợi ý response leak, pool nhỏ hoặc request quá dài. **Connect timeout cao, pool rảnh** cần kiểm tra network/DNS/TLS/proxy trước khi tăng pool. Với HTTP/2, thêm metric **concurrent streams**.

Log phương thức, route template, dependency, attempt, status/error class, duration và correlation ID. Không dùng raw URL có secret, token hoặc userId làm nhãn metric.

## 12. OpenAPI không tự đặt timeout cho client Java

OpenAPI mô tả hợp đồng HTTP, **không có thuộc tính chuẩn chung** khiến mọi Java SDK đồng bộ connect/response/pool timeout. Ví dụ Order API công bố các lỗi khi phụ thuộc Inventory:

~~~yaml
openapi: 3.1.0
info:
  title: Order API
  version: 1.0.0
paths:
  /api/v1/orders/{id}/availability:
    get:
      operationId: checkAvailability
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200':
          description: Thông tin khả dụng
          content:
            application/json:
              schema:
                type: object
                required: [available]
                properties:
                  available: { type: boolean }
        '401': { description: Chưa xác thực }
        '403': { description: Không đủ quyền }
        '503': { description: Dependency quá tải }
        '504':
          description: Gateway chờ upstream quá hạn
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: { type: string }
        title: { type: string }
        status: { type: integer }
        code: { type: string }
~~~

Cấu hình timeout/pool/retry thuộc SDK và deployment, cần test riêng. Nếu POST hỗ trợ Idempotency-Key, công bố scope, repeat-response semantics và TTL trong hợp đồng.

## 13. Kiểm thử lỗi mạng và connection pool

Unit test mock một service ném TimeoutException chỉ kiểm mapper lỗi, **không chứng minh HTTP client thực sự giới hạn thời gian**. Dùng **MockWebServer/WireMock** để trì hoãn headers/body, tạo 429/503, stream lâu; dùng fault proxy kiểm tra TCP connect stall.

### 13.1. Test request timeout khi headers chậm

~~~java
@Test
void lateHeadersTriggerTimeout() throws Exception {
    MockWebServer server = new MockWebServer();
    server.enqueue(new MockResponse()
        .setHeadersDelay(1, TimeUnit.SECONDS)
        .setBody("{\"available\":true}"));
    server.start();

    try {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(300))
            .build();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(server.url("/stock").toString()))
            .timeout(Duration.ofMillis(150))
            .GET()
            .build();

        assertThrows(HttpTimeoutException.class,
            () -> client.send(request,
                HttpResponse.BodyHandlers.ofString()));
    } finally {
        server.shutdown();
    }
}
~~~

Cần JUnit, MockWebServer dependency và imports phù hợp. Server local **đã nhận connection nhưng trì hoãn headers**; đây là test request/response timeout, **không phải connect timeout**. Để test connect timeout, dùng network fault injection có kiểm soát; không dựa vào IP public ngẫu nhiên gây CI flaky.

### 13.2. Pool exhausted rồi phục hồi

Apache HttpClient 5: đặt **maxConnPerRoute=1**, **connectionRequestTimeout=100 ms**. Request A giữ response stream; B tới cùng route khi A chưa đóng → **acquire timeout**. Đóng/cancel A; C phải thành công, **leased/pending giảm**. Dùng latch/barrier thay vì sleep tùy ý. Với HTTP/2, test theo concurrency streams thực tế.

| Test | Kỳ vọng |
| --- | --- |
| 200 nhanh | DTO hợp lệ, reuse client |
| Connect stall | Connect timeout đúng loại |
| Headers chậm | Response/request timeout |
| Body ngừng gửi | Read/deadline giới hạn |
| Pool hết slot | Acquisition timeout, không chờ vô hạn |
| Đóng response sau lỗi | Pool hồi phục |
| GET 503/429 | Retry budget và Retry-After hợp lý |
| POST commit, response mất | Không duplicate reservation |
| Redirect sang host lạ | Authorization không rò |
| TLS certificate sai | Không trust-all |
| JSON body khổng lồ | Body/codec size cap |
| 401/403/404 | Không retry vô hạn |
| WebClient pending acquire | Timeout có hiệu lực |
| HTTP/2 multiplex | Đếm streams đúng |
| Cancellation/shutdown | Không leak socket/thread |

Kiểm tra **DB/business outcome** sau POST timeout, không chỉ exception Java. Một timeout ở client không bảo đảm server không thực thi.

## 14. Chẩn đoán triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Điều tra |
| --- | --- | --- |
| Connect timeout, pool còn rảnh | DNS/proxy/firewall/TLS/route | Network trace, fault test |
| Pool acquire timeout | Pool nhỏ, response leak, request dài | Leased, idle, pending |
| Response timeout | Inventory chậm, body stall | Server latency, time-to-first-byte |
| Tăng pool lại giảm throughput | Quá tải upstream | Bulkhead, giảm concurrency |
| Lỗi xuất hiện sau nhiều giờ | Stale idle socket, LB/NAT, leak | TTL/eviction, response close |
| Retry làm 503 cao hơn | Multi-layer retry | Budget, backoff, circuit breaker |
| Heap tăng theo response | Materialize body lớn | Byte cap, streaming |
| Proxy 504 khác client timeout | Time budget các hop lệch | Trace proxy/app/upstream |

**Không sửa mọi timeout bằng cách tăng timeout.** Phải tách queue wait, connect, upstream xử lý, download body và retry.

## 15. Bài thực hành: Inventory client có budget một giây

**Bối cảnh:** Order API gọi **GET /api/v1/stocks/{sku}** và **POST /api/v1/reservations**. Inventory call phải có deadline **1 giây**, giới hạn concurrent load và không tạo reservation trùng.

**Nhiệm vụ (100 điểm):**

1. **Thiết kế (20):** phân biệt connect/acquire/response/read/deadline; sizing pool cho HTTP/1.1 và HTTP/2.
2. **Spring/Java (30):** xây singleton RestClient + Apache 5 hoặc WebClient + Reactor Netty, cấu hình timeout/pool/cleanup.
3. **Bảo mật (25):** cố định host, chặn SSRF và redirect rò token, body cap, POST Idempotency-Key.
4. **Kiểm thử (25):** tám case gồm headers chậm, body stall, exhausted pool, close/recovery, 429/503, POST lost response và TLS/redirect.

**Hướng giải:** overall deadline bao trùm timeout các pha và retry; dùng bulkhead/pool giới hạn. GET retry tối đa một lần nếu transient và còn budget; POST không retry thiếu idempotency contract. Kiểm bằng MockWebServer/WireMock, fault proxy và metrics chứng minh pool phục hồi.

## 16. Checklist và tài liệu tham khảo

- [ ] Phân biệt **connect, acquire, response, read timeout, overall deadline**.
- [ ] Không coi timeout Java là HTTP 408/504 tự động.
- [ ] Reuse client/pool, cấu hình total/per route, idle/TTL, close response.
- [ ] RestClient/RestTemplate dùng request factory phù hợp.
- [ ] WebClient/Reactor Netty có pendingAcquireTimeout và lifecycle.
- [ ] Retry theo method, deadline, idempotency và bulkhead.
- [ ] Không nhận untrusted URL, redirect rò token hoặc body vô hạn.
- [ ] Có metrics leased/idle/pending và test network failure/recovery.

**Ghi nhớ:** timeout kiểm soát **chờ bao lâu**, pool kiểm soát **bao nhiêu lời gọi dùng tài nguyên cùng lúc**, retry/idempotency quyết định **thử lại có an toàn không**. Chúng phải cùng tuân thủ time budget của request cha.

**Nguồn:** RFC 9110, RFC 9457; Java SE HttpClient API; Apache HttpComponents Client 5; Spring RestClient/WebClient; Reactor Netty Reference; OpenAPI 3.1; MockWebServer, WireMock, Toxiproxy.
