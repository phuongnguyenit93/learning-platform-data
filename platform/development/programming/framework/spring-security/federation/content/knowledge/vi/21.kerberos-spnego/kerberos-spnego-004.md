# SPNEGO, HTTP Negotiate và vai trò của trình duyệt

> **Module:** Spring Security – federation. **Nhóm:** Kerberos và SPNEGO. Bài học giải thích trình duyệt tham gia **Integrated Windows Authentication/Single Sign-On** qua HTTP `Negotiate` như thế nào; phân biệt rõ **Kerberos**, **GSS-API/SSPI**, **SPNEGO**, **SPN**, **keytab**, **ticket cache**, browser allowlist, HTTP 401 và cơ chế xác thực trong Spring Security. Ví dụ dùng Java 17, Spring Boot 3.5.x, Spring Security 6.5.x và Spring Security Kerberos 2.2.0. Mọi hostname/realm trong bài là **ví dụ**, không phải dịch vụ thật.

## 1. Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt Kerberos v5, GSS-API, Windows SSPI, SPNEGO và HTTP authentication scheme `Negotiate`; không gọi cả năm thứ là một giao thức duy nhất.
2. Mô tả một browser nhận `401 WWW-Authenticate: Negotiate`, hỏi hệ điều hành tạo GSS context token, gửi `Authorization: Negotiate <base64-token>`, xử lý vòng lặp và nhận kết quả.
3. Giải thích user có thể SSO mà không nhập password một lần nữa nhờ **TGT và service ticket**; browser không gửi TGT hoặc keytab lên web server.
4. Xác định Service Principal Name `HTTP/intranet.example.org@EXAMPLE.ORG`, vai trò của KDC/Active Directory, DNS/FQDN, server keytab và Java GSS acceptor.
5. Cấu hình trusted sites trên Microsoft Edge/Chrome/Firefox và phân biệt **cho phép xác thực SSO** với **Kerberos credential delegation**.
6. Nhận biết `Negotiate` có thể chọn NTLM trong một số môi trường, do đó phải xác minh **negotiated mechanism** nếu cần chính sách Kerberos-only.
7. Tích hợp `SpnegoEntryPoint`, `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator` và `UserDetailsService` vào Spring Security.
8. Hiểu sự khác nhau giữa **HTTP Negotiate authentication**, **HTTP session cookie**, **application authorization**, **CSRF protection**, **mutual authentication** và **TLS**.
9. Chạy chương trình Java 17 thuần JDK phân loại HTTP header, đối chiếu stdout và biết vì sao Base64 decode không phải Kerberos validation.
10. Lập ma trận test positive/negative và runbook cho KDC/SPN/keytab/KVNO, browser allowlist, reverse proxy, NTLM fallback, channel binding và double-hop.

**Đầu vào nên có:** HTTP status/headers, browser DevTools, TLS và reverse proxy, Java 17, Spring Security `SecurityFilterChain`, kiến thức Kerberos cơ bản (KDC, principal, keytab). Bài tập dùng môi trường AD/KDC sandbox riêng; không cần môi trường đó để chạy phần Java thuần.

## 2. Tổng quan: bốn lớp và trách nhiệm

| Lớp | Chuẩn/cơ chế | Vai trò |
| --- | --- | --- |
| **Kerberos v5** | RFC 4120/4121 | KDC cấp TGT và **service ticket** cho service principal; service xác minh token bằng secret key |
| **GSS-API / SSPI** | Java/Unix GSS-API, Windows SSPI | APIs để client tạo và server chấp nhận **security context tokens** |
| **SPNEGO** | RFC 4178 | Thương lượng cơ chế xác thực GSS-API có thể dùng, chẳng hạn Kerberos hoặc NTLM theo môi trường |
| **HTTP Negotiate** | RFC 4559 | Chở GSS/SPNEGO tokens trong HTTP `WWW-Authenticate` và `Authorization` |
| **Spring Security** | Servlet authentication architecture | Dùng filter/provider xác minh token rồi tạo `Authentication`, lưu `SecurityContext` và kiểm authorization |

**Không đồng nhất các lớp:**

- `Authorization: Negotiate ...` là **header HTTP**, không phải bằng chứng mặc định rằng cơ chế được chọn là Kerberos.
- SPNEGO **không phải phiên bản mới của Kerberos**; nó là mechanism negotiation. Trong một số môi trường Windows, NTLM có thể được chọn.
- Kerberos service ticket **không phải JWT, SAML Assertion, OAuth Access Token hay cookie `JSESSIONID`**.
- SPNEGO là cơ chế **authentication**; không tự quyết định user có quyền đọc báo cáo, sửa đơn hàng hay truy cập tenant khác.
- Browser không giữ **server keytab** và không phải KDC. Browser trao đổi GSS token với server, hệ điều hành/security library xử lý credentials/tickets.

### 2.1. Bức tranh tổng thể

~~~text
                         Kerberos Realm EXAMPLE.ORG
                +-------------------------------------+
                | KDC / Active Directory Controller   |
                | - Authentication Service (AS)       |
                | - Ticket Granting Service (TGS)     |
                +-------------------------------------+
                       ^                       |
                       | request ticket        | service ticket
                       | for HTTP/host         v
User -> Desktop login -> OS Ticket Cache <-> Browser/GSS/SSPI
        TGT thường có             |                |
                                 +-- SPNEGO token--+
                                              |
                                              | HTTPS
                                              | WWW-Authenticate: Negotiate
                                              | Authorization: Negotiate ...
                                              v
                               intranet.example.org (Web SP)
                                      |
                           GSS accept with SPN/keytab
                                      |
                           Spring Security Authentication
                                      |
                           UserDetails + tenant/role policy
                                      |
                           Business resource / HTTP 200
~~~

**Giá trị của SSO:** Một user đã xác thực với domain/KDC trước đó có thể mở intranet website mà không cần nhập mật khẩu lần nữa. Điều này chỉ xảy ra nếu **browser trusted-site policy, ticket cache, SPN, KDC, server keytab và app config** cùng phù hợp.

## 3. Kerberos trước khi có HTTP

1. User đăng nhập Windows domain hoặc lấy credentials trong một Kerberos realm được hỗ trợ. Với MIT Kerberos có thể dùng `kinit lan@EXAMPLE.ORG` trong môi trường test.
2. KDC cấp **Ticket-Granting Ticket (TGT)** và user giữ trong **OS ticket cache**, không gửi TGT tới web server.
3. Browser cần truy cập `https://intranet.example.org/private`. OS/GSS xác định service principal thông thường là `HTTP/intranet.example.org@EXAMPLE.ORG`.
4. Nếu client chưa có service ticket cho SPN này, nó dùng TGT để yêu cầu KDC TGS phát **service ticket dành riêng cho HTTP/intranet.example.org**.
5. Client xây Kerberos authenticator/AP-REQ theo GSS-API và bọc vào SPNEGO token.
6. Browser mang bytes đó trong `Authorization: Negotiate <base64-token>`.
7. Server dùng service principal/keytab để nhận GSS context, xác minh user và loại ticket/token không phù hợp.
8. Spring Security dùng user principal đã được xác thực, tra user status/roles/tenant rồi áp quyền dữ liệu.

