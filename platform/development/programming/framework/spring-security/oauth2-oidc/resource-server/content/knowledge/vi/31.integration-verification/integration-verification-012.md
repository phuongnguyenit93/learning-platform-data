# Lỗi mạng, timeout và kiểm chứng không có đường đi bỏ qua xác minh

Một **Spring Security OAuth 2.0/OIDC Resource Server** thường phụ thuộc vào dịch vụ identity bên ngoài để xác minh access token. Với JWT, Resource Server có thể cần tải public key từ JWKS endpoint; với opaque token, nó cần gọi token introspection endpoint. Hai đường đi này có thể gặp DNS failure, TLS handshake failure, connection refusal, timeout, HTTP 5xx, response không hợp lệ hoặc dịch vụ identity tạm thời không khả dụng.

Integration test phải chứng minh hai điều:

1. Khi dependency xác minh token gặp lỗi, API xử lý request theo một chính sách lỗi có giới hạn thời gian và **không chấp nhận token chưa xác minh**.
2. Không có fallback âm thầm nào biến lỗi mạng thành Authentication thành công, principal giả, anonymous access được phép hoặc kết quả “token hợp lệ”.

Không nên đánh đồng token không hợp lệ với hệ thống xác minh đang gặp sự cố. **active=false**, chữ ký sai, issuer/audience sai là kết quả xác thực thất bại. Timeout hoặc AS/JWKS endpoint không truy cập được là lỗi hạ tầng. Cả hai đều không được cấp quyền; cách ánh xạ HTTP status và khả năng retry cần được thiết kế rõ.

> **Nguyên tắc:** không thể xác minh thì không được cấp Authentication. Một lỗi mạng không phải bằng chứng token hợp lệ.

## 1. Hai đường xác minh và các điểm có thể lỗi

### 1.1. JWT: xác minh chữ ký bằng JWKS

JWT access token thường được xác minh cục bộ sau khi Resource Server có public key phù hợp. Nếu cấu hình bằng issuer discovery/JWK Set URI, Spring Security/Nimbus có thể phải gọi identity provider để lấy metadata hoặc JWKS:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as JWT Resource Server
    participant JWKS as Issuer JWKS endpoint
    C->>RS: Authorization: Bearer signed-JWT
    RS->>RS: Parse protected header (kid, alg)
    RS->>RS: Find trusted key in JWKS cache
    alt Key is not cached / refresh required
        RS->>JWKS: GET configured JWKS URI
        JWKS-->>RS: JWK Set
    end
    RS->>RS: Verify signature
    RS->>RS: Validate iss, aud, exp, nbf, typ
    RS-->>C: Resource response or authentication failure
~~~

Một điểm quan trọng khi viết test: **JWKS cache có thể khiến request vẫn xác minh được dù JWKS endpoint đang offline**. Nếu key cần thiết đã có trong cache, decoder có thể tiếp tục xác minh chữ ký cục bộ. Muốn kiểm tra lỗi lấy key, phải dùng decoder/cache mới hoặc token có kid chưa có trong cache, đồng thời kiểm soát response JWKS endpoint.

Nếu ứng dụng dùng một public key tĩnh được cấu hình trực tiếp, việc xác minh request không cần gọi JWKS mỗi lần. Khi đó test network timeout của JWKS không áp dụng cho request path đó; hãy test đúng dependency mà cấu hình production thực sự sử dụng.

### 1.2. Opaque token: gọi introspection endpoint

Opaque token không mang claims mà Resource Server tự xác minh bằng chữ ký. Resource Server gửi token tới AS theo RFC 7662:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Opaque Resource Server
    participant AS as Introspection endpoint
    C->>RS: Authorization: Bearer opaque-token
    RS->>AS: POST /introspect (token + client authentication)
    alt AS responds active=true
        AS-->>RS: active=true + claims/scope
        RS->>RS: Build authenticated principal
        RS-->>C: Resource response
    else AS responds active=false
        AS-->>RS: active=false
        RS-->>C: Authentication failure
    else Network / timeout / server error
        AS--xRS: No usable introspection response
        RS-->>C: Fail closed (401 or service error by API policy)
    end
~~~

Introspection là một lời gọi mạng trong authentication flow, trừ khi ứng dụng có cache introspection. Vì vậy, latency và availability của AS ảnh hưởng trực tiếp đến khả năng xác thực opaque token.

### 1.3. Bảng phân loại lỗi

