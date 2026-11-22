# Phân biệt đăng nhập thành công với lỗi thiếu quyền sau đăng nhập

> **Chủ đề:** Spring Security – federation. **Nhóm:** Quan sát và gỡ lỗi. Bài Knowledge này giải thích vì sao **OIDC/SAML2/Kerberos/CAS login có thể thành công nhưng người dùng vẫn gặp 403 hoặc bị điều hướng tới trang báo không có quyền**; cách phân biệt authentication, authorization, HTTP entry point, CSRF, session, role mapping, tenant và business policy; và cách chẩn đoán bằng Spring Security logs, events, tests cùng ví dụ Java 17.

## 1. Tình huống điển hình

Alice đăng nhập qua IdP thành công:
1. Trình duyệt được redirect sang IdP.
2. Alice xác thực với IdP.
3. Trình duyệt quay về Spring ứng dụng.
4. Spring kiểm ID Token hoặc SAML Response và lưu Authentication.
5. UI hiển thị tên Alice.
6. Alice mở `/reports/2026`.
7. Server trả **403 Forbidden**.

Không có mâu thuẫn. **IdP đã chứng minh Alice là ai**, nhưng endpoint báo cáo yêu cầu `ROLE_REPORT_VIEW` hoặc membership tenant mà Alice chưa có. Cần kiểm **quyết định ở bước 6–7**, không vội kết luận SAML signature hay OIDC token sai.

Ngược lại, nếu callback bị lỗi chữ ký, sai issuer, nonce, audience hoặc ticket validation, Spring **chưa tạo Authentication hợp lệ**. Đó là lỗi **authentication**, không phải thiếu quyền sau login.

### 1.1. Kết luận cần nhớ

- **Authentication success:** hệ thống xác nhận được identity đáng tin, ví dụ `OidcUser`, `Saml2AuthenticatedPrincipal` hoặc Kerberos principal.
- **Authorization success:** identity đó được phép thực hiện hành động cụ thể với tài nguyên/tenant cụ thể.
- **Login success ≠ access granted to every endpoint.**
- **403 không phải lúc nào cũng là thiếu business role**: có thể là CSRF, CORS/preflight, method-security, tài nguyên thuộc tenant khác, hoặc gateway/proxy tự trả 403.
- **302 không chứng minh login thành công**: redirect có thể về IdP, login page, callback hoặc trang báo lỗi.
- **401 không phải lúc nào là IdP lỗi**: với HTTP API, một yêu cầu thiếu token/phiên cũng bị challenge 401 dù browser từng SSO thành công.
- Cần quan sát **cùng một request/trace**, trạng thái SecurityContext, authorities, policy được áp dụng và nơi sinh response.

## 2. Authentication và Authorization khác nhau

| Khía cạnh | Authentication | Authorization |
|---|---|---|
| Câu hỏi | Người gọi là ai? Chứng cứ danh tính hợp lệ? | Identity này được làm gì với resource này? |
| Đầu vào | Password, Kerberos ticket, SAML Assertion, OIDC authorization code/ID Token | Authentication, GrantedAuthorities, roles, scopes, tenant, resource owner, business policy |
| Thành phần Spring | AuthenticationManager, AuthenticationProvider, login filters | AuthorizationManager, AuthorizationFilter, @PreAuthorize, domain policy |
| Kết quả | Authenticated principal trong SecurityContext | Permit / deny cho một request/method/action |
| Lỗi điển hình | Bad credentials, invalid token/signature, wrong issuer/nonce, expired credential | Missing authority, wrong role prefix, inactive tenant membership, ownership denied |
| User-facing | Login error, redirect, 401/challenge | Thường 403; có thể khác do policy/handler |
| Sửa đúng | Sửa trusted IdP/credential/flow | Sửa approved role mapping/entitlement/rule hoặc policy |
| Sửa sai | Gán ROLE_ADMIN cho mọi người để login | Bỏ signature check hoặc permitAll vì gặp 403 |

**Phân quyền được tính cho từng tài nguyên.** Một user đã login có thể mở `/profile` nhưng bị từ chối ở `/admin`; đó là hoạt động bình thường của least privilege.

## 3. Spring Security Servlet filter chain: hai cổng riêng

Trong Servlet stack, request thường đi qua:

~~~text
Incoming HTTP request
   |
   v
FilterChainProxy / selected SecurityFilterChain
   |
   +-- SecurityContextHolderFilter
   |      Load context for this request (if available)
   |
   +-- CSRF / exploit protection filters
   |
   +-- Authentication filters
   |      OIDC/SAML/Basic/Bearer/Kerberos/form login ...
   |      May authenticate and save SecurityContext
   |
   +-- AnonymousAuthenticationFilter (if still anonymous)
   |
   +-- ExceptionTranslationFilter
   |      Bridges security exceptions to HTTP response
   |
   +-- AuthorizationFilter
   |      Evaluate requestMatchers / AuthorizationManager
   |      May throw AccessDeniedException
   |
   v
DispatcherServlet / Controller
   |
   +-- Method Security (@PreAuthorize, @PostAuthorize)
   +-- Domain authorization / tenant membership
   |
   v
HTTP response
~~~

Đây là sơ đồ **khái niệm**: thứ tự/những filters cụ thể phụ thuộc phiên bản, cơ chế và cấu hình. Không dùng sơ đồ thay cho việc xem SecurityFilterChain thật ở startup logs.

### 3.1. Trường hợp login thành công

Một SAML2/OIDC authentication filter xác minh credential, Authentication được xây dựng và (với session login) SecurityContext được lưu theo configured SecurityContextRepository. Browser có session cookie; redirect về saved request hoặc success URL. Các request sau đọc lại context từ session nếu policy có persistence.

**Success handler chỉ nói authentication flow vừa thành công.** Nó **không** kiểm trước tất cả các route/tenant/resource trong toàn ứng dụng.

### 3.2. Trường hợp authorization từ chối

`AuthorizationFilter`/`AuthorizationManager` hoặc method-security kiểm quyền, thấy thiếu `ROLE_REPORT_VIEW` hay tenant membership → deny, thường dẫn đến `AccessDeniedException`.

`ExceptionTranslationFilter` xử lý exception từ downstream:
- Nếu caller anonymous/chưa đủ authentication theo trust resolver, dùng `AuthenticationEntryPoint` để bắt đầu đăng nhập/challenge.
- Nếu đã authenticated ở mức phù hợp nhưng thiếu quyền, chuyển cho `AccessDeniedHandler`, thường tạo **403**.
- Nếu là `AuthenticationException`, tiếp tục/challenge authentication.
- Không phải mọi 403 đều đi qua filter này; ví dụ `CsrfFilter` có thể từ chối trước hoặc proxy trả lỗi.

Spring documentation cũng lưu ý remember-me authentication có thể được xem là insufficient trong một số luồng cần login đầy đủ; vì thế “có Authentication object” chưa luôn là fully authenticated.

## 4. HTTP 302, 401, 403: đọc theo ngữ cảnh

| Mã/hiện tượng | Khả năng thường gặp | Cách xác định |
|---|---|---|
| 302 sang IdP/login | Chưa authentication hoặc đang bắt đầu SSO | Xem Location và cookie/request state |
| 302 về saved URL sau SSO | Login callback có thể thành công | Kiểm SecurityContext và request tiếp theo |
| 200 từ callback/landing | UI được trả ra; **chưa đủ** khẳng định mọi quyền | Kiểm local Authentication và authorities |
| 401 Unauthorized | Thiếu/chưa đủ credential ở API | Xem WWW-Authenticate, token/session |
| 403 Forbidden sau login | Có principal nhưng thiếu quyền/tenant/resource | Xem accessDenied cause và matched policy |
| 403 trên POST khi GET được | CSRF token thiếu/sai hoặc method policy | Xem CSRF log/handler trước khi kết luận role |
| 403 trên OPTIONS/preflight | CORS/security gateway cấu hình sai | Xem Origin, CORS headers, filter chain |
| 404 sau redirect | Route không tồn tại hoặc cố ý che tài nguyên | Kiểm MVC mapping và product policy |
| 405 | HTTP method không được route hỗ trợ | Kiểm controller/request method |
| 500 khi tra quyền | Lỗi ứng dụng/entitlement provider | Xem sanitized exception và dependency |
| Lặp redirect về login | Session/cookie/correlation chưa được giữ | Kiểm SameSite, domain, HTTPS, RequestCache |
| Frontend hiển thị “access denied” nhưng API 200 | UI tự kiểm role hoặc cached state | So network/API và client route guard |

