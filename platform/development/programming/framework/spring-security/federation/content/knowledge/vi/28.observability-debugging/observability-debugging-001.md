# Theo dõi chuỗi chuyển hướng và xác định bước SSO thất bại

> **Chủ đề:** Spring Security – federation. **Nhóm:** Quan sát và gỡ lỗi. Bài Knowledge độc lập hướng dẫn tái dựng các bước Single Sign-On (SSO), tìm **bước thành công cuối cùng** và **bước thất bại đầu tiên** khi ứng dụng Java 17+/Spring Security Servlet tích hợp OpenID Connect (OIDC)/OAuth2 Login, SAML 2.0, CAS, Kerberos/SPNEGO hoặc xác thực qua reverse proxy. Mục tiêu là quan sát chính xác nhưng **không ghi lộ authorization code, SAMLResponse, service ticket, session cookie, private keys hoặc token**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt request được browser thực hiện (**front-channel**) với request Spring thực hiện trực tiếp tới IdP/token endpoint/CAS (**back-channel**).
2. Hiểu `302`/`303`/`307`, HTML `200` auto-submit, `401` Negotiate challenge và `403` authorization denial trong đúng ngữ cảnh.
3. Vẽ chuỗi OIDC Authorization Code: `/oauth2/authorization/{registrationId}` → IdP authorize → `/login/oauth2/code/{registrationId}` → token/JWKS/UserInfo → session → business resource.
4. Vẽ chuỗi SAML: `/saml2/authenticate/{registrationId}` → AuthnRequest → IdP login → browser **POST** `SAMLResponse` tới `/login/saml2/sso/{registrationId}` → OpenSAML validation.
5. Nhận diện CAS `service`/`ticket`/`serviceValidate` và Kerberos `401 WWW-Authenticate: Negotiate`/`Authorization: Negotiate`; không ép hai giao thức này vào khuôn OIDC.
6. Tìm lỗi do mất `state`, `RelayState`, `InResponseTo`, PKCE `code_verifier`, browser cookie `SameSite`, Proxy `Forwarded`, session store, token endpoint, signing keys hay authorization.
7. Thu thập DevTools Network Preserve log/HAR có kiểm soát, trace IDs, sanitized logs từ proxy/Spring/IdP và phân loại lỗi theo owner.
8. Instrument Spring Boot filter an toàn để theo dõi **route category, method, status, thời gian** mà không truy cập raw query/form/header credentials.
9. Chạy chương trình Java 17 độc lập để phân loại chuỗi events giả lập thành `COMPLETE`, `CORRELATION_GAP`, `REDIRECT_LOOP`, lỗi callback/back-channel hoặc challenge bình thường.
10. Xây test matrix happy path/negative cases và checklist nghiệm thu không làm mất bảo vệ state/signature/CSRF/issuer/audience.

**Nguyên tắc:** Một HTTP `302` chỉ nói browser được yêu cầu chuyển URL. Nó **không tự là SSO thành công hoặc thất bại**. Một callback trả 302 có thể đang redirect về trang đích sau authentication thành công, hoặc về `/login?error` sau authentication thất bại. Để chẩn đoán cần chứng cứ về request, component trả lời, correlation, provider validation và session.

## 2. Mô hình quan sát bốn ranh giới

```text
                  BROWSER
                   |   ^
          (1) navigation / cookies /
              redirects / HTML form POST
                   |   |
                   v   |
          [EDGE / CDN / WAF / PROXY]
              TLS, Host, routing
                   |   ^
                   v   |
          [SPRING SECURITY APP]
              FilterChainProxy,
              AuthnEntryPoint,
              callback filters,
              SecurityContext, session
                   |   ^
      server HTTP  |   |  server responses
                   v   |
          [OP / IDP / CAS / DIRECTORY]
          token, JWKS, UserInfo,
          CAS ticket validation
                   |
          [BUSINESS AUTHORIZATION]
            user + role + tenant + resource
```

Sơ đồ tách ra:

- **Browser:** nhìn HTTP redirection, trang đăng nhập IdP, consent/MFA, form auto-submit SAML và cookie sent/blocked. DevTools chỉ ghi requests do browser thực hiện.
- **Proxy:** thấy status do chính nó trả và status upstream từ Spring, latency, TLS, virtual host/path rewriting; có thể trả 413, 502, 504 trước khi Spring nhận request.
- **Spring:** chọn SecurityFilterChain, tạo authentication request, nhận callback, xác minh correlation/claims/cert, gọi back-channel, lưu SecurityContext vào HttpSession/Spring Session rồi chuyển hướng.
- **IdP/OP/CAS/KDC:** chịu trách nhiệm credential login, MFA, signed assertions, token issuance hoặc ticket validation. Cần logs riêng của hệ đó; Spring không tự thấy được mọi IdP policy failure.
- **Ứng dụng nghiệp vụ:** một login PASS chưa có nghĩa được phép xem/pay/admin tài nguyên. HTTP `403` sau khi session hợp lệ có thể là **authorization đúng**.

### 2.1. Các phép đo cần thiết cho mỗi request

```text
UTC timestamp
origin/category (browser, edge, app, IdP)
HTTP method and status
sanitized route category
redirect target origin/path (NO query values)
Set-Cookie/Cookie presence & attributes (NO cookie values)
application requestId / traceId where available
SSO protocol & configured registrationId
authentication stage (START, IDP, CALLBACK, TOKEN, SESSION, RESOURCE)
signed/correlated/denied decision category
instance/pod and session lookup result if instrumented
upstream status and duration at edge
```

Không suy một event `sessionLookup=MISS` nếu chưa đo ở session repository. Không đặt NameID/username/email, user-supplied Host, full redirect URL, raw `state` hoặc `ticket` vào Prometheus labels.

## 3. Đọc mã HTTP đúng ngữ cảnh

| Status | Trường hợp hợp lệ | Dấu hiệu đáng điều tra |
| --- | --- | --- |
| `200 OK` | Trang login IdP; HTML form tự POST SAML; business page sau login | 200 nhưng là HTML login thay vì resource đã yêu cầu |
| `302 Found` | SP tới IdP, IdP về callback, SP về saved request | Lặp 302 liên tục không tạo session |
| `303 See Other` | Chuyển sang GET sau POST | Redirect không thuộc allowlist |
| `307/308` | Bảo toàn method/body khi redirect | SAML POST có thể bị gửi nguyên body sang host/route sai; cần tránh |
| `400` | Không phải SSO success | Form/callback/state malformed, SAML response invalid format |
| `401` | SPNEGO `WWW-Authenticate: Negotiate` challenge ban đầu | API Bearer invalid, SPNEGO không tiếp tục, CAS callback error |
| `403` | User authenticated nhưng không có quyền | SAML ACS POST bị CsrfFilter/WAF chặn; tenant/role thiếu |
| `404` | Route không tồn tại | Callback/ACS sai route hoặc filter chain |
| `413` | Không phải login thành công | SAMLResponse form body/attributes quá lớn |
| `429` | Hệ thống rate limit | Login storm/loop, IdP throttling |
| `500` | Lỗi app | Provider/validator exception, request mapping bug |
| `502` | Gateway không kết nối/đọc upstream | TLS, DNS, upstream reset; request có thể chưa vào Spring |
| `503/504` | Downstream down/timeout | Token/JWKS/IdP/Redis service unavailable |

Ví dụ `302 → 200 → 302 → 302 → 200` là một chuỗi SSO **có thể hợp lệ**; không quy lỗi chỉ vì có nhiều `302`. Đọc kết quả của bước **sau** redirect. Một `302` có `Location: /login?error` và authentication failure event là bằng chứng mạnh hơn một mã HTTP riêng.

### 3.1. Điều đặc biệt của `Location`

```text
HTTP/1.1 302 Found
Location: https://idp.example.org/authorize?
    client_id=portal&
    redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcorp&
    response_type=code&
    state=REDACTED&
    nonce=REDACTED&
    code_challenge=REDACTED
```

Trong báo cáo chỉ giữ: status 302, host `idp.example.org`, path `/authorize`, **tên** query keys và stage `OIDC_AUTHORIZATION_REDIRECT`. Raw `code`/`state`/`ticket`/`RelayState`/`SAMLResponse` không được log. Không đưa token vào external redirect tracing service.

## 4. Playbook chung: theo dõi một lần thử đến khi kết thúc