| Sự kiện | Ý nghĩa | Không được làm |
|---|---|---|
| **active=false** | AS đã trả lời token inactive | Tạo principal authenticated |
| JWT signature sai | Token không được ký bởi key tin cậy hoặc đã bị sửa | Bỏ qua signature rồi đọc claims |
| Issuer/audience/type sai | Token không dành cho trust contract/API này | Chấp nhận vì chữ ký đúng |
| DNS/connect/TLS failure | Không kết nối được dependency xác minh | Coi lỗi kết nối như active=true |
| Read/response timeout | Không nhận được kết quả trong deadline | Chờ vô hạn hoặc cho request đi qua |
| HTTP 5xx từ AS/JWKS | Dependency xác minh đang lỗi | Trả principal mặc định |
| Response malformed/không parse được | Không có kết quả xác minh đáng tin | Chấp nhận dựa trên một phần response |
| Circuit breaker open | Dependency đang bị cách ly do lỗi liên tiếp | Dùng fallback trả về token hợp lệ |
| Cache miss khi AS offline | Không có kết quả xác minh mới | Bỏ qua introspection/JWKS validation |

## 2. Authentication failure khác với identity-provider outage

API cần phân biệt hai nhóm kết quả.

**Credential không hợp lệ:** token sai chữ ký, sai issuer, sai audience, hết hạn, sai loại hoặc introspection trả active=false. Resource Server phải từ chối Authentication. Với Bearer API, phản hồi thường là HTTP 401 và có thể có header WWW-Authenticate: Bearer.

**Không thể xác minh do hạ tầng:** AS/JWKS endpoint timeout, DNS lỗi, TLS lỗi hoặc trả 5xx. Resource Server cũng không được cấp Authentication. Tuy nhiên, đây là lỗi dịch vụ xác minh chứ không phải kết luận token của client chắc chắn sai.

Về HTTP response:

- Một số cấu hình mặc định của Bearer authentication entry point có thể ánh xạ lỗi xác thực thành 401.
- API có thể chọn ánh xạ lỗi hạ tầng xác minh thành 503 Service Unavailable để client phân biệt “credential không hợp lệ” với “dịch vụ xác minh tạm thời không sẵn sàng”.
- Nếu cần phân biệt, hãy cấu hình failure handling/entry point rõ ràng cho Servlet hoặc ServerAuthenticationEntryPoint cho WebFlux. Không giả định mọi exception của thư viện sẽ tự động thành 503.
- Dù trả 401 hay 503, request được bảo vệ phải bị chặn. Không trả 2xx hoặc tạo principal authenticated khi không có kết quả xác minh.

Không đưa chi tiết URL nội bộ, response body của AS, client secret, token hoặc stack trace vào response cho caller. Log nội bộ nên ghi loại lỗi, dependency, correlation ID và thời gian xử lý; không ghi raw access token.

## 3. Timeout phải có giới hạn ở tầng HTTP client

Chỉ đặt timeout ở một lớp không phải lúc nào cũng đủ. Nên có:

1. **Connection timeout:** giới hạn thời gian thiết lập kết nối.
2. **Read/response timeout:** giới hạn thời gian chờ dữ liệu trả về.
3. **Overall deadline:** giới hạn tổng thời gian cho toàn bộ bước xác minh, kể cả retry.
4. **Bounded retry:** nếu có retry, giới hạn số lần và chỉ áp dụng cho lỗi transient phù hợp.

Ví dụ minh họa:

~~~text
connect timeout: 1 second
response/read timeout: 2 seconds
overall authentication dependency budget: 3 seconds
retry: at most one attempt for selected transient failures
~~~

Các con số trên chỉ để minh họa. Chọn giá trị theo latency/SLA của identity provider, thời gian xử lý request và ngân sách end-to-end của API.

### 3.1. Vì sao không chờ vô hạn?

Nếu AS không trả lời, thread/request có thể bị giữ lâu, connection pool cạn, queue tăng và nhiều request khác bị ảnh hưởng. Với WebFlux, blocking call trên event loop còn có thể làm nghẽn nhiều request cùng lúc. Deadline hữu hạn giúp hệ thống giải phóng tài nguyên và trả kết quả lỗi có kiểm soát.

### 3.2. Retry không thay timeout

Retry 3 lần với mỗi lần chờ 10 giây vẫn có thể giữ request rất lâu. Tổng deadline phải bao gồm cả retry và backoff. Không retry mọi lỗi:

- Không retry token sai chữ ký, active=false, issuer/audience/type sai.
- Có thể retry giới hạn với lỗi kết nối hoặc 5xx transient nếu policy cho phép.
- Không retry liên tục khi circuit breaker đã mở.
- Không vượt qua overall deadline của request.

Introspection thường là POST nhưng về mục đích là truy vấn trạng thái token. Nếu retry, phải cân nhắc tải AS, idempotency theo contract, số lần gọi và khả năng token state thay đổi giữa hai lần. Không retry mù quáng tất cả exception.

## 4. Cấu hình timeout cho Servlet Resource Server

Với Servlet stack, NimbusJwtDecoder và NimbusOpaqueTokenIntrospector có thể dùng một RestOperations được cấu hình timeout. Ví dụ dùng RestTemplate và SimpleClientHttpRequestFactory:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestOperations;
import org.springframework.web.client.RestTemplate;

@Configuration
class IdentityHttpClientConfiguration {

