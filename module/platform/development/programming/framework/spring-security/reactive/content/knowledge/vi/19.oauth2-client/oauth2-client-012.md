# Tùy chỉnh kết nối HTTPS, timeout và lỗi khi gọi token endpoint trong Spring Security reactive OAuth2 Client

## 1. Mục tiêu bài học

Trong Spring Security - reactive, **OAuth2 Client** không chỉ là chỗ khai báo `client-id` và `client-secret`. Khi cần lấy access token, thành phần client phải gọi **Token Endpoint** của Authorization Server qua HTTP. Nếu môi trường có CA nội bộ, mutual TLS, proxy doanh nghiệp, độ trễ mạng hoặc Token Endpoint bị quá tải, ứng dụng cần điều chỉnh **HTTPS/TLS, timeout, connection pool, cách xử lý lỗi và khả năng quan sát** ở đúng chỗ.

Bài này tập trung vào **lượt gọi token endpoint** trong OAuth2 Client WebFlux: `client_credentials` để service-to-service, và chỉ rõ cách áp dụng ý tưởng tương ứng cho `authorization_code` và `refresh_token`. Đây không phải bài thiết kế OpenID Provider hay triển khai Resource Server.

Sau bài học, bạn có thể:

1. Xác định Token Endpoint nằm ở đâu trong flow OAuth2 và phân biệt nó với Authorization Endpoint, callback URL và Resource Server API.
2. Biết các class reactive phù hợp: `WebClientReactiveClientCredentialsTokenResponseClient`, `WebClientReactiveAuthorizationCodeTokenResponseClient`, `WebClientReactiveRefreshTokenTokenResponseClient`, `ReactiveOAuth2AccessTokenResponseClient`, `ReactiveOAuth2AuthorizedClientManager`.
3. Dùng `setWebClient(...)` với `ReactorClientHttpConnector` và Reactor Netty `HttpClient` để cấu hình kết nối riêng **chỉ cho token request**.
4. Giữ **certificate chain validation + hostname verification** khi dùng HTTPS, cấu hình truststore cho CA nội bộ, phân biệt truststore với mTLS keystore.
5. Đặt giới hạn **pool acquire, TCP connect, TLS handshake, response timeout và tổng token exchange deadline**; hiểu mỗi timeout đo điều gì.
6. Nhận biết lỗi `invalid_client`, `invalid_scope`, `invalid_grant`, 429/5xx, DNS/TCP/SSL và timeout; phân biệt lỗi **OAuth2 protocol** với lỗi **transport**.
7. Quyết định tình huống nào **không được retry**, tránh phát lại authorization code hoặc tạo bão request lên Authorization Server.
8. Biên soạn app Java 17+ / Spring Boot 3.3.13 / WebFlux dùng `client_credentials` với HTTPS Keycloak local có self-signed cert và truststore cụ thể.
9. Kiểm thử endpoint vận hành bằng `WebTestClient` khi cấp token thành công, provider trả lỗi, network timeout, caller 401/403; hiểu mock test khác E2E TLS.
10. Áp dụng nguyên tắc **không leak access token/client secret** qua response, log, metrics hay tracer, kể cả lúc lỗi.
11. Phân biệt cấu hình OAuth2 Login, background job và các grant type để không tùy biến sai `WebClient`.
12. Thiết kế time budget, health/observability, resource isolation và hành vi fail-closed cho môi trường sản xuất.

**Ý quan trọng:** Đổi `spring.security.oauth2.client.provider.*.token-uri` chỉ đổi **địa chỉ**, không tự cấu hình pool, TLS trust hoặc timeout cho HTTP client. Ngược lại, tạo một `WebClient.Builder` dùng chung không đảm bảo OAuth2 token exchange sẽ tự lấy cấu hình đó. Cần nối đúng `WebClient` tùy biến vào **token response client** của grant type tương ứng.

## 2. Token Endpoint xuất hiện ở đâu?

### 2.1. Client Credentials: máy gọi máy

```text
Spring WebFlux Service                 Authorization Server
   |                                         |
   | 1. Cần access token để gọi API          |
   |                                         |
   | 2. POST /realms/learning/.../token      |
   |    grant_type=client_credentials         |
   |    Authorization: Basic <client-credentials>
   |---------------------------------------->|
   |                                         |
   | 3. Xác minh client ID/secret/permissions |
   |<----------------------------------------|
   |  200 {access_token,token_type,expires_in}|
   |                                         |
   | 4. Client lưu OAuth2AuthorizedClient     |
   |    rồi dùng Bearer token gọi API khác    |
   |                                         |
Resource Server khác: Authorization: Bearer <access-token>
```

`client_credentials` không có browser login, authorization code, `state` hay callback. Nó dùng **danh tính của client ứng dụng**; thường dành cho background jobs, đồng bộ dữ liệu hoặc server-to-server. Access token vẫn phải có audience/scope phù hợp với Resource Server.

**Ví dụ HTTP cơ bản:**

```http
POST /realms/learning/protocol/openid-connect/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-id-and-secret>

grant_type=client_credentials
```

Phản hồi hợp lệ có thể là:

```json
{
  "access_token": "REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "profile"
}
```

Đây là **minh họa giao thức**, không phải access token thật. Không đưa `access_token`/`refresh_token` từ provider vào HTTP response của một trang kiểm tra vận hành.

### 2.2. Authorization Code Grant

Trong login OAuth2/OIDC, browser được redirect tới Authorization Server rồi callback về Spring client với `code`. **Token exchange vẫn là request backend-to-backend**:

```text
Browser -> /oauth2/authorization/{registrationId} -> Provider login
Browser -> /login/oauth2/code/{registrationId}?code=...&state=...
WebFlux client -> POST Token Endpoint, grant_type=authorization_code
Provider -> access_token, id_token (nếu OIDC), ...
```

Class token response client dành cho grant này là `WebClientReactiveAuthorizationCodeTokenResponseClient`. Nó cũng có `setWebClient(...)` nhưng **cần được wire vào OAuth2 Login**, không chỉ vào một service manager độc lập nếu bạn dùng browser login.

Không retry mù quáng `authorization_code`: code thường ngắn hạn, một lần, một lần trao đổi thất bại/timeout có thể làm code đã được tiêu thụ dù client chưa nhận response. Giải pháp cho user thường là **khởi động lại authorization flow**, không lặp lại cùng code 5 lần.

### 2.3. Refresh Token Grant

Khi access token sắp hết hạn, Client có thể dùng refresh token (nếu được cấp) để xin token mới. Class reactive tương ứng là `WebClientReactiveRefreshTokenTokenResponseClient`. Refresh token có thể bị **rotate** và single-use theo policy provider; retry sau khi request timeout có thể làm mất tính hợp lệ/chuỗi rotation.

`client_credentials` thường **không dựa vào refresh token** như user login. Client manager có thể xin một access token mới khi token cũ gần hết hạn; các lần gọi manager không nhất thiết luôn tới Token Endpoint vì còn cache authorized client.

### 2.4. Ba loại lỗi phải tách biệt

| Nhóm | Ví dụ | Quyết định |
| --- | --- | --- |
| OAuth2 protocol rejection | `invalid_client`, `invalid_scope`, `invalid_grant` | Lỗi identity/grant/policy; thường không retry tự động |
| HTTP/provider availability | 429, 502/503/504 hoặc endpoint trả payload sai | Kiểm tra rate-limit/SLO, retry hạn chế nếu policy cho phép |
| Transport/TLS | DNS fail, TCP connect fail, certificate unknown, hostname mismatch, TLS handshake timeout | Không có OAuth2 response thành công; cần sửa kết nối/trust/cert/network |

**Không đồng nhất HTTP 401 từ Token Endpoint với 401 của Resource Server.** 401 token endpoint thường nghĩa client authentication thất bại; 401 Resource Server thường nghĩa Bearer token không hợp lệ/thiếu. Đọc đường đi và error code trước khi sửa.

## 3. Thành phần nào thực sự gửi token request?

Spring Security WebFlux sử dụng một chuỗi:

```text
Application service / WebClient với OAuth2
            |
            v
ReactiveOAuth2AuthorizedClientManager
            |
            v
ReactiveOAuth2AuthorizedClientProvider
   (client_credentials, authorization_code, refresh_token...)
            |
            v
ReactiveOAuth2AccessTokenResponseClient<TGrantRequest>
            |
            v
WebClientReactive*TokenResponseClient
            |
            v
WebClient + ReactorClientHttpConnector
            |
            v
Reactor Netty HttpClient (TLS, pool, timeouts, proxy)
            |
            v
HTTPS Token Endpoint
```

Class và vai trò:

