# 28.12. Quy trình chẩn đoán lỗi theo từng bước của luồng OAuth/OIDC

## 1. Tư duy chẩn đoán: xác định bước lỗi đầu tiên

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client**, thông báo “Không đăng nhập được”, “Không lấy được token”, “Không đủ quyền” hoặc “Mất phiên” chỉ là biểu hiện bên ngoài. Nguyên nhân thực sự có thể nằm ở `ClientRegistration`, chuyển hướng browser, authorization request, Token Endpoint, xác minh ID Token, UserInfo, ánh xạ quyền, session store, Resource Server hoặc refresh token.

Đừng bắt đầu bằng việc tắt CSRF hay tăng quyền cho client. Hãy trả lời ba câu hỏi:

1. **Luồng đã đi được tới chặng nào?** Có redirect sang OpenID Provider (OP) chưa? Có callback về RP chưa? Token Endpoint có được gọi không?
2. **Bước đầu tiên thất bại ở đâu?** Tìm HTTP status, OAuth error code hoặc sự kiện của Spring Security có bằng chứng xác nhận.
3. **Lỗi thuộc loại nào?** Sai cấu hình, sai phiên/identity correlation, provider từ chối authorization, lỗi mã hóa/chữ ký, quyền ở Resource Server, hay outage tạm thời?

Ví dụ hai tình huống cùng hiển thị trang `/login?error`:

~~~text
Tình huống A
  Browser -> OP -> callback RP
  RP không tìm thấy authorization request trong session
  => Lỗi state/session/cookie, CHƯA tới Token Endpoint

Tình huống B
  Browser -> OP -> callback RP
  RP gửi code + code_verifier tới Token Endpoint
  OP trả invalid_client
  => Lỗi client authentication/registration
~~~

Sửa client secret không giúp tình huống A; sửa SameSite cookie không giúp tình huống B. Vì thế, chẩn đoán phải bám theo **thứ tự thời gian và ranh giới các thành phần**.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Đọc bản đồ đầy đủ của Authorization Code + OIDC Login, từ `/oauth2/authorization/{registrationId}` đến request API.
- Phân biệt lỗi `state`, PKCE, `redirect_uri`, `invalid_grant`, `invalid_client`, `iss`, `aud`, `nonce`, JWKS và UserInfo.
- Hiểu tại sao login thành công nhưng vẫn có HTTP 401/403, hoặc tại sao browser tiếp tục mất session.
- Xác định lỗi access token, refresh token, Resource Server, Session/Authorized Client Store và logout.
- Thu thập logs, metrics, traces **mà không ghi raw token, code, client secret hoặc cookie**.
- Viết runbook, checklists, integration tests và cách escalation phù hợp Servlet lẫn Reactive.

> **Phạm vi:** Bài tập trung vào Spring Security OAuth2 Client/OIDC Login, đặc biệt Authorization Code Flow có PKCE. Các API/Javadoc phụ thuộc nhánh Spring Security và Spring Boot đang sử dụng. Không chạy kiểm thử với token production thật hoặc yêu cầu user gửi mật khẩu/ID Token vào ticket.

## 2. Bản đồ luồng end-to-end

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant RP as Spring Boot OAuth2/OIDC Client
    participant Store as Session / Authorized Client Store
    participant OP as OpenID Provider
    participant UI as UserInfo Endpoint
    participant API as Resource Server
    Browser->>RP: GET /private
    RP-->>Browser: Redirect tới login
    Browser->>RP: GET /oauth2/authorization/company
    RP->>Store: Lưu authorization request, state, nonce và PKCE verifier
    RP-->>Browser: 302 sang OP Authorization Endpoint
    Browser->>OP: Authorization Request + code_challenge
    OP-->>Browser: Login / consent / MFA
    OP-->>Browser: Redirect callback: code + state
    Browser->>RP: GET /login/oauth2/code/company
    RP->>Store: Load authorization request, đối chiếu state
    RP->>OP: POST Token Endpoint: code, client auth, code_verifier
    OP-->>RP: ID Token, Access Token, optional Refresh Token
    RP->>RP: Validate ID Token signature, iss, aud, exp, nonce
    opt UserInfo cần thiết
        RP->>UI: Bearer Access Token
        UI-->>RP: UserInfo claims
        RP->>RP: UserInfo sub MUST match ID Token sub
    end
    RP->>Store: Lưu Authentication + Authorized Client
    RP-->>Browser: Session cookie + success redirect
    Browser->>RP: GET /private + session cookie
    RP->>Store: Khôi phục SecurityContext
    RP->>API: Gửi đúng Access Token cho API
    API-->>RP: 200, 401, 403 hoặc 5xx
~~~

### 2.1. Bảng chẩn đoán nhanh

| Chặng | Đầu vào/đầu ra mong đợi | Lỗi cần tìm |
| --- | --- | --- |
| 0. Security filter | Protected URL bắt đầu login | Matcher, chain ordering, entry point |
| 1. Registration | Đúng provider/client ID | Issuer, client secret, redirect, scopes |
| 2. Login initiation | 302 sang Authorization Endpoint | Sai registrationId, thiếu state/PKCE |
| 3. OP authorization | User login/consent, redirect code | access_denied, login_required, invalid_scope |
| 4. Callback | Code + state về đúng RP | Session/cookie, state mismatch, proxy |
| 5. Token exchange | Access Token + ID Token | invalid_grant, invalid_client, PKCE, outage |
| 6. ID Token validation | OIDC principal được xác minh | JWT signature/JWKS, iss, aud, nonce, clock |
| 7. UserInfo | Claim sub khớp ID Token | 401/403, thiếu claims, subject mismatch |
| 8. Authorization | OidcUser và authorities | Role mapping, tenant policy, CSRF |
| 9. Persistence | Session và authorized client được lưu | Cookie, Redis/JDBC, multi-node, principal key |
| 10. API call | Bearer token đúng resource | 401 invalid_token, 403 scope/ACL, 503 |
| 11. Refresh | Token mới được lưu đúng | invalid_grant, rotation race, failure handler |
| 12. Logout | RP/OP sessions xử lý đúng | end_session_endpoint, back-channel, revocation |

## 3. Thu thập bằng chứng mà không làm lộ credential

Thông tin thường đủ để xác định nơi thất bại:

~~~text
timestamp_utc=2026-11-16T03:30:00Z
environment=staging
application_version=build-2026-11-16
registration_id=company
provider_alias=company-oidc
stage=token_exchange
error_code=invalid_grant
http_status=400
correlation_id=diag-7e2d
duration_ms=430
~~~

Đây là format minh họa, **không phải log mặc định**.

### 3.1. Không ghi các trường sau

- Access Token, Refresh Token, ID Token, client secret, private keys.
- Authorization code, PKCE `code_verifier`, OAuth2 `state`, OIDC `nonce` nguyên giá trị.
- `Authorization` header, `Cookie`, `Set-Cookie`, CSRF token, Bearer token trong URL.
- Raw Token Endpoint request/response, full UserInfo payload hoặc serialized `OAuth2AuthorizedClient`.
- Session IDs, Back-Channel Logout Token, complete exception traces chứa request parameters.

