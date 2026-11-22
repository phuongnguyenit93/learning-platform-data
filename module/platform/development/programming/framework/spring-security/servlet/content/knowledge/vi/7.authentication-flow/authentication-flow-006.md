# AuthenticationFilter, AuthenticationConverter và AuthenticationManagerResolver trong Spring Security Servlet

Trong Spring Security Servlet, xác thực HTTP không chỉ là “đọc username/password rồi so sánh”. Một hệ thống có thể nhận nhiều dạng request, nhiều phương thức chứng minh danh tính, hoặc nhiều vùng người dùng/tenant cần được kiểm tra bởi các bộ quản lý xác thực khác nhau. Bộ ba **`AuthenticationFilter` – `AuthenticationConverter` – `AuthenticationManagerResolver`** giúp phân tách ba quyết định đó thành các trách nhiệm rõ ràng: **lọc request cần xác thực**, **chuyển HTTP request thành Authentication chưa được kiểm chứng**, và **chọn AuthenticationManager để kiểm tra Authentication đó**.

Bài học nằm trong mảng **Luồng xác thực** của **Spring Security – Servlet**, dùng API hiện đại của Spring Security 6.x, Java 17+ và Spring Boot 3.x. Ví dụ thực thi bên dưới chọn Spring Boot 3.3.5 và HTTP form parameters để tập trung vào contract của ba thành phần; nó **không** tự triển khai hệ thống login production, cơ sở dữ liệu người dùng hay token/session đăng nhập.

## 1. Mục tiêu và bản đồ trách nhiệm

Sau bài học, bạn cần giải thích được:

1. Khi nào `AuthenticationFilter` tham gia request và khi nào nó **đi tiếp mà không thử xác thực**.
2. `AuthenticationConverter.convert(HttpServletRequest)` nhận gì và cần trả về gì; ý nghĩa của `null`, token chưa xác thực và `AuthenticationException`.
3. `AuthenticationManagerResolver<HttpServletRequest>` chọn `AuthenticationManager` theo bối cảnh **của request**, còn manager/provider mới thực hiện kiểm chứng credentials.
4. Cách kết quả Authentication được chuyển tới success/failure handling; tại sao một success handler có thể kết thúc HTTP response **mà không gọi controller**.
5. Cách tích hợp filter vào `SecurityFilterChain`, lựa chọn đúng thứ tự, phạm vi áp dụng, session policy và CSRF.
6. Cách kiểm thử các nhánh đúng credentials, sai credentials, thiếu trường, manager không phù hợp và request không cần xác thực.

| Thành phần | Input chính | Output/hiệu ứng | Không phải trách nhiệm |
| --- | --- | --- | --- |
| `AuthenticationFilter` | Servlet request/response + chain và các collaborator | Quyết định có thử authentication, gọi converter/resolver/manager, xử lý thành công/thất bại | Không tự định nghĩa logic kiểm tra password của mọi ứng dụng |
| `AuthenticationConverter` | `HttpServletRequest` | Một `Authentication` yêu cầu xác thực, hoặc `null`/lỗi phù hợp | Không xác nhận password đúng, không cấp quyền tin cậy |
| `AuthenticationManagerResolver<C>` | Một context kiểu `C`; ở đây là `HttpServletRequest` | `AuthenticationManager` cần dùng trong bối cảnh đó | Không tự biến request thành authenticated user |
| `AuthenticationManager` | Authentication do converter tạo | Authentication đã xác thực hoặc `AuthenticationException` | Không tự chọn HTTP URL/parse JSON khi chỉ nhận Authentication |
| `AuthenticationProvider` | Loại Authentication mà provider hỗ trợ | Kiểm chứng theo chính sách cụ thể | Không nên tin role do client gửi |
| `SecurityFilterChain` | Request matcher + các security filters đã cấu hình | Tập filter bảo vệ request | Không tương đương một AuthenticationManager |

Điểm cốt lõi: **converter chuyển đổi; resolver định tuyến; manager xác minh; filter điều phối**. Trong một request xác thực đúng, cả bốn việc có thể diễn ra liên tiếp, nhưng chúng không nên bị gom vào một đoạn code đọc form rồi tự đặt `isAuthenticated=true`.

## 2. Vị trí trong Servlet filter chain

Với ứng dụng Spring MVC, các Servlet filter chạy trước controller. Spring Security dùng `DelegatingFilterProxy` nối tới `FilterChainProxy`, rồi chọn `SecurityFilterChain` khớp với request.

~~~text
HTTP request
    |
Servlet container / DelegatingFilterProxy
    |
FilterChainProxy
    |  chọn SecurityFilterChain theo matcher và thứ tự
    v
... các filter trước AuthenticationFilter ...
    |
AuthenticationFilter
    |-- RequestMatcher không khớp --------> filter tiếp theo
    |
    |-- RequestMatcher khớp
        |
        v
    AuthenticationConverter.convert(request)
        |-- null -------------------------> filter tiếp theo
        |-- AuthenticationException ------> failure handler
        |
        v
    Authentication request (thường chưa xác thực)
        |
        v
    AuthenticationManagerResolver.resolve(request)
        |
        v
    AuthenticationManager.authenticate(authentication)
        |-- AuthenticationException ------> failure handler
        |
        v
    Authentication result đã kiểm chứng
        |
        v
    SecurityContext / repository tùy cấu hình
        |
        v
    AuthenticationSuccessHandler -> response
~~~

Đây là sơ đồ **logic**, không phải log runtime có chuỗi class cố định. Filter order thực tế phụ thuộc configurer/phiên bản và filter đã đăng ký. Khi một request không khớp `RequestMatcher`, converter/resolver không cần được gọi. Nếu converter trả `null`, `AuthenticationFilter` cho request đi tiếp thay vì coi `null` tự động là “password sai”. Với request **đã được thử xác thực** nhưng credentials không hợp lệ, manager hoặc converter cần báo thất bại theo contract thích hợp.

