# Ranh giới giữa kiểm tra TLS tại hạ tầng và ánh xạ danh tính trong ứng dụng

## 1. Vấn đề cần phân biệt

Trong hệ thống dùng **chứng thư X.509 để xác thực client**, câu “đã xác thực bằng certificate” thường gộp hai việc khác nhau:

1. **Kiểm tra TLS/mTLS ở hạ tầng:** thành phần kết thúc TLS (web server, load balancer, ingress, reverse proxy, service mesh hoặc chính embedded server của Spring Boot) quyết định certificate của **TLS peer** có đáng tin theo chính sách hay không.
2. **Ánh xạ danh tính ở ứng dụng:** Spring Security xác định certificate hoặc một **assertion đáng tin do hạ tầng tạo ra** tương ứng với tài khoản/service nào, có còn được phép sử dụng hay không và được gán những `GrantedAuthority` nào.

Điểm then chốt: **certificate hợp lệ ở TLS chưa tự động đồng nghĩa một người dùng hợp lệ của ứng dụng; tên người dùng hoặc HTTP header có giá trị giống subject certificate cũng không tự động là bằng chứng TLS đã xác thực.**

Ví dụ: một CA nội bộ cấp certificate client cho `CN=lan`. Reverse proxy kiểm tra certificate và cho phép kết nối. Ứng dụng quản lý hồ sơ vẫn cần biết `lan` tương ứng tài khoản nào, trạng thái tài khoản có bị khóa không và có quyền `ROLE_HR` để xem hồ sơ nhân sự không. Nếu chưa có ánh xạ/phân quyền, việc TLS bắt tay thành công chỉ mới giải quyết một phần của bài toán.

### Hai ranh giới tin cậy cần nhìn rõ

~~~text
Trường hợp A — TLS kết thúc ngay tại ứng dụng:

Client có private key + X.509 certificate
       │  HTTPS + mTLS
       ▼
Spring Boot embedded server (Tomcat/Jetty...)
       │  kiểm tra certificate client ở tầng TLS
       │  đưa certificate đã nhận vào Servlet request
       ▼
Spring Security X.509 authentication
       │  rút trích principal + nạp tài khoản/authorities
       ▼
Controller / Service
          kiểm tra quyền nghiệp vụ


Trường hợp B — TLS kết thúc tại reverse proxy:

Client có private key + X.509 certificate
       │  HTTPS + mTLS
       ▼
Reverse proxy / ingress  ◄── trust store, chính sách PKI
       │  kiểm tra certificate, xác thực TLS peer
       │  tạo thông tin định danh đã kiểm tra
       ▼  HTTP/mTLS giữa proxy và backend (một kết nối khác)
Spring Boot application
       │  xác minh nguồn/provenance của assertion
       │  ánh xạ principal + authorities
       ▼
Controller / Service
          kiểm tra quyền nghiệp vụ
~~~

Ở trường hợp B, **mTLS từ proxy đến backend (nếu có) xác thực proxy là TLS peer của backend**, không biến proxy thành certificate gốc của người dùng. Danh tính client ban đầu phải được truyền bằng **hợp đồng tin cậy riêng**, thí dụ assertion đã ký hoặc metadata do proxy kiểm soát trong một kênh chỉ proxy được phép dùng.

## 2. Kiểm tra certificate ở tầng TLS thực sự làm gì?

X.509 là định dạng chứng thư chứa public key và các trường như subject, issuer, serial number, thời hạn hiệu lực, Subject Alternative Name (SAN), Key Usage / Extended Key Usage tùy profile. Certificate **không phải mật khẩu**; private key tương ứng không được chuyển cho server.

Với **server-authenticated TLS** thông thường, server đưa certificate để client xác thực máy chủ, và giao thức thiết lập một kênh bảo mật. Với **mutual TLS (mTLS)**, server còn yêu cầu client certificate. Trong quá trình bắt tay, TLS peer chứng minh quyền sử dụng private key tương ứng và phía xác minh đánh giá certificate theo trust configuration. Các bước kiểm tra có thể gồm:

- Xây dựng đường dẫn certificate đến CA được tin cậy và kiểm tra chữ ký/chuỗi phát hành.
- Kiểm tra thời hạn, ràng buộc cơ bản, key usage, extended key usage và chính sách certificate phù hợp mục đích **client authentication**.
- Xem xét cơ chế thu hồi certificate (**CRL/OCSP**) nếu chính sách và sản phẩm triển khai; đừng mặc định mọi TLS stack tự kiểm tra thu hồi trực tuyến.
- Kiểm soát phiên bản TLS, thuật toán được phép, certificate được cấp từ CA nào và yêu cầu certificate là bắt buộc hay tùy chọn.

