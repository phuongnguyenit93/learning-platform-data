# Lấy danh tính và quyền từ gateway, container hoặc hệ thống truy cập tập trung

Trong nhiều hệ thống doanh nghiệp, **Spring Security không phải thành phần trực tiếp xác thực mật khẩu, khóa bảo mật hay phiên SSO của người dùng**. Một **API gateway**, **reverse proxy xác thực**, **Java Servlet container** hoặc **hệ thống truy cập tập trung** (access manager) đã xác thực người dùng trước đó. Ứng dụng Java tiếp nhận một **danh tính đã được xác thực ở thượng nguồn** (*pre-authenticated identity*) và chuyển nó thành `Authentication`, `UserDetails` và `GrantedAuthority` để thực thi quyền truy cập.

Điểm khó nhất **không nằm ở cách đọc một HTTP header**, mà là chứng minh **ai đã đưa header/principal vào request, họ có thực sự xác thực người dùng không, và thông tin đó có thể bị khách hàng giả mạo hay thay đổi ở bất kỳ hop nào không**. Nếu backend tin `X-User: admin` chỉ vì có header, bất kỳ người gọi trực tiếp hoặc gateway cấu hình sai nào cũng có thể mạo danh admin.

**Nguyên tắc:** xác minh **nguồn/bằng chứng tin cậy** trước, xác định **danh tính ổn định và phạm vi nhà phát hành** thứ hai, nạp **tài khoản/quyền theo chính sách server** thứ ba, rồi **kiểm tra tenant, hành động và tài nguyên** ở ứng dụng. Header do gateway đưa vào **không tự là bằng chứng mật mã**; HTTP container principal chỉ đáng tin khi container thực sự đã triển khai authentication; groups từ hệ thống tập trung chỉ là dữ kiện đầu vào cho policy, không phải giấy phép quản trị vô điều kiện.

Bài thuộc **Spring Security – federation → Xác thực qua proxy**, tập trung vào ba nguồn danh tính: **gateway/reverse proxy**, **Servlet container** và **access manager tập trung**; cách bảo vệ trust boundary, các lớp Spring Security pre-authentication, cách ánh xạ quyền, mã cấu hình Spring và ví dụ Java 17 chạy được, cùng checklist kiểm thử/vận hành.

## 1. Phân biệt authentication, pre-authentication và authorization

**Authentication** trả lời: “Người đang gửi request là ai, bằng chứng nào xác minh danh tính đó?”. **Pre-authentication** là tình huống hệ thống khác đã làm bước kiểm chứng, Spring nhận kết quả theo giao thức/tầng tích hợp được tin cậy. **Authorization** trả lời: “Danh tính đó được làm gì đối với tài nguyên cụ thể, trong tenant nào?”.

Ví dụ minh họa:

~~~text
Browser
  |
  | OIDC / SAML / Kerberos / session cookie với hệ thống SSO
  v
Access Gateway
  | 1. Kiểm chứng token hoặc session
  | 2. Xác định issuer + subject + assurance
  | 3. Xóa các identity headers do client tự gửi
  | 4. Gắn identity context đáng tin
  | 5. Kết nối backend qua kênh có xác thực
  v
Spring Boot Backend
  | 6. Chỉ nhận request từ gateway đã xác thực
  | 7. Đọc pre-authenticated principal
  | 8. Liên kết external identity -> local account
  | 9. Load roles/tenant membership theo allowlist
  | 10. Kiểm hành động và quyền trên từng object
  v
Business response
~~~

**Lưu ý:** `PreAuthenticatedAuthenticationProvider` theo Spring Security **không tự kiểm mật khẩu, chữ ký JWT hay SAML assertion**. Nó giả định bước external authentication đã diễn ra an toàn và chủ yếu nạp thông tin người dùng/quyền. Ranh giới ở bước 6 cần được thiết kế riêng.

## 2. Ba nguồn danh tính được đề bài đề cập

| Nguồn | Spring có thể đọc ở đâu? | Ai thật sự xác thực? | Nguy cơ nổi bật |
| --- | --- | --- | --- |
| **Gateway/reverse proxy** | Header do gateway đưa vào; đôi khi JWT/verified request attribute | Gateway/IdP hoặc service mesh | Header spoofing; backend bị gọi bypass |
| **Servlet/Jakarta EE container** | `HttpServletRequest.getUserPrincipal()`, `getRemoteUser()`, `isUserInRole()` | Container authentication realm, có thể dùng BASIC/FORM/CLIENT-CERT/SPNEGO/JASPIC theo cấu hình | Container principal giả định đã có dù container không bật security |
| **Access manager tập trung** | Header kiểu `SM_USER`, trusted application context, validated signed assertion/JWT | SiteMinder hoặc sản phẩm/quy tắc IAM được quản trị | Đổi trust namespace, role collision, phiên hết hạn/thay đổi quyền |
| **Spring OAuth2 Resource Server** | `Authorization: Bearer` JWT/opaque token | Spring tự kiểm token với issuer/JWK hoặc introspection | Audience/token type mismatch, giả mạo issuer |
| **Spring session** | `SecurityContext` lưu theo session strategy | Spring đã xác thực ở request trước | Phiên cũ, account disabled nhưng quyền chưa cập nhật |

**Phân biệt hai phương án:** nếu Spring **tự xác minh JWT access token**, đây là OAuth2 Resource Server authentication, **không nhất thiết là header-based pre-authentication**. Nếu gateway đã xác minh token rồi backend chỉ nhận identity headers, backend đang dùng **pre-auth trust contract** với gateway và phải có bảo vệ tương ứng.

## 3. Trust boundary là phần quan trọng nhất

Một sơ đồ hạ tầng an toàn phải cho thấy đường đi nào **được phép** và đường đi nào **bị chặn**:

~~~text
Internet
  |
  +----> Public Gateway / Access Proxy
  |            |
  |            | HTTPS/mTLS, authenticated gateway identity
  |            | overwrite trusted identity headers
  |            v
  |       Private Backend
  |       no public ingress
  |
  +--X--> Backend pod/VM trực tiếp
  |
  +--X--> Bypass qua alternate hostname/port/health endpoint
~~~

**Bốn lớp bắt buộc xem xét cùng nhau:**

1. **Network reachability:** backend không có public ingress/port/alternate route vượt gateway; Kubernetes NetworkPolicy, firewall, security groups hoặc service mesh authorization thực sự ngăn truy cập trực tiếp.
2. **Hop authentication:** backend xác nhận request tới từ gateway/service mesh được phép qua **mTLS identity** hoặc phương thức authentication đáng tin tương đương; **không chỉ nhìn IP hoặc `X-Forwarded-For`**.
3. **Header integrity:** gateway xóa mọi header identity do client cung cấp và đặt lại một **bộ header do chính gateway kiểm soát** sau successful authentication.
4. **Application identity mapping:** backend chỉ sử dụng subject/issuer/tenant từ trusted context, không tự gộp email hoặc chuyển raw upstream roles thành admin.

**“Mạng nội bộ” không phải bằng chứng người gọi là gateway.** Pod khác, developer VPN, SSRF, misconfigured ingress hoặc sidecar có thể mở đường bypass. Một hop bị bỏ sót làm toàn bộ hợp đồng pre-auth mất giá trị.

## 4. Giá trị identity header chỉ là dữ liệu nếu không có nguồn đáng tin

Ví dụ header thường gặp, **không phải tiêu chuẩn chung**:

~~~http
GET /app/invoices/42 HTTP/1.1
Host: service.internal.example.test
X-Verified-Subject: usr-8fa1
X-Verified-Issuer: https://sso.example.test
X-Verified-Auth-Method: mfa
X-Verified-Groups: finance-readers,finance-approvers
~~~

Đây chỉ là dữ liệu minh họa. Kẻ tấn công cũng có thể gửi cùng văn bản qua `curl` nếu backend nhận request trực tiếp.

**An toàn hơn:** gateway xác minh phiên người dùng, **loại bỏ trước** các header `X-Verified-*` do browser/client đưa vào, rồi ghi lại headers có contract rõ, ký hoặc bảo vệ đường truyền và xác thực gateway. Backend phải từ chối request không đến từ hop đã xác thực.

**Không chấp nhận:** 

- Chỉ kiểm `request.getHeader("X-Verified-Subject") != null`.
- Coi `X-Forwarded-For` hoặc `X-Real-IP` là bằng chứng người dùng đã được xác thực.
- Tin mọi request có header `X-Groups: admins`.
- Chấp nhận header từ một ingress nhưng không khóa port gốc của backend.
- Dùng browser cookie của gateway làm Spring identity nếu backend không thể xác thực cookie đó.

Header tên giống `SM_USER` hay `X-Authenticated-User` không có tính bảo mật nội tại. **Bảo đảm thuộc về hệ thống đặt header và đường truyền**, không thuộc tên.

## 5. Trách nhiệm của gateway/access proxy

