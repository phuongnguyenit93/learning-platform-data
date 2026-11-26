# @Import cấu hình kiểm thử mà không thay chính sách cần xác minh

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào **Spring MVC slice test** với `@WebMvcTest`: bổ sung cấu hình cần thiết cho test context nhưng vẫn giữ nguyên chính sách bảo mật mà test cần xác minh.

Sau bài học, bạn có thể:

1. Phân biệt cấu hình bảo mật của ứng dụng với cấu hình hỗ trợ riêng cho test.
2. Dùng `@Import` để đưa custom `SecurityFilterChain` và `@TestConfiguration` vào MVC slice.
3. Cung cấp mock cho controller dependency mà không tạo một security policy khác.
4. Nhận biết test chain có thể che khuất hoặc thay đổi policy cần kiểm tra.
5. Viết ca public, anonymous, thiếu role, đủ role và CSRF để xác minh cấu hình thật.

## 1. Mục đích của @Import trong MVC slice

`@WebMvcTest` tạo một test context tập trung vào Spring MVC. Nó chọn controller và hạ tầng web cần thiết, nhưng không nạp toàn bộ cấu hình ứng dụng như `@SpringBootTest`. Vì vậy, một cấu hình `SecurityFilterChain` tùy chỉnh có thể không nằm trong lát cắt nếu test không đưa nó vào.

`@Import` cho phép khai báo rõ những cấu hình hoặc bean cần bổ sung:

~~~java
@WebMvcTest(ArticleController.class)
@Import(SecurityConfiguration.class)
class ArticleControllerSecurityTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Trong ví dụ, `SecurityConfiguration` là cấu hình cần xác minh. `@Import` đưa chính cấu hình đó vào slice để Spring tạo security filters theo policy đã khai báo.

Khi controller cần service, repository hoặc client không có trong slice, test có thể bổ sung bean hỗ trợ riêng. Một cách tổ chức rõ ràng là import **cả cấu hình bảo mật cần kiểm tra và cấu hình fixture của test**:

~~~java
@WebMvcTest(ArticleController.class)
@Import({
    SecurityConfiguration.class,
    ArticleMvcTestSupport.class
})
class ArticleControllerSecurityTest {
    // ...
}
~~~

Hai cấu hình có hai trách nhiệm khác nhau:

| Cấu hình | Trách nhiệm | Có thay đổi security policy không? |
| --- | --- | --- |
| `SecurityConfiguration` của ứng dụng | Định nghĩa URL matcher, role, authentication, CSRF và filter chain | Đây là policy đang được kiểm tra |
| `ArticleMvcTestSupport` | Cung cấp mock service, fixture hoặc bean phụ trợ cho MVC slice | Không, nếu chỉ cung cấp dependency hỗ trợ |

Nguyên tắc là **import cấu hình bảo mật thật mà bạn muốn kiểm tra, rồi bổ sung đúng các dependency còn thiếu**. Không tạo một security policy khác chỉ để test dễ chạy.

## 2. Bean graph của test context

~~~mermaid
flowchart TB
    A["@WebMvcTest(ArticleController.class)"] --> B["MVC slice context"]
    B --> C["ArticleController"]
    B --> D["MockMvc + MVC infrastructure"]
    E["@Import(SecurityConfiguration.class)"] --> F["Production SecurityFilterChain"]
    G["@Import(ArticleMvcTestSupport.class)"] --> H["Test fixture / mock dependencies"]
    F --> I["Security filters"]
    H --> C
    C --> J["Request / response"]
    I --> J
    D --> J
~~~

Một slice có thể gồm controller thật, cấu hình `SecurityFilterChain` thật, cấu hình method security nếu cần, mock cho service/client ngoài phạm vi, cùng converter/advice/filter tùy chỉnh mà request sử dụng.

Không cần đưa mọi bean production vào một slice. Nhưng mọi bean được tham chiếu bởi cấu hình đã import phải được giải quyết khi context khởi tạo. Ví dụ, nếu `SecurityConfiguration` nhận `JwtDecoder` qua tham số `@Bean`, test cần cung cấp decoder phù hợp, kể cả khi request dùng JWT giả lập để kiểm tra authorization.