1. Xác định user **test**/môi trường, hostname public, protocol, expected IdP/registrationId, tenant, UTC timestamp và browser version. Không tái hiện bằng credentials production trên môi trường debug chưa được duyệt.
2. Mở DevTools → Network **trước** khi login, bật **Preserve log**, lọc `All` khi có SAML POST. Chỉ dùng một tab để khởi tạo flow đầu tiên; sau đó mới test concurrent tabs.
3. Ghi **request protected resource đầu**: method/status, redirect location origin/path, có đến Spring hay bị edge chặn?
4. Xác định request SP initiation: `/oauth2/authorization/corp` hoặc `/saml2/authenticate/corp`, CAS `/cas/login?service=...` hoặc `401 Negotiate`.
5. Tìm IdP interaction: login page `200`, MFA, consent, policy deny hoặc redirect. Lỗi tại IdP cần IdP audit event ID riêng.
6. Tìm **callback về SP**: OIDC GET `/login/oauth2/code/corp`, SAML POST `/login/saml2/sso/corp`, CAS GET `/login/cas` có ticket; SPNEGO dùng cùng endpoint với Negotiate header.
7. Chứng minh callback **qua proxy tới Spring**, được đúng filter xử lý, correlation state tìm được và authentication provider có decision.
8. Nếu callback tới Spring nhưng thất bại, kiểm server back-channel (OIDC token/JWKS/UserInfo, CAS validation) và SAML XML signature/conditions, cùng exact error category.
9. Sau authentication success, kiểm app `SecurityContext` được save, cookie được cấp và request tiếp theo **gửi cookie đúng**; nếu nhiều pods, kiểm Redis/JDBC session store.
10. Truy cập tài nguyên cuối: 200 đúng trang, 401 missing authentication, 403 expected/incorrect authorization, hay 302 về login?
11. Ghi **last good stage → first failed stage → actor/owner → evidence ID → remediation → regression test**. Không kết luận “IdP hỏng” chỉ từ việc browser quay lại login.
12. Sau điều tra, tắt TRACE rộng, purge artifacts nhạy cảm theo policy, báo cáo chỉ dùng bằng chứng đã redact.

**Tiêu chuẩn kết luận:** “Browser đã đến SP callback lúc 09:50 UTC; callback được filter nhận; correlation lookup MISS trên pod-2, token endpoint chưa được gọi; browser không gửi session cookie ở callback” chính xác hơn “SSO redirect lỗi”.

## 5. OAuth2/OIDC Authorization Code: chuỗi mẫu

Spring Security Servlet sử dụng:

```text
(1) Browser -> GET https://portal.example.org/private
(2) Spring  -> 302 /login or /oauth2/authorization/corp
(3) Browser -> GET /oauth2/authorization/corp
(4) Spring  -> 302 https://idp.example.org/authorize?
                    response_type=code&client_id=...&
                    redirect_uri=...&state=...&
                    code_challenge=...&nonce=...
(5) Browser -> IdP authorize/login/MFA (200 or more 302)
(6) IdP     -> 302 https://portal.example.org/
                    login/oauth2/code/corp?code=...&state=...
(7) Browser -> GET /login/oauth2/code/corp?code=...&state=...
(8) Spring  -> [SERVER-TO-SERVER] POST IdP /token
                    code + client authentication + PKCE code_verifier
(9) Spring  <- [SERVER-TO-SERVER] tokens / error
(10) Spring -> verify ID Token, iss/aud/nonce/exp/signature/JWKS
             optional UserInfo / local account mapping
(11) Spring -> save Authentication / SecurityContext / session
(12) Spring -> 302 originally requested URL
(13) Browser-> GET /private with session cookie
(14) Spring -> 200 resource or 403 business authorization
```

**Bước (8)–(10) không hiển thị trong browser Network**; đó là outbound requests từ JVM. Callback `302` chỉ nói Spring đã chuyển hướng, không chứng minh bước (8) đã được thực hiện hoặc thành công.

### 5.1. Những giá trị phải có correlation

| Giá trị | Do ai quản lý? | Điều kiện | Nếu sai/mất |
| --- | --- | --- | --- |
| `state` | OAuth2 client tạo trước redirect, đối chiếu callback | Khớp authorization request đã lưu | `invalid_state`/authorization request not found |
| `OAuth2AuthorizationRequestRepository` | Thường gắn vào `HttpSession` của Servlet flow | Request cũ còn được tìm | Callback không thể liên kết giao dịch |
| `redirect_uri` | ClientRegistration + IdP allowlist | Exact public callback + token exchange | `invalid_redirect_uri`/`invalid_grant` |
| `code` | OP cấp một lần cho client | Chưa dùng, chưa hết hạn | `invalid_grant` hoặc code replay |
| PKCE `code_challenge`/`code_verifier` | Client khởi tạo/chứng minh ở token exchange | Cùng transaction | Token endpoint từ chối |
| `nonce` trong OIDC | Client + ID Token | Khớp request khi yêu cầu | ID Token rejected |
| `iss`/`aud`/`azp` | ID Token / OP metadata | Đúng OP và client policy | Invalid issuer/audience |
| `exp`/`iat` | ID Token | Thời gian hợp lệ theo validator | Expired token, clock skew |
| JWKS `kid`/signature | OP signing keys | Key đang được tin | Unknown kid/invalid signature |
| Session cookie | Browser, Spring session store | Cookie được gửi lại callback/resource | Saved request/session lookup miss |

**Không ghi `state` vào log để “ghép trace”**. Nếu cần định danh toàn login journey, tạo ID ngẫu nhiên server-side gắn vào trusted authorization request state/session; chỉ log ID đó, hoặc log keyed HMAC digest khi có security review. Không dùng raw state/ticket/code làm trace IDs.

### 5.2. Lỗi OIDC theo bước

- **Không xuất hiện bước (4):** Sai login link, chưa có `ClientRegistrationRepository`, filter chain không match `/oauth2/authorization/{registrationId}`, wrong registrationId.
- **IdP từ chối tại (5):** `redirect_uri` không trong client allowlist, `client_id` sai, user policy/MFA/consent bị từ chối. Need IdP log, không sửa browser query thủ công.
- **Callback (7) đến nhưng state lookup MISS:** Browser không gửi session cookie hoặc session expiry/Redis issue/multi-pod memory session/tabs song song làm state overwrite. Giữ state check, sửa session/cookies.
- **Token endpoint (8) trả `invalid_grant`:** Code expired/reused, redirect_uri khác, PKCE verifier sai, client authentication hoặc timing. Không replay production code để thử lại.
- **Token exchange PASS nhưng OIDC `OidcUserService`/decoder FAIL:** Check `iss`/`aud`/`nonce`/`exp`/JWK kid/signature, UserInfo/network/TLS, local account status. Không chấp nhận unsigned JWT hoặc JWKS bất kỳ.
- **App success nhưng (13) quay lại login:** `Set-Cookie`/`Cookie` Domain/Path/Secure/SameSite, session fixation ID rotation, Redis saves, load balancer, wrong forwarded proto.
- **OIDC web login PASS nhưng API trả 401:** `oauth2Login` session cookie không tự thay `oauth2ResourceServer` Bearer access token cho service khác. Token phải đúng audience/scopes, không dùng ID Token làm API access token.
- **Callback bằng `response_mode=form_post`:** Không mặc định là GET; phải test cross-site POST cookies/CSRF giống SAML nếu OP dùng mode này.

### 5.3. Cấu hình ví dụ cho OIDC web app

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-op
            client-id: "portal-client"
            client-secret: "SET_VIA_SECRET_MANAGER_NOT_IN_GIT"
            scope: openid,profile,email
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp-op:
            issuer-uri: "https://idp.example.org/realms/corp"

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Đây là **Spring Boot 3.x fragment**, không tự chạy nếu không có project/dependencies, IdP test và secret được mount an toàn. `same-site: lax` thường hợp lệ cho top-level GET OAuth2 callback, nhưng **không** phải quy tắc cho mọi SAML/POST callback. `forward-headers-strategy` chỉ phù hợp khi trusted edge strip/overwrite `Forwarded`/`X-Forwarded-*`.

## 6. SAML2: HTTP-POST callback thường không có 302 từ IdP

### 6.1. Chuỗi SP-initiated điển hình

```text
(1) Browser -> GET /finance/reports
(2) Spring  -> 302 /login or /saml2/authenticate/corp
(3) Browser -> GET /saml2/authenticate/corp
(4) Spring  -> create AuthnRequest ID R-123,
               store correlation/request context
(5) Spring  -> 302 IdP SSO URL with SAMLRequest + RelayState
               (HTTP-Redirect Binding)
               OR 200 HTML form POST to IdP
(6) Browser -> IdP login/MFA (200 or 302)
(7) IdP     -> 200 HTML with hidden SAMLResponse,
               RelayState and auto-submitting form
(8) Browser -> POST /login/saml2/sso/corp
               Content-Type: application/x-www-form-urlencoded
               SAMLResponse=<Base64 signed XML>
(9) Spring  -> Saml2WebSsoAuthenticationFilter/OpenSAML
               signature, issuer, destination, audience,
               recipient, time, InResponseTo/replay
(10) Spring -> map NameID/attributes; save Authentication
(11) Spring -> 302 saved resource
(12) Browser-> GET resource with app session cookie
(13) Spring -> 200 or authorized 403
```

