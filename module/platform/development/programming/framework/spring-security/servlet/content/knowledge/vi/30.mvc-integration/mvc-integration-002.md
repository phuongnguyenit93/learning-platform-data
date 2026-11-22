# @CurrentSecurityContext và đọc Authentication trong Spring MVC

## 1. Mục tiêu bài học

Trong Spring Security trên Servlet stack, controller Spring MVC thường cần biết **ai đang thực hiện request**, request đã được xác thực ra sao, và các quyền hiện có. Spring Security lưu thông tin này trong **SecurityContext** và **Authentication**. Annotation **@CurrentSecurityContext** giúp lấy SecurityContext, hoặc trích xuất thuộc tính bên trong bằng Spring Expression Language (SpEL), ngay ở tham số method của controller.

Sau bài học, bạn có thể:
- Giải thích vòng đời SecurityContext trong request Servlet.
- Dùng @CurrentSecurityContext để nhận **SecurityContext** hoặc **Authentication**; lấy **authentication.name** và authorities.
- So sánh với **@AuthenticationPrincipal**, **Principal** của Java Servlet và **SecurityContextHolder**.
- Phân biệt người dùng đã đăng nhập, anonymous và quyền truy cập tài nguyên.
- Chạy ví dụ Java 17, Spring Boot 3.4.5, Spring MVC, MockMvc và security tests.
- Tránh rò rỉ dữ liệu Authentication hoặc dùng sai context khi xử lý bất đồng bộ.

**Phạm vi:** Spring Security Servlet + Spring MVC. Không trộn với WebFlux reactive SecurityContext.

## 2. SecurityContext chứa Authentication như thế nào?

**SecurityContext** là đối tượng chứa **Authentication** hiện hành. Trong code:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

**Authentication** đại diện cho principal và trạng thái xác thực của request. Các API quan trọng:

| Phương thức | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| getName() | Tên định danh principal mà provider cung cấp | Không bảo đảm luôn là email hoặc username |
| getPrincipal() | Principal thực tế | Có thể là UserDetails, Jwt, OidcUser, String... |
| getAuthorities() | GrantedAuthority: ROLE_USER, ROLE_ADMIN, SCOPE_read... | Không thay kiểm tra quyền sở hữu từng tài nguyên |
| isAuthenticated() | Trạng thái của Authentication implementation | **AnonymousAuthenticationToken có thể trả true** |
| getCredentials() | Dữ liệu credentials tùy mechanism | Không log, trả JSON hay ghi xuống cơ sở dữ liệu |
| getDetails() | Thông tin phụ như web request details | Có thể chứa dữ liệu nhạy cảm |

Một SecurityContext có thể **tồn tại nhưng Authentication là null**. Trên những request không đăng nhập, anonymous filter có thể đặt **AnonymousAuthenticationToken** để tạo đại diện người dùng vô danh. Vì vậy, kiểm tra **authentication != null** hoặc **authentication.isAuthenticated()** là **không đủ** để biết một người đã đăng nhập thật.

Dữ liệu Authentication không phải dữ liệu do client tự khai báo: nó phải đến từ các authentication filters/providers được cấu hình đúng. Ví dụ, HTTP Basic giải mã credentials rồi xác minh với UserDetailsService; JWT Resource Server xác minh token theo chính sách; OIDC login kiểm tra kết quả authentication từ nhà cung cấp danh tính.

### Authentication khác authorization

Một request có principal alice và ROLE_USER chưa chắc được phép xem đơn hàng của bob. **Xác thực** trả lời ai đang gọi; **phân quyền** quyết định có được truy cập endpoint và **tài nguyên cụ thể** hay không. Controller đọc Authentication không được phép bỏ qua SecurityFilterChain, method security hoặc resource ownership check.

## 3. SecurityContext được tạo và lấy ra khi nào?

Luồng cơ bản:

~~~text
HTTP request
     |
     v
Servlet container
     |
     v
Spring Security FilterChainProxy
     |-- SecurityContextHolderFilter / context lifecycle
     |-- Authentication filters: Basic, form, JWT, OIDC...
     |-- AuthenticationManager / AuthenticationProvider
     |-- AuthorizationFilter
     |
     v
DispatcherServlet
     |
     +-- Chọn @RestController method
     +-- Argument resolver cho @CurrentSecurityContext
     |
     v
Controller nhận SecurityContext hoặc Authentication
~~~

