# Phân biệt nhiều AuthenticationProvider trong một AuthenticationManager với nhiều SecurityFilterChain

> **Kết luận cốt lõi:** **Nhiều AuthenticationProvider trong một AuthenticationManager** giải quyết câu hỏi **“Bằng chứng đăng nhập này được kiểm tra bằng cách nào?”**. **Nhiều SecurityFilterChain** giải quyết câu hỏi **“HTTP request này phải đi qua tập filter và chính sách bảo mật nào?”**. Hai cách tổ chức hoạt động ở **hai tầng khác nhau**, có thể dùng riêng hoặc kết hợp trong cùng một ứng dụng Spring Security.

## 1. Bức tranh tổng thể

Với ứng dụng **Spring Security Servlet**, một request đi qua **FilterChainProxy** trước khi đến Spring MVC. Proxy xem danh sách **SecurityFilterChain** theo thứ tự ưu tiên và chọn **chain đầu tiên** khớp request. Bên trong chain, filter xác thực thích hợp (ví dụ **BasicAuthenticationFilter**, **UsernamePasswordAuthenticationFilter** hoặc filter tự viết) tạo một đối tượng **Authentication** chưa xác thực, rồi gọi **AuthenticationManager**. Nếu manager là **ProviderManager**, nó hỏi các **AuthenticationProvider** phù hợp để xác minh bằng chứng.

~~~text
HTTP request: GET /api/me, Authorization: Basic ...
                 |
                 v
     DelegatingFilterProxy
                 |
                 v
       FilterChainProxy
                 |
           xem các chain
         theo thứ tự @Order
                 |
                 +-- SecurityFilterChain #1: /api/**  <-- khớp đầu tiên
                 |      |
                 |      +-- SecurityContext / CSRF / ... / BasicAuthenticationFilter
                 |                                         |
                 |                                 tạo Authentication
                 |                                         |
                 |                                         v
                 |                                 AuthenticationManager
                 |                                         |
                 |                                  ProviderManager
                 |                                    /        \
                 |                        PasswordProvider   ApiKeyProvider
                 |                        (token user/pass)  (token API key)
                 |                                    \        /
                 |                              kết quả xác thực
                 |                                         |
                 |                               AuthorizationFilter
                 |                                         |
                 |                                         v
                 |                                  MVC controller
                 |
                 +-- SecurityFilterChain #2: fallback (không chạy trong request trên)
~~~

**Điều quyết định ở hai chỗ khác nhau:**

- **FilterChainProxy** so khớp **HttpServletRequest** qua **RequestMatcher** của chain. Đó là việc chọn *tập filter*.
- **ProviderManager** nhận **Authentication object** do filter tạo và hỏi provider nào có thể kiểm tra *loại bằng chứng*. Đây là việc chọn *nơi xác minh credential*.
- **AuthorizationFilter** (hoặc cơ chế phân quyền đã cấu hình) kiểm tra những gì principal đã xác thực được phép làm. Chọn đúng chain hoặc xác thực thành công không đồng nghĩa có đủ quyền.

Không nên gọi chung cả hai là “chọn phương thức đăng nhập” rồi dùng lẫn **@Order**, **supports(...)**, **securityMatcher(...)** và **requestMatchers(...)**.

## 2. Bảng so sánh chính xác