### 3.1. Các vật mang quan trọng

| Vật mang | Ai sở hữu | Dùng để làm gì? |
| --- | --- | --- |
| **TGT** | User client/KDC | Xin service tickets khác, không gửi cho Portal |
| **Service ticket** | Client có được từ KDC | Xác thực tới một SPN cụ thể, chẳng hạn HTTP/intranet.example.org |
| **AP-REQ** | Client tạo từ service ticket và authenticator | Chứng minh identity đối với service acceptor |
| **AP-REP** | Service trả khi cần mutual authentication | Client kiểm service trong Kerberos security context |
| **SPNEGO GSS token** | Client/server trao đổi | Token chứa/thương lượng mechanism, chở qua HTTP Negotiate |
| **Server keytab** | Service process hoặc trusted gateway | Chứa long-term secret keys để accept Kerberos service tickets |
| **JSESSIONID** | Browser + Spring web app | Local HTTP session sau authentication, không phải Kerberos ticket |

**Thực hành cần nhớ:** Khi user login lại ngay sau khi “Logout Portal”, đó có thể là do browser vẫn có TGT/service ticket trong OS cache. Xóa local `JSESSIONID` **không xóa TGT**, và server không thể xóa Kerberos credentials của OS user bằng một response Set-Cookie.

### 3.2. FQDN và SPN

~~~text
Browser public URL:
    https://intranet.example.org/private

Kerberos HTTP service principal:
    HTTP/intranet.example.org@EXAMPLE.ORG

Server acceptor:
    service-principal = HTTP/intranet.example.org@EXAMPLE.ORG
    keytab = /run/secrets/http-intranet.keytab
~~~

`HTTP/` là **service class Kerberos**, kể cả khi transport dùng HTTPS; hostname phải tương ứng định danh mà client GSS chọn, thường là FQDN public. Realm là danh tính Kerberos, không luôn suy ra từ HTTP host nếu tổ chức có cross-realm trusts. DNS alias/CNAME, load balancer, IP truy cập và proxy có thể khiến client xin service ticket cho tên **khác** keytab của server.

Trường hợp cùng một service chạy trên nhiều nodes, service account/keytab distribution phải theo policy bảo mật được duyệt. Không chia sẻ một keytab rộng cho các ứng dụng không liên quan chỉ để tránh lỗi SPN.

## 4. HTTP Negotiate: chu trình 401 challenge-response

Theo RFC 4559, ban đầu một request chưa có authentication:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Accept: text/html
~~~

Web server trả challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Browser thấy scheme, xét trusted-site policy rồi gọi OS security library. Nếu được phép và có Kerberos credentials hợp lệ, browser gửi tiếp:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Authorization: Negotiate <base64-of-gss-spnego-token>
~~~

**Ký hiệu trong dấu ngoặc chỉ là placeholder giải thích format**, không phải token có thể gửi; đừng sao chép làm credential.

Server Base64-decode để lấy bytes, đưa vào **GSS acceptor**/Kerberos provider. Khi hoàn thành, server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8

Hello authenticated user
~~~

### 4.1. Không luôn chỉ có hai lượt

GSS-API `initSecContext`/`acceptSecContext` có thể cần thêm lượt trao đổi. Nếu context chưa hoàn tất, server trả một 401 mới **có token continuation**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate <base64-response-token>
~~~

Client xử lý token và gửi tiếp `Authorization: Negotiate ...`. Nếu mutual authentication yêu cầu final token, RFC 4559 cho phép server gửi token cuối **trong response 200**:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate <base64-final-token>
Content-Type: text/plain; charset=UTF-8

Authenticated
~~~

**401 đầu không phải lỗi cuối**. Phải phân biệt “challenge bình thường” với “GSS/credentials bị từ chối”, và phân biệt 401 continuation với 401 loop do sai SPN/keytab. Proxy không được tự loại bỏ các headers cần thiết trên 401 hoặc 200.

### 4.2. Có thể không thấy 401 đầu tiên

Một browser đã biết server hỗ trợ Negotiate có thể chủ động gửi token hoặc tái sử dụng authentication/session context; các trình duyệt có cache và policy khác nhau. Nếu Spring đã giữ `SecurityContext` trong HTTP session, request tiếp theo còn có thể chỉ mang cookie `JSESSIONID`. Vì vậy “không thấy 401” hoặc “không thấy Authorization trong mỗi request” **không đủ** kết luận SPNEGO chưa từng chạy.

### 4.3. 401 khác 407

- **401 + WWW-Authenticate: Negotiate**: origin server cần authentication.
- **407 + Proxy-Authenticate: Negotiate**: **forward HTTP proxy** cần authentication trước khi chuyển request.
- `Authorization` khác `Proxy-Authorization`. Token có target SPN khác; không chuyển token dành cho proxy tới origin server hay ngược lại.
- Nếu DevTools cho thấy 407, hãy kiểm proxy/PAC/client policy, không chỉ cấu hình Spring Security tại ứng dụng đích.

### 4.4. Tại sao Base64 không bảo vệ HTTP?

Base64 mã hóa **biểu diễn byte sang text** cho header; không mã hóa dữ liệu hay bảo vệ content. HTTP Negotiate là authentication scheme, không tự bảo vệ mọi HTTP request body/header. **HTTPS/TLS vẫn cần** để chống nghe lén, chỉnh sửa, credential leakage qua intermediaries và bảo vệ session cookies. Dùng HSTS, secure cookies và TLS policy theo môi trường.

## 5. Trình duyệt thực sự làm gì?

Browser là HTTP client và là một **policy enforcement point**: nó chỉ tự gửi Integrated Authentication khi host và môi trường phù hợp.

| Thời điểm | Browser/OS | Server |
| --- | --- | --- |
| User mở intranet URL | Browser gửi GET qua HTTPS | Spring/nginx/gateway xem request có authentication không |
| Server yêu cầu xác thực | Browser nhận 401 Negotiate | EntryPoint phát challenge |
| Xét chính sách | Browser hỏi trusted-site/enterprise policy; OS kiểm ticket cache | Server chưa biết identity chỉ từ 401 |
| Tạo token | SSPI (Windows) hoặc GSS libraries tạo token, xin service ticket từ KDC nếu cần | Server không tham gia xin ticket thay browser |
| Gửi request mới | Browser gửi `Authorization: Negotiate ...` | Filter đưa bytes cho Kerberos/GSS acceptor |
| Tiếp tục negotiation | Browser xử lý token từ 401/200 | Server `acceptSecContext` và có thể phát response token |
| Hoàn tất login | Browser nhận nội dung và có thể cookie session | Spring Authentication và app authorization |
| User refresh hoặc logout local | Browser có thể dùng tickets còn trong OS cache | Spring có thể yêu cầu Negotiate lại hoặc dùng session |

