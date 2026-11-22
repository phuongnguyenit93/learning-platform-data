# Lấy biến đường dẫn để đối chiếu danh tính người gọi trong Spring Security Servlet

## Mục tiêu và bối cảnh

Trong API Servlet có đường dẫn gắn với người dùng, ví dụ GET /users/alice/profile, phần alice thường được gọi là **URI template variable** hoặc **biến đường dẫn**. Hệ thống cần trả lời: người gửi request hiện tại có được xem profile của alice hay không? Chỉ nhận tham số username trong controller không tạo ra cơ chế phân quyền: client hoàn toàn có thể đổi đường dẫn sang /users/bob/profile.

Spring Security 6 cung cấp cơ chế phân quyền HTTP bằng authorizeHttpRequests, RequestMatcher và AuthorizationManager. Khi một RequestMatcher có biến đường dẫn, Spring Security có thể chuyển những biến đã trích xuất vào **RequestAuthorizationContext.getVariables()**, cho phép so sánh username trong URL với **Authentication của người gọi đã được xác thực**. Đây là cách thể hiện rõ chính sách **chỉ chủ tài khoản hoặc quản trị viên được truy cập**, trước khi request đến controller.

Sau bài học, bạn có thể:

1. Phân biệt biến đường dẫn, query parameter, dữ liệu request và danh tính đã xác thực.
2. Hiểu cách requestMatchers kết hợp URI template, HttpMethod, biến path và AuthorizationManager.
3. Sử dụng RequestAuthorizationContext.getVariables(), Authentication.getName() và AuthorizationDecision để chặn truy cập sai chủ tài khoản.
4. Viết một ứng dụng Java 17+ Spring Boot 3.x / Spring Security 6.x có ví dụ GET /users/{username}/profile.
5. Kiểm thử được trường hợp anonymous, owner, user khác, quản trị viên, giả mạo header và query parameter.
6. Phân biệt phân quyền HTTP và kiểm tra quyền trên bản ghi nghiệp vụ; phòng tránh IDOR/BOLA khi đường dẫn chứa ID tài nguyên.
7. Nhận biết lỗi về matcher, thứ tự rule, encoding URL, path normalization, tài khoản đổi tên và nhiều SecurityFilterChain.
8. Chọn giữa lambda AuthorizationManager, WebExpressionAuthorizationManager và bảo vệ ở tầng service.

Bối cảnh chỉ áp dụng cho **Spring Security Servlet**. API của Spring WebFlux như ServerWebExchange và ReactiveAuthorizationManager không phải các class được sử dụng trong bài này.

## 1. Mô hình quyền: đường dẫn là dữ liệu do client cung cấp

Xét ba người dùng:

| Danh tính xác thực | URL yêu cầu | Kỳ vọng nếu chỉ chủ sở hữu được xem |
| --- | --- | --- |
| alice | GET /users/alice/profile | Cho phép |
| alice | GET /users/bob/profile | Từ chối |
| bob | GET /users/bob/profile | Cho phép |
| bob | GET /users/alice/profile | Từ chối |
| khách chưa đăng nhập | GET /users/alice/profile | Yêu cầu xác thực |
| admin có ROLE_ADMIN | GET /users/alice/profile | Có thể cho phép theo chính sách quản trị |

Đường dẫn /users/alice/profile **không chứng minh** request do alice gửi. Tương tự, header X-User: alice, query parameter ?username=alice hoặc body chứa "owner":"alice" đều do client tự cung cấp và không phải bằng chứng định danh.

Thông tin được tin cậy để xét quyền phải đến từ cơ chế authentication đã được cấu hình: Spring Security tạo hoặc xác minh Authentication qua SecurityContext từ session, HTTP Basic, bearer token, v.v. Tầng phân quyền đọc Authentication này nhưng không tự giải mã mật khẩu hay xác minh token thay AuthenticationManager/Provider.

Lý tưởng, hệ thống có danh tính nội bộ ổn định, ví dụ user ID dạng UUID. username trong URL chỉ là ví dụ học API. Nếu username có thể đổi hoặc có quy tắc chuẩn hóa phức tạp, so sánh username chuỗi nguyên văn có thể không còn đúng chính sách nghiệp vụ.

### Sơ đồ request

~~~text
Client: GET /users/bob/profile + credentials của alice
            |
     FilterChainProxy / SecurityFilterChain
            |
     Filter authentication xác minh alice
            |
     RequestMatcher match /users/{username}/profile
            |   -> variables = {"username": "bob"}
            |
     AuthorizationManager<RequestAuthorizationContext>
            |   -> Authentication.name = "alice"
            |   -> path variable username = "bob"
            |   -> alice != bob và không có ROLE_ADMIN
            |
     AuthorizationDecision(false)
            |
     Trả 403; controller profile không được thực thi
~~~

Nếu client chưa có danh tính hợp lệ, HTTP Basic thường trả 401 với WWW-Authenticate; form login thường redirect tới trang đăng nhập. Nếu client đã xác thực nhưng không đủ quyền, thường trả 403. Cách phản hồi cụ thể phụ thuộc AuthenticationEntryPoint, AccessDeniedHandler và SecurityFilterChain của ứng dụng; không dùng riêng HTTP status để kết luận password đúng/sai.

## 2. Ba kiểu dữ liệu dễ bị nhầm

### 2.1. Path variable

Ví dụ định nghĩa MVC:

~~~java
@GetMapping("/users/{username}/profile")
public String profile(@PathVariable("username") String username) {
    return "PROFILE:" + username;
}
~~~

Với GET /users/alice/profile, framework có thể gán username = "alice". Đây là dữ liệu định tuyến do URL mang đến; controller nhận nó **sau** khi request đi qua security filter chain, nếu được phép.