**Phân biệt rõ hai thời điểm:**

- **Startup:** tạo `AuthenticationFilter`, converter, resolver/manager, success/failure handler rồi build `SecurityFilterChain`.
- **Request time:** filter nhận từng request khớp matcher; converter, resolver, manager được gọi theo request tương ứng.

Cấu hình ở startup có thể tái sử dụng các manager/provider đã được xây dựng. Không nên tạo BCrypt encoder, kết nối database hay toàn bộ AuthenticationManager **mới ở mỗi request** chỉ để resolver đưa ra quyết định.

## 3. AuthenticationFilter: bộ điều phối, không phải bộ kiểm chứng mật khẩu

`org.springframework.security.web.authentication.AuthenticationFilter` là filter hỗ trợ mô hình authentication theo request. Có hai cách tạo thường gặp:

~~~java
// Khi mọi request phù hợp đều dùng cùng AuthenticationManager:
AuthenticationFilter single = new AuthenticationFilter(manager, converter);

// Khi cần chọn manager theo request:
AuthenticationFilter routed = new AuthenticationFilter(resolver, converter);
~~~

Hai dòng trên là **mảnh code minh họa**: `manager`, `resolver` và `converter` phải là các instance được định nghĩa phù hợp. Loại generic của resolver trong ví dụ Servlet là `AuthenticationManagerResolver<HttpServletRequest>`.

### 3.1. RequestMatcher là cổng đầu tiên

Filter có thể nhận `RequestMatcher` để quyết định loại request nào cần thử xác thực:

~~~java
filter.setRequestMatcher(request ->
    "POST".equals(request.getMethod())
        && "/login".equals(request.getServletPath()));
~~~

Đây là ví dụ cho một ứng dụng Servlet được mount tại root với servlet-path phù hợp. Khi có context-path, custom servlet mapping, proxy hoặc multi-servlet, cần sử dụng matcher tương thích với routing thực tế. Ví dụ runnable phần sau dùng helper bỏ context path từ URI để kiểm thử minh bạch.

Không nên đăng ký một custom login filter rồi để nó cố đọc credentials trên **mọi GET/POST**. Xác định rõ HTTP method, path, content type và các điều kiện thuộc giao thức authentication mà bạn thực sự hỗ trợ.

### 3.2. Nhánh success và failure

Khi converter tạo authentication request và manager xác thực thành công, filter xử lý authentication result và gọi `AuthenticationSuccessHandler`. Handler có thể:

- Trả response HTTP 200 với một nội dung xác nhận.
- Redirect sau form login.
- Làm thêm việc cần thiết trong flow authentication đã thiết kế.

Ngược lại, `AuthenticationFailureHandler` có thể trả 401, xử lý thông báo lỗi hoặc redirect phù hợp. Không có cam kết rằng sau success handler request **luôn** tiếp tục tới MVC controller. Trong ví dụ dưới đây, handler **chủ động trả 200** tại endpoint login; controller không xử lý endpoint đó.

**Cẩn thận với persistence:** một Authentication thành công ở một request không tự làm các request tiếp theo đăng nhập vĩnh viễn. Việc duy trì trạng thái phụ thuộc session policy, `SecurityContextRepository`, cơ chế lưu/truyền token hoặc cookies. Một flow stateless chỉ xác nhận thông tin có thể không cấp session hoặc token nào cả.

## 4. AuthenticationConverter: từ dữ liệu HTTP thành yêu cầu xác thực

`org.springframework.security.web.authentication.AuthenticationConverter` là functional interface được dùng để tạo `Authentication` từ `HttpServletRequest`.

Hình dạng contract:

~~~java
Authentication convert(HttpServletRequest request);
~~~

Một converter tốt cần trả lời các câu hỏi:

- Dữ liệu chứng minh danh tính nằm ở đâu: form fields, Basic header, bearer token, client certificate hay một header chuyên biệt?
- Request này có mang credentials theo giao thức được hỗ trợ không?
- Trường nào bắt buộc, giới hạn input ra sao, lỗi cấu trúc được báo thế nào?
- Kiểu Authentication nào phù hợp để AuthenticationManager/Provider hiểu?
- Làm sao tránh ghi log, lưu hoặc tiết lộ raw secret ngoài vòng đời cần thiết?

### 4.1. Ví dụ converter cho form username/password

~~~java
AuthenticationConverter converter = request -> {
    String username = request.getParameter("username");
    String password = request.getParameter("password");

    if (username == null || username.isBlank()
            || password == null || password.isBlank()) {
        throw new BadCredentialsException("Missing credentials");
    }

    return UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);
};
~~~

Đoạn trên là **mảnh code**, cần các import của Spring Security và Servlet, và nằm trong vị trí cấu hình thích hợp. Nó tạo token có `principal=username` và `credentials=password` với `isAuthenticated()==false`. Nó **không** xác thực password hoặc cấp authority. Lệnh `unauthenticated(...)` truyền tải rõ ràng việc token chỉ là yêu cầu kiểm chứng.

**Quan trọng:** không dùng factory `UsernamePasswordAuthenticationToken.authenticated(...)` trong converter để tự cấp role dựa trên body/header mà client gửi. Token “đã xác thực” phải là kết quả của thành phần thực sự kiểm tra bằng chứng và xác định authorities đáng tin.

### 4.2. Khi nào trả null? Khi nào ném exception?

Hai hành vi không tương đương:

- `return null`: converter **không tạo authentication request**. Với `AuthenticationFilter`, đây thường là tín hiệu bỏ qua authentication attempt và để chuỗi filter tiếp tục. Hữu ích với converter nhận request không có credential tùy chọn.
- Ném `AuthenticationException` (ví dụ `BadCredentialsException`): request này **được coi là một authentication attempt thất bại**. Filter có thể chuyển tới failure handler.
- Trả Authentication chưa xác thực: có dữ liệu đủ để yêu cầu manager kiểm chứng. Thành công/thất bại thực chất phụ thuộc manager/provider.

