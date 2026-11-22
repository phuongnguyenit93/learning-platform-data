# Kerberos trong đăng nhập mạng nội bộ và mối liên hệ với SSO

## 1. Bài toán và kết quả cần hiểu

Nhân viên đã đăng nhập một máy tính thuộc miền doanh nghiệp, mở **https://intranet.example.org** và được ứng dụng nhận diện mà không phải nhập lại mật khẩu. Đây là một trải nghiệm **Single Sign-On (SSO)**. Một cơ chế phổ biến để thực hiện là **Kerberos V5** ở hạ tầng **Active Directory Domain Services (AD DS)** hoặc **MIT Kerberos**, kết hợp **HTTP Negotiate/SPNEGO** ở trình duyệt và ứng dụng web.

**Ý chính:** máy người dùng có **Ticket-Granting Ticket (TGT)** trong kho credential an toàn của hệ điều hành. Khi cần truy cập web service, client lấy **service ticket** cho đúng **Service Principal Name (SPN)**, ví dụ **HTTP/intranet.example.org@EXAMPLE.ORG**. Browser gửi token GSS/SPNEGO, server kiểm bằng secret key của service (thường lấy từ **keytab**), và Spring Security chỉ tạo Authentication sau khi kiểm thành công.

Không có chuyện browser gửi mật khẩu domain của người dùng cho từng intranet app để tạo SSO. Nhưng **Kerberos xác thực danh tính không tự cấp quyền nghiệp vụ**, và cũng không tạo một HttpSession chung giữa mọi app.

### Mục tiêu học tập

- Nêu được vai trò **KDC, AS, TGS, realm, principal, SPN, TGT, service ticket, keytab và credential cache**.
- Diễn giải đúng **AS-REQ/AS-REP, TGS-REQ/TGS-REP, AP-REQ/AP-REP**.
- Đọc luồng **HTTP 401 WWW-Authenticate: Negotiate → Authorization: Negotiate**.
- Phân biệt **Kerberos** với **SPNEGO negotiation** và trường hợp fallback NTLM.
- Hiểu vì sao DNS alias, SPN trùng, keytab/kvno sai, clock skew và browser policy làm silent SSO thất bại.
- Cấu hình **Spring Security Kerberos 2.x** với **Spring Boot 3.3.5 / Security 6.x / Java 17** và lưu session đúng.
- Phân biệt Kerberos nội bộ với **SAML2, CAS, OIDC** và các mô hình SSO khác.
- Kiểm thử positive/negative và xử lý lỗi mà không tắt HTTPS hay ticket validation.

Các miền EXAMPLE.ORG và user alice chỉ là dữ liệu bài học. Một Kerberos login thật cần KDC/AD, SPN, keytab và máy client được tổ chức quản trị.

## 2. Thuật ngữ: không nhầm KDC ticket với browser session

| Khái niệm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Realm** | Phạm vi Kerberos với KDC và principal namespace, thường được viết in hoa. | EXAMPLE.ORG |
| **KDC** | Key Distribution Center, có chức năng **Authentication Service (AS)** và **Ticket-Granting Service (TGS)**. | AD domain controller hoặc MIT KDC |
| **User principal** | Danh tính Kerberos của người dùng. | alice@EXAMPLE.ORG |
| **Service principal** | Danh tính của dịch vụ nhận ticket. | HTTP/intranet.example.org@EXAMPLE.ORG |
| **SPN** | Service Principal Name mà client yêu cầu cho service, đặc biệt quan trọng trong AD. | HTTP/intranet.example.org |
| **TGT** | Ticket cho client xin tiếp các service tickets từ TGS, không phải ticket login mọi web app. | krbtgt/EXAMPLE.ORG@EXAMPLE.ORG |
| **Service ticket** | Ticket mã hóa/bảo vệ cho service principal cụ thể. | HTTP/intranet.example.org |
| **Session key** | Khóa phiên dùng trong trao đổi Kerberos giữa client/service. | Giá trị bí mật, không ghi log |
| **Keytab** | Tệp chứa long-term keys của server/service principal, có thể kèm kvno và enctype. | /etc/security/keytabs/http.keytab |
| **Credential cache** | Kho credentials/TGT/service tickets phía client. | Windows LSA, MIT ccache |
| **GSS-API** | API trừu tượng thiết lập authenticated security context. | org.ietf.jgss trong JDK 17 |
| **SPNEGO** | Cơ chế thương lượng để chọn GSS mechanism, có thể là Kerberos. | HTTP Negotiate |
| **Local HTTP session** | Trạng thái ứng dụng Spring sau authentication nếu triển khai stateful. | JSESSIONID hoặc SESSION |

**TGT không phải session cookie của Spring.** Một browser không gửi TGT thẳng cho intranet ứng dụng; nó dùng cơ chế Kerberos/GSS-API để có token phù hợp service. Tương tự, **keytab không phải X.509 public certificate**: keytab chứa khóa bí mật dài hạn của service và phải bảo vệ như credential.

### Ba loại danh tính thường không giống nhau

~~~text
Kerberos principal:       alice@EXAMPLE.ORG
Kerberos service SPN:     HTTP/intranet.example.org@EXAMPLE.ORG
Local application user:   employee-0041
Email:                    alice@example.org
~~~

Chỉ khi Kerberos đã kiểm principal thành công và policy liên kết identity với account cục bộ, app mới biết user nội bộ tương ứng. **Không tự động cắt realm hoặc lấy email làm global key** nếu nhiều realm/tenant có thể phát cùng một tên.

## 3. Luồng Kerberos V5: từ đăng nhập máy đến app

~~~text
(1) Workstation/user logon
     Client ------------------ AS-REQ -------------------> KDC / AS
     Client <----------------- AS-REP -------------------- KDC / AS
          TGT được cache ở client

(2) User mở https://intranet.example.org
     Client -- TGS-REQ + TGT cho HTTP/intranet --> KDC / TGS
     Client <-- TGS-REP + service ticket ------- KDC / TGS

(3) Browser gọi intranet application
     Browser ---- HTTP Negotiate (AP-REQ) -------------> Web service
     Browser <--- optional GSS final token (AP-REP) --- Web service

(4) Server đã accept GSS context
     Verified Kerberos identity -> local UserDetails -> Spring Authentication
     -> SecurityContext/session -> kiểm quyền theo resource/tenant
~~~

### 3.1. Authentication Service: cấp TGT

Trong quá trình login domain/Kerberos, client gửi **AS-REQ** và nhận **AS-REP** sau khi thỏa điều kiện pre-auth/credential policy. Client có TGT để trình khi xin service tickets.

- User không phải nhập lại password tại từng web service.
- TGT có lifetime/renewable flags theo KDC policy, không sống mãi.
- Hệ điều hành hoặc MIT Kerberos quản lý cache; không đặt TGT vào cookie browser hay query URL.
- Nếu user chưa có TGT, hệ điều hành/browser có thể không hoàn tất silent authentication, hoặc yêu cầu login theo cơ chế của thiết bị.
- Một client ở realm khác cần **cross-realm trust/referral** có quản trị; không mặc nhiên tin mọi realm.

