# @WebMvcTest và những bean bảo mật cần đưa vào lát cắt

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào **Spring MVC slice test** với `@WebMvcTest`: cách chọn controller cần kiểm thử, đưa cấu hình Spring Security vào test context và cung cấp các bean phụ thuộc để những ca kiểm thử phản ánh đúng hành vi mong muốn.

Sau bài học, bạn có thể:

1. Giải thích `@WebMvcTest` tải một lát cắt web thay vì toàn bộ application context.
2. Xác định vì sao custom `SecurityFilterChain` có thể không xuất hiện nếu cấu hình không được import.
3. Đưa `SecurityConfiguration` và những bean bảo mật liên quan vào lát cắt bằng `@Import`.
4. Cung cấp mock cho service, repository hoặc authentication dependency mà controller/security config cần.
5. Viết ca kiểm thử ẩn danh, đủ quyền, thiếu quyền và CSRF với `MockMvc`.
6. Phân biệt kiểm thử authorization bằng danh tính giả lập với kiểm thử authentication thật.

## 1. @WebMvcTest là một lát cắt của ứng dụng

`@WebMvcTest` tạo một **Spring MVC test slice**. Thay vì khởi tạo tất cả service, repository, scheduler và các thành phần hạ tầng của ứng dụng, nó tập trung vào các thành phần phục vụ web: controller được chọn, MVC infrastructure, message converter, formatter, validation và một số thành phần web liên quan.

Ví dụ:

~~~java
@WebMvcTest(ArticleController.class)
class ArticleControllerTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Lớp test trên yêu cầu Spring Boot tạo web context dành cho `ArticleController` và cung cấp `MockMvc`. Nó không có nghĩa mọi bean `@Configuration`, service hay security component trong ứng dụng production đều được tải.

Một số loại thành phần thường có thể xuất hiện trong slice:

- `@Controller`, `@RestController` được chỉ định hoặc được chọn theo quy tắc của slice.
- `@ControllerAdvice` và `@RestControllerAdvice` để xử lý ngoại lệ MVC.
- Các thành phần chuyển đổi/serialize, `Converter`, `GenericConverter`, `Filter`, `HandlerInterceptor`, `WebMvcConfigurer` và `HandlerMethodArgumentResolver` phù hợp với web layer.
- MVC infrastructure và các auto-configuration được `@WebMvcTest` lựa chọn.

Các `@Service`, `@Repository` hoặc cấu hình ứng dụng tổng quát thường không tự động được đưa vào slice. Nếu controller phụ thuộc service, test phải cung cấp dependency phù hợp, thường bằng mock bean.

~~~mermaid
flowchart TB
    A["@WebMvcTest(ArticleController.class)"] --> B["Web MVC test slice"]
    B --> C["Controller được chọn"]
    B --> D["MVC infrastructure<br/>JSON / validation / binding"]
    B --> E["Web components được chọn"]
    B --> F["Security auto-configuration<br/>nếu được kích hoạt"]
    G["@Import(SecurityConfiguration.class)"] --> H["Custom SecurityFilterChain<br/>và config được import"]
    I["@MockitoBean / @MockBean"] --> J["Mock service hoặc dependency"]
    C --> K["MockMvc"]
    D --> K
    E --> K
    F --> K
    H --> K
    J --> C
~~~

**Phạm vi slice là một quyết định thiết kế của test.** Một test chạy nhanh và cô lập tốt, nhưng chỉ chứng minh hành vi của những bean thực sự có mặt trong context. Khi một bean bị thiếu hoặc bị thay bằng mock, kết quả không tự động đại diện cho toàn bộ ứng dụng production.

## 2. Vì sao phải import cấu hình bảo mật?

Spring Security trong ứng dụng Servlet thường được cấu hình bằng một hoặc nhiều bean `SecurityFilterChain`. Ví dụ:

~~~java
@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

