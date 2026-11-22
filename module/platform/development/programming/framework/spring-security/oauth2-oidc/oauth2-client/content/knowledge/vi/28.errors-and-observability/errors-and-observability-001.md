# 28.1. Phân loại lỗi ở authorization, callback, token và UserInfo

Trong **Spring Security OAuth 2.0/OIDC Client**, thông báo chung “OAuth login failed” không đủ để xác định nguyên nhân. Một lỗi tại Authorization Endpoint khi người dùng từ chối consent, một callback không khớp `state`, Token Endpoint trả `invalid_grant`, và UserInfo trả HTTP 401 đều có thể khiến màn hình đăng nhập thất bại. Nhưng chúng xảy ra ở **những ranh giới tin cậy, bước xử lý và trách nhiệm khác nhau**.

Bài này xây dựng cách **phân loại lỗi theo giai đoạn**, mã giao thức, HTTP status, exception type, hệ thống gây lỗi và hành động phục hồi. Nội dung áp dụng cho Spring Security OAuth2 Client/OIDC Relying Party trên **Spring MVC/Servlet** và **Reactive WebFlux**, có các ví dụ cấu hình, hướng xử lý an toàn, sơ đồ, test cases, logging/metrics, dashboard và runbook.

> **Quy tắc đầu tiên:** Trước khi đọc `error`, HTTP 400, HTTP 401 hoặc một exception, hãy xác định **request nào đang thất bại và hệ thống nào trả lỗi**. Một HTTP 401 ở UserInfo Endpoint không giống HTTP 401 của Reports API; `invalid_grant` lúc đổi authorization code không giống `invalid_grant` khi refresh token.

## 1. Bản đồ luồng lỗi của OAuth2/OIDC

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Browser
    participant RP as Spring Security OAuth2/OIDC Client
    participant Session as Session / Authorized Client Store
    participant OP as Authorization Server / OP
    participant UI as UserInfo Endpoint

    User->>Browser: Chọn Đăng nhập
    Browser->>RP: GET /oauth2/authorization/company
    Note over Browser,RP: A — Authorization initiation
    RP->>Session: Lưu OAuth2AuthorizationRequest (state, PKCE, nonce)
    RP-->>Browser: 302 tới authorization_endpoint
    Browser->>OP: User authentication + consent
    Note over Browser,OP: B — Authorization decision
    OP-->>Browser: Redirect ?code=... hoặc ?error=...
    Browser->>RP: GET /login/oauth2/code/company
    Note over Browser,RP: C — Callback correlation
    RP->>Session: Khôi phục request + kiểm tra state
    RP->>OP: POST /token, code + client auth + PKCE
    Note over RP,OP: D — Token exchange
    OP-->>RP: Tokens hoặc OAuth2 error
    RP->>RP: Xác minh ID Token (signature, iss, aud, nonce)
    Note over RP,RP: E — OIDC ID Token validation
    opt UserInfo được sử dụng
      RP->>UI: GET /userinfo với Bearer access token
      Note over RP,UI: F — UserInfo
      UI-->>RP: Claims hoặc lỗi
    end
    RP->>Session: Lưu Authentication và OAuth2AuthorizedClient
    RP-->>Browser: Login success hoặc failure handler
```

Trong tên bài, bốn điểm cần phân biệt là **authorization**, **callback**, **token** và **UserInfo**. Nhưng khi quan sát thực tế cần thêm:

- **ID_TOKEN_VALIDATION:** token endpoint có thể trả HTTP 200 rồi RP mới phát hiện JWT/issuer/nonce sai.
- **PROVIDER_DISCOVERY/JWKS:** lỗi metadata, TLS hoặc signing key có thể xuất hiện trước hoặc trong login.
- **AUTHORIZED_CLIENT_PERSISTENCE:** lỗi lưu token/session là lỗi của RP storage, không phải provider.
- **TOKEN_REFRESH:** dùng cùng Token Endpoint nhưng khác grant, vòng đời và hành động.
- **RESOURCE_SERVER_API:** lỗi gọi API sau login không đồng nghĩa OAuth2 Login thất bại.

### 1.1. Bảng các giai đoạn

| Giai đoạn | Chủ thể | Đầu vào quan trọng | Lỗi tiêu biểu |
|---|---|---|---|
| Authorization initiation | RP | `registrationId`, scopes, redirect URI, authorization request | ClientRegistration không có; session store lỗi |
| Authorization decision | OP + Browser | Session OP, consent, authorization request | `access_denied`, `invalid_scope` |
| Callback correlation | RP | `code`/`error`, `state`, saved authorization request | Missing request, state mismatch, replay |
| Token exchange | RP → Token Endpoint | Code, client authentication, redirect URI, PKCE verifier | `invalid_grant`, `invalid_client` |
| ID Token validation | RP | JWT signature, issuer, audience, nonce | JWT invalid, wrong `iss`/`aud` |
| UserInfo | RP → UserInfo | Access token, UserInfo claims | 401 `invalid_token`, `sub` mismatch |
| Authorized client persistence | RP → local/DB store | Registration, principal, token | DB unavailable, wrong key |
| Token refresh | RP → Token Endpoint | Refresh token, client auth | `invalid_grant`, rotation race |
| Downstream API | RP → Resource Server | Bearer access token | 401 `invalid_token`, 403 `insufficient_scope` |

### 1.2. Phân loại theo hai trục

**Trục stage:**

```text
AUTHORIZATION_INITIATION
AUTHORIZATION_RESPONSE
CALLBACK_CORRELATION
TOKEN_EXCHANGE
ID_TOKEN_VALIDATION
USERINFO
AUTHORIZED_CLIENT_PERSISTENCE
TOKEN_REFRESH
RESOURCE_SERVER_CALL
```

**Trục category:**

```text
USER_DENIED
CLIENT_CONFIGURATION
INVALID_REQUEST
PROTOCOL_VALIDATION
SECURITY_REJECTION
REMOTE_PROVIDER_FAILURE
NETWORK_OR_TLS
TIMEOUT
RATE_LIMIT
SESSION_OR_STORAGE
ACCOUNT_MAPPING
INTERNAL_ERROR
```

Ví dụ:

```text
stage=AUTHORIZATION_RESPONSE
category=USER_DENIED
protocolError=access_denied
action=show_safe_message
```

Khác:

```text
stage=TOKEN_EXCHANGE
category=CLIENT_CONFIGURATION
protocolError=invalid_client
action=alert_integration_owner
```

Đây là **taxonomy vận hành do ứng dụng tự thiết kế**, không phải các tên error mới của OAuth2. Luôn giữ riêng mã OAuth2 gốc và stage nhận được.

## 2. Anatomy của OAuth2 error

### 2.1. Authorization response lỗi

Authorization Server có thể redirect browser trở lại RP:

```http
HTTP/1.1 302 Found
Location: https://portal.example.test/login/oauth2/code/company?error=access_denied&state=EXAMPLE_STATE
```

### 2.2. Token Endpoint lỗi

Token Endpoint thường trả JSON lỗi:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant",
  "error_description": "Example provider message"
}
```

### 2.3. Trường dữ liệu cần hiểu

| Field | Ý nghĩa | Lưu ý bảo mật |
|---|---|---|
| `error` | OAuth2 error code hoặc extension provider-specific | Có thể dùng phân loại, cần giới hạn kích thước/ký tự |
| `error_description` | Mô tả do provider cung cấp | Không hiển thị nguyên văn cho user, có thể chứa PII/untrusted content |
| `error_uri` | URI tham khảo giải thích lỗi | Không tự fetch URI tùy ý do response cung cấp |
| `state` | Liên kết authorization response với request trước đó | Không dùng làm tracing ID; không ghi giá trị vào log |
| HTTP status | Trạng thái của request tới một endpoint | Không đủ để xác định stage/root cause |

**Không hiển thị full OAuth2 error response hay callback URL cho frontend.** Các URL có thể chứa code, state hoặc dữ liệu không nên ghi vào telemetry.

### 2.4. Ba nhóm mã lỗi dễ nhầm