Khi hạ tầng từ chối client certificate, lỗi có thể xảy ra **ngay ở TLS handshake, trước khi HTTP request tới Spring Security**. Vì vậy controller, filter hoặc `@ExceptionHandler` của ứng dụng có thể không nhìn thấy request để trả JSON lỗi tùy biến.

Cần phân biệt phạm vi lời khẳng định:

| Kết quả / dữ liệu | Có thể kết luận gì? | Chưa được kết luận gì? |
|---|---|---|
| TLS handshake thành công với client auth bắt buộc và policy kiểm tra đúng | TLS peer đã xuất trình certificate đáp ứng chính sách của điểm kết thúc TLS. | Peer có tài khoản ứng dụng, nhóm quản trị hoặc quyền dùng API nhạy cảm. |
| Certificate có subject `CN=lan` | Certificate chứa chuỗi subject đó. | `lan` duy nhất trên mọi CA, đang là nhân viên hoặc chưa bị khóa trong ứng dụng. |
| Certificate có SAN URI `spiffe://corp.example/payments/api` | Certificate khẳng định URI đó theo chính sách CA/PKI đã cấp. | Ứng dụng tự động cấp mọi quyền cho workload đó. |
| Request mang `X-Client-Cert` hoặc `X-Verified-User` | Có một HTTP header với giá trị đó. | Header do TLS terminator đáng tin tạo ra, chưa bị client hoặc proxy khác giả mạo. |
| HTTP `200` của endpoint sau TLS | Request được xử lý thành công theo logic endpoint ấy. | Mọi endpoint của cùng ứng dụng đã cấu hình authorization đúng. |

**mTLS xác thực TLS peer trên một kết nối cụ thể.** Khi TLS được kết thúc rồi mở một kết nối khác, kết quả xác thực không tự được “truyền nguyên trạng” sang kết nối sau.

## 3. Ranh giới số 1: ứng dụng trực tiếp kết thúc TLS

Nếu embedded Tomcat (hoặc servlet container tương đương) của Spring Boot nhận HTTPS/mTLS trực tiếp, container kiểm tra certificate dựa trên TLS trust store/policy. Khi có client certificate gắn với request, **Jakarta Servlet** quy định request attribute:

~~~java
Object value = request.getAttribute("jakarta.servlet.request.X509Certificate");
~~~

Giá trị phù hợp là mảng `java.security.cert.X509Certificate[]`; certificate đầu tiên là chứng thư phía client đưa ra, các phần tiếp theo là chuỗi liên quan. **Chỉ đọc attribute này không có nghĩa ứng dụng tự đã kiểm chứng certificate**: việc bảo đảm nguồn gốc và xác thực chuỗi đến từ cấu hình container/TLS cùng sự bảo vệ của đường request. Ứng dụng có thể kiểm tra thêm ràng buộc danh tính theo nhu cầu nghiệp vụ.

Spring Security (Servlet) có `X509AuthenticationFilter` để lấy certificate từ request đã được container xử lý, rút trích principal, rồi dùng cơ chế pre-authentication để tìm user và authorities. Thuật ngữ **pre-authenticated** có nghĩa một tầng bên ngoài Spring Security đã thực hiện xác thực cơ sở; Spring tiếp tục liên kết thông tin đó với mô hình bảo mật ứng dụng.

### Ví dụ Spring Boot: mTLS ngay tại server

Giả sử máy chủ có key store chứa server certificate/private key, và trust store chứa CA được phép cấp **client certificate**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=read-from-secret-management
server.ssl.trust-store=classpath:client-trust.p12
server.ssl.trust-store-type=PKCS12
server.ssl.trust-store-password=read-from-secret-management
server.ssl.client-auth=need
~~~

Các đường dẫn và mật khẩu ở đây là **giá trị minh họa**, cần thay bằng tài nguyên và secret thật trước khi chạy. Không lưu private key hoặc mật khẩu production trong repository. `client-auth=need` yêu cầu client cung cấp certificate hợp lệ ở kết nối trực tiếp với server. `client-auth=want` chỉ yêu cầu thử xuất trình; nếu thiếu certificate, handshake vẫn có thể thành công, nên các route bảo vệ bằng X.509 phải được xử lý riêng. Trust store phải khớp CA cấp cho client và không nên mặc định tin toàn bộ public CA.

