# Thiết kế Authentication token riêng và trạng thái chưa xác thực trong Spring Security Servlet

**Bối cảnh:** Java 17+, Spring Security 6.x và Spring Boot 3.x trên Jakarta Servlet. Bài thuộc nhóm **Xác thực tùy chỉnh**. Trọng tâm là phân biệt token *yêu cầu xác thực* với token *đã được xác thực*, cách tạo một <code>Authentication</code> riêng, dùng <code>AuthenticationProvider</code> để kiểm tra bằng chứng và đặt kết quả đáng tin cậy vào <code>SecurityContext</code> một cách có kiểm soát.

Ở đây từ **token** nghĩa là đối tượng Java triển khai interface <code>org.springframework.security.core.Authentication</code>. Nó **không mặc nhiên là JWT, access token OAuth2, API key hay chuỗi do client gửi**. Một custom Authentication token có thể chỉ tồn tại trong JVM, dùng để chuyên chở credential từ filter tới AuthenticationManager và kết quả từ AuthenticationProvider trở lại Spring Security.

## 1. Vì sao cần custom Authentication token?

Spring Security đã có nhiều loại authentication phổ biến như username/password, Basic, OAuth2/OIDC, bearer token, X.509 và pre-authentication. Chỉ nên tạo token riêng khi bằng chứng đăng nhập hoặc trạng thái nghiệp vụ không thể biểu diễn phù hợp bằng cơ chế sẵn có, ví dụ:
- Xác thực bằng một loại credential chuyên biệt do hệ thống nội bộ phát hành.
- Kết hợp một tài khoản với challenge được máy chủ xác minh.
- Kết nối một AuthenticationProvider kiểm tra credential theo giao thức nghiệp vụ riêng.
- Biểu diễn hai giai đoạn trước/sau xác thực mà vẫn tích hợp được <code>AuthenticationManager</code>, <code>SecurityContext</code> và authorization của Spring Security.

Không cần tạo token riêng chỉ vì controller muốn biết vai trò người dùng hoặc cần thêm một thuộc tính. Có thể dùng principal riêng trong cơ chế authentication hiện có, một <code>AuthenticationConverter</code> hoặc một <code>GrantedAuthoritiesMapper</code>, tùy mục đích. Tránh phát minh cơ chế đăng nhập thay cho tiêu chuẩn đã được hỗ trợ nếu dùng OIDC/OAuth2, SAML hay passkey có thư viện phù hợp.

### Năm thành phần trên tuyến xác thực

| Thành phần | Vai trò | Có phải nguồn xác nhận quyền? |
| --- | --- | --- |
| <code>Authentication</code> | Đối tượng mô tả yêu cầu/kết quả xác thực | Chưa chắc: phụ thuộc <code>isAuthenticated()</code> và nguồn tạo |
| <code>AuthenticationManager</code> | Điều phối việc xác thực, thường là <code>ProviderManager</code> | Chuyển việc kiểm tra đến provider |
| <code>AuthenticationProvider</code> | Kiểm tra credential và trả Authentication đã được xác thực | **Có**, sau khi tự xác minh bằng chứng |
| <code>SecurityContext</code> | Giữ Authentication của request/phiên | Chứa trạng thái, không tự xác minh credential |
| <code>SecurityContextHolder</code> | Cung cấp SecurityContext cho mã xử lý hiện tại | Không phải nơi để tự đánh dấu user là tin cậy |

Thứ tự điển hình:

~~~text
HTTP request
    |
SecurityFilterChain / custom authentication filter
    |
custom Authentication (isAuthenticated = false)
    |
AuthenticationManager -> AuthenticationProvider.supports(...)
    |
Provider kiểm tra credential từ nguồn đáng tin
    |-----------------------------+
    | Sai / thiếu                  | Đúng
    v                             v
AuthenticationException      Authentication đã xác thực
(401, không lưu context)     isAuthenticated = true
                                  |
                             SecurityContext
                                  |
                             AuthorizationFilter
                                  |
                        200 / 403 tùy GrantedAuthority
~~~

Không bao giờ cấp quyền cho request chỉ bởi client gửi một flag <code>authenticated=true</code>, <code>role=ADMIN</code> hay một <code>Authentication</code> do controller tự dựng.

## 2. Hợp đồng của interface Authentication

<code>Authentication</code> mở rộng <code>Principal</code> và có các phương thức chủ chốt:

- <code>getPrincipal()</code>: danh tính hoặc định danh được trình bày; trước xác thực có thể chỉ là username chưa được xác minh, sau xác thực là principal đã được xác nhận.
- <code>getCredentials()</code>: bằng chứng để xác thực, ví dụ mật khẩu, mã hoặc credential khác. Nên xóa/không giữ credential thô sau khi hoàn tất.
- <code>getAuthorities()</code>: danh sách <code>GrantedAuthority</code>. Authority có ý nghĩa cấp quyền **chỉ khi đến từ nguồn đã xác minh**.
- <code>getDetails()</code>: dữ liệu bổ sung của request, ví dụ remote address hoặc thông tin thiết bị, không thay cho xác minh credential.
- <code>isAuthenticated()</code> và <code>setAuthenticated(...)</code>: thể hiện/cập nhật trạng thái của đối tượng theo contract của loại token.
- <code>getName()</code>: tên định danh dùng bởi API <code>Principal</code>.

