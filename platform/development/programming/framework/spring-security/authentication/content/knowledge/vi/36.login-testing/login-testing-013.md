# Kiểm thử qua container, proxy và trình duyệt cho hành vi cookie, TLS thực tế

## 1. Mục tiêu và tình huống xuất phát

Một ứng dụng Spring Security đăng nhập bằng form. `MockMvc` kiểm tra đúng username/password, trả redirect khi thành công. Tuy vậy, ở production sau Nginx/load balancer, người dùng có thể bị đưa về trang login vì browser **không giữ hoặc không gửi JSESSIONID**, cookie thiếu `Secure`/`SameSite`, proxy đưa sai scheme/port, hoặc session không được dùng chung giữa các pod.

Đây là lý do phải thử qua **container, proxy, TLS handshake và browser thật**, thay vì chỉ chạy Java unit test.

Sau bài học bạn có thể:
- Phân biệt xác thực Java/Spring với hành vi cookie/session của user agent.
- Kiểm tra `Set-Cookie`, `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, session expiration, session fixation và logout.
- Kiểm tra public HTTPS URL, SAN của certificate, trust chain và redirect; không dùng `curl -k` hay `ignoreHTTPSErrors:true` để “pass” test.
- Triển khai lab Spring Boot **3.3.12**, Java **17+**, Docker Compose, Nginx TLS termination và Chromium/Playwright.
- Thử cross-site POST thực tế từ `127.0.0.1` sang `localhost`, phân biệt cookie SameSite với CSRF token.
- Kiểm tra `Forwarded`/`X-Forwarded-*` không bị attacker giả mạo, backend không mở direct HTTP port.
- Dùng JDK `HttpClient` để đo TLS và cookie flags, nhưng không nhầm với chính sách browser.
- Lập test matrix cho các node, session store, CI, cert rotation và browser compatibility.

**Phạm vi:** Spring Security Servlet/Spring MVC. Với WebFlux dùng reactive SecurityWebFilterChain, không sao chép thẳng `HttpSecurity`. Host và mật khẩu trong bài chỉ là **dữ liệu lab**.

## 2. Vì sao các tầng test phải được tách biệt?

| Tầng | Kiểm tra tốt | Không đủ chứng minh |
| --- | --- | --- |
| Unit test JUnit | PasswordEncoder, UserDetails, logic đăng nhập và khóa tài khoản | TLS, browser cookie acceptance |
| MockMvc | Spring Security filters, CSRF, login/logout status, redirect logic mô phỏng | Handshake, certificate hostname, SameSite gửi cookie |
| Curl/JDK HttpClient | HTTPS handshake/CA nếu không bypass, status, Location, Set-Cookie | Browser navigation/iframe/site-for-cookies |
| Docker Compose/Testcontainers | App, proxy, network, container port và forwarding | Browser có lưu/gửi cookie hay không |
| Playwright | Browser cookie jar, HTTPS page load, network Cookie header, SameSite, login/logout E2E | Các browser/OS khác và production multi-node |
| Multi-node staging | LB, sticky routing, shared session, restart/revoke, cert rotation | Không thay thế authorization/coding review |

**Quan điểm đo:** Phải quan sát một request sau login **được browser gửi kèm Cookie** và backend nhận đúng principal. Chỉ thấy HTTP 200 trên request login, hay thấy server phát `Set-Cookie`, chưa đủ.

## 3. Các thuộc tính cookie cần kiểm tra

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**`Secure`:** browser hạn chế cookie tới HTTPS, có ngoại lệ `localhost` ở một số trình duyệt. Không dùng test HTTP localhost để kết luận cookie Secure không bao giờ lộ trên public HTTP.

**`HttpOnly`:** JavaScript không thể đọc session ID qua `document.cookie` nhưng browser vẫn tự gửi cookie theo policy. HttpOnly **không** thay CSRF defense.

**`SameSite=Lax`:** hạn chế phần lớn cross-site unsafe requests như POST; vẫn có thể gửi cookie trong top-level safe navigation. `Strict` chặt hơn; `None` cần `Secure` và còn phụ thuộc third-party cookie restrictions. `SameSite` không loại bỏ mọi CSRF.

**`Path`:** quyết định URL path nào nhận cookie. `Path=/` bao phủ ứng dụng ở root.

**`Domain`:** nếu không đặt, cookie là **host-only**; nếu đặt `Domain=example.org` có thể gửi sang nhiều subdomain, gồm các subdomain có mức tin cậy thấp. Với browser API `context.cookies()`, trường domain được chuẩn hóa; cần đọc **raw Set-Cookie** để khẳng định header không có thuộc tính `Domain`.

**`Expires`/`Max-Age`:** persistence của cookie phía browser khác TTL của server-side session. Cookie tồn tại không có nghĩa session server còn hiệu lực.

**`JSESSIONID`:** là bearer secret; không log giá trị cookie hoặc đưa Playwright storage state/traces chứa cookie thật vào artifact công khai.

### 3.1. Same-origin khác same-site

~~~text
https://localhost:8443  vs  https://localhost:9443
=> Khác origin vì port, nhưng thường CÙNG site.

https://localhost:8443  vs  https://127.0.0.1:9443
=> Khác host và khác site (phù hợp cross-site lab).

https://app.example.org  vs  https://blog.example.org
=> Khác origin nhưng thường cùng site theo registrable domain.
~~~

Để test `SameSite=Lax` không gửi cookie vào cross-site POST, **không** chỉ đổi port ở cùng `localhost`. Phải sử dụng site khác thực sự như địa chỉ IP loopback trong lab. Hành vi còn phụ thuộc scheme, request method, top-level navigation, iframe và browser version.

### 3.2. Ba bằng chứng về cookie

1. **Raw response `Set-Cookie`:** backend/proxy phát thuộc tính gì?
2. **Browser cookie jar:** browser có chấp nhận/lưu nó với flags phù hợp không?
3. **Browser network request tiếp theo:** browser thực sự gửi cookie cho đúng URL và context không?

`curl` nhìn thấy `Set-Cookie` nhưng không đủ để chứng minh browser lưu. `document.cookie` không thấy `JSESSIONID` có thể là **đúng** vì HttpOnly. Cần kết hợp cả ba bằng chứng và kiểm tra principal/session server.

## 4. TLS thực tế và reverse proxy

Trên public HTTPS, client cần xác minh:
- Certificate chain đến CA được tin cậy, leaf cert có SAN đúng hostname/IP.
- Cert còn hạn, SNI/hostname và trust store khớp.
- Handshake dùng TLS version/cipher theo policy (thường TLSv1.2/TLSv1.3).
- Không downgrade sang HTTP khi login, logout hoặc redirect.
- Session cookie có `Secure` và browser chỉ dùng qua kết nối bảo vệ tương ứng.
- Reverse proxy được phép chuyển TLS→HTTP nội bộ chỉ khi mạng/ứng dụng có trust boundary rõ.
- Không nhận `Forwarded: proto=https;host=attacker.invalid` do người ngoài tự khai như nguồn sự thật.

**Tránh anti-pattern:** `curl -k`, `ignoreHTTPSErrors:true`, Java trust-all `SSLContext`/`HostnameVerifier`, bỏ certificate checks trong CI. Chúng có thể tạm dùng để phân biệt lỗi trong môi trường chẩn đoán riêng, **không phải test TLS đạt yêu cầu**.

Spring có thể nhìn thấy `request.isSecure()==true` do forwarded headers dù client thực tế không xác minh cert. Vì thế phải thử **từ phía browser/HTTP client**, không chỉ assert request metadata trong JVM.

## 5. Kiến trúc lab end-to-end

~~~text
Browser / Playwright
   |
   +--> https://localhost:8443
   |          |
   |          v
   |       Nginx TLS:443
   |          | X-Forwarded-Proto=https
   |          | X-Forwarded-Host=localhost:8443
   |          | X-Forwarded-Port=8443
   |          v
   |       Spring Boot app:8080 (Docker private network)
   |
   +--> https://127.0.0.1:9443
              |
              v
           Nginx static attack.html:4444
              |
              +-- HTML form POST -> https://localhost:8443/profile/name
~~~

Target site và attack site đều thuộc sở hữu lab. `app` **không công bố port 8080 ra host**; chỉ Nginx publish 8443/9443 tới loopback `127.0.0.1`. Người thử không gửi credential thật tới địa chỉ ngoài quyền kiểm soát.

Cấu trúc:

~~~text
cookie-tls-login-lab/
├── settings.gradle
├── build.gradle
├── Dockerfile
├── compose.yaml
├── nginx.conf
├── certs/                     # generated; không commit
├── attacker/attack.html
├── src/main/
│   ├── java/demo/cookie/
│   │   ├── CookieApplication.java
│   │   ├── SecurityConfig.java
│   │   └── SessionController.java
│   └── resources/application.yml
├── HttpsCookieProbe.java
├── package.json
├── playwright.config.js
└── e2e/session.spec.js
~~~

`.gitignore`:

~~~gitignore
certs/
build/
.gradle/
node_modules/
playwright-report/
test-results/
*.trace.zip
~~~

Không commit leaf private key, CA private key, browser storage state hay log chứa Cookie/Set-Cookie nguyên văn.

## 6. Spring Boot 3.3.12 + Java 17: build và cấu hình session

`settings.gradle`:

~~~groovy
rootProject.name = 'cookie-tls-login-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  forward-headers-strategy: framework
  tomcat:
    redirect-context-root: false
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

spring:
  application:
    name: cookie-tls-login-lab
~~~

- `secure: true` yêu cầu cookie session được phát có Secure, kể cả khi proxy gọi app bằng HTTP nội bộ.
- `http-only: true` ngăn JS đọc cookie session.
- `same-site: lax` là giá trị tường minh, tránh phụ thuộc browser default.
- `forward-headers-strategy: framework` bật Spring `ForwardedHeaderFilter`. **Chỉ dùng khi proxy đã kiểm soát, làm sạch và ghi đè forwarded headers, backend không public**.
- `redirect-context-root: false` giúp Tomcat phía sau TLS-terminating proxy áp dụng forwarded scheme đúng thời điểm tạo redirect.

**Không tự coi `server.forward-headers-strategy=framework` là “secure”**: app có thể tin header giả nếu ingress đưa nó qua mà không sanitize.

### 6.1. Entrypoint

`src/main/java/demo/cookie/CookieApplication.java`:

~~~java
package demo.cookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieApplication.class, args);
    }
}
~~~

### 6.2. Spring Security: form login, CSRF và logout

`src/main/java/demo/cookie/SecurityConfig.java`:

~~~java
package demo.cookie;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("lab-password-123456"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .anyRequest().authenticated())
                .formLogin(login ->
                        login.defaultSuccessUrl("/whoami", true))
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Spring Security render `GET /login` và xử lý `POST /login`; redirect success tới `/whoami`. Khi CSRF bật, form login có hidden token; `POST /logout` cũng cần token, còn `GET /logout` thường là trang xác nhận. Trước login có thể tạo session để lưu CSRF token; sau login mặc định đổi session ID (session fixation protection). `InMemoryUserDetailsManager` chỉ dùng cho lab; production dùng user store, account status, MFA và rate limit phù hợp.

### 6.3. Controller để nhìn public scheme/host/port và test CSRF

`src/main/java/demo/cookie/SessionController.java`:

~~~java
package demo.cookie;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.MediaType;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.HtmlUtils;

@RestController
public class SessionController {

    // Chỉ lab: một biến dùng chung, production phải lưu theo account ID.
    private final AtomicReference<String> displayName =
            new AtomicReference<>("Initial");

    @GetMapping(value = "/health", produces = MediaType.TEXT_PLAIN_VALUE)
    public String health() {
        return "OK";
    }

    @GetMapping("/whoami")
    public Map<String, Object> whoami(
            Principal principal, HttpServletRequest request) {
        return Map.of(
                "user", principal.getName(),
                "scheme", request.getScheme(),
                "secure", request.isSecure(),
                "host", request.getServerName(),
                "port", request.getServerPort());
    }

    @GetMapping("/profile/name")
    public Map<String, String> readProfile() {
        return Map.of("displayName", displayName.get());
    }

    @GetMapping(value = "/settings",
            produces = MediaType.TEXT_HTML_VALUE)
    public String settings(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        if (token == null) {
            throw new IllegalStateException("CSRF token unavailable");
        }

        return """
                <!doctype html>
                <html lang="en">
                <head><meta charset="UTF-8"></head>
                <body>
                <form method="post" action="/profile/name">
                  <input type="hidden" name="%s" value="%s">
                  <label for="displayName">Display name</label>
                  <input id="displayName" name="value">
                  <button type="submit">Save</button>
                </form>
                </body></html>
                """.formatted(
                        HtmlUtils.htmlEscape(token.getParameterName()),
                        HtmlUtils.htmlEscape(token.getToken()));
    }

    @PostMapping("/profile/name")
    public Map<String, String> updateProfile(
            @RequestParam String value) {
        if (value.isBlank() || value.length() > 80) {
            throw new IllegalArgumentException("Invalid display name");
        }

        displayName.set(value);
        return Map.of("displayName", displayName.get());
    }
}
~~~

- `/whoami` trả principal, `request.getScheme()`, `isSecure()`, host/port **mà Spring nhìn thấy** sau trusted forwarding. Để chứng minh TLS thật, test phải xác minh cert từ client.
- `/settings` có form POST chứa CSRF token của `CsrfFilter`; dùng `HtmlUtils.htmlEscape` khi render.
- `/profile/name` GET cho phép quan sát state; POST cần authenticated session và CSRF token. Nếu POST không token gây side effect, security configuration có lỗi.
- Production nên dùng template engine (Thymeleaf/JSP) với CSRF support, không tự render form bằng string, và áp dụng authorization theo user/tenant. `AtomicReference` toàn cục không phù hợp production.

## 7. Image và mạng container

`Dockerfile`:

~~~dockerfile
FROM gradle:8.10.2-jdk17 AS build
WORKDIR /workspace
COPY settings.gradle build.gradle ./
COPY src ./src
RUN gradle --no-daemon bootJar

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/*.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

`EXPOSE 8080` là metadata image, không publish host port. Production cần non-root, pinned image digest, scanning, limits, secrets management và monitoring.

`compose.yaml`:

~~~yaml
services:
  app:
    build: .
    expose:
      - "8080"
    networks:
      - private

  gateway:
    image: nginx:1.27-alpine
    depends_on:
      - app
    ports:
      - "127.0.0.1:8443:443"
      - "127.0.0.1:9443:4444"
    volumes:
      - "./nginx.conf:/etc/nginx/conf.d/default.conf:ro"
      - "./certs:/etc/nginx/certs:ro"
      - "./attacker:/usr/share/nginx/html/attacker:ro"
    networks:
      - private

networks:
  private:
    driver: bridge
~~~

App không có `ports` nên không có direct HTTP port công bố từ Compose. Các container khác trong cùng Docker network vẫn có thể gọi app; production phải phân tách network và giới hạn proxy trust. Hai public ports chỉ bind loopback của host. `depends_on` không đồng nghĩa health-ready; CI phải poll `/health` sau khi start.

## 8. Nginx TLS termination và bảo vệ Forwarded headers

`nginx.conf`:

~~~nginx
server {
    listen 443 ssl;
    server_name localhost;

    ssl_certificate     /etc/nginx/certs/localhost.pem;
    ssl_certificate_key /etc/nginx/certs/localhost-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    if ($host != "localhost") { return 421; }

    location / {
        proxy_pass http://app:8080;
        proxy_http_version 1.1;

        proxy_set_header Host "localhost:8443";
        proxy_set_header X-Forwarded-Proto "https";
        proxy_set_header X-Forwarded-Host "localhost:8443";
        proxy_set_header X-Forwarded-Port "8443";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header Connection "";
        proxy_redirect off;
    }
}

server {
    listen 4444 ssl;
    server_name 127.0.0.1;

    ssl_certificate     /etc/nginx/certs/localhost.pem;
    ssl_certificate_key /etc/nginx/certs/localhost-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        root /usr/share/nginx/html/attacker;
        try_files $uri =404;
    }
}
~~~

**Điểm trọng tâm:** Public port là `8443`, Nginx bên trong là `443`. Forwarding phải bảo toàn public `https://localhost:8443`, **không** sinh redirect `http://app:8080` hoặc sai port `443`. Nginx dùng các giá trị fixed trong lab, đè `X-Forwarded-Proto`/Host/Port và xóa `Forwarded` do client ngoài có thể tự khai. Tránh tin trực tiếp `$http_host` nếu chưa allowlist. Ở production nhiều virtual hosts, làm canonical host routing/trust boundary cụ thể.

