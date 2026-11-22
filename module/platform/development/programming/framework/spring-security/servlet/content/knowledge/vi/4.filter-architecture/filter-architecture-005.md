# Thứ tự bộ lọc và quan hệ giữa nạp ngữ cảnh, xác thực, CSRF và phân quyền

> Bài Knowledge thuộc **Kiến trúc bộ lọc** của Spring Security **Servlet stack**. Nội dung dùng quy ước Spring Security 6 / Spring Boot 3, Jakarta Servlet và Java 17+. Danh sách filter chính xác thay đổi theo cơ chế đăng nhập, cấu hình session, OAuth2 và những filter tùy chỉnh được bật.

## 1. Một HTTP request đi qua những tầng nào?

Trên Servlet stack, Spring Security tham gia chuỗi filter của Servlet container bằng `DelegatingFilterProxy`, thường mang tên `springSecurityFilterChain`. Proxy chuyển xử lý tới `FilterChainProxy`. Thành phần này tìm **`SecurityFilterChain` đầu tiên khớp request**, sau đó gọi các security filter trong chain được chọn theo thứ tự.

```text
HTTP request
    |
    v
[Servlet container filter chain]
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
            |
            v
        FilterChainProxy
            |
            +-- chọn SecurityFilterChain đầu tiên khớp URL/request
            |
            +-- SecurityContextHolderFilter (cung cấp SecurityContext)
            +-- ... các filter hạ tầng/CORS nếu cấu hình ...
            +-- CsrfFilter
            +-- LogoutFilter
            +-- ... filter xác thực được bật ...
            +-- AnonymousAuthenticationFilter
            +-- ExceptionTranslationFilter
            +-- AuthorizationFilter
            |
            v
        Spring MVC / Servlet / Controller
```

Sơ đồ trình bày **thứ tự tương đối của các giai đoạn quan trọng**, không phải danh sách mặc định bất biến. Một số filter có thể vắng mặt, ví dụ `UsernamePasswordAuthenticationFilter` khi không bật form login hoặc `BearerTokenAuthenticationFilter` khi không cấu hình OAuth2 Resource Server.

Cần phân biệt ba loại thứ tự:

1. **Servlet container order:** vị trí của `DelegatingFilterProxy` so với những Servlet filter khác.
2. **Security filter order:** vị trí các filter bên trong một `SecurityFilterChain`; điều chỉnh bằng `addFilterBefore`, `addFilterAfter` hoặc cơ chế cấu hình tương ứng.
3. **Authorization rule order:** thứ tự những `requestMatchers(...)` trong `authorizeHttpRequests(...)`; rule phù hợp đầu tiên quyết định chính sách truy cập.

`@Order` trên nhiều `SecurityFilterChain` giúp xác định **chain nào được xét trước**, không phải vị trí của từng filter trong chain. `securityMatcher(...)` giới hạn phạm vi chain, khác với `requestMatchers(...)` dùng cho rule phân quyền bên trong chain.

## 2. Vai trò và thứ tự của các filter cốt lõi

| Giai đoạn | Filter tiêu biểu | Thực hiện | Không thực hiện |
| --- | --- | --- | --- |
| Nạp/chuẩn bị context | `SecurityContextHolderFilter` | Cung cấp `SecurityContext` cho lượt xử lý hiện tại, thường lấy qua `SecurityContextRepository` khi cần. | Không mặc định kiểm tra lại username/password hoặc luôn lưu context ở cuối request. |
| Chống giả mạo request | `CsrfFilter` | Kiểm tra CSRF token đối với các HTTP method cần bảo vệ, trước nhiều filter xác thực. | Không đánh giá quyền `ROLE_ADMIN` hay đọc mật khẩu đăng nhập. |
| Đăng xuất | `LogoutFilter` | Xử lý logout request phù hợp rồi có thể kết thúc response. | Không có nghĩa mọi GET tới URL logout sẽ thực sự đăng xuất. |
| Xác thực | `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, `BearerTokenAuthenticationFilter`… | Xử lý credential/token phù hợp, tạo `Authentication` và cập nhật context khi xác thực thành công. | Không đảm bảo mọi request đều có credential hoặc mọi chain chứa đủ các filter này. |
| Danh tính mặc định | `AnonymousAuthenticationFilter` | Đặt anonymous authentication khi chưa có principal phù hợp. | Không biến anonymous thành người dùng đã đăng nhập. |
| Xử lý lỗi bảo mật ở cuối chain | `ExceptionTranslationFilter` | Chuyển ngoại lệ xác thực/phân quyền từ các filter **phía sau** thành entry point hoặc access denied handling. | Không tự xác thực, và không bao trùm mọi filter đứng trước nó. |
| Quyết định truy cập | `AuthorizationFilter` | Kiểm tra `AuthorizationManager` theo các rule đã cấu hình, thường là chốt cuối trước endpoint. | Không tự kiểm tra CSRF hay xác thực password. |

Vị trí tương đối quan trọng nhất:

```text
NẠP CONTEXT
     v
