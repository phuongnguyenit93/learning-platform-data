# Kiến thức đầu vào và trình tự học: từ đăng nhập cơ bản đến tích hợp định danh bên ngoài

> **Phạm vi:** Spring Security Authentication trên ứng dụng **Servlet/Spring MVC**. Bài này là bản đồ học tập: cần biết gì, học theo thứ tự nào, thực hành ra sao và khi nào đủ nền tảng để kết nối hệ thống định danh ngoài. Ví dụ chạy ở **Java 17+ và Spring Boot 3.3.x (Spring Security 6.x)**; khi dùng bản khác, đối chiếu tài liệu đúng phiên bản. Các bài chuyên sâu về phân quyền, OAuth2/OIDC, federation và reactive được học sau những nền tảng xác thực tương ứng.

## 1. Mục tiêu và ranh giới

Sau bài này, người học phải tự giải thích được:

1. Vì sao request chưa đăng nhập bị đưa đến trang login, và request sau đăng nhập được nhận diện thế nào.
2. Vai trò của `SecurityFilterChain`, `Authentication`, `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` và `SecurityContext`.
3. Cách chuyển từ tài khoản trong bộ nhớ sang tài khoản trong cơ sở dữ liệu mà không tự viết cơ chế so sánh mật khẩu.
4. Khác nhau giữa phiên đăng nhập browser, HTTP Basic, API bearer token và đăng nhập qua nhà cung cấp định danh (IdP).
5. Cách chọn thứ tự tích hợp: tài khoản nội bộ → lưu trữ thực tế → quản lý phiên → API → IdP/LDAP; đồng thời biết kiểm tra tình huống thất bại và ranh giới tin cậy.

**Authentication (xác thực)** trả lời “đây là ai, bằng chứng nào chứng minh danh tính?”. **Authorization (phân quyền)** trả lời “danh tính đó được làm gì?”. Đăng nhập thành công không đồng nghĩa được phép truy cập mọi tài nguyên. `GrantedAuthority`, vai trò và scope là dữ kiện đầu vào cho quyết định phân quyền; việc thiết kế chính sách phân quyền chi tiết nằm ngoài bài này.

## 2. Kiến thức đầu vào nên có

| Nền tảng | Cần hiểu trước khi bắt đầu | Tự kiểm tra |
| --- | --- | --- |
| Java 17+ | Class, interface, exception, dependency injection qua constructor, annotation | Giải thích vì sao một service có thể nhận interface thay cho implementation |
| Spring Boot và Spring MVC | `@SpringBootApplication`, `@Configuration`, `@Bean`, `@RestController`, ánh xạ endpoint | Tạo được `GET /hello` trả HTTP 200 |
| HTTP/HTTPS | GET/POST, header, status, redirect 302, cookie, TLS | Phân biệt request/response và vì sao mật khẩu phải đi qua HTTPS |
| Trạng thái phiên | Cookie `JSESSIONID`, session phía server, timeout | Giải thích vì sao browser có thể được nhận ra ở request tiếp theo |
| Lưu trữ người dùng | Khóa định danh, truy vấn theo username/email, cột password hash, trạng thái enabled/locked | Phân biệt mật khẩu gốc với giá trị băm lưu trong DB |
| Khái niệm bảo mật | Xác thực, phân quyền, hash có salt, CSRF, XSS, brute force, nguyên tắc quyền tối thiểu | Giải thích vì sao không lưu plaintext password và không tắt CSRF chỉ để form POST chạy |
| Kiểm thử | JUnit, MockMvc, đọc log không chứa bí mật | Viết được phép thử request chưa đăng nhập và mật khẩu sai |

Có thể học đồng thời HTTP cookie/session và password hashing trong chặng đầu; **không nên bắt đầu bằng JWT, OAuth2 hoặc một `AuthenticationProvider` tự viết** khi còn chưa hiểu luồng đăng nhập chuẩn.

## 3. Bản đồ một request đăng nhập

