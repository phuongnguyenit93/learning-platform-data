# Token leakage qua log

Một **access token**, **refresh token**, **session cookie** hoặc credential OAuth có thể được bảo vệ bằng TLS trên đường truyền và bằng mã hóa khi lưu, nhưng vẫn bị lộ chỉ vì một dòng log:

```text
DEBUG outgoing request:
GET https://orders.example.test/v1/orders
Authorization: Bearer ACCESS_TOKEN_TEST_ONLY_DO_NOT_USE
```

Nếu đây là token thật, bất kỳ ai đọc được log — kỹ sư hỗ trợ, hệ thống phân tích, nhà cung cấp dịch vụ quan sát, tài khoản CI bị xâm nhập hoặc kẻ tấn công lấy bản sao log — có thể có cơ hội **sao chép credential và sử dụng lại**. Đối với **bearer access token**, possession thường đủ để gọi API trong phạm vi `aud`/`scope`/`exp` mà resource server cho phép. Đối với **refresh token**, hậu quả có thể nghiêm trọng và kéo dài hơn: attacker có thể thử xin access token mới từ authorization server (AS) nếu thiếu các ràng buộc hoặc biện pháp phát hiện sử dụng lại cần thiết.

**Quy tắc cốt lõi:** *token và credential không phải dữ liệu phục vụ quan sát; chúng là bí mật hoặc tài sản bảo mật phải được loại khỏi logs, traces, metrics, crash dumps, support tickets và dữ liệu xuất từ hệ thống quan sát.* Không chỉ “ẩn một phần JWT cho đẹp”: phải thiết kế để **không thu thập raw credential ngay từ đầu**.

```mermaid
flowchart LR
    C[Client / Browser / Service] -->|Authorization: Bearer| GW[Gateway / WAF]
    GW --> APP[Java / Spring API]
    APP --> OUT[Downstream API]
    GW -. unsafe HTTP logging .-> COL[Log / Trace Collector]
    APP -. exception / debug / MDC .-> COL
    OUT -. HTTP wire debug .-> COL
    COL --> SIEM[Search / APM / SIEM]
    SIEM --> EXP[Dashboards / Export / Backups / Support]
    EXP -. leaked token .-> ATK[Attacker or overprivileged reader]
    ATK -. credential replay .-> APP
```

TLS không giúp gì nếu token bị in **sau khi TLS được giải mã** tại gateway/service. JWT có chữ ký mạnh không ngăn credential được gửi lại nguyên vẹn. JWE có mã hóa payload cũng không tự ngăn **replay nguyên ciphertext bearer token**. Vì thế, chống rò rỉ qua log là một phần độc lập của **vòng đời token** và cần được kiểm thử cùng OAuth 2.0/OIDC, token storage, audience, scope và revocation.

Bài học này thuộc chương **Threats**, chủ đề **“Token leakage qua log”**, của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Phạm vi module là nắm mô hình tin cậy và vòng đời token, phân biệt JWT/opaque, access/refresh, ứng dụng trong xác thực, phân quyền và OAuth 2.0/OIDC; phát hành, kiểm claims/scope/audience, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại. Bài tập trung vào **đường đi của credential vào log, cách phòng ngừa, cách phát hiện và xử lý khi log đã chứa token thật**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao **bearer token trong log tương đương một credential có thể bị sao chép**, kể cả JWT đã ký hoặc JWE đã mã hóa.
2. Nhận diện các dạng dữ liệu nguy hiểm: `Authorization`, `Cookie`, `Set-Cookie`, refresh token, authorization code, PKCE verifier, client secret, ID token và token endpoint response.
3. Vẽ **data flow** qua gateway, servlet filters, interceptors, HTTP clients, APM, OpenTelemetry, tracing, CI/CD, log collectors, data lake và backups.
4. Phân biệt rủi ro **access token theft**, **refresh token theft**, **session cookie theft**, **ID token disclosure** và **client credential leak**.
5. Thiết kế **log allowlist**, field-level minimization, structured logging, sanitization trước ingestion, retention, access control và safe correlation identifiers.
6. Nhận diện anti-pattern trong Java/Spring: `request.getHeader("Authorization")`, `log.debug("{}", request)`, response body logging, wiretap và exception-to-string.
7. Áp dụng mã Java/Spring minh họa cho **request metadata logging không chứa secrets**, HTTP client filter chỉ ghi status/method, và error handling không trả raw token.
8. Kiểm thử **synthetic canary tokens**, log sinks, traces, metrics, incident exports và “không có token trong log” như một security invariant.
9. Thực hiện runbook khi log đã lộ credential: **contain → identify → revoke/rotate → invalidate sessions/grants → investigate usage → remediate pipeline → verify**.
10. Kết hợp TTL, scope, audience, DPoP/mTLS, refresh rotation và revocation để **giảm blast radius**, không dùng chúng thay việc ngăn log leak.

## 2. Vì sao token lộ trong log là vấn đề bảo mật?

### 2.1. Bearer nghĩa là bên cầm token có thể thử sử dụng token

OAuth 2.0 bearer-token usage (RFC 6750) dựa trên khả năng bên nhận access token **xuất trình** token. Resource server quyết định cho phép dựa trên issuer/trust, audience, expiry, scope, grant state và các quy tắc khác. Nếu attacker có cùng chuỗi bearer token, signature không tự phân biệt attacker với client hợp lệ.

```text
Normal request:
  Legitimate client --Bearer T--> Orders API

Log leak:
  Orders API or gateway --"Authorization: Bearer T"--> Log store
  Unauthorized reader --copy T--> Replay to Orders API

Unless additional controls block replay:
  same token T, same cryptographic signature, same claims.
```

**Giới hạn cần nói rõ:** Không phải mọi token bị lộ đều sẽ dùng lại thành công: nó có thể đã hết hạn, bị revoke, bị giới hạn audience/scope, cần DPoP/mTLS proof hoặc có policy chặn bất thường. Nhưng việc token có thể không còn dùng được **không làm hành vi ghi credential vào log trở nên chấp nhận được**.

### 2.2. JWT payload không phải dữ liệu mật chỉ vì có Base64url

Một JWT dạng JWS thường có:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Phần payload có thể chứa `sub`, `aud`, `scope`, `tenant_id`, thời gian hoặc PII do hệ thống đưa vào. Chữ ký giúp phát hiện sửa đổi nếu được verify, **không mã hóa nội dung**. Người đọc log có thể thu được cả **credential có thể replay** lẫn **metadata/PII**.

Không log “chỉ hai phần đầu” của JWT: header/payload vẫn có thể tiết lộ danh tính, quyền, tenant và key IDs; việc cắt bớt chữ ký không phải một privacy policy đủ.

### 2.3. JWE mã hóa vẫn là một bearer token

JWE có thể che claims khỏi người không có decryption key, nhưng nếu API chấp nhận **nguyên compact JWE** qua `Authorization: Bearer`, attacker không cần decrypt để replay. **Encryption at rest hoặc in-token confidentiality không thay credential redaction.**

### 2.4. Refresh token có thể kéo dài cửa sổ tấn công

Refresh token được gửi tới **AS token endpoint** để xin access token mới; token này thường cần được bảo vệ nghiêm hơn access token vì lifetime/quyền renew. Nếu log chứa refresh token, attacker có thể thử dùng nó trước khi hết hạn hoặc bị revoke. Rotation/reuse detection có thể giúp phát hiện/chặn tùy client binding và AS policy, nhưng **không đảm bảo việc leak là vô hại**.

### 2.5. Một log event dễ có nhiều bản sao

```text
Application stdout
  -> container log driver
  -> node daemon / log sidecar
  -> collector with persistent queue
  -> central log index
  -> APM trace attachment
  -> dashboard saved search
  -> exported CSV / ticket attachment
  -> object-storage backup
  -> disaster-recovery replica
```

Xóa dòng trên dashboard **không đồng nghĩa** xóa credential ở các hệ thống khác. Điều này ảnh hưởng trực tiếp đến **incident scope, containment, deletion/retention và audit**.

## 3. Phân loại credential và hậu quả khi bị ghi log

| Dữ liệu | Thường xuất hiện ở đâu? | Rủi ro khi lộ | Ghi log an toàn? |
| --- | --- | --- | --- |
| **Bearer access token** | `Authorization` request, SDK debug, proxy | API replay tới đúng audience trong thời hạn | Không log raw token |
| **Refresh token** | Token endpoint request/response, DB debug | Xin token mới, đe dọa phiên/grant lâu dài | Không log raw token |
| **ID token** | OIDC callback/token response, RP session | Rò identity claims/PII, token confusion nếu RP sai | Không log raw token |
| **Authorization code** | OAuth redirect callback `?code=...` | Có thể đổi token nếu ràng buộc PKCE/client không đủ | Không log raw code hoặc callback URL |
| **PKCE code verifier** | Client storage, token endpoint form | Giảm bảo vệ code interception nếu lộ cùng code | Không log verifier/challenge transaction secrets |
| **Client secret / Basic auth** | Token/introspection endpoint, configs | Giả mạo confidential client trong phạm vi cho phép | Không log |
| **`private_key_jwt` assertion** | OAuth client authentication | Credential ngắn hạn có thể bị replay nếu AS controls yếu | Không log assertion |
| **Session cookie** | `Cookie`/`Set-Cookie`, browser | Session hijacking/replay nếu không ràng buộc | Không log |
| **API key / mTLS private material** | Headers/config/TLS setup | Service/API impersonation | Không log |
| **DPoP proof JWT** | `DPoP` request header | Có thể hỗ trợ replay trong bound window nếu bị thu cùng token; lộ metadata | Không log raw proof |
| **Signed JWT payload/claims** | Debug serialization, exceptions | PII/tenant/scope leakage, correlation risk | Không log raw; dùng allowlist metadata |
| **JWE ciphertext** | HTTP logs, APM | Replay encrypted bearer token | Không log raw |
| **Token fingerprint (HMAC)** | Safe audit nếu thật cần | Có thể tạo stable cross-event identifier | Chỉ log khi có chính sách, key/retention controls |

**Chú ý:** `code_challenge` PKCE thường được gửi công khai trong authorization request, khác `code_verifier` bí mật dùng tại token exchange. Nhưng authorization request URL vẫn chứa `state`, client identifiers, redirect context và các tham số có thể nhạy cảm; không nên ghi nguyên URL chỉ vì một số trường vốn public.

### 3.1. ID token và access token không hoán đổi được

OIDC ID token phục vụ RP xác minh login; OAuth access token phục vụ RS authorization. **ID token không phải credential Bearer gọi API nghiệp vụ theo profile thông thường**, nhưng leak ID token vẫn là privacy/security incident. Nếu RS/RP sai khi chỉ kiểm chữ ký bỏ `aud`/`typ`, cross-JWT confusion có thể làm hậu quả nặng hơn.

### 3.2. Sender-constrained token không cho phép bỏ redaction

DPoP/mTLS-bound access tokens có thể giảm khả năng replay khi attacker chỉ lấy được access token mà **không có private proof key/certificate**. Nhưng:

- Log đôi khi chứa **cả token lẫn DPoP proof** trong cùng event.
- Compromised workload có thể có cả key material/proof signing access.
- Xác minh DPoP `htu`/`htm`/`ath`/`iat`/`jti`/nonce hoặc mTLS `cnf` vẫn phải đúng.
- Leak vẫn có thể tiết lộ metadata/PII và tạo attack opportunities khác.

**Vì thế sender-constraining là defense-in-depth, không phải giấy phép ghi token vào log.**

## 4. Threat model: ai có thể đọc log?

Trong thiết kế, cần xem log như **một hệ thống dữ liệu thứ hai** với nhiều consumer hơn database sản xuất.

| Tác nhân | Khả năng | Tại sao token bị log có thể nguy hiểm? |
| --- | --- | --- |
| Support engineer | Xem dashboard, tìm request IDs | Có thể vô ý copy token sang ticket/chat |
| Developer | Xem dev/prod traces theo quyền | Debug “print request” có thể làm secrets phân tán |
| CI/CD runner | Thu stdout của tests/build/deploy | Artifact/traces lưu lâu và truy cập rộng |
| APM/SIEM vendor/operator | Nhận events/traces | Shared-responsibility, retention và quyền truy cập ngoài app |
| Compromised log collector | Đọc spool, queue, tokenized payload | Thu thập số lượng lớn bearer credentials |
| Attacker có quyền read-only log | Không có quyền DB/KMS/AS | Vẫn có thể replay token còn hiệu lực |
| Insider có quyền export | Trích CSV/JSON, gửi email | Mở rộng phạm vi lưu secrets |
| Application/infra admin | Bật DEBUG/wiretap | Vô ý ghi inbound/outbound token |
| Malicious external client | Điều khiển header/path/body trong request | Log injection, data pollution, DoS, có thể ép log credential khác qua lỗi |

### 4.1. Tài sản cần bảo vệ

1. Raw bearer values và refresh token family credentials.
2. Confidential client credentials và cryptographic proof keys.
3. User/session identifiers, PII, authentication context và tenant affiliations.
4. Token grant/consent state và khả năng phát hành token mới.
5. Tính toàn vẹn của incident/audit logs và quá trình truy vết.
6. Chính sách retention/access/export của mọi bản sao logs.

### 4.2. Sự cố điển hình

