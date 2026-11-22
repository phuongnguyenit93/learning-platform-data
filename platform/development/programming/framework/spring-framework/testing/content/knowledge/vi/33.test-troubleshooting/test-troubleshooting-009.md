# 401 hoặc 403 do cấu hình bảo mật và dữ liệu yêu cầu

Khi một endpoint Spring trả về **401 Unauthorized** hoặc **403 Forbidden**, lỗi thường xuất phát từ Spring Security trước khi controller được gọi, từ quy tắc phân quyền tại method security, hoặc từ dữ liệu request làm thay đổi quyết định truy cập. Muốn chẩn đoán đúng, cần xác định request đã dừng ở lớp nào, người gọi được xác thực ra sao, authority nào đang có và request có mang đủ thông tin bảo mật như CSRF token hay không.

Hai status này có ý nghĩa khác nhau. 401 thường cho biết request chưa được xác thực hợp lệ và cần một cơ chế xác thực; 403 thường cho biết request đã được nhận diện nhưng không được phép thực hiện hành động. Tuy vậy, cấu hình AuthenticationEntryPoint, AccessDeniedHandler, cơ chế bearer token và chính sách bảo mật của ứng dụng có thể tùy chỉnh cách trả status. Vì vậy, hãy xem status cùng response header, security log và cấu hình đang chạy.

Bài học này tập trung vào cách tìm nguyên nhân và tái hiện lỗi bằng Spring MVC Test/MockMvc.

## 1. Request đi qua những lớp nào?

Trong ứng dụng Spring MVC có Spring Security, request thường đi qua servlet filter chain trước khi tới DispatcherServlet và controller.

    HTTP request
         |
         v
    Servlet container
         |
         v
    Spring Security FilterChainProxy
         |
         +--> Xác thực (session, Basic, Bearer, ...)
         |
         +--> CSRF / CORS / các security filter khác
         |
         +--> Phân quyền theo URL
         |
         v
    DispatcherServlet
         |
         v
    Handler mapping và controller
         |
         +--> Method security (@PreAuthorize, ...)
         |
         v
    Response

Nếu một security filter từ chối request, controller có thể chưa được gọi. Ví dụ, request POST thiếu CSRF token có thể bị từ chối trong filter chain trước khi Spring MVC tìm handler. Nếu controller đã được gọi nhưng method có @PreAuthorize và người dùng thiếu authority, method security có thể từ chối lời gọi.

Vì vậy, khi gặp 401 hoặc 403, đừng bắt đầu bằng việc sửa DTO hoặc validation ngay lập tức. Trước tiên hãy xác định request có đi tới controller hay không.

## 2. Phân biệt 401 và 403

Theo ý nghĩa HTTP phổ biến:

| Status | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| 401 Unauthorized | Chưa có thông tin xác thực hợp lệ hoặc xác thực thất bại. | Không gửi token, token hết hạn, Basic credentials sai. |
| 403 Forbidden | Request không được phép thực hiện hành động. | User đã đăng nhập nhưng thiếu ROLE_ADMIN; CSRF token thiếu hoặc không hợp lệ. |

### Trường hợp thường dẫn đến 401

- Endpoint yêu cầu authentication nhưng request không có session, Basic credentials hoặc Bearer token hợp lệ.
- Username/password không hợp lệ.
- Bearer token hết hạn, sai chữ ký hoặc không được chấp nhận.
- Authentication filter không thể tạo Authentication hợp lệ.
- AuthenticationEntryPoint được cấu hình để trả 401 cho request chưa xác thực.

Spring Security thường sử dụng AuthenticationEntryPoint khi cần yêu cầu client xác thực. Với HTTP Basic hoặc Bearer token, response có thể có header WWW-Authenticate mô tả scheme xác thực.

### Trường hợp thường dẫn đến 403

- Người dùng đã được xác thực nhưng không có authority cần thiết.
- URL yêu cầu ROLE_ADMIN trong khi Authentication chỉ có ROLE_USER.
- Method security từ chối quyền truy cập.
- CSRF protection đang bật nhưng request thay đổi trạng thái thiếu token hoặc token không hợp lệ.
- Quy tắc truy cập dữ liệu theo owner, tenant hoặc ACL từ chối tài nguyên.
- AccessDeniedHandler được cấu hình để trả 403.