### 4.1. 401 và 403 trong browser SSO khác API

Với trang web chạy `oauth2Login()` hay `saml2Login()`:
- Người chưa login thường **302** sang entrypoint/IdP thay vì hiển thị raw 401.
- Người đã login nhưng thiếu authority thường nhận **403** theo AccessDeniedHandler.
- Nếu session mất giữa redirect và resource request, browser có thể lại **302** sang login.
- Với REST resource server, `BearerTokenAuthenticationEntryPoint` thường trả **401** cho token thiếu/sai; `BearerTokenAccessDeniedHandler` thường xử lý thiếu scope/authority thành **403** theo Bearer protocol policy.
- `WWW-Authenticate` hữu ích để phân biệt `invalid_token` và `insufficient_scope`, nhưng output cụ thể tùy config/framework.

**Không ép mọi API hoặc browser login dùng một handler/mã HTTP cố định.** Cần xác định loại SecurityFilterChain, authentication mechanism và failure handler thực tế.

### 4.2. 302 có thể che lỗi thiếu quyền

RequestCache lưu URL ban đầu, ví dụ `/admin`. Sau khi SSO thành công, success handler redirect về URL được lưu:
~~~text
GET /admin
  -> redirect to IdP (anonymous)
  -> user logs in
  -> IdP callback passes
  -> redirect to /admin (saved request)
  -> 403 because ROLE_ADMIN missing
~~~

Người dùng sẽ nói “login bị lỗi 403”, nhưng log cho thấy **login đã success**, lỗi xảy ra ở request sau redirect. Hãy theo dấu từng HTTP request, không chỉ trang cuối cùng.

## 5. Decision tree khi người dùng báo “đăng nhập được rồi nhưng bị chặn”

~~~text
User says "login succeeded, but access denied"
                |
                v
Was SSO callback/authentication successful?
                |
           +----+----+
           |         |
          NO        YES
           |         |
  Check IdP token/   v
  signature, state,  Does current request have
  nonce, audience,   a persisted Authentication?
  session exchange        |
                    +-----+------+
                    |            |
                   NO           YES
                    |            |
           Session/cookie/      v
           wrong chain/     Which control denied?
           token missing       |
                           +----+----+---------------+
                           |         |               |
                       URL rule   Method rule     CSRF/tenant
                           |         |               |
                      authorities  @PreAuthorize   check policy,
                      & matchers   & proxy         token/resource
                           \         |              /
                            \--------+-------------/
                                     |
                          Correct policy or approved
                          role mapping; do not bypass
                          authentication/authorization
~~~

**Bước đầu tiên là lấy timeline**, gồm callback response, next request URL/method, status, handler, SecurityContext trong request đang lỗi, and matched security rule.

## 6. Tìm bằng chứng login thật sự thành công

Một chuỗi chứng cứ tốt:
1. IdP redirect/callback được nhận ở đúng endpoint.
2. Spring AuthenticationProvider xác minh giao thức và credential.
3. Authentication thành công có `isAuthenticated()=true` và **không phải AnonymousAuthenticationToken**.
4. Principal có identity key ổn định từ đúng IdP realm/issuer.
5. Với session-based app, SecurityContext được lưu và đọc lại ở request sau.
6. User ID/local account mapping đã được duyệt.
7. Có event/log thành công hoặc authentication success handler execution.
8. **Có thể** đọc authorities tại request bị từ chối, nhưng không log nhạy cảm toàn bộ.

**Cẩn thận:** `AnonymousAuthenticationToken.isAuthenticated()` có thể trả true. Vì thế điều kiện `auth != null && auth.isAuthenticated()` **không đủ** để kết luận người dùng SSO đã login thật. Dùng trust resolver, authorization expression `isAuthenticated()` / `isFullyAuthenticated()` theo Spring policy và phân biệt authentication implementation.

### 6.1. SecurityContext của mỗi request

`SecurityContextHolder` thường gắn với thread/request. Sau callback, nếu bạn mở một request khác hoặc chạy asynchronous task, không mặc nhiên dùng được context từ thread callback. Với session login, repository cần lưu/đọc context; với stateless JWT API, mỗi request cần bearer token.

**Nếu callback pass nhưng request tiếp theo anonymous**, ưu tiên kiểm:
- Session cookie có được set/được trình duyệt gửi lại không?
- Cookie Path/Domain/SameSite/Secure khớp origin/HTTPS/redirect không?
- Spring Session/Redis và load balancer có chia sẻ state đúng không?
- Có `SessionCreationPolicy.STATELESS` vô ý trong browser SSO chain không?
- Có nhiều `SecurityFilterChain` không, request nào match chain nào?
- Có custom success handler/repository quên save context trong version sử dụng không?
- Reverse proxy/ingress có làm sai forwarded host/scheme không?
- Frontend gọi API trên origin khác mà không gửi cookies/credentials?
- Logout/session expiry diễn ra giữa hai requests?
- Có stale browser tab hoặc third-party cookie restrictions?

Đừng sửa bằng cách bỏ mọi `authenticated()` guard.

## 7. Authentication object có gì và không có gì?

Một Authentication thành công cung cấp:
- `getPrincipal()`: người dùng đã được xác minh, type tùy protocol.
- `getAuthorities()`: authorities đã được map/tra tại thời điểm tạo Authentication.
- `getName()`: một tên đại diện, không luôn là stable account ID.
- `isAuthenticated()`: một flag của Authentication; phải loại trừ anonymous/remember-me theo policy.
- `getDetails()`: thông tin request/context tùy implementation; **không** được tin như role nguồn.

**Không bảo đảm**:
- User có `ROLE_ADMIN`.
- User thuộc tenant cần truy cập.
- Local account còn active ngay hôm nay.
- Tất cả SAML/OIDC claims đã map thành application roles.
- Authorities được cập nhật ngay khi AD/IAM thay đổi.
- Resource owner trùng với người đang login.

### 7.1. Đọc authorities chính xác

Ví dụ authorities:
~~~text
OIDC_USER
SCOPE_openid
SCOPE_profile
ROLE_REPORT_VIEW
~~~

Nó **không** chứa `ROLE_REPORT_APPROVE`. Một endpoint yêu cầu `hasAuthority("ROLE_REPORT_APPROVE")` phải bị từ chối dù Alice có `OIDC_USER` và có scope `profile`.

### 7.2. isAuthenticated không phải access decision

Một ứng dụng chỉ kiểm `isAuthenticated()` rồi cho truy cập mọi tenant sẽ bỏ qua least privilege. Conversely, một application thiếu role mapping có thể 403 với users hợp lệ. **Authorization phải được quyết định theo hành động và tài nguyên**, không dựa trên “đã login”.

## 8. Vai trò, GrantedAuthority và lỗi prefix

Spring Security authorization rules hay gặp:

~~~java
.requestMatchers("/reports/**")
    .hasAuthority("ROLE_REPORT_VIEW")

.requestMatchers("/admin/**")
    .hasRole("ADMIN")
~~~

Với role prefix mặc định:
- `hasAuthority("ROLE_REPORT_VIEW")` so chính xác chuỗi authority.
- `hasRole("ADMIN")` thường kiểm `ROLE_ADMIN`.
- Nếu bạn đưa `hasRole("ROLE_ADMIN")` khi prefix mặc định được áp, có thể gây lỗi hoặc cấu hình không nhất quán. Nên dùng `hasAuthority("ROLE_ADMIN")` nếu muốn kiểm chuỗi đầy đủ.
- `ROLE_Report_View` khác `ROLE_REPORT_VIEW` về chữ hoa/thường.
- `SCOPE_admin` không tương đương `ROLE_ADMIN`.
- `"GROUP_FINANCE"` từ IdP không tự tương đương `ROLE_FINANCE_VIEW`.

### 8.1. Đọc chính sách được áp vào URL

Các ví dụ:
~~~text
GET /reports/2026
Rule: hasAuthority("ROLE_REPORT_VIEW")
Actual: [ROLE_USER, SCOPE_profile]
Outcome: DENY

GET /reports/2026
Rule: hasAuthority("ROLE_REPORT_VIEW")
Actual: [ROLE_USER, ROLE_REPORT_VIEW]
Outcome: Potentially PERMIT at URL layer

