# Quản lý secret, tránh log token và xoay thông tin xác thực

## 1. Bí mật bị lộ thường nguy hiểm hơn một lần đăng nhập thất bại

`Authorization: Bearer ...` là **credential**, không chỉ metadata. Access token trong log/APM có thể bị replay; private key ký JWT bị lộ có thể tạo token giả; database password bị lộ có thể mở quyền dữ liệu. Phải bảo vệ **toàn bộ vòng đời**, không chỉ code kiểm tra token.

~~~http
GET /v1/orders/o-42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <redacted-access-token>
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":"o-42","status":"PAID"}
~~~

Server phải kiểm tra chữ ký, issuer, audience, expiry và quyền, **không ghi Bearer token vào log, trace, metric hay response lỗi**. Placeholder trên không phải token thật.

Bài thuộc chương **Xác thực**, module **INTEGRATION_API_REST**, trong chương trình resource/URI/status, hợp đồng REST, cache, idempotency, OpenAPI và bảo mật Java/Spring. Mục tiêu:

1. Phân biệt các secret/token, xác định **ai sở hữu, ai cần đọc, dùng để làm gì và sống bao lâu**.
2. Thiết kế lưu trữ/phân phối từ secret manager/KMS, không hard-code hoặc đưa secret vào artifact.
3. Ngăn lộ token qua HTTP URL, logs, traces, exceptions, telemetry và môi trường CI/CD.
4. Xoay **client secret, API key, khóa ký JWT và refresh token** có kiểm chứng, rollback và phản ứng sự cố.
5. Áp dụng kiểm thử Java/Spring, bài tập và checklist vận hành.

Quản lý secret không thay OAuth/OIDC, TLS, CSRF hoặc tenant authorization; credential vẫn cần **quyền tối thiểu và TTL hợp lý**.

## 2. Phân loại đúng secret trước khi bảo vệ

| Loại | Ai sở hữu / cách sử dụng | Nguy cơ lộ | Chính sách điển hình |
|---|---|---|---|
| **API key** | Client gọi API đối tác hoặc server-to-server | Gọi API thay ứng dụng, tiêu quota | Scope hẹp, key ID, rotation, revoke, monitoring |
| **OAuth client secret** | Confidential client xác thực với token endpoint | Lấy token dưới danh tính client nếu điều kiện khác thỏa | Giữ server-side, vault/secret manager, rotate; không dùng cho SPA/native public client |
| **Access token** | Client gửi `Authorization: Bearer` | Replay trong phạm vi scope/audience đến khi hết hạn | TTL ngắn, TLS, audience/scope, không log |
| **Refresh token** | Đổi lấy access token mới | Duy trì quyền truy cập lâu dài | Lưu an toàn, rotation hoặc sender-constraining tùy policy, phát hiện reuse |
| **JWT signing private key / HMAC secret** | Authorization server ký JWT; resource server xác minh | Có thể giả mạo token nếu lộ key ký | KMS/HSM, key version, JWKS với khóa công khai, rollover có overlap |
| **Database password / cloud credential** | Ứng dụng kết nối hạ tầng | Truy cập dữ liệu/hạ tầng trực tiếp | Workload identity/dynamic credentials nếu có, quyền tối thiểu, xoay có health check |
| **Webhook signing secret** | Xác minh request từ đối tác | Giả webhook; hoặc bỏ lọt request giả | HMAC trên raw bytes, timestamp/replay defense, dual-secret window |
| **mTLS private key** | Chứng minh danh tính client/server trong TLS | Giả danh endpoint nếu kẻ xấu có key/chứng chỉ hợp lệ | Keystore/HSM, tự động cấp/thu hồi, overlap trust, theo dõi expiry |

**Đừng nhầm identifier với secret:** `kid`, `client_id`, `jti`/`sub` thường là ID/claim, `client_secret` là bí mật. Public verification key được công bố qua JWKS; private key không.

Bearer token có nguy cơ replay; DPoP/mTLS sender-constraining giảm rủi ro nhưng **không cho phép log credential**.

### 2.1. Một secret cần bản mô tả sở hữu tối thiểu

