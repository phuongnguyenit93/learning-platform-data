# Phản hồi 401, 403 và kiểm thử truy cập không được phép

Khi Spring Data REST công bố repository thành REST API, Spring Security có thể bảo vệ collection resource, item resource, search endpoint và association resource. Khi client gọi endpoint mà không đủ điều kiện truy cập, API cần trả về phản hồi phù hợp và có thể kiểm thử được.

Hai status thường gặp là:

- **401 Unauthorized**: request chưa được xác thực hợp lệ. Client cần cung cấp hoặc làm mới thông tin xác thực.
- **403 Forbidden**: request đã có danh tính được xác thực, nhưng người dùng không có quyền thực hiện thao tác.

Tên “Unauthorized” của 401 dễ gây nhầm. Theo HTTP semantics, 401 nói về việc thiếu hoặc không chấp nhận thông tin xác thực; 403 nói rằng server hiểu request nhưng từ chối thực hiện. Với API dùng HTTP Basic, 401 thường đi kèm header **WWW-Authenticate** để client biết cơ chế xác thực.

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt 401, 403 và các status liên quan như 404.
- Hiểu vai trò của AuthenticationEntryPoint, AccessDeniedHandler và ExceptionTranslationFilter.
- Bảo vệ endpoint Spring Data REST bằng URL authorization và method security.
- Trả JSON nhất quán cho lỗi xác thực và lỗi phân quyền.
- Kiểm thử anonymous user, credentials sai, user thiếu authority và user có quyền bằng MockMvc.
- Phân biệt lỗi authorization với lỗi CSRF và CORS.
- Tránh để response lỗi tiết lộ thông tin nội bộ.

## 1. Phân biệt 401 và 403

| Tình huống | Phản hồi thường dùng | Ý nghĩa |
| --- | --- | --- |
| Không gửi credentials tới endpoint cần đăng nhập | 401 | Client chưa được xác thực |
| Gửi username/password hoặc token không hợp lệ | 401 | Credentials bị từ chối |
| Đã đăng nhập nhưng thiếu role/authority | 403 | Danh tính hợp lệ nhưng không được phép |
| Đã đăng nhập nhưng thao tác bị cấm theo policy | 403 | Authorization từ chối request |
| Resource không tồn tại | 404 | Không tìm thấy resource |
| API cố ý che giấu sự tồn tại của resource | Có thể dùng 404 | Chính sách bảo mật không tiết lộ resource có tồn tại hay không |

401 và 403 là hai kết quả khác nhau của quá trình bảo vệ endpoint. Không nên trả 401 cho mọi lỗi vì client có thể hiểu nhầm rằng chỉ cần đăng nhập lại là được phép. Cũng không nên trả 403 cho mọi request thiếu credentials khi API đang dùng HTTP authentication challenge.

### 1.1. Ví dụ với Spring Data REST

Giả sử repository được export dưới path /orders:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

Một client chưa đăng nhập gọi:

~~~http
GET /orders
Accept: application/hal+json
~~~

Nếu endpoint yêu cầu authentication, server trả 401.

Một người dùng đã đăng nhập nhưng chỉ có quyền đọc gọi:

~~~http
DELETE /orders/42
Authorization: Basic ...
~~~

Nếu thao tác xóa yêu cầu authority riêng, server trả 403.

Nếu người dùng có quyền xóa nhưng order 42 không tồn tại, response có thể là 404. Không nên nhầm resource không tồn tại với resource tồn tại nhưng người dùng không được phép truy cập.

### 1.2. Header WWW-Authenticate

Khi trả 401 theo HTTP authentication challenge, server phải cho client biết cơ chế xác thực thông qua header WWW-Authenticate.

Ví dụ với Basic authentication:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/problem+json
~~~

Client có thể dựa vào challenge để gửi credentials. Nếu viết custom AuthenticationEntryPoint, hãy bảo đảm response vẫn có challenge phù hợp với authentication scheme đang sử dụng.

