# RequestHeaderAuthenticationFilter và PreAuthenticatedAuthenticationProvider

## 1. Bài toán: proxy xác thực, ứng dụng nhận danh tính đã được kiểm tra

Trong kiến trúc **Spring Security - federation**, nhánh **Xác thực qua proxy**, người dùng có thể đăng nhập tại một **identity-aware reverse proxy / access gateway** trước khi request đến ứng dụng Spring Boot. Gateway có thể dùng OIDC, SAML, mTLS, Kerberos hoặc một chính sách xác thực doanh nghiệp khác. Sau khi xác thực, gateway gửi một header nội bộ, ví dụ `X-Authenticated-User: alice@corp.example`, tới backend để thông báo **ai đã được xác thực**.

Spring Security hỗ trợ mô hình **pre-authentication** bằng hai thành phần trọng tâm:

- **`RequestHeaderAuthenticationFilter`**: trích principal (thường là username) từ một HTTP request header; kế thừa `AbstractPreAuthenticatedProcessingFilter`. **Nó không xác minh password, token OIDC, chữ ký SAML hay danh tính caller.**
- **`PreAuthenticatedAuthenticationProvider`**: tiếp nhận `PreAuthenticatedAuthenticationToken` từ filter, nạp `UserDetails` và authorities qua `AuthenticationUserDetailsService`, kiểm tra các điều kiện tài khoản được cấu hình rồi tạo `Authentication` của Spring. **Nó cũng không chứng minh header thật sự do gateway tin cậy phát ra.**

Thiết kế này an toàn **chỉ khi toàn bộ ranh giới trust ở trước Spring đã được thực thi**: client không thể tự gắn/ghi đè header, backend không thể được truy cập trực tiếp, gateway xác thực ở mọi endpoint cần bảo vệ, kênh gateway → ứng dụng được bảo vệ, và ứng dụng áp dụng **local account admission/authorization** trước khi truy cập tài nguyên.

> **Bất biến quan trọng nhất:** `X-Authenticated-User` **không phải credential tự xác minh**. Nếu một request không đáng tin có thể tự đặt `X-Authenticated-User: admin` mà Spring coi đó là principal đã xác thực, đây là **lỗ hổng giả mạo danh tính hoàn chỉnh**, dù ứng dụng có Spring Security.

Bài học trình bày luồng đầy đủ, semantics các setter/defaults, cấu hình Servlet SecurityFilterChain, cách chọn stateless/stateful, hành vi thiếu header, kiểm soát spoofing, map identity/authority, bài Java 17 chạy độc lập, cùng ma trận kiểm thử và checklist vận hành.

## 2. Sơ đồ ranh giới tin cậy

~~~text
Untrusted Internet / Browser
        |
        | GET /reports
        | Header attacker tự gửi:
        | X-Authenticated-User: admin@corp.example
        v
+-----------------------------------------+
| Trusted Identity-Aware Gateway           |
| 1. Terminate TLS và xác thực request      |
| 2. XÓA mọi client-supplied identity       |
|    headers và biến thể tương đương        |
| 3. Kiểm tra phiên IdP, policy, context    |
| 4. Nếu OK: GHI MỚI đúng một header        |
|    X-Authenticated-User: alice@corp.example
| 5. Nếu FAIL: từ chối, KHÔNG forward      |
+-----------------------------------------+
        |
        | HTTPS / mTLS / private network
        | X-Authenticated-User: alice@corp.example
        v
+-----------------------------------------+
| Spring Boot application                  |
| RequestHeaderAuthenticationFilter       |
|  -> principal: alice@corp.example       |
|  -> PreAuthenticatedAuthenticationToken |
|  -> AuthenticationManager               |
|  -> PreAuthenticatedAuthenticationProvider
|  -> UserDetailsService                  |
|  -> AccountStatusUserDetailsChecker      |
|  -> local GrantedAuthority             |
|  -> SecurityContext cho request         |
|  -> authorization: tenant / resource    |
+-----------------------------------------+
        |
        +--> 200 nếu cả identity và quyền hợp lệ
        +--> 403 nếu thiếu principal/quyền theo policy
~~~

**Gateway** là nơi xác thực upstream; **Spring pre-auth filter/provider** là lớp **chấp nhận và tích hợp** kết quả bên ngoài với mô hình `Authentication`/`GrantedAuthority`. Nếu thiếu một trong hai vế, hệ thống có thể từ chối người dùng hợp lệ hoặc cho phép người giả mạo.

### 2.1. Phân biệt chứng cứ, thuộc tính và quyền

| Dữ liệu | Ai đưa ra? | Nó chứng minh gì? | Chưa chứng minh được gì? |
| --- | --- | --- | --- |
| Phiên OIDC/SAML/mTLS tại gateway | Gateway/IdP tin cậy | Người dùng đã qua cơ chế xác thực upstream theo contract. | App local account còn active; có quyền trên resource X. |
| Header `X-Authenticated-User` | Gateway **sau khi** strip/overwrite | Gateway tuyên bố principal tương ứng. | Không tự chống giả mạo nếu client có thể đi thẳng vào backend. |
| `PreAuthenticatedAuthenticationToken` đầu vào | Spring filter | Có một principal đã được bên ngoài khẳng định. | Token chưa được provider nạp user/details và kiểm tra account. |
| `UserDetails` | Directory/DB ứng dụng | Local user/authorities/status theo thời điểm tra cứu. | Không đảm bảo header đến từ gateway nếu network trust sai. |
| `Authentication` đã hoàn tất | Spring provider | Ứng dụng đã chấp nhận principal và authorities theo policy. | Không tự cấp quyền trên mọi tenant/tài nguyên. |
| HTTP session / SecurityContext | Spring repository | Có thể giữ kết quả giữa requests, tùy cấu hình. | Không tự phản ánh gateway logout/revocation ngay lập tức. |

### 2.2. Đây không phải “xác thực bằng một password header”

`RequestHeaderAuthenticationFilter` theo thiết kế **không cần password của user**, thậm chí mặc định credentials được trả là chuỗi **`"N/A"`**. Điều này đúng vì gateway đã xác thực trước. Việc đưa password, access token hoặc JWT vào một header có tên `credentialsRequestHeader` rồi hy vọng provider sẽ verify là **sai mô hình**. Nếu muốn backend tự xác minh bearer JWT, dùng **OAuth2 Resource Server**; nếu cần Spring tự đăng nhập OIDC, dùng **`oauth2Login()`**; nếu xác thực SAML Web SSO, dùng SAML2 support. Pre-auth không tự thay thế các validators đó.

## 3. RequestHeaderAuthenticationFilter: API, defaults và rủi ro

Class:

~~~java
org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter
~~~

Kế thừa:

~~~java
org.springframework.security.web.authentication.preauth.AbstractPreAuthenticatedProcessingFilter
~~~

Các hành vi đã được định nghĩa trong JavaDoc:

| Thành phần | Giá trị / hành vi | Ảnh hưởng bảo mật |
| --- | --- | --- |
| `principalRequestHeader` | Mặc định **`SM_USER`** (tương thích CA SiteMinder). | Nếu gateway gửi header khác, phải cấu hình rõ; không tự suy từ mọi header. |
| `setPrincipalRequestHeader(String)` | Chọn header username, ví dụ `X-Authenticated-User`. | Tên header không tạo trust; cần gateway strip và sign/transport trust theo kiến trúc. |
| `getPreAuthenticatedPrincipal(request)` | Đọc `request.getHeader(principalRequestHeader)`. | **Không xác minh** giá trị và không chuẩn hóa namespace/tenant hộ bạn. |
| `exceptionIfHeaderMissing` | Mặc định **`true`**: thiếu header thì ném `PreAuthenticatedCredentialsNotFoundException`. | Response thực tế phụ thuộc cách exception được xử lý; phải test 401/403/5xx. |
| `setExceptionIfHeaderMissing(false)` | Cho phép trả `null` khi thiếu principal. | Chỉ an toàn nếu chain **vẫn deny** anonymous và không có auth fallback vô tình. |
| `credentialsRequestHeader` | Không đặt theo mặc định. | Nếu đặt, provider đọc giá trị header; **không tự xác minh** nó. |
| `getPreAuthenticatedCredentials(request)` | Mặc định trả chuỗi dummy **`N/A`**. | Provider cần credential không null; dummy không phải password đã kiểm tra. |
| `setAuthenticationManager(...)` | Từ base filter. | Bắt buộc phải nối tới provider phù hợp. |
| `setCheckForPrincipalChanges(...)` | Mặc định không liên tục kiểm tra principal đã có trong session. | Nếu dùng session và header có thể đổi, cần xem xét principal changes/invalidations. |
| `setContinueFilterChainOnUnsuccessfulAuthentication(...)` | Mặc định **`true`** khi provider gặp `AuthenticationException`. | Nếu có provider khác trong cùng chain, có thể sinh fallback trái ý định. |
| `setSecurityContextRepository(...)` | Cho phép chọn nơi lưu Authentication. | Tác động đến stale session và khả năng revoke khi gateway logout. |

