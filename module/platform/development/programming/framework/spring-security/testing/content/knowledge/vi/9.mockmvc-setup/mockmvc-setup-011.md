# Phát hiện filter được gắn hai lần hoặc cấu hình thiếu filter

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào **Servlet/Spring MVC với MockMvc**: chẩn đoán khi một filter bị đăng ký lặp hoặc không được đưa vào pipeline kiểm thử.

Sau bài học, bạn có thể:

1. Phân biệt bean filter tồn tại trong Spring context với filter thực sự được đăng ký trong MockMvc.
2. Nhận ra hai cách tích hợp Spring Security thường dùng: Boot tự cấu hình và builder thủ công với `springSecurity()`.
3. Tìm nguyên nhân filter bị thêm hai lần, filter bị bỏ qua hoặc request không khớp `SecurityFilterChain`.
4. Dùng ca anonymous, thiếu role, đủ role và CSRF để xác minh hành vi thay vì chỉ kiểm tra bean.
5. Đọc log filter chain và kiểm tra cấu hình theo đúng phạm vi của test.

## 1. Hai lỗi ngược chiều

Khi kiểm thử Spring Security bằng MockMvc, có hai vấn đề dễ bị nhầm:

- **Thiếu filter:** request đi thẳng tới MVC/controller mà không chạy filter cần kiểm tra. Một endpoint đáng lẽ phải từ chối có thể trả 200.
- **Filter bị đăng ký hai lần:** cùng một filter hoặc cùng chuỗi filter xuất hiện nhiều lần trong pipeline. Một số filter có thể xử lý request lặp, ghi log hoặc thực hiện side effect nhiều lần; các filter kế thừa `OncePerRequestFilter` có cơ chế đánh dấu để tránh xử lý lặp trong cùng request, nên hiện tượng có thể không biểu hiện giống nhau ở mọi filter.

~~~mermaid
flowchart TB
    A["MockMvc.perform(request)"] --> B{"Filter chain được gắn đúng?"}
    B -->|Không có filter| C["DispatcherServlet / Controller<br/>bị gọi mà thiếu lớp bảo vệ"]
    B -->|Một lần| D["Security filters chạy đúng"]
    B -->|Trùng filter| E["Filter có thể chạy lặp<br/>hoặc tạo side effect"]
    C --> F["Kết quả sai phạm vi test"]
    D --> G["Kiểm tra authentication / authorization"]
    E --> H["Kết quả khó đoán / xử lý trùng"]
~~~

Mục tiêu là một pipeline có đúng các filter cần thiết, mỗi filter được đăng ký theo đúng cơ chế và thứ tự phù hợp.

## 2. Hiểu hai cách cấu hình MockMvc

### 2.1. Spring Boot tự đăng ký filters

Với Spring Boot:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ArticleSecurityTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

`@AutoConfigureMockMvc` tạo MockMvc từ web application context. Mặc định `addFilters = true`, nên các servlet `Filter` được tìm thấy trong application context được đăng ký với MockMvc, bao gồm filter bảo mật nếu hạ tầng Spring Security đã được nạp.

Khi Boot đã cấp MockMvc theo cách này, hãy sử dụng instance được inject. Không cần tự dựng một builder khác chỉ để gọi `springSecurity()` cho cùng mục đích.

### 2.2. Tự dựng MockMvc từ WebApplicationContext

Nếu không dùng MockMvc do Boot auto-configure, có thể tự tạo:

~~~java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

`SecurityMockMvcConfigurers.springSecurity()` kết nối filter đầu vào `springSecurityFilterChain` từ context và hỗ trợ test security context. Với cách này, không cần gọi thêm `.addFilters(securityFilterChain)` cho chính filter đó.

### 2.3. Không trộn hai cách trên vào cùng một pipeline

Một lỗi phổ biến là lấy filter bean rồi thêm thủ công, đồng thời gọi configurer vốn cũng đăng ký filter:

~~~java
Filter securityFilter =
    context.getBean("springSecurityFilterChain", Filter.class);