## 3. Ví dụ: import policy thật và fixture test riêng

Ví dụ dùng Spring Boot 3.x, Spring Security 6.x, Java 17+ và JUnit Jupiter. Chính sách yêu cầu role `ADMIN` để đọc trang quản trị, role `EDITOR` để tạo bài viết và cho phép truy cập endpoint public. CSRF được giữ mặc định.

### 3.1. Controller và service

Tệp `src/main/java/example/ArticleService.java`:

~~~java
package example;

public interface ArticleService {
    String findById(String id);
    void create();
}
~~~

Tệp `src/main/java/example/ArticleController.java`:

~~~java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArticleController {
    private final ArticleService articleService;

    public ArticleController(ArticleService articleService) {
        this.articleService = articleService;
    }

    @GetMapping("/api/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/admin")
    public String adminInfo() {
        return "admin";
    }

    @GetMapping("/api/articles/{id}")
    public String article(@PathVariable String id) {
        return articleService.findById(id);
    }

    @PostMapping("/api/articles")
    public ResponseEntity<Void> createArticle() {
        articleService.create();
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

### 3.2. Security policy của ứng dụng

Tệp `src/main/java/example/SecurityConfiguration.java`:

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {
    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/articles").hasRole("EDITOR")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là policy cần kiểm tra. Test sẽ import class này và không khai báo một `SecurityFilterChain` thay thế.

### 3.3. Test-only configuration

Tệp `src/test/java/example/ArticleMvcTestSupport.java`:

~~~java
package example;

import static org.mockito.Mockito.mock;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class ArticleMvcTestSupport {
    @Bean
    ArticleService articleService() {
        return mock(ArticleService.class);
    }
}
~~~

`ArticleMvcTestSupport` chỉ cung cấp một mock `ArticleService` để controller được khởi tạo trong slice. Nó không định nghĩa `SecurityFilterChain`, không tắt CSRF và không thay đổi authorization rules. Vì service implementation nằm ngoài MVC slice, test kiểm tra routing và security mà không cần database hoặc business service thật.

Nếu muốn stub hoặc verify mock, test có thể inject `ArticleService` rồi dùng Mockito:

~~~java
when(articleService.findById("42")).thenReturn("Spring Security");
verify(articleService).create();
~~~

Các lệnh trên cần static import `when` và `verify` từ `org.mockito.Mockito`.

### 3.4. Test import cả hai cấu hình

Tệp `src/test/java/example/ArticleControllerSecurityTest.java`:

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ArticleController.class)
@Import({
    SecurityConfiguration.class,
    ArticleMvcTestSupport.class
})
class ArticleControllerSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @Autowired
    ArticleService articleService;

    @BeforeEach
    void setUp() {
        when(articleService.findById("42")).thenReturn("Spring Security");
    }

    @Test
    void anonymousCanReadPublicEndpoint() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousCannotReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCannotReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void authenticatedUserCanReadArticle() throws Exception {
        mockMvc.perform(get("/api/articles/42"))
            .andExpect(status().isOk())
            .andExpect(content().string("Spring Security"));
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorCanCreateArticleWithCsrf() throws Exception {
        mockMvc.perform(post("/api/articles").with(csrf()))
            .andExpect(status().isCreated());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorWithoutCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/api/articles"))
            .andExpect(status().isForbidden());
    }
}
~~~

Test này sử dụng controller thật, security policy thật và service mock. `@WithMockUser` tạo danh tính giả lập để kiểm tra authorization; `with(csrf())` cung cấp token hợp lệ cho request POST. Những ca bị từ chối giúp xác nhận filter chain đang thực thi policy đã import.

### 3.5. Kết quả mong đợi

| Request | Danh tính | Kết quả |
| --- | --- | --- |
| `GET /api/public` | Ẩn danh | 200 |
| `GET /api/admin` | Ẩn danh | 401 với HTTP Basic |
| `GET /api/admin` | VIEWER | 403 |
| `GET /api/admin` | ADMIN | 200 |
| `GET /api/articles/42` | USER | 200, service mock trả dữ liệu |
| `POST /api/articles` | EDITOR + CSRF hợp lệ | 201 |
| `POST /api/articles` | EDITOR, thiếu CSRF | 403 |

401/403 có thể khác nếu ứng dụng dùng form login hoặc entry point tùy chỉnh. Bảng trên mô tả kết quả của cấu hình HTTP Basic trong ví dụ.

## 4. Những điều không nên import vào test

### 4.1. Không tạo một SecurityFilterChain thứ hai chỉ để test

Một cách dễ làm sai mục tiêu là viết cấu hình test:

~~~java
@TestConfiguration
class UnsafeTestSecurityConfiguration {
    @Bean
    SecurityFilterChain testChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
~~~

Nếu import cấu hình này thay cho policy production, test có thể chạy xanh vì mọi request đều được cho phép. Nhưng nó không còn kiểm tra authorization hoặc CSRF mà ứng dụng thực sự sử dụng.

Khi có nhiều bean `SecurityFilterChain`, `FilterChainProxy` chọn **chuỗi đầu tiên khớp request** theo thứ tự. Một test chain với matcher rộng có thể đứng trước và che khuất chain cần kiểm tra. `@Primary` không phải cơ chế sắp thứ tự các chain trong `FilterChainProxy`; hãy xem `@Order` và `securityMatcher(...)`.

Chỉ khai báo chain riêng trong test khi mục tiêu thực sự là kiểm tra một policy test-specific. Khi đó cần nói rõ test đang kiểm tra policy nào và không dùng kết quả để kết luận policy production đã được xác minh.

### 4.2. Không vô hiệu hóa filter để tránh lỗi context

`@AutoConfigureMockMvc(addFilters = false)` hoặc cấu hình builder không tích hợp Spring Security có thể làm request đi thẳng tới controller. Nếu test nhằm kiểm tra bảo mật HTTP, không dùng cách này để né lỗi bean hoặc làm assertion trở nên xanh.

Nếu context thiếu service, provider hoặc decoder, hãy bổ sung đúng dependency cần thiết hoặc mock dependency ngoài phạm vi. Đừng bỏ `SecurityFilterChain` chỉ để khởi tạo slice thành công.

### 4.3. Không mock chính sách đang kiểm tra

Nếu thay `SecurityFilterChain` bằng mock, test không kiểm tra được matcher, filter, CSRF hay authorization rules thật. Hãy mock các collaborator nằm phía sau policy (service, client, repository hoặc provider nếu authentication không phải mục tiêu), còn chain cần xác minh phải là cấu hình thật.

## 5. @Import, @TestConfiguration và @MockitoBean

Ba cơ chế này phối hợp được, nhưng mục đích khác nhau:

| Cơ chế | Vai trò | Dùng khi |
| --- | --- | --- |
| `@Import(SecurityConfiguration.class)` | Đưa cấu hình bảo mật cụ thể vào slice | Cần xác minh policy thật |
| `@Import(TestSupportConfiguration.class)` | Bổ sung bean chỉ dành cho test | Cần fixture, converter hoặc dependency hỗ trợ |
| `@MockitoBean` | Thay một bean trong context bằng Mockito mock | Cần cô lập collaborator đã được đăng ký trong context |
| `@MockBean` | Cơ chế mock bean của Spring Boot ở các phiên bản cũ | Dự án chưa dùng Spring Framework 6.2+ |

Ví dụ dùng `@MockitoBean` thay cho test configuration cung cấp service:

~~~java
@WebMvcTest(ArticleController.class)
@Import(SecurityConfiguration.class)
class ArticleControllerSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    ArticleService articleService;
}
~~~

`@MockitoBean` thuộc `org.springframework.test.context.bean.override.mockito.MockitoBean` và có trong Spring Framework 6.2+. Với dự án Spring Boot cũ hơn, `@MockBean` là lựa chọn tương ứng (đã deprecated ở một số phiên bản Boot mới). Không cần đồng thời dùng cả `@MockitoBean` lẫn một `@TestConfiguration` khai báo bean cùng kiểu cho cùng mục đích.

**Chú ý khi thay bean:** nếu security configuration nhận `UserDetailsService`, `AuthenticationProvider`, `JwtDecoder` hoặc dependency khác qua tham số method `@Bean`, Spring cần có bean tương ứng để dựng chain. Có thể dùng `@MockitoBean` để cung cấp dependency khi test không kiểm tra implementation của nó. Nếu test cần xác minh authentication thật, hãy dùng implementation phù hợp và dữ liệu kiểm thử thay vì mock.

## 6. Khi SecurityConfiguration có nhiều dependency

Giả sử chain của ứng dụng bật JWT resource server:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http, JwtDecoder jwtDecoder)
        throws Exception {
    return http
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(jwtDecoder))
        )
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/reports").hasAuthority("SCOPE_reports.read")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Nếu import class cấu hình này, slice cần `JwtDecoder`. Khi chỉ kiểm tra authorization bằng JWT giả lập, có thể cung cấp mock decoder để dựng chain rồi dùng `with(jwt())` trên request. Post-processor `jwt()` tạo authentication giả lập, không gọi decoder để xác minh chữ ký.

