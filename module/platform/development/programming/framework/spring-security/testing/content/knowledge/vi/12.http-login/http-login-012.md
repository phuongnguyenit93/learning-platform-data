# Không dùng dữ liệu xác thực thật của môi trường triển khai trong bộ kiểm thử

Trong chương **Đăng nhập qua HTTP** của module **SPRING_SECURITY_TESTING**, mục tiêu là kiểm chứng xác thực, phân quyền và khả năng bảo vệ HTTP bằng `spring-security-test` trên ứng dụng **Servlet** và **Reactive**. Một nguyên tắc bắt buộc khi viết các bài kiểm thử này là: **không đưa tài khoản, mật khẩu, session, access token, refresh token, cookie đăng nhập, khóa ký hoặc thông tin kết nối tới hệ thống xác thực thật của môi trường triển khai vào bộ kiểm thử**.

Kiểm thử cần tái tạo *trạng thái bảo mật* hoặc *quy trình đăng nhập* bằng dữ liệu được kiểm soát riêng cho test. Nhờ vậy, kết quả ổn định, có thể chạy cục bộ và trên CI, không phụ thuộc người dùng thật hay dịch vụ nhận dạng bên ngoài. Đồng thời, cần hiểu ranh giới của từng kiểu giả lập: một `@WithMockUser` có thể chứng minh luật phân quyền hoạt động, nhưng không chứng minh mật khẩu được kiểm tra đúng; `jwt()` giả lập một JWT đã được xác thực, nhưng không chứng minh chữ ký JWT hợp lệ.

## 1. Vì sao không dùng dữ liệu xác thực của môi trường triển khai?

“Dữ liệu xác thực thật” bao gồm cả tài khoản production lẫn tài khoản dùng chung tại staging, pre-production, hệ thống SSO doanh nghiệp hoặc nhà cung cấp OAuth2/OIDC đang phục vụ một môi trường triển khai. Những thứ cần tránh đưa vào test gồm:

| Dữ liệu hoặc phụ thuộc thật | Rủi ro khi dùng trong test | Thay thế phù hợp |
| --- | --- | --- |
| Tên đăng nhập và mật khẩu của người dùng, quản trị viên hoặc tài khoản dịch vụ | Lộ thông tin qua repository, log CI, báo cáo lỗi; tài khoản bị khóa khi chạy sai nhiều lần | User giả trong `InMemoryUserDetailsManager` hoặc kho dữ liệu test cô lập |
| Cookie session, mã CSRF hoặc token lấy từ trình duyệt đã đăng nhập | Hết hạn ngẫu nhiên, phụ thuộc phiên thật và có thể bị sử dụng ngoài ý muốn | `@WithMockUser`, `user(...)`, `csrf()` hoặc phiên đăng nhập được tạo ngay trong test |
| Access token, refresh token, ID token đang còn hiệu lực | Mang quyền truy cập thật; dễ bị in vào log hoặc artifact của CI | `jwt()`, `mockJwt()`, `oauth2Login()`, `oidcLogin()` với danh tính và claim giả |
| Private key, client secret, certificate hoặc JWK của môi trường triển khai | Rủi ro rò rỉ khóa và phụ thuộc hạ tầng bảo mật thật | Khóa test sinh cục bộ, bộ khóa tạm thời hoặc mock decoder tùy lớp kiểm thử |
| Database người dùng, LDAP hoặc Identity Provider dùng chung | Kiểm thử làm thay đổi dữ liệu/giới hạn đăng nhập, gây gián đoạn hoặc kết quả phụ thuộc mạng | Database dùng một lần, stub HTTP, fake IdP hoặc môi trường sandbox riêng |

Một bài test chạy thành công bằng token production không phải bằng chứng chất lượng mạnh hơn. Nó thường chỉ cho thấy một token hiện tại vẫn có quyền truy cập, trong khi ngày hôm sau token có thể hết hạn hoặc bị thu hồi. Test cũng có thể vô tình gửi request thay đổi dữ liệu tới dịch vụ ngoài phạm vi kiểm soát.