### Quy tắc này có ngoại lệ

Spring Security phân biệt anonymous authentication và authenticated user khi xử lý AccessDeniedException. Một request anonymous bị từ chối có thể được chuyển sang AuthenticationEntryPoint và nhận 401; một principal đã xác thực nhưng không đủ quyền thường đi qua AccessDeniedHandler và nhận 403. Tuy nhiên, ứng dụng có thể tùy chỉnh entry point, handler hoặc status response.

Do đó, không nên kết luận chỉ từ status. Hãy kiểm tra:

- Header WWW-Authenticate.
- Response body hoặc error code riêng của ứng dụng.
- Security debug log.
- Authentication trong SecurityContext.
- Filter hoặc method security đã từ chối request.

## 3. Kiểm tra quy tắc phân quyền theo URL

Một cấu hình Spring Security có thể định nghĩa quyền theo HTTP method và path:

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/reports/**")
                            .hasAnyRole("USER", "ADMIN")
                        .requestMatchers("/api/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .build();
    }

Đọc cấu hình theo đúng thứ tự:

1. URL thuộc /public/** được phép truy cập mà không cần đăng nhập.
2. GET đến /api/reports/** cần role USER hoặc ADMIN.
3. URL /api/admin/** cần role ADMIN.
4. Các request còn lại cần authentication.

Các request matcher được xét theo thứ tự khai báo; quy tắc cụ thể cần đứng trước quy tắc tổng quát có thể khớp cùng request. Nếu đặt một matcher rộng như /api/** trước matcher /api/admin/**, quy tắc rộng có thể được áp dụng trước và làm quy tắc admin không bao giờ được xét.

Khi chẩn đoán, hãy đối chiếu đủ ba yếu tố:

- HTTP method thực tế.
- Path thực tế sau context path, servlet path hoặc reverse proxy mapping.
- Matcher đầu tiên phù hợp trong SecurityFilterChain được chọn.

Không chỉ so sánh URL nhìn thấy trong browser. Request POST và GET tới cùng path có thể chịu hai chính sách khác nhau.

## 4. Kiểm tra role và authority

Spring Security phân biệt role và authority. Phương thức hasRole("ADMIN") tự thêm prefix ROLE_ khi so sánh, tương đương yêu cầu authority ROLE_ADMIN. Phương thức hasAuthority("ROLE_ADMIN") so sánh chính xác chuỗi authority được chỉ định.

Ví dụ:

    .requestMatchers("/api/admin/**").hasRole("ADMIN")

cần Authentication có authority:

    ROLE_ADMIN

Nếu test tạo user bằng roles:

    @WithMockUser(username = "alice", roles = "ADMIN")

Spring Security Test tạo authority ROLE_ADMIN.

Nếu dùng authorities:

    @WithMockUser(username = "alice", authorities = "ADMIN")

authority được tạo là ADMIN, không tự thêm ROLE_. Với matcher hasRole("ADMIN"), hai cấu hình này không tương đương.

Bảng đối chiếu:

| Cấu hình kiểm tra | Authority được yêu cầu |
| --- | --- |
| hasRole("ADMIN") | ROLE_ADMIN |
| hasAnyRole("USER", "ADMIN") | ROLE_USER hoặc ROLE_ADMIN |
| hasAuthority("invoice:read") | invoice:read |
| hasAuthority("ROLE_ADMIN") | ROLE_ADMIN |
| @PreAuthorize("hasRole('ADMIN')") | ROLE_ADMIN |
| @PreAuthorize("hasAuthority('invoice:read')") | invoice:read |

Khi một test bất ngờ nhận 403, hãy kiểm tra authority thực tế trong Authentication thay vì chỉ nhìn tên role trong tài liệu nghiệp vụ.

## 5. Tái hiện 401 bằng MockMvc

Để kiểm tra security filter chain, test phải thực sự đưa filter của Spring Security vào MockMvc. Với Spring Boot, @AutoConfigureMockMvc thường cấu hình filter chain trong MockMvc nếu filter registration không bị tắt.

Ví dụ:

    @SpringBootTest
    @AutoConfigureMockMvc
    class ReportSecurityTest {

        @Autowired
        MockMvc mockMvc;

        @Test
        void anonymousUserCannotReadProtectedReport() throws Exception {
            mockMvc.perform(get("/api/reports/42"))
                    .andExpect(status().isUnauthorized());
        }
    }

Test này gửi request không có authentication. Nếu endpoint yêu cầu người dùng đăng nhập và entry point trả 401, assertion sẽ thành công.

Nếu ứng dụng dùng form login, response anonymous có thể là redirect đến trang đăng nhập thay vì 401. Khi đó cần kiểm tra status và Location phù hợp với cấu hình. Với REST API, thường cấu hình entry point trả 401 để client nhận response rõ ràng.

### Xác nhận header xác thực

Với HTTP Basic hoặc Bearer, response 401 thường có WWW-Authenticate. Có thể kiểm tra:

    mockMvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));

Header cụ thể phụ thuộc authentication scheme và cấu hình entry point. Không nên hard-code Basic nếu endpoint thực tế dùng Bearer.

## 6. Tái hiện 403 do thiếu authority

Spring Security Test cung cấp @WithMockUser để thiết lập Authentication giả lập cho test method. Test có thể kiểm tra người dùng đã đăng nhập nhưng không đủ quyền:

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userRoleCannotAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin/users"))
                .andExpect(status().isForbidden());
    }

Nếu endpoint yêu cầu ROLE_ADMIN, user chỉ có ROLE_USER sẽ bị từ chối với 403.

Test quyền hợp lệ:

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanAccessAdminEndpoint() throws Exception {
        mockMvc.perform(get("/api/admin/users"))
                .andExpect(status().isOk());
    }

Hai test này tạo ra một cặp kiểm tra rõ ràng: user thiếu quyền bị từ chối, user có quyền được phép. Nếu controller còn phụ thuộc service, hãy stub dữ liệu service tương ứng để test không thất bại vì một nguyên nhân khác sau khi qua security.

## 7. Dùng request post-processor user() để kiểm soát principal

Thay vì đặt @WithMockUser trên method, có thể gắn user trực tiếp vào request:

    mockMvc.perform(get("/api/admin/users")
                    .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

Cách này tiện khi một test method cần gửi nhiều request với các principal khác nhau.

Nếu endpoint kiểm tra authority tùy chỉnh:

    mockMvc.perform(get("/api/invoices")
                    .with(user("alice")
                            .authorities(
                                    new SimpleGrantedAuthority("invoice:read"))))
            .andExpect(status().isOk());

Dùng roles(...) khi security config dùng hasRole/hasAnyRole. Dùng authorities(...) khi config dùng quyền cụ thể như invoice:read, order:approve hoặc tenant:manage.

Lưu ý: user(...) và @WithMockUser thiết lập Authentication cho request/test. Chúng hữu ích để kiểm tra authorization. Chúng không xác nhận luồng đăng nhập thật, mật khẩu có được kiểm tra hay JWT có chữ ký hợp lệ hay không.

## 8. Phân biệt kiểm tra authorization và authentication thật

Có ba loại test khác nhau:

| Mục tiêu | Cách làm phù hợp |
| --- | --- |
| User có role/authority nào được gọi endpoint? | @WithMockUser hoặc request post-processor user(...). |
| HTTP Basic credentials được xác thực qua filter? | Dùng httpBasic(...) cùng AuthenticationManager/UserDetailsService và PasswordEncoder test thật hoặc cấu hình phù hợp. |
| Bearer token được parse, xác minh chữ ký và claims? | Gửi token qua Bearer filter; dùng JwtDecoder mock hoặc test key/token thực theo mục tiêu. |

Ví dụ kiểm tra HTTP Basic:

    @Test
    void validBasicCredentialsCanAccessEndpoint() throws Exception {
        mockMvc.perform(get("/api/profile")
                        .with(httpBasic("alice", "password")))
                .andExpect(status().isOk());
    }

Test này có ý nghĩa khi security chain được cấu hình HTTP Basic và AuthenticationManager có user/password phù hợp. Nếu chỉ dùng @WithMockUser, Basic authentication filter không được kiểm tra.

Với JWT resource server, request post-processor jwt() có thể tạo JwtAuthenticationToken để kiểm tra authorization theo claims và authorities:

    mockMvc.perform(get("/api/invoices")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority("invoice:read"))))
            .andExpect(status().isOk());

jwt() hữu ích để kiểm tra rule phân quyền dựa trên principal/claims đã được tạo. Nó không kiểm tra việc decode token, xác minh chữ ký, issuer, audience hoặc thời hạn token. Muốn kiểm tra những bước đó, cần gửi Bearer token qua filter chain với JwtDecoder phù hợp, có thể mock decoder ở test slice hoặc dùng test key/token thật trong test tích hợp.

## 9. CSRF: nguyên nhân phổ biến khiến POST/PUT/DELETE nhận 403

CSRF protection được bật mặc định trong nhiều cấu hình Spring Security cho ứng dụng servlet. Request thay đổi trạng thái như POST, PUT, PATCH và DELETE thường cần CSRF token hợp lệ. GET, HEAD, OPTIONS và TRACE được xem là safe method theo quy ước và thông thường không cần token.

Một test POST có thể trả 403 dù người dùng đã đăng nhập và có role đúng:

    @Test
    @WithMockUser(roles = "ADMIN")
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/api/admin/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isForbidden());
    }

Nếu mục tiêu của test là xác nhận controller tạo dữ liệu thành công, cần thêm CSRF token:

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanCreateUserWithCsrfToken() throws Exception {
        mockMvc.perform(post("/api/admin/users")
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isCreated());
    }

Static request post-processor csrf() được cung cấp bởi Spring Security Test. Nó thêm token hợp lệ theo cơ chế CSRF của test support.

Có thể kiểm tra token không hợp lệ:

    mockMvc.perform(post("/api/admin/users")
                    .with(csrf().useInvalidToken())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isForbidden());

Có thể gửi token dưới dạng header nếu ứng dụng/client sử dụng header:

    mockMvc.perform(post("/api/admin/users")
                    .with(csrf().asHeader())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isCreated());

Tên header mặc định phụ thuộc CsrfTokenRepository. Nếu ứng dụng dùng repository tùy chỉnh, cần cấu hình request post-processor hoặc request token theo đúng tên/header mà ứng dụng mong đợi.

Không nên tắt CSRF chỉ để làm test xanh nếu ứng dụng dùng session/cookie authentication và có nguy cơ CSRF. Với API stateless dùng Bearer token trong Authorization header, chính sách CSRF có thể khác; hãy cấu hình dựa trên cách trình duyệt gửi credentials và threat model của ứng dụng.

## 10. Phân biệt 403 do CSRF với 403 do quyền truy cập

Cả hai trường hợp đều có thể trả 403 nhưng nguyên nhân và cách sửa khác nhau.

| Dấu hiệu | CSRF từ chối | Thiếu quyền |
| --- | --- | --- |
| Request method | Thường là POST/PUT/PATCH/DELETE. | Có thể là bất kỳ method nào. |
| Authentication | Có thể đã đăng nhập và có role đúng. | Thường đã xác thực nhưng authority không đủ. |
| Token CSRF | Thiếu, sai hoặc không được gửi đúng vị trí. | Có thể hoàn toàn hợp lệ. |
| Rule URL/Method | Có thể cho phép user hiện tại. | Rule yêu cầu role/authority cao hơn. |
| Vị trí từ chối | CSRF filter trong filter chain. | Authorization filter hoặc method security. |
| Cách tái hiện | Bỏ token hoặc dùng token sai; sau đó thêm csrf() để so sánh. | Dùng user có authority thiếu; sau đó đổi sang role phù hợp. |

Một cách chẩn đoán hiệu quả là chạy hai request giống nhau, chỉ thay đổi một yếu tố:

1. Giữ nguyên user và payload, gửi POST không có CSRF token.
2. Gửi lại cùng request với csrf().
3. Nếu request thứ hai đi tiếp, lỗi ban đầu do CSRF.
4. Nếu request thứ hai vẫn nhận 403, kiểm tra URL authorization, method security và quyền theo dữ liệu.

Đừng thêm cả role mới, token mới và thay đổi payload trong cùng một lần thử. Khi chỉ thay đổi một yếu tố, nguyên nhân dễ được xác định hơn.

## 11. Method security có thể từ chối sau khi request đã tới controller

Một endpoint có thể được phép qua URL matcher nhưng method vẫn bị chặn bởi @PreAuthorize hoặc @PostAuthorize.

    @Service
    class InvoiceService {

        @PreAuthorize("hasAuthority('invoice:approve')")
        public void approve(long invoiceId) {
            // Business operation.
        }
    }

Cần bật method security trong cấu hình:

    @Configuration
    @EnableMethodSecurity
    class MethodSecurityConfig {
    }

Nếu user có thể truy cập URL nhưng thiếu invoice:approve, lời gọi service bị từ chối. Với MVC request, exception có thể được xử lý và trả 403 tùy cấu hình exception translation và nơi method được gọi.

Test:

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCannotApproveInvoice() throws Exception {
        mockMvc.perform(post("/api/invoices/42/approve")
                        .with(csrf()))
                .andExpect(status().isForbidden());
    }

Test này đã cung cấp CSRF token để không bị chặn ở CSRF filter; authority chỉ có invoice:read nên method security có thể từ chối thao tác approve.

Test cho quyền hợp lệ:

    @Test
    @WithMockUser(authorities = {"invoice:read", "invoice:approve"})
    void approverCanApproveInvoice() throws Exception {
        mockMvc.perform(post("/api/invoices/42/approve")
                        .with(csrf()))
                .andExpect(status().isNoContent());
    }

Nếu method security được kiểm tra ở service, cũng có thể viết unit/integration test trực tiếp cho service. MockMvc test bổ sung xác nhận toàn bộ request đi qua filter chain và controller trước khi method security được áp dụng.

## 12. Dữ liệu request có thể ảnh hưởng quyết định phân quyền

Không phải mọi 403 đều do role thiếu. Nhiều ứng dụng kiểm tra quyền dựa trên dữ liệu request:

- ID tài nguyên trong path thuộc về user khác.
- Tenant ID trong header hoặc token không khớp với tài nguyên.
- Organization ID trong request body không nằm trong phạm vi user.
- Owner ID, project ID hoặc account ID được tra cứu từ database.
- Trạng thái nghiệp vụ không cho phép user thực hiện hành động.
- ACL hoặc permission record của tài nguyên không cho phép thao tác.

Ví dụ service kiểm tra quyền sở hữu hóa đơn:

    @Service
    class InvoiceAccessService {

        private final InvoiceRepository repository;

        InvoiceAccessService(InvoiceRepository repository) {
            this.repository = repository;
        }

        @PreAuthorize("@invoiceAccessService.canRead(authentication, #invoiceId)")
        public Invoice findReadable(long invoiceId) {
            return repository.findById(invoiceId).orElseThrow();
        }

        public boolean canRead(Authentication authentication, long invoiceId) {
            Invoice invoice = repository.findById(invoiceId).orElse(null);
            if (invoice == null) {
                return false;
            }
            return invoice.getOwnerUsername().equals(authentication.getName());
        }
    }

Một user có thể có role USER nhưng chỉ được đọc hóa đơn do chính mình sở hữu. Nếu request tới /api/invoices/42 và hóa đơn 42 thuộc user khác, method security từ chối dù role của user là hợp lệ.

Khi test trường hợp này, phải kiểm soát cả principal và dữ liệu tài nguyên:

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void userCannotReadAnotherUsersInvoice() throws Exception {
        // Test fixture tạo invoice 42 thuộc về bob.
        mockMvc.perform(get("/api/invoices/42"))
                .andExpect(status().isForbidden());
    }

Nếu test không tạo dữ liệu invoice tương ứng, kết quả có thể là 404 hoặc lỗi khác thay vì 403. Điều đó không chứng minh authorization sai; nó có thể chỉ ra fixture không khớp với tình huống đang kiểm tra.

Cần phân biệt:
- Tài nguyên không tồn tại: thường là 404.
- Tài nguyên tồn tại nhưng user không có quyền: có thể là 403.
- Ứng dụng cố ý che giấu sự tồn tại của tài nguyên: có thể trả 404 thay vì 403.

Đây là quyết định bảo mật của ứng dụng và cần được kiểm tra theo hợp đồng đã chọn.

## 13. Dữ liệu request không hợp lệ thường không phải 401/403

Một payload sai cấu trúc, thiếu trường hoặc không vượt qua Bean Validation thường được xử lý ở tầng MVC và trả về 400 Bad Request hoặc status validation riêng của ứng dụng.

Ví dụ:
- JSON malformed: thường 400.
- Content-Type không được hỗ trợ: thường 415 Unsupported Media Type.
- Thiếu request parameter bắt buộc: thường 400.
- DTO vi phạm @Valid: thường 400 nếu exception handler mặc định hoặc cấu hình tương ứng.
- HTTP method không được hỗ trợ: thường 405.
- Mapping không tồn tại: thường 404.

Nếu nhận 401/403, hãy xem request có bị security filter từ chối trước khi binding hoặc validation hay không. Một request payload không hợp lệ không nhất thiết được controller nhìn thấy nếu filter chain đã từ chối nó trước.

Tuy nhiên, dữ liệu request có thể được dùng trong authorization. Ví dụ tenantId hoặc resourceId sai có thể dẫn đến 403. Vì vậy, hãy xác định dữ liệu nào là input cho binding/validation và dữ liệu nào là input cho access decision.

## 14. Cấu hình MockMvc đúng để test Spring Security

Một test dùng MockMvc chỉ xác nhận security filter chain nếu filter chain thực sự được đăng ký trong MockMvc.

### Spring Boot với @AutoConfigureMockMvc

    @SpringBootTest
    @AutoConfigureMockMvc
    class SecurityIntegrationTest {
        @Autowired
        MockMvc mockMvc;
    }

Trong cấu hình mặc định, Spring Boot thêm servlet filters vào MockMvc. Nếu test dùng thuộc tính addFilters = false, security filter chain sẽ không được áp dụng và các request có thể đi thẳng tới MVC.

### Tự tạo MockMvc từ WebApplicationContext

Khi tự build MockMvc, thêm Spring Security configurer:

    @Autowired
    WebApplicationContext context;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(context)
                .apply(springSecurity())
                .build();
    }

Configurers springSecurity() kết nối Spring Security filter chain với MockMvc. Nếu bỏ qua bước này, test có thể không tái hiện được 401/403 mà ứng dụng thật trả về.

### Standalone setup

standaloneSetup(controller) chỉ tạo MVC infrastructure quanh controller được chọn. Nó không tự động nạp toàn bộ security filter chain của ứng dụng. Nếu mục tiêu là chẩn đoán security config thực tế, ưu tiên webAppContextSetup hoặc Spring Boot test với filter chain đã được nạp.

Có thể thêm filter thủ công vào standalone MockMvc, nhưng khi đó test phải tự quản lý đầy đủ filter chain và thứ tự filter. Cách này dễ bỏ sót cấu hình production và chỉ phù hợp khi có lý do cụ thể.

## 15. Kiểm tra CORS và preflight request

Một số request từ browser bắt đầu bằng CORS preflight OPTIONS. Nếu security config không cho phép preflight hoặc CORS configuration không cho origin/method/header cần thiết, request có thể nhận 401/403 hoặc browser báo lỗi CORS.

Ví dụ preflight:

    mockMvc.perform(options("/api/reports")
                    .header("Origin", "https://app.example.test")
                    .header("Access-Control-Request-Method", "POST")
                    .header("Access-Control-Request-Headers", "content-type,authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin",
                    "https://app.example.test"));
    
Status và header thực tế phụ thuộc CORS configuration. Cần kiểm tra:

- Origin có nằm trong allowed origins không?
- Method POST có nằm trong allowed methods không?
- Header Authorization hoặc Content-Type có được cho phép không?
- CORS filter/processor có chạy trước phần security authorization phù hợp không?
- OPTIONS có bị yêu cầu authentication ngoài ý muốn không?

CORS là chính sách của browser. Một request bằng curl hoặc MockMvc không tái hiện hoàn toàn việc browser chặn response, nhưng có thể kiểm tra preflight response và header do server trả về.

## 16. Nhiều SecurityFilterChain và matcher không đúng

Ứng dụng có thể khai báo nhiều SecurityFilterChain, ví dụ một chain cho API và một chain cho form login. Spring chọn chain đầu tiên có securityMatcher phù hợp với request; các chain sau không tiếp tục áp dụng cho cùng request.

Ví dụ:

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

Nếu API request không khớp chain mong muốn, nó có thể rơi vào chain khác và nhận status hoặc redirect khác dự kiến.

Khi chẩn đoán, kiểm tra:
- securityMatcher của từng chain.
- @Order của các chain.
- URL thực tế, context path và servlet path.
- Chain nào là chain đầu tiên khớp request.
- Cơ chế authentication được cấu hình trong chain đó.

Đừng chỉ xem một đoạn authorizeHttpRequests; cần xem cả cấu trúc các SecurityFilterChain trong application context.

## 17. Bật log để tìm filter từ chối request

Khi không rõ filter nào trả 401/403, có thể bật log Spring Security trong profile test hoặc cấu hình chẩn đoán:

    logging.level.org.springframework.security=DEBUG

Log có thể cho biết:
- SecurityFilterChain nào được chọn.
- Request matcher nào được kiểm tra.
- Authentication được tạo hoặc thất bại ở đâu.
- Access decision bị từ chối do authority nào.
- CSRF filter phát hiện token thiếu hoặc sai.
- ExceptionTranslationFilter gọi AuthenticationEntryPoint hoặc AccessDeniedHandler.

Không nên bật DEBUG cho toàn bộ production nếu log có thể chứa thông tin nhạy cảm hoặc quá nhiều dữ liệu. Dùng profile test/dev và tắt sau khi chẩn đoán.

## 18. Checklist chẩn đoán 401/403

Khi MockMvc test hoặc API test nhận 401/403 ngoài dự kiến, đi theo trình tự:

1. Xác nhận HTTP method và URL chính xác mà test gửi.
2. Xác nhận MockMvc có gắn Spring Security filter chain hay không.
3. Xác định SecurityFilterChain đầu tiên khớp request.
4. Kiểm tra request có authentication hay chưa.
5. Nếu dùng Basic/Bearer, kiểm tra credentials/token, header và authentication filter.
6. Kiểm tra authority thực tế, phân biệt ROLE_ prefix với authority tùy chỉnh.
7. Kiểm tra request matcher theo method/path và thứ tự khai báo.
8. Với POST/PUT/PATCH/DELETE, kiểm tra CSRF token.
9. Kiểm tra method security như @PreAuthorize và @PostAuthorize.
10. Kiểm tra dữ liệu tài nguyên, owner, tenant hoặc ACL có ảnh hưởng quyết định truy cập.
11. Kiểm tra CORS preflight nếu lỗi chỉ xảy ra trên browser.
12. Đọc response header/body và security log để xác định entry point hoặc access denied handler.

## 19. Những lỗi thường gặp trong test

**Dùng @WithMockUser nhưng vẫn nhận 403 ở POST.**

User đã được xác thực, nhưng request vẫn thiếu CSRF token. Thêm .with(csrf()) nếu test cần gửi request hợp lệ qua CSRF filter.

**Dùng roles("ADMIN") nhưng vẫn bị từ chối.**

Kiểm tra endpoint dùng hasRole("ADMIN") hay hasAuthority("ADMIN")/hasAuthority("ROLE_ADMIN"). roles(...) tự thêm prefix ROLE_; authorities(...) không thêm.

**Test nhận 200 trong khi ứng dụng thật nhận 401.**

Có thể MockMvc không đăng ký security filters, hoặc test dùng standaloneSetup. Dùng webAppContextSetup(...).apply(springSecurity()) hoặc cấu hình Boot giữ filter chain.

**Dùng @Mock cho service rồi nghĩ đã thay bean trong Spring context.**

@Mock chỉ tạo mock trong test instance. Nó không tự thay thế bean mà controller được inject. Dùng @MockitoBean/@MockBean theo version hoặc cấu hình test bean phù hợp.

**Thêm role mới để sửa lỗi CSRF.**

CSRF là kiểm tra token, không phải role authorization. Thêm role không giải quyết request thiếu token.

**Nhận 404 thay vì 403 khi kiểm tra quyền sở hữu.**

Tài nguyên có thể chưa được tạo trong fixture hoặc ứng dụng chủ động che giấu tài nguyên không thuộc quyền truy cập. Chuẩn bị dữ liệu đúng và xác nhận hợp đồng 404/403 của ứng dụng.

**Kiểm tra JWT bằng jwt() rồi kết luận token thật hợp lệ.**

jwt() tạo Authentication giả lập cho authorization. Nó không xác minh chữ ký, issuer, audience hoặc expiration của token thật.

**Chỉ sửa controller khi security filter đã chặn request.**

Nếu controller chưa được gọi, thay đổi validation hoặc mapping trong controller không giải quyết nguyên nhân. Tìm filter, matcher, CSRF hoặc authentication entry point đã từ chối request.

## 20. Quy trình kiểm thử theo từng nguyên nhân

Có thể tổ chức test thành các nhóm nhỏ:

| Nhóm test | Request setup | Kết quả mong đợi |
| --- | --- | --- |
| Anonymous | Không có authentication | 401 hoặc redirect login theo cấu hình. |
| Authenticated nhưng thiếu role | user("alice").roles("USER") | 403 ở endpoint yêu cầu ADMIN. |
| Có role phù hợp | user("admin").roles("ADMIN") | 2xx theo endpoint. |
| POST thiếu CSRF | User hợp lệ, không có csrf() | 403 khi CSRF đang bật. |
| POST có CSRF | User hợp lệ và csrf() | Request qua CSRF; kết quả phụ thuộc quyền và dữ liệu. |
| Token/credentials không hợp lệ | Gửi credentials/token sai qua filter thật | 401 theo authentication entry point. |
| Không sở hữu tài nguyên | User hợp lệ, resource thuộc user khác | 403 hoặc 404 theo chính sách ứng dụng. |
| Payload không hợp lệ | Authentication và quyền hợp lệ, body sai | Thường 400/415, không phải 401/403. |

Giữ mỗi test tập trung vào một nguyên nhân. Ví dụ, khi kiểm tra CSRF, cung cấp user có đủ role và payload hợp lệ; khi kiểm tra role, cung cấp CSRF token hợp lệ cho request POST. Điều này giúp test không bị một lớp bảo mật khác chặn trước lớp đang muốn kiểm tra.

## Kết luận

401 và 403 thường xuất hiện khi request bị từ chối ở Spring Security filter chain hoặc method security. 401 thường liên quan đến authentication chưa hợp lệ; 403 thường liên quan đến authority, CSRF hoặc quyền truy cập tài nguyên. Tuy nhiên, status thực tế phụ thuộc entry point, access denied handler và chính sách của ứng dụng.

Để chẩn đoán bằng MockMvc, bảo đảm security filters thực sự được gắn vào test, sau đó kiểm tra method/path, authentication, authority, CSRF token, method security và dữ liệu owner/tenant/ACL. Dùng @WithMockUser hoặc user(...) cho authorization test; dùng Basic/Bearer flow thật khi cần kiểm tra authentication. Phân biệt lỗi bảo mật với lỗi binding/validation để sửa đúng lớp chịu trách nhiệm.
