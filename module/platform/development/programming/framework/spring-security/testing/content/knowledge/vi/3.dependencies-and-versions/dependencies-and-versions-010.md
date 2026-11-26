# Nhận diện cấu hình hoặc annotation cũ trước khi sao chép ví dụ

Một đoạn code Spring Security có thể từng đúng ở thời điểm được viết nhưng không còn biên dịch hoặc không còn là cách cấu hình nên dùng trong dự án hiện tại. Khi đọc bài hướng dẫn, câu hỏi đầu tiên không phải “đoạn code này có vẻ quen không?” mà là **nó được viết cho Spring Boot, Spring Framework và Spring Security phiên bản nào, dùng JUnit thế hệ nào và chạy trên Servlet hay Reactive?**

Bài này giúp nhận diện các dấu hiệu cũ thường gặp trong ví dụ kiểm thử xác thực và phân quyền: `WebSecurityConfigurerAdapter`, `antMatchers()`, `authorizeRequests()`, `@EnableGlobalMethodSecurity`, JUnit 4 `@RunWith`, annotation mock của Spring Boot, cách cấu hình Security DSL cũ và các giả định sai về status HTTP. Sau khi nhận diện, người học biết chuyển ví dụ sang cấu hình hiện hành và kiểm tra rằng test vẫn đi qua security chain thật.

Nội dung thuộc chương **Phụ thuộc và phiên bản** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng **Servlet** và **Reactive**, với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và các ca được phép hoặc bị từ chối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhận diện dấu hiệu một ví dụ Spring Security được viết cho thế hệ API cũ.
2. Phân biệt API đã bị loại bỏ, API deprecated và API vẫn hợp lệ nhưng không còn là lựa chọn ưu tiên.
3. Chọn cấu hình thay thế theo phiên bản Spring Security và loại ứng dụng Servlet/Reactive.
4. Chuyển các ví dụ JUnit 4 sang JUnit Jupiter khi dự án đã dùng JUnit 5.
5. Cập nhật test khi chuyển từ `@MockBean`/`@SpyBean` sang API mới của Spring Framework.
6. Phát hiện các giả định sai về `401`, `403`, `302`, CSRF, role/authority và JWT mock.
7. Đánh giá một snippet cũ trước khi sao chép vào dự án.

## 2. Ba trạng thái cần phân biệt khi gặp API cũ

Không phải API cũ nào cũng có cùng mức độ rủi ro. Trước khi thay đổi, xác định nó thuộc trạng thái nào:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| **Removed** | API đã bị loại khỏi phiên bản đang dùng; code không thể biên dịch với dependency hiện tại | Thay bằng API được hỗ trợ trong dòng phiên bản hiện tại |
| **Deprecated** | API vẫn có thể biên dịch nhưng nhà phát hành đã khuyến nghị chuyển đổi; có thể bị loại ở major kế tiếp | Lập kế hoạch chuyển đổi và kiểm tra migration guide |
| **Discouraged / legacy style** | API còn hợp lệ nhưng có cách viết mới rõ ràng, an toàn hoặc dễ mở rộng hơn | Cân nhắc cập nhật theo convention hiện tại; không thay đổi máy móc nếu chưa hiểu semantics |

Ví dụ:

- `WebSecurityConfigurerAdapter` đã bị loại khỏi Spring Security 6.0.
- `@EnableGlobalMethodSecurity` là API cũ; dùng `@EnableMethodSecurity` cho cấu hình mới.
- `@MockBean` vẫn tồn tại trong Boot 3.4/3.5 nhưng deprecated; Boot 4 đã loại bỏ.
- `@WithMockUser` vẫn là API hợp lệ của Spring Security Test, không phải annotation lỗi thời chỉ vì xuất hiện trong bài viết cũ.
- Cấu hình lambda DSL là cách viết được khuyến nghị; không phải mọi method chain cũ đều đã bị xóa cùng lúc.