```mermaid
sequenceDiagram
    participant U as Legitimate Client
    participant API as Resource Server
    participant LOG as APM / Central Log Store
    participant X as Unauthorized Log Reader
    U->>API: GET /orders + Bearer T
    API->>LOG: Debug logs full HTTP headers, including T
    X->>LOG: Read/export event containing T
    LOG-->>X: Captured bearer T
    X->>API: Replay Bearer T before expiry/revocation
    API-->>X: Response if token and policy still allow
```

Không cần giả định attacker phá TLS hoặc SHA/RSA. **Log read permission trở thành đường truy cập có thể thay thế credential authentication** — đó là một trust-boundary failure.

### 4.3. Blast radius không đồng nhất

Hậu quả tùy thuộc:

- **Loại token:** access vs refresh vs ID vs cookie vs client credentials.
- **TTL:** còn bao lâu tới `exp`, có refresh capability không?
- **Issuer/audience:** token dành API nào, AS nào? RS có kiểm `aud` không?
- **Scope/roles:** `read` hay `write`/admin? Resource-level authorization có chặt không?
- **Sender binding:** có DPoP/mTLS thực sự được verify không?
- **Revocation awareness:** RS dùng introspection/denylist/grant version hay offline JWT validation?
- **Quyền đọc log và thời gian retention:** một event hay nhiều bản sao, ai có quyền?

**Không kết luận “token đã hết hạn nên không cần điều tra”** khi log có refresh token/client secret hoặc khi thời gian log exposure trước expiry chưa được xác minh.

## 5. Bản đồ vị trí token có thể lọt vào logs

### 5.1. Gateway, reverse proxy, WAF và load balancer

Các proxy thường log metadata request (method, path, status, client address). Một số cấu hình/debug extensions có thể log:

- `Authorization` và `Proxy-Authorization`.
- `Cookie`/`Set-Cookie`.
- Full URL chứa `?access_token=...`, `?code=...`, `?state=...`.
- Request/response bodies khi bật inspection.
- Headers trả về từ AS/token endpoint.
- Rewritten URLs hoặc forwarded headers.

**Không mặc định** proxy nào cũng log Authorization theo cấu hình mặc định; **kiểm cấu hình thực tế**. An toàn hơn là **log route template hoặc path đã loại secrets**, không full query string.

### 5.2. Java/Spring application

Các điểm dễ gây leak:

```java
// ANTI-PATTERNS — các ví dụ sau không được dùng trong production.
log.debug("headers: {}", request.getHeader("Authorization"));
log.debug("request: {}", request);
log.info("token response: {}", tokenResponse);
log.error("OAuth failed: " + exception.getMessage());
log.info("request DTO: {}", loginOrRefreshRequest);
log.debug("outgoing HTTP: {}", clientRequest);
```

Rủi ro tăng khi DTO có `toString()` sinh tự động (records/Lombok/data classes), exception message chứa URL/header/body, hoặc một HTTP client interceptor ghi toàn bộ request/response.

### 5.3. OAuth authorization endpoint và callback

OAuth Authorization Code flow thường chuyển trình duyệt tới callback với `code` và `state` trong query (hoặc profile/response mode phù hợp). Web server access logs ghi full URI có thể thu **authorization code**; browser history, diagnostics và referrer cũng cần bảo vệ.

**PKCE S256 và one-time code** giảm khả năng khai thác riêng authorization code, nhưng không thay chính sách không log code, không chữa leak nếu `code_verifier`/client credential cùng bị lộ.

### 5.4. Token endpoint request/response

OAuth token endpoint thường dùng `application/x-www-form-urlencoded`, với các trường như:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_CREDENTIALS_TEST_PLACEHOLDER

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_TEST_ONLY
```

Nếu interceptor log **request body**, `refresh_token` bị lộ. Nếu response logger in JSON token response:

```json
{
  "access_token": "ACCESS_TOKEN_TEST_ONLY",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "REFRESH_TOKEN_TEST_ONLY"
}
```

**Mọi giá trị trên là placeholder**, không phải credential sử dụng được. Trong production, **không log raw request/response body của token endpoint**, kể cả ở DEBUG/TRACE.

### 5.5. Outbound HTTP clients và retry

`RestTemplate`, `RestClient`, `WebClient`, Feign, Apache HttpClient, OkHttp hoặc Reactor Netty có thể bị gắn interceptor/wire logger cho debug. Khi client gọi downstream API, log request headers/body có thể in `Authorization: Bearer`. Retry/error handler có thể capture request lại vào exception.

### 5.6. Telemetry và asynchronous processing

Một credential có thể lọt vào:

- OpenTelemetry span attributes/events, exemplars, baggage hoặc instrumentation hooks.
- Traces được lưu trên APM và sample “failed requests”.
- MDC/thread context truyền qua asynchronous callbacks, queues và batch jobs.
- Dead-letter queue, Kafka/RabbitMQ message dumps khi payload chứa token.
- Server-side exception report và crash dump/heap dump.
- Browser console, frontend error tracking, mobile crash reports.
- Pipeline exports và dashboards dùng chung.

**Không suy rằng trace ID/request ID là nơi lưu bí mật**. Correlation identifiers phải được tạo/kiểm theo policy, không reuse raw token.

## 6. Các anti-pattern cụ thể cần nhận biết

| Anti-pattern | Ví dụ ngắn | Vì sao sai? | Thay thế |
| --- | --- | --- | --- |
| **Log toàn bộ headers** | `log.info("{}", headers)` | Có Authorization/Cookie/API keys | Allowlist method/status/route |
| **Log full request URI** | `request.getRequestURL()+"?"+query` | Có code/token/query secret | Route template không query |
| **Log token response** | `log.debug("{}", oauthTokenResponse)` | Access+refresh token | Event `token_issued` + safe metadata |
| **Log DTO mặc định** | `log.info("{}", refreshRequest)` | `toString` chứa refresh token | DTO safe projection/event |
| **Log JWT claims** | `log.info("{}", claims)` | PII/scope/tenant | Allowlist policy-safe fields |
| **Bật wiretap ở production** | HTTP client full frames | Headers/body bị capture | Disabled/payload-redacting instrumentation |
| **Log exception message tùy ý** | `log.error("{}", ex.getMessage())` | Message có URL/token | Safe error code + restricted stack if sanitized |
| **Đưa token vào MDC** | `MDC.put("token", token)` | Lan sang mọi log trong request | MDC chỉ có safe correlation ID |
| **Đưa token vào OpenTelemetry baggage** | `baggage.put("auth", token)` | Baggage lan qua services | Baggage chỉ values ít nhạy cảm/allowlisted |
| **Chỉ mask 5 ký tự đầu** | `eyJhb...` | JWT claims có thể còn lộ; partial token có rủi ro | Không log credential |
| **Chỉ dùng regex cuối pipeline** | Replace sau ingestion | Raw secrets đã đi qua collector/queue | Prevent collection + source redaction |
| **Xóa một dashboard là xong** | Delete search result | Spool/export/backup vẫn còn | Full incident scope/remediation |
| **In token để correlate requests** | `log.info("token={}", token)` | Biến log thành secret store | Random request/transaction ID |
| **Trả raw error body vào logs** | `log.error("{}", responseBody)` | OAuth error may contain sensitive fields | Error category/status only |
| **Log secrets khi failed auth** | `invalid JWT: {}` token | Attacker có thể ép log hàng loạt | Count/reason code, no raw input |

## 7. Thiết kế logging an toàn ngay từ đầu

### 7.1. “Log allowlist” tốt hơn “redact denylist”

**Default policy:** Chỉ log trường có mục đích quan sát rõ, không chứa credential. Ví dụ:

```json
{
  "event": "api_request_completed",
  "request_id": "req-test-7d3",
  "http_method": "GET",
  "route_template": "/v1/orders/{orderId}",
  "status_code": 200,
  "duration_ms": 42,
  "auth_result": "valid",
  "resource_ref": "orders-api"
}
```

Trong event này **không có** `Authorization`, `Cookie`, raw URL query, user token hoặc response body. Route template đến từ **trusted routing metadata**, không sao chép path với ID/token tùy ý. `request_id` phải là giá trị được tạo hoặc validate/canonicalize; attacker-controlled correlation ID cũng có thể tạo log injection/high-cardinality noise.

### 7.2. Chính sách trường nên được review như API contract

| Trường | Có thể log? | Ghi chú |
| --- | --- | --- |
| Event name, service, deployment version | Thường có | Kiểm tránh secret trong version/env |
| HTTP method | Có | Method được chuẩn hóa |
| Route template | Có nếu trusted | Không raw path/query |
| Status code, latency, error category | Có | Không raw exception message chứa token |
| Correlation/request ID | Có nếu safe | Random/trusted, bounded length/charset |
| JWT issuer ref | Có nếu mapped trusted | Dùng registry ID, không arbitrary `iss` string |
| Token type | Có nếu policy cho | `access`/`refresh`/`id`; không raw JWT |
| Scope/roles | Hạn chế | Có thể nhạy cảm và high-cardinality; cân nhắc category |
| Subject/user ID | Cần privacy review | Pseudonymous internal ref nếu cần |
| `jti` | Hạn chế | Stable credential identifier; không cần cho mọi request |
| `kid` từ unverified token | Không trực tiếp | Chỉ log normalized trusted key ref khi cần |
| Bearer/refresh/ID token, cookie, code | **Không** | Credentials |
| Full headers, full URL, request/response body | Mặc định **không** | Có thể chứa credential/PII |
| Raw stack trace/exception message | Theo chính sách | Scrub source; đừng để request/token embed vào message |

### 7.3. Safe correlation không cần biết token

```text
Request starts:
  generate request_id
  attach request_id to trusted request context

Log events:
  request_id + route + status + safe error category

Cross-service trace:
  use trace_id/span_id from tracing protocol
  never use bearer value as trace_id/baggage
```

Nếu cần liên hệ **một token** với issuance/revocation trong hệ thống an ninh được cấp quyền, cân nhắc **token reference** từ AS được thiết kế riêng hoặc **keyed HMAC fingerprint** chỉ trong restricted security telemetry, với key riêng, ngắn hạn, rotation, TTL, access review và tránh cross-system linkage. **Không mặc định hash SHA-256 toàn bộ token rồi log cho mọi request**: dù một digest không dễ đảo ngược với token entropy cao, nó vẫn là stable identifier có vấn đề privacy/correlation, và chuỗi có entropy thấp có thể bị đoán.

### 7.4. Tránh “masking là biện pháp duy nhất”

Redaction/masking có thể hữu ích như **defense-in-depth** khi hệ thống vẫn cần log cấu trúc request do yêu cầu hợp đồng. Tuy nhiên:

1. Masking rule thường bỏ sót biến thể capitalization, nested JSON, URL-encoding, custom header và framework internals.
2. Nếu masking ở collector, **app/stdout/transport đã thấy raw token**.
3. Sai regex có thể che sai hoặc làm lộ một phần lớn.
4. Với JWE/JWS, chỉ che signature hoặc một phần cuối vẫn có rủi ro.
5. Exception/crash dumps và manual exports có thể bypass logging pipeline.

**Ưu tiên ngăn thu thập secret tại nguồn**, sau đó thêm redaction tại collector/sink như lớp bảo vệ bổ sung.

## 8. Quản trị log store và data lifecycle

Không có cấu hình Java nào giải quyết được việc một SIEM account có quyền export hàng triệu logs không kiểm soát. Cần:

- **Least privilege:** phân vai đọc event kỹ thuật, security audit, export/admin.
- **MFA/SSO**, short-lived admin sessions và access reviews cho dashboard/log API.
- **Encryption in transit/at rest** cho log pipelines, collector queues và backups.
- **Retention có hạn** theo audit/legal/security policy; không mặc định lưu logs mãi.
- **Access/export audit**, alert bulk download hoặc unusual access.
- **DLP/secrets detection** ở nhiều giai đoạn, nhưng tránh gửi raw leaked token tới một nơi kém tin hơn.
- **Isolation** giữa dev/test/prod, giữa tenants và giữa business vs security telemetry.
- **Deletion/remediation plan** cho indexes, object stores, queues, cached views, exported files và replicas trong giới hạn hệ thống.
- **Incident evidence preservation** có kiểm soát, không xóa dấu vết trái chính sách pháp lý/audit.

### 8.1. Shared responsibility

Với APM/SIEM hosted service, cần hiểu ai có quyền xem dữ liệu, dữ liệu lưu ở vùng nào, hợp đồng retention, subprocessors, backup deletion và cách incident export được quản lý. Không suy rằng “đã dùng một vendor lớn” thì raw bearer tokens được phép đi qua.

### 8.2. Khi vẫn phải log request body vì business audit?

Chỉ log **safe projection** được thiết kế, ví dụ `order_id` đã được validate và business event `order_created` với access controls. Không log raw HTTP body hoặc toàn bộ DTO vì body có thể chứa `access_token`, `refresh_token`, `client_secret`, password, PII hoặc dữ liệu người dùng.

### 8.3. Logs cũng có thể bị injection

Untrusted headers/URLs/error strings có thể chứa xuống dòng, control characters hoặc strings giả định dạng JSON/log để gây **log injection**. Đừng đưa arbitrary request data vào event/metric labels. Khi phải ghi user input vì audit, sanitize/escape và giới hạn length theo policy, nhưng **không ghi credential**.

## 9. Java/Spring: request logging không chứa Authorization

Một ví dụ servlet filter dùng **chỉ method/status và request ID mới tạo**, không đọc header, query, body, path, cookie hoặc token:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public final class SafeHttpMetadataLoggingFilter
    extends OncePerRequestFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(SafeHttpMetadataLoggingFilter.class);

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain
    ) throws ServletException, IOException {
        String requestId = UUID.randomUUID().toString();
        long started = System.nanoTime();

        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                (System.nanoTime() - started) / 1_000_000L;
            LOG.info(
                "http_request request_id={} method={} status={} duration_ms={}",
                requestId,
                request.getMethod(),
                response.getStatus(),
                elapsedMs
            );
        }
    }
}
```

