# MockMvc trả 401, 403 hoặc 404 ngoài dự kiến

## 1. Mục tiêu và phạm vi

Trong **Spring Boot - testing**, nhóm **Chẩn đoán lỗi kiểm thử**, một MockMvc test kỳ vọng status 200 hoặc 201 nhưng thực tế nhận **401 Unauthorized**, **403 Forbidden** hoặc **404 Not Found** không tự nói lên root cause. Có thể request bị Spring Security filter chain chặn trước controller; một POST bị **CSRF** từ chối; user thiếu **GrantedAuthority**; path không match MVC handler; hoặc controller đã xử lý nhưng business entity không tồn tại.

Bài học dùng **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, Spring Security 6.4, JUnit Jupiter và spring-security-test**. Ví dụ hoàn chỉnh có SecurityFilterChain explicit, DemoController với public/private/admin/item endpoints, service trả Optional<ItemView>, bộ **@WebMvcTest + @MockitoBean + @Import(SecurityConfig.class)** và bộ **@SpringBootTest + @AutoConfigureMockMvc**. Từng status có cả positive và negative controls: 401 anonymous, 403 thiếu role/CSRF, 404 routing vs 404 domain; các requests hợp lệ trả 200.

**Không chữa test bằng cách vô hiệu toàn bộ filters, thêm role ADMIN bừa bãi, sửa expected status cho xanh hoặc mock controller đang cần kiểm.** Cần xác định security/MVC/business layer thực sự tạo response trước khi thay code.

Mọi kết quả được giải thích trong bài là **expected behavior từ assertions**, không phải log Gradle đã được chạy trong khi soạn bài.

## 2. Pipeline của một MockMvc request

~~~text
MockMvc.perform(MockHttpServletRequest)
            |
            v
Servlet filters được đăng ký với MockMvc
            |
            +-- Spring Security FilterChainProxy
            |       |
            |       +-- securityMatcher chọn SecurityFilterChain
            |       +-- Authentication / SecurityContext
            |       +-- CsrfFilter với unsafe method
            |       +-- AuthorizationFilter
            |       +-- EntryPoint / AccessDeniedHandler
            |
            v  nếu filters cho đi tiếp
DispatcherServlet
            |
            +-- HandlerMapping
            +-- HandlerAdapter + binding/converter/validation
            +-- Controller / RestController
            +-- Service / @ControllerAdvice
            |
            v
MockHttpServletResponse
~~~

Đây là sơ đồ khái niệm; thứ tự chính xác filters phụ thuộc SecurityFilterChain. Điểm quan trọng là **filter có thể trả 401/403 trước khi DispatcherServlet tìm handler**. Vì vậy một URL thực sự không tồn tại nhưng gọi anonymous có thể nhận 401 thay vì 404. Một request được authenticated nhưng thiếu role có thể nhận 403 trước khi controller chạy. Chỉ sau khi bảo mật cho request đi tiếp ta mới phân tích MVC mapping đúng cách.

| Status | Nguồn thường gặp | Bước kiểm đầu |
| --- | --- | --- |
| 401 | Anonymous vào URL protected, HTTP Basic/Bearer challenge | AuthenticationEntryPoint, principal, WWW-Authenticate |
| 401 | Invalid credentials hoặc JWT | Authentication provider/decoder trace | 
| 403 | Logged-in user thiếu ROLE_/authority | Authorities, hasRole/hasAuthority, @PreAuthorize |
| 403 | POST/PUT/PATCH/DELETE thiếu CSRF | CsrfFilter, csrf() |
| 404 | URI/method/path mismatch | HandlerMapping, request URI |
| 404 | Controller chạy nhưng entity không tồn tại | Handler là controller, service result |
| 404 | Static resource fallback | ResourceHttpRequestHandler, NoResourceFoundException |
| 404 | Custom security che resource existence | AccessDeniedHandler hoặc controller policy |

**Status code là triệu chứng chứ không phải stack trace.** Chẩn đoán bằng selected handler, resolved exception, filters và một positive control.

## 3. 401 Unauthorized: authentication và entry point

Khi anonymous request gọi endpoint yêu cầu Authentication, Spring Security thường chuyển lỗi sang **AuthenticationEntryPoint**. Với chain dùng **httpBasic(Customizer.withDefaults())**, response thường là **401** và **WWW-Authenticate: Basic**. Với **formLogin**, anonymous request có thể **302 redirect** tới login page thay vì 401. Với OAuth2 Resource Server/Bearer token, lỗi token có thể 401 và header Bearer; chi tiết tùy cấu hình.

