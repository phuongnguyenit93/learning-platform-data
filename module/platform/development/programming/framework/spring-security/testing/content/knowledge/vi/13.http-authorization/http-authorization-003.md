# hasRole, hasAuthority và quy ước tiền tố

## 1. Vì sao đúng danh tính vẫn có thể bị từ chối?

Giả sử một người dùng đã đăng nhập thành công, mang vai trò quản trị viên và gọi `GET /admin/audit`. Controller tồn tại, nhưng server trả `403 Forbidden`. Khi kiểm tra test, bạn thấy:

```java
@WithMockUser(authorities = "ADMIN")
```

Trong khi cấu hình HTTP lại là:

```java
.requestMatchers(HttpMethod.GET, "/admin/audit").hasRole("ADMIN")
```

Hai chuỗi `ADMIN` và `ROLE_ADMIN` **không giống nhau**. Với quy ước mặc định của Spring Security, `hasRole("ADMIN")` yêu cầu một `GrantedAuthority` có giá trị `ROLE_ADMIN`. Annotation ở ví dụ lại tạo authority đúng bằng `ADMIN`, nên test thất bại. Đây là một trong những nguyên nhân phổ biến khiến test phân quyền trông hợp lý nhưng trả kết quả ngược mong đợi.

Trong **SPRING_SECURITY_TESTING**, người học sử dụng `spring-security-test` để kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên Servlet lẫn Reactive. Bài này tập trung vào **cách Spring Security biểu diễn quyền** và cách dùng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và các principal JWT/OAuth2/OIDC giả lập để chứng minh quy tắc quyền có hiệu lực thực sự.

Sau bài học, bạn sẽ có thể:

- Phân biệt `Authentication`, `GrantedAuthority`, role và OAuth2 scope.
- Chọn `hasRole`, `hasAnyRole`, `hasAuthority`, `hasAnyAuthority` phù hợp với dữ liệu quyền.
- Dự đoán chính xác `ROLE_` và `SCOPE_` xuất hiện ở đâu, khi nào chỉ là quy ước và khi nào là chuỗi phải khớp hoàn toàn.
- Viết test cho cả ca **được phép** và **bị từ chối** mà không nhầm `401`, `403` và CSRF.
- Chẩn đoán sai lệch quyền trong HTTP security, method security và Resource Server JWT.

## 2. Quyền trong Spring Security được lưu như thế nào?

Khi một request đã được xác thực, Spring Security biểu diễn danh tính qua `Authentication`. Đối tượng này thường có:

- `principal`: người dùng hoặc chủ thể của token.
- `credentials`: thông tin chứng thực khi phù hợp; không nên ghi thông tin nhạy cảm vào log.
- `authenticated`: trạng thái xác thực do cơ chế xác thực thiết lập.
- `authorities`: tập các `GrantedAuthority` quyết định chủ thể được làm gì.

Một `GrantedAuthority` thông dụng là `SimpleGrantedAuthority`, chỉ bao bọc **một chuỗi**:

```java
new SimpleGrantedAuthority("ROLE_ADMIN");
new SimpleGrantedAuthority("SCOPE_reports.read");
new SimpleGrantedAuthority("document:approve");
```

Ba giá trị trên đều là `GrantedAuthority`. Spring Security không tự suy ra quan hệ giữa chúng chỉ từ tên gọi. Điều kiện phân quyền sẽ kiểm tra một hoặc nhiều chuỗi đó theo quy tắc đã cấu hình.

Ví dụ với hai người dùng:

| Chủ thể | `Authentication.getAuthorities()` | Ý nghĩa theo chính sách ví dụ |
| --- | --- | --- |
| `alice` | `ROLE_USER` | Người dùng thông thường |
| `bob` | `ROLE_ADMIN`, `SCOPE_reports.read` | Quản trị viên và có quyền đọc báo cáo |

Nếu endpoint yêu cầu `ROLE_ADMIN`, `alice` không được phép còn `bob` được phép. Nếu một endpoint khác yêu cầu `SCOPE_reports.read`, `bob` cũng được phép, nhưng **chỉ vì có authority đó**, không phải do `ROLE_ADMIN` tự động bao hàm scope.

### Role cũng được biểu diễn bằng authority

Trong Spring Security, role **thường là một authority có tiền tố `ROLE_`**. Không có một danh sách role toàn cục tự động gắn ý nghĩa cho `ADMIN`, `USER` hoặc `MANAGER`. Tên role và quan hệ giữa các role phải do ứng dụng quyết định, hoặc do cơ chế ánh xạ/quy tắc phân quyền khai báo rõ.

