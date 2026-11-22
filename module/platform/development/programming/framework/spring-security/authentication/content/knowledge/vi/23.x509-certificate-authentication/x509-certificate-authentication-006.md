# Chứng thư X.509 qua reverse proxy: bảo vệ đường truyền và header xác thực

## 1. Mục tiêu và tình huống sử dụng

Khi một ứng dụng Spring Security chạy sau **reverse proxy** (NGINX, Apache HTTP Server, ingress controller, API gateway hoặc service mesh), kết nối TLS từ client có thể **kết thúc tại proxy** thay vì tại tiến trình Java. Điều đó ảnh hưởng trực tiếp tới xác thực bằng **chứng thư X.509 của client**.

Giả sử một hệ thống B2B chỉ cho các client có chứng thư do CA doanh nghiệp cấp truy cập API:

~~~text
Client (certificate + private key)
          │
          │ HTTPS + mutual TLS (mTLS)
          ▼
    Reverse proxy
    - kiểm tra TLS handshake và chứng thư client
    - trích xuất danh tính đã xác minh
    - tạo lại header tin cậy
          │
          │ HTTP trên loopback / HTTPS hoặc mTLS trên mạng nội bộ
          ▼
     Spring Boot API
    - đọc danh tính từ proxy đã tin cậy
    - ánh xạ danh tính → authorities
    - quyết định cho phép/không cho phép truy cập
~~~

Mục tiêu bài học:

1. Hiểu **hai mô hình nhận chứng thư**: TLS vào Java trực tiếp và TLS kết thúc ở proxy.
2. Phân biệt **chứng thư X.509 thật được xác minh** với **chuỗi HTTP header mang thông tin chứng thư**.
3. Biết cách cấu hình proxy bắt buộc client certificate, xác minh CA, chỉ chuyển tiếp danh tính đã xác minh và ngăn header spoofing.
4. Biết dùng **pre-authentication** trong Spring Security khi danh tính do proxy cung cấp; không nhầm với `http.x509()`.
5. Bảo vệ đầy đủ **client → proxy → backend**, hạn chế đường truy cập trực tiếp, theo dõi certificate lifecycle và kiểm thử các tình huống âm tính.

**Nguyên tắc quan trọng nhất:** header do client gửi có thể bị giả mạo. Một header chứa tên user hoặc PEM certificate **không chứng minh** client sở hữu private key. Chỉ được tin header danh tính khi toàn bộ đường đi và hệ thống tạo header được bảo vệ.

## 2. Ôn lại X.509 và mutual TLS

Chứng thư X.509 là tài liệu được ký số, gắn một public key với thông tin định danh và thuộc tính như subject, subject alternative name (SAN), issuer, serial number, thời hạn, key usage và extended key usage (EKU).

Với **TLS một chiều**, client xác minh chứng thư **server**. Với **mutual TLS (mTLS)**, server/proxy cũng yêu cầu client trình chứng thư hợp lệ và kiểm tra client có quyền sử dụng private key tương ứng trong TLS handshake.

Các bước đơn giản hóa:

1. Client mở kết nối TLS tới proxy.
2. Proxy đưa ra server certificate; client xác minh tên máy chủ, chuỗi tin cậy và các điều kiện áp dụng.
3. Proxy yêu cầu client certificate.
4. Client trình chuỗi chứng thư và chứng minh quyền sở hữu private key qua handshake.
5. Proxy kiểm tra chuỗi chứng thư với CA tin cậy, thời hạn, policy/EKU và cơ chế thu hồi chứng thư theo cấu hình.
6. **Chỉ khi thành công**, proxy mới tạo request HTTP tới backend và gắn danh tính lấy từ kết nối TLS.

Kết quả mTLS là chứng cứ danh tính ở **đầu kết thúc TLS**. Nếu đầu đó là proxy, Java backend không tự chứng kiến handshake của client ban đầu.

Các khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Server certificate | Chứng thư của website/proxy | Xác minh server, không thay thế client certificate |
| Client certificate | Chứng thư định danh client | Cần được kiểm tra và dùng đúng mục đích |
| Client private key | Khóa riêng của client | Không truyền qua header hay gửi cho backend |
| Subject DN | Tên phân biệt như `CN=app-client,O=Example` | Có thể không duy nhất giữa các CA hoặc chính sách cấp phát |
| SAN | Các định danh bổ sung như DNS, URI hoặc email | Nên có quy tắc ánh xạ identity ổn định |
| Issuer + serial | CA cấp và số sê-ri của chứng thư | Hữu ích cho đối chiếu, thu hồi và audit |
| CA trust store | Tập CA được phép xác nhận chứng thư client | Chỉ tin đúng CA được ủy quyền, tránh trust quá rộng |
| Certificate revocation | Cơ chế từ chối chứng thư đã thu hồi | Cần policy CRL/OCSP hoặc giải pháp tương đương; không mặc định đã bật |

