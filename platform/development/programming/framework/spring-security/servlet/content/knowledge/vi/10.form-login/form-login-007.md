# defaultSuccessUrl, successHandler và lựa chọn đích chuyển hướng

Trong **Spring Security cho Servlet**, khi người dùng gửi biểu mẫu đăng nhập (form login) và xác thực thành công, hệ thống phải quyết định **đi đâu tiếp theo**. Một ứng dụng thường muốn đưa người dùng về trang họ vừa cố mở; ứng dụng khác muốn luôn mở dashboard, hoặc muốn chuyển admin sang một trang riêng. Spring Security cho phép thực hiện các chính sách này thông qua `defaultSuccessUrl(...)` và `AuthenticationSuccessHandler` cấu hình ở `formLogin(...)`.

Điểm dễ nhầm nhất là chữ **default**: `defaultSuccessUrl("/dashboard")` **không mặc định bảo đảm mọi login đều tới /dashboard**. Nếu `RequestCache` đã lưu một request cần xác thực từ trước, handler mặc định cho form login thường ưu tiên quay lại URL đó. Muốn ép luôn tới một đường dẫn, dùng tham số `alwaysUse` hoặc tự thiết kế một success handler phù hợp.

Bài học giải thích luồng filter, thứ tự chọn URL, hai overload của `defaultSuccessUrl`, quan hệ `SavedRequestAwareAuthenticationSuccessHandler`–`RequestCache`, cách viết `successHandler` cho quy tắc riêng, khác biệt redirect và forward, lưu ý chống open redirect và cách kiểm thử bằng `MockMvc`. Các ví dụ framework hướng đến **Java 17+, Spring Boot 3.x và Spring Security 6.x (Servlet)**; chi tiết API/behavior có thể khác khi framework được cấu hình tùy biến.

## 1. “Đăng nhập thành công” xảy ra ở đâu?

Một form login điển hình:

~~~text
GET /orders/42 (chưa đăng nhập)
  |
  v
SecurityFilterChain -> AuthorizationFilter
  | yêu cầu Authentication hợp lệ
  v
ExceptionTranslationFilter
  | chuyển sang AuthenticationEntryPoint
  | RequestCache có thể lưu GET /orders/42
  v
302 -> GET /login (trang đăng nhập)

Người dùng nhập tài khoản và mật khẩu
  |
  v
POST /login + CSRF token
  |
  v
UsernamePasswordAuthenticationFilter
  |
  v
AuthenticationManager / AuthenticationProvider
  | xác minh thành công
  v
SecurityContext được cập nhật/lưu theo cơ chế cấu hình
  |
  v
AuthenticationSuccessHandler.onAuthenticationSuccess(...)
  |
  +-- dùng URL đã lưu?    -> redirect /orders/42
  +-- dùng URL mặc định?  -> redirect /dashboard
  +-- chính sách riêng?   -> redirect /admin/home ...
~~~

`UsernamePasswordAuthenticationFilter` xử lý request đăng nhập ở URL mà filter được cấu hình, thường là `POST /login`. Sau khi authentication thành công, nó ủy quyền bước phản hồi thành công cho `AuthenticationSuccessHandler`. Việc chọn đích **khác với** việc kiểm tra username/password: xác thực phải thành công trước khi handler thành công chạy.

Với form login mặc định, Spring Security thường sử dụng `SavedRequestAwareAuthenticationSuccessHandler`. Nó dựa vào request đã lưu (nếu có) hoặc một **default target URL** để tạo redirect. Response thường là HTTP 302 cùng header `Location`. Đây là lần điều hướng mới của trình duyệt, không phải server tự gọi controller đích trong cùng request.

### Phân biệt bốn điểm cấu hình

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| `loginPage("/login")` | URL **hiển thị** trang nhập thông tin | GET /login |
| `loginProcessingUrl("/login")` | URL được authentication filter **xử lý POST login** | POST /login |
| `defaultSuccessUrl("/dashboard")` | URL mặc định **sau xác thực thành công** | /dashboard |
| `failureUrl("/login?error")` | URL khi **xác thực thất bại** | /login?error |

Các URL này có vai trò khác nhau dù trong cấu hình mặc định GET và POST có thể cùng đường dẫn `/login`. `defaultSuccessUrl` không xử lý xác thực sai, logout hay lần truy cập tài nguyên không yêu cầu đăng nhập.

## 2. defaultSuccessUrl(String): “mặc định” đúng nghĩa

Cách cấu hình phổ biến với lambda DSL:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/about").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .defaultSuccessUrl("/dashboard"));

    return http.build();
}
~~~

Đây là **đoạn trong cấu hình Spring Security**; cần `@Bean`, imports `HttpSecurity` và `SecurityFilterChain` cùng project có Spring Security. Trong trường hợp trang đăng nhập mặc định, không cần tự tạo HTML form; Spring Security có thể cung cấp trang GET /login cho form login được kích hoạt.

Khi cấu hình:

~~~java
.formLogin(form -> form.defaultSuccessUrl("/dashboard"))
~~~

đường dẫn `/dashboard` là **fallback target**:

- Người dùng mở trang login trực tiếp rồi đăng nhập; không có request trước đó được lưu → thường tới `/dashboard`.
- Người dùng cố mở tài nguyên bảo vệ `/orders/42`, sau đó được yêu cầu login; request trước đã lưu → thường quay lại `/orders/42`, **không** tới `/dashboard`.
- Nếu request cache bị tắt, không có saved request hoặc saved request không còn hợp lệ → dùng target mặc định.
- Nếu ứng dụng thay thế success handler bằng một implementation khác, quy tắc trên có thể không còn áp dụng.