Phân biệt hai cấp độ:

1. **Tên logic của role:** `ADMIN`.
2. **Chuỗi authority lưu trong `Authentication` theo mặc định:** `ROLE_ADMIN`.

Ở phía request, `hasRole("ADMIN")` giúp viết chính sách ở cấp tên logic, còn `hasAuthority("ROLE_ADMIN")` yêu cầu nguyên chuỗi.

## 3. Bốn API quan trọng và phép so khớp thực tế

| API | Cách hiểu với tiền tố mặc định | Principal có gì thì đạt? |
| --- | --- | --- |
| `hasRole("ADMIN")` | Kiểm tra authority `ROLE_ADMIN` | Có `ROLE_ADMIN` |
| `hasAnyRole("USER", "ADMIN")` | Kiểm tra **ít nhất một** trong `ROLE_USER` hoặc `ROLE_ADMIN` | Có một trong hai |
| `hasAuthority("ADMIN")` | Kiểm tra authority đúng chuỗi `ADMIN` | Có `ADMIN` |
| `hasAnyAuthority("document:read", "document:write")` | Kiểm tra **ít nhất một** chuỗi được truyền vào | Có `document:read` hoặc `document:write` |

Với quy ước mặc định:

```java
// Hai biểu thức có cùng yêu cầu authority:
.hasRole("ADMIN")
.hasAuthority("ROLE_ADMIN")

// Hai biểu thức sau KHÔNG tương đương:
.hasRole("ADMIN")       // tìm ROLE_ADMIN
.hasAuthority("ADMIN")  // tìm đúng ADMIN
```

Các phương thức `hasAnyRole` và `hasAnyAuthority` kết hợp các lựa chọn theo logic **OR**: chỉ cần một quyền khớp. Nếu cần **đồng thời** hai quyền, phải khai báo quy tắc kết hợp phù hợp, chẳng hạn một `AuthorizationManager` tùy chỉnh, hoặc sử dụng biểu thức method security khi áp dụng được. Không viết `hasAnyAuthority("a", "b")` rồi hiểu thành phải có cả hai.

### Những nhầm lẫn thường gặp

**1. Thêm tiền tố hai lần.** Với quy ước mặc định, truyền `"ROLE_ADMIN"` vào `hasRole` là sai cách dùng. Hãy truyền `"ADMIN"` hoặc chủ động dùng `hasAuthority("ROLE_ADMIN")`.

**2. Xem role như một thứ bậc ngầm.** Người chỉ có `ROLE_ADMIN` không tự động có `ROLE_USER`. Nếu một endpoint yêu cầu `hasRole("USER")`, principal chỉ mang `ROLE_ADMIN` không nhất thiết qua được. Khi muốn ADMIN truy cập cả chức năng USER, hãy cấp authority phù hợp, dùng `hasAnyRole` hoặc cấu hình role hierarchy một cách tường minh.

**3. Nghĩ rằng `hasAuthority` tự thêm tiền tố.** `hasAuthority("SCOPE_reports.read")` yêu cầu đúng `SCOPE_reports.read`; `hasAuthority("reports.read")` yêu cầu đúng `reports.read`. Spring Security không biến đổi hai chuỗi này trong lúc so khớp.

**4. Đồng nhất đăng nhập thành công với đủ quyền.** `authenticated()` chỉ đòi chủ thể đã xác thực; `hasRole`/`hasAuthority` thêm điều kiện quyền. Vì vậy, một `Authentication` hợp lệ có thể vượt qua `/api/me` nhưng bị từ chối `/admin/audit`.

## 4. Quy ước `ROLE_` đến từ đâu?

`ROLE_` là **tiền tố mặc định** của nhiều cơ chế kiểm tra role trong Spring Security. Ví dụ:

```java
@PreAuthorize("hasRole('ADMIN')")
public AuditLog readAuditLog() { /* ... */ }
```

