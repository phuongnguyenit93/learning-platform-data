# Kiểm thử tích hợp bảo mật với @SpringBootTest và @AutoConfigureMockMvc

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, bạn kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng spring-security-test trên ứng dụng Servlet và Reactive. Bài này tập trung vào cách kết hợp **@SpringBootTest** với **@AutoConfigureMockMvc** để kiểm tra security trong application context đầy đủ của một ứng dụng Spring Boot.

Sau bài học, bạn có thể:

1. Phân biệt vai trò của **@SpringBootTest** và **@AutoConfigureMockMvc**.
2. Hiểu request đi qua servlet filter và Spring Security trước khi tới controller như thế nào.
3. Viết kiểm thử tích hợp cho endpoint công khai, endpoint yêu cầu đăng nhập, role, authority và CSRF.
4. Chọn đúng cách tạo người dùng kiểm thử: **@WithMockUser**, **@WithUserDetails** hoặc thông tin đăng nhập thực tế.
5. Xác định giới hạn của MockMvc và biết khi nào cần khởi động HTTP server thật.
6. Xử lý cấu hình test, nhiều SecurityFilterChain và các lỗi thường gặp khi tải application context.

Các ví dụ dùng Spring Boot 3.x, Spring Security 6.x, Java 17+ và JUnit Jupiter. Hãy dùng phiên bản dependency tương thích với Spring Boot mà dự án đang quản lý.

## 1. Hai annotation phối hợp như thế nào?

**@SpringBootTest** khởi tạo application context theo cấu hình của ứng dụng Spring Boot. Spring Boot tìm lớp cấu hình chính, thường là lớp có **@SpringBootApplication**, rồi nạp các bean và auto-configuration phù hợp với môi trường test.

Với cấu hình mặc định, **@SpringBootTest** dùng web environment kiểu **MOCK** cho ứng dụng Servlet. Spring tạo web application context cùng các thành phần web mô phỏng, nhưng không mở cổng HTTP và không khởi động embedded server để nhận kết nối mạng.

**@AutoConfigureMockMvc** yêu cầu Spring Boot cấu hình **MockMvc** từ web application context đó. MockMvc gửi request mô phỏng qua Spring MVC và có thể chạy các servlet filter đã đăng ký trong context. Thuộc tính **addFilters** mặc định là **true**, vì vậy các filter như Spring Security thường tham gia vào request.

Hai annotation giải quyết hai phần khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| **@SpringBootTest** | Tạo application context với cấu hình và bean của ứng dụng |
| **@AutoConfigureMockMvc** | Tạo MockMvc để gửi request mô phỏng vào ứng dụng |
| **spring-security-test** | Cung cấp post-processor và annotation để tạo authentication, CSRF, JWT hoặc OAuth2 giả lập |
| **MockMvc** | Gửi request và kiểm tra status, header, cookie, body hoặc kết quả chuyển tiếp |

Đường đi cơ bản của request:

~~~mermaid
flowchart TD
    A["@SpringBootTest"] --> B["ApplicationContext"]
    C["@AutoConfigureMockMvc"] --> D["MockMvc"]
    B --> D
    D --> E["Servlet filters"]
    E --> F["FilterChainProxy"]
    F --> G["SecurityFilterChain phù hợp"]
    G --> H["DispatcherServlet"]
    H --> I["Controller và service"]
    I --> J["HTTP response mô phỏng"]
    G --> K["401 / 403 hoặc redirect"]
~~~

Nếu security filter từ chối request, controller có thể không được gọi. Vì vậy, kiểm thử chỉ gọi trực tiếp method của controller không thể thay thế kiểm thử request qua MockMvc khi mục tiêu là xác minh HTTP security.

Một application context đầy đủ cũng không có nghĩa mọi hệ thống bên ngoài đều tự động sẵn sàng. Kết nối database, message broker, dịch vụ thanh toán hoặc API bên thứ ba vẫn cần cấu hình test phù hợp.