    @Bean
    RestOperations identityRestOperations() {
        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(1_000);
        requestFactory.setReadTimeout(2_000);
        return new RestTemplate(requestFactory);
    }
}
~~~

Áp dụng cho JWT JWKS retrieval:

~~~java
@Bean
JwtDecoder jwtDecoder(RestOperations identityRestOperations) {
    return NimbusJwtDecoder
        .withJwkSetUri("https://identity.example.com/.well-known/jwks.json")
        .restOperations(identityRestOperations)
        .build();
}
~~~

Áp dụng cho opaque-token introspection:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        RestOperations identityRestOperations) {

    NimbusOpaqueTokenIntrospector introspector =
        new NimbusOpaqueTokenIntrospector(
            "https://identity.example.com/oauth2/introspect",
            "orders-resource-server",
            identityClientSecret);

    introspector.setRestOperations(identityRestOperations);
    return introspector;
}
~~~

Trong production, lấy identityClientSecret từ secret manager hoặc cấu hình được bảo vệ. Ví dụ chỉ thể hiện cách gắn timeout-configured RestOperations vào introspector. Nếu decoder dùng public key tĩnh thay vì JWKS URI, không có JWKS HTTP request trong đường xác minh.

**Lưu ý phiên bản:** API builder/setter có thể thay đổi giữa các dòng Spring Security/Spring Framework. Hãy kiểm tra đúng Javadoc của version được quản lý bởi Spring Boot BOM. Điều cần giữ là HTTP client thực sự được dùng cho JWKS/introspection có connect/read timeout hữu hạn; chỉ khai báo một bean timeout nhưng không gắn bean đó vào decoder/introspector thì không có tác dụng.

## 5. Timeout cho WebFlux Resource Server

WebFlux nên dùng HTTP client non-blocking. Với Reactor Netty, có thể cấu hình connect timeout và response timeout cho WebClient:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

WebClient identityWebClient() {
    HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2));

    return WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
}
~~~

Với reactive JWT decoder, truyền WebClient đã cấu hình vào builder của NimbusReactiveJwtDecoder theo API version đang dùng:

~~~java
ReactiveJwtDecoder reactiveJwtDecoder(WebClient identityWebClient) {
    return NimbusReactiveJwtDecoder
        .withJwkSetUri(trustedJwkSetUri)
        .webClient(identityWebClient)
        .build();
}
~~~

Với reactive opaque introspection, dùng ReactiveOpaqueTokenIntrospector/NimbusReactiveOpaqueTokenIntrospector được cấu hình với HTTP client có timeout. Có thể bọc thêm một deadline ở reactive boundary:

~~~java
ReactiveOpaqueTokenIntrospector boundedIntrospector(
        ReactiveOpaqueTokenIntrospector delegate) {
    return token -> delegate.introspect(token)
        .timeout(Duration.ofSeconds(3));
}
~~~

Mono.timeout đặt deadline cho publisher và phát lỗi timeout khi hết thời gian. Nó không thay thế connect/response timeout của HTTP connector; cần cấu hình cả tầng network để giải phóng socket/connection phù hợp.

Không dùng block() trong reactive authentication flow để gọi AS/JWKS. Không chạy RestTemplate blocking trên Netty event loop. Nếu phải tích hợp thư viện blocking, cô lập trên bounded scheduler hoặc chọn reactive client/implementation phù hợp; ưu tiên đường xác minh non-blocking.

**Lưu ý phiên bản:** constructor và cách truyền WebClient vào reactive decoder/introspector khác nhau theo version. Xác nhận builder/constructor có trong Spring Security BOM của dự án. Không tự tạo WebClient có timeout rồi bỏ quên không truyền nó vào implementation thực tế.

## 6. Cache, key rotation và hành vi khi dependency offline

### 6.1. JWT JWKS cache

JWT verification có thể tiếp tục hoạt động khi JWKS endpoint offline nếu public key cần thiết đã được tải và còn trong cache theo chính sách của decoder. Điều này không phải bypass: chữ ký vẫn được xác minh bằng key đã nhận từ JWKS tin cậy trước đó.

Các trường hợp khác nhau:

| Trạng thái key | JWKS endpoint | Kết quả có thể xảy ra |
|---|---|---|
Key hợp lệ đã cache | Offline | Decoder có thể tiếp tục verify bằng key cache |
kid mới chưa cache | Online | Decoder có thể refresh JWKS và tìm key |
kid mới chưa cache | Offline/timeout | Không lấy được key; authentication thất bại |
Key đã bị loại khỏi JWKS | Online sau refresh | Decoder có thể không còn xác minh được token dùng key đó |
Unknown kid | Online nhưng không có key | Authentication thất bại |

Không viết test “JWKS offline luôn phải 401” nếu key đã cache và implementation được phép dùng cache. Hãy tách test cache hit khỏi test cold-cache/unknown-key. Cần xác định rõ key cache lifetime và rotation policy của thư viện/ứng dụng.