Chọn hành vi dựa trên giao thức. Ở một endpoint chỉ dành cho login, thiếu username/password nên được xử lý như lỗi đăng nhập; trong ví dụ bài này, converter ném `BadCredentialsException` và failure handler trả 401. Ở một filter theo dõi token tùy chọn trên endpoint public, `null` có thể hợp lý hơn. Không đánh đồng hai trường hợp.

### 4.3. Converter không phải input validator duy nhất

Converter có thể kiểm tra shape và định dạng, nhưng chưa đủ để bảo vệ hệ thống. Manager/provider vẫn cần kiểm tra mật khẩu, trạng thái user, tenant membership hoặc chữ ký token. Nếu có các field như `role`, `isAdmin` trong request, đừng sao chép chúng thành trusted authorities.

Form parameters được dùng ở đây để giữ ví dụ gọn. Khi thiết kế JSON login, cần converter đọc JSON body đúng một lần, tuân thủ content type/encoding và giới hạn body; tránh viết filter tiêu thụ request body rồi làm filter/controller khác không đọc được nữa. Nếu dùng HTTP Basic, có sẵn các thành phần tiêu chuẩn; không nên tự viết converter Basic chỉ để thay thứ đã được framework bảo trì tốt.

## 5. AuthenticationManagerResolver: chọn manager theo request

`AuthenticationManagerResolver<C>` có ý nghĩa “với context này, dùng manager nào?”. Trong Servlet, context thường là `HttpServletRequest`:

~~~java
AuthenticationManagerResolver<HttpServletRequest> resolver = request -> {
    String path = request.getServletPath();
    if (path.startsWith("/tenant-a/")) {
        return tenantAManager;
    }
    if (path.startsWith("/tenant-b/")) {
        return tenantBManager;
    }
    throw new BadCredentialsException("Unsupported authentication area");
};
~~~

Đây là **đoạn minh họa** về việc chọn giữa các manager đã được tạo; các biến `tenantAManager` và `tenantBManager` phải được cấp từ cấu hình tin cậy. Một request không có manager phù hợp cần được xử lý rõ ràng; không âm thầm fallback vào manager cho phép tất cả.

### 5.1. Resolver không xác thực request

Resolver chỉ trả về bộ thực thi. Trong sơ đồ:

~~~text
request path /login/alpha -> alpha manager
request path /login/beta  -> beta manager

alpha manager + ("alice", đúng password) -> authenticated
alpha manager + ("bob", đúng password của beta) -> rejected
beta manager  + ("bob", đúng password) -> authenticated
~~~

Một request chọn được alpha manager chưa chứng minh caller thuộc alpha. **Caller tự chọn URL**. Chính alpha manager/provider phải kiểm tra credentials và quyền phù hợp cho tenant alpha. Chỉ dựa trên `X-Tenant`, `Host` hoặc giá trị do client gửi để cấp role là lỗ hổng ranh giới tin cậy.

### 5.2. Khi nào nên dùng resolver?

- Hai khu vực authentication dùng cấu hình/user store khác nhau.
- Multi-tenant cần chọn nguồn kiểm tra credential hoặc provider theo tenant đã được xác định bằng chính sách phù hợp.
- API có nhiều dạng token/issuer và cần chọn manager theo context đã được xác thực/kiểm tra an toàn.
- Một ứng dụng có yêu cầu xác thực khác nhau theo request nhưng muốn giữ converter/filter composition rõ ràng.

**Không nhất thiết cần resolver cho ứng dụng đơn giản.** Nếu toàn bộ login request dùng một manager, constructor `AuthenticationFilter(authenticationManager, converter)` thường dễ hiểu hơn.

Một số cơ chế khác đã có resolver/filter chuyên dụng, ví dụ resource server với bearer token. Hãy dùng công cụ chuẩn của Spring Security khi chúng đáp ứng nhu cầu, thay vì viết lại xác minh JWT/issuer/signature thủ công.

### 5.3. Lỗi thiết kế resolver thường gặp

| Thiết kế | Vấn đề |
| --- | --- |
| Mỗi request tạo AuthenticationManager, hash password và khởi tạo client database mới | Tốn tài nguyên, hành vi không nhất quán; resolver chỉ nên chọn manager đã chuẩn bị |
| Tự động chọn manager “mở” khi tenant không tồn tại | Fail-open: có thể bỏ qua kiểm chứng |
| Tin `X-Tenant: admin` như chứng cứ user là admin | Header tự khai không phải bằng chứng danh tính/quyền |
| Dùng manager cho tenant A nhưng không ràng buộc credential thuộc tenant A | Dễ cross-tenant access |
| Nuốt exception rồi trả authentication thành công | Biến lỗi thành lỗ hổng xác thực |
| Chọn manager theo host do proxy không đáng tin tạo ra | Có thể bị host-header/proxy-header spoofing |
| Lặp logic phân quyền trong resolver | Trộn authentication routing với authorization; khó audit |
| Định nghĩa quá nhiều manager khi chỉ cần một | Tăng độ phức tạp và khả năng cấu hình lệch |

## 6. So sánh với các cơ chế có sẵn và vai trò của filter chain

Không phải dự án Spring Security nào cũng cần tự tạo `AuthenticationFilter`.

