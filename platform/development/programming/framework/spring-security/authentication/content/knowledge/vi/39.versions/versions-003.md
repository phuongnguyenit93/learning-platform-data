# Bean AuthenticationManager, AuthenticationProvider và cấu hình hiện đại trong Spring Security

Từ Spring Security 5.7 đến các nhánh 6.x và 7.x, cấu hình bảo mật Servlet ngày càng dựa vào **Spring beans** và **lambda DSL**, thay cho kế thừa `WebSecurityConfigurerAdapter`. Điều dễ gây nhầm là: có `SecurityFilterChain` bean rồi thì **AuthenticationManager** đến từ đâu? Khi nào chỉ cần `UserDetailsService`, khi nào phải tạo `AuthenticationProvider` và `ProviderManager`? Định nghĩa một bean mới có làm filter login dùng bean đó không? Tại sao đoạn code cũ dùng `new DaoAuthenticationProvider()` biên dịch ở một phiên bản nhưng lỗi ở phiên bản mới?

Bài này làm rõ **các thành phần, cách wiring, phạm vi global/local, khác biệt phiên bản, ví dụ Java 17+, kiểm thử và lỗi cấu hình thường gặp**. Trọng tâm là **Spring Security Servlet**; WebFlux dùng `ReactiveAuthenticationManager` và `SecurityWebFilterChain`, không thể sao chép nguyên các bean Servlet vào reactive stack.

**Mục tiêu sau bài học:** tự xác định ai tạo AuthenticationManager cho filter chain; cấu hình username/password bằng các bean hiện đại mà không tạo manager dư; chủ động xuất bản manager cho REST login tùy chỉnh; ghép nhiều providers đúng `supports(...)` và trật tự; xử lý credential erasure/events/HTTP session đúng cách; biết vì sao một snippet thuộc Spring Security 5.x không tương thích 6.x/7.x.

## 1. Bức tranh tổng thể của xác thực Servlet

Một HTTP request chứa credentials đi qua những ranh giới riêng:

~~~text
Browser / HTTP client
        |
        v
SecurityFilterChain (Servlet)
        |
        +-- Authentication filter:
        |     UsernamePasswordAuthenticationFilter
        |     BasicAuthenticationFilter / custom filter / ...
        |
        +-- Tạo Authentication request CHƯA xác thực
        |
        v
AuthenticationManager.authenticate(authentication)
        |
        v
ProviderManager (implementation phổ biến)
        |
        +-- AuthenticationProvider 1: supports loại token?
        +-- AuthenticationProvider 2: supports loại token?
        +-- ...
        |
        v
AuthenticationProvider xác minh credentials và account policy
        |
        +-- Success -> trả Authentication ĐÃ xác thực
        +-- Failure -> AuthenticationException
        +-- Không thể quyết định -> null / provider khác
        |
        v
Filter xử lý success/failure, session và SecurityContext
        |
        v
Authorization kiểm authorities trên request tiếp theo
~~~

**`AuthenticationManager` không phải người dùng, không phải nơi lưu session.** Nó là interface cho một lời gọi xác thực. `AuthenticationProvider` là chiến lược làm công việc xác thực cho một loại credential cụ thể. `SecurityFilterChain` chọn các filter và quy tắc HTTP; `SecurityContextHolder` giữ Authentication của phạm vi xử lý hiện tại; `SecurityContextRepository` xử lý persistence khi cần.

### Các thành phần chính

| Thành phần | Vai trò | API phổ biến |
| --- | --- | --- |
| `SecurityFilterChain` | Cấu hình filter nào chạy và quyền HTTP | `http.authorizeHttpRequests(...)`, `http.formLogin(...)` |
| `AuthenticationManager` | Cổng xác thực được filter/controller gọi | `authenticate(Authentication)` |
| `ProviderManager` | Duyệt các AuthenticationProvider | `new ProviderManager(provider)` hoặc List |
| `AuthenticationProvider` | Xác thực một nhóm token | `supports(Class<?>)`, `authenticate(...)` |
| `DaoAuthenticationProvider` | Username/password qua user store | `UserDetailsService` + `PasswordEncoder` |
| `UserDetailsService` | Nạp thông tin user, hash mật khẩu, trạng thái/authorities | `loadUserByUsername(...)` |
| `PasswordEncoder` | So sánh/lưu password hash | `matches(raw, encoded)`, `encode(raw)` |
| `Authentication` | Input token chưa auth hoặc verified identity | `UsernamePasswordAuthenticationToken` |
| `AuthenticationEventPublisher` | Sự kiện thành công/thất bại nếu manager được cấu hình | `DefaultAuthenticationEventPublisher` |
| `SecurityContextRepository` | Lưu context cho HTTP requests kế | `saveContext(...)` |

**Một UserDetailsService không tự so sánh mật khẩu**: `DaoAuthenticationProvider` gọi user service rồi dùng encoder để so sánh submitted password với stored hash. **PasswordEncoder không phải AuthenticationProvider** và **AuthenticationManager không tự phát session cookie**.

## 2. Các mốc phiên bản quan trọng

