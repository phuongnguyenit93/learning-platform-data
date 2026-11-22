# Phân biệt Kerberos SSO với LDAP bind và đăng nhập bằng mật khẩu Active Directory

**Kerberos SSO, LDAP bind và đăng nhập bằng mật khẩu Active Directory (AD) có thể cùng sử dụng một hệ thống danh tính doanh nghiệp, nhưng không phải cùng một cơ chế xác thực.** Trong Kerberos SSO qua **HTTP SPNEGO**, browser/OS gửi **bằng chứng dạng Kerberos service ticket** đến ứng dụng; ứng dụng sử dụng **service principal và keytab** để xác minh ticket, thường **không cần nhận mật khẩu** của người dùng. Trong **LDAP simple bind** để xác thực form login, ứng dụng **nhận username/password** và chuyển thông tin đăng nhập đó qua một kết nối LDAP có **TLS được kiểm chứng** tới directory để thử bind. “Đăng nhập bằng mật khẩu AD” chỉ mô tả **nguồn và loại credential**, không chỉ rõ giao thức: có thể xác minh qua LDAP bind, qua Kerberos AS exchange hoặc qua một hệ thống liên kết như OIDC/SAML.

**Ngoại lệ cần nhớ:** LDAP còn hỗ trợ **SASL**, trong đó **SASL/GSSAPI dùng Kerberos** để xác thực đến LDAP server. Do đó khẳng định “LDAP luôn gửi password, Kerberos không bao giờ đi cùng LDAP” là sai. Phải xác định **đường HTTP browser→app** và **đường app/client→directory** đang dùng cơ chế nào, ai thấy mật khẩu, ai kiểm vé và ứng dụng lấy quyền ở đâu.

Bài thuộc **Spring Security – federation → Kerberos và SPNEGO**, trình bày cách phân biệt ở mức giao thức, ranh giới tin cậy, các lựa chọn tích hợp với Spring Security/Spring LDAP/Active Directory, mô hình hybrid, bảo mật LDAPS và Kerberos, ví dụ Java 17 chạy được, ma trận kiểm thử và runbook cho môi trường doanh nghiệp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Kerberos SSO thường không hỏi lại mật khẩu trên ứng dụng web.
2. Mô tả đúng chức năng của **TGT**, **service ticket**, **KDC**, **SPN**, **keytab**, **SPNEGO** và **HTTP Negotiate**.
3. Giải thích **LDAP simple bind** bằng username/password, khác với **LDAP SASL/GSSAPI bind**.
4. Nhận ra **đăng nhập với mật khẩu AD** không đồng nghĩa với tự động SSO.
5. Phân biệt **xác thực danh tính** với **tra cứu group/department**, **tạo local account** và **phân quyền ứng dụng**.
6. Chọn đúng Spring Security provider cho từng luồng, không trộn password provider với ticket validator.
7. Bảo vệ simple bind bằng TLS, tránh rò password và hiểu LDAP signing/channel binding theo cơ chế.
8. Hiểu điều kiện Kerberos SSO (realm, trust, SPN, đồng hồ, keytab, browser policy).
9. Viết kiểm thử tích hợp có thể chứng minh **đang dùng đúng cơ chế**, thay vì chỉ kiểm HTTP 200.
10. Thiết kế đường chuyển đổi từ login bằng mật khẩu AD sang SSO mà không vô tình tạo cơ chế fallback yếu hơn.

## 2. Ba tên gọi, ba lớp ý nghĩa

| Cụm từ | Bản chất | Bằng chứng gửi đến app/server | App web có thấy mật khẩu? |
| --- | --- | --- | --- |
| **Kerberos SSO qua SPNEGO/HTTP Negotiate** | Đăng nhập dùng vé đã được hệ điều hành/KDC cấp | SPNEGO token chứa/đại diện Kerberos AP-REQ cho HTTP service | Thông thường **không** |
| **LDAP simple bind** | Thử xác thực vào LDAP directory với bind identity và password | DN/UPN và password đưa đến directory qua LDAP | **Có** nếu form login đến app |
| **AD password login** | Tên nghiệp vụ: người dùng cung cấp mật khẩu tài khoản AD | Tùy implementation: LDAP bind, Kerberos password-based AS, OIDC/SAML redirect... | Tùy implementation; form trực tiếp thường **có** |
| **LDAP SASL/GSSAPI bind** | LDAP authentication dùng Kerberos qua SASL | GSSAPI/Kerberos exchange cho LDAP service | Không nhất thiết; có thể dùng ticket |
| **OIDC/SAML federation với AD làm nguồn identity** | Ứng dụng nhận token/assertion từ IdP/OP | ID Token hoặc SAML Assertion | Có thể **không** nếu redirect sang IdP |

**Quy tắc:** “chúng tôi dùng AD” không phải câu trả lời cho câu hỏi bảo mật. Cần biết **frontend truyền thứ gì**, **backend xác minh bằng cách nào**, **password đi qua đâu**, **session và quyền được quản lý ở đâu**.

## 3. Sơ đồ so sánh đặt cạnh nhau

**Kerberos SSO qua HTTP SPNEGO:**

~~~text
Windows/Linux user session
         |
         | User already has TGT from KDC after desktop sign-in
         v
Browser -> GET /secure       -> Spring SPNEGO service
Browser <- 401 Negotiate     <- Spring SPNEGO service
         |
         | OS acquires service ticket for HTTP/portal.example.test
         v
Browser -> Authorization: Negotiate ... -> Spring service
                                             |
                                       JAAS/GSS accept context
                                       SPN + service keytab
                                             |
                                       Kerberos principal verified
                                             |
                                       Local account and roles
~~~

**LDAP simple bind từ form đăng nhập:**

~~~text
Browser -- HTTPS POST username/password --> Spring login endpoint
                                                |
                                         LDAP authentication provider
                                                |
                                  TLS LDAPS/STARTTLS to AD/LDAP server
                                                |
                                  Simple bind as user + password
                                                |
                                        Bind success/failure
                                                |
                                      Local account/roles
~~~

**LDAP SASL/GSSAPI từ một LDAP client có Kerberos credentials:**

~~~text
LDAP client / application with Kerberos credentials
                         |
                 SASL GSSAPI bind to ldap/host SPN
                         |
                    Directory Server
                         |
             Authentication via Kerberos context
                         |
                   LDAP operations as authorized
~~~

**Nhìn sơ đồ:** SPNEGO HTTP xác thực **request web tại service HTTP**; LDAP SASL/GSSAPI xác thực **phiên LDAP tại directory**. Cùng sử dụng Kerberos nhưng **khác service principal, đường giao thức và trust boundary**.

## 4. Kerberos: vai trò của KDC, realm và service principal

Kerberos V5 dùng **Key Distribution Center (KDC)** để cấp tickets trong một realm. Trong môi trường AD, Domain Controller thường cung cấp KDC và LDAP services. Các đối tượng:

- **Client principal:** danh tính người dùng, ví dụ `alice@CORP.EXAMPLE.TEST`.
- **Realm:** namespace Kerberos, ví dụ `CORP.EXAMPLE.TEST`.
- **TGT (Ticket-Granting Ticket):** được dùng để xin service tickets mà không đưa mật khẩu user cho từng ứng dụng.
- **TGS (Ticket-Granting Service):** thành phần KDC cấp ticket cho dịch vụ đích.
- **Service principal name (SPN):** ví dụ `HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST`.
- **Service ticket:** bằng chứng để client truy cập một service cụ thể.
- **Acceptor secret/keytab:** service dùng để giải mã/xác minh ticket (thường qua JAAS/GSS).
- **Authenticator/replay protection:** chứng minh freshness; xử lý sai đồng hồ/replay theo Kerberos policy.
- **Trust/referral giữa realms:** cần thiết khi client và service ở các realms khác nhau.

**Không đồng nhất:** cùng `sub`/username ở hai realms không mặc định cùng user; một ticket cho HTTP portal không tự được chấp nhận ở LDAP directory hoặc service HTTP khác.

## 5. HTTP SPNEGO: trình tự chính xác hơn

1. Người dùng đã đăng nhập OS hoặc có credential cache chứa TGT hợp lệ.
2. Browser truy cập endpoint được bảo vệ.
3. Server yêu cầu authentication bằng `401 WWW-Authenticate: Negotiate`.
4. Browser/OS gọi GSSAPI/SSPI, thường tìm ticket cho `HTTP/hostname`.
5. Nếu chưa có service ticket, OS gửi TGS request cho KDC để lấy.
6. Browser gửi `Authorization: Negotiate <base64-token>`.
7. Service dùng Kerberos acceptor credentials (thường service keytab) để nhận GSS context.
8. Service xác minh ticket/Authenticator, SPN, thời hạn, replay và điều kiện protocol.
9. Spring Security tạo `Authentication` cho Kerberos principal đã xác minh.
10. Application map principal tới local account/groups/roles và kiểm requested resource.
11. Browser có thể nhận session cookie sau login; các HTTP requests sau thường được xử lý theo session strategy của app.

