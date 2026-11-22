# Timeout, connection pool, TLS và vòng đời tài nguyên của HTTP client đồng bộ

## 1. Vấn đề thực tế và mục tiêu

Trong một ứng dụng Spring MVC, batch job hay Java service, khi gọi REST API bằng `RestClient` hoặc `RestTemplate`, caller thường **chờ đồng bộ** cho đến khi có HTTP response hoặc lỗi. Nếu upstream chậm, việc chờ này có thể giữ Java worker thread, chiếm một connection trong outbound pool, tạo pending queue và kéo theo timeout dây chuyền. Ngay cả API có business logic đơn giản vẫn có thể cạn worker threads, file descriptors hay sockets nếu các giới hạn không được cấu hình.

Bốn vấn đề phải được xử lý đồng thời:

1. **Timeout:** mất bao lâu để lấy connection từ pool, DNS/TCP connect, TLS handshake, gửi request và chờ response? Giới hạn thời gian nào bảo vệ toàn bộ HTTP call?
2. **Connection pool:** connection được tạo, cho thuê, trả lại, tái sử dụng, kiểm tra stale và đóng theo policy nào? Chia giới hạn tổng và theo route thế nào?
3. **TLS:** client tin certificate nào, xác minh hostname ra sao, khi nào dùng truststore, keystore, mTLS? Làm gì khi gặp `SSLHandshakeException`?
4. **Resource lifecycle:** RestClient/factory/pool được tạo một lần hay từng request, ai là chủ sở hữu để đóng, khi nào dọn idle connections và response streams?

**Phạm vi:** Java 17, Spring Framework 6.1/6.2, Spring Boot 3.3.x, Spring `RestClient` và `RestTemplate`, JDK `java.net.http.HttpClient`, Apache HttpClient 5.x. Đây là bài **HTTP client đồng bộ**, không phải WebClient reactive. Bản ví dụ hoàn chỉnh sử dụng Spring Boot **3.3.13** / Java **17** và Apache HttpClient 5, có mock HTTP upstream chạy trên localhost, không cần gọi dịch vụ Internet.

### Học xong bạn cần trả lời được

- Timeout kết nối khác timeout đợi response và chờ thuê connection như thế nào?
- Vì sao 700 ms response timeout **không** bảo đảm toàn bộ call kết thúc trước 700 ms?
- Khi pool max 5 connections tới một upstream, request thứ sáu đi đâu?
- Vì sao keep-alive giảm TCP/TLS handshake, nhưng idle connection cũng có thể stale?
- RestClient có tự động đảm bảo cùng pool/timeouts trên mọi môi trường không?
- Spring 6.1 và Spring 6.2 khác nhau thế nào ở HttpComponents request factory?
- PKIX/hostname mismatch phải xử lý thế nào **mà không tắt TLS verification**?
- Khi POST timeout, retry có thể tạo duplicate record không?
- Vì sao Java 17 JDK HttpClient chưa có `close()` public như Java 21?
- Làm sao viết JUnit tests kiểm chứng HTTP status vs transport timeout và đóng pool đúng lifecycle?

## 2. Một synchronous HTTP call gồm các giai đoạn nào?

```text
Inbound MVC request / background job
                 |
                 v
       RestClient.get(...).retrieve().body(...)
                 |
          Caller thread chờ
                 |
       ClientHttpRequestFactory
                 |
                 +--- [A] Pool lease / acquire connection
                 |         Có thể phải chờ nếu pool đầy
                 |
                 +--- [B] DNS resolution (nếu chưa cache)
                 |
                 +--- [C] TCP connect (nếu không reuse)
                 |
                 +--- [D] TLS handshake + certificate/hostname check
                 |         Chỉ HTTPS, thường không cần lặp khi reuse
                 |
                 +--- [E] Gửi HTTP headers/body
                 |
                 +--- [F] Chờ status/headers/body
                 |
                 +--- [G] Decode JSON, xử lý HTTP error status
                 |
                 +--- [H] Consume/close response, release pool resource
                 |
                 v
        Trả DTO/ResponseEntity hoặc exception
```

Một request có thể bỏ qua [B]–[D] khi connection đang sống được reuse. Với HTTP/2, nhiều logical streams có thể chia sẻ một connection khi client/transport và server hỗ trợ; không giả định HTTP/2 trên tất cả synchronous HTTP clients.

**Connection không phải worker thread.** Apache connection pool quản lý outbound sockets; Tomcat worker pool quản lý inbound request execution. Nếu 100 Tomcat workers cùng muốn gọi một upstream mà Apache per-route limit chỉ 10, phần lớn có thể đang chờ acquire. Tăng Tomcat maxThreads không khắc phục được outbound pool saturation.

## 3. Phân loại timeout: đúng tầng, đúng ý nghĩa

| Tên | Giai đoạn | Ý nghĩa |
| --- | --- | --- |
| Pool acquire / connection-request timeout | [A] | Thời gian tối đa chờ một connection từ pool |
| DNS lookup timeout | [B] | Phụ thuộc resolver/OS/JVM/client; không luôn có setting độc lập |
| TCP connect timeout | [C] | Giới hạn kết nối mới tới host:port |
| TLS handshake timeout | [D] | Giới hạn phiên TLS/ALPN và certificate exchange; có thể cấu hình riêng |
| Write/socket timeout | [E] | Chờ ghi bytes; semantics tùy engine |
| Response timeout | [F] | Đợi response theo HTTP client, không mặc nhiên toàn call |
| Socket read inactivity timeout | [F] | Đợi dữ liệu tiếp theo; stream có thể kéo dài qua nhiều khoảng |
| Whole-call deadline | [A]–[H] | Ngân sách thời gian nghiệp vụ tổng thể; thường cần policy riêng |
| Idle timeout / connection TTL | Sau call | Khi nào pool đóng socket không dùng hoặc quá tuổi |
| Gateway/proxy timeout | Ngoài JVM | Có thể trả 502/504 dù client/remote có policy khác |

### 3.1. Connect timeout chỉ giới hạn một giai đoạn

Giả sử TCP kết nối sau 5 ms, server giữ request 15 giây rồi trả body. Nếu client chỉ đặt connect timeout 1 giây, caller vẫn có thể chờ lâu vì bước connect đã hoàn tất. Cần timeout cho response/read và **overall deadline** khi business có SLA.

### 3.2. Lease timeout khác connect timeout

Nếu Apache pool max 5 connections và đã có 5 calls đang bận, call thứ sáu có thể chờ **trong pool trước khi mở bất kỳ TCP socket mới nào**. Nếu lease timeout 200 ms và không có connection được trả về kịp, call có thể fail mà upstream không nhìn thấy request thứ sáu. Việc tăng TCP connect timeout không giúp.

### 3.3. TLS handshake không đơn giản thuộc connect timeout

Trong Spring Framework 6.1, `HttpComponentsClientHttpRequestFactory#setConnectTimeout` cấu hình Apache RequestConfig connection timeout nhưng Javadoc cảnh báo **không bao trùm SSL handshakes hoặc HTTP CONNECT**; có thể cần low-level socket/TLS config. Với JDK HttpClient, thời gian TLS/request thuộc các APIs và implementation semantics khác. Không dùng cụm “connectTimeout bao luôn TLS” khi chưa xác minh engine/version.