Gateway có thể kiểm **OIDC authorization flow, OAuth bearer token, SAML session, Kerberos, client certificate** hoặc cookie do access manager phát. Sau xác minh, nó cần biến đổi kết quả thành một **identity contract** phù hợp backend.

Một contract nên định nghĩa ít nhất:

| Trường | Ví dụ | Quy tắc |
| --- | --- | --- |
| `auth_source` | `corp-gateway-v1` | Danh tính nguồn do backend cấu hình/trust |
| `issuer` | `https://id.example.test/realm/corp` | Nguồn định danh, không chọn tùy tiện từ request |
| `subject` | `user-1044` | Opaque, giữ exact string, không mặc định email |
| `client/actor` | `portal-web` | Ứng dụng thực sự gửi yêu cầu, khi cần audit |
| `auth_time` | Thời điểm xác thực | Dùng cho freshness policy, theo nghĩa hợp đồng |
| `assurance` | `mfa` hoặc mức tin cậy | Chỉ tin nếu gateway/IdP xác minh đúng semantics |
| `tenant_context` | `north` | Gợi ý hoặc context đã kiểm, **không tự cấp membership** |
| `groups` | `billing-readers` | Dữ kiện để SP map qua policy allowlist |
| `correlation_id` | ID truy vết không bí mật | Không dùng làm authentication credential |
| `session_id` | Định danh phiên có kiểm soát | Cẩn trọng PII/session hijack, không cần gửi nếu không dùng |

Tốt nhất định nghĩa **version của contract**, schema, encoding, format chuỗi, tính đa trị, max lengths, expiration và cách xử lý trường thiếu. Khi nhiều gateways cùng gửi tới một backend, xác định rõ **namespace/issuer/trust context** cho từng nguồn.

**Không nhận `X-User` từ client rồi dùng email để suy ra `issuer`.** Issuer và identity namespace là phần của trust policy chứ không chỉ profile data.

## 6. RequestHeaderAuthenticationFilter thực sự làm gì?

Trong Spring Security Servlet, `org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter`:

1. Đọc **principal** từ request header, mặc định là `SM_USER` (tương thích mô hình SiteMinder).
2. Có thể cấu hình `setPrincipalRequestHeader("X-Verified-Subject")`.
3. Mặc định khi thiếu header có thể ném `PreAuthenticatedCredentialsNotFoundException`; hành vi thay đổi được bằng `setExceptionIfHeaderMissing(...)`.
4. Tạo `PreAuthenticatedAuthenticationToken` chứa principal và credentials giả/được cấu hình, rồi đưa đến `AuthenticationManager`.
5. **Không kiểm chữ ký, mật khẩu, chứng chỉ client hoặc identity proof** chỉ vì header tồn tại.

Cảnh báo của chính Javadoc Spring Security: nếu sử dụng filter khi external authentication system không bảo vệ toàn bộ đường truy cập đến backend, kẻ tấn công có thể **tự chọn username** bằng cách đặt header.

### Cái gì không nằm trong filter?

- Không tự kiểm OAuth JWT issuer/audience.
- Không kiểm CAS Service Ticket.
- Không kiểm SAML assertion signature.
- Không đảm bảo mTLS gateway identity.
- Không thực hiện domain/tenant authorization.
- Không kiểm xem header groups là do ai đặt.
- Không tự chặn lối đi thẳng vào backend.
- Không xác minh container authentication realm.

Đó là các bảo đảm cần đến **hạ tầng, validator đúng protocol và application policy**.

## 7. AbstractPreAuthenticatedProcessingFilter và AuthenticationManager

`RequestHeaderAuthenticationFilter` và `J2eePreAuthenticatedProcessingFilter` dựa trên framework `AbstractPreAuthenticatedProcessingFilter`.

Luồng:

~~~text
HTTP request đã đi qua trusted external authentication
             |
             v
AbstractPreAuthenticatedProcessingFilter
  getPreAuthenticatedPrincipal(request)
  getPreAuthenticatedCredentials(request)
             |
             v
PreAuthenticatedAuthenticationToken (chưa fully authenticated)
             |
             v
AuthenticationManager / ProviderManager
             |
             v
PreAuthenticatedAuthenticationProvider
             |
             v
AuthenticationUserDetailsService
  local account lookup, account status, authorities
             |
             v
PreAuthenticatedAuthenticationToken (authenticated)
             |
             v
SecurityContext -> AuthorizationFilter / @PreAuthorize
~~~

**Đặt tên dễ nhầm:** `PreAuthenticatedAuthenticationProvider` về bản chất **chấp nhận rằng bên ngoài đã xác thực**, sau đó load `UserDetails` và kiểm account status. Không mô tả nó như một validator của HTTP identity header.

Provider thông thường đòi `principal` và `credentials` khác `null`; RequestHeaderAuthenticationFilter sử dụng một dummy credential khi không cấu hình credentialsRequestHeader. Dummy này **không phải mật khẩu user** và không có ý nghĩa chứng minh danh tính.

Nếu external system không đưa principal hoặc cung cấp principal không hợp lệ, phải **fail closed** thay vì tự gán guest/admin.

## 8. PreAuthenticatedAuthenticationProvider: tài khoản và quyền

Provider dùng `setPreAuthenticatedUserDetailsService(...)` để nhận `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>`. Loader có thể:

- Ánh xạ verified external subject → local account ID.
- Kiểm account vẫn enabled, chưa bị khóa/suspend.
- Đọc roles của local account từ database/authorization service.
- Áp giới hạn tenant/scope/caller.
- Chỉ giữ các `GrantedAuthority` nằm trong allowlist được phê duyệt.
- Không cho một identity pair đang thuộc local account khác được reassigned.
- Từ chối account chưa được liên kết nếu JIT provisioning không được phép.

Javadoc của provider nói rõ nó **không thực hiện authentication check đối với request**, vì upstream đã làm. Nó có thể ném `UsernameNotFoundException` hoặc exception khác khi không thể tìm hoặc chấp nhận local account.

**Không nhầm “đã nhận header” với “đã tìm được local account active”.** Ngay cả khi gateway xác nhận người dùng thành công, backend vẫn có thể phải từ chối vì account disabled, không thuộc tenant hoặc thiếu quyền.

## 9. UserDetailsService và AuthenticationUserDetailsService

`UserDetailsService` nhận `String username` và thường gọi database. `AuthenticationUserDetailsService<T extends Authentication>` nhận cả authentication token nên phù hợp khi cần context hoặc external authorities.

| Nhu cầu | Lựa chọn |
| --- | --- |
| Chỉ có một trusted issuer, subject unique và roles đều từ local DB | `UserDetailsService` + `UserDetailsByNameServiceWrapper` |
| Cần nguồn/trust context, tenant, actor, hoặc extra claims đã xác minh | Custom `AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>` hoặc custom AuthenticationProvider |
| Container có role names đã kiểm | `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` + mapping/authorization |
| Nhận `GrantedAuthoritiesContainer` đáng tin từ details | `PreAuthenticatedGrantedAuthoritiesUserDetailsService` có thể phù hợp |
| Raw gateway header chứa tên nhóm | **Không tự đưa thẳng** thành role; parse + allowlist + tenant checks |
| Có signed JWT access token do IdP/AS phát | Cân nhắc `oauth2ResourceServer().jwt()`, thay vì parser header thủ công |

**PreAuthenticatedGrantedAuthoritiesUserDetailsService** chỉ lấy authorities từ `token.getDetails()` nếu details implements `GrantedAuthoritiesContainer`. Nó **không tự đọc mọi request header hoặc kiểm rằng danh sách role là đáng tin**. Nếu details do input do browser có thể chi phối, đưa thẳng vào UserDetails là nguy cơ privilege escalation.

## 10. Java EE/Jakarta Servlet container: getUserPrincipal và isUserInRole

Trong container-authenticated request:

~~~java
// Mảnh code thuộc Servlet/Controller đã được container bảo vệ:
java.security.Principal principal = request.getUserPrincipal();
String userName = principal == null ? null : principal.getName();

boolean isAuditor = request.isUserInRole("auditor");
~~~

Các API Servlet cung cấp **identity/role do container quản lý**. Nếu container chưa cấu hình security constraint/realm/authentication mechanism thật, `getUserPrincipal()` có thể là `null`, còn các methods role không chứng minh người dùng đã login.

Spring có `org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter` để đọc username từ `getUserPrincipal()`, thay vì tin identity HTTP header gửi từ client.

### Nguồn role từ container

`J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` kiểm một danh sách **mappable roles đã định nghĩa** bằng `request.isUserInRole(role)`. Sau đó `Attributes2GrantedAuthoritiesMapper` chuyển chúng thành authorities (thường thêm `ROLE_`). Danh sách roles phải được quản trị và **giới hạn**; container không cung cấp một API chuẩn để liệt kê mọi role không giới hạn.

**Không suy ra mọi role của mọi deployment container đều giống role nghiệp vụ của ứng dụng.** `isUserInRole("admin")` chỉ chứng minh container đã map một role có tên đó theo container security configuration; ứng dụng vẫn cần kiểm entitlement/tenant/object.