### 3.2. Ticket-Granting Service: cấp ticket cho từng SPN

Client dùng **TGS-REQ + TGT** để yêu cầu ticket cho **HTTP/intranet.example.org@EXAMPLE.ORG**. TGS dùng **long-term key của service** để bảo vệ phần ticket mà server đích nhận được. Client cũng nhận vật liệu session key thích hợp.

- **Ticket của HTTP/intranet.example.org không mặc nhiên dùng cho HTTP/payroll.example.org**.
- Nếu client có service ticket còn hiệu lực trong cache, nó có thể không cần hỏi KDC mới cho mỗi HTTP request.
- Nếu SPN không tồn tại, client/KDC không map service account đúng và ticket acquisition có thể fail.
- Cross-realm sử dụng các trust paths riêng; cấu hình realm, DNS, krb5.conf/AD referrals ảnh hưởng.
- TGT có thể dùng xin nhiều service tickets, tạo trải nghiệm SSO cho nhiều ứng dụng **nhưng từng ứng dụng vẫn kiểm ticket của mình**.

### 3.3. Application exchange: AP-REQ/AP-REP

Client gửi GSS token thường chứa Kerberos **AP-REQ** đến service. Server dùng keytab/service key để:

1. Kiểm ticket dành cho đúng service principal.
2. Xử lý authenticated session key và authenticator.
3. Kiểm thời gian hiệu lực, clock skew, replay cache và policy.
4. Xác lập GSS context; nếu mutual authentication cần, có thể trả AP-REP.
5. Trả ra principal đã được kiểm chứng để tầng ứng dụng ánh xạ thành local user.

**Không được tin user identity chỉ từ chuỗi principal ghi trong HTTP header**. Credential Kerberos phải được GSS acceptor/server validator kiểm thành công; constructor KerberosPrincipal hoặc một JSON có tên alice không chứng minh người gửi là alice.

## 4. HTTP Negotiate / SPNEGO: cách browser “dùng Kerberos”

**RFC 4559** định nghĩa HTTP authentication scheme **Negotiate**, thường sử dụng GSS-API/SPNEGO. Trong intranet:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
~~~

Server chưa có Authentication hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Browser được policy cho phép sẽ lấy token từ GSS/Kerberos stack:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Authorization: Negotiate BASE64_GSS_TOKEN
~~~

Server xác minh context, có thể trả:

~~~http
HTTP/1.1 200 OK
WWW-Authenticate: Negotiate OPTIONAL_FINAL_TOKEN
Content-Type: text/plain

Welcome to intranet
~~~

**Token trên chỉ là placeholder mô tả**, không phải credential thật. Một số GSS negotiations cần nhiều vòng **401 và token tiếp tục**; RFC 4559 cho phép response 2xx mang final GSS token để hoàn tất mutual authentication ở client. Đừng suy rằng HTTP 200 đơn độc chứng minh mutual authentication đã thành công theo mọi policy.

### Vì sao máy nội bộ không hiện trang login?

Một kịch bản thường gặp:

- User đã domain-logon và có TGT trong OS credential cache.
- Browser hiểu intranet.example.org là site được phép dùng integrated authentication.
- Browser xin đúng service ticket cho hostname của URL.
- Browser gửi HTTP Authorization: Negotiate.
- Server có keytab của HTTP/intranet.example.org, xác minh ticket, tạo Authentication.
- App cho user được truy cập theo local account/role policy.

**Không có form password tại website** vì browser/OS thực hiện ticket exchange, không phải vì website bỏ authentication.

### Negotiate không đồng nghĩa chắc chắn là Kerberos

SPNEGO là một **negotiation mechanism**. Trên Windows/HTTP, lựa chọn có thể liên quan **Kerberos hoặc NTLM** tùy browser, policy và environment. Chỉ thấy **Authorization: Negotiate** không tự chứng minh thực tế đã chọn Kerberos. Nếu hệ thống yêu cầu **Kerberos-only**, kiểm actual GSS mechanism và cấu hình từ chối fallback không mong muốn, tránh downgrade không được phê duyệt.

**Kerberos token không tự mã hóa toàn bộ HTTP body/cookie.** RFC 4559 khuyến nghị bảo vệ kênh thích hợp; production phải dùng HTTPS/TLS. Không gửi Authorization token thật vào issue tracker hoặc log công khai.

## 5. Mối liên hệ với SSO và các protocol federation khác

| Đặc tính | Kerberos + HTTP Negotiate | SAML2 Web Browser SSO | OIDC Authorization Code | CAS native |
| --- | --- | --- | --- | --- |
| Trung tâm xác thực | KDC/realm, service keys và tickets. | SAML IdP ký Response/Assertion. | OIDC Provider phát tokens. | CAS server phát ST cho service. |
| Browser flow | HTTP 401 + WWW-Authenticate: Negotiate. | Redirect đến IdP, SAMLResponse về ACS. | Redirect auth endpoint, callback authorization code. | CAS /login?service, callback ST. |
| Dữ liệu app kiểm | GSS Kerberos service ticket/context. | XML signature/issuer/audience/time. | ID Token/issuer/audience/nonce và code/token exchange. | CAS ticket với /serviceValidate. |
| Trải nghiệm SSO | TGT giúp xin ticket cho nhiều SPN. | IdP session giúp nhiều SP không login lại. | OP session giúp nhiều clients không login lại. | CAS TGC/TGT session giúp cấp ST mới. |
| Thiết bị ngoài intranet | Cần credential cache/KDC reachability/browser support hoặc bridge. | Thường thuận tiện hơn cho Internet SaaS. | Tốt cho web/mobile/API ecosystems. | Phù hợp ứng dụng web tích hợp CAS. |
| Local app session | Có thể có, độc lập TGT. | Có thể có. | Có thể có. | Có thể có. |

**Một lần đăng nhập Windows → nhiều intranet apps** là SSO dựa trên **TGT + service tickets**, **không phải mọi ứng dụng cùng dùng một JSESSIONID**. Mỗi app có thể tạo phiên riêng, có session timeout và logout policy riêng.

### Kerberos làm nền cho SAML2/OIDC SSO

Có mô hình doanh nghiệp:

~~~text
Employee login domain workstation
    |
    +--> Intranet Spring app:
    |      Browser --Kerberos/SPNEGO--> Web app
    |
    +--> Enterprise IdP:
           Browser --Kerberos/SPNEGO--> IdP
           IdP --SAMLResponse hoặc OIDC tokens--> SaaS SP/RP
~~~

SaaS app không nhận raw Kerberos service ticket nếu integration thực tế là SAML2/OIDC. **IdP dùng Kerberos như phương pháp authentication đầu vào**, rồi federation bằng protocol thích hợp ra bên ngoài. Không nhầm **spring-security-saml2-service-provider** với **spring-security-kerberos**.

## 6. SPN, DNS, keytab, kvno và time: yếu tố hạ tầng