// Ví dụ minh họa cấu hình có nguy cơ thêm cùng filter hai lần:
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .addFilters(securityFilter)
    .apply(springSecurity())
    .build();
~~~

Trong builder này, `.addFilters(securityFilter)` đã thêm filter, còn `springSecurity()` cũng đưa filter đầu vào của Spring Security vào pipeline. Không kết hợp hai thao tác cho cùng filter. Chọn một cách tích hợp:

- Dùng `.apply(springSecurity())` khi tự dựng từ `WebApplicationContext`.
- Dùng `@AutoConfigureMockMvc` và inject MockMvc do Boot tạo.
- Chỉ dùng `.addFilters(...)` trực tiếp khi bạn chủ động quản lý filter cụ thể và không đồng thời thêm cùng filter qua configurer.

Việc tạo hai **instance MockMvc khác nhau** không tự nó là đăng ký trùng. Vấn đề xảy ra khi cùng một filter được đưa nhiều lần vào **một pipeline**.

## 3. Xác minh filter đã có trong context

Trước hết, xác nhận Spring đã tạo các bean bảo mật mong đợi. Với cấu hình Spring Security kiểu bean:

~~~java
@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Có thể kiểm tra bean trong test:

~~~java
@Autowired
ApplicationContext context;

@Test
void securityConfigurationIsLoaded() {
    assertThat(context.getBeansOfType(SecurityFilterChain.class))
        .containsKey("applicationSecurity");

    assertThat(context.getBean("springSecurityFilterChain"))
        .isInstanceOf(Filter.class);
}
~~~

Các import cần thiết gồm `org.springframework.context.ApplicationContext`, `jakarta.servlet.Filter`, `org.springframework.security.web.SecurityFilterChain` và static `org.assertj.core.api.Assertions.assertThat`.

Phép kiểm tra trên xác nhận:

1. Bean policy `applicationSecurity` đã được nạp.
2. Bean đầu vào `springSecurityFilterChain` tồn tại và có kiểu `Filter`.

Nhưng đây mới là **kiểm tra Spring context**. Nó chưa chứng minh MockMvc đang sử dụng filter đó. Ví dụ `@AutoConfigureMockMvc(addFilters = false)` vẫn có thể để các bean tồn tại trong context nhưng không đăng ký chúng với MockMvc.

Không ép kiểu bean `springSecurityFilterChain` thành `FilterChainProxy` nếu chưa xác minh kiểu thực tế; bean có thể được bọc. Dùng giao diện `jakarta.servlet.Filter` cho việc kiểm tra và tích hợp tổng quát.

## 4. Xác minh filter thực sự chạy trên request

Bằng chứng quan trọng nhất là hành vi request đi qua pipeline. Với policy ở mục 3:

| Request | Danh tính | Kết quả với HTTP Basic |
| --- | --- | --- |
| `GET /api/public` | Anonymous | 200 |
| `GET /api/admin` | Anonymous | 401 |
| `GET /api/admin` | VIEWER | 403 |
| `GET /api/admin` | ADMIN | 200 |

Ví dụ test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class FilterRegistrationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotAccessAdmin() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerIsForbidden() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminIsAllowed() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
    }
}
~~~

Các import cần thiết gồm JUnit `@Test`, `@Autowired`, `SpringBootTest`, `AutoConfigureMockMvc`, `WithMockUser`, `MockMvc` và static imports `get`, `status`.

Nếu anonymous nhận 401, VIEWER nhận 403 và ADMIN nhận 200 như mong đợi, đây là bằng chứng mạnh rằng policy URL đang được thực thi trên request. Nếu cả ba đều nhận 200, hãy kiểm tra filters và matcher. Nếu cả ba đều nhận 401, có thể test đang dùng default security chain hoặc danh tính giả lập không được áp dụng.

### CSRF là phép thử bổ sung

