# SpnegoEntryPoint và phản hồi WWW-Authenticate: Negotiate

**SPNEGO (Simple and Protected GSS-API Negotiation Mechanism)** cho phép trình duyệt và ứng dụng web thương lượng cơ chế xác thực qua HTTP; trong môi trường doanh nghiệp, nó thường dùng **Kerberos** để hiện thực **Integrated Windows Authentication (IWA)**, tức người dùng đã đăng nhập vào domain có thể vào ứng dụng mà không phải nhập lại mật khẩu. Trong **Spring Security - federation**, module mở rộng **Spring Security Kerberos** cung cấp lớp `SpnegoEntryPoint` để phát HTTP authentication challenge phù hợp: **`401 Unauthorized`** cùng header **`WWW-Authenticate: Negotiate`**.

Điểm cần nắm: **`SpnegoEntryPoint` không xác minh Kerberos ticket và không đăng nhập người dùng.** Nó chỉ yêu cầu client bắt đầu (hoặc tiếp tục) **HTTP Negotiate authentication**. Browser nhận challenge, có thể xin service ticket từ KDC/Active Directory, rồi gửi **`Authorization: Negotiate <base64-token>`** ở request tiếp theo. Việc **giải mã/xác minh token** thuộc `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider` và `KerberosTicketValidator` (thường là `SunJaasKerberosTicketValidator`) theo phiên bản Spring Security Kerberos tương ứng.

Bài học giải thích **vai trò của 401/header, chu trình challenge–response, sự khác biệt 401 và 403, cấu hình SecurityFilterChain, fallback login, điều kiện SPN/keytab/DNS/browser, proxy và các kiểm thử bảo mật**. Mã minh họa Spring được tách rõ khỏi **chương trình Java 17 có thể chạy độc lập** mô phỏng HTTP state machine.

> **Nguyên tắc bảo mật:** chỉ xác thực người dùng khi server **đã validate thành công GSS/SPNEGO token cho đúng service principal và trust policy**, đồng thời ứng dụng còn kiểm tra trạng thái tài khoản/authorities. **Không coi việc nhìn thấy chuỗi `Authorization: Negotiate ...` là bằng chứng xác thực.**

## 1. Bối cảnh: khi nào SPNEGO/Kerberos có ích?

Một doanh nghiệp có:

- **KDC / Active Directory** quản lý realm, ví dụ `CORP.EXAMPLE.ORG`.
- Máy người dùng đã tham gia domain, có TGT hợp lệ và được browser cho phép **Integrated Authentication** tại `https://portal.example.org`.
- Backend Spring Boot Servlet chạy sau reverse proxy; dịch vụ có **HTTP service principal** `HTTP/portal.example.org@CORP.EXAMPLE.ORG` và **keytab** phù hợp để giải mã/xác minh Kerberos AP-REQ.
- User `alice@CORP.EXAMPLE.ORG` đã được Kerberos xác thực nhưng Portal vẫn cần tra **local account**, xem có bị khóa hay không, ánh xạ authorities và kiểm tra quyền truy cập.

Khi người dùng truy cập `/reports`, Spring Security yêu cầu authentication. Browser được gợi ý cơ chế Negotiate, tự lấy service ticket (nếu được phép và có credentials), rồi gửi token đến Portal. Người dùng **không đưa password cho Portal**. Đây là một dạng SSO giữa Windows/Kerberos realm và ứng dụng web, nhưng **không đồng nhất với SAML, OIDC hoặc CAS**; mỗi giao thức có credential, message và trust boundary khác nhau.

### 1.1. Các vai trò

| Thành phần | Vai trò | Điều cần kiểm chứng |
| --- | --- | --- |
| **Browser/HTTP client** | Nhận challenge, gửi Negotiate token. | Được browser policy cho phép tự động dùng Kerberos cho đúng URL. |
| **KDC/AD** | Cấp TGT và service ticket cho SPN. | Trust realm, tài khoản/service principal đúng, policy thời hạn/clock. |
| **SPN** `HTTP/portal.example.org` | Danh tính Kerberos của web service. | Phù hợp FQDN người dùng truy cập; không nhầm `HTTP` với HTTP cleartext. |
| **Keytab của server** | Chứa khóa phục vụ SPN để accept service ticket. | Quyền file, KVNO/enctype, account, rotation, không lộ qua build/log. |
| **`SpnegoEntryPoint`** | `AuthenticationEntryPoint` phát challenge. | HTTP 401 và `WWW-Authenticate: Negotiate`. |
| **`SpnegoAuthenticationProcessingFilter`** | Đọc `Authorization: Negotiate`, tạo authentication request. | Không coi header/tên user là kết quả đã được xác minh. |
| **`KerberosServiceAuthenticationProvider`** | Xác thực request token qua ticket validator. | SPNEGO/GSS-API validation trước khi load user. |
| **`KerberosTicketValidator`** | Xác minh token cho server principal/keytab. | Xác thực Kerberos, handle replay/clock/crypto theo GSS/Kerberos. |
| **`UserDetailsService`** | Lấy user local và `GrantedAuthority`. | Trạng thái locked/disabled, tenant, quyền riêng của Portal. |
| **`SecurityContextRepository`** | Giữ trạng thái auth giữa requests khi cấu hình. | Session fixation, lifetime, tính đúng khi nhiều node. |

## 2. HTTP 401 và WWW-Authenticate: Negotiate có ý nghĩa gì?

HTTP authentication sử dụng cơ chế **challenge–response**:

- Server trả **`401 Unauthorized`** khi request đến vùng cần xác thực mà chưa có credentials được chấp nhận.
- Header **`WWW-Authenticate`** cho biết authentication scheme mà server hỗ trợ. Với SPNEGO, scheme là **`Negotiate`**.
- Client có hỗ trợ và được phép sẽ gửi lại request với **`Authorization: Negotiate <base64-GSSAPI-token>`**.
- Server xác minh token bằng GSS-API/Kerberos, hoàn tất hoặc yêu cầu thêm một vòng handshake theo protocol.
- Khi đã xác thực và có quyền, server trả 2xx; nếu **đã xác thực nhưng không đủ quyền**, ứng dụng thường trả **403 Forbidden**, không lặp mãi 401 challenge.

Ví dụ challenge ban đầu:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
Cache-Control: no-store
Content-Length: 0
~~~

**Header `WWW-Authenticate: Negotiate` trống phần dữ liệu là bình thường ở vòng đầu.** Nó không có nghĩa ticket bị thiếu do server lỗi. Theo RFC 4559, continuation có thể trả header chứa token GSS-API để client xử lý tiếp.

Client có thể gửi:

~~~http
GET /reports HTTP/1.1
Host: portal.example.org
Authorization: Negotiate YIIF...BASE64_GSSAPI_TOKEN...
Cookie: JSESSIONID=optional-existing-session
~~~

Token ở trên là **ký hiệu minh họa**, không phải credential thật. Base64 chỉ là **encoding**, không có tính bảo mật bí mật riêng. **Không ghi nguyên header Authorization vào logs, tracing, analytics, bug report hoặc frontend console.**

### 2.1. Vì sao challenge không phải login form?

Form login có xu hướng:

~~~text
GET /reports -> 302 Location: /login -> browser hiển thị form
~~~

Negotiate có xu hướng:

~~~text
GET /reports -> 401 WWW-Authenticate: Negotiate
browser tự tìm credentials / service ticket
GET /reports + Authorization: Negotiate <token>
server validate -> 200, hoặc continuation/failure
~~~

Với cơ chế HTTP authentication, **401 là cách khởi đầu hợp lệ**, không nhất thiết là một sự cố. Công cụ giám sát chỉ xem “có 401” có thể báo lỗi giả, vì request đầu tiên của một browser chưa xác thực thường nhận 401 có chủ đích. Hãy đo cả tỷ lệ **401 challenge → token gửi lại → authentication success/failure**, không chỉ mã 401 riêng.

### 2.2. Kerberos ticket khác HTTP Authorization header ra sao?