**Browser không gửi domain password plaintext trong Kerberos thông thường.** Nó cũng **không gửi TGT** cho web server chỉ để SSO; nó trình chứng thực dành cho **HTTP service principal**. Tuy vậy SPNEGO trên Windows có thể fallback NTLM, nên không thể coi mọi token Negotiate là hoàn toàn không chứa thông tin credential nhạy cảm. Browser trust policy và mechanism restriction vẫn quan trọng.

### 5.1. Browser không quyết định user là admin

Sau Kerberos validation, server có thể biết principal như `lan@EXAMPLE.ORG`. Nhưng **ứng dụng** phải kiểm enabled status, tenant, role và quyền resource. Ticket hợp lệ chỉ chứng minh authentication trong realm/trust policy, không cho user xem dữ liệu của người khác hoặc mọi API nội bộ.

### 5.2. Browser có thể hiển thị dialog hay fallback form

Nếu OS không có TGT, host không nằm trong allowlist hoặc mechanism không hỗ trợ, client có thể không gửi Negotiate token; tùy cấu hình browser/app, user thấy credential prompt, HTTP 401, hoặc form/OIDC/SAML fallback được ứng dụng cung cấp. Không gán một hành vi duy nhất cho mọi browser/OS.

### 5.3. Silent SSO khác credential delegation

**Integrated Authentication** chứng minh user đến web server. **Kerberos delegation** cho phép web server dùng delegated credentials gọi **một service khác** thay user, cần KDC/AD, service account, browser policy và quyền hạn riêng. Cho browser gửi Negotiate tới Portal **không đồng nghĩa** Portal đã có quyền gọi database/API dưới identity user.

## 6. Cấu hình Edge, Chrome và Firefox

Nếu một website tùy ý có thể phát 401 Negotiate và browser tự gửi credentials, user dễ bị dẫn tới host không đáng tin. Vì thế các browser có trusted-site lists.

### 6.1. Microsoft Edge/Chromium: AuthServerAllowlist

Microsoft Edge enterprise policy `AuthServerAllowlist` xác định các server được phép dùng Integrated Authentication khi gặp challenge. Nếu không được cấu hình, Edge có thể dựa trên việc site có được coi là intranet hay không theo chính sách platform; cấu hình explicit giúp giảm bất ngờ.

Ví dụ danh sách host đã duyệt:

~~~text
AuthServerAllowlist = intranet.example.org,reports.example.org
~~~

Kiểm effective policy tại `edge://policy`. Trong doanh nghiệp, triển khai qua GPO/MDM/ADMX phù hợp; đừng yêu cầu user thêm wildcard `*` hoặc host do người khác sở hữu. Danh sách broad wildcard cho tất cả subdomains có thể chứa các site không đáng tin và làm credential exposure.

`AuthNegotiateDelegateAllowlist` là **policy khác**, cho phép **credential delegation** tới các servers chỉ định. Nếu ứng dụng chỉ cần user login SSO tới một intranet page, **không mặc định bật delegation**.

~~~text
AuthServerAllowlist
    -> browser được phép Integrated Authentication với host

AuthNegotiateDelegateAllowlist
    -> browser được phép delegated Kerberos credentials tới host
       (chỉ khi KDC/server-side policy cũng cho phép)
~~~

### 6.2. Chrome/Chromium

Chrome Enterprise có các HTTP authentication policies như `AuthServerAllowlist` và `AuthNegotiateDelegateAllowlist`, nhưng cách deploy/OS integration thay đổi theo platform và version. Kiểm `chrome://policy` trên thiết bị thực. Một số tài liệu cũ dùng tên `AuthServerWhitelist`/command-line flags đời cũ; **không copy-paste cách cấu hình đó cho phiên bản hiện tại mà không kiểm docs**.

### 6.3. Firefox: Authentication.SPNEGO

Firefox Enterprise có policy `Authentication` với trường `SPNEGO` là danh sách sites được phép, `Delegated` là danh sách riêng cho delegation. Ví dụ sandbox policy:

~~~json
{
  "policies": {
    "Authentication": {
      "SPNEGO": [
        "https://intranet.example.org",
        "https://reports.example.org"
      ],
      "Delegated": []
    }
  }
}
~~~

Preferences cần biết:
- `network.negotiate-auth.trusted-uris`: sites được phép dùng SPNEGO.
- `network.negotiate-auth.delegation-uris`: sites được phép Kerberos delegation.
- `network.automatic-ntlm-auth.trusted-uris`: cấu hình riêng cho NTLM.
- `about:config` có thể kiểm trong sandbox; production dùng enterprise policy để tránh user tự mở host lạ.

Theo policy docs, Firefox matching có thể chấp nhận một domain và subdomains của nó (dot-boundary). Nếu cho phép `https://example.org`, không được mặc nhiên nghĩ chỉ đúng apex host được nhận credentials; hãy kiểm phạm vi subdomains và chọn domain hẹp có quyền sở hữu rõ.

### 6.4. Browser không có ticket hoặc thiết bị unmanaged

Firefox/Chrome/Edge trên Linux/macOS còn phụ thuộc GSS libraries/credential cache, không chỉ một JSON policy. Safari và mobile browsers có khả năng khác nhau theo OS và managed-device configuration. Đối với client REST tự động, `curl --negotiate`, Java HTTP client/GSS hoặc agent phù hợp mới là chủ thể xử lý; không phải mọi HTTP client sẽ tự lấy Kerberos ticket như desktop browser.

**Bất biến:** Browser policy chỉ quyết định client có thể **bắt đầu/tiếp tục Negotiate**. Nó không làm SPN đúng, không tạo server keytab và không thay authorization.

## 7. SPN, DNS, realm và keytab trên server

Trong environment ví dụ:

~~~text
Public URL  = https://intranet.example.org/private
SPN         = HTTP/intranet.example.org@EXAMPLE.ORG
Service key = /run/secrets/http-intranet.keytab
KDC/realm   = EXAMPLE.ORG
~~~

**Giải nghĩa:**
- `HTTP/` là Kerberos service class (vẫn là HTTP/ khi website dùng HTTPS).
- `intranet.example.org` là FQDN mà browser/GSS chọn làm Kerberos service target.
- `EXAMPLE.ORG` là realm; có thể khác hostname domain trong hệ thống cross-realm.
- `keytab` ở web service chứa secret keys cho service principal. Chỉ public website owner/service account có quyền sử dụng.
- **KVNO** là key version number; keytab cũ sau password rotation có thể không giải mã được ticket mới.
- Enctype (AES types), clock skew, key rotation, duplicate SPN cũng ảnh hưởng GSS validation.

### 7.1. Lỗi phổ biến với alias và load balancer

Browser truy cập `https://intranet.example.org` nhưng app chạy phía sau LB tại `app01.internal.example.org`. Client thường xin ticket cho `HTTP/intranet.example.org`, **không** tự xin cho internal node tên `app01`. Vì thế phải quyết định:

**Mô hình A – app là acceptor:** LB chuyển `Authorization: Negotiate ...` tới app, app có keytab phù hợp public SPN và kiểm GSS token. TLS/mTLS giữa LB→app, source network policy và việc forward headers cần được bảo vệ.