Mỗi secret cần metadata: **owner, consumer, scope, TTL, issuer, version, rotation/revoke plan và audit** — không lưu giá trị trong ticket/wiki/dashboard.

`payment-partner-key` và `v12` là alias/version, **không phải giá trị secret**; tránh đưa credential vào message queue/correlation ID.

## 3. Vòng đời bảo vệ secret: phát hành → dùng → xoay → thu hồi

~~~mermaid
flowchart LR
    A["Phát hành ngẫu nhiên / từ identity provider"] --> B["Lưu secret manager / KMS / HSM"]
    B --> C["Cấp quyền cho workload identity"]
    C --> D["Nạp vào ứng dụng có kiểm soát"]
    D --> E["Sử dụng TLS + scope tối thiểu"]
    E --> F["Quan sát metadata, không log giá trị"]
    F --> G["Xoay có chồng lấn phiên bản"]
    G --> H["Thu hồi khóa cũ / giám sát"]
    H --> B
~~~

### 3.1. Phát hành và lưu trữ

- Tạo secret bằng **CSPRNG**/provider; không dùng `UUID` làm mặc định cho mọi yêu cầu entropy hay tự đặt password dễ đoán.
- Ưu tiên **managed identity/workload identity**, short-lived credentials hoặc secret manager có audit/IAM/versioning thay vì static key. Private signing key có thể nằm trong KMS/HSM không cho ứng dụng đọc raw private key; ứng dụng gọi **signing operation** theo quyền.
- Mã hóa at rest/in transit; tách quyền **đọc**, **ghi version**, **đổi alias**, **thu hồi**. Người đọc log không được mặc nhiên đọc secret.
- Không commit vào Git, Dockerfile/image, `application.yml`, `.env` chia sẻ hay CI artifact. `gitignore` không gỡ credential đã commit; phải **xoay/thu hồi**.

**Kubernetes Secret dùng base64, không tự mã hóa dữ liệu.** Bật etcd encryption, RBAC, audit, hạn chế `kubectl get` và cân nhắc CSI/external secret manager. Environment variables có thể lộ qua dump/process/diagnostics: giới hạn quyền và không in config.

### 3.2. Phân phối secret cho Spring Boot

Một triển khai thường có Spring Boot đọc credential qua **config data** hoặc đường dẫn file do secret manager/CSI mount cung cấp. Ví dụ **chỉ chứa địa chỉ và tên property**, không chứa giá trị:

~~~yaml
# application.yml - không lưu credential thật trong repository
app:
  partner:
    base-url: https://partner.example.com
    credential-file: /run/secrets/partner-api-key
  security:
    rotation-grace: PT5M
~~~

Code đọc file phải kiểm tra quyền/size/encoding và xử lý thiếu secret. Không in `@ConfigurationProperties.toString()` có credential, không lộ qua Actuator/heap dump; **masking mặc định có thể bỏ sót custom property**.

Mount cập nhật **không bảo đảm client pool/TLS context/JWT decoder tự reload**. Cần refresh theo version, health check và rollback.

### 3.3. Giữ secret sống ngắn trong bộ nhớ, nhưng không hứa “xóa sạch RAM”

Hạn chế bản sao và serialization. Java `String` immutable nên **không thể bảo đảm zeroize**; `char[]`/`byte[]` chỉ xóa được buffer mình sở hữu. Vẫn phải bảo vệ process, heap dump và debug access.

## 4. Tránh log token từ đầu vào đến đầu ra

### 4.1. Những bề mặt thường vô tình làm rò credential