Vì vậy tên phương thức nên được đọc là **“đặt URL mặc định khi không có yêu cầu điều hướng ưu tiên khác”**, thay vì “luôn chuyển hướng đến URL này”.

### defaultSuccessUrl(String, boolean)

Overload thứ hai cho phép thay đổi chính sách:

~~~java
.formLogin(form -> form.defaultSuccessUrl("/dashboard", true))
~~~

Tham số thứ hai là `alwaysUse`. Khi `true`, cấu hình success handler sử dụng default target dù trước đó đã có saved request. Khi `false` (hành vi của overload một tham số), saved request có thể được ưu tiên. Với handler chuẩn, việc ép default cũng đi kèm xử lý loại bỏ saved request không còn cần thiết.

Bảng:

| Cấu hình | Có request đã lưu GET /orders/42 | Không có request đã lưu |
| --- | --- | --- |
| `defaultSuccessUrl("/dashboard")` | Thường chuyển về /orders/42 | Chuyển về /dashboard |
| `defaultSuccessUrl("/dashboard", false)` | Thường chuyển về /orders/42 | Chuyển về /dashboard |
| `defaultSuccessUrl("/dashboard", true)` | Chuyển về /dashboard, bỏ ưu tiên saved request | Chuyển về /dashboard |
| `successHandler(custom)` | Theo logic của custom handler | Theo logic của custom handler |

Các kết quả trong bảng giả định người dùng login **thành công**, handler và `RequestCache` mặc định được sử dụng nếu không nêu khác. Request cache có thể có cấu hình riêng, session hết hạn hoặc nhiều security chain.

### Khi nào nên đặt alwaysUse=true?

Phù hợp khi sản phẩm chủ động thiết kế điểm vào cố định: dashboard, trang chọn tổ chức, trang onboarding bắt buộc hoặc màn hình xác nhận chính sách. Tuy nhiên, bỏ qua URL ban đầu có thể gây khó chịu khi người dùng bấm liên kết sâu đến một tài nguyên rồi phải tự tìm lại sau login.

Không nên dùng `alwaysUse=true` như giải pháp che lỗi request cache, lỗi phân quyền hoặc lỗi route. Nếu người dùng liên tục bị đưa về login, hãy kiểm tra authentication/session/authorization thay vì ép chuyển hướng.

## 3. SavedRequestAwareAuthenticationSuccessHandler chọn URL như thế nào?

Handler mặc định mang tên `SavedRequestAwareAuthenticationSuccessHandler` vì nó nhận biết `SavedRequest`. Quy tắc lý tưởng để học:

~~~text
Đăng nhập thành công
       |
       v
Có SavedRequest trong RequestCache?
       |
       +---- không ----> target mặc định (thường / hoặc defaultSuccessUrl đã đặt)
       |
       +---- có
               |
               v
    alwaysUseDefaultTargetUrl = true
       |                 |
       +---- yes -------> target mặc định, loại saved request phù hợp
       |
       +---- no --------> redirect URL của SavedRequest
~~~

Đây là phiên bản đơn giản hóa: `SavedRequestAwareAuthenticationSuccessHandler` còn hỗ trợ các cấu hình kế thừa từ `AbstractAuthenticationTargetUrlRequestHandler`, ví dụ `targetUrlParameter`. Nếu ứng dụng dùng tham số mục tiêu, thứ tự ưu tiên còn tùy cấu hình. Không dựa vào sơ đồ để tự cho phép URL do client gửi mà không kiểm soát.

### RequestCache lưu gì?

Một `RequestCache` có thể lưu thông tin request trước khi Spring Security yêu cầu người dùng đi xác thực. Trong cấu hình stateful thường gặp, `HttpSessionRequestCache` sử dụng session để giữ một `DefaultSavedRequest`. Dữ liệu có thể bao gồm URL, method, parameters/headers thích hợp cho mục tiêu quay lại request được bảo vệ.

Ví dụ:

~~~text
GET http://localhost:8080/orders/42
    |
    | chưa login
    v
RequestCache.saveRequest(...)
    |
    v
GET /login
    |
    v
POST /login thành công
    |
    v
SavedRequestAwareAuthenticationSuccessHandler
    |
    v
302 Location: http://localhost:8080/orders/42
    |
    v
Trình duyệt gửi GET /orders/42 với trạng thái login mới
~~~

URL trong đoạn trên là ví dụ, còn scheme, host, port, context path thực tế do request và triển khai quyết định. Handler **không bảo đảm tự chạy lại toàn bộ HTTP POST/PUT cũ**: browser redirect tạo request mới theo ngữ nghĩa HTTP, không phải bản sao nguyên vẹn body ban đầu. Đừng xây nghiệp vụ yêu cầu replay tác vụ ghi dữ liệu nhạy cảm sau login một cách ngầm định.

### Ai lưu request, ai sử dụng?

Có ba vai trò cần tách:

1. `ExceptionTranslationFilter` có thể yêu cầu `RequestCache.saveRequest(...)` trước khi khởi động authentication khi gặp trường hợp cần xác thực.
2. `SavedRequestAwareAuthenticationSuccessHandler` có thể lấy saved request để chọn URL sau login.
3. `RequestCacheAwareFilter` có thể hỗ trợ khôi phục thông tin request khi điều hướng khớp saved request trong luồng phù hợp.

Sự tồn tại của `RequestCache` không có nghĩa tất cả request đều được lưu. Chính sách lưu request, matcher, phương thức HTTP, trạng thái session, lỗi xác thực và security chain đều ảnh hưởng.

