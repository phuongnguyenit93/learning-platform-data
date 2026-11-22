# Xử lý cache-control, dữ liệu nhạy cảm và truyền token qua HTTPS

## 1. Vì sao bảo vệ Token Endpoint phải là một phần của thiết kế?

Trong **Spring Security OAuth2/OIDC Authorization Server**, **Token Endpoint** là nơi ứng dụng đổi một grant hợp lệ thành **access token**, đôi khi kèm **refresh token** hoặc **OIDC ID token**. Các giá trị này có thể cho phép truy cập API hoặc tiếp tục xin token, vì vậy một lỗi truyền thông, caching hay logging có thể nghiêm trọng ngay cả khi grant, chữ ký JWT và cơ chế xác thực client đều đúng.

Ví dụ: `orders-bff` sử dụng `client_credentials` qua `POST /oauth2/token`. Phản hồi HTTP 200 có một access token hợp lệ. Nếu CDN/reverse proxy cache phản hồi theo URL, hoặc ứng dụng ghi đầy đủ JSON response vào APM log, token có thể xuất hiện ở một nơi người khác đọc được. Nếu kết nối HTTPS chỉ tồn tại ở đoạn browser tới load balancer, còn đoạn chuyển tiếp chứa token về backend đi qua mạng không được tin cậy, mã thông báo cũng có thể bị lộ khi truyền.

Trong module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách **thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot**. Bài này thuộc chương **Token Endpoint** và tập trung ba trụ cột cần triển khai cùng nhau:

1. **Không lưu cache phản hồi nhạy cảm:** dùng `Cache-Control: no-store` và `Pragma: no-cache` theo OAuth 2.0.
2. **Không làm lộ credential/token:** kiểm soát log, trace, metric, exception, request body, header, backup, debugger và cách client lưu token.
3. **Bảo vệ đường truyền:** dùng **HTTPS/TLS**, xác thực máy chủ và bảo vệ cả những hop nội bộ sau proxy.

### Kết quả học tập

Sau bài học, bạn có thể:

- Giải thích chính xác yêu cầu từ **RFC 6749 §3.2, §5.1 và §5.2** đối với Token Endpoint và response chứa credential.
- Phân biệt `no-store`, `no-cache`, `max-age=0` với **thời hạn của token**.
- Thiết kế sơ đồ bảo vệ token từ client → gateway → Authorization Server → client → Resource Server.
- Giữ cấu hình header an toàn trong Spring Security/Spring Authorization Server và kiểm thử cả success/error response khi có extension.
- Tách các kịch bản rò rỉ: qua query URL, Basic auth, reverse proxy, logs/APM, JWT claims, browser storage và môi trường kiểm thử.
- Triển khai chứng cứ kiểm thử HTTPS, certificate validation, cache headers và cơ chế không lộ token trong vận hành nhiều instance.

**Phạm vi kỹ thuật:** ví dụ theo họ **Spring Authorization Server 1.5.x / Spring Security 6.x / Spring Boot 3.x**, với lưu ý đối chiếu API khi chuyển sang Spring Security 7.x. Các đoạn code minh họa có thể cần cấu hình client, khóa ký, session và database khác để trở thành dự án chạy đầy đủ.

## 2. Token Endpoint nằm ở đâu trong hệ thống?

Trong Spring Authorization Server, Token Endpoint mặc định thường có path **`/oauth2/token`**. Nó nhận yêu cầu cấp token bằng **HTTP POST**, thường với `Content-Type: application/x-www-form-urlencoded` và xác thực client theo phương thức được đăng ký. Token Endpoint là đường **back-channel** giữa OAuth client và Authorization Server, khác với browser redirect tới Authorization Endpoint.

```mermaid
flowchart LR
    B["Browser / user"] -->|"Authorization Code redirect"| RP["OAuth Client / BFF"]
    RP -->|"POST /oauth2/token<br/>grant + client authentication"| GW["TLS / Gateway / Reverse proxy"]
    GW -->|"Protected upstream channel"| AS["Spring Authorization Server<br/>OAuth2TokenEndpointFilter"]
    AS --> STORE[("RegisteredClientRepository<br/>OAuth2AuthorizationService")]
    AS --> GEN["OAuth2TokenGenerator<br/>JwtEncoder / key service"]
    AS -->|"Sensitive JSON response<br/>no-store / no-cache"| GW
    GW -->|"HTTPS response<br/>non-cacheable"| RP
    RP -->|"Authorization: Bearer access_token"| API["Resource Server API"]
```

**Ba chỗ cần giữ an toàn:** request mang grant hoặc secret; response mang token; request tiếp theo đến Resource Server mang access token. Không có một header hay một khóa JWT nào bảo vệ được tất cả nếu một trong ba đoạn bị lộ dữ liệu.

### 2.1. Những gì có thể xuất hiện trong request

| Grant/method | Credential hoặc dữ liệu nhạy cảm trong request Token Endpoint | Ghi chú |
| --- | --- | --- |
| `authorization_code` | Authorization code, `code_verifier`, redirect URI, client credentials (nếu confidential) | Code ngắn hạn, dùng một lần; `code_verifier` phải giữ bí mật tới lúc đổi code. |
| `refresh_token` | Refresh token, client authentication | Refresh token có thể xin access token mới; cần bảo vệ nghiêm ngặt. |
| `client_credentials` | Client secret, private-key JWT assertion hoặc client certificate theo method | Không có end user, nhưng access token được cấp cho chính client. |
| Device Code grant | `device_code`, `client_id` / client authentication | Không gửi nhầm `user_code` vào Token Endpoint. |
| Token Exchange (nếu bật) | `subject_token`, `actor_token` hoặc các credential khác | Có thể chứa token của một chủ thể khác; mức độ nhạy cảm cao. |

Các tham số này không phải thứ có thể in ra console vì “đang debug”. Dù đã URL-encode, **URL encoding không phải mã hóa bảo mật**.

### 2.2. Những gì có thể xuất hiện trong response

```http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_EXAMPLE_NOT_REAL",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

Nếu grant, client type và chính sách cho phép, response có thể có `refresh_token`. Khi xử lý một OIDC flow, response có thể có `id_token`. **Không phải response nào cũng chứa tất cả loại token**; nhưng chỉ cần một credential nhạy cảm là yêu cầu chống lưu cache đã có ý nghĩa.

## 3. Quy tắc chuẩn: Cache-Control và Pragma

### 3.1. RFC 6749 §5.1 yêu cầu gì?

RFC 6749 §5.1 nêu rằng Authorization Server **MUST** gửi hai response headers sau với các phản hồi có token, credential hoặc thông tin nhạy cảm:

```http
Cache-Control: no-store
Pragma: no-cache
```

Ý nghĩa:

- **`Cache-Control: no-store`:** yêu cầu các cache tuân thủ không lưu thông tin từ **request/response** vào cache. Đây là chỉ thị quan trọng nhất ngăn bản sao phản hồi chứa access/refresh token nằm ở browser/proxy cache.
- **`Pragma: no-cache`:** header tương thích với các HTTP/1.0 cache cũ. OAuth 2.0 vẫn yêu cầu gửi cùng với `Cache-Control`.

Spring Security có thể gửi giá trị cache control **mạnh hơn/chi tiết hơn**:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
```