**Không áp dụng bộ lọc Network chỉ xem redirect 302**. Bước (7) là HTML `200`, bước (8) là browser **POST**. Browser JavaScript/CSP/extension có thể chặn auto-submit; lúc đó IdP báo login thành công nhưng app **không nhận được SAMLResponse**.

### 6.2. Đối chiếu các giá trị SAML

| Thành phần | Kiểm gì? | Lỗi tương ứng |
| --- | --- | --- |
| `registrationId` | Cặp SP–IdP nội bộ đúng | Unknown registration/wrong tenant |
| `AuthnRequest@ID` | Saved request đã phát | Lost `InResponseTo` correlation |
| `RelayState` | Transaction/navigation state theo binding | Lost/altered context, open redirect |
| `Issuer` | IdP EntityID đúng registration | Wrong IdP/tenant |
| XML Signature | Key IdP được tin, exact signed node | Invalid signature/unknown certificate |
| `Destination` | Public ACS mà Response gửi tới | Wrong scheme/host/path |
| `SubjectConfirmationData.Recipient` | ACS SP nhận bearer assertion | Wrong recipient |
| `AudienceRestriction` | SP EntityID đúng | Wrong audience |
| `InResponseTo` | Trỏ request đã tạo (khi SP-initiated) | Missing request/session/mismatch |
| `NotBefore/NotOnOrAfter` | Validity window | Clock skew/NTP/expired assertion |
| `NameID`/`AttributeStatement` | Verified principal/attributes | User mapping/group explosion |
| `SessionIndex` | Liên kết SAML SLO session | Không phải `HttpSession` ID |

**Lớp byte/crypto:** SAMLResponse là Base64 của XML theo HTTP-POST binding; có thể chứa nhiều group values, nhiều signatures, encrypted assertions. Phải có size limits ở edge/container/parser. Không parse XML bằng regex rồi tin NameID/Role trước OpenSAML signature/conditions verification.

### 6.3. Triệu chứng và root-cause candidate

- **SP `/saml2/authenticate/corp` trả 404:** RelyingPartyRegistration missing, wrong Spring SecurityFilterChain, default/custom URL mismatch.
- **IdP hiển thị lỗi trước trả callback:** SP EntityID/ACS chưa đăng ký, AuthnRequest signature/binding lỗi, IdP login/MFA policy từ chối.
- **IdP 200 HTML form nhưng ACS không có POST:** JS/CSP/extension/browser, wrong form action, network block. Xem DevTools Console/Initiator trước khi debug XML signature.
- **Edge thấy ACS POST, Spring không thấy:** NGINX/WAF 413/403/502, TLS upstream, route/host/path mismatch. Dùng `upstream_status`, không tắt validation.
- **ACS POST đến Spring trả 403:** Có thể `CsrfFilter` chặn **trước** SAML filter hoặc WAF trả 403; phân biệt từ logs. ACS POST từ IdP không mang Spring CSRF token thông thường; cần exception có scope chính xác cho SAML endpoint. **Không disable CSRF toàn app**.
- **OpenSAML authentication FAIL:** Signature/issuer/audience/recipient/destination/time/InResponseTo mismatch, certificate rollover, replay. Xem sanitized reason và IdP metadata/trusted keys, không tin unverified `KeyInfo`.
- **SAML provider thành công, browser quay lại IdP:** Spring session/cookie lost, SameSite cross-site POST, session repository, multiple pods; có thể IdP SSO còn sống nhưng app session không.
- **Login OK nhưng resource `403`:** Business tenant/roles, không phải signature. Đừng sửa bằng cách `permitAll()` cho resource.

### 6.4. SameSite và correlation của cross-site POST

```text
T0  Browser GET /saml2/authenticate/corp
    Spring creates HttpSession H-1 and stores AuthnRequest R-123.

T1  Browser visits external IdP at another site.

T2  IdP HTML auto-POSTs SAMLResponse back to SP ACS.

T3  Browser may omit SESSION=H-1 cookie
    because SameSite=Lax normally blocks cross-site POST.

T4  Spring cannot retrieve R-123 for InResponseTo.
    Login fails or loops despite valid IdP signature.
```

Kiểm **Cookies/Blocked cookies reasons** của browser và attributes `SameSite`, `Secure`, `Domain`, `Path`. Khi use case cần `SameSite=None; Secure`, phải có HTTPS, CSRF browser protection trên business endpoints và đánh giá browser/third-party cookie policy. Cookie behavior tùy phiên bản/heuristics; test trên browser mục tiêu, không có một kết luận tuyệt đối cho mọi thiết bị. Không bỏ `InResponseTo`/replay/signature để bù cookie issue.

## 7. CAS: service ticket ở browser, validation ở server

```text
(1) GET https://portal.example.org/private
(2) App 302 https://cas.example.org/cas/login?
              service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas
(3) CAS login page 200; user authenticates / TGC SSO
(4) CAS 302 https://portal.example.org/login/cas?ticket=ST-...
(5) Browser GET /login/cas?ticket=ST-...
(6) Spring -> [SERVER-TO-SERVER] CAS /serviceValidate
              with exact service URL and ticket
(7) CAS -> [SERVER-TO-SERVER] ticket success/error
(8) Spring -> local Authentication, session, redirect resource
```

`/login/cas` là URL mặc định ở nhiều tích hợp `CasAuthenticationFilter`; hệ thống có thể dùng custom route. `service` phải khớp public service URL đã đăng ký và được CAS dùng để phát ticket: khác HTTPS/HTTP, hostname, port, path hoặc trailing slash có thể dẫn đến ticket reject.

**Nếu callback có ticket nhưng app lại về login:** kiểm CAS back-channel network/TLS, CAS service registry, ticket single-use/expiry, `ServiceProperties` và session. **Đừng replay raw ticket** lấy từ HAR production hoặc log query `ticket`. CAS Server TGT/TGC và local app session có lifecycle khác nhau; local logout không tự bảo đảm CAS global logout.

## 8. Kerberos/SPNEGO: 401 challenge là bước bình thường

```text
(1) Browser -> GET https://intranet.example.org/private
               without Authorization: Negotiate
(2) Server  -> 401 Unauthorized
               WWW-Authenticate: Negotiate
(3) Browser -> obtains service ticket through OS/KDC
               then GET with Authorization: Negotiate <token>
(4) Server  -> JAAS/GSS validates AP-REQ via HTTP service keytab
(5) Server  -> 200 resource OR further challenge/failure
```

**Không gọi bước (2) “SSO thất bại” chỉ vì 401.** Tìm request sau đó: browser có `Authorization: Negotiate` không? Nếu không, kiểm browser enterprise policy/trusted intranet zone, SPN DNS/host, KDC ticket cache, user environment. Nếu đã có mà vẫn 401, kiểm `HTTP/public-host@REALM`, keytab/KVNO, etype, time skew, GSS service acceptor, delegation/channel binding theo thiết kế.

`Authorization: Negotiate` mang token nhạy cảm; không in raw header. Khi SPNEGO terminate ở edge, Spring chỉ nhận identity nếu có trusted pre-auth contract qua kênh bảo vệ; HTTP `X-User` chưa được verify không phải Kerberos proof. Một số tích hợp có fallback `302` form login, cần phân biệt fallback policy với Kerberos success.

## 9. Reverse proxy: mất public URL và redirect loop

```text
Browser: https://portal.example.org/private
             |
             v
    NGINX HTTPS termination
             |
             v
    Spring app http://spring:8080
             |
             +-- WITHOUT trusted forwarding:
                   Spring sees http://spring:8080
                   generates redirect_uri/ACS/service with wrong host/scheme
             |
             +-- WITH canonical forwarding:
                   Spring sees https://portal.example.org
                   generates expected registered callback URLs
```

Sai forwarded headers có thể làm OIDC `invalid_redirect_uri`, SAML `Destination`/`Recipient` mismatch, CAS `service` mismatch và `https → http → https` loop. Đừng chỉ thay allowlist IdP thành internal URL, vì browser có thể không tới được và TLS/session sẽ sai.

### 9.1. NGINX trusted edge fragment

```nginx
# Fragment trong server { listen 443 ssl; ... }
location / {
    proxy_pass http://spring.internal:8080;

    # Tại trusted edge: không forward các values do client tự nhận.
    proxy_set_header Host portal.example.org;
    proxy_set_header Forwarded "";
    proxy_set_header X-Forwarded-Host portal.example.org;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Port 443;
    proxy_set_header X-Forwarded-For $remote_addr;

    # Request correlation chỉ nội bộ app/edge.
    proxy_set_header X-Request-ID $request_id;

    proxy_connect_timeout 5s;
    proxy_read_timeout 30s;
}
```