KIỂM TRA CSRF   ---- thiếu/sai token ----> 403 (dừng sớm)
     v
XÁC THỰC nếu có credential đúng loại
     v
ANONYMOUS nếu chưa có danh tính
     v
EXCEPTION TRANSLATION (bao quanh xử lý phía sau)
     v
PHÂN QUYỀN ----- thiếu quyền -----------> 401/302/403 tùy trạng thái
     v
ENDPOINT
```

Chẳng hạn, `POST /login` thiếu CSRF token có thể bị từ chối **trước** `UsernamePasswordAuthenticationFilter`; còn `GET /admin` của người dùng đã đăng nhập có thể vượt qua các bước đầu nhưng bị chặn bởi `AuthorizationFilter`.

## 3. Nạp SecurityContext và vòng đời Authentication

### 3.1. SecurityContext, Authentication và SecurityContextHolder

`SecurityContext` chứa `Authentication`, đại diện cho principal và authorities mà các thành phần bảo mật dùng trong request hiện tại. Có thể đọc trong code chạy sau các filter liên quan:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Đoạn trên cần các import `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder` trong ứng dụng Spring Security. **Có object `Authentication` không nhất thiết có nghĩa đăng nhập thật:** `AnonymousAuthenticationFilter` có thể đã đặt `AnonymousAuthenticationToken` vào holder. Do đó tránh dùng điều kiện `authentication != null` để thay thế rule `authenticated()`.

`SecurityContextHolder` mặc định gắn context với **thread hiện tại**. Nó không tự động là bộ lưu đăng nhập lâu dài; tự tạo thread/executor mới không đồng nghĩa context của request cũ được chuyển tiếp. Với MVC async cần sử dụng các cơ chế context propagation phù hợp.

### 3.2. Ai nạp và ai lưu context?

`SecurityContextRepository` có nhiệm vụ lấy/lưu context theo cơ chế cấu hình: ví dụ dựa vào HTTP session hoặc request attribute. `SecurityContextHolderFilter` của Spring Security 6 có thể chuẩn bị **deferred context** và chỉ truy xuất thực sự khi cần, vì vậy không được giả định mọi request đều đọc session ngay lập tức.

Luồng dùng session điển hình:

```text
Request đăng nhập:
  UsernamePasswordAuthenticationFilter
    -> xác thực thành công
    -> đặt Authentication vào SecurityContext
    -> cơ chế xác thực lưu SecurityContext qua SecurityContextRepository
    -> client có thể nhận session cookie

Request kế tiếp:
  Browser gửi session cookie
    -> SecurityContextHolderFilter cung cấp context đã lưu
    -> AuthorizationFilter đọc Authentication và authorities hiện tại
    -> cho phép hoặc từ chối truy cập