**Mô hình B – gateway là acceptor:** Gateway nhận/verify SPNEGO bằng keytab và chuyển **verified identity** tới app bằng secure channel (mTLS/signed identity assertion/headers do gateway strip/overwrite). App không tin header `X-User` do browser gửi trực tiếp.

Nếu LB tự consume Authorization rồi app vẫn đòi Negotiate, sẽ có 401 loop. Nếu app dùng keytab chỉ cho internal SPN, GSS reject. Cách sửa là **đồng bộ public SPN và nơi terminate**, không tắt validation.

### 7.2. Những lệnh kiểm tra môi trường

**Windows domain workstation/admin:**

~~~powershell
klist
setspn -Q HTTP/intranet.example.org
~~~

`klist` xem user TGT/service tickets; `setspn -Q` tra SPN đăng ký trong AD (quyền/môi trường phù hợp). Không tự thực hiện thay đổi AD `setspn -S` trên production nếu chưa được phê duyệt.

**Linux/macOS với Kerberos tools:**

~~~bash
klist
kvno HTTP/intranet.example.org
~~~

`kvno` thường cần TGT và network KDC, có thể yêu cầu ticket mới cho service principal. Trên server có quyền đọc keytab:

~~~bash
klist -k /run/secrets/http-intranet.keytab
~~~

Các lệnh này là **chẩn đoán thật phụ thuộc môi trường**; không có stdout cố định. Đừng copy ticket cache, keytab hoặc `Authorization` token vào bug report.

### 7.3. TLS, channel binding và proxy

SPNEGO HTTP authentication **không tự mã hóa request body/header**; dùng HTTPS public, HSTS, Secure/HttpOnly session cookies. Nếu môi trường bật **Extended Protection for Authentication / channel binding**, một số topology TLS termination dẫn tới `GSSException: Channel binding mismatch`. Phải điều tra cert, TLS endpoint, binding policy, reverse proxy và GSS implementation, **không** khắc phục bằng cách tắt EPA/TLS verification mù quáng.

## 8. Spring Security Kerberos hoạt động ra sao?

Spring Security Kerberos là extension riêng. Tài liệu phiên bản **2.2.0** ghi nó được build/test với **JDK 17, Spring Security 6.5.1 và Spring Framework 6.2.8**, rất phù hợp để học trên Spring Boot 3.5.x. Khi triển khai, kiểm effective dependency versions và ứng dụng container trước khi go-live.

| Thành phần | Trách nhiệm |
| --- | --- |
| `SpnegoEntryPoint` | Trả HTTP 401 + `WWW-Authenticate: Negotiate` để browser bắt đầu SSO |
| `SpnegoAuthenticationProcessingFilter` | Trích token từ `Authorization`, tạo `KerberosServiceRequestToken` và gọi AuthenticationManager |
| `KerberosServiceAuthenticationProvider` | Validate token bằng ticket validator; kết hợp `UserDetailsService` |
| `SunJaasKerberosTicketValidator` | Dùng Java/JGSS, servicePrincipal/keytab để accept Kerberos service token |
| `UserDetailsService` | Load user details, enabled state và GrantedAuthorities; KHÔNG làm Kerberos verification |
| `SecurityFilterChain` | Gắn entry point/filter, chặn unauthorized resources |
| `SecurityContext`/Session | Giữ authentication kết quả của app, không tự lưu Kerberos TGT |
| `AuthorizationManager`/Business service | Kiểm role, tenant, resource ownership, method permissions |

### 8.1. Luồng filter

~~~text
GET /whoami without Spring Security authentication
        |
        v
Authorization filter requires authenticated()
        |
        v
ExceptionTranslationFilter -> SpnegoEntryPoint
        |
        | 401 WWW-Authenticate: Negotiate
        v
Browser + OS/GSS + KDC
        |
        | Authorization: Negotiate <base64 token>
        v
SpnegoAuthenticationProcessingFilter
        |
        v
KerberosServiceRequestToken -> AuthenticationManager
        |
        v
KerberosServiceAuthenticationProvider
        |
        +--> SunJaasKerberosTicketValidator
        |       verify GSS token with SPN/keytab
        |
        +--> UserDetailsService
                active user + application authorities
        |
        v
Spring Security authenticated principal
        |
        v
Application authorization -> 200 or 403
~~~

**Không viết controller tự Base64-decode header rồi lấy username bằng regex**. Mọi bytes dù decode được đều có thể là giả. Chỉ GSS acceptor dùng trusted service key và mechanism policy mới xác thực được.

## 9. Project Spring Boot 3.5/Java 17 tích hợp SPNEGO

Project sau minh họa **chỉ browser→server authentication**, không bật delegation sang backend, không tự chạy KDC. Maven/JDK17 build có thể hoạt động khi dependencies có sẵn; **login Kerberos end-to-end chỉ chạy sau khi có AD/KDC, SPN, keytab, browser trusted-site policy và HTTPS ingress thật**.

### 9.1. Cấu trúc

~~~text
negotiate-web/
  pom.xml
  src/main/
    java/demo/NegotiateApplication.java
    resources/application.yml
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.1</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>negotiate-web</artifactId>
  <version>1.0.0</version>
  <properties><java.version>17</java.version></properties>
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
      <groupId>org.springframework.security.kerberos</groupId>
      <artifactId>spring-security-kerberos-core</artifactId>
      <version>2.2.0</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.security.kerberos</groupId>
      <artifactId>spring-security-kerberos-web</artifactId>
      <version>2.2.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Spring Boot BOM quản lý Spring Security; extension 2.2.0 được kiểm thử với Spring Security 6.5.1. Kiểm `mvn dependency:tree` và dependency alignment của bản patch thực tế. Không dùng các tutorial Spring Security Kerberos 1.x phụ thuộc javax.servlet với Boot 3.x Jakarta Servlet mà không xác minh khả năng tương thích.

### 9.3. application.yml

~~~yaml
server:
  port: 8080

kerberos:
  service-principal: HTTP/intranet.example.org@EXAMPLE.ORG
  keytab-path: /run/secrets/http-intranet.keytab
~~~

Keytab chứa secret key, phải mount read-only từ secret manager/volume với quyền tối thiểu. Không commit vào Git, container image, classpath hay lưu trong source. Đừng đặt production keytab trong user downloads hoặc log.

### 9.4. NegotiateApplication.java

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class NegotiateApplication {

    public static void main(String[] args) {
        SpringApplication.run(NegotiateApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        // DEMO: mọi user Kerberos đã verified nhận ROLE_USER.
        // Production: tra directory/DB, enabled status, tenant, roles.
        return name -> new User(
                name, "{noop}unused",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            Environment env,
            UserDetailsService users) throws Exception {

        String principal =
                env.getRequiredProperty("kerberos.service-principal");
        String path =
                env.getRequiredProperty("kerberos.keytab-path");

        var validator = new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(path));
        validator.setDebug(false);

        var provider = new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);

        var authManager = new ProviderManager(provider);
        var spnegoFilter = new SpnegoAuthenticationProcessingFilter();
        spnegoFilter.setAuthenticationManager(authManager);

        // Tạo Filter nội bộ cho SecurityFilterChain, không đăng ký
        // một servlet Filter @Bean nữa để tránh double execution.
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(new SpnegoEntryPoint()))
                .addFilterBefore(
                        spnegoFilter, BasicAuthenticationFilter.class)
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Open /whoami for HTTP Negotiate";
        }

        @GetMapping("/whoami")
        Map<String, Object> whoami(Authentication auth) {
            return Map.of(
                    "authenticated", auth.isAuthenticated(),
                    "principal", auth.getName());
        }
    }
}
~~~