Nếu edge Nginx chuyển TLS→HTTP nội bộ, bảo vệ upstream theo network policy/mTLS/segmentation phù hợp. **Cookie Secure không có nghĩa chặng upstream nội bộ luôn được mã hóa**.

## 9. Trang cross-site mô phỏng form POST

`attacker/attack.html`:

~~~html
<!doctype html>
<html lang="en">
<head><meta charset="UTF-8"><title>Local CSRF demonstration</title></head>
<body>
  <form method="post"
        action="https://localhost:8443/profile/name">
    <input type="hidden" name="value" value="FORGED">
    <button id="attack" type="submit">Send test POST</button>
  </form>
</body>
</html>
~~~

Test phải mở `https://127.0.0.1:9443/attack.html`. Đích của form là `https://localhost:8443/profile/name` — **khác site**. Cookie `SameSite=Lax` không được browser đính kèm vào một cross-site top-level POST điển hình; và `CsrfFilter` vẫn từ chối vì POST thiếu CSRF token. Hai lớp phòng vệ phải được test riêng, không coi SameSite là lý do tắt CSRF.

Đây là PoC an toàn chỉ gửi tới app của chính lab; không thử với dịch vụ ngoài quyền sở hữu.

## 10. Cấp chứng chỉ local và xác minh HTTPS