| Khía cạnh | Nhiều AuthenticationProvider trong một manager | Nhiều SecurityFilterChain |
| --- | --- | --- |
| Đơn vị điều phối | **ProviderManager** (một triển khai AuthenticationManager) | **FilterChainProxy** |
| Dữ liệu dùng để lựa chọn | **Authentication**: class token, credential và logic provider | **HttpServletRequest**: path, method, header hoặc điều kiện RequestMatcher |
| Điểm mở rộng | **AuthenticationProvider.authenticate(...)** và **supports(...)** | **SecurityFilterChain** bean, **HttpSecurity**, **securityMatcher(...)**, **@Order** |
| Câu hỏi chính | “Ai/điều gì xác minh bằng chứng này?” | “Request này áp dụng chuỗi filter, đăng nhập, session, CSRF và authorization nào?” |
| Thứ tự | Danh sách provider do ProviderManager duyệt; kết quả/exception ảnh hưởng việc thử tiếp | Danh sách chain theo thứ tự ưu tiên; **chain khớp đầu tiên** được chọn |
| Nếu không khớp | Có thể **ProviderNotFoundException** nếu không provider nào xác thực và không có parent phù hợp | Nếu **không chain nào khớp**, request **không được Spring Security bảo vệ** |
| Có thể có nhiều kết quả được áp dụng? | Một lần authenticate có thể tham khảo nhiều provider nhưng cuối cùng trả **một Authentication thành công** hoặc thất bại | Một request được **một** SecurityFilterChain của FilterChainProxy xử lý, không ghép filter các chain còn lại |
| Nơi chứa rule quyền | Provider trả **GrantedAuthority** có nguồn gốc tin cậy | Chain cấu hình **authorizeHttpRequests**, nhưng có thể dùng method security bên cạnh |
| Ví dụ | Username/password + API key có token type riêng; password + OTP provider | **/api/** dùng Basic/stateless; phần web dùng form login/session |
| Lỗi thiết kế hay gặp | Provider yếu hơn nhận credential mà provider trước đã từ chối | Chain tổng quát ưu tiên cao che chain cụ thể hoặc không có catch-all |

**Một AuthenticationManager không tương đương một SecurityFilterChain.** Một chain có thể có manager với nhiều provider; nhiều chain có thể chia sẻ manager hoặc dùng manager riêng. Quan hệ không mặc định một–một.

## 3. Nhiều provider trong một manager hoạt động ra sao?

### 3.1. Hợp đồng ProviderManager

Giao diện chính:

~~~java
public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
            throws AuthenticationException;
}
~~~

Với **ProviderManager**, thứ tự xử lý về mặt khái niệm như sau:

1. Nhận một **Authentication** chưa được xác minh.
2. Duyệt các **AuthenticationProvider** đã cấu hình.
3. Với provider mà **supports(authentication.getClass())** có khả năng xử lý loại token, gọi **authenticate(authentication)**.
4. Nếu provider trả một **Authentication hợp lệ**, trả kết quả thành công. Một provider không xử lý được có thể trả **null** để manager thử tiếp.
5. Nếu provider báo lỗi, manager xử lý theo loại **AuthenticationException** và cơ chế fallback của nó; với một số lỗi, việc duyệt có thể dừng sớm. **Không được giả định mọi lỗi đều dừng ngay hoặc mọi lỗi đều thử provider kế tiếp.**
6. Nếu không provider nào xác thực, manager có thể tham khảo **parent AuthenticationManager** đã cấu hình; cuối cùng xác thực thất bại, có thể với **ProviderNotFoundException** khi không tìm được provider hỗ trợ.

**supports(...) không phải bộ lọc URL.** Một provider hỗ trợ **UsernamePasswordAuthenticationToken** sẽ không tự biết yêu cầu đến từ **/api/** hay **/web/**. Nếu muốn giới hạn theo bối cảnh, cần chọn đúng filter/manager/token và đánh giá trust boundary; không nên dựa vào tên endpoint lấy tùy tiện từ Authentication.details.

Đa số filter đăng nhập tạo một đối tượng Authentication cụ thể:

| Filter/cơ chế | Đầu vào thường tạo | Provider phù hợp |
| --- | --- | --- |
| **HTTP Basic** | **UsernamePasswordAuthenticationToken** | Thường **DaoAuthenticationProvider** hoặc provider tương thích username/password |
| **Form login** | **UsernamePasswordAuthenticationToken** | Cũng thường chính **DaoAuthenticationProvider** |
| **Custom API key filter** | **ApiKeyAuthenticationToken** do ứng dụng định nghĩa | Custom provider hỗ trợ token type này |
| **OAuth2 Resource Server JWT** | Token chuyên biệt do cơ chế bearer/JWT tạo | Thành phần xác minh JWT theo kiến trúc Spring Security |
| **Pre-authenticated identity** | Token pre-auth do filter cụ thể tạo | Provider cho ngữ cảnh pre-auth, chỉ tin identity từ thành phần upstream đã xác minh |

**Quan sát quan trọng:** Bật cả **httpBasic()** và **formLogin()** không nhất thiết cần hai provider, vì hai filter mặc định đều dùng token username/password và thường có thể gọi cùng một **DaoAuthenticationProvider**. Ngược lại, đăng ký thêm **ApiKeyProvider** vào manager **không tự làm cho HTTP request có X-API-Key được xác thực**: phải có filter hoặc endpoint đáng tin tạo **ApiKeyAuthenticationToken** rồi chuyển nó cho manager.

### 3.2. Ví dụ Java 17: một ProviderManager với hai loại bằng chứng

Ví dụ dưới đây là **chương trình chạy độc lập trong một dự án Spring Boot 3.x** có dependency **Spring Security**. Nó không tạo HTTP endpoint; mục đích là nhìn thấy **cùng một manager** xử lý hai loại Authentication khác nhau. Tạo dự án Maven bằng Spring Initializr (Java 17+, dependency **Spring Security**), đặt tệp **src/main/java/com/example/demo/ProviderManagerDemo.java** dưới package tương ứng và dùng class này làm main duy nhất của dự án minh họa.

~~~java
package com.example.demo;

import java.util.Collection;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootApplication
public class ProviderManagerDemo implements CommandLineRunner {

    public static void main(String[] args) {
        SpringApplication.run(ProviderManagerDemo.class, args);
    }

    @Override
    public void run(String... args) {
        var manager = new ProviderManager(List.of(
                new PasswordProvider(),
                new ApiKeyProvider()));

        Authentication person = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "alice", "demo-pass"));

        Authentication job = manager.authenticate(
                ApiKeyToken.request("example-key"));

        System.out.println("password: " + person.getName()
                + " | " + person.getAuthorities().iterator().next()
                        .getAuthority());
        System.out.println("api-key: " + job.getName()
                + " | " + job.getAuthorities().iterator().next()
                        .getAuthority());

        try {
            manager.authenticate(ApiKeyToken.request("wrong"));
        } catch (BadCredentialsException ex) {
            System.out.println("invalid key: rejected");
        }
    }

    static final class PasswordProvider implements AuthenticationProvider {
        @Override
        public Authentication authenticate(Authentication input)
                throws AuthenticationException {
            if (!supports(input.getClass())) {
                return null;
            }
            boolean valid = "alice".equals(input.getName())
                    && "demo-pass".equals(input.getCredentials());
            if (!valid) {
                throw new BadCredentialsException("Invalid credentials");
            }
            return UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
        }

        @Override
        public boolean supports(Class<?> type) {
            return UsernamePasswordAuthenticationToken.class
                    .isAssignableFrom(type);
        }
    }

    static final class ApiKeyProvider implements AuthenticationProvider {
        @Override
        public Authentication authenticate(Authentication input)
                throws AuthenticationException {
            if (!supports(input.getClass())) {
                return null;
            }
            if (!"example-key".equals(input.getCredentials())) {
                throw new BadCredentialsException("Invalid API key");
            }
            return ApiKeyToken.verified("nightly-job");
        }

        @Override
        public boolean supports(Class<?> type) {
            return ApiKeyToken.class.isAssignableFrom(type);
        }
    }

    static final class ApiKeyToken extends AbstractAuthenticationToken {
        private final String principal;
        private String credentials;

        private ApiKeyToken(
                String principal,
                String credentials,
                Collection<? extends GrantedAuthority> authorities,
                boolean verified) {
            super(authorities);
            this.principal = principal;
            this.credentials = credentials;
            super.setAuthenticated(verified);
        }

        static ApiKeyToken request(String apiKey) {
            return new ApiKeyToken(null, apiKey, List.of(), false);
        }

        static ApiKeyToken verified(String subject) {
            return new ApiKeyToken(subject, null,
                    List.of(new SimpleGrantedAuthority("SCOPE_read")),
                    true);
        }

        @Override
        public Object getPrincipal() {
            return principal;
        }

        @Override
        public Object getCredentials() {
            return credentials;
        }

        @Override
        public void eraseCredentials() {
            super.eraseCredentials();
            credentials = null;
        }
    }
}
~~~

Chạy trong thư mục dự án vừa tạo:

~~~bash
./mvnw spring-boot:run
~~~

PowerShell trên Windows dùng **.\mvnw.cmd spring-boot:run**. Bên cạnh các dòng log Spring Boot, ba dòng do chương trình in sẽ là:

~~~text
password: alice | ROLE_USER
api-key: nightly-job | SCOPE_read
invalid key: rejected
~~~

**Phân tích:** Request token đầu tiên thuộc lớp **UsernamePasswordAuthenticationToken**, nên **PasswordProvider** hỗ trợ. Request token thứ hai thuộc lớp **ApiKeyToken**, nên **ApiKeyProvider** hỗ trợ. Một **ProviderManager** đã kiểm tra hai dạng bằng chứng; không cần tạo hai SecurityFilterChain để chứng minh điều này.

**Ranh giới của ví dụ:** mật khẩu và API key được hard-code **chỉ để học luồng dispatch**. Tuyệt đối không triển khai kiểu so sánh này vào production. Với mật khẩu thật, dùng **UserDetailsService** và **PasswordEncoder.matches** với hash đã lưu; với API key, dùng kho khóa server kiểm soát, quản lý scope, hết hạn, thu hồi, tránh log credential và so sánh an toàn theo thiết kế. Class **ApiKeyToken.verified(...)** là factory nội bộ chỉ được provider gọi sau khi xác minh; không cho client tự tạo token đã xác thực. Với app thật, filter phải tạo request token chưa xác thực từ header, không nhận role từ client.

**Lưu ý thêm:** phần minh họa dùng manager được tạo trực tiếp trong **CommandLineRunner**. Nó là một bài thử API **ProviderManager**; chưa tích hợp manager đó vào filter chain HTTP. Khi tích hợp vào web, cần cấu hình **AuthenticationManager** tương ứng cho chain và thêm filter nhận API key nếu muốn xác thực header API key.

## 4. Nhiều SecurityFilterChain hoạt động ra sao?

### 4.1. FilterChainProxy chọn chain theo request

Trong môi trường Servlet, Spring Security dùng **FilterChainProxy** để quản lý các **SecurityFilterChain**. Mỗi chain có một **RequestMatcher**; **securityMatcher(...)** giới hạn vùng request mà chain quản lý. **@Order** quyết định thứ tự các chain được xét: chain có thứ tự ưu tiên cao được xét trước. Khi một chain khớp, **chỉ chain đó chạy**, bất kể các chain khác cũng có thể khớp.

Ví dụ:

~~~text
@Order(1): SecurityFilterChain A, securityMatcher("/api/admin/**")
@Order(2): SecurityFilterChain B, securityMatcher("/api/**")
Không @Order: SecurityFilterChain C, mặc định match mọi request

GET /api/admin/users -> A
GET /api/items       -> B
GET /login           -> C
GET /favicon.ico     -> C
~~~

Đảo thứ tự A và B có thể khiến **/api/admin/users** bị B bắt trước. Chính sách chặt hơn đặt ở A sẽ không được áp dụng trong request ấy. **@Order chỉ sắp thứ tự chain**; nó không chọn AuthenticationProvider.