```text
Browser: GET /profile (chưa đăng nhập)
    → Servlet Filter Chain / Spring Security
    → chưa có Authentication hợp lệ, endpoint yêu cầu authenticated
    → AuthenticationEntryPoint chuyển hướng đến /login
    → Browser GET /login, nhận trang login
    → Browser POST /login (username, password, CSRF token)
    → UsernamePasswordAuthenticationFilter tạo Authentication chưa xác thực
    → AuthenticationManager (thường là ProviderManager)
    → AuthenticationProvider phù hợp (thường DaoAuthenticationProvider)
    → UserDetailsService lấy user + password hash + trạng thái
    → PasswordEncoder.matches(rawPassword, storedHash)
    → thành công: Authentication đã xác thực
    → SecurityContextHolder giữ SecurityContext cho request
    → cơ chế session/context repository lưu trạng thái khi phù hợp
    → request sau: browser gửi cookie, context được khôi phục
    → Controller nhận danh tính đã xác thực
```

Đây là **đường đi thường gặp của form login dùng username/password**, không phải sơ đồ cố định cho mọi cơ chế. HTTP Basic, bearer token và OAuth2 Login sử dụng filter/provider khác nhưng vẫn quy về danh tính được xác thực trong `SecurityContext`.

Đọc các thành phần theo đúng trách nhiệm:

- `SecurityFilterChain` xác định lớp filter bảo vệ HTTP request; cấu hình login và điều kiện truy cập nằm ở đây.
- `Authentication` biểu diễn yêu cầu xác thực (trước xác thực) hoặc kết quả có principal, authorities và trạng thái xác thực (sau xác thực).
- `AuthenticationManager` nhận yêu cầu xác thực; `ProviderManager` có thể ủy quyền cho nhiều `AuthenticationProvider` theo loại credential/token.
- `DaoAuthenticationProvider` dùng `UserDetailsService` để lấy thông tin tài khoản và `PasswordEncoder` để kiểm tra mật khẩu.
- `SecurityContextHolder` cho phép đọc `SecurityContext` hiện thời, thông thường gắn với thread xử lý request. Giữ context qua các request phụ thuộc cơ chế repository/session; không nên tự giả định dữ liệu trong ThreadLocal tự sống qua request sau.
- `AuthenticationEntryPoint` khởi động quá trình xác thực khi cần (redirect login hoặc thử thách HTTP); `AuthenticationFailureHandler` và `AuthenticationSuccessHandler` xử lý kết quả login.
- `SecurityContextRepository` là phần liên quan đến lưu/khôi phục context. **Nếu tự triển khai luồng login ngoài filter chuẩn**, phải xem xét việc lưu context tường minh; chỉ gọi `SecurityContextHolder.setContext(...)` chưa đủ để tự bảo đảm đăng nhập được duy trì.

## 4. Trình tự thực hành từ đơn giản đến thực tế

### Chặng 1 — Một ứng dụng có trang đăng nhập mặc định

**Đích:** quan sát được trước/sau xác thực với số thành phần ít nhất.

Tạo một ứng dụng Gradle Spring Boot **3.3.13**, Java **17+**, package `dev.demo.auth`. Nếu tạo bằng Spring Initializr, chọn **Spring Web**, **Spring Security**, Gradle và Java 17 trở lên. Nội dung `build.gradle` tối thiểu dưới đây dùng dependency do Spring Boot quản lý:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `src/main/java/dev/demo/auth/AuthLearningApplication.java`:

```java
package dev.demo.auth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class AuthLearningApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthLearningApplication.class, args);
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

Tạo `src/main/java/dev/demo/auth/SecurityConfig.java`:

```java
package dev.demo.auth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-pass-123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
```

Trong thư mục project, chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), hoặc dùng tác vụ Gradle tương ứng trong IDE. Ví dụ này sử dụng form login mặc định, **không cấu hình `loginPage(...)`** nên Spring Security tự cung cấp màn hình login. Mật khẩu `demo-pass-123` là **dữ liệu học tập**, tuyệt đối không sao chép thành tài khoản triển khai thật.

Thí nghiệm theo thứ tự:

1. Mở `http://localhost:8080/public` khi chưa đăng nhập: nhận **HTTP 200**, body **`public`**.
2. Mở `http://localhost:8080/profile` trong browser mới: được chuyển tới `/login`. Đây là ví dụ request cần xác thực trước khi vào controller.
3. Đăng nhập `learner` / `demo-pass-123` trên trang login mặc định. Sau khi vào lại `/profile`, body là **`hello learner`**.
4. Thử mật khẩu sai: đăng nhập thất bại, không xuất hiện phiên người dùng hợp lệ. Theo mặc định form login dẫn lại trang có chỉ báo lỗi.
5. Đóng/mở DevTools Network, quan sát **302 redirect**, **POST /login**, cookie/session và request đi sau đăng nhập. Trong browser, form login chứa CSRF token; đừng thử POST không có token rồi kết luận mật khẩu sai.
6. Đăng xuất bằng chức năng logout do Spring Security hỗ trợ rồi truy cập lại `/profile`. Khi CSRF đang bật, logout nên dùng **POST** kèm token CSRF thay vì tự giả định GET logout.