Thông thường <code>AbstractAuthenticationToken</code> giúp triển khai sẵn nhiều phần của contract, như danh sách authority, details, <code>isAuthenticated()</code>, <code>getName()</code> và xóa credential theo <code>CredentialsContainer</code>. Custom token phải hoàn thiện <code>getPrincipal()</code>, <code>getCredentials()</code> và quyết định cách tạo trạng thái tin cậy.

### Hai trạng thái của cùng một loại token

**Request token chưa xác thực:**

~~~text
principal = "learner"           (chỉ là lời khai từ request)
credentials = "..."             (mã chưa được kiểm tra)
authorities = []                (không tin quyền client)
authenticated = false
~~~

**Result token đã xác thực:**

~~~text
principal = "learner"           (đã xác nhận qua provider)
credentials = null              (không giữ mã raw)
authorities = [ROLE_LEARNER]    (server tự cấp)
authenticated = true
~~~

Đừng hiểu <code>authenticated=false</code> là “anonymous user” theo mọi trường hợp: request token có thể mang username/credential được đề nghị nhưng chưa được xác minh. Cũng đừng dùng mỗi boolean để chứng minh người dùng đã đăng nhập hợp lệ: một số token đặc biệt như <code>AnonymousAuthenticationToken</code> có <code>isAuthenticated()</code> là true theo contract, nhưng authorization như <code>authenticated()</code> dùng cách diễn giải thích hợp để phân biệt anonymous. Trạng thái tin cậy phải được xác định bởi **pipeline xác thực và loại Authentication**.

## 3. Nguyên tắc thiết kế token an toàn

Một custom token tốt có:
1. Factory/constructor **công khai chỉ cho trạng thái chưa xác thực**. Client input được đặt trong request token không có authority đặc quyền.
2. Constructor/factory tạo token đã xác thực chỉ được gọi từ vùng code tin cậy sau khi provider kiểm tra credential. Điều này là quy tắc thiết kế, không phải cơ chế sandbox thay thế cho review code.
3. Không cho code bất kỳ gọi <code>setAuthenticated(true)</code> trên request token để bỏ qua provider.
4. Tách <code>principal</code>, <code>credentials</code>, <code>authorities</code> về ý nghĩa; credentials có thể được xóa sau authentication.
5. Không đưa credential vào <code>toString()</code>, log, exception hoặc details. <code>String</code> đã đọc từ HTTP header có giới hạn về khả năng xóa khỏi bộ nhớ; cần tránh lưu thêm bản sao.
6. Chỉ giữ dữ liệu quyền được cấp từ server. Nếu client gửi <code>X-Role: ADMIN</code>, filter/provider phải bỏ qua nó.
7. Không để một Authentication có <code>isAuthenticated=true</code> chỉ vì đã parse được JSON/header/token. Bước parse chưa phải bước xác minh.

Mã chưa xác thực phải dẫn đến <code>AuthenticationManager.authenticate(...)</code>; thất bại phải tạo lỗi <code>AuthenticationException</code> có ý nghĩa. Không tự cấp authority mặc định cao khi database chậm, header thiếu hoặc credential không hợp lệ.

## 4. Ví dụ độc lập: demo code trong HTTP header, per-request stateless

Ví dụ dùng hai header <code>X-Demo-User</code> và <code>X-Demo-Code</code> để minh họa cơ chế custom token. Provider kiểm tra user demo <code>learner</code> và một mã server-side đọc từ biến môi trường. Khi hợp lệ, chỉ cấp <code>ROLE_LEARNER</code>.

**Đây là cơ chế đào tạo, tuyệt đối không phải thiết kế đăng nhập production.** Mã dùng chung, credential trong header và thiếu chống replay/rate limit/rotation/identification riêng cho từng user khiến nó không phù hợp cho hệ thống thật. Trong sản phẩm, ưu tiên OAuth2/OIDC, bearer token được xác minh đầy đủ, mTLS hoặc cơ chế tiêu chuẩn khác. Ví dụ được giới hạn GET, không tạo session và **không tắt CSRF** (Spring Security vẫn có chính sách mặc định cho những method thay đổi trạng thái).

Cấu trúc dự án:

~~~text
custom-token-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/customauth/
    │   │   ├── CustomAuthApplication.java
    │   │   ├── DemoCodeAuthenticationToken.java
    │   │   ├── DemoCodeAuthenticationProvider.java
    │   │   ├── DemoCodeFilter.java
    │   │   └── SecurityConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/customauth/
            └── CustomAuthenticationTest.java
~~~

### 4.1. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>custom-token-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Controller dùng để kiểm thử kết quả xác thực

Tạo <code>src/main/java/com/example/customauth/CustomAuthApplication.java</code>:

~~~java
package com.example.customauth;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CustomAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomAuthApplication.class, args);
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/private")
    public String privateEndpoint(Principal principal) {
        return "private:" + principal.getName();
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin";
    }
}
~~~

<code>/private</code> yêu cầu người đã xác thực có quyền LEARNER, <code>/admin</code> yêu cầu ADMIN. Provider mẫu **chỉ cấp ROLE_LEARNER**, vì vậy ngay cả credential đúng cũng không đủ truy cập admin; đây là khác biệt giữa authentication thành công và authorization được phép.

### 4.3. Custom Authentication token: factory chưa xác thực và factory tin cậy

Tạo <code>src/main/java/com/example/customauth/DemoCodeAuthenticationToken.java</code>:

~~~java
package com.example.customauth;

import java.util.Collection;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.authentication.AbstractAuthenticationToken;