### 6.1. SPN và account sở hữu khóa

~~~text
URL browser:
  https://intranet.example.org

Service principal dùng trong Kerberos:
  HTTP/intranet.example.org@EXAMPLE.ORG

SPN trên AD service account:
  HTTP/intranet.example.org

Service account (giả lập):
  EXAMPLE\svc_intranet

Keytab nằm trên server:
  /etc/security/keytabs/http-intranet.keytab
~~~

**HTTP/** là service class, còn hostname thường theo FQDN website. **SPN không phải một URL**: không chứa https://, path /private hoặc query string.

Với Active Directory, người có quyền phù hợp có thể:

~~~powershell
setspn -Q HTTP/intranet.example.org
setspn -L EXAMPLE\svc_intranet

# Lệnh thay đổi cấu hình AD: chỉ chạy khi có change approval
setspn -S HTTP/intranet.example.org EXAMPLE\svc_intranet

# Kiểm duplicate SPNs
setspn -X
~~~

**setspn -S** kiểm duplicate trước khi thêm; không tùy tiện đăng ký cùng SPN trên hai account. SPN trùng hoặc gắn nhầm account có thể khiến service không decrypt được ticket mà KDC phát.

### 6.2. DNS alias, CNAME, load balancer và container

Browser truy cập **https://portal.example.org** nhưng server keytab chỉ hỗ trợ **HTTP/intranet.example.org** có thể fail nếu client xin SPN theo portal.example.org. Tương tự, browser dùng IP address hoặc localhost không tự nhận ticket cho SPN của FQDN.

- CNAME/hostname canonicalization phụ thuộc Kerberos/GSS/browser stack; **không giả định mọi client tự đổi alias về host gốc giống nhau**.
- Nếu sau LB có nhiều instances, cùng logical service **HTTP/intranet.example.org** cần một mô hình service identity nhất quán, keytab đúng trên các acceptors hoặc một reverse proxy đã được phê duyệt làm acceptor.
- Không tạo hai accounts AD riêng có cùng SPN để “chia tải”; phải quản lý service account/keytab/kvno chính xác.
- Nếu HTTPS termination diễn ra tại ingress, cần xác định **ai thực sự xác minh SPNEGO token**. Nếu reverse proxy verify Kerberos rồi truyền identity tới backend, backend phải chỉ tin identity assertion qua channel đã bảo vệ, không tin header X-User tùy client.
- Proxy rewriting host, forwarding và DNS ảnh hưởng SPN; kiểm đường browser nhìn thấy, không chỉ DNS nội bộ cluster.

### 6.3. Keytab chứa secret và có version

Keytab có thể chứa key cho các **kvno (key version number)** và **enctype (encryption type)**. Nếu AD service account đã đổi key nhưng keytab chưa cập nhật, KDC cấp ticket theo key mới trong khi server chỉ có key cũ:

- Service có thể báo **KRB_AP_ERR_MODIFIED**, integrity failure hoặc GSSException.
- Kiểm SPN owner, keytab principal/kvno/enctype, quyền file và thời điểm rotation.
- Phối hợp key rotation giữa KDC và tất cả nodes, có overlap/rollback theo chính sách.
- Tránh bật DES/RC4/weak crypto chỉ để lỗi biến mất; ưu tiên AES và policy được phê duyệt.

Keytab **không phải certificate public**; không đưa vào Git, logs, artifacts hay gửi qua chat/email. Dùng secret management, permission tối thiểu và auditing.

### 6.4. Clock skew, ticket expiry và replay

Kerberos dùng lifetime/timestamps để hạn chế replay. Client, KDC và server cần đồng bộ NTP/Windows Time. Một policy phổ biến cho phép clock skew nhỏ (thường khoảng 5 phút), nhưng **giá trị thực do realm/service policy quyết định**.

- TGT hết hạn/không renewable → client có thể phải authenticate lại để có TGT mới.
- Service ticket hết hạn → phải lấy ticket mới nếu credentials cho phép.
- Authenticator replay hoặc lệch giờ → server phải từ chối.
- Không nới expiry hoặc tắt replay protection vô hạn để che sai lệch NTP.
- Ticket cache giúp tránh TGS-REQ mỗi request, không cho phép dùng ticket mãi mãi.

## 7. Browser integrated authentication và thiết bị truy cập

### Microsoft Edge / Chromium

Microsoft Edge có policy **AuthServerAllowlist**, cho phép chỉ định host được browser gửi integrated authentication. Khi không cấu hình, Edge có thể chỉ tự sử dụng IWA cho các site được nhận diện là intranet. Với website Internet không được allowlist, browser có thể không gửi token dù Windows đã domain-joined.

Chỉ allowlist hostname được tổ chức phê duyệt như **intranet.example.org**; không mở wildcard bao phủ Internet. Proxy/PAC, browser profile và hệ điều hành có thể ảnh hưởng phân loại intranet.

### Firefox, Linux, macOS

Firefox có cấu hình như **network.negotiate-auth.trusted-uris**. Linux/macOS có thể cần **kinit** và credential cache GSSAPI, hoặc enterprise SSO integration. Không mặc định rằng trình duyệt nào cũng có quyền dùng TGT ở mọi máy.

### Ngoài domain / mobile / Internet

Máy cá nhân không có Kerberos credentials hoặc không tới được KDC có thể không thực hiện silent login. Thay vì ép Kerberos ở mọi client, ứng dụng nên có **federated OIDC/SAML2 qua enterprise IdP** hoặc fallback có kiểm soát, cùng MFA/device policy khi cần. **Không chấp nhận NTLM/HTTP Basic tự động chỉ vì Kerberos không hoạt động.**

KDC không nhất thiết phải online trong mọi request nếu client đã cache service ticket còn hạn; nhưng vẫn cần mạng/KDC khi xin ticket mới, renew hoặc cross-realm referrals.

## 8. Spring Security Kerberos 2.x: các lớp liên quan

**Spring Security Kerberos** là extension, không phải tính năng xuất hiện chỉ vì thêm spring-boot-starter-security. Với hệ **Spring Security 6.x** có thể dùng **Spring Security Kerberos 2.x**, packages **org.springframework.security.kerberos**.

| Thành phần | Vai trò |
| --- | --- |
| **SpnegoEntryPoint** | Gửi HTTP **401 WWW-Authenticate: Negotiate** khi user chưa authenticated. |
| **SpnegoAuthenticationProcessingFilter** | Đọc Authorization: Negotiate; tạo KerberosServiceRequestToken và gọi AuthenticationManager. |
| **KerberosServiceAuthenticationProvider** | Nhờ validator xác minh service ticket/SPNEGO token, rồi nạp UserDetails. |
| **SunJaasKerberosTicketValidator** | Sử dụng JDK/JAAS để accept ticket với service principal và keytab. |
| **ProviderManager** | Chuyển authentication token tới provider tương ứng. |
| **UserDetailsService** | Map verified Kerberos principal sang local account và GrantedAuthorities. |
| **SecurityContextRepository** | Lưu Authentication cho những request sau nếu ứng dụng dùng HttpSession. |
| **SessionAuthenticationStrategy** | Xử lý session fixation/session ID rotation sau login. |

**KerberosAuthenticationProvider** hỗ trợ luồng authentication khác có thể sử dụng password/JAAS client, không phải thành phần bắt buộc để nhận **SPNEGO service ticket** ở web server. Bài này sử dụng **KerberosServiceAuthenticationProvider**.

### Bẫy của custom filter trong Spring Security 6.x

Khi tự tạo **SpnegoAuthenticationProcessingFilter** bằng new, filter **không tự lưu SecurityContext cho các request tiếp theo** nếu không gắn SecurityContextRepository. Nếu muốn stateful SP session, phải cấu hình repository **cho cả filter lẫn HttpSecurity**, đồng thời session fixation strategy và cookies. Nếu bỏ qua, ticket có thể pass ở request đầu nhưng user bị 401 ở request sau.

Trong hệ Spring Security Kerberos **7.x**, coordinates/API thuộc họ Spring Security 7 khác 2.x; không copy dependency và imports 7.x vào Spring Boot 3.3.5.

## 9. Java 17 độc lập: nhận diện đúng principal và local authorization

Ví dụ **KerberosSsoPolicyDemo.java** chạy bằng JDK 17, không cần KDC/AD/keytab. Nó minh họa **policy sau khi GSS context đã được xác minh**. Đối tượng **VerifiedContext** trong main được giả lập; **không được tạo từ client-supplied header/JSON hoặc KerberosPrincipal constructor để bypass GSS validation trong production**.

~~~java
import java.util.Set;
import javax.security.auth.kerberos.KerberosPrincipal;

public class KerberosSsoPolicyDemo {
    static final String SERVICE =
            "HTTP/intranet.example.org@EXAMPLE.ORG";
    static final Set<String> MEMBERS = Set.of("alice@EXAMPLE.ORG");
    static final Set<String> RESOURCES = Set.of("/intranet/report");

    record VerifiedContext(String client, String service,
                           String mechanism, boolean established) {}

    static String authorize(VerifiedContext c, String resource) {
        if (c == null || !c.established()) {
            return "DENY CONTEXT_NOT_ESTABLISHED";
        }
        if (!"KERBEROS".equals(c.mechanism())) {
            return "DENY MECHANISM_NOT_ALLOWED";
        }
        if (!SERVICE.equals(c.service())) {
            return "DENY WRONG_SERVICE";
        }
        if (!c.client().endsWith("@EXAMPLE.ORG")) {
            return "DENY REALM_NOT_ALLOWED";
        }
        if (!MEMBERS.contains(c.client())) {
            return "DENY NO_MEMBERSHIP";
        }
        if (!RESOURCES.contains(resource)) {
            return "DENY RESOURCE_NOT_ALLOWED";
        }
        return "ALLOW";
    }

    static void check(String label, VerifiedContext c, String resource) {
        System.out.println(label + ": " + authorize(c, resource));
    }

    public static void main(String[] args) {
        KerberosPrincipal principal =
                new KerberosPrincipal("alice@EXAMPLE.ORG");
        System.out.println("principal: " + principal.getName());

        VerifiedContext good = new VerifiedContext(
                principal.getName(), SERVICE, "KERBEROS", true);

        check("valid", good, "/intranet/report");
        check("wrong service", new VerifiedContext(
                principal.getName(), "HTTP/other.example.org@EXAMPLE.ORG",
                "KERBEROS", true), "/intranet/report");
        check("wrong mechanism", new VerifiedContext(
                principal.getName(), SERVICE, "NTLM", true), "/intranet/report");
        check("wrong realm", new VerifiedContext(
                "bob@OTHER.ORG", SERVICE, "KERBEROS", true), "/intranet/report");
        check("not provisioned", new VerifiedContext(
                "mallory@EXAMPLE.ORG", SERVICE, "KERBEROS", true),
                "/intranet/report");
        check("wrong resource", good, "/admin");
        check("not established", new VerifiedContext(
                principal.getName(), SERVICE, "KERBEROS", false),
                "/intranet/report");
        check("no context", null, "/intranet/report");
    }
}
~~~

Chạy:

~~~bash
javac KerberosSsoPolicyDemo.java
java KerberosSsoPolicyDemo
~~~

**stdout chính xác:**

~~~text
principal: alice@EXAMPLE.ORG
valid: ALLOW
wrong service: DENY WRONG_SERVICE
wrong mechanism: DENY MECHANISM_NOT_ALLOWED
wrong realm: DENY REALM_NOT_ALLOWED
not provisioned: DENY NO_MEMBERSHIP
wrong resource: DENY RESOURCE_NOT_ALLOWED
not established: DENY CONTEXT_NOT_ESTABLISHED
no context: DENY CONTEXT_NOT_ESTABLISHED
~~~

**KerberosPrincipal** chỉ biểu diễn một tên principal, không đăng nhập KDC. **VerifiedContext** được dùng để diễn đạt “đã có GSS validation”, không phải object được browser tự cấp. Trong ứng dụng thật, danh tính và mechanism chỉ lấy từ trusted Kerberos acceptor/provider, rồi mới kiểm local account/tenant/resource.

## 10. Spring Boot 3.3.5 + Spring Security Kerberos 2.1.0

Đây là mẫu **Servlet intranet SPNEGO acceptor** trên Java 17, chỉ hoàn tất authentication end-to-end khi đã có:

- Realm EXAMPLE.ORG thật và user alice@EXAMPLE.ORG.
- SPN HTTP/intranet.example.org gắn đúng service account.
- Keytab server đúng principal/kvno/enctype, file readable bởi process.
- DNS/LB/HTTPS cho https://intranet.example.org.
- Browser domain/trusted intranet allowlist và TGT trong client credential cache.
- Policies realm/service đủ mạnh, không cho fallback không được phê duyệt.

### 10.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>kerberos-intranet-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <version>2.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.security.kerberos</groupId>
            <artifactId>spring-security-kerberos-web</artifactId>
            <version>2.1.0</version>
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

**Version cảnh báo:** Maven coordinates cho Kerberos **2.1.0** khác Kerberos 7.x. Đây là một ví dụ phù hợp họ Spring Security 6.x; các dependency transitive cần được kiểm bằng dependency:tree, security advisories và integration test trong môi trường doanh nghiệp.

### 10.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework

app:
  kerberos:
    service-principal: "HTTP/intranet.example.org@EXAMPLE.ORG"
    keytab-location: "/etc/security/keytabs/http-intranet.keytab"
~~~

Đường keytab là minh họa trên Linux/container, cần file thật và quyền truy cập đúng khi chạy. Không commit keytab; không cho ứng dụng lấy keytab location hoặc service principal từ request user. URL public vẫn là HTTPS intranet hostname, không phải localhost:8080.

### 10.3. Main class

**src/main/java/com/example/krbdemo/KerberosApplication.java**

~~~java
package com.example.krbdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosApplication.class, args);
    }
}
~~~

### 10.4. SecurityConfig.java

**src/main/java/com/example/krbdemo/SecurityConfig.java**

~~~java
package com.example.krbdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {
    @Bean
    UserDetailsService localUsers() {
        return username -> {
            // Demo chỉ cấp quyền cho một account đã provision.
            if (!"alice@EXAMPLE.ORG".equals(username)) {
                throw new UsernameNotFoundException("Unknown local account");
            }
            return User.withUsername(username)
                    .password("{noop}unused-by-kerberos")
                    .authorities("ROLE_EMPLOYEE")
                    .build();
        };
    }

    @Bean
    SunJaasKerberosTicketValidator ticketValidator(
            @Value("${app.kerberos.service-principal}") String principal,
            @Value("${app.kerberos.keytab-location}") String keytabPath) {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(keytabPath));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService localUsers) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(localUsers);
        return provider;
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            KerberosServiceAuthenticationProvider kerberosProvider)
            throws Exception {

        SecurityContextRepository repository =
                new DelegatingSecurityContextRepository(
                    new RequestAttributeSecurityContextRepository(),
                    new HttpSessionSecurityContextRepository());

        SpnegoAuthenticationProcessingFilter spnego =
                new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(
                new ProviderManager(kerberosProvider));
        spnego.setSecurityContextRepository(repository);
        spnego.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .securityContext(sc -> sc
                .securityContextRepository(repository))
            .authenticationProvider(kerberosProvider)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Các điểm đúng của ví dụ:**

1. **SpnegoEntryPoint()** gửi 401 Negotiate challenge, không phải CAS redirect hay SAML2 redirect.
2. **SpnegoAuthenticationProcessingFilter** nhận GSS token, gọi ProviderManager.
3. **KerberosServiceAuthenticationProvider** nhận ticket validator và local user details; nó không tự cấp mọi user ROLE_ADMIN.
4. **SunJaasKerberosTicketValidator** dùng servicePrincipal + keytab được cấu hình ngoài HTTP input.
5. **SecurityContextRepository** chung được nối vào filter và HttpSecurity; stateful SecurityContext có thể còn sau request đầu.
6. **ChangeSessionIdAuthenticationStrategy** giúp session fixation protection.
7. Filter được tạo **bên trong SecurityFilterChain**, không là servlet Filter bean độc lập, tránh bị Spring Boot đăng ký hai lần ngoài chain.
8. **anyRequest().authenticated()** chưa đủ để bảo vệ từng role/tenant/resource; vẫn phải có authorization.
9. Không bật Basic/formLogin fallback mặc định, cũng không tắt CSRF mặc định chỉ để demo.
10. Spring app phụ thuộc **KDC/keytab/browser integration thật**; code không thể tự tạo một principal Kerberos đã xác thực từ chuỗi username.

**Lưu ý:** giá trị password trong UserDetailsService là placeholder local UserDetails, **không phải password domain và không dùng để validate Kerberos**. Với production, thay localUsers bằng DB/LDAP/IGA được quản trị và kiểm disabled/locked/revoked.

### 10.5. Controller

**src/main/java/com/example/krbdemo/IntranetController.java**

~~~java
package com.example.krbdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IntranetController {
    @GetMapping("/")
    public String home() {
        return "Kerberos intranet SSO ready";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "Authenticated: " + authentication.getName();
    }
}
~~~

Chạy trong thư mục pom.xml:

~~~bash
mvn spring-boot:run
~~~

**Đầu ra có điều kiện:**

- **GET http://localhost:8080/** trả **Kerberos intranet SSO ready** nếu app khởi động và keytab config không gây lỗi khởi tạo.
- **GET /private** lúc chưa authenticated trả **401 + WWW-Authenticate: Negotiate** nếu request vào đúng SecurityFilterChain.
- Browser được allowlist có thể gửi **Authorization: Negotiate** sau khi nhận 401.
- Khi KDC/SPN/keytab/validator thành công và localUsers tìm thấy **alice@EXAMPLE.ORG**, **/private** trả **Authenticated: alice@EXAMPLE.ORG**.
- Nếu principal trả về từ KDC theo định dạng khác, phải map đúng qua policy, không dùng mặc định email hay bỏ realm để ép login.
- **http://localhost:8080** không tương ứng SPN HTTP/intranet.example.org; để test SSO thật cần truy cập **https://intranet.example.org** với DNS/HTTPS ingress và keytab thật.