| Loại | Công dụng |
| --- | --- |
| `ReactiveClientRegistrationRepository` | Cung cấp `ClientRegistration`, bao gồm token URI, client auth method |
| `OAuth2AuthorizeRequest` | Yêu cầu manager authorize một registration với principal key |
| `ReactiveOAuth2AuthorizedClientManager` | Quản lý authorize, cache/re-authorize, persistence |
| `ClientCredentialsReactiveOAuth2AuthorizedClientProvider` | Xử lý grant `client_credentials` |
| `WebClientReactiveClientCredentialsTokenResponseClient` | HTTP POST tới Token Endpoint, parse OAuth2 response |
| `WebClientReactiveAuthorizationCodeTokenResponseClient` | Token exchange cho authorization code |
| `WebClientReactiveRefreshTokenTokenResponseClient` | Refresh token exchange |
| `ReactorClientHttpConnector` | Nối Spring `WebClient` với Reactor Netty HttpClient |
| `ConnectionProvider` | Pool connection và acquire wait |
| `SslContextBuilder` + `TrustManagerFactory` | Định nghĩa nguồn CA tin cậy cho TLS |
| `ServerHttpSecurity` | Bảo vệ inbound HTTP; **không** tự thay WebClient outbound token request |
| `OAuth2AuthorizationException` | Một kiểu lỗi OAuth2 ở Spring Security, có `OAuth2Error` |

Tài liệu Spring Security 6.3+ cho phép công bố bean `ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>` để framework nối vào các thành phần mặc định. Đối với ví dụ bên dưới, chúng ta **cố ý tạo manager thủ công** và gọi `provider.setAccessTokenResponseClient(...)` để mọi người nhìn thấy chính xác wiring và dùng được cả trong background service không có `ServerWebExchange`.

**Đừng dùng Servlet types** `DefaultClientCredentialsTokenResponseClient`, `OAuth2AuthorizedClientManager` đồng bộ hoặc `RestTemplate` vào WebFlux. Những tên giống nhau nhưng thuộc stack khác. Cũng không bọc HTTP call blocking bằng `Mono.just(restTemplate...);` vì lời gọi đã chạy đồng bộ trước khi publisher được tạo.

## 4. HTTPS cho token endpoint: trust không đồng nghĩa với bỏ xác minh

### 4.1. TLS kiểm tra những gì?

Khi Client gọi `https://auth.example.test/oauth2/token`, client TLS cần:

1. Có thể phân giải hostname và kết nối TCP.
2. TLS handshake thành công với protocol/cipher suites được hai bên hỗ trợ.
3. Certificate chain dẫn đến CA được tin cậy hoặc pin/truststore được cấu hình đúng.
4. Certificate đang trong thời hạn hiệu lực, không vi phạm những policy liên quan.
5. **Hostname verification**: SAN của certificate phải khớp hostname Client thực sự kết nối.
6. Kiểm tra mTLS client certificate **nếu** Token Endpoint yêu cầu, ngoài client authentication của OAuth2.

**CA trust ≠ hostname verification.** Một certificate do CA tin cậy ký nhưng chỉ có SAN `api.example.test` vẫn phải thất bại nếu client kết nối `https://auth.example.test`. **mTLS ≠ client_secret_basic**: hai cơ chế có thể cùng tồn tại, nhưng một bên là TLS client certificate, một bên là OAuth2 token endpoint client authentication.

### 4.2. Production public CA

Nếu Authorization Server dùng certificate chain của CA công khai được runtime tin cậy, HTTP client mặc định có thể thực hiện TLS validation. Không phải môi trường nào cũng cần truststore riêng.

Đừng cấu hình `trustManager(InsecureTrustManagerFactory.INSTANCE)` hoặc `verifyHostname(false)` để vượt lỗi test. Hành vi đó mở cửa **man-in-the-middle**: kẻ tấn công có thể giả Token Endpoint, nhận client credentials và phát token giả.

### 4.3. Nội bộ/self-signed: chỉ trust CA/cert cần thiết

Khi công ty dùng private CA hoặc máy lab tự ký:

- Tạo `PKCS12` truststore chứa CA root/intermediate tin cậy; lab có thể import một self-signed server cert.
- Đọc truststore qua Java `KeyStore` + `TrustManagerFactory`.
- Truyền vào Netty `SslContextBuilder.forClient().trustManager(...)`.
- Dùng `HttpClient.secure(sslSpec -> sslSpec.sslContext(...))`. Ở Reactor Netty 1.1.x, overload secure với Consumer áp dụng hostname verification theo mặc định; hãy xác nhận với hostname mismatch negative test.
- Giữ token URI là HTTPS có hostname đúng SAN.
- Quản lý password truststore/keystore qua secret manager hoặc environment, không commit vào Git.

**Đừng biến truststore thành thư mục chứa toàn bộ certificates người dùng upload.** Trust anchor phải qua quy trình phê duyệt và có vòng đời/rotation.

### 4.4. Truststore khác keystore mTLS

| Kho | Thường chứa | Dùng để |
| --- | --- | --- |
| Truststore | Public CA certificates / trusted server certs | Xác minh **server** của Token Endpoint |
| Client keystore (mTLS) | Client private key và certificate chain | Chứng minh danh tính **client** ở TLS handshake |
| OAuth2 client secret | Secret đăng ký tại Authorization Server | Client authentication ở tầng OAuth2 token request |
| Access token | Quyền cho resource API | Bearer đến Resource Server, không phải TLS credential |

Nếu Token Endpoint yêu cầu mTLS, cần load client key/certificate qua `KeyManagerFactory` và `SslContextBuilder.keyManager(...)`. Không copy truststore vào keyManager hoặc lưu private key trong tài liệu bài học.

### 4.5. TLS lỗi phải fail-closed

Các lỗi thường gặp:

| Dấu hiệu | Khả năng | Điều cần làm |
| --- | --- | --- |
| `SSLHandshakeException: PKIX path building failed` | CA/server chain không tin cậy | Import đúng CA vào truststore, kiểm chain |
| `No subject alternative names matching ...` | Host trong token URI không khớp SAN | Sửa DNS/URL/cert SAN |
| `certificate expired` | Server/CA certificate hết hạn | Rotate certificate, không tắt kiểm |
| `handshake timed out` | SSL negotiation/network/proxy chậm/hỏng | Kiểm hạ tầng, handshake timeout budget |
| `Connection refused` | Không có listener hoặc port sai | Kiểm token URI/health/network |
| `UnknownHostException` | DNS sai | Kiểm DNS, VPN/proxy, pod DNS |
| `invalid_client` | Client ID/secret/auth method không khớp | Sửa OAuth2 registration, không phải TLS |

Chỉ đổi mức timeout không chữa được certificate trust failure. Đặc biệt **không auto-retry lỗi hostname/cert** vì retry chỉ tạo thêm tải, không làm chứng chỉ hợp lệ hơn.

## 5. Timeout: có nhiều đồng hồ khác nhau

Một token request có thể trải qua:

```text
Authorization call
   |
   +-- chờ pool có connection        pending acquire timeout
   +-- DNS lookup                    resolver timeout
   +-- mở TCP                        CONNECT_TIMEOUT_MILLIS
   +-- TLS handshake                 SSL handshakeTimeout
   +-- gửi POST form data
   +-- đợi/đọc HTTP response         responseTimeout
   +-- giải mã JSON, OAuth2 errors
   |
   +-- tổng trao đổi (từ subscribe)  Mono.timeout / overall deadline
```

### 5.1. Timeout phân lớp

| Timeout | Cấu hình tiêu biểu | Nó chặn việc gì? |
| --- | --- | --- |
| Pool acquire | `ConnectionProvider.pendingAcquireTimeout(Duration)` | Đợi slot connection trong pool |
| Pool queue cap | `pendingAcquireMaxCount(n)` | Số request đang đợi slot, tránh queue vô hạn |
| TCP connect | `ChannelOption.CONNECT_TIMEOUT_MILLIS` | Thời gian dựng kết nối TCP |
| TLS handshake | `HttpClient.secure(ssl -> ssl.handshakeTimeout(...))` | TLS handshake không hoàn thành |
| HTTP response | `HttpClient.responseTimeout(Duration)` | Chờ/đọc response từ peer theo semantics Reactor Netty |
| Overall token exchange | `Mono.timeout(Duration)` quanh `getTokenResponse` | Toàn bộ quá trình chờ publisher trả token response hoặc lỗi |
| Resource Server request | Cấu hình `WebClient` outbound **khác** | Độ trễ gọi API sau khi đã có token |

**Không cộng đơn giản các timeout rồi cho rằng độ trễ tối đa chính xác bằng tổng đó.** Một số giới hạn chỉ áp dụng ở từng giai đoạn; kết nối pooled có thể bỏ qua DNS/connect/TLS, còn overall deadline phủ tất cả các giai đoạn sau khi subscribe.

Reactor Netty `responseTimeout` áp dụng giới hạn thời gian phản hồi/đọc theo cơ chế request, không thay thế một deadline tuyệt đối bao trùm pool wait, DNS, TLS, giải mã body. Dùng `Mono.timeout` quanh **`getTokenResponse`**, không chỉ filter `next.exchange(request)` của `WebClient`, vì `exchange` có thể hoàn thành sau response headers trong khi token body vẫn chưa được giải mã.

### 5.2. Ví dụ ngân sách

Cho một hệ thống có yêu cầu trả lỗi kịp thời:

```text
Pending pool acquire:       1 giây
TCP connect:                2 giây
TLS handshake:              4 giây
HTTP response timeout:      4 giây
Overall token deadline:     9 giây
```