### 3.4. Response timeout không phải total wall-clock cap

Một server có thể gửi headers rồi stream body thành nhiều chunks, mỗi chunk đến trước ngưỡng inactivity timeout nhưng tổng download mất hàng phút. Các response/socket timeouts có semantics theo engine. Nếu business cần SLA 2 giây, phải đo deadline end-to-end và phối hợp timeout/cancellation/retry policy; riêng `setResponseTimeout(2s)` chưa đủ để cam kết mọi byte đã đọc xong trước 2 giây.

### 3.5. Timeout có thể không dừng side effect từ remote

Client gửi POST tạo đơn hàng. Server đã lưu vào database, nhưng response bị mất giữa đường và client read timeout. Client **không thể suy ra operation đã rollback**. Retry POST không kiểm soát sẽ tạo đơn trùng. Cần idempotency key, unique constraints, bounded retries và quy tắc business rõ.

### 3.6. Ví dụ tính latency budget

API inbound có SLA 1.000 ms; một cách phân bổ minh họa:

| Bước | Budget ví dụ |
| --- | ---: |
| Authentication/validation | 100 ms |
| Lease outbound connection | 100 ms |
| TCP/TLS nếu cần mới | 200 ms |
| Wait upstream response | 450 ms |
| Encode/send inbound response, contingency | 150 ms |

Đây không phải benchmark: mỗi stage có thể overlap hoặc chậm bất thường; số liệu phải lấy từ metrics. Nếu downstream timeout lớn hơn SLA inbound, request dễ bị gateway trả 504 trước khi caller biết lỗi.

## 4. RestClient, RestTemplate và factory thật sự làm I/O

### 4.1. RestClient (Spring Framework 6.1+)

`RestClient` là API fluent **đồng bộ**:

```java
RestClient client = RestClient.builder()
    .baseUrl("https://api.example.test")
    .build();

Product product = client.get()
    .uri("/products/{id}", 42L)
    .retrieve()
    .body(Product.class);
```

Đây là snippet minh họa, cần DTO `Product` và server thật. Khi `retrieve()` nhận 4xx/5xx, Spring thường ném `RestClientResponseException` subtype tương ứng. Khi I/O lỗi, thường có `ResourceAccessException` với root cause khác. Khi 204 No Content hoặc body trống, `body(Product.class)` có thể trả null; tránh unbox/deserialize như thể luôn có object.

### 4.2. RestTemplate cũng đồng bộ

`RestTemplate` được Spring tiếp tục hỗ trợ, nhưng RestClient thuận tiện hơn với fluent style. Cả hai sử dụng `ClientHttpRequestFactory` để thực hiện I/O:

```java
RestTemplate template = new RestTemplate(requestFactory);
Product product = template.getForObject(
    "https://api.example.test/products/42", Product.class);
```

Đây là snippet có `requestFactory`/Product cần được cấu hình. Migrate RestTemplate sang RestClient **không tự** tạo timeouts/pool nếu request factory thực vẫn không được kiểm soát.

### 4.3. Các transport factories

| Spring factory | HTTP engine | Ý nghĩa |
| --- | --- | --- |
| `JdkClientHttpRequestFactory` | Java `java.net.http.HttpClient` | Có connect/read timeout APIs, JDK-managed connections |
| `HttpComponentsClientHttpRequestFactory` | Apache HttpClient 5 | Pool metrics/limits và lifecycle explicit |
| `SimpleClientHttpRequestFactory` | Java `HttpURLConnection` | Đơn giản, không có API pool tường minh như Apache |
| `JettyClientHttpRequestFactory` | Jetty HTTP client | Tuning riêng |
| `ReactorNettyClientRequestFactory` | Reactor Netty | Một request factory có thể dùng dưới synchronous RestClient facade |

Nếu không set factory, selection phụ thuộc Spring Framework version, HTTP libraries trên classpath và Spring Boot auto-configuration. **Không** giả định tất cả environments sử dụng chung các pool/timeout defaults. Với production, cấu hình request factory tường minh để dễ review/test.

### 4.4. RestClient.Builder do Boot quản lý

Spring Boot tạo `RestClient.Builder` đã có message converters, customizers và observation hooks theo application environment. Nên inject builder, tạo một RestClient bean/service-scoped client với base URL và factory nhất quán, thay vì `RestClient.create()` cho mỗi request.

```java
@Service
class ExternalGateway {
    private final RestClient client;

    ExternalGateway(RestClient.Builder builder) {
        client = builder.baseUrl("https://api.example.test")
            .build();
    }
}
```

Builder là mutable; khi dùng chung để build nhiều target clients, cân nhắc `clone()` hoặc các builder injections riêng. Không mutate builder trong request concurrent.

## 5. JDK HttpClient trên Java 17

Java 17 cung cấp `java.net.http.HttpClient`. Nó có pool/reuse phía implementation, redirects, SSLContext và HTTP/2 negotiation tùy server. Nhưng JDK 17 **không** có public API chuẩn tương đương Apache `setMaxConnPerRoute`/`getTotalStats` để giới hạn và quan sát pool chi tiết.

### 5.1. Tích hợp RestClient với JDK request factory

```java
HttpClient jdk = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

JdkClientHttpRequestFactory factory =
    new JdkClientHttpRequestFactory(jdk);
factory.setReadTimeout(Duration.ofSeconds(3));

RestClient client = RestClient.builder()
    .requestFactory(factory)
    .baseUrl("https://api.example.test")
    .build();
```

Đây là snippet Java17/Spring6.1+, cần imports `java.net.http.HttpClient`, `Duration` và Spring types. JDK request factory read timeout ánh xạ tới `HttpRequest.Builder.timeout` theo Javadoc Spring. Nó không giống hoàn toàn Apache socket read timeout trong mọi trường hợp.

### 5.2. Java HttpClient trực tiếp

```java
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example.test/data"))
    .timeout(Duration.ofSeconds(3))
    .GET()
    .build();

HttpResponse<String> response =
    jdk.send(request, HttpResponse.BodyHandlers.ofString());
```

`send` chặn thread gọi, còn `sendAsync` trả CompletableFuture và có lifecycle khác. Nếu dùng `BodyHandlers.ofInputStream()` hoặc `ofLines()`, cần consume/close stream đúng cách; nếu bỏ ngang, implementation có thể không reuse kết nối và giữ resources.

### 5.3. Lifecycle JDK 17 khác JDK 21

Trong **Java 17**, `java.net.http.HttpClient` chưa có public `close()`/`shutdown()` và không implement AutoCloseable như ở **Java 21**. Không viết mã Java17 `try (HttpClient c = ...)` hoặc `c.close()`. Reuse một instance ứng dụng thay vì tạo nhiều client tùy tiện; nếu yêu cầu pool lifecycle tường minh và metrics ở Java17, Apache HttpClient 5 thường thuận tiện hơn.

## 6. Apache HttpClient 5: pool, timeout và lifecycle rõ ràng

Apache 5 classic synchronous client thường được dùng bên dưới `HttpComponentsClientHttpRequestFactory`. Những tham số cơ bản:

| API/config | Công dụng |
| --- | --- |
| `PoolingHttpClientConnectionManagerBuilder.setMaxConnTotal(n)` | Số connections tối đa toàn pool |
| `setMaxConnPerRoute(n)` | Số connections tối đa tới một route |
| `ConnectionConfig.setConnectTimeout(...)` | TCP connect timeout |
| `ConnectionConfig.setSocketTimeout(...)` | Socket I/O timeout |
| `ConnectionConfig.setTimeToLive(...)` | Tuổi tối đa connection |
| `ConnectionConfig.setValidateAfterInactivity(...)` | Check pooled connection stale sau idle |
| `RequestConfig.setConnectionRequestTimeout(...)` | Chờ lấy connection từ manager |
| `RequestConfig.setResponseTimeout(...)` | Chờ response theo Apache semantics |
| `HttpClientBuilder.evictIdleConnections(...)` | Dọn idle connections |
| `evictExpiredConnections()` | Dọn connections quá tuổi |
| `HttpClientBuilder.disableAutomaticRetries()` | Tắt Apache-level retries để tự quản policy |

### 6.1. Chú ý về Spring 6.1 và 6.2

`HttpComponentsClientHttpRequestFactory` Spring **6.1** cung cấp `setConnectTimeout(Duration)` và `setConnectionRequestTimeout(Duration)` nhưng **chưa có `setReadTimeout(Duration)`**. Spring **6.2** bổ sung readTimeout setter cho Apache factory. Do đó trên Spring Boot 3.3.x (Spring Framework 6.1.x), cấu hình response timeout thông qua `RequestConfig.setResponseTimeout(...)` của Apache 5 là cách phù hợp. Trong khi đó, `JdkClientHttpRequestFactory.setReadTimeout(Duration)` đã có từ Spring 6.1.

Copy một blog dùng Spring 6.2 vào Boot 3.3 rồi gọi `factory.setReadTimeout(Duration...)` trên Apache factory có thể fail lúc compile. Phân biệt theo **actual class và Spring version**, không chỉ tên phương thức giống nhau.

### 6.2. Pool total và per-route

Nếu total=20, per-route=5, một upstream có tối đa 5 established/leased connections theo route; HTTP requests tiếp theo có thể xếp hàng để lease tới khi timeout hoặc connection được trả. Một "route" gắn với scheme/host/port/proxy path, không phải URL path như `/orders` vs `/customers`. Do đó nhiều API endpoints trên cùng host có thể tranh cùng giới hạn.

### 6.3. Pool size không phải caller concurrency

Application Tomcat có thể có 200 workers; Apache outbound pool chỉ có 10. 190 workers vẫn có thể đứng chờ lease. Tăng total connections có thể làm remote quá tải. Cần phối hợp caller thread pool, semaphores/bulkheads, rate limits và backend capacity.

### 6.4. Connection reused vs stale

Khi keep-alive còn hiệu lực, connection đã hoàn tất request A có thể xử lý request B mà không cần TCP/TLS handshake mới. Nếu load balancer đóng socket vì idle nhưng client không biết, reuse có thể fail. `validateAfterInactivity`, idle eviction, TTL và retry có kiểm soát giúp giảm stale reuse, nhưng không bảo đảm mọi network race biến mất.

### 6.5. Vì sao phải close body?

Khi HTTP response body đã được consume hoặc response được đóng đúng, engine có cơ hội trả/loại bỏ connection đúng trạng thái. Nếu nhận raw InputStream rồi không close, pool có thể giữ connection leased cho đến khi timeout/GC/transport abort. `RestClient.retrieve().body(Dto.class)` thường quản lý vòng đời decode thông thường; nhưng `exchange` callback/custom stream hoặc Apache low-level response phải tuân thủ contract close/consume.

## 7. TLS: trust, hostname và mTLS

### 7.1. HTTPS cần xác thực đối tác, không chỉ mã hóa

Khi kết nối `https://orders.example.test`, TLS client cần xác minh:

1. Certificate chain từ server có dẫn tới trust anchor được tin cậy không?
2. Certificate còn hiệu lực, đúng key usage/algorithm policies không?
3. SAN có khớp hostname trong URL **orders.example.test** không?
4. TLS protocol/cipher/ALPN có tương thích không?
5. Nếu server yêu cầu client certificate (mTLS), client có key/cert hợp lệ không?

Nếu server gửi certificate đúng CA nhưng SAN chỉ có `payments.example.test`, client phải reject cho `orders.example.test`. **Trust chain và hostname verification là hai việc bổ sung**, không thay nhau.

### 7.2. Truststore vs keystore

| Artifact | Nội dung | Dùng khi |
| --- | --- | --- |
| Truststore | CA certificates/trust anchors | Client xác minh server |
| Client keystore | Private key + client certificate chain | Server yêu cầu mTLS |
| SSLContext | Key/trust managers + TLS settings | Client cấu hình TLS |
| Hostname verification | So URL host và certificate SAN | Ngăn MITM endpoint giả |
| System trust | Root CA bundle/policy của JDK | HTTPS thông thường |

Không dùng header `X-Client-Cert` do untrusted client tự cung cấp làm bằng chứng mTLS. Nếu qua gateway, trust boundary/cert forwarding phải được thiết kế chặt.

### 7.3. Truststore riêng trong Java

Ví dụ minh họa Java17 (không phải file độc lập):

```java
KeyStore trust = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("/secure/api-truststore.p12"))) {
    trust.load(in, password);
}

TrustManagerFactory tmf =
    TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
tmf.init(trust);

SSLContext tls = SSLContext.getInstance("TLS");
tls.init(null, tmf.getTrustManagers(),
    new SecureRandom());

HttpClient httpsClient = HttpClient.newBuilder()
    .sslContext(tls)
    .connectTimeout(Duration.ofSeconds(2))
    .build();
```

Cần `KeyStore`, `InputStream`, `Files/Path`, `TrustManagerFactory`, `SSLContext`, `SecureRandom`, `HttpClient` và `Duration` imports. `password` là `char[]` lấy từ secrets, không hardcode. Custom truststore có thể **thay** system default roots; nếu muốn đồng thời tin public/private CA cần trust policy riêng. Không gộp trust managers bằng cách chấp nhận mọi certificate.

### 7.4. mTLS thêm client private key

Sau khi load client keystore, khởi tạo `KeyManagerFactory` và:

```java
SSLContext tls = SSLContext.getInstance("TLS");
tls.init(keyManagerFactory.getKeyManagers(),
    trustManagerFactory.getTrustManagers(),
    new SecureRandom());
```

Đây là snippet chỉ minh họa, cần load cả stores. mTLS xác nhận client certificate nhưng authorization người dùng/resource vẫn riêng biệt. Certificate/key rotation và grace period phải được lên kế hoạch.

### 7.5. Không sửa SSL lỗi bằng trust-all

**Không sử dụng**:

- `TrustManager.checkServerTrusted` method trống;
- `NoopHostnameVerifier.INSTANCE`;
- property tắt hostname verification;
- trust toàn bộ untrusted self-signed certificate;
- HTTP plaintext để tránh certificate issue trên traffic chứa credentials.