## 2. Chọn đúng mức độ giả lập cho mục tiêu kiểm thử

Các cách kiểm thử Spring Security không thay thế lẫn nhau. Trước khi viết test, hãy xác định **điều cần chứng minh**:

| Mục tiêu | Công cụ nên dùng | Điều được kiểm chứng | Điều chưa được kiểm chứng |
| --- | --- | --- | --- |
| Luật truy cập URL và `@PreAuthorize` | MockMvc + `@WithMockUser`/`user(...)` | Security filter chain, quyền và phản hồi HTTP khi có danh tính giả | Xác thực mật khẩu, xác minh chữ ký token |
| Login biểu mẫu thực sự bằng HTTP | MockMvc + tài khoản test trong `UserDetailsService` + request `/login` | Luồng nhận username/password, bộ mã hóa mật khẩu, session, chuyển hướng | Kết nối kho tài khoản hoặc IdP môi trường triển khai |
| Phân quyền API resource server dựa trên claim/scope | MockMvc `jwt()` hoặc WebTestClient `mockJwt()` | Cách ứng dụng dùng principal/authority đã xác thực | Chữ ký, `issuer`, `audience`, thời hạn token nếu chỉ dùng mock JWT |
| Hành vi ứng dụng sau OAuth2 Login hoặc OIDC Login | `oauth2Login()`/`oidcLogin()` và dữ liệu giả | Mapping principal, claim và quyền sau đăng nhập | Authorization Code flow, token exchange, OIDC discovery từ nhà cung cấp thật |
| Bộ giải mã và validator JWT | Token ký bằng khóa test + decoder/validator thực + JWKS stub cục bộ | Chữ ký, thời hạn, issuer, audience, key rotation tùy cấu hình | Độ sẵn sàng của hệ thống IdP sản xuất |
| Tích hợp với IdP bên ngoài | Fake IdP hoặc sandbox được cấp riêng cho kiểm thử | Giao thức và tích hợp trong môi trường cô lập | Không dùng tài khoản và khóa production để thay thế sandbox |

Nguyên tắc thiết kế là **giả lập ở ranh giới nhỏ nhất vẫn đủ chứng minh hành vi cần kiểm tra**. Test kiểm tra `hasRole("ADMIN")` không cần đăng nhập thật vào SSO. Ngược lại, test kiểm tra JWT hết hạn phải đi qua decoder/validator thật hoặc kiểm thử độc lập validator; chỉ thêm claim `exp` vào `mockJwt()` là chưa đủ.

## 3. Servlet: kiểm chứng 401, 403 và 200 bằng tài khoản giả

Ví dụ có endpoint `GET /api/admin/reports`, chỉ người có role `ADMIN` được truy cập. Cấu hình minh họa dùng Spring Security 6 / Spring Boot 3 và HTTP Basic để phản hồi **401** với request chưa xác thực:

```java
@Configuration
class ReportSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/reports")
                    .hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class ReportController {

    @GetMapping("/api/admin/reports")
    String report() {
        return "report-ready";
    }
}
```

Test dùng `@WebMvcTest` để nạp controller và import cấu hình bảo mật đang cần kiểm tra. `@WithMockUser` tạo `Authentication` giả trong `SecurityContext` của test, không đọc mật khẩu hay người dùng từ cơ sở dữ liệu triển khai:

```java
@WebMvcTest(ReportController.class)
@Import(ReportSecurityConfig.class)
class ReportSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousRequestReturns401() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "local-reader", roles = "USER")
    void authenticatedUserWithoutAdminRoleReturns403() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "local-admin", roles = "ADMIN")
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("report-ready"));
    }
}
```

Các import chính: `@WithMockUser` từ `org.springframework.security.test.context.support`, request builder `get` từ `MockMvcRequestBuilders`, `status` và `content` từ `MockMvcResultMatchers`. Test cần dependency `spring-security-test` ở phạm vi `test`.

