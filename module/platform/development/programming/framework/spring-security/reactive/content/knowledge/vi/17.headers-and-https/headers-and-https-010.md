# Tùy chỉnh header theo điểm truy cập và kiểm tra giá trị thực tế trong Spring Security Reactive

## 1. Bài toán và mục tiêu

Một ứng dụng **Spring WebFlux + Spring Security Reactive** có thể trả nhiều loại tài nguyên:

- **GET /public/ping**: JSON công khai.
- **GET /ui/help**: trang HTML đơn giản, có thể chứa stylesheet và hình ảnh cùng origin.
- **GET /api/me**: JSON chứa danh tính người đã đăng nhập.
- **GET /api/admin/report**: JSON chỉ dành cho ROLE_ADMIN.

Mọi response nên giữ các **security headers cơ bản**, nhưng một số header cần **chính sách theo endpoint**. Ví dụ CSP cho trang HTML khác với CSP dành cho JSON; API riêng tư phải chống cache; host HTTPS cần HSTS, kể cả khi response có status lỗi. Nếu chỉ nhìn code cấu hình, ta không biết gateway hoặc error handler có thay đổi header trên response đến trình duyệt hay không.

Sau bài học, bạn có thể:

1. Phân biệt request headers, response headers, quyền truy cập URL và quy tắc browser.
2. Hiểu các header mặc định của Spring Security WebFlux và lý do không vô hiệu hóa toàn bộ mặc định để thêm một header.
3. Cấu hình **ServerHttpSecurity.headers(...)** và **ServerHttpHeadersWriter** để chọn header theo path/response type.
4. Nhận biết vai trò của **Cache-Control, X-Content-Type-Options, X-Frame-Options, Content-Security-Policy, Referrer-Policy, Permissions-Policy, HSTS**.
5. Đảm bảo header hiện diện trên cả 200, **401 Unauthorized** và **403 Forbidden**.
6. Phân biệt HSTS trên HTTPS với request HTTP hoặc TLS termination ở reverse proxy.
7. Chạy một demo **Java 17+**, Spring Boot WebFlux và kiểm thử bằng curl, WebTestClient và mock HTTPS exchange.
8. Kiểm tra response cuối sau CDN/NGINX/Ingress/API gateway thay vì coi code Java là bằng chứng cuối.
9. Tránh CSP yếu, cache dữ liệu cá nhân, HSTS preload không an toàn, header trùng và nhầm CORS/CSRF.

**Quy tắc quan trọng:** mục tiêu không phải thêm thật nhiều header, mà là **đặt đúng header cho đúng response, không phá các mặc định hữu ích, và kiểm tra giá trị trên HTTP wire**.

## 2. Request header khác response header

Ví dụ request:

~~~http
GET /api/me HTTP/1.1
Host: api.example.org
Authorization: Basic <encoded-credentials>
Accept: application/json
Origin: https://app.example.org
~~~

Header Authorization và Origin là thông tin từ client; **Origin không xác thực danh tính**, và header do client gửi không phải là security policy của server.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'

{"username":"reader"}
~~~

Header response hướng dẫn browser/proxy cách xử lý nội dung; việc reader được xem hồ sơ đến từ **Authentication, SecurityContext, authorizeExchange và quyền nghiệp vụ**, không phải từ CSP hay no-store.

| Header response | Công dụng | Không thay thế được |
| --- | --- | --- |
| Cache-Control: no-store | Tránh cache lưu dữ liệu nhạy cảm | Authentication, logout, xóa dữ liệu đã tải |
| X-Content-Type-Options: nosniff | Hạn chế browser đoán MIME type | Content-Type đúng, xử lý file độc hại |
| Content-Security-Policy | Hạn chế nguồn script/style/img, framing theo directive | Input validation, output encoding, auth |
| X-Frame-Options: DENY | Chặn nhúng trang trong frame ở browser hỗ trợ | Quyền truy cập dữ liệu, CSP toàn diện |
| Referrer-Policy | Giới hạn dữ liệu URL rò qua Referer | CSRF token, chống XSS |
| Permissions-Policy | Giới hạn camera/geolocation/microphone và browser features | ROLE_ADMIN, API scopes |
| Strict-Transport-Security | Yêu cầu browser ưu tiên HTTPS cho host ở các lần sau | TLS certificate, redirect HTTPS ban đầu |
| Access-Control-Allow-Origin | Cho phép browser một số cross-origin reads | Authentication, authorization, CSRF |

**Đừng nhầm “điểm truy cập” với tên Java class.** Một điểm truy cập được xác định bằng method/path thực mà request đi qua. @RestController hay RouterFunction đều có thể được bảo vệ bằng một SecurityWebFilterChain nếu được đăng ký trong cùng ứng dụng WebFlux.

### 2.1. Origin, Site và Host không phải chủ thể xác thực

Header Origin có thể liên quan CORS, nhưng không chứng minh user là nhân viên. Các headers X-Forwarded-* có thể có giá trị khi đứng sau proxy **đáng tin**, nhưng không được tin bừa từ Internet. Việc chọn header profile theo path phải dựa trên server-side policy, không ghép giá trị header từ client vào CSP/HSTS tùy ý.

## 3. Những header Spring Security Reactive cung cấp mặc định

Trong Spring Security 6.x, cấu hình headers mặc định thường bao gồm:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

Trên một **secure HTTPS request**, Spring Security còn có writer HSTS, mặc định một năm và includeSubDomains. HSTS **không được ghi trên HTTP** theo hành vi writer chuẩn.