Khi Spring MVC gọi controller, SecurityContext hiện hành được Spring Security cung cấp qua **SecurityContextHolder**. Annotation **@CurrentSecurityContext** dùng cơ chế argument resolution để đưa SecurityContext vào method. Nó **không tự thực hiện login** và không tự kiểm tra mật khẩu, chữ ký JWT hoặc OAuth2 authorization code.

Theo chiến lược mặc định của Servlet, SecurityContextHolder sử dụng ngữ cảnh gắn với **thread** hiện hành, thường là ThreadLocal. SecurityContext có thể được nạp từ session tùy cấu hình, hoặc dựng mới cho mỗi request trong mô hình stateless token. Cuối request, security infrastructure có trách nhiệm làm sạch context để thread được tái sử dụng an toàn.

**Không suy đoán** rằng controller đọc được Authentication tức là ứng dụng đang dùng HttpSession: JWT stateless cũng tạo SecurityContext theo request.

## 4. Cú pháp @CurrentSecurityContext

Annotation:

~~~java
import org.springframework.security.core.annotation.CurrentSecurityContext;
~~~

### 4.1. Nhận nguyên SecurityContext

~~~java
@GetMapping("/api/me")
String me(@CurrentSecurityContext SecurityContext context) {
    Authentication auth = context.getAuthentication();
    return auth.getName();
}
~~~

### 4.2. Nhận Authentication bằng SpEL

