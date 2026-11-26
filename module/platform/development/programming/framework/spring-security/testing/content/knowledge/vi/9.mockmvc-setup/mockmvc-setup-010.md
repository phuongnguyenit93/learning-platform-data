# addFilters=false và lý do có thể làm kiểm thử phân quyền đạt sai

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào **Spring MVC với MockMvc** và tùy chọn `@AutoConfigureMockMvc(addFilters = false)`: hiểu nó thay đổi pipeline kiểm thử ra sao và vì sao một bộ test có thể xanh dù các quy tắc truy cập HTTP không hề được thực thi.

Sau bài học, bạn có thể:

1. Giải thích `addFilters` quyết định việc đăng ký servlet filters từ application context vào MockMvc.
2. Phân biệt việc bean `SecurityFilterChain` tồn tại với việc security filters thực sự chạy trên request.
3. Nhận biết một test chỉ kiểm tra controller có thể trả 200 dù người dùng không có quyền.
4. Viết bộ ca kiểm thử có cả 401, 403 và 200 để xác minh filter chain.
5. Biết trường hợp nào method security vẫn có thể hoạt động dù servlet filters bị tắt.
6. Chọn cách cấu hình phù hợp thay vì tắt toàn bộ filters để né lỗi test context.

## 1. addFilters có tác dụng gì?

Khi dùng Spring Boot Test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ArticleSecurityTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

`@AutoConfigureMockMvc` tạo `MockMvc` dựa trên web application context. Thuộc tính `addFilters` quyết định những servlet `Filter` đã đăng ký trong application context có được đưa vào pipeline MockMvc hay không. Giá trị mặc định là `true`.

Khi viết:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

MockMvc do Boot cấu hình sẽ **không đăng ký các filters lấy từ application context**. Điều này bao gồm Spring Security filter chain và các servlet filters khác được đăng ký ở context đó, không chỉ riêng một filter bảo mật.

Hệ quả quan trọng: `SecurityFilterChain` bean vẫn có thể tồn tại, `FilterChainProxy` vẫn có thể được tạo, cấu hình vẫn có thể được nạp vào Spring context, nhưng MockMvc không gọi các filters đó khi thực hiện request. Vì thế, sự tồn tại của bean không chứng minh request đã đi qua filter.

~~~mermaid
flowchart TB
    A["@SpringBootTest + WebEnvironment.MOCK"] --> B["ApplicationContext"]
    B --> C["SecurityFilterChain / FilterChainProxy"]
    B --> D["Các servlet Filter khác"]
    E["@AutoConfigureMockMvc(addFilters=true)"] --> F["MockMvc"]
    C --> F
    D --> F
    G["@AutoConfigureMockMvc(addFilters=false)"] --> H["MockMvc không đăng ký<br/>filters từ context"]
    H --> I["DispatcherServlet / Controller"]
    F --> J["Request đi qua filter chain"]
    J --> I
~~~

`addFilters = false` không xóa bean khỏi Spring context và cũng không sửa policy trong `HttpSecurity`. Nó thay đổi **đường đi của request trong MockMvc**.

## 2. Vì sao test phân quyền có thể xanh sai?

Giả sử ứng dụng có endpoint `GET /api/admin` chỉ dành cho role `ADMIN`:

~~~java
@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Controller:

~~~java
@RestController
class AdminController {
    @GetMapping("/api/admin")
    String admin() {
        return "admin data";
    }
}
~~~

Khi request chạy qua Spring Security:

- Người dùng ẩn danh phải bị yêu cầu xác thực: HTTP Basic trong ví dụ trả 401.
- Người dùng đã xác thực nhưng chỉ có `ROLE_VIEWER` phải bị từ chối: 403.
- Người dùng có `ROLE_ADMIN` được phép: 200.

Nếu filters bị tắt, request có thể đi từ MockMvc vào `DispatcherServlet` rồi tới controller mà không qua `AuthorizationFilter`. Controller trả về `"admin data"`, nên một test chỉ kiểm tra response 200 của controller vẫn xanh.

Đây là một **false green**: test chứng minh controller hoạt động, nhưng người viết có thể hiểu nhầm rằng authorization đã được xác minh.

Ví dụ test dễ tạo cảm giác an toàn nhưng thực tế bỏ qua policy:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = false)
class MisleadingAdminTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerAlsoReachesTheController() throws Exception {
        // Diagnostic only: 200 here exposes that URL authorization was skipped.
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isOk());
    }
}
~~~