### Vì sao mở tab login trực tiếp lại đi tới dashboard?

Khi người dùng tự truy cập `GET /login`, thông thường không có tài nguyên bảo vệ trước đó để lưu. Handler không tìm thấy saved request thích hợp và dùng default target. Đây là hành vi mong đợi chứ không phải lỗi.

### Vì sao cùng một người đôi lúc về trang khác nhau?

Một session có thể chứa saved request từ lần điều hướng trước. Nếu người dùng mở nhiều tab yêu cầu các trang bảo vệ, saved request lưu trong session có thể bị cập nhật, gây kết quả không trực giác. Session cũng có thể hết hạn hoặc request cache bị custom. Hãy test luồng **từ URL ban đầu tới login**, không chỉ test riêng `POST /login`.

## 4. Viết cấu hình Spring Boot đầy đủ để thử nghiệm

Ví dụ dưới đây dùng Spring Boot 3.x, Spring Security 6.x, Java 17+, một tài khoản in-memory và trang login **mặc định của Spring Security**. Đây là bản demo cho đường đi sau login, không phải hệ thống quản lý tài khoản production.

### 4.1. Maven dependencies

Trong project Spring Boot đã có parent/BOM và plugin khởi chạy, cần các dependency:

~~~xml
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
~~~

Dùng BOM Spring Boot tương thích, không tự pha trộn phiên bản Spring Security khác. Với các bản Spring Boot mới, package hỗ trợ test có thể thay đổi; kiểm tra dependency và imports theo version dự án.

### 4.2. Main class

Tạo `src/main/java/com/example/login/LoginRedirectApplication.java`:

~~~java
package com.example.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginRedirectApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginRedirectApplication.class, args);
    }
}
~~~

### 4.3. SecurityFilterChain

Tạo `src/main/java/com/example/login/LoginRedirectConfig.java`:

~~~java
package com.example.login;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginRedirectConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-admin-password"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/about").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/dashboard")
                .permitAll());

        return http.build();
    }
}
~~~

`formLogin(...).permitAll()` cho phép các URL cần thiết cho form login theo cấu hình, không có nghĩa mọi URL ứng dụng đều công khai. Password demo **chỉ phục vụ thử nghiệm cục bộ**; ứng dụng thật phải dùng kho user phù hợp, policy password, encoder và quy trình quản lý secret an toàn.

Nếu thay `defaultSuccessUrl("/dashboard")` thành `defaultSuccessUrl("/dashboard", true)`, test saved request ở phần sau phải đổi kỳ vọng sang dashboard.

### 4.4. Các endpoint để kiểm tra

Tạo `src/main/java/com/example/login/PagesController.java`:

~~~java
package com.example.login;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/")
    public String home() {
        return "public home";
    }

    @GetMapping("/about")
    public String about() {
        return "about";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }

    @GetMapping("/orders/{id}")
    public String order(@PathVariable long id) {
        return "order " + id;
    }

    @GetMapping("/admin/home")
    public String adminHome() {
        return "admin home";
    }
}
~~~

Ở đây controller chỉ trả text để minh họa URL. Với ứng dụng MVC thực tế, bạn có thể trả template Thymeleaf/JSP hoặc view cần thiết. Khi chọn URL thành công, **đích vẫn phải đi qua authorization** ở request tiếp theo; redirect không cấp thêm quyền.

### 4.5. Chạy và quan sát

Sau khi chuẩn bị Maven wrapper tương thích:

~~~bash
./mvnw spring-boot:run
~~~

Thử mở `http://localhost:8080/login` trên browser và đăng nhập Alice bằng password demo. Nếu vào login trực tiếp, bạn thường được chuyển tới `/dashboard`. Sau đó xóa session/cookie hoặc dùng cửa sổ riêng tư và thử truy cập `http://localhost:8080/orders/42` trước khi login; sau khi đăng nhập thành công, bạn thường quay lại `/orders/42` thay vì dashboard.

**Lưu ý khi dùng curl:** gửi POST form mặc định cần CSRF token và cookie session thích hợp. Một lệnh `curl -d username=...` thuần thường bị chặn 403 nếu thiếu CSRF token; đó không phải bằng chứng `defaultSuccessUrl` hoạt động sai. Dùng trình duyệt, hoặc integration test MockMvc có `csrf()` như phần 8.

## 5. successHandler là gì và khi nào cần dùng?

`AuthenticationSuccessHandler` là interface Spring Security dùng để xử lý một lần authentication thành công trong web flow:

~~~java
// Chữ ký rút gọn của interface Spring Security:
void onAuthenticationSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication)
        throws IOException, ServletException;
~~~

Chữ ký này là **trích dạng minh họa**, không phải class độc lập. `request` và `response` thuộc Jakarta Servlet trong Spring Security 6.x. `authentication` là kết quả authentication hợp lệ do provider trả về.

Một implementation có thể:

- Chọn URL đích theo role/authority hoặc trạng thái onboarding.
- Duy trì ưu tiên saved request hoặc cố ý bỏ saved request.
- Phát hành response JSON thích hợp nếu có yêu cầu riêng (dù form login browser thường dùng redirect).
- Ghi audit event an toàn và tránh làm lộ credential.
- Gửi redirect thông qua `RedirectStrategy`.