Nếu cả ba chain có **securityMatcher** hạn chế và không chain nào khớp **/unlisted**, Spring Security không áp dụng filter chain bảo vệ cho request đó. Vì vậy, ứng dụng nhiều chain thường có **một chain cuối không đặt securityMatcher**, với chính sách rõ ràng cho phần còn lại.

### 4.2. securityMatcher khác requestMatchers

Hai API trông giống nhau nhưng phục vụ hai mục tiêu:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

- **securityMatcher("/api/**")**: chain này chỉ được chọn cho request trong **/api/**. Đây là giới hạn của cả chain.
- **requestMatchers("/api/admin/**").hasRole("ADMIN")**: quy tắc phân quyền **bên trong chain đã chọn**; không tạo chain mới.
- **anyRequest().authenticated()**: mọi request còn lại **trong chain hiện tại**, không phải “mọi request của ứng dụng” nếu chain bị giới hạn bởi securityMatcher.

Một lỗi nguy hiểm là cấu hình **requestMatchers("/admin/**")** trong chain mà **securityMatcher("/api/**")** không bao giờ khớp **/admin/**. Rule đó không được chạy cho **/admin/**. Muốn bảo vệ URL khác, cần matcher của chain bao phủ URL ấy hoặc một chain khác phù hợp.

### 4.3. Ví dụ Spring Boot 3.x: hai chain cho API và web

Đây là **dự án minh họa riêng** với ví dụ **ProviderManagerDemo** ở mục 3. Tạo dự án Spring Boot 3.x/Java 17+ với **Spring Web** và **Spring Security**, giữ class **DemoApplication** do Spring Initializr sinh ra và đặt hai class dưới package **com.example.demo**. Ví dụ sử dụng một tài khoản từ **UserDetailsService** để cả HTTP Basic và form login có thể đăng nhập, nhưng hai **SecurityFilterChain** áp dụng **cơ chế request và session khác nhau**.

Tệp **src/main/java/com/example/demo/MultiChainSecurityConfig.java**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .requestCache(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

**Hai chain có trách nhiệm khác nhau:**

- **apiChain** có **@Order(1)**, chỉ khớp **/api/**, dùng **HTTP Basic**, không dùng form login, chọn **SessionCreationPolicy.STATELESS** để không dùng session làm nơi lưu Authentication cho API. Trong ví dụ chỉ thử request GET.
- **webChain** không có **securityMatcher** nên là chain mặc định xét sau, dùng **formLogin**, session cho trải nghiệm trình duyệt và không bật BasicAuthenticationFilter. Nó bao phủ cả **/login** để trang đăng nhập mặc định của Spring Security hoạt động.
- Cả hai cùng tham chiếu logic xác thực username/password qua UserDetailsService và PasswordEncoder. **Điều này không chứng minh hai chain đang dùng cùng một object AuthenticationManager.** Spring có thể cấu hình manager riêng ở từng HttpSecurity hoặc dùng chung các thành phần xác thực. Nếu cần cùng một **instance**, hãy inject và gắn **http.authenticationManager(sharedManager)** một cách tường minh.
- Ví dụ **không tắt CSRF**. CSRF vẫn cần được đánh giá khi client là trình duyệt, kể cả HTTP Basic nếu trình duyệt tự gửi credential. Phần demo chỉ gọi GET; với POST/PUT/DELETE, phải chọn chính sách CSRF đúng mô hình truy cập, không tắt chỉ để vượt lỗi 403.