`@WebMvcTest` không quét và nạp mọi cấu hình ứng dụng như `@SpringBootTest`. Một class `@Configuration` định nghĩa chain tùy chỉnh có thể nằm ngoài tập component mà slice chọn. Nếu cấu hình đó không được import, test có thể chạy với security auto-configuration mặc định của Spring Boot hoặc một cấu hình test khác.

Vì vậy, nếu mục tiêu là kiểm tra chính sách URL của `SecurityConfiguration`, hãy đưa nó vào context:

~~~java
@WebMvcTest(ArticleController.class)
@Import(SecurityConfiguration.class)
class ArticleControllerSecurityTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

`@Import` đưa cấu hình được chỉ định vào slice. Khi `SecurityConfiguration` khai báo `SecurityFilterChain`, bean này có thể được dùng để xây dựng hạ tầng filter của context. `@WebMvcTest` trong Spring Boot cũng có tích hợp MockMvc và các auto-configuration liên quan; nếu Spring Security hiện diện trên classpath, cấu hình bảo mật có thể tham gia slice. Tuy nhiên, **không nên dựa vào cấu hình mặc định để đại diện cho custom chain của ứng dụng**.

### Security auto-configuration mặc định khác custom chain

Khi không có cấu hình chain tùy chỉnh, Spring Boot có thể tạo bảo mật mặc định cho ứng dụng web nếu các điều kiện auto-configuration phù hợp. Điều đó thường khiến endpoint bị yêu cầu xác thực dù bạn chưa import cấu hình của mình. Vì vậy, một test nhận 401 **không chứng minh** custom matcher, role hoặc authentication entry point production đã được tải.

Hãy phân biệt:

| Trạng thái test context | Điều có thể kết luận |
| --- | --- |
| Có default security config của Boot | Request có thể được bảo vệ theo mặc định; chưa chứng minh policy custom |
| Đã import custom `SecurityConfiguration` | Có thể kiểm tra các rule do cấu hình đó định nghĩa, nếu các dependency cần thiết cũng có mặt |
| Không có security filter | Request có thể đi thẳng tới controller; các kết quả 200/201 không chứng minh authorization |
| Import nhầm cấu hình test khác | Test chỉ chứng minh policy trong cấu hình test đã nạp |

Để xác minh, có thể kiểm tra bean chain trong context và viết các ca request mang tính phân biệt: URL public, URL private, người dùng thiếu role và người dùng đủ role.

## 3. Ví dụ hoàn chỉnh: import SecurityFilterChain vào @WebMvcTest

Ta xây một API có ba hành vi: đọc công khai, đọc khu vực quản trị và tạo bài viết chỉ dành cho `EDITOR`. CSRF được giữ bật theo mặc định để minh họa kiểm thử POST.

### 3.1. Controller

Tệp `src/main/java/example/ArticleController.java`:

~~~java
package example;

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

    @GetMapping("/api/admin")
    public String adminInfo() {
        return "admin";
    }

    @PostMapping("/api/articles")
    public ResponseEntity<Void> createArticle() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

### 3.2. Cấu hình bảo mật

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

Bean `applicationSecurity` là cấu hình mà test muốn kiểm tra. Nó cho phép GET public, yêu cầu role ADMIN ở GET admin và role EDITOR ở POST articles. HTTP Basic được bật để request ẩn danh có kết quả 401 dễ quan sát. CSRF không bị tắt.

### 3.3. Lớp kiểm thử slice