- **TGT** cho phép client xin các service tickets từ KDC; browser không gửi TGT thô cho web app.
- **Service ticket** được KDC cấp cho service principal `HTTP/portal.example.org`.
- **GSS-API/SPNEGO token** được truyền trong `Authorization: Negotiate`, có thể chứa các token Kerberos liên quan đến service ticket và negotiation.
- **HTTP session cookie** là trạng thái local do ứng dụng tạo sau xác thực (nếu cấu hình dùng session), không phải TGT/service ticket.
- **HTTP authentication negotiation** có thể cần nhiều HTTP exchanges; không phải một lần gửi username là đủ.

Kerberos/SPNEGO tránh gửi password của người dùng tới Portal, nhưng vẫn phải bảo vệ **token, keytab, browser policy, DNS/SPN, TLS và local authorization**.

## 3. Vai trò chính xác của SpnegoEntryPoint

Class nằm trong:

~~~java
org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint
~~~

và thực thi:

~~~java
org.springframework.security.web.AuthenticationEntryPoint
~~~

Khi một request chưa xác thực cần access protected resource, `ExceptionTranslationFilter` của Spring Security sẽ gọi `AuthenticationEntryPoint.commence(...)` theo flow `SecurityFilterChain`. Với `SpnegoEntryPoint` mặc định, logic cốt lõi là:

~~~java
response.addHeader("WWW-Authenticate", "Negotiate");
response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
response.flushBuffer();
~~~

**Đây là trích đoạn logic API minh họa, không phải class đầy đủ.** Phản hồi thực tế có thể có thêm headers do Spring/container/proxy thêm; quan trọng là header Negotiate và HTTP 401.

**`SpnegoEntryPoint` không:**
- Tạo hoặc xác minh Kerberos AP-REQ, không đọc keytab, không liên hệ KDC.
- Kiểm tra principal `alice@REALM` có thuộc group admin hay không.
- Đặt `Authentication` đã xác thực vào `SecurityContext` bằng cách tự suy từ HTTP header.
- Thay `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider` hoặc `SunJaasKerberosTicketValidator`.
- Tự đảm bảo mọi browser sẽ hỗ trợ/muốn gửi Negotiate.
- Tự cấp HTTP session hoặc quyết định logout/revocation khi đã có Kerberos authentication.

### 3.1. Các constructor của SpnegoEntryPoint

Theo JavaDoc Spring Security Kerberos:

| Constructor | Hành vi |
| --- | --- |
| `new SpnegoEntryPoint()` | Chỉ trả **401 + `WWW-Authenticate: Negotiate`**, không form fallback. |
| `new SpnegoEntryPoint("/login")` | Trả **401 + Negotiate** và **server-side forward** đến `/login` để có nội dung fallback. |
| `new SpnegoEntryPoint("/login", HttpMethod.GET)` | Giống trên nhưng request được forward bằng method đã chỉ định. |

Trong phiên bản có constructor `forwardMethod`, tham số method có thể ép request forwarded được xem là **GET** thay vì giữ nguyên POST ban đầu (cần cân nhắc semantics). **Đường dẫn forward là URL tương đối với web application context, bắt đầu bằng `/`; không được là absolute URL**. Đừng tự lấy `forwardUrl` từ query parameter của client.

**Điểm thường bị hiểu sai:** `new SpnegoEntryPoint("/login")` dùng **RequestDispatcher.forward**, **không phải** `302 Location: /login`. Trong implementation chính thức, status vẫn là **401** và header **`WWW-Authenticate: Negotiate`** được thêm trước khi forward. Trình duyệt có hỗ trợ thường thử Negotiate; client không hỗ trợ có thể thấy body fallback. Để fallback trở nên dễ dùng, phải **thiết kế endpoint/body login page** và cơ chế form authentication riêng, không chỉ tạo entry point.

### 3.2. 401 và 403 trong Spring Security

| Trạng thái | Kết quả thường thấy | Nguyên nhân |
| --- | --- | --- |
| **Chưa đăng nhập** và yêu cầu `/reports`. | **401 + Negotiate**. | `AuthenticationEntryPoint` mời xác thực. |
| Browser gửi token hỏng/sai service principal. | Authentication fail; có thể **401 challenge lại** hoặc error handler theo cấu hình. | Không chứng minh được Kerberos identity. |
| Đã được xác thực `alice` nhưng không có `reports:read`. | **403 Forbidden**. | Authorization fail, không phải thiếu credentials. |
| User local `DISABLED` mặc dù Kerberos ticket hợp lệ. | Authentication failure / deny, tùy flow. | Authentication admission fail ở local policy. |
| Một endpoint `/public/**` được `permitAll`. | 200/public response, không yêu cầu challenge. | Không cần Kerberos cho route này. |
| Preflight `OPTIONS` đúng CORS policy. | Được xử lý theo CORS, thường không chạy Negotiate handshake. | Tránh browser CORS bị khóa bởi 401 vô ích. |

**Không chữa 403 bằng cách phát 401 vô hạn**; quyền là vấn đề khác với xác thực. Nếu role do local account thiếu, cần sửa entitlement/mapper đúng policy, không nới `.anyRequest().permitAll()`.

## 4. Luồng toàn phần: từ challenge đến Kerberos authentication

~~~text
Browser                        Spring Security                   KDC/AD
  |                                 |                              |
  | GET /private                    |                              |
  |-------------------------------->|                              |
  |                                 | check SecurityContext        |
  |                                 | anonymous + protected route  |
  |                                 | ExceptionTranslationFilter   |
  |<--------------------------------|                              |
  | 401 WWW-Authenticate: Negotiate |                              |
  |                                 |                              |
  | Browser policy: trust URL       |                              |
  | Existing TGT or OS credentials  |                              |
  | request service ticket for      |                              |
  | HTTP/portal.example.org         |                              |
  |--------------------------------------------------------------->|
  |<---------------------------------------------------------------|
  | service ticket for SPN          |                              |
  |                                 |                              |
  | GET /private                    |                              |
  | Authorization: Negotiate <GSS token>                           |
  |-------------------------------->|                              |
  |                SpnegoAuthenticationProcessingFilter             |
  |                   creates KerberosServiceRequestToken          |
  |                   -> AuthenticationManager                      |
  |                   -> KerberosServiceAuthenticationProvider      |
  |                   -> SunJaasKerberosTicketValidator             |
  |                   -> JAAS/GSS accept service ticket with keytab |
  |                   -> principal alice@CORP.EXAMPLE.ORG          |
  |                   -> UserDetailsService -> local status/roles  |
  |                   -> authenticated Authentication              |
  |<--------------------------------|                              |
  | 200 /private (if allowed)       |                              |
~~~

**Lưu ý:** đây là giản đồ với một Kerberos token round-trip thành công; **SPNEGO/GSS** có thể phải trao đổi nhiều tokens. Server đôi khi trả một **`WWW-Authenticate: Negotiate <response-token>`** để client hoàn tất mutual authentication. Đừng cứng hóa ứng dụng theo giả thiết “chỉ đúng một 401 rồi 200”, và đừng dùng body JSON đơn giản để ép browser xem negotiation thành công.

### 4.1. Phân biệt trách nhiệm 4 lớp

| Lớp | Input | Output/trách nhiệm |
| --- | --- | --- |
| `SpnegoEntryPoint` | Spring authentication entry point invoked. | **401 + header challenge** cho HTTP client. |
| `SpnegoAuthenticationProcessingFilter` | `Authorization: Negotiate <base64>`. | Trích token hợp lệ về mặt cấu trúc, gửi authentication request qua manager. |
| `KerberosServiceAuthenticationProvider` | `KerberosServiceRequestToken`. | Gọi validator, nhận Kerberos principal, dùng `UserDetailsService`, tạo authenticated token. |
| `SunJaasKerberosTicketValidator` | GSS-API token, server SPN/keytab. | Kiểm tra Kerberos qua JAAS/GSS; không phải local RBAC. |

Một số hướng dẫn dùng chữ “ticket” cho cả HTTP Negotiate token và Kerberos AP-REQ. Trong mã ứng dụng, **đừng cắt Base64 rồi tự đọc tên user**. Việc giải nghĩa/accept GSS context thuộc validator/framework được kiểm thử.

### 4.2. Header phía client trông ra sao?

~~~http
GET /private HTTP/1.1
Host: portal.example.org
Authorization: Negotiate YII...opaque-base64-gss-token
~~~

Ở token server-to-client continuation:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate YII...server-gss-continuation
~~~