Ví dụ Spring Security **6.x, Java 17+, Servlet** dưới đây mô tả phần ánh xạ sau TLS. Đây là lớp trong **dự án Spring Boot có `spring-boot-starter-security`**, không phải chương trình Java độc lập; `InMemoryUserDetailsManager` chỉ để minh họa kết quả mapping.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CertificateSecurityConfig {

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
            User.withUsername("lan")
                .password("{noop}unused-for-this-x509-example")
                .roles("EMPLOYEE")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users) throws Exception {
        http
            .x509(x509 -> x509.userDetailsService(users))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated());
        return http.build();
    }
}
~~~

Ý nghĩa từng phần:

1. TLS/servlet container xác thực client certificate trên kết nối tới server; chương trình Java trên **không tự thực hiện TLS certificate path validation**.
2. Với cấu hình mặc định phù hợp của Spring Security 6, X.509 principal extractor dựa vào **CN** để tìm tên người dùng. Khi certificate hợp lệ mang `CN=lan`, `UserDetailsService` tìm account `lan`.
3. Account `lan` trong ví dụ có `ROLE_EMPLOYEE`, nên có thể vào endpoint yêu cầu `authenticated()`; không có `ROLE_ADMIN` nên bị từ chối khi truy cập `/api/admin/**`. Chính sách cấp role thuộc ứng dụng.
4. Mật khẩu giả của user trong ví dụ chỉ để thỏa giao diện user model; **X.509 pre-authentication không yêu cầu nhập mật khẩu ứng dụng khi xác thực bằng client certificate**.
5. Production cần thay in-memory account bằng nguồn người dùng thật, kiểm tra account enabled/locked/expired, quản trị quyền theo role thực, đồng thời quyết định danh tính ổn định dựa trên certificate profile và chính sách phát hành.

**Giới hạn an toàn của ví dụ:** dùng CN làm identity chỉ đủ cho demo khi CA có chính sách bảo đảm CN duy nhất và không cấp nhầm identity. Trong hệ thống nhiều CA/tenant, CN có thể trùng hoặc đổi tên. Nên xem xét **SAN (URI/DNS/email phù hợp loại chủ thể), issuer và thuộc tính ổn định được quy định**, rồi dùng `x509PrincipalExtractor(...)` hoặc quy trình mapping riêng đã kiểm chứng. Không dùng serial number đơn lẻ làm khóa toàn cục vì nó chỉ duy nhất trong phạm vi một issuer.

Một lưu ý dễ bỏ qua: khi `server.ssl.client-auth=need`, **TLS bắt buộc ngay tại listener**, nên endpoint cho phép `permitAll()` trong Spring Security vẫn không truy cập được nếu client không có certificate. Không thể dùng `permitAll()` để nới lỏng yêu cầu bắt tay TLS.

## 4. Ranh giới số 2: TLS kết thúc tại proxy, ingress hoặc load balancer

Đây là tình huống dễ xảy ra lỗi nghiêm trọng nhất:

~~~text
Client                       Gateway                     Spring Boot
   │                           │                              │
   ├─ HTTPS/mTLS ─────────────>│                              │
   │                           ├─ verify client certificate  │
   │                           │                              │
   │                           ├─ HTTP request ──────────────>│
   │                           │  (certificate không tự      │
   │                           │   đi qua kết nối mới)       │
   │                           │                              │
   │                           │  optional: identity metadata│
   │                           ├─ trusted assertion ────────>│
   │                           │                              ├─ map user/role
   │                           │                              └─ authorize
~~~

Ở backend, `request.getAttribute("jakarta.servlet.request.X509Certificate")` thường **không có certificate gốc** của client. Nếu proxy dùng mTLS khi gọi backend, servlet container có thể thấy **certificate của proxy** ở kết nối thứ hai. Vì vậy chỉ bật `http.x509(...)` ở backend **không tự giải quyết** việc ánh xạ end-user đã được gateway xác thực.

### Mẫu cấu hình minh họa tại NGINX

~~~nginx
server {
    listen 443 ssl;
    server_name internal.corp.example;

    ssl_certificate     /etc/nginx/tls/server.crt;
    ssl_certificate_key /etc/nginx/tls/server.key;

    ssl_client_certificate /etc/nginx/tls/allowed-client-ca.pem;
    ssl_verify_client on;
    ssl_verify_depth 2;

    location / {
        proxy_set_header X-Verified-Client-Subject $ssl_client_s_dn;
        proxy_set_header X-Verified-Client-Status  $ssl_client_verify;

        proxy_pass http://127.0.0.1:8080;
    }
}
~~~