| Nhu cầu | Điểm bắt đầu hợp lý | Ghi chú |
| --- | --- | --- |
| HTTP Basic username/password | `http.httpBasic(...)` | Dùng filter chuẩn cho HTTP Basic và provider phù hợp |
| Form login trang web | `http.formLogin(...)` | Có flow form/login, success/failure/session phù hợp |
| OAuth2 Login | `oauth2Login(...)` | Ủy thác flow phức tạp cho framework |
| Resource server JWT | `oauth2ResourceServer(...jwt(...))` | Xác minh bearer token/issuer bằng stack phù hợp |
| Một endpoint login đặc thù (form/headers/custom token) | `AuthenticationFilter + AuthenticationConverter` | Tự kiểm soát protocol adapter và response |
| Chọn manager theo request | `AuthenticationManagerResolver<HttpServletRequest>` | Cần đảm bảo manager vẫn xác thực độc lập |
| Cần khác cả cơ chế và bộ filter theo URL | Nhiều `SecurityFilterChain` với `securityMatcher` và `@Order` | Không nhầm chọn chain với chọn manager |

**Hai lần lựa chọn độc lập:**

1. `FilterChainProxy` chọn **SecurityFilterChain** đầu tiên khớp request, qua `securityMatcher` và chain order.
2. Nếu chain đó chứa `AuthenticationFilter` và request khớp filter's `RequestMatcher`, resolver mới chọn **AuthenticationManager**.

Resolver không làm công việc của `securityMatcher`, và chain matcher không tự kiểm tra credentials. Khi debug hệ thống multi-chain/multi-tenant, hãy kiểm tra cả hai quyết định theo thứ tự.

Một filter được chèn vào chain ở vị trí đã định vẫn cần rule authorization phù hợp. Đừng mặc định “có filter xác thực là toàn bộ endpoint đã được bảo vệ”. Khi một request không được filter custom xử lý, những filter/authorization rules khác vẫn quyết định response cuối cùng.

## 7. Ví dụ hoàn chỉnh Java 17+: hai tenant, một AuthenticationFilter

Ví dụ chạy cục bộ này dùng một `AuthenticationFilter` cho hai endpoint:

- `POST /login/alpha`: manager alpha chấp nhận `alice / alpha-pass`.
- `POST /login/beta`: manager beta chấp nhận `bob / beta-pass`.
- `GET /public/ping`: endpoint công khai không cần converter/resolver.
- Request login thành công trả **200** và body ngắn để quan sát; thất bại trả **401**.
- Flow được thiết kế **stateless, không tạo session login và không phát token**. Gọi login thành công không có nghĩa một request tiếp theo tự được đăng nhập.

**Phạm vi bảo mật minh họa:** user/password chỉ dùng local, hash bằng BCrypt để provider kiểm tra; API không có database, rate limiting, 2FA hay audit production. Trong sản phẩm thật không hardcode passwords/tenant credentials như code bên dưới.

### 7.1. Cấu trúc thư mục

~~~text
auth-filter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/authfilter/
    │   ├── AuthFilterDemoApplication.java
    │   ├── SecurityConfiguration.java
    │   └── PublicController.java
    └── test/java/demo/authfilter/
        └── AuthenticationFilterTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'auth-filter-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

Starter security kéo các module core/web/config/crypto tương thích qua dependency management của Spring Boot. `spring-security-test` ở test scope phục vụ MockMvc integration; không thêm vào runtime production.

### 7.2. Application entry point

Tệp `src/main/java/demo/authfilter/AuthFilterDemoApplication.java`:

~~~java
package demo.authfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthFilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthFilterDemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration: converter, resolver và filter

Tệp `src/main/java/demo/authfilter/SecurityConfiguration.java`:

~~~java
package demo.authfilter;

import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.security.web.authentication.AuthenticationFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationConverter loginConverter() {
        return request -> {
            String username = request.getParameter("username");
            String password = request.getParameter("password");

            if (username == null || username.isBlank()
                    || password == null || password.isBlank()) {
                throw new BadCredentialsException("Missing credentials");
            }

            return UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);
        };
    }

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> managerResolver(
            PasswordEncoder encoder) {

        // Hash chỉ được tạo khi bean khởi tạo, không phải mỗi request.
        String alphaHash = encoder.encode("alpha-pass");
        String betaHash = encoder.encode("beta-pass");

        AuthenticationManager alphaManager =
            localManager("alice", alphaHash, "TENANT_ALPHA", encoder);

        AuthenticationManager betaManager =
            localManager("bob", betaHash, "TENANT_BETA", encoder);

        return request -> {
            String path = applicationPath(request);

            if ("/login/alpha".equals(path)) {
                return alphaManager;
            }
            if ("/login/beta".equals(path)) {
                return betaManager;
            }

            throw new BadCredentialsException(
                "Unsupported login endpoint");
        };
    }

    private static AuthenticationManager localManager(
            String expectedUser,
            String encodedPassword,
            String authority,
            PasswordEncoder encoder) {

        return candidate -> {
            Object raw = candidate.getCredentials();

            if (!(raw instanceof String suppliedPassword)) {
                throw new BadCredentialsException(
                    "Invalid credentials");
            }

            if (!expectedUser.equals(candidate.getName())
                    || !encoder.matches(
                        suppliedPassword, encodedPassword)) {
                throw new BadCredentialsException(
                    "Invalid credentials");
            }

            // Chỉ manager đã kiểm chứng credentials tạo trusted result.
            return UsernamePasswordAuthenticationToken.authenticated(
                expectedUser,
                null,
                List.of(new SimpleGrantedAuthority(authority)));
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationConverter loginConverter,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        AuthenticationFilter loginFilter =
            new AuthenticationFilter(resolver, loginConverter);

        // Filter chỉ thử xác thực ở đúng hai endpoint POST.
        loginFilter.setRequestMatcher(
            SecurityConfiguration::isLoginRequest);

        loginFilter.setSuccessHandler((request, response, result) -> {
            response.setStatus(200);
            response.setHeader("Cache-Control", "no-store");
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write(
                "authenticated:" + result.getName());
        });

        loginFilter.setFailureHandler((request, response, exception) ->
            response.sendError(401, "Invalid credentials"));

        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))

            // Demo chỉ trả login result, không tạo session/cookie.
            // Không copy ngoại lệ CSRF này vào app dùng session login.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                "/login/alpha", "/login/beta"))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.POST,
                    "/login/alpha", "/login/beta")
                    .permitAll()
                .anyRequest().denyAll())

            .addFilterAt(
                loginFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }

    private static boolean isLoginRequest(
            HttpServletRequest request) {

        if (!"POST".equals(request.getMethod())) {
            return false;
        }

        String path = applicationPath(request);
        return "/login/alpha".equals(path)
            || "/login/beta".equals(path);
    }

    private static String applicationPath(
            HttpServletRequest request) {

        // getRequestURI bao gồm context path, bỏ phần đó để so URL.
        String uri = request.getRequestURI();
        String contextPath = request.getContextPath();
        return uri.substring(contextPath.length());
    }
}
~~~

