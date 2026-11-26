# Authentication, principal, authorities và SecurityContext trong một ca kiểm thử

## Mục tiêu học tập

Trong Spring Security, câu “test đã đăng nhập với người dùng `linh`” vẫn chưa nói rõ test đã chuẩn bị những gì: một tên đăng nhập, một principal Java, tập quyền `GrantedAuthority`, một `Authentication` hay toàn bộ `SecurityContext`? Hiểu nhầm các thành phần này có thể khiến test trả `200` hoặc `403` đúng như mong đợi nhưng không đi qua cơ chế bảo mật cần kiểm tra.

Sau bài học, bạn có thể:

- Phân biệt đối tượng `Authentication` với principal, credentials, details và authorities của nó.
- Giải thích `SecurityContext` lưu gì, `SecurityContextHolder` phục vụ request Servlet thế nào, và Reactor context đóng vai trò gì trong WebFlux.
- Dùng `@WithMockUser`, `@WithUserDetails`, `user()` và `@WithSecurityContext` để tạo đúng danh tính cho bài kiểm thử.
- Đọc các kiểm tra `hasRole`, `hasAuthority`, `isAuthenticated`, `@AuthenticationPrincipal` và hiểu vì sao principal mock có thể khác principal thực.
- Kiểm chứng mô hình này qua `MockMvc` trong Servlet và `WebTestClient` trong Reactive, bao gồm principal JWT/OAuth2/OIDC giả lập.
- Viết ca kiểm thử chứng minh **ai được phép** và **ai bị từ chối** với cùng một chính sách.