Tệp **src/main/java/com/example/demo/IdentityController.java**:

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api " + authentication.getName();
    }

    @GetMapping("/web/me")
    public String webMe(Authentication authentication) {
        return "web " + authentication.getName();
    }
}
~~~

Trong **src/main/resources/application.properties**:

~~~properties
server.port=8080
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Chạy trên Linux/macOS:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

Trên Windows PowerShell, đặt **$env:DEMO_USER_PASSWORD = "demo-pass"**, rồi chạy **.\mvnw.cmd spring-boot:run**. Mật khẩu minh họa chỉ dùng trên localhost; không lưu secret thực vào repository. Ở môi trường thật phải sử dụng HTTPS và cấu hình cookie an toàn.

Gọi thử:

~~~bash
curl -i http://localhost:8080/api/me
curl -i -u alice:demo-pass http://localhost:8080/api/me
curl -i http://localhost:8080/web/me
curl -i http://localhost:8080/login
curl -i http://localhost:8080/public
~~~

Kết quả cần quan sát:

| Request | Chain được chọn | Kết quả mong đợi |
| --- | --- | --- |
| **GET /api/me**, chưa có credential | **apiChain** | **401 Unauthorized**, có thể kèm **WWW-Authenticate: Basic** |
| **GET /api/me**, Basic đúng | **apiChain** | **200 OK**, body **api alice** |
| **GET /web/me**, chưa có session | **webChain** | **302** chuyển hướng tới trang **/login** |
| **GET /login** | **webChain** | **200 OK**, form đăng nhập HTML do Spring Security cung cấp |
| **GET /public** | **webChain** | **200 OK**, body **public** |

