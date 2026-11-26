# SecurityMockMvcConfigurers.springSecurity để kết nối hạ tầng kiểm thử

## Mục tiêu bài học

Trong chương **Thiết lập MockMvc** thuộc mô-đun **SPRING_SECURITY_TESTING**, người học cần kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test`. Bài này tập trung vào ứng dụng **Servlet/Spring MVC** và phương thức `SecurityMockMvcConfigurers.springSecurity()`: cầu nối giúp các request của `MockMvc` thực sự đi qua cơ chế Spring Security trong test application context.

Kết thúc bài, bạn có thể:

1. Giải thích vì sao chỉ có `@WithMockUser` hoặc bean `SecurityFilterChain` trong context vẫn chưa đủ để khẳng định một `MockMvc` đang kiểm thử bảo mật HTTP.
2. Dùng `MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build()` đúng cách.
3. Phân biệt tích hợp thủ công với `@AutoConfigureMockMvc` của Spring Boot.
4. Kiểm tra danh tính qua `@WithMockUser`, `with(user(...))`, trạng thái 401/403 và CSRF trên **cùng pipeline**.
5. Chẩn đoán lỗi thiếu filter, cấu hình context không khớp, đăng ký filter lặp và nhầm lẫn giữa xác thực giả lập với xác thực thực tế.

## 1. Vì sao MockMvc cần tích hợp với Spring Security?

`MockMvc` tạo `MockHttpServletRequest`, đưa request vào Spring MVC và cho phép so sánh response mà **không mở cổng HTTP thật**. Nhưng khả năng kiểm tra URL mapping, controller hay JSON **không tự bảo đảm** rằng chuỗi lọc bảo mật đã được gắn vào đối tượng `MockMvc` bạn đang dùng.

Giả sử cấu hình ứng dụng yêu cầu role `EDITOR` khi gọi `POST /api/articles`. Nếu test chỉ tạo controller bằng `standaloneSetup(controller)` mà không thêm filter, controller có thể trả **201 Created** cho cả người dùng ẩn danh. Kết quả đó cho thấy controller chạy được; nó không xác nhận chính sách phân quyền hoạt động.

Khi dùng `webAppContextSetup(context)`, Spring MVC lấy cấu hình từ `WebApplicationContext`. Tuy vậy, **builder thủ công vẫn cần tích hợp Spring Security** để filter bảo mật tham gia request và các tiện ích giả lập `SecurityContext` hoạt động nhất quán. Điểm tích hợp thường dùng là:

~~~java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

MockMvc mockMvc = webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
~~~

Đây là phương thức tĩnh `springSecurity()` trong lớp `SecurityMockMvcConfigurers` của thư viện `spring-security-test`; **không phải** method `springSecurity()` của `HttpSecurity` hay một bean có tên này do ứng dụng tự viết.

## 2. springSecurity() nối những thành phần nào?

Ứng dụng Servlet có thể định nghĩa một hoặc nhiều bean `SecurityFilterChain`. Spring Security tập hợp các chuỗi này vào bộ lọc đầu vào, thông thường dưới tên bean **`springSecurityFilterChain`**. Thành phần điều phối bên trong là `FilterChainProxy`, có nhiệm vụ chọn chuỗi khớp request và chạy các security filter tương ứng.

`SecurityMockMvcConfigurers.springSecurity()` thực hiện những bước tích hợp cần thiết giữa Spring MVC Test và Spring Security Test:

- Lấy **filter đầu vào** `springSecurityFilterChain` từ `WebApplicationContext` để đưa vào pipeline của `MockMvc`.
- Kết nối phần hỗ trợ **`TestSecurityContextHolder`** với xử lý request, thông qua post-processor do Spring Security Test cung cấp, nhờ đó ngữ cảnh bảo mật được tạo cho test có thể được dùng trong luồng MVC mock.
- Giúp các tiện ích kiểm thử như `@WithMockUser`, `with(user(...))`, `with(authentication(...))` hoặc các assertion liên quan đến authentication vận hành trên một request có bảo mật được tích hợp.

~~~mermaid
flowchart TD
    A["JUnit test"] --> B["MockMvc.perform(...)"]
    C["@WithMockUser / with(user(...))"] --> D["Test SecurityContext"]
    E["WebApplicationContext"] --> F["Bean springSecurityFilterChain"]
    G[".apply(springSecurity())"] --> H["Cấu hình MockMvc<br/>filter + test context"]
    D --> H
    F --> H
    B --> H
    H --> I["FilterChainProxy:<br/>chọn SecurityFilterChain"]
    I --> J["Authentication / Authorization<br/>CSRF / security headers"]
    J --> K["DispatcherServlet / Controller<br/>nếu request được phép"]
    K --> L["andExpect(...)"]
~~~

**Hai phần bổ trợ nhau:** có danh tính giả lập trong test context chưa chứng minh security filters được chạy; có một filter bean trong Spring context chưa chứng minh **instance MockMvc** đã đăng ký filter đó. Chính các ca kiểm thử *bị từ chối* (ví dụ 401, 403) mới giúp xác minh hành vi mong đợi từ đầu tới cuối.

> **Lưu ý về kiểu bean:** `SecurityFilterChain` là chính sách cho một tập request; `FilterChainProxy` là bộ điều phối. Bean `springSecurityFilterChain` cung cấp giao diện `jakarta.servlet.Filter` cho bên gọi. Tùy phiên bản Spring Security, nó có thể được bọc bởi thành phần khác; không nên ép kiểu mù quáng bean này thành `FilterChainProxy`.

## 3. Chuẩn bị dự án Spring Boot Servlet

Ví dụ sau sử dụng Spring Boot 3.x, Spring MVC, Spring Security 6.x, Java 17+ và JUnit Jupiter. Với phiên bản khác, package của annotation auto-configuration có thể thay đổi; điểm cốt lõi vẫn là cấu hình `SecurityFilterChain` và tích hợp đúng với `MockMvc`.

Trong Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

`spring-boot-starter-test` cung cấp JUnit, Spring Test và MockMvc; `spring-security-test` cung cấp `springSecurity()`, `@WithMockUser` và những request post-processor bảo mật. Với Maven, sử dụng các artifact tương ứng và scope `test` cho hai phụ thuộc kiểm thử.

### 3.1. Controller và SecurityFilterChain

Tệp `src/main/java/example/DemoApplication.java`:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Tệp `src/main/java/example/ArticleController.java`:

~~~java
package example;

import java.security.Principal;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArticleController {
    @GetMapping("/api/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/api/me")
    public String currentUser(Principal principal) {
        return principal.getName();
    }

    @PostMapping("/api/articles")
    public ResponseEntity<Void> createArticle() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/articles")
                    .hasRole("EDITOR")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            // Giữ CSRF mặc định để kiểm chứng POST có/không có token.
            .build();
    }
}
~~~

Ví dụ tạo những quy tắc rõ ràng:

| Request | Người dùng | Kết quả dự kiến |
| --- | --- | --- |
| `GET /api/public` | Ẩn danh | 200 |
| `GET /api/me` | Ẩn danh | 401 với HTTP Basic |
| `GET /api/me` | Đã xác thực | 200; body là tên người dùng |
| `POST /api/articles` + CSRF hợp lệ | `VIEWER` | 403 vì thiếu `ROLE_EDITOR` |
| `POST /api/articles` + CSRF hợp lệ | `EDITOR` | 201 |
| `POST /api/articles` không có CSRF | `EDITOR` | 403 |

Chú ý sự khác nhau giữa **đăng nhập** và **được phân quyền**: `@WithMockUser(roles = "EDITOR")` tạo authority `ROLE_EDITOR` cho phép thử, không thực hiện truy vấn người dùng hay kiểm tra mật khẩu.

## 4. Dùng springSecurity() với webAppContextSetup

Tệp `src/test/java/example/ArticleSecurityMockMvcTest.java` sau đây minh họa cách gắn security configurer vào một builder **được tạo thủ công**.

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ArticleSecurityMockMvcTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = webAppContextSetup(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void publicRequestIsAllowed() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "linh", roles = "VIEWER")
    void annotationSetsAuthenticatedUser() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isOk())
            .andExpect(content().string("linh"));
    }

    @Test
    void requestProcessorSetsAuthenticatedUser() throws Exception {
        mockMvc.perform(get("/api/me")
                .with(user("mai").roles("VIEWER")))
            .andExpect(status().isOk())
            .andExpect(content().string("mai"));
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void insufficientRoleIsRejected() throws Exception {
        mockMvc.perform(post("/api/articles").with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorCanCreateArticle() throws Exception {
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

Trong ví dụ:

- `@SpringBootTest(webEnvironment = MOCK)` tải `WebApplicationContext` mà không chạy server HTTP thật.
- `webAppContextSetup(context)` cho MockMvc sử dụng các thành phần MVC đã nạp trong context.
- `.apply(springSecurity())` nối filter bảo mật và hỗ trợ sử dụng test `SecurityContext`.
- `@WithMockUser` áp dụng danh tính ở mức test method; `with(user(...))` áp dụng danh tính riêng cho **một request**.
- `with(csrf())` cung cấp CSRF token hợp lệ để tách nguyên nhân 403 do quyền truy cập với 403 do CSRF.

Ca `anonymousRequestIsRejected`, `insufficientRoleIsRejected` và `editorWithoutCsrfIsRejected` đặc biệt có giá trị: chúng xác nhận những tình huống phải bị chặn thực sự bị chặn, giảm nguy cơ test **xanh giả** khi filter không được nạp.

### Vì sao không chỉ kiểm tra 200/201?

Giả sử vô tình bỏ `.apply(springSecurity())`. Một request đi thẳng vào controller có thể trả 200/201, khiến phép thử “được phép” vẫn thành công. Nhưng những ca yêu cầu 401/403 sẽ thất bại. Vì thế bộ kiểm thử bảo mật cần bao gồm **được phép, chưa xác thực, đã xác thực nhưng thiếu quyền, và thiếu/CSRF sai**.

Sơ đồ luồng request:

~~~mermaid
flowchart LR
    A["@WithMockUser / with(user)"] --> B["SecurityContext của request"]
    C["MockMvc.perform"] --> D["springSecurity() đã áp dụng"]
    B --> D
    D --> E["Security filters"]
    E --> F{"Kiểm tra hợp lệ?"}
    F -->|Không| G["401 / 403"]
    F -->|Có| H["Controller"]
    H --> I["200 / 201"]
~~~

## 5. Quan hệ với TestSecurityContextHolder và các request post-processor

Spring Security Test hỗ trợ nhiều cách thiết lập authentication giả lập:

| Cách dùng | Cấp danh tính ở đâu? | Thích hợp để thử |
| --- | --- | --- |
| `@WithMockUser(username = "linh", roles = "EDITOR")` | Test method/class, qua hạ tầng Spring Test | Authorization của request trong test |
| `with(user("linh").roles("EDITOR"))` | Trên một request cụ thể của MockMvc | Hai request trong cùng test có danh tính khác nhau |
| `with(anonymous())` | Một request cụ thể | Route công khai và trường hợp ẩn danh |
| `with(authentication(authentication))` | Một request, bằng đối tượng `Authentication` do test cung cấp | Principal và authorities tùy chỉnh |
| `with(jwt())` | Một request, `JwtAuthenticationToken` giả lập | Authorization theo scope/authority của resource server |
| `with(oauth2Login())` hoặc `with(oidcLogin())` | Một request, principal sau OAuth2/OIDC login | Quy tắc phân quyền sau đăng nhập |

`@WithMockUser` được Spring Security Test chuẩn bị bằng hạ tầng test execution listener, tạo `SecurityContext` phù hợp cho test. Những request post-processor như `with(user(...))` hoặc `with(authentication(...))` chuẩn bị authentication trên **request**. Security configurer giúp tích hợp phần ngữ cảnh kiểm thử này với chuỗi lọc của MockMvc.

Ví dụ chạy hai danh tính trên cùng instance MockMvc:

~~~java
mockMvc.perform(get("/api/me")
        .with(user("alice").roles("VIEWER")))
    .andExpect(status().isOk())
    .andExpect(content().string("alice"));

mockMvc.perform(get("/api/me")
        .with(user("bob").roles("EDITOR")))
    .andExpect(status().isOk())
    .andExpect(content().string("bob"));
~~~

`@WithMockUser` và `with(user(...))` giúp cô lập phép thử phân quyền, nhưng **không gọi** `AuthenticationProvider` để kiểm tra username/password. Tương tự, `with(jwt())` không chứng minh chữ ký JWT đã được decoder xác minh. Muốn kiểm thử đường đi xác thực thật, cần gửi header `Authorization` hoặc dữ liệu đăng nhập tới filter đã cấu hình và không dùng post-processor tạo sẵn authentication cho ca đó.

> Tránh gọi `SecurityContextHolder.setContext(...)` thủ công rồi suy ra MockMvc sẽ đọc đúng ngữ cảnh đó cho mọi request. Spring Security quản lý vòng đời context theo filter và cơ chế lưu trữ của nó; `@WithMockUser` và các post-processor do `spring-security-test` cung cấp là lựa chọn ổn định hơn cho kiểm thử.

## 6. So sánh với @AutoConfigureMockMvc trong Spring Boot

Khi dùng Spring Boot và muốn giảm mã cấu hình, có thể yêu cầu Boot tạo MockMvc:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ArticleSecurityBootTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadProfile() throws Exception {
        mockMvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Các import tương ứng: `org.springframework.boot.test.context.SpringBootTest`, `org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc` (Spring Boot 3.x), `org.springframework.beans.factory.annotation.Autowired`, JUnit `@Test` và static import của MockMvc request/result.

`@AutoConfigureMockMvc` đăng ký một `MockMvc` được liên kết với web application context. Mặc định `addFilters = true` nên các `Filter` trong test context, bao gồm filter bảo mật nếu có, được áp dụng. Với `spring-security-test` trên classpath, Boot có thể cung cấp thêm tích hợp Spring Security Test cần thiết; bạn thường chỉ cần inject `MockMvc`.

**Không cần tạo builder thứ hai** nếu instance MockMvc do Boot cấp đã có filter. Quan trọng là xác định test đang gọi instance nào:

~~~java
// Boot quản lý MockMvc:
@AutoConfigureMockMvc
@Autowired MockMvc bootMockMvc;

// Hoặc tự xây một MockMvc riêng từ WebApplicationContext:
MockMvc manualMockMvc = webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Hai dòng này đại diện cho **hai cách cấu hình thay thế**. Không nên vô tình thêm cùng filter hai lần vào **cùng một builder**, vì việc chạy filter lặp có thể tạo hành vi sai.

Một cấu hình dễ làm test bảo mật mất tác dụng:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

Nó vô hiệu hóa việc đăng ký các filter với MockMvc do Boot tạo, nên có thể khiến các ca 401/403 không còn đúng. Cấu hình này đôi khi hữu ích cho test controller thuần, nhưng không phù hợp khi mục tiêu là khẳng định endpoint được bảo vệ bởi Spring Security.

## 7. Trường hợp standaloneSetup và springSecurity(Filter)

`MockMvcBuilders.standaloneSetup(controller)` tự dựng một môi trường MVC quanh controller; nó **không tự tìm filter từ Spring context**. Nếu muốn tích hợp một filter bảo mật có sẵn, `SecurityMockMvcConfigurers` còn có overload nhận đối tượng `Filter`:

~~~java
import jakarta.servlet.Filter;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

Filter securityFilter =
    context.getBean("springSecurityFilterChain", Filter.class);

MockMvc securedStandalone = MockMvcBuilders.standaloneSetup(controller)
    .apply(springSecurity(securityFilter))
    .build();
~~~

Ở đây `context` là `WebApplicationContext` đã nạp Spring Security; `controller` là instance mà test cung cấp. Đoạn trên minh họa cấu hình đặc biệt, không phải mô hình standalone *không có context*. Các kiểu `MockMvc`, `MockMvcBuilders` và bean `controller` cần được import/cung cấp trong lớp test thích hợp.

Cách này chỉ kết nối filter mà bạn truyền vào; nó **không tự nạp toàn bộ** `@ControllerAdvice`, message converter tùy chỉnh, MVC argument resolver hay proxy method security từ application context. Nếu mục tiêu kiểm chứng cấu hình bảo mật thực của ứng dụng, `webAppContextSetup(context).apply(springSecurity())` thường ít phải lắp ghép hơn.

Phân biệt hai thao tác:

- `.addFilters(filter)`: trực tiếp đưa một servlet filter vào MockMvc, hữu ích khi chỉ cần test filter hoặc thiết lập thủ công.
- `.apply(springSecurity(...))`: dùng cấu hình chuyên biệt của Spring Security Test để kết nối filter **và** hỗ trợ ngữ cảnh xác thực giả lập.

Khi sử dụng các helper `@WithMockUser` hoặc `with(user(...))`, hãy chọn cấu hình tích hợp đầy đủ phù hợp với cách bạn dựng MockMvc.

## 8. Khi springSecurity() không hoạt động như mong đợi

### 8.1. Không tìm thấy springSecurityFilterChain

`springSecurity()` không tự tạo chính sách bảo mật cho một context không có web security. Nếu thiếu bean filter đầu vào, builder có thể không hoàn tất.

Kiểm tra lần lượt:

1. Dự án có dependency `spring-boot-starter-security`/Spring Security web tương ứng không?
2. Test có tải đúng `SecurityConfiguration` và các bean `SecurityFilterChain` không?
3. `@WebMvcTest` có tạo một slice context khác với application context thật không? Có cần `@Import(SecurityConfiguration.class)` hoặc cấu hình test thích hợp không?
4. `context.getBean("springSecurityFilterChain", Filter.class)` có trả về filter không?

Ví dụ introspection trong test:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void securityFilterExists() {
    assertThat(applicationContext
        .getBean("springSecurityFilterChain"))
        .isInstanceOf(jakarta.servlet.Filter.class);
}
~~~

Các import giả định: `org.springframework.context.ApplicationContext` và `org.assertj.core.api.Assertions.assertThat`. Đây là phép kiểm tra **sự tồn tại của bean**, chưa đủ để chứng minh MockMvc đã đăng ký hoặc thực thi filter. Hãy ghép với ca request bị từ chối.

### 8.2. Có bean nhưng ẩn danh vẫn nhận 200

Thường gặp khi test đang sử dụng instance MockMvc **khác** với instance đã cấu hình `springSecurity()`, hoặc đăng ký filter bị tắt. Ngoài ra, với nhiều bean `SecurityFilterChain`, request có thể **không khớp** chuỗi nào hoặc khớp một chuỗi cho phép truy cập.

Ví dụ chỉ áp dụng chính sách cho `/api/**`:

~~~java
http.securityMatcher("/api/**");
~~~

Request `/admin` không thuộc vùng matcher đó. Nếu ứng dụng không có chain fallback, route ngoài phạm vi có thể không đi qua chuỗi Spring Security nào. Kiểm tra `securityMatcher`, `@Order` của các chain và test cả vùng khớp lẫn ngoài vùng khớp.

### 8.3. Test có @WithMockUser nhưng vẫn nhận 401/403

Các nguyên nhân thường gặp bao gồm:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@WithMockUser` nhưng request ẩn danh | MockMvc/test context integration thiếu hoặc test không dùng instance đã cấu hình | Dùng `.apply(springSecurity())` hoặc MockMvc Boot đã tự cấu hình |
| `@WithMockUser(roles = "EDITOR")` vẫn 403 | Request `POST` thiếu CSRF token | Thêm `with(csrf())`; viết ca thiếu token riêng |
| `@WithMockUser(roles = "ADMIN")` vẫn 403 | Rule đòi một authority khác, hoặc chain được chọn khác mong đợi | Kiểm tra `ROLE_` prefix, `hasAuthority` và chain matcher |
| Ẩn danh nhận 302 thay vì 401 | `formLogin` redirect đến trang đăng nhập | Assert mã redirect đúng contract thay vì áp đặt HTTP Basic |
| Không có SecurityContext trong controller | Filter hoặc post-processor ngữ cảnh chưa được gắn, hoặc sử dụng phương pháp dựng request không phù hợp | Kiểm tra cấu hình MockMvc và test identity trên `GET /api/me` |
| Filter chạy hai lần | Vừa auto-register vừa thêm filter thủ công vào cùng builder | Xác định một đường đăng ký filter thống nhất |

Đặc biệt, `with(csrf())` chỉ giúp **tạo CSRF token trên request**. Nó không tự đưa `CsrfFilter` vào MockMvc. Nếu test không chạy qua filter, phép thử CSRF có thể cho kết quả sai.

### 8.4. Quan sát chuỗi filter khi cần điều tra

Có thể bật log test:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Log hỗ trợ xác định request được áp dụng chuỗi nào và các filter liên quan; nội dung log cụ thể tùy phiên bản. Với nhiều chain, nhớ phân biệt `http.securityMatcher(...)` (phạm vi của chain) và `authorizeHttpRequests().requestMatchers(...)` (luật phân quyền trong chain đã chọn).

## 9. Giới hạn của tích hợp này và phạm vi Reactive

`springSecurity()` dành cho **Servlet MVC Test**. Nó giúp kiểm thử security filters và logic Spring MVC trong một tiến trình; **không chạy TLS handshake, TCP socket, reverse proxy hoặc servlet container đang lắng nghe HTTP thật**. Khi mục tiêu là thử hành vi hạ tầng thực, bổ sung `@SpringBootTest(webEnvironment = RANDOM_PORT)` và client gửi request qua HTTP.

Với ứng dụng **Reactive/WebFlux**, các kiểu và API khác:

| Servlet | Reactive |
| --- | --- |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `FilterChainProxy` | `WebFilterChainProxy` |
| `MockMvc` | `WebTestClient` |
| `SecurityMockMvcConfigurers.springSecurity()` | `SecurityMockServerConfigurers.springSecurity()` |
| `with(user(...))`, `with(jwt())` | `mutateWith(mockUser())`, `mutateWith(mockJwt())` |

Với WebFlux, gắn `WebTestClient` vào reactive application context rồi áp dụng reactive security configurer. Không dùng `SecurityMockMvcConfigurers.springSecurity()` của Servlet cho `WebTestClient`. Các thao tác `mockJwt()` hoặc `jwt()` giả lập xác thực để thử phân quyền; chúng không mặc nhiên kiểm tra chữ ký hoặc tính hợp lệ của JWT thật.

## 10. Bài tập thực hành

**Bài 1 — Phát hiện filter bị thiếu.** Bỏ `.apply(springSecurity())` khỏi `ArticleSecurityMockMvcTest`. Chạy các ca GET/POST và ghi lại sự thay đổi: ca truy cập trái phép nào không còn bị chặn? Khôi phục cấu hình sau khi quan sát.

**Bài 2 — Hai danh tính trong một test.** Dùng `with(user(...))` gọi `GET /api/me` hai lần với `alice` và `bob`, đối chiếu body tương ứng. Sau đó dùng `@WithMockUser` cho một phương thức khác và so sánh phạm vi áp dụng.

**Bài 3 — Phân biệt 403 do role và CSRF.** Viết một request POST có `ROLE_VIEWER` kèm CSRF hợp lệ, một request `ROLE_EDITOR` thiếu CSRF và một request `ROLE_EDITOR` có CSRF hợp lệ. Giải thích vì sao cả hai ca đầu có thể cùng 403 nhưng cơ chế chặn khác nhau.

**Bài 4 — So sánh Boot và builder thủ công.** Chạy cùng những ca ở mục 4 bằng `@AutoConfigureMockMvc` và bằng `webAppContextSetup(context).apply(springSecurity())`. Xác minh cùng kết quả khi cả hai instance đều được tích hợp đúng.

**Bài 5 — Kiểm tra security context và nhiều chain.** Tạo thêm `SecurityFilterChain` riêng cho `/admin/**`, áp dụng `@Order` và test một URL khớp chuỗi này. Quan sát điều gì xảy ra nếu chain quá rộng được đặt trước chuỗi dành riêng.

## 11. Ghi nhớ

**`SecurityMockMvcConfigurers.springSecurity()` kết nối hạ tầng Spring Security với một MockMvc được dựng từ `WebApplicationContext`.** Nó đưa filter bảo mật của context vào pipeline và chuẩn bị tích hợp `TestSecurityContextHolder` phục vụ những ca kiểm thử có authentication giả lập.

Để bài test bảo mật có giá trị, hãy đồng thời kiểm tra **bean cấu hình đã được nạp, filter thực sự chạy trên instance MockMvc đang dùng, và kết quả ở cả các ca được phép lẫn bị từ chối**. `@WithMockUser` hay `with(jwt())` rất hữu ích khi kiểm thử phân quyền, nhưng không thay thế phép thử xác thực credentials/token thực tế và không chứng minh đường truyền HTTP ngoài JVM đã được bảo vệ.
