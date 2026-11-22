# Thêm bộ lọc khi cần và kiểm soát đúng vị trí, phạm vi áp dụng

## 1. Bài toán: vì sao một bộ lọc đúng chức năng vẫn có thể gây lỗi bảo mật?

Trong ứng dụng Spring Security Servlet, mỗi HTTP request đi qua nhiều bộ lọc (filter) trước khi đến controller. Một filter có thể đọc header, xác thực thông tin, thêm dữ liệu vào request, ghi log, từ chối request hoặc xử lý response. Khi thêm filter mới, **vị trí trong chuỗi** và **những request mà filter được chạy** quan trọng ngang với nội dung xử lý.

Ví dụ, đội phát triển muốn đánh dấu những request đã xác thực truy cập `/api/private/**` để các thành phần phía sau dùng thông tin kiểm tra:

- Nếu filter chạy **trước xác thực**, nó chưa thể tin `SecurityContext` chứa người dùng thật.
- Nếu filter chạy **sau phân quyền**, nó chỉ đánh dấu request đã vượt qua bước phân quyền; request 401/403 bị chặn sớm sẽ không đi qua filter đó.
- Nếu filter bị đăng ký cả ở **Servlet container** lẫn trong `SecurityFilterChain`, nó có thể chạy hai lần hoặc ở thứ tự không mong muốn.
- Nếu filter vô tình áp dụng cho `/api/public/**`, `/site/**`, login, health check hoặc CORS preflight, nó có thể phá vỡ luồng vốn không cần chức năng đó.
- Nếu filter dùng sai cách để từ chối truy cập, phản hồi 401/403 và quá trình xử lý ngoại lệ có thể không đúng thiết kế.

Do đó, cách làm đúng là: **xác nhận filter thật sự cần thiết → chọn điểm đặt theo dữ liệu đã sẵn sàng → giới hạn phạm vi ở các lớp phù hợp → kiểm thử cả request phải chạy và request không được chạy**.

Bài này tập trung vào **Spring Security Servlet với `HttpSecurity`, `SecurityFilterChain` và `OncePerRequestFilter`**, dùng Java 17+ và Spring Boot 3.x / Spring Security 6.x. Với WebFlux dùng `SecurityWebFilterChain`, `ServerHttpSecurity` và `WebFilter`; không áp dụng trực tiếp các lớp Servlet trong bài.

## 2. Hiểu các lớp chuỗi lọc trước khi tự thêm filter

Luồng rút gọn của một yêu cầu HTTP:

```text
Trình duyệt / HTTP client
        |
        v
Servlet container filter chain
        |
        +-- các Servlet Filter do container/Boot đăng ký
        |
        +-- DelegatingFilterProxy ("springSecurityFilterChain")
                  |
                  v
             FilterChainProxy
                  |
                  +-- chọn SecurityFilterChain ĐẦU TIÊN phù hợp
                  |       |
                  |       +-- SecurityContext / headers / CSRF ...
                  |       +-- các filter xác thực
                  |       +-- các filter xử lý anonymous
                  |       +-- ExceptionTranslationFilter
                  |       +-- AuthorizationFilter
                  |       +-- filter tự thêm (nếu đặt tại đây)
                  |
                  v
             DispatcherServlet -> Controller
```

**Phân biệt chính xác:**

- `DelegatingFilterProxy` nối bộ lọc của Servlet container với Spring bean `springSecurityFilterChain`.
- `FilterChainProxy` quản lý các `SecurityFilterChain` và chọn **chuỗi đầu tiên có RequestMatcher phù hợp**; không cộng dồn mọi security chain khớp request.
- Mỗi `SecurityFilterChain` gồm một danh sách filter có thứ tự. Hai chain có thể khác nhau về xác thực, CSRF, CORS, phân quyền và filter tự thêm.
- `AuthorizationFilter` thực thi quyết định phân quyền cho HTTP request khi dùng `authorizeHttpRequests`.
- Bộ lọc được đặt **trước** một filter khác sẽ chưa thấy kết quả mà filter phía sau tạo ra. Bộ lọc được đặt **sau** một filter có thể không chạy nếu filter phía trước đã kết thúc request hoặc ném exception.

Vì lý do này, không nên suy luận vị trí chỉ từ tên gọi của custom filter hoặc sao chép máy móc câu lệnh `addFilterBefore(..., UsernamePasswordAuthenticationFilter.class)` từ một hướng dẫn khác.

### 2.1. Những mốc quan trọng để chọn vị trí

Sơ đồ sau minh họa thứ tự **tương đối** phổ biến, không phải danh sách bất biến mọi filter trong mọi cấu hình:

```text
SecurityContextHolderFilter
        |
bảo vệ khai thác: CORS / CSRF / headers tùy cấu hình
        |
các bộ lọc xác thực (ví dụ BasicAuthenticationFilter)
        |
AnonymousAuthenticationFilter
        |
ExceptionTranslationFilter
        |
AuthorizationFilter
        |
controller / Servlet
```