**Giới hạn minh họa:** request ID không được xuất/propagate tới caller trong ví dụ; với tracing thực, dùng một nguồn request ID/trace ID **được chuẩn hóa và validate**. Filter có thể chạy khác trong async/error dispatch; status/duration có thể chưa cuối với asynchronous responses. Logging filter này **không tự ngăn các filter/framework khác ghi token**. Nếu route template cần log, lấy từ trusted routing metadata khi đã resolve, đừng đọc raw `request.getRequestURI()`/`getQueryString()`.

### 9.1. Vì sao không log `request.toString()`?

Một số `toString()` chỉ trả tên class; một số wrappers/interceptors có thể serialize headers/body. **Không dựa vào implementational accident** “hiện tại chưa in token”. Logging allowlist giúp bảo đảm ngay cả khi thư viện đổi behavior, event vẫn không có credential.

### 9.2. SecurityContext không phải thứ nên serialize

Spring Security `Authentication`/`JwtAuthenticationToken` có thể chứa token/claims ở một số hình thức. Tránh:

```java
// SAI: có thể tiết lộ sensitive authentication details.
log.debug("security context = {}",
    org.springframework.security.core.context.SecurityContextHolder
        .getContext().getAuthentication());
```

Nếu cần audit, tạo **event riêng với allowlisted issuer reference, auth result và safe principal reference**, có privacy review; không `toString()` principal hoặc serialize claims.

### 9.3. Không gọi `getInputStream()` chỉ để log

Một filter đọc request body để log có thể:

- Làm rò `refresh_token`/`client_secret`/password.
- Tiêu thụ request stream gây lỗi controller.
- Chứa binary/PII hoặc tokens trong JSON.
- Tạo memory amplification với request lớn.

Đừng cài body-capture logging ở authentication/token endpoints. Nếu một chức năng audit thật sự cần nội dung nghiệp vụ, làm **safe projection sau validation**.

## 10. HTTP client logging: inbound đã sạch nhưng outbound vẫn có thể lộ

Một lỗi phổ biến là chỉ sửa servlet filter inbound. Khi API gọi downstream resource server với access token, interceptor/logging library lại in **outbound Authorization header** hoặc response từ AS.

### 10.1. Spring WebClient: chỉ ghi method và status

Ví dụ Reactor `WebClient` với `ExchangeFilterFunction`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

public final class SafeWebClientTelemetry {
    private static final Logger LOG =
        LoggerFactory.getLogger(SafeWebClientTelemetry.class);

    public static ExchangeFilterFunction metadataOnly() {
        return (request, next) -> {
            long started = System.nanoTime();
            return next.exchange(request)
                .doOnNext(response -> LOG.info(
                    "outbound_http method={} status={} duration_ms={}",
                    request.method().name(),
                    response.statusCode().value(),
                    (System.nanoTime() - started) / 1_000_000L
                ))
                .doOnError(error -> LOG.warn(
                    "outbound_http_failed method={} error_class=transport",
                    request.method().name()
                ));
        };
    }

    public static WebClient newClient() {
        return WebClient.builder()
            .filter(metadataOnly())
            .build();
    }
}
```

**Cần lưu ý:**

- Filter **không log** `request.url()`, headers, cookies, body hoặc exception message.
- Không vô tình ghi body response `/oauth2/token` hoặc introspection khi thêm filter khác.
- Đo latency trong reactive pipeline có semantics riêng (subscription/retry/cancellation); ví dụ chỉ minh họa **logging surface an toàn**, không phải bộ đo latency đầy đủ cho mọi reactive behavior.
- `doOnError` không in raw throwable; vẫn cần error classification hữu ích ở một lớp khác, được kiểm soát.
- Những HTTP clients khác (Feign, OkHttp, RestClient, RestTemplate, Apache HttpClient) có cơ chế wiretap/DEBUG riêng; kiểm logging configuration của **từng client**.

### 10.2. Tránh log response body của token endpoint

Sai:

```java
// ANTI-PATTERN: access/refresh/ID token có thể nằm trong response.
log.debug("oauth token endpoint returned {}", tokenResponseBody);
```

Thay bằng:

```java
log.info(
    "oauth_token_exchange grant_type={} status={} error_class={}",
    "authorization_code",
    200,
    "none"
);
```

Đây là event minh họa với hằng số kiểm thử. Trong thực tế, grant type và status cần được lấy từ **trusted control flow**, không phải dump request body; không log authorization code, PKCE verifier, `client_secret`, assertion JWT hoặc token response.

### 10.3. Các kiểu debug đặc biệt nguy hiểm

- `curl -v`, HTTP wire logs, `trace logging` hoặc packet captures ở nơi TLS kết thúc.
- Feign `Logger.Level.FULL` cho OAuth clients nếu nó ghi request/response headers/bodies.
- Reactor Netty `wiretap` hoặc các logging hooks chứa byte frames.
- Apache HttpClient wire/header logging ở DEBUG.
- Logging interceptor tự tạo cho `RestTemplate` đọc body/headers.
- Client retry libraries log context chứa `HttpRequest`/`HttpResponse`.

**Không khẳng định** mọi framework tự log bearer token theo mặc định; nguy cơ xuất hiện khi cấu hình, plugin, middleware hoặc code ứng dụng thu thập dữ liệu quá rộng. Security review phải kiểm **chính version và cấu hình đang deploy**.

## 11. Spring Security và OAuth-specific logging

### 11.1. Resource Server: authentication failure không in token

Một `JwtDecoder` hoặc introspection component có thể báo token invalid. Không viết:

```java
// SAI: đưa credential ra log khi xác minh không thành công.
try {
    jwtDecoder.decode(bearerValue);
} catch (Exception ex) {
    log.warn("rejected token={} cause={}", bearerValue, ex);
    throw ex;
}
```

Vì attacker có thể gửi hàng nghìn token tùy ý, code này biến log thành **hộp thư chứa attacker-controlled bytes**, đồng thời ghi cả token thật khi client vô tình gửi sai.

Đúng về nguyên tắc:

```text
incoming credential
  -> decoder/introspector validates
  -> on invalid:
       auth_result=denied
       reason_code=signature_invalid | issuer_mismatch | expired
       request_id=safe-id
       no bearer value, claims or raw exception string
  -> no authenticated SecurityContext
```

Nếu cần nguyên nhân từ exception, **map exception class/validation code sang enum an toàn**, không đưa `ex.getMessage()` vào trường `reason` khi message có thể chứa token, URL, `kid` chưa tin hoặc claims.

### 11.2. AuthenticationEntryPoint trả lỗi chung

Ví dụ cho **trường hợp invalid bearer credential** trong Servlet Spring Security:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

@Component
public class SafeBearerAuthenticationEntryPoint
    implements AuthenticationEntryPoint {

    @Override
    public void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException failure
    ) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer error=\"invalid_token\""
        );
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write("{\"error\":\"invalid_token\"}");
    }
}
```

**Giới hạn:** với request thiếu credential hoàn toàn hoặc authentication schemes khác, header `WWW-Authenticate` cần phản ánh RFC 6750/framework contract đúng; ví dụ tập trung nhánh **invalid credential**. Không gửi raw failure message/token trong body. Với KMS/introspection outage, authentication layer vẫn phải **fail closed**, có thể map lỗi dependency sang 503 theo design thay vì mặc định mọi lỗi đều invalid token. Kiểm bằng integration tests qua filter chain; `@ControllerAdvice` không nhất thiết bắt được security filter exceptions.

### 11.3. OAuth 2.0 Client/Authorization Server

Với OAuth client/AS, những giá trị sau **tuyệt đối không log raw**:

```text
authorization_code
code_verifier
client_secret
client_assertion
refresh_token
access_token
id_token
Authorization: Basic ...
Authorization: Bearer ...
Cookie: ...
Set-Cookie: ...
```

AS có thể ghi **safe issuance event**:

```json
{
  "event": "oauth_token_issued",
  "issuer_ref": "corp-issuer",
  "client_ref": "storefront-web",
  "grant_type": "authorization_code",
  "resource_ref": "orders-api",
  "scope_category": "read",
  "result": "approved",
  "request_id": "req-safe-test-98"
}
```

Không đưa raw `scope` string vào mọi event nếu tổ chức coi scope/tenant metadata nhạy cảm; phân loại theo **approved schema**. `client_ref` là trusted registry identifier, không phải giá trị arbitrary từ unvalidated client input.

### 11.4. Spring Security DEBUG/TRACE

Một số phiên bản/security middleware có log về filter chain, principal hoặc request/response. Không khẳng định “bật `org.springframework.security=DEBUG` luôn in token” cũng không khẳng định “Spring tự che mọi secret”. **Đánh giá output thực tế** với synthetic token canary, dependency/version-specific instrumentation và HTTP proxy logs. Tránh để DEBUG/TRACE có khả năng ghi credentials ở production.

### 11.5. MDC: chỉ chứa context an toàn

```java
import org.slf4j.MDC;

String safeRequestId = java.util.UUID.randomUUID().toString();
try (MDC.MDCCloseable ignored =
         MDC.putCloseable("request_id", safeRequestId)) {
    // Business code may log request_id, never bearer token.
    service.handleBusinessRequest();
}
```

Đây là fragment minh họa. Với async/reactive execution, MDC không tự được lan truyền/clear đúng theo mọi threading model; dùng context propagation framework phù hợp và test. **Không đưa JWT claims, access token, refresh token hay session cookie vào MDC** vì chúng sẽ lộ trong nhiều log statements ngoài dự kiến.

## 12. Logback/Log4j và HTTP access logs: cấu hình ở nhiều tầng

### 12.1. Logback logging levels chỉ là một hàng rào

Ví dụ cấu hình **hạn chế wire/header debug loggers đã biết**:

```xml
<configuration>
  <!-- Chỉ minh họa; xác minh logger names theo dependency versions. -->
  <logger name="org.apache.http.wire" level="WARN" />
  <logger name="org.springframework.web.reactive.function.client.ExchangeFunctions"
          level="WARN" />
  <logger name="reactor.netty.http.client.HttpClient" level="WARN" />

  <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger{24} - %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO">
    <appender-ref ref="STDOUT" />
  </root>
</configuration>
```

**Đây không phải giải pháp đủ:** `%msg` có thể chứa token nếu code đã `log.info("token={}", value)`. Logger names thay đổi theo client/version; ngay cả ở WARN/ERROR, exception messages vẫn có nguy cơ. Chính sách chính vẫn là **log allowlist tại source**, và review tất cả instrumentation.

### 12.2. NGINX access log: tránh `$request` và query string

Ví dụ cấu hình logging **metadata-only**:

```nginx
log_format safe_api
  'method=$request_method status=$status '
  'request_id=$request_id bytes_sent=$body_bytes_sent';

access_log /var/log/nginx/api_access.log safe_api;
```

**Cần rà soát các cấu hình khác:** `$request` thường chứa full request line (có URI/query), `$request_uri` chứa raw URI, `$args` chứa query; `$http_authorization`/`$http_cookie` ghi credentials. `$uri` có thể chứa sensitive path segments; nếu log route, chỉ dùng **route template đã tin** hoặc an toàn theo privacy policy. Ví dụ trên giả định biến `$request_id` khả dụng trong NGINX version/build và không dùng dữ liệu token để làm request ID.

### 12.3. Servlet container access logs

Các container/servers có cú pháp log riêng. Với Tomcat access log, patterns như **request line**, **query string** hoặc **request headers** có thể chứa secrets tùy cấu hình. Đừng dùng pattern có raw Authorization/Cookie/query. Kiểm:

- Container access log policy.
- Reverse proxy/gateway/WAF fields.
- Service-mesh telemetry.
- Audit log từ identity provider.
- Cloud load balancer logs và request/response capture.

Một Spring filter safe không ngăn gateway hoặc container khác in raw request.

### 12.4. Các biểu hiện “log tưởng metadata nhưng vẫn lộ”

- `http.url` có query `code=...` hoặc `access_token=...`.
- `http.request.header.authorization`.
- `http.response.header.set_cookie`.
- `request.body` token response JSON.
- `exception.stacktrace` có `message="...token=..."`.
- `user.id` chứa raw `sub`/PII theo policy.
- `request_id` bị thay bằng token value do developer tận dụng làm correlation ID.

## 13. OpenTelemetry, distributed tracing và APM

### 13.1. Trace context không phải nơi chứa secrets

`traceparent`, trace/span IDs dùng để correlate requests; **không chứa bearer token**. OpenTelemetry baggage là cơ chế truyền key/value qua service boundaries, do đó rất nguy hiểm nếu ứng dụng đặt `Authorization`/`access_token`/`refresh_token` vào baggage:

```text
Service A
  -> baggage: auth_token=<sensitive value>
  -> Service B
  -> Service C
  -> telemetry exporter
```

Credential có thể được lan rộng hơn đường API ban đầu. **Không propagate secrets bằng trace context/baggage.**

### 13.2. Cấu hình instrumentation theo allowlist

Chỉ thu:

```text
service.name
http.request.method
http.response.status_code
http.route (trusted template)
server.address (if policy permits)
duration
error.type (safe normalized category)
trace_id/span_id
```

Không thu:

```text
http.request.header.authorization
http.request.header.cookie
http.response.header.set-cookie
url.full containing query credentials
request/response bodies from token endpoints
raw JWT claims, tokens, client assertions, secrets
```

Tên semantic-convention attributes **có thể khác theo phiên bản instrumentation**; cần kiểm chính configuration đang chạy và pipelines. Việc không thu header ở một SDK không chứng minh sidecar/proxy hay một exception event khác đã an toàn.

### 13.3. Sampling không phải bảo vệ credential

Nếu chỉ sample 1% requests, vẫn có thể capture token thật. Một token response hiếm gặp nhưng nhạy cảm có thể xuất hiện trong sampled trace, và sampling tăng khi lỗi càng nguy hiểm vì exception code thường chứa bodies. **Không dùng sampling để thay redaction.**

### 13.4. Processor redaction cần ở đúng tầng

Mô hình:

```text
Instrumentation SDK: collect safe fields only
        |
        v
Local agent/collector: drop unsafe attributes (second guard)
        |
        v
Central collector: schema checks + restricted retention
        |
        v
APM/SIEM: least privilege + export audit
```

Nếu scrub chỉ xảy ra ở central collector, token đã đi qua client SDK, local process/agent và network/spool. **Ưu tiên phòng ngừa trước khi thu**, dùng collector redaction là lớp phòng vệ thứ hai.

## 14. Frontend/mobile logging cũng có thể làm lộ token

Trong browser, một ứng dụng có thể vô tình:

```javascript
// ANTI-PATTERN: không dùng khi có token thật.
console.log("auth response", oauthResponse);
console.log("fetch options", requestOptions);
errorTracker.captureException(new Error(
  "request failed: " + JSON.stringify(requestOptions)
));
```

Rủi ro:

- Browser developer console, remote logging SDK và customer support screenshots.
- Frontend error reporting với request headers/body.
- Session replay/analytics tools capture form contents/URLs.
- Mobile crash logs, diagnostic reports và network inspectors.
- LocalStorage/sessionStorage dumps khi debug authentication state.

### 14.1. Không đưa bearer token vào URL

Query-string access token có thể lọt vào browser history, proxy logs, referrer và analytics. OAuth bearer token usage có đề cập query method nhưng **khuyến cáo tránh** do rủi ro bảo mật (RFC 6750). Với API, ưu tiên:

```http
Authorization: Bearer TOKEN_VALUE_NOT_LOGGED
```

Header cũng phải được **redact ở mọi logging boundary**. “Đưa token từ query sang header” giảm một lớp rủi ro, không loại bỏ lỗi full-header logging.

### 14.2. Browser URL fragment khác query

Fragment (`#...`) thông thường **không được browser gửi lên server trong HTTP request**, nên một server access log mặc định không thấy fragment. Nhưng fragment có thể bị JavaScript/frontend telemetry/browser history thu, và các redirect/response modes khác cũng có nguy cơ. Không suy “fragment không vào HTTP request nên token an toàn để log ở frontend”.

### 14.3. Secure cookies vẫn không nên được ghi log

`HttpOnly` giảm JavaScript đọc cookie, `Secure` buộc HTTPS, `SameSite` hỗ trợ CSRF risk reduction theo bối cảnh. Nhưng **backend/proxy vẫn nhận Cookie header sau TLS termination**; full request logging có thể in session cookie. Cookies là credentials tương đương session state và phải bị loại khỏi log.

## 15. CI/CD, test runners và vận hành thủ công

Token leakage không chỉ đến từ production application:

### 15.1. Shell history và debug mode

```bash
# MINH HỌA RỦI RO - KHÔNG SỬ DỤNG TOKEN THẬT.
curl -v -H "Authorization: Bearer TEST_ONLY" https://api.example.test
```

Verbose output, terminal scrollback, command history hoặc CI step log có thể ghi token. Với testing, dùng **short-lived test-only credentials**, secret injection từ CI secret store và công cụ redaction được kiểm thử; không paste production tokens vào terminal/collaboration tools.

### 15.2. Build scripts và environment variables

Shell `set -x`/debug tracing hoặc framework “print all env vars/config” có thể in `CLIENT_SECRET`, refresh tokens, service account credentials. **Không log toàn bộ environment**, không dùng token thật làm command-line argument nếu shell/process list/history có thể ghi lại; quản lý CI runner logs và retention.

### 15.3. Test failures có thể chứa token

Ví dụ assertion:

```java
// SAI: failure output in token fixture / response.
assertEquals(expectedResponse, actualTokenResponse.toString());
```

Khi test fail, JUnit/CI có thể in **expected vs actual** chứa secret. Thay bằng assertions trên **safe properties**:

```java
// Chỉ ví dụ test metadata, không dump token response.
assertTrue(tokenResponse.hasAccessToken());
assertEquals("Bearer", tokenResponse.getTokenType());
assertTrue(tokenResponse.getExpiresIn() > 0);
```

Với test đối với token được phát thật, tránh dùng `toString()` trong failure messages và kiểm tool reports/test artifacts.

### 15.4. Support/debug tickets

Không yêu cầu user/customer gửi raw access/refresh/ID token “để đội kỹ thuật xem”. Thay bằng:

- Request ID/trace ID.
- Thời điểm và timezone.
- Endpoint **route template**.
- Response status/error code đã sanitize.
- Client/ref ID không nhạy cảm theo chính sách.
- Test reproduction với synthetic token.

Nếu cần credential để tái hiện lỗi, dùng sandbox/test credential có TTL ngắn, giới hạn quyền và kênh xử lý được phê duyệt — không dán production bearer token vào chat/ticket.

## 16. Sanitization: phòng ngừa nhiều lớp, không tin regex duy nhất

### 16.1. Thứ tự ưu tiên

1. **Không tạo log event có credential.**
2. **Không cấu hình middleware capture raw headers/bodies.**
3. **Cho phép chỉ những trường quan sát đã duyệt**, không serialize object tổng.
4. **Redact tại nguồn** với các tình huống buộc phải ghi cấu trúc.
5. **Redact ở collector** như safety net, trước durable store nếu có thể.
6. **DLP scans, tests, reviews và incident runbooks** để phát hiện phần bị bỏ sót.

### 16.2. Header redaction

Một allowlist/denylist kết hợp có thể quy định:

```text
DROP ENTIRE HEADER VALUES:
  Authorization
  Proxy-Authorization
  Cookie
  Set-Cookie
  X-Api-Key
  DPoP
  client assertion/proof headers as applicable

ALLOW ONLY EXPLICIT METADATA:
  Content-Type (after validation)
  Accept (if operationally useful)
  request-id generated by trusted middleware
  user-agent category (if privacy approved; not raw device fingerprint)
```

Tên headers **không phân biệt hoa thường**. Đừng chỉ block một tên mà bỏ biến thể custom `X-Auth-Token`/`X-Forwarded-Authorization`. Với custom protocol, xem toàn bộ nơi credential có thể xuất hiện, không chỉ header `Authorization`.

### 16.3. Body redaction

Với endpoint nhạy cảm (ví dụ `/oauth2/token`, `/introspect`, `/revoke`, `/login`, `/password/reset`), **tắt request/response body capture** là chính sách đơn giản nhất. Nếu phải ghi business DTO sau validation, map thành **safe audit DTO** chỉ gồm allowed fields.

### 16.4. Regex detect “JWT-like string” không chứng minh sạch hoàn toàn

Một JWT thường có ba thành phần Base64url cách nhau dấu chấm; JWE compact thường có năm. Tuy nhiên:

- Opaque token không có pattern cố định.
- JWT có serialization khác compact.
- Token bị URL-encoded, JSON-escaped, split giữa lines hoặc truncated.
- `Bearer` có thể được in trong ngoại lệ với format lạ.
- Prefix/suffix có thể vô tình giống token.
- Encryption ciphertext vẫn là credential dù không “trông như JWT”.

Pattern scanning là **lớp phát hiện**, không thay “do not log credentials”. Dùng **synthetic canaries** để test đường dữ liệu và review source code/interceptors.

### 16.5. Redaction output không nên chứa token một phần

Ví dụ mong đợi:

```text
authorization_present=true
authorization_scheme=Bearer
token_value=<REDACTED>
```

Tốt hơn nữa, phần lớn HTTP event chỉ cần `auth_result=valid|invalid` do security layer quyết định, không cần log `authorization_present`. Nếu cần biết scheme, dùng enum đã chuẩn hóa; **không xuất raw header** dù giá trị đầu chỉ là `Bearer`.

## 17. Redaction kiểm thử được bằng synthetic sentinel

Một test an toàn **không dùng production token thật**. Tạo một chuỗi sentinel có định dạng đặc biệt chỉ phục vụ test, đưa qua các đường HTTP/OAuth logging và kiểm tất cả sinks:

```text
TEST_ONLY_LOG_SECRET_SENTINEL_9C41_NOT_A_REAL_TOKEN
```

**Không phải credential hợp lệ.** Dùng marker như vậy giúp phát hiện log/raw-header capture; nhưng **không chứng minh** mọi loại secret format đều được bảo vệ, nên bổ sung canaries cho JWS-like, JWE-like, opaque và form-field layouts trong test sandbox.

### 17.1. Quy trình integration test

```mermaid
flowchart TD
    A[Create synthetic sentinel value] --> B[Send via Authorization header/cookie/body/query in TEST env]
    B --> C[Exercise gateway, app, HTTP client, error and retry paths]
    C --> D[Collect test stdout + collector + APM export + CI artifacts]
    D --> E{Any sentinel present?}
    E -->|Yes| F[FAIL: identify leaking stage, fix and rerun]
    E -->|No| G[PASS for tested paths; review coverage]
```

Test cả **successful 200**, **unauthorized 401**, **server 5xx**, **timeout**, **retry**, **rate limit** và **exception path**. Nhiều leaks chỉ xuất hiện khi request fail và debug logger in toàn bộ context.

### 17.2. Kiểm cả redaction trước và sau ingestion

Nếu application stdout **có token** nhưng central SIEM không có, **test vẫn FAIL**: raw token đã đi qua stdout/log driver/collector local. Xác định cụ thể mục tiêu:

```text
No credential in:
  app stdout/stderr
  container/runtime logs
  local agent buffers/spool
  tracing SDK export
  central log indexes
  dashboards/exports
  CI artifacts
  error tracking/crash reports
```

Với một số sinks khó đọc trong automation, cần audit/config verification và risk-based manual tests, không tuyên bố “all logs verified” khi chỉ quét một file.

## 18. Ma trận kiểm thử: 80 đường rò rỉ token qua log

**Yêu cầu kiểm thử:** Với từng input chứa synthetic sentinel, xác minh **không có raw credential ở log/trace/metric/CI/sink liên quan**, và mọi authentication/authorization decision vẫn đúng. Một case PASS chỉ có giá trị cho **component và logging configuration** đã được test.