Những thông tin này có thể tồn tại trong HAR, browser DevTools, reverse proxy logs, APM và debugging tools. Không gửi một file HAR nguyên vẹn lên ticket/chat công khai. Nếu cần phục vụ điều tra, phải lọc/chỉ giữ metadata dưới quyền truy cập phù hợp.

### 3.2. Bằng chứng tối thiểu

| Trường | Ví dụ |
| --- | --- |
| Timestamp UTC và timezone | Nối sự kiện RP/OP/API |
| Environment/region/pod | Phân biệt một node hay toàn hệ thống |
| Build và phiên bản dependencies | Phát hiện thay đổi deployment |
| `registrationId` | Chọn đúng ClientRegistration |
| Chặng thất bại | callback/token/id_token/userinfo/api/refresh |
| HTTP status/error code | Không log token/body |
| Correlation ID | ID nội bộ không chứa OAuth state |
| Provider incident/case ID | Nếu OP có status page hoặc hỗ trợ |
| Browser/session mode | Session container, Spring Session, Redis |
| Độ rộng ảnh hưởng | Một user/tenant/provider hay tất cả |

### 3.3. Những điều không được làm để “sửa nhanh”

~~~text
State mismatch       -> KHÔNG disable state validation
PKCE verifier sai    -> KHÔNG bỏ PKCE
JWT signature fail   -> KHÔNG accept unsigned JWT
Issuer mismatch      -> KHÔNG sửa chuỗi iss trong token
TLS error            -> KHÔNG tắt certificate validation
CSRF 403             -> KHÔNG tắt CSRF toàn hệ thống
API 403              -> KHÔNG tự chuyển sang admin client
OP 503               -> KHÔNG xóa mọi Refresh Token
~~~

## 4. Bước 0 — Khoanh vùng nhanh trước khi sửa cấu hình

Đặt các câu hỏi theo thứ tự:

1. Lỗi xảy ra **trước login**, **sau login**, khi **refresh** hay khi **logout**?
2. Tất cả người dùng hay một người?
3. Tất cả providers hay một `registrationId`?
4. Tất cả instances hay một pod/region?
5. Có thay đổi domain, proxy, cookie, client secret, issuer, JWKS hoặc scopes gần đây?
6. Browser đã tới OP chưa? OP có redirect về callback không?
7. Token Endpoint đã được gọi chưa?
8. Provider có incident/rate limit đang xảy ra không?

| Phạm vi | Ưu tiên điều tra |
| --- | --- |
| Một user | Consent revoked, account/tenant policy, session |
| Một browser | Cookies, SameSite, extensions, stale login tab |
| Một provider | Client registration, OP outage, scopes/secret |
| Một pod | NTP/time skew, container config, session, truststore |
| Toàn hệ thống sau deploy | SecurityFilterChain, proxy/base URL, dependencies |
| Sau scale-out | Shared session/authorization request store, pod affinity |
| Sau secret rotation | Cũ/mới client credentials, pod rollout |
| Sau OP key rotation | JWKS cache/kid, issuer |

Không biến bảng này thành kết luận tự động; đây là cách sắp xếp thứ tự kiểm tra.

## 5. Bước 1 — Kiểm tra ClientRegistration và Discovery

Một cấu hình Servlet OIDC mẫu:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company-oidc:
            issuer-uri: https://id.example.net/realms/company
~~~

Đây là placeholder configuration. `company` là `registrationId`, `company-oidc` là provider config key, `OIDC_CLIENT_ID` là client ID được OP cấp.

### 5.1. Checklist

| Thuộc tính | Kiểm tra |
| --- | --- |
| Registration ID | Trùng login initiation URL/callback |
| Client ID | Đúng OP client và tenant |
| Secret/private key | Đúng version, chưa revoke, không lộ trong logs |
| Client authentication method | OP chấp nhận Basic, private_key_jwt, mTLS... |
| Grant type | `authorization_code` cho OIDC Login |
| Redirect URI | Trùng exact URI ở OP |
| Scopes | Có `openid`; các scopes khác hợp đồng |
| Issuer URI | Khớp exact `iss` của OP |
| Authorization/Token Endpoint | Từ trusted metadata, không đoán |
| JWKS URI | Signing keys của issuer |
| UserInfo URI | Có hay không; đúng provider |

### 5.2. Discovery Metadata

OIDC provider thường có endpoint Discovery tương ứng issuer, ví dụ:

~~~text
https://id.example.net/realms/company/.well-known/openid-configuration
~~~

Payload minh họa:

~~~json
{
  "issuer": "https://id.example.net/realms/company",
  "authorization_endpoint": "https://id.example.net/realms/company/authorize",
  "token_endpoint": "https://id.example.net/realms/company/token",
  "jwks_uri": "https://id.example.net/realms/company/jwks",
  "userinfo_endpoint": "https://id.example.net/realms/company/userinfo"
}
~~~

Nếu Discovery 404/timeout/TLS fail, chẩn đoán issuer path, DNS, proxy, truststore và trạng thái OP. **Không cho request của user chọn một JWKS URL tùy ý**, vì có thể biến việc tải metadata thành SSRF hoặc chấp nhận JWT do attacker ký.

### 5.3. Issuer phải là trust boundary chính xác

~~~text
Configured issuer: https://id.example.net/realms/company
Token issuer:      https://id.example.net/realms/partner

=> Không cùng issuer; token phải bị từ chối.
~~~

Đừng dùng `contains("example.net")` hoặc thay `iss` bằng string replacement.

## 6. Bước 2 — Browser có bắt đầu đúng authorization flow không?

Login initiation mặc định của Spring Security Servlet:

~~~text
GET /oauth2/authorization/company
~~~

Kỳ vọng HTTP 302 sang Authorization Endpoint, với các tham số:

~~~text
response_type=code
client_id=...
redirect_uri=...
scope=openid ...
state=...
code_challenge=...
code_challenge_method=S256
nonce=... (tùy OIDC flow/config)
~~~

### 6.1. Nếu login initiation trả 404

- `company` có tồn tại trong `ClientRegistrationRepository` không?
- Spring Security `oauth2Login()` đã được cấu hình?
- SecurityFilterChain nào match URL?
- Có custom `authorizationEndpoint().baseUri(...)`?
- Reverse proxy strip/prefix có đúng?

### 6.2. Nếu redirect sang login page của RP thay vì OP

Có thể browser đang truy cập protected route và entry point điều hướng đến custom `/login`. Kiểm tra **toàn bộ chuỗi redirects**, không chỉ URL cuối.

### 6.3. Nếu OP từ chối request ngay

Xem safe error code của OP:

| Lỗi | Hướng điều tra |
| --- | --- |
| `invalid_client` | Client ID/registration |
| `invalid_scope` | Scope/consent/permission |
| `invalid_request` | Thiếu/sai parameter |
| `unauthorized_client` | Grant/client policy |
| `redirect_uri_mismatch` (provider-specific) | Public URL và URI đã đăng ký |