Ở một số cơ chế mutual authentication, phản hồi thành công cũng có thể kèm token:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate YII...server-final-gss-token
Content-Type: application/json
~~~

Các chuỗi sau `Negotiate` ở đây là **giả lập**, không thể dùng xác thực thật. Theo RFC 4559, initial challenge thường **không** mang gssapi-data; continuation hoặc final step **có thể** mang data. Không coi `WWW-Authenticate` trên 200 là token danh tính để lưu browser theo ý muốn.

## 5. Điều kiện để browser thực sự trả lời Negotiate

Nhìn thấy **401 + Negotiate** chỉ là **điều kiện cần**, không phải điều kiện đủ.

1. Máy/browser có **Kerberos credentials** hợp lệ hoặc có thể lấy credentials từ môi trường đăng nhập.
2. Đúng **URL host** và vùng website được browser/OS cho phép gửi Integrated Authentication. Trình duyệt thường chỉ tự động thương lượng cho allowlist/intranet/trusted URIs, không tự gửi credentials tới mọi Internet host.
3. DNS/hostname của URL dẫn tới **SPN đúng**; KDC có service principal `HTTP/portal.example.org` gắn đúng tài khoản và keytab của service.
4. Thời gian client/KDC/server đồng bộ trong giới hạn cho phép Kerberos, realm trust và DNS SRV/KDC discovery hoạt động.
5. HTTP challenge không bị proxy/gateway loại header; request Authorization từ browser đến đúng backend; response `WWW-Authenticate` không bị xóa.
6. HTTPS certificate, hostname, SNI và trusted proxy configuration phù hợp.
7. Server acceptor có **keytab được đọc** với đúng encryption keys/KVNO; local user mapping không làm mất domain/realm ngoài dự kiến.
8. Không có middlebox captive portal/SSO gateway trả 302 thay cho challenge hoặc tự chuyển `WWW-Authenticate` thành Basic.
9. Browser không ở môi trường privacy/anonymous/Incognito hoặc network zone khiến SSO bị chặn, và user không cố tình tắt cơ chế Negotiate.

### 5.1. SPN HTTP/fqdn khác URL scheme

Ví dụ:

~~~text
Public URL:      https://portal.example.org
Kerberos SPN:    HTTP/portal.example.org@CORP.EXAMPLE.ORG
KDC realm:       CORP.EXAMPLE.ORG
Service account: svc-portal
Keytab:          /etc/security/keytabs/portal-http.keytab
~~~

Phần `HTTP/` trong SPN là **Kerberos service class**, không có nghĩa web app phải chạy **HTTP cleartext**. **HTTPS vẫn là lựa chọn bắt buộc ở production** để bảo vệ cookies, token trao đổi và giảm MITM/captive proxy.

Khi dùng DNS alias `portal.corp.example.org` → `portal.example.org` hoặc load balancer, **SPN/KDC/SSO policy phải khớp host mà client thật sự dùng**. Các trình duyệt và Kerberos library có thể canonicalize hostname theo cách riêng; vì vậy phải đo request thực tế/KDC logs thay vì đoán alias. Không khắc phục `KRB_AP_ERR_MODIFIED` bằng cách tắt ticket validation.

### 5.2. NTLM fallback và downgrade

**Negotiate là tên HTTP authentication scheme cho SPNEGO, không phải tên riêng của Kerberos.** Tùy Windows/browser/OS và bộ thư viện, SPNEGO có thể thương lượng **Kerberos hoặc NTLM**. Nếu tổ chức yêu cầu **Kerberos-only**, cần policy ở client/OS/server và validator **ngăn NTLM fallback**, không chỉ kiểm tra header chứa chữ `Negotiate`.

Ví dụ hai requests đều có header Negotiate nhưng có thể **khác cơ chế bên trong**:

~~~text
Authorization: Negotiate <SPNEGO-token-with-Kerberos>
Authorization: Negotiate <SPNEGO-token-with-NTLM>
~~~

Đây là ký hiệu, không phải header thật. Không tự phân loại token bằng regex tiền tố Base64; dùng GSS/provider/hệ thống xác thực có khả năng xác minh và nêu mechanism đã thực sự chọn. Nếu thư viện Spring Kerberos chỉ accept Kerberos theo cấu hình, NTLM sẽ không được hợp lệ hóa bằng cách bỏ kiểm tra. **Đừng mở Basic fallback không bảo vệ chỉ để “mọi máy đều login được”.**

## 6. Spring Security Kerberos: các module và version caveats

Tích hợp SPNEGO này thuộc **Spring Security Kerberos extension**, không phải `spring-boot-starter-security` mặc định tự bật. Các artifact có thể là:

~~~xml
<!-- Khai báo dependency trong Maven project có version management phù hợp -->
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-client</artifactId>
</dependency>
~~~

**Đây là fragment `pom.xml` minh họa**. Chọn release extension tương thích **Spring Security core**, Java runtime và namespace Servlet. Các bản hiện đại dùng `jakarta.servlet`, trong khi bài viết/nhánh cũ có thể dùng `javax.servlet`; **không trộn binary Jakarta/Javax** và không gắn một version tự đoán vào production. Cần kiểm tra dependency tree, BOM, API JavaDoc đúng version đang dùng và test end-to-end với KDC thực.

### 6.1. Bean tạo 401 challenge

~~~java
@Bean
SpnegoEntryPoint spnegoEntryPoint() {
    return new SpnegoEntryPoint();
}
~~~

Khi muốn hỗ trợ browser ngoài domain, có thể cân nhắc:

~~~java
@Bean
SpnegoEntryPoint spnegoEntryPoint() {
    return new SpnegoEntryPoint("/login");
}
~~~

**Hai bean là hai lựa chọn thay thế**, không khai báo đồng thời cùng tên. Với fallback, **401 + Negotiate vẫn tồn tại**, nội dung `/login` được **forward nội bộ**. Đảm bảo URL fallback hợp lệ, không bị vòng lặp authentication hoặc lỗi method. Không lấy `/login` làm nơi “tự phát hành Principal” từ email/password nếu chưa có một authentication provider hợp lệ.

### 6.2. Kerberos ticket validator dùng keytab

Bean minh họa:

~~~java
@Bean
SunJaasKerberosTicketValidator kerberosTicketValidator() {
    SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
    validator.setServicePrincipal(
            "HTTP/portal.example.org@CORP.EXAMPLE.ORG");
    validator.setKeyTabLocation(
            new FileSystemResource(
                "/etc/security/keytabs/portal-http.keytab"));
    validator.setDebug(false);
    return validator;
}
~~~

Các import trong project Spring:

~~~java
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
~~~

**Keytab là credential nhạy cảm**: mount từ secret manager với filesystem permissions hạn chế; không commit vào git/docker image/public classpath. Server service principal phải **có khóa thực tế trong keytab**, khớp KVNO/encryption types của account tại KDC. Trong một số môi trường, đường dẫn `file:/...` được ưu tiên hơn classpath resource khi JAAS cần truy cập file thật. Không bật `setDebug(true)` ở production vì log Kerberos/GSS có thể lộ chi tiết nhạy cảm.

### 6.3. Provider xác minh và ánh xạ user

~~~java
@Bean
KerberosServiceAuthenticationProvider kerberosServiceProvider(
        SunJaasKerberosTicketValidator validator,
        UserDetailsService userDetailsService) {

    KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
    provider.setTicketValidator(validator);
    provider.setUserDetailsService(userDetailsService);
    return provider;
}
~~~

Import:

~~~java
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
~~~

`KerberosServiceAuthenticationProvider` thực hiện **GSS ticket validation** rồi load `UserDetails` và `GrantedAuthority`. Một user `alice@CORP.EXAMPLE.ORG` được Kerberos xác thực **không đồng nghĩa** đã được cấp `ROLE_ADMIN` hoặc có quyền vào mọi tenant. `UserDetailsService` cần map realm/canonical username với local account ổn định, kiểm tra `disabled/locked` và entitlement đã được quản trị.

### 6.4. SpnegoAuthenticationProcessingFilter

~~~java
@Bean
SpnegoAuthenticationProcessingFilter spnegoFilter(
        KerberosServiceAuthenticationProvider provider) {

    SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
    filter.setAuthenticationManager(new ProviderManager(provider));
    return filter;
}
~~~