## 3. Spring Security nhìn thấy gì khi TLS kết thúc tại proxy?

### 3.1. Trường hợp A: TLS vào chính servlet container

Nếu Tomcat/Jetty trực tiếp xử lý kết nối mTLS, servlet container có thể cung cấp chuỗi chứng thư client thông qua request attribute:

`jakarta.servlet.request.X509Certificate`

Spring Security Servlet có `X509AuthenticationFilter` và DSL:

~~~java
http.x509(Customizer.withDefaults());
~~~

Đây là **đoạn cấu hình minh họa** bên trong `SecurityFilterChain`, không phải chương trình độc lập. Bộ lọc đọc chứng thư được servlet container công bố, trích xuất principal, tra cứu tài khoản và gắn quyền; TLS connector chịu trách nhiệm kiểm tra handshake/chứng thư. Cần cấu hình connector/trust store đúng trước khi kỳ vọng `x509()` hoạt động.

### 3.2. Trường hợp B: TLS kết thúc ở reverse proxy

Nếu proxy nhận mTLS và gọi ứng dụng bằng HTTP, servlet container chỉ thấy kết nối từ **proxy**. Request attribute X.509 của client ban đầu thường **không tồn tại**. Gọi `http.x509()` ở backend **không tự đọc** bất kỳ header như `X-Client-Cert` hay `X-Forwarded-Client-Cert`.

Hai hướng tích hợp:

- **Pre-authentication theo danh tính:** proxy xác thực client, chọn danh tính đã xác minh và truyền qua header do **proxy tự đặt**; Spring Security dùng `RequestHeaderAuthenticationFilter`, map user/roles và kiểm tra authorization.
- **Chuyển chứng thư cho servlet container:** proxy truyền thông tin chứng thư theo định dạng của container; thành phần như **Tomcat SSLValve** (khi cấu hình đúng) có thể chuyển từ header tin cậy thành request attribute. Lúc này `x509()` mới có dữ liệu để xử lý, nhưng **phải bảo vệ đầu vào SSLValve** khỏi giả mạo. Chuyển PEM certificate không tự thay thế bước xác minh mTLS.

Bảng so sánh:

| Thuộc tính | Java nhận mTLS trực tiếp | Proxy kết thúc mTLS, truyền danh tính |
| --- | --- | --- |
| Thành phần thấy handshake client | Servlet container | Reverse proxy |
| Nguồn danh tính | Chứng thư do container công bố | Header do proxy tin cậy tạo |
| Spring Security tiêu biểu | `http.x509()` | `RequestHeaderAuthenticationFilter` + pre-auth provider |
| Xác minh client cert | TLS connector | Reverse proxy |
| Rủi ro chính | Cấu hình connector/PKI sai | Header giả mạo, proxy bypass, hop nội bộ không an toàn |
| Nguồn quyền ứng dụng | UserDetailsService/AuthenticationProvider | UserDetailsService hoặc mapping nhóm tin cậy |

**Không đồng nhất hai trường hợp:** header mang tên `X-SSL-Client-Cert` không tự biến thành thuộc tính servlet `jakarta.servlet.request.X509Certificate`.

## 4. Ranh giới tin cậy và bốn điều kiện bắt buộc

Một kiến trúc nhận identity header cần thỏa **đồng thời** các điều kiện sau.

### Điều kiện 1: Proxy thật sự xác minh chứng thư

Không chỉ kiểm tra “có header PEM” hoặc “client gửi `CN=Alice`”. Reverse proxy phải thực hiện mTLS và chỉ nhận chứng thư hợp lệ theo CA, thuật toán/policy, thời hạn, purpose (client authentication), cùng trạng thái thu hồi theo yêu cầu hệ thống.

Nếu chỉ chuyển tiếp một chứng thư công khai trong header, kẻ khác có thể **sao chép chính chứng thư ấy** mà không sở hữu private key. Việc parse PEM ở Java hay kiểm tra chữ ký CA của chứng thư không tự chứng minh người gửi HTTP chính là chủ sở hữu private key.

### Điều kiện 2: Xóa hoặc ghi đè header do client cung cấp

Ví dụ ứng dụng tin header `X-Verified-Client-DN`. Client có thể gửi:

~~~http
GET /whoami HTTP/1.1
Host: api.example.test
X-Verified-Client-DN: CN=admin,O=Example
~~~

Nếu proxy truyền nguyên header này vào backend, client có thể **mạo danh** người khác. Proxy phải bỏ header từ bên ngoài và **tạo lại** giá trị từ thông tin TLS đã kiểm tra. Tên HTTP header không phân biệt chữ hoa/chữ thường; cần kiểm soát các biến thể, header trùng tên và mọi ingress path.