**Quan hệ với defaultSuccessUrl:** Khi bạn cài một custom `successHandler(...)`, chính handler ấy là nơi quyết định phản hồi thành công. Đừng mặc định `defaultSuccessUrl(...)` được áp dụng thêm sau khi handler custom đã hoàn tất. Nếu muốn kết hợp “quay lại URL cũ nếu có, ngược lại chọn đích theo role”, phải viết/chọn handler thực sự triển khai thứ tự đó.

### Nên dùng defaultSuccessUrl khi nào?

Ưu tiên `defaultSuccessUrl` khi chỉ cần một URL mặc định với hai khả năng “ưu tiên saved request” hoặc “luôn tới trang đã chọn”. Cách này ít mã hơn, tận dụng xử lý session, cache và redirect của framework.

### Nên dùng successHandler khi nào?

Dùng handler tùy biến khi có chính sách xác thực thành công **không biểu đạt được bằng một URL mặc định**, ví dụ phân loại quyền, chọn vùng làm việc, phân nhánh onboarding, phát response theo hợp đồng frontend, hay quyết định đích dựa trên dữ liệu nghiệp vụ đáng tin cậy. Handler nên ngắn, rõ chính sách và được kiểm thử từng nhánh.

## 6. Ví dụ handler chọn đích theo quyền

Giả sử ứng dụng muốn:

- Người dùng có authority `ROLE_ADMIN` → `/admin/home`.
- Người dùng khác đã login → `/dashboard`.
- Không ưu tiên saved request trong chính sách này (đích sau login luôn theo quyền).

Đây là **quy tắc khác** với `defaultSuccessUrl("/dashboard")`. Vì nó bỏ qua saved request, handler nên xóa saved request khỏi cache để URL cũ không còn gây hiệu ứng ở những bước tiếp theo.

### 6.1. Custom handler

Tạo `src/main/java/com/example/login/RoleBasedSuccessHandler.java`:

~~~java
package com.example.login;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.WebAttributes;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;
import org.springframework.security.web.DefaultRedirectStrategy;
import org.springframework.security.web.RedirectStrategy;

public final class RoleBasedSuccessHandler implements AuthenticationSuccessHandler {
    private final RequestCache requestCache;
    private final RedirectStrategy redirectStrategy = new DefaultRedirectStrategy();

    public RoleBasedSuccessHandler(RequestCache requestCache) {
        this.requestCache = requestCache;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        // Chính sách này KHÔNG quay lại URL đã lưu.
        requestCache.removeRequest(request, response);

        // Xóa thông tin exception do lần login thất bại trước đó nếu có.
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.removeAttribute(WebAttributes.AUTHENTICATION_EXCEPTION);
        }

        boolean admin = authentication.getAuthorities().stream()
            .anyMatch(grant -> "ROLE_ADMIN".equals(grant.getAuthority()));

        String target = admin ? "/admin/home" : "/dashboard";
        redirectStrategy.sendRedirect(request, response, target);
    }
}
~~~

Đây là class thuộc Spring Security Servlet có dependency tương ứng; `DefaultRedirectStrategy` xử lý chuyển hướng HTTP. Cách dùng `RequestCache.removeRequest(...)` thống nhất với mục tiêu **bỏ saved request**; trong ứng dụng dùng request cache tùy biến, cần truyền **cùng instance** được cấu hình cho security chain.

Điều handler **không** làm: tự xác thực mật khẩu, cấp `ROLE_ADMIN`, cho phép truy cập trái với `AuthorizationFilter` hoặc lấy đích redirect từ query parameter do người dùng tùy ý sửa.

### 6.2. Kết nối vào SecurityFilterChain

Trong class cấu hình, thêm các bean sau:

~~~java
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Bean
RequestCache requestCache() {
    return new HttpSessionRequestCache();
}

@Bean
AuthenticationSuccessHandler loginSuccessHandler(RequestCache requestCache) {
    return new RoleBasedSuccessHandler(requestCache);
}
~~~

Sau đó **thay phương thức** tạo security chain ở ví dụ mục 4, không đăng ký trùng bean:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        AuthenticationSuccessHandler loginSuccessHandler,
        RequestCache requestCache) throws Exception {

    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/about").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .requestCache(cache -> cache.requestCache(requestCache))
        .formLogin(form -> form
            .successHandler(loginSuccessHandler)
            .permitAll());

    return http.build();
}
~~~

Các import cho `HttpSecurity` và `SecurityFilterChain` giống phần 4. Đoạn code này chọn **handler tùy biến thay cho defaultSuccessUrl**; không đặt cả hai rồi suy diễn rằng Spring Security sẽ tự ghép kết quả.

Giả sử user Alice có `ROLE_USER`, admin có `ROLE_ADMIN`, kỳ vọng:

| Người login | Có saved request trước login? | URL đích theo handler |
| --- | --- | --- |
| alice | Không | /dashboard |
| alice | Có /orders/42 | /dashboard (bỏ saved request) |
| admin | Không | /admin/home |
| admin | Có /orders/42 | /admin/home (bỏ saved request) |

Sự lựa chọn URL ở đây chỉ là chính sách navigation. Một request sau redirect tới `/admin/home` vẫn được kiểm tra `hasRole("ADMIN")`; không nên coi redirect là tầng authorization.

## 7. Chính sách kết hợp: ưu tiên saved request hay phân nhánh theo vai trò?

Có ít nhất ba cách thiết kế hợp lệ:

### Chính sách A: ưu tiên hành trình ban đầu

Nếu mục tiêu là “đến trang người dùng muốn mở”, sử dụng `SavedRequestAwareAuthenticationSuccessHandler` và `defaultSuccessUrl("/dashboard")`. Role vẫn kiểm tra ở trang đích; người không có quyền sẽ nhận `403` hoặc luồng xử lý denial tương ứng. Đây là cách đơn giản nhất cho ứng dụng server-rendered có deep links.