Khi gặp `PKIX path building failed` hoặc `SSLHandshakeException`, điều tra CA/intermediate chain, SAN, expiry, clock skew, protocol/cipher, proxy TLS interception và mTLS requirement. Nếu upstream dùng private CA, cấu hình truststore hợp lệ; **không bỏ kiểm tra certificate**.

### 7.6. JVM truststore system properties và Apache client

Một số engines có thể dùng hệ thống JSSE trust properties khi được cấu hình `useSystemProperties()`. Nhưng không giả định **mọi** Apache custom SSLContext đều tự nhận `-Djavax.net.ssl.trustStore=...`. Với đa client/tenant, nên cấu hình per-client truststore, tránh thay JVM global trust state ngoài ý muốn.

### 7.7. TLS handshake và pool reuse

Khi connection reused, không cần làm lại TLS handshake cho mỗi request. Khi bị idle eviction/TTL/remote close, kết nối mới cần handshake; p99 có thể khác giữa cold start và warm pool. HTTP/2 multiplexing, TLS session resumption, OCSP và ALPN còn làm khác chi phí connection. Benchmark cần xét cả hai trường hợp.

## 8. Timeout + retry + error taxonomy

### 8.1. Phân loại lỗi

| Trường hợp | Biểu hiện điển hình | Phản ứng |
| --- | --- | --- |
| 404 | `HttpClientErrorException.NotFound` với `retrieve()` | Nghiệp vụ không tìm thấy (nếu contract nói vậy) |
| 429 | TooManyRequests | Rate limit/Retry-After/backoff |
| 503 | ServiceUnavailable | Service outage, circuit breaker |
| TCP connect refused | `ResourceAccessException` bọc ConnectException | Host/port/listener/network |
| Connect timeout | ResourceAccessException/root timeout | Network path/DNS/firewall |
| Pool lease timeout | Apache request connection manager timeout | pool stats, active/pending |
| Response/socket timeout | I/O exception | upstream latency, response policy |
| Bad certificate | `SSLHandshakeException`/PKIX | chain, truststore, hostname |
| JSON decode error | message conversion exception | DTO/schema/media type |
| 204 response | body có thể null | API contract no-content |
| Redirect ngoài host | 3xx/redirect policy | chống SSRF/credential leak |

Các exception chi tiết thay đổi theo Spring/Apache/JDK version; log root cause an toàn và phân biệt HTTP status (remote thực sự trả) với I/O failure (có thể chưa có HTTP response).

### 8.2. Retry không phải công tắc bật là xong

- HTTP 400/401/403: thường không retry.
- 404: chỉ retry khi eventual consistency đã có thỏa thuận.
- 429: giảm tốc, tôn trọng `Retry-After` nếu có.
- 500/502/503/504: có thể retry giới hạn nếu idempotent và còn deadline.
- TCP reset/timeout: không biết remote operation có chạy xong chưa.
- POST create: dùng idempotency key và server-side deduplication khi retry có thể xảy ra.

Đồng thời kiểm tra tầng Apache auto retries, Spring retry, gateway retries và orchestration retries để không tạo retry multiplication. Trong lab Apache automatic retries bị tắt, bảo đảm tests dễ hiểu.

### 8.3. Circuit breaker khác timeout

Timeout chặn một lần chờ quá lâu; circuit breaker tạm giảm calls tới upstream lỗi; bulkhead giới hạn concurrency; rate limiter điều chỉnh tốc độ; retry có thể tăng traffic. Chúng bổ sung nhau, không thay thế. Nếu circuit breaker dùng metrics 503, không coi mọi exception (ví dụ 404) là backend unhealthy.

## 9. Resource lifecycle: ai đóng client và khi nào?

### 9.1. Không new HTTP client cho từng request

Anti-pattern:

```java
@GetMapping("/proxy")
Product wrong() {
    RestClient client = RestClient.builder()
        .baseUrl("https://api.example.test")
        .build();
    return client.get()
        .uri("/product").retrieve().body(Product.class);
}
```

Code minh họa, không độc lập; vấn đề là tạo client/factory liên tục có thể tạo nhiều transports/pools và không có owner đóng, mất reuse, tăng socket churn. Tốt hơn: singleton `RestClient` được inject theo upstream với một shared factory/pool đã quản lý.

### 9.2. Ownership rõ ràng

Với Apache:

```text
Spring ApplicationContext
  └── HttpComponentsClientHttpRequestFactory bean
        └── owns CloseableHttpClient
              └── owns PoolingHttpClientConnectionManager
                    └── socket connections + optional evictor thread

ApplicationContext shutdown
  └── factory.destroy()
        └── closes Apache client / manager / workers
```

Tránh khai báo `CloseableHttpClient` vừa là bean có destroy callback, vừa được factory đóng lần nữa mà không xác định ownership. Trong ví dụ runnable, **factory là owner duy nhất**, chứa Apache client trong method và có `@Bean(destroyMethod="destroy")`.

### 9.3. Response streaming và raw entities

Nếu dùng low-level Apache response:

```java
try (CloseableHttpResponse response =
        apache.execute(new HttpGet(url))) {
    // Đọc entity/body trong scope.
}
```

Đây là snippet, cần imports và `apache` đã tạo. Không trả trực tiếp raw InputStream ra ngoài `try` rồi đọc sau đó, không bỏ response body unconsumed; nếu response không thể tái sử dụng, engine cần được phép hủy connection thay vì giữ leased mãi.

### 9.4. Graceful shutdown và active calls

`server.shutdown=graceful` là cấu hình **inbound** web server; nó không tự bảo đảm mọi outbound pool đã drain. Spring lifecycle phải ngừng nhận việc mới, cho active calls deadline phù hợp rồi đóng pools. Chú ý điều gì xảy ra nếu HTTP clients đang thực hiện request khi bean destroy; integration test shutdown/cancellation phù hợp.

### 9.5. Pool eviction và metrics

Idle eviction/TTL giúp giảm stale sockets và tài nguyên rảnh, nhưng idle policy quá ngắn tăng CPU/TLS handshakes. Giám sát `leased`/`available`/`pending`/`max`, thời gian chờ lease, active caller threads và upstream p95/p99. Một pooled connection còn leased có thể là call dài hợp lệ, không nhất thiết leak.

## 10. Demo chạy được: Spring Boot 3.3.13, Java 17, Apache 5

Demo có **hai mode** trong cùng Spring Boot fat JAR:

- Mode `--mock-upstream`: chạy JDK `com.sun.net.httpserver.HttpServer` trên `127.0.0.1:9090`; endpoint `/fast`, `/slow`, `/missing`, `/unavailable`, `/echo`. Không dùng TLS vì chỉ là localhost lab.
- Mode mặc định: Spring MVC web app trên port 8080, tạo **một** Apache HTTP client pool tường minh, Spring RestClient gọi mock server đồng bộ.
- JUnit: dùng mock server trên ephemeral port thay vì 9090 để tests không phụ thuộc port đang rảnh.

### 10.1. Cây thư mục