Nếu mục tiêu là kiểm tra token thật, cung cấp decoder test phù hợp và gửi header `Authorization: Bearer ...` qua filter chain. Không dùng mock decoder hoặc `with(jwt())` để kết luận chữ ký, issuer, audience hay thời hạn token đã được xác minh.

Tương tự, nếu cấu hình authentication dùng `UserDetailsService` và `PasswordEncoder`, hãy xác định test đang kiểm tra:

- **Authorization:** có thể dùng `@WithMockUser`; không cần thực hiện user lookup hoặc kiểm tra password.
- **Authentication:** cần provider và dependency phù hợp, gửi credentials qua filter thực và kiểm tra kết quả xác thực.

## 7. Method security và cấu hình bổ trợ

URL authorization trong `SecurityFilterChain` và method security là hai lớp khác nhau. Nếu test cần kiểm tra `@PreAuthorize`, phải import cấu hình có `@EnableMethodSecurity` và gọi bean thật được Spring proxy:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Nếu service bị mock bằng `@MockitoBean`, method body và interceptor bảo mật trên implementation thật không chạy. Khi đó test vẫn có thể kiểm tra URL rule, nhưng không chứng minh method security của service.

Những cấu hình bổ trợ khác có thể được import khi thuộc phạm vi test:

- `@ControllerAdvice` hoặc `@RestControllerAdvice` để xác minh định dạng lỗi.
- CORS configuration khi kiểm thử preflight `OPTIONS`.
- Custom servlet filter nếu filter đó là một phần của đường đi request.
- Converter, formatter hoặc argument resolver tùy chỉnh nếu binding phụ thuộc chúng.
- Authentication entry point hoặc access denied handler riêng nếu chain tham chiếu các bean đó.