| Bề mặt | Phản mẫu | Thay thế an toàn |
|---|---|---|
| HTTP access log của gateway/proxy | Ghi toàn bộ `Authorization`/`Cookie`/URL query | Ghi method, route template, status, latency, request ID và metadata allowlist |
| Java controller/filter | `log.info("headers={}", request.getHeaderNames())` hoặc dump toàn bộ request | Chỉ lấy những field đã duyệt; không log body/header nhạy cảm |
| WebClient/RestClient | Wiretap hoặc interceptor ghi raw request/response | Tắt body/header debug ở production, chỉ log đích đã chuẩn hóa, status và thời gian |
| Exception / `toString()` | `throw new RuntimeException("token=" + token)` | Lỗi có mã trung tính, context không nhạy cảm; không đưa credential vào `toString()` |
| Traces/APM | Attribute `http.request.header.authorization`, raw query URL | Cấu hình capture allowlist/redaction ở **mọi exporter và collector** |
| Metrics | Token làm label trong time series | Label cardinality thấp như route/status/service; không chứa identity/token |
| CI/CD | `set -x`, in environment, echo secrets trong pipeline | Dùng masking + không echo giá trị, quyền runner/artifact tối thiểu |
| Browser/mobile | Token trong URL, analytics, error reporting | Authorization header qua TLS, storage phù hợp ứng dụng, bỏ token khỏi telemetry |

Redact app log **chưa đủ**: proxy, mesh, APM, CI test dump và dead-letter queue cũng có thể lưu credential. Kiểm tra dev/staging và retention/backups.

**Không truyền token trong URL query** vì history, `Referer`, analytics và proxy log. Dùng `Authorization` và cấu hình tầng hạ tầng không ghi header này.

### 4.2. Logging theo allowlist thay vì blacklist

Một blacklist tìm chuỗi `password`/`token` có thể bỏ sót `apiKey`, `client_secret`, custom header, cookie hoặc secret ở JSON nested field. **Allowlist** cho biết chính xác metadata nào được phép xuất:

~~~text
Cho phép: timestamp, service, operation/route template, HTTP method,
         HTTP status, duration, server-generated requestId, errorCode

Không ghi: Authorization, Cookie, Set-Cookie, API key, raw JWT,
           URL query nhạy cảm, request/response body, signing key,
           OTP, password, refresh token, full user claims
~~~

Nếu cần điều tra request, dùng **route template** như `/v1/orders/{id}` thay vì raw URI chứa ID ngoài scope; dùng error code thay vì exception message có thể mang input chưa kiểm soát. Nếu bắt buộc lấy một trường nhạy cảm để xử lý sự cố, cần quy trình phê duyệt, giới hạn thời gian/scope và masking được kiểm thử, không bật payload logging toàn cục.

### 4.3. Servlet filter Spring Boot chỉ log metadata an toàn

~~~java
@Component
class SafeRequestLogFilter extends OncePerRequestFilter {
    private static final Logger LOG =
        LoggerFactory.getLogger(SafeRequestLogFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        long start = System.nanoTime();
        MDC.put("requestId", requestId);
        response.setHeader("X-Request-Id", requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);
            LOG.info("http_request method={} status={} elapsedMs={} requestId={}",
                request.getMethod(), response.getStatus(),
                elapsedMs, requestId);
            MDC.remove("requestId");
        }
    }
}
~~~

Ví dụ **Spring MVC/Servlet** dùng `OncePerRequestFilter`, Servlet, SLF4J/`MDC`, `UUID`, `TimeUnit`. UUID chỉ là **correlation ID**, không phải signing key. Filter **không log raw URI/header/body/claims**.

Filter ordering có thể bỏ sót `401`; cần quan sát ở gateway/ingress an toàn. Log cần retention và access control; WebFlux dùng `WebFilter`/Reactor Context, không phụ thuộc MDC truyền thread.

### 4.4. Body/error log và trường hợp exception

~~~java
// Sai: ném credential vào exception/log, kể cả khi HTTP call thất bại.
log.error("Partner call failed headers={} body={}",
          outboundHeaders, rawResponseBody);

// Tốt: log metadata có whitelist, response lỗi tách thành mã ổn định.
log.warn("partner_call_failed operation={} status={} requestId={}",
         "get-order", status, requestId);
~~~

Đừng trả nguyên `exception.getMessage()`, stack trace, `Authorization` hay JWT claims trong `ProblemDetail.detail`. Response `401 Unauthorized` nên mang thông tin an toàn theo hợp đồng và challenge `WWW-Authenticate` khi thích hợp; thông điệp “token validation failed because user email is ...” vừa lộ dữ liệu vừa khiến client phụ thuộc chi tiết nội bộ.

## 5. Chọn nơi giữ token theo loại ứng dụng