public final class DemoCodeAuthenticationToken
        extends AbstractAuthenticationToken {

    private final String principal;
    private String credentials;

    private DemoCodeAuthenticationToken(
            String principal,
            String credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean authenticated) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        if (authenticated) {
            // Chỉ constructor nội bộ dành cho kết quả provider.
            super.setAuthenticated(true);
        }
    }

    // Được phép tạo từ dữ liệu request: CHƯA đáng tin.
    public static DemoCodeAuthenticationToken unauthenticated(
            String username, String code) {
        return new DemoCodeAuthenticationToken(username, code, null, false);
    }

    // Chỉ dùng trong cùng package sau khi provider xác minh.
    static DemoCodeAuthenticationToken authenticated(
            String username,
            Collection<? extends GrantedAuthority> authorities) {
        return new DemoCodeAuthenticationToken(
            username, null, authorities, true);
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
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                "Cannot mark request token as trusted");
        }
        super.setAuthenticated(false);
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }
}
~~~

Giải thích quan trọng:

- <code>unauthenticated(...)</code> gọi constructor với <code>authorities=null</code>; <code>AbstractAuthenticationToken</code> biểu diễn một tập authority trống. <code>isAuthenticated()</code> ban đầu là false.
- <code>authenticated(...)</code> là factory **package-private**, được provider của demo gọi sau xác minh và truyền các authority do server tự tạo. Đây chỉ là convention trong codebase, không phải ranh giới bảo mật chống mọi code cùng package; mọi nơi gọi factory vẫn phải được review.
- <code>setAuthenticated(true)</code> từ bên ngoài bị chặn. Chỉ constructor nội bộ có nhánh tin cậy sử dụng <code>super.setAuthenticated(true)</code>. Không tạo factory public cho caller tự gắn role ADMIN.
- Sau xác thực, <code>credentials=null</code>. Điều đó tránh giữ mã raw trong token kết quả. <code>eraseCredentials()</code> cũng xóa credentials trên request token nếu được gọi.
- <code>principal</code> ở request chưa xác thực chỉ là chuỗi user tự khai; nó chỉ trở thành danh tính được tin cậy khi provider kiểm tra thành công.

Trong Spring Security hiện đại cũng có các token built-in với static factory <code>unauthenticated(...)</code>/<code>authenticated(...)</code>. Quy tắc về nguồn tạo trạng thái tin cậy vẫn giống nhau.

### 4.4. AuthenticationProvider xác minh mã từ nguồn server

Tạo <code>src/main/java/com/example/customauth/DemoCodeAuthenticationProvider.java</code>:

~~~java
package com.example.customauth;

import java.util.List;
import org.springframework.core.env.Environment;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class DemoCodeAuthenticationProvider
        implements AuthenticationProvider {

    private final PasswordEncoder encoder;
    private final String expectedCodeHash;

    public DemoCodeAuthenticationProvider(
            PasswordEncoder encoder, Environment environment) {
        this.encoder = encoder;
        String demoCode = environment.getRequiredProperty("demo.auth.code");
        // Không giữ credential thô như một field của provider.
        this.expectedCodeHash = encoder.encode(demoCode);
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        if (!(authentication instanceof DemoCodeAuthenticationToken request)
                || request.isAuthenticated()) {
            throw new BadCredentialsException("Invalid demo credentials");
        }

        String username = (String) request.getPrincipal();
        String code = (String) request.getCredentials();

        // Kiểm tra code ở server, không tin danh tính hay role từ header.
        boolean codeValid = encoder.matches(
            code == null ? "" : code, expectedCodeHash);
        if (!codeValid || !"learner".equals(username)) {
            throw new BadCredentialsException("Invalid demo credentials");
        }

        DemoCodeAuthenticationToken result =
            DemoCodeAuthenticationToken.authenticated(
                "learner",
                List.of(new SimpleGrantedAuthority("ROLE_LEARNER")));
        result.setDetails(request.getDetails());
        return result;
    }

    @Override
    public boolean supports(Class<?> type) {
        return DemoCodeAuthenticationToken.class.isAssignableFrom(type);
    }
}
~~~

**Phân biệt <code>supports</code> và <code>authenticate</code>:**
- <code>supports(type)</code> chỉ cho biết provider **có thể xử lý loại token**. Nó chưa xác nhận credential nào đúng.
- <code>authenticate</code> bắt buộc kiểm tra bằng chứng trước khi trả token <code>isAuthenticated=true</code>.
- Nếu token được hỗ trợ nhưng credential sai, provider ném <code>BadCredentialsException</code>, không trả một đối tượng đã xác thực.
- Một provider có thể trả <code>null</code> khi không quyết định được và muốn provider tiếp theo xử lý theo contract tương ứng; nhưng **không** dùng <code>null</code> làm “thành công” hay cho phép request không có bằng chứng bỏ qua xác thực.
- Authentication result được cấp chỉ <code>ROLE_LEARNER</code> từ server. Header giả mạo <code>X-Demo-Roles: ROLE_ADMIN</code> hoàn toàn không được đọc trong provider.

Demo tạo hash của một code được cấu hình từ môi trường lúc khởi động. Nó **không** thay thế kho credential production, không có giới hạn số lần thử, secret rotation, mã dùng một lần hay chống replay. Không triển khai cơ chế header-code này ở nơi công khai.

### 4.5. Custom filter chuyển HTTP headers thành request token

Tạo <code>src/main/java/com/example/customauth/DemoCodeFilter.java</code>:

~~~java
package com.example.customauth;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.web.filter.OncePerRequestFilter;

public final class DemoCodeFilter extends OncePerRequestFilter {

    private final AuthenticationManager authenticationManager;