Giải thích theo đúng thứ tự tạo và chạy:

1. Spring Boot tạo `PasswordEncoder` bean (BCrypt).
2. `loginConverter()` cung cấp cách đọc form fields và tạo unauthenticated token.
3. `managerResolver()` tạo hai manager đã cấu hình; resolver **chỉ lựa chọn** dựa trên path đã được giới hạn trước.
4. `securityFilterChain(...)` tạo một `AuthenticationFilter` với converter và resolver.
5. Filter matcher chỉ chọn `POST /login/alpha` và `POST /login/beta`; GET endpoint public không bị filter cố đăng nhập.
6. Khi đúng credentials, manager trả `UsernamePasswordAuthenticationToken.authenticated(...)` với principal là username đáng tin, credentials null, authority tenant do **server cấp**. Converter không tự cấp authority.
7. Success handler trả 200 và response body; failure handler trả 401. Endpoint login **không** có controller mapping.
8. `SessionCreationPolicy.STATELESS` nhấn mạnh ví dụ không lưu trạng thái login vào HTTP session. Vì không phát token, response chỉ chứng minh một lượt request đã được xác thực.
9. Ngoại lệ CSRF chỉ áp dụng cho đúng hai endpoint demo và đi cùng thiết kế không sử dụng cookie/session xác thực. Với browser session login thực tế, phải đánh giá **login CSRF** và thường giữ bảo vệ CSRF thay vì sao chép ngoại lệ này.
10. `addFilterAt(loginFilter, UsernamePasswordAuthenticationFilter.class)` đặt custom filter tại vị trí bảo mật framework biết cho username/password authentication. Đây là cách **đặt thứ tự**, không phải lời cam kết tự động xóa mọi filter cùng vị trí nếu bạn còn bật thêm cơ chế form login. Tránh cấu hình hai filter cạnh tranh cùng endpoint.

Trong code Java 17, `instanceof String suppliedPassword` là pattern matching; nó bảo đảm chỉ gọi encoder khi credentials thật sự là chuỗi. Manager không sử dụng raw password sau khi kiểm tra, và authenticated token được tạo với credentials `null`. Đây là demo dùng manager lambda; sản phẩm thật nên dùng provider/user store phù hợp, hashing policy, lockout/rate limiting, audit và quản lý credentials an toàn.

### 7.4. Controller chỉ cho public endpoint

Tệp `src/main/java/demo/authfilter/PublicController.java`:

~~~java
package demo.authfilter;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Không có controller `/login/alpha` hoặc `/login/beta`. Chính filter nhận login POST và success/failure handler tạo HTTP response. Nếu vô tình bỏ filter khỏi SecurityFilterChain, URL login có thể bị policy/handler routing xử lý khác và test sẽ phát hiện.

## 8. MockMvc: kiểm tra converter, manager selection và kết quả HTTP

Tệp `src/test/java/demo/authfilter/AuthenticationFilterTests.java`:

~~~java
package demo.authfilter;