**Không kết luận API lỗi thời chỉ dựa vào năm xuất bản của bài viết.** Hãy tra package, artifact, Javadoc và phiên bản thực tế trong classpath.

## 3. Xác định thế hệ Spring trước khi đánh giá snippet

| Nền tảng | Spring Framework thường đi kèm | Spring Security thường đi kèm | Điều cần chú ý |
|---|---|---|---|
| Spring Boot 2.x | Framework 5.x | Security 5.x | Có nhiều ví dụ dùng adapter và matcher cũ; JUnit 4 có thể còn phổ biến |
| Spring Boot 3.x | Framework 6.x | Security 6.x | Java 17+, cấu hình bean-based, Jakarta namespace, JUnit Jupiter thường được dùng |
| Spring Boot 4.x | Framework 7.x | Security 7.x | Test starter tách theo module, package test Boot có thể thay đổi; API Security 7 cần tra đúng docs |

Đây là bảng nhận diện **dòng major**, không thay thế dependency tree. Một dự án có thể override version hoặc dùng Spring Framework/Security không thông qua Boot. Trước khi chuyển code, kiểm tra:

**Maven**

```bash
./mvnw dependency:tree -Dscope=test
./mvnw help:effective-pom
```

**Gradle**

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
```

Tập trung vào `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-test`, `spring-test` và các module OAuth2 nếu ứng dụng dùng JWT/OIDC. Chọn tài liệu đúng dòng phiên bản trước khi thay API.

## 4. Nhận diện cấu hình Servlet cũ: WebSecurityConfigurerAdapter

Một dấu hiệu rất rõ trong bài viết cũ là lớp kế thừa:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .formLogin();
    }
}
```

Cách cấu hình này từng được dùng rộng rãi, nhưng `WebSecurityConfigurerAdapter` đã deprecated từ Spring Security 5.7 và bị loại khỏi Spring Security 6.0. Khi dự án dùng Security 6.x/7.x, không thể chỉ sao chép lớp trên rồi mong compiler chấp nhận.

### 4.1. Cách viết bean-based hiện hành

Dùng một bean `SecurityFilterChain` nhận `HttpSecurity`:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Cần import `Customizer`, `Bean`, `Configuration`, `HttpSecurity` và `SecurityFilterChain` tương ứng. Trong ứng dụng thực tế, có thể chia nhiều `SecurityFilterChain` bằng `@Order` và `securityMatcher(...)`; nếu có nhiều chain, thứ tự và matcher của từng chain ảnh hưởng trực tiếp đến kết quả test.

**Tại sao điều này quan trọng với test?** `MockMvc` cần dùng chính filter chain được Spring đăng ký. Nếu test slice không nạp bean `SecurityFilterChain`, một request đến controller có thể không phản ánh chính sách trong cấu hình production.

### 4.2. Chuyển test theo cấu hình mới

Test HTTP không cần phụ thuộc lớp adapter cũ. Nó cần Spring context chứa bean security chain và `MockMvc` được tích hợp:

```java
@SpringBootTest
@AutoConfigureMockMvc
class AdminAccessTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(roles = "USER")
    void userCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin/reports"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin/reports"))
           .andExpect(status().isOk());
    }
}
```

Đây là ví dụ Boot 3.x minh họa. Với Boot 4.x, dùng test starter và import annotation theo package của dòng Boot 4; `@WithMockUser` và `MockMvc` vẫn là các API cần tra theo Spring Security Test và Spring Framework tương ứng.

## 5. Nhận diện matcher cũ: antMatchers và mvcMatchers

Một ví dụ cũ thường có:

```java
http.authorizeRequests()
    .antMatchers("/api/public/**").permitAll()
    .mvcMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

Các matcher builder `antMatchers()` và `mvcMatchers()` bị loại trong Spring Security 6.0 cùng quá trình chuyển đổi DSL. Cấu hình mới dùng `authorizeHttpRequests()` và `requestMatchers()`:

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

### 5.1. Không chỉ thay tên method

Khi chuyển matcher, kiểm tra kỹ:

- **Thứ tự rule:** quy tắc cụ thể phải đứng trước quy tắc tổng quát như `anyRequest()`.
- **Loại request matcher:** `requestMatchers(String...)` lựa chọn matcher phù hợp với classpath và môi trường; nếu cần semantics đặc biệt, khai báo một `RequestMatcher` rõ ràng.
- **HTTP method:** nếu chỉ cho phép GET, truyền method hoặc dùng matcher tường minh để tránh vô tình cho phép POST/DELETE.
- **Servlet path và context path:** endpoint có thể được deploy dưới servlet path khác; kiểm tra request thực tế mà test tạo.
- **Nhiều filter chain:** `securityMatcher(...)` chọn chain trước khi authorization matcher bên trong chain được áp dụng.

Ví dụ chỉ cho phép GET ở khu vực public:

```java
.requestMatchers(HttpMethod.GET, "/api/catalog/**").permitAll()
.requestMatchers("/api/catalog/**").authenticated()
```

Với test, nên có ít nhất một request đúng method và một request method khác để xác nhận chính sách không bị nới lỏng ngoài ý muốn.

### 5.2. Viết test xác nhận matcher

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@Test
void publicGetIsAllowed() throws Exception {
    mvc.perform(get("/api/catalog/items"))
       .andExpect(status().isOk());
}

@Test
void catalogWriteStillRequiresAuthentication() throws Exception {
    mvc.perform(post("/api/catalog/items").with(csrf()))
       .andExpect(status().isUnauthorized());
}
```

Status `401` ở ví dụ thứ hai giả định API dùng authentication entry point trả Unauthorized. Request gửi kèm `csrf()` để không bị CSRF filter từ chối trước khi authorization matcher được kiểm tra. Nếu ứng dụng dùng form login, anonymous request có thể bị redirect `302`; test phải khớp cấu hình thực tế. Hãy viết ca POST thiếu/sai token riêng để kiểm tra CSRF.

## 6. Nhận diện authorizeRequests và chuyển sang authorizeHttpRequests

`authorizeRequests()` là DSL cũ của Servlet authorization. Với cấu hình mới, dùng:

```java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/health").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

`authorizeHttpRequests` sử dụng cơ chế authorization mới của Spring Security và làm rõ việc xử lý request authorization. Khi đọc bài cũ, đừng nhầm lẫn rằng `authorizeRequests` và `authorizeHttpRequests` chỉ là hai tên tương đương không có khác biệt; hãy đọc phần migration/authorization của đúng phiên bản nếu ứng dụng có custom voter, expression handler hoặc matcher phức tạp.

**Reactive là DSL riêng.** Trong WebFlux, cấu hình đi qua `ServerHttpSecurity` và `SecurityWebFilterChain`; authorization thường dùng `authorizeExchange(...)`:

```java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Không sao chép `HttpSecurity`/`SecurityFilterChain` của Servlet sang WebFlux, và không thay `authorizeExchange` bằng `authorizeHttpRequests` theo kiểu tìm-thay toàn văn. Hai stack có abstraction và API riêng.

## 7. Nhận diện cấu hình method security cũ

Ví dụ cũ:

```java
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
class MethodSecurityConfig {
}
```

`@EnableGlobalMethodSecurity` là cấu hình cũ; với ứng dụng mới dùng:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Mặc định `@EnableMethodSecurity` bật pre/post annotations như `@PreAuthorize` và `@PostAuthorize`. Nếu ứng dụng dùng `@Secured` hoặc JSR-250 `@RolesAllowed`, bật rõ các tùy chọn tương ứng, ví dụ `securedEnabled = true` hoặc `jsr250Enabled = true`, thay vì giả định mọi loại method annotation đều tự bật.

### 7.1. Test method security không được gọi đối tượng tự tạo

Đây là test không đáng tin nếu mục tiêu là kiểm tra `@PreAuthorize`:

```java
ReportService service = new ReportService(repository);
service.readSensitiveReport();
```

Đối tượng tạo bằng `new` không đi qua Spring AOP proxy. Test cần inject bean do Spring quản lý:

```java
@SpringJUnitConfig(MethodSecurityTest.Config.class)
class MethodSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void readerCanRead() {
        reportService.readSensitiveReport();
    }

    @Test
    @WithMockUser(authorities = "SCOPE_other")
    void wrongScopeIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> reportService.readSensitiveReport());
    }
}
```

Cấu hình test phải bật `@EnableMethodSecurity`, đăng ký `ReportService` như Spring bean và cung cấp collaborator cần thiết. Có thể mock repository bằng `@MockitoBean` nếu phiên bản hỗ trợ, nhưng giữ service đang được bảo vệ là bean thật.

## 8. Nhận diện JUnit 4 trong ví dụ kiểm thử cũ

Một ví dụ cũ thường dùng:

```java
@RunWith(SpringRunner.class)
public class SecurityTests {

    @Before
    public void setUp() { }

    @Test
    public void testAccess() { }
}
```

Đây là JUnit 4: `@RunWith`, `@Before`, `org.junit.Test`. Nếu dự án dùng JUnit Jupiter, chuyển sang:

```java
@ExtendWith(SpringExtension.class)
class SecurityTests {

    @BeforeEach
    void setUp() { }

    @Test
    void accessIsChecked() { }
}
```

Import tương ứng từ `org.junit.jupiter.api.*` và `org.junit.jupiter.api.extension.ExtendWith`. Trong test Spring Boot dùng `@SpringBootTest`, `@WebMvcTest` hoặc `@WebFluxTest`, SpringExtension thường đã được tích hợp; không cần thêm `@ExtendWith(SpringExtension.class)` chỉ để autowire hoạt động.

Không chuyển mọi test JUnit 4 một cách máy móc: nếu dự án vẫn chủ động dùng Vintage Engine để chạy test cũ, `@RunWith(SpringRunner.class)` có thể còn hợp lệ. Cần thống nhất framework chạy test trong module và tránh import nhầm hai annotation `@Test` từ hai thế hệ.

## 9. Nhận diện annotation mock đã cũ

Trong ví dụ Boot cũ, có thể gặp:

```java
@MockBean
ReportService reportService;
```

Mốc chuyển đổi:

| Nền tảng | API phù hợp |
|---|---|
| Boot 3.0–3.3 / Framework 6.0–6.1 | `@MockBean`, `@SpyBean` của Boot hoặc Mockito thủ công |
| Boot 3.4–3.5 / Framework 6.2 | Ưu tiên `@MockitoBean`, `@MockitoSpyBean`; API Boot cũ deprecated |
| Boot 4.x / Framework 7.x | Dùng annotation Framework mới; annotation Boot cũ đã bị loại |

Annotation mới nằm trong `org.springframework.test.context.bean.override.mockito`. Chúng thuộc `spring-test`, không thuộc `spring-security-test`. Nếu dùng `@MockitoBean` để mock service có `@PreAuthorize`, test có thể bỏ qua method implementation và proxy; hãy mock repository/client thay vì mock service cần kiểm chứng.

## 10. Nhận diện cách viết Security DSL cũ và lambda DSL

Một số bài hướng dẫn viết chuỗi method cũ:

```java
http
    .csrf().disable()
    .authorizeHttpRequests()
        .anyRequest().authenticated()
    .and()
    .httpBasic();
```

Trong các dòng Security mới, cách viết lambda DSL rõ ràng hơn và tránh phụ thuộc vào chuỗi `and()`:

```java
http
    .csrf(csrf -> csrf.disable())
    .authorizeHttpRequests(authorize -> authorize
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
```