```text
http-client-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── HttpClientDemoApplication.java
    │   │   ├── Message.java
    │   │   ├── ClientConfiguration.java
    │   │   ├── UpstreamGateway.java
    │   │   ├── GatewayController.java
    │   │   └── MockUpstreamServer.java
    │   └── resources/application.properties
    └── test/java/example/
        └── UpstreamGatewayTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>http-client-demo</artifactId>
  <version>1.0.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.apache.httpcomponents.client5</groupId>
      <artifactId>httpclient5</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
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
```

Dependency versions do Spring Boot quản lý; không lấy một HttpClient 5 alpha/release khác tự ý để tránh mismatch.

### 10.3. Message.java

```java
package example;
public record Message(String value) {}
```

Record là JSON DTO cho mock response.

### 10.4. ClientConfiguration.java — pool & timeouts

```java
package example;

import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "destroy")
    public HttpComponentsClientHttpRequestFactory pooledRequestFactory() {
        ConnectionConfig connection = ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofSeconds(1))
            .setSocketTimeout(Timeout.ofSeconds(2))
            .setTimeToLive(TimeValue.ofMinutes(3))
            .setValidateAfterInactivity(TimeValue.ofSeconds(5))
            .build();

        PoolingHttpClientConnectionManager manager =
            PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(20)
                .setMaxConnPerRoute(5)
                .setDefaultConnectionConfig(connection)
                .build();

        RequestConfig perRequest = RequestConfig.custom()
            .setConnectionRequestTimeout(
                Timeout.ofMilliseconds(300))
            .setResponseTimeout(Timeout.ofMilliseconds(700))
            .build();

        CloseableHttpClient apache = HttpClients.custom()
            .setConnectionManager(manager)
            .setDefaultRequestConfig(perRequest)
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .disableAutomaticRetries()
            .build();

        return new HttpComponentsClientHttpRequestFactory(apache);
    }

    @Bean
    public RestClient upstreamRestClient(
            RestClient.Builder builder,
            HttpComponentsClientHttpRequestFactory pooledRequestFactory,
            @Value("${demo.upstream-base-url}") String baseUrl) {
        return builder
            .requestFactory(pooledRequestFactory)
            .baseUrl(baseUrl)
            .build();
    }
}
```

Các điểm cốt lõi:

- `setMaxConnTotal(20)` và `setMaxConnPerRoute(5)` giới hạn connections; đây là **lab numbers**, không phải production defaults.
- `ConnectionConfig.setConnectTimeout` khác `RequestConfig.setConnectionRequestTimeout`.
- `RequestConfig.setResponseTimeout` có trong Apache 5 và dùng được với Spring Framework 6.1.
- `setSocketTimeout` áp low-level socket I/O; không coi response timeout là total deadline.
- `evictIdleConnections`/`evictExpiredConnections` cần client lifecycle đúng.
- Factory tạo và **sở hữu** `CloseableHttpClient`; `destroy()` đóng underlying client. Không đăng ký thêm một Apache client Spring Bean rồi close trùng.
- `disableAutomaticRetries()` giúp có **một** retry policy rõ ràng ở app layer nếu sau này cần.
- Không copy các ngưỡng 300/700ms sang production nếu chưa đo traffic/demand và upstream p99.

### 10.5. UpstreamGateway.java

```java
package example;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class UpstreamGateway {
    private final RestClient client;

    public UpstreamGateway(RestClient upstreamRestClient) {
        this.client = upstreamRestClient;
    }

    public Message fast() {
        return client.get()
            .uri("/fast")
            .retrieve()
            .body(Message.class);
    }

    public Message slow(long ms) {
        return client.get()
            .uri(builder -> builder.path("/slow")
                .queryParam("ms", ms).build())
            .retrieve()
            .body(Message.class);
    }

    public Message echo(String requestId) {
        return client.get()
            .uri("/echo")
            .header("X-Request-Id", requestId)
            .retrieve()
            .body(Message.class);
    }

    public void missing() {
        client.get().uri("/missing")
            .retrieve().toBodilessEntity();
    }

    public void unavailable() {
        client.get().uri("/unavailable")
            .retrieve().toBodilessEntity();
    }
}
```

Các method trên đều **synchronous**. `retrieve().toBodilessEntity()` vẫn kiểm tra HTTP status; 404/503 ném exceptions mặc định. Không bắt mọi lỗi thành null vì điều đó sẽ trộn transport error với empty business result.

### 10.6. GatewayController.java

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

@RestController
@RequestMapping("/demo")
public class GatewayController {
    private final UpstreamGateway gateway;

    public GatewayController(UpstreamGateway gateway) {
        this.gateway = gateway;
    }

    @GetMapping("/fast")
    public Message fast() {
        return gateway.fast();
    }

    @GetMapping("/slow")
    public Message slow(@RequestParam(defaultValue = "50") long ms) {
        if (ms < 0 || ms > 5000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms out of range");
        }
        return gateway.slow(ms);
    }

    @GetMapping("/safe-status")
    public ResponseEntity<String> safeStatus() {
        try {
            gateway.unavailable();
            return ResponseEntity.ok("upstream-ok");
        } catch (HttpServerErrorException.ServiceUnavailable ex) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body("upstream-unavailable");
        } catch (ResourceAccessException ex) {
            return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body("upstream-IO-failed");
        }
    }
}
```

Demo mapping upstream 503 thành inbound 502 là một lựa chọn API policy, không phải tất cả 503 bắt buộc thành 502. Mapping ResourceAccessException thành 504 cũng chỉ là đơn giản hóa; connect refused có thể là 502/503. Trong production nên phân biệt root causes và schema lỗi thống nhất, không trả exception details có host/secret.

### 10.7. MockUpstreamServer.java

```java
package example;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

public final class MockUpstreamServer implements AutoCloseable {
    private final HttpServer server;
    private final ExecutorService executor;

    private MockUpstreamServer(
            HttpServer server, ExecutorService executor) {
        this.server = server;
        this.executor = executor;
    }

    public static MockUpstreamServer start(int port)
            throws IOException {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", port), 0);
        ExecutorService workers = Executors.newCachedThreadPool();
        server.setExecutor(workers);

        server.createContext("/fast", exchange ->
            respond(exchange, 200, "{\"value\":\"fast\"}"));

        server.createContext("/slow", exchange -> {
            long ms = parseSleep(exchange.getRequestURI()
                .getRawQuery());
            try {
                Thread.sleep(ms);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
                return;
            }
            respond(exchange, 200, "{\"value\":\"slow\"}");
        });

        server.createContext("/missing", exchange ->
            respond(exchange, 404, "{\"error\":\"missing\"}"));

        server.createContext("/unavailable", exchange ->
            respond(exchange, 503,
                "{\"error\":\"unavailable\"}"));

        server.createContext("/echo", exchange -> {
            String candidate = exchange.getRequestHeaders()
                .getFirst("X-Request-Id");
            String safe = candidate != null &&
                candidate.matches("[A-Za-z0-9._-]{1,64}")
                    ? candidate : "invalid";
            respond(exchange, 200,
                "{\"value\":\"" + safe + "\"}");
        });

        server.start();
        return new MockUpstreamServer(server, workers);
    }