Nếu gửi **Authorization: Basic ...** tới **/web/me** bằng một client mới không có session, đừng mong filter Basic tự chạy: **webChain** đã tắt HTTP Basic. Request ấy thường vẫn chuyển hướng tới trang đăng nhập HTML. Mỗi chain có **tập filter riêng**, nên HTTP header giống nhau có thể dẫn tới hành vi khác nhau ở các vùng URL.

**Lưu ý endpoint do filter tạo:** Nếu giới hạn **webChain** bằng **securityMatcher("/web/**")**, trang mặc định **GET /login** và xử lý **POST /login** không nằm trong matcher này. Chúng có thể bị chain khác xử lý hoặc trả 404. Khi dùng chain phạm vi hẹp, hãy chuyển **loginPage**, **loginProcessingUrl**, **logoutUrl** và các đường dẫn liên quan vào phạm vi chain hoặc giữ chain fallback bao phủ chúng.

## 5. Có thể kết hợp cả hai trong một ứng dụng không?

**Có, và đây là điểm dễ nhầm nhất.** Ví dụ một hệ thống phục vụ:

- **/api/**: client máy–máy sử dụng API key hoặc bearer token.
- **/web/**: người dùng đăng nhập form username/password.
- **/internal/**: nhân viên qua kết nối có xác thực khác.

Bạn có thể dùng **nhiều SecurityFilterChain** để tách vùng request và policy; mỗi chain có **AuthenticationManager** riêng hoặc chia sẻ một manager với nhiều provider. Một sơ đồ hợp lệ:

~~~text
FilterChainProxy
  |
  +-- chain #1: /api/** (stateless, nhận API key)
  |       |
  |       +--> ApiKeyFilter --> AuthenticationManager A
  |                              +--> ApiKeyProvider
  |                              +--> JWT Provider (nếu có)
  |
  +-- chain #2: /web/** (session + form login)
  |       |
  |       +--> UsernamePasswordAuthenticationFilter
  |                                  |
  |                                  v
  |                           AuthenticationManager B
  |                                  +--> DaoAuthenticationProvider
  |
  +-- chain #3: fallback (deny/explicit policy)
~~~

Một cấu trúc khác cũng hợp lệ: hai chain khác nhau **dùng chung** một manager được cấu hình với **DaoAuthenticationProvider** và **ApiKeyProvider**. Tuy nhiên, cần có filter tạo đúng **Authentication token type** cho từng bằng chứng.

### 5.1. Cấu hình manager chia sẻ, minh họa khung kết nối

Đoạn bên dưới **chỉ minh họa wiring**, chưa thể biên dịch độc lập vì chưa khai báo các bean provider và filter API key. Nó cho thấy **những điểm cần kết nối**; không thể thay cho cấu hình lọc HTTP thực tế:

~~~java
// Đoạn minh họa trong @Configuration; cần định nghĩa
// passwordProvider, apiKeyProvider và apiKeyFilter trong dự án thật.
@Bean
AuthenticationManager sharedManager(
        AuthenticationProvider passwordProvider,
        ApiKeyAuthenticationProvider apiKeyProvider) {
    return new ProviderManager(List.of(
            passwordProvider,
            apiKeyProvider));
}

@Bean
@Order(1)
SecurityFilterChain apiChain(
        HttpSecurity http,
        AuthenticationManager sharedManager) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authenticationManager(sharedManager)
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            // Thêm ApiKeyFilter ở đúng vị trí filter phù hợp
            // để chuyển header API key thành ApiKeyAuthenticationToken.
            .build();
}

@Bean
SecurityFilterChain webChain(
        HttpSecurity http,
        AuthenticationManager sharedManager) throws Exception {
    return http
            .authenticationManager(sharedManager)
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

Khi **ApiKeyFilter** chưa được gắn, request chỉ mang **X-API-Key** không tự đi vào manager, dù ApiKeyProvider có tồn tại. Khi manager chia sẻ, provider phải kiểm tra đúng loại token và nguồn dữ liệu tin cậy; không để một provider được gọi sai ngữ cảnh và làm rò quyền của vùng khác.

Nếu lựa chọn nhiều manager, có thể cấu hình **AuthenticationManager** cụ thể cho từng chain. Có trường hợp các manager con dùng một **parent AuthenticationManager** chung. Đó là lựa chọn **kiến trúc và trust boundary**; nó không phải hành vi ngầm bảo đảm của việc tạo hai bean SecurityFilterChain.

### 5.2. Khi nào chọn cách nào?

| Yêu cầu | Giải pháp thường phù hợp | Vì sao |
| --- | --- | --- |
| Cùng một endpoint cho phép nhiều kiểu bằng chứng | **Một chain + các filter thích hợp + manager hỗ trợ nhiều provider**, nếu chính sách request giống nhau | Quyết định theo credential sau khi request đi vào chain |
| Cùng username/password nhưng URL API trả 401, giao diện web redirect tới login | **Nhiều chain**, có thể dùng chung UserDetailsService/provider | Khác biệt nằm ở entry point, session, filter và response, không phải cách kiểm tra password |
| API key cho /api và form session cho /web, CSRF/chính sách khác nhau | **Nhiều chain**, mỗi chain cấu hình filter/manager thích hợp | Khác biệt ở cả vùng request và cơ chế xác thực |
| Hỗ trợ hai nguồn mật khẩu nội bộ khác nhau | **ProviderManager với provider chuyên biệt** hoặc một service xác thực hợp nhất | Cần xác định rõ ngữ cảnh người dùng và thứ tự fallback; tránh nguồn yếu được thử sau nguồn mạnh |
| Phân quyền /admin nghiêm ngặt hơn /user, cùng cơ chế login | Có thể chỉ cần **requestMatchers** trong một chain; nhiều chain nếu khác filter/policy rõ rệt | Tránh tạo chain khi chỉ khác một rule authorization |
| Cần chạy cả form login và Basic trong cùng vùng URL | Một chain có **formLogin + httpBasic**, thường dùng chung provider username/password | Hai filter xác thực khác nhau có thể dùng cùng một token type |
| Một path vừa có JWT vừa có API key | Một chain với filter/token dành cho từng cơ chế và manager/provider tương ứng, hoặc matcher tách chain nếu thực sự phân vùng được | **Nhiều chain không tự cộng dồn**, request chỉ vào chain đầu tiên khớp |

### 5.3. Vì sao không nên dùng nhiều chain chỉ để “thử provider tiếp theo”?

Giả sử **/api/orders** khớp cả hai SecurityFilterChain A và B. Nếu A dùng Basic nhưng không có credential hợp lệ, **FilterChainProxy không chuyển request sang B** để thử login token. Nó đã chọn A ngay khi matcher của A khớp; lỗi xác thực trong A được xử lý theo chain A. Cơ chế thử nhiều provider thuộc **ProviderManager ở bên trong chain**, không thuộc FilterChainProxy.

