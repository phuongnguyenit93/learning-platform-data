# Bảo vệ kết nối HTTPS giữa ứng dụng và CAS server

Trong **Central Authentication Service (CAS)**, một ứng dụng dùng **Spring Security CAS client** không chỉ chuyển hướng trình duyệt đến CAS server để người dùng đăng nhập. Sau khi nhận **Service Ticket (ST)**, ứng dụng còn tự gửi yêu cầu **server-to-server** đến CAS để xác minh ticket. Vì thế, bảo vệ HTTPS cho CAS bao gồm **hai khách hàng TLS khác nhau**: trình duyệt của người dùng và **JVM chạy ứng dụng Spring**.

Một trình duyệt hiển thị khóa HTTPS tại `https://sso.example.org` **không chứng minh** JVM của Portal tin được certificate đó. Browser và JVM có thể dùng truststore khác nhau. Ngược lại, nếu CAS client đã bị cấu hình bỏ qua certificate/hostname checks, một người đứng giữa (MITM) có thể phát XML `authenticationSuccess` giả để ứng dụng tin một người dùng không hề được CAS xác thực.

**Mục tiêu:** thiết lập ranh giới tin cậy CAS đúng bằng HTTPS/TLS, PKIX certificate chain, Subject Alternative Name (SAN), truststore, callback URL, reverse proxy và kiểm thử âm tính. Bài thuộc nhóm **Tích hợp CAS**, dùng ví dụ Spring Security Servlet, Apereo CAS và Java 17+. Các tên miền `.example` chỉ dùng minh họa, không phải endpoint thực tế.

## 1. Ba bước HTTPS cốt lõi trong đăng nhập CAS

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring Security Portal
    participant CAS as CAS Server
    U->>SP: HTTPS GET /reports
    SP-->>U: Redirect tới CAS login và service URL
    U->>CAS: HTTPS GET /cas/login?service=...
    CAS->>CAS: Xác thực người dùng / dùng TGC
    CAS-->>U: Redirect tới service với ST-...
    U->>SP: HTTPS GET /login/cas?ticket=ST-...
    SP->>CAS: HTTPS GET /cas/serviceValidate?ticket=...&service=...
    CAS->>CAS: Kiểm ST, service, timeout và một lần sử dụng
    CAS-->>SP: HTTPS XML authenticationSuccess / failure
    SP->>SP: Tạo Authentication, kiểm local user/role
    SP-->>U: Session cookie an toàn
~~~

Điều cần hiểu:

1. **Browser → SP:** browser kiểm TLS certificate của Portal.
2. **Browser → CAS:** browser kiểm TLS certificate của CAS khi truy cập login UI.
3. **SP → CAS:** **Java HTTP client bên trong Spring** kiểm CAS certificate khi xác minh ST qua `TicketValidator`. Đây là đường back-channel quyết định ứng dụng có được tin XML response hay không.

Nếu dùng **CAS Proxy Authentication**, có chặng thứ tư: **CAS → SP** khi CAS gọi `pgtUrl` (Proxy Granting Ticket callback). Lúc đó CAS trở thành HTTPS client và phải kiểm certificate của SP.

### Bảng người kiểm chứng thư

| Kết nối | HTTPS client | HTTPS server | Nơi cần cấu hình trust |
| --- | --- | --- | --- |
| Browser → Portal | Browser | SP / load balancer | Browser/OS trust store |
| Browser → CAS Login | Browser | CAS / ingress | Browser/OS trust store |
| **Spring → CAS Validator** | **JVM của SP** | **CAS server** | **JVM hoặc TLS transport của CAS client** |
| CAS → SP proxy callback, nếu dùng | CAS HTTP client | SP proxy receptor | **Truststore phía CAS** |
| Ingress → SP/CAS backend | Reverse proxy | Backend | Trust cấu hình trên proxy, nếu TLS được dùng |

**Không dùng certificate SP để giải lỗi `PKIX` trên SP→CAS**, trừ khi đó thực sự là CA chung được xác minh. Đường SP→CAS cần trust **CAS identity**; đường CAS→SP cần trust **SP identity**.

## 2. CAS Protocol: ticket validation và vai trò của HTTPS

CAS Protocol dùng những thành phần sau:

- **Ticket Granting Ticket (TGT):** đại diện phiên SSO ở CAS; browser thường dùng cookie `TGC` để tham chiếu.
- **Service Ticket (ST):** giá trị opaque, ngắn hạn, phát cho **một service URL cụ thể**, thường dùng một lần.
- **`service` parameter:** callback URL mà CAS phát ticket cho nó; phải khớp khi validate.
- **`/serviceValidate`:** endpoint CAS 2.0 trả response XML.
- **`/p3/serviceValidate`:** biến thể CAS 3 trả thêm attributes theo cấu hình service/attribute release.
- **`/proxyValidate`:** endpoint cho các proxy flows được phê duyệt, không phải mọi app đều cần.

Các URL phân biệt:

~~~text
CAS server base:
  https://sso.example.org/cas

CAS login:
  https://sso.example.org/cas/login

CAS ticket validator:
  https://sso.example.org/cas/serviceValidate
  hoặc https://sso.example.org/cas/p3/serviceValidate

Spring application's registered CAS service callback:
  https://portal.example.com/login/cas
~~~

Một request SP→CAS khi validate:

~~~http
GET /cas/serviceValidate?service=https%3A%2F%2Fportal.example.com%2Flogin%2Fcas&ticket=ST-DEMO HTTP/1.1
Host: sso.example.org
Accept: application/xml
~~~

CAS trả XML, ví dụ:

~~~xml
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>employee-123</cas:user>
  </cas:authenticationSuccess>
</cas:serviceResponse>
~~~

**ST-DEMO và XML trên chỉ minh họa, không phải giao dịch thật.** Một kẻ tấn công có thể tự viết XML trông như vậy. Spring chỉ được dựng Authentication khi **ticket validator chuẩn** thực sự đã gửi yêu cầu qua **HTTPS đến CAS server tin cậy**, kiểm ticket/service, nhận và parse response hợp lệ. Không tạo authentication bằng một form parameter `user=employee-123` hoặc bằng HTTP response chưa qua trust check.

### Vì sao HTTPS vẫn cần ngay cả khi ticket “một lần”?

Service Ticket vẫn là credential nhạy cảm. Một attacker trên mạng có thể đánh cắp ST trước khi SP kịp validate, hoặc nếu có thể giả CAS validator endpoint, có thể phát authenticationSuccess giả. Ticket binding, one-time usage và TLS bảo vệ các điều kiện khác nhau:

| Cơ chế | Vai trò |
| --- | --- |
| **HTTPS + PKIX + hostname** | Xác thực CAS endpoint thật và bảo vệ nội dung request/response |
| **Service binding** | ST chỉ dùng được cho service đã cấp |
| **One-time/TTL** | Giảm replay ST và thời gian sử dụng |
| **CAS registered-service policy** | Chỉ service được duyệt mới tham gia SSO |
| **Spring local authorization** | Quyền ứng dụng/tenant được xét sau khi CAS xác thực |

Không tắt `service` matching hoặc chấp nhận ST cũ chỉ vì “đã có HTTPS”.

## 3. HTTPS thực sự xác minh điều gì?

Khi CAS client kết nối `https://sso.example.org/cas`, quá trình TLS phải bảo đảm:

1. **Certificate chain:** certificate CAS được nối qua những intermediate CA cần thiết đến **CA trust anchor** đã được client phê duyệt.
2. **Validity:** certificate còn hiệu lực theo `NotBefore` và `NotAfter`; đồng hồ host đáng tin.
3. **Server name matching:** certificate chứa **SAN dNSName=sso.example.org** hoặc danh tính phù hợp quy tắc HTTPS; không chấp nhận certificate chỉ dành cho hostname khác.
4. **Ký và policy PKI:** chữ ký chain, key usage và extended key usage phù hợp, thuật toán/độ dài khóa được phép.
5. **TLS protocol/cipher:** không đàm phán version/cipher bị vô hiệu theo JDK/security baseline.
6. **Revocation (nếu bắt buộc):** áp chính sách OCSP/CRL và failure mode theo PKI; không mặc định mọi JDK kiểm revocation giống nhau.
7. **Đích thực:** kết nối gửi đến đúng CAS base URL đã được cấu hình, không phải một server bất kỳ do user request chỉ định.

**Chỉ có chuỗi bắt đầu bằng `https://` là chưa đủ**. Nếu code cài `X509TrustManager` chấp nhận mọi CA hoặc `HostnameVerifier` luôn trả true, HTTPS mất khả năng chứng minh server chính là CAS đáng tin.

### Certificate chain và hostname là hai phép kiểm khác nhau

Ví dụ:

~~~text
Target URL: https://sso.example.org/cas

Certificate A:
  Valid public CA chain: YES
  SAN: other.example.org
  Result: REJECT (hostname mismatch)

Certificate B:
  SAN: sso.example.org
  Trusted issuer/root: NO
  Result: REJECT (PKIX path building failure)

Certificate C:
  SAN: sso.example.org
  Trusted chain: YES
  Within validity window: YES
  TLS algorithms allowed: YES
  Result: may proceed to HTTP/CAS validation
~~~

Không có certificate nào tự chứng minh ST được chấp nhận; trường hợp C **mới chỉ vượt TLS**, ứng dụng còn phải kiểm CAS ticket response.

### SAN, CN và địa chỉ IP

Dùng Subject Alternative Name, không trông chờ riêng `CN=sso.example.org` khi cấp certificate mới. Nếu client kết nối bằng IP address, certificate cần **IP SAN** tương ứng theo quy tắc HTTPS. Không sửa hostname mismatch bằng cách tắt SNI/hostname verifier rồi giữ nguyên trong production.

Nếu trước reverse proxy có nhiều vhosts, `Server Name Indication (SNI)` giúp proxy chọn certificate đúng host; `openssl s_client -servername sso.example.org` hữu ích khi chẩn đoán. Nếu proxy trả default certificate của website khác, sửa SNI/vhost configuration.

## 4. Truststore không giống keystore

| Thành phần | Chứa dữ liệu | Mục đích |
| --- | --- | --- |
| **SP JVM truststore** | Trusted CA certificates/certificates | SP kiểm CAS certificate khi validate ticket |
| **CAS server keystore** | CAS private key + certificate chain | CAS hoặc servlet container terminate inbound TLS |
| **CAS proxy/LB keystore** | Public hostname private key + certificate | Ingress terminate TLS thay CAS |
| **SP inbound keystore** | SP private key + certificate | Browser/CAS callback xác thực HTTPS của SP |
| **SP outbound client keystore** | SP client private key/certificate nếu mTLS | SP chứng minh identity với CAS server khi mTLS được yêu cầu |
| **CAS-side truststore** | Trusted CA của CAS outbound clients | CAS kiểm `pgtUrl`/upstream service khi nó là HTTPS client |

**`server.ssl.*` trong Spring Boot** thường cấu hình TLS **inbound** của web server, không tự tạo tin cậy cho **outbound Cas20ServiceTicketValidator**. Cũng vậy, `spring.ssl.bundle.*` chỉ định nghĩa một bundle; **phải nối bundle vào HTTP client cụ thể** nếu thư viện không auto-apply.

### Truststore mặc định trong Java 17

Oracle JSSE mô tả khi Java không chỉ định `javax.net.ssl.trustStore`, JVM thường tìm `jssecacerts` rồi `cacerts` dưới `java.home/lib/security`. Trong containers và các JDK distributions, đường dẫn và tập CA có thể khác máy dev.

Nếu đặt `-Djavax.net.ssl.trustStore=/path/cas-truststore.p12` thì **truststore được chỉ định có thể thay nguồn trust mặc định**, không tự merge toàn bộ public roots. Vì thế app gọi một API khác có thể lỗi nếu truststore riêng chỉ chứa internal CA. Khi sử dụng global truststore, phải cân nhắc blast radius và nhu cầu trust theo từng outbound client.

**Quan trọng:** file custom truststore được khai báo nhưng không tồn tại có thể làm trust manager mặc định thiếu mọi trust anchors; xác nhận file thật, permissions và JVM process arguments ở **đúng pod/node**.

## 5. Tạo truststore PKCS12 với CA đã được phê duyệt

Khi CAS dùng CA nội bộ, đội PKI cấp root/intermediate certificate qua **kênh quản trị đáng tin cậy**, kèm SHA-256 fingerprint để đối chiếu độc lập. Sau khi được phê duyệt:

~~~bash
keytool -importcert \
  -alias corporate-cas-root \
  -file corp-root-ca.pem \
  -keystore /etc/portal/security/cas-truststore.p12 \
  -storetype PKCS12
~~~

Lệnh hỏi password/xác nhận trust theo cấu hình, vì vậy không cần đưa password vào dòng command lưu history. Kiểm lại:

~~~bash
keytool -list -v \
  -keystore /etc/portal/security/cas-truststore.p12 \
  -storetype PKCS12
~~~