Nếu yêu cầu proxy→backend mTLS, thay `proxy_pass http://...` bằng HTTPS upstream có `proxy_ssl_verify on`, CA/SNI và client certificate đúng; ví dụ trên minh họa canonical forwarding, không phải một deployment mTLS. Edge cần strip/overwrite cả `Forwarded` lẫn nhóm `X-Forwarded-*`; `X-Request-ID` từ client cũng nên được thay bằng ID tại trusted edge, không dùng làm identity.

Spring Boot fragment:

```yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

**Lưu ý:** `forward-headers-strategy` không tự xác minh proxy identity. Nếu app public direct hoặc attacker giả `X-Forwarded-Host`, có thể tạo malicious redirect/open redirect. Chặn đường bypass, canonical hosts, trusted proxy IP/workload identity và test host spoofing. Nếu IdP sử dụng cross-site POST, `same-site: lax` cần xem lại theo chính sách mục 6.4.

### 9.2. Những vòng lặp thường gặp

| Loop | Bằng chứng | Bước khắc phục |
| --- | --- | --- |
| `/private → /login → /private` vô hạn | Auth cookie không được gửi/Redis MISS | Cookie + session storage |
| `https → http → https` | Edge 301, Spring 302 ngược | Forwarded scheme, HTTPS policy |
| `OIDC IdP → callback → /login?error` | Auth failure handler | State, PKCE, token/JWKS |
| `SAML IdP → ACS → /login` | OpenSAML fail hoặc no session | Signature/InResponseTo/cookie |
| `CAS → /login/cas → CAS` | Ticket validation/cookie failed | Service URL, CAS back-channel |
| 401 Negotiate liên tiếp | No Negotiate token/GSS failure | Browser policy, SPN, keytab |
| `/error` lại redirect `/login` | Error route protected hoặc wrong chain | Secure error page config |
| 302 tới internal hostname | Wrong Host/XFH | Canonical public base URL |
| Login success nhưng original URL mất | SavedRequest/handler override | RequestCache, success handler |

Tránh giải pháp nguy hiểm: `permitAll()` toàn bộ routes, `csrf.disable()` toàn cục, bỏ `state`/SAML signature hoặc tin mọi certificate. Cần sửa từng ranh giới theo evidence.

## 10. Dùng DevTools Network và HAR đúng cách

1. Dùng IdP/account staging, mở DevTools **trước** khi bắt đầu.
2. Bật **Preserve log** để giữ timeline khi browser chuyển site. Với SAML phải xem `All`, gồm POST và HTML form, không chỉ GET/Doc.
3. Ghi request method/status/host/path/response `Location` origin/path **không lưu query values**.
4. Xem **Initiator**: navigation 302, HTML form auto-submit hoặc script; kiểm Console nếu ACS POST không xuất hiện.
5. Xem `Request Headers` và `Response Headers` trên máy kiểm thử nhưng chỉ **chia sẻ** presence/cookie attributes, không value.
6. Vào Network → Cookies / blocked reasons để kiểm SameSite/Secure/Domain/Path, third-party restrictions.
7. Xem timings: DNS/connect/TLS/wait; phân biệt browser network outage với OIDC token endpoint call không hiển thị.
8. Dùng filter `All` để không bỏ redirect response/status của iframe, favicon hoặc form; chú ý các request khác có thể là noise.
9. Chỉ export **HAR (sanitized)** khi cần. Theo Chrome DevTools, chế độ sanitized loại một số headers nhạy cảm như `Cookie`/`Set-Cookie`/`Authorization`, **nhưng không đảm bảo xóa hết query code/state/CAS ticket hay form SAMLResponse**.
10. Review/redact mọi `request.url`, `postData`, `response.content`, custom headers và screenshot trước khi đưa sang ticket/chat/IdP.
11. Lưu artifacts trong kho access restricted, thời hạn retention ngắn; không dùng URL raw làm labels hoặc đưa secrets vào công cụ APM của bên thứ ba.
12. Tắt debug mode sau khi có evidence, kiểm credentials/session impact nếu artifact từng bị phát tán.

### 10.1. Bảng HAR hữu ích

| Trường | Giá trị chẩn đoán | Quy tắc bảo mật |
| --- | --- | --- |
| `startedDateTime` | Xếp timeline theo UTC | Bảo đảm clock sync |
| `request.method` | GET vs POST SAML | Có thể log |
| `request.url` | Origin/path và query key names | Redact `code/state/ticket` values |
| `response.status` | Redirect/4xx/5xx | Không tự suy authentication result |
| `response.redirectURL` | Đích tiếp theo | Chỉ lưu origin/path |
| `request.postData` | SAMLResponse/RelayState có xuất hiện? | **Không lưu raw payload** |
| `headers.Cookie` | Session có được gửi không? | Presence only |
| `headers.Set-Cookie` | Session được cấp không? | Attributes only, không value |
| `timings` | Latency/network trouble | Có thể đo và so |
| `_initiator` | Auto-submit/JS vs redirect | Tìm POST bị chặn |

### 10.2. Vì sao `curl -L` không đủ?

`curl -L` không tự chạy HTML JavaScript auto-submit SAML form, không thực hiện IdP MFA/consent theo browser, không tự mô phỏng browser SameSite cookie rules, và không hiện Spring backend token/JWKS/CAS validator requests. `curl -I` gửi HEAD chứ không phải GET; một endpoint có thể trả status khác giữa HEAD/GET, vì thế đừng dùng nó làm bằng chứng trọn flow.

Test đơn giản trên staging, **không đi theo redirect**, chỉ in status:

```bash
curl -sS --max-redirs 0 \
  -o /dev/null -w '%{http_code}\n' \
  https://portal.example.org/private
```

Nếu in response headers với `curl -D -`, có thể lộ `Location` chứa code/ticket hoặc `Set-Cookie`; không sao chép nguyên output sang ticket. Các lệnh trên không thực hiện authentication thực.

## 11. Correlation IDs: không dùng token/session làm trace ID

Có ba loại correlation khác nhau:

- **Request ID:** Sinh ở trusted edge hoặc Spring cho **một HTTP request**. Hữu ích so NGINX status với Spring status; không tự đi sang IdP khi browser navigate tới origin khác.
- **Distributed trace ID:** `traceId`/`spanId` từ Micrometer Tracing/OpenTelemetry với instrumented server-to-server HTTP clients. Chỉ truyền ở các hop có hỗ trợ/trust, không bảo đảm IdP tham gia trace.
- **SSO journey ID:** Random ID do app tạo khi khởi tạo login và lưu cùng server-side authentication request/session. Có thể ghép start, callback, token exchange, session save với một ID an toàn, không log raw `state`/`RelayState`/authorization code.

**Đừng dùng hash SHA-256 trần của `state`/ticket như một “safe correlation ID” theo mặc định**: một số giá trị có thể bị đoán/tra ngược, và Hash còn có thể là PII identifier. Nếu cần derived marker, dùng keyed HMAC, secret management, scoped retention và security review. Không cho client tự đặt `X-Request-ID`/`traceparent` để ảnh hưởng security decisions hoặc metric cardinality; có thể regenerate/normalize tại trust boundary.

### 11.1. Structured event minh họa

```json
{
  "event": "SSO_STAGE",
  "utc": "2030-05-10T09:50:00Z",
  "journeyId": "generated-server-side-id",
  "requestId": "generated-edge-id",
  "protocol": "OIDC",
  "registrationId": "corp",
  "stage": "CALLBACK",
  "method": "GET",
  "routeCategory": "oidc_callback",
  "status": 302,
  "decision": "FAIL",
  "reason": "AUTHORIZATION_REQUEST_NOT_FOUND",
  "cookiePresented": false,
  "sessionLookup": "MISS",
  "appNode": "portal-pod-2",
  "elapsedMs": 19
}
```

**Đây là schema đề xuất, không phải event Spring Security built-in.** `sessionLookup`/`decision` chỉ được ghi theo kết quả đo/validation thực sự. Không dùng raw token, SAMLResponse, NameID, cookie, client secret hoặc principal data làm fields.

### 11.2. Những gì mỗi tầng có thể chứng minh

| Tầng | Chứng cứ đáng tin | Không chứng minh |
| --- | --- | --- |
| Browser | Request và response đã thấy; cookie blocked | Spring đã gọi token endpoint |
| Edge | Route/upstream status, TLS, request ID | User đã được IdP authenticate |
| Spring filter | Chọn chain, callback nhận/validation outcome | Các redirects bên trong IdP khi không có trace |
| Spring Session | Session save/read HIT/MISS, TTL | IdP SSO session đã logout |
| OP/IdP | Login policy, MFA, token/assertion issued | Local app session đã lưu thành công |
| CAS validator | Ticket valid/invalid and service URL | Browser session cookie policy |
| KDC/GSS | Ticket/SPN/keytab validation | App user có quyền business tenant |
| App authorization | Role/tenant/resource allow/deny | OAuth code state đã qua nếu không có trace liên kết |

## 12. Spring Security logging: tìm đúng filter/stage

Spring Security Servlet dùng `FilterChainProxy` với nhiều `SecurityFilterChain`. Bật DEBUG/TRACE có mục tiêu để xác nhận callback có đi qua đúng filters không.

Ví dụ **tạm thời trong staging**:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
    org.springframework.security.oauth2: DEBUG
    org.springframework.security.saml2: DEBUG
```