## 11. JAAS / Java GSS-API trong JDK 17

Bên dưới Spring extension là JDK **JAAS** và **GSS-API**. JDK 17 có **Krb5LoginModule**, **LoginContext**, **KerberosPrincipal** và package **org.ietf.jgss**.

**Ví dụ JAAS acceptor configuration (jaas.conf):**

~~~text
KerberosAcceptor {
    com.sun.security.auth.module.Krb5LoginModule required
    useKeyTab=true
    keyTab="/etc/security/keytabs/http-intranet.keytab"
    storeKey=true
    doNotPrompt=true
    isInitiator=false
    principal="HTTP/intranet.example.org@EXAMPLE.ORG";
};
~~~

Giải thích:

- **useKeyTab=true** dùng file keytab.
- **storeKey=true** cung cấp acceptor credentials/key trong Subject khi phù hợp.
- **isInitiator=false** cấu hình service nhận GSS contexts, không phải client khởi xướng.
- **doNotPrompt=true** không yêu cầu nhập password tương tác.
- **principal** phải match đúng service principal mà browser đang xin ticket.
- JAAS config và keytab được bảo vệ ngoài webroot, không trả ra API.

**Mảnh Java GSS-API sau khi đã có Subject/JAAS acceptor** — đây là snippet mô tả API, **không phải chương trình compile độc lập** nếu thiếu imports, request handler, GSS credentials, JAAS và KDC:

~~~java
GSSManager manager = GSSManager.getInstance();
GSSContext context = manager.createContext((GSSCredential) null);

byte[] output = context.acceptSecContext(
        inputNegotiateToken, 0, inputNegotiateToken.length);

if (!context.isEstablished()) {
    // Tiếp tục HTTP 401 WWW-Authenticate: Negotiate với output token.
    return;
}

GSSName clientName = context.getSrcName();
// Chỉ sau established context + mechanism/service checks
// mới map clientName sang local account và quyền.
~~~

Cần import org.ietf.jgss types và thực thi trong acceptor Subject có service credentials. Trong production phải xử lý GSS final token, mutual auth, replay, TLS, response framing, cleanup và lỗi chuẩn; không tự viết GSS filter thay thư viện chỉ vì đoạn mã ngắn.

## 12. Công cụ kiểm tra trên client và server

### MIT Kerberos (Linux/macOS nếu đã cài toolkit)

~~~bash
# Kiểm credentials/TGT/service tickets trong cache của user
klist
klist -e

# Chỉ dùng trong lab được phép: lấy TGT
kinit alice@EXAMPLE.ORG

# Xin service ticket và kiểm version từ KDC
kvno HTTP/intranet.example.org@EXAMPLE.ORG
~~~

**klist** liệt kê tickets đã cache. **kvno** xin service ticket và cho biết key version; fail ở đây thường liên quan client/KDC/DNS/SPN, chưa tới Spring backend.

