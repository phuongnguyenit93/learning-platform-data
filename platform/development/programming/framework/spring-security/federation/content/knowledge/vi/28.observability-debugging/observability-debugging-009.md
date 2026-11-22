# Chẩn đoán SPNEGO không được thương lượng và service principal không khớp

> **Module:** Spring Security – federation. **Nhóm:** Quan sát và gỡ lỗi. **Tình huống:** Một ứng dụng Spring Security bảo vệ §https://portal.example.org/private§ bằng HTTP Negotiate/Kerberos, nhưng browser chỉ hiện trang login hoặc trả §401§ lặp lại. Hoặc browser đã gửi token mà Java/JGSS báo sai service principal/keytab. Bài học đưa ra **phương pháp thu thập bằng chứng theo từng hop** để không nhầm lỗi HTTP challenge, browser policy, KDC/SPN, keytab, TLS channel binding và application authorization. Ví dụ ưu tiên **Java 17**, Spring Security Kerberos extension và Active Directory/MIT Kerberos; không dùng thông tin bí mật sản xuất trong test.

## 1. Mục tiêu học tập và điều kiện nền

Sau bài học, bạn phải làm được:

1. Giải thích handshake §401 WWW-Authenticate: Negotiate§ / §Authorization: Negotiate ...§, nhận ra khi nào **browser không thương lượng** và khi nào **đã thương lượng nhưng vé không xác thực được**.
2. Tách §401§ của **origin server** khỏi §407 Proxy Authentication Required§ của explicit proxy; xác định điểm chặn tại CDN/ingress/WAF/reverse proxy.
3. Chẩn đoán bốn lỗi tách biệt: **không có challenge**, **browser không gửi token**, **KDC không phát ticket cho SPN**, **acceptor không giải được ticket cho SPN**.
4. Tìm đúng §HTTP/portal.example.org@EXAMPLE.ORG§ từ URL công khai; không dùng nhầm §HTTP/node-7.internal§ hoặc tài khoản máy.
5. Kiểm DNS canonicalization, CNAME/alias, Kerberos realm, SPN unique trong AD, keytab principal/KVNO/enctype và quyền file trong container.
6. Hiểu các triệu chứng §KDC_ERR_S_PRINCIPAL_UNKNOWN§, §KDC_ERR_PRINCIPAL_NOT_UNIQUE§, §KRB_AP_ERR_MODIFIED§, §KRB_AP_ERR_SKEW§, §KDC_ERR_ETYPE_NOTSUPP§, §GSSException: No valid credentials§ và khả năng NTLM fallback.
7. Phân biệt vai **client initiator** xin service ticket với **server acceptor** dùng JAAS/keytab để kiểm ticket; không lấy TGT user ở Portal để “sửa lỗi login”.
8. Cấu hình và quan sát §SpnegoEntryPoint§, §SpnegoAuthenticationProcessingFilter§, §KerberosServiceAuthenticationProvider§, §SunJaasKerberosTicketValidator§ và Spring Security filter chains theo version.
9. Dùng các lệnh đọc metadata an toàn §curl§, §klist§, §kvno§, §setspn -Q§, §klist -k -e§ và Java 17 demo để khoanh vùng lỗi; không log raw token/key.
10. Thiết kế negative tests và lập runbook điều tra có Expected/Actual, bảo vệ bí mật và nguyên tắc **fail closed**.

**Kiến thức cần có:** HTTP 401/403/407, TLS/HTTPS, DNS FQDN, Kerberos KDC/AS/TGS/TGT/service ticket, realm/SPN, JAAS/JGSS, Java 17, Spring Security §SecurityFilterChain§, Active Directory hoặc MIT KDC.

**Phiên bản:** Spring Security Kerberos là **extension** cần thư viện tương thích; Spring Boot core không có switch chuẩn “bật SPNEGO”. API filter/validator và cách cấu hình có thể khác giữa version của Spring Security Kerberos. Đừng copy XML từ tài liệu Spring Security cũ vào Boot 3.5 mà không kiểm dependencies và integration test.

## 2. SPNEGO đúng phải trông như thế nào?

Một browser đã có Kerberos TGT ở domain và được phép Integrated Authentication tới §portal.example.org§:

~~~text
Browser                  Portal Spring/JGSS                KDC/AD
  |                              |                            |
  | GET /private                 |                            |
  |----------------------------->|                            |
  | 401 WWW-Authenticate: Negotiate                         |
  |<-----------------------------|                            |
  |                              |                            |
  | request ticket for HTTP/portal.example.org ------------->|
  |<-------------------------------------- service ticket ----|
  |                              |                            |
  | GET /private                 |                            |
  | Authorization: Negotiate <opaque-SPNEGO-token>            |
  |----------------------------->|                            |
  |                              |  GSS accept using keytab   |
  |                              |  map user + authorities    |
  | 200 (authorized) or 403      |                            |
  |<-----------------------------|                            |
~~~

Hai điểm cần phân biệt tuyệt đối:

- **Negotiate** là **HTTP authentication scheme**/SPNEGO negotiation. Thấy header §Authorization: Negotiate§ chưa chắc token chứa Kerberos; trên Windows, cơ chế Negotiate có thể fallback sang **NTLM** theo client policy. Java acceptor cấu hình Kerberos có thể không chấp nhận token NTLM. Hãy xác minh mechanism thực bằng công cụ/trace phù hợp đã sanitize.
- **Xác thực thành công** không tự đồng nghĩa HTTP 200. Nếu Spring đã xác thực §lan@EXAMPLE.ORG§ nhưng user thiếu §ROLE_REPORT_READER§, kết quả đúng là **403**. Đừng sửa SPN/keytab khi vấn đề là authorization.

Các cách để thấy khác biệt:
1. Chỉ có response §302 /login§ hoặc §401§ nhưng **không** §WWW-Authenticate: Negotiate§: vấn đề thường ở entry point, URL routing, filter chain, ingress hoặc policy chọn form login.
2. Có §401 Negotiate§ nhưng browser **không** gửi §Authorization: Negotiate§: browser/OS/zone/domain/credential acquisition hoặc proxy stripping header.
3. Browser gửi §Authorization: Negotiate§ nhưng 401 tiếp: server filter/validator/GSS/keytab, KDC service ticket/SPN, NTLM fallback, TLS channel binding, replay/clock skew.
4. GSS accept thành công, Spring principal có rồi nhưng §403§: business roles, account mapping, tenant/resource authorization.
5. §200§ sau form/Basic fallback: không chứng minh SPNEGO đã dùng Kerberos! Phải xem authentication mechanism/accepted principal từ server **đã xác minh**.

## 3. Khung quan sát: thu bằng chứng từ client tới server

Đừng sửa keytab ngay. Tạo một **correlation ID** cho lần gọi test, dùng một browser profile cô lập và request tới **protected endpoint** đã được biết phải yêu cầu Negotiate, ví dụ §/private§.

| Hop | Câu hỏi chẩn đoán | Bằng chứng tối thiểu |
| --- | --- | --- |
| Browser → edge | URL công khai, scheme/host/port/path là gì? | URL/Host đã chuẩn hóa, HTTP status |
| Edge → client | Response có §WWW-Authenticate: Negotiate§ không? | Header presence, không log ticket |
| Browser → edge | Browser có trả §Authorization: Negotiate§ không? | Chỉ **presence và scheme**, không raw value |
| Edge → app | Reverse proxy có chuyển nguyên Authorization header không? | Boolean presence ở ingress và ứng dụng |
| Browser → KDC | Browser có TGT và xin service ticket cho SPN nào? | Target service principal, KDC status, không xuất ticket bytes |
| KDC/AD | SPN tồn tại, unique và thuộc tài khoản service đúng không? | §setspn -Q§/DC event IDs |
| App JVM | Java đang đọc krb5.conf/JAAS/keytab nào? | Approved config paths, runtime UID |
| Acceptor | Keytab có principal/KVNO/enctype trùng ticket không? | Metadata §klist -k -e§ và GSS outcome |
| Spring | Filter/provider có nhận ticket, authentication principal có đúng không? | Result type + error category, không raw token |
| Authorization | User có quyền truy cập protected resource không? | 200 hoặc 403 theo policy, không tự bypass |

**Quan trọng:** Không gửi raw browser HAR, §Authorization§ token, §WWW-Authenticate§ token có payload, TGT/service ticket, KRB5CCNAME cache, keytab, password hoặc private key vào hệ thống log/chat. Chỉ thu metadata đã redact. §WWW-Authenticate: Negotiate§ có thể kèm token từ server trong vòng negotiation; không log toàn bộ giá trị header, chỉ scheme.