**Cần hiểu sau chặng 1:** `requestMatchers` quyết định tài nguyên có cần danh tính hay không; form login là cách **thu thập credential**, `UserDetailsService` cung cấp user, encoder kiểm tra bí mật, context biểu diễn người đang đăng nhập. `ROLE_USER` trong ví dụ là authority được gán cho user, chưa phải một chính sách phân quyền chi tiết.

### Chặng 2 — Hiểu password và thay InMemory bằng database

**Đích:** đăng nhập từ tài khoản bền vững, không hardcode user trong cấu hình.

Làm theo thứ tự:

1. Thiết kế bảng tài khoản có ít nhất `id`, `username` duy nhất, `password_hash`, `enabled`, `locked` và thời điểm tạo/cập nhật. Phân biệt account nội bộ với hồ sơ người dùng nghiệp vụ.
2. Tạo quy trình đăng ký/khởi tạo tài khoản: **encode** mật khẩu một lần trước khi ghi DB; khi login, đọc hash và dùng `PasswordEncoder.matches(raw, hash)`. BCrypt có salt nên hai lần encode cùng mật khẩu thường cho hai giá trị hash khác nhau; **không so sánh hai chuỗi hash bằng `equals`**.
3. Thay bean `InMemoryUserDetailsManager` bằng `UserDetailsService` lấy tài khoản qua repository theo username. Trả về `UserDetails` gồm username, password hash, các cờ enabled/locked và authorities. Đây là điểm mở rộng **nguồn dữ liệu**, chưa cần tự thay cả authentication pipeline.
4. Cấu hình bean `PasswordEncoder` nhất quán với định dạng hash trong DB. Trong hệ thống có nhiều thuật toán theo thời gian, xem `DelegatingPasswordEncoder` và prefix dạng `{id}`; không để lẫn hash không có định dạng rõ ràng rồi âm thầm “fallback” sang plaintext.
5. Kiểm tra các trạng thái: user tồn tại, password sai, user disabled/locked, user không tồn tại, cập nhật password và thay đổi quyền.

Phần sau chỉ là **phác thảo điểm nối DB**, cần bổ sung các class `Account` và `AccountRepository` trong hệ thống thực tế; không phải file Java độc lập có thể chạy:

```java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    Account account = repository.findByUsername(username)
            .orElseThrow(() -> new UsernameNotFoundException("Unknown user"));

    return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .roles("USER")
            .build();
}
```

Không gọi `PasswordEncoder.encode(rawPassword)` rồi so trực tiếp với DB trong mỗi lần login; cũng không ghi password, access token hoặc Authorization header vào log. Thông điệp lỗi trả ra giao diện nên đủ hữu ích mà không lộ việc username có tồn tại hay không. Bổ sung hạn chế số lần thử, quan sát đăng nhập thất bại và cách khóa/mở khóa tài khoản theo yêu cầu thực tế.

### Chặng 3 — Session, SecurityContext, CSRF và vòng đời đăng nhập

**Đích:** nắm được câu hỏi “vì sao request tiếp theo vẫn biết tôi là ai?”.

Với **browser + form login**, sau xác thực thành công Spring Security có thể lưu thông tin bảo mật thông qua `SecurityContextRepository`/HTTP session. Browser giữ cookie tham chiếu tới session phía server; server khôi phục context để xử lý request tiếp. Đây **không phải** việc client gửi lại password mỗi request, cũng **không phải** `SecurityContextHolder` tự lưu bền vững.