GET /tenants/team-b/reports/42
Rule: hasAuthority("ROLE_REPORT_VIEW")
Actual: [ROLE_REPORT_VIEW]
Additional business check: Alice member of team-a only
Outcome: DENY at tenant/resource layer
~~~

“Potentially PERMIT” nghĩa là URL-level rule pass; method/domain-level policies vẫn có thể từ chối.

### 8.2. Role hierarchy và permission naming

Nếu project dùng `RoleHierarchy`, ví dụ ADMIN bao hàm REPORT_VIEW, phải cấu hình và kiểm behavior cho cùng AuthorizationManager/method-security expressions. Không mặc định mọi nơi hiểu role hierarchy hoặc “ADMIN” tự có mọi authorities.

Với domain permissions, có thể dùng `REPORT_READ`, `invoice:approve` hoặc `ROLE_REPORT_VIEW`. Chọn một naming convention được version-control; tests xác nhận matcher và mapper cùng dùng convention đó.

### 8.3. Không tự cấp role để che lỗi

Khi Alice 403, không làm:
~~~java
// KHÔNG AN TOÀN: mỗi login đều thành admin.
authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
~~~

Hướng sửa đúng: tìm nguồn entitlements, issuer/tenant trust, user account mapping và allowlisted group-to-role; chỉ cấp quyền thật sự đã được phê duyệt.

## 9. OIDC/OAuth2 Login: có user nhưng không có app role

Ở Spring `oauth2Login()`:
- Spring xác minh Authorization Code flow/ID Token theo protocol.
- Authenticated principal có thể là `OidcUser`.
- `OidcUserAuthority`/`OIDC_USER` cho biết identity/claims đã được xử lý.
- `SCOPE_...` từ scopes dùng khi thích hợp; đó không phải các app roles tùy ý.
- `OAuth2AuthenticationToken.getAuthorities()` được dùng ở HTTP/method authorization.
- Ứng dụng có thể dùng `GrantedAuthoritiesMapper` hoặc delegated `OidcUserService` để map trusted IdP claims/groups sang app authorities.

### 9.1. Ví dụ root cause

~~~text
IdP login status: SUCCESS
iss: https://login.example.org/realm/staff
sub: stable-subject-123
IdP claim: groups=["ReportReaders"]
Local user mapping: alice / active
Spring authorities: [OIDC_USER, SCOPE_openid, SCOPE_profile]
URL rule: hasAuthority("ROLE_REPORT_VIEW")
Decision: DENY
~~~

Nếu `groups` claim chưa được map, Spring không tự biến nó thành `ROLE_REPORT_VIEW`. Cần mapper theo stable group IDs và trusted issuer/tenant contract, hoặc lấy entitlements từ approved IAM/DB.

### 9.2. Issuer-subject identity mapping

Trong OIDC, cặp `iss + sub` là nguồn định danh ổn định trong scope của provider. Email hoặc `preferred_username` không đủ cho tự động link một account nhạy cảm. Một OIDC login thành công có thể đi tới **local account chưa provisioned/disabled**, khi đó business onboarding/authorization từ chối là đúng.

### 9.3. OAuth2 login không phải OAuth2 resource server

`oauth2Login()`: trình duyệt tương tác, session, IdP redirects.

`oauth2ResourceServer().jwt()`: API nhận Bearer access token từng request, kiểm signature/issuer/audience/scopes theo cấu hình. Một browser có OIDC session không tự làm request JavaScript tới REST API được xác thực bằng bearer token nếu không gửi token hợp lệ; một session cookie không tự thay access token.

Phân loại chính xác SecurityFilterChain trước khi chẩn đoán 401/403.

## 10. SAML 2.0 Login: assertion hợp lệ vẫn thiếu quyền

Với `saml2Login()`, Spring Security xác minh SAML Response/Assertion signature, Issuer, Audience, Destination, SubjectConfirmation, Conditions, InResponseTo theo provider/profile. Khi thành công, `Saml2Authentication` và `Saml2AuthenticatedPrincipal` thể hiện danh tính đã xác minh.

Sau đó:
- `Saml2AuthenticatedPrincipal.getName()` không tự là local user ID.
- `getAttributes()` chứa SAML attributes theo protocol/provider mapping; không tự là `ROLE_ADMIN`.
- `Saml2Authentication.getAuthorities()` phản ánh authorities đã gán theo cấu hình.
- App cần local account linking, role/group mapping và tenant/resource authorization.
- XSW signature wrapping hoặc invalid assertion là **authentication failure**; thiếu application authority sau verified assertion là **authorization failure**.

### 10.1. Ví dụ

~~~text
SAML Issuer: urn:example:saml:idp:staff
Signed Assertion: verified
NameID: alice-staff-001
Attributes: department=Finance, groups=["ReadOnlyReports"]
Local user: 1001, active
Mapped authority: ROLE_REPORT_VIEW
Endpoint /finance/approve: requires ROLE_FINANCE_APPROVE
HTTP result: 403 after successful SAML login
~~~

Không sửa bằng cách vô hiệu hóa signature verification hoặc chấp nhận mọi `groups` raw. Kiểm policy mapping; nếu Alice không được duyệt quyền approve thì 403 là kết quả đúng.

### 10.2. SAML logout, assertion expiry và phiên ứng dụng

SAML Assertion có thời gian hiệu lực, nhưng Spring HttpSession có vòng đời khác. User đã được xác minh tại login có thể giữ authority snapshot cho đến khi session hết hạn hoặc policy recheck; group bị gỡ ở IdP không tự hủy mọi sessions. SAML Single Logout cần thiết kế riêng, không mặc định mọi local session được revoke nhờ assertion validity.

## 11. Kerberos, LDAP và CAS: quyền vẫn là vấn đề riêng

**Kerberos/SPNEGO:** GSS ticket validator xác minh principal `alice@EXAMPLE.ORG`; `KerberosServiceAuthenticationProvider` có thể gọi `UserDetailsService` để tải local account/GrantedAuthorities. Nếu mapping trả rỗng hoặc thiếu group, login có thể hợp lệ nhưng route có role requirement sẽ 403.

**LDAP direct authentication:** Bind username/password đúng chứng minh credential; `LdapAuthoritiesPopulator`/database rule mapping xác định authorities. Tìm được LDAP entry không phải proof user đã login; bind thành công cũng không cấp mọi quyền.

**CAS:** CAS service ticket validation chứng minh principal từ CAS server; app vẫn cần map local account/roles/tenant. Một user CAS authenticated chưa tự là admin trên portal.

**Cross-realm/tenant:** Cùng short username Alice ở hai Kerberos realms hoặc cùng email từ hai OIDC issuers **không** chứng minh cùng local user. False 403 có thể đến từ thiếu identity link; còn 403 đúng có thể ngăn cross-tenant takeover.

## 12. Method security: URL-level pass nhưng service từ chối

Spring Security hỗ trợ `@PreAuthorize`/`@PostAuthorize` khi bật `@EnableMethodSecurity`. Một request có thể pass URL rule `authenticated()`, vào controller, rồi bị method interceptor deny vì thiếu `ROLE_REPORT_VIEW`.

Ví dụ:
~~~java
@PreAuthorize("hasAuthority('ROLE_REPORT_VIEW')")
public ReportDto loadReport(String reportId) {
    return reportService.load(reportId);
}
~~~

Đây là **method fragment**: types, imports, domain service implementation do dự án cung cấp. Điều cần học là thứ tự:
1. URL-level AuthorizationManager có thể cho phép.
2. Method invocation đi qua Spring AOP interceptor.
3. `@PreAuthorize` kiểm authorities.
4. Thiếu role → `AccessDeniedException`/authorization-denied.
5. Trên luồng HTTP, ExceptionTranslationFilter có thể chuyển thành 403 theo handler.
6. Nếu method chạy ngoài HTTP/request filter chain, exception phải được ứng dụng xử lý ở boundary khác.

### 12.1. Bật method security

~~~java
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Đây là Spring application class hợp lệ với dependencies tương ứng. Spring Boot starter security **không tự bật mọi method-level annotations** nếu không có configuration thích hợp.

### 12.2. Self-invocation và AOP proxy

Một method trong cùng bean tự gọi method gắn `@PreAuthorize` có thể bỏ qua Spring AOP proxy. Hệ quả thường là **thiếu enforcement** chứ không phải 403 thiếu quyền. Khi debug phải kiểm method thực sự đi qua proxy, các interfaces/proxy visibility và async/thread contexts. Không dựa vào một annotation chưa được intercept để bảo vệ business resource.