**Authorization Endpoint** theo OAuth2 có thể dùng:

```text
invalid_request
unauthorized_client
access_denied
unsupported_response_type
invalid_scope
server_error
temporarily_unavailable
```

**Token Endpoint** thường dùng:

```text
invalid_request
invalid_client
invalid_grant
unauthorized_client
unsupported_grant_type
invalid_scope
```

**Bearer Resource Server** theo RFC 6750 có các mã:

```text
invalid_request
invalid_token
insufficient_scope
```

UserInfo Endpoint có thể dùng Bearer-style errors vì nó là một protected resource. Các API nghiệp vụ cũng có thể dùng những error codes này nhưng **không thuộc login flow**.

## 3. Authorization initiation: lỗi trước khi rời RP

Người dùng bấm:

```text
GET /oauth2/authorization/company
```

Spring Security cần resolve `ClientRegistration`, tạo authorization request, lưu `state` và PKCE/nonce nếu cần, rồi redirect tới Authorization Endpoint của OP.

### 3.1. Các lỗi điển hình

| Biểu hiện | Nguyên nhân gợi ý |
|---|---|
| Không tìm thấy registration | URL dùng provider ID thay registration ID, thiếu cấu hình |
| Discovery lỗi | `issuer-uri` sai, TLS/DNS/metadata không hợp lệ |
| Authorization Endpoint URI sai | Registration nhầm issuer/provider |
| Redirect URI sai public host | Reverse proxy forwarded headers không đúng |
| Không lưu được authorization request | Session/Redis store lỗi, serialization hoặc timeout |
| Custom request resolver exception | Sai scope, state, redirect hoặc code customization |
| Tenant/issuer không được phép | Backend chủ động chặn dynamic provider vì trust policy |

Có những lỗi xuất hiện **ngay lúc startup** do discovery/ClientRegistration initialization, thay vì khi user bấm login. Vì vậy runbook cần có category cho `PROVIDER_DISCOVERY`/configuration.

### 3.2. Các thành phần Spring Security

**Servlet:**

- `ClientRegistrationRepository`.
- `OAuth2AuthorizationRequestRedirectFilter`.
- `OAuth2AuthorizationRequestResolver`.
- `AuthorizationRequestRepository<OAuth2AuthorizationRequest>`.
- `HttpSessionOAuth2AuthorizationRequestRepository`.

**Reactive:**

- `ReactiveClientRegistrationRepository`.
- `OAuth2AuthorizationRequestRedirectWebFilter`.
- `ServerOAuth2AuthorizationRequestResolver`.
- `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>`.
- `WebSessionOAuth2ServerAuthorizationRequestRepository`.

Nếu dùng `SecurityWebFilterChain`, không dùng Servlet `HttpSessionOAuth2AuthorizationRequestRepository` thay WebSession repository.

### 3.3. Dấu hiệu nhận biết

- Browser chưa tới OP.
- Chưa có callback `code` hoặc `error` từ OP.
- Token Endpoint chưa được gọi.
- Trace/log của RP chỉ đến request resolver/config/session store.

Trường hợp browser đã tới OP và OP hiển thị “invalid redirect URI” thì đây thường là **Authorization Endpoint validation**, không phải lỗi tạo callback của RP.

### 3.4. Cách xử lý

- Kiểm tra `registrationId` và `provider` trong YAML; chúng khác nhau.
- Kiểm tra issuer URI, HTTPS, discovery và provider metadata.
- Đăng ký đúng callback URI tại OP, không dùng wildcard quá rộng.
- Chỉ tin forwarded headers từ reverse proxy đáng tin.
- Kiểm tra session store và cookie TTL.
- Nếu lỗi là config cố định, alert team phụ trách thay vì yêu cầu user retry liên tục.
- Không dùng issuer URL do browser truyền vào để tự khám phá endpoints nếu chưa có trust/SSRF controls.

## 4. Authorization decision: OP từ chối hoặc policy không thỏa

Ở giai đoạn này, browser đã đến OP. OP xử lý đăng nhập, MFA, policy, consent và trả authorization response.

### 4.1. `access_denied`

Ví dụ:

```http
GET /login/oauth2/code/company?error=access_denied&state=EXAMPLE_STATE HTTP/1.1
Host: portal.example.test
```

`access_denied` có thể là:

- Người dùng nhấn “Cancel/Deny”.
- User từ chối consent.
- OP áp dụng conditional access policy.
- Tài khoản không được phép dùng Client hoặc scope.
- Một yêu cầu authentication/MFA không được hoàn tất.
- Provider gộp nhiều nguyên nhân vào cùng mã.

**Không luôn kết luận user bấm Cancel.** Tìm thêm category hoặc OP audit events khi cần nhưng không tự động coi đây là hệ thống hỏng.

### 4.2. Các mã authorization error

| Code | Ý nghĩa | Nhóm action |
|---|---|---|
| `access_denied` | Resource owner hoặc OP từ chối authorization | Thông báo an toàn; user có thể thử lại |
| `invalid_request` | Yêu cầu thiếu/sai/trùng tham số | Sửa request/config |
| `unauthorized_client` | Client không được phép thực hiện cách authorization này | Kiểm tra OP Client policy |
| `unsupported_response_type` | OP không hỗ trợ response type | Kiểm tra `response_type=code` |
| `invalid_scope` | Scope không được cấp/không hợp lệ | Điều chỉnh scope/consent |
| `server_error` | OP internal failure | Monitoring/SLO/incident |
| `temporarily_unavailable` | OP tạm thời không khả dụng | Backoff, giới hạn retry |

### 4.3. Mã lỗi của provider có thể khác chuẩn

Một số OP thêm error codes riêng cho MFA, thiết bị, session, tenant policy, identity federation hoặc quản trị. Đừng viết controller chỉ chấp nhận những mã cố định rồi trả 500 cho mọi code lạ. Cách xử lý:

1. Ghi `protocolErrorCode` trong danh sách đã làm sạch.
2. Ánh xạ code phổ biến sang category ổn định.
3. Với code không nhận diện, dùng `PROVIDER_SPECIFIC`/`UNKNOWN`.
4. Gửi thông điệp UX an toàn và correlation ID.
5. Không hiển thị raw `error_description` hoặc tải `error_uri` tùy ý.

### 4.4. Có cần retry ngay?

Với user từ chối consent, **không** tự redirect trở lại OP vô hạn. Với `temporarily_unavailable`, có thể cho user chủ động thử lại hoặc backoff. Với `invalid_scope` và `unauthorized_client`, user retry sẽ không giải quyết nếu ClientRegistration/OP policy chưa thay đổi.

## 5. Callback: OP báo lỗi hay RP từ chối response?

Callback chuẩn thường có mẫu:

```text
/login/oauth2/code/{registrationId}
```

Ở đây có ít nhất hai trường hợp:

```text
Nhánh A — OP đã quyết định lỗi:
  callback ?error=access_denied&state=...
  -> lỗi bắt nguồn từ Authorization Endpoint / consent

Nhánh B — OP trả code:
  callback ?code=...&state=...
  -> RP không tìm thấy saved request hoặc state không khớp
  -> lỗi xảy ra tại callback correlation
```

Cả hai cùng “hiện trên callback” nhưng cách xử lý khác nhau.

### 5.1. Kiểm tra bắt buộc

RP cần giữ và xác minh:

- `state` gắn với request đã tạo trước đó.
- Session/WebSession còn giữ `OAuth2AuthorizationRequest` tương ứng.
- Registration ID/issuer và flow không bị đánh tráo.
- PKCE verifier được giữ cho token exchange.
- OIDC nonce được giữ cho ID Token validation.
- Authorization request không bị tiêu thụ/replay.
- Redirect URI đúng context gốc.
- Callback chỉ sử dụng endpoint đã được đăng ký với OP.

Không tự lấy một `code` từ query parameter rồi gửi sang Token Endpoint tùy ý mà bỏ authorization request/state.

### 5.2. `authorization_request_not_found`