Trong ứng dụng cụ thể còn có các filter cho form login, logout, OAuth2, session, request cache và nhiều chức năng khác. Thứ tự thực tế được xác định bởi cấu hình đã bật. Chỉ bật mức log phù hợp trong môi trường phát triển để quan sát chain thật.

Tự hỏi trước khi thêm filter:

1. Nó có cần đọc `Authentication` hoặc vai trò của người dùng không? Nếu có, đặt sau khi cơ chế xác thực thích hợp đã chạy.
2. Nó có cần đọc kết quả phân quyền không? Nếu có, đặt **sau `AuthorizationFilter`**, đồng thời hiểu rằng request bị từ chối sẽ không tới filter.
3. Nó có cần tự quyết định từ chối truy cập không? Khi đó hãy ưu tiên `AuthorizationManager`; nếu bắt buộc dùng filter ném exception bảo mật, phải hiểu vị trí của `ExceptionTranslationFilter` và cách trả 401/403.
4. Nó có phải cơ chế bảo vệ có sẵn của Spring Security không? Nếu có, hãy cấu hình DSL tích hợp thay vì dựng lại cả filter.
5. Nó là chức năng xử lý HTTP kỹ thuật không phụ thuộc security chain (ví dụ dữ liệu tracing ở gateway) hay chức năng có liên quan ngữ cảnh bảo mật? Câu trả lời quyết định dùng Servlet filter độc lập hay security filter.

## 3. Khi nào nên thêm filter và khi nào nên dùng điểm mở rộng khác?

| Nhu cầu | Điểm mở rộng thường phù hợp | Lý do |
| --- | --- | --- |
| Bật HTTP Basic, OAuth2 Resource Server, form login, CORS, CSRF, security headers | DSL có sẵn của `HttpSecurity` | Spring Security đã quản lý vị trí, tích hợp ngoại lệ và cơ chế chuẩn. |
| Phân quyền theo role, authority, endpoint, tenant | `authorizeHttpRequests` với `AuthorizationManager`, hoặc bảo mật ở mức phương thức | Quy tắc phân quyền thuộc lớp phân quyền, dễ kiểm thử và kiểm toán hơn. |
| Xác thực giao thức riêng thật sự không có hỗ trợ sẵn | `AuthenticationFilter` hoặc custom filter phối hợp với `AuthenticationManager`/`AuthenticationProvider` | Cần vị trí và hợp đồng xác thực rõ ràng; không tự nhồi việc xác minh token vào filter tùy ý. |
| Đánh dấu/ghi nhận request sau khi vượt qua phân quyền | Custom filter sau `AuthorizationFilter`, đặt trong chain phù hợp | Có thể dùng `SecurityContext` và biết request đã qua cổng phân quyền HTTP. |
| Ghi nhận correlation ID cho cả request bị từ chối trước khi vào security chain | Servlet filter/gateway được đăng ký trước security proxy | Mục tiêu cần bao phủ cả phản hồi 401/403 và các filter phía trước controller. |
| Chuyển đổi JSON lỗi từ controller | `@RestControllerAdvice` / `ProblemDetail` | Đây là xử lý MVC, không cần filter tự viết để bao mọi exception. |
| Xử lý trước/sau controller và cần thông tin MVC handler | `HandlerInterceptor` hoặc MVC advice | Có ngữ cảnh controller/handler rõ ràng hơn filter ở mức Servlet. |
| Ràng buộc dữ liệu input, validation nghiệp vụ | Bean Validation, service và domain | Filter không phải nơi mặc định cho mọi quy tắc nghiệp vụ. |

Một filter mới tạo thêm một điểm có thể ảnh hưởng bảo mật và hiệu năng. Đặc biệt, nếu nhu cầu chỉ là “đọc JWT rồi gắn `SecurityContext`”, hãy kiểm tra trước hỗ trợ `oauth2ResourceServer(...).jwt(...)`. Tự triển khai lại xác minh chữ ký, hạn dùng, audience, issuer và các tình huống lỗi thường làm giảm độ an toàn.

## 4. Ba lớp quyết định **phạm vi chạy** của filter

### 4.1. `securityMatcher` chọn cả chuỗi bảo mật

`http.securityMatcher("/api/**")` đặt điều kiện để **toàn bộ `SecurityFilterChain`** có hiệu lực cho đường dẫn `/api/**`. Nếu request không khớp, `FilterChainProxy` thử chain tiếp theo.

Ví dụ:

```java
http.securityMatcher("/api/**");
```

Filter bạn thêm vào chain này **không** chạy trong chain fallback dành cho `/site/**`. Tuy nhiên, các filter của Servlet container độc lập với Spring Security vẫn có thể chạy cho cả hai.