Không suy diễn trust từ tên header: `X-Forwarded-Client-Cert`, `X-SSL-CERT`, `SSL_CLIENT_S_DN` hay `X-Verified-*` chỉ là **chuỗi HTTP**, giá trị tin cậy phụ thuộc hệ thống tạo ra nó.

### Điều kiện 3: Backend chỉ nhận request qua proxy đã tin cậy

Nếu Internet hoặc một workload không tin cậy có thể gọi thẳng `http://backend:8080`, chúng có thể gửi header nhận diện giả và **bỏ qua mTLS**. Vì vậy phải:

- Chặn truy cập trực tiếp bằng firewall/security group, Kubernetes NetworkPolicy, service mesh policy hoặc bind loopback.
- Hạn chế mọi cổng phụ, hostname trực tiếp, health/admin listener và đường đi qua ingress khác.
- Với proxy và backend ở **khác host**, dùng TLS xác minh server và ưu tiên mTLS giữa proxy và backend, cộng với ACL mạng.
- Kiểm tra cả trường hợp backend bị gọi qua một proxy nội bộ khác chưa sanitize header.

**Chỉ kiểm tra địa chỉ IP nguồn từ `X-Forwarded-For` không đủ**, vì đó cũng là header có thể giả mạo khi chuỗi proxy bị cấu hình sai.

### Điều kiện 4: Backend chỉ tin một danh tính được provision và cấp quyền

Chứng thư hợp lệ do CA tin cậy cấp không mặc nhiên có quyền mọi API. Backend cần ánh xạ định danh chứng thư sang tài khoản/service đã được provision và gắn authorities phù hợp.

Không nên tự coi mọi `CN` là username có quyền cao. Với các tổ chức nhiều CA, chủ thể (subject) trùng tên, chứng thư được cấp lại, thay đổi SAN hoặc nhóm phân quyền khác nhau, cần một khóa ánh xạ ổn định (ví dụ issuer + serial, định danh SAN được kiểm soát, hoặc ID nội bộ do proxy tạo sau policy check). Kiểm tra cả certificate rotation và thu hồi quyền.

## 5. Ví dụ NGINX: nhận mTLS và chuyển danh tính đã xác minh

Ví dụ dưới đây dành cho **NGINX và Spring Boot chạy cùng host**. Spring lắng nghe ở `127.0.0.1:8080`; NGINX là cổng duy nhất cho client bên ngoài.

Các giả định học tập:

- `api.example.test` trỏ về proxy; server certificate có SAN hợp lệ cho tên đó.
- `/etc/nginx/certs/server.crt` và `server.key` thuộc proxy; `client-ca.crt` là CA được phép cấp **client** certificate cho hệ thống này.
- Client dùng chứng thư có subject DN chính xác `CN=app-client,O=Example` khi NGINX xuất theo RFC 2253.
- Quản trị hệ thống đã cấu hình certificate lifecycle, CA trust, revocation policy và phân quyền file khóa riêng.

Cấu hình NGINX mẫu (ngữ cảnh `server`):

~~~nginx
server {
    listen 443 ssl;
    server_name api.example.test;

    ssl_certificate     /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;

    # CA được tin để xác minh chứng thư của CLIENT.
    ssl_client_certificate /etc/nginx/certs/client-ca.crt;
    ssl_verify_client on;
    ssl_verify_depth 2;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8080;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;

        # Ghi đè thông tin từ client bằng giá trị do TLS tại NGINX cung cấp.
        proxy_set_header X-Verified-Client-DN $ssl_client_s_dn;

        # Loại bỏ những header nhận diện không được ứng dụng sử dụng.
        proxy_set_header X-Forwarded-Client-Cert "";
        proxy_set_header X-SSL-Client-Cert "";
    }
}
~~~

**Giải thích quan trọng:**

- `ssl_verify_client on` yêu cầu và xác minh client certificate. Chứng thư không có, không hợp lệ hoặc không thuộc CA tin cậy bị từ chối **tại proxy**; không được chuyển vào Spring như một user đã xác thực.
- `ssl_client_certificate` chỉ định CA cho client verification, **khác** `ssl_certificate` dùng làm server certificate.
- `$ssl_client_s_dn` lấy subject DN của client certificate mà kết nối TLS đã trình (NGINX bản hiện đại trả biểu diễn RFC 2253). Đây là **danh tính được proxy dẫn xuất sau mTLS**, không phải nội dung header gốc.
- `proxy_set_header X-Verified-Client-DN ...` chủ động **đặt lại** header trong request upstream. Nếu client gửi một header cùng tên, giá trị tới backend phải do proxy thay thế.
- Các lệnh `proxy_set_header ... ""` minh họa việc không chuyển tiếp các header chứng thư khác vốn có thể bị client giả mạo. Rà soát toàn bộ các tên header thực tế mà backend/sidecar/framework có thể tin.
- `proxy_pass http://127.0.0.1:8080` chỉ phù hợp khi **cùng máy**, backend bind loopback và local host được kiểm soát. Đây không phải cấu hình an toàn cho hop qua mạng giữa hai máy.