Header như trên thỏa yêu cầu OAuth vì có **chỉ thị `no-store`** và `Pragma: no-cache`. **Không cần response phải khớp nguyên chuỗi chính xác `Cache-Control: no-store`**; khi test, kiểm tra header có directive `no-store` và header `Pragma` thích hợp.

### 3.2. `no-cache` không đồng nghĩa `no-store`

| Header/directive | Mục đích | Có đủ thay `no-store` trong token response? |
| --- | --- | --- |
| `Cache-Control: no-store` | Không lưu request/response trong cache tuân thủ | **Có** cho yêu cầu ngăn lưu cache (vẫn phải gửi Pragma theo RFC). |
| `Cache-Control: no-cache` | Cache có thể lưu nhưng phải revalidate trước khi tái sử dụng | **Không**; có thể còn bản sao nhạy cảm trong storage. |
| `Cache-Control: private` | Shared cache không được lưu; private cache có thể lưu | **Không**; browser/private cache vẫn có thể chứa token. |
| `Cache-Control: max-age=0` | Response coi như đã stale để revalidate | **Không**; không cấm việc lưu. |
| `Pragma: no-cache` | Tương thích với cache HTTP cũ | **Không**, nếu thiếu `no-store` trên cache hiện đại. |
| `Expires: 0` | Thông báo hết hạn theo cơ chế cache cũ | **Không**; hỗ trợ nhưng không thay `no-store`. |

**Điểm nhớ:** `no-cache` nghĩa là không tái sử dụng tùy tiện, **không nhất thiết là không lưu**. Với credential/token, ưu tiên `no-store`.

### 3.3. Cache TTL không phải token TTL

Ví dụ access token có `expires_in=600`, tức thời hạn **10 phút**. Điều đó **không cho phép** browser hoặc proxy cache token response 10 phút:

```text
Token lifetime (10 phút):
    Token có thể được Resource Server chấp nhận tới hạn và theo chính sách.

Cache-Control: no-store:
    Không lưu bản sao HTTP response chứa credential trong cache.

Kết luận:
    Token còn hạn KHÔNG đồng nghĩa response được phép cache.
    Token hết hạn KHÔNG đồng nghĩa cache đã xóa bản sao credential.
```

Tương tự, `TokenSettings.accessTokenTimeToLive(...)` không tạo HTTP cache headers. Ngược lại, `Cache-Control: no-store` không tự rút ngắn token lifetime hay revoke token.

### 3.4. Phải áp dụng cho những response nào?

| Response | Yêu cầu/cách xử lý |
| --- | --- |
| Thành công `authorization_code` | **MUST no-store + Pragma no-cache** vì chứa access token/credential. |
| Thành công `refresh_token` | **MUST** vì chứa token, có thể có refresh token thay thế. |
| Thành công `client_credentials` | **MUST** vì chứa access token. |
| Thành công Device Code/Token Exchange | **MUST** nếu response chứa token/credential. |
| Lỗi `invalid_client`, `invalid_grant`, `invalid_scope` | Nên giữ **no-store** và **Pragma no-cache** trên toàn bộ Token Endpoint để phòng vệ chiều sâu; RFC 6749 §5.1 bắt buộc cho **response chứa dữ liệu nhạy cảm**, không nên khẳng định mọi lỗi thuần mã đều mặc nhiên chứa token. |
| Introspection, revocation, discovery | Có endpoint/chuẩn riêng; kiểm soát caching tùy dữ liệu. Không lấy quy tắc Token Endpoint để khẳng định discovery metadata công khai không thể cache. |

**Cảnh báo:** lỗi `invalid_client` có thể xảy ra **trước** Token Endpoint authentication provider do client authentication filter. Vì vậy test header phải bao phủ cả error response được xử lý ở **filter khác** trong SecurityFilterChain, không chỉ success handler của Token Endpoint.

### 3.5. Không dựa vào header để chống log/tracing

`Cache-Control: no-store` điều khiển hành vi cache HTTP tuân thủ; nó **không ngăn**:

- Reverse proxy hoặc API gateway chủ động dump request/response body ra log.
- Tracing agent thu `Authorization` header, form parameters hoặc JSON response.
- Ứng dụng ghi token vào log, metrics, error tracker, audit hoặc database sai mục đích.
- Debugger, heap dump, crash report hoặc CI giữ biến môi trường chứa secret.
- Client tự lưu token vào local storage, cookie kém an toàn hay hệ thống analytics.

Đây là những luồng **thu thập dữ liệu khác cache HTTP**, cần cấu hình và kiểm thử độc lập.

## 4. Truyền token qua HTTPS: bảo vệ mọi chặng

### 4.1. Yêu cầu TLS cho Token Endpoint

RFC 6749 §3.2 yêu cầu Token Endpoint sử dụng **TLS** vì đây là nơi trao đổi credential. Client phải xác minh chứng chỉ máy chủ; RFC 6750 cũng yêu cầu bảo vệ bearer token bằng TLS hoặc mức bảo vệ tương đương khi truyền.

**Không sử dụng HTTP plaintext** cho Token Endpoint production, kể cả khi mọi token là JWT có chữ ký:

- **Chữ ký JWT** bảo vệ tính toàn vẹn và xác thực nguồn token, **không mã hóa payload**.
- **TLS** bảo vệ bí mật và tính toàn vẹn của HTTP request/response trong lúc truyền.
- **`client_secret_basic`** chỉ base64-encode user/password; Base64 **không phải mã hóa**.
- Nếu bearer token bị chặn bắt, bên giữ token có thể dùng nó để gọi API theo phạm vi quyền, trừ khi token có sender constraint và Resource Server kiểm tra đúng.

```mermaid
flowchart TB
    subgraph CLIENT["OAuth2 Client / BFF"]
        C["HTTPS request<br/>client auth + grant"]
    end
    subgraph EDGE["Edge / TLS termination"]
        P["Reverse proxy / gateway<br/>Không cache, không log token"]
    end
    subgraph PRIVATE["Trusted backend segment"]
        A["Spring Authorization Server<br/>Token Endpoint"]
        K["Key management / HSM / secret store"]
        DB[("Authorization + client persistence")]
    end
    C -->|"TLS: certificate validated"| P
    P -->|"TLS/mTLS hoặc kênh riêng được bảo vệ"| A
    A --> K
    A --> DB
    A -->|"no-store token response"| P
    P -->|"HTTPS encrypted response"| C
```