Các phương thức cấu hình không tham số như `csrf()`, `headers()`, `httpBasic()` đã được đánh dấu deprecated trong quá trình chuyển sang lambda DSL ở Security 6.1; các overload lambda là lựa chọn nên dùng cho code mới. Khi nâng lên Security 7, kiểm tra migration guide vì các overload cũ có thể đã bị loại bỏ.

Không tắt CSRF chỉ để làm test POST xanh. Chỉ vô hiệu hóa khi mô hình bảo mật của ứng dụng cho phép và có lý do rõ ràng. Với ứng dụng dùng cookie/session, CSRF thường là một lớp bảo vệ quan trọng; test nên xác minh token hợp lệ và token thiếu/sai.

## 11. Nhận diện ví dụ test HTTP có giả định sai

Một đoạn test có thể dùng API còn hợp lệ nhưng expectation không đúng với ứng dụng. Trước khi sao chép, kiểm tra các giả định sau:

| Cách nói trong bài cũ | Điều cần xác minh |
|---|---|
| “Anonymous luôn trả `401`” | Form login có thể redirect `302`; entry point của API quyết định response |
| “Đã đăng nhập nhưng sai role luôn là `403`” | Thường đúng với authorization, nhưng CSRF/filter khác có thể từ chối trước |
| “Có role là POST thành công” | CSRF có thể đang bật; request cần token |
| “`@WithMockUser` kiểm tra login” | Annotation chỉ thiết lập authentication giả lập, không gọi login endpoint/password provider |
| “`jwt()` chứng minh token hợp lệ” | Helper giả lập authentication; không xác minh chữ ký/JWK/issuer/audience |
| “`MockMvc` tự động có mọi filter” | Chỉ khi setup/context tích hợp đúng filter chain |
| “`WebTestClient` luôn chạy WebFlux” | Có thể dùng với MVC hoặc server HTTP; phải xác định stack ứng dụng |
| “Test slice nạp toàn bộ Security config” | `@WebMvcTest`/`@WebFluxTest` giới hạn context; có thể cần `@Import` |
| “Mock service là đủ để test `@PreAuthorize`” | Mock thay logic thật; phải test service bean/proxy riêng |

### 11.1. Phân biệt 401, 403 và 302

- **401 Unauthorized:** request chưa có authentication hợp lệ theo entry point của ứng dụng.
- **403 Forbidden:** authentication đã được xác lập nhưng thiếu quyền, hoặc một filter khác (ví dụ CSRF) từ chối request.
- **302 Found:** ứng dụng có thể chuyển anonymous user sang trang login trong form-login flow.

Khi viết test, hãy ghi rõ cấu hình authentication entry point. Nếu muốn API trả 401, cấu hình API theo Basic/Bearer hoặc entry point phù hợp; không thay assertion từ 302 sang 401 mà không đổi cấu hình.

### 11.2. Role và authority không giống chuỗi

`@WithMockUser(roles = "ADMIN")` tạo authority `ROLE_ADMIN`. Nó phù hợp với `hasRole("ADMIN")`. Nếu rule dùng `hasAuthority("ADMIN")`, cần:

```java
@WithMockUser(authorities = "ADMIN")
```

Với OAuth2 scope, authority thường có dạng `SCOPE_reports.read`. Test phải cung cấp đúng authority mà converter và authorization rule đang sử dụng.

## 12. Nhận diện nhầm Servlet và Reactive

| Thành phần | Servlet / MVC | Reactive / WebFlux |
|---|---|---|
| Cấu hình chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Builder | `HttpSecurity` | `ServerHttpSecurity` |
| Request client test | `MockMvc` | `WebTestClient` |
| Authorization DSL | `authorizeHttpRequests` | `authorizeExchange` |
| Request matcher | `requestMatchers` | `pathMatchers` |
| Security context | Thường gắn với `SecurityContextHolder` | Truyền qua Reactor Context |
| Mock user mỗi request | `.with(user("lan"))` | `.mutateWith(mockUser("lan"))` |
| Mock JWT | `.with(jwt())` | `.mutateWith(mockJwt())` |

