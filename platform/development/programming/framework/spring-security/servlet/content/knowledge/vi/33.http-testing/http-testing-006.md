# Kiểm tra authenticated, unauthenticated, status, header và chuyển hướng trong Spring Security Servlet

## 1. Mục tiêu bài học

Khi kiểm thử bảo mật HTTP trong **Spring Security Servlet** với **Spring MVC** và **MockMvc**, chỉ xác minh rằng endpoint trả về 200 là chưa đủ. Một ca kiểm thử đúng phải trả lời đồng thời: request có **được xác thực** hay không, **được phân quyền** hay không, HTTP **status** là gì, các **response headers** có đúng không và browser/API client sẽ được **chuyển hướng** đến đâu.

Một sự khác biệt quan trọng: **Authentication của Spring Security** là trạng thái bảo mật bên trong request, trong khi **HTTP status, headers và Location** là kết quả giao tiếp với client. Chúng liên quan nhưng không đồng nghĩa.

Ví dụ:
- Người dùng chưa đăng nhập gọi API HTTP Basic: thường **401 Unauthorized**, kèm **WWW-Authenticate**.
- Người dùng đã đăng nhập nhưng thiếu ROLE_ADMIN: thường **403 Forbidden**.
- Người dùng chưa đăng nhập mở trang web cần phiên đăng nhập: thường **302 Found** với **Location: /login**.
- Người dùng đăng nhập thành công bằng form: thường **302** đến trang đích.
- Client gửi request tới endpoint public: có thể **200** dù **chưa có Authentication của người dùng thực**.

Bài này giúp bạn xây dựng test đáng tin cho các trường hợp trên, hiểu các công cụ **spring-security-test**, đọc kết quả MockMvc, kiểm tra cả **authenticated/unauthenticated** lẫn **status/header/redirect**, và phân biệt một test mock user với test authentication thực.

## 2. Phân biệt bốn chiều cần kiểm thử

| Chiều | Câu hỏi | Công cụ kiểm thử |
| --- | --- | --- |
| **Authentication** | Spring Security đã xác thực request chưa, là user nào? | **authenticated()**, **unauthenticated()**, **@WithMockUser**, **user()**, hoặc thực sự đi qua Basic/form login |
| **Authorization** | User này có được truy cập tài nguyên/role/scope cần thiết không? | Kiểm tra **200/403** và nội dung dữ liệu; test nhiều authorities |
| **HTTP status** | Client nhận mã HTTP nào? | **status().isOk()**, **isUnauthorized()**, **isForbidden()**, **is3xxRedirection()** |
| **Headers/redirect** | Response có challenge, cache directives, Location, Content-Type đúng không? | **header().string(...)**, **header().exists(...)**, **redirectedUrl(...)**, **redirectedUrlPattern(...)** |

Một test có thể xác minh nhiều chiều trong một request. Ví dụ, thiếu Bearer token hay Basic credentials thì **status 401** cần đi kèm **WWW-Authenticate** đúng scheme. Ngược lại, nếu web app dùng form login, unauthenticated request thường nhận **302 tới trang login**, không phải 401.

**Không hardcode một status cho mọi cấu hình:** HTTP Basic, Bearer, formLogin, oauth2Login, custom entry point, request matcher, CSRF và exception handlers quyết định kết quả thật. Status kỳ vọng phải xuất phát từ **security contract** của API hoặc giao diện đang thử.

## 3. Authentication != HTTP 200

Một endpoint có thể public:

~~~java
.requestMatchers("/api/public").permitAll()
~~~

Khi chưa đăng nhập, client vẫn nhận **200**. Điều này không chứng minh request đã được xác thực; nó chỉ chứng minh authorization rule cho phép anonymous truy cập.

Một endpoint bảo vệ:

~~~java
.requestMatchers("/api/admin").hasRole("ADMIN")
~~~

User alice đã xác thực có **ROLE_USER** nhưng không có **ROLE_ADMIN** sẽ bị từ chối **403**. Alice **authenticated**, nhưng **not authorized for this resource**.

**AnonymousAuthenticationToken** có thể tồn tại và thậm chí **isAuthenticated() trả true** theo semantics của implementation. Do đó không dùng:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Sai nếu dùng để kết luận user là người đăng nhập thật.
}
~~~

để thay cho Spring Security authorization rules. Khi cần phân biệt anonymous với user thực, framework có **AuthenticationTrustResolver**; khi bảo vệ endpoint, ưu tiên **authenticated()**, **fullyAuthenticated()**, **hasRole(...)** hoặc **hasAuthority(...)** theo chính sách.