Với một endpoint POST có CSRF mặc định:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void postWithoutTokenIsRejected() throws Exception {
    mockMvc.perform(post("/api/admin/reports"))
        .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void postWithTokenIsAccepted() throws Exception {
    mockMvc.perform(post("/api/admin/reports").with(csrf()))
        .andExpect(status().isCreated());
}
~~~

Cần static imports `post`, `status` và `SecurityMockMvcRequestPostProcessors.csrf`. Nếu cả request có và không có token đều đi tới controller, có thể `CsrfFilter` chưa được đăng ký hoặc CSRF bị tắt trong policy. Hãy phân biệt hai nguyên nhân này trước khi kết luận.

## 5. Chẩn đoán thiếu filter

Các nguyên nhân thường gặp:

| Nguyên nhân | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| `@AutoConfigureMockMvc(addFilters = false)` | Bean filter tồn tại nhưng anonymous vẫn tới controller | Bỏ `addFilters = false` cho security tests |
| Dùng `standaloneSetup(controller)` | Controller chạy nhưng filter ứng dụng không có | Dùng web context hoặc tích hợp filter có chủ đích |
| Builder thủ công thiếu `springSecurity()` | Có web context nhưng request không đi qua security chain | Thêm `.apply(springSecurity())` một lần |
| `@WebMvcTest` không nạp custom config | Default chain hoặc policy khác được áp dụng | Import đúng `SecurityConfiguration` |
| URL không khớp chain nào | Filter proxy có thể được gọi nhưng không chọn security chain cho request | Kiểm tra `securityMatcher` và fallback chain |
| Rule cho phép truy cập | Filter chạy nhưng request vẫn nhận 200 | Kiểm tra `permitAll`, `requestMatchers` và thứ tự rule |
| Danh tính giả lập không đúng | Role test không tương ứng với authority policy | Kiểm tra `ROLE_` prefix, `@WithMockUser` và request processor |

Đặc biệt, **filter được gọi không có nghĩa request chắc chắn bị chặn**. `FilterChainProxy` có thể chạy nhưng không có `SecurityFilterChain` nào khớp request. Hoặc chain được chọn có rule `permitAll`. Vì vậy, hãy kiểm tra cả cấu hình matcher và phản hồi của endpoint.

### Kiểm tra khi dùng builder thủ công

Đối với builder từ web context, cấu hình bảo mật thường cần:

~~~java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Nếu dùng `standaloneSetup` cho một controller riêng, hãy hiểu rằng nó không tự thừa hưởng toàn bộ MVC config và filter bean của ứng dụng. Có thể truyền filter cụ thể vào configurer phù hợp, nhưng cần xác minh test đang kiểm tra đúng pipeline nào.

## 6. Chẩn đoán filter bị đăng ký hai lần

Filter trùng có thể đến từ những tình huống sau:

1. Dùng `@AutoConfigureMockMvc` (đã đăng ký các filter trong context), sau đó thêm lại một filter bằng custom `MockMvcBuilderCustomizer` hoặc builder tùy chỉnh.
2. Gọi `.addFilters(securityFilter)` rồi đồng thời gọi `.apply(springSecurity())` cho cùng filter.
3. Một filter tùy chỉnh được đăng ký qua nhiều cấu hình hoặc nhiều `FilterRegistrationBean`.
4. Một cấu hình đăng ký filter bổ sung cùng filter đã được đăng ký ở nơi khác, ví dụ vừa khai báo filter bean để Boot tự thêm vào MockMvc vừa tạo thêm một registration thủ công cho cùng instance.

Chỉ import lại cùng một class cấu hình không mặc nhiên làm filter được đăng ký hai lần; cần tìm hai đường đăng ký thực tế hoặc hai lần thêm vào cùng builder.

Các triệu chứng có thể gồm:

- Một filter có side effect bị gọi nhiều lần, ví dụ ghi audit event hoặc tăng counter hai lần.
- Log cho thấy cùng một filter xuất hiện lặp trong chuỗi.
- Request bị xử lý hai lần ở một lớp filter tùy chỉnh.
- Security context, response header hoặc request wrapper có hành vi khó giải thích.
- Một số filter không thể chạy lặp do cơ chế once-per-request, nên lỗi đăng ký trùng không nhất thiết luôn làm response sai rõ rệt.

### Kiểm kê filter bean và registration bean

Có thể liệt kê các filter bean trong context:

~~~java
@Test
void listFilterBeans() {
    Map<String, Filter> filters = context.getBeansOfType(Filter.class);
    filters.forEach((name, filter) ->
        System.out.println(name + " -> " + filter.getClass().getName()));
}
~~~

Nếu ứng dụng dùng Spring Boot, có thể kiểm tra thêm các `FilterRegistrationBean` để hiểu filter nào được đăng ký với servlet context:

~~~java
Map<String, FilterRegistrationBean> registrations =
    context.getBeansOfType(FilterRegistrationBean.class);

registrations.forEach((name, registration) ->
    System.out.println(name + " -> " + registration.getFilter().getClass().getName()));
~~~

Đoạn này cần import `org.springframework.boot.web.servlet.FilterRegistrationBean`, `java.util.Map` và `jakarta.servlet.Filter`. Đây là bước chẩn đoán, không phải assertion cứng cho mọi ứng dụng: một số filter có thể được đăng ký bởi hạ tầng theo cách khác, và filter đầu vào của Spring Security có thể được bọc. Đừng kết luận trùng chỉ vì cùng loại filter xuất hiện ở hai danh sách; hãy kiểm tra **cùng instance/registration** và đường đi request.

### Dùng filter đếm lần gọi để điều tra filter tùy chỉnh

Nếu nghi một filter tự viết bị đăng ký hai lần, có thể dùng một filter chẩn đoán đơn giản trong test:

~~~java
AtomicInteger invocations = new AtomicInteger();

Filter countingFilter = (request, response, chain) -> {
    invocations.incrementAndGet();
    chain.doFilter(request, response);
};

MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
    .addFilters(countingFilter)
    .addFilters(countingFilter) // Cố ý thêm cùng filter hai lần để quan sát.
    .build();

mvc.perform(get("/api/public"))
    .andExpect(status().isOk());

assertThat(invocations.get()).isEqualTo(2);
~~~

Ví dụ này minh họa rằng builder tích lũy các lần gọi `addFilters`; nó cố ý tạo cấu hình lỗi để quan sát, **không phải cấu hình dùng trong test suite thật**. Với `OncePerRequestFilter`, việc gọi hai lần có thể bị chặn bởi request marker, vì vậy không dùng bộ đếm loại này để suy ra mọi filter đều chạy hai lần.

Ví dụ đếm lần gọi cần import `java.util.concurrent.atomic.AtomicInteger`, `jakarta.servlet.Filter`, `MockMvcBuilders` và static `get`. Trong một test thực tế, tạo `invocations` trước mỗi phép thử hoặc reset counter để kết quả không phụ thuộc lần chạy trước.

## 7. Quy tắc chọn một đường tích hợp

| Cách dựng MockMvc | Cách đăng ký filter nên dùng | Tránh |
| --- | --- | --- |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Inject MockMvc do Boot tạo; để `addFilters = true` | Tự thêm lại filter đã được Boot đăng ký |
| `webAppContextSetup(context)` | `.apply(springSecurity())` | Vừa gọi configurer vừa `.addFilters` cùng security filter |
| `standaloneSetup(controller)` | Thêm filter/configurer có chủ đích nếu test cần filter | Giả định standalone tự tải toàn bộ application filters |
| MVC test thuần không kiểm tra filter | Có thể cân nhắc tắt filters, ghi rõ phạm vi test | Dùng kết quả này làm bằng chứng authorization |

Với Spring Boot, cấu hình thường nên là:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class SecurityIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Với builder thủ công, cấu hình thường nên là:

~~~java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Chọn một trong hai cách cho mỗi instance MockMvc. Không thêm lại security filter bằng một cơ chế thứ hai.

## 8. Log và quan sát FilterChainProxy

Khi cần xem request được chọn chuỗi nào, bật log trong cấu hình test:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Log giúp xác định:

- `FilterChainProxy` có nhận request hay không.
- Chuỗi `SecurityFilterChain` nào được chọn.
- Những security filters nào tham gia xử lý.
- Request có bị dừng bởi authentication, authorization hoặc CSRF hay không.

Nội dung log cụ thể thay đổi theo phiên bản. Không nên assert nguyên văn log trong test; dùng log để chẩn đoán và dùng status/header/body để xác minh hành vi.

Nếu log không cho thấy `FilterChainProxy` nhận request, hãy kiểm tra cách MockMvc được dựng và filter registration. Nếu proxy có nhận request nhưng không có chain phù hợp, kiểm tra `securityMatcher` và fallback chain. Nếu chain đúng nhưng status sai, kiểm tra authorization rule, authentication và CSRF.

## 9. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Khả năng | Bước kiểm tra đầu tiên |
| --- | --- | --- |
| Anonymous vào admin nhận 200 | Thiếu filter hoặc chain không khớp | Xác minh `addFilters`, `springSecurity()`, matcher |
| Anonymous nhận 401 nhưng ADMIN cũng 401 | Mock user không được chuyển vào request hoặc chain mặc định khác | Kiểm tra `@WithMockUser` và custom chain |
| Một filter tùy chỉnh ghi audit hai lần | Filter được thêm vào builder/registration hai lần | Kiểm kê bean, registration và builder customizer |
| CSRF thiếu token vẫn được phép | `CsrfFilter` không chạy hoặc CSRF bị tắt | Kiểm tra filter chain và policy CSRF |
| Header bảo mật xuất hiện hai lần | Filter/header writer hoặc registration trùng | Xem response headers và cấu hình filter |
| Bean `springSecurityFilterChain` có nhưng MockMvc không bảo vệ | Filter bean không được đăng ký với instance MockMvc đó | Kiểm tra Boot auto-config hoặc `apply(springSecurity())` |
| Log có chain nhưng endpoint vẫn 200 | Rule cho phép hoặc matcher/rule không đúng | Kiểm tra thứ tự matcher và `permitAll` |
| Filter chạy lặp nhưng response không đổi | Filter có thể là `OncePerRequestFilter` hoặc idempotent | Đo side effect của filter cụ thể; không chỉ nhìn status |

## 10. Bài tập thực hành

**Bài 1 — Thiếu filter.** Tắt `addFilters` trong một test và gọi endpoint admin bằng anonymous. Quan sát response; sau đó bật lại filters và viết assertion 401.

**Bài 2 — Đăng ký trùng.** Dùng filter đếm lần gọi, thêm cùng filter hai lần bằng `addFilters` và quan sát counter. Sau đó loại bỏ lần đăng ký dư và xác nhận filter chỉ chạy một lần.

**Bài 3 — Trộn hai cơ chế.** Tạo builder vừa `addFilters(securityFilter)` vừa `apply(springSecurity())`. Xác định vì sao cấu hình này có nguy cơ thêm filter lặp và sửa thành một đường tích hợp.

**Bài 4 — Kiểm tra matcher.** Tạo hai `SecurityFilterChain` với `@Order` và `securityMatcher` khác nhau. Viết test cho URL thuộc từng chain và một URL không thuộc chain nào.

**Bài 5 — Kiểm chứng đủ lớp.** Viết ca anonymous 401, VIEWER 403, ADMIN 200, POST thiếu CSRF 403 và POST có CSRF 201. Đối chiếu log `FilterChainProxy` với kết quả assertion.

## 11. Ghi nhớ

**Thiếu filter và đăng ký trùng filter là hai lỗi khác nhau.** Bean `springSecurityFilterChain` có trong context không có nghĩa MockMvc đã dùng nó; ngược lại, một filter có thể được thêm nhiều lần nếu vừa dùng auto-registration vừa thêm thủ công.

Với MockMvc do Boot tạo, thường chỉ cần `@AutoConfigureMockMvc` mặc định và inject instance. Với builder thủ công từ web context, dùng `.apply(springSecurity())` một lần. Xác minh bằng cả ca được phép và bị từ chối, kiểm tra CSRF và quan sát `FilterChainProxy` khi cần. Đừng dựa vào một response 200 hoặc sự tồn tại của bean để kết luận filter được gắn đúng.