### 2.2. Query parameter

Request GET /users/alice/profile?username=bob có URI path vẫn là /users/alice/profile. Query parameter không tự thay thế {username} trong URI template.

~~~text
Path:   /users/alice/profile
Query:  username=bob
Path variable username: alice
~~~

Spring MVC có thể đọc query qua @RequestParam, nhưng không được biến query username thành căn cứ xác định chủ tài khoản nếu policy đang bảo vệ path variable.

### 2.3. Authentication

Authentication thường có getName() trả tên định danh do cơ chế authentication cung cấp. Ví dụ tài khoản InMemoryUserDetailsManager tên alice đăng nhập bằng HTTP Basic, Authentication.getName() trả alice.

Với JWT, OIDC hoặc custom principal, getName() có thể là subject, email, ID hoặc claim đã cấu hình; **không mặc định** nó luôn khớp username hiển thị ở URL. Phải thống nhất định nghĩa danh tính canonical và ánh xạ dữ liệu bảo mật.

Tuyệt đối không tự tạo Authentication từ query/header X-User chưa được một thành phần đáng tin xác minh rồi coi là người gọi thật.

## 3. Spring Security phân quyền URI template ra sao?

Trong Spring Security 6 trên Servlet, các rule authorizeHttpRequests được áp dụng cho request match một RequestMatcher. Một mẫu có biến:

~~~text
/users/{username}/profile
~~~

Dấu ngoặc nhọn là cách biểu diễn URI template variable; khi một request match, matcher có thể trả thông tin biến tương ứng. Trong kiểu AuthorizationManager<RequestAuthorizationContext>, context cung cấp:

~~~java
Map<String, String> variables = context.getVariables();
String usernameFromUrl = variables.get("username");
~~~

Đây là đoạn minh họa đặt bên trong một AuthorizationManager callback; không phải Java file độc lập. Chính context này nối thế giới **URI matching** và **HTTP authorization**: tránh việc tự cắt URL bằng split("/") rồi đoán vị trí của username.

Một callback thường có dạng:

~~~java
(authentication, context) -> {
    Authentication current = authentication.get();
    String target = context.getVariables().get("username");
    boolean allowed = /* kiểm tra policy */;
    return new AuthorizationDecision(allowed);
}
~~~

- authentication là Supplier<Authentication>, để Spring Security có thể trì hoãn việc lấy authentication khi không cần.
- context là RequestAuthorizationContext, chứa HttpServletRequest và các variables do matcher cung cấp.
- AuthorizationDecision(true) cho phép; false từ chối.
- Đừng mặc định context.getVariables() luôn có key username. Rule không khai báo biến, matcher không hỗ trợ trích xuất hoặc path không khớp có thể làm dữ liệu khác mong muốn. Chính sách an toàn là **thiếu biến → không cấp quyền**, không bỏ qua check.
- Không truy cập request.getParameter("username") để thay cho biến đã được matcher trích xuất.

### MvcRequestMatcher và sự khớp với Spring MVC

Trong Spring MVC, MvcRequestMatcher có thể dùng HandlerMappingIntrospector để bám theo cơ chế matching của MVC. Khi dùng builder với pattern có {username}, bạn có thể thu biến từ RequestAuthorizationContext trong HTTP authorization rule.

Ví dụ:

~~~java
MvcRequestMatcher profileMatcher =
        new MvcRequestMatcher.Builder(introspector)
                .pattern(HttpMethod.GET, "/users/{username}/profile");
~~~

Đây là snippet nằm trong SecurityConfig, với HandlerMappingIntrospector được Spring MVC cung cấp. Ở phần code hoàn chỉnh sẽ có import và @Bean đầy đủ.

Trong những phiên bản/configuration khác, requestMatchers(String...) có thể chọn matcher phù hợp dựa trên Spring MVC và các yếu tố classpath. Với ứng dụng đã có nhiều Servlet/mappings hoặc thay cơ chế path matching, nên khai báo matcher rõ ràng và **kiểm thử URL thực tế**, không đoán cơ chế matcher chỉ từ hình dạng pattern.

Nếu hệ thống dùng matcher không hỗ trợ capture variables, bạn có thể không nhận được dữ liệu như mong đợi. Không viết phân quyền “cho phép nếu không có biến” để chữa NullPointerException; phải sửa matcher hoặc thiết kế policy khác.

## 4. Chính sách chỉ chủ sở hữu hoặc ADMIN

Quy tắc ví dụ:

**Cho phép GET /users/{username}/profile khi request đã xác thực và một trong hai điều kiện đúng:**

1. username trong đường dẫn bằng Authentication.getName(), với quy tắc so sánh nhất quán.
2. Authentication có authority ROLE_ADMIN.

Nếu người gọi chưa được xác thực, không cấp quyền dù đường dẫn là /users/anonymousUser/profile. Điểm này rất quan trọng: trong Spring Security, AnonymousAuthenticationToken có thể trả isAuthenticated() là true theo cơ chế token, nhưng nó vẫn đại diện người dùng anonymous, **không** phải tài khoản thực.

Một implementation tự kiểm tra:

~~~java
private static AuthorizationManager<RequestAuthorizationContext>
ownerOrAdmin() {
    return (authentication, context) -> {
        Authentication current = authentication.get();
        String requestedUser = context.getVariables().get("username");

        boolean actualLogin = current != null
                && current.isAuthenticated()
                && !(current instanceof AnonymousAuthenticationToken);

        boolean sameUser = actualLogin
                && requestedUser != null
                && requestedUser.equals(current.getName());

        boolean admin = actualLogin && current.getAuthorities().stream()
                .anyMatch(authority ->
                        "ROLE_ADMIN".equals(authority.getAuthority()));

        return new AuthorizationDecision(sameUser || admin);
    };
}
~~~

