# Xử lý thiếu header, thay đổi người dùng và phiên cũ còn tồn tại trong xác thực qua proxy

## 1. Bối cảnh và mục tiêu

Trong kiến trúc **Spring Security – federation**, nhiều ứng dụng không tự thu mật khẩu hoặc thực hiện OIDC/SAML challenge với browser. Thay vào đó, một **reverse proxy / identity-aware proxy / access gateway** xác thực người dùng trước, sau đó gửi thông tin danh tính đến backend qua những **HTTP headers được quản lý**.

Ví dụ:

~~~text
Browser
   |
   | Cookie của gateway / external SSO
   v
Trusted Identity Gateway / Reverse Proxy
   | - bắt buộc login OIDC/SAML/Kerberos/enterprise SSO
   | - kiểm phiên upstream còn hiệu lực
   | - LOẠI BỎ header danh tính do client tự đưa vào
   | - tạo header danh tính tin cậy cho backend
   v
Spring Boot Application
   | - RequestHeaderAuthenticationFilter
   | - PreAuthenticatedAuthenticationProvider
   | - UserDetailsService / authorization
   | - có thể lưu SecurityContext trong HttpSession
   v
API / Database / Business Operations
~~~

Thông thường gateway gửi một header đại diện người dùng, ví dụ:

~~~http
X-Authenticated-Subject: employee-42
~~~

**Header không tự là bằng chứng mật mã.** Spring Security pre-authentication **giả định hệ thống đứng trước đã xác thực user và bảo vệ đường đi**. Nếu ứng dụng nhận trực tiếp header tùy ý từ Internet, attacker có thể ghi `X-Authenticated-Subject: admin` để mạo danh.

Bài học thuộc nhóm **Xác thực qua proxy**, giải quyết ba tình huống khó nhưng thường gặp:

1. **Thiếu header:** gateway không gửi header vì upstream SSO đã hết hạn, request đi sai route, một middleware làm mất header hoặc client gọi trực tiếp backend. Dù browser vẫn có `JSESSIONID`, ứng dụng **không được giữ danh tính cũ** chỉ vì session local còn.
2. **Header đổi người dùng:** gateway bắt đầu báo `bob` thay cho `alice`, do người dùng chuyển tài khoản, reauthentication, cookie upstream đổi hoặc định danh được liên kết lại. Ứng dụng phải **ngăn session/roles của Alice bị dùng trong request của Bob**, không tự tiếp tục với SecurityContext cũ.
3. **Phiên cũ vẫn tồn tại:** Spring SecurityContext/HttpSession/Spring Session giữ Authentication đã có từ request trước; có thể xảy ra khi logout upstream nhưng app chưa nhận tín hiệu, khi cookie còn, khi user bị khóa hoặc quyền/tenant đã thay đổi.

Sau bài học bạn cần biết cách:

- Tách rõ **gateway identity**, **request headers**, **SecurityContext** và **HttpSession**; mỗi thứ có vòng đời và bên chịu trách nhiệm khác nhau.
- Đọc đúng hành vi `RequestHeaderAuthenticationFilter` và `AbstractPreAuthenticatedProcessingFilter`, đặc biệt `setExceptionIfHeaderMissing`, `setCheckForPrincipalChanges`, `setInvalidateSessionOnPrincipalChange` và `setContinueFilterChainOnUnsuccessfulAuthentication`.
- Cấu hình **fail-closed** khi thiếu/blank/duplicate header, kể cả khi request mang session cookie cũ.
- Xử lý thay đổi identity bằng **reauthenticate và rotate/invalidate session**, tuyệt đối không kế thừa authority hoặc cache nghiệp vụ cũ sang tài khoản mới.
- Phân biệt **username/display name** với khóa danh tính ổn định **issuer + tenant + subject**, khi cần thêm **upstream session ID**.
- Thiết kế **stateful** hoặc **stateless per-request** có chủ đích, không vô tình mix chính sách.
- Xây test matrix và runbook trước production.

**Quy tắc:** quyền truy cập cho mỗi request phải được suy từ **danh tính upstream hiện đang được xác minh** cộng với **trạng thái phiên/ủy quyền local phù hợp**, chứ không chỉ từ một Authentication được cache trong phiên cũ.

## 2. Các thành phần và điều gì được phép tin

| Đối tượng | Được tạo/giữ ở đâu? | Dùng để làm gì? | Có đủ để cấp quyền không? |
| --- | --- | --- | --- |
| **Gateway SSO session** | Identity proxy/OP/IdP | Quyết định browser hiện đã đăng nhập ở gateway hay chưa | Chỉ gateway có thể xác nhận |
| **Trusted identity header** | Gateway cấp sau xác thực và sanitize | Truyền principal/claim tới backend | **Chỉ khi kênh gateway→backend được bảo vệ** |
| **Client-supplied header** | Browser/API caller | Dữ liệu HTTP tùy ý | **Không**, phải strip trước backend |
| **Spring Authentication** | SecurityContext sau pre-auth provider | Principal + GrantedAuthorities hiện tại | Cần tương ứng với upstream identity còn hiệu lực |
| **HttpSession / JSESSIONID** | Spring app, session store, browser cookie | Lưu state/application SecurityContext | **Không** thay được bằng chứng gateway đang đăng nhập |
| **Spring Session store** | Redis/JDBC/... | Session state dùng chung các replicas | Có thể chứa Authentication đã cũ |
| **UserDetails/local roles** | Application DB/LDAP/authorization service | Trạng thái user, tenant, roles, quyền nghiệp vụ | Phải kiểm chính sách cập nhật và scope |
| **Logout/revocation event** | Gateway/IdP/session registry | Báo identity session bị hủy | Chỉ hữu ích nếu đến và được xử lý |
| **API bearer token** | Issuer/resource server | Xác thực API độc lập với gateway header | Không tự có cùng lifecycle với browser session |

Một lỗi tư duy điển hình là: “Header chỉ là để tạo session lần đầu; từ đó chỉ cần cookie là đủ”. Điều này **chỉ đúng khi đó là thiết kế ủy quyền rõ ràng**, ví dụ gateway/API đã cho app quản lý session độc lập với thời hạn chấp nhận được. Với **pre-auth bắt buộc kiểm gateway mỗi request**, giữ quyền từ session cũ khi header mất là lỗi bảo mật.

### 2.1. Luồng thực tế có hai lớp phiên

~~~text
Lần 1:  Gateway có upstream session A
          -> X-Authenticated-Subject: alice
          -> App tạo SecurityContext = alice, HttpSession S1

Lần 2:  Gateway vẫn xác thực alice
          -> header alice
          -> Browser gửi JSESSIONID=S1
          -> App cho tiếp tục nếu identity và policy nhất quán

Lần 3:  Gateway mất xác thực / không phát header
          -> Browser vẫn gửi JSESSIONID=S1
          -> App KHÔNG ĐƯỢC dùng SecurityContext=alice để cấp quyền

Lần 4:  Gateway đã xác thực bob thay alice
          -> header bob
          -> Browser vẫn gửi JSESSIONID=S1
          -> App phải hủy/rotate S1 và xét bob như phiên mới
~~~

**Header thiếu** và **session cookie cũ còn** là hai quan sát độc lập. Browser có thể giữ cookie lâu hơn gateway SSO hoặc người dùng có thể mở nhiều tab/chuyển tài khoản.

## 3. Trust boundary: chỉ gateway được tạo header danh tính

Trước khi phân tích hành vi Spring Security, cần có ranh giới hạ tầng **bắt buộc**:

~~~text
Internet request:
  X-Authenticated-Subject: admin   # attacker tự thêm

Gateway:
  - strip X-Authenticated-* từ client
  - xác thực SSO session/token
  - nếu hợp lệ, set X-Authenticated-Subject bằng identity đã xác minh
  - nếu không hợp lệ, 401/redirect login; không chuyển header cũ

Backend:
  - chỉ nhận traffic từ gateway/sidecar đáng tin
  - mTLS/private routing/service identity/network policy
  - không coi direct traffic có header là đáng tin
~~~

**RequestHeaderAuthenticationFilter không kiểm chữ ký hay mật khẩu của header.** Javadoc Spring Security nêu thẳng: filter chỉ lấy username từ header, dựa hoàn toàn vào external authentication system. Cài filter trên backend truy cập trực tiếp được từ Internet là cấu hình nguy hiểm.

Các biện pháp ở gateway và network:

- Strip mọi tên header danh tính có thể đến từ client, kể cả **duplicate, case variants, underscore/dash variants, forwarded headers** do proxy stack có thể normalize khác nhau.
- Tạo **một header principal duy nhất**, không truyền raw user input trở lại để dùng làm principal.
- Chặn đường **direct-to-backend** bằng network policy, firewall, mTLS hoặc service mesh identity có kiểm soát.
- Nếu nhiều gateways, mỗi gateway phải cùng có hợp đồng issuer/tenant/header và cấu hình trust rõ; không trộn trusted path và untrusted path.
- Không dùng `X-Forwarded-For` hoặc chỉ kiểm source IP trong một chuỗi proxy không tin cậy như bằng chứng người dùng đã đăng nhập.
- Bắt gateway kiểm **session/token upstream tại tần suất đã cam kết**; đừng phát header từ một upstream cookie đã logout nếu gateway vẫn cache sai.
- Không chuyển header danh tính vào logs public hoặc downstream không được phép.
- Nếu yêu cầu signed identity assertion, dùng JWT/PASETO hoặc một định dạng được gateway ký và backend xác minh issuer/audience/expiry/replay theo profile; **header plain text và RequestHeaderAuthenticationFilter không tự làm việc này**.

### 3.1. Đừng dùng tên header tùy ý không quản trị