| Nhánh | Điều thay đổi đáng chú ý | Cách viết được khuyên |
| --- | --- | --- |
| Spring Security 5.4 | Bắt đầu hỗ trợ cấu hình `SecurityFilterChain` bean | Dần tách khỏi inheritance |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` bị deprecate | Component-based beans |
| Spring Security 6.x | Bỏ `WebSecurityConfigurerAdapter`, chuyển Jakarta Servlet, loại nhiều API matchers cũ | `@Bean SecurityFilterChain`, `requestMatchers`, lambda DSL |
| Spring Security 6.5 | Một số constructor/setter cũ của `DaoAuthenticationProvider` đã deprecated | Constructor nhận `UserDetailsService` |
| Spring Security 7.x | Cấu hình lambda DSL là lựa chọn hiện đại; API `DaoAuthenticationProvider(UserDetailsService)` được tài liệu 7.x sử dụng | Duy trì bean-based config, tránh API đã xóa |

Nếu dự án dùng Spring Boot, phiên bản Spring Security thường do dependency management của Boot chọn. **Không tự gắn một version của `spring-security-config` khác version của `spring-security-web`**. Dùng BOM và kiểm dependency tree của ứng dụng.

Nhóm tương thích thường gặp:

- Spring Boot 2.x đi cùng Spring Security 5.x (javax Servlet).
- Spring Boot 3.x đi cùng Spring Security 6.x (Jakarta Servlet).
- Spring Boot 4.x đi cùng Spring Security 7.x (Jakarta Servlet).

Đây là **nhóm tương thích theo thế hệ**, không phải một bảng ghép chính xác mọi minor release. Trước khi nâng, đọc dependency tree/BOM cụ thể và migration guides tương ứng.

### Những đoạn code cũ cần thay

~~~java
// Kiểu Spring Security 5.x, không dùng khi đã nâng lên 6/7:
class SecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests().anyRequest().authenticated();
    }
}
~~~

Việc hiện đại hóa không chỉ xóa `extends`; bạn phải chuyển các khai báo sang beans, chuyển matchers và xem lại authentication wiring. Ví dụ:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

Mảnh này cần imports `@Configuration`, `@EnableWebSecurity`, `@Bean`, `HttpSecurity`, `SecurityFilterChain` và `Customizer`. Không có `WebSecurityConfigurerAdapter` và không override `configure(...)`.

**Không coi `permitAll()`, `web.ignoring()` và `requestMatchers()` giống nhau**: `permitAll()` vẫn qua security filter chain, có thể giữ các headers/CSRF behavior; `web.ignoring()` bỏ qua chain cho request đó. Với login/public endpoints, thường dùng `permitAll()` thay vì loại toàn bộ security filters.

## 3. Khi nào không cần định nghĩa AuthenticationManager bean?

Đối với một ứng dụng form login/HTTP Basic thông thường, bạn có thể chỉ cần:

1. `SecurityFilterChain` để cấu hình HTTP;
2. `UserDetailsService` để lấy user;
3. `PasswordEncoder` để xác minh password hash.

Spring Security có thể xây `DaoAuthenticationProvider` và `AuthenticationManager` nội bộ khi cấu hình phù hợp. **Không phải dự án nào cũng cần viết `@Bean AuthenticationManager`**.

Ví dụ đầy đủ về mặt cấu trúc cho Spring Boot Servlet:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.Customizer;

@Configuration(proxyBeanMethods = false)
public class SimpleSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("training-password-only"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Chạy trong project Spring Boot**, không phải Java class chạy riêng bằng `javac`. Cần starters Spring Web, Spring Security, main `@SpringBootApplication` và route protected. Account `alice` ở đây là **fixture học tập**, không phải ví dụ triển khai mật khẩu production. Không đưa password test vào git của ứng dụng thực; production dùng user store và hashes từ dữ liệu được quản lý.

Lý do code đơn giản:

- `UserDetailsService` chỉ cung cấp UserDetails;
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` xử lý password hash theo định dạng delegating (ví dụ prefix `{bcrypt}` theo cấu hình);
- Spring Security có thể sử dụng built-in provider để hỗ trợ form login;
- Không cần tạo một `ProviderManager` mới trùng với manager framework đang xây.

**Điều kiện cần kiểm:** nếu có nhiều UserDetailsService hoặc nhiều AuthenticationProvider beans, hoặc bạn đã cấu hình AuthenticationManagerBuilder thủ công, auto wiring có thể khác. Đừng giả định mọi bean được tự gom vào cùng một manager; cần xem actual chain và cấu hình, hoặc chủ động khai báo composition tường minh.

## 4. AuthenticationManager và ProviderManager khác nhau thế nào?

`AuthenticationManager` là interface:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
~~~

Đây là biểu diễn rút gọn signature cho mục đích giải thích, **không phải khai báo lại interface trong project**.

`ProviderManager` là implementation phổ biến. Nó có danh sách `AuthenticationProvider`. Mỗi provider xác định qua `supports(Class<?>)` liệu có xử lý loại Authentication hay không.

Quy trình:

~~~text
Request: UsernamePasswordAuthenticationToken
   |
   v
ProviderManager
   |
   +-- DaoAuthenticationProvider.supports(...) -> true
   |        |
   |        +-- credential hợp lệ -> Authentication đã xác thực
   |        +-- sai -> AuthenticationException
   |
   +-- CustomApiKeyProvider.supports(...) -> false (bỏ qua)
   |
   +-- Không provider nào hỗ trợ -> ProviderNotFoundException
~~~

Provider trả `null` nghĩa **không đưa ra quyết định**, cho phép manager thử provider tiếp theo. Nếu một provider đã hỗ trợ nhưng ném exception, manager có logic xử lý tùy loại exception; một số lỗi trạng thái account/dịch vụ có thể chặn việc tiếp tục. Đừng tự giả định mọi exception đều được bỏ qua để thử provider sau hoặc mọi provider cứ trả null là “bad credentials”.

**Thứ tự providers có ý nghĩa** nếu nhiều provider hỗ trợ cùng một Authentication token. Phải xác định ai có quyền xác minh, ai có thể decline, loại exception nào phải dừng flow và có thể bị credential-downgrade hay không.

`ProviderManager` có thể có một parent `AuthenticationManager`. Parent được dùng khi local providers không xử lý được theo contract. Parent/shared manager hữu ích với nhiều filter chains nhưng dễ làm lẫn phạm vi hoặc phát trùng events nếu cấu hình sai.

## 5. Khi nào cần AuthenticationManager @Bean?

Có ba nhu cầu phổ biến:

1. **REST/controller tùy chỉnh** gọi `authenticate(...)` trực tiếp vì không sử dụng filter login sẵn có.
2. Muốn cấu hình **một tập providers rõ ràng** và chính sách như event publisher, credential erasure.
3. Nhiều `SecurityFilterChain` cần manager riêng/local, hoặc một shared manager cho những cơ chế chung.

Ví dụ bean-style đăng tải một manager password:

~~~java
@Bean
AuthenticationManager authenticationManager(
        UserDetailsService userDetailsService,
        PasswordEncoder passwordEncoder) {

    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(passwordEncoder);

    return new ProviderManager(provider);
}
~~~