### 5.1. Server-to-server / OAuth client credentials

Confidential client có thể giữ client secret, private key hoặc workload identity để lấy access token. Token nên được cache theo **audience/scope và expiry**, có thời gian dự phòng trước khi hết hạn, không dùng token cùng audience cho API khác. Không log body token endpoint vì có `access_token`/`refresh_token`.

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=client_credentials&scope=orders.read

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"access_token":"<redacted>","token_type":"Bearer","expires_in":300}
~~~

Đây là ví dụ định dạng HTTP, **không chứa credential sử dụng được**. Nếu đối tác hỗ trợ `private_key_jwt`/mTLS hoặc workload identity, cân nhắc để giảm vòng đời long-lived client secret; vẫn phải quản lý và xoay signing key/chứng chỉ tương ứng.

### 5.2. Browser có cookie phiên

Với session cookie, đặt `Secure`, `HttpOnly`, `SameSite`, Path/Domain thích hợp và TTL giới hạn; ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

Tiền tố `__Host-` còn yêu cầu cookie không có `Domain` và `Path=/`; nó giúp giảm rủi ro cookie bị ghi đè qua subdomain, **không phải cơ chế xác thực độc lập**. Trình duyệt vẫn gửi cookie tự động theo quy tắc, vì thế API dùng cookie/session cần **CSRF protection** cho thao tác thay đổi trạng thái, kiểm tra Origin khi phù hợp. `HttpOnly` giảm nguy cơ JavaScript đọc cookie, không ngăn mọi hành vi XSS/CSRF.

**SPA/mobile public client không được cài client secret như một bí mật có thể giữ kín trong binary hoặc JavaScript.** Với OIDC/OAuth, dùng flow phù hợp như Authorization Code + PKCE; chỉ giữ token ở vị trí phù hợp threat model, hạn chế storage lâu dài và bảo vệ telemetry. Không chuyển access/refresh token vào URL redirect query, local logs hoặc analytics.

### 5.3. Refresh-token rotation

Một số authorization server phát **refresh token mới mỗi lần refresh**, vô hiệu hóa token trước và theo dõi **token family**. Nếu refresh token cũ bị tái dùng sau khi đã xoay, đây có thể là dấu hiệu bị đánh cắp: revoke family, yêu cầu đăng nhập lại và điều tra. Vì có thể tồn tại **race giữa hai tab/request hợp lệ**, cần đồng bộ refresh phía client hoặc thiết kế xử lý grace/reuse detection theo policy của IdP; đừng tắt replay detection chỉ để tránh race.

Không tự cài đặt refresh-token rotation trong REST resource server chỉ có nhiệm vụ xác minh access token nếu hệ thống đã có **OAuth Authorization Server/IdP**. Token có thể là opaque hoặc JWT; cách thu hồi nhanh phụ thuộc introspection, token store, denylist hoặc TTL, không chỉ giá trị `exp`.

## 6. Xoay API key và client secret mà không làm gián đoạn dịch vụ

**Rotation** thay credential đang dùng bằng credential mới. **Revocation** là làm credential hết hiệu lực. Hai hành động này khác nhau: trong xoay thường lệ, ta cần **khoảng chồng lấn cũ/mới** để các consumer chuyển dần; khi credential bị đánh cắp, phải ưu tiên thu hồi sớm hơn tính liên tục và kích hoạt quy trình ứng cứu.

### 6.1. Runbook xoay thường lệ

| Bước | Bên phát hành / bên sử dụng | Điều kiện hoàn thành |
|---|---|---|
| **1. Kiểm kê** | Xác định owner, consumer, scope, TTL, version, dependency | Biết ai sẽ bị ảnh hưởng và cách rollback |
| **2. Phát hành** | Tạo **v2** trong secret manager/IdP, vẫn giữ **v1** hợp lệ | v2 dùng được ở môi trường thử nghiệm |
| **3. Chấp nhận song song** | Provider hỗ trợ v1/v2 trong grace window nếu protocol cho phép | Không gián đoạn traffic hiện tại |
| **4. Phân phối** | Cập nhật secret reference/mount; refresh provider/client pool | Các workload nạp v2, không lộ giá trị |
| **5. Chuyển gửi** | Chỉ dùng v2 để tạo request/ký mới; v1 chỉ xác minh request cũ | Quan sát error rate, success rate theo **key version ID** |
| **6. Xác nhận** | Kiểm tra mọi consumer, job chậm, batch, queue, DR site | Không còn traffic hợp lệ dùng v1 |
| **7. Thu hồi** | Disable/revoke v1, xóa bản sao không cần thiết | Test request v1 bị từ chối; cập nhật audit |