Các filter thường liên quan:

| Filter/provider | Vai trò | Khi cần nhìn |
| --- | --- | --- |
| `ExceptionTranslationFilter` | Khởi phát auth entry point khi unauthenticated | GET protected resource dẫn đi đâu |
| `OAuth2AuthorizationRequestRedirectFilter` | Phát authorize request sang OP | Không thấy OIDC redirect |
| `OAuth2LoginAuthenticationFilter` | Nhận authorization response callback | Callback OIDC lỗi |
| OAuth2 token response client/`OidcUserService` | Token exchange/UserInfo phía backend | Callback đến nhưng không login |
| `Saml2WebSsoAuthenticationRequestFilter` | Tạo AuthnRequest SAML | Không rời SP đến IdP |
| `Saml2WebSsoAuthenticationFilter` | Nhận SAMLResponse tại ACS | POST tới Spring mà không authenticate |
| `CsrfFilter` | Kiểm browser CSRF token | POST ACS/other endpoint 403 trước provider |
| `SecurityContextHolderFilter`/repositories | Đọc/ghi auth context theo config | Login success nhưng session mất |
| `AuthorizationFilter` | Quyền resource sau auth | Auth PASS nhưng resource 403 |
| `CasAuthenticationFilter`/`CasAuthenticationProvider` | CAS ST processing/validation | CAS callback error |
| `SpnegoEntryPoint`/`SpnegoAuthenticationProcessingFilter` | Negotiate challenge/GSS | SPNEGO 401 lặp |

**Cảnh báo:** Exact filters/classes và ordering phụ thuộc Spring Security version và active feature configuration. Spring 6 và Spring 7 có những thay đổi. Việc bật `org.springframework.security=TRACE` có thể log URL/parameters/headers tùy custom filters, phải giới hạn thời gian/tenant/staging, kiểm redaction và tắt lại sau điều tra.

Nếu callback tới proxy mà không có Spring filter log, kiểm `502/404/413` ở gateway, Service URL/upstream routing hoặc Servlet filter registration **trước** khi phỏng đoán XML/JWT failure. Nếu Spring có nhiều chains (API Bearer và browser SSO), test callback matched chain nào; route vào API-only chain có thể chỉ trả `401 Bearer` mà không chạy OAuth2/SAML login filter.

## 13. Java Spring Boot observation filter không làm lộ token

Mã sau dùng Spring Boot 3.x, Spring Web, SLF4J, Java 17. Nó **không sửa authentication**, chỉ ghi **category**/status và gắn appRequestId. Không đọc `getQueryString()`/`getParameter()`/`SAMLResponse`/`Authorization`/`Cookie`/`Location`.

File `src/main/java/com/example/sso/SsoObservationFilter.java`:

```java
package com.example.sso;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class SsoObservationFilter
        extends OncePerRequestFilter {

    private static final Logger LOG =
        LoggerFactory.getLogger(SsoObservationFilter.class);

    private static String route(String path) {
        if (path == null) return "unknown";
        if (path.matches("^/oauth2/authorization/[^/]+$")) {
            return "oidc_start";
        }
        if (path.matches("^/login/oauth2/code/[^/]+$")) {
            return "oidc_callback";
        }
        if (path.matches("^/saml2/authenticate/[^/]+$")) {
            return "saml_start";
        }
        if (path.matches("^/login/saml2/sso(?:/[^/]+)?$")) {
            return "saml_acs";
        }
        if ("/login/cas".equals(path)) {
            return "cas_callback";
        }
        if ("/login".equals(path)) {
            return "login_page";
        }
        if (path.startsWith("/private/")) {
            return "protected_resource";
        }
        return "other";
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        String routeCategory = route(request.getServletPath());
        long t0 = System.nanoTime();

        MDC.put("appRequestId", id);
        response.setHeader("X-App-Request-ID", id);

        try {
            chain.doFilter(request, response);
        }
        finally {
            long elapsedMs = (System.nanoTime() - t0) / 1_000_000L;

            LOG.info(
                "sso_request id={} route={} method={} status={} ms={}",
                id, routeCategory, request.getMethod(),
                response.getStatus(), elapsedMs);

            MDC.remove("appRequestId");
        }
    }
}
```

File `src/main/java/com/example/sso/ObservationFilterConfig.java`:

```java
package com.example.sso;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class ObservationFilterConfig {

    @Bean
    FilterRegistrationBean<SsoObservationFilter> ssoFilter() {

        var bean = new FilterRegistrationBean<>(
            new SsoObservationFilter());

        bean.addUrlPatterns("/*");
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return bean;
    }
}
```

**Phạm vi:** Hai files cần Spring Boot dependencies/project thực, không `javac` độc lập. Filter là một **Servlet Filter** được đăng ký bởi `FilterRegistrationBean` trước Spring Security FilterChain ở thứ tự thông thường; không đồng thời đánh dấu `@Component` hay gắn cùng instance vào `http.addFilterBefore` để tránh chạy hai lần. `getServletPath()` phụ thuộc Servlet/context-path và proxy rewriting; test routes thực tế.

**Chưa làm được gì?** Filter này chỉ cho biết request/route/status; **không tự phân biệt 302 success với 302 failure**, không tự đọc credential state, không theo back-channel, không nối IdP origin, không chứng minh user authenticated. Muốn biết success/failure cần hook/auth provider events hoặc success/failure handlers có redaction. Không thay `SavedRequestAwareAuthenticationSuccessHandler` bằng handler hardcoded nếu chưa test saved-request restoration.

`X-App-Request-ID` là ID ngẫu nhiên cho **mỗi request**, không phải login journey ID. `MDC.remove` ở finally tránh rò ID sang request kế trên thread pool. Với async requests, `finally` có thể được gọi trước khi response hoàn tất; cần Observation/AsyncListener phù hợp nếu muốn timing cuối chính xác. Nếu exception phát sinh và container error mapping chạy sau filter, `response.getStatus()` chưa chắc là final HTTP status, cần đối chiếu server access log.

## 14. Spring Security SecurityFilterChain và callback routing

Mẫu Spring Security 6.x Servlet fragment:

```java
package com.example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SsoSecurityConfiguration {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
```

Cần thêm OAuth2 ClientRegistrationRepository và SAML RelyingPartyRegistrationRepository thật cùng phụ thuộc module phù hợp. Khi bật cả OIDC và SAML, phải thiết kế login page/entry point để chọn IdP và regression test login. Đây là **fragment**, không tự chạy với Java thuần.

Một callback bắt buộc nằm trong security chain chứa đúng authentication filter, **không** được route tới controller tự lấy `code`/`SAMLResponse` rồi tạo session. `permitAll` không được thay thế verification ở callback. Nếu ứng dụng cấu hình nhiều `SecurityFilterChain`, cần xem matcher và thứ tự chains; resource server chain có thể bắt callback và trả 401/404 khiến tưởng IdP lỗi.

### 14.1. Authentication result khác HTTP redirect

- Spring success handler có thể redirect về `SavedRequest` hoặc default success URL. Tùy custom handler, URL có thể khác.
- Failure handler có thể redirect về `/login?error`, cũng là HTTP `302`.
- Một exception từ token exchange hoặc SAML validation có thể được mapping thành `401`/`400`/`302` tùy handler.
- Ghi **auth outcome event** (SUCCESS/FAIL with safe reason) tại approved extension point nếu cần chứng minh; không đoán success chỉ từ 302.
- `RequestCache` và `SavedRequestAwareAuthenticationSuccessHandler` dùng để đưa user về URL đã yêu cầu; custom success handler hardcoded có thể làm mất đúng navigation dù authentication thành công.
- Server-side session save có thể fail vì Redis/downstream; auth success không đồng nghĩa subsequent request vẫn authenticated.

## 15. Micrometer Tracing và session continuity

Spring Boot Actuator/Micrometer Tracing có thể sinh `traceId`/`spanId` trong MDC khi có đúng dependencies/config; không tự có full tracing nếu chỉ dùng Spring Web. Các HTTP client builders được Boot instrument có thể propagate trace qua outbound calls tới OP token endpoint, UserInfo, CAS, nhưng không tự nối browser redirects qua IdP external.

