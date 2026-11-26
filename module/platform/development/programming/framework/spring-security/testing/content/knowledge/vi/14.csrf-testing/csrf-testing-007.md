# Phân biệt lỗi CSRF với lỗi xác thực hoặc phân quyền

Trong kiểm thử Spring Security, cùng một request có thể nhận `403 Forbidden` vì **CSRF token thiếu/sai** hoặc vì **người dùng đã đăng nhập nhưng không có quyền**. Một request khác có thể nhận `401 Unauthorized` hoặc redirect vì chưa xác thực. Nếu chỉ nhìn status code, ta rất dễ chẩn đoán nhầm nguyên nhân và viết assertion khiến test xanh nhưng không kiểm tra đúng lớp bảo vệ.

Bài học này trình bày cách tách ba loại quyết định:

- **CSRF:** request có token hợp lệ khi chain yêu cầu hay không?
- **Authentication (xác thực):** request có danh tính hợp lệ hay không?
- **Authorization (phân quyền):** danh tính đó có role, authority hoặc scope cần thiết hay không?

Với ứng dụng Servlet, dùng `MockMvc`, `@WithMockUser`, `@WithAnonymousUser`, `csrf()` và các request post-processor để giữ từng điều kiện cố định. Với WebFlux, áp dụng cùng cách suy luận bằng `WebTestClient` và các mutator Reactive tương ứng.

## 1. Ba lớp bảo vệ trả lời ba câu hỏi khác nhau

| Lớp | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| CSRF | Request có cung cấp token hợp lệ theo chính sách của chain không? | Thiếu token hoặc token sai trên `POST`. |
| Authentication | Server có xác định được người gọi là ai không? | Không có thông tin đăng nhập, mật khẩu sai, Bearer token không hợp lệ hoặc hết hạn. |
| Authorization | Người gọi đã xác thực có đủ quyền thực hiện thao tác không? | User chỉ có `ROLE_VIEWER` nhưng endpoint yêu cầu `ROLE_EDITOR`. |

CSRF token **không đăng nhập người dùng** và **không cấp quyền nghiệp vụ**. Ngược lại, người dùng đã đăng nhập hoặc có quyền cao vẫn phải gửi CSRF token nếu request đi qua chain bật CSRF và khớp matcher yêu cầu bảo vệ.

Ví dụ một endpoint `POST /reports` chỉ cho phép EDITOR:

- EDITOR không gửi token: request có thể bị CSRF từ chối.
- EDITOR gửi token hợp lệ: request được phép tiếp tục và có thể thành công.
- VIEWER gửi token hợp lệ: CSRF qua, nhưng authorization từ chối.
- Anonymous gửi token hợp lệ: CSRF qua, nhưng authentication yêu cầu đăng nhập.

## 2. Vì sao CSRF và phân quyền đều có thể trả 403?

Trong filter chain Servlet tiêu chuẩn, `CsrfFilter` thường chạy trước các filter xác thực phổ biến như form login, HTTP Basic hoặc Bearer token, và trước `AuthorizationFilter`. Do đó, request thuộc diện CSRF nhưng thiếu/sai token có thể bị chặn trước khi thông tin xác thực hoặc quyền của người dùng được đánh giá.

Khi CSRF token hợp lệ, request mới tiếp tục qua các bước xác thực và phân quyền. Nếu user đã xác thực nhưng không có quyền, cơ chế xử lý access denied thường trả `403`. Nếu chưa xác thực, `AuthenticationEntryPoint` có thể trả `401` hoặc redirect tới trang đăng nhập, tùy cấu hình.

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Nạp SecurityContext nếu đã có]
    B --> C{Request khớp CSRF matcher?}
    C -- Không --> E[Tiếp tục filter chain]
    C -- Có --> D{Token hợp lệ?}
    D -- Không --> X[CSRF từ chối: thường 403]
    D -- Có --> E
    E --> F[Authentication filters nếu cần]
    F --> G{Đã xác thực?}
    G -- Không --> Y[Entry point: 401 hoặc redirect]
    G -- Có --> H{Đủ role/authority?}
    H -- Không --> Z[Authorization từ chối: thường 403]
    H -- Có --> I[Controller và nghiệp vụ]
~~~