**Cơ chế đoạn code:**
- `SpnegoEntryPoint` yêu cầu browser Negotiate nếu `/whoami` chưa được xác thực.
- `SpnegoAuthenticationProcessingFilter` đọc Authorization Negotiate và gọi `ProviderManager`.
- `KerberosServiceAuthenticationProvider` dùng validator Kerberos/JGSS và `UserDetailsService` để tạo authenticated principal.
- `SunJaasKerberosTicketValidator` nhận service principal/keytab từ cấu hình được bảo vệ.
- `users()` chỉ là **demo**: cấp ROLE_USER cho mọi Kerberos principal đã xác minh; production phải kiểm directory/user enabled, tenant, account status và per-resource policy.
- Filter được tạo trong method chain, **không đặt filter @Bean cho Servlet container đăng ký thêm** (tránh chạy trùng/ngoài security chain).
- Đây không phải Kerberos delegation demo; không có backend API call thay user.

**Giới hạn quan trọng:** Mẫu code là cấu hình tham khảo của extension 2.2.0; khi framework/BOM patch khác hoặc production có multiple chains, authentication failures/fallback/session strategies cần integration test riêng. Không dùng một `SpnegoEntryPoint` đơn lẻ để suy rằng keytab đã đúng.

### 9.5. Chạy project

Sau khi đã đăng ký `HTTP/intranet.example.org@EXAMPLE.ORG` và mount keytab hợp lệ, dùng JDK 17:

~~~bash
mvn spring-boot:run
~~~

Để browser làm Kerberos SSO, mở public hostname có HTTPS theo ingress đã cấu hình, ví dụ `https://intranet.example.org/whoami`. `GET /` public trả:

~~~text
Open /whoami for HTTP Negotiate
~~~

Một request chưa có authentication tới `/whoami` có thể nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Sau browser/GSS hoàn tất và Spring Security chấp nhận, kết quả **có dạng**:

~~~json
{
  "authenticated": true,
  "principal": "lan@EXAMPLE.ORG"
}
~~~

JSON này là **mẫu**; principal thực tế phụ thuộc realm/user. Nếu chưa có KDC, keytab, SPN, TLS public host và browser trusted-site policy, không thể kết luận SSO chạy chỉ từ lệnh Maven. Thường không dùng `http://localhost:8080` để kiểm SPN public; browser có thể không xin đúng ticket.

## 10. Ví dụ Java 17 chạy độc lập: gate HTTP trước GSS

Mẫu này không cần Kerberos realm. Nó chỉ minh họa chính sách **Host allowlist + HTTP Authorization Negotiate syntax + Base64 decode + length guard** trước khi giao bytes cho GSS validator. Trạng thái `PASS_TO_GSS` **không đồng nghĩa authentication thành công**. Ngưỡng kích thước 64 trong demo chỉ để cho dễ thử, rất nhỏ so với token GSS production.

**Tệp `NegotiateHeaderDemo.java`:**

~~~java
import java.util.Base64;
import java.util.Set;

public class NegotiateHeaderDemo {

    enum Decision {
        CHALLENGE, DENY_HOST, DENY_SCHEME,
        DENY_FORMAT, DENY_SIZE, PASS_TO_GSS
    }

    private static final Set<String> APPROVED = Set.of(
            "intranet.example.org", "reports.example.org");

    static Decision decide(String host, String authorization) {
        if (!APPROVED.contains(host)) {
            return Decision.DENY_HOST;
        }
        if (authorization == null || authorization.isBlank()) {
            return Decision.CHALLENGE;
        }

        int space = authorization.indexOf(' ');
        if (space < 0 ||
            !authorization.substring(0, space)
                    .equalsIgnoreCase("Negotiate")) {
            return Decision.DENY_SCHEME;
        }

        String encoded = authorization.substring(space + 1).trim();
        if (encoded.isEmpty()) {
            return Decision.DENY_FORMAT;
        }
        if (encoded.length() > 64) {
            return Decision.DENY_SIZE;
        }
        try {
            byte[] bytes = Base64.getDecoder().decode(encoded);
            return bytes.length == 0
                    ? Decision.DENY_FORMAT
                    : Decision.PASS_TO_GSS;
        } catch (IllegalArgumentException ex) {
            return Decision.DENY_FORMAT;
        }
    }

    static void show(String label, String host, String auth) {
        System.out.println(label + "=" + decide(host, auth));
    }

    public static void main(String[] args) {
        show("missing", "intranet.example.org", null);
        show("evilHost", "evil.example.org", null);
        show("basic", "intranet.example.org", "Basic dXNlcjpwYXNz");
        show("bareNegotiate", "intranet.example.org", "Negotiate");
        show("emptyNegotiate", "intranet.example.org", "Negotiate ");
        show("invalidBase64", "intranet.example.org", "Negotiate !!!");
        show("fakeShape", "intranet.example.org", "Negotiate dG9rZW4=");
        show("tooLong", "intranet.example.org",
                "Negotiate " + "A".repeat(65));
        show("reports", "reports.example.org", "Negotiate dG9rZW4=");
    }
}
~~~

Chạy JDK 17:

~~~bash
javac NegotiateHeaderDemo.java
java NegotiateHeaderDemo
~~~

**Stdout chính xác:**

~~~text
missing=CHALLENGE
evilHost=DENY_HOST
basic=DENY_SCHEME
bareNegotiate=DENY_SCHEME
emptyNegotiate=DENY_FORMAT
invalidBase64=DENY_FORMAT
fakeShape=PASS_TO_GSS
tooLong=DENY_SIZE
reports=PASS_TO_GSS
~~~

**Giải thích:**

- `missing`: nếu endpoint protected, server nên trả 401 challenge.
- `evilHost`: host không thuộc allowlist nội bộ bị từ chối. Trong app thật, host phải là canonical từ trusted ingress; raw `Host`/`X-Forwarded-Host` có thể bị spoof.
- `basic` không phải authentication scheme mà ứng dụng chọn.
- `bareNegotiate` thiếu token và không có separator nên bị `DENY_SCHEME` ở classifier này. `emptyNegotiate` có separator nhưng token rỗng nên `DENY_FORMAT`.
- `invalidBase64` fail syntax; `fakeShape` decode ra bytes của chữ “token”, **không phải Kerberos token**.
- `tooLong` vượt ngưỡng minh họa 64 ký tự; production GSS tokens có thể dài nhiều KB, vì vậy cần limit theo framework/container/threat model, không dùng ngưỡng này.
- `reports` là host allowlisted khác, nhưng chưa chứng minh SPN/keytab ở Reports đúng.