```yaml
management:
  tracing:
    sampling:
      probability: 0.10

logging:
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
```

Đây là fragment **theo Spring Boot version**, không bảo đảm cùng property/dependency ở mọi 3.x/4.x. `0.10` là tỷ lệ mẫu, không phải dữ liệu thật hoặc compliance recommendation. Không nên sử dụng sampling thấp làm nguồn security audit duy nhất. **Không đưa state/RelayState/authorization code/session cookie vào baggage**; tracing exporters có thể chuyển data tới nhà cung cấp bên ngoài.

### 15.1. Session continuity checklist

```text
Before redirect:
   saved request or OAuth2AuthorizationRequest/AuthnRequest exists?
   session record created? Set-Cookie attributes?

At callback:
   browser sends corresponding cookie? (presence only)
   state/RelayState/InResponseTo points to saved transaction?
   same or other pod? shared Spring Session repository working?

After authentication success:
   SecurityContext saved? Session ID changed as expected?
   Set-Cookie sent? Cookie Domain/Path/Secure/SameSite correct?

After redirect back to resource:
   browser sent new app session cookie?
   Spring Session lookup HIT?
   Authentication restored, or anonymous?
   authorization allowed for tenant/resource?
```

**Session ID rotation** sau authentication có thể là bảo vệ session fixation hợp lệ. Đừng mặc định khác cookie value trước/sau login là lỗi. Ngược lại, một `200` login page khi truy cập `/private` sau success có thể là **session lost** dù URL không 302.

## 16. Java 17 độc lập: phân loại bước lỗi theo events đã được tin cậy

Ví dụ sau không cần Spring, IdP, HTTP server hay certificate. Nó minh họa cách đọc một danh sách **events mô phỏng** để phân biệt callback correlation, back-channel failure và SPNEGO challenge; **không** thực hiện OIDC/SAML/CAS/Kerberos thực, không giải mã tokens, không xác minh chữ ký. Các cờ `correlated`/`outcome` trong ví dụ là test fixtures, không được nhận từ browser.

File `SsoRedirectDiagnosisDemo.java`:

```java
import java.util.List;

public final class SsoRedirectDiagnosisDemo {

    enum Protocol { OIDC, SAML, CAS, SPNEGO }

    enum Stage {
        START, TO_IDP, CALLBACK, BACKCHANNEL,
        SESSION, RESOURCE, CHALLENGE
    }

    record Event(
        Protocol protocol,
        Stage stage,
        int status,
        boolean correlated,
        String outcome
    ) { }

    static String diagnose(List<Event> events) {
        if (events == null || events.isEmpty()) {
            return "NO_EVIDENCE";
        }

        Protocol protocol = events.get(0).protocol();
        for (Event event : events) {
            if (event.protocol() != protocol) {
                return "MIXED_PROTOCOL";
            }
        }

        if (protocol == Protocol.SPNEGO
                && events.size() == 1
                && events.get(0).stage() == Stage.CHALLENGE
                && events.get(0).status() == 401) {
            return "EXPECTED_NEGOTIATE_CHALLENGE";
        }

        // Heuristic demo, KHÔNG phải tiêu chuẩn SSO:
        // 4 redirects 302 liên tiếp giữa START và TO_IDP.
        if (events.size() >= 4) {
            boolean looping = true;
            for (int i = events.size() - 4;
                    i < events.size(); i++) {
                Event event = events.get(i);
                if (event.status() != 302
                        || (event.stage() != Stage.START
                            && event.stage() != Stage.TO_IDP)) {
                    looping = false;
                }
            }
            if (looping) return "REDIRECT_LOOP";
        }

        for (Event event : events) {
            if (event.stage() == Stage.CALLBACK
                    && !event.correlated()) {
                return "CORRELATION_GAP@CALLBACK";
            }
            if ("FAIL".equals(event.outcome())) {
                return "FAIL@" + event.stage() + ":" + event.status();
            }
        }

        Event last = events.get(events.size() - 1);
        if (last.stage() == Stage.RESOURCE
                && last.status() == 200
                && "OK".equals(last.outcome())) {
            return "COMPLETE";
        }

        return "INCOMPLETE@" + last.stage();
    }

    static Event event(Protocol p, Stage s, int code,
            boolean correlated, String outcome) {
        return new Event(p, s, code, correlated, outcome);
    }

    public static void main(String[] args) {
        var oidcOk = List.of(
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 200, true, "OK"),
            event(Protocol.OIDC, Stage.CALLBACK, 302, true, "OK"),
            event(Protocol.OIDC, Stage.BACKCHANNEL, 200, true, "OK"),
            event(Protocol.OIDC, Stage.SESSION, 302, true, "OK"),
            event(Protocol.OIDC, Stage.RESOURCE, 200, true, "OK"));

        var oidcLostState = List.of(
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 200, true, "OK"),
            event(Protocol.OIDC, Stage.CALLBACK, 302, false, "UNKNOWN"));

        var samlDenied = List.of(
            event(Protocol.SAML, Stage.START, 302, true, "OK"),
            event(Protocol.SAML, Stage.TO_IDP, 200, true, "OK"),
            event(Protocol.SAML, Stage.CALLBACK, 403, true, "FAIL"));

        var casInvalid = List.of(
            event(Protocol.CAS, Stage.START, 302, true, "OK"),
            event(Protocol.CAS, Stage.CALLBACK, 302, true, "OK"),
            event(Protocol.CAS, Stage.BACKCHANNEL, 401, true, "FAIL"));

        var spnegoChallenge = List.of(
            event(Protocol.SPNEGO, Stage.CHALLENGE, 401, true, "OK"));

        var redirectLoop = List.of(
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 302, true, "OK"),
            event(Protocol.OIDC, Stage.START, 302, true, "OK"),
            event(Protocol.OIDC, Stage.TO_IDP, 302, true, "OK"));

        System.out.println("oidcOk=" + diagnose(oidcOk));
        System.out.println("oidcLostState=" + diagnose(oidcLostState));
        System.out.println("samlDenied=" + diagnose(samlDenied));
        System.out.println("casInvalid=" + diagnose(casInvalid));
        System.out.println("spnegoChallenge=" +
            diagnose(spnegoChallenge));
        System.out.println("redirectLoop=" + diagnose(redirectLoop));
        System.out.println("empty=" + diagnose(List.of()));
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac --release 17 SsoRedirectDiagnosisDemo.java
java SsoRedirectDiagnosisDemo
```

Stdout **chính xác**:

```text
oidcOk=COMPLETE
oidcLostState=CORRELATION_GAP@CALLBACK
samlDenied=FAIL@CALLBACK:403
casInvalid=FAIL@BACKCHANNEL:401
spnegoChallenge=EXPECTED_NEGOTIATE_CHALLENGE
redirectLoop=REDIRECT_LOOP
empty=NO_EVIDENCE
```

### 16.1. Giải thích đúng giới hạn

- `oidcOk`: danh sách event đã có RESOURCE 200 với outcome OK; **chưa chứng minh** IdP ký token thật vì dữ liệu do test fixture đặt.
- `oidcLostState`: callback có `correlated=false` nên tìm correlation gap; không được suy từ HTTP 302 một mình.
- `samlDenied`: biết callback bị reject 403, **chưa xác định CSRF/WAF/signature** nếu chưa có actor/failure reason.
- `casInvalid`: failure ở CAS ticket-validation back-channel; browser có thể vẫn thấy callback redirect bình thường.
- `spnegoChallenge`: 401 ban đầu là expected negotiation stage; cần request tiếp theo để kết luận thành công.
- `redirectLoop`: heuristic về 4 redirects không phải định lý; IdP MFA cũng có thể nhiều 302 hợp lệ, nên production detector cần URL categories, session progression, bounded time và rate threshold.
- `empty`: không có evidence, phải thu thập thêm chứ không quy lỗi IdP.
- Code không lưu/đọc raw tokens, cookie, SAMLResponse; production observability phải lấy trust decisions từ filter/provider thật.

## 17. Ma trận kiểm thử redirect và localization