Không đổi tên API theo tìm-thay. Nếu bài cũ viết Servlet mà dự án dùng WebFlux, phải chuyển cả **security chain**, **builder**, **matcher**, **test client** và **security context model**.

Ví dụ Reactive hiện hành:

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .build();
}
```

Test Reactive:

```java
client.mutateWith(mockUser("lan").roles("USER"))
      .get().uri("/admin/reports")
      .exchange()
      .expectStatus().isForbidden();
```

Đảm bảo `WebTestClient` đã được gắn với Reactive Security, chẳng hạn dùng `apply(springSecurity())` khi tự dựng client từ context.

## 13. Nhận diện package và namespace đã thay đổi

Khi chuyển Spring Boot 2.x lên 3.x, Spring Framework 6 và Jakarta EE 9 chuyển namespace từ `javax.*` sang `jakarta.*` đối với Servlet API và nhiều Jakarta API liên quan.

Ví dụ cũ:

```java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
```

Với ứng dụng Servlet dùng thế hệ Jakarta hiện tại:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
```

Không thay mọi package `javax.*` một cách tự động: một số package Java SE như `javax.crypto`, `javax.net` vẫn thuộc JDK. Chỉ chuyển những API đã chuyển sang Jakarta namespace, và kiểm tra phiên bản Servlet container cùng dependency tương ứng.

Tương tự, package của annotation test Boot có thể thay đổi khi Boot 4 tách test starter theo module. Ví dụ Boot 3 dùng package `org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest`; Boot 4 dùng package theo module `org.springframework.boot.webflux.test.autoconfigure.WebFluxTest`. Kiểm tra Javadoc đúng version trước khi thay import.

## 14. Quy trình đánh giá một snippet cũ trước khi sao chép

Dùng checklist này để đánh giá code tìm được trong blog, Stack Overflow, repository cũ hoặc tài liệu nội bộ:

1. **Ghi nguồn và version:** snippet thuộc Boot/Security/Framework/JUnit phiên bản nào? Có ghi version không?
2. **Xác định web stack:** Servlet/MVC hay WebFlux/Reactive? Tìm `SecurityFilterChain` hay `SecurityWebFilterChain`.
3. **Rà API removed:** có `WebSecurityConfigurerAdapter`, `antMatchers`, `mvcMatchers` hoặc package `javax.servlet` trong project Jakarta không?
4. **Rà API deprecated:** có `@EnableGlobalMethodSecurity`, `@MockBean`, `@SpyBean` hoặc no-arg DSL method không?
5. **Kiểm tra JUnit:** `org.junit.Test`/JUnit 4 hay `org.junit.jupiter.api.Test`/Jupiter? Build đang bật engine nào?
6. **Kiểm tra dependency:** `spring-security-test`, `spring-test`, JUnit và test starter có đúng dòng tương thích không?
7. **Kiểm tra security chain:** MockMvc/WebTestClient có thực sự đi qua filter chain đang cần thử?
8. **Kiểm tra policy:** rule matcher có đúng path/method/order? role/authority có đúng tiền tố?
9. **Kiểm tra HTTP expectation:** anonymous là 401 hay 302? CSRF có làm POST bị 403 trước authorization không?
10. **Kiểm tra giới hạn mock:** `@WithMockUser`, `jwt()`, `mockJwt()` đang giả lập trạng thái nào và bỏ qua bước xác thực nào?

Nếu không xác định được version của bài viết, hãy dùng nó như **ý tưởng**, rồi dựng lại ví dụ theo Reference/Javadoc chính thức của dependency hiện có.

## 15. Bảng chuyển đổi nhanh