Đây là **giá trị minh họa cần đo theo SLO**, không phải chuẩn áp dụng mọi môi trường. Deadline 9 giây có thể chặn sớm hơn tổng lý thuyết của các bước; đó là chủ đích tránh chờ vô hạn. Với endpoint vốn có SLO 2 giây, time budget phải ngắn hơn và phù hợp retry budget. Với mạng xuyên vùng/PKI chậm, cần đo thực tế p95/p99 và điều chỉnh.

### 5.3. Hủy reactive không đồng nghĩa server rollback

Khi `Mono.timeout` phát `TimeoutException`, subscriber upstream thường được cancel. Nhưng request có thể đã đến Authorization Server và token có thể đã được phát rồi, chỉ là response đến trễ. **Không được** giả định “timeout tức server chắc chắn chưa làm gì”.

Điều này đặc biệt quan trọng với:
- `authorization_code`: code có thể đã tiêu thụ.
- `refresh_token`: rotation có thể đã xảy ra.
- `client_credentials`: nhiều token có thể được phát khi retry nhiều lần; tốn quota/tạo tải.

Vì vậy cơ chế retry phải xét **idempotency/grant semantics** và trạng thái token cache chứ không dựa riêng vào `Retry.backoff(...)`.

### 5.4. Connection pool và backpressure

Dưới tải cao, nhiều request đồng thời cần token có thể tạo:
- Burst kết nối TCP/TLS;
- Pending-acquire queue lớn;
- Authorization Server 429 hoặc 503;
- Cache stampede khi token hết hạn cùng lúc;
- Socket exhaustion, event loop bị ảnh hưởng nếu thêm code blocking.

Giới hạn connection pool, pending queue và request concurrency là cần thiết. Pool quá nhỏ gây timeout dù provider khỏe; pool quá lớn có thể gây overload provider. Đo `pendingAcquire`, handshake, response latency và actual token exchanges, không chỉ tổng HTTP latency của API.

**Cache token đúng cách:** AuthorizedClientManager/AuthorizedClientService thường tái sử dụng token còn hạn cho cùng client registration/principal key. Đừng gọi token endpoint trước **mọi** business request nếu không cần, và đừng tạo `principal("random-UUID")` mỗi lần vì sẽ phá hiệu quả cache.

## 6. Lỗi Token Endpoint và hành vi fail-closed

### 6.1. OAuth2 error response

Theo OAuth2, Authorization Server có thể trả JSON lỗi:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "invalid_client",
  "error_description": "Client authentication failed"
}
```

Các error codes tiêu biểu:

| OAuth2 error | Ý nghĩa thường gặp | Retry? |
| --- | --- | --- |
| `invalid_client` | Sai client ID/secret, auth method, client bị vô hiệu | **Không**; sửa cấu hình/secret |
| `invalid_grant` | Code/refresh token sai, hết hạn, replay, redirect/PKCE mismatch | **Không** với cùng code/refresh token |
| `invalid_scope` | Scope không được phép hoặc không tồn tại | **Không**; sửa scope/permissions |
| `unsupported_grant_type` | Provider không hỗ trợ grant | **Không**; sửa registration/IdP |
| `invalid_request` | Thiếu/không hợp lệ tham số form | **Không**; sửa payload/wiring |
| `unauthorized_client` | Client không được dùng grant/scope | **Không**; sửa policy IdP |

Trong Spring Security, lỗi OAuth2 protocol có thể được biểu diễn bởi `OAuth2AuthorizationException` và `OAuth2Error`; tùy grant/client/version sẽ có wrapper khác. Khi tự viết error handling, kiểm **cause chain và test trên phiên bản thật**, không hardcode rằng mọi status 401/400/429 sẽ luôn thành một class duy nhất.

### 6.2. HTTP 429 và 5xx

Token Endpoint có thể trả:
- 429 Too Many Requests: quota/rate limiting, có thể có `Retry-After`.
- 500 Internal Server Error: provider hỏng.
- 502/503/504: gateway/ingress/upstream lỗi.
- 200 nhưng JSON không đúng format/thiếu `access_token`: lỗi protocol/schema, không coi là token thành công.

Có thể xét **retry hạn chế** cho request có tính an toàn/idempotency phù hợp, với exponential backoff + jitter + upper deadline, tôn trọng `Retry-After` và circuit breaker. Với 429 do chính ứng dụng làm quá tải, retry tức thời có thể làm tình hình tệ hơn.

**Không áp dụng cùng retry policy cho tất cả grant.** Authorization code và rotating refresh token có rủi ro replay; một số client_credentials request tương đối ít phụ thuộc vào state nhưng vẫn có quota/cost. Chỉ retry khi có căn cứ provider/contract và giới hạn rõ.

### 6.3. Lỗi transport

Các lỗi như DNS, TCP refused, TLS trust failure, `WebClientRequestException`/Netty exception hay `TimeoutException` **không phải** `invalid_client`. Cần lưu mã lỗi nội bộ dạng `TOKEN_ENDPOINT_UNAVAILABLE`/`TOKEN_TIMEOUT`, ghi metrics và trả response phù hợp cho caller, không bịa `invalid_grant` để thống nhất format.

Nếu không lấy được token, **không gọi Resource Server như đã được xác thực**. Không trả một token cũ đã expired, không tạo bearer token giả và không biến lỗi thành `Mono.empty()` khiến code phía sau nghĩ authorization thành công.

### 6.4. Giữ an toàn log và response

Được phép log:
- `registrationId`, provider alias, category (`timeout`/`tls_error`/`oauth_error`/`http_5xx`);
- HTTP status, latency, correlation ID;
- Sanitized OAuth2 `error_code` từ allowlist;
- pool active/pending count và timeout count.

Không được log:
- `Authorization: Basic ...`/`client-secret`;
- body token response chứa access/refresh token;
- authorization code, code_verifier, client assertion, DPoP proof;
- raw TLS private key, keystore password;
- session cookie hay raw ID Token;
- full request/response wiretap của token endpoint.

**Đặc biệt:** `HttpClient.wiretap(true)` hoặc `ExchangeFilterFunction` log body/header có thể ghi **toàn bộ credential/token**. Không bật wiretap/debug body trong production; nếu cần debug test, dùng fake data và redact.

## 7. Ví dụ đầy đủ: Spring Boot WebFlux + HTTPS Keycloak + token timeouts

Ví dụ thực hành dùng:
- **Java 17+**, Spring Boot **3.3.13**, Gradle;
- WebFlux server tại `http://localhost:8080` chỉ cho một user OPS demo gọi endpoint kiểm tra;
- Authorization Server **Keycloak HTTPS** tại `https://localhost:9443`;
- Client registration `machine` với grant `client_credentials` và `client_secret_basic`;
- TLS truststore `PKCS12` chứa self-signed cert lab;
- Outbound token `WebClient` riêng với pool, connect/handshake/response/overall timeout;
- `ReactiveOAuth2AuthorizedClientManager` của service, không phụ thuộc browser `ServerWebExchange`;
- API kiểm tra trả **trạng thái + expiresAt**, **không** trả raw access token.

**Lưu ý bảo mật:** Môi trường local dùng private key và password giả để học. Không mở Keycloak dev mode/public port, không đưa token probe endpoint hoặc `{noop}` password vào production.

### 7.1. Cây thư mục

```text
reactive-token-endpoint-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/TokenTlsApplication.java
      java/example/TokenClientConfig.java
      java/example/TokenProbeController.java
      resources/application.yml
    test/
      java/example/TokenProbeControllerTests.java
  tls/
    (cert.pem, key.pem, truststore.p12 được tạo cục bộ)
```

Không commit `tls/key.pem` hoặc truststore/private key sản phẩm. Lab tự ký là nguồn tin cậy **chỉ trong môi trường demo**.

### 7.2. settings.gradle

```groovy
rootProject.name = 'reactive-token-endpoint-lab'
```

### 7.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Gradle 7.5+/8.x và Java 17+ tương thích với Spring Boot 3.3.13; ưu tiên Gradle Wrapper có version cố định trong dự án thật. **Không** thêm `spring-boot-starter-web` của Servlet, `RestTemplate` hay token client đồng bộ.

### 7.4. application.yml

Tạo `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          machine:
            provider: machine-idp
            client-id: reactive-machine
            client-secret: ${LAB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: []
        provider:
          machine-idp:
            token-uri: https://localhost:9443/realms/learning/protocol/openid-connect/token

lab:
  token:
    trust-store: ${LAB_TOKEN_TRUSTSTORE:}
    trust-store-password: ${LAB_TOKEN_TRUSTSTORE_PASSWORD:}
```

Với `client_credentials`, chỉ cần token URI đúng; không cần authorization URI, callback, login page hoặc OIDC issuer discovery trong ví dụ này. Việc bỏ `issuer-uri` có chủ đích: tránh tạo thêm HTTP discovery cần TLS trong giai đoạn application startup. **Nếu dùng OIDC login thật**, issuer discovery/JWK/userinfo cũng cần trust policy đúng; chỉ cấu hình WebClient của token endpoint không tự cấu hình toàn bộ outbound HTTP clients khác.

`scope: []` là lựa chọn demo để IdP cấp scope mặc định theo client; Keycloak có thể tự thêm scopes theo cấu hình realm. Trong production, định nghĩa scopes được cấp tối thiểu và dùng đúng audience/permission mapping.