**Lưu ý:** `Negotiate` là một negotiation scheme; có thể xảy ra **NTLM fallback** trong một số môi trường Windows. **Chỉ thấy header `Negotiate` hoặc trang trả 200 không chứng minh đã dùng Kerberos**. Phải kiểm negotiated mechanism/ticket service principal trong môi trường test.

## 6. Vì sao đây được gọi là Single Sign-On?

Người dùng **không phải nhập lại mật khẩu vào từng ứng dụng** vì OS/Kerberos credential cache có TGT; browser có thể xin service ticket mới cho đúng SPN từ KDC. Một lần desktop authentication có thể hỗ trợ truy cập nhiều Kerberos-enabled services trong trust scope đã được cấu hình.

Điều này **không có nghĩa**:
- User không cần đăng nhập OS bao giờ.
- TGT/service tickets không bao giờ hết hạn.
- Browser nào cũng tự làm SPNEGO; browser policy và thiết bị phải hỗ trợ.
- User ở ngoài domain/realm trust luôn có SSO.
- Kerberos chỉ cần hostname, không cần SPN/keytab/clock đúng.
- Có Kerberos authentication là tự có `ROLE_ADMIN` trong Spring.
- Một lần logout ứng dụng sẽ tự thu hồi toàn bộ TGT, Kerberos credentials trên các thiết bị.
- Kerberos desktop SSO đồng nghĩa OIDC/SAML SSO cho browser internet.

**SSO là trải nghiệm không nhập lại mật khẩu trong một trust environment**, không phải quyền truy cập không điều kiện.

## 7. LDAP là gì và vì sao có thể dùng để xác thực?

**LDAP (Lightweight Directory Access Protocol)** là giao thức truy cập dịch vụ thư mục. Nó hỗ trợ:
- Bind/authentication vào directory.
- Search user objects và attributes.
- Read memberships/organizational information (trong phạm vi ACL).
- Các operation khác như compare, add, modify, delete nếu được phép.

**Active Directory Domain Services** có thể cung cấp LDAP directory và Kerberos KDC cùng lúc. Hai endpoints này **không đồng nhất giao thức**.

Một application dùng LDAP có thể:
1. Search tìm Distinguished Name (DN) của user bằng service bind identity đã giới hạn quyền.
2. Thử bind dưới danh tính user với password người dùng vừa nhập.
3. Nếu bind thành công, coi password đã được directory xác minh.
4. Lấy attributes/groups và map sang authorities của app.

**Điểm quan trọng từ Spring Security:** LDAP bind authentication không đọc lại password từ directory để so sánh ở ứng dụng; **directory tự xác minh password khi bind**. Vì vậy cấu hình LDAP bind không đơn giản là một `UserDetailsService` lấy password hash về so sánh.

## 8. LDAP simple bind: identity và password được gửi thế nào?

LDAP simple bind có thể dùng:
- **DN:** `CN=Alice Nguyen,OU=People,DC=corp,DC=example,DC=test`.
- **Tên dạng UPN trong AD:** `alice@corp.example.test` nếu DC/AD setup hỗ trợ.
- Một số name forms khác tùy directory implementation.

Bản chất simple bind: **directory nhận bind identity và password** rồi phản hồi success/failure. Bản thân LDAP simple bind **không có mã hóa password ở lớp LDAP**, vì vậy phải bảo vệ bằng **TLS** để không lộ credentials trên network.

~~~text
POST https://portal.example.test/login
  username = alice@corp.example.test
  password = ********
       |
       v
Spring AuthenticationManager
       |
       v
LdapAuthenticationProvider / AD-specific provider
       |
       v
LDAPS 636 / STARTTLS 389 with verified TLS certificate
       |
       v
LDAP bind as Alice using provided password
       |
       +--- Success -> verified password, map attributes/roles
       |
       +--- Failure -> bad credentials / account policy / LDAP error
~~~

**Những vị trí password có thể xuất hiện:** browser form, reverse proxy/WAF (nếu log sai), app memory, Authentication request, LDAP client library và directory. Tuyệt đối không log/metric/tracing raw password.

## 9. Password login với Active Directory có phải LDAP bind không?

**Không bắt buộc.** Câu “ứng dụng kiểm tra mật khẩu AD” có thể chỉ một trong nhiều kiến trúc:

| Kiểu triển khai | Ai nhận password? | Đường kiểm |
| --- | --- | --- |
| App có form login, dùng LDAP bind | Browser → app → AD LDAP | Directory kiểm password qua bind |
| App có form login, provider Kerberos với password | Browser → app → Kerberos KDC | KDC/AS exchange từ credential, không HTTP SPNEGO SSO |
| App redirect tới corporate OIDC/SAML IdP | Browser → IdP (nếu nhập) | App nhận token/assertion, thường không thấy password |
| OS integrated Kerberos HTTP SPNEGO | OS/browser không post password đến app | Service kiểm Kerberos ticket |
| Legacy custom AD integration | Tùy cách làm | Phải inspect thực tế, không suy đoán |

Một đội có thể gọi mọi phương thức “AD login” vì AD quản lý tài khoản. **Tên UX/marketing không cho biết password exposure hoặc cryptographic trust**. Cần phân tích request path và AuthenticationProvider thực tế.

## 10. LDAP bind không mặc định là SSO

Nếu người dùng phải nhập password vào form ở từng ứng dụng Spring, thì dù mỗi ứng dụng xác minh về **cùng AD**, đó vẫn là **đăng nhập lại bằng mật khẩu**. Các session cookie riêng có thể giúp user không nhập lại trong từng app sau login, nhưng **không tự là Kerberos SSO xuyên ứng dụng**.

**Để có web SSO đúng nghĩa**, có thể dùng:
- HTTP SPNEGO/Kerberos với desktop credential cache/realm trust.
- Redirect tới central IdP dùng **OIDC hoặc SAML**, nơi app không giữ mật khẩu.
- Một SSO gateway được cấu hình cẩn thận, truyền verified identity qua protocol/trust boundary.

**LDAP là directory protocol**; nó thường phục vụ identity lookup/group attributes **bên cạnh** Kerberos/OIDC/SAML, không tự cung cấp browser SSO chỉ vì kết nối đến cùng AD.

## 11. LDAP SASL/GSSAPI: một ngoại lệ quan trọng

LDAP hỗ trợ cả **simple bind** và **SASL bind**. Với **SASL/GSSAPI**, LDAP client và server có thể dùng Kerberos credentials/tickets để thiết lập authenticated LDAP session.

~~~text
LDAP client (có Kerberos credentials/TGT)
    |
    | SASL mechanism GSSAPI
    v
LDAP server service principal (ldap/dc.example.test)
    |
    | Validate Kerberos context
    v
Authenticated LDAP session
    |
    +--> Search/group lookup theo quyền của security context
~~~

Một số trường hợp client là ứng dụng web tự xác thực với directory bằng service identity; trường hợp khác có delegated user credentials được kiểm soát. **Không tự suy rằng app có LDAP SASL/GSSAPI nghĩa là browser đã đăng nhập Spring bằng Kerberos**. Cần xem **ai là Kerberos initiator**, principal nào được dùng để bind LDAP, và có thực hiện delegation hay không.

**NTLM SASL** cũng có thể tồn tại trong AD, nhưng không được đồng nhất với GSSAPI Kerberos. Trong chính sách hiện đại, nên tránh phụ thuộc vào NTLM relay-prone và yêu cầu signing/channel binding phù hợp. <https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing>

## 12. LDAP bind vs LDAP search: hai nhiệm vụ khác nhau

Một LDAP integration có thể:
- **Bind để xác thực** username/password user.
- **Bind bằng service account (read-only)** để search user/group attributes.
- **SASL bind** bằng Kerberos identity để LDAP search.
- **Bind với user credentials** rồi lấy attributes trong quyền user.

Nếu ứng dụng chỉ **search được user** bằng service account, đó **không chứng minh user đã được xác thực**. Ngược lại, SPNEGO Kerberos có thể xác thực user nhưng vẫn cần **directory search** để tìm nhóm, manager hoặc thuộc tính business.

~~~text
Kerberos SPNEGO verified principal
             |
             v
Search AD via protected LDAP with service credentials
             |
             v
Resolve directory object and memberOf/group memberships
             |
             v
Map approved groups -> app GrantedAuthority
~~~

Không dùng bind/search result `displayName` hoặc email làm primary identity key. Với AD, có thể dùng objectGUID hoặc stable directory identifier trong link do IAM phê duyệt, kết hợp source namespace/realm. User account linking cần chính sách rõ; tên hiển thị và UPN có thể thay đổi.

## 13. Bảng tổng hợp sâu: Kerberos SPNEGO vs LDAP simple bind