**Một request HTTPS nhìn từ client chưa đủ để kết luận toàn tuyến an toàn.** Sau TLS termination ở gateway, dữ liệu có thể đi vào plaintext trên một mạng khác. Thiết kế mức bảo vệ cần dựa trên trust boundary, khả năng truy cập mạng, compliance và threat model.

### 4.2. Bảo vệ kết nối upstream sau reverse proxy

| Đoạn đường | Kiểm soát cần có |
| --- | --- |
| OAuth client → edge/load balancer | HTTPS, chứng chỉ hợp lệ, hostname verification, TLS versions/ciphers phù hợp chính sách |
| Edge → Authorization Server | Kênh nội bộ được bảo vệ; ưu tiên TLS/mTLS khi trust boundary yêu cầu; không để credential đi qua mạng không tin cậy |
| AS → database/secret store | TLS và xác thực dịch vụ theo khả năng, giới hạn quyền truy cập, secrets/key rotation |
| Client → Resource Server | HTTPS cho `Authorization: Bearer ...` và kiểm tra chứng chỉ máy chủ |
| Browser → Authorization/Verification Endpoint | HTTPS, cookie `Secure`/`HttpOnly`/`SameSite` phù hợp, chống CSRF và open redirect |

**Không tắt certificate validation** bằng `curl -k`, Java TrustManager “trust all”, hoặc `InsecureSkipVerify` trong production. Nếu dùng chứng chỉ CA nội bộ, cài CA vào trust store được quản lý; không bỏ kiểm tra hostname.

### 4.3. HSTS, issuer và forwarded headers

- **HSTS** (`Strict-Transport-Security`) giúp browser ghi nhớ chính sách HTTPS đối với host đã truy cập bảo mật. HSTS là lớp bảo vệ hữu ích cho browser, **không thay TLS verification** của OAuth client không phải trình duyệt.
- `AuthorizationServerSettings.issuer(...)` phải công bố **HTTPS issuer URL chính xác**, khớp với discovery, JWT `iss`, JWKS và cấu hình Resource Server.
- Ở sau proxy, phải cấu hình xử lý forwarded headers **chỉ từ proxy tin cậy**. Không lấy `X-Forwarded-Proto`/`Host` do Internet client tự gửi làm nguồn sự thật để dựng token endpoint URL hoặc issuer.
- Khi ép HTTPS, cần kiểm thử phản hồi thực từ cả entrypoint công khai và các đường nội bộ; không nên ép redirect POST `/oauth2/token` từ HTTP sang HTTPS rồi hy vọng client tự xử lý mà không lộ credential trong request đầu tiên.

Ví dụ khai báo issuer công khai:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .tokenEndpoint("/oauth2/token")
            .build();
}
```

Đây là cấu hình issuer/endpoint, **không** trực tiếp bật TLS. HTTPS có thể do Spring Boot embedded server hoặc reverse proxy cung cấp; phải triển khai TLS thực tế bên ngoài đoạn mã này.

### 4.4. Không đưa token vào URL hoặc redirect

Những mẫu **không an toàn**:

```http
GET /oauth2/token?grant_type=refresh_token&refresh_token=SECRET HTTP/1.1
Host: auth.example.com
```

```http
GET /api/orders?access_token=SECRET HTTP/1.1
Host: api.example.com
```

URL thường bị sao chép vào **browser history, server access log, proxy log, telemetry, referrer, analytics, monitoring dashboards**. RFC 6750 khuyến nghị **không gửi bearer token qua URI query parameter**; Token Endpoint phải dùng POST theo giao thức, không có lý do thiết kế mới để đưa credential vào URL.

Với **Resource Server**, dùng:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_EXAMPLE_NOT_REAL
```

Tuy bearer token trong header được ưu tiên hơn query, **header vẫn nhạy cảm** và phải bị redaction ở log/tracing. Không nhận token header rồi tiếp tục chuyển nó thành query parameter của một backend khác.

## 5. Quản lý dữ liệu nhạy cảm tại Token Endpoint

### 5.1. Phân loại dữ liệu

| Giá trị | Rủi ro nếu bị lộ | Chính sách |
| --- | --- | --- |
| `client_secret` | Attacker có thể giả danh confidential client tại Token Endpoint | Secret manager, hash/encoded khi đăng ký, rotate, không log |
| Private key / JWT client assertion | Giả mạo client nếu lộ khóa hoặc assertion còn hiệu lực | KMS/HSM, giới hạn TTL assertion, chống replay, không log |
| Authorization code | Có thể bị đổi lấy token nếu các ràng buộc khác bị vượt qua | One-time, TTL ngắn, PKCE, không log |
| `code_verifier` | Cùng authorization code có thể đủ để đổi token | Giữ theo transaction, không gửi qua front-channel/log |
| Refresh token | Xin access token mới trong phạm vi đã cấp | Lưu an toàn server-side khi phù hợp, rotation/revocation, không log |
| Access token | Truy cập API khi còn hợp lệ | Scope/audience/TTL tối thiểu, bảo vệ truyền và lưu |
| OIDC ID token | Có thể chứa claims người dùng, giúp client xác thực danh tính | Chỉ dùng cho OIDC client, không log payload/claims PII |
| Device code / subject_token | Có thể được dùng trong grant đặc thù | TTL, binding, không tiết lộ trong UI/log |
| Session cookie | Chiếm phiên browser hoặc BFF nếu bị lộ | `Secure`, `HttpOnly`, `SameSite`, chống fixation/CSRF |

**Không phải chỉ raw access token mới cần bảo vệ.** Refresh token, client assertion, private key, PKCE verifier và authorization code có thể có tác động bảo mật tương đương hoặc lớn hơn.

### 5.2. Logging, tracing và metrics

Ba cấp độ vận hành cần tách biệt:

**Có thể log (đã xử lý):**

- Timestamp, request ID/correlation ID ngẫu nhiên, endpoint, grant type **đã xác định hợp lệ**.
- Client ID khi có chính sách truy cập phù hợp (client ID không phải secret, nhưng vẫn có thể là thông tin nội bộ).
- OAuth error code `invalid_client`, `invalid_grant`, `invalid_scope`, outcome, latency, thời lượng.
- Hash/ID tương quan không cho phép tái tạo token nếu có nhu cầu audit và thiết kế HMAC/secret key đúng.

**Không log:**

- Trọn request/response bodies của `/oauth2/token`.
- Giá trị của `Authorization` header, `client_secret`, `refresh_token`, `access_token`, `code`, `code_verifier`, `device_code`, client assertion.
- Raw query string có credential, Set-Cookie hoặc session ID.
- JWT claims có thông tin cá nhân nhạy cảm, private JWK, khóa ký hoặc payload dump.

**Cần kiểm tra ở nhiều nơi:** Spring Boot application logging, Tomcat/Jetty access logs, ingress/gateway logs, load balancer, WAF, service mesh, OpenTelemetry/Zipkin/Jaeger, APM vendor, Sentry/error tracking, reverse-proxy error pages, CI test reports và hỗ trợ kỹ thuật.