### 12.3. Deny từ domain service

Ví dụ route pass URL-level và method role-level nhưng business service kiểm user chỉ thuộc tenant A, trong khi report thuộc tenant B. Domain service có thể ném `AccessDeniedException` hoặc trả business denial theo documented API contract. Cần trace nguyên nhân và resource ID đã được sanitize; không đánh đồng mọi 403 là thiếu `ROLE_REPORT_VIEW`.

## 13. CSRF 403 không phải thiếu app role

Spring `CsrfFilter` bảo vệ state-changing requests khi session cookies mang credentials. Một tình huống:
~~~text
GET  /reports       -> 200 (authenticated + authorized)
POST /reports/export -> 403 (CSRF token missing)
~~~

Nếu log cho thấy `InvalidCsrfTokenException` hoặc `MissingCsrfTokenException`, sửa:
- UI/form gửi CSRF token đúng.
- API client nhận/gửi token theo configured repository.
- Cookie/headers/SameSite đúng.
- Nếu API hoàn toàn stateless dùng Bearer token và không dựa cookie, CSRF policy có thể khác theo threat model.
- Chỉ `csrf.ignoringRequestMatchers(...)` cho các endpoints giao thức thật sự cần exemption theo contract (ví dụ SAML ACS do Spring quản lý), **không `csrf.disable()` toàn hệ thống** vì một POST bị 403.

**Không gán thêm ROLE_ADMIN** để chữa CSRF. Role mapper không giải được thiếu token.

## 14. CORS/Preflight, proxy và nguồn trả 403

Một browser SPA có thể gửi `OPTIONS /api/reports` trước GET có Authorization header. Nếu CORS/security proxy từ chối OPTIONS, frontend có thể hiển thị “Forbidden” dù end-user session/roles hợp lệ.

Kiểm:
- HTTP method là OPTIONS hay GET/POST?
- Origin và Access-Control-Request-Headers có được allowlist?
- Filter chain đã bật `cors()` và CORS configuration đúng?
- Authentication/Authorization có áp sai vào preflight?
- 403 do Spring app hay NGINX/WAF/API gateway?
- Có internal ingress header `X-Forwarded-Proto/Host` ảnh hưởng redirect/cookie?
- API gọi đúng host/path và có gửi cookies/Bearer token?

**Nguồn trả 403 quan trọng hơn mã 403 một mình.** Nếu request không đến Spring controller/filter chain, chỉnh Spring roles có thể hoàn toàn không có tác dụng.

## 15. RequestCache và success redirect: truy nguyên đúng request

Một login success handler có thể redirect:
- Saved original URL.
- Configured default success URL.
- URL đã được request cache.
- Frontend landing page.

Nếu saved URL yêu cầu nhiều quyền hơn Authentication được cấp, user thấy 403 ngay sau callback. Hãy ghi sanitized diagnostics:
~~~text
traceId=abc
event=authentication_success
mechanism=OIDC
registration=staff
principalIdHash=...
redirectTarget=/reports/review

traceId=def
event=authorization_denied
method=GET
path=/reports/review
requiredAuthority=ROLE_REPORT_APPROVE
availableAuthorityCategories=[OIDC_USER,SCOPE_profile,ROLE_REPORT_VIEW]
decision=DENY
status=403
~~~

Đây là **log mẫu**, không phải một log format mặc định của Spring. HTTP trace IDs có thể cần truyền qua session/redirect correlation riêng nếu muốn nối hai requests; ID của hai requests có thể khác.

### 15.1. Tránh open redirect

Không để client cung cấp arbitrary success URL rồi ứng dụng redirect không kiểm. Với OAuth2/OIDC/SAML, state/RelayState/request cache phải được xử lý an toàn; điều hướng hậu đăng nhập nên allowlist nội bộ. Một login success redirect không chứng minh URL đích được authorize.

## 16. Java 17 standalone: mô hình quyết định quyền sau login

Ví dụ độc lập này chạy với **JDK 17+, không cần Spring hay IdP**. Nó giả định một authentication pipeline **đã** xác minh credentials và tạo `AuthSnapshot` đáng tin. Mã cố ý tách authentication state, role, tenant và yêu cầu fully authenticated.

Tệp `PostLoginDecisionDemo.java`:

~~~java
import java.util.Set;

public class PostLoginDecisionDemo {

    record AuthSnapshot(
            boolean hasTrustedLogin,
            boolean fullAuthentication,
            Set<String> authorities,
            Set<String> tenants) {
    }

    enum Decision {
        START_AUTHENTICATION,
        REQUIRE_FULL_LOGIN,
        FORBIDDEN_MISSING_AUTHORITY,
        FORBIDDEN_TENANT,
        ALLOW
    }

    static Decision decide(
            AuthSnapshot auth,
            String requiredAuthority,
            String resourceTenant,
            boolean requireFullLogin) {

        if (auth == null || !auth.hasTrustedLogin()) {
            return Decision.START_AUTHENTICATION;
        }

        if (requireFullLogin && !auth.fullAuthentication()) {
            return Decision.REQUIRE_FULL_LOGIN;
        }

        if (!auth.authorities().contains(requiredAuthority)) {
            return Decision.FORBIDDEN_MISSING_AUTHORITY;
        }

        if (!auth.tenants().contains(resourceTenant)) {
            return Decision.FORBIDDEN_TENANT;
        }

        return Decision.ALLOW;
    }