## 2. Chuẩn bị dependency

Ứng dụng Servlet thường có các dependency runtime cho web và security. Phần test cần Spring Boot Test và Spring Security Test.

Ví dụ Maven:

~~~xml
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
~~~

Khi dùng Spring Boot dependency management, không cần tự chỉ định version cho các dependency đã được BOM quản lý. Dependency **spring-security-test** phải tương thích với phiên bản Spring Security trong ứng dụng.

Nếu dự án đã có starter web và security, chỉ cần bổ sung dependency test còn thiếu. Không thêm đồng thời các phiên bản Spring Framework hoặc Spring Security khác với bộ phiên bản mà Spring Boot quản lý.

## 3. Chuẩn bị security policy trong ứng dụng

Giả sử ứng dụng có ba quy tắc:

- GET **/api/public** cho phép truy cập ẩn danh.
- GET **/api/admin** yêu cầu role ADMIN.
- POST **/api/articles** yêu cầu authority ARTICLE_WRITE và CSRF token hợp lệ.

Cấu hình Servlet:

~~~java
@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/articles")
                    .hasAuthority("ARTICLE_WRITE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình trên giữ CSRF protection mặc định của Spring Security. HTTP Basic được bật để ví dụ có entry point trả 401 khi request ẩn danh truy cập tài nguyên cần đăng nhập.

Controller có thể được triển khai như sau:

~~~java
@RestController
@RequestMapping("/api")
public class ArticleController {

    private final ArticleService articleService;

    public ArticleController(ArticleService articleService) {
        this.articleService = articleService;
    }

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/admin")
    public String adminInfo() {
        return "admin";
    }

    @PostMapping("/articles")
    public ResponseEntity<Void> createArticle() {
        articleService.create();
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Service là bean ứng dụng bình thường:

~~~java
@Service
public class ArticleService {

    public void create() {
        // Thực hiện nghiệp vụ tạo bài viết.
    }
}
~~~

Trong dự án thực tế, service có thể gọi repository hoặc các hệ thống khác. Khi dùng **@SpringBootTest**, các bean đó cũng được khởi tạo theo cấu hình đang hoạt động. Bạn cần quyết định dependency nào dùng implementation thật, dependency nào cần thay bằng bean test hoặc mock.

## 4. Viết kiểm thử tích hợp bằng MockMvc

Đặt test trong package có thể tìm thấy lớp cấu hình Spring Boot chính. Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class ArticleSecurityIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCanReadPublicEndpoint() throws Exception {
        mockMvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void authenticatedUserWithoutAdminRoleIsForbidden()
            throws Exception {
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
    @WithMockUser(authorities = "ARTICLE_WRITE")
    void writerCanCreateArticleWithCsrf() throws Exception {
        mockMvc.perform(post("/api/articles").with(csrf()))
            .andExpect(status().isCreated());
    }

    @Test
    @WithMockUser(authorities = "ARTICLE_WRITE")
    void writerCannotCreateArticleWithoutCsrf() throws Exception {
        mockMvc.perform(post("/api/articles"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các static import thường dùng:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Ngoài ra, test class cần các import tương ứng cho **SpringBootTest**, **AutoConfigureMockMvc**, **Autowired**, **Test**, **WithMockUser** và **MockMvc**. Nếu test dùng **csrf()**, hãy import đúng request post-processor như ví dụ.

Kết quả dự kiến:

| Request | Danh tính trong test | Kết quả | Điều được xác minh |
| --- | --- | --- | --- |
| GET /api/public | Ẩn danh | 200 | Rule permitAll |
| GET /api/admin | Ẩn danh | 401 | Authentication entry point của HTTP Basic |
| GET /api/admin | VIEWER | 403 | Đã xác thực nhưng thiếu ROLE_ADMIN |
| GET /api/admin | ADMIN | 200 | Role ADMIN được chấp nhận |
| POST /api/articles | ARTICLE_WRITE và CSRF hợp lệ | 201 | Authority và CSRF đều hợp lệ |
| POST /api/articles | ARTICLE_WRITE, không có CSRF | 403 | CSRF filter từ chối request |

Các status trong bảng phụ thuộc cấu hình ứng dụng. Với form login, request ẩn danh có thể nhận 302 redirect tới trang đăng nhập thay vì 401. Một access denied handler tùy chỉnh cũng có thể thay đổi response. Hãy assert theo HTTP contract mà ứng dụng thực sự công bố.

### Vì sao cần giữ filter?

**@AutoConfigureMockMvc(addFilters = true)** bảo đảm các filter trong application context được thêm vào MockMvc. Đây là thiết lập cần thiết khi muốn kiểm tra Spring Security qua HTTP request.

Nếu đặt **addFilters = false**, MockMvc bỏ qua các filter đã đăng ký. Request có thể tới controller mà không trải qua security filter chain. Một test như vậy có thể hữu ích khi chỉ muốn kiểm tra mapping hoặc response của controller, nhưng không thể chứng minh authorization, authentication hay CSRF đang hoạt động.

## 5. Phân biệt kiểm thử authentication và authorization

Một test dùng **@WithMockUser** thường kiểm tra authorization. Spring Security Test tạo một Authentication giả lập với username, role hoặc authority được khai báo rồi đặt nó vào SecurityContext trong thời gian chạy test.

Ví dụ:

~~~java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void adminCanAccessProtectedEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin"))
        .andExpect(status().isOk());
}
~~~

Cách này không gọi UserDetailsService để tìm người dùng, không xác minh mật khẩu và không chạy quy trình đăng nhập thực tế. Nó trả lời câu hỏi: với một principal đã xác thực và có quyền ADMIN, policy có cho phép request hay không?

Có ba cách thường gặp:

| Cách tạo danh tính | Cơ chế | Phù hợp với |
| --- | --- | --- |
| **@WithMockUser** | Tạo Authentication giả lập với username, role hoặc authority | Kiểm tra authorization |
| **@WithUserDetails** | Tải UserDetails từ UserDetailsService rồi tạo SecurityContext | Kiểm tra policy với user có trong kho người dùng |
| **httpBasic()** hoặc gửi form login | Gửi thông tin xác thực qua filter đăng nhập thực tế | Kiểm tra AuthenticationManager, provider và password encoder |

Ví dụ dùng HTTP Basic để chạy qua authentication filter:

~~~java
@Test
void validCredentialsCanAccessAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin")
            .with(httpBasic("admin-test", "test-password")))
        .andExpect(status().isOk());
}
~~~

Test này chỉ thành công khi người dùng **admin-test** tồn tại trong nguồn người dùng mà cấu hình test đang sử dụng, mật khẩu khớp và người dùng có role ADMIN. Hãy khai báo dữ liệu đó trong test profile hoặc test fixture. Không đưa credential của môi trường thật vào mã nguồn kiểm thử.

Nếu muốn tải user qua UserDetailsService, có thể dùng:

~~~java
@Test
@WithUserDetails("admin-test")
void configuredAdminUserCanAccessEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin"))
        .andExpect(status().isOk());
}
~~~

**@WithUserDetails** xác minh rằng user có thể được tải từ UserDetailsService, nhưng vẫn không gửi mật khẩu qua authentication filter. Khi cần xác minh password encoder hoặc AuthenticationProvider, hãy gửi credential qua cơ chế đăng nhập thực tế.

## 6. Kiểm thử JWT, OAuth2 và OIDC trong application context

Với resource server JWT, Spring Security Test cung cấp request post-processor **jwt()** để tạo JWT authentication cho request:

~~~java
@Test
void reportReaderCanAccessReportEndpoint() throws Exception {
    mockMvc.perform(get("/api/reports")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
        .andExpect(status().isOk());
}
~~~

Ví dụ cần static import **jwt()** và import **SimpleGrantedAuthority**. Route minh họa giả định yêu cầu authority **SCOPE_reports.read**.

Post-processor **jwt()** tạo authentication trong test. Nó không gửi bearer token qua decoder để kiểm tra chữ ký, issuer, audience hoặc thời hạn. Vì vậy, test này hữu ích để kiểm tra authorization theo claim hoặc authority đã được thiết lập, nhưng không chứng minh JWT decoder xác minh token đúng.

Muốn kiểm tra decoder, hãy cấu hình decoder bằng khóa và issuer dành riêng cho test, tạo token kiểm thử hợp lệ, gửi header Authorization dạng Bearer rồi để filter chain xử lý token như request thực tế.

Với OAuth2 Login và OIDC, Spring Security Test có các post-processor **oauth2Login()** và **oidcLogin()** để tạo principal đăng nhập giả lập. Chúng phù hợp khi kiểm tra authorization sau khi người dùng đã đăng nhập. Chúng không thay thế kiểm thử redirect, authorization code exchange, giao tiếp token endpoint hoặc xác minh chữ ký ID Token với nhà cung cấp danh tính thật.

Khi cấu hình ứng dụng tham chiếu các bean OAuth2 client hoặc JWT decoder, application context vẫn cần các bean đó để khởi tạo. Có thể dùng cấu hình test hoặc mock bean phù hợp để cung cấp dependency; lựa chọn phụ thuộc vào việc test đang kiểm tra policy hay kiểm tra tích hợp authentication thực tế.

## 7. Điều khiển application context cho môi trường test

**@SpringBootTest** tải cấu hình ứng dụng theo profile và property đang hoạt động. Một số cách khai báo thường dùng:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "app.audit.enabled=false",
        "app.remote-service.base-url=http://localhost"
    }
)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ArticleSecurityIntegrationTest {
}
~~~

Chỉ khai báo property mà ứng dụng thực sự sử dụng. **@ActiveProfiles("test")** yêu cầu dự án có cấu hình tương ứng, chẳng hạn application-test.yml hoặc các bean được điều kiện hóa theo profile.

Nếu test cần cấu hình lớp ứng dụng rõ ràng, dùng thuộc tính **classes**:

~~~java
@SpringBootTest(classes = Application.class)
@AutoConfigureMockMvc
class ApplicationSecurityTest {
}
~~~

Cách này hữu ích khi package của test không nằm dưới package chứa lớp cấu hình chính, hoặc khi dự án có nhiều lớp cấu hình ứng dụng khiến Spring không thể xác định duy nhất cấu hình cần dùng.

### Database và dịch vụ bên ngoài

Application context đầy đủ có thể khởi tạo repository, connection pool, client HTTP, message listener và các bean tích hợp khác. Nếu các bean đó cần hạ tầng bên ngoài, hãy chuẩn bị môi trường test tương ứng:

- Dùng database riêng cho test, database nhúng hoặc Testcontainers.
- Cấp property kết nối bằng test profile hoặc **@DynamicPropertySource**.
- Dùng mock bean cho dịch vụ bên ngoài khi test không nhắm tới giao tiếp với dịch vụ đó.
- Tắt scheduler hoặc background consumer trong test nếu chúng không thuộc mục tiêu của bài kiểm tra.
- Dùng dữ liệu kiểm thử có thể tái tạo để các test không phụ thuộc thứ tự chạy.

Với Spring Framework 6.2+ có thể dùng **@MockitoBean** để thay một bean trong application context bằng Mockito mock:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ArticleSecurityIntegrationTest {

    @MockitoBean
    ExternalCatalogClient externalCatalogClient;

    @Autowired
    MockMvc mockMvc;
}
~~~

**@MockitoBean** nằm trong package **org.springframework.test.context.bean.override.mockito**. Với các phiên bản Spring Boot/Spring Framework cũ hơn, dự án có thể đang dùng **@MockBean** của Spring Boot. Hãy chọn annotation tương thích với phiên bản đang sử dụng.

Thay một client bên ngoài bằng mock vẫn cho phép test chạy với application context rộng, nhưng hành vi của client thật không được kiểm chứng. Nếu mock một service có method security, lời gọi sẽ đi vào mock thay vì implementation được Spring proxy; khi đó test không xác minh được interceptor bảo vệ method của bean thật.

### Context caching và thời gian chạy

Spring Test có thể tái sử dụng application context giữa các test class có cấu hình tương thích. Điều này giúp giảm thời gian khởi động, nhưng các thay đổi bean hoặc cấu hình giữa các class có thể làm context cần được tạo lại.

Tránh thêm **@DirtiesContext** vào mọi test theo thói quen. Annotation này yêu cầu loại context khỏi cache sau test và có thể làm suite chậm hơn. Chỉ dùng khi test thực sự làm thay đổi trạng thái context khiến không thể tái sử dụng an toàn.

## 8. Kiểm tra SecurityFilterChain và servlet filter

Một ứng dụng có thể khai báo nhiều **SecurityFilterChain**, ví dụ một chain cho API và một chain cho trang quản trị. Spring Security dùng matcher và thứ tự chain để chọn cấu hình phù hợp với từng request.

Ví dụ:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasAuthority("API_ACCESS"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Trong ví dụ này, request thuộc **/api/** được chain đầu tiên xử lý. Các request khác được xét bởi chain thứ hai. Các chain không tự động gộp tất cả rule của chúng thành một policy chung.

Khi kiểm thử nhiều chain, hãy gửi request vào URL thuộc từng matcher và xác minh riêng hành vi của chúng. Nếu một request nhận response khác dự kiến, kiểm tra **securityMatcher**, **requestMatchers**, **@Order** và filter chain thực sự được chọn.

MockMvc cũng chạy các servlet filter khác được đăng ký trong application context khi **addFilters** bật. Với custom filter:

- Xác minh filter được tạo và đăng ký đúng một lần.
- Kiểm tra thứ tự filter nếu filter phụ thuộc SecurityContext hoặc request wrapper.
- Bảo đảm filter không gọi dịch vụ bên ngoài ngoài ý muốn trong test.
- Kiểm tra request đi qua filter bằng assertion về response hoặc tác động có thể quan sát được.

Không nên tắt toàn bộ filter chỉ để làm test qua nhanh nếu mục tiêu của test là bảo mật HTTP. Nếu cần kiểm tra riêng controller, có thể dùng một test hẹp hơn và ghi rõ test đó không bao phủ security filter chain.

## 9. Method security trong kiểm thử tích hợp

Method security bảo vệ lời gọi method của bean Spring, ví dụ bằng **@PreAuthorize**. Cấu hình ứng dụng cần bật method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Service được bảo vệ:

~~~java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        return "report";
    }
}
~~~

Với **@SpringBootTest**, cấu hình method security của ứng dụng được nạp cùng application context nếu profile và điều kiện cấu hình cho phép. Khi request từ MockMvc gọi controller rồi tới service thật, Spring proxy có thể áp dụng method authorization.

Ví dụ kiểm tra quyền qua endpoint:

~~~java
@Test
@WithMockUser(authorities = "REPORT_READ")
void userWithReportAuthorityCanReadReport() throws Exception {
    mockMvc.perform(get("/api/reports"))
        .andExpect(status().isOk());
}

@Test
@WithMockUser(authorities = "PROFILE_READ")
void userWithoutReportAuthorityCannotReadReport() throws Exception {
    mockMvc.perform(get("/api/reports"))
        .andExpect(status().isForbidden());
}
~~~

Các test trên giả định controller gọi **ReportService** thật và endpoint cho phép request đi qua URL authorization. Nếu service bị thay bằng **@MockitoBean**, method body cùng method-security interceptor trên bean thật không được thực thi. Hãy giữ bean thật khi mục tiêu là xác minh **@PreAuthorize** trên service.

Cũng cần phân biệt URL authorization và method authorization. Một request có thể vượt qua rule trong SecurityFilterChain nhưng vẫn bị từ chối ở service do thiếu authority. Ngược lại, một request bị filter từ chối sẽ không đi tới method được bảo vệ.

## 10. MockMvc kiểm chứng điều gì và không kiểm chứng điều gì?

MockMvc mô phỏng servlet request/response trong test process. Nó chạy MVC dispatch và các filter đã cấu hình, do đó phù hợp để kiểm tra:

- URL matcher, role, authority và authentication entry point.
- CSRF, custom filter và servlet security configuration.
- Controller mapping, binding, validation và response.
- Sự phối hợp giữa controller, service và các bean trong application context.

MockMvc không mở kết nối TCP và không kiểm tra embedded server nhận request qua cổng mạng. Nó cũng không kiểm chứng TLS handshake, reverse proxy, load balancer hoặc cấu hình mạng bên ngoài ứng dụng.

Nếu cần kiểm tra ứng dụng qua HTTP thật, có thể khởi động server bằng **@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)** rồi dùng **TestRestTemplate** hoặc **WebTestClient** để gửi request tới cổng được cấp động. Kiểu test này bao phủ thêm embedded server và đường truyền HTTP trong môi trường test.

| Nhu cầu | Cách kiểm thử phù hợp |
| --- | --- |
| Một controller, ít bean, phản hồi nhanh | **@WebMvcTest** |
| Security config và nhiều bean của ứng dụng phối hợp | **@SpringBootTest** + **@AutoConfigureMockMvc** |
| Embedded server, cổng mạng và HTTP thực tế | **@SpringBootTest(RANDOM_PORT)** với HTTP client |
| Ứng dụng WebFlux | **WebTestClient** cùng cấu hình reactive security |

**@AutoConfigureMockMvc** dành cho ứng dụng Servlet MVC. Với ứng dụng Reactive WebFlux, dùng **WebTestClient**, **SecurityWebFilterChain** và các cấu hình kiểm thử reactive tương ứng. Không dùng MockMvc để kết luận reactive security filter chain hoạt động đúng.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Application context không khởi tạo | Thiếu property, database không sẵn sàng hoặc bean phụ thuộc dịch vụ ngoài | Đọc nguyên nhân gốc trong lỗi tạo bean; cấu hình test profile và hạ tầng |
| Request public trả 401 | Request khớp chain khác hoặc rule permitAll chưa được nạp | Kiểm tra matcher, thứ tự SecurityFilterChain và cấu hình active |
| Request ẩn danh nhận 302 thay vì 401 | Ứng dụng dùng form login hoặc entry point redirect | Assert theo authentication entry point của ứng dụng |
| User có role vẫn nhận 403 | Sai role prefix, authority hoặc chain được chọn | So sánh hasRole với hasAuthority và quyền trong Authentication |
| POST nhận 403 dù đã có authority | Thiếu hoặc sai CSRF token | Thêm csrf() cho ca hợp lệ; giữ ca thiếu token để kiểm tra từ chối |
| Request đáng lẽ bị chặn nhưng lại thành công | Filter bị tắt, matcher không khớp hoặc request dùng chain khác | Xác minh addFilters, securityMatcher, requestMatchers và @Order |
| @WithMockUser không kiểm tra được đăng nhập | Annotation tạo Authentication giả lập | Gửi credential qua filter đăng nhập hoặc dùng test phù hợp cho provider |
| JWT test qua nhưng token thật không hợp lệ | jwt() bỏ qua bước decode token | Gửi bearer token kiểm thử qua decoder thật |
| Method security không từ chối | Chưa bật @EnableMethodSecurity hoặc service bị mock/tự tạo | Gọi bean thật do Spring quản lý và kiểm tra cấu hình proxy |
| Test chạy riêng thì qua, chạy cả suite thì lỗi | Dữ liệu chia sẻ hoặc trạng thái test không được cô lập | Làm test độc lập, khởi tạo và dọn dữ liệu có kiểm soát |

### Checklist trước khi tin vào kết quả

1. Test đang tải đúng lớp cấu hình Spring Boot của ứng dụng?
2. Profile và property trong test có giống môi trường mà bạn muốn xác minh?
3. **@AutoConfigureMockMvc** đang bật filter?
4. Request có đi vào đúng **SecurityFilterChain**?
5. Test đang giả lập Authentication hay thực sự chạy authentication mechanism?
6. Các ca kiểm thử có cả truy cập được phép và bị từ chối?
7. POST, PUT, PATCH hoặc DELETE có kiểm tra CSRF theo policy?
8. Service cần method security có phải bean thật được Spring proxy?
9. Database và dịch vụ bên ngoài có được cô lập bằng cấu hình test?

## 12. Bài tập thực hành

**Bài 1 — Kiểm tra toàn bộ request pipeline.** Dùng **@SpringBootTest** và **@AutoConfigureMockMvc** để kiểm tra một endpoint public và một endpoint yêu cầu đăng nhập. Quan sát response khi request ẩn danh và khi có user đã xác thực.

**Bài 2 — Role và authority.** Tạo endpoint yêu cầu ADMIN và endpoint yêu cầu authority ARTICLE_WRITE. Viết ca đủ quyền, thiếu quyền và ẩn danh. Giải thích khác biệt giữa **hasRole** và **hasAuthority**.

**Bài 3 — Authentication thực tế.** Tạo user dành riêng cho test profile. Dùng HTTP Basic hoặc form login để gửi credential qua filter đăng nhập. Kiểm tra cả credential hợp lệ và không hợp lệ; so sánh với test dùng **@WithMockUser**.

**Bài 4 — CSRF.** Viết request POST có authority phù hợp nhưng không có CSRF token, sau đó thêm token bằng **csrf()**. Giải thích vì sao có quyền nghiệp vụ vẫn chưa đủ để request thay đổi trạng thái được chấp nhận.

**Bài 5 — Nhiều SecurityFilterChain.** Tạo chain riêng cho **/api/** và chain cho các URL còn lại. Viết test cho cả hai nhóm URL để xác minh matcher và thứ tự chain.

**Bài 6 — Method security.** Bật **@EnableMethodSecurity**, đặt **@PreAuthorize** trên service và gọi service qua controller. So sánh kết quả khi dùng bean thật với khi thay service bằng mock.

**Bài 7 — MockMvc và HTTP server.** Chạy cùng một kịch bản authorization bằng MockMvc và bằng **RANDOM_PORT** với HTTP client. Ghi rõ lớp hạ tầng mà mỗi cách kiểm thử bao phủ.

## 13. Ghi nhớ

**@SpringBootTest** tải application context của ứng dụng; **@AutoConfigureMockMvc** tạo MockMvc để gửi request mô phỏng qua Spring MVC. Khi giữ **addFilters = true**, request đi qua servlet filter và Spring Security theo cấu hình đang hoạt động trong test context.

Dùng **@WithMockUser** để kiểm tra authorization với danh tính giả lập. Dùng credential qua authentication filter khi cần xác minh đăng nhập, provider và password encoder. Dùng **csrf()** cho request thay đổi trạng thái khi CSRF được bật. Với JWT hoặc OAuth2, hãy phân biệt post-processor giả lập authentication với kiểm thử decoder hoặc giao thức thực tế.

Chọn MockMvc khi cần kiểm tra tích hợp trong ứng dụng Servlet mà không cần mở cổng HTTP. Khi cần xác minh embedded server hoặc đường truyền mạng, khởi động server thật và dùng HTTP client.