Một cách đọc tư duy kiểm thử:

~~~text
        Request
           |
           v
  Có credentials/token?
           |
     +-----+------+
     |            |
    Không         Có
     |            |
  Public?    Xác thực hợp lệ?
   |   |         |    |
  Có  Không      Không Có
   |   |          |    |
  200 401/302    401  Kiểm tra quyền
                      |         |
                    Đủ        Thiếu
                     |          |
                    200        403
~~~

Đây là **sơ đồ khái quát**, không phải mọi ứng dụng đều trả đúng các mã này: framework và các entry points/custom handlers có thể trả 400/404/302 hoặc response riêng. Đặc biệt **CSRF** có thể khiến POST bị **403** dù user hợp lệ; không tự động coi 403 là thiếu role.

## 4. Status: 200, 201, 204, 302, 401, 403, 404 và 405

| Status | Diễn giải trong bài kiểm thử | Cần kiểm tra thêm |
| --- | --- | --- |
| **200 OK** | Endpoint xử lý thành công | JSON/body và quyền sở hữu dữ liệu có đúng không |
| **201 Created** | Tạo tài nguyên thành công | Header **Location**, body, authorization và idempotency |
| **204 No Content** | Thao tác thành công, không có body | Không đòi JSON response; cân nhắc side effect |
| **301/302/303/307/308** | Chuyển hướng | Header **Location**, hướng đích, method semantics, cookie/session |
| **401 Unauthorized** | Chưa xác thực hoặc credentials không được chấp nhận | **WWW-Authenticate**, không vô tình redirect login UI |
| **403 Forbidden** | Đã xác thực nhưng thiếu quyền, hoặc CSRF/policy từ chối | Phân biệt authorization với CSRF và AccessDeniedHandler |
| **404 Not Found** | Không có route/resource hoặc cố ý che sự tồn tại | Xác minh request có qua security chain mong đợi không |
| **405 Method Not Allowed** | Route không hỗ trợ HTTP method | Header **Allow** nếu framework trả, không suy từ authentication |

Tên 401 là “Unauthorized”, nhưng về nghĩa HTTP authentication, thường là **chưa có xác thực hợp lệ**. Một request đã xác thực nhưng thiếu role thông thường là **403**.

**Client login qua browser:** status 302 không nhất thiết là lỗi. Nó có thể đúng hoàn toàn khi user chưa có session web và phải vào login page. API dành cho máy-to-máy thường muốn **401/403 trực tiếp**, không muốn nhận HTML login page qua redirect.

## 5. Kiểm tra header đúng mục đích

### 5.1. WWW-Authenticate

Với HTTP Basic, 401 thường kèm một challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Realm cụ thể phụ thuộc cấu hình; test không nên đóng đinh **Realm** nếu đó không phải contract. Để kiểm tra đúng cơ chế:

~~~java
.andExpect(status().isUnauthorized())
.andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE, startsWith("Basic")))
~~~

Với OAuth2 Resource Server Bearer, scheme thường là **Bearer** và có thể kèm **error** / **error_description** hoặc **scope** theo RFC/implementation. Nếu API đang mong Bearer nhưng test chỉ thấy Basic hoặc redirect /login, có thể request đã vào **sai SecurityFilterChain**.

### 5.2. Location

Khi trả redirect, **Location** cho biết client sẽ điều hướng đến URL nào:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Test:

~~~java
.andExpect(status().is3xxRedirection())
.andExpect(header().string(HttpHeaders.LOCATION, endsWith("/login")))
~~~

Sử dụng **redirectedUrl("/login")** nếu contract và test environment bảo đảm URL chính xác. Nếu Location có thể là absolute **http://localhost/login** hoặc relative **/login**, có thể dùng **redirectedUrlPattern("**/login")** hoặc Hamcrest **endsWith("/login")**; chú ý chỉ nới lỏng so khớp khi đó là lựa chọn có chủ đích, không che một redirect sai domain.

Với redirect có query string như **/login?error**, nên kiểm tra query hoặc redirect pattern rõ ràng; dấu **?** trong Ant-style pattern có thể là ký tự wildcard, vì vậy test nên dùng matcher phù hợp với contract.

### 5.3. Cache-Control, Content-Type và các security headers

Spring Security có thể thiết lập các header như **Cache-Control**, **X-Content-Type-Options**, **X-Frame-Options** tùy phiên bản/cấu hình. Đừng giả định mọi header luôn xuất hiện ở mọi route hoặc mọi bản Spring Security. Khi contract yêu cầu, dùng:

~~~java
.andExpect(header().exists(HttpHeaders.CACHE_CONTROL))
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
~~~