Mẫu audit event **không chứa credential**:

```json
{
  "timestamp": "2026-11-16T09:10:00Z",
  "correlation_id": "req-a24e",
  "event": "oauth.token.grant",
  "grant_type": "client_credentials",
  "client_id": "orders-bff",
  "result": "success",
  "duration_ms": 42
}
```

Nếu cần truy dấu một token bị lạm dụng, đừng tự ghi nguyên bearer token rồi giải thích “chỉ nội bộ xem”. Chọn token ID/authorization ID đã kiểm soát, hoặc HMAC có secret riêng phục vụ tương quan; hạn chế số người đọc log và retention.

### 5.3. Vì sao bật DEBUG có thể rủi ro?

Các thư viện Spring Security/Spring Authorization Server thường hạn chế in credential theo thiết kế, **nhưng** một logging filter, interceptor, gateway hoặc HTTP client debug tùy biến có thể ghi full form body và authorization header. Đừng suy luận “đã bật DEBUG logger của Spring thì chắc chắn an toàn hoặc chắc chắn lộ”: phải xem dữ liệu thực qua test.

Tránh các anti-pattern:

```java
// SAI: có thể lộ client_secret/refresh_token/code_verifier.
log.debug("Token request: {}", request.getParameterMap());

// SAI: tiết lộ token và dữ liệu user trong response.
log.info("Token response: {}", tokenResponseJson);

// SAI: đưa Bearer / Basic credentials vào thông điệp lỗi.
log.error("Authorization header was: {}", request.getHeader("Authorization"));
```

Khi cần debug một sự cố, ghi **loại lỗi và correlation ID**, không ghi nguyên giá trị credential. Không dùng Java `toString()` của object chứa token như nguồn log nếu chưa biết rõ nó đã mask các field nhạy cảm hay chưa.

### 5.4. Bảo vệ token ở client và trong browser

- Confidential web client/BFF nên giữ OAuth tokens server-side, cấp browser một cookie phiên được bảo vệ; tránh đẩy refresh token vào JavaScript.
- Public SPA không thể giữ shared secret cố định đáng tin cậy; dùng Authorization Code + PKCE, policy token phù hợp và cân nhắc BFF khi dữ liệu nhạy cảm.
- Với ứng dụng native, dùng secure storage theo nền tảng, không hardcode credential vào binary.
- Không dùng browser URL, `localStorage` không được kiểm soát hoặc cookie không có thuộc tính bảo vệ như một “kho bảo mật mặc định” cho refresh token.
- Giảm scope, audience và token lifetime; đánh giá sender-constrained tokens (DPoP/mTLS) khi threat model yêu cầu, nhưng không coi đó là giấy phép bỏ TLS.
- Không chia sẻ token giữa các client/RP chỉ vì chúng có chung Authorization Server.

## 6. Cấu hình Spring Security/Spring Authorization Server: giữ mặc định an toàn

### 6.1. Các lớp xử lý request/response

Theo tài liệu Spring Authorization Server 1.5.x, Token Endpoint dùng:

| Component | Trách nhiệm |
| --- | --- |
| `OAuth2TokenEndpointFilter` | Nhận request của Token Endpoint và chuyển qua AuthenticationManager. |
| `OAuth2AuthorizationCodeAuthenticationConverter` và các converters khác | Chuyển tham số form POST theo grant thành Authentication. |
| `OAuth2AuthorizationCodeAuthenticationProvider`, `OAuth2RefreshTokenAuthenticationProvider`, `OAuth2ClientCredentialsAuthenticationProvider`... | Xác thực grant/client và điều phối token issuance. |
| `OAuth2AccessTokenResponseAuthenticationSuccessHandler` | Xử lý thành công và trả token response. |
| `OAuth2ErrorAuthenticationFailureHandler` | Xử lý OAuth error response. |
| `OAuth2TokenEndpointConfigurer` | Extension points cho request converter, providers, success/error handlers. |
| `SecurityFilterChain` / Spring Security Headers | Bổ sung security response headers theo cấu hình, bao gồm cache-control mặc định. |

**Ưu tiên giữ success/error handlers và security headers mặc định.** Nếu tự thay handler, phải kiểm thử rằng JSON, HTTP status, OAuth error và cache headers vẫn đáp ứng yêu cầu. Một handler chỉ ghi JSON token mà quên `Cache-Control: no-store` có thể tạo lỗ hổng ngay cả khi token generator đúng.

### 6.2. Ví dụ SecurityFilterChain cho Authorization Server

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .headers(headers ->
            // Giữ cache-control headers của Spring Security.
            headers.cacheControl(Customizer.withDefaults()));

    return http.build();
}
```

Đây là **một đoạn cấu hình chain để minh họa cache-control**, không phải Authorization Server hoàn chỉnh. Ứng dụng còn cần user/login chain, client repository, signing key, authorization services, issuer, consent và các bean tùy phiên bản. Không cấu hình toàn bộ SecurityFilterChain là stateless nếu làm hỏng phiên login/consent của Authorization Endpoint.

Spring Security mặc định thêm các header an toàn cho response (trong đó `Cache-Control` chứa `no-store`, `Pragma: no-cache` và `Expires: 0`), **trừ khi bạn tắt/cố tình ghi đè bằng cấu hình khác**. Cấu hình `headers.cacheControl(...)` ở đây là để làm rõ ý định, không phải điều kiện bắt buộc nếu defaults đã được giữ.

**Không làm thế này:**

```java
// SAI nếu làm mất no-store ở Token Endpoint:
http.headers(headers -> headers.cacheControl(cache -> cache.disable()));

// Cũng cần tránh một filter/controller đặt lại header như sau:
response.setHeader("Cache-Control", "public, max-age=600");
```

Nếu có một filter/controller custom đã tự đặt `Cache-Control`, Spring Security có thể **không ghi đè** header đó. Vì thế phải kiểm chứng response cuối cùng từ phía client qua proxy/gateway, không chỉ đọc code của filter.

### 6.3. Xử lý khi tự viết custom token response handler

Khi bắt buộc tùy biến success handler, các điều kiện tối thiểu:

1. Chỉ chạy sau khi provider xác thực grant và client; không tự phát token trong `@RestController` không đi qua các validator.
2. Giữ response format chuẩn OAuth (`access_token`, `token_type`, `expires_in`, `scope` khi cần, `refresh_token`/`id_token` nếu áp dụng).
3. Giữ `Cache-Control: no-store` và `Pragma: no-cache` trên **response cuối cùng**.
4. Không in hoặc trả thông tin nội bộ/stack trace; không đưa token vào redirect URL, cookie hoặc custom header dễ bị log.
5. Kiểm thử error handler, content type, proxy header rewrite, non-cacheable responses và concurrency.

Ví dụ một **helper** dùng khi tự quản lý response (không phải cách thay thế handlers mặc định):

```java
import jakarta.servlet.http.HttpServletResponse;