Một lỗi thường gặp là Spring không tìm được authorization request đã được lưu trước redirect. Nguyên nhân có thể:

- Session hết hạn giữa initiation và callback.
- Browser không gửi cookie do SameSite/domain/path.
- User mở nhiều tabs và custom/session repository làm flow trước bị thay thế.
- Load balancer chuyển callback tới pod không có local session.
- Spring Session Redis timeout/down.
- App restart với in-memory sessions.
- Custom repository làm mất `state`/nonce/PKCE attributes.
- Callback được gọi trực tiếp khi chưa từng khởi tạo login.

Không “sửa” bằng cách bỏ state validation. Hãy sửa session architecture, cookie configuration và repository behavior.

### 5.3. `invalid_state` hoặc state mismatch

Nếu callback state không khớp saved authorization request, Spring phải từ chối flow. Đây có thể là lỗi nhiều tabs, cookie mất hoặc một nỗ lực login CSRF/callback injection.

Log tốt:

```text
stage=CALLBACK_CORRELATION
category=SECURITY_REJECTION
reason=state_mismatch
registrationId=company
correlationId=internal-random-id
```

Log không an toàn:

```text
state=actual-secret-value
code=actual-authorization-code
Cookie=actual-session-id
```

### 5.4. SameSite và callback POST

Authorization Code Flow thường callback bằng top-level GET, tương thích với nhiều cấu hình `SameSite=Lax`. Nếu OP dùng `response_mode=form_post`, browser có thể thực hiện cross-site POST; cookie Lax có thể bị chặn.

Cần kiểm tra response mode, cookie `Secure`/`SameSite`, domain/path, proxy HTTPS và CSRF policy. Không mặc định bật `SameSite=None` cho tất cả cookies hoặc tắt CSRF toàn ứng dụng mà không đánh giá.

### 5.5. Callback có `code` chưa chắc login thành công

Code có thể hết hạn, đã dùng, không khớp Client hoặc verifier. Nó chỉ là đầu vào cho Token Endpoint, không phải chứng nhận user đã được Authentication tại RP.

## 6. Token Endpoint: authorization-code exchange

Sau callback hợp lệ, RP gọi Token Endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=EXAMPLE_CODE&
redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=EXAMPLE_CODE_VERIFIER
```

Những giá trị trên là giả. Không ghi code, verifier hoặc Client credentials thật vào logs. OP có thể yêu cầu Client authentication khác `client_secret_basic`, chẳng hạn `private_key_jwt` hoặc mTLS.

### 6.1. Các lỗi Token Endpoint

| Error | Ý nghĩa | Điều cần điều tra |
|---|---|---|
| `invalid_request` | Thiếu/sai tham số token request | Code, redirect URI, grant, verifier, encoding |
| **`invalid_client`** | Client authentication không hợp lệ | Client ID/secret, key, mTLS, auth method |
| **`invalid_grant`** | Authorization grant không hợp lệ/hết hạn/đã dùng/sai Client | Code expiry, replay, PKCE, redirect URI |
| `unauthorized_client` | Client không được phép dùng grant | Grant permission của OP |
| `unsupported_grant_type` | Không hỗ trợ grant yêu cầu | `authorization_code`, registration |
| `invalid_scope` | Scope không hợp lệ | Consent, scope restrictions |

Có thể gặp HTTP 400 hoặc 401 tùy lỗi và chính sách OP. Không dùng HTTP status đơn độc để kết luận loại lỗi.

### 6.2. `invalid_grant` lúc đổi code

Thường do:

- Code hết hạn.
- Code đã được dùng.
- Code không thuộc Client đã cấu hình.
- Redirect URI không khớp.
- PKCE `code_verifier` không khớp hoặc bị mất.
- Callback bị replay.
- Token Endpoint/registration trỏ sang tenant/issuer khác.

Không hiển thị “Sai mật khẩu” cho `invalid_grant`. OP xử lý password/MFA ở giai đoạn user authentication; RP không được suy đoán từ mã token.

### 6.3. `invalid_client` thường là lỗi vận hành

Xem xét:

- Client secret expired/rotated không đồng bộ.
- Sai `client_authentication_method`.
- Client ID trỏ nhầm tenant.
- Chứng thư mTLS hoặc private_key_jwt hỏng.
- Secret manager trả sai environment.
- Client bị disable tại OP.

Nếu lỗi xuất hiện cho nhiều users sau deployment, nên alert integration owner. Yêu cầu user đổi mật khẩu thường không liên quan.

### 6.4. Network, TLS, timeout, 429 và 5xx

Token request có thể lỗi trước khi nhận JSON OAuth2:

| Biểu hiện | Nhóm lỗi | Hành động |
|---|---|---|
| DNS failure | Network | Kiểm tra DNS/egress |
| TLS handshake | Security/Network | Kiểm tra CA/hostname/mTLS, không tắt TLS verification |
| Connect timeout | Network/Dependency | Timeout/backoff phù hợp |
| Read timeout | Dependency | Quan sát latency/availability |
| HTTP 429 | Rate limit | `Retry-After` và quota policy |
| HTTP 500/503 | OP outage | Circuit breaker/incident |
| HTML error page | Proxy/WAF/contract | Không parse như JSON thành công |
| Unexpected JSON schema | Protocol/dependency | So tài liệu/version provider |

### 6.5. Retry authorization code rất nhạy cảm

Authorization code dùng **một lần**. Nếu Token Endpoint xử lý xong nhưng response mất do timeout, retry với code cũ có thể trả `invalid_grant`. Không áp retry vô hạn giống một GET idempotent. Với trường hợp không thể phục hồi an toàn, yêu cầu user bắt đầu Authorization Code Flow mới.

## 7. Token Endpoint trả HTTP 200 nhưng OIDC Login vẫn thất bại

Token response mẫu:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "EXAMPLE_ID_TOKEN"
}
```

Spring có thể nhận response hợp lệ HTTP nhưng sau đó phát hiện:

- Thiếu hoặc sai kiểu `access_token`/`token_type`.
- OIDC flow thiếu `id_token` khi cần.
- ID Token JWT parse lỗi, sai signature, không có signing key phù hợp.
- `iss` khác issuer của provider đã cấu hình.
- `aud` không chứa Client ID RP.
- `exp`/`iat` không hợp lệ theo chính sách.
- `nonce` không khớp request khi nonce được sử dụng.
- Các điều kiện `azp`/hash claims theo OIDC không thỏa khi áp dụng.

**Đừng ghi các lỗi này là Token Endpoint `invalid_grant` khi Token Endpoint đã trả success.** Nên dùng stage **ID_TOKEN_VALIDATION** với category `SECURITY_REJECTION` hoặc `DEPENDENCY_JWKS`.

### 7.1. JWT chữ ký hợp lệ chưa đủ

Một ID Token do OP tin cậy ký nhưng `aud` là Client khác không được dùng để xác thực RP hiện tại. Tương tự, `iss` phải khớp issuer expected, không chỉ so hostname tùy ý.

### 7.2. `nonce` khác `state`

- `state` liên kết authorization response/callback với authorization request.
- PKCE verifier liên kết authorization code với Client đã khởi tạo.
- OIDC `nonce` liên kết ID Token với authentication request khi flow sử dụng.
- Issuer/audience/signature validation xác minh token đúng nguồn và đúng Client.

Không tắt một cơ chế vì đã bật cơ chế khác.

### 7.3. JWKS rotation hoặc discovery failure

RP có thể không tải được signing key khi OP đổi khóa, mạng lỗi hoặc metadata sai. Đây là **lỗi dependency ở bước validation**, không đồng nghĩa OP trả OAuth2 error.

Cần phân biệt:

```text
stage=ID_TOKEN_VALIDATION
dependency=JWKS
category=NETWORK_OR_TLS
```

và:

```text
stage=ID_TOKEN_VALIDATION
category=SECURITY_REJECTION
reason=invalid_signature
```

Không chấp nhận ID Token không xác minh chữ ký khi JWKS unavailable.

## 8. UserInfo: HTTP, Bearer, response và identity binding

