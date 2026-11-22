# Chuyển hướng HTTP sang HTTPS và nhận diện giao thức sau reverse proxy — Spring Security WebFlux

## Mục tiêu

Sau bài học, người học có thể:

1. Giải thích vì sao mã hóa TLS, chuyển hướng HTTP → HTTPS và nhận diện giao thức sau reverse proxy là ba vấn đề liên quan nhưng **khác nhau**.
2. Bật `ServerHttpSecurity.redirectToHttps(Customizer.withDefaults())` trong `SecurityWebFilterChain`, hiểu vai trò `HttpsRedirectWebFilter` và `Location`.
3. Giải thích vì sao browser truy cập HTTPS nhưng Spring Boot vẫn nhìn thấy HTTP khi TLS kết thúc tại proxy, dẫn đến redirect loop hoặc URL tuyệt đối sai.
4. Dùng `Forwarded` (RFC 7239), `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port` và `server.forward-headers-strategy: framework` để WebFlux khôi phục scheme/host/port public.
5. Hiểu sự khác biệt giữa `none`, `native`, `framework` và `ForwardedHeaderTransformer`; **không tin header client tự gửi**.
6. Kết hợp proxy TLS termination, kiểm soát trusted network, HSTS, cookie Secure, callback URL và các phép kiểm tra HTTPS đầy đủ.
7. Chạy ví dụ Java 17+ / Spring Boot 3.5 / Spring Security 6.5, kiểm chứng HTTP redirect, HTTPS forwarded, 401/403/200, HSTS và request scheme qua `WebTestClient`.

> Bài này thuộc **Spring Security reactive (WebFlux)**. Mã dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerWebExchange` và Spring WebFlux. Các API Servlet như `HttpSecurity`, `ForwardedHeaderFilter`, `RemoteIpValve` và `HttpServletRequest` không phải giải pháp trực tiếp cho Reactor Netty.

## 1. Sơ đồ vấn đề: browser HTTPS, backend HTTP

Triển khai phổ biến:

```text
Browser                   Reverse proxy / Load balancer            Spring WebFlux
    |                                 |                                   |
    | HTTPS app.example.test          |                                   |
    |-------------------------------->|                                   |
    |       TLS termination           |                                   |
    |                                 | HTTP 127.0.0.1:8080              |
    |                                 |---------------------------------->|
    |                                 | X-Forwarded-Proto: https          |
    |                                 | X-Forwarded-Host: app.example.test |
    |                                 | X-Forwarded-Port: 443            |
    |                                 |                                   |
    |<--------------------------------|<----------------------------------|
    | HTTPS response                  | HTTP internal response            |
```

Browser đã có kết nối mã hóa với reverse proxy. Nhưng trên socket giữa proxy và Netty, ứng dụng có thể thấy `http://127.0.0.1:8080/...`. Nếu không xử lý metadata của request gốc, ứng dụng sẽ:

- Nhận `exchange.getRequest().getURI().getScheme() == "http"` dù client bên ngoài đã truy cập HTTPS.
- Trả `Location: https://...` cho **cùng request** sau khi proxy kết thúc TLS, gây vòng lặp redirect.
- Sinh URL tuyệt đối, OAuth2 redirect URI, password-reset link hoặc cookie configuration theo hostname/port/scheme nội bộ.
- Không nhận ra secure request để áp HSTS hoặc những hành vi phụ thuộc scheme.

Khi proxy chuyển tiếp **metadata đáng tin**, Spring có thể nhìn URI client-facing như `https://app.example.test/account` dù TCP hop cuối là HTTP. Tuy nhiên, việc sửa URI trong request **không mã hóa hop nội bộ**. Tầng mạng nội bộ vẫn cần firewall, segmentation, hoặc TLS/mTLS khi phù hợp.

### Phân biệt ba chức năng

| Chức năng | Kết quả | Không tự giải quyết |
| --- | --- | --- |
| HTTPS/TLS | Mã hóa và xác thực đường truyền tới điểm TLS | Không báo tự động original scheme cho backend HTTP |
| Redirect HTTP → HTTPS | Trả HTTP 3xx + `Location: https://...` | Không mã hóa request HTTP đầu tiên |
| Forwarded headers | Cho Spring biết original scheme/host/port | Không bảo vệ header khỏi bị client giả nếu proxy/network sai |
| HSTS | Dặn browser ưu tiên HTTPS ở những lần truy cập sau | Không thay chứng chỉ TLS hay trusted proxy |
| Cookie Secure | Giới hạn cookie gửi qua kênh HTTPS trong browser | Không thay CSRF, authn, authz |

Tư duy đúng: **HTTPS được thiết lập ở edge**, **HTTP được chuyển sang HTTPS càng sớm càng tốt**, còn **Spring cần biết external scheme đáng tin** để không redirect sai và không sinh URL sai.

## 2. Cấu hình redirectToHttps trong Spring Security reactive