    public DemoCodeFilter(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String username = request.getHeader("X-Demo-User");
        String code = request.getHeader("X-Demo-Code");

        // Không có credential nào: để anonymous/authorization xử lý.
        if (username == null && code == null) {
            chain.doFilter(request, response);
            return;
        }

        // Có một header nhưng thiếu header còn lại: từ chối rõ ràng.
        if (username == null || code == null
                || username.isBlank() || code.isBlank()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        DemoCodeAuthenticationToken requested =
            DemoCodeAuthenticationToken.unauthenticated(username, code);
        requested.setDetails(
            new WebAuthenticationDetailsSource().buildDetails(request));

        final Authentication verified;
        try {
            verified = authenticationManager.authenticate(requested);
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED,
                "Invalid demo credentials");
            return;
        } finally {
            requested.eraseCredentials();
        }

        // Mỗi request tự xác thực: KHÔNG lưu vào HttpSession.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);
        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Filter có các quyết định rõ ràng:
1. Không có cả hai header: không tự login. Request có thể được phép vào public endpoint; protected endpoint sẽ bị authorization yêu cầu xác thực.
2. Header thiếu/mã sai: phản hồi 401 và không lưu trusted Authentication.
3. Credential được đóng vào <code>DemoCodeAuthenticationToken.unauthenticated(...)</code>, gọi <code>AuthenticationManager</code>.
4. Chỉ kết quả trả về từ provider mới được đặt vào SecurityContext. Input token được xóa credentials khi kết thúc xác minh.
5. Vì demo dùng <code>SessionCreationPolicy.STATELESS</code>, không lưu SecurityContext vào HttpSession. Cùng browser muốn truy cập <code>/private</code> ở request kế tiếp phải gửi lại credential hợp lệ.
6. Context được clear trong <code>finally</code> để không rò danh tính sang request khác khi luồng servlet được tái sử dụng.

Đối với sản phẩm thật, cần thêm kiểm soát header trùng lặp/canonicalization, xử lý proxy đáng tin cậy, rate limiting, timeout, metrics và bảo vệ credential trong mọi log. Việc dùng <code>sendError</code> trong filter demo là lựa chọn đơn giản có chủ đích; dự án thật nên nhất quán với <code>AuthenticationEntryPoint</code> và response JSON/problem details.

Một giới hạn quan trọng: custom authentication filter **không tự động chạy bên trong mọi SecurityFilterChain**. Nó chỉ chạy ở những chain mà bạn đăng ký nó. Nếu có nhiều chain hoặc matcher hẹp, phải kiểm tra request thật được đưa vào đúng chain theo quy tắc **first matching SecurityFilterChain**.

### 4.6. SecurityFilterChain, ProviderManager, PasswordEncoder

Tạo <code>src/main/java/com/example/customauth/SecurityConfiguration.java</code>:

~~~java
package com.example.customauth;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    AuthenticationManager demoAuthenticationManager(
            DemoCodeAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager demoAuthenticationManager)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").hasRole("LEARNER")
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex.authenticationEntryPoint(
                (request, response, error) -> response.sendError(401)))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .addFilterBefore(
                new DemoCodeFilter(demoAuthenticationManager),
                AnonymousAuthenticationFilter.class)
            .build();
    }
}
~~~

Lý do:
- <code>ProviderManager</code> biết provider hỗ trợ custom token; các built-in credential khác không được tự dùng để xác thực trong demo này.
- <code>DemoCodeFilter</code> được khởi tạo **trực tiếp khi xây dựng SecurityFilterChain**, **không khai báo là <code>@Component</code> hoặc <code>@Bean</code> Servlet Filter**. Nếu một Filter là bean trong Spring Boot Servlet, nó có thể bị tự đăng ký thêm ở container, dẫn tới chạy hai lần hoặc sai thứ tự.
- <code>addFilterBefore(..., AnonymousAuthenticationFilter.class)</code> cho phép filter custom thiết lập authenticated context trước khi anonymous authentication và authorization chạy.
- <code>SessionCreationPolicy.STATELESS</code>: không dùng HttpSession để lưu/lấy SecurityContext; context chỉ sống trong request demo.
- <code>formLogin</code> và <code>httpBasic</code> bị tắt để người học phân biệt đường xác thực mới với username/password filter sẵn có.
- <code>exceptionHandling(...authenticationEntryPoint...)</code> tạo phản hồi 401 cho protected endpoint khi không có Authentication hợp lệ; người có Authentication thành công nhưng thiếu authority thường bị 403.
- <code>anyRequest().denyAll()</code> giữ các đường dẫn chưa liệt kê không được mặc nhiên cấp quyền. Rule này có tác dụng vì **SecurityFilterChain mẫu khớp mọi request**.
- **Không tắt CSRF** trong demo: chỉ có các GET được cho phép. Nếu về sau thêm POST, phải đánh giá CSRF theo cách browser gửi credential; không tắt CSRF toàn app mà thiếu threat model.

### 4.7. Khai báo mã demo từ biến môi trường

Tạo <code>src/main/resources/application.yml</code>:

~~~yaml
demo:
  auth:
    code: ${DEMO_AUTH_CODE}
~~~

Lúc khởi động, nếu không cấp <code>DEMO_AUTH_CODE</code>, demo không có cấu hình bắt buộc và không nên vận hành. Trong test, sẽ dùng thuộc tính <code>demo.auth.code</code> riêng; mã giả là fixture test, không dùng lại cho sản phẩm thật. Ở production, secret phải lấy từ hệ thống được kiểm soát, bảo vệ đường truyền và vòng đời.