Kiểm Subject, Issuer, Validity, Basic Constraints, SHA-256 fingerprint và các aliases. **Không nhập certificate mới lấy từ một endpoint đang bị nghi MITM mà chưa đối chiếu out-of-band**. Việc import đó có thể vô tình biến key của attacker thành root tin cậy.

### Cấu hình Java JSSE mặc định

Ví dụ JVM options (đưa vào phương thức quản lý secrets được phê duyệt):

~~~text
-Djavax.net.ssl.trustStore=/etc/portal/security/cas-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=[securely injected value]
~~~

Đây là **mẫu options**, không phải các thuộc tính CAS-specific tự động được Spring Boot đọc. Không đặt password thật vào public process command line, CI logs hoặc repository. Có thể dùng protected runtime config/secret management phù hợp môi trường; xem lại mô hình bảo vệ vì JVM options có thể bị lộ qua chẩn đoán.

**Lưu ý:** liệu Apereo CAS client dùng JVM default SSLContext, SSL socket factory riêng hay HTTP transport tùy biến phụ thuộc version/adapter. Cần kiểm implementation **đang chạy thật**: không khẳng định chỉ định `javax.net.ssl.trustStore` đã áp đúng nếu một transport được override.

### Vì sao không nên chỉnh bừa cacerts của JDK?

Thêm CA vào JDK `cacerts` toàn cục có thể tác động mọi outbound HTTPS connections của toàn JVM hoặc cả runtime image. Ưu tiên truststore/container secret được quản trị, rollout cùng ứng dụng, có checksum và rollback. Nếu có shared truststore do tổ chức quản lý, cần vòng đời cập nhật CA, kiểm permission và bảo đảm mọi node dùng cùng cấu hình.

## 6. Spring Boot SSL Bundles và giới hạn auto-config

Spring Boot hiện đại cho phép định nghĩa named SSL bundles:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        cas-client:
          truststore:
            location: "file:/etc/portal/security/cas-truststore.p12"
            password: "${CAS_TRUSTSTORE_PASSWORD}"
            type: "PKCS12"
~~~

Trong ứng dụng Spring, `SslBundles` có thể lấy bundle:

~~~java
SslBundle bundle = sslBundles.getBundle("cas-client");
SSLContext context = bundle.createSslContext();
~~~

**Đây là API fragment**, không chạy độc lập và phải import các type của Spring Boot/JSSE. Cần tích hợp `SSLContext` vào **HTTP client mà CAS TicketValidator thật dùng** qua API/adapter phù hợp version. Việc có bundle nhưng CAS client vẫn sử dụng JSSE default truststore sẽ không giải lỗi.

Phân biệt:

- **`server.ssl.bundle`**: thường dùng bảo vệ **inbound server TLS**.
- **`spring.ssl.bundle.jks.cas-client.truststore`**: mô tả trust material, nhưng không tự kết nối nó với mọi CAS client.
- **`javax.net.ssl.trustStore`**: cấu hình JSSE default trust managers cấp JVM, ảnh hưởng các HTTP clients sử dụng defaults.
- **Per-client SSLContext**: giảm phạm vi ảnh hưởng nhưng yêu cầu wiring chính xác trong thư viện CAS client.

Nếu ứng dụng phải gọi cả CAS nội bộ và public APIs, một per-client SSLContext được quản trị có thể thích hợp hơn truststore global rất hẹp — miễn là CAS HTTP transport thật sự sử dụng nó.

## 7. Các thành phần Spring Security CAS

Spring Security Servlet có module CAS riêng, khác `oauth2Login` và `saml2Login`:

- `CasAuthenticationEntryPoint` tạo redirect browser đến CAS login và gửi `service`.
- `ServiceProperties` chứa **SP service callback URL**, ví dụ `https://portal.example.com/login/cas`.
- `CasAuthenticationFilter` nhận ST ở callback và gửi token chưa xác thực tới AuthenticationManager.
- `CasAuthenticationProvider` kiểm ST bằng `TicketValidator` và tạo result Authentication.
- `Cas20ServiceTicketValidator` thuộc Apereo CAS client làm ticket validation với CAS server.
- `CasAuthenticationToken` đại diện kết quả đã xác thực trong Spring Security; một số class token request thay đổi theo Security version.
- `UserDetailsService` / `AuthenticationUserDetailsService` giúp ánh xạ principal đã xác minh sang local account và authorities.

Tài liệu Spring Security cho biết `CasAuthenticationFilter` thường monitor `/login/cas` và `ServiceProperties.service` phải nhất quán với callback URL thật.

### Hai URL không được đảo ngược

~~~text
Spring ServiceProperties.service:
  https://portal.example.com/login/cas
  (URL của ứng dụng, nơi browser quay về)

CAS validator base:
  https://sso.example.org/cas
  (URL của CAS, nơi Java gọi ticket validation)
~~~

**Không đặt `ServiceProperties.service` bằng `https://sso.example.org/cas/serviceValidate`**: đó là endpoint validation phía CAS, không phải callback của SP. Nếu CAS cấp ST cho service khác URI SP dùng khi validate, CAS sẽ từ chối `INVALID_SERVICE` hoặc mã lỗi tương ứng.

### Bean JavaConfig minh họa

~~~java
import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.apereo.cas.client.validation.TicketValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.cas.ServiceProperties;

@Configuration
public class CasHttpsBaseConfig {

    private static final String CAS_BASE =
            "https://sso.example.org/cas";
    private static final String SP_CALLBACK =
            "https://portal.example.com/login/cas";

    @Bean
    ServiceProperties serviceProperties() {
        ServiceProperties properties = new ServiceProperties();
        properties.setService(SP_CALLBACK);
        properties.setSendRenew(false);
        return properties;
    }

    @Bean
    TicketValidator casTicketValidator() {
        return new Cas20ServiceTicketValidator(CAS_BASE);
    }
}
~~~

**Đây chỉ là fragment cấu hình**, yêu cầu Spring Security CAS module, Apereo CAS client đúng version và những beans khác để hoàn tất auth: `CasAuthenticationEntryPoint`, `CasAuthenticationFilter`, `CasAuthenticationProvider`, AuthenticationManager và local user service. Nó không tự tạo login flow khi đưa vào một file trống. Domain .example không chạy thật, và trust material phải được cấu hình cho HTTP transport outbound.

Thành phần JavaConfig có thể phụ thuộc version; kiểm Javadoc ứng với `spring-security-cas`/CAS client đã resolve. Spring Security 6/7 dùng `jakarta.servlet`, trong khi nhiều sample CAS cũ dùng `javax.servlet` hoặc XML namespaces khác. Đừng sao chép code 3.x và coi là tương thích.

### Cấu hình tương quan bean