Bài thực hành: login → kiểm tra cookie phiên → request `/profile` → logout → request lại → timeout → login lại. Quan sát hiệu ứng thay session ID khi đăng nhập (session fixation protection), cấu hình timeout, xử lý nhiều tab/browser và vô hiệu hóa phiên khi logout. Nếu ứng dụng chạy nhiều node, cân nhắc session store chia sẻ và chiến lược logout theo kiến trúc triển khai.

CSRF là rủi ro đặc biệt đối với request mà browser tự đính kèm cookie. Trong form login, giữ CSRF protection và đưa token vào form POST; dùng view technology hỗ trợ CSRF hoặc truyền token do server cấp một cách đúng đắn. **Không tắt `csrf` toàn cục để giải quyết lỗi 403**. Đối với API bearer token thật sự stateless, quyết định CSRF phụ thuộc cách credential được truyền và liệu browser có tự gửi credential hay không; không thể kết luận chỉ từ chữ “REST”.

Đọc `SecurityContextHolder` cho request hiện thời, nhưng cẩn trọng khi chạy `@Async`, executor hoặc thread khác: danh tính không tự động được truyền sang mọi thread. Không lưu `Authentication` vào biến static hay cache toàn cục để “giữ login”.

### Chặng 4 — Từ HTML login đến API authentication

**Đích:** chọn đúng kiểu credential cho đúng loại client.

| Cách truy cập | Credential và trạng thái | Hành vi thường gặp khi chưa xác thực | Khi nào học/dùng |
| --- | --- | --- | --- |
| Form login + session | Form gửi username/password một lần; browser giữ session cookie | Chuyển tới trang login | Web app với phiên server |
| HTTP Basic | Mỗi request gửi `Authorization: Basic ...`; nội dung Base64 **không phải mã hóa** | HTTP 401 với Basic challenge | Học cơ chế, tích hợp đơn giản qua HTTPS; cân nhắc mức phù hợp thực tế |
| Bearer access token | `Authorization: Bearer <token>`; API kiểm tra token | HTTP 401/challenge nếu token thiếu/sai | SPA/mobile/API do một IdP hoặc authorization server cấp token |
| OAuth2/OIDC Login | Browser được chuyển tới IdP; ứng dụng nhận kết quả code flow và thiết lập principal/session theo cấu hình | Redirect tới IdP | SSO/đăng nhập qua tổ chức hoặc nhà cung cấp ngoài |
| LDAP/AD | Directory là nguồn xác thực/dữ liệu danh tính | Phụ thuộc UI và filter tích hợp | Hệ thống doanh nghiệp có directory |

**HTTP 401** thường nghĩa là thiếu/không đạt xác thực; **HTTP 403** nghĩa là yêu cầu bị từ chối dù đã xác thực hoặc thất bại ở một kiểm tra bảo vệ khác (ví dụ CSRF). Chỉ nhìn status không đủ chẩn đoán: xem cơ chế đăng nhập, log an toàn và nguồn tạo response.

Bài tập nhỏ: chuyển một endpoint học tập sang HTTP Basic bằng `http.httpBasic(Customizer.withDefaults())`, gọi từ client có/không có header, so sánh với redirect form login. Đây là **đoạn cấu hình minh họa bổ sung** cho `SecurityFilterChain`, không phải chương trình Java độc lập. Chỉ dùng trên HTTPS; không coi Base64 là bảo mật mật khẩu.