Đây là **mảnh trong @Configuration**, dùng constructor nhận `UserDetailsService` tương thích Spring Security 6.5 và 7.x. Không dùng `new DaoAuthenticationProvider()` rồi `setUserDetailsService(...)` khi viết code mới; constructor no-arg và setter này đã bị deprecated ở 6.5 và không còn trong API 7.x.

**Một @Bean AuthenticationManager có thể dùng cho injection**, nhưng không kết luận mọi chain tự động chọn đúng instance trong mọi cấu hình phức tạp. Khi muốn chain sử dụng manager đó, hãy wire **tường minh**:

~~~java
@Bean
SecurityFilterChain formChain(
        HttpSecurity http,
        AuthenticationManager authenticationManager) throws Exception {

    return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Không cần khai bean manager trong khi chỉ có một provider và built-in form auth hoạt động đúng; càng nhiều bean tùy biến, càng cần test để tránh manager khác với manager bạn nghĩ.

### Bean scope trong Spring không phải token scope

`AuthenticationManager` và `AuthenticationProvider` thường là **singleton beans** chứa cấu hình/strategies, không phải một bean cho mỗi người dùng. Không lưu raw password, mutable `Authentication` của request hiện tại hoặc user-specific session trong fields của singleton provider.

Mọi yêu cầu xác thực tạo một `Authentication` riêng; chính manager/provider xử lý request. Session và Authentication context sau thành công do filter/controller và repository quản lý, không phải singleton manager giữ “user đang login”.

## 6. Mẫu cấu hình tường minh phù hợp Spring Security 6.5+/7.x

Khi cần bảo đảm đúng manager và đúng provider, bạn có thể dùng mẫu sau cho một ứng dụng Spring Boot Servlet. Đoạn này có định nghĩa beans, imports chính và security chain; **cần Spring Boot runtime, không tự chạy bằng javac**.

Tệp **ExplicitAuthenticationConfig.java**:

~~~java
package demo.security;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ExplicitAuthenticationConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("demo")
                .password(encoder.encode("training-password-only"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(demo);
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService service, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(service);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher events) {
        return new DefaultAuthenticationEventPublisher(events);
    }

    @Bean
    AuthenticationManager authenticationManager(
            DaoAuthenticationProvider dao,
            AuthenticationEventPublisher events) {
        ProviderManager manager = new ProviderManager(dao);
        manager.setAuthenticationEventPublisher(events);
        return manager;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager authenticationManager)
            throws Exception {
        return http
                .authenticationManager(authenticationManager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Điểm cần kiểm ở mẫu này:**

- `DaoAuthenticationProvider(UserDetailsService)` là constructor tương thích 6.5/7.x, có `setPasswordEncoder(...)`.
- `PasswordEncoder` là bean duy nhất để cùng quy tắc hash cho sign-up, password change và login.
- `ProviderManager` chỉ có **một provider** password, không vô tình nhận authentication type khác.
- `ProviderManager#setAuthenticationEventPublisher(...)` được gọi tường minh vì manager mới tự tạo **không tự xuất bản sự kiện theo mặc định**.
- `HttpSecurity.authenticationManager(authenticationManager)` gắn manager vào đúng chain; không phụ thuộc suy luận auto wiring.
- `@Configuration(proxyBeanMethods=false)` dùng method-parameter injection, không gọi trực tiếp @Bean method của nhau; tránh lỗi khi config class không proxy methods.
- `formLogin(...)` dùng filter chuẩn, có trách nhiệm xử lý thành công/thất bại, security context và session strategy theo framework.
- InMemory user/password chỉ phục vụ **demo/test**; không ghi credential cố định vào production.

Nếu Spring Boot đã tự tạo một `UserDetailsService` hoặc application có nhiều user stores, kiểm có **trùng bean** không. Khi cấu hình custom ProviderManager, không thêm một DaoAuthenticationProvider trùng bằng builder khác mà không định nghĩa thứ tự và mục tiêu.

## 7. Cách lấy AuthenticationManager để dùng trong custom REST login

Trong một controller/service do Spring quản lý, có thể inject bean:

~~~java
@RestController
@RequestMapping("/auth")
public class LoginController {

    private final AuthenticationManager manager;

    public LoginController(AuthenticationManager manager) {
        this.manager = manager;
    }

    @PostMapping("/verify")
    public String verify(@RequestBody LoginRequest request) {
        Authentication unauthenticated =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        request.username(), request.password());

        Authentication verified =
                manager.authenticate(unauthenticated);

        return "Authentication verified for " + verified.getName();
    }

    public record LoginRequest(String username, String password) {}
}
~~~

Đây là **mảnh Spring MVC**, cần các imports và SecurityFilterChain cho `POST /auth/verify`; không chạy độc lập. **Nó chỉ biểu diễn bước kiểm credentials**, chưa triển khai một login API an toàn đầy đủ. Đặc biệt:

1. Không trả `verified.getName()` trong API công khai nếu chính sách privacy không cho phép.
2. Không log request body/password.
3. Nếu muốn **session-based login**, sau authenticate cần xây context mới, gọi `SecurityContextHolder.setContext(...)` và `SecurityContextRepository.saveContext(context, request, response)` trước response commit; thực hiện session fixation strategy phù hợp.
4. Nếu muốn **token-based login**, sau authenticate phải cấp token theo hệ thống token service được thiết kế và ký/xác minh an toàn; request sau tự gửi Bearer token. Không tự tạo session nếu API đã định nghĩa stateless.
5. Cần CSRF cho những flow dựa cookie/session, anti-brute-force/rate limiting, failure handler không để lộ user existence và xử lý transaction/session lifecycle.
6. Những điều này là lý do ưu tiên filter auth chuẩn khi tính năng tương đương đã được Spring Security hỗ trợ.

**Gọi `AuthenticationManager.authenticate(...)` không tự động login cho HTTP request tiếp theo**. Manager xác minh; filter/controller sở hữu việc đặt context và lưu trạng thái.

## 8. Phân biệt authentication token đầu vào và kết quả

Với username/password, các giá trị điển hình:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);

Authentication result = authenticationManager.authenticate(request);

if (!result.isAuthenticated()) {
    throw new IllegalStateException("Provider did not authenticate");
}
~~~

Đây là mảnh Java trong Spring app. `username`/`rawPassword` lấy từ request chưa tin cậy; không tự làm:

~~~java
// Cực kỳ nguy hiểm: tự gán authorities trước khi kiểm credentials!
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN")));
~~~

Factory `authenticated(...)` hoặc constructor ba tham số chỉ dùng khi **một provider/trust boundary đáng tin đã xác minh**. Không được trả một token đã được đánh dấu authenticated chỉ vì client gửi field `role=ADMIN`.

Khi thành công, `DaoAuthenticationProvider` thường trả `UsernamePasswordAuthenticationToken` với `principal` là `UserDetails` và authorities lấy từ nguồn identity đáng tin. Trong Spring Security 7, một số cơ chế xác thực có thêm factor authority như `FACTOR_PASSWORD` cho mô hình multi-factor; vì thế test chỉ so sánh **exact list of authorities** có thể giòn khi upgrade. Test vai trò cần thiết theo policy, không mặc định danh sách authorities không bao giờ có thêm phần tử.

**Không giữ raw password lâu hơn cần thiết.** `ProviderManager` mặc định cố xóa credentials khỏi Authentication thành công qua `CredentialsContainer`. Nếu cache chia sẻ cùng UserDetails object, việc xóa có thể ảnh hưởng cache; giải pháp thường là copy/không cache password object, không phải tắt `eraseCredentialsAfterAuthentication` toàn cục một cách tùy tiện.

## 9. AuthenticationProvider.supports(...) có ý nghĩa chính xác gì?

Interface trọng tâm:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;

    boolean supports(Class<?> authentication);
}
~~~

Đây là signature rút gọn để học; không khai báo lại interface trùng với Spring.

- `supports(TokenType.class) == true`: provider **có khả năng** xử lý loại Authentication đó, không có nghĩa chắc chắn sẽ xác thực thành công.
- `authenticate(...)` trả một `Authentication` đã xác thực nếu kiểm chứng thành công.
- Trả `null` nghĩa provider không đưa ra quyết định cho request này; `ProviderManager` có thể thử provider khác.
- Ném `AuthenticationException` nghĩa xác thực thất bại; cách manager xử lý và có thử tiếp hay không phụ thuộc loại exception/cấu hình.
- `supports(...)` false cho toàn bộ providers (và parent không xử lý) thường dẫn đến `ProviderNotFoundException`.

**Đừng viết provider trả authenticated token cho mọi token type**, hoặc một provider `supports(Authentication.class)` rất rộng mà bỏ qua loại credential. Điều này dễ làm request loại khác được đi qua sai hệ thống xác minh.

### Provider cho nhiều loại credential

Giả sử ứng dụng có:

- `DaoAuthenticationProvider` cho username/password;
- Một `ServiceKeyAuthenticationProvider` cho service API key đã được cấp/quản lý;
- OAuth2 resource server cho Bearer JWT, thường được cấu hình bằng `oauth2ResourceServer()` thay vì viết lại validation của JWT.

Nếu bạn cố gom cả ba vào một `ProviderManager`, phải xác định rõ loại token và flow/filter nào tạo token. Nhiều trường hợp nên **tách SecurityFilterChain** theo routes và protocol, đặc biệt giữa browser session login và stateless API.

## 10. Tạo custom AuthenticationProvider an toàn

Tình huống học tập: một backend nhận credential dành cho service-to-service, không phải username/password. Một custom provider nên hỗ trợ **token riêng** chứ không cố tái dùng `UsernamePasswordAuthenticationToken` rồi đoán ý nghĩa password field.

Mảnh code minh họa, trong dự án Spring Security (chưa thể chạy độc lập vì cần `ServiceCredentialVerifier` và implementation token):

~~~java
public final class ServiceKeyAuthenticationProvider
        implements AuthenticationProvider {

    private final ServiceCredentialVerifier verifier;

    public ServiceKeyAuthenticationProvider(
            ServiceCredentialVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        if (!(authentication instanceof ServiceKeyAuthenticationToken keyToken)) {
            return null;
        }

        String presentedKey = (String) keyToken.getCredentials();
        ServiceIdentity identity = verifier.verify(presentedKey);

        if (identity == null) {
            throw new BadCredentialsException("Invalid credentials");
        }

        // Chỉ SAU xác minh thành công mới dựng token authenticated.
        return ServiceKeyAuthenticationToken.authenticated(
                identity.id(), identity.authorities());
    }

    @Override
    public boolean supports(Class<?> tokenType) {
        return ServiceKeyAuthenticationToken.class.isAssignableFrom(tokenType);
    }
}
~~~

`ServiceCredentialVerifier`, `ServiceIdentity` và `ServiceKeyAuthenticationToken` là **các kiểu ứng dụng phải định nghĩa**; đoạn này là pseudocode framework rõ ràng, không có ý giả vờ API Spring cung cấp `ServiceKeyAuthenticationToken.authenticated(...)` sẵn. Khi triển khai thật:

1. Xây token subclass `AbstractAuthenticationToken` với trạng thái unauthenticated và authenticated rõ.
2. Chỉ filter ở endpoint service-key mới tạo token unauthenticated từ header được quy định.
3. Ưu tiên lưu **verifier** của key trong kho tin cậy; kiểm bằng cơ chế mật mã, constant-time comparison phù hợp, key rotation/revocation.
4. `AuthenticationProvider` không nhận authorities do client tự gửi.
5. Không log raw key, không trả về client sự khác nhau giữa key không tồn tại và sai.
6. Implement `eraseCredentials()`/`CredentialsContainer` khi cần để xóa secret.
7. Bảo đảm provider `supports(...)` đúng token class, không bỏ qua các policy account/service status.
8. Với Bearer JWT chuẩn, ưu tiên `oauth2ResourceServer().jwt(...)` và `JwtDecoder` đúng issuer/audience, tránh một custom provider tự parse token thiếu kiểm chữ ký.

## 11. Ghép nhiều providers tường minh

Một cách tổ chức:

~~~java
@Bean
AuthenticationManager authenticationManager(
        DaoAuthenticationProvider passwordProvider,
        ServiceKeyAuthenticationProvider serviceKeyProvider,
        AuthenticationEventPublisher publisher) {

    ProviderManager manager = new ProviderManager(
            List.of(serviceKeyProvider, passwordProvider));
    manager.setAuthenticationEventPublisher(publisher);
    return manager;
}
~~~

Mảnh code cần import `java.util.List`, các provider beans có thật và Spring context. Thứ tự có thể chọn theo policy; mỗi provider phải hỗ trợ đúng token type. Nếu đưa provider mới vào manager nhưng không có filter/controller tạo `ServiceKeyAuthenticationToken`, endpoint vẫn không thể tự xác thực key.

**Không đăng ký hai provider cho cùng password token chỉ để “fallback nếu provider A nói sai”** nếu điều đó cho phép downgrade. Ví dụ một directory chính từ chối account disabled thì không được tùy tiện thử local fallback để đăng nhập account bị disable. Có các `AuthenticationException` như `AccountStatusException` mà manager xử lý theo chính sách đặc biệt; hãy test trường hợp thực, không giả sử “cứ lỗi là thử B”.

Nếu nhiều providers cho các tổ chức/tenants, nên route tới provider đúng dựa trên tenant context **đã được xác minh** và không tin domain/tenantId từ request để tự cấp quyền.

## 12. Global manager và local manager của SecurityFilterChain

Có hai phạm vi cần tách:

**Global AuthenticationManager bean**

~~~java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationProvider provider) {
    return new ProviderManager(provider);
}
~~~