Ở Spring Security 6.5, DSL khuyến nghị:

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
            .redirectToHttps(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Đoạn trên là **fragment** trong class cấu hình, cần import `Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `Customizer`. Đoạn runnable đầy đủ xuất hiện ở phần thực hành.

Khi bật `redirectToHttps`:

- Spring Security thêm `HttpsRedirectWebFilter`, kiểm tra URI/scheme mà WebFlux nhìn thấy.
- Nếu request không phải HTTPS, filter tạo redirect sang URL HTTPS tương đương (cổng và đường dẫn theo mapping cụ thể).
- Nếu request được xác định là HTTPS, filter cho đi tiếp để các bước authentication/authorization/controller xử lý.
- Redirect không đồng nghĩa user đã đăng nhập; actual request sau redirect vẫn cần authentication và authorization.
- Mã response redirect mặc định phụ thuộc implementation/version; kiểm thử nên khẳng định **3xx và Location có scheme https** khi không có yêu cầu chặt hơn, thay vì hứa một con số 301/302 duy nhất.

Dạng gọi `http.redirectToHttps()` không đối số đã bị đánh dấu deprecated trong Spring Security 6.5. Dùng `redirectToHttps(Customizer.withDefaults())` để phù hợp API hiện hành trong baseline này.

### Vị trí trong filter chain

`HttpsRedirectWebFilter` thực hiện điều hướng trước khi cho request HTTP đi sâu vào phần còn lại của luồng bảo vệ. Tuy nhiên, các cấu hình nhiều `SecurityWebFilterChain`, security matcher hoặc custom filter có thể thay đổi đường xử lý. Hãy test **từng route thực tế** chứ không suy luận rằng có một bean security nghĩa là mọi URL đều được redirect.

### HTTPS redirect không cứu được request HTTP đầu tiên

Nếu người dùng gửi form login trên HTTP, thông tin đăng nhập **đã đi qua HTTP** trước khi server trả redirect. Nếu attacker có thể chặn/hạ cấp request HTTP đầu tiên, redirect đến HTTPS không loại bỏ được nguy cơ đó. Vì vậy:

- Mọi đường dẫn, form action và API URL phải ưu tiên HTTPS ngay từ đầu.
- Proxy ở edge nên chuyển HTTP GET sang HTTPS sớm, không phục vụ thao tác nhạy cảm trên cổng 80.
- Dùng HSTS trên HTTPS domain sau khi đã kiểm soát các subdomain liên quan.
- Không đưa password, JWT hoặc cookie session vào request HTTP public rồi hy vọng redirect làm request an toàn.

## 3. Tại sao redirect loop sau proxy?

Một vòng lặp điển hình:

```text
Browser GET https://app.example.test/settings
          |
          v
Proxy nhận HTTPS; gọi backend qua HTTP
          |
          v
Spring chưa xử lý X-Forwarded-Proto
-> perceived scheme=http
          |
          v
HttpsRedirectWebFilter -> 3xx Location=https://app.example.test/settings
          |
          v
Browser gọi lại chính HTTPS URL
          |
          +--> Proxy lại forward HTTP ... lặp
```

Lỗi browser thường hiển thị `ERR_TOO_MANY_REDIRECTS`. Có thể cũng thấy redirect từ `https://public` sang `https://internal-host:8080`, hoặc OAuth2 provider báo callback URI không khớp.

Khi proxy set và sanitize `X-Forwarded-Proto: https`, Spring dùng `ForwardedHeaderTransformer` thì:

```text
Browser HTTPS
  -> trusted proxy (TLS termination)
  -> backend HTTP + forwarded HTTPS metadata
  -> WebFlux khôi phục URI external với scheme=https
  -> HttpsRedirectWebFilter thấy HTTPS: KHÔNG redirect
  -> authentication + authorization + controller xử lý bình thường
```

Chìa khóa là **khôi phục perceived scheme trước security redirect**; không phải vô hiệu hóa security hoặc tin một header bất kỳ.

## 4. Forwarded (RFC 7239) và X-Forwarded-*

### 4.1. Header chuẩn

```http
Forwarded: for=192.0.2.123;proto=https;host=app.example.test
```

Các thuộc tính:

- `for`: địa chỉ client/hop theo convention và topology.
- `proto`: original scheme khi proxy nhận request.
- `host`: external host public.

Có thể có nhiều proxy và nhiều phần tử Forwarded; không tự lấy giá trị đầu tiên rồi tin tuyệt đối. Proxy chain cần có policy rõ về hop tin cậy và cách normalize.

### 4.2. Các header thực tế thường gặp

```http
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.test
X-Forwarded-Port: 443
X-Forwarded-For: 192.0.2.123
```

| Header | Thông tin | Rủi ro khi bị giả |
| --- | --- | --- |
| `X-Forwarded-Proto` | Scheme public | Lách HTTPS redirect hoặc ảnh hưởng Secure/HSTS handling |
| `X-Forwarded-Host` | Host public | URL tuyệt đối/Location trỏ tới host attacker hoặc host sai |
| `X-Forwarded-Port` | Port public | URL chứa port sai hoặc lộ port nội bộ |
| `X-Forwarded-For` | IP client qua proxy chain | IP allowlist, rate limiting, log sai nếu nguồn chưa được tin |
| `X-Forwarded-Prefix` | Context path/prefix public | Đường dẫn callback hoặc link sai |
| `Forwarded` | Metadata chuẩn hóa nhiều thành phần | Xung đột với X-Forwarded-* hoặc spoofing |

Với external `https://app.example.test/path` đi qua backend `http://127.0.0.1:8080/path`, sau transform dự kiến:

```text
Trước khi xử lý header:
  scheme=http, host=127.0.0.1, port=8080

Sau khi xử lý metadata của trusted proxy:
  scheme=https, host=app.example.test, port=443
```

Cổng HTTPS chuẩn 443 thường không hiện khi URI được biểu diễn lại. Chính controller, redirect URL builder, HSTS và các cơ chế phụ thuộc secure request hưởng lợi từ URI đã được chuẩn hóa.

### Vì sao không tự parse raw header trong controller?

Không nên viết:

```java
// Anti-pattern nếu header không được trusted proxy sanitize:
String scheme = exchange.getRequest().getHeaders()
        .getFirst("X-Forwarded-Proto");
boolean secure = "https".equalsIgnoreCase(scheme);
```

Dữ liệu này có thể do client ngoài tự tạo. Sau khi `ForwardedHeaderTransformer` chạy, header có thể đã bị loại khỏi downstream request. Cách đúng là để framework chuẩn hóa `ServerHttpRequest` ở ranh giới được cấu hình và để security xử lý scheme của URI, còn firewall/proxy bảo đảm nguồn metadata đáng tin.

## 5. server.forward-headers-strategy trong Spring Boot 3.5

Boot cung cấp property:

```yaml
server:
  forward-headers-strategy: framework
```

| Giá trị | Cơ chế | Khi chọn |
| --- | --- | --- |
| `none` | Boot không tiêu thụ forwarded headers để hiệu chỉnh URI | App có TLS trực tiếp hoặc giải pháp riêng |
| `native` | Embedded HTTP server xử lý theo hỗ trợ riêng (Netty/Tomcat/Jetty...) | Khi đã xác minh native handling đáp ứng header/topology |
| `framework` | Spring Framework xử lý; với WebFlux là `ForwardedHeaderTransformer` | Khi cần khôi phục external scheme/host/port bằng cơ chế của WebFlux |

Tài liệu Spring Boot 3.5 giải thích default có thể là `native` ở một số môi trường cloud được hỗ trợ, còn các môi trường khác thường `none`. Không dựa vào default khi cấu hình TLS termination; hãy khai báo rõ và kiểm thử tại runtime.

### ForwardedHeaderTransformer nằm ở đâu?

Ở WebFlux, `org.springframework.web.server.adapter.ForwardedHeaderTransformer` xử lý request **trước security WebFilters**:

1. Đọc các header forwarded từ request.
2. Khôi phục request URI/host/port theo thông tin forwarded.
3. Bỏ forwarded headers khỏi request đi sâu vào pipeline để giảm tác động lập lại hoặc bị dùng sai.
4. Cho `HttpsRedirectWebFilter` và những thành phần khác nhìn scheme chính xác từ client-facing request.

Khác với `ForwardedHeaderFilter` của Servlet. Trong Boot WebFlux, `server.forward-headers-strategy=framework` cho phép integration phù hợp; không cần đồng thời đăng ký các filter/transformer thủ công khác để "bù" cho thuộc tính đó.

### Khi không có proxy đáng tin: removeOnly

Spring Framework hỗ trợ `ForwardedHeaderTransformer#setRemoveOnly(true)` để **xóa** forwarded headers mà không dùng chúng:

```java
// Fragment thay thế trong Spring @Configuration.
// Không đăng ký cạnh một transformer khác đang hoạt động.
@Bean(name = "forwardedHeaderTransformer")
ForwardedHeaderTransformer forwardedHeaderTransformer() {
    ForwardedHeaderTransformer transformer =
            new ForwardedHeaderTransformer();
    transformer.setRemoveOnly(true);
    return transformer;
}
```

Cần import `org.springframework.web.server.adapter.ForwardedHeaderTransformer` và `org.springframework.context.annotation.Bean`. Đây là phương án khi **không** có trust boundary phù hợp, không phải cấu hình cùng lúc với strategy framework tin header. Khi removeOnly, Spring **không thể suy ra external HTTPS** từ những header đã bị bỏ.

## 6. Trusted proxy là ranh giới bảo mật bắt buộc

Bật `framework` trên app có cổng backend public mà **không** giới hạn ai gửi headers có thể tạo lỗ hổng. Một request trực tiếp HTTP với `X-Forwarded-Proto: https` có thể làm app tưởng HTTP là HTTPS. Header `X-Forwarded-Host: malicious.invalid` có thể khiến code tạo URL tuyệt đối hoặc redirect sai host.

**Ba yêu cầu không được thiếu:**

1. **Network isolation:** backend chỉ cho reverse proxy/load balancer/workload hợp lệ kết nối. Mô hình một host có thể dùng `server.address=127.0.0.1`; môi trường container cần security group, private listener, network policy hoặc mTLS thích hợp.
2. **Header normalization tại edge:** xóa các header `Forwarded` và `X-Forwarded-*` từ client ngoài, sau đó viết bộ header mới từ connection mà proxy thật sự quan sát. Không dùng raw `$http_x_forwarded_proto` do client tự chọn.
3. **Host/protocol allowlist:** proxy chỉ phục vụ các virtual host được cấp phép, không phản chiếu tùy ý Host hoặc Forwarded-Host; ứng dụng nên có public base URL đáng tin cho link nhạy cảm.

Với nhiều reverse proxy (CDN → LB → Gateway → Spring), cần xác định hop nào được tin và nơi nào xóa/append headers. Đừng tin "X-Forwarded-For đầu tiên" nếu client bên ngoài có thể ghi header đó.

### Ví dụ minh họa hành vi nguy hiểm (chỉ phân tích)

```http
GET /api/public HTTP/1.1
Host: backend.example.test:8080
X-Forwarded-Proto: https
X-Forwarded-Host: malicious.invalid
X-Forwarded-Port: 443
```

Nếu backend public tin các header này, perceived request có thể là HTTPS trên host sai dù TCP thật là HTTP. Vì thế **không** coi một unit test mô phỏng XFP=https là bằng chứng production an toàn. Test mô phỏng giúp chứng minh framework parse header; firewall và proxy sanitation phải được kiểm tra riêng.

### Hậu quả khi cấu hình sai

| Hạ tầng sai | Hậu quả |
| --- | --- |
| Proxy không ghi X-Forwarded-Proto | Redirect loop dù browser đang HTTPS |
| Backend public tin client XFP=https | Có thể bỏ qua redirect cho HTTP thật |
| Proxy giữ X-Forwarded-Host của client | Open redirect, link poisoning hoặc callback URL sai |
| Proxy giữ RFC Forwarded nhưng sửa XFP | Hai nguồn metadata mâu thuẫn |
| Proxy dùng Host nội bộ cho backend | Absolute Location/links trỏ sai |
| Proxy trust mọi nguồn X-Forwarded-For | Client IP log/rate limiting sai |
| Đặt `framework` nhưng không kiểm soát network | Mở ranh giới tin cậy ra Internet |

## 7. Ví dụ Nginx TLS termination

Giả sử:

- Browser truy cập `https://app.example.test`.
- Nginx chạy trên cùng máy với Spring Boot, có certificate TLS tin cậy cho domain thật.
- Spring Boot chạy HTTP trên `127.0.0.1:8080`, không expose cổng này ra Internet.
- Nginx là edge duy nhất, không nằm sau proxy khác. Với topology khác phải sửa cấu hình IP/trusted hops.

Cấu hình Nginx minh họa:

```nginx
server {
    listen 80;
    server_name app.example.test;

    return 308 https://app.example.test$request_uri;
}

server {
    listen 443 ssl;
    server_name app.example.test;

    ssl_certificate     /etc/ssl/certs/app.example.test.crt;
    ssl_certificate_key /etc/ssl/private/app.example.test.key;

    location / {
        proxy_pass http://127.0.0.1:8080;

        # Host public được allowlist, không phản chiếu Host tùy ý.
        proxy_set_header Host app.example.test;

        # Loại bỏ header RFC Forwarded do client gửi.
        proxy_set_header Forwarded "";

        # Ghi đè metadata X-Forwarded bằng sự thật tại edge.
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host app.example.test;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $remote_addr;

        # Không giữ các metadata tùy ý ngoài nhu cầu của demo.
        proxy_set_header X-Forwarded-Prefix "";
        proxy_set_header X-Forwarded-Ssl "";
    }
}
```

Các đường dẫn certificate chỉ minh họa; khi triển khai phải cung cấp cert/key thật và policy TLS phù hợp. Trong Nginx, giá trị rỗng của `proxy_set_header` có ý nghĩa không chuyển tiếp header đó. Bên ngoài cần một default server từ chối hostname không nằm trong `server_name` đã duyệt. Mô hình này dùng host cố định vì chỉ có một hostname; hệ thống đa tenant/vhost cần thiết kế riêng.

**Nginx 80 → HTTPS** bảo vệ client HTTP ở edge; **Spring redirectToHttps** là lớp bổ sung khi request vẫn được xem là HTTP. Khi browser đã đi qua Nginx HTTPS, forwarded scheme=https làm Spring không redirect thêm.

**Không dùng `$proxy_add_x_forwarded_for` một cách máy móc khi proxy ở edge nhận X-Forwarded-For không tin cậy**, vì cách append có thể giữ header attacker. Với nhiều trusted hops, xác định cấu hình real-IP/trusted proxies và chính sách append/replace phù hợp.

## 8. Dự án Spring Boot 3.5 WebFlux chạy được

Ví dụ gồm:

- Spring Boot + WebFlux/Spring Security, Java 17.
- HTTPS redirect mặc định.
- Forwarded strategy `framework`.
- API public cho thấy URI mà Spring nhận sau transformation.
- API private yêu cầu HTTP Basic và API admin cần role ADMIN.
- WebTestClient chạy embedded Netty thực trên loopback, kiểm chứng HTTP direct và forwarded HTTPS.

**Cấu trúc file:**

```text
https-proxy-demo/
  settings.gradle
  build.gradle
  src/main/java/example/httpsproxy/
    HttpsProxyApplication.java
    SecurityConfiguration.java
    ApiController.java
  src/main/resources/
    application.yml
  src/test/java/example/httpsproxy/
    HttpsProxyIntegrationTest.java
```

### 8.1. Gradle

**`settings.gradle`**:

```groovy
rootProject.name = 'https-proxy-demo'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot 3.5.7 là release cụ thể để ví dụ có baseline ổn định, không phải khuyến nghị giữ nguyên patch cũ khi production cần nâng cấp bảo mật. Dự án yêu cầu JDK 17+ và Gradle tương thích. Đừng thêm `spring-boot-starter-web` cho demo thuần WebFlux vì Boot có thể ưu tiên Servlet khi cả hai stack cùng trên classpath.

### 8.2. application.yml

**`src/main/resources/application.yml`**:

```yaml
server:
  address: 127.0.0.1
  port: 8080
  forward-headers-strategy: framework

spring:
  application:
    name: https-proxy-demo
```

- Netty chỉ bind loopback trên máy chạy demo, tránh public backend port.
- Backend không bật TLS tại 8080. TLS public đặt ở proxy.
- `framework` kích hoạt ForwardedHeaderTransformer trong WebFlux.
- Test `RANDOM_PORT` override cổng, vẫn truy cập trên loopback.
- Nếu chạy container trên máy khác, không copy nguyên ràng buộc địa chỉ mà chưa hiểu mạng; phải cấu hình private listener và network policies.

### 8.3. Main class

**`src/main/java/example/httpsproxy/HttpsProxyApplication.java`**:

```java
package example.httpsproxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpsProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpsProxyApplication.class, args);
    }
}
```

### 8.4. Cấu hình Spring Security WebFlux

**`src/main/java/example/httpsproxy/SecurityConfiguration.java`**:

```java
package example.httpsproxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("local-demo-password"))
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("local-demo-password"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .redirectToHttps(Customizer.withDefaults())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/api/private")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Giải thích:

1. `redirectToHttps` xử lý khi **scheme mà Spring nhận là HTTP**. Nếu trước đó ForwardedHeaderTransformer đã chuẩn hóa scheme=https thì request đi tiếp, tránh vòng lặp.
2. Role không thể bị nâng cấp chỉ vì có HTTPS. `/api/admin` vẫn kiểm tra `ROLE_ADMIN`.
3. HTTP Basic chỉ giúp test nhận rõ 401 (thiếu authentication) và 403 (đã login, thiếu role). Đừng gửi Basic credentials thật qua HTTP công khai; production nên dùng HTTPS và xác thực phù hợp.
4. Login HTML bị tắt để tránh nhầm 302 redirect tới trang login với 3xx redirect HTTPS.
5. CSRF vẫn bật mặc định; demo chỉ dùng GET. Nếu mở unsafe methods cho browser cookies thì thiết kế CSRF riêng.
6. Bản demo tạo password hash bằng `DelegatingPasswordEncoder`, mật khẩu cứng chỉ dùng localhost/test. Không copy tài khoản demo vào production.
7. Một `SecurityWebFilterChain` áp dụng toàn bộ URL; nếu app thực có nhiều chain, phải đặt và test HTTPS policy theo từng matcher.

### 8.5. Controller quan sát scheme public

**`src/main/java/example/httpsproxy/ApiController.java`**:

```java
package example.httpsproxy;

import java.net.URI;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> perceivedUri(ServerWebExchange exchange) {
        URI uri = exchange.getRequest().getURI();
        return Mono.just(uri.getScheme() + "://" +
                uri.getRawAuthority() + uri.getRawPath());
    }

    @GetMapping("/api/private")
    public Mono<String> privateInfo() {
        return Mono.just("private-ok");
    }

    @GetMapping("/api/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin-ok");
    }
}
```

Sau khi framework tin header **đến từ proxy đã sanitize**, `/api/public` mô phỏng external URL như `https://app.example.test/api/public` dù backend socket HTTP. Trong production, không dùng endpoint debug công khai này làm nơi tạo password-reset URLs hoặc quyết định ai được tin; đối với link nhạy cảm, dùng public base URL cấu hình cố định và validate.

Không có `block()` hay `subscribe()` tự gọi trong controller; WebFlux nhận `Mono<String>`.

## 9. Integration tests với WebTestClient và Netty thực

Test này chạy embedded Netty qua `@SpringBootTest(webEnvironment=RANDOM_PORT)`. Mỗi client test gửi HTTP tới loopback backend:

- `direct`: không có forwarded headers, đại diện request backend HTTP trực tiếp.
- `proxied`: gắn `X-Forwarded-Proto: https`, host và port để mô phỏng những headers một **proxy tin cậy** đã đặt.

**Chú ý:** kết nối test vẫn là HTTP; test chỉ chứng minh xử lý scheme và security filter logic, **không** chứng minh TLS/certificate/ngăn spoof headers ở production. Những phần đó phải được test sau khi triển khai reverse proxy thật.

**`src/test/java/example/httpsproxy/HttpsProxyIntegrationTest.java`**:

```java
package example.httpsproxy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpsProxyIntegrationTest {

    @LocalServerPort
    int port;

    private WebTestClient direct;
    private WebTestClient proxied;

    @BeforeEach
    void prepareClients() {
        String url = "http://127.0.0.1:" + port;

        direct = WebTestClient.bindToServer()
                .baseUrl(url)
                .build();

        // Header được đặt bởi mock proxy trong test, KHÔNG phải production.
        proxied = WebTestClient.bindToServer()
                .baseUrl(url)
                .defaultHeader("X-Forwarded-Proto", "https")
                .defaultHeader("X-Forwarded-Host", "app.example.test")
                .defaultHeader("X-Forwarded-Port", "443")
                .build();
    }

    @Test
    void httpDirectRequestRedirectsToHttps() {
        direct.get().uri("/api/public")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().value("Location", location ->
                        assertTrue(location.startsWith("https://")));
    }

    @Test
    void insecureResponseDoesNotSetHsts() {
        direct.get().uri("/api/public")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().doesNotExist("Strict-Transport-Security");
    }

    @Test
    void forwardedHttpsIsRecognizedWithoutLoop() {
        proxied.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> {
                    assertTrue(body.startsWith(
                            "https://app.example.test"));
                    assertTrue(body.endsWith("/api/public"));
                });
    }

    @Test
    void forwardedHttpsAnonymousStillNeedsLogin() {
        proxied.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderGetsPrivateData() {
        proxied.get().uri("/api/private")
                .headers(headers -> headers.setBasicAuth(
                        "reader", "local-demo-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("private-ok");
    }

    @Test
    void authenticatedReaderCannotUseAdminEndpoint() {
        proxied.get().uri("/api/admin")
                .headers(headers -> headers.setBasicAuth(
                        "reader", "local-demo-password"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void authorizedAdminCanUseAdminEndpoint() {
        proxied.get().uri("/api/admin")
                .headers(headers -> headers.setBasicAuth(
                        "admin", "local-demo-password"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void recognizedSecureRequestGetsHsts() {
        proxied.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("Strict-Transport-Security");
    }

    @Test
    void forwardedHttpStillRequiresRedirect() {
        direct.get().uri("/api/public")
                .header("X-Forwarded-Proto", "http")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().value("Location", location ->
                        assertTrue(location.startsWith("https://")));
    }

    @Test
    void securePublicApiNeedsNoIdentity() {
        proxied.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Chạy từ project có Gradle Wrapper:

```bash
./gradlew test --tests example.httpsproxy.HttpsProxyIntegrationTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.httpsproxy.HttpsProxyIntegrationTest
```

**Kỳ vọng:** 10 test PASS với JDK, Gradle, dependencies và project theo ví dụ. Đây là kỳ vọng từ source, **không phải kết quả chạy thực tế tại workspace**. Khi nâng Spring Boot/Security hoặc đổi server, nên test lại status, Host forwarding, TLS handling và cookie.

### Ý nghĩa từng nhóm test

| Nhóm test | Chứng minh |
| --- | --- |
| Direct HTTP → 3xx + Location HTTPS | Redirect filter hoạt động |
| Direct HTTP không có HSTS | HSTS không được gửi như thể request secure |
| Forwarded HTTPS → 200, URI public | Framework đã khôi phục scheme/host/port theo metadata |
| Forwarded HTTPS private không credential → 401 | HTTPS không bypass authentication |
| Reader private → 200; reader admin → 403 | Authorization vẫn phân quyền |
| Admin → 200 | Role hợp lệ |
| Forwarded HTTPS có HSTS | Spring thấy request secure và áp header bảo vệ |
| Forwarded HTTP vẫn 3xx | XFP=http không lách được yêu cầu HTTPS |

Các test này **không bảo đảm** backend production không thể bị gọi trực tiếp với fake headers. Cần test firewall/ingress tại hạ tầng; test TLS với certificate thật; test browser HSTS/cookie ở domain thật.

## 10. Thử thủ công và kiểm tra kết quả

### 10.1. Chạy backend demo

Trong project có Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

### 10.2. HTTP backend trực tiếp

```bash
curl -i "http://127.0.0.1:8080/api/public"
```

Kỳ vọng: response 3xx và `Location` có scheme HTTPS. Đừng tự động dùng `curl -L` follow sang cổng HTTP 8080 vì ví dụ chưa chạy TLS trên cổng đó. Port redirect được quyết định bởi `HttpsRedirectWebFilter`/port mapping; không giả định nó chính là port backend.

### 10.3. Mô phỏng request từ proxy HTTPS trong môi trường local

```bash
curl -i "http://127.0.0.1:8080/api/public" \
    -H "X-Forwarded-Proto: https" \
    -H "X-Forwarded-Host: app.example.test" \
    -H "X-Forwarded-Port: 443"
```

Kỳ vọng: 200 với URI biểu thị `https://app.example.test/api/public`. Việc `curl` tự đặt được header chính là lý do **backend không được public** khi tin forwarded metadata.

### 10.4. Qua Nginx thực tế

Sau khi cài certificate hợp lệ tại domain do bạn quản lý:

```bash
curl -i "https://app.example.test/api/public"
curl -I "http://app.example.test/api/public"
```

- Request HTTPS public nên qua TLS thật tới proxy, về backend như forwarded HTTPS, rồi trả 200.
- Request HTTP public tới port 80 thường nhận 308 từ Nginx và không vào Spring trong cấu hình bài.
- Kiểm tra TLS certificate chain, đúng hostname, và HSTS trên HTTPS.
- Không dùng `curl -k` trong kiểm thử TLS production vì sẽ bỏ qua xác minh certificate.

Nếu browser liên tục 301/302 cùng URL, kiểm tra headers tại proxy và forwarded strategy, **không** chỉ xóa cookie browser.

## 11. HSTS: bảo vệ lần truy cập sau

HSTS (HTTP Strict Transport Security) cho browser biết một host chỉ nên được truy cập HTTPS trong khoảng thời gian do server thông báo:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

- `max-age`: khoảng thời gian browser ghi nhớ chính sách.
- `includeSubDomains`: áp dụng thêm cho subdomain; không bật trước khi kiểm kê các host có thể vẫn chạy HTTP.
- `preload`: chỉ thị cho chương trình preload theo điều kiện và quy trình riêng, không phải thêm chữ `preload` là được preload ngay.
- Header HSTS **chỉ có ý nghĩa khi browser nhận qua HTTPS hợp lệ**; không thể dùng một HTTP response để khởi tạo tin cậy HSTS.

Spring Security hỗ trợ HSTS cho secure responses theo mặc định. Đằng sau proxy TLS termination, nếu app nhìn nhận scheme sai là HTTP, HSTS có thể không được ghi đúng. Đây là lý do nhận diện forwarded scheme ảnh hưởng cả redirect **và** header security.

Không lạm dụng HSTS preload ở hệ thống có subdomain legacy; browser cache/preload có thể tồn tại lâu sau khi rollback.

## 12. Cookie Secure, auth callback và absolute URL

### Cookie/session

Một ứng dụng dùng WebSession và cookie đăng nhập nên đánh giá `Secure`, `HttpOnly`, `SameSite`, domain/path phù hợp. Cơ chế phát cookie có thể dựa vào request secure information, nên kiểm tra `Set-Cookie` ở response **HTTPS qua proxy thật**, không chỉ trên một fake forwarded header trong test. HSTS và Secure cookie không thay CSRF protection.

### OAuth2/OIDC

Redirect URI có thể bị dựng sai thành:

```text
http://127.0.0.1:8080/login/oauth2/code/provider
```

thay vì:

```text
https://app.example.test/login/oauth2/code/provider
```

Identity provider thường kiểm tra redirect URI đã đăng ký, nên scheme/host/port sai tạo `redirect_uri mismatch`. Khi chạy OAuth2 login, test callback qua proxy TLS thực tế, kiểm tra client registration, server base URL, forwarded metadata và các security allowlists. Không mở callback HTTP public để xử lý lỗi.

### Absolute links

Password-reset link, invitation email, Location header, redirect success URL và links trong JSON/HATEOAS đều có thể phụ thuộc request host. Với URL liên quan tài khoản hoặc token, ưu tiên **public base URL cấu hình cố định, đã xác minh** thay vì tin raw Host/Forwarded-Host.

## 13. Tùy môi trường và reverse proxy nhiều tầng

### Dev chưa có TLS

Nếu bật `redirectToHttps` nhưng chỉ có HTTP ở localhost:8080, browser có thể được chuyển tới HTTPS endpoint **chưa tồn tại**. Đó là hành vi theo chính sách HTTPS, không phải lỗi password hay CORS.

Chọn một trong hai cách:

- Tạo reverse proxy HTTPS trên localhost dùng chứng chỉ dev được tin cậy, gần với topology production.
- Chỉ trong profile dev, tắt riêng HTTPS redirect dựa trên **configuration property đáng tin** do vận hành quản lý; giữ authentication/authorization, và kiểm soát không deploy profile đó lên Internet.

Không suy rằng network private luôn miễn cần TLS; mạng nội bộ chia sẻ có thể bị sniffing hoặc cần mTLS.

### Nếu có CDN → LB → Gateway → Spring

- Xác định nơi kết thúc TLS bên ngoài, nơi đặt X-Forwarded-Proto được tin.
- Tại edge, xóa forwarded headers không tin từ client; ở các hop nội bộ, xác định cách overwrite/append.
- Xác nhận IP/CIDR/identity của proxy được phép vào backend.
- Nếu route có prefix public khác backend, kiểm tra `X-Forwarded-Prefix` và URL generation.
- Từ chối Host không khai báo, tránh redirect hoặc email link tới host attacker.
- Khi có nhiều security chains, bảo đảm `redirectToHttps` ở các chain cần thiết hoặc được edge enforce trước tất cả.
- Không để proxy và Spring cùng tạo các redirect mâu thuẫn (HTTP⇄HTTPS hoặc slash/path rewrite loop).

## 14. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Browser báo ERR_TOO_MANY_REDIRECTS | Spring nhìn backend HTTP mặc dù browser HTTPS | Trusted forwarded scheme + framework strategy |
| HTTPS public bị redirect về chính nó | Proxy thiếu XFP=https hoặc Spring không xử lý | Kiểm tra actual request ở từng hop |
| Location trỏ internal host:8080 | Forwarded Host/Port không được chuẩn hóa | Proxy set external host/port cố định |
| Backend HTTP public trả 200 khi client tự gửi XFP=https | Header spoofing, trust boundary bị phá | Firewall, bind private, strip headers ở edge |
| HTTPS hostname ngẫu nhiên tạo URL redirect lạ | Host/Forwarded-Host poisoning | Host allowlist, default vhost reject |
| HSTS thiếu sau TLS proxy | Spring nghĩ request HTTP hoặc gateway xóa header | Kiểm tra transformed scheme và response edge |
| HTTP direct không có HSTS | HSTS không hợp lệ trên HTTP | Đây là hành vi mong muốn |
| Browser vào HTTPS trên cổng backend HTTP | TLS handshake thất bại | Dùng cổng 443 của proxy, không phải 8080 |
| OAuth2 redirect_uri mismatch | Scheme/host/port callback bị suy ra sai | Forwarded headers + public registered redirect URL |
| Password-reset link dùng http/internal host | URL builder tin request sai | Config public base URL tin cậy |
| Cookie không có Secure | Session/proxy config hoặc backend nhận sai scheme | Kiểm tra Set-Cookie từ HTTPS edge |
| Gateway không gửi forwarded metadata | Backend không thể biết TLS gốc | Bổ sung header chuẩn từ gateway đáng tin |
| Strategy=native khác framework | Native implementation khác hỗ trợ header | Chọn strategy đã test đúng stack |
| @Configuration tạo hai transformer | Xử lý trùng hoặc policy xung đột | Dùng một cơ chế forwarding duy nhất |
| Trộn RFC Forwarded và XFP mâu thuẫn | Proxy không sanitize mọi biến thể | Strip cả hai rồi tạo metadata nhất quán |
| HSTS includeSubDomains làm hỏng subdomain | Chưa migrate hết sang HTTPS | Audit/rollout trước khi bật |
| 401 sau proxy HTTPS | Authentication chưa đạt | Sửa credential/token, không nới redirect |
| 403 sau proxy HTTPS | Thiếu role, CSRF hoặc rule | Phân tích authorization/CSRF riêng |
| Request POST đổi method sau redirect | 301/302/307/308 có semantics khác | Dùng HTTPS URL ngay từ đầu; test client |
| App có hai SecurityWebFilterChain, một chain không redirect | HTTPS rule thiếu trên một matcher | Test từng chain/route |
| Test WebTestClient pass nhưng site public còn lộ HTTP | Test không kiểm tra ingress/network | Bổ sung TLS/network integration test |

### Trình tự gỡ lỗi 302 loop

1. Xác định URL browser sử dụng, đâu là edge TLS termination.
2. Trong Network tab, ghi status và Location qua từng hop, không chia sẻ session cookie/token.
3. Kiểm tra proxy có thật sự chuyển HTTPS vào backend, và đã set X-Forwarded-Proto=https chưa.
4. Kiểm tra proxy **loại bỏ** Forwarded/X-Forwarded-* do client gửi trước khi set metadata.
5. Xem Boot strategy đang dùng là none/native/framework, và stack là WebFlux chứ không phải Servlet.
6. Kiểm tra perceived scheme/host/port tại staging an toàn, xác định redirect filter nào tạo response.
7. Xác minh route match đúng SecurityWebFilterChain.
8. Test HTTP direct → 3xx, forwarded HTTPS → 200/401/403, sau đó test browser qua TLS thật.
9. Kiểm tra HSTS, cookie Secure và absolute callback URLs.
10. Chỉ sửa thành phần có bằng chứng sai; không tắt security một cách bừa bãi.

## 15. Checklist production

1. Có HTTPS public tại edge, chứng chỉ hợp lệ và được giám sát expiry/chain.
2. Edge HTTP redirect sớm sang HTTPS, không chấp nhận credential nhạy cảm trên HTTP.
3. Backend không public; chỉ trusted reverse proxy/ingress được phép kết nối.
4. Proxy sanitize toàn bộ Forwarded và X-Forwarded-* từ client, ghi đúng original proto/host/port.
5. Host allowlist rõ ràng; không sinh URL nhạy cảm từ arbitrary headers.
6. Spring Boot dùng forwarding strategy tương thích và đã kiểm chứng (ví dụ `framework` trong WebFlux).
7. `redirectToHttps(Customizer.withDefaults())` hoặc edge enforcement được áp nhất quán cho các chain/route.
8. HTTPS browser qua proxy không gặp vòng lặp hoặc Location nội bộ.
9. HSTS có max-age/includeSubDomains phù hợp, không bật preload khi chưa đủ điều kiện.
10. Cookie Secure/HttpOnly/SameSite/Domain/Path đúng với topology và được test qua browser.
11. OAuth2 callbacks và absolute links trả URL HTTPS public chính xác.
12. Authentication, authorization, CSRF vẫn có hiệu lực; HTTPS không thay thế phân quyền.
13. Test HTTP/HTTPS, 3xx/401/403/200, host sai, forwarded metadata giả, gateway chain và TLS certificate.
14. Log/tracing không chứa password, bearer token, cookie/session ID và forwarded headers raw không tin cậy.
15. Review lại chiến lược khi đổi proxy, thêm CDN, đổi domain hoặc thay phiên bản Spring.

## 16. Bài tập

1. Bỏ `server.forward-headers-strategy=framework` trong demo đang sau proxy HTTP, dự đoán lỗi redirect và xác minh.
2. Bật `framework`, mô phỏng X-Forwarded-Proto=https và chứng minh không redirect. Vì sao phép thử này không chứng minh TLS thật?
3. Thử `X-Forwarded-Host` khác giá trị expected trong môi trường test để thấy rủi ro URL poisoning. Đặt host allowlist ở edge và backend không public.
4. So sánh none/native/framework trên Reactor Netty, xác định scheme/host/port trong controller theo từng chế độ.
5. Thêm GET /api/admin cho user READER: kiểm tra 403 sau forwarded HTTPS để chứng minh transport khác authorization.
6. Tắt redirect chỉ trong profile dev và thêm test/provisioning rule ngăn sử dụng profile đó ở production.
7. Dựng proxy TLS thật với domain bạn sở hữu, kiểm tra HSTS và Set-Cookie qua Chrome DevTools.
8. Di chuyển OAuth2 client ra sau proxy, so sánh redirect_uri khi có/không trusted forwarded metadata.
9. Thêm security chain cho /admin/**, xác minh HTTPS rule áp đúng cả hai chain.
10. Chuyển pipeline sang CDN → gateway → app; mô tả trusted hops, nơi strip headers và nơi append IP.
11. Tìm một endpoint dựng password-reset URL từ request Host và thay bằng public base URL đã validate.
12. Kiểm tra ý nghĩa 301/302/307/308 với form POST thử nghiệm; thiết kế sao cho credential không gửi qua HTTP ban đầu.

## Tổng kết

Ở Spring Security **WebFlux**, `redirectToHttps(Customizer.withDefaults())` giúp chuyển request mà framework nhìn thấy là HTTP sang HTTPS. Khi TLS kết thúc tại reverse proxy, ứng dụng có thể nhận HTTP nội bộ mặc dù browser đã HTTPS; `server.forward-headers-strategy: framework` và `ForwardedHeaderTransformer` giúp khôi phục scheme/host/port **nếu metadata đến từ proxy đã được tin cậy**.

Thiếu forwarding đúng dễ gây **redirect loop** và URL/cookie/HSTS/callback sai. Nhưng tin `X-Forwarded-Proto`/`X-Forwarded-Host` do client ngoài đặt lại có thể tạo bypass hoặc host poisoning. Bảo vệ phải có **TLS edge + network isolation + proxy header sanitation + Spring redirect/forwarding configuration + kiểm thử thật**. HSTS, Secure cookies, CSRF và phân quyền là các lớp bổ sung, không thể thay thế nhau.

## Tài liệu chính thức

- [Spring Security 6.5 — Reactive HTTP, Redirect to HTTPS và Proxy Server Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/http.html)
- [Spring Security 6.5 — ServerHttpSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security 6.5 — HttpsRedirectWebFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/transport/HttpsRedirectWebFilter.html)
- [Spring Security 6.5 — HTTP Strict Transport Security](https://docs.spring.io/spring-security/reference/6.5/features/exploits/headers.html)
- [Spring Boot 3.5 — Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Framework 6.2 — WebFlux Forwarded Header Transformer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239)
- [RFC 6797 — HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797)
- [OWASP — HTTP Strict Transport Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html)