## 11. Ví dụ container-authenticated flow

Một application server/WAS/WildFly/Tomcat-with-realm có thể xác thực user bằng policy của container rồi cung cấp `Principal` trên ServletRequest.

~~~text
Browser
   |
   | HTTPS, container-managed auth mechanism
   v
Servlet Container
   | authenticate client
   | set HttpServletRequest userPrincipal + roles
   v
J2eePreAuthenticatedProcessingFilter
   | read container principal
   v
PreAuthenticatedAuthenticationProvider
   | load local account / authorities
   v
Spring SecurityContext
   |
   v
Tenant + resource authorization
~~~

**Điều kiện:** container phải thực sự cấu hình authentication và enforce access trước Servlet filter. Một plain Tomcat chưa bảo vệ `/app/**` không tự bảo đảm pre-authentication chỉ vì trong Java code có method `getUserPrincipal()`.

### Container và gateway có thể dùng chung?

Có, nhưng phải quyết định ai là **source of truth**: gateway kiểm JWT rồi container đặt principal, hay container có realm riêng? Nếu container nhận principal từ reverse proxy header, trust boundary vẫn là gateway; `getUserPrincipal()` không thần kỳ biến header giả thành bảo mật. Không bật hai providers với logic fallback vô điều kiện khiến một nguồn kém tin cậy vượt nguồn mạnh.

## 12. Access manager tập trung: SiteMinder, SSO proxy, access broker

Các hệ thống như SiteMinder hoặc access proxies doanh nghiệp có thể:

1. Redirect tới centralized login.
2. Kiểm session cookie/token tại proxy/policy server.
3. Áp access policy ở gateway.
4. Truyền principal vào `SM_USER` hoặc một identity context đã được bảo vệ.
5. Backend mapping về local account và quyền.

**Mô hình SiteMinder** là một ví dụ nổi tiếng trong Spring Security: `RequestHeaderAuthenticationFilter` mặc định dùng `SM_USER`. Đây **không phải một chuẩn liên thông bảo mật**: mỗi nhà cung cấp có phương thức truyền attributes, signing, proxy chaining và session lifecycle khác nhau.

**Access manager có thể quyết định quyền truy cập URL**, nhưng đó **không thay thế quyền business object** trong ứng dụng. Gateway biết người dùng được vào `/app/invoices` không có nghĩa được đọc **hóa đơn của mọi tenant**. Cần phân quyền tại backend.

Nếu access manager cấp một signed token cho backend thay vì header trần, hãy xem xét **verify token tại backend** để có cryptographic issuer/audience/expiry guarantee. Không lấy username từ payload token đã Base64-decode rồi giả là authenticated.

## 13. Header spoofing: một request độc hại trông như thế nào?

~~~http
GET /app/admin/users HTTP/1.1
Host: service.internal.example.test
X-Verified-Subject: administrator
X-Verified-Groups: admin,superuser
~~~

Một client có thể tự tạo request như trên. Nếu backend được gọi trực tiếp và chỉ kiểm header, kẻ tấn công có thể **giả danh administrator**.

### Cấu hình phải bảo vệ nhiều lớp

- **Strip:** tại cổng public, xóa tất cả inbound identity headers, kể cả các alias/case variants được runtime normalize.
- **Rewrite:** đặt lại identity headers **chỉ sau successful authentication**, không giữ giá trị bất kỳ do client gửi.
- **Authenticate hop:** backend chỉ tin gateway đã được xác thực bằng mTLS/service identity hoặc cơ chế tương đương.
- **Network deny:** không có đường trực tiếp tới pod/backend port.
- **Header contract:** không chấp nhận duplicate/conflicting headers hoặc header chứa newline/control chars/giá trị quá lớn.
- **Scope:** thông tin issuer/subject/tenant thuộc nguồn nào, có được dùng ở service này không?
- **Authorization:** ngay cả identity đúng cũng không nhận role vượt policy.

**Không chỉ dựa vào hostname của reverse proxy trong `X-Forwarded-Host` hoặc IP trong `X-Forwarded-For`**, vì những fields này chỉ đáng tin khi một trusted proxy đã sanitize chúng.

## 14. Kết nối gateway–backend qua mTLS

**Mutual TLS (mTLS)** có thể giúp backend xác thực identity của gateway/service mesh peer, trong khi gateway xác thực server certificate của backend. Khi dùng mTLS làm bằng chứng gateway:

1. Certificate issuance dựa trên PKI/trust domain được kiểm soát.
2. Backend kiểm certificate chain, SAN/service identity và trust policy của peer.
3. Chỉ những gateway identities được cho phép mới được kết nối tới protected backend route.
4. Nếu TLS được terminate ở ingress/sidecar, phải bảo đảm hop sau đó cũng được bảo vệ đúng và không thể bypass sidecar.
5. Certificate rotation/revocation phải hoạt động.
6. Tránh chấp nhận mọi certificate có chữ ký của một CA rộng nếu chỉ một gateway được phép.

**mTLS chỉ xác thực gateway/hop**, **không tự chứng minh end-user**. Gateway vẫn cần chứng minh đã kiểm session/JWT/OIDC/SAML đúng và identity header được gắn theo kết quả đó.

**Đường đi đầy đủ:** “gateway đã xác thực user” **AND** “backend xác thực đây thật là gateway” **AND** “backend giới hạn quyền user”.

## 15. Signed assertion/JWT: một thay thế tốt hơn header trần trong nhiều kiến trúc

Một gateway có thể chuyển tiếp một **signed identity assertion** hoặc JWT access token đã được phát cho backend. Backend dùng validator để kiểm:

- Signature với trust anchor/JWKS/allowed algorithms đúng issuer.
- `iss` là issuer được phê duyệt.
- `aud` bao gồm backend/API hiện tại.
- `exp`, `nbf`, thời hạn token và clock skew giới hạn.
- Token type/purpose phù hợp, chống lấy ID Token dùng như API Access Token.
- `sub` là stable subject trong phạm vi issuer.
- `scope` hoặc claims đã được định nghĩa theo contract, không auto-admin.
- Actor/client, `azp` hoặc delegation context khi policy cần.
- Replay/freshness/revocation theo mức rủi ro.

Nếu ứng dụng tự xác minh JWT access token từ `Authorization: Bearer`, trong Spring thường nên dùng **`oauth2ResourceServer().jwt()`**. Nếu cần xử lý JWT assertion độc lập từ gateway, phải có trust policy/validator rõ; **đừng tự parse Base64 và gọi đó là chữ ký hợp lệ**.

**OIDC ID Token** được phát cho OIDC client, không được dùng làm API access token mặc định. Cùng một chữ ký hợp lệ vẫn có thể bị dùng sai audience nếu application không kiểm chính xác.

## 16. Thiết kế identity key: username không đủ trong multi-provider

Trường hợp nhiều gateways/tenants/identity providers:

~~~text
Gateway Corp phát subject "123" cho người A.
Gateway Partner phát subject "123" cho người B.

Nếu backend lookup chỉ bằng subject = "123":
  Có nguy cơ gộp nhầm A và B.

Khóa đúng:
  (trusted-source/issuer, subject)
    -> local_account_id
~~~

Nếu upstream dùng OIDC, tiêu chuẩn cho khóa ổn định là **`(iss,sub)` của ID Token đã được OP xác minh**. Khi gateway chuyển tiếp danh tính, backend cần một **verified issuer context** từ cấu hình/contract hoặc signed claims, không dùng email làm khóa.

Nếu container authentication cho `getUserPrincipal().getName()`, ứng dụng phải biết **container realm/trust namespace**. Username `alice` từ container A và từ container B không tự là cùng account.

Ví dụ mô hình DB:

~~~sql
CREATE TABLE federated_identity (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  local_account_id BIGINT NOT NULL REFERENCES local_account(id),
  trusted_source VARCHAR(128) NOT NULL,
  issuer VARCHAR(512) NOT NULL,
  subject VARCHAR(255) NOT NULL,
  linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (trusted_source, issuer, subject)
);
~~~

Đây là ví dụ PostgreSQL, giả định bảng `local_account` đã tồn tại. Với identity strings, cần **case-sensitive exact matching** theo issuer/provider contract và DB collation đúng; không tự lowercase subject hoặc bỏ path của issuer.

**Email, display name, preferred_username, phone number không là khóa định danh bất biến xuyên mọi providers.** Liên kết hai identities tới cùng account phải có chứng cứ/linking workflow được phê duyệt.

## 17. Nhận quyền từ gateway: direct mapping nguy hiểm khi nào?

Giả sử gateway chuyển:

~~~text
X-Verified-Groups: finance,operations,ROLE_ADMIN
~~~

Một cách làm sai:

~~~java
// KHÔNG áp dụng cho untrusted hoặc unrestricted group header.
for (String group : rawGroups) {
    authorities.add(new SimpleGrantedAuthority(group));
}
~~~

