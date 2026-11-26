# Phát hiện cấu hình permitAll hoặc thiếu filter làm kết quả đạt sai

## 1. Khi test xanh nhưng endpoint thực tế không được bảo vệ

Xét một API báo cáo có quy tắc: chỉ người dùng đã xác thực và có authority `SCOPE_reports:read` mới được đọc tài liệu. Một test chỉ thực hiện:

```java
mvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports:read"))))
    .andExpect(status().isOk());
```

Test này có thể **PASS trong cả hai tình huống rất khác nhau**:

1. Spring Security thật sự kiểm tra JWT authentication giả lập và quyền `SCOPE_reports:read` rồi cho phép.
2. Endpoint vô tình được cấu hình `permitAll()`, hoặc `MockMvc` không chạy security filters; controller vẫn trả 200 cho mọi người.

Một kết quả **200 của người được phép không chứng minh rằng người không được phép đã bị chặn**. Nếu nhóm chỉ chạy positive tests trong CI, thay đổi nhầm một matcher, tắt filter hoặc bỏ annotation kiểm tra quyền có thể không làm bộ test đỏ. Đây là một dạng **false positive về bảo mật**: test xanh nhưng tuyên bố “endpoint đã được bảo vệ” không có bằng chứng.

Bài thuộc chương **Bộ kiểm thử và CI**, module **SPRING_SECURITY_TESTING**. Mục tiêu của module là kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` ở Servlet lẫn Reactive, sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext`, JWT/OAuth2/OIDC giả lập và các ca được phép/bị từ chối. Chủ đề này tập trung vào cách dựng **regression suite không bị đánh lừa bởi `permitAll` hoặc thiếu security filter**.

Sau khi học, bạn có thể:

- Phân biệt **allow được xác nhận** với **deny được xác nhận** ở cùng một endpoint.
- Thiết lập `MockMvc` có filter chain thực và nhận biết `addFilters = false`, `standaloneSetup` hoặc test slice thiếu cấu hình.
- Nhận biết thứ tự matcher `permitAll`, `securityMatcher` và nhiều `SecurityFilterChain` tác động ra sao.
- Thiết lập `WebTestClient` có WebFlux Security và nhận biết controller-only binding.
- Tạo ma trận `anonymous / thiếu authority / đủ authority`, kèm CSRF hoặc method security khi thích hợp.
- Thực hiện kiểm tra âm tính có chủ đích (negative control) để phát hiện regression bảo mật.
- Đưa các bài test quan trọng vào CI, xác minh test thực sự được chạy, và đọc kết quả đúng phạm vi.
- Phân biệt test có mock authentication với xác minh JWT, OAuth2, OIDC thật qua mạng.

## 2. Ba cách khiến test trả 200 dù chưa có authorization đúng

### 2.1. permitAll: filter vẫn chạy nhưng quyết định cho phép mọi người