### 10.1. mkcert

Cài `mkcert` theo hướng dẫn OS, trên Linux/macOS:

~~~bash
mkdir -p certs
mkcert -install
mkcert -cert-file certs/localhost.pem \
       -key-file certs/localhost-key.pem \
       localhost 127.0.0.1 ::1
~~~

- `localhost.pem` là leaf cert có SAN cho hostname/IP của lab.
- `localhost-key.pem` chứa **private leaf key**, không commit/share.
- `$(mkcert -CAROOT)/rootCA.pem` là public CA certificate.
- `$(mkcert -CAROOT)/rootCA-key.pem` là **private CA key**, tuyệt đối không mang vào repo, container hoặc CI artifact.

`mkcert -install` có thể thêm CA vào trust store của OS, nhưng Playwright-managed browser và JDK/Node có thể dùng trust store khác. Test **phải** xác minh HTTPS thật ở chính client, không suy luận từ việc đã gọi `mkcert -install`.

### 10.2. Chạy Compose và dùng curl có CA verification

~~~bash
docker compose up --build -d

curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
     -i https://localhost:8443/health

curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
     -i https://127.0.0.1:9443/attack.html
~~~

`GET /health` dự kiến 200/`OK` khi app đã ready. Nếu mới start bị 502, dùng readiness polling hữu hạn và xem Docker logs, không tắt TLS. `curl -k` chỉ tắt certificate validation, không nên nằm trong bài test xác nhận.

