# HTTPS giữa trình duyệt, proxy, ứng dụng và nhà cung cấp danh tính trong Spring Security WebFlux

## 1. Vì sao HTTPS phải được bảo vệ trên từng chặng?

Một ứng dụng Spring Security **reactive** thường không trực tiếp nhận kết nối TLS từ trình duyệt: trình duyệt gọi reverse proxy hoặc load balancer; proxy chuyển tiếp tới Spring Boot WebFlux (Reactor Netty); ứng dụng lại gọi Identity Provider (IdP) để thực hiện OAuth2/OpenID Connect, tải JWK Set hoặc introspect token. **HTTPS bên ngoài không tự động bảo vệ các chặng phía sau.**

Mục tiêu của bài học là hiểu chính xác **ai thiết lập TLS với ai, ai được quyền xác nhận scheme/host gốc, ứng dụng xây URL OAuth2 như thế nào và cách kiểm thử rằng cả luồng không bị hạ xuống HTTP**.

Sau bài này, người học có thể:

1. Vẽ luồng TLS cho trình duyệt, proxy, WebFlux và IdP; chỉ ra điểm giải mã và mã hóa lại.
2. Lựa chọn TLS termination, TLS re-encryption hoặc mutual TLS (mTLS) theo trust boundary.
3. Cấu hình `Forwarded`/`X-Forwarded-*` an toàn để WebFlux nhìn thấy URL HTTPS công khai, không tin header do client tùy ý gửi.
4. Cấu hình đúng OAuth2/OIDC redirect URI, session cookie, HSTS, HTTPS redirect và kết nối TLS từ ứng dụng đến IdP.
5. Chẩn đoán các lỗi thực tế: redirect loop, `redirect_uri_mismatch`, mất session callback, certificate handshake fail, HSTS thiếu và giả mạo forwarded headers.

**Ngữ cảnh:** Java 17+, Spring Boot 3.x với Spring Security 6.x và WebFlux/Reactor Netty. Các đoạn Nginx là cấu hình minh họa cho một kiến trúc cụ thể; khi dùng Gateway API, Kubernetes Ingress, Envoy, Traefik hoặc cloud load balancer, áp dụng cùng nguyên tắc trust boundary theo cơ chế tương ứng. Không dùng `HttpSecurity`/`ForwardedHeaderFilter` của Servlet để giải quyết ứng dụng reactive.

## 2. Phân biệt bốn kết nối

Giả sử địa chỉ công khai là `https://app.example.com`, địa chỉ upstream nội bộ là `https://app.internal.example:8443`, IdP là `https://login.example.com`.

```text
                           (A) TLS: app.example.com
+-----------+  HTTPS  +---------------------+
| Browser   | ------> | Edge proxy / LB     |
+-----------+         | chấm dứt TLS A      |
      |               | làm sạch forwarded  |
      |               +----------+----------+
      |                          |
      |               (B) TLS: app.internal.example
      |                          |
      |                          v
      |               +---------------------+
      |               | Spring Boot WebFlux  |
      |               | SecurityWebFilterChain|
      |               +----------+----------+
      |                          |
      |               (C) TLS: login.example.com
      |                          |
      |                          v
      |               +---------------------+
      +--- (D) HTTPS --> Identity Provider  |
          browser       OAuth2/OIDC         |
          front-channel +--------------------+
```

**Bốn kết nối có vai trò khác nhau:**

| Chặng | Ai là TLS client → TLS server? | Dữ liệu quan trọng | Kiểm tra bắt buộc |
| --- | --- | --- | --- |
| A. Browser → proxy | Browser → proxy công khai | Session cookie, Bearer token, OAuth authorization code trong URL callback | Chứng chỉ tin cậy, DNS/SAN đúng hostname, redirect HTTP→HTTPS, HSTS |
| B. Proxy → WebFlux | Proxy → ứng dụng nội bộ | Cookie, Authorization header, body, thông tin forwarded | Mã hóa lại TLS, xác minh upstream certificate; giới hạn truy cập chỉ từ proxy |
| C. WebFlux → IdP | HTTP client của ứng dụng → token/JWKS/introspection/userinfo endpoint | `client_secret`, authorization code, refresh/access token, JWK | HTTPS, chuỗi CA và hostname IdP hợp lệ, timeout, không cho trust-all |
| D. Browser → IdP | Browser → trang đăng nhập/authorize của IdP | Mật khẩu, MFA, consent, `state`, `code_challenge` | HTTPS IdP với chứng chỉ hợp lệ, kiểm soát redirect URI, không phát token qua HTTP |

**Quan trọng:** một nút mũi tên HTTPS chỉ bảo vệ **chặng đó**. Khi proxy giải mã TLS A, request đã ở dạng rõ trong bộ nhớ proxy; nếu chuyển tiếp B qua HTTP, người có quyền quan sát mạng giữa hai thành phần có thể đọc dữ liệu. Kết nối D do **trình duyệt trực tiếp** thiết lập đến IdP; kết nối C do **backend** chủ động thiết lập và có chứng chỉ/CA trust riêng.

