# Phân biệt kiểm thử đơn vị, kiểm thử theo lát cắt, tích hợp và đầu cuối

> **Chương:** Chiến lược kiểm thử  
> **Module:** `SPRING_SECURITY_TESTING` — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` cho ứng dụng Servlet và Reactive, với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và các cơ chế JWT/OAuth2/OIDC giả lập.

## 1. Vì sao phải phân biệt bốn tầng kiểm thử?

Một lỗi bảo mật có thể phát sinh ở những vị trí rất khác nhau:

- Hàm kiểm tra quyền sở hữu đơn hàng tính sai.
- Controller có rule đúng nhưng security filter chain không được nạp trong một cấu hình.
- `@PreAuthorize` được khai báo nhưng phương thức thực tế không đi qua Spring proxy.
- JWT được chấp nhận trong test vì đã giả lập thành công, trong khi decoder thật lại cấu hình sai issuer.
- Luồng đăng nhập, cookie, CSRF, redirect và API bảo vệ hoạt động riêng lẻ nhưng thất bại khi đi qua trình duyệt thật.

Không có một kiểu test duy nhất phát hiện tốt tất cả các lỗi trên. Cùng một yêu cầu, ví dụ “người dùng thường không được xem báo cáo”, có thể được chứng minh ở nhiều lớp nhưng **mỗi lớp tạo ra một mức bằng chứng khác nhau**.

Bài này phân biệt:

1. **Kiểm thử đơn vị** (*unit test*): cô lập một đơn vị logic.
2. **Kiểm thử theo lát cắt** (*slice test*): nạp một phần có chủ đích của Spring, thường là lớp web.
3. **Kiểm thử tích hợp** (*integration test*): ghép các thành phần thật để chứng minh chúng hoạt động cùng nhau.
4. **Kiểm thử đầu cuối** (*end-to-end, E2E test*): đi qua hành trình người dùng hoặc hệ thống gần với môi trường sử dụng thực.

Sau bài học, bạn có thể chọn tầng kiểm thử theo **rủi ro muốn phát hiện** và biết chính xác `spring-security-test` đang giả lập phần nào.

## 2. Bảng phân biệt nhanh

| Tiêu chí | Đơn vị | Lát cắt | Tích hợp | Đầu cuối |
|---|---|---|---|---|
| Phạm vi chính | Hàm, policy, service logic cô lập | Một phần Spring context, thường là MVC/WebFlux | Nhiều bean và hạ tầng cùng hoạt động | Hành trình qua HTTP/trình duyệt và các dịch vụ liên quan |
| Ví dụ thông dụng | JUnit + assertion + Mockito khi cần | `@WebMvcTest`, `@WebFluxTest` | `@SpringBootTest`, `MockMvc` hoặc `WebTestClient`, DB test | Server chạy thật, HTTP client/trình duyệt, định danh và dữ liệu gần thực tế |
| Có Spring Security filter chain? | Thường không | **Có nếu được cấu hình/nạp đúng** | Có khi test đi qua web security thực | Có trong ứng dụng đang chạy |
| Có kiểm thử `@PreAuthorize` thực? | Không, nếu gọi trực tiếp object thường | Chỉ khi method-security proxy thật nằm trong lát cắt | Có thể, khi gọi qua bean/proxy thật | Có, nếu hành trình chạm tới đường đó |
| Có mạng HTTP thật? | Không | Không | Tùy: `MockMvc` và client bind vào context thì không | Thông thường có |
| Phụ thuộc DB, OAuth2 provider, hệ thống ngoài? | Được cô lập | Thường bị thay bằng mock | Chỉ những thành phần được chủ ý đưa vào | Các thành phần hoặc bản thay thế có hành vi tương đương luồng thật |
| Ưu điểm | Nhanh, chỉ rõ sai logic | Phản hồi nhanh, phát hiện lỗi ở web/security boundary | Phát hiện lỗi cấu hình, kết nối, proxy, persistence | Phát hiện lỗi ghép nối và hành trình thực tế |
| Giới hạn | Không chứng minh cấu hình/HTTP | Không chứng minh phần nằm ngoài lát cắt | Không tự động chứng minh luồng trình duyệt/IdP thực | Tốn công thiết lập, chậm hơn, khó xác định nguyên nhân lỗi |

**Lưu ý:** Tên tầng phụ thuộc vào **những gì thực sự chạy**, không chỉ annotation. `@SpringBootTest` chưa chắc là E2E; `@SpringBootTest` kết hợp `MockMvc` vẫn gửi request trong tiến trình, không mở socket HTTP. Ngược lại, dùng `WebTestClient.bindToServer()` đến cổng thật là một bước kiểm thử qua mạng, nhưng chỉ trở thành E2E đầy đủ nếu nó kiểm chứng hành trình và các phụ thuộc liên quan.

### Hai trục cần tách riêng

Trong Spring Security Testing có hai câu hỏi độc lập:

**Trục 1 — Bao nhiêu hệ thống là thật?** Hàm thuần → web slice → context và hạ tầng tích hợp → hành trình thực qua mạng.

**Trục 2 — Danh tính được tạo như thế nào?** Giả lập principal/`SecurityContext` → đi qua bộ lọc với danh tính giả lập → đi qua cơ chế xác thực thật, như password login, session hoặc JWT decoder.

Ví dụ, một integration test `@SpringBootTest` có `@WithMockUser` có thể kiểm chứng đúng cả controller, service, repository và phân quyền; nhưng vì danh tính đã được gán giả, nó **chưa kiểm tra password login hoặc chữ ký JWT**.

## 3. Tình huống xuyên suốt và hợp đồng bảo mật

Giả sử hệ thống có:

- `GET /public/catalog`: công khai.
- `GET /api/reports`: chỉ dành cho principal có authority `REPORT_READ`.
- `DELETE /api/orders/{id}`: chỉ chủ sở hữu đơn hoặc người có `ROLE_ADMIN` được xóa, với điều kiện đơn ở trạng thái cho phép.
- `POST /api/orders`: người đã đăng nhập có thể tạo đơn; với nhánh session/cookie đang bật CSRF, phải gửi token hợp lệ.
- `GET /partner/data`: tài nguyên dành cho đối tác xác thực bằng Bearer JWT có authority `SCOPE_data.read`.

Một hợp đồng bảo mật tối thiểu trước khi chọn test:

| ID | Chủ thể và điều kiện | Hành động | Mong đợi |
|---|---|---|---|
| A1 | Ẩn danh | `GET /api/reports` | Bị chặn: ví dụ `401` trong API dùng HTTP Basic/Bearer |
| A2 | Đã xác thực, thiếu `REPORT_READ` | `GET /api/reports` | `403` |
| A3 | Đã xác thực, có `REPORT_READ` | `GET /api/reports` | `200` và chỉ dữ liệu được phép |
| B1 | Người dùng không là chủ đơn, không phải admin | `DELETE /api/orders/42`, CSRF hợp lệ | Bị từ chối; bản ghi không bị xóa |
| B2 | Chủ đơn, trạng thái cho phép | `DELETE /api/orders/42`, CSRF hợp lệ | Được xóa; dữ liệu thay đổi đúng |
| C1 | Đã xác thực qua session, thiếu CSRF | `POST /api/orders` | `403` và không tạo đơn |
| C2 | Đã xác thực qua session, CSRF hợp lệ | `POST /api/orders` | Được xử lý nếu dữ liệu hợp lệ |
| D1 | JWT có scope `data.write` nhưng thiếu `data.read` | `GET /partner/data` | `403` |
| D2 | JWT hợp lệ và scope `data.read` | `GET /partner/data` | Được phép; đúng dữ liệu |

HTTP status phụ thuộc cấu hình: form login có thể chuyển hướng `302` thay vì `401`; chính sách che giấu tài nguyên có thể trả `404` thay vì `403`. Bảng trên giả định thiết kế API cụ thể và phải điều chỉnh theo hợp đồng của sản phẩm.

Ở những phần tiếp theo, mỗi loại test sử dụng một phần hợp đồng này với câu hỏi bằng chứng khác nhau.

## 4. Kiểm thử đơn vị: chứng minh thuật toán ra quyết định

**Mục tiêu:** tìm lỗi của policy hoặc service logic trong một số đầu vào rõ ràng. Không cần chạy Spring context, servlet filter hay Reactor runtime nếu logic là hàm thuần.

Ví dụ tách quy tắc quyền sở hữu đơn hàng thành một thành phần nhỏ:

```java
final class OrderAccessPolicy {