### 6.2. Opaque introspection cache

Nếu ứng dụng cache kết quả introspection, cache có thể cho phép token đã xác minh trước đó tiếp tục được chấp nhận trong một khoảng thời gian khi AS offline. Đó là một quyết định availability/revocation-latency có chủ đích, không phải lý do để chấp nhận token chưa từng được introspect.

Cache policy nên quy định:

- Chỉ cache response đã parse và xác thực thành công theo contract.
- Không cache exception, timeout, 5xx hoặc response malformed thành kết quả active.
- TTL không vượt quá thời gian còn lại của token nếu response có expiry đáng tin cậy.
- TTL phải nằm trong SLA thu hồi token: cache dài làm revoke propagation chậm.
- Xác định cách xử lý active=false; không chuyển nó thành active do cache fallback.
- Key cache phải gắn với token một cách an toàn; tránh log raw token hoặc dùng key dễ lộ credential.

### 6.3. Không nhầm stale cache với fail-open

Nếu policy cho phép dùng **một kết quả active đã được xác minh và còn trong TTL**, request có thể được chấp nhận dù AS hiện đang offline. Nếu cache miss hoặc TTL hết, request phải đi qua introspection; khi không thể xác minh thì từ chối. Đừng tạo cache fallback kiểu “không hỏi được AS thì coi token active”.

## 7. Fail closed và các đường bypass nguy hiểm

### 7.1. Fail closed nghĩa là gì?

Fail closed không nhất thiết có nghĩa mọi lỗi phải trả cùng HTTP status. Nó có nghĩa:

- Không tạo authenticated principal nếu không có kết quả xác minh đáng tin.
- Không chuyển lỗi mạng thành active=true.
- Không bỏ qua validator khi decoder/introspector lỗi.
- Không chuyển request được bảo vệ thành anonymous request rồi cho phép đi tiếp.
- Không dùng key/issuer fallback tùy ý khi JWKS không truy cập được.
- Không trả quyền mặc định rộng khi authorities không được tạo.

### 7.2. Anti-pattern: catch lỗi rồi chấp nhận

Không làm:

~~~java
try {
    return delegate.introspect(token);
}
catch (RuntimeException ex) {
    // Identity server is unavailable, allow request to continue.
    return trustedDefaultPrincipal();
}
~~~

Đoạn này biến outage thành authentication success. Nếu không xác minh được token, phải propagate authentication/service failure để Security filter chặn request.

### 7.3. Anti-pattern: decoder lỗi thì parse JWT không xác minh

Không làm:

~~~java
try {
    return jwtDecoder.decode(token);
}
catch (JwtException ex) {
    return parsePayloadWithoutVerifyingSignature(token);
}
~~~

Payload JWT chỉ là dữ liệu do người gửi cung cấp cho tới khi signature được xác minh. Đọc sub, scope, iss từ payload chưa xác minh rồi tạo principal là bypass trực tiếp.

### 7.4. Anti-pattern: fallback sang một key bất kỳ

Không làm:

~~~text
unknown kid / JWKS timeout
    -> choose first cached key
    -> skip signature error
    -> accept claims
~~~

kid chỉ giúp chọn key. Nếu không tìm được key phù hợp hoặc không xác minh được signature, token không được authenticated. Không dùng key cũ không liên quan hoặc public key do token chỉ định.

### 7.5. Anti-pattern: Mono.empty() như một kết quả xác minh

Trong custom reactive authentication code, không biến timeout/error thành Mono.empty() rồi để route permitAll() vô tình cho phép anonymous access. Mono.empty() có nghĩa không có authentication result; route permitAll() vẫn có thể cho request đi tiếp. Endpoint được bảo vệ phải yêu cầu authenticated/authority rõ ràng và test cả trường hợp không có Authentication.

### 7.6. Anti-pattern: permitAll fallback

Không cấu hình:

~~~java
.anyExchange().permitAll()
~~~

cho API cần access token chỉ để ứng dụng vẫn hoạt động khi AS offline. Những endpoint public thật sự có thể permitAll(), nhưng phải được phân định rõ bằng matcher riêng. Không đặt một rule rộng cho phép mọi request sau khi authentication failure.

## 8. Kiểm thử bằng MockWebServer hoặc WireMock

Dùng một HTTP server giả lập để điều khiển response của JWKS/introspection endpoint. Test vẫn phải gửi Bearer token qua Security filter chain thật của ứng dụng.

Các công cụ thường dùng:

- **MockWebServer:** điều khiển response, delay, disconnect và kiểm tra request nhận được.
- **WireMock:** stub HTTP status/body, fixed delay, fault và request verification.
- Một local test server tương đương nếu dự án đã có test infrastructure.

Không cần gọi AS thật trong unit/integration test thông thường. Test server phải bind loopback/ephemeral port và được đóng sau test để tránh phụ thuộc môi trường.

### 8.1. Ma trận response cho opaque introspection