Các OAuth2 flow phải được phân loại đúng:

- **OAuth2 Login/OIDC Client:** trình duyệt được redirect đến IdP trên D, IdP redirect ngược về callback công khai A, backend trao đổi `code` lấy token với IdP trên C.
- **JWT Resource Server:** trình duyệt/client gửi Bearer JWT tới API trên A/B, Resource Server có thể tải public JWK từ IdP qua C để kiểm tra chữ ký; không nhất thiết có browser login.
- **Opaque Token Resource Server:** backend gọi introspection endpoint qua C để kiểm tra token; OAuth2 login callback không bắt buộc tồn tại.

Một ứng dụng có thể đóng nhiều vai trò nhưng phải xác định từng endpoint và SecurityWebFilterChain tương ứng; không trộn ý nghĩa redirect URI của client với endpoint xác minh của Resource Server.

## 3. TLS termination, re-encryption và mTLS

### 3.1. Các mô hình thường gặp

**Mô hình 1 – Termination tại proxy; proxy → ứng dụng là HTTP:**

```text
Browser --HTTPS--> Proxy --HTTP--> App
```

Dễ vận hành nhưng chặng sau proxy **không được mã hóa**. Chỉ chấp nhận khi chính sách/hạ tầng chứng minh được mạng nội bộ đáng tin và phạm vi rủi ro được phê duyệt. Không xem “cùng VPC” hay “cùng Kubernetes cluster” là bằng chứng có TLS.

**Mô hình 2 – TLS re-encryption (khuyến nghị cho môi trường nhạy cảm):**

```text
Browser --HTTPS--> Proxy --HTTPS--> App
```

Có hai TLS session độc lập: certificate công khai của proxy và certificate nội bộ của ứng dụng. Proxy phải **xác minh** certificate upstream, bao gồm CA, thời hạn và hostname/SAN. Chỉ dùng `https://` ở `proxy_pass` nhưng tắt xác thực upstream vẫn có nguy cơ bị chèn máy chủ giả.

**Mô hình 3 – mTLS cho chặng nội bộ:**

```text
Browser --HTTPS--> Proxy --mTLS--> App
```

Ứng dụng yêu cầu proxy xuất trình client certificate; proxy vẫn kiểm tra server certificate của ứng dụng. mTLS bổ sung xác thực hai chiều giữa các workload; không thay thế xác thực người dùng OAuth2/OIDC hoặc phân quyền. Việc chuyển xác thực client certificate của browser qua header tùy biến là một bài toán khác và cũng cần trust boundary được thiết kế riêng.

### 3.2. Quy tắc đối với chứng chỉ

- Chứng chỉ của `app.example.com` phải hợp lệ đối với **hostname công khai**. Chứng chỉ của upstream `app.internal.example` phải hợp lệ với tên mà proxy dùng để kiểm tra TLS upstream, không nhất thiết trùng hostname công khai.
- TLS 1.3 ưu tiên; TLS 1.2 có thể duy trì khi cần tương thích với cipher suite được đánh giá là an toàn. Tắt phiên bản TLS cũ và cipher yếu theo chuẩn tổ chức.
- Tự động gia hạn certificate, theo dõi thời hạn và kiểm tra full certificate chain; cấp phát private key bằng secret manager hoặc cơ chế lưu trữ có phân quyền, tránh commit vào repository/container image.
- Certificate pinning cố định dễ gây sự cố khi xoay vòng; với phần lớn ứng dụng server-to-server, dùng CA trust phù hợp, hostname verification và chính sách cấp/chuyển chứng chỉ được quản lý.
- Kiểm tra mối quan hệ **SNI + SAN + DNS**; tên upstream trong DNS không khớp certificate thường gây `SSLHandshakeException`/`certificate_unknown`.

## 4. Cấu hình reverse proxy: xử lý HTTPS và trust boundary

### 4.1. Proxy phải tự tạo thông tin về request công khai

Khi browser gọi:

```http
GET /oauth2/authorization/company HTTP/1.1
Host: app.example.com
```