Nếu upstream group có quyền tự đặt tên hoặc gateway chỉ chuyển raw claims từ IdP không được kiểm soát, user có thể trở thành `ROLE_ADMIN` ở ứng dụng.

**Nguyên tắc role mapping:**

1. **Allowlist theo issuer/trusted_source và application**.
2. Chỉ map group IDs đã được app owner phê duyệt.
3. Kiểm **tenant** của local account, không tin tenant trong request để tự cho membership.
4. Thực hiện exact matching/encoding theo contract; không regex “chứa admin”.
5. Phân biệt group/department với scoped permissions.
6. Role nhạy cảm yêu cầu entitlement nội bộ hoặc policy có assurance/step-up phù hợp.
7. Khi thiếu group hoặc attributes sai, **fail closed** cho quyền đặc quyền.
8. Giới hạn số nhóm/độ dài/kiểu; tránh header overflows và memory abuse.
9. Revocation/role changes có thể xảy ra sau khi tạo session/JWT; cần freshness strategy.
10. Không đưa tên group raw thành metric labels/PII logs.

**Mô hình tốt:** external groups là tín hiệu đầu vào; **backend policy** quyết định GrantedAuthority. Với hành động nhạy cảm, xét quyền ở **resource-level** mỗi request.

## 18. Servlet container roles: mapping có kiểm soát

Một Servlet container có thể hiểu các vai trò `auditor`, `billing-editor` và `container-admin`. Spring J2EE preauth details có thể hỏi:

~~~java
// Mảnh code chạy trong Servlet context đã cấu hình container auth:
boolean auditor = request.isUserInRole("auditor");
boolean billingEditor = request.isUserInRole("billing-editor");
~~~

Trong Spring preauth framework, `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` thu thập các roles **được khai báo trước**; `Attributes2GrantedAuthoritiesMapper` chuyển sang Spring authorities. **Không liệt kê hoặc nhận arbitrary role names** từ request parameters.

Bảng policy ví dụ:

| Container role | Authority nội bộ | Điều kiện bổ sung |
| --- | --- | --- |
| `auditor` | `ROLE_VIEWER` | Account active, tenant membership |
| `billing-editor` | `ROLE_EDITOR` | Membership và đối tượng được phép sửa |
| `container-admin` | Không tự map `ROLE_ADMIN` | App admin phải được phê duyệt riêng |
| Không có role | Chỉ quyền cơ sở nếu app policy cho phép | Không cấp quyền đặc biệt |

**Container role không phải một access token OAuth**, cũng không làm việc kiểm tra CSRF/XSS/session trở nên không cần thiết.

## 19. Ví dụ Spring Security 6.x: nhận principal từ gateway đã xác thực

Ví dụ sau dành cho **Spring Boot 3.x/Spring Security 6.x Servlet**, triển khai cho một API nội bộ được gateway **bảo vệ ở tầng mạng và xác thực mTLS/service identity**. Để dễ học, Spring lọc một header cố định `X-Verified-Subject` rồi ánh xạ sang tài khoản/quyền từ **local trusted directory**. Ví dụ **không tự triển khai mTLS validation hay header sanitization**: đó là **điều kiện triển khai bắt buộc ở edge/ingress/mesh**, không phải thứ Spring header filter có thể thay thế.

File `src/main/java/com/example/security/GatewayPreAuthSecurity.java`:

~~~java
package com.example.security;

import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.AuthenticationUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.Http403ForbiddenEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;

@Configuration
public class GatewayPreAuthSecurity {

    // Ứng dụng phải cung cấp implementation/bean thật từ database.
    public interface TrustedAccountDirectory {
        LinkedAccount findByExternalIdentity(String trustedSource, String subject);
    }

    public record LinkedAccount(
            String localAccountId, boolean active, Set<String> appRoles) {}

    private static final String TRUSTED_SOURCE = "corp-gateway";
    private static final Set<String> ROLE_ALLOWLIST =
            Set.of("ROLE_VIEWER", "ROLE_APPROVER");

    @Bean
    AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>
            gatewayAccountLoader(TrustedAccountDirectory directory) {

        return token -> {
            String externalSubject = token.getName();
            if (externalSubject == null || externalSubject.isBlank()) {
                throw new UsernameNotFoundException("Missing gateway subject");
            }

            LinkedAccount account = directory.findByExternalIdentity(
                    TRUSTED_SOURCE, externalSubject);
            if (account == null) {
                throw new UsernameNotFoundException(
                        "No verified external identity link");
            }
            if (!account.active()) {
                throw new DisabledException("Local account is disabled");
            }

            // Authorities do local DB/policy cấp, KHÔNG lấy từ raw headers.
            List<GrantedAuthority> granted =
                    account.appRoles().stream()
                            .filter(ROLE_ALLOWLIST::contains)
                            .map(role -> (GrantedAuthority)
                                    new SimpleGrantedAuthority(role))
                            .toList();

            // Password marker không dùng để xác thực pre-auth.
            // Không dùng UserDetails này trong password-based login.
            return new User(
                    account.localAccountId(),
                    "{noop}UNUSED_PREAUTH_PASSWORD",
                    true, true, true, true, granted);
        };
    }

    @Bean
    PreAuthenticatedAuthenticationProvider gatewayProvider(
            AuthenticationUserDetailsService<PreAuthenticatedAuthenticationToken>
                    gatewayAccountLoader) {

        PreAuthenticatedAuthenticationProvider provider =
                new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(gatewayAccountLoader);
        provider.setThrowExceptionWhenTokenRejected(true);
        return provider;
    }