### Chính sách B: luôn vào một trang phù hợp role

Dùng `RoleBasedSuccessHandler` như mục 6. Handler bỏ saved request, chọn từ **danh sách đường dẫn cố định**, tránh nhầm URL do client cung cấp với authorization. Phù hợp cho portal có hai khu vực tách biệt hoặc onboarding.

### Chính sách C: saved request trước, không có thì chọn role

Đây là quy tắc tùy biến cần được thực thi rõ ràng:

~~~text
Authentication thành công
         |
         v
SavedRequest hợp lệ, được phép ưu tiên?
         |
     +---+---+
    Có      Không
     |         |
     v         v
Redirect    Kiểm tra authority / trạng thái account
URL đã lưu       |
                 +-- admin -> /admin/home
                 +-- others -> /dashboard
~~~

Trong thực tế, để triển khai chính sách C, có thể xây một handler dựa trên các cơ chế của `SavedRequestAwareAuthenticationSuccessHandler` cùng một `RequestCache` được quản lý, hoặc tự xây thuật toán lựa chọn + cleanup với test đầy đủ. **Không thay `defaultTargetUrl` của một singleton success handler qua từng request** để chọn URL theo user: handler bean được nhiều thread gọi đồng thời, cập nhật trường cấu hình chung có thể khiến Alice nhận target của Bob.

Nếu cho saved request ưu tiên, cần làm rõ trường hợp user có login nhưng **không có quyền vào URL đã lưu**: redirect vẫn có thể tới URL đó, sau đó authorization từ chối 403. Đây thường là hành vi đúng; không bắt buộc handler phải tra trước quyền của mọi endpoint. Nếu UI muốn tránh redirect tới trang bị từ chối, cần chính sách truy cập/đích tinh tế hơn và kiểm thử đủ mọi route.

## 8. Kiểm thử bằng Spring Security Test và MockMvc

Test `defaultSuccessUrl` phải kiểm tra **hai đường đi khác nhau**:

1. Đăng nhập trực tiếp, **không có saved request**.
2. Chạm vào trang bảo vệ trước, sinh saved request, rồi đăng nhập bằng **cùng HTTP session**.

Nếu test chỉ gọi POST /login trực tiếp, không thể chứng minh handler biết khôi phục request đã lưu. Với HTTP form, đừng quên CSRF token.

### 8.1. Test integration cho defaultSuccessUrl

Cần `spring-boot-starter-test` và `spring-security-test` như mục 4. Tạo `src/test/java/com/example/login/LoginRedirectTest.java`:

~~~java
package com.example.login;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginRedirectTest {

    @Autowired MockMvc mvc;

    @Test
    void directLoginGoesToDefaultPage() throws Exception {
        MvcResult loggedIn = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = loggedIn.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.endsWith("/dashboard"), location);
    }

    @Test
    void savedRequestWinsWhenAlwaysUseIsFalse() throws Exception {
        MvcResult beforeLogin = mvc.perform(get("/orders/42"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) beforeLogin.getRequest().getSession(false);
        assertNotNull(session);

        MvcResult loggedIn = mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = loggedIn.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.endsWith("/orders/42"), location);
    }
}
~~~

Các assertion sử dụng `endsWith` để không gắn test vào một dạng tuyệt đối/tương đối duy nhất của redirect URL khi mock server thay scheme/host. **Test này yêu cầu chính cấu hình `defaultSuccessUrl("/dashboard")` của phần 4**. Nếu thay bằng `alwaysUse=true` hoặc `successHandler` theo role, test thứ hai cần sửa theo chính sách mới; không nên coi khác biệt đó là framework bug.

Trong phần test, `csrf()` cung cấp CSRF token phù hợp để filter chấp nhận POST login. Khi chạy trên trình duyệt thật, form login được sinh bởi Spring Security mặc định có cơ chế đưa token vào form; nếu tự viết trang login, bạn phải đảm bảo CSRF token được gửi đúng cách khi CSRF bật.

### 8.2. Kiểm thử alwaysUseDefaultTargetUrl

Thay cấu hình:

~~~java
.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", true)
    .permitAll());
~~~

Khi thực hiện đúng kịch bản saved request ở test thứ hai, kỳ vọng redirect về `/dashboard`, dù người dùng trước đó đã yêu cầu `/orders/42`. Việc kiểm thử cần xác nhận saved request không còn gây điều hướng ngầm ở lần sau.

### 8.3. Kiểm thử custom successHandler

Với custom handler phần 6, test riêng hai tài khoản:

- Alice đăng nhập → redirect kết thúc bằng `/dashboard`.
- Admin đăng nhập → redirect kết thúc bằng `/admin/home`.
- Thực hiện một request bảo vệ trước login → handler vẫn ưu tiên role, không phục hồi saved request.
- Sau redirect, truy cập endpoint admin bằng Alice → vẫn bị từ chối; handler không thay đổi authorities.

Có thể kiểm tra URL redirect bằng `getRedirectedUrl()` và actual authorization bằng HTTP request tiếp theo mang session. Đây là hai assertion khác nhau.

### Vì sao không dùng @WithMockUser để test POST /login?

`@WithMockUser` tạo sẵn authentication cho test, hữu ích khi test authorization nhưng **không chứng minh UsernamePasswordAuthenticationFilter đã xử lý credentials và gọi success handler như mong đợi**. Khi test form login, gửi username/password qua POST và giữ session/CSRF đúng luồng để bao phủ cấu hình thật.