~~~text
CasAuthenticationEntryPoint:
  loginUrl         = https://sso.example.org/cas/login
  serviceProperties = ServiceProperties

CasAuthenticationFilter:
  filterProcessesUrl = /login/cas
  authenticationManager = ProviderManager

CasAuthenticationProvider:
  ticketValidator = Cas20ServiceTicketValidator(CAS_BASE)
  serviceProperties = ServiceProperties
  authenticationUserDetailsService = local user mapping
  key = unique provider identifier

Spring outbound TLS:
  CAS hostname allowed and resolved to approved destination
  TLS trust manager validates chain and SAN
  HTTP transport validates CAS ticket over HTTPS
~~~

**Không tắt ticket validation vì bị lỗi TLS**. Nếu CAS protocol 3 cần attributes, dùng validator CAS3 được thư viện hỗ trợ theo version; nhiệm vụ HTTPS trust/hostname vẫn phải giữ nguyên.

## 8. TLS ở reverse proxy và internal network

Mô hình thường gặp:

~~~text
Browser / Spring CAS client
       | HTTPS public
       v
CAS ingress / reverse proxy / LB
       | HTTPS backend (khi threat model yêu cầu)
       v
CAS server node

Browser
       | HTTPS public
       v
Portal ingress
       | HTTPS backend (khi threat model yêu cầu)
       v
Spring servlet app
~~~

Nếu TLS terminate tại proxy:

1. Certificate **public CAS hostname** thường nằm ở proxy, đó là certificate **Spring CAS client** nhìn thấy.
2. Backside proxy→CAS node có thể là HTTPS/mTLS hoặc HTTP trong mạng riêng; lựa chọn cần được đánh giá theo zero trust và network threat model.
3. Nếu backside HTTPS, proxy phải **xác minh backend server cert**, không đặt một chế độ “verify off” tùy tiện.
4. CAS và SP phải dựng public service URLs chính xác, bất kể backend chạy ở `http://pod:8080`.
5. Header `X-Forwarded-Proto`/`X-Forwarded-Host` chỉ đáng tin khi ingress **strip/replace** mọi bản do Internet gửi và chỉ cho trusted proxies truy cập backend.

Spring Boot có thể có:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
~~~

**Cấu hình này không tự tạo trust boundary.** Phải cấu hình mạng/proxy đúng; nếu backend tin `X-Forwarded-Host: evil.example.net` do client gửi, callback/login redirect có thể bị chuyển hướng sai.

Một trường hợp phổ biến:

~~~text
Browser-facing SP: https://portal.example.com/login/cas
Internal app:      http://portal-app:8080/login/cas

CAS issued ticket for public HTTPS callback.
Spring validates using internal HTTP callback by mistake.
Result: INVALID_SERVICE or login loop.
~~~

Giải pháp là cấu hình `ServiceProperties.service` và registered service theo **public URL**, kiểm proxy headers/host/path và các routes. Không bỏ HTTPS ở public callback để dễ khớp.

### Cookie và HSTS

- Session cookie nên dùng `Secure` và `HttpOnly`; SameSite được chọn theo browser flow.
- CAS TGC/session cookie không được chia sẻ trực tiếp cho SP; mỗi ứng dụng/domain sở hữu phiên riêng.
- `Strict-Transport-Security` có thể buộc browser ưu tiên HTTPS sau khi nhận policy; **HSTS không thay thế TLS verification của Java back-channel**.
- `includeSubDomains`/preload HSTS chỉ bật nếu kiểm soát toàn bộ subdomains và có kế hoạch rollout/rollback.
- Không gửi ST/TGC qua redirect sang HTTP hoặc thêm ticket vào các URL của bên thứ ba.

## 9. CAS proxy authentication: đường HTTPS ngược

CAS có hỗ trợ Proxy Granting Ticket (PGT) khi service cần đại diện người dùng gọi service khác. Một luồng PGT có thể:

1. Spring CAS client validate ST và gửi kèm `pgtUrl=https://portal.example.com/login/cas/proxyreceptor`.
2. CAS kiểm service/allowed proxy policy.
3. **CAS tự mở HTTPS tới SP proxy receptor**.
4. CAS xác minh chứng thư SP, gọi callback theo protocol và liên hệ PGT với PGTIOU.
5. Ứng dụng có thể dùng PGT/PT theo quyền đã cho phép.

Khác với back-channel SP→CAS, **CAS phải tin certificate SP** ở bước này. Apereo CAS 7.3.x mô tả khi proxy callback endpoint có cert invalid/self-signed chưa trust/chain thiếu/expired, CAS có thể từ chối callback.

**PGT callback đòi HTTPS và peer trust theo CAS protocol**, không phải có thể chấp nhận HTTP cho thuận tiện. Không bật `acceptAnyProxy=true` chỉ để sample hoạt động nếu chính sách không cho phép proxy đại trà. Nếu dự án không sử dụng CAS proxy, không cần mở PGT endpoints/credential release.

### Ma trận phân quyền certificate

| Trường hợp | Chứng thư cần kiểm | Bên giữ truststore |
| --- | --- | --- |
| Spring validate Service Ticket | CAS public server certificate | Spring JVM/CAS client |
| CAS gọi PGT proxy receptor | SP public server certificate | CAS JVM/CAS HTTP client |
| Browser đến CAS login | CAS public certificate | Browser/OS |
| Browser đến SP portal | SP public certificate | Browser/OS |

Một lỗi vận hành: CAS→SP callback fail vì cert SP không trust, nhưng đội dev chỉ sửa SP-side truststore. Hãy xác định **hướng request** trước khi cấu hình certificate.

## 10. Có cần mutual TLS (mTLS) cho CAS?

**CAS Protocol không mặc định bắt buộc mTLS**. Thường SP xác thực CAS TLS server. Doanh nghiệp có thể thêm mTLS trên đường SP→CAS, proxy→backend hoặc CAS→SP callback khi threat model yêu cầu.

Nếu token validation endpoint yêu cầu client certificate:

- SP có **keystore** chứa client private key + certificate.
- CAS/ingress có **truststore** để xác minh client certificate và policy.
- SP **vẫn phải** có truststore để xác minh certificate CAS.
- Các phần client certificate và server certificate có lifecycles/issuers/KeyUsage khác nhau.
- HTTP transport thực sự gọi CAS phải được tạo với SSLContext có KeyManagers phù hợp.

**Đừng nhầm `server.ssl.client-auth` trong Spring Boot** với mTLS khi Spring **đi ra** CAS: cấu hình đó thường dành cho **inbound** kết nối đến Spring server. Outbound mTLS cần cấu hình riêng trên CAS client transport.