public final class SensitiveResponseHeaders {
    private SensitiveResponseHeaders() {}

    public static void apply(HttpServletResponse response) {
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");
        response.setHeader("X-Content-Type-Options", "nosniff");
    }
}
```

**Không cần** thêm helper này vào Token Endpoint mặc định nếu response đã đúng. Nếu dùng trong một handler tùy biến, phải gọi trước khi response commit và vẫn giữ các header/kiểm soát khác như HSTS/cert validation do hạ tầng cung cấp. Helper không tạo được HTTPS và không ngăn proxy ghi log.

### 6.4. Phân biệt endpoint back-channel và CSRF của login

Token Endpoint phục vụ client máy-máy, không phải form HTML dùng cookie session để thay đổi dữ liệu trên browser. Spring Authorization Server cấu hình các protocol endpoints và các exception CSRF tương ứng trong security chain. **Không tắt CSRF toàn ứng dụng** chỉ để POST tới Token Endpoint thành công: việc đó có thể làm mất bảo vệ của trang đăng nhập/consent hoặc admin API dùng cookie.

Không cài CORS `*` rồi cho phép mọi frontend gọi Token Endpoint chỉ vì token response có `no-store`. **CORS không thay client authentication, PKCE, state và redirect URI validation**. Nếu thiết kế public browser client thật sự cần CORS, chỉ cho phép origins đã phê duyệt và kiểm thử flow; tuyệt đối không kỳ vọng CORS giữ kín shared client secret nhúng trong frontend.

## 7. Kiểm tra Token Endpoint qua HTTP thực

### 7.1. Dùng fixture an toàn

Chuẩn bị một client **dành riêng cho integration test**, ví dụ:

```text
client_id: orders-test-service
client_authentication_method: client_secret_basic
authorization_grant_type: client_credentials
scopes: {orders.read}
endpoint: https://auth.test.example/oauth2/token

Secret và token:
    - chỉ là fixture, không dùng credential production
    - không lưu vào log chung
    - không đưa vào ảnh chụp/debug output hoặc source control
```

Gửi request POST có kiểm soát, **chỉ hiển thị headers**, không in JSON chứa token:

```bash
# Chỉ dùng secret giả/trong môi trường thử nghiệm riêng.
# Không dùng -k/--insecure, không tự động follow redirects.
curl --silent --show-error \
  --dump-header - \
  --output /dev/null \
  --request POST 'https://auth.test.example/oauth2/token' \
  --user 'orders-test-service:TEST_ONLY_SECRET' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode 'scope=orders.read'
```

**Kỳ vọng:** response thành công dùng HTTPS và headers có `Cache-Control` chứa directive `no-store`, đồng thời có `Pragma: no-cache`. `Content-Type` phải phản ánh JSON token response. Trong test thực, cần kiểm tra status và response body qua một client có cơ chế redaction, nhưng **không** in token ra terminal/CI log.

**Cảnh báo với curl:** `--user` đưa credential vào argument dòng lệnh, có thể hiện trong process inspection và shell history. Cú pháp này **chỉ minh họa cho fixture**; production hoặc kiểm thử với secret thật nên dùng client library lấy secret từ vault/secret manager, không gắn credential vào lệnh shell hoặc script commit trong repository. Không dùng `--trace-ascii`, `-v` hoặc redirect output body vào log công khai khi chứa credential.

### 7.2. Tại sao kiểm tra qua edge quan trọng?

Kiểm tra trên `localhost:9000/oauth2/token` có thể PASS trong khi response đi qua proxy thật lại bị:

- Ghi đè `Cache-Control` thành `public, max-age=...` theo một rule gateway.
- Gỡ `Pragma` hoặc các security headers trong pipeline response.
- Bật cache mọi response của một route có cấu hình sai.
- Ghi body response trong access log/WAF/APM để “phân tích sự cố”.
- Tắt TLS hoặc certificate validation ở một hop nội bộ.

Do đó phải thử **cả** Token Endpoint qua public issuer/edge và đường upstream được kiến trúc cho phép. **Không** chỉ xác minh một giá trị header ở lớp `HttpServletResponse` mà bỏ qua response cuối từ gateway.

### 7.3. Không dùng HEAD/GET để kiểm thử token issuance

Token Endpoint xử lý token grant qua **POST**. Một request `HEAD /oauth2/token` hoặc `GET /oauth2/token` trả 404/405/redirect không chứng minh token response thật có cache headers đúng. Hãy dùng HTTP POST test fixture, sau đó kiểm tra chính response của grant thành công; với negative tests, kiểm tra lỗi thật của Token Endpoint.

## 8. Kiểm thử Spring Boot bằng MockMvc

### 8.1. Integration test thành công của client_credentials

Đoạn dưới là một **test skeleton** có thể hoàn thiện trong Spring Boot integration test khi ứng dụng đã có:

- `spring-security-test`, `spring-boot-starter-test` và cấu hình MockMvc.
- Authorization Server SecurityFilterChain, `RegisteredClientRepository` và token generator.
- Client test `orders-test-service` với secret `test-secret` đã được đăng ký/băm đúng cách, grant `client_credentials` và scope `orders.read`.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class TokenEndpointResponseSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulTokenResponseIsNotCacheable() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("orders-test-service", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "orders.read"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(header().string(
                    HttpHeaders.PRAGMA, containsString("no-cache")))
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.token_type").value("Bearer"));
    }

    @Test
    void invalidScopeDoesNotExposeCredentialOrCacheableResponse() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("orders-test-service", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "orders.admin"))
            .andExpect(status().isBadRequest())
            .andExpect(header().string(
                    HttpHeaders.CACHE_CONTROL, containsString("no-store")))
            .andExpect(header().string(
                    HttpHeaders.PRAGMA, containsString("no-cache")))
            .andExpect(jsonPath("$.error").value("invalid_scope"))
            .andExpect(jsonPath("$.access_token").doesNotExist());
    }
}
```

Đoạn test chủ ý **không in token value**. Nó chứng minh response của Spring Test MVC có headers đúng, **không chứng minh** TLS thật ngoài mạng hoặc cấu hình cache tại gateway. Nếu app đã customize grant validation hoặc dùng Spring Boot/Spring Security phiên bản khác, cần điều chỉnh fixture và assertions phù hợp. Không chạy trong STEP 4 của bài viết; đây là mã mẫu cho người học.

### 8.2. Kiểm thử response lỗi ở các vị trí khác nhau

Thêm các trường hợp:

| Request | Kết quả nên kiểm tra |
| --- | --- |
| Client Credentials đúng | 200; JSON access token; no-store + Pragma. |
| `invalid_scope` | OAuth error JSON, không có token; headers an toàn. |
| Sai client secret | Client authentication bị từ chối; headers an toàn cả khi lỗi xử lý **trước Token Endpoint provider**. |
| Missing `grant_type` | Lỗi request phù hợp; không leak credential/stack trace. |
| `authorization_code` hết hạn/đã dùng | `invalid_grant` hoặc lỗi đúng ngữ cảnh; không cấp token. |
| Refresh token đã revoke | Lỗi grant, không cấp access token mới; headers an toàn. |
| Unsupported grant | `unsupported_grant_type`; không có token. |
| HTTP GET thay POST | Không phát token, không redirect tới URI ngoài ý muốn. |
| Token Exchange/Device Code nếu được bật | Success/error theo profile; cache/security policy không bị bỏ qua. |

**Tránh sai kết luận:** nếu request bị từ chối ở lớp client authentication trước khi grant validator chạy, test đã chứng minh **credential bị từ chối**, chưa chứng minh `invalid_scope` hoặc logic token issuance đã được kiểm thử. Mỗi case cần fixture có đủ điều kiện để đi tới đúng nhánh xử lý.

### 8.3. Tránh test header theo exact string