Sau khi có access token và ID Token, RP **có thể** truy cập UserInfo Endpoint để lấy claims. Việc gọi UserInfo là tùy flow, scope, provider metadata và `OidcUserService`, **không phải điều bắt buộc của mọi OIDC Login**.

Ví dụ:

```http
GET /userinfo HTTP/1.1
Host: login.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

### 8.1. Bảng lỗi UserInfo

| Nhóm lỗi | Dấu hiệu | Nguyên nhân |
|---|---|---|
| Bearer rejection | HTTP 401 `invalid_token` | Token expired/revoked/sai resource, issuer hoặc policy |
| Permission | HTTP 403 / `insufficient_scope` | Scopes/consent không đủ |
| Network/TLS | Timeout, TLS, DNS | OP/proxy/network |
| HTTP dependency | 429, 5xx | Rate limit/outage |
| Response encoding | HTML thay JSON, JSON parse lỗi | Proxy, provider contract |
| Required claims | Thiếu `sub` | UserInfo response không đúng contract |
| **Identity mismatch** | `sub` UserInfo khác `sub` ID Token | Security rejection, phải từ chối |
| Optional claims | Thiếu `email`/`name` | Có thể hợp lệ, tùy scope/provider |
| Account mapping | Unique constraint, ownership | Lỗi ứng dụng/DB, không phải UserInfo HTTP error |

### 8.2. `sub` UserInfo phải khớp ID Token

Ví dụ:

```json
{
  "id_token_claims": {
    "iss": "https://login.example.test",
    "sub": "user-A",
    "aud": "portal-client"
  },
  "userinfo_response": {
    "sub": "user-B",
    "name": "Another user"
  }
}
```

Không được sử dụng UserInfo của `user-B` như thuộc về `user-A`. OIDC RP phải kiểm tra subject matching, không tự map sang user khác chỉ vì email hoặc tên giống.

### 8.3. 401 UserInfo khác 401 downstream API

UserInfo thuộc OIDC OP. Nếu nó là nguồn claims cần để xây OIDC principal, lỗi có thể làm login thất bại.

Downstream Reports API là một Resource Server nghiệp vụ, có thể trả 401 **sau khi user login thành công**. Lỗi này thường là vấn đề access token/permission/connection, không nhất thiết buộc logout portal.

### 8.4. Missing optional claims không bằng security failure

UserInfo có thể không trả `email`, `phone_number`, `picture` hoặc `name` nếu scope/consent/provider không cấp. Nếu application bắt buộc email cho nghiệp vụ, hãy thiết kế onboarding/verification riêng. Không coi mọi email missing là ID Token signature invalid.

### 8.5. Claim từ UserInfo không tự thành role quản trị

Một UserInfo response có `groups=["admin"]` không tự có nghĩa user được cấp `ROLE_ADMIN` tại mọi tenant. Phải có claim-source contract, trusted issuer, account mapping và authorization policy được kiểm soát.

### 8.6. UserInfo không được gọi có phải lỗi?

**Không tự động.** Một số flows chỉ cần claims từ ID Token; framework có thể không gọi UserInfo theo cấu hình. Nếu quan sát UserInfo traffic bằng 0, hãy kiểm tra có endpoint và điều kiện gọi hay không trước khi đặt incident.

## 9. Authorized client storage và session là lỗi riêng

Sau OIDC login, Spring có thể lưu:

- `SecurityContext`/`Authentication` vào local session.
- `OAuth2AuthorizedClient` chứa access token/refresh token vào repository/service.
- External identity mapping vào database nghiệp vụ.

Các lỗi có thể xuất hiện:

- Redis/session store unavailable.
- JDBC authorized client service không lưu được.
- Principal name/registration ID không nhất quán.
- Hai instances dùng in-memory store riêng.
- Schema migration sai.
- Session cookie hết hạn ngay sau login.

Không ghi những lỗi này là “UserInfo timeout” hoặc “Token Endpoint invalid_grant” chỉ vì triệu chứng user không vào được ứng dụng.

### 9.1. Lưu đúng khóa

`OAuth2AuthorizedClientService` thường lookup theo `(registrationId, principalName)`. Một record có thể tồn tại nhưng service tra bằng principalName khác do account mapping thay đổi.

Ví dụ:

```text
Login lưu: ("company", "oidc-sub-3")
Worker tra: ("company", "account-42")
=> Không tìm thấy
```

Cần sửa mapping/ownership, không tự chọn một principal ngẫu nhiên hoặc dùng token của user khác.

### 9.2. WebSession/HttpSession không đồng nghĩa token service

Spring Session Redis có thể chia sẻ session nhưng không tự biến `InMemoryOAuth2AuthorizedClientService` thành database phân tán. Khi nhiều pods, phải kiểm tra cả **authorization request session store** và **authorized client token store**.

## 10. Token refresh: cùng Token Endpoint nhưng khác vòng đời

Sau khi login, Spring OAuth2AuthorizedClientManager có thể xin access token mới qua Refresh Token Grant:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

### 10.1. `invalid_grant` lúc refresh

Thường liên quan:

- Refresh token expired/revoked.
- User thu hồi consent.
- Refresh token rotation.
- Client/tenant thay đổi không tương thích.
- Token reuse/replay detection.
- Đồng thời nhiều jobs làm mới cùng token.

**Một error code, hai bối cảnh:**

| `invalid_grant` ở đâu? | Khả năng nguyên nhân | Action |
|---|---|---|
| Authorization-code exchange | Code expired/reused, PKCE, redirect URI | Khởi tạo login mới hoặc sửa protocol/config |
| Refresh Token Grant | Token revoked/expired/rotated | Cleanup đúng authorized client, reconnect khi cần |

### 10.2. Refresh rotation race

```mermaid
sequenceDiagram
    participant A as Pod A
    participant B as Pod B
    participant DB as Shared Token Store
    participant OP as Token Endpoint
    A->>DB: Đọc RT-1
    B->>DB: Đọc RT-1
    A->>OP: refresh_token=RT-1
    OP-->>A: AT-2 + RT-2
    A->>DB: Ghi RT-2
    B->>OP: refresh_token=RT-1
    OP-->>B: invalid_grant / reuse detection