Import:

~~~java
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
~~~

Đây là **một phần cấu hình**. Cần **đăng ký filter vào đúng SecurityFilterChain**, cung cấp `UserDetailsService`, Java runtime/KDC và quyết định session strategy/context repository theo nhu cầu.

**Một caveat quan trọng của phiên bản mới:** `SpnegoAuthenticationProcessingFilter` có các tùy chọn như `setSkipIfAlreadyAuthenticated(true)` (mặc định), `setSessionAuthenticationStrategy(...)`, `setSecurityContextRepository(...)`, `setSuccessHandler(...)` và `setFailureHandler(...)`. Các defaults cần được xem theo phiên bản đang chạy; **đừng mặc định mọi request đã được lưu auth vào HttpSession chỉ vì đã thấy header Negotiate một lần**. Chọn session persistence hay per-request SPNEGO rõ ràng để bảo vệ expected behavior.

### 6.5. SecurityFilterChain mẫu

Trong Spring Boot Servlet:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        SpnegoEntryPoint entryPoint,
        SpnegoAuthenticationProcessingFilter spnegoFilter)
        throws Exception {

    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**", "/error").permitAll()
            .requestMatchers("/admin/**").hasAuthority("app:admin")
            .anyRequest().authenticated())
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(entryPoint))
        .addFilterBefore(spnegoFilter,
            UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
~~~

Import:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
~~~

Ví dụ `securityFilterChain` là **method trong một Spring `@Configuration` với `@Bean`**, không phải Java SE tự chạy. Các bean `entryPoint` và `spnegoFilter` phải được khai báo như trên, cùng deps Spring Boot Web/Security và Kerberos extension. Tùy ứng dụng, filter placement và HTTP entry point có thể cần `RequestMatcher` riêng để không trả Negotiate ở OAuth API hoặc admin-only exception.

**Lưu ý về code:** với SPNEGO, `UsernamePasswordAuthenticationFilter.class` thường là **mốc đặt filter** trong chain, không có nghĩa bạn phải cho phép password authentication. Cần kiểm tra chain thực tế bằng Spring Security debug logging đã được redacted, tránh thêm cùng filter cả Servlet và Spring Security chain khiến token bị xử lý hai lần.

### 6.6. Vì sao không chỉ cần EntryPoint?

Nếu bạn chỉ cấu hình:

~~~java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(new SpnegoEntryPoint()));
~~~

thì Spring vẫn có thể trả 401 challenge, nhưng **chưa chắc có filter/provider nào nhận `Authorization: Negotiate`** để xác thực. Kết quả thường là **401 → browser gửi token → vẫn 401**, trông giống vòng lặp vô tận. Phải có đủ filter + manager/provider + validator + local user mapping.

Ngược lại, nếu chỉ có `SpnegoAuthenticationProcessingFilter` mà không có `SpnegoEntryPoint`, browser có thể **không nhận được HTTP Negotiate challenge** khi truy cập route bảo vệ, tùy entry point mặc định của chain. Khả năng client “preemptive Authorization” tồn tại nhưng không nên dựa vào nó để thiết kế web SSO.

## 7. Fallback form login: forward nội bộ với mã 401

`SpnegoEntryPoint("/login")` hữu ích khi có hai nhóm người dùng:

- Máy trong domain, browser hỗ trợ IWA/SPNEGO.
- Máy cá nhân/ngoài domain hoặc client không hỗ trợ Kerberos, cần form login thay thế với **provider khác có policy phù hợp**, ví dụ LDAP authentication qua TLS hoặc OIDC ở luồng khác.

### 7.1. Thứ tự phản hồi

~~~text
GET /reports (anonymous)
   |
   v
Spring EntryPoint.commence
   |
   +-- HTTP status = 401
   +-- WWW-Authenticate = Negotiate
   +-- RequestDispatcher.forward("/login")
        |
        +-- body HTML của trang fallback (theo app)
        +-- status/header vẫn 401 + Negotiate
~~~

**Không phải redirect 302.** Khi browser không hỗ trợ Negotiate, nó có thể hiển thị trang fallback được forward. Khi browser hỗ trợ, nó thường thử Kerberos trước. Một số trình duyệt có UI khác nhau trước 401 challenge hoặc chọn sẵn auth scheme; cần E2E test với các client mục tiêu.

### 7.2. Fallback không được làm yếu xác thực

1. Trang `/login` phải accessible và không gây vòng `401 → forward /login → authentication entry point → ...`.
2. Nếu route `/login` chứa HTML, gửi **anti-cache headers** và chống XSS; không nhúng token Kerberos vào HTML.
3. Nếu dùng form password, chỉ qua **HTTPS**, có CSRF protection, rate limiting, lockout/abuse control và provider kiểm tra credentials thật.
4. Không dùng query `?username=alice` hoặc `X-Remote-User` thiếu trusted proxy boundary làm fallback authenticated.
5. Với request POST gốc, server-side forward giữ method có thể gây lệch handler; phiên bản hỗ trợ constructor `(String, HttpMethod)` có thể chọn `GET` cho fallback, nhưng cần test API semantic/CSRF. Đối với APIs, **401 JSON/Negotiate** thường rõ hơn forward HTML.
6. Đừng lẫn `WWW-Authenticate: Negotiate` và Basic nếu không thật sự có use case và TLS; browser có thể chọn mechanism ngoài dự tính.
7. Nếu đã xác thực Kerberos nhưng thiếu app role, trả **403** theo authorization policy; không tự động ném người dùng vào form rồi cấp thêm quyền.

### 7.3. Nếu cần nhiều entry points cho các vùng

Một ứng dụng có thể có:
- `/intranet/**` → SPNEGO.
- `/api/**` → OAuth2 Resource Server/JWT.
- `/public/**` → không yêu cầu auth.
- `/admin/**` → SPNEGO + policy MFA/step-up khác.

Hãy dùng **nhiều SecurityFilterChain có `securityMatcher` và order rõ** hoặc `defaultAuthenticationEntryPointFor(..., RequestMatcher)` khi hợp lý. **Không** trả header Negotiate cho mọi endpoint chỉ vì cấu hình entry point toàn cục; browser có thể thử ambient credentials ngoài phạm vi, đặc biệt với CORS và SPA.

## 8. Proxy, load balancer và hostname: nguyên nhân nhiều lỗi 401 vòng lặp

### 8.1. Reverse proxy không được làm mất HTTP auth headers

Cần kiểm tra hai chiều:

~~~text
Browser -> HTTPS reverse proxy -> Spring Backend
  Authorization: Negotiate <opaque-token>
           MUST reach trusted Kerberos-accepting backend

Spring Backend -> reverse proxy -> Browser
  HTTP 401
  WWW-Authenticate: Negotiate
           MUST reach browser unchanged as intended
~~~

Nếu gateway xóa `Authorization` hoặc chỉ cho Bearer, Spring filter không bao giờ thấy token. Nếu gateway xóa `WWW-Authenticate` hoặc thay status 401 thành 302 login portal của gateway, browser không bắt đầu SPNEGO. Nếu proxy và backend **cùng tự terminate Kerberos**, phải xác định **một trust boundary chính thức**; không giả định hai nơi đều có thể đọc cùng AP-REQ và tạo principal độc lập.

### 8.2. SPN của public hostname, không phải pod hostname

Public URL:

~~~text
https://portal.example.org
~~~

Nhưng backend thật:

~~~text
http://portal-service.namespace.svc.cluster.local:8080
~~~

Browser xin ticket cho **`HTTP/portal.example.org`**, không phải `HTTP/portal-service.namespace.svc.cluster.local`. Backend validator/keytab phải có khóa đúng SPN của **public host**, bất kể nội bộ HTTP host là gì. Cần HTTPS client-to-proxy và network trust được thiết kế cẩn thận giữa proxy/backend; nếu backend untrusted, Negotiate token có thể lộ.

### 8.3. Multi-node service keys

Nếu cả Node A/B accept trực tiếp Kerberos cho cùng `HTTP/portal.example.org`, các nodes cần **credential cùng service principal/keys hợp lệ** (hoặc thiết kế delegation/proxy termination khác) và cấu hình keytab distribution/rotation an toàn. Không copy keytab qua log/repository. Nếu session/auth state lưu local, người dùng chuyển node có thể gặp re-authentication; tùy policy, SPNEGO có thể được chạy lại hoặc dùng shared session. Kiểm tra cả **sticky session failover** và load balancer health route.