    public static void main(String[] args) {
        AuthSnapshot alice = new AuthSnapshot(
                true, true,
                Set.of("OIDC_USER", "SCOPE_profile", "ROLE_REPORT_VIEW"),
                Set.of("tenant-a"));

        AuthSnapshot remembered = new AuthSnapshot(
                true, false,
                Set.of("ROLE_REPORT_VIEW"),
                Set.of("tenant-a"));

        System.out.println("anonymous=" +
                decide(null, "ROLE_REPORT_VIEW", "tenant-a", false));

        System.out.println("read=" +
                decide(alice, "ROLE_REPORT_VIEW", "tenant-a", false));

        System.out.println("approve=" +
                decide(alice, "ROLE_REPORT_APPROVE", "tenant-a", false));

        System.out.println("other-tenant=" +
                decide(alice, "ROLE_REPORT_VIEW", "tenant-b", false));

        System.out.println("remembered=" +
                decide(remembered, "ROLE_REPORT_VIEW", "tenant-a", true));

        System.out.println("scope-is-not-role=" +
                decide(alice, "ROLE_ADMIN", "tenant-a", false));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PostLoginDecisionDemo.java
java PostLoginDecisionDemo
~~~

**Stdout chính xác:**

~~~text
anonymous=START_AUTHENTICATION
read=ALLOW
approve=FORBIDDEN_MISSING_AUTHORITY
other-tenant=FORBIDDEN_TENANT
remembered=REQUIRE_FULL_LOGIN
scope-is-not-role=FORBIDDEN_MISSING_AUTHORITY
~~~

**Diễn giải:** Alice đã login nên đọc report tenant-a được phép, nhưng không thể approve hoặc đọc tenant-b chỉ vì có `ROLE_REPORT_VIEW`. `SCOPE_profile` không cấp ROLE_ADMIN. Remember-me/snapshot không thỏa chính sách fully-authenticated sẽ yêu cầu bước authentication mạnh hơn.

**Giới hạn:** Đây là pure decision model, không xác minh OIDC/SAML/Kerberos, không implement Spring AuthenticationTrustResolver hoặc real tenant lookup. Hai booleans trong record **không được nhận trực tiếp từ browser**. Trong production, Authentication và tenant entitlements phải đến từ trusted IdP/DB/policy service; không dùng decision model này thay security filters.

## 17. Java 17 standalone: phân biệt login event với resource decision

Ví dụ thứ hai tạo một timeline có sự kiện login success và denial trên resource sau đó. Mục tiêu là minh họa tại sao **một event success không đồng nghĩa tất cả requests success**.

Tệp `AuthTimelineDemo.java`:

~~~java
import java.util.List;

public class AuthTimelineDemo {

    record SecurityEvent(
            String requestId,
            String phase,
            String result) {
    }

    public static void main(String[] args) {
        List<SecurityEvent> events = List.of(
                new SecurityEvent("req-101", "AUTHENTICATION",
                        "SUCCESS:OIDC"),
                new SecurityEvent("req-102", "AUTHORIZATION",
                        "DENY:ROLE_REPORT_APPROVE"),
                new SecurityEvent("req-103", "AUTHORIZATION",
                        "ALLOW:ROLE_REPORT_VIEW"));

        for (SecurityEvent event : events) {
            System.out.println(
                    event.requestId() + " " +
                    event.phase() + " " + event.result());
        }
    }
}
~~~

Lệnh:

~~~bash
javac AuthTimelineDemo.java
java AuthTimelineDemo
~~~

**Stdout chính xác:**

~~~text
req-101 AUTHENTICATION SUCCESS:OIDC
req-102 AUTHORIZATION DENY:ROLE_REPORT_APPROVE
req-103 AUTHORIZATION ALLOW:ROLE_REPORT_VIEW
~~~

Cả ba events có thể thuộc cùng browser session nhưng là các requests khác nhau. Mã này không đọc Spring logs thật; đó là minh họa concept về event correlation.

## 18. Spring Security Java 17: HTTP access rules có chủ đích

Ví dụ Spring Boot Servlet dùng OIDC login cho browser, Method Security cho business service và explicit access-denied handler để phân biệt lỗi thiếu quyền. Muốn dùng SAML2 thay OIDC, cấu hình `saml2Login(...)` tương ứng với trusted RelyingPartyRegistration và giữ nguyên tinh thần URL/method security.

Tệp `src/main/java/com/example/security/PortalSecurity.java`:

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class PortalSecurity {

    @Bean
    SecurityFilterChain portalChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/reports/view/**")
                    .hasAuthority("ROLE_REPORT_VIEW")
                .requestMatchers("/reports/approve/**")
                    .hasAuthority("ROLE_REPORT_APPROVE")
                .requestMatchers("/admin/**")
                    .hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .exceptionHandling(ex -> ex
                .accessDeniedHandler((request, response, denied) ->
                    response.sendError(
                        HttpServletResponse.SC_FORBIDDEN)))
            .build();
    }
}
~~~

**Lưu ý chạy thực:** Code là class Spring configuration, cần Spring Security/Boot dependencies và OIDC ClientRegistration (issuer/client ID/client secret/redirect URI) đã cấu hình. Trong production, không log access token, ID token, secrets hay raw principal attributes. Authentication entry point của browser login vẫn do `oauth2Login` thiết lập; explicit accessDeniedHandler chỉ xử lý denies phù hợp, không tự biến authentication failures thành 403.

### 18.1. Thay flow bằng SAML2

Khi dùng SAML, thay:
~~~java
.oauth2Login(Customizer.withDefaults())
~~~
bằng:
~~~java
.saml2Login(Customizer.withDefaults())
~~~

Đây là **đoạn thay thế trong cùng Spring config**, cần `spring-security-saml2-service-provider` và trusted relying-party registration. Không vừa bật/test nhiều cơ chế mà thiếu plan về entrypoint, request matching và session policy.

### 18.2. Spring Boot dependencies

POM fragment trong dự án có Spring Boot dependency management:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Với SAML2 sử dụng module `spring-security-saml2-service-provider` theo version tương thích thay cho OIDC-only dependency. Đây không phải full POM chạy độc lập; đúng BOM/provider/metadata config do dự án quyết định.

### 18.3. Vì sao không disable filters?

Khi callback success nhưng 403, đừng đổi `anyRequest().permitAll()` hoặc `csrf.disable()` chỉ để xóa lỗi. Kỹ thuật đúng là xác định root cause rồi map approved authorities, sửa path matcher/tenant policy hoặc sửa CSRF flow. Bỏ enforcement là authentication/authorization bypass.

## 19. Debug-only endpoint: xem Authentication tại request hiện tại

Chỉ trong **profile dev/test**, một endpoint giới hạn quyền có thể cho biết Authentication type và authority labels. Không expose endpoint chẩn đoán raw claims ở production.

Tệp `src/main/java/com/example/diagnostics/AuthDiagnostics.java`:

~~~java
package com.example.diagnostics;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("dev")
@RestController
public class AuthDiagnostics {

    @GetMapping("/internal/dev/auth-state")
    public Map<String, Object> state(Authentication authentication) {
        Map<String, Object> result = new LinkedHashMap<>();

        if (authentication == null) {
            result.put("present", false);
            return result;
        }

        result.put("present", true);
        result.put("authenticationType",
                authentication.getClass().getSimpleName());
        result.put("isAuthenticatedFlag",
                authentication.isAuthenticated());
        result.put("principalType",
                authentication.getPrincipal() == null
                    ? "null"
                    : authentication.getPrincipal()
                        .getClass().getSimpleName());
        result.put("authorityLabels",
                authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
        return result;
    }
}
~~~

**Các cảnh báo cần tuân thủ:**
- Đoạn mã dùng Spring MVC; không phải standalone `javac` app.
- @Profile("dev") chỉ loại bean khi profile khác; **chưa phải authorization guard**. Thêm một URL rule yêu cầu admin cho route này trong dev và giới hạn network. Không phát hành endpoint trong public production.
- Không trả `authentication.getCredentials()`, raw `OidcIdToken`, SAMLResponse, user claims hoặc session cookie.
- `isAuthenticatedFlag=true` có thể cũng xuất hiện với AnonymousAuthenticationToken; phải kiểm `authenticationType` và authentication trust resolver.
- Authority labels có thể tiết lộ cấu trúc phân quyền; đừng log/echo chúng cho end users ngoài môi trường kiểm soát.
- Nếu `/internal/dev/auth-state` bị chính rule `anyRequest().authenticated()` chặn thì không thể dùng để debug anonymous; trong dev nên dùng request/trace logs an toàn, không tạo public permitAll diagnostic endpoint.

### 19.1. Gắn route debug với admin authority

Trong dev, thêm rule **trước `anyRequest().authenticated()`**:
~~~java
.requestMatchers("/internal/dev/**")
    .hasAuthority("ROLE_SECURITY_DIAGNOSTICS")
~~~

Đây là fragment, không phải cấu hình đầy đủ. Diagnostic endpoint chỉ phục vụ tài khoản đã được approved; nếu đang debug user bị 403, dùng server-side correlation/trace thay vì gán user quyền diagnostics.

## 20. Logging đúng lớp trong Spring Security

Ví dụ chỉ bật debug tạm thời ở môi trường test/dev:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.access: DEBUG
    org.springframework.security.authorization: DEBUG
    org.springframework.security.oauth2: DEBUG
~~~

Tùy Spring Security version và module, các logger names/sự kiện cụ thể có thể khác. Không mặc định mỗi 403 sẽ có log đã nêu required role. Khi cần sâu hơn, dùng TRACE **ngắn hạn trên hệ test**, vì trace có thể chứa request/subject details.

**Không bật DEBUG/TRACE bảo mật vô hạn ở production.** Chặn log credentials, raw Bearer tokens, `Authorization: Negotiate`, SAMLResponse, ID Token/refresh token, LDAP passwords, cookies, secrets và nhạy cảm PII.

### 20.1. Dấu hiệu trong logs

Một chuỗi event hữu ích:
~~~text
[request-101] authentication_result=SUCCESS
  flow=OIDC registration=staff
  local_user_link_status=ACTIVE

[request-102] security_context=AUTHENTICATED
  auth_type=OAuth2AuthenticationToken
  url_rule=ROLE_REPORT_APPROVE
  authorization_result=DENIED
  denial_stage=HTTP_AUTHORIZATION
  response_status=403

[request-103] security_context=AUTHENTICATED
  url_rule=ROLE_REPORT_VIEW
  authorization_result=GRANTED
  response_status=200
~~~

**Đây là logs được thiết kế để minh họa**, không phải output mặc định từ Spring. Bạn cần instrumentation để ghi policy/decision mà không chứa secrets.

### 20.2. Khi nào log báo SUCCESS nhưng thực ra login chưa persistent?

Authentication success event hoặc success handler execution có thể xảy ra ngay trong callback request. Nếu SecurityContextRepository/session chưa lưu đúng hoặc browser không gửi cookie, request sau vẫn anonymous. Vì vậy cần log **authn event và auth state tại request bị deny** theo các correlation IDs phù hợp.

## 21. Authentication events vs authorization events

Spring Security có thể phát các events:
- `AuthenticationSuccessEvent`.
- `AbstractAuthenticationFailureEvent` và subclasses.
- `AuthorizationDeniedEvent` khi được cấu hình/phát ở authorization layer.
- `AuthorizationGrantedEvent` khi publisher/implementation hỗ trợ và được cấu hình.

**Quan trọng:** Event publisher, provider mechanisms và handler wiring khác nhau theo version/flow. Không mặc định mọi SAML/OIDC integration tự phát cùng event ở cùng thời điểm. Test listener trên phiên bản production thực tế và đo lần logout/login/reauth đúng.

### 21.1. AuthenticationEventPublisher bean

Spring Security documentation ví dụ:

~~~java
package com.example.monitoring;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;

@Configuration
public class AuthenticationEventConfiguration {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new DefaultAuthenticationEventPublisher(publisher);
    }
}
~~~

Đây là Spring class với dependency; nó cấu hình cơ chế publish cho các AuthenticationManager/providers dùng publisher theo kiến trúc. Không khẳng định mọi thất bại ở filter tầng HTTP hoặc gateway đều phát cùng event.

### 21.2. Listen và phân loại

~~~java
package com.example.monitoring;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;

@Component
public class AuthenticationAuditListener {

    @EventListener
    public void success(AuthenticationSuccessEvent event) {
        // Ghi metric/authn success với tags low-cardinality.
        // Không ghi credentials, tokens hoặc toàn bộ principal.
    }

    @EventListener
    public void failure(AbstractAuthenticationFailureEvent event) {
        // Ghi loại lỗi đã sanitize; không leak username cho client.
    }
}
~~~

Các comments là mục tiêu instrumentation; project cần logger/metrics implementation cụ thể. **Không viết event handler tự thay đổi Authentication trong quá trình ghi log.**

### 21.3. AuthorizationDeniedEvent khác AuthenticationFailureEvent

Một user có thể có:
~~~text
AuthenticationSuccessEvent(user=Alice)
AuthorizationDeniedEvent(resource=/reports/approve)
AuthorizationGrantedEvent(resource=/reports/view)
~~~

Không có contradiction: login thành công, approve deny, view allow. Khi cấu hình publisher, ưu tiên log denial stage và policy rule; **không** dùng authn_failure counter cho business authorization denials.

### 21.4. Micrometer/Observability

Spring Security có integration với Micrometer Observation trong các phiên bản hỗ trợ. Tracing nên liên kết:
- HTTP request ID/span.
- Authentication type/flow (giới hạn tags).
- Authorization decision layer.
- Denial reason category.
- Request path theo **route template** thay vì raw path có IDs.
- SP registration/IdP category theo allowlist có cardinality kiểm soát.
- Latency của role/IAM lookup.

Không gắn raw `sub`, email, NameID, access token, dynamic tenant ID hoặc full resource IDs vào high-cardinality metric tags. Chúng có thể gây bùng nổ metrics và lộ PII. Dùng sanitized audit log riêng khi nghiệp vụ có nhu cầu điều tra.

## 22. Mẫu bảng log để phân tích “login thành công nhưng 403”

Một dashboard tối thiểu nên tách:

| Counter/metric | Khi tăng | Giá trị điều tra |
|---|---|---|
| `authn_success_total` | Credential/protocol xác minh thành công | IdP/protocol healthy? |
| `authn_failure_total` | Credential/protocol fail | Signature, nonce, expired token, wrong issuer? |
| `authz_denied_total` | Access policy deny | Missing role, tenant, resource? |
| `csrf_rejected_total` | CSRF token invalid/missing | POST/PUT protection issues? |
| `security_context_missing_total` | Request đáng lẽ có session/token nhưng anonymous | Cookie/repository/API token? |
| `authority_mapping_failure_total` | IAM/group lookup/role mapping failure | Entitlement source/config? |
| `session_expired_total` | Session timeout/invalidated | SSO loops/reauth? |
| `access_denied_by_stage_total` | HTTP, METHOD, DOMAIN, PROXY | Root stage? |

Đây là **tên metrics đề xuất**, không phải metrics mặc định của Spring. Đừng tăng cùng một authz deny hai lần từ filter và service rồi coi hai lần 403.

### 22.1. SLO/SLA của authorization

Có thể theo dõi:
- Authn success rate theo IdP registration.
- 403 rate sau SSO, phân loại theo policy-denied vs unintended missing role.
- Session persistence failures.
- Role/entitlement lookup latency và error.
- Tenant denial counts (không tự coi mọi denial là incident).
- False positive denies phát hiện bởi support/QA.

Không đặt mục tiêu “403 phải bằng 0”; nhiều 403 là enforcement đúng trước requests không hợp quyền.

## 23. HTTP API 401/403 và Session-based Web Login

Nếu project vừa có SPA/browser routes vừa có API:
- Sử dụng **SecurityFilterChain riêng** theo path hoặc request characteristics, với entrypoints hợp ngữ nghĩa.
- Browser OIDC/SAML thường dùng redirect + HttpSession.
- REST API bearer JWT thường stateless và có `WWW-Authenticate`.
- Đảm bảo path matchers của chain thứ nhất không nuốt callback/ACS hoặc API request của chain thứ hai.
- Đừng chỉ thay một AccessDeniedHandler để sửa route matching sai.

### 23.1. API JWT authority mapping

Một access token có scopes:
~~~text
scope: reports.read profile
~~~

Spring Resource Server thường map scopes thành:
~~~text
SCOPE_reports.read
SCOPE_profile
~~~

Nếu API rule đòi `ROLE_REPORT_VIEW` thì 403 có thể do **authorization mapping mismatch**, không phải invalid JWT. Chọn:
- API rule `hasAuthority("SCOPE_reports.read")` nếu scope được resource server tin và đúng contract; hoặc
- Map trusted scope/permissions thành domain authority với converter và issuer/audience policy.

Không cho user tự khai arbitrary ROLE_ADMIN trong JSON body/header để bổ sung JWT authorities.

### 23.2. Token đúng nhưng thiếu audience

Một JWT signature valid nhưng aud sai phải bị authentication token validation từ chối khi audience policy được cấu hình. Không xếp lỗi sai audience vào “thiếu role” chỉ vì UI hiển thị 403. Xem security chain và token validation outcome.

## 24. Lỗi authority mapper, group lookup và local identity link

Các nguyên nhân 403 dù SSO thành công:
1. Group claim không có trong ID Token/UserInfo/Assertion.
2. App đọc sai tên claim hoặc schema.
3. External identity `iss+sub`/SAML stable ID không map tới đúng local user.
4. Đọc LDAP/AD group trực tiếp nhưng nested groups chưa được resolve.
5. Group IDs đổi/realm khác mà allowlist cũ.
6. Disabled local account hoặc tenant membership inactive.
7. Role bị thu hồi nhưng session cache còn snapshot cũ.
8. Role được cấp nhưng app code kiểm authority tên khác.
9. Đúng URL role nhưng domain service kiểm ownership.
10. AuthorizationManager rule ordering/path mismatch.
11. MethodSecurity config áp rule khác HTTP matcher.
12. AOP proxy chưa áp hoặc annotation đặt sai điểm.
13. API gửi sai access token/scope.
14. Role lookup timeout, fail-closed (đúng bảo mật).
15. Frontend lưu role state cũ hoặc UI guard sai.

### 24.1. Nguyên tắc sửa mapping

Luồng đề xuất:
~~~text
Verified IdP identity (with issuer/realm)
       |
       v
Approved identity link -> localUserId
       |
       v
Local account active/locked/tenant membership
       |
       v
Trusted group/role entitlement lookup
       |
       v
Allowlisted mapper -> GrantedAuthorities
       |
       v
SecurityContext + HTTP/method/domain authorization
~~~

Nếu IdP authentication đã đúng, không cần reconfigure SAML signing keys hoặc disable OIDC validation để xử lý missing role. Hãy sửa source mapping hoặc policy có phê duyệt, test cases và audit.

### 24.2. Quyền bị thu hồi và stale session

Authentication có thể giữ authorities snapshot cho đến khi session được refresh hoặc invalidated. Ví dụ quyền của Alice bị gỡ ở AD nhưng existing session vẫn có `ROLE_REPORT_APPROVE`; đây là **over-authorization risk**, đối lập với missing-authority false deny. Cần TTL, revocation events, session invalidation, sensitive-action live entitlement check theo risk.

## 25. Trạng thái ban đầu và tái tạo lỗi có kiểm soát

Để debug một user:
1. Có request ID và thời gian chính xác.
2. Xác định login mechanism: OIDC, SAML, Kerberos, CAS, LDAP hay JWT Bearer.
3. Xác định endpoint callback và result.
4. Xem browser Network/redirect chain, cookie flags **không copy token/cookie vào ticket**.
5. Ghi request thật bị 403: method, route, matched chain, resource type.
6. Kiểm auth type/context ở request đó bằng server-side debug có kiểm soát.
7. So actual authority labels (sanitized) với required policy.
8. Kiểm tenant/resource membership.
9. Kiểm CSRF/CORS/gateway trước khi sửa role.
10. Kiểm last change IdP metadata, role mapper, IAM groups, authorization config.
11. Tái tạo ở test environment với synthetic principal và scopes/roles tương đương.
12. Bổ sung test trước khi sửa rồi chạy regression authn/authz cases.
13. Ghi root cause: AUTHN_FAILED, SESSION_MISSING, AUTHZ_DENIED_HTTP, AUTHZ_DENIED_METHOD, AUTHZ_DENIED_DOMAIN, CSRF_DENIED, CORS_DENIED hoặc PROXY_DENIED.

### 25.1. Không yêu cầu người dùng gửi token để debug

Support nên yêu cầu:
- Correlation/request ID.
- Thời điểm và tuyến chức năng.
- Thông báo lỗi hiển thị.
- Môi trường, browser và tái hiện được hay không.

**Không** yêu cầu gửi raw SAMLResponse, ID Token, access token, refresh token, Kerberos ticket, session cookie, password hay private key.

## 26. Test cases: xác thực đúng và thiếu quyền

| ID | Scenario | Kỳ vọng |
|---|---|---|
| A01 | OIDC login valid, no app role | Login success, restricted resource 403 |
| A02 | SAML signed valid, account role REPORT_VIEW | View 200, approve 403 |
| A03 | SAML signature invalid | Authentication fail, no trusted local session |
| A04 | OIDC issuer/audience/nonce invalid | Authentication fail |
| A05 | Missing session cookie after login redirect | Next request anonymous → login challenge |
| A06 | Bearer JWT missing | API 401/challenge |
| A07 | JWT valid nhưng thiếu SCOPE_reports.read | API 403 |
| A08 | User has ROLE_REPORT_VIEW | /reports/view allowed |
| A09 | User lacks ROLE_REPORT_APPROVE | /reports/approve 403 |
| A10 | User has admin role but resource tenant mismatch | Domain access denied |
| A11 | GET allowed, POST missing CSRF | CSRF 403, không nhầm role |
| A12 | OPTIONS blocked by proxy/CORS | Preflight denial, không blame IdP |
| A13 | Browser saved URL /admin, login success | Final /admin 403 nếu không ROLE_ADMIN |
| A14 | Role prefix mismatch | Deny; sửa matcher/mapper convention |
| A15 | OIDC groups claim có nhưng mapper không map | Deny, không auto ROLE_ADMIN |
| A16 | SAML Assertion attrs không thuộc signed coverage | Reject authentication, không tạo role |
| A17 | Kerberos ticket valid, local user disabled | Deny local account/authorization |
| A18 | LDAP bind succeeds, role lookup returns none | Authenticated but restricted URL denied |
| A19 | @PreAuthorize deny sau HTTP permit | Method-level denial |
| A20 | Internal service call bypass AOP proxy | Security regression, không coi “allow” là đúng |
| A21 | Role removed after session creation | Test revocation/invalidation SLA |
| A22 | Two filter chains match route incorrectly | Diagnose selected chain |
| A23 | IdP valid nhưng identity link conflict | Reject local account mapping |
| A24 | AnonymousAuthenticationToken.isAuthenticated() true | Không coi là SSO login |
| A25 | Remember-me insufficient for sensitive method | Require full/step-up auth policy |
| A26 | Business service throws AccessDeniedException | Expected 403/deny per HTTP boundary |
| A27 | User belongs tenant-a, resource tenant-b | Deny even with global role |
| A28 | CDN/WAF returns 403; app receives no request | Fix gateway, not role mapper |
| A29 | Success handler redirects to wrong URL | Fix saved-request/redirect config |
| A30 | Correct entitlement but stale frontend role cache | Server policy wins; refresh UI view |

### 26.1. MockMvc test ví dụ với authority

Tệp `src/test/java/com/example/ReportAccessTest.java` (fragment trong Spring Boot test project có `/reports/view/demo` và `/reports/approve/demo` endpoints):

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    void readerCanViewButCannotApprove() throws Exception {
        mvc.perform(get("/reports/view/demo")
                .with(user("synthetic-user")
                    .authorities(() -> "ROLE_REPORT_VIEW")))
            .andExpect(status().isOk());

        mvc.perform(get("/reports/approve/demo")
                .with(user("synthetic-user")
                    .authorities(() -> "ROLE_REPORT_VIEW")))
            .andExpect(status().isForbidden());
    }
}
~~~

**Điều kiện:** Các controllers/services của test phải thực sự tồn tại, URL matching và SecurityFilterChain phải tương ứng; nếu endpoint chưa có có thể trả 404. `.authorities(() -> "ROLE_REPORT_VIEW")` tạo mock GrantedAuthority cho business authorization tests; test này **không** verify một real OIDC token hay SAMLResponse. Có thể dùng `saml2Login()` hoặc `oidcLogin()` test post-processors để kiểm giao diện/authorization, nhưng cần integration tests riêng cho protocol verification.

### 26.2. Test anonymous khác test unauthorized

Với browser OAuth2 Login, anonymous GET protected URL có thể redirect **302**, không phải 401. Với API bearer chain, anonymous GET thường 401. Test expected HTTP code theo chain, không chép một assert 401 cho tất cả cơ chế.

### 26.3. Test CSRF độc lập

Với session-cookie browser app:
- GET authorized có thể pass.
- POST không CSRF bị 403.
- POST có valid CSRF token mới đi tới authorization/business code.
- CSRF test cần `with(csrf())` trong Spring MockMvc khi phù hợp.

Nếu muốn kiểm POST bị từ chối do thiếu role, hãy **cung cấp CSRF token hợp lệ** để lỗi thực sự nằm ở role, không phải bị chặn từ CsrfFilter trước đó.

## 27. Troubleshooting matrix theo symptom

| Triệu chứng | Root cause có thể | Điểm kiểm |
|---|---|---|
| Login callback success, /admin 403 | ROLE_ADMIN thiếu | Actual authorities vs matcher |
| Login callback success, /me 302 login | Session không persistent | Cookie, SecurityContextRepository |
| Spring log 403 trên POST, GET OK | CSRF token | CsrfFilter/Request method |
| API GET 401 dù browser OIDC login | JWT bearer/token chưa được gửi | Correct SecurityFilterChain |
| API 403 với token valid | Scope/authority thiếu | JwtGrantedAuthoritiesConverter và policy |
| Có OIDC_USER nhưng không ROLE_USER | Mapper chưa mapping | Approved IdP groups/local roles |
| Có SAML attributes groups nhưng role rỗng | Provider mapper không mapping | Verified attrs + allowlist |
| Đúng role nhưng vẫn 403 | Tenant/owner policy | Domain authorization |
| `hasRole("ADMIN")` không pass | ROLE_ADMIN thiếu hoặc prefix lệch | Naming conventions |
| 403 chỉ trên endpoint @PreAuthorize | Method-level enforcement | AOP proxy + authority |
| Browser redirect liên tục | Cookie/SameSite/secure issue | Redirect chain/session |
| 403 trên OPTIONS | CORS/security proxy | Preflight, allowed origins |
| Role thay đổi mà session không cập nhật | Stale authorities snapshot | Cache invalidation/reauth |
| Account bị disabled nhưng vẫn login | Local account policy thiếu | Identity-link/account check |
| Login OIDC IdP A bị map user IdP B | Issuer/sub linking sai | Namespace identity + tenant |
| Callback SAML bị lỗi signature | Authentication failure | IdP cert/metadata, not roles |
| Frontend báo thiếu role nhưng server allow | UI stale state | Align client/server policy |
| Một node OK, một node 403 | Config/session store drift | Pod roles/cert/session |
| Gateway returns 403 without Spring log | WAF/API gateway | Proxy and upstream tracing |
| Browser SSO works, API JavaScript 401 | fetch credentials/cookie/token | Cross-origin policy |
| Thấy Auth SuccessEvent nhưng endpoint 403 | Expected authn/authz split | Denied event + matched rule |
| AuthService/LDAP outage | Role lookup fail closed | IAM dependencies/timeouts |
| Các case đều 403 kể cả public health | Wrong chain/default rule | SecurityFilterChain ordering |
| POST with csrf passes but 403 remains | Actual method/role/tenant check | @PreAuthorize/business service |
| Unknown redirect URL after login | SavedRequest/targetUrl config | RequestCache/SuccessHandler |

## 28. Những anti-pattern nguy hiểm

1. **Thấy 403 rồi tắt SAML/OIDC signature validation.** Không giải quyết role và gây auth bypass.
2. **Gắn ROLE_ADMIN cho mọi login để tránh 403.** Phá least privilege.
3. **Cho `permitAll()` toàn ứng dụng** khi chỉ một endpoint fail.
4. **Tắt CSRF toàn hệ thống** vì một POST không có CSRF token.
5. **Tin `auth.isAuthenticated()` không kiểm anonymous** khi quyết định user SSO.
6. **Lấy claim groups tùy ý từ browser request** để biến thành GrantedAuthority.
7. **Đọc raw SAMLResponse** và chọn NameID/role không được chữ ký bảo vệ.
8. **Auto-link local account theo email** từ IdP chưa được approve.
9. **Xóa tenant/owner check** chỉ để role-level 200.
10. **Đo mỗi 302 login redirect là login success** mà không kiểm callback context.
11. **Đo mỗi 403 là authentication failure** trong metrics.
12. **Log raw ID/access/refresh token hoặc session cookie** trong support ticket.
13. **Bật TRACE Security toàn bộ production vô thời hạn.**
14. **Thay AccessDeniedHandler trả 200** để UI không báo lỗi.
15. **Tự refresh roles bằng user-controlled headers.**
16. **Dựa vào frontend route guard** thay server-side authorization.
17. **Chỉ kiểm scope khi API policy cần tenant/ownership**.
18. **Ngầm hợp nhất nhiều SecurityFilterChains** dẫn đến entrypoints khác nhau.
19. **Kéo session lifetime vô hạn** để tránh user phải login lại.
20. **Bỏ failure test** sau khi sửa một role mapping.

**Cách sửa đúng** là chứng minh root cause và bảo toàn ranh giới authentication/authorization.

## 29. Checklist trước khi kết luận “lỗi thiếu quyền”

- [ ] Đã phân biệt SSO callback với resource request sau callback.
- [ ] Đã xác định request URL/method/status/response source.
- [ ] Đã xác định đúng SecurityFilterChain và entrypoint.
- [ ] Có Authentication trong SecurityContext ở request bị lỗi.
- [ ] Đã phân biệt authenticated user với anonymous/remember-me.
- [ ] Session cookie/Authorization header được gửi đúng.
- [ ] Đã xem SavedRequest/redirect target sau login.
- [ ] Có actual GrantedAuthorities (sanitized) và required authorities.
- [ ] `hasRole`/`hasAuthority` và ROLE_ prefix nhất quán.
- [ ] OIDC scopes/roles được map đúng, không tự coi `SCOPE_` là `ROLE_`.
- [ ] SAML verified attributes được map từ trusted assertion.
- [ ] Kerberos principal/realm/LDAP group lookup không nhầm user.
- [ ] Local user identity link approved, account active.
- [ ] Tenant membership và resource owner được kiểm.
- [ ] @EnableMethodSecurity thực sự bật, @PreAuthorize chạy qua proxy.
- [ ] CSRF token đã được loại trừ như root cause khi POST 403.
- [ ] CORS/OPTIONS và gateway 403 đã được kiểm.
- [ ] IAM/AD group cache và session authorities không stale.
- [ ] Logs/metrics chia authn success/failure và authz deny.
- [ ] Không có tokens, passwords, raw claims hoặc PII nhạy cảm trong logs.
- [ ] Test gồm 302/401/403, role mapping, tenant, method, CSRF, multi-IdP.
- [ ] Mọi thay đổi role/policy có approval/audit.
- [ ] Không disable security controls để sửa symptom.

## 30. Câu hỏi ôn tập

1. **Đăng nhập thành công có nghĩa được truy cập mọi URL?** Không.
2. **Authentication trả lời gì?** Người gọi là ai và credential/protocol có hợp lệ.
3. **Authorization trả lời gì?** Identity có quyền thực hiện action/resource cụ thể.
4. **403 sau callback OIDC thường cần kiểm gì?** SecurityContext, authorities, matcher, tenant/method/resource.
5. **401 và 403 khác nhau?** 401 thường yêu cầu credential/challenge; 403 thường từ chối quyền khi đã xác thực, nhưng handlers/context có thể khác.
6. **302 về login có chứng minh authentication fail?** Không, cần xem redirect và callback result.
7. **RequestCache có tác dụng gì?** Lưu request ban đầu để redirect lại sau login.
8. **ExceptionTranslationFilter làm gì?** Chuyển AuthenticationException/AccessDeniedException thành entrypoint/denied response.
9. **AuthorizationFilter làm gì?** Dùng AuthorizationManager để kiểm URL request rule.
10. **AuthenticationEntryPoint khác AccessDeniedHandler?** Một bên bắt đầu authentication, bên kia xử lý deny khi caller đã authenticated theo trust policy.
11. **isAuthenticated() true có luôn là user thật không?** Không, AnonymousAuthenticationToken cũng có thể true.
12. **Có OIDC_USER đã có ROLE_ADMIN chưa?** Chưa.
13. **SCOPE_profile có tương đương ROLE_REPORT_VIEW không?** Không.
14. **SAML signed success có tự cấp business role không?** Không, phải map attributes/local entitlements.
15. **Kerberos ticket đúng nhưng group chưa được map sẽ thế nào?** Login có thể thành công nhưng restricted route deny.
16. **hasRole("ADMIN") cần authority nào mặc định?** ROLE_ADMIN.
17. **URL rule pass mà @PreAuthorize deny có thể xảy ra?** Có.
18. **403 do CSRF có sửa bằng thêm role không?** Không.
19. **403 trên OPTIONS có thể do đâu?** CORS/preflight/gateway rules.
20. **Vì sao /me được nhưng /admin không?** Hai endpoints có policy khác nhau.
21. **Một user có global role nhưng tenant khác thì sao?** Resource-level tenant check vẫn deny.
22. **Vì sao success event và denied event cùng hợp lệ?** Chúng đo hai giai đoạn khác nhau.
23. **Browser login session có tự xác thực stateless API không?** Không nếu API cần bearer token và request thiếu nó.
24. **Callback login pass nhưng request sau anonymous?** Kiểm cookie/session/repository/chain trước.
25. **Role thay đổi ở IAM có cập nhật existing HttpSession tức thì?** Không mặc định.
26. **MockMvc user() test chứng minh IdP token signature không?** Không.
27. **Có nên bật TRACE toàn production để debug?** Không; có nguy cơ lộ tokens/PII.
28. **Gặp 403 nên chỉnh permitAll trước?** Không, phải xác định rule/denial root cause.
29. **Một đoạn code decision model Java17 có là real Spring filter?** Không; chỉ minh họa logic.
30. **Chẩn đoán đúng cần gì nhất?** Correlation giữa login callback và request lỗi, Authentication, GrantedAuthorities, exact policy và source of denial.

## 31. Tài liệu tham khảo chính thức

- Spring Security – Servlet Architecture, filter chain và ExceptionTranslationFilter: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – Authorize HTTP Requests, AuthorizationFilter: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security (@EnableMethodSecurity, @PreAuthorize): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security – OAuth2 Login Advanced Configuration/GrantedAuthoritiesMapper: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security – OAuth2 Login Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML2 Response Authentication: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security – MockMvc Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security – Micrometer Observability: https://docs.spring.io/spring-security/reference/observability/index.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP – Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP – Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Tổng kết:** Một luồng federation login có thể đã hoàn thành đúng về cryptography/protocol, nhưng Spring vẫn **đúng khi trả 403** cho endpoint mà principal thiếu GrantedAuthority, sai tenant, không qua @PreAuthorize hoặc vi phạm CSRF/business policy. Để gỡ lỗi, hãy nối chuỗi **authentication callback → persisted SecurityContext → request sau login → exact AuthorizationManager/method/domain policy → denial source**, rồi sửa nguyên nhân thật. Đừng “chữa 403” bằng cách disable xác thực, cấp role quản trị rộng, bỏ CSRF hoặc bật trust-all. Quan sát riêng authn success/failure và authz deny sẽ giúp phân biệt login lỗi thực sự với hệ thống đang thực thi phân quyền đúng.