Test này sẽ nhận 200 khi controller hoạt động. Nhưng vì filters không chạy, kết quả tương tự có thể xảy ra với `VIEWER` hoặc request ẩn danh. Nó không chứng minh `hasRole("ADMIN")` được thực thi.

Các import cần có cho ví dụ này gồm JUnit `@Test`, `@Autowired`, `SpringBootTest`, `AutoConfigureMockMvc`, `WithMockUser`, `MockMvc` và static imports `get`, `status`. Test `viewerAlsoReachesTheController` là phép thử chẩn đoán để nhìn thấy lỗi cấu hình; không giữ assertion 200 này như một kỳ vọng bảo mật hợp lệ.

Nếu bổ sung ca âm:

~~~java
@Test
@WithMockUser(roles = "VIEWER")
void viewerMustBeForbidden() throws Exception {
    mockMvc.perform(get("/api/admin"))
        .andExpect(status().isForbidden());
}
~~~

ca này sẽ thất bại với cấu hình `addFilters = false` vì controller vẫn trả 200. Ca âm là phép thử quan trọng để phát hiện việc thiếu filter.

## 3. @WithMockUser không tự thay thế security filters

`@WithMockUser` giúp Spring Security Test tạo một `Authentication` giả lập trong `SecurityContext` dành cho test. Nó rất hữu ích để kiểm tra authorization, nhưng cần hiểu đúng phạm vi:

- Annotation tạo danh tính/authority cho test.
- Nó không tự đăng ký `SecurityFilterChain` vào MockMvc.
- Nó không khiến `AuthorizationFilter` chạy nếu servlet filter chain đã bị bỏ qua.
- Nó không kiểm tra username/password, password encoder hoặc user store.

Khi filters bị tắt, context giả lập có thể vẫn hiện diện trong thread của test và có thể được dùng bởi code đọc trực tiếp `SecurityContextHolder`. Method security qua Spring AOP proxy cũng có thể vẫn chạy nếu đã được bật và bean thật được gọi. Nhưng điều đó **không chứng minh URL authorization ở servlet filter layer** đã được kiểm tra.

Phân biệt các lớp:

| Lớp bảo mật | Cơ chế thực thi | Ảnh hưởng của addFilters=false |
| --- | --- | --- |
| URL authorization (`requestMatchers`, `hasRole`) | Servlet security filters, thường gồm `AuthorizationFilter` | Bị bỏ qua nếu filter chain không được đăng ký |
| Authentication qua HTTP Basic/form login/bearer token | Các authentication filters | Không chạy qua filter chain |
| CSRF | `CsrfFilter` | Không kiểm tra ở filter layer |
| Security headers | Các security filters liên quan | Không được thêm bởi những filters bị bỏ qua |
| Method security (`@PreAuthorize`) | Method interceptor / Spring AOP proxy | Có thể vẫn chạy; không phụ thuộc servlet filter registration |
| Business rule trong service | Code ứng dụng | Vẫn chạy nếu controller gọi service |

Do đó, không nên kết luận “addFilters=false vô hiệu hóa mọi bảo mật”. Nó bỏ qua các filters đăng ký trong MockMvc. Các lớp bảo mật chạy qua cơ chế khác, như method security, vẫn có thể hoạt động nếu cấu hình và proxy hiện diện.

## 4. Ví dụ kiểm thử đúng với filters được bật

Giữ nguyên `SecurityConfiguration` và `AdminController` ở mục 2. Dùng cấu hình:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc // addFilters mặc định là true
class AdminSecurityTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousCannotReadAdmin() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCannotReadAdmin() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAdmin() throws Exception {
        mockMvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin data"));
    }
}
~~~

Ba ca kiểm thử xác minh ba trạng thái khác nhau:

| Danh tính | Kết quả | Điều được chứng minh |
| --- | --- | --- |
| Anonymous | 401 với HTTP Basic | Entry point từ chối request chưa xác thực |
| `VIEWER` | 403 | Người dùng đã xác thực nhưng không đủ quyền |
| `ADMIN` | 200 | Người dùng có quyền được truy cập |

Nếu dùng form login hoặc entry point tùy chỉnh, anonymous có thể nhận 302 hoặc một status khác theo contract ứng dụng. Hãy assert kết quả đúng với cấu hình thật.

### Kiểm tra CSRF cùng filter chain

Nếu endpoint tạo dữ liệu là `POST` và CSRF đang bật:

~~~java
@PostMapping("/api/admin/reports")
@ResponseStatus(HttpStatus.CREATED)
void createReport() {
}
~~~