proxy có thể chuyển đến `https://app.internal.example:8443`, trong khi Spring cần biết bên ngoài người dùng đã dùng `https://app.example.com`. Các header thường gặp:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
X-Forwarded-Port: 443
X-Forwarded-For: <địa chỉ IP client do proxy xác định>
```

RFC 7239 chuẩn hóa biến thể:

```http
Forwarded: for=<client>;proto=https;host=app.example.com
```

**Không được tin giá trị do trình duyệt tự khai.** Kẻ tấn công có thể gửi `X-Forwarded-Host: attacker.example` hoặc `Forwarded: proto=http;host=attacker.example`. Nếu edge proxy giữ lại header đó, WebFlux có thể xây URL redirect/password reset/callback theo hostname không tin cậy, gây redirect sai, host-header injection hoặc lộ thông tin.

Tại **ranh giới mạng được tin cậy**, proxy phải xóa/ghi đè **cả nhóm** `Forwarded` (RFC 7239) và các biến thể `X-Forwarded-*`. Không chỉ xóa một tên và để loại khác lọt qua. Nếu có nhiều proxy, mỗi hop phải có quy tắc rõ ai là nguồn chân lý của host, scheme, port và client IP; không mặc định lấy phần tử đầu danh sách do client có thể tiêm vào.

### 4.2. Ví dụ Nginx có re-encryption

Cấu hình dưới đây minh họa **một edge proxy độc lập** nhận public traffic; sử dụng tên miền/certificate nội bộ hợp lệ đã được cấp. Các đường dẫn certificate là đường dẫn cấu hình triển khai, không phải tệp được bài học tạo sẵn.

```nginx
server {
    listen 80;
    server_name app.example.com;
    return 308 https://app.example.com$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/nginx/tls/public-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/public-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass https://app.internal.example:8443;

        # Mã hóa lại tới ứng dụng và thực sự kiểm tra chứng chỉ nội bộ.
        proxy_ssl_server_name on;
        proxy_ssl_name app.internal.example;
        proxy_ssl_verify on;
        proxy_ssl_trusted_certificate /etc/nginx/tls/internal-ca.pem;
        proxy_ssl_verify_depth 2;

        # Chỉ dùng canonical public host đã được triển khai.
        proxy_set_header Host app.example.com;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.com;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;

        # Loại các biến thể không sử dụng khỏi request đi tới app.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

**Giải thích:** `proxy_ssl_verify on` và CA nội bộ là hai cài đặt quan trọng của TLS upstream; `proxy_ssl_name` phải khớp certificate của ứng dụng. `$remote_addr` có nghĩa là IP peer mà Nginx nhìn thấy; nếu còn CDN/LB phía trước thì cần thiết kế thêm chuỗi trusted proxy trước khi coi đó là IP người dùng.

Ví dụ cố ý gắn host công khai cố định; với nhiều virtual host, phải xây host allowlist/route policy tương ứng chứ không truyền `Host` tùy ý như một địa chỉ redirect đáng tin. Bảo vệ cổng `8443` để chỉ proxy/đối tượng có quyền được kết nối; cấu hình nginx chỉ là một phần, còn firewall/network policy/TLS certificate vẫn phải vận hành đúng.

**Lưu ý 308:** một lần truy cập HTTP ban đầu vẫn diễn ra trước khi trình duyệt được redirect; không gửi credentials vào URL HTTP. Dùng HSTS đã được browser ghi nhớ hoặc chính sách preload sau khi đánh giá đầy đủ các subdomain để giảm rủi ro của request đầu tiên.

## 5. Để Spring Boot WebFlux hiểu scheme và host bên ngoài

### 5.1. `ForwardedHeaderTransformer`, không phải Servlet filter

WebFlux dùng `org.springframework.web.server.adapter.ForwardedHeaderTransformer` để xử lý các header đã được proxy tin cậy làm sạch. Với Spring Boot 3.x, cách cấu hình thuận tiện:

```yaml
server:
  forward-headers-strategy: framework
```

`FRAMEWORK` yêu cầu Spring Framework xử lý forwarded headers; trong ứng dụng reactive, cơ chế tương ứng là `ForwardedHeaderTransformer`. `NATIVE` sử dụng khả năng của web server và phải kiểm tra cụ thể server đang chạy; `NONE` không áp dụng forwarded headers. Không tùy tiện khai báo thêm bean `ForwardedHeaderTransformer` nếu Boot đã cấu hình cùng trách nhiệm và không hiểu tác động chồng chéo.

**Điều kiện tiên quyết:** ứng dụng chỉ nhận các forwarded headers do proxy đáng tin đã xác định; có network policy chặn truy cập trực tiếp từ bên ngoài đến app. `ForwardedHeaderTransformer` **không tự xác thực** xem header tới từ proxy hợp lệ hay từ attacker. Khi không có proxy đáng tin và không cần áp dụng header, dùng `NONE` hoặc transformer `removeOnly` để loại header thay vì áp dụng dữ liệu không tin cậy.

Tác động cần kiểm tra sau cấu hình:

- `ServerHttpRequest.getURI()` phản ánh public `https://app.example.com/...` khi request thực sự tới qua proxy hợp lệ.
- Generated redirect/link của Spring Security sử dụng host và scheme công khai thích hợp.
- HTTPS redirect trong filter chain **không tạo vòng lặp vô hạn** do nhầm request HTTPS của browser thành HTTP phía sau TLS termination.
- Các log, redirect và cookie không phát tán tên máy nội bộ hoặc cổng `8443`.

### 5.2. Nếu ứng dụng cũng bật HTTPS trên cổng nội bộ

Ví dụ `application-prod.yml` của Spring Boot 3.x:

```yaml
server:
  port: 8443
  forward-headers-strategy: framework

  ssl:
    enabled: true
    key-store: ${APP_TLS_KEYSTORE}
    key-store-type: PKCS12
    key-store-password: ${APP_TLS_KEYSTORE_PASSWORD}

  reactive:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

`APP_TLS_KEYSTORE` là đường dẫn PKCS#12 do môi trường triển khai cấp. Nếu private key có mật khẩu riêng, cấu hình `server.ssl.key-password` tương ứng. Certificate trong keystore phải có SAN phù hợp với upstream hostname proxy kiểm tra. Mật khẩu keystore đi qua secret injection; không đặt literal secret trong Git.

`server.reactive.session.cookie.*` áp dụng cho cơ chế session cookie reactive do Boot quản lý; nếu ứng dụng dùng Spring Session hoặc custom `WebSessionIdResolver`, phải kiểm tra cookie serializer/resolver đang thực sự phát `Set-Cookie`. Không dùng nhầm `server.servlet.session.cookie.*` cho WebFlux.

**Một cách khác:** nếu TLS được chấm dứt tại proxy và đường truyền tới ứng dụng ở HTTP theo kiến trúc đã được phê duyệt, không bật SSL listener nội bộ như trên; dù vậy forwarded headers vẫn phải được quản lý và rủi ro HTTP hop cần được ghi nhận. Bài học dùng TLS re-encryption làm cấu hình mục tiêu.

## 6. Cấu hình Spring Security reactive: HTTPS redirect và HSTS

Spring Security bảo vệ request ở lớp ứng dụng nhưng bản thân nó **không mở cổng TLS**; TLS là trách nhiệm của web server/proxy. Khi cần ứng dụng chủ động chuyển request HTTP sang HTTPS, dùng `ServerHttpSecurity.redirectToHttps()`.

Một cấu hình Java 17+ hoàn chỉnh về mặt cú pháp cho **ứng dụng OAuth2 Login WebFlux** (lưu tại `src/main/java/example/https/SecureLoginApplication.java` trong một project Spring Boot đã có WebFlux và OAuth2 Client):

```java
package example.https;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class SecureLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureLoginApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .redirectToHttps(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        Mono<String> publicPage() {
            return Mono.just("HTTPS boundary demo");
        }

        @GetMapping("/private")
        Mono<String> privatePage() {
            return Mono.just("Only authenticated users");
        }
    }
}
```

Gradle Groovy dependencies tối thiểu cho ví dụ Spring Boot có dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Ví dụ chỉ chạy thành công khi đã cung cấp certificate/keystore và OAuth2 client registration với IdP thực hoặc IdP thử nghiệm đáng tin cậy (xem mục 7). Lệnh chạy trong dự án Gradle có wrapper:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod'
```