### 3.1. Header mặc định SM_USER

Một deployment SiteMinder lịch sử có thể gửi:

~~~http
GET /reports HTTP/1.1
Host: portal.example.org
SM_USER: alice
~~~

Nếu gateway của bạn dùng:

~~~http
X-Authenticated-User: alice@corp.example
~~~

thì cần:

~~~java
RequestHeaderAuthenticationFilter filter =
        new RequestHeaderAuthenticationFilter();
filter.setPrincipalRequestHeader("X-Authenticated-User");
~~~

**Không có magic auto-discovery:** filter không biết `X-Forwarded-User`, `X-Remote-User`, `X-User` hay `SM_USER` của gateway nào là “đáng tin”; nó chỉ đọc **một tên header đã được cấu hình**. Tên header cần có trong **hợp đồng triển khai** của gateway và backend, cùng logic canonicalization, cách xử lý thiếu/trùng và lifecycle.

### 3.2. Thiếu header: true khác false nhưng cả hai chưa là policy đầy đủ

Mặc định:

~~~java
filter.setExceptionIfHeaderMissing(true);
~~~

Nếu header thiếu, `getPreAuthenticatedPrincipal` ném `PreAuthenticatedCredentialsNotFoundException`. Trong mã nguồn của base filter, việc lấy principal xảy ra **trước** khối `try/catch` dành cho lời gọi `AuthenticationManager`; vì vậy **không nên đảm bảo nó sẽ tự trả 403 trong mọi filter ordering và error handler**. Test HTTP status thực tế; nếu một exception đi ra ngoài filter mà không được dịch, có thể thành 5xx do container.

Một cấu hình có chủ đích khác:

~~~java
filter.setExceptionIfHeaderMissing(false);
~~~

Filter có thể tiếp tục nếu principal `null`. **Đây không phải lệnh “cho anonymous vào”!** Nếu toàn bộ chain dùng `anyRequest().authenticated()`, không có fallback và context stateless, request thiếu header vẫn bị từ chối (thường 403 với `Http403ForbiddenEntryPoint`). Nhưng nếu cùng chain còn form login/session cũ/anonymous được permit, việc không có header có thể dẫn đến hành vi khác.

**Khuyến nghị thực tế:** để **gateway chặn request chưa xác thực trước khi forward**, đồng thời Spring có policy deny rõ; không kỳ vọng backend sửa một thiết kế gateway cho phép “đôi khi có header, đôi khi không” mà vẫn an toàn.

### 3.3. Vì sao credentials mặc định là N/A?

`AbstractPreAuthenticatedProcessingFilter` tạo một authentication request gồm **principal và credentials**. `PreAuthenticatedAuthenticationProvider` thường bỏ qua request nếu principal **hoặc** credentials `null` (hoặc ném lỗi nếu bật `throwExceptionWhenTokenRejected`). `RequestHeaderAuthenticationFilter` vì thế cung cấp giá trị dummy `N/A` khi không cấu hình `credentialsRequestHeader`.

**Không được hiểu N/A là password.** Nó chỉ đáp ứng contract token shape. Đưa một “shared secret” vào credentials header cũng không tự tạo xác thực proxy an toàn, vì provider này **không so khớp secret**. Nếu cần chứng minh nguồn request là gateway, hãy dùng **mTLS/khóa mạng và chính sách gateway**, hoặc một cơ chế token có chữ ký được backend xác minh bằng validator thực sự, không dựa vào dummy credentials.

## 4. PreAuthenticatedAuthenticationProvider: vai trò chính xác

Class:

~~~java
org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider
~~~

Đây là một Spring `AuthenticationProvider` chuyên xử lý `PreAuthenticatedAuthenticationToken`. Khác với `DaoAuthenticationProvider`, nó **không kiểm tra password**; nó tin giả định rằng nguồn pre-authentication đã làm bước xác thực chính.

Một pipeline điển hình:

~~~text
PreAuthenticatedAuthenticationToken(
  principal = "alice@corp.example",
  credentials = "N/A",
  authenticated = false
)
    |
    v
PreAuthenticatedAuthenticationProvider
  1. supports(PreAuthenticatedAuthenticationToken)
  2. Reject/ignore null principal or null credentials
  3. AuthenticationUserDetailsService.loadUserDetails(token)
  4. UserDetailsChecker.check(userDetails)
  5. Build authenticated PreAuthenticatedAuthenticationToken
     with UserDetails + GrantedAuthorities
    |
    v
SecurityContextHolder
    |
    v
Authorization decisions for application/resource
~~~

**Provider không biết** reverse proxy đã đăng nhập OIDC/SAML/mTLS như thế nào, request có đi qua một gateway đáng tin hay không, hoặc attacker đã tự chèn header vào đường mạng. Đây là nhiệm vụ của **deployment boundary**.

### 4.1. Các setter và mặc định quan trọng

| API | Tác dụng | Lưu ý |
| --- | --- | --- |
| `setPreAuthenticatedUserDetailsService(...)` | Cấu hình dịch vụ nạp `UserDetails` từ Authentication request. | **Thiết yếu**; thiếu sẽ không biết account/authorities theo policy. |
| `setThrowExceptionWhenTokenRejected(true)` | Với null principal/credentials, chuyển thành `BadCredentialsException` thay vì trả `null`. | Không chứng minh nguồn header; chỉ thay cách xử lý input. |
| `setUserDetailsChecker(...)` | Chọn cách kiểm tra trạng thái `UserDetails`. | Mặc định **`AccountStatusUserDetailsChecker`**; tránh vô hiệu để bypass DISABLED/LOCKED. |
| `setGrantedAuthoritySupplier(...)` | Cấp thêm authorities theo cấu hình ở các phiên bản có API này. | Không cấp mặc định quyền mạnh hoặc coi mọi header role là trusted. |
| `supports(...)` | Chỉ hỗ trợ `PreAuthenticatedAuthenticationToken`/subclasses. | Không xử lý `UsernamePasswordAuthenticationToken` như password provider. |

Theo mã nguồn mới, provider gọi `userDetailsChecker.check(userDetails)` **sau khi** loader trả thông tin user, rồi tạo một authenticated token dựa trên authorities. Điều này giúp kiểm tra các trạng thái như locked/disabled theo dữ liệu trả về. Tuy nhiên, **quyền nghiệp vụ, tenant, ownership và trạng thái tài khoản mới cập nhật giữa các requests** vẫn cần chính sách cụ thể ở ứng dụng.

### 4.2. UserDetailsByNameServiceWrapper

`AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` nhận **Authentication token**, không chỉ một username String. Nếu đã có `UserDetailsService` truyền thống, Spring cung cấp:

~~~java
new UserDetailsByNameServiceWrapper<
        PreAuthenticatedAuthenticationToken>(userDetailsService)
~~~

Class này chuyển việc nạp thành `userDetailsService.loadUserByUsername(authentication.getName())` về mặt ngữ nghĩa. Nó phù hợp khi principal do gateway phát **đã là khóa tài khoản đúng và duy nhất trong ứng dụng**.

Nếu gateway có nhiều IdP/tenant, bạn có thể cần một `AuthenticationUserDetailsService` tự viết để map:
- `verifiedIssuer` + `verifiedSubject` từ một **trust contract** có thể kiểm chứng.
- Tenant đã được hệ thống xác định độc lập.
- Local account ID/disabled status.
- Authorities đã được phê duyệt cho **chính ứng dụng**.

**Không dùng email đơn lẻ làm khóa hợp nhất các tài khoản của nhiều issuer** khi email có thể đổi/tái sử dụng. Tránh cắt realm/domain không rõ ràng; nếu gateway chỉ gửi `alice` và có hai hệ thống identity cùng username, chính trust contract phải giải quyết collision.

### 4.3. PreAuthenticatedGrantedAuthoritiesWebAuthenticationDetails và vai trò nhóm

Spring có các lớp như `PreAuthenticatedGrantedAuthoritiesWebAuthenticationDetails` và `PreAuthenticatedGrantedAuthoritiesUserDetailsService` để xử lý pre-auth authorities được gắn vào authentication details. Chúng có ích **chỉ khi nguồn authorities là đáng tin và có hợp đồng chính xác**.

Ví dụ nguy hiểm:

~~~text
Untrusted request:
  X-Authenticated-User: alice
  X-Role: ADMIN

Backend mapper:
  any X-Role -> ROLE_ADMIN
~~~

Kẻ tấn công đã nâng quyền nếu request được đi qua hoặc có thể tới backend trực tiếp. Thậm chí khi gateway thực sự phát `groups=admins`, nhóm của IdP cũng **không mặc định** là `ROLE_ADMIN` tại Portal. Nên dùng local entitlement service và allowlisted mapping theo issuer, tenant, app. Đối với admin/finance, phải có **deny precedence** khi local account bị khóa/permission revoked.

## 5. Trục trặc nguy hiểm nhất: header spoofing