Do Spring Security có thể gửi:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
```

Một assertion `Cache-Control == "no-store"` dễ **fail sai** dù response bảo vệ tốt. Trong test, kiểm tra sự tồn tại directive `no-store` thay vì so nguyên chuỗi cứng. Với kiểm tra nghiêm ngặt cần parse danh sách directives, không chấp nhận trường hợp header bị gateway ghi thêm `public` xung đột.

### 8.4. MockMvc không phải thử nghiệm HTTPS thật

`MockMvc` chạy ở tầng Servlet/test context; ngay cả khi gọi `request().secure(true)`, nó cũng chỉ **giả lập thuộc tính secure** của request, không tạo TLS handshake thật. Muốn kiểm chứng HTTPS:

- Chạy môi trường staging với TLS endpoint công khai.
- Xác minh certificate chain, hostname, issuer, cipher/TLS configuration.
- Kiểm tra redirect HTTP bị xử lý an toàn và không gửi credential qua HTTP.
- Kiểm tra upstream mTLS/TLS khi kiến trúc yêu cầu.
- Kiểm tra header/no-store ở response qua ingress thực.

## 9. Kiểm soát reverse proxy, CDN, gateway và HTTP cache

### 9.1. Đường nào tuyệt đối không nên được cache?

Các đường **trả token hoặc credential** phải được quản lý đặc biệt:

```text
POST /oauth2/token                 -> NO STORE
POST /oauth2/device_authorization  -> chứa device_code/user_code: NO STORE
POST /oauth2/introspect            -> chứa trạng thái/claims nhạy cảm: chính sách cache chặt
POST /oauth2/revoke                -> bảo vệ request/response và logging, không cache
GET  /oauth2/jwks                  -> public keys có thể có caching hợp lý theo chính sách
GET  /.well-known/openid-configuration -> public discovery metadata có thể cache có kiểm soát
```

Đây là **định hướng vận hành** chứ không phải lời khẳng định mọi endpoint trên đều có response cache policy giống Token Endpoint trong chuẩn OAuth. Đừng vô tình tắt cache của JWKS/discovery toàn cục rồi đổ lỗi cho Token Endpoint chậm; ngược lại, **không bật cache mọi `/oauth2/*`** chỉ vì muốn tối ưu discovery/JWKS.

### 9.2. Quy tắc gateway cần được kiểm tra

Tại proxy/CDN/gateway:

1. **Không cache** `POST /oauth2/token` và những đường protocol có credential.
2. Không làm mất header `Cache-Control: no-store`/`Pragma: no-cache` do AS trả.
3. Không ghi `Authorization` header, request/response body, `client_secret` hoặc token vào access log.
4. Không bật “full request/response capture” trên Token Endpoint cho APM hay WAF nếu chưa có redaction được kiểm chứng.
5. Không dùng response caching tùy biến theo `client_id`, `scope` hoặc hash của grant parameters để “tái sử dụng token”.
6. Bảo vệ TLS cả tới upstream theo trust boundary; kiểm soát forwarded headers và host/issuer.
7. Không biến lỗi backend thành error page HTML chứa raw URL/headers có credential.

**Một CDN bình thường có thể không cache POST theo mặc định**, nhưng điều đó không đủ để bỏ `no-store`. Cấu hình edge, plugin hoặc middleware có thể đổi hành vi; RFC quy định header độc lập với giả định triển khai.

### 9.3. Những header không thể thay no-store

`Vary: Authorization`, `ETag` hoặc `Last-Modified` **không phải giải pháp chống lưu token response**. Chúng thuộc semantics cache/revalidation, có thể vẫn giữ bản sao nhạy cảm. Đối với Token Endpoint, cách an toàn là trả response **non-cacheable** và đồng thời disable caching tại gateway.

## 10. Khác biệt giữa truyền token và dùng token

### 10.1. Cấp token ở AS không đồng nghĩa Resource Server sẽ kiểm tra đúng

Token Endpoint có thể cấp một access token qua HTTPS, no-store hoàn chỉnh, nhưng Resource Server vẫn có thể sai:

- Cho phép HTTP request mang bearer token.
- Không kiểm tra `iss`/`aud`/`exp`/scope, dẫn đến token dùng sai API.
- Ghi Bearer token vào access logs.
- Nhận token từ query string/cookie thiếu bảo vệ.
- Không kiểm tra trạng thái revoked nếu API yêu cầu thu hồi tức thời và chỉ xác minh JWT offline.

**Bảo vệ Token Endpoint là điều kiện cần, không phải điều kiện đủ cho toàn bộ OAuth deployment.**

### 10.2. JWT có chữ ký nhưng không bí mật

JWT access token dạng JWS thường có payload **base64url có thể giải mã đọc**, không được coi là đã mã hóa:

```text
header.payload.signature
```

Chữ ký chứng minh tính toàn vẹn và khóa ký phù hợp; nó **không giấu** các claims như `sub`, `roles`, tenant, email hoặc quyền. Không đưa client secret, mật khẩu, refresh token hay dữ liệu cá nhân không cần thiết vào claims. TLS bảo vệ JWT **khi đang truyền**, còn storage/logging cần bảo vệ riêng.

Opaque/reference token không dễ đọc claims từ giá trị token nhưng vẫn là **bearer credential**; đánh cắp giá trị đó vẫn nguy hiểm nếu Resource Server chấp nhận.

### 10.3. Sender-constrained tokens là biện pháp bổ sung

**DPoP** (RFC 9449) và **OAuth 2.0 mutual-TLS client authentication/certificate-bound access tokens** (RFC 8705) có thể giảm khả năng lạm dụng token khi chỉ bị lấy cắp value. Nhưng:

- Không phải mọi client, grant và Resource Server hỗ trợ chúng theo mặc định.
- Phải xác minh binding và proof ở đúng endpoint.
- Token Endpoint vẫn phải được bảo vệ bằng TLS và no-store.
- Kẻ tấn công chiếm luôn private key/thiết bị vẫn có thể vượt sender constraint.

Không coi DPoP/mTLS là thay thế cho access token TTL, scope/audience, log redaction và token revocation policy.

## 11. Xử lý các tình huống sự cố

### 11.1. Token xuất hiện trong log APM

Giả sử nhóm vận hành phát hiện `response.body.access_token` trong một bản ghi tracing:

1. **Ngừng thu thập mới** hoặc bật redaction ngay tại instrumentation/gateway.
2. Xác định phạm vi token bị lộ, khoảng thời gian, grants/clients liên quan và bên có quyền đọc log.
3. Thu hồi refresh tokens/authorization state phù hợp và đánh giá access tokens còn sống.
4. Với JWT offline, **không** giả định xóa token trong database sẽ làm API chặn ngay; cần TTL ngắn, denylist/introspection/state check theo chính sách.
5. Giảm retention/phạm vi truy cập log bị ảnh hưởng theo quy trình incident/legal, không tự xóa chứng cứ một cách thiếu kiểm soát.
6. Bổ sung regression test xác nhận log capture không còn chứa tên trường/giá trị credential, đồng thời giữ metrics an toàn.

`Cache-Control: no-store` vẫn cần có, nhưng **không giải quyết** nguyên nhân APM cố tình copy body.

### 11.2. Proxy trả `Cache-Control: public` dù AS đúng

Điều tra theo đường đi:

```mermaid
flowchart TD
    U["Client quan sát response<br/>Cache-Control: public"] --> E["Gateway/CDN rule"]
    E --> F{"Gọi upstream trong môi trường<br/>test có no-store không?"}
    F -->|"Có"| P["Proxy thay/ghi đè header<br/>Sửa rule, disable cache /oauth2/token"]
    F -->|"Không"| A["AS hoặc custom success handler<br/>mất security header"]
    P --> T["Retest response cuối qua HTTPS edge"]
    A --> T
    T --> V["Kiểm tra no-store + Pragma<br/>và không có public/max-age cacheable"]
```

Không bỏ qua phần kiểm tra **response cuối cùng**. Trong mạng nhiều tầng, ingress A có thể giữ header còn CDN B thì xóa.

### 11.3. Token Endpoint phản hồi qua HTTP trên mạng nội bộ

Trước tiên xác định trust boundary: ai có quyền kết nối hay quan sát đoạn nội bộ, dữ liệu có đi qua nhiều network zones, service mesh có mã hóa hop-to-hop không, lưu lượng có bị mirror/tap không. Nếu yêu cầu bảo mật buộc mã hóa nội bộ, triển khai TLS/mTLS đúng chỗ, không “giải quyết” bằng cách bỏ verify server certificate.

**Chỉ dùng HTTPS ở edge không tự bảo đảm mọi hop nội bộ đều được mã hóa.** Cần mô tả ranh giới bảo mật và kiểm chứng hạ tầng thật.

### 11.4. Client báo lỗi TLS handshake/certificate

Không hạ bảo mật bằng `curl --insecure` hoặc trust-all. Kiểm tra hostname, certificate chain, CA trust store, certificate expiry, SNI, proxy interception, protocol/cipher compatibility và đồng hồ hệ thống. Sửa cấu hình/certificates; không đưa refresh token hoặc client secret qua HTTP để “test tạm”.

## 12. Ma trận kiểm thử bảo mật trước production

| ID | Thành phần | Kịch bản | Kết quả mong đợi |
| --- | --- | --- | --- |
| H01 | Token success | `client_credentials` hợp lệ | `no-store` và `Pragma: no-cache`; không bị gateway cache. |
| H02 | Token success | Đổi authorization code hợp lệ | Header chống cache vẫn có dù response chứa refresh/ID token. |
| H03 | Token success | Refresh token hợp lệ | Header chống cache; refresh token mới không bị log. |
| H04 | Token errors | `invalid_scope` | Error JSON đúng; không chứa token; headers an toàn. |
| H05 | Client auth error | Sai client secret | Không trả token; headers an toàn khi lỗi xử lý ở client authentication filter. |
| H06 | Custom handlers | Thay success/error handler | Không mất `no-store`/`Pragma`, JSON/status đúng chuẩn. |
| H07 | Cache semantics | Response bị ghi `public`/`max-age` | Phát hiện và sửa; không cho cache token response. |
| H08 | TLS | Gọi Token Endpoint qua HTTPS hợp lệ | Handshake/hostname/chain verification thành công. |
| H09 | TLS | Chứng chỉ hết hạn/sai host/untrusted CA | Client từ chối; không tắt certificate validation. |
| H10 | HTTP | Attempt POST qua `http://` | Không cấp token qua plaintext; không trông chờ redirect credential sang HTTPS. |
| H11 | Reverse proxy | TLS edge → upstream | Đường nội bộ đáp ứng chính sách mã hóa và xác thực. |
| H12 | Proxy headers | Client tự gửi `X-Forwarded-Proto`/`Host` giả | Không làm đổi issuer/host/HTTPS policy vì proxy lọc. |
| H13 | URL query | Gửi `refresh_token`/`access_token` trong query | Token Endpoint không lấy credential từ query theo thiết kế. |
| H14 | Logging | TRACE/DEBUG trên server/edge | Không lưu raw grant/Authorization header/token response. |
| H15 | Tracing | Bật APM instrumentation | Redaction của headers/form/body hoạt động, không có token trong spans. |
| H16 | Metrics | Label/token/correlation | Không sử dụng token/secret làm metric label. |
| H17 | JWT claims | Token phát ra chứa claims | Không chứa secret hoặc PII không cần thiết; issuer/audience/scope phù hợp. |
| H18 | Resource Server | API nhận bearer token | Chỉ qua HTTPS; kiểm tra chữ ký/token, issuer, audience, expiry, scope. |
| H19 | Multi-instance | Token Endpoint trên nhiều node | Cùng security headers và TLS policy; không lệch cấu hình. |
| H20 | CI/test | Lỗi test in HTTP body | Test runner/report không xuất token/secret thật. |
| H21 | OIDC | Token response có ID token | ID token vẫn được truyền qua HTTPS/no-store, không log claims PII. |
| H22 | Token Exchange | Subject/actor token trong request | Không log/copy credential nguồn; back-channel được bảo vệ. |
| H23 | Session/CSRF | Token Endpoint hoạt động, login/consent vẫn bảo vệ | Không tắt CSRF toàn hệ thống để xử lý POST token. |
| H24 | Cache headers | `no-cache` đơn lẻ nhưng thiếu `no-store` | Test FAIL, cần bổ sung `no-store`. |
| H25 | Gateway | Cache disabled cho token route, discovery/JWKS còn policy riêng | Không tái sử dụng token response cho client khác. |

### 12.1. Kiểm thử âm tính không được làm rò rỉ credential

Một vài framework HTTP test có thể đưa full request/response vào assertion failure. Khi test với client secret/refresh token, hãy dùng **test credentials** và cân nhắc công cụ redaction; đừng đưa token production vào unit/integration tests. Không upload traffic capture chứa credential thật lên ticket công khai chỉ để chứng minh header.

### 12.2. Bằng chứng cần lưu cho đợt release

Các artifact kiểm thử nên giữ **thông tin an toàn**:

- Ảnh/chụp headers `Cache-Control`, `Pragma`, HTTP status, issuer URL, không kèm token body.
- Báo cáo TLS/certificate validation đã redaction.
- Kết quả automated test chính xác cả success/error và gateway path.
- Evidence rằng logging/tracing pipelines đã loại credential và không ghi body token endpoint.
- Version của Spring Boot/Spring Security/Spring Authorization Server, proxy và cấu hình relevant.

Không dùng một ảnh chụp JSON token phản hồi chưa che để “chứng minh đã cấp token thành công”.

## 13. Checklist triển khai thực tế

**Protocol & HTTP**

- [ ] Token Endpoint nhận POST với request format đúng giao thức, có client authentication theo client registration.
- [ ] Mọi response chứa token/credential có `Cache-Control` bao gồm `no-store` và `Pragma: no-cache`.
- [ ] Error response giữ headers an toàn; error handler không in stack trace/token/secret.
- [ ] Không dùng `no-cache`, `private` hoặc `max-age=0` thay cho `no-store`.
- [ ] Không phát token qua GET/query parameter, không redirect token response tới URL tùy ý.

**TLS & infrastructure**

- [ ] Public issuer và Token Endpoint dùng HTTPS, client kiểm tra hostname/chứng chỉ.
- [ ] TLS policy đủ mạnh theo tiêu chuẩn đang áp dụng; không có trust-all client.
- [ ] Các hop reverse proxy/upstream/database/secret manager được bảo vệ theo trust boundary.
- [ ] Gateway không cache hoặc log full body/token; không ghi đè `no-store`/`Pragma`.
- [ ] Forwarded headers và Host được tin cậy có kiểm soát; HSTS được triển khai phù hợp.

**Dữ liệu nhạy cảm**

- [ ] Client secret/refresh token/code/verifier/assertion/access token được bảo vệ khi truyền và lưu.
- [ ] Không nhúng shared secret vào public frontend hoặc mobile binary.
- [ ] Application logs, proxy logs, APM/traces, metrics và test reports có redaction được kiểm thử.
- [ ] Token scope/audience/TTL tối thiểu; JWT không mang secret/PII không cần thiết.
- [ ] Có quy trình rotate credential, revoke token/authorization và ứng phó sự cố lộ token.

**Kiểm thử và vận hành**

- [ ] Automated tests kiểm tra success/error, đúng headers và không có token khi lỗi.
- [ ] Có test HTTPS thật qua edge và certificate failure; MockMvc không bị coi là bằng chứng TLS.
- [ ] Kiểm thử custom handlers, nhiều SecurityFilterChain, multi-node và gateway rules.
- [ ] Bằng chứng release không chứa credential; giám sát có correlation ID an toàn.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “JWT đã ký thì không cần HTTPS.” | JWT signature không mã hóa request/response hay claims. |
| “`Cache-Control: no-cache` đồng nghĩa không lưu.” | Cache có thể lưu nhưng phải revalidate; cần `no-store`. |
| “`max-age=0` là đủ cho OAuth token response.” | Không cấm lưu response; RFC yêu cầu `no-store` và `Pragma`. |
| “Access token TTL 10 phút thì cache response 10 phút hợp lý.” | Token TTL và cache TTL là hai cơ chế độc lập. |
| “Token Endpoint chạy POST nên không cache được.” | Cache middleware tùy biến có thể vẫn lưu; cần headers/chính sách gateway. |
| “Gateway dùng HTTPS nên AS chắc chắn truyền TLS mọi chặng.” | Phải kiểm tra cả upstream sau TLS termination. |
| “`client_secret_basic` đã base64 nên an toàn trên HTTP.” | Base64 chỉ mã hóa biểu diễn, không giữ bí mật. |
| “Có `no-store` thì APM không ghi token.” | Header cache không kiểm soát log/tracing; cần redaction. |
| “Chỉ log request form parameters thì không lộ token.” | `refresh_token`, `code` và `code_verifier` đều có trong form. |
| “In `toString()` của OAuth object luôn an toàn.” | Phải kiểm tra mask/redaction thực tế; không mặc nhiên tin. |
| “`MockMvc.secure(true)` chứng minh TLS certificate đúng.” | Nó chỉ giả lập thuộc tính request, không có handshake. |
| “Tắt CSRF để Token Endpoint POST được là ổn.” | Có thể phá bảo vệ login/consent/admin endpoints. |
| “CORS `*` làm public SPA gửi secret an toàn.” | CORS không giữ kín credential trong JavaScript. |
| “Token không ở URL thì logging luôn an toàn.” | Header/body/traces vẫn có thể chứa token. |
| “Spring Security mặc định thêm header nên khỏi test proxy.” | Custom filters/gateway có thể xóa/ghi đè; phải xem response cuối. |

## 15. Tài liệu tham khảo

- [RFC 6749 §3.2 — Token Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.2): Token Endpoint, HTTP POST, yêu cầu TLS và client authentication.
- [RFC 6749 §5.1 — Successful Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.1): yêu cầu `Cache-Control: no-store` và `Pragma: no-cache` với response chứa token/credential/sensitive info.
- [RFC 6749 §5.2 — Error Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.2): OAuth error JSON và mã lỗi ở Token Endpoint.
- [RFC 6750 §2 và §5 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer token qua Authorization header, yêu cầu TLS và cảnh báo rò rỉ qua URI query.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): các yêu cầu/khuyến nghị OAuth hiện đại về authorization, token, redirect và client security.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): semantics `no-store`, `no-cache`, `private` và cache directives.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens khi được triển khai.
- [RFC 8705 — OAuth 2.0 Mutual-TLS](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication và certificate-bound access tokens.
- [Spring Authorization Server 1.5.x — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenEndpointFilter`, converters/providers và response handlers.
- [Spring Authorization Server 1.5.x — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` và security filters.
- [Spring Security — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cache-control defaults và khả năng tùy chỉnh/ghi đè.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): kiểm tra JWT phía API, issuer và chữ ký.

**Kết luận:** **Token Endpoint là điểm trao đổi credential nhạy cảm**, nên một implementation đúng không chỉ kiểm tra grant và ký JWT, mà còn phải bảo vệ **response khỏi HTTP caching**, bảo vệ **request/response khỏi log/tracing không kiểm soát**, và bảo đảm **HTTPS/TLS ở mọi trust boundary**. Trong Spring Authorization Server, hãy giữ các security headers/handlers mặc định khi có thể, chỉ tùy biến với test chứng minh `no-store` và `Pragma: no-cache` vẫn còn, đồng thời kiểm tra response thực đi qua gateway và việc sử dụng token tại Resource Server.