**Không triển khai chương trình này làm Kerberos authentication provider.** Trong production, Spring Security Kerberos/GSS phải verify token cryptographically, negotiated mechanism và service principal trước khi cấp quyền. Một token decode được có thể là fake, NTLM hoặc Kerberos service ticket bị chỉnh sửa.

## 11. SPNEGO vs session, logout và CSRF

### 11.1. HTTP session không phải domain session

Sau lần SPNEGO thành công, Spring Security có thể giữ `Authentication` trong `SecurityContext` và HTTP session. Browser gửi session cookie cho các requests sau mà không nhất thiết lặp lại Kerberos handshake mỗi lần.

- **Logout local ứng dụng** có thể invalidate session/cookie của Portal.
- **TGT/service tickets trong OS cache** có thể vẫn tồn tại: browser có thể SSO lại ngay khi nhận 401 Negotiate.
- **Lock/logout OS user domain** là một lifecycle riêng. Server website không thể tùy ý xóa client-side TGT từ xa.
- Nếu có session timeout hoặc account disabled, ứng dụng phải kiểm authorization/status phù hợp, không tin mãi một cache.
- Nếu ứng dụng dùng stateless auth trên từng request, cần theo dõi overhead, replay/connection context và gateway behavior, không áp giả định session ở mô hình stateful.

### 11.2. Kerberos không tự chống CSRF business form

Browser có thể tự gửi credentials (Negotiate hoặc cookie) khi bị dẫn tới trusted host. Vì vậy một POST thay đổi dữ liệu vẫn có thể chịu **Cross-Site Request Forgery** nếu thiếu kiểm soát. Với ứng dụng Servlet có forms/API browser, giữ CSRF protection, cookie policy và authorization per action. Không tắt CSRF chỉ vì “người dùng đã Kerberos SSO”.

### 11.3. CORS không phải cơ chế cấp quyền

Một SPA khác origin cần CORS/credentials handling hợp lệ, nhưng CORS không kiểm thay SPNEGO/GSS và không cấp quyền server-side. Không mở `Access-Control-Allow-Origin: *` cùng credentials hoặc cấu hình wildcard để né Integrated Auth browser restrictions. Ưu tiên same-origin/BFF/gateway có trust boundary rõ cho browser-based apps.

### 11.4. Session fixation và cookie

Sau xác thực, Spring Security cần áp session fixation strategy/cookie settings, `Secure`, `HttpOnly`, `SameSite`, session idle/absolute timeout theo policy. Kerberos authenticate user, không tự xác thực nội dung một cookie do attacker tự đặt. Đừng chia sẻ session cookie cho mọi subdomains/tenants không liên quan.

## 12. TLS, mutual authentication, channel binding

### 12.1. TLS là yêu cầu riêng

Theo RFC 4559, HTTP Negotiate là cơ chế xác thực, **không bảo vệ tự động toàn bộ HTTP body/headers**. Dùng HTTPS, cert validation, HSTS và secure cookies. SPNEGO GSS token được Base64 chở qua header, không phải mã hóa message HTTP.

### 12.2. Mutual authentication / AP-REP

Kerberos có thể thực hiện mutual authentication: service gửi GSS output token, browser xử lý để xác nhận phía server. Trong HTTP Negotiate, final token có thể xuất hiện trong `WWW-Authenticate` **ngay cả ở response 200**, không phải mọi `WWW-Authenticate` là lỗi.

Reverse proxy/LB phải xử lý continuation/final token theo đúng GSS/context lifetime; không xóa header để “tránh lộ info” khi protocol còn cần nó.

### 12.3. Extended Protection và channel binding

Windows Extended Protection for Authentication có thể yêu cầu TLS channel binding, tránh một số dạng relay. Khi TLS terminate tại gateway còn Kerberos accept ở backend, cấu hình giữa client/proxy/backend có thể không thống nhất gây `GSSException: Channel binding mismatch`. Không sửa bằng cách tắt EPA vô điều kiện; cần đối chiếu kiến trúc TLS termination, SPN, cert, browser/server policy và Java GSS implementation.

## 13. NTLM fallback: Negotiate chưa chắc là Kerberos

RFC 4559 mô tả Negotiate trong Windows có thể hoạt động với SPNEGO bọc **Kerberos hoặc NTLM**. Một website có `Authorization: Negotiate ...` chưa thể nói “Kerberos verified” chỉ từ scheme này.

**Khi xảy ra NTLM fallback?** Có thể do client không lấy được Kerberos service ticket: SPN chưa đăng ký/trùng, dùng IP/alias sai, DNS/KDC lỗi, thời gian lệch, trust thiếu hoặc browser/OS policy lựa mechanism khác. Không tự kết luận nguyên nhân; phải kiểm negotiated mechanism thực tế.

**Hệ quả bảo mật:**
- NTLM có trust/mutual authentication/delegation khác Kerberos và có rủi ro relay trong cấu hình bất lợi.
- Một ứng dụng có yêu cầu **Kerberos-only** phải bảo đảm **server/OS/GSS mechanism selection và domain/browser policy** thực sự từ chối NTLM, không chỉ filter `Authorization` prefix.
- Không bật wildcard trusted hosts hoặc delegation để “chữa” NTLM/401.
- Cần kiểm AD/KDC và accepted mechanism, chứ không chỉ kiểm `klist` có một TGT.

### 13.1. Double-hop và delegation khác SSO một hop

Browser Lan có thể SSO Kerberos tới Portal A; nhưng A gọi Reports B thay Lan là bài toán **delegation**, không tự xảy ra:

~~~text
Browser Lan -- Kerberos HTTP/portal --> Portal A
                                        |
                                        +-- no delegation:
                                        |     A không dùng được user ticket
                                        |     cho HTTP/reports
                                        |
                                        +-- constrained delegation:
                                        |     AD/KDC cho A thay user tới
                                        |     danh sách SPNs được duyệt
                                        |
                                        +-- OAuth2 Token Exchange/OBO:
                                              dùng ủy quyền API theo
                                              audience/scopes riêng
~~~

Ưu tiên **constrained delegation** khi dùng Kerberos backend, không bật unconstrained delegation rộng cho mọi services. Edge có `AuthNegotiateDelegateAllowlist`, Firefox có `Authentication.Delegated`; chúng không thay KDC/server-side delegation policy. Nếu không cần ủy quyền user, hãy dùng service identity với quyền máy rõ hoặc OIDC/OAuth2 flows phù hợp.

## 14. Debug từng bước: từ browser tới KDC và app