Đây là **mẫu để giải thích vai trò từng tầng**, không phải cấu hình production hoàn chỉnh. Khi `ssl_verify_client on`, NGINX yêu cầu và kiểm tra client certificate theo CA cấu hình. Biến `$ssl_client_verify` có thể trả `SUCCESS` khi kiểm tra thành công; `$ssl_client_s_dn` chứa subject DN của client certificate mà proxy đã nhận. Các `proxy_set_header` cho biết ví dụ **proxy chủ động ghi** giá trị metadata vào request gửi backend.

Để biến metadata thành assertion đáng tin phải thiết lập **đầy đủ** các điều kiện:

- Backend chỉ nhận request từ proxy đã được xác thực: giới hạn network/port, firewall/loopback hay mTLS proxy → backend, không có đường truy cập trực tiếp từ client đến backend.
- Proxy **xóa và ghi đè toàn bộ phiên bản** của header dùng làm định danh ở mọi điểm vào, có quy tắc xử lý header trùng/biến thể chữ hoa-thường và không chuyển tiếp giá trị client tự đặt.
- Nếu có nhiều tầng proxy, mỗi hop phải giữ nguyên hợp đồng provenance; không để các trung gian chưa được kiểm soát chèn/sửa assertion.
- Ứng dụng chỉ chấp nhận assertion tại **đúng trust boundary**, xác nhận issuer/proxy identity và định dạng; từ chối khi thiếu, trùng, sai, rỗng hoặc đến từ đường không đáng tin. Bản thân `X-Verified-Client-Status: SUCCESS` từ một HTTP client **không chứng minh gì**.
- Với hệ thống phân tán hoặc biên phức tạp, nên dùng identity assertion **được ký** (có xác minh chữ ký, issuer, audience, expiry và ràng buộc phù hợp) hoặc một cơ chế xác thực liên tầng có thiết kế rõ. mTLS từ proxy sang backend bảo vệ kênh và xác thực proxy; ứng dụng vẫn phải xác minh identity claim mà proxy chuyển.
- Quyết định cách kiểm tra thu hồi certificate, giới hạn CA/profile và policy thay certificate; `ssl_verify_client on` đơn lẻ chưa phải giải pháp vận hành PKI hoàn chỉnh.

**Không lấy thẳng `X-Verified-Client-Subject` rồi gọi `SecurityContextHolder.setContext(...)` ở filter bất kỳ.** Khi thực hiện pre-authentication, cần một integration có kiểm soát trust boundary, tìm user theo mapping được quy định, quản trị authority và thực thi mặc định **fail closed**. `X-Forwarded-For` / `X-Forwarded-Proto` dùng cho thông tin mạng/redirect qua proxy; chúng **không phải** bằng chứng danh tính X.509.

### Ba mô hình triển khai có hệ quả khác nhau

| Mô hình | Ai kiểm tra certificate gốc? | Ứng dụng nhận bằng chứng gì? | Trách nhiệm mapping |
|---|---|---|---|
| **TLS passthrough tới app** | Embedded server / servlet container của app. | Certificate request attribute có provenance từ TLS của app. | X.509 authentication/pre-auth trong Spring. |
| **TLS termination + proxy metadata** | Ingress/gateway. | Assertion/header do proxy phát hành trên đường truyền tin cậy (nếu triển khai đúng). | Tích hợp trusted pre-auth, tra account/role, phân quyền. |
| **TLS termination + mTLS proxy→backend** | Gateway kiểm tra client gốc; backend kiểm tra **proxy**. | Certificate proxy cho kết nối thứ hai, cộng với assertion riêng về client gốc (nếu có). | Xác thực proxy và mapping client gốc là hai bước tách biệt. |

Khi service mesh gắn danh tính workload cho kết nối nội bộ, đó thường là danh tính của **workload đang gọi**, không phải tự động là danh tính nhân viên cuối cùng. Muốn thực thi quyền người dùng, ứng dụng cần một user token/assertion có nguồn gốc và scope phù hợp.

## 5. Ranh giới số 3: từ danh tính trên certificate sang tài khoản và quyền ứng dụng

Một pipeline mapping chặt chẽ có thể biểu diễn:

~~~text
Verified TLS peer / verified gateway assertion
               │
               ▼
Extract canonical identity
  • chủ thể nào: user, service, device, workload?
  • namespace/issuer/tenant nào?
  • field nào được chứng nhận ổn định (SAN/ID)?
               │
               ▼
Resolve exactly one application account
  • tồn tại? active? không bị khóa?
  • định danh có bị trùng/không khớp không?
               │
               ▼
Build Spring Authentication / authorities
  • ROLE_EMPLOYEE, APP_READ, APP_APPROVE...
               │
               ▼