Nếu cần kiểm tra **Content-Security-Policy**, **Strict-Transport-Security**, **Referrer-Policy**, hoặc cookie **Secure/HttpOnly/SameSite**, hãy dựa vào cấu hình đã bật và điều kiện request. Ví dụ HSTS thường liên quan HTTPS; test HTTP mock không nên tự khẳng định HSTS luôn phải xuất hiện.

### 5.4. Không đọc sai request headers thành response headers

**Authorization: Basic ...** là request header từ client. **WWW-Authenticate: Basic ...** là response header challenge của server. **Location** là response header khi redirect. **Cookie** client gửi trong request khác với **Set-Cookie** server trả. Đặt assertion vào **đúng phía** để test không vô tình pass với dữ liệu sai.

## 6. Spring Security Test và MockMvc: hai nhóm helper

### 6.1. RequestPostProcessors: tạo đầu vào

Spring Security Test có:

- **user("alice").roles("USER")**: tạo Authentication mock cho request.
- **anonymous()**: tạo ngữ cảnh anonymous trong test.
- **httpBasic("alice", "password")**: tạo HTTP Basic Authorization header để filter thực kiểm tra credentials.
- **csrf()**: thêm CSRF token hợp lệ cho POST/PUT/DELETE test nếu app sử dụng CSRF protection.
- **jwt()**: tạo JWT Authentication mock, dùng khi test authorization của resource-server endpoint.
- **oauth2Login()**: mock tình huống user đã đăng nhập OAuth2, không chạy authorization code flow thật.

**Phân biệt quan trọng:** **user()**, **@WithMockUser**, **jwt()** không kiểm tra password, chữ ký token hoặc liên lạc IdP. Chúng chủ yếu dựng Authentication để kiểm thử **authorization và controller**. **httpBasic()** chỉ tạo header; khi chạy Spring Security filter chain, backend vẫn phải kiểm tra username/password.

### 6.2. ResultMatchers: kiểm tra đầu ra

~~~java
// Spring MVC HTTP-level:
.andExpect(status().isOk())
.andExpect(status().isUnauthorized())
.andExpect(status().isForbidden())
.andExpect(status().is3xxRedirection())

// Header-level:
.andExpect(header().string(HttpHeaders.LOCATION, endsWith("/login")))
.andExpect(header().exists(HttpHeaders.CACHE_CONTROL))

// Redirect-level:
.andExpect(redirectedUrlPattern("**/login"))

// JSON-level:
.andExpect(jsonPath("$.name").value("alice"))
~~~

Ngoài ra, **SecurityMockMvcResultMatchers** có **authenticated()** và **unauthenticated()** để kiểm tra authentication state mà Spring Security test quan sát được. Đây là phép kiểm khác với status:

~~~java
// Trích đoạn minh họa trên request đã được gắn test Authentication.
mvc.perform(get("/api/me").with(user("alice").roles("USER")))
        .andExpect(status().isOk())
        .andExpect(authenticated().withUsername("alice"));
~~~

Dòng **authenticated()** cần static import từ **org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers**. Trong dự án dùng API stateless, cách lưu/đọc context của test cần phù hợp với filter chain, không nên kết luận failed result matcher đồng nghĩa HTTP status sai.

Test **unauthenticated()** phù hợp khi muốn chứng minh request không có user đã xác thực, nhưng **status 200 của public endpoint** không tự đảm bảo điều đó. Sử dụng các matchers riêng thay vì so sánh response status với authentication state một cách suy đoán.

## 7. Dự án hoàn chỉnh: hai SecurityFilterChain, HTTP Basic API và form login web

Để thấy rõ hai contract khác nhau, dự án dưới đây dùng:

- **API /api/**: HTTP Basic; không redirect login, trả 401 khi thiếu/sai credentials và 403 khi thiếu quyền.
- **Web /dashboard**: form login; user chưa đăng nhập được redirect 302 đến **/login**; login thành công redirect đến **/dashboard**.
- **/api/public**: cho phép anonymous để chứng minh **200 không đồng nghĩa authenticated**.
- **/api/admin**: yêu cầu ROLE_ADMIN.
- **Cache-Control**, **Content-Type**, **WWW-Authenticate**, **Location**, **CSRF** và session được đưa vào test có chủ đích.

Dùng **Java 17**, **Spring Boot 3.4.5**, Maven, Spring MVC và Spring Security Servlet. Phiên bản này được pin cố định để ví dụ dễ tái hiện; không ngầm tuyên bố là phiên bản mới nhất.

Cấu trúc:

~~~text
security-http-tests/
├── pom.xml
└── src/
    ├── main/java/demo/httptest/SecurityHttpApplication.java
    └── test/java/demo/httptest/SecurityHttpTests.java
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
    <artifactId>security-http-tests</artifactId>
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

### 7.2. src/main/java/demo/httptest/SecurityHttpApplication.java

~~~java
package demo.httptest;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityHttpApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityHttpApplication.class, args);
    }
}

@Configuration
class TestSecurityConfiguration {
    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}alice-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin-pass")
                        .roles("USER", "ADMIN")
                        .build());
    }

    // Chain thứ nhất chỉ áp dụng cho /api/**.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Demo chỉ có GET. Không tắt CSRF máy móc.
                .build();
    }

    // Chain thứ hai dành cho web và trang login.
    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .defaultSuccessUrl("/dashboard", true))
                .build();
    }
}

@RestController
class DemoController {
    @GetMapping("/api/public")
    Map<String, String> publicApi() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication auth) {
        return Map.of("name", auth.getName());
    }

    @GetMapping("/api/admin")
    Map<String, String> admin(Authentication auth) {
        return Map.of("admin", auth.getName());
    }

    @GetMapping("/dashboard")
    Map<String, String> dashboard(Authentication auth) {
        return Map.of("welcome", auth.getName());
    }
}
~~~

**Giải thích cấu hình:**

1. **@Order(1) + securityMatcher("/api/**")** bảo đảm request API đi vào Basic chain trước web chain. API request không có Basic credentials được xử lý bằng HTTP Basic entry point, không redirect đến trang login.
2. **/api/public** dùng **permitAll()**; request anonymous vẫn được phép thành công.
3. **/api/admin** yêu cầu ROLE_ADMIN. User alice có ROLE_USER nhưng không có ROLE_ADMIN.
4. **SessionCreationPolicy.STATELESS** ở API không lưu trạng thái xác thực vào HttpSession; mỗi lần gọi API có thể phải gửi Basic credentials. Đây là demo HTTP Basic qua **localhost**, không nên dùng plaintext HTTP Basic cho production.
5. **Web chain** có form login và **defaultSuccessUrl("/dashboard", true)**, nên sau login thành công nó redirect đến dashboard không phụ thuộc saved request. Với ứng dụng thật, có thể dùng saved request/default target tùy UX.
6. Web login dùng **HttpSession** theo mặc định và còn **CSRF**. Vì vậy POST login trong test cần **csrf()**.
7. Demo cố ý chỉ có GET ở API. Nếu thêm POST/PUT/DELETE, đặc biệt khi browser tự gửi Basic/cookie credentials, cần thiết kế và kiểm thử **CSRF**; không copy việc disable CSRF tùy tiện.
8. **{noop}alice-pass** và **{noop}admin-pass** là dữ liệu bài học, không phải thiết kế password production; triển khai thật cần password encoder thích hợp, TLS, quản lý credentials và chính sách bảo mật.
9. Chỉ có **SecurityFilterChain** được khai báo, không có một filter custom khác làm thay đổi status. Vì vậy các HTTP assertions trong mục sau trực tiếp mô tả hai entry points của bài.

## 8. Bộ test MockMvc đầy đủ: status, headers, redirect và session

Tạo **src/test/java/demo/httptest/SecurityHttpTests.java**:

~~~java
package demo.httptest;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.endsWith;
import static org.hamcrest.Matchers.startsWith;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHttpTests {
    @Autowired
    MockMvc mvc;

    @Test
    void publicApiAllowsUnauthenticatedRequest() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void apiWithoutCredentialsReturns401AndBasicChallenge()
            throws Exception {
        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic")))
                .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }

    @Test
    void wrongBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        HttpHeaders.WWW_AUTHENTICATE,
                        startsWith("Basic")));
    }

    @Test
    void validBasicCredentialsReturn200AndExpectedHeaders()
            throws Exception {
        mvc.perform(get("/api/me")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        HttpHeaders.CACHE_CONTROL,
                        containsString("no-store")))
                .andExpect(jsonPath("$.name").value("alice"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403()
            throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }

    @Test
    void adminCanReachAdminApi() throws Exception {
        mvc.perform(get("/api/admin")
                        .with(httpBasic("admin", "admin-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.admin").value("admin"));
    }

    @Test
    void anonymousWebRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        endsWith("/login")));
    }

    @Test
    void defaultLoginPageIsHtml() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML));
    }

    @Test
    void loginWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "alice")
                        .param("password", "alice-pass"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongFormPasswordRedirectsToLoginError() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        endsWith("/login?error")));
    }

    @Test
    void successfulLoginRedirectsAndSessionCanOpenDashboard()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "alice-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string(
                        HttpHeaders.LOCATION,
                        endsWith("/dashboard")))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/dashboard").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.welcome").value("alice"));
    }
}
~~~