### 4.2. `requestMatchers` trong `authorizeHttpRequests` chọn quy tắc phân quyền

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/private/**").authenticated()
    .anyRequest().denyAll()
);
```

Các matcher này chỉ quyết định **quyền** của request đã được chọn vào chain. Chúng **không tự giới hạn** việc một custom filter trong cùng chain có được gọi trên đường dẫn public hay không. Nếu filter nằm trước hoặc sau `AuthorizationFilter` và request public được `permitAll`, filter vẫn có thể chạy với request đó.

Vì vậy, **`permitAll()` không đồng nghĩa với “bỏ qua tất cả filter”**. Ngược lại, `web.ignoring()` bỏ qua các bộ lọc bảo mật, làm mất những lớp bảo vệ như security headers. Với endpoint công khai, thường nên giữ trong chain và dùng `permitAll()`.

### 4.3. `shouldNotFilter` giới hạn chính custom `OncePerRequestFilter`

Nếu filter chỉ áp dụng cho một nhánh nhỏ thuộc `/api/**`, triển khai `shouldNotFilter(HttpServletRequest)` để trả `true` khi **bỏ qua** request. Điều này tránh chạy logic không cần thiết ngay cả khi chain rộng hơn.

Ví dụ:

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return !request.getServletPath().startsWith("/api/private/");
}
```

Quy tắc này áp dụng cho các endpoint bắt đầu bằng `/api/private/` trong ứng dụng demo, và không áp dụng `/api/public/**`. Với ứng dụng có servlet mapping, nhiều context hoặc yêu cầu match phức tạp, ưu tiên một `RequestMatcher` được thiết kế/test cùng cách Spring Security diễn giải URL, thay vì dựa vào `contains(...)` hay tiền tố quá rộng.

**Tổng hợp:** `securityMatcher` chọn chain, `requestMatchers` chọn quy tắc quyền, và `shouldNotFilter` chọn nơi chạy custom filter bên trong chain đã chọn. Ba thứ không thay thế nhau.

## 5. Chọn `addFilterBefore`, `addFilterAfter`, `addFilterAt`

`HttpSecurity` cung cấp các cách chèn theo **mốc filter**, không yêu cầu bạn tính thủ công “vị trí số 13”.

| API | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| `addFilterBefore(custom, AnchorFilter.class)` | Đưa filter vào trước mốc được chỉ định. | Cần chuẩn bị dữ liệu để mốc phía sau dùng; hoặc can thiệp trước bước kiểm tra. |
| `addFilterAfter(custom, AnchorFilter.class)` | Đưa filter vào sau mốc được chỉ định. | Cần dữ liệu/kết quả mà các filter trước đó đã tạo. |
| `addFilterAt(custom, AnchorFilter.class)` | Đặt custom filter tại vị trí dành cho một filter chuẩn. | Chỉ khi thật sự thay đổi cách một cơ chế chuẩn hoạt động và đã xử lý filter gốc; không coi là “tự động loại bỏ filter cũ”. |

**Ví dụ theo mục tiêu:**

- Muốn ghi nhận request **đã vượt qua phân quyền HTTP**, có thể dùng `addFilterAfter(custom, AuthorizationFilter.class)`.
- Muốn thực thi một kiểm tra riêng **trước `AuthorizationFilter`** khi `Authentication` đã có, cần phân tích `addFilterBefore(custom, AuthorizationFilter.class)`. Điểm này thường nằm phía sau `ExceptionTranslationFilter` trong cấu hình thông dụng, nhưng vẫn phải kiểm tra chain thực tế và các ngoại lệ.
- Muốn tạo một kiểu xác thực mới, cần đặt filter ở giai đoạn xác thực và tích hợp với `AuthenticationManager`/`SecurityContext`/entry point; không chọn mốc chỉ vì nó xuất hiện trên một blog.
- Muốn thay một filter chuẩn ở cùng vị trí, ưu tiên DSL cấu hình chính thức trước. `addFilterAt` **không phải phép bảo đảm “replace hoàn toàn”** nếu cơ chế cũ vẫn thêm filter của nó; phải loại bỏ/tránh đăng ký trùng theo cấu hình được hỗ trợ.

**Vị trí ảnh hưởng xử lý lỗi:** `ExceptionTranslationFilter` chủ yếu bắt những `AuthenticationException` và `AccessDeniedException` phát sinh **trong phần chuỗi chạy phía sau nó**. Nếu custom filter ném các exception đó ở vị trí nằm phía trước, không được mặc định kỳ vọng Spring Security sẽ chuyển thành 401/403 đúng cách. Cần thiết kế điểm đặt và kiểm thử âm tính; nếu là lỗi nghiệp vụ, cân nhắc MVC/authorization thay vì filter.

## 6. Ví dụ Java 17+: đánh dấu request riêng tư sau phân quyền

Yêu cầu:

- Tất cả request `/api/**` thuộc **API security chain** ưu tiên cao.
- `GET /api/public/ping` cho truy cập công khai.
- `GET /api/private/whoami` yêu cầu đăng nhập HTTP Basic, sau đó filter đánh dấu request và lưu tên người dùng đã xác thực vào **request attribute** để controller quan sát.
- `GET /site/home` thuộc **fallback chain** và không có filter API.
- Request API chưa xác thực, đường dẫn bị cấm hoặc request public không được gắn dấu bởi filter.
- Ví dụ phải giữ cơ chế CSRF và các bảo vệ HTTP mặc định; không tắt bảo vệ chỉ để test chạy được.

**Giới hạn ví dụ:** Header `X-Demo-Filter: applied` chỉ là dấu hiệu hỗ trợ học/kiểm thử, không phải bằng chứng bảo mật để client tin cậy. Trong sản phẩm, audit thật cần chính sách log, bảo vệ dữ liệu và xử lý lỗi phù hợp. Tài khoản mẫu chỉ dùng trong môi trường học.

### 6.1. Dependency và ứng dụng khởi động

Dự án Spring Boot 3.x có Gradle plugin/Java toolchain phù hợp, dùng `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đoạn này là phần `dependencies` trong dự án Boot đã có plugin Gradle, **không phải file build hoàn chỉnh**. Mọi lớp sau dùng package `demo.filterchain`.

Tệp `src/main/java/demo/filterchain/FilterChainApplication.java`:

```java
package demo.filterchain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterChainApplication.class, args);
    }
}
```

### 6.2. Viết `OncePerRequestFilter` có phạm vi hẹp

Tệp `src/main/java/demo/filterchain/PrivateRequestMarkerFilter.java`:

```java
package demo.filterchain;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Ví dụ: chỉ đánh dấu request riêng tư đã vượt qua phân quyền HTTP.
 * Không dùng @Component hoặc @Bean để tránh Boot tự đăng ký thêm ở container.
 */