| Mock AS response | Điều cần kiểm tra |
|---|---|
200 với active=true | Principal được tạo và authorization chạy |
200 với active=false | Token bị từ chối |
401/403 từ introspection endpoint | Credential/config của Resource Server sai; không tạo principal |
500/503 | Authentication không thành công; lỗi hạ tầng được phân loại theo policy |
Response malformed/thiếu active | Không chấp nhận |
Delay vượt read timeout | Request kết thúc trong deadline và không được cấp quyền |
Disconnect trước response | Không tạo principal |
Connection refused | Không tạo principal |

### 8.2. Ma trận response cho JWKS

| JWKS behavior | Token | Điều cần kiểm tra |
|---|---|---|
JWKS trả public key A | Ký bằng private key A | Signature có thể được xác minh |
JWKS trả public key A | Ký bằng private key B | Signature bị từ chối |
JWKS trả 500 | kid chưa cache | Không thể xác minh; không bypass |
JWKS timeout | kid chưa cache | Không tạo Authentication |
JWKS offline | kid đã cache | Kiểm tra behavior cache đã định nghĩa |
JWKS trả JWK Set không parse được | kid chưa cache | Decoder không tạo principal |
JWKS online nhưng không có kid | Token dùng key không có trong set | Authentication thất bại |

Để test lỗi JWKS một cách deterministic, dùng decoder/cache mới cho test cold-cache. Nếu test dùng chung decoder giữa nhiều case, key từ test trước có thể còn trong cache và làm test outage không còn thực sự gọi JWKS.

## 9. Ví dụ integration test opaque token với MockMvc

