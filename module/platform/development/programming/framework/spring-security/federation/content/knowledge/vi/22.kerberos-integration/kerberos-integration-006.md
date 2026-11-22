# Phân biệt KerberosAuthenticationProvider với xác thực service ticket trong Spring Security Kerberos

## 1. Vì sao cần phân biệt hai provider?

Trong một ứng dụng **Spring Security – federation**, bạn có thể gặp đồng thời hai trải nghiệm:

- Người dùng mở website nội bộ trên máy đã đăng nhập domain. Trình duyệt tự trao đổi **HTTP Negotiate / SPNEGO** và ứng dụng đăng nhập mà không hỏi lại mật khẩu.
- Người dùng truy cập từ thiết bị không có Kerberos credentials hoặc browser không hỗ trợ Negotiate. Ứng dụng hiển thị **form login**, người dùng nhập username/password để được kiểm chứng với Kerberos KDC/realm.

Cả hai có thể dùng **Kerberos V5**, nhưng dữ liệu đầu vào, nơi kiểm mật mã và provider cần chọn **khác nhau**:

1. `KerberosAuthenticationProvider` là provider cho **luồng username/password**, sử dụng **KerberosClient** (thường `SunJaasKerberosClient`) để đăng nhập bằng credentials qua Kerberos/JAAS; sau đó nạp tài khoản/authorities bằng `UserDetailsService`.
2. `KerberosServiceAuthenticationProvider` là provider cho **service ticket hoặc token SPNEGO** đã được browser/client gửi tới **ứng dụng đóng vai service acceptor**. Nó cần **KerberosTicketValidator** (thường `SunJaasKerberosTicketValidator`) và **service principal/keytab** của chính service để xác minh qua GSS/JAAS; sau đó cũng dùng `UserDetailsService`.

Tên gọi gần giống nhau dễ dẫn tới cấu hình sai: thêm `KerberosAuthenticationProvider` **không tự làm browser SPNEGO hoạt động**, và thêm `KerberosServiceAuthenticationProvider` **không tự tạo màn hình xác minh username/password**.

Bài học thuộc nhóm **Tích hợp Kerberos**. Mục tiêu:

- Phân biệt **KerberosClient.login(username, password)** với **KerberosTicketValidator.validateTicket(byte[] token)** ở mức trách nhiệm.
- Hiểu rõ request Authentication types: `UsernamePasswordAuthenticationToken` và `KerberosServiceRequestToken`.
- Đọc được luồng Spring Security form-login, SPNEGO, `ProviderManager`, `supports(...)`, `UserDetailsService` và `SecurityContext`.
- Phân biệt **KDC xác thực password ở AS exchange** với **service acceptor xác minh AP-REQ/GSS token bằng keytab**.
- Thiết lập config một hoặc hai provider, kèm fallbacks và giới hạn.
- Chẩn đoán lỗi KDC, SPN, keytab, replay, clock skew, trạng thái local user và quyền truy cập.
- Tự chạy một **Java 17 demo** mô phỏng provider routing và test các kiểu nhầm lẫn đường xác thực.

**Nguyên tắc:** Hãy nhìn **loại bằng chứng mà caller trình**: username/password hay Kerberos service credential. Từ đó chọn **provider có đúng trust boundary**, không chọn theo tên class có chữ “Kerberos” chung chung.

## 2. Bức tranh tổng thể

~~~text
                           Spring Security Servlet app
                                      |
                            AuthenticationManager
                            (ProviderManager)
                                /           \
                               /             \
                      FORM LOGIN           SPNEGO / HTTP
                         |                   NEGOTIATE
                         |                       |
               UsernamePassword           KerberosService
              AuthenticationToken         RequestToken
                         |                       |
                         v                       v
             KerberosAuthentication  KerberosServiceAuthentication
                   Provider                  Provider
                         |                       |
                         v                       v
                 KerberosClient           KerberosTicketValidator
                SunJaasKerberosClient     SunJaasKerberosTicketValidator
                         |                       |
                         v                       v
                    KDC/JAAS                JAAS/JGSS acceptor
             login(username,password)      servicePrincipal + keytab
                         \                       /
                          \                     /
                           v                   v
                         user principal được xác minh
                                      |
                                      v
                         UserDetailsService / local policy
                                      |
                                      v
                         Authentication + GrantedAuthorities
                                      |
                                      v
                            SecurityContext / session
                                      |
                                      v
                              Application authorization
~~~

**Không phải hai provider gọi nhau.** Chúng là **hai implementations của AuthenticationProvider** với loại Authentication request khác nhau. `ProviderManager` sẽ hỏi `supports(...)` và thử provider thích hợp theo policy/ thứ tự đăng ký.

Một service Kerberos có thể **chỉ dùng SPNEGO**, **chỉ dùng form login qua KDC**, hoặc **kết hợp cả hai**. Không nhất thiết phải bật cả hai.

## 3. Bảng so sánh cốt lõi

| Tiêu chí | KerberosAuthenticationProvider | KerberosServiceAuthenticationProvider |
| --- | --- | --- |
| **Mục đích** | Xác thực **username/password** bằng Kerberos KDC | Xác thực **service ticket / SPNEGO token** ở service nhận |
| **Dữ liệu vào** | Username và mật khẩu do user cung cấp | GSS-API/SPNEGO bytes từ caller; thường trong header `Authorization: Negotiate` |
| **Authentication request** | Thường là `UsernamePasswordAuthenticationToken` | `KerberosServiceRequestToken` |
| **Bộ kiểm mật mã** | `KerberosClient`, ví dụ `SunJaasKerberosClient` | `KerberosTicketValidator`, ví dụ `SunJaasKerberosTicketValidator` |
| **Tác nhân mạng** | Server web dùng username/password làm Kerberos client để xác thực qua KDC/JAAS | Browser/OS có ticket; server web dùng keytab để nhận và xác minh GSS token, không phải thực hiện password login |
| **Service keytab** | Không phải thành phần bắt buộc chỉ để kiểm user/password | **Cần** service principal/keytab hoặc acceptor credentials tương đương theo deployment |
| **User password** | **Có**, ứng dụng xử lý password đầu vào; cần bảo vệ nghiêm ngặt | **Không**, ứng dụng không cần biết password của user |
| **KDC involvement** | Kerberos client thực hiện quy trình đăng nhập/AS theo môi trường | Browser có thể dùng TGT xin ticket từ KDC/TGS; acceptor có thể xác minh AP-REQ cục bộ bằng keytab |
| **Trình duyệt** | Form POST thường tới login processing URL | 401 `WWW-Authenticate: Negotiate`, browser trả `Authorization: Negotiate` |
| **Filter thường gặp** | `UsernamePasswordAuthenticationFilter` qua DSL `formLogin` | `SpnegoAuthenticationProcessingFilter` |
| **EntryPoint** | Login page/redirect theo form policy | `SpnegoEntryPoint`, có thể forward login page khi fallback |
| **Sau khi xác thực** | `KerberosUsernamePasswordAuthenticationToken` có thể giữ JAAS Subject phục vụ use case phù hợp | `KerberosServiceRequestToken` authenticated chứa kết quả ticket validation/GSS context |
| **Local account/roles** | `UserDetailsService` | `UserDetailsService` |
| **Lỗi thường gặp** | Wrong password, KDC unreachable, JAAS login failure, account disabled | SPN/keytab/KVNO sai, expired ticket, replay, invalid GSS/SPNEGO token |
| **Tình huống sử dụng** | Non-domain devices, form fallback có chủ đích | Integrated Windows Authentication/domain SSO, Kerberos HTTP acceptor |

**Chú ý:** `UsernamePasswordAuthenticationToken` và `KerberosServiceRequestToken` là **Spring Authentication objects**, không phải vé KDC dạng raw, không phải JWT. Và `KerberosUsernamePasswordAuthenticationToken` là một class trong module Kerberos **dùng làm kết quả đăng nhập phù hợp**, không phải “Kerberos service ticket”.

## 4. Luồng A: KerberosAuthenticationProvider — username/password

### 4.1. Khi nào luồng này được kích hoạt?

Thường khi:

- Người dùng chưa có OS Kerberos credentials hoặc browser không dùng SPNEGO.
- App chủ động cung cấp form login để người dùng điền username/password.
- Doanh nghiệp muốn kiểm password bằng KDC/realm thay vì một local password database.
- Ứng dụng đồng thời hỗ trợ SPNEGO nhưng có chính sách fallback cho thiết bị ngoài domain.

Sơ đồ:

~~~text
Browser                     Spring Web                    KDC / Realm
   |                            |                             |
   | GET /login                 |                             |
   |--------------------------->|                             |
   |<---------------------------| HTML form + CSRF            |
   |                            |                             |
   | POST /login               |                             |
   | username + password        |                             |
   |--------------------------->|                             |
   |                            | UsernamePassword            |
   |                            | AuthenticationFilter        |
   |                            |   -> ProviderManager        |
   |                            |   -> KerberosAuthentication |
   |                            |      Provider               |
   |                            |   -> SunJaasKerberosClient  |
   |                            |       .login(user,password) |
   |                            |---------------------------->|
   |                            |   JAAS/Kerberos login       |
   |                            |<----------------------------|
   |                            | KDC đã kiểm credentials      |
   |                            | UserDetailsService          |
   |                            |  check enabled/authorities  |
   |<---------------------------| Authentication + session   |
~~~

Spring không nên so plaintext password với một chuỗi hard-coded trong business code. `SunJaasKerberosClient` sử dụng JAAS login module của Java runtime và KDC để thực hiện xác thực phù hợp với realm/Kerberos configuration. Phương thức được Javadoc công bố là:

~~~java
JaasSubjectHolder login(String username, String password);
~~~

Đó là signature **KerberosClient**, không phải phương thức `authenticate` của Spring AuthenticationProvider. `KerberosAuthenticationProvider` gọi client này thông qua pipeline Spring. Tùy cấu hình/phiên bản, kết quả JAAS Subject có thể dùng cho use case nhiều tầng; không đồng nghĩa mọi web app đã được cấp quyền delegation.

### 4.2. Dùng KDC khác với so mật khẩu local

`KerberosAuthenticationProvider` **không phải** `DaoAuthenticationProvider`:

- `DaoAuthenticationProvider` thường nạp password hash từ `UserDetailsService` và kiểm bằng `PasswordEncoder`.
- `KerberosAuthenticationProvider` dùng `KerberosClient` để **xác minh username/password với Kerberos realm/KDC**.
- `ActiveDirectoryLdapAuthenticationProvider` (nếu dùng) thực hiện AD/LDAP authentication riêng, **không phải alias** của KerberosAuthenticationProvider.
- Nếu tổ chức dùng OIDC/SAML broker, đó là trust/protocol khác, không tự thay Kerberos provider.

Vì ứng dụng form-login **nhận mật khẩu user**, cần HTTPS, CSRF protection, rate limiting, lưu vết tối thiểu, không log password, không đặt password trong query string, và cơ chế chống credential stuffing theo policy. Một lợi ích của SPNEGO là server web **không cần trực tiếp nhận user password**, nên nên ưu tiên khi hạ tầng cho phép.

### 4.3. Request và kết quả Authentication

Thông thường Spring form filter tạo một request:

~~~java
UsernamePasswordAuthenticationToken request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice@EXAMPLE.TEST", userSuppliedPassword);
~~~

Đây là **snippet minh họa** nằm ở tầng Spring Authentication pipeline; nếu dùng `formLogin`, filter tự tạo request, không cần controller tự gọi đoạn này. Không hard-code hoặc ghi password vào log.

Sau thành công, module Kerberos có class `KerberosUsernamePasswordAuthenticationToken` — mở rộng `UsernamePasswordAuthenticationToken` — và có thể giữ `JaasSubjectHolder` cho một số use case như `KerberosMultiTier`. Các thông tin này thuộc **server-side credential context nhạy cảm**; không serialize Subject/TGT/service credentials sang JSON cho browser.

### 4.4. Những gì provider form **không** làm

- Không nhận và xác minh `Authorization: Negotiate` thay cho service ticket provider.
- Không thay thế browser SPNEGO/Kerberos acceptor keytab.
- Không tự có nghĩa ứng dụng đã phát HTTP `WWW-Authenticate: Negotiate`.
- Không đảm bảo login thành công khi user không được local policy cấp quyền.
- Không tự thu hồi mọi TGT hoặc service tickets trên máy người dùng khi logout.
- Không tự thực hiện Kerberos constrained delegation đến mọi downstream service.

## 5. Luồng B: KerberosServiceAuthenticationProvider — service ticket

### 5.1. Client có TGT trước khi đến website

Trong domain SSO, hệ điều hành/browser có thể đã có **Ticket Granting Ticket (TGT)** từ AS exchange. Để truy cập `https://portal.example.test/private`, client lấy hoặc dùng lại một **service ticket** cho service principal:

~~~text
HTTP/portal.example.test@EXAMPLE.TEST
~~~

Nếu chưa có service ticket cache, client dùng **TGT** trong TGS exchange để xin service ticket cho SPN này. Browser không cần gửi mật khẩu user cho web app. **TGT không được đưa trực tiếp vào Spring web acceptor**.

### 5.2. HTTP Negotiate challenge/response

~~~http
GET /private HTTP/1.1
Host: portal.example.test

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Client sau đó gửi:

~~~http
GET /private HTTP/1.1
Host: portal.example.test
Authorization: Negotiate <base64-SPNEGO-GSS-token>
~~~

Các dòng là **minh họa header**; dữ liệu trong dấu ngoặc không phải token hợp lệ. Đây là **GSS/SPNEGO token**, không nhất thiết chỉ chứa raw service ticket; nó có thể bao gồm **AP-REQ và authenticator**, mech negotiation state và có thể cần nhiều vòng trao đổi. Không Base64-decode rồi parse username trong controller.

### 5.3. Đường đi qua Spring Security

~~~text
SpnegoEntryPoint: gửi 401 / WWW-Authenticate: Negotiate
        |
        v
Browser: Authorization: Negotiate <token>
        |
        v
SpnegoAuthenticationProcessingFilter
  - đọc header
  - decode bytes từ token
  - tạo KerberosServiceRequestToken (chưa authenticated)
        |
        v
ProviderManager
  - provider.supports(KerberosServiceRequestToken)
        |
        v
KerberosServiceAuthenticationProvider
  - KerberosTicketValidator.validateTicket
        |
        v
SunJaasKerberosTicketValidator
  - servicePrincipal = HTTP/portal.example.test@EXAMPLE.TEST
  - service keytab = /run/secrets/kerberos/http.keytab
  - JAAS/JGSS accept security context
  - verify Kerberos service ticket + authenticator
        |
        v
Kết quả user principal do validator đã xác minh
        |
        v
UserDetailsService / local user status & authorities
        |
        v
Authentication / SecurityContext
        |
        v
Application authorization
~~~

**`KerberosServiceAuthenticationProvider` không xác minh password user.** Nó sử dụng **KerberosTicketValidator** để kiểm rằng client nắm service credential hợp lệ theo service identity của ứng dụng; đây là **đường xác thực sử dụng bằng chứng đã cấp trước**.

### 5.4. Vì sao cần keytab và SPN?

Một service ticket của Kerberos được cấp cho **đúng service principal** và được bảo vệ bằng long-term key của service. Ví dụ:

~~~text
SPN:    HTTP/portal.example.test@EXAMPLE.TEST
Keytab: /run/secrets/kerberos/http.keytab
~~~

Service keytab phải chứa key tương ứng với principal, encryption type và **KVNO** mà KDC dùng khi phát service ticket. Sai keytab/KVNO/SPN/hostname có thể khiến GSS accept thất bại ngay cả khi browser có ticket và KDC đã cấp thành công.

**Không dùng user password hoặc khóa `krbtgt` để thay service keytab.** `krbtgt` là principal của TGS/KDC, không phải website. Truy cập ticket của service khác, ví dụ `cifs/files.example.test`, không được xác thực như ticket cho `HTTP/portal.example.test`.

### 5.5. Không nhầm “ticket dùng một lần” của giao thức khác

Kerberos V5 service ticket có thể được sử dụng trong nhiều **AP exchanges** khi còn hiệu lực, nếu client tạo **Authenticator mới** và service chấp nhận theo GSS/Kerberos policy. **Authenticator đã phát lại** bị replay protection từ chối; việc phát lại **nguyên cùng GSS/AP-REQ token** có thể gây lỗi Kerberos.

Javadoc `KerberosServiceRequestToken` còn lưu ý đối tượng authenticated token **không được đem authenticate lại**, vì có thể gặp Kerberos reply/replay error. Đây là lời nhắc **không cache raw SPNEGO token rồi re-submit để xác thực mỗi request**. Nên giữ local SecurityContext/HttpSession phù hợp hoặc yêu cầu client tạo một GSS exchange hợp lệ mới.

Đừng áp quy tắc **CAS Service Ticket một lần validation** lên Kerberos service ticket; hai giao thức khác nhau.

## 6. Authentication types và cách ProviderManager phân luồng

### 6.1. ProviderManager hỏi supports(Class)

Spring Security có interface:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
    boolean supports(Class<?> authentication);
}
~~~

Đây là **tóm tắt signature ở mức ý tưởng**; type parameters/annotations có thể thay đổi theo Spring Security version. Ý nghĩa:

- `supports` cho biết provider **có khả năng** xử lý một lớp Authentication.
- `authenticate` thực hiện việc kiểm thực tế; có thể trả về Authentication thành công, hoặc throw AuthenticationException, hoặc `null` nếu không thể xử lý theo contract.
- `ProviderManager` quản lý nhiều providers và tìm provider theo request type/ordering.

Theo tài liệu Kerberos:

~~~text
Request: UsernamePasswordAuthenticationToken
          |
          +-> KerberosAuthenticationProvider
                    uses KerberosClient

Request: KerberosServiceRequestToken
          |
          +-> KerberosServiceAuthenticationProvider
                    uses KerberosTicketValidator
~~~

Không dùng `getPrincipal().toString()` như logic chọn “SPNEGO hay form”: ban đầu SPNEGO token chưa được xác minh, nên username từ browser hoặc header không đáng tin. Phân luồng bằng **request class và filter/endpoint** được cấu hình đúng.

### 6.2. Hai provider đều được đăng ký có nghĩa gì?

Ví dụ một `ProviderManager` có hai provider:

~~~java
AuthenticationManager manager = new ProviderManager(
    kerberosPasswordProvider,
    kerberosServiceTicketProvider);
~~~

Cách sử dụng:

- Form-login chuyển request username/password đến **KerberosAuthenticationProvider**.
- SPNEGO filter chuyển `KerberosServiceRequestToken` đến **KerberosServiceAuthenticationProvider**.
- Cả hai sau đó đều có thể dùng chung `UserDetailsService`/local account policy.

**Quan trọng về provider order:** `ProviderManager` có thể có nhiều providers hỗ trợ **cùng một kiểu request**, ví dụ `DaoAuthenticationProvider` và `KerberosAuthenticationProvider` đều xử lý username/password trong một số cấu hình. Khi một provider thất bại, Spring có quy tắc tiếp tục hay dừng theo loại AuthenticationException. Do đó phải thiết kế rõ:

- Realm/KDC nào chịu trách nhiệm xác thực form?
- Có cho fallback sang local DB/LDAP không?
- Lỗi “KDC unavailable” có được chuyển sang provider yếu hơn không?
- Có cho một username hợp lệ ở provider A đăng nhập qua provider B với password khác không?
- Kết quả provider nào được phép cấp quyền nghiệp vụ?

**Không thêm nhiều providers rồi giả định thứ tự luôn được bỏ qua.** Tích hợp test với provider manager thật, từng lỗi wrong-password, disabled, KDC outage và wrong-token-type.

### 6.3. supports=true không phải accepted=true

`supports(KerberosServiceRequestToken.class)` chỉ nói provider **biết xử lý kiểu yêu cầu**, không nói ticket đã giải mã đúng. Một raw SPNEGO token của attacker có thể có kiểu request hợp lệ nhưng **gặp lỗi xác minh** trong `KerberosTicketValidator`.

Tương tự, `supports(UsernamePasswordAuthenticationToken.class)` không có nghĩa password chính xác. Phải đợi `authenticate` trả kết quả được xác minh, rồi mới lấy principal để phân quyền.

## 7. So sánh trust boundary: KDC login và service acceptor

| Câu hỏi | Luồng username/password | Luồng service ticket |
| --- | --- | --- |
| Ai cung cấp bằng chứng ban đầu? | User/client form cung cấp username + password | Browser/OS cung cấp GSS/SPNEGO token |
| Ai kiểm password? | JAAS/KDC qua KerberosClient login | **Không có bước kiểm password tại service** |
| KDC tham gia lúc nào? | Khi KerberosClient thực hiện login theo realm policy | Khi client lấy TGT/ST, có thể từ cache; acceptor thường không hỏi KDC mỗi request |
| Ai nắm keytab? | Không yêu cầu web keytab chỉ để kiểm password | Server acceptor nắm service keytab/acceptor credentials |
| Credential compromise nguy hiểm ra sao? | Web app có thể làm lộ mật khẩu user nếu bị compromise | Keytab compromise cho phép giả dạng service/đọc hoặc xử lý tickets trong phạm vi key |
| Bằng chứng user identity từ đâu? | KDC login result/JAAS Subject rồi local mapping | GSS ticket validation result rồi local mapping |
| Cần local authorization không? | **Có** | **Có** |
| Có mặc định là MFA vừa hoàn thành không? | **Không**; tùy KDC/JAAS/pre-auth policy | **Không**; SPNEGO không tự chứng minh MFA freshness |
| Có tự logout toàn domain không? | **Không** | **Không** |

Một kết quả `KerberosClient.login` thành công có thể dẫn đến JAAS Subject chứa client-side Kerberos credentials phục vụ các use case đặc biệt. **Đừng serialize JAAS Subject hoặc Kerberos credentials vào browser** và đừng mặc nhiên cho service quyền ủy nhiệm tới mọi backend. Việc dùng `KerberosMultiTier`/constrained delegation cần chính sách và service principal rights riêng.

## 8. Cấu hình dependencies cho Spring Security Kerberos

Trong Spring Security Kerberos **7.x**, các module chính dùng group `org.springframework.security`, ví dụ:

~~~groovy
// build.gradle: dự án Spring Boot/Spring Security đã quản lý version
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-kerberos-core'
    implementation 'org.springframework.security:spring-security-kerberos-web'
}
~~~

Nếu chỉ dùng `KerberosAuthenticationProvider` ngoài web, module core có thể đủ tùy dependencies. Nếu dùng `SpnegoAuthenticationProcessingFilter`/HTTP, cần web extension.

**Phiên bản rất quan trọng:** Spring Security Kerberos 7.x đổi Maven coordinates sang `org.springframework.security`. Các dự án Spring Security 6.x/extension 2.x có thể vẫn dùng group `org.springframework.security.kerberos`. Không mix JAR 6.x và 7.x hoặc chọn version ngẫu nhiên để xử lý `ClassNotFoundException`/`NoSuchMethodError`. Kiểm BOM, dependency graph, Jakarta Servlet/Java versions và tài liệu đúng bản.

Nguồn chính thức: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html .

### 8.1. Môi trường cần chuẩn bị

Tùy đường xác thực:

**Form KerberosClient:**

- KDC/realm cấu hình đúng.
- DNS và `krb5.conf` hoặc Java system property thích hợp.
- KDC cho phép username/password/JAAS login theo policy.
- Application HTTPS và chính sách bảo vệ password/form.

**SPNEGO Service Ticket:**

- Client có OS Kerberos credentials/TGT phù hợp.
- Browser được phép Integrated Authentication cho service.
- Service principal `HTTP/public-host@REALM` đã đăng ký tại KDC/AD.
- Service keytab đúng principal/KVNO/enctype, JVM đọc được.
- Java/Kerberos runtime, DNS, reverse proxy và time sync nhất quán.
- Header `Authorization: Negotiate` đến đúng server acceptor.
- SPNEGO/GSS mechanism thực tế là Kerberos nếu policy yêu cầu (không lặng lẽ dùng NTLM).

## 9. Cấu hình riêng KerberosAuthenticationProvider

Ví dụ class bean trong **Spring Boot/Spring Security Kerberos 7.x**. Các import và methods được minh họa theo Spring Security Kerberos docs:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosClient;

@Configuration
public class KerberosPasswordProviderConfig {
    @Bean
    KerberosAuthenticationProvider kerberosPasswordProvider(
            UserDetailsService userDetailsService) {
        SunJaasKerberosClient client = new SunJaasKerberosClient();
        client.setDebug(false); // không log credentials/JAAS details
        KerberosAuthenticationProvider provider =
            new KerberosAuthenticationProvider();
        provider.setKerberosClient(client);
        provider.setUserDetailsService(userDetailsService);
        return provider;
    }
}
~~~

Đây là **bean cấu hình**, không phải ứng dụng Java độc lập. Để sử dụng:

- Đăng ký provider vào AuthenticationManager/SecurityFilterChain có `formLogin`.
- Cung cấp `UserDetailsService` thực, không dùng dummy service cấp ROLE_ADMIN cho tất cả user.
- Có `/login` page và CSRF token nếu dùng custom form page.
- KDC/JAAS config phải phù hợp realm/user credentials.
- Đảm bảo auth result của KerberosClient là **nguồn xác thực**, không đơn giản gọi `userDetailsService.loadUserByUsername` rồi coi user tồn tại là login thành công.

**Không copy đoạn JavaConfig của tài liệu có `client.setDebug(true)` vào production** khi chưa quản lý log, vì debug Kerberos/JAAS có thể làm lộ thông tin vận hành nhạy cảm.

### 9.1. Form login chỉ nên sử dụng trên HTTPS

Một request hợp lệ có thể là:

~~~http
POST /login HTTP/1.1
Host: portal.example.test
Content-Type: application/x-www-form-urlencoded

username=alice%40EXAMPLE.TEST&password=<sensitive-value>&_csrf=<csrf-token>
~~~

Đây là cấu trúc minh họa **không chứa mật khẩu thật**, chưa phải raw request đầy đủ. Server cần:

- HTTPS bắt buộc, TLS trust policy.
- CSRF token còn hiệu lực nếu dùng cookie-based form.
- Không ghi password trong access logs, APM, request body dumps, error pages hoặc exception.
- Brute-force protection, lockout/step-up theo tổ chức.
- Khi authentication fail, trả error chung không lộ user enumeration quá mức.
- Không lưu username/password trong session/remember-me theo cách không được duyệt.
- Erase credentials nơi thích hợp và tránh giữ JAAS Subject nhạy cảm quá lâu.

### 9.2. UserDetailsService có thể thất bại sau KDC success

KDC có thể xác nhận `alice@EXAMPLE.TEST` hợp lệ nhưng local account bị disabled hoặc chưa được onboarded. Khi đó **không cấp session authenticated** cho người dùng đó, hoặc xử lý JIT provisioning theo policy rõ. `UserDetailsService` là bộ ánh xạ/kiểm quyền nghiệp vụ, **không thay KerberosClient kiểm password**.

## 10. Cấu hình riêng KerberosServiceAuthenticationProvider

Ví dụ bean cho website public FQDN `portal.example.test`:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;