```

Trong Spring Security 6, mô hình `SecurityContextHolderFilter` thường yêu cầu **lưu thay đổi context tường minh**. Trong custom authentication filter, chỉ làm:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

**chưa đủ** để chắc chắn request sau còn đăng nhập. Khi cần duy trì trạng thái, tích hợp `SecurityContextRepository.saveContext(...)` đúng cách; các authentication filter chuẩn xử lý cơ chế lưu tương ứng. Codebase đời cũ dùng `SecurityContextPersistenceFilter` có hành vi lưu và vòng đời khác; không nên áp dụng quy tắc của một filter cho filter còn lại.

### 3.3. Stateless vẫn cần SecurityContext

Trong API Bearer stateless, request thường mang token riêng; không cần dùng session để giữ login giữa các request. Tuy nhiên filter Bearer vẫn xác thực token và đặt `Authentication` vào `SecurityContextHolder` cho **request hiện tại**, để authorization biết người gửi request là ai.

```text
GET /api/items + Authorization: Bearer <token>
   |
   +-- SecurityContext ban đầu chưa có principal
   +-- BearerTokenAuthenticationFilter kiểm tra token
   +-- Authentication được thiết lập cho request này
   +-- AuthorizationFilter kiểm tra authority/policy
```

Stateless **không có nghĩa** tắt Spring Security context hoặc bỏ qua phân quyền.

## 4. Xác thực: khi nào credentials được kiểm tra?

**Authentication** trả lời “người gửi request là ai và bằng chứng xác minh là gì?”. Tùy cấu hình:

- `UsernamePasswordAuthenticationFilter` thường xử lý POST đến login processing URL khi bật `formLogin`.
- `BasicAuthenticationFilter` giải mã và xác minh HTTP Basic credentials.
- `BearerTokenAuthenticationFilter` xử lý Bearer token của OAuth2 Resource Server.
- Các filter khác có thể xử lý remember-me, pre-authentication hoặc cơ chế login riêng.

Khi request khớp, filter xác thực có thể tạo `Authentication` bằng cách gọi `AuthenticationManager`/`AuthenticationProvider`, đặt kết quả vào context và lưu context nếu cơ chế yêu cầu. Khi thất bại, authentication filter có thể tự gọi failure handler/entry point và **không gọi tiếp** filter phía sau. Với form login thành công, success handler thường redirect; không phải mọi POST login đều đi tới controller ứng dụng.

Một request đã có `Authentication` từ session có thể **không phải xác thực lại mật khẩu** ở mỗi lượt. Ngược lại, API Bearer stateless có thể kiểm tra token trên mỗi request.

**Authentication khác authorization:** người dùng đã đăng nhập với `ROLE_USER` vẫn có thể bị từ chối ở `/admin/**` nếu rule cần `ROLE_ADMIN`. Principal anonymous cũng có thể đi vào endpoint công khai với `permitAll()`.

## 5. CSRF đứng trước xác thực/phân quyền và hoạt động độc lập

CSRF (Cross-Site Request Forgery) là tình huống website khác cố kích hoạt request thay mặt người dùng khi browser **tự gửi credential** như session cookie. `CsrfFilter` yêu cầu token hợp lệ cho những request dễ gây thay đổi trạng thái. Theo mặc định, `GET`, `HEAD`, `OPTIONS` và `TRACE` được coi là safe methods; `POST`, `PUT`, `PATCH` và `DELETE` thường cần token.

**Điều đặc biệt quan trọng:** `permitAll()` chỉ ảnh hưởng **quy tắc authorization**. Nó không tắt `CsrfFilter`.

| Request | Chính sách URL | CSRF | Kết quả điển hình |
| --- | --- | --- | --- |
| `GET /demo/public`, anonymous | `permitAll()` | Không yêu cầu token theo method mặc định | 200 nếu handler chạy tốt. |
| `POST /demo/public`, anonymous, thiếu token | `permitAll()` | Thất bại ở `CsrfFilter` | 403 **trước authorization**. |
| `POST /demo/public`, anonymous, token hợp lệ | `permitAll()` | Qua CSRF | Có thể tới handler. |
| `GET /demo/private`, anonymous | `authenticated()` | Không yêu cầu token | Redirect login hoặc 401 tùy cơ chế. |
| `GET /demo/private`, user đã đăng nhập | `authenticated()` | Không yêu cầu token | Có thể tới handler. |
| `POST /demo/private`, user đã đăng nhập, thiếu token | `authenticated()` | Thất bại ở `CsrfFilter` | 403 dù user đã đăng nhập. |
| `POST /demo/private`, user đã đăng nhập, token hợp lệ | `authenticated()` | Qua CSRF | Tới phân quyền rồi handler nếu được phép. |

### 5.1. Tại sao login cũng cần CSRF?

Một website độc hại có thể cố ép browser đăng nhập vào tài khoản do kẻ khác kiểm soát (login CSRF). Do `CsrfFilter` đứng trước `UsernamePasswordAuthenticationFilter`, request POST login thiếu/sai token sẽ có thể bị chặn **trước khi password được kiểm tra**. Logout cũng làm đổi trạng thái; mặc định với CSRF bật, POST logout cần token hợp lệ.

### 5.2. Token được gửi thế nào?

Form HTML thường chứa hidden input `_csrf`, còn AJAX/SPA có thể gửi header theo cấu hình. `CsrfTokenRepository` quyết định chỗ lưu token; `CsrfTokenRequestHandler` quyết định cách request cung cấp token. Trong Spring Security 6, deferred tokens và cơ chế che giấu token (liên quan BREACH) có thể ảnh hưởng việc SPA đọc token từ cookie và gửi qua header; phải cấu hình client và server tương thích, không tự suy ra một token cookie luôn dùng được nguyên dạng ở mọi thiết lập.

### 5.3. Có nên tắt CSRF cho API?

Chỉ cân nhắc khi đánh giá đúng threat model. Một API chỉ dùng Bearer token do client **chủ động** đưa vào `Authorization` header, không dùng cookie hay credential tự động gửi bởi browser, có thể cần chính sách CSRF khác. Nhưng API JSON dùng session cookie vẫn thường cần bảo vệ CSRF. HTTP Basic trong browser cũng cần đánh giá vì trình duyệt có thể gửi lại credentials tự động. Chỉ gọi API là “REST” hoặc “stateless” không đủ để bỏ kiểm tra CSRF.

## 6. Phân quyền và vai trò của ExceptionTranslationFilter

`AuthorizationFilter` thường ở cuối security chain mặc định. Nó áp dụng những rule trong `authorizeHttpRequests(...)`, dựa trên Authentication và request hiện tại:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

Đây là DSL **đặt trong cấu hình `HttpSecurity`**, không phải class Java đầy đủ. `hasRole("ADMIN")` thường đòi authority `ROLE_ADMIN` với role prefix mặc định. Thứ tự matcher phải từ cụ thể đến tổng quát để tránh rule quá rộng chiếm trước.

Khi AuthorizationFilter phát sinh `AccessDeniedException`, `ExceptionTranslationFilter` phía trước có thể:

- Khởi động `AuthenticationEntryPoint` (redirect login hoặc 401) khi người gửi bị xem là chưa xác thực.
- Gọi `AccessDeniedHandler` (thường 403) khi đã xác thực nhưng thiếu quyền.

`ExceptionTranslationFilter` **không thực hiện** password authentication và **chỉ bao quanh** những filter phía sau. `CsrfFilter` nằm trước nó và có đường `AccessDeniedHandler` riêng. Vì vậy 403 do CSRF không chứng tỏ request đã tới `AuthorizationFilter`. Các authentication filter cũng có failure handler riêng và có thể dừng request trước đó.

Ngoài URL authorization, code có thể dùng method security như `@PreAuthorize`; cho qua `AuthorizationFilter` ở mức URL không tự động cho phép mọi method chạy phía sau.

## 7. Tình huống so sánh theo thứ tự thực thi

**Tình huống A: GET công khai.** `GET /demo/public` không cần CSRF token; không có login cũng có thể vào controller vì rule `permitAll()`. `AnonymousAuthenticationFilter` có thể đặt anonymous principal trước authorization.

**Tình huống B: POST công khai thiếu CSRF.** `POST /demo/public` thiếu token: `CsrfFilter` chặn trước authorization. Đổi `permitAll()` thành rule khác không làm token hợp lệ.

**Tình huống C: POST đăng nhập.** Với form login, CSRF phải qua trước. Sau đó `UsernamePasswordAuthenticationFilter` nhận credential, xác thực, lưu context khi phù hợp và redirect. Login thành công chưa chắc sẽ chạy `AuthorizationFilter` của cùng request.

**Tình huống D: GET có session.** `SecurityContextHolderFilter` có thể khôi phục context; không cần xác thực mật khẩu lại ở mọi request; `AuthorizationFilter` kiểm tra role.

**Tình huống E: POST có session nhưng thiếu CSRF.** Người dùng đã đăng nhập vẫn nhận 403 ở CSRF; không phải lỗi thiếu role.

**Tình huống F: API Bearer.** Bearer filter xác thực token rồi đặt principal vào holder; phân quyền sử dụng principal ấy. Vẫn phải xem chain matcher và CSRF policy thực tế, đặc biệt nếu browser có thể tự gửi credential.

## 8. Ví dụ chạy được với Java 17, Spring Boot 3 và MockMvc

Ví dụ sau dùng hai URL: `/demo/public` cho mọi người, `/demo/private` cần đăng nhập. CSRF giữ nguyên mặc định; tests kiểm chứng **bảy tình huống**. Một probe filter chạy sau `AnonymousAuthenticationFilter` để quan sát request đã đi đến gần bước authorization. Vì probe ở **sau `CsrfFilter`**, request thiếu token bị chặn sớm sẽ không tới probe.

### 8.1. Tạo project

```text
security-flow/
├── pom.xml
└── src/
    ├── main/java/example/securityflow/
    │   ├── SecurityFlowApplication.java
    │   └── DemoController.java
    └── test/java/example/securityflow/
        └── SecurityFlowApplicationTests.java
```

**`pom.xml`**:

```xml
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
    <groupId>example</groupId>
    <artifactId>security-flow</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
```

**`src/main/java/example/securityflow/SecurityFlowApplication.java`**:

```java
package example.securityflow;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@SpringBootApplication
public class SecurityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFlowApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/demo/public").permitAll()
                    .requestMatchers("/demo/private").authenticated()
                    .anyRequest().denyAll())
            .formLogin(form -> form.permitAll());

        // Probe chỉ thuộc Spring Security filter chain.
        // Không thêm @Component cho probe để tránh đăng ký kép.
        http.addFilterAfter(
                new AuthorizationProbe(),
                AnonymousAuthenticationFilter.class);

        // Giữ nguyên CSRF mặc định, không gọi csrf.disable().
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        // "{noop}" chỉ cho demo, KHÔNG dùng cho mật khẩu thực tế.
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                    .password("{noop}demo-pass")
                    .roles("USER")
                    .build()
        );
    }

    static final class AuthorizationProbe extends OncePerRequestFilter {
        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {
            Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();
            String principal = auth == null ? "(none)" : auth.getName();

            System.out.printf("PROBE %s %s principal=%s%n",
                    request.getMethod(),
                    request.getRequestURI(),
                    principal);

            chain.doFilter(request, response);
        }
    }
}
```

**`src/main/java/example/securityflow/DemoController.java`**:

```java
package example.securityflow;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/demo/public")
    public String publicGet() {
        return "public-get";
    }

    @PostMapping("/demo/public")
    public String publicPost() {
        return "public-post";
    }

    @GetMapping("/demo/private")
    public String privateGet() {
        return "private-get";
    }

    @PostMapping("/demo/private")
    public String privatePost() {
        return "private-post";
    }
}
```

**`src/test/java/example/securityflow/SecurityFlowApplicationTests.java`**:

```java
package example.securityflow;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityFlowApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void publicGetIsAllowed() throws Exception {
        mvc.perform(get("/demo/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public-get"));
    }

    @Test
    void publicPostWithoutCsrfIsDenied() throws Exception {
        mvc.perform(post("/demo/public"))
                .andExpect(status().isForbidden());
    }

    @Test
    void publicPostWithCsrfIsAllowed() throws Exception {
        mvc.perform(post("/demo/public").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("public-post"));
    }

    @Test
    void privateGetWithoutLoginRedirects() throws Exception {
        mvc.perform(get("/demo/private")
                        .accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void privateGetWithUserIsAllowed() throws Exception {
        mvc.perform(get("/demo/private").with(user("learner")))
                .andExpect(status().isOk())
                .andExpect(content().string("private-get"));
    }

    @Test
    void privatePostWithUserButNoCsrfIsDenied() throws Exception {
        mvc.perform(post("/demo/private").with(user("learner")))
                .andExpect(status().isForbidden());
    }

    @Test
    void privatePostWithUserAndCsrfIsAllowed() throws Exception {
        mvc.perform(post("/demo/private")
                        .with(user("learner"))
                        .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().string("private-post"));
    }
}
```

Yêu cầu cài JDK 17+ và Maven; chạy trong `security-flow`:

```bash
mvn test
mvn spring-boot:run
```

Bảy bài test biểu diễn các assertion **mong đợi** trên cấu hình này; lệnh `mvn test` sẽ kiểm tra các giá trị ấy. Khi ứng dụng chạy, thử:

```bash
curl -i http://localhost:8080/demo/public
curl -i -X POST http://localhost:8080/demo/public
curl -i -H "Accept: text/html" http://localhost:8080/demo/private
```

Kết quả HTTP mong đợi (bỏ qua header thay đổi theo môi trường): **200**, **403**, **302 redirect login**. POST muốn qua CSRF cần token hợp lệ; tests cấp token bằng `with(csrf())`. `user("learner")` ở đây **mô phỏng principal đã xác thực** cho một request MockMvc, không phải test password login thật.

Những dòng log **ví dụ**, không đại diện thứ tự kiểm thử cố định:

```text
PROBE GET /demo/public principal=anonymousUser
PROBE GET /demo/private principal=learner
PROBE POST /demo/private principal=learner
```

Request POST thiếu CSRF token sẽ bị dừng tại `CsrfFilter` trước probe, nên không xuất hiện log tương ứng. Request chưa đăng nhập có thể tới probe với `anonymousUser` rồi bị `AuthorizationFilter` từ chối; việc probe ghi log không có nghĩa request đã được cho phép. Với POST login thành công, filter xác thực có thể redirect mà không đi tiếp tới probe.

### 8.2. Xem log thứ tự filter thật sự

Trong môi trường phát triển có thể bật:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

Đặt vào `src/main/resources/application.properties`. Xem các log “Invoking ...Filter” để biết filter nào được gọi, chain nào được chọn, và request dừng ở đâu. Tắt TRACE sau khi chẩn đoán để tránh log quá nhiều hoặc chứa dữ liệu nhạy cảm.

## 9. Các lỗi thiết kế và cách phòng tránh

1. **Nhầm `permitAll()` với “bỏ qua toàn bộ bảo mật”.** Nó chỉ thay đổi policy authorization. CSRF, login filter và các security filter khác vẫn có thể xử lý request.
2. **Nghĩ HTTP 403 luôn do `AuthorizationFilter`.** CSRF có thể từ chối trước. Đọc log của filter gây lỗi và thử request có CSRF token hợp lệ.
3. **Chỉ kiểm tra `authentication != null` để biết đã đăng nhập.** AnonymousAuthenticationFilter có thể đặt token anonymous. Dùng các rule `authenticated()` hoặc cơ chế xác định anonymous đúng cách.
4. **Đặt context trong custom filter mà quên lưu.** Với `SecurityContextHolderFilter` hiện đại, tích hợp `SecurityContextRepository` và tường minh lưu context theo thiết kế cần thiết.
5. **Tự viết mã thay đổi dữ liệu quá sớm, trước kiểm tra CSRF.** Side effect nghiệp vụ có thể xảy ra trước khi request bị từ chối; phải để đường thay đổi dữ liệu nằm sau các kiểm soát phù hợp.
6. **Đăng ký custom Filter hai lần.** Nếu filter vừa là `@Component` được container tự đăng ký vừa thêm bằng `http.addFilterBefore/After`, nó có thể chạy ở hai vị trí. Demo tạo probe trực tiếp trong cấu hình để tránh việc này.
7. **Dùng `@Order` sai cấp.** `@Order` của nhiều `SecurityFilterChain` điều khiển chọn chain, `addFilter...` điều khiển thứ tự filter bên trong chain, `requestMatchers` điều khiển thứ tự rule.
8. **Áp rule vào nhầm SecurityFilterChain.** `FilterChainProxy` chọn chain khớp đầu tiên; các chain không được gộp. Khi có `/api/**` và `/**`, kiểm tra matcher và thứ tự của cả hai.
9. **Tắt CSRF chỉ vì API dùng JSON.** Nếu browser có thể tự gửi cookie/session hoặc credentials, nguy cơ CSRF có thể vẫn tồn tại.
10. **Tưởng `OncePerRequestFilter` luôn chạy một lần duy nhất mọi dispatcher.** Async/error dispatch và registration dispatcher types ảnh hưởng số lượt gọi; phải xét cơ chế của container lẫn filter.
11. **Giả định `ExceptionTranslationFilter` bắt mọi security exception.** Nó chủ yếu xử lý ngoại lệ từ các filter đứng sau; CSRF và filter xác thực phía trước có handler riêng.
12. **Đồng nhất session với context.** Session lưu trạng thái giữa các request khi được cấu hình; `SecurityContextHolder` đại diện context trong phạm vi xử lý hiện tại.

## 10. Quy trình chẩn đoán request bị chặn

1. Ghi chính xác **HTTP method, URI, dispatcher type**, authentication mechanism và request headers liên quan. Không đưa password/token thật vào log.
2. Xác định **`SecurityFilterChain` đầu tiên khớp** request; các chain khác không tham gia cho request đó.
3. Bật TRACE phù hợp để tìm **filter dừng sớm**. `CsrfFilter` trước authorization, filter login có thể tự kết thúc request.
4. Đọc `Authentication` tại giai đoạn sau xác thực/anonymous; phân biệt null, anonymous và user thật.
5. Với form/session: xác minh login success đã lưu context, session cookie được trả về và client gửi lại.
6. Với Bearer/stateless: xác minh token được kiểm tra, principal và authorities được dựng đúng.
7. Kiểm tra policy `authorizeHttpRequests`, thứ tự `requestMatchers`, role prefix và method security. Nếu cần custom filter, kiểm tra thứ tự bên trong chain cùng việc đăng ký container.
8. Viết test cho **GET/POST**, có/không token CSRF, anonymous/authenticated và đủ/thiếu role. Đọc status và filter log cùng nhau.

## 11. Tự kiểm tra

**1.** Một `POST /public` đã cấu hình `permitAll()`, thiếu CSRF token, có thể trả gì?  
**Đáp án:** 403 tại `CsrfFilter`, trước khi rule `permitAll()` được xét.

**2.** Một user đã đăng nhập được nạp từ HTTP session có bắt buộc kiểm tra lại password ở mọi request không?  
**Đáp án:** Không. Context được khôi phục từ repository; password authentication là cơ chế riêng.

**3.** Đã login với `ROLE_USER` nhưng `/admin/**` yêu cầu `ROLE_ADMIN`, bị chặn ở bước nào?  
**Đáp án:** Phân quyền; thường `AuthorizationFilter` phát sinh từ chối và `ExceptionTranslationFilter` chuyển thành phản hồi phù hợp.

**4.** Một `Authentication` không null chắc chắn là user đã login không?  
**Đáp án:** Không; có thể là `AnonymousAuthenticationToken`.

**5.** Chỉ gọi `setAuthentication(...)` trong custom filter có bảo đảm request sau còn login không?  
**Đáp án:** Không; với cơ chế hiện đại, phải bảo đảm lưu context qua repository phù hợp khi cần duy trì đăng nhập.

**6.** Có thể sửa quyền của chain API bằng cách thêm `requestMatchers(...)` vào chain MVC không khớp API không?  
**Đáp án:** Không. `FilterChainProxy` áp dụng chain khớp đầu tiên, cần cấu hình trên đúng chain.

**7.** `ExceptionTranslationFilter` có phải nơi đọc password và kiểm tra token CSRF không?  
**Đáp án:** Không. Authentication filter và `CsrfFilter` có trách nhiệm riêng; exception translation nằm gần cuối chain.

**8.** API Bearer stateless có cần `SecurityContext` không?  
**Đáp án:** Có, để authorization và code phía sau biết principal trong request hiện tại, dù không lưu đăng nhập vào session.

**Ghi nhớ:** hiểu **thứ tự filter**, **nguồn Authentication** và **giai đoạn bị dừng** là chìa khóa để phân biệt lỗi CSRF, xác thực và phân quyền trong Spring Security Servlet.