| # | Kịch bản kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| 1 | Inbound `Authorization: Bearer TEST_SENTINEL`, API trả 200 với test credential hợp lệ | No token in app logs/collector |
| 2 | Inbound bearer sai, API trả 401 | No raw invalid token trong auth failure |
| 3 | Token hết hạn `exp`, RS từ chối | Không log compact JWT/claims |
| 4 | JWT signature sai | Không log token hoặc serialized header/payload |
| 5 | Wrong `iss` | Log reason code, không raw JWT |
| 6 | Wrong `aud` | Log safe audience mismatch category, không raw claims |
| 7 | Missing scope, trả 403 | Không in token để debug permission |
| 8 | Cross-tenant resource deny | Không log toàn bộ principal/claims |
| 9 | Bearer token sau revoke | Không log token trong revocation decision |
| 10 | Request không có Authorization | Event vẫn có status, không cần headers |
| 11 | `Authorization` header viết hoa/thường khác | Redaction case-insensitive |
| 12 | `Proxy-Authorization` có sentinel | Không log proxy credential |
| 13 | Custom `X-Api-Key` | Không log raw API key |
| 14 | Custom `X-Auth-Token` | Không log raw token |
| 15 | Header `DPoP` có proof JWT | Không log proof |
| 16 | `Cookie` chứa session value | Không log cookie |
| 17 | `Set-Cookie` response | Không log cookie value |
| 18 | Multiple Authorization headers (malformed request) | Reject appropriately; no values in logs |
| 19 | Header có newline/control characters | Không log injection, không raw credential |
| 20 | Oversized Authorization header | Limit/reject; no full header dump |
| 21 | GET query `?access_token=sentinel` | Không ghi full URI/query |
| 22 | OAuth callback query `?code=sentinel` | Không log raw code/URL |
| 23 | OAuth callback `state=sentinel` | Không log state transaction secret |
| 24 | OAuth callback rejected due invalid `state` | No callback URL in exception |
| 25 | OAuth PKCE `code_verifier` body field | Không log form body |
| 26 | Authorization request `code_challenge` | No full URL/request dump |
| 27 | OAuth token request `client_secret` | No secret from form body |
| 28 | OAuth token request Basic auth header | Không log Basic credentials |
| 29 | OAuth token request `refresh_token` | Không log refresh |
| 30 | OAuth refresh token invalid/reused | Không log raw value trong audit/errors |
| 31 | OAuth token response `access_token` | No response body capture |
| 32 | OAuth token response `refresh_token` | No response body capture |
| 33 | OAuth token response `id_token` | No response body capture |
| 34 | OAuth client assertion `client_assertion` | No assertion JWT logged |
| 35 | OIDC login callback lỗi nonce | Không log raw ID token |
| 36 | OIDC userinfo response contains PII | No raw response body/claims |
| 37 | Encrypted JWE bearer token | No ciphertext token logged |
| 38 | JWE decrypt fails, invalid AEAD tag | No JWE/CEK/plaintext in errors |
| 39 | Opaque bearer token | No opaque string in logs |
| 40 | RS introspection request token form field | No token or client credentials |
| 41 | RS introspection response metadata | Allowlist safe, no full body/PII |
| 42 | Controller throws with token-bearing exception message | Generic safe error, no raw message |
| 43 | Security filter throws before controller | Entry point logs safe category only |
| 44 | Request DTO `toString()` contains refresh token | DTO not blindly serialized in logs |
| 45 | Response DTO `toString()` contains access token | DTO not blindly serialized |
| 46 | Spring Security `Authentication`/principal logging | No token/claims object dump |
| 47 | Servlet request filter logs method/status | No header/query/body |
| 48 | Async dispatch/error dispatch | No credential from secondary paths |
| 49 | WebClient successful downstream request | No outbound Authorization header |
| 50 | WebClient 4xx error | No request header/response body |
| 51 | WebClient 5xx retry | No token in retry diagnostics |
| 52 | Feign debug logging on controlled test | Policy prevents full headers/bodies |
| 53 | Apache HttpClient wire logger | Disabled/redacted before logs |
| 54 | Reactor Netty wiretap | Not exposed to production sinks |
| 55 | RestTemplate interceptor | Safe metadata projection only |
| 56 | NGINX access log query string | Raw `?access_token` absent |
| 57 | Gateway/WAF structured request logging | Authorization/Cookie excluded |
| 58 | Load balancer/ingress error log | No raw request line with secret query |
| 59 | Service mesh request metadata | No sensitive headers/URL |
| 60 | OpenTelemetry HTTP span attributes | No authorization/cookie attributes |
| 61 | OpenTelemetry baggage carrier | No bearer/refresh secrets propagated |
| 62 | OpenTelemetry exception event | No raw token-bearing exception message |
| 63 | APM error capture on 5xx | No auth request body/headers |
| 64 | Trace sampling increased on failure | Redaction invariant still holds |
| 65 | MDC includes request_id | No token/claims/session ID |
| 66 | Async task inherits/traces context | No secret propagation |
| 67 | Kafka/dead-letter logging of event | No credentials or raw payload dump |
| 68 | Job queue retry payload errors | No serialized token-bearing object |
| 69 | Browser console/error tracker | No token response or requestOptions |
| 70 | Mobile crash report/network debug | No raw auth headers/tokens |
| 71 | CI/test assertion failure | No raw token in expected/actual diff |
| 72 | CI `set -x`/verbose command output | No production secret or raw token |
| 73 | Container stdout/stderr | No synthetic sentinel |
| 74 | Local log agent buffer/spool | No synthetic sentinel |
| 75 | Central log index/APM export | No synthetic sentinel |
| 76 | Dashboard CSV/JSON export | No synthetic sentinel |
| 77 | Incident ticket attachment | No raw token from trace export |
| 78 | Collector redaction fails/disabled in test | Source logging still avoids token |
| 79 | Log retention/deletion exercise | Known replicas/exports included in scope |
| 80 | Log reader attempts replay with **test-only** credential | Incident detection/revocation controls work in sandbox |

### 18.1. Phân tầng kiểm thử

- **Unit:** safe logging event builder, DTO safe projection, error classification, field allowlist.
- **Component:** Servlet filters, WebClient/Feign interceptors, logback appenders, MDC, Spring Security auth failures.
- **Integration:** API gateway → Spring service → collector → APM test tenant; authorization code/refresh token flows.
- **End-to-end:** một synthetic sensitive token đi qua 200/401/403/503/timeout/retry rồi kiểm **tất cả quan sát được**.
- **Resilience:** thay DEBUG/TRACE config, network failure, token endpoint 5xx, collector buffer/retry.
- **Security:** token theft simulation trong sandbox, log access audits, DLP, retention/export paths.

### 18.2. Hai assertion bắt buộc

```text
Security invariant A:
  No raw bearer/refresh/ID token, cookie, code, verifier or client secret
  enters any tested logging/telemetry sink.

Security invariant B:
  Auth decisions remain correct:
    valid token + authorized resource -> allow
    invalid/revoked/expired token -> deny
    valid token + missing permission -> deny
    dependency unavailable -> fail closed
```

Một app “không log token” nhưng **bỏ signature validation** để tránh exception vẫn không an toàn. Và một API kiểm token đúng nhưng **in token trong error log** cũng không an toàn.

### 18.3. Negative test cần cả “token giả” và “token hợp lệ”

Nếu chỉ gửi sentinel không phải credential, code logging có thể chỉ log token hợp lệ sau khi decode claims. Vì vậy trong sandbox cần **test token hợp lệ thật do test AS cấp** (không có quyền production), đồng thời có canary riêng trong body/header/URL. Với log outputs, không dùng raw token trong test failure messages; kiểm dấu hoặc fingerprint trong test harness có quyền, không in credential ra output.

## 19. JUnit + MockMvc: kiểm log không chứa synthetic token

Ví dụ sau dùng một `ListAppender` của Logback để test log events trong JVM. **Giả định** test có `MockMvc` cấu hình Spring Security filter chain và endpoint `/v1/orders` được bảo vệ. Đây là **một phần test**, không thay kiểm gateway/collector/APM/CI.

```java
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class BearerTokenNotLoggedTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void invalidSyntheticBearerValueMustNotAppearInAppLog()
        throws Exception {

        final String sentinel =
            "TEST_ONLY_LOG_SECRET_SENTINEL_9C41_NOT_REAL";
        Logger root = (Logger) LoggerFactory.getLogger(
            Logger.ROOT_LOGGER_NAME);

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        root.addAppender(appender);
        try {
            mockMvc.perform(
                get("/v1/orders")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + sentinel)
            ).andExpect(status().isUnauthorized());

            String messages = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));
            assertFalse(
                messages.contains(sentinel),
                "Synthetic secret must not appear in formatted application logs"
            );
        } finally {
            root.detachAppender(appender);
            appender.stop();
        }
    }
}
```

**Giới hạn và cải tiến:**

- Test này chỉ kiểm `getFormattedMessage()` trên appender gắn vào root logger trong JVM. Nó **chưa** kiểm stack trace từ throwable proxy, custom appenders không propagate root, HTTP gateway, collector, APM hoặc stdout ngoài test harness.
- Không mọi `MockMvc` test tự bật security filters; phải dùng đúng Spring test setup và xác minh 401 đến từ security chain.
- Test concurrent loggers có thể tạo nhiễu; sử dụng isolated test appender/context hoặc per-test lifecycle.
- Thêm cases **valid sandbox JWT, refresh token form, `Cookie`, token response**, error/async paths.
- Đừng include sentinel/raw token trong assertion failure bằng cách in tất cả log contents.
- Kết quả PASS **không chứng minh** mọi secrets khác đều không lộ; test suite phải đo bao phủ từng pipeline.

### 19.1. Test token endpoint request/response

Pseudocode có fixtures:

```java
@Test
void tokenExchangeMustNotLogRefreshOrAccessToken() {
    var refresh = fixtures.syntheticRefreshTokenWithSentinel();
    var response = oauthClient.refreshInSandbox(refresh);

    assertTrue(response.hasAccessToken());

    var captured = telemetryHarness.captureAllTestSinks();
    assertFalse(captured.containsSyntheticRefreshToken());
    assertFalse(captured.containsSyntheticAccessToken());
    assertFalse(captured.containsRawTokenResponse());
}
```

Đây là **pseudocode**: `fixtures`/`telemetryHarness` là test support do dự án xây, không phải API chuẩn có sẵn. Test harness có thể so secrets trong memory, nhưng không **print actual tokens** khi fail.

### 19.2. Test DTO và exception paths

```java
@Test
void oauthErrorPathMustUseSafeReasonCode() {
    var token = fixtures.syntheticInvalidBearer();
    var result = apiHarness.sendWithBearer(token);

    assertEquals(401, result.statusCode());
    assertEquals("invalid_token", result.publicErrorCode());

    var events = telemetryHarness.captureAllTestSinks();
    assertTrue(events.hasSafeAuthDeniedEvent());
    assertFalse(events.containsBearerValue(token));
    assertFalse(events.containsAuthorizationHeader());
}
```

Test thêm `RequestRejectedException`/Spring Security `AuthenticationException`/HTTP-client exception khi message chứa một URL do test tạo với sentinel. Không in nguyên exception message ra log để debug.

### 19.3. Test tracing/MDC

```text
Given:
  test Authorization header contains TEST_SENTINEL

When:
  API calls downstream service
  OpenTelemetry propagates traceparent/baggage
  async task and 5xx handler execute

Then:
  trace_id/span_id exist
  all propagated baggage keys are approved
  no Authorization/Cookie/token values in spans/events/export
  MDC contains only approved context
  no raw token in collector buffer
```

### 19.4. Test redaction thay đổi config

Cho CI stage chạy một số “untrusted logging configurations” trong test environment:

```text
baseline INFO logging
DEBUG level enabled for app
HTTP client instrumentation accidentally enabled
collector redaction rule temporarily removed (test only)
async error handler triggered
gateway access-log format changed
```

Kỳ vọng **source allowlist** vẫn không log tokens trong đường mà code kiểm soát; nếu third-party wiretap bypass source thì **test phải FAIL**, và policy phải cấm/bảo vệ configuration đó trước production. Không bật thử nguy hiểm này trên production.

## 20. Phát hiện token đã xuất hiện trong log

Phòng ngừa là chính, nhưng vẫn cần **detective controls**:

1. Quét logs trong **test pipeline** bằng synthetic canary markers.
2. Secrets scanning trên source/config/CI artifacts và build reports.
3. DLP pattern matching cho `Authorization: Bearer`, `refresh_token`, `client_secret`, JWT-like/JWE-like strings, cookies, known token prefixes.
4. Nhận diện **high-entropy strings** trong trường không được phép, với false-positive review.
5. Schema validation: reject/drop events có field name không thuộc allowlist.
6. Alert khi DEBUG/wiretap config được bật trên production workloads.
7. Audit bulk log export và unusual read access.
8. Đối chiếu issuance/refresh/revoke events để tìm hoạt động bất thường sau exposure.

### 20.1. Không đưa leaked token sang một hệ thống kiểm tra kém an toàn

Một scanner gửi raw suspected secrets cho dịch vụ công cộng hoặc chat hỗ trợ có thể **tạo thêm leak**. DLP/scanning phải chạy trong **trusted security boundary** với quyền giới hạn và safe reporting:

```json
{
  "finding": "possible_bearer_credential_in_log",
  "dataset_ref": "prod-gateway-logs",
  "time_window_start": "2026-11-23T00:00:00Z",
  "field_class": "authorization_header",
  "count": 17,
  "sample_value": "REDACTED",
  "severity": "needs_triage"
}
```

Đây là event minh họa; không sử dụng các con số/ngày làm bằng chứng về một incident thật. Không log lại raw matches, không attach CSV chứa tokens vào alert.

### 20.2. Regex chỉ là tín hiệu xác suất

Không có regex nào phát hiện mọi token. JWT-like có thể là false positive; opaque secrets có thể không nhận dạng được. **Schema-first source controls** và synthetic tests giúp vượt qua giới hạn của regex. Không dùng quét/khôi phục token thật làm một bài thử không có quyền.

### 20.3. Fingerprint cho điều tra

Nếu cần đối chiếu leaked token với AS issuance records mà không lộ raw token trong nhiều công cụ:

- Ưu tiên AS-issued **safe grant/token reference** từ registry riêng nếu có.
- Nếu thật cần fingerprint, cân nhắc **HMAC-SHA-256(secret-audit-key, token-bytes)** ở **trusted scanner**; key audit tách signing secret, access restricted, retention ngắn.
- Không xuất token hoặc HMAC key sang dashboard/ticket.
- Không coi fingerprint là cơ chế xác thực; giá trị stable có thể gây correlation/privacy risk.
- Với tokens entropy thấp hoặc bị format yếu, digest không phép màu; key/algorithm/threat model vẫn quan trọng.

**Đừng dùng fingerprint làm metric label không giới hạn**; token cardinality rất cao, gây chi phí và DoS.

## 21. Incident response: phát hiện token thật trong log

Giả sử security scanner xác nhận central log có một raw **refresh token** production. Không cần chờ bằng chứng attacker đã dùng token mới bắt đầu giảm rủi ro: bản thân sự cố là **credential disclosure**.

### 21.1. Bước 1 — Xác nhận và phân loại bí mật

Không paste raw token vào incident chat. Sử dụng safe event reference để xác nhận:

- Credential loại gì: access, refresh, ID, session cookie, OAuth code, client secret, DPoP proof?
- Token dành issuer/resource/client nào, có hiệu lực khi nào?
- Token có thể đã hết hạn, bị revoke, sender-bound hay còn có refresh capability?
- Log record thuộc dịch vụ/region nào và có bao nhiêu bản sao?
- Exposure window: bắt đầu từ phiên bản/config nào, ai có quyền xem/export?