**Grace window** phụ thuộc TTL, refresh, cache và consumer ngoại tuyến. Nếu nhà cung cấp chỉ cho **một key hoạt động**, cần cutover theo lịch; không giả định luôn hỗ trợ dual-key.

**Rollback có giới hạn:** nếu v2 gây lỗi *và v1 chưa bị lộ*, có thể tạm quay lại trong cửa sổ đã lên kế hoạch. Nếu v1 bị compromise, **không rollback sang credential đã lộ** chỉ để phục hồi availability.

### 6.2. Java/Spring đọc credential mới cho mỗi lần gọi

~~~java
interface CredentialProvider {
    // Lấy từ cache được refresh bởi secret manager, không từ Git.
    String currentApiKey();
}

@Component
class PartnerOrderClient {
    private final WebClient webClient;
    private final CredentialProvider credentials;

    PartnerOrderClient(WebClient.Builder builder,
                       CredentialProvider credentials) {
        this.webClient = builder
            .baseUrl("https://partner.example.com").build();
        this.credentials = credentials;
    }

    Mono<OrderDto> get(String orderId) {
        return Mono.defer(() -> webClient.get()
            .uri("/v1/orders/{id}", orderId)
            .headers(h -> h.set("X-Api-Key", credentials.currentApiKey()))
            .retrieve()
            .bodyToMono(OrderDto.class));
    }
}
~~~

`Mono.defer` giúp lấy credential vào **lúc subscribe**, tránh chốt key ngay khi lắp pipeline. `CredentialProvider` phải được hiện thực có **atomic snapshot/version**, đồng bộ refresh, TTL có giới hạn, xử lý secret manager outage và không log key. Không tự retry `401` vô hạn: cần phân biệt key hết hạn với thiếu quyền, rate limit hoặc policy của provider. Với API dùng OAuth bearer token, gửi `Authorization` và xử lý cache token qua OAuth client; không tự đổi nó thành custom API key header.

**Về verifier:** khi API key là chuỗi ngẫu nhiên có entropy cao, có thể lưu **digest/HMAC có pepper được bảo vệ** và `keyId` để tra cứu, so sánh giá trị xác minh theo cách không rò timing, không lưu plaintext nếu nghiệp vụ không yêu cầu khôi phục. Không tự tạo giao thức xác thực từ mật khẩu người dùng bằng cách SHA-256 một lần; password cần KDF chuyên dụng như Argon2id/bcrypt/scrypt.

## 7. Xoay khóa ký JWT và JWKS: khác xoay access token

Trong hệ JWT bất đối xứng, **Authorization Server/IdP** giữ private key để ký; **resource server** tải các **public verification keys** từ endpoint JWKS đáng tin. `kid` trong JWT header chỉ định phiên bản khóa, **không phải bí mật và không phải URL mà client được tùy ý yêu cầu server truy cập**.

~~~json
{
  "keys": [
    {"kty":"RSA","kid":"signing-2026-11","use":"sig","alg":"RS256",
     "n":"<public-modulus>","e":"AQAB"},
    {"kty":"RSA","kid":"signing-2026-12","use":"sig","alg":"RS256",
     "n":"<new-public-modulus>","e":"AQAB"}
  ]
}
~~~

Đây là **JWKS mô phỏng, không phải khóa hợp lệ**. **Không đưa private key, HMAC signing secret hay token vào JWKS**. Với HMAC `HS256`, các bên xác minh dùng cùng secret nên phải phân phối qua secret manager theo trust boundary; không công bố nó trong JWKS công khai.

### 7.1. Rollover khóa ký không downtime