Sơ đồ là luồng khái quát của cấu hình tiêu chuẩn. `SecurityContext` có thể đã được nạp từ session hoặc được thiết lập trong test trước khi request chạy. Thứ tự filter cụ thể thay đổi theo cấu hình, authentication mechanism, custom filter và nhiều `SecurityFilterChain`; hãy kiểm tra chain thực tế khi kết quả khác dự đoán.

## 3. Status code là manh mối, không phải bằng chứng duy nhất

| Response thường gặp | Nguyên nhân phổ biến | Cách xác minh |
| --- | --- | --- |
| `403 Forbidden` | CSRF token thiếu/sai | Gửi lại cùng request với token hợp lệ và giữ nguyên user, quyền, body. |
| `403 Forbidden` | User đã xác thực nhưng thiếu quyền | Dùng cùng user với token hợp lệ; kiểm tra role/authority được cấp. |
| `401 Unauthorized` | Chưa xác thực hoặc credential không hợp lệ | Kiểm tra entry point và thử với danh tính hợp lệ. |
| `302 Found` hoặc redirect | Form login yêu cầu người dùng đăng nhập | Kiểm tra `Location` và cấu hình login entry point. |
| `400 Bad Request` | Body, validation hoặc định dạng request không hợp lệ | Kiểm tra xem request đã qua CSRF/authentication/authorization hay chưa. |
| `404 Not Found` hoặc `405 Method Not Allowed` | Không có route hoặc method handler phù hợp | Xác minh mapping trước khi kết luận về bảo mật. |

Ứng dụng có thể thay `AccessDeniedHandler`, `AuthenticationEntryPoint`, exception handler hoặc response format, vì vậy status code thực tế có thể khác bảng. Đừng suy ra nguyên nhân chỉ từ mã trạng thái.

Một cặp đối chứng rất hữu ích:

1. Gửi request thiếu token, nhận `403`.
2. Gửi cùng request với token hợp lệ, vẫn giữ nguyên danh tính và dữ liệu.
3. Nếu request thứ hai thành công, bằng chứng nghiêng về lỗi CSRF ở request đầu.
4. Nếu request thứ hai vẫn `403`, kiểm tra authorization hoặc quy tắc từ chối khác.
5. Nếu request thứ hai là `401`/redirect, kiểm tra authentication.

## 4. Chuẩn bị ví dụ Servlet có CSRF và phân quyền

Giả sử ứng dụng có endpoint tạo báo cáo. CSRF bật mặc định, chỉ role `EDITOR` được phép `POST /reports`, và HTTP Basic được dùng để minh họa lỗi xác thực:

~~~java
@Configuration
@EnableWebSecurity
class ReportSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/reports")
                    .hasRole("EDITOR")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}

@RestController
class ReportController {

    @PostMapping("/reports")
    ResponseEntity<Void> createReport() {
        return ResponseEntity.noContent().build();
    }
}
~~~

Các đoạn code lược bỏ import và giả định ứng dụng Servlet được nạp đầy đủ trong Spring Boot test. `204 No Content` là kết quả của controller minh họa; dự án thực tế cần dùng response nghiệp vụ của endpoint.

Thiết lập MockMvc có security filter:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityDiagnosisTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

Nếu tự dựng MockMvc từ `WebApplicationContext`, gắn filter bằng `.apply(springSecurity())`. Không dùng `standaloneSetup(controller)` thiếu filter hoặc `@AutoConfigureMockMvc(addFilters = false)` để kết luận về CSRF hay authorization.

## 5. Dùng danh tính giả lập để tách CSRF khỏi authorization

`@WithMockUser` thiết lập một người dùng đã xác thực trong `SecurityContext` của test. Với `roles`, Spring Security thêm tiền tố `ROLE_`: `roles = "EDITOR"` tương ứng authority `ROLE_EDITOR`.

### EDITOR thiếu token: CSRF từ chối

~~~java
@Test
@WithMockUser(username = "editor", roles = "EDITOR")
void editorWithoutToken_isForbiddenByCsrf() throws Exception {
    mockMvc.perform(post("/reports"))
        .andExpect(status().isForbidden());
}
~~~

EDITOR đã có quyền nhưng request vẫn bị từ chối vì thiếu token. Điều này cho thấy quyền không thay thế CSRF.