Chỉ import những gì test cần. Một slice quá rộng sẽ mất ưu điểm nhanh và cô lập; một slice quá hẹp có thể bỏ sót chính sách hoặc dependency cần xác minh.

## 8. Chẩn đoán khi kết quả không như mong đợi

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Endpoint public trả 401 | Custom chain chưa import; default security đang áp dụng | Import policy thật và kiểm tra matcher |
| Endpoint admin trả 200 cho ẩn danh | Filter không được đăng ký hoặc request không khớp chain | Kiểm tra filter, `securityMatcher` và ca bị từ chối |
| ADMIN vẫn bị 403 | Authority/prefix không đúng hoặc chain khác được chọn | Kiểm tra `hasRole`, `hasAuthority`, `@Order` |
| Context không khởi tạo | Thiếu dependency của cấu hình đã import | Bổ sung bean test hoặc mock đúng collaborator |
| POST trả 403 | Thiếu CSRF token hoặc không đủ quyền | Tách ca POST có CSRF và ca thiếu token |
| Kết quả xanh với mọi role | Test chain `permitAll()` đã che policy thật | Bỏ chain test và import cấu hình production |
| Method security không chặn | Chưa bật `@EnableMethodSecurity`, hoặc service bị mock | Dùng bean thật đã proxy và import cấu hình method security |
| Bean override conflict | Cấu hình test và ứng dụng cùng khai báo một bean không được phép thay thế | Dùng `@MockitoBean` có chủ đích hoặc chỉ cung cấp bean còn thiếu |

Checklist:

1. Test đang import đúng `SecurityConfiguration` cần xác minh?
2. Có cấu hình test nào định nghĩa thêm `SecurityFilterChain` không?
3. Nếu có nhiều chain, thứ tự và matcher có khiến chain khác được chọn trước không?
4. Những dependency được chain tham chiếu đã có trong slice chưa?
5. MockMvc có thực sự đăng ký security filters?
6. Có ca ẩn danh, thiếu quyền, đủ quyền và CSRF không?
7. Test có vô tình mock provider/decoder trong khi mục tiêu là authentication không?

Khi cần, bật log `org.springframework.security.web.FilterChainProxy` ở mức `DEBUG` hoặc `TRACE` để quan sát request được chọn chain nào. Log hỗ trợ chẩn đoán; assertion về response và các ca bị từ chối vẫn là bằng chứng hành vi chính.

## 9. Phân biệt @WebMvcTest với @SpringBootTest

| Tiêu chí | `@WebMvcTest` | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| --- | --- | --- |
| Context | MVC slice, cần import cấu hình ngoài phạm vi slice | Application context rộng hơn |
| Tốc độ | Thường nhanh hơn | Thường chậm hơn |
| Dependency controller | Thường mock hoặc import có chọn lọc | Có thể dùng bean thật |
| Custom security policy | Nên import rõ ràng để biết chain nào được kiểm tra | Thường được nạp theo cấu hình ứng dụng |
| Mục tiêu | Controller, mapping, response và policy chọn lọc | Tích hợp nhiều bean/config |
| HTTP server thật? | Không | Không với `WebEnvironment.MOCK`; có với `RANDOM_PORT` |

`@WebMvcTest` phù hợp khi câu hỏi tập trung vào một controller và policy có thể import rõ ràng. `@SpringBootTest` phù hợp hơn khi cần xác minh nhiều cấu hình hoặc authentication dependency trong application context. Khi cần TLS, proxy hoặc servlet container, dùng `RANDOM_PORT` và HTTP client thật.

**Với Reactive/WebFlux**, dùng `WebTestClient`, `SecurityWebFilterChain` và `SecurityMockServerConfigurers.springSecurity()`. `@WebMvcTest` và servlet `SecurityFilterChain` trong bài này chỉ dành cho Spring MVC.

## 10. Bài tập thực hành

**Bài 1 — Import đúng policy.** Tạo `@WebMvcTest` không import custom chain, quan sát phản hồi của endpoint public và admin. Sau đó import `SecurityConfiguration` và viết lại các ca 200/401/403.

**Bài 2 — Bổ sung fixture.** Tạo `@TestConfiguration` chỉ cung cấp mock `ArticleService`. Import nó cùng `SecurityConfiguration` và giải thích vì sao mock service không làm thay đổi role rules.

**Bài 3 — Phát hiện chain thay thế.** Tạo một test config có `SecurityFilterChain` dùng `permitAll()`. Quan sát vì sao test không còn kiểm chứng policy production; kiểm tra thứ tự chain khi có nhiều bean.

**Bài 4 — Dependency của authentication.** Thêm `AuthenticationProvider`, `UserDetailsService`, `PasswordEncoder` hoặc `JwtDecoder` vào security configuration. Quyết định bean nào cần thật và bean nào có thể mock theo mục tiêu authorization/authentication.

**Bài 5 — Method security.** Import cấu hình `@EnableMethodSecurity`, dùng service thật được proxy và kiểm tra `@PreAuthorize`. So sánh với test dùng service mock.

## 11. Ghi nhớ

**`@Import` nên bổ sung đúng cấu hình và bean còn thiếu cho MVC slice.** Hãy import `SecurityConfiguration` thật để kiểm tra policy của ứng dụng, và dùng `@TestConfiguration`, `@MockitoBean` hoặc `@MockBean` để cung cấp dependency phục vụ test.

Tránh tạo một `SecurityFilterChain` test quá rộng hoặc tắt filter để làm test xanh, vì khi đó test có thể không còn xác minh chính sách cần bảo vệ ứng dụng. Hãy kiểm tra cả request được phép và bị từ chối, đồng thời phân biệt rõ mock authorization với authentication thực tế.