## 5. Quan sát trạng thái request/result bằng Java

Sau khi parser lấy hai header, token ban đầu sẽ có:

~~~java
DemoCodeAuthenticationToken submitted =
    DemoCodeAuthenticationToken.unauthenticated(
        "learner", "test-code-123456789");

// submitted.isAuthenticated() == false
// submitted.getAuthorities().isEmpty() == true
// submitted.getPrincipal().equals("learner") == true
// submitted.getCredentials() chứa raw code chưa được xác minh.
~~~

Đoạn trên được hiểu trong package và dependencies demo, không phải một file Java có <code>main</code> độc lập. **Không** gọi <code>submitted.setAuthenticated(true)</code>: demo chủ đích ném <code>IllegalArgumentException</code> với lời nhắc không được nâng cấp request token thành trusted token.

Sau xác minh thành công:

~~~java
Authentication result = demoAuthenticationManager.authenticate(submitted);

// result.isAuthenticated() == true
// result.getPrincipal().equals("learner") == true
// result.getCredentials() == null
// result.getAuthorities() có đúng ROLE_LEARNER
~~~

Việc đối tượng được trả về có authority LEARNER là do **AuthenticationProvider đã kiểm tra server-side code**. Bản thân chuỗi username “learner” không cho phép suy ra role. Khi code sai, provider ném <code>BadCredentialsException</code> và sẽ không có result authenticated.

Nếu ứng dụng cần hỗ trợ xác thực nhiều bước (ví dụ OTP challenge), không nên đánh dấu token authenticated=true chỉ vì đã hoàn thành bước 1. Có thể dùng một loại request/challenge riêng, lưu trạng thái challenge đã xác minh với TTL/anti-replay, và chỉ tạo fully authenticated token khi mọi điều kiện bắt buộc đạt. Nếu cần mô hình xác thực từng phần có quyền hạn riêng, phải mô hình hóa rõ bằng authentication type/authorities và rule chuyên biệt thay vì đánh lừa <code>isAuthenticated</code>.

## 6. Chạy HTTP request và đọc kết quả

Trên Windows PowerShell, tại thư mục có <code>pom.xml</code>:

~~~powershell
$env:DEMO_AUTH_CODE = "local-demo-code-123456789"
mvn spring-boot:run
~~~

Tại terminal khác:

~~~powershell
# Công khai.
curl.exe -i http://localhost:8080/public

# Không gửi header -> anonymous -> 401.
curl.exe -i http://localhost:8080/private

# Đúng credential -> 200, body "private:learner".
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: local-demo-code-123456789" http://localhost:8080/private

# Sai credential -> 401.
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: bad-code" http://localhost:8080/private

# Chỉ có một header -> 401.
curl.exe -i -H "X-Demo-User: learner" http://localhost:8080/private

# Đúng credential nhưng không có ROLE_ADMIN -> 403.
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: local-demo-code-123456789" http://localhost:8080/admin

# Header giả mạo role không nâng quyền được -> 403.
curl.exe -i -H "X-Demo-User: learner" -H "X-Demo-Code: local-demo-code-123456789" -H "X-Demo-Roles: ROLE_ADMIN" http://localhost:8080/admin
~~~

| Request | Authentication | Authorization | HTTP dự kiến |
| --- | --- | --- | --- |
| GET /public, không header | Anonymous | permitAll | 200, <code>public</code> |
| GET /private, không header | Không có user thật | hasRole LEARNER | 401 |
| GET /private, user/code đúng | Custom token authenticated, ROLE_LEARNER | Đạt | 200, <code>private:learner</code> |
| GET /private, code sai | AuthenticationException | Chưa được xét như user authenticated | 401 |
| GET /private, thiếu một header | Không tạo token hợp lệ | Bị từ chối tại filter | 401 |
| GET /admin, user/code đúng | ROLE_LEARNER | Thiếu ROLE_ADMIN | 403 |
| GET /admin, gửi thêm X-Demo-Roles=ROLE_ADMIN | ROLE_LEARNER | Header giả mạo không có hiệu lực | 403 |

Request thứ hai sau khi đã nhận 200 phải gửi lại các header nếu muốn tiếp tục truy cập <code>/private</code>, vì ví dụ **không lưu login vào HttpSession**. Không đánh đồng custom Authentication token với một session login tự động được duy trì.

## 7. Kiểm thử token, provider và SecurityFilterChain bằng MockMvc

Thêm <code>src/test/java/com/example/customauth/CustomAuthenticationTest.java</code>:

~~~java
package com.example.customauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "demo.auth.code=test-code-123456789")
@AutoConfigureMockMvc
class CustomAuthenticationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AuthenticationManager demoAuthenticationManager;

    @Test
    void requestTokenStartsUntrustedAndCannotSelfAuthenticate() {
        DemoCodeAuthenticationToken request =
            DemoCodeAuthenticationToken.unauthenticated(
                "learner", "test-code-123456789");

        assertThat(request.isAuthenticated()).isFalse();
        assertThat(request.getAuthorities()).isEmpty();
        assertThatThrownBy(() -> request.setAuthenticated(true))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void onlyProviderCanReturnVerifiedAuthority() {
        Authentication result = demoAuthenticationManager.authenticate(
            DemoCodeAuthenticationToken.unauthenticated(
                "learner", "test-code-123456789"));

        assertThat(result.isAuthenticated()).isTrue();
        assertThat(result.getCredentials()).isNull();
        assertThat(result.getPrincipal()).isEqualTo("learner");
        assertThat(result.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactly("ROLE_LEARNER");
    }

    @Test
    void noHeadersPublicAllowedAndPrivateRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void goodCredentialIsAuthenticatedForOneRequest() throws Exception {
        mvc.perform(get("/private")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "test-code-123456789"))
            .andExpect(status().isOk())
            .andExpect(content().string("private:learner"));

        // Stateless: request mới không có header không giữ danh tính cũ.
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongOrPartialHeadersAreRejected() throws Exception {
        mvc.perform(get("/private")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "wrong"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private")
                .header("X-Demo-User", "learner"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private")
                .header("X-Demo-User", "other")
                .header("X-Demo-Code", "test-code-123456789"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authorizedRoleComesFromProviderNotClientHeader() throws Exception {
        mvc.perform(get("/admin")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "test-code-123456789")
                .header("X-Demo-Roles", "ROLE_ADMIN"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedUrlIsDeniedEvenWithValidCredential() throws Exception {
        mvc.perform(get("/unlisted")
                .header("X-Demo-User", "learner")
                .header("X-Demo-Code", "test-code-123456789"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy <code>mvn test</code>. Test chứng minh:
- Request token mặc định chưa được xác thực và không thể nâng quyền qua setter.
- Provider trả kết quả authenticated chỉ sau khi kiểm tra credential.
- Public endpoint không yêu cầu header; protected endpoint yêu cầu Authentication.
- Credential sai/thiếu hoặc username sai dẫn tới 401.
- Đã xác thực **không đồng nghĩa được cấp mọi quyền**: LEARNER vẫn nhận 403 ở <code>/admin</code>.
- Header tự khai role không ảnh hưởng kết quả.
- Một request thành công không tự tạo login session cho request tiếp theo.

Code và status nêu ở đây được thiết kế cho cấu hình demo, không đại diện cho mọi hệ thống có custom exception handler hoặc nhiều filter chain. Khi tích hợp thực tế, thêm test thứ tự filter, đường dẫn loại trừ, context propagation, logout và authentication failure handling.

## 8. Phân biệt authentication chưa hoàn tất với anonymous và ủy quyền

Có ít nhất bốn trạng thái cần phân biệt:

| Trạng thái | Ví dụ | Có nên cho truy cập protected endpoint? |
| --- | --- | --- |
| Không có credential | Request vào <code>/private</code> không header | Không; thường cần authentication |
| Credential đã parse, **chưa xác minh** | <code>DemoCodeAuthenticationToken.unauthenticated(...)</code> | Không; phải gọi provider |
| Credential đã xác minh nhưng thiếu quyền | Result có ROLE_LEARNER, request <code>/admin</code> | Không; authorization trả 403 |
| Credential xác minh và có quyền | Result có ROLE_LEARNER, request <code>/private</code> | Có, nếu các rule khác cũng đạt |

<code>Authentication</code> có thể có principal ngay ở trạng thái chưa xác thực. Đừng lấy <code>getPrincipal()!=null</code> làm bằng chứng đăng nhập; principal lúc đó có thể chỉ là dữ liệu người gọi tự khai. Tương tự, không dựa vào độ dài của <code>getAuthorities()</code> của input token để quyết định credential đã hợp lệ. Tập authority chỉ đáng tin sau provider.

Trong Spring Security, anonymous authentication được xử lý bởi cơ chế riêng và có thể tạo <code>AnonymousAuthenticationToken</code>. Một anonymous token không tương đương user được authentication thực sự dù <code>isAuthenticated()</code> của nó có thể là true. Khi kiểm tra logic trong code của sản phẩm, ưu tiên rule của Spring Security như <code>authenticated()</code> hoặc một <code>AuthenticationTrustResolver</code> thay vì tự suy luận bằng boolean đơn lẻ.

## 9. Authentication token khác token truyền qua mạng

Đặt cùng một chữ “token” cho các thứ sau dễ gây sai thiết kế:

- **Authentication token Java:** đối tượng trong tiến trình, ví dụ <code>DemoCodeAuthenticationToken</code>, có trạng thái trusted/untrusted theo cách khởi tạo.
- **API key hoặc mã demo:** chuỗi được client gửi; chỉ là bằng chứng được đề nghị, có thể sai, bị lộ hoặc bị replay.
- **JWT access token:** chuỗi đã ký có claims, cần xác minh signature, issuer, audience, expiry và các ràng buộc khác. Chỉ parse payload chưa phải xác thực.
- **HttpSession ID:** khóa tham chiếu phiên server-side, thường do cookie mang; Spring Security có thể dùng phiên để lưu SecurityContext.
- **CSRF token:** dùng giảm nguy cơ cross-site request forgery; bản thân nó không chứng minh danh tính và không nên trở thành authority.

Một custom <code>Authentication</code> có thể được tạo từ JWT đã xác minh hoặc từ dữ liệu account đáng tin. Nhưng việc tạo Java object <code>new SomeAuthenticationToken(...)</code> không tự thay thế bước xác minh giao thức gốc.

## 10. Khi cần đăng nhập có session thay vì stateless

Ví dụ ở phần 4 có chủ đích không lưu SecurityContext giữa các request. Nếu xây dựng **đăng nhập stateful**, không chỉ đổi <code>SessionCreationPolicy</code> từ STATELESS sang IF_REQUIRED rồi kỳ vọng mọi custom filter tự ghi session.

Trong Spring Security 6, việc sử dụng <code>SecurityContextHolderFilter</code> theo cấu hình mặc định có thể yêu cầu **lưu SecurityContext một cách tường minh** bằng <code>SecurityContextRepository</code> khi custom authentication thành công. Đồng thời phải xét <code>SessionAuthenticationStrategy</code> để quản lý session fixation, giới hạn phiên và lifecycle. Cần chú ý thứ tự gọi các thành phần này và chỉ save context **sau khi** AuthenticationManager trả kết quả thành công.

Mã minh họa (không phải phần có thể chép độc lập vào demo stateless):

~~~java
// Các thành phần repository, request và response phải được cấu hình
// trong một authentication filter/handler stateful hợp lệ.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

<code>SecurityContextRepository</code> có thể dùng HttpSession, request attributes hoặc repository kết hợp theo thiết kế. Phải biết repo nào thực sự được SecurityFilterChain sử dụng; không chỉ gọi <code>getSession(true)</code> rồi nhét Authentication vào attribute tùy ý. Nếu là <code>AuthenticationFilter</code> chuẩn, có thể kết hợp converter, success/failure handlers và repository theo API framework thay vì tự quản lý tất cả.

Với custom provider, khi logout hoặc credential bị thu hồi, phải dọn phiên/token tương ứng. <code>eraseCredentials()</code> không phải logout: nó chỉ dọn bằng chứng nhạy cảm ra khỏi đối tượng, không vô hiệu hóa session.

## 11. AuthenticationFilter và AuthenticationConverter: lựa chọn khác cho production

Trong demo để nhìn được từng bước, <code>DemoCodeFilter</code> kế thừa <code>OncePerRequestFilter</code> và tự gọi AuthenticationManager. Trong dự án thực tế, một thiết kế Spring Security tự nhiên hơn thường gồm:

1. <code>AuthenticationConverter</code>: chuyển dữ liệu HTTP đã kiểm tra cấu trúc thành custom request token **chưa xác thực**; nếu không áp dụng có thể trả null.
2. <code>AuthenticationManager</code> / <code>ProviderManager</code>: chọn provider hỗ trợ token.
3. <code>AuthenticationProvider</code>: xác minh bằng chứng và trả trusted Authentication.
4. <code>AuthenticationFilter</code>: điều phối xác thực, success/failure handler, security context và repository phù hợp.
5. <code>SecurityFilterChain</code>: khai báo vị trí filter, matcher và authorization.

Tách converter khỏi provider giúp test riêng khâu parse credential, trường hợp thiếu/malformed/duplicate header và khâu xác minh server-side. Không để converter tạo token có authority do client tự khai. Provider phải nhận dạng đúng loại token bằng <code>supports</code> và xử lý failure bằng <code>AuthenticationException</code>; không dùng <code>RuntimeException</code> tùy ý để lẫn lỗi hệ thống với sai credential.

Ở ứng dụng có nhiều provider, <code>ProviderManager</code> có thể thử các provider theo contract của chúng. Một provider xác định credential sai phải báo lỗi phù hợp; không để cơ chế khác vô tình biến credential sai thành một tài khoản hợp lệ với quyền rộng hơn.

## 12. Quy tắc bảo mật của kết quả authentication

Một trusted Authentication nên thỏa các invariant:

| Invariant | Vì sao quan trọng? |
| --- | --- |
| Principal có nguồn gốc server/IdP đã được xác minh | Tránh tin username hoặc userId tự khai |
| Credentials đã được loại khỏi kết quả nếu không cần | Giảm rủi ro log/dump lộ secret |
| Authorities chỉ do server xác định | Chống privilege escalation từ header/client body |
| <code>isAuthenticated=true</code> chỉ sau khi đủ bằng chứng | Không bypass authentication provider |
| Context không rò sang request/thread khác | Không cho user B mang danh tính user A |
| Failure không tạo authenticated context | Request sai phải bị 401 hoặc xử lý thất bại nhất quán |
| Context được lưu **chỉ nếu policy yêu cầu** | Stateless không phát sinh session ngoài chủ đích |
| Session/token revocation có thiết kế nếu cần | Đăng xuất hoặc đổi quyền phải có hiệu lực phù hợp |

Một provider có thể nạp account từ database, kiểm tra trạng thái locked/disabled/expired, xác minh credential, rồi cấp authority từ các role/permission thực sự. Demo đơn giản không có các phần đó, do đó không được coi header-code là phương án thay thế cho authentication production.

Các lựa chọn như <code>ROLE_LEARNER</code> và <code>hasRole("LEARNER")</code> liên quan prefix <code>ROLE_</code> mặc định. Nếu code tạo <code>SimpleGrantedAuthority("LEARNER")</code> mà rule kiểm tra <code>hasRole("LEARNER")</code>, có thể nhận 403 vì authority không khớp. <code>hasAuthority("report:read")</code> so sánh chính xác mã permission, không tự thêm prefix.

## 13. Những lỗi thường gặp và cách kiểm tra

| Lỗi / triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Tạo request token với <code>authenticated=true</code> | Tin dữ liệu chưa xác minh | Factory unauthenticated mặc định, provider tạo trusted token |
| <code>setAuthenticated(true)</code> có thể gọi từ mọi nơi | Bypass provider | Không cho setter nâng quyền; review mọi constructor/factory trusted |
| Client gửi <code>ROLE_ADMIN</code> rồi API cho qua | Cấp authority từ dữ liệu client | Ánh xạ quyền từ server hoặc IdP đã xác minh |
| Provider trả <code>null</code> cho credential sai | Có thể bị hiểu sai trong chuỗi provider | Trả AuthenticationException cho credential sai |
| Credential sai gây 500 | Không xử lý AuthenticationException đúng chỗ | Failure handler/entry point trả response xác thực thất bại |
| GET /private không header nhưng trả 200 | Filter hoặc authorization đang permitAll sai | Test anonymous, inspect matcher, filter order |
| GET /admin với LEARNER trả 200 | Authority hoặc rule bị cấp quá rộng | Test role/permission và nguyên tắc least privilege |
| Đăng nhập một lần nhưng request kế cần header | Stateless, không lưu SecurityContext | Thiết kế stateful nếu thực sự cần session |
| Đăng nhập custom stateful chỉ thành công ở request đầu | Quên saveContext hoặc session strategy | Kiểm tra SecurityContextRepository/Spring Security 6 |
| Filter chạy hai lần | Spring Boot tự đăng ký một Filter bean và Spring Security cũng add | Tránh bean Servlet filter tự đăng ký hoặc disable registration rõ |
| Filter custom không chạy | Đăng ký sai SecurityFilterChain/thứ tự matcher | Xác định chain đầu tiên khớp và vị trí addFilterBefore |
| Secret xuất hiện trong log | In nguyên Authentication/request/header | Redact credential, audit log pipeline và error handler |
| Token JWT đã parse thành công nhưng chưa verify | Nhầm parsing với trust | Verify issuer, audience, chữ ký, expiry, claims phù hợp |
| Thread xử lý request khác mang user cũ | Quên clear SecurityContext | Dọn context finally và dùng cơ chế context propagation đúng |
| Tắt CSRF trên app dùng cookie/session | Bỏ lớp bảo vệ request thay đổi trạng thái | Đánh giá threat model, bật CSRF đúng phạm vi |

## 14. Checklist khi triển khai custom authentication

1. Xác định **vì sao** loại authentication sẵn có chưa phù hợp; ghi rõ ranh giới giữa nguồn credential và Authentication token Java.
2. Thiết kế token chưa xác thực với principal đề nghị, credential thô, authorities rỗng, <code>isAuthenticated=false</code>; chặn nâng trạng thái tùy ý.
3. Định nghĩa provider hỗ trợ đúng class, xác minh bằng nguồn tin cậy và tạo trusted Authentication không giữ raw credentials.
4. Đặt custom filter/converter đúng trong SecurityFilterChain; tránh auto-registration trùng; kiểm tra chain đầu tiên khớp.
5. Chọn stateless hoặc stateful có chủ đích. Với stateful, cấu hình SecurityContextRepository, explicit save và session fixation/session limits khi cần.
6. Khai báo luật authorization theo role/permission; từ chối mặc định những URL chưa phân loại.
7. Xử lý authentication failure/expired account như lỗi xác thực, tránh fallback vô tình thành quyền truy cập rộng.
8. Bảo vệ credential bằng TLS, secret management, rate limit, TTL/anti-replay khi cần và kiểm soát log; không dùng header-code demo ở production.
9. Test token factory, provider thành công/thất bại, 200/401/403, header giả mạo role, concurrent request, session behavior và các endpoint không khớp matcher.
10. Rà soát quyền khi credential/role bị thu hồi, ứng dụng nhiều node và việc lưu context giữa các request.

## 15. Câu hỏi tự kiểm tra

**Câu 1:** Custom Authentication token có <code>principal="admin"</code> nhưng <code>isAuthenticated=false</code>. Có thể cấp quyền ADMIN chưa?  
**Trả lời:** Không. Principal ở request token là lời khai; provider chưa xác minh danh tính và chưa cấp authority đáng tin.

**Câu 2:** Vì sao không cho mọi code gọi <code>setAuthenticated(true)</code>?  
**Trả lời:** Vì như vậy dữ liệu từ request có thể được nâng thành trạng thái tin cậy mà không qua AuthenticationManager/Provider. Trusted token phải chỉ được tạo sau xác minh.

**Câu 3:** Provider xác minh mã đúng và cấp <code>ROLE_LEARNER</code>. Tại sao <code>/admin</code> vẫn 403?  
**Trả lời:** Authentication thành công không đồng nghĩa authorization cho mọi chức năng. Rule cần <code>ROLE_ADMIN</code>, token chỉ có LEARNER.

**Câu 4:** Sau GET /private thành công, request GET /private thứ hai không kèm header có được tự động nhận diện không?  
**Trả lời:** Không trong demo stateless. SecurityContext không được lưu vào HttpSession, nên request mới cần xác thực lại.

**Câu 5:** Tự đặt <code>SecurityContextHolder.setContext(...)</code> trong custom filter stateful có bảo đảm session được lưu cho request sau không?  
**Trả lời:** Không mặc nhiên. Phải hiểu SecurityContextRepository, explicit save trong Spring Security 6 và session authentication strategy đang dùng.

**Câu 6:** <code>Authentication.isAuthenticated()</code> của anonymous token có thể trả true. Vậy nên kiểm tra user bằng cách nào?  
**Trả lời:** Dùng authorization/trust resolver của Spring Security, không chỉ boolean. Anonymous token có semantics riêng và không tương đương người dùng đã xác minh.

**Ghi nhớ:** Custom Authentication token là **một mô hình trạng thái trong server**. Client chỉ được tạo yêu cầu **chưa xác thực**; <code>AuthenticationProvider</code> mới xác minh bằng chứng và sinh kết quả tin cậy với authority do server cấp. SecurityContext giữ kết quả theo chính sách stateless/stateful, còn authorization quyết định mỗi endpoint có được phép hay không.