~~~text
T0: JWKS có public key K1, IdP ký token bằng private K1
T1: Công bố public K2 vào JWKS, tiếp tục ký K1
T2: Đợi resource servers/cache nhận K2; thử xác minh K2
T3: IdP bắt đầu ký token mới với K2, JWKS còn K1 + K2
T4: Đợi token K1 còn hiệu lực hết hạn + clock skew/cache budget
T5: Gỡ K1 khỏi JWKS, revoke/archive private K1 theo policy
~~~

T3–T4 phải xác minh token K1 còn hạn; JWKS cache có thể chỉ refresh định kỳ. Không gỡ K1 ngay sau khi publish K2. Opaque token/introspection có cơ chế thu hồi khác JWT.

### 7.2. Verifier phải chặn JWT giả dù JWKS hợp lệ

Resource server cần xác minh **chữ ký với thuật toán cho phép**, `iss`, `aud`, `exp`, `nbf` khi áp dụng, clock skew hợp lý, và scope/role tại endpoint. Không chấp nhận `alg=none`, không tự đổi thuật toán theo header không tin cậy, không dùng `kid` làm file path/SQL/URL; chỉ lookup trong **JWKS origin đã cấu hình tin cậy**. Một JWT có chữ ký đúng nhưng audience thuộc API khác **vẫn phải bị từ chối**.

**Khóa ký bị lộ là tình huống khác rollover định kỳ:** không giữ K1 xác minh để “chờ hết TTL” nếu attacker có thể ký token giả. Phải xoay sang K2, **loại K1 khỏi trust**, cân nhắc invalidate phiên/refresh token, dùng denylist/introspection/re-auth khi cần và thông báo sự cố theo quy trình. Với token đã phát bằng K1, có thể xảy ra logout diện rộng; đó là đánh đổi an toàn cần dự liệu.

## 8. Spring Security: xác minh bearer token, không tự parse JWT

Resource server Spring Boot nên dùng **Spring Security OAuth2 Resource Server**, không tự lấy `Authorization` rồi giải mã Base64 JWT và tin các claim. Ví dụ cấu hình cho bearer JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
# Bổ sung audience validation theo contract: orders-api.
# JWKS URI/TTL được kiểm soát bởi cấu hình trusted issuer/runtime.
~~~