Tiếp đó học **resource server**: ứng dụng nhận access token do một issuer đáng tin phát hành, kiểm tra chữ ký (đối với JWT), `iss`, `exp`, `aud` theo yêu cầu của API, ánh xạ claim/scope thành authorities, rồi thiết lập principal. Cấu hình ví dụ sau chỉ đầy đủ khi project đã thêm dependency `spring-boot-starter-oauth2-resource-server`, có issuer hợp lệ và chính sách xác minh audience phù hợp:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/demo
```

`identity.example.org` chỉ là **địa chỉ minh họa, không có IdP thật**. Với JWT, không “decode Base64” rồi tin nội dung: decode không đồng nghĩa verify. Không dùng **ID token** từ OIDC như access token để gọi API chỉ vì nó có JWT shape; mỗi loại token có đối tượng nhận và mục đích khác nhau.

### Chặng 5 — Chỉ custom khi điểm mở rộng chuẩn chưa đáp ứng

**Đích:** nhận diện đúng lớp cần thay khi hệ thống dùng nguồn xác thực ngoài thông thường.

- Nếu chỉ đổi nơi lưu user (DB, JDBC, LDAP): ưu tiên tích hợp `UserDetailsService` hoặc provider được Spring Security hỗ trợ.
- Nếu cần kiểm tra loại credential đặc biệt do hệ thống khác cấp: tìm hiểu `AuthenticationProvider.supports(...)`, `authenticate(...)`, cách trả kết quả thành công, thất bại và việc đăng ký provider trong `AuthenticationManager`.
- Nếu credential xuất hiện theo giao thức HTTP mới: có thể cần filter/extractor phù hợp, nhưng đừng viết filter thủ công chỉ để nhận username/password của form login.
- Nếu gọi external user service: đặt timeout, giới hạn retry, kiểm soát outage, không log secret, xác định ai là nguồn sự thật cho account lock, và đảm bảo không cho “fallback” sang cơ chế yếu hơn khi dịch vụ ngoài lỗi.

Ví dụ tư duy: nếu endpoint dịch vụ định danh trả “tài khoản đã xác thực”, ứng dụng phải kiểm tra **bằng chứng có thể xác minh** và trust boundary, không chỉ tin một JSON có trường `authenticated=true` từ client. Phân biệt rõ **xác thực credential** với **đồng bộ profile/role** sau khi danh tính đã xác thực.

### Chặng 6 — Đăng nhập qua IdP bên ngoài: OAuth2 Login và OpenID Connect

**Đích:** tích hợp SSO mà không tự tiếp nhận mật khẩu của nhà cung cấp.

Học các vai trò theo thứ tự: browser/user → ứng dụng **OAuth2 Client/Relying Party** → **Authorization Server/OpenID Provider** → API **Resource Server** (nếu có). **OAuth 2.0** chủ yếu là framework ủy quyền truy cập; **OpenID Connect (OIDC)** thêm lớp xác thực và ID token để truyền thông tin danh tính chuẩn. Khi yêu cầu “đăng nhập với nhà cung cấp”, ưu tiên hiểu **OIDC Authorization Code Flow** thay vì gọi OAuth2 là giao thức đăng nhập một cách chung chung.

Luồng điển hình:

```text
Browser mở trang được bảo vệ
    → ứng dụng chuyển đến IdP (authorization request)
    → IdP xác thực user và lấy consent nếu cần
    → IdP chuyển về redirect URI đã đăng ký cùng authorization code
    → ứng dụng trao đổi code qua back channel lấy token
    → thư viện kiểm tra state, token/issuer/nonce theo luồng và cấu hình
    → ứng dụng xây dựng principal, quyết định map sang local account
    → thiết lập phiên đăng nhập hoặc trả response cho ứng dụng