| Case | Cách tái hiện trong staging | Bước lỗi/tiêu chí |
| --- | --- | --- |
| **OIDC happy path** | Resource → authorize → callback → token → session | 200 resource, đúng login |
| **OIDC redirect_uri sai** | Client URI không thuộc OP allowlist | IdP authorization reject |
| **OIDC state missing** | Expire saved authorization request | Callback reject, không bỏ state |
| **OIDC two tabs** | Start hai login đồng thời | Correlation riêng, không overwrite sai |
| **OIDC code reuse** | Replay một authorization code test | Token endpoint `invalid_grant` |
| **OIDC PKCE wrong verifier** | Test verifier sai | Token request reject |
| **OIDC issuer wrong** | ID Token OP B thay OP A | Validation fail |
| **OIDC audience wrong** | ID Token aud cho client khác | Validation fail |
| **OIDC nonce mismatch** | Nonce khác request | Validation fail |
| **OIDC signing key rotated** | OP publish JWK mới | Trusted JWKS refresh, unknown key reject |
| **OIDC token endpoint 503** | OP staging outage | Server-side back-channel fail |
| **OIDC UserInfo timeout** | Mock UserInfo timeout | App failure handled, không loop vô hạn |
| **OIDC form_post cross-site** | OP dùng POST callback | Cookie/CSRF policy đúng |
| **SAML happy path** | Signed Response ACS POST | Signature/conditions/session pass |
| **SAML JS blocked** | Chặn IdP auto-submit form | IdP 200 nhưng không ACS POST |
| **SAML ACS wrong** | IdP POST khác path/host | Proxy 404, recipient/destination reject |
| **SAML CsrfFilter 403** | SAML ACS matcher không ngoại lệ đúng | Chặn trước provider, sửa scoped config |
| **SAML signature wrong** | Test cert lạ ký Response | OpenSAML reject |
| **SAML issuer wrong** | IdP khác registration | Reject |
| **SAML audience wrong** | SP EntityID sai | Reject |
| **SAML InResponseTo wrong** | Signed response R2, saved R1 | Reject |
| **SAML expired assertion** | NotOnOrAfter past | Reject |
| **SAML replay** | Replay assertion/response fixture | Reject theo replay policy |
| **SAML 413** | Nhiều groups làm body quá lớn | Edge/Servlet rejects trước parser |
| **SAML SameSite=Lax POST** | Cross-site IdP ACS POST | Cookie blocked, correlation miss |
| **SAML two IdPs** | IdP A response tới registration B | Reject, không cấp tenant B |
| **CAS happy path** | ST + serviceValidate | Login success |
| **CAS wrong service URL** | Public URL lệch protocol | CAS ticket reject |
| **CAS ST replay** | Ticket test dùng hai lần | Không authenticate lần hai |
| **CAS server TLS fail** | CA không tin CAS endpoint | Back-channel failure |
| **SPNEGO first 401** | No token request | Expected Negotiate challenge |
| **SPNEGO browser no token** | Browser không trust origin | Không có Authorization header sau 401 |
| **SPNEGO wrong SPN** | Ticket SPN khác HTTP hostname | GSS reject |
| **SPNEGO keytab KVNO mismatch** | Server keytab cũ | GSS reject |
| **Proxy wrong XFP** | App thấy http internal | redirect_uri/ACS/service sai |
| **Proxy 502** | Backend TLS/DNS fail | Edge fail, Spring không nhận |
| **HTTP/HTTPS loop** | Edge redirect HTTPS, app redirect HTTP | Repeated canonical path |
| **307 SAML POST** | Redirect ACS POST giữ body | Reject unsafe redirect/leak risk |
| **Session Redis outage** | Kill test Redis while callback | Authentication pass but session save/read fail |
| **Multiple pods local sessions** | Start pod A, callback pod B | Auth request missing |
| **Browser cookie Path wrong** | Session cookie không đến callback | Correlation gap |
| **SavedRequest lost** | Success handler hardcoded | Login success, wrong post-login URL |
| **API Bearer only chain** | Callback route vào Resource Server chain | 401 instead of OIDC/SAML callback |
| **Authenticated but 403** | User không có quyền tenant | Expected business deny |
| **TRACE output audit** | Bật debug trong staging | Không có raw code/ticket/SAMLResponse trong shared logs |
| **Sanitized HAR audit** | Export HAR/test | Query/form secrets vẫn được redact |
| **IdP policy MFA deny** | User không đáp ứng MFA | IdP error stage/owner rõ ràng |
| **Clock skew** | OP/IdP/adapter lệch NTP | Token/assertion time reject; sửa NTP |
| **Unknown registrationId** | URL start không tồn tại | Không fallback tenant khác |

**Không thể test post-validation bằng cách sửa signed SAML XML sau khi ký**, vì điều đó gây signature error trước khi tới đúng stage muốn test. Với “wrong audience nhưng signature hợp lệ”, tạo signed fixture **với wrong audience trước khi ký** bằng IdP test. Với token exchange, dùng OP staging, không log production codes.

## 18. Sáu runbook thực hành

### A. OIDC IdP login xong nhưng quay về `/login?error`

1. Xác minh callback `/login/oauth2/code/corp` tới Spring, không chỉ tới edge.
2. Xác nhận `OAuth2LoginAuthenticationFilter` thực sự match.
3. Kiểm session cookie, `AuthorizationRequestRepository` lookup và `state` correlation (không log raw state).
4. Nếu correlation pass, kiểm token back-channel HTTP status/error class, PKCE verifier, redirect URI, client auth.
5. Nếu token pass, kiểm ID Token `iss/aud/nonce/exp/signature`, JWKS and local user mapping.
6. Ghi sanitized reason. Tránh “sửa” bằng cách bỏ state/PKCE.

### B. SAML IdP báo 200 nhưng không có login tại SP

1. Xem IdP có HTML auto-submit POST form không.
2. Tìm browser POST ACS trong Network. Nếu không có, kiểm JS/CSP/Console.
3. Nếu có POST ở edge nhưng Spring không thấy, kiểm WAF/413/502/location/TLS.
4. Nếu Spring nhận, phân biệt `CsrfFilter` 403 với OpenSAML signature/conditions reject.
5. Nếu SAML success, kiểm session persistence/cookie/browser.
6. Không thu thập SAMLResponse production qua ticket không kiểm soát.

### C. SAML `InResponseTo` sai sau load balancing

1. AuthnRequest phát trên pod A với state lưu local.
2. Callback ACS POST tới pod B.
3. Pod B không thấy local session/saved AuthnRequest → `InResponseTo` reject.
4. Khắc phục bằng shared Spring Session Redis/JDBC hoặc kiến trúc sticky có kiểm soát, test cookie SameSite.
5. Retest hai pods với signed IdP fixtures. Không bỏ InResponseTo để đạt 200.

### D. CAS có ticket nhưng ticket validate fail

1. Browser callback GET có `ticket` (chỉ ghi presence).
2. Kiểm Spring CAS validator outbound request tới CAS server.
3. So exact `service` URL public, client TLS truststore/hostname và CAS registry.
4. Kiểm ticket one-time/expired; tạo ticket mới trong staging, không replay.
5. Sửa forwarded canonical URL nếu Spring thấy HTTP internal hostname.

### E. SPNEGO trả 401 liên tục

1. `WWW-Authenticate: Negotiate` có xuất hiện? Nếu không, kiểm entry point/chain.
2. Browser có gửi `Authorization: Negotiate` request sau? Nếu không, kiểm enterprise browser trust/OS ticket.
3. Server có GSS acceptor và keytab đúng `HTTP/host@REALM`?
4. Kiểm SPN/DNS, KVNO, etype, NTP và GSS error codes.
5. Không lưu GSS token/keytab vào logs; fallback login chỉ khi được policy cho phép.

### F. Login PASS nhưng `/admin` trả 403

1. Có authentication success event và session HIT?
2. 403 do Spring `AuthorizationFilter`/`@PreAuthorize`/policy service hay WAF?
3. Kiểm user internal ID, issuer-scoped identity, tenant membership và resource action.
4. Nếu user không có quyền, 403 là **đúng**, không phải IdP outage.
5. Không `permitAll()` /admin chỉ để thấy 200; test cross-tenant.

## 19. Các bẫy bảo mật khi gỡ lỗi

| Cách “sửa nhanh” nguy hiểm | Hậu quả | Cách sửa đúng |
| --- | --- | --- |
| Bỏ kiểm OIDC `state` | Login CSRF/session mix-up | Sửa cookie/request repository |
| Bỏ PKCE/nonce validation | Code/token substitution | Sửa verifier/nonce correlation |
| Tắt JWT signature/`iss/aud` | Token giả hoặc client khác được nhận | Sửa trust/JWKS/client config |
| Tin certificate trong raw SAML `KeyInfo` | Signature trust bypass | Trusted IdP registration keys |
| Bỏ `InResponseTo` | Replay/unsolicited login risk | Sửa saved request/session |
| `csrf.disable()` toàn app | Business CSRF | Scope ACS exception, giữ CSRF elsewhere |
| `SameSite=None` không `Secure` | Browser reject cookie | HTTPS/Secure + CSRF review |
| NGINX log `$request_uri` | Lộ code/ticket qua URL query | Sanitized route category/status |
| Spring debug raw `SAMLResponse` | Rò NameID/groups/PII | Staging fixtures, redacted reason |
| Bật TRACE production vĩnh viễn | Secrets/PII leakage + chi phí | Time-boxed debug/ACL/retention |
| Dùng `curl -k` | Bỏ TLS server authentication | Sửa CA/hostname/cert |
| Tin `X-Request-ID` do browser đặt | Spoofing/correlation pollution | Generate at trusted edge |
| Cho redirect từ raw `RelayState` | Open redirect/phishing | Bind saved request + allowlist |
| `permitAll()` mọi endpoints khi loop | Authorization bypass | Sửa filter/session/entrypoint |
| Dùng email làm account key đa IdPs | Account collision | issuer+subject→stable local account |
| Log raw CAS ST/OIDC code để đối chiếu | Bearer secret replay/leak | Per-request/journey ID riêng |