Có thể kiểm tra TLS chain:

~~~bash
openssl s_client -connect localhost:8443 \
  -servername localhost \
  -CAfile "$(mkcert -CAROOT)/rootCA.pem" \
  -verify_return_error </dev/null
~~~

Khi cert/CA đúng, verify chain thành công và TLS protocol thuộc tập cho phép. Hostname SAN nên kiểm tra thêm qua curl/browser vì `openssl s_client` trên một số phiên bản không mặc định enforce hostname verification trừ khi được cấu hình.

### 10.3. Kiểm tra redirect và header spoofing

~~~bash
curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
  -i https://localhost:8443/whoami

curl --cacert "$(mkcert -CAROOT)/rootCA.pem" -i \
  -H 'Forwarded: proto=http;host=evil.invalid' \
  -H 'X-Forwarded-Proto: http' \
  -H 'X-Forwarded-Host: evil.invalid' \
  https://localhost:8443/whoami
~~~

Khi chưa login, Spring redirect tới login. Header `Location` có thể relative hoặc absolute, tùy redirect strategy. Nếu absolute, phải dùng **public HTTPS origin** đúng port. Không được có `evil.invalid` hay `http://app:8080`. Production cần kiểm thử nhiều host/virtual host và proxy chain, không chỉ ba headers này.

## 11. Java 17 HttpClient kiểm tra TLS/Set-Cookie (không log ID)

JDK `HttpClient` kết nối thật tới HTTPS và đọc raw `Set-Cookie`, nhưng **không** mô phỏng toàn bộ browser SameSite/navigation behavior.

File `HttpsCookieProbe.java`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Locale;

public final class HttpsCookieProbe {

    static boolean has(String cookie, String flag) {
        for (String part : cookie.split(";")) {
            if (part.trim().equalsIgnoreCase(flag)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://localhost:8443/login"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        List<String> headers =
                response.headers().allValues("set-cookie");

        String session = headers.stream()
                .filter(s -> s.startsWith("JSESSIONID="))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("Missing JSESSIONID"));

        System.out.println("HTTP: " + response.statusCode());
        System.out.println("TLS: "
                + response.sslSession().isPresent());
        System.out.println("Cookie: true");
        System.out.println("Secure: " + has(session, "Secure"));
        System.out.println("HttpOnly: " + has(session, "HttpOnly"));
        System.out.println("SameSite=Lax: "
                + has(session, "SameSite=Lax"));
        System.out.println("Host-only: "
                + !session.toLowerCase(Locale.ROOT)
                        .contains("; domain="));
    }
}
~~~

Chạy:

~~~bash
javac HttpsCookieProbe.java

# JVM có thể không tự tin CA local của OS; tạo truststore riêng
# bằng PUBLIC root certificate (không phải rootCA-key.pem).
keytool -importcert -noprompt \
  -alias lab-ca \
  -file "$(mkcert -CAROOT)/rootCA.pem" \
  -keystore certs/java-truststore.p12 \
  -storetype PKCS12 -storepass changeit

java -Djavax.net.ssl.trustStore=certs/java-truststore.p12 \
     -Djavax.net.ssl.trustStorePassword=changeit \
     HttpsCookieProbe
~~~

Kết quả kỳ vọng **nếu lab được cấu hình và certificate được JVM tin**:

~~~text
HTTP: 200
TLS: true
Cookie: true
Secure: true
HttpOnly: true
SameSite=Lax: true
Host-only: true
~~~

`changeit` chỉ là password truststore chứa public CA cho lab, không phải credential production. Không sửa JDK default cacerts hoặc tạo trust-all verifier để chạy test. `HttpClient` trong Java 17 không phải `AutoCloseable` dùng với try-with-resources. **Không in session ID** dù raw Set-Cookie có trong response.

Kết quả JDK probe chứng minh TLS và cookie attributes mà HTTP client nhìn thấy, **không** chứng minh browser chấp nhận/gửi cookie theo SameSite.

## 12. Playwright Chromium: cookie jar, session, CSRF và cross-site

### 12.1. Setup

`package.json`:

~~~json
{
  "private": true,
  "type": "module",
  "scripts": { "test:e2e": "playwright test" },
  "devDependencies": { "@playwright/test": "^1.56.1" }
}
~~~

~~~bash
npm install
npx playwright install chromium
~~~

`playwright.config.js`:

~~~javascript
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    baseURL: "https://localhost:8443",
    ignoreHTTPSErrors: false,
    trace: "retain-on-failure"
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } }
  ]
});
~~~