`LAB_CLIENT_SECRET` bắt buộc là secret thật của client Keycloak. `LAB_TOKEN_TRUSTSTORE` và password chỉ phục vụ custom CA. Nếu để truststore trống, Java/Netty sẽ dùng trust anchors mặc định; với self-signed cert ở lab sẽ không tin cậy, đúng theo nguyên tắc fail-closed.

### 7.5. TokenTlsApplication.java

Tạo `src/main/java/example/TokenTlsApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails
        .MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
public class TokenTlsApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenTlsApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/ops/token-check").hasRole("OPS")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("ops")
                .password("{noop}lab-only")
                .roles("OPS")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
```

`/ops/token-check` là **endpoint demo có bảo vệ HTTP Basic**. Không để nó public để user tùy ý gây tải Token Endpoint. `{noop}lab-only` chỉ phục vụ lab localhost; ứng dụng thật cần password encoder, HTTPS cho inbound HTTP, authorization nghiêm ngặt và rate limits hoặc không triển khai endpoint này.

### 7.6. TokenClientConfig.java — phần trọng tâm

Tạo `src/main/java/example/TokenClientConfig.java`:

```java
package example;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;

import javax.net.ssl.TrustManagerFactory;

import io.netty.channel.ChannelOption;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client
        .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
        .ClientCredentialsReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
        .InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.endpoint
        .OAuth2ClientCredentialsGrantRequest;
import org.springframework.security.oauth2.client.endpoint
        .ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
        .WebClientReactiveClientCredentialsTokenResponseClient;
import org.springframework.security.oauth2.client.registration
        .ReactiveClientRegistrationRepository;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
public class TokenClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider tokenConnectionPool() {
        return ConnectionProvider.builder("oauth-token-pool")
                .maxConnections(10)
                .pendingAcquireMaxCount(30)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .maxIdleTime(Duration.ofSeconds(30))
                .build();
    }

    @Bean
    WebClient tokenEndpointWebClient(
            ConnectionProvider tokenConnectionPool,
            @Value("${lab.token.trust-store:}") String trustPath,
            @Value("${lab.token.trust-store-password:}") String trustPass)
            throws Exception {

        SslContextBuilder sslBuilder = SslContextBuilder.forClient();

        if (!trustPath.isBlank()) {
            KeyStore store = KeyStore.getInstance("PKCS12");

            try (InputStream input =
                    Files.newInputStream(Path.of(trustPath))) {
                store.load(input, trustPass.toCharArray());
            }

            TrustManagerFactory trustManager =
                    TrustManagerFactory.getInstance(
                            TrustManagerFactory.getDefaultAlgorithm());
            trustManager.init(store);
            sslBuilder.trustManager(trustManager);
        }

        // Khai báo trust anchors; KHÔNG disable certificate
        // validation hay hostname verification.
        SslContext sslContext = sslBuilder.build();

        HttpClient netty = HttpClient.create(tokenConnectionPool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
                .responseTimeout(Duration.ofSeconds(4))
                .followRedirect(false)
                .secure(ssl -> ssl
                        .sslContext(sslContext)
                        .handshakeTimeout(Duration.ofSeconds(4)));

        return WebClient.builder()
                .clientConnector(new ReactorClientHttpConnector(netty))
                .build();
    }

    @Bean
    ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>
            clientCredentialsTokenResponseClient(
                    WebClient tokenEndpointWebClient) {

        var delegate =
                new WebClientReactiveClientCredentialsTokenResponseClient();

        // Giữ converter/form encoding và OAuth2 error parsing
        // mặc định của Spring Security.
        delegate.setWebClient(tokenEndpointWebClient);

        // Deadline bao trùm chính token exchange publisher.
        return request -> delegate.getTokenResponse(request)
                .timeout(Duration.ofSeconds(9));
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>
                    clientCredentialsTokenResponseClient) {

        var provider =
                new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(
                clientCredentialsTokenResponseClient);

        var store = new InMemoryReactiveOAuth2AuthorizedClientService(
                registrations);

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, store);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

**Giải thích từng lớp cấu hình:**

1. `ConnectionProvider` chỉ cho tối đa 10 connections tới token HTTP client, 30 requests đợi, tối đa 1 giây chờ pool slot. Tùy workload, số này phải benchmark, không có một giá trị tốt cho mọi ứng dụng.
2. `SslContextBuilder.forClient()` giữ trust policy mặc định khi `trustPath` rỗng. Khi có đường dẫn file `PKCS12`, dùng `TrustManagerFactory` để xác minh server cert theo trust anchors đã import.
3. Không dùng `InsecureTrustManagerFactory`, không tắt hostname verification. Overload `HttpClient.secure(Consumer)` của Reactor Netty được thiết kế áp dụng hostname verification theo mặc định; hãy test mismatch tại môi trường thật.
4. `CONNECT_TIMEOUT_MILLIS` là timeout dựng TCP; `handshakeTimeout` là timeout TLS; `responseTimeout` giới hạn response; `pendingAcquireTimeout` là thời gian chờ pool.
5. `followRedirect(false)` giúp HTTP token request không tự động gửi credentials qua redirect ngoài ý định. Nếu token endpoint được cấu hình lệch sang 302, coi đó là lỗi cấu hình/provider, không tự follow sang domain khác.
6. `WebClient.builder().clientConnector(...)` tạo WebClient **dành riêng token endpoint**, không phải toàn bộ business HTTP calls.
7. `WebClientReactiveClientCredentialsTokenResponseClient` giữ cách mã hóa `application/x-www-form-urlencoded`, Basic client authentication và OAuth2 response/error parsing của Spring Security.
8. `setWebClient(tokenEndpointWebClient)` nối connector HTTPS/timeout vào đúng thành phần gửi POST.
9. `getTokenResponse(request).timeout(9s)` là deadline cho **full publisher token exchange**, không chỉ đến lúc nhận response headers.
10. `ClientCredentialsReactiveOAuth2AuthorizedClientProvider.setAccessTokenResponseClient(...)` chứng minh wiring thực sự dùng token client mới.
11. `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` hoạt động ở **service/background tier không cần ServerWebExchange**. Nó khác `DefaultReactiveOAuth2AuthorizedClientManager` dùng cho context web.
12. `InMemoryReactiveOAuth2AuthorizedClientService` chỉ hợp với lab/ứng dụng đơn instance. Với production đa node, cân nhắc storage phù hợp, token cache/rotation và risk; đừng mặc định mỗi instance gọi IdP riêng vô hạn.

**Không thêm `.retryWhen(...)` vào mọi `getTokenResponse` trong lab.** Phải thiết kế retry riêng theo lỗi/grant/provider, có time budget và tránh replay, không biến availability workaround thành thay đổi semantics OAuth2.

### 7.7. TokenProbeController.java — không trả access token

Tạo `src/main/java/example/TokenProbeController.java`:

```java
package example;

import java.util.Map;
import java.util.concurrent.TimeoutException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.client
        .OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class TokenProbeController {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public TokenProbeController(
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/ops/token-check")
    public Mono<ResponseEntity<Map<String, String>>> check() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("machine")
                        .principal("service-probe")
                        .build();

        return manager.authorize(request)
                .map(client -> ResponseEntity.ok(
                        Map.of(
                                "status", "authorized",
                                "expiresAt", String.valueOf(
                                        client.getAccessToken()
                                                .getExpiresAt()))))
                .switchIfEmpty(Mono.just(
                        ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                                .body(Map.of(
                                        "status", "no_authorized_client"))))
                .onErrorResume(TimeoutException.class, error ->
                        Mono.just(ResponseEntity
                                .status(HttpStatus.GATEWAY_TIMEOUT)
                                .body(Map.of("status", "token_timeout"))))
                .onErrorResume(OAuth2AuthorizationException.class, error ->
                        Mono.just(ResponseEntity
                                .status(HttpStatus.BAD_GATEWAY)
                                .body(Map.of(
                                        "status", "oauth2_rejected",
                                        "code", safeCode(
                                                error.getError()
                                                        .getErrorCode())))))
                .onErrorResume(Exception.class, error ->
                        Mono.just(ResponseEntity
                                .status(HttpStatus.SERVICE_UNAVAILABLE)
                                .body(Map.of(
                                        "status", "token_endpoint_unavailable"))));
    }

    private static String safeCode(String providerCode) {
        return switch (providerCode) {
            case "invalid_client" -> "invalid_client";
            case "invalid_scope" -> "invalid_scope";
            case "invalid_grant" -> "invalid_grant";
            case "unauthorized_client" -> "unauthorized_client";
            default -> "oauth2_token_error";
        };
    }
}
```

**Tại sao dùng principal `service-probe`?** Ở `client_credentials`, manager sử dụng principal key để lưu/tra authorized client. Đây là một key **nội bộ cố định** cho service, không phải user đang đăng nhập OAuth2. Đặt ngẫu nhiên mỗi request sẽ tạo nhiều cache keys và gây token churn.

**HTTP 502/503/504 ở demo là quyết định của ứng dụng**, không phải ánh xạ OAuth2 bắt buộc:
- `502 Bad Gateway` khi provider trả OAuth2 rejection và app đóng vai trò phụ thuộc vào IdP;
- `503 Service Unavailable` khi transport/TLS/connection lỗi không phân loại thêm;
- `504 Gateway Timeout` khi token deadline bị vượt;
- `200` khi đã có authorized client còn hạn.

Trong ứng dụng thực, nhiều lỗi cấu hình dài hạn như `invalid_client` nên tạo alert vận hành thay vì client retry. Không để caller bên ngoài dùng endpoint này để dò trạng thái/secret của IdP. Có thể bỏ endpoint này và kiểm token qua metrics + chính business service.

**Không hiển thị:** `client.getAccessToken().getTokenValue()`. Ngay cả endpoint có role OPS cũng không nên trả token thô; nó là credential truy cập tài nguyên khác.

### 7.8. Tạo HTTPS certificate và truststore lab

Ví dụ Linux/macOS với OpenSSL và JDK 17+ đã cài; tạo chứng chỉ self-signed có **SAN cho localhost**:

```bash
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/key.pem \
  -out tls/cert.pem \
  -days 7 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