Trong code này:

- Nếu requestedUser null, sameUser false; chỉ admin đã xác thực mới được qua. Với chính sách mong muốn chỉ khi path variable tồn tại, **có thể yêu cầu requestedUser != null cho cả ADMIN** để fail closed. Phần chương trình đầy đủ sẽ áp dụng điều kiện này.
- Xác thực thật được yêu cầu cho cả owner và admin; không được chỉ dựa vào isAuthenticated() trên anonymous token.
- ROLE_ADMIN là authority do User.withUsername(...).roles("ADMIN") tạo trong ứng dụng demo.
- ADMIN được phép theo **chính sách đã định nghĩa**. Nếu sản phẩm không cho admin xem dữ liệu cá nhân người khác, bỏ nhánh admin; kỹ thuật matcher không tự áp đặt quản trị viên phải có quyền.

Đây là một AuthorizationManager ở **tầng HTTP**. Với tài nguyên nhạy cảm, service truy xuất dữ liệu cũng nên thực thi kiểm soát ownership/tenant để tránh đường đi khác bypass được lớp HTTP.

## 5. Ví dụ hoàn chỉnh: Java 17 + Spring Boot 3.x + Spring Security 6.x

Chúng ta xây một Spring MVC API rất nhỏ:

- GET /users/{username}/profile trả một chuỗi nhận diện profile nếu được phép.
- Danh tính lấy từ HTTP Basic, không lấy từ URL/header tự khai.
- User alice được xem alice, user bob được xem bob.
- User khác bị 403; anonymous bị 401 theo HTTP Basic.
- ADMIN được xem các profile theo yêu cầu minh họa.
- Các URL khác bị denyAll để tránh vô tình công khai dữ liệu khi mở rộng controller.

HTTP Basic chỉ để kiểm thử dễ bằng curl và MockMvc; nó không phải khuyến nghị dùng mật khẩu demo trong production. Với API thực, cần HTTPS và có thể dùng session, OAuth2 Resource Server hoặc cơ chế đã được đánh giá.

### 5.1. Cấu trúc project

~~~text
path-identity-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat (nếu đã tạo Gradle Wrapper)
  src/main/java/dev/example/pathidentity/
    PathIdentityApplication.java
    SecurityConfig.java
    ProfileController.java
  src/test/java/dev/example/pathidentity/
    PathIdentityIntegrationTest.java
~~~

Tệp settings.gradle:

~~~groovy
rootProject.name = 'path-identity-demo'
~~~

Tệp build.gradle (ví dụ phiên bản Spring Boot 3.3.5 với Java 17):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

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

Khi dùng Spring Boot dependency management, các phiên bản Spring Security tương thích được chọn theo Spring Boot. Đừng buộc riêng một spring-security-web version không tương thích.

### 5.2. Entry point

Tệp src/main/java/dev/example/pathidentity/PathIdentityApplication.java:

~~~java
package dev.example.pathidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathIdentityApplication.class, args);
    }
}
~~~

### 5.3. SecurityFilterChain và AuthorizationManager

Tệp src/main/java/dev/example/pathidentity/SecurityConfig.java:

~~~java
package dev.example.pathidentity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.Customizer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-demo-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-demo-pass"))
                        .roles("ADMIN").build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, HandlerMappingIntrospector introspector)
            throws Exception {

        MvcRequestMatcher profileGet =
                new MvcRequestMatcher.Builder(introspector)
                        .pattern(HttpMethod.GET,
                                "/users/{username}/profile");

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(profileGet)
                        .access(ownerOrAdmin())
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    private static AuthorizationManager<RequestAuthorizationContext>
    ownerOrAdmin() {
        return (authentication, context) -> {
            Authentication current = authentication.get();
            String requestedUser = context.getVariables().get("username");

            boolean loggedIn = current != null
                    && current.isAuthenticated()
                    && !(current instanceof AnonymousAuthenticationToken);

            boolean sameUser = loggedIn && requestedUser != null
                    && requestedUser.equals(current.getName());

            boolean hasAdminRole = loggedIn
                    && current.getAuthorities().stream()
                    .anyMatch(authority ->
                            "ROLE_ADMIN".equals(authority.getAuthority()));

            boolean allowed = requestedUser != null
                    && (sameUser || hasAdminRole);

            return new AuthorizationDecision(allowed);
        };
    }
}
~~~

Giải thích đoạn cấu hình:

1. MvcRequestMatcher.Builder sử dụng HandlerMappingIntrospector và khai báo rõ HttpMethod.GET cùng mẫu /users/{username}/profile.
2. Khi URL khớp, RequestAuthorizationContext có key username; hàm ownerOrAdmin đọc đúng biến này.
3. Authentication nhận từ Supplier của Spring Security, không tạo thủ công từ query hoặc X-User header.
4. actual login được xác định bằng cách từ chối AnonymousAuthenticationToken, ngoài kiểm tra isAuthenticated().
5. Nếu biến path không có giá trị, allowed=false cho mọi người, kể cả admin, tránh một thiếu sót mapping biến bị hiểu thành quyền hợp lệ.
6. Đường dẫn /users/alice/profile được xem bởi alice hoặc admin; bob bị từ chối trước controller.
7. anyRequest().denyAll() là chốt chặn fail closed cho URL chưa có policy. Điều này khác anyRequest().authenticated(): một user đã login vẫn không được xem endpoint ngoài phạm vi rule.
8. httpBasic() tạo HTTP Basic authentication để demo. CSRF protection không bị tắt, nhưng vì mẫu chỉ có GET nên không cần CSRF token cho những request này.
9. Account demo nằm trong InMemoryUserDetailsManager; đây không phải giải pháp production user store hay password policy.