Theo cấu hình method security mặc định, biểu thức này cũng nhắm tới `ROLE_ADMIN`. Trong HTTP DSL:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
```

Ý nghĩa theo cấu hình mặc định cũng là yêu cầu `ROLE_ADMIN`. Dù cú pháp gần giống nhau, đây là **hai tầng thực thi**: một tầng xử lý request HTTP, một tầng xử lý lời gọi method. Không nên suy ra đã kiểm thử tầng method chỉ vì test HTTP matcher chạy thành công.

Spring Security cung cấp các điểm tùy chỉnh quy ước role prefix, chẳng hạn `GrantedAuthorityDefaults` cho những thành phần hỗ trợ nó. Tuy nhiên, **không nên giả định một cấu hình tiền tố sẽ tự động thay đổi mọi API và mọi AuthorizationManager trong mọi phiên bản**. Đặc biệt, các factory `hasRole` của một số authorization manager áp dụng trực tiếp quy ước `ROLE_`. Khi dự án đổi sang tiền tố khác, cần xác nhận chính xác từng tầng HTTP, method, expression handler và test fixture đang dùng cách ánh xạ nào.

Nếu dự án cần authority không có tiền tố hoặc dùng tiền tố riêng như `APP_ADMIN`, cách minh bạch trong chính sách là:

```java
.requestMatchers("/admin/**").hasAuthority("APP_ADMIN")
```

Khi đó, fixture phải tạo **đúng** `APP_ADMIN`. Đổi tiền tố mà không kiểm tra lại toàn bộ đường đi của quyền là nguyên nhân gây `403` hoặc cấp quyền rộng hơn mong muốn.

## 5. Quy ước `SCOPE_` của OAuth2/JWT là chuyện khác

Trong OAuth2 Resource Server với JWT, token có thể mang claim `scope` hoặc `scp`, ví dụ:

```json
{
  "sub": "reader-17",
  "scope": "reports.read reports.export"
}
```

Bộ chuyển đổi authority mặc định phổ biến của Spring Security (`JwtGrantedAuthoritiesConverter`) đọc scope và tạo các authority:

```text
SCOPE_reports.read
SCOPE_reports.export
```

Vì vậy, chính sách:

```java
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports.read")
```

phù hợp với một token được ánh xạ chứa `SCOPE_reports.read`. Trong khi đó, `hasRole("reports.read")` tìm `ROLE_reports.read` theo quy ước mặc định, và không tương đương.

| Chuỗi trong JWT hoặc principal | Chuỗi authority dùng để kiểm tra | Biểu thức phù hợp theo mặc định |
| --- | --- | --- |
| Scope `reports.read` sau converter mặc định | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` |
| Role logic `ADMIN` được ánh xạ thành role chuẩn | `ROLE_ADMIN` | `hasRole("ADMIN")` |
| Permission tùy chỉnh `invoice:approve` | `invoice:approve` | `hasAuthority("invoice:approve")` |

Lưu ý: `SCOPE_` là tiền tố do **bước chuyển scope sang authority** áp dụng. Nó không phải quy tắc chung của `hasAuthority`. Ứng dụng có thể cấu hình converter dùng claim hoặc tiền tố khác, ví dụ `permissions` và `PERM_`. Khi converter thay đổi, cả cấu hình endpoint và dữ liệu kiểm thử phải phản ánh **authority sau chuyển đổi**.

## 6. API ví dụ: tách rõ đăng nhập, role và scope

Giả sử có ứng dụng Servlet cung cấp:

| Method và URL | Chính sách | Kết quả handler mẫu |
| --- | --- | --- |
| `GET /public/ping` | Công khai | `200 OK` |
| `GET /api/me` | Đã xác thực | `200 OK`, trả username |
| `GET /api/team` | `ROLE_USER` hoặc `ROLE_ADMIN` | `200 OK` |
| `GET /admin/audit` | `ROLE_ADMIN` | `200 OK` |
| `GET /api/reports` | `SCOPE_reports.read` | `200 OK` |
| `POST /admin/jobs` | `ROLE_ADMIN` và CSRF hợp lệ | `202 Accepted` |
| URL khác | Từ chối mặc định | Tùy danh tính và entry point |

Cấu hình `SecurityFilterChain`:

```java
@Configuration
class RoleAuthoritySecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.GET, "/admin/audit")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/admin/jobs")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/team")
                    .hasAnyRole("USER", "ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Cấu hình dùng **HTTP Basic** để các ca anonymous truy cập endpoint bảo vệ nhận `401 Unauthorized` trong ví dụ. CSRF vẫn bật theo mặc định, nên `POST /admin/jobs` cần token hợp lệ để thực sự kiểm tra rule `hasRole("ADMIN")`. Với ứng dụng form login, anonymous có thể nhận `302` chuyển hướng đăng nhập; với Bearer Resource Server, cơ chế phản hồi phụ thuộc entry point cho Bearer.

Để có endpoint thật phục vụ test:

```java
@RestController
class ExampleController {
    @GetMapping("/public/ping")
    String ping() { return "pong"; }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/api/team")
    String team() { return "team"; }