### 8.4. TLS và channel binding / extended protection

SPNEGO/Kerberos xác thực service principal, nhưng **HTTP Negotiate không tự thay TLS**. Với thiết kế có Extended Protection for Authentication/channel binding, cần đảm bảo TLS termination và channel binding tokens phù hợp giữa browser, proxy và SPNEGO acceptor. Nếu terminate TLS ở ingress nhưng backend tự accept SPNEGO, một số cơ chế channel binding có thể bị ảnh hưởng; phải kiểm thử theo realm/security policy, không tắt EPA/CBT mù quáng để “sửa 401”.

## 9. Nhận diện chính xác các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| GET protected trả 302 tới `/login`, không có 401 Negotiate. | Entry point Spring đang là form login/default handler. | Xem `SecurityFilterChain` và `exceptionHandling`; đo response headers. |
| 401 có Negotiate nhưng browser không gửi `Authorization`. | Browser không có credentials/không whitelist URL/intranet hoặc client không hỗ trợ. | Xem browser policy, Kerberos TGT và domain; không đổ lỗi cho validator trước. |
| Browser gửi Authorization rồi liên tục 401. | Keytab/SPN/realm sai, filter không chạy, provider không được đăng ký, NTLM fallback không được accept. | Quan sát filter invocation, sanitized GSS error, SPN/KDC/keytab. |
| `KRB_AP_ERR_MODIFIED`. | Server không có khóa đúng SPN/KVNO, duplicate SPN, tài khoản service sai. | Kiểm tra SPN registry, keytab, account rotation và DNS alias. |
| `KRB_AP_ERR_SKEW` hoặc clock skew. | Đồng hồ client/KDC/server lệch quá policy. | Đồng bộ NTP, xem timezone/clock nhưng không tắt validation. |
| `KRB5KDC_ERR_S_PRINCIPAL_UNKNOWN`. | KDC không tìm SPN dành host client truy cập. | Xác minh `HTTP/<FQDN>` trong realm và hostname canonicalization. |
| GSS: `Message stream modified` / `Integrity check` fail. | Key mismatch, token corrupt, wrong enctype hoặc proxy làm hỏng dữ liệu. | Keytab KVNO/enctype, truyền Authorization qua gateway, sanitized logs. |
| `GSSException: Defective token`. | Header malformed, Base64 invalid, wrong mechanism (NTLM), trung gian cắt token. | Kiểm tra scheme/header ở mức metadata, không log raw token. |
| KDC trả TGT nhưng không phát HTTP service ticket. | SPN wrong, trust realm, DNS/KDC policy, credentials không đủ. | `klist`/OS Kerberos tools ở máy test, KDC audit. |
| 401 ở URL alias nhưng hostname gốc hoạt động. | SPN/allowlist browser và canonicalization khác. | Dùng đúng public URL, map SPNs chính xác, test DNS. |
| Browser hỗ trợ Kerberos nhưng hiện form fallback. | 401 forwarded body, browser policy không auto Negotiate, challenge bị proxy đổi. | Xem response thật `WWW-Authenticate` và browser trusted URI policy. |
| Java code có `NoClassDefFoundError: jakarta.servlet`. | Trộn Kerberos extension cũ `javax` với Spring Security mới `jakarta`. | Dùng release đồng bộ, dependency tree, version lock. |
| Đã xác thực nhưng mọi lần gọi vẫn hỏi Negotiate. | SecurityContext/session không persistent theo cấu hình; multiple nodes. | Kiểm tra context repository, cookies và auth state; không tắt auth validation. |
| User có Kerberos principal đúng nhưng 403. | Local user disabled hoặc thiếu role/permission/tenant. | Tra local admission, granted authorities, method security. |
| Gọi API từ browser SPA bị CORS error. | Preflight OPTIONS bị 401 challenge, CORS config/trusted origin sai. | CORS filter trước security, test `OPTIONS` và credentials policy. |
| curl `--negotiate` không thành công trong container. | Không có Kerberos credentials, SPN/DNS sai hoặc curl lib không hỗ trợ GSS. | Kiểm tra curl build, `klist`, realm/keytab; không “bypass Negotiate”. |
| Server trả Negotiate nhưng browser dùng NTLM. | SPNEGO negotiation/downgrade theo policy client/OS. | Xác định mechanism thực sự accept, enforce Kerberos-only nếu cần. |
| Sau form login lại bị Negotiate prompt. | EntryPoint/chain fallback cấu hình sai, Spring session không lưu. | Tách matchers và authentication success, kiểm tra forwarded 401. |
| Gateway sửa 401 thành 302. | Identity gateway/middleware chiếm route trước Spring. | Xác định chủ sở hữu authentication ở từng hop, không tự tin `X-User` vô danh. |

### 9.1. Thứ tự debug hữu ích

1. **Network:** request đầu tiên có 401 + `WWW-Authenticate: Negotiate` không?
2. **Browser:** request tiếp theo có `Authorization: Negotiate` không? Nếu chưa, kiểm tra browser policy/Kerberos client.
3. **KDC:** client có service ticket cho **HTTP/public-FQDN** không?
4. **Gateway:** header Authorization có tới Spring và 401 Negotiate có ra browser không?
5. **Spring:** `SpnegoAuthenticationProcessingFilter` có chạy, token được gửi `AuthenticationManager` đúng không?
6. **Validator:** servicePrincipal/keytab/KVNO/enctype/realm/GSS có đúng không?
7. **Local account:** `UserDetailsService` có chấp nhận principal, tài khoản ACTIVE không?
8. **Authorization:** có role/tenant/resource permissions không?
9. **Session:** SecurityContext được duy trì theo policy không, session fixation/cookie/multi-node có đúng không?
10. **Fallback:** nếu browser không có Kerberos, có hiển thị nội dung login phù hợp nhưng vẫn fail closed không?

## 10. Kiểm thử thủ công: phân biệt 401 đúng chủ đích và lỗi xác thực

### 10.1. Kiểm tra challenge không cần credentials

Với endpoint được bảo vệ:

~~~bash
curl -i --max-time 10 https://portal.example.org/private
~~~

Khi chưa có cookie hợp lệ và `curl` chưa cung cấp GSS credentials, kỳ vọng:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

**Mẫu kết quả** còn tùy gateway/filter và endpoint. Nếu có redirect 302, kiểm tra entry point/fallback/gateway trước khi kết luận Spring Kerberos hỏng. Không coi curl “nhận 401” là thất bại của server: chính challenge 401 là mục đích ban đầu của `SpnegoEntryPoint`.

### 10.2. Test với client thực sự có Kerberos credentials

Trên máy có Kerberos client/curl build hỗ trợ GSSAPI và ticket cache hợp lệ:

~~~bash
klist
curl --negotiate -u : -i https://portal.example.org/private
~~~

`curl --negotiate -u :` là cú pháp thông dụng trên một số curl builds để bật Negotiate với credential cache sẵn có; khả năng thực tế phụ thuộc phiên bản/build, môi trường Kerberos và OS. **Không dùng ticket thật trong public demo hoặc log `-v` chứa Authorization**, đặc biệt ở máy chia sẻ. Không chạy `curl -k` để bỏ TLS verification chỉ vì thiếu chứng thư.

**Thành công** là service trả tài nguyên bảo vệ khi đã xác minh GSS context và local account/permission đúng; **không** phải chỉ nhìn thấy client gửi Authorization header. Đối với endpoint cần `app:admin`, Kerberos login hợp lệ nhưng user không có authority tương ứng phải nhận 403.

### 10.3. Test 401 ↔ 403 ↔ 200