Authorization on each request/resource
               │
               ▼
Allow hoặc Deny
~~~

**Mapping identity** cần chính sách cụ thể, không chỉ một biểu thức regex cho mọi certificate.

Ví dụ certificate của máy chủ thanh toán có SAN URI `spiffe://corp.example/ns/payments/sa/collector`. Ứng dụng có thể ánh xạ **đúng** URI này, trong namespace/issuer được ủy quyền, tới account `payments-collector` với authority `PAYMENT_PUBLISH`. Một client certificate khác có CN `collector` nhưng không cùng SAN/issuer phải **không** được hưởng quyền đó.

Ví dụ ở mô hình nhân viên: certificate mang một employee ID đã được CA doanh nghiệp phát hành sau xác minh danh tính. Ứng dụng tra employee ID vào bảng người dùng, kiểm tra trạng thái active, rồi lấy quyền từ service quản trị role. **Role không nhất thiết nằm trong certificate**, và role trong certificate (nếu được nhúng) không nên được dùng ngoài chính sách CA, vòng đời và freshness đã được duyệt.

Các quyết định cần định nghĩa rõ:

1. **Định danh bền vững:** CN hiển thị có thể đổi; subject DN có thể không ổn định; SAN hoặc định danh thuộc profile PKI có thể phù hợp hơn. Khi cần phân biệt nhiều tổ chức, namespace cùng issuer/policy cũng là một phần của định danh.
2. **Ràng buộc CA:** certificate “được CA đáng tin ký” chưa đủ nếu CA ấy được phép cấp cho rất nhiều loại chủ thể. Thu hẹp CA, EKU, policy OID hoặc trust domain theo nghiệp vụ.
3. **Trạng thái tài khoản:** khóa tài khoản ứng dụng phải chặn truy cập kể cả certificate chưa hết hạn. Phân quyền dựa trên database/authorization service cập nhật theo chính sách.
4. **Đổi và thu hồi certificate:** định danh người dùng nên có thể tiếp tục qua việc thay key/certificate nếu chính sách yêu cầu; ngược lại, thu hồi quyền phải có thời điểm có hiệu lực rõ ràng.
5. **Quy tắc khi thiếu chứng cứ:** không match được duy nhất account, không xác minh được provenance, hoặc không đọc được role bắt buộc thì từ chối; không “fallback” sang guest hoặc admin.

### Mã Java 17 minh họa ranh giới mapping

Đây là **mô hình logic ra quyết định độc lập**, chạy được trên Java 17. `attestedByInfrastructure` là **đầu ra đã được một integration đáng tin xác minh**; trong code thật **không được lấy boolean này từ HTTP header hoặc request parameter**.

~~~java
public class IdentityBoundaryDemo {
    record VerifiedIdentity(String subject, boolean attestedByInfrastructure) {}

    static String resolveAccount(VerifiedIdentity identity) {
        if (!identity.attestedByInfrastructure()) {
            throw new SecurityException("untrusted origin");
        }
        return switch (identity.subject()) {
            case "spiffe://corp.example/payments/collector" -> "payments-collector";
            case "spiffe://corp.example/reports/reader"     -> "reports-reader";
            default -> throw new SecurityException("unmapped identity");
        };
    }

    public static void main(String[] args) {
        var trusted = new VerifiedIdentity(
            "spiffe://corp.example/payments/collector", true);
        System.out.println(resolveAccount(trusted));

        try {
            var forged = new VerifiedIdentity(
                "spiffe://corp.example/payments/collector", false);
            System.out.println(resolveAccount(forged));
        } catch (SecurityException e) {
            System.out.println(e.getMessage());
        }
    }
}
~~~

Lưu thành `IdentityBoundaryDemo.java` và chạy:

~~~bash
javac IdentityBoundaryDemo.java
java IdentityBoundaryDemo
~~~

Stdout chính xác:

~~~text
payments-collector
untrusted origin
~~~

Ví dụ chỉ minh họa **chấp nhận danh tính sau khi đã xác thực provenance** và phép ánh xạ allowlist. Nó **không phải** bộ kiểm tra TLS, JWT signature, X.509 chain, issuer hay revocation. Trong một hệ thống thật, các kiểm tra này phải được thực hiện bằng lớp hạ tầng hoặc thư viện bảo mật đã được cấu hình và kiểm thử, trước khi gọi code mapping.

## 6. Vì sao dễ gặp lỗ hổng khi ranh giới bị nhầm?

### Tình huống 1: backend mở cổng công khai nhưng tin header