Windows PowerShell dùng `.\gradlew.bat bootRun --args='--spring.profiles.active=prod'`. Khi kết nối HTTPS, `GET /public` trả body **chính xác** `HTTPS boundary demo`; truy cập chưa đăng nhập vào `/private` kích hoạt OAuth2 login theo cấu hình. Đây là ứng dụng **OAuth2 Login**, không phải mẫu JWT Resource Server; nếu ứng dụng chỉ nhận Bearer JWT, thay `.oauth2Login(...)` bằng `.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` trong cấu hình riêng và cung cấp `issuer-uri`.

### 6.1. Tránh HTTPS redirect loop

Khi browser đã dùng HTTPS nhưng proxy → app là HTTP, nếu app chỉ nhìn thấy `http://internal-host:8080` mà không xử lý trusted `X-Forwarded-Proto: https`, `.redirectToHttps(...)` có thể liên tục tạo 3xx. Cách giải quyết đúng là:

1. Proxy chuẩn hóa scheme/host/port và loại header giả mạo.
2. WebFlux bật forwarded-header strategy thích hợp khi request qua proxy.
3. HTTPS redirect được đặt tại edge hoặc tại Spring Security sau khi có request URI chính xác.
4. Dùng `curl`/trình duyệt kiểm tra chuỗi `Location`; đừng chữa bằng cách tắt TLS verification hoặc tiếp tục redirect vô hạn.

Ở kiến trúc đã có HTTPS redirect tại edge, có thể để edge là nguồn phát redirect 80→443, nhưng vẫn giữ cơ chế phát hiện scheme HTTPS chính xác tại ứng dụng phục vụ OAuth callback và cookies.

### 6.2. HSTS chỉ có ý nghĩa trên HTTPS public response

Spring Security hỗ trợ **HTTP Strict Transport Security** và mặc định bật HSTS khi điều kiện secure request phù hợp. Header ví dụ:

```http
Strict-Transport-Security: max-age=31536000
```

`includeSubDomains` ảnh hưởng đến **toàn bộ** subdomain; `preload` yêu cầu tuân thủ chính sách preload trước khi đăng ký. Không thêm các directive này chỉ để “mạnh hơn” nếu vẫn có subdomain phục vụ HTTP hay khả năng quay lui certificate chưa sẵn sàng.