```

Shared JDBC/Redis store **không tự bảo đảm single-flight refresh**. Có thể cần per-connection locking/optimistic versioning, không ghi đè token mới bằng stale write và không retry cùng refresh token vô hạn.

### 10.3. Lỗi refresh không phải luôn lỗi login

Một user có thể vẫn có Corp portal session hợp lệ nhưng Calendar refresh token đã bị thu hồi. Thường nên đánh dấu Calendar connection `RECONNECT_REQUIRED`, không tự logout toàn portal, trừ khi security policy yêu cầu.

## 11. Resource Server API errors: tách khỏi lỗi UserInfo

Một downstream API có thể trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

hoặc:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

| Lỗi | Nơi phát ra | Hướng xử lý |
|---|---|---|
| `invalid_client` | Token Endpoint | Client credentials/config |
| `invalid_grant` | Token Endpoint | Authorization code hoặc refresh |
| `invalid_token` | UserInfo Endpoint | Access token dùng cho UserInfo |
| `invalid_token` | Reports API | Access token dùng cho Reports API |
| `insufficient_scope` | UserInfo/API | Quyền/scope của token |
| ID Token wrong `iss` | RP validator | OIDC security, không phải API |
| Missing `state` | RP callback handler | Session/flow correlation |

### 11.1. HTTP 401 không luôn do token expired

Resource Server có thể từ chối do issuer, audience, signature, revoke, DPoP/mTLS proof hoặc policy. Không khẳng định chỉ cần refresh token là sửa được.

### 11.2. HTTP 403 không nên retry vô hạn

Nếu API yêu cầu scope không được cấp, refresh cùng scope không sinh thêm quyền. Cần user consent/scopes hoặc policy phù hợp. Đừng tự chọn token của ClientRegistration khác để vượt quyền.

## 12. Tổng hợp root cause theo đối tượng chịu trách nhiệm

| Owner hoặc hệ thống | Nhóm lỗi | Ví dụ |
|---|---|---|
| Người dùng | Hủy consent, không hoàn tất xác thực | `access_denied` |
| RP configuration | Sai registration/redirect/Client secret | `invalid_client`, `invalid_request` |
| RP security validation | State/nonce/issuer/audience mismatch | Callback rejected, ID Token invalid |
| OP/AS | Policy, outage, metadata issue | `temporarily_unavailable`, 5xx |
| Mạng/proxy | DNS/TLS/timeouts, forwarded headers | Redirect mismatch, TLS failure |
| Session/token store | Redis/JDBC unavailable, wrong key | `authorization_request_not_found`, missing authorized client |
| UserInfo | Bearer rejection, response invalid | 401, invalid `sub` |
| Account mapping | Business identity/ownership | Duplicate external identity, tenant isolation |
| Resource Server | Access token/scope rejection | 401/403 after successful login |

Giai đoạn và owner có thể khác nhau. Ví dụ callback thất bại nhưng root cause là session store ở RP; UserInfo 401 nhưng root cause là Token Endpoint đã cấp token sai resource theo provider configuration.

## 13. Spring Security exception types

Các lớp thường thấy:

- **`OAuth2Error`**: mô tả `errorCode`, `description` và `uri`.
- **`OAuth2AuthenticationException`**: lỗi authentication liên quan OAuth2, chứa `OAuth2Error`.
- **`OAuth2AuthorizationException`**: lỗi authorization/token lifecycle, chứa `OAuth2Error`.
- **`AuthenticationException`**: nhóm lỗi xác thực Spring Security.
- **`WebClientResponseException`** hoặc HTTP client exceptions: lỗi khi gọi remote API/Token/UserInfo tùy implementation.
- Lỗi transport/TLS/timeouts từ HTTP client, Redis hoặc JDBC.

**Không có một exception type duy nhất cho mọi stage.** Exception có thể bị wrap. Phân loại stage nên dựa vào **vị trí instrument/request** thay vì chỉ dò exception text.

### 13.1. Ví dụ mapper cho OAuth2Error

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

public final class SafeOAuthErrorCode {

    private SafeOAuthErrorCode() {}

    public static String classify(Throwable exception) {
        OAuth2Error error = null;

        if (exception instanceof OAuth2AuthenticationException auth) {
            error = auth.getError();
        } else if (exception instanceof OAuth2AuthorizationException authorization) {
            error = authorization.getError();
        }

        if (error == null) {
            return "non_oauth2_error";
        }

        String code = error.getErrorCode();
        if (code == null) {
            return "unknown_oauth2_error";
        }

        return switch (code) {
            case "access_denied" -> "access_denied";
            case "invalid_request" -> "invalid_request";
            case "invalid_client" -> "invalid_client";
            case "invalid_grant" -> "invalid_grant";
            case "invalid_scope" -> "invalid_scope";
            case "temporarily_unavailable" -> "temporarily_unavailable";
            default -> "other_oauth2_error";
        };
    }
}
```

Đây là **ví dụ classifier nhỏ**, không phải cơ chế phân loại stage hoàn chỉnh. Stage cần được truyền từ nơi gọi hoặc context đã được xác định đáng tin. Error descriptions không được nối vào output UI.

## 14. Servlet OAuth2 Login failure handler

Spring Security MVC cho phép cài `AuthenticationFailureHandler` trong `oauth2Login`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

@Configuration
public class OidcFailureConfiguration {

    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {

        AuthenticationFailureHandler failureHandler =
            (request, response, exception) -> {

                String safeReason = "authentication_failed";

                if (exception instanceof OAuth2AuthenticationException oauth2) {
                    String code = oauth2.getError().getErrorCode();
                    if ("access_denied".equals(code)) {
                        safeReason = "authorization_declined";
                    } else if ("invalid_grant".equals(code)) {
                        safeReason = "token_exchange_failed";
                    }
                }

                // Ghi metrics/log đã redact tại đây nếu cần.
                // Không xuất exception.message, code/state/tokens.
                response.sendRedirect(
                    request.getContextPath() +
                    "/login?error=" + safeReason
                );
            };

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .failureHandler(failureHandler)
            )
            .build();
    }
}
```

Ví dụ cho thấy mapping sang **nhãn cố định**, không thể tự suy stage một cách hoàn hảo: `invalid_grant` ở callback login có khả năng là token exchange, nhưng trong hệ thống refresh token cần một stage khác. Khi triển khai thực, tích hợp telemetry ở đúng bước/Client manager.

### 14.1. Failure handler không quan sát mọi lỗi từ initiation

`oauth2Login().failureHandler(...)` thường xử lý authentication failures tại OAuth2 Login filter. Nhưng lỗi tại `OAuth2AuthorizationRequestRedirectFilter`, startup discovery hay OP error page không redirect về RP có thể không đi qua đó. Vì vậy dashboard chỉ từ failure handler này có thể bỏ sót lỗi trước callback.

### 14.2. Không dùng fallback “login thành công giả”

Không nên:

```java
// Không làm điều này:
// if (stateMismatch || badSignature) { createAuthenticatedUserAnyway(); }
```

Khi Spring từ chối vì state, nonce, issuer, audience hoặc signature, đây là một **security rejection** cần giữ nguyên.

### 14.3. Tránh login loop

Nếu `/login?error=...` lập tức tự chuyển user trở lại `/oauth2/authorization/company`, một lỗi cấu hình có thể tạo vòng lặp redirect. Cần trang lỗi public, thông điệp phù hợp và user quyết định retry.


## 15. Reactive WebFlux: phân loại và điều hướng lỗi

Trong WebFlux, dùng các abstraction reactive như `SecurityWebFilterChain`, `ServerHttpSecurity` và `ServerAuthenticationFailureHandler`. Không trộn Servlet `HttpSecurity`/`AuthenticationFailureHandler` vào WebFlux.

Ví dụ một failure handler đưa user tới một URL cố định:

```java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ServerAuthenticationFailureHandler;