~~~http
GET /api/payroll HTTP/1.1
Host: backend.corp.example
X-Verified-Client-Subject: CN=director
X-Verified-Client-Status: SUCCESS
~~~

Nếu client kết nối trực tiếp đến backend và ứng dụng tin hai header trên mà không kiểm tra provenance, nó có thể coi một chuỗi do attacker gửi là danh tính được hạ tầng xác thực. **Việc header có chữ “Verified” hay “SUCCESS” không làm nó đáng tin.**

Cách xử lý: đóng đường truy cập trực tiếp, proxy phải xóa/ghi đè header, xác thực hop proxy→backend và định nghĩa rõ provider xác thực assertion. Với kiến trúc phù hợp, dùng assertion có chữ ký và các điều kiện xác minh bắt buộc.

### Tình huống 2: “Certificate valid” bị hiểu thành “quản trị viên”

CA có thể cấp certificate cho cả nhân viên và máy chủ. Nếu ứng dụng cho mọi certificate hợp lệ quyền `ROLE_ADMIN`, hệ thống đã biến một điều kiện **xác thực thiết bị/chủ thể** thành quyết định **phân quyền** không có cơ sở. Hãy map vào account và role rõ ràng; certificate của máy không nên tự trở thành account người.

### Tình huống 3: hai certificate có cùng CN

Certificate ở hai đơn vị khác nhau cùng có `CN=service-api`. Bộ trích xuất chỉ lấy CN có thể map nhầm vào một tài khoản. Cần phân biệt issuer, trust domain, SAN hoặc định danh được CA bảo đảm duy nhất. Chỉ dùng thumbprint/serial có thể giúp nhận diện certificate cụ thể nhưng gây chi phí vận hành khi rotate; lựa chọn phụ thuộc yêu cầu ràng buộc certificate hay user/workload bền vững.

### Tình huống 4: backend dùng mTLS với gateway và lấy CN của gateway làm end-user

Backend nhìn thấy `CN=api-gateway` vì gateway là TLS peer của kết nối phía sau. Khi đó `http.x509(...)` có thể map `api-gateway`, nhưng **không chứng minh** request thuộc người dùng Lan đang đứng trước gateway. Nếu cần phân quyền theo Lan, cần một assertion người dùng riêng đã được gateway xác minh.

### Tình huống 5: Spring Security cấu hình đúng nhưng TLS policy sai

`http.x509(...)` không bù được trust store quá rộng, certificate client không bắt buộc, chứng chỉ hết hạn vẫn được proxy chuyển dưới nhãn “verified”, hoặc việc bỏ qua revocation trái policy. TLS validation và Spring user mapping là **hai lớp phải được kiểm thử độc lập**.

### Tình huống 6: bảo vệ request nhưng quên session và certificate rotation

Sau khi xác thực bằng mTLS, một hệ thống có thể giữ session/cached authentication. Nếu employee bị khóa hoặc certificate bị thu hồi, các kết nối và session tồn tại có thể tiếp tục theo chính sách cache/session hiện hành. Cần quyết định TTL, cơ chế kiểm tra lại account, thu hồi session và hiệu lực thay đổi quyền. **Đừng mặc định certificate bị thu hồi là mọi session lập tức biến mất.**

## 7. Kịch bản thực hành: cổng nhân sự dùng reverse proxy

Giả sử nhân viên Lan có client certificate phát hành từ CA nhân sự. NGINX là TLS terminator, Spring Boot chạy sau proxy, dữ liệu lương chỉ cho phép nhân viên có authority `PAYROLL_VIEW`.

Luồng mong muốn:

1. Trình duyệt/client thiết lập mTLS với NGINX. NGINX kiểm tra certificate theo trust store dành cho nhân sự và policy chấp nhận certificate. Nếu thiếu/chứng thư không hợp lệ, request bị chặn ở hạ tầng; Spring không cần tự diễn dịch lỗi TLS.
2. NGINX xác định subject/SAN chuẩn hóa, gắn assertion được bảo vệ và chuyển request qua đường đã xác thực tới backend.
3. Backend chỉ tiếp nhận assertion nếu xác thực được provenance của gateway. Backend ánh xạ identity vào chính xác account Lan, kiểm tra Lan còn active và lấy authority từ nguồn đáng tin.
4. Spring Security lưu đối tượng `Authentication` có principal Lan và các authorities hợp lệ trong `SecurityContext` của request; ứng dụng kiểm tra `PAYROLL_VIEW` khi truy cập chức năng lương.
5. Khi Lan chuyển bộ phận và bị thu hồi `PAYROLL_VIEW`, cache/session và nguồn role phải đồng bộ theo thời hạn chính sách; certificate còn hạn **không phải** lý do giữ quyền cũ.