### 5.1. Kịch bản khai thác khi backend được truy cập trực tiếp

Giả sử attacker biết địa chỉ pod/service qua một LB hoặc public IP bỏ sót:

~~~http
GET /admin/users HTTP/1.1
Host: backend.example.org
X-Authenticated-User: admin@corp.example
~~~

Nếu backend dùng `RequestHeaderAuthenticationFilter` và `PreAuthenticatedAuthenticationProvider` với local directory có user `admin@corp.example`, request có thể được coi như admin **mà không cần biết password hay có phiên IdP**. Sự hiện diện của `UserDetailsService` không sửa được lỗi này, bởi loader chỉ tra tài khoản và quyền của principal mà caller đã tự khai.

**Bảo vệ đúng:** backend chỉ nhận kết nối đến từ gateway/service mesh identity được phép (mTLS, network ACL, Kubernetes NetworkPolicy, security groups), không có NodePort/ingress phụ/port-forward/public route bypass; gateway phải strip header từ client trước khi phát giá trị đã xác minh.

### 5.2. Kịch bản gateway chuyển tiếp header giả

Một proxy cấu hình sai:

~~~text
client -> X-Authenticated-User: admin@corp.example
gateway -> authenticate alice
gateway -> proxy_pass with ORIGINAL client header
backend -> sees admin@corp.example
~~~

Ngay cả khi gateway thực sự xác thực `alice`, việc **không overwrite** header khiến attacker mượn hệ thống gateway làm phương tiện chuyển một danh tính tự khai. Header phải được **xóa tại trust ingress rồi phát lại duy nhất từ principal đã kiểm chứng**, không “chỉ thêm nếu client chưa gửi”.

Bảo vệ cần gồm các biến thể:
- Case-insensitive header names theo HTTP.
- Dấu gạch nối và underscore nếu proxy/framework biến đổi tên.
- Trùng header, nhiều values, header folding, whitespace.
- HTTP/2 → HTTP/1.1 translation và path routing.
- Header khác cùng chức năng như `X-User`, `X-Remote-User`, `SM_USER`, `X-Auth-Request-User`.
- Header định danh được thêm bởi internal CDN/LB khác nhưng không được xác thực.

**Đừng chỉ strip một tên ở một ingress rồi cho request đến service qua ingress thứ hai có chính sách khác.**

### 5.3. Tại sao X-Forwarded-For không chứng minh request đáng tin?

`X-Forwarded-For`, `X-Real-IP`, `Forwarded` và `X-Forwarded-Proto` là **metadata networking**, không phải chứng thư danh tính. Client có thể tự gửi chúng nếu proxy không quản trị. `ForwardedHeaderFilter` hoặc cấu hình trusted proxies có thể giúp URL/scheme đúng, nhưng **không tự xác minh rằng principal header do gateway authentication phát**.

`request.getRemoteAddr()` có thể cho biết hop gần nhất, nhưng trong mạng mesh/LB đây chưa đủ để chứng minh gateway đã xác thực user. **Trust caller identity** nên có mTLS/service identity/network policy + đường đi được kiểm soát + header sanitation; không thay thế bằng một IP được copy từ HTTP header.

## 6. Hợp đồng giữa gateway và Spring: những câu hỏi phải trả lời

Trước khi viết Java config, hai bên cần thống nhất:

| Nhóm | Cần quy định rõ |
| --- | --- |
| **Authenticator upstream** | OIDC OP/SAML IdP/mTLS/enterprise SSO nào xác thực user, issuer được tin, MFA/assurance nếu cần. |
| **Request coverage** | Path/host/method nào bắt buộc xác thực; có đường tắt admin/actuator/WebSocket/gRPC không. |
| **Identity header** | Tên chính xác, format, tối đa length, charset, case folding, xử lý duplicate, null/empty. |
| **Identity namespace** | Subject có dạng opaque ID/realm-qualified username không, issuer và tenant có cần đi kèm không. |
| **Sanitization** | Gateway strip mọi incoming identity headers rồi viết đúng một bản từ verified principal. |
| **Channel trust** | TLS/mTLS hoặc network isolation, gateway service identity, firewall/NetworkPolicy chặn direct backend. |
| **Lifecycle** | Upstream logout, session expiry, revocation, refresh và edge cache TTL; mỗi request có header hay không. |
| **Authorization** | Local user status, authorities, tenant, resource owner; admin role mapping có approval không. |
| **Error contract** | Gateway fail → 401/403/redirect; backend missing header → deny; upstream timeout → fail closed. |
| **Observability** | Event correlation IDs, identity refs đã hash, no raw tokens/headers trong logs. |
| **Deployment/testing** | Ingress paths, health endpoints, failover, chaos test chặn mTLS và direct service access. |

### 6.1. Chọn principal dạng ổn định

Có ít nhất ba lựa chọn:

**A. Username có domain**, ví dụ `alice@corp.example`: dễ tra local directory nhưng có thể đổi/tái sử dụng. Chỉ dùng nếu tổ chức đã cam kết identity immutability/uniqueness đủ mức yêu cầu.

**B. Opaque stable ID**, ví dụ `employee-uuid-7cf1`: dễ chống rename nếu directory có mapping tốt, nhưng cần namespace/issuer để tránh collision giữa tenants.

**C. Composite issuer + sub**, ví dụ `corp-op|sub-pairwise-091`: rõ namespace nhưng cần giao thức canonicalization và phải bảo vệ khỏi delimiter collision. Tốt hơn là gửi hai trường riêng **chỉ nếu gateway xác thực và phát cả hai** rồi backend **ràng buộc chúng như một identity assertion** đã được chứng thực; không lấy tenant do browser tự gửi.

`UserDetailsByNameServiceWrapper` thuận tiện cho A hoặc một khóa composed đã được canonicalize. Với nhiều issuers, custom `AuthenticationUserDetailsService` thường phù hợp hơn để lookup theo tuple (issuer, subject, tenant), nhưng **đừng chỉ ghép chuỗi từ các header không đáng tin rồi tra DB**.

### 6.2. Thuộc tính “thực” và “tạm”

Nếu gateway phát `X-Authenticated-User` sau xác thực, đó là assertion của gateway. Nếu nó còn phát `X-Groups` hay `X-Email`, backend phải biết:
- Thuộc tính đến từ HR/LDAP/IdP hay user self-edit?
- Khi nào được cập nhật, có còn hiệu lực?
- Namespace tenant/group nằm ở đâu?
- Thuộc tính phục vụ hiển thị hay thực sự được phép dùng để cấp quyền?
- Khi source unavailable hoặc claim missing, deny, hide hay dùng local source thay thế?

Không tự gán `ROLE_ADMIN` chỉ vì `X-Groups: admin`. **Authentication ≠ authorization**.

## 7. Cấu hình Spring Security 6+/Java 17: một chain pre-auth stateless

Ví dụ sau cố ý áp dụng một giả định **chặt chẽ**: **tất cả requests đến ứng dụng trong trust zone đều phải qua gateway**; gateway **xác thực hoặc từ chối trước khi forward**, strip/overwrite identity headers, còn Spring **không giữ Authentication qua nhiều requests**. Khi thiếu header, Spring deny qua authorization; không có fallback form login trong cùng chain.

File `src/main/java/example/security/GatewayPreauthConfig.java`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;

@Configuration
public class GatewayPreauthConfig {