Với **JWE ciphertext**, vẫn là bearer token nếu nó được dùng như credential. Với **ID token**, tập trung PII/privacy và RP security; với **authorization code**, cần xem PKCE/client binding và code đã redeem/chưa.

### 21.2. Bước 2 — Ngăn thêm dữ liệu bị lộ

1. Tắt/rollback **log statement, HTTP wiretap hoặc collector setting** đang in credential.
2. Đổi mức logging theo policy nếu cần nhưng **không** chỉ chuyển `DEBUG → INFO` rồi coi đã sửa khi `INFO` vẫn log raw DTO.
3. Hạn chế tạm quyền **đọc/export logs** hoặc cô lập dataset/sink bị ảnh hưởng.
4. Bảo vệ log collectors, replicas, dashboards, support exports.
5. Không xóa forensic evidence một cách tùy tiện; lưu bằng chứng vào **restricted incident evidence store** theo chính sách pháp lý/retention rồi xử lý remediation.

### 21.3. Bước 3 — Thu hồi đúng loại credential

| Credential lộ | Hành động chủ đạo | Điều cần nhớ |
| --- | --- | --- |
| **Access bearer token** | Revoke/denylist/grant invalidation nếu architecture hỗ trợ | JWT offline RS có thể vẫn tin đến `exp` nếu không có revocation-aware path |
| **Refresh token** | Revoke token/family/grant, rotation/reuse investigation, reauth khi cần | Token mới có thể đã được mint; rà cascade |
| **Session cookie** | Invalidate server session/rotate session identifiers, reauth | Chỉ xóa cookie ở browser không vô hiệu server-side session cho attacker |
| **Client secret** | Rotate secret, revoke client grants nếu cần, audit token issuances | Client credential có thể dùng để xác thực token endpoint |
| **`private_key_jwt` assertion** | Kiểm expiry/`jti` replay, client key/registration compromise | Assertion copy khác với private signing key leak |
| **Authorization code** | One-time redemption state, PKCE/redirect/client binding check | Có thể đã hết hạn/redeemed; vẫn điều tra callback/log path |
| **ID token** | Privacy/identity risk review, invalidate sessions nếu liên quan | Không coi mặc định như API access token |
| **DPoP-bound token** | Revoke/check proof-key compromise, usage audit | Stolen access token riêng có thể khó replay, nhưng exposure vẫn cần xử lý |
| **Private signing key/HMAC secret** | Emergency key distrust/rotate, incident escalation | Đây là key compromise có thể forge token, khác bearer leak |

**Tính chính xác quan trọng:** RFC 7009 quy định revocation endpoint cho token types, nhưng khả năng revoke access token và cách RS nhận trạng thái mới **tùy authorization server và token architecture**. Không tuyên bố “gọi revoke thành công nên tất cả stateless JWT ngay lập tức chết” nếu RS không có introspection/denylist/grant version/key distrust.

### 21.4. Bước 4 — Điều tra hành vi sử dụng

Đối chiếu:

- Safe issuance/refresh/grant revocation records.
- Authentication outcomes và unusual scopes/audiences.
- API access logs **không có raw tokens** nhưng có request ID, resource, status, trusted client/subject references theo chính sách.
- KMS/signing operations nếu có nghi ngờ key compromise.
- Vùng địa lý/thiết bị/client indicators được privacy/security policy cho phép.
- Thời điểm log read/export và request bất thường sau đó.

**Đừng khẳng định mọi request từ IP lạ là attacker**; NAT, proxies và mobile networks có thể làm tín hiệu mơ hồ. Sử dụng nhiều nguồn evidence và giảm rủi ro trước khi kết luận attribution.

### 21.5. Bước 5 — Xử lý các bản sao log và dữ liệu phái sinh

Lập inventory:

```text
app/container stdout
node logs and local buffers
collector durable queues/spool
central log indexes
APM/tracing datasets
saved dashboards/searches
SIEM alerts with samples
CSV/JSON exports
incident tickets / email / chat attachments
object storage backups and DR replicas
```

Thực hiện redaction/deletion theo khả năng và policy, có phối hợp pháp lý/audit. Với bản sao không thể purge ngay (ví dụ immutable backup), **đảm bảo credential đã được revoke/rotate**, hạn chế truy cập, ghi nhận retention và theo dõi cho tới hết rủi ro. Không nói “đã xóa hoàn toàn” nếu còn bản sao.

### 21.6. Bước 6 — Khôi phục và xác minh

1. Triển khai safe logging policy mới.
2. Chạy end-to-end canary tests cho tất cả relevant paths.
3. Kiểm logs không còn raw credentials **trước ingestion**.
4. Kiểm affected sessions/grants/tokens không còn dùng được theo security objective.
5. Theo dõi unusual attempts, errors, retries, new leakage alerts.
6. Hoàn thiện incident report, owner, timeline, impact, user/regulatory communications nếu được yêu cầu, và preventive actions.

### 21.7. Runbook tóm tắt

```mermaid
flowchart TD
    A[Confirmed token disclosure in log] --> B[Stop new logging and restrict exposure]
    B --> C[Classify token/credential type and scope]
    C --> D[Revoke or rotate appropriate credentials/grants/sessions]
    D --> E[Investigate use and exported log copies]
    E --> F[Remediate source/collector/retention]
    F --> G[Run canary and revocation verification]
    G --> H[Document evidence, impact and preventive controls]
```

## 22. Nếu access JWT đã hết hạn thì có cần hành động không?

**Không có một đáp án cho mọi trường hợp.** Một access JWT đã hết hạn và được RS kiểm `exp` chặt chẽ sẽ không còn dùng để gọi RS như token hợp lệ. Nhưng cần xác minh:

- Tại **thời điểm exposure**, token đã hết hạn hay vẫn còn hiệu lực?
- Log có kèm **refresh token**, session cookie hoặc client secret không?
- Đã có API requests đáng ngờ trước expiry chưa?
- RS có kiểm đúng `exp`, issuer, audience và clock skew không?
- JWT payload có lộ PII/claims nhạy cảm kể cả khi credential hết hạn không?
- Có bản sao token còn ở collector/export với policy retention rộng không?

Nếu chỉ có token access đã hết hạn, không có refresh capability, không có evidence misuse và đã sửa logging, mức độ response có thể khác leak refresh token còn hạn. **Điều tra bằng risk-based process thay vì mặc định mọi leak đều giống nhau**.

### 22.1. Token TTL giảm cửa sổ chứ không giải quyết nguồn rò

Một access token 5 phút vẫn có thể bị dùng sai trong 5 phút. TTL ngắn + refresh rotation là defense-in-depth, không cho phép log raw access/refresh token.

### 22.2. Scope và audience giới hạn blast radius

Access token `aud=orders-api`, `scope=orders:read` đúng profile có thể hạn chế attacker không gọi `payments-api` hoặc ghi orders. Nhưng:

- Một scope `read` vẫn có thể cho phép đọc dữ liệu nhạy cảm.
- RS phải kiểm `aud`/scope/resource ownership đúng.
- Cross-JWT confusion hoặc missing audience checks có thể khiến phạm vi vượt dự kiến.
- Token lộ trong log không tự bị thu hồi khi user logout nếu architecture không có enforcement.

### 22.3. Revocation và offline JWT

Với opaque token/introspection, AS có thể trả `active=false` tương đối nhanh theo cache policy. Với RS chỉ verify JWT offline và không có denylist/grant version/introspection, token **có thể tiếp tục được chấp nhận tới `exp`**. Việc lấy lại logs, thay logger hoặc “revoke trong AS database” không tự ép một RS offline thay đổi quyết định.

Khi security objective đòi ngừng chấp nhận trước expiry, cần **revocation-aware mechanism** hoặc emergency key distrust nếu sự cố ở cấp signing key. Đừng xoay **toàn bộ issuer signing key** cho một bearer leak đơn lẻ nếu có phương án revoke an toàn hơn; key rotation có blast radius lớn và cần phối hợp.

## 23. Sai lầm hay gặp khi ứng phó

### 23.1. “JWT đã ký nên không ai dùng được”

Sai. Signature giúp RS phát hiện token bị sửa, nhưng **copy nguyên token không làm signature invalid**.

### 23.2. “JWE đã mã hóa nên có thể log”

Sai. Ciphertext JWE vẫn là bearer credential nếu RS chấp nhận nó.

### 23.3. “Xóa dashboard là đủ”

Sai. Có thể còn collector spool, stdout, backups, exports, incident tickets và APM.

### 23.4. “Mask đoạn cuối token là đủ”

Không mặc định. JWT payload có thể bị lộ và partial strings vẫn gây correlation. **Không log credential** là nguyên tắc chính.

### 23.5. “Dùng regex ở SIEM sẽ bảo vệ”

Không đủ. Token có thể đã đi qua client SDK, app stdout, agent queue trước khi SIEM scrub; scanner cũng có false negatives.

### 23.6. “Chỉ access token rò, không cần kiểm refresh flow”

Chưa chắc. Nếu code log token endpoint response có cả `access_token`/`refresh_token`, phải đánh giá cả hai. Có thể có client secret trong request.

### 23.7. “Thu hồi token là đã xóa mọi dữ liệu nhạy cảm”

Không. Revocation giảm khả năng sử dụng credential, **không xóa JWT claims/PII** đã nằm trong logs.

### 23.8. “Đã bật HttpOnly/SameSite nên Cookie log vô hại”

Không. Cookie vẫn truyền từ browser đến backend/proxy và có thể bị copy từ server-side log.

### 23.9. “Nếu log token để debug, chỉ nhân viên nội bộ xem”

Không đủ. Least privilege, contractor access, exports, compromised accounts và long retention là một phần threat model; internal logs không phải vault mặc định.

### 23.10. “Có DPoP nên mọi bản sao token vô hại”

Không. Cần xem proof/private key compromise, replay window, metadata leakage và enforcement thực tế. Raw token vẫn không được log.

## 24. Tình huống thực tế và cách phân tích

### Tình huống A — `Authorization: Bearer` trong gateway access log

Một gateway có custom access log ghi tất cả request headers. Requests hợp lệ đến Orders API, log store xuất hiện raw `Authorization: Bearer ...`.

**Chẩn đoán:** Gateway đã phá vỡ ranh giới credential, dù Orders API không log. Cần **ngừng header capture tại nguồn**, rà các replica/export, hạn chế quyền log và revoke các access tokens theo phạm vi/độ mới. Thêm sentinel test chạy **qua gateway**; chỉ test Spring controller không bắt được lỗi này.

### Tình huống B — Refresh token bị in bởi OAuth client debug

OAuth client gọi `POST /oauth2/token` với `grant_type=refresh_token`. Khi AS trả `invalid_grant`, HTTP client logger in request form body chứa refresh token.

**Chẩn đoán:** Credential dài hạn bị lộ trong error path; không chỉ bật “log success = false”. Tắt body logging cho token endpoint, kiểm refresh family/reuse, revoke credentials liên quan nếu thật sự lộ, kiểm token endpoint metrics mà không in raw body.

### Tình huống C — JWT đã hết hạn nhưng chứa thông tin cá nhân

Một JWT `exp` đã qua, được phát hiện trong 90-day retained logs. Bearer credential có thể không còn dùng được, nhưng payload vẫn có email/tenant/authorization metadata.

**Chẩn đoán:** Vẫn cần privacy review và xử lý retention/exposure, không chỉ nói “exp đã hết”. Đồng thời xác minh token có bị xem trước expiry và có refresh/client credential đi kèm không.

### Tình huống D — JWE bị log vì “không đọc được claims”

Backend bật debug full `Authorization` cho encrypted access token JWE. Kỹ sư tin token mã hóa là vô hại.

**Chẩn đoán:** Nếu endpoint dùng bearer JWE, ciphertext vẫn replay được khi còn hạn. Không cần decrypt mới có thể gửi lại. Redact toàn bộ và đánh giá revocation/sender-constraining.

### Tình huống E — Log access URI chứa authorization code

Proxy access pattern lưu request line:

```text
GET /login/oauth2/code/provider?code=AUTH_CODE_TEST&state=STATE_TEST
```

**Chẩn đoán:** OAuth callback URL bị ghi vào access logs. PKCE/one-time code và client authentication giúp giảm khai thác nhưng không hợp thức hóa logging. Chuyển sang route template/status, không query. Kiểm redirect URI, referrer và callback middleware.

### Tình huống F — MDC giữ token qua thread pool

Một filter đặt `MDC.put("accessToken", bearer)`. Các async tasks dùng MDC context propagation, khiến token xuất hiện trong DB timeout logs và worker error logs; nếu không clear, còn có nguy cơ context leak giữa requests.

**Chẩn đoán:** Loại token khỏi MDC; truyền request ID/trace ID an toàn, dọn context đúng lifecycle và kiểm async paths.

### Tình huống G — OpenTelemetry baggage chứa credential

Service A chuyển access token vào baggage để Service B “xem được user”. Baggage lan tới nhiều services và APM exporter.

**Chẩn đoán:** Baggage không phải secure credential channel. Dùng chuẩn OAuth token propagation đúng endpoint/trust boundary, hoặc identity context được bảo vệ và xác thực; không đưa token vào tracing metadata.

### Tình huống H — Client credentials trong CI `set -x`

CI script dùng `set -x` khi gọi token endpoint với client secret. Runner ghi shell command + HTTP verbose output, test logs được giữ 30 ngày.

**Chẩn đoán:** Credential leak qua pipeline. Đổi/rotate client secret hoặc credentials theo incident scope, ngừng shell tracing, chuyển sang secret injection và access controls; rà artifacts/cache/export.