**Cấu hình của NGINX cần được kiểm tra trên phiên bản đang triển khai.** Nếu cài các `proxy_set_header` ở cấp `location`, các directive cùng loại kế thừa từ cấp trên có thể không còn được áp dụng như dự tính; hãy kiểm tra cấu hình hiệu lực và lưu lượng upstream.

### 5.1. Khi proxy và backend ở hai máy khác nhau

Cần HTTPS và xác thực upstream; cấu hình sau là **đoạn minh họa** thay cho `proxy_pass` HTTP trên loopback, chỉ dùng khi backend thực sự phục vụ HTTPS với CA và chính sách tương ứng:

~~~nginx
proxy_pass https://app.internal.example:8443;
proxy_ssl_server_name on;
proxy_ssl_name app.internal.example;
proxy_ssl_verify on;
proxy_ssl_trusted_certificate /etc/nginx/certs/backend-ca.crt;

# Bật khi backend cũng yêu cầu xác thực proxy bằng mTLS:
proxy_ssl_certificate /etc/nginx/certs/proxy-client.crt;
proxy_ssl_certificate_key /etc/nginx/certs/proxy-client.key;
~~~

- `proxy_ssl_verify on` buộc proxy kiểm tra chứng thư backend; mặc định của nhiều triển khai reverse proxy không nên được suy là đã xác minh upstream.
- Backend cần giới hạn cổng 8443 để chỉ proxy được phép kết nối và xác minh client certificate của proxy nếu dùng mTLS upstream.
- Vẫn phải **sanitize và tạo lại header danh tính** ở đúng điểm tin cậy; HTTPS giữa các hop không ngăn một proxy sai chuyển tiếp header giả.
- Nếu có nhiều lớp load balancer/ingress/mesh, ghi rõ lớp nào thực hiện mTLS client, lớp nào tạo lại identity, lớp nào xóa header bên ngoài. Không giả định NGINX ở hop thứ hai vẫn thấy chứng thư client của hop thứ nhất.

## 6. Ví dụ Spring Security: pre-authentication qua header đã bảo vệ

### 6.1. Chọn đúng cơ chế

Spring Security có `RequestHeaderAuthenticationFilter` để đọc principal từ một request header do hệ thống xác thực bên ngoài cung cấp. Filter này **không kiểm tra chứng thư hoặc chữ ký số**. Nó chỉ đọc username; kết quả được chuyển cho `AuthenticationManager` và `PreAuthenticatedAuthenticationProvider` để nạp thông tin tài khoản và authorities.

Vì vậy ví dụ dưới đây **chỉ được sử dụng phía sau proxy đã cấu hình mTLS + kiểm soát header + chặn backend bypass**. Chạy riêng Spring Boot rồi gửi header tùy ý có thể mạo danh user; đó là tính chất của cơ chế pre-authentication, không phải lỗi xảy ra sau khi build.

### 6.2. Tạo dự án

Dùng **Java 17+**, **Spring Boot 3.x** và Spring Security 6.x tương ứng. Tạo dự án Maven trên Spring Initializr với:

- `spring-boot-starter-web` (Spring MVC/Servlet, Tomcat nhúng).
- `spring-boot-starter-security`.

Không cần `spring-security-ldap` vì bài này không thực hiện LDAP bind. Không cần một dependency X.509 riêng để dùng `RequestHeaderAuthenticationFilter`; class nằm trong Spring Security Web do starter security cung cấp.

Tệp `src/main/resources/application.properties`:

~~~properties
# Demo: NGINX và Spring Boot cùng host.
server.address=127.0.0.1
server.port=8080
~~~

Trong môi trường container/Kubernetes, địa chỉ bind và NetworkPolicy phải được thiết kế theo topology thật. Lấy cấu hình loopback này áp dụng nguyên xi vào hai container khác nhau thường khiến NGINX không kết nối được; không mở public backend để chữa lỗi mạng.

### 6.3. Java hoàn chỉnh

Tạo tệp `src/main/java/demo/mtls/ProxyCertificateDemoApplication.java`:

~~~java
package demo.mtls;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsByNameServiceWrapper;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationProvider;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.authentication.preauth.RequestHeaderAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ProxyCertificateDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProxyCertificateDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        // Demo provisioning: chỉ chủ thể đã đăng ký được cấp ROLE_MTLS_CLIENT.
        var user = User.withUsername("CN=app-client,O=Example")
                .password("{noop}not-used-for-mtls")
                .roles("MTLS_CLIENT")
                .build();
        var users = new InMemoryUserDetailsManager(user);

        var userDetails =
                new UserDetailsByNameServiceWrapper<PreAuthenticatedAuthenticationToken>();
        userDetails.setUserDetailsService(users);

        var provider = new PreAuthenticatedAuthenticationProvider();
        provider.setPreAuthenticatedUserDetailsService(userDetails);

        // Tạo filter bên trong chain, tránh servlet container tự đăng ký
        // thêm một Filter bean độc lập bên ngoài Spring Security.
        var preAuthFilter = new RequestHeaderAuthenticationFilter();
        preAuthFilter.setPrincipalRequestHeader("X-Verified-Client-DN");
        preAuthFilter.setExceptionIfHeaderMissing(true);
        preAuthFilter.setAuthenticationManager(new ProviderManager(provider));

        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").hasRole("MTLS_CLIENT")
                .anyRequest().denyAll())
            .addFilterBefore(preAuthFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @RestController
    static class CertificateApi {
        @GetMapping("/whoami")
        Map<String, String> whoAmI(Authentication authentication) {
            return Map.of("principal", authentication.getName());
        }
    }
}
~~~

### 6.4. Vì sao cấu hình này đúng vai trò?

1. `RequestHeaderAuthenticationFilter` đọc `X-Verified-Client-DN`, trích thành principal cho pre-authentication. Nó **không gọi TLS, không kiểm tra chain**, không xem client private key.
2. `PreAuthenticatedAuthenticationProvider` xử lý token pre-authentication và nhờ `UserDetailsByNameServiceWrapper` truy vấn `InMemoryUserDetailsManager`. Chỉ DN đã provision trong ví dụ mới nạp được user có role `MTLS_CLIENT`.
3. Mật khẩu `not-used-for-mtls` là dữ liệu bắt buộc cho đối tượng `UserDetails` của ví dụ; provider **không so sánh password** trong đường đi pre-auth. Không lưu chứng thư/private key vào đó.
4. Rule `hasRole("MTLS_CLIENT")` kiểm tra `ROLE_MTLS_CLIENT`. User khác hoặc không có role phù hợp bị từ chối authorization.
5. `SessionCreationPolicy.STATELESS` tránh dựa vào session để duy trì danh tính: với mỗi request, proxy cần cung cấp danh tính tương ứng với **kết nối TLS client của chính request ấy**. Không thay thế policy về session của ứng dụng khác nếu có nhiều security chain.
6. Filter được tạo **bên trong** method cấu hình, không khai báo riêng thành `@Bean Filter` để tránh Spring Boot tự đăng ký nó lần thứ hai ngoài `springSecurityFilterChain`.

Ví dụ có một account cố định để minh họa. Hệ thống thực tế nên tra identity mapping/roles từ cấu hình có kiểm soát hoặc cơ sở dữ liệu, hỗ trợ certificate rotation, tenant isolation và cập nhật quyền. Nếu hai certificate có cùng subject DN nhưng không được phép coi là một identity, chỉ dùng DN như ví dụ là **không đủ**; phải thay bằng định danh mà policy cấp chứng thư đảm bảo tính duy nhất.

### 6.5. Chạy và kiểm tra

Từ thư mục Maven của dự án:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu không có Maven Wrapper, dùng `mvn spring-boot:run`.

Sau khi NGINX và certificate thật đã được thiết lập, kiểm thử bằng client certificate hợp lệ:

~~~bash
curl --cert client.crt --key client.key \
     --cacert server-ca.crt \
     https://api.example.test/whoami
~~~