Hữu ích cho các components cần injection trực tiếp và có contract dùng chung. Nhưng một ứng dụng nhiều chains có thể cần lựa chọn khác nhau.

**Local AuthenticationManager cho một chain**

~~~java
@Bean
SecurityFilterChain adminChain(
        HttpSecurity http,
        AuthenticationManager adminManager) throws Exception {

    return http
            .securityMatcher("/admin/**")
            .authenticationManager(adminManager)
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().hasRole("ADMIN"))
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Đoạn này giả định `adminManager` đã được định nghĩa với provider phù hợp username/password cho Basic. Không dùng manager service-key với Basic rồi ngạc nhiên vì `ProviderNotFoundException`.

**Quan trọng:** `@Bean AuthenticationManager` không có nghĩa mọi chain luôn lấy bean ấy theo cùng cách khi bạn có các local overrides và configuration tự động. Muốn biết chính xác filter chain A dùng provider nào, hãy kiểm integration test và wiring ở runtime. Khi có nhiều beans cùng type, dùng `@Qualifier` hoặc tên rõ ràng để không tiêm nhầm.

## 13. Nhiều SecurityFilterChain: giới hạn đường dẫn rõ ràng

Ứng dụng có thể dùng session form login cho web và JWT cho API:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/login", "/error").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Đây là cấu hình Spring Security Servlet, cần `JwtDecoder`/JWK configuration và OAuth2 resource server dependency cho API. `@Order` từ Spring Core; `securityMatcher("/api/**")` giới hạn chain API, còn chain browser là fallback. Mỗi request khớp **một SecurityFilterChain được chọn theo thứ tự**, không phải mọi chains chạy nối nhau.

Phân biệt:

- `securityMatcher(...)` quyết định **toàn bộ chain** có áp dụng với request không.
- `requestMatchers(...)` trong `authorizeHttpRequests` quyết định **quyền bên trong chain đã được chọn**.
- `http.authenticationManager(manager)` quyết định manager **của chain đang xây**.
- `anyRequest().authenticated()` không xác minh password; authentication filters làm việc đó.

Với mẫu trên, đăng nhập form tạo HTTP session cho browser **không khiến /api/** tự cho phép gọi thiếu Bearer**. Đây là kết quả đúng của kiến trúc stateless API, không phải Spring Security “mất user”.

**CSRF/CORS** phải được xét theo từng loại client. Session-based browser flow thường cần CSRF; API JWT stateless có thể có chính sách khác nhưng không được tắt CSRF rộng rãi chỉ để một test pass.

## 14. Vì sao AuthenticationConfiguration.getAuthenticationManager() đôi khi được dùng?

Nhiều hướng dẫn Spring Security 6.x viết:

~~~java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration config) throws Exception {
    return config.getAuthenticationManager();
}
~~~

Ý tưởng là **expose global manager do Spring Security đã xây** cho injection vào component tùy chỉnh. Nó có thể phù hợp khi manager global đã được cấu hình qua user store/provider/builder và bạn muốn tham chiếu đúng instance.

Nhưng đây **không phải câu thần chú cho mọi project**:

- Nếu đã tự tạo `@Bean AuthenticationManager` khác, có thể gây bean ambiguity hoặc vòng phụ thuộc tùy config.
- Nếu nhiều `SecurityFilterChain` dùng local manager, global manager này không đại diện tất cả chains.
- Nếu provider hoặc bean wiring chưa có, lấy manager không tự sinh implementation bạn mong muốn.
- Trong phiên bản khác, cách cấu hình global manager và auto configuration có thể thay đổi.

**Khuyến nghị:** nếu dự án chỉ dùng built-in form login với một user store, không expose manager khi không cần. Nếu REST/controller cần manager, dùng cấu hình explicit `ProviderManager(DaoAuthenticationProvider)` như tài liệu 7.x hoặc expose manager thực đã được Spring xây **sau khi xác minh dependency graph**. Tránh vừa dùng hai pattern trong cùng application mà không có lý do rõ.

## 15. AuthenticationManagerBuilder có còn nên dùng không?

`AuthenticationManagerBuilder` vẫn xuất hiện trong một số tài liệu/cấu hình vì cần tinh chỉnh global manager, nhưng hướng kiến trúc hiện đại là **bean composition** khi có thể.

Các dấu hiệu cấu hình cũ cần review:

~~~java
// Hình minh họa API đời trước:
protected void configure(AuthenticationManagerBuilder auth) throws Exception {
    auth.inMemoryAuthentication()
        .withUser("user")
        .password("{noop}password")
        .roles("USER");
}
~~~

Đoạn này gắn với `WebSecurityConfigurerAdapter` cũ và không phải mẫu dùng trong Spring Security 6/7. Thay bằng `InMemoryUserDetailsManager` hoặc `JdbcUserDetailsManager` bean và encoder phù hợp.

Khi có custom provider, đừng kéo toàn bộ app quay lại builder DSL chỉ để đăng ký nó. Thay vào đó có thể khai provider bean và một explicit `ProviderManager`, hoặc đăng ký qua DSL được version hỗ trợ khi policy rõ. Sử dụng map/chains và bean scopes để test dễ hơn.

## 16. Credential erasure, cache và password hashing

`ProviderManager` theo mặc định có thể xóa credentials khỏi Authentication thành công để giảm thời gian giữ secret trong bộ nhớ. Điều này liên quan `CredentialsContainer`.

Ví dụ cạm bẫy:

~~~text
UserDetailsService trả đúng object cached UserDetails
     |
     v
ProviderManager trả Authentication tham chiếu đến cùng object
     |
     v
eraseCredentials() làm mất password hash trên object cached
     |
     v
Lần đăng nhập sau cache trả user đã bị xóa password
     |
     v
Password verification gặp lỗi
~~~

Giải pháp ưu tiên:

- Không cache mutable object chứa password bị dùng chung ngoài ý định.
- Tạo copy phù hợp khi đưa UserDetails vào Authentication.
- Sử dụng caching strategy/framework hỗ trợ đúng semantics.
- Test nhiều lần đăng nhập liên tiếp, sau update mật khẩu và cache eviction.
- Không tắt `eraseCredentialsAfterAuthentication` toàn cục trừ khi đã đánh giá rủi ro kỹ.

**Dùng PasswordEncoder đúng vai trò**:

~~~java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

String storedHash = encoder.encode("password-used-only-for-test");

boolean matches = encoder.matches(
        "password-used-only-for-test", storedHash);
~~~

`DelegatingPasswordEncoder` cho phép định dạng hash mang algorithm prefix, hỗ trợ tiến hóa policy. Trong production, mật khẩu mới phải được hash theo cấu hình phù hợp, tuyệt đối không lưu plaintext hoặc dùng `{noop}` cho user thật. Khi thay algorithm/cost, lập kế hoạch rehash trên đăng nhập/đổi mật khẩu, không coi “password mã hóa giống hệt mỗi lần” là yêu cầu (salt làm output thay đổi).

## 17. Authentication events khi tự tạo ProviderManager

Một lỗi vận hành: ứng dụng có `@EventListener(AuthenticationFailureBadCredentialsEvent.class)` nhưng không thấy sự kiện dù authentication thất bại. Nếu bạn tự khởi tạo:

~~~java
ProviderManager manager = new ProviderManager(daoProvider);
~~~

theo Javadoc, event publisher mặc định của manager tự dựng có thể là **no-op**. Nếu cần events, đăng ký:

~~~java
DefaultAuthenticationEventPublisher publisher =
        new DefaultAuthenticationEventPublisher(applicationEventPublisher);

manager.setAuthenticationEventPublisher(publisher);
~~~

Mảnh trên cần Spring `ApplicationEventPublisher` từ context. Không log raw password/Authentication object/exception details khi bắt events; dùng event type, reason code, opaque request ID và PII policy.

**Parent manager có thể gây event trùng.** Khi manager con publish event cho exception/result từ parent, nếu parent cũng publish, một attempt có thể tạo nhiều events. Định nghĩa rõ một điểm chịu trách nhiệm và test số event thực tế.

Custom `AuthenticationException` không tự hưởng mapping của superclass trong `DefaultAuthenticationEventPublisher` vì matching theo concrete class. Khi cần metrics đúng loại failure, thêm mapping tường minh hoặc fallback event thích hợp.

## 18. Java 17 độc lập: mô phỏng chọn provider theo loại token

Chương trình này không dùng Spring, không triển khai credential hashing và **không được dùng để xác thực thật**. Nó chỉ mô phỏng ý tưởng: manager nhận một request typed, tìm provider có `supports` thích hợp, và chỉ provider đó xác minh. Spring `ProviderManager` có xử lý null/exception/parent khác phức tạp hơn.

Tạo file **ProviderSelectionDemo.java**:

~~~java
import java.util.List;

public class ProviderSelectionDemo {

    sealed interface LoginRequest
            permits PasswordLogin, ServiceKeyLogin, UnknownLogin {}

    record PasswordLogin(String user, String password)
            implements LoginRequest {}

    record ServiceKeyLogin(String key) implements LoginRequest {}

    record UnknownLogin() implements LoginRequest {}

    interface Provider {
        boolean supports(LoginRequest request);
        String authenticate(LoginRequest request);
    }

    static class PasswordProvider implements Provider {
        public boolean supports(LoginRequest request) {
            return request instanceof PasswordLogin;
        }

        public String authenticate(LoginRequest request) {
            PasswordLogin login = (PasswordLogin) request;
            return "alice".equals(login.user())
                    && "training-only".equals(login.password())
                    ? "USER:alice" : "DENIED";
        }
    }

    static class ServiceKeyProvider implements Provider {
        public boolean supports(LoginRequest request) {
            return request instanceof ServiceKeyLogin;
        }

        public String authenticate(LoginRequest request) {
            ServiceKeyLogin login = (ServiceKeyLogin) request;
            return "demo-key".equals(login.key())
                    ? "SERVICE:worker-a" : "DENIED";
        }
    }

    static String authenticate(List<Provider> providers, LoginRequest request) {
        for (Provider provider : providers) {
            if (provider.supports(request)) {
                return provider.authenticate(request);
            }
        }
        return "NO_PROVIDER";
    }

    public static void main(String[] args) {
        List<Provider> providers =
                List.of(new ServiceKeyProvider(), new PasswordProvider());

        System.out.println("Password login = "
                + authenticate(providers,
                        new PasswordLogin("alice", "training-only")));

        System.out.println("Service key = "
                + authenticate(providers, new ServiceKeyLogin("demo-key")));

        System.out.println("Invalid password = "
                + authenticate(providers, new PasswordLogin("alice", "bad")));

        System.out.println("Unsupported token = "
                + authenticate(providers, new UnknownLogin()));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac ProviderSelectionDemo.java
java ProviderSelectionDemo
~~~

Stdout chính xác:

~~~text
Password login = USER:alice
Service key = SERVICE:worker-a
Invalid password = DENIED
Unsupported token = NO_PROVIDER
~~~

**Lưu ý về phạm vi:** chương trình so sánh secret bằng chuỗi cố định chỉ để output dễ tái lập; **không bảo vệ mật khẩu/API key thật**, không có hash, constant-time comparison, credential erasure, account policy, events hoặc SecurityContext. Trong Spring Security thật, dùng `DaoAuthenticationProvider`/`PasswordEncoder` và một verifier quản lý service key an toàn. Bài học của lab là **không để password provider xử lý service token hoặc ngược lại**.

## 19. Unit test trực tiếp AuthenticationManager bean

Thay vì chỉ test controller có `@WithMockUser`, hãy gọi **bean manager** với credentials test để chứng minh provider wiring thực sự hoạt động.

Ví dụ JUnit 5 + Spring Boot Test, dùng cấu hình `ExplicitAuthenticationConfig` ở mục 6 và user `demo`:

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class AuthenticationManagerBeanTest {

    @Autowired
    AuthenticationManager manager;

    @Test
    void acceptsCorrectPassword() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "demo", "training-password-only");

        Authentication result = manager.authenticate(request);

        assertTrue(result.isAuthenticated());
        assertEquals("demo", result.getName());
        assertTrue(result.getAuthorities().stream()
                .anyMatch(a -> a.getAuthority().equals("ROLE_USER")));
    }

    @Test
    void rejectsWrongPassword() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "demo", "wrong-password");

        assertThrows(BadCredentialsException.class,
                () -> manager.authenticate(request));
    }
}
~~~

Test này cần Spring Boot project với beans của ví dụ và JUnit 5. Nó xác minh **manager + DAO provider + password encoder** thực tế đã nối vào nhau; không tự kiểm Servlet cookies, CSRF hay session persistence.

Nếu dùng authentication factors trong Spring Security 7, tránh assert authorities chỉ bằng một danh sách chính xác cố định; xác minh vai trò `ROLE_USER` cùng các yêu cầu bảo mật riêng theo phiên bản.

### MockMvc cho filter chain

Bổ sung test:

~~~java
mvc.perform(formLogin("/login")
        .user("demo")
        .password("training-password-only"))
    .andExpect(authenticated().withUsername("demo"));

mvc.perform(formLogin("/login")
        .user("demo")
        .password("wrong-password"))
    .andExpect(unauthenticated());
~~~

Đây là **mảnh Spring Security Test**, cần MockMvc đã áp `springSecurity()` và static imports `formLogin`, `authenticated`, `unauthenticated`. Với cấu hình form login chuẩn, kiểm HTTP behavior và follow session ở request B bằng `MockHttpSession`, **không dùng `with(user(...))` để giả làm bằng chứng password provider đã chạy**.

Nếu API dùng JSON login custom, dùng MockMvc POST JSON + CSRF khi cần, verify response và lưu context/token theo contract. Đừng test một chain rồi suy mọi chain còn lại đều đã nhận đúng manager.

## 20. Kiểm thử local managers và nhiều authentication types

Ma trận kiểm thử nên bao gồm:

| Test | Kỳ vọng |
| --- | --- |
| Bean SecurityFilterChain tồn tại | FilterChainProxy có chain được chọn cho route |
| Một UserDetailsService + encoder hợp lệ | Password provider xác minh đúng |
| Wrong password | AuthenticationException, không có authenticated token |
| Account disabled/locked | Bị từ chối theo policy đúng, không fallback trái phép |
| Custom token type | Chỉ provider hỗ trợ mới xử lý |
| Không có provider cho token | ProviderNotFoundException trong Spring manager |
| Hai providers supports cùng class | Thứ tự và exception/fallthrough như thiết kế |
| Parent AuthenticationManager | Chỉ dùng khi phù hợp, không bypass policy |
| Manual ProviderManager | Event publisher có được gắn nếu cần |
| SecurityFilterChain local manager | HTTP request chọn đúng manager |
| REST controller inject manager | Cùng instance/cấu hình mong muốn |
| Username/password auto config | Không tạo provider trùng/bean ambiguity |
| Nhiều `UserDetailsService` beans | Không dựa auto selection mơ hồ |
| Password hash không đúng id/algorithm | Bị từ chối; lỗi cấu hình được chẩn đoán |
| Credential erasure + user cache | Login nhiều lần vẫn đúng |
| Form login → request sau | Session/context được lưu và khôi phục |
| Stateless API thiếu Bearer | 401 mong đợi, không nhận cookie auth |
| Session/API chain matchers | Không dùng nhầm filter chain |
| Custom failure event | Mapping đúng, không leak credentials |
| Upgrade 6.5 → 7.x | No-arg DaoAuthenticationProvider không còn; code constructor mới hoạt động |

Đừng chỉ viết một test có `@WithMockUser` rồi kết luận manager đã được cấu hình đúng: mock user có thể tạo Authentication trực tiếp mà không đi qua password provider.

## 21. Những lỗi thường gặp khi nâng phiên bản

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `WebSecurityConfigurerAdapter cannot be resolved` | Đã bị bỏ trong Spring Security 6 | Chuyển @Bean SecurityFilterChain |
| `antMatchers(...) cannot be resolved` | API matcher cũ bị loại | Dùng `requestMatchers(...)` / `securityMatcher(...)` đúng chỗ |
| `javax.servlet... cannot be resolved` | Spring Boot 3+/Jakarta migration | Dùng `jakarta.servlet.*` |
| `DaoAuthenticationProvider()` không còn constructor | Spring Security 7 bỏ no-arg constructor | Dùng `new DaoAuthenticationProvider(userDetailsService)` |
| `setUserDetailsService(...)` không còn | Setter cũ bị deprecated/removed | Inject UserDetailsService trong constructor |
| Controller không inject được AuthenticationManager | Chưa expose bean hoặc bean ambiguity | @Bean tường minh, @Qualifier đúng |
| Đã khai provider bean nhưng filter không dùng | Manager/chain wiring không đúng | Kiểm `http.authenticationManager(...)` |
| Exception `ProviderNotFoundException` | Token type không provider nào supports | Kiểm supports và chain |
| Login thành công nhưng request sau anonymous | Manager chỉ xác minh, chưa save context/session | Kiểm SecurityContextRepository và cookie |
| Password đúng nhưng BadCredentialsException | Encoder/hash id, user store, account policy | Kiểm match/encoded hash, không log raw password |
| Hai chains đều match /api | Order/matcher chưa đúng | Specific chain đứng trước fallback |
| AuthenticationFailureEvent không tới listener | Manual ProviderManager default publisher no-op | Gắn AuthenticationEventPublisher |
| Event bị nhân đôi | Parent/child manager publish cùng attempt | Quy định nơi publish, test count |
| Credential cache bị mất hash sau login | ProviderManager erases credentials | Tránh shared mutable cached UserDetails |
| Bean circular dependency | @Bean method gọi chéo/config dựa vào manager quá sớm | Constructor/method injection, tách wiring |
| REST Login bean chạy nhưng HTTP Basic sai | REST manager khác chain manager | Wiring tường minh, test cả hai |
| Stateless endpoint không nhận session user | API cố ý yêu cầu Bearer per request | Gửi token, không đổi stateful bừa |
| Lỗi 403 sau auth | Authorization hoặc CSRF, không phải provider | Kiểm authorities/CSRF riêng |

**Không sửa bằng cách tắt CSRF, bật `anyRequest().permitAll()`, tự tạo authenticated token hoặc đổi toàn app sang STATELESS/ALWAYS mà chưa chẩn đoán.** Những cách này thường chỉ giấu nguyên nhân và phá ranh giới bảo mật.

## 22. Khi nào không nên tự tạo ProviderManager?

Mặc dù tạo `new ProviderManager(...)` rất đơn giản, nó tăng trách nhiệm:

- Phải truyền đúng danh sách providers, đúng token types, thứ tự/parent policy;
- Phải gắn event publisher nếu muốn authentication events;
- Phải cân nhắc credential erasure/cache;
- Phải wire nó vào **đúng SecurityFilterChain**;
- Phải tích hợp session strategy và context persistence trong custom login;
- Phải kiểm cả password failures, account status, multi-factor requirements;
- Phải tránh tạo bean trùng với default manager mà framework đã xây.

Nếu chỉ dùng username/password chuẩn, `UserDetailsService` + `PasswordEncoder` + `SecurityFilterChain` là đường đi dễ bảo trì hơn. Nếu dùng LDAP, SAML, OAuth2/OIDC, JWT hoặc passkey, ưu tiên cơ chế chuyên dụng của Spring Security trước khi tự làm provider mới.

**Cần custom provider khi có một giao thức/loại credential thật sự tùy biến**, không phải vì muốn sửa HTTP error page hoặc controller route. Đổi giao diện login nên làm ở handler/filter/entry point phù hợp; đổi cách lấy user có thể chỉ cần custom UserDetailsService.

## 23. Những quyết định quan trọng cho Spring Boot production

1. **Authentication method:** password, LDAP/AD, SAML, OIDC, JWT, API key hay nhiều cơ chế?
2. **State model:** browser session hay stateless Bearer? Một request có thể đến nhiều chains không?
3. **Credential storage:** password hash ở đâu; PasswordEncoder policy/rehash và credential rotation?
4. **Manager composition:** dùng auto manager hay @Bean tường minh; ai chịu trách nhiệm wiring?
5. **Provider boundaries:** hỗ trợ token class nào, lỗi nào phải chặn fallback?
6. **Events và audit:** có cần audit; ai publish; tránh duplicate/PII leak?
7. **Context persistence:** login flow chuẩn hay custom; save trước response commit?
8. **Method/HTTP authorization:** user đã auth vẫn phải được kiểm quyền theo resource/tenant.
9. **Testing:** test beans, provider dispatch, filter chain, session, stateless API, CSRF/CORS và regression khi upgrade.
10. **Dependencies:** dùng Spring Boot BOM, Java/Jakarta versions phù hợp, kiểm API deprecations trước khi nâng.

### Checklist tự rà soát cấu hình

- Tôi có cần định nghĩa AuthenticationManager bean không, hay Spring Security đã làm đủ?
- Nếu định nghĩa, manager đó có phải **instance filter chain thực sự sử dụng**?
- Provider nào supports `UsernamePasswordAuthenticationToken`? Custom token nào có provider khác?
- DaoAuthenticationProvider có dùng **constructor nhận UserDetailsService** và PasswordEncoder hợp lệ?
- UserDetailsService chỉ load user, không tự “authenticate” password sai?
- Tôi đã tránh `WebSecurityConfigurerAdapter` và `antMatchers` ở Spring Security 6/7?
- Tôi có bảo vệ password/credentials, không giữ raw secret trong Authentication hoặc log?
- Tôi có test custom manager cần event publisher, không trùng events với parent?
- Tôi đã kiểm HTTP session persistence **riêng** với xác thực credential?
- Cấu hình `SecurityFilterChain` có matchers/order đúng và không lẫn browser/API?
- Với upgrade, tôi đã đối chiếu API Java thực tế của dependency được resolve?

**Kết luận:** Cấu hình Spring Security hiện đại nên bắt đầu từ **các bean có trách nhiệm rõ**: `SecurityFilterChain` cho HTTP, `UserDetailsService` + `PasswordEncoder` cho password, `AuthenticationProvider` cho việc xác minh một loại credential và `AuthenticationManager/ProviderManager` khi thực sự cần composition hoặc injection. Không nhầm manager với session; không coi mọi provider bean tự đi vào mọi filter chain; không tái dùng API bị loại sau `WebSecurityConfigurerAdapter`. Một cấu hình explicit có thể dài hơn vài dòng nhưng dễ kiểm thử, nâng phiên bản và bảo vệ ranh giới xác thực hơn.

### Tài liệu tham khảo chính thức

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Username/Password Authentication (Publish an AuthenticationManager Bean): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — DaoAuthenticationProvider API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security — ProviderManager API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security — Servlet Configuration and Multiple Chains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Password Storage and DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — SecurityContext Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security — MockMvc Authentication Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security Engineering — Without WebSecurityConfigurerAdapter: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter/
- Spring Security 6.5 DaoAuthenticationProvider API (deprecated constructors): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