### Windows

~~~powershell
klist
klist tickets
setspn -Q HTTP/intranet.example.org
~~~

Windows klist có cú pháp và quyền khác MIT klist; không áp dụng nguyên tùy chọn -e, -k giữa hai OS. **setspn -S** thay đổi cấu hình AD nên chỉ admin thực hiện theo change approval.

### Server keytab

~~~bash
klist -k -e /etc/security/keytabs/http-intranet.keytab
~~~

Phải nhìn thấy đúng service principal, kvno/enctype phù hợp, nhưng không hiển thị key material hoặc copy keytab khỏi server. Không dùng các lựa chọn in secret keys vào terminal log.

### HTTP/browser

Kiểm DevTools → Network:

1. **/private** trả 401 + **WWW-Authenticate: Negotiate** chưa?
2. Browser gửi **Authorization: Negotiate** không?
3. Hostname public chính xác như SPN đã đăng ký không?
4. GSS acceptor thực tế xác minh được context và keytab không?
5. Nếu ticket pass, **UserDetailsService** có cấp local account không?
6. Request sau đã lưu SecurityContext/session hay 401 lại?
7. User authenticated thiếu quyền có bị 403 không?

Với máy đã có Kerberos cache và curl build hỗ trợ GSS:

~~~bash
curl --negotiate -u : -i https://intranet.example.org/private
~~~

Lệnh này **không tự cấp TGT** và sẽ fail nếu client không có credentials hoặc không trust hostname/KDC. Tránh log header Authorization nguyên bản, kể cả khi sử dụng curl --verbose.

### Debug JDK chỉ trong môi trường kiểm soát

~~~text
-Dsun.security.krb5.debug=true
-Djava.security.auth.login.config=/etc/security/jaas.conf
~~~

Bật debug chỉ trong sandbox hoặc cửa sổ điều tra được phê duyệt; log có thể chứa principal/realm/ticket details. Sử dụng reason codes và trace IDs đã lọc thay vì lưu token/keytab/credentials.

## 13. Troubleshooting: phân biệt 401, KDC, keytab và authorization

| Dấu hiệu | Khả năng | Cách chẩn đoán |
| --- | --- | --- |
| Không có WWW-Authenticate: Negotiate | Entry point/filter chain/proxy response sai. | Kiểm exceptionHandling, reverse proxy headers. |
| Có 401 nhưng browser không gửi token | IWA policy, host ngoài intranet, client không có TGT. | AuthServerAllowlist, klist, DNS/KDC. |
| **KDC_ERR_S_PRINCIPAL_UNKNOWN** | SPN không tồn tại hoặc client hỏi sai hostname. | setspn -Q, kvno, DNS aliases. |
| **KRB_AP_ERR_MODIFIED** | Service keytab/SPN owner/kvno/enctype sai; server không decrypt ticket. | Kiểm AD service account, keytab và rotation. |
| **KRB_AP_ERR_SKEW** | Clock skew quá realm policy. | Kiểm NTP, ticket lifetime và thời gian client/KDC/server. |
| GSSException: Defective token | Header bị cắt, cơ chế không tương thích, token hỏng. | Kiểm proxy/header limits, SPNEGO mechanism. |
| GSSException: No valid credentials | Acceptor không load keytab hoặc principal sai. | File permission, jaas.conf, servicePrincipal. |
| 401 lặp sau khi ticket pass | SecurityContext không persist, session cookie mất hoặc LB chuyển node. | SecurityContextRepository, Session strategy, shared sessions. |
| 403 sau khi ticket pass | Local account/role/resource policy deny. | UserDetailsService, authority mapping, tenant membership. |
| SSO chỉ chạy ở hostname gốc, không chạy alias | Service ticket theo SPN khác. | FQDN, CNAME/canonicalization, SPN/keytab. |
| SSO chỉ chạy ở node A | Keytab node B lỗi hoặc local session không chia sẻ. | Per-node keytab/kvno, LB and session store. |
| HTTP Negotiate fallback thành NTLM | Browser/KDC không lấy được Kerberos ticket hoặc policy. | Actual GSS mechanism, Kerberos-only enforcement. |
| KDC online nhưng web app vẫn 401 | Có thể GSS/server acceptor hoặc role mapping sai. | Trace từng tầng, không đổ lỗi mạng ngay. |
| Local logout nhưng browser lại SSO | Client vẫn có TGT/service ticket, auto Negotiate. | Phân biệt workstation credential và local session. |
| App A không dùng user Kerberos để gọi DB B | Chưa có delegation/KCD. | Double-hop/KCD policy, không tin X-User header. |

## 14. Double-hop: SSO không mặc nhiên là delegation

Nhân viên đăng nhập intranet app A bằng Kerberos, sau đó app A cần gọi backend B **với danh tính chính nhân viên**. A đã xác thực user, nhưng **không mặc nhiên có credential hoặc quyền đại diện user ở backend B**.

~~~text
Browser alice --HTTP/intranet ticket--> Web A
Web A        --requires own ticket/delegation--> Backend B
~~~

**Kerberos Constrained Delegation (KCD)** hoặc **Resource-Based KCD** có thể cho phép sử dụng các luồng **S4U2Self/S4U2Proxy** theo chính sách AD phù hợp. Đây là một thiết kế riêng có rủi ro:

- Chỉ cho phép A delegate tới services được phê duyệt.
- Không bật **unconstrained delegation** chỉ để ứng dụng chạy.
- Không dùng service account có domain-admin privilege.
- Kiểm user/tenant permissions tại backend B dù Kerberos delegation đã pass.
- Nếu A gọi B bằng **service account của A**, đó là service-to-service auth, **không phải tự động impersonate alice**.
- B không tin header **X-User: alice** do client bên ngoài tự gửi.

**SSO** là giảm lần nhập credentials ban đầu cho người dùng; **delegation** là cho phép dịch vụ trung gian dùng quyền user tại dịch vụ khác. Hai khái niệm liên quan nhưng không đồng nhất.

## 15. HTTPS, session và authorization vẫn bắt buộc

- **TLS/HTTPS** bảo vệ HTTP body, cookies, session ID và headers. HTTP Negotiate chỉ giải quyết authentication context, không tự encrypt toàn bộ HTTP request/response.
- **Spring HttpSession** độc lập Kerberos TGT. App có thể đã phát session và không cần Negotiate lại mỗi request; session expiry hoặc logout không tự xóa TGT máy người dùng.
- **CSRF** vẫn có ý nghĩa khi app dùng cookie-based session cho state-changing requests; không tắt CSRF toàn ứng dụng vì SPNEGO.
- **Service keytab** là secret cấp server, bảo vệ file ACL/secret manager, key rotation và không log.
- **UserDetailsService** không tự cấp quyền admin. Principal alice@EXAMPLE.ORG cần local active account, scoped roles và membership.
- **Cross-realm trust** không có nghĩa user của mọi realm được dùng tài nguyên. Map realm/identity/account có allowlist.
- **Ticket expiry** không tự đóng tất cả local sessions đã tạo; muốn revocation nhanh phải có session/authorization policy.
- **Kerberos-only policy** cần từ chối SPNEGO fallback không phù hợp, không chỉ thấy Negotiate header là pass.
- **Reverse proxy** chỉ chuyển verified identity qua trusted channel nếu nó là GSS acceptor; không tin X-Forwarded-User public.