Nếu proxy phát HSTS thay ứng dụng, bảo đảm chính sách tập trung và không sinh nhiều header trái nhau. Kiểm tra header tại **địa chỉ HTTPS công khai**, không chỉ tại port nội bộ. Browser bỏ qua HSTS trên response HTTP; redirect HTTP→HTTPS đơn thuần không bảo vệ hoàn toàn request đầu tiên.

## 7. HTTPS trong luồng OAuth2 Login / OpenID Connect

### 7.1. Luồng authorization code qua proxy

```text
1. Browser -> https://app.example.com/private
2. App -> 302 /oauth2/authorization/company
3. Browser -> https://app.example.com/oauth2/authorization/company
4. App -> 302 https://login.example.com/.../authorize
          ?response_type=code
          &client_id=...
          &redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
          &state=... [&code_challenge=...]
5. Browser -> HTTPS IdP /authorize; người dùng đăng nhập
6. IdP -> Browser -> 302
          https://app.example.com/login/oauth2/code/company?code=...&state=...
7. Browser -> HTTPS app callback (qua proxy)
8. App -> HTTPS IdP token endpoint (backend POST + code, client auth, PKCE verifier nếu áp dụng)
9. App thiết lập phiên theo chính sách, trả response/cookie HTTPS
```

Bước 4 và 6 là **front channel qua browser**. Bước 8 là **back channel app → IdP**. Không đưa `client_secret`, refresh token, access token vào query string browser. `state` phải được kiểm tra khớp transaction, PKCE S256 là thực hành tốt cho authorization code flow; với OIDC, xử lý `nonce` và issuer theo vai trò/khả năng của client library.

### 7.2. Redirect URI phải trùng chính xác

Trong Spring Security WebFlux, callback mặc định là:

```text
/login/oauth2/code/{registrationId}
```

Với `registrationId=company`, cấu hình IdP đăng ký chính xác:

```text
https://app.example.com/login/oauth2/code/company
```

Ví dụ `application-prod.yml` bổ sung:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company-idp:
            issuer-uri: https://login.example.com/realms/company
```

Phần provider dựa trên OIDC discovery: issuer URI phải **khớp metadata và claim `iss` thực** của IdP; nơi IdP công bố authorize/token/JWK endpoints cũng cần được xác minh và dùng HTTPS. URL `example.com` ở đây là tên ví dụ, khi triển khai cần thay bằng DNS/certificate/issuer thực tế của hệ thống. Client secret chỉ inject qua secret store hoặc biến môi trường được bảo vệ.

Với metadata từ trusted proxy, `{baseUrl}` được tạo theo `https://app.example.com`, không theo tên hoặc port upstream. Nếu xuất hiện `redirect_uri=http://app.internal.example:8443/...` hoặc `redirect_uri=http://app.example.com/...`, kiểm tra trust/scheme/port tại proxy và `server.forward-headers-strategy` trước. Không nới policy IdP cho phép wildcard redirect URI hoặc HTTP callback ở production để che lỗi này.

### 7.3. Session cookie và cross-site callback

Nếu ứng dụng dùng OAuth2 Login và lưu session phía server, browser cần gửi lại cookie để đối chiếu OAuth2 `state` khi callback. Ví dụ header an toàn cho cookie session:

```http
Set-Cookie: SESSION=<id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

- `Secure` chỉ gửi cookie qua HTTPS.
- `HttpOnly` giảm nguy cơ JavaScript đọc cookie; không ngăn toàn bộ XSS.
- `SameSite=Lax` thường phù hợp cho OAuth2 code callback bằng **top-level GET navigation**, dù IdP khác site.
- `SameSite=Strict` có thể khiến browser không gửi cookie khi quay lại từ IdP khác site; `state`/session bị mất.
- Khi dùng `response_mode=form_post` (cross-site POST), `Lax` có thể không được gửi; phải thiết kế cookie `SameSite=None; Secure` và CSRF/session binding phù hợp, xét cả hạn chế third-party cookie của trình duyệt.
- Hạn chế `Domain`; cookie chỉ cho host công khai thường an toàn hơn cookie dùng chung mọi subdomain. Kiểm tra `Path`, thời hạn và session store khi ứng dụng chạy nhiều instance.

Với API chỉ nhận Bearer token từ `Authorization`, việc ứng dụng dùng session cookie có thể không cần thiết. Dù thế, Bearer token vẫn phải đi trong HTTPS và không lộ qua URL, logs, referer hoặc hệ thống quan sát.

## 8. HTTPS từ WebFlux tới IdP: đúng trust store và hostname

### 8.1. Những endpoint backend thường gọi

| Mục đích | Ví dụ URL | Yêu cầu |
| --- | --- | --- |
| OIDC discovery | `https://login.example.com/realms/company/.well-known/openid-configuration` | CA/hostname được tin cậy; xác minh `issuer` |
| Token exchange / refresh | `https://login.example.com/realms/company/protocol/openid-connect/token` | HTTPS, client authentication, không log code/secret/token |
| UserInfo | Endpoint HTTPS do metadata IdP công bố | Gửi access token theo contract, kiểm tra issuer/subject |
| JWK Set | HTTPS `jwks_uri` | Tải khóa công khai có nguồn tin cậy; tiếp tục kiểm chữ ký JWT và claims |
| Opaque introspection | HTTPS introspection URI | Credential backend, xác minh `active`, timeout và error policy |