Javadoc `RequestHeaderAuthenticationFilter` có mặc định `principalRequestHeader="SM_USER"` nhằm tương thích với CA SiteMinder. Trong ví dụ dùng:

~~~text
X-Authenticated-Subject: employee-42
~~~

Tên này là **quy ước ứng dụng minh họa**, không phải header chuẩn bắt buộc của Spring/OIDC. Hệ thống thật phải thống nhất tên, issuer, encoding, byte length, khả năng duplicate và value format giữa gateway, proxy chain và app.

### 3.2. Dùng subject ổn định thay email/display name

Nếu gateway có upstream OIDC:

~~~text
Issuer:  https://identity.example.test/realms/company
Tenant:  business-a
Subject: 67e2a83f-...
Email:   alice@example.test
~~~

Nên ràng buộc identity theo **(issuer, tenant, sub)** hoặc key đã quản trị. **Email/display name** có thể đổi, tái sử dụng hoặc trùng giữa các tenants; không nên là session-binding key mặc định khi thiết kế nhiều IdP.

Nếu gateway gửi riêng `X-Authenticated-Subject` và `X-Authenticated-Tenant`, backend cần kiểm **cả bộ** đến từ một gateway đã xác minh. Chỉ kiểm `Authentication.getName()` là subject mà bỏ tenant có thể làm lẫn phiên.

## 4. RequestHeaderAuthenticationFilter xử lý gì?

Spring Security có lớp:

~~~text
org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter
~~~

Nó extends:

~~~text
AbstractPreAuthenticatedProcessingFilter
~~~

và thường kết hợp:

~~~text
PreAuthenticatedAuthenticationProvider
  + AuthenticationUserDetailsService
  + UserDetailsByNameServiceWrapper / user-details provider phù hợp
~~~

Luồng mới (không có Authentication trước đó):

~~~text
Incoming HTTP request đã qua trusted gateway
   |
   v
RequestHeaderAuthenticationFilter
  getPreAuthenticatedPrincipal()
     -> X-Authenticated-Subject
  getPreAuthenticatedCredentials()
     -> "N/A" nếu không cấu hình credentialsRequestHeader
   |
   v
PreAuthenticatedAuthenticationToken (initial request)
   |
   v
AuthenticationManager / ProviderManager
   |
   v
PreAuthenticatedAuthenticationProvider
  -> AuthenticationUserDetailsService
  -> nạp/kiểm user mapping, authorities theo policy
   |
   v
Authenticated Authentication
   |
   v
SecurityContextHolder + SecurityContextRepository
   |
   v
AuthorizationFilter -> business endpoint
~~~

**PreAuthenticatedAuthenticationProvider không tự kiểm người dùng đã thực sự đăng nhập tại gateway.** Nó chủ yếu tải UserDetails dựa trên authentication đã được external gateway khẳng định. Một user hiện diện trong database **không phải bằng chứng header hợp lệ** nếu network trust không được đảm bảo.

### 4.1. Hành vi mặc định của header

Theo Spring Security Javadoc hiện hành:

- Mặc định lấy username từ header **`SM_USER`**.
- Khi header **không tồn tại**, `getPreAuthenticatedPrincipal` **throw `PreAuthenticatedCredentialsNotFoundException`** theo `exceptionIfHeaderMissing=true` mặc định.
- Có thể đặt `setExceptionIfHeaderMissing(false)` để thiếu header trả **null**, nhưng cách này **không đồng nghĩa fail closed**.
- Nếu không có credentials header, `getPreAuthenticatedCredentials` thường trả **`"N/A"`**; đó **không phải secret/password của user**.
- Filter **không làm authentication thật**, tất cả assurance nằm tại proxy.

### 4.2. Default “đã authenticated thì bỏ qua” rất quan trọng

Javadoc `AbstractPreAuthenticatedProcessingFilter` nêu: nếu `SecurityContext` **đã có Authentication**, filter **không làm gì theo mặc định**. Muốn so sánh principal ở mỗi request, phải bật:

~~~java
filter.setCheckForPrincipalChanges(true);
~~~

Nếu để mặc định không kiểm tra:

~~~text
Request 1:
  header = alice, không có local session
  -> tạo Authentication=alice, session S1

Request 2:
  header = bob, cookie vẫn S1
  -> SecurityContext của S1 vẫn là alice
  -> filter mặc định có thể BỎ QUA xác thực lại
  -> backend vẫn có Authentication=alice
~~~

Đây là một dạng **stale principal / account confusion**. Không nên nghĩ rằng “header mới đến thì filter chắc chắn chạy lại”.

### 4.3. Về lỗi xác thực và tiếp tục filter chain

Cũng theo Javadoc, nếu `AuthenticationManager` ném AuthenticationException trong pre-auth:

~~~java
filter.setContinueFilterChainOnUnsuccessfulAuthentication(false);
~~~

có thể làm exception được ném tiếp thay vì âm thầm cho filter chain chạy và cơ chế authentication khác thử tiếp. Tuy nhiên:

- Mặc định `continueFilterChainOnUnsuccessfulAuthentication` là **true** nhằm cho phép cơ chế khác thử xác thực.
- **false không xử lý các trường hợp principal trả null**, vì filter có thể không bắt đầu authentication và chain vẫn tiếp tục.
- **false cũng không bảo đảm chặn header thiếu khi filter hoàn toàn bỏ qua do SecurityContext đã authenticated**.
- Exception phải được chuyển thành HTTP 401/403 hợp lý bằng filter/error/entrypoint integration; không mặc định mọi throw đều được Spring xử lý đúng nếu thrown ở vị trí trước `ExceptionTranslationFilter`.
- Trong hệ thống **proxy-only**, tránh form login/HTTP Basic fallback không được duyệt: nó có thể biến lỗi gateway thành đường bypass xác thực yếu hơn.

**Kết luận phần này:** cấu hình `setCheckForPrincipalChanges(true)` và `setContinueFilterChainOnUnsuccessfulAuthentication(false)` rất hữu ích, nhưng để đảm bảo **thiếu header + session cũ phải bị vô hiệu hóa**, nên có một **request-boundary guard** kiểm tra header trước khi restored SecurityContext được dùng cho authorization.

## 5. Thiếu header nhưng cookie session cũ còn: xử lý fail closed

### 5.1. Tình huống lỗi

~~~text
T0: alice login qua gateway -> proxy header alice -> app session S1.
T1: alice logout upstream, gateway xóa SSO cookie.
T2: Browser vẫn giữ JSESSIONID=S1 của app.
T3: Một request đến backend:
      Cookie: JSESSIONID=S1
      X-Authenticated-Subject: [MISSING]
T4: Nếu chỉ dựa vào S1:
      Spring SecurityContextHolder có thể load Alice
      Authorization vẫn coi request authenticated
~~~

**Expected:** từ chối request, **không phục vụ dữ liệu dưới danh tính Alice**. Nếu policy xác định header bắt buộc trên mọi protected request, invalidate local session S1, xóa/security context cũ và yêu cầu login lại ở gateway. Không tiếp tục đến business controller.

### 5.2. Các trạng thái header đều cần xử lý

| Header từ request đến backend | Đánh giá |
| --- | --- |
| Không có tên header | **DENY**, không dùng local session cũ |
| Có tên header nhưng giá trị rỗng | **DENY** |
| Chỉ khoảng trắng | **DENY** |
| Nhiều header cùng tên với hai giá trị | **DENY**, không dùng “giá trị đầu” |
| Một header nhưng giá trị ghép kiểu `alice,bob` | **DENY** nếu contract chỉ cho một subject, tránh coalescing ambiguity |
| Header có CR/LF/control chars | **DENY**, gateway cũng phải reject |
| Header hợp format nhưng đến từ direct/untrusted connection | **DENY**, không chỉ kiểm string |
| Header hợp lệ từ trusted gateway | Chưa đủ nếu chưa kiểm tenant/account/session binding và authorization |
| Header Alice, session Bob | **DENY old session**, reauthenticate/rotate |
| Header Alice, session Alice nhưng upstream SSO đã logout | Chỉ chấp nhận nếu gateway **thực sự** còn khẳng định phiên hợp lệ; nếu không có tín hiệu tin cậy thì phải deny |

**Không lấy request.getHeader(...) trả string đầu tiên rồi bỏ qua duplicates**. Các proxy/Servlet containers có thể xử lý header duplicates, case folding và comma coalescing khác nhau. Gateway và backend cần **một hợp đồng duy nhất**: strip header từ client, một giá trị duy nhất, format và giới hạn độ dài rõ ràng.

### 5.3. Hướng fail closed cho ứng dụng có session

Khi guard xác định **không có trusted upstream identity**:

1. **Không chạy business controller** hoặc authorization với Authentication cũ.
2. Nếu có HttpSession local: `invalidate()` để loại bỏ SecurityContext/SavedRequest và session-scoped state.
3. Clear SecurityContext cho request/thread hiện tại bằng cách phù hợp với vị trí filter; nếu guard chạy **trước SecurityContextHolderFilter**, invalidation diễn ra **trước khi context cũ được khôi phục**.
4. Nếu đã load context rồi, phải vừa clear context vừa invalidate/save empty context theo Spring Security version; **không chỉ `SecurityContextHolder.clearContext()` trong khi repository vẫn giữ Authentication cũ**.
5. Phản hồi **401 Unauthorized** khi cần reauthentication, hoặc **403 Forbidden** cho identity không được phép/trust violation theo API contract; tránh redirect loop.
6. Có thể xóa cookie `JSESSIONID` trên browser với đúng Path/Domain/SameSite/Secure nếu application quản lý cookie; `invalidate()` phía server mới là phần chống tái sử dụng session, chỉ xóa cookie phía browser là không đủ.
7. Ghi log **reason code + correlation ID**, không ghi raw identities/SSO tokens.