    private static long parseSleep(String query) {
        if (query == null) return 0L;
        for (String part : query.split("&")) {
            if (part.startsWith("ms=")) {
                try {
                    long ms = Long.parseLong(part.substring(3));
                    return Math.max(0, Math.min(ms, 5000));
                } catch (NumberFormatException ignored) {
                    return 0L;
                }
            }
        }
        return 0L;
    }

    private static void respond(
            HttpExchange exchange, int status, String json)
            throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.getResponseHeaders().add(
                "Content-Type", "application/json; charset=UTF-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    public int port() {
        return server.getAddress().getPort();
    }

    @Override
    public void close() {
        server.stop(0);
        executor.shutdownNow();
    }

    public static void main(String[] args) throws Exception {
        try (MockUpstreamServer mock = start(9090)) {
            System.out.println(
                "Mock upstream: http://127.0.0.1:9090");
            new CountDownLatch(1).await();
        }
    }
}
```

Mock sử dụng class Java17 `com.sun.net.httpserver.HttpServer` từ JDK module `jdk.httpserver`. `Thread.sleep` ở mock cố tình tạo response chậm, **không phải** pattern tốt cho app sản xuất. Nhờ `start(0)`, tests lấy ephemeral port nên tránh conflict giữa CI workers.

### 10.8. HttpClientDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpClientDemoApplication {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 &&
                "--mock-upstream".equals(args[0])) {
            MockUpstreamServer.main(new String[0]);
            return;
        }
        SpringApplication.run(HttpClientDemoApplication.class, args);
    }
}
```

Mode mock **không khởi động Spring application**, chỉ phục vụ upstream API trên 9090. Mode thường khởi động MVC app trên 8080. Đây là hai processes độc lập, tránh HTTP self-call làm khó quan sát thread contention.

### 10.9. application.properties

```properties
server.port=8080
demo.upstream-base-url=http://127.0.0.1:9090
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Production phải thay loopback HTTP bằng HTTPS host đã được allowlist, trust config và credential policy. Đừng cung cấp endpoint proxy nhận một arbitrary URL từ client rồi cho RestClient truy cập được internal metadata endpoints (SSRF).

### 10.10. Build và chạy

Với JDK 17+, Maven, từ thư mục có `pom.xml`:

```bash
mvn clean package

# Terminal 1 - mock server
java -jar target/http-client-demo-1.0.0.jar --mock-upstream

# Terminal 2 - Spring MVC web server
java -jar target/http-client-demo-1.0.0.jar
```

Sau đó chạy:

```bash
curl -i http://localhost:8080/demo/fast
curl -i "http://localhost:8080/demo/slow?ms=50"
curl -i http://localhost:8080/demo/safe-status
curl -i "http://localhost:8080/demo/slow?ms=-1"
```

Kỳ vọng:

| Request | HTTP kết quả |
| --- | --- |
| `/demo/fast` | 200, JSON `{"value":"fast"}` |
| `/demo/slow?ms=50` | 200, JSON `{"value":"slow"}` |
| `/demo/safe-status` | 502, text `upstream-unavailable` |
| `/demo/slow?ms=-1` | 400, lỗi query invalid |
| `/demo/slow?ms=1800` | Có thể ném ResourceAccessException do response timeout; inbound default error handling tùy Boot |

Không assert raw stacktrace/error JSON chưa được cấu hình. Các timeouts nêu trên là lab values và chạy trên OS/CI tải cao có thể thay đổi thời gian thực tế.

## 11. Tests JUnit 5: HTTP status, timeout và reuse client

File `src/test/java/example/UpstreamGatewayTest.java`:

```java
package example;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;

class UpstreamGatewayTest {
    private MockUpstreamServer mock;
    private HttpComponentsClientHttpRequestFactory factory;
    private UpstreamGateway gateway;

    @BeforeEach
    void startMock() throws Exception {
        mock = MockUpstreamServer.start(0);
        factory = new ClientConfiguration().pooledRequestFactory();
        RestClient client = RestClient.builder()
            .baseUrl("http://127.0.0.1:" + mock.port())
            .requestFactory(factory)
            .build();
        gateway = new UpstreamGateway(client);
    }

    @AfterEach
    void closeAll() throws Exception {
        if (factory != null) factory.destroy();
        if (mock != null) mock.close();
    }

    @Test
    void fastJsonIsDecoded() {
        Message result = gateway.fast();
        assertNotNull(result);
        assertEquals("fast", result.value());
    }

    @Test
    void sameClientCanBeUsedRepeatedly() {
        for (int i = 0; i < 5; i++) {
            assertEquals("fast", gateway.fast().value());
        }
    }

    @Test
    void shortDelayStillSucceeds() {
        assertEquals("slow", gateway.slow(10).value());
    }

    @Test
    void slowResponseTriggersTransportTimeout() {
        assertThrows(ResourceAccessException.class,
            () -> gateway.slow(1800));
    }

    @Test
    void http404IsNotAnIoTimeout() {
        assertThrows(HttpClientErrorException.NotFound.class,
            gateway::missing);
    }

    @Test
    void http503IsAStatusError() {
        assertThrows(
            HttpServerErrorException.ServiceUnavailable.class,
            gateway::unavailable);
    }

    @Test
    void safeHeaderReachesUpstream() {
        assertEquals("req-001",
            gateway.echo("req-001").value());
    }

    @Test
    void mockRejectsUnexpectedHeaderValue() {
        assertEquals("invalid",
            gateway.echo("unsafe whitespace").value());
    }
}
```

**8 JUnit methods** kiểm tra JSON, reuse cùng client object, slow response timeout, status 404/503 và header forwarding. Tests dùng ephemeral port, không cần Internet. Chúng **không chứng minh** một TCP connection vật lý đã được reuse mỗi lần; chứng minh client/factory object được reuse và request processing hoạt động qua nhiều calls. Muốn test socket reuse thật phải quan sát remote socket/session/connection stats.

### 11.1. Kiểm thử pool acquisition cần test khác

Với pool 20/5 ở demo, hai HTTP calls không làm pool lease bão hòa. Test đúng cần pool max=1, giữ một slow response đang lease socket, để call thứ hai chờ lâu hơn lease timeout và assert pending/acquire error. Nếu chỉ dùng `gateway.slow(1800)`, bạn đang kiểm tra **response timeout**, không phải acquisition timeout.

### 11.2. Chưa được test TLS

Mock server là `http://127.0.0.1`, không dùng HTTPS. Vì vậy 8 tests **không** validate PKIX, hostname, mTLS hoặc ALPN. TLS cần môi trường HTTPS test với local CA/cert hợp lệ, hostname SAN khớp, client truststore/keystore được quản lý; cũng cần negative tests expired/untrusted/wrong-host cert. Không tự tuyên bố “TLS PASS” chỉ vì HTTP tests chạy.

### 11.3. Mã đã được soạn nhưng không khẳng định đã chạy

Các lệnh `mvn test` và `mvn clean package` ở đây dành cho người học. Chỉ công bố Maven tests PASS khi có output Maven thực tế. Nếu test timeout flaky dưới CI cực tải, điều chỉnh mock timing trong test setup/test-specific request policy thay vì bỏ timeout validation.

## 12. Connection pool sizing và tải hệ thống