## 9. Chương trình Java 17 độc lập mô phỏng thứ tự chọn URL

Để kiểm tra logic mà không cần Spring framework, đoạn mã dưới đây mô phỏng hai chính sách: handler mặc định có saved request và handler luôn chọn đích theo role. Đây là **mô hình thuật toán** — nó không triển khai filter, redirect HTTP hoặc RequestCache thật.

Lưu file `SuccessTargetDecisionDemo.java`:

~~~java
public class SuccessTargetDecisionDemo {

    static String savedAware(String savedUrl, boolean alwaysDefault) {
        if (alwaysDefault || savedUrl == null) {
            return "/dashboard";
        }
        return savedUrl;
    }

    static String roleBased(boolean hasAdminRole) {
        return hasAdminRole ? "/admin/home" : "/dashboard";
    }

    public static void main(String[] args) {
        System.out.println("direct -> " + savedAware(null, false));
        System.out.println("saved -> "
                + savedAware("/orders/42", false));
        System.out.println("always -> "
                + savedAware("/orders/42", true));
        System.out.println("admin -> " + roleBased(true));
        System.out.println("user -> " + roleBased(false));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac SuccessTargetDecisionDemo.java
java SuccessTargetDecisionDemo
~~~

Stdout chính xác:

~~~text
direct -> /dashboard
saved -> /orders/42
always -> /dashboard
admin -> /admin/home
user -> /dashboard
~~~

Ý nghĩa là **quy tắc chọn đích**, không phải khẳng định mọi redirect trong Spring Security có cùng trạng thái, scheme, context path hay cách tương tác với session.

## 10. Redirect, forward và xử lý response khác nhau thế nào?

Spring Security còn có API như `successForwardUrl(...)` cho một số kịch bản, khác bản chất với `defaultSuccessUrl(...)`:

| Tiêu chí | Redirect sau login | Server-side forward sau login |
| --- | --- | --- |
| HTTP | Trình duyệt nhận status 3xx/Location rồi gửi request mới | Servlet container chuyển tiếp xử lý nội bộ |
| URL hiển thị trên browser | Thường đổi thành URL đích | Thường vẫn là URL POST login |
| Phương thức / request | Request mới theo quy tắc HTTP redirect | Cùng request phía server; phương thức/parameters gốc có thể còn |
| Refresh trang | Thường refresh URL đích | Có thể lặp lại xử lý POST hoặc không phù hợp kỳ vọng |
| Phù hợp | Web app điều hướng thông thường | Trường hợp nội bộ đặc biệt được thiết kế cẩn thận |

Với trải nghiệm form login truyền thống, **redirect thường phù hợp hơn** để tránh refresh lại POST, tạo URL dễ bookmark và làm rõ vòng đời request. Không tự thay redirect bằng forward chỉ vì muốn giữ dữ liệu form. Khi thiết kế UI, dùng Post/Redirect/Get khi phù hợp và tránh lưu thông tin nhạy cảm vào query parameter.

`failureUrl(...)` hoặc `AuthenticationFailureHandler` là đường xử lý **login thất bại**, không liên quan `AuthenticationSuccessHandler`. Tương tự, `logoutSuccessUrl(...)` hoặc `LogoutSuccessHandler` xử lý sau logout, không sử dụng `defaultSuccessUrl` cho login.

## 11. An toàn chuyển hướng: tránh open redirect và lộ dữ liệu

Lựa chọn đích sau login có ý nghĩa bảo mật. Một sai lầm nguy hiểm là lấy trực tiếp URL từ client:

~~~java
// KHÔNG NÊN: target có thể là URL do attacker kiểm soát.
String target = request.getParameter("next");
response.sendRedirect(target);
~~~

Nếu `next` trỏ sang website của attacker, ứng dụng có thể bị dùng làm **open redirect**. Người dùng tưởng đang theo quy trình login hợp lệ nhưng sau xác thực bị đưa sang website giả mạo. Ngay cả khi một trình duyệt hiện đại không tự gửi cookie sang domain khác, chuyển hướng lừa đảo vẫn là vấn đề lớn.

### Cách thiết kế an toàn hơn

- Ưu tiên **đường dẫn cố định hoặc một danh sách allowlist** do server xác định, ví dụ `/dashboard`, `/reports`, `/profile`.
- Nếu UI cho chọn vùng, nhận một **mã lựa chọn** như `reports` hoặc `profile` rồi ánh xạ mã này sang path được kiểm soát.
- Không coi query parameter `next` là bằng chứng người dùng được truy cập URL đó; URL đích vẫn phải qua authorization.
- Nếu yêu cầu redirect động thật sự, dùng logic canonicalization/allowlist chặt chẽ cho scheme, host, port, context path, encoding và path; không tự phát minh một regex đơn giản rồi tuyên bố an toàn.
- Không đặt password, access token, session ID, thông tin nhận dạng nhạy cảm vào URL redirect; query string có thể xuất hiện trong browser history, log hoặc referrer.
- Đối với nhiều tenant, lấy tenant được phép từ nguồn đã xác thực; không để client tự khai báo tenant hay external domain để handler chuyển hướng qua một nơi chưa kiểm chứng.

Một ví dụ mapping mã lựa chọn an toàn theo danh sách đóng:

~~~java
String section = request.getParameter("section");

String destination = switch (section == null ? "" : section) {
    case "reports" -> "/reports";
    case "profile" -> "/profile";
    default -> "/dashboard";
};

redirectStrategy.sendRedirect(request, response, destination);
~~~

Đây là **đoạn minh họa trong AuthenticationSuccessHandler**, với `request`, `response` và `redirectStrategy` đã được tạo. Dù URL thuộc allowlist, endpoint `/reports` vẫn phải có security rule phù hợp. Handler không được tin vào vai trò do client gửi để bỏ qua rule.

### Redirect sau login và context path

Khi ứng dụng chạy dưới `server.servlet.context-path=/portal` hoặc phía sau reverse proxy, đường dẫn root-relative `/dashboard` và redirect URL tuyệt đối có thể được xử lý khác nhau. Cần kiểm tra cấu hình `RedirectStrategy`, proxy forwarded headers đáng tin, context path và test môi trường triển khai. Đừng hardcode host nội bộ hay protocol HTTP vào redirect của production.

Với `SavedRequest`, URL ban đầu có thể chứa host/port lấy từ HTTP request; cấu hình reverse proxy sai hoặc header forwarded không đáng tin có thể làm sai redirect URL. Chỉ tin vào forwarded headers khi hạ tầng proxy đáng tin và đã giới hạn nguồn có thể gửi chúng.

## 12. Các trường hợp làm kết quả redirect khó hiểu

### 12.1. RequestCache bị vô hiệu hóa

Với `NullRequestCache` hoặc chính sách session/stateless không lưu request, không có saved request để ưu tiên. Khi đó `defaultSuccessUrl("/dashboard")` hoạt động gần giống một URL đích cố định cho các lần login được quản lý bởi handler mặc định. Nhưng không nên bật stateless bừa bãi cho form login dựa trên session; ứng dụng sẽ mất mô hình duy trì đăng nhập như mong muốn.

### 12.2. Nhiều SecurityFilterChain

Nếu có API chain `securityMatcher("/api/**")` trước web chain, API có thể dùng bearer/HTTP Basic còn web chain dùng form login. Mỗi request đi qua **SecurityFilterChain đầu tiên khớp**; không phải mọi response 401/302 được tạo bởi cùng một form login success handler. Kiểm tra thứ tự chain và matcher khi URL đích khác kỳ vọng.

### 12.3. Session hết hạn hoặc session khác giữa hai request

`HttpSessionRequestCache` thường lưu saved request trong session. Nếu browser không gửi cookie session hoặc session đã hết hạn, request login sau đó không tìm thấy saved request. Chạy lại kịch bản với cookie đúng; đừng đánh giá handler chỉ từ request POST không giữ session.

### 12.4. CSRF bị từ chối trước bước xác thực

Nếu tự viết form login và quên token, `CsrfFilter` có thể từ chối `POST /login` với 403. `AuthenticationSuccessHandler` **không hề được gọi**, vì login chưa thành công. Kiểm tra CSRF trước khi debug redirect.

### 12.5. Authentication thất bại hoặc user thiếu quyền ở URL đích

Password sai sẽ đi qua failure handler, thường quay lại `/login?error`. Login đúng nhưng redirect tới tài nguyên yêu cầu authority người dùng không có có thể tạo 403 tại **request mới**. Đừng nhầm lỗi phân quyền sau redirect với lỗi đăng nhập.

### 12.6. Custom successHandler quên dọn saved request

Nếu handler chủ ý bỏ URL đã lưu nhưng không xóa mục đó khỏi `RequestCache`, có thể xuất hiện điều hướng lạ ở request kế tiếp hoặc lưu dư trạng thái. Khi override logic, phải hiểu vòng đời RequestCache và đảm bảo xử lý saved request nhất quán.

### 12.7. Sử dụng targetUrlParameter tùy tiện

Các success handler kế thừa `AbstractAuthenticationTargetUrlRequestHandler` có thể hỗ trợ tham số chỉ định đích chuyển hướng. Nếu bật tính năng này và chấp nhận URL không kiểm soát từ request, nguy cơ open redirect tăng. Ưu tiên đích server-defined hoặc allowlist nghiêm ngặt, và test các input như URL tuyệt đối, `//host`, encoding bất thường, đường dẫn thoát context path.

### 12.8. Đã custom successHandler nhưng vẫn mong defaultSuccessUrl có hiệu lực

Một handler custom đã chọn URL và gửi response thì Spring Security không chạy thêm một “vòng redirect mặc định” sau nó. Nếu cần chính sách kết hợp, cấu hình logic kết hợp trong handler. Tránh mutate bean singleton để đổi target theo user và làm rò URL giữa request đồng thời.

### Bảng tra nhanh

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Sau login đến /orders/42 thay vì /dashboard | SavedRequest được ưu tiên | Xem RequestCache, `alwaysUse=false` |
| Luôn đến dashboard dù đã mở deep link | `alwaysUse=true`, handler custom hoặc cache trống | Xem cấu hình handler, session và matcher lưu request |
| Login đúng nhưng vẫn 403 | URL đích thiếu authority hoặc POST login bị CSRF chặn | Phân biệt 403 trước và sau authentication |
| Không có redirect sau POST /login | Sai loginProcessingUrl, authentication thất bại hoặc handler trả response khác | Xem status/Location và filter processing |
| Người dùng đôi lúc đến URL của tab khác | SavedRequest bị thay đổi trong session dùng chung | Test nhiều tab, xác định chính sách cache |
| Redirect về host/scheme không đúng | Proxy/context path/forwarded headers cấu hình chưa chính xác | Kiểm tra reverse proxy và RedirectStrategy |
| Login đúng nhưng URL sau login rỗng hoặc sai | Handler custom gửi URL lỗi | Test handler và allowlist đích |
| Login xong trở lại /login liên tục | Authentication/session không duy trì hoặc security rule cho /login sai | Kiểm tra session cookie, context repository, permitAll và redirect loop |
| Có open redirect qua tham số next | URL client cung cấp chưa được kiểm soát | Thay bằng mapping đích server-defined |

## 13. Bài tập thực hành

**Bài 1.** Alice mở `/orders/42` khi chưa đăng nhập, Spring Security lưu request, Alice login thành công, cấu hình `defaultSuccessUrl("/dashboard")`. Đích nào thường được chọn?

**Đáp án:** `/orders/42` được ưu tiên vì handler mặc định nhận ra saved request. Chỉ khi không có saved request phù hợp, nó dùng `/dashboard`.

**Bài 2.** Cùng kịch bản nhưng cấu hình `defaultSuccessUrl("/dashboard", true)`. Đích nào?

**Đáp án:** `/dashboard` dù trước login có request đã lưu. Chính sách “always use default” bỏ ưu tiên saved request.

**Bài 3.** Ứng dụng dùng `successHandler(roleHandler)` chọn URL theo `ROLE_ADMIN`. Có thể tiếp tục trông chờ `defaultSuccessUrl("/dashboard")` tự thực thi khi handler xong không?

**Đáp án:** Không. Custom handler chịu trách nhiệm chọn response; muốn fallback mặc định thì chính handler phải triển khai/ủy quyền cho hành vi đó.

**Bài 4.** User đăng nhập thành công và được chuyển đến `/admin/home` nhưng chỉ có `ROLE_USER`. Có phải success handler bị lỗi xác thực?

**Đáp án:** Không nhất thiết. Success handler chỉ chọn URL; request tiếp theo vẫn qua authorization và có thể bị từ chối 403. Nên chọn target phù hợp, nhưng không thay security rule bằng lựa chọn target.

**Bài 5.** Người dùng đưa `next=https://untrusted.example/phishing` vào POST login; handler dùng thẳng `sendRedirect(next)`. Rủi ro gì?

**Đáp án:** Open redirect và phishing. Cần không tin URL tùy ý từ client; dùng mã lựa chọn/allowlist hoặc kiểm tra URL nghiêm ngặt, đồng thời không đưa token/credentials vào URL.

**Bài 6.** Test MockMvc gửi `POST /login` không kèm CSRF và thấy 403 thay vì redirect. Nên sửa `defaultSuccessUrl` không?

**Đáp án:** Không. Nếu CSRF bật, request login phải có CSRF token hợp lệ; với Spring Security Test dùng `with(csrf())` hoặc form login test builder phù hợp. Khi POST bị chặn, success handler chưa chạy.

**Bài 7.** Hệ thống form login được triển khai trên `/portal` nhưng redirect về `/dashboard` ở root domain thay vì `/portal/dashboard`. Nên kiểm tra gì?

**Đáp án:** Context path, cấu hình RedirectStrategy, forward headers từ reverse proxy và chính sách URL tương đối/tuyệt đối. Test trên URL triển khai thật, không hardcode host nội bộ.

**Bài 8.** Người dùng mở hai tab: tab A đòi `/orders/42`, tab B đòi `/profile`, sau đó login tại tab A. Có chắc về `/orders/42` không?

**Đáp án:** Không. Saved request có thể được lưu theo session và tab B đã ghi đè entry ưu tiên. Nếu UX cần bảo toàn hành trình theo tab, phải thiết kế request cache/đích điều hướng phù hợp và tránh nhận URL ngoài allowlist.

## 14. Checklist thiết kế và kiểm chứng

- Xác định **cơ chế login**: form login thực sự hay Basic/Bearer/OAuth2; không áp dụng nhầm handler.
- Xác định `loginPage`, `loginProcessingUrl`, `failureUrl` và `defaultSuccessUrl` làm nhiệm vụ gì.
- Chọn rõ chính sách: **saved request ưu tiên**, **luôn dùng default**, hay **custom role/business handler**.
- Khi dùng `defaultSuccessUrl(..., true)`, kiểm tra trải nghiệm deep link và việc loại saved request.
- Khi dùng `successHandler(...)`, handler phải định nghĩa đầy đủ redirect, session state và xử lý saved request.
- Không sửa shared handler singleton theo từng request để thay target.
- Đích redirect phải được chọn từ nguồn đáng tin cậy; không lấy URL bất kỳ từ request mà thiếu allowlist.
- Luôn bảo vệ endpoint đích bằng authorization; redirect không phải quyền truy cập.
- Test **login trực tiếp**, **login sau protected GET**, **saved request có/không**, **admin/user**, **CSRF**, **login sai** và **session**.
- Với proxy/context path, kiểm tra header `Location` trên môi trường triển khai.
- Tránh gửi secret/token vào query string hoặc log redirect.

**Kết luận:** `defaultSuccessUrl("/dashboard")` là **đích dự phòng**, vì `SavedRequestAwareAuthenticationSuccessHandler` thường ưu tiên request được lưu từ trước; overload `defaultSuccessUrl("/dashboard", true)` ép chọn một đích cố định. Khi hành vi cần phụ thuộc quyền hoặc nghiệp vụ, `successHandler(...)` trao quyền chọn response cho code của ứng dụng. Thiết kế tốt phải thống nhất **ưu tiên URL, session/request cache, authorization và an toàn chuyển hướng**, đồng thời kiểm thử cả luồng từ request bảo vệ đến POST login.