### 3.1. Baseline request không có cookie

Trong sandbox có TLS tin cậy:

~~~bash
# Không dùng -k để bỏ TLS verification.
# Không dùng --negotiate ở phép thử kiểm server challenge ban đầu.
curl --head --max-redirs 0 https://portal.example.org/private

# Hoặc dùng GET và chỉ lấy response headers, tránh log body nhạy cảm:
curl -sS -D /dev/stderr -o /dev/null \
  --max-redirs 0 https://portal.example.org/private
~~~

**Expected phụ thuộc routing:** Một protected endpoint chưa có authentication thường trả §401§ và §WWW-Authenticate: Negotiate§ nếu SPNEGO entry point được dùng. Nếu §302 Location: /login§, kiểm Spring entry point/form login priority; nếu §200§, có thể endpoint permitAll, session/cookie vẫn đi kèm, hoặc ingress bypass. §curl --head§ dùng HEAD nên có thể không cùng behavior với GET khi endpoint filter khác; so sánh GET và HEAD trước khi kết luận.

Không dùng §curl -v§/§--trace§ vào terminal được thu logs ở production khi nó có thể in bearer headers/cookies. Không lưu stdout của raw Negotiate tokens trong CI artifacts.

### 3.2. HTTP 401 khác HTTP 407

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Đây là **origin web server** yêu cầu xác thực. Nếu thấy:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Negotiate
~~~

thì có thể là **explicit HTTP proxy**, không phải Portal. Khi browser dùng proxy, có hai trust boundaries khác nhau: §Proxy-Authorization§ dành cho proxy và §Authorization§ dành cho Portal. Không đưa proxy credential tới origin hoặc ngược lại. Kiểm PAC/WPAD, proxy bypass list, VPN/corporate egress và nơi response thật được tạo.

### 3.3. Correlation: một trace cho một lần thử

Dùng một bản ghi đã sanitize:

~~~text
case=SPNEGO-CASE-17
browser_url=https://portal.example.org/private
response_status=401
www_authenticate_has_negotiate=true
client_sent_authorization_negotiate=false
ingress_forwarded_authorization=not_applicable
os_has_tgt=true
requested_spn=not_observed
spring_entry_point=SpnegoEntryPoint
outcome=CLIENT_TOKEN_MISSING
raw_token_logged=false
~~~

Đừng đưa raw §Authorization§/cookie vào record. Chỉ ghi hostname, principal alias và những IDs đã được allowlist theo security policy.

## 4. Decision tree theo nơi lỗi xuất hiện

~~~text
GET /private (browser chưa authenticated)
   |
   +-- Server không phát 401 WWW-Authenticate: Negotiate?
   |      -> Kiểm SecurityFilterChain, SpnegoEntryPoint, ingress/CDN
   |         /login redirect, permitAll, Basic/Form priority
   |
   +-- Server đã phát 401 Negotiate
           |
           +-- Browser không gửi Authorization: Negotiate?
           |      -> Browser allowlist/Integrated Auth, TGT, proxy, DNS,
           |         zone, KDC reachability, service ticket acquisition
           |
           +-- Browser gửi Authorization: Negotiate
                   |
                   +-- Header không tới backend?
                   |      -> Reverse proxy/WAF strips Authorization
                   |
                   +-- Header tới backend
                           |
                           +-- SPNEGO/NTLM mechanism mismatch?
                           |      -> Xác minh Kerberos vs NTLM
                           |
                           +-- KDC không biết target SPN?
                           |      -> SPN registration/realm/DNS
                           |
                           +-- Server không giải được ticket?
                           |      -> keytab principal, KVNO, enctype, UID,
                           |         TLS channel binding / SPN mismatch
                           |
                           +-- GSS pass, Spring auth fail?
                           |      -> Provider/UserDetailsService/roles
                           |
                           +-- Spring auth pass, HTTP 403?
                                  -> Business authorization/tenant/resource
~~~

**Không đánh đồng các branch:** §No service ticket issued§ và §service ticket issued but acceptor cannot decrypt§ có nguyên nhân và quyền sửa khác nhau. Người sửa AD SPN cũng khác người sửa Spring Security filter, Kubernetes mount hoặc client browser policy.

## 5. Nhánh A: Server không gửi Negotiate challenge

Một response §401§ không có §WWW-Authenticate: Negotiate§ **không phải SPNEGO handshake đúng**. Trước khi chạy §setspn§ hoặc mở keytab, xem filter chain:

- Endpoint §/private§ có thực sự §authenticated()§ không, hay §permitAll()§?
- Có nhiều §SecurityFilterChain§ với §@Order§ và §securityMatcher§ không? Request có rơi vào chain form login/Basic thay vì chain SPNEGO?
- §SpnegoEntryPoint§ có được đăng ký làm §AuthenticationEntryPoint§ cho protected URL không? Hay mặc định §LoginUrlAuthenticationEntryPoint§ redirect §/login§?
- §SpnegoAuthenticationProcessingFilter§ có nằm trong đúng filter chain và trước controller không? Một bean riêng không tự chèn filter vào chain.
- Một upstream Nginx/Apache/API Gateway có tạo §302§/§401§ trước khi request tới Spring không?
- CORS preflight §OPTIONS§, static assets và health endpoints có bị nhầm là protected GET không?
- Với session đã authenticated, Spring có thể trả 200 thay vì challenge. Dùng clean browser/curl **không cookies** để kiểm baseline.
- Nếu RP dùng OIDC/SAML cho cùng URL và security config ưu tiên cơ chế đó, §WWW-Authenticate: Negotiate§ sẽ không xuất hiện dù Java keytab vẫn đúng.

**Mẫu Bean tích hợp Spring Security Kerberos (mã fragment, KHÔNG phải app runnable độc lập):**

~~~java
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;

@Bean
SunJaasKerberosTicketValidator kerberosTicketValidator() {
    SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
    validator.setServicePrincipal("HTTP/portal.example.org@EXAMPLE.ORG");
    validator.setKeyTabLocation(
            new FileSystemResource("/run/secrets/kerberos/http-portal.keytab"));
    validator.setDebug(false);
    return validator;
}

@Bean
KerberosServiceAuthenticationProvider kerberosProvider(
        SunJaasKerberosTicketValidator validator,
        UserDetailsService users) {
    KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
    provider.setTicketValidator(validator);
    provider.setUserDetailsService(users);
    return provider;
}

@Bean
SpnegoEntryPoint spnegoEntryPoint() {
    return new SpnegoEntryPoint();
}

@Bean
SpnegoAuthenticationProcessingFilter spnegoFilter(
        AuthenticationManager manager) {
    SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
    filter.setAuthenticationManager(manager);
    return filter;
}
~~~

**Giới hạn:** Cần imports cho Spring annotations, §AuthenticationManager§/§UserDetailsService§, dependency Spring Security Kerberos phiên bản tương thích, §SecurityFilterChain§ gắn entry point/filter/provider, KDC, TLS, keytab và account mapping. Đừng copy fragment rồi kỳ vọng SPNEGO tự bật. Không có Spring Boot core property §spring.security.kerberos.enabled=true§ đảm bảo cấu hình toàn bộ.

**Ví dụ wiring ở mức ý tưởng** cho một chain chuyên SPNEGO:

~~~java
// Fragment cấu hình: xác nhận exact API và @Order theo phiên bản.
http
    .securityMatcher("/private/**")
    .authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .exceptionHandling(e -> e.authenticationEntryPoint(spnegoEntryPoint))
    .addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);
~~~