~~~text
A. Request protected không có auth:
   Server có trả 401 + WWW-Authenticate: Negotiate?
   |
   +-- Không: entry point, filter chain, gateway/route
   |
   +-- Có: Browser có tự gửi Authorization?
             |
             +-- Không: Edge/Chrome/Firefox trusted host policy,
             |          OS GSS support, TGT, user profile
             |
             +-- Có: KDC đã cấp HTTP/fqdn service ticket?
                       |
                       +-- Không: SPN, DNS, realm trust,
                       |          time skew, KDC connectivity
                       |
                       +-- Có: Header tới được acceptor?
                                  |
                                  +-- Không: proxy stripped Authorization,
                                  |          407 vs 401, routing
                                  |
                                  +-- Có: GSS accept context pass?
                                             |
                                             +-- Không: service keytab, KVNO,
                                             |          enctype, SPN/EPA
                                             |
                                             +-- Có: UserDetails/authorization?
                                                        |
                                                        +-- Không: user disabled,
                                                        |          tenant/roles
                                                        |
                                                        +-- Có: 200 resource
~~~

### 14.1. Lệnh kiểm client/host

~~~bash
# Cần Kerberos credentials, GSS-enabled curl và HTTPS server thật:
curl --negotiate -u : -v https://intranet.example.org/whoami
~~~

`curl --negotiate -u :` chỉ hoạt động khi curl build có GSS/SPNEGO support và OS cache phù hợp. `-v` có thể in Authorization tokens: **chỉ dùng trong sandbox và redact trước khi chia sẻ logs**. Không dùng `-k` tắt TLS validation để làm test pass.

`klist` kiểm ticket cache; `kvno HTTP/intranet.example.org` có thể xin service ticket trong Kerberos environment; `setspn -Q HTTP/intranet.example.org` kiểm AD SPN (theo quyền của admin). Các công cụ có output phụ thuộc môi trường, không có stdout cố định.

### 14.2. Triệu chứng và ý nghĩa

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm |
| --- | --- | --- |
| 401 lần đầu rồi 200 | Challenge-response bình thường | Xem browser request có Negotiate token |
| 401 loop, không có Authorization | Browser chưa gửi credentials | Edge/Firefox policy, OS TGT, hostname |
| 401 loop, đã gửi Authorization | GSS reject hoặc bị strip continuation token | SPN/keytab, KDC, gateway, mechanism |
| 407 từ proxy | Forward proxy authentication | Proxy/PAC và Proxy-Authenticate |
| `KRB5KDC_ERR_S_PRINCIPAL_UNKNOWN` | SPN không có trong KDC | `HTTP/fqdn` registration |
| `KRB_AP_ERR_MODIFIED` | Keytab/service account sai, SPN duplicate | KVNO, key rotation, duplicate SPNs |
| `KRB_AP_ERR_SKEW` | Clock mismatch | NTP client/KDC/server |
| `GSSException: Defective token` | Corrupted/wrong GSS token | Proxy header truncation, mechanism |
| `GSSException: Channel binding mismatch` | EPA/TLS binding không khớp | TLS offload/cert/context |
| Login pass nhưng 403 | Authorization deny hoặc CSRF | Role, account, tenant, CSRF on POST |
| Chỉ Firefox lỗi | Firefox SPNEGO allowlist/policy | `Authentication.SPNEGO` |
| Chỉ Edge lỗi | Edge AuthServerAllowlist/intranet detection | `edge://policy` |
| IP khác FQDN | SPN target mismatch | DNS/FQDN, aliases |
| Qua proxy không chạy | Header, SPN hoặc gateway termination | Authorization passthrough mode |
| Logout app rồi được SSO lại | TGT/ticket cache OS còn | Đúng lifecycle, UX cần rõ |
| Backend “on behalf of” không chạy | Chưa cấu hình delegation | Constrained delegation/OBO |

### 14.3. Logging an toàn

Ghi correlation ID đã sanitize, canonical host/SPN/realm, loại auth scheme, accepted mechanism nếu API expose an toàn, success/error category, internal user/tenant và latency. **Không ghi** raw SPNEGO token, HTTP Authorization, TGT, service ticket, keytab, session cookies, password, GSS trace quá chi tiết hoặc private user attributes. GSS debug logs chỉ dùng trong sandbox.

## 15. Test matrix kỹ thuật và bảo mật

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Happy path Windows domain | TGT, SPN/keytab và browser allowlist đúng | 401→Negotiate→200 |
| Happy path Firefox | SPNEGO policy đúng, OS credential cache | Token được gửi và xác minh |
| No Authorization | GET protected, không session | 401 `WWW-Authenticate: Negotiate` |
| Browser untrusted host | Host không được allowlist | Không silent-send credentials |
| No TGT | Browser không có credentials | 401/fallback theo policy, không fake user |
| Wrong SPN | Browser xin ticket cho alias sai | GSS/KDC fail |
| Wrong keytab/KVNO | Server dùng secret cũ | GSS reject |
| Duplicate SPN | AD có principal conflict | Fail hoặc policy ambiguity, điều tra AD |
| NTLM fallback | KDC/SPN Kerberos lỗi; NTLM client cho phép | Với Kerberos-only: reject |
| Wrong realm | User/realm không được trust | Reject theo policy |
| Initial 401 stripped | Gateway bỏ WWW-Authenticate | Browser không bắt đầu SSO |
| Authorization stripped | Gateway bỏ token | 401 loop, sửa reverse proxy |
| 401 continuation stripped | Proxy bỏ GSS output token | Negotiation không hoàn tất |
| 200 final token stripped | Proxy bỏ final Negotiate token | Mutual context có thể fail |
| 407 from forward proxy | Proxy riêng yêu cầu auth | Xử lý Proxy-Authenticate, không nhầm app |
| Header quá lớn | SPNEGO group-heavy token | Chính sách size hợp lý, không truncation |
| TLS downgrade | HTTP không bảo vệ token | Deny/redirect theo HTTPS/HSTS policy |
| Channel binding mismatch | TLS termination/EPA policy khác | Fail; điều tra không tự disable protection |
| Authenticated but disabled user | GSS pass, user directory disabled | Spring/app deny |
| Cross-tenant resource | Valid principal truy cập tenant khác | 403 |
| POST without CSRF | Browser đã Kerberos authenticated | CSRF filter deny theo policy |
| Local logout | Spring session invalidated, OS TGT còn | Có thể SSO lại; không claim domain logout |
| Multi-node | LB callbacks/keys đúng thiết kế | Accept consistent |
| Double-hop unauthorized | A cố impersonate user tới B | Reject nếu không có delegation rights |
| Delegation wildcard | Browser/domain policy vô tình quá rộng | Security review fail |
| Host header spoofing | Client gửi forged forwarded host | Trusted ingress không truyền thành identity |

### Cách chứng minh Kerberos chứ không chỉ Negotiate

Kiểm server-side **accepted GSS mechanism**, audit/log phù hợp và client ticket cache có `HTTP/fqdn` service ticket. Dù client `klist` có TGT, `Authorization: Negotiate` vẫn không tự chứng minh Kerberos đã dùng. Với test Kerberos-only cần cố ý tạo điều kiện NTLM fallback và xác nhận server từ chối nếu policy yêu cầu.

### Kiểm thử Spring Security riêng

Dùng unit/integration tests kiểm filter/entry point, `UserDetailsService`, account status và `SecurityContext`. Mocks có thể chứng minh 401/authorization wiring, nhưng **không chứng minh cryptographic GSS ticket validation**. Để test thực cần KDC/AD sandbox và keytab test. Không dùng domain admin keytab hoặc live user credentials trong CI.