@Bean
SecurityWebFilterChain reactiveChain(ServerHttpSecurity http) {

    ServerAuthenticationFailureHandler failureHandler =
        (webFilterExchange, exception) -> {

            var response = webFilterExchange.getExchange().getResponse();
            response.setStatusCode(HttpStatus.SEE_OTHER);
            response.getHeaders().setLocation(
                URI.create("/login?error=authentication_failed")
            );

            return response.setComplete();
        };

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/", "/login", "/error").permitAll()
            .anyExchange().authenticated()
        )
        .oauth2Login(login -> login
            .authenticationFailureHandler(failureHandler)
        )
        .build();
}
```

Đây là ví dụ định hướng: triển khai thực tế nên dùng một redirect handler có sẵn khi phù hợp và bổ sung logging/metrics không lộ dữ liệu.

### 15.1. Reactor context và token manager

Trong WebFlux, Authentication được truyền qua Reactive SecurityContext/Reactor context. Nếu một pipeline chạy ngoài HTTP request, không được giả định luôn có `ServerWebExchange` và session.

Một job/background worker cần service-based reactive manager nếu làm việc với `client_credentials` hoặc authorized clients đã được cấp trước. Việc thiếu Reactive context có thể gây lỗi lookup token/Authentication, **không phải OP từ chối consent**.

### 15.2. Không block trong failure handler

Đừng dùng `block()` trên Netty event-loop để ghi audit database hoặc gọi external diagnostics. Blocking có thể gây cạn event-loop và làm nhiều request timeout. Dùng reactive storage hoặc boundary được quản lý đúng.

## 16. OIDC UserInfo customization

Khi dùng `OidcUserService`, ứng dụng có thể bổ sung mapping external user vào tài khoản nội bộ. Cần phân biệt:

1. **UserInfo HTTP error:** API thật sự trả 401/403/5xx.
2. **UserInfo validation error:** `sub` không khớp ID Token, JSON sai.
3. **Optional claim absent:** thiếu email/name dù identity vẫn hợp lệ.
4. **Business mapping error:** account ownership, unique constraint, tenant policy.
5. **Storage error:** database/Redis không sẵn sàng.

### 16.1. Wrapper không nên nuốt lỗi security

```java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class AuditedOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private final OidcUserService delegate = new OidcUserService();

    @Override
    public OidcUser loadUser(OidcUserRequest request) {
        try {
            return delegate.loadUser(request);
        } catch (RuntimeException ex) {
            // Ghi metric/log category đã redact.
            // Không log raw access token/ID token/UserInfo response.
            throw ex;
        }
    }
}
```

Trong ứng dụng thực, wrapper được wiring vào OIDC user service configuration phù hợp. Bài không giả định class này được auto-install chỉ vì đã khai báo. Mục tiêu là quan sát mà **không bỏ qua lỗi protocol/security**.

### 16.2. Optional profile khác identity validation

Nếu UserInfo không có `email`, app có thể yêu cầu user nhập/xác minh email riêng theo chính sách. Nhưng nếu UserInfo `sub` khác ID Token `sub` thì **phải từ chối response**, không fallback sang email hoặc ID Token để coi UserInfo sai như “thiếu dữ liệu không quan trọng”.

## 17. Lỗi refresh và manager failure handlers

`OAuth2AuthorizedClientManager` điều phối token cho outbound APIs. Có thể cấu hình `OAuth2AuthorizedClientProvider` gồm authorization code, refresh token và client credentials tùy yêu cầu.

Nếu Token Endpoint trả `invalid_grant` khi refresh:

- Ngừng dùng refresh token không hợp lệ.
- Không retry vô hạn cùng token.
- Xem lỗi đến từ rotation race hay revoke/expiry.
- Nếu required, remove/invalidate đúng authorized client theo registration/principal.
- Ghi trạng thái external connection như `RECONNECT_REQUIRED`.
- Yêu cầu reauthorization theo UX phù hợp.

Một số manager implementations của Spring có success/failure handlers mặc định. **Nếu thay `setAuthorizationFailureHandler` chỉ để log mà không giữ cleanup policy**, ứng dụng có thể lặp lại refresh token invalid. Cần kiểm tra đúng phiên bản và storage implementation.

### 17.1. Failure handler của WebClient khác failure handler của login

- **OAuth2 Login authentication failure handler:** xử lý user login callback/Authentication.
- **Authorized client manager authorization failure handler:** xử lý lỗi authorize/refresh tại Token Endpoint.
- **WebClient OAuth2 filter authorization failure handler:** có thể xử lý response OAuth2 error của Resource Server và cập nhật/loại authorized client theo policy.

Không dùng một lớp handler với giả định tất cả ba chặng có cùng ngữ nghĩa.

## 18. UX: thông báo đúng nguyên nhân nhưng không lộ bí mật

| Trường hợp | Thông điệp gợi ý | Hành động |
|---|---|---|
| User hủy consent | “Bạn chưa hoàn tất cấp quyền.” | Thử lại khi muốn |
| `state`/session hết hạn | “Phiên đăng nhập đã hết hạn, vui lòng bắt đầu lại.” | Bắt đầu OAuth2 login mới |
| OP tạm ngừng | “Dịch vụ đăng nhập tạm thời không khả dụng.” | Thử lại sau |
| Client configuration lỗi | “Không thể hoàn tất đăng nhập. Mã hỗ trợ: …” | Liên hệ support |
| ID Token validation thất bại | “Không thể xác minh phiên đăng nhập.” | Dừng flow, điều tra |
| UserInfo unavailable | “Không thể tải thông tin tài khoản lúc này.” | Thử lại/fallback policy |
| API connection refresh token bị revoke | “Cần kết nối lại dịch vụ bên ngoài.” | Reconnect đúng provider |
| Reports API 403 | “Bạn không có quyền thực hiện thao tác này.” | Quyền/scopes |

Không đưa raw `error_description`, stack trace, internal hostnames, Client secret, `code`, `state`, token hoặc cookie ra trang lỗi.

### 18.1. Correlation ID độc lập

`state` là tham số chống nhầm OAuth2 flow; **không dùng làm support ID/tracing ID**. Tạo một correlation ID độc lập, không nhạy cảm để user gửi cho support.

### 18.2. Phân biệt lỗi user và incident

Một lượng lớn `access_denied` do user từ chối consent có thể không cần incident alert. Ngược lại, hàng loạt `invalid_client` sau secret rotation hoặc callback state failures sau deploy là tín hiệu đáng báo động.

## 19. Structured logging an toàn

Một event gợi ý:

```json
{
  "event": "oauth2_login_failure",
  "stage": "TOKEN_EXCHANGE",
  "category": "CLIENT_CONFIGURATION",
  "protocol_error_code": "invalid_client",
  "grant_type": "authorization_code",
  "registration_id": "company",
  "provider_alias": "enterprise-op",
  "http_status": 401,
  "duration_ms": 182,
  "correlation_id": "internal-random-id",
  "outcome": "failure"
}
```

Đây là schema do ứng dụng tự thiết kế.

### 19.1. Các field hữu ích

- `stage`, `category` và `outcome`.
- `registration_id` và `provider_alias` được giới hạn từ config.
- `grant_type`: `authorization_code`, `refresh_token`, `client_credentials`.
- `protocol_error_code` đã chuẩn hóa hoặc bounded.
- `http_status`, `duration_ms` nếu có dependency call.
- `dependency` như `authorization`, `token`, `userinfo`, `jwks`, `session_store`.
- `correlation_id` độc lập.
- `exception_family`, không phải full message từ provider.

### 19.2. Tuyệt đối không ghi

```text
authorization code
state
nonce
code_verifier
access_token
refresh_token
id_token
client_secret
Authorization header
Cookie / Set-Cookie header
full callback URL with query
raw UserInfo profile JSON
untrusted error_description
```

Kiểm tra cả reverse proxy, APM, HTTP client interceptor, request/response body logging và tracing. Một filter đã redact tại controller không ngăn proxy ghi full callback URL.

### 19.3. Lựa chọn metric labels có cardinality thấp

```text
oauth2.login.failure{stage="callback",registration="company",category="security_rejection"}
oauth2.token.failure{grant="refresh_token",registration="calendar",error="invalid_grant"}
oauth2.userinfo.failure{registration="company",category="network"}
```

Không dùng user ID, email, token, state, raw URL hoặc error description làm metric labels. Những giá trị đó vừa nhạy cảm vừa tạo lượng time-series rất lớn.

## 20. Logs, metrics và tracing phục vụ câu hỏi khác nhau

| Công cụ | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Metrics | Lỗi nào tăng, ở stage nào? | `invalid_grant` refresh tăng theo cluster |
| Structured logs | Lỗi nào có cùng registration/provider? | `company` + `invalid_client` sau deploy |
| Distributed traces | Dependency nào chậm? | Token Endpoint 4s, UserInfo 100ms |
| Audit events | Ai thực hiện link/disconnect? | Account internal tạo connection |
| Synthetic checks | Login flow/provider có hoạt động? | OIDC test tenant đăng nhập định kỳ |
| OP admin logs | Vì sao provider từ chối? | Client disabled, consent policy |

### 20.1. Browser redirect làm trace bị đứt

Authorization Code Flow có browser đi qua OP rồi quay lại RP. Không mặc định một trace tự chạy xuyên suốt ba origins. Có thể dùng correlation được lưu server-side theo session/request trong phạm vi tin cậy; không đưa tracing headers bí mật hoặc state/token sang URL của OP.

### 20.2. Không log Token Endpoint body

Một HTTP client debug flag có thể ghi cả `refresh_token` hoặc `client_secret` trong form body. Chỉ đo status, latency, error code đã làm sạch và dependency identity.

## 21. Runbook chẩn đoán theo triệu chứng

Bước đầu tiên: **người dùng đã nhìn thấy trang nào?**

```text
Không rời Portal
  -> Authorization initiation / configuration / session

Đã tới OP, bị lỗi tại OP
  -> Authorization decision / provider policy