**Quan trọng:** Playwright-managed Chromium phải tin CA public của `mkcert`. Nếu không, setup đúng trust store của browser trên runner/OS. **Không đổi `ignoreHTTPSErrors` thành true** vì như vậy mất bằng chứng TLS hostname/chain verification. `trace` có thể chứa request metadata/cookie, chỉ dùng user/password lab và giới hạn người đọc.

### 12.2. Browser E2E đầy đủ

`e2e/session.spec.js`:

~~~javascript
import { test, expect } from "@playwright/test";

const BASE = "https://localhost:8443";
const ATTACK = "https://127.0.0.1:9443";

async function login(page) {
  const response = await page.goto(BASE + "/login");
  expect(response?.status()).toBe(200);
  await page.locator('input[name="username"]').fill("student");
  await page.locator('input[name="password"]').fill(
    "lab-password-123456");
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(BASE + "/whoami");
}

test("HTTPS cookie flags, public scheme, session rotation", async ({
  page, context
}) => {
  await page.goto(BASE + "/login");
  const before = (await context.cookies(BASE))
    .find(c => c.name === "JSESSIONID");
  expect(before).toBeDefined();

  await page.locator('input[name="username"]').fill("student");
  await page.locator('input[name="password"]').fill(
    "lab-password-123456");
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(BASE + "/whoami");

  const after = (await context.cookies(BASE))
    .find(c => c.name === "JSESSIONID");
  expect(after).toBeDefined();
  expect(after.secure).toBe(true);
  expect(after.httpOnly).toBe(true);
  expect(after.sameSite).toBe("Lax");
  expect(after.path).toBe("/");
  expect(after.value).not.toBe(before.value);

  const whoami = await page.evaluate(async () => {
    const r = await fetch("/whoami");
    return r.json();
  });
  expect(whoami.user).toBe("student");
  expect(whoami.scheme).toBe("https");
  expect(whoami.secure).toBe(true);
  expect(whoami.host).toBe("localhost");
  expect(whoami.port).toBe(8443);

  const readable = await page.evaluate(() => document.cookie);
  expect(readable).not.toContain("JSESSIONID=");

  const reqPromise = page.waitForRequest(r =>
    r.url() === BASE + "/whoami" && r.method() === "GET"
  );
  await page.reload();
  const request = await reqPromise;
  const headers = await request.allHeaders();
  expect(headers.cookie ?? "").toContain("JSESSIONID=");
});

test("POST missing CSRF cannot mutate; valid form can", async ({ page }) => {
  await login(page);
  await page.goto(BASE + "/settings");

  const before = await page.evaluate(async () => {
    const r = await fetch("/profile/name");
    return r.json();
  });

  const status = await page.evaluate(async () => {
    const r = await fetch("/profile/name", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ value: "FORGED" })
    });
    return r.status;
  });
  expect(status).toBe(403);

  const unchanged = await page.evaluate(async () => {
    const r = await fetch("/profile/name");
    return r.json();
  });
  expect(unchanged.displayName).toBe(before.displayName);

  await page.locator("#displayName").fill("Approved");
  await page.locator('button[type="submit"]').click();
  await expect(page.locator("body"))
    .toContainText('"displayName":"Approved"');
});

test("cross-site POST has no Lax session cookie", async ({
  page, context
}) => {
  await login(page);

  const foreign = await context.newPage();
  const html = await foreign.goto(ATTACK + "/attack.html");
  expect(html?.status()).toBe(200);

  const requestPromise = foreign.waitForRequest(r =>
    r.url() === BASE + "/profile/name" && r.method() === "POST"
  );
  const responsePromise = foreign.waitForResponse(r =>
    r.url() === BASE + "/profile/name" &&
    r.request().method() === "POST"
  );

  await foreign.locator("#attack").click();
  const forgedRequest = await requestPromise;
  const headers = await forgedRequest.allHeaders();
  expect(headers.cookie ?? "").not.toContain("JSESSIONID=");

  const forgedResponse = await responsePromise;
  expect(forgedResponse.status()).toBe(403);
});

test("logout POST with CSRF invalidates session", async ({ page }) => {
  await login(page);
  await page.goto(BASE + "/logout");
  await page.locator('form[action="/logout"] button').click();

  await expect(page).toHaveURL(/\/login\?logout/);
  await page.goto(BASE + "/whoami");
  await expect(page).toHaveURL(/\/login/);
});
~~~

**Bốn test xác minh:**
1. Browser thật lưu session cookie có flags mong đợi; session ID đổi sau login, JS không đọc được HttpOnly cookie, nhưng network request cùng origin **có gửi** JSESSIONID; backend nhìn thấy scheme/host/port public từ trusted forwarding.
2. Unsafe POST **có browser session** nhưng không CSRF token trả 403 và không đổi state; form render token đúng thì cập nhật được.
3. Cross-site top-level POST từ IP loopback tới hostname localhost **không gửi** `SameSite=Lax` cookie, đồng thời server CSRF từ chối request.
4. GET logout chỉ là confirmation, POST logout có token invalidate session; protected GET sau logout phải chuyển về login.

Nếu muốn đo SameSite, **không dùng** Playwright `context.request.post()` hoặc Java `CookieManager` vì các HTTP clients không mô phỏng đầy đủ browser site-for-cookies. Dùng `page`/`BrowserContext` và quan sát request thực từ network qua `request.allHeaders()`.

### 12.3. Chạy browser tests

~~~bash
npm run test:e2e

# Quan sát browser có giao diện khi điều tra:
npx playwright test --headed --project=chromium
~~~

**Kỳ vọng 4 test pass**, với điều kiện app/proxy/cert/trust/browser khớp lab. Đây là expected behavior, **không phải kết quả đã chạy được chứng nhận**. Nếu Playwright thất bại vì TLS, sửa CA/SAN/trust; nếu vì cookie/CSRF, kiểm tra DevTools network/Spring Security chain thay vì tắt bảo vệ. Nên thêm Firefox/WebKit và browser mobile đúng phạm vi sản phẩm.