Nếu ứng dụng còn login HTML/OIDC ở URL khác, áp dụng §securityMatcher§/filter order có chủ đích. Đừng vô tình giữ một chain §permitAll()§ bắt hết §/private/**§ trước chain SPNEGO. Khi dùng filter custom, kiểm filter bean có bị Spring Boot auto-register một lần bên ngoài Spring Security và lại add vào SecurityFilterChain lần nữa hay không.

## 6. Nhánh B: Có challenge nhưng browser không gửi Authorization: Negotiate

Khi §401 WWW-Authenticate: Negotiate§ đã tới browser mà tiếp theo không có §Authorization: Negotiate§, **chưa có căn cứ nói keytab server sai**. Server chưa có ticket để kiểm. Kiểm client theo thứ tự:

1. User đã đăng nhập domain/có Kerberos TGT hợp lệ không?
2. FQDN của site có thuộc **Integrated Authentication allowlist/trusted zone** của browser/OS không?
3. Browser có được phép dùng Negotiate, và policy có hạn chế auth server whitelist không?
4. Truy cập bằng **FQDN** hay bằng IP/localhost/alias/cổng khác? Với Kerberos HTTP thường dựa trên FQDN.
5. Thiết bị có kết nối KDC/DC không (VPN, DNS SRV, time, port 88)? Browser ở Internet ngoài mạng có thể không lấy service ticket.
6. Có PAC/WPAD/HTTP proxy đưa ra 407, hoặc gửi ticket tới proxy thay vì Portal không?
7. Browser có chuyển sang NTLM/Basic theo policy mà Java Kerberos acceptor không hỗ trợ không?
8. Có redirect HTTP→HTTPS hoặc sang hostname khác làm thay đổi SPN mà client định xin không?
9. Có cross-site iframe, browser security restriction hoặc access policy cấm silent integrated authentication không?
10. Có CNAME/SPN canonicalization khiến browser xin ticket cho **host canonical khác** host mà server có keytab không?

### 6.1. Cấu hình browser: minh họa, phải kiểm policy hiện tại

- **Microsoft Edge/Chrome trên Windows:** Integrated Authentication có thể phụ thuộc OS intranet zone và chính sách enterprise browser. Chính sách như §AuthServerAllowlist§/allowlist máy chủ xác thực giúp xác định host nào được phép Negotiate; cần kiểm đúng policy đang áp dụng qua browser enterprise policy UI. Không mặc định mọi §*.example.org§ đều trusted.
- **Firefox:** các preferences như §network.negotiate-auth.trusted-uris§ và môi trường SSPI/GSS có thể quyết định host được chọn. Đối chiếu Firefox version, enterprise policy và security policy tổ chức; đừng thêm mọi domain công cộng.
- **Linux/macOS:** Browser cần GSS-API/OS Kerberos credentials và đúng §krb5.conf§/ticket cache; §kinit§/§klist§ có thể giúp kiểm source, nhưng không đảm bảo browser đang dùng đúng cache/session.
- **Incognito/private profile:** cookie isolation và policy authentication có thể khác browser bình thường; test hai chế độ và nêu setup thay vì chỉ report “401”.

### 6.2. Windows: kiểm ticket client trước khi đụng server

Trên máy Windows domain-joined, dùng command prompt test đã được phê duyệt:

~~~powershell
# Liệt kê TGT/service tickets đang có của Windows logon session.
klist

# Chỉ xóa ticket cache trong môi trường TEST nếu được cho phép:
# klist purge
# Lệnh purge có thể gây gián đoạn các SSO sessions khác.
~~~

§klist§ giúp nhận diện service ticket cho §HTTP/portal.example.org§ đã được cấp chưa. Không dùng §klist purge§ tùy tiện trên máy của user thật hoặc domain controller. Nếu client không xin được ticket, xem Event Viewer/DC events và KDC logs theo quyền của AD team.

### 6.3. Linux/MIT Kerberos: kiểm service-ticket acquisition

Nếu sandbox đã có TGT hợp lệ và được phép:

~~~bash
# Chỉ kiểm cache của user TEST, không đọc TGT production.
klist

# Yêu cầu ticket cho service principal mong đợi:
kvno HTTP/portal.example.org@EXAMPLE.ORG

# Kiểm ticket cache sau yêu cầu:
klist
~~~

§kvno§ hỏi KDC ticket cho SPN; nếu báo không tìm thấy principal, lỗi thường nằm ở KDC registration/realm mapping, **chưa phải** keytab acceptor. Nếu §kvno§ trả KVNO/ticket, vẫn **chưa chứng minh** Java acceptor decrypt được ticket. MIT tools và JDK có thể dùng config khác nhau: §KRB5_CONFIG§/§KRB5CCNAME§ không mặc nhiên thay Java §-Djava.security.krb5.conf§/JAAS.

## 7. Nhánh C: Browser có Authorization nhưng token không tới Spring

Một số reverse proxy/WAF/CDN có thể bỏ hoặc rewrite §Authorization§ trước khi chuyển tới JVM. Vì vậy cần quan sát **presence** trên hai phía, không log raw token.

~~~text
Browser:
 Authorization: Negotiate [REDACTED]
      |
      v
Ingress:
 hasAuthorizationHeader = true
      |
      v
Spring app:
 hasAuthorizationHeader = false
      |
      +--> Authentication filter không có token
           --> Trả 401 Negotiate lần nữa
~~~

Kiểm:
- Ingress/reverse proxy có forward §Authorization§ nguyên vẹn và không dùng header cho một phương thức auth khác không?
- WAF có coi header lớn là bất thường, trả §400/431§ hoặc truncate không? Kerberos/SPNEGO tokens có thể khá dài.
- HTTP/2→HTTP/1.1 forwarding, request size/header limits, upstream proxy path có thay đổi không?
- Backend app có đang nhận trực tiếp request từ bypass route khác (không đi qua trusted ingress) không?
- Nếu ingress **tự authenticate Kerberos**, app nhận identity header do ingress ký/được bảo vệ, đó là kiến trúc trust khác; không thể vừa giả định Spring nhận raw SPNEGO token vừa yêu cầu ingress strip nó.
- Không chuyển §Authorization: Negotiate§ sang client khác hoặc log nó trong APM/tracing.

**Không nên “sửa” bằng cách thêm một header §X-User: lan§ cho browser tự khai.** Nếu gateway làm authentication và backend tin identity header, phải có mTLS/trusted network, strip injected headers từ bên ngoài, trusted proxy authentication và kiểm user/tenant/authorization tại app.

## 8. Nhánh D: Header đã tới Spring nhưng GSS/JAAS không accept

Khi token đến đúng §SpnegoAuthenticationProcessingFilter§, provider phải dùng Kerberos ticket validator để kiểm. Mọi lỗi “401 repeat” cần phân lớp:

- Filter không được gọi hoặc §AuthenticationManager§ thiếu §KerberosServiceAuthenticationProvider§: wiring.
- Token thực tế là NTLM dưới umbrella §Negotiate§: mechanism không được Java Kerberos-only acceptor hỗ trợ.
- Token Kerberos có target SPN không khớp keytab: acceptor principal mismatch.
- Ticket đúng SPN nhưng key khác/KVNO khác sau rotation: §KRB_AP_ERR_MODIFIED§ hoặc decrypt failure.
- Encryption type không tương thích: KDC/JDK/AD crypto policy mismatch.
- JAAS Subject không có acceptor credentials: §LoginException§/§GSSException§; app keytab path sai/quyền đọc không đủ.
- Channel binding/EPA: client gửi channel binding info nhưng server/TLS termination không khớp, hoặc policy yêu cầu binding mà Java acceptor không cung cấp.
- Replay/time skew: ticket dùng sai thời gian hoặc cùng authenticator bị replay.
- Acceptor GSS đã verify, nhưng §UserDetailsService§ không tìm user/disabled account/authority mapping fail: Spring auth/application layer.

### 8.1. Kerberos target SPN có dạng nào?

~~~text
Public URL:
  https://portal.example.org/private

Host-based SPN:
  HTTP/portal.example.org@EXAMPLE.ORG

Not usually:
  HTTP/portal-pod-7.internal@EXAMPLE.ORG
  HTTP/kdc1.example.org@EXAMPLE.ORG
  https://portal.example.org/private@EXAMPLE.ORG
  HTTP/192.0.2.10@EXAMPLE.ORG
~~~

SPN **không phải HTTP URL đầy đủ**: thường dạng §HTTP/FQDN§, cộng realm khi thể hiện Kerberos principal. AD §setspn§ thường quản lý §HTTP/portal.example.org§ **không có §@REALM§** trong chuỗi query; JAAS/keytab principal có thể có §@EXAMPLE.ORG§. HTTP SPN không mặc định gồm port/path; một số ứng dụng/clients có ngoại lệ cần hợp đồng riêng.

**Lưu ý CNAME:** Client có thể canonicalize hostname qua DNS/CNAME tùy OS/browser/GSS config. Nếu browser vào §https://alias.example.org§ nhưng ticket dành §HTTP/backend.example.org§, keytab chỉ có §HTTP/portal.example.org§ thì mismatch. Bằng chứng phải lấy từ **actual requested SPN**, không chỉ đoán từ address bar.

### 8.2. KDC không tìm thấy SPN khác acceptor không giải được ticket

~~~text
Case 1 – KDC_ERR_S_PRINCIPAL_UNKNOWN:
  Browser asks KDC for HTTP/portal.example.org
  KDC has no such SPN
  -> Client cannot obtain Kerberos service ticket
  -> No valid Kerberos token reaches Portal

Case 2 – KRB_AP_ERR_MODIFIED:
  KDC finds SPN on account svc-web-A
  Browser obtains service ticket encrypted for svc-web-A
  Portal keytab actually has key for svc-web-B / stale KVNO
  -> Java acceptor cannot decrypt/verify ticket
~~~

Với duplicate SPN, một KDC có thể trả §KDC_ERR_PRINCIPAL_NOT_UNIQUE§ hoặc client thấy lỗi liên quan tùy AD/realm. §KRB_AP_ERR_MODIFIED§ có **nhiều nguyên nhân**, không tự quy mọi trường hợp thành duplicate SPN. Đọc thêm KDC/server events, KVNO/enctype, identity account, time, TLS binding và network.

### 8.3. AD SPN query: chỉ kiểm, không sửa tùy tiện

Chạy trên máy có RSAT/quyền tra cứu AD, theo policy tổ chức:

~~~powershell
# Tra cứu một SPN cụ thể:
setspn -Q HTTP/portal.example.org

# Tra cứu duplicate SPNs trong phạm vi được hỗ trợ/quản trị:
setspn -X
~~~

Nếu §setspn -Q§ không tìm ra SPN hoặc trả SPN gắn nhầm account, **chuyển AD/Identity team**. Chỉ AD admins được phê duyệt mới cân nhắc sửa bằng §setspn -S§/§-D§. Không viết playbook cho app tự sửa AD mỗi khi login fail: thay SPN account có thể làm hỏng dịch vụ khác hoặc tạo lỗ hổng giả mạo dịch vụ.

**Tên SPN và keytab phải được cấp từ cùng service account** theo thiết kế. Một §HTTP/portal.example.org§ đăng ký sai vào computer account hoặc tài khoản ứng dụng khác có thể khiến browser nhận ticket mà Portal Java không giải được.

## 9. Keytab, KVNO, enctype và quyền runtime

Keytab là **binary secret** chứa key của một hoặc nhiều principals, không phải certificate TLS hoặc file §krb5.conf§. Đặt ngoài JAR/Git/container image, ví dụ:

~~~text
/etc/kerberos/krb5.conf
/etc/kerberos/jaas.conf
/run/secrets/kerberos/http-portal.keytab
~~~

§krb5.conf§ xác định realm/KDC; §jaas.conf§ xác định login module/principal và keytab path; §*.keytab§ chứa key. Để đối chiếu **metadata** mà không in key bytes:

~~~bash
# Chạy trong container/VM TEST với đúng quyền được cấp.
id

# Kiểm file mode, owner, group; symlink mount được dereference:
stat -L -c '%a %U %G %n' \
  /run/secrets/kerberos/http-portal.keytab

# Kiểm quyền đọc đúng UID/GID chạy JVM:
test -r /run/secrets/kerberos/http-portal.keytab \
  && printf 'KEYTAB_READABLE=YES\n' \
  || printf 'KEYTAB_READABLE=NO\n'

# Chỉ xem KVNO, principal, enctype metadata:
klist -k -e /run/secrets/kerberos/http-portal.keytab
~~~

§klist -k -e§ (MIT Kerberos) thường hiển thị principal, KVNO và encryption types, **không in raw key material**. Tuy nhiên principal list/topology vẫn nhạy và không đẩy lên ticket/log rộng quyền. Không dùng §cat§, §xxd§, base64 toàn file, options dump key bytes hoặc in §Subject.getPrivateCredentials()§.

Kiểm:

| Dấu hiệu | Khả năng |
| --- | --- |
| Không đọc được keytab | UID/GID/mode/mount/symlink mismatch |
| Keytab chứa §HTTP/node.internal§ | Wrong principal/SPN cho public host |
| Keytab chỉ có KVNO cũ | Service account password/key đã rotate, pod chưa cập nhật |
| Keytab enctype chỉ có RC4/DES hoặc AES unsupported | KDC/JDK/AD encryption policy mismatch |
| Một Pod có keytab mới, Pod khác cũ | Intermittent 401 theo load-balancer backend |
| Keytab owner root mode §0400§, Pod UID 10001 | App không đọc được; cần group/owner phù hợp |
| Keytab chỉ được cấu hình trong env string base64 | Không phải file binary path mà JAAS đọc được |
| keytab path relative/classpath | Có thể trỏ sai file trong container/working directory |
| Service account SPN duplicate trong AD | KDC ambiguity, ticket có thể không khớp expected key |

**Không dùng §chmod 777§** để chữa lỗi. Kubernetes Secret volume có thể mount root-owned; cân nhắc §fsGroup§ + read-only §0440§ nếu CSI/volume driver hỗ trợ. Kiểm bên trong Pod bằng **đúng runtime UID**. Root host hoặc privileged Pod vẫn có thể đọc keytab dù file mode hạn chế, nên cần RBAC, admission, node isolation và encryption at rest.

### 9.1. Key rotation và KVNO

Khi service account password/key thay đổi, **KVNO có thể tăng**. KDC có thể bắt đầu mã hóa service tickets bằng key mới. Pod dùng keytab cũ không giải được và trả SPNEGO 401. Cách xử lý đúng:

1. Identity team xác nhận service account sở hữu SPN, KVNO/enctypes hiện tại và keytab mới.
2. Provision keytab mới qua secret manager/mount bảo mật.
3. Kiểm §klist -k -e§ metadata, path/mode và auth integration test trong staging.
4. Kiểm library/JGSS có cache credentials; mounted file đổi không bảo đảm Java §Subject§/GSS đã nạp key mới.
5. Rolling restart hoặc refresh theo capability đã kiểm, theo dõi 401/error rates từng Pod.
6. Xác định khả năng old/new key overlap từ AD/KDC policy, **không giả định luôn có overlap** sau password rotation.
7. Thu hồi key cũ theo quy trình, xử lý incident nếu đã lộ, không đơn giản xóa file mà key cũ tự bị revoke.

### 9.2. SPN nhiều alias, node và load balancer

Nếu URL public có §portal.example.org§ và §portal-alt.example.org§, quyết định có cần đăng ký **hai SPNs** và provision keys ra sao theo browser canonicalization và IdP/AD policy. Một VIP/load balancer chuyển tới nhiều nodes thường dùng **một logical HTTP service identity**; tất cả acceptors phải có khả năng dùng key của đúng logical SPN và đúng KVNO. Không tự tạo SPN theo Pod name.

Không dùng §servicePrincipal="*"§ hoặc accept any keytab principal chỉ để “bỏ lỗi” trong production khi service phải nhận đúng một SPN; wildcard acceptor làm tăng phạm vi credential/trust khi keytab chứa nhiều entries.

## 10. JAAS và krb5.conf phía Java acceptor

**Ví dụ §/etc/kerberos/krb5.conf§:**

~~~ini
[libdefaults]
    default_realm = EXAMPLE.ORG
    dns_lookup_realm = false
    dns_lookup_kdc = false

[realms]
    EXAMPLE.ORG = {
        kdc = kdc1.example.org:88
        kdc = kdc2.example.org:88
    }

[domain_realm]
    .example.org = EXAMPLE.ORG
    example.org = EXAMPLE.ORG
~~~

Nếu tổ chức cần DNS SRV discovery cho KDC/AD, chính sách §dns_lookup_kdc§ có thể khác. Không ép config này cho mọi domain. §EXAMPLE.ORG§ phải khớp realm Kerberos/KDC đã duyệt, không lấy từ HTTP Host header.

**Ví dụ §/etc/kerberos/jaas.conf§ cho acceptor-only:**

~~~text
com.sun.security.jgss.krb5.accept {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/run/secrets/kerberos/http-portal.keytab"
    principal="HTTP/portal.example.org@EXAMPLE.ORG"
    storeKey=true
    isInitiator=false
    useTicketCache=false
    doNotPrompt=true
    debug=false;
};
~~~

| Option | Tác dụng |
| --- | --- |
| §useKeyTab=true§ | Nạp credential service từ keytab |
| §keyTab§ | Absolute path đến **binary secret**, app UID phải đọc được |
| §principal§ | Full service principal, phải tương ứng KDC SPN/keytab |
| §storeKey=true§ | Giữ credentials trong private §Subject§ để GSS accept |
| §isInitiator=false§ | Server **nhận** service ticket, không cần TGT user chỉ để accept |
| §useTicketCache=false§ | Không mặc định dùng TGT cache của một user |
| §doNotPrompt=true§ | Fail khi thiếu keytab, không bật interactive password prompt |
| §debug=false§ | Tránh in Kerberos internals ở production |

**Khác biệt thư viện:** §SunJaasKerberosTicketValidator§ có thể tự tạo login config/JAAS Subject từ §setServicePrincipal(...)§ và §setKeyTabLocation(...)§, nên không mặc định nó luôn đọc entry §com.sun.security.jgss.krb5.accept§ trong external JAAS file. Xác định app dùng **application-managed LoginContext** hay **validator-managed login**; kiểm actual version source/API trước khi cấu hình kép.

**Java flags minh họa:**

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  -Djavax.security.auth.useSubjectCredsOnly=true \
  -jar portal.jar
~~~

- §java.security.krb5.conf§: file realm/KDC của **JDK**, không phải JAAS config.
- §java.security.auth.login.config§: file entry/login module.
- §javax.security.auth.useSubjectCredsOnly§: điều khiển JGSS credential lookup trong JAAS Subject; §false§ có thể khiến JGSS tìm credentials từ môi trường/default ticket cache. Không bật §false§ mù quáng để né lỗi keytab server.
- Các biến MIT §KRB5_CONFIG§, §KRB5_KTNAME§, §KRB5CCNAME§ hữu ích cho §klist§/§kinit§/§kvno§ nhưng **không nên mặc định** là nguồn duy nhất mà JDK đang đọc. Đặt Java properties/JAAS rõ ràng để tránh trường hợp shell thành công mà JVM fail.
- §isInitiator=false§ thuộc acceptor. Nếu Java app cũng gọi backend Kerberos với service principal riêng, cấu hình **initiator** khác và credentials khác. Không dùng user TGT/service keytab acceptor để tự động “delegate người dùng”.

## 11. Phân biệt GSS failure, NTLM fallback và channel binding

**Negotiate không bảo đảm Kerberos.** Khi browser/Windows không xin được Kerberos ticket, nó có thể fallback NTLM tùy policies. Java JGSS Kerberos acceptor có thể từ chối NTLM token trong §Authorization: Negotiate§. Khi response là 401 loop, hãy xác minh:
- Browser có service ticket cho §HTTP/portal.example.org§ không?
- KDC đã cấp ticket hay báo §S_PRINCIPAL_UNKNOWN§?
- Security events/SSPI cho biết Kerberos hay NTLM được dùng?
- Policy cấm NTLM/downgrade có được áp dụng đúng không?

**Không bật NTLM toàn domain như một workaround**, không đổi authentication mode từ Kerberos sang Basic chỉ để “đỡ 401” khi chưa có risk approval.

### 11.1. Extended Protection / channel binding

Một số Windows clients/servers có Extended Protection for Authentication (EPA) hoặc TLS channel binding requirements. Nếu TLS được terminate ở LB/WAF rồi Kerberos accept xảy ra ở JVM, channel binding data có thể không phù hợp. Lỗi §GSSException: Channel binding mismatch§ khác lỗi §KRB_AP_ERR_MODIFIED§ thuần keytab, dù cả hai có thể hiện là 401.

Điều tra:
1. TLS kết thúc ở đâu? Browser→LB, LB→Spring có mTLS/TLS không?
2. SPN được client sử dụng có dựa vào public hostname đúng không?
3. Server/IdP/OS policies có yêu cầu Channel Binding Token (CBT) hay EPA không?
4. Spring Kerberos/JDK version có hỗ trợ cơ chế channel binding cần thiết không?
5. Có proxy nào thay hostname/route hoặc offload TLS không?
6. Có thể điều chỉnh kiến trúc termination, cấu hình supported channel binding hay Kerberos accept tại proxy đáng tin với backend mTLS không?

**Không khuyên tắt EPA hoặc chỉnh Windows registry bỏ channel binding** như mẹo mặc định. Đây là cơ chế chống relay; thay đổi phải được Identity/Security review.

## 12. Các mã lỗi phổ biến: đừng “fix” nhầm lớp

| Symptom/mã lỗi | Điều cần nghi ngờ | Kiểm chứng và cách xử lý |
| --- | --- | --- |
| Không có §WWW-Authenticate: Negotiate§ | Entry point/filter chain/proxy | Kiểm Spring Security route, 302/401 edge |
| Có challenge, browser không gửi token | Browser policy, TGT, proxy, KDC | Allowlist, klist, user identity, VPN/DNS |
| §407 Proxy-Authenticate§ | Explicit proxy đòi auth | Kiểm PAC/WPAD; không thay keytab Portal |
| §KDC_ERR_S_PRINCIPAL_UNKNOWN§ | Target SPN không có trong KDC hoặc sai realm | §setspn -Q§/§kvno§/DNS |
| §KDC_ERR_PRINCIPAL_NOT_UNIQUE§ | Duplicate SPN trong AD | AD admin kiểm registry, tránh auto sửa |
| §KRB_AP_ERR_MODIFIED§ | Wrong key/account/KVNO/SPN, đôi khi lỗi môi trường khác | KDC events, keytab metadata, SPN owner và version |
| §KRB_AP_ERR_SKEW§ hoặc “Clock skew too great” | Client/KDC/server clock lệch | Đồng bộ NTP, không tắt timestamp validation |
| §KDC_ERR_ETYPE_NOTSUPP§ | Encryption algorithms không giao nhau | AD account enctype/JDK/KDC policy, ưu tiên AES |
| §GSSException: No valid credentials provided§ | Subject/JAAS/keytab thiếu hoặc wrong identity | LoginContext/validator config, file permissions |
| §Cannot locate KDC§ | krb5.conf/realm/DNS/network | Java properties, DC lookup, port 88, VPN |
| §Server not found in Kerberos database§ | FQDN/SPN chưa đăng ký | SPN chính xác, alias/CNAME, realm |
| §No key to decrypt ticket§ | Acceptor keytab/SPN/KVNO/enctype mismatch | Approved keytab/rotation, đúng JVM path |
| §Channel binding mismatch§ | TLS EPA/CBT với LB/proxy | Test TLS topology, không tắt EPA bừa |
| Token có NTLM thay Kerberos | Browser fallback do KDC/SPN policy | Kiểm actual auth mechanism, chặn downgrade |
| 401 sau app restart chỉ ở 1 Pod | Secret version/file owner drift hoặc cache | Compare pod version, UID/GID, rolling restart |
| GSS success rồi 403 | UserDetailsService/roles/tenant/resource deny | Application authorization, không sửa keytab |
| §WWW-Authenticate§ bị mất ở ingress | Gateway strips/rewrites challenge | Network trace 2 phía, config proxy |
| Authorization header mất giữa proxy/app | Ingress strips header | Presence-only tracing, sửa header forwarding |
| Login loop 302→IdP/form | Filter-chain priority, SSO fallback | Kiểm URL chain + AuthEntryPoint |
| Client klist OK nhưng Java fail | Khác JAAS/krb5.conf/cache/UID | Kiểm process flags, runtime path, Subject |

**Không gộp lỗi 401 thành một “Kerberos issue”.** 401 là HTTP status; cần nhìn header negotiation và server-side GSS error để biết nguyên nhân.

## 13. Bật quan sát có kiểm soát tại JVM/Spring

Chỉ trong môi trường test/staging riêng, có thể bật:

~~~bash
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Dsun.security.krb5.debug=true \
  -Dsun.security.jgss.debug=true \
  -jar portal.jar
~~~

**Rủi ro:** JDK/JGSS debug có thể chứa principal, realm, KDC host, ticket metadata, IP, session hints và các giá trị nhạy cảm. Chỉ bật trong khoảng điều tra ngắn, log RBAC hạn chế, retention ngắn, tắt khi kết thúc. Không bật §debug=true§ dài hạn trong §Krb5LoginModule§/§SunJaasKerberosTicketValidator§ ở production. Không copy raw logs lên chat nếu chưa redact.

### 13.1. Những gì nên thu thập

- Timestamp chính xác (timezone), correlation ID, node/pod ID.
- URL host, response 401/403/407/302, presence boolean của Negotiate challenge/response.
- SPN requested từ client trace **đã kiểm và được phép tiết lộ**, SPN expected trong approved service config.
- Java config paths (không secret file contents), runtime UID/GID và readable boolean.
- Keytab principal alias, KVNO/enctype categories đã được phép, rotation version.
- GSS/JAAS **error code/category** và provider authentication outcome.
- SecurityContext principal/authority **đã pseudonymize** để phân biệt authentication và authorization.
- IdP/KDC event ID, không lưu raw service ticket.
- Việc nhận/forward Authorization header chỉ ở dạng **exists=true/false**, không giá trị.

### 13.2. Những gì không thu thập

Không thu thập:
- §Authorization: Negotiate <raw-token>§;
- §Proxy-Authorization§, session cookies, browser HAR chưa redact;
- keytab bytes, §kinit§ password, TGT cache, credentials trong §Subject.getPrivateCredentials()§;
- User principal/email thật khi không cần, production screenshots chứa thông tin nội bộ;
- Secrets/KDC admin credentials trong README hoặc CI pipeline;
- KDC logs toàn domain vượt phạm vi incident.

### 13.3. End-to-end correlation từ 401 tới GSS

~~~text
Browser event:
   URL portal.example.org/private
   Response 401, hasNegotiateChallenge=true
   Request hasNegotiateAuthorization=true

Ingress event:
   request-id=qa-171
   hasNegotiateAuthorization=true

Spring event:
   request-id=qa-171
   SpnegoFilter invoked=true
   KerberosServiceAuthProvider invoked=true
   GSS_ACCEPT_RESULT=FAIL
   GSS_ERROR=KRB_AP_ERR_MODIFIED

Identity team event:
   requestedSPN=HTTP/portal.example.org
   AD owner=svc-portal-prod
   keyVersion=current-N

Runtime inventory:
   pod=portal-3
   keytabPrincipal=HTTP/portal.example.org
   keytabVersion=previous-N-1

=> Hypothesis: stale keytab KVNO on pod portal-3.
=> Fix: approved secret rollout, validate and retest.
~~~

Đây là trace **giả lập đã sanitize**, không có tài khoản hoặc secrets thật. Nó minh họa yêu cầu bằng chứng qua ít nhất browser, ingress, JVM và AD/KDC; không cần toàn bộ raw packet payload.

## 14. Java 17 chạy độc lập: công cụ phân loại lỗi SPNEGO

Chương trình §SpnegoTriageDemo.java§ bên dưới chạy được **không cần AD/KDC/keytab**. Nó nhận *quan sát đã được xác minh* (boolean và SPN strings do tester tự tạo) và gợi ý điều tra. Không dùng như Kerberos validator, không đọc HTTP headers thực tế, không kiểm chữ ký, không trích xuất SPN từ untrusted request, không xác thực user.

**Tệp SpnegoTriageDemo.java:**

~~~java
import java.util.Objects;

public class SpnegoTriageDemo {

    record Evidence(
        boolean hasNegotiateChallenge,
        boolean browserSentNegotiate,
        boolean headerReachedApp,
        boolean kdcIssuedServiceTicket,
        String ticketServicePrincipal,
        String acceptorPrincipal,
        boolean keytabKeyMatches,
        boolean gssAccepted) {}

    static String diagnose(Evidence e) {
        if (!e.hasNegotiateChallenge()) {
            return "CHECK_SERVER_CHALLENGE";
        }
        if (!e.browserSentNegotiate()) {
            return "CHECK_BROWSER_OR_KDC";
        }
        if (!e.headerReachedApp()) {
            return "CHECK_PROXY_HEADER_FORWARDING";
        }
        if (!e.kdcIssuedServiceTicket()) {
            return "CHECK_KDC_SPN_REGISTRATION";
        }
        if (!Objects.equals(
                e.ticketServicePrincipal(), e.acceptorPrincipal())) {
            return "CHECK_ACCEPTOR_SPN_MISMATCH";
        }
        if (!e.keytabKeyMatches()) {
            return "CHECK_KEYTAB_KVNO_ENCTYPE";
        }
        if (!e.gssAccepted()) {
            return "CHECK_GSS_MECHANISM_OR_POLICY";
        }
        return "SPNEGO_ACCEPTED_CHECK_AUTHORIZATION";
    }

    static void show(String label, Evidence e) {
        System.out.println(label + "=" + diagnose(e));
    }

    public static void main(String[] args) {
        String spn = "HTTP/portal.example.org@EXAMPLE.ORG";
        String wrong = "HTTP/node7.internal@EXAMPLE.ORG";

        show("missingChallenge", new Evidence(
            false, false, false, false, null, spn, false, false));
        show("browserNoToken", new Evidence(
            true, false, false, false, null, spn, false, false));
        show("proxyStripped", new Evidence(
            true, true, false, true, spn, spn, true, false));
        show("kdcNoSpn", new Evidence(
            true, true, true, false, spn, spn, false, false));
        show("wrongSpn", new Evidence(
            true, true, true, true, spn, wrong, true, false));
        show("staleKeytab", new Evidence(
            true, true, true, true, spn, spn, false, false));
        show("gssReject", new Evidence(
            true, true, true, true, spn, spn, true, false));
        show("accepted", new Evidence(
            true, true, true, true, spn, spn, true, true));
    }
}
~~~

**Chạy với JDK 17 trở lên:**

~~~bash
javac SpnegoTriageDemo.java
java SpnegoTriageDemo
~~~

**Stdout chính xác:**

~~~text
missingChallenge=CHECK_SERVER_CHALLENGE
browserNoToken=CHECK_BROWSER_OR_KDC
proxyStripped=CHECK_PROXY_HEADER_FORWARDING
kdcNoSpn=CHECK_KDC_SPN_REGISTRATION
wrongSpn=CHECK_ACCEPTOR_SPN_MISMATCH
staleKeytab=CHECK_KEYTAB_KVNO_ENCTYPE
gssReject=CHECK_GSS_MECHANISM_OR_POLICY
accepted=SPNEGO_ACCEPTED_CHECK_AUTHORIZATION
~~~

Giải thích: Khi không có challenge, **không kiểm keytab đầu tiên**; khi browser không gửi token, kiểm client/KDC; khi proxy strip header, lỗi nằm trên đường đi; khi KDC không cấp ticket, kiểm SPN/realm; khi ticket SPN khác keytab, sửa service identity; khi key material sai, điều tra KVNO/enctype; GSS reject dù SPN/key đúng có thể là NTLM/CBT/time/replay/policy; khi GSS accepted, tiếp tục kiểm authorization.

**Giới hạn an toàn:** Bản ghi §Evidence§ chứa dữ liệu **đã được tester tin cậy thu thập**. Trong thực tế §browserSentNegotiate=true§ chưa chứng minh KDC cấp Kerberos ticket (có thể là NTLM). Đây là một *decision support demo*, không phải “bypass” SPNEGO bằng cách tin booleans từ HTTP.

## 15. Java 17 integration probe: kiểm JAAS acceptor với keytab thật

Ví dụ này có thể **biên dịch với JDK 17** nhưng chỉ chạy PASS khi bạn đã có **JAAS config + keytab thật của sandbox**; nó chỉ kiểm khả năng JAAS nạp principal acceptor, **chưa chứng minh** browser handshake hoặc service-ticket decryption.

**Tệp KerberosAcceptorProbe.java:**

~~~java
import javax.security.auth.Subject;
import javax.security.auth.login.LoginContext;
import javax.security.auth.kerberos.KerberosPrincipal;

public class KerberosAcceptorProbe {
    public static void main(String[] args) throws Exception {
        LoginContext context =
            new LoginContext("com.sun.security.jgss.krb5.accept");
        context.login();
        try {
            Subject subject = context.getSubject();
            boolean match = subject
                .getPrincipals(KerberosPrincipal.class).stream()
                .anyMatch(p -> p.getName().equals(
                    "HTTP/portal.example.org@EXAMPLE.ORG"));

            if (!match) {
                throw new IllegalStateException(
                    "Approved service principal not found in JAAS Subject");
            }
            System.out.println("JAAS_ACCEPTOR_LOGIN=PASS");
            System.out.println("EXPECTED_PRINCIPAL=PASS");
            System.out.println("SECRETS_PRINTED=false");
        } finally {
            context.logout();
        }
    }
}
~~~

**Chạy trong sandbox đã provision §jaas.conf§/keytab:**

~~~bash
javac KerberosAcceptorProbe.java
java \
  -Djava.security.krb5.conf=/etc/kerberos/krb5.conf \
  -Djava.security.auth.login.config=/etc/kerberos/jaas.conf \
  KerberosAcceptorProbe
~~~

**Stdout nếu login thành công:**

~~~text
JAAS_ACCEPTOR_LOGIN=PASS
EXPECTED_PRINCIPAL=PASS
SECRETS_PRINTED=false
~~~

Nếu file không tồn tại/quyền sai/principal sai, §LoginContext.login()§ có thể ném §LoginException§. Không catch rồi in PASS giả; không in §Subject.getPrivateCredentials()§. Một JAAS login PASS chỉ chứng minh nạp service acceptor credentials, không chứng minh client đã có Kerberos ticket hợp lệ, TLS CBT policy hợp lệ hay §SpnegoAuthenticationProcessingFilter§ wiring đúng.

### 15.1. So sánh kết quả hai probes

| Tình trạng | SpnegoTriageDemo | KerberosAcceptorProbe | Cần test gì nữa? |
| --- | --- | --- | --- |
| No challenge | Gợi ý sửa entry point | Có thể pass | Server SecurityFilterChain |
| Browser no token | Gợi ý client/KDC | Có thể pass | Browser policy/TGT/network |
| Wrong SPN | Gợi ý mismatch | Probe thường fail nếu principal không đúng | Actual ticket SPN, keytab entries |
| Wrong KVNO | Gợi ý keytab mismatch | JAAS có thể vẫn pass | GSS accept real ticket, KDC current key |
| NTLM/CBT issue | Gợi ý GSS/policy | Có thể pass | Actual token mechanism/TLS binding |
| GSS accepted nhưng HTTP 403 | Gợi ý authorization | Có thể pass | Roles/tenant/business permission |

## 16. Reverse proxy, Kubernetes, DNS và nhiều backend nodes

**Reverse proxy ở phía trước Portal:**
- Public §https://portal.example.org§ không đồng nghĩa backend thấy §http://portal-pod-7.internal:8080§. SPN là **public logical service name**, không phải Pod hostname.
- Khi ingress terminate TLS, kiểm channel binding/EPA expectations của client và acceptor; không mặc định Kerberos sẽ tương thích bất kể TLS topology.
- Header §WWW-Authenticate§ phải ra browser; header §Authorization§ phải tới đúng acceptor nếu Spring xác thực.
- Nếu ingress làm Kerberos acceptor thay Spring, backend identity trust phải dùng mTLS/authorized identity propagation, không tin §X-User§ do browser gửi.
- LB phải không random route vào node có keytab cũ, realm config khác hoặc role policy khác. Quan sát error rate **theo node**.

**Kubernetes keytab secret mount:**

~~~yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: portal
      image: registry.example.org/portal:1.0
      volumeMounts:
        - name: kerberos-keytab
          mountPath: /run/secrets/kerberos
          readOnly: true
      env:
        - name: JAVA_TOOL_OPTIONS
          value: >-
            -Djava.security.krb5.conf=/etc/kerberos/krb5.conf
  volumes:
    - name: kerberos-keytab
      secret:
        secretName: portal-kerberos-keytab
        defaultMode: 0440
~~~

Đây là **đoạn Pod spec**, chưa đủ §Deployment§; §krb5.conf§ và validator config cũng phải được cung cấp từ nguồn tin cậy. App UID/GID, §fsGroup§ và driver volume quyết định có đọc được mount hay không; CSI/projection có thể có semantics khác nhau. Secret Kubernetes base64 chỉ là encoding, không phải encryption; bảo vệ etcd, RBAC, node isolation. Không chứa keytab bytes trong YAML/Helm/Git.

**Dấu hiệu nhiều Pod:** Nếu 4/5 Pods trả 200 nhưng một Pod trả 401 GSS, ưu tiên đối chiếu **keytab version/KVNO/UID, JVM flags, clock, cert TLS, Pod DNS và runtime image** trước khi sửa AD SPN toàn tổ chức.

## 17. Ma trận kiểm thử negative/positive

| ID | Điều kiện test | Expected |
| --- | --- | --- |
| T01 | Browser mới GET /private chưa có session | 401 Negotiate challenge đúng route |
| T02 | GET /public không cần auth | Không tự phát SPNEGO challenge |
| T03 | Server response chỉ 302 /login | Phát hiện form entry point/matcher priority |
| T04 | 401 không có Negotiate | Filter/entry point problem, không đổ lỗi keytab |
| T05 | Browser chưa có TGT | Không có Kerberos ticket, 401/flow phù hợp |
| T06 | Browser không allowlist host | Không tự gửi Negotiate token |
| T07 | Browser truy cập IP thay FQDN | SPN acquisition có thể fail/mismatch |
| T08 | Browser dùng CNAME/alias | SPN thực được đo, keytab/SPN owner khớp |
| T09 | Proxy trả 407 | Phân biệt proxy auth và Portal auth |
| T10 | Proxy strip Authorization | Server không thấy token, fail closed |
| T11 | Ingress strip WWW-Authenticate | Browser không nhận challenge, fail closed |
| T12 | Client fallback NTLM | Java Kerberos-only không được coi là authenticated |
| T13 | KDC không có HTTP SPN | KDC_ERR_S_PRINCIPAL_UNKNOWN, không được issue ticket |
| T14 | Duplicate SPN trong AD | KDC error/AD audit, không auto sửa |
| T15 | Keytab principal ≠ ticket SPN | GSS reject, không tạo principal |
| T16 | Keytab stale KVNO | Reject until approved rotation |
| T17 | Keytab không readable bởi JVM UID | Startup/auth fail, không chmod 777 |
| T18 | Keytab wrong enctype | GSS/KDC fail theo policy, không bật DES/RC4 yếu |
| T19 | Time skew lớn | Kerberos reject, sync NTP |
| T20 | KDC unavailable/VPN down | Browser không lấy ticket hoặc controlled failure |
| T21 | JAAS entry/krb5.conf path sai | Login/probe fail, xác định JVM property |
| T22 | Ticket valid nhưng §UserDetailsService§ reject account | Authentication denied, không bypass |
| T23 | Principal authenticated nhưng role thiếu | 403 đúng |
| T24 | TLS channel binding/EPA mismatch | Reject, điều tra TLS topology, không tắt EPA |
| T25 | Pod 1 keytab mới, Pod 2 cũ | Node-specific drift được phát hiện |
| T26 | Application SSO fallback Basic | Test phát hiện mechanism không phải Kerberos |
| T27 | Logs bật JGSS debug chứa dữ liệu nhạy | QA fail, redact/retention |
| T28 | User/header giả từ browser | Không tạo trusted principal |
| T29 | Real Kerberos token for correct SPN + correct keytab | GSS accept; app auth/roles áp riêng |
| T30 | Browser gửi lại token lặp/replay | Replay/time checks theo GSS/KDC, không bypass |
| T31 | Acceptor có JAAS credentials nhưng browser không Negotiate | Probe pass không đánh dấu E2E pass |
| T32 | Java mock bool true nhưng real token invalid | Integration validator phải reject |
| T33 | App có chain OIDC và SPNEGO cùng URL | Route matcher/priority được xác định rõ |
| T34 | Client request qua LB TLS offload | Kiểm EPA/CBT và SPN public logical hostname |

### 17.1. Tránh test sai lớp

- Sửa bytes của ticket → GSS từ chối integrity; **không** chứng minh SPN validator hoạt động độc lập.
- Tắt browser Integrated Auth → client không gửi token; **không** chứng minh keytab lỗi.
- Có §setspn -Q§ trả kết quả → chỉ chứng minh SPN hiện có trong directory; **không** chứng minh keytab KVNO hay Java filter đúng.
- §klist§ thấy ticket → client có credential; **không** chứng minh server accept.
- Java §LoginContext§ pass → server đọc được keytab; **không** chứng minh browser/endpoint negotiation.
- HTTP 200 sau Basic login → app có thể authenticated nhưng **không** phải SPNEGO Kerberos.
- HTTP 403 sau GSS accept → có thể là quyền app từ chối, Kerberos đã hoạt động.
- Test trên một Pod → **không** chứng minh toàn cluster nhất quán.

## 18. Runbook xử lý sự cố 401/403 lặp lại

### Giai đoạn A – Khoanh vùng trong 5 phút đầu (không tự sửa credential)

1. Xác định exact public URL và protected path, browser/OS version, network/VPN/proxy, thời điểm, 401/407/302/403.
2. Dùng clean session và inspect §WWW-Authenticate§: có scheme Negotiate không?
3. Quan sát **chỉ presence** §Authorization: Negotiate§ tại browser, ingress, JVM; không copy raw token.
4. Xác định Kerberos hay NTLM, browser có TGT và requested SPN nào.
5. Lấy server-side GSS error category và node ID nếu token đã tới app.
6. **Chọn một branch** của decision tree trước khi bắt đầu sửa.

### Giai đoạn B – Kiểm chứng hypothesis

**Nếu browser no token:** kiểm Integrated Auth allowlist, domain TGT, klist, DNS/KDC, VPN, proxy và SPN query. Không động vào keytab server trừ khi có bằng chứng.

**Nếu KDC no service ticket:** identity team kiểm §setspn -Q§, uniqueness/owner, realm, FQDN/CNAME và permissions; chỉ thay đổi AD qua change-control.

**Nếu acceptor decrypt fail:** kiểm actual ticket SPN, keytab metadata KVNO/enctype, account owner, runtime permissions, Pod drift, rotation và channel binding.

**Nếu Spring returns 403:** kiểm authenticated principal được verify, user enabled, role mapping, tenant/resource authorization; không tăng role bừa hoặc disable CSRF.

### Giai đoạn C – Sửa và xác minh

1. Apply **một thay đổi** trong sandbox hoặc canary: browser allowlist, SPN registration (AD team), keytab secret, app filter wiring hay reverse proxy.
2. Chạy lại baseline 401 Negotiate, client token presence, GSS success và protected HTTP response.
3. Kiểm negative test wrong SPN/token vẫn reject, không tạo fallback yếu.
4. Theo dõi 401/403/407 và KDC errors theo node, browser group và version trong rollout window.
5. Thu hồi stale keytabs/ticket caches theo policy, tắt JGSS debug, redact temporary logs.
6. Viết incident note: root cause, scope, fix, tests, credential impact và follow-up owner.

**Không chữa 401 bằng cách:** trust-all TLS, tắt EPA, bật Basic không kiểm soát, hardcode password, chấp nhận mọi service principal, §chmod 777§ keytab, dump raw ticket/log, tắt Spring Security, dùng user header hoặc add §permitAll§ cho protected resource.

## 19. Checklist trước production

- [ ] Protected endpoint chưa authenticated trả đúng §401 WWW-Authenticate: Negotiate§, không bị Form/Basic chain cướp ưu tiên.
- [ ] Browser enterprise policies chỉ allowlist các hosts approved; xác định NTLM fallback có được phép không.
- [ ] DNS/FQDN/alias, KDC realm và §HTTP/FQDN§ đúng public service name.
- [ ] AD SPN unique và thuộc đúng service account; không tạo duplicate.
- [ ] Keytab principal, KVNO, enctype trùng KDC keys đã phê duyệt; secret version đồng nhất tất cả Pods.
- [ ] JVM chạy đúng §krb5.conf§/JAAS/validator config, keytab path absolute và quyền runtime UID/GID.
- [ ] Spring filter chain có §SpnegoEntryPoint§, filter, authentication provider và user mapping tương thích version.
- [ ] Ingress forward Negotiate headers đến đúng component; reverse proxy không chèn untrusted identity header.
- [ ] TLS termination/EPA/channel binding phù hợp policy; không tắt bảo vệ để “pass login”.
- [ ] Debug Kerberos/JGSS tắt trong production; logs chỉ ghi metadata đã sanitize.
- [ ] Authenticated Kerberos principal vẫn qua application authorization, disabled user/tenant/resource kiểm riêng.
- [ ] Có negative tests wrong SPN, wrong keytab, client no token, NTLM, rotation, time skew, cluster drift.
- [ ] Có owner cho AD SPN, keytab/secret rotation, Spring security config, ingress, browser policy và incident response.
- [ ] Không có raw tickets, keytab, TGT caches, cookie/session secrets trong Git, image, logs, tickets/chat.

## 20. Bài tập thực hành

**Bài 1 – không có challenge.** Portal trả 302 tới §/login§ thay vì 401 Negotiate. Phân tích §SecurityFilterChain§ matchers/§AuthenticationEntryPoint§ và viết một MockMvc/WebTest xác minh đúng challenge từ endpoint §/private§.

**Bài 2 – browser im lặng.** Server có 401 Negotiate nhưng không có §Authorization§ ở ingress. Dùng browser policy, OS ticket cache, domain/VPN/KDC và proxy status để lập thứ tự kiểm, giải thích vì sao chưa có căn cứ sửa keytab.

**Bài 3 – SPN không tồn tại.** Client chạy §kvno HTTP/portal.example.org@EXAMPLE.ORG§ trong sandbox nhưng KDC trả §KDC_ERR_S_PRINCIPAL_UNKNOWN§. AD team cần query gì? Giải thích khác biệt giữa query §HTTP/portal.example.org§ và JAAS principal có realm suffix.

**Bài 4 – stale KVNO.** AD đã rotate svc account, Pod A dùng new keytab còn Pod B old keytab. Thiết kế log metadata, canary/rollout và test tính nhất quán, tránh đọc keys.

**Bài 5 – CNAME/LB.** Browser truy cập §https://alias.example.org§, client xin ticket §HTTP/backend.example.org§, JVM keytab chỉ có §HTTP/portal.example.org§. Vẽ trust flow và cách xác định actual SPN qua client/KDC metadata.

**Bài 6 – Java 17.** Chạy §SpnegoTriageDemo.java§, đối chiếu 8 dòng stdout, đổi evidence để nhận §CHECK_PROXY_HEADER_FORWARDING§ và §CHECK_ACCEPTOR_SPN_MISMATCH§. Nêu vì sao boolean không thay ticket validation thật.

**Bài 7 – JAAS integration.** Trong sandbox có keytab test, chạy §KerberosAcceptorProbe.java§. Phân biệt JAAS login pass với GSS accept/HTTP Negotiate end-to-end pass.

**Bài 8 – Kerberos hay NTLM?** Browser gửi §Authorization: Negotiate§ nhưng Java Kerberos-only reject. Nêu cách xác định actual authentication mechanism mà không giải mã/in raw token, và vì sao bật NTLM không phải mặc định an toàn.

**Bài 9 – Channel binding.** TLS terminate ở ingress, backend dùng Java GSS. Chứng minh vì sao channel binding mismatch không được “giải” bằng việc tắt EPA mù, và đề xuất kiểm thử TLS topology có security review.

**Bài 10 – HTTP 403.** User authenticated bằng Kerberos nhưng không có permission xem báo cáo. Kiểm layers và giải thích vì sao đây là outcome đúng; đề xuất user mapping/authorization regression tests.

**Bài 11 – Log redaction.** Xây một sự kiện trace chỉ có request ID, Negotiate header present, target SPN alias, GSS category, node và outcome. Chỉ ra những trường không được in.

**Bài 12 – Nhóm lỗi.** Phân nhóm §KDC_ERR_S_PRINCIPAL_UNKNOWN§, §KRB_AP_ERR_MODIFIED§, §No valid credentials§, §407§ và §403§ vào client/KDC/acceptor/proxy/app theo sơ đồ ở mục 4.

**Tiêu chí đạt:** Với một 401 loop, học viên có thể trả lời **“đã có Negotiate challenge chưa, client đã gửi token chưa, KDC cấp ticket cho SPN nào, ticket có tới JVM chưa, acceptor keytab/kvno có khớp không, GSS accept chưa, Spring authorization cho phép chưa?”** và thiết kế một phép kiểm độc lập cho mỗi câu, không làm yếu trust.

## 21. Tài liệu tham khảo chính thức

- Oracle JDK 17 – Part VI: HTTP/SPNEGO Authentication, 401 Negotiate, 407 Proxy, JAAS/useSubjectCredsOnly: https://docs.oracle.com/en/java/javase/17/security/part-vi-httpspnego-authentication.html
- Oracle JDK 17 – Krb5LoginModule JAAS options, acceptor, keyTab, isInitiator: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html
- Oracle JDK 17 – JAAS Reference Guide: https://docs.oracle.com/en/java/javase/17/security/java-authentication-authorization-service-jaas-reference-guide.html
- Spring Security Kerberos – SpnegoEntryPoint, ProcessingFilter, ServiceAuthenticationProvider, SunJaasKerberosTicketValidator: https://docs.spring.io/spring-security-kerberos/reference/ssk.html
- Spring Security – Kerberos extension integration: https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/ssk.html
- Microsoft Learn – Kerberos SPN registered on wrong account, KRB_AP_ERR_MODIFIED: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-event-4-access-denied
- Microsoft Learn – Troubleshooting Kerberos authentication failures: https://learn.microsoft.com/en-us/troubleshoot/windows-server/windows-security/kerberos-authentication-troubleshooting-guidance
- MIT Kerberos – krb5.conf realm/KDC/domain_realm: https://web.mit.edu/Kerberos/www/krb5-current/doc/admin/conf_files/krb5_conf.html
- MIT Kerberos – klist command: https://web.mit.edu/Kerberos/krb5-latest/doc/user/user_commands/klist.html
- MIT Kerberos – kvno command: https://web.mit.edu/Kerberos/krb5-latest/doc/user/user_commands/kvno.html
- Microsoft Learn – Setspn command for AD SPN queries: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setspn
- OWASP – Secrets Management Cheat Sheet (keytab/TGT): https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