**mTLS không thay Service Ticket verification**. Client certificate chứng minh một máy/service gọi CAS endpoint theo policy, nhưng không chứng minh user mà browser vừa đăng nhập.

## 11. TLS 1.2/1.3, cipher suites và thuật toán

JDK 17 hỗ trợ TLS 1.2 và TLS 1.3. Các triển khai hiện đại thường nên tắt TLS 1.0/1.1 và cipher suites yếu; Java có `jdk.tls.disabledAlgorithms` ảnh hưởng thuật toán/protocol được dùng. Tùy JDK vendor/patch, kết quả thực tế cần đo bằng handshake, không suy từ một ví dụ tài liệu.

- Ưu tiên TLS 1.3, cho phép TLS 1.2 khi tương thích theo baseline.
- Không khôi phục SSLv3/TLS1.0/TLS1.1 hoặc 3DES/RC4 để giải lỗi login.
- Cần cấp server certificates với SAN và thuật toán phù hợp PKI.
- Đánh giá signature chain và cipher negotiation, không chỉ URL.
- Cập nhật runtime JDK security patches và các CAS client dependencies.
- Kiểm TLS handshake thực qua LB/ingress trên môi trường staging, không chỉ cấu hình file.

**Không trộn TLS signing với SAML XML signature**: CAS Protocol thường dựa vào HTTPS + Service Ticket validation; nếu Apereo CAS cũng làm OIDC/SAML IdP, thì token/assertion validation lại theo giao thức tương ứng.

## 12. Java 17 tự chạy: kiểm URL CAS và SP callback trước deployment

Đây là chương trình Java 17 **biên dịch/chạy không cần thư viện ngoài**, dùng để phát hiện config HTTPS sai trước khi kết nối mạng. Nó so khớp scheme, hostname allowlist, port, exact path và từ chối userinfo/query/fragment trong **base URL cấu hình**.

**Nó không thực hiện TLS handshake, không kiểm certificate, không xác minh CAS ticket**; kết quả ALLOW chỉ có nghĩa **đúng cấu trúc policy URL**. Không dùng demo để thay `HttpsURLConnection`/`HttpClient` TLS checks.

Tạo file **`CasHttpsPolicyDemo.java`**:

~~~java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

public class CasHttpsPolicyDemo {