Ghi chú:

- **CSP không được tự động cấu hình một chính sách đủ dùng cho mọi ứng dụng**. Mỗi ứng dụng HTML/SPA cần lựa chọn nguồn script, style, image, font và frame.
- **X-XSS-Protection: 0** là vô hiệu hóa bộ lọc XSS cũ của một số browser, không phải tắt việc bảo vệ XSS của ứng dụng.
- **Referrer-Policy** cần được kiểm tra theo phiên bản và policy thực tế; demo sẽ cấu hình rõ no-referrer để test giá trị ổn định.
- Nếu response đã tự có Cache-Control, một số default writer có thể tôn trọng value đó; đừng mặc định mọi response của mọi tầng đều giống nhau.
- **Header support phải giữ bật**: thêm một header không phải lý do để tắt cả baseline.

Đoạn sai:

~~~java
// Không dùng chỉ để thêm một CSP mới.
.headers(headers -> headers.disable())
~~~

Nếu tắt toàn bộ defaults, bạn phải chủ động quản lý mọi header quan trọng và rủi ro cấu hình sai cao hơn. Nên dùng HeaderSpec.writer hoặc DSL hsts/frameOptions/referrerPolicy/permissionsPolicy cụ thể.

### 3.1. Trạng thái HTTP cũng quan trọng

Khi GET /api/me chưa có credential, authentication entry point có thể trả 401 **trước khi controller chạy**. Khi reader vào /api/admin/report thiếu ROLE_ADMIN, access denied handler có thể trả 403. Nếu bạn chỉ set headers trong controller, các response lỗi này có thể không nhận chính sách.

**Yêu cầu của bài:** test CSP, cache, no-sniff và các header cần thiết trên **200/401/403**; đồng thời test tại public edge nếu có proxy.

## 4. Ma trận chính sách header theo endpoint

Dự án mẫu chọn:

| Endpoint | Ai được gọi? | Response header riêng | Baseline chung |
| --- | --- | --- | --- |
| GET /public/ping | Guest và user | CSP JSON chặt | Cache no-store, no-sniff, frame DENY, referrer no-referrer |
| GET /ui/help | Guest và user | CSP phù hợp HTML không có script | Tương tự |
| GET /api/me | Authenticated | CSP JSON, Permissions-Policy, X-Robots-Tag | Tương tự |
| GET /api/admin/report | ROLE_ADMIN | Chính sách API kể cả trên 403 | Tương tự |
| URL lạ | denyAll | CSP JSON chặt làm fallback | Tương tự |

Giá trị CSP JSON:

~~~http
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

Giá trị CSP trang HTML help:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

Tại sao khác nhau? JSON không phải trang chứa script/style; CSP chặt là defense in depth khi trình duyệt vô tình diễn giải nội dung. HTML có thể cần CSS và hình từ cùng origin; demo vẫn không cho scripts hoặc iframe. Nếu HTML thực sự cần JavaScript, phải thiết kế **script-src/connect-src/nonce/hash** phù hợp. Không nên thêm 'unsafe-inline' hay '*' chỉ để làm mất cảnh báo CSP.

**X-Frame-Options DENY** được giữ nhất quán với **frame-ancestors 'none'**. Nếu sản phẩm cần được nhúng vào iframe đã phê duyệt, phải thay đổi đồng bộ và test khả năng chống clickjacking.

Đối với API:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Robots-Tag: noindex, nofollow
~~~

Đây là các chính sách browser/crawler bổ sung, **không cấp hay tước quyền API**. Không dùng X-Robots-Tag như giải pháp bảo mật dữ liệu, vì bot không buộc phải tôn trọng nó.

### 4.1. Cache dữ liệu cá nhân

Với /api/me và /api/admin/report, hãy bảo đảm **Cache-Control có directive no-store**. Một CDN sai cấu hình cache response có Authorization hoặc cookie có thể tạo sự cố nghiêm trọng, ngay cả khi CSP đúng.