**Tuyệt đối không dùng key.pem của lab trong production.** Nó là private key, hãy giới hạn filesystem permissions và không commit.

Import public certificate vào truststore dành cho **Client WebFlux**:

```bash
keytool -importcert -noprompt \
  -alias keycloak-local \
  -file tls/cert.pem \
  -keystore tls/truststore.p12 \
  -storetype PKCS12 \
  -storepass changeit
```

- `tls/cert.pem` là chứng chỉ public để tin cậy trong lab.
- `tls/key.pem` là **private key của Keycloak TLS server**, chỉ mount vào container.
- `tls/truststore.p12` không chứa private key trong bước import này.
- `changeit` là mật khẩu lab, **không** là password khuyến nghị production.
- Trên Windows PowerShell, viết lệnh OpenSSL/keytool trên một dòng hoặc dùng cú pháp continuation của PowerShell, không copy dấu `\` của bash.

### 7.9. Chạy Keycloak qua HTTPS

Từ thư mục dự án có `tls/cert.pem`/`tls/key.pem`:

```bash
docker run --rm --name keycloak-token-lab \
  -p 127.0.0.1:9443:8443 \
  -v "$PWD/tls/cert.pem:/opt/keycloak/conf/lab-cert.pem:ro" \
  -v "$PWD/tls/key.pem:/opt/keycloak/conf/lab-key.pem:ro" \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev \
  --hostname=https://localhost:9443 \
  --https-port=8443 \
  --https-certificate-file=/opt/keycloak/conf/lab-cert.pem \
  --https-certificate-key-file=/opt/keycloak/conf/lab-key.pem
```

- Host chỉ xuất port 9443 trên `127.0.0.1`; backend app chạy 8080.
- Keycloak listen HTTPS nội bộ cổng 8443, mapped ra host 9443.
- `--hostname=https://localhost:9443` giúp Keycloak tạo URLs khớp issuer/public host.
- Keycloak `start-dev` có defaults dành cho phát triển, **không** dùng production.
- Nếu Docker trên Windows không mount `$PWD` đúng path theo shell đang dùng, thay bằng absolute host path phù hợp; chỉ cần bảo đảm hai file PEM đã mount là file thật và server đọc được.

Mở `https://localhost:9443/admin/`. Browser có thể báo certificate self-signed chưa tin cậy; lab vẫn có thể mở để cấu hình, nhưng **không** dùng phương pháp “ignore TLS cert” cho Spring OAuth2 HTTP client. WebFlux sẽ tin đúng certificate qua truststore đã tạo.

### 7.10. Tạo realm và confidential service client

Trong Keycloak Admin Console:

1. Đăng nhập admin lab.
2. Tạo realm `learning`.
3. Trong realm này, chọn **Clients → Create client**, loại OpenID Connect.
4. Đặt **Client ID = reactive-machine**.
5. Bật **Client authentication** (confidential client).
6. Cho phép **Service accounts roles** (service account / client credentials). Trên Keycloak mới, chức năng này nằm trong capability flow/settings.
7. Không cần Standard flow/authorization code cho bài client credentials. Có thể tắt các grant không cần trong client lab.
8. Vào tab **Credentials**, lấy client secret. Đặt biến môi trường `LAB_CLIENT_SECRET` cho Spring, không copy vào source/repository.
9. Nếu cần token có resource-specific scope/audience, cấu hình client scopes và service account roles đúng theo Keycloak; không trao admin realm permissions cho client lab.
10. Token endpoint của realm là:

```text
https://localhost:9443/realms/learning/protocol/openid-connect/token
```

Có thể kiểm TLS và endpoint tồn tại bằng:

```bash
curl -sS --cacert tls/cert.pem \
  -o /dev/null \
  -w "token endpoint HTTP=%{http_code}\n" \
  https://localhost:9443/realms/learning/protocol/openid-connect/token
```

GET token endpoint có thể trả 405 hoặc 400 vì cần POST. Mục đích của lệnh là xác minh **certificate/hostname/TCP**, không xác minh cấp token thành công.

Kiểm POST client credentials mà **không in token body** (chỉ lab):

```bash
curl -sS --cacert tls/cert.pem \
  -o /dev/null \
  -w "token POST HTTP=%{http_code}\n" \
  -u "reactive-machine:$LAB_CLIENT_SECRET" \
  -d "grant_type=client_credentials" \
  https://localhost:9443/realms/learning/protocol/openid-connect/token
```

Nếu shell đã đặt `LAB_CLIENT_SECRET` đúng và Keycloak client cho phép service accounts, status kỳ vọng 200. **Hạn chế** của `curl -u`: credential có thể đi qua command history/process inspection tùy shell. Lệnh chỉ dành lab local; production dùng secret manager và credential handling phù hợp, không dùng command line raw secret.

### 7.11. Chạy WebFlux app

Linux/macOS:

```bash
export LAB_CLIENT_SECRET='replace-with-keycloak-client-secret'
export LAB_TOKEN_TRUSTSTORE="$PWD/tls/truststore.p12"
export LAB_TOKEN_TRUSTSTORE_PASSWORD='changeit'

gradle bootRun
```

Trên Windows PowerShell, đặt các biến tương đương:

```powershell
$env:LAB_CLIENT_SECRET = "replace-with-keycloak-client-secret"
$env:LAB_TOKEN_TRUSTSTORE = "C:\path\to\tls\truststore.p12"
$env:LAB_TOKEN_TRUSTSTORE_PASSWORD = "changeit"

gradle bootRun
```

Giá trị `C:\path\to\tls\truststore.p12` là **ví dụ đường dẫn cần thay bằng đường dẫn thật**. Dự án có Gradle Wrapper dùng `./gradlew bootRun` hoặc `gradlew.bat bootRun`.

**Quan trọng:** Nếu Spring Boot chạy **trong một container khác**, `https://localhost:9443` của nó không phải Keycloak trên host. Khi đó cần DNS/network/container ports thích hợp, và certificate SAN/hostname phải khớp token URI mà Client thật gọi.

### 7.12. Gọi endpoint kiểm tra

```bash
curl -i http://localhost:8080/ops/token-check

curl -i -u ops:lab-only \
  http://localhost:8080/ops/token-check
```

- Không credentials: **401 Basic challenge** từ Spring Security inbound.
- Ops demo đúng: backend gọi manager lấy token nếu chưa cache và trả response **không chứa token**.
- Body ví dụ sau khi thành công:

```json
{
  "status": "authorized",
  "expiresAt": "2026-11-07T09:00:00Z"
}
```

**Thời điểm expiresAt chỉ là ví dụ định dạng**, giá trị thực phụ thuộc token TTL/đồng hồ khi chạy. Không cố so timestamp tuyệt đối trong unit tests.

Nếu provider không hoạt động, token request có thể kết thúc bằng:
- 502 + `{"status":"oauth2_rejected","code":"invalid_client"}` cho OAuth2 error đã được Spring phân loại;
- 503 + `{"status":"token_endpoint_unavailable"}` cho TLS/connect/network failures;
- 504 + `{"status":"token_timeout"}` cho deadline timeout;
- 502 + `{"status":"no_authorized_client"}` nếu manager hoàn thành rỗng.

Status mapping trong controller là **contract demo**, không phải mặc định của Spring Security hay RFC 6749.

### 7.13. Quan sát cache

Gọi `/ops/token-check` hai lần liên tiếp. Manager dùng principal key `service-probe` và service lưu authorized client, nên lần sau **có thể tái sử dụng access token chưa expired**, không nhất thiết POST Token Endpoint lại.

Muốn thử timeout hoặc invalid-client bằng Keycloak thật, cần kích hoạt lại token acquisition trong **lab**: restart ứng dụng (xóa in-memory authorized-client cache), đợi token hết hạn hoặc tạo test setup kiểm soát cache. Đừng tưởng sửa secret là mọi request sau lập tức gọi Token Endpoint nếu cache vẫn có token hợp lệ.

Trong production, refresh/caching phải đồng bộ giữa nhiều instances theo chính sách, tránh token stampede. Token expiration clock skew thường khiến client xin token sớm hơn exp, điều cần thiết tránh gửi token gần hết hạn tới API.

## 8. Kiểm thử bằng WebTestClient — HTTP error contract