**Các nguyên nhân 401 ngoài dự kiến:**
- Test không gắn **@WithMockUser** hoặc **with(user("alice"))**.
- Test dùng MockMvcBuilders.standaloneSetup mà không tích hợp Spring Security.
- @WebMvcTest thiếu production SecurityFilterChain, Boot default chain bảo vệ mọi URL.
- Authentication fixture có username nhưng không có real credential validation như test mong.
- Request bị một SecurityFilterChain khác match trước do @Order/securityMatcher.
- Custom stateless/token filter không dùng mock Authentication như giả định.
- Authorization header không có hoặc sai scheme; HTTP Basic chưa được bật.
- Route sai nhưng filter chặn trước MVC nên chưa có 404.

**@WithMockUser** tạo một mock Authentication tại Spring Security test context; user **không cần tồn tại trong DB**. Nó tốt để kiểm authorization/handler, nhưng **không kiểm password verification/JWT signature**, issuer/audience, authentication manager hoặc login form.

Ví dụ expected:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void authenticatedCanReadProfile() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(content().string("alice"));
}
~~~

Ngược lại anonymous:

~~~java
@Test
void anonymousNeedsAuthentication() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isUnauthorized());
}
~~~

Đây là các snippets của test project đầy đủ ở phần 8.

## 4. 403 Forbidden: authorization hoặc CSRF

**403 authorization:** user có ROLE_USER nhưng endpoint yêu cầu **hasRole("ADMIN")**, tức ROLE_ADMIN. **403 CSRF:** một request POST vào route **permitAll** vẫn bị CsrfFilter từ chối nếu thiếu token. Hai lý do cần test khác nhau.

~~~text
GET /api/admin/report
user = alice; authorities = [ROLE_USER]
rule = hasRole("ADMIN")
=> 403

POST /api/public/echo
url authorization = permitAll
csrf enabled, no token
=> 403
~~~

### role và authority

- **hasRole("ADMIN")** đòi GrantedAuthority **ROLE_ADMIN**.
- **@WithMockUser(roles = "ADMIN")** cung cấp ROLE_ADMIN.
- **@WithMockUser(authorities = "ROLE_ADMIN")** cũng cấp string đó.
- **hasAuthority("SCOPE_catalog.read")** không giống hasRole("catalog.read"); scopes dùng tên authority khác.
- Không khai **roles = "ROLE_ADMIN"** trong shortcut muốn biểu diễn ADMIN role; Spring Security test xử lý prefix ROLE_ cho roles.

### permitAll không disable CSRF

Spring Security mặc định bảo vệ unsafe HTTP methods như POST, PUT, PATCH, DELETE bằng CSRF nếu chưa cấu hình khác. GET/HEAD/OPTIONS/TRACE thường không cần token theo matcher mặc định.

~~~java
mvc.perform(post("/api/public/echo")
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"message\":\"ok\"}"))
    .andExpect(status().isOk());
~~~

Security test còn hỗ trợ **csrf().asHeader()** và **csrf().useInvalidToken()**. Nếu thiếu token dẫn đến 403 rồi thêm valid token vẫn 403, cần điều tra URL authorization, method security, role và chain chứ không tiếp tục thêm role tùy ý.

**CSRF policy phải là quyết định của ứng dụng.** Một stateless API thực sự không dùng cookie/session credentials có thể có policy khác, nhưng không disable CSRF trong test chỉ để che một ứng dụng production đang bật CSRF. Browser automatically attached credentials tạo threat model khác với manually attached bearer tokens.

## 5. 404: không có MVC route hay không có business object?

**Routing 404:** Controller khai **GET /api/items/{id}** nhưng test gọi **GET /api/item/42**; không có mapping controller đúng URI.

**Domain 404:** GET /api/items/99 đã match DemoController.item, nhưng InventoryService.find(99) trả Optional.empty, controller trả ResponseEntity.notFound().build(). Cùng status nhưng handler đã chạy.

**Resource 404:** Trong Spring MVC, static resource mapping có thể nhận URL còn lại và trả **NoResourceFoundException**. Debug có thể cho thấy **ResourceHttpRequestHandler** thay vì handler null; đừng đọc nhầm là API controller đã xử lý.

**Custom 404:** Một hệ thống có thể cố ẩn resource existence trước user không có quyền bằng 404; đó là authorization policy, không tự động chứng minh sai path.

Cách tách:
1. Gửi cùng request với test user có đủ quyền để vượt security filter.
2. Xem **MvcResult.getHandler()** hoặc **handler().handlerType(DemoController.class)**.
3. Xem **getResolvedException()**; khi controller trả ResponseEntity.notFound() thì exception có thể null.
4. Stub/verify service mock và kiểm item ID.
5. Kiểm route prefix/method/contextPath/servletPath/trailing slash.
6. Kiểm controller có được scan hoặc được chỉ định trong @WebMvcTest không.

**Không lấy anonymous GET sai URL rồi kết luận MVC trả 404**: filter có thể xử lý trước bằng 401.

## 6. Dự án Java 17 / Spring Boot 3.4.5