## 13. Kiểm thử thêm bằng MockMvc: đúng tầng, không thay thế E2E

Một test Spring Boot với `MockMvc` kiểm tra logic `CsrfFilter`:

~~~java
// Mảnh test trong @SpringBootTest + @AutoConfigureMockMvc,
// có static imports MockMvcRequestBuilders.*, csrf(), status().
mvc.perform(post("/login")
        .param("username", "student")
        .param("password", "lab-password-123456"))
    .andExpect(status().isForbidden());

mvc.perform(post("/login")
        .with(csrf())
        .param("username", "student")
        .param("password", "lab-password-123456"))
    .andExpect(status().is3xxRedirection());
~~~

Điều này **không** mở TCP/TLS, không có cert SAN, không đi qua Nginx, không chứng minh browser đã nhận cookie hoặc `SameSite`. Dùng MockMvc cho filter/Provider; dùng Docker/proxy/curl để đo mạng và Playwright để đo browser.

## 14. Vấn đề reverse proxy và forwarded headers

Một request có ba scheme/host khác nhau:
1. **Browser public URL:** `https://localhost:8443`.
2. **Nginx upstream URL:** `http://app:8080`, chỉ trong private network.
3. **Spring logical request:** sau trusted forwarding nên là `https` + `localhost` + port `8443`.

Nếu Spring tạo redirect `http://app:8080/login`, lỗi thường ở `X-Forwarded-Proto`/Host/Port hoặc Boot forwarding strategy. Nếu header do attacker tự khai tạo `Location: https://evil.invalid`, đó là nguy cơ host header poisoning/open redirect. **Sửa tại ingress**: validate host allowlist, overwrite/strip Forwarded headers và không public backend. Đừng tin mọi forwarded hop của client.

**Khi có nhiều proxy:** phải định nghĩa rõ proxy nào được tin, header nào được ghi đè và các mức network trust. Với TLS termination trong một container và upstream HTTP, đánh giá mTLS/segmentation nếu chặng nội bộ đi qua ranh giới khác. Cookie Secure không tự mã hóa nội bộ.

## 15. Troubleshooting theo dấu hiệu quan sát

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Login đúng nhưng redirect login lại | Browser reject cookie, session store không khôi phục | Set-Cookie, browser jar, Cookie request sau |
| Cookie thiếu Secure | Boot session cookie config/proxy scheme | application.yml, forwarded proto |
| Cookie có nhưng không gửi | Path/Domain/SameSite/scheme/third-party policy | Browser DevTools cookie reason |
| JS không thấy JSESSIONID | **Đúng** nếu HttpOnly | Network headers, cookie jar |
| `Location` trỏ host/container nội bộ | Forwarded headers không đúng | curl public, Nginx config |
| Header `Forwarded` giả thay đổi redirect | Proxy đang trust client | Strip/overwrite, host allowlist |
| Browser HTTPS chỉ chạy khi ignore errors | Cert trust/SAN/scheme mismatch | Sửa certificate chain/trust |
| Curl pass nhưng Java PKIX error | JVM truststore thiếu CA | Import public CA vào truststore riêng |
| POST profile 403 dù có cookie | Thiếu/sai CSRF token | Hidden field/header token và rotation |
| POST logout 403 | CSRF token thiếu sau login | GET logout form, refresh token đúng |
| Cookie cross-site “vẫn đi” khi chỉ đổi port | Hai origin khác nhưng cùng site | Đổi host/site thật |
| App A đăng nhập, app B mất phiên | Không shared sessions | Redis/JDBC Spring Session hoặc sticky LB |
| MockMvc pass nhưng browser reject | Test chưa đi qua cookie/TLS policies | Playwright E2E và browser matrix |
| Health 200 nhưng login lỗi | Health không tạo session | Test login/cookie/CSRF/redirect thực |
| Một browser pass, browser khác fail | Cookie privacy/CA trust khác nhau | Firefox/WebKit/Safari matrix |

Đừng chẩn đoán vấn đề bằng cách in toàn bộ request headers: `Cookie`, `Authorization`, password và CSRF token phải được redacted. Log request ID, route, status, lỗi được phân loại và upstream timing, không cần bearer credentials.

### 15.1. Phân biệt lỗi cookie và lỗi session

- **Set-Cookie có, browser jar không có:** khả năng bị browser từ chối do thuộc tính/trust/privacy.
- **Browser jar có, request không mang Cookie:** scope/Path/SameSite/scheme/third-party rules.
- **Request có Cookie, server không có principal:** session expired/revoked, store không chia sẻ, session ID sai, proxy routing.
- **Request có Cookie/principal nhưng POST 403:** nhiều khả năng CSRF/authorization, không nhất thiết là cookie hỏng.
- **Login 200 và phát cookie nhưng `/whoami` 302:** không chứng minh session bền vững; cần kiểm tra lần request sau trong cùng context.

## 16. Kiểm thử load balancer và session nhiều node

Lab một app instance dùng session memory. Production có nhiều app pods sẽ phát sinh:

~~~text
POST /login -> LB -> app-A giữ session S
GET /profile -> LB -> app-B không tìm thấy S
=> dù browser gửi cookie, app-B coi chưa đăng nhập
~~~

Phương án: sticky sessions (có giới hạn khi pod chết) hoặc **shared session repository** bằng Spring Session Redis/JDBC theo kiến trúc được quản trị.

Các test cần thêm:
1. Login ở node A; yêu cầu sau bị route sang B, principal vẫn đúng.
2. Scale/rolling restart, pod drain và reconnect; session không mất ngoài policy.
3. Logout ở B invalidate session mà A cũng không chấp nhận nữa.
4. Session TTL/idle timeout/absolute timeout đúng trên shared store, kể cả clock skew.
5. Session fixation rotation sau login hoạt động xuyên node, ID cũ không được tái dùng.
6. Cookie Domain/Path/SameSite/Secure đồng nhất trên mọi ingress/instance.
7. Account disabled/logout-all-sessions propagate theo SLA; token còn hiệu lực phải có strategy revoke.
8. DB/Redis outage không biến authentication thành **fail open**.