~~~java
@Configuration
class ApiSecurityConfig {
    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(s ->
                s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/v1/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đây là ví dụ **Spring MVC/Servlet, Boot 3.x**: cần dependency Spring Security/resource-server, cấu hình issuer/JWKS tin cậy và **audience validator `orders-api`** trước khi production. `issuer-uri` hỗ trợ discovery/validate issuer theo cấu hình; **không suy rằng audience đã được kiểm tra đúng chỉ vì JWT có chữ ký hợp lệ**. Role/scope chỉ có ý nghĩa sau khi token được xác minh; service vẫn cần BOLA/tenant check cho từng order.

**CSRF:** ví dụ là API bearer stateless, không cung cấp cấu hình cookie/session. Chỉ tùy chỉnh CSRF sau khi xác định client authentication và phương thức thay đổi trạng thái; nếu trình duyệt gửi cookie session tự động, phải bảo vệ CSRF. JWT dùng Authorization header **không được ghi log** dù `401`/`403`/`500`.

Để log lỗi xác thực, chỉ lưu **error category**, status, request ID và endpoint/route an toàn. Không log raw token, `Jwt.getTokenValue()`, toàn bộ `Authentication`/principal claims, hoặc body token endpoint. Trong `@RestControllerAdvice`/`AuthenticationEntryPoint` có thể trả Problem Details trung tính, không tiết lộ giá trị token hay cấu hình khóa.

## 9. Khi phát hiện secret bị lộ: quy trình khẩn cấp

Giả sử phát hiện `client_secret` trong CI output hoặc private signing key trong image layer. **Không chỉ xóa dòng log hoặc commit mới**: nội dung đã có thể bị tải xuống, đồng bộ, backup hoặc truy cập bởi bên thứ ba.

1. **Xác định phạm vi:** loại secret, credential ID/version, hệ thống phát hành, quyền, thời điểm khả năng lộ, vị trí artifact/log và consumer ảnh hưởng. Không copy secret nguyên văn sang ticket ứng cứu.
2. **Khoanh vùng:** chặn quyền đọc thêm, khóa publication/artifact nếu cần; bảo tồn chứng cứ theo quy trình nhưng giới hạn truy cập.
3. **Xoay/thu hồi:** phát hành credential mới và **disable credential lộ càng sớm càng an toàn**. Với signing key có thể cần vô hiệu token cũ, buộc đăng nhập lại; với database key kiểm soát connection pool và session đang tồn tại.
4. **Đánh giá hậu quả:** truy vấn audit, requests bất thường, phạm vi dữ liệu, log truy cập; không giả định “chưa thấy abuse” là “không có abuse”.
5. **Phục hồi:** xác nhận consumer mới chạy, kiểm tra 401/403, latency, downstream failures; loại credential cũ khỏi trust và artifacts.
6. **Ngăn tái diễn:** sửa log pipeline, secret scanning, IAM/RBAC, TTL/rotation policy; rà bản sao trong Git history, backups và export theo chính sách lưu giữ/tuân thủ.

**Rotation khẩn cấp và rotation thường lệ có SLO khác nhau**: thường lệ ưu tiên không downtime qua overlap; khẩn cấp ưu tiên **giảm cửa sổ attacker có thể dùng credential**, chấp nhận gián đoạn có kiểm soát. Ghi nhận thời điểm *phát hiện → thu hồi → khôi phục* và kiểm tra lại khóa đã bị vô hiệu thực sự.

## 10. Kiểm thử bảo mật: credential không lọt qua log và rotation thật sự hiệu lực

| Ca | Đầu vào / sự kiện | Kết quả bắt buộc |
|---|---|---|
| S01 | Gửi `Authorization: Bearer SECRET_SENTINEL` | Không có sentinel trong app/access/error log, trace, response |
| S02 | `401` do token sai/hết hạn | Có status/challenge đúng, không phản chiếu token hoặc JWT claims |
| S03 | Caller hợp lệ nhưng scope/tenant sai | `403`/`404` đúng policy, không lộ resource |
| S04 | API key v1/v2 trong cửa sổ overlap | Hai credential hợp lệ **chỉ trong khoảng cho phép** |
| S05 | Sau revoke v1 | v1 bị từ chối, v2 vẫn hoạt động |
| S06 | JWT ký K2 khi JWKS đã publish K1+K2 | Resource server xác minh được với `kid` K2 |
| S07 | Token ký K1 sau khi revoke khẩn cấp | Bị từ chối; không tin cache cũ quá policy |
| S08 | JWT đúng signature nhưng `aud`/`iss` sai | `401`, không trở thành principal |
| S09 | JWT có `alg=none` hoặc `kid` bất thường | Bị từ chối, không tải JWKS từ URL do token đề xuất |
| S10 | Secret manager refresh thất bại | Không log secret/cấu hình; fallback/fail-closed theo policy |
| S11 | Job batch dùng credential cũ sau cutover | Cảnh báo bằng version ID, không log key |
| S12 | Token xuất hiện trong CI fixture/dump giả lập | Secret scanning/DLP phát hiện và chặn artifact |

### 10.1. Java test ghi nhận output của filter

~~~java
@Test
void requestLoggingNeverPrintsBearerToken() throws Exception {
    String marker = "SECRET_SENTINEL_DO_NOT_LOG";
    var logger = (ch.qos.logback.classic.Logger)
        LoggerFactory.getLogger(SafeRequestLogFilter.class);
    var appender = new ListAppender<ILoggingEvent>();
    appender.start();
    logger.addAppender(appender);

    try {
        var req = new MockHttpServletRequest("GET", "/v1/orders/o-42");
        req.addHeader("Authorization", "Bearer " + marker);
        var res = new MockHttpServletResponse();
        new SafeRequestLogFilter().doFilter(
            req, res, (request, response) -> {});

        assertTrue(appender.list.stream().noneMatch(
            event -> event.getFormattedMessage().contains(marker)));
    } finally {
        logger.detachAppender(appender);
        appender.stop();
    }
}
~~~

Ví dụ dùng JUnit 5, Spring MockHttpServletRequest/Response, SLF4J và Logback Test `ListAppender`. Nó kiểm tra **logger của filter**, chưa chứng minh gateway, APM, HTTP wiretap hay exception handler khác không log token; cần **integration test có capture toàn đường xử lý** và test cấu hình telemetry ở môi trường gần production.

### 10.2. Test rotation theo pha, không chỉ “key mới hoạt động”

Tạo môi trường giả lập secret provider có **key ID v1/v2**. Test: phát hành v2 → request dùng v1 và v2 thành công trong overlap → tất cả consumer đổi sang v2 → revoke v1 → request v1 thất bại, v2 vẫn thành công. Với JWT, phát K2 public trước khi ký K2, xác minh `iss/aud/exp/kid`, mô phỏng JWKS cache và thời điểm gỡ K1. Test cả **rotation không đồng bộ, network timeout và rollback chưa bị compromise**.

Đừng dùng real production secret trong test; dùng sentinel/khóa thử nghiệm được quản lý riêng. Test âm tính cho `Authorization` trong response, log/trace và issue metadata quan trọng không kém test status 200.

## 11. Bài tập và đáp án

**Tình huống:** một Spring Boot worker gọi API đối tác bằng `X-Api-Key` đọc từ environment variable. Hôm nay key xuất hiện trong debug log; đối tác cho phép tối đa hai key hoạt động đồng thời. Hãy đề xuất xử lý và chứng minh sự cố đã được khắc phục.

**Gợi ý:** (1) coi key đã lộ; kiểm tra logs/artifacts và giới hạn truy cập, không paste giá trị vào ticket; (2) phát hành v2 trong secret manager, phân phối tới worker; (3) xác minh v2 thành công, chuyển mọi consumer và batch job sang v2; (4) **revoke v1 sớm**, kiểm tra v1 bị từ chối và audit các request nghi ngờ; (5) bỏ debug/wiretap, cấu hình logging allowlist và secret scanning; (6) test không có marker trong app/gateway/APM logs và deployment restart/reload vẫn dùng v2.

**Câu hỏi mở:** nếu chính **private key ký JWT** bị lộ, có nên đợi access token cũ hết hạn mới gỡ K1 khỏi JWKS không? **Không**: đó là hướng cho *rotation thường lệ*, không phải *compromise*. Phải loại khóa lộ khỏi trust sớm, xử lý token/session đã ký bằng khóa ấy và đánh giá tác động reauthentication.

## 12. Checklist production và tài liệu tham khảo

- [ ] Không có secret/token trong Git, image, CI output, URL, logs/traces/metrics và response lỗi.
- [ ] Secret được phát hành an toàn, có owner/TTL/scope, lưu secret manager/KMS/HSM và IAM tối thiểu.
- [ ] Consumer reload theo version; đã test startup, refresh failure, rotation overlap và revoke.
- [ ] JWT verifier xác minh signature/algorithm, `iss`, `aud`, `exp`; JWKS chỉ công bố public key.
- [ ] Access/refresh token có TTL và replay/rotation policy phù hợp; cookie/session có CSRF control.
- [ ] Log/telemetry **allowlist**, có retention/access audit, không chỉ regex redact tên `password`.
- [ ] Runbook khẩn cấp có owner, cách revoke, kiểm chứng cũ bị từ chối và quan sát sự cố.
- [ ] Có test bảo mật ở mức unit, HTTP integration, gateway, CI và secret scanning.

**Nguồn:** [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750), [RFC 9700 — OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700), [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), [Spring Security OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html), [Kubernetes Secrets good practices](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

**Kết luận:** bảo vệ credential là quản lý **vòng đời**, không chỉ mã hóa ở một vị trí. Secret phải được phân phối qua ranh giới tin cậy, **không xuất hiện trong log/trace**, được xoay theo version và **thu hồi thực sự** khi bị lộ. HTTP/Java/Spring đúng hợp đồng chỉ an toàn khi các bước phát hành, sử dụng, quan sát, kiểm thử và ứng cứu đều được kiểm soát.