    @Bean
    SecurityFilterChain privateGatewayChain(
            HttpSecurity http,
            PreAuthenticatedAuthenticationProvider gatewayProvider)
            throws Exception {

        ProviderManager manager = new ProviderManager(gatewayProvider);

        RequestHeaderAuthenticationFilter preAuth =
                new RequestHeaderAuthenticationFilter();
        preAuth.setPrincipalRequestHeader("X-Verified-Subject");
        preAuth.setExceptionIfHeaderMissing(true);
        preAuth.setContinueFilterChainOnUnsuccessfulAuthentication(false);
        preAuth.setAuthenticationManager(manager);

        return http
                .securityMatcher("/private/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(new Http403ForbiddenEntryPoint()))
                .authenticationProvider(gatewayProvider)
                .addFilterBefore(preAuth,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

### Điều kiện để ví dụ an toàn và hoạt động

1. **Gateway phải authenticates end user**, sanitize/overwrite header và không gửi request anonymous đến `/private/**`.
2. Backend **không được truy cập trực tiếp** và có mTLS/service authorization trước Servlet request; nếu không, code trên **dễ bị spoof**.
3. Mỗi external subject phải được liên kết bằng **trusted source + subject** tới local account. Nếu có nhiều issuers, mở rộng thành **issuer+subject** và versioned trust contract.
4. App phải implement `TrustedAccountDirectory` và cung cấp bean; ví dụ **không tạo database hoặc account provisioning**.
5. Role mapping lấy từ local trusted DB, không từ `X-Verified-Groups`.
6. Một request trong chain này phải dùng đúng identity header; khi thiếu/invalid không tự chuyển sang form login. Bảo đảm failure handling theo phiên bản Spring.
7. Với browser có cookie ở gateway và các method thay đổi state, **CSRF vẫn phải được phân tích/bảo vệ**; stateless backend không tự loại bỏ CSRF nếu browser tự gửi credential đến gateway.
8. Nếu có những routes khác, **SecurityFilterChain khác phải bảo vệ chúng**; không coi `securityMatcher("/private/**")` là bảo vệ toàn ứng dụng.
9. Version/JDK/dependency phải phù hợp; đây là class cho **dự án Spring**, **không** phải Java standalone.
10. Cấu hình các guardrails hạ tầng **trước** khi bật chain này ở production; Spring không tự chứng minh gateway identity.

**Nhược điểm minh họa:** external issuer đang cố định trong `TRUSTED_SOURCE`. Với một gateway gộp nhiều IdPs, phải thêm issuer vào identity link và bảo đảm issuer được xác minh bởi gateway/AS. Không dùng user-supplied issuer header như nguồn lựa chọn trust provider.

## 20. Container pre-auth trong Spring: cấu hình dạng thành phần

Nếu Servlet container đã xác thực bằng cơ chế của nó, Spring có thể dùng `J2eePreAuthenticatedProcessingFilter` thay vì đọc gateway header:

~~~java
// Mảnh bean wiring thuộc dự án Spring; requires authenticationManager
// và container-managed authentication/realm đã được cấu hình thật.
J2eePreAuthenticatedProcessingFilter containerFilter =
        new J2eePreAuthenticatedProcessingFilter();
containerFilter.setAuthenticationManager(authenticationManager);

// Thêm vào SecurityFilterChain bằng addFilterBefore(...) theo
// filter ordering của dự án và bảo vệ URL container ở tầng server.
~~~

**Lưu ý:** `J2eePreAuthenticatedProcessingFilter` chỉ lấy principal của container. Để lấy role đã xác thực ở container, cần cấu hình `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` với danh sách mappable roles và mapper, hoặc dùng local UserDetailsService; **không mặc định mọi role đã được đọc từ container**.

Nếu container có `getUserPrincipal() == null` hoặc `isUserInRole() == false`, không tự tạo principal/role “anonymous admin” và không lấy một header raw để lấp chỗ trống. Cấu hình security constraints/realm theo app-server và validate E2E.

## 21. Khi nào chọn OAuth2 Resource Server thay vì header pre-auth?

| Tình huống | Hướng thiết kế thường hợp lý |
| --- | --- |
| Public API nhận signed JWT access token có issuer/aud rõ | **Spring OAuth2 Resource Server JWT** |
| Public API dùng opaque token | **Spring Resource Server opaque token introspection** |
| Gateway đã xác thực browser SSO, backend private không thể bypass, contract headers được bảo vệ | **Pre-auth header** có thể phù hợp |
| Servlet container được quản trị, đã xác thực request và có principal/roles chuẩn | **Container pre-auth** |
| Access manager đã có signed assertion dành cho service | **Validate signed assertion** hoặc token tại backend |
| Nhiều independent clients/tenants/cross-network hops | Ưu tiên **cryptographically verifiable tokens**, audience và issuance policy |
| Có user identity nhưng cần delegated authorization tới API khác | Cần OAuth2 access tokens/delegation policy phù hợp, **không tự gửi forwarded user header xuyên mọi APIs** |
| Service-to-service không có người dùng | **mTLS/service identity hoặc OAuth client_credentials**, không giả human username |

Một header pre-auth contract chỉ nên dùng trong **rất rõ ràng trust domain**; nó không tạo một giao thức identity federation tiêu chuẩn xuyên mọi network boundaries.

## 22. Session và principal changes: điểm dễ bỏ qua

`AbstractPreAuthenticatedProcessingFilter` có các tùy chọn:

- `setCheckForPrincipalChanges(true)`: so principal incoming với Authentication hiện tại; khi thay đổi, trigger re-authentication.
- `setInvalidateSessionOnPrincipalChange(true)`: khi enabled và phát hiện principal change, có thể invalidate session theo cơ chế được hỗ trợ.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)`: không âm thầm cho filters khác thử authentication sau một failure từ AuthenticationManager.

Những tùy chọn này cần xem cùng session strategy. **Mặc định**, nếu SecurityContext đã có Authentication, pre-auth filter có thể không kiểm lại header principal ở mọi request. Nguy cơ trong browser có session:

~~~text
Request 1: gateway subject = alice
  Spring session lưu Authentication của alice

Gateway logout alice, login bob trong cùng browser
Request 2: gateway subject = bob
  Nếu app vẫn dùng Authentication cũ mà không so principal,
  backend có thể xử lý request của bob dưới identity alice.
~~~

**Giải pháp theo loại app:**

- Stateless API: xử lý identity từ authenticated hop **mỗi request** và không giữ stale login state ngoài ý muốn.
- Browser app stateful: xem xét principal-change detection và session invalidation, hoặc tích hợp logout/session events.
- Account/tenant changes: khi user bị khóa hoặc đổi quyền, có session revocation/role version check.
- Nếu `Authentication.getName()` là **local account ID** còn header là **external subject**, cơ chế so sánh principal mặc định có thể xem chúng khác nhau. Cần **custom mapping/comparator đáng tin** hoặc lựa chọn session strategy phù hợp, không bật cờ bừa khiến mọi request reauthenticate.
- Hệ có nhiều logins: không kết hợp formLogin và header preauth trong cùng trust boundary thiếu separation; nguy cơ bypass đã được Javadoc cảnh báo.

**Không chỉ đặt `SessionCreationPolicy.STATELESS` rồi mặc định mọi cookie và CSRF risk biến mất**. Browser có thể vẫn gửi gateway SSO cookie, và gateway chuyển yêu cầu vào backend.

## 23. Lấy roles từ hệ thống truy cập tập trung: bảo đảm nào là đủ?

Một access manager thường đã tính roles/entitlements theo policy. Có ba cách:

**A. Backend nạp quyền từ DB của mình (thường đơn giản để kiểm soát):**
- Chỉ nhận verified subject và trust source.
- Map tới local account.
- Load nhóm/quyền server-side, có account status, tenant checks.
- Có thể dùng gateway group claims làm tín hiệu bổ sung đã được kiểm.

**B. Backend nhận roles đã ký/xác minh từ access manager:**
- Contract rõ issuer, service audience, entitlement version, TTL, role naming/tenant.
- Backend validate token/proof hoặc dựa vào trusted channel kèm gateway guarantee.
- Mapper giới hạn role names/scope.
- Chính sách thu hồi khi access manager thay group.

**C. Backend hỏi authorization service tại thời điểm request:**
- Dùng cho quyền nhạy cảm hoặc scope thay đổi nhanh.
- Có timeout/fail-closed, caching TTL ngắn và audit.
- Request bao gồm authenticated subject, actor, tenant, action, resource.
- Không chỉ tin câu trả lời gateway “user được vào URL”.

### Không tạo một “role” toàn cục xuyên tenants

Ví dụ group `finance-approvers` ở tenant North không nhất thiết cho quyền approve ở South. Một token/header role cấp cho một ứng dụng khác cũng không tự dùng được trong ứng dụng hiện tại.

**Công thức tư duy:** quyền thực = **identity hợp lệ** ∩ **account active** ∩ **tenant membership** ∩ **role/permission hợp lệ** ∩ **resource rule** ∩ **assurance/freshness yêu cầu**.

## 24. Java 17 độc lập: kiểm chứng trust context và quyền

Ví dụ Java 17 dưới đây chạy thuần JDK để kiểm **logic quyết định sau khi external system đã cung cấp chứng cứ xác thực**. Nó cố ý cho upstream đưa claim `ROLE_ADMIN` để chứng minh backend **không cấp admin nếu quyền local không có**.

**File:** `PreAuthTrustBoundaryDemo.java`

~~~java
import java.util.Set;

public class PreAuthTrustBoundaryDemo {

    record ExternalIdentity(String source, String issuer, String subject) {}

    record Evidence(
            boolean trustedHop,
            boolean upstreamAuthenticated,
            ExternalIdentity identity,
            Set<String> externalClaims) {}

    record LocalAccount(
            String id,
            ExternalIdentity linkedIdentity,
            boolean active,
            Set<String> tenants,
            Set<String> appAuthorities) {}

    static String authorize(
            Evidence evidence,
            LocalAccount account,
            String tenant,
            String requiredAuthority) {

        if (!evidence.trustedHop()) {
            return "DENY_UNTRUSTED_HOP";
        }
        if (!evidence.upstreamAuthenticated()) {
            return "DENY_NO_UPSTREAM_AUTH";
        }
        if (evidence.identity() == null
                || evidence.identity().issuer() == null
                || evidence.identity().subject() == null
                || evidence.identity().subject().isBlank()) {
            return "DENY_INVALID_IDENTITY";
        }
        if (!evidence.identity().equals(account.linkedIdentity())) {
            return "DENY_IDENTITY_MISMATCH";
        }
        if (!account.active()) {
            return "DENY_DISABLED";
        }
        if (!account.tenants().contains(tenant)) {
            return "DENY_TENANT";
        }
        if (!account.appAuthorities().contains(requiredAuthority)) {
            return "DENY_AUTHORITY";
        }

        // externalClaims cố ý KHÔNG được dùng để tự cấp quyền.
        return "ALLOW " + account.id();
    }

    public static void main(String[] args) {
        ExternalIdentity user = new ExternalIdentity(
                "gateway-corp", "https://id.example.test", "u-42");

        LocalAccount active = new LocalAccount(
                "acct-7", user, true,
                Set.of("north"),
                Set.of("ROLE_VIEWER"));

        Evidence verified = new Evidence(
                true, true, user, Set.of("ROLE_ADMIN"));

        System.out.println("Valid viewer: "
                + authorize(verified, active, "north", "ROLE_VIEWER"));
        System.out.println("Claimed admin: "
                + authorize(verified, active, "north", "ROLE_ADMIN"));

        Evidence directCall = new Evidence(
                false, true, user, Set.of("ROLE_ADMIN"));
        System.out.println("Direct bypass: "
                + authorize(directCall, active, "north", "ROLE_VIEWER"));

        Evidence noUpstreamProof = new Evidence(
                true, false, user, Set.of());
        System.out.println("Unverified upstream: "
                + authorize(noUpstreamProof, active, "north", "ROLE_VIEWER"));

        ExternalIdentity otherIssuer = new ExternalIdentity(
                "gateway-partner", "https://partner.example.test", "u-42");
        Evidence wrongIdentity = new Evidence(
                true, true, otherIssuer, Set.of());
        System.out.println("Same sub wrong source: "
                + authorize(wrongIdentity, active, "north", "ROLE_VIEWER"));

        System.out.println("Wrong tenant: "
                + authorize(verified, active, "south", "ROLE_VIEWER"));

        LocalAccount disabled = new LocalAccount(
                "acct-7", user, false,
                Set.of("north"),
                Set.of("ROLE_VIEWER"));
        System.out.println("Disabled account: "
                + authorize(verified, disabled, "north", "ROLE_VIEWER"));
    }
}
~~~

Chạy với **JDK 17 trở lên**:

~~~bash
javac PreAuthTrustBoundaryDemo.java
java PreAuthTrustBoundaryDemo
~~~

**Stdout chính xác:**

~~~text
Valid viewer: ALLOW acct-7
Claimed admin: DENY_AUTHORITY
Direct bypass: DENY_UNTRUSTED_HOP
Unverified upstream: DENY_NO_UPSTREAM_AUTH
Same sub wrong source: DENY_IDENTITY_MISMATCH
Wrong tenant: DENY_TENANT
Disabled account: DENY_DISABLED
~~~

### Diễn giải

- **Valid viewer:** hop và upstream đều được xác thực, external identity linked đúng local account, có quyền xem North.
- **Claimed admin:** gateway có claim ROLE_ADMIN nhưng app local chỉ cho ROLE_VIEWER nên không được nâng quyền.
- **Direct bypass:** request trực tiếp không có bằng chứng hop đáng tin bị chặn trước khi xét identity.
- **Unverified upstream:** gateway/hop không chứng minh đã xác thực người dùng → từ chối.
- **Same sub wrong source:** cùng chuỗi subject nhưng issuer/source khác không được tự nối account.
- **Wrong tenant:** role toàn cục không bỏ qua tenant membership.
- **Disabled account:** user xác thực upstream thành công nhưng backend vẫn chặn local account disabled.

**Giới hạn cực kỳ quan trọng:** hai boolean `trustedHop` và `upstreamAuthenticated` là **giả định đã có evidence sau xác minh** để dạy policy. Chương trình **không chứng thực mTLS/JWT/session/gateway**, không phân tích headers, không có DB hoặc network. Trong production **không được lấy hai boolean này từ request parameters/headers**; chúng phải do trusted security middleware/validator cung cấp. Đây **không phải một Spring AuthenticationProvider**, và không được triển khai nó như filter bảo mật production.

## 25. Lỗi khi dùng request attributes và Forwarded headers

Không chỉ header mà **request attributes** cũng cần ranh giới tin cậy. Một filter nội bộ có thể gắn:

~~~java
// Mảnh Servlet code trong trusted upstream middleware:
request.setAttribute("verifiedPrincipal", verifiedUserId);
~~~

Spring `RequestAttributeAuthenticationFilter` đọc một request attribute nhất định, nhưng **chỉ an toàn khi attribute do một middleware đáng tin, chạy đúng thứ tự và không bị client điều khiển**. Nếu một component khác chuyển raw client input thành attribute, đó chỉ là đổi nơi lưu untrusted data.

**Forwarded headers** (`Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`) chủ yếu mô tả hop/network/URL, **không phải identity proof**. Spring `ForwardedHeaderFilter` có thể xử lý các giá trị này để tính URL gốc, nhưng **không xác thực end user**. Nếu trusted proxy không strip/rewrite headers, chúng có thể bị spoof và làm sai redirect URI, origin, callback hoặc audit log.

### HTTP header normalization và duplicate headers

Các proxy, ingress, container có thể xử lý khác nhau với:
- Hoa/thường của tên header.
- Dấu gạch ngang so với underscore.
- Header bị lặp nhiều lần hoặc nhiều giá trị.
- Ký tự điều khiển và newline, giá trị Unicode.
- Header bị gộp qua nhiều proxies hoặc bị truncate.

**Không xây identity contract từ tên header tùy tiện mà không kiểm pipeline thật.** Có các test độc lập gửi duplicate, mixed-case và spoofing variants qua tất cả hops.

## 26. Reverse proxy/mesh topology: các bypass cần phát hiện

Một thiết kế trông đúng trên sơ đồ có thể có các đường phụ:

| Đường vào | Nguy cơ | Cách kiểm |
| --- | --- | --- |
| Public ingress → auth gateway → backend | Đường chính | Kiểm authenticated gateway hop và header rewrite |
| Public ingress → backend service khác path | Bypass auth | Kiểm routing và policy theo host/path |
| Backend NodePort/LoadBalancer cũ | Gọi thẳng backend | Xóa ingress hoặc firewall deny |
| Kubernetes pod-to-pod | Pod nội bộ mạo danh gateway | NetworkPolicy/service-mesh authorization, mTLS peer identity |
| Internal VPN → backend admin port | Bypass gateway | ACL, authentication riêng cho admin interface |
| Health/metrics endpoint | Tiết lộ thông tin/role headers | Tách endpoint, access control phù hợp |
| HTTP callback/webhook | Dùng route không qua auth gateway | Signature/mTLS riêng và SecurityFilterChain tách biệt |
| Service mesh sidecar → app plaintext localhost | Local bypass hoặc misrouted traffic | Chỉ nhận từ sidecar, container isolation và policy |
| Background queue consumer | Không có HTTP gateway | Dùng service identity và domain auth riêng |
| Test/staging hostname trỏ production | Bypass trust contract | Allowlist host và đổi cấu hình/secret tách môi trường |

**Network allowlist theo IP chỉ là một lớp**, có thể thay đổi khi autoscaling/proxy và không chứng minh end-user. Trong Zero Trust, ưu tiên identity/authentication của workload và policy liên tục, không chỉ “nằm trong VPC”.

## 27. Thời gian sống, logout và thu hồi quyền

Ở kiến trúc gateway pre-auth thường có ít nhất **ba vòng đời**:

1. **Phiên/token tại gateway/IdP:** có expiry, refresh, logout và account disable policy riêng.
2. **Spring Authentication/local session:** có thể giữ UserDetails/authorities snapshot nếu application có session.
3. **Local account/tenant permissions:** có thể đổi độc lập với cả hai bên trên.

Ví dụ:

~~~text
09:00 User SSO login tại gateway
09:01 Gateway forward verified principal; Spring tạo session
09:15 Admin rút ROLE_APPROVER của user
09:16 Spring session vẫn có authority cũ nếu không refresh/revoke
09:30 Gateway SSO session hết hạn
09:31 Nếu backend còn đường truy cập trực tiếp hoặc session cũ,
      nguy cơ sử dụng identity/role cũ nếu policy thiếu
~~~

Đây là timeline minh họa. **Không mặc định gateway logout sẽ ngay lập tức invalidate mọi Spring sessions**, hay thay đổi groups sẽ được đồng bộ mọi request.

Cơ chế cần xét:

- **Stateless per-request preauth:** đánh giá trusted gateway identity trên từng request.
- **Short local session:** giảm độ trễ thu hồi nếu app dùng cookie/session.
- **Revalidation/entitlement lookup:** quyền nhạy cảm kiểm DB/authorization service tại request.
- **Revocation events:** IdP/gateway có thể báo logout/disabled account tới service, nhưng cần triển khai và test.
- **Account/role version:** session hoặc token chứa version; backend kiểm version hiện tại.
- **Gateway assertion TTL:** chỉ tin token/proof còn thời hạn với đúng audience.
- **Principal changes:** một browser từ user A sang user B không được giữ A trong Spring SecurityContext.
- **Multi-node:** session/role cache invalidation phải có hiệu lực trên mọi pods.

**Chỉ thay đổi giá trị header không đảm bảo Spring UserDetails session tự cập nhật**, nhất là khi filter không kiểm principal change vì SecurityContext đã có Authentication.

## 28. CSRF, cookies, OAuth scopes và MFA không được bỏ qua

**Header pre-auth không tự miễn CSRF.** Nếu browser tự động gửi gateway SSO cookie tới access proxy, kẻ tấn công có thể cố kích hoạt request thay đổi state từ origin khác. Gateway và backend phải có **CSRF defense phù hợp browser flow**, SameSite/cookie policy, Origin/Referer validation theo use case, và không tin chỉ vì backend không sử dụng HttpSession.

**OAuth scopes:** Gateway có thể xác minh access token có `scope=profile.read`, nhưng backend không được tự suy ra quyền `invoice.approve`. Audience phải khớp backend, scopes và tenant policies phải được map rõ.

**MFA/step-up:** Header `X-Auth-Method: mfa` chỉ có nghĩa khi gateway/IdP thật sự kiểm và bảo vệ bằng contract. Với thao tác quan trọng, backend có thể cần chứng cứ `auth_time`/`acr`/`amr` đáng tin, tối đa tuổi xác thực và session step-up.

**XSS/clickjacking/session fixation:** Spring Security vẫn cần các cơ chế defense chuẩn. Gateway đã xác thực không có nghĩa UI sẽ tự an toàn.

**Client IP:** là dữ liệu audit/rate limit, không phải identity key. Không dùng public IP chung của văn phòng để ánh xạ người dùng.

## 29. Audit và quan sát không lộ danh tính nhạy cảm

Nên ghi các trường sau theo chính sách tối thiểu hóa dữ liệu:

| Trường | Mục đích |
| --- | --- |
| Request correlation ID | Ghép trace giữa gateway/authorization/backend |
| Trusted source ID | Biết gateway/container/access manager nào được tin |
| Auth mechanism type | Ví dụ GATEWAY_PREAUTH, CONTAINER_PREAUTH, OAUTH_JWT |
| External identity fingerprint | Điều tra mà không lộ raw subject khi không cần |
| Local account ID | Xác định ai thực hiện hành động |
| Tenant, action, resource ID | Audit domain authorization |
| Decision | ALLOW/DENY và lý do nhóm |
| Auth/role policy version | Xác định quyền có bị stale sau deploy không |
| Gateway hop identity | Chứng minh request đi qua đúng service identity |
| Assurance freshness bucket | Có đủ mức xác thực không, tránh lộ credential |

**Không log** raw JWT, session cookie, SAML assertion, access token, plaintext password, private key, nguyên bộ group claims chứa PII hoặc header identity vô hạn trong APM. Nếu cần pseudonymization, dùng một key HMAC nội bộ và quản trị rotation/retention.

**Giảm account enumeration:** UI hoặc HTTP error không nên phân biệt chi tiết “username có tồn tại ở IdP X” nếu user không được phép biết; logs nội bộ có thể dùng mã lỗi riêng và được kiểm soát.

## 30. Các lỗi điển hình và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Ai gửi `X-Verified-Subject: admin` cũng truy cập được | Backend có direct ingress, thiếu hop authentication | Chặn bypass và xác thực gateway/mTLS |
| User login ở gateway nhưng backend 403 | Identity chưa linked, account disabled hoặc tenant role thiếu | Kiểm local link và policy, không cho admin mặc định |
| RequestHeaderAuthenticationFilter không chạy | Không nằm đúng SecurityFilterChain/filter order | Kiểm matcher, filter configuration |
| Header thiếu nhưng ứng dụng vẫn chạy filter khác | Continue-chain/fallback policy không chặt | Tách mechanisms, fail closed ở gateway/backend |
| Provider nhận principal nhưng authorities rỗng | UserDetailsService không nạp hoặc account chưa linked | Kiểm loader, role mapping, account DB |
| Header group “admins” tạo ROLE_ADMIN | Raw authority mapping không allowlist | Chỉ map quyền được owner phê duyệt |
| User A đổi sang B nhưng backend vẫn là A | SecurityContext/session stale, principal change không kiểm | Stateless re-eval hoặc session invalidation |
| Gateway logout nhưng Spring session còn sống | Hai session lifecycles tách biệt | SLO/revocation/freshness policy |
| Truy cập API thành công với ID Token | API thiếu token type/audience checks | Resource Server JWT validation đúng token |
| Container getUserPrincipal() trả null | Container auth realm/security constraints chưa bật | Bật container authentication, fail closed |
| Container role “admin” không khớp hasRole | Prefix/mapping khác nhau | Kiểm mappable roles và mapper |
| User có role ở tenant North nhưng dùng ở South | Role global thiếu tenant isolation | Kiểm membership/resource-level authorization |
| Cùng username ở hai gateways gộp account | Lookup không có issuer/source | Dùng verified source+issuer+subject |
| Có dấu gạch dưới/header duplicates lạ | Các proxy normalize khác nhau | Kiểm sanitize/deny duplicate headers |
| Backend bị lộ qua Kubernetes NodePort | Network bypass | Đóng public route, network policy |
| Gateway forward `X-Forwarded-For` do browser đặt | Spoofed forwarded headers | Strip/rewrite ở trusted edge |
| Signed JWT hết hạn nhưng header vẫn có | Gateway bỏ qua exp hoặc backend không kiểm freshness | Fix gateway validator, signed assertion exp |
| Role thay đổi nhưng người dùng còn quyền | Authorities snapshot/caches stale | Evict hoặc online entitlement lookup |
| Gateway service certificate rotate làm 401/503 | mTLS trust/cert renewal lỗi | Kiểm SAN/CA/rotation, không disable verification |
| Hai authentication mechanisms cùng route | Filter chain overlap, bypass | Tách matchers và precedence |
| Gateway outage nhưng backend cho vào trực tiếp | Fail-open fallback | Fail closed và circuit breaker policy |
| Admin interface vẫn mở riêng | Bypass/alternate port | Network identity controls cho mọi ingress |

**Không “sửa nhanh” bằng cách tắt TLS, chấp nhận mọi certificate, hardcode ROLE_ADMIN hoặc tự bật formLogin fallback không được phê duyệt.**

## 31. Ma trận kiểm thử bảo mật

| # | Kịch bản | Kết quả bắt buộc |
| --- | --- | --- |
| 01 | Client gửi identity header giả vào public gateway | Gateway strip và thay bằng verified identity hoặc từ chối |
| 02 | Client gọi backend trực tiếp với identity header | Bị chặn ở network/hop auth |
| 03 | Pod không phải gateway gọi backend qua internal service | Bị service policy/mTLS chặn |
| 04 | Gateway chưa xác thực user | Không set trusted identity cho backend |
| 05 | Gateway đã xác thực user đúng | Backend nhận đúng external identity link |
| 06 | Header principal bị thiếu | Không tự nhận anonymous/admin |
| 07 | Header subject rỗng hoặc chỉ whitespace | Từ chối |
| 08 | Duplicate identity headers khác giá trị | Từ chối hoặc xử lý deterministic theo strict contract |
| 09 | Header name case/underscore variant | Không cho vượt sanitization |
| 10 | Header size/value vượt policy | Từ chối, không gây DoS |
| 11 | Issuer không thuộc allowlist | Không accept identity |
| 12 | Same sub từ hai issuers | Hai identities khác nhau |
| 13 | Email trùng, issuer/sub khác | Không auto-link |
| 14 | Local account chưa linked | Onboarding/deny theo policy |
| 15 | Local account disabled | Deny dù gateway vẫn xác thực |
| 16 | X-Verified-Groups chứa ROLE_ADMIN | Không được tự cấp ROLE_ADMIN |
| 17 | Gateway role group từ tenant khác | Không cross-tenant privilege |
| 18 | Người dùng chỉ có ROLE_VIEWER, cố approve invoice | 403/domain DENY |
| 19 | Invoice thuộc tenant khác | Domain DENY |
| 20 | SSO cookie tự gửi trên unsafe POST cross-site | CSRF protection hoạt động |
| 21 | Gateway logout nhưng Spring session đang active | Kiểm session invalidation/freshness policy |
| 22 | Gateway đổi user A→B cùng browser | Không dùng stale SecurityContext của A |
| 23 | Container getUserPrincipal null | Không tạo authenticated principal |
| 24 | Container role absent | Không cấp role đó |
| 25 | Container role name trùng nhưng scope khác | Policy ánh xạ chính xác |
| 26 | JWT đúng ký nhưng sai audience | Bị Resource Server từ chối |
| 27 | JWT hết exp / invalid issuer | Bị từ chối |
| 28 | ID Token gửi vào API như access token | Không được coi là API auth |
| 29 | Gateway–backend mTLS cert không đúng service identity | Bị chặn |
| 30 | Reverse proxy/sidecar bị bypass | Test thất bại; đóng ingress |
| 31 | Role bị rút trong local DB | Revocation SLA được đáp ứng |
| 32 | Authorization service timeout | Fail closed cho quyền nhạy cảm |
| 33 | SecurityFilterChain khác bắt nhầm path | Test matcher và thứ tự |
| 34 | Gateway header đổ vào access logs | Có redaction, retention đúng |
| 35 | Signed gateway assertion bị replay ngoài TTL | Bị từ chối |
| 36 | Active access manager session nhưng account bị khóa | Backend local policy DENY |
| 37 | Deploy gateway bản mới đổi schema header | Contract versioning; fail closed khi không tương thích |
| 38 | Backend load balancer chuyển node | Trust/cache/role policy nhất quán |
| 39 | Một gateway bị thu hồi certificate | mTLS authorization chặn gateway đó |
| 40 | API webhook bên ngoài không có gateway user | Route dùng riêng webhook signature/service auth, không giả human identity |

**Test E2E phải dùng hạ tầng gateway/container thật**, không chỉ mock HTTP headers ở Spring MockMvc. Một unit test chứng minh filter đọc `X-Verified-Subject` chưa chứng minh hệ thống production chống spoofing.

## 32. Runbook triển khai an toàn theo giai đoạn

### Pha A — Thiết kế contract

1. Inventory gateway, access manager, container, IdP và các routes/backend services.
2. Định nghĩa ai xác thực end user, bằng protocol nào, issuer nào, assurance nào.
3. Chốt identity key: source/issuer+subject, mapping đến local account; tránh email.
4. Chốt header names, encoding, duplicate handling, max length, contract version và ai cấp roles.
5. Định nghĩa service audience, tenant membership, role allowlist và resource rules.
6. Chọn browser session hay stateless API; định nghĩa session/CSRF/refresh/revocation.

### Pha B — Khóa trust boundary

1. Chặn mọi public/direct backend ingress; chỉ gateway/trusted mesh identity đi qua.
2. Dùng TLS/mTLS, kiểm SAN/peer identities, cert lifecycle.
3. Edge strip mọi client identity headers trước khi authentication.
4. Gateway rewrite trusted headers sau successful authentication; reject anonymous.
5. Kiểm các alternate ports, health/metrics, pod-to-pod bypass và webhook routes.
6. Thiết kế fail closed khi gateway/access manager/authorization service lỗi.

### Pha C — Tích hợp Spring Security

1. Chọn `RequestHeaderAuthenticationFilter` **hoặc** `J2eePreAuthenticatedProcessingFilter` theo nguồn principal thực tế.
2. Cấu hình `PreAuthenticatedAuthenticationProvider` với loader tài khoản đáng tin.
3. Kiểm rằng provider **không tự verify upstream**, nên hạ tầng phải cung cấp proof.
4. Tách SecurityFilterChains theo routes, cấm fallback kém tin cậy.
5. Có local account status/tenant check và role allowlist.
6. Bảo vệ CSRF/session/security context khi browser có SSO cookie.
7. Trường hợp signed access token, cân nhắc Resource Server validator thay header-only.

### Pha D — Canary và cutover

1. Test legitimate login path, direct backend spoof và header duplicate variants.
2. Test logout A→B principal change, roles update, account disabled.
3. Test tenant isolation và object-level authorization.
4. Test mTLS rotation, gateway outage, backend failover, DNS/reverse proxy changes.
5. Theo dõi 401/403, proxy failures, role-deny, suspicious bypass traffic.
6. Chỉ mở traffic khi security owner duyệt E2E trust-boundary proof.
7. Giữ rollback routing nhưng **không mở direct header bypass** làm đường cứu hộ.

### Pha E — Vận hành

1. Theo dõi access manager/gateway session và backend account entitlement freshness.
2. Kiểm tra policy drift khi thêm IdP, tenant, gateway hoặc service.
3. Rà soát firewall/NetworkPolicy và direct backend exposure định kỳ.
4. Rotate secrets/certs và invalidate caches theo event.
5. Audit role mapping, IAM ownership và incident procedures.
6. Loại bỏ role/admin fallback ngoại lệ và routes không còn hợp lệ.

## 33. Câu hỏi tự đánh giá

**1. Header `X-Verified-Subject: alice` có đủ xác thực user không?**  
Không. Phải chứng minh gateway đã xác thực người dùng và backend chỉ nhận header do chính gateway đáng tin đặt.

**2. `PreAuthenticatedAuthenticationProvider` có tự verify JWT hay password không?**  
Không. Nó giả định upstream đã xác thực và thường nạp UserDetails/authorities.

**3. Dùng `getUserPrincipal()` có tự bảo đảm container đã xác thực không?**  
Chỉ khi Servlet container đã cấu hình và thực thi authentication realm/security constraints đúng.

**4. Vì sao không nên dùng email làm primary key external identity?**  
Vì email có thể thay đổi/tái cấp/trùng giữa providers; cần issuer/source + stable subject.

**5. `PreAuthenticatedGrantedAuthoritiesUserDetailsService` có tự xác minh role header?**  
Không. Nó lấy GrantedAuthorities từ details container; nguồn details phải đáng tin và đúng policy.

**6. `isUserInRole("admin")` có đủ cho mọi quyền admin ứng dụng không?**  
Không. Container role và app business role có thể khác nhau; cần mapping và entitlement riêng.

**7. Vì sao mTLS gateway–backend vẫn chưa đủ chứng minh end user?**  
mTLS chứng minh gateway là peer; gateway còn phải chứng minh đã xác thực end user và bảo vệ identity assertion.

**8. Gateway logout có tự hủy mọi Spring sessions không?**  
Không mặc định. Cần session lifecycle/logout/revocation integration.

**9. Nếu API nhận JWT hợp lệ, có nên lấy `sub` rồi bỏ qua `aud` không?**  
Không. Phải xác minh issuer, audience, time, token type và authorization.

**10. Nếu muốn không phụ thuộc trust header xuyên nhiều hops, làm gì?**  
Ưu tiên signed access/identity assertion có audience/expiry và backend validator, hoặc dùng OAuth2 Resource Server khi phù hợp.

**11. Nếu user thuộc North, header tenant=South thì sao?**  
Backend phải kiểm membership và resource scope; không coi header là quyền auto-granted.

**12. Vì sao cần kiểm principal change khi dùng session?**  
Vì browser có thể đổi người đăng nhập tại gateway trong khi Spring SecurityContext còn principal cũ.

## 34. Checklist production

- [ ] Có sơ đồ đầy đủ các hops public gateway → access manager/mesh → backend.
- [ ] Backend không có đường truy cập trực tiếp/alternate port vượt auth gateway.
- [ ] Gateway chứng minh đã xác thực end user, không chỉ redirect/login page có sẵn.
- [ ] Trusted gateway hop được xác thực ở backend (mTLS/service identity hoặc tương đương).
- [ ] Gateway strip/overwrite mọi identity headers từ client; không tin forwarding headers làm auth proof.
- [ ] Các nguồn identity được versioned và có issuer/source/subject exact mapping.
- [ ] Không auto-link dựa vào email hoặc trùng username xuyên realms.
- [ ] `RequestHeaderAuthenticationFilter` chỉ dùng sau khi trust boundary thật được bảo đảm.
- [ ] `J2eePreAuthenticatedProcessingFilter` chỉ dùng khi container auth thực sự được cấu hình.
- [ ] `PreAuthenticatedAuthenticationProvider` có loader local account/status và roles; không giả nó verify upstream.
- [ ] External groups/roles được kiểm bằng allowlist, tenant và policy nghiệp vụ.
- [ ] Không biến raw ROLE_ADMIN header thành quyền admin.
- [ ] Có route-specific SecurityFilterChain và không có fallback mạo danh.
- [ ] Có chính sách stateless/session principal change, logout và revocation.
- [ ] Browser SSO cookie flows có CSRF protection phù hợp.
- [ ] Signed JWT/opaque tokens được verify type, issuer, audience, expiry, scope.
- [ ] Tenant membership và quyền trên object được server-side kiểm mỗi thao tác.
- [ ] Có timeout/fail-closed cho account/authorization lookups.
- [ ] Có unit test mapper và E2E spoofing/bypass/mTLS/headers normalization tests.
- [ ] Không log raw identity assertions, session tokens hoặc group claims nhạy cảm.
- [ ] Có monitoring 401/403/cross-tenant denials và incident response.
- [ ] Có owner cho trust contract, certificate rotation và release policy.
- [ ] Kiểm lại policy sau mọi thay đổi ingress/gateway/IdP/tenant/container.

## 35. Kết luận

**Lấy danh tính và quyền từ gateway, container hoặc hệ thống truy cập tập trung** là một mô hình **pre-authentication** hữu ích để dùng Spring Security cho authorization trong khi hệ thống khác đã xác thực người dùng. Spring cung cấp `RequestHeaderAuthenticationFilter`, `J2eePreAuthenticatedProcessingFilter`, `PreAuthenticatedAuthenticationProvider`, `AuthenticationUserDetailsService` và các utility cho GrantedAuthorities.

Nhưng **đọc identity không phải chứng minh identity**. Thành công phụ thuộc vào **trust boundary thực sự**, chống header injection, identity namespace/issuer+subject, account linking có bằng chứng, role mapping theo allowlist và tenant/resource authorization. Nếu cần bảo đảm độc lập theo service qua nhiều network hops, **signed access tokens/verified assertions** thường minh bạch hơn việc tin headers trần. Gateway có thể xác thực người dùng, nhưng **backend vẫn phải quyết định người đó được làm gì** và có trách nhiệm với phiên/quyền của chính mình.

### Tài liệu chính thức

- Spring Security Reference — Pre-Authentication Scenarios, Request Header và Java EE Container: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security Javadoc — RequestHeaderAuthenticationFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- Spring Security Javadoc — AbstractPreAuthenticatedProcessingFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Security Javadoc — PreAuthenticatedAuthenticationProvider: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security Javadoc — PreAuthenticatedGrantedAuthoritiesUserDetailsService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedGrantedAuthoritiesUserDetailsService.html
- Spring Security Javadoc — J2eePreAuthenticatedProcessingFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/j2ee/J2eePreAuthenticatedProcessingFilter.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Authorization Architecture và Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Jakarta Servlet Specification — Request principal và isUserInRole: https://jakarta.ee/specifications/servlet/
- NIST SP 800-207 — Zero Trust Architecture: https://csrc.nist.gov/pubs/sp/800/207/final