### 5.4. Nếu header thiếu do proxy lỗi chứ không phải logout?

Vẫn phải fail closed. Sau đó sửa hạ tầng. **Không dùng local session cũ như “chế độ offline dự phòng”** trừ khi đây là một **business continuity mechanism** có policy/TTL/assurance riêng, đã được phân tích rủi ro và kiểm thử. Mặc định nên giả định header identity là điều kiện bắt buộc của từng request.

## 6. Header đổi user: không kế thừa session và quyền

Ví dụ:

~~~text
Request A:
  Trusted gateway identity = (issuer=corp, tenant=A, sub=alice)
  App session S1 = alice, roles=[ROLE_FINANCE_READER]

Request B:
  Trusted gateway identity = (issuer=corp, tenant=A, sub=bob)
  Browser vẫn gửi Cookie JSESSIONID=S1
~~~

Có hai chiến lược hợp lệ **nếu được thiết kế rõ**:

- **Reject-on-change (đơn giản, chặt):** invalidate S1, trả 401 và yêu cầu một luồng login/session mới; request Bob **không thể nhìn thấy dữ liệu của Alice**.
- **Reauthenticate-and-rotate:** invalidate hoặc thay toàn bộ authentication/session identity; chạy provider/local authorization lại cho Bob, tạo/rotate session mới, bỏ mọi principal-specific state cũ. Yêu cầu đảm bảo **atomicity** và session fixation protection.

Điều **không được làm**:

~~~text
SecurityContext vẫn chứa alice
Header hiện tại = bob
-> controller đọc profile/permissions/session cache của alice
-> trả dữ liệu alice cho browser đang là bob
~~~

### 6.1. Spring có API để phát hiện đổi principal

~~~java
filter.setCheckForPrincipalChanges(true);
filter.setInvalidateSessionOnPrincipalChange(true);
~~~

Javadoc `AbstractPreAuthenticatedProcessingFilter` cho biết khi bật `checkForPrincipalChanges`, filter so principal header mới với `Authentication.getName()` hiện có, và khi phát hiện đổi principal sẽ thực hiện lại authentication. `invalidateSessionOnPrincipalChange` mặc định là **true** khi cơ chế này được sử dụng; khai rõ trong code giúp người review biết security intent.

**Nhưng cần nắm giới hạn:** phép so mặc định chủ yếu dựa vào **principal name**; nó **không tự phát hiện** nếu:

- Hai tenants có cùng subject/email nhưng issuer khác.
- Upstream session ID đã đổi nhưng subject vẫn giống.
- User bị khóa hoặc đổi nhóm quyền mà tên principal không đổi.
- Gateway chuyển OP/IdP alias nhưng username trùng.
- Identity provider đổi authentication assurance mà display name giữ nguyên.

Nếu hệ thống có những yêu cầu trên, hãy mở rộng identity-binding logic **trước authorization** bằng verified issuer/tenant/subject/session, không chỉ dựa vào tên.

### 6.2. Không dùng email để so user switch khi có nhiều IdP

Ví dụ:

~~~text
Gateway trước:
  issuer = https://idp-a.example.test
  tenant = alpha
  subject = e7cf...
  email = manager@example.test

Gateway sau:
  issuer = https://idp-b.example.test
  tenant = beta
  subject = 5b02...
  email = manager@example.test
~~~

Hai email giống **không chứng minh hai principal là một**. Cần bản ghi local binding có **(trusted issuer, tenant, stable subject)** và policy liên kết tài khoản nếu muốn gộp. Request đang mang session cũ phải bị từ chối/rotate nếu binding thay đổi.

## 7. Cùng user nhưng upstream session đã thay: một giới hạn khác

Khi proxy hỗ trợ trusted session claim, ví dụ:

~~~text
X-Authenticated-Issuer: corp-sso
X-Authenticated-Tenant: tenant-a
X-Authenticated-Subject: alice-001
X-Authenticated-Session: upstream-session-7
~~~

Nếu identity vẫn là Alice nhưng `upstream-session-7` đổi thành `upstream-session-8`, mặc định chỉ so tên Alice có thể thấy “không đổi”. Với hệ thống shared-device hoặc có yêu cầu session freshness:

- Ràng buộc local session S1 với **upstream session ID đã được xác minh**.
- Nếu ID đổi, hủy S1 và cấp session mới sau khi áp policy.
- Không cho query/header do browser tự chọn quyết định session binding.
- Nếu upstream không cung cấp session ID tin cậy, đừng tự bịa dựa vào IP, User-Agent hoặc email; dùng **session epoch/token expiry và back-channel logout** nếu có, hoặc session policy chặt.
- Không lưu raw upstream session tokens/cookies vào HttpSession; lưu **opaque binding ID/hash hoặc internal session reference** theo nhu cầu.
- Nếu RP/gateway biết session bị revoked, local session phải bị hủy/chặn theo SLA của hệ thống.

**Lưu ý:** các header `X-Authenticated-Issuer/Tenant/Session` là **quy ước minh họa**, không phải tiêu chuẩn chung của OIDC/SAML. Việc dùng chúng trong production đòi hợp đồng xác thực, chuẩn hóa và bảo vệ đường truyền từ gateway tới backend.

## 8. Session cũ tồn tại: phân biệt các nơi lưu state

### 8.1. SecurityContextHolder là theo request/thread

`SecurityContextHolder` giữ Authentication được dùng cho request hiện tại (thông thường trong ThreadLocal hoặc strategy tương đương). `SecurityContextHolder.clearContext()` chỉ thay đổi **context hiện tại**, không đương nhiên xóa mọi copy trong:

- HttpSession/Spring Session store;
- Redis/JDBC session persistence;
- Spring Security `SessionRegistry` nếu quản lý session khác;
- Application-specific user profile/tenant cache;
- SavedRequest, CSRF token, shopping cart hoặc view-model chứa PII;
- Browser cookies ở các tab;
- Token session riêng của identity gateway.

### 8.2. SecurityContextRepository có thể khôi phục auth cũ

Với ứng dụng Servlet stateful:

~~~text
Request: Cookie JSESSIONID=S1
    |
    v
SecurityContextHolderFilter
    |
    v
SecurityContextRepository.loadContext(...)
    |
    v
HttpSession/Spring Session -> Authentication=alice (từ trước)
    |
    v
Filters + Authorization
~~~

Nếu bạn muốn mỗi request phải có header proxy hiện tại, **không được chỉ dựa vào Authentication đã khôi phục**. Cần guard trước restore context hoặc cơ chế enforce per-request khi context đã load, tương thích chính xác với filter ordering.

### 8.3. Spring Security 6/7 và explicit save

Từ Spring Security 6, cơ chế Servlet có `SecurityContextHolderFilter` và **explicit-save semantics** cho custom authentication; `SecurityContextPersistenceFilter`/`SessionManagementFilter` không còn là các defaults như Spring Security 5. Hướng dẫn Spring nêu custom filter/controller tạo Authentication cần lưu nó bằng `SecurityContextRepository.saveContext` khi muốn persist.

`AbstractPreAuthenticatedProcessingFilter` có setter `setSecurityContextRepository(...)` và lưu context sau authentication thành công. Nếu muốn stateful pre-auth:

~~~java
HttpSessionSecurityContextRepository repository =
    new HttpSessionSecurityContextRepository();
filter.setSecurityContextRepository(repository);
~~~

Cần dùng **cùng policy/repository** ở SecurityFilterChain; nếu controller/handler tự clear context thì phải đảm bảo **repository cũng không giữ bản cũ**. Không giải quyết bằng một lệnh `SecurityContextHolder.clearContext()` trong một code path mà request sau vẫn load lại Authentication=alice từ HttpSession.

### 8.4. Session fixation khác user-switch

- **Session fixation**: attacker biết/preset một session ID trước khi victim login. Sau login cần rotate `JSESSIONID` hoặc tạo session mới theo framework strategy.
- **User-switch stale state**: session S1 thuộc Alice, gateway chuyển Bob. Dù Session ID đã được rotate ở lần login Alice, nó vẫn là **session sai người** ở request Bob. Cần xử lý principal change riêng.
- **Session expiry**: sau TTL session tự hết hạn, nhưng **không đủ** để ngăn truy cập sai trong khoảng TTL trước đó.
- **Gateway logout**: external session hết hạn không có nghĩa Spring session local tự biến mất nếu không có propagation/guard.

Các biện pháp nên phối hợp, không thay thế nhau.

## 9. Mẫu cấu hình Spring Security: RequestHeaderAuthenticationFilter