### EDITOR có token hợp lệ: request được phép

~~~java
@Test
@WithMockUser(username = "editor", roles = "EDITOR")
void editorWithValidToken_canCreateReport() throws Exception {
    mockMvc.perform(post("/reports").with(csrf()))
        .andExpect(status().isNoContent());
}
~~~

Ca này là đối chứng cho test thiếu token: cùng user, method và path, chỉ thêm token hợp lệ.

### VIEWER có token hợp lệ: authorization từ chối

~~~java
@Test
@WithMockUser(username = "viewer", roles = "VIEWER")
void viewerWithValidToken_isForbiddenByAuthorization() throws Exception {
    mockMvc.perform(post("/reports").with(csrf()))
        .andExpect(status().isForbidden());
}
~~~

VIEWER vượt qua CSRF nhưng không thỏa `hasRole("EDITOR")`, nên bị authorization từ chối. Đây là ca quan trọng nhất để chứng minh lỗi `403` đến từ thiếu quyền thay vì token.

### VIEWER thiếu token: CSRF chặn trước

~~~java
@Test
@WithMockUser(username = "viewer", roles = "VIEWER")
void viewerWithoutToken_isForbiddenByCsrf() throws Exception {
    mockMvc.perform(post("/reports"))
        .andExpect(status().isForbidden());
}
~~~

Ca này cũng nhận `403`, nhưng không chứng minh quy tắc `hasRole("EDITOR")` đã được đánh giá. Request thiếu token nên có thể bị chặn trước authorization.

## 6. Kiểm tra lỗi xác thực với anonymous và credential sai

`@WithAnonymousUser` mô phỏng người gọi chưa đăng nhập. Để xác định nhánh authentication, hãy cung cấp token CSRF hợp lệ để request đi tiếp:

~~~java
@Test
@WithAnonymousUser
void anonymousWithValidToken_requiresAuthentication() throws Exception {
    mockMvc.perform(post("/reports").with(csrf()))
        .andExpect(status().isUnauthorized());
}
~~~

Với `httpBasic()` trong cấu hình ví dụ, entry point mặc định trả `401`. Nếu dùng form login, response có thể là redirect tới trang đăng nhập. Vì vậy, assertion phải theo cơ chế xác thực mà ứng dụng đang sử dụng.

Có thể kiểm tra credential sai bằng HTTP Basic post-processor:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;

@Test
void invalidBasicCredentials_returns401AfterCsrfPasses() throws Exception {
    mockMvc.perform(post("/reports")
            .with(csrf())
            .with(httpBasic("editor", "wrong-password")))
        .andExpect(status().isUnauthorized());
}
~~~

Test này giả định ứng dụng có `UserDetailsService` hoặc cơ chế xác thực HTTP Basic thật để từ chối credential sai. Nếu dùng `@WithMockUser`, test đã bỏ qua bước xác thực credential; vì thế không dùng annotation đó để kiểm tra mật khẩu sai.

Đối với anonymous không có token:

~~~java
@Test
@WithAnonymousUser
void anonymousWithoutToken_isRejectedByCsrf() throws Exception {
    mockMvc.perform(post("/reports"))
        .andExpect(status().isForbidden());
}
~~~

Trong cấu hình tiêu chuẩn, CSRF có thể từ chối request trước khi HTTP Basic entry point xử lý. Khi thêm token hợp lệ, test trước đó mới kiểm tra được nhánh authentication.

## 7. Ma trận đối chứng cho cùng một endpoint

Với `POST /reports` trong cấu hình ví dụ:

| Danh tính | CSRF token | Kết quả điển hình | Lớp được kiểm tra |
| --- | --- | --- | --- |
| EDITOR | Thiếu | `403` | CSRF |
| EDITOR | Sai | `403` | CSRF |
| EDITOR | Hợp lệ | `204` | CSRF qua, authorization cho phép |
| VIEWER | Thiếu | `403` | CSRF |
| VIEWER | Hợp lệ | `403` | Authorization |
| Anonymous | Thiếu | `403` | CSRF có thể chặn trước authentication |
| Anonymous | Hợp lệ | `401` với HTTP Basic | Authentication |
| Credential Basic sai | Hợp lệ | `401` | Authentication |