TLS xác thực server IdP **không thay thế** việc validate `iss`, `aud`, `exp`, `nbf`, chữ ký, `nonce` hoặc trạng thái `active`. TLS bảo vệ **đường truyền đến đúng đối tác**; xác thực OAuth2/OIDC bảo vệ **ý nghĩa của token và quyền**.

Nếu dùng private CA hoặc certificate của IdP trong mạng nội bộ, cấu hình Java/Netty HTTP client trust **đúng CA được phê duyệt**. Không dùng `InsecureTrustManagerFactory`, `trustAll`, `curl -k`, bỏ hostname verification hoặc tạo SSLContext “accept all” để sửa lỗi TLS. JVM có trust store riêng; `curl` hoặc `openssl` thành công trên máy không bảo đảm Java cũng tin cùng CA. Tránh vô tình thay đổi trust store toàn process khi chỉ cần một HTTP client có trust bundle riêng.

### 8.2. Resource Server: URI luôn HTTPS

Với JWT Resource Server, cấu hình ví dụ (trong **profile/context riêng** của Resource Server):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/company
```

Với opaque-token Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/realms/company/protocol/openid-connect/token/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Tên và đường dẫn endpoint phải lấy từ metadata/tài liệu của **IdP thực tế**. Cả hai cấu hình chỉ mô tả phương án xác thực; dùng `.oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` **hoặc** `.opaqueToken(...)` theo loại token, và bảo vệ route bằng `SecurityWebFilterChain`.

Không chuyển `issuer-uri` sang HTTP chỉ vì deployment bên trong cluster; đừng để chính sách firewall/DNS vô tình cho phép gọi tên IdP do attacker điều khiển. Khi IdP lỗi certificate, ứng dụng phải fail closed cho việc xác thực cần kiểm tra mạng, thay vì vô hiệu hóa TLS verification hoặc cấp quyền tạm.

### 8.3. Timeout, retry và thông tin nhạy cảm

TLS handshake có thể thất bại vì CA, hostname, certificate hết hạn, TLS version/cipher không tương thích, SNI hoặc mTLS thiếu client certificate. Chẩn đoán nguyên nhân cụ thể, giữ timeout kết nối/response hữu hạn. Retry có giới hạn với sự cố tạm thời khi logic cho phép; tuyệt đối không fallback sang HTTP hoặc endpoint không được tin cậy. Tránh ghi body request token endpoint, `Authorization`, access token, refresh token, client secret vào access logs, distributed tracing hoặc exception response.

## 9. Các rủi ro ngoài TLS mà HTTPS không tự giải quyết

**CSRF:** HTTPS không ngăn cross-site request mang cookie. Với browser session/login, giữ CSRF protection phù hợp của Spring Security (trừ khi có lý do và kiến trúc token rõ ràng), kiểm tra OAuth `state`/PKCE/nonce. Không tắt CSRF toàn cục để chữa lỗi callback khi nguyên nhân là cookie `SameSite` hoặc redirect URI.

**XSS và mixed content:** HTTPS không loại bỏ JavaScript độc hại. Tất cả CSS, JS, font, image, API calls và WebSocket phải dùng HTTPS/WSS; Content Security Policy phù hợp hỗ trợ giảm rủi ro. Các asset `http://` trên trang HTTPS có thể bị browser chặn hoặc tạo rủi ro tải nội dung không an toàn.

**CORS:** redirect browser sang IdP authorization endpoint **không đòi** CORS giữa app và IdP; đó là top-level navigation. CORS áp dụng khi JavaScript muốn truy cập cross-origin API. Không mở `Access-Control-Allow-Origin: *` kết hợp credential để “sửa” login. Backend gọi token/introspection/JWKS qua HTTPS không chịu browser CORS.

**Token replay:** Bearer token có thể bị dùng lại nếu rò từ logs, history hoặc client; TLS giảm rủi ro nghe lén, nhưng phải hạn chế quyền/thời hạn token, cân nhắc sender-constrained token/mTLS/DPoP theo yêu cầu hệ thống.

**Open redirect và host spoofing:** đừng lấy `returnUrl`, `redirect_uri` hoặc `X-Forwarded-Host` không kiểm soát để tạo Location tùy ý. IdP phải đối chiếu redirect URI chính xác; ứng dụng phải hạn chế host/đích redirect có thể nhận.

## 10. Kiểm thử trên môi trường triển khai

Các lệnh sau chạy từ máy có DNS và quyền truy cập đúng tới môi trường; ví dụ sử dụng domain minh họa và cần thay bằng domain thật.

### 10.1. Xác minh browser → proxy

