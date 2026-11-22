# Đọc danh tính hiện tại qua API mà không phụ thuộc trực tiếp vào phiên

> **Chủ đề:** Ngữ cảnh bảo mật trong Spring Security trên **Servlet stack**. Các ví dụ dùng Spring Security 6, Spring Boot 3, Jakarta Servlet và Java 17+. Mục tiêu là đọc danh tính mà Spring Security **đã xác thực cho request hiện tại**, thay vì tự tìm user trong `HttpSession`, tự giải mã cookie hoặc tin vào dữ liệu do client khai báo.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

- Giải thích đường đi từ cơ chế xác thực đến `Authentication`, `SecurityContext` và `SecurityContextHolder`.
- Chọn đúng API để lấy username, principal, authorities hoặc một thông tin danh tính đã chuẩn hóa tại controller/service.
- Dùng `Principal`, `Authentication`, `@AuthenticationPrincipal` hoặc `@CurrentSecurityContext` mà không buộc code nghiệp vụ biết thông tin được lưu ở HTTP session, request attribute hay được xác thực lại từ token.
- Xử lý user chưa đăng nhập, anonymous principal, nhiều loại principal và xử lý bất đồng bộ an toàn.
- Phân biệt **đọc danh tính**, **xác thực**, **phân quyền**; tránh trả credential/token và tránh lấy danh tính từ input do client tùy ý gửi.

## 2. SecurityContext là điểm truy cập danh tính của request

Spring Security không yêu cầu controller tự đọc `JSESSIONID` hay tự gọi `session.getAttribute("user")` để biết ai đang yêu cầu tài nguyên. Các security filter xử lý việc nạp hoặc tạo `Authentication` phù hợp và cung cấp thông tin đó qua `SecurityContext`.

```text
HTTP request
    |
    v
Spring Security filter chain
    |
    +-- cơ chế context/repository cho request hiện tại
    |
    +-- nếu có Basic/Bearer/form login:
    |      filter xác thực xử lý credential/token phù hợp
    |      và tạo Authentication khi thành công
    |
    +-- nếu chưa có Authentication phù hợp:
    |      có thể tạo AnonymousAuthenticationToken
    |
    +-- AuthorizationFilter quyết định quyền truy cập
    |
    v
Controller / Service
    |
    +-- Principal / Authentication method argument
    +-- @AuthenticationPrincipal / @CurrentSecurityContext
    +-- SecurityContextHolder.getContext().getAuthentication()
```

Các đối tượng chính:

| Đối tượng | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `Authentication` | Đại diện danh tính và bằng chứng/trạng thái xác thực đã được xử lý trong request. | Chứa `getName()`, `getPrincipal()`, `getAuthorities()`, `isAuthenticated()`; có thể là anonymous. |
| `SecurityContext` | Vùng chứa một `Authentication` hiện tại. | Không phải đối tượng phiên HTTP; là giao diện ngữ cảnh bảo mật. |
| `SecurityContextHolder` | Điểm truy cập ngữ cảnh được Spring Security gắn vào xử lý hiện tại. | Mặc định sử dụng chiến lược dựa vào thread, cần quan tâm async/thread reuse. |
| `SecurityContextRepository` | Nguồn/đích lưu context khi cơ chế yêu cầu. | Có thể dùng HTTP session, request attribute, hoặc cấu hình khác. |
| `Principal` | Giao diện Java chuẩn có `getName()`. | Thích hợp khi chỉ cần tên đã xác thực, không phụ thuộc loại principal cụ thể. |

Cần phân biệt ba khái niệm:

**Authentication** xác minh ai đang gửi request; **identity lookup** đọc kết quả xác thực đã được lưu trong ngữ cảnh; **authorization** quyết định người đó được phép làm gì. Đọc username qua `Authentication.getName()` **không tự kiểm tra** quyền truy cập một tài nguyên.

### 2.1. Vì sao không truy cập trực tiếp session?

Ví dụ gắn chặt nghiệp vụ với session:

```java
// Cách dễ gây phụ thuộc vào nơi lưu danh tính:
HttpSession session = request.getSession(false);
String username = session == null
        ? null
        : (String) session.getAttribute("username");
```

Đây là **đoạn minh họa**, không phải cách xác thực user. Code trên dựa vào tên attribute tùy ý, không có bảo đảm attribute do Spring Security đặt vào, không hoạt động tương đương với Basic/Bearer stateless, và dễ nhầm dữ liệu phiên ứng dụng với **danh tính được xác thực**.