Ví dụ cho **Spring Boot 3.x/Spring Security 6.x** hoặc nhánh Servlet hiện đại có những API tương ứng. Đây là **code minh họa tích hợp**, không tự chạy bằng JDK thuần nếu thiếu Spring dependencies và gateway đã cấu hình.

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration
public class ProxyPreAuthSecurityConfig {
    @Bean
    SecurityFilterChain proxyFilterChain(
            HttpSecurity http,
            UserDetailsService userDetailsService) throws Exception {

        UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>
            details = new UserDetailsByNameServiceWrapper<>();
        details.setUserDetailsService(userDetailsService);

        PreAuthenticatedAuthenticationProvider provider =
            new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(details);

        RequestHeaderAuthenticationFilter filter =
            new RequestHeaderAuthenticationFilter();
        filter.setPrincipalRequestHeader("X-Authenticated-Subject");
        filter.setExceptionIfHeaderMissing(true);
        filter.setCheckForPrincipalChanges(true);
        filter.setInvalidateSessionOnPrincipalChange(true);
        filter.setContinueFilterChainOnUnsuccessfulAuthentication(false);

        HttpSessionSecurityContextRepository repository =
            new HttpSessionSecurityContextRepository();
        filter.setSecurityContextRepository(repository);
        filter.setAuthenticationManager(new ProviderManager(provider));

        http
            .securityMatcher("/app/**", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .securityContext(ctx -> ctx
                .securityContextRepository(repository))
            .authenticationProvider(provider)
            .addFilterBefore(
                new TrustedProxyHeaderGuard(),
                SecurityContextHolderFilter.class)
            .addFilterBefore(
                filter,
                UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Để dùng code trên**, phải định nghĩa class `TrustedProxyHeaderGuard` trong phần tiếp theo và cung cấp `UserDetailsService` thật. `securityMatcher` giới hạn ví dụ cho `/app/**` và `/api/**`; các URL khác phải có **SecurityFilterChain/route policy riêng**, không để đường nhạy cảm lọt ra ngoài chain. Có thể chọn một chain toàn ứng dụng với explicit health/static path exclusions nếu kiến trúc phù hợp.

Các lựa chọn quan trọng:

- `setExceptionIfHeaderMissing(true)`: **chỉ có tác dụng khi filter thực sự gọi `getPreAuthenticatedPrincipal`**; guard phía trước xử lý trường hợp filter không chạy vì context cũ.
- `setCheckForPrincipalChanges(true)`: so user header với current Authentication khi có context đã được lưu.
- `setInvalidateSessionOnPrincipalChange(true)`: yêu cầu invalidation session khi principal đổi; tránh giữ attributes của user cũ.
- `setContinueFilterChainOnUnsuccessfulAuthentication(false)`: không tự chuyển sang auth cơ chế khác khi pre-auth manager thất bại. **Không tự xử lý principal=null hoặc old context**.
- `setSecurityContextRepository(repository)`: lưu trạng thái pre-auth khi thành công, thống nhất với chain. Nếu chọn **stateless**, không dùng HttpSession repository.
- `new ProviderManager(provider)`: provider chỉ nạp user/roles sau khi gateway đã xác thực. **Không dùng provider như bộ xác minh chữ ký của header**.
- `addFilterBefore(guard, SecurityContextHolderFilter.class)`: mục tiêu chạy guard **trước bước nạp SecurityContext từ HttpSession**, để missing header không được dùng chung cookie S1.
- `addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)`: filter pre-auth chạy sau context restoration và trước authorization trong cấu hình mặc định; **cần kiểm thứ tự bằng integration test**, nhất là multiple chains/các filter custom.
- Không bật form login/basic login khác vào chính chain trusted-proxy-only khi chưa có thiết kế assurance/fallback riêng.

**Lưu ý phiên bản:** Spring Security 6/7 có thể thay đổi API/ordering; đừng giả định cấu hình này thay thế integration tests trên project và Servlet container thực tế. `UserDetailsService` mặc định có thể **không chủ động kiểm disabled/locked** trong mọi implementation pre-auth; hãy đảm bảo **account state được kiểm và reject** theo chính sách, không chỉ nạp một record tồn tại.

## 10. Guard thiếu header chạy trước khi load session

Một cách rõ ràng là dùng `OncePerRequestFilter` chạy **trước `SecurityContextHolderFilter`** cho đường pre-auth đã được hạ tầng bảo vệ.

Tệp `TrustedProxyHeaderGuard.java` (Spring Boot Servlet, không độc lập với JDK):

~~~java
package com.example.portal.security;

import java.io.IOException;
import java.util.Collections;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.web.filter.OncePerRequestFilter;

public final class TrustedProxyHeaderGuard extends OncePerRequestFilter {
    private static final String SUBJECT = "X-Authenticated-Subject";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        List<String> headers = Collections.list(
            request.getHeaders(SUBJECT));

        boolean invalid = headers.size() != 1;
        if (!invalid) {
            String subject = headers.get(0);
            invalid = subject == null
                || !subject.matches("[A-Za-z0-9._@:-]{1,160}")
                || subject.indexOf(',') >= 0;
        }

        if (invalid) {
            // Guards BEFORE SecurityContextHolderFilter restores session.
            HttpSession previous = request.getSession(false);
            if (previous != null) {
                previous.invalidate();
            }
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED,
                "Trusted identity is required");
            return;
        }
        chain.doFilter(request, response);
    }
}
~~~

### 10.1. Những điều code guard này bảo đảm

- **Không có header**, header rỗng, multiple values hoặc ký tự không khớp hợp đồng → **401**.
- **Có session cookie cũ** nhưng thiếu header → server invalidate `HttpSession` trước khi SecurityContext cũ được load.
- Không chuyển tiếp yêu cầu lỗi đến protected endpoint.
- Không cần biết username cũ để xóa session; guard có thể chạy cả khi chưa authenticated.

### 10.2. Những điều code guard này chưa bảo đảm

**Rất quan trọng:** ví dụ guard chỉ kiểm **cấu trúc header**, **không xác minh rằng proxy thực sự đáng tin**. Production **phải** có mTLS/network routing và strip-inject header ở gateway; tốt hơn là một gateway-authenticated principal/assertion được dịch vụ tin với context mạng đã kiểm.

Ngoài ra:

- Nếu reverse proxy gộp duplicates thành một chuỗi, check comma chỉ là defense-in-depth cho contract minh họa; ingress vẫn phải reject ambiguous syntax.
- Regex ví dụ cho phép ASCII subject với một tập ký tự hạn chế; khi dùng opaque OIDC sub có thể cần Unicode/encoding khác, hãy thống nhất ở gateway/backend; **đừng tự trim/canonicalize danh tính** vì có thể làm hai principals khác nhau bị gộp.
- Regex không kiểm issuer/tenant/upstream session; nếu cần, áp bước **binding guard** riêng theo `(issuer, tenant, subject, upstreamSid)`.
- `HttpSession.invalidate()` không thay thế một logout notification tới gateway/IdP hoặc token revocation ở nơi khác.
- Code không tự xóa cookie browser; có thể thêm `Clear-Site-Data`/Set-Cookie theo thiết kế và đúng domain/path mà app sở hữu.
- `OncePerRequestFilter` là cơ chế một lần theo dispatch semantics, không có nghĩa tự bảo vệ tất cả URL: nếu URL nằm ngoài SecurityFilterChain hoặc filter không chạy, route đó phải được bảo vệ độc lập.
- Khi session invalidation diễn ra trong filter nằm sau khi context đã load, cần xóa/cập nhật SecurityContextRepository đúng cách; ví dụ cố ý **đặt trước SecurityContextHolderFilter**.

**Không copy guard như biện pháp duy nhất để bảo vệ web public**. Nó chỉ xử lý header presence/format, không chứng thực người dùng.

## 11. Kiểm tra đổi principal và invalidate phiên

Với trường hợp header đổi từ Alice sang Bob, cơ chế tích hợp `RequestHeaderAuthenticationFilter` có thể tự so user:

~~~java
filter.setCheckForPrincipalChanges(true);
filter.setInvalidateSessionOnPrincipalChange(true);
~~~

Theo Javadoc `AbstractPreAuthenticatedProcessingFilter`, mặc định:

- `checkForPrincipalChanges` **không được bật**: nếu có Authentication hiện tại, pre-auth filter có thể bỏ qua.
- Khi bật, `principalChanged` thông thường so **header String** với `Authentication.getName()`.
- `invalidateSessionOnPrincipalChange` có mặc định **true**, và chỉ hữu ích nếu actually check/change principal.
- Filter thử authenticate lại và lưu kết quả theo `SecurityContextRepository`; cần kiểm session strategy, business session state và result thực tế.

### 11.1. Vì sao chỉ dựa vào username không đủ?

Giả sử:

~~~text
Session S1:
  header user = alice
  tenant = A
  upstreamSession = sid-7
  authorities = [ROLE_FINANCE_READER]

Request mới:
  header user = alice
  tenant = B
  upstreamSession = sid-19
~~~

`Authentication.getName() == "alice"`, nên **tên không đổi**. Tuy nhiên tenant, session upstream và quyền có thể đã khác hoàn toàn. Nếu policy cần bảo vệ ranh giới này, tạo **SessionIdentityBinding** dạng:

~~~text
issuer
tenant
stableSubject
upstreamSessionId or sessionEpoch (nếu upstream hỗ trợ)
authorizationRevision (nếu ứng dụng có role revocation)
localSessionIssuedAt
~~~

Mọi thành phần của binding phải đến từ **verified gateway context** hoặc server-side state, không lấy từ một query/username tự do. Trước khi phục vụ request, so sánh **full binding** với current identity; mismatch → deny + invalidate session, không tái sử dụng Cached UserDetails/roles.

### 11.2. Vai trò của downstream session registry và policy version

Với Spring Session/Redis/JDBC:

- `HttpSession.invalidate()` ở một node phải làm session không còn được node khác chấp nhận, thông qua shared session store phù hợp.
- Nếu có `SessionRegistry`, cần kiểm event/cleanup cho session bị invalidated, không để stale registry refs làm lộ user state.
- Khi user disabled/revoked role, pre-auth filter chỉ kiểm principal String có thể **không reload authorities**. Thiết kế cần một trong các cơ chế: authorization revision, per-request authorization check, session expiry ngắn, cache invalidation, hoặc explicit session revocation event.
- Nếu thay tenant hoặc principal, xóa các attributes chứa profile/tenant data cũ, request cache và business caches gắn session.
- Nếu dùng distributed session, test logout/race ở hai replicas/requests đồng thời.

**Một người đổi role trong database không tự làm Authentication cached trong HttpSession được cập nhật.** Kiểm stale authorities là một yêu cầu riêng với principal switch.

## 12. Có nên dùng stateless per-request pre-auth?

Một lựa chọn giảm rủi ro **stale HttpSession** là không lưu Authentication giữa requests:

~~~text
Mỗi request:
  trusted gateway đảm bảo session upstream hợp lệ
  -> headers danh tính mới
  -> backend validate trust/identity binding
  -> load/check local authorization
  -> thực thi
  -> không persist Authentication vào HttpSession
~~~

Spring Security Servlet có thể dùng:

~~~java
http
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .securityContext(ctx -> ctx
        .securityContextRepository(new NullSecurityContextRepository()))
    .requestCache(cache -> cache
        .requestCache(new NullRequestCache()));
~~~

Đây là **fragment cấu hình**, cần imports:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
~~~

Nếu dùng stateless, **không được đồng thời set `HttpSessionSecurityContextRepository` cho preauth filter**. Tất cả authentication mechanisms trong chain phải dùng policy nhất quán. Stateless có chi phí:

- UserDetails/roles lookup mỗi request trừ khi có cache được kiểm freshness.
- Gateway phải phát trusted identity trên **mọi** protected request.
- Những endpoint cần browser CSRF/session state có thể cần chain/architecture khác.
- Không bảo đảm gateway token/SSO thực sự còn hiệu lực nếu gateway dùng cache sai.
- Không tự chặn header spoof nếu backend vẫn có thể được gọi trực tiếp.

**Stateful không nhất thiết sai.** Có những ứng dụng cần session và chọn invalidate-on-change + per-request guard; quan trọng là nói rõ **thời điểm nào Authentication local hết được phép tin**.

## 13. Bốn trạng thái truy cập cần phân biệt

| Gateway header | Cookie app | Trạng thái local cần xử lý |
| --- | --- | --- |
| Alice hợp lệ | Không có | Pre-auth + local user policy → tạo session nếu stateful |
| Alice hợp lệ | Session Alice còn đúng binding | Chấp nhận, subject/tenant/roles còn phù hợp |
| Không có | Session Alice còn | **401 và invalidation**, không dùng Alice |
| Bob hợp lệ | Session Alice | **401/new login hoặc reauthenticate+rotate**, không kế thừa state |
| Alice hợp lệ | Session Bob | **DENY**, invalidate Bob session |
| Alice, tenant B | Session Alice, tenant A | **DENY** dù string username giống |
| Alice, upstream session mới | Session Alice, upstream session cũ | Theo policy yêu cầu session binding: **DENY old session** |
| Alice hợp lệ | Session expired/unknown | Không phục hồi S1; xác thực/cấp session mới theo policy |
| Alice hợp lệ | Session Alice nhưng roles revoked | **DENY/reload roles**, không tiếp tục authority cũ |
| Header forged từ client | Bất kỳ | **DENY** tại gateway/network, không tin header |
| Header duplicate/malformed | Session Alice | **DENY**, không chọn giá trị tùy tiện |
| Header Alice nhưng gateway đã logout user | Session Alice | Gateway phải không phát header; nếu phát sai, app cần revocation/freshness controls |
| Gateway session hết hạn | Không có local session | 401/SSO login; không tạo anonymous user có quyền |
| Service-to-service job không qua gateway | Không có | **Không** dùng trusted-proxy chain; dành riêng route/service auth có kiểm chứng |

Để tránh tình huống session cũ tái tạo không kiểm soát, **khi phát hiện mismatch** nên chọn một trong hai policy:

- **Deny then new session:** trả 401/403 thích hợp; browser điều hướng login, request mới có identity hợp lệ và không còn cookie S1; session S2 được tạo.
- **Atomic replace:** trong cùng request, invalidate S1, xác minh full identity và local policy cho Bob, tạo S2, rotate session ID và xác nhận không còn state Alice; hành vi phải được integration test. Dễ sai hơn nếu app có nhiều caches/session attributes.

## 14. Java 17 chạy độc lập: mô phỏng identity binding và session invalidation

Đoạn mã sau **chạy với JDK 17+**, không cần Spring, proxy, KDC, OIDC hoặc Redis. Nó mô phỏng chính sách **deny on identity mismatch** theo các bất biến:

- Browser mới có **trusted gateway assertion** → application tạo local session.
- Request tiếp theo chỉ được dùng session khi **issuer/tenant/subject/upstreamSession** vẫn tương ứng.
- Missing/duplicate header **không được cứu bằng cookie cũ**.
- Header user mới nhưng cookie cũ: invalidate session và yêu cầu **phiên mới**.
- Cùng username nhưng tenant hoặc upstream session khác: deny.
- Gateway chưa được kiểm (untrusted direct caller): deny.
- Local user disabled/unknown hoặc roles version thay đổi: deny.
- Upstream session revoked/expired: deny; local session age quá policy: deny.
- Authorities luôn lấy từ **server-side local policy**, không từ header.

**Giới hạn bắt buộc:** `edgeVerified`, `upstreamActive` và các `Identity` trong demo là **giá trị giả lập từ một gateway/verifier đã được bảo vệ**, **không được lấy thẳng từ HTTP JSON/header/query hay một client-supplied boolean**. Demo **không xác minh mTLS, JWT signature, OIDC session, SAML assertion hoặc network identity**. `HashMap` không phải distributed session store, `local-1` không phải session ID ngẫu nhiên dùng được cho production. Mục tiêu là kiểm **logic continuity**, không phải tạo authentication middleware thật.

Tệp **ProxyIdentityContinuityDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ProxyIdentityContinuityDemo {
    static final String ISSUER = "trusted-gateway";
    static final Instant START = Instant.parse("2026-01-01T10:00:00Z");

    record Identity(String issuer, String tenant, String subject,
                    String upstreamSession) {}
    record Request(boolean edgeVerified, List<Identity> headers,
                   String cookie, boolean upstreamActive, Instant now) {}
    record Account(boolean enabled, int permissionsRevision,
                   Set<String> roles) {}
    record LocalSession(String id, Identity identity,
                        int permissionsRevision, Instant createdAt) {}
    record Result(int status, String reason, String sessionId,
                  Set<String> roles) {
        boolean ok() { return status == 200; }
    }

    static final class Service {
        private final Map<String, LocalSession> sessions = new HashMap<>();
        private final Map<String, Account> accounts = new HashMap<>();
        private int nextId = 1;

        Service() {
            accounts.put("tenant-a/alice",
                new Account(true, 1, Set.of("ROLE_READER")));
            accounts.put("tenant-a/bob",
                new Account(true, 1, Set.of("ROLE_EDITOR")));
            accounts.put("tenant-a/disabled",
                new Account(false, 1, Set.of("ROLE_READER")));
            accounts.put("tenant-b/alice",
                new Account(true, 1, Set.of("ROLE_TENANT_B")));
        }

        void changeRoles(String key) {
            Account current = accounts.get(key);
            accounts.put(key, new Account(current.enabled(),
                current.permissionsRevision() + 1, Set.of("ROLE_BASIC")));
        }

        boolean contains(String sessionId) {
            return sessions.containsKey(sessionId);
        }

        private Result deny(int status, String reason, String cookie) {
            if (cookie != null) sessions.remove(cookie);
            return new Result(status, reason, null, Set.of());
        }

        Result handle(Request request) {
            if (!request.edgeVerified()) {
                // In production the edge blocks untrusted traffic before app.
                return new Result(403, "untrusted-edge", null, Set.of());
            }
            if (request.headers() == null || request.headers().size() != 1) {
                return deny(401, "header-missing-or-duplicate", request.cookie());
            }
            Identity id = request.headers().get(0);
            if (id == null || !ISSUER.equals(id.issuer())
                    || id.tenant() == null || id.subject() == null
                    || id.upstreamSession() == null
                    || id.tenant().isBlank() || id.subject().isBlank()
                    || id.upstreamSession().isBlank()) {
                return deny(403, "untrusted-or-invalid-identity",
                    request.cookie());
            }
            if (!request.upstreamActive()) {
                return deny(401, "upstream-session-expired", request.cookie());
            }
            Account account = accounts.get(id.tenant() + "/" + id.subject());
            if (account == null || !account.enabled()) {
                return deny(403, "account-not-authorized", request.cookie());
            }
            if (request.cookie() == null) {
                String sid = "local-" + nextId++;
                sessions.put(sid, new LocalSession(
                    sid, id, account.permissionsRevision(), request.now()));
                return new Result(200, "new-session", sid, account.roles());
            }
            LocalSession previous = sessions.get(request.cookie());
            if (previous == null) {
                return deny(401, "stale-cookie", request.cookie());
            }
            if (!previous.identity().equals(id)) {
                return deny(401, "identity-or-upstream-session-switched",
                    request.cookie());
            }
            if (!request.now().isBefore(
                    previous.createdAt().plus(Duration.ofMinutes(30)))) {
                return deny(401, "session-too-old", request.cookie());
            }
            if (previous.permissionsRevision() !=
                    account.permissionsRevision()) {
                return deny(401, "roles-changed", request.cookie());
            }
            return new Result(200, "same-identity",
                previous.id(), account.roles());
        }
    }

    static Identity id(String tenant, String user, String upstreamSession) {
        return new Identity(ISSUER, tenant, user, upstreamSession);
    }

    static Request req(Identity identity, String cookie) {
        return new Request(true, List.of(identity), cookie, true, START);
    }

    public static void main(String[] args) {
        Service app = new Service();
        Identity alice = id("tenant-a", "alice", "upstream-1");
        Identity bob = id("tenant-a", "bob", "upstream-2");
        Result first = app.handle(req(alice, null));
        String sid1 = first.sessionId();

        System.out.println("firstHeaderCreatesSession=" + first.ok());
        System.out.println("sameUserReusesSession=" +
            app.handle(req(alice, sid1)).ok());
        System.out.println("rolesFromLocalPolicy=" +
            first.roles().equals(Set.of("ROLE_READER")));

        Result missing = app.handle(
            new Request(true, List.of(), sid1, true, START));
        System.out.println("missingHeaderDenied=" + (missing.status() == 401));
        System.out.println("missingHeaderRevokesOldSession=" +
            !app.contains(sid1));
        System.out.println("staleCookieDenied=" +
            !app.handle(req(alice, sid1)).ok());

        Result recovered = app.handle(req(alice, null));
        String sid2 = recovered.sessionId();
        System.out.println("newSessionAfterFreshAuth=" +
            (recovered.ok() && !sid2.equals(sid1)));

        Result switched = app.handle(req(bob, sid2));
        System.out.println("switchDenied=" + (switched.status() == 401));
        System.out.println("switchRevokesOldSession=" +
            !app.contains(sid2));
        System.out.println("newUserNeedsNewSession=" +
            app.handle(req(bob, null)).ok());

        Result forUpstream = app.handle(req(alice, null));
        System.out.println("upstreamSessionChangeDenied=" +
            !app.handle(req(
                id("tenant-a", "alice", "upstream-new"),
                forUpstream.sessionId())).ok());

        Result forTenant = app.handle(req(alice, null));
        System.out.println("tenantSwitchDenied=" +
            !app.handle(req(
                id("tenant-b", "alice", "upstream-1"),
                forTenant.sessionId())).ok());

        System.out.println("duplicateHeaderDenied=" +
            !app.handle(new Request(true, List.of(alice, bob),
                null, true, START)).ok());
        System.out.println("untrustedEdgeDenied=" +
            !app.handle(new Request(false, List.of(alice),
                null, true, START)).ok());
        System.out.println("disabledAccountDenied=" +
            !app.handle(req(id("tenant-a", "disabled", "u-3"),
                null)).ok());

        Result beforeRolesChange = app.handle(req(alice, null));
        app.changeRoles("tenant-a/alice");
        System.out.println("rolesChangeRevokesSession=" +
            !app.handle(req(alice, beforeRolesChange.sessionId())).ok());

        Result beforeUpstreamLogout = app.handle(req(alice, null));
        System.out.println("upstreamLogoutRevokesSession=" +
            !app.handle(new Request(true, List.of(alice),
                beforeUpstreamLogout.sessionId(), false, START)).ok());

        Result beforeTimeout = app.handle(req(alice, null));
        System.out.println("localSessionLifetimeEnforced=" +
            !app.handle(new Request(true, List.of(alice),
                beforeTimeout.sessionId(), true,
                START.plus(Duration.ofMinutes(31)))).ok());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 ProxyIdentityContinuityDemo.java
java ProxyIdentityContinuityDemo
~~~

**Stdout chính xác đã kiểm chứng**:

~~~text
firstHeaderCreatesSession=true
sameUserReusesSession=true
rolesFromLocalPolicy=true
missingHeaderDenied=true
missingHeaderRevokesOldSession=true
staleCookieDenied=true
newSessionAfterFreshAuth=true
switchDenied=true
switchRevokesOldSession=true
newUserNeedsNewSession=true
upstreamSessionChangeDenied=true
tenantSwitchDenied=true
duplicateHeaderDenied=true
untrustedEdgeDenied=true
disabledAccountDenied=true
rolesChangeRevokesSession=true
upstreamLogoutRevokesSession=true
localSessionLifetimeEnforced=true
~~~

**Ý nghĩa:** tất cả các dòng `...Denied=true`/`...Revokes...=true` chỉ ra **policy đã từ chối và hủy state cũ như mong đợi**, không phải kết quả 401/403 từ Spring production. Demo cũng cho thấy đổi người dùng cần **session mới**, thay vì tự sử dụng cookie của Alice cho Bob.

## 15. Ma trận kiểm thử tích hợp và bảo mật

| Test case | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Header đúng, chưa có cookie | Gateway đã xác minh Alice | App xác thực Alice và cấp session S1 |
| Header đúng, cookie đúng | Alice + S1 | Cho phép nếu binding/account/roles còn hợp lệ |
| Thiếu header, cookie S1 | Gateway logout hoặc proxy làm mất header | **401, invalidate S1**, không trả dữ liệu Alice |
| Header rỗng, cookie S1 | `X-Authenticated-Subject:` | 401, invalidate |
| Header whitespace | Header chỉ có dấu cách | 401, invalidate |
| Duplicate headers | Alice và Bob cùng tên header | 401, không chọn giá trị đầu |
| Header gộp comma | `alice,bob` | Reject theo header format contract |
| Header control chars | Newline/CR hoặc ký tự bất hợp lệ | Reject tại proxy/backend |
| Header từ direct backend | Caller bypass gateway, tự gắn Alice | **403/network reject** |
| Proxy không strip header | Client tự gửi admin, gateway forward nguyên | Security test FAIL; sửa gateway |
| Alice → Bob, cookie S1 | User switch upstream | Invalidate S1; không trả dữ liệu Alice |
| Bob → Alice, cookie S1 | Chuyển ngược tài khoản | Reauthenticate/new session, không reuse |
| Same username, tenant đổi | Tenant A/Alice → B/Alice | Reject old binding |
| Same email, issuer đổi | IdP A → IdP B | Reject nếu principal binding thay đổi |
| Same subject, upstream session mới | sid-7 → sid-8 | Reject/rotate theo policy |
| Gateway session bị revoke | Header biến mất sau logout | Local session không được reuse |
| Gateway phát header stale | SSO đã logout nhưng gateway còn cache | Gateway security test FAIL; app cần freshness/revocation |
| Browser còn JSESSIONID stale | Session ID không tồn tại trong store | Không khôi phục Authentication cũ |
| Session S1 hết TTL | Local session expired | Reject/reauth theo policy |
| User disabled ở local DB | Header hợp lệ nhưng local account bị khóa | 403, invalidation theo policy |
| Local role revoked | Session auth cũ có quyền cao | Reload/deny hoặc invalidate theo role revision |
| SavedRequest chứa dữ liệu Alice | Alice→Bob | Không chuyển request cache/profile data qua user mới |
| Hai tab cùng cookie | Tab A Alice, tab B switch Bob | Không trộn session data/authorities |
| Request đồng thời trên 2 nodes | Session shared Redis/JDBC | Invalidation nhìn thấy ở các nodes, xử lý races |
| Proxy header không có trên static | Static public path | Chỉ cho phép theo explicit public chain, không vô hiệu hóa login/protected routes |
| Filter nằm sai chain | `/api/private` bypass guard | Integration test FAIL |
| `setExceptionIfHeaderMissing(false)` | Header thiếu, stale auth còn | Test phát hiện fail-open |
| `checkForPrincipalChanges=false` | Header Bob, context Alice | Test phát hiện stale principal |
| `setContinueFilterChainOnUnsuccessfulAuthentication=true` | Provider fail rồi form fallback | Detect downgrade nếu không có policy |
| Pre-auth provider trả user mà không kiểm status | Disabled user exists | Fail authorization test; thêm local policy |
| Logout chỉ clear context | Session repository còn auth cũ | Request sau phải không restore được |
| Cookie bị xóa phía browser nhưng store còn | Client giữ/đánh cắp cookie | Server-side session invalidation bắt buộc |
| Session fixation | Session ID trước và sau login trùng ngoài policy | Rotate session theo security strategy |
| API bearer auth trên route khác | Không có header proxy | Route phải theo chain/credential policy riêng |
| Reverse proxy trust change | Gateway khác hoặc header name đổi | Deny nếu contract chưa được cập nhật |
| Gateway mất kết nối IdP | Gateway không thể validate session | Fail closed; không phát identity cũ |
| Log full headers | Raw subject/SSO/assertion bị in | Redact, audit privacy |
| Session ID trong URL | `;jsessionid` hoặc query được chấp nhận ngoài policy | Disable URL session tracking; test |
| Cross-tenant same subject | `alice` ở nhiều partners | User binding không được gộp |
| Retry 401 sau missing header | Browser login lại gateway | Chỉ tạo session mới sau upstream proof hợp lệ |

**Không chỉ unit test RequestHeaderAuthenticationFilter.** Cần e2e test đi từ **browser → gateway → backend**, với đúng header sanitization, session cookie, filter chain, Redis/Spring Session và response codes.

### 15.1. Test đúng bug nguy hiểm nhất

~~~text
Arrange:
  GET /api/reports with gateway header Alice -> 200
  Capture JSESSIONID=S1

Act:
  GET /api/reports
  Cookie JSESSIONID=S1
  KHÔNG có X-Authenticated-Subject

Assert:
  status = 401 (hoặc policy deny)
  KHÔNG có business data trong response
  Session S1 bị invalidated ở server/session store
  Retry với S1 không được chấp nhận
~~~

Nếu test trả 200 cho Alice chỉ vì `HttpSession` còn, cơ chế proxy pre-auth **chưa đảm bảo continuity theo contract**.

### 15.2. Test đổi identity giữa hai tab

~~~text
Tab 1:
  gateway Alice -> app session S1

Tab 2:
  gateway Bob nhưng browser vẫn gửi S1

Expected:
  không có request nào của Bob nhìn thấy Alice data
  S1 bị invalidated hoặc reauthenticated/rotated an toàn
  new session S2 chỉ chứa Bob roles/tenant data
  session cũ S1 không còn hợp lệ trên replica khác
~~~

### 15.3. Test header spoof

~~~text
Request không đi qua gateway:
  X-Authenticated-Subject: admin

Expected:
  network deny/mTLS fail/edge policy deny
  backend không chỉ dựa vào header string để cấp ROLE_ADMIN
~~~

**Đừng chỉ test request thông qua trusted gateway**, vì kênh bypass network chính là một threat model quan trọng.

## 16. Troubleshooting và log an toàn

| Triệu chứng | Nguyên nhân thường gặp | Cách điều tra |
| --- | --- | --- |
| Header thiếu nhưng request vẫn authenticated | Old SecurityContext loaded; preauth filter skip khi đã có auth | Kiểm checkForPrincipalChanges, guard ordering |
| Header Bob nhưng controller thấy Alice | Filter mặc định không check principal changes | Enable check + invalidate, test |
| Header Alice tenant B vẫn dùng quyền tenant A | So name mà không binding tenant | Full identity-binding guard |
| Logout upstream nhưng app session vẫn sống | Không có header presence check/logout event/session invalidation | Gateway session policy + app guard |
| Header thiếu gây HTTP 500 | Exception từ filter không được translate | Request boundary guard send 401, kiểm filter order |
| `exceptionIfHeaderMissing=false` được bật để fix 500 | Chuyển thành principal null và chain vẫn chạy | Không dùng như fail-closed fix |
| `continueFilterChainOnUnsuccessfulAuthentication=false` nhưng fail-open | No principal returned hoặc filter không chạy vì existing context | Guard trước context load |
| Một số URL không bị guard | Multiple SecurityFilterChains, matcher không phủ | Review URL coverage, MockMvc integration |
| Duplicate header cho kết quả ngẫu nhiên | getHeader chỉ chọn first/coalesced | Strip/reject duplicates tại gateway/backend |
| User switch tạo session nhưng vẫn có cart của Alice | migrateSession/copy session attributes cũ | Invalidate+new clean session, business cache cleanup |
| User bị revoke role nhưng context còn role cũ | UserDetails cached trong session | Role revision/periodic recheck/invalidate |
| Distributed session chỉ bị revoke ở một node | Redis/JDBC synchronization hoặc local cache | Shared session store, events, TTL/invalidation |
| Reauthentication loop | 401 khiến gateway redirect nhưng app vẫn giữ stale cookie/route | Session cookie clear, forwarding/login route policy |
| Người dùng thấy 403 sau gateway success | Account local disabled/tenant policy | PreAuthenticatedAuthenticationProvider+user policy |
| URL host/proxy header khác giữa environments | Header contract, ingress normalization khác | Edge config, proxy hop sanitization |
| Direct HTTP header impersonation | Backend mở public, trust network sai | Block external traffic, mTLS, gateway strip |
| API route cần bearer token bị chặn vì thiếu proxy header | Filter/chain matchers trùng | Phân chain và auth scheme theo route |
| Logout trả 200 rồi request sau lại authenticated | Gateway SSO vẫn active và phát header mới | Phân biệt app logout và gateway logout |
| JSESSIONID hết hạn nhưng header Alice còn | Gateway vẫn xác thực Alice | New local session nếu policy cho phép |
| Header format sai sau upgrade | Issuer/subject encoding/duplicate behavior đổi | Contract test, reject fail-closed |

### 16.1. Log gợi ý

~~~text
event=PROXY_IDENTITY_GUARD_REJECT
reason=HEADER_MISSING
route=/api/reports
gatewayId=corp-edge
localSessionPresent=true
traceId=trace-8b2c
status=401
~~~

~~~text
event=PROXY_IDENTITY_SESSION_MISMATCH
reason=PRINCIPAL_SWITCH
previousBindingHash=sha256:...
currentBindingHash=sha256:...
policyVersion=proxy-auth-v5
traceId=trace-b9f4
status=401
~~~

Các hash trên là **mẫu placeholder về định dạng log**, không phải hash có thể xác minh. Tránh log raw identity headers, cookies, bearer tokens, mTLS private key data, Spring Authentication object serialized, session DB nội dung hoặc PII.

### 16.2. Runbook theo tầng

1. **Gateway:** request thực sự qua đúng gateway đã được xác thực/mTLS chưa? Có strip-inject headers không?
2. **Header:** tên/value đúng contract? Có missing/blank/duplicate hoặc forwarding inconsistent không?
3. **Spring filter chain:** URL nằm trong đúng chain? Guard có chạy **trước SecurityContextHolderFilter**? Pre-auth có check principal changes?
4. **SecurityContext:** Authentication được load từ session cũ hay vừa được provider tạo? User/tenant/issuer/upstream binding tương ứng không?
5. **Local policy:** account enabled, roles revision, tenant access, resource ACL còn hợp lệ không?
6. **Session:** HttpSession/Spring Session có bị invalidate ở tất cả replicas chưa? Cookie cũ còn được dùng không?
7. **Upstream lifecycle:** nếu gateway vẫn phát header sau logout, proxy session/cache/revocation có lỗi không? Backend không thể sửa bằng cách chỉ xóa một cookie.
8. **Response:** status 401/403/302 đúng API/browser contract? Có login loop hoặc unauthorized data leak không?
9. **Observability:** correlation IDs, event reason, issuer/tenant hash (không raw PII), gatewayId, route, policyVersion.
10. **Remediation:** không bật missing-header fallback hoặc bỏ session-check chỉ để tạm hết 401; sửa nguyên nhân kèm negative tests.

## 17. Design choices theo threat model

### 17.1. Session local bị invalidated mỗi lần thiếu header có quá nghiêm không?

Nếu contract là **“mọi protected request phải đi qua gateway đã xác thực”**, đó là chính sách hợp lý và dễ audit. Có thể có request công khai, health check hoặc static assets không cần danh tính; cần **URL allowlist/chain tách riêng**, chứ không cho protected APIs đọc session khi thiếu header.

### 17.2. Có thể cho request mới của Bob tạo session ngay sau switch không?

Có thể nếu có **atomic reauthentication+session rotation** và app không giữ session data của Alice. Tuy nhiên mô hình deny-on-change trong ví dụ **đơn giản hơn để chứng minh an toàn**. Với thiết bị dùng chung/multiple tabs, yêu cầu người dùng xác nhận đổi tài khoản cũng hữu ích.

### 17.3. Có cần invalidate khi email thay nhưng sub không đổi?

Không nhất thiết nếu stable binding **issuer+tenant+sub** vẫn đúng, local roles/policy phù hợp. **Email/display name** không nên quyết định session identity trong SSO federation. Nhưng nếu ứng dụng dùng email làm key nghiệp vụ, phải thiết kế migration/cache invalidation tránh nhầm tài khoản.

### 17.4. Session đổi nhưng user giống có nguy hiểm không?

Có thể. Với security-sensitive products, một upstream session ID mới chứng minh **lần login upstream khác**. Nếu dùng lại local session cũ, saved requests/roles/state của phiên trước có thể trộn với phiên mới, hoặc bypass reauthentication freshness. Có thể phải rotate. Tuy nhiên chỉ có thể kiểm nếu gateway cung cấp **session binding đáng tin và bền vững**.

### 17.5. Khi user bị vô hiệu hóa, header vẫn có thể hợp lệ?

Có. External authentication có thể còn hiệu lực một thời gian, còn local policy đã revoked. `PreAuthenticatedAuthenticationProvider` không tự liên tục đối chiếu local trạng thái nếu Authentication được reuse từ session. Cần per-request authorization/version/TTL hoặc sự kiện revocation. **Đừng đồng nhất “gateway authenticated” với “business account enabled”.**

### 17.6. Proxy-only có nên bật form login trong cùng SecurityFilterChain?

Tài liệu Spring Security `RequestHeaderAuthenticationFilter` cảnh báo không nên kết hợp bừa với auth mechanisms khác, vì có thể tạo cách bypass external system. Nếu tổ chức bắt buộc có recovery login, cần route tách biệt, threat model, provider order, assurance, audit và policy cho credential downgrade; không để `AuthenticationException` bị swallow rồi tự chuyển sang cơ chế yếu hơn.

### 17.7. Trình duyệt logout local và logout gateway khác gì?

App logout local chỉ invalidate `HttpSession`. Nếu gateway SSO session còn, request mới có thể được gateway xác thực và phát header Alice → app login lại nhanh. Đó là **session mới sau proxy authentication**, không nhất thiết do HttpSession cũ chưa xóa. Muốn kết thúc upstream SSO phải tích hợp logout tại gateway/IdP theo protocol, không chỉ Spring local logout.

### 17.8. Bảo vệ khi gateway trả header nhiều identity

Một số proxy có thể gửi groups/roles hoặc identity từ nhiều tenants. Không chấp nhận trường `roles` chưa có hợp đồng/trust hoặc gộp nhiều identities bằng lấy phần tử đầu. Prefer identity assertion với issuer, audience, subject, tenant, phiên và permissions đã được ký hoặc truyền trên kênh tin cậy; map roles bằng allowlist local. Reject ambiguous inputs.

## 18. Checklist triển khai production

- [ ] Đã có sơ đồ trust browser → identity gateway → Spring app, không có direct backend bypass.
- [ ] Gateway strip mọi client-supplied identity headers và inject **một** identity header chính xác.
- [ ] Backend chỉ nhận gateway qua network policy/mTLS/service identity; không tin `X-Forwarded-For` như proof.
- [ ] Contract header nêu tên, format, charset, length, duplicate handling, issuer/tenant/subject/session semantics.
- [ ] Missing header **không** được dùng session S1 cũ; protected request 401 và invalidate session.
- [ ] Header blank, whitespace, comma-joined, duplicate hoặc invalid encoding bị từ chối.
- [ ] `RequestHeaderAuthenticationFilter` dùng đúng principalRequestHeader; không nhầm mặc định `SM_USER`.
- [ ] `setExceptionIfHeaderMissing(true)`, nhưng hiểu chỉ có tác dụng khi filter được gọi.
- [ ] `setCheckForPrincipalChanges(true)` để không bỏ qua user switch trong SecurityContext đã có.
- [ ] `setInvalidateSessionOnPrincipalChange(true)` và test business session-state cleanup.
- [ ] `setContinueFilterChainOnUnsuccessfulAuthentication(false)` khi proxy-only, tránh fallback ngoài policy.
- [ ] Có guard/binding policy xử lý header thiếu **trước hoặc bất chấp existing SecurityContext**.
- [ ] Guard chỉ áp dụng đúng SecurityFilterChain, static/health/other auth routes có explicit policy riêng.
- [ ] Việc invalidation được thực hiện ở **server/session store**, không chỉ xóa cookie client.
- [ ] Nếu clear SecurityContext manually, SecurityContextRepository cũng được cập nhật/xóa đúng.
- [ ] Session binding dùng stable issuer+tenant+subject, không dùng email làm key mặc định.
- [ ] Nếu gateway cung cấp trusted upstream session ID, session change được phát hiện theo policy.
- [ ] Nếu user disabled hoặc roles revoked, old Authentication không được giữ quyền mãi; có policy revision/recheck.
- [ ] UserDetailsService/AuthenticationUserDetailsService áp account status và local roles; không cấp ROLE_ADMIN từ header.
- [ ] Khi principal đổi, không giữ SavedRequest, cart, user profile cache/tenant context của user trước.
- [ ] Không dùng `SessionFixationProtection` như biện pháp thay thế user-switch handling.
- [ ] Với stateful, `HttpSessionSecurityContextRepository`/Spring Session và filter save/load nhất quán.
- [ ] Với stateless, `SessionCreationPolicy.STATELESS`/NullSecurityContextRepository và identity header mỗi request.
- [ ] Multiple replicas cùng nhìn thấy session revoked; có test races/parallel requests.
- [ ] API có bearer auth khác dùng chain/route riêng, không nhầm missing proxy header là anonymous được phép.
- [ ] HTTPS, CSRF/cookies/session timeouts vẫn cần thiết dù authentication đi qua gateway.
- [ ] App logout khác gateway/IdP logout; UX không tuyên bố đã xóa SSO nếu chỉ xóa local session.
- [ ] Đã test missing/blank/duplicate/spoofed headers, Alice→Bob, tenant/issuer switch, upstream logout, revoked roles.
- [ ] Đã test identity switch với old cookie trên browser hai tab và Spring Session/Redis cluster.
- [ ] Có log lý do, correlation ID và policyVersion nhưng không log raw tokens/cookies/PII.
- [ ] Có runbook cho 401 loops, proxy missing header, session stale, provider fallback và broken deployment.

## 19. Câu hỏi tự kiểm tra

**1. Header đã mất nhưng JSESSIONID còn, app có được dùng SecurityContext cũ không?**

Nếu contract yêu cầu gateway-authenticated header mỗi protected request thì **không**. Phải từ chối và invalidate session cũ, không cho quyền từ Authentication đã cache.

**2. Vì sao `RequestHeaderAuthenticationFilter` mặc định có thể không phát hiện Alice→Bob?**

Vì `AbstractPreAuthenticatedProcessingFilter` mặc định **bỏ qua khi SecurityContext đã có Authentication**. Bật `setCheckForPrincipalChanges(true)` để so user ở mỗi request.

**3. `setExceptionIfHeaderMissing(true)` có đủ chống missing-header stale-session không?**

Không tự động. Nếu filter không xử lý do existing Authentication, method đọc header có thể không được gọi. Cần guard enforce header presence hoặc cơ chế tương đương trên mọi protected request.

**4. `setContinueFilterChainOnUnsuccessfulAuthentication(false)` có tự chặn principal=null không?**

Không. Javadoc nói cấu hình này chỉ ảnh hưởng AuthenticationException từ AuthenticationManager; trường hợp principal null có thể cho chain chạy bình thường.

**5. `setInvalidateSessionOnPrincipalChange(true)` có tác dụng khi checkForPrincipalChanges=false không?**

Không như mong muốn: phải **bật principal change check** để có sự kiện đổi user.

**6. Khi header Bob, app có thể dùng role Alice nhưng đổi tên principal sang Bob không?**

Không. Mọi session-specific data/authorities phải được lấy lại theo Bob và policy; tốt nhất invalidate S1 và tạo session mới.

**7. Hai users có cùng email ở hai IdP có nên dùng chung session không?**

Không tự động. Dùng binding **issuer + tenant + stable subject**; account linking cần policy riêng.

**8. Nếu upstream SSO session đổi nhưng username giữ nguyên, `checkForPrincipalChanges` có phát hiện không?**

Không bảo đảm. Name comparison có thể thấy “không đổi”. Cần thêm trusted upstream session binding/epoch nếu product yêu cầu.

**9. `PreAuthenticatedAuthenticationProvider` có xác minh gateway đã login user không?**

Không. Nó giả định external system đã xác thực. Network/header trust ở gateway là điều kiện bắt buộc.

**10. Nếu local user bị khóa nhưng gateway vẫn phát header hợp lệ thì sao?**

Application phải kiểm user status/authorization và deny. Gateway authentication không tự tạo quyền nghiệp vụ.

**11. `SecurityContextHolder.clearContext()` có xóa HttpSession và Spring Session không?**

Không. Cần invalidate session hoặc cập nhật/xóa SecurityContextRepository phù hợp; nếu không request sau có thể restore old auth.

**12. Vì sao phải reject duplicate identity headers?**

Vì các proxy/Servlet stacks có thể chọn giá trị đầu, gộp hoặc parse không nhất quán, tạo **identity ambiguity** và nguy cơ spoofing.

**13. 401 và 403 dùng khi nào?**

Thông thường **401** khi cần xác thực lại (header thiếu/session expired), **403** khi identity đã biết nhưng không được phép hoặc trust violation; chi tiết theo API/security contract. Không trả 200 với stale principal.

**14. Không có upstream session ID thì có được tự lấy IP/UA để ràng buộc session không?**

Không nên. IP/UA không phải stable security identity, có thể đổi hoặc giả; dùng gateway-issued session ID/epoch hoặc policy freshness được phê duyệt.

**15. Stateless có loại bỏ mọi rủi ro proxy auth không?**

Không. Nó giảm stale app session nhưng backend vẫn phải tin đúng gateway, chống header spoof, kiểm local authorization và gateway session freshness.

**16. Logout local xong app tự login lại khi refresh có phải session xóa lỗi không?**

Không nhất thiết. Gateway SSO có thể còn active và phát header mới; app tạo Authentication/session mới. Phân biệt app logout với upstream logout.

**17. Vì sao cần integration test trên hai replicas?**

Vì invalidation local ở một node có thể không xóa session trong store/chế độ cache của node khác. Cần kiểm shared session semantics và concurrent requests.

**18. Guard chỉ kiểm regex header có đủ để production không?**

Không. Nó chỉ kiểm format. Phải có **trusted gateway/mTLS/network boundary**, binding issuer/tenant/session, local account/roles và đầy đủ authorization.

## 20. Tài liệu chính thức và tham khảo

- Spring Security, **Pre-Authentication Scenarios** — ranh giới external system, RequestHeaderAuthenticationFilter, PreAuthenticatedAuthenticationProvider và UserDetails services: https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html
- Spring Security Javadoc, **RequestHeaderAuthenticationFilter** — mặc định SM_USER, exceptionIfHeaderMissing=true, cảnh báo nguy cơ header spoof và mix login mechanisms: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html
- Spring Security Javadoc, **AbstractPreAuthenticatedProcessingFilter** — default skip khi SecurityContext có Authentication, checkForPrincipalChanges, invalidateSessionOnPrincipalChange, continueFilterChainOnUnsuccessfulAuthentication và SecurityContextRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/AbstractPreAuthenticatedProcessingFilter.html
- Spring Security Javadoc, **PreAuthenticatedAuthenticationProvider** — xử lý pre-auth token, load UserDetails nhưng không tự authentication external user: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html
- Spring Security, **Authentication Persistence and Session Management** — SecurityContextHolderFilter, explicit save, HttpSessionSecurityContextRepository, session fixation và logout: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security, **SecurityContextHolder** — lưu context/auth hiện tại theo strategy: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security, **Servlet Logout** — invalidation session và SecurityContext cleanup: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security, **Java Configuration / FilterChain** — securityMatcher, filter order và authorization: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- OWASP, **Session Management Cheat Sheet** — session fixation, expiration, logout/invalidation và cookies: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP, **Authentication Cheat Sheet** — identity lifecycle, reauthentication và controls: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP, **Authorization Cheat Sheet** — deny by default, permission checks, least privilege: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Ghi nhớ:** trong xác thực qua proxy, **missing header**, **user đổi** và **session cũ còn** là các sự kiện khác nhau nhưng dễ kết hợp thành lỗi mạo danh/stale authorization. `RequestHeaderAuthenticationFilter` chỉ trích principal từ header, không tự xác minh external identity; theo mặc định, `AbstractPreAuthenticatedProcessingFilter` có thể bỏ qua request khi đã có Authentication. Hãy xác thực **gateway trust trước tiên**, buộc protected requests có **identity header hiện tại**, bật principal-change detection khi stateful, ràng buộc **issuer/tenant/subject/upstream session** khi cần, invalidate/rotate session khi đổi identity, và kiểm lại quyền local trước khi trả dữ liệu. **Không để JSESSIONID cũ thay thế thông tin xác thực upstream đã biến mất.**