Ba trường hợp thể hiện ba quyết định khác nhau của HTTP security:

- **401 Unauthorized:** không có thông tin xác thực hợp lệ đối với HTTP Basic hoặc Bearer API. Nếu cấu hình `formLogin()`, request anonymous tới trang bảo vệ có thể được **302 redirect** đến trang đăng nhập; vì vậy phải khẳng định theo cơ chế xác thực thực tế của ứng dụng.
- **403 Forbidden:** đã có danh tính nhưng thiếu quyền phù hợp. `roles = "USER"` tương ứng authority `ROLE_USER`, còn `hasRole("ADMIN")` yêu cầu `ROLE_ADMIN`.
- **200 OK:** danh tính thử nghiệm có đúng quyền, endpoint thực thi và trả nội dung mong đợi.

Nếu chỉ muốn gắn danh tính cho **một request**, dùng `SecurityMockMvcRequestPostProcessors.user(...)` thay cho annotation:

```java
mvc.perform(get("/api/admin/reports")
        .with(user("fixture-admin").roles("ADMIN")))
    .andExpect(status().isOk());
```

Khi tự tạo `MockMvc` bằng `MockMvcBuilders`, phải tích hợp Spring Security bằng `.apply(springSecurity())` (hoặc cách lắp filter tương đương); trong bài test Spring Boot với `@AutoConfigureMockMvc`, cần đảm bảo filter được bật. Nếu filter chain không tham gia request, kết quả 200 có thể là **dương tính giả** và test sẽ không thực sự kiểm chứng phân quyền.

## 4. Khi cần kiểm tra đăng nhập bằng username/password thật sự

`@WithMockUser` **bỏ qua bước kiểm tra mật khẩu**. Nếu mục tiêu là kiểm chứng endpoint đăng nhập HTTP form, hãy cho ứng dụng xác thực một tài khoản *hoàn toàn giả* trong bộ nhớ. Cấu hình dưới đây chỉ dùng ở test và giả định ứng dụng bật `formLogin()`:

```java
@TestConfiguration(proxyBeanMethods = false)
class LocalTestAccounts {

    @Bean
    PasswordEncoder testPasswordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService testUserDetailsService(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("fixture-user")
            .password(encoder.encode("fixture-password-only"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(user);
    }
}
```

Một bài kiểm thử login sử dụng chính cặp giá trị vừa tạo, có CSRF token do tiện ích test sinh ra:

```java
@Test
void fixtureAccountCanLogIn() throws Exception {
    mvc.perform(post("/login")
            .with(csrf())
            .param("username", "fixture-user")
            .param("password", "fixture-password-only"))
        .andExpect(status().is3xxRedirection())
        .andExpect(authenticated().withUsername("fixture-user"));
}
```

Để chạy đoạn minh họa, test phải import cấu hình account, dùng `SecurityFilterChain` có `formLogin(Customizer.withDefaults())`, và giữ `PasswordEncoder`/`UserDetailsService` nhất quán. Không sao chép username/password từ biến môi trường hoặc file cấu hình deployment. Mặc dù chuỗi `fixture-password-only` xuất hiện trong mã, nó **chỉ là dữ liệu tạo ra cho test**, không cấp quyền vào hệ thống thực nào.

Với biểu mẫu có CSRF protection, dùng `.with(csrf())` để tạo token hợp lệ, và kiểm tra thêm request **thiếu** hoặc **sai** CSRF bị từ chối. Tuy nhiên, không mặc định mọi request POST đều phải có CSRF: API stateless có thể cấu hình chính sách CSRF khác. Phải kiểm thử theo cấu hình triển khai của endpoint.

## 5. JWT, OAuth2 và OIDC: giả lập đúng trạng thái bảo mật

### 5.1. MockMvc với JWT của resource server

Một API chỉ cho phép authority `SCOPE_reports.read` có thể được kiểm tra bằng request giả lập JWT:

```java
mvc.perform(get("/api/reports")
        .with(jwt()
            .jwt(token -> token
                .subject("fixture-subject")
                .claim("tenant", "tenant-test"))
            .authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

`jwt()` ở đây là `SecurityMockMvcRequestPostProcessors.jwt()`. Test đặt `Authentication` tương ứng vào request; không cần access token do IdP cấp hoặc private key triển khai. Gán `authorities(...)` một cách tường minh giúp test không phụ thuộc quy tắc suy diễn scope mặc định.

Viết thêm trường hợp âm tính với authority khác và mong đợi 403, hoặc request không mang bearer authentication và mong đợi 401 trong cấu hình resource server. **Đừng gọi `jwt()` là kiểm thử xác minh chữ ký:** mặc dù có thể đặt `iss`, `aud`, `exp` trong claim giả, request này không tự kích hoạt đầy đủ quy trình giải mã và xác thực chữ ký từ header `Authorization`.

### 5.2. OAuth2 Login và OpenID Connect Login

Khi ứng dụng nhận danh tính từ OAuth2 Client/OIDC, `spring-security-test` cung cấp request post-processor phù hợp:

```java
// Giả lập người dùng đã hoàn tất OAuth2 Login.
mvc.perform(get("/profile")
        .with(oauth2Login()
            .attributes(attrs -> attrs.put("sub", "fixture-oauth2-user"))))
    .andExpect(status().isOk());

// Giả lập một OIDC principal với ID token nhân tạo.
mvc.perform(get("/profile")
        .with(oidcLogin()
            .idToken(idToken -> idToken.subject("fixture-oidc-user"))))
    .andExpect(status().isOk());