Không xin mọi quyền admin để “cho qua” một `invalid_scope`.

## 7. Bước 3 — Redirect URI và reverse proxy

Một topology phổ biến:

~~~text
Browser:
  https://portal.example.net

Reverse Proxy:
  HTTPS public -> http://app:8080 internal

RP authorization request redirect_uri:
  https://portal.example.net/login/oauth2/code/company

Registered redirect URI tại OP:
  https://portal.example.net/login/oauth2/code/company
~~~

Nếu RP gửi `http://app:8080/login/oauth2/code/company`, OP có thể trả `redirect_uri_mismatch`.

### 7.1. Dấu hiệu

- Scheme `http` thay vì `https`.
- Host nội bộ thay public host.
- Path thiếu hoặc dư prefix.
- Port sai.
- Sai trailing slash hoặc URL encoding.
- Callback redirect vòng giữa HTTP và HTTPS.

### 7.2. Forwarded headers

Spring Boot có cấu hình liên quan đến trusted proxy forwarding:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Đây chỉ là **ví dụ cấu hình phụ thuộc hạ tầng**. Proxy phải strip các `Forwarded`/`X-Forwarded-*` headers do browser giả mạo và chỉ cung cấp thông tin đã tin cậy. Đừng tin tùy ý `X-Forwarded-Host` từ Internet, nếu không có thể tạo host spoofing/open redirect.

### 7.3. Exact redirect URI

Các phần sau có thể khiến OP từ chối nếu lệch:

~~~text
scheme | hostname | port | path | trailing slash
~~~

Không mở wildcard redirects rộng chỉ để khắc phục cấu hình. Sửa URI đúng public route và đăng ký ở đúng client/OP.

## 8. Bước 4 — OP authentication và consent có hoàn tất không?

Ở OP, user có thể gặp MFA, conditional access, account lock, tenant policy, consent. Một số lỗi xuất hiện ngay trên trang OP, RP **chưa nhận callback** và không ghi được failure event.

| OP error | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| `access_denied` | User không đồng ý hoặc OP policy chặn | Tôn trọng từ chối |
| `login_required` | Không có SSO session khi silent login | Yêu cầu interactive login |
| `consent_required` | Consent chưa cấp | Sử dụng approved consent flow |
| `interaction_required` | OP cần tương tác với user | Mở tương tác hợp lệ |
| `invalid_scope` | Scope sai/chưa cho phép | Sửa registration/scopes |
| `temporarily_unavailable` | OP tạm lỗi | Degrade và retry phù hợp |

### 8.1. Kiểm tra đường callback thay vì thu raw HAR

Browser DevTools có thể cho biết:

- OP có thực hiện redirect về RP chưa?
- Callback HTTP status là 200/302/400/404?
- Cookie có được gửi hay bị loại vì SameSite/Secure/Domain?
- Reverse proxy có thay path?

Không upload HAR chứa `code`, `state`, cookies hoặc token. Dùng sanitized evidence.

## 9. Bước 5 — Callback, state và authorization request repository

Callback mặc định:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

RP phải tải authorization request tương ứng và xác minh `state` trước khi đổi authorization code. Trong Servlet mặc định, authorization request thường được lưu trong HTTP session.

### 9.1. Callback 404

Kiểm tra callback matcher, SecurityFilterChain, OP registered URI, proxy rewrite, `registrationId`, custom redirection base URI.

### 9.2. State không khớp/không tìm được request

Các nguyên nhân:

- Browser không gửi RP session cookie.
- SameSite/Secure/Domain/Path cookie không phù hợp.
- Session timeout khi user đang MFA/consent.
- Login bắt đầu ở Node A, callback tới Node B không có session.
- Browser có nhiều tabs/attempts, callback cũ bị dùng lại.
- Custom `AuthorizationRequestRepository` hoặc session serialization lỗi.
- User bắt đầu login ở một domain, callback về domain khác.

**Không disable state validation.** `state` bảo vệ correlation/login CSRF/mix-up.

### 9.3. State khác nonce

- `state`: liên kết authorization response với request gốc, giúp chống CSRF/mix-up.
- `nonce`: liên kết ID Token với OIDC authentication request theo flow/policy.
- `code_verifier`: secret dùng ở Token Endpoint để chứng minh sở hữu PKCE.

Không được thay thế ba giá trị cho nhau hoặc log nguyên giá trị.

## 10. Bước 6 — PKCE và Token Endpoint

Authorization Code Flow với PKCE:

~~~text
RP sinh code_verifier có entropy cao
    |
    +-> code_challenge = BASE64URL(SHA256(code_verifier))
    |
    +-> Gửi code_challenge trong authorization request
    |
OP trả code tại callback
    |
RP gửi cùng code_verifier tới Token Endpoint
    |
OP xác minh challenge/verifier và grant
~~~

HTTP POST minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.net
Content-Type: application/x-www-form-urlencoded
Authorization: Basic REDACTED_CLIENT_AUTH

grant_type=authorization_code&
code=REDACTED_CODE&
redirect_uri=https%3A%2F%2Fportal.example.net%2Flogin%2Foauth2%2Fcode%2Fcompany&
code_verifier=REDACTED_VERIFIER
~~~

Authentication method có thể là `client_secret_basic`, `private_key_jwt`, mTLS hoặc cơ chế phù hợp client registration; không mặc định mọi OP đều dùng Basic.

### 10.1. Token Endpoint `invalid_grant`

Các nguyên nhân:

- Code đã hết hạn hoặc đã được dùng.
- Code được cấp cho client khác.
- `redirect_uri` không khớp với authorization request.
- PKCE `code_verifier` không đúng hoặc bị mất.
- OP revoke/invalidate grant.
- Callback bị gửi hai lần.

Phải xác định **grant type**. `invalid_grant` của authorization code exchange khác `invalid_grant` khi refresh token.

### 10.2. Token Endpoint `invalid_client`

Kiểm tra client ID, secret rotation, private key/certificate, client authentication method, tenant/realm, deployment pods có secret cũ, secret manager và clock nếu dùng JWT client assertion.

Không retry vô hạn cùng credentials bị từ chối.

### 10.3. 429, 502/503/504 và timeout

Đây có thể là lỗi tạm thời của OP/network. Dùng bounded retry, `Retry-After`, backoff và jitter. Tuy nhiên, Authorization Code **dùng một lần**: nếu timeout xảy ra sau khi OP đã xử lý code, request retry có thể trả `invalid_grant`. Không gửi lại code vô hạn; có thể cần bắt đầu flow mới.

### 10.4. Nội dung token response

OIDC Authorization Code Login thường cần:

~~~text
access_token = present
token_type = Bearer (nếu dùng Bearer)
id_token = present
expires_in = expiry duration
refresh_token = optional
scope = actual granted scopes (nếu response có)
~~~

Không mặc định OP cấp Refresh Token chỉ vì có `offline_access` trong requested scope.

## 11. Bước 7 — ID Token validation

