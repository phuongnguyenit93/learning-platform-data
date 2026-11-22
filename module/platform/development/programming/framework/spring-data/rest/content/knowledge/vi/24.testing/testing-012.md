# Kiểm tra phân quyền, CSRF và CORS bằng Spring Security Test

Spring Data REST tự động công khai các repository thành REST endpoint, nhưng việc endpoint xuất hiện trên HTTP không có nghĩa mọi người dùng đều được phép truy cập. API cần xác định ai được đọc, tạo, sửa hoặc xóa resource; request ghi có cần CSRF token hay không; và frontend ở origin khác được phép gọi những đường dẫn nào.

Spring Security Test giúp kiểm tra các quy tắc đó ngay ở mức HTTP bằng MockMvc. Bài này trình bày cách chuẩn bị test, giả lập người dùng và quyền, kiểm tra CSRF token, gửi CORS preflight và xác nhận các request bị từ chối.

## 1. Phân biệt authentication, authorization, CSRF và CORS

Bốn khái niệm này giải quyết các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Request thuộc về ai? | Session, HTTP Basic, JWT |
| Authorization | Người đó được làm gì? | ROLE_READER được GET, ROLE_ADMIN được POST |
| CSRF protection | Request thay đổi dữ liệu có được gửi từ một trang khác lợi dụng credentials tự động đính kèm hay không? | POST phải có CSRF token hợp lệ |
| CORS | Browser có được phép cho JavaScript ở origin này đọc response từ API không? | Cho phép https://app.example.com gọi API |

Không dùng một cơ chế để thay thế cơ chế khác:

- CORS không xác thực người dùng và không phân quyền endpoint.
- CSRF không quyết định người dùng có role phù hợp hay không.
- Authentication thành công không có nghĩa request được phép thực hiện thao tác.
- Một request bị browser chặn đọc response do CORS vẫn có thể đã đến server và gây side effect nếu server xử lý request đó.

Đặc biệt, CORS là chính sách do browser thực thi. Một lệnh curl hoặc một service backend gọi API không bị browser áp dụng CORS. Vì vậy, CORS không phải hàng rào bảo vệ API trước mọi client.

## 2. Chuẩn bị Spring Security Test

Trong ứng dụng Spring Boot, dependency test thường được khai báo như sau:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-rest")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

Dùng dependency version được quản lý bởi Spring Boot dependency management để tránh trộn các phiên bản Spring Security không tương thích.

Các thành phần quan trọng của Spring Security Test:

- @WithMockUser: tạo SecurityContext với một user giả lập cho test.
- @WithUserDetails: tải user từ UserDetailsService thực tế.
- user() và anonymous(): gắn user hoặc anonymous principal vào từng request MockMvc.
- csrf(): tạo CSRF token hợp lệ hoặc token không hợp lệ.
- jwt(): giả lập JWT authentication khi ứng dụng dùng OAuth2 Resource Server.
- springSecurity(): tích hợp Spring Security filter chain vào MockMvc khi tự dựng MockMvc thủ công.

Với test dùng @SpringBootTest và @AutoConfigureMockMvc, Spring Boot thường cấu hình MockMvc cùng filter chain trong application context. Nếu tự dựng MockMvc bằng MockMvcBuilders, phải áp dụng Spring Security configurer để các filter được chạy trong test.

Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerSecurityIntegrationTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

Test tích hợp nên dùng cấu hình bảo mật thực tế của ứng dụng. Nếu chỉ test một controller bằng standalone MockMvc mà không gắn Security filter chain, kết quả không chứng minh endpoint được bảo vệ đúng trong ứng dụng đang chạy.

## 3. Khai báo quy tắc phân quyền cho Spring Data REST

Giả sử repository công khai resource tại /customers và item resource tại /customers/{id}. Một quy tắc minh họa:

- READER được GET danh sách và chi tiết.
- ADMIN được GET, POST, PUT, PATCH và DELETE.
- Người chưa xác thực không được truy cập các endpoint cần đăng nhập.