    @Bean
    SecurityFilterChain gatewaySecurityFilterChain(
            HttpSecurity http, UserDetailsService localUsers)
            throws Exception {

        // Provider: nạp user/authorities; không xác minh nguồn header.
        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();

        provider.setPreAuthenticatedUserDetailsService(
                new UserDetailsByNameServiceWrapper<
                        PreAuthenticatedAuthenticationToken>(localUsers));
        provider.setThrowExceptionWhenTokenRejected(true);

        // Không đăng ký filter thành @Bean Servlet thứ hai:
        // chỉ đưa instance này vào Spring Security FilterChain.
        RequestHeaderAuthenticationFilter preAuth =
                new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Authenticated-User");
        preAuth.setExceptionIfHeaderMissing(false);
        preAuth.setAuthenticationManager(new ProviderManager(provider));

        // Cùng lựa chọn stateless cho cả filter và HttpSecurity.
        NullSecurityContextRepository noSession =
                new NullSecurityContextRepository();
        preAuth.setSecurityContextRepository(noSession);

        http
            .securityContext(sc -> sc.securityContextRepository(noSession))
            .sessionManagement(sm -> sm
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
            .addFilterBefore(
                preAuth, UsernamePasswordAuthenticationFilter.class);

        // Không bật formLogin/httpBasic trong chain pre-auth này.
        // CSRF mặc định không bị tắt trong ví dụ.
        return http.build();
    }
}
~~~

**Phạm vi của snippet:** đây là configuration **dành cho dự án Spring Boot Servlet**, cần dependencies `spring-boot-starter-security` và `spring-boot-starter-web`, một bean `UserDetailsService` **thực sự** (database/LDAP/local directory), một gateway được harden và quy trình khởi chạy Spring. Nó **không phải chương trình Java SE tự biên dịch bằng `javac`**. Ngoài ra, tương thích Jakarta Servlet/Spring Security phải được xác nhận theo version dự án.

### 7.1. Vì sao cấu hình này không tạo Bean cho filter?

Spring Boot có thể **tự đăng ký một object kiểu Servlet Filter là `@Bean` vào container filter chain**. Nếu bạn cũng gọi `http.addFilterBefore(filter, ...)` với cùng bean, filter có thể được chạy **hai lần** (một ngoài Spring Security FilterChainProxy, một trong chain), dẫn tới identity context sai thứ tự hoặc lỗi khó điều tra.

Mẫu trên tạo `new RequestHeaderAuthenticationFilter()` **bên trong phương thức cấu hình SecurityFilterChain**, không đăng ký Servlet Filter Bean riêng. Nếu tổ chức muốn filter là bean vì DI/metrics, cần **disable container auto-registration** có chủ đích bằng `FilterRegistrationBean#setEnabled(false)` và vẫn add vào đúng security chain. Không mặc định hai cơ chế cùng hoạt động đúng.

### 7.2. Vì sao dùng stateless?

`NullSecurityContextRepository` **không lưu** `Authentication` vào HttpSession. Request kế tiếp muốn được chấp nhận phải có assertion của gateway **trong request đó**. Nhờ vậy:
- Gateway hủy phiên/upstream không gửi header → Spring không tự giữ quyền user từ session trước.
- Gateway trả principal khác → Spring xác thực theo principal mới trong request mới.
- Không cần một cookie `JSESSIONID` của Spring làm nguồn identity song song với gateway.
- Dễ kiểm thử: request thiếu/giả header bị chặn ở gateway, hoặc deny ở backend theo chain.

**Nhưng:** `STATELESS` **không tự bảo đảm** CSRF safety. Nếu browser dùng một cookie SSO của gateway mà gateway tự gắn identity header ở mọi request, đó là **ambient credential**. Một site độc hại có thể kích hoạt request state-changing qua browser; cần **CSRF/origin defenses** tương ứng. Ví dụ giữ CSRF default; trong ứng dụng API/browser thực cần cấu hình CSRF token repository và CORS phù hợp với loại client, thử POST/PUT/DELETE, không bật `csrf.disable()` theo thói quen.

Nếu cần HTML login UI và session-based app, có thể chọn **stateful** nhưng phải thiết kế SSO lifecycle và logout propagation riêng (xem mục 8); không dùng đồng thời Spring session và gateway identity mà không biết nguồn nào thắng.

### 7.3. Vì sao `exceptionIfHeaderMissing(false)` mà vẫn an toàn trong mô hình này?

1. **Gateway** không forward request chưa xác thực.
2. Spring filter nhận request thiếu header (nếu có lỗi gateway/deployment) và **không tạo Authentication**.
3. `NullSecurityContextRepository` **không phục hồi phiên xác thực cũ**.
4. Chain `anyRequest().authenticated()` và `Http403ForbiddenEntryPoint` sẽ **từ chối** anonymous.
5. Không có formLogin/httpBasic/provider fallback trong chain để tiếp nhận identity khác ngoài hợp đồng.

**Nếu một trong các giả định này không đúng, kết luận cũng không còn đúng.** Chẳng hạn đặt `/admin/**` là `permitAll()` hoặc cho browser kết nối thẳng backend đã phá bảo vệ; không thể đổ lỗi cho `setExceptionIfHeaderMissing(false)` riêng lẻ. Trường hợp cần status code 401 thay 403 cho API, có thể dùng entry point tương ứng nhưng chỉ đổi cách trả lỗi, **không đổi trust model**.

### 7.4. Vì sao không đặt `setContinueFilterChainOnUnsuccessfulAuthentication(false)` tùy tiện?

`AbstractPreAuthenticatedProcessingFilter` mặc định **tiếp tục chain** khi `AuthenticationManager` ném `AuthenticationException` sau khi nó đã xóa SecurityContext. Điều này an toàn trong **một chain stateless, deny-all-otherwise, không có auth mechanism khác** như snippet; anonymous sẽ bị từ chối ở cuối. Nhưng nếu chain có formLogin hoặc một alternative provider, mặc định đó có thể cho một con đường xác thực ngoài dự định.

Đặt `false` sẽ khiến exception được **ném ra khỏi pre-auth filter**; tùy thứ tự filter/exception handler, exception có thể vượt qua `ExceptionTranslationFilter` và thành 5xx nếu không có failure handler thích hợp. **Không tuyên bố `false` tự động trả HTTP 403.** Nếu cần fail-fast, xây failure handler/error mapping có kiểm thử và tách security chains cho các auth modes độc lập.

### 7.5. Cung cấp UserDetailsService thật

Có thể khởi tạo bean từ một service repository ứng dụng; ví dụ cấu trúc nghiệp vụ:

~~~text
loadUserByUsername("alice@corp.example"):
  find local identity binding by canonical principal
  if not found -> UsernameNotFoundException
  load local account status
  if DISABLED/LOCKED -> UserDetails reflects status
  load approved authorities for this app + tenant
  return UserDetails with stable username and authorities
~~~

Với production, cần **khóa local mapping**, nguồn entitlements, revocation policy, caching và chống account takeover khi username/email bị đổi. Không tạo `InMemoryUserDetailsManager` chứa admin demo trong hệ thống production chỉ vì muốn login nhanh.

**Provider có `AccountStatusUserDetailsChecker` mặc định**, nhưng một tài khoản có permission thay đổi trong lúc một request đang chạy vẫn cần authorization/resource checks theo chính sách; không xem “UserDetails loaded once” là grant vô hạn.

## 8. Nếu ứng dụng cần lưu HttpSession: rủi ro vòng đời

Một số ứng dụng server-rendered dùng session và muốn **giữ kết quả pre-auth** qua nhiều requests. Base filter có thể dùng `HttpSessionSecurityContextRepository`, và thông thường nếu đã có `Authentication`, filter **bỏ qua** request mới theo mặc định. Điều này có nguy cơ giữ quyền stale sau khi user logout khỏi gateway hoặc gateway chuyển người dùng nhưng cookie Spring vẫn được gửi.

### 8.1. Các setter cần xem xét

- `setCheckForPrincipalChanges(true)`: buộc kiểm tra principal hiện tại với `Authentication.getName()`, tái xác thực nếu khác.
- `setInvalidateSessionOnPrincipalChange(true)`: mặc định với chế độ check có thể invalidate session khi principal thay đổi, giảm nguy cơ giữ dữ liệu user A cho user B.
- `setSecurityContextRepository(...)`: quyết định khi nào/how Authentication được lưu.
- `setRequiresAuthenticationRequestMatcher(...)`: áp dụng pre-auth chỉ cho phạm vi requests đã thiết kế.
- Cấu hình `SessionAuthenticationStrategy` và session fixation protection theo phiên bản Spring Security.
- Logout/revocation flow của gateway và local session: nếu gateway logout nhưng Spring session còn, cần điều kiện **bỏ qua/thu hồi session** đúng.

**Cảnh báo:** `checkForPrincipalChanges` chỉ giải quyết so sánh principal khi request đi qua filter; **không tự** biết upstream session đã bị hủy nếu header vẫn stale, và không thay local account status/permissions freshness. Với header rỗng/missing, behavior còn phụ thuộc `exceptionIfHeaderMissing`, matcher và current SecurityContext; phải viết integration tests thay vì phỏng đoán.

### 8.2. Ví dụ hai yêu cầu khác danh tính

~~~text
Request 1:
  Gateway authenticated alice
  X-Authenticated-User: alice@corp.example
  App stores SecurityContext (alice) in JSESSIONID=J1

Request 2:
  Same JSESSIONID J1 but Gateway now authenticates bob
  X-Authenticated-User: bob@corp.example

Unsafe if filter skips because existing session auth:
  Application still uses alice identity

Required semantics:
  detect principal change
  invalidate old app session where appropriate
  create authentication for bob only after trusted header
  do not inherit alice's local authorities/cache
~~~

Với hai người dùng dùng chung thiết bị/browser, trường hợp này đặc biệt nguy hiểm. **Stateless pre-auth mỗi request** là cách đơn giản hơn nếu gateway luôn gắn principal thật ở mọi request. Nếu không, cần thiết kế identity/session binding có chứng cứ và timeouts.

### 8.3. Local logout không hủy upstream SSO

Nếu ứng dụng local `/logout` hủy `JSESSIONID`, nhưng gateway vẫn có SSO cookie và xác thực browser, request tiếp theo sẽ được gắn lại `X-Authenticated-User` và có thể lập tức login lại. Đây **không tự là lỗi của Spring**. Nếu UI hứa “đăng xuất toàn hệ thống”, cần logout tại gateway/IdP qua đúng protocol, thu hồi app session và API token phù hợp. Không dùng local logout một mình rồi khẳng định upstream session đã hết.

## 9. Phân quyền: UserDetails, GrantedAuthority và tenant

`PreAuthenticatedAuthenticationProvider` nạp `UserDetails` và gán `GrantedAuthority` dựa vào service được cấu hình. Điều này hữu ích để phân biệt:

- **Upstream authentication**: Gateway xác thực `alice` theo trust agreement.
- **Local admission**: tài khoản Spring của `alice` có tồn tại, ACTIVE, chưa bị LOCKED/DISABLED không?
- **Local authorization**: `alice` có `reports:read`, `users:manage`, `payments:approve` ở đúng tenant/resource không?

### 9.1. Hai nguồn roles phải được hòa giải rõ

Giả sử gateway phát:

~~~http
X-Authenticated-User: alice@corp.example
X-Authenticated-Groups: all-staff,finance-viewers
~~~

Ứng dụng chỉ nên dùng nhóm đã được **gateway chứng thực về nguồn, namespace, cập nhật và release policy**; vẫn cần một **allowlist** ánh xạ chúng sang authorities của app. Mẫu chính sách:

~~~text
Gateway:
  authenticated identity = (trusted-issuer, stable-subject)
  upstream groups = known source + timestamp + namespace

App:
  map verified identity -> local account
  enforce account ACTIVE
  map approved group IDs -> candidate app roles
  intersect with local entitlements and tenant constraints
  deny revoked/locked roles
  enforce resource-owner and action policy
~~~

Không chuyển `X-Groups: admin` thành `ROLE_ADMIN` tùy ý. Một nhóm `admins` của đối tác có thể không có quyền gì tại ứng dụng tài chính của bạn. **Local deny thắng upstream group** theo chính sách được thiết kế.

### 9.2. Method security

Ví dụ Spring service:

~~~java
package example.reports;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('reports:read')")
    public String readReport() {
        return "Authorized by local report policy";
    }
}
~~~