Một quan hệ định lượng thường dùng là Little's Law:

`in_flight ≈ requests_per_second × average_latency_seconds`

Ví dụ upstream nhận 100 calls/s, trung bình 0,2s → khoảng **20 in-flight calls** trong steady state. Nhưng p99 spikes, retries và bursts có thể làm concurrency peak cao hơn. Không lấy 20 làm maxConn mặc định nếu backend chỉ cho phép 8 concurrent requests; sizing phải tôn trọng quotas.

### 12.1. Quá ít connections

Pool lease pending tăng, caller thread chờ, dù upstream khỏe. Cần kiểm tra active/leased/pending metrics, backend response latency và queue. Có thể cải thiện bằng giảm traffic, cache, giới hạn concurrency hoặc tăng pool **sau khi** downstream chấp nhận được.

### 12.2. Quá nhiều connections

Số instance × maxConnPerRoute tạo cluster-wide possible connections. Ví dụ 20 JVMs × 100 per route = 2000 potential sockets tới cùng host. Cần quan tâm FD limits, SNAT ephemeral ports, TLS sessions, proxy/LB connection quotas, remote CPU và rate limits.

### 12.3. Idle, TTL và stale

- **Idle:** thời gian connection không được sử dụng.
- **TTL:** tuổi tối đa connection.
- **Server keep-alive timeout:** server có thể đóng pooled connection trong lúc idle.
- **Validate after inactivity:** giảm dùng lại socket đã stale.
- **Evict idle/expired:** dọn sockets nhưng có thể tăng connect/TLS khi cần lại.

Chọn idle eviction phù hợp proxy/server behavior, quan sát stale retry rates. Không đặt tất cả thành 0 hoặc cực thấp chỉ để “an toàn”.

### 12.4. Pool metric và thread dump

Nếu worker threads đều blocked ở `leaseConnection`, đó khác vấn đề block ở socket read. Thread dump kết hợp Apache connection manager pool stats, Spring HTTP client metrics và downstream server p99 giúp phân biệt. Một leased connection không tự là leak: nếu server stream dài hoặc client tải dữ liệu lớn thì trạng thái leased có thể đúng.

## 13. Error handling và bảo mật trong hệ thống production

### 13.1. Network failure vs HTTP response

- HTTP 404/429/503: **đã có HTTP status** từ server/gateway.
- `ResourceAccessException`: I/O layer có thể chưa nhận HTTP response; root cause có thể là timeout, refused, DNS, SSL hoặc pool acquisition.
- JSON parse/converter error: upstream body không phù hợp DTO, dù status 200.
- Client cancellation/interruption: không đảm bảo remote operation bị rollback.

Tầng gateway/service nên phân loại errors thành business not-found, validation, transient, policy violation và unexpected; không chuyển mọi exception thành 404 hoặc 504.

### 13.2. Retry budget

Đặt max attempts (ví dụ 2), jitter, exponential backoff, deadline và circuit breaker. Nếu server trả `Retry-After` cần xử lý theo contract. Tránh retry multiplication giữa Apache HttpClient, framework resilience library, reverse proxy và message broker consumer. Với POST/PUT/PATCH, xác định idempotency theo nghiệp vụ/HTTP semantics; không retry mù quáng.

### 13.3. SSRF và redirect

Không tạo request từ URL tùy ý do client gửi; kẻ tấn công có thể yêu cầu gọi localhost, metadata endpoints hoặc private networks. Dùng cố định base URL, validate scheme/host/port, kiểm soát DNS resolution, redirect hosts và outbound egress policies. Tắt follow redirects khi cần hạn chế destinations; nếu theo redirect cần loại bỏ sensitive headers khi đổi origin.

### 13.4. Không lộ secrets

Không log `Authorization`, client keystore password, private keys, toàn response body PII, hay SSL debug traces chứa dữ liệu nhạy cảm. Với custom truststore/keystore, lưu passwords bằng secret management, phân quyền filesystem và rotation. Không commit `.p12` chứa private key hoặc đặt password thật vào sample.

### 13.5. HTTP client đồng bộ trong reactive handler

Đừng gọi RestClient blocking trực tiếp trong Netty event-loop của WebFlux. Dùng WebClient + reactive driver nếu cần reactive end-to-end hoặc cô lập blocking call qua bounded worker pool có queue/timeout limits rõ; `Mono.just(restClient.get()...)` vẫn chạy blocking **trước** Mono assembly.

## 14. Troubleshooting theo triệu chứng

| Triệu chứng | Chẩn đoán ưu tiên |
| --- | --- |
| 700ms timeout nhưng call kéo dài hơn 1s | Lease/DNS/connect/TLS/response/body là các giai đoạn khác nhau |
| 100 inbound requests, chỉ 5 outbound chạy | Max per-route = 5, pending acquire |
| Timeout dù upstream không nhận request | Lease/connection acquisition timeout |
| `Connection refused` | Listener/firewall/host:port, không phải HTTP 404 |
| `UnknownHostException` | DNS/resolver/network |
| `PKIX path building failed` | CA/cert chain/truststore |
| Hostname mismatch | URL host không khớp certificate SAN |
| Local HTTPS tốt, production fail | Proxy, TLS version, truststore, cert rotation |
| POST timeout nhưng có hai records | Automatic retry/duplicate write |
| Pool leased count không giảm | Slow response, unconsumed body hoặc resource leak |
| JVM không exit khi app shutdown | Pool/client/evictor/executor chưa đóng |
| JDK 17 compile error với HttpClient.close | Method này không có trên Java 17 |
| Spring 6.1 compile error Apache setReadTimeout | Method này chỉ được thêm ở 6.2 |
| Browser nhận 504 nhưng remote có 200 | Gateway timeout xảy ra trước response đến |
| CPU thấp nhưng p99 cao | Blocking waits/pool queue/downstream latency |
| Too many open files | Sockets/pools/FDS chưa giới hạn |
| TLS trust-all khiến kết nối “hoạt động” | Security verification đã bị vô hiệu hóa |

## 15. Checklist production

1. [ ] Biết HTTP engine/factory thực, không dựa vào defaults ngẫu nhiên.
2. [ ] Chỉ rõ maxConnTotal, maxConnPerRoute theo downstream capacity.
3. [ ] Có pool acquire timeout, connect timeout, response timeout và whole-call deadline.
4. [ ] DNS, proxy CONNECT, TLS handshake được tính riêng trong SLA.
5. [ ] HTTP client/factory/pool là shared beans được khởi tạo một lần.
6. [ ] Connection có TTL/idle eviction/stale validation hợp lý.
7. [ ] Response body/low-level InputStream luôn consume/close đúng.
8. [ ] Close/dispose pool/evictor đúng lúc app shutdown.
9. [ ] Có bulkhead/rate limit cho số synchronous calls đồng thời.
10. [ ] Có chính sách retry rõ, deadline và idempotency key cho writes.
11. [ ] HTTP status errors không bị nhầm với network transport exceptions.
12. [ ] TLS CA trust, SAN hostname verification và mTLS (nếu yêu cầu) được kiểm thử.
13. [ ] Không dùng trust-all, NoopHostnameVerifier, disableHostnameVerification.
14. [ ] Secrets/truststores/keystores được lưu và rotate an toàn.
15. [ ] Base URL/redirect/egress hạn chế SSRF.
16. [ ] Pool leased/pending/available và p95/p99 latency có metric.
17. [ ] Cluster-wide connection budget được tính theo số instances.
18. [ ] Test 404/429/503, timeout, pool exhaustion, untrusted/wrong-host cert.
19. [ ] Test graceful shutdown và active outbound calls.
20. [ ] Khi upgrade Java/Spring/Apache, kiểm tra API và default semantics.
21. [ ] Trong WebFlux event-loop, không chạy RestClient blocking trực tiếp.
22. [ ] Benchmark gồm cold/warm connections và TLS/proxy thực tế.