### Tình huống I — Test thất bại in cả token response

JUnit so hai token response objects bằng `assertEquals(expected, actual)`; failure output in fields `access_token`/`refresh_token`.

**Chẩn đoán:** Test framework không xấu; **assertion strategy** chưa an toàn. So safe fields/behavior, tránh `toString()` object có token, dùng test-only keys và quét CI output.

### Tình huống J — Spring Security 401 nhưng exception chứa JWT

Một custom `JwtDecoder` throw `new JwtException("invalid: " + token)`. Error handler ghi `ex.getMessage()`.

**Chẩn đoán:** Raw JWT được log mỗi lần validation fail. Throw stable code/message không chứa input và log normalized reason, không stringify exception có token. Test 401 path cùng sentinel.

### Tình huống K — Proxy URI đã che query nhưng path có token

Một endpoint legacy dùng `/download/{access_token}`. Proxy chỉ bỏ query khỏi logs, nhưng `$uri` vẫn chứa token trong path.

**Chẩn đoán:** “Không log query” chưa đủ. Không đặt bearer credential trong URL path; migrate sang protected header/session contract. Với logs chỉ dùng route template có trusted route configuration, không raw path.

### Tình huống L — DPoP-bound token bị log cùng DPoP proof

Client gửi `Authorization: DPoP <access-token>` và `DPoP: <proof JWT>`, gateway log toàn bộ headers.

**Chẩn đoán:** Phải loại cả access-token và proof. Sender binding có thể làm replay khó hơn, nhưng proof trong cùng event có thể bị dùng trong bound window nếu verifier sai hoặc đáp ứng điều kiện replay; key/private proof exposure cần được đánh giá riêng. Không dựa vào DPoP để bỏ redaction.

### Tình huống M — Client không thể revoke access JWT ngay

AS phát access JWT 30 phút; một log dataset lộ token khi còn 20 phút. RS chỉ verify offline signature/exp, không denylist hay introspection.

**Chẩn đoán:** Gọi revoke endpoint có thể không thay đổi RS behavior. Incident response cần xác định **time-to-deny thật**; cân nhắc traffic isolation/denylist/grant version hoặc key distrust chỉ khi risk/blast radius justified. Sau sự cố cần thiết kế revoke-aware path nếu business SLA đòi.

### Tình huống N — Support tải raw log CSV

Một nhân viên support export hàng nghìn request records có `Cookie`, gửi file vào ticket của đối tác để phân tích.

**Chẩn đoán:** Token đã qua nhiều ranh giới: log store → CSV → ticket → external collaboration. Contain toàn bộ artifacts và readers, revoke sessions trong scope, bảo vệ evidence, thiết kế **safe export schema** chỉ gồm request ID/status/route.

### Tình huống O — Partial masking JWT

Logger ghi `eyJhbGci...{payload fields}...***`. Chữ ký bị cắt nhưng `sub`/`email`/`scope` vẫn có thể suy ra/đọc.

**Chẩn đoán:** Masking không bảo đảm privacy. Không log JWT fragments; dùng approved issuer/client/resource refs và auth decision metadata.

### Tình huống P — Chỉ SIEM đã mask, stdout vẫn có token

Collector rule thay raw `Authorization` bằng `<REDACTED>` trước khi đưa vào index. Tuy nhiên node logs và collector spool giữ raw string.

**Chẩn đoán:** Security gate **FAIL**. Chặn capture ở ứng dụng/gateway, đánh giá node/collector retention, sau đó giữ downstream redaction như defense-in-depth.

### Tình huống Q — Có hệ thống mã hóa log nhưng vẫn lộ quyền

Log store được mã hóa at rest bằng KMS nhưng quá nhiều nhóm có permission xem và export records. Token được ghi raw trong encrypted log.

**Chẩn đoán:** Encryption at rest bảo vệ storage medium, không ngăn authorized/compromised reader sử dụng credential. Cần least privilege, export audit, token redaction và revoke.

### Tình huống R — Old token còn trong backup bất biến

Incident remediation xóa index chính nhưng bản immutable backup vẫn còn và chỉ hết retention sau vài tháng.

**Chẩn đoán:** Đừng tuyên bố đã xóa hoàn toàn. Revoke/rotate credentials, giới hạn quyền backup, ghi nhận residual risk và retention schedule, duy trì audit/evidence theo chính sách.

### Tình huống S — Log “token fingerprint” trở thành global user tracker

Mỗi API log `SHA256(access_token)` thành metric label để nhóm vận hành correlate. Token được dùng trên nhiều services.

**Chẩn đoán:** Có thể tạo stable identifier/high-cardinality và không giải quyết nhu cầu thực. Dùng trace ID/request ID cho request correlation; nếu security audit thực sự cần token-level correlation, xem xét **keyed HMAC fingerprint trong restricted telemetry** với privacy/retention review.

### Tình huống T — Incident chỉ focus access token mà bỏ Basic secret

Từ log `/oauth2/token`, nhóm chỉ tìm `access_token` trong JSON response. Request header lại chứa `Authorization: Basic ...` cho confidential client.

**Chẩn đoán:** Cần inventory **cả hai chiều request và response**, form body và headers; rotate client credentials nếu bị lộ, đánh giá refresh token và token grants cùng cửa sổ.

## 25. Bài thực hành

### Bài A — Threat model cho Orders API

Vẽ luồng:

```text
Browser / mobile client
  -> API Gateway
  -> Spring Orders Resource Server
  -> Downstream Payments API
  -> Log/Trace Collector -> SIEM -> CSV exports
```

Đánh dấu **nơi TLS kết thúc**, nơi có `Authorization: Bearer`, nơi token được truyền tiếp, ai có quyền đọc logs và các bước attacker có thể dùng token bị lộ. Nêu trust boundary **log read → API access**.

### Bài B — Phân loại loại credential

Một log chứa bốn trường:

```text
access_token  = TEST_ONLY_ACCESS_CREDENTIAL
refresh_token = TEST_ONLY_REFRESH_CREDENTIAL
id_token      = TEST_ONLY_ID_TOKEN
client_secret = TEST_ONLY_CLIENT_SECRET
```

Phân loại phạm vi ảnh hưởng, thứ tự containment/revocation và vì sao ID token không được dùng như access token theo profile thông thường.

### Bài C — JWT đọc được payload

Giải thích tại sao JWS JWT có `sub`/`aud`/`scope` trong Base64url **không bí mật**. Vì sao log chỉ header+payload nhưng bỏ signature vẫn có privacy risk, kể cả khi credential không thể được replay từ fragment đã cắt?

### Bài D — JWE encrypted token

Một access token JWE `RSA-OAEP-256/A256GCM` bị ghi raw trong log. Attacker không có private decryption key. Có thể replay ciphertext tới đúng RS không? Cần những điều kiện nào để token vẫn bị từ chối? So sánh TTL, revoke, DPoP và mTLS.

### Bài E — Sửa Java anti-pattern

```java
// SAI
log.info(
    "headers={} body={} exception={}",
    request.getHeader("Authorization"),
    requestBody,
    ex.getMessage()
);
```

Viết lại thành **structured safe event** chỉ có request ID, method, trusted route template, status và normalized error class. Không stringifies request, headers hoặc DTO.

### Bài F — HTTP client outbound

Một `WebClient` gọi `orders-api` với OAuth access token nhưng bật wiretap DEBUG. Dựa trên `SafeWebClientTelemetry`, thiết kế interceptor chỉ log method/status/duration và cấu hình tắt capture headers/body; test lỗi 4xx/5xx/retry.

### Bài G — OAuth callback

Proxy đang log full `GET /login/oauth2/code/app?code=...&state=...`. Hãy sửa access logging sang **route template không query**, bảo vệ callback, nêu PKCE `S256`, one-time code và tại sao chúng **không cho phép** log authorization code.

### Bài H — Token endpoint form và response

Một client dùng refresh token grant. Hãy liệt kê tất cả fields không được log ở request/response, gồm `refresh_token`, `Authorization: Basic`, `client_secret`, `access_token`, `id_token` nếu có. Thiết kế safe event `token_exchange result`.

### Bài I — NGINX access log

Cấu hình legacy:

```nginx
log_format bad '$remote_addr "$request" "$http_authorization" "$http_cookie"';
```

Giải thích từng đường leak và đề xuất format metadata-only, hạn chế retention/roles; test một route có token trong query/path với synthetic marker.

### Bài J — OpenTelemetry

Developer thêm `access_token` vào baggage để “dễ trace”. Mô tả đường propagation tới downstream exporters. Đề xuất dùng trace/span IDs và safe context; test cả sampling on/off và exception events.

### Bài K — Synthetic sentinel test

Viết integration test đưa một sentinel vào `Authorization`, `Cookie`, OAuth refresh form và 401 exception path. Kiểm **app stdout, log agent, collector, APM, export**. Vì sao chỉ kiểm một root Logback appender chưa đủ?

### Bài L — Exception class

Custom auth filter throw `new RuntimeException("invalid token " + bearer)`. Hãy thay bằng safe error code/exception type và `AuthenticationEntryPoint`, để 401 không chứa raw credential. Kiểm filter chain trước MVC controller.

### Bài M — Logback levels

Một team đề xuất chỉ đặt `root=INFO` và bỏ việc review `log.info("token={}", token)`. Tại sao điều này không đủ? So sánh **logging level**, **source allowlist**, **collector redaction** và **DLP scans**.

### Bài N — CI debug

CI log chứa refresh token do `curl -v` và `set -x`. Viết runbook ngừng leak, giới hạn artifacts, revoke affected credentials, rotate secret, kiểm access logs và thiết kế test-only tokens cho tương lai.

### Bài O — Access JWT offline revocation

Access JWT còn hạn 20 phút bị lộ. AS có RFC 7009 endpoint nhưng RS chỉ verify offline và không kiểm denylist/introspection. Hãy giải thích **time-to-deny thật**, các phương án giảm rủi ro và vì sao không tùy tiện rotate toàn bộ issuer signing key cho mỗi single-token leak.

### Bài P — Refresh family

Một refresh token R1 đã bị ghi log; AS dùng rotation R1→R2. Hãy nêu cách xác định family/grant state, revoke phù hợp, điều tra reuse và các access tokens đã được phát. Giải thích vì sao xóa dòng log không ngăn R1 bị replay nếu credential còn active.

### Bài Q — Quyền truy cập log

Ba nhóm có quyền: developers chỉ cần latency, SRE cần lỗi hạ tầng, security team cần incident audit. Hãy định nghĩa **RBAC**, safe fields, export approval và retention. Tại sao encrypt log at rest chưa đủ?

### Bài R — Token fingerprint

Một team muốn log `SHA256(token)` ở mọi API call. Phân tích privacy, stable correlation/high-cardinality và token entropy; thiết kế **request ID** trước, chỉ cho **restricted HMAC token fingerprint** khi có use case security audit rõ.

### Bài S — Key và token bị lộ khác gì?

So sánh incident:

1. Một access bearer token bị lộ.
2. Một refresh token bị lộ.
3. HS256 signing secret bị lộ.
4. RSA private signing key của AS bị lộ.

Nêu attacker capabilities, scope revoke/rotation, JWKS/verifier trust và vì sao **signing-key compromise** nguy hiểm hơn một bearer credential đơn lẻ.

### Bài T — Viết một policy cho hệ thống thật

Soạn policy gồm:

- Allowed log fields ở gateway, Spring API và HTTP clients.
- Cấu hình HTTP debug/wiretap/OTel.
- Token endpoint/callback safe logging.
- CI secret redaction và token fixture.
- Retention/least-privilege/export.
- Synthetic canary tests/PR gates.
- Credential leak incident runbook, owner và time-to-deny evidence.

Định nghĩa tiêu chí **PASS/FAIL** có thể chạy trong CI/sandbox thay vì chỉ khẩu hiệu “không log token”.

## 26. Checklist trước khi triển khai production

### 26.1. Thiết kế và phân loại credentials

- [ ] Inventory access/refresh/ID/JWT/JWE/opaque tokens, session cookies, authorization codes, PKCE verifier, client secrets và client assertions.
- [ ] Xem **mọi bearer credential** là sensitive, dù JWT ký hoặc JWE mã hóa.
- [ ] Có data flow request/response qua gateway, AS, RS, browser/mobile, HTTP clients, queues và telemetry.
- [ ] Có policy ownership cho logging schema, token issuance/revocation và incident response.
- [ ] Biết các endpoint nhạy cảm: OAuth authorization callback, token, introspection, revoke, login và logout.
- [ ] Không truyền access/refresh tokens qua URL query/path nếu có phương án header/standard protocol phù hợp.

### 26.2. Logging tại nguồn