```

Cần nắm `client_id`, redirect URI chính xác, `state` chống trộn request/CSRF, `nonce` trong OIDC, PKCE nơi phù hợp, issuer/discovery metadata, JWKS, `sub` là định danh ổn định trong issuer, session/local logout và token lifecycle. Với external account, khóa định danh bền vững thường là **(issuer, subject)**; không tự đồng nhất hai người chỉ bởi email giống nhau hoặc email chưa được xác minh.

Đối với Spring MVC app, bài thực hành tích hợp yêu cầu dependency `spring-boot-starter-oauth2-client`, đăng ký client hợp lệ ở IdP và cấu hình `spring.security.oauth2.client.registration`/`provider`. Trong `SecurityFilterChain`, cấu hình mức nhập môn:

```java
http.oauth2Login(Customizer.withDefaults());
```

Đây chỉ là **một dòng cấu hình minh họa**, chưa thể chạy độc lập nếu chưa có client registration/IdP. Spring Security thường dùng endpoint khởi tạo như `/oauth2/authorization/{registrationId}` và callback như `/login/oauth2/code/{registrationId}`. Kiểm tra chính xác redirect URI được IdP cho phép và ứng dụng đang dùng HTTP/HTTPS qua reverse proxy.

Cần trả lời trước khi triển khai: login thành công nhưng local user chưa tồn tại thì tạo mới, liên kết có kiểm soát hay từ chối? Role và group lấy từ IdP ở lần đăng nhập hay đồng bộ định kỳ? Nếu IdP bị lỗi thì sao? Khi IdP logout, session local có còn hiệu lực? Đây là quyết định thiết kế phải có test, không được giả định framework giải quyết thay.

**Các hướng học kế tiếp:** LDAP/Active Directory khi dùng directory; SAML2 khi hệ thống doanh nghiệp áp dụng SAML; MFA/step-up authentication khi yêu cầu mức bảo đảm cao hơn. Đây là các nhánh sau khi vững kiến trúc authentication chung, không phải điều kiện bắt buộc để làm form login nội bộ.

## 5. Cách chọn đường học theo bài toán

| Bài toán | Điểm khởi đầu phù hợp | Bước tiếp theo cần làm rõ |
| --- | --- | --- |
| Website học tập đăng nhập tài khoản nội bộ | Form login + in-memory user | Password hashing → DB → session/logout |
| Ứng dụng web doanh nghiệp có user trong DB | `UserDetailsService` + encoder | Account state, rate limiting, reset password, auditing |
| API server nhận token từ nhà cung cấp | OAuth2 Resource Server | Issuer/JWKS, audience, scopes, lỗi token và clock skew |
| Web app “Login with Company/Google/IdP” | OAuth2 Client + OIDC Login | Redirect URI, subject mapping, account linking, logout |
| Cổng nội bộ kết nối AD/LDAP | LDAP authentication integration | Bind mode, group mapping, TLS, directory outage |
| Hệ thống nhiều nguồn danh tính | `AuthenticationManager` + providers có kiểm soát | Thứ tự provider, fallback policy, trust, security test |

Không cần xây authorization server hoặc tự ký token để học đăng nhập cơ bản. Khi tích hợp ngoài, trước hết xác định **ứng dụng là client nhận đăng nhập, API kiểm tra access token, hay hệ thống phát hành token**; ba vai trò này không thay thế nhau.

## 6. Ma trận kiểm thử tối thiểu ở từng chặng

| Trường hợp | Mong đợi cần kiểm tra |
| --- | --- |
| Request public không có session | Cho phép truy cập |
| Request protected chưa login | Chuyển login với browser, hoặc 401 với cơ chế API được chọn |
| Đúng username/password, account active | Tạo principal hợp lệ; request tiếp theo nhận đúng username |
| Password sai hoặc account không tồn tại | Từ chối; không tạo phiên đã xác thực; không lộ mật khẩu/log nhạy cảm |
| Account disabled/locked | Từ chối theo chính sách, không bỏ qua cờ trạng thái |
| Form POST thiếu/không khớp CSRF token | Bị từ chối khi CSRF protection áp dụng |
| Logout và session hết hạn | Không thể tái sử dụng phiên cũ để vào tài nguyên bảo vệ |
| JWT hết hạn/sai issuer/sai audience/chữ ký | Từ chối token; tuyệt đối không chấp nhận chỉ vì parse được payload |
| IdP callback sai state/nonce/redirect | Flow thất bại an toàn, không tự gắn user theo dữ liệu client đưa |
| Nguồn DB/LDAP/IdP không khả dụng | Thất bại có kiểm soát, không cho đăng nhập bằng đường dự phòng yếu |
| Đổi password hoặc khóa tài khoản | Xác minh chính sách với session/token đã phát hành, không ngầm giả định mọi phiên bị thu hồi tức thì |

Với `spring-security-test` và `MockMvc`, phân biệt kiểm thử **giả lập danh tính** (ví dụ `@WithMockUser`) với kiểm thử **luồng xác thực thực** bằng `formLogin()`. `@WithMockUser` hữu ích khi test truy cập tài nguyên, nhưng không chứng minh `UserDetailsService`, encoder hay login filter hoạt động đúng. Một nhóm test nên có cả hai loại, đặc biệt các negative case.

**Bài thực hành có thể lặp lại:** chụp trạng thái Network/browser trước khi login, chạy các case theo ma trận, ghi request URL, status, cookie/redirect và principal nhìn thấy tại endpoint; không lưu password, session ID, access token hoặc ID token thô trong tài liệu/kho log. Với hệ thống thật cần bổ sung test refresh/revocation và đồng bộ quyền theo chính sách vận hành.

## 7. Sai lầm phổ biến và cách nhận biết

1. **Nhầm xác thực với phân quyền:** login thành công nhưng endpoint vẫn 403 có thể vì chính sách truy cập, không phải lỗi password.
2. **Tự gọi controller `POST /login` rồi so string password:** bỏ qua filter/provider, CSRF, session fixation và success/failure handling đã được framework cung cấp.
3. **Lưu plaintext hoặc SHA-256 một vòng cho password:** dùng password hashing có cost/salt phù hợp; quản lý nâng cấp hash và không tự phát minh thuật toán.
4. **Tắt CSRF vì bị 403:** tìm hiểu hình thức client, cookies và cơ chế token; chỉ giới hạn exception có giải thích rõ ràng.
5. **Đặt `anyRequest().permitAll()` để “login chạy”:** làm mất mục tiêu bảo vệ endpoint. Phải có request public và request cần xác thực để quan sát.
6. **Cho rằng có `Authentication` là session đã lưu:** phân biệt context của request hiện tại với repository/session và API custom login.
7. **Nhầm OAuth2 Access Token với OIDC ID Token:** token dùng cho API và token biểu diễn danh tính có audience/mục đích khác nhau.
8. **Tin claim JWT chỉ vì đã decode:** kiểm tra issuer, chữ ký, thời gian và audience theo resource server.
9. **Dựa vào email làm khóa external identity duy nhất:** cần issuer + subject, quy trình account linking an toàn và kiểm tra email verification nếu dùng.
10. **Tự dùng provider ngoài mà không đặt timeout/failure policy:** một outage có thể biến thành lỗi bảo mật hoặc làm toàn bộ login treo.
11. **Test chỉ bằng `@WithMockUser`:** các test đó không đi qua quy trình kiểm tra password/IdP thật.
12. **Chuyển ngay sang custom filter/provider:** học chức năng chuẩn trước, chỉ thay điểm mở rộng mà yêu cầu thực sự cần.

## 8. Bài tổng hợp để chứng minh đã học đúng thứ tự

Xây một ứng dụng demo nhỏ gồm `/public`, `/profile`, `/admin-demo` và một tài khoản nội bộ. Hoàn thiện theo các mốc, mỗi mốc chỉ thêm một biến số:

1. **M1 — Luồng chuẩn:** in-memory user, form login mặc định, request protected, quan sát redirect/cookie/CSRF, logout. Có ít nhất ba test thành công/thất bại.
2. **M2 — Nguồn dữ liệu thật:** thay user store bằng DB, lưu BCrypt/DelegatingPasswordEncoder hash, kiểm tra disabled/locked và không tiết lộ account existence.
3. **M3 — Vòng đời:** session timeout, logout, kiểm tra request sau khi hết phiên, log sự kiện bảo mật không lộ secret.
4. **M4 — API:** tạo một API có xác thực phù hợp (Basic chỉ để học hoặc Resource Server với issuer thử nghiệm); giải thích chính xác HTTP 401, 403, credential gửi ở đâu.
5. **M5 — Tích hợp ngoài:** cấu hình một IdP thử nghiệm cho OIDC Login; thử login, account mapping, callback sai, mất kết nối IdP và logout. Có sơ đồ trust boundary.

**Tiêu chí hoàn thành:** người học tự vẽ được authentication flow, chỉ ra lớp nào làm việc gì, chạy được demo chặng 1, giải thích DB/session/API/IdP mà không lẫn cơ chế, có test cho các trường hợp lỗi, và nêu được rủi ro ở ranh giới ứng dụng ↔ IdP. Nếu chưa giải thích nổi đường đi của `UsernamePasswordAuthenticationToken` và vai trò của `UserDetailsService`/`PasswordEncoder`, hãy củng cố chặng 1–2 trước khi sang OIDC.

## 9. Tài liệu đối chiếu chính thức

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html)
- [Spring Security — OAuth2 / OIDC Client và Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/index.html)
- [Spring Boot 3.3 — Java/Gradle requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)

Các liên kết trên tham chiếu dòng Spring Security 6.5/Spring Boot 3.3 để dễ đối chiếu với ví dụ; khi dự án đang dùng Spring Boot/Spring Security khác phiên bản, kiểm tra lại API, mặc định bảo mật và hướng dẫn tương ứng.