Nếu thêm endpoints quản lý trong ứng dụng thật, bạn phải thêm rule riêng đúng thứ tự và test từng rule. **Không copy nguyên anyRequest().denyAll() vào app có các endpoint khác mà không thiết kế chính sách của chúng.**

### 5.4. MVC Controller

Tệp src/main/java/dev/example/pathidentity/ProfileController.java:

~~~java
package dev.example.pathidentity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/users/{username}/profile")
    public String profile(@PathVariable("username") String username) {
        return "PROFILE:" + username;
    }
}
~~~

Controller nhận biến username từ MVC path; trước đó SecurityFilterChain đã kiểm tra policy. Vì code minh họa chỉ trả chuỗi, không có database hoặc dữ liệu thật để rò rỉ. Trong production, controller/service còn phải truy xuất đúng record và kiểm tra authorization trên dữ liệu thực tế.

Không đánh đồng việc controller nhận được @PathVariable với bằng chứng user đã được xác thực: user đầu vào không phải identity của request.

### 5.5. Chạy và quan sát bằng curl

Trong project có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Dùng một terminal khác:

~~~bash
curl -i -u alice:alice-demo-pass http://localhost:8080/users/alice/profile
curl -i -u bob:bob-demo-pass http://localhost:8080/users/alice/profile
curl -i -u admin:admin-demo-pass http://localhost:8080/users/alice/profile
curl -i http://localhost:8080/users/alice/profile
~~~

Kết quả ứng dụng/HTTP quan trọng:

| Request | Kỳ vọng |
| --- | --- |
| alice → /users/alice/profile | 200 và body PROFILE:alice |
| bob → /users/alice/profile | 403 (đã xác thực, không phải owner/admin) |
| admin → /users/alice/profile | 200 và body PROFILE:alice |
| anonymous → /users/alice/profile | 401 challenge theo Basic |
| alice → /users/bob/profile | 403 |
| alice → /users/alice/profile?username=bob | 200, vì path variable là alice |
| bob + header X-User: alice → /users/alice/profile | 403 |

Bảng nói về **kết quả kỳ vọng**, không sao chép nguyên HTTP headers: có thể có WWW-Authenticate, Cache-Control và các security headers khác. Không đưa password demo của code vào môi trường thật. Với Basic, username/password được truyền trong Authorization header mã hóa Base64 chứ không được mã hóa bảo mật về mặt transport: production **bắt buộc HTTPS**.

### 5.6. Kiểm thử MockMvc

Tệp src/test/java/dev/example/pathidentity/PathIdentityIntegrationTest.java:

~~~java
package dev.example.pathidentity;

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
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PathIdentityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void ownerCanReadOwnProfile() throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE:alice"));
    }

    @Test
    void otherAuthenticatedUserIsForbidden() throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadOtherUsersProfile() throws Exception {
        mvc.perform(get("/users/bob/profile")
                        .with(httpBasic("admin", "admin-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE:bob"));
    }

    @Test
    void anonymousUserReceivesAuthenticationChallenge() throws Exception {
        mvc.perform(get("/users/alice/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotPretendToOwnAnonymousUser() throws Exception {
        mvc.perform(get("/users/anonymousUser/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void queryParameterDoesNotReplacePathVariable() throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .queryParam("username", "bob")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("PROFILE:alice"));
    }

    @Test
    void forgedHeaderDoesNotOverrideAuthenticatedIdentity()
            throws Exception {
        mvc.perform(get("/users/alice/profile")
                        .header("X-User", "alice")
                        .with(httpBasic("bob", "bob-demo-pass")))
                .andExpect(status().isForbidden());
    }

    @Test
    void unmatchedRouteFailsClosed() throws Exception {
        mvc.perform(get("/users/alice/profile/extra")
                        .with(httpBasic("alice", "alice-demo-pass")))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy trong thư mục project:

~~~bash
./gradlew test
~~~

Các bài kiểm thử dùng HTTP Basic qua spring-security-test, tức là kiểm tra đường đi authentication và authorization của ứng dụng chứ không chỉ mock trực tiếp phương thức ownerOrAdmin. Việc test owner thành công không đủ: cần cả negative test (user khác bị chặn), anonymous, admin policy, query/header giả mạo và URL ngoài matcher.

Kỳ vọng test pass với cấu hình mẫu ở trên. Nếu một request đã bị Spring Security từ chối, controller không trả body PROFILE:... cho request đó. Khi tùy chỉnh AuthenticationEntryPoint/AccessDeniedHandler hoặc chạy sau proxy, HTTP status có thể đổi theo hợp đồng app; lúc ấy sửa assertion cho đúng policy dự kiến, không tùy tiện nới quyền.

## 6. Cách viết ngắn bằng WebExpressionAuthorizationManager

Spring Security 6 hỗ trợ biểu thức ủy quyền HTTP qua WebExpressionAuthorizationManager. Khi RequestMatcher cung cấp path variables, biểu thức có thể tham chiếu các biến đó (ví dụ #username).

Một cách biểu đạt tương đương chính sách owner-or-admin:

~~~java
MvcRequestMatcher matcher =
        new MvcRequestMatcher.Builder(introspector)
                .pattern(HttpMethod.GET, "/users/{username}/profile");

http.authorizeHttpRequests(auth -> auth
        .requestMatchers(matcher)
        .access(new WebExpressionAuthorizationManager(
                "isAuthenticated() and "
                + "(#username == authentication.name or hasRole('ADMIN'))"))
        .anyRequest().denyAll());
~~~

**Đây là snippet thay thế** cho rule trong SecurityConfig, không phải một cấu hình thứ hai để chồng lên cùng URL trong project mẫu. Import tương ứng là org.springframework.security.web.access.expression.WebExpressionAuthorizationManager.

Giải thích:

- #username đại diện cho URI variable do matcher cung cấp, không phải một query parameter.
- authentication.name là tên được authentication cung cấp.
- isAuthenticated() theo expression evaluation của Spring Security phân biệt anonymous với user login; không được chỉ viết #username == authentication.name vì giá trị anonymousUser có thể bị lợi dụng nếu biểu thức không có guard.
- hasRole('ADMIN') kiểm tra ROLE_ADMIN theo role prefix thông thường.
- Nếu matcher không trích biến hoặc nhiều mapping trùng nhau, phải kiểm thử biểu thức thực tế.

Ưu điểm: rule ngắn, dễ đọc khi điều kiện đơn giản. Nhược điểm: biểu thức chuỗi có thể khó refactor, khó debug và khó test hơn Java code có kiểu rõ ràng khi policy phức tạp. Đối với RBAC/ABAC nhiều điều kiện, người dùng/tenant/data lookups, một AuthorizationManager có tên rõ hoặc service-level authorization thường dễ duy trì hơn.

Không ghép dữ liệu chưa tin cậy của người dùng trực tiếp vào **chuỗi biểu thức** được truyền cho WebExpressionAuthorizationManager. Biểu thức là policy do developer cấu hình; dữ liệu request phải được đưa vào evaluation context như biến được framework xử lý.

## 7. Cách bảo vệ tương tự ở tầng method

Một lựa chọn khác là kiểm tra quyền khi gọi controller hoặc service bằng method security:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig {
}
~~~

Với một method có tham số username, bạn có thể đặt:

~~~java
@PreAuthorize("isAuthenticated() and "
        + "(#username == authentication.name or hasRole('ADMIN'))")
@GetMapping("/users/{username}/profile")
public String profile(@PathVariable("username") String username) {
    return "PROFILE:" + username;
}
~~~

Đây là **đoạn minh họa** trong controller đã có import, và chỉ hoạt động khi bạn bật @EnableMethodSecurity, dùng @PreAuthorize với method security được cấu hình, proxy intercept đúng bean/method, tham số method được nhận diện đúng tên (qua @P hoặc tên tham số compile). Nếu sử dụng annotation trên interface hoặc gọi nội bộ cùng bean, cần hiểu giới hạn proxy/AOP.

Không thay đồng loạt HTTP authorization và method security bằng hai rule xung đột mà không biết thứ tự. Thông thường một lớp bảo vệ ở HTTP giúp chặn sớm, còn service-level protection bảo vệ dữ liệu khi method được gọi từ nhiều đường đi.

Với method-level SpEL, biến #username lấy từ **tham số Java của method**, không phải tự động từ RequestAuthorizationContext. Đây là khác biệt quan trọng so với #username trong WebExpressionAuthorizationManager khi HTTP matcher đã trích URL variable.

### Khi nào ưu tiên service-level authorization?

Giả sử profile được gọi từ HTTP API, scheduled job, message listener và một service khác. Quyền trên **bản ghi dữ liệu** không nên chỉ tồn tại trong SecurityFilterChain của HTTP, vì các đường đi nội bộ có thể bypass URL.

Service nên nhận user ID đáng tin và tài nguyên đã được tải, rồi kiểm tra owner/tenant/permission ở cùng transaction hoặc ngay trước truy vấn dữ liệu. Có thể dùng @PreAuthorize, AuthorizationManager dành cho method, PermissionEvaluator hoặc policy service rõ ràng, tùy độ phức tạp.

## 8. Chống IDOR/BOLA khi đường dẫn chứa ID bản ghi

Đây là điểm cần phân biệt để không tạo **lỗ hổng Insecure Direct Object Reference (IDOR)** hoặc Broken Object Level Authorization (BOLA).

Nếu URL là:

~~~text
GET /documents/8ac4a1d0-59de-4803-b8f6-1ea6101eeabc
~~~

Biến đường dẫn là documentId, **không phải username**. Không thể so sánh documentId với Authentication.getName() rồi coi là kiểm tra quyền đúng.

Cần:

1. Xác thực danh tính caller từ SecurityContext.
2. Lấy bản ghi tài liệu theo documentId qua repository.
3. Kiểm tra bản ghi thuộc cùng ownerId/tenantId hoặc caller có quyền đọc cụ thể.
4. Chỉ sau khi đạt policy mới trả nội dung.
5. Nếu cố tình che giấu sự tồn tại của tài liệu, có thể trả 404 cho người không được phép thay vì 403, nhưng phải nhất quán và không tiết lộ qua timing/error message.

Ví dụ pseudocode ở tầng service (các repository/domain class trong đây chỉ là minh họa, không phải file Java độc lập để compile):

~~~java
public DocumentDto getDocument(UUID documentId, String callerId) {
    Document doc = documentRepository.findById(documentId)
            .orElseThrow(NotFoundException::new);

    boolean owner = doc.getOwnerId().equals(callerId);
    boolean canRead = owner || policy.canReadDocument(callerId, doc);

    if (!canRead) {
        throw new AccessDeniedException("Access denied");
    }
    return mapper.toDto(doc);
}
~~~

Truy vấn database có thể gắn điều kiện owner trong SQL để tránh trả dữ liệu nhầm user:

~~~sql
SELECT id, owner_id, title
FROM documents
WHERE id = :document_id
  AND owner_id = :authenticated_user_id;
~~~

Điều kiện authenticated_user_id phải đến từ danh tính đã xác minh, **không** phải query parameter hoặc path variable do client tự gán. Trong multi-tenant, thường cần cả tenant ID và quyền chia sẻ/role nội bộ; chỉ kiểm tra user ID có thể chưa đủ.

Một path-matching rule tốt vẫn không thay được kiểm soát quyền trên dữ liệu thực tế. Ngược lại, một service kiểm tra quyền đúng vẫn nên có HTTP rules để chặn sớm, giảm tài nguyên bị xử lý và cung cấp phản hồi thích hợp.

### Chống “confused deputy” và header giả mạo

Nếu app đứng sau API gateway, đôi khi gateway chuyển thông tin user bằng header. Chỉ tin header khi nó được bảo vệ bằng giao thức xác thực nội bộ, được gateway kiểm soát, không thể do client công khai ghi đè, và Spring Security cấu hình xác minh rõ ràng. Không thêm logic kiểu header X-User tự khai = {username} để cấp quyền, kể cả khi app “thường chạy sau proxy”.

## 9. Rule ordering và độ rộng của mẫu đường dẫn

Trong authorizeHttpRequests, thứ tự rule có ý nghĩa: một request thường được quyết định bởi rule match đầu tiên của AuthorizationManager tương ứng.

Sai:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers("/users/**").permitAll()
        .requestMatchers("/users/{username}/profile")
            .access(ownerOrAdmin())
        .anyRequest().denyAll())
~~~

Rule /users/** rộng và permitAll đứng trước đã cho phép GET profile; rule ownerOrAdmin đặt sau có thể không bao giờ được đánh giá. Không thể sửa bằng cách nghĩ “rule cuối cùng nghiêm nhất sẽ thắng”.

Đúng: đặt matcher chuyên biệt trước, kiểm tra method, rồi xử lý các đường dẫn khác theo nhu cầu:

~~~java
.authorizeHttpRequests(auth -> auth
        .requestMatchers(profileGet).access(ownerOrAdmin())
        .anyRequest().denyAll())
~~~

Nếu API có thêm /users/public-info, phải khai báo rule riêng cho nó với phạm vi và method cụ thể. Không tùy tiện đưa anyRequest().authenticated() vào ứng dụng có dữ liệu thuộc từng user vì nó chỉ yêu cầu user login, **không** kiểm tra owner.

### HttpMethod quan trọng

GET /users/alice/profile và DELETE /users/alice/profile không có cùng tác động. Một matcher chỉ giới hạn GET cho phép đọc theo rule; DELETE không tự động kế thừa quyền nếu không có rule khác. Trong ví dụ, mọi method khác đều bị denyAll.

Nếu bạn tạo PUT/DELETE cho thao tác thay đổi dữ liệu:

- Cần định nghĩa quyền sửa/xóa riêng; thường chặt hơn quyền đọc.
- Với browser dùng cookie session, giữ CSRF protection phù hợp cho phương thức unsafe; permitAll hoặc cùng owner không tắt CsrfFilter.
- Với API sử dụng bearer token trong Authorization header và không dựa vào browser cookies, CSRF có thể được cấu hình khác tùy threat model; không disable toàn bộ khi chưa đánh giá.
- Kiểm thử cả user khác và user anonymous, cùng trường hợp method/URL bị lệch.

## 10. MvcRequestMatcher, path normalization và encoding URL

Matcher và controller cần hiểu URL nhất quán. Một số tình huống phải kiểm thử:

| Tình huống | Vấn đề có thể gặp |
| --- | --- |
| /users/alice/profile | Trường hợp chuẩn, username là alice |
| /users/Alice/profile | So sánh có phân biệt hoa/thường? User store có chuẩn hóa không? |
| /users/alice/profile/ | Dấu slash cuối có được match không tùy MVC/version/config? |
| /users/alice%20smith/profile | Percent-encoding/space có được MVC giải mã như mong muốn? |
| /users/alice%2Fadmin/profile | Encoded slash có thể bị container/proxy từ chối hoặc giải mã khác nhau |
| /users/../bob/profile | Normalization/path traversal thường bị chặn hoặc chuẩn hóa; cần bảo đảm matcher/controller đồng thuận |
| /users/alice/profile?username=bob | Path variable vẫn là alice, query độc lập |
| /users/alice/profile;v=1 | Matrix parameters và semicolon handling phụ thuộc MVC/container/firewall config |

Spring Security có StrictHttpFirewall trong các cấu hình thông thường, nhưng không nên dựa vào việc “mọi URL lạ đều đã bị chặn” mà bỏ test. Proxy, servlet mapping, securityMatcher và application routing có thể thay đổi path được nhìn thấy ở từng tầng.

**Không dùng string.startsWith("/users/" + authentication.getName()) để cấp quyền**, vì /users/alice-bad/profile có thể bắt đầu bằng /users/alice dù thuộc user khác. Không tự decode URL hai lần hoặc cắt chuỗi bằng split("/") để lấy username nếu đã có RequestMatcher/URI-template variables.

### Chuẩn hóa danh tính

Giả sử username có thể là "Alice", "alice" hoặc ký tự Unicode tương đương. So sánh equals() trong demo là **so sánh chuỗi chính xác**. Nếu identity provider/DB có quy tắc canonicalization, nên lưu và so sánh **ID nội bộ ổn định** hoặc username chuẩn hóa từ nguồn đáng tin, không tự gọi toLowerCase() vô điều kiện trên dữ liệu client.

Không hợp nhất tùy tiện các tên user theo Unicode case folding nếu user store không áp dụng cùng quy tắc; có thể cấp quyền sai chủ.

## 11. Multiple SecurityFilterChain và phạm vi áp dụng rule

Nếu ứng dụng có nhiều chain:

~~~text
@Order(1): securityMatcher("/api/**")
           -> API bearer/basic policies

@Order(2): fallback web requests
           -> form login + web policies
~~~

FilterChainProxy chọn chain đầu tiên match request. Nếu /users/{username}/profile không nằm trong chain bạn nghĩ, AuthorizationManager ownerOrAdmin có thể không chạy.

Ví dụ:

- Bạn cấu hình rule owner trong chain chỉ match /api/** nhưng controller thực ở /users/**: request không vào chain đó.
- Chain tổng quát match mọi request đứng trước chain chuyên biệt: rule phía sau bị che.
- API có servlet mapping riêng; MvcRequestMatcher dùng sai servletPath nên URI variables không được trích như dự kiến.
- Một chain dùng STATELESS nhưng test lại gửi cookie của form login từ chain khác; Authentication trong chain hiện tại có thể không như bạn suy đoán.

Luôn xác định **request → SecurityFilterChain → RequestMatcher → Authentication → AuthorizationDecision → controller/service**, và tạo integration tests cho endpoint thật trên ứng dụng đang triển khai.

## 12. Các lỗi thường gặp

### 12.1. “Bất kỳ user đã login đều xem được profile người khác”

Nguyên nhân: chỉ dùng .authenticated() trên /users/**; không có điều kiện owner. Cách sửa: dùng URI variable access policy hoặc service ownership check. Bổ sung test bob truy cập profile alice phải bị 403.

### 12.2. “Đã dùng path variable nhưng vẫn bị IDOR”

Nguyên nhân: so sánh sai đối tượng. Nếu path là documentId thì không thể so sánh documentId với username; phải tra database để biết ownerId/tenantId thật và đối chiếu với caller ID đã xác thực.

### 12.3. “Anonymous được xem /users/anonymousUser/profile”

Nguyên nhân: AnonymousAuthenticationToken có tên anonymousUser và có thể isAuthenticated() là true. Cách sửa: check authenticated theo semantics của Spring Security và loại AnonymousAuthenticationToken, hoặc expression isAuthenticated() phù hợp.

### 12.4. “context.getVariables().get('username') là null”

Nguyên nhân: matcher không bắt biến, biến viết sai tên, path rule khác match trước, securityMatcher không áp dụng, hoặc mismatch servlet path. Cách sửa: xem matcher thật được dùng, pattern và variables; policy thiếu biến phải fail closed.

### 12.5. “Controller có @PathVariable nhưng Spring Security không hiểu biến đó”

Controller mapping và security matching là hai tầng. @PathVariable không tự chia sẻ biến vào mọi custom RequestMatcher. Dùng matcher hỗ trợ URI template variables và RequestAuthorizationContext.getVariables() hoặc method-level authorization nhận tham số rõ ràng.

### 12.6. “User bob giả mạo X-User: alice rồi truy cập được”

Nguyên nhân: app tin header chưa xác minh. Cách sửa: Authentication phải đến từ security mechanism tin cậy; chỉ tin proxy headers khi gateway/signed headers và network boundary thực sự được bảo vệ.

### 12.7. “admin vẫn bị từ chối”

Kiểm tra authority thực tế: .roles("ADMIN") sinh ROLE_ADMIN; nếu hệ thống dùng .authorities("ADMIN") không có prefix, policy phải đồng nhất. Không tự bỏ check để test pass.

### 12.8. “Path /users/alice/profile?username=bob bị nhận là bob”

Bạn đã lấy request.getParameter("username") thay vì variables.get("username"), hoặc controller dùng query thay path. Hãy phân biệt @PathVariable với @RequestParam và test trường hợp có cả hai.

### 12.9. “Rule owner không có tác dụng vì permitAll đứng trước”

Một matcher rộng như /users/**.permitAll() ở trước rule owner có thể cho phép request ngay. Cần rà thứ tự và scope mỗi matcher, dùng denyAll cho đường dẫn chưa định nghĩa.

### 12.10. “Đổi sang JWT rồi Authentication.getName() không còn username”

JWT principal name có thể lấy từ sub hay claim được cấu hình; username hiển thị không nhất thiết bằng sub. Chuyển policy sang stable ID hoặc mapping đáng tin, đừng yêu cầu client gửi claim username như bằng chứng.

### 12.11. “Kiểm thử @WithMockUser pass nhưng production fail”

Test mock Authentication có getName và roles do test tự đặt, nhưng production authentication principal khác. Bổ sung integration tests qua cơ chế thật (Basic, bearer, session), xác minh principal name semantics và role mapping.

### 12.12. “Chỉ bảo vệ URL, nhưng service vẫn bị gọi từ job/message consumer”

Authorization HTTP không chạy với đường gọi trực tiếp ngoài MVC. Tài nguyên quan trọng cần service-level authorization hoặc hệ thống policy nghiệp vụ, cùng kiểm thử các entrypoint tương ứng.

### 12.13. “So sánh chuỗi username trực tiếp giữa tenant”

Cùng username có thể tồn tại ở nhiều tenant. Phải kiểm tra tenant ID và user ID; không dùng username làm khóa owner toàn cục khi hệ thống là multi-tenant.

### 12.14. “Không nhận được AuthorizationDecision như mong muốn”

Kiểm tra method rule, RequestMatcher và SecurityFilterChain đã chọn, auth state, variables thực sự capture, role prefix. Khi debug tuyệt đối không in raw Authorization header, session cookie hoặc access token vào log công khai.

## 13. Checklist thiết kế và kiểm thử production

1. **Xác định chủ thể:** Authentication.getName() là username, subject hay ID? Đã canonical hóa theo policy chưa?
2. **Xác định tài nguyên:** URI variable là username, userId hay resourceId? Nếu là ID bản ghi phải tra owner/tenant trong nguồn dữ liệu.
3. **Chọn RequestMatcher đúng MVC/Servlet mapping** và HttpMethod; kiểm tra variables được capture đúng.
4. **Không tin path/query/header do client khai** như danh tính của request; chỉ dùng Authentication đến từ cơ chế xác minh tin cậy.
5. **Check anonymous rõ ràng**, kể cả path có giá trị anonymousUser.
6. **Chính sách fail closed:** thiếu path variable, matcher lỗi hoặc URL không được định nghĩa phải không được phép truy cập.
7. **Sắp xếp rule đúng thứ tự:** rule cụ thể trước rule rộng; không để permitAll hoặc authenticated rộng vượt qua ownership.
8. **Phân quyền role thực tế:** thống nhất ROLE_ADMIN, hasRole/hasAuthority và chính sách data privacy.
9. **Tách quyền HTTP khỏi data ownership:** mọi service access path nhạy cảm vẫn cần bảo vệ phù hợp.
10. **Kiểm thử cả positive/negative:** owner, other user, admin, anonymous, forged header, query khác path và URL chưa match.
11. **Kiểm thử URL lạ:** encoding, trailing slash, case, Unicode, matrix parameters, servletPath và reverse proxy.
12. **Nhiều security chain:** đảm bảo endpoint rơi vào chain dự kiến; test method-safe và unsafe riêng.
13. **Khi dùng JWT/OIDC**, xác nhận subject/claim mapping từ authentication provider và tenant semantics.
14. **Không lộ dữ liệu nhạy cảm:** log authorization decision có correlation ID riêng, không log raw credentials/cookie/token.
15. **Theo dõi lỗi và thay đổi:** sau nâng Spring Boot/Spring Security, kiểm thử behavior của matcher/path mapping trên endpoint thật.

## 14. Câu hỏi tự luyện

**Câu 1.** GET /users/bob/profile do alice gọi, có thể lấy bob từ @PathVariable và kết luận request do bob gửi không?

**Đáp án:** không. Path variable do client chọn. Authentication từ Spring Security mới biểu thị identity của caller. Muốn bảo vệ owner thì so sánh bob với danh tính đã xác thực.

**Câu 2.** RequestAuthorizationContext.getVariables().get("username") lấy username từ đâu?

**Đáp án:** từ việc RequestMatcher tương ứng match URI template {username}, không phải từ X-User header hay query parameter cùng tên.

**Câu 3.** Vì sao chỉ dùng current.isAuthenticated() có thể nguy hiểm trong policy tự viết?

**Đáp án:** AnonymousAuthenticationToken có thể báo true, dù người gọi thực tế là anonymous. Phải loại anonymous hoặc dùng cơ chế kiểm tra authenticated phù hợp.

**Câu 4.** Rule .requestMatchers("/users/**").permitAll() trước owner rule có vấn đề gì?

**Đáp án:** rule rộng có thể match trước, cho phép request và không cần đánh giá owner rule phía sau.

**Câu 5.** Nếu URL /documents/{id} chứa ID tài liệu, có thể so sánh id với Authentication.name không?

**Đáp án:** không. Phải nạp dữ liệu tài liệu, kiểm tra ownerId/tenantId và permission theo caller ID đã xác minh.

**Câu 6.** GET /users/alice/profile?username=bob, matcher capture giá trị nào?

**Đáp án:** nếu pattern /users/{username}/profile, variable username là alice; query username=bob là dữ liệu riêng.

**Câu 7.** Muốn ADMIN xem profile mọi user thì làm gì?

**Đáp án:** thêm nhánh role/authority được định nghĩa rõ, bảo đảm người gọi đã xác thực, URL variable hợp lệ và test cả trường hợp admin, non-admin, anonymous.

**Câu 8.** Nếu một service được gọi từ scheduled job mà không đi qua HTTP SecurityFilterChain, rule owner HTTP có chạy không?

**Đáp án:** không. Cần policy ở service/domain layer cho dữ liệu nhạy cảm hoặc cơ chế authorization phù hợp với entrypoint đó.

**Câu 9.** Khi đổi từ HTTP Basic sang OIDC, getName() có chắc vẫn là username?

**Đáp án:** không. Có thể là subject hoặc claim khác; phải xác định principal name semantics trước khi so sánh với URL.

**Câu 10.** Với app nhiều SecurityFilterChain, sao owner AuthorizationManager không chạy?

**Đáp án:** request có thể được chọn vào chain khác theo securityMatcher/@Order, hoặc một rule ở chain match trước. Cần kiểm tra chain/matcher/method/variables bằng integration test.

## Tổng kết

**Lấy biến đường dẫn là việc đọc dữ liệu định tuyến, không phải xác minh danh tính.** Spring Security Servlet cho phép truyền URI template variables từ RequestMatcher vào RequestAuthorizationContext, để AuthorizationManager so sánh **giá trị URL** với **Authentication đã được xác thực** và các quyền như ROLE_ADMIN.

Công thức thực tế của ví dụ là: **đúng HTTP method + đúng route + caller thực sự authenticated + biến username hợp lệ + (caller là owner hoặc admin)**. Nếu không đạt, từ chối trước controller; các URL chưa định nghĩa nên fail closed.

Với ứng dụng thật, đừng chỉ dừng ở so sánh chuỗi username. Hãy dùng **user ID/tenant ID ổn định**, kiểm tra ownership của **bản ghi trong database**, kiểm thử những request do user khác cố tình tạo và giữ chính sách nhất quán trên cả HTTP, service lẫn các luồng không qua web.