## 16. Câu hỏi ôn tập và đáp án

**1.** TCP connect timeout có đảm bảo response nhanh không?  
**Đáp án:** Không; response/read timeout là giai đoạn khác.

**2.** Lease timeout là gì?  
**Đáp án:** Chờ connection từ pool, có thể fail trước khi HTTP request ra mạng.

**3.** Pool total khác per-route?  
**Đáp án:** Total giới hạn mọi connection; per-route giới hạn mỗi target route.

**4.** Vì sao RestClient thường nên được reuse?  
**Đáp án:** Reuse request factory/pool, quản lý TLS/timeouts/lifecycle nhất quán.

**5.** RestTemplate có dùng pool Apache được không?  
**Đáp án:** Có qua HttpComponentsClientHttpRequestFactory.

**6.** Spring 6.1 HttpComponents factory có setReadTimeout(Duration) chưa?  
**Đáp án:** Chưa; API được thêm từ Spring 6.2.

**7.** Spring 6.1 JdkClientHttpRequestFactory có setReadTimeout(Duration) không?  
**Đáp án:** Có.

**8.** Java 17 HttpClient có close() như Java 21 không?  
**Đáp án:** Không, Java 21 bổ sung public lifecycle APIs.

**9.** Connection idle và TTL khác gì?  
**Đáp án:** Idle đo lúc không dùng; TTL đo tuổi tối đa từ khi tạo.

**10.** HTTP keep-alive giảm chi phí gì?  
**Đáp án:** Giảm tạo TCP/TLS connection mới qua reuse.

**11.** Một response stream chưa đóng ảnh hưởng pool ra sao?  
**Đáp án:** Connection có thể còn leased/không reusable.

**12.** 204 có đảm bảo body DTO không null không?  
**Đáp án:** Không; 204 không có body.

**13.** HTTP 404 khác TCP connection refused?  
**Đáp án:** 404 là HTTP response, refused là TCP failure.

**14.** Timeout sau POST có chứng minh server không lưu record?  
**Đáp án:** Không, server có thể đã commit.

**15.** Vì sao cần idempotency key cho retry POST?  
**Đáp án:** Tránh tạo resource trùng khi response của lần trước bị mất.

**16.** PKIX path building failed nên sửa thế nào?  
**Đáp án:** Kiểm tra CA/intermediates/truststore, không trust-all.

**17.** Hostname verification làm gì?  
**Đáp án:** Kiểm tra SAN certificate có khớp URL host.

**18.** Truststore và client keystore có giống nhau không?  
**Đáp án:** Không; truststore để xác thực server, keystore private key để client auth/mTLS.

**19.** TLS mTLS tự thay authorization của business không?  
**Đáp án:** Không; vẫn cần mapping identity/permissions.

**20.** Tăng pool vô hạn có tốt không?  
**Đáp án:** Không; có thể làm upstream quá tải, cạn sockets/FDS.

**21.** Response timeout 700ms là total-call deadline 700ms chứ?  
**Đáp án:** Không, còn các stages khác và body semantics.

**22.** Timeout khi chờ pool có thể xảy ra dù upstream khỏe?  
**Đáp án:** Có, khi pool tất cả connections đang leased.

**23.** Vì sao Java 17 JDK HttpClient khó kiểm soát pool hơn Apache 5?  
**Đáp án:** Không có cùng public per-route pool limit/metrics/close APIs.

**24.** Khi Spring Boot shutdown, chỉ cần server.shutdown=graceful là Apache client đã đóng đúng?  
**Đáp án:** Không; cần bean lifecycle/destroy của outbound pool.

**25.** Nếu REST client gọi trong WebFlux event-loop sẽ sao?  
**Đáp án:** Có thể chặn event-loop, làm giảm concurrency; dùng WebClient hoặc bounded bridge.

**26.** Test gateway.slow(1800) với 700ms response timeout chứng minh pool lease limit không?  
**Đáp án:** Không; test đó chỉ chứng minh response timeout.

**27.** TLS handshake có thể ảnh hưởng p99 dù request body rất nhỏ không?  
**Đáp án:** Có, đặc biệt cold connections/certificate negotiation.

**28.** Client theo redirect sang host khác cần chú ý gì?  
**Đáp án:** SSRF/Authorization header leak và trust boundary.

**29.** Apache HttpClient automatic retries có nên bật mọi khi không?  
**Đáp án:** Không; phải xét idempotency, deadline và các retry layers khác.

**30.** Đo gì đầu tiên khi leased=max và pending tăng?  
**Đáp án:** Pool stats, upstream latency, body closes và caller concurrency.

## 17. Nguồn tham khảo

- [Spring Framework 6.1 — Rest Clients](https://docs.spring.io/spring-framework/reference/6.1/integration/rest-clients.html): RestClient/RestTemplate và transport adapters.
- [Spring 6.1 JdkClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/http/client/JdkClientHttpRequestFactory.html): read timeout và JDK bridge.
- [Spring 6.1 HttpComponentsClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): connect/lease timeout và lifecycle.
- [Spring 6.2 HttpComponentsClientHttpRequestFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html): read timeout API được thêm trong 6.2.
- [Apache HttpClient 5.2 ConnectionConfig API](https://javadoc.io/static/org.apache.httpcomponents.client5/httpclient5/5.2.1/org/apache/hc/client5/http/config/ConnectionConfig.Builder.html): connect/socket timeout, TTL, idle validation.
- [Apache HttpClient 5 Pooling Manager API](https://hc.apache.org/components/httpcomponents-client-5.4.x/5.4.4/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManagerBuilder.html): total/per-route pool limits.
- [Java 17 HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): send/sendAsync, connectTimeout, SSLContext.
- [Java 21 HttpClient API](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html): new public lifecycle methods.
- [Java 17 HttpExchange Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): local test server lifecycle.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): injected RestClient.Builder.
- [Java Secure Socket Extension](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): trust managers, key managers, TLS.
- [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status, methods, idempotency.
- [RFC 8446 TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS handshake.

**Kết luận:** HTTP client đồng bộ chỉ đáng tin khi **connect, lease, response và whole-call deadlines được phân biệt**, connection pool có limits/metrics và lifecycle rõ, TLS chain cùng hostname luôn được xác minh, response streams được đóng và retries có idempotency. Chọn request factory theo Spring/JDK/Apache **phiên bản thực**, không copy một phương thức chưa tồn tại hoặc mặc định rằng mọi HTTP client có pool giống nhau.