Bài thuộc phần **Tổng quan** của module **SPRING_SECURITY_TESTING**, tập trung vào xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` cho ứng dụng Servlet và Reactive. Nội dung dùng Spring Security hiện đại với Java 17+ và lối cấu hình theo `SecurityFilterChain`/`SecurityWebFilterChain`.

## 1. Mô hình cốt lõi: bốn khái niệm liên quan nhưng khác nhau

Giả sử một request gửi tới `GET /api/admin/report`. Server cần biết request đó đại diện cho người nào và người đó có `ROLE_ADMIN` hay không.

Spring Security thường lưu kết quả xác thực theo mô hình sau:

~~~mermaid
flowchart TD
    SC["SecurityContext"] --> A["Authentication"]
    A --> P["principal<br/>Danh tính: UserDetails / Jwt / OidcUser / đối tượng tùy biến"]
    A --> C["credentials<br/>Bằng chứng xác thực, có thể đã bị xóa"]
    A --> AU["authorities<br/>Collection&lt;GrantedAuthority&gt;"]
    A --> D["details<br/>Thông tin bổ sung của request"]
    A --> S["isAuthenticated<br/>Trạng thái trên đối tượng token"]
    AU --> R1["ROLE_ADMIN"]
    AU --> R2["SCOPE_reports.read"]
    AU --> R3["orders:read"]
~~~

Diễn giải từng thành phần:

| Thành phần | Vai trò | Điều test nên kiểm tra |
| --- | --- | --- |
| `SecurityContext` | Chứa `Authentication` gắn với ngữ cảnh bảo mật hiện tại. | Context có đúng authentication cần thiết không? |
| `Authentication` | Đối tượng biểu diễn thông tin xác thực: danh tính, quyền, trạng thái và dữ liệu liên quan. | `getName()`, principal, authorities và loại authentication có đúng không? |
| `principal` | Đối tượng đại diện cho thực thể đang được nhận diện. | Principal có đúng kiểu và đúng mã tài khoản/claims cần dùng không? |
| `GrantedAuthority` | Một quyền cụ thể được gán cho authentication. | Có chính xác `ROLE_ADMIN` hoặc `SCOPE_reports.read` theo chính sách không? |

### 1.1. Authentication là đối tượng bao ngoài danh tính

Giao diện `org.springframework.security.core.Authentication` định nghĩa các thông tin quan trọng:

~~~java
Authentication authentication = ...;

Object principal = authentication.getPrincipal();
Object credentials = authentication.getCredentials();
Object details = authentication.getDetails();
Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();

String name = authentication.getName();
boolean authenticated = authentication.isAuthenticated();
~~~

`Authentication` còn kế thừa `java.security.Principal`, nhưng **principal nằm bên trong Authentication** có thể là đối tượng thuộc kiểu hoàn toàn khác. Ví dụ:

- Trong một luồng username/password, `Authentication` có thể là `UsernamePasswordAuthenticationToken`, còn principal là một `UserDetails`.
- Với resource server JWT, `Authentication` thường là `JwtAuthenticationToken`, principal là đối tượng `Jwt` chứa claims.
- Với đăng nhập OIDC, principal thường triển khai `OidcUser`, cung cấp thông tin từ ID token và có thể cả UserInfo.
- Với anonymous authentication, principal có thể chỉ là một chuỗi như `anonymousUser`.

**Không nên suy ra kiểu của `getPrincipal()` chỉ từ `getName()`.** Hai authentication khác loại có thể cùng có tên `linh` nhưng principal và authorities rất khác nhau.

### 1.2. getName() và getPrincipal() không nhất thiết tương đương

`authentication.getName()` cung cấp một tên biểu diễn danh tính theo cách loại authentication cụ thể xác định. Một số ví dụ:

| Loại authentication thường gặp | Principal điển hình | Giá trị tên thường gặp |
| --- | --- | --- |
| `UsernamePasswordAuthenticationToken` | `UserDetails` hoặc đối tượng người dùng tùy biến | `getUsername()` nếu principal là `UserDetails`. |
| `JwtAuthenticationToken` | `Jwt` | Claim `sub` theo cấu hình chuẩn; có thể tùy biến. |
| `OAuth2AuthenticationToken` | `OAuth2User` / `OidcUser` | Thuộc tính tên được cấu hình cho OAuth2/OIDC principal. |
| `AnonymousAuthenticationToken` | Thường là chuỗi | Tên biểu diễn anonymous principal. |

Điều này tác động trực tiếp đến controller sử dụng `@AuthenticationPrincipal`. Một tham số kiểu `UserDetails` không tự trở thành kiểu principal của JWT, và một principal do dự án tự định nghĩa không tự được tạo khi chỉ viết `@WithMockUser`.

### 1.3. Credentials và details không phải authorities

`getCredentials()` có thể chứa mật khẩu, token hoặc dữ liệu chứng minh danh tính trong giai đoạn xác thực. Sau khi xác thực thành công, một authentication provider có thể xóa credentials để hạn chế giữ bí mật trong bộ nhớ. Vì vậy, test phân quyền không nên phụ thuộc vào việc credentials còn nguyên.

`getDetails()` thường chứa metadata liên quan request (ví dụ remote address hoặc session id trong một số luồng), nhưng **không đại diện cho quyền**. Các quyết định như `hasRole("ADMIN")` thông thường xét `GrantedAuthority` của authentication, không xét credentials hay details.

## 2. Authorities: đơn vị Spring Security dùng để quyết định quyền

Một `GrantedAuthority` thường có một chuỗi từ `getAuthority()`. Ví dụ:

~~~text
ROLE_USER
ROLE_ADMIN
SCOPE_reports.read
orders:approve
tenant:42:read
~~~

Spring Security không ép ứng dụng phải sử dụng một danh sách quyền cố định. Các chuỗi có ý nghĩa theo quy tắc mà ứng dụng cấu hình.

### 2.1. Role là một quy ước trên authorities

Trong cấu hình mặc định, `hasRole("ADMIN")` kiểm tra sự hiện diện của authority `ROLE_ADMIN`. Ngược lại, `hasAuthority("ADMIN")` kiểm tra đúng chuỗi `ADMIN`, trừ khi ứng dụng có cơ chế quy đổi riêng.

| Cách tạo/kiểm tra | Authority liên quan |
| --- | --- |
| `@WithMockUser(roles = "ADMIN")` | Tạo `ROLE_ADMIN`. |
| `user("mai").roles("ADMIN")` | Tạo `ROLE_ADMIN`. |
| `@WithMockUser(authorities = "ADMIN")` | Tạo chính xác `ADMIN`. |
| `@WithMockUser(authorities = "SCOPE_reports.read")` | Tạo chính xác `SCOPE_reports.read`. |
| `hasRole("ADMIN")` | Thường yêu cầu `ROLE_ADMIN`. |
| `hasAuthority("SCOPE_reports.read")` | Yêu cầu `SCOPE_reports.read`. |

Trong `@WithMockUser`, thuộc tính `roles` và `authorities` được sử dụng theo hai cách riêng; khi chỉ định authorities tùy ý, nên dùng `authorities` thay vì cố biến scope thành role.

### 2.2. Vì sao scope trong JWT cần kiểm tra riêng?

Ở resource server, các scope từ JWT có thể được ánh xạ sang các authority như `SCOPE_reports.read`. Việc ánh xạ phụ thuộc `JwtAuthenticationConverter` và bộ chuyển đổi authorities thực tế của ứng dụng.

Giả sử endpoint bảo vệ bởi:

~~~java
.requestMatchers("/api/reports/**")
    .hasAuthority("SCOPE_reports.read")
~~~

Một test sử dụng `jwt().authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))` đang **cấp sẵn authority**. Nó kiểm tra quyết định phân quyền theo authority đó, nhưng không chứng minh converter có thể trích scope từ JWT thật một cách chính xác.

Muốn kiểm tra converter, cần test riêng sử dụng claims đầu vào và converter thực, hoặc kiểm thử tích hợp đi qua đường xác thực JWT thật. Phân tách hai mục tiêu này giúp chẩn đoán lỗi: sai **cấp quyền** hay sai **ánh xạ claims**.

## 3. SecurityContext: nơi chứa Authentication trong vòng đời xử lý

Về mặt khái niệm, `SecurityContext` đơn giản là nơi chứa `Authentication` đang có hiệu lực:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
~~~

Tuy nhiên, **cách ngữ cảnh được truyền qua luồng xử lý** phụ thuộc mô hình ứng dụng.

### 3.1. Servlet: SecurityContextHolder và ThreadLocal

Trong ứng dụng Servlet, các filter của Spring Security thiết lập và dọn dẹp ngữ cảnh bảo mật cho request. Với chiến lược mặc định, `SecurityContextHolder` lưu ngữ cảnh theo `ThreadLocal`, để code chạy trong luồng xử lý request có thể gọi:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Các điểm cần lưu ý:

1. Ngữ cảnh của request này không nên tự động bị xem là ngữ cảnh của request khác.
2. Spring Security quản lý dọn dẹp ngữ cảnh sau request; test không nên kỳ vọng `SecurityContextHolder` vẫn chứa authentication của request sau khi `MockMvc.perform(...)` đã hoàn tất.
3. Nếu code chuyển sang một thread khác bằng executor hoặc `@Async`, `ThreadLocal` không tự bảo đảm truyền đúng authentication. Ứng dụng cần dùng cơ chế truyền ngữ cảnh phù hợp.
4. `SecurityContext` trong một request không đồng nghĩa với **đã lưu session**. Muốn chứng minh session login/persistence, phải viết kiểm thử vòng đời phiên riêng.

### 3.2. Reactive: Reactor context thay cho ThreadLocal

Trong WebFlux, request có thể chuyển qua nhiều thread trong quá trình thực thi `Mono`/`Flux`. Spring Security truyền ngữ cảnh bằng Reactor context, và API truy cập là:

~~~java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
~~~

Không nên lấy `SecurityContextHolder.getContext()` bên trong một reactive pipeline rồi giả định đó là người dùng hiện tại. Trong Reactive, việc lấy authentication phải gắn với **subscription** và Reactor context đúng của request.

### 3.3. Test listener thiết lập và dọn ngữ cảnh

Khi dùng `@WithMockUser`, Spring Security Test phối hợp với Spring Test để tạo một `SecurityContext` trước khi test chạy và dọn nó sau test. Điều này giúp các test tránh rò rỉ danh tính sang nhau, miễn là bạn không tự tạo cơ chế lưu context toàn cục hoặc giữ reference không đúng cách.

Nếu bạn tự đặt authentication bằng `SecurityContextHolder.setContext(...)` trong một bài test đơn lẻ, cần chủ động hoàn nguyên hoặc dọn context trong `finally`/cleanup để tránh ảnh hưởng đến test khác. Với phần lớn test, nên ưu tiên annotation hoặc request post processor vì vòng đời đã được framework quản lý.

## 4. Ví dụ Servlet tự chứa: quan sát principal và authorities

### 4.1. Cấu hình một ứng dụng Spring MVC nhỏ

Ví dụ sau định nghĩa hai API: một endpoint để **quan sát** authentication hiện tại trong môi trường học tập và một endpoint chỉ dành cho quản trị viên.

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Configuration
class LessonSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class IdentityController {

    @GetMapping("/api/identity")
    Map<String, Object> identity(Authentication authentication) {
        return Map.of(
            "name", authentication.getName(),
            "principalType",
                authentication.getPrincipal().getClass().getSimpleName(),
            "authorities", authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList()
        );
    }

    @GetMapping("/api/admin/report")
    ResponseEntity<String> adminReport() {
        return ResponseEntity.ok("secret-report");
    }
}
~~~

Mã này giả định có một ứng dụng Spring Boot MVC đã nạp hai lớp trên vào application context. Endpoint `/api/identity` cố ý trả kiểu principal và authorities để người học quan sát cấu trúc; trên hệ thống production, không nên tự động công khai metadata bảo mật nội bộ nếu sản phẩm không có nhu cầu rõ ràng.

Các bài test dưới đây dùng `spring-security-test` và hai dependency kiểm thử quen thuộc:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Để xác minh cấu hình Servlet, dùng `@SpringBootTest` và `@AutoConfigureMockMvc`. Spring Boot thường đưa các security filter của context vào `MockMvc`. Nếu bạn tự tạo `MockMvc` bằng `MockMvcBuilders.webAppContextSetup(context)`, hãy áp dụng `.apply(springSecurity())` để tích hợp cơ chế kiểm thử bảo mật đúng cách.

### 4.2. @WithMockUser gắn Authentication cho phương thức test

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "linh", roles = "USER")
    void mockUserHasExpectedNameAndRole() throws Exception {
        mvc.perform(get("/api/identity"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("linh"))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"));
    }

    @Test
    @WithMockUser(username = "linh", roles = "USER")
    void userCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "mai", roles = "ADMIN")
    void adminCanReadAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk())
            .andExpect(content().string("secret-report"));
    }

    @Test
    void anonymousRequestNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/identity"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Test đầu tiên chứng minh những giá trị mà endpoint nhìn thấy sau khi Spring Security xử lý request. Hai test tiếp theo tạo cặp **không có quyền/có quyền** cho `ROLE_ADMIN`. Test cuối thể hiện hành vi chưa xác thực với HTTP Basic; nếu thay bằng form login, kết quả có thể là chuyển hướng đến trang đăng nhập.

`@WithMockUser` mặc định tạo principal dạng `org.springframework.security.core.userdetails.User` với các authorities phù hợp annotation. Nó không tải người dùng từ database hay xác minh mật khẩu. Khi không khai báo tham số, annotation dùng người dùng mock mặc định tên `user` và role `USER`.

### 4.3. Kiểm tra trực tiếp SecurityContext trong ca test

Đôi khi mục tiêu không phải endpoint mà là **hợp đồng của ngữ cảnh** dùng trong service. Ta có thể kiểm tra trực tiếp authentication do annotation tạo:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AuthenticationContextTest {

    @Test
    @WithMockUser(
        username = "linh",
        authorities = {"orders:read", "orders:write"}
    )
    void annotationInstallsExpectedAuthentication() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertThat(authentication).isNotNull();
        assertThat(authentication.isAuthenticated()).isTrue();
        assertThat(authentication.getName()).isEqualTo("linh");
        assertThat(authentication.getPrincipal())
            .isInstanceOf(UserDetails.class);
        assertThat(authentication.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .containsExactlyInAnyOrder("orders:read", "orders:write");
    }
}
~~~

Ví dụ giả định lớp test chạy với Spring Test context/JUnit integration có `WithSecurityContextTestExecutionListener`, như khi dùng `@SpringBootTest`. **Với test Java thuần không chạy Spring Test listener**, annotation `@WithMockUser` sẽ không tự thiết lập context. Khi mang ví dụ này vào dự án, có thể bổ sung `@SpringBootTest` hoặc một cấu hình Spring Test tương ứng.

Test trực tiếp này chứng minh annotation tạo dữ liệu như kỳ vọng; nó **chưa** chứng minh `SecurityFilterChain` của endpoint thực sự áp dụng chính sách. Vì vậy, vẫn cần test `MockMvc` cho rule bảo mật URL.

### 4.4. Tạo danh tính cho riêng một request bằng user()

Trong các ca cần nhiều danh tính trong cùng một phương thức test, request post processor tiện hơn annotation:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;

// Mỗi perform có danh tính riêng trong request.
mvc.perform(get("/api/identity")
        .with(user("linh").roles("USER")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.name").value("linh"));

mvc.perform(get("/api/identity")
        .with(user("mai").authorities(
            new SimpleGrantedAuthority("reports:read"))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.authorities[0]").value("reports:read"));
~~~

Khi soạn class thực tế, import `SimpleGrantedAuthority` từ `org.springframework.security.core.authority`. Trái với `@WithMockUser` định nghĩa context cho phương thức, `.with(user(...))` cung cấp danh tính cho **request cụ thể**.

Tương tự, request processor `authentication(customAuthentication)` hoặc `securityContext(customContext)` hữu ích nếu bạn đã tạo sẵn đối tượng bảo mật cần kiểm tra. Chúng phải được sử dụng với tích hợp Spring Security Test và filter chain thích hợp.

## 5. Principal tùy biến: khi @WithMockUser không đủ

Nhiều ứng dụng có principal riêng chứa `accountId`, `tenantId` hoặc một mã định danh nghiệp vụ. Ví dụ controller có thể dựa vào principal tùy biến:

~~~java
record AccountPrincipal(String accountId, String email) {}
~~~

Nếu service/controller kỳ vọng `AccountPrincipal` mà test chỉ dùng `@WithMockUser`, principal nhận được mặc định là `UserDetails` và không thể ép kiểu thành `AccountPrincipal`. Với `@AuthenticationPrincipal AccountPrincipal principal`, tham số có thể không được resolve như mong muốn khi kiểu thực tế không tương thích.

### 5.1. @WithUserDetails: lấy principal từ UserDetailsService

Khi ứng dụng có `UserDetailsService` sử dụng một kiểu `UserDetails` tùy biến, có thể dùng:

~~~java
@Test
@WithUserDetails("linh")
void loadsPrincipalFromUserDetailsService() {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    // Principal phản ánh UserDetails do service trong test context trả về.
}
~~~

Cần import `org.springframework.security.test.context.support.WithUserDetails` và chạy trong Spring Test context có `UserDetailsService`. Annotation gọi `loadUserByUsername("linh")` để thiết lập ngữ cảnh test. Đây vẫn là một cách **chuẩn bị danh tính đã xác thực**; nó không thực hiện kiểm tra mật khẩu như một request login thực tế.

Nếu dự án không dùng `UserDetailsService`, hoặc principal không triển khai giao diện này, nên tạo annotation với factory riêng.

### 5.2. @WithSecurityContext tạo Authentication theo mô hình nghiệp vụ

Ví dụ annotation `@WithAccount` tạo principal có mã tài khoản nhất quán:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithSecurityContext;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

record AccountPrincipal(String accountId, String email) {}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD, ElementType.TYPE})
@WithSecurityContext(factory = WithAccountFactory.class)
@interface WithAccount {
    String accountId() default "acc-101";
}

class WithAccountFactory
        implements WithSecurityContextFactory<WithAccount> {

    @Override
    public SecurityContext createSecurityContext(WithAccount annotation) {
        AccountPrincipal principal = new AccountPrincipal(
            annotation.accountId(), "linh@example.test");

        var authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                principal,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
~~~

Sau đó kiểm tra:

~~~java
@Test
@WithAccount(accountId = "acc-202")
void customPrincipalContainsAccountId() {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    assertThat(authentication.getPrincipal())
        .isInstanceOf(AccountPrincipal.class);

    AccountPrincipal principal =
        (AccountPrincipal) authentication.getPrincipal();

    assertThat(principal.accountId()).isEqualTo("acc-202");
    assertThat(authentication.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .contains("ROLE_USER");
}
~~~

Trong ví dụ trên, test phải chạy cùng Spring Test listener như mục 4.3. Đặt lớp principal, annotation và factory ở phạm vi test hoặc module hỗ trợ test để không phải đưa một cơ chế giả lập vào mã nghiệp vụ production.

**Hai lưu ý khi tạo custom authentication:**

1. Dùng factory/constructor phù hợp để biểu diễn trạng thái đã xác thực một cách chủ đích. Không tự đặt `authenticated = true` cho credential chưa được xác minh trong mã production.
2. Nếu business rule đọc `tenantId`, `accountId` hoặc thuộc tính khác, nên kiểm tra cả quyền theo **đối tượng** bằng dữ liệu khác nhau. Chỉ có `ROLE_USER` không chứng minh người dùng được phép xem tài nguyên của người khác.

## 6. Phân biệt người dùng vô danh với một Authentication đã đăng nhập

Một lỗi thường gặp là suy diễn rằng `SecurityContextHolder.getContext().getAuthentication() != null` đồng nghĩa “đã đăng nhập”. Trong Spring Security, cơ chế anonymous authentication có thể đặt một đối tượng `AnonymousAuthenticationToken` vào context cho request chưa đăng nhập.

Đặc biệt, `AnonymousAuthenticationToken.isAuthenticated()` có thể trả về `true` theo trạng thái của token, nhưng Spring Security vẫn phân loại nó là **anonymous**, không phải người dùng được xác thực theo chính sách `authenticated()`.

Để phân biệt, Spring Security sử dụng cơ chế nhận diện anonymous/trust resolver trong các biểu thức bảo mật. Ở mức test, nên kiểm tra hành vi của endpoint hoặc biểu thức `authenticated()`/`anonymous()` thay vì tự viết một điều kiện `authentication != null && authentication.isAuthenticated()` rồi coi đó là hợp đồng bảo mật đầy đủ.

Spring Security Test cung cấp `@WithAnonymousUser` cho những bài test cần ngữ cảnh anonymous rõ ràng:

~~~java
@Test
@WithAnonymousUser
void explicitAnonymousCannotReadProtectedEndpoint() throws Exception {
    mvc.perform(get("/api/identity"))
        .andExpect(status().isUnauthorized());
}
~~~

Import từ `org.springframework.security.test.context.support.WithAnonymousUser`. Trong ứng dụng HTTP Basic minh họa, endpoint bảo vệ có phản hồi `401` cho anonymous; form login có thể trả redirect theo cấu hình.

## 7. JWT, OAuth2 và OIDC: principal cùng kiểu nghiệp vụ có thể đến từ nhiều cơ chế

Bốn thành phần đã học vẫn tồn tại khi ứng dụng không dùng username/password:

~~~mermaid
flowchart LR
    J["JWT bearer token"] --> JA["JwtAuthenticationToken"]
    O["OAuth2 login"] --> OA["OAuth2AuthenticationToken"]
    I["OIDC login"] --> IA["OAuth2AuthenticationToken với OidcUser"]
    JA --> SC["SecurityContext / authentication"]
    OA --> SC
    IA --> SC
    SC --> AZ["Authorizations theo authorities/claims"]
~~~

### 7.1. JWT mock với MockMvc

Giả sử API đọc thông tin người dùng dựa vào `Authentication` như ở mục 4. Bạn có thể gắn JWT authentication đã được giả lập:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

@Test
void jwtPrincipalHasSubjectAndAuthority() throws Exception {
    mvc.perform(get("/api/identity")
            .with(jwt()
                .jwt(token -> token.subject("account-42"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_profile.read"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("account-42"))
        .andExpect(jsonPath("$.authorities[0]")
            .value("SCOPE_profile.read"));
}
~~~

Đây là một **ca test mô hình danh tính và phân quyền**. Nó không gửi chuỗi JWT tới decoder để kiểm tra chữ ký, thời hạn hay issuer. Khi chỉ định `.authorities(...)`, bạn cũng đã đặt sẵn danh sách quyền; test chưa kiểm chứng thuật toán ánh xạ scope claims sang authorities.

Để kiểm chứng việc server từ chối token bị sửa chữ ký hoặc hết hạn, phải gửi header `Authorization: Bearer ...` qua filter xác thực của resource server với `JwtDecoder`/validator phù hợp trong test context. Nếu decoder bị mock để “ném lỗi”, test chỉ xác minh cách filter xử lý lỗi giả lập, không chứng minh phép kiểm tra chữ ký mật mã thực sự đúng.

### 7.2. OAuth2/OIDC mock cho các principal khác kiểu

Trong Servlet, Spring Security Test cung cấp:

- `oauth2Login()`: mô phỏng một phiên xác thực OAuth2 login thành công, với `OAuth2User` và các authorities.
- `oidcLogin()`: mô phỏng người dùng đã đăng nhập OpenID Connect, với `OidcUser` và thông tin định danh.
- `opaqueToken()`: mô phỏng thông tin xác thực từ opaque bearer token đã được chấp nhận.
- `oauth2Client()`: hỗ trợ kiểm thử tình huống ứng dụng có authorized OAuth2 client.

Điểm cần nhận biết: `@AuthenticationPrincipal Jwt jwt` và `@AuthenticationPrincipal OidcUser user` là hai kiểu tham số khác nhau. Để kiểm tra logic phụ thuộc thuộc tính OIDC, dùng principal OIDC giả lập đúng kiểu; với resource server JWT, dùng principal JWT phù hợp.

Các mock nói trên **không chạy trọn vẹn** authorization code flow, chuyển hướng trình duyệt, callback, nonce/state validation hoặc xác minh token ở identity provider. Nếu ứng dụng thực hiện những bước đó, cần test tích hợp riêng.

### 7.3. Nhìn cùng một người qua các loại Authentication

Một người dùng có thể xuất hiện dưới các dạng sau:

| Luồng | `authentication.getName()` | Principal | Authority thử nghiệm |
| --- | --- | --- | --- |
| `@WithMockUser(username = "linh")` | `linh` | `UserDetails` mặc định | `ROLE_USER` |
| `@WithUserDetails("linh")` | Theo `UserDetailsService` | `UserDetails` do ứng dụng trả về | Theo dữ liệu người dùng. |
| `jwt()` với `sub = "account-42"` | Thường là `account-42` | `Jwt` | Scope/authority được giả lập. |
| `oidcLogin()` | Theo principal OIDC mock | `OidcUser` | OIDC/OAuth2 authorities được giả lập. |
| `@WithAccount(accountId = "acc-202")` | Phụ thuộc `getName()` của authentication tùy biến | `AccountPrincipal` | `ROLE_USER` theo factory. |

Nếu ứng dụng phụ thuộc một định danh ổn định như `accountId`, hãy xác định rõ cách lấy nó từ principal/claims cho từng cơ chế đăng nhập. `getName()` có thể thích hợp với một ứng dụng nhưng không đủ để làm khóa định danh xuyên các identity provider.

## 8. Reactive/WebFlux: đưa Authentication vào Reactor context

Trong WebFlux, một danh tính giả lập không được đặt đúng Reactor context có thể “biến mất” khi chuỗi xử lý đổi thread. Spring Security Test cung cấp các configurer dành cho `WebTestClient` để tránh tự thiết lập `ThreadLocal`.

### 8.1. Một handler đọc ngữ cảnh Reactive

Trong một ứng dụng WebFlux **riêng** với `spring-boot-starter-webflux` và cấu hình SecurityWebFilterChain:

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@Configuration
class ReactiveLessonSecurity {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class ReactiveIdentityController {

    @GetMapping("/api/reactive/identity")
    Mono<Map<String, Object>> identity() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> {
                Authentication authentication = context.getAuthentication();
                return Map.<String, Object>of(
                    "name", authentication.getName(),
                    "authorities",
                    authentication.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .toList()
                );
            });
    }

    @GetMapping("/api/admin/report")
    Mono<String> adminReport() {
        return Mono.just("secret-report");
    }
}
~~~

Handler chủ động lấy ngữ cảnh từ `ReactiveSecurityContextHolder`. Đây là lựa chọn phù hợp cho mã học tập cần minh họa Reactor context; trong ứng dụng thực tế, WebFlux cũng có các cơ chế resolve principal/controller argument để giảm việc truy cập holder trực tiếp.

### 8.2. Gắn mockUser và mockJwt vào WebTestClient

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.*;

@SpringBootTest
class ReactiveIdentityTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void mockUserAppearsInReactiveContext() {
        client.mutateWith(mockUser("linh").roles("USER"))
            .get().uri("/api/reactive/identity")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("linh")
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_USER");
    }

    @Test
    void roleDeterminesAdminAccess() {
        client.mutateWith(mockUser("linh").roles("USER"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();

        client.mutateWith(mockUser("mai").roles("ADMIN"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void mockJwtUsesSubjectAsName() {
        client.mutateWith(mockJwt()
                .jwt(token -> token.subject("account-42"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_profile.read")))
            .get().uri("/api/reactive/identity")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("account-42");
    }
}
~~~

`SecurityMockServerConfigurers.springSecurity()` tích hợp security cho WebTestClient gắn với application context. `mockUser()` tạo authentication mock theo request; `mockJwt()` tạo JWT authentication mock trong môi trường Reactive.

**Phạm vi quan trọng:** các configurer mock này hữu ích khi `WebTestClient` gắn vào mock server/application context của test. Nếu `WebTestClient` được bind tới server đang chạy qua HTTP, chẳng hạn test `RANDOM_PORT`, principal giả lập trong JVM test không tự gửi sang server thật. Khi đó phải gửi credential hoặc bearer token qua HTTP.

Ngoài ra, `Mono`/`Flux` thường chỉ thực thi khi có subscriber. Với method security Reactive, hãy dùng `StepVerifier` hoặc bước xác minh có subscription thực sự để bảo đảm authorization được kích hoạt.

## 9. Một ca test nên khẳng định gì?

Một bài kiểm thử có thể hoạt động ở nhiều mức:

| Mục đích | Nên tạo gì | Nên assert gì | Chưa được chứng minh |
| --- | --- | --- | --- |
| Kiểm tra `SecurityContext` test | `@WithMockUser` hoặc custom `@WithSecurityContext` | Principal type/name, authorities, trạng thái token. | Endpoint/filter chain có áp dụng quyền đúng hay không. |
| Kiểm tra URL authorization Servlet | `MockMvc` với `user()`, `@WithMockUser` hoặc `jwt()` | 200/403 của người có/không có quyền, nội dung response. | Mật khẩu hoặc chữ ký JWT đã được xác minh thật. |
| Kiểm tra method security | Bean Spring + `@PreAuthorize` và mock context | Người thiếu quyền bị `AccessDeniedException`; người có quyền được thực thi. | Quy tắc bảo vệ URL của web filter. |
| Kiểm tra xác thực thực | Gửi HTTP Basic/form login/bearer token qua pipeline thật | Credential/token sai bị từ chối, đúng được chấp nhận. | Mọi trường hợp phân quyền theo dữ liệu nghiệp vụ. |
| Kiểm tra Reactive authorization | `WebTestClient` gắn context + `mockUser()`/`mockJwt()` | Chính sách áp dụng trong WebFilter/Reactor context. | Xác thực với server thật qua mạng. |
| Kiểm tra quyền theo tài nguyên | Principal có accountId/tenantId và dữ liệu sở hữu | Cùng role nhưng khác chủ sở hữu cho kết quả khác nhau. | Toàn bộ cơ chế HTTP nếu chỉ test một hàm nghiệp vụ. |

Ví dụ khi gặp yêu cầu “chỉ admin được xem báo cáo”, một test tốt có **ít nhất hai ca**:

~~~java
mvc.perform(get("/api/admin/report")
        .with(user("linh").roles("USER")))
    .andExpect(status().isForbidden());

mvc.perform(get("/api/admin/report")
        .with(user("mai").roles("ADMIN")))
    .andExpect(status().isOk());
~~~

Nếu chỉ có test thứ hai, việc vô tình cho phép **mọi** người truy cập vẫn có thể làm test xanh. Nếu endpoint dùng `POST`, cần cung cấp CSRF token hợp lệ trong các ca test **role**; nếu không, một phản hồi `403` có thể đến từ CSRF chứ không phải role.

## 10. Những bẫy thường gặp khi dùng Authentication và SecurityContext

### 10.1. Authentication tồn tại nên mặc định coi là đăng nhập

Anonymous authentication có thể tạo một `Authentication` với principal `anonymousUser`. Ngay cả `isAuthenticated()` cũng không nên được dùng riêng lẻ để tái tạo đầy đủ khái niệm “đã đăng nhập” của Spring Security. Hãy dùng biểu thức/chính sách chuẩn và test kết quả truy cập.

### 10.2. Nhầm roles với authorities

`roles("ADMIN")` thường tạo `ROLE_ADMIN`, còn `authorities("ADMIN")` tạo chính xác `ADMIN`. Khi kiểm tra `hasAuthority("SCOPE_reports.read")`, hãy cấp `SCOPE_reports.read` chứ không giả định `ROLE_reports.read` tương đương.

### 10.3. Ép kiểu principal mà không xem cơ chế xác thực

`@WithMockUser` không tạo custom `AccountPrincipal`; `jwt()` thường tạo principal `Jwt`; `oidcLogin()` tạo `OidcUser`. Nếu controller dùng `@AuthenticationPrincipal` với một kiểu cụ thể, test phải dựng đúng kiểu hoặc kiểm tra mapping principal của ứng dụng.

### 10.4. Đọc SecurityContextHolder sau MockMvc.perform

Bên trong filter chain, context được gắn với request; khi request kết thúc, Spring Security có thể dọn context. Để kiểm tra authentication mà controller nhận, hãy assert response hoặc dùng cơ chế ghi nhận được thiết kế cho test. Đừng dựa vào việc `SecurityContextHolder` còn giữ danh tính sau khi `perform` trả về.

### 10.5. Dùng SecurityContextHolder trong pipeline Reactive

Reactive context không được bảo đảm chạy trên cùng một thread. Dùng `ReactiveSecurityContextHolder` và các tiện ích `WebTestClient` dành cho WebFlux.

### 10.6. Cho rằng principal mock đã chứng minh password/JWT đúng

Mock authentication bỏ qua các bước xác minh credential tương ứng. Viết bài test riêng gửi credential/token thật khi cần kiểm chứng xác thực, decoder, phiên đăng nhập hoặc luồng OAuth2/OIDC.

### 10.7. Test method security trên object tạo bằng new

Với `@PreAuthorize`, mã phải đi qua bean/interceptor do Spring quản lý. Tạo service thủ công bằng `new` có thể bỏ qua cơ chế bảo mật và tạo kết luận sai.

### 10.8. Tự đặt context và quên dọn

Việc dùng `SecurityContextHolder.setContext(...)` trong test mà không cleanup có thể làm test sau kế thừa danh tính ngoài ý muốn. Dùng `@WithMockUser`/custom annotation hoặc đảm bảo cleanup khi tự thao tác.

## 11. Bài thực hành củng cố

Thực hiện trên ứng dụng Servlet ở mục 4, sau đó nếu có WebFlux thì thử mục 8:

1. **Quan sát authentication:** chạy với `@WithMockUser(username = "linh", roles = "USER")`. In hoặc assert `getName()`, kiểu principal và danh sách authorities.
2. **Đổi role thành authority:** thay `roles = "ADMIN"` bằng `authorities = "ADMIN"`. Quan sát test `hasRole("ADMIN")` đổi kết quả và giải thích lý do.
3. **Tùy biến principal:** dùng `@WithAccount(accountId = "acc-202")`; viết test xác minh `accountId` và kiểm tra quyền sở hữu một tài nguyên giả định.
4. **So sánh request-level và method-level:** dùng `user("linh")` cho request `MockMvc`, sau đó dùng `@WithMockUser` cho một test đọc `SecurityContextHolder` trực tiếp. Nêu vòng đời của từng cơ chế.
5. **JWT mock:** tạo JWT subject `account-42` và authority `SCOPE_profile.read`. Kiểm tra `getName()` và authority trong endpoint. Giải thích vì sao test này chưa kiểm chứng chữ ký JWT.
6. **Reactive:** dùng `mockUser()` và `mockJwt()` với `WebTestClient`. Kiểm tra `ReactiveSecurityContextHolder` trả về đúng người dùng ở handler.
7. **Ca từ chối:** mỗi quyền nhạy cảm phải có người được phép và người không có quyền. Xóa tạm quy tắc giới hạn trong môi trường thử và bảo đảm test từ chối phát hiện được lỗi.

### Câu hỏi tự kiểm tra

- Tại sao `Authentication` và `getPrincipal()` không phải cùng một khái niệm?
- Vì sao `@WithMockUser(username = "linh")` không bảo đảm controller nhận được `AccountPrincipal`?
- `hasRole("ADMIN")` tìm authority nào theo cấu hình mặc định?
- Nếu JWT claim có `scope = "reports.read"` nhưng test tự gắn `SCOPE_reports.read`, thành phần nào **chưa** được kiểm chứng?
- Tại sao WebFlux dùng `ReactiveSecurityContextHolder` thay vì truy cập holder dựa trên ThreadLocal?
- Vì sao một request POST bị `403` có thể chưa chứng minh rằng kiểm tra role hoạt động?

## 12. Ghi nhớ

**Authentication** là thông tin bảo mật đã được tổ chức thành một đối tượng; **principal** là danh tính bên trong đối tượng đó; **authorities** là tập quyền mà chính sách phân quyền sẽ kiểm tra; **SecurityContext** chứa authentication đang có hiệu lực trong ngữ cảnh xử lý.

Trong Servlet, các bài kiểm thử dùng `MockMvc`, `@WithMockUser` hoặc các request processor để thiết lập context phù hợp với security filter chain. Trong Reactive, `WebTestClient` và Reactor context giữ vai trò tương ứng. Các công cụ giả lập này cho phép kiểm tra rất chính xác việc **một principal với tập quyền cụ thể có được truy cập hay bị từ chối**, còn quá trình xác thực credential, xác minh JWT hoặc hoàn thành OAuth2/OIDC flow cần bài kiểm thử thực tế riêng.

Khi viết mỗi ca test, hãy trả lời rõ ba câu: **principal thực sự có kiểu và định danh nào, authentication đang mang authorities nào, và SecurityContext được truyền tới đúng lớp xử lý cần kiểm tra hay chưa?**