    static String check(String candidate, String host, String path) {
        final URI uri;
        try {
            uri = new URI(candidate);
        } catch (URISyntaxException ex) {
            return "DENY: malformed URI";
        }

        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            return "DENY: HTTPS required";
        }
        if (uri.getRawUserInfo() != null) {
            return "DENY: userinfo forbidden";
        }
        if (uri.getRawQuery() != null || uri.getRawFragment() != null) {
            return "DENY: unexpected query or fragment";
        }
        if (uri.getHost() == null
                || !host.equals(uri.getHost().toLowerCase(Locale.ROOT))) {
            return "DENY: unapproved host";
        }
        if (uri.getPort() != -1 && uri.getPort() != 443) {
            return "DENY: unapproved port";
        }
        if (!path.equals(uri.getRawPath())) {
            return "DENY: unexpected path";
        }
        return "ALLOW: approved URL policy";
    }

    public static void main(String[] args) {
        System.out.println("Good CAS: " + check(
                "https://sso.example.org/cas", "sso.example.org", "/cas"));

        System.out.println("HTTP CAS: " + check(
                "http://sso.example.org/cas", "sso.example.org", "/cas"));

        System.out.println("Other host: " + check(
                "https://other.example.org/cas", "sso.example.org", "/cas"));

        System.out.println("Wrong port: " + check(
                "https://sso.example.org:8443/cas",
                "sso.example.org", "/cas"));

        System.out.println("Userinfo: " + check(
                "https://user:secret@sso.example.org/cas",
                "sso.example.org", "/cas"));

        System.out.println("Query on CAS base: " + check(
                "https://sso.example.org/cas?ticket=ST-DEMO",
                "sso.example.org", "/cas"));

        System.out.println("SP callback: " + check(
                "https://portal.example.com/login/cas",
                "portal.example.com", "/login/cas"));

        System.out.println("Wrong callback: " + check(
                "https://portal.example.com/other",
                "portal.example.com", "/login/cas"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CasHttpsPolicyDemo.java
java CasHttpsPolicyDemo
~~~

**Stdout chính xác:**

~~~text
Good CAS: ALLOW: approved URL policy
HTTP CAS: DENY: HTTPS required
Other host: DENY: unapproved host
Wrong port: DENY: unapproved port
Userinfo: DENY: userinfo forbidden
Query on CAS base: DENY: unexpected query or fragment
SP callback: ALLOW: approved URL policy
Wrong callback: DENY: unexpected path
~~~

**Giải thích:**

- Good CAS được policy chấp thuận nhưng **còn phải kiểm TLS certificate và CAS response thật**.
- HTTP CAS bị từ chối vì thiếu TLS.
- Other host bị từ chối dù tên host có thể sở hữu certificate hợp lệ của một CA khác.
- Wrong port bị từ chối vì policy của **bài tập** chỉ cho port mặc định/443; trong mạng nội bộ có thể phê duyệt HTTPS port khác với cấu hình minh bạch.
- Userinfo ngăn thông tin login được nhét vào URL.
- Query on CAS base: khi cấu hình base URL không nên kèm ticket/query. **CAS TicketValidator thật** được phép tạo request có `?service=...&ticket=...` sau đó.
- SP callback khác CAS base; path sai phải sửa chứ không nới regex service.
- `URI` không kiểm PKIX, SAN, cipher, validity hay network host thực. Không được dùng kết quả ALLOW như chứng chỉ an toàn.

## 13. Java 17 probe HTTPS thật, không tắt certificate verification

Nếu muốn kiểm từ **chính JDK 17/JVM environment**, có thể dùng `HttpClient` và **default JSSE TLS validation**. Chương trình dưới đây **không có stdout cố định** vì kết quả phụ thuộc server thật. Chỉ chạy với một URL CAS login/test endpoint được tổ chức phê duyệt, không chứa Service Ticket.

File `CasTlsProbe.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import javax.net.ssl.SSLSession;

public class CasTlsProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CasTlsProbe <approved-https-url>");
            System.exit(2);
        }

        URI url = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(url.getScheme())
                || url.getHost() == null
                || url.getRawUserInfo() != null) {
            throw new IllegalArgumentException("HTTPS URL required");
        }

        // Chỉ chạy với host đã được admin phê duyệt.
        // Default JSSE: không có trustAll hoặc hostname bypass.
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response =
                client.send(request, HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
        SSLSession tls = response.sslSession().orElseThrow();
        System.out.println("TLS protocol: " + tls.getProtocol());
    }
}
~~~

Chạy khi có CAS test host thật:

~~~bash
javac CasTlsProbe.java
java CasTlsProbe https://sso.your-approved-test-domain.example/cas/login
~~~

Vì tên miền minh họa, phải thay bằng URL thật được quản trị. Nếu certificate không trust, SAN sai hoặc handshake lỗi, chương trình phải fail; không thêm `-k` hay bypass. HTTP 200/302 và protocol TLS chỉ chứng tỏ HTTPS endpoint truy cập được, **không chứng minh một ST đã được CAS xác nhận**. Cần integration test validator tiếp theo.

## 14. Công cụ kiểm chứng tại đúng network/JVM

### openssl s_client

~~~bash
openssl s_client \
  -connect sso.example.org:443 \
  -servername sso.example.org \
  -verify_return_error \
  -showcerts
~~~

Kiểm handshake/chain và SNI. `-verify_return_error` yêu cầu OpenSSL báo khi không verify được certificate theo trust settings của OpenSSL. **OpenSSL có thể dùng CA store khác Java**, vì vậy kết quả OK không bảo đảm JVM cũng OK.

### curl

~~~bash
curl -I --max-time 10 https://sso.example.org/cas/login
~~~

Kiểm HTTP/TLS theo libcurl trust. Không dùng `curl -k` hoặc `--insecure` để kết luận an toàn. Dùng endpoint không chứa ticket/cookie. Curl không thay CAS TicketValidator integration test.

### keytool

~~~bash
keytool -printcert -sslserver sso.example.org:443 -rfc
keytool -list -v \
  -keystore /etc/portal/security/cas-truststore.p12 \
  -storetype PKCS12
~~~

`printcert` giúp xem certificate public endpoint, còn `list` xem trust anchors app sử dụng. Không hiểu nhầm thao tác hiển thị certificate là đã xác minh hostname/CA chain trong app.

### JSSE debug

Trong staging an toàn có thể dùng:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
~~~

Log có thể tiết lộ hostname/certificates và chi tiết nội bộ; hạn chế thời gian, quyền xem và lọc dữ liệu nhạy cảm trước khi gửi support. Nếu truststore đúng trên laptop nhưng lỗi pod, hãy kiểm `java.home`, image version, file mount và JVM options của pod thật.

## 15. Những dấu hiệu lỗi và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| `PKIX path building failed` | JVM không tin CA/chain CAS | Kiểm trusted CA, intermediate chain và đúng runtime truststore |
| `unable to find valid certification path` | Thiếu trust anchor hoặc truststore rỗng/sai | Cấp CA đã phê duyệt, kiểm path/mount/password |
| `No subject alternative names present` | CAS cert không có SAN tương ứng | Cấp lại cert có SAN đúng hostname |
| `No name matching sso.example.org found` | Hostname/SNI/certificate mismatch | Sửa CAS URL, DNS/LB SNI hoặc cert, không tắt verifier |
| `CertificateExpiredException` | Cert hoặc intermediate hết hạn | Renew và rollout hợp lệ |
| `CertificateNotYetValidException` | Cert chưa hiệu lực hoặc clock lệch | Kiểm NTP/validity, không bỏ date checks |
| `handshake_failure` | Cipher/TLS version, client-auth hoặc policy mismatch | Sửa TLS baseline/mTLS configuration, không bật cipher yếu |
| CAS login page hiện nhưng SP login loop | SP→CAS ticket validator bị TLS/network lỗi | Test từ JVM/container và CAS validation, không chỉ browser |
| CAS `INVALID_SERVICE` | `ServiceProperties.service` sai callback | Đồng bộ public URL/registry/proxy |
| CAS `INVALID_TICKET` | Ticket expired/consumed/sai issuer/service | Kiểm ticket lifecycle, không cho replay |
| Proxy callback CAS PGT fail | CAS→SP certificate không trust | Sửa certificate SP và CAS-side truststore |
| Chỉ một node fail | Truststore/JDK/certificate cấu hình không đều | So rollout, config và SSL sessions trên nodes |
| Bật custom truststore làm API khác fail | Truststore thay public default roots | Sửa trust anchors hoặc per-client SSLContext |
| HTTPS 302 thành công nhưng user không được login | HTTP success không thay ticket validation | Xem CAS response, Spring provider và local account/role |
| Spring tạo redirect HTTP thay HTTPS | Trusted Forwarded headers/public host sai | Sửa ingress/proxy và service URL |
| TLS pass nhưng user bị 403 | Local authorization đúng hoặc role/tenant sai | Kiểm policy nghiệp vụ, không quy cho TLS |

**Không chữa lỗi TLS bằng cách bỏ certificate validation hoặc chuyển ticket validation sang HTTP.** Lỗi kết nối TLS phải được xử lý ở trust/chain/hostname/protocol; lỗi CAS service phải xử lý URL/ticket; lỗi authorization phải xử lý quyền local.

## 16. Những anti-pattern phải loại bỏ

### A. Trust-all certificate

~~~java
// MẪU SAI — không dùng:
public void checkServerTrusted(
        java.security.cert.X509Certificate[] chain,
        String authenticationType) {
    // no-op: mọi server certificate đều được chấp nhận
}
~~~

Một implementation `X509TrustManager` không kiểm gì có thể biến kết nối HTTPS thành kênh mã hóa tới bất kỳ attacker nào. Không dùng production, cũng không coi đó là bản sửa tạm đã an toàn.

### B. HostnameVerifier luôn true

~~~java
// MẪU SAI — không dùng:
javax.net.ssl.HostnameVerifier insecure =
        (hostname, session) -> true;
~~~

Certificate có CA hợp lệ nhưng cho tên máy khác không được chấp nhận cho `sso.example.org`. Nếu hostname sai hãy sửa certificate hoặc URL. Không đặt global default verifier insecure.

### C. Chạy curl -k để “chứng minh HTTPS đã ổn”

~~~bash
# Sai nếu dùng làm kiểm chứng TLS an toàn:
curl -k https://sso.example.org/cas/login
~~~

`-k` bỏ bước xác minh certificate. Chỉ dùng trong chẩn đoán có kiểm soát để định vị khác biệt network/HTTP, không công bố kết quả như kiểm chứng bảo mật.

### D. Mở rộng CAS service registry quá rộng

~~~text
^https?://.*
~~~

Pattern này cho phép nhiều services không được quản trị. Với Portal cụ thể, đăng ký regex anchored, HTTPS hostname/path chính xác:

~~~text
^https://portal[.]example[.]com/login/cas$
~~~

Bảo mật service ticket bao gồm **giới hạn CAS server chỉ cấp ST cho service được duyệt**.

### E. Truy cập CAS URL từ request người dùng

Một query `?casServer=https://untrusted.example.net` không được dùng để đổi TicketValidator base URL trong runtime. Nếu cho phép, attacker có thể gây **SSRF**, lộ ST hoặc dụ app tin một CAS giả. CAS URL phải được cấu hình server-side và quản trị.

### F. HTTP cho ticket validation hoặc PGT callback

~~~text
http://sso.example.org/cas/serviceValidate?ticket=ST-...
http://portal.example.com/login/cas/proxyreceptor
~~~

Những đường này có thể lộ credential/callback identity. CAS proxy protocol yêu cầu HTTPS cho PGT callback và đánh giá peer trust. Không disable để “chữa lỗi PKIX”.

### G. Import tùy tiện certificate từ server đang lỗi

Nếu dùng `openssl` lấy certificate ở một đường bị nghi MITM rồi ngay lập tức import làm trust anchor không kiểm qua PKI, bạn có thể **tin key của attacker**. Cần xác minh fingerprint/CA bằng kênh độc lập, có owner và audit.

## 17. Bảo vệ Service Ticket và browser session ngoài TLS

HTTPS không tự giải quyết việc ST xuất hiện trong URL redirect:

- Không log nguyên query `?ticket=ST-...` tại access logs, APM, analytics hoặc error reporting.
- Không dán ST thật vào ticket hỗ trợ, shell history hoặc chat.
- Dùng `Referrer-Policy` phù hợp và hạn chế external resources trên callback có ST.
- Bảo vệ SP session cookie với `Secure`, `HttpOnly`, path/domain và SameSite theo browser flow.
- Dùng HTTPS callback chính xác; tránh biến redirect sang HTTP qua proxy.
- CAS TGC/session cookie thuộc domain CAS, không chia sẻ/đọc trực tiếp bởi SP.
- Đặt local `Authentication` chỉ sau CAS ticket validation; không tin query username.
- CAS ST thường one-time, chống replay bằng protocol; không cố replay để lấy identity.
- Khi app dùng local roles/tenants, kiểm disabled/locked user và authorization sau CAS login.

**CAS principal attributes** có thể chứa PII. Không ghi raw CAS XML `authenticationSuccess`/attributes vào debug logs khi production; chỉ log event ID, service identifier và lỗi rút gọn.

## 18. Kiểm thử tích hợp đầy đủ trên staging

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Browser → CAS | HTTPS login, certificate hợp lệ | Browser xác minh CAS host đúng |
| Browser → SP | HTTPS Portal, certificate hợp lệ | Browser kết nối an toàn |
| **SP → CAS TLS** | JVM truststore có CA hợp lệ | Handshake và hostname verification PASS |
| Wrong CA | CAS dùng certificate từ CA chưa trust | SP phải từ chối |
| Wrong SAN | Certificate hợp lệ nhưng tên máy khác | SP phải từ chối |
| Expired certificate | CAS cert hết hạn | SP phải từ chối |
| Missing intermediate | Server không gửi đủ chain và client không xây được path | TLS fail |
| Weak TLS | CAS chỉ cung cấp TLS cũ/cipher yếu bị disable | Handshake fail |
| Wrong service | ST cấp cho Portal A, validate với Portal B | CAS từ chối |
| ST replay | Validate ticket đã consume | CAS từ chối |
| Fake CAS XML | Không có ticket validation thật | Không được tạo Authentication |
| Browser receives ticket | ST redirect qua HTTPS | SP nhận và xử lý đúng |
| Java truststore mount sai | Container thiếu file | TLS fail, không tự bật trustAll |
| CAS certificate rotation | Cert mới dưới CA đã trust | Rollout thành công và monitoring ổn |
| CA rotation | Trust anchors thay đổi | Chỉ CA được phê duyệt mới được tin |
| Proxy HTTPS termination | Backend internal HTTP | Public service callback vẫn HTTPS đúng |
| Forwarded header spoof | Request ngoài đặt host/proto giả | Ingress strip/replace, không open redirect |
| PGT callback HTTPS | CAS Proxy bật đúng | CAS xác minh certificate SP |
| PGT callback wrong cert | SP certificate invalid | CAS từ chối proxy callback |
| mTLS sai client cert | Policy yêu cầu mTLS | CAS/ingress từ chối |
| Disabled local user | CAS xác thực nhưng SP user bị khóa | Local app deny theo policy |
| Multi-node | Load balance qua các CAS/SP nodes | Truststore/callback nhất quán |

**Test âm tính phải chạy ở staging/test CA**, không thay certificate production để tạo failure. Có thể dùng lab CAS server, truststore thử nghiệm và Spring integration test cùng TicketValidator thực. Unit test chỉ mock `CasAuthenticationToken` không chứng minh HTTPS trust hoặc CAS protocol security.

### Một quy trình test E2E tối thiểu

1. Đăng ký `https://portal.example.com/login/cas` trong CAS service registry với HTTPS regex chặt.
2. Kiểm CAS public certificate và CA chain/SAN từ JVM container.
3. Đăng nhập browser test qua CAS và nhận Service Ticket, không log raw value.
4. Spring gọi `Cas20ServiceTicketValidator` đến CAS base qua HTTPS.
5. Xem CAS ticket validation XML thực, liên hệ service đúng, consumed once.
6. Spring tạo session/principal/authorities theo local policy.
7. Thử URL sai service, ST đã dùng, CA chưa trust và wrong SAN; tất cả phải bị từ chối.
8. Nếu có PGT workflow, test callback CAS→SP với SP certificate hợp lệ và sai.
9. Kiểm forwarded headers, cookies và HTTPS redirect không làm lộ ST.
10. Chỉ báo PASS khi cả TLS trust và CAS authentication/authorization đều đúng.

## 19. Certificate rotation và vận hành lâu dài

Để tránh CAS SSO đứt hàng loạt khi certificate sắp hết hạn:

1. Xác định nơi TLS thật kết thúc: CAS process, ingress hay LB.
2. Ghi nhận public hostname, SAN, issuer/CA, chain và ngày hết hạn.
3. Với CA rollover, phê duyệt CA mới qua PKI, phân phối trust anchors tới các JVM trước cutover theo kế hoạch.
4. Khi renew leaf certificate dưới cùng CA đã tin, vẫn kiểm SAN/key usage/intermediate chain và hostname.
5. Đảm bảo các SP pods dùng cùng trust material và JDK security baseline.
6. Kiểm private key server không bị đưa vào repo hoặc CAS metadata/log.
7. Giám sát số lỗi `SSLHandshakeException`, PKIX path, hostname mismatch, timeout và `INVALID_SERVICE` theo ứng dụng.
8. Loại bỏ CA cũ khi giai đoạn overlap kết thúc; tránh giữ trust anchors không còn cần vô hạn.
9. Chạy negative tests sau thay certificate/truststore.
10. Có rollback, owner, change record, và thông báo các SP clients tiêu thụ CAS.

**Hạn chế leaf pinning tùy tiện**: pin một leaf certificate cố định mà không có key rotation plan dễ làm login fail khi renew. Trusted internal CA với review/giới hạn phạm vi có thể phù hợp hơn; lựa chọn tùy threat model.

## 20. Câu hỏi thường gặp

**Hỏi:** Chrome mở CAS HTTPS không lỗi, nhưng backend `PKIX path building failed`?

**Đáp:** Browser và Java JVM có truststore khác nhau. Kiểm CA/chain/cert/SAN và JVM runtime **thật**, không dựa vào browser.

**Hỏi:** Dùng `server.ssl.key-store` có đủ để SP tin CAS không?

**Đáp:** Không. Nó chủ yếu phục vụ HTTPS inbound. Outbound CAS validator cần truststore/SSLContext của HTTP client.

**Hỏi:** Đã đặt `spring.ssl.bundle.jks.cas-client.truststore` nhưng vẫn lỗi?

**Đáp:** Định nghĩa bundle không bảo đảm Apereo CAS validator tự dùng. Kiểm client adapter/transport đã nhận bundle hay chưa.

**Hỏi:** Có cần import private key CAS vào truststore Spring?

**Đáp:** Không. SP chỉ cần trusted public CA/certificate để verify CAS. Private key CAS phải được CAS/ingress giữ bí mật.

**Hỏi:** CAS cert có CA hợp lệ nhưng SAN không khớp thì tắt hostname check được không?

**Đáp:** Không. Phải cấp lại certificate hoặc cấu hình hostname/public DNS đúng.

**Hỏi:** `ServiceProperties.service` có phải URL CAS validation?

**Đáp:** Không. Đó là URL callback **của Spring app**. CAS validator được chỉ định CAS base URL riêng.

**Hỏi:** HTTPS có thay việc validate ticket không?

**Đáp:** Không. TLS bảo vệ kênh tới CAS server, còn TicketValidator và CAS server quyết định ST có hợp lệ, đúng service, còn hạn và chưa dùng.

**Hỏi:** CAS yêu cầu mTLS mọi nơi?

**Đáp:** Không mặc định. mTLS là lớp xác thực service bổ sung theo chính sách; không thay CAS ticket protocol.

**Hỏi:** Ai kiểm certificate khi CAS gọi PGT callback ở SP?

**Đáp:** CAS là HTTPS client, nên **CAS-side** trust material phải tin SP certificate.

## 21. Checklist triển khai

- [ ] Đã phân biệt TLS Browser→SP, Browser→CAS, SP→CAS và CAS→SP proxy callback.
- [ ] HTTPS cho CAS base, CAS login và SP service callback.
- [ ] CAS client dùng trust manager/hostname verifier chuẩn và CA được phê duyệt.
- [ ] Chứng thư CAS có SAN đúng, chain đầy đủ, còn hạn, thuật toán an toàn.
- [ ] Truststore đúng file/JVM/container; không nhập CA không xác minh.
- [ ] Không dùng trustAll, `HostnameVerifier` true, HTTP validation hoặc `curl -k` để kết luận an toàn.
- [ ] Đã tách keystore inbound, truststore outbound và mTLS client keystore.
- [ ] Spring Boot SSL Bundle nếu dùng đã được wiring tới đúng HTTP transport.
- [ ] `ServiceProperties.service` là SP callback, còn TicketValidator trỏ CAS base.
- [ ] CAS registered service regex chỉ cho đúng HTTPS host/path.
- [ ] Reverse proxy/Forwarded headers chỉ tin ingress có kiểm soát.
- [ ] SP/CAS cookies có Secure/HttpOnly và session lifecycle thích hợp.
- [ ] ST và CAS XML không xuất hiện nguyên văn trong logs hoặc telemetry.
- [ ] ST one-time/service matching, local user/role/tenant authorization được giữ.
- [ ] Wrong CA, wrong hostname, expired certificate và wrong-service tests fail closed.
- [ ] Certificate/CA rotation có owner, timeline, monitoring và rollback.
- [ ] Nếu dùng CAS Proxy PGT, CAS tin SP certificate và callback dùng HTTPS.
- [ ] Đã kiểm tương thích Java/CAS client/Spring Security/Boot version cụ thể.

## 22. Tài liệu chính thức tham khảo

1. [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `CasAuthenticationEntryPoint`, `ServiceProperties`, `CasAuthenticationProvider`, ticket validation HTTPS.
2. [Spring Security — CasAuthenticationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): callback Service Ticket và `/login/cas`.
3. [Spring Security — ServiceProperties Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html): service callback semantics.
4. [Apereo CAS 7.3 — CAS Protocol](https://apereo.github.io/cas/7.3.x/protocol/CAS-Protocol.html): ST, TGT/TGC, CAS2/3 validation endpoints.
5. [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): service matching, ticket validation, HTTPS PGT callback.
6. [Apereo CAS 7.3 — Proxy Authentication](https://apereo.github.io/cas/7.3.x/authentication/Configuring-Proxy-Authentication.html): callback SSL validation khi CAS là HTTPS client.
7. [Apereo CAS — Troubleshooting SSL/Certificates](https://apereo.github.io/cas/development/installation/Troubleshooting-Guide.html): PKIX path, SAN, hostname errors.
8. [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): truststore, keystore, HTTPS hostname checks, TLS config.
9. [Oracle Java 17 — JDK Providers](https://docs.oracle.com/en/java/javase/17/security/oracle-providers.html): TLS versions và disabled algorithms.
10. [Spring Boot — SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): `spring.ssl.bundle.*` và `SslBundles`.
11. [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS configuration và certificate lifecycle.

**Ghi nhớ:** bảo vệ CAS SSO cần HTTPS đúng **cả front channel và back channel**. Quan trọng nhất với Spring Security là **TicketValidator gọi CAS bằng HTTPS thật, xác minh PKIX certificate chain và hostname SAN**, song song với **ST one-time và service binding**. Truststore của JVM không giống keystore inbound; TLS của browser không chứng minh TLS của Java; không tắt certificate checks để khắc phục sai cấu hình.