# Lưu ngữ cảnh sau đăng nhập và đổi mã phiên để hạn chế session fixation trong Spring Security Reactive

## 1. Vấn đề cần giải quyết

Đăng nhập biểu mẫu (**form login**) trong Spring WebFlux không kết thúc ở việc kiểm tra đúng username/password. Sau khi xác thực thành công, ứng dụng web có trạng thái thường cần **ghi SecurityContext vào WebSession** để request tiếp theo nhận lại danh tính đã đăng nhập. Đồng thời, server cần **đổi mã định danh phiên (session ID)** tại ranh giới nâng mức tin cậy từ anonymous sang authenticated để hạn chế **session fixation**.

Hình dung một người dùng:

1. Mở trang \`/login\` và nhận một cookie phiên khi server cần lưu dữ liệu như CSRF token.
2. Điền tên đăng nhập và mật khẩu; trình duyệt gửi \`POST /login\` cùng cookie hiện có.
3. Server kiểm tra credential, tạo \`Authentication\` tin cậy.
4. Server **lưu \`SecurityContext\`** vào phiên và **đổi session ID**.
5. Trình duyệt dùng cookie phiên mới cho \`GET /api/me\`; server đọc lại \`SecurityContext\`, nhận ra đúng người dùng.

Nếu bước 4 bị bỏ qua hoặc triển khai sai, có thể xảy ra hai vấn đề tách biệt: **đăng nhập không được duy trì qua request**, hoặc **mã phiên mà kẻ tấn công đã biết vẫn dùng được sau khi nạn nhân đăng nhập**.

Mục tiêu bài học:

- Hiểu \`SecurityContext\`, \`Authentication\`, \`WebSession\`, cookie phiên và \`Reactor Context\`.
- Dùng **\`WebSessionServerSecurityContextRepository\`** để lưu/đọc SecurityContext qua các request.
- Nắm được chức năng **\`WebSession.changeSessionId()\`** và tại sao repository mặc định của form login thực hiện đổi ID khi save.
- Cấu hình **\`ServerHttpSecurity\`** để đường **save** của form login và đường **load** của ReactorContextWebFilter dùng đúng một repository.
- Thực hành Java 17+ với phiên bản Spring đã có bản vá bảo mật, form login mặc định, CSRF, cookie jar và kiểm thử bằng \`StepVerifier\`.
- Phân biệt session fixation với session hijacking, CSRF và XSS; biết giới hạn của biện pháp đổi ID.

**Trọng tâm:** chỉ đổi ID khi cần chưa đủ; cần đảm bảo **kết quả xác thực được lưu đúng chỗ, cookie được gửi lại đúng cách và ID cũ không còn dùng được** theo cơ chế phiên đang triển khai.

## 2. Các đối tượng trong vòng đời phiên

| Đối tượng | Nhiệm vụ | Điều không nên hiểu nhầm |
| --- | --- | --- |
| \`Authentication\` | Kết quả xác minh người dùng và authorities | Không tự tồn tại giữa mọi request |
| \`SecurityContext\` | Bao bọc \`Authentication\` | Không phải session ID |
| \`ReactiveSecurityContextHolder\` | Đọc \`SecurityContext\` từ Reactor Context ở subscription hiện tại | Không phải nơi lưu session lâu dài |
| \`ServerSecurityContextRepository\` | Hợp đồng \`load(exchange)\` và \`save(exchange, context)\` | Không phải một servlet SecurityContextRepository |
| \`WebSessionServerSecurityContextRepository\` | Lưu SecurityContext trong WebSession; khi save sẽ đổi session ID | Không tự tạo credential hoặc kiểm tra password |
| \`WebSession\` | Giữ thuộc tính session và ID ở server | Khác \`jakarta.servlet.http.HttpSession\` |
| Cookie phiên | Giúp trình duyệt gửi ID tới server ở request sau | Không được xem như mật khẩu có thể log/công khai |
| \`ReactorContextWebFilter\` | Nạp SecurityContext từ repository vào Reactor Context | Cần repo tương thích với nơi đã save |
| Form login \`AuthenticationWebFilter\` | Xác thực username/password và lưu context qua repo đã cấu hình | Không tự động mang context qua mọi request nếu chỉ dùng NoOp repository |

Một sơ đồ:

~~~text
                           ĐĂNG NHẬP LẦN ĐẦU
GET /login  ----------------> WebSession (chưa đăng nhập)
     |                                  |
     +<------ CSRF token + cookie ID S0-+
     |
POST /login, cookie S0, username/password, _csrf
     |
     v
AuthenticationWebFilter -> ReactiveAuthenticationManager
     |
     +-- sai ----------> login?error, không ghi context đã xác thực
     |
     +-- đúng ---------> Authentication(alice)
                              |
                              v
                      SecurityContext(alice)
                              |
                              v
                  WebSessionServerSecurityContextRepository.save()
                              |
                              +--> Ghi context vào WebSession
                              +--> Đổi ID S0 -> S1
                              |
                              v
                     Redirect + Set-Cookie(S1)
                              |
                           REQUEST SAU
GET /api/me, cookie S1
     |
     v
ReactorContextWebFilter -> repository.load()
     |
     v
Reactor Context -> Authentication(alice) -> Authorization -> Controller
~~~

Sơ đồ mô tả ý tưởng theo cấu hình session-based form login. Việc có session trước login hay không phụ thuộc request và các thành phần lưu CSRF/request cache; nếu **chưa từng có S0**, hệ thống vẫn có thể tạo một phiên mới khi cần. Đây không phải điều kiện tiên quyết để login thành công.

## 3. Hiểu session fixation từ nguyên nhân

**Session fixation** là tấn công trong đó kẻ tấn công tìm cách khiến nạn nhân sử dụng một **session ID mà kẻ đó đã biết hoặc có thể kiểm soát**, rồi đợi nạn nhân đăng nhập. Nếu server giữ nguyên ID ấy sau login và cho phép nó truy cập phiên đã được nâng quyền, kẻ tấn công có thể thử dùng cùng ID để mạo danh nạn nhân.

Ví dụ minh họa:

~~~text
TRƯỚC LOGIN
Kẻ tấn công biết ID = S0
Nạn nhân cũng dùng ID = S0

NẠN NHÂN LOGIN
Server lưu Authentication(alice)

THIẾT KẾ SAI
Sau login ID vẫn = S0
Kẻ tấn công thử S0 -> có nguy cơ truy cập phiên Alice

THIẾT KẾ CÓ CHỐNG FIXATION
Sau login ID đổi thành S1
ID S0 không còn là credential hợp lệ cho phiên Alice
Nạn nhân giữ S1, còn kẻ tấn công chỉ biết S0
~~~

Đổi session ID không đảm bảo chống mọi tấn công. Nó **không tự bảo vệ** khi S1 bị đánh cắp sau login qua malware, XSS, cấu hình cookie yếu, proxy log, rò URL hoặc kênh HTTP không TLS. Những rủi ro này là **session hijacking** hay các kỹ thuật chiếm phiên khác. Session fixation tập trung vào **mã phiên có thể đã bị biết từ trước thời điểm xác thực**.

Điều kiện để bảo vệ có ý nghĩa:

1. Đổi sang ID ngẫu nhiên, khó dự đoán bằng cơ chế WebSession/Session Store đáng tin.
2. ID cũ không còn ánh xạ tới phiên đã đăng nhập.
3. Trình duyệt được cập nhật cookie/session identifier mới.
4. Tất cả instance của hệ thống session chung đều hiểu việc đổi ID.
5. Cookie có thuộc tính bảo vệ phù hợp, ứng dụng dùng HTTPS và chống CSRF/XSS.
6. Khi logout/hết hạn, phiên hoặc SecurityContext được xóa đúng cách.

Không tự tạo ID từ username, timestamp hoặc \`Random\`; không gửi session ID qua query parameter để “dễ debug”.

## 4. Cơ chế mặc định của Spring Security WebFlux form login

Với **Spring Security Reactive**, \`ServerHttpSecurity.FormLoginSpec.securityContextRepository(...)\` dùng để chọn repository **lưu Authentication sau khi form login thành công**. Theo Javadoc Spring Security 6.5, mặc định của FormLoginSpec là **\`WebSessionServerSecurityContextRepository\`**.

Lớp này có mô tả API quan trọng: **khi \`SecurityContext\` được lưu, session ID được thay đổi nhằm phòng chống session fixation**. Nó triển khai \`ServerSecurityContextRepository\`, với các phương thức:

~~~java
Mono<SecurityContext> load(ServerWebExchange exchange);
Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
~~~

Trong Spring Framework, API liên quan ở mức WebSession là:

~~~java
Mono<Void> changeSessionId();
~~~

Đây là API **reactive**, không phải \`HttpServletRequest.changeSessionId()\` của Servlet. Việc gọi \`save()\` trả Mono<Void> nghĩa là tác vụ phải được **subscribe/compose** đúng cách; không được chỉ tạo publisher rồi bỏ đi.

**Lưu ý cực kỳ quan trọng:** mặc định của **lớp AuthenticationWebFilter tạo trực tiếp** lại là **\`NoOpServerSecurityContextRepository\`**. Khi dùng \`http.formLogin(...)\`, FormLoginSpec cấu hình repository cho filter form login. Nếu tự tạo AuthenticationWebFilter và chỉ gọi setAuthenticationSuccessHandler(), đừng mặc định nó sẽ lưu danh tính qua request sau. Cần cấu hình repository rõ ràng.

### 4.1. Không nhầm nơi lưu với nơi nạp

Javadoc của \`ServerHttpSecurity.securityContextRepository(repository)\` nói đây là chiến lược dùng với **ReactorContextWebFilter**; còn FormLoginSpec.securityContextRepository(...) quy định cách **filter form login lưu context sau xác thực**. Chúng có trách nhiệm khác nhau và **không phải lúc nào cũng được liên kết tự động** khi tự tùy chỉnh.

Thiết kế nhất quán:

~~~java
ServerSecurityContextRepository repository =
        new WebSessionServerSecurityContextRepository();

return http
        .securityContextRepository(repository) // LOAD trên request sau
        .formLogin(form -> form
                .securityContextRepository(repository)) // SAVE khi login
        .build();
~~~

Đoạn trên chỉ minh họa phần SecurityWebFilterChain, không phải class Java biên dịch riêng. Cùng một repository giúp tránh tình huống “login đúng nhưng request sau lại anonymous” do save và load trỏ tới hai kho khác nhau.

### 4.2. Dòng chảy tín hiệu Reactor

~~~text
POST /login
  -> authenticationManager.authenticate(...)
  -> Mono<Authentication> thành công
  -> SecurityContextImpl(authentication)
  -> repository.save(exchange, context)
  -> WebSession đổi ID khi save
  -> handler chuyển hướng/tiếp tục
  -> trình duyệt nhận cookie phiên mới

GET /api/me
  -> repository.load(exchange)
  -> Mono<SecurityContext>
  -> ReactorContextWebFilter đặt vào Reactor Context
  -> ReactiveSecurityContextHolder.getContext()
  -> Authorization và controller
~~~

Nếu \`repository.save\` bị lỗi do session store hoặc backend không khả dụng, ứng dụng **không nên coi login đã được lưu bền vững** rồi thông báo thành công một cách sai lệch. Trong luồng reactive, cần xử lý lỗi thay vì gọi subscribe() thủ công và bỏ kết quả.

## 5. Vì sao phải quan sát cả cookie lẫn SecurityContext?

Có thể có ba trạng thái khác nhau:

| Trạng thái | Điều gì đúng? | Hệ quả |
| --- | --- | --- |
| Authentication thành công chỉ trong request login | Manager đã xác minh password | Chưa chứng minh request sau sẽ có danh tính |
| SecurityContext được lưu vào WebSession | Kho session có bản ghi authentication | Request sau có thể nạp lại nếu browser gửi ID đúng |
| Session ID đã đổi và cookie mới được sử dụng | ID trước login không còn là ID của phiên đã đăng nhập | Giảm nguy cơ session fixation |

Cách chứng minh end-to-end:

1. Trước login, nắm một session/cookie chưa xác thực (nếu được tạo).
2. Login thành công với CSRF token và password đúng.
3. Kiểm tra **ID sau login khác ID trước login** nếu có ID trước đó.
4. Dùng cookie mới gọi endpoint protected → đúng người dùng.
5. Dùng lại cookie trước login → **không** được đọc dữ liệu protected.
6. Logout bằng luồng hợp lệ → cookie cũ của phiên đã logout không cấp quyền truy cập.

Không chỉ kiểm tra status của \`POST /login\`: một redirect 302 có thể xảy ra nhưng client không lưu cookie, hoặc app đang dùng NoOp context repo.

### 5.1. Form login khác HTTP Basic và bearer token

Form login chủ yếu phục vụ trình duyệt với trạng thái đăng nhập được lưu qua session cookie. HTTP Basic hoặc bearer JWT thường mang credential trên từng request và **không nhất thiết** cần server-side session. Nếu chọn stateless, cần thiết kế riêng, không cố “xoay session ID” cho một phiên mà hệ thống không dùng.

\`WebSessionServerSecurityContextRepository\` phù hợp với web app session-based. **\`NoOpServerSecurityContextRepository\`** phù hợp khi cố ý không lưu SecurityContext qua request; nó không có tính năng đổi ID lúc lưu bởi nó không lưu.

### 5.2. CSRF khi đăng nhập

Spring Security WebFlux mặc định **bảo vệ \`POST /login\` bằng CSRF**. Để demo hoạt động:

- GET /login trước để nhận trang có token CSRF.
- Gửi cookie cùng \`_csrf\` tương ứng khi POST form.
- Không tắt CSRF chỉ để một lệnh curl POST ngắn hơn.

Thiếu CSRF token có thể trả **403 trước khi kiểm tra mật khẩu**, khiến người học nhầm rằng user/password sai. Token CSRF bảo vệ các hành động dựa trên cookie khỏi cross-site request giả mạo; session ID rotation giải quyết bài toán khác. Với custom login form, bạn phải đưa token vào form đúng cách.

## 6. Ví dụ tự cấu hình sai và cách sửa

**Sai: dùng NoOp repository trong form login có session**

~~~java
// Minh họa cấu hình sai nếu yêu cầu lưu login giữa các request.
return http
        .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
        .formLogin(form -> form
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance()))
        .build();
~~~

Một request có thể xác thực thành công, nhưng SecurityContext không được duy trì qua cookie session bằng repo này. Nó cũng không thực hiện đổi ID bằng cơ chế WebSessionServerSecurityContextRepository.save().

**Đúng: dùng WebSession repository ở cả hai điểm**

~~~java
ServerSecurityContextRepository repo =
        new WebSessionServerSecurityContextRepository();

return http
        .securityContextRepository(repo)
        .formLogin(form -> form
                .securityContextRepository(repo))
        .build();
~~~

Nếu dùng custom AuthenticationWebFilter, cần \`setSecurityContextRepository(repo)\` cho filter đó và tiếp tục cấu hình đường load từ đúng kho. Không tự viết filter chỉ để đổi ID nếu repository chuẩn đã làm điều đó. Nếu bạn thiết kế custom repository thay thế, phải **tự chịu trách nhiệm** về thời điểm lưu, đổi ID, loại bỏ ID cũ, xử lý lỗi, expiration và tính nhất quán đa instance; không giả định mọi repository đều an toàn mặc định.

## 7. Demo Java 17+ có thể chạy

Dùng **Spring Boot 3.5.16** (Java 17+, Gradle 8.4+ hoặc bản phù hợp; khuyến nghị Gradle 8.14+) để tránh ví dụ phụ thuộc những phiên bản Spring Framework cũ đã công bố lỗ hổng session fixation WebFlux. Với Spring Boot 3.5.16, Spring Framework yêu cầu tối thiểu nhánh 6.2.19 đã có bản vá cho vấn đề được nêu ở mục 12. Khi mang demo vào hệ thống thật, luôn kiểm tra phiên bản phụ thuộc đã resolve bằng dependency report và cập nhật bản vá mới.

Ứng dụng gồm:

- GET \`/public/ping\`: công khai.
- GET \`/login\`: trang login do Spring Security tạo.
- POST \`/login\`: form login với username/password và CSRF.
- GET \`/api/me\`: chỉ nhận khi có SecurityContext được khôi phục qua session.
- GET \`/api/admin\`: chỉ cho ROLE_ADMIN.
- POST \`/logout\`: logout mặc định có yêu cầu CSRF phù hợp.

Cấu trúc thư mục:

~~~text
webflux-form-session/
├── settings.gradle
├── build.gradle
├── src/main/java/example/session/SessionApplication.java
├── src/main/java/example/session/SecurityConfig.java
├── src/main/java/example/session/ApiController.java
└── src/test/java/example/session/SessionRepositoryTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-form-session'
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

Để dùng đúng phiên bản Gradle khi làm việc nhóm, có thể tạo **Gradle Wrapper** trong dự án bằng Gradle hợp lệ; demo không phụ thuộc wrapper đã được cung cấp sẵn.

### 7.3. SessionApplication.java

~~~java
package example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — thống nhất repository LOAD và SAVE

~~~java
package example.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {

        return http
                // Đường LOAD trên những request có session cookie.
                .securityContextRepository(repository)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping", "/login", "/logout")
                            .permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                // Đường SAVE sau POST /login thành công.
                .formLogin(form -> form
                        .securityContextRepository(repository)
                        .authenticationSuccessHandler(
                                new RedirectServerAuthenticationSuccessHandler(
                                        "/api/me")))
                // Demo chỉ dùng form login, không dùng Basic song song.
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .build();
    }
}
~~~

**Từng phần:**

1. **Bean repository** là một đối tượng WebSessionServerSecurityContextRepository dùng chung; rõ ràng trách nhiệm load/save.
2. **\`http.securityContextRepository(repository)\`** cấu hình đường khôi phục SecurityContext cho ReactorContextWebFilter ở request tiếp theo.
3. **\`form.securityContextRepository(repository)\`** cấu hình đường lưu Authentication thành công từ form login. Chính repository này thực hiện đổi session ID lúc save.
4. **Success handler** chuyển hướng về /api/me; đây là biểu hiện thành công cho người học, không tự tạo session hoặc tự gán Authentication.
5. **httpBasic.disable()** ngăn nhầm lẫn giữa Basic credential trên mỗi request với cookie-based form login.
6. **authorizeExchange** yêu cầu login cho API và ROLE_ADMIN cho đường quản trị. Đã login không tự cho phép mọi tài nguyên.
7. **Không disable CSRF**: form POST /login và POST /logout phải được bảo vệ.
8. Không thay đổi logout mặc định; khi muốn tùy chỉnh logout, phải đồng bộ việc xóa SecurityContext, session và cookie.

Dữ liệu password là **ví dụ cố định chỉ dành cho local dev**. Khi production, phải dùng kho danh tính, luân chuyển bí mật và các chính sách login phù hợp.

### 7.5. ApiController.java

~~~java
package example.session;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("report", "ok"));
    }
}
~~~

Đoạn controller không đọc hoặc xuất session ID. Nó chỉ xem Principal của request mà Spring Security đã khôi phục/xác minh. Không nên tạo endpoint trả \`WebSession.getId()\` cho client chỉ để debug: session identifier là credential nhạy cảm.

### 7.6. Chạy ứng dụng

Yêu cầu JDK 17+, Gradle tương thích và kết nối Maven Central để tải dependencies:

~~~bash
gradle bootRun
~~~

Khi startup thành công, demo lắng nghe ở \`http://localhost:8080\` nếu không có cấu hình port khác. Đây chỉ là môi trường local; production phải dùng HTTPS.

### 7.7. Luồng dùng trình duyệt

1. Mở \`http://localhost:8080/login\`. Spring Security tạo login page với input username, password và trường CSRF hidden.
2. Đăng nhập bằng alice / alice-pass.
3. Sau thành công, trình duyệt được chuyển đến /api/me và nhận \`{"username":"alice"}\`.
4. Bấm tải lại /api/me: vẫn nhận alice vì cookie phiên đã được gửi lại và repository đã load SecurityContext.
5. Mở /api/admin khi đăng nhập alice: bị từ chối 403; đăng nhập admin / admin-pass thì đủ ROLE_ADMIN.
6. Logout bằng luồng POST hợp lệ có CSRF, sau đó yêu cầu /api/me phải đưa về login hoặc bị từ chối.

Nên xem tab **Network** của công cụ DevTools: ở request login thành công sẽ có cookie/session mới, nhưng **không sao chép session ID vào log/chat/ticket**. Các header/cookie có thể phụ thuộc reverse proxy, cấu hình SameSite/Secure và session resolver.

## 8. Thử bằng curl có giữ cookie và CSRF

Một lệnh \`curl -d 'username=alice&password=alice-pass' /login\` không đủ nếu bật CSRF theo mặc định. Cần một **cookie jar** và lấy token từ trang login.

### 8.1. Bước 1: GET trang login

~~~bash
curl -sS -c before-login.cookies \
  http://localhost:8080/login \
  -o login.html
~~~

File \`before-login.cookies\` chứa cookie mà server đã phát trước login (nếu đã tạo phiên). \`login.html\` chứa form do Spring Security sinh. CSRF token có thể là giá trị đã mask chống BREACH, nhưng phải gửi lại **chính giá trị render trong form**.

Nếu muốn xem token thủ công, tìm input có \`name="_csrf"\` trong login.html. Không lấy token từ một request khác hoặc tự tạo giá trị ngẫu nhiên.

### 8.2. Bước 2: gửi POST login cùng token

Trên môi trường có Python 3, có thể lấy token bằng đoạn script dùng HTMLParser:

~~~python
from html.parser import HTMLParser

class CsrfParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        if tag != "input":
            return
        values = dict(attrs)
        if values.get("name") == "_csrf":
            self.token = values.get("value")

parser = CsrfParser()
with open("login.html", encoding="utf-8") as file:
    parser.feed(file.read())

if not parser.token:
    raise SystemExit("No _csrf input found")
print(parser.token)
~~~

Lưu code trên vào \`extract_csrf.py\` rồi thực hiện:

~~~bash
CSRF_TOKEN="$(python3 extract_csrf.py)"

curl -i -sS \
  -b before-login.cookies \
  -c after-login.cookies \
  --data-urlencode "username=alice" \
  --data-urlencode "password=alice-pass" \
  --data-urlencode "_csrf=$CSRF_TOKEN" \
  http://localhost:8080/login
~~~

Kỳ vọng **POST /login trả redirect 302 hoặc 303 tùy handler**, có Location trỏ đến /api/me theo cấu hình. Cookie jar **after-login.cookies** sẽ chứa cookie phiên được cập nhật khi server lưu SecurityContext.

**Không dùng \`curl -L\` trong bước đầu** nếu muốn nhìn rõ response redirect, Set-Cookie và kết quả POST. Sau đó có thể dùng -L để theo redirect nếu giữ cookie jar đúng.

### 8.3. Bước 3: dùng cookie sau login

~~~bash
curl -i -sS -b after-login.cookies \
  http://localhost:8080/api/me
~~~

Kết quả body dự kiến:

~~~json
{"username":"alice"}
~~~

Nếu dùng cookie **trước login** để gọi endpoint protected:

~~~bash
curl -i -sS -b before-login.cookies \
  http://localhost:8080/api/me
~~~

Thao tác này **không được** trả dữ liệu người dùng đã đăng nhập. Với form login mặc định, request chưa được xác thực thường bị chuyển hướng tới /login. Nếu không có cookie trước login vì chưa từng tạo session, đó vẫn là kết quả bình thường; kiểm chứng việc đổi ID cần test có session S0 thực tế (mục 9).

**Phân biệt tệp cookie:** curl với \`-c\` chỉ ghi cookie được biết tại thời điểm thực hiện. Để so sánh chính xác, lưu **before-login.cookies** riêng và dùng **after-login.cookies** cho request sau. Không đưa cookie vào version control hoặc chia sẻ công khai; chúng có thể cho quyền truy cập phiên dev.

### 8.4. Giải thích session ID trước và sau

Ở Spring WebFlux, tên cookie session thường là \`SESSION\` nếu không tùy chỉnh cookie resolver. Tên, đường dẫn, thuộc tính và trạng thái Secure/SameSite có thể khác trong ứng dụng thực tế. So sánh **giá trị định danh** trước và sau login khi cả hai xuất hiện.

| Mốc | ID | Trạng thái |
| --- | --- | --- |
| Trước login | S0 | Anonymous, có thể chứa CSRF token |
| Sau login thành công | S1, khác S0 | Có SecurityContext của alice |
| Request sau với S1 | S1 | Load thành công SecurityContext |
| Request với S0 | S0 | Không được nhận quyền của alice |
| Logout thành công | Phiên bị kết thúc/xóa context theo cấu hình | Cookie cũ không cho truy cập protected |

Không đưa S0/S1 thực vào ảnh chụp demo hay báo cáo. Có thể log **boolean "rotated=true"** để kiểm tra mà không log raw session ID.

## 9. Kiểm thử chính chức năng save/load/changeSessionId

Test API WebSessionServerSecurityContextRepository riêng giúp quan sát rõ việc đổi ID, không phụ thuộc HTML login hay cú pháp curl.

Tệp **src/test/java/example/session/SessionRepositoryTest.java**:

~~~java
package example.session;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockWebSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

import reactor.test.StepVerifier;

class SessionRepositoryTest {

    @Test
    void saveRotatesSessionIdAndLoadRestoresAuthentication() {
        WebSessionServerSecurityContextRepository repository =
                new WebSessionServerSecurityContextRepository();

        MockWebSession session = new MockWebSession();
        String originalSessionId = session.getId();

        MockServerWebExchange exchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/api/me"))
                .session(session)
                .build();

        Authentication verified =
                UsernamePasswordAuthenticationToken.authenticated(
                        "alice",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        SecurityContext context = new SecurityContextImpl(verified);

        StepVerifier.create(repository.save(exchange, context))
                .verifyComplete();

        assertNotEquals(originalSessionId, session.getId());

        StepVerifier.create(repository.load(exchange))
                .assertNext(restored -> {
                    assertEquals(
                            "alice",
                            restored.getAuthentication().getName());
                    assertEquals(
                            "ROLE_USER",
                            restored.getAuthentication()
                                    .getAuthorities()
                                    .iterator()
                                    .next()
                                    .getAuthority());
                })
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kết quả dự kiến:** test PASS và Gradle báo BUILD SUCCESSFUL trong môi trường có JDK/Gradle/dependencies hợp lệ. Ở đây không giả định một chuỗi session ID cố định: ID phải khác nhau, nhưng giá trị ID mới là ngẫu nhiên hoặc do Session Store quản lý.

Bài test chứng minh **hành vi repository độc lập**: save có side effect đổi ID và load trả đúng Authentication. Nó **không đủ để chứng minh trình duyệt nhận Set-Cookie hay ID trước login bị vô hiệu hóa trên mọi replica**; để bảo đảm end-to-end, cần thêm WebTestClient/browser/curl thực sự qua HTTP, session store thật và cả reverse proxy nếu có.

### 9.1. Nên kiểm thử những gì trên HTTP?

1. Chưa đăng nhập, GET /api/me → redirect /login, không đọc được username.
2. GET /login → form có CSRF token; cookie jar được giữ nếu có session.
3. POST /login với đúng CSRF, password đúng → redirect và có cookie phiên hợp lệ.
4. GET /api/me bằng cookie sau login → đúng username.
5. POST /login với password sai → không được lưu context đã xác thực, thường redirect /login?error.
6. Gửi POST login không CSRF → từ chối theo quy tắc CSRF, thường 403.
7. Nếu có ID S0 trước login, S1 sau login phải khác, và S0 không được phép truy cập thay S1.
8. Logout hợp lệ → request mới với cookie cũ không được phép đọc dữ liệu.
9. Login alice và admin ở hai cookie jar tách biệt → không lẫn Authentication.
10. Kiểm tra hành vi khi session hết hạn, khi backend session không khả dụng và sau restart.

Không chỉ test repository bằng \`MockWebSession\` rồi kết luận chắc chắn không có session fixation ở trình duyệt thực. Session cookie, store, proxy và phiên bản framework đều có thể tạo khác biệt.

## 10. Lỗi thường gặp khi cấu hình

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ cấu hình \`formLogin.securityContextRepository\` nhưng đường load dùng repository khác | POST login thành công, GET sau login thành anonymous | Chỉ định repository nhất quán ở formLogin và ServerHttpSecurity |
| Dùng NoOpServerSecurityContextRepository dù muốn session login | Không duy trì SecurityContext qua request | Dùng WebSessionServerSecurityContextRepository |
| Tự tạo AuthenticationWebFilter và quên setSecurityContextRepository | Filter mặc định không lưu context | Cấu hình repo cho filter và đường load |
| Tự gọi subscribe() để lưu SecurityContext | Lỗi lưu không gắn với vòng đời login, không đảm bảo redirect chờ lưu xong | Compose Mono<Void> của repository.save |
| Chỉ thêm Authentication vào Reactor Context | Có tác dụng cho subscription hiện tại, không tự persist qua request | Lưu qua ServerSecurityContextRepository |
| Chỉ đổi cookie bằng JS, không đổi ID ở session store | ID cũ có thể vẫn hợp lệ | Dùng cơ chế WebSession.changeSessionId/session store chính thức |
| Gọi session.changeSessionId() ở nhiều nơi không cần thiết | Tạo nhiều lần đổi ID khó theo dõi | Để WebSessionServerSecurityContextRepository.save làm việc đúng |
| Sử dụng \`HttpSession\`/Servlet SessionFixationProtectionStrategy trong WebFlux | Không đúng stack | Dùng WebSession và API reactive |
| Thử POST /login không gửi CSRF | Nhận 403 trước bước password | GET form, giữ cookie và gửi _csrf |
| Disable CSRF chỉ để curl chạy dễ hơn | Dễ có login CSRF/cross-site write | Giữ CSRF, hỗ trợ token trong form và test |
| Giữ session cookie qua HTTP không TLS | Người ngoài có thể lấy ID mới và chiếm phiên | HTTPS, Secure/HttpOnly/SameSite và cấu hình proxy |
| Coi rotation ngăn cả session hijacking | ID mới vẫn có thể bị đánh cắp sau login | Kết hợp XSS defense, TLS, cookie protection |
| Cookie Domain quá rộng trên các subdomain không tin cậy | Có nguy cơ cookie injection/session abuse | Giới hạn Domain/Path, ưu tiên host-only cookie |
| Dùng phiên bản Spring Framework có CVE đã biết | Vẫn có nguy cơ dù cấu hình trông đúng | Nâng lên bản vá chính thức |
| Trả session ID qua API để kiểm thử | Làm lộ credential phiên | Dùng test nội bộ, không public ID |
| Quên xử lý logout / timeout | Người dùng có thể truy cập lâu hơn kỳ vọng | Invalidate session và kiểm thử expiration |

## 11. Lưu phiên trong hệ thống nhiều instance

**Map user trong RAM** và **session trong RAM** là hai vấn đề khác nhau. Trong demo, UserDetails ở Map chỉ dành cho học; session store WebFlux mặc định thường là in-memory cho ứng dụng một process, không bảo đảm hai instance cùng nhìn thấy trạng thái đăng nhập.

Khi chạy nhiều replica sau load balancer:

- Sử dụng một **session store dùng chung** hỗ trợ reactive I/O, chẳng hạn cấu hình Spring Session với Redis phù hợp.
- Đảm bảo **changeSessionId** cập nhật mapping trong store theo đúng semantics và ID cũ không còn truy cập được.
- Đảm bảo mọi replica dùng chung cấu hình cookie (tên, Domain, Path, SameSite, Secure) và cách serialize session attributes.
- Giới hạn TTL, max idle time, rotation key, recovery và chính sách revoke.
- Nếu dùng session clustering, kiểm thử login/redirect/request sau trên **hai instance khác nhau** thay vì chỉ trên một instance.
- Không dựa chỉ vào sticky session để che lỗi ID rotation hoặc inconsistency của store.

Spring Session có tích hợp **ReactiveRedisSessionRepository** / **@EnableRedisWebSession** cho WebFlux, nhưng việc kết nối Redis, secret, TLS, serializer và cấu hình TTL là một bài toán deployment độc lập. Không thêm một phụ thuộc Redis vào demo nếu không có server Redis và cấu hình chạy thực tế.

Khi logout hoặc người dùng đổi mật khẩu, yêu cầu nghiệp vụ có thể đòi invalidate các session khác nhau. Rotation lúc login không thay thế chính sách logout-all-devices, quản lý phiên đồng thời hay audit.

## 12. Cảnh báo bảo mật cập nhật: CVE-2026-41839

Ngày **8/6/2026**, Spring công bố **CVE-2026-41839 – Spring Framework Escalation via Session Fixation in WebFlux**, liên quan tình huống subdomain bị xâm nhập và trao đổi session ID đã biết sang người dùng được xác thực. Đây là một lý do thực tế vì sao không nên chỉ nhìn vào code gọi changeSessionId mà kết luận hệ thống chắc chắn an toàn.

Theo thông báo của Spring, các dòng Framework chịu ảnh hưởng gồm:

- **7.0.0–7.0.7**.
- **6.2.0–6.2.18**.
- **6.1.0–6.1.27**.
- Các nhánh 5.3.48 trở xuống.

Các bản vá công khai trong thông báo bao gồm **Spring Framework 7.0.8** và **6.2.19**; nhánh cũ hơn có điều kiện hỗ trợ khác. Ứng dụng cần dùng phiên bản đã vá theo vendor, kể cả khi đã dùng WebSessionServerSecurityContextRepository.

**Vì vậy demo chọn Spring Boot 3.5.16**, không dùng một ví dụ cũ Spring Boot 3.3.5 vốn dựa trên nhánh Spring Framework trước khi lỗ hổng này được công bố. Khi chuyển một dự án có sẵn, nên xác minh phiên bản thực tế bằng:

~~~bash
gradle dependencies --configuration runtimeClasspath
~~~

Sau đó tìm phiên bản \`org.springframework:spring-webflux\`, \`spring-web\`, \`spring-session\` (nếu có), và đối chiếu advisory chính thức. Đừng đoán rằng chỉ đổi version plugin Spring Boot đã loại bỏ mọi override BOM hoặc dependency đã ghim trước đó.

Nguồn: https://spring.io/security/cve-2026-41839/

## 13. Checklist đưa vào production

**Bảo vệ luồng login:**

1. Dùng HTTPS mọi nơi; chỉ tin X-Forwarded-* từ reverse proxy được kiểm soát.
2. Mọi form login POST phải có CSRF token hợp lệ; bảo vệ thao tác thay đổi trạng thái khác.
3. Xác thực password bằng PasswordEncoder phù hợp; rate limit và quan sát login thất bại.
4. Không tạo Authentication dựa trên username/role do client tự khai.
5. Ghi SecurityContext qua ServerSecurityContextRepository đã chọn, và fail closed khi save thất bại.
6. Đảm bảo WebSessionServerSecurityContextRepository thay ID khi save; không vô hiệu hóa cơ chế này vì muốn “giữ cookie ổn định”.
7. Kiểm tra ID cũ không còn cấp quyền của user mới đăng nhập.
8. Đảm bảo cookie phiên được cấu hình Secure trong HTTPS, HttpOnly, SameSite phù hợp; hạn chế Domain/Path và không ghi vào log.
9. Kiểm thử logout/hết hạn/đổi mật khẩu/thu hồi quyền theo chính sách.
10. Nâng các phiên bản Spring Framework/Security/Session lên bản vá còn được hỗ trợ.
11. Với multi-instance, kiểm thử session rotation thật trên store dùng chung.
12. Không xuất session ID trong URL, JSON, tracing, error response hoặc screenshot.

**Không nhầm các cơ chế:**

| Cơ chế | Đối tượng bảo vệ | Ví dụ |
| --- | --- | --- |
| Session ID rotation | Giảm session fixation trước/sau login | S0 → S1 |
| CSRF token | Giảm request giả mạo từ site khác với cookie/credential tự gửi | _csrf ở POST /login |
| TLS + Secure cookie | Giảm nguy cơ nghe lén ID trên đường truyền | HTTPS |
| HttpOnly cookie | Hạn chế JavaScript đọc trực tiếp cookie | Set-Cookie HttpOnly |
| SameSite | Giảm một số tình huống gửi cookie cross-site | Lax/Strict theo nghiệp vụ |
| XSS defense | Giảm khả năng script độc hại thao túng phiên và hành động | Escaping, CSP, không unsafe inline |
| Authorization | Quyết định user có quyền với URL/tài nguyên | hasRole, owner/tenant check |
| Session invalidation | Chấm dứt session khi logout/timeout | WebSession.invalidate() / logout handler |

## 14. Câu hỏi tự kiểm tra

1. Vì sao Authentication thành công trong POST /login chưa chứng minh GET /api/me sau đó vẫn thấy user?
2. Hai cấu hình \`http.securityContextRepository(repo)\` và \`form.securityContextRepository(repo)\` đóng vai trò gì?
3. Tại sao WebSessionServerSecurityContextRepository đổi ID lúc lưu SecurityContext?
4. Session fixation khác session hijacking sau login ở điểm nào?
5. Nếu trước login không có cookie S0 thì có cần một ID S0 để login thành công không?
6. Vì sao không nên dùng NoOpServerSecurityContextRepository cho website dùng form login giữ session?
7. Tại sao một lệnh curl POST username/password thường chưa đủ khi giữ CSRF mặc định?
8. Hai request với cookie S0 và S1 sau login nên khác nhau về quyền như thế nào?
9. Vì sao test MockWebSession không thay thế integration test qua cookie và session store thực?
10. Có nên gọi \`changeSessionId()\` thủ công thêm một lần ngay sau khi repo chuẩn đã save không?
11. Khi dùng Redis session store qua nhiều node, phải kiểm thử điều gì về ID cũ?
12. Lỗ hổng CVE-2026-41839 cho thấy vì sao cần quan tâm phiên bản thư viện dù đã bật tính năng đổi session ID?

**Đáp án gợi ý:** (1) còn cần save/load context và client gửi cookie; (2) đường load request sau và đường save lúc login; (3) cắt liên kết với ID pre-auth có thể đã bị biết; (4) fixation nhắm ID được biết trước login, hijacking có thể xảy ra sau khi ID mới bị lộ; (5) không, server có thể tạo session khi cần; (6) NoOp không duy trì context qua request; (7) POST /login bị CSRF bảo vệ; (8) S1 dùng được, S0 không được kế thừa quyền; (9) test đơn vị không đo cookie/proxy/multi-node; (10) không cần nếu repo đã đổi ID; (11) old ID invalid, new ID load đúng trên mọi node; (12) bảo vệ còn phụ thuộc bản vá của Spring Framework/Session Store.

## 15. Tài liệu tra cứu

- Spring Security Javadoc — \`WebSessionServerSecurityContextRepository\`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security Javadoc — \`ServerHttpSecurity.FormLoginSpec\`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security Javadoc — \`ServerHttpSecurity.securityContextRepository\`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework — \`WebSession.changeSessionId()\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Session — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Security Advisory CVE-2026-41839: https://spring.io/security/cve-2026-41839/
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Kết luận:** Trong Spring Security Reactive, một đăng nhập biểu mẫu an toàn cần **xác thực thành công → lưu SecurityContext vào WebSession → thay session ID → client sử dụng cookie mới → request sau nạp lại context**. Dùng \`WebSessionServerSecurityContextRepository\` và cấu hình thống nhất ở FormLoginSpec lẫn ServerHttpSecurity để tránh lỗi save/load. Hãy giữ CSRF, bảo vệ cookie, kiểm chứng ID cũ không còn dùng được và luôn áp dụng các bản vá Spring Framework, nhất là trước những lỗ hổng session fixation đã được công bố.