Với Bearer token, challenge thường có scheme Bearer và có thể chứa thuộc tính error theo RFC 6750. Không trả Basic challenge nếu API thực tế chỉ chấp nhận Bearer token.

## 2. Spring Security xử lý lỗi ở đâu?

Trong Servlet security filter chain, **ExceptionTranslationFilter** chuyển các exception bảo mật thành HTTP response phù hợp. Filter này không tự quyết định user có quyền hay không; nó chuyển tiếp kết quả từ authentication và authorization components.

Luồng tổng quát:

~~~text
HTTP request
    |
    v
SecurityFilterChain
    |
    v
Authentication / Authorization
    |
    +--> AuthenticationException
    |        |
    |        v
    |   AuthenticationEntryPoint
    |        |
    |        v
    |      401 / login challenge
    |
    +--> AccessDeniedException
             |
             v
       Kiểm tra Authentication
             |
             +--> Anonymous / chưa đủ xác thực
             |        |
             |        v
             |   AuthenticationEntryPoint
             |        |
             |        v
             |       401
             |
             +--> Đã xác thực
                      |
                      v
                AccessDeniedHandler
                      |
                      v
                     403
~~~

Quy tắc quan trọng:

- **AuthenticationEntryPoint** bắt đầu quá trình xác thực khi request chưa có authentication hợp lệ hoặc cần challenge.
- **AccessDeniedHandler** xử lý trường hợp user đã xác thực nhưng bị từ chối quyền.
- ExceptionTranslationFilter là cầu nối giữa exception bảo mật và HTTP response.
- Một số authentication mechanism có thể tự gọi entry point khi credentials sai, ví dụ BasicAuthenticationFilter.

Người dùng anonymous truy cập resource cần bảo vệ thường được chuyển tới AuthenticationEntryPoint. Nếu user đã đăng nhập nhưng thiếu quyền, AccessDeniedHandler được gọi.

## 3. Cấu hình authorization cho Spring Data REST

Spring Data REST công bố nhiều loại endpoint. Cần quyết định quyền cho từng nhóm resource:

- Collection resource: /orders.
- Item resource: /orders/{id}.
- Search resource: /orders/search và các query method bên dưới.
- Association resource: /orders/{id}/customer, /orders/{id}/items.
- Các repository resource khác như customers, products hoặc accounts.

Ví dụ dùng request authorization theo HTTP method:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    HttpMethod.GET,
                    "/orders/**"
                ).hasAuthority("ORDER_READ")
                .requestMatchers(
                    HttpMethod.POST,
                    "/orders/**"
                ).hasAuthority("ORDER_CREATE")
                .requestMatchers(
                    HttpMethod.PUT,
                    "/orders/**"
                ).hasAuthority("ORDER_UPDATE")
                .requestMatchers(
                    HttpMethod.PATCH,
                    "/orders/**"
                ).hasAuthority("ORDER_UPDATE")
                .requestMatchers(
                    HttpMethod.DELETE,
                    "/orders/**"
                ).hasAuthority("ORDER_DELETE")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ví dụ này minh họa chính sách cho repository path /orders. Cần điều chỉnh matcher theo base path và endpoint thực tế của ứng dụng.

Lưu ý:

- Matcher được đánh giá theo thứ tự khai báo; rule cụ thể phải đứng trước rule tổng quát.
- /orders/** bao phủ cả item và các path con như search/association.
- hasAuthority("ORDER_READ") so khớp authority đúng tên.
- hasRole("ADMIN") mặc định kiểm tra authority ROLE_ADMIN.
- anyRequest().authenticated() yêu cầu đăng nhập cho các request còn lại; nếu có endpoint công khai, khai báo permitAll() trước rule này.
- Đừng chỉ ẩn link trong HAL. Link không xuất hiện không thay thế authorization ở server.

Nếu ứng dụng có base path như /api, matcher phải dùng đường dẫn thực tế, ví dụ /api/orders/**. Nếu dùng nhiều SecurityFilterChain, cần kiểm tra chain nào match request và thứ tự chain.

## 4. Bảo vệ repository method bằng method security

Spring Data REST cũng hỗ trợ Spring Security method-level authorization trên repository. Cách này hữu ích khi quyền gắn với thao tác repository cụ thể.

Bật method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Áp dụng quyền ở repository:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('ORDER_READ')")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Override
    @PreAuthorize("hasAuthority('ORDER_READ')")
    Page<Order> findAll(Pageable pageable);

    @Override
    @PreAuthorize("hasAuthority('ORDER_DELETE')")
    void deleteById(Long id);

    @Override
    @PreAuthorize("hasAuthority('ORDER_DELETE')")
    void delete(Order order);
}
~~~

Ví dụ cho thấy method-level rule có thể kiểm soát thao tác riêng. Với repository thực tế, hãy kiểm kê tất cả method và overload mà REST exporter có thể gọi.

Theo tài liệu Spring Data REST, annotation bảo mật ở cấp repository và method **không tự cộng dồn**; method-level annotation ghi đè rule ở cấp repository cho method đó. Nếu cần rule riêng cho delete, phải override các method delete tương ứng và đặt annotation trên từng method.

Tài liệu Spring Data REST nêu rõ CrudRepository có nhiều delete method. Chỉ bảo vệ deleteById không có nghĩa mọi đường xóa khác đều đã được bảo vệ. Kiểm tra các chữ ký như delete(entity), deleteAll(iterable), deleteAll() và các overload có trong interface/version đang dùng.

### 4.1. Request authorization và method security

| Cơ chế | Phạm vi | Ví dụ |
| --- | --- | --- |
| URL/request authorization | Quyết định theo HTTP method và path | GET /orders cần ORDER_READ |
| Repository method security | Quyết định khi repository method được gọi | deleteById cần ORDER_DELETE |
| Service method security | Bảo vệ nghiệp vụ dùng chung từ REST, batch hoặc message consumer | closeAccount cần ACCOUNT_CLOSE |
| Domain rule | Xác nhận trạng thái nghiệp vụ hợp lệ | Chỉ được thanh toán order đang PENDING |

Có thể kết hợp request authorization với method security. Request authorization chặn sớm theo path/method; method security bảo vệ thao tác ở tầng repository hoặc service khi được gọi từ entry point khác.

Không coi method security là thay thế cho business rule. Người có quyền ORDER_UPDATE vẫn không được chuyển một order sang trạng thái bất hợp lệ nếu domain rule cấm.

## 5. Tùy chỉnh phản hồi 401 bằng AuthenticationEntryPoint

Với REST API, client thường cần JSON thay vì trang HTML hoặc redirect đến form login.

Có thể triển khai AuthenticationEntryPoint để tạo response thống nhất:

~~~java
@Component
public class ApiAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final ObjectMapper objectMapper;

    public ApiAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setHeader(
            HttpHeaders.WWW_AUTHENTICATE,
            "Basic realm=\"api\""
        );
        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Unauthorized",
                "status", 401,
                "detail", "Authentication is required."
            )
        );
    }
}
~~~

Response ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required."
}
~~~

Nếu API dùng Bearer token, thay challenge header theo scheme đó. Không đưa password, token, stack trace hoặc lý do nội bộ chi tiết vào response.

Với form login, AuthenticationEntryPoint mặc định có thể redirect user tới trang đăng nhập và trả 302. Đó là hành vi phù hợp cho browser flow nhưng có thể không phù hợp với REST client mong đợi JSON 401. Hãy cấu hình entry point theo loại client và authentication scheme.

## 6. Tùy chỉnh phản hồi 403 bằng AccessDeniedHandler

AccessDeniedHandler xử lý request đã xác thực nhưng không có quyền:

~~~java
@Component
public class ApiAccessDeniedHandler
        implements AccessDeniedHandler {

    private final ObjectMapper objectMapper;

    public ApiAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception) throws IOException {

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Forbidden",
                "status", 403,
                "detail", "You do not have permission to perform this action."
            )
        );
    }
}
~~~

Response ví dụ:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action."
}
~~~

Thông điệp nên đủ rõ để client hiểu thao tác bị từ chối, nhưng không tiết lộ quyền nội bộ, tên policy, cấu trúc dữ liệu hoặc thông tin về người dùng khác.

### 6.1. Đăng ký hai handler

Có thể đưa hai handler vào SecurityFilterChain:

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(
            HttpSecurity http,
            ApiAuthenticationEntryPoint entryPoint,
            ApiAccessDeniedHandler deniedHandler) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/orders/**")
                    .hasAuthority("ORDER_READ")
                .anyRequest().authenticated()
            )
            .httpBasic(basic ->
                basic.authenticationEntryPoint(entryPoint)
            )
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
            );

        return http.build();
    }
}
~~~

Đăng ký entry point cả ở cấu hình HTTP Basic và exception handling giúp xử lý nhất quán challenge khi thiếu hoặc sai Basic credentials và khi ExceptionTranslationFilter cần bắt đầu authentication.

Nếu ứng dụng dùng nhiều authentication mechanism, hãy cấu hình handler phù hợp cho từng filter/chain thay vì áp dụng một Basic challenge cho tất cả request.

## 7. Kiểm thử 401 và 403 bằng MockMvc

Spring Security cung cấp tích hợp với Spring MVC Test thông qua dependency spring-security-test. Khi dùng Spring Boot, cấu hình phổ biến là:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityIntegrationTest {

    @Autowired
    private MockMvc mockMvc;
}
~~~

Với MockMvc tự dựng từ WebApplicationContext, áp dụng springSecurity() để đăng ký security filters và test support:

~~~java
mockMvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

### 7.1. Anonymous user nhận 401

Không gắn user hoặc credentials vào request:

~~~java
@Test
void anonymousCannotReadOrders() throws Exception {
    mockMvc.perform(
            get("/orders")
                .accept(MediaTypes.HAL_JSON)
        )
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Basic")
        ));
}
~~~

Test này giả định API cấu hình HTTP Basic và entry point trả 401 kèm Basic challenge. Nếu dùng Bearer token, kiểm tra challenge tương ứng. Nếu dùng form login, cấu hình mặc định có thể redirect thay vì trả 401.

### 7.2. Credentials sai nhận 401

Nếu muốn kiểm tra authentication manager thực sự xác minh username/password, gửi Basic credentials sai:

~~~java
@Test
void invalidBasicCredentialsAreRejected() throws Exception {
    mockMvc.perform(
            get("/orders")
                .with(httpBasic("alice", "wrong-password"))
        )
        .andExpect(status().isUnauthorized());
}
~~~

Test này kiểm tra luồng authentication thực. Nó khác với @WithMockUser, vốn tạo Authentication giả trong SecurityContext và không xác minh password.

### 7.3. User đã xác thực nhưng thiếu quyền nhận 403

Dùng user có authority đọc nhưng gọi endpoint yêu cầu quyền xóa:

~~~java
@Test
@WithMockUser(
    username = "alice",
    authorities = "ORDER_READ"
)
void readerCannotDeleteOrder() throws Exception {
    mockMvc.perform(
            delete("/orders/42")
                .with(csrf())
        )
        .andExpect(status().isForbidden());
}
~~~

@WithMockUser tạo principal cho test. Authority được khai báo phải khớp với rule đang cấu hình. Nếu dùng hasRole("ADMIN"), hãy dùng roles = "ADMIN"; nếu dùng hasAuthority("ORDER_DELETE"), hãy dùng authorities = "ORDER_DELETE".

### 7.4. User có quyền được phép

Kiểm tra quyền hợp lệ để bảo đảm rule không chặn nhầm:

~~~java
@Test
@WithMockUser(
    username = "admin",
    authorities = "ORDER_DELETE"
)
void userWithDeleteAuthorityCanDeleteOrder() throws Exception {
    mockMvc.perform(
            delete("/orders/42")
                .with(csrf())
        )
        .andExpect(status().isNoContent());
}
~~~

Status và dữ liệu test phụ thuộc endpoint, repository và cấu hình response của ứng dụng. Chuẩn bị dữ liệu trước test và xác nhận trạng thái persistence sau thao tác nếu cần kiểm tra cả kết quả nghiệp vụ.

### 7.5. Kiểm tra response body tùy chỉnh

Nếu dùng Problem Details JSON, kiểm tra cả status, content type và trường body:

~~~java
@Test
@WithMockUser(authorities = "ORDER_READ")
void forbiddenResponseUsesProblemJson() throws Exception {
    mockMvc.perform(delete("/orders/42").with(csrf()))
        .andExpect(status().isForbidden())
        .andExpect(content().contentType(
            MediaType.APPLICATION_PROBLEM_JSON
        ))
        .andExpect(jsonPath("$.status").value(403))
        .andExpect(jsonPath("$.title").value("Forbidden"));
}
~~~

Kiểm thử contract response giúp client xử lý lỗi nhất quán mà không phụ thuộc thông báo exception nội bộ.

## 8. Phân biệt lỗi authorization với lỗi CSRF

Một request POST, PUT, PATCH hoặc DELETE có thể nhận 403 vì **CSRF protection**, ngay cả khi user đã đăng nhập và có authority phù hợp.

CSRF filter kiểm tra token cho request không an toàn khi cơ chế CSRF đang bật. Nếu token thiếu hoặc không hợp lệ, request bị từ chối trước khi logic authorization của endpoint được thực hiện.

Trong MockMvc test, thêm token hợp lệ để kiểm tra riêng quyền:

~~~java
mockMvc.perform(
    post("/orders")
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("ORDER_CREATE")
        ))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"customerName":"An","status":"NEW"}
        """)
);
~~~

Kiểm thử CSRF riêng:

~~~java
@Test
@WithMockUser(authorities = "ORDER_CREATE")
void postWithoutCsrfTokenIsForbidden() throws Exception {
    mockMvc.perform(
            post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"customerName":"An","status":"NEW"}
                """)
        )
        .andExpect(status().isForbidden());
}
~~~

Khi test 403 trên DELETE hoặc POST:

- Nếu mục tiêu là kiểm tra role/authority, thêm .with(csrf()) khi CSRF đang bật.
- Nếu mục tiêu là kiểm tra CSRF, cố ý bỏ token hoặc gửi token sai.
- Đọc response/log để xác định filter nào từ chối request.
- Không tắt CSRF toàn cục chỉ để làm cho test pass.

Chỉ cân nhắc tắt hoặc bỏ qua CSRF cho một API chain khi authentication không dựa vào credentials tự động do browser gửi, ví dụ Bearer token trong Authorization header, và threat model của ứng dụng cho phép. Nếu browser gửi session cookie hoặc Basic credentials tự động, CSRF vẫn cần được xem xét.

## 9. CORS và OPTIONS preflight

Browser có thể gửi CORS preflight bằng method OPTIONS trước request thực. Nếu preflight bị authentication filter chặn, browser có thể báo lỗi CORS dù request thật chưa được gửi.

Cần cấu hình CORS ở server với origin, method và header được cho phép. Nếu policy yêu cầu, OPTIONS preflight có thể được xử lý trước authorization của endpoint. Không mở mọi OPTIONS hoặc mọi origin một cách tùy tiện.

CORS không thay thế authentication hoặc authorization. Nó là chính sách cho browser kiểm soát việc JavaScript từ origin khác có thể đọc response hay không; client ngoài browser vẫn có thể gọi API trực tiếp.

## 10. Khi nào nên trả 404 thay cho 403?

Một số API không muốn tiết lộ rằng resource tồn tại nhưng người gọi không có quyền. Trong trường hợp đó, ứng dụng có thể chủ động trả 404 cho cả “không tồn tại” và “không được phép xem”.

Đây là chính sách che giấu thông tin, không phải cách hiểu mặc định của 403. Chỉ dùng khi có yêu cầu bảo mật rõ ràng và áp dụng nhất quán cho collection, item, association và query endpoint liên quan.

Nếu API luôn trả 404 cho tài nguyên bị cấm, client không thể phân biệt resource không tồn tại với resource bị che giấu. Điều đó có thể ảnh hưởng UX, retry và hỗ trợ vận hành. Hãy quyết định theo threat model và hợp đồng API.

## 11. Kiểm thử đầy đủ các trường hợp truy cập

Một bộ integration test cho Spring Data REST nên có tối thiểu:

| Test case | Principal | Request | Kết quả mong đợi |
| --- | --- | --- | --- |
| Không có credentials | Anonymous | GET collection được bảo vệ | 401 |
| Credentials sai | Không xác thực được | GET collection được bảo vệ | 401 |
| Có quyền đọc | ORDER_READ | GET collection/item/search | 2xx nếu resource tồn tại |
| Chỉ có quyền đọc | ORDER_READ | DELETE item | 403 |
| Có quyền xóa | ORDER_DELETE | DELETE item | 2xx theo contract nếu resource tồn tại |
| Có quyền tạo nhưng thiếu CSRF | ORDER_CREATE | POST khi CSRF bật | 403 do CSRF |
| Có quyền tạo và CSRF hợp lệ | ORDER_CREATE | POST | 2xx theo contract |
| Có quyền nhưng item không tồn tại | Authority phù hợp | GET hoặc DELETE item không tồn tại | 404 hoặc status theo contract |
| Truy cập association không được phép | Thiếu authority tương ứng | GET/PUT/POST/DELETE association | 401 hoặc 403 theo authentication state và policy |

Ngoài status code, nên kiểm tra:

- Header WWW-Authenticate với 401.
- Content-Type và cấu trúc JSON lỗi.
- Không có stack trace, password, token hoặc thông tin nhạy cảm trong response.
- HAL link discovery không làm lộ dữ liệu không được phép.
- Gọi trực tiếp URL đã biết vẫn bị server kiểm soát.
- Collection, item, search và association đều được bảo vệ.
- Các thao tác qua service/repository khác vẫn tuân theo method security nếu chúng dùng chung nghiệp vụ.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| API trả 302 thay vì 401 | Form login entry point redirect tới trang đăng nhập | Cấu hình entry point phù hợp cho REST client |
| Anonymous request trả 403 | CSRF filter hoặc filter khác từ chối trước authentication entry point | Kiểm tra method, CSRF token và filter chain |
| User đã đăng nhập vẫn nhận 403 | Authority/role không khớp, role prefix sai hoặc method security từ chối | Kiểm tra SecurityContext, GrantedAuthority và expression |
| User có quyền đọc nhưng không xóa được | Rule DELETE yêu cầu authority khác | Cấp đúng quyền hoặc điều chỉnh policy |
| @PreAuthorize không có tác dụng | Chưa bật @EnableMethodSecurity hoặc method call không đi qua proxy | Bật method security và kiểm tra cách gọi bean/proxy |
| Repository-level rule bị ghi đè | Method-level annotation có precedence riêng | Kiểm tra và khai báo rule trên từng method override |
| Một delete method được bảo vệ nhưng overload khác vẫn xóa được | Chỉ override một chữ ký delete | Kiểm kê và bảo vệ toàn bộ delete overload được export |
| Response 401 thiếu WWW-Authenticate | Custom AuthenticationEntryPoint không đặt challenge header | Thêm challenge đúng scheme hoặc dùng entry point chuẩn |
| Response 403 tiết lộ policy nội bộ | Body dùng nguyên exception message hoặc stack trace | Trả thông điệp tổng quát, log chi tiết ở server |
| Test DELETE luôn 403 | CSRF token thiếu, không phải lỗi role | Thêm .with(csrf()) khi test authorization |
| Test dùng @WithMockUser nhưng production Basic vẫn lỗi | Mock user bỏ qua authentication manager/password validation | Bổ sung test credentials thực bằng httpBasic hoặc token tương ứng |
| Link HAL bị ẩn nhưng endpoint vẫn gọi được | Chỉ giấu link ở representation, chưa cấu hình authorization | Bảo vệ request ở server filter chain hoặc method security |
| OPTIONS nhận 401/403 và browser báo CORS | Preflight không được xử lý đúng | Cấu hình CORS/preflight phù hợp với policy |

## 13. Quy trình triển khai

1. Liệt kê các repository path và endpoint Spring Data REST đang công bố.
2. Xác định quyền cần cho GET, POST, PUT, PATCH, DELETE và association operations.
3. Cấu hình request authorization với matcher cụ thể theo HTTP method/path.
4. Bật @EnableMethodSecurity nếu cần bảo vệ repository hoặc service method.
5. Kiểm tra các overload CRUD; không giả định một method override bảo vệ mọi đường gọi.
6. Chọn authentication scheme và AuthenticationEntryPoint phù hợp với API client.
7. Cấu hình AccessDeniedHandler để trả 403 nhất quán.
8. Giữ challenge header WWW-Authenticate đúng scheme khi trả 401.
9. Xác định CSRF và CORS policy theo loại client.
10. Viết MockMvc integration test cho anonymous, credentials sai, thiếu authority, đủ authority và CSRF.
11. Kiểm tra response status, header, JSON body và dữ liệu sau thao tác.
12. Kiểm tra log server để chẩn đoán, nhưng không đưa chi tiết nội bộ vào response cho client.

## 14. Checklist nhanh

- [ ] Anonymous request tới endpoint cần authentication trả 401 theo API contract.
- [ ] 401 có WWW-Authenticate challenge phù hợp với scheme.
- [ ] Credentials sai được kiểm thử riêng.
- [ ] User đã xác thực nhưng thiếu authority nhận 403.
- [ ] User có authority phù hợp được phép thực hiện thao tác.
- [ ] Request authorization bao phủ collection, item, search và association resource.
- [ ] Method security được bật nếu repository/service dùng @PreAuthorize.
- [ ] Các overload delete và method override đã được kiểm tra.
- [ ] CSRF token được gửi trong test authorization cho POST/PUT/PATCH/DELETE khi CSRF bật.
- [ ] CSRF failure được kiểm thử riêng.
- [ ] CORS preflight được cấu hình mà không mở rộng quyền API quá mức.
- [ ] Response lỗi không chứa stack trace hoặc thông tin xác thực.
- [ ] Đã kiểm thử trực tiếp URL, không chỉ kiểm tra link HAL.
- [ ] Đã kiểm tra 404 và chính sách che giấu resource nếu ứng dụng áp dụng.

## 15. Ghi nhớ

- **401**: client chưa được xác thực hoặc credentials không hợp lệ; API cần challenge đúng authentication scheme.
- **403**: client đã được xác thực nhưng thiếu quyền thực hiện thao tác.
- **AuthenticationEntryPoint** xử lý việc bắt đầu/challenge authentication.
- **AccessDeniedHandler** xử lý quyền truy cập bị từ chối đối với user đã xác thực.
- **ExceptionTranslationFilter** chuyển exception bảo mật thành HTTP response.
- **Request authorization** bảo vệ path và HTTP method; **method security** bảo vệ repository/service operation.
- Khi test POST/PUT/PATCH/DELETE với CSRF bật, phải thêm token hợp lệ để kiểm tra riêng authorization.
- Kiểm tra cả status, header, response body và tác động dữ liệu.

## Tài liệu tham khảo

- Spring Data REST Reference — Security: https://docs.spring.io/spring-data/rest/reference/security.html
- Spring Security Reference — Exception Translation: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security API — AuthenticationEntryPoint: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
- Spring Security API — AccessDeniedHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandler.html
- Spring Security Reference — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security Reference — Running a Test as a User: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html
- Spring Security Reference — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- RFC 9110 — HTTP Semantics, 401 and 403: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
