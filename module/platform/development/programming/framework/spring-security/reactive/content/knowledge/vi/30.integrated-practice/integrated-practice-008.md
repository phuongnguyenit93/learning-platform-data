# Tách chuỗi bảo mật cho giao diện web, API và điểm quản trị trong Spring Security Reactive

## 1. Mục tiêu của bài thực hành tổng hợp

Một ứng dụng Spring WebFlux thường phục vụ đồng thời nhiều nhóm truy cập: trang web cho người dùng, API cho ứng dụng máy khách và các endpoint vận hành dành cho quản trị viên. Ba nhóm có yêu cầu khác nhau về cơ chế đăng nhập, CSRF, session, quyền hạn, phản hồi lỗi và giám sát. Dùng một chính sách cho mọi URL dễ dẫn đến các lỗi như API tự chuyển hướng về trang login, trang quản trị vô tình chấp nhận cookie đăng nhập của người dùng phổ thông hoặc vô hiệu hóa CSRF cho toàn bộ website.

Bài này xây dựng cấu hình **nhiều SecurityWebFilterChain** với Spring Security WebFlux, Java 17+ và Spring Boot 3.x/Spring Security 6.x, tập trung vào:

1. Tách một chuỗi cho **/admin/**, một chuỗi cho **/api/**, một chuỗi cho **giao diện web**, và một chuỗi dự phòng **từ chối mặc định**.
2. Điều khiển thứ tự bằng **@Order** và phạm vi bằng **securityMatcher**.
3. Phân biệt **chọn filter chain** với **kiểm tra quyền của request trong filter chain**.
4. Thiết kế session/CSRF và cách trả 401, 403, 302 phù hợp từng nhóm.
5. Test các điểm giao nhau, ngăn việc dùng cơ chế xác thực của nhóm này để đi nhầm vào nhóm khác.

Mã nguồn bên dưới là ví dụ cấu hình và endpoint của **một ứng dụng Spring Boot WebFlux**; các tệp Java có tên/lệnh build cụ thể. Phần JWT cần một Identity Provider/ReactiveJwtDecoder thật trong triển khai; tài khoản in-memory ở profile local chỉ phục vụ học và test. Không đem mật khẩu mẫu hoặc cơ chế HTTP Basic dành cho quản trị vào production mà không đánh giá MFA và chính sách bảo vệ bổ sung.

## 2. Kiến trúc ứng dụng và ma trận chính sách

Giả sử cùng một dịch vụ WebFlux có các route sau:

| Nhóm | URL điển hình | Xác thực | Quyền | CSRF | Lưu Authentication |
| --- | --- | --- | --- | --- | --- |
| Trang công khai | GET /web/public/info | Không bắt buộc | permitAll | Bật theo chuỗi web, GET không cần token | Có thể dùng WebSession cho phần web |
| Trang cá nhân | GET /web/home | Form login, cookie session | ROLE_USER | Bật | WebSession |
| Thao tác trên web | POST /web/actions | Form login, cookie session | ROLE_USER | Bắt buộc token | WebSession |
| API công khai | GET /api/public/ping | Không bắt buộc | permitAll | Tắt nếu chỉ dùng bearer header và không dựa cookie | Không lưu auth vào session |
| API đọc/ghi | GET/POST /api/orders | JWT bearer | SCOPE_orders.read / SCOPE_orders.write | Tắt trong API stateless dùng bearer header | Không lưu auth vào session |
| Quản trị | GET /admin/status | HTTP Basic trong demo | ROLE_ADMIN | Bật | Không lưu auth vào session |
| Thao tác quản trị | POST /admin/reindex | HTTP Basic trong demo | ROLE_ADMIN | Bắt buộc token | Không lưu auth vào session |
| Khác | /unknown, /internal, /debug | Không cấp quyền | denyAll | Không phụ thuộc | Không nhận quyền từ nhóm khác |

**Quy tắc phân loại:** URL quản trị là tài nguyên đặc quyền. Không vì route được đặt tên /api/admin/** hoặc /web/admin/** mà mặc nhiên áp dụng chuỗi /admin/**. Đường dẫn thực tế, thứ tự matcher và quyền trong chuỗi phải được kiểm soát nhất quán. Cùng một chức năng quản trị không nên xuất hiện thêm dưới endpoint phổ thông thiếu kiểm tra quyền.

Chúng ta chọn:
- Chuỗi **ADMIN** ưu tiên 1: /admin/**, HTTP Basic chỉ để minh họa rõ sự khác biệt cơ chế, yêu cầu ROLE_ADMIN. CSRF vẫn bật do Basic credentials có thể được trình duyệt gửi tự động.
- Chuỗi **API** ưu tiên 2: /api/**, JWT bearer, theo scope, tắt CSRF **chỉ khi API không xác thực bằng cookie hoặc credential tự động được gửi bởi browser**.
- Chuỗi **WEB** ưu tiên 3: /web/**, /login, /logout, /assets/**, form login và CSRF; không mở HTTP Basic cho nhóm này.
- Chuỗi **FALLBACK** ưu tiên 4: mọi request còn lại, từ chối bằng denyAll.

**Điều kiện quan trọng:** HTTP Basic + ROLE_ADMIN **không tương đương MFA**. Đây là cơ chế test cục bộ để biểu diễn một chính sách độc lập; giao diện quản trị sản xuất nên dùng OIDC/SSO với MFA hoặc xác thực mạnh phù hợp, kiểm soát truy cập mạng và audit. Khi thay cơ chế quản trị, vẫn giữ nguyên tư duy tách matcher, quyền, session/CSRF và test.

## 3. SecurityWebFilterChain được chọn như thế nào?

Một request đến ứng dụng WebFlux sẽ được Spring Security chọn **một SecurityWebFilterChain phù hợp** theo thứ tự xét. Các chuỗi không tự động cộng gộp filter hoặc kế thừa policy từ chuỗi có thứ tự sau. Spring Security xét matcher của chuỗi ưu tiên cao trước; chuỗi đầu tiên khớp được sử dụng.

Có hai cấp matcher khác nhau:

**Cấp 1 — securityMatcher:** quyết định chuỗi bảo mật nào xử lý request. Ví dụ một chain có securityMatcher cho /api/** sẽ không xử lý /web/home.

**Cấp 2 — authorizeExchange:** bên trong chain đã chọn, áp các quyền khác nhau cho các method/route. Ví dụ GET /api/orders cần SCOPE_orders.read, POST /api/orders cần SCOPE_orders.write.

Một ví dụ dễ nhầm:

~~~java
// Chỉ thuộc chain API, KHÔNG bảo vệ các route nằm ngoài /api/**.
http.securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/public/**").permitAll()
        .anyExchange().authenticated());
~~~

Nếu không có chain khác bao phủ /admin/** thì matcher API không giúp bảo vệ /admin/**. Tương tự, đặt một chain bắt mọi request ở @Order(1) khiến các chain /api/** và /admin/** nằm sau không bao giờ được xét. Do đó fallback phải có thứ tự thấp nhất và nên denyAll mặc định.

**Không nhầm với Spring MVC/Servlet:** WebFlux sử dụng ServerHttpSecurity, SecurityWebFilterChain, ServerWebExchangeMatcher. Trong Servlet dùng HttpSecurity, SecurityFilterChain, RequestMatcher. Không copy ví dụ servlet rồi đổi tên import từng lớp.

## 4. Tạo project và phụ thuộc tối thiểu

Tạo project Spring Boot WebFlux (Java 17+) với các dependency:
- spring-boot-starter-webflux
- spring-boot-starter-security
- spring-boot-starter-oauth2-resource-server
- spring-boot-starter-test
- spring-security-test

Phần pom.xml dưới đây là **khối dependencies**, giả định project đã có parent/BOM Spring Boot tương thích; không phải toàn bộ POM độc lập:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dùng Gradle, thêm các starter runtime tương ứng bằng implementation(...), test dependencies bằng testImplementation(...) và quản lý version theo Spring Boot plugin/BOM. Tránh override các phiên bản Spring Security, Framework, Reactor và Netty tùy ý.

Đây là Spring Boot main class trong src/main/java/example/split/SplitSecurityApplication.java:

~~~java
package example.split;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SplitSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(SplitSecurityApplication.class, args);
    }
}
~~~

**Yêu cầu với API JWT:** Tại môi trường triển khai, cung cấp spring.security.oauth2.resourceserver.jwt.issuer-uri trỏ đến nhà phát hành token tin cậy, hoặc cung cấp ReactiveJwtDecoder phù hợp. Với issuer-uri, decoder phải xác minh chữ ký và claims theo cấu hình; một resource server không tự sinh bearer token. Một token tự đặt chuỗi tùy ý không trở thành JWT hợp lệ.

Không đưa issuer, client secret hay JWT signing key vào code bài học để “làm cho chạy”. Phần integration test sau dùng mockJwt() nhằm kiểm tra quyền mà không đòi Identity Provider thật; test token thật cần môi trường chuyên biệt có khóa và nhà phát hành được kiểm soát.

## 5. Cấu hình đầy đủ bốn chain WebFlux

Tạo src/main/java/example/split/SegmentedSecurityConfig.java. Đây là class Java hoàn chỉnh về imports/khai báo; nó cần Spring Boot WebFlux, Spring Security và một cấu hình Authentication thực tế để chạy.

~~~java
package example.split;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SegmentedSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain adminChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/admin/**"))
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().hasRole("ADMIN"))
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/api/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/orders", "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST,
                                "/api/orders", "/api/orders/**")
                                .hasAuthority("SCOPE_orders.write")
                        .anyExchange().denyAll())
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(ServerWebExchangeMatchers.pathMatchers(
                        "/web/**", "/login", "/logout", "/assets/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login", "/assets/**",
                                "/web/public/**").permitAll()
                        .pathMatchers("/web/**").hasRole("USER")
                        .anyExchange().authenticated())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(4)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().denyAll())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Đọc cấu hình theo thứ tự:**

1. /admin/** được xét đầu tiên. Người dùng phải có ROLE_ADMIN và gửi Basic credentials hợp lệ cho từng request demo. NoOpServerSecurityContextRepository không lưu/tải SecurityContext qua repository session ở chain này; nó không tự vô hiệu hóa các cookie hoặc mọi cơ chế session khác của ứng dụng. CSRF vẫn bật cho request thay đổi trạng thái.
2. /api/** được xét tiếp. JWT bearer được cấu hình trong cùng chain với rule scope, NoOp repository để không dùng session login như credential của API; CSRF chỉ tắt tại đây.
3. Giao diện web dùng form login + logout, CSRF và WebSession. Login mặc định ở /login, logout mặc định ở /logout, nên cả hai đường dẫn đều phải khớp **securityMatcher của chain web**. Các tài nguyên /assets/** cũng được đưa vào đúng chain.
4. Mọi route khác dùng fallback có denyAll, tránh xuất hiện một khoảng URL được framework xử lý mà không có chain bảo mật.

**Có thể đổi thứ tự 1–3** nếu matcher thực sự rời nhau, nhưng phải giữ thứ tự rõ ràng và test. Khi matcher chồng nhau, chain đặc hiệu/đặc quyền cần đứng trước chain bao quát hơn. Không dùng cùng số @Order cho hai chain rồi phụ thuộc vào thứ tự tình cờ của bean scanning.

**Lưu ý về root path:** Nếu muốn /admin, /api hoặc /web (không có dấu / sau prefix) được phép truy cập hay redirect, phải kiểm tra hành vi PathPattern cụ thể và bổ sung matcher/route rõ ràng. Không mặc định /admin/** chắc chắn bao phủ mọi biến thể /admin trong mọi cấu hình. Với ví dụ này, fallback denyAll là kết quả bảo thủ cho những đường dẫn nằm ngoài matcher dự định.

## 6. Giải thích ba kiểu xác thực và phạm vi session

### 6.1. Giao diện web: form login, cookie và CSRF

Người dùng truy cập /web/home, SecurityWebFilterChain của web yêu cầu ROLE_USER. Nếu chưa xác thực, entry point của form login thường chuyển hướng đến /login. Form login cần gửi username, password theo contract được cấu hình; sau xác thực, Spring Security có thể lưu SecurityContext trong WebSession để request sau sử dụng lại.

- GET /login phải được phép vào web chain để trang login được tạo/hiển thị.
- POST /login phải đi đúng chain và có CSRF token hợp lệ.
- POST /logout cũng cần CSRF token khi dùng hành vi mặc định.
- Khi tạo trang login tùy chỉnh, URL hiển thị, URL xử lý login, static assets và redirect cần khớp chain. Thêm một loginPage() khác mà quên thêm path vào securityMatcher có thể gây vòng lặp 302, 404 hoặc 403.

**Browser session không phải phương pháp xác thực API** trong thiết kế này. Một cookie session của webuser không được dùng để gọi GET /api/orders; API cần bearer token và scope.

### 6.2. API: bearer JWT, không dùng cookie login

Một client API gửi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<chuoi-token-minh-hoa>
Accept: application/json
~~~

Chuỗi trong Authorization ở trên **chỉ mô tả định dạng header**, không phải token dùng được. JWT hợp lệ phải được decoder xác minh chữ ký, hạn dùng, nhà phát hành và các ràng buộc liên quan (ví dụ audience tùy chính sách). Mapper chuyển scope/authority vào GrantedAuthority. Với quy tắc ở mục 5:
- GET /api/orders cần SCOPE_orders.read.
- POST /api/orders cần SCOPE_orders.write.
- GET /api/public/ping cho anonymous theo permitAll.
- Các phương thức/URL API còn lại bị denyAll.

**Đặc biệt:** permitAll ở /api/public/** không đồng nghĩa một bearer token sai được bỏ qua. Nếu request đã gửi Authorization: Bearer không hợp lệ, authentication filter có thể trả 401 trước khi thực thi authorization. Hãy test cả public endpoint không có header và trường hợp có header sai.

**Tại sao có thể tắt CSRF ở API này?** Vì đây là API chỉ chấp nhận credential trong Authorization header được client chủ động gắn, không dùng cookie/session hoặc Basic credentials tự động được browser gửi. Nếu đổi API để xác thực bằng session cookie, refresh cookie hoặc triển khai cơ chế trình duyệt tự đính kèm credential, phải đánh giá và bảo vệ CSRF lại. Chỉ đặt “REST” trong tên route không chứng minh API miễn CSRF.

### 6.3. Điểm quản trị: quyền cao, phạm vi độc lập

Chain admin trong ví dụ dùng HTTP Basic để kiểm thử ROLE_ADMIN tách khỏi web form và API JWT:
- Không có Basic credentials: thường 401 với Basic challenge.
- Basic của tài khoản ROLE_USER: đã xác thực nhưng không đủ quyền, thường 403.
- Basic của ROLE_ADMIN: được xử lý nếu method/CSRF hợp lệ.
- Chỉ có cookie session của web: không được dùng làm credential bởi no-op security context repository trên admin chain.
- Chỉ có bearer JWT API: không được dùng để xác thực bởi chain admin trong ví dụ.

**Không dùng HTTP Basic đơn thuần như kiến trúc quản trị production.** Đối với bảng quản trị thao tác qua browser, nên ưu tiên SSO/OIDC với MFA, WebAuthn hoặc chính sách xác thực mạnh theo tổ chức; HTTPS bắt buộc, có thể yêu cầu thiết bị được quản lý, VPN/allowlist, giới hạn tài khoản đặc quyền và log kiểm toán. Thay cơ chế này cần điều chỉnh entry point, session và CSRF của riêng chain admin. Tách chain chỉ là cơ chế tổ chức policy, không tự cung cấp xác thực mạnh.

**Nuance về CSRF:** Mặc dù NoOpServerSecurityContextRepository tránh lưu Authentication trong repository session, cơ chế CSRF mặc định có thể vẫn sử dụng WebSession để lưu token. Nói “không có authentication session” chính xác hơn tuyên bố toàn bộ admin chain không thể dùng session nào. Khi browser sử dụng Basic, credential cũng có thể được tự gửi lại, vì vậy vẫn phải chống CSRF cho POST/PUT/PATCH/DELETE.

## 7. Các route minh họa để tự chạy và kiểm thử

Tạo src/main/java/example/split/DemoEndpoints.java:

~~~java
package example.split;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoEndpoints {

    @GetMapping("/web/public/info")
    public Mono<String> publicWebInfo() {
        return Mono.just("web-public");
    }

    @GetMapping("/web/home")
    public Mono<String> webHome() {
        return Mono.just("web-home");
    }

    @PostMapping("/web/actions")
    public Mono<String> webAction() {
        return Mono.just("web-action-ok");
    }

    @GetMapping("/api/public/ping")
    public Mono<String> apiPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/orders")
    public Mono<String> readOrders() {
        return Mono.just("api-orders-read");
    }

    @PostMapping("/api/orders")
    public Mono<String> writeOrders() {
        return Mono.just("api-orders-write");
    }

    @GetMapping("/admin/status")
    public Mono<String> adminStatus() {
        return Mono.just("admin-status");
    }

    @PostMapping("/admin/reindex")
    public Mono<String> adminReindex() {
        return Mono.just("admin-reindex-requested");
    }
}
~~~

Đây là controller demo chỉ trả chuỗi để quan sát phản hồi, không thao tác dữ liệu thật. Trong hệ thống thực, controller được bảo vệ ở filter chain nhưng service quan trọng vẫn nên có kiểm tra quyền nghiệp vụ/ownership/tenant. Nếu một method nghiệp vụ tương tự được gọi qua job/queue hoặc một endpoint khác, chỉ dựa vào route policy có thể chưa đủ.

Các route này có thể được bind bởi Spring WebFlux, còn SecurityWebFilterChain quyết định request có được vào controller hay không. Một GET /api/orders không thỏa scope không thể được cho phép chỉ vì controller không gọi API kiểm tra quyền trực tiếp.

## 8. Tài khoản thử nghiệm chỉ dành cho profile local

Tạo src/main/java/example/split/LocalUsers.java. Class này chỉ được khởi tạo nếu profile local được bật. Mật khẩu dưới đây là **dữ liệu giả, không được dùng trong production**:

~~~java
package example.split;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration(proxyBeanMethods = false)
@Profile("local")
public class LocalUsers {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails webUser = User.withUsername("webuser")
                .password(encoder.encode("web-only-local"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("opsadmin")
                .password(encoder.encode("admin-only-local"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(webUser, admin);
    }
}
~~~

- webuser có ROLE_USER, dùng form login web. Không được quyền vào /admin/status nếu gửi Basic credentials.
- opsadmin có ROLE_ADMIN, dùng Basic để test /admin/status. Không tự động có ROLE_USER.
- BCrypt mã hóa mật khẩu mẫu khi khởi tạo bean; nhưng **mật khẩu rõ vẫn nằm trong mã demo**. Không bật profile local trong môi trường chứa dữ liệu thật, không giữ tài khoản demo khi phát hành.

Trong production, thay bean demo bằng ReactiveUserDetailsService/ReactiveAuthenticationManager, SSO/OIDC hoặc hệ thống định danh có quản lý. Không cần tự tạo MapReactiveUserDetailsService chỉ để hỗ trợ JWT bearer, vì JWT validation đi qua decoder và Resource Server auth manager riêng.

## 9. Điểm cần cấu hình cho Resource Server JWT

Ở môi trường có nhà phát hành thật, đặt config kiểu:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/your-realm
~~~

Địa chỉ trên chỉ là **ví dụ về cấu trúc cấu hình**; phải thay bằng issuer URI thật, có metadata/JWK hợp lệ trước khi chạy. Không dùng issuer giả để kết luận Java config bị lỗi. Tùy kiểu token, hệ thống cũng có thể dùng jwk-set-uri hoặc ReactiveJwtDecoder bean riêng. Không tắt kiểm tra chữ ký, exp/nbf, issuer hoặc audience chỉ để làm bài test xanh.

Nếu issuer đưa ra authority theo scope, convention thông dụng tạo các authority SCOPE_...; ví dụ scope orders.read tương ứng SCOPE_orders.read. Tuy nhiên không phải mọi IdP đều có cùng claim; cần xem converter thực tế. Rule hasRole("ADMIN") kỳ vọng authority ROLE_ADMIN, khác với một JWT claim “admin” chưa chuyển đổi. Đừng mặc định claim role và Spring GrantedAuthority tự giống nhau.

Các yêu cầu JWT production nên được kiểm tra riêng:
1. Chữ ký, thuật toán được phép và key rotation.
2. Issuer, thời hạn exp/nbf, thời gian lệch đồng hồ.
3. Audience phù hợp API này, không chỉ issuer đúng.
4. Scope/role ánh xạ thành quyền với quy tắc tối thiểu.
5. Token loại access, tránh dùng ID token để truy cập resource.
6. Log không chứa token, Authorization header, JWK secret hoặc claims dữ liệu cá nhân.
7. Không tự chuyển token thành cookie auth trong API rồi vẫn giữ cấu hình csrf.disable() mà không đánh giá rủi ro.

## 10. Dòng request thực tế qua bốn chain

Hình dung quy trình:

~~~text
HTTP request
  |
  v
@Order(1): khớp /admin/** ?
  |-- Có --> Admin SecurityWebFilterChain --> ROLE_ADMIN, Basic, CSRF
  |
  v
@Order(2): khớp /api/** ?
  |-- Có --> API SecurityWebFilterChain --> JWT, scopes, no auth session
  |
  v
@Order(3): khớp /web/**, /login, /logout, /assets/** ?
  |-- Có --> Web SecurityWebFilterChain --> Form login, WebSession, CSRF
  |
  v
@Order(4): khớp mọi đường dẫn còn lại
  |-- Có --> denyAll
~~~

Bảng tình huống tham khảo cho cấu hình ví dụ (giả định app chạy đúng, decoder/API mock tương ứng và không có custom exception handler thay đổi status):

| Request | Danh tính | Dự kiến | Vì sao |
| --- | --- | --- | --- |
| GET /web/public/info | Không có | 200 | WEB permitAll |
| GET /web/home | Không có | 302 về /login | WEB formLogin entry point |
| GET /web/home | Session webuser | 200 | ROLE_USER |
| POST /web/actions | Session webuser, thiếu CSRF | 403 | WEB CsrfWebFilter từ chối |
| POST /web/actions | Session webuser, CSRF hợp lệ | 200 | Auth + CSRF đạt |
| GET /api/public/ping | Không có | 200 | API permitAll |
| GET /api/orders | Không có | 401 | API yêu cầu JWT |
| GET /api/orders | JWT có scope orders.read | 200 | SCOPE_orders.read |
| POST /api/orders | JWT chỉ có orders.read | 403 | Thiếu orders.write |
| POST /api/orders | JWT có orders.write | 200 | Scope phù hợp, API không dùng CSRF |
| GET /admin/status | Không có | 401 | ADMIN Basic challenge |
| GET /admin/status | Basic webuser | 403 | Không có ROLE_ADMIN |
| GET /admin/status | Basic opsadmin | 200 | Đủ role |
| POST /admin/reindex | Basic opsadmin, không có CSRF | 403 | ADMIN CSRF đang bật |
| GET /admin/status | Chỉ có web session cookie | 401 | ADMIN không tải auth từ session |
| GET /api/orders | Chỉ có web session cookie | 401 | API không tải web session |
| GET /api/orders | Basic opsadmin | 401 | API chỉ bật Resource Server JWT |
| GET /unknown | Bất kỳ | 403 hoặc deny response phù hợp | FALLBACK denyAll |

Một số mã HTTP cụ thể (đặc biệt 302/401/403) chịu ảnh hưởng entry point, exception handling và các filter bổ sung. Test dựa trên hành vi cấu hình thực chứ không coi bảng này là kết quả cam kết cho mọi phiên bản. Nếu resource đã bị router trả 404 trước security hoặc gateway đã đổi path, cần xác minh đường đi thực tế.

## 11. Kiểm thử bằng WebTestClient và spring-security-test

**Chuẩn bị test:** Spring Boot context có SegmentedSecurityConfig, DemoEndpoints, LocalUsers (profile local) và reactive decoder phù hợp. Với test chỉ tập trung vào chain/authorization, có thể định nghĩa decoder **chỉ trong test** trả lỗi với raw token, rồi dùng mockJwt() để đưa một Authentication đã mô phỏng vào pipeline. Điều này tránh kết nối IdP thật khi test route policy; test chữ ký JWT phải là bộ riêng.

Tạo src/test/java/example/split/SegmentedSecurityTest.java:

~~~java
package example.split;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ActiveProfiles("local")
@Import(SegmentedSecurityTest.TestDecoder.class)
class SegmentedSecurityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicEndpointsAreReachable() {
        client.get().uri("/web/public/info")
                .exchange().expectStatus().isOk();
        client.get().uri("/api/public/ping")
                .exchange().expectStatus().isOk();
    }

    @Test
    void protectedApiDoesNotAcceptAnonymous() {
        client.get().uri("/api/orders")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void apiReadScopeAllowsReadOnly() {
        WebTestClient apiReader = client.mutateWith(
                mockJwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read")));

        apiReader.get().uri("/api/orders")
                .exchange().expectStatus().isOk();

        apiReader.post().uri("/api/orders")
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void apiWriteScopeAllowsPostWithoutCsrf() {
        client.mutateWith(mockJwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.write")))
                .post().uri("/api/orders")
                .exchange().expectStatus().isOk();
    }

    @Test
    void webWriteRequiresCsrf() {
        client.mutateWith(mockUser("webuser").roles("USER"))
                .post().uri("/web/actions")
                .exchange().expectStatus().isForbidden();

        client.mutateWith(mockUser("webuser").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/web/actions")
                .exchange().expectStatus().isOk();
    }

    @Test
    void adminRequiresBasicCredentialAndAdminRole() {
        client.get().uri("/admin/status")
                .exchange().expectStatus().isUnauthorized();

        client.get().uri("/admin/status")
                .headers(headers ->
                        headers.setBasicAuth("webuser", "web-only-local"))
                .exchange().expectStatus().isForbidden();

        client.get().uri("/admin/status")
                .headers(headers ->
                        headers.setBasicAuth("opsadmin", "admin-only-local"))
                .exchange().expectStatus().isOk();
    }

    @Test
    void webSessionDoesNotBecomeApiCredential() {
        // No bearer header -> cannot authenticate at the API.
        // A complete session test should first login via /login,
        // capture the session cookie and send it to /api/orders.
        client.get().uri("/api/orders")
                .exchange().expectStatus().isUnauthorized();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestDecoder {
        @Bean
        ReactiveJwtDecoder jwtDecoder() {
            return token -> Mono.error(
                    new BadJwtException(
                            "Raw tokens are intentionally rejected in this test"));
        }
    }
}
~~~

Các test trên có ý nghĩa:
- Test mockJwt đặt Authentication/authority để **test authorization của endpoint**, không test tính hợp lệ chữ ký hay issuer của token thật.
- Test Basic dùng LocalUsers để kiểm tra role mà không giả lập admin bằng mockUser.
- Test webWriteRequiresCsrf minh họa CSRF hiệu lực trên chain web.
- Test webSessionDoesNotBecomeApiCredential ở đây chỉ xác nhận API từ chối request thiếu bearer. **Nó chưa mô phỏng một cookie web session thật**; để xác thực ranh giới session hoàn chỉnh, cần làm form login có CSRF, lấy Set-Cookie rồi thử gửi cookie đó sang /api/orders và /admin/status. Không tuyên bố test này đã chứng minh đầy đủ session isolation.

Nếu môi trường test đang cấu hình issuer-uri production, bỏ cấu hình issuer cho profile test hoặc điều chỉnh cấu hình để TestDecoder được chọn rõ ràng; tránh tạo hai ReactiveJwtDecoder beans không phân biệt. Nếu framework/test setup khác biệt, giữ nguyên mục tiêu test và kiểm tra docs tương ứng với phiên bản Spring Boot/Security dùng thực tế.

Chạy với Maven Wrapper:

~~~bash
./mvnw -Dtest=SegmentedSecurityTest test
~~~

Hoặc với Gradle:

~~~bash
./gradlew test --tests example.split.SegmentedSecurityTest
~~~

Windows dùng mvnw.cmd hoặc gradlew.bat. Trên hệ thống CI, cần chạy thêm test không có profile local để chứng minh demo users không được đưa vào runtime production.

## 12. Test quan trọng nhất: ranh giới giữa ba nhóm

Một test chỉ kiểm tra GET /admin/status bằng admin user là chưa đủ. Cần xác minh **các quyền không bị dùng nhầm qua nhóm**:

1. Session webuser hợp lệ đi vào /web/home; nếu đưa cùng cookie sang /api/orders hoặc /admin/status mà không có credential tương ứng, vẫn bị từ chối.
2. Basic opsadmin hợp lệ cho /admin/status nhưng **không thay JWT bearer của API**. Gửi Basic header đến /api/orders phải bị từ chối.
3. JWT có SCOPE_orders.read gọi GET /api/orders được; dùng JWT ấy để gọi /admin/status trong ví dụ Basic chain không được.
4. JWT có SCOPE_orders.read không được POST /api/orders; SCOPE_orders.write không tự suy ra SCOPE_orders.read nếu converter/issuer chỉ cấp một scope.
5. Người có ROLE_ADMIN không tự động có ROLE_USER; người dùng thường không được xem/tác động tài nguyên admin dù biết endpoint.
6. POST /web/actions và POST /admin/reindex cần CSRF hợp lệ; POST /api/orders dùng bearer header không cần CSRF theo thiết kế đã nêu.
7. /assets/** cho phép truy cập công khai nếu chỉ chứa static assets an toàn, nhưng /unknown, /debug, /actuator hoặc các route lạ không được vô tình công khai.
8. Path biên như /admin, /admin/, /admin/status/, /api, /api/, /web và các tổ hợp chữ hoa/thường phải được thử theo router/matcher thực tế.
9. Có nhiều SecurityWebFilterChain, từng route phải thực sự đi qua **một chain đúng**, không bị catch-all chọn trước.
10. Khi thay form login bằng OIDC, các URL callback/authorization phải nằm trong chain web và được bảo vệ đúng; không để fallback chặn hoặc API chain bắt nhầm.

**Chất lượng test:** Dùng cả test auth bằng cơ chế thật (form login, Basic, JWT signature/decoder với issuer thử nghiệm) và test mock để cô lập authorization. Nếu mọi test đều dùng mockUser hoặc mockJwt trên mọi route, chúng có thể bỏ qua những sai sót cấu hình authentication manager, login endpoints hoặc session persistence.

## 13. Tại sao không chỉ dùng một chain có pathMatchers?

Một chain duy nhất vẫn có thể tách authorization:

~~~java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().permitAll());
~~~

Nhưng đoạn này **không chia cơ chế xác thực, CSRF, SecurityContextRepository hoặc entry point theo nhóm**. Nếu cùng một chain bật form login và bearer auth:
- API không có token có thể nhận redirect HTML về /login thay vì 401 JSON.
- Trình duyệt có cookie session có thể được coi là authenticated ở API nếu không có policy riêng.
- Disable CSRF toàn chain để “dễ gọi API” vô tình làm yếu các form web.
- Một rule permitAll quá rộng hoặc thứ tự pathMatchers sai có thể để lộ admin.
- Khi có yêu cầu quản trị mạnh hơn, cấu hình exception handler, header policy, tenant controls và monitoring trở nên khó kiểm soát.

Nhiều chain là phù hợp khi **các nhóm có policy xác thực hoặc HTTP handling khác nhau**. Nếu toàn bộ hệ thống thật sự chỉ là một API JWT thống nhất, không cần tách chain giả tạo cho đủ số lượng. Số chain nên do phân vùng bảo mật thực tế quyết định.

## 14. CSRF: quyết định theo cách browser gửi credential

**CSRF không phải lỗi riêng của HTML form.** Nó xuất hiện khi trình duyệt tự gửi credential của nạn nhân trên request do nguồn khác kích hoạt, như session cookie hoặc HTTP Basic đã được cache. Vì vậy:

- Web form login dùng cookie session: giữ CSRF cho POST/PUT/PATCH/DELETE, kể cả login/logout.
- Admin HTTP Basic được dùng từ trình duyệt: CSRF vẫn có thể cần vì browser tự gửi credential. Trong ví dụ, bật CSRF.
- API JWT chỉ nhận Authorization header do client JavaScript/mobile/service chủ động gắn: có thể tắt CSRF cho chain API, nếu không có cookie/session/Basic tự động gửi.
- API dùng cookie session, refresh cookie hoặc credential tự động: đánh giá CSRF lại, dù endpoint trả JSON.
- CORS không tự thay thế CSRF. SameSite cookie là lớp bổ sung, không thay thế kiểm tra CSRF ở mọi mô hình.

Ví dụ lỗi cần tránh:

~~~java
// KHÔNG đặt ở một chain bắt mọi URL của ứng dụng có form/session.
http.csrf(ServerHttpSecurity.CsrfSpec::disable);
~~~

Trong cấu hình nhiều chain, chỉ API đã chứng minh không nhận credential tự động mới tắt CSRF. Web/admin vẫn bật. Nếu dùng SPA với cookie, có thể cấu hình ServerCsrfTokenRepository phù hợp và gửi token qua header; triển khai cụ thể phải tương thích với XorServerCsrfTokenRequestAttributeHandler/BREACH protection và framework client. Không đưa CSRF token vào URL, log hoặc analytics.

## 15. Authentication, Authorization và ranh giới nghiệp vụ

Mỗi chain phải trả lời ba câu hỏi độc lập:

1. **Ai đang gọi?** Form login, JWT bearer, Basic, OIDC hay hệ thống khác; credential được kiểm chứng bởi thành phần nào.
2. **Gọi được route nào?** authorizeExchange, role/authority/scope, method, policy.
3. **Gọi được tài nguyên nào bên trong route?** Ownership, tenant isolation, field-level authorization và method security/kiểm tra ở service.

Ví dụ SCOPE_orders.read không cho phép đọc mọi đơn hàng của mọi khách. Service phải giới hạn theo người dùng/tenant hoặc dùng authorization manager phù hợp. ROLE_ADMIN không nhất thiết cho phép thao tác nhạy cảm như khóa tài khoản nếu yêu cầu thêm approval hoặc step-up authentication.

Trong reactive service, nên đọc principal bằng ReactiveSecurityContextHolder hoặc truyền Actor/Principal đã được xác thực qua Mono/Flux. Không dựa ThreadLocal/SecurityContextHolder ở thread bất kỳ, không cache Authentication singleton, và không tạo WebFilter tự chèn quyền dựa vào header client chưa xác thực.

Khi có method security, dùng @EnableReactiveMethodSecurity theo phiên bản, kiểm tra quyền ở Spring-managed bean, đồng thời test rằng lời gọi nội bộ không vô tình vượt proxy method security.

## 16. Nguyên tắc cho web login và OIDC callback

Nếu UI sau này đổi sang OAuth2/OIDC login:
- Endpoint khởi động thường mang dạng /oauth2/authorization/{registrationId}.
- Redirect callback thường mang dạng /login/oauth2/code/{registrationId}.
- Login success/failure redirect có thể đi đến /web/... hoặc URL được định nghĩa rõ.
- Các đường dẫn này cần khớp securityMatcher của chain quản lý OAuth2 login và phải có xử lý callback theo cơ chế Spring Security. Không chỉ permitAll rồi hy vọng callback được xử lý.
- Với nhiều chain dùng OAuth2 login khác nhau, phải kiểm tra login/redirect URI, registrationId, session/correlation state, CSRF và handler không va chạm.
- Chỉ chấp nhận redirect URI đã đăng ký; không lấy arbitrary redirect từ query để tránh open redirect.

Một anti-pattern điển hình: webChain chỉ khớp /web/** nhưng cấu hình formLogin mặc định redirect /login, trong khi fallback denyAll. Kết quả là chưa login thì request /web/home đi đến /login nhưng route này không nằm trong web chain. Việc thêm /login và /logout vào securityMatcher ở mục 5 là quyết định **có chủ đích**, không phải permitAll toàn bộ phần còn lại.

## 17. CORS, same-origin, cookie và proxy

Nếu UI và API ở hai origin khác nhau, CORS cần được cấu hình theo origin tin cậy và method/header thực sử dụng. Chính sách CORS không thay rule xác thực; preflight OPTIONS có thể phải được xử lý đúng theo thứ tự filter và chính sách cho browser. Tránh Access-Control-Allow-Origin: * kết hợp credential cookies. Nếu UI cùng origin với API nhưng API chỉ dùng bearer header, vẫn không được tự coi session cookie là API auth.

Một số điểm vận hành:
- Cookie web: Secure, HttpOnly và SameSite theo nhu cầu login/SSO, HTTPS, thời hạn session ngắn phù hợp; không log session IDs.
- API Authorization bearer: không ghi JWT/token vào log; không để token trên query string hoặc URL.
- Reverse proxy: xác minh path mà WebFlux thấy **sau khi** gateway rewrite; securityMatcher dựa trên đường dẫn tại lớp ứng dụng, không dựa trên URL gốc tưởng tượng.
- Nếu ứng dụng nằm sau context path hoặc route prefix, kiểm tra pattern phù hợp với path thực tế sau proxy. Chỉ dùng Forwarded/X-Forwarded-* từ proxy đáng tin, không tin trực tiếp header do Internet gửi.
- Nếu hệ thống triển khai nhiều subdomain, phân biệt host/origin policy và cookie domain với path matcher; path matcher không tự bảo vệ theo hostname.
- /actuator/** có thể ở cổng hoặc management context riêng; kiểm tra thiết lập management endpoint và security độc lập, không mặc định fallback tại application port cũng bảo vệ mọi management path.

## 18. Giám sát và debug thứ tự chain

Khi endpoint có hành vi sai, lần lượt xác định:

**Triệu chứng API trả HTML 302 /login**
- Có thể API chain không khớp, web/fallback chain bắt nhầm, hoặc API đang bật formLogin/entry point không phù hợp.
- Kiểm tra path sau gateway, securityMatcher, @Order, cơ chế auth đã cấu hình.
- Test GET /api/orders thiếu token: kỳ vọng 401 trong thiết kế bearer.

**Web form login bị 403/404 hoặc vòng lặp**
- /login, POST /login hoặc /logout không thuộc web chain; CSRF token thiếu; form action sai; URL loginPage hoặc redirect không khớp.
- Kiểm tra cookie session, CSRF repository và login success URL theo môi trường.

**Admin được phép bằng web cookie**
- Có thể admin bị web catch-all chain chọn trước, hoặc dùng chung repository và rule quá rộng.
- Đối chiếu @Order, securityMatcher, entry point và chính sách xác thực riêng admin.
- Dùng test gửi chỉ cookie web đến admin, không kèm Basic/JWT hợp lệ.

**API POST trả 403 dù JWT hợp lệ**
- Có thể scope mapper không tạo SCOPE_orders.write; có thể request tới nhầm chain bật CSRF; có thể không được permit method.
- Phân biệt lỗi CSRF, authorization và signature/issuer; không tắt toàn bộ security để chữa triệu chứng.

**403 hoặc 404 ở một route chưa biết**
- Xác nhận route mapping, chain selected và fallback denyAll.
- Không biến fallback thành permitAll để “sửa nhanh” lỗi routing.

Khi debug, chỉ dùng event, route template, chain identifier do ứng dụng gắn rõ ràng, outcome và mã lỗi chuẩn hóa; không in password, cookie, raw Authorization header, ID token/JWT hoặc SecurityContext.

## 19. Đánh giá bảo mật trước khi triển khai thật

Checklist thiết kế:

- [ ] Các prefix /admin/**, /api/** và /web/** được định nghĩa rõ; không trùng tài nguyên nhạy cảm qua các route khác.
- [ ] @Order đảm bảo chuỗi đặc quyền đứng trước catch-all; fallback denyAll và có test.
- [ ] securityMatcher đúng phạm vi, authorizeExchange đúng method và role/scope; không nhầm hai tầng matcher.
- [ ] /login, /logout, callback OAuth2 và static assets có chain phù hợp khi được dùng.
- [ ] Web form login dùng session + CSRF; không tắt CSRF vì API cần JSON.
- [ ] API bearer thật sự không dùng cookie tự động; JWT decoder kiểm tra chữ ký, issuer, thời hạn, audience và scope theo yêu cầu.
- [ ] Admin có xác thực mạnh/MFA, hạn chế truy cập mạng và audit; HTTP Basic chỉ tồn tại trong demo hoặc trường hợp được đánh giá riêng.
- [ ] Không tồn tại user/password in-memory profile local trong môi trường production.
- [ ] Web session không được xác thực API/admin; Basic admin không xác thực API, JWT API không tự xác thực admin.
- [ ] Test anonymous, ROLE_USER, ROLE_ADMIN, API scope read/write, CSRF pass/fail, method không được phép, URL unknown.
- [ ] Có test integration với session cookie thật và với JWT thật, không chỉ mockUser/mockJwt.
- [ ] Các route vận hành, health, metrics, actuator và gateway rewrite được kiểm tra riêng.
- [ ] Không ghi credentials, cookie, token, dữ liệu cá nhân vào log/tracing.
- [ ] Khi nâng cấp Spring Security/Spring Boot, chạy lại test chain selection và 401/403/redirect.

## 20. Bài tập mở rộng

**Bài A — Chain bị bắt nhầm:** Đưa fallbackChain lên @Order(1), chạy test. Giải thích vì sao /api/orders không được xử lý bằng JWT chain dù bean vẫn tồn tại. Khôi phục thứ tự và chứng minh bằng test.

**Bài B — CSRF sai phạm vi:** Tạm tắt CSRF ở webChain trong môi trường test, xác minh POST /web/actions không cần token khi đã đăng nhập; giải thích vì sao thay đổi này tạo rủi ro với session cookie và khôi phục bảo vệ.

**Bài C — Cookie vượt vùng:** Đăng nhập webuser thông qua POST /login có CSRF, lấy session cookie rồi gửi đến /admin/status và /api/orders không có credential khác. Kỳ vọng bị từ chối. Nếu không, điều tra chain matcher/repository/authentication.

**Bài D — Mở route quản trị mới:** Tạo /admin/audit/export và /api/admin/audit. Cấu hình quyền chính xác cho cả hai, không dựa vào chữ admin trong path để tự động được bảo vệ. Viết test người dùng thường/token thiếu quyền không thể tải dữ liệu.

**Bài E — Thay Basic quản trị bằng OIDC:** Lập sơ đồ login, MFA, callback, session, CSRF và logout của admin riêng. Liệt kê endpoint đặc biệt cần vào securityMatcher và các trường hợp cần test; không copy nguyên cơ chế form/session phổ thông một cách thiếu chủ đích.

**Bài F — Tích hợp quản trị trên cổng riêng:** Đưa admin hoặc management endpoint vào context/port tách biệt. Xác định nơi áp chính sách firewall, load balancer, TLS và Spring Security. Đánh giá lớp bảo vệ nào có hiệu lực tại mỗi cổng.

Bài tập đều nên thực hiện ở môi trường cô lập bằng tài khoản/token giả, không dùng password hoặc token của production. Kết quả đạt là trạng thái HTTP và chính sách không bị vượt qua, không phải việc tìm được credential hợp lệ.

## 21. Tài liệu chính thức

- [Spring Security — WebFlux Security, Multiple Chains Support](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): cách chọn nhiều SecurityWebFilterChain theo @Order và matcher.
- [Spring Security — OAuth2 Resource Server WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): JWT/Opaque token và cơ chế xác thực bearer.
- [Spring Security — Cross Site Request Forgery for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF, session, login/logout và request thay đổi trạng thái.
- [Spring Security — Testing Authentication in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): WebTestClient, mockUser và reactive filter chain.
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): mockJwt, kiểm tra authorities.
- [Spring Security — Testing CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): csrf() với WebTestClient.
- [ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): securityMatcher, authorizeExchange, formLogin, oauth2ResourceServer, csrf và HTTP Basic.

**Ghi nhớ:** Một request WebFlux được chọn vào một chuỗi bảo mật theo matcher/thứ tự, rồi mới được kiểm tra quyền trong chuỗi ấy. Tách web, API và admin có ý nghĩa khi mỗi nhóm có cơ chế xác thực và quy tắc HTTP riêng. Luôn giữ chain đặc hiệu đúng ưu tiên, CSRF ở mọi giao diện dùng credential tự động, API bearer với scope rõ ràng, admin có kiểm soát quyền mạnh và fallback denyAll cho URL chưa được khai báo.