```bash
# HTTP nên chuyển về canonical HTTPS (trên edge).
curl -sS -D - -o /dev/null http://app.example.com/public

# HTTPS phải xác thực chứng chỉ; không thêm -k.
curl -sS -D - -o /dev/null https://app.example.com/public

# Theo dõi chain certificate và SNI.
openssl s_client -connect app.example.com:443 \
  -servername app.example.com -verify_return_error </dev/null
```

Kết quả kỳ vọng theo cấu hình mẫu: request HTTP nhận `308` và `Location: https://app.example.com/public`; request HTTPS `/public` nhận `200` và nội dung công khai khi dùng GET; certificate hợp lệ theo hostname và CA tin cậy. Kiểm tra `Strict-Transport-Security` trên HTTPS response khi HSTS được bật. Không đưa `-k` vào script QA vì nó che certificate failure.

### 10.2. Xác minh proxy → ứng dụng

- Nginx đang dùng `proxy_pass https://...` và `proxy_ssl_verify on`; certificate upstream có SAN `app.internal.example` và chain tới CA đã cấu hình.
- Trong log/metrics, không có 502/525/SSL handshake error giữa proxy và app.
- Firewall/network policy ngăn Internet truy cập thẳng `:8443` và bỏ qua bước làm sạch forwarded headers.
- Nếu chuyển giả lập upstream certificate sang certificate sai tên/hết hạn, kết nối phải **thất bại**; không tự động bỏ xác minh để duy trì traffic.

### 10.3. Kiểm thử URL OAuth2 và chống spoofed headers

```bash
# Địa chỉ /oauth2/authorization/company thường trả 302 tới IdP.
curl -sS -D - -o /dev/null \
  https://app.example.com/oauth2/authorization/company

# Cố tình đưa forwarded host/proto giả từ bên ngoài.
curl -sS -D - -o /dev/null \
  -H 'Forwarded: proto=http;host=attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: attacker.example' \
  https://app.example.com/oauth2/authorization/company
```

Điều phải quan sát: `Location` hướng đến **IdP đã tin cậy**; tham số `redirect_uri` (URL-encoded) chỉ có `https://app.example.com/login/oauth2/code/company`, không chứa `http://`, `attacker.example` hay `app.internal.example`. Nếu app không có OAuth2 Login, kiểm thử cùng nguyên tắc trên route thực sự tạo absolute redirect/link.

### 10.4. Xác minh cookie và callback

Kiểm tra `Set-Cookie` sau khi session được tạo và callback thành công: phải có `Secure`, `HttpOnly`, `SameSite`/Path/Domain đúng thiết kế. Chạy flow browser thật vì `curl` không tái hiện chính xác cookie policy SameSite. Dùng trình duyệt quan sát network: authorize HTTPS → callback HTTPS → token exchange backend HTTPS → ứng dụng tạo session → truy cập trang bảo vệ được. Mất session sau callback thường liên quan SameSite, Domain, Path hoặc session store, không phải vì HTTPS không hoạt động.

### 10.5. Xác minh app → IdP

Từ môi trường runtime backend, xác nhận DNS/SNI/cert chain IdP; sau đó chạy **integration test bằng chính HTTP client của ứng dụng** để kiểm tra trust store Java, timeout và error handling. Giả lập certificate không tin cậy, hostname không khớp, IdP 5xx hoặc mất mạng: authentication phải thất bại có kiểm soát, không có fallback HTTP hay bypass kiểm tra token. Không trích xuất hoặc in token thật vào terminal/CI.

## 11. Ma trận lỗi vận hành và hướng chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh và sửa |
| --- | --- | --- |
| Redirect lặp 301/302/307/308 | Browser HTTPS nhưng app nghĩ request HTTP | Kiểm tra `X-Forwarded-Proto`, transformer, điểm đặt HTTPS redirect |
| IdP báo `redirect_uri_mismatch` | Callback có `http`, host nội bộ, port 8443 hoặc path sai | Kiểm tra `Location` và URI đăng ký chính xác ở IdP |
| Browser callback nhưng báo state/session invalid | Cookie `Secure`/`SameSite`/Domain/Path không phù hợp; nhiều instance không chia session | Kiểm tra browser cookie jar, route callback, session store; giữ `state` binding |
| Trình duyệt cảnh báo chứng chỉ | Cert hết hạn, chain sai, SAN không khớp | Kiểm tra cert công khai với SNI/hostname và CA chuẩn |
| Proxy trả 502 ngay sau bật HTTPS upstream | SNI/CA/SAN upstream sai hoặc ứng dụng chưa mở TLS 8443 | Kiểm tra `proxy_ssl_*`, keystore, Netty listener, CA và DNS |
| Backend không gọi được IdP | Java trust store thiếu CA, hostname mismatch, proxy outbound sai, TLS version | Kiểm tra stacktrace SSL handshake, DNS/SNI; cấu hình trust đúng, không trust-all |
| HSTS không xuất hiện | Chỉ kiểm tra HTTP; app không nhìn thấy secure request; edge chưa phát header | Kiểm tra response HTTPS public, forwarded scheme và layer sở hữu HSTS |
| `Location` chứa host attacker | Proxy không ghi đè `Forwarded`/`X-Forwarded-Host` | Xóa/overwrite tại edge, ràng buộc hosts, ngăn gọi app trực tiếp |
| API request không thể xác thực khi IdP downtime | Introspection/JWKS cần mạng nhưng IdP/CA không sẵn sàng | Kiểm tra timeout/cache policy, phát hiện sự cố; **không** fail-open |
| Cookie không có `Secure` | Cookie policy cấu hình sai hoặc lớp phát cookie không dùng cấu hình Boot | Kiểm tra WebFlux `server.reactive.session.cookie.*` và resolver/session framework thực tế |