Để dùng annotation cần bật `@EnableMethodSecurity` ở cấu hình Spring phù hợp. Đây **không** phải chương trình Java SE thuần. `hasAuthority` chỉ là một lớp kiểm tra; report còn cần owner/tenant classification khi quyền chi tiết phụ thuộc đối tượng.

### 9.3. Header không phải trust contract về MFA

Nếu proxy đã thực hiện MFA cho giao dịch nhạy cảm, ứng dụng muốn biết **mức assurance và auth_time**, không thể chỉ nhìn `X-Authenticated-User`. Cần:
- Hợp đồng gateway về nguồn/phương thức/tính mới của authentication event.
- Cơ chế truyền/kiểm chứng context phù hợp (trusted assertion, mTLS scoped data hoặc token có chữ ký phù hợp audience).
- Chính sách step-up khi assurance không đủ.
- Audit quyết định mà không log credential.

**Đừng tự tạo `acr=mfa` hoặc `amr=otp` từ role/username header.** Chữ ký gateway trên claim khác không tự cho phép nâng assurance.

## 10. Xử lý trùng header, chuẩn hóa username và HTTP parsing

Một proxy chain có thể nhận các biến thể:

~~~http
X-Authenticated-User: alice@corp.example
x-authenticated-user: admin@corp.example
~~~

HTTP header names **case-insensitive**; một số Servlet containers xử lý nhiều giá trị bằng `getHeader(name)` trả **giá trị đầu tiên**, trong khi proxy khác ghép thành chuỗi phẩy. Vì vậy **không thể coi hai lines là hai principal được tách an toàn**. Quy tắc ở gateway:

1. **Strip** tất cả incoming identity header names và aliases trước bước authentication.
2. Sau auth, **set/replace exactly one authoritative identity header**.
3. **Reject duplicate/conflicting identity headers**, không tự “lấy cái cuối”.
4. Giới hạn chiều dài, charset, khoảng trắng, CR/LF và số values; log violation metadata (không log raw identity).
5. Canonicalize username/subject ở **một nơi duy nhất**, dùng đúng namespace và document case-sensitivity.
6. Pin trusted gateways / reverse proxy identities, không dựa vào header có thể spoof.

### 10.1. Đừng trim/case-fold mù quáng

Username có thể phân biệt hoa/thường theo IdP, và subject opaque có thể chứa các ký tự không có quy tắc canonicalization giống email. Các ví dụ:

~~~text
Alice@Corp.Example
alice@corp.example
alice
CORP\alice
opaque-sub:001
opaque-sub:1
~~~

Chúng có thể là **các identity khác nhau** tùy nguồn và hợp đồng. Không tự biến `CORP\alice` thành `alice` nếu cùng username còn tồn tại ở realm khác. Một IdP/OIDC OP có thể có `sub` pairwise theo client; đừng hợp nhất dựa vào email.

### 10.2. Nhiều tầng proxy

~~~text
Browser -> CDN -> WAF -> OIDC Gateway -> Service Mesh -> Spring
             (untrusted identity until trusted gateway injects)
~~~

Mỗi hop phải có hợp đồng: ai strip header, ai inject, ai overwrite, ai có thể call backend. Nếu Service Mesh cấp identity mTLS cho pod, vẫn phải đảm bảo gateway-only **authorization policy** ở mesh (đúng service account/namespace/port), không chỉ “service mesh bật mTLS cho mọi pods”. **mTLS giữa tất cả pods** không tự chứng minh request đi từ **đúng authenticated gateway**.

## 11. Java 17 tự chạy: mô phỏng một trust boundary an toàn

Chương trình sau mô phỏng hai vế:
- **Bên ngoài Spring**: gateway thực hiện authentication trước khi forward, **bỏ qua header do client tự khai** và phát identity đã xác minh.
- **Bên trong ứng dụng**: kiểm tra principal có format/namespaces được phê duyệt, local account active và quyền tài nguyên.

Đây là **Java SE 17 độc lập**, không import Spring. Nó **không** kết nối một gateway thật, không có TLS/mTLS/OIDC/SAML validation, và các boolean như `trustedConnection` **chỉ là giả lập**. Trong production những điều đó phải do hạ tầng/Gateway chứng minh, **không được lấy từ bất kỳ HTTP request header nào**.

Tệp **`TrustedProxyBoundaryDemo.java`**:

~~~java
import java.util.Set;

public final class TrustedProxyBoundaryDemo {

    record Incoming(
            boolean trustedConnection,
            String clientSuppliedHeader,
            boolean gatewayAuthenticated,
            String verifiedPrincipal,
            boolean localAccountActive,
            boolean hasReportsPermission) {}

    private static final Set<String> PROVISIONED =
            Set.of("alice@corp.example", "bob@corp.example");

    static String evaluate(Incoming in) {
        if (!in.trustedConnection()) {
            return "EDGE_REJECT";
        }
        if (!in.gatewayAuthenticated()) {
            return "UPSTREAM_DENIED";
        }

        // Gateway MUST strip clientSuppliedHeader.
        // Only an upstream-verified identity may reach backend.
        String principal = in.verifiedPrincipal();

        if (principal == null || principal.isBlank()) {
            return "NO_PRINCIPAL";
        }
        if (!principal.matches("[a-z][a-z0-9._-]{0,30}@corp\\.example")) {
            return "BAD_PRINCIPAL";
        }
        if (!PROVISIONED.contains(principal)) {
            return "NOT_PROVISIONED";
        }
        if (!in.localAccountActive()) {
            return "ACCOUNT_DISABLED";
        }
        if (!in.hasReportsPermission()) {
            return "FORBIDDEN";
        }
        return "ALLOW:" + principal;
    }

    public static void main(String[] args) {
        System.out.println(evaluate(new Incoming(
                false, "admin@corp.example", true,
                "alice@corp.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", false,
                null, true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "alice@corp.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "eve@other.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "bob@corp.example", false, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "bob@corp.example", true, false)));

        System.out.println(evaluate(new Incoming(
                true, null, true,
                "alice@corp.example", true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                null, true, true)));

        System.out.println(evaluate(new Incoming(
                true, "admin@corp.example", true,
                "mallory@corp.example", true, true)));
    }
}
~~~

Lệnh chạy:

~~~bash
javac TrustedProxyBoundaryDemo.java
java TrustedProxyBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
EDGE_REJECT
UPSTREAM_DENIED
ALLOW:alice@corp.example
BAD_PRINCIPAL
ACCOUNT_DISABLED
FORBIDDEN
ALLOW:alice@corp.example
NO_PRINCIPAL
NOT_PROVISIONED
~~~

Diễn giải:

1. Caller không qua trusted gateway → **EDGE_REJECT**, dù header hoặc principal có vẻ đúng.
2. Gateway chưa xác thực, client lại gửi `admin` → **UPSTREAM_DENIED**.
3. Gateway xác thực `alice` và overwrite client header `admin` → ứng dụng chấp nhận **alice**, không chấp nhận admin.
4. Gateway phát principal ngoài namespace được phê duyệt → **BAD_PRINCIPAL**.
5. Kerberos/OIDC/SAML gateway đã xác thực `bob` nhưng local account disabled → **ACCOUNT_DISABLED**.
6. `bob` active nhưng thiếu quyền report → **FORBIDDEN**.
7. Client không hề gửi header tự khai nhưng gateway xác thực `alice` → vẫn cho đúng `alice`.
8. Upstream không cung cấp principal → **NO_PRINCIPAL**, không dùng client header.
9. Principal hợp định dạng nhưng chưa được local provision → **NOT_PROVISIONED**.