## 16. Khi nào nên dùng Kerberos SSO?

| Bối cảnh | Lựa chọn |
| --- | --- |
| Máy nhân viên domain-joined, intranet ổn định và AD/KDC đã có | **Kerberos/SPNEGO phù hợp**, browser IWA có thể silent login. |
| Linux/macOS workstation đã có GSS cache và browser policy | Có thể dùng Kerberos, cần test thực tế. |
| Website public phục vụ khách hàng bên ngoài domain | OIDC/SAML2 thường phù hợp hơn làm login chính. |
| Ứng dụng mobile không có Kerberos credential cache | Xem OIDC/mobile SSO agent hoặc enterprise bridge. |
| SaaS cần SSO từ AD | IdP dùng Kerberos nội bộ rồi phát SAML2/OIDC cho SaaS. |
| Multi-node intranet web | SPN/keytab hoặc proxy acceptor nhất quán; session HA riêng. |
| User cần gọi nhiều backend thay mặt mình | Thiết kế KCD/S4U hoặc delegated auth riêng, không tự có. |
| Yêu cầu revoke quyền tức thời | Kết hợp local account/role/session revocation, không dựa ticket expiry đơn độc. |

## 17. Kiểm thử dương tính và âm tính

Dùng **AD/KDC sandbox**, service account thử nghiệm và browser policy được quản trị. **Không tạo SPN trên production AD** hoặc sao chép keytab nếu chưa được phép.

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 1 | Client có TGT, SPN/keytab đúng | Browser gửi Negotiate, server có thể authenticate. |
| 2 | Client không có TGT và không có fallback | SSO không hoàn tất; không tự tạo Authentication. |
| 3 | Browser không allowlist intranet host | Có thể không gửi Authorization Negotiate. |
| 4 | Spring thiếu SpnegoEntryPoint | Không có challenge Negotiate đúng. |
| 5 | Spring thiếu SpnegoAuthenticationProcessingFilter | Có challenge nhưng server không xử lý token. |
| 6 | Thiếu KerberosServiceAuthenticationProvider | Không kiểm service ticket, fail. |
| 7 | SPN chưa đăng ký | KDC trả principal unknown hoặc lỗi tương ứng. |
| 8 | SPN đăng ký trùng account | Lỗi ownership/crypto, không tự tạo account trùng nữa. |
| 9 | URL CNAME khác SPN trên keytab | Fail theo client canonicalization/config. |
| 10 | Keytab sai principal hoặc file permission | GSS acceptor fail, không cho login. |
| 11 | Keytab kvno cũ sau key rotation | Integrity/ticket decryption fail. |
| 12 | Client và KDC lệch đồng hồ | Clock skew/time fail. |
| 13 | Ticket quá hạn hoặc replay | Reject theo Kerberos policy. |
| 14 | Mechanism thực tế là NTLM khi yêu cầu Kerberos-only | Deny. |
| 15 | HTTPS cert hostname mismatch | TLS fail; không disable cert check. |
| 16 | Ticket pass nhưng local account bị disable | Không cấp quyền. |
| 17 | User thiếu ADMIN role | Admin resource trả 403. |
| 18 | User thiếu tenant membership | Cross-tenant access deny. |
| 19 | Custom SPNEGO filter không persist SecurityContext | Request sau có thể bị 401; test và sửa repository. |
| 20 | Browser session hết hạn nhưng TGT còn | Có thể SSO lại không hỏi password. |
| 21 | Node A keytab đúng, B keytab sai | LB gây lỗi ngẫu nhiên, kiểm per-node. |
| 22 | KDC tạm offline nhưng ticket đã cache còn hạn | Có thể context vẫn hoạt động tùy policy/cache. |
| 23 | Client cần service ticket mới khi KDC offline | Không lấy được ticket, fail. |
| 24 | User từ realm chưa được tin | Deny mapping/realm trust. |
| 25 | Server A muốn gọi B thay user không có KCD | Delegation fail; không tự impersonate. |
| 26 | CAS hoặc SAML IdP dùng Kerberos nội bộ | SaaS chỉ nhận CAS/SAML/OIDC artifact tương ứng, không raw AP-REQ. |
| 27 | Authorization token bị ghi vào access log | Security QA fail; cần redact. |
| 28 | Service chạy qua URL http://localhost | Không tự có SPN HTTP/intranet.example.org. |
| 29 | GET / public | Không bắt buộc Negotiate theo route policy. |
| 30 | GET /private sau successful Kerberos và local membership | 200 với verified principal, authorization đúng. |

**Test âm tính thành công khi security layer từ chối đúng** chứ không phải khi bỏ ticket verification, TLS, RBAC hoặc session controls để che lỗi.

## 18. Các sai lầm phổ biến

1. **Coi Kerberos là cookie chung cho mọi ứng dụng.** TGT và service tickets khác HttpSession.
2. **Nghĩ domain-login bảo đảm mọi browser/URL đều SSO.** Cần intranet allowlist, credentials, SPN.
3. **Đồng nhất SPNEGO Negotiate với Kerberos đã được xác minh.** Negotiation có thể khác mechanism.
4. **Cho rằng Kerberos mã hóa toàn bộ HTTP.** Vẫn phải dùng HTTPS.
5. **Đăng ký SPN bằng URL có https:// hoặc /private.** SPN thường là HTTP/hostname.
6. **Gắn cùng SPN vào nhiều AD accounts.** Có thể gây principal ambiguity và key mismatch.
7. **Tin DNS aliases luôn map về SPN gốc.** Cần test canonicalization.
8. **Coi keytab là public certificate.** Nó chứa secret service keys.
9. **Gửi TGT trực tiếp tới web server.** Browser dùng service ticket/GSS context.
10. **Bỏ qua clock skew, kvno, enctype.** Chúng ảnh hưởng ticket accept.
11. **Chỉ thêm starter-security là có SPNEGO.** Cần extension/filter/provider.
12. **Coi SpnegoEntryPoint tạo Authentication.** Nó chỉ gửi challenge.
13. **Không set SecurityContextRepository cho custom filter.** Authentication có thể không persist.
14. **Bỏ local UserDetailsService/permission vì KDC đã tin user.** Authentication khác authorization.
15. **Kết luận local logout phải xóa TGT.** Hai vòng đời riêng.
16. **Dùng unconstrained delegation cho double-hop.** Vi phạm least privilege.
17. **Để service account là Domain Admin.** Không cần và tăng rủi ro.
18. **Tắt TLS hoặc Kerberos checks để SSO “pass”.** Không an toàn.
19. **Log raw Authorization Negotiate token hoặc keytab.** Rò credentials.
20. **Nhầm SAMLResponse/OIDC Token với Kerberos AP-REQ.** Protocol khác nhau.