Để test 200/401/502/503/504 **không phụ thuộc Keycloak đang chạy**, có thể mock `ReactiveOAuth2AuthorizedClientManager`. Việc này kiểm **controller và inbound Spring Security**, không chứng minh truststore/TLS thật; TLS sẽ được test riêng ở mục 9.

Tạo `src/test/java/example/TokenProbeControllerTests.java`:

```java
package example;

import java.time.Instant;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration
        .ClientRegistration;
import org.springframework.security.oauth2.core
        .AuthorizationGrantType;
import org.springframework.security.oauth2.core
        .OAuth2AccessToken;
import org.springframework.security.oauth2.core
        .OAuth2AuthorizationException;
import org.springframework.security.oauth2.core
        .OAuth2Error;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class TokenProbeControllerTests {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveOAuth2AuthorizedClientManager manager;

    @Test
    void missingInboundCredentialsIs401() {
        client.get().uri("/ops/token-check")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authorizedResponseDoesNotExposeRawToken() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.just(testAuthorizedClient()));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("authorized")
                .jsonPath("$.access_token").doesNotExist();
    }

    @Test
    void tokenDeadlineMapsTo504() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.error(
                        new TimeoutException("token request timed out")));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isEqualTo(504)
                .expectBody()
                .jsonPath("$.status").isEqualTo("token_timeout");
    }

    @Test
    void invalidClientMapsTo502WithoutSecret() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.error(
                        new OAuth2AuthorizationException(
                                new OAuth2Error(
                                        "invalid_client",
                                        "secret must not be echoed",
                                        null))));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isEqualTo(502)
                .expectBody()
                .jsonPath("$.code").isEqualTo("invalid_client");
    }

    @Test
    void transportFailureMapsTo503() {
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
                .thenReturn(Mono.error(
                        new IllegalStateException("simulated TLS failure")));

        client.get().uri("/ops/token-check")
                .headers(h -> h.setBasicAuth("ops", "lab-only"))
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody()
                .jsonPath("$.status")
                .isEqualTo("token_endpoint_unavailable");
    }

    private static OAuth2AuthorizedClient testAuthorizedClient() {
        ClientRegistration registration =
                ClientRegistration.withRegistrationId("machine")
                        .clientId("test-client")
                        .clientSecret("test-secret")
                        .authorizationGrantType(
                                AuthorizationGrantType.CLIENT_CREDENTIALS)
                        .tokenUri("https://localhost:9443/token")
                        .build();

        OAuth2AccessToken token =
                new OAuth2AccessToken(
                        OAuth2AccessToken.TokenType.BEARER,
                        "TOKEN_ONLY_FOR_UNIT_TEST",
                        Instant.now(),
                        Instant.now().plusSeconds(600));

        return new OAuth2AuthorizedClient(
                registration, "service-probe", token);
    }
}
```

Chạy:

```bash
gradle test
```

**Lưu ý test framework:** `@MockBean` nằm trong Spring Boot 3.3.x và giúp thay manager bean trong test context. Ở các phiên bản Boot mới hơn, cách mock bean có thể thay đổi/được deprecate; test phải được cập nhật theo version thực, không copy annotation một cách vô thức.

**Test kiểm được:**
- Endpoint vận hành không public (401).
- Khi token được cấp, app chỉ trả metadata, không trả raw token.
- `TimeoutException` được chuyển sang 504.
- `OAuth2AuthorizationException` với code `invalid_client` được chuyển sang 502, không echo provider description.
- Lỗi transport tổng quát tạo 503, không làm HTTP 200 giả.

**Không chứng minh được bằng mock:**
- Truststore thật được đọc và certificate chain hợp lệ;
- Hostname verification đang bật;
- Reactor Netty connect/response timeout hoạt động dưới mạng thật;
- Provider mã hóa/parse OAuth2 response đúng;
- Client secret Basic POST thật;
- Retry semantics hoặc cache khi grant đang hết hạn.

Các điểm đó cần test transport/integration riêng.

## 9. Kiểm thử TLS và timeout thực tế

### 9.1. Positive TLS test

Với Keycloak HTTPS và truststore như mục 7:

1. `curl --cacert tls/cert.pem` tới token endpoint phải hoàn tất TLS handshake.
2. Spring Boot khởi động với `LAB_TOKEN_TRUSTSTORE` đúng.
3. Gọi `/ops/token-check` lần đầu → 200 authorized nếu client/secret đúng.
4. Kiểm Keycloak logs/metrics (đã redact): có token request, không có certificate failure.
5. Gọi lại → có thể lấy token cache, không bắt buộc token endpoint POST lần hai.

### 9.2. CA không tin cậy

Để test fail-closed trong **lab**:

- Chạy Spring với một truststore khác không chứa CA/cert của Keycloak, hoặc không set truststore custom.
- Restart app để xóa in-memory cached token.
- Gọi `/ops/token-check`.
- Kỳ vọng request không authorize; controller có thể trả 503 do TLS handshake/PKIX error.

**Không** sửa bằng `InsecureTrustManagerFactory.INSTANCE`. Sửa truststore thật là giải pháp an toàn.

### 9.3. Hostname mismatch

Lab certificate SAN chỉ có `localhost`/`127.0.0.1`. Nếu dùng host alias không có trong SAN (ví dụ `keycloak.internal.test`) và DNS trỏ về cùng IP nhưng cert không chứa alias, TLS hostname verification phải **từ chối**. Đây là phép thử quan trọng để không nhầm "truststore chứa cert" với "chấp nhận mọi hostname".

### 9.4. TCP connect timeout và DNS failure

Thay token URI trong profile test thành HTTPS host/port không mở hoặc không thể kết nối, restart app, gọi endpoint:
- Connection refused có thể fail ngay, **không phải** timeout.
- Network drop có thể chờ `CONNECT_TIMEOUT_MILLIS` và phát error.
- DNS failure có error riêng; deadline 9s giúp tránh đợi vô hạn trong token publisher.

**Không** cố tạo điều kiện lỗi mạng bằng cách chặn network production hay gửi traffic tới public host không thuộc quyền. Dùng mock proxy, container network hoặc test environment riêng.

### 9.5. Response timeout

Dùng một controlled HTTPS test server (WireMock/MockWebServer/MockServer hỗ trợ TLS, hoặc IdP test) trì hoãn body/response để vượt `responseTimeout(4s)`. Kiểm:
- Error path phát và caller không nhận access token.
- Overall `timeout(9s)` bao trùm thời gian token exchange.
- Không có retry tự động làm vượt deadline, nếu test bật retry phải ghi rõ.
- Connection pool không bị giữ vô hạn sau khi cancel/error.

Không dùng raw HTTP stub để kết luận đã test **certificate validation**; nếu stub không có TLS/CA thật, chỉ kiểm timeout/payload parsing.

### 9.6. Pool overload

Dùng load test có giới hạn trong lab để tạo nhiều token requests đồng thời. Với `maxConnections(10)`, `pendingAcquireMaxCount(30)`, `pendingAcquireTimeout(1s)`, một số request có thể fail pool acquire **trước** khi tới Token Endpoint. Đây không phải `invalid_client` và không nên kích hoạt rotation secret.

Cân nhắc single-flight token refresh/cache để tránh hàng chục request token cùng lúc. Khi test race, đảm bảo token cache không che thực tế traffic; có thể dùng explicit test token client thay vì manager đã cache.

### 9.7. Test OAuth2 error response

Dùng IdP test:
- Sai client secret → `invalid_client`.
- Client thiếu quyền grant → `unauthorized_client`.
- Sai scope → `invalid_scope` theo provider.
- Quota 429 → cần phân biệt với lỗi auth.
- Trả JSON lỗi đúng kiểu → parser của token client phải phát error, không tạo `OAuth2AuthorizedClient`.
- Trả HTTP 200 nhưng body thiếu access token → phải lỗi parse/protocol, không được coi thành công.
- Provider trả HTML 502 → không log HTML raw nếu chứa thông tin nội bộ.

**Không dựa vào chính xác exception class của mọi provider mà chưa test**, vì Spring Security có thể wrap protocol error/HTTP error khác nhau giữa các versions.

## 10. Tùy biến các grant khác

### 10.1. Authorization Code token client

Nếu ứng dụng WebFlux hỗ trợ `oauth2Login` hoặc authorization code, class phù hợp:

```java
// MẢNH MINH HỌA, không phải bean ghép vào
// demo client_credentials ở mục 7.
@Bean
ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
        authorizationCodeTokenResponseClient(
                WebClient tokenEndpointWebClient) {

    var client = new WebClientReactiveAuthorizationCodeTokenResponseClient();
    client.setWebClient(tokenEndpointWebClient);

    return request -> client.getTokenResponse(request)
            .timeout(Duration.ofSeconds(9));
}
```

Imports trong mảnh này:
```java
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
```

Từ Spring Security 6.3+, công bố bean generic đúng grant giúp framework autoconfigure token client. Tuy nhiên **khi tự tạo `ReactiveOAuth2AuthorizedClientManager`/`authenticationManager` hoặc custom `SecurityWebFilterChain` sâu**, bạn phải chắc chắn nó thật sự dùng bean mới. Nếu không, tùy biến chỉ tồn tại dưới dạng một bean không được gọi.