Đoạn controller này cần import `PostMapping`, `ResponseStatus` và `HttpStatus` từ Spring MVC/Spring HTTP.

Các ca:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void postWithoutCsrfIsRejected() throws Exception {
    mockMvc.perform(post("/api/admin/reports"))
        .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void postWithCsrfIsAccepted() throws Exception {
    mockMvc.perform(post("/api/admin/reports").with(csrf()))
        .andExpect(status().isCreated());
}
~~~

Các test POST cần static imports `post`, `status` và `SecurityMockMvcRequestPostProcessors.csrf`.

Không có `CsrfFilter` thì cả hai request có thể tới controller và nhận 201. Điều này cho thấy `addFilters = false` ảnh hưởng nhiều hơn role authorization: nó còn bỏ qua CSRF và các servlet filters khác.

## 5. Những filter nào bị ảnh hưởng?

Thuộc tính `addFilters` áp dụng cho các servlet filters được tìm thấy trong application context khi Boot cấu hình MockMvc. Ví dụ:

| Filter / nhóm filter | Vai trò | Điều gì mất đi khi không đăng ký? |
| --- | --- | --- |
| Spring Security filter chain | Authentication, authorization, CSRF, security headers | Request không đi qua các kiểm tra bảo mật HTTP |
| Custom authentication filter | Xử lý token hoặc header riêng | Token/header không được xử lý ở filter đó |
| CORS filter | Kiểm tra CORS và phản hồi preflight | Kết quả không đại diện CORS policy của filter |
| Character encoding filter | Chuẩn hóa encoding request/response | Encoding có thể khác ứng dụng thật |
| Request logging / tracing filter | Ghi nhận hoặc gắn metadata cho request | Test không kiểm tra được hành vi filter đó |
| Custom tenant / correlation filter | Thiết lập tenant hoặc request context | Controller có thể thiếu metadata mà production thường nhận |

Không phải tất cả các thành phần web đều là servlet filters. Ví dụ `HandlerInterceptor` và MVC argument resolver có vòng đời riêng. `addFilters = false` không đồng nghĩa tắt toàn bộ MVC infrastructure; nó chỉ ảnh hưởng việc đăng ký filters được Boot lấy từ application context vào MockMvc.

## 6. Khi nào dùng addFilters=false?

Có thể dùng khi mục tiêu của test chỉ là kiểm tra controller thuần túy và người viết **chủ động không kiểm tra servlet filter layer**. Ví dụ:

- Kiểm tra JSON serialization hoặc mapping của controller độc lập.
- Kiểm tra validation hoặc exception response mà test không nhắm tới filter.
- Một test MVC cần cô lập khỏi filter tùy chỉnh không thuộc phạm vi đang xem xét.

Nhưng nếu test được đặt tên hoặc được dùng làm bằng chứng cho authentication, URL authorization, CSRF, CORS hay security headers, không tắt filters.

Một cách tổ chức rõ ràng là tách lớp test:

~~~java
// Test controller thuần, không đưa ra kết luận về HTTP security.
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = false)
class ArticleControllerMvcTest {
    @Autowired
    MockMvc mockMvc;
}

// Test policy bảo mật, phải chạy qua filters.
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class ArticleSecurityTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Hai lớp test có mục tiêu khác nhau. Không tái sử dụng kết quả của `ArticleControllerMvcTest` để kết luận rằng security policy đã được xác minh.

## 7. Nếu context gặp lỗi filter hoặc dependency thì xử lý thế nào?

Đôi khi người viết thêm `addFilters = false` vì MockMvc test không khởi tạo được do một filter tùy chỉnh hoặc dependency của filter bị thiếu. Cách này có thể làm lỗi biến mất nhưng đồng thời loại bỏ hành vi mà security test cần xác minh.

Hãy tìm nguyên nhân cụ thể:

1. **Thiếu bean của filter:** import cấu hình đăng ký filter hoặc cung cấp dependency phù hợp.
2. **Filter cần external service:** thay collaborator ngoài phạm vi bằng mock; giữ filter thật nếu nó là đối tượng đang kiểm tra.
3. **Slice test thiếu security config:** dùng `@Import(SecurityConfiguration.class)` và cung cấp những dependency chain cần.
4. **Filter được đăng ký trùng:** kiểm tra cả auto-configuration và cấu hình đăng ký thủ công; không thêm cùng filter hai lần.
5. **Chỉ một filter không liên quan gây cản trở:** thiết kế test slice hoặc cấu hình filter rõ ràng hơn, và giữ một bộ security integration test có đầy đủ Spring Security filters.

Với MockMvc tự dựng thủ công từ context, cách tích hợp Spring Security là:

~~~java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Không dùng builder không có `springSecurity()` rồi kết luận URL authorization đã được thử. Nếu cần kiểm tra controller độc lập bằng `standaloneSetup`, hãy tách rõ khỏi bài test filter chain.

## 8. Phân biệt URL authorization và method security

Một ứng dụng có thể bảo vệ endpoint ở hai tầng:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/reports").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

và:

~~~java
@PreAuthorize("hasAuthority('REPORT_READ')")
public Report readReport() {
    // ...
}
~~~

Quy tắc URL chạy trong servlet security filter chain. Quy tắc method chạy qua Spring AOP proxy/interceptor khi method security được bật. Vì vậy:

- Với `addFilters = false`, URL rule ở trên không được thực thi bởi security filters của MockMvc.
- Method rule `@PreAuthorize` có thể vẫn được thực thi nếu bean được Spring proxy, method security được bật và request thực sự gọi qua proxy.
- Một test method security thành công không chứng minh URL authorization hoặc CSRF hoạt động.
- Một test controller dùng service mock không kiểm tra được method security bên trong implementation thật của service.

Hãy viết test riêng cho từng lớp bảo mật nếu cả hai đều quan trọng.

## 9. Dấu hiệu nhận biết test đang bỏ qua filters

| Dấu hiệu | Điều cần kiểm tra |
| --- | --- |
| Anonymous gọi URL admin vẫn nhận 200 | `addFilters = false` hoặc filter chain không được gắn |
| Viewer gọi URL admin vẫn nhận 200 | `AuthorizationFilter` không chạy hoặc matcher không khớp |
| POST thiếu CSRF vẫn nhận 201 | `CsrfFilter` không chạy |
| Security headers biến mất | Các header filters không được đăng ký |
| Test có `@WithMockUser` nhưng không phân biệt role | Danh tính test không đồng nghĩa URL authorization được thực thi |
| Bean `springSecurityFilterChain` tồn tại nhưng request vẫn qua | Bean có trong context nhưng không được MockMvc đăng ký |

Có thể kiểm tra bean filter trong context để xác nhận cấu hình đã nạp, nhưng kết quả cuối cùng phải dựa trên hành vi request. Một test ẩn danh phải bị chặn và một test thiếu role phải nhận phản hồi từ chối theo cấu hình ứng dụng.

## 10. Bài tập thực hành

**Bài 1 — Tạo false green.** Bật `@AutoConfigureMockMvc(addFilters = false)` và viết test `@WithMockUser(roles = "ADMIN")` cho `GET /api/admin`. Xác nhận test nhận 200. Sau đó thử anonymous và VIEWER trên cùng instance, giải thích vì sao response không còn phản ánh role rule.

**Bài 2 — Khôi phục filter.** Bỏ `addFilters = false`, chạy lại ba ca anonymous, VIEWER và ADMIN. Ghi nhận kết quả 401/403/200 trong cấu hình HTTP Basic.

**Bài 3 — CSRF.** Thử `POST` khi filters bị tắt, sau đó bật filters và so sánh request có/không có `with(csrf())`.

**Bài 4 — Tách test scope.** Tạo một lớp MVC test không cần filter và một lớp security test dùng cấu hình mặc định có filters. Đặt tên test để reviewer không nhầm hai phạm vi.

**Bài 5 — Method security.** Bật `@EnableMethodSecurity`, bảo vệ một service bằng `@PreAuthorize` và so sánh test gọi bean thật với test gọi mock. Giải thích vì sao method security có thể chạy dù servlet filters bị tắt.

## 11. Ghi nhớ

`@AutoConfigureMockMvc(addFilters = false)` bỏ qua việc đăng ký **các servlet filters từ application context** vào MockMvc. Security beans vẫn có thể tồn tại, nhưng URL authorization, authentication filters, CSRF và security headers không được thực thi qua filter chain của request đó.

Một test chỉ kiểm tra controller trả 200 có thể xanh dù request ẩn danh hoặc người dùng thiếu quyền cũng được đi qua. **Để kiểm chứng phân quyền HTTP, giữ filters được bật và luôn có ca bị từ chối** bên cạnh ca được phép. Dùng `addFilters = false` chỉ cho test MVC thuần có phạm vi được ghi rõ, không dùng kết quả đó làm bằng chứng bảo mật.