Ngược lại, nếu manager hỗ trợ cả **PasswordProvider** và **ApiKeyProvider** nhưng chain chỉ có **BasicAuthenticationFilter**, request chứa **X-API-Key** không được biến thành ApiKeyToken. Chỉ thêm provider không thay thế việc đăng ký filter.

Đây là lý do hai tầng phải được thiết kế và kiểm thử riêng.

## 6. Thứ tự và fallback: hai nguồn lỗi dễ bị bỏ sót

### 6.1. Chain bị che do @Order

**Ví dụ nguy hiểm:**

~~~java
@Bean
@Order(1)
SecurityFilterChain all(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityFilterChain admin(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/admin/**")
            .authorizeHttpRequests(a -> a.anyRequest().hasRole("ADMIN"))
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

Trong ví dụ **minh họa lỗi**, chain **all** không đặt securityMatcher nên match mọi request ngay ở mức ưu tiên **1**. Request **/api/admin/users** không bao giờ tới chain **admin**. Cách sửa là đưa chain đặc thù **/api/admin/** lên trước và chain bao phủ mọi request xuống cuối, hoặc thiết kế authorization rule trong một chain đúng thứ tự.

**Đừng đọc hai bean như hai lớp bảo vệ cộng dồn.** Chúng là hai lựa chọn loại trừ ở tầng FilterChainProxy.

### 6.2. Provider sau vô tình chấp nhận credential provider trước từ chối

Nếu một manager đăng ký hai provider cùng **supports(UsernamePasswordAuthenticationToken.class)**, hãy xem kỹ:

1. Hai provider có cùng nhận username/password không? Nếu có, khác biệt nguồn xác thực được xác định thế nào?
2. Khi một provider ném **BadCredentialsException**, manager có thể tiếp tục thử provider khác tùy loại exception và cấu hình. Điều này có đúng chính sách hay mở đường fallback yếu?
3. Provider sau có xác minh bằng chứng độc lập, có nguồn tin cậy và account state không?
4. **parent AuthenticationManager** nếu có có làm phát sinh đường chấp nhận ngoài dự kiến không?
5. Nếu user cùng username hiện diện ở hai nguồn, **authorities** trả về có bị nhập nhằng hoặc nâng quyền không?

**Giải pháp:** chọn các loại token khác nhau cho các dạng bằng chứng khác nhau; khi cần tách user domain, định tuyến rõ ràng và áp dụng một chính sách chấp nhận nhất quán. Test mọi nhánh provider-fallback, đặc biệt khi source lỗi hoặc credential sai. Không nên sử dụng **return null** để bỏ qua bằng chứng đã biết là sai chỉ với mục tiêu cho “nhà cung cấp khác thử”.

### 6.3. Nếu không chain nào khớp, Spring Security có chặn không?

**Không tự động.** Theo tài liệu, request không khớp SecurityFilterChain nào sẽ không được bảo vệ bởi Spring Security. Nếu toàn bộ chain đều có matcher hẹp, cần kiểm tra các endpoint như **/actuator/**, **/error**, **/login**, **/favicon.ico**, route mới, các method khác và đường dẫn nội bộ.

Một **fallback SecurityFilterChain** với **anyRequest().denyAll()** thường là lựa chọn bảo thủ cho API chỉ định nghĩa rõ endpoint; còn ứng dụng hỗn hợp có thể dùng fallback với những route công khai được liệt kê và **anyRequest().authenticated()**. Tránh dùng một fallback **permitAll()** rộng mà không hiểu hệ quả.

## 7. Session, CSRF, entry point và scope của từng chain

Khi dùng nhiều chain, mỗi chain có thể thiết lập khác nhau:

| Cấu phần | API stateless mẫu | Web dùng session mẫu |
| --- | --- | --- |
| Cách nhận credential | HTTP Basic, Bearer/JWT hoặc custom filter | Form login |
| SecurityContext | Không dùng session để lấy Authentication nếu thực sự stateless | Tải/lưu SecurityContext qua session theo cấu hình |
| Phản hồi chưa xác thực | Thường **401** (JSON/WWW-Authenticate) | Thường **302** đến login page |
| CSRF | Đánh giá theo cơ chế credential; với bearer trong header do JS tự gắn và không có cookie auto-attach có thể được miễn theo thiết kế | Thường cần CSRF token vì trình duyệt gửi cookie tự động |
| Logout | Với bearer token: thường thu hồi token/credential theo mô hình; không mặc nhiên là session logout | Session invalidation, cookie và CSRF cần xử lý |
| Cache request/redirect | Thường không dùng saved request | Có thể lưu saved request để quay lại trang trước |
| Authorization | Scope/role của API | Role/quyền của người dùng web |

Không nên sao chép cấu hình **csrf(AbstractHttpConfigurer::disable)** từ một API bearer-token không dùng cookie sang chain form login. Và **SessionCreationPolicy.STATELESS** không tự biến endpoint thành API bảo mật; nó chỉ định chính sách session, còn xác thực và phân quyền vẫn phải cấu hình.

Điểm TLS cũng độc lập với lựa chọn chain/provider: dù đăng nhập qua Basic, form hay API key, credential nhạy cảm vẫn cần **HTTPS** và kiểm tra chứng chỉ. Nếu API qua reverse proxy, hãy kiểm tra trusted forwarding headers và điểm kết thúc TLS.

## 8. Kiểm thử phân biệt hai tầng

### 8.1. Lập ma trận request → chain

Dựa trên ví dụ **MultiChainSecurityConfig** ở mục 4:

| Test | Request | Chain kỳ vọng | Kết quả |
| --- | --- | --- | --- |
| API không có Basic | GET /api/me | apiChain | 401 |
| API có Basic đúng | GET /api/me + Basic | apiChain | 200, body **api alice** |
| Web chưa đăng nhập | GET /web/me | webChain | Redirect tới login |
| Trang login | GET /login | webChain | 200 HTML |
| Public | GET /public | webChain | 200 |
| Web gửi Basic nhưng không có session | GET /web/me + Basic | webChain | Vẫn chưa form-login, thường redirect |
| Admin bị che bởi catch-all ở thứ tự cao hơn | GET /api/admin/x trong cấu hình sai của mục 6 | chain tổng quát | Rule ADMIN ở chain sau không chạy |

Phải xác minh chain thực sự được chọn, không chỉ status. Hai chain có thể tình cờ cùng trả 401; khi đó chỉ kiểm tra status sẽ bỏ sót lỗi matching.

### 8.2. Kiểm thử bằng MockMvc

Với dự án ở mục 4, thêm dependency test **spring-boot-starter-test** (và **spring-security-test** nếu muốn dùng các tiện ích mock SecurityContext, CSRF). Tạo **src/test/java/com/example/demo/MultiChainSecurityTest.java**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.user.password=demo-pass")
@AutoConfigureMockMvc
class MultiChainSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiNeedsCredentials() throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void apiAcceptsCorrectBasicCredentials() throws Exception {
        String encoded = Base64.getEncoder().encodeToString(
                "alice:demo-pass".getBytes(StandardCharsets.UTF_8));

        mvc.perform(get("/api/me")
                .header("Authorization", "Basic " + encoded))
                .andExpect(status().isOk())
                .andExpect(content().string("api alice"));
    }

    @Test
    void webRedirectsWithoutFormSession() throws Exception {
        mvc.perform(get("/web/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void webDoesNotTreatBasicHeaderAsFormLogin() throws Exception {
        String encoded = Base64.getEncoder().encodeToString(
                "alice:demo-pass".getBytes(StandardCharsets.UTF_8));

        mvc.perform(get("/web/me")
                .header("Authorization", "Basic " + encoded))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicRouteIsAccessible() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Ở PowerShell: **.\mvnw.cmd test**. Những test này xác minh hành vi quan sát được của hai chain. Để kiểm thử **ProviderManager**, cần thêm test cung cấp hai loại Authentication token như ví dụ mục 3, kiểm tra **supports(...)**, credential đúng/sai, source unavailable và authority chính xác. Nếu có custom filter API key, phải test rằng header được chuyển sang **ApiKeyToken** và provider được gọi.

### 8.3. Quan sát lúc chạy

Trong môi trường phát triển, có thể tạm bật log Spring Security để xem request được bảo vệ bởi chain/filter nào:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Log TRACE có thể tạo rất nhiều sự kiện hoặc metadata nhạy cảm; chỉ bật có giới hạn trên máy phát triển, không sao chép log chứa Authorization/credential ra nơi công khai. Có thể đặt điểm dừng tại **FilterChainProxy** để quan sát chain được chọn, **BasicAuthenticationFilter** hoặc filter tùy chỉnh để quan sát Authentication được tạo, và **ProviderManager** để xem provider nào được gọi.

**Không suy từ tên bean ra số lượng manager thực tế.** Muốn biết chia sẻ hay tách biệt manager, kiểm tra cấu hình bean, cấu trúc filter chain đã build và hành vi trong môi trường chạy.

## 9. Các câu hỏi tự kiểm tra

**Câu 1:** Có hai AuthenticationProvider (password và API key) trong một manager. Request gửi **X-API-Key** có tự đăng nhập được không?

**Không.** ProviderManager chỉ nhận **Authentication** do filter/endpoint gửi tới. Cần filter chuyển header thành token đúng loại rồi gọi manager. Chỉ đăng ký provider không thêm filter nhận header.

**Câu 2:** Có hai chain đều khớp **/api/orders**, chain đầu dùng Basic và xác thực thất bại. Spring có tự thử chain sau dùng JWT không?

**Không.** **FilterChainProxy** chọn chain đầu tiên khớp, không fallback sang chain khác vì lỗi xác thực. Nếu cần hỗ trợ cả Basic và JWT trên cùng endpoint, thiết kế trong cùng chain hoặc tách matcher thật sự khác nhau.

**Câu 3:** Basic và form login cùng dùng username/password thì cần hai provider không?

**Không nhất thiết.** Hai filter có thể cùng tạo **UsernamePasswordAuthenticationToken**, sau đó một DaoAuthenticationProvider có thể xử lý bằng chứng của cả hai. Chain riêng vẫn hữu ích nếu HTTP response, session và chính sách bảo vệ khác nhau.

**Câu 4:** **securityMatcher("/api/**")** và **requestMatchers("/api/admin/**").hasRole("ADMIN")** có giống nhau không?

**Không.** Cái đầu chọn phạm vi chain; cái sau đặt luật phân quyền trong phạm vi chain đã chọn.

**Câu 5:** Nếu không có chain fallback và request khớp không chain nào, sẽ thế nào?

Request ấy không được Spring Security bảo vệ, dù controller hoặc thành phần khác có thể có biện pháp riêng. Vì vậy, cần kiểm tra phạm vi bao phủ của mọi chain.

**Câu 6:** Có thể chia sẻ AuthenticationManager giữa nhiều chain không?

**Có.** Khi chủ ý chia sẻ, cấu hình manager và inject vào từng **HttpSecurity**. Nhưng hai chain độc lập không mặc nhiên chứng minh đang dùng chung một instance; hãy kiểm tra wiring thực tế.

**Câu 7:** Manager có hai provider cùng hỗ trợ username/password, provider đầu ném BadCredentialsException. Có thể chắc chắn provider thứ hai không được gọi không?

**Không.** Việc xử lý exception và fallback tùy **ProviderManager**, loại exception và cấu hình. Cần thiết kế các provider tương thích với cùng chính sách và có test ngăn đường xác thực yếu hơn.

## 10. Checklist thiết kế

- [ ] Viết rõ **request nào → SecurityFilterChain nào**, kể cả login, logout, error, actuator và route mới.
- [ ] Đặt chain cụ thể trước chain tổng quát, có **@Order** và **securityMatcher** chính xác.
- [ ] Có chain fallback rõ ràng; không để đường dẫn không mong muốn nằm ngoài Spring Security.
- [ ] Với từng chain, liệt kê filter thực sự nhận Basic, form, bearer, API key hoặc credential khác.
- [ ] Với từng filter, xác định **Authentication token type** mà nó tạo và **AuthenticationManager** mà nó gọi.
- [ ] Với từng manager, liệt kê **AuthenticationProvider**; kiểm tra **supports**, thứ tự, parent manager và nhánh lỗi.
- [ ] Không chấp nhận token được đánh dấu authenticated, role hoặc principal do client tự khai mà chưa xác minh.
- [ ] Quyền được lấy từ nguồn đáng tin; authorization chạy đúng phạm vi chain và method security nếu có.
- [ ] Thiết kế cụ thể session, CSRF, entry point, error response, login/logout path, TLS và rate limiting theo từng vùng.
- [ ] Test 401/403/302/200 cũng như chain/filter/provider thực sự được chọn; test các giao nhau giữa matcher.
- [ ] Không tự động tắt CSRF hoặc mở permitAll rộng để giải quyết lỗi matching.

## 11. Tài liệu chính thức

- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): ProviderManager, AuthenticationProvider, parent manager và SecurityContext.
- [Spring Security 6.5 — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): multiple SecurityFilterChain, **@Order**, **securityMatcher** so với **requestMatchers**, và các endpoint login do filter cung cấp.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, chọn chain đầu tiên khớp và thứ tự filter.
- [AuthenticationProvider Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/authentication/AuthenticationProvider.html): hợp đồng **supports** và **authenticate**.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): kiểm tra bằng chứng và bảo vệ tài khoản khi dùng nhiều cơ chế xác thực.