Cách đọc dựa vào Spring Security:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
String username = auth == null ? null : auth.getName();
```

Controller/service giờ quan tâm **“ai được xác thực cho request?”**; quyết định context đến từ session, Basic, Bearer, OAuth2 hay cơ chế khác nằm tại cấu hình security filter. Code vẫn cần xử lý anonymous phù hợp; kiểm tra `auth != null` chưa đủ để kết luận user đã đăng nhập.

## 3. Bốn cách phổ biến để lấy danh tính

### 3.1. `Principal` làm tham số controller

Spring MVC có thể truyền principal của request vào handler:

```java
@GetMapping("/me/name")
public String myName(Principal principal) {
    return principal.getName();
}
```

Đây là **đoạn method** đặt trong `@RestController` với import `java.security.Principal`. Handler cần được bảo vệ bằng `authenticated()` nếu muốn bảo đảm có principal đã đăng nhập. Trên endpoint công khai, không mặc định principal luôn khác `null`.

Ưu điểm: code chỉ quan tâm tên. Nó cũng dùng được khi cơ chế đăng nhập thay đổi mà vẫn có principal phù hợp.

Giới hạn: không cung cấp trực tiếp authorities, loại token, hoặc cấu trúc principal đặc thù. Trong Servlet stack, `HttpServletRequest#getUserPrincipal()` là một cơ chế liên quan; Spring Security tích hợp principal của request với context mà các filter đã xử lý.

### 3.2. `Authentication` làm tham số controller

Khi cần cả tên và authorities:

```java
@GetMapping("/me/roles")
public List<String> myRoles(Authentication authentication) {
    return authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
}
```

Đoạn method trên cần import `org.springframework.security.core.Authentication`, `org.springframework.security.core.GrantedAuthority` và `java.util.List`. `Authentication` là một kiểu `Principal` nên Spring MVC có thể cung cấp nó qua cơ chế giải quyết principal. Nếu cần nêu rõ dữ liệu phải được lấy **từ SecurityContext**, sử dụng `@CurrentSecurityContext(expression = "authentication")` như mục sau.

`getName()` trả tên hiển thị/định danh theo chính sách của loại `Authentication`; không mặc nhiên là primary key trong database. `getAuthorities()` là tập quyền của security layer, không phải danh sách tính năng người dùng được phép truy cập mà không cần kiểm tra thêm resource policy.

### 3.3. `@AuthenticationPrincipal` lấy principal đã được chuẩn hóa

Khi biết ứng dụng dùng một loại principal cụ thể:

```java
@GetMapping("/me/details")
public String details(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

Ví dụ này phù hợp với cơ chế xác thực mà `Authentication.getPrincipal()` trả về `UserDetails`, như cấu hình HTTP Basic sử dụng `DaoAuthenticationProvider` và `UserDetailsService` ở bài thực hành bên dưới.

Ưu điểm: controller không cần nhận toàn bộ object `Authentication`. Hạn chế: principal **không nhất thiết** là `UserDetails` trong mọi cơ chế. Bearer JWT có thể dùng `Jwt`, OAuth2/OIDC có thể dùng `OAuth2User` hoặc `OidcUser`, còn custom filter có thể tạo principal riêng. Nếu chọn sai kiểu, giá trị tiêm có thể `null` hoặc phát sinh lỗi khi bật kiểm tra type; cần hiểu chain đang dùng.

Có thể truy cập thuộc tính principal bằng expression, nhưng chỉ khi kiểu principal cung cấp thuộc tính đó:

```java
@GetMapping("/me/details-name")
public String detailsName(
        @AuthenticationPrincipal(expression = "username")
        String username) {
    return username;
}
```

Đoạn này phù hợp `UserDetails`; không nên sao chép nguyên expression sang `Jwt` hay `OidcUser` khi chưa xác định cấu trúc dữ liệu của chúng.

### 3.4. `@CurrentSecurityContext` lấy context hoặc Authentication

Nếu handler muốn khai báo rõ ràng dependency:

```java
@GetMapping("/me/context")
public String fromContext(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
```

Import annotation `org.springframework.security.core.annotation.CurrentSecurityContext`. Cách này mô tả chính xác việc đọc kết quả xác thực từ `SecurityContext`. Tương tự các cách trên, chỉ dùng thẳng `getName()` khi route bảo đảm principal phù hợp hoặc đã kiểm tra null/anonymous.

### 3.5. Chọn API nào?

| Nhu cầu | API ưu tiên | Phạm vi |
| --- | --- | --- |
| Chỉ cần username trong controller | `Principal` hoặc `Authentication#getName()` | HTTP handler đã được bảo vệ. |
| Cần roles/authorities trong controller | `Authentication` / `@CurrentSecurityContext` | Không cần truy vấn session thủ công. |
| Cần thuộc tính riêng của `UserDetails` | `@AuthenticationPrincipal UserDetails` | Chỉ khi principal thực sự là `UserDetails`. |
| Cần `Jwt` hoặc `OidcUser` | `@AuthenticationPrincipal` với đúng kiểu | Chỉ khi security chain dùng loại principal đó. |
| Code service không phụ thuộc Spring MVC | `SecurityContextHolder` (hoặc abstraction riêng) | Phải ở đúng execution context. |
| Code muốn dùng chuẩn Servlet | `HttpServletRequest#getUserPrincipal()` | Phụ thuộc Servlet request, nhưng không trực tiếp vào HTTP session. |

Không cần tự viết filter đọc `HttpSession` rồi gắn username vào request attribute nếu security chain đã cung cấp principal. Nếu nhiều service cần danh tính, một interface như `CurrentIdentity` có thể gói việc đọc holder để policy anonymous và mapping user ID tập trung một chỗ.

## 4. Nhận diện anonymous và dữ liệu chưa đăng nhập

Một trong những lỗi phổ biến là:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
boolean loggedIn = auth != null && auth.isAuthenticated();
```

Điều kiện này **có thể đánh giá anonymous là đã xác thực** vì `AnonymousAuthenticationToken` có thể trả `isAuthenticated() == true` theo ý nghĩa nội bộ của token. Vì vậy không dùng biểu thức trên làm ranh giới bảo mật.

Ở code nghiệp vụ cần danh tính tùy chọn, có thể loại anonymous:

```java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

if (auth == null
        || !auth.isAuthenticated()
        || auth instanceof AnonymousAuthenticationToken) {
    return Optional.empty();
}
return Optional.of(auth.getName());
```

Đây là **thân method** với import `Authentication`, `AnonymousAuthenticationToken`, `SecurityContextHolder` và `java.util.Optional`. Phần runnable bên dưới triển khai đầy đủ logic này trong service.

Với yêu cầu **bảo vệ endpoint**, cấu hình `.authenticated()` hoặc các rule `hasRole`, `hasAuthority` và policy theo tài nguyên thay vì tự sáng tác kiểm tra `getName()` ở controller. Anonymous filter, remember-me, session state, authority mapping và authentication trust resolver đều có thể ảnh hưởng cách Spring Security đánh giá người dùng.

Một endpoint `permitAll()` có thể được truy cập không có principal thật, và việc Spring Security trì hoãn đọc context có thể khiến null/anonymous xuất hiện tùy đoạn xử lý. Để có response ổn định, **trình bày trạng thái guest rõ ràng** thay vì ép kiểu hay ném NullPointerException.

## 5. Không phụ thuộc session vẫn không đồng nghĩa không có context

### 5.1. Đăng nhập bằng session

```text
Request A: user đăng nhập
  -> authentication filter tạo Authentication
  -> SecurityContextRepository lưu nếu cấu hình yêu cầu
  -> browser nhận/có session cookie

Request B: browser gửi lại cookie
  -> security filter cung cấp SecurityContext từ repository
  -> controller đọc Authentication qua API giống nhau
```

Controller không cần biết container đang lưu context trong đâu. Với Spring Security 6, `SecurityContextHolderFilter` có thể chuẩn bị deferred context và lưu thay đổi context thường cần được thực hiện tường minh bởi cơ chế xác thực thích hợp; khác với một số cơ chế cũ dùng `SecurityContextPersistenceFilter`.

### 5.2. HTTP Basic stateless

```text
GET /api/me
Authorization: Basic <base64(username:password)>

BasicAuthenticationFilter xác thực credential cho request
  -> SecurityContextHolder có Authentication
  -> AuthorizationFilter kiểm tra truy cập
  -> controller vẫn dùng @CurrentSecurityContext / Principal
```

Với `SessionCreationPolicy.STATELESS`, ứng dụng không dùng HTTP session để lấy/lưu authentication giữa các request. Khi gửi request tiếp theo, client phải chứng minh danh tính lại theo cơ chế yêu cầu, ví dụ header Basic. **HTTPS là bắt buộc trong môi trường thực tế** vì Base64 không phải mã hóa mật khẩu. Basic chỉ dùng ở đây để có ví dụ độc lập và dễ kiểm thử.

### 5.3. Bearer token stateless

```text
GET /api/me
Authorization: Bearer <access-token>

BearerTokenAuthenticationFilter
  -> xác minh token qua cơ chế resource server
  -> tạo Authentication theo cấu hình
  -> đặt vào SecurityContext hiện tại
  -> controller đọc Authentication / principal
```

Ở cả ba luồng, **cách đọc danh tính không đòi hỏi controller truy cập trực tiếp session**. Sự khác nhau nằm ở lúc context được cung cấp, cách credential được xác minh và có hay không việc lưu trạng thái giữa các request.

Không nên suy từ `SessionCreationPolicy.STATELESS` rằng `SecurityContextHolder` sẽ luôn trống: holder vẫn giữ authentication cho **request hiện tại**. Cũng không được suy từ việc nhận thấy cookie rằng user đã được xác thực; cookie có thể hết hạn, không hợp lệ hoặc không được dùng bởi chain đã chọn.

## 6. Ví dụ chạy được: Spring Boot 3 + Java 17, HTTP Basic stateless

Ứng dụng này có một principal `alice` với role `READER`, một endpoint có thể mở cho guest và bốn endpoint chỉ dành cho người dùng đã đăng nhập. Nó minh họa đồng thời API `Principal`, `Authentication` qua `@CurrentSecurityContext`, `@AuthenticationPrincipal UserDetails`, và service dùng `SecurityContextHolder`.

**Điều quan trọng:** ví dụ không gọi `request.getSession()` hay dùng `HttpSession`; policy stateless buộc client gửi credential ở mỗi request. Chỉ dùng HTTP GET nên CSRF mặc định vẫn giữ nguyên mà không gây nhiễu cho bài về danh tính.

### 6.1. Cấu trúc

```text
current-identity/
├── pom.xml
└── src/
    ├── main/java/example/currentidentity/
    │   ├── CurrentIdentityApplication.java
    │   ├── CurrentIdentityService.java
    │   └── IdentityController.java
    └── test/java/example/currentidentity/
        └── CurrentIdentityApplicationTests.java
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
    <artifactId>current-identity</artifactId>
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
```

**`src/main/java/example/currentidentity/CurrentIdentityApplication.java`**:

```java
package example.currentidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class CurrentIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(CurrentIdentityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/optional").permitAll()
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // {noop} CHỈ để bài thực hành có thể chạy ngay.
        // Production phải dùng PasswordEncoder và secret storage phù hợp.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo-pass")
                    .roles("READER")
                    .build());
    }
}
```

Giải thích cấu hình:

- `/api/optional` cho phép anonymous; các URL `/api/**` còn lại yêu cầu đã xác thực; URL khác bị từ chối.
- `httpBasic` bật cơ chế xác thực Basic, `STATELESS` khiến auth của request không phụ thuộc HTTP session.
- Không bật `formLogin` để hành vi unauthenticated API dễ quan sát qua HTTP 401, và không tắt CSRF vì demo chỉ dùng GET.
- Tài khoản dùng `{noop}` và mật khẩu mẫu để học; **không đem tài khoản này ra môi trường thật**.

**`src/main/java/example/currentidentity/CurrentIdentityService.java`**:

```java
package example.currentidentity;

import java.util.Optional;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CurrentIdentityService {
    public Optional<String> currentUsername() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        if (auth == null
                || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken) {
            return Optional.empty();
        }

        return Optional.of(auth.getName());
    }
}
```

Service này không phụ thuộc Spring MVC và không biết user được tạo từ session hay token. Với API dùng loại token riêng hoặc chính sách anonymous khác, có thể triển khai kiểm tra bằng `AuthenticationTrustResolver` và quy tắc chuẩn hóa danh tính ở đây.

**`src/main/java/example/currentidentity/IdentityController.java`**:

```java
package example.currentidentity;

import java.security.Principal;
import java.util.List;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {
    private final CurrentIdentityService currentIdentityService;

    public IdentityController(CurrentIdentityService currentIdentityService) {
        this.currentIdentityService = currentIdentityService;
    }

    public record IdentityView(String username, List<String> authorities) {
    }

    @GetMapping("/api/optional")
    public String optional() {
        return currentIdentityService.currentUsername().orElse("guest");
    }

    @GetMapping("/api/me")
    public IdentityView me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return new IdentityView(authentication.getName(), authorities);
    }

    @GetMapping("/api/principal")
    public String byPrincipal(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/details")
    public String byUserDetails(@AuthenticationPrincipal UserDetails user) {
        return user.getUsername();
    }

    @GetMapping("/api/service")
    public String byService() {
        return currentIdentityService.currentUsername()
                .orElseThrow();
    }
}
```

Giải thích:

- `/api/optional` minh họa một API nhận cả guest và user. Không dùng `auth != null` để xác định login.
- `/api/me` cố ý tạo **DTO nhỏ** chỉ chứa `username` và `authorities`. Không trả nguyên `Authentication` vì nó có thể chứa credential/details/token hoặc thông tin không nên công khai.
- `/api/principal` dùng chuẩn `Principal` và chỉ lấy `getName()`.
- `/api/details` chứng minh `@AuthenticationPrincipal` với `UserDetails` trong **cấu hình Basic của ví dụ**. Không mặc định principal từ JWT/OIDC là `UserDetails`.
- `/api/service` thể hiện tầng service đọc danh tính mà không có `HttpServletRequest`, `HttpSession` hoặc controller truyền username thủ công. Route này đã yêu cầu authenticated; `orElseThrow()` chỉ là phòng vệ phụ, không được xem là chính sách phân quyền.

### 6.2. Kiểm thử thật sự đi qua BasicAuthenticationFilter

Thay vì chỉ gắn principal giả bằng `with(user(...))`, ví dụ kiểm thử dùng `httpBasic(...)` của `spring-security-test` để request có header Basic thật trong MockMvc. Khi đó credentials được security filter xử lý; test thể hiện sự khác biệt giữa **request không credential**, **sai password** và **đúng password**.

**`src/test/java/example/currentidentity/CurrentIdentityApplicationTests.java`**:

```java
package example.currentidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CurrentIdentityApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void optionalEndpointShowsGuest() throws Exception {
        mvc.perform(get("/api/optional"))
                .andExpect(status().isOk())
                .andExpect(content().string("guest"));
    }

    @Test
    void optionalEndpointShowsUserAfterBasicAuthentication()
            throws Exception {
        mvc.perform(get("/api/optional")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void privateEndpointWithoutCredentialsReturns401()
            throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordReturns401() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticationIsAvailableInSecurityContext()
            throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("ROLE_READER"));
    }

    @Test
    void principalArgumentReadsCurrentIdentity()
            throws Exception {
        mvc.perform(get("/api/principal")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void authenticationPrincipalReadsUserDetails()
            throws Exception {
        mvc.perform(get("/api/details")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }

    @Test
    void serviceReadsHolderWithoutHttpSession()
            throws Exception {
        mvc.perform(get("/api/service")
                        .with(httpBasic("alice", "demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));
    }
}
```

Chạy với JDK 17+ và Maven trong thư mục `current-identity`:

```bash
mvn test
mvn spring-boot:run
```

Đây là **tám bài kiểm thử**, với các kết quả HTTP theo cấu hình mẫu:

| Request thử nghiệm | Kết quả mong đợi |
| --- | --- |
| GET `/api/optional` không header Basic | 200, body `guest` |
| GET `/api/optional` Basic đúng | 200, body `alice` |
| GET `/api/me` không Basic | 401 |
| GET `/api/me` Basic sai mật khẩu | 401 |
| GET `/api/me` Basic đúng | 200, JSON có `"username":"alice"` và `"authorities":["ROLE_READER"]` |
| GET `/api/principal` Basic đúng | 200, body `alice` |
| GET `/api/details` Basic đúng | 200, body `alice` |
| GET `/api/service` Basic đúng | 200, body `alice` |

Có thể chạy độc lập khi ứng dụng đã khởi động:

```bash
curl -i http://localhost:8080/api/optional
curl -i http://localhost:8080/api/me
curl -i --user alice:demo-pass http://localhost:8080/api/me
curl -i --user alice:demo-pass http://localhost:8080/api/principal
curl -i --user alice:demo-pass http://localhost:8080/api/details
curl -i --user alice:demo-pass http://localhost:8080/api/service
```

`curl --user` tạo header Basic tương ứng. Dữ liệu ví dụ được thiết kế cho **localhost**; dùng TLS/HTTPS cho môi trường thật. Thứ tự request trong các bài test không được bảo đảm; không dựa vào việc chúng dùng cùng session, và các endpoint authenticated phải tiếp tục yêu cầu credential cho từng request theo cấu hình stateless.

### 6.3. Vì sao ví dụ vẫn có SecurityContext dù không có session?

Khi Basic filter xác thực đúng credentials, nó tạo `Authentication` cho request hiện tại. Các cách đọc trong controller hoặc service sử dụng cùng danh tính đó. Khi request hoàn tất, context gắn với xử lý hiện tại được dọn theo vòng đời filter; request tiếp theo phải gửi Basic credential lại. `SecurityContextHolder` không bị “tắt” bởi `STATELESS`.

Nếu đổi sang form login/session trong một ứng dụng khác, phương thức `byPrincipal` hoặc `currentUsername()` có thể giữ nguyên; điều cần thay đổi thuộc cấu hình xác thực/lưu context, không phải cách gọi `session.getAttribute(...)` trong service.

## 7. Từ username đến định danh nghiệp vụ: phân biệt hai tầng

Tên từ `authentication.getName()` không tự động là **ID cơ sở dữ liệu bất biến**. Với HTTP Basic trong demo, nó là `alice`; với JWT, tên có thể dựa trên subject hoặc claim được cấu hình; với OAuth2/OIDC, tên có thể là giá trị nhà cung cấp định danh trả về.

Khi hệ thống có user ID nội bộ, cách làm an toàn hơn là một trong hai phương án:

1. Tạo principal riêng đã xác thực, ví dụ `AppPrincipal(userId, username, tenantId)`, được xây dựng ở authentication layer; business layer chỉ đọc các trường đã có hợp đồng rõ.
2. Dùng tên/subject đã xác thực làm khóa tra cứu mapping từ identity provider sang tài khoản nội bộ trong service; kiểm tra tenant, trạng thái tài khoản và quyền truy cập tài nguyên.

**Đừng nhận `userId` từ query parameter/body rồi coi đó là user hiện tại.** Ví dụ `GET /api/orders?userId=42` chỉ là input do client gửi, không chứng minh caller chính là user 42. Nếu thao tác “xem đơn hàng của chính tôi”, user ID hiện tại phải lấy qua trusted authentication context hoặc lớp mapping identity; phân quyền object-level vẫn cần kiểm tra chủ sở hữu, tenant và chính sách nghiệp vụ.

Một response DTO nên chỉ xuất những trường cần thiết. Không serialize thẳng `Authentication`, `Principal` tùy biến hoặc token, vì chúng có thể chứa credentials, provider attributes, internal claims, session details hoặc dữ liệu riêng tư.

## 8. Principal khác nhau theo cơ chế xác thực

### 8.1. `UserDetails`

Trong ứng dụng sử dụng `DaoAuthenticationProvider`, `Authentication.getPrincipal()` thường là `UserDetails`. Có thể lấy username, trạng thái account và các thuộc tính tùy chỉnh. Dù vậy, `UserDetails` không phải giao diện chung của mọi loại authentication.

### 8.2. JWT Resource Server

Trong Spring Security Resource Server dùng JWT, principal có thể là `org.springframework.security.oauth2.jwt.Jwt`, và authentication thường là `JwtAuthenticationToken`. Trong controller của **ứng dụng đã cấu hình Resource Server**:

```java
@GetMapping("/api/jwt-subject")
public String jwtSubject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
```

Đây chỉ là **method minh họa**; nó yêu cầu dependency/configuration OAuth2 Resource Server và JWT decoder phù hợp, **không phải endpoint có thể chạy trong project HTTP Basic ở mục 6**. `getSubject()` trả claim `sub`, không nhất thiết tương đương ID account nội bộ. `Authentication.getName()` cũng có thể được cấu hình lấy từ claim khác.

Nếu muốn tránh mọi phụ thuộc trực tiếp vào format token, chỉ dùng `Authentication.getName()` khi ứng dụng đã chuẩn hóa ý nghĩa tên đó; logic mapping subject → user ID nên ở service riêng.

### 8.3. OAuth2/OIDC login

Với OAuth2/OIDC login, principal có thể là `OAuth2User` hoặc `OidcUser`. Claims/attributes cần được đọc theo đúng hợp đồng provider và mapping đã xác minh; email là dữ liệu có thể thay đổi và không nên mặc định làm primary key bất biến. Controller phục vụ người dùng có thể dùng một `CurrentIdentity` abstraction để cả session login và API Bearer có cùng cách truy vấn “user nội bộ hiện tại”.

### 8.4. Anonymous và remember-me

Anonymous authentication có thể được Spring Security đặt vào context để nhiều thành phần xử lý thống nhất. Remember-me cũng có thể phục hồi danh tính với mức bảo đảm khác login trực tiếp. Nếu thao tác yêu cầu **fresh login / full authentication**, không được chỉ xem `Authentication.getName()`; hãy dùng chính sách như `fullyAuthenticated()` và các yêu cầu xác thực bổ sung thích hợp.

## 9. Thread, async và phạm vi an toàn của SecurityContextHolder

Trên Servlet stack, `SecurityContextHolder` mặc định dùng `ThreadLocal`. Khi code xử lý ngay trong request/filter chain, đọc holder là hợp lý. Nhưng request có thể chuyển thread khi dùng `@Async`, `CompletableFuture`, thread pool hoặc xử lý Servlet bất đồng bộ.

```java
// Chỉ minh họa vấn đề; KHÔNG có bảo đảm tự truyền context:
CompletableFuture.supplyAsync(() ->
        SecurityContextHolder.getContext().getAuthentication());
```

Trong một thread chạy từ executor, kết quả có thể là `null` hoặc context không tương ứng nếu quản lý thread/context sai. Đừng sửa bằng cách đặt toàn cục `MODE_INHERITABLETHREADLOCAL` rồi tưởng sẽ an toàn cho mọi thread pool. Spring Security cung cấp các wrapper như `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor` để truyền/bọc context theo chính sách; Spring MVC có tích hợp cho một số luồng async như `Callable`, nhưng không suy rộng sang tất cả executor.

**Hai chiến lược cần cân nhắc:**

- Nếu tác vụ bất đồng bộ cần thực thi với quyền của user hiện tại, dùng cơ chế propagate security context chính thức và bảo đảm context được phục hồi/dọn đúng thời điểm.
- Nếu tác vụ nền chỉ cần ID người đã kích hoạt nghiệp vụ, chuyển một **ID đã được xác thực và kiểm tra quyền** vào command/event với ý nghĩa audit rõ ràng. Không giữ nguyên tham chiếu request/session hoặc mang credential nhạy cảm vào queue chỉ vì tiện.

Cũng không nên đọc holder tại thời điểm ứng dụng khởi động hoặc trong bean constructor rồi lưu vào singleton field. Danh tính là **thuộc tính của ngữ cảnh thực thi hiện tại**, không phải trạng thái toàn cục gắn vĩnh viễn với một service instance.

## 10. Những lỗi thường gặp khi tích hợp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `getAuthentication()` trả null | Request chưa qua chain phù hợp; context chưa được cung cấp; thread khác. | Kiểm tra security chain, phase xử lý, thread và dispatcher type. |
| `getName()` trả `anonymousUser` | Endpoint công khai và anonymous filter đã cung cấp principal giả danh. | Kiểm tra anonymous bằng cơ chế phù hợp trước khi gọi là user đăng nhập. |
| `@AuthenticationPrincipal UserDetails` trả null | Principal thực tế là `Jwt`, `OidcUser` hoặc custom type. | Kiểm tra authentication class và principal class trong môi trường phát triển. |
| Browser có cookie nhưng controller vẫn thấy guest | Cookie không hợp lệ/hết hạn hoặc chain không dùng session. | Đọc cấu hình SecurityContextRepository, session policy, authentication filter. |
| API dùng Bearer nhưng code gọi `session.getAttribute("user")` trả null | Ứng dụng đang gắn nghiệp vụ với session trong khi auth stateless. | Thay bằng API đọc `SecurityContext` / principal; mapping danh tính rõ ràng. |
| Request sau login không thấy context | Context chưa được lưu đúng repository; cookie không gửi lại; session policy khác. | Kiểm tra cơ chế lưu context và response/login flow. |
| Danh tính mất trong `@Async` | `ThreadLocal` không tự truyền cho thread của executor. | Dùng context propagation được hỗ trợ hoặc truyền ID đã xác thực. |
| User đã login nhưng xem được dữ liệu người khác | Controller đọc identity đúng, nhưng không kiểm tra quyền trên resource. | Bổ sung object-level authorization; không dùng tên user để thay thế authorization. |
| Endpoint trả JSON chứa credentials | Serialize nguyên `Authentication` hoặc principal. | Dùng DTO chỉ chứa trường cần xuất, không log token/secrets. |
| Multiple `SecurityFilterChain` cho kết quả khác dự kiến | Chain đầu tiên khớp có session/policy khác. | Kiểm tra `securityMatcher`, thứ tự chain và filter của chain thực sự chạy. |

### Quy trình debug ngắn

1. Xác định method, URL, dispatcher type, chain khớp và cơ chế xác thực thực tế; không in credentials/token đầy đủ.
2. Kiểm tra authentication ở đúng **vị trí request sau security filter**, khác với đọc holder trước filter.
3. Phân biệt `null`, `AnonymousAuthenticationToken`, principal đã xác thực và những authentication type riêng.
4. Kiểm tra `getName()` có đúng ý nghĩa hợp đồng hay không; nếu cần ID nội bộ, xem lớp mapping.
5. Nếu request sau mất login, xem session policy, `SecurityContextRepository` và việc client gửi lại credential.
6. Nếu tác vụ async không thấy identity, kiểm tra propagation hoặc dữ liệu immutable được chuyển vào tác vụ.
7. Với lỗi quyền, tách authentication (ai) khỏi authorization (được làm gì); bổ sung integration test cho guest, user thường, user thiếu quyền.

## 11. Câu hỏi tự kiểm tra

**1.** Vì sao không nên lấy danh tính bằng `session.getAttribute("username")` trong service?  
Vì service sẽ phụ thuộc tên attribute/cơ chế session cụ thể và không hoạt động tương đương với Basic, Bearer hoặc cơ chế xác thực khác. Spring Security đã cung cấp `Authentication` cho request.

**2.** Endpoint chỉ cần username nên dùng API gì?  
Có thể dùng `Principal#getName()` hoặc `Authentication#getName()` trong controller; `@CurrentSecurityContext` giúp lấy rõ ràng từ context.

**3.** `auth != null && auth.isAuthenticated()` có chắc là người dùng đăng nhập không?  
Không. `AnonymousAuthenticationToken` có thể trả authenticated=true; cần đánh giá anonymous/trust level bằng cơ chế phù hợp.

**4.** `SessionCreationPolicy.STATELESS` có làm `SecurityContextHolder` vô dụng không?  
Không. Context vẫn mang authentication cho request hiện tại; chỉ không dựa vào session để duy trì trạng thái xác thực giữa các request.

**5.** Có nên dùng `@AuthenticationPrincipal UserDetails` cho mọi JWT endpoint không?  
Không. JWT Resource Server có thể dùng `Jwt` làm principal; phải chọn đúng type hoặc chuẩn hóa identity trong service.

**6.** Tại sao `Authentication.getName()` chưa chắc là user ID trong database?  
Vì tên phụ thuộc loại authentication, claim mapping hoặc identity provider. User ID nội bộ cần hợp đồng/mapping riêng.

**7.** Một method đọc đúng user hiện tại đã đủ bảo vệ `GET /orders/{id}` chưa?  
Chưa. Phải kiểm tra user có quyền xem order đó (owner/tenant/policy) tại service/resource layer.

**8.** Tại sao context có thể mất khi dùng `CompletableFuture.supplyAsync()`?  
Vì holder mặc định gắn với thread, còn task có thể chạy trên thread khác; cần context propagation hoặc truyền ID đã xác thực một cách chủ đích.

**9.** Nên trả nguyên `Authentication` qua JSON để frontend tự lấy email, roles và token không?  
Không. Trả DTO tối thiểu và tránh lộ credentials, claims hoặc các thuộc tính bảo mật không cần thiết.

**10.** `Principal`, `@AuthenticationPrincipal`, `SecurityContextHolder` khác nhau chủ yếu thế nào?  
`Principal` cho interface chung của người dùng hiện tại; `@AuthenticationPrincipal` lấy object principal theo type; `SecurityContextHolder` đọc authentication/context từ bất cứ code nào ở đúng ngữ cảnh thực thi. Cả ba không đòi hỏi truy cập trực tiếp HTTP session.

**Điểm cần nhớ:** đọc danh tính từ **nguồn mà Spring Security đã xác thực**. Hãy để security filter/repository quyết định cách cung cấp context; controller/service chỉ tiêu thụ một API danh tính có hợp đồng rõ, xử lý anonymous, giới hạn dữ liệu trả về và luôn phân quyền riêng cho tài nguyên.