Ví dụ cấu hình sai:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports/**").permitAll()
    .anyRequest().authenticated()
)
```

`permitAll()` là một rule hợp lệ khi dùng cho trang công khai; nó **sai** khi đặt vào endpoint báo cáo riêng tư. Với rule trên, người gọi anonymous có thể đi tới controller mà không cần authentication. Nếu positive test chỉ gửi `jwt()` hợp lệ và kỳ vọng 200, test vẫn xanh.

**Đặc điểm quan trọng:** `permitAll` không có nghĩa Spring Security filter chain bị vô hiệu hóa. Filter chain có thể vẫn chạy đầy đủ; chính **authorization decision** đang quá rộng. Vì vậy việc kiểm tra “có filter trong chain” cũng chưa đủ để chứng minh endpoint bị chặn đúng.

### 2.2. Không gắn security filters vào client kiểm thử

Một kiểu setup sai mục tiêu:

```java
@AutoConfigureMockMvc(addFilters = false)
```

`addFilters = false` ngăn việc đăng ký các filter bean từ Spring application context vào `MockMvc` được auto-configure. Controller vẫn chạy; nhiều test HTTP kiểm tra DTO vẫn có thể 200. Nhưng test không còn kiểm chứng chuỗi xử lý request như production.

Một kiểu khác:

```java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new ReportController())
    .build();
```

`standaloneSetup` hữu ích cho controller unit test, nhưng **không tự gắn** Spring Security filter chain. Nếu bạn không thêm security filters/test configuration, request sẽ đến controller mà không được bảo vệ ở tầng HTTP.

### 2.3. Filter chain có tồn tại nhưng request không đi vào chain bảo vệ đúng

Ví dụ ứng dụng có hai `SecurityFilterChain`:

- Chain A ưu tiên cao cho `/api/**` được cấu hình `permitAll`.
- Chain B dùng `hasAuthority("SCOPE_reports:read")` cho `/api/reports/**`.

Nếu chain A là **chain đầu tiên khớp request**, chain B sẽ không được dùng cho request đó. Một test positive vẫn có thể 200.

Bài học: phải kiểm tra **chain được chọn, matcher đúng, rule đúng và các kết quả từ chối đúng**, không chỉ kiểm tra có bean `SecurityFilterChain` trong context.

## 3. Thiết kế tiêu chí PASS bằng ma trận hai chiều

Giả sử endpoint `GET /api/reports/42` yêu cầu `SCOPE_reports:read` trong bearer token.

| Request | Có authentication? | Authority | Kỳ vọng |
|---|---|---|---|
| Anonymous | Không | Không | **401** (Bearer entry point) |
| JWT principal của Bob | Có | `SCOPE_profile` | **403** |
| JWT principal của Alice | Có | `SCOPE_reports:read` | **200** |
| JWT principal có nhiều authority | Có | Bao gồm `SCOPE_reports:read` | **200** |
| JWT principal của Carol | Có | `ROLE_ADMIN` nhưng không có scope | **403**, nếu policy chỉ xét scope |

Ba case đầu là mức kiểm tra tối thiểu.

- **200** chứng minh request được phép vẫn có thể xử lý.
- **401** chứng minh request chưa xác thực bị chặn.
- **403** chứng minh request đã xác thực nhưng thiếu quyền cũng bị chặn.

Nếu cấu hình bị đổi thành `permitAll` hoặc security filter không chạy, ca 401 và 403 **phải đỏ**; nếu bỏ hai ca đó, bộ kiểm thử có lỗ hổng.

### 3.1. 401 không phải kỳ vọng cho mọi ứng dụng

Ma trận trên dành cho **API Resource Server Bearer**, không dùng form/OAuth2 browser login. Với ứng dụng có form login, anonymous có thể nhận **302** đến trang đăng nhập; với security entry point được tùy chỉnh, status cũng có thể khác. Quan trọng là test phải chứng minh anonymous **không được nhận nội dung riêng tư**, thay vì khóa cứng 401 trong mọi kiến trúc.

### 3.2. Kiểm tra cả response body và side effect

Một test từ chối nên xác minh response không chứa dữ liệu tài nguyên. Với endpoint ghi, chỉ assert 403 là chưa đủ nếu ứng dụng đã cập nhật database trước khi chặn. Cần test repository, event, queue hoặc downstream call để xác nhận **hành động trái phép không diễn ra**.

## 4. Ứng dụng Servlet mẫu: chính sách đúng để đối chứng

Dùng Spring Boot 3, Spring Security 6, Java 17+ và JUnit 5. Trong ứng dụng thực, dùng phiên bản Spring Security tương thích với Spring Boot.

### 4.1. Dependency liên quan

```kotlin
// build.gradle.kts - minh họa dependency cho Servlet tests
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

### 4.2. Controller đơn giản nhưng rất dễ lộ khi security vắng mặt

```java
record ReportDto(long id, String title) {}

@RestController
class ReportController {

    @GetMapping("/api/reports/{id}")
    ReportDto report(@PathVariable long id) {
        return new ReportDto(id, "report-" + id);
    }
}
```

Controller trên **không tự kiểm tra authentication**. Đây là thiết kế có chủ đích: việc bảo vệ endpoint thuộc `SecurityFilterChain`. Nếu test bỏ filters hoặc có `permitAll`, mọi người sẽ nhận được body. Bởi vậy negative tests có thể trực tiếp phát hiện việc bảo vệ bị mất.

### 4.3. SecurityFilterChain phù hợp với Bearer API

```java
@Configuration
@EnableWebSecurity
class ReportApiSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports:read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Các import liên quan: `HttpSecurity`, `SecurityFilterChain`, `HttpMethod`, `SessionCreationPolicy`, `AbstractHttpConfigurer`, `Customizer`, `@Configuration`, `@Bean` và `@EnableWebSecurity`.

Cấu hình này đưa ra hai lớp bảo vệ:

1. **Authentication:** JWT bearer resource server xác thực token nếu request gửi token qua giao thức thật.
2. **Authorization:** request `GET /api/reports/**` cần authority `SCOPE_reports:read`.

`csrf(...disable)` chỉ phù hợp ví dụ API **stateless sử dụng bearer header**. Nếu ứng dụng dùng cookie/session, CSRF cần được đánh giá riêng và có test âm tính tương ứng. Không tắt CSRF để làm test POST dễ xanh.

### 4.4. Cung cấp JwtDecoder chỉ dành cho test

Vì chain cấu hình JWT Resource Server, Spring Security có thể cần `JwtDecoder` khi khởi tạo context. Các test dùng `jwt()` post-processor **không gọi decoder**, nhưng ta vẫn cung cấp bean test-only minh bạch:

```java
@TestConfiguration
class TestOnlyJwtDecoder {

    @Bean
    JwtDecoder jwtDecoder() {
        return token -> {
            throw new BadJwtException(
                "Real token verification is tested separately");
        };
    }
}
```

Nếu ứng dụng đã có một decoder khác trong test context, cần xử lý bean override theo cấu hình thực tế, không tạo hai bean cạnh tranh ngẫu nhiên. Bean trên **không được mang sang production**. Nó không làm JWT giả lập “hợp lệ về chữ ký”; test authorization ở đây sử dụng authentication được test helper tạo trước.

## 5. Bộ test MockMvc đúng: positive và negative cùng kiểm tra một rule

`@AutoConfigureMockMvc` mặc định thêm các filter đã đăng ký (`addFilters = true`). Không chuyển sang `false` trong security regression test.

```java
@SpringBootTest
@AutoConfigureMockMvc
@Import(TestOnlyJwtDecoder.class)
class ReportAuthorizationMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadPrivateReport() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(jwt()
                    .jwt(token -> token.subject("bob"))
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_profile"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readerScopeCanAccessReport() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(
                        new SimpleGrantedAuthority(
                            "SCOPE_reports:read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.title")
                .value("report-42"));
    }

    @Test
    void unrelatedAdminRoleDoesNotReplaceReadScope()
            throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(jwt()
                    .jwt(token -> token.subject("carol"))
                    .authorities(
                        new SimpleGrantedAuthority(
                            "ROLE_ADMIN"))))
            .andExpect(status().isForbidden());
    }
}
```

Các static imports: `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.status/jsonPath`, `SecurityMockMvcRequestPostProcessors.jwt`. Các import khác: `@SpringBootTest`, `@AutoConfigureMockMvc`, `@Import`, `@Autowired`, `@Test`, `MockMvc`, `SimpleGrantedAuthority`.

Test này nên chạy với chính `ReportApiSecurity` và `ReportController` được nạp trong application context. Với security filter chain đúng, bốn ca theo bảng ở mục 3 đều PASS.

### 5.1. Thử thay permitAll để xem test nào phải đỏ

Nếu một lập trình viên vô tình đổi:

```java
.requestMatchers(
    HttpMethod.GET, "/api/reports/**")
.permitAll()
```

thì `readerScopeCanAccessReport` vẫn có thể PASS. Nhưng:

- `anonymousCannotReadPrivateReport` phải FAIL vì anonymous có thể nhận 200.
- `authenticatedWithoutScopeIsForbidden` phải FAIL vì Bob nhận 200.
- `unrelatedAdminRoleDoesNotReplaceReadScope` phải FAIL vì Carol cũng nhận 200.

Chính **các ca từ chối** mới chứng minh hệ thống không mở rộng quyền ngoài dự kiến.

### 5.2. Thử bỏ filters để phát hiện “xanh giả”

Nếu đổi annotation test thành:

```java
@AutoConfigureMockMvc(addFilters = false)
```

controller vẫn trả JSON bình thường, nên `readerScopeCanAccessReport` có thể tiếp tục PASS. Tuy nhiên các case anonymous và thiếu scope sẽ không còn bị security filter chặn, **phải FAIL** nếu test đã viết đúng.

Đây là một phép kiểm tra sức mạnh của bộ test theo kiểu **mutation check có chủ đích**. Chỉ thực hiện trong nhánh/phiên thử nghiệm riêng và khôi phục cấu hình đúng ngay sau đó; không đưa cấu hình `permitAll` hoặc `addFilters = false` vào nhánh phát hành.

### 5.3. Vì sao @WithMockUser chưa đủ khi controller cần Jwt?

`@WithMockUser(username = "alice", roles = "USER")` cung cấp một authentication giả kiểu user/password. Nếu controller đọc `@AuthenticationPrincipal Jwt`, loại principal này không phù hợp. Test có thể thất bại ở controller, dù security filter authorization quyết định đúng.

Ví dụ ở trên chọn `jwt()` vì Resource Server thực tế sử dụng JWT authentication. Nhưng **mock JWT không chứng minh** `JwtDecoder`, chữ ký, issuer, audience, `exp` hoặc converter scope thật. Những trách nhiệm đó phải có kiểm thử bổ sung.

## 6. Anti-pattern: @WebMvcTest, standaloneSetup và test slice

`@WebMvcTest` hữu ích khi chỉ muốn tải MVC controller, nhưng tùy cách slice import security/configuration, test có thể:

- Có security auto-configuration nhưng thiếu custom `SecurityFilterChain` của ứng dụng.
- Có filter chain, nhưng rule khác production.
- Bị thay đổi bởi các test-specific bean/configuration.
- Cấu hình MockMvc qua `standaloneSetup` và bỏ qua filters.

Không khẳng định “`@WebMvcTest` luôn bỏ qua Spring Security” hoặc “`@WebMvcTest` luôn có đủ chính sách production”. Cả hai kết luận đều không đáng tin nếu chưa kiểm tra test context.

### 6.1. Một controller-only test có phạm vi hợp lệ

```java
@Test
void controllerReturnsAReportRepresentation() throws Exception {
    MockMvc controllerOnly = MockMvcBuilders
        .standaloneSetup(new ReportController())
        .build();

    controllerOnly.perform(get("/api/reports/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));
}
```

Test này có giá trị để kiểm tra mapping/serialization, nhưng chỉ chứng minh **controller**, không chứng minh authorization. Đặt tên `ReportControllerTest` và không đưa nó vào nhóm bằng chứng “security protected”.

### 6.2. Khi muốn test security trong @WebMvcTest

Cần nạp chính xác những bean security/decoder cần thiết và áp dụng Spring Security vào `MockMvc`; nếu dùng `MockMvcBuilders.webAppContextSetup(context)` thủ công, có thể:

```java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

`springSecurity()` ở đây là `SecurityMockMvcConfigurers.springSecurity`, **khác** helper Reactive `SecurityMockServerConfigurers.springSecurity`.

Điểm quyết định vẫn là ba test anonymous/thiếu scope/đủ scope **chạy trên security chain ứng dụng thực sự cần bảo vệ**. Cấu hình test có filter nhưng sai matcher vẫn có thể xanh một phần; do đó đừng thay negative tests bằng việc chỉ kiểm tra bean có tồn tại.

## 7. permitAll do thứ tự matcher và nhiều SecurityFilterChain

### 7.1. Thứ tự rule trong cùng chain

Cấu hình dễ sai:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/reports/**")
        .hasAuthority("SCOPE_reports:read")
    .anyRequest().denyAll()
)
```

Trong kiểu xử lý rule này, matcher đầu tiên phù hợp request có thể quyết định chính sách. `/api/reports/42` đã khớp `/api/**` nên rule cụ thể phía sau không còn hiệu lực.

Cấu hình hợp lý:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers(
        HttpMethod.GET, "/api/reports/**")
        .hasAuthority("SCOPE_reports:read")
    .anyRequest().denyAll()
)
```

Ngay cả khi code đã đảo lại thứ tự cho đúng, test vẫn cần cover các route công khai và route riêng tư để bảo vệ chính sách về sau.

### 7.2. Nhiều chain được xét theo độ ưu tiên

Ví dụ hai chain Servlet:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET, "/api/reports/**")
                .hasAuthority("SCOPE_reports:read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .csrf(AbstractHttpConfigurer::disable)
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

`FilterChainProxy` chọn **chain khớp đầu tiên theo thứ tự**, không chạy nối tiếp mọi chain cho cùng request. Nếu một chain ưu tiên cao có `securityMatcher("/**")` hoặc `/api/**` rồi `permitAll` quá rộng, nó có thể “nuốt” request cần bảo vệ của chain khác.

Nếu không có chain nào khớp, request có thể không được bảo vệ bởi Spring Security filter chain. Bài test cần xác nhận **đường dẫn thật** `/api/reports/42` được filter và bị từ chối khi thiếu quyền, không chỉ route giả định khác.

### 7.3. Matcher có thể sai vì method, path hoặc cấu hình proxy

Một số lỗi cấu hình khác:

- Chỉ bảo vệ `GET /api/reports/**` nhưng endpoint `POST /api/reports/export` vẫn mở.
- Test dùng `/api/reports/42`, production có context path hoặc servlet path khác.
- Có slash cuối, prefix version (`/v2/api/...`), dispatcher type hoặc path variable làm matcher khác điều dự kiến.
- Endpoint controller đã đổi URI nhưng test chỉ còn dùng URI cũ (404 vẫn có thể bị hiểu nhầm là “từ chối đúng”).
- Một rule `permitAll` dành cho health-check vô tình trùm sang admin/API.

Dùng **positive control** cho endpoint thật, kết hợp negative controls trên cùng path/method. Nếu test anonymous kỳ vọng 404, cần xác nhận endpoint thật sự tồn tại và một người có quyền truy cập được; 404 một mình có thể chỉ vì test gọi nhầm URL.

## 8. Kiểm tra filter chain có mặt: chỉ là chứng cứ bổ sung

Có thể dùng Spring Security diagnostics để quan sát chain và filters được chọn. Với Servlet, bean `springSecurityFilterChain` thông thường là `FilterChainProxy`, chứa nhiều `SecurityFilterChain`.

```java
@Autowired
@Qualifier("springSecurityFilterChain")
FilterChainProxy springSecurityFilterChain;

@Test
void applicationHasConfiguredSecurityChains() {
    assertThat(springSecurityFilterChain.getFilterChains())
        .isNotEmpty();
}
```

Test trên có thể phát hiện context bất ngờ **không có bean/chain**, nhưng **không đủ** để chứng minh `/api/reports/42` bị bảo vệ. Cần xem matcher và chain áp dụng cho request thực tế, đặc biệt khi có nhiều chain.

Một kiểm tra diagnostic có thể tạo mock request phù hợp với URL và xét chain đầu tiên khớp:

```java
MockHttpServletRequest request =
    new MockHttpServletRequest("GET", "/api/reports/42");
request.setServletPath("/api/reports/42");

SecurityFilterChain firstMatchingChain =
    springSecurityFilterChain.getFilterChains()
        .stream()
        .filter(chain -> chain.matches(request))
        .findFirst()
        .orElseThrow();

assertThat(firstMatchingChain.getFilters())
    .anyMatch(filter -> filter instanceof AuthorizationFilter);
```

Các import: `FilterChainProxy`, `SecurityFilterChain`, `AuthorizationFilter`, `MockHttpServletRequest` và AssertJ. Cách tạo request diagnostic phải mô phỏng đúng servlet path/context path của ứng dụng; các matcher phụ thuộc MVC infrastructure có thể cần WebApplicationContext thích hợp. Test này chỉ nhằm **phát hiện chain/filter thiếu**, không thay cho HTTP tests 401/403. `AuthorizationFilter` có thể tồn tại nhưng cấu hình `permitAll()` vẫn cho phép anonymous.

### 8.1. Khi debug, kiểm tra cả ứng dụng lẫn test setup

Nếu negative test bất ngờ nhận 200, hãy kiểm tra theo thứ tự:

1. `MockMvc` được tạo bằng `@AutoConfigureMockMvc(addFilters = true)` hay bằng setup nào?
2. Bean `springSecurityFilterChain` có trong context và được gắn vào MockMvc không?
3. Matcher nào chọn chain cho URL/method thực tế?
4. Có `permitAll` hoặc `anyRequest().permitAll()` trước rule bảo vệ không?
5. Request test có vô tình gắn `@WithMockUser` cấp lớp hoặc authentication mặc định không?
6. Controller có trả response trước khi policy ở service được áp dụng không?
7. Test có gọi nhầm endpoint public hoặc đường dẫn không tồn tại không?

Chỉ sau khi xác định các yếu tố này mới nên sửa security rules. Đừng thêm `permitAll` chỉ để làm một test thất bại được PASS.

## 9. Cấu hình permitAll ngoài ý muốn ở method security

Lớp HTTP không phải nơi duy nhất có kiểm soát quyền. Một service có thể dùng:

```java
@Service
class SecureReportService {

    @PreAuthorize("hasAuthority('SCOPE_reports:read')")
    public String readReport() {
        return "private-report";
    }
}
```

Nếu ứng dụng quên `@EnableMethodSecurity` (Servlet) hoặc `@EnableReactiveMethodSecurity` (Reactive), annotation có thể **không được thực thi**. Nếu test chỉ dùng user đủ quyền, kết quả vẫn 200; cần test người thiếu authority bị từ chối **qua bean Spring đã được proxy**.

Ví dụ unit/integration test method security Servlet:

```java
@SpringBootTest
class ReportMethodSecurityTest {

    @Autowired
    SecureReportService service;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "SCOPE_reports:read")
    void allowsReader() {
        assertThat(service.readReport())
            .isEqualTo("private-report");
    }

    @Test
    @WithMockUser(
        username = "bob",
        authorities = "SCOPE_profile")
    void rejectsOtherAuthority() {
        assertThatThrownBy(service::readReport)
            .isInstanceOf(AccessDeniedException.class);
    }
}
```

Để test này có ý nghĩa, security configuration của ứng dụng phải bật `@EnableMethodSecurity` và lời gọi phải đi qua **bean do Spring quản lý**. Không gọi `new SecureReportService()` hoặc self-invocation rồi kỳ vọng annotation luôn được áp dụng.

Nếu HTTP chain đã có cùng rule `hasAuthority`, một request bị 403 ở tầng HTTP **không chứng minh** method security hoạt động. Hãy test service trực tiếp hoặc tạo một đường kiểm tra có chủ đích để xác nhận interceptor thực thi, thay vì suy luận từ status HTTP.

## 10. CSRF: một negative control khác thường bị bỏ quên

Với ứng dụng browser dùng cookie/session, CSRF có thể bảo vệ các HTTP method thay đổi trạng thái. Một test chỉ gửi POST **đã có CSRF token** và assert 200 sẽ không phát hiện việc CSRF filter bị tắt:

```java
mvc.perform(post("/browser/notes")
        .with(user("alice").roles("EDITOR"))
        .with(csrf()))
    .andExpect(status().isOk());
```

Muốn chứng minh CSRF thực sự cần thiết, phải có case tương ứng **không gửi token** (hoặc gửi token sai) và kỳ vọng bị từ chối, ví dụ `403`:

```java
mvc.perform(post("/browser/notes")
        .with(user("alice").roles("EDITOR")))
    .andExpect(status().isForbidden());

mvc.perform(post("/browser/notes")
        .with(user("alice").roles("EDITOR"))
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
```

Các ví dụ này giả định ứng dụng thực sự cấu hình endpoint `POST /browser/notes`, user `ROLE_EDITOR` có đủ quyền, security filters được gắn và CSRF **được bật**. Chúng không chạy với API Bearer stateless ở mục 4 vì mẫu đó đã chủ đích tắt CSRF.

**Phân biệt 403 do CSRF và 403 do thiếu quyền:** để test CSRF, authentication phải có quyền tạo ghi chú; nếu thiếu role, 403 không cho biết CSRF có chạy hay không. Khi kiểm tra authorization, cung cấp CSRF token hợp lệ để không bị CSRF filter chặn trước.

## 11. WebFlux: bỏ lỡ SecurityWebFilterChain cũng tạo kết quả xanh giả

Với Reactive WebFlux, một test `WebTestClient` có thể được bind theo nhiều cách:

- `bindToApplicationContext(applicationContext)` cùng `apply(springSecurity())`: dùng application context và Spring Security test support.
- WebTestClient auto-configure trong Spring Boot WebFlux test: tùy setup test, có thể gắn vào context có WebFlux security chain.
- `bindToController(new ReportController())`: chủ yếu kiểm tra controller và không tự đảm bảo `SecurityWebFilterChain` của ứng dụng được nạp.
- `bindToServer()`: gửi HTTP tới server thật; mock authentication configurer trong JVM test không thể tự đi qua TCP.

### 11.1. Cấu hình Resource Server Reactive tương đương

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveReportApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(
                    HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports:read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .httpBasic(
                ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(
                ServerHttpSecurity.FormLoginSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
```

Ứng dụng mẫu WebFlux cần `spring-boot-starter-webflux`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-resource-server`, `spring-security-test` và `spring-boot-starter-test`. Không gộp hai class Servlet và Reactive cấu hình cùng một application type rồi giả định cả hai đều hoạt động. Test WebFlux phải thật sự nạp **Reactive WebApplicationContext**.

### 11.2. Dùng WebTestClient với các ca được phép và từ chối

Để các ví dụ Reactive tự chứa, dùng controller WebFlux tương đương (thay cho controller Servlet trong ứng dụng test riêng):

```java
@RestController
class ReactiveReportController {

    @GetMapping("/api/reports/{id}")
    Mono<ReportDto> report(@PathVariable long id) {
        return Mono.just(new ReportDto(id, "report-" + id));
    }
}
```

Đặt `ReactiveReportController` cùng cấu hình `ReactiveReportApiSecurity` trong **một WebFlux application context**, không nạp đồng thời controller Servlet có cùng đường dẫn trong cùng context.

```java
@TestConfiguration
class TestOnlyReactiveJwtDecoder {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder() {
        return token -> Mono.error(
            new BadJwtException(
                "Bearer decoding belongs to a different test"));
    }
}
```

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
@Import(TestOnlyReactiveJwtDecoder.class)
class ReactiveReportSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousIsUnauthorized() {
        client.get()
            .uri("/api/reports/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void missingScopeIsForbidden() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("bob"))
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_profile")))
            .get()
            .uri("/api/reports/42")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readerScopeIsAllowed() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice"))
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_reports:read")))
            .get()
            .uri("/api/reports/42")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id")
            .isEqualTo(42);
    }
}
```

Để chạy test, cần dùng phiên bản **Reactive** của controller ở mục 4 (hoặc một controller WebFlux tương đương), nạp `ReactiveReportApiSecurity`, test decoder và bảo đảm application type là reactive. Import static `SecurityMockServerConfigurers.mockJwt`; controller trả `ReportDto` được WebFlux serialize JSON như bình thường.

Nếu build có cả Spring MVC và WebFlux, Spring Boot có thể ưu tiên loại ứng dụng khác với mong đợi; chỉ annotation `@AutoConfigureWebTestClient` không đủ để khẳng định test đang chạy Reactivity đúng. Cần kiểm tra context và security chain.

### 11.3. Dựng WebTestClient thủ công cho đúng hạ tầng security

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .build();
```

`springSecurity()` ở đây từ `SecurityMockServerConfigurers` của `spring-security-test`, không phải `SecurityMockMvcConfigurers`. Nó tạo điều kiện để các helper reactive như `mockUser()`, `mockJwt()`, `mockOAuth2Login()` và `mockOidcLogin()` hoạt động với mock WebFlux exchange.

Anti-pattern:

```java
WebTestClient controllerOnly = WebTestClient
    .bindToController(new ReactiveReportController())
    .build();

// Chỉ assert GET 200 ở controllerOnly không chứng minh
// app đã bật SecurityWebFilterChain.
```

Khi dùng setup controller-only, không được gắn nhãn test đó “Reactive Security integration test” nếu filter chain thật không hiện diện. Một negative test trên **chính client cần kiểm chứng** phải phát hiện anonymous không bị từ chối.

### 11.4. Khi chạy WebTestClient qua RANDOM_PORT

`@SpringBootTest(webEnvironment = RANDOM_PORT)` gửi request qua HTTP server thật; `mockJwt()`/`mockUser()` là helper cho **mock exchange**, không tạo bearer credential trên remote HTTP connection. Với live HTTP, hãy gửi một JWT thử nghiệm đã ký và decoder test tương ứng:

```java
liveClient.get()
    .uri("/api/reports/42")
    .headers(headers ->
        headers.setBearerAuth(signedTestToken))
    .exchange()
    .expectStatus().isOk();
```

`signedTestToken` phải là token thực sự được server test tin cậy, không phải chuỗi placeholder. Negative controls cho live HTTP cũng cần: **không token → 401**, token hợp lệ nhưng thiếu scope → 403, token hợp lệ đủ scope → 200. Nếu decoder test `DenyAll` ở mục trên vẫn được dùng, mọi signed bearer token sẽ bị từ chối; phải tách **mock-authorization suite** khỏi **token-verification suite**.

## 12. Đừng để kết quả 404 hoặc 302 che lấp việc thiếu filter

Một test anonymous chỉ viết “không nhận 200” có thể PASS vì nhiều nguyên nhân khác nhau:

- `404`: controller không được map đến đường dẫn test.
- `302`: chuyển hướng do chính controller hoặc web server, không phải login entry point.
- `500`: lỗi ứng dụng khi đọc principal null.
- `403`: CSRF filter chặn POST, nhưng endpoint GET vẫn mở.
- Test không chạy gì vì filter tag/Gradle task đã loại bỏ toàn bộ cases.

Do đó cần **positive control**: cùng URI/method với một principal đủ quyền phải trả đúng body. Sau đó test anonymous và thiếu authority trên **cùng URI/method**. Nếu app dùng 302 để bắt đầu đăng nhập, phải kiểm tra `Location` thực sự trỏ đến flow được thiết kế, không chỉ assert `status().is3xxRedirection()`.

Ví dụ một trang browser riêng tư với form login:

```java
MvcResult response = mvc.perform(get("/private"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

String redirect = response.getResponse()
    .getHeader(HttpHeaders.LOCATION);

assertThat(redirect).isNotBlank();
assertThat(redirect).contains("/login");
```

Dùng assertion cụ thể hơn nếu ứng dụng có quy tắc redirect chính xác. Không sao chép kỳ vọng 302 này sang resource server API.

### 12.1. Login/OAuth2/OIDC giả lập có thể bỏ qua chính bước cần test

`with(oauth2Login())`/`with(oidcLogin())` và reactive `mockOAuth2Login()`/`mockOidcLogin()` thường tạo user đã xác thực mà không chạy flow OAuth2/OIDC thực. Vì vậy 200 ở các test đó không chứng minh authorization redirect, `state`, callback, Token Endpoint, ID Token signature, issuer hay nonce đúng.

Muốn bảo vệ một endpoint sau login, vẫn cần case chưa xác thực và thiếu quyền, và một suite riêng kiểm tra authorization-code flow/token validation khi đó là yêu cầu.

## 13. Tách quyền HTTP và quyền cấp đối tượng

Một endpoint có thể có HTTP rule đúng nhưng service vẫn trả bản ghi của tenant khác. Test âm tính cho bearer scope chỉ chứng minh tầng **chức năng**, không chứng minh policy cấp dữ liệu.

Ví dụ API `GET /api/documents/{id}` cần:

- Authentication hợp lệ.
- `SCOPE_docs:read`.
- `tenant_id` của request khớp tenant tài liệu.
- `sub` sở hữu tài liệu, nếu chính sách owner-only.

Ma trận bổ sung:

| Danh tính | Scope | Chủ sở hữu / tenant của bản ghi | Kỳ vọng |
|---|---|---|---|
| Alice alpha | Đủ | Alice alpha | 200 |
| Alice alpha | Đủ | Bob alpha | 404 hoặc 403 theo policy |
| Alice alpha | Đủ | Alice beta | 404 hoặc 403 theo policy |
| Alice alpha | Thiếu | Alice alpha | 403 |
| Anonymous | — | Alice alpha | 401 |

Nếu test chỉ dùng một bản ghi Alice alpha, code quên điều kiện tenant có thể vẫn xanh. Cần fixture **Alice ở cả alpha lẫn beta** hoặc dữ liệu chéo owner tương đương. Sau PUT/PATCH/DELETE bị từ chối, kiểm tra trạng thái database thật không đổi. Nếu test bị 404 do dữ liệu chưa seed, đó không phải bằng chứng quyền bị chặn: cần positive control xác nhận chủ sở hữu có thể truy cập cùng bản ghi.

## 14. Xây dựng security regression suite trong CI

CI không chỉ chạy một lệnh test, mà phải đảm bảo **những test có tính phân biệt** được thực thi. Một cấu trúc có thể chia thành:

| Nhóm | Kiểm tra | Mức ưu tiên CI |
|---|---|---|
| `security-http` | Anonymous, thiếu authority, đúng authority trên mỗi protected endpoint | Bắt buộc cho pull request |
| `security-method` | `@PreAuthorize` và proxy method security | Bắt buộc khi có method policy |
| `security-csrf` | POST không token/sai token, POST token hợp lệ | Bắt buộc với cookie/session app |
| `security-object` | Khác owner/tenant, đọc/ghi trái phép, không side effect | Bắt buộc với dữ liệu riêng tư |
| `security-authentication` | JWT chữ ký/iss/aud/exp, opaque introspection, login flow thật | Theo risk/khả năng tích hợp |
| `security-live-http` | RANDOM_PORT, token thực, cookie, headers, reverse proxy behavior | Bắt buộc trước release nếu phụ thuộc hợp đồng HTTP |
| `security-mutation` | Cố tình permitAll/bỏ filter để xác định negative tests đỏ | Chạy có kiểm soát trên nhánh kiểm chứng suite |

Tên nhóm chỉ là **quy ước ví dụ**, không tự tạo Gradle task hoặc CI job khi chưa cấu hình chúng.

### 14.1. JUnit 5 tag và Gradle test

Có thể gắn một tag cho bộ regression trọng yếu:

```java
@Tag("security-regression")
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationMvcTest {
    // Các test: anonymous 401, thiếu quyền 403, đủ quyền 200...
}
```

Gradle Kotlin DSL tối thiểu:

```kotlin
tasks.test {
    useJUnitPlatform()
}
```

Cấu hình này chạy tests mà Gradle/JUnit discovery tìm thấy, trừ khi có bộ lọc riêng ở nơi khác. Với nhiều test source set, các nhiệm vụ `test`, `integrationTest` hoặc test suites chuyên dụng chỉ chạy những tập được cấu hình tương ứng.

**Rủi ro lớn:** CI gọi `./gradlew test` nhưng security tests nằm trong `integrationTest` không được nối vào pipeline; hoặc CI dùng filter tag sai khiến **0 security tests** được thực thi. Đừng coi exit code 0 của một job là chứng cứ nếu không xác minh số lượng test đã chạy.

### 14.2. Một workflow CI minh họa

```yaml
name: Security regression

on:
  pull_request:
  push:
    branches: [main]

jobs:
  security-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Run JUnit and security regression tests
        run: ./gradlew --no-daemon test
      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-results
          path: |
            **/build/test-results/test/*.xml
            **/build/reports/tests/test/**
```

Đây là **minh họa GitHub Actions**; phiên bản action cần cập nhật theo chuẩn CI của dự án, và `test` chỉ kiểm tra suite mặc định nếu chưa tạo task khác. Nếu có `integrationTest`, pipeline phải gọi rõ task đó và upload đúng thư mục report tương ứng.

Các điểm cần bảo đảm:

1. Job trả lỗi khi security regression test FAIL.
2. Không bỏ qua exit code bằng `|| true` hoặc `continue-on-error: true` cho job bảo vệ bắt buộc.
3. Không dùng `@Disabled`, `@Ignore` hoặc tag exclusion để “tạm qua” mà không ghi nhận rủi ro.
4. Báo cáo JUnit XML chứng minh các ca 401/403/200 thực sự được chạy.
5. Khi dùng Testcontainers/IdP stub, kiểm tra readiness và cô lập fixtures; infra BLOCKED không được ghi là feature PASS.
6. Có branch protection/review policy để kết quả bảo mật bắt buộc được xem xét trước merge.

### 14.3. Test chỉ xanh vì 0 test được chạy

Một Gradle job có thể thành công nhưng không có kết quả test security do:

- Class test không được discovery vì package/source set/naming.
- Test dùng JUnit Jupiter nhưng `useJUnitPlatform()` không được cấu hình đúng.
- Gradle `--tests` pattern sai hoặc JUnit tag filter loại bỏ tất cả.
- Bước CI chạy một task khác với task chứa security tests.
- Test bị `@Disabled` hoặc condition theo environment.

Cần đọc report và số case executed. Một tiêu chí thực tế: **CI phải chứng minh bộ core regression gồm anonymous, thiếu scope và đủ scope trên endpoint mục tiêu đã chạy thành công**; nếu không có test result tương ứng, xem là thiếu bằng chứng.

## 15. Mutation check: test có thực sự phát hiện sai cấu hình?

Để đánh giá chất lượng regression suite, có thể thử thay một cấu hình trong **nhánh làm việc cục bộ** và quan sát kết quả dự kiến:

| Mutation có chủ đích | Kỳ vọng nếu suite mạnh |
|---|---|
| Đổi `hasAuthority("SCOPE_reports:read")` thành `permitAll()` | Ca anonymous 401 và thiếu scope 403 FAIL |
| Đổi `@AutoConfigureMockMvc` sang `addFilters = false` | Ca anonymous/thiếu scope FAIL |
| Thay client WebFlux bảo vệ bằng controller-only binding | Ca anonymous/thiếu scope FAIL |
| Đặt rule `/api/** permitAll` trước rule report | Ca anonymous/thiếu scope FAIL |
| Bỏ `@EnableMethodSecurity` khi policy chỉ nằm ở method | Ca thiếu authority ở service FAIL |
| Bỏ CSRF trong cookie browser flow | Ca POST không token FAIL |
| Bỏ điều kiện `tenant_id` ở truy vấn tài liệu | Ca truy cập chéo tenant FAIL |
| Bỏ điều kiện `ownerSubject` ở truy vấn | Ca truy cập dữ liệu Bob FAIL |

**Không cần giữ mutation trong codebase.** Đây là phép tự kiểm tra khả năng phát hiện lỗi, không phải thay đổi sản phẩm. Đảm bảo khôi phục code đúng trước khi commit.

Nếu sau khi cố tình mở endpoint bằng `permitAll` mà **mọi test vẫn xanh**, bộ test không đủ để bảo đảm chính sách authorization. Hãy bổ sung những ca negative ở đúng request path, method, principal và security layer.

### 15.1. Mutation test cũng có thể đánh lừa nếu fixture yếu

Ví dụ: test chéo tenant kỳ vọng 404 nhưng database không chứa bản ghi cần kiểm tra, nên test vẫn PASS dù đã bỏ filter tenant. Để mutation check có giá trị, cần positive control:

- Bản ghi phải tồn tại.
- Chủ sở hữu được phép truy cập phải nhận 200.
- Người khác với cùng ID phải bị từ chối.

Tương tự, một test CSRF kỳ vọng 403 nhưng user thiếu role sẽ vẫn 403 khi tắt CSRF; phải dùng user **đủ quyền** để phân biệt nguyên nhân.

## 16. Kiểm thử token và login thật không được thay thế bằng mock identity

Những test có `jwt()`, `mockJwt()`, `@WithMockUser`, `oauth2Login()` hoặc `oidcLogin()` được dùng để xác nhận logic ứng dụng **khi authentication đã được tạo**. Chúng không xác minh toàn bộ giao thức.

| Mục tiêu | Mock phù hợp | Test thực bổ sung |
|---|---|---|
| Rule `SCOPE_reports:read` | `jwt()` / `mockJwt()` | JWT Bearer ký thử nghiệm qua decoder nếu cần xác minh token |
| Role admin | `@WithMockUser` / `mockUser()` | HTTP Basic/form login thật nếu cần xác minh login |
| OAuth2 login principal | `oauth2Login()` / `mockOAuth2Login()` | Authorization redirect, `state`, callback và token endpoint |
| OIDC ID Token claims | `oidcLogin()` / `mockOidcLogin()` | ID Token signature, issuer/audience/nonce, UserInfo flow |
| Opaque bearer principal | `opaqueToken()` / `mockOpaqueToken()` | Introspection endpoint, `active=false`, outage và mapping scope |
| SecurityContext trong task async | `@WithMockUser` và executor wrapper | Context propagation/call từ request thật nếu cần |

Một suite bảo mật chất lượng thường dùng **nhiều lớp test**: mock nhanh cho quy tắc, test filter/decoder cho authentication thực, và E2E khi phụ thuộc HTTP network/IdP/DB. Đừng chọn một trong các lớp rồi tuyên bố nó chứng minh tất cả.

## 17. Khi nào lỗi 401, 403 hoặc 200 là bằng chứng chưa đủ?

| Quan sát | Có thể đúng | Còn cần xác minh |
|---|---|---|
| Anonymous GET trả 401 | API Bearer đã chặn chưa xác thực | Endpoint có tồn tại, người đủ quyền vào được không? |
| Bob GET trả 403 | Thiếu authority bị chặn | 403 có phải do CSRF/method khác, hay đúng rule cần test? |
| Alice GET trả 200 | Endpoint cho người đọc hợp lệ | Anonymous và Bob bị chặn không? Dữ liệu có đúng tenant không? |
| POST thiếu CSRF trả 403 | CSRF được bật | User có đủ role không? Có filter chạy không? |
| GET private trả 302 | Browser login entry point kích hoạt | `Location` có đúng login flow không? |
| Test 404 cho tài liệu Bob | Tài liệu có thể bị ẩn đúng policy | Bản ghi Bob có tồn tại và Bob đọc được không? |
| Test `@PreAuthorize` pass với Alice | Method chạy được cho người có quyền | Bob thiếu quyền có bị chặn qua proxy không? |
| CI build xanh | Các task được gọi đã thành công | Có đúng security tests được discovery/executed không? |

Nếu test không thể phân biệt hai hệ thống “bảo mật đúng” và “bảo mật bị mở”, test đó **không đủ sức chứng minh yêu cầu bảo mật**.

## 18. Checklist chẩn đoán khi negative test không hoạt động

1. **Xác định URI và HTTP method:** test có gọi đúng endpoint đang được bảo vệ không? Có positive control của endpoint đó không?
2. **Kiểm tra client setup:** `MockMvc`/`WebTestClient` đang gắn với ApplicationContext có security chain hay controller-only?
3. **Kiểm tra filters:** có `addFilters = false`, thiếu `springSecurity()`, hoặc exclude auto-configuration không?
4. **Kiểm tra chain:** `securityMatcher`, `@Order`, rule đầu tiên khớp có `permitAll` không?
5. **Kiểm tra danh tính:** có `@WithMockUser` cấp lớp khiến ca anonymous thành authenticated không? Có client mock đã mutate mặc định không?
6. **Kiểm tra authority:** `hasRole("ADMIN")` cần `ROLE_ADMIN`; `hasAuthority("SCOPE_reports:read")` cần đúng chuỗi đó.
7. **Kiểm tra method security:** `@EnableMethodSecurity`/`@EnableReactiveMethodSecurity` và bean proxy có thực sự hoạt động không?
8. **Kiểm tra CSRF:** POST bị 403 do CSRF hay do authorization? Test phải tách bạch.
9. **Kiểm tra dữ liệu:** với object-level authorization, fixture trái quyền có tồn tại không; có side effect sau request không?
10. **Kiểm tra CI:** test có chạy, có report, không bị skip/tag filter, không nuốt exit code không?

### 18.1. Bảo toàn trạng thái khi chạy test song song

Khi CI tăng parallel workers, không chia sẻ một `SecurityContextHolder` static tự sửa, client đã mutate vào biến global, user fixture hoặc database schema có thể bị test khác thay đổi. Dùng identity được tạo riêng mỗi ca; nếu test dùng DB, chọn transaction/cleanup và namespace phù hợp.

Không bỏ các negative tests để giảm thời gian CI; thường chúng chạy nhanh hơn E2E và có giá trị phát hiện regression lớn.

### 18.2. Thông điệp failure nên chỉ ra đúng hợp đồng bị phá

Một tên test như `testSecurity()` khó giúp chẩn đoán. Ưu tiên tên mô tả:

- `anonymousCannotReadPrivateReport()`
- `authenticatedWithoutScopeIsForbidden()`
- `readerScopeCanAccessReport()`
- `postWithoutCsrfIsForbidden()`
- `crossTenantDocumentIsNotVisible()`

Nếu CI đỏ do đổi `permitAll`, tên test sẽ giúp người review thấy rõ **cam kết bảo mật nào đã bị vi phạm**, thay vì chỉ thấy expected=401 actual=200.

## 19. Bài thực hành và tiêu chí đánh giá

Cho ứng dụng có `GET /api/reports/{id}` yêu cầu `SCOPE_reports:read` và `POST /browser/notes` có CSRF:

1. Viết ba test MockMvc cho reports: anonymous 401, Bob thiếu scope 403, Alice đủ scope 200 với body hợp lệ.
2. Viết test Carol chỉ có `ROLE_ADMIN` nhưng không có scope và xác nhận 403 theo policy minh họa.
3. Tạo một `standaloneSetup` chỉ test DTO report; giải thích vì sao 200 của nó không có giá trị làm bằng chứng authorization.
4. Thử bật `@AutoConfigureMockMvc(addFilters = false)` trong nhánh tạm; ghi nhận ít nhất hai negative tests đỏ.
5. Thử đổi rule report thành `permitAll()`; xác nhận positive 200 vẫn xanh nhưng các ca từ chối đỏ.
6. Thử thêm `requestMatchers("/api/**").permitAll()` trước matcher report; xác nhận suite phát hiện.
7. Nếu dùng nhiều filter chains, tạo test cho đường dẫn được chain ưu tiên cao nhất chọn.
8. Với cookie browser flow, test POST có CSRF hợp lệ thành công, POST không token/invalid token bị 403 **khi user đủ role**.
9. Với method security, test `@PreAuthorize` trên Spring-managed bean bằng Alice và Bob; thử tắt method security trong nhánh tạm rồi xác nhận Bob không còn bị từ chối.
10. Viết các test Reactive `WebTestClient` tương đương: anonymous 401, thiếu scope 403, đủ scope 200; phải đi qua `SecurityWebFilterChain` thật.
11. Bổ sung một test bảo mật cấp đối tượng: Alice alpha đọc được bản ghi của mình nhưng không được đọc bản ghi Bob alpha hoặc Alice beta.
12. Cấu hình CI chạy đầy đủ các test trên, lưu JUnit report và xác minh không có security test bị skip.
13. Thêm một suite token Bearer HTTP thật với decoder test, để phân biệt mock authentication với xác minh chữ ký.
14. Ghi rõ test nào chạy mock exchange, test nào chạy server thật, test nào vẫn phụ thuộc IdP hoặc DB test.

### Bảng đánh giá cuối

| Cấu hình | Positive 200 | Anonymous bị chặn | Thiếu scope bị chặn | Được kết luận security PASS? |
|---|---|---|---|---|
| Đúng `hasAuthority`, filter hoạt động | Có | Có | Có | **Có**, trong phạm vi rule HTTP đã test |
| `permitAll` trên endpoint private | Có | Không | Không | **Không** |
| MockMvc `addFilters = false` | Có | Không | Không | **Không** |
| Controller-only standalone test | Có | Không có bằng chứng | Không có bằng chứng | **Không**, chỉ PASS controller |
| Rule đúng nhưng test anonymous gọi URL sai | Có thể | 404 không chứng minh | Chưa rõ | **Không đủ bằng chứng** |
| Mock JWT tests PASS nhưng live JWT verifier fail | Có trong mock | Có thể đúng ở mock | Có thể đúng ở mock | Chỉ PASS authorization với mock; cần test decoder riêng |
| CI chỉ chạy positive test | Có | Chưa test | Chưa test | **Không đủ bằng chứng** |

**Tiêu chí hoàn thành:** Bộ kiểm thử và CI phải phát hiện được ít nhất hai thay đổi sai: **đổi endpoint riêng tư sang `permitAll`** và **bỏ security filters khỏi client kiểm thử**. Điều này đòi hỏi trên **cùng URI/method** phải có ca **được phép (200)**, **chưa xác thực bị chặn** và **đã xác thực nhưng thiếu quyền bị chặn**; thêm CSRF, method security và kiểm tra cấp tài nguyên khi hợp đồng yêu cầu. Test chỉ xanh với `@WithMockUser`, `jwt()`, `mockJwt()` hoặc `oauth2Login()` chưa bảo đảm authentication thực hoạt động. CI chỉ được xem là bằng chứng khi **đúng test đã được thực thi và kết quả được kiểm tra**, không phải khi mọi job đều xanh nhưng các ca âm tính vắng mặt.