**11 test methods** kiểm tra public, thiếu credentials, Basic sai/đúng, role, redirect, login page HTML, CSRF, login failure, login success và session continuity. Kết quả chạy thật phụ thuộc dependencies/version/Servlet config, nên phải dùng **mvn test** để xác nhận; mã này được thiết kế theo Spring Security Servlet mặc định của cấu hình đã nêu, không giả định tồn tại external IdP.

### 8.1. Kiểm tra từng assertion quan trọng

**Case A — anonymous API:** GET /api/public trả **200**. Test kiểm tra JSON public; không được ghi “user đã login” chỉ vì status 200.

**Case B — unauthenticated API:** GET /api/me không credentials trả **401**, kèm **WWW-Authenticate: Basic ...**, không có **Location**. Nếu nhận 302 và Location /login, kiểm tra securityMatcher /api/** và thứ tự các SecurityFilterChain.

**Case C — sai mật khẩu:** Gửi Basic header nhưng không vượt qua AuthenticationManager. Test vẫn phải nhận 401. Điều này khác hẳn test **.with(user(...))** vốn mô phỏng người đã xác thực và không thử password.

**Case D — user hợp lệ:** HTTP Basic alice đúng password nhận **200**, body có name alice. Test xác nhận **Cache-Control** có **no-store** theo default header writer ở cấu hình demo. Nếu dự án thay header policy, sửa test theo **hợp đồng đã được quyết định**, không chỉ xóa assertion.

**Case E — role:** alice hợp lệ nhưng thiếu ADMIN nhận **403**. Admin đủ ROLE_ADMIN nhận **200**. Đây là sự khác nhau giữa Authentication và Authorization.

**Case F — web redirect:** GET /dashboard không session nhận **3xx** và **Location** kết thúc bằng **/login**. Cần kiểm tra cả status và đích chuyển hướng; test chỉ assert 302 không phát hiện redirect nhầm domain hoặc route.

**Case G — CSRF:** POST /login không CSRF bị chặn 403 trước khi login filter xử lý; POST có **csrf()** đến form login. Đây là ví dụ vì sao “403” không luôn có nghĩa thiếu role.

**Case H — login failure:** credentials không đúng được redirect tới **/login?error**. Đây là flow browser, không phải HTTP Basic challenge.

**Case I — login success:** POST /login hợp lệ trả redirect tới **/dashboard**; test lấy HttpSession do login tạo rồi thực hiện request tiếp theo với session đó. Chỉ kiểm tra redirect sẽ không chứng minh phiên đăng nhập có thể dùng ở request tiếp theo.

### 8.2. Vì sao không dùng username của response để kiểm tra mọi thứ?

Một endpoint vô tình trả **{"name":"alice"}** từ một biến hardcoded vẫn có thể pass JSON assertion. Vì vậy test nên phối hợp:
- Status/challenge/redirect theo security contract.
- Authentication thật ở test phù hợp: Basic login, form login hoặc signed JWT integration.
- Authorization positive và negative theo roles.
- Kiểm tra controller trả dữ liệu được xác định từ principal, không phải request parameter.
- Với tài nguyên có chủ sở hữu, kiểm tra **record ownership**, không chỉ status và username.

## 9. Lệnh chạy và HTTP ví dụ

Tại thư mục gốc Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Các request thử cục bộ:

~~~bash
# API public: dự kiến 200
curl -i http://localhost:8080/api/public

# API protected chưa đăng nhập: dự kiến 401 và WWW-Authenticate
curl -i http://localhost:8080/api/me

# Basic authentication đúng: dự kiến 200
curl -i -u alice:alice-pass http://localhost:8080/api/me

# User thiếu ROLE_ADMIN: dự kiến 403
curl -i -u alice:alice-pass http://localhost:8080/api/admin

# API admin với admin user: dự kiến 200
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Web chưa login: dự kiến 302 và Location
curl -i http://localhost:8080/dashboard

# Trang login: dự kiến 200 HTML
curl -i http://localhost:8080/login
~~~

**Chú ý:** curl mặc định **không tự theo redirect** khi thiếu tùy chọn -L; sử dụng **-i** để quan sát status và Location. Nếu bật **-L**, curl sẽ tiếp tục đến /login và kết quả cuối cùng có thể là 200 HTML, làm người đọc nhầm rằng /dashboard trả 200. Trong test bảo mật, cần quan sát cả **initial response** và redirect chain.