```

Hai đoạn kiểm tra hành vi ứng dụng *sau đăng nhập*, chẳng hạn đọc thông tin principal hoặc kiểm soát endpoint theo authority. Chúng không đi qua trang đăng nhập của nhà cung cấp, authorization code callback, token endpoint hay kiểm tra chữ ký ID token. Để kiểm thử những bước đó, dùng một nhà cung cấp giả/stub chạy nội bộ hoặc sandbox độc lập và áp dụng validator, redirect URI, `state`, `nonce` theo đúng luồng cần kiểm chứng.

### 5.3. Kiểm thử decoder/validator bằng khóa test

Nếu yêu cầu là **xác minh JWT thật sự**, thiết lập một bài kiểm thử riêng:

1. Tạo cặp khóa bất đối xứng chỉ phục vụ test, ưu tiên sinh mới theo lần chạy; công bố public key qua JWKS stub nội bộ.
2. Ký JWT nhân tạo với `sub`, `iss`, `aud`, `iat`, `exp` và `scope` dành cho test; không dùng token sao chép từ production.
3. Gửi HTTP request với `Authorization: Bearer <token-test>` qua filter chain và `JwtDecoder` thật.
4. Khẳng định token hợp lệ được chấp nhận; token sai chữ ký, hết hạn, issuer/audience sai bị từ chối theo cấu hình validator của ứng dụng.
5. Đảm bảo issuer/JWKS URL trỏ vào stub nội bộ; không để test tự phát hiện metadata qua OIDC discovery ở domain triển khai.

Nếu mock `JwtDecoder` để trả `Jwt` theo ý muốn, test chỉ chứng minh hành vi **sau giải mã**. Không coi test đó là bằng chứng đã kiểm tra thuật toán chữ ký hoặc chính sách chấp nhận token.

## 6. Reactive: WebTestClient với `mockJwt()`

Trong ứng dụng WebFlux, sử dụng `WebTestClient` gắn với application context có `SecurityWebFilterChain` và cấu hình tích hợp Spring Security. Với endpoint `GET /api/reports` yêu cầu `SCOPE_reports.read`, có thể kiểm tra cùng ma trận quyền như Servlet:

```java
@WebFluxTest(ReactiveReportController.class)
@Import(ReactiveSecurityConfig.class)
class ReactiveReportSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousIsRejected() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongScopeIsForbidden() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_profile.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void correctScopeCanRead() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk();
    }
}
```

`mockJwt()` là tiện ích `SecurityMockServerConfigurers.mockJwt()` thuộc `spring-security-test`. `ReactiveSecurityConfig` cần định nghĩa rule thực tế cho URI bằng `SecurityWebFilterChain`, resource server hoặc cơ chế bearer phù hợp. Test chỉ có ý nghĩa khi `WebTestClient` kết nối với context đã tích hợp security; với cấu hình client thủ công, sử dụng `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` trước khi build client.

Tương tự Servlet, `mockJwt()` không cần mạng, token thật hoặc IdP. Khi test tính hợp lệ của Bearer token trong Reactive, cần một lớp kiểm thử riêng có `ReactiveJwtDecoder` thực và JWKS/khóa test cục bộ.

## 7. Ngăn bộ kiểm thử vô tình dùng thông tin triển khai

Việc dùng mock chưa đủ nếu ứng dụng test vẫn nạp cấu hình, bean hoặc kết nối bên ngoài của production. Thiết kế một **ranh giới môi trường test** rõ ràng:

- Dùng profile test, ví dụ `@ActiveProfiles("test")`, và cấu hình riêng cho `DataSource`, user store, OAuth2 Client, JWT issuer/JWKS và service cần gọi. Profile chỉ là phương tiện chọn cấu hình; cần xác minh các giá trị cuối cùng thực sự được nạp.
- Khởi tạo fixture user/role, tenant, session và token ngay trong test hoặc từ bộ dữ liệu test cô lập. Không lấy cookie/token từ DevTools, Postman, secret manager của deployment, database bản sao chứa credential thật hoặc file `.env` dùng khi triển khai.
- Chặn hoặc thay thế các phụ thuộc mạng khi test không có chủ đích tích hợp. Có thể dùng stub server gắn cổng cục bộ, mock HTTP client, database dùng một lần hoặc quy tắc kiểm soát egress trong CI.
- Với bài kiểm thử tích hợp IdP, chỉ dùng sandbox dành riêng cho test, có tài khoản và quyền tối thiểu, dữ liệu có thể xóa/khởi tạo lại. Sandbox vẫn cần quản lý bí mật phù hợp; không ghi bí mật vào source hoặc báo cáo test.
- Không in header `Authorization`, cookie, refresh token, `client_secret`, private key hoặc toàn bộ `SecurityContext` ra log. Khi failure, ghi HTTP status, URL được phép và thông tin chẩn đoán đã loại dữ liệu nhạy cảm.
- Kiểm tra cấu hình CI: test không phụ thuộc vào `PROD_*`/secret deployment, không tải được khóa triển khai và không gọi domain authentication của hệ thống đang phục vụ người dùng.
- Thực thi các trường hợp âm tính. Nếu một bài test chỉ kiểm tra 200, filter vô hiệu hóa hoặc rule truy cập cấu hình sai có thể vẫn khiến test xanh.

Ví dụ **không nên làm**:

```java
// Sai: bộ test phụ thuộc token thật, có thể hết hạn hoặc mang quyền thật.
String token = System.getenv("PRODUCTION_ACCESS_TOKEN");
mockMvc.perform(get("/api/reports")
        .header("Authorization", "Bearer " + token))
    .andExpect(status().isOk());