Một thiết kế đối chiếu thường dùng:

| Lớp | Dữ liệu kiểm tra | Quyết định |
|---|---|---|
| TLS terminator | Certificate chain, CA được cấp quyền, mục đích client auth, thời hạn, chính sách thu hồi. | Cho phép hoặc từ chối bắt tay/HTTP trước backend. |
| Trusted identity bridge | Nguồn assertion, proxy identity, chữ ký/issuer/audience/expiry nếu dùng token; chống header spoofing. | Chấp nhận hoặc từ chối nguồn gốc danh tính. |
| Spring Security authentication | Principal chuẩn hóa, account tồn tại/đang active, ánh xạ roles. | Tạo Authentication với authorities hoặc thất bại. |
| Spring authorization + nghiệp vụ | Role/scope, sở hữu tài nguyên, trạng thái giao dịch. | Cho phép/403 trên từng thao tác/tài nguyên. |

## 8. Kiểm thử bắt buộc theo ranh giới

Bộ thử nghiệm nên kiểm tra **đúng điểm từ chối** và hệ quả ở ứng dụng, thay vì chỉ nhìn một mã HTTP duy nhất.

| Thử nghiệm | Kỳ vọng | Cần quan sát ở đâu |
|---|---|---|
| Client không đưa certificate khi policy `need/on` | Bị chặn tại TLS hoặc thành phần terminator. | Access/error log của terminator, handshake/curl. |
| Certificate ký bởi CA không được phép | Không đến được route được bảo vệ. | TLS verification/error log. |
| Certificate hợp lệ nhưng SAN/identity không map được account | Bị từ chối bởi authentication/mapping của app. | Audit bảo mật backend; không gán anonymous quyền đặc biệt. |
| Certificate hợp lệ, account bị khóa | Không có phiên xác thực hợp lệ. | Application account policy / audit. |
| Account hợp lệ nhưng thiếu `ROLE_ADMIN` | Bị từ chối ở authorization, thường HTTP 403 khi đã authenticated. | Spring Security authorization log. |
| Client tự gửi header `X-Verified-Client-Subject` khi đi qua proxy | Proxy loại bỏ/ghi đè; identity app phải đến từ phiên TLS đã verify. | Header capture ở hop backend có kiểm soát. |
| Client gọi thẳng cổng backend cùng header giả | Kết nối bị chặn hoặc assertion bị từ chối. | Firewall/ingress và application audit. |
| Gateway gọi backend qua mTLS riêng | Backend thấy **gateway certificate** ở kết nối sau; end-user assertion được xử lý riêng. | TLS peer info và application principal. |
| Chứng thư hết hạn, bị thu hồi hoặc chuyển sang CA khác | Phù hợp chính sách TLS/PKI đã cấu hình; test thời hạn/caching. | Terminator/DC/PKI audit. |
| Rotate certificate nhưng giữ cùng user/workload hợp lệ | Mapping ổn định hoặc cần re-enrollment đúng thiết kế. | User mapping và audit thay key. |
| Hai certificate cùng CN nhưng khác issuer/trust domain | Không vô tình map vào cùng account nếu policy cấm. | Identity resolver/audit. |
| Gateway gửi header trùng hoặc thiếu assertion | Fail closed, không lấy ngẫu nhiên một giá trị. | Backend ingress integration và audit. |

Có thể dùng công cụ curl có client certificate ở môi trường thử nghiệm:

~~~bash
curl --verbose \
  --cert client.crt \
  --key client.key \
  --cacert server-ca.crt \
  https://internal.corp.example/api/profile
~~~

Lệnh chỉ là **cấu trúc minh họa**; đường dẫn, certificate và endpoint phải tồn tại. `--cacert` ở client giúp xác minh **server certificate**; `--cert`/`--key` dùng danh tính client nếu server yêu cầu mTLS. Không dùng `-k` hoặc tắt verify để “sửa” một lỗi certificate trong quy trình xác thực.

Với curl thử certificate không hợp lệ, **không khẳng định luôn nhận HTTP 401/403**: có thể bị từ chối tại TLS và không nhận được HTTP response. HTTP 401/403 thường thuộc tầng ứng dụng khi request đã vượt qua hạ tầng.

## 9. Vận hành, quan sát và xử lý sự cố

Một hệ thống tốt cần phân biệt lỗi theo lớp ngay từ telemetry:

- **TLS terminator:** log loại handshake failure/verification failure, CA policy và trạng thái chứng thư; giới hạn dữ liệu nhạy cảm. Không log private key hoặc nội dung certificate dư thừa.
- **Trusted bridge:** log proxy identity, assertion issuer, ID tương quan request và kết quả xác minh nguồn; kiểm tra mismatch, duplicate header, signature sai.
- **Spring authentication:** log có kiểm soát nguyên nhân account không tồn tại/bị khóa hoặc ánh xạ không nhất quán; **không** trả chi tiết cho client để tránh lộ thông tin tài khoản.
- **Authorization:** ghi account/role và resource/action bị từ chối dưới dạng audit phù hợp, không ghi dữ liệu nhạy cảm của hồ sơ nhân sự.
- **Quản lý CA:** giám sát certificate sắp hết hạn, rotation của CA/client certificate, OCSP/CRL theo policy và kiểm soát trust-store rollout.
- **Traffic topology:** kiểm tra lại sau khi đổi ingress, thêm service mesh sidecar, chuyển từ TLS passthrough sang TLS termination hoặc bật CDN/LB trung gian; thay đổi một hop có thể đổi **ai là TLS peer thực tế**.

Một vài triệu chứng cần suy luận đúng:

- `request.getAttribute("jakarta.servlet.request.X509Certificate") == null` trên backend phía sau proxy: **chưa phải lỗi Spring Security**; có thể backend không phải TLS terminator của kết nối client.
- Proxy trả lỗi client-certificate nhưng app không log request: request đã thất bại **trước khi vào Spring**.
- Đăng nhập được nhưng nhận 403: ưu tiên kiểm tra mapping authorities và quy tắc endpoint, **không** vội mở rộng CA trust.
- Mọi request sau proxy đều hiện cùng principal `gateway`: app đang nhìn thấy TLS peer của hop proxy → backend, chưa có ánh xạ end-user đáng tin.
- User bị khóa vẫn truy cập được: cần kiểm tra cache/session, thời gian làm mới authorities và đường phụ bỏ qua authentication policy.

## 10. Nguyên tắc lựa chọn kiến trúc và kết luận

Khi ứng dụng trực tiếp nhận TLS/mTLS, hãy cấu hình trust store và client-auth tại server, rồi dùng Spring Security X.509 để ánh xạ certificate sang **account và authorities**. Khi ingress/proxy nhận TLS/mTLS trước, hãy coi kết quả kiểm tra certificate là **đầu ra của một trust boundary khác**: backend phải nhận được assertion có provenance đáng tin và thực hiện mapping, không được tự tin vào bất kỳ header nào chỉ vì tên của nó giống dữ liệu certificate.

Cần trả lời rõ năm câu hỏi trước khi triển khai:

1. **Ai là TLS terminator?** Component nào thực sự kiểm tra certificate gốc của client?
2. **Ai là TLS peer của backend?** Client cuối cùng, gateway hay service mesh sidecar?
3. **Danh tính được truyền thế nào?** Servlet certificate attribute trực tiếp hay assertion do proxy ký/chuyển qua kênh đã xác thực?
4. **Ánh xạ theo định danh nào?** SAN/issuer/trust domain/CA policy đã bảo đảm tính duy nhất và vòng đời ra sao?
5. **Ai quyết định quyền?** Account trạng thái gì, authorities đến từ đâu, kiểm tra tài nguyên cụ thể ở lớp nào và khi nào quyền được làm mới?

**Thông điệp cốt lõi:** TLS xác minh *kết nối và chủ thể sở hữu khóa theo chính sách PKI*; Spring Security xác định *principal có ý nghĩa với ứng dụng*; authorization quyết định *principal ấy được làm gì*. Mỗi lớp phải có nguồn bằng chứng riêng, ranh giới tin cậy rõ ràng và quy tắc từ chối khi không đủ bằng chứng.

## Tài liệu tham khảo

- [Spring Security — X.509 Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html): filter X.509, principal extraction và user mapping.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): Authentication, SecurityContext, GrantedAuthority và provider.
- [Spring Boot — SSL / Embedded Web Server](https://docs.spring.io/spring-boot/how-to/webserver.html): cấu hình `server.ssl.*` cho embedded container.
- [NGINX — ngx_http_ssl_module](https://nginx.org/en/docs/http/ngx_http_ssl_module.html): `ssl_verify_client`, `ssl_client_s_dn`, `ssl_client_verify` và chính sách certificate.
- [Jakarta Servlet Specification 6.1](https://jakarta.ee/specifications/servlet/6.1/): chứng thư client qua request attribute `jakarta.servlet.request.X509Certificate`.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cấu trúc certificate, path validation và revocation.