| Case | Header/condition | Expected |
| --- | --- | --- |
| Anonymous GET `/private`. | Không Authorization/cookie. | **401 + Negotiate**. |
| Browser gửi token random hoặc Base64 giả. | `Authorization: Negotiate fake`. | **Không xác thực thành công**; 401/failure. |
| Browser có ticket đúng SPN và local user ACTIVE. | Token verified. | **200** nếu có quyền. |
| User ACTIVE nhưng thiếu role ở `/admin`. | Verified Kerberos identity, authority thiếu. | **403**, không login admin. |
| Local user DISABLED. | Kerberos verified, admission denied. | Không tạo authenticated session. |
| Protected `POST /transfer` với session nhưng thiếu CSRF token. | Local session valid, thiếu CSRF. | **403** CSRF theo policy, không phải lỗi KDC. |
| Public `GET /public/ping`. | Không Authorization. | 200, không challenge. |
| CORS `OPTIONS /private`. | Legitimate preflight + CORS policy. | CORS xử lý phù hợp, không bắt browser thực hiện Negotiate ở preflight. |
| Browser không hỗ trợ Negotiate, fallback đã bật. | Anonymous GET. | 401 + header Negotiate, nội dung fallback theo app; không phải 302 do `SpnegoEntryPoint`. |
| Service SPN/keytab không khớp. | Token không accept được. | Không có 200 authenticated, có GSS failure được log an toàn. |
| Proxy xóa header `Authorization`. | Browser đã gửi Negotiate nhưng backend không nhận. | Backend tiếp tục 401; E2E FAIL. |
| Lỗi KDC/clock. | Không xin/validate service ticket đúng. | Fail closed, không map user từ header tự khai. |

## 11. Java 17 tự chạy: state machine mô phỏng Negotiate challenge

Chương trình sau **không triển khai Kerberos**. Nó mô phỏng quyết định HTTP của tầng web: khi chưa xác thực phải phát **401 Negotiate**, khi có header nhưng chưa được validator xác minh phải từ chối, khi identity đã được validator + local policy chấp nhận mới trả 200 hoặc 403.

Đặc điểm của demo: không chấp nhận `Authorization` là bằng chứng tự thân; chỉ biến **`validatorAccepted` giả lập** thể hiện **kết quả đã được GSS/provider xác minh** mới chuyển sang authenticated. Trong production, phải lấy kết quả từ **Spring Security `AuthenticationManager`**, không phải từ HTTP request flag.

Tệp **`SpnegoChallengeDecisionDemo.java`**:

~~~java
public final class SpnegoChallengeDecisionDemo {

    record Request(boolean protectedResource,
                   boolean sessionAuthenticated,
                   boolean hasNegotiateHeader,
                   boolean validatorAccepted,
                   boolean localAccountActive,
                   boolean resourceAllowed) {}

    record Response(int status, String wwwAuthenticate, String reason) {
        @Override public String toString() {
            return status + " | " + wwwAuthenticate + " | " + reason;
        }
    }

    static Response decide(Request request) {
        if (!request.protectedResource()) {
            return new Response(200, "-", "PUBLIC");
        }

        boolean verifiedSession = request.sessionAuthenticated();
        boolean freshKerberos = request.hasNegotiateHeader()
                && request.validatorAccepted();

        if (!verifiedSession && !freshKerberos) {
            return new Response(401, "Negotiate",
                    request.hasNegotiateHeader()
                            ? "TOKEN_REJECTED" : "CHALLENGE");
        }

        if (!request.localAccountActive()) {
            return new Response(403, "-", "ACCOUNT_BLOCKED");
        }
        if (!request.resourceAllowed()) {
            return new Response(403, "-", "FORBIDDEN");
        }
        return new Response(200, "-", "ALLOWED");
    }