**Giới hạn thật sự:** demo dùng `PROVISIONED` là tập giả lập, format cố định `@corp.example` và bool `gatewayAuthenticated`. Không tự dùng những biến này như một proxy authentication control trong controller Spring; phải có chứng cứ mTLS, header sanitation, gateway auth middleware và user repository thật. Nó cho thấy **thứ tự các điều kiện** và tại sao **không bao giờ đọc lại `clientSuppliedHeader` làm user**.

### 11.1. Bài tập thay đổi code demo

- Đổi `trustedConnection` thành `false` dù `gatewayAuthenticated=true`: vẫn bị EDGE_REJECT.
- Đổi `verifiedPrincipal` thành `admin@corp.example` và giữ `localAccountActive=true`: kết quả NOT_PROVISIONED vì local DB chưa có admin, khác với “header admin nên tự được admin”.
- Đổi `clientSuppliedHeader` thành chuỗi khác: kết quả không đổi nếu gateway verified principal không đổi.
- Đặt `gatewayAuthenticated=false` với `verifiedPrincipal` có giá trị: vẫn UPSTREAM_DENIED.
- Đặt `hasReportsPermission=false`: dù principal được xác thực, vẫn FORBIDDEN.
- Bổ sung tenant/account status, đảm bảo cross-tenant deny và blocked local user.
- Bổ sung test chống đồng nhất hai giá trị subject gần giống nhau (case, realm, delimiter) khi nhận nhiều identity providers.

## 12. Tình huống vận hành: proxy lỗi, backend sai cấu hình

| Triệu chứng | Nguyên nhân có thể | Kiểm tra an toàn |
| --- | --- | --- |
| Tất cả request vào Spring đều 403. | Gateway không phát principal, backend thiếu UserDetails, entry point không fallback. | Trace gateway auth success → header injected metadata → Spring loader; không in raw JWT/cookie. |
| Header đến Spring là `null`. | Proxy strip nhầm cả header đã set, route khác gateway, filter đọc sai tên. | So chính xác `principalRequestHeader` và gateway output trên trusted hop. |
| Header `SM_USER` có nhưng filter đang đợi `X-Authenticated-User`. | Contract khác nhau. | Cấu hình một tên chuẩn, không tự đọc “bất kỳ header nào”. |
| Request direct tới pod với `X-Authenticated-User: admin` login được. | NetworkPolicy/ingress bypass. | **Security incident**: chặn direct path, bảo vệ mTLS/ACL và strip headers. |
| Client gửi admin còn gateway xác thực alice nhưng app thấy admin. | Gateway không overwrite hoặc duplicate canonicalization. | Fix strip/replace ở ingress, test duplicate/case/underscore. |
| App nhận header nhưng không có quyền. | `UserDetailsService` thiếu authorities, local account status/tenant deny. | Phân biệt authentication và authorization, không bypass account checks. |
| User disabled nhưng app vẫn active. | Session cũ hoặc user-details cache stale; disable status checker. | Kiểm tra stateless mỗi request, cache TTL, revoked epoch. |
| Browser SSO logout nhưng Spring vẫn cấp quyền. | SecurityContext/HttpSession còn hoặc proxy vẫn gửi stale identity. | Kiểm tra local session vs gateway lifetime, recheck and revoke. |
| Principal chuyển từ alice sang bob cùng cookie, app vẫn alice. | Base filter skip khi session authenticated. | Stateless hoặc `checkForPrincipalChanges` + invalidate session và test. |
| Login lỗi chỉ khi thêm filter dưới dạng `@Bean`. | Spring Boot tự đăng ký Servlet filter ngoài Security chain. | Chặn auto-registration, đảm bảo filter chạy một lần. |
| Provider không xử lý token. | Chưa set `AuthenticationManager`, khác token type, thiếu wrapper. | Inspect FilterChain và ProviderManager wiring. |
| Missing credentials ở provider. | Custom filter trả null credentials (khác default N/A). | Sửa contract, không coi N/A là secret. |
| Missing header tạo 500. | `exceptionIfHeaderMissing=true` ném trước auth manager handler; filter order/error mapping. | Test exception path, gateway deny và Spring error policy. |
| Có form login và header auth cùng chain. | Fallback vô tình tạo bypass trust perimeter. | Tách chains/hosts với matcher và policy, hoặc bỏ fallback. |
| API bearer token vào pre-auth app không hoạt động. | `RequestHeaderAuthenticationFilter` không phải JWT decoder. | Dùng `oauth2ResourceServer` với token validation riêng. |
| Một tenant nhìn dữ liệu tenant khác. | Map username mà không namespace issuer/tenant, permission check thiếu. | Bind identity tuple và resource/tenant authorization. |
| Multi-node hoạt động không nhất quán. | Session local, header path khác, user cache/roles khác. | Shared policy/DB, stateless or consistent session store, load test. |
| Header case/multiple values gây identity khác. | HTTP normalization ở CDN/gateway/backend không nhất quán. | Strip all variants, reject duplicates, canonicalization tests. |
| CSRF thành công dù app stateless. | Browser SSO ambient cookie khiến gateway gắn header tự động. | CSRF/origin/Fetch Metadata policy, không tự disable CSRF. |
| API 403 sau khi login upstream. | Local user missing/disabled hoặc permission thiếu. | Giữ deny-by-default; không cho admin theo header nhóm. |
| Gateway lỗi IdP nhưng vẫn forward header cũ. | Fail-open/caching sai TTL. | Fix gateway session revocation, fail closed. |

### 12.1. Bộ câu hỏi debug theo thứ tự

1. Request có **đi từ trusted gateway** không? Backend có chặn direct access không?
2. Gateway có xác thực user hay dùng một fallback “allow without login” không?
3. Client-supplied identity headers đã được **strip** trước khi gateway gắn verified principal chưa?
4. Header cuối đến Spring có **đúng một value** và tên đúng không?
5. Spring có đúng `RequestHeaderAuthenticationFilter` trong **SecurityFilterChain**, không duplicate Servlet registration không?
6. Filter có chạy trên request path đó không, và `getPreAuthenticatedPrincipal` trả giá trị nào (ghi audit masked/hash)?
7. `AuthenticationManager` có `PreAuthenticatedAuthenticationProvider` phù hợp không?
8. `AuthenticationUserDetailsService` có tìm đúng local account không?
9. `AccountStatusUserDetailsChecker`/custom checker có tôn trọng disabled/locked không?
10. `SecurityContextRepository` có persist auth ngoài dự tính, khiến upstream logout không có tác dụng không?
11. `authorizeHttpRequests` và method security có đúng authority/tenant/resource checks không?
12. Có một “fallback” formLogin/httpBasic/bearer hoặc permitAll route vô tình mở protected resource không?
13. Gateway/reverse-proxy có giữ nguyên header qua HTTP/2, WAF, service mesh mà không cho duplicate không?
14. Có logs/metrics đủ phân biệt edge deny, missing principal, loader reject và authz deny không?

## 13. Kiểm thử: không chỉ happy path

### 13.1. Unit tests cho filter/provider

Những trường hợp đáng thử bằng Spring MockMvc/Servlet mocks (đây là **test specification**, không phải code có thể chạy khi thiếu dependencies):

| Test | Expected |
| --- | --- |
| Header `X-Authenticated-User: alice@corp.example`, local user ACTIVE, có role. | Provider tạo authenticated token với authorities được duyệt. |
| Header thiếu, backend stateless với `anyRequest().authenticated()`. | Deny; không dùng identity từ request trước. |
| Header rỗng/whitespace. | Deny theo contract/gateway validation; không tạo empty username session. |
| Header chứa CR/LF hoặc nhiều values. | Edge reject/normalize fail-safe; không tin value đầu/giữa tùy container. |
| Header `SM_USER` nhưng filter cấu hình `X-Authenticated-User`. | Không tự nhận identity từ header lạ. |
| `PreAuthenticatedAuthenticationToken` có null credentials. | Provider reject/ignore theo config, không cấp Authentication. |
| Token principal hợp lệ nhưng `UserDetailsService` không tìm user. | Reject, không auto-provision tùy tiện. |
| UserDetails `isEnabled=false`. | Reject theo checker mặc định. |
| UserDetails `isAccountNonLocked=false`. | Reject, không cho chạy controllers. |
| User có `ROLE_USER` nhưng endpoint cần `app:admin`. | 403. |
| Provider không có `PreAuthenticatedUserDetailsService`. | Bean init/config fail; không tạo identity mặc định. |
| App stateless, request 1 alice rồi request 2 thiếu header. | Request 2 không còn authenticated. |
| App stateful, request 1 alice rồi request 2 bob. | Detect change/invalidate/re-auth theo policy và tested filter settings. |
| App đã login nhưng permission bị thu hồi. | Theo SLA, data source/cache policy deny hành động mới. |