Với `oauth2Login` và customization bằng DSL trực tiếp, cần bảo đảm wiring ảnh hưởng cả `OidcAuthorizationCodeReactiveAuthenticationManager` và `OAuth2LoginReactiveAuthenticationManager` khi thích hợp. **Không** thay đổi grant type/flow chỉ để dùng chung một timeout.

### 10.2. Refresh Token token client

```java
// MẢNH MINH HỌA, dùng trong ứng dụng có refresh_token.
@Bean
ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
        refreshTokenResponseClient(WebClient tokenEndpointWebClient) {

    var client = new WebClientReactiveRefreshTokenTokenResponseClient();
    client.setWebClient(tokenEndpointWebClient);

    return request -> client.getTokenResponse(request)
            .timeout(Duration.ofSeconds(9));
}
```

Imports tương ứng:
```java
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
```

**Cảnh báo:** Refresh-token rotation có thể khiến retry request sau timeout bị từ chối. Không thêm `retryWhen(Retry.max(5))` vào wrapper mà chưa xác định chính sách provider và idempotency.

### 10.3. Có nên dùng một WebClient chung?

Có thể dùng cùng HTTP connector/trust policy cho nhiều token response clients nếu **đều gọi các endpoints cùng trust boundary**. Nhưng:
- Các IdP khác nhau có CA/mTLS/proxy/timeouts khác nhau.
- Dùng WebClient chung với resource API có thể làm request/token traffic cạnh tranh pool hoặc áp timeout sai.
- Truststore cấp doanh nghiệp rộng có thể tăng bề mặt tin cậy nếu cần chỉ trust một CA.
- Chỉ dùng một pool cho token endpoint và userinfo/JWK/discovery có thể gây head-of-line contention.

Đối với đa provider, thiết kế theo registration/provider-specific routing và trust policy, có tests đúng hostname; không sử dụng **một** `InsecureTrustManager` để “chạy được với mọi IdP”.

### 10.4. Client authentication methods

Các cách phổ biến:

| Method | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| `client_secret_basic` | Client ID/secret qua HTTP Basic tại token request | Mặc định hỗ trợ, phải HTTPS |
| `client_secret_post` | Secret trong form POST | Có thể hợp lệ nhưng rủi ro logs/body; dùng khi provider yêu cầu |
| `private_key_jwt` | Client assertion ký bằng private key | Cần bảo vệ key, ký đúng audience/time/jti |
| `tls_client_auth` / mTLS | Chứng thư client tại TLS / OAuth client auth policy | Thêm client key material và IdP config |
| `none` | Public client không có secret | Cần PKCE cho authorization code; không dùng để giả confidential service |

**Đừng coi việc tự gửi một header `Authorization: Bearer ...` tới token endpoint là client authentication cho grant client_credentials.** OAuth2 Client Registration và provider quyết định phương thức client authentication.

## 11. Proxy doanh nghiệp, DNS và TLS termination

Một doanh nghiệp có thể yêu cầu HTTPS token traffic đi qua HTTP CONNECT proxy:

```text
WebFlux OAuth2 client
    |
    | HTTPS CONNECT
    v
Corporate proxy
    |
    v
Authorization Server HTTPS
```

Reactor Netty `HttpClient.proxy(...)` hỗ trợ cấu hình ProxyProvider khi cần. Cấu hình tùy proxy type/credentials và bypass list; phải test rằng TLS **đầu cuối** vẫn xác minh certificate của Authorization Server, không vô tình tin CA không được phê duyệt.

**Chú ý TLS-inspecting proxy:** Nếu proxy doanh nghiệp thực hiện TLS interception, certificate mà client nhận có thể do enterprise CA ký. Chỉ cài enterprise CA sau khi có policy phê duyệt và kiểm tra hostname vẫn đúng. Không dùng insecure trust manager để “sửa” network.

Nếu IdP dùng private DNS hoặc Kubernetes service hostname, URI `https://auth.svc.cluster.local` phải khớp SAN/issuer/network policy. Nếu công khai issuer `https://login.example.com` nhưng backend token URI dùng một hostname nội bộ khác, cần xác định tác động tới token endpoint, OIDC discovery, ID Token `iss` và chứng chỉ; không bỏ issuer/hostname verification.

**Redirect token endpoint:** HTTP 302 từ một token endpoint thường bất thường. `followRedirect(false)` giúp tránh gửi Basic client credentials ra host khác; xử lý endpoint sai tại cấu hình và IdP/proxy, không auto-follow mọi redirect.

## 12. Retry, circuit breaker và lỗi từ nhiều người gọi

### 12.1. Bảng quyết định retry

| Tình huống | Khuyến nghị mặc định |
| --- | --- |
| `invalid_client` / `invalid_scope` / `unauthorized_client` | Không retry; alert cấu hình/secret/permission |
| Certificate invalid/hostname mismatch | Không retry; sửa PKI/hostname |
| DNS NXDOMAIN/URL sai | Không retry liên tục; sửa DNS/config |
| Authorization code `invalid_grant` | Không dùng lại code; bắt đầu flow mới |
| Rotating refresh token timeout | Không retry mù quáng; xem contract/provider |
| `client_credentials` 429 | Retry rất hạn chế nếu policy cho phép, tôn trọng `Retry-After` |
| `client_credentials` 503/transient network | Có thể retry có điều kiện, giới hạn tổng deadline |
| Pool acquire timeout do quá tải nội bộ | Giảm concurrency/cải thiện cache, không tăng retry |
| Token endpoint phản hồi 200 nhưng payload sai | Fail-closed, alert provider/schema; không tạo token |

Một chiến lược retry có thể dùng `Retry.backoff(maxRetries, backoff)`, `jitter`, lọc **chính xác** lỗi được phép và giới hạn time budget. Nhưng cần thử với provider thật hoặc IdP stub, không áp dụng trực tiếp cho authorization code/refresh token.

**Ví dụ nguy hiểm:**

```java
// SAI: retry mọi lỗi cho mọi grant.
return tokenResponseClient.getTokenResponse(request)
        .retryWhen(Retry.max(10));
```

Nó có thể replay code, spam invalid credentials, vượt quota hoặc tạo sự cố cascading.

### 12.2. Circuit breaker

Khi IdP đã lỗi, cần giảm request đến nó để tránh bão. Có thể dùng circuit breaker/bulkhead riêng cho token exchange:
- State CLOSED cho request bình thường.
- OPEN trả lỗi nhanh trong một khoảng ngắn khi tỷ lệ lỗi vượt ngưỡng.
- HALF_OPEN thăm dò rất ít request.

Không biến circuit breaker OPEN thành **ALLOW** hoặc phát token giả. Nếu có token đã lấy còn hợp lệ, manager có thể dùng token được cache theo policy, nhưng không dùng token expired trái chuẩn. Nhớ rằng circuit breaker nên dựa trên **transport/availability**, không đếm mọi `invalid_client` như sự cố mạng.

### 12.3. Đồng hồ và token expiration

`OAuth2AuthorizedClient` chứa access token và thời điểm `expiresAt`. Provider thường sử dụng **clock skew** để xin token sớm hơn khi sắp hết hạn. Máy có sai lệch thời gian lớn có thể khiến token bị cho là expired quá sớm hoặc muộn. Cần đồng bộ NTP/clock, kiểm token TTL/issuer, không sửa bằng cách vô hiệu hóa expiry checks.

### 12.4. Thundering herd

Nếu 500 business requests phát hiện token hết hạn cùng lúc, chúng có thể đồng loạt yêu cầu token mới. Giải pháp có thể:
- cache token theo registration ID và service principal ổn định;
- single-flight/in-flight request sharing;
- rate limit ở token acquisition;
- short jittered refresh window;
- shared token cache phù hợp khi đa node, có kiểm soát secret/token storage;
- capacity planning với IdP.

**Chú ý:** Mọi cơ chế share/cache access token phải giữ đúng audience/scope/client/grant; không dùng token của một tenant/client cho tenant khác.

## 13. Observability và SLO

Metrics tối thiểu:

| Metric | Ý nghĩa |
| --- | --- |
| token_exchange_duration_seconds (p50/p95/p99) | Độ trễ từ subscription tới token response/error |
| token_acquisition_success_total | Bao nhiêu lần lấy token mới thành công |
| token_acquisition_error_total{category} | Lỗi OAuth2, TLS, DNS, connect, timeout, 429, 5xx |
| token_pool_pending_connections | Chờ pool có thể là bottleneck nội bộ |
| token_pool_active_connections | Connections đang sử dụng |
| token_cache_hit/miss | Bao nhiêu manager requests thực sự gọi token endpoint |
| token_client_credential_rotation | Secret rotation success/failure |
| auth_server_rate_limit_total | Bị IdP quota/throttle |
| resource_api_401_after_token | Token được cấp nhưng resource server từ chối |

Đừng dùng **raw client ID secret, token, URL có query nhạy cảm** làm metric labels. Label theo registration ID/provider alias trong allowlist, không theo email/user input với cardinality vô hạn.

### Tách latency budget