| Tiêu chí | Kerberos HTTP SSO/SPNEGO | LDAP simple bind với form AD |
| --- | --- | --- |
| Browser gửi lên app | Negotiate token / service ticket | Username + password |
| App nhận password của user | Thường không | Có |
| Backend kiểm | Keytab/GSS acceptor, Kerberos AP exchange | Directory LDAP bind success/failure |
| Nguồn identity | Kerberos realm/KDC, principal | Directory bind identity + attributes |
| Cần SPN cho HTTP service | Có | Không bắt buộc |
| Cần HTTP service keytab | Thường có hoặc managed credential tương đương | Không, nếu chỉ LDAP simple bind |
| Cần kết nối directory lúc mỗi login | Không nhất thiết cho Kerberos AP verify; có thể cần group lookup | Thường có ở bind |
| Cần KDC | Có để cấp ticket (có thể cache tickets) | Không cần Kerberos riêng cho simple bind |
| Có thể dùng ở thiết bị ngoài domain | Phức tạp hơn, phụ thuộc trust/client config | Có nếu app và LDAPS kết nối được |
| Password exposure tại app | Thấp hơn nếu SSO đúng | Cao hơn vì app xử lý password |
| Clock skew/SPN/KVNO | Quan trọng | Không áp cho bản thân simple bind |
| LDAP TLS/cert | Không bắt buộc cho AP verification; cần nếu app dùng LDAP lookup | **Bắt buộc trên đường truyền bí mật** |
| Nhóm/quyền Spring | Vẫn phải map | Vẫn phải map |
| Rủi ro chính | Ticket misuse, SPN/keytab, fallback, relay/delegation, replay | Password exposure, insecure LDAP, brute force, credential stuffing |
| Failure thường thấy | 401 Negotiate loop, GSSException, KRB_AP_ERR_SKEW/MODIFIED | LDAP invalidCredentials (49 AD), TLS/LDAP errors |
| Session logout | Không tự purge OS TGT | Không tự đổi password hoặc hủy session app khác |

**Đừng xếp hạng “một bên luôn an toàn tuyệt đối hơn”**: Kerberos phụ thuộc quản trị SPN/keytab và browser/OS; LDAP password login có thể được bảo vệ bằng TLS/MFA/rate limits và chính sách rõ. Với mục tiêu corporate seamless login, Kerberos SPNEGO giúp app **không thu thập lại mật khẩu người dùng**, là một lợi thế bảo mật rõ ràng khi triển khai đúng.

## 14. Spring Security: những module nào dùng cho mỗi nhánh?

**Kerberos HTTP SPNEGO** trong hệ Spring thường dùng **Spring Security Kerberos extension**, không tự bật chỉ từ `spring-boot-starter-security`:

- `SpnegoAuthenticationProcessingFilter`: đọc header `Authorization: Negotiate`.
- `SpnegoEntryPoint`: phát challenge `WWW-Authenticate: Negotiate`.
- `KerberosServiceAuthenticationProvider`: nhận token/service ticket qua ticket validator.
- `SunJaasKerberosTicketValidator`: cấu hình service principal + keytab để JAAS/GSS verify.
- `UserDetailsService` hoặc domain mapping: load local account và authorities.

**LDAP/AD password login** thường dùng:
- `spring-security-ldap` dependency.
- `LdapAuthenticationProvider` + `BindAuthenticator` hoặc AD-specific `ActiveDirectoryLdapAuthenticationProvider`.
- `AuthenticationManager`/form login để đọc user credentials.
- `LdapAuthoritiesPopulator` hoặc approved mapping để lấy groups và authorities.

**Chung:** SecurityFilterChain, Authentication, SecurityContext, session management, auditing và method/resource authorization.

**Khác:** **Kerberos ticket validation** không phải `BindAuthenticator`; **LDAP bind** không phải `SpnegoAuthenticationProcessingFilter`.

## 15. ActiveDirectoryLdapAuthenticationProvider xác thực bằng gì?

Spring Security LDAP cung cấp provider dành riêng cho Active Directory: `ActiveDirectoryLdapAuthenticationProvider`. Khi người dùng nhập username/password, provider tương tác LDAP/AD để xác minh credentials, rồi có thể tìm các thuộc tính/roles theo cấu hình. Nó **không tạo HTTP SPNEGO** và **không tự cung cấp Kerberos ticket cho browser**.

Ví dụ fragment Java trong Spring Boot 3/Spring Security 6.x hoặc release tương thích:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.ldap.authentication.ad.ActiveDirectoryLdapAuthenticationProvider;

@Configuration
class ActiveDirectoryPasswordLoginConfig {

    @Bean
    ActiveDirectoryLdapAuthenticationProvider activeDirectoryProvider() {
        ActiveDirectoryLdapAuthenticationProvider provider =
                new ActiveDirectoryLdapAuthenticationProvider(
                    "corp.example.test",
                    "ldaps://dc1.corp.example.test:636/"
                );
        provider.setConvertSubErrorCodesToExceptions(true);
        return provider;
    }
}
~~~

**Đây là fragment project-level**: cần `spring-security-ldap`, TLS truststore có CA của AD DC, network access, SecurityFilterChain/form login và appropriate authorities mapping. **Không chạy trực tiếp với javac/JDK thuần**.

**Không dùng** `ldap://...:389` với simple bind không có STARTTLS. Nếu LDAP server bắt TLS certificate sai, phải sửa truststore/name/certificate chain, **không tắt hostname verification** hay dùng trust-all SSL context.

**Lưu ý:** AD `data 52e/775/532/533` sub-error codes có thể giúp phân loại lỗi, nhưng không trả hết chi tiết cho browser, tránh username enumeration và lộ policy.

## 16. Spring Security LDAP: bind authenticator khác password comparison

Với LDAP thông thường, có các chiến lược khác nhau:

**Bind authentication:**
- App lấy username/password user từ Authentication request.
- Tìm user DN hoặc dùng name form được directory chấp nhận.
- Thử bind với chính password đó.
- Directory quyết định accept/reject.
- Không cần/không nên lấy user password hash về app.

**Password comparison authentication:**
- Dùng LDAP compare operation để so với giá trị thuộc tính password theo directory contract.
- Không phải mọi AD deployment cung cấp semantics phù hợp cho cách này.
- Không suy rằng đọc được `unicodePwd`/password hash của AD để so local.

Spring docs xác nhận `LdapAuthenticationProvider` có `LdapAuthenticator` implementations như `BindAuthenticator` và `PasswordComparisonAuthenticator`. Với AD password form login, **dùng provider phù hợp AD** hoặc BindAuthenticator theo schema thực tế; không tự lấy password hash từ LDAP rồi so trong Java.

## 17. Ví dụ Spring BindAuthenticator cho directory không phải AD-specific

Fragment mô tả ý tưởng (imports và bean context phải theo Spring LDAP version):

~~~java
// Code fragment trong Spring @Configuration, không tự chạy.
DefaultSpringSecurityContextSource contextSource =
    new DefaultSpringSecurityContextSource(
        "ldaps://directory.example.test:636/dc=example,dc=test");

BindAuthenticator bindAuthenticator =
    new BindAuthenticator(contextSource);

bindAuthenticator.setUserDnPatterns(
    new String[] { "uid={0},ou=people" });

LdapAuthenticationProvider provider =
    new LdapAuthenticationProvider(bindAuthenticator);
~~~

**Giới hạn:** DN pattern chỉ phù hợp với directory schema đã biết; trong AD, UPN thường thuận tiện hơn và user có thể nằm ở nhiều OUs. Nếu phải search DN, cần giới hạn scope/filters, escape input, service bind account read-only và chống LDAP filter injection.

**Đây không phải lựa chọn thay thế Kerberos web SSO**, và vẫn cần TLS + password handling controls.

## 18. Spring Kerberos extension: phần service ticket validator

Fragment Java điển hình trong ứng dụng Spring:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
class KerberosSsoConfig {

    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
                "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST");
        validator.setKeyTabLocation(
                new FileSystemResource("/run/secrets/portal.keytab"));
        validator.setDebug(false);
        return validator;
    }

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
}
~~~