    @GetMapping("/admin/audit")
    String audit() { return "audit"; }

    @GetMapping("/api/reports")
    String reports() { return "report"; }

    @PostMapping("/admin/jobs")
    ResponseEntity<Void> createJob() {
        return ResponseEntity.accepted().build();
    }
}
```

Controller chỉ minh họa phân quyền ở **lớp HTTP**. Trong ứng dụng thật, cần kiểm tra thêm quyền sở hữu dữ liệu và tác dụng phụ của thao tác ghi.

## 7. Dự đoán kết quả từ tập authority

Giả sử mỗi persona có một tập quyền chính xác:

| Danh tính kiểm thử | Authority được cấp |
| --- | --- |
| Anonymous | Không có Authentication đăng nhập |
| `regular` | `ROLE_USER` |
| `admin` | `ROLE_ADMIN` |
| `reader` | `SCOPE_reports.read` |
| `operator` | `ROLE_ADMIN`, `SCOPE_reports.read` |

Với cấu hình HTTP Basic ở mục trước và **CSRF hợp lệ cho request POST**, kết quả dự kiến:

| Endpoint | Anonymous | Regular | Admin | Reader | Operator |
| --- | ---: | ---: | ---: | ---: | ---: |
| `GET /public/ping` | `200` | `200` | `200` | `200` | `200` |
| `GET /api/me` | `401` | `200` | `200` | `200` | `200` |
| `GET /api/team` | `401` | `200` | `200` | `403` | `200` |
| `GET /admin/audit` | `401` | `403` | `200` | `403` | `200` |
| `GET /api/reports` | `401` | `403` | `403` | `200` | `200` |
| `POST /admin/jobs` | `401` | `403` | `202` | `403` | `202` |

Ma trận cho thấy:

- Admin **không mặc nhiên có scope đọc báo cáo**; hàng `GET /api/reports` phải từ chối admin chỉ có `ROLE_ADMIN`.
- Reader **không mặc nhiên có role USER**; hàng `GET /api/team` phải từ chối người chỉ có `SCOPE_reports.read`.
- Operator được phép ở cả hai khu vực vì fixture cấp **hai authority riêng**.
- Với `POST`, cần gửi CSRF token hợp lệ khi kiểm tra quyền. Nếu thiếu token, kết quả `403` có thể đến từ `CsrfFilter` trước bước phân quyền.

Một ma trận chất lượng phải kiểm tra **ca âm**. Nếu chỉ xác nhận rằng operator có thể gọi tất cả endpoint, bạn chưa chứng minh ranh giới giữa role và scope tồn tại.

## 8. MockMvc: kiểm tra `@WithMockUser(roles)` và `@WithMockUser(authorities)`

Trong ứng dụng Spring Boot Servlet, thêm `spring-security-test` trong test scope; nếu dự án dùng Spring Boot Test/JUnit Jupiter, có thể viết:

```java
@WebMvcTest(ExampleController.class)
@Import(RoleAuthoritySecurityConfig.class)
class RoleAuthorityMvcTest {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCanAccessPublicPing() throws Exception {
        mvc.perform(get("/public/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }

    @Test
    void anonymousNeedsAuthenticationForAudit() throws Exception {
        mvc.perform(get("/admin/audit"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleCanAccessAudit() throws Exception {
        mvc.perform(get("/admin/audit"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "ADMIN")
    void plainAdminAuthorityDoesNotSatisfyHasRole() throws Exception {
        mvc.perform(get("/admin/audit"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "ROLE_ADMIN")
    void prefixedAuthoritySatisfiesHasRole() throws Exception {
        mvc.perform(get("/admin/audit"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotGrantReportScope() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void reportScopeCanAccessReports() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void reportScopeDoesNotGrantAdminRole() throws Exception {
        mvc.perform(get("/admin/audit"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanSubmitWithValidCsrf() throws Exception {
        mvc.perform(post("/admin/jobs").with(csrf()))
           .andExpect(status().isAccepted());
    }
}
```

Các đoạn code minh họa lược bỏ phần `import`: cần `@WebMvcTest`, `@Import`, `@Test`, `@WithMockUser`, các static import `get`/`post` từ `MockMvcRequestBuilders`, `status`/`content` từ `MockMvcResultMatchers` và `csrf` từ `SecurityMockMvcRequestPostProcessors`.

**Hai cách khai báo fixture không tương đương:**

```java
@WithMockUser(roles = "ADMIN")
// Tạo GrantedAuthority: ROLE_ADMIN

@WithMockUser(authorities = "ADMIN")
// Tạo GrantedAuthority: ADMIN

@WithMockUser(authorities = "SCOPE_reports.read")
// Tạo GrantedAuthority: SCOPE_reports.read
```

`@WithMockUser` đặt Authentication giả vào `SecurityContext` cho test. Nó không kiểm tra mật khẩu, token hay cơ chế đăng nhập thật. Test này chứng minh **hành vi authorization khi principal có tập authority cụ thể**. Để kiểm tra HTTP Basic thực, cần gửi credentials bằng `httpBasic(...)` với `UserDetailsService` hoặc authentication provider được cấu hình cho test; không dùng `@WithMockUser` rồi kết luận đường đi xác thực đã được kiểm chứng.

### Kiểm tra nhiều persona trong một test

Nếu cần đối chiếu các principal mà không tạo nhiều phương thức, dùng `user()` và `anonymous()` trên từng request:

```java
@Test
void roleAndScopeHaveDifferentResults() throws Exception {
    mvc.perform(get("/api/reports").with(anonymous()))
       .andExpect(status().isUnauthorized());

    mvc.perform(get("/api/reports").with(user("admin").roles("ADMIN")))
       .andExpect(status().isForbidden());

    mvc.perform(get("/api/reports").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
       .andExpect(status().isOk());

    mvc.perform(get("/admin/audit").with(
            user("operator").authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN"),
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
       .andExpect(status().isOk());
}
```

`user("admin").roles("ADMIN")` thêm tiền tố role theo quy ước. `user("reader").authorities(...)` sử dụng đúng các authority được truyền vào. Khi cần principal vừa có role vừa có scope, cấp cả hai chuỗi authority như trường hợp `operator`.

Đảm bảo bộ kiểm thử thực sự áp dụng security filters: `@WebMvcTest`/`@AutoConfigureMockMvc` với Spring Security cấu hình phù hợp, hoặc `MockMvcBuilders` có tích hợp `springSecurity()` khi tạo builder thủ công. Nếu bỏ qua filters, endpoint có thể trả `200` khiến test phân quyền cho kết quả sai.

## 9. Kiểm tra SecurityContext và dấu vết phân quyền

Khi test bị `403` ngoài dự kiến, nên quan sát **authority thực tế** đã gắn vào principal thay vì phỏng đoán từ tên role:

```java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void mockAdminHasRolePrefixedAuthority() {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    assertThat(auth.isAuthenticated()).isTrue();
    assertThat(auth.getName()).isEqualTo("alice");
    assertThat(auth.getAuthorities())
        .extracting(GrantedAuthority::getAuthority)
        .contains("ROLE_ADMIN");
}
```

Ví dụ dùng AssertJ. Phạm vi test trên Servlet sử dụng `SecurityContextHolder` được Spring Security Test chuẩn bị cho phương thức có `@WithMockUser`. Trong WebFlux, authentication chủ yếu được truyền qua **Reactor Context**; không lấy `ThreadLocal SecurityContextHolder` làm bằng chứng rằng principal đã tồn tại trong toàn bộ reactive pipeline.

Trong test HTTP, có thể kiểm tra Authentication bằng bộ so khớp hỗ trợ Spring Security Test hoặc ghi nhận danh tính ở một endpoint fixture có kiểm soát. Tránh log credentials, access token hoặc thông tin nhận dạng nhạy cảm chỉ để debug quyền.

### Method security dùng cùng các chuỗi quyền

`@PreAuthorize` thường áp dụng chính sách lên method:

```java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig { }

@Service
class ReportService {
    @PreAuthorize("hasRole('ADMIN') or hasAuthority('SCOPE_reports.read')")
    public String readReport() {
        return "report";
    }
}
```

Trong cấu hình mặc định, role `ADMIN` ở biểu thức trên cần authority `ROLE_ADMIN`; biểu thức scope cần đúng `SCOPE_reports.read`. Nếu bạn mock toàn bộ `ReportService` trong một `@WebMvcTest`, chính proxy method security ở service thật có thể không chạy. Muốn chứng minh `@PreAuthorize` có hiệu lực, cần test gọi qua bean/proxy Spring thật với method security được bật.

## 10. JWT/OAuth2: kiểm tra authority giả lập và mapping thực

Với OAuth2 Resource Server, `jwt()` của `SecurityMockMvcRequestPostProcessors` cho phép giả lập `JwtAuthenticationToken` ở cấp request:

```java
@Test
void jwtWithReportScopeCanReadReports() throws Exception {
    mvc.perform(get("/api/reports").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
       .andExpect(status().isOk());
}

@Test
void jwtWithoutReportScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/reports").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read"))))
       .andExpect(status().isForbidden());
}
```

Hai ca này xác minh **authorization với authority đã được cấp**, không xác minh khả năng đọc claim `scope`, kiểm tra chữ ký JWT, thời hạn, issuer hay audience. Cụ thể, khi gọi `jwt().authorities(...)`, bạn đã chỉ định kết quả authority và bỏ qua việc phải tự suy ra authority từ một access token thật.

Để kiểm tra **quá trình chuyển claim thành quyền**, cần thực thi converter thực tế hoặc gửi bearer token qua cấu hình Resource Server/decoder phù hợp. Nếu dự án tùy chỉnh converter như:

```java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();
converter.setAuthoritiesClaimName("permissions");
converter.setAuthorityPrefix("PERM_");

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(converter);
```

thì một JWT có claim `permissions` chứa `"reports.read"` sẽ được ánh xạ thành `PERM_reports.read` nếu converter được sử dụng trong Resource Server. Rule tương ứng cần là:

```java
.hasAuthority("PERM_reports.read")
```

Việc khởi tạo converter **chưa đủ**; phải đăng ký nó vào cấu hình xác thực JWT thực sự. Với Servlet, cấu hình thường dùng `oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> jwt.jwtAuthenticationConverter(authenticationConverter)))`. Với Reactive, cần cấu hình bộ chuyển đổi tương ứng theo API Reactive. Kiểm thử integration nên xác minh chuỗi quyền sau conversion và cả token thiếu quyền bị từ chối.

Với **OAuth2 Login** hoặc **OIDC Login** (người dùng đăng nhập qua trình duyệt), dùng `oauth2Login()`/`oidcLogin()` cho MockMvc; WebFlux có `mockOAuth2Login()`/`mockOidcLogin()`. Những fixture này thể hiện principal đã đăng nhập, không tự đồng nghĩa với bearer token dành cho Resource Server. Cần xác định endpoint kiểm tra `ROLE_`, `SCOPE_` hay authority tùy biến rồi cấu hình dữ liệu test tương ứng.

## 11. Reactive/WebFlux: hasRole và hasAuthority có cùng ý nghĩa

Trong WebFlux, chính sách HTTP nằm ở `SecurityWebFilterChain` và `authorizeExchange`:

```java
@Configuration
class ReactiveRoleAuthorityConfig {
    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/admin/audit")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Giả sử `ReactiveExampleController` cung cấp các endpoint trên với giá trị phản hồi như ví dụ Servlet; kiểm thử `WebTestClient` có thể viết:

```java
@WebFluxTest(ReactiveExampleController.class)
@Import(ReactiveRoleAuthorityConfig.class)
class ReactiveRoleAuthorityTest {
    @Autowired WebTestClient client;

    @Test
    void anonymousCannotReadAudit() {
        client.get().uri("/admin/audit")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void adminRoleCanReadAudit() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
              .get().uri("/admin/audit")
              .exchange()
              .expectStatus().isOk();
    }

    @Test
    void plainAdminAuthorityCannotReadAudit() {
        client.mutateWith(mockUser("plain").authorities(
                  new SimpleGrantedAuthority("ADMIN")))
              .get().uri("/admin/audit")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void scopeReaderCanReadReports() {
        client.mutateWith(mockUser("reader").authorities(
                  new SimpleGrantedAuthority("SCOPE_reports.read")))
              .get().uri("/api/reports")
              .exchange()
              .expectStatus().isOk();
    }

    @Test
    void adminWithoutScopeCannotReadReports() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
              .get().uri("/api/reports")
              .exchange()
              .expectStatus().isForbidden();
    }
}
```

Ở Reactive, `mockUser` đến từ `SecurityMockServerConfigurers`; còn ở Servlet, `user` đến từ `SecurityMockMvcRequestPostProcessors`. Nếu test dựng `WebTestClient` thủ công, cần tích hợp security để đi qua chain; một test chỉ gọi handler mà bỏ qua `SecurityWebFilterChain` sẽ không chứng minh phân quyền.

Với JWT Reactive, dùng `mockJwt()` để thiết lập authority:

```java
client.mutateWith(mockJwt().authorities(
          new SimpleGrantedAuthority("SCOPE_reports.read")))
      .get().uri("/api/reports")
      .exchange()
      .expectStatus().isOk();
```

Giống `jwt()` bên Servlet, `mockJwt()` hữu ích khi kiểm tra quyền, nhưng **không thay thế** bài test decoder và kiểm tra bearer token thật.

## 12. CSRF, 401 và 403: ba điều rất dễ lẫn nhau

Ngay cả khi role đã đúng, `POST`, `PUT`, `PATCH` hoặc `DELETE` có thể bị `403` vì **thiếu hoặc sai CSRF token** trong ứng dụng có CSRF protection. Vì vậy, bài test role trên endpoint ghi dữ liệu phải gửi CSRF hợp lệ để cô lập điều kiện quyền:

```java
@Test
@WithMockUser(roles = "USER")
void ordinaryUserCannotCreateAdminJobEvenWithCsrf() throws Exception {
    mvc.perform(post("/admin/jobs").with(csrf()))
       .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void adminWithoutCsrfIsStillForbidden() throws Exception {
    mvc.perform(post("/admin/jobs"))
       .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void adminWithCsrfCanCreateJob() throws Exception {
    mvc.perform(post("/admin/jobs").with(csrf()))
       .andExpect(status().isAccepted());
}
```

Phân biệt:

| Kết quả | Ý nghĩa thường gặp trong cấu hình ví dụ | Điểm cần xác minh |
| --- | --- | --- |
| `401 Unauthorized` | Request chưa được xác thực với HTTP Basic hoặc xác thực thất bại | `AuthenticationEntryPoint` và cơ chế xác thực |
| `403 Forbidden` | Đã xác thực nhưng thiếu authority; cũng có thể thiếu/sai CSRF | Security filter nào từ chối, tập authority và trạng thái CSRF |
| `302 Found` | Form login có thể chuyển người ẩn danh đến trang đăng nhập | Header `Location` và cấu hình đăng nhập |
| `200`/`202` | Security cho request đi tiếp, handler xử lý thành công | Body, status thực tế và tác dụng phụ |

Nếu test anonymous `POST /admin/jobs` không gửi CSRF, `CsrfFilter` có thể trả `403` trước bước xác thực. Muốn kỳ vọng `401` trong cấu hình HTTP Basic này, hãy gửi **CSRF hợp lệ** rồi kiểm tra đường đi xác thực. Với Resource Server hoàn toàn stateless được cấu hình bỏ CSRF phù hợp, kỳ vọng phải bám sát chính sách triển khai.

## 13. Sổ tay chẩn đoán sai lệch role/authority

Khi một bài test phân quyền cho kết quả bất ngờ, hãy kiểm tra theo thứ tự:

1. **Chính sách yêu cầu chuỗi nào?** `hasRole("ADMIN")` → `ROLE_ADMIN` trong cấu hình mặc định; `hasAuthority("ADMIN")` → `ADMIN` chính xác.
2. **Principal thực sự có gì?** Kiểm tra `Authentication.getAuthorities()`, loại `Authentication` và danh tính đang được sử dụng.
3. **Nguồn authority là gì?** `@WithMockUser(roles)`, `@WithMockUser(authorities)`, `user().roles()`, JWT converter hay dữ liệu từ authentication provider.
4. **Có mapping role/claim không?** Kiểm tra cấu hình converter, tiền tố và claim; đừng mặc định `ROLE_ADMIN`, `SCOPE_reports.read` có thể thay thế nhau.
5. **Matcher nào được áp dụng?** Rule được xét theo thứ tự trong `authorizeHttpRequests`/`authorizeExchange`; matcher rộng có thể khiến rule hẹp không chạy.
6. **Đang kiểm thử URL hay method?** `@PreAuthorize` chỉ được xác minh nếu request/lời gọi đi qua proxy có method security được bật.
7. **Bộ lọc nào đã từ chối trước?** Với request ghi dữ liệu, loại trừ lỗi CSRF trước khi kết luận thiếu role.
8. **Client có chạy qua security không?** Đặc biệt khi dựng `MockMvc` hoặc `WebTestClient` thủ công.

| Hiện tượng | Khả năng cao | Hướng sửa hoặc phép thử xác nhận |
| --- | --- | --- |
| `@WithMockUser(authorities = "ADMIN")` nhận `403` với `hasRole("ADMIN")` | Sai tiền tố | Dùng `roles = "ADMIN"` hoặc authority `ROLE_ADMIN` |
| `@WithMockUser(roles = "ADMIN")` nhận `403` với `hasAuthority("ADMIN")` | Fixture tạo `ROLE_ADMIN` | Chọn `hasRole` hoặc khai báo authority `ADMIN` tường minh |
| JWT có `scope: reports.read` nhưng `hasRole("reports.read")` trả `403` | Scope được ánh xạ sang `SCOPE_reports.read` | Dùng `hasAuthority("SCOPE_reports.read")` hoặc đổi converter và chính sách nhất quán |
| Admin không qua endpoint yêu cầu role USER | Không có role hierarchy mặc định | Cấp quyền/`hasAnyRole`/hierarchy rõ ràng |
| Test quyền PASS nhưng token sai chữ ký vẫn được chấp nhận trong test | Test dùng `jwt()` để giả lập principal | Thêm integration test qua JWT decoder thật |
| Request ghi dữ liệu luôn `403`, kể cả admin | Thiếu/sai CSRF | Thêm `csrf()` hợp lệ trước khi thay đổi quyền |
| Anonymous đi qua endpoint bảo vệ | Filter chain không được tích hợp hoặc matcher mở rộng | Xác minh `springSecurity()` và thứ tự rule |

Không nên sửa test bằng cách đổi `403` thành `200` hoặc bổ sung role tùy ý cho đến khi xanh. Hãy xác định **hợp đồng quyền** trước, rồi điều chỉnh chính sách hoặc fixture để phản ánh đúng hợp đồng đó.

## 14. Thực hành: viết một ma trận quyền không phụ thuộc tên vai trò

Cho API quản lý hóa đơn:

- `GET /public/plans`: công khai.
- `GET /api/invoices`: người đã xác thực và có `SCOPE_invoices.read`.
- `POST /api/invoices`: người đã xác thực và có `SCOPE_invoices.write`; nếu CSRF bật thì cần token hợp lệ.
- `GET /admin/users`: `ROLE_ADMIN`.
- `POST /admin/users/42/disable`: `ROLE_ADMIN` và CSRF hợp lệ trong cấu hình dùng session.

Hãy làm các bước sau:

1. Viết `SecurityFilterChain` hoặc `SecurityWebFilterChain` với matcher riêng theo method/URL, đặt rule hẹp trước và kết thúc bằng `denyAll`.
2. Tạo năm persona: anonymous, `ROLE_USER`, `ROLE_ADMIN`, `SCOPE_invoices.read`, và principal có cả `ROLE_ADMIN` lẫn `SCOPE_invoices.write`. Lập ma trận kết quả kỳ vọng cho từng endpoint.
3. Dùng `@WithMockUser(roles = "ADMIN")` và `@WithMockUser(authorities = "ROLE_ADMIN")` để chứng minh hai fixture đều qua rule `hasRole("ADMIN")`. Thử thêm `authorities = "ADMIN"` để chứng minh ca âm.
4. Với API hóa đơn, dùng principal chỉ có `SCOPE_invoices.read`, chỉ có `SCOPE_invoices.write` và có cả hai để kiểm tra rằng mỗi scope cấp đúng phần việc của mình.
5. Với `POST`, thử CSRF hợp lệ, thiếu và sai token. Giữ danh tính đủ quyền trong bài test CSRF; giữ CSRF hợp lệ trong bài test role/scope.
6. Nếu hệ thống sử dụng JWT, bổ sung một integration test chứng minh converter thật tạo authority đúng từ claim của token, và token thiếu scope bị từ chối.

**Tiêu chí hoàn thành:** mọi ca dương và âm đều chạy qua lớp security thực tế; test phân quyền so khớp đúng **chuỗi authority sau ánh xạ**; role và scope không được hiểu là đồng nghĩa; các ca `403` chỉ được kết luận là thiếu quyền sau khi đã loại trừ CSRF và lỗi cấu hình test.