import jakarta.servlet.http.HttpServletRequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFilterTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    AuthenticationConverter loginConverter;

    @Autowired
    AuthenticationManagerResolver<HttpServletRequest> resolver;

    @Test
    void converterOnlyCreatesAnAuthenticationRequest() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/login/alpha");

        request.addParameter("username", "alice");
        request.addParameter("password", "alpha-pass");

        Authentication candidate = loginConverter.convert(request);

        assertFalse(candidate.isAuthenticated());
        assertEquals("alice", candidate.getPrincipal());
        assertEquals("alpha-pass", candidate.getCredentials());
        assertTrue(candidate.getAuthorities().isEmpty());
    }

    @Test
    void resolverSelectsManagerThatVerifiesCredentials() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("POST", "/login/alpha");

        Authentication candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alpha-pass");

        Authentication verified =
            resolver.resolve(request).authenticate(candidate);

        assertTrue(verified.isAuthenticated());
        assertEquals("alice", verified.getName());
        assertNull(verified.getCredentials());
        assertEquals("TENANT_ALPHA",
            verified.getAuthorities().iterator().next().getAuthority());
    }

    @Test
    void publicRequestIsNotHandledAsLogin() throws Exception {
        mockMvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void alphaAcceptsItsOwnCredentials() throws Exception {
        mockMvc.perform(post("/login/alpha")
                .param("username", "alice")
                .param("password", "alpha-pass"))
            .andExpect(status().isOk())
            .andExpect(content().string("authenticated:alice"));
    }

    @Test
    void betaAcceptsItsOwnCredentials() throws Exception {
        mockMvc.perform(post("/login/beta")
                .param("username", "bob")
                .param("password", "beta-pass"))
            .andExpect(status().isOk())
            .andExpect(content().string("authenticated:bob"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mockMvc.perform(post("/login/alpha")
                .param("username", "alice")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void alphaCredentialsCannotLoginThroughBeta() throws Exception {
        mockMvc.perform(post("/login/beta")
                .param("username", "alice")
                .param("password", "alpha-pass"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingPasswordIsRejectedByConverter() throws Exception {
        mockMvc.perform(post("/login/alpha")
                .param("username", "alice"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Tám test cung cấp ba mức bằng chứng:

| Nhóm test | Kiểm tra | Điều không nên suy ra |
| --- | --- | --- |
| Unit converter | Request có form field trở thành Authentication chưa xác thực, authority rỗng | Không chứng minh mật khẩu đúng |
| Unit resolver + manager | Manager alpha từ request path thực sự kiểm chứng và cấp authority | Chưa chứng minh filter order/HTTP integration |
| MockMvc public | Request công khai không bị custom filter chiếm mất | Không có nghĩa mọi endpoint đều public |
| MockMvc login thành công | Filter matcher + converter + resolver + manager + success handler hợp tác đúng | Không chứng minh user đã có session/token cho request sau |
| MockMvc login thất bại | Sai password, sai manager hoặc thiếu field trả 401 | Không phải kết luận tất cả lỗi web đều phải trả 401 |

`@AutoConfigureMockMvc` trong test tích hợp này giúp MockMvc dùng Spring Security filter chain của ApplicationContext. Khi tự xây dựng MockMvc theo cách riêng, cần kiểm tra security filters được áp dụng; nếu không, test có thể bỏ qua authentication filter mà chạy sai lệch so với Servlet runtime.

### 8.1. Chạy ứng dụng

Nếu đã cài Gradle tương thích và đặt đúng các tệp ở trên:

~~~bash
gradle test
gradle bootRun
~~~

Với Gradle wrapper của project:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows, dùng `gradlew.bat test` và `gradlew.bat bootRun`. Các class của Spring nằm trong dependencies, nên chỉ dùng `javac`/`java` không có classpath tương ứng sẽ không chạy được. Khi tests PASS, Gradle thông thường báo build thành công; không cố định nguyên văn log, thời gian chạy hoặc số dòng vì chúng phụ thuộc môi trường.

### 8.2. Thử endpoint bằng curl

Ứng dụng chạy mặc định tại `http://localhost:8080` trong môi trường học nếu cổng chưa bị thay đổi:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i -X POST http://localhost:8080/login/alpha \
  -d 'username=alice&password=alpha-pass'
curl -i -X POST http://localhost:8080/login/beta \
  -d 'username=bob&password=beta-pass'
curl -i -X POST http://localhost:8080/login/alpha \
  -d 'username=alice&password=wrong'
curl -i -X POST http://localhost:8080/login/beta \
  -d 'username=alice&password=alpha-pass'
curl -i -X POST http://localhost:8080/login/alpha \
  -d 'username=alice'
~~~

Đây là **form-urlencoded** do curl gửi với option `-d`; converter đọc bằng `request.getParameter(...)`. Trên Windows PowerShell, nếu alias `curl` khác binary curl, hãy dùng `curl.exe`. Các ký tự password này chỉ dùng cục bộ; với bất kỳ tài khoản thực nào, hãy dùng HTTPS và tránh hardcode secret trong shell history.

| Request | HTTP status dự kiến | Body thành công |
| --- | --- | --- |
| GET `/public/ping` | 200 | `pong` |
| POST `/login/alpha`, alice/alpha-pass | 200 | `authenticated:alice` |
| POST `/login/beta`, bob/beta-pass | 200 | `authenticated:bob` |
| POST `/login/alpha`, alice/wrong | 401 | Không phụ thuộc body lỗi |
| POST `/login/beta`, alice/alpha-pass | 401 | Không phụ thuộc body lỗi |
| POST `/login/alpha`, thiếu password | 401 | Không phụ thuộc body lỗi |

Không kỳ vọng response login success là redirect hoặc cookie session, vì handler và session policy của ví dụ không tạo chúng. Những endpoint ngoài danh sách được bảo vệ bởi rule `denyAll()` trong cùng chain; nếu cần trả 401 thay vì 403 cho request chưa đăng nhập, phải cấu hình authentication entry point/authorization behavior có chủ đích, không suy đoán từ bảng ở trên.

## 9. Đọc chính xác hai loại “thành công”

Để tránh lỗi về ý nghĩa, cần phân biệt:

- **Converter success:** tạo được Authentication request từ HTTP data. Nó chưa xác thực.
- **Authentication success:** manager/provider kiểm chứng credentials và trả Authentication trusted.
- **Success handler response success:** filter quyết định phản hồi HTTP của *authentication endpoint*. Nó **không tự động** chứng minh người dùng có quyền truy cập mọi resource sau này.

Ví dụ gọi POST `/login/alpha` và nhận HTTP 200 chỉ chứng minh credentials được alpha manager chấp nhận *ở request đó*. Vì ứng dụng minh họa là stateless và không phát token, client không có bằng chứng mới để tự động gọi một endpoint riêng ở request tiếp theo. Trong một flow thật, việc duy trì đăng nhập cần hợp đồng rõ ràng: session cookie + repository thích hợp, hoặc token đã được ký/cấp và xác minh trong các request tiếp theo, v.v.

### 9.1. Khi nào dùng SecurityContextRepository?

Ở flow form login có session, xác thực thành công thường cần đưa trusted Authentication vào SecurityContext và lưu qua repository thích hợp để request sau tái sử dụng. Các phiên bản Spring Security hiện đại chú trọng việc lưu context **tường minh** tại điểm authentication. `AuthenticationFilter` có tích hợp SecurityContext/Repository và handler nhưng việc persistence chịu ảnh hưởng cấu hình repository, session policy và cơ chế sử dụng.

Nếu tự sửa repository, cần đồng bộ với cách những filter khác tải context, session fixation protection, CSRF, logout và cơ chế lưu session. Không chỉ viết `SecurityContextHolder.getContext().setAuthentication(result)` rồi giả định mọi request tiếp theo đã được login.

### 9.2. Khi nào cần tiếp tục vào controller?

Nếu mục tiêu là **xác thực mỗi request API** rồi cho controller xử lý, bạn cần kiến trúc filter và success behavior đúng cho per-request authentication, hoặc dùng filter chuẩn như `BasicAuthenticationFilter`/bearer token filters. Trong ví dụ này, `AuthenticationSuccessHandler` chủ động ghi response và kết thúc request login, nên nó **không** đóng vai trò một “header checker” trong suốt pipeline cho mọi API request.

Việc cố gắn success handler trả 200 vào filter áp dụng cho mọi URL có thể khiến controller **không bao giờ được gọi**. Kiểm tra contract của filter trước khi thay filter chuẩn bằng một filter custom.

### 9.3. Khi nào converter trả null vẫn có thể tạo 401/403 về sau?

Nếu converter trả `null`, authentication filter thường đi tiếp. Một authorization rule phía sau có thể vẫn chặn request thiếu authenticated principal. Như vậy kết quả HTTP **phụ thuộc cả chain**, không thể kết luận `null => 200` hay `null => 401` chỉ bằng cách nhìn converter.

Trong bài này, thiếu password ở endpoint login ném `BadCredentialsException` nên failure handler trả 401 một cách rõ ràng; đây là lựa chọn giao thức của ví dụ, không phải quy luật cho mọi converter.

## 10. Kỹ thuật chọn manager: path, header, tenant, token

Một resolver có thể xét path, request header, query, host, issuer hoặc một thông tin khác; **dữ liệu dùng để chọn manager không mặc nhiên đáng tin**. Quyết định nên theo các nguyên tắc:

1. Có tập giá trị hợp lệ/whitelist và chính sách mặc định **từ chối** khi không xác định được manager.
2. Dùng các manager/provider đã được cấu hình và tái sử dụng, không xây lại đối tượng đắt tiền mỗi request.
3. Đối chiếu ranh giới tenant/issuer khi manager thực hiện authentication, không chỉ ở bước routing.
4. Nếu dùng `Host`, forwarded headers hoặc gateway metadata, bảo đảm proxy thực sự đáng tin và normalize các nguồn đó.
5. Nếu chọn manager dựa trên JWT issuer, phải xác minh chữ ký và issuer/audience theo cơ chế đáng tin; không tin payload JWT chưa được xác thực như một lời khẳng định quyền.
6. Không để một manager “mặc định” quá dễ dãi xử lý request bị route sai.
7. Có test **chéo tenant**: credentials của tenant A không được chấp nhận bởi manager tenant B.
8. Không đưa password/header token vào logs; nếu muốn quan sát routing, log path/manager-id không nhạy cảm và kết quả tổng quát.

Tình huống minh họa về ranh giới tin cậy:

~~~text
Client: POST /login/beta
        username=alice&password=alpha-pass

Filter: path khớp login endpoint
Converter: tạo authentication request principal=alice
Resolver: chọn beta manager
Beta manager: kiểm tra against beta credentials -> rejected
Failure handler: HTTP 401
~~~

Việc request khai `alice` hay client cố ý chọn path beta không khiến beta manager cấp quyền TENANT_BETA. Đây là điểm mạnh của việc tách routing và verification.

## 11. Các lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Điểm kiểm tra |
| --- | --- | --- |
| Filter không bao giờ chạy | `RequestMatcher` không khớp; chain khác được chọn; filter chưa được thêm vào chain | HTTP method/path, `securityMatcher`, `@Order`, `addFilterAt` |
| Converter luôn trả null | Không thấy header/param hoặc parser không khớp content type | Request thật, tên form field, contract null vs exception |
| Đã tạo Authentication nhưng vẫn 401 | Manager/provider từ chối credential; resolver chọn sai manager | Kiểu token, password encoder, manager selection |
| Request đúng password nhưng bị fail chéo tenant | Resolver chọn manager có nguồn user khác | Kiểm tra tenant routing/identity binding |
| Response 200 nhưng controller không chạy | Success handler đã kết thúc request | Auth filter flow, handler design |
| Request tiếp theo lại như chưa login | Không lưu session/token hoặc stateless policy | Repository, session, token flow |
| POST luôn 403 trước converter | CSRF filter chặn unsafe request | CSRF configuration, cookie/session client model |
| Role do client khai được chấp nhận | Converter/provider tự tin vào payload | Không đặt trusted authorities từ nguồn chưa xác minh |
| Hai filter cùng xử lý endpoint | Custom filter trùng form login/Basic configurer | Filter ordering, URL matcher, configurers trùng nhau |
| Resolver cấp manager mới cho mỗi request | Factory nằm trong resolve callback | Tạo manager khi khởi tạo bean; resolve chỉ chọn |
| Manager không hỗ trợ kiểu Authentication | Converter tạo token/provider không hỗ trợ | `supports(...)` của provider, manager architecture |
| Log có raw credentials | Logging request/form/token quá rộng | Redact, giảm log security, không in Authorization |
| Test converter pass nhưng MockMvc fail | Đã kiểm tra parsing, chưa kiểm tra filter/chain/handler | Integration test với security filter chain |
| MockMvc trả 200 nhưng runtime khác | MockMvc thiếu filter chain hoặc cấu hình context khác | `@AutoConfigureMockMvc` / áp dụng springSecurity() |

### 11.1. Debug theo thứ tự của request

Đừng bắt đầu bằng “tắt CSRF” hoặc “thêm permitAll cho mọi URL”. Hãy lần lượt xác minh:

1. URL/method có thuộc đúng `SecurityFilterChain` không?
2. Chain đó có chứa `AuthenticationFilter` ở vị trí mong muốn không?
3. Filter's `RequestMatcher` có khớp request không?
4. `AuthenticationConverter` có nhận đúng field/header và tạo token chưa xác thực không?
5. Resolver chọn manager nào? Có nằm trong whitelist được thiết kế không?
6. Manager thực sự kiểm tra credential/issuer/user state/tenant binding chưa?
7. Authentication kết quả mang principal, authorities gì? Có loại bỏ credentials nhạy cảm không?
8. Failure/success handler phản hồi thế nào? Có đúng status và không leak secret không?
9. Nếu cần request tiếp theo đã login, có cơ chế session/token/repository rõ ràng chưa?
10. Authorization/CSRF ở filter khác có từ chối trước/sau authentication attempt không?

**Không đọc stack trace như bằng chứng role đúng/sai** nếu chưa xác định chính xác failure path. Với request bị CSRF filter chặn trước, converter có thể chưa hề chạy. Với request ngoài chain, custom filter có thể chưa được xem xét.

### 11.2. Bật log để quan sát (môi trường học)

Có thể dùng thuộc tính:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Lúc startup, tìm thông tin về security filter chain và các filter được cấu hình. Lúc request, quan sát đường đi bảo mật và status, nhưng không giả định mọi phiên bản đều có cùng chuỗi log. Tránh bật debug/trace quá rộng ở production và đặc biệt tránh log raw password/token/session cookie. Test với HTTPS khi có credentials không phải demo cục bộ.

Khi dùng IDE debugger, đặt breakpoint ở callback converter, resolver, manager lambda và success/failure handlers. Một lần đăng nhập alpha hợp lệ nên quan sát được bốn bước theo thứ tự; GET public nên không gọi các callback login.

## 12. Bài tập vận dụng

1. Vẽ lại đường đi của `POST /login/alpha` theo thứ tự: matcher → converter → resolver → manager → success/failure handler. Với từng bước, ghi loại input/output.
2. Thay `return UsernamePasswordAuthenticationToken.unauthenticated(...)` bằng authenticated token cấp authority trực tiếp trong converter. Giải thích vì sao đây là anti-pattern nguy hiểm (không nên triển khai thật).
3. Tạo unit test: thiếu username khiến converter ném `BadCredentialsException`; vì sao demo chọn exception thay vì `null`?
4. Thử dùng `alice/alpha-pass` ở endpoint beta; giải thích vì sao resolver **chọn được manager** nhưng xác thực vẫn thất bại.
5. Thêm tenant gamma có user/secret và một manager riêng, bảo đảm fallback không cấp quyền. Viết đủ test gamma đúng, gamma sai và credentials alpha qua gamma.
6. Sửa filter matcher để chỉ nhận POST; thử gọi GET cùng URL và chỉ ra tại sao kết quả cuối có thể đến từ authorization/MVC thay vì login filter.
7. Nếu muốn login persist với session, liệt kê những thay đổi kiến trúc cần đánh giá: repository, session fixation, CSRF, cookie, logout và security context lifecycle. Không chỉ thêm một dòng `setAuthentication(...)`.
8. Giải thích vì sao `addFilterAt` không phải “thay thế cơ chế form login” trong mọi cấu hình. Khi cùng một URL có hai filter, bạn sẽ debug ra sao?
9. Chuyển ví dụ form-urlencoded sang JSON: converter phải làm gì với content type, body, parsing exception và dữ liệu credential nhạy cảm?
10. Khi thêm một API JWT, nên dùng cấu hình resource server có sẵn hay tự viết converter + manager? Những công việc xác minh signature, issuer, audience và key rotation nào không được bỏ qua?
11. Với một endpoint chỉ cho user có `TENANT_ALPHA`, quy tắc authorization cần kiểm tra ở đâu? Vì sao resolver chọn alpha manager chưa thay thế authorization rule?
12. Giải thích sự khác biệt giữa status 401 do failure handler trong ví dụ và 403 do CSRF/authorization từ filter khác. Chẩn đoán từ log mà không lộ password.

## 13. Checklist trước khi đưa authentication flow custom vào production

- [ ] Có lý do rõ ràng cần custom filter thay vì `httpBasic`, `formLogin` hay OAuth2/resource-server support.
- [ ] URL/method/content type được match chính xác; filter chain bao phủ đúng resource cần bảo vệ.
- [ ] Converter tạo **unauthenticated request**, không tin role/tenant do client tự khai.
- [ ] Resolver fail-closed, chọn từ manager đã cấu hình, không tạo manager mới mỗi request.
- [ ] Manager/provider xác minh đầy đủ secret, user state, tenant/issuer binding; không hardcode credentials.
- [ ] Dùng password hash/password encoder thích hợp cho credential dạng password; áp dụng rate limiting/lockout khi cần.
- [ ] Xử lý thành công/thất bại có chủ đích, status và response không lộ secret.
- [ ] Quyết định rõ session/token/refresh/logout và SecurityContext persistence.
- [ ] Đánh giá CSRF theo mô hình cookie/session và client browser, không tắt vô điều kiện.
- [ ] Bảo đảm HTTPS, audit logging an toàn, metrics và test cross-tenant.
- [ ] Test cả converter, manager selection, đúng/sai credentials và HTTP integration qua Spring Security filter chain.
- [ ] Phân biệt authentication success với authorization; các endpoint vẫn có rule phân quyền rõ ràng.

**Tóm tắt:** `AuthenticationFilter` quyết định request nào được xử lý và điều phối authentication attempt; `AuthenticationConverter` diễn dịch HTTP thành một yêu cầu Authentication chưa được kiểm chứng; `AuthenticationManagerResolver` chọn manager thích hợp theo ngữ cảnh; **manager/provider mới chứng minh danh tính**, rồi success/failure handling quyết định HTTP response và cơ chế lưu ngữ cảnh được áp dụng theo cấu hình. Nắm đúng ranh giới này là nền tảng để mở rộng luồng xác thực Servlet mà không tạo lỗ hổng nhầm lẫn giữa routing, verification, session và authorization.