### 13.2. Integration tests với reverse proxy thật

| Kịch bản | Expected outcome |
| --- | --- |
| Chưa đăng nhập gateway, GET protected. | Gateway chặn/redirect trước backend; không có trusted principal header. |
| Gửi client header `X-Authenticated-User: admin` chưa đăng nhập. | Gateway strip và từ chối request, không đến Spring authenticated. |
| Đăng nhập alice nhưng client gửi `admin`. | Gateway overwrite, backend chỉ thấy alice. |
| Header name khác case và duplicate. | Gateway reject/strip đúng, không kết hợp ra admin. |
| Header với underscore thay hyphen. | Không có đường bypass do normalization khác nhau. |
| Truy cập thẳng pod/node port/LB thứ hai. | Bị chặn network-level, không thể đăng nhập bằng header tự gắn. |
| Cùng header qua CDN, WAF, ingress và service mesh. | Không bị đổi, thêm hai values hoặc rơi mất. |
| Gateway mTLS client certificate không đúng. | Backend/mesh từ chối trước Spring. |
| Gateway IdP tạm unavailable. | Fail closed, không forward identity stale ngoài SLA. |
| Browser logout tại upstream. | Request tiếp theo không có trusted header; app stateless deny. |
| Gateway đổi user trong cùng browser. | Backend nhận đúng identity mới, không giữ old role. |
| Local account disabled giữa requests. | App deny theo policy, dù gateway còn SSO. |
| Multi-tenant username collision. | Không merge accounts do cùng email/username. |
| Browser gửi state-changing POST từ origin độc hại. | CSRF/origin checks ngăn, không dựa vào header SSO. |
| Response 403 không lộ raw principal/headers. | Error handling/logging redacted. |
| Audit logs đầy username/token. | Test security review phải fail và yêu cầu data minimization. |
| Session-based variant chạy qua nhiều pod. | Header changes/logout consistent, không giữ stale SecurityContext. |

**Điểm nghiệm thu cao nhất:** tấn công **header spoofing từ client và direct-backend** phải thất bại. Một unit test filter trả authenticated với request có header không chứng minh được hạ tầng an toàn; nó chỉ chứng minh library làm đúng chức năng “tin header đã được xác thực”.

### 13.3. Ví dụ yêu cầu HTTP minh họa

**Cố ý giả mạo từ phía client chưa đăng nhập:**

~~~http
GET /admin/users HTTP/1.1
Host: portal.example.org
X-Authenticated-User: admin@corp.example
~~~

Hệ thống đúng:
- Gateway chặn vì client chưa xác thực;
- hoặc gateway xác thực user thật rồi **ghi đè** header thành identity thật;
- Spring không được thấy admin tự khai.

**Client đã xác thực alice nhưng cố gắn admin:**

~~~http
GET /reports HTTP/1.1
Host: portal.example.org
Cookie: edge_sso_session=browser-owned-cookie
X-Authenticated-User: admin@corp.example
~~~

Dòng cookie chỉ là **ký hiệu minh họa**, không phải credential dùng được. Backend phải nhận identity của **alice đã được gateway xác thực**, không phải admin từ request gốc. Không đưa cookie/token thực vào tài liệu hay logs.

## 14. Lựa chọn pre-auth khác: đừng dùng nhầm giao thức

| Kiến trúc | Integration Spring phù hợp | Vì sao |
| --- | --- | --- |
| Gateway đã xác thực và gửi username qua private/trusted header. | `RequestHeaderAuthenticationFilter` + `PreAuthenticatedAuthenticationProvider`. | Chính là pre-auth, không tự kiểm tra upstream credential. |
| Java EE/Jakarta container đã có authenticated `request.getUserPrincipal()`. | `J2eePreAuthenticatedProcessingFilter` hoặc cơ chế container pre-auth tương ứng. | Nguồn principal là container trust boundary, không HTTP header từ client. |
| Client certificate X.509 tại Spring/TLS termination đáng tin. | Spring X.509 authentication/filter với certificate validation. | Certificate binding khác trusted gateway username. |
| Browser login trực tiếp bằng OIDC ở Spring app. | `oauth2Login()`. | Spring thực hiện code/token validation theo client registration. |
| REST API nhận OAuth Bearer JWT. | `oauth2ResourceServer().jwt()` cùng issuer/audience checks. | Resource server phải tự xác minh token, không tin header `X-User`. |
| REST API nhận opaque bearer token. | Resource Server introspection. | Không dùng PreAuthenticatedAuthenticationProvider như decoder. |
| SAML 2.0 POST Web SSO vào Spring. | `saml2Login()` và SAML2 providers/validators. | Assertion signature/audience/correlation khác pre-auth header. |
| Reverse proxy terminate Kerberos rồi gửi principal header. | Pre-auth nếu network/headers được tin; hoặc GSS validation ở Spring nếu ứng dụng tự terminate. | Phải chọn nơi xác thực có thẩm quyền. |
| Microservice gọi microservice bằng mTLS + SPIFFE identity. | mTLS/service identity + application authorization, đôi khi custom principal extraction. | Không tự coi header do mọi pod gửi là user login. |

Nếu gateway kết thúc xác thực, ứng dụng vẫn cần biết **điều kiện trust** và đủ thông tin để phân biệt account. Nếu API cần kiểm tra token audience/expiry/signature độc lập, **không** dùng header-only preauth chỉ vì triển khai nhanh hơn.

## 15. Observability và privacy

Không ghi raw:
- `Cookie`, `Authorization`, OIDC ID/access/refresh tokens.
- Header identity với email/employee ID trong logs công khai.
- SAML assertions hoặc gateway session IDs.
- Toàn bộ danh sách groups/roles hoặc user profile.
- Private network peer details nhạy cảm và mTLS credentials.

Dùng audit trường có định danh tham chiếu:

~~~text
event=PROXY_PREAUTH_DECISION
time_utc=2026-11-07T03:00:00Z
gateway_service_ref=corp-identity-gateway
request_correlation_id=req-729c
principal_ref=HMAC(canonical-principal)
principal_header_count=1
trusted_peer_verified=true
edge_authentication_status=SUCCESS
local_account_status=ACTIVE
authority_policy_version=portal-v6
decision=ALLOW
~~~

Đây là **schema tự đề xuất**, không phải log mặc định của Spring Security. Không cho client tự đặt `trusted_peer_verified=true`. Metric labels nên dùng reason codes và service refs có cardinality hạn chế, không dùng raw username làm label.

Các metrics hữu ích:
- `proxy_auth_success_total` / `proxy_auth_failure_total` tại gateway.
- `preauth_header_missing_total`, `preauth_header_duplicate_total`.
- `preauth_user_not_found_total`, `preauth_account_disabled_total`.
- `preauth_authorization_denied_total` theo route/role đã được cho phép metric.
- `preauth_principal_change_total` ở hệ thống session-based.
- `preauth_direct_backend_probe_denied_total` tại firewall/mesh.
- `preauth_edge_header_spoof_attempt_total`.
- `preauth_gateway_idp_outage_total` và stale cache hit/expiry.

**Đừng lấy 403 spike làm bằng chứng duy nhất:** phân tách `gateway reject`, `Spring missing header`, `UserDetailsService reject` và `resource authorization deny`; sửa sai lớp có thể vô tình làm yếu bảo mật.

## 16. Sai lầm phổ biến