### 6.1. Cây file

~~~text
settings.gradle
build.gradle
src/main/java/com/example/mockdiag/MockDiagApplication.java
src/main/java/com/example/mockdiag/SecurityConfig.java
src/main/java/com/example/mockdiag/ItemView.java
src/main/java/com/example/mockdiag/InventoryService.java
src/main/java/com/example/mockdiag/DemoController.java
src/test/java/com/example/mockdiag/DemoControllerSecuritySliceTest.java
src/test/java/com/example/mockdiag/FullSecurityContractTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'mockmvc-security-diagnostics'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

**spring-security-test** cung cấp @WithMockUser, SecurityMockMvcRequestPostProcessors.csrf(), user(), httpBasic(), authentication() và JWT support phù hợp khi sử dụng OAuth2 testing. **spring-boot-starter-test** có MockMvc, Spring TestContext, JUnit Jupiter, Mockito và AssertJ. Không cần DB, Kafka, Docker hay embedded real web server cho MockMvc.

### 6.4. MockDiagApplication.java

~~~java
package com.example.mockdiag;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockDiagApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockDiagApplication.class, args);
    }
}
~~~

Application và các classes cùng root package để full @SpringBootTest scan được controllers/security/service.

### 6.5. SecurityConfig.java

~~~java
package com.example.mockdiag;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // CSRF giữ mặc định enabled.
        return http.build();
    }
}
~~~

Các rules có thứ tự: public và admin trước **anyRequest**. **httpBasic** dùng AuthenticationEntryPoint phù hợp để anonymous GET /api/me thường 401. **hasRole("ADMIN")** cần authority ROLE_ADMIN. **CSRF không disabled**, nên ngay cả POST public vẫn yêu cầu token theo default CSRF matcher.

Nếu production dùng form login hoặc Bearer JWT, expected authentication response khác; phải test config thực tế của sản phẩm, không mặc định luôn có Basic challenge.

### 6.6. ItemView.java

~~~java
package com.example.mockdiag;

public record ItemView(long id, String name) {
}
~~~

Spring MVC/Jackson serialize record sang JSON có fields id và name.

### 6.7. InventoryService.java

~~~java
package com.example.mockdiag;

import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    public Optional<ItemView> find(long id) {
        return id == 42L
            ? Optional.of(new ItemView(42L, "keyboard"))
            : Optional.empty();
    }
}
~~~

Full context dùng service thật; WebMvc slice cần mock dependency.

### 6.8. DemoController.java