RP chỉ chấp nhận OIDC Authentication khi ID Token đáp ứng ràng buộc:

| Ràng buộc | Nguyên nhân khi fail |
| --- | --- |
| JWS signature và allowed algorithm | Key/alg/signature sai |
| `kid` từ trusted JWKS | JWKS cache stale hoặc key rotation |
| `iss` exact match | Sai issuer/tenant/realm |
| `aud` chứa client ID | Token dành cho client khác |
| `azp` khi điều kiện yêu cầu | Authorized party mismatch |
| `exp`/`iat` | Hết hạn, clock skew |
| `nonce` nếu dùng | Không khớp authentication request |
| `auth_time`, `at_hash`, `c_hash` khi áp dụng | Điều kiện flow/policy không đạt |

### 11.1. JWT signature fail sau JWKS rotation

~~~text
ID Token header: kid=op-key-new
JWKS cache RP:   op-key-old
~~~

Kiểm tra trusted issuer, JWKS URI, key rotation announcement, key cache refresh, TLS, proxy, NTP và cấu hình khác nhau giữa pods. Không chấp nhận `alg=none`, không bypass signature validation hoặc tự lấy key từ arbitrary `jku`/`x5u` trong JWT header.

### 11.2. Issuer và audience khác nhau

~~~text
registrationId = company
clientId = portal-web
Configured issuer = https://id.example.net/realms/company
ID Token iss = https://id.example.net/realms/partner
ID Token aud = reports-api

=> Không chấp nhận token này làm OIDC login cho portal-web.
~~~

`aud` của ID Token là **client ID**, không phải Spring `registrationId`. Không dùng Access Token của Reports API làm ID Token của Portal.

### 11.3. Clock skew

Một pod chạy đồng hồ lệch lớn có thể xem token `exp` đã hết hạn hoặc `iat` ở tương lai. Kiểm tra NTP, UTC, epoch seconds và chính sách clock skew nhỏ. Không tự gia hạn mọi token hết hạn.

### 11.4. Nonce mismatch

Nếu `nonce` không khớp, điều tra login attempt/session correlation, tab cũ, provider custom flow hoặc token substitution. Không tắt nonce verification.

## 12. Bước 8 — UserInfo Endpoint và sub equality

UserInfo là một endpoint được bảo vệ; RP dùng Access Token để lấy claims bổ sung khi OP hỗ trợ và framework/config cần gọi.

~~~http
GET /userinfo HTTP/1.1
Host: id.example.net
Authorization: Bearer REDACTED_ACCESS_TOKEN
~~~

| Dấu hiệu | Kiểm tra |
| --- | --- |
| 401 | Access Token không hợp lệ/sai issuer/audience |
| 403 | Scope/policy không đủ |
| 5xx/timeout | UserInfo outage |
| Claim `email` vắng | Privacy, consent, dữ liệu không tồn tại |
| `sub` khác ID Token | Token substitution/mix-up; không dùng UserInfo |
| Sai response format | OP contract, ký/mã hóa UserInfo |

### 12.1. Quy tắc bắt buộc của OIDC Core

`sub` trong UserInfo response **MUST khớp chính xác** `sub` của ID Token.

~~~text
ID Token: sub = alice-123
UserInfo: sub = bob-456

=> Không được sử dụng claims của UserInfo response.
~~~

Không cho rằng hai users là một vì email giống nhau.

### 12.2. Claim thiếu không mặc định là lỗi protocol

Requested `openid profile email` không bảo đảm email luôn được cấp. Nếu email là dữ liệu nghiệp vụ bắt buộc, phải có UX/policy yêu cầu xác minh hoặc từ chối onboarding. Không tự đặt `email_verified=true` khi không có claim.

## 13. Bước 9 — Login thành công nhưng authorization fail

OIDC Login success chỉ chứng minh user đã được OP xác thực và RP chấp nhận OIDC protocol. Nó **không cấp quyền admin hoặc scope của API**.

Những điểm cần kiểm tra:

- Internal account mapping dùng **issuer + subject**, không chỉ email hoặc raw `sub`.
- Tenant policy có từ chối user?
- `GrantedAuthoritiesMapper`/`OidcUserService` có map đúng role được phép?
- `@PreAuthorize`, URL matcher, ACL có yêu cầu role khác?
- HTTP POST/PUT/DELETE có thiếu CSRF token?
- 403 đến từ RP hay downstream Resource Server?

### 13.1. Authentication khác authorization

~~~text
Authentication:
  ID Token validated -> user là Alice theo issuer A

Application authorization:
  Alice có được xem báo cáo tenant X không?

Resource Server authorization:
  Access Token có audience/scope cho Reports API không?
~~~

Không tự map arbitrary provider claim `admin` thành `ROLE_ADMIN`. Cần trusted issuer + schema + allowlist policy.

### 13.2. RP HTTP 403 sau POST

Nếu GET vẫn ổn nhưng POST trả 403, kiểm tra CSRF trước khi kết luận thiếu role. Không tắt CSRF toàn app để test production.

## 14. Bước 10 — Session cookie và SecurityContext

Triệu chứng phổ biến: login callback thành công, browser về trang ứng dụng, request kế tiếp lại bị chuyển về login.

~~~text
Browser:
  Cookie: JSESSIONID=<redacted>

RP:
  HttpSession -> SecurityContext -> Authentication
~~~

WebFlux/Spring Session có thể dùng cookie `SESSION` theo config.

### 14.1. Checklist

1. Login response có `Set-Cookie`?
2. Browser có chấp nhận cookie không, hay bị loại vì Secure/SameSite/Domain/Path?
3. Request kế tiếp có gửi đúng cookie?
4. HTTP session/WebSession có tồn tại?
5. SecurityContext có được lưu?
6. Cookie có được rotate sau authentication (bình thường để chống session fixation)?
7. Callback có chạy ở node khác node bắt đầu login?
8. Redis/JDBC session store có được chia sẻ/serialize đúng?
9. Session TTL có hết khi user MFA/consent lâu?
10. Một filter hoặc logout handler có vô tình invalidate session ngay?

### 14.2. SameSite và response mode

Authorization callback dạng GET và `form_post` có thể có cookie behavior khác nhau. Kiểm tra browser cookie exclusion reasons trong DevTools và chính sách `SameSite`/`Secure`, không log cookie nguyên giá trị.

### 14.3. Multi-instance

~~~text
Begin OAuth login -> Pod A giữ authorization request
Callback         -> Pod B không thấy state
Next request     -> Pod C không thấy SecurityContext
~~~

Shared session store hoặc kiến trúc affinity có thể cần thiết. Đừng coi một lần login trên localhost đã chứng minh flow hoạt động trên nhiều pods.

## 15. Bước 11 — Authorized Client Store và principal key

Spring Security Servlet:

~~~text
OAuth2AuthorizedClientService
OAuth2AuthorizedClientRepository
~~~

Reactive:

~~~text
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
~~~