### Một tình huống trước–sau

**Trước:** browser gọi `https://app.example.com`, edge chuyển về `http://app:8080`, chuyển tiếp `X-Forwarded-Proto` do browser cung cấp; Spring không hiểu địa chỉ public. `/oauth2/authorization/company` sinh `redirect_uri=http://app:8080/login/oauth2/code/company`. IdP từ chối, hoặc browser bị redirect sai. Attacker còn có thể giả mạo host.

**Sau:** edge chỉ nhận HTTPS public hợp lệ, chuẩn hóa `Host=app.example.com`, `X-Forwarded-Proto=https`, `X-Forwarded-Host=app.example.com`, chặn spoofed `Forwarded`; proxy → app dùng TLS verified; `server.forward-headers-strategy=framework` làm WebFlux suy ra đúng public URI. IdP nhận `redirect_uri=https://app.example.com/login/oauth2/code/company`, callback quay về qua HTTPS; backend trao đổi code qua HTTPS với IdP có CA/SAN hợp lệ. Từng điểm có thể kiểm tra riêng và không cần bỏ qua xác minh certificate.

## 12. Checklist trước khi triển khai production

- [ ] Public domain chỉ phục vụ tài nguyên nhạy cảm qua HTTPS; HTTP được redirect có kiểm soát; certificate full chain, SAN, SNI, hạn sử dụng đã xác minh.
- [ ] TLS proxy → WebFlux được bảo vệ theo trust boundary đã phê duyệt; nếu HTTPS, **bật upstream certificate verification**; cổng app nội bộ không lộ ra Internet.
- [ ] Proxy loại giá trị `Forwarded` và `X-Forwarded-*` không tin cậy và phát host/scheme/port chuẩn.
- [ ] Spring WebFlux xử lý forwarded headers phù hợp qua `server.forward-headers-strategy`; không thêm Servlet filter để chữa vấn đề reactive.
- [ ] HTTPS redirect không lặp vô hạn, không lộ hostname/port nội bộ trong absolute links.
- [ ] HSTS có trên public HTTPS response; chỉ sử dụng `includeSubDomains`/`preload` sau khi đánh giá tác động toàn domain.
- [ ] OAuth2/OIDC dùng HTTPS IdP issuer và callback URI **trùng chính xác** đăng ký; `state`, PKCE/nonce được áp dụng theo flow.
- [ ] Session cookie `Secure`, `HttpOnly`, SameSite, Path, Domain phù hợp; browser callback hoạt động qua proxy.
- [ ] Các kết nối WebFlux → IdP (discovery/token/JWKS/introspection/userinfo) xác minh CA và hostname; không có trust-all hoặc HTTP fallback.
- [ ] Client secret, keystore password, private key, Bearer token, authorization code không xuất hiện trong Git, URL ngoài ý muốn hay access logs.
- [ ] Test bao gồm forwarded-header spoofing, redirect URI, certificate mismatch, IdP TLS failure và timeout; các lỗi đều không tạo authenticated principal ngoài ý muốn.

## Tài liệu chuẩn để đào sâu

- Spring Boot 3.3 — [Common Application Properties (forward headers, reactive session cookies, SSL)](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/).
- Spring Boot — [Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/reference/how-to/webserver.html#howto.webserver.configure-behind-a-proxy).
- Spring Security 6.5 — [Reactive HTTP: redirect to HTTPS, HSTS, proxy](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/http.html).
- Spring Security 6.5 — [Reactive Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html).
- Spring Security 6.5 — [OAuth2 Login core configuration, redirect URI](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html).
- Spring Framework — [ForwardedHeaderTransformer JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/adapter/ForwardedHeaderTransformer.html).
- IETF — [RFC 7239: Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239); [RFC 9700: OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
- IETF — [RFC 6797: HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797).

**Kết quả cần đạt:** có thể chứng minh từ **bên ngoài tới bên trong** rằng browser, proxy, WebFlux và IdP đều giao tiếp qua đường truyền được bảo vệ phù hợp; các URL/cookie OAuth2 phản ánh đúng hostname HTTPS công khai; mọi certificate và forwarded header đều được kiểm tra theo đúng ranh giới tin cậy.