public final class PrivateRequestMarkerFilter extends OncePerRequestFilter {
    public static final String REQUEST_PRINCIPAL =
            PrivateRequestMarkerFilter.class.getName() + ".principal";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getServletPath().startsWith("/api/private/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        // Trong ví dụ, filter được đặt sau AuthorizationFilter;
        // request không đủ quyền sẽ bị chặn trước khi tới đây.
        String principal = authentication == null
                ? "not-available"
                : authentication.getName();

        request.setAttribute(REQUEST_PRINCIPAL, principal);
        response.setHeader("X-Demo-Filter", "applied");

        chain.doFilter(request, response);
    }
}
```

**Điểm cần hiểu:**

1. `OncePerRequestFilter` giảm nguy cơ chạy lặp trong **một lần xử lý dispatch phù hợp**; nó có cơ chế đánh dấu đã lọc, nhưng không hứa “toàn bộ vòng đời request, kể cả async/error dispatch, tuyệt đối chỉ một lần”. Các hook `shouldNotFilterAsyncDispatch` và `shouldNotFilterErrorDispatch` có vai trò riêng nếu cần xử lý các dispatch đó.
2. `shouldNotFilter` trả `true` để bỏ qua. Với `/api/public/ping`, filter không đọc context hay thêm header.
3. Filter **không được** `@Component` hoặc khai báo như một bean `Filter` trong ví dụ này; Spring Boot có thể tự đăng ký Servlet filter bean bên ngoài Spring Security, tạo tình trạng chạy thêm hoặc sai thứ tự.
4. `Authentication` được đọc từ `SecurityContextHolder` sau mốc phân quyền; trong request riêng tư được phép, có danh tính đã xác thực. Không coi riêng `authentication.isAuthenticated()` là phép thay thế phân quyền: anonymous token cũng có thể có thuộc tính này, tùy loại xác thực.
5. `chain.doFilter(request, response)` chuyển quyền xử lý tiếp. Bỏ dòng này sẽ chặn các filter/Servlet phía sau, trừ khi filter cố tình tự kết thúc request và đã trả response đúng.
6. Trong ví dụ, chỉ lưu tên người dùng trong request attribute của cùng request; **không biến tên do client gửi thành danh tính**, không đưa thông tin nhạy cảm vào header kiểm thử.

### 6.3. Chọn đúng chain và vị trí filter

Tệp `src/main/java/demo/filterchain/SecurityConfig.java`:

```java
package demo.filterchain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/private/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .addFilterAfter(
                new PrivateRequestMarkerFilter(),
                AuthorizationFilter.class
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/site/home").permitAll()
            .anyRequest().denyAll()
        );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("READER")
                .build()
        );
    }
}
```

Giải thích từng ranh giới:

- `@Order(1)` khiến chain `/api/**` được xét trước. Nếu request là `/api/private/whoami`, chain này được chọn và chain `fallbackSecurity` không chạy thêm lần nữa.
- `securityMatcher("/api/**")` giới hạn phạm vi toàn API chain. Phần `requestMatchers("/api/private/**").authenticated()` là quy tắc phân quyền **bên trong** chain đó.
- `.addFilterAfter(..., AuthorizationFilter.class)` đảm bảo custom filter đứng sau bước `AuthorizationFilter` trong thứ tự security chain. Nếu request không được phép, filter không được gọi trong luồng thông thường vì `AuthorizationFilter` từ chối trước.
- `httpBasic(...)` chỉ dùng trong ví dụ để kiểm thử xác thực dễ dàng. Một ứng dụng dùng Bearer/JWT nên cấu hình Resource Server và dùng test tương ứng.
- `fallbackSecurity` **không dùng `securityMatcher`**, nên có thể xử lý các request còn lại và `denyAll` theo mặc định. Nếu bỏ fallback, request không khớp bất kỳ `SecurityFilterChain` nào có thể đi qua mà không được Spring Security bảo vệ.
- Đoạn cấu hình không gọi `csrf.disable()`. Các yêu cầu thay đổi trạng thái vẫn chịu quy tắc CSRF mặc định nếu phù hợp; ví dụ chỉ sử dụng `GET`.

**Không lấy ví dụ này làm mẫu bảo mật thông tin đăng nhập cho production:** mật khẩu tĩnh nằm trong source chỉ phục vụ bài học; môi trường thật sử dụng quản lý danh tính và bí mật an toàn, TLS và kiểm soát quyền phù hợp.

### 6.4. Controller dùng dấu đã được filter gắn

Tệp `src/main/java/demo/filterchain/DemoController.java`:

```java
package demo.filterchain;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("result", "pong");
    }

    @GetMapping("/api/private/whoami")
    public Map<String, Object> whoami(
            Authentication authentication,
            HttpServletRequest request
    ) {
        Object atFilter = request.getAttribute(
                PrivateRequestMarkerFilter.REQUEST_PRINCIPAL
        );
        return Map.of(
            "user", authentication.getName(),
            "filterApplied", atFilter != null,
            "principalAtFilter", atFilter == null ? "" : atFilter.toString()
        );
    }

    @GetMapping("/site/home")
    public String home() {
        return "site home";
    }
}
```

Khi người dùng `reader` đã xác thực gọi `GET /api/private/whoami`, JSON dự kiến có các giá trị:

```json
{
  "user": "reader",
  "filterApplied": true,
  "principalAtFilter": "reader"
}
```

Thứ tự các trường JSON không được bảo đảm vì `Map.of` không cam kết thứ tự. Để xác minh, so sánh theo tên trường (ví dụ JSONPath), không so sánh một chuỗi JSON với thứ tự cố định.

Với `GET /api/public/ping`, filter được bỏ qua, nhưng endpoint vẫn đi qua API security chain và các filter bảo vệ khác trong chain. Với `GET /site/home`, filter không có mặt vì URL thuộc chain khác.

## 7. Kiểm thử bắt buộc: cả phạm vi chạy và phạm vi không chạy

Tệp `src/test/java/demo/filterchain/FilterPlacementTests.java`:

```java
package demo.filterchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class FilterPlacementTests {

    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedPrivateRequestRunsFilterAfterAuthorization()
            throws Exception {
        mvc.perform(
                get("/api/private/whoami")
                    .with(httpBasic("reader", "demo-password"))
            )
            .andExpect(status().isOk())
            .andExpect(header().string("X-Demo-Filter", "applied"))
            .andExpect(jsonPath("$.user").value("reader"))
            .andExpect(jsonPath("$.filterApplied").value(true))
            .andExpect(jsonPath("$.principalAtFilter").value("reader"));
    }

    @Test
    void unauthenticatedPrivateRequestIsRejectedBeforeCustomFilter()
            throws Exception {
        mvc.perform(get("/api/private/whoami"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void wrongPasswordIsRejectedBeforeCustomFilter() throws Exception {
        mvc.perform(
                get("/api/private/whoami")
                    .with(httpBasic("reader", "wrong-password"))
            )
            .andExpect(status().isUnauthorized())
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void publicApiRequestSkipsCustomFilter() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("pong"))
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void fallbackChainDoesNotContainApiFilter() throws Exception {
        mvc.perform(get("/site/home"))
            .andExpect(status().isOk())
            .andExpect(content().string("site home"))
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }

    @Test
    void unknownApiRouteIsDeniedWithoutRunningFilter()
            throws Exception {
        mvc.perform(
                get("/api/not-allowed")
                    .with(httpBasic("reader", "demo-password"))
            )
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist("X-Demo-Filter"));
    }
}
```

Đây là test tích hợp Spring Boot với MockMvc, cần có `spring-security-test` và đăng ký Spring Security filters trong MockMvc. `@AutoConfigureMockMvc` theo cấu hình mặc định của Spring Boot tích hợp các filter được đăng ký; nếu tự cấu hình MockMvc standalone, phải gắn đúng chain và test lại.

Chạy từ gốc dự án Spring Boot có wrapper:

```bash
./gradlew test --tests demo.filterchain.FilterPlacementTests
```

Kết quả mong đợi khi cấu hình đúng là **6 test PASS**. Bài học đưa ra mã và phép thử có thể chạy trong dự án Boot tương thích; câu “6 test PASS” là kỳ vọng kiểm chứng khi người học chạy lệnh, không phải khẳng định đã thực thi chương trình trong tài liệu.

Bảng giải thích kiểm thử:

| Request | Authentication | Chain được chọn | Custom filter? | Status dự kiến |
| --- | --- | --- | --- | --- |
| `GET /api/private/whoami` | Basic hợp lệ | API | **Có**, đánh dấu sau phân quyền | 200 |
| `GET /api/private/whoami` | Không có | API | **Không**, bị chặn trước | 401 |
| `GET /api/private/whoami` | Basic sai | API | **Không**, xác thực thất bại | 401 |
| `GET /api/public/ping` | Không có | API | **Không**, do `shouldNotFilter` | 200 |
| `GET /site/home` | Không có | Fallback | **Không**, filter không nằm trong chain | 200 |
| `GET /api/not-allowed` | Basic hợp lệ | API | **Không**, `denyAll` từ chối trước | 403 |

**Phân biệt cơ chế được kiểm thử:** test riêng tư không có đăng nhập chứng minh vị trí filter sau phân quyền; test public chứng minh lọc theo đường dẫn; test site chứng minh giới hạn phạm vi theo `SecurityFilterChain`; test đường dẫn lạ chứng minh `anyRequest().denyAll()` không bị custom filter mở quyền ngoài ý muốn.

Không nên chỉ test một request thành công rồi kết luận filter đã đặt đúng. Các lỗi nguy hiểm nhất thường xảy ra ở đường dẫn **không được chạy**.

## 8. Cách kiểm tra thứ tự filter trên ứng dụng thật

Bên cạnh test, Spring Security có thể in danh sách filter được cấu hình khi bật log DEBUG ở thời điểm khởi động. Ví dụ cấu hình chỉ dùng ở môi trường phát triển, `src/main/resources/application.yml`:

```yaml
logging:
  level:
    org.springframework.security.web.DefaultSecurityFilterChain: DEBUG
```

Đọc dòng log dạng “Will secure ... with [...]” để biết mỗi `SecurityFilterChain` có những filter nào. Cần xác nhận:

- `PrivateRequestMarkerFilter` chỉ nằm trong chain `/api/**`, không nằm trong chain fallback.
- Trong API chain, custom filter xuất hiện sau `AuthorizationFilter` theo ý định.
- Không có hai instance filter ngoài ý muốn từ Servlet container và Spring Security.
- Cơ chế xác thực và các bảo vệ HTTP được bật theo thiết kế.

Khi cần hiểu **request thực sự đi qua những filter nào**, có thể bật mức quan sát Spring Security phù hợp trên môi trường thử nghiệm và đối chiếu log request; đừng bật log quá chi tiết trên production khi chưa đánh giá nguy cơ lộ token, cookie, thông tin đăng nhập hoặc lưu lượng nhạy cảm.

Lưu ý: thứ tự xuất hiện trong danh sách khởi động mới chỉ chứng minh cấu hình filter, **không chứng minh** filter được chạy cho mọi URL hay mọi kiểu dispatch. Kết quả đầu cuối phải được xác nhận bằng test HTTP thực tế và hành vi endpoint.

## 9. Tránh đăng ký filter hai lần trong Spring Boot

Một bẫy phổ biến:

```java
@Component
public class MyFilter extends OncePerRequestFilter {
    // ...
}

// Ở SecurityConfig:
http.addFilterAfter(myFilter, AuthorizationFilter.class);
```

Một đối tượng triển khai `Filter` được đăng ký bằng `@Component` hoặc `@Bean` có thể tự động trở thành **Servlet filter của Spring Boot**. Nếu đồng thời thêm nó vào `HttpSecurity`, bạn đã đăng ký filter ở **hai hệ thống chuỗi lọc**. Tùy dispatcher và cơ chế đánh dấu của `OncePerRequestFilter`, hiện tượng có thể là chạy lặp, chạy sai vị trí hoặc hành vi khó nhận ra; đừng xem “tôi chỉ thấy log một lần” là bằng chứng chắc chắn không có đăng ký trùng.

Có hai phương án:

**Phương án A — đơn giản nhất nếu không cần dependency injection:** tạo instance trực tiếp khi xây dựng security chain, như `new PrivateRequestMarkerFilter()` trong ví dụ. Không gắn `@Component` hoặc khai báo bean cho instance đó.

**Phương án B — nếu filter cần tiêm dependency:** khai báo filter thành Spring bean nhưng chủ động tắt đăng ký tại Servlet container. Ví dụ sau **thay cách khai báo filter trong ví dụ**, không dùng đồng thời hai phương án:

```java
@Bean
PrivateRequestMarkerFilter privateRequestMarkerFilter() {
    return new PrivateRequestMarkerFilter();
}

@Bean
FilterRegistrationBean<PrivateRequestMarkerFilter> disableServletFilter(
        PrivateRequestMarkerFilter filter
) {
    FilterRegistrationBean<PrivateRequestMarkerFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

Tương ứng thêm import:

```java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
```

Và trong `SecurityFilterChain`, tiêm filter bean vào tham số phương thức cấu hình rồi dùng:

```java
.addFilterAfter(filter, AuthorizationFilter.class)
```

`FilterRegistrationBean#setEnabled(false)` ngăn Boot đăng ký bean thành Servlet filter độc lập; `HttpSecurity` vẫn thêm cùng instance vào security chain. Đây là cách áp dụng khi cần injection và đã kiểm tra không có đăng ký trùng bằng cấu hình/log/test.

**Không thêm filter bằng `@WebFilter`, Servlet `FilterRegistrationBean` và `HttpSecurity` đồng thời trừ khi có thiết kế minh bạch cho từng lớp đăng ký.**

## 10. Các trường hợp đặc biệt cần quyết định trước

### 10.1. Filter xử lý xác thực hoặc phân quyền

Ví dụ trong bài chỉ quan sát request sau phân quyền. Nếu custom filter **phải từ chối** request, không nên tùy tiện:

```java
if (!allowed) {
    throw new RuntimeException("blocked");
}
```

Một exception thường như vậy có thể trở thành lỗi 500, làm lộ thông tin hoặc bỏ qua hợp đồng phản hồi xác thực. Nếu là bài toán quyền truy cập, ưu tiên khai báo `AuthorizationManager` trong `authorizeHttpRequests` hoặc ở tầng method security. Nếu filter phải tạo `Authentication`, cần dùng các thành phần xác thực chuẩn và đặt trước bước phân quyền; kiểm tra tương tác với anonymous, security context persistence, exception entry point, Basic/Bearer và session.

Với filter có chủ đích ném `AccessDeniedException`, cần đặt ở đoạn chuỗi mà `ExceptionTranslationFilter` có thể bao phía ngoài nếu mong muốn 401/403 được xử lý theo cơ chế mặc định. Đừng mặc định mọi exception ở mọi vị trí đều được Spring Security chuyển đổi.

### 10.2. CORS preflight và các endpoint công khai

Preflight `OPTIONS` có thể không mang cookie/session. Một custom filter bắt buộc lấy `Authentication` đối với mọi `/api/**` dễ chặn nhầm preflight và khiến trình duyệt báo lỗi CORS. Hãy dùng cấu hình `cors(...)` tích hợp, xử lý CORS đúng vị trí và giới hạn custom filter theo endpoint/phương thức thực sự cần thiết. Không tạo “bypass all security” để sửa một request OPTIONS.

Đường dẫn `/login`, `/logout`, OAuth2 callback, webhook, actuator và error handler cần được xem xét riêng. Nếu chọn `securityMatcher` quá hẹp, endpoint do chính một filter bảo mật tạo ra có thể nằm ngoài chain đó và không còn hoạt động như bạn tưởng; quy tắc URL cho login/logout phải đồng bộ với phạm vi chain.

### 10.3. Servlet dispatch: REQUEST, ASYNC, ERROR, FORWARD

`OncePerRequestFilter` có các hook để quyết định chạy ở dispatch async/error. Mặc định thường bỏ qua một số dispatch; không được hứa rằng filter chạy tuyệt đối đúng một lần trong mọi tình huống. Nếu cần bảo vệ hoặc quan sát xử lý bất đồng bộ, phải kiểm thử khi request chuyển thread, error dispatch, forward hoặc response đã bắt đầu gửi.

`SecurityContextHolder` thường sử dụng ngữ cảnh gắn với thread trong Servlet. Khi thay thread, dữ liệu xác thực hoặc MDC không nhất thiết tự truyền sang công việc async; dùng công cụ truyền ngữ cảnh phù hợp thay vì giữ `Authentication` trong biến static hay ThreadLocal không dọn.

### 10.4. Đọc body, thay request hoặc response

Đọc hết `request.getInputStream()` trong filter có thể làm controller không còn đọc được body. Muốn quan sát payload cần thiết kế wrapper và giới hạn kích thước, giải quyết dữ liệu nhạy cảm/streaming. Không log raw `Authorization`, `Cookie`, password, session ID hoặc token. Việc thay response body và status trong filter phải chú ý response đã commit hay chưa.

### 10.5. Nhiều SecurityFilterChain và điều kiện ưu tiên

Nếu có chain `/api/admin/**` với `@Order(1)` và chain `/api/**` với `@Order(2)`, request admin sẽ vào **chain thứ nhất**, không chạy tiếp chain thứ hai. Filter chỉ có ở chain API rộng **không tự áp dụng** cho chain admin đã khớp trước. Vì vậy, mỗi chain cần kiểm toán độc lập: matcher, filter, quyền mặc định, endpoint login và fallback.

Không có chain fallback bao tất cả có thể khiến các URL không khớp **bỏ qua Spring Security**. Mặc dù điều này có thể là lựa chọn có chủ đích trong một vài hạ tầng, ứng dụng bình thường nên có chain cuối bao phủ toàn bộ với chính sách rõ ràng.

## 11. Quy trình thiết kế và bộ kiểm thử chấp nhận

Trước khi thêm một filter vào ứng dụng:

1. **Mô tả yêu cầu.** Filter phải giải quyết sự kiện gì? Dữ liệu nào nó cần? Vì sao CORS/CSRF/authentication/authorization DSL, interceptor hoặc service hiện có chưa đáp ứng?
2. **Chọn vị trí có căn cứ.** Xác định các mốc đã hoàn thành trước khi filter chạy: context, CSRF, authentication, authorization. Chọn `addFilterBefore` hoặc `addFilterAfter` theo một filter cụ thể.
3. **Xác định phạm vi.** Viết rõ tập URL/method/dispatcher được phép chạy; chọn `securityMatcher`, `requestMatchers` và `shouldNotFilter` đúng vai trò, không suy diễn thay thế.
4. **Chỉ đăng ký một lần.** Xem filter là bean hay instance tại chỗ; kiểm tra Spring Boot auto-registration và container filter.
5. **Giữ đường đi của request.** Gọi `chain.doFilter` đúng lúc; nếu từ chối, trả status và xử lý exception phù hợp. Tránh chặn ngầm hoặc nuốt exception bảo mật.
6. **Kiểm thử hai chiều.** Có trường hợp filter phải chạy, không được chạy, chưa xác thực, thiếu quyền, CORS preflight, đường dẫn ngoài chain và error/async nếu có liên quan.
7. **Kiểm tra vận hành.** Xem filter list ở DEBUG và request trace trong môi trường thử nghiệm; đo độ trễ, log nhạy cảm và rủi ro khi tiến hành triển khai.

Ma trận nghiệm thu mẫu:

| Loại phép thử | Kết quả cần có |
| --- | --- |
| Đường dẫn được bảo vệ, tài khoản hợp lệ | Filter chạy đúng thứ tự, có dữ liệu `SecurityContext` mong đợi. |
| Đường dẫn đó không đăng nhập hoặc sai credentials | 401 theo cơ chế xác thực; filter sau phân quyền không được chạy. |
| Đường dẫn đó đã đăng nhập nhưng thiếu quyền | 403; filter sau `AuthorizationFilter` không chạy. |
| Public URL trong cùng chain | Đúng chính sách; custom filter được bỏ qua theo `shouldNotFilter`. |
| URL ngoài chain | Custom filter không nằm trong chain được chọn. |
| Endpoint không có rule cấp quyền | `denyAll` hoặc chính sách fallback đã định; không bất ngờ trở thành public. |
| CORS preflight, login, logout, callback | Không bị custom filter chặn sai luồng; policy cụ thể được kiểm thử. |
| Async/error dispatch nếu có hỗ trợ | Không lọt hoặc lặp logic ngoài mong đợi; ngữ cảnh được xử lý đúng. |
| Cấu hình khởi động | Một đăng ký ở hệ thống mong muốn, đúng vị trí, không có Servlet filter trùng. |
| Tích hợp, hiệu năng và log | Không đọc mất body, rò token, tăng độ trễ quá mức hoặc làm hỏng response. |

## 12. Những sai lầm thường gặp

- **“Cứ thêm trước `UsernamePasswordAuthenticationFilter`.”** Mốc này không phù hợp với mọi loại filter và mọi kiểu xác thực. Hãy chọn theo sự kiện cần xảy ra trước/sau.
- **Nhầm `securityMatcher` với `requestMatchers`.** Một cái chọn chain; một cái chọn rule phân quyền trong chain. Không tự giới hạn custom filter.
- **Tin rằng `permitAll()` tắt mọi filter.** Nó chỉ cho phép request theo rule; CSRF, headers và custom filter vẫn có thể chạy.
- **Thêm cùng một filter thành bean và vào `HttpSecurity` mà không kiểm tra Boot auto-registration.** Dễ chạy trùng hoặc sai vị trí.
- **Dựa vào `OncePerRequestFilter` để kết luận không thể chạy hai lần trong mọi dispatcher.** Phải hiểu dispatch và thử nghiệm thực tế.
- **Đặt filter cần user identity trước các bước xác thực.** Dữ liệu principal có thể rỗng/anonymous/không đúng nguồn tin cậy.
- **Ném exception bảo mật ngoài phạm vi `ExceptionTranslationFilter` rồi đợi tự chuyển thành 401/403.** Kết quả có thể khác mong đợi.
- **Đặt filter sau phân quyền rồi muốn nó ghi nhận mọi 401/403.** Các request bị chặn sớm sẽ không tới nó; cần thiết kế điểm quan sát khác.
- **Dùng custom filter thay authorization rule có sẵn.** Quyền khó kiểm toán, dễ mâu thuẫn với `@PreAuthorize` hoặc rule HTTP.
- **Thiếu fallback chain.** Một số URL có thể không được bảo vệ.
- **Chỉ test happy path.** Không thấy filter chạy sai trên public URL, callback, preflight hoặc chain khác.
- **Đọc body/log secret trong filter.** Dễ phá controller hoặc làm lộ dữ liệu bảo mật.

**Kết luận thực hành:** một custom filter chỉ “đúng” khi bạn chứng minh được **vì sao cần nó**, **nó chạy sau/trước mốc nào**, **nó chạy trên request nào và bỏ qua request nào**, và **không tạo đường đi tắt qua cơ chế bảo mật khác**. Thứ tự và phạm vi phải được kiểm thử như một phần của chính chức năng filter.

## Tài liệu tham khảo

- Spring Security 6.5 — [Servlet Architecture, SecurityFilterChain và thêm filter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html).
- Spring Security 6.5 — [Java Configuration, nhiều SecurityFilterChain và securityMatcher](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html).
- Spring Security 6.5 — [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html).
- Spring Framework — [OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html).
- Spring Boot — [Servlet Filters và FilterRegistrationBean](https://docs.spring.io/spring-boot/reference/web/servlet.html).