Các hàng cùng status cần được phân biệt bằng điều kiện thử và đối chứng. Ví dụ VIEWER thiếu token và VIEWER có token hợp lệ đều có thể trả `403`; chỉ ca có token hợp lệ mới cô lập được nhánh authorization.

## 8. Phân biệt role và authority

`hasRole("EDITOR")` thường kiểm tra authority `ROLE_EDITOR`, trong khi `hasAuthority("reports:write")` kiểm tra chính xác chuỗi authority đã cấu hình.

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/reports")
        .hasAuthority("reports:write")
    .anyRequest().denyAll());
~~~

Test cho user đủ quyền phải dùng `authorities`, không dùng `roles`:

~~~java
@Test
@WithMockUser(authorities = "reports:write")
void userWithWriteAuthority_canCreateReport() throws Exception {
    mockMvc.perform(post("/reports").with(csrf()))
        .andExpect(status().isNoContent());
}
~~~

Nếu khai báo `@WithMockUser(roles = "reports:write")`, authority được tạo sẽ là `ROLE_reports:write`, không khớp với `reports:write`. Test khi đó có thể trả `403` do thiếu quyền dù token CSRF hợp lệ.

Với JWT resource server, authority có thể được ánh xạ từ scope thành `SCOPE_reports.write` hoặc theo converter tùy chỉnh. `jwt()` tạo authentication giả lập để test nhánh đã xác thực và authorization; nó không kiểm tra chữ ký, issuer, audience hay thời hạn của JWT thật. Muốn kiểm tra authentication thất bại do JWT sai, hãy test luồng Bearer token với decoder phù hợp thay vì dùng mutator tạo JWT hợp lệ.

## 9. Kiểm tra tác dụng phụ để xác định request đã tới nghiệp vụ chưa

Status code không cho biết controller hoặc service có chạy hay không. Với thao tác thay đổi dữ liệu, xác minh service không được gọi khi CSRF hoặc authorization từ chối:

~~~java
@Test
@WithMockUser(username = "viewer", roles = "VIEWER")
void viewerWithValidToken_doesNotCallReportService() throws Exception {
    mockMvc.perform(post("/reports").with(csrf()))
        .andExpect(status().isForbidden());

    verifyNoInteractions(reportService);
}
~~~

Ở ví dụ này token hợp lệ, nên `403` phản ánh thiếu quyền. Với ca CSRF, giữ user đủ quyền nhưng bỏ token hoặc dùng `csrf().useInvalidToken()`, rồi xác minh service không được gọi. Với integration test có database, đọc lại dữ liệu để bảo đảm không có báo cáo được tạo.

Lưu ý: method security như `@PreAuthorize` có thể từ chối ở tầng service sau khi controller đã được gọi. Nếu mục tiêu là phân biệt authorization ở URL với method security, hãy xác minh đúng ranh giới: controller có thể đã vào nhưng service bị từ chối. Không mặc định mọi lỗi quyền đều xảy ra trong `AuthorizationFilter`.

## 10. Đọc response body và log một cách có chủ đích

Mặc định, response `403` do CSRF hoặc access denied có thể không chứa thông tin đủ để phân biệt. Ứng dụng có thể cấu hình `AccessDeniedHandler` riêng, nhưng không nên phụ thuộc vào một body lỗi chung chung nếu chưa kiểm tra handler đang được sử dụng.

Để chẩn đoán:

- Kiểm tra status, header `Location` khi có redirect, `WWW-Authenticate` khi entry point HTTP Basic trả `401`, và response body nếu ứng dụng có error contract ổn định.
- Kiểm tra log bảo mật ở môi trường test/development để xác định `Invalid CSRF token`, authentication failure hoặc access denied. Không bật log nhạy cảm ở production chỉ để lấy token.
- Không log giá trị CSRF token, cookie session, mật khẩu hoặc Bearer token. Log lý do và request correlation ID là đủ.
- Nếu ứng dụng có `AccessDeniedHandler` hoặc `AuthenticationEntryPoint` tùy chỉnh, viết test cho status/body/headers mà handler cam kết.

Ví dụ kiểm tra redirect của form login cần assertion theo URL thực tế:

~~~java
mockMvc.perform(post("/reports").with(csrf()))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string("Location", containsString("/login")));
~~~