OP chuyển về Portal, Portal báo lỗi
  -> Callback correlation / token / ID Token / UserInfo

Đăng nhập Portal thành công, API thất bại
  -> Authorized client / refresh / Resource Server
```

Đây là định hướng ban đầu, không thay thế logs/traces.

### 21.1. Quy trình chẩn đoán 10 bước

1. Xác định **stage** thực tế.
2. Xác định **registration ID**, expected issuer và provider alias.
3. Xác định lỗi ở RP, OP Authorization, Token, UserInfo hay API.
4. Phân biệt protocol error code với HTTP status/exception class.
5. Với callback: kiểm tra session, saved request, state, nonce/PKCE có bị mất không.
6. Với Token Endpoint: xem **grant type** và Client authentication.
7. Với ID Token: xem signature/issuer/audience/nonce/JWKS, không bỏ validation.
8. Với UserInfo: xem 401/403, JSON, `sub` matching, optional claims.
9. Với API sau login: kiểm tra access token scope/audience và authorized client storage.
10. Kết luận owner và action; ghi correlation ID/log đã redact.

### 21.2. Matrix root cause → action

| Root cause | Xử lý an toàn |
|---|---|
| User denied consent | Thông báo và để user chủ động thử lại |
| Missing state/session | Sửa cookie/session store/routing, không bypass |
| Invalid redirect URI | Sửa OP registration/public host/proxy |
| `invalid_client` | Kiểm tra Client credentials/config, alert owner |
| Code `invalid_grant` | Xem PKCE/redirect/code reuse, tạo flow mới |
| Refresh `invalid_grant` | Xem rotation/revoke, cleanup/reconnect |
| Invalid ID Token | Dừng Authentication; điều tra issuer/JWKS/validator |
| UserInfo HTTP 401 | Kiểm tra access token/endpoint/consent |
| UserInfo `sub` mismatch | Không dùng response; điều tra bảo mật |
| OP 503/timeout | Backoff, monitor, thông báo unavailable |
| Reports API 403 | Kiểm tra scope/authorization, không tự logout |

## 22. Những chẩn đoán sai thường gặp

### 22.1. “Có `access_denied` nên hệ thống bị lỗi”

Có thể user vừa hủy consent. Đếm category `USER_DENIED` riêng thay vì trộn vào infrastructure error.

### 22.2. “`invalid_grant` là sai mật khẩu”

Không đúng. Đây là Token Endpoint error, thường liên quan code/refresh/token grant, không trực tiếp chứng minh user nhập password sai.

### 22.3. “UserInfo trả 401 nên ID Token sai chữ ký”

Không đúng. ID Token và access token có mục đích khác nhau. UserInfo có thể từ chối Bearer access token dù ID Token hợp lệ.

### 22.4. “API 403 nên bắt user login lại”

Có thể API thiếu scope/role hoặc business permission. Bắt login lại với cùng token/scope không tự tăng quyền.

### 22.5. “Không tìm thấy session, hãy bỏ kiểm tra state”

Không an toàn. Đây là ranh giới chống login CSRF/callback injection. Sửa session store/cookie/route.

### 22.6. “Token Endpoint trả 200 nên login chắc chắn thành công”

Không đúng. ID Token validation, UserInfo subject matching, account mapping và session persistence còn có thể thất bại.

### 22.7. “Có UserInfo Endpoint thì mọi login phải gọi nó”

Không đúng. Nhiều OIDC flows không yêu cầu UserInfo, tùy configuration/claims.

### 22.8. “OIDC login thành công nên mọi API dùng được access token đó”

Không đúng. Resource Servers có audience/scopes/policy khác nhau.

## 23. Kiểm thử theo từng stage

### Authorization initiation

- Registration ID không tồn tại.
- Issuer discovery 404/unavailable.
- Redirect URI/forwarded headers sai.
- Authorization request repository không lưu được.
- Custom resolver bị lỗi.
- User hủy consent.

### Callback

- Thiếu `state`.
- `state` sai hoặc không thuộc session.
- Authorization request hết hạn.
- Replay callback.
- Multi-tab concurrent flows.
- Callback bị chặn cookie khi `response_mode=form_post`.
- Callback có error từ OP nhưng được hiển thị an toàn.

### Token Endpoint

- Authorization code đã dùng/hết hạn.
- Client authentication sai.
- PKCE verifier mismatch.
- Redirect URI không khớp.
- HTTP 429/500/timeout/TLS.
- Token response thiếu trường cần thiết.
- Không retry code vô hạn.

### OIDC ID Token

- Signature invalid.
- Wrong `iss`/`aud`.
- Expired token.
- Nonce mismatch.
- JWKS unavailable/rotation.
- Claim type/format không hợp lệ.
- Không bypass validation.

### UserInfo

- HTTP 401 `invalid_token`.
- HTTP 403 `insufficient_scope`.
- 5xx/timeout/HTML response.
- JSON parse error.
- Missing `sub`.
- **`sub` mismatch ID Token**.
- Optional `email` missing.
- Business mapping/tenant conflict.

### Token refresh/API

- Refresh token revoked/rotated.
- Concurrent refresh trên hai pods.
- Access token sai audience.
- API 401 và 403.
- Client token gửi sai HTTP origin.
- External connection bị lỗi nhưng portal session vẫn hợp lệ.

## 24. Unit test an toàn cho error classifier

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SafeOAuthErrorCodeTest {

    @Test
    void accessDeniedUsesFixedCategory() {
        OAuth2Error error = new OAuth2Error(
            "access_denied",
            "Untrusted provider description",
            null
        );

        var exception = new OAuth2AuthenticationException(error);

        assertEquals(
            "access_denied",
            SafeOAuthErrorCode.classify(exception)
        );
    }

    @Test
    void unknownProviderCodeDoesNotLeakDescription() {
        OAuth2Error error = new OAuth2Error(
            "provider_specific_error",
            "Sensitive text from a provider",
            null
        );

        var exception = new OAuth2AuthenticationException(error);

        assertEquals(
            "other_oauth2_error",
            SafeOAuthErrorCode.classify(exception)
        );
    }
}
```

Test chỉ kiểm tra mapper. Nó **không** thực hiện browser redirects, state/PKCE, token exchange, JWKS hay UserInfo. `oidcLogin()` trong Spring Security Test cũng là mock Authentication và không thay kiểm thử protocol end-to-end.

### 24.1. Không phụ thuộc nguyên văn framework exception text

Message/stack trace có thể đổi theo Spring version và provider. Test nên assert:

- Outcome/stage.
- Mã lỗi chuẩn khi có.
- Không tạo Authentication khi validation fail.
- Không leak credential.
- Cleanup/reauthorization đúng.
- Error UI và support correlation phù hợp.

## 25. Bảng tra nhanh khi có sự cố

| Triệu chứng | Stage gợi ý | Điều kiểm tra trước |
|---|---|---|
| Login link không redirect | Initiation | Registration ID, resolver |
| OP báo redirect invalid | Authorization | Public URI và OP whitelist |
| User nhấn Cancel | Authorization response | `access_denied` |
| Callback missing request | Callback | Session/cookie/Redis |
| Callback state mismatch | Callback | Flow correlation/multi-tab |
| Token `invalid_grant` lúc login | Token exchange | Code/PKCE/redirect URI |
| Token `invalid_client` | Token exchange | Client authentication |
| Token 200 nhưng JWT fail | ID Token | Signature/issuer/audience/nonce |
| UserInfo 401 | UserInfo | Access token/scopes |
| UserInfo `sub` mismatch | UserInfo | Reject identity response |
| Missing email | UserInfo/mapping | Optional claims/onboarding |
| Refresh invalid_grant | Refresh | Rotation/revocation |
| Reports API 403 | Downstream API | Scope/role/resource |
| Lỗi chỉ khi nhiều pods | Session/storage | Shared session, principal key |
| Lỗi sau secret rotation | Token Endpoint/config | Client secret/key/mTLS |
| Lỗi sau đổi registration ID | Storage/config | Persisted token key và callback |