**Quan trọng:** fragment này cần Spring Security Kerberos extension và phải thêm `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, AuthenticationManager/SecurityFilterChain, proper fallback policy. **Không tự động cấu thành một full SSO application** chỉ vì đã tạo beans.

**Giá trị cấu hình phải thuộc trust environment thật:** HTTP SPN theo browser URL, service account, realm, KDC trust, keytab permissions và supported enctypes. Không lưu keytab trong Git/container image công khai.

## 19. Có KerberosAuthenticationProvider dùng mật khẩu là SSO không?

Trong extension Kerberos, có các APIs phục vụ Kerberos authentication từ **username/password** (ví dụ `KerberosAuthenticationProvider` kết hợp `KerberosClient`) và APIs phục vụ **service ticket** từ SPNEGO (`KerberosServiceAuthenticationProvider`).

Phân biệt:

| Component/flow | User input chính | App thấy password? | Tính chất |
| --- | --- | --- | --- |
| KerberosAuthenticationProvider với form credentials | Username/password | **Có** | App xác minh credentials bằng KDC; không phải seamless SPNEGO SSO |
| KerberosServiceAuthenticationProvider từ HTTP Negotiate | Kerberos service ticket token | Thông thường **không** | Kerberos HTTP SSO |
| ActiveDirectoryLdapAuthenticationProvider | Username/password | **Có** | LDAP/AD bind password login |
| LDAP SASL/GSSAPI bind | Kerberos SASL tokens | Tùy credential acquisition, không nhất thiết | Directory session authentication |
| OIDC/SAML login với AD-backed IdP | Redirect/callback token/assertion | Có thể không | Federation SSO theo IdP |

**“Xác thực bằng Kerberos” không tự đồng nghĩa “browser không gửi mật khẩu”.** Phải đọc đúng component và flow.

## 20. Secure LDAP: LDAPS, STARTTLS và xác minh TLS

**Simple bind chỉ an toàn khi đường truyền được bảo vệ đúng**. Hai mô hình phổ biến:
- **LDAPS:** TLS ngay khi mở kết nối, thường cổng 636.
- **LDAP + STARTTLS:** kết nối thường trên cổng 389 rồi **nâng cấp TLS trước khi bind**.

Bảo vệ thực tế cần:
1. CA/truststore đúng, certificate chain hợp lệ.
2. Hostname/DC name match certificate; không dùng trust-all.
3. TLS versions/ciphers theo policy.
4. Không downgrade thành plaintext LDAP nếu TLS lỗi.
5. Kết nối app–DC qua network/egress control.
6. Không ghi password ở gateway, proxy, app logs/APM.
7. Timeout và rate limits để tránh connection exhaustion.
8. Account lockout/brute-force detection theo AD policies.
9. DNS/DC failover được quản lý để không connect sai domain.
10. Secret lifecycle cho service search-bind identity.

**LDAP signing không thay thế TLS cho simple bind**. Microsoft giải thích LDAP signing áp dụng trên SASL sessions không có TLS, còn simple bind phải dùng TLS để bảo vệ credentials. Xem: https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing

## 21. LDAP signing và channel binding: đừng đánh đồng

Các khái niệm:

| Biện pháp | Bảo vệ | Áp dụng chính |
| --- | --- | --- |
| **TLS (LDAPS/STARTTLS)** | Bảo mật và toàn vẹn traffic, xác minh server theo PKI | Simple bind và SASL kết nối qua TLS |
| **LDAP signing** | Toàn vẹn/xác thực LDAP messages (không tự mã hóa data) | SASL binds không có TLS |
| **SASL sealing** | Confidentiality + integrity ở SASL layer | SASL không TLS nếu mechanism hỗ trợ |
| **LDAP Channel Binding Token (CBT)** | Ràng buộc SASL authentication với TLS channel | **TLS + SASL** theo AD policy |
| **Kerberos service binding** | Bằng chứng gắn với service principal và trust/keys | Kerberos authentication/GSS |
| **HTTP TLS** | Bảo vệ browser↔app và cookies | Cả SPNEGO và form login |

**Không nói “bật LDAP signing là password simple bind an toàn trên 389 không TLS”.** Simple bind không hưởng signing theo cách SASL. Với LDAP over TLS dùng SASL/GSSAPI, AD channel-binding policy có thể yêu cầu CBT; **CBT không áp dụng cho simple bind** theo Microsoft.

Các defaults khác nhau theo Windows Server version và policy. **Không suy đoán current AD DC đang enforce gì chỉ từ version OS**; xác nhận configuration và audit events. https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding

## 22. Khi nào dùng password AD và khi nào ưu tiên SSO?

| Tình huống | Lựa chọn phù hợp | Điểm cần đánh giá |
| --- | --- | --- |
| Portal intranet, domain-joined Windows, managed browser | HTTP SPNEGO/Kerberos | SPN/keytab, realm trust, browser policy, NTLM fallback |
| SaaS nhiều thiết bị, mobile, ngoại mạng | OIDC/SAML với corporate IdP | IdP policy/MFA, issuer/audience, tenant mapping |
| Legacy app chỉ hỗ trợ username/password | AD/LDAP bind qua TLS, kế hoạch hiện đại hóa | Password handling, phishing, lockout, TLS, MFA |
| Machine process đọc directory | LDAP SASL/GSSAPI với service principal hoặc protected service bind | Credential management, least privilege |
| Ứng dụng chỉ cần group/profile data sau SPNEGO | LDAP search qua service credential được bảo vệ | Không hỏi lại user password |
| Hybrid app hỗ trợ hai hình thức | SPNEGO cho managed clients, IdP redirect hoặc password flow nếu được policy phê duyệt | Downgrade/fallback, assurance, session collision |
| User ngoài realm trust | Federation với IdP là lựa chọn phổ biến | Không tự nới Kerberos trust/accept-any-realm |

**Không coi password AD là mục tiêu cuối** nếu app có yêu cầu phishing resistance/MFA, federation, device posture hoặc quyền nội bộ theo session. Đôi khi OIDC/SAML IdP đứng trước AD/Kerberos tạo ra trải nghiệm SSO tốt hơn cho các trình duyệt đa nền tảng.

## 23. Cách thiết kế hybrid mà không tạo lỗ hổng fallback

Một app có thể có:
- `/login/kerberos` hoặc protected intranet path sử dụng HTTP Negotiate.
- `/oauth2/authorization/corp` cho OIDC redirect.
- `/login/password` chỉ nếu business/policy vẫn cần form AD.
- `/api/**` chỉ nhận OAuth2 access token đúng audience.

**Các điều kiện:**
1. Không cho Kerberos ticket validation fail rồi **âm thầm** coi header `X-User` là authenticated.
2. Không cho người dùng “chọn password fallback” để vượt chính sách **MFA/assurance/conditional access** mà route khác yêu cầu.
3. Xác định methods được phép cho từng user/tenant/action, không chỉ lựa chọn UI.
4. Sessions phải biết authentication method và assurance, không tự nâng đặc quyền.
5. Nếu principal đã login theo một method, switching method phải kiểm session fixation/identity change.
6. Mỗi provider có audit category độc lập: Kerberos, AD LDAP, OIDC/SAML.
7. Group mapping/authorization không phụ thuộc kiểu credential là ticket hay password.
8. Có account disable/revocation strategy cho local sessions và API tokens.
9. Login errors không lộ user existence/password status chi tiết cho attacker.
10. Test browser logout rồi Kerberos auto-login lại: đó có thể là **SSO expected behavior**, không phải session logout thất bại.

**Một hệ nhiều providers phải nói rõ precedence và fallback policy.** Không đăng ký một authentication provider lỏng để hợp thức hóa yêu cầu mà provider mạnh từ chối.

## 24. AD account state, lockout và đổi mật khẩu

**LDAP simple bind** có thể thất bại vì:
- Password sai.
- User không tồn tại hoặc sai bind DN/UPN.
- Account disabled/locked/expired.
- User phải đổi password hoặc password đã hết hạn.
- AD DC/LDP policy/TLS/certificate không đáp ứng.
- Network/DC outage, anonymous/search service credentials lỗi.

**Kerberos SSO** có thể thất bại vì:
- Không có TGT/service ticket.
- Client realm/KDC hoặc cross-realm trust sai.
- HTTP SPN đăng ký nhầm account.
- Keytab có sai principal/KVNO/enctype/key material.
- Client/KDC/service lệch đồng hồ.
- Ticket hết hạn, replay hoặc crypto policy mismatch.
- Browser không gửi Negotiate token do allowlist/zone/policy.
- Reverse proxy strip Authorization header.

**Không nhầm phản hồi của LDAP password bind với Kerberos AP-REQ**. Cùng một account AD bị disabled có thể ảnh hưởng khác nhau khi đã có **ticket/session được cấp trước lúc disable**; ứng dụng cần session/token revocation và account active guard theo SLA.

## 25. Tác động khi password AD thay đổi

Khi user đổi mật khẩu:
- Một **form LDAP bind mới** với password cũ sẽ thường bị từ chối theo DC/account replication policy.
- Một **Kerberos TGT** được cấp trước đó có thể còn hiệu lực cho đến khi hết hạn/revocation logic; app session đã tạo cũng có thể tồn tại.
- Password của **service account** đổi có thể làm **keytab/KVNO mismatch** và ảnh hưởng SPNEGO dù user password không đổi.
- Nếu app ghi nhớ password để tự bind lại, đó là **anti-pattern**; không lưu reusable user password trong database/session.
- Nếu business cần sign-out ngay sau password reset/disable, phải có **explicit session revocation/authorization state check**, không kỳ vọng password change tự destroy mọi tickets.

**Ba credential khác nhau:** user password, user TGT/service tickets, service keytab. Rotation/revocation của từng cái có scope và timing riêng.

## 26. LDAP filter injection khi tìm user trước bind

Một số apps dùng bind service account để search DN theo username rồi bind với user password. Nếu tự ghép LDAP filter:

~~~java
// Anti-pattern minh họa: không dùng trong production.
String filter = "(uid=" + rawUsernameFromRequest + ")";
~~~

Attacker có thể chèn ký tự như `*`, `(`, `)`, `\`, NULL để làm lệch filter tùy LDAP API. Dùng API có escaping/parameterized filters của Spring LDAP, giới hạn base DN/search scope và object classes, không cho client chọn arbitrary LDAP URL.

**Không đồng nhất LDAP injection với SQL injection**; LDAP filter escaping có quy tắc riêng theo RFC 4515.

**Không để search-result-first dẫn tới user confusion:** nếu filter trả nhiều accounts, dừng thay vì bind nhầm; kiểm exact directory identity và source tenant. Nếu không cần search vì AD cho bind theo UPN, tránh query phức tạp không cần thiết.

## 27. LDAP group retrieval và granted authorities

Một ứng dụng cần phân quyền:

~~~text
AD user verified:
  alice@corp.example.test

Directory groups:
  CN=Finance_Readers,OU=Groups,...
  CN=Shared_Service,OU=Groups,...

App-owned policy:
  (AD source, Finance_Readers, tenant=north)
      -> ROLE_INVOICE_VIEWER

Unknown group:
  CN=Global_Admins,OU=Groups,...
      -> No automatic app admin
~~~

Đối với Kerberos SSO, app có thể dùng LDAP lookup để lấy groups **sau khi đã xác thực principal**. Đối với LDAP password bind, provider có thể dùng LDAP authorities populator. **Cả hai vẫn cần chính sách mapping có kiểm soát**.

Lưu ý:
- `memberOf` có thể không biểu diễn đủ mọi nested/primary group semantics trong AD.
- Group displayName/opaque ID không tự xác nhận quyền cross-tenant.
- Authenticated user còn phải có local account active, tenant membership và object-level authorization.
- Authorities đã được cache trong Spring SecurityContext có thể stale sau khi group bị rút.
- Không map thẳng mọi group giống `ROLE_ADMIN` thành quyền toàn hệ thống.
- Không tự link directory identities khác domain/realm chỉ bằng email.

## 28. Mật khẩu và Kerberos ticket: ranh giới rủi ro

**Nếu app nhận user password từ form AD:**
- Password có thể bị lộ nếu app/server/proxy, access logs, APM, heap dumps hoặc TLS termination bị xâm phạm.
- App trở thành điểm thu thập reusable credentials có thể dùng tại nhiều hệ thống nếu AD password reused.
- Phải chống brute force, credential stuffing, login enumeration, CSRF/session fixation và xác thực chính sách MFA.
- Không log password, không gửi password qua HTTP plaintext, không lưu lại sau login.

**Nếu app chỉ nhận Kerberos SPNEGO ticket:**
- App không cần có plaintext reusable user password.
- Service keytab là secret có giá trị cao: phải bảo vệ, rotate, phân quyền.
- Ticket/AP-REQ replay, SPN substitution, credential delegation/forwarding, clock skew và NTLM fallback cần kiểm soát.
- Không cho arbitrary service principal hoặc keytab fallback; kiểm GSS acceptor.
- TLS vẫn cần để bảo vệ HTTP/session/response và hạn chế nhiều lớp tấn công.
- Logout app không mặc định xóa Kerberos credentials ở OS.

**Không gọi một cơ chế là “passwordless tuyệt đối”** chỉ vì application web không nhận password: người dùng có thể đã đăng nhập OS với password hoặc smart card để có TGT.

## 29. Demo Java 17 độc lập: mô hình chứng cứ xác thực

Chương trình sau **không giao tiếp AD/KDC/LDAP và không verify Kerberos ticket hoặc password thật**. Nó chỉ minh họa **quyết định dựa trên kết quả đã được provider tin cậy xác minh**, làm rõ ba loại chứng cứ:

- Web SPNEGO yêu cầu **HTTP service ticket thật được GSS accept**, đúng SPN.
- Form LDAP simple bind yêu cầu **TLS tới directory được xác minh**, app nhận user credentials, **bind đã thành công**.
- LDAP SASL/GSSAPI xác thực **phiên LDAP**; nó **không tự chứng minh browser đã hoàn tất HTTP SPNEGO**.

**Các boolean trong demo do test harness giả lập**, không được lấy từ request headers để tạo Authentication trong production.

Tạo file **KerberosVsLdapLoginDemo.java**:

~~~java
import java.util.Set;

public class KerberosVsLdapLoginDemo {

    enum Mechanism {
        HTTP_SPNEGO, LDAP_PASSWORD_BIND, LDAP_SASL_GSSAPI
    }

    record Evidence(
        Mechanism mechanism,
        String identity,
        boolean serviceTicketVerified,
        boolean httpServicePrincipalMatched,
        boolean appReceivedPassword,
        boolean tlsVerified,
        boolean ldapBindSucceeded,
        boolean accountActive,
        boolean tenantAllowed) {}

    static final String TRUSTED_SPN =
        "HTTP/portal.corp.example.test@CORP.EXAMPLE.TEST";

    static final Set<String> APPROVED_IDENTITIES = Set.of(
        "alice@CORP.EXAMPLE.TEST",
        "bob@CORP.EXAMPLE.TEST"
    );

    static String decide(Evidence e) {
        if (!APPROVED_IDENTITIES.contains(e.identity())) {
            return "DENY_UNMAPPED_IDENTITY";
        }

        switch (e.mechanism()) {
            case HTTP_SPNEGO -> {
                if (e.appReceivedPassword()) {
                    return "DENY_UNEXPECTED_PASSWORD";
                }
                if (!e.serviceTicketVerified()) {
                    return "DENY_NO_VALID_HTTP_TICKET";
                }
                if (!e.httpServicePrincipalMatched()) {
                    return "DENY_WRONG_SERVICE_PRINCIPAL";
                }
            }
            case LDAP_PASSWORD_BIND -> {
                if (!e.tlsVerified()) {
                    return "DENY_LDAP_NO_TLS";
                }
                if (!e.appReceivedPassword()) {
                    return "DENY_MISSING_PASSWORD";
                }
                if (!e.ldapBindSucceeded()) {
                    return "DENY_BAD_AD_CREDENTIALS";
                }
            }
            case LDAP_SASL_GSSAPI -> {
                // LDAP bind authentication != HTTP browser SSO.
                if (!e.serviceTicketVerified()
                    || !e.ldapBindSucceeded()) {
                    return "DENY_LDAP_GSSAPI";
                }
                return "LDAP_SESSION_ONLY_NOT_HTTP_SSO";
            }
        }

        if (!e.accountActive()) {
            return "DENY_DISABLED_LOCAL_ACCOUNT";
        }
        if (!e.tenantAllowed()) {
            return "DENY_TENANT";
        }
        return "ALLOW_" + e.mechanism().name();
    }

    static Evidence sample(
        Mechanism mechanism, boolean ticket,
        boolean spn, boolean password, boolean tls,
        boolean bind, boolean active, boolean tenant) {
        return new Evidence(
            mechanism, "alice@CORP.EXAMPLE.TEST",
            ticket, spn, password, tls, bind, active, tenant
        );
    }

    public static void main(String[] args) {
        Evidence kerberos = sample(
            Mechanism.HTTP_SPNEGO,
            true, true, false, true, false, true, true);

        Evidence ldap = sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, true, true, true, true);

        System.out.println("SPNEGO with ticket: " + decide(kerberos));
        System.out.println("LDAP password bind: " + decide(ldap));

        System.out.println("No ticket: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            false, true, false, true, false, true, true)));

        System.out.println("Wrong SPN: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            true, false, false, true, false, true, true)));

        System.out.println("Password sent to SPNEGO: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            true, true, true, true, false, true, true)));

        System.out.println("LDAP without TLS: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, false, true, true, true)));

        System.out.println("LDAP invalid password: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, true, false, true, true)));

        System.out.println("LDAP no password: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, false, true, false, true, true)));

        System.out.println("LDAP SASL GSSAPI: " + decide(sample(
            Mechanism.LDAP_SASL_GSSAPI,
            true, false, false, true, true, true, true)));

        System.out.println("Disabled account: " + decide(sample(
            Mechanism.HTTP_SPNEGO,
            true, true, false, true, false, false, true)));

        System.out.println("Wrong tenant: " + decide(sample(
            Mechanism.LDAP_PASSWORD_BIND,
            false, false, true, true, true, true, false)));
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac KerberosVsLdapLoginDemo.java
java KerberosVsLdapLoginDemo
~~~

**Stdout chính xác:**

~~~text
SPNEGO with ticket: ALLOW_HTTP_SPNEGO
LDAP password bind: ALLOW_LDAP_PASSWORD_BIND
No ticket: DENY_NO_VALID_HTTP_TICKET
Wrong SPN: DENY_WRONG_SERVICE_PRINCIPAL
Password sent to SPNEGO: DENY_UNEXPECTED_PASSWORD
LDAP without TLS: DENY_LDAP_NO_TLS
LDAP invalid password: DENY_BAD_AD_CREDENTIALS
LDAP no password: DENY_MISSING_PASSWORD
LDAP SASL GSSAPI: LDAP_SESSION_ONLY_NOT_HTTP_SSO
Disabled account: DENY_DISABLED_LOCAL_ACCOUNT
Wrong tenant: DENY_TENANT
~~~

**Giải thích:**
- SPNEGO chỉ ALLOW nếu bộ xác minh ticket đã chứng thực ticket đúng SPN và app không nhận password trong flow này.
- LDAP form login cần TLS và bind success; nó không dùng HTTP service ticket.
- LDAP SASL/GSSAPI có thể dùng Kerberos nhưng bằng chứng đó thuộc **LDAP session**, không nên tự biến thành Spring browser Authentication.
- Sau proof, app vẫn kiểm local account/tenant (trong demo, riêng SASL LDAP được phân loại là LDAP session, không cho web login).
- Các biến `serviceTicketVerified`, `ldapBindSucceeded`, `tlsVerified` **chỉ là mô phỏng**, không được chấp nhận từ client-supplied request.

**Giới hạn:** Demo không xử lý JAAS/GSS, HTTP Negotiate, LDAP StartTLS, password hashing, directory ACLs, signing/channel binding, session protection hoặc DC account policies. **Không dùng làm production AuthenticationProvider**.

## 30. Tổ chức Spring SecurityFilterChain để không trộn phương thức

Một application có browser login, Kerberos SSO và resource APIs cần có trust rõ:

~~~text
/secure/intranet/**    -> SPNEGO/Kerberos filter + trusted GSS acceptor
/login/password        -> AD LDAP password login (chỉ nếu policy cho phép)
/oauth2/**             -> OIDC client/redirect login
/api/**                -> OAuth2 Resource Server access-token validation
/directory/**          -> Protected directory operations (service identity)
~~~

**Sơ đồ này là ý tưởng**, không phải URLs Spring mặc định cho từng filter. Cần cấu hình `SecurityFilterChain` và matcher/ordering theo app. Với multiple chains, test route nào thuộc chain nào, tránh fall-through sang một chain permissive.

**Chống downgrade:**
- Nếu một endpoint yêu cầu Kerberos hoặc MFA assurance, LDAP password fallback **không tự đủ** nếu thiếu yếu tố bảo đảm.
- Không cho anonymous Basic/Auth header thay Kerberos ticket.
- Không cấp authority theo raw LDAP displayName hoặc Kerberos realm string.
- Không truyền raw AD password từ backend tới nhiều microservices để authenticate lại.
- Với browser có Spring session, security context phải phân biệt authentication method, thời hạn và principal changes.

## 31. Vòng đời phiên và logout khác nhau

**Sau Kerberos SSO:**
- App có thể tạo HTTP session cookie riêng sau GSS authentication.
- Logout ứng dụng hủy local session/cookie nhưng **không tự xóa TGT** khỏi OS credential cache.
- Browser mở lại endpoint có thể **tự đăng nhập** qua Kerberos, đúng theo SSO policy.
- Nếu user bị disabled hoặc group bị thu hồi, session cũ có thể chưa cập nhật ngay; cần application policy.

**Sau LDAP password form login:**
- App cũng có thể tạo HTTP session.
- Logout app chỉ hủy session đó; không đổi/thu hồi password AD.
- Password AD đổi không tự terminate mọi local app sessions trừ khi có revocation integration.
- Không giữ raw password trong session/remember-me token; remember-me nếu dùng phải có policy, encryption/revocation phù hợp.

**Sau OIDC/SAML federation:** có cơ chế logout/token/session semantics khác nữa. Không giả single logout xuyên Kerberos, LDAP, OIDC, SAML chỉ vì backend cùng dùng AD.

## 32. SSO với Active Directory có cần LDAP không?

**Không nhất thiết.** HTTP SPNEGO acceptor có thể xác minh ticket bằng service keytab và không cần LDAP bind trong chính bước AP verification. Tuy nhiên ứng dụng có thể chọn:
- Tra group membership từ AD bằng LDAP sau login.
- Tra local account/provisioning registry (SCIM hoặc DB).
- Dùng local policy để quyết định tenant/resource access.
- Kiểm user status gần realtime nếu security SLA yêu cầu.

**Kết luận:** “Dùng AD để đăng nhập” có thể gồm **Kerberos authentication + LDAP authorization data lookup**, hoặc **LDAP password authentication + local authorization**. Hai dạng này khác nhau về password handling và trust boundaries, dù kết quả cuối cùng đều là Spring Authentication.

## 33. So sánh lỗi chẩn đoán

| Triệu chứng | Kerberos/SPNEGO nghi ngờ | LDAP/AD password nghi ngờ |
| --- | --- | --- |
| Browser không gửi Negotiate | Browser zone/policy, OS tickets, trusted URLs | Không liên quan nếu form login |
| 401 lặp sau Negotiate | Wrong SPN/keytab/KVNO/realm/clock, provider wiring | Không tự suy LDAP bad password |
| KRB_AP_ERR_SKEW | Clock skew client/service/KDC | Không phải simple bind |
| KRB_AP_ERR_MODIFIED | Keytab/SPN/key integrity | Không phải LDAP invalidCredentials |
| LDAP resultCode 49 | Không phải Kerberos AP success/fail | Bad credentials/account state/AD subcodes |
| LDAP strongAuthRequired (8) | Không phải GSS Kerberos lỗi password | LDAP signing/TLS policy mismatch |
| TLS PKIX/cert path error | Chỉ nếu component dùng TLS LDAP/HTTPS | LDAPS truststore/hostname/CA |
| Login thành công nhưng 403 | Local role/tenant policy | Local role/tenant policy |
| User disabled nhưng session vẫn truy cập | Stale local auth/session, ticket lifecycle | Stale local auth/session |
| NTLM fallback | Mechanism negotiation/policy | SASL NTLM cũng có policy riêng |
| AD DC outage | KDC ticket issuance có thể fail; cached tickets có thể còn | LDAP bind mới thường fail |
| Browser password popup | SPNEGO policy/realm/NTLM negotiation | Password form vốn yêu cầu password |

**Cùng HTTP 401/403 không chứng minh cùng nguyên nhân**. Định vị trước: browser→app, app→KDC, app→directory hay application authorization.

## 34. Kiểm thử kỹ thuật: Kerberos SPNEGO happy path

**Môi trường test có domain/KDC và service keytab riêng:**

1. Đăng nhập Windows/Linux client vào test realm, có TGT hợp lệ.
2. Mở browser được phép dùng integrated authentication cho test portal.
3. Gọi protected endpoint, quan sát `401 WWW-Authenticate: Negotiate` ở bước challenge.
4. Xác minh browser gửi `Authorization: Negotiate`, không có form password.
5. Xem OS ticket cache: service ticket cho `HTTP/portal.corp.example.test`.
6. Spring Kerberos ticket validator accept, log cơ chế chính xác và principal đã được pseudonymized.
7. User mapping và tenant/roles đúng.
8. Test disabled local account, wrong tenant, missing group → deny.
9. Test wrong service principal/keytab, expired ticket, clock skew → fail closed.
10. Browser logout rồi truy cập lại: có thể SSO lại nếu TGT vẫn còn; ghi đúng expected behavior.

**Không coi Chrome/Edge/Firefox luôn có policy giống nhau**, cũng không coi một request có session cookie từ lần login trước là chứng minh SPNEGO đang hoạt động.

## 35. Kiểm thử kỹ thuật: LDAP password bind

**Lab với test DC/AD và LDAPS trusted certificate:**

1. Người dùng vào form login qua HTTPS.
2. App submit username/password đến `ActiveDirectoryLdapAuthenticationProvider` hoặc BindAuthenticator đã cấu hình.
3. Provider kết nối đến đúng LDAP server qua TLS certificate hợp lệ.
4. Bind đúng username/password → Authentication success.
5. Password sai → authentication denied, không tạo user session.
6. Account disabled/locked/expired → denial theo AD policy.
7. TLS certificate sai/expired → fail closed, không fallback plaintext.
8. Thử LDAP signing policy và CBT theo đúng loại simple/SASL bind.
9. Test injection strings trong username; search filter an toàn.
10. Kiểm app logs/APM không có raw credentials.
11. Chặn brute-force/rate limits và kiểm lockout AD policy.
12. Sau bind success, local account/tenant permissions vẫn được kiểm.

**Dùng test password giả được quản lý**, không lưu actual AD passwords của nhân viên trong fixtures hoặc gửi HAR có credentials lên tickets.

## 36. Kiểm thử SASL/GSSAPI LDAP khác gì?

Nếu product hoặc integration layer dùng LDAP SASL/GSSAPI:
1. Xác định **LDAP client principal** thực sự là service hay delegated user.
2. Kiểm lấy Kerberos credentials/TGT đúng realm và SPN cho LDAP service.
3. Bật SASL mechanism GSSAPI và yêu cầu signing/sealing/TLS theo security policy.
4. Nếu dùng LDAP over TLS và AD CBT enforce, kiểm channel binding support.
5. Xác minh LDAP bind thành công cho **đúng LDAP session principal**.
6. Kiểm directory ACL chỉ cho phép đọc dữ liệu cần thiết.
7. Xác nhận **không tự tạo HTTP browser Authentication** chỉ vì backend LDAP SASL bind success.
8. Với Kerberos constrained delegation, kiểm chính sách delegation chặt, không xuất tickets tùy tiện.

**Một service LDAP GSSAPI bind thành công chứng minh service có credentials để gọi directory, không chứng minh người dùng browser nào đã được xác minh.** Nếu cần user delegation, đó là một luồng xác thực/ủy quyền riêng và phải audit.

## 37. Ma trận kiểm thử tổng hợp

| # | Ca thử | Kết quả mong đợi |
| --- | --- | --- |
| 01 | HTTP SPNEGO có valid ticket, đúng SPN/keytab | Spring tạo đúng verified principal |
| 02 | HTTP SPNEGO không có service ticket | 401 challenge/deny |
| 03 | HTTP Negotiate nhưng thực tế NTLM fallback | Không đánh dấu là Kerberos pass |
| 04 | SPNEGO sai service principal | Fail closed |
| 05 | SPNEGO keytab KVNO cũ | Decrypt/accept fail nếu key không có |
| 06 | Kerberos client/KDC/service lệch giờ vượt limit | Authentication fail |
| 07 | Kerberos ticket expired | Reject |
| 08 | Kerberos token replay | Replay policy reject |
| 09 | Wrong realm without trust | Không tạo user authentication |
| 10 | Cross-realm trust hợp lệ | Giữ verified realm, kiểm app authorization |
| 11 | Same username ở hai realms | Không auto-link |
| 12 | Browser không được phép dùng Negotiate | Không giả user từ header |
| 13 | SPNEGO success nhưng account disabled | Deny |
| 14 | SPNEGO success nhưng tenant mismatch | 403 |
| 15 | SPNEGO success nhưng thiếu role | 403 |
| 16 | LDAP simple bind đúng password trên TLS | Authentication success |
| 17 | LDAP simple bind sai password | Deny |
| 18 | LDAP simple bind không TLS | Không thực hiện/insecure path bị từ chối |
| 19 | LDAPS certificate không được tin | Fail closed |
| 20 | LDAP hostname mismatch | Fail closed |
| 21 | STARTTLS upgrade fail | Không gửi password plaintext |
| 22 | Account AD bị locked/disabled | Bind/access denial đúng |
| 23 | Password expired / must change | Phân loại chính xác, không leak subcode |
| 24 | LDAP search filter chứa ký tự injection | Escape/bound search, không bypass |
| 25 | LDAP search trả nhiều users | Không chọn user ngẫu nhiên để bind |
| 26 | LDAP group tên ROLE_ADMIN | Không auto cấp admin |
| 27 | LDAP group removed, Spring session cũ | Revocation/online guard theo SLA |
| 28 | LDAP SASL/GSSAPI bind thành công | Chỉ chứng minh LDAP session |
| 29 | LDAP SASL/GSSAPI có wrong service principal | Fail bind |
| 30 | TLS + SASL khi CBT bắt buộc mà thiếu CBT | Reject theo AD policy |
| 31 | LDAP signing non-TLS SASL không được bật theo policy | Reject theo AD policy |
| 32 | Plain LDAP simple bind 389 khi DC yêu cầu secure bind | Reject |
| 33 | Kerberos form password provider | App có password; không ghi nhận seamless SPNEGO |
| 34 | Kerberos service-ticket provider | App không cần nhận password user |
| 35 | Portal dùng OIDC IdP backed by AD | App nhận token, không tự gắn là LDAP/SPNEGO |
| 36 | Proxy strip Negotiate Authorization header | Detect proxy issue, không fallback X-User |
| 37 | Wrong LDAP DC/domain URL | Không authenticate nhầm directory |
| 38 | Directory outage khi password login | New bind fail/controlled availability |
| 39 | KDC outage với OS cached ticket | Hành vi tùy ticket/service; không auto-login sai |
| 40 | Password changed nhưng app session cũ | Session revocation theo policy |
| 41 | Kerberos service keytab password rotated | Check KVNO/pod rollout |
| 42 | Local user mapping bằng substring trước @ | Security test fail với duplicate realms |
| 43 | OIDC token dùng như HTTP Negotiate ticket | Reject wrong protocol |
| 44 | LDAP password post tới API không phải login | Không nhận/không log credentials |
| 45 | Group membership thuộc tenant A, request tenant B | 403 |
| 46 | User có valid Kerberos ticket nhưng no local account | Fail closed/JIT theo policy |
| 47 | Browser logout rồi SSO tự hoạt động lại | Expected if TGT still valid |
| 48 | LDAP simple bind passwords vô tình bị log | Security QA fail |
| 49 | Credential downgrade sang form bỏ qua MFA policy | Reject |
| 50 | Service account bind có quyền write quá rộng | Least-privilege QA fail |

**PASS không chỉ là HTTP 200/302**: phải có bằng chứng đang dùng **đúng authentication mechanism**, đúng principal/source, đúng account/tenant và không để lộ password/service secret.

## 38. Mô hình lỗi và cách chẩn đoán

**Khi SPNEGO không đăng nhập được:**
1. Có `WWW-Authenticate: Negotiate` không?
2. Browser có thực sự gửi Negotiate token? Cơ chế Kerberos hay NTLM?
3. TGT và service ticket còn hạn? Kiểm OS ticket cache nếu được phép.
4. SPN có khớp browser hostname sau canonicalization không?
5. KDC realm/trust đúng không?
6. Keytab đúng service account/principal/KVNO/enctype/key material?
7. Client/KDC/service clocks đồng bộ?
8. Proxy có chuyển Authorization header đầy đủ?
9. Spring provider/entrypoint/filter đúng SecurityFilterChain?
10. Kerberos đã pass nhưng `UserDetailsService`/tenant policy từ chối?

**Khi LDAP password login thất bại:**
1. Browser form gửi đến đúng HTTPS endpoint?
2. Username/UPN/DN tìm đúng entry? LDAP filter có escape?
3. App kết nối đúng AD/DC/LDAPS hostname?
4. TLS certificate chain/hostname/truststore OK?
5. AD simple bind có bị signing/TLS policy chặn?
6. Password đúng, account disabled/locked/expired?
7. LDAP bind/result code là gì?
8. Service search account còn quyền tối thiểu cần thiết?
9. LDAP provider có bị gọi qua wrong AuthenticationManager không?
10. Bind pass nhưng app account/roles/tenant deny?

**Không dùng một runbook để “sửa chung” cả hai:** reset service keytab không chữa password sai; tăng clock skew không chữa LDAP TLS; nới user search filter không chữa Kerberos SPN.

## 39. Mô hình logging và observability

Những metrics gợi ý do app/infra tự instrument, **không phải Spring Security tự cung cấp tất cả**:

| Metric | Mục tiêu |
| --- | --- |
| `authentication_kerberos_spnego_total` | Requests được kiểm Kerberos |
| `authentication_ldap_simple_bind_total` | Password LDAP bind attempts |
| `authentication_ldap_sasl_gssapi_total` | Directory GSSAPI binds |
| `authentication_unexpected_ntlm_fallback_total` | NTLM use trái policy |
| `authentication_kerberos_ticket_error_total` | Ticket/SPN/realm/KVNO errors |
| `authentication_ldap_tls_failure_total` | TLS/certificate/hostname errors |
| `authentication_ldap_invalid_credentials_total` | Invalid bind credentials |
| `authentication_directory_unavailable_total` | AD/LDAP failures |
| `authentication_account_disabled_total` | Local user status |
| `authentication_tenant_denied_total` | Membership/resource denial |
| `authentication_mfa_downgrade_blocked_total` | Attempt bypass assurance |
| `authentication_credential_exposure_incident_total` | Password/ticket/keytab accidentally logged |

**Audit event nên lưu** timestamp, auth mechanism, trusted realm/directory ID, pseudonymized principal/local account, tenant, policy version, success/failure category, correlation ID. **Không log** raw password, LDAP bind request secret, Authorization: Negotiate header, Kerberos ticket, keytab content hoặc session cookie.

**Không cho email, raw UPN, password error message có PII, token value làm metric label không kiểm soát.**

## 40. Runbook chuyển từ AD password form sang SSO

1. **Inventory**: những apps nào hiện nhận AD password qua LDAP, apps nào đã Kerberos/OIDC/SAML, directory DCs, tenants, role mapping.
2. **Measure**: xác nhận LDAP binds có TLS/hostname verification và audit no password logs.
3. **Choose**: intranet managed clients có thể dùng Kerberos SPNEGO; internet/mobile thường hợp OIDC/SAML IdP.
4. **Register**: SPN/keytab, realm trust, browser Negotiate policy nếu chọn Kerberos.
5. **Map identity**: verified Kerberos principal/issuer+subject → local account, không dựa vào email-only.
6. **Decouple groups**: LDAP chỉ là directory attributes source, không tự cấp roles.
7. **Set assurance**: quy định các endpoints yêu cầu MFA, device posture hoặc step-up.
8. **Configure**: tách routes/providers, giảm fallback password nếu không cần.
9. **Canary**: nhóm user, browsers, VPN/network và devices; signed logs/metrics đã redact.
10. **Test negative**: wrong SPN, wrong realm, LDAP plaintext, password logs, downgrade, account disabled, tenant mismatch.
11. **Cut over**: giảm dần thu thập password trực tiếp ở app, giữ emergency flow chỉ khi security review cho phép.
12. **Observe**: số login success theo method, NTLM fallback, 401 loops, 403 permission issues.
13. **Revoke**: session/token/cookie handling phù hợp khi user disabled/mover/leaver.
14. **Rollback safely**: không mở plaintext LDAP, không chấp nhận mọi Kerberos realm và không bypass MFA.

**Mục tiêu chuyển đổi:** giảm password exposure và tập trung chính sách xác thực, **không** giảm chất lượng application authorization.

## 41. Câu hỏi tự đánh giá

**1. Kerberos SSO có gửi password AD trực tiếp đến Spring web app không?**  
Thông thường không. Browser/OS gửi Kerberos SPNEGO ticket cho HTTP service; app cần xác minh ticket.

**2. LDAP simple bind có gửi user password tới directory không?**  
Có. Nếu form login, app cũng nhận password; phải dùng TLS bảo vệ directory connection.

**3. LDAP bind có bao giờ dùng Kerberos không?**  
Có. LDAP SASL/GSSAPI có thể dùng Kerberos để authenticate LDAP session.

**4. LDAP SASL/GSSAPI bind thành công có chứng minh browser đã HTTP SPNEGO login không?**  
Không tự động. Chúng là hai security contexts và service principals khác nhau.

**5. Mọi AD password login đều là LDAP simple bind?**  
Không. Có thể dùng Kerberos password-based flow hoặc identity federation.

**6. Vì sao cần service HTTP keytab cho Kerberos SPNEGO?**  
Service acceptor cần key material để giải mã/xác minh service ticket theo SPN.

**7. Vì sao Spring LDAP bind không đơn giản dùng UserDetailsService lấy password hash?**  
Directory xác minh password lúc bind; Spring không cần lấy password hash của AD về app.

**8. LDAPS có giống LDAP signing không?**  
Không. LDAPS/TLS cung cấp confidentiality/integrity; signing là message integrity chủ yếu cho non-TLS SASL sessions.

**9. LDAP channel binding token áp vào simple bind qua TLS không?**  
Không theo AD CBT policy; CBT áp cho TLS+SASL sessions.

**10. Browser nhận 401 Negotiate ban đầu có nghĩa authentication thất bại không?**  
Không, có thể là challenge bình thường.

**11. Kerberos principal có cùng local username ở hai realms có phải cùng account không?**  
Không. Giữ namespace nguồn và linking proof.

**12. Spring app Kerberos SSO có thể LDAP-search groups không?**  
Có. LDAP search chỉ để lấy thuộc tính/quyền theo policy, không phải bước thay thế ticket validation.

**13. User đổi AD password có tự logout mọi app Kerberos/LDAP không?**  
Không nhất thiết; tickets và application sessions đã phát có lifecycle riêng.

**14. Nếu LDAP TLS certificate sai, nên tắt verification cho login pass không?**  
Không. Phải sửa server cert/truststore/hostname.

**15. Kerberos ticket hợp lệ tự cấp quyền admin trong Spring không?**  
Không. Application phải map approved authorities và kiểm tenant/resource.

## 42. Checklist production

- [ ] Phân biệt rõ Web Kerberos SPNEGO, LDAP simple bind, LDAP SASL/GSSAPI và AD password login.
- [ ] Chứng minh HTTP Negotiate thực tế dùng Kerberos, không nhầm NTLM fallback.
- [ ] Kerberos SPN/realm/KDC/keytab/clock và browser policy đã kiểm.
- [ ] Keytab được bảo vệ như secret, rotation và pod consistency có owner.
- [ ] LDAP simple bind chỉ trên LDAPS/STARTTLS có TLS certificate/hostname validation.
- [ ] Không fallback plaintext LDAP khi TLS lỗi.
- [ ] LDAP signing, sealing, CBT áp đúng cho SASL hoặc TLS theo policy.
- [ ] AD password được xử lý tối thiểu trong app; không lưu, log hoặc forward bừa bãi.
- [ ] LDAP filter search được escape và scope giới hạn.
- [ ] Service search-bind account có least privilege.
- [ ] Spring Security dùng đúng provider/filter/entrypoint cho từng route.
- [ ] Spring Security Kerberos extension được cài khi cần SPNEGO; không giả starter-security là đủ.
- [ ] Spring LDAP provider được chọn đúng directory/AD schema và configuration.
- [ ] Không coi LDAP directory lookup success là user authentication success.
- [ ] Không coi Kerberos AuthenticationProvider password flow là seamless browser SSO.
- [ ] Group/GrantedAuthority mapping qua approved allowlist, theo issuer/realm/tenant.
- [ ] User account active và local tenant/resource authorization được kiểm.
- [ ] Có policy downgrade/MFA/assurance cho hybrid login methods.
- [ ] Password reset/account disable có session/ticket revocation SLA phù hợp.
- [ ] Có test Kerberos ticket/SPN/realm/clock/keytab và LDAP password/TLS/lockout.
- [ ] Có test LDAP SASL/GSSAPI không bị hiểu nhầm thành HTTP browser login.
- [ ] Có audit/metrics phân biệt source và không lộ secrets/PII.
- [ ] Có canary và rollback không hạ credential transport/ticket validation.

## 43. Kết luận

**Kerberos HTTP SPNEGO SSO dùng vé Kerberos đã được cấp từ OS/KDC; LDAP simple bind xác minh username/password do ứng dụng gửi đến directory; “đăng nhập bằng mật khẩu AD” là tên nghiệp vụ có thể triển khai bằng nhiều protocol.** LDAP SASL/GSSAPI là một trường hợp đặc biệt dùng Kerberos trong LDAP, **không tự biến LDAP session thành web SSO session**.

Trong Spring Security, hãy dùng **Spring Security Kerberos extension** với SPNEGO filter/entrypoint và service-ticket validator cho HTTP Negotiate; dùng **Spring Security LDAP/ActiveDirectoryLdapAuthenticationProvider** cho form password bind khi cần, với LDAPS/STARTTLS đáng tin và kiểm soát password nghiêm ngặt. Khi authentication thành công, **cả hai đều phải map external identity tới local account và thực hiện authorization theo roles/tenant/resource**.

**Quy tắc thiết kế:** đừng suy ra cơ chế từ tên “AD login”; hãy kiểm xem **ai nhận password, ai phát và xác minh ticket, giao thức nào bảo vệ đường truyền, và chính sách nào quyết định quyền**. Đây là cơ sở để chọn SSO phù hợp, giảm rủi ro credential exposure và không trộn LDAP directory lookup với chứng cứ authentication.

### Tài liệu tham khảo chính thức

- Spring Security — LDAP Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
- Spring Security — LdapAuthenticationProvider Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/LdapAuthenticationProvider.html
- Spring Security — ActiveDirectoryLdapAuthenticationProvider Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/ldap/authentication/ad/ActiveDirectoryLdapAuthenticationProvider.html
- Spring Security Kerberos — SPNEGO/Negotiate, KerberosAuthenticationProvider và KerberosServiceAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Microsoft Learn — LDAP Signing Overview for Active Directory: https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-signing
- Microsoft Learn — LDAP Channel Binding for AD DS: https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/ldap-channel-binding
- Microsoft Learn — Enable LDAP signing and reject insecure simple binds: https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/enable-ldap-signing-in-windows-server
- MIT Kerberos — Kerberos concepts and admin documentation: https://web.mit.edu/kerberos/krb5-current/doc/
- RFC 4120 — The Kerberos Network Authentication Service (V5): https://www.rfc-editor.org/rfc/rfc4120
- RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication: https://www.rfc-editor.org/rfc/rfc4559
- RFC 4511 — LDAPv3 Protocol, Bind and Operations: https://www.rfc-editor.org/rfc/rfc4511
- RFC 4513 — LDAP Authentication Methods and Security Mechanisms: https://www.rfc-editor.org/rfc/rfc4513
- RFC 4752 — The Kerberos V5 (GSSAPI) SASL Mechanism: https://www.rfc-editor.org/rfc/rfc4752
- RFC 4515 — LDAP String Representation of Search Filters: https://www.rfc-editor.org/rfc/rfc4515