Lệnh **curl -u** có thể xuất hiện trong shell history; không sử dụng mật khẩu thật theo cách này ở production. HTTP Basic trong thực tế phải được bảo vệ bằng HTTPS. Ví dụ minh họa localhost có credentials giả chỉ để học tập.

## 10. Test authenticated() và unauthenticated() của Spring Security

Đôi khi bạn muốn assert **trạng thái security** chứ không chỉ status HTTP. Spring Security Test cung cấp:

~~~java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
~~~

Sử dụng trong một test method (trích đoạn, không phải file độc lập):

~~~java
mvc.perform(get("/api/me")
                .with(user("alice").roles("USER")))
        .andExpect(status().isOk())
        .andExpect(authenticated().withUsername("alice"));
~~~

Với một endpoint public, có thể kiểm tra rằng request không được xác thực thực sự qua matcher **unauthenticated()** nếu test setup/security chain đúng. Tuy nhiên, trên hệ thống có anonymous authentication, kiểm tra **anonymous vs authenticated** cần dựa trên semantics của Spring Security test, không chỉ **Authentication != null**.

**Sự khác nhau giữa test mock và test thật:**

| Cách test | Kiểm tra được | Chưa kiểm tra được |
| --- | --- | --- |
| .with(user("alice")) | Authorization và controller với mock principal | Password encoder, HTTP Basic header, session login |
| @WithMockUser | SecurityContext mock trong test | SSO/OIDC/JWT validation thật |
| .with(httpBasic(...)) | Header Basic + filter/provider xử lý credentials khi MockMvc có filters | HTTPS thật, proxy, browser session |
| POST /login với csrf() | Login form filter, CSRF, session/redirect | External SSO provider nếu không được cấu hình |
| .with(jwt()) | JWT principal/authorities giả lập | JWT signature, issuer, audience, key rotation |
| HTTP integration test với token ký hợp lệ | Authentication ngoài đời gần thực hơn | Cần thêm gateway/proxy/authorization E2E nếu kiến trúc có |

Nếu test chỉ dùng **@WithMockUser** rồi tuyên bố form login/Basic password đã hoạt động, đó là kết luận sai. Nên có cả **authorization unit tests** và **authentication integration tests** tương ứng với cơ chế thực tế.

## 11. Kiểm tra redirect và saved request

Spring Security có thể ghi lại request chưa xác thực và chuyển user về URL ban đầu sau login. Điều đó phụ thuộc cấu hình **RequestCache**, **SavedRequestAwareAuthenticationSuccessHandler**, default target URL và session policy.

Trong ví dụ ở mục 7, **defaultSuccessUrl("/dashboard", true)** cố ý đặt **alwaysUse** thành true, nên sau login thành công người dùng được chuyển đến /dashboard kể cả khi có saved request. Test có thể assert đích cụ thể.

Nếu đổi sang behavior phục hồi saved request:
1. Gọi GET /reports trước khi login.
2. Nhận 302 /login; request được lưu theo cấu hình.
3. Lấy cùng HttpSession và gửi POST /login với CSRF hợp lệ.
4. Kiểm tra redirect quay lại /reports.
5. Gọi /reports với session, xác nhận nội dung đúng user.

**Không bắt buộc mọi ứng dụng phải redirect về URL ban đầu.** Một ứng dụng có thể cố ý đưa user về dashboard, MFA step-up hoặc trang lựa chọn tenant. Điều cần kiểm thử là **contract đã thiết kế**, bao gồm kiểm soát **open redirect**.

### Tránh open redirect

Không cho client tùy ý cung cấp URL ngoài ứng dụng làm điểm chuyển hướng sau login mà không kiểm tra allowlist/same-origin policy. Test nên bao gồm:
- Relative URL hợp lệ.
- URL ngoài domain bị từ chối hoặc chuẩn hóa.
- URL với scheme hoặc ký tự encoded bất thường không chuyển người dùng sang trang attacker.
- Saved request không chuyển sang tài nguyên mà user đã mất quyền truy cập.

**Location matching** không chỉ là kiểm tra chuỗi; khi cần bảo mật, còn phải kiểm tra **scheme, host, path và query** theo policy.

## 12. Session, cookie và CSRF khi kiểm thử browser login

Trong web flow, login thành công thường tạo **HttpSession** và cookie phiên. Với **MockMvc**, bạn có thể chuyển trực tiếp **MockHttpSession** sang request tiếp theo, như test ở mục 8. Trên trình duyệt thật, client thường nhận cookie qua **Set-Cookie** rồi gửi lại qua **Cookie**.