Tệp `src/test/java/example/ArticleControllerSecurityTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ArticleController.class)
@Import(SecurityConfiguration.class)
class ArticleControllerSecurityTest {
    @Autowired
    MockMvc mockMvc;

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
            .andExpect(status().isOk());
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

`@WebMvcTest(ArticleController.class)` tạo slice tập trung vào controller. `@Import(SecurityConfiguration.class)` đưa custom chain vào slice. `@WithMockUser` tạo authentication giả lập để kiểm tra authorization; `with(csrf())` tạo CSRF token cho request POST hợp lệ.

Kết quả kỳ vọng trong cấu hình này:

| Ca kiểm thử | Kết quả | Lý do |
| --- | --- | --- |
| GET public, ẩn danh | 200 | `permitAll()` |
| GET admin, ẩn danh | 401 | HTTP Basic entry point |
| GET admin, VIEWER | 403 | Không có `ROLE_ADMIN` |
| GET admin, ADMIN | 200 | Đủ quyền |
| POST articles, EDITOR + CSRF | 201 | Đủ quyền và CSRF hợp lệ |
| POST articles, EDITOR, thiếu CSRF | 403 | `CsrfFilter` từ chối |

Nếu ứng dụng dùng form login hoặc entry point tùy chỉnh, ca ẩn danh có thể trả 302 hoặc status khác theo contract. Hãy assert theo cấu hình thực tế.

## 4. Những bean nào cần đưa vào slice?

Không phải mọi test đều cần import cùng một tập bean. Hãy xuất phát từ **đường đi của request** và **những dependency được tham chiếu trong cấu hình**.

| Bean / thành phần | Khi nào cần trong `@WebMvcTest`? | Cách đưa vào |
| --- | --- | --- |
| Custom `SecurityFilterChain` | Khi muốn test chính sách URL/CSRF/headers của ứng dụng | `@Import(SecurityConfiguration.class)` |
| Cấu hình `@EnableMethodSecurity` | Khi muốn kiểm tra `@PreAuthorize` / method security | Import class cấu hình bật method security |
| `UserDetailsService` | Khi chain hoặc authentication provider cần tra cứu người dùng thật trong test | Import implementation phù hợp hoặc thay bằng mock nếu mục tiêu cho phép |
| `AuthenticationProvider` | Khi kiểm tra cơ chế xác thực tùy chỉnh | Import provider và dependencies của nó |
| `PasswordEncoder` | Khi authentication provider cần so sánh mật khẩu | Import bean encoder phù hợp; dùng cùng loại cấu hình với ứng dụng |
| `JwtDecoder` | Khi kiểm thử resource server với bearer token thực | Import cấu hình resource server và cung cấp decoder test phù hợp |
| OAuth2 client / authorized client services | Khi kiểm thử hành vi OAuth2 client liên quan tới MVC | Import config và cung cấp các service/client registration cần thiết |
| Service của controller | Khi controller gọi business logic | Mock bean hoặc import service nếu test cần logic thật |
| `@ControllerAdvice` tùy chỉnh | Khi cần xác minh định dạng lỗi toàn cục | Có thể được slice phát hiện; nếu không, dùng `@Import` |
| Custom filter/interceptor | Khi nó thuộc đường đi cần kiểm tra | Đảm bảo được slice phát hiện hoặc import/đăng ký rõ ràng |

### 4.1. Chỉ import cấu hình cần thiết

Ví dụ cấu hình bảo mật có một bean hỗ trợ:

~~~java
@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain applicationSecurity(
            HttpSecurity http,
            ApiAuthenticationProvider provider) throws Exception {
        return http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Nếu import class này vào `@WebMvcTest`, Spring phải giải quyết được `ApiAuthenticationProvider`. Có thể import provider và các dependency cần thiết, hoặc thay dependency bằng mock bean nếu test chỉ nhằm kiểm tra rule authorization và không kiểm tra authentication provider.

Với Spring Framework 6.2+ có thể dùng `@MockitoBean`; các phiên bản Spring Boot cũ thường dùng `@MockBean`. Ví dụ (chọn annotation phù hợp phiên bản dự án):

~~~java
@WebMvcTest(ArticleController.class)
@Import(SecurityConfiguration.class)
class ArticleControllerSliceTest {
    @MockitoBean
    ArticleService articleService;
}
~~~

`@MockitoBean` thay bean phù hợp trong test context bằng mock. Nếu dự án chưa hỗ trợ annotation này, dùng `@MockBean` từ Spring Boot Test theo phiên bản tương ứng. Không khai báo cả hai cho cùng một dependency.

### 4.2. Import cấu hình bảo mật có thể kéo theo những gì?

Một class cấu hình có thể tham chiếu các bean khác qua constructor hoặc tham số method `@Bean`. Khi import, Spring phải tạo các dependency cần thiết. Ví dụ:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        JwtDecoder jwtDecoder) throws Exception {
    return http
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(jwtDecoder))
        )
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Trong slice, `JwtDecoder` có thể không có nếu cấu hình resource server hoặc bean decoder không được tự nạp. Nếu test chỉ thử authorization với JWT giả lập, có thể cung cấp decoder mock/bean test tối thiểu để tạo filter chain, rồi dùng `with(jwt())` cho request. Nếu mục tiêu là kiểm tra decoder xác thực token thật, phải cung cấp decoder thực/test phù hợp và gửi bearer token qua filter; không dùng `with(jwt())` cho ca đó.

## 5. Cấu hình mặc định và lỗi “test vẫn 401”

Một slice có Spring Security trên classpath có thể được bảo vệ bởi **default security auto-configuration** của Spring Boot. Do đó, test sau:

~~~java
@WebMvcTest(ArticleController.class)
class ArticleControllerTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousIsRejected() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

có thể nhận 401 dù custom `SecurityConfiguration` của ứng dụng **chưa được import**. Kết quả chỉ cho thấy cấu hình đang có trong slice đã chặn request; nó không chứng minh `hasRole("ADMIN")` hoặc matcher custom được áp dụng.

Hãy tạo test phân biệt chính sách:

- URL được phép ẩn danh phải trả 200.
- URL chỉ cho ADMIN phải từ chối ẩn danh.
- VIEWER đã xác thực phải bị từ chối ở route ADMIN.
- ADMIN phải được phép.
- POST có CSRF hợp lệ và thiếu token phải cho hai kết quả khác nhau.

Một tập ca như vậy thường phát hiện được việc test đang dùng default chain hoặc thiếu custom chain tốt hơn một assertion 401 đơn lẻ.

### Không tắt filter để làm test chạy xanh

`@AutoConfigureMockMvc(addFilters = false)` tắt việc đăng ký filter với MockMvc được Boot tạo. Cấu hình này có thể hữu ích cho một test MVC không quan tâm filter, nhưng **không phù hợp để kiểm chứng Spring Security**. Khi filter bị tắt, các ca 401/403 và CSRF có thể không phản ánh hành vi ứng dụng.

Nếu test cần chạy qua custom filter, giữ mặc định đăng ký filter và đưa đúng bean vào context.

## 6. Kiểm thử method security trong MVC slice

`@PreAuthorize` là method security, khác với authorization theo URL trong `SecurityFilterChain`. Muốn kiểm tra annotation trên service/controller, phải bảo đảm method security được bật và đối tượng được gọi là bean có proxy bảo mật.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Nếu controller gọi một service có `@PreAuthorize`, slice phải có service bean (hoặc bean thay thế phù hợp) và cấu hình bật method security:

~~~java
@Service
class ReportService {
    @PreAuthorize("hasAuthority('REPORT_READ')")
    String report() {
        return "report";
    }
}
~~~

Khi test chỉ mock `ReportService`, lời gọi thực tế đi vào mock nên không kiểm tra được method security bên trong service. Nếu mục tiêu là xác minh annotation trên service, hãy đưa service thật và dependencies cần thiết vào test context, bật method security, rồi gọi qua bean proxy Spring quản lý. Nếu mục tiêu chỉ là kiểm tra HTTP authorization ở URL layer, không cần kéo toàn bộ service thật vào slice.

## 7. JWT, OAuth2 và xác thực trong slice

Chọn bean theo loại test:

| Mục tiêu | Bean/config cần có | Cách tạo request |
| --- | --- | --- |
| Kiểm tra role/scope sau khi đã xác thực | Custom `SecurityFilterChain`; cấu hình resource server tương ứng | `with(jwt())` hoặc authentication giả lập |
| Kiểm tra JWT decoder/validator | Resource server config và `JwtDecoder` thực hoặc test decoder phù hợp | Header `Authorization: Bearer ...` với token test |
| Kiểm tra OAuth2 login principal/role | Security config và các thành phần login cần thiết trong phạm vi test | `with(oauth2Login())` |
| Kiểm tra OIDC principal/claim | OIDC/security config phù hợp | `with(oidcLogin())` |
| Kiểm tra authorization code redirect/callback | Client registration, authorized client services và endpoint/callback config cần thiết | Test redirect/callback theo flow hoặc integration test |

`with(jwt())`, `oauth2Login()` và `oidcLogin()` của Spring Security Test giúp tạo authentication/principal giả lập. Chúng hữu ích để kiểm tra quyền truy cập và ánh xạ authority, nhưng không tự xác minh chữ ký JWT, issuer, audience, thời hạn token hay việc trao đổi authorization code với Identity Provider.

Với `@WebMvcTest`, hãy chỉ import cấu hình OAuth2/JWT cần thiết cho câu hỏi đang kiểm tra. Nếu muốn kiểm thử toàn bộ quá trình đăng nhập với nhà cung cấp ngoài hoặc cookie/session qua nhiều request, cân nhắc `@SpringBootTest` hoặc test tích hợp chuyên biệt thay vì cố nhồi toàn bộ hệ thống vào một MVC slice.

## 8. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| GET admin ẩn danh trả 200 | Filter không được đăng ký, matcher không khớp hoặc controller đang được test bằng cấu hình khác | Kiểm tra chain, filter, matcher và ca bị từ chối |
| GET admin ẩn danh trả 401 nhưng VIEWER cũng nhận 401 | Chưa thiết lập danh tính, hoặc test đang dùng default chain không có rule role mong đợi | Import custom config và kiểm tra `@WithMockUser` |
| ADMIN vẫn nhận 403 | Authority/prefix không khớp, chain khác được chọn hoặc CSRF với POST | Kiểm tra `hasRole`/`hasAuthority`, `@Order`, CSRF |
| Không tạo được context vì thiếu service/provider | Slice không nạp bean ứng dụng | Mock hoặc import đúng dependency |
| Không tìm thấy `JwtDecoder` | Resource server config tham chiếu bean ngoài slice | Cung cấp decoder phù hợp mục tiêu test |
| Controller trả lỗi 500 khi gọi service | Service không có trong slice hoặc mock chưa được cấu hình | Dùng `@MockitoBean`/`@MockBean` và stub hành vi |
| `@PreAuthorize` không chặn | Method security chưa bật, service bị mock hoặc không đi qua proxy | Import config, dùng bean thật đã proxy |
| Test 401/403 biến mất sau khi tắt filters | `addFilters = false` làm bỏ qua security filters | Bật lại filters trong security tests |
| Test chạy đơn lẻ được nhưng suite thất bại | Shared state, context tùy biến hoặc mock reset chưa đúng | Dọn trạng thái, cấu hình mock rõ ràng và bỏ phụ thuộc thứ tự |

Checklist debug:

1. `@WebMvcTest` đang chọn đúng controller chưa?
2. Custom `SecurityConfiguration` đã được `@Import` chưa?
3. Mọi dependency được tham chiếu từ `SecurityFilterChain` đã có trong context chưa?
4. MockMvc có đăng ký filter không? Có vô tình dùng `addFilters = false` không?
5. Request có khớp đúng `SecurityFilterChain` và rule authorization không?
6. Danh tính giả lập có authority đúng, và POST có CSRF token khi cần không?
7. Test có đang vô tình mock chính service mà bạn định kiểm tra method security không?

## 9. Chọn giữa @WebMvcTest và @SpringBootTest

| Tiêu chí | `@WebMvcTest` | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| --- | --- | --- |
| Phạm vi | MVC slice, chỉ những bean được chọn/import | Application context rộng hơn theo cấu hình test |
| Tốc độ | Thường nhanh hơn | Thường chậm hơn |
| Dependency của controller | Thường mock | Có thể dùng bean thật hoặc mock |
| Custom SecurityFilterChain | Thường phải import rõ ràng nếu không được slice nạp | Thường được nạp cùng application config |
| Mục tiêu | Controller, MVC mapping, response và security policy có chọn lọc | Tích hợp nhiều bean/config trong ứng dụng |
| Giới hạn | Không chứng minh toàn bộ wiring production | Vẫn là MockMvc, không kiểm tra TCP/TLS/server thật |

Nếu mục tiêu chỉ là kiểm tra endpoint và luật phân quyền cụ thể, `@WebMvcTest` là lựa chọn gọn. Nếu cần xác minh nhiều cấu hình tương tác hoặc authentication provider thực, `@SpringBootTest` có thể phù hợp hơn. Khi cần HTTP server thật, dùng `webEnvironment = RANDOM_PORT` và client thực.

### Ghi chú cho Reactive/WebFlux

`@WebMvcTest` và `MockMvc` dành cho Servlet MVC. Ứng dụng Reactive sử dụng `WebTestClient`, `SecurityWebFilterChain` và reactive security test configurer như `SecurityMockServerConfigurers.springSecurity()`. Không áp dụng cách import filter Servlet hoặc `@WebMvcTest` cho pipeline WebFlux.

## 10. Bài tập thực hành

**Bài 1 — Phát hiện default chain.** Tạo `@WebMvcTest` không import custom security config. Quan sát phản hồi ẩn danh, sau đó import `SecurityConfiguration` và viết lại ca public/admin. Giải thích vì sao 401 ban đầu không chứng minh custom policy đã được nạp.

**Bài 2 — Kiểm tra quyền.** Dùng `@WithMockUser` với các role VIEWER, ADMIN và EDITOR để kiểm thử những endpoint tương ứng. Bao phủ cả trường hợp được phép và bị từ chối.

**Bài 3 — Dependency của security config.** Thêm `UserDetailsService` hoặc `AuthenticationProvider` vào cấu hình. Xác định dependency nào slice không tự tạo, sau đó quyết định import thật hay thay bằng mock dựa trên mục tiêu test.

**Bài 4 — JWT.** Dùng `with(jwt())` để thử scope thiếu/đủ quyền. Sau đó viết một test riêng gửi bearer token qua `JwtDecoder` và giải thích khác biệt giữa hai test.

**Bài 5 — Method security.** Thêm `@PreAuthorize` trên service. Chạy test khi service là mock và khi service là bean thật được proxy; quan sát trường hợp nào thực sự kiểm tra annotation.

## 11. Ghi nhớ

**`@WebMvcTest` tạo một lát cắt MVC, vì vậy custom security config và những dependency ngoài web layer phải được đưa vào có chủ đích.** Dùng `@Import(SecurityConfiguration.class)` để kiểm tra chain tùy chỉnh; dùng mock bean cho service hoặc provider khi mục tiêu không yêu cầu chạy implementation thật; và import cấu hình method security khi cần kiểm tra `@PreAuthorize`.

Một MVC slice test chỉ chứng minh hành vi của **các bean và filter có trong slice đó**. Hãy kiểm tra cả URL public, request ẩn danh, người dùng thiếu quyền, người dùng đủ quyền và CSRF. Nếu cần xác minh authentication provider, JWT decoder, session hoặc toàn bộ wiring của ứng dụng, mở rộng phạm vi test cho phù hợp.