## 26. Bài tập tình huống

### Bài 1: User từ chối consent

OP redirect `?error=access_denied&state=...`. Đây là lỗi ở đâu?

**Đáp án gợi ý:** Authorization decision; callback chỉ chuyển thông tin lỗi về RP. Hiển thị “chưa hoàn tất cấp quyền” thay vì `invalid_grant`.

### Bài 2: Callback thiếu authorization request

Browser được OP chuyển về Portal nhưng Spring báo không tìm thấy request đã lưu.

**Đáp án gợi ý:** Callback correlation/session store. Kiểm tra cookie, TTL, multi-node routing; không bỏ state validation.

### Bài 3: `invalid_grant` ngay sau callback

Code đã bị dùng một lần do browser refresh.

**Đáp án gợi ý:** Token Endpoint không chấp nhận code reuse; khởi tạo login flow mới và điều tra request retry/replay.

### Bài 4: `invalid_grant` sau một tuần

Background job refresh token cũ sau rotation.

**Đáp án gợi ý:** TOKEN_REFRESH, không phải login. Kiểm tra stale refresh token/concurrency và reconnect.

### Bài 5: `invalid_client` sau deploy

Secret vừa đổi ở OP nhưng RP vẫn dùng secret cũ.

**Đáp án gợi ý:** Client authentication/configuration. Alert owner; không yêu cầu user reset password.

### Bài 6: ID Token sai audience

Token có chữ ký hợp lệ nhưng `aud=other-client`.

**Đáp án gợi ý:** ID_TOKEN_VALIDATION phải thất bại; signature không thay audience validation.

### Bài 7: UserInfo `sub` mismatch

ID Token `sub=user-A`, UserInfo `sub=user-B`.

**Đáp án gợi ý:** Security rejection, không map profile B vào user A.

### Bài 8: UserInfo không trả email

`sub` hợp lệ nhưng `email` absent.

**Đáp án gợi ý:** Optional claim; cần chính sách business mapping/onboarding, không tự coi là invalid token.

### Bài 9: API trả 403

Portal đã login, Reports API thiếu scope.

**Đáp án gợi ý:** Resource Server authorization; không tự chuyển sang token của provider khác.

### Bài 10: Callback POST mất cookie

OP dùng `form_post`, browser không gửi session cookie Lax.

**Đáp án gợi ý:** Kiểm tra SameSite/response mode/HTTPS; không bypass callback correlation.

### Bài 11: JWKS outage

Token Endpoint trả 200 nhưng RP không tải được signing keys.

**Đáp án gợi ý:** Stage ID_TOKEN_VALIDATION, dependency JWKS. Không chấp nhận unsigned token.

### Bài 12: Error description chứa PII

Provider trả email/user ID trong `error_description`.

**Đáp án gợi ý:** Redact, dùng mã lỗi cố định và correlation ID; không log nguyên văn.

### Bài 13: Hai providers bị mix-up

Login khởi tạo với `corp`, token request lại đi `partner`.

**Đáp án gợi ý:** Kiểm tra state/registration/issuer binding, không thử lần lượt các Token Endpoints.

### Bài 14: Metrics ghi state vào label

`oauth2_failures{state="..."}`.

**Đáp án gợi ý:** Sai do nhạy cảm và cardinality. Chỉ dùng stage/error category/registration đã giới hạn.

### Bài 15: UserInfo HTTP 401 nhưng ID Token hợp lệ

**Đáp án gợi ý:** Access token dành cho UserInfo bị từ chối. Phân biệt Bearer error với ID Token validation.

### Bài 16: Logged-in user không gọi được Calendar API

Calendar refresh token bị revoke nhưng Corp portal session vẫn hợp lệ.

**Đáp án gợi ý:** Đánh dấu connection `RECONNECT_REQUIRED` thay vì logout toàn Portal mặc định.

## 27. Checklist triển khai

- [ ] Có phân loại riêng initiation, authorization decision, callback, token, ID Token, UserInfo, refresh và API.
- [ ] HTTP status, OAuth2 error code, exception type và stage được lưu ở các field khác nhau.
- [ ] Authorization `access_denied` được phân biệt với provider outage.
- [ ] Callback state/authorization request luôn được xác minh.
- [ ] PKCE verifier/nonce/issuer/audience không bị bỏ qua khi lỗi.
- [ ] Token `invalid_grant` có `grant_type` để phân biệt code và refresh.
- [ ] Không retry authorization code hoặc refresh token invalid vô hạn.
- [ ] UserInfo `sub` được so khớp ID Token.
- [ ] Thiếu optional email không bị nhầm với identity mismatch.
- [ ] UserInfo 401 không bị nhầm với Resource Server 401 sau login.
- [ ] Có cơ chế xử lý DB/session store errors riêng.
- [ ] Failure handlers trả thông điệp cố định, không lộ provider descriptions.
- [ ] Quan sát cả initiation trước redirect, không chỉ OAuth2 Login callback filter.
- [ ] Có timeout và monitoring Token Endpoint, JWKS, UserInfo.
- [ ] Có metrics labels cardinality thấp.
- [ ] Không log code/state/nonce/verifier/tokens/cookies/Client secrets/full callback URLs.
- [ ] Correlation ID độc lập với `state`.
- [ ] Có negative tests từng stage.
- [ ] Có runbook xác định owner và cách phục hồi.
- [ ] Resource Server API errors không buộc local logout ngoài policy.
- [ ] Kiểm thử đa provider, nhiều instances và refresh rotation.
- [ ] Không tắt bất kỳ validation nào chỉ để làm giảm lỗi đăng nhập.

## 28. Tài liệu tham khảo

1. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization response và token errors.
2. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `invalid_token`, `insufficient_scope` và `WWW-Authenticate`.
3. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect, PKCE, token lifecycle.
4. [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): `code_verifier` và `code_challenge`.
5. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation, UserInfo `sub` matching.
6. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): provider metadata/JWKS/UserInfo.
7. [Spring Security Reference — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): login flow và error handling.
8. [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized clients/managers/refresh.
9. [Spring Security Reference — OAuth2 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): Reactive OAuth2/OIDC Login.
10. [Spring Security API — OAuth2Error](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2Error.html): code/description/URI.
11. [Spring Security API — OAuth2AuthenticationException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticationException.html): authentication failures.
12. [Spring Security API — OAuth2AuthorizationException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthorizationException.html): authorization failures.
13. [Spring Security API — OidcUserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html): OIDC user loading.
14. [Spring Security Reference — Observability](https://docs.spring.io/spring-security/reference/servlet/observability/index.html): telemetry theo Spring Security version.
15. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): logging an toàn, không ghi secrets.

## 29. Tổng kết

**Một OAuth2/OIDC lỗi không nên được nhận diện chỉ bằng HTTP status hoặc exception message.** Hãy xác định **giai đoạn**, **endpoint phát sinh**, **error code**, **grant type**, **ClientRegistration**, **dependency** và **root-cause category**. Authorization decision có thể từ chối consent; callback có thể thất bại vì state/session; Token Endpoint có thể từ chối code hoặc refresh grant; ID Token validation có thể từ chối sai issuer/audience/signature; UserInfo có thể không chấp nhận access token hoặc trả `sub` không khớp.

Trên Spring Security, failure handlers nên đưa người dùng về **một trạng thái lỗi an toàn**, chứ không tự bỏ state, PKCE, nonce, ID Token validation hoặc thử các credentials của provider khác. Quan sát bằng structured logs, metrics và traces được **redact**, đồng thời giữ security tests cho các đường lỗi và runbook để nhóm vận hành sửa đúng nguồn gốc.

Phân loại đúng bốn giai đoạn **authorization → callback → token → UserInfo** (và các substage liên quan) giúp giảm chẩn đoán nhầm, giảm retry nguy hiểm, không làm gián đoạn những phiên đăng nhập còn hợp lệ và giữ ranh giới bảo mật OAuth2/OIDC ngay cả khi hạ tầng hoặc nhà cung cấp gặp sự cố.