Không tuyên bố Compose một node đã test failover production. Multi-node/session persistence cần môi trường staging và datastore thật hoặc gần production.

## 17. SameSite, CSRF, CORS và SSO là các lớp riêng

- **SameSite:** quyết định lúc nào browser gửi cookie theo site; explicit Lax không thay CSRF trên same-site subdomains và GET có side effects.
- **CSRF:** server kiểm tra token cho unsafe methods với browser-auto-sent credentials; Spring Security mặc định bảo vệ POST login/logout.
- **CORS:** điều khiển browser cross-origin JS đọc response và preflight; HTML form có thể gửi POST dù JS không đọc response.
- **HttpOnly:** JS không đọc được cookie, browser vẫn gửi; không chống CSRF.
- **Secure:** cookie đi theo secure transport; không bảo đảm TLS từ proxy tới backend.
- **XSS:** script chạy cùng origin có thể gửi token CSRF hợp lệ; cần CSP, output encoding và review.
- **OAuth2/OIDC/SAML:** callback/redirect dùng state, nonce, issuer/audience/signature, CSRF/correlation riêng; SameSite của session/callback cookie cần được kiểm thử đúng browser/protocol, không nới `None` hoặc tắt CSRF toàn site bừa bãi.
- **Bearer-only API:** nếu chỉ accept Authorization header do client tự gắn, không có cookie/Basic auto-sent, CSRF threat model khác. JWT trong cookie **vẫn** có CSRF risk.

Thực tế còn có partitioned cookies, third-party cookie blocking, Storage Access API và mobile webviews. Không suy rằng một Chromium test đại diện tất cả browser.

## 18. CI workflow và báo cáo kiểm thử

Một chuỗi CI hợp lý:
1. JUnit/MockMvc tests, static analysis và dependency checks.
2. Sinh local test cert/CA và đảm bảo public CA được browser/JDK tin.
3. Build Docker images, start Nginx/app trong private network.
4. Poll `GET /health` bằng curl có `--cacert` và timeout hữu hạn; không dùng `-k`.
5. Run Playwright Chromium/Firefox/WebKit theo browser support.
6. Assert TLS trust, Secure/HttpOnly/SameSite, browser cookie send, CSRF/POST, logout và redirects.
7. Thu logs/traces đã redact và hạn retention; tuyệt đối không upload CA private key, real session cookie/password.
8. Cleanup container, volumes, test cert/private keys và browser contexts, kể cả khi job thất bại.
9. Với production nhiều replicas, chạy thêm session failover/sticky/Redis JDBC tests.

Shell skeleton:

~~~bash
set -eu
docker compose up --build -d

# CI thật cần readiness polling/timeout và cleanup finally/trap.
curl --cacert "$(mkcert -CAROOT)/rootCA.pem" \
  --fail https://localhost:8443/health

npm run test:e2e
docker compose down --volumes
~~~

**Không xem đây là CI script hoàn chỉnh**: nếu test lỗi, `set -e` dừng trước cleanup, nên pipeline thực dùng `trap/finally`. Thời gian boot không cố định, nên curl đơn lẻ có thể chạy trước khi app healthy.

Trong báo cáo QA, phân biệt: **code đã soạn**, **đã biên dịch**, **Docker đã chạy**, **TLS verify đã pass**, **browser tests thực sự pass**, **multi-node/staging đã test**. Không tuyên bố lệnh đã chạy nếu chưa có log.

## 19. Test matrix trước khi phát hành

| ID | Hành vi | Expected |
| --- | --- | --- |
| TLS-01 | Valid cert, SAN, CA chain | Browser/curl HTTPS không bypass |
| TLS-02 | Untrusted/wrong-host cert | Handshake/hostname verification fail |
| PROXY-01 | Trusted forwarding | Backend nhận scheme=https, host=localhost, port=8443 |
| PROXY-02 | Header injection | Không xuất redirect evil.invalid |
| PROXY-03 | Backend private | Không có direct HTTP port public ngoài ý muốn |
| COOKIE-01 | Session Set-Cookie | Secure; HttpOnly; SameSite=Lax; Path=/, không Domain |
| COOKIE-02 | Browser accepted cookie | `context.cookies()` có session với đúng flags |
| COOKIE-03 | Same-origin HTTPS next request | Browser gửi Cookie và được xác thực |
| COOKIE-04 | HttpOnly | `document.cookie` không lộ session ID |
| COOKIE-05 | Cross-site POST | SameSite Lax cookie không đi với form POST |
| LOGIN-01 | Password đúng | Principal đúng, session còn ở request sau |
| LOGIN-02 | Password sai | Không authenticated session |
| LOGIN-03 | Session fixation | Session ID thay sau login |
| CSRF-01 | POST thiếu token | 403, không side effect |
| CSRF-02 | POST có token | Thành công khi đã authenticated |
| LOGOUT-01 | GET logout | Không có side effect |
| LOGOUT-02 | POST logout + token | Session invalid, protected GET redirect login |
| HA-01 | Failover app node | Session chia sẻ/route đúng theo policy |
| HA-02 | Logout nhiều node | Session cũ không được dùng lại |
| OBS-01 | Logs/test artifacts | Không lộ credentials/session/CA private key |
| UA-01 | Chrome/Firefox/Safari | Browser support matrix được kiểm chứng |

## 20. Lỗi thường gặp