~~~java
@GetMapping("/api/me/auth")
String authName(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
~~~

### 4.3. Nhận trực tiếp username

~~~java
@GetMapping("/api/me/name")
String name(
        @CurrentSecurityContext(
                expression = "authentication.name") String name) {
    return name;
}
~~~

Các đoạn trên là **trích đoạn phương thức**, cần đặt trong @RestController và cấu hình security phù hợp. Dự án hoàn chỉnh có ở mục 7.

**Điểm quan trọng về expression:** Root của SpEL trong @CurrentSecurityContext là **SecurityContext**, không phải bản thân Authentication. Vì thế:
- **expression = "authentication"** truy cập SecurityContext.getAuthentication().
- **expression = "authentication.name"** truy cập Authentication.getName().
- **expression = "authentication.principal"** truy cập principal runtime.
- **expression = "authentication.authorities"** truy cập authorities.

Đừng nhầm với annotation **@AuthenticationPrincipal**, nơi đối tượng được tiêm là principal và biểu thức, nếu có, được đánh giá theo cơ chế resolver của annotation đó.

Annotation có tùy chọn **errorOnInvalidType**; nếu kiểu method parameter không khớp với kết quả expression, cần kiểm thử hành vi phù hợp. Đừng ép một principal kiểu Jwt thành UserDetails chỉ vì một ứng dụng cũ dùng UserDetails.

## 5. So sánh các cách lấy danh tính trong controller

| Cách dùng | Mục đích | Giới hạn |
| --- | --- | --- |
| @CurrentSecurityContext SecurityContext | Lấy context đầy đủ | Vẫn phải đọc Authentication, xử lý anonymous/null khi cần |
| @CurrentSecurityContext(expression = "authentication") Authentication | Lấy Authentication trực tiếp | Không nên serialize Authentication thành JSON |
| @CurrentSecurityContext(expression = "authentication.name") String | Lấy tên từ Authentication | Không đảm bảo name là email hoặc định danh bất biến |
| @AuthenticationPrincipal UserDetails | Lấy principal, phù hợp UserDetails | Sai kiểu nếu principal là Jwt, OidcUser hoặc String |
| java.security.Principal | Lấy tên principal theo MVC/Servlet | Không phải API đầy đủ cho authorities |
| SecurityContextHolder.getContext() | Truy cập imperative ở lớp không có argument resolver | Phụ thuộc request thread/context propagation |

Ví dụ @AuthenticationPrincipal:

~~~java
@GetMapping("/api/profile")
String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

Ở HTTP Basic hoặc form login sử dụng UserDetailsService, principal thường là UserDetails. Trong OAuth2 Resource Server JWT, principal thường là **Jwt**; với OIDC Login thường là **OidcUser**; với anonymous có thể là String. Vì thế code trên **chỉ đúng khi đã biết cơ chế xác thực**.

Ví dụ dùng servlet request:

~~~java
@GetMapping("/api/who")
String who(HttpServletRequest request) {
    Principal principal = request.getUserPrincipal();
    return principal == null ? "guest" : principal.getName();
}
~~~

Đoạn này cần import **jakarta.servlet.http.HttpServletRequest** và **java.security.Principal**. Nếu cần authorities và loại Authentication, @CurrentSecurityContext là cách trực tiếp hơn.

Không tin **X-User**, **X-Authenticated-User** hoặc query parameter như danh tính, trừ khi có kiến trúc pre-authentication với trusted gateway và cơ chế chống header spoofing. Header do caller đặt không tự chứng minh người gọi là ai.

## 6. Anonymous không đồng nghĩa người dùng đã đăng nhập

Một lỗi bảo mật rất dễ gặp:

~~~java
// Không đủ để kết luận đây là người dùng đăng nhập thật.
if (authentication != null && authentication.isAuthenticated()) {
    // ...
}
~~~

AnonymousAuthenticationToken có thể trả isAuthenticated() = true dù principal thường là **anonymousUser**. Spring Security phân biệt anonymous, remember-me và fully authenticated theo cơ chế của framework.

Nếu chỉ cần hiển thị trạng thái, có thể dùng AuthenticationTrustResolver:

~~~java
AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

boolean loggedIn = authentication != null
        && !trustResolver.isAnonymous(authentication);
~~~

Đây là **trích đoạn**, cần import AuthenticationTrustResolver và AuthenticationTrustResolverImpl. Nếu cần chính sách nghiêm hơn nhớ đăng nhập, phải hiểu remember-me và **fullyAuthenticated()**. Đối với bảo vệ API, nên dùng **authorizeHttpRequests** hoặc **@PreAuthorize** với **@EnableMethodSecurity** thay vì một if trong controller.

Với endpoint public, code đọc context phải chịu được null/anonymous; đối với endpoint được **authenticated()** bảo vệ đúng cách, controller có thể kỳ vọng có Authentication hợp lệ tại thời điểm handler chạy.

## 7. Ví dụ Java 17 đầy đủ với Spring Boot 3 và MVC

Dự án dùng **Java 17**, **Spring Boot 3.4.5**, Maven, Spring MVC và Spring Security HTTP Basic. Đây là phương án đơn giản để quan sát SecurityContext, không phải cấu hình password cho production. Các endpoint:

- **GET /public/ping** là endpoint công khai, minh họa anonymous.
- **GET /api/me/context** nhận nguyên SecurityContext và đọc Authentication.
- **GET /api/me/name** dùng expression authentication.name.
- **GET /api/me/auth** nhận Authentication.
- **GET /api/me/principal** dùng @AuthenticationPrincipal để so sánh.
- **GET /api/me/direct** dùng SecurityContextHolder.
- **GET /api/admin** chỉ cho ROLE_ADMIN.

Cấu trúc:

~~~text
mvc-security-context-demo/
├── pom.xml
└── src/
    ├── main/java/demo/mvcsecurity/MvcSecurityContextApplication.java
    └── test/java/demo/mvcsecurity/MvcSecurityContextTests.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-security-context-demo</artifactId>
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

### 7.2. File ứng dụng chạy được

Lưu vào **src/main/java/demo/mvcsecurity/MvcSecurityContextApplication.java**. Java cho phép một public class cùng các package-private classes khác trong một file.

~~~java
package demo.mvcsecurity;

import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcSecurityContextApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcSecurityContextApplication.class, args);
    }
}