- [ ] Default log schema **allowlist**, không serialize toàn bộ request/response/DTO/security context.
- [ ] `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `DPoP`, `X-Api-Key` và custom token headers không được log raw.
- [ ] Không log full URI/query/callback URL; dùng route template trusted nếu cần.
- [ ] Không log token endpoint request form và response body.
- [ ] Không log access/refresh/ID token, authorization code, PKCE verifier hoặc client secret ở DEBUG/TRACE.
- [ ] Không dùng `toString()` của OAuth DTO/`Authentication`/JWT claims để debug.
- [ ] Không log raw exception message nếu có thể chứa token/URL/header.
- [ ] Error code được chuẩn hóa, external response không lộ token/key metadata.
- [ ] Request/trace IDs không được tạo bằng raw token hoặc user-controlled arbitrary strings.
- [ ] MDC/async context chỉ chứa allowlisted safe fields, luôn clear đúng lifecycle.
- [ ] Outbound HTTP client logs chỉ có safe method/status/duration, không header/body/URL chứa secrets.
- [ ] Wiretap/full Feign or HTTP client logging không được bật cho auth-token traffic trong production.

### 26.3. Telemetry và infrastructure

- [ ] Gateway, WAF, ingress, load balancer, service mesh và servlet container access-log patterns đã được review.
- [ ] OpenTelemetry baggage không chứa bearer/refresh/ID/session secrets.
- [ ] Traces không capture raw auth headers, token endpoint bodies, URL query hoặc claims.
- [ ] APM error capture/exception events không chứa token ở 4xx/5xx/retry/timeout.
- [ ] Redaction tại source, collector redaction là defense-in-depth.
- [ ] Collector spool, durable queue, node stdout và exported dashboards cũng được kiểm.
- [ ] Log storage có encryption/transit, least privilege, access reviews, export audit, retention và backup governance.
- [ ] Browser console, frontend error reporting, session replay và mobile crash logs không chứa token.
- [ ] CI runners không in secrets qua `set -x`, verbose curl, environment/config dumps hoặc assertion failures.
- [ ] Không dán production credentials vào tickets/chat/attachments.

### 26.4. Token lifecycle và defense-in-depth

- [ ] RS kiểm issuer, audience, expiry, token type, scope và resource-level authorization.
- [ ] Token issuance theo đúng authentication/consent/grant gates của OAuth/OIDC.
- [ ] Access token TTL và scope/audience giới hạn tối thiểu theo use case.
- [ ] Refresh token storage/rotation/reuse detection và revoke policy đã được xác minh.
- [ ] DPoP/mTLS sender constraint được verify nếu threat model yêu cầu, không chỉ được khai trong token.
- [ ] Có thực tế **time-to-deny** cho revoked JWT/opaque token, xét RS caches/introspection/offline verification.
- [ ] Không coi key rotation là cơ chế revoke per-token mặc định.
- [ ] Encrypted JWE vẫn được redact như bearer token có thể replay.
- [ ] JWT claims/PII không bị log dù token hết hạn hoặc signature bị cắt.

### 26.5. Tests, detection và response

- [ ] Chạy synthetic sentinel ở inbound, outbound, OAuth callback, token endpoint, error/retry và async paths.
- [ ] Kiểm cả **app stdout, container logs, collector, APM, CI, export**, không chỉ một dashboard.
- [ ] Test valid sandbox tokens và invalid canaries, vì happy-path và error-path logging khác nhau.
- [ ] Regression tests khi đổi Spring/HTTP client/OTel/gateway/logging version.
- [ ] Schema/DLP checks phát hiện unknown sensitive fields và likely token patterns, không xem regex là đủ.
- [ ] Alert khi production DEBUG/wiretap/credentials capture được bật trái policy.
- [ ] Có runbook: stop leak, restrict logs, classify secret, revoke/rotate, investigate usage, remediate copies, retest.
- [ ] Incident evidence được bảo vệ, deletion/retention theo policy và không tuyên bố xóa sạch khi còn replicas.
- [ ] User/regulatory notifications được đánh giá theo incident scope và quy định áp dụng.
- [ ] Có owner, kiểm toán, postmortem và target time-to-containment/time-to-deny phù hợp rủi ro.

## 27. Câu hỏi tự kiểm tra

**1. Bearer access token trong log có còn nguy hiểm nếu JWT đã được ký không?** Có. Chữ ký kiểm integrity; attacker có thể replay nguyên token còn hiệu lực nếu không có ràng buộc khác.

**2. JWE mã hóa payload có cho phép log raw ciphertext không?** Không. Nếu JWE là bearer credential, ciphertext vẫn có thể được xuất trình lại.

**3. Opaque token có an toàn để log vì không decode được không?** Không. Opaque token là credential reference, không cần decode để replay.

**4. Refresh token bị lộ thường khác access token như thế nào?** Nó có thể được dùng để xin access tokens mới, phụ thuộc client binding/rotation/AS policy và thời gian sống.

**5. ID token có phải access token của RS không?** Không theo profile OAuth/OIDC thông thường; nhưng ID token leak vẫn gây privacy/security risk.

**6. PKCE `S256` giúp gì nếu authorization code lộ trong callback log?** Nó ràng buộc đổi code với verifier, giảm nguy cơ code interception; không cho phép log code/verifier.

**7. Token endpoint body có thể chứa secret nào?** `refresh_token`, `client_secret`, `code_verifier`, `code` và các client assertions tùy grant/method.

**8. Token endpoint response có thể chứa gì?** Access token, refresh token, ID token và metadata; không log nguyên body.

**9. `Authorization: Basic` có nên log vì không phải Bearer không?** Không. Basic có thể chứa client credentials.

**10. Session cookie có được log nếu bật HttpOnly không?** Không. HttpOnly chỉ giới hạn JavaScript access, không ngăn server/proxy log Cookie.

**11. Vì sao không log full URL?** Query/path có thể chứa authorization code, token, secret hoặc PII.

**12. Fragment URL thường có xuất hiện trong HTTP request tới server không?** Thường không, nhưng frontend/browser telemetry vẫn có thể thu.

**13. Vì sao một Spring filter safe chưa đủ?** Gateway, container access logs, outbound client, APM, collector, CI có thể log riêng.

**14. Vì sao `log.debug("{}", requestDto)` nguy hiểm?** `toString` có thể serialize raw token/secret fields.

**15. Vì sao không log `Authentication` object?** Có thể chứa principal/token/claims hoặc details nhạy cảm.

**16. MDC có nên chứa JWT không?** Không. MDC context có thể lan sang nhiều logs/async tasks.

**17. OpenTelemetry baggage có dùng truyền access token để debug không?** Không. Nó truyền metadata qua dịch vụ, có nguy cơ rò rỉ rộng.

**18. Trace sampling 1% có loại bỏ rủi ro không?** Không. Chỉ một sampled request chứa token thật cũng gây leak.

**19. Log redaction ở central SIEM đã đủ chưa?** Chưa. Token có thể đã nằm trong stdout/collector spool trước khi scrub.

**20. Tại sao allowlist logging tốt hơn denylist regex?** Nó không đưa sensitive fields vào event từ đầu; denylist dễ bỏ sót format/đường khác.

**21. Có thể log một phần JWT để correlate không?** Không mặc định; payload/metadata vẫn nhạy cảm, partial strings có thể tạo correlation.

**22. Dùng SHA-256(token) ở mọi API log có phù hợp không?** Không mặc định; stable identifier/privacy/cardinality risk. Ưu tiên request ID, restricted HMAC fingerprint khi có lý do rõ.

**23. Synthetic sentinel là gì?** Chuỗi giả không phải credential thật được đưa qua pipeline test để phát hiện raw logging.

**24. Test Logback ListAppender PASS có chứng minh gateway không leak không?** Không. Nó chỉ kiểm một phần log trong JVM.

**25. Tại sao cần test 401/5xx/retry?** Nhiều loggers chỉ dump request/exception khi lỗi.

**26. Có nên in token thật vào CI để test masking không?** Không. Dùng test-only fixtures/canaries với access giới hạn.

**27. Phát hiện token trong log, bước đầu tiên là gì?** Ngăn nguồn leak, hạn chế exposure và phân loại credential/scope; bảo vệ evidence.

**28. Xóa dashboard log có loại bỏ mọi bản sao không?** Không. Có thể còn stdout, agent spool, APM, exports, backups và tickets.

**29. Khi refresh token bị log, cần xử lý gì?** Revoke/rotate family/grant theo policy, điều tra reuse và tokens phát thêm, cùng sửa pipeline.

**30. Khi private signing key bị log, chỉ revoke một access token là đủ không?** Không. Key compromise có thể cho attacker forge tokens; cần emergency key distrust/rotation và phạm vi incident rộng.

**31. Có thể revoke một JWT access token offline ngay bằng RFC 7009 không?** Không đảm bảo. RS cần cơ chế nhận trạng thái revoke/denylist hoặc chờ expiry theo architecture.

**32. Access token hết hạn thì hoàn toàn vô hại trong log?** Không. Trước expiry có thể đã bị dùng; payload/PII và credentials khác vẫn cần xem.

**33. Scope/audience có giúp giảm blast radius không?** Có nếu được RS validate, nhưng không ngăn log leak.

**34. DPoP/mTLS-bound token có cần redaction không?** Có. Sender constraints là defense-in-depth, không cho phép log raw.

**35. Vì sao log encryption at rest chưa đủ?** Người có quyền đọc/export log vẫn có thể thấy và dùng raw credential.

**36. Có nên ghi raw stack trace mọi OAuth exception không?** Không nếu trace/message có thể chứa token/secret; cần safe error classification và audit controls.

**37. Một log chứa `kid` có phải token leak không?** `kid` riêng không phải bearer token, nhưng untrusted/raw value có thể tạo injection/cardinality/metadata risk; dùng trusted key refs khi cần.

**38. Không có token trong SIEM nhưng có token trong container stdout thì test đạt không?** Không. Secret đã xuất hiện ở một sink.

**39. Làm sao điều tra mà không lưu token thật vào ticket?** Dùng safe request ID, issuer/client/resource refs, time window, sanitized error codes và restricted security telemetry.

**40. Kết quả mong muốn của kiểm soát token leakage qua log là gì?** Không thu raw credential ở bất kỳ logging boundary nào, phát hiện leak nhanh, revoke/rotate đúng loại credential và xác minh token không bị sử dụng trái phép theo security objective.

## 28. Tiêu chuẩn và tài liệu tham khảo

Những tài liệu sau là nguồn để đối chiếu **semantics và best practices** khi triển khai; cần kiểm phiên bản framework/stack đang sử dụng. Phần trích dẫn này không đồng nghĩa các ví dụ cấu hình đều là mặc định bắt buộc trong mọi hệ thống.

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer credential model, Authorization header, `invalid_token`/`insufficient_scope` và rủi ro token qua URI query.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** token endpoint, grant types, access/refresh token, OAuth roles và token response.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** authorization code binding, `code_verifier`/`code_challenge` và `S256`.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** code interception, bearer token theft/replay, refresh-token protection và OAuth security guidance.
- **RFC 7009 — OAuth 2.0 Token Revocation:** token revocation endpoint và grant handling.
- **RFC 7662 — OAuth 2.0 Token Introspection:** active state và RS revocation-aware validation cho opaque/token types.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** issuer, audience, claims, token type và RS validation.
- **RFC 7515 / RFC 7519 — JWS / JWT:** JWS signing và registered claims; chữ ký không mã hóa payload.
- **RFC 7516 — JSON Web Encryption (JWE):** confidentiality, compact serialization và authenticated encryption.
- **RFC 8725 — JWT Best Current Practices:** algorithm/key trust, explicit typing và cross-JWT confusion.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** certificate sender-constraining.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** DPoP proof, key binding, replay requirements.
- **OpenID Connect Core 1.0:** ID token, RP validation, nonce, user identity, token endpoint contexts.
- **OWASP Logging Cheat Sheet:** dữ liệu không nên log, event integrity, log injection, access control, sanitization và retention.
- **OWASP Secrets Management Cheat Sheet:** secret inventory, key/credential management, rotation, incident processes.
- **OWASP JSON Web Token Cheat Sheet:** JWT leakage, safe storage, sidejacking và token validation.
- **OWASP OAuth 2.0 Cheat Sheet:** OAuth flow/token handling và các rủi ro liên quan.
- **OWASP Error Handling Cheat Sheet:** tránh lộ dữ liệu qua exception/error responses.
- **OpenTelemetry Specification / Semantic Conventions:** span attributes, trace context, baggage, instrumentation và exporter controls.
- **W3C Trace Context / Baggage specifications:** trace propagation và metadata; không dùng chúng làm nơi truyền bearer secrets.
- **Spring Security OAuth2 Resource Server/Client documentation:** Bearer filters, `JwtDecoder`, introspection, `AuthenticationEntryPoint` và OAuth client flows.
- **Spring Boot/Logback/SLF4J documentation:** logging levels, appenders, MDC, structured events và log configuration.
- **NGINX HTTP Log Module documentation:** access `log_format` variables và cách tránh raw request URI/headers.

**Kết luận:** **Token leakage qua log là một đường đánh cắp credential thực sự**, không chỉ là lỗi “log quá chi tiết”. JWT có chữ ký vẫn có thể bị replay; JWE được mã hóa cũng có thể được gửi nguyên vẹn dưới dạng bearer token; refresh token và session cookie có thể kéo dài quyền truy cập của kẻ xấu. Cách bảo vệ hiệu quả là **không thu thập raw token ngay tại nguồn**, dùng **structured logging allowlist**, không log Authorization/Cookie/callback URL/token endpoint bodies/exception messages, đồng thời kiểm gateway, Java/Spring HTTP clients, OpenTelemetry, APM, CI, collectors và backups. Dùng synthetic canary tests để chứng minh pipeline thực tế sạch credential; khi đã lộ, phải **contain, revoke/rotate đúng loại token/secret, điều tra sử dụng, xử lý các bản sao log và xác minh time-to-deny**. Scope, audience, TTL, DPoP/mTLS, refresh rotation và revocation giúp giảm thiệt hại, nhưng **không thay nguyên tắc cốt lõi: token là credential, không phải log field**.