```

Ví dụ thay thế để kiểm tra *phân quyền theo scope*:

```java
// Đúng với mục tiêu kiểm tra quyền: token/principal chỉ tồn tại trong test.
mockMvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
```

Nếu muốn kiểm tra khả năng ứng dụng **từ chối token sai**, ví dụ thứ hai chưa đủ; cần test decoder với token được ký bằng khóa test như mục 5.3.

## 8. Ma trận ca kiểm thử tối thiểu

| Kịch bản | Dữ liệu đầu vào của test | Kết quả mong đợi |
| --- | --- | --- |
| Truy cập API cần xác thực khi anonymous | Không gắn danh tính hay token | 401 với HTTP Basic/Bearer, hoặc 302 tới login với form login tùy cấu hình |
| User đăng nhập nhưng thiếu role | `@WithMockUser(roles = "USER")` đối với route cần `ADMIN` | 403 |
| User có đúng role | `@WithMockUser(roles = "ADMIN")` | 2xx và dữ liệu nghiệp vụ phù hợp |
| JWT thiếu scope | `jwt()`/`mockJwt()` với authority khác | 403 |
| JWT có scope yêu cầu | `jwt()`/`mockJwt()` với authority đúng | 2xx |
| Đăng nhập form với fixture hợp lệ | Username/password tạo trong `UserDetailsService` test | Xác thực thành công, redirect/session theo cấu hình |
| Đăng nhập form với sai mật khẩu | Cùng fixture user nhưng password khác | Đăng nhập thất bại, không cấp phiên xác thực |
| POST thay đổi trạng thái với CSRF bật | Có/thiếu token từ `csrf()` | Có token có thể tiếp tục xử lý; thiếu/sai token bị 403 |
| JWT hỏng chữ ký, hết hạn, sai issuer/audience | Token test được ký cục bộ hoặc biến đổi có chủ đích | Decoder/validator từ chối theo chính sách cấu hình |
| Truy cập tài nguyên thuộc tenant khác | Principal giả của tenant A, dữ liệu test thuộc tenant B | Từ chối theo luật nghiệp vụ, không lộ dữ liệu tenant B |

Không ép mọi API dùng cùng mã HTTP: một rule trả `403`, `404` để che giấu tài nguyên, hoặc một login flow trả `302` có thể là thiết kế có chủ đích. Cần ghi rõ contract của endpoint và khẳng định nhất quán với cấu hình bảo mật thật trong ứng dụng.

## 9. Bài thực hành đề xuất

Tạo hai endpoint trong một ứng dụng thử nghiệm: `GET /api/profile` yêu cầu xác thực và `GET /api/admin/audit` yêu cầu `ADMIN`. Thực hiện hai bộ test tương đương trên Servlet (`MockMvc`) và Reactive (`WebTestClient`): anonymous, user thiếu quyền và admin đủ quyền. Sau đó thêm một endpoint yêu cầu `SCOPE_audit.read` và kiểm tra qua `jwt()`/`mockJwt()` với authority đúng và sai.

Tiêu chí hoàn thành:

1. Không sử dụng tên đăng nhập, mật khẩu, session hay token được lấy từ môi trường triển khai; toàn bộ danh tính và quyền là fixture.
2. Các test xác thực được rằng **filter chain được chạy**; anonymous và thiếu quyền bị từ chối, đúng quyền mới thành công.
3. Có ít nhất một ca âm tính cho mỗi chính sách quan trọng; kết quả không phụ thuộc mạng ngoài hoặc thời hạn token thật.
4. Người học giải thích được vì sao mock user/JWT **không thay thế** bài kiểm thử mật khẩu hoặc chữ ký và thiết kế được một test decoder dùng khóa test.
5. Chạy lại trên máy khác hoặc CI vẫn tái lập kết quả mà không cần cấp secret của môi trường triển khai.

## Ghi nhớ

Trong **Spring Security Testing**, `@WithMockUser`, `user(...)`, `jwt()`, `oauth2Login()`, `oidcLogin()` và `mockJwt()` là công cụ để kiểm chứng hành vi HTTP trong các trạng thái bảo mật có thể kiểm soát. Dùng fixture cô lập cho login thực sự và token được ký bằng khóa test khi cần kiểm tra xác thực ở tầng thấp hơn. **Tài khoản và bí mật của môi trường triển khai không thuộc dữ liệu đầu vào của test tự động**; test tốt là test chứng minh đúng chính sách bảo mật với dữ liệu an toàn, xác định và có thể tái lập.