    boolean mayDelete(
            String actorId,
            Set<String> authorities,
            String ownerId,
            boolean orderIsDeletable) {

        if (actorId == null || !orderIsDeletable) {
            return false;
        }

        return actorId.equals(ownerId)
            || authorities.contains("ROLE_ADMIN");
    }
}
```

Kiểm thử bằng JUnit 5:

```java
class OrderAccessPolicyTest {

    private final OrderAccessPolicy policy = new OrderAccessPolicy();

    @Test
    void ownerMayDeleteOpenOrder() {
        assertTrue(policy.mayDelete(
            "an", Set.of("ROLE_USER"), "an", true));
    }

    @Test
    void strangerCannotDeleteAnotherPersonsOrder() {
        assertFalse(policy.mayDelete(
            "binh", Set.of("ROLE_USER"), "an", true));
    }

    @Test
    void adminMayDeleteOpenOrder() {
        assertTrue(policy.mayDelete(
            "admin", Set.of("ROLE_ADMIN"), "an", true));
    }

    @Test
    void nobodyMayDeleteClosedOrder() {
        assertFalse(policy.mayDelete(
            "admin", Set.of("ROLE_ADMIN"), "an", false));
    }

    @Test
    void unauthenticatedActorIsDenied() {
        assertFalse(policy.mayDelete(
            null, Set.of(), "an", true));
    }
}
```

Ở đây, role được biểu diễn bằng authority `ROLE_ADMIN` đúng theo quy ước phổ biến của `hasRole("ADMIN")`. Quy tắc giả định ID thực của người dùng đã được xác minh từ phía server. Nếu client tự truyền `actorId`, logic này có thể bị lạm dụng; test HTTP/tích hợp cần xác minh danh tính được lấy từ nguồn tin cậy.

Đoạn unit test chứng minh:

- Cách kết hợp điều kiện chủ sở hữu, role và trạng thái đơn.
- Cách xử lý ranh giới ẩn danh, người lạ, quản trị viên.
- Một thay đổi sai ở nhánh `OR` hoặc điều kiện trạng thái làm test thất bại nhanh.

Đoạn unit test **không** chứng minh:

- Một endpoint có gọi `OrderAccessPolicy` hay không.
- Spring Security có nạp `SecurityFilterChain`/`SecurityWebFilterChain` đúng không.
- `@PreAuthorize` có chạy không.
- `403` có trả đúng hay request bị từ chối có thực sự không ghi DB không.

### Trường hợp unit test dùng Spring Security API

Có thể viết unit test trực tiếp cho một `AuthorizationManager` hoặc một hàm nhận `Authentication`, bằng cách tạo `UsernamePasswordAuthenticationToken` có authorities mong đợi. Khi test lớp logic đó, không cần `@WithMockUser`: annotation này cần tích hợp listener của Spring Test để thiết lập `SecurityContext`; nó không tự hoạt động như phép gán biến trong JUnit thuần.

Đối với logic phân quyền **Reactive**, `ReactiveSecurityContextHolder` gắn vào Reactor context của subscriber; không nên giả định `SecurityContextHolder` dựa trên `ThreadLocal` tự truyền qua chuỗi `Mono`/`Flux`. Nếu kiểm thử trực tiếp publisher có đọc reactive context, đưa ngữ cảnh vào Reactor context và kiểm tra publisher bằng `StepVerifier`.

**Bẫy quan trọng:** gọi trực tiếp `new OrderService().securedMethod()` rồi khẳng định `@PreAuthorize` hoạt động là không đúng. Method security do Spring proxy/interceptor thực thi; unit test chỉ kiểm tra logic bên trong method. Để chứng minh annotation, cần gọi qua Spring-managed bean với method security đã bật, hoặc test riêng interceptor/authorization manager.

## 5. Kiểm thử theo lát cắt Servlet: `@WebMvcTest` + `MockMvc`

**Mục tiêu:** chứng minh HTTP mapping, status, body và chính sách Spring Security ở ranh giới MVC với chi phí khởi tạo thấp. `@WebMvcTest` nạp các thành phần web liên quan, không mặc nhiên nạp toàn bộ business service/repository.

Ví dụ tối giản: một controller trả báo cáo và một filter chain quyết định quyền đọc.

```java
@RestController
class ReportController {

    @GetMapping("/api/reports")
    String read() {
        return "report-content";
    }
}

@Configuration
@EnableWebSecurity
class ReportSecurityConfiguration {

    @Bean
    SecurityFilterChain reportChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Cấu hình `httpBasic()` giúp ví dụ này định nghĩa rõ hành vi `401` khi chưa xác thực. Test lát cắt nhập cấu hình security cần thiết một cách tường minh:

```java
@WebMvcTest(ReportController.class)
@Import(ReportSecurityConfiguration.class)
class ReportMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousIsChallenged() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "an", roles = "USER")
    void authenticatedUserWithoutAuthorityIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "an", authorities = "REPORT_READ")
    void authorityHolderCanRead() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("report-content"));
    }
}
```

Các `import` Java được lược bỏ để tập trung vào ý tưởng; lớp test sử dụng JUnit 5, Spring Boot Test, `spring-security-test` và các static import của `MockMvcRequestBuilders`/`MockMvcResultMatchers`. Với cấu hình ứng dụng khác, hãy thay `ReportSecurityConfiguration` bằng cấu hình thực trong phạm vi test.

**Bằng chứng thu được:** yêu cầu `GET /api/reports` đi qua MVC và filter chain của lát cắt, rule `REPORT_READ` chặn người thiếu quyền, còn người đủ quyền nhận đúng nội dung.

**Những gì chưa được chứng minh:** repository có trả đúng báo cáo hay không, method security trong một service không được nạp có hoạt động hay không, password có được mã hóa/kiểm chứng thật hay không.

### `@WithMockUser` đang làm gì?

`@WithMockUser` tạo một `Authentication` giả cho security context của test. Chẳng hạn:

- `@WithMockUser(roles = "ADMIN")` tạo authority `ROLE_ADMIN`.
- `@WithMockUser(authorities = "REPORT_READ")` tạo authority chính xác `REPORT_READ`.
- `@WithMockUser(username = "an")` giúp mô phỏng principal có tên `an` mà không cần gửi password thật.

Nếu mã ứng dụng đòi một kiểu custom principal thay vì tên chuỗi, `@WithMockUser` mặc định có thể không đại diện chính xác. Khi đó có thể dùng `@WithUserDetails` cùng `UserDetailsService` thực trong test, custom `@WithSecurityContext` hoặc request post-processor phù hợp. Đừng để một principal giả sai kiểu làm test đi vào nhánh khác so với chạy thật.

### MockMvc có thể hoạt động với nhiều phạm vi

`MockMvc` là **công cụ mô phỏng request Servlet**, không đồng nghĩa với riêng slice test.

- `MockMvcBuilders.standaloneSetup(controller)` rất gọn; muốn chứng minh Spring Security phải cấu hình filter/chain phù hợp và hiểu phạm vi đã dựng.
- `@WebMvcTest` + `@Autowired MockMvc` là ví dụ điển hình của web slice.
- `@SpringBootTest` + `@AutoConfigureMockMvc` là integration test ở cấp application context; vẫn dùng MockMvc để đưa request vào MVC trong tiến trình.

Nếu cấu hình `@AutoConfigureMockMvc(addFilters = false)`, yêu cầu không đi qua các Servlet filters được đăng ký cho MockMvc. Dùng kiểu cấu hình đó để khẳng định “route đã được bảo vệ” sẽ tạo kết luận sai.

## 6. Kiểm thử theo lát cắt Reactive: `@WebFluxTest` + `WebTestClient`

Với ứng dụng dùng WebFlux, cơ chế bảo vệ nằm trong `SecurityWebFilterChain` và reactive security context. `MockMvc` là công cụ cho Servlet, còn `WebTestClient` hỗ trợ gửi request đến các thành phần Reactive được bind vào context hoặc đến server thật.

Một cấu hình giả định cho cùng quy tắc đọc báo cáo:

```java
@RestController
class ReactiveReportController {

    @GetMapping("/api/reports")
    Mono<String> read() {
        return Mono.just("report-content");
    }
}

@Configuration
@EnableWebFluxSecurity
class ReportReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain reportWebChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Kiểm thử lớp web Reactive, chủ động apply `springSecurity()` khi bind client vào application context:

```java
@WebFluxTest(ReactiveReportController.class)
@Import(ReportReactiveSecurityConfiguration.class)
class ReportWebFluxSliceTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousIsChallenged() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void userWithoutPermissionIsForbidden() {
        client.mutateWith(mockUser("an")
                .authorities(
                    new SimpleGrantedAuthority("ORDER_READ")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void userWithPermissionCanRead() {
        client.mutateWith(mockUser("an")
                .authorities(
                    new SimpleGrantedAuthority("REPORT_READ")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report-content");
    }
}
```

`springSecurity()` trong ví dụ này là `SecurityMockServerConfigurers.springSecurity()`, còn `mockUser()` đến từ `SecurityMockServerRequestPostProcessors` trong `spring-security-test`. Đây là các hàm **Reactive**, khác với `SecurityMockMvcRequestPostProcessors.user()` dùng trong Servlet.

Bài test này vẫn là **slice**, vì chỉ những thành phần được phép vào lát cắt được tạo ra. Nếu ứng dụng có rule phân quyền nằm ở service riêng và service ấy được mock, kết quả HTTP không chứng minh rule thực ở service.

## 7. Kiểm thử tích hợp: các lớp Spring hoạt động cùng nhau

**Mục tiêu:** phát hiện sai lệch giữa cấu hình, controller, service, method security, repository và thành phần hạ tầng mà một unit/slice test không thấy.

Ví dụ Servlet với context đầy đủ:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "an", authorities = "REPORT_READ")
    void allowedUserCanReadViaFullApplicationContext()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "an", authorities = "ORDER_READ")
    void wrongAuthorityIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }
}
```

Ví dụ này giả định ứng dụng có controller `/api/reports` và security configuration như hợp đồng đã nêu. Khác với `@WebMvcTest`, `@SpringBootTest` tạo application context rộng hơn, cho phép kiểm tra sự tương tác giữa các bean thực. Nhưng test vẫn dùng `@WithMockUser`: cơ chế xác thực thông tin đăng nhập thật nằm ngoài bằng chứng.

**Chỗ integration test tạo giá trị đặc biệt:** với yêu cầu xóa đơn hàng B1, setup một đơn do người A sở hữu; gửi `DELETE` dưới danh tính người B (CSRF hợp lệ nếu áp dụng); assert quyết định truy cập và đọc lại repository để xác nhận bản ghi **chưa bị xóa**. Cùng bộ test đó thử người A/admin để xác nhận nhánh cho phép. Cách này kiểm tra cả wiring, method security, nghiệp vụ và persistence.

### Cần gì để kiểm tra method security thực?

Ví dụ service:

```java
@Service
class BillingService {

    @PreAuthorize("hasAuthority('INVOICE_READ')")
    public Invoice readInvoice(Long id) {
        return loadInvoice(id);
    }

    private Invoice loadInvoice(Long id) {
        // Đọc từ repository trong ứng dụng thực
        throw new UnsupportedOperationException("example only");
    }
}
```

Khi test `@PreAuthorize`, cần:

- Bật `@EnableMethodSecurity` cho Servlet hoặc `@EnableReactiveMethodSecurity` ở cấu hình Reactive phù hợp.
- Gọi service qua **bean do Spring quản lý** để interceptor tham gia; tránh `new BillingService()`.
- Đảm bảo phần phụ thuộc vào dữ liệu đã được setup hoặc mock có chủ đích.
- Kiểm tra đúng exception hoặc HTTP mapping của truy cập bị từ chối; không đánh đồng mọi exception với một quyết định phân quyền.

Nếu test chỉ inject mock `BillingService` vào controller, method-security annotation trên implementation thật không được kiểm chứng. Nếu service tự gọi một method được bảo vệ trên cùng instance (**self-invocation**) với cơ chế proxy, interceptor cũng có thể không chạy qua lời gọi đó.

### Integration test trên Reactive

`@SpringBootTest` có thể nạp toàn bộ WebFlux context. Nếu `WebTestClient` được bind vào application context và apply `springSecurity()`, test kiểm tra nhiều bean thật nhưng không mở HTTP port. Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `WebTestClient.bindToServer()` sẽ đi qua HTTP stack thật.

Các đoạn sử dụng `mockUser()` hoặc `mockJwt()` trong client bind vào context giúp cô lập bài toán authorization. Khi cần xác minh authentication thực, gửi header `Authorization: Bearer ...`/cookie thật vào server chạy, bảo đảm decoder, cookie/session và thành phần cần kiểm tra không bị thay bằng cơ chế mock.

### Dữ liệu kiểm thử và độ tin cậy

Một integration test có repository hoặc DB phải dùng fixture có trạng thái xác định: chủ sở hữu khác nhau, trạng thái đơn cho phép/cấm, authority khác nhau, dữ liệu đã tồn tại. Có thể dùng DB kiểm thử hay Testcontainers nếu muốn kiểm tra hành vi phụ thuộc loại DB thực, và reset dữ liệu giữa các test để tránh phụ thuộc thứ tự chạy.

Việc test “đã nhận `403`” thường chưa đủ đối với thao tác ghi; kiểm tra dữ liệu không đổi hoặc tương tác phụ gây side effect không xảy ra mới chứng minh đầy đủ tính an toàn của từ chối.

## 8. Kiểm thử đầu cuối: chứng minh hành trình và ranh giới triển khai

**Mục tiêu:** quan sát kết quả từ phía client qua những mắt xích giống sản phẩm thực. Ví dụ một hành trình:

1. Người dùng mở trang đăng nhập hoặc ứng dụng chuyển hướng đến nhà cung cấp OAuth2/OIDC.
2. Người dùng đăng nhập; ứng dụng tạo session/cookie hoặc nhận access token hợp lệ.
3. Client truy cập API cần quyền.
4. Một người không đủ quyền nhận thông báo bị từ chối; không thấy dữ liệu hoặc thay đổi dữ liệu.
5. Đăng xuất/phiên hết hạn, truy cập tài nguyên bảo vệ không còn được chấp nhận.

Một test HTTP đơn giản để kiểm tra server có lắng nghe thật:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReportHttpJourneyTest {

    @LocalServerPort
    int port;

    WebTestClient http;

    @BeforeEach
    void setUp() {
        http = WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void anonymousRequestIsChallengedOverHttp() {
        http.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Test này **đi qua HTTP thật** nhưng mới kiểm chứng một chặng. Để gọi là E2E của hành trình xác thực, cần thêm bước đăng nhập/được cấp token theo giao thức mà sản phẩm sử dụng, gọi tài nguyên bảo vệ với cookie/header do chính bước đó tạo, xác minh quyền và logout hoặc hết hạn. Với UI, công cụ trình duyệt như Playwright/Selenium có thể giúp kiểm tra cookie, redirect và tương tác trên trang; cần xác định phần nào của identity provider được thay thế bằng môi trường test có hành vi tương ứng.

Khi dùng một identity provider giả lập thay vì nhà cung cấp thật, báo cáo chính xác phạm vi đã chứng minh. Có thể kiểm tra application flow với IdP test, nhưng kết quả không tự chứng minh tích hợp với production IdP hay cấu hình production.

E2E thường chạy ít hơn unit/slice vì setup nặng và khó khoanh vùng lỗi. Nên chọn một số hành trình bảo mật có ảnh hưởng cao, ví dụ đăng nhập → xem tài nguyên được phép → cố truy cập tài nguyên của người khác → bị từ chối → đăng xuất.

## 9. Những helper của `spring-security-test` chứng minh điều gì?

| Helper | Dùng ở đâu | Cung cấp | Không tự chứng minh |
|---|---|---|---|
| `@WithMockUser` | Spring Test, test với security context | User/authority/role giả lập | Đăng nhập, mật khẩu, token thật |
| `with(user("an"))` | `MockMvc` Servlet | User giả trên một request | Authentication provider thực |
| `with(csrf())` | `MockMvc` Servlet | CSRF token hợp lệ giả lập cho request | Toàn bộ hành trình lấy/phát hành CSRF token trong trình duyệt |
| `with(jwt())` | `MockMvc` Servlet/resource server | `JwtAuthenticationToken` và claims/authorities giả | Chữ ký, issuer, audience, expiry được decoder thực kiểm tra |
| `with(oauth2Login())` / `with(oidcLogin())` | `MockMvc` Servlet | OAuth2/OIDC principal và attributes/claims giả lập | Redirect và trao đổi authorization code với IdP |
| `mockUser()` | `WebTestClient` bind Reactive mock exchange | Reactive principal/authorities giả | Đăng nhập thực |
| `mockJwt()` | `WebTestClient` Reactive/resource server | JWT/authentication giả lập | Decoder và xác minh chữ ký thật |
| `mockOAuth2Login()` / `mockOidcLogin()` | `WebTestClient` Reactive | OAuth2/OIDC login giả lập | Trọn giao thức OAuth2/OIDC |
| `springSecurity()` | Setup `MockMvc` hoặc `WebTestClient` phù hợp | Gắn security test support/filter processing vào client test | Chỉ riêng việc apply helper không đảm bảo đúng cấu hình policy ứng dụng |

Ví dụ Servlet kiểm thử JWT scope của endpoint đối tác, **khi đã cấu hình resource server và policy thực**:

```java
mvc.perform(get("/partner/data")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_data.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/partner/data")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_data.write"))))
    .andExpect(status().isForbidden());
```

Ví dụ Reactive tương ứng với client bind vào application context:

```java
client.mutateWith(mockJwt()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_data.read")))
    .get().uri("/partner/data")
    .exchange()
    .expectStatus().isOk();
```

Nếu token thật bị hết hạn/sai chữ ký/sai issuer, cả hai helper trên vẫn có thể dựng authentication thành công, bởi chúng **bỏ qua khâu xác minh JWT bằng decoder**. Muốn kiểm tra việc từ chối token lỗi, dùng HTTP request có Bearer token được tạo thực và để resource server decoder/validators xử lý. Phải ghi rõ trong test rằng mock JWT chỉ chứng minh **authorization theo claims/authorities đã cấp**.

**Phân biệt role, authority và scope:** `roles = "ADMIN"` thường tạo `ROLE_ADMIN`; `hasAuthority("REPORT_READ")` đối chiếu chính xác `REPORT_READ`; scope JWT `data.read` thường được đổi thành `SCOPE_data.read`, trừ khi ứng dụng tùy biến converter. Test phải dựng đúng giá trị mà cấu hình thật sẽ nhìn thấy.

## 10. CSRF, xác thực và phân quyền có thể che khuất lẫn nhau

Xét `POST /api/orders` được bảo vệ bằng session/cookie và bật CSRF:

| Request | Tín hiệu đầu tiên có thể quyết định kết quả | Nên dùng để chứng minh |
|---|---|---|
| Người dùng đủ quyền, **thiếu CSRF** | CSRF filter trả `403` | Chính sách CSRF |
| Người dùng thiếu quyền, **thiếu CSRF** | CSRF có thể chặn trước rule quyền | Chưa đủ bằng chứng về authorization |
| Người dùng thiếu quyền, **có CSRF hợp lệ** | Rule authorization/method security quyết định | Chính sách quyền |
| Người dùng đủ quyền, **có CSRF hợp lệ** | Request có thể đến controller/service | Nhánh được phép và tác động nghiệp vụ |

Servlet:

```java
mvc.perform(post("/api/orders")
        .with(user("an"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\"SKU-1\"}"))
    .andExpect(status().isCreated());
```

Reactive:

```java
client.mutateWith(mockUser("an"))
    .mutateWith(csrf())
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "SKU-1"))
    .exchange()
    .expectStatus().isCreated();
```

Hai đoạn trên giả định controller và nghiệp vụ chấp nhận dữ liệu, người dùng đủ quyền, và ứng dụng dùng CSRF tương ứng; với Reactive, `csrf()` là helper của `SecurityMockServerRequestPostProcessors`.

Với API chỉ nhận Bearer token từ Authorization header và không dùng cookie tự động gửi, quyết định về CSRF khác nhánh web theo session. Tắt CSRF cho một API phải dựa trên threat model/cấu hình thực, không dựa vào việc test trả `403` gây bất tiện.

Cũng cần phân biệt thử **người ẩn danh** với thử **người đã đăng nhập nhưng thiếu quyền**. Yêu cầu ẩn danh đến một API dùng Basic/Bearer có thể nhận `401`; người đã xác thực nhưng không đủ authority thường nhận `403`. Nếu ứng dụng dùng form login, một request ẩn danh có thể bị chuyển hướng đến trang login. Assertion chính xác phản ánh hợp đồng đã thống nhất, không áp đặt máy móc một status cho mọi trường hợp.

## 11. Chọn tầng nào cho từng lỗi/rủi ro?

| Điều muốn chứng minh | Ưu tiên | Bổ sung khi cần |
|---|---|---|
| Điều kiện “chủ đơn hoặc admin” và trạng thái đơn | Unit test cho policy | Integration để xác minh policy thực sự được gọi và không xóa nhầm |
| URL `/api/reports` chặn người thiếu `REPORT_READ` | Web slice qua filter chain | Integration kiểm tra cấu hình thật theo profile |
| `@PreAuthorize` thực thi trong service | Integration với bean/proxy thật | Unit test cho logic policy bên trong |
| Thiếu/đủ CSRF đổi kết quả request | Slice với `MockMvc`/`WebTestClient` | E2E nếu cần kiểm chứng token qua cookie/form/browser |
| JWT scope quyết định `403`/`200` | Slice/integration với `jwt()` hoặc `mockJwt()` | Integration HTTP với token thật để kiểm tra decoder |
| JWT sai chữ ký, hết hạn, sai issuer/audience bị từ chối | Integration đi qua decoder thật | E2E qua môi trường cấp token gần thực tế |
| OIDC đăng nhập, callback và session sống đúng | Integration hoặc E2E theo hành trình thật | Slice với `oidcLogin()` cho logic dựa trên claims |
| Người dùng B không thấy/không sửa dữ liệu người A | Unit test rule sở hữu + integration với DB | E2E cho luồng công khai quan trọng |
| Logout làm cookie/session mất hiệu lực | Integration HTTP có session thật | E2E browser nếu cần cookie/redirect thực |

### Một chiến lược thực dụng

Bắt đầu bằng nhiều unit tests cho những nhánh logic lớn và nhiều web slice tests cho các quy tắc HTTP nhỏ. Bổ sung integration tests ở nơi wiring, proxy, repository, decoder và side effect có nguy cơ sai. Cuối cùng chọn vài E2E journeys đại diện cho tình huống quan trọng nhất của người dùng. Tỷ lệ chính xác giữa các loại phụ thuộc kiến trúc và rủi ro, không có tỷ lệ cố định phù hợp cho mọi dự án.

Một rule đơn giản như “`GET /api/reports` cần `REPORT_READ`” thường chỉ cần một cặp allow/deny ở lát cắt và một bài integration xác nhận cấu hình thật, thay vì lặp lại mọi hoán vị principal ở cả bốn tầng. Ngược lại, rule phức tạp theo ownership/tenant cần unit tests rộng, vài integration tests với dữ liệu thật và một E2E journey cho trường hợp ảnh hưởng lớn.

## 12. Các bẫy làm “test xanh” nhưng bảo mật vẫn sai

**Bẫy 1 — Test unit gọi thẳng method có `@PreAuthorize`.** Annotation không chạy nếu không có Spring-managed proxy/interceptor thích hợp. Test unit cho logic, và có test tích hợp để chứng minh enforcement.

**Bẫy 2 — Dùng `@WebMvcTest` rồi tưởng mọi bean và rule đều tồn tại.** Slice chỉ nạp một phần ứng dụng. Nếu method security nằm trong service đã mock hoặc cấu hình filter chain thật không được import, kết quả có thể không đại diện cho sản phẩm.

**Bẫy 3 — Đặt `@SpringBootTest` là mặc nhiên E2E.** Nó nạp context; `MockMvc` vẫn mô phỏng request trong tiến trình. Thêm server port thật và hành trình liên quan khi mục tiêu đòi E2E.

**Bẫy 4 — `@WithMockUser` hoặc `jwt()` xanh nên kết luận login/token hợp lệ.** Các helper đã tạo danh tính giả. Chúng chứng minh quyết định bảo mật dưới danh tính đã cấp, không chứng minh cơ chế kiểm chứng credentials.

**Bẫy 5 — Chỉ có trường hợp được phép.** Nếu đổi rule từ `hasAuthority("REPORT_READ")` thành `authenticated()`, test với user đủ quyền vẫn xanh. Phải có trường hợp đã xác thực nhưng thiếu quyền và kiểm tra bị chặn.

**Bẫy 6 — Chỉ assert status.** Yêu cầu bị từ chối vẫn có thể làm thay đổi DB trong một đường đi lỗi; yêu cầu được phép có thể trả nhầm dữ liệu tenant khác. Bổ sung assertion về body và trạng thái dữ liệu ở tầng phù hợp.

**Bẫy 7 — Test nhầm lỗi CSRF thay vì thiếu quyền.** Một request `POST` thiếu CSRF trả `403` không chứng minh `@PreAuthorize` hay authorization matcher hoạt động. Cấp token hợp lệ khi test quyền.

**Bẫy 8 — Test chạy một profile, deploy chạy một profile khác.** Cấu hình security có thể phụ thuộc profile, properties hoặc thứ tự các filter chain. Integration test dùng các cấu hình deployment quan trọng, nhất là khi có nhiều nhánh session, Basic và OAuth2 resource server.

**Bẫy 9 — Tạo user/mock không đúng cách ánh xạ authority.** `ROLE_ADMIN`, `ADMIN` và `SCOPE_admin` là những chuỗi khác nhau. Mock phải phản ánh mapping thật; nếu cần kiểm tra mapping, để converter thực chạy trong integration test.

**Bẫy 10 — Quên kiểm tra phương thức HTTP và resource ID khác nhau.** `GET` có thể được bảo vệ trong khi `DELETE` bị mở; owner A có thể xem nhầm tài nguyên owner B. Ma trận test phải đề cập cả action lẫn resource.

## 13. Quy trình đưa một yêu cầu vào bộ kiểm thử

Áp dụng với yêu cầu: “Nhân viên hỗ trợ chỉ được xem đơn hàng trong tenant đang được phân công; quản trị viên có thể xem mọi tenant; khách ẩn danh không được xem”.

1. **Ghi hợp đồng:** principal, role/authority, tenant, resource ID, HTTP method, kết quả allow/deny và dữ liệu không được lộ.
2. **Viết unit tests:** tách policy theo tenant và admin; kiểm tra ít nhất user đúng tenant, sai tenant, admin, anonymous.
3. **Viết slice tests:** `GET /api/orders/{id}` đi qua matcher, auth context, controller; xác minh `401`/`403`/`200` theo contract. Nếu kiểm soát tenant nằm trong service, slice không thay thế integration.
4. **Viết integration tests:** nạp security config và service thật; tạo hai tenant/two orders trong dữ liệu test; kiểm tra response và repository, nhất là trường hợp từ chối.
5. **Viết E2E journey trọng yếu:** tạo phiên hoặc token thật cho nhân viên được phân quyền, truy cập đơn đúng tenant rồi thử đơn sai tenant; đảm bảo client không hiển thị/nhận dữ liệu cấm.
6. **Kiểm tra giá trị test:** nếu vô tình bỏ rule tenant hoặc biến `hasAuthority` thành `authenticated()`, bài test phù hợp phải đỏ.

Cần ghi rõ trong tài liệu test nơi nào **giả lập danh tính** và nơi nào **kiểm chứng đăng nhập/token thật**. Một bộ test tốt không yêu cầu mọi tầng mô phỏng toàn bộ thế giới, nhưng phải có đủ bằng chứng để giải quyết những rủi ro đã nêu.

## 14. Bài tập tự đánh giá

Một ứng dụng Spring Security có `GET /api/payments/{id}` và `POST /api/payments/{id}/refund`. Người dùng có `PAYMENT_READ` được xem giao dịch thuộc tenant của mình. Người có `PAYMENT_REFUND` chỉ được hoàn tiền giao dịch cùng tenant đang ở trạng thái `SETTLED`. Refund chạy trên nhánh session/cookie có CSRF protection. Hệ thống còn cung cấp `GET /partner/payments`, bảo vệ bằng Bearer JWT scope `payments.read`.

**Yêu cầu:**

1. Thiết kế bảng ít nhất **tám** ca allow/deny bao gồm user đúng/sai tenant, thiếu authority, sai trạng thái, thiếu CSRF và JWT thiếu scope.
2. Chọn **hai** ca unit test cho rule tenant/trạng thái; nêu vì sao không cần HTTP.
3. Chọn **ba** ca slice test để chứng minh `401`/`403`/`200` hoặc một status allow phù hợp. Chỉ rõ sẽ dùng `MockMvc` hay `WebTestClient` theo stack Servlet/Reactive của ứng dụng.
4. Chọn **hai** ca integration test cần service/repository thật; nêu assertion cho dữ liệu không được sửa khi refund bị từ chối.
5. Thiết kế **một** E2E journey: từ đăng nhập/lấy token thật đến request bị từ chối hoặc được phép; ghi rõ thành phần nào đang chạy thật.
6. Giải thích vì sao dùng `jwt()`/`mockJwt()` với scope `payments.read` vẫn chưa chứng minh token được cấp bởi issuer đáng tin cậy.

**Tự kiểm:** Nếu đổi một policy để cho phép quá rộng, bạn có chỉ được test nào sẽ thất bại ở tầng nào không? Nếu đổi cơ chế xác thực và decoder thật hỏng, bạn có test nào phát hiện được lỗi mà `@WithMockUser` hay `mockJwt()` không thể phát hiện không?

Trả lời được hai câu hỏi đó nghĩa là bạn đã phân biệt **mục đích**, **phạm vi** và **giới hạn bằng chứng** của bốn tầng kiểm thử trong Spring Security Testing.