| Ví dụ cũ | Cách tiếp cận hiện hành | Lưu ý |
|---|---|---|
| `extends WebSecurityConfigurerAdapter` | Bean `SecurityFilterChain` | Servlet; cấu hình nhiều chain phải xét thứ tự |
| `authorizeRequests()` | `authorizeHttpRequests(...)` | Servlet authorization |
| `antMatchers()` / `mvcMatchers()` | `requestMatchers()` hoặc matcher tường minh | Kiểm tra method, path, servlet path |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity` | Bật riêng secured/JSR-250 khi cần |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` hoặc annotation Boot | Chỉ khi dùng JUnit Jupiter |
| `@MockBean` / `@SpyBean` | `@MockitoBean` / `@MockitoSpyBean` | Framework 6.2+; Boot 3.4 deprecated API cũ, Boot 4 loại bỏ |
| `.csrf().disable()` | `.csrf(csrf -> csrf.disable())` | Chỉ tắt nếu chính sách ứng dụng yêu cầu |
| `.and()` trong DSL | Lambda DSL | Viết rõ từng configurer |
| `javax.servlet.*` | `jakarta.servlet.*` | Khi chuyển sang nền tảng Jakarta |
| `SecurityFilterChain` trong WebFlux | `SecurityWebFilterChain` | Không dùng Servlet config cho Reactive |
| `MockMvc` cho Reactive | `WebTestClient` | Dùng test client đúng stack |

Bảng là định hướng chuyển đổi, không phải script tự động. Đọc migration guide khi snippet sử dụng custom matcher, authentication provider, session management hoặc nhiều filter chain.

## 16. Bài tập thực hành

Một dự án cũ có cấu hình:

- `WebSecurityConfigurerAdapter`.
- `authorizeRequests()` và `antMatchers()`.
- `@EnableGlobalMethodSecurity(prePostEnabled = true)`.
- JUnit 4 `@RunWith(SpringRunner.class)`.
- `@MockBean` trên service có `@PreAuthorize`.
- Test anonymous mặc định mong `401`, và test POST không gửi CSRF.

Hãy thực hiện:

1. Xác định phiên bản Boot/Framework/Security/JUnit thực tế trong dependency tree.
2. Chuyển cấu hình Servlet sang `SecurityFilterChain`, `authorizeHttpRequests` và `requestMatchers`.
3. Chuyển method security sang `@EnableMethodSecurity`, bật đúng tùy chọn cho annotation mà service đang sử dụng.
4. Chuyển test sang Jupiter nếu dự án đã dùng JUnit 5; loại bỏ `@RunWith` và `@Before` cũ.
5. Chuyển mock service thành mock repository/client nếu mục tiêu là kiểm tra `@PreAuthorize` trên service thật.
6. Cấu hình entry point phù hợp hoặc sửa expectation 401/302 theo flow thực tế.
7. Thêm CSRF token cho ca POST thành công và ca thiếu token để xác nhận bảo vệ.
8. Viết một test denied và một test allowed qua MockMvc; nếu dự án WebFlux, chuyển toàn bộ sang Reactive chain và WebTestClient.

**Tiêu chí hoàn thành:** code mới biên dịch trên đúng version, test đi qua security chain, có ca được phép/bị từ chối và không còn giả định sai về login, role, CSRF hoặc JWT.

## 17. Tài liệu tham khảo chính thức

- [Spring Security — Configuration Migrations](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): cấu hình Java và bean-based Security.
- [Spring Security — Lambda DSL](https://docs.spring.io/spring-security/reference/migration-7/configuration.html): cách viết lambda DSL và các thay đổi khi lên Security 7.
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests` và request matcher.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@Secured`.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html) và [Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): các API test theo stack.
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): deprecation của `@MockBean`/`@SpyBean`.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi package và test starter.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html): TestContext, JUnit Jupiter, MockMvc và WebTestClient.

> **Nguyên tắc áp dụng:** không sao chép một snippet chỉ vì nó từng chạy được. Hãy xác định version, web stack, API status và mục tiêu kiểm thử; sau đó cập nhật cấu hình và giữ lại bằng chứng rằng request thực sự đi qua lớp bảo vệ đang cần kiểm tra.