Lưu ý: **HAR sanitized vẫn có thể chứa query `code/state/ticket`, form `SAMLResponse`, response bodies hoặc custom headers**. Kiểm toàn bộ nội dung trước khi chia sẻ, không tin tuyệt đối nhãn “sanitized”.

## 20. Câu hỏi kiểm tra có đáp án

**1.** Có bảy lần HTTP 302 trong một flow OIDC. Đây có phải redirect loop?

**Đáp án:** Không thể kết luận bằng số lần 302. Kiểm các URL categories, callback, authentication outcome, session và resource cuối; IdP MFA cũng có thể redirect nhiều lần.

**2.** Browser Network có OIDC callback nhưng không thấy `POST /token`. Có phải Spring không đổi code?

**Đáp án:** Token exchange là server-to-server; DevTools browser thường không thấy. Cần logs/traces phía Spring/OP.

**3.** IdP SAML trả trang 200, không thấy redirect. Có phải IdP không gửi Response?

**Đáp án:** Không nhất thiết. SAML HTTP-POST dùng HTML form tự submit. Xem POST ACS/Initiator/CSP/Console.

**4.** SAML ACS nhận POST 403. Có thể kết luận signature sai?

**Đáp án:** Không. Có thể CsrfFilter/WAF chặn trước. Kiểm edge upstream status và Spring filter/authentication failure reason.

**5.** Browser không gửi cookie ở ACS POST dù đã gửi lúc khởi tạo SAML. Lý do?

**Đáp án:** SameSite cross-site POST, Secure/Domain/Path, browser restrictions. Không bỏ InResponseTo để “cứu” login.

**6.** CAS callback có `ticket` nhưng browser không thấy ticket validation call. Tại sao?

**Đáp án:** CAS ticket validation do Spring server gửi tới CAS, nằm ở back-channel.

**7.** Kerberos lần đầu 401 có `WWW-Authenticate: Negotiate`. Là lỗi?

**Đáp án:** Có thể là challenge bình thường. Phải xem request tiếp theo có `Authorization: Negotiate` và GSS verification result.

**8.** App sau proxy sinh redirect URI HTTP internal, cần cho IdP chấp nhận URI này?

**Đáp án:** Không. Sửa HTTPS public canonical URL và trusted forwarded headers, ClientRegistration/ACS/service config.

**9.** Authentication success nhưng `/tenant/b` 403 đối với user tenant A. Có đúng?

**Đáp án:** Có thể là authorization chính xác. Không coi mọi 403 là SSO login failure.

**10.** HAR sanitized có thể chuyển trực tiếp cho đối tác?

**Đáp án:** Cần kiểm query/POST body/token/PII và redact; mặc định sanitized không phải chứng nhận an toàn tuyệt đối.

**11.** Một request ID ở proxy có tự xuyên qua IdP redirects không?

**Đáp án:** Không. Browser tạo requests mới ở origins khác. Muốn nối journey phải dùng server-side transaction correlation/IdP audit ID có kiểm soát.

**12.** Tại sao custom authentication success handler có thể gây “login rồi quay lại trang lạ”?

**Đáp án:** Nếu bỏ `SavedRequestAwareAuthenticationSuccessHandler` behavior, original requested URL không còn được phục hồi, dù authentication pass.

## 21. Checklist hoàn thành một ticket SSO

- [ ] Protocol và registrationId/issuer/tenant dự kiến được xác định, không đoán theo username/email.
- [ ] Có timeline UTC từ request protected ban đầu đến callback, back-channel, session và resource cuối.
- [ ] Có actor trả từng status: browser, proxy, IdP, Spring filter, OP token/CAS validator, business service.
- [ ] Đã bật Preserve log và thấy SAML HTML auto-submit/POST, không chỉ HTTP 302.
- [ ] Không coi SPNEGO 401 Negotiate challenge là lỗi nếu còn bước handshake tiếp.
- [ ] OIDC state/PKCE/nonce/redirect_uri và JWT iss/aud/signature/time được xác minh.
- [ ] OAuth2 token endpoint/JWKS/UserInfo back-channel được kiểm bằng server logs/traces.
- [ ] SAML signature/issuer/audience/destination/recipient/InResponseTo/time/replay được xác minh.
- [ ] CAS service URL, ST one-use và server ticket validation được kiểm.
- [ ] Reverse proxy canonical HTTPS host/path/Forwarded đúng; chặn spoofed headers.
- [ ] Callback/ACS match đúng Spring SecurityFilterChain, không bị API-only chain bắt nhầm.
- [ ] Cookie Set-Cookie/Cookie presence và Secure/HttpOnly/SameSite/Domain/Path được kiểm, không log value.
- [ ] Session store Redis/JDBC/multiple pods có save/read đúng, session fixation rotation được hiểu.
- [ ] SavedRequest/success/failure handler behavior được kiểm, không có open redirect/redirect loop.
- [ ] Authenticated user mapping dùng issuer+stable subject, business tenant authorization độc lập.
- [ ] HTTP 401/403/413/502/504 được định vị đúng tầng, không gán hết cho IdP.
- [ ] TRACE/DEBUG có approval/timebox, logs và HAR đã redact, không chứa credential artifacts.
- [ ] Staging tests gồm invalid state, wrong PKCE, invalid issuer/audience, SAML signature/recipient, CAS service, SPNEGO SPN, cookie missing, proxy loop và multi-pod.
- [ ] Có synthetic Java test hoặc automated diagnostic regression test không dựa vào raw user tokens.
- [ ] Có first failed stage + last known-good step + owner + sanitized evidence ID + cách khắc phục + regression pass.
- [ ] Sau khi sửa, đã test user **truy cập đúng tài nguyên được phép**, không chỉ nhìn thấy 200 login page.

**Kết luận:** Gỡ lỗi SSO là điều tra **một state machine phân tán**, không phải đếm redirects. OIDC token exchange nằm ở server, SAML HTTP-POST quay về bằng form chứ không nhất thiết 302, CAS service ticket được validate ở back-channel và SPNEGO 401 có thể hoàn toàn bình thường. Một phương pháp đáng tin kết nối browser timeline, edge upstream status, Spring filter/provider outcomes, session continuity và business authorization mà **không bỏ state/PKCE/signature/tenant kiểm tra và không phát tán secrets**.

## 22. Tài liệu chính thức

1. [Spring Security – OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): default OAuth2 authorization/callback endpoints, token/UserInfo callbacks.
2. [Spring Security – OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): Authorization Code flow và redirect-uri.
3. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): AuthnRequest, ACS, Browser Redirect/POST.
4. [Spring Security – SAML Response Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): OpenSAML signature/conditions.
5. [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, filter order, DEBUG/TRACE logging.
6. [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF protection và scope exclusions.
7. [Spring Security – Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): saved request, session/context behavior.
8. [Spring Security – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CasAuthenticationFilter/provider, service-ticket validation.
9. [Spring Security Kerberos](https://docs.spring.io/spring-security-kerberos/reference/): SPNEGO negotiation.
10. [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing/log correlation.
11. [Chrome DevTools – Network Reference](https://developer.chrome.com/docs/devtools/network/reference): Preserve log, Initiator, HAR sanitized export.
12. [MDN – Redirections](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Redirections): 302/303/307/308 semantics.
13. [MDN – Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): SameSite/Secure/HttpOnly.
14. [RFC 6749 – OAuth2](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code, state and token request.
15. [RFC 7636 – PKCE](https://www.rfc-editor.org/rfc/rfc7636): code_challenge/code_verifier.
16. [RFC 9700 – OAuth2 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): redirect URI, mix-up and transaction security.
17. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, iss/aud/nonce.
18. [OASIS – SAML2 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): Redirect/POST and RelayState.
19. [OASIS – SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Request/Response, Assertion validation.
20. [RFC 4559 – SPNEGO HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): Negotiate challenge.
21. [RFC 7239 – Forwarded](https://www.rfc-editor.org/rfc/rfc7239): forwarded protocol/host trust boundaries.
22. [W3C – Trace Context](https://www.w3.org/TR/trace-context/): traceparent/tracestate.
23. [OWASP – Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session cookies/session fixation.
24. [OWASP – Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): secrets redaction and event logging.
25. [OWASP – SAML Security](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signing trust and validated SAML assertions.