Với /assets/app.abc123.js là file công khai mang content hash, **public,max-age dài,immutable** có thể có lợi. Nhưng đây là policy khác, nên đặt đúng tại static resource handler/proxy và test Cache-Control, Pragma, Expires, Vary; **không** mở cache mặc định cho mọi đường /api/**.

## 5. API reactive dùng để thêm header

Package đúng của WebFlux:

~~~java
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.ServerHttpHeadersWriter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
~~~

**ServerHttpHeadersWriter** có hợp đồng:

~~~java
Mono<Void> writeHttpHeaders(ServerWebExchange exchange);
~~~

Đây là chữ ký minh họa, không phải file Java độc lập. Trong Spring Security 6.5, API **ServerHttpSecurity.HeaderSpec.writer(ServerHttpHeadersWriter)** cho phép thêm custom writer vào header support.

Ví dụ một phần cấu hình SecurityWebFilterChain:

~~~java
return http
        .headers(headers -> headers
                .writer(endpointHeadersWriter))
        .build();
~~~

**Không gọi subscribe() thủ công** trên Mono<Void>. Spring Security đưa writer vào đúng luồng response commit. Nếu viết WebFilter riêng, cần hiểu response.beforeCommit và thứ tự filter; tránh viết headers quá muộn sau khi response đã commit.

### 5.1. Cách chọn path đúng

~~~java
String path = exchange.getRequest()
        .getPath().pathWithinApplication().value();
~~~

Với một application path không đổi, ta có thể dùng exact match cho /ui/help và prefix cho /api/. Nếu có gateway rewrite URL, context path hoặc nhiều SecurityWebFilterChain, cần đối chiếu **path thực mà WebFlux nhìn thấy**; đường dẫn ở browser có thể khác vì proxy.

### 5.2. Header theo URL không đồng nghĩa role policy theo URL

Custom writer chỉ quyết định header response. Authentication và authorization được khai báo riêng:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers("/public/ping", "/ui/help").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

**Đặt rule admin trước /api/**. Nếu đảo thứ tự, người đã đăng nhập nhưng thiếu ROLE_ADMIN có thể qua rule authenticated rộng. Dù CSP đúng, đó vẫn là lỗ hổng authorization.

## 6. HSTS chỉ có ý nghĩa đúng trên HTTPS

**HTTP Strict Transport Security** báo cho browser sử dụng HTTPS cho host trong thời hạn max-age. Nó không tạo TLS certificate, không tự ngăn tấn công trước khi browser từng học policy, cũng không thay thế redirect HTTPS.

Ví dụ:

~~~http
Strict-Transport-Security: max-age=2592000
~~~

2592000 giây = **30 ngày**. Demo chọn 30 ngày, **includeSubDomains=false**, **preload=false** để minh họa một bước rollout thận trọng. Đây **không phải** khuyến nghị mặc định cho mọi production: mức độ bảo vệ tối ưu cần tăng sau khi hệ thống đã kiểm toán HTTPS.

- **Trên HTTP localhost:** không kỳ vọng HSTS. Một browser phải bỏ qua HSTS nhận qua HTTP không bảo mật.
- **Trên HTTPS public URL:** kỳ vọng HSTS theo policy sau khi proxy/edge xử lý.
- **includeSubDomains** chỉ nên bật khi toàn bộ subdomains phục vụ HTTPS tin cậy.
- **preload** có tiêu chí/ảnh hưởng dài hạn; không tự bật chỉ vì một endpoint admin cần tăng bảo mật.
- HSTS là **chính sách theo host**, không phải chính sách cho riêng /api/admin hoặc cho một role.

### 6.1. Khi có TLS termination

Kiến trúc thường gặp:

~~~text
Browser -- HTTPS --> Reverse proxy -- HTTP nội bộ --> WebFlux
~~~

Nếu backend chỉ thấy HTTP, HSTS writer có thể không ghi header. Hãy đảm bảo:

1. Proxy ở ranh giới tin cậy xác thực TLS rồi xóa/ghi đè header Forwarded/X-Forwarded-* do Internet gửi.
2. Spring xử lý forwarded headers chỉ khi topology và trusted proxy đã được thiết kế rõ.
3. Redirect HTTP→HTTPS và Set-Cookie Secure hoạt động đúng qua edge.
4. Chọn nơi sở hữu HSTS policy cuối cùng (proxy hoặc ứng dụng) để tránh duplicate/mâu thuẫn.
5. **curl tới HTTPS public URL** để kiểm tra giá trị sau cùng, không chỉ nhìn localhost.

Ví dụ cấu hình chỉ dành cho deployment có proxy đáng tin:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Không bật nó máy móc khi backend trực tiếp phơi ra Internet và client có thể giả mạo X-Forwarded-Proto. Cần đánh giá trust boundary trước.

## 7. Dự án mẫu Java 17+ Spring Boot WebFlux

Dùng **Java 17+**, **Spring Boot 3.5.16**, Gradle 8.x tương thích và Spring Security reactive do BOM của Spring Boot quản lý. Không thêm spring-boot-starter-web nếu muốn quan sát chính xác WebFlux pipeline. Với production, kiểm tra bản vá và nhánh hỗ trợ đang áp dụng.

Tài khoản demo:

| Username | Password dùng trong demo local | Role |
| --- | --- | --- |
| reader | reader-pass | ROLE_USER |
| admin | admin-pass | ROLE_USER, ROLE_ADMIN |

**Không hard-code credential thật trong source hoặc frontend**. HTTP Basic Base64 không phải mã hóa; chỉ dùng HTTP localhost để học, production phải dùng HTTPS/TLS và identity store phù hợp.

Cấu trúc:

~~~text
webflux-endpoint-headers/
├── settings.gradle
├── build.gradle
├── src/main/java/example/headers/HeadersApplication.java
├── src/main/java/example/headers/SecurityConfig.java
├── src/main/java/example/headers/EndpointHeadersWriter.java
├── src/main/java/example/headers/Endpoints.java
├── src/test/java/example/headers/HeaderPolicyTest.java
└── src/test/java/example/headers/HstsWriterTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-endpoint-headers'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.3. HeadersApplication.java

~~~java
package example.headers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(HeadersApplication.class, args);
    }
}
~~~

### 7.4. EndpointHeadersWriter.java

~~~java
package example.headers;

import org.springframework.http.HttpHeaders;
import org.springframework.security.web.server.header.ServerHttpHeadersWriter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class EndpointHeadersWriter
        implements ServerHttpHeadersWriter {

    public static final String API_CSP =
            "default-src 'none'; base-uri 'none'; "
            + "object-src 'none'; frame-ancestors 'none'";

    public static final String HELP_CSP =
            "default-src 'none'; style-src 'self'; "
            + "img-src 'self'; base-uri 'none'; "
            + "object-src 'none'; frame-ancestors 'none'";

    public static final String API_PERMISSIONS =
            "camera=(), microphone=(), geolocation=()";

    @Override
    public Mono<Void> writeHttpHeaders(ServerWebExchange exchange) {
        return Mono.fromRunnable(() -> {
            String path = exchange.getRequest()
                    .getPath().pathWithinApplication().value();

            HttpHeaders h = exchange.getResponse().getHeaders();

            // Dùng CSP fallback chặt cho mọi path và response lỗi.
            h.set("Content-Security-Policy",
                    "/ui/help".equals(path) ? HELP_CSP : API_CSP);

            if (path.startsWith("/api/")) {
                h.set("Permissions-Policy", API_PERMISSIONS);
                h.set("X-Robots-Tag", "noindex, nofollow");
            }
        });
    }
}
~~~

Giải thích:

- Writer dùng **ServerWebExchange**, không dùng HttpServletResponse của servlet.
- **Mono.fromRunnable** giúp mutation headers diễn ra khi reactive publisher được subscribe đúng vòng đời commit; không tự gọi subscribe()/block().
- CSP được chọn bằng **path** nhưng **value đến từ chuỗi do server kiểm soát**, không phản chiếu query, Host, Origin, username.
- Mọi path trừ /ui/help có CSP chặt, kể cả response 401/403/denyAll.
- /api/** thêm Permissions-Policy và X-Robots-Tag. Các header đó không cấp quyền.
- Không overwrite Cache-Control mặc định vì bài không có static asset cần cache public.
- Nếu thêm custom error handler, vẫn phải test output headers trong SecurityWebFilterChain.

### 7.5. SecurityConfig.java

~~~java
package example.headers;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy;
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER").build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN").build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    EndpointHeadersWriter endpointHeadersWriter() {
        return new EndpointHeadersWriter();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            EndpointHeadersWriter endpointWriter) {

        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public/ping", "/ui/help")
                                .permitAll()
                        .pathMatchers("/api/admin/**")
                                .hasRole("ADMIN")
                        .pathMatchers("/api/**")
                                .authenticated()
                        .anyExchange().denyAll())
                .headers(headers -> headers
                        .hsts(hsts -> hsts
                                .maxAge(Duration.ofDays(30))
                                .includeSubdomains(false)
                                .preload(false))
                        .frameOptions(frame -> frame
                                .mode(
                                    XFrameOptionsServerHttpHeadersWriter
                                            .Mode.DENY))
                        .referrerPolicy(referrer -> referrer
                                .policy(ReferrerPolicy.NO_REFERRER))
                        .writer(endpointWriter))
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Đọc cấu hình đúng:**

1. authorizeExchange xử lý quyền URL; rule admin đứng trước /api/**.
2. HeaderSpec được thêm **không gọi disable()**, nên no-sniff và cache baseline tiếp tục được cung cấp.
3. HSTS maxAge 30 ngày, không includeSubDomains/preload; chỉ được phát khi request đã được nhìn nhận là secure.
4. X-Frame-Options DENY và CSP frame-ancestors none thống nhất.
5. Referrer-Policy no-referrer được cấu hình rõ để giảm rò URL.
6. EndpointHeadersWriter áp dụng các giá trị CSP/Permissions-Policy riêng.
7. HTTP Basic tạo 401 cho thiếu/sai credential; role thiếu tạo 403, và cả hai cần được test header.
8. Demo chỉ có GET, không tắt CSRF; khi thêm POST cần kiểm tra CSRF theo mô hình credential.

### 7.6. Endpoints.java

~~~java
package example.headers;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class Endpoints {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping(value = "/ui/help",
            produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> help() {
        return Mono.just(
                "<!doctype html><html lang=\"vi\">"
                + "<head><title>Trợ giúp</title></head>"
                + "<body><h1>Trợ giúp</h1></body></html>");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.map(p -> Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

HTML help không chứa script hay CSS inline, vì vậy HELP_CSP không phá chức năng hiện có. Nếu thêm script, hãy đánh giá script-src, connect-src và nonce/hash thay vì nới wildcard không kiểm soát.

### 7.7. Chạy

~~~bash
gradle bootRun
~~~

Yêu cầu JDK 17+, Gradle tương thích và Maven Central. Mặc định server ở **http://localhost:8080**. Đây là HTTP local; không kỳ vọng HSTS tại cổng đó. Để chứng minh HSTS trong production cần xem response trên public HTTPS edge.

## 8. Kiểm tra header bằng curl thay vì chỉ tin cấu hình

### 8.1. Gọi GET và in response headers

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Hoặc in headers nhưng bỏ body của **GET**:

~~~bash
curl -sS -D - -o /dev/null \
  http://localhost:8080/public/ping
~~~

Không lấy kết quả từ **curl -I** làm bằng chứng đầy đủ của GET, vì -I gửi HEAD. GET/HEAD có thể đi qua authorization/mapping khác nhau.

Kết quả chính dự kiến trên HTTP local:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

Các header Date, Content-Length, Transfer-Encoding và thứ tự có thể khác; đây là ví dụ các giá trị cần kiểm tra, không phải output được chép từ server đã chạy.

### 8.2. GET trang HTML

~~~bash
curl -sS -D - -o /dev/null \
  http://localhost:8080/ui/help
~~~

Kỳ vọng:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Frame-Options: DENY
Content-Security-Policy: default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
~~~

Content-Type có thể thêm charset=UTF-8; hãy so sánh media type, không nhất thiết từng byte. Trang HTML nhận **CSP khác** với JSON, đây là điểm cần chứng minh.

### 8.3. API chưa đăng nhập: 401 và header phải còn

~~~bash
curl -sS -D - -o /dev/null \
  http://localhost:8080/api/me
~~~

Kỳ vọng **401**, WWW-Authenticate: Basic với realm do framework đặt, và các header:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Robots-Tag: noindex, nofollow
~~~

**Không hard-code giá trị realm mặc định** của Basic challenge như một hợp đồng dài hạn nếu chưa cấu hình cụ thể. Kiểm tra WWW-Authenticate có scheme đúng, status đúng và header CSP API vẫn có trên 401.

### 8.4. API đăng nhập đúng: 200

~~~bash
curl -sS -D - -o /dev/null \
  -u reader:reader-pass \
  http://localhost:8080/api/me
~~~

Kỳ vọng 200, CSP API, no-store, no-sniff, Permissions-Policy. Body của một request GET có xác thực hợp lệ:

~~~json
{"username":"reader"}
~~~

### 8.5. Người dùng thiếu quyền: 403

~~~bash
curl -sS -D - -o /dev/null \
  -u reader:reader-pass \
  http://localhost:8080/api/admin/report
~~~

Kỳ vọng **403 Forbidden** và các header CSP API, no-store, no-sniff, Permissions-Policy. Nếu chỉ set CSP trong Controller, nhánh 403 này có thể bỏ sót header; writer trong security chain cùng các test sẽ phát hiện.

### 8.6. Admin đủ quyền: 200

~~~bash
curl -sS -D - -o /dev/null \
  -u admin:admin-pass \
  http://localhost:8080/api/admin/report
~~~

Kỳ vọng 200 với body:

~~~json
{"report":"ok"}
~~~

### 8.7. Không log bí mật khi xác minh

Các ví dụ dùng mật khẩu demo, không dùng tài khoản thật. Khi curl -v hoặc trace request, có thể lộ Authorization, Cookie, Set-Cookie và token. Không gửi output chứa các giá trị đó lên chat/ticket hay log công khai. Hãy chỉ ghi lại **status, tên header, profile và kết quả match/mismatch**, không đưa raw credential vào báo cáo.

Trên PowerShell, dùng **curl.exe**; câu lệnh có dấu backslash tiếp dòng ở trên là dành cho Bash.

## 9. Kiểm thử HTTP thực tế bằng WebTestClient

**Cần test status lẫn header**, vì một request chưa đăng nhập có thể bị SecurityWebFilterChain từ chối trước khi controller chạy.

Tệp **src/test/java/example/headers/HeaderPolicyTest.java**:

~~~java
package example.headers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HeaderPolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointHasBaselineAndApiCsp() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff")
                .expectHeader().valueEquals(
                        "X-Frame-Options", "DENY")
                .expectHeader().valueEquals(
                        "Referrer-Policy", "no-referrer")
                .expectHeader().value(HttpHeaders.CACHE_CONTROL,
                        v -> assertTrue(v.contains("no-store")))
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void htmlEndpointHasDifferentCsp() {
        client.get().uri("/ui/help")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML)
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.HELP_CSP);
    }

    @Test
    void unauthorizedResponseStillHasHeaders() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE)
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "Permissions-Policy",
                        EndpointHeadersWriter.API_PERMISSIONS)
                .expectHeader().value(
                        HttpHeaders.CACHE_CONTROL,
                        v -> assertTrue(v.contains("no-store")));
    }

    @Test
    void authenticatedResponseHasApiHeaders() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth(
                        "reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "X-Robots-Tag", "noindex, nofollow")
                .expectBody()
                .jsonPath("$.username").isEqualTo("reader");
    }

    @Test
    void forbiddenResponseStillHasHeaders() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth(
                        "reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectHeader().valueEquals(
                        "Permissions-Policy",
                        EndpointHeadersWriter.API_PERMISSIONS);
    }

    @Test
    void adminGets200WithSamePolicy() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP)
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }

    @Test
    void unlistedUrlIsDeniedWithFallbackCsp() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth(
                        "reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().valueEquals(
                        "Content-Security-Policy",
                        EndpointHeadersWriter.API_CSP);
    }

    @Test
    void localHttpHasNoHstsHeader() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().doesNotExist(
                        HttpHeaders.STRICT_TRANSPORT_SECURITY);
    }

    @Test
    void responseDoesNotAccidentallyDuplicateCsp() {
        EntityExchangeResult<byte[]> result =
                client.get().uri("/public/ping")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody()
                        .returnResult();

        assertEquals(1, result.getResponseHeaders()
                .getOrEmpty("Content-Security-Policy").size());
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kết quả dự kiến:** 9 test trong HeaderPolicyTest PASS nếu code, JDK và dependencies được chuẩn bị đúng. Đây là dự đoán từ cấu hình đã viết, **không phải log thực nghiệm**.

### 9.1. Vì sao cần test 401/403?

Request 401 có thể không đi qua controller; 403 có thể do authorization hoặc CSRF filter. Nếu header chỉ được set bởi method xử lý thành công, response lỗi dễ bị thiếu chính sách. WebTestClient đi qua WebFilters và đo chính xác headers mà test server nhận, giúp bắt regression ở error pipeline.

### 9.2. Vì sao đếm số header CSP?

Nếu cả gateway lẫn ứng dụng thêm CSP, browser có thể áp dụng nhiều policies và làm hỏng giao diện. Đếm header trong tích hợp app giúp phát hiện lỗi trong ứng dụng, **nhưng vẫn phải xem response tại public edge** vì proxy/CDN có thể thêm header sau đó.

### 9.3. Vì sao kiểm tra no-store thay vì nguyên chuỗi Cache-Control?

Cache-Control chứa nhiều directives, thứ tự của các directives có thể bị chuẩn hóa. Điều kiện nghiệp vụ quan trọng là **no-store có mặt ở dữ liệu riêng**. Nếu yêu cầu tuân thủ phải chính xác hơn, dùng parser kiểm tra từng directive thay vì chỉ so substring thiếu ngữ cảnh.

## 10. Test HSTS bằng MockServerWebExchange

Demo chạy cổng local HTTP, nên **không thể xác nhận HSTS secure branch chỉ bằng curl HTTP localhost**. Test writer chuẩn với MockServerWebExchange cho hai schemes là cách kiểm tra đơn vị có giá trị.

Tệp **src/test/java/example/headers/HstsWriterTest.java**:

~~~java
package example.headers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.header.StrictTransportSecurityServerHttpHeadersWriter;
import reactor.test.StepVerifier;

class HstsWriterTest {

    private StrictTransportSecurityServerHttpHeadersWriter writer() {
        StrictTransportSecurityServerHttpHeadersWriter hsts =
                new StrictTransportSecurityServerHttpHeadersWriter();
        hsts.setMaxAge(Duration.ofDays(30));
        hsts.setIncludeSubDomains(false);
        hsts.setPreload(false);
        return hsts;
    }

    @Test
    void writesHstsOnHttpsOnly() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get(
                                "https://api.example.org/api/me"));

        StepVerifier.create(writer().writeHttpHeaders(exchange))
                .verifyComplete();

        assertEquals("max-age=2592000",
                exchange.getResponse().getHeaders()
                        .getFirst(
                                HttpHeaders.STRICT_TRANSPORT_SECURITY));
    }

    @Test
    void doesNotWriteHstsOnHttp() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get(
                                "http://api.example.org/api/me"));

        StepVerifier.create(writer().writeHttpHeaders(exchange))
                .verifyComplete();

        assertNull(exchange.getResponse().getHeaders()
                .getFirst(HttpHeaders.STRICT_TRANSPORT_SECURITY));
    }
}
~~~

Khi chạy toàn project bằng gradle test, dự kiến **11 test PASS** (9 kiểm thử HTTP và 2 kiểm thử HSTS writer). Test MockExchange chứng minh **logic writer chuẩn**, không chứng minh proxy production đã phát HSTS. Một bài kiểm tra end-to-end phải đi qua **TLS public URL**.

### 10.1. Kiểm tra HTTPS thực qua proxy

Giả sử tổ chức đã triển khai domain thật và có chứng chỉ TLS hợp lệ:

~~~bash
curl -sS -D - -o /dev/null \
  https://api.example.org/api/me
~~~

Đổi api.example.org thành hostname dịch vụ thực của bạn. Kỳ vọng nhận Strict-Transport-Security với max-age như deployment và các security headers khác. Đừng dùng **curl -k** để bỏ qua xác minh chứng chỉ trong bài test production.

Nếu 401 xuất hiện do thiếu credential, vẫn cần kiểm tra HSTS, cache no-store, nosniff, CSP; nếu chỉ thử 200 thì chưa bao quát security entry point. Thử cả 403 với tài khoản hợp lệ thiếu role và 200 với account test có quyền.

## 11. Kiểm tra giá trị cuối cùng sau gateway, CDN và browser

**Đường đi của response:**

~~~text
WebFlux SecurityWebFilterChain
        |
        v
Controller/RouterFunction
        |
        v
Spring HTTP response
        |
        v
Ingress / NGINX / API gateway / WAF / CDN
        |
        v
Browser nhận security response headers
~~~

Các tầng ở giữa có thể:

- Thêm HSTS ở edge và loại bỏ giá trị từ backend.
- Ghi đè hoặc xóa Cache-Control.
- Tự thêm CSP hoặc X-Frame-Options, tạo policies mâu thuẫn.
- Thêm/chỉnh headers cho status 200 nhưng thiếu trên 4xx/5xx.
- Rewrite Location thành http thay vì https.
- Thay đổi Content-Type, Vary, CORS hoặc Set-Cookie.

Để biết giá trị **thực tế**:

1. Xem headers ở cổng app nội bộ nếu có quyền.
2. Xem headers qua URL public HTTPS và proxy.
3. So sánh đủ 200/401/403 cùng các path HTML/JSON.
4. Kiểm tra giá trị **không bị duplicate**, đặc biệt CSP, HSTS và Access-Control-Allow-Origin.
5. Với dữ liệu cá nhân, kiểm tra Cache-Control, Pragma và Expires trên response thực.
6. Kiểm tra Location của redirect, cookie Secure/HttpOnly/SameSite khi có session.
7. Dùng DevTools Network/Console để xem CSP violations và browser behavior thực.
8. Nếu có cache/CDN, kiểm tra Vary/TTL và thử bypass cache khi debug.

**Không lấy screenshot của source config làm bằng chứng đủ.** Một chứng cứ tốt gồm URL, HTTP method, status, header names/values đã lọc dữ liệu nhạy cảm, môi trường và proxy route được kiểm tra.

### 11.1. HTML có script thực và CSP

Nếu ứng dụng dùng SPA với script từ self hoặc CDN đã phê duyệt:

- Audit network và xác định script-src, connect-src, img-src, font-src, style-src đúng.
- Dùng CSP Report-Only ở staging để phân tích violation trước khi enforcement.
- Ưu tiên nonce/hash phù hợp cho inline script hợp lệ, không mở unsafe-inline bừa bãi.
- Không kết luận CSP giải quyết mọi XSS: vẫn cần escaping, sanitization và kiểm tra dữ liệu.
- Không phản chiếu hostname/origin do attacker chọn vào CSP hoặc frame-ancestors.

### 11.2. Static assets và download khác JSON API

File tĩnh content-hash có thể được cache công khai lâu, nhưng chỉ khi không có dữ liệu nhạy cảm; tránh override toàn ứng dụng. Endpoint tải file cần Content-Type đúng, Content-Disposition với filename đã sanitize/encode, no-sniff và cache policy theo quyền truy cập. File nhận từ user có thể cần scanning/attachment thay vì inline. Không chèn filename chưa làm sạch vào response headers.

### 11.3. Login, logout và 401/403

- HTTP Basic 401 cần **WWW-Authenticate** đúng scheme; custom header writer không được xóa challenge đó.
- User đã login thiếu role thường nhận 403; giữ header bảo vệ trên error response.
- Form login chưa login có thể trả redirect 302, không nhất thiết là 401; header và Location vẫn cần kiểm tra.
- Logout có thể cần Clear-Site-Data chỉ trên endpoint có chủ đích và khi threat model phù hợp; không gắn Clear-Site-Data mọi response.
- Lỗi 5xx của proxy có thể không đi qua SecurityWebFilterChain; cần test thêm tại gateway.
- CSP frame-ancestors không đồng nghĩa CORS; Referrer-Policy không đồng nghĩa CSRF.

## 12. Lỗi thường gặp và cách xử lý

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| headers.disable() chỉ để thêm CSP | Mất security defaults | Thêm headers.writer, giữ baseline |
| Chỉ set header ở Controller | 401/403 thiếu CSP/cache | ServerHttpHeadersWriter trong SecurityWebFilterChain |
| HSTS trên HTTP localhost không thấy rồi cho là bug | Nhầm secure với insecure | Mock HTTPS writer và test public HTTPS |
| Tin X-Forwarded-Proto từ client Internet | Giả mạo scheme/trust | Edge strip/overwrite và trusted proxy |
| Bật preload/includeSubDomains khi chưa audit TLS | Có thể gây hỏng truy cập subdomain | Rollout có kiểm soát |
| CSP default-src * và unsafe-inline | Giảm hiệu lực chống XSS | CSP tối thiểu và nonce/hash |
| CSP frame-ancestors khác X-Frame-Options | Policy nhúng mâu thuẫn | Test clickjacking cả browser hiện đại/cũ |
| Cache public trên /api/me | Rò dữ liệu do cache | no-store và kiểm tra CDN |
| Chỉ check Content-Type, bỏ nosniff | Có thể tăng rủi ro MIME confusion | Test cả Content-Type và nosniff |
| Permissions-Policy bị hiểu là role | Bỏ qua authorization | hasRole/hasAuthority và kiểm tra owner |
| X-Robots-Tag bị hiểu là chặn hacker | Dữ liệu có thể vẫn truy cập | Authentication/authorization thực |
| Header bị duplicate ở gateway | Browser policy không như dự kiến | Một policy owner, test tại edge |
| Dùng curl -I để xác nhận GET | HEAD có thể khác GET | curl -D - -o /dev/null với GET |
| Lấy Origin/Host từ request ghép vào CSP | Policy injection hoặc bypass | Server-controlled constants/allowlist |
| Tắt CSRF vì POST bị 403 | Mở rủi ro browser credential | Test CSRF riêng với method unsafe |
| Thấy CSP trên 200 rồi thôi | Không kiểm tra error pipeline | Test 200, 401, 403 và 5xx khi thích hợp |
| Ghi Authorization/cookie khi debug | Rò credential | Mask log, dùng fixture |
| Thay đổi path mà không đổi matcher writer | Header profile sai | Test path cuối sau nesting/rewrite |

### 12.1. Khi có nhiều SecurityWebFilterChain

Nếu app chia chain API và browser, kiểm tra securityMatcher và @Order: một request chỉ được xử lý bởi chain phù hợp, không tự nhận header writers của tất cả chains. Dù một chain được phép public, vẫn cần baseline headers riêng nếu nó không qua cấu hình chung.

### 12.2. ServerWebExchangeDelegatingServerHttpHeadersWriter

Spring Security còn có **ServerWebExchangeDelegatingServerHttpHeadersWriter**, cho phép chạy một writer khi **ServerWebExchangeMatcher** match:

~~~java
new ServerWebExchangeDelegatingServerHttpHeadersWriter(
        matcher, delegateWriter);
~~~

Đây là snippet minh họa API, **matcher/delegateWriter phải được tạo** trong ứng dụng; không phải hai biến có sẵn từ dự án mẫu. Với nhiều path có policy khác nhau, matcher-based delegation có thể gọn hơn một writer if/else dài. Dù dùng cách nào, phải test đúng path/method và giữ các headers baseline.

## 13. Checklist review, staging và production

1. Liệt kê chính xác **method/path**, loại nội dung HTML/JSON/download và chain security thực.
2. Đảm bảo HeaderSpec không tắt các mặc định hữu ích.
3. CSP phù hợp từng endpoint, không có wildcard vô cớ.
4. X-Frame-Options và CSP frame-ancestors nhất quán.
5. Referrer-Policy là giá trị đã được phê duyệt.
6. Dữ liệu cá nhân/response lỗi có Cache-Control no-store.
7. no-sniff và Content-Type đúng.
8. API có Permissions-Policy chỉ là browser policy, không thay quyền.
9. Header values không được tạo bằng input không tin cậy.
10. HSTS trên HTTPS thật, đúng max-age và phạm vi subdomain.
11. Reverse proxy headers chỉ được tin sau khi proxy strip/overwrite.
12. Kiểm tra HTTP→HTTPS redirect/Location khi triển khai.
13. Test **GET thật**, không nhầm HEAD.
14. Test 200, 401, 403 và 404/5xx ở gateway nếu cần.
15. Kiểm tra duplicate CSP, HSTS, ACAO ở edge.
16. Kiểm tra CORS/CSRF nếu frontend có cookie/credential cross-origin.
17. Kiểm tra static assets cache khác dữ liệu riêng, không mất Vary.
18. Kiểm tra session cookie flags khi có form login.
19. Không đưa secret/session ID/Authorization vào ticket/log.
20. Có rollback cho CSP/HSTS và quan sát CSP violation sau deploy.

## 14. Bài tập tự đánh giá

1. Vì sao có CSP trong source config chưa chứng minh browser nhận CSP?
2. Header nào thường có sẵn từ Spring Security WebFlux? Header nào cần cân nhắc tự bật?
3. Tại sao không nên dùng headers.disable() khi chỉ muốn thêm một policy?
4. ServerHttpHeadersWriter trả kiểu gì và vì sao không tự subscribe?
5. Nếu /ui/help hiển thị HTML nhưng /api/me trả JSON, CSP của hai endpoint nên giống hoàn toàn không?
6. Vì sao X-Frame-Options DENY cần nhất quán với frame-ancestors none?
7. Khi user thiếu Basic credential, header writer có nên được kiểm tra ở response 401 không?
8. Khi reader thiếu ROLE_ADMIN nhận 403, làm sao biết CSP có thực sự tồn tại?
9. Vì sao HSTS không nên phát trên HTTP?
10. Khi server đứng sau HTTPS reverse proxy, cần kiểm tra X-Forwarded-Proto theo trust boundary thế nào?
11. includeSubDomains/preload có tác động gì với host chưa hỗ trợ HTTPS?
12. Vì sao curl -I không thay thế test GET?
13. Cache-Control no-store có nghĩa là user không cần login nữa không?
14. Vì sao X-Robots-Tag và Permissions-Policy không thay authorization?
15. Nếu một CDN thêm CSP nữa, browser có thể xử lý ra sao?
16. Tại sao cần kiểm tra header ở public edge thay vì chỉ ở localhost?
17. Khi response 200 có CSP đúng nhưng 401 không có, nên sửa policy ở đâu?
18. Một file có content hash và công khai có thể dùng cache dài không? Điều kiện là gì?

**Đáp án gợi ý:** (1) proxy/filters/error handlers có thể sửa; (2) cache/no-sniff/frame/HSTS secure mặc định, CSP do app chọn; (3) mất baseline; (4) Mono<Void> do framework subscribe; (5) khác theo tài nguyên cần tải; (6) bảo vệ clickjacking không mâu thuẫn; (7) có; (8) WebTestClient hoặc curl status + response headers; (9) HSTS chỉ được browser tin qua HTTPS; (10) chỉ tin proxy đã kiểm soát; (11) có thể làm subdomains HTTP-only không truy cập được; (12) HEAD có semantics khác GET; (13) không; (14) browser/crawler policy khác user quyền; (15) nhiều policies có thể đồng thời áp dụng/mâu thuẫn; (16) edge là response cuối; (17) bổ sung trong security header writer hoặc edge policy chuẩn; (18) có, nếu không nhạy cảm và URL immutable/hash đúng.

## 15. Tài liệu tham khảo

- Spring Security 6.5 — WebFlux Security HTTP Response Headers: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security 6.5 — ServerHttpSecurity.HeaderSpec Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html
- Spring Security 6.5 — ServerHttpHeadersWriter Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/ServerHttpHeadersWriter.html
- Spring Security 6.5 — StrictTransportSecurityServerHttpHeadersWriter: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/StrictTransportSecurityServerHttpHeadersWriter.html
- Spring Security 6.5 — ServerWebExchangeDelegatingServerHttpHeadersWriter: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/header/ServerWebExchangeDelegatingServerHttpHeadersWriter.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- MDN — HTTP Strict Transport Security: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security
- MDN — Content Security Policy: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- MDN — Cache-Control: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
- OWASP — HTTP Headers Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html

**Kết luận:** Để tùy chỉnh headers theo điểm truy cập trong Spring Security Reactive, giữ **baseline headers của ServerHttpSecurity**, thêm **ServerHttpHeadersWriter** có điều kiện path/response type, xác định CSP/cache/clickjacking policy rõ ràng và test response HTTP thật ở **200/401/403**. **HSTS là chính sách HTTPS theo host**, phải được kiểm tra ở public TLS edge sau proxy, không chỉ bằng HTTP localhost. WebTestClient, mock HTTPS writer, curl và DevTools kết hợp sẽ chứng minh header đã đến nơi đúng giá trị.