1. **“`RequestHeaderAuthenticationFilter` xác thực user bằng header.”** Sai: nó chỉ **trích** principal, giả định gateway đã xác thực.
2. **“`PreAuthenticatedAuthenticationProvider` kiểm tra password upstream.”** Sai: nó nạp user/authorities, không validate OIDC/SAML/credential.
3. **“Có `UserDetailsService` là chặn được header spoofing.”** Sai: loader có thể tra đúng account admin do attacker tự khai.
4. **“Chỉ cần kiểm tra `X-Forwarded-For` là trusted gateway.”** Sai: đó là network metadata, có thể spoof nếu boundary sai.
5. **“Backend có HTTPS thì mọi request header đều đáng tin.”** Sai: TLS không chứng minh rằng gateway đã strip header, trừ khi mutual trust/client identity được áp dụng.
6. **“Gateway chỉ cần thêm header nếu chưa có.”** Sai: phải xóa client-supplied header rồi **overwrite** từ verified identity.
7. **“Header default là X-Authenticated-User.”** Sai: class mặc định dùng **`SM_USER`**.
8. **“Filter tự nhận token header có chữ ký.”** Sai: không có JWT/SAML decoder.
9. **“`credentialsRequestHeader` làm provider so mật khẩu.”** Sai: không có password verification.
10. **“Thiếu header mặc định luôn trả HTTP 403.”** Sai: mặc định throw; response phụ thuộc filter chain/error handlers.
11. **“`exceptionIfHeaderMissing(false)` nghĩa là anonymous được vào mọi route.”** Sai: authorization vẫn có thể deny; nhưng phải test fallback/session.
12. **“`continueFilterChainOnUnsuccessfulAuthentication(true)` luôn an toàn.”** Sai nếu chain có auth method khác có thể bypass trust contract.
13. **“Bật false luôn trả 403.”** Sai: thrown exception cần handler và đúng filter order.
14. **“Tạo Filter Bean rồi `addFilterBefore` thêm lần nữa không có hại.”** Sai: có thể double registration.
15. **“`STATELESS` tự phòng CSRF.”** Sai: browser gateway SSO cookie có thể là ambient credential.
16. **“User đã upstream MFA thì mặc định admin.”** Sai: assurance và authorization tách biệt.
17. **“X-Groups=admin ở proxy được đổi thẳng ROLE_ADMIN.”** Sai: cần contract/allowlist/entitlements.
18. **“Cùng username ở hai issuer luôn là cùng người.”** Sai: phải namespace identity.
19. **“Upstream logout tự làm biến mất Spring session.”** Không chắc: session/cookie có thể sống khác.
20. **“Một application server active session có thể thay đổi user trong header mà không cần xử lý gì.”** Sai: cần principal-change reauth/invalidate hoặc stateless.
21. **“Có mTLS giữa mọi pods thì chỉ gateway mới gọi được backend.”** Sai: cần chính sách **authorization** cho đúng service identity.
22. **“Gateway fail thì ứng dụng có thể tự chấp nhận header cũ.”** Sai: fail-closed theo SLA và trust contract.
23. **“Header case-sensitive nên gửi thêm x-authenticated-user sẽ tạo claim khác.”** Sai: HTTP header names case-insensitive.
24. **“Cho `/admin/**` permitAll vẫn an toàn vì proxy sẽ chặn.”** Đó là defense-in-depth thất bại và rủi ro routing bypass.
25. **“Pre-auth thay thế luôn resource authorization.”** Sai: phải kiểm tra tenant/owner/action tại business service.

## 17. Checklist trước production

1. Gateway đã chứng minh **upstream authentication** qua IdP/SSO/mTLS theo hợp đồng chưa?
2. Backend có **chặn direct network paths** (public IP, NodePort, ingress phụ, service mesh unauthorized source) không?
3. Gateway có **strip tất cả client-supplied identity headers** và **overwrite đúng một header** từ verified principal không?
4. Gateway có từ chối request chưa auth, IdP outage, invalid session, revoked token thay vì forward với header cũ không?
5. Kênh gateway→backend có TLS/mTLS/service identity hoặc network isolation phù hợp không?
6. Username/subject/issuer/tenant có namespace ổn định, tránh collision và rename takeover không?
7. `RequestHeaderAuthenticationFilter` có `principalRequestHeader` đúng tên, test missing/empty/duplicate không?
8. `PreAuthenticatedAuthenticationProvider` đã nối tới `AuthenticationUserDetailsService` / `UserDetailsByNameServiceWrapper` đúng không?
9. `UserDetailsChecker` có kiểm tra locked/disabled và local authorization deny đúng không?
10. Filter có trong đúng **Spring Security FilterChain** và không duplicate Servlet registration không?
11. Có biết rõ defaults `exceptionIfHeaderMissing`, `continueFilterChainOnUnsuccessfulAuthentication`, `checkForPrincipalChanges` không?
12. Đã chọn **stateless** hoặc **session-based** một cách chủ đích, có test thay đổi user, logout và revoked entitlement chưa?
13. Có giới hạn đường fallback formLogin/httpBasic/Bearer ở chain/host/URL riêng, không tạo bypass pre-auth không?
14. Có giữ CSRF/origin defenses với browser SSO cookie và policy CORS không?
15. Có phân biệt `authentication` và `authorization`, enforce tenant/resource ownership tại backend không?
16. Có log correlation IDs/reason codes nhưng không log raw identity tokens/PII không?
17. Có integration test gửi **admin header giả** từ Internet, gọi direct pod, duplicate header và gateway failure không?
18. Có kiểm thử multi-node, DNS/TLS rotation, source identity policy, session storage/expiry và authz update không?
19. Với admin/finance endpoints, có step-up/assurance evidence đáng tin và local entitlement riêng không?
20. Có quy trình owner/approval/review cho thay đổi gateway header contract, service identities, permissions không?

## 18. Tự kiểm tra kiến thức

1. **`RequestHeaderAuthenticationFilter` làm gì?** — Đọc principal từ một header cấu hình sẵn và tạo pre-authentication request; không xác minh upstream credentials.
2. **Header mặc định là gì?** — **`SM_USER`**.
3. **`PreAuthenticatedAuthenticationProvider` làm gì?** — Dùng `AuthenticationUserDetailsService` nạp `UserDetails`/authorities và kiểm tra account status, tạo authenticated token.
4. **Vì sao user có thể impersonate admin nếu được gọi backend trực tiếp?** — Vì filter tin header, không có cryptographic proof ở chính header đó.
5. **Proxy cần làm gì với header do client gửi?** — Xóa tất cả header identity tự khai trước khi phát một header chuẩn từ verified principal.
6. **`N/A` trong credentials là gì?** — Dummy value, không phải password.
7. **Thiếu header sẽ thế nào mặc định?** — Filter ném `PreAuthenticatedCredentialsNotFoundException`; HTTP response cần test theo error handling/filter order.
8. **`exceptionIfHeaderMissing(false)` có luôn cho anonymous vào không?** — Không; chain phải deny anonymous nếu route cần auth.
9. **`UserDetailsByNameServiceWrapper` dùng khi nào?** — Khi principal đã là khóa duy nhất để tra bằng `UserDetailsService.loadUserByUsername`.
10. **Vì sao không map upstream group admin thành app admin trực tiếp?** — Vì khác namespace/semantics và cần local entitlements.
11. **Tại sao stateless có lợi khi gateway inject header mỗi request?** — Không giữ SecurityContext cũ khi upstream ngừng phát assertion.
12. **Tại sao stateless chưa tự hết CSRF?** — Gateway SSO cookie có thể khiến browser tự được xác thực lại mà không có ý định của user.
13. **`checkForPrincipalChanges(true)` giải quyết gì?** — Đối chiếu principal header mới với authentication session cũ khi request đi qua filter.
14. **`invalidateSessionOnPrincipalChange` cần gì?** — Giảm nguy cơ dùng session/data cũ khi identity thay đổi.
15. **Tại sao không nên trộn formLogin và pre-auth trong cùng chain?** — Có thể tạo đường bypass external authentication system.
16. **API JWT khác pre-auth header thế nào?** — JWT phải được backend verify signature, issuer, audience và expiry; header-only pre-auth không làm việc đó.
17. **Khác biệt 403 và 401 ở pre-auth?** — Phụ thuộc entry point/error policy; `Http403ForbiddenEntryPoint` thường trả 403 khi không có principal.
18. **Bằng chứng kiểm thử mạnh nhất cho gateway trust?** — Admin header spoofing/direct backend attempts đều thất bại, trong khi user được xác thực thật vẫn map đúng.
19. **Tại sao mTLS giữa mọi pods chưa đủ?** — Cần authorize chỉ đúng gateway service identity được gọi backend.
20. **Có thể dựa vào email/username không namespace khi nhiều IdP?** — Không an toàn nếu có collision, rename hoặc tái sử dụng.
21. **Khi local account bị DISABLED nhưng upstream header còn valid, phải làm gì?** — Deny admission/authorization theo status checker và policy.
22. **Spring Security biết gateway đã dùng MFA không?** — Không chỉ từ username header; cần assurance evidence có hợp đồng và xác minh.
23. **Cấu hình sao để không bị chạy filter hai lần?** — Đưa filter vào đúng SecurityFilterChain, không đồng thời auto-register Servlet Filter Bean.
24. **Sau upstream logout, local session có thể còn không?** — Có nếu session-based và không có revocation/identity refresh; cần policy.
25. **Nguồn xác minh identity thực sự ở mô hình này là đâu?** — Gateway/IdP + trust channel; Spring chỉ chấp nhận và map danh tính đã xác minh.

## Tài liệu tham khảo

- [Spring Security — Pre-Authentication Scenarios: Request-Header, provider, Http403ForbiddenEntryPoint](https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html)
- [Spring Security API — RequestHeaderAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html)
- [Spring Security API — AbstractPreAuthenticatedProcessingFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html)
- [Spring Security API — PreAuthenticatedAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [Spring Security API — UserDetailsByNameServiceWrapper](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsByNameServiceWrapper.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security GitHub — RequestHeaderAuthenticationFilter implementation](https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.java)
- [Spring Security GitHub — PreAuthenticatedAuthenticationProvider implementation](https://github.com/spring-projects/spring-security/blob/main/web/src/main/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.java)
- [OWASP — HTTP Security Response Headers and reverse-proxy architecture guidance](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