## 19. Checklist production

**KDC / browser / mạng**

- [ ] Realm, client principal, server SPN, DNS/FQDN đúng.
- [ ] AD/MIT KDC, browser allowlist và credential cache đã kiểm.
- [ ] SPN duy nhất, keytab đúng key/kvno/enctype, synchronized time.
- [ ] Không bật weak crypto hoặc fallback không phê duyệt.
- [ ] Cross-realm/delegation policy có owner, scope, audit.

**Spring và app**

- [ ] Spring Kerberos extension đúng version family.
- [ ] SpnegoEntryPoint, filter, ProviderManager, KerberosServiceAuthenticationProvider và SunJaasKerberosTicketValidator được nối đúng.
- [ ] Custom filter có SecurityContextRepository/session fixation strategy.
- [ ] UserDetailsService map verified principal sang local account active, roles scoped.
- [ ] HTTPS, CSRF, cookie security, LB/session persistence và fail-closed behavior.
- [ ] Kerberos-only policy thực sự kiểm mechanism và không downgrade lặng lẽ.

**QA / vận hành**

- [ ] Test 401 challenge, Negotiate response, accepted context và local 403.
- [ ] Test alias, SPN duplicate, kvno rotation, clock skew, ticket expiry, KDC offline.
- [ ] Test multi-node, logout/relogin, browser không domain-joined.
- [ ] Bảo vệ keytab/tickets/credentials khỏi logs và backups không được phép.
- [ ] Có phương án OIDC/SAML2 bridge cho SaaS/external devices và KCD riêng cho backend hop.

## 20. Câu hỏi tự kiểm tra

**1. Vì sao người dùng login domain một lần có thể mở nhiều apps intranet mà không gõ lại password?**  
Vì client có TGT và xin service ticket riêng cho từng SPN, browser/GSS dùng tickets để xác thực với từng app.

**2. HTTP Authorization: Negotiate đã đủ xác nhận user là Kerberos principal chưa?**  
Chưa. Server phải kiểm GSS token/context bằng service keys và policy, kiểm mechanism thật rồi mới map account.

**3. TGT khác service ticket thế nào?**  
TGT cho phép xin tickets từ TGS; service ticket dành cho service principal cụ thể để thực hiện AP authentication.

**4. Tại sao HTTPS và keytab đều cần?**  
HTTPS bảo vệ kênh HTTP, keytab chứa Kerberos service key để server xác minh ticket. Hai lớp không thay thế nhau.

**5. Vì sao HTTPS alias portal.example.org có thể lỗi trong khi intranet.example.org chạy được?**  
Browser có thể xin SPN theo alias, nhưng account/keytab không có đúng service principal. Cần đối chiếu DNS/SPN và client canonicalization.

**6. Ticket Kerberos pass nhưng /admin trả 403, có nghĩa SSO hỏng không?**  
Không. Local user/role/resource authorization có thể deny người đã xác thực.

**7. Vì sao custom SpnegoFilter cần SecurityContextRepository?**  
Nếu muốn stateful session ở Spring Security 6.x, filter phải lưu Authentication sau successful GSS; nếu không request sau có thể trở lại anonymous.

**8. Browser logout app có làm mất Windows TGT không?**  
Không. Local HttpSession và client Kerberos cache là hai phạm vi; browser có thể login lại im lặng.

**9. Kerberos SSO tự làm Web A có quyền gọi DB B thay user không?**  
Không. Cần KCD/S4U hoặc cơ chế service-to-service/delegation riêng.

**10. SaaS dùng SAML2 có phải triển khai keytab chỉ vì IdP dùng Kerberos nội bộ không?**  
Không. SaaS SP kiểm SAML2 protocol, trong khi IdP dùng Kerberos để xác thực user tại phía IdP.

## 21. Nguồn tham khảo chính thống

1. [RFC 4120 — Kerberos V5](https://www.rfc-editor.org/rfc/rfc4120): AS/TGS/AP exchanges, tickets, authenticators, replay và lifetime.
2. [RFC 4559 — SPNEGO-based Kerberos and NTLM HTTP Authentication](https://www.rfc-editor.org/rfc/rfc4559): WWW-Authenticate/Authorization Negotiate, 401 flow và giới hạn bảo vệ HTTP.
3. [RFC 4178 — SPNEGO](https://www.rfc-editor.org/rfc/rfc4178): mechanism negotiation.
4. [RFC 4121 — Kerberos GSS-API mechanism](https://www.rfc-editor.org/rfc/rfc4121): GSS security contexts/tokens.
5. [MIT Kerberos — Enctypes and tickets](https://web.mit.edu/kerberos/www/krb5-latest/doc/admin/enctypes.html): AS/TGS, service key, session key.
6. [MIT Kerberos — kinit](https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/kinit.html), [klist](https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/klist.html), [kvno](https://web.mit.edu/kerberos/www/krb5-latest/doc/user/user_commands/kvno.html): CLI diagnostics.
7. [Oracle Java 17 — Krb5LoginModule](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.security.auth/com/sun/security/auth/module/Krb5LoginModule.html): keyTab, principal, storeKey và isInitiator.
8. [Oracle — JAAS và Java GSS-API](https://docs.oracle.com/en/java/javase/17/security/use-jaas-login-utility-and-java-gss-api-secure-message-exchanges.html): service principals, JAAS acceptor.
9. [Spring Security Kerberos Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): KerberosServiceAuthenticationProvider, SpnegoEntryPoint, SunJaasKerberosTicketValidator.
10. [Spring Security Kerberos 2.1.1 — SpnegoAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security-kerberos/docs/2.1.1/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): SecurityContextRepository, session strategy, token processing.
11. [Spring Security Kerberos — Spring Project](https://spring.io/projects/spring-security-kerberos/): extension/version family.
12. [Microsoft Learn — setspn](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/setspn): SPN registration và duplicate detection.
13. [Microsoft Edge — AuthServerAllowlist](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authserverallowlist): browser integrated authentication.
14. [Microsoft Entra — Kerberos constrained delegation](https://learn.microsoft.com/en-us/entra/architecture/auth-kcd): double-hop/KCD và remote access.

**Kết luận:** Kerberos mang lại SSO intranet nhờ **client TGT → service ticket theo SPN → browser SPNEGO/GSS → server acceptor dùng keytab**, chứ không nhờ dùng chung mật khẩu hay HttpSession. Spring Security nhận identity đã xác thực, nhưng **HTTPS, local account/role authorization, session security, SPN/keytab/DNS/clock, replay protection và delegation policy** vẫn phải quản lý độc lập. Khi ra Internet/SaaS, Kerberos thường được dùng ở **phía enterprise IdP**, còn ứng dụng ngoài nhận **SAML2/OIDC**.