Ví dụ dưới đây minh họa cấu trúc test. MockWebServer đại diện introspection endpoint; property URI và bean introspector của ứng dụng phải trỏ tới server này.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpaqueIntrospectionFailureIntegrationTest {

    static MockWebServer identityServer;

    @BeforeAll
    static void startIdentityServer() throws IOException {
        identityServer = new MockWebServer();
        identityServer.start();
    }

    @AfterAll
    static void stopIdentityServer() throws IOException {
        identityServer.shutdown();
    }

    @Autowired
    MockMvc mockMvc;

    @Test
    void activeTokenCanReachProtectedEndpoint() throws Exception {
        identityServer.enqueue(new MockResponse()
            .setHeader("Content-Type", "application/json")
            .setBody("""
                {
                  "active": true,
                  "sub": "alice",
                  "scope": "orders.read",
                  "aud": ["orders-api"]
                }
                """));

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-test-token"))
            .andExpect(status().isOk());

        RecordedRequest request = identityServer.takeRequest();
        assertThat(request.getMethod()).isEqualTo("POST");
        assertThat(request.getPath()).isEqualTo("/introspect");
        assertThat(request.getBody().readUtf8())
            .contains("token=opaque-test-token");
    }

    @Test
    void inactiveTokenIsRejected() throws Exception {
        identityServer.enqueue(new MockResponse()
            .setHeader("Content-Type", "application/json")
            .setBody("{\"active\":false}"));

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer inactive-token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Ví dụ cần các imports từ OkHttp MockWebServer và Spring Test. Với introspector dùng cache, phải cấu hình cache riêng/tắt cache cho test này để mỗi request nhận response tương ứng. Kiểm tra request body theo encoding/form contract của implementation; đừng giả định mọi provider gửi cùng thứ tự tham số.

### 9.1. Test timeout

MockWebServer có thể trì hoãn response lâu hơn read timeout:

~~~java
identityServer.enqueue(new MockResponse()
    .setHeadersDelay(5, TimeUnit.SECONDS)
    .setBody("{\"active\":true,\"sub\":\"alice\"}"));
~~~

Nếu read timeout của HTTP client là 2 giây, test phải chứng minh:

- Request không chờ tới 5 giây để nhận response.
- Không có principal authenticated.
- Endpoint được bảo vệ không trả 2xx.
- Exception được ánh xạ theo API contract (401 hoặc 503 nếu có custom handling).
- Không có fallback introspector hoặc principal mặc định được gọi.

Đặt timeout test đủ rộng để tránh flaky do CI scheduling nhưng vẫn ngắn hơn server delay rõ rệt. Không dùng Thread.sleep để đo timeout; kiểm thời gian bằng test deadline/Awaitility hoặc cấu hình MockWebServer deterministic.

### 9.2. Test server disconnect

Có thể dùng SocketPolicy.DISCONNECT_AT_START hoặc policy tương ứng của version MockWebServer để ngắt kết nối. Kỳ vọng giống timeout: request bị chặn và không tạo Authentication. Nếu thư viện test server thay đổi API giữa version, chọn fault mode tương ứng; điều cần chứng minh là client không nhận response xác minh.

## 10. Ví dụ kiểm thử JWKS outage

Để test JWKS, test server phải trả JWK Set có public key test. Token được ký bằng private key tương ứng. Cấu hình NimbusJwtDecoder với URI của server.

### 10.1. Happy path với JWKS

~~~text
1. Generate RSA keypair A.
2. Publish public key A as a JWK with kid=test-key-a.
3. Sign access token with private key A and header kid=test-key-a.
4. Send Authorization: Bearer <token> through MockMvc/WebTestClient.
5. Assert request succeeds and JWKS endpoint received a GET.
~~~

JWK Set response minh họa:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "test-key-a",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

Trong test code, tạo JWK từ public key bằng Nimbus RSAKey và serialize JWKSet để tránh hardcode modulus giả. Không đưa private key vào JWKS response.

### 10.2. Unknown kid khi JWKS trả lỗi

Tạo token ký bằng key B, đặt kid=test-key-b, trong khi JWKS chỉ có key A hoặc trả 503. Dùng decoder mới để chắc chắn key B chưa nằm trong cache.

Kỳ vọng:

- Decoder không tìm được public key tin cậy.
- Authentication thất bại.
- Endpoint được bảo vệ không trả 2xx.
- Không fallback sang parse payload hoặc key bất kỳ.

### 10.3. Key đã cache và JWKS offline

Đây là test khác:

1. Gọi một request đầu để decoder tải key A và xác minh token.
2. Làm JWKS server ngừng trả lời.
3. Gửi token khác nhưng vẫn ký bằng key A và cùng kid.
4. Quan sát behavior theo cache của decoder/version.

Nếu decoder vẫn xác minh được từ key cache, đó là behavior có thể mong đợi. Không kết luận “fail-open” chỉ từ kết quả này; chữ ký vẫn được xác minh bằng public key đã nhận từ nguồn tin cậy. Hãy đặt rõ cache TTL/rotation/revocation assumptions.

## 11. Kiểm chứng không có đường đi bỏ qua xác minh

Một test chỉ assert status 401 khi AS lỗi là chưa đủ nếu có một đường code khác có thể cấp Authentication. Cần chứng minh request được bảo vệ không tới controller và không có fallback path.

### 11.1. Theo dõi controller/service không được gọi

~~~java
@Test
void introspectionFailureNeverInvokesProtectedHandler() throws Exception {
    identityServer.enqueue(new MockResponse().setResponseCode(503));

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-test-token"))
        .andExpect(status().isServiceUnavailable());

    verify(orderService, never()).listOrders(any());
}
~~~

Ví dụ kỳ vọng 503 nếu ứng dụng có custom mapping lỗi identity-provider outage. Nếu API dùng Bearer entry point mặc định và trả 401 cho authentication failure, hãy assert status thực tế theo contract nhưng vẫn bắt buộc xác minh service/controller không được gọi.

### 11.2. Kiểm tra số lần gọi introspector

Dùng spy/mock hoặc test introspector có counter để xác nhận:

- Request Bearer hợp lệ đi qua introspector/decoder.
- Request Bearer gặp timeout không được thay bằng một principal fixture.
- Không có lần gọi fallback tới introspector thứ hai trả active=true.
- Một cache hit chỉ xảy ra khi đã có entry được xác minh trước đó và còn TTL.

Với JWKS, kiểm tra request tới JWKS endpoint khi cold-cache/unknown-kid; nhớ rằng cache có thể làm số lần gọi bằng 0 cho request tiếp theo.

### 11.3. Không dùng mock authentication trong integration test trust

Các helper sau cố ý bỏ qua bước xác minh token:

- mockJwt() trong WebTestClient.
- jwt()/mockJwt() trong MockMvc.
- opaqueToken()/mockOpaqueToken() trong MockMvc/WebTestClient.
- @WithMockUser.
- Tự đặt SecurityContext hoặc JwtAuthenticationToken.

Chúng phù hợp để test authorization/controller sau authentication. Chúng không thể chứng minh timeout hoặc lỗi mạng của decoder/introspector được xử lý an toàn. Trong integration test này, gửi Bearer token thực (test token ký thật với JWT, chuỗi opaque test với introspection stub) qua filter chain.

### 11.4. Kiểm tra protected route không cho anonymous đi qua

Khi auth thất bại, framework có thể không tạo Authentication và request có thể trở thành anonymous. Vì vậy, mọi route nhạy cảm phải có rule authenticated()/authority rõ ràng. Test:

- Không có token → không truy cập được protected route.
- Token không xác minh được do dependency outage → không truy cập được protected route.
- Token inactive/invalid → không truy cập được protected route.
- Token hợp lệ và đủ quyền → truy cập được.
- Public route chỉ được mở theo matcher rõ ràng, không phải fallback toàn cục.

Nếu có route permitAll(), hãy test matcher để bảo đảm protected path không vô tình rơi vào route public.

## 12. Circuit breaker, retry và bulkhead

Circuit breaker có thể ngăn ứng dụng tiếp tục tạo tải lên AS đang lỗi. Khi circuit open, authentication dependency phải trả lỗi rõ ràng và request được bảo vệ vẫn bị chặn.

### 12.1. Circuit breaker không có fallback “active”

Mẫu hành vi:

~~~text
introspection call
    |
    +-- success + active=true -> authenticated principal
    +-- success + active=false -> invalid token
    +-- timeout / connection / 5xx -> authentication service failure
    +-- circuit open -> authentication service failure
~~~

Không cấu hình fallback trả principal mặc định, scope mặc định hoặc active=true. Circuit breaker chỉ điều tiết việc gọi dependency; nó không thay thế xác minh token.

### 12.2. Bounded retry

Retry nên:

- Chỉ áp dụng cho lỗi transient đã xác định.
- Có số lần thử hữu hạn.
- Có backoff nhỏ và jitter nếu cần.
- Tính vào overall deadline.
- Không retry lỗi token invalid, signature, issuer, audience hoặc active=false.
- Không retry liên tục khi circuit breaker open.

### 12.3. Bulkhead và connection pool

Giới hạn concurrency dành cho identity provider để một outage không chiếm hết tài nguyên của API. Theo dõi:

- Số request đang chờ xác minh.
- Connection pool utilization.
- Timeout count và latency percentile.
- Circuit breaker state.
- Số authentication failure do credential và số service failure do dependency.

Không tăng pool size vô hạn để che timeout; việc đó có thể chuyển outage của AS thành outage của Resource Server.

## 13. Cache và outage policy cần được kiểm thử

Nếu triển khai cache cho introspection hoặc dùng JWKS cache, test phải mô tả rõ cache behavior:

| Test | Trạng thái cache | Dependency | Kết quả cần xác minh |
|---|---|---|---|
Opaque token first use | Miss | AS active=true | Principal được tạo và entry được cache |
Opaque token reuse | Hit, TTL còn | AS offline | Theo policy, có thể dùng kết quả active đã xác minh |
Opaque token after TTL | Expired | AS offline | Fail closed; không biến miss thành active |
Opaque token after revoke | Cached active | AS active=false/revoked | Revocation delay không vượt SLA đã định |
JWT known kid | Public key cached | JWKS offline | Signature vẫn được verify bằng cached key nếu policy/cache cho phép |
JWT unknown kid | Miss | JWKS offline | Không xác minh được; từ chối |
Cache store unavailable | Unknown | AS online/offline | Theo policy rõ; không dùng entry không xác minh |

Không nên viết assertion chung “AS offline thì tất cả token đều bị từ chối” nếu hệ thống cố ý dùng cache có TTL. Điều phải giữ là **không có cache entry hợp lệ thì không có xác minh thì không có Authentication**.

## 14. Những lỗi thường gặp

| Anti-pattern | Rủi ro | Cách xử lý |
|---|---|---|
Không đặt connect/read timeout | Request/thread/connection bị giữ lâu | Timeout hữu hạn ở HTTP client |
Chỉ dùng Mono.timeout mà không cấu hình HTTP connector | Publisher timeout nhưng network resource có thể chưa được giới hạn đúng | Cấu hình cả connector và overall deadline |
Retry mọi exception | Tăng tải AS và kéo dài request | Retry bounded cho transient failure |
AS timeout thì trả active=true | Bypass xác minh trực tiếp | Propagate service/authentication failure |
JWT decoder lỗi thì parse payload | Chấp nhận claims chưa xác minh | Không tạo principal nếu signature/key validation fail |
JWKS offline thì chọn key đầu tiên | Có thể xác minh bằng key sai | Chỉ dùng key match theo trusted JWK Set và kid |
Dùng mockJwt() để test JWKS timeout | Bỏ qua decoder/JWKS | Gửi signed Bearer JWT qua filter chain |
Dùng opaqueToken() để test introspection timeout | Bỏ qua introspector | Gửi opaque Bearer token qua filter chain |
Cache exception thành active | Outage kéo dài thành quyền truy cập sai | Cache chỉ successful verified response theo policy |
Không tách active=false và 5xx | Credential failure bị nhầm với outage | Phân loại lỗi và metrics riêng |
Fallback Mono.empty() trên auth error | Route permitAll() có thể cho anonymous đi qua | Protected routes yêu cầu authenticated/authority |
Circuit breaker fallback principal | Circuit open vẫn cấp quyền | Circuit open phải fail closed |
Test dùng decoder/key cache chung | Test JWKS outage không gọi network | Tạo decoder/cache mới cho cold-cache case |
Chỉ assert status, không assert handler | Có thể handler đã chạy qua fallback | Verify controller/service không được gọi |
Log raw token hoặc client secret | Credential leakage | Redact token/secret, log correlation ID |

## 15. Ma trận kiểm thử tổng hợp

| Scenario | Cách kích hoạt | Kết quả security | Assertion bổ sung |
|---|---|---|---|
Opaque active | AS trả active=true | Authenticated | Handler được gọi |
Opaque inactive | AS trả active=false | 401 | Handler không được gọi |
Introspection 500 | Mock AS trả 500 | Fail closed | 401/503 theo contract; không principal |
Introspection timeout | Delayed response quá deadline | Fail closed | Hoàn tất trong deadline; handler không được gọi |
Introspection disconnect | Server đóng socket | Fail closed | Không fallback |
JWKS valid | JWKS chứa public key đúng | Authenticated | Decoder xác minh chữ ký |
JWKS 503, cold cache | Unknown kid | Fail closed | Không parse payload để cấp quyền |
JWKS timeout, cold cache | Unknown kid | Fail closed | Handler không được gọi |
JWKS outage, warm cache | Key còn cache | Theo cache policy | Signature vẫn được xác minh |
Circuit open | Mô phỏng breaker open | Fail closed | Không gọi AS liên tục, không principal |
Missing Bearer | Không gửi token | 401 | Protected handler không được gọi |
Valid token thiếu scope | Token xác minh thành công | 403 | Authentication có, authorization fail |
Valid token đủ scope | Token xác minh thành công | 2xx | Handler được gọi |

## 16. Checklist trước khi phát hành

### Network resilience

- [ ] Connect timeout được cấu hình cho JWKS/introspection HTTP client.
- [ ] Read/response timeout được cấu hình.
- [ ] Có overall deadline cho authentication dependency.
- [ ] Retry có giới hạn và chỉ áp dụng cho transient failures.
- [ ] Connection pool/concurrency có giới hạn.
- [ ] WebFlux không thực hiện blocking I/O trên event loop.

### Fail-closed

- [ ] active=false không tạo Authentication.
- [ ] Timeout/DNS/TLS/5xx không tạo Authentication.
- [ ] Decoder không parse payload chưa xác minh để tạo principal.
- [ ] Unknown kid không fallback sang key bất kỳ.
- [ ] Cache miss + dependency offline bị từ chối.
- [ ] Circuit breaker open không có fallback authenticated principal.
- [ ] Protected route không cho anonymous đi qua.

### Integration test

- [ ] Test gửi Bearer token qua filter chain thật.
- [ ] Test introspection active/inactive.
- [ ] Test introspection timeout, disconnect và 5xx.
- [ ] Test JWKS valid, unknown kid, timeout/5xx với cold cache.
- [ ] Test JWKS warm-cache behavior riêng.
- [ ] Assert controller/service không được gọi khi xác minh thất bại.
- [ ] Test status mapping 401/503 theo API contract.
- [ ] Không dùng mockJwt()/opaqueToken() để thay cho network verification tests.

## 17. Kết luận

~~~text
TOKEN VALIDATION
  JWT: trusted key + signature + iss/aud/time/type
  Opaque: successful introspection + active=true

DEPENDENCY FAILURE
  DNS / connect / TLS / timeout / 5xx / malformed response
      |
      v
  NO VERIFIED AUTHENTICATION
      |
      v
  Protected endpoint remains inaccessible
  (401 or 503 according to explicit API policy)

NEVER
  network error -> active=true
  decoder error -> unverified payload principal
  unknown kid -> arbitrary key
  circuit open -> default authenticated user
  cache miss -> accept without verification
~~~

Network failure và timeout là tình huống vận hành bình thường cần được kiểm thử như một phần của trust boundary. JWT Resource Server có thể tiếp tục xác minh bằng public key đã cache; opaque Resource Server có thể dùng một introspection result đã cache trong TTL được policy cho phép. Nhưng khi không có key hoặc kết quả introspection đáng tin, hệ thống không được tạo Authentication.

Hãy cấu hình timeout ở HTTP client thật sự được decoder/introspector sử dụng, giới hạn retry/deadline và kiểm tra hành vi khi dependency lỗi bằng MockWebServer/WireMock. Quan trọng nhất, gửi Bearer token qua Security filter chain trong integration test, xác minh protected handler không chạy và không có fallback nào biến lỗi mạng thành quyền truy cập. mockJwt() và opaqueToken() vẫn hữu ích cho test controller/authorization, nhưng không chứng minh network verification hay fail-closed behavior.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response, active và token metadata.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK Set, key identifiers và public key distribution.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata và endpoint configuration.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token validation profile.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): signature verification, trusted key sources và JWT validation.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): OpaqueTokenIntrospector và opaque-token authentication.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, JWKS và JWT validation.
- [Spring Security Reference — Reactive Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): reactive opaque-token introspection.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder và WebFlux JWT authentication.
- [Spring Framework Reference — HTTP Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): cấu hình HTTP clients và request factories.
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client.
- [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): connect timeout, response timeout và connection settings.
- [OkHttp MockWebServer](https://github.com/square/okhttp/tree/master/mockwebserver): điều khiển HTTP responses và lỗi mạng trong test.
- [WireMock Documentation](https://wiremock.org/docs/): stubbing, delays, faults và request verification.