@Configuration
class DemoSecurityConfiguration {
    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}password")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-password")
                        .roles("ADMIN", "USER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class IdentityController {
    @GetMapping("/public/ping")
    Map<String, String> ping(
            @CurrentSecurityContext SecurityContext context) {
        Authentication a = context.getAuthentication();
        boolean guest = a == null
                || a instanceof AnonymousAuthenticationToken;
        return Map.of("viewer", guest ? "guest" : a.getName());
    }

    @GetMapping("/api/me/context")
    Map<String, Object> context(
            @CurrentSecurityContext SecurityContext context) {
        Authentication a = context.getAuthentication();
        List<String> authorities = a.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return Map.of(
                "name", a.getName(),
                "authenticationType", a.getClass().getSimpleName(),
                "authorities", authorities);
    }

    @GetMapping("/api/me/name")
    Map<String, String> name(
            @CurrentSecurityContext(
                    expression = "authentication.name") String username) {
        return Map.of("name", username);
    }

    @GetMapping("/api/me/auth")
    Map<String, Object> auth(
            @CurrentSecurityContext(
                    expression = "authentication") Authentication a) {
        return Map.of(
                "name", a.getName(),
                "authenticated", a.isAuthenticated());
    }

    @GetMapping("/api/me/principal")
    Map<String, String> principal(
            @AuthenticationPrincipal UserDetails user) {
        return Map.of("username", user.getUsername());
    }

    @GetMapping("/api/me/direct")
    Map<String, String> direct() {
        Authentication a =
                SecurityContextHolder.getContext().getAuthentication();
        return Map.of("name", a.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin(
            @CurrentSecurityContext(
                    expression = "authentication.name") String name) {
        return Map.of("admin", name);
    }
}
~~~

**Giải thích quan trọng:**

1. **SecurityFilterChain** định nghĩa ai được gọi endpoint. **GET /api/admin** yêu cầu ROLE_ADMIN; các request API khác yêu cầu authenticated; **GET /public/ping** cho phép anonymous.
2. **HttpSecurity.httpBasic(...)** kích hoạt authentication bằng Basic credentials. Ví dụ dùng InMemoryUserDetailsManager cho dễ thử.
3. **@CurrentSecurityContext SecurityContext** tự nhận context mà không cần viết SecurityContextHolder ở controller; **expression = "authentication"** trích Authentication.
4. **expression = "authentication.name"** trả tên được Authentication cung cấp. Nó không tự truy vấn dữ liệu người dùng hoặc chứng minh email đã xác thực.
5. **@AuthenticationPrincipal UserDetails** hoạt động trong ví dụ vì HTTP Basic xác thực với UserDetailsService. Sang JWT/OIDC có thể cần kiểu principal khác.
6. **context()** chỉ xuất name, loại Authentication và authorities. Đây là các trường minh họa; trong production cũng nên tối thiểu hóa thông tin. **Không trả toàn bộ Authentication** vì có thể chứa credentials/details.
7. **AnonymousAuthenticationToken** giúp minh họa lý do phải phân biệt anonymous với authenticated. Nếu ứng dụng tắt anonymous hoặc có nhiều chain, trạng thái có thể khác.
8. Dự án chỉ có GET nên giữ CSRF mặc định. Nếu bổ sung POST/PUT/DELETE với browser cookie authentication, phải đánh giá CSRF; không tắt toàn cục chỉ để demo.
9. **{noop}** và password hardcoded chỉ dành cho môi trường đào tạo; production cần password encoding, HTTPS, secrets management và chính sách credential phù hợp.

### 7.3. Chạy và xem response

Tại thư mục gốc:

~~~bash
mvn test
mvn spring-boot:run
~~~

Khi ứng dụng đã khởi động:

~~~bash
# Request public
curl -i http://localhost:8080/public/ping

# Không có Basic credentials -> 401
curl -i http://localhost:8080/api/me/name

# Đăng nhập bằng tài khoản demo
curl -i -u alice:password \
  http://localhost:8080/api/me/name

# Đọc SecurityContext và authorities
curl -i -u alice:password \
  http://localhost:8080/api/me/context

# User thông thường không được vào admin
curl -i -u alice:password \
  http://localhost:8080/api/admin

# Admin có quyền
curl -i -u admin:admin-password \
  http://localhost:8080/api/admin
~~~

Bảng kết quả dự kiến:

| Request | Status | Ý nghĩa |
| --- | --- | --- |
| /public/ping, chưa đăng nhập | 200 | Ví dụ JSON **{"viewer":"guest"}** |
| /api/me/name, chưa đăng nhập | 401 | Endpoint bảo vệ, HTTP Basic challenge |
| /api/me/name, alice | 200 | Ví dụ **{"name":"alice"}** |
| /api/me/context, alice | 200 | Chứa name, authenticationType, ROLE_USER |
| /api/admin, alice | 403 | Thiếu ROLE_ADMIN |
| /api/admin, admin | 200 | Ví dụ **{"admin":"admin"}** |

Đây là **output kỳ vọng của mã ví dụ**, cần chạy kiểm chứng trong môi trường Java/Maven thật. Thứ tự các key trong JSON không có bảo đảm. Không dùng mật khẩu demo, Basic over HTTP hoặc lệnh lưu credentials trong shell history ở production.

## 8. Kiểm thử với Spring Security Test và MockMvc

Spring Security cung cấp **spring-security-test** để tạo Authentication giả lập trong MockMvc. Đặt file **src/test/java/demo/mvcsecurity/MvcSecurityContextTests.java**:

~~~java
package demo.mvcsecurity;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcSecurityContextTests {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReachPublicEndpoint() throws Exception {
        mvc.perform(get("/public/ping").with(anonymous()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.viewer").value("guest"));
    }

    @Test
    void protectedEndpointRejectsAnonymous() throws Exception {
        mvc.perform(get("/api/me/name").with(anonymous()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void nameExpressionResolvesAuthenticatedUser() throws Exception {
        mvc.perform(get("/api/me/name")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void contextContainsAuthority() throws Exception {
        mvc.perform(get("/api/me/context")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authorities[0]")
                        .value("ROLE_USER"));
    }

    @Test
    void authenticationExpressionResolvesAuthentication()
            throws Exception {
        mvc.perform(get("/api/me/auth")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true));
    }

    @Test
    void userDetailsPrincipalWorksWithTestUser() throws Exception {
        mvc.perform(get("/api/me/principal")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void ordinaryUserIsDeniedAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanUseAdminEndpoint() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(user("admin").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.admin").value("admin"));
    }

    @Test
    void imperativeContextMatchesResolvedName() throws Exception {
        mvc.perform(get("/api/me/direct")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));
    }
}
~~~

Bộ test gồm **9 trường hợp**, kiểm tra public, anonymous 401, 200, authorities, UserDetails, 403 và truy cập trực tiếp SecurityContextHolder. Chạy:

~~~bash
mvn test
~~~

**Giới hạn của test:** .with(user(...)) gắn user giả vào SecurityContext trong môi trường MockMvc; nó không xác thực mật khẩu, không kiểm tra HTTP Basic thật, không xác minh chữ ký JWT hoặc kết nối OIDC provider. Nếu cần thử HTTP Basic credential path, viết test với **httpBasic("alice", "password")** của spring-security-test và chạy filter thực. Với JWT, cần thêm tests cho issuer/audience/expiry/signature và converter để không lầm test mock principal với xác minh token production.

### 8.1. Vì sao test 401/403 không giống nhau?

- **401 Unauthorized:** chưa xác thực hoặc credentials không được chấp nhận; HTTP Basic thường gửi WWW-Authenticate.
- **403 Forbidden:** user đã được xác thực nhưng không đủ quyền; ví dụ alice có ROLE_USER nhưng /api/admin cần ROLE_ADMIN.
- Với browser formLogin hoặc OAuth2 Login, request chưa đăng nhập có thể **302 redirect**, không nhất thiết là 401.
- Nếu test bất ngờ 200 vì @WithMockUser hoặc custom MockMvc setup, xác nhận đúng security chain đang chạy; đừng chỉnh endpoint thành permitAll để “pass test”.

## 9. Khi ứng dụng thay HTTP Basic bằng JWT/OIDC

**@CurrentSecurityContext** vẫn đọc SecurityContext bất kể Authentication đến từ đâu. Nhưng **principal type** và authorities có thể thay đổi.

| Cơ chế | Authentication thường gặp | Principal thường gặp |
| --- | --- | --- |
| Username/password / HTTP Basic | UsernamePasswordAuthenticationToken | UserDetails |
| Resource Server JWT | JwtAuthenticationToken | Jwt |
| OAuth2/OIDC Login | OAuth2AuthenticationToken | OAuth2User hoặc OidcUser |
| Pre-authenticated gateway | PreAuthenticatedAuthenticationToken | Phụ thuộc provider |
| Anonymous | AnonymousAuthenticationToken | Thường String anonymousUser |

Với JWT, **getName()** thường dựa trên **sub** hoặc claim do JwtAuthenticationConverter cấu hình, không chắc là email. Với OIDC, subject/issuer có thể là định danh bền vững hơn display name. **Không lưu quyền sở hữu dữ liệu chỉ bằng email mà không xác định contract identity giữa tenants và providers**.

Nếu endpoint thật sự cần JWT claims, có thể dùng **@AuthenticationPrincipal Jwt jwt** (khi principal là Jwt) hoặc kiểm tra Authentication là JwtAuthenticationToken. Nhưng không cast Authentication.getPrincipal() thành UserDetails trong một API sử dụng JWT.

Ví dụ ngắn dùng Authentication tổng quát:

~~~java
@GetMapping("/api/current-subject")
String currentSubject(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication) {
    return authentication.getName();
}
~~~

Đây là trích đoạn controller, không có đầy đủ import. Nó sử dụng contract chung **Authentication.getName()**, nhờ đó ít phụ thuộc vào một principal implementation cụ thể.

Nếu một ứng dụng có **nhiều SecurityFilterChain** (một chain cho API Bearer và một chain cho web login), phải kiểm tra thứ tự **securityMatcher**. Spring Security chọn chain thích hợp theo cấu hình; @CurrentSecurityContext chỉ đọc kết quả, không thể sửa sai việc API vô tình đi qua login chain.

## 10. Đọc Authentication không thay thế phân quyền

Một anti-pattern:

~~~java
// SAI: isAuthenticated không chứng minh user có quyền với record.
if (authentication.isAuthenticated()) {
    return customerRepository.findById(id).orElseThrow();
}
~~~

Những biện pháp cần thiết:

1. Cấu hình **authorizeHttpRequests** tại security filter chain; ví dụ **hasRole("ADMIN")** yêu cầu GrantedAuthority **ROLE_ADMIN**.
2. Nếu dùng method security, bật **@EnableMethodSecurity** rồi kiểm tra **@PreAuthorize** theo policy.
3. Trong service, đối chiếu **owner/tenant/ACL** của bản ghi với principal ID đã được xác minh.
4. Không tin role do client gửi trong header, request parameter hoặc JSON.
5. Chỉ đọc Authentication để lấy thông tin đầu vào cho quyết định quyền có kiểm chứng.

Với Spring Security, **hasAuthority("SCOPE_read")** so khớp chính xác SCOPE_read, còn **hasRole("ADMIN")** mặc định ghép prefix ROLE_. Nếu mapper của IdP cấp một định dạng khác, phải cấu hình converter và test thay vì suy luận quyền chỉ từ chuỗi name.

**Không trả nguyên Authentication hoặc SecurityContext thành JSON.** Các object này có thể chứa credentials, principal attributes, details và thông tin không dành cho client. Ví dụ code chỉ xuất ba trường có chủ đích: name, authenticationType, authorities; production cũng có thể cần ẩn authorities nếu không nằm trong API contract.

## 11. ThreadLocal, @Async và vòng đời request

SecurityContextHolder mặc định phục vụ Servlet processing với ngữ cảnh gắn với request thread. Code dưới đây không tự động có context đúng khi chạy trong thread tùy ý:

~~~java
executor.execute(() -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    // Có thể null hoặc không phải danh tính dự kiến.
});
~~~

- **new Thread(...)**, custom Executor hoặc **@Async** không luôn kế thừa SecurityContext.
- Truyền cùng context sang một thread pool dài hạn có nguy cơ rò quyền hoặc giữ danh tính đã cũ.
- Spring Security hỗ trợ các wrapper như **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextExecutor**, **DelegatingSecurityContextAsyncTaskExecutor**, tùy execution model.
- Spring MVC async Callable có tích hợp nhất định, nhưng không nên giả định mọi DeferredResult/custom task đều có propagation tương đương.
- Một hướng thiết kế tốt là trích **principal ID bất biến và được xác minh** tại request boundary, truyền vào service/job rồi kiểm tra quyền ở thời điểm hành động thực sự diễn ra.

Không tự thao tác SecurityContextHolder.setContext() hoặc setAuthentication() trong controller để “bỏ qua login”. Nếu hệ thống chủ động tạo Authentication, đó phải là một authentication flow có kiểm tra credentials/token phù hợp và quản lý lifecycle/clear/save context chính xác.

## 12. Lỗi thường gặp và cách chẩn đoán

| Lỗi/triệu chứng | Nguyên nhân hoặc điều cần xem |
| --- | --- |
| Context có nhưng Authentication null | Request chưa xác thực, anonymous bị tắt, chain không áp dụng hoặc lifecycle khác |
| getName() là anonymousUser | AnonymousAuthenticationToken chứ không phải tài khoản đăng nhập |
| isAuthenticated() true nhưng user vẫn anonymous | Semantics của AnonymousAuthenticationToken |
| @AuthenticationPrincipal UserDetails bị null/sai kiểu | Principal runtime là Jwt, OidcUser, String... |
| SpEL expression trả sai | Root là SecurityContext, không phải Authentication; kiểm tra expression |
| Chưa đăng nhập API lại 302 thay vì 401 | API vô tình đi qua web login chain/entry point |
| User đăng nhập nhưng 403 | Thiếu authorities, sai ROLE_/SCOPE_ hoặc không đủ quyền resource |
| MockMvc pass, production 401 | Mock principal không chứng minh token/password thật hợp lệ |
| @Async không thấy Authentication | ThreadLocal không tự propagate qua mọi executor |
| User A xuất hiện trong request B | Custom filter/executor làm rò SecurityContext hoặc không clear |
| POST browser 403 dù GET chạy | Có thể là CSRF hoặc authorization, không chỉ liên quan @CurrentSecurityContext |
| Curl chạy được, browser gặp lỗi CORS | CORS/preflight là cơ chế riêng, không phải controller argument resolver |
| Lộ token/password khi debug | Đã log credentials hoặc serialize Authentication |
| User xem được dữ liệu người khác dù authenticated | Thiếu ownership check/ACL ở service |

**Quy trình debug:** xác nhận request vào đúng SecurityFilterChain → xác định authentication filter/provider → xem loại Authentication thật → lấy principal/name và authorities → kiểm tra AuthorizationFilter/method security → kiểm tra quyền đối với dữ liệu đích. Đừng dùng permitAll() để che 401/403 chưa rõ nguyên nhân.

## 13. Checklist sử dụng trong dự án thực

- [ ] Chắc chắn đang dùng Spring MVC Servlet, không trộn với WebFlux.
- [ ] Endpoint đã có Authentication mechanism và security chain đúng.
- [ ] Dùng **@CurrentSecurityContext** khi cần context hoặc Authentication, **@AuthenticationPrincipal** khi cần principal type cụ thể.
- [ ] Không suy luận login từ Authentication != null hoặc isAuthenticated() đơn lẻ.
- [ ] Xác định rõ getName(), principal type và authorities theo provider đang chạy.
- [ ] Dùng authorizeHttpRequests/@PreAuthorize và resource-level authorization thay vì tự xét chuỗi tên.
- [ ] Không serialize SecurityContext/Authentication; chỉ xuất DTO với trường cần thiết.
- [ ] Không truyền credentials hoặc SecurityContext tùy tiện qua background tasks.
- [ ] Có tests 200/401/403, anonymous, principal type, authorities, Web MVC argument resolution.
- [ ] Có integration tests riêng cho Basic/OIDC/JWT thực tế nếu ứng dụng dùng các cơ chế đó.
- [ ] Kiểm tra CSRF khi browser sử dụng cookie/session và có request thay đổi trạng thái.

## 14. Câu hỏi tự kiểm tra

1. **@CurrentSecurityContext SecurityContext context** lấy gì? Lấy SecurityContext hiện hành do Spring Security cung cấp cho MVC request.
2. Muốn nhận Authentication trực tiếp, viết gì? **@CurrentSecurityContext(expression = "authentication") Authentication authentication**.
3. Muốn tên, viết gì? **@CurrentSecurityContext(expression = "authentication.name") String name**.
4. Vì sao **@AuthenticationPrincipal UserDetails** không đúng cho mọi API? Vì principal có thể là Jwt/OidcUser/String.
5. **isAuthenticated()** đủ loại trừ anonymous không? Không, AnonymousAuthenticationToken có thể trả true.
6. SecurityContext có luôn đồng nghĩa đã có HttpSession? Không, API JWT stateless cũng có context.
7. Đọc được role nghĩa là được xem bất kỳ dữ liệu nào? Không, vẫn cần authorization theo đối tượng/tenant.
8. @CurrentSecurityContext có tự xác minh mật khẩu hoặc JWT không? Không; đó là trách nhiệm authentication infrastructure.
9. Có nên trả nguyên Authentication thành JSON không? Không, phải chọn những trường được phép hiển thị.
10. SecurityContextHolder có tự được truyền sang mọi @Async task không? Không; cần propagation hoặc truyền principal ID thích hợp.

**Tóm tắt:** **@CurrentSecurityContext** là cách khai báo rõ ràng để Spring MVC controller lấy SecurityContext hoặc giá trị bên trong như Authentication và authentication.name. Dùng đúng annotation theo nhu cầu, hiểu kiểu principal/anonymous, giữ ranh giới xác thực–phân quyền, chỉ trả thông tin công khai tối thiểu và kiểm thử thật với security chain phù hợp.