```text
Business request SLO 1500 ms
  |
  +-- Tác vụ nội bộ 600 ms
  +-- Resource Server API 600 ms
  +-- Dự phòng 300 ms
  |
  +-- Token cache hit: nhỏ (không exchange)
  +-- Token cache miss: token endpoint 9 s = quá SLO!
```

Nếu token miss có thể chậm 9s, một HTTP business request 1.5s sẽ không đáp ứng SLO; phải thiết kế theo cache, pre-warm, fail-fast, async job hoặc điều chỉnh deadline theo ứng dụng. Giá trị timeout 9s của bài lab **không** phù hợp cho mọi frontend latency SLO.

### Logging có ích nhưng an toàn

Nên log:

```text
traceId=... operation=oauth2_token_exchange
registrationId=machine outcome=timeout
durationMs=9012 stage=overall_deadline
```

Không log:

```text
Authorization: Basic ...
access_token=eyJ...
client_secret=...
code_verifier=...
```

Spring Security có thể ghi message/cause chứa URL hoặc response text. Cấu hình logging sanitizer/redaction trước khi đẩy vào centralized logging. Không bật full Reactor Netty wiretap ngoài test giả lập.

## 14. Checklist trước khi triển khai production

1. `token-uri` là **HTTPS URL cố định/được kiểm soát**, không lấy tùy ý từ request để tránh SSRF.
2. Certificate chain được xác minh theo CA đúng; **hostname verification** còn hoạt động.
3. Truststore/keystore được quản lý vòng đời, rotation và secret storage; không commit file private key.
4. Nếu mTLS, client keystore đúng alias/cert/key; phân biệt với client secret.
5. Có **pool limits**, pending queue cap, connect/handshake/response/overall deadlines.
6. Tách `WebClient` token endpoint khỏi resource/business HTTP khi cần trust/pool riêng.
7. Token client **được gắn thật vào provider/manager**, không chỉ tạo bean không dùng.
8. Test `invalid_client` và secret rotation, không retry lỗi cấu hình.
9. Test TLS không tin/hostname mismatch, không dùng insecure trust workaround.
10. Test slow response, pool contention, 429/503 và cancellation.
11. Không retry authorization code/refresh token bừa bãi; giới hạn retry theo grant.
12. Không trả raw token/secret trong endpoint kiểm tra, logs, trace, metrics.
13. Resource Server vẫn kiểm access token audience/scope; token acquisition success không bảo đảm API 200.
14. Giữ authorized client cache đúng theo grant/registration/principal, không sinh key ngẫu nhiên.
15. Có metrics p95/p99, error rate, cache miss và circuit breaker đúng loại lỗi.
16. Kiểm nhiều providers/tenants với distinct CA/hostname/permissions khi cần.
17. Server công khai có HTTPS cho inbound, authentication/authorization và rate limiting; lab Basic/noop không dùng production.
18. Có test E2E qua proxy/ingress đúng TLS trust chain, không chỉ mock `WebClient`.
19. Khi nâng Spring Boot/Spring Security, xác minh lại reactive token response client API và lỗi được wrap.
20. Có chính sách fail-closed: không có token hợp lệ thì không dùng token hết hạn/giả để gọi API.

## 15. Câu hỏi tự kiểm tra

**1. Trong WebFlux OAuth2 Client, thành phần nào thực sự POST token request?**  
`ReactiveOAuth2AccessTokenResponseClient` cho grant tương ứng, ví dụ `WebClientReactiveClientCredentialsTokenResponseClient` dùng `WebClient` phía dưới.

**2. Tạo WebClient.Builder bean mặc định có chắc token response client dùng nó không?**  
Không. Phải nối đúng bằng `setWebClient(...)`/bean generic autoconfiguration hoặc provider/manager wiring.

**3. Vì sao không dùng InsecureTrustManagerFactory để sửa self-signed?**  
Vì nó bỏ xác minh certificate chain, mở rủi ro MITM và lộ client secret/token. Import CA/cert được phép vào truststore.

**4. Truststore và client keystore khác nhau thế nào?**  
Truststore xác minh server. Client keystore chứa certificate/private key của client khi mTLS.

**5. Chứng chỉ đã nằm trong truststore mà hostname vẫn mismatch, request nên thế nào?**  
Phải fail TLS; trust CA không thay thế hostname verification.

**6. pendingAcquireTimeout khác connect timeout gì?**  
Pending là chờ pool slot, connect là dựng kết nối TCP. Pool overload có thể làm lỗi trước khi gửi network request.

**7. responseTimeout có phải deadline toàn bộ OAuth2 token exchange không?**  
Không. Dùng thêm `Mono.timeout` quanh `getTokenResponse(...)` nếu cần giới hạn toàn bộ publisher.

**8. Timeout có nghĩa IdP chắc chắn chưa phát token không?**  
Không. Request có thể đã được xử lý nhưng response tới muộn/cancel.

**9. Có được retry authorization code sau timeout không?**  
Không retry mù quáng: code single-use và có thể đã tiêu thụ. Thường bắt đầu lại authorization flow.

**10. invalid_client có nên được retry 10 lần không?**  
Không; cần kiểm client ID/secret/auth method/permissions, tránh spam IdP.

**11. Token Endpoint trả 429 khác invalid_client chỗ nào?**  
429 thường là quota/overload, có thể có Retry-After; invalid_client là OAuth client authentication/config failure.

**12. Tại sao principal key ổn định quan trọng cho client_credentials?**  
Authorized client service dùng registration + principal để lưu token; key ngẫu nhiên mỗi request phá cache và tăng token calls.

**13. Client lấy được token nhưng Resource Server trả 403 nghĩa gì?**  
Token acquisition thành công không đồng nghĩa đủ quyền API. Cần kiểm audience/scope/roles/resource authorization.

**14. Trong Spring Security 6.3 có thể tùy chỉnh riêng token HTTP WebClient bằng bean nào?**  
Một `ReactiveOAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>` hoặc class token response client phù hợp grant với `setWebClient`.

**15. Vì sao token WebClient không nên tự follow 302 sang domain khác?**  
Để tránh chuyển client credentials/token request tới host ngoài ý định; token endpoint phải được cấu hình đúng.

**16. WebTestClient mock manager có chứng minh TLS cert hợp lệ không?**  
Không. Nó kiểm HTTP response contract/controller; cần E2E HTTPS Keycloak/truststore và negative TLS tests.

**17. Có được log body token response để debug 500 không?**  
Không. Body chứa access/refresh token. Chỉ log sanitized error category/status/trace ID.

**18. Nếu app chạy trong Docker, localhost:9443 có trỏ Keycloak host không?**  
Không nhất thiết. localhost của container là chính container; cần network hostname và SAN phù hợp.

**19. HTTP Basic ops:lab-only ở /ops/token-check có liên quan client_secret_basic tới Keycloak không?**  
Không. Basic vào Spring inbound endpoint bảo vệ demo; client_secret_basic là auth của OAuth2 machine client tại Token Endpoint.

**20. Token response sau khi hết hạn có được dùng tiếp khi IdP offline không?**  
Không mặc định. Access token hết hạn không còn hợp lệ; không “fail-open” bằng expired token.

**Ghi nhớ:** Tùy chỉnh **HTTPS + timeout + lỗi của Token Endpoint** phải làm tại **đúng reactive token response client**, dùng WebClient gắn Reactor Netty connector với TLS trust, hostname verification và pool/timeouts. Bao ngoài token response publisher bằng deadline; phân loại OAuth2 errors và transport failures; retry có giới hạn theo grant; giữ cache/metrics; không rò rỉ secrets. Trong service-to-service, `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` phù hợp vì không phụ thuộc `ServerWebExchange`.

## Tài liệu tham khảo

- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): ví dụ công bố `ReactiveOAuth2AccessTokenResponseClient` beans, custom `WebClient` cho token HTTP transport.
- [Spring Security — Reactive Authorization Grant Support](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): `client_credentials`, `authorization_code`, `refresh_token`, `setWebClient(...)`.
- [Spring Security — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html): `ReactiveOAuth2AuthorizedClientManager`, background service manager, provider/client service.
- [Spring Security — Client Authentication Support](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/client-authentication.html): `client_secret_basic`, token request credentials và các grant.
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/1.1.28/reference/index.html#http-client): TCP connect, TLS, SSL handshake, response timeout, pool, proxy.
- [Reactor Netty — HttpClient API](https://projectreactor.io/docs/netty/1.1.28/api/reactor/netty/http/client/HttpClient.html): `secure(Consumer)`, hostname verification và timeout.
- [Reactor Netty — ConnectionProvider API](https://projectreactor.io/docs/netty/1.1.28/api/reactor/netty/resources/ConnectionProvider.html): pool limits và acquire timeout.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): connectors, ExchangeStrategies, error handling.
- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java 17+ và Gradle support.
- [Keycloak — Configuring TLS](https://www.keycloak.org/server/enabletls): HTTPS certificates, port 8443.
- [Keycloak — Containers and Hostnames](https://www.keycloak.org/server/containers): Docker HTTPS and hostname configuration.
- [Keycloak — Docker Quickstart](https://www.keycloak.org/getting-started/getting-started-docker): realm/client/service accounts local setup.
- [OAuth 2.0 — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, client credentials grant, error response.
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): TLS, credential handling và bảo mật flow.