~~~java
@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/customers", "/customers/**")
                    .hasAnyRole("READER", "ADMIN")
                .requestMatchers(HttpMethod.POST,
                    "/customers", "/customers/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.PUT,
                    "/customers/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.PATCH,
                    "/customers/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.DELETE,
                    "/customers/**")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là cấu hình minh họa cho một API dùng HTTP Basic. Đường dẫn thực tế phải khớp với base path, repository path và cấu hình export của ứng dụng. Nếu dùng session login hoặc bearer token, authentication mechanism và cách test tương ứng sẽ khác.

hasRole("ADMIN") mặc định kiểm tra authority ROLE_ADMIN. Khi dùng hasAuthority("CUSTOMER_WRITE"), Spring Security so sánh đúng tên authority được khai báo, không tự thêm tiền tố ROLE_.

@EnableMethodSecurity bật method security để các annotation như @PreAuthorize được thực thi. Có thể dùng nó để bảo vệ thao tác repository hoặc service theo quy tắc nghiệp vụ. Khi kết hợp URL authorization và method authorization, test cần xác nhận cả hai lớp hoạt động.

Không dựa vào việc frontend ẩn nút Delete để bảo vệ thao tác. Client có thể gọi trực tiếp URL; server phải từ chối request không đủ quyền.

## 4. Giả lập user và role trong test

### 4.1. Dùng @WithMockUser

Ví dụ kiểm tra READER được đọc collection:

~~~java
@Test
@WithMockUser(username = "reader", roles = "READER")
void readerCanReadCustomers() throws Exception {
    mockMvc.perform(get("/customers"))
        .andExpect(status().isOk());
}
~~~

@WithMockUser tạo user trong SecurityContext cho test. Nó không tạo tài khoản trong database và không kiểm tra quy trình đăng nhập thật. Đây là cách nhanh để kiểm tra authorization sau khi authentication đã được giả lập thành công.

Kiểm tra READER không được tạo Customer:

~~~java
@Test
@WithMockUser(username = "reader", roles = "READER")
void readerCannotCreateCustomer() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isForbidden());
}
~~~

Request có CSRF token hợp lệ để test tập trung vào authorization. Nếu bỏ token, request có thể bị CSRF filter từ chối trước khi kiểm tra role; khi đó test không chứng minh được quy tắc READER không được POST.

### 4.2. Dùng authority chính xác

Nếu ứng dụng không sử dụng role prefix, khai báo authority trực tiếp:

~~~java
@Test
@WithMockUser(authorities = "CUSTOMER_READ")
void customerReadAuthorityCanRead() throws Exception {
    mockMvc.perform(get("/customers"))
        .andExpect(status().isOk());
}
~~~

Nếu security rule yêu cầu hasRole("READER"), hãy dùng roles = "READER" hoặc authority ROLE_READER. Tránh nhầm giữa role và authority vì đây là nguyên nhân thường gặp khiến test trả 403 ngoài dự kiến.

### 4.3. Dùng user thật từ UserDetailsService

Khi cần kiểm tra cách ứng dụng tải user, role và trạng thái tài khoản từ database, có thể dùng:

~~~java
@Test
@WithUserDetails("reader@example.com")
void persistedReaderCanReadCustomers() throws Exception {
    mockMvc.perform(get("/customers"))
        .andExpect(status().isOk());
}
~~~

User tương ứng phải tồn tại trong dữ liệu test và UserDetailsService phải tải được user đó. Test cần chuẩn bị dữ liệu trước khi chạy, đồng thời dọn dẹp hoặc dùng transaction theo chiến lược test của ứng dụng.

### 4.4. Phân biệt 401 và 403

- 401 Unauthorized: request chưa được xác thực hoặc credentials không hợp lệ; server yêu cầu authentication.
- 403 Forbidden: request đã được xác thực nhưng principal không đủ quyền, hoặc bị một filter như CSRF từ chối.

Status thực tế còn phụ thuộc authentication entry point và access denied handler. Với HTTP Basic như ví dụ trên, request không có credentials thường nhận 401. Với form login, request chưa xác thực có thể nhận redirect 302 đến trang đăng nhập. Hãy kiểm tra đúng hợp đồng của ứng dụng.

## 5. Kiểm tra CSRF token

CSRF (Cross-Site Request Forgery) xảy ra khi browser tự động gửi credentials của người dùng, ví dụ session cookie, cùng một request được tạo từ trang web khác. Kẻ tấn công có thể lợi dụng phiên đăng nhập đang tồn tại để yêu cầu server thực hiện thao tác ghi.

Spring Security bật CSRF protection mặc định cho các request thay đổi trạng thái như POST, PUT, PATCH và DELETE. Các method safe như GET, HEAD, TRACE và OPTIONS được loại khỏi CSRF protection mặc định.

CSRF token là bằng chứng bổ sung cho thấy request ghi được tạo theo luồng mà ứng dụng mong đợi. Token phải được client gửi lại theo cách server cấu hình, thường qua request parameter hoặc header.

### 5.1. Request có token hợp lệ

Spring Security Test cung cấp request post processor csrf():

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void adminCanCreateCustomerWithCsrfToken() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isCreated());
}
~~~

Ví dụ giả định payload hợp lệ và repository resource được phép tạo. Nếu endpoint có validation hoặc response contract khác, điều chỉnh body và assertion theo ứng dụng.

### 5.2. Gửi token qua header

Frontend thường gửi CSRF token trong header. Có thể kiểm tra cách này bằng:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void acceptsCsrfTokenInHeader() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf().asHeader())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isCreated());
}
~~~

csrf().asHeader() đặt token vào header theo tên mà request post processor và cấu hình Spring Security sử dụng. Nếu ứng dụng đổi tên header hoặc dùng một token repository tùy chỉnh, phải kiểm tra đúng tên header thực tế.

### 5.3. Không có token hoặc token sai

Kiểm tra request ghi không có token:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void rejectsPostWithoutCsrfToken() throws Exception {
    mockMvc.perform(post("/customers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isForbidden());
}
~~~

Kiểm tra token không hợp lệ:

~~~java
@Test
@WithMockUser(roles = "ADMIN")
void rejectsInvalidCsrfToken() throws Exception {
    mockMvc.perform(post("/customers")
            .with(csrf().useInvalidToken())
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Nguyen An",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isForbidden());
}
~~~

Các test này nên dùng user đã có quyền ADMIN để xác nhận nguyên nhân bị từ chối là CSRF. Nếu dùng user thiếu quyền, nhiều lớp bảo mật có thể cùng từ chối request và làm test khó xác định filter nào đang được kiểm tra.

Cũng cần kiểm tra PUT, PATCH và DELETE vì đây là các method ghi. Một test POST thành công không chứng minh mọi method ghi đều được bảo vệ đúng.

### 5.4. Khi nào có thể tắt CSRF?

Không tắt CSRF chỉ vì API trả JSON hoặc được gọi từ frontend SPA. Nếu browser xác thực bằng session cookie hoặc credentials được browser tự động gửi, request vẫn có thể chịu rủi ro CSRF.

Một API chỉ nhận bearer token trong Authorization header, không dùng credentials tự động gửi bởi browser, có thể có mô hình rủi ro khác và có thể cấu hình CSRF riêng cho security chain đó. Quyết định phải dựa trên cơ chế xác thực thực tế, cách token được lưu và việc browser có tự động đính kèm credentials hay không.

Nếu dùng cookie để chia sẻ CSRF token với SPA, có thể cấu hình CookieCsrfTokenRepository. Ví dụ:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

Cách xử lý token trong Spring Security 6 có thể cần cấu hình request handler phù hợp với SPA và phiên bản đang dùng. Không giả định chỉ cần đọc cookie là có thể gửi lại token đúng; hãy kiểm tra tên cookie, header, cơ chế token masking và response thực tế. Cookie token thường được frontend đọc để đặt giá trị vào header; session cookie vẫn cần được browser gửi theo chính sách cookie phù hợp.

## 6. Kiểm tra CORS preflight

CORS (Cross-Origin Resource Sharing) kiểm soát việc browser cho phép JavaScript ở một origin đọc response từ origin khác. Origin gồm scheme, host và port. Ví dụ:

- https://app.example.com
- https://api.example.com

Hai URL trên là hai origin khác nhau dù cùng domain gốc.

Một request cross-origin có thể được browser gửi trực tiếp hoặc phải gửi preflight OPTIONS trước. Preflight thường xuất hiện khi request dùng method hoặc header không thuộc nhóm simple request, ví dụ POST với Content-Type application/json hoặc custom header X-XSRF-TOKEN.

### 6.1. Cấu hình CORS

Có thể khai báo CorsConfigurationSource và bật CORS trong SecurityFilterChain:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();

    config.setAllowedOrigins(
        List.of("https://app.example.com")
    );
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    );
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-XSRF-TOKEN")
    );
    config.setExposedHeaders(
        List.of("Location", "ETag", "Link")
    );
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);

    return source;
}
~~~

Các lựa chọn quan trọng:

- allowedOrigins: origin cụ thể được phép gọi API.
- allowedMethods: method mà browser được phép sử dụng cross-origin.
- allowedHeaders: header mà browser được phép gửi.
- exposedHeaders: response header mà JavaScript được phép đọc.
- allowCredentials: cho phép browser gửi credentials trong request cross-origin.

Khi bật credentials, không dùng wildcard * cho allowed origin. Hãy chỉ định origin cụ thể hoặc thiết kế cơ chế kiểm tra origin phù hợp. Nếu client cần đọc Location, ETag hoặc Link từ response Spring Data REST, phải expose các header đó; việc server gửi header không tự động có nghĩa JavaScript được đọc header.

CORS phải được xử lý trước khi authorization yêu cầu người dùng đăng nhập, vì preflight thường không mang session cookie hoặc bearer token. Khi dùng Spring Security, bật http.cors(...) và cung cấp cấu hình CORS để filter có thể xử lý preflight trước bước xác thực thông thường.

Không cần mở toàn bộ OPTIONS endpoint một cách tùy tiện để giải quyết CORS. CORS filter phải xác nhận Origin, requested method và requested headers theo cấu hình.

### 6.2. Kiểm thử preflight origin được phép

Dùng MockMvc gửi OPTIONS với các header mà browser thường gửi:

~~~java
@Test
void allowsPreflightFromConfiguredOrigin() throws Exception {
    mockMvc.perform(options("/customers")
            .header(HttpHeaders.ORIGIN, "https://app.example.com")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-xsrf-token"
            ))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
            "https://app.example.com"
        ))
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
            containsString("POST")
        ))
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
            allOf(
                containsString("content-type"),
                containsString("x-xsrf-token")
            )
        ));
}
~~~

Tùy phiên bản và cấu hình, status preflight có thể được trả về theo cách triển khai CORS của ứng dụng. Điều cần xác nhận là response cho origin hợp lệ có Allow-Origin, method và headers phù hợp với request. Nếu ứng dụng cấu hình credentials, kiểm tra thêm Access-Control-Allow-Credentials có giá trị true.

### 6.3. Kiểm thử origin không được phép

~~~java
@Test
void rejectsPreflightFromUntrustedOrigin() throws Exception {
    mockMvc.perform(options("/customers")
            .header(HttpHeaders.ORIGIN, "https://evil.example")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "POST"
            ))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
        ));
}
~~~

Test này xác nhận origin không được phép không nhận header cho phép truy cập. Nếu ứng dụng có custom CORS processor hoặc error handler, status cụ thể có thể khác; hãy giữ hợp đồng rõ ràng và xác nhận browser không được phép đọc response.

### 6.4. Kiểm tra actual request

Preflight thành công chưa chứng minh request thật được authorization và CSRF chấp nhận. Hãy kiểm tra thêm request có Origin hợp lệ:

~~~java
@Test
@WithMockUser(roles = "READER")
void allowsActualReadFromConfiguredOrigin() throws Exception {
    mockMvc.perform(get("/customers")
            .header(HttpHeaders.ORIGIN, "https://app.example.com"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
            "https://app.example.com"
        ));
}
~~~

Với request ghi, phải kiểm tra đồng thời:

- Origin có được cho phép không.
- Method và header có được cho phép không.
- User đã xác thực và có quyền không.
- CSRF token có hợp lệ không nếu CSRF protection được bật.
- Request có thực sự tạo hoặc cập nhật dữ liệu đúng không.

CORS không thay thế các assertion phân quyền hoặc CSRF.

## 7. Kiểm tra JWT Resource Server

Nếu API dùng OAuth2 Resource Server thay cho HTTP Basic, có thể giả lập JWT authentication bằng Spring Security Test:

~~~java
@Test
void readerJwtCanReadCustomers() throws Exception {
    mockMvc.perform(get("/customers")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("ROLE_READER")
            )))
        .andExpect(status().isOk());
}
~~~

Cách này tạo authentication trong test mà không cần ký và gửi JWT thật. Nó phù hợp để kiểm tra authorization sau khi token đã được xác thực và chuyển thành authorities.

Nó không kiểm tra chữ ký, issuer, audience, expiry hoặc việc lấy public key từ identity provider. Những phần đó cần test riêng cho decoder hoặc security integration tương ứng.

Nếu API dùng scope như customers.read, authority thường được ánh xạ thành SCOPE_customers.read. Hãy giả lập đúng authority mà rule thực tế kiểm tra, ví dụ:

~~~java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_customers.read")
))
~~~

Không dùng role READER trong test nếu production token chỉ cung cấp scope và converter không chuyển scope thành role tương ứng.

## 8. Ma trận test nên có

Một bộ test tích hợp cho Spring Data REST có thể bao gồm:

| Tình huống | Cách giả lập | Kết quả mong đợi |
|---|---|---|
| Anonymous đọc resource cần đăng nhập | Không cung cấp user | 401 hoặc redirect theo entry point |
| READER đọc collection | @WithMockUser(roles = "READER") | 200 |
| READER tạo resource | READER + CSRF hợp lệ | 403 |
| ADMIN tạo resource | ADMIN + CSRF hợp lệ + payload hợp lệ | 201 hoặc status theo endpoint |
| ADMIN POST thiếu CSRF | ADMIN, không có token | 403 |
| ADMIN POST token sai | ADMIN + invalid token | 403 |
| ADMIN PUT/PATCH/DELETE | ADMIN + token hợp lệ | Thành công theo hợp đồng |
| Origin được phép preflight | OPTIONS + Origin hợp lệ | Allow-Origin/Methods/Headers phù hợp |
| Origin không được phép | OPTIONS + Origin ngoài allowlist | Không có Allow-Origin |
| JWT thiếu authority | JWT với scope/role không đủ | 403 |
| Repository method bị bảo vệ | Authentication hợp lệ nhưng method security từ chối | 403 |

Bên cạnh status, kiểm tra các header quan trọng:

- Access-Control-Allow-Origin
- Access-Control-Allow-Methods
- Access-Control-Allow-Headers
- Access-Control-Allow-Credentials
- Access-Control-Expose-Headers
- Vary: Origin khi response thay đổi theo origin

Nếu test kiểm tra response body, hãy bảo đảm dữ liệu không bị thay đổi khi request bị từ chối. Ví dụ sau POST bị CSRF từ chối, repository không được tạo thêm entity. Sau DELETE bị thiếu quyền, resource vẫn phải tồn tại.

## 9. Các lỗi thường gặp khi viết Spring Security Test

**Test POST trả 403 dù user có ADMIN:** có thể CSRF token bị thiếu. Thêm .with(csrf()) khi mục tiêu là test authorization. Nếu đang test CSRF, giữ request không token và xác nhận bị từ chối.

**Dùng roles = "ADMIN" nhưng rule vẫn từ chối:** kiểm tra rule dùng hasRole("ADMIN") hay hasAuthority("ADMIN"). Role mặc định có prefix ROLE_.

**Test GET trả 401:** kiểm tra test đã gắn @WithMockUser, user() hoặc JWT chưa; đồng thời kiểm tra URL matcher và authentication entry point.

**Preflight OPTIONS bị yêu cầu đăng nhập:** kiểm tra http.cors(...), CorsConfigurationSource và thứ tự xử lý CORS. Preflight cần được xử lý trước authorization thông thường.

**CORS test pass nhưng browser vẫn không đọc được response:** kiểm tra origin thực tế gồm cả scheme/host/port, credentials, requested headers, exposed headers và Vary. Header Access-Control-Allow-Origin phải phù hợp chính xác với origin của frontend.

**Frontend gửi Authorization nhưng preflight thất bại:** thêm Authorization vào allowed headers nếu API cần header này. Cũng kiểm tra Content-Type và custom CSRF header.

**Dùng wildcard origin cùng credentials:** browser sẽ từ chối cấu hình này. Chỉ định origin cụ thể hoặc kiểm tra origin theo allowlist.

**CORS bị nhầm là authentication:** curl gọi được API không có nghĩa browser được phép đọc response. Ngược lại, CORS cho phép origin không có nghĩa người dùng đã đăng nhập hoặc có quyền.

**Tắt CSRF để làm test pass:** việc này có thể che giấu lỗ hổng ở ứng dụng dùng cookie/session. Hãy cấu hình theo mô hình authentication và test đúng token flow.

**Chỉ dùng @WithMockUser để kết luận login hoạt động:** annotation không chạy quy trình đăng nhập và không kiểm tra mật khẩu, session creation hoặc JWT signature. Cần test riêng cho authentication mechanism.

## 10. Checklist trước khi công bố

1. Các repository resource có quy tắc GET/POST/PUT/PATCH/DELETE rõ ràng.
2. Anonymous, reader và admin được kiểm tra riêng.
3. Role và authority trong test khớp với rule production.
4. Test ghi có CSRF token hợp lệ khi kiểm tra quyền nghiệp vụ.
5. Test thiếu token và token sai đều bị từ chối.
6. PUT, PATCH và DELETE được kiểm tra cùng POST.
7. Preflight từ origin được phép trả đúng allow headers.
8. Preflight từ origin không được phép không nhận Allow-Origin.
9. Actual request được kiểm tra riêng với authorization và CSRF.
10. CORS credentials và wildcard origin được cấu hình đúng.
11. Các response header mà frontend cần đọc được expose.
12. JWT test giả lập đúng authorities production converter tạo ra.
13. Request bị từ chối không làm thay đổi database hoặc phát side effect.
14. Test chạy với Spring Security filter chain thật của application context.

## Kết luận

Spring Security Test giúp xác nhận API Spring Data REST bảo vệ resource theo đúng người dùng, quyền và trạng thái request. @WithMockUser, user() và jwt() hỗ trợ giả lập authentication; csrf() kiểm tra token cho thao tác ghi; MockMvc OPTIONS cùng các CORS header kiểm tra preflight và origin.

Hãy kiểm tra authentication, authorization, CSRF và CORS như những phần độc lập trong cùng một luồng request. Một bộ test tốt phải chứng minh cả request hợp lệ được phép thực hiện và request sai quyền, thiếu token hoặc đến từ origin không được phép bị xử lý đúng theo hợp đồng của API.