**Lưu ý kỹ thuật:** Không nên assert cứng rằng response MockMvc POST /login luôn chứa Set-Cookie, vì MockMvc không phải một Servlet container mạng đầy đủ và cách cookie được tạo có thể khác server thật. Nếu yêu cầu xác minh **Secure, HttpOnly, SameSite**, dùng thêm embedded-server/HTTP integration tests trong cấu hình TLS/proxy tương ứng.

**CSRF là kiểm soát riêng với Authentication.** Một user đã đăng nhập bằng cookie vẫn có thể bị 403 ở POST nếu thiếu CSRF token. Spring Security Test cung cấp **csrf()** để mô phỏng token hợp lệ, hoặc **csrf().useInvalidToken()** khi muốn kiểm tra token sai.

Ví dụ trích đoạn:

~~~java
mvc.perform(post("/action")
                .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
~~~

Đoạn này chỉ có ý nghĩa khi dự án thật có route và CSRF được bật. Không copy vào bài demo rồi kỳ vọng test endpoint **/action** không tồn tại. Khi API dùng Bearer token gửi qua Authorization header và không dùng credentials tự động của browser, có thể thiết kế khác, nhưng phải đánh giá CSRF theo **toàn bộ cơ chế xác thực**, không đơn giản tắt cho mọi endpoint.

## 13. Kiểm thử content, body và JSON cùng security

**Status đúng nhưng dữ liệu sai** vẫn là một test thiếu. Đối với endpoint **/api/me**, nên xác minh:

~~~java
.andExpect(status().isOk())
.andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
.andExpect(jsonPath("$.name").value("alice"))
~~~

Trong API thật, có thể thêm:
- ID của resource trả về thuộc về principal đang gọi.
- Tenant ID/scope không bị lấy từ header hoặc query parameter chưa kiểm tra.
- Body không chứa credentials, raw access token, refresh token, cookie hoặc SecurityContext serialized.
- Header cache đúng nếu response nhạy cảm.
- Không trả dữ liệu 200 cho user không có quyền chỉ vì URL matching sai.
- Error body không tiết lộ token, thông tin user hoặc stack trace.

Đừng viết test chỉ so sánh **response.getStatus() == 200**, vì test đó không phát hiện endpoint vô tình trả dữ liệu của tài khoản khác. Cũng không nên dựa vào thứ tự key JSON; dùng **jsonPath** với tên property cụ thể.

## 14. API Bearer token và OAuth2 login: đừng nhầm entry point

Dự án ví dụ dùng HTTP Basic và form login, nhưng cùng tư duy áp dụng cho OAuth2:

**Resource Server Bearer:**
- Không token/sai token: thường **401**, header **WWW-Authenticate: Bearer ...**.
- Token hợp lệ thiếu scope: thường **403**.
- Token hợp lệ đủ scope: **200**, kiểm tra quyền tài nguyên.
- Test MockMvc với **jwt()** kiểm tra authorization; test chữ ký/issuer/audience cần decoder hoặc integration fixture thật.

**OAuth2/OIDC Login web:**
- User chưa login: thường **302** đến endpoint bắt đầu login như **/oauth2/authorization/{registrationId}**, hoặc trang chọn nhà cung cấp.
- Login thành công có thể tạo session/cookie và redirect về saved request/target URL.
- Cần test state, redirect URI, CSRF/session và configuration thực; mock OAuth2 login không chứng minh external IdP đã được gọi.

Nếu **API Bearer lại trả 302 HTML login page**, có thể là lỗi chain selection; nếu browser page được dự kiến redirect mà lại trả 401 JSON, có thể là sai entry point. Vì vậy đừng dùng một SecurityFilterChain rộng cho mọi URL mà không kiểm tra các loại client.

## 15. Các sai lầm phổ biến

1. **Chỉ assert status().isOk().** Bỏ qua user identity, dữ liệu, header và quyền.
2. **Coi 200 là authenticated.** permitAll() cũng trả 200 cho anonymous.
3. **Coi 403 luôn là thiếu role.** CSRF cũng có thể trả 403.
4. **Coi 302 luôn là login thành công.** Redirect có thể đến /login, /login?error hoặc URL sai.
5. **Dùng @WithMockUser để test password thật.** Nó bypass quá trình password verification.
6. **Test WWW-Authenticate của API bằng header Authorization.** Một cái là response challenge, cái kia là request credential.
7. **Lấy final status của curl -L làm initial redirect status.** Nó che chuỗi 302 -> 200.
8. **Dùng redirectedUrl chính xác khi app trả absolute URL.** Cần chọn assertion phù hợp và không làm lỏng bảo mật host quá mức.
9. **Quên session ở request thứ hai sau login.** Test lại như user chưa đăng nhập.
10. **Quên csrf() ở POST form login.** Test 403 có thể do CSRF, chưa hề chạy password validation.
11. **Không test negative roles.** ADMIN 200 không chứng minh USER bị 403.
12. **Lầm MockMvc với trình duyệt/HTTP server đầy đủ.** Cookie/TLS/proxy/redirect follow behavior cần E2E khi quan trọng.
13. **Chỉ kiểm tra principal name, không ownership.** User có thể đọc dữ liệu không thuộc mình.
14. **Giả định security headers mặc định vĩnh viễn không đổi.** Cần dựa vào Spring Security version/config và contract.
15. **Bỏ qua request matcher order.** API có thể đi vào web login chain, làm status/header/redirect sai.

## 16. Checklist thiết kế bộ kiểm thử HTTP security

- [ ] Ghi rõ endpoint dành cho browser/session hay API/token.
- [ ] Có test public/anonymous và endpoint yêu cầu authenticated riêng.
- [ ] Với API Basic/Bearer, có test **401** và header **WWW-Authenticate** đúng scheme.
- [ ] Có test credentials/token không hợp lệ.
- [ ] Có test user hợp lệ nhưng thiếu quyền => 403.
- [ ] Có test user đủ quyền => 200 và body đúng dữ liệu.
- [ ] Với form/OIDC login, có test **3xx + Location** đúng destination.
- [ ] Có test login failure và success nếu ứng dụng dùng form.
- [ ] Có test session continuity sau login nếu dùng cookie/session.
- [ ] Có test CSRF hợp lệ, thiếu và sai token cho mutation endpoints phù hợp.
- [ ] Có test Content-Type/Cache-Control/security headers theo contract.
- [ ] Có test redirect không đến domain không tin cậy.
- [ ] Có test nhiều SecurityFilterChain chọn đúng cho API/web.
- [ ] Phân biệt **mock authentication** và **real filter/provider authentication**.
- [ ] Có integration tests với HTTP server, proxy/TLS/cookie khi những thành phần này quyết định kết quả.
- [ ] Không log hay serialize access token, password hoặc SecurityContext vào test reports.

## 17. Câu hỏi tự kiểm tra

1. **Một endpoint public trả 200 chứng minh authenticated chưa?** Chưa; permitAll cho phép anonymous.
2. **API Basic không có credentials thường trả gì?** 401 cùng header WWW-Authenticate: Basic ...
3. **User đã xác thực nhưng không có ROLE_ADMIN?** Thường 403 với endpoint yêu cầu role đó.
4. **Web form login chưa xác thực thường phản hồi thế nào?** 302 tới trang login qua Location.
5. **Vì sao cần kiểm tra header Location?** Để xác nhận redirect đúng destination, không chỉ có status 302.
6. **.with(user("alice")) có kiểm tra mật khẩu của alice không?** Không, nó mô phỏng Authentication.
7. **.with(httpBasic(...)) khác như thế nào?** Nó tạo Basic Authorization header, cho filter/provider xử lý credentials khi MockMvc có security filters.
8. **POST /login không csrf() bị 403 có phải mật khẩu sai?** Không nhất thiết; có thể bị CSRF filter từ chối trước khi thử password.
9. **MockMvc login thành công rồi muốn GET /dashboard cần gì?** Duy trì MockHttpSession hoặc cơ chế cookie phù hợp cho request kế tiếp.
10. **Làm sao tránh nhầm 302 với 200 khi dùng curl?** Quan sát initial response bằng curl -i; không tự theo redirect bằng -L nếu đang test Location.
11. **Một API dùng Bearer mà trả HTML login page thì kiểm tra gì?** SecurityFilterChain matching, authentication entry point và client contract.
12. **Status 200 với username đúng đã đủ kiểm tra authorization chưa?** Chưa; còn ownership/tenant/scope và dữ liệu trả về.

**Kết luận:** Kiểm thử HTTP security trong Spring Security Servlet cần phối hợp **Authentication state**, **Authorization**, **HTTP status**, **response headers**, **Location/redirect** và dữ liệu được trả về. Với **MockMvc + spring-security-test**, hãy viết cả positive và negative cases, phân biệt **401/403/302**, kiểm tra **WWW-Authenticate**, **Location**, CSRF và session theo đúng loại client. Test mock user giúp kiểm tra phân quyền, nhưng test đi qua filter/provider và integration môi trường thật mới giúp xác minh luồng đăng nhập/token đúng thiết kế.