~~~java
package com.example.mockdiag;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final InventoryService inventory;

    public DemoController(InventoryService inventory) {
        this.inventory = inventory;
    }

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping(
        value = "/me",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping(
        value = "/admin/report",
        produces = MediaType.TEXT_PLAIN_VALUE)
    public String adminReport() {
        return "restricted";
    }

    @GetMapping("/items/{id}")
    public ResponseEntity<ItemView> item(
            @PathVariable long id) {
        return inventory.find(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(
        value = "/public/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public EchoResponse echo(
            @RequestBody EchoRequest request) {
        return new EchoResponse(request.message());
    }

    public record EchoRequest(String message) {
    }

    public record EchoResponse(String message) {
    }
}
~~~

Controller có **public GET**, **private GET**, **admin GET**, **item GET**, **public POST**. Không có @ControllerAdvice hay @PreAuthorize custom trong source để status nào cũng có nguyên nhân rõ.

### 6.9. Ma trận kết quả của API

| Request | Auth/CSRF | Kết quả mong đợi |
| --- | --- | --- |
| GET /api/public/ping | Anonymous | 200 pong |
| GET /api/me | Anonymous | 401 |
| GET /api/me | user alice | 200 alice |
| GET /api/admin/report | ROLE_USER | 403 |
| GET /api/admin/report | ROLE_ADMIN | 200 restricted |
| POST /api/public/echo | Anonymous, no CSRF | 403 |
| POST /api/public/echo | Anonymous, valid CSRF | 200 JSON |
| POST /api/public/echo | Anonymous, invalid CSRF | 403 |
| GET /api/items/42 | Authenticated | 200 JSON item |
| GET /api/items/99 | Authenticated | 404 domain |
| GET /api/item/42 | Authenticated | 404 route |

## 7. Unit MVC slice với Spring Security thực sự tham gia

**src/test/java/com/example/mockdiag/DemoControllerSecuritySliceTest.java**

~~~java
package com.example.mockdiag;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.handler;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DemoController.class)
@Import(SecurityConfig.class)
class DemoControllerSecuritySliceTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private InventoryService inventory;

    @Test
    void anonymousPublicIs200() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousProtectedIs401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void authenticatedProtectedIs200() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserDeniedAdmin403() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminAuthorized200() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isOk())
            .andExpect(content().string("restricted"));
    }

    @Test
    void publicPostWithoutCsrfIs403() throws Exception {
        mvc.perform(post("/api/public/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void publicPostWithCsrfIs200() throws Exception {
        mvc.perform(post("/api/public/echo")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"));
    }

    @Test
    void publicPostInvalidCsrfIs403() throws Exception {
        mvc.perform(post("/api/public/echo")
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"message\":\"hello\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postProcessorCreatesAuthentication() throws Exception {
        mvc.perform(get("/api/me")
                .with(user("reader").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("reader"));
    }

    @Test
    @WithMockUser
    void foundItemUsesControllerAndReturns200()
            throws Exception {
        when(inventory.find(42L))
            .thenReturn(Optional.of(
                new ItemView(42L, "keyboard")));

        mvc.perform(get("/api/items/42"))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(
                DemoController.class))
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.name").value("keyboard"));

        verify(inventory).find(42L);
    }

    @Test
    @WithMockUser
    void missingItemIsDomain404() throws Exception {
        when(inventory.find(99L))
            .thenReturn(Optional.empty());

        mvc.perform(get("/api/items/99"))
            .andExpect(status().isNotFound())
            .andExpect(handler().handlerType(
                DemoController.class));

        verify(inventory).find(99L);
    }

    @Test
    @WithMockUser
    void wrongSingularPathIsRouting404()
            throws Exception {
        mvc.perform(get("/api/item/42"))
            .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser
    void debugMvcResultShowsMatchedDomainHandler()
            throws Exception {
        when(inventory.find(99L))
            .thenReturn(Optional.empty());

        MvcResult result = mvc.perform(get("/api/items/99"))
            .andDo(print())
            .andExpect(status().isNotFound())
            .andReturn();

        assertEquals(404, result.getResponse().getStatus());
        assertNotNull(result.getHandler());
    }
}
~~~

### Giải thích bộ test

- **@WebMvcTest(DemoController.class)** tạo MVC slice, không mở socket.
- **@Import(SecurityConfig.class)** đảm bảo slice có explicit production authorization rules thay vì Boot default security chain.
- **@MockitoBean InventoryService** cung cấp collaborator vì slice không tự scan mọi @Service.
- Anonymous 401, user thiếu role 403, CSRF 403 là **expected negative contracts**, không phải lỗi cần tắt filters.
- Positive user/admin/CSRF tests chứng minh route thực sự hoạt động khi điều kiện đúng.
- **missingItemIsDomain404** assert đúng controller handler và verify service.find.
- **wrongSingularPathIsRouting404** kiểm URI sai, sau khi test user được authenticate.
- **MvcResult** cho biết handler/status để phân biệt 404 domain và route.

**Không dùng @MockitoBean để giả lập AuthenticationFilter rồi tuyên bố security config đã được kiểm.** Mock InventoryService là boundary nghiệp vụ, còn SecurityFilterChain vẫn chạy thật trong MockMvc.

## 8. Kiểm production wiring bằng full context

**src/test/java/com/example/mockdiag/FullSecurityContractTest.java**

~~~java
package com.example.mockdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FullSecurityContractTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousPublicStill200() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousProtectedStill401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void realServiceReturnsExistingItem() throws Exception {
        mvc.perform(get("/api/items/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("keyboard"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void realSecurityStillBlocksNonAdmin()
            throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isForbidden());
    }
}
~~~

**@SpringBootTest** tải full Spring context, có InventoryService và SecurityConfig thật. **@AutoConfigureMockMvc** tạo MockMvc đã nối application filters. Nó không phải real RANDOM_PORT HTTP server; mặc định @SpringBootTest sử dụng MOCK web environment. Full-context tests giúp bắt chênh lệch giữa slice security config và production component scanning/profiles.

## 9. Đọc diagnostics đúng cách

Tạm thêm **andDo(print())** để xem request, selected Handler, resolved exception và response:

~~~java
mvc.perform(get("/api/items/99")
        .with(user("debug")))
    .andDo(print())
    .andExpect(status().isNotFound());
~~~

Hoặc inspect **MvcResult** trực tiếp:

~~~java
MvcResult result = mvc.perform(
        get("/api/item/42")
            .with(user("debug")))
    .andReturn();

int actualStatus = result.getResponse().getStatus();
Object handler = result.getHandler();
Exception resolved = result.getResolvedException();
String responseBody =
    result.getResponse().getContentAsString();
~~~

Các snippets này thuộc test method, không phải full Java file độc lập. Khi security filter chặn request, **handler có thể null** vì DispatcherServlet chưa xử lý. Khi static resource fallback nhận URI, handler có thể là **ResourceHttpRequestHandler**, còn lỗi là **NoResourceFoundException**. Khi controller chủ động trả ResponseEntity.notFound(), **getResolvedException() có thể null** dù status=404. Vì vậy phải nhìn **handler + response + nguyên nhân**, không chỉ trường exception.

### Logging có chọn lọc

Ví dụ **src/test/resources/application-test.yml** khi @ActiveProfiles("test") thực sự được bật:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: TRACE
    org.springframework.web.servlet.DispatcherServlet: DEBUG
~~~

Đây là cấu hình minh họa, không bắt buộc cho project. Spring Security DEBUG có thể giúp kiểm filter chain/matcher. MVC mapping TRACE có thể giúp thấy registered request handlers. **Đừng in Authorization tokens, raw Basic passwords, session cookies hoặc thông tin khách hàng vào public CI logs.** Không bật TRACE production dài hạn chỉ để debug unit test.

## 10. addFilters=false và standalone MockMvc

Spring Boot cho phép:

~~~java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = false)
class ControllerOnlyExample {
    // Chỉ minh họa, không nằm trong project chính.
}
~~~

**@AutoConfigureMockMvc(addFilters=false)** bỏ đăng ký servlet Filter beans vào MockMvc. Test có thể thôi trả 401/403 vì **bỏ qua security filtering**, nhưng lúc đó cũng bỏ CORS, tracing, tenant, encoding và custom filters khác. **Không coi test ấy là bằng chứng authentication/authorization/CSRF đúng production**. Chỉ dùng khi chủ động giới hạn test vào controller, có suite security riêng còn bật filters.

Tự dựng standalone:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new DemoController(fakeInventory))
    .build();
~~~

Đây cũng là snippet minh họa với fakeInventory cần được tạo, không là project full file. **StandaloneSetup không mặc nhiên thêm Spring Security FilterChainProxy**. Với manually built MockMvc trên WebApplicationContext, cần SecurityMockMvcConfigurers.springSecurity() và filters/test listener integration đúng cách. Test standalone 200 anonymous không chứng minh production endpoint public.

## 11. WebMvcTest slice có thể khác production thế nào?

**Trường hợp A:** Production public /api/public/ping, nhưng @WebMvcTest trả 401. Rất có thể **custom SecurityConfig không được import**, Boot tạo default chain yêu cầu auth cho mọi URI. **Sửa:** dùng @Import(SecurityConfig.class) và một full-context security contract test.

**Trường hợp B:** @WebMvcTest fail load context với UnsatisfiedDependencyException. Controller inject @Service nhưng slice không có. **Sửa:** @MockitoBean đúng type hoặc @Import test fixture. Đây chưa phải một MockMvc HTTP error vì @Test method chưa chạy.

**Trường hợp C:** Test đi tới controller nhưng trả 404 item missing. Mockito service chưa stub, trả Optional.empty theo default hoặc explicit stub. **Sửa:** when(inventory.find(id)).thenReturn(Optional.of(...)), assert handler và verify call.

**Trường hợp D:** Full context có custom Filter beans/interceptors hoặc @ControllerAdvice nhưng slice thiếu hoặc khác. So sánh hai levels, không giả rằng @WebMvcTest gồm mọi bean production.

**Trường hợp E:** Test profile/feature flag khác. Bean đăng ký theo @Profile/@ConditionalOnProperty có thể thay đổi SecurityFilterChain hoặc controller. Kiểm context test properties rõ, không tự gán default của production.

## 12. Role, authority và method security

**hasRole("ADMIN")** thông thường yêu cầu **ROLE_ADMIN**. **@WithMockUser(roles="ADMIN")** cấp authority ROLE_ADMIN. Với security policy dùng **hasAuthority("SCOPE_reports.read")**, fixture phải cấp chính chuỗi đó, không thể thay bằng roles="reports.read".

**@PreAuthorize** hoặc @PostAuthorize có thể từ chối access **sau khi URL-level filter rule đã cho qua**. Nếu @EnableMethodSecurity active và service method có proxy/interceptor, một controller route có thể vẫn trả 403. Khi service được @MockitoBean thay, method security trên service thật có thể không được thực thi như production; bổ sung full-context method security test nếu contract yêu cầu.

### Multiple SecurityFilterChain

Spring Security có thể có nhiều chains. **securityMatcher** quyết định chain nào được áp dụng, còn **requestMatchers** áp rules trong chain. @Order và chain specificity quan trọng. Ví dụ dưới đây là snippet minh họa ngoài project chính:

~~~java
@Bean
@Order(1)
SecurityFilterChain managementChain(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/actuator/**")
        .authorizeHttpRequests(auth ->
            auth.anyRequest().hasRole("OPS"))
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Cần imports @Order, @Bean và cấu hình chain khác/Actuator khi triển khai thật. Nếu /actuator/health 401 bất ngờ, sửa API public matcher thường **không có tác dụng** khi request đã match management chain.

## 13. HTTP Basic và JWT thật khác mock user

**@WithMockUser** không gọi UserDetailsService, PasswordEncoder hoặc JWT decoder. Với HTTP Basic credentials thật, cần tạo UserDetailsService/PasswordEncoder fixture rồi test:

~~~java
mvc.perform(get("/api/me")
        .with(httpBasic("reader", "secret")))
    .andExpect(status().isOk());
~~~

Đây là snippet **không chạy độc lập trong project chính** vì project không tạo user reader/secret; muốn dùng cần cấu hình authentication provider có user đó. Test bad password phải trả 401; không nhầm @WithMockUser với password integration.

Với OAuth2 Resource Server, **with(jwt())** tạo JWT test Authentication giúp kiểm authorization nhưng không chứng minh token signature, issuer, audience, expiration, JWK retrieval. Muốn kiểm decoder thật phải có integration fixture/token/decoder configuration. Chỉ thêm Bearer string header mà không có resource-server config sẽ không tự authenticate.

## 14. CSRF theo tầng bảo vệ

Một matrix hữu ích cho POST public endpoint:

| Scenario | Authorization | CSRF | Kỳ vọng |
| --- | --- | --- | --- |
| Anonymous + no token | permitAll | Missing | 403 |
| Anonymous + invalid token | permitAll | Invalid | 403 |
| Anonymous + valid token | permitAll | Valid | 200 |
| ROLE_ADMIN + no token | permitAll | Missing | 403 |
| ROLE_USER + valid token | permitAll | Valid | 200 |
| GET public + no token | permitAll | Không yêu cầu mặc định | 200 |

CSRF có thể từ chối trước khi MVC thấy Content-Type/JSON. Do vậy một POST no token + malformed body có thể **403**, nhưng sau khi thêm valid token lại **400** (JSON lỗi) hoặc **415** (media type lỗi). Đó là dấu hiệu request đã tiến sang layer sau, không phải hành vi bất thường.

## 15. Context path, servlet path, method và media types

Nếu app có:

~~~properties
server.servlet.context-path=/shop
spring.mvc.servlet.path=/gateway
~~~

External URL có prefix /shop/gateway trước controller path. Trong MockMvc, request URI/contextPath/servletPath phải nhất quán. Ví dụ khi chỉ có context path và request setup đúng:

~~~java
mvc.perform(get("/shop/api/items/42")
        .contextPath("/shop")
        .with(user("reader")))
    .andExpect(status().isOk());
~~~

Snippet đòi config và inventory fixture phù hợp; khi DispatcherServlet có custom path cần mô phỏng servletPath. Không thêm prefix đó vào @RequestMapping một cách vội vàng khi production controller đang đúng.

**Spring Framework 6.x** path matching không nên giả định trailing slash tự match như version/config cũ: /api/items/42 và /api/items/42/ có thể khác. Path case, encoding, URL segments và servlet mapping phải được xác minh từ HandlerMapping. Với HTTP method sai trên path tồn tại, MVC có thể trả **405** thay vì 404. Với Accept không tương thích produces → **406**; Content-Type không đúng consumes → **415**. JSON parse/binding/validation → **400**. Không quy mọi lỗi response vào Spring Security.

## 16. Controller advice và exception handling

Một controller có thể trả ResponseEntity.notFound() mà không ném exception; ném ResponseStatusException(HttpStatus.NOT_FOUND); hoặc ném custom business exception được @RestControllerAdvice map sang 404. Trong các trường hợp này, handler có thể đã match. **MvcResult.getResolvedException()** giúp xem exceptions được MVC resolvers xử lý, nhưng không nhất thiết có giá trị cho mọi non-2xx response.

Trong @WebMvcTest, @ControllerAdvice thường thuộc MVC slice nhưng cấu hình package/filter/import có thể khiến nó khác full context. Lỗi security filter sinh trước DispatcherServlet không nhất thiết đi qua @ControllerAdvice. Xác minh layer và resolver đúng trước khi sửa.

## 17. CI và test flakiness liên quan SecurityContext

Một MockMvc test pass riêng nhưng fail trong suite có thể do:
- Static mutable Authentication hoặc SecurityContextHolder bị set thủ công rồi không clear.
- @WithMockUser class-level áp vào cả tests muốn anonymous.
- HTTP session/cookies reused ngoài ý muốn.
- Mockito stubbing/reset, @MockitoBean scope hoặc test order dependence.
- Spring TestContext cache singleton mutable state hoặc @DirtiesContext lạm dụng.
- Custom rate-limit/filter/tenant state dùng chung.
- Active profiles/properties khác giữa test classes.
- Parallel JUnit tests dùng shared credentials, DB state, secrets hoặc resource IDs.
- CSRF token/session gắn với request khác.
- JWT hết hạn/system clock khác CI.
- Gradle Test task FROM-CACHE hoặc UP-TO-DATE nên tests không được thực thi ở lần invocation hiện tại.

Nên để Spring Security Test context listeners thiết lập/clear SecurityContext; dùng per-test @WithMockUser hoặc request post processor; không chia static mutable auth; reset mocks/test fixtures đúng lifecycle. Xác nhận actual test execution trước khi so sánh logs.

## 18. Quy trình điều tra nhanh

1. **Đọc actual status, request, headers, handler và resolved exception** qua print()/MvcResult.
2. **Kiểm test layer:** @WebMvcTest, @SpringBootTest + @AutoConfigureMockMvc, standaloneSetup hay real RANDOM_PORT?
3. **Kiểm SecurityFilterChain:** default hay custom, có import vào slice không, filters đã được đăng ký?
4. **Nếu 401:** Anonymous? AuthenticationEntryPoint nào? Basic/form/JWT? Credentials/mock user có đúng không?
5. **Nếu 403 POST:** Kiểm csrf() trước khi kiểm role. Nếu 403 GET, kiểm authorities/roles/method security.
6. **Nếu 404:** Dùng authenticated user, kiểm handler là controller hay resource, path/method/contextPath và service fixture.
7. **Có positive control?** User có quyền và input hợp lệ phải trả 200.
8. **So sánh full context:** Slice và production có config/beans cùng semantics?
9. **Sửa đúng nguyên nhân** chứ không tắt security/test filters.
10. **Giữ negative tests** để bảo vệ chính sách authorization/CSRF và not-found contracts.

### Quyết định theo triệu chứng

~~~text
Status ngoài dự kiến?
   |
   +-- 401: User? Entry point? SecurityFilterChain? Basic/Bearer?
   |
   +-- 403: CSRF trên unsafe method?
   |          |
   |          +-- CSRF hợp lệ rồi? Roles/authorities/@PreAuthorize?
   |
   +-- 404: Security đã cho qua chưa?
              |
              +-- Handler controller? Service/data trả not found.
              |
              +-- Handler resource/null? URI/route/context path.
~~~

## 19. Lệnh chạy và expected results

~~~bash
./gradlew clean test
./gradlew test --tests com.example.mockdiag.DemoControllerSecuritySliceTest
./gradlew test --tests com.example.mockdiag.FullSecurityContractTest
./gradlew test --tests com.example.mockdiag.DemoControllerSecuritySliceTest.publicPostWithoutCsrfIs403
./gradlew test --tests com.example.mockdiag.DemoControllerSecuritySliceTest.missingItemIsDomain404
~~~

Trên Windows dùng gradlew.bat. Nếu project chưa có Gradle Wrapper scripts, dùng Gradle cài sẵn hoặc tạo wrapper trước; build.gradle không tự tạo gradlew. **Không có báo cáo thực thi BUILD SUCCESSFUL nào được quan sát khi soạn bài.**

| Test | Bằng chứng kỳ vọng |
| --- | --- |
| anonymousPublicIs200 | 200 pong |
| anonymousProtectedIs401 | 401 |
| authenticatedProtectedIs200 | 200 alice |
| ordinaryUserDeniedAdmin403 | 403 |
| adminAuthorized200 | 200 restricted |
| publicPostWithoutCsrfIs403 | 403 |
| publicPostWithCsrfIs200 | 200 JSON hello |
| publicPostInvalidCsrfIs403 | 403 |
| postProcessorCreatesAuthentication | 200 reader |
| foundItemUsesControllerAndReturns200 | 200 JSON item, controller handler |
| missingItemIsDomain404 | 404 domain, controller handler |
| wrongSingularPathIsRouting404 | 404 wrong URI |
| debugMvcResultShowsMatchedDomainHandler | 404, handler present |
| anonymousPublicStill200 | Full context 200 |
| anonymousProtectedStill401 | Full context 401 |
| realServiceReturnsExistingItem | Full context 200 |
| realSecurityStillBlocksNonAdmin | Full context 403 |

Các expected outcomes không được coi là CI output thực; nếu test thật fail cần đọc stack trace và library/version configuration thực.

## 20. Anti-pattern và cách sửa

| Sai lầm | Vì sao không ổn | Hướng sửa |
| --- | --- | --- |
| Thấy 401 rồi thêm addFilters=false | Bypass security | Setup authentication/chain đúng |
| @WebMvcTest public trả 401 do default chain | Slice thiếu config | @Import(SecurityConfig.class) |
| Thấy 403 POST rồi thêm ADMIN role | CSRF vẫn thiếu | with(csrf()) |
| Disable CSRF toàn production vì test đỏ | Thay security threat model | Giữ policy, test token đúng |
| @WithMockUser(roles="ROLE_ADMIN") | Nhầm prefix | roles="ADMIN" |
| 404 Optional.empty nhưng sửa mapping | Domain not found | Stub data, assert handler |
| Wrong path singular/plural | Không map | Fix request URI |
| HTTP method sai | 405 | Đúng @GetMapping/@PostMapping |
| Content-Type sai | 415 | application/json |
| @WebMvcTest thiếu service | Context fail trước @Test | @MockitoBean |
| Standalone MockMvc tự nhận là secure | Không có filters | springSecurity() đúng setup |
| Mock user chứng minh JWT verified | Không decode token | Decoder integration |
| Chỉ assert HTTP status | Che body/handler sai | Assert payload/handler/service |
| Dùng @ControllerAdvice cho filter exception | Lỗi có thể trước MVC | EntryPoint/AccessDeniedHandler |
| Ghi DEBUG logs có credentials vào CI | Lộ secrets | Redact logs |
| Test class-level user cho cả anonymous tests | False positive | Method-level auth |

## 21. Tự kiểm tra

**1.** Anonymous GET protected route trả 401 có phải bug? **Không**, có thể đúng HTTP Basic policy.

**2.** Form login anonymous có thể trả 302 thay 401? **Có**.

**3.** 403 có nhất thiết user đã login không? **Không**, CSRF có thể chặn anonymous POST.

**4.** permitAll có tắt CSRF không? **Không**.

**5.** @WithMockUser có tạo real DB user không? **Không**.

**6.** @WithMockUser có kiểm JWT signature không? **Không**.

**7.** hasRole("ADMIN") cần authority gì? **ROLE_ADMIN**.

**8.** roles="ADMIN" tạo authority nào? **ROLE_ADMIN** thông thường.

**9.** GET wrong route có thể trả 401 trước 404? **Có**, security xử lý trước.

**10.** Controller item route trả 404 khi service empty nghĩa gì? **Domain 404, routing vẫn đúng**.

**11.** @WebMvcTest có scan @Service tự động? **Không**, cần mock/fixture.

**12.** Vì sao @Import(SecurityConfig.class)? **Giữ rule custom trong MVC slice**.

**13.** addFilters=false có thể làm 401/403 biến mất? **Có, vì bypass filters**, nên không chứng minh security.

**14.** MockMvc mặc định mở TCP socket không? **Không**.

**15.** POST sai Content-Type có thể trả 415? **Có**, sau khi security cho đi tiếp.

**16.** POST vào GET route có thể trả 405? **Có**.

**17.** Có thể biết 404 do controller từ MvcResult? **Có**, xem handler và service result.

**18.** @PreAuthorize có thể gây 403? **Có**, nếu method security enabled và proxy active.

**19.** SecurityFilterChain nhiều lớp quan trọng gì? **securityMatcher/@Order quyết định chain, requestMatchers quyết định URL rule**.

**20.** Chẩn đoán nên bắt đầu từ đâu? **Request, filters, principal, CSRF, handler và MvcResult**.

### Checklist QA

- Đã xác định @WebMvcTest vs full @SpringBootTest vs standalone MockMvc?
- spring-security-test dependency có đúng và mock user setup có hiệu lực?
- SecurityConfig production được import vào slice hay được load ở full context?
- Không tắt addFilters trong security tests?
- Anonymous/authenticated scenarios được kiểm riêng?
- Role/authority và ROLE_ prefix đúng?
- POST/PUT/PATCH/DELETE có CSRF test negative và positive?
- Không disable CSRF chỉ để test xanh?
- 404 domain được phân biệt với routing/static resource 404?
- MvcResult handler, status, resolved exception được inspect?
- URI, contextPath, servletPath, HTTP method, produces/consumes đúng?
- @MockitoBean service được stub chính xác khi test controller?
- Có positive 200 cho public/user/admin/CSRF/item?
- Có full-context security contract test để tránh slice khác production?
- Không coi mock principal là test real credential/JWT auth?
- Không leak SecurityContext, sessions, static state giữa tests?
- Logs không để lộ credentials, JWT hoặc CSRF tokens?
- Không báo đã chạy Gradle nếu chưa có kết quả thật?

**Kết luận:** **401, 403 và 404 ngoài dự kiến trong MockMvc** phải được phân tích theo thứ tự **security filters → authentication → CSRF/authorization → DispatcherServlet handler mapping → controller/service/domain response**. Test bằng **@WithMockUser, with(user()), csrf(), @Import(SecurityConfig.class), MvcResult/print()** đúng ý đồ; giữ cả negative security tests và positive controls. Không làm test xanh bằng cách bỏ qua security filters.

## Nguồn tham khảo

- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 — Spring Security: https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html
- Spring Security — Setting Up MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html
- Spring Security — Running Test as User: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security — CSRF MockMvc Test: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security — HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Framework 6.2 — MockMvc Framework: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Framework 6.2 — @RequestMapping: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Boot 3.4 API — AutoConfigureMockMvc: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html