1. “MockMvc `.secure(true)` = TLS thật.” **Sai**: không có handshake.
2. “`curl -k` là test HTTPS đạt yêu cầu.” **Sai**: vô hiệu cert validation.
3. “Server phát Set-Cookie nghĩa browser lưu rồi.” **Sai**: browser có thể reject.
4. “Secure cookie không thể được gửi HTTP localhost.” **Không luôn đúng** vì localhost exception.
5. “HttpOnly ngăn CSRF.” **Sai**: browser vẫn tự gửi.
6. “Đổi port là đổi site.” **Sai**: port làm khác origin, không nhất thiết khác site.
7. “CORS block đọc response nên form POST không tới server.” **Sai**.
8. “Proxy public HTTPS nghĩa backend tự biết request secure.” **Không chắc**.
9. “Có Secure nghĩa proxy→backend cũng được TLS.” **Sai**.
10. “Tin client X-Forwarded-Proto là an toàn.” **Sai**: host/proto spoofing.
11. “Cho phép backend 8080 public để debug không ảnh hưởng.” **Nguy hiểm**: bypass proxy/TLS.
12. “JSESSIONID Domain rộng sẽ tiện hơn luôn.” **Có rủi ro subdomain takeover/tossing**.
13. “Cookie không thấy trong document.cookie là user chưa login.” **Sai** với HttpOnly.
14. “Java CookieManager giống Chrome SameSite.” **Sai**.
15. “HTTP 200 sau login đủ.” **Sai**: cần request tiếp theo.
16. “Logout thành công ở một pod đã thu hồi ở mọi pod.” **Chưa chắc**.
17. “Cần tắt CSRF khi browser test bị 403.” **Sai**.
18. “Chỉ cần health 200.” **Sai**: health không kiểm tra cookie/login.
19. “Một test Chromium đại diện mọi browser.” **Sai**.
20. “Trace session test không nhạy cảm.” **Sai**: trace/storage state có thể chứa secrets.
21. “Dùng CA local cho production.” **Sai**: chỉ cho lab, cần production CA lifecycle.
22. “`forward-headers-strategy=framework` bảo đảm trust.” **Sai**: ingress phải overwrite/strip.
23. “Test cùng localhost khác port chứng minh SameSite.” **Sai**: cùng site.
24. “JWT trong cookie không có CSRF.” **Sai**: browser tự gửi cookie.
25. “Không cần session store chung vì Kubernetes tự đồng bộ memory.” **Sai**.

## 21. Câu hỏi tự kiểm tra

**1.** GET `/login` trả `Set-Cookie` nhưng browser không giữ. Cần xem gì?  
**Trả lời:** browser DevTools cookie rejection reason, Domain/Path/SameSite/Secure/trust, không chỉ server log.

**2.** Backend request scheme là HTTP sau Nginx HTTPS. Vì sao?  
Kiểm tra X-Forwarded-Proto/Host/Port, Boot forwarding strategy, ingress trust; phải đo TLS ở browser **và** scheme logic ở app.

**3.** Tại sao Java HttpClient không thể khẳng định Chrome sẽ bỏ SameSite=Lax cookie trong cross-site POST?  
Vì nó không có browser site-for-cookies/navigation/privacy model.

**4.** Test ở `localhost:8443` và `localhost:9443` chứng minh khác site?  
**Không**; khác origin theo port, thường cùng site.

**5.** `HttpOnly` khiến `document.cookie` trống. User có thể vẫn authenticated?  
**Có**. Browser vẫn đính kèm cookie trong HTTP request; phải kiểm tra network headers/principal.

**6.** POST profile có cookie và nhận 403. Có nên tắt CSRF?  
**Không**. Kiểm tra token/CSRF repository và flow, vì bị chặn có thể là đúng.

**7.** Playwright chạy được khi `ignoreHTTPSErrors=true`; có thể dùng để chứng minh TLS an toàn?  
**Không**. Phải sửa CA trust/host SAN và chạy validation thật.

**8.** User đã login ở app A, load balancer chuyển sang B thì mất session, fix sao?  
Dùng session repository chung hoặc sticky session phù hợp, test failover/logout/TTL và không fail-open.

### Checklist vận hành

- [ ] Browser public HTTPS đúng SAN/trust chain, không bypass validation.
- [ ] Backend private, proxy overwrite trusted forwarding headers, không redirect host nội bộ.
- [ ] Cookie session Secure, HttpOnly, SameSite, Path, Domain đúng scope.
- [ ] Browser thật nhận/gửi cookie và có principal đúng ở request tiếp.
- [ ] Session ID đổi khi login, invalid khi logout.
- [ ] POST login/logout/profile kiểm tra CSRF; GET logout không thực hiện logout.
- [ ] SameSite test từ **site khác thật**, không chỉ port khác.
- [ ] Mọi log/trace đã che Cookie/Set-Cookie/password/session tokens.
- [ ] Test JVM/browser truststore riêng khi CA local.
- [ ] CI cleanup khi lỗi, test browser compatibility và session HA theo production.

## 22. Tài liệu tham khảo

- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): session cookie/SameSite properties.
- [Spring Boot 3.3 — Running Behind a Front-end Proxy Server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): forward headers strategy và redirect.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF token, login/logout, SPA token lifecycle.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation và server sessions.
- [Spring Security 6.5 — Handling Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET confirmation, POST logout, invalidation.
- [Playwright — BrowserContext](https://playwright.dev/docs/api/class-browsercontext): cookie jar và request observation.
- [Playwright — Test options](https://playwright.dev/docs/test-use-options): TLS error handling.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure/HttpOnly/SameSite/domain/localhost rules.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie and session security.
- [OWASP WSTG — Exposed Session Variables](https://wstg.owasp.org/stable/4-Web_Application_Security_Testing/06-Session_Management_Testing/04-Testing_for_Exposed_Session_Variables/): session transport/headers.
- [mkcert — Local CA for development](https://github.com/FiloSottile/mkcert): SAN, trusted local certificates.
- [Docker Compose file reference](https://docs.docker.com/compose/compose-file/): network/port/service declarations.

**Kết luận:** Đăng nhập đúng trong Java chưa chứng minh session an toàn khi qua reverse proxy và trình duyệt. Kiểm thử cần đi qua **TLS có kiểm tra CA/hostname**, **container network/proxy forwarding đúng**, **browser cookie jar và network thực**, cùng CSRF/logout/session fixation. `MockMvc`, `curl`, JDK `HttpClient` và Playwright là những phép đo **bổ sung**, không thay thế lẫn nhau.