Các tệp phải trỏ đến chứng thư/khóa test tương thích, server CA thực tế, DNS tên máy chủ chính xác. Lệnh trên dành cho shell hỗ trợ `\` tiếp dòng (Linux/macOS); ở Windows có thể viết trên một dòng. Không tắt TLS verification bằng `-k`.

Nếu chứng thư client hợp lệ và subject DN khớp user minh họa, response dự kiến:

~~~json
{"principal":"CN=app-client,O=Example"}
~~~

Thứ tự/escaping DN có thể khác theo nội dung certificate thực tế và phiên bản proxy. Khi khác, đối chiếu kết quả RFC 2253 và mapping identity của hệ thống; không tự đổi username một cách tùy tiện.

Các kiểm thử âm tính quan trọng:

| Thử nghiệm | Kết quả mong đợi | Thành phần phải chặn |
| --- | --- | --- |
| Không gửi client certificate | Request không được upstream như user đã xác thực | NGINX mTLS |
| Client certificate không thuộc CA được trust | Bị từ chối ở biên TLS | NGINX mTLS |
| Chứng thư hết hạn/không được phép sử dụng | Bị từ chối theo policy TLS/PKI | NGINX/PKI |
| Client không có cert nhưng tự gửi `X-Verified-Client-DN: CN=app-client,O=Example` | Vẫn bị từ chối | NGINX mTLS |
| Client có cert hợp lệ nhưng gửi header giả chỉ tới NGINX | Backend vẫn phải nhận DN do NGINX trích từ TLS, không nhận DN giả | NGINX header overwrite |
| Client cert hợp lệ nhưng DN chưa được provision | Không được cấp quyền vào `/whoami` | Spring Security |
| Gọi trực tiếp backend từ mạng ngoài với header giả | Không thể thiết lập kết nối đến backend | Firewall/bind/NetworkPolicy |
| User được xác thực nhưng thiếu authority cần thiết | Bị từ chối theo rule authorization | Spring Security |

Mã lỗi HTTP cụ thể của chứng thư không hợp lệ phụ thuộc phiên bản và cấu hình NGINX (TLS handshake, xử lý mã nội bộ 495/496, error_page); không nên viết test hard-code tất cả tình huống là 401.

**Thử nghiệm xác thực độ tin cậy:** từ **chính host** nơi backend nghe loopback, nếu gửi một header giả trực tiếp tới `127.0.0.1:8080`, filter pre-auth có thể chấp nhận nó. Điều này chứng minh vì sao **isolation của backend là một phần bắt buộc trong security design**. Hệ thống sản xuất phải giới hạn cả khả năng local workload lạ truy cập listener đó.

## 7. Bảo vệ header theo từng lớp

### 7.1. Tin đúng đầu tạo ra identity

Danh tính phải do thành phần đã **thực sự xác minh mTLS** cung cấp. Nếu một load balancer ở ngoài cùng xác minh certificate nhưng NGINX phía trong chỉ nhận HTTP, NGINX không thể tự khẳng định `$ssl_client_s_dn` phản ánh client ban đầu. Cần truyền identity qua **kênh được xác thực giữa các hop** và bảo đảm mọi hop bỏ input giả từ Internet.

Nhiều proxy có cơ chế riêng như `X-Forwarded-Client-Cert`; cấu hình phải chỉ rõ hành vi **sanitize / set / append / forward**, mức tin cậy của upstream/downstream và việc header nào được ứng dụng đọc. Tránh mặc định mọi giá trị đến từ XFCC đều đã qua TLS verification.

### 7.2. Không tin giá trị chỉ vì trông giống PEM

Nếu proxy chuyển chứng thư dưới dạng PEM qua header:

- NGINX có `$ssl_client_escaped_cert` (URL-encoded PEM) dùng cho một số tích hợp container; biến `$ssl_client_cert` cũ đã bị khuyến cáo không dùng.
- Phải có giới hạn kích thước header, decode đúng một lần và xử lý lỗi encoding.
- Header PEM **không tự chứng minh possession của private key**. Proxy vẫn phải xác minh client trong handshake.
- Nếu dùng Tomcat `SSLValve`, chỉ chấp nhận header SSL do proxy tin cậy tạo và bảo đảm container không mở đường truy cập bypass. Không tự bật SSLValve vì thấy header có chữ `CERT`.
- Nếu backend tự thực hiện kiểm tra chuỗi chứng thư, nó vẫn phải hiểu được chứng cứ mTLS của **proxy** và đường truyền tin cậy; chỉ kiểm tra chữ ký chứng thư ở backend là chưa đủ.

### 7.3. Chống header injection, duplicate và normalization

HTTP header names không phân biệt hoa/thường. Các gateway và thư viện có thể xử lý dấu gạch dưới, gạch ngang hoặc nhiều header cùng tên theo cách khác nhau. Cần:

- Xác định chính xác **một** tên header hợp lệ để làm principal.
- Xóa/ghi đè giá trị đến từ client ở **mọi đường ingress**.
- Không ghép tùy ý nhiều giá trị danh tính hoặc chấp nhận danh sách nhập bởi client.
- Đặt chính sách chặn header bất thường, giá trị rỗng/quá dài, điều khiển CRLF và encoding lạ tại gateway.
- Giữ nguyên danh tính đã xác minh qua một quy tắc canonicalization thống nhất với hệ thống provisioning.
- Cẩn trọng nếu áp dụng thêm `ForwardedHeaderFilter` hoặc cấu hình forward headers của Spring Boot: các thành phần này chủ yếu xử lý host/scheme/client IP và **không biến một header client certificate thành chứng cứ mTLS**.

### 7.4. Không làm lộ chứng thư hoặc nội dung nhạy cảm

Không ghi private key, full PEM, subject nhạy cảm hoặc chi tiết certificate vào access log chung. Chỉ ghi tối thiểu các trường phục vụ điều tra: request/correlation ID, kết quả verify, identity nội bộ, issuer/serial hoặc fingerprint theo chính sách, nguyên nhân bị từ chối ở mức phù hợp. Log phải có phân quyền và retention.

Nếu dùng SAN/email/CN để nhận diện, coi đây là **dữ liệu do PKI cấp** chứ không phải chuỗi tự do để đưa thẳng vào SQL, đường dẫn, nội dung HTML hoặc policy expression. Mọi truy vấn và mapping vẫn phải validate input.

## 8. Chứng thư hợp lệ chưa đồng nghĩa được phép truy cập

Spring Security tách **authentication** (ai đang gọi) khỏi **authorization** (người đó được làm gì).

Ví dụ:

- NGINX xác minh client certificate do CA nội bộ cấp.
- Header mang DN `CN=partner-7,O=Example`.
- Backend xác nhận DN đã provision nhưng chỉ gắn `ROLE_READER`.
- Endpoint `/admin` đòi `ROLE_ADMIN` nên vẫn từ chối.

Có nhiều cách ánh xạ certificate sang identity:

| Cách ánh xạ | Ưu điểm | Rủi ro cần quản lý |
| --- | --- | --- |
| Subject DN | Đơn giản, dễ đọc | Có thể trùng, đổi cách biểu diễn, không ổn định khi cấp lại |
| SAN URI/DNS/email | Diễn tả identity rõ theo policy PKI | Cần đảm bảo CA cấp phát đúng namespace và extension |
| Issuer + serial | Phân biệt từng certificate theo CA | Rotation cấp serial mới, phải cập nhật mapping |
| Fingerprint | Gắn với một certificate cụ thể | Rotation đổi giá trị; lựa chọn thuật toán và bảo quản fingerprint |
| Internal subject ID sau bước policy tại proxy | Tách ứng dụng khỏi định dạng certificate | Phải bảo vệ logic mapping và header đầu ra của proxy |

Nếu dùng NGINX chuẩn, `$ssl_client_fingerprint` là fingerprint SHA-1; không nên tự xem SHA-1 là khóa định danh dài hạn có yêu cầu chống va chạm mạnh. Với hệ thống phức tạp, có thể dùng lớp xác thực chuyên biệt sinh identity dựa trên SAN/issuer/serial và chuyển qua cơ chế được bảo vệ.

## 9. Những lỗi thường gặp

### Lỗi 1: bật `http.x509()` dù TLS đã kết thúc ở proxy

Triệu chứng: NGINX báo client certificate hợp lệ nhưng Spring Security không nhận được certificate trong servlet request.

Nguyên nhân: `http.x509()` không tự đọc `X-Client-Cert`. Cách xử lý: sử dụng pre-auth header đáng tin cậy **hoặc** cấu hình tích hợp container (như SSLValve) để tạo request attribute từ proxy đã tin cậy.

### Lỗi 2: backend mở public

Triệu chứng: kẻ gọi thẳng cổng backend với identity header có thể vượt qua bước mTLS ở NGINX.

Cách xử lý: bind đúng interface, firewall, deny-by-default network policy, authenticated internal transport; kiểm tra tất cả route phụ.

### Lỗi 3: proxy chuyển nguyên header của client

Triệu chứng: một `X-Verified-Client-DN` giả được backend tin.

Cách xử lý: xóa/ghi đè header đầu vào tại điểm tin cậy; kiểm tra NGINX config sau khi include các file và xác nhận packet thực đến backend trong lab.

### Lỗi 4: chỉ bật HTTPS client → proxy

Triệu chứng: client gửi mTLS an toàn nhưng identity header bị quan sát hoặc sửa trên mạng nội bộ giữa proxy và app.

Cách xử lý: HTTPS xác minh backend, ưu tiên mTLS upstream và ACL mạng nếu khác host hoặc khác ranh giới tin cậy. Không tắt `proxy_ssl_verify` để vượt lỗi chứng thư.

### Lỗi 5: nhầm “chứng thư hợp lệ” với “client có quyền”

Triệu chứng: mọi certificate thuộc CA tin cậy đều truy cập API quản trị.

Cách xử lý: mapping identity xác định rõ, provisioning, kiểm tra role/authority và deny-by-default.

### Lỗi 6: quên chứng thư bị thu hồi hoặc đổi mới

Triệu chứng: certificate từng hợp lệ tiếp tục được chấp nhận dù đã thu hồi, hoặc ứng dụng từ chối service mới sau rotation.

Cách xử lý: thiết kế CA trust/CRL/OCSP hoặc policy tương đương, giám sát thời hạn, quy trình cập nhật mapping và diễn tập rotation.

### Lỗi 7: hai lớp proxy không nhất quán

Triệu chứng: identity thật bị mất, bị chuyển thành DN của proxy hoặc bị lẫn header của client.

Cách xử lý: vẽ rõ hop TLS, nguồn identity và transform ở từng lớp; kiểm tra SAN, issuer, gateway policy và header sanitization end-to-end.

### Lỗi 8: nhầm 401, 403 và lỗi TLS

- Client certificate không hợp lệ có thể bị chặn **tại proxy hoặc trong TLS**, Spring không nhận request.
- Identity đã qua mTLS nhưng user không được provision có thể bị pre-auth provider từ chối.
- Identity đã xác thực nhưng thiếu quyền có thể nhận **403** từ Spring Security.
- HTTP status cuối cùng phụ thuộc entry point và exception handling, không chỉ loại exception Java.

## 10. Checklist triển khai và kiểm thử

### Cấu hình

- [ ] Đầu kết thúc mTLS được xác định rõ, CA tin cậy giới hạn đúng client.
- [ ] Kiểm tra chain, thời hạn, clientAuth/EKU, revocation theo policy tổ chức.
- [ ] Proxy xóa/ghi đè mọi identity header do client gửi.
- [ ] Hệ thống chỉ có các ingress path được kiểm soát, backend không public.
- [ ] Kênh proxy → backend được bảo vệ phù hợp với topology (loopback cô lập hoặc TLS/mTLS + ACL).
- [ ] Nguồn identity (SAN/DN/issuer/serial/ID nội bộ) có quy tắc chuẩn hóa và uniqueness rõ ràng.
- [ ] Mapping authority theo nguyên tắc ít quyền nhất và deny-by-default.
- [ ] Cơ chế cấp mới, rotation, thu hồi chứng thư và cập nhật quyền được kiểm thử.
- [ ] Log/audit tối thiểu, không làm lộ PEM/private key/headers nhạy cảm.

### Kiểm thử

- [ ] Valid cert + mapped identity → request hợp lệ được cho qua.
- [ ] No cert / wrong CA / expired/revoked cert → không có đường vào backend đã xác thực.
- [ ] Spoof identity header từ Internet → proxy thay thế hoặc loại bỏ, không đổi identity.
- [ ] Direct request tới backend → bị network isolation chặn.
- [ ] Valid cert nhưng unmapped identity → bị từ chối.
- [ ] Mapped identity không có role → bị từ chối authorization.
- [ ] TLS upstream sai CA/hostname, proxy hoặc backend bị lỗi → fail closed.
- [ ] Certificate renewal/rotation và nhiều proxy hop → identity đúng, không mất hoặc bị nhập nhằng.

**Kiểm thử chỉ bằng MockMvc hoặc unit test có gắn header không đủ để kết luận an toàn.** Những test đó chỉ xác minh mapping ở Spring; phải có integration test chạy qua proxy thật và kiểm tra firewall/network path, vì TLS verification và header overwrite nằm ngoài Java.

## 11. Câu hỏi tự kiểm tra

1. Vì sao `http.x509()` có thể không thấy client certificate khi NGINX terminate TLS?
2. Tại sao header chứa PEM certificate không chứng minh client sở hữu private key?
3. Nếu proxy không ghi đè `X-Verified-Client-DN`, kẻ tấn công có thể làm gì?
4. Chỉ bật HTTPS client → proxy có đủ bảo vệ identity giữa proxy và backend không?
5. Vì sao đã xác minh CA vẫn cần whitelist/provisioning identity và authorization theo role?
6. Điều gì có thể xảy ra nếu hai client certificate hợp lệ có cùng subject DN?
7. Một HTTP status 403 có luôn có nghĩa là client certificate bị từ chối không?
8. Test nào chứng minh backend không thể bị gọi trực tiếp bằng header giả?

Khi phân biệt được nơi thực hiện **chứng minh sở hữu khóa riêng**, nơi **tạo header danh tính**, nơi **quyết định quyền truy cập**, bạn sẽ thiết kế và review được luồng X.509 sau reverse proxy mà không đặt niềm tin nhầm chỗ.

## 12. Tài liệu tham khảo chính thức

- [Spring Security — X.509 Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html)
- [Spring Security — Pre-Authentication Scenarios](https://docs.spring.io/spring-security/reference/servlet/authentication/preauth.html)
- [Spring Security — RequestHeaderAuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/RequestHeaderAuthenticationFilter.html)
- [Spring Security — PreAuthenticatedAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/preauth/PreAuthenticatedAuthenticationProvider.html)
- [NGINX — ngx_http_ssl_module: client certificate verification and variables](https://nginx.org/en/docs/http/ngx_http_ssl_module.html)
- [NGINX — Securing HTTP Traffic to Upstream Servers](https://docs.nginx.com/nginx/admin-guide/security-controls/securing-http-traffic-upstream)
- [Apache Tomcat — SSLValve documentation](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html)