    public static void main(String[] args) {
        System.out.println(decide(
                new Request(false, false, false, false, true, false)));
        System.out.println(decide(
                new Request(true, false, false, false, true, true)));
        System.out.println(decide(
                new Request(true, false, true, false, true, true)));
        System.out.println(decide(
                new Request(true, false, true, true, true, true)));
        System.out.println(decide(
                new Request(true, false, true, true, true, false)));
        System.out.println(decide(
                new Request(true, false, true, true, false, true)));
        System.out.println(decide(
                new Request(true, true, false, false, true, true)));
        System.out.println(decide(
                new Request(true, true, false, false, true, false)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SpnegoChallengeDecisionDemo.java
java SpnegoChallengeDecisionDemo
~~~

**Stdout xác định:**

~~~text
200 | - | PUBLIC
401 | Negotiate | CHALLENGE
401 | Negotiate | TOKEN_REJECTED
200 | - | ALLOWED
403 | - | FORBIDDEN
403 | - | ACCOUNT_BLOCKED
200 | - | ALLOWED
403 | - | FORBIDDEN
~~~

**Giải thích từng dòng:**
1. Public route không bị thử Kerberos.
2. Anonymous protected request được challenge 401.
3. Có `Authorization: Negotiate` nhưng validator không chấp nhận token → **vẫn 401**.
4. GSS token hợp lệ, local account ACTIVE, có quyền → 200.
5. GSS token hợp lệ nhưng thiếu quyền → **403**, không lặp challenge.
6. GSS token hợp lệ nhưng local account bị chặn → deny.
7. Session đã được xác thực và còn quyền → 200 mà không nhất thiết gửi Authorization trên request đó.
8. Session đã xác thực nhưng resource permission thiếu → 403.

**Giới hạn:** code trên là **policy simulation**, không phải HTTP servlet, không tạo keytab, không gọi KDC, không parse Base64/GSS, không xử lý multi-round SPNEGO, channel binding, session fixation hoặc Kerberos credential lifetime. Trường `validatorAccepted` chỉ đại diện **bằng chứng đã xác minh từ framework**, không được copy trực tiếp từ form, JSON hay header tự khai. Response 403 cho account blocked là quyết định đơn giản của demo; Spring authentication failure thực tế có thể có response 401 phù hợp flow.

## 12. Session, reauthentication và expiry

### 12.1. Khi đã có HttpSession

Một ứng dụng Servlet thường muốn lưu `Authentication` đã xác minh trong `SecurityContext` để không phải trao đổi SPNEGO ở mọi request. Nhưng behavior **phụ thuộc cấu hình `SecurityContextRepository`, `SessionAuthenticationStrategy` và chính sách phiên**.

Nếu dùng Spring Security Kerberos extension phiên bản mới, `SpnegoAuthenticationProcessingFilter` có mặc định liên quan **skipIfAlreadyAuthenticated**, success handlers và security context saving; cần kiểm tra framework version. Không suy ra browser **luôn** gửi Authorization lại ở mọi request, hoặc app **luôn** có HttpSession sau handshake.

### 12.2. Kerberos TGT và local session là hai thời hạn

- TGT hoặc service ticket hết hạn theo KDC/Kerberos policy.
- HTTP session có idle/absolute TTL do ứng dụng đặt.
- Browser có thể có credentials để **thực hiện Negotiate lại** khi session local mất.
- Local logout chỉ invalidate session ứng dụng; nếu client vẫn có TGT hợp lệ, request tiếp theo có thể tự xác thực lại ngay.

Vì vậy **“logout khỏi portal” không đồng nghĩa “đã logout khỏi Windows/Kerberos domain”**. Nếu ứng dụng yêu cầu người dùng chủ động nhập lại yếu tố cho thao tác nhạy cảm, cần cơ chế reauthentication/step-up phù hợp policy; **SPNEGO mặc định không chứng minh MFA mới xảy ra ngay lúc request**.

### 12.3. Session fixation và CSRF

Spring Security session fixation protection, cookie `Secure`/`HttpOnly`/`SameSite` phù hợp, CSRF protection trên state-changing requests và authorization từng tài nguyên vẫn quan trọng. Đừng tắt `.csrf()` trên toàn ứng dụng chỉ vì muốn dùng Kerberos; **ambient credentials** làm CSRF càng cần được xem xét. Đối với API dùng token thay vì cookie, thiết kế riêng token audience/CORS/CSRF phù hợp.

## 13. Kerberos federation và các ranh giới không được vượt

SPNEGO/Kerberos có thể là một **chặng** trong kiến trúc federation rộng hơn:

~~~text
Enterprise AD / KDC
       |
     Kerberos
       |
Browser -> Spring Portal (SPNEGO acceptor)
                 |
                 | local session / SecurityContext
                 |
                 +--> API with OAuth access token (separate protocol)
                 +--> SAML SP/IdP federation (separate protocol)
                 +--> OIDC broker (separate protocol)
~~~

Một Kerberos ticket cho `HTTP/portal.example.org` **không phải** OIDC ID Token cho RP hoặc SAML Assertion cho SP khác. Nếu Portal cần gọi downstream service thay mặt người dùng, phải có **Kerberos constrained delegation/S4U** được AD và service accounts cấu hình đúng, hoặc **OAuth2 token exchange/delegation** được Authorization Server chấp nhận, tùy kiến trúc. **Không copy `Authorization: Negotiate` của browser sang API khác** rồi hy vọng API sẽ coi là đã đăng nhập.

### 13.1. Danh tính đã xác thực không phải quyền ứng dụng

Khi provider nhận Kerberos principal `alice@CORP.EXAMPLE.ORG`, ứng dụng vẫn phải:
- Bind realm-qualified identity với local account một cách ổn định, không tự bỏ realm nếu có nhiều realms/trusts.
- Kiểm tra local status `ACTIVE`/`LOCKED`/`DISABLED`.
- Map approved `GrantedAuthority` từ local app/LDAP/directory có contract.
- Áp dụng tenant/resource ownership và method authorization.
- Từ chối khi account/policy service không khả dụng, không fallback `ROLE_USER` quá quyền.
- Không dùng workstation hostname, email hoặc `X-Remote-User` không được xác minh làm principal.

**Authn ≠ Authz.** 401 Negotiate chỉ bắt đầu xác thực; Kerberos ticket đúng chưa cấp quyền `admin` hoặc `payments:approve`.

### 13.2. Trường hợp reverse proxy tự terminate Kerberos

Một số môi trường dùng **IIS, Apache mod_auth_gssapi, NGINX module hoặc enterprise gateway** để xử lý Kerberos trước Spring. Lúc này gateway có thể gửi thông tin principal qua header/SSO session đã xác thực.

Chỉ dùng mô hình này khi Spring **tin duy nhất gateway đã xác thực**, kết nối backend được bảo vệ/mTLS/network ACL, gateway **strip/overwrite tất cả identity headers do client gửi** và có tài liệu trust contract. Nếu cả gateway và `SpnegoAuthenticationProcessingFilter` đều đọc cùng Authorization, có thể xảy ra double-auth hoặc token bị gateway consume. **Chỉ chọn một nơi có thẩm quyền xác thực request**, hoặc cấu hình delegation thật rõ ràng.

## 14. Bảo mật giao thức và vận hành

| Rủi ro | Biện pháp |
| --- | --- |
| **Kerberos token leak** trong Authorization log. | Redact request/response auth headers, không lưu raw Base64. |
| **Keytab compromise**. | Secret storage, hạn chế ACL, rotation, không bake vào image. |
| **SPN mismatch**. | Đăng ký HTTP/public-FQDN đúng, theo dõi duplicate SPNs/KVNO. |
| **Clock skew/realm misconfig**. | NTP, DNS/KDC discovery, trust relationship được quản trị. |
| **NTLM downgrade**. | Enforce Kerberos-only khi policy yêu cầu; kiểm tra mechanism thực sự. |
| **Proxy header stripping**. | End-to-end test `WWW-Authenticate` và `Authorization` qua ingress. |
| **Basic auth fallback lỏng lẻo**. | Chỉ bật khi có nhu cầu, qua HTTPS, provider và rate limit đúng. |
| **SPNEGO to unexpected origin**. | Browser intranet/trusted URI allowlist nhỏ, không broad wildcard tùy tiện. |
| **Unauthorized account admission**. | UserDetailsService với status/role/tenant checks. |
| **CSRF do ambient credentials**. | CSRF tokens, SameSite, origin checks và method rules. |
| **Host header/SPN confusion**. | Pin public host/trusted proxy, không dùng Host tùy ý để chọn keytab/realm. |
| **Failure loops**. | Giới hạn challenge retry, log reason codes, không hạ cấp trust để tránh 401. |
| **DoS bằng token oversized**. | Header size limits, rate limits, timeouts, reject invalid GSS. |
| **Stale local session**. | Idle/absolute timeout, reauth policy, revocation và account checks. |
| **Sự cố rollout Jakarta/Javax**. | Lock extension/core versions, compile/integration test. |

Một `401 WWW-Authenticate: Negotiate` tự nó **không tiết lộ mật khẩu**, nhưng có thể kích hoạt **ambient authentication** ở browser trusted. Vì vậy không phát challenge cho một host chưa được doanh nghiệp phê duyệt, không mở wildcard “mọi website đều được Kerberos SSO”, và bảo vệ service principal khỏi DNS spoofing/TLS interception.

## 15. Bộ test e2e cho SpnegoEntryPoint

| Trường hợp | Expected result |
| --- | --- |
| Anonymous vào `/protected`. | **401** và header `WWW-Authenticate: Negotiate`. |
| Anonymous vào `/public`. | **200** hoặc public response, không 401 Negotiate. |
| Browser domain có TGT, URL trong allowlist. | Sau challenge có `Authorization: Negotiate`, Kerberos validator xác thực được. |
| Browser không có TGT hoặc URL ngoài allowlist. | Không tự gửi credentials; nếu bật fallback thì nội dung login phù hợp. |
| `new SpnegoEntryPoint("/login")`. | **401 + Negotiate** cùng **forward nội bộ**, không tự 302. |
| POST protected không xác thực với forward login. | Kiểm tra method semantics, không bỏ CSRF/authorization. |
| Gửi `Authorization: Negotiate invalid-token`. | Không tạo authenticated principal/session. |
| Gửi token hợp lệ nhưng user local DISABLED. | Authentication/admission rejected. |
| User hợp lệ nhưng không có quyền admin. | **403** tại `/admin`; không nâng quyền từ Kerberos. |
| User hợp lệ và có quyền. | **200** ở protected endpoint. |
| SPN sai `HTTP/wrong.example.org`. | Không accept ticket cho Portal. |
| Keytab sai/KVNO cũ. | Validation failure, không fail-open. |
| Clock skew quá policy. | KDC/GSS fails; không disable checks. |
| Proxy xóa `WWW-Authenticate`. | Browser không thương lượng; test FAIL. |
| Proxy xóa `Authorization`. | Backend không validate được token; test FAIL. |
| NTLM được chọn khi policy Kerberos-only. | Reject/deny, không im lặng chấp nhận. |
| Client gửi token quá dài/malformed. | Reject/limit an toàn, không DoS hay log credential. |
| 401 continuation có GSS data. | Client/library xử lý theo protocol, không tự cắt token. |
| Client hoàn tất mutual auth với 200 + header. | Không làm hỏng final handshake do gateway. |
| `OPTIONS` preflight hợp lệ. | CORS xử lý theo policy, không đòi Kerberos từ preflight. |
| Browser session hết nhưng TGT còn. | Có thể Negotiate lại; phân biệt session mới với session cũ. |
| Local user revoked khi session còn. | Authorization/status policy chặn theo SLA; không tin Kerberos mãi. |
| Hai nodes cùng SPN nhưng keys khác. | Failover test phát hiện lỗi, sửa keytab distribution. |
| Tấn công giả `X-Remote-User` trực tiếp vào backend. | Header bị strip/ignored nếu không phải trusted gateway. |
| `spring-security-kerberos` thiếu dependency. | Build/runtime fail rõ, không đánh đồng với lỗi KDC. |

**Acceptance criteria:** không chỉ đếm 401/200; phải quan sát **challenge, Authorization exchange, GSS validation, local account admission, authorities, session lifecycle và refusal cases**. Trong integration test dùng KDC/AD test với SPN/keytab riêng, không copy prod keytab/tokens vào test.

## 16. Các hiểu lầm thường gặp

1. **“`SpnegoEntryPoint` tự xác minh Kerberos token.”** Sai: nó chỉ tạo challenge HTTP 401.
2. **“401 có nghĩa ứng dụng lỗi.”** Sai: 401 + Negotiate là bước đầu chuẩn khi chưa có credentials.
3. **“Server phải trả 302 đến /login để dùng SPNEGO.”** Sai: dùng HTTP authentication challenge.
4. **“`SpnegoEntryPoint("/login")` là redirect 302.”** Sai: RequestDispatcher.forward và giữ 401/Negotiate.
5. **“Có `Authorization: Negotiate` là đã authenticate.”** Sai: GSS token phải qua validator/acceptor.
6. **“`Negotiate` luôn đồng nghĩa Kerberos.”** Sai: cơ chế thực tế có thể thương lượng NTLM nếu policy/client/server hỗ trợ.
7. **“Không cần SPN nếu keytab đúng user.”** Sai: service ticket nhắm đúng `HTTP/<host>` và key matching.
8. **“HTTPS tương đương Kerberos.”** Sai: TLS bảo vệ kênh, Kerberos xác thực principal qua GSS.
9. **“SPN `HTTP/` nghĩa server phải chạy HTTP không mã hóa.”** Sai: Kerberos service class, website vẫn HTTPS.
10. **“Kerberos ticket đúng thì user chắc chắn có `ROLE_ADMIN`.”** Sai: quyền app cần local authorization.
11. **“Basic auth tự hoạt động nếu bật SpnegoEntryPoint.”** Sai: fallback cần form/provider riêng; không tự chấp nhận password.
12. **“`curl` không Negotiate được nghĩa server lỗi.”** Chưa chắc: curl/OS cần GSS support và credentials.
13. **“Tắt certificate verification giúp Kerberos an toàn hơn.”** Sai: làm yếu TLS và có thể phá trust.
14. **“Proxy có thể xóa `WWW-Authenticate` mà browser vẫn dùng SPNEGO.”** Không thể dựa vào việc client tự gửi preemptive token.
15. **“Một HTTP 401 rồi 200 luôn là handshake duy nhất.”** Sai: SPNEGO/GSS có thể cần continuation.
16. **“Lưu user trong session sau Kerberos thì mọi request mãi mãi đủ quyền.”** Sai: session timeout, account revoke, policy phải được kiểm soát.
17. **“SPNEGO cũng là OIDC/SAML/CAS.”** Sai: protocol khác, token và endpoint khác.
18. **“Nhận username từ reverse proxy header là tương đương GSS validation.”** Chỉ khi có gateway trust boundary xác thực/không cho spoof headers.
19. **“Kerberos login tự chứng minh MFA mới xảy ra.”** Sai: không có bảo đảm freshness/assurance nếu chưa có policy/bằng chứng.
20. **“Chỉ cần class `SpnegoEntryPoint` và securityFilterChain là production-ready.”** Sai: còn SPN/keytab/KDC/validator/user mapping/observability và tests.

## 17. Checklist triển khai production

1. Có xác định rõ ứng dụng dùng **SPNEGO/Kerberos HTTP authentication**, không nhầm OIDC/SAML/CAS không?
2. Client/browser có TGT/realm access và trusted URI allowlist giới hạn đúng host không?
3. HTTP request đầu tiên được challenge bằng **401 + `WWW-Authenticate: Negotiate`** không?
4. Request tiếp theo có `Authorization: Negotiate` tới đúng backend qua proxy mà không bị lộ logs không?
5. `SpnegoAuthenticationProcessingFilter`, `AuthenticationManager`, `KerberosServiceAuthenticationProvider` và `KerberosTicketValidator` đã được nối đúng không?
6. SPN `HTTP/public-fqdn@REALM`, keytab, KVNO, encryption types, keytab rotation và AD account có khớp không?
7. Có HTTPS, TLS trusted certificate, proxy/ingress header preservation và channel binding policy khi cần không?
8. Có khóa Kerberos-only/NTLM fallback theo chính sách tổ chức không?
9. `UserDetailsService` có map realm-qualified principal, local account status và app entitlements đúng không?
10. Có xử lý **401 khác 403**, không biến thiếu quyền thành vòng lặp login không?
11. Nếu bật `SpnegoEntryPoint("/login")`, có hiểu đây là **forward 401**, trang fallback và method safety không?
12. Fallback login có provider độc lập, HTTPS, CSRF/rate limit và policy chấp nhận rõ không?
13. Có chọn rõ SecurityContext repository/session strategy, session fixation và local logout behavior không?
14. CORS preflight/API endpoints có entry point phù hợp, không gợi Negotiate ngoài phạm vi không?
15. Multi-node deployment có keytab đúng SPN và session consistency, failover tests không?
16. Logs/APM có redact Authorization/GSS tokens, giới hạn size và có reason codes không?
17. Có unit test challenge và integration test GSS với test KDC/AD, wrong SPN/keytab/clock, replay, local disabled/role không?
18. Đã phân biệt Kerberos authentication với delegation tới downstream APIs và chính sách revocation chưa?

## 18. Tự kiểm tra kiến thức

1. **`SpnegoEntryPoint` trả gì khi chưa xác thực?** — **401** và `WWW-Authenticate: Negotiate`.
2. **Browser gửi gì ở bước tiếp?** — `Authorization: Negotiate <GSS-API/SPNEGO token>`.
3. **Class nào nhận header ở Spring?** — `SpnegoAuthenticationProcessingFilter`.
4. **Class nào kiểm tra service ticket?** — `KerberosServiceAuthenticationProvider` gọi `KerberosTicketValidator`, ví dụ `SunJaasKerberosTicketValidator`.
5. **SPN của web service trông thế nào?** — `HTTP/portal.example.org@CORP.EXAMPLE.ORG`.
6. **`SpnegoEntryPoint("/login")` redirect hay forward?** — **Server-side forward**, giữ HTTP 401 + Negotiate.
7. **Vì sao 401 có thể là bình thường?** — Vì HTTP auth cần challenge trước khi browser gửi credentials.
8. **Vì sao không tạo principal chỉ vì thấy Negotiate header?** — Vì header có thể chứa token giả/hỏng/cho SPN khác; GSS phải xác minh.
9. **Sau xác thực, user thiếu role thì phản hồi gì?** — Thường **403 Forbidden**.
10. **SPNEGO luôn chỉ dùng Kerberos?** — Không; cơ chế Negotiate có thể có NTLM fallback tùy policy/implementation.
11. **Tại sao public hostname liên quan keytab?** — Client xin service ticket cho `HTTP/public-host`, server acceptor phải có khóa của SPN đó.
12. **Tại sao proxy có thể khiến 401 vòng lặp?** — Nó có thể xóa/chuyển `Authorization` hoặc `WWW-Authenticate`.
13. **Kerberos TGT hết hạn đồng nghĩa HttpSession lập tức mất?** — Không tự động; đây là hai vòng đời.
14. **Local logout có xóa OS Kerberos TGT không?** — Không; request sau có thể tự Negotiate lại.
15. **Chỉ dùng `SpnegoEntryPoint` có đủ login Kerberos không?** — Không; còn filter, provider, validator, local mapping và cấu hình SPN/keytab.
16. **Dùng HTTPS có đủ để chứng minh user Kerberos?** — Không; TLS chỉ bảo vệ kênh, GSS validation mới chứng minh principal.
17. **Một request `/public` có cần 401 Negotiate không?** — Không khi được `permitAll`.
18. **Browser không hỗ trợ Negotiate nên xử lý sao?** — Fallback đã được thiết kế hoặc trả 401 có hướng dẫn; không tự cấp quyền.
19. **Tại sao không gửi Negotiate token thẳng tới API khác?** — Ticket bị ràng buộc service principal/trust; cần delegation/token exchange đúng giao thức.
20. **Nên test 401 theo cách nào?** — Kiểm tra status và header, sau đó E2E browser/KDC/validator/local permission, không chỉ curl 401.

## Tài liệu tham khảo

- [Spring Security Kerberos API — SpnegoEntryPoint constructors, commence, forward behavior](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html)
- [Spring Security Kerberos API — SpnegoAuthenticationProcessingFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html)
- [Spring Security Kerberos API — KerberosServiceAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html)
- [Spring Security Kerberos API — SunJaasKerberosTicketValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosTicketValidator.html)
- [Spring Security Kerberos open-source implementation — SpnegoEntryPoint.java](https://github.com/spring-projects/spring-security-kerberos/blob/main/spring-security-kerberos-web/src/main/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.java)
- [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication in Microsoft Windows](https://www.rfc-editor.org/rfc/rfc4559.html)
- [RFC 4178 — The SPNEGO GSS-API Mechanism](https://www.rfc-editor.org/rfc/rfc4178.html)
- [RFC 4120 — The Kerberos Network Authentication Service (V5)](https://www.rfc-editor.org/rfc/rfc4120.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