`OAuth2AuthorizedClient` chứa registration, principal, Access Token và Refresh Token nếu được cấp; không đồng nghĩa với `HttpSession` dù đôi khi được lưu trong session.

### 15.1. Khi nào nghi store lỗi?

- Login được nhưng restart làm mất delegated connection.
- Token refresh thành công rồi request sau vẫn dùng token cũ.
- Scheduler không tìm thấy token của user.
- Một instance dùng in-memory store, instance khác không có record.
- Principal khi save dùng `sub` nhưng load dùng email.
- Custom success handler không persist Refresh Token mới.
- Redis/JDBC failure khiến authorization result không lưu được.

### 15.2. Metadata an toàn để kiểm tra

~~~text
registrationId=company
principalKeyAlias=internal-account-123
authorizedClientExists=true
accessTokenExpiryBucket=less_than_5_minutes
refreshTokenPresent=true
storeType=encrypted-jdbc
rowVersion=8
~~~

Không SELECT và in raw token vào logs. Với multi-provider, identity key nên namespace theo issuer/sub và tenant policy, không chỉ email.

## 16. Bước 12 — Resource Server 401/403

Một browser login OIDC thành công tại RP nhưng API vẫn có thể từ chối Bearer Access Token.

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.read"
~~~

| HTTP/API error | Ý nghĩa thường gặp | Cần kiểm tra |
| --- | --- | --- |
| 401 `invalid_token` | Hết hạn, revoke, issuer/aud sai | Access Token và Resource Server validation |
| 403 `insufficient_scope` | Scope chưa đủ | Granted scopes/consent/Resource Server policy |
| 403 business ACL | User/tenant/entity không có quyền | Business authorization, không đổi token |
| 404 | Route/resource không tồn tại hoặc cố ý ẩn | API path/domain/routing |
| 429 | Rate limit | `Retry-After`/backoff |
| 503 | API outage | Không refresh Access Token vô hạn |

### 16.1. Audience là ranh giới của API

Access Token hợp lệ ở UserInfo không tự hợp lệ cho Reports API. Một ID Token dành cho RP client cũng không dùng làm API Bearer Token. Xác định đúng registration, requested/granted scopes, token audience và endpoint nhận token.

### 16.2. WebClient và nguy cơ gửi token nhầm host

Kiểm tra `ServletOAuth2AuthorizedClientExchangeFilterFunction` hoặc `ServerOAuth2AuthorizedClientExchangeFilterFunction`:

- Chọn đúng `clientRegistrationId` hoặc authorized client theo request?
- Có gắn default OAuth2 Client vào WebClient gọi arbitrary URLs?
- Người dùng/tenant có quyền dùng token đó?
- Absolute URI/redirect có làm token đi sang host khác?
- Failure handler có xử lý Bearer errors phù hợp không?

Không nhận user-supplied URL rồi tự gắn admin Bearer Token: đây là rủi ro SSRF/token exfiltration.

## 17. Bước 13 — Refresh Token và invalid_grant

Khi Access Token hết hạn, manager có thể refresh nếu có Refresh Token và provider hỗ trợ. `invalid_grant` lúc này không nhất thiết giống `invalid_grant` khi đổi authorization code.

### 17.1. Những nguyên nhân chính

- Refresh Token hết hạn hoặc user revoke consent.
- Provider rotate Refresh Token và một request dùng lại token cũ.
- Hai concurrent requests cùng load Refresh Token cũ.
- OP phát hiện replay, revoke token family.
- Token lưu ở sai principal/registration.
- Background job dùng store không đồng bộ.

### 17.2. Race minh họa

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant Store as Authorized Client Store
    participant OP as Token Endpoint
    A->>Store: Load R1
    B->>Store: Load R1
    A->>OP: Refresh R1
    OP-->>A: Access A2, Refresh R2
    A->>Store: Save R2, version 2
    B->>OP: Refresh R1
    OP-->>B: invalid_grant
    Note over B,Store: B không được xóa nhầm bản R2 của A
~~~

Giải pháp có thể là single-flight refresh theo connection key, optimistic locking hoặc conditional delete/update, tùy persistence. Không retry R1 vô hạn.

### 17.3. Nếu Token Endpoint trả 503

Đó có thể là outage; **không xóa mọi Refresh Token**. Dùng bounded retry, exponential backoff, jitter, circuit breaker; giữ trạng thái kết nối phù hợp.

### 17.4. Success/failure handlers

`DefaultOAuth2AuthorizedClientManager` thường dùng trong Servlet request; `AuthorizedClientServiceOAuth2AuthorizedClientManager` hữu ích trong background/non-request context. Chúng sử dụng success/failure handlers để lưu/xóa authorized clients theo kết quả.

Khi custom handlers, kiểm tra không vô tình bỏ việc save token mới, không xóa bản ghi mới do một request khác vừa refresh, không retry lỗi permanent như `invalid_grant` vô hạn.

## 18. Bước 14 — Logout và session còn lại

Các trạng thái khác nhau:

~~~text
RP local HttpSession
OP SSO session
OAuth2AuthorizedClient trong DB/Redis
Access Token tại Resource Server
Refresh Token tại Authorization Server
~~~

### 18.1. Local Logout

Thông thường chỉ invalidate local RP session. OP SSO session có thể vẫn hoạt động, nên user login lại có thể không cần nhập mật khẩu.

### 18.2. RP-Initiated Logout

Khi OP hỗ trợ, Spring Security có `OidcClientInitiatedLogoutSuccessHandler` (Servlet) hoặc `OidcClientInitiatedServerLogoutSuccessHandler` (Reactive). Kiểm tra `end_session_endpoint`, `id_token_hint` và `post_logout_redirect_uri` đã đăng ký. Không tự đoán URL `issuer + "/logout"`.

### 18.3. Back-Channel Logout

Nếu OP hỗ trợ, nó gửi signed `logout_token` server-to-server tới:

~~~text
POST /logout/connect/back-channel/{registrationId}
~~~

RP cần xác minh Logout Token và liên kết OP `sid`/`sub` với local session qua session registry. OP `sid` không phải RP `JSESSIONID`. Kiểm tra cookie name, registry sharing khi multi-node và OP endpoint registration.

### 18.4. Token revocation là bước riêng

`OAuth2AuthorizedClientService.removeAuthorizedClient(...)` chỉ xóa local entry. Thu hồi token ở Authorization Server theo RFC 7009 hoặc policy provider là cơ chế khác. Một JWT Access Token có thể vẫn được API chấp nhận đến hết hạn nếu không có introspection/denylist/revocation strategy.

## 19. Decision tree chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["Báo lỗi OAuth/OIDC"] --> B{"Trước hay sau login?"}
    B -->|Trước| C{"Có redirect sang OP?"}
    C -->|Không| D["Registration, SecurityFilterChain, login URL"]
    C -->|Có| E{"OP callback RP?"}
    E -->|Không| F["redirect_uri, scopes, user/OP policy"]
    E -->|Có| G{"State match và session còn?"}
    G -->|Không| H["Cookie, SameSite, proxy, cluster"]
    G -->|Có| I{"Token exchange thành công?"}
    I -->|Không| J["client auth, PKCE, invalid_grant, outage"]
    I -->|Có| K{"ID Token valid?"}
    K -->|Không| L["JWKS, iss, aud, nonce, exp"]
    K -->|Có| M{"UserInfo/authorities valid?"}
    M -->|Không| N["sub equality, missing claims, role policy"]
    M -->|Có| O["Session và authorized client store"]
    B -->|Sau| P{"API, refresh hay logout?"}
    P -->|API| Q["invalid_token / insufficient_scope / API outage"]
    P -->|Refresh| R["revoked, rotation race, OP outage"]
    P -->|Logout| S["RP session vs OP session vs revocation"]
~~~

Decision tree chỉ cung cấp **thứ tự tìm chứng cứ**. Mỗi nhánh vẫn cần logs/correlation với OP, RP và Resource Server để khẳng định nguyên nhân.

## 20. Logging Spring Security: bật có thời hạn, không lộ token

Ví dụ cấu hình tạm ở staging/canary:

~~~yaml
logging:
  level:
    org.springframework.security: INFO
    org.springframework.security.oauth2: DEBUG
    org.springframework.web.client: INFO
    reactor.netty.http.client: INFO
~~~

Không coi đây là cấu hình DEBUG production lâu dài. Khi tăng log level:

1. Chọn một instance và thời gian ngắn.
2. Kiểm tra logger/appender/HTTP wiretap có che token, code, state, verifier, cookie không.
3. Hạn chế quyền xem logs và thời hạn lưu.
4. Không log body của Token Endpoint hay Authorization header.
5. Khôi phục baseline khi đủ chứng cứ.

### 20.1. Spring Security debug mode

`spring.security.debug=true` có thể giúp hiểu filter chain nhưng cũng làm lộ nhiều chi tiết request. Không bật tràn lan production khi chưa xác minh redaction, privacy và retention.

### 20.2. Safe structured event

~~~json
{
  "event": "oauth2_login_failed",
  "registrationId": "company",
  "stage": "callback",
  "reason": "authorization_request_not_found",
  "correlationId": "diag-7e2d",
  "deployment": "canary-04"
}
~~~

Không đưa `exception.getMessage()` hoặc raw request query string vào event nếu chúng có thể chứa code/state/token.

## 21. Servlet: AuthenticationFailureHandler minh họa

Spring Security cho phép gắn một `AuthenticationFailureHandler` riêng trong OAuth2 Login, ghi **loại lỗi** mà không ghi credential.

~~~java
package com.example.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class OAuth2DiagnosticConfig {

    private static final Logger LOG =
        LoggerFactory.getLogger(OAuth2DiagnosticConfig.class);

    @Bean
    AuthenticationFailureHandler diagnosticFailureHandler() {
        SimpleUrlAuthenticationFailureHandler fallback =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, exception) -> {
            LOG.warn("oauth2_login_failed reason={}",
                safeCategory(exception));

            // Không log exception.getMessage(), raw JWT,
            // request URI/query, Authorization header hoặc cookie.
            fallback.onAuthenticationFailure(request, response, exception);
        };
    }

    private static String safeCategory(
            AuthenticationException exception) {

        if (exception instanceof OAuth2AuthenticationException oauth) {
            String code = oauth.getError().getErrorCode();
            return switch (code) {
                case "invalid_grant", "invalid_client",
                     "invalid_request", "invalid_scope",
                     "access_denied", "temporarily_unavailable" -> code;
                default -> "oauth2_authentication_error";
            };
        }
        if (exception instanceof AuthenticationServiceException) {
            return "authentication_service_error";
        }
        return "authentication_error";
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler diagnosticFailureHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .failureHandler(diagnosticFailureHandler))
            .build();
    }
}
~~~

`/login` phải được ứng dụng triển khai nếu dùng custom login page. Ví dụ trên là **một SecurityFilterChain hoàn chỉnh để minh họa**, không copy song song với chain khác match toàn bộ requests. Ngoài handler này, các HTTP libraries, proxy, APM vẫn có thể ghi credentials; phải rà soát toàn bộ pipeline.

### 21.1. Đừng bắt mọi exception làm `invalid_grant`

Một lỗi storage/network có thể không phải `OAuth2AuthenticationException`. Giữ riêng danh mục `authentication_service_error` hoặc `provider_unavailable` thay vì gán nhầm user bị thu hồi quyền.

## 22. Ghi nhận metadata về người dùng đã authenticated

Đối với ứng dụng nội bộ hoặc staging, một endpoint diagnostic được giới hạn quyền có thể cho biết `registrationId` và tập authority đã lọc.

~~~java
package com.example.web;

import java.util.List;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticAuthController {

    @GetMapping("/internal/diagnostic/auth")
    public DiagnosticAuth view(OAuth2AuthenticationToken authentication) {
        String registrationId =
            authentication.getAuthorizedClientRegistrationId();

        List<String> safeAuthorities =
            authentication.getAuthorities().stream()
                .map(a -> a.getAuthority())
                .filter(a -> a.equals("OIDC_USER")
                    || a.equals("ROLE_REPORT_VIEWER"))
                .toList();

        return new DiagnosticAuth(registrationId, safeAuthorities);
    }

    record DiagnosticAuth(
        String registrationId, List<String> authorities) {}
}
~~~

Chỉ triển khai với **internal admin authorization**, environment gating, audit và privacy policy. Không trả `OidcUser.getClaims()`, ID Token, Access Token hoặc session cookie. Ví dụ giả định principal là OAuth2 Login; nếu ứng dụng còn form login/API key, phải xử lý Authentication type khác.

## 23. Reactive/WebFlux: khác Servlet ở context và storage

| Điểm | Servlet | Reactive |
| --- | --- | --- |
| DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Session | `HttpSession` | `WebSession` |
| Authorized client store | `OAuth2AuthorizedClientRepository` / service | `ServerOAuth2AuthorizedClientRepository` / reactive service |
| WebClient token filter | `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| Context | Servlet request/security context | Reactor Context/SecurityContext |

Một cấu hình Reactive cơ bản:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là cấu hình **Reactive thay thế Servlet**, không dùng đồng thời hai DSL nếu không có kiến trúc hybrid rõ.

### 23.1. Authentication mất khi chuyển scheduler

Các lỗi có thể phát sinh khi code:

- Tự gọi `subscribe()` làm pipeline tách khỏi request.
- Dùng `block()` trên Reactor event loop.
- Tự tạo threads và nghĩ ThreadLocal SecurityContext luôn được truyền.
- Không compose `Mono` save/remove authorized client.
- Chạy background job bằng manager cần `ServerWebExchange` mà thực tế không có.

Chẩn đoán Reactor Context propagation, reactive transaction lifecycle và principal được truyền rõ. Với background jobs có thể dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.

## 24. Observability: metrics, logs và tracing

### 24.1. Metrics gợi ý

| Metric | Tags an toàn |
| --- | --- |
| `oauth2_login_started_total` | registration, environment |
| `oauth2_login_failed_total` | stage, safe error category |
| `oauth2_callback_failed_total` | registration, region |
| `oauth2_token_exchange_duration` | provider, grant type |
| `oauth2_id_token_validation_failures` | issuer alias, reason class |
| `oauth2_userinfo_failed_total` | provider, status class |
| `oauth2_session_missing_total` | region, node class |
| `oauth2_api_invalid_token_total` | API alias |
| `oauth2_api_insufficient_scope_total` | API alias |
| `oauth2_refresh_invalid_grant_total` | provider |
| `oauth2_provider_5xx_total` | provider, endpoint class |

Không dùng raw subject, email, token, session ID, OAuth state hoặc `jti` làm metric labels vì privacy và high-cardinality.

### 24.2. Tracing qua browser redirect

Browser điều hướng qua OP rồi quay về RP, nên không mặc định trace headers giữ nguyên. Một internal login attempt ID có thể giúp correlation nếu lưu theo server-side request/session và tuân thủ bảo mật; đừng đưa arbitrary trace context vào OAuth protocol parameters làm hỏng state/nonce behavior.

### 24.3. Health check

Liveness/readiness không nên chạy Authorization Code Flow hoặc refresh user production token liên tục. Synthetic login tests nên dùng provider sandbox/test client/test user riêng, cadence và quyền đã phê duyệt.

## 25. Retry, rate limit và circuit breaker

| Error | Retry policy |
| --- | --- |
| Network timeout | Bounded, phân biệt outcome unknown |
| HTTP 429 | Tôn trọng `Retry-After`, backoff/jitter |
| HTTP 502/503/504 | Bounded retry/circuit breaker |
| `invalid_grant` | Không retry cùng code/refresh token vô hạn |
| `invalid_client` | Sửa credential/registration, không spam Token Endpoint |
| `invalid_scope` | Sửa requested scope và consent |
| API 401 `invalid_token` | Xử lý stale token theo policy, kiểm tra handler |
| API 403 `insufficient_scope` | Không tự nâng quyền |
| JWKS unavailable | Retry/cache theo trusted policy; không tắt signature |

Backoff:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
delayWithJitter = random(0, delay)
~~~

Circuit breaker và bulkhead nên phân chia theo provider/endpoint cần thiết, tránh Provider A outage khiến Provider B cũng bị chặn. Với POST có side effects hoặc authorization code một lần, không tự retry mù quáng sau timeout.

## 26. Tình huống A — redirect_uri_mismatch sau thay proxy

**Triệu chứng:** browser tới OP nhưng OP từ chối ngay.

**Bước lỗi:** Authorization Endpoint validation, trước callback.

**Điều tra:** so sánh scheme, host, port, path trong redirect URI mà RP gửi với URI OP đăng ký; kiểm tra forwarding/trust của proxy.

**Cách xử lý:** đồng bộ public URL, trusted forwarded headers và exact redirect registration. Không mở redirect wildcard tùy tiện.

## 27. Tình huống B — Mất state sau MFA dài

**Triệu chứng:** OP đăng nhập thành công, callback RP báo authorization request not found.

**Bước lỗi:** callback/session correlation.

**Điều tra:** session timeout, browser cookie inclusion reasons, SameSite, domain/path, two-tab flow, load balancer/pod.

**Cách xử lý:** sửa cookie/session store/TTL theo policy. Không disable state validation.

## 28. Tình huống C — invalid_client sau rotate client secret

**Triệu chứng:** Token Endpoint trả 401/400 với `invalid_client` cho mọi users của một registration.

**Bước lỗi:** client authentication tại Token Endpoint.

**Điều tra:** OP secret version, method (Basic/private_key_jwt/mTLS), pod rollout, secret manager, client ID/tenant.

**Cách xử lý:** rotate và rollout đúng, không log secret và không retry vô hạn.

## 29. Tình huống D — Code exchange invalid_grant khi reload callback

**Triệu chứng:** login một lần được, nhấn refresh ở callback gây lỗi.

**Bước lỗi:** Token Endpoint.

**Điều tra:** code đã dùng một lần, callback bị proxy/browser gửi lặp, redirect_uri/PKCE.

**Cách xử lý:** không dùng lại authorization code; tạo authorization request mới khi cần.

## 30. Tình huống E — ID Token có issuer/audience sai

**Triệu chứng:** Token Endpoint trả 200, nhưng Spring Security không tạo session.

**Bước lỗi:** ID Token validation.

**Điều tra:** `issuer-uri`, `client-id`, realm/tenant, signing keys/JWKS, `azp` nếu áp dụng.

**Cách xử lý:** sửa registration hoặc OP configuration; không sửa claims trong JWT.

## 31. Tình huống F — JWKS mới chưa được RP tải

**Triệu chứng:** chỉ ID Tokens ký bằng `kid` mới bị reject.

**Bước lỗi:** JWT signature verification.

**Điều tra:** JWKS fetch, trusted issuer, cache refresh, OP key rotation, proxy/TLS.

**Cách xử lý:** cập nhật key cache theo trusted provider policy; tuyệt đối không bỏ signature verification.

## 32. Tình huống G — UserInfo sub mismatch

**Triệu chứng:** UserInfo 200 nhưng claims bị từ chối.

**Bước lỗi:** UserInfo identity binding.

**Điều tra:** Access Token từ principal/issuer khác, token substitution, routing nhầm endpoint.

**Cách xử lý:** không dùng UserInfo khi `sub` khác ID Token; sửa luồng token/context.

## 33. Tình huống H — Login được, API 403

**Triệu chứng:** browser có OIDC session, nhưng Reports API từ chối.

**Bước lỗi:** Resource Server authorization, không nhất thiết OIDC Login.

**Điều tra:** Bearer `WWW-Authenticate`, token audience/scope, entity ACL, tenant policy.

**Cách xử lý:** lấy đúng delegated API scope qua approved consent, không tự dùng admin Client Credentials để vượt quyền.

## 34. Tình huống I — Scale-out khiến user bị redirect login lại

**Triệu chứng:** login trên Pod A, request Pod B không có SecurityContext.

**Bước lỗi:** Session/Authorized Client persistence.

**Điều tra:** Redis/JDBC session, cookie routing, serialization, TTL, in-memory authorized clients.

**Cách xử lý:** thiết kế shared state/affinity có kiểm thử multi-node, không chỉ thử localhost.

## 35. Tình huống J — Refresh Token rotation race

**Triệu chứng:** Request A refresh thành công, Request B `invalid_grant` và xóa token mới.

**Bước lỗi:** Refresh concurrency/persistence.

**Điều tra:** two requests load same Refresh Token, success/failure handlers, row version.

**Cách xử lý:** single-flight hoặc CAS/optimistic locking, không xóa stale record của request khác.

## 36. Tình huống K — OP outage một phần

**Triệu chứng:** Token Endpoint 503, Resource Server vẫn 200 với Access Token cũ.

**Bước lỗi:** provider availability, không nhất thiết grant revoked.

**Điều tra:** endpoint/region/provider status, response class, Retry-After và rate limit.

**Cách xử lý:** giữ valid credential, backoff/circuit breaker và degraded UX, không xóa mọi Refresh Token.

## 37. Tình huống L — Logout rồi login lại ngay

**Triệu chứng:** user không được yêu cầu nhập mật khẩu lần nữa.

**Bước lỗi hay hiểu lầm:** RP local session khác OP SSO session.

**Điều tra:** có RP-Initiated Logout không, OP công bố `end_session_endpoint` không, post-logout URI hợp lệ không.

**Cách xử lý:** UX/policy logout đúng khả năng OP; không coi local logout đồng nghĩa revoke Access Token.

## 38. Test matrix theo từng chặng

| Chặng | Positive test | Negative test |
| --- | --- | --- |
| Registration | Valid issuer/client | Unknown registrationId |
| Authorization request | Redirect có state/PKCE | Invalid scope/redirect |
| OP consent | User đồng ý | access_denied |
| Callback | Code + state đúng | Missing/wrong state, session expired |
| Token Endpoint | Code đổi token | invalid_client, invalid_grant, 503 |
| ID Token | Signature/iss/aud/exp đúng | Wrong issuer, audience, nonce, bad signature |
| UserInfo | sub match | sub mismatch, missing optional claim |
| Authority mapping | Trusted role mapped | Unknown/foreign admin claim |
| Session | Cookie + SecurityContext restored | Wrong SameSite, different pod |
| Authorized Client | Save/load/refresh persisted | Wrong principal, stale row |
| Resource Server | 200 đúng audience/scope | 401 invalid_token, 403 insufficient_scope |
| Refresh | Token rotation và atomic save | Race, revoked token, provider down |
| Logout | Local/OP/backchannel đúng | Wrong sid/sub, invalid logout token |

### 38.1. Mock authentication không phải protocol integration test

`@WithMockUser`, `oauth2Login()` hoặc `oidcLogin()` trong Spring Security Test rất hữu ích khi kiểm tra controllers/authorities, nhưng có thể chỉ dựng fake Authentication, không tự thực hiện authorization code exchange, PKCE, ID Token verification và UserInfo requests.

Khi cần xác minh protocol, dùng **mock/test OP** có Token Endpoint, Discovery/JWKS, signed test ID Tokens, UserInfo; kết hợp browser/HTTP integration tests.

### 38.2. Không test bằng production user credentials

Không dump raw tokens vào CI artifacts. Dùng test registrations, test users và controlled fixtures; xóa cookies/token traces theo retention.

## 39. Checklist xử lý incident theo thứ tự

1. Xác định registration ID, environment, version, UTC time và phạm vi ảnh hưởng.
2. Phân loại login/callback/token/id_token/userinfo/session/api/refresh/logout.
3. Thu thập HTTP status, OAuth error code, correlation ID đã lọc.
4. Kiểm tra trusted issuer/ClientRegistration và OP metadata.
5. Xác nhận Authorization Endpoint redirect và registered `redirect_uri`.
6. Xác nhận OP login/consent xong và callback đến đúng path.
7. Kiểm tra `state`/session/cookie và PKCE verifier correlation.
8. Nếu token exchange fail: phân biệt `invalid_grant`, `invalid_client` và 429/5xx.
9. Nếu ID Token fail: kiểm tra signature/JWKS, iss/aud/nonce/expiry/clock.
10. Nếu UserInfo fail: kiểm tra token/endpoint và `sub` exact match.
11. Nếu 403 sau login: phân biệt RP CSRF, role/tenant policy và Resource Server scope.
12. Nếu mất session: kiểm tra Cookie/SecurityContext/Redis/multi-instance.
13. Nếu API 401/403: xem `WWW-Authenticate`/audience/granted scope và API logs.
14. Nếu refresh fail: xem revocation, rotation race, authorized client persistence.
15. Nếu logout fail: phân biệt RP session, OP SSO và token revocation.
16. Kết luận bằng bằng chứng, thêm regression test, khôi phục logging level và ghi hậu kiểm.

## 40. Tài liệu tham khảo

- Spring Security — OAuth2 Login Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — OAuth2 Client Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2 Login Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — OAuth2 Client Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — OIDC Logout Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — OIDC Logout Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security — OAuth2 Login MockMvc Tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OpenID Connect RP-Initiated Logout: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Back-Channel Logout: https://openid.net/specs/openid-connect-backchannel-1_0.html
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 7636 — Proof Key for Code Exchange (PKCE): https://www.rfc-editor.org/rfc/rfc7636
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 8725 — JSON Web Token BCP: https://www.rfc-editor.org/rfc/rfc8725
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html

## 41. Tổng kết

~~~text
Chẩn đoán OAuth/OIDC theo thứ tự:

ClientRegistration và issuer metadata
  -> Authorization request (state/PKCE/redirect_uri)
  -> OP login/consent
  -> Callback correlation
  -> Token Endpoint exchange
  -> ID Token signature/iss/aud/nonce/exp
  -> UserInfo sub equality
  -> Authentication + GrantedAuthorities
  -> Session + Authorized Client persistence
  -> Resource Server 401/403 và refresh
  -> Logout local/OP/revocation

Tại mỗi chặng:
  1. Thu thập metadata đã redacted.
  2. Xác định lỗi đầu tiên có bằng chứng.
  3. Phân biệt config/security/policy/transient outage.
  4. Sửa đúng ranh giới và chạy regression tests.
  5. Không disable các kiểm tra bảo mật.
~~~

**Những nguyên tắc quan trọng nhất:**

1. **Bắt đầu từ chặng thất bại đầu tiên.** State mismatch trước Token Endpoint không thể sửa bằng client secret; Resource Server 403 sau login không có nghĩa OIDC Login lỗi.
2. **Không nhầm token và server.** ID Token phục vụ RP authentication, Access Token dành cho UserInfo/API, Refresh Token dành cho Token Endpoint; mỗi loại có issuer/audience/lifecycle riêng.
3. **Giữ nguyên security invariants.** Không tắt state, PKCE, nonce, issuer/audience, JWT signature, TLS, CSRF chỉ để lấy HTTP 200.
4. **Chỉ log metadata an toàn.** Error category, stage, registration alias, UTC time và correlation ID thường đủ để điều tra mà không lộ token/code/cookie.
5. **Phân biệt permanent và transient errors.** `invalid_grant`, `invalid_client`, `invalid_token`, `insufficient_scope` và HTTP 503 cần quyết định khác nhau.
6. **Xác nhận bằng integration tests.** Mock user test không thay thế browser callback, OP Token Endpoint, JWKS, UserInfo và session persistence trong topology nhiều instances.

Thói quen luôn hỏi **“Luồng đã đi đến đâu, bước nào thất bại trước tiên, bằng chứng nào xác nhận?”** giúp đội ngũ chẩn đoán Spring Security OAuth2/OIDC Client chính xác, nhanh và an toàn hơn, đồng thời tránh khắc phục sai phạm vi.