## 16. Vận hành và hardening

**Service account/keytab:** sử dụng least privilege, read-only secret mount, rotation có KVNO/enctype/certificate/trust đồng bộ, không lưu trong Git/image. Với nhiều nodes, phân phối secret chỉ cho workloads dùng chung approved SPN; không sao chép cho mọi container.

**Browser policy:** quản trị allowlist server names và delegation list riêng; kiểm `edge://policy`, `chrome://policy`, Firefox enterprise configuration; tắt broad wildcard/unknown domains. Đảm bảo HTTPS canonical origin và TLS cert hợp lệ.

**Network:** KDC/AD routing, DNS, NTP client/server, firewall, reverse proxy authentication termination, forwarded headers trust và Authorization passthrough. Đừng tăng header-size limit vô tận mà không cân nhắc DoS; Kerberos tickets có thể dài do PAC/groups, cần giới hạn thực tế.

**Mechanism policy:** nếu sản phẩm yêu cầu Kerberos-only, enforce ở OS/GSS/domain/server và test NTLM negative. Không mặc định `Negotiate=Kerberos`.

**App authorization:** nội bộ phải kiểm user enabled, realm trust, tenant membership, role, resource ownership, CSRF. Một principal từ domain được tin vẫn có thể không được phép dùng ứng dụng.

**UX/fallback:** nếu thiết bị ngoài domain không có ticket, cung cấp form/OIDC fallback khi được phê duyệt, không hạ bảo mật vô thức. Trang giải thích “SSO không khả dụng trên thiết bị này” hữu ích hơn 401 loop.

### Runbook nếu keytab bị lộ

1. Contain affected service/credential, chặn phạm vi sử dụng và tránh tiếp tục phát sinh access.
2. Xác định nodes/secrets stores/backups/logs đã chạm keytab.
3. Phối hợp AD/KDC rotation service account key, cập nhật keytab/KVNO ở toàn bộ service acceptors.
4. Đánh giá tickets/sessions còn hiệu lực và khả năng revoke theo hệ thống Kerberos thực.
5. Rà soát accepted mechanism, browser allowlists và app authorization events.
6. Không gửi keytab/raw tokens trong ticket hỗ trợ; dùng redacted logs/correlation IDs.
7. Regression test wrong keytab/duplicate SPN/NTLM fallback, xác nhận service hoạt động với key mới.

## 17. Bài tập thực hành

**Bài 1 – phân lớp.** Vẽ Kerberos/KDC, GSS-API/SSPI, SPNEGO và HTTP Negotiate. Đặt TGT, TGS-REQ, service ticket, AP-REQ, WWW-Authenticate, Authorization vào đúng chặng.

**Bài 2 – đọc trace.** Giải thích một chuỗi `GET /private → 401 Negotiate → GET Authorization Negotiate → 200`. Nêu khi nào có 401 continuation/200 final token và tại sao proxy không được strip.

**Bài 3 – vai trò browser.** Browser đã domain login, user mở intranet. Nó gửi mật khẩu, TGT hay service ticket? KDC giúp gì? Ai verify token?

**Bài 4 – chính sách Edge.** Viết AuthServerAllowlist hẹp cho intranet host, không bật AuthNegotiateDelegateAllowlist. Giải thích khác nhau giữa authentication và delegation.

**Bài 5 – Firefox.** Viết Authentication.SPNEGO policy cho một host HTTPS và Delegated rỗng. Kiểm khả năng match subdomains theo Mozilla docs; vì sao domain quá rộng nguy hiểm?

**Bài 6 – SPN.** Browser xin ticket `HTTP/intranet.example.org` nhưng keytab chỉ có `HTTP/app01.internal.example.org`. Chỉ ra lỗi và cách sửa SPN/DNS/proxy/keytab đúng, không bypass GSS validation.

**Bài 7 – Java 17.** Chạy `NegotiateHeaderDemo.java`, đối chiếu 9 dòng stdout. Giải thích tại sao `fakeShape=PASS_TO_GSS` không có nghĩa “đã login”.

**Bài 8 – Spring Boot.** Trong KDC sandbox, chạy project mục 9 với SPN/keytab test. Quan sát 401/Authorization/200, sau đó thử user disabled/roles không đủ.

**Bài 9 – NTLM.** Với `Authorization: Negotiate`, mô tả cách kiểm mechanism thật và tại sao chỉ nhìn prefix không chứng minh Kerberos-only.

**Bài 10 – channel binding.** Nếu thay proxy TLS gây GSS channel-binding mismatch, bạn phải kiểm những lớp nào trước khi thay policy?

**Bài 11 – CSRF/logout.** Tại sao user logout local xong có thể được SSO lại mà không nhập password? Tại sao một POST thay đổi dữ liệu vẫn cần CSRF protection?

**Bài 12 – double-hop.** Portal A đã Kerberos login, cần gọi API B thay user. Nêu điều kiện constrained delegation hoặc OAuth2 OBO; giải thích vì sao một service ticket cho A không tự được gửi tới B.

**Tiêu chí đạt:** Người học trình bày đúng chuỗi **OS/KDC ticket cache → browser SSPI/GSS token → SPNEGO/HTTP 401/Authorization → SPN/keytab GSS accept → Spring Authentication → application authorization** và phân biệt hoàn toàn **Negotiate vs Kerberos, SSO vs delegation, authentication vs authorization**.

## 18. Nguồn chính thức

- RFC 4559 – HTTP Negotiate/SPNEGO, 401 challenge, Authorization, multi-step/final response: https://www.rfc-editor.org/rfc/rfc4559
- RFC 4178 – The Simple and Protected GSS-API Negotiation Mechanism: https://www.rfc-editor.org/rfc/rfc4178
- RFC 4120 – Kerberos Network Authentication Service v5: https://www.rfc-editor.org/rfc/rfc4120
- RFC 4121 – Kerberos GSS-API mechanism: https://www.rfc-editor.org/rfc/rfc4121
- Spring Security Kerberos 2.2.0 – Introduction và tested versions: https://docs.spring.io/spring-security-kerberos/reference/introduction.html
- Spring Security Kerberos – Spring and Spring Security Kerberos: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security Kerberos – SpnegoEntryPoint: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html
- Spring Security Kerberos – SpnegoAuthenticationProcessingFilter: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Microsoft Edge AuthServerAllowlist: https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authserverallowlist
- Microsoft Edge AuthNegotiateDelegateAllowlist: https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authnegotiatedelegateallowlist
- Firefox Enterprise Authentication/SPNEGO policy: https://firefox-admin-docs.mozilla.org/reference/policies/authentication/
- Oracle Java – JAAS/Kerberos JGSS: https://docs.oracle.com/en/java/javase/26/security/part-i--secure-authentication-using-java-authentication-authorization-service-jaas.html
- Microsoft Learn – Kerberos double-hop với Microsoft Edge: https://learn.microsoft.com/en-us/troubleshoot/developer/webapps/iis/www-authentication-authorization/kerberos-double-hop-authentication-edge-chromium