@Configuration
public class KerberosServiceTicketProviderConfig {
    @Bean
    SunJaasKerberosTicketValidator kerberosTicketValidator() {
        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(
            "HTTP/portal.example.test@EXAMPLE.TEST");
        validator.setKeyTabLocation(new FileSystemResource(
            "/run/secrets/kerberos/http.keytab"));
        validator.setDebug(false);
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosServiceTicketProvider(
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

**Không thể chạy đoạn này chỉ bằng javac**: cần project Spring, các dependencies, cấu hình realm, service principal và **keytab thật do KDC/AD cấp**. Không có KDC test thì không thể xác nhận handshake SPNEGO end-to-end.

### 10.1. Ý nghĩa của setTicketValidator

`SunJaasKerberosTicketValidator` là implementation Java/JGSS cho **service acceptor**. Nó dùng service principal và keytab để xác minh Kerberos/SPNEGO token. Ứng dụng không nên tự:

- Base64-decode Negotiate rồi tin username in được.
- Parse service ticket như JSON/JWT, xem token có `alice` là đúng.
- Bỏ qua service principal match hoặc chấp nhận TGT thay service ticket.
- Bỏ qua clock skew, ticket lifetime, authenticator replay hoặc GSS integrity checks.
- Chấp nhận keytab của service khác hoặc keytab từ tenant không được tin.
- Tin header `X-Forwarded-User` do Internet cung cấp để bỏ qua validator.

### 10.2. Vì sao ticket validator thường không cần gọi KDC mỗi request?

KDC cấp service ticket, bảo vệ bằng khóa của service. Khi app nhận AP-REQ, JAAS/JGSS có thể **giải mã/xác minh bằng service keytab**, kết hợp authenticator/session key/replay/time checks. Vì vậy KDC không phải nguồn API bắt buộc **trên từng HTTP request**. Nếu browser đã có service ticket trong cache, một login SPNEGO có thể thành công dù không có TGS exchange mới ngay lúc đó, theo môi trường.

Điều này đồng thời có nghĩa một người dùng bị disable tại KDC **không nhất thiết làm mọi service ticket đã phát trở nên bất hợp lệ tức thì**. Muốn thu hồi truy cập gần thời gian thực phải kết hợp local session management, account status checks, ticket lifetime/policy và chiến lược cấp quyền tương ứng.

## 11. SecurityFilterChain: SPNEGO-only

Nếu ứng dụng chỉ muốn Kerberos HTTP SSO, có thể xây SecurityFilterChain như sau. Đoạn này cần hai bean từ `KerberosServiceTicketProviderConfig` ở trên:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@Configuration
public class SpnegoOnlySecurityConfig {
    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider ticketProvider)
            throws Exception {

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(new ProviderManager(ticketProvider));
        filter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .authenticationProvider(ticketProvider)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .addFilterBefore(filter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

Điểm quan trọng:

- `SpnegoEntryPoint` phản hồi HTTP 401 với `WWW-Authenticate: Negotiate`.
- `SpnegoAuthenticationProcessingFilter` đọc header và tạo request Authentication, **không xác minh ticket một mình**.
- `ProviderManager(ticketProvider)` bảo đảm filter chuyển request đến **KerberosServiceAuthenticationProvider**.
- `setSecurityContextRepository(new HttpSessionSecurityContextRepository())` giúp xác thực thành công được lưu trong local session nếu ứng dụng dùng stateful web; Javadoc filter cảnh báo mặc định có thể không lưu SecurityContext.
- `ChangeSessionIdAuthenticationStrategy` giúp giảm session fixation.
- `authorizeHttpRequests` áp business constraints; demo chỉ yêu cầu authenticated cho các URL không public.
- Không có form-login provider; không phải “form-login nhưng dấu password bị ẩn”.

**Không khai `@Bean SpnegoAuthenticationProcessingFilter` ngoài filter chain mà không kiểm soát Servlet auto-registration**, vì có thể bị thực thi hai lần. Nếu có nhiều SecurityFilterChain, filter phải ở đúng matcher/chain chứa requests cần Negotiate.

## 12. SecurityFilterChain: kết hợp SPNEGO và form fallback

Một ứng dụng vừa phục vụ máy domain đã có Kerberos credentials, vừa cho khách nội bộ từ thiết bị không có integrated auth, có thể phối hợp **hai providers**:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.kerberos.authentication.KerberosAuthenticationProvider;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;

@Configuration
public class SpnegoWithFormSecurityConfig {
    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            KerberosAuthenticationProvider passwordProvider,
            KerberosServiceAuthenticationProvider ticketProvider)
            throws Exception {

        ProviderManager manager = new ProviderManager(
            passwordProvider, ticketProvider);

        SpnegoAuthenticationProcessingFilter spnegoFilter =
            new SpnegoAuthenticationProcessingFilter();
        spnegoFilter.setAuthenticationManager(manager);
        spnegoFilter.setSecurityContextRepository(
            new HttpSessionSecurityContextRepository());
        spnegoFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/public/**", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll())
            .authenticationProvider(passwordProvider)
            .authenticationProvider(ticketProvider)
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint("/login")))
            .addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Các điều kiện để sử dụng đúng:**

1. Hai provider bean phải thực sự có `KerberosClient` và `KerberosTicketValidator`/`UserDetailsService` được cấu hình.
2. Phải có **view/controller GET /login** để hiển thị form và POST login processing URL phù hợp. Cấu hình này **không tạo sẵn HTML page**.
3. `SpnegoEntryPoint("/login")` phản hồi 401 Negotiate và có tùy chọn **forward** tới page fallback; nó **không đơn giản là HTTP 302 redirect trực tiếp**.
4. Form có CSRF token đúng, POST password qua HTTPS.
5. Browser hỗ trợ SPNEGO sẽ có thể tự Negotiate; browser không hỗ trợ có thể dùng form page tùy thiết lập/agent behavior.
6. Phần session persistence phải hoạt động ở cả form và SPNEGO. Kiểm cookie/HttpSession/CSRF/session fixation trong bản Spring đang chạy.
7. Nếu có nhiều providers cùng support username/password, phải cấu hình precedence và fallback fail-closed; không để KDC outage biến thành bypass sang weaker provider.
8. User identity sau cả hai đường phải được scope theo **realm + principal**, kiểm account enabled và cấp authorities từ **local policy nhất quán**.
9. Nếu UI/flow cần chọn SSO hay form tách biệt, có thể dùng security matchers/filter chains riêng được test, không nhất thiết dùng một chain chung.
10. Không để filter trả 401 Negotiate cho mọi API client nếu giao diện/API có yêu cầu authentication scheme khác; thiết kế endpoint và client behavior rõ.

**Tránh khai đồng thời toàn bộ ba class SecurityFilterChain ở phần 9–12 trong một project mẫu.** Phần 9 và 10 là hai **provider bean configurations**, phần 11 và 12 là **hai phương án security chain thay thế nhau**. Chọn **một phương án** hoặc thiết kế multiple chains có matcher/order rõ ràng.

## 13. TGT, service ticket, SPNEGO token và JAAS Subject

Một số lớp dữ liệu dễ bị nhầm:

| Thứ | Ai sở hữu? | Dùng ở đâu? | Provider trực tiếp xử lý? |
| --- | --- | --- | --- |
| **Password của user** | User / form request, KDC credential mechanism | `KerberosClient.login(...)` | **KerberosAuthenticationProvider** |
| **TGT** | Client OS/JAAS Subject/credential cache sau AS exchange | KDC TGS để xin service tickets | Không gửi TGT như login header tới web app |
| **Service ticket** | Client lấy từ TGS cho một service SPN | AP-REQ đến service đích | **KerberosServiceAuthenticationProvider** qua TicketValidator |
| **Authenticator** | Client tạo bằng session key, kèm ticket | Kerberos AP-REQ/negotiation | JGSS/Kerberos library kiểm |
| **SPNEGO/GSS token** | Browser/OS tạo | HTTP Authorization: Negotiate | SPNEGO filter + service ticket provider |
| **Service keytab** | Web service acceptor | Giải mã/kiểm ticket cho SPN | SunJaasKerberosTicketValidator |
| **JaasSubjectHolder** | Server-side JAAS login state | Có thể phục vụ multi-tier/credential handling | Có trong KerberosClient/login result |
| **Spring SecurityContext** | Web app/session | Authorization giữa requests | Kết quả của hai flow sau khi authentication thành công |

**Không xem JAAS Subject là một user-visible session token.** Subject có thể giữ private credentials, TGT/service session keys và thông tin nhạy cảm. Không đưa vào JSON, cookie, log hay shared cache chưa được thiết kế bảo mật.

### 13.1. TGT có tự xuất hiện ở form path không?

Khi `SunJaasKerberosClient.login(username,password)` thành công, JAAS có thể tạo một Subject chứa Kerberos credentials tùy login/module settings. Điều đó **khác hoàn toàn** việc web app accept service ticket của browser qua SPNEGO. Form path là **app chủ động làm client đăng nhập bằng user credentials**; service-ticket path là **app thụ động làm acceptor**.

Tùy policy, giữ một JAAS Subject có user credentials tại web server có thể tạo thêm rủi ro. **Không tự bật multi-tier/delegation** trừ khi cần và đã được kiểm soát.

### 13.2. SPNEGO không nhất thiết luôn là Kerberos

HTTP `Negotiate` có thể thương lượng các GSS mechanisms khác, trong một số hệ thống Windows có **NTLM fallback**. Nếu chính sách chỉ chấp nhận Kerberos, cần test mechanism thực tế và cấu hình client/server không tự hạ xuống NTLM. Đừng chỉ thấy `WWW-Authenticate: Negotiate` mà ghi “Kerberos đã xác minh”.

## 14. Ranh giới phân quyền: hai provider cùng cần UserDetailsService

Dù username/password hay GSS token đã được Kerberos subsystem xác minh, **ứng dụng phải quyết định user có được dùng dịch vụ và làm tác vụ hay không**.

Ví dụ:

~~~text
Kerberos identity: alice@EXAMPLE.TEST
Local user:        portal-user-17
Enabled:           true
Tenant:            finance
Granted authorities:
  ROLE_REPORT_READER
  ROLE_EMPLOYEE
~~~

Còn:

~~~text
Kerberos identity: disabled@EXAMPLE.TEST
Local user:        portal-user-34
Enabled:           false
=> không cấp session/Authentication có quyền
~~~

Quy tắc:

- Định danh local nên scope theo **username + Kerberos realm**, tránh gộp `alice@REALM_A` và `alice@REALM_B`.
- Nếu có account linking/JIT provisioning, cần hợp đồng rõ và logging/audit.
- Không tin `X-Remote-User`, email/header/query từ browser để thay username đã được KDC/GSS kiểm.
- Không biến tên group, username, Host header hoặc fake principal thành dynamic admin role.
- `UserDetailsService` có thể đọc LDAP/AD/local DB **để nạp thuộc tính user và authorities**, nhưng không được coi việc tìm được user là bằng chứng password/GSS token đã hợp lệ.
- Với resource nhạy cảm, luôn kiểm tenant/resource ownership độc lập với `isAuthenticated()`.
- Nếu user bị disable giữa session, cần chiến lược session invalidation/account refresh ngoài ticket-validation path.

**Kerberos xác thực user; Spring Security phân quyền dựa trên principals/authorities và app policy.** Không có provider nào tự giải quyết authorization chi tiết cho mọi nghiệp vụ.

## 15. Java 17 độc lập: mô phỏng hai provider và việc chọn request type

Ví dụ này **biên dịch với JDK 17+**, không cần Spring Boot, KDC, AD, JAAS, GSS hay keytab. Nó mô hình hóa những quyết định cốt lõi:

- `PasswordProvider` chỉ hỗ trợ `PasswordRequest`; giả lập KDC kiểm password.
- `ServiceTicketProvider` chỉ hỗ trợ `TicketRequest`; giả lập GSS acceptor kiểm SPN, expiry, chứng cứ mật mã và replay.
- `ProviderManagerMock` chọn đúng provider theo **request type**, không đọc username hoặc token text để đoán loại authentication.
- Cả hai chỉ lấy quyền từ **local account policy**, không từ chuỗi token do client cung cấp.
- Ticket hợp lệ cho SPN HTTP được chấp nhận; **TGT hoặc ticket cho CIFS** không được nhận ở web.
- Cùng ticket nhưng **authenticator mới** có thể dùng khi còn hạn; **lặp nguyên authenticator** bị từ chối.
- KDC xác minh thành công nhưng user local bị khóa vẫn bị từ chối.
- Wrong password, fake GSS proof, expired ticket hoặc unknown user phải fail closed.

**Cảnh báo quan trọng:** đây là **MÔ PHỎNG LUỒNG**. `MockKdc` dùng một mật khẩu giả `lab-secret` trong source, `cryptographicallyVerified` là **đầu ra giả lập đáng tin** (không bao giờ lấy boolean này từ HTTP/JSON), replay cache chỉ là Set trong một JVM. **Không có mật mã Kerberos thật**, không có JAAS `login`, không có GSS `acceptSecContext`, không có session key/keytab, không có Kerberos protocol. Mã này **không được dùng làm authentication provider trong production**.

Tệp **KerberosProviderPathsDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class KerberosProviderPathsDemo {
    private static final String HTTP_SPN =
        "HTTP/portal.example.test@EXAMPLE.TEST";
    private static final Instant NOW =
        Instant.parse("2026-01-01T10:00:00Z");

    sealed interface Request permits PasswordRequest, TicketRequest {}

    record PasswordRequest(String user, char[] password)
            implements Request {}

    // Trusted metadata of a MOCK GSS verifier; never accept these fields
    // from an HTTP client in production.
    record TicketProof(String ticketId, String user, String spn,
                       Instant expiresAt, boolean cryptographicallyVerified,
                       String authenticatorId) {}
    record TicketRequest(TicketProof proof) implements Request {}

    record Account(boolean enabled, Set<String> roles) {}
    record Decision(boolean authenticated, String path,
                    String principal, Set<String> roles) {
        static Decision deny(String path) {
            return new Decision(false, path, "", Set.of());
        }
    }

    interface Provider {
        boolean supports(Request request);
        Decision authenticate(Request request);
    }

    static final Map<String, Account> ACCOUNTS = Map.of(
        "alice@EXAMPLE.TEST", new Account(
            true, Set.of("ROLE_REPORT_READER")),
        "disabled@EXAMPLE.TEST", new Account(
            false, Set.of("ROLE_REPORT_READER"))
    );

    static Decision allowLocalUser(String user, String path) {
        Account account = ACCOUNTS.get(user);
        if (account == null || !account.enabled()) {
            return Decision.deny(path);
        }
        return new Decision(true, path, user, account.roles());
    }

    static final class MockKdc {
        boolean login(String user, char[] password) {
            // Deliberately fake lab data. Production uses JAAS/KDC, not
            // a hard-coded local password or Arrays.equals.
            return (user.equals("alice@EXAMPLE.TEST")
                    || user.equals("disabled@EXAMPLE.TEST"))
                && Arrays.equals(password, "lab-secret".toCharArray());
        }
    }

    static final class PasswordProvider implements Provider {
        private final MockKdc kdc = new MockKdc();
        @Override public boolean supports(Request r) {
            return r instanceof PasswordRequest;
        }
        @Override public Decision authenticate(Request request) {
            if (!supports(request)) return Decision.deny("password");
            PasswordRequest r = (PasswordRequest) request;
            try {
                if (r.user() == null || r.password() == null
                        || !kdc.login(r.user(), r.password())) {
                    return Decision.deny("password");
                }
                return allowLocalUser(r.user(), "password");
            } finally {
                if (r.password() != null) {
                    Arrays.fill(r.password(), '\0');
                }
            }
        }
    }

    static final class MockGssAcceptor {
        private final Set<String> replayCache =
            ConcurrentHashMap.newKeySet();

        String validate(TicketProof p) {
            if (p == null || !p.cryptographicallyVerified()
                    || !HTTP_SPN.equals(p.spn())
                    || p.ticketId() == null || p.ticketId().isBlank()
                    || p.user() == null || p.user().isBlank()
                    || p.expiresAt() == null
                    || !NOW.isBefore(p.expiresAt())
                    || p.authenticatorId() == null
                    || p.authenticatorId().isBlank()) {
                return null;
            }
            // A real acceptor checks AP-REQ, session-key proof,
            // timestamp, service keytab, realm and GSS replay cache.
            if (!replayCache.add(
                    p.ticketId() + "/" + p.authenticatorId())) {
                return null;
            }
            return p.user();
        }
    }

    static final class ServiceTicketProvider implements Provider {
        private final MockGssAcceptor gss = new MockGssAcceptor();
        @Override public boolean supports(Request request) {
            return request instanceof TicketRequest;
        }
        @Override public Decision authenticate(Request request) {
            if (!supports(request)) return Decision.deny("service-ticket");
            String user = gss.validate(((TicketRequest) request).proof());
            return user == null ? Decision.deny("service-ticket")
                : allowLocalUser(user, "service-ticket");
        }
    }

    static final class ProviderManagerMock {
        private final Provider passwordProvider = new PasswordProvider();
        private final Provider ticketProvider = new ServiceTicketProvider();

        Decision authenticate(Request request) {
            if (passwordProvider.supports(request)) {
                return passwordProvider.authenticate(request);
            }
            if (ticketProvider.supports(request)) {
                return ticketProvider.authenticate(request);
            }
            return Decision.deny("unsupported");
        }
    }

    static TicketRequest ticket(
            String id, String user, String spn, boolean verified,
            String authenticator, Instant expiresAt) {
        return new TicketRequest(new TicketProof(
            id, user, spn, expiresAt, verified, authenticator));
    }

    public static void main(String[] args) {
        ProviderManagerMock manager = new ProviderManagerMock();
        PasswordProvider password = new PasswordProvider();
        ServiceTicketProvider service = new ServiceTicketProvider();

        TicketRequest initial = ticket(
            "st-1", "alice@EXAMPLE.TEST", HTTP_SPN, true,
            "auth-1", NOW.plus(Duration.ofMinutes(15)));
        System.out.println("formProviderSupportsPassword=" +
            password.supports(new PasswordRequest(
                "alice@EXAMPLE.TEST", new char[0])));
        System.out.println("formProviderDoesNotSupportTicket=" +
            !password.supports(initial));
        System.out.println("serviceProviderSupportsTicket=" +
            service.supports(initial));
        System.out.println("serviceProviderDoesNotSupportPassword=" +
            !service.supports(new PasswordRequest(
                "alice@EXAMPLE.TEST", new char[0])));

        Decision form = manager.authenticate(
            new PasswordRequest(
                "alice@EXAMPLE.TEST", "lab-secret".toCharArray()));
        System.out.println("formLoginAccepted=" + form.authenticated());
        System.out.println("wrongPasswordRejected=" +
            !manager.authenticate(new PasswordRequest(
                "alice@EXAMPLE.TEST", "bad".toCharArray())).authenticated());
        System.out.println("serviceTicketAccepted=" +
            manager.authenticate(initial).authenticated());
        System.out.println("sameAuthenticatorReplayRejected=" +
            !manager.authenticate(initial).authenticated());
        System.out.println("sameTicketFreshAuthenticatorAccepted=" +
            manager.authenticate(ticket(
                "st-1", "alice@EXAMPLE.TEST", HTTP_SPN, true,
                "auth-2", NOW.plusSeconds(900))).authenticated());
        System.out.println("tgtWrongSpnRejected=" +
            !manager.authenticate(ticket(
                "tgt-1", "alice@EXAMPLE.TEST",
                "krbtgt/EXAMPLE.TEST@EXAMPLE.TEST", true,
                "auth-tgt", NOW.plusSeconds(900))).authenticated());
        System.out.println("wrongServiceRejected=" +
            !manager.authenticate(ticket(
                "st-cifs", "alice@EXAMPLE.TEST",
                "cifs/files.example.test@EXAMPLE.TEST", true,
                "auth-cifs", NOW.plusSeconds(900))).authenticated());
        System.out.println("expiredTicketRejected=" +
            !manager.authenticate(ticket(
                "st-expired", "alice@EXAMPLE.TEST", HTTP_SPN, true,
                "auth-old", NOW.minusSeconds(1))).authenticated());
        System.out.println("fakeProofRejected=" +
            !manager.authenticate(ticket(
                "st-fake", "alice@EXAMPLE.TEST", HTTP_SPN, false,
                "auth-fake", NOW.plusSeconds(900))).authenticated());
        System.out.println("unknownLocalUserRejected=" +
            !manager.authenticate(ticket(
                "st-unknown", "unknown@EXAMPLE.TEST", HTTP_SPN,
                true, "auth-unknown", NOW.plusSeconds(900)))
            .authenticated());
        System.out.println("disabledLocalUserRejected=" +
            !manager.authenticate(ticket(
                "st-disabled", "disabled@EXAMPLE.TEST", HTTP_SPN,
                true, "auth-disabled", NOW.plusSeconds(900)))
            .authenticated());
        System.out.println("rolesComeFromLocalPolicy=" +
            form.roles().equals(Set.of("ROLE_REPORT_READER")));
        System.out.println("providerTypeConfusionRejected=" +
            !password.authenticate(ticket(
                "st-2", "alice@EXAMPLE.TEST", HTTP_SPN, true,
                "auth-3", NOW.plusSeconds(900))).authenticated());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 KerberosProviderPathsDemo.java
java KerberosProviderPathsDemo
~~~

**Stdout chính xác** (đã biên dịch và chạy với JDK 17):

~~~text
formProviderSupportsPassword=true
formProviderDoesNotSupportTicket=true
serviceProviderSupportsTicket=true
serviceProviderDoesNotSupportPassword=true
formLoginAccepted=true
wrongPasswordRejected=true
serviceTicketAccepted=true
sameAuthenticatorReplayRejected=true
sameTicketFreshAuthenticatorAccepted=true
tgtWrongSpnRejected=true
wrongServiceRejected=true
expiredTicketRejected=true
fakeProofRejected=true
unknownLocalUserRejected=true
disabledLocalUserRejected=true
rolesComeFromLocalPolicy=true
providerTypeConfusionRejected=true
~~~

### 15.1. Diễn giải kết quả

- **formProviderSupportsPassword=true**: password provider chỉ nhận request đúng kiểu.
- **serviceProviderSupportsTicket=true**: service-ticket provider nhận ticket request.
- **formProviderDoesNotSupportTicket=true** và **serviceProviderDoesNotSupportPassword=true**: đường authentication được phân biệt, không đưa nhầm bằng chứng tới provider.
- **formLoginAccepted=true**: password đúng trong **mock KDC** và local user enabled.
- **wrongPasswordRejected=true**: sai password không được xác thực.
- **serviceTicketAccepted=true**: service-ticket mock validation hợp lệ với service principal HTTP.
- **sameAuthenticatorReplayRejected=true**: replay cùng authenticator bị từ chối.
- **sameTicketFreshAuthenticatorAccepted=true**: cùng service ticket còn hạn có thể tham gia exchange mới với authenticator mới — khác với replay raw token.
- **tgtWrongSpnRejected=true**: web service từ chối credential dành cho `krbtgt`.
- **wrongServiceRejected=true**: ticket cho CIFS không dùng tại Portal.
- **expiredTicketRejected=true** và **fakeProofRejected=true**: không dùng token không hợp lệ.
- **unknownLocalUserRejected=true** và **disabledLocalUserRejected=true**: đã xác minh Kerberos vẫn phải qua local user policy.
- **rolesComeFromLocalPolicy=true**: authorities đến từ allowlist của ứng dụng.
- **providerTypeConfusionRejected=true**: password provider không nhận token kiểu service ticket.

**Mã này không chứng minh actual Spring Security providers đã chạy**; nó kiểm **kiến trúc phân luồng và các trường hợp từ chối**. Phải có integration tests với KDC/SPNEGO thật khi triển khai production.

## 16. Test hỗn hợp hai phương thức trong cùng ứng dụng

Một số lỗi chỉ xuất hiện khi có **cả hai providers**:

### 16.1. Form-login gửi sai kiểu Authentication

Nếu custom controller tạo `KerberosServiceRequestToken` từ username/password thay vì `UsernamePasswordAuthenticationToken`, service ticket provider sẽ được chọn sai. Nó có thể ném GSSException vì nhận text không phải GSS token. **Không chữa bằng cách chuyển password thành bytes rồi giả một SPNEGO token**. Form-login phải dùng đúng authentication request và provider password.

### 16.2. Header Negotiate bị route qua password provider

Nếu custom filter biến chuỗi Base64 token thành username, nó sẽ bypass bằng chứng Kerberos thực và đưa user “không password” cho KDC login. **Không làm điều này.** SPNEGO filter cần chuyển **raw token bytes** đến `KerberosServiceRequestToken` và service-ticket provider.

### 16.3. Form fallback mở khi KDC unavailable

Một lỗi chính sách có thể xảy ra nếu bạn đăng ký `DaoAuthenticationProvider` local cạnh `KerberosAuthenticationProvider` và cho fallback khi Kerberos KDC lỗi. Lúc này một user có local password có thể đăng nhập **không qua KDC** dù tổ chức dự kiến KDC là bắt buộc. Nếu fallback được phép, phải có policy, MFA/assurance và account ownership được phê duyệt, không chỉ “provider tiếp theo thử tiếp”.

### 16.4. SPNEGO thất bại rồi tự động cấp anonymous permissions

Một 401 Negotiate khi browser không có TGT không nên trở thành **200 OK với ROLE_USER**. Nếu có fallback form, form chỉ được hiển thị/cho đăng nhập sau **một luồng xác thực hợp lệ mới**. Không tạo Authentication từ thông tin browser chưa kiểm chứng.

### 16.5. Session từ provider A chuyển sang provider B

Một user có thể đăng nhập bằng form rồi sau đó gửi Negotiate với principal khác (ví dụ thiết bị đang login một domain account khác). Cần quyết định policy:

- Giữ session authenticated hiện tại hay thay principal?
- Nếu thay, có yêu cầu logout/login lại hoặc confirmation không?
- Có thể bị session fixation hoặc account confusion không?
- Có cần `setSkipIfAlreadyAuthenticated(true)` cho SpnegoAuthenticationProcessingFilter không?
- Phải audit account switching và quyền của tenant nào đang có hiệu lực?

Đây là quyết định bảo mật **tùy sản phẩm**. Không để filter SPNEGO vô tình overwrite một session của user khác rồi giữ local authorities cũ.

### 16.6. Nhiều browser và client types

Ứng dụng có thể phục vụ:

- Chrome/Edge managed domain: SPNEGO.
- Firefox/Chrome ngoài domain: form.
- Mobile/API clients: bearer token hoặc phương án khác, không mặc định Negotiate.
- Reverse proxy: có hoặc không terminate Kerberos, cần trust boundary rõ.

Một global `SpnegoEntryPoint` cho mọi endpoint có thể làm API trả 401 Negotiate trong khi client đang mong Bearer challenge; cân nhắc multiple SecurityFilterChain với matchers, entry points/authorization policies riêng.

## 17. Chẩn đoán lỗi theo đường provider

| Triệu chứng | Provider liên quan | Khả năng chính | Kiểm tra an toàn |
| --- | --- | --- | --- |
| Form login thất bại dù browser SPNEGO hoạt động | Password provider | KDC/JAAS username-password path khác credential cache đã có | KerberosClient/KDC logs, realm, username format |
| Form trả bad credentials | Password provider | Password sai, KDC từ chối, principal không hợp lệ | Auth logs đã lọc, KDC codes |
| Form login không gọi KDC | Password path/config | Form provider không được gắn manager; Dao provider bắt request trước | ProviderManager, supports/ordering |
| Form success nhưng user bị khóa | UserDetails/local auth | Chưa thực thi enabled/locked policy | UserDetailsService, account status |
| GET /private trả 302 /login thay vì 401 Negotiate | SPNEGO entrypoint | EntryPoint/form override | SecurityFilterChain và entry point |
| 401 Negotiate nhưng browser không gửi token | Client | Browser policy, không có TGT, site không được Integrated Auth | Klist, browser enterprise policy |
| Authorization: Negotiate có mà tiếp tục 401 | Service ticket provider | SPN/keytab/KVNO/enctype/GSS issue | Validator, keytab, AD SPN, GSS logs |
| `KDC_ERR_S_PRINCIPAL_UNKNOWN` | Client TGS exchange | SPN không có tại KDC | `kvno` và service account mapping |
| `KRB_AP_ERR_MODIFIED` | Service acceptor | Keytab/SPN/KVNO lệch, duplicate AD SPN | KDC principal/keytab/AD |
| `KRB_AP_ERR_REPEAT` | Service acceptor | Authenticator replay/GSS context bị tái submit | Replay cache, duplicated token handling |
| `KRB_AP_ERR_SKEW` | Kerberos | Clock lệch quá policy | NTP KDC/client/server |
| `KRB_AP_ERR_TKT_EXPIRED` | Service acceptor | Service ticket hết hạn | Klist, ticket times, policy |
| `GSSException: No valid credentials provided` | Service acceptor | Keytab thiếu hoặc JVM không đọc được | Path, filesystem owner/permissions |
| `GSSException: Defective token` | SPNEGO | Token bị sửa, sai mechanism/format, proxy làm hỏng header | Header flow, mech, client/server versions |
| `GSSException: Channel binding mismatch` | SPNEGO/TLS | CBT/Extended Protection không đồng nhất TLS termination | Security/AD/TLS policy, không bypass |
| NTLM fallback | Browser/SSPI | Không thể Kerberos SPN hoặc client policy | Actual mech, Windows policy |
| Form success, SPNEGO fail chỉ production | Service keytab/SPN | Form không dùng acceptor keytab; SPNEGO có | Keytab/host/KVNO/ingress |
| SPNEGO success, form fail | KDC/JAAS/password | Có cached Kerberos credentials nhưng password path không đúng | KDC login path, policy, user input |
| Hai phương thức đều xác thực, API 403 | Local authorization | UserDetails/roles/resource policy từ chối | Authorities, tenant membership |
| User account bị đổi sau lần Negotiate | Session handling | Filter reauth với principal khác hoặc session reused | SkipIfAlreadyAuthenticated, session policy |
| Logout xong browser lại login ngay | OS credential cache | TGT/service ticket vẫn còn | Local logout vs domain SSO scope |
| Error sau service password rotate | Keytab KVNO | KDC phát ticket key mới, service vẫn key cũ | KVNO/enctype và rollout |
| Chỉ một replica lỗi | Keytab hoặc config không đồng nhất | Per-node mismatch | Deployment/node logs, secret version |

### 17.1. Một trình tự debug không lộ secrets

1. Ghi nhận endpoint là **form** hay **SPNEGO**.
2. Kiểm **request type** và provider hỗ trợ; log tên class/hạng mục, không log credentials.
3. Nếu form: kiểm `KerberosClient.login` có gọi KDC, realm/user format và xử lý lỗi JAAS.
4. Nếu SPNEGO: kiểm `WWW-Authenticate: Negotiate`, browser có `Authorization: Negotiate` và SPN mà client xin.
5. Dùng `klist`/`kvno` trên máy kiểm thử có quyền, không xuất raw tickets.
6. Trên service, kiểm `klist -k -t -e /run/secrets/kerberos/http.keytab`, owner và KVNO/enctype.
7. Kiểm clock skew, AD SPN ownership, realm trust, TLS termination/channel binding.
8. Nếu Kerberos validation thành công nhưng app không login, kiểm `UserDetailsService` và session persistence.
9. Nếu Authentication có nhưng 403, kiểm local authorities/tenant/resource ACL; không hạ bảo mật Kerberos.
10. Không sửa bằng cách tắt replay, tin HTTP header hoặc lưu password trong log.

### 17.2. Log ví dụ

~~~text
event=AUTH_FAILED
authPath=SPNEGO
requestTokenClass=KerberosServiceRequestToken
provider=KerberosServiceAuthenticationProvider
servicePrincipal=HTTP/portal.example.test@EXAMPLE.TEST
reason=SPN_OR_KEYTAB_MISMATCH
traceId=trace-a3b5
~~~

Với form path:

~~~text
event=AUTH_FAILED
authPath=FORM_KERBEROS
requestTokenClass=UsernamePasswordAuthenticationToken
provider=KerberosAuthenticationProvider
reason=KERBEROS_LOGIN_REJECTED
traceId=trace-f02d
~~~

Không log `Authorization: Negotiate`, Base64/GSS tokens, raw password, JAAS Subject, keytab bytes, TGT/service session keys hoặc stack trace nhạy cảm ra public APM.

## 18. Negative test matrix

| Ca kiểm thử | Input | Kết quả đúng |
| --- | --- | --- |
| Form hợp lệ | username/password được KDC chấp nhận, local user active | PASS |
| Form sai password | Password sai | FAIL |
| Form không có password | Missing credential | FAIL |
| KDC offline với form | KerberosClient không kết nối AS/realm | FAIL an toàn; không fallback provider yếu ngoài policy |
| SPNEGO hợp lệ | GSS token dành đúng SPN, keytab khớp | PASS |
| User chưa có TGT | Browser không có credential cache | 401/fallback theo policy, không tạo user |
| Raw token giả | Base64 không phải GSS/AP-REQ hợp lệ | FAIL |
| TGT dùng làm web credential | Principal `krbtgt` thay HTTP | FAIL |
| Ticket CIFS vào HTTP | `cifs/files` ticket | FAIL |
| SPN host sai | Client lấy ticket HTTP/internal nhưng app HTTP/public | FAIL |
| KVNO/keytab mismatch | Service key khác key KDC cấp | FAIL |
| Enctype mismatch | Server không có compatible key | FAIL |
| Ticket expired | Kerberos endtime đã qua | FAIL |
| Authenticator stale | Timestamp vượt clock skew | FAIL |
| Replay raw token | Re-submit cùng AP-REQ/authenticator | FAIL |
| Service ticket hợp lệ + fresh authenticator | Exchange mới hợp lệ trong lifetime | Có thể PASS theo Kerberos semantics |
| Wrong realm | Identity không thuộc trusted realm | FAIL hoặc identity scoped theo policy |
| NTLM fallback khi policy chỉ Kerberos | Negotiate chọn NTLM | FAIL policy |
| Form request gửi đến ticket provider | Request type không hỗ trợ | Không authenticate |
| Ticket request gửi đến password provider | Request type không hỗ trợ | Không authenticate |
| User local unknown | KDC/GSS xác thực nhưng không có local account, JIT disabled | FAIL |
| User local disabled | KDC/GSS xác thực nhưng local disabled | FAIL |
| User không có role | Auth thành công, resource requires role | 403; không nâng quyền |
| Principal switch giữa hai methods | Form alice, SPNEGO bob trên cùng browser | Có chính sách reauth/session switch rõ |
| Provider order mismatch | Kerberos + Dao đều supports username/password | Test precedence/fallback |
| Form disabled CSRF | POST /login không bảo vệ | Security test FAIL |
| Password in access logs | Request body/URL bị ghi | Security test FAIL |
| GSS token in logs | Authorization header lộ | Security test FAIL |
| Keytab trong repo/container image | Secret bị commit/bundled | Security test FAIL |
| Duplicate SPN AD | Cùng SPN nhiều service accounts | Fail/điều tra |
| HTTP không TLS | Dùng Negotiate nhưng body/cookie không được bảo vệ | Security policy FAIL |
| Proxy spoof identity | Client tự gửi `X-Remote-User: alice` | Không được dùng thay GSS |
| Session fixation | Session ID không đổi sau login theo policy | Test và sửa session strategy |
| Logout local | Session Spring xóa nhưng OS ticket còn | Có thể tự SPNEGO lại; không khẳng định domain logout |
| Multi-node mismatch | Một instance keytab cũ | Test theo node, không mở bypass |

**Test integration thật** với KDC/AD test environment là bắt buộc trước production: unit tests mô phỏng chỉ kiểm routing và business logic, không xác minh JAAS/GSS keys/tickets thật.

## 19. Khi nào nên chọn kiến trúc nào?

### 19.1. Chỉ dùng SPNEGO service-ticket provider

Phù hợp khi:

- Ứng dụng internal intranet, tất cả clients có enterprise Kerberos credentials.
- Mục tiêu không nhận user passwords tại ứng dụng.
- Domain SPN/keytab được IT quản lý và browsers hỗ trợ Integrated Auth.
- Không yêu cầu custom form fallback hoặc dùng fallback ở một access gateway khác.

Lợi ích: giảm nơi nhập mật khẩu; domain SSO hiệu quả. Chi phí: cần SPN/keytab, browser policy, clock/realm/GSS troubleshooting.

### 19.2. Chỉ dùng KerberosAuthenticationProvider

Phù hợp khi:

- User cần đăng nhập từ máy không có integrated browser auth.
- Tổ chức cho phép app kiểm username/password qua Kerberos KDC.
- Password flow có bảo vệ HTTPS, CSRF, rate limit và logs tốt.
- Không muốn hoặc chưa thể cấp service SPN/keytab cho HTTP SPNEGO.

Lợi ích: không phụ thuộc browser Negotiate. Chi phí: app nhận user passwords, cần quản trị credential risk, có thể làm giảm mục tiêu passwordless SSO.

### 19.3. Kết hợp cả hai

Phù hợp khi:

- Một nhóm users đã join domain và một nhóm khác không.
- Có explicit security policy cho form fallback.
- App có thể quản lý hai authentication methods mà không tự mở provider downgrade.

Yêu cầu: định nghĩa rõ loại authentication, thứ tự provider, entry point, session behavior, account linking, user authority mapping và test các trường hợp failover.

### 19.4. Thay thế bằng OIDC/SAML broker?

Nếu doanh nghiệp muốn giảm việc ứng dụng web trực tiếp xử lý KDC/password/SPNEGO, có thể đặt identity provider/broker chuyên trách, rồi app dùng **OIDC Authorization Code** hoặc **SAML**. Khi đó ứng dụng không cần cả hai Kerberos providers, nhưng broker/gateway phải đảm nhiệm ranh giới Kerberos. **Đó là kiến trúc khác**, không phải đơn giản đổi class AuthenticationProvider.

## 20. Checklist code review và vận hành

- [ ] Đã mô tả rõ hai luồng: **username/password** và **SPNEGO service ticket**.
- [ ] `KerberosAuthenticationProvider` được cấu hình với `KerberosClient`, ví dụ `SunJaasKerberosClient`.
- [ ] `KerberosServiceAuthenticationProvider` được cấu hình với `KerberosTicketValidator`, ví dụ `SunJaasKerberosTicketValidator`.
- [ ] `SpnegoAuthenticationProcessingFilter` chuyển token Negotiate thành `KerberosServiceRequestToken` và vào đúng AuthenticationManager.
- [ ] `UsernamePasswordAuthenticationFilter`/formLogin chuyển username/password vào đúng password provider.
- [ ] Không tự dùng service ticket như password hoặc dùng TGT làm web session credential.
- [ ] Đã kiểm `ProviderManager.supports`, thứ tự providers và fallback policy với cả hai request types.
- [ ] Nếu có Dao/LDAP khác cùng hỗ trợ password request, đã test downgrade/KDC unavailable.
- [ ] `SpnegoEntryPoint` trả 401 Negotiate và optional forward form đúng, không tạo redirect loop.
- [ ] Form login dùng HTTPS/CSRF/rate limiting; không ghi password/JAAS Subject.
- [ ] SPNEGO dùng đúng `HTTP/public-host@REALM` và service keytab có KVNO/enctype hợp lệ.
- [ ] Không commit keytab hoặc lưu keys trong classpath/JAR/image.
- [ ] GSS acceptor kiểm ticket, authenticator, replay, clock skew, principal/realm và SPN theo policy.
- [ ] Nếu yêu cầu Kerberos, đã test tránh NTLM fallback không mong muốn.
- [ ] SecurityContextRepository/stateful session đã được cấu hình cho SPNEGO filter, tránh auth thành công nhưng request sau anonymous.
- [ ] Session fixation policy được áp cho cả form và SPNEGO.
- [ ] Local UserDetailsService kiểm user active, roles/tenant; không gán mọi KDC user thành admin.
- [ ] Không re-authenticate lại một `KerberosServiceRequestToken` đã authenticated/đã dùng.
- [ ] Multi-tenant/cross-realm identity keys không gộp cùng username ở hai realms.
- [ ] Authentication success không tự thành authorization cho mọi business endpoints.
- [ ] Reverse proxy không cho client spoof `Authorization`/`X-Remote-User` và TLS channel binding được thiết kế.
- [ ] Các OS credential caches, user TGT, service tickets và Spring local sessions có vòng đời được giải thích rõ.
- [ ] Local logout không hứa xóa Kerberos credentials của OS/domain.
- [ ] Tài liệu Maven/Gradle dùng đúng group/version Spring Security Kerberos 6.x hay 7.x.
- [ ] Có integration tests với KDC/keytab, form, browser Negotiate và negative cases.
- [ ] Có monitoring riêng cho `FORM_KERBEROS` và `SPNEGO_SERVICE_TICKET`, log không chứa raw credentials.
- [ ] Có kế hoạch rotate service keytab, cập nhật KVNO, rollback và đo lỗi theo replica.
- [ ] Có runbook KDC offline, clock skew, duplicate SPN, browser policy và session/account confusion.

## 21. Câu hỏi tự kiểm tra

**1. KerberosAuthenticationProvider và KerberosServiceAuthenticationProvider khác nhau ở bước xác thực nào?**

Một bên xác minh **username/password** qua `KerberosClient`; bên kia xác minh **SPNEGO/service ticket** qua `KerberosTicketValidator` với keytab/service principal.

**2. Vì sao cài KerberosAuthenticationProvider không đủ để browser tự SSO qua Negotiate?**

Vì browser gửi GSS token, không gửi password. Cần `SpnegoAuthenticationProcessingFilter`, `KerberosServiceAuthenticationProvider`, TicketValidator và keytab.

**3. KerberosServiceAuthenticationProvider có cần password của Alice không?**

Không. Nó là service acceptor kiểm Kerberos AP-REQ bằng service credentials, rồi lấy principal qua GSS validation.

**4. Vì sao password provider lại cần KerberosClient?**

Để ứng dụng kiểm username/password với KDC bằng Kerberos/JAAS, thay vì tự so mật khẩu local.

**5. Hai provider có dùng chung UserDetailsService được không?**

Có. Sau khi từng phương thức xác minh identity, có thể nạp chung local user/roles với policy nhất quán theo realm/tenant.

**6. `KerberosServiceRequestToken` có phải TGT không?**

Không. Nó là Authentication object Spring Security chứa GSS/SPNEGO token cho service acceptor; TGT nằm ở client credential cache/KDC TGS exchange.

**7. SPNEGO token ở header có thể parse Base64 để lấy username rồi tin ngay không?**

Không. Phải qua GSS/KerberosTicketValidator. Base64 chỉ là transport encoding, không chứng minh token hợp lệ.

**8. `supports(UsernamePasswordAuthenticationToken.class)` có nghĩa password đúng không?**

Không. `supports` chỉ cho biết provider có khả năng xử lý request type. `authenticate` mới quyết định kết quả sau KerberosClient/KDC validation.

**9. Vì sao form success nhưng SPNEGO vẫn lỗi sau khi đổi service account password?**

SPNEGO cần keytab/KVNO khớp service key KDC mới, còn form username/password đi qua KerberosClient path khác. Một đường chạy không chứng minh đường còn lại đúng.

**10. Nếu browser gửi ticket của CIFS đến website HTTP, có thể đăng nhập không?**

Không. Kerberos service ticket ràng buộc với SPN; service acceptor phải từ chối ticket không dành cho mình.

**11. Service ticket Kerberos có chỉ sử dụng được một lần không?**

Không theo nghĩa của CAS ST. Kerberos service ticket có thể dùng cho AP exchanges khác khi còn hạn, nhưng **authenticator/GSS token replay** phải bị phát hiện và từ chối.

**12. Vì sao authenticated Kerberos user có thể vẫn gặp HTTP 403?**

Vì local UserDetailsService/authorities hoặc resource authorization không cho user thực hiện tác vụ. Authentication không đồng nghĩa authorization.

**13. Có nên bật form fallback khi KDC không reachable không?**

Chỉ khi security policy đã cho phép và cơ chế fallback có assurance tương đương hoặc được quản lý. Không để provider order tạo downgrade ngoài ý muốn.

**14. Phải bảo vệ loại secret nào ở hai phương thức?**

Form phải bảo vệ user password/JAAS Subject; SPNEGO phải bảo vệ service keytab và raw GSS tokens. Cả hai cần TLS, session security và audit.

**15. Nếu có SpnegoEntryPoint("/login"), browser luôn nhận HTTP 302 đến form không?**

Không. Theo Javadoc, nó gửi **401 Negotiate** và có tùy chọn **forwardUrl** đến form fallback; không nên nhầm với một redirect 302 đơn giản.

**16. Khi local logout, người dùng có thể tự đăng nhập lại qua SPNEGO ngay không?**

Có thể, vì OS Kerberos TGT/service ticket vẫn còn. Local HttpSession logout khác domain sign-out.

**17. Vì sao UserDetailsService không được tự quyết định KDC credentials hợp lệ?**

Nó phục vụ local user mapping/authorities. Bằng chứng Kerberos phải được **KerberosClient** hoặc **KerberosTicketValidator** xác minh trước.

**18. Khi nào nên cân nhắc OIDC thay vì hai Kerberos providers?**

Khi ứng dụng muốn giao việc tích hợp KDC/SSO cho identity broker chuyên trách. Broker xác thực Kerberos, còn app làm OIDC RP; đây là thiết kế federation khác.

## 22. Tài liệu chính thức để đối chiếu

- Spring Security, **Spring and Spring Security Kerberos**, phần Authentication Provider, Spnego Negotiate, mẫu phối hợp hai provider: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Spring Security, **Introduction to Kerberos**, dependency coordinates Spring Security 7, Java 17/version compatibility: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html
- Spring Security Javadoc, **KerberosAuthenticationProvider**, `setKerberosClient`, `setUserDetailsService` và `supports`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosAuthenticationProvider.html
- Spring Security Javadoc, **KerberosServiceAuthenticationProvider**, Kerberos service ticket/SPNEGO validation, `setTicketValidator`, UserDetailsService: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceAuthenticationProvider.html
- Spring Security Javadoc, **SunJaasKerberosClient**, `login(String username, String password)` sử dụng JAAS: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/sun/SunJaasKerberosClient.html
- Spring Security Javadoc, **KerberosServiceRequestToken**, unauthenticated byte token, authenticated validation result, cảnh báo re-authenticate: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosServiceRequestToken.html
- Spring Security Javadoc, **KerberosUsernamePasswordAuthenticationToken**, JaasSubjectHolder cho multi-tier: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/authentication/KerberosUsernamePasswordAuthenticationToken.html
- Spring Security Javadoc, **SpnegoAuthenticationProcessingFilter**, đọc header và gắn SecurityContextRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html
- Spring Security Javadoc, **SpnegoEntryPoint**, 401 Negotiate và forward form fallback: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html
- Spring Security, **Authentication Architecture**, ProviderManager, supports(), order/providers: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- IETF **RFC 4120, Kerberos V5**, AS/TGS/AP exchange, service ticket, authenticator/replay: https://www.rfc-editor.org/rfc/rfc4120
- IETF **RFC 4559, SPNEGO-based Kerberos and NTLM HTTP Authentication**, `Authorization: Negotiate` và 401 challenge: https://www.rfc-editor.org/rfc/rfc4559
- MIT Kerberos, **kinit** và **klist**, credential cache/service principal troubleshooting: https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kinit.html và https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/klist.html

**Tóm kết:** **`KerberosAuthenticationProvider` kiểm username/password bằng `KerberosClient`**, thích hợp form login/KDC verification. **`KerberosServiceAuthenticationProvider` kiểm service ticket/SPNEGO bằng `KerberosTicketValidator` và service keytab**, thích hợp browser Integrated Authentication. Chọn provider theo **kiểu request và ranh giới tin cậy**, không theo tên “Kerberos” chung. Sau cả hai, Spring Security vẫn phải nạp **local user/authorities**, lưu SecurityContext phù hợp và kiểm **authorization nghiệp vụ**; không bao giờ tin raw header/token hoặc user input chưa được xác minh.