Đoạn này chỉ phù hợp với cấu hình form login và URL đăng nhập tương ứng; với HTTP Basic, hãy kỳ vọng `401` thay vì redirect.

## 11. Những yếu tố có thể làm kết quả khác dự đoán

| Yếu tố | Ảnh hưởng | Việc cần kiểm tra |
| --- | --- | --- |
| Nhiều `SecurityFilterChain` | URL khác nhau có thể dùng CSRF/authentication policy khác nhau | `securityMatcher`, `@Order` và chain được chọn. |
| `csrf.disable()` hoặc `ignoringRequestMatchers` | Request có thể không cần token | Matcher và ngoại lệ chính xác. |
| `permitAll()` | Không yêu cầu đăng nhập nhưng không tự miễn CSRF | Tách authorization khỏi CSRF. |
| Form login vs HTTP Basic | Anonymous có thể redirect hoặc nhận `401` | Authentication entry point. |
| `AccessDeniedHandler` tùy chỉnh | Body/status lỗi có thể khác mặc định | Hợp đồng response của ứng dụng. |
| CORS/preflight | `OPTIONS` có thể thất bại vì CORS dù không cần CSRF theo matcher mặc định | CORS config và filter liên quan. |
| Method security | Lỗi quyền có thể xảy ra trong service sau khi controller vào | Xác minh invocation ở đúng tầng. |
| MockMvc không có filter | CSRF và URL authorization không được kiểm tra | `@AutoConfigureMockMvc` hoặc `springSecurity()`. |

## 12. Đối chiếu với WebTestClient trên Reactive

WebFlux sử dụng `SecurityWebFilterChain`; `WebTestClient` có mutator riêng để thiết lập user và CSRF. Không dùng `@WithMockUser` hoặc `RequestPostProcessor` của MockMvc cho client Reactive.

Ví dụ user đủ quyền, token hợp lệ:

~~~java
webTestClient
    .mutateWith(mockUser().roles("EDITOR"))
    .mutateWith(csrf())
    .post()
    .uri("/reports")
    .exchange()
    .expectStatus().isNoContent();
~~~

User thiếu quyền nhưng token hợp lệ:

~~~java
webTestClient
    .mutateWith(mockUser().roles("VIEWER"))
    .mutateWith(csrf())
    .post()
    .uri("/reports")
    .exchange()
    .expectStatus().isForbidden();
~~~

Anonymous với token hợp lệ cần được kiểm tra theo authentication entry point và cấu hình Reactive thực tế. Cặp đối chứng vẫn giữ nguyên: token hợp lệ giúp cô lập authentication/authorization; token thiếu hoặc sai giúp kiểm tra nhánh CSRF. Nếu test qua HTTP thật, phải lấy token từ ứng dụng và giữ cookie/session đúng ngữ cảnh.

## Bài tập thực hành

Endpoint `POST /invoices` yêu cầu authority `invoice:approve`, CSRF bật và dùng HTTP Basic. Hãy thiết kế các ca:

1. User có `invoice:approve`, không token: bị từ chối do CSRF.
2. User có `invoice:approve`, token hợp lệ: thành công.
3. User chỉ có `invoice:read`, token hợp lệ: bị từ chối do authorization.
4. Anonymous, token hợp lệ: nhận lỗi authentication theo HTTP Basic.
5. Credential Basic sai, token hợp lệ: nhận lỗi authentication.

Với mỗi ca `403`, giải thích vì sao đó là CSRF hay authorization. Không chấp nhận lời giải chỉ dựa vào status code; phải nêu điều kiện đã được giữ cố định và request đối chứng.

## Ghi nhớ

Để phân biệt lỗi CSRF với lỗi xác thực hoặc phân quyền, hãy thay đổi **một điều kiện mỗi lần**. Giữ user đủ quyền rồi so sánh token thiếu/sai/hợp lệ để kiểm tra CSRF; giữ token hợp lệ rồi so sánh EDITOR, VIEWER và anonymous để kiểm tra authorization/authentication. `403` có thể đến từ CSRF hoặc thiếu quyền, `401`/redirect thường phản ánh yêu cầu xác thực. Hãy kiểm tra filter chain, entry point, handler và tác dụng phụ trước khi kết luận nguyên nhân.
