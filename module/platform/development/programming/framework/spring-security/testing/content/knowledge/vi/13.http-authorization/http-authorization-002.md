# Tài nguyên công khai, tài nguyên cần đăng nhập và tài nguyên theo quyền

## 1. Ba mức truy cập cần phân biệt

Một ứng dụng Spring Security thường cung cấp nhiều loại tài nguyên: trang giới thiệu cho mọi khách truy cập, hồ sơ chỉ dành cho người đăng nhập, và chức năng quản trị chỉ dành cho người có quyền phù hợp. Trong kiểm thử HTTP, ba loại này phải được diễn tả thành **hành vi có thể quan sát**: request của ai được đi tiếp, request của ai bị chặn, và bị chặn bởi lý do nào.

Trong module **SPRING_SECURITY_TESTING**, chúng ta dùng `spring-security-test` để kiểm chứng chính sách đó trên ứng dụng **Servlet** với `MockMvc` và **Reactive** với `WebTestClient`. Các danh tính có thể được tạo bằng `@WithMockUser`, `SecurityContext` giả lập hoặc các bộ hỗ trợ JWT/OAuth2/OIDC. Cần hiểu rõ phạm vi: giả lập principal giúp kiểm thử **phân quyền**; kiểm thử quy trình xác thực thật còn cần kiểm tra thông tin đăng nhập, filter và bộ xác minh token tương ứng.

| Loại tài nguyên | Quy tắc Spring Security | Ai được phép? | Ví dụ |
| --- | --- | --- | --- |
| **Công khai** | `permitAll()` | Cả khách ẩn danh lẫn người đã xác thực, nếu request vượt qua các bộ lọc bảo vệ liên quan | `GET /public/catalog` |
| **Cần đăng nhập** | `authenticated()` | Mọi principal đã được xác thực; chưa yêu cầu role cụ thể | `GET /api/me` |
| **Theo quyền** | `hasRole(...)`, `hasAuthority(...)` hoặc quy tắc tùy chỉnh | Chỉ principal có role, authority hoặc điều kiện nghiệp vụ được yêu cầu | `GET /api/reports`, `DELETE /api/users/42` |

Ba mức trên không tương ứng đơn giản với ba HTTP status cố định. Kết quả của một request còn phụ thuộc cơ chế đăng nhập, CSRF, định tuyến và mã thành công do controller trả về. Vì thế, một ca kiểm thử cần mô tả đầy đủ **HTTP method, URL, danh tính, quyền, điều kiện request và kết quả mong đợi**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Chọn `permitAll`, `authenticated`, `hasRole` và `hasAuthority` đúng với hợp đồng truy cập của từng endpoint.
2. Viết kiểm thử chứng minh tài nguyên công khai thực sự truy cập được khi **không có danh tính**.
3. Kiểm tra tài nguyên yêu cầu đăng nhập bằng người ẩn danh và người đã xác thực, kể cả người dùng không có role đặc biệt.
4. Kiểm tra tài nguyên theo quyền với ít nhất một ca được phép và một ca bị từ chối vì thiếu quyền.
5. Phân biệt `401`, `403`, redirect đăng nhập và lỗi CSRF, tránh kết luận sai khi một test âm cho kết quả `403`.
6. Áp dụng các nguyên tắc tương tự trong `MockMvc`, `WebTestClient`, JWT/OAuth2/OIDC, đồng thời biết giới hạn của các danh tính giả lập.

## 2. Một API ví dụ có đủ ba mức truy cập

Giả sử một hệ thống quản lý người dùng và báo cáo có hợp đồng HTTP:

| Method | Endpoint | Mức truy cập | Phản hồi khi thành công |
| --- | --- | --- | --- |
| `GET` | `/public/catalog` | Công khai | `200 OK` |
| `GET` | `/api/me` | Đã xác thực | `200 OK` |
| `PATCH` | `/api/me` | Đã xác thực và có CSRF hợp lệ trong cấu hình ví dụ | `204 No Content` |
| `GET` | `/api/reports` | Có authority `SCOPE_reports.read` | `200 OK` |
| `DELETE` | `/api/users/{id}` | Có role `ADMIN` và CSRF hợp lệ | `204 No Content` |
| Các request khác | Bất kỳ | Từ chối theo chính sách mặc định | Phụ thuộc danh tính và cơ chế xử lý lỗi |

Ở đây `SCOPE_reports.read` là một **authority cụ thể**, thường dùng cho OAuth2 access token có scope `reports.read`. Một người mang `ROLE_ADMIN` không tự động có authority đó. Đây là lựa chọn chính sách có chủ ý nhằm minh họa sự khác nhau giữa role và scope.

Để các kết quả `401`/`403` trong ví dụ nhất quán, chúng ta dùng **HTTP Basic** cho phần Servlet/Reactive thông thường, giữ **CSRF bật theo mặc định** và giả định các controller bên dưới thực sự tồn tại. Ứng dụng dùng form login có thể trả `302` để chuyển đến trang đăng nhập, trong khi Resource Server Bearer token thường trả `401` với challenge Bearer khi thiếu xác thực.

## 3. Cấu hình phân quyền Servlet

Với Spring MVC/Servlet, điểm cấu hình là bean `SecurityFilterChain`:

```java
@Configuration
class AccessSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // 1. Tài nguyên công khai
                .requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()

                // 2. Tài nguyên có yêu cầu quyền rõ ràng
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.DELETE, "/api/users/{id}")
                    .hasRole("ADMIN")

                // 3. Tài nguyên cho mọi người đã đăng nhập
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.PATCH, "/api/me").authenticated()

                // 4. Mặc định không mở quyền cho URL ngoài dự kiến
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Cấu hình này quy định **ai được gọi** chứ chưa quyết định nghiệp vụ trả về dữ liệu gì. Controller tối giản sau tạo các route để thử nghiệm:

```java
@RestController
class AccessController {
    @GetMapping("/public/catalog")
    String catalog() {
        return "public-catalog";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @PatchMapping("/api/me")
    ResponseEntity<Void> updateMe() {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/reports")
    String report() {
        return "protected-report";
    }

    @DeleteMapping("/api/users/{id}")
    ResponseEntity<Void> deleteUser(@PathVariable long id) {
        return ResponseEntity.noContent().build();
    }
}
```

Các đoạn Java lược bỏ `import` và các lớp cấu hình ứng dụng không liên quan để tập trung vào chính sách HTTP. Controller này là fixture minh họa, không thực hiện cập nhật hoặc xóa dữ liệu. Trong hệ thống thật, cần bổ sung kiểm thử tác dụng phụ, kiểm tra quyền sở hữu tài nguyên và thao tác dữ liệu.

### Vì sao nên khai báo matcher cụ thể trước?

Spring Security xử lý các rule trong `authorizeHttpRequests` **theo thứ tự**. Rule khớp đầu tiên quyết định chính sách áp dụng cho request. Chẳng hạn:

```java
.requestMatchers("/api/**").authenticated()
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports.read")
```

Đặt matcher rộng `/api/**` ở trước khiến request báo cáo bị xử lý bởi rule `authenticated()` trước khi rule scope có cơ hội chạy. Người đã đăng nhập nhưng không có `reports.read` có thể đọc báo cáo. Cần đặt các quy tắc hẹp và nhạy cảm trước rule tổng quát, hoặc ghi rõ từng tổ hợp method/path như ví dụ chính.

`anyRequest().denyAll()` đóng các đường dẫn chưa có trong chính sách. Tuy vậy, với người **ẩn danh**, một lần từ chối từ tầng authorization có thể dẫn đến `401` qua authentication entry point; với người đã xác thực thường là `403`. Muốn khẳng định request bị chặn vì một rule cụ thể, cần kiểm tra thêm matcher và danh tính, không chỉ nhìn mã phản hồi.

## 4. `permitAll()`: tài nguyên công khai thực sự có nghĩa gì?

`permitAll()` bỏ yêu cầu quyền ở **bước ủy quyền URL** cho request khớp rule. Nó **không** tắt toàn bộ Spring Security:

- Request vẫn có thể đi qua các security filter khác, như xử lý security headers, CSRF và cơ chế xác thực được cấu hình.
- Nếu một endpoint công khai dùng phương thức thay đổi trạng thái như `POST`, CSRF vẫn có thể từ chối request nếu CSRF được bật và không có token hợp lệ.
- Controller vẫn có thể trả `400`, `404` hoặc lỗi nghiệp vụ; `permitAll` không bảo đảm mọi request sẽ thành công.
- Quy tắc công khai chỉ áp dụng cho các HTTP method và đường dẫn mà matcher chỉ rõ. `GET /public/catalog` không mặc nhiên cho phép `DELETE /public/catalog`.

Với các endpoint công khai, ca kiểm thử quan trọng nhất là gọi **không cung cấp người dùng**. Nếu chỉ dùng `@WithMockUser` thì bài test chứng minh người đã đăng nhập truy cập được, chưa chứng minh khách ẩn danh cũng vào được.

Không đồng nhất `permitAll()` với loại trừ request khỏi toàn bộ filter chain bằng `WebSecurityCustomizer#ignoring`. Trong đa số trường hợp HTTP, giữ request đi qua security chain và cấp `permitAll` sẽ duy trì các bảo vệ chung của Spring Security. Nếu ứng dụng dùng nhiều `SecurityFilterChain` với các `securityMatcher` khác nhau, cần xác định request có đi vào chain dự kiến không trước khi kết luận rằng `permitAll` là rule đang chạy.

**Trường hợp thường gặp:** `GET /login`, ảnh/CSS/JavaScript tĩnh, tài liệu công khai hoặc health endpoint có thể mở cho anonymous. Tuy nhiên, `/actuator/health`, các endpoint quản trị và toàn bộ `/api/**` không nên được coi là công khai chỉ vì tên đường dẫn; quyền truy cập phải xuất phát từ yêu cầu thực tế của hệ thống.

## 5. `authenticated()`: cần danh tính nhưng chưa cần role đặc biệt

Rule `authenticated()` chỉ yêu cầu principal được xem là **đã xác thực**. Một người có `ROLE_USER`, `ROLE_ADMIN` hoặc tập authority khác đều có thể đi tiếp nếu Authentication đã được chấp nhận. Ngược lại, một anonymous principal do Spring Security gắn vào context **không** được tính là người đã đăng nhập cho rule này.

Một số DSL khác:

| Rule | Ý nghĩa khi dùng |
| --- | --- |
| `authenticated()` | Chấp nhận người đã xác thực nói chung |
| `fullyAuthenticated()` | Yêu cầu xác thực đầy đủ, không chỉ thông qua remember-me |
| `rememberMe()` | Xác định kiểu xác thực remember-me nếu ứng dụng sử dụng cơ chế này |
| `anonymous()` | Chỉ cho anonymous principal; khác với tài nguyên công khai cho tất cả mọi người |
| `permitAll()` | Cho phép cả anonymous và người đã đăng nhập tại bước phân quyền URL |

Ví dụ, hồ sơ `GET /api/me` phù hợp với `authenticated()` nếu **mọi** tài khoản hợp lệ đều có quyền xem chính hồ sơ mình. Dù vậy, khi lấy hồ sơ từ cơ sở dữ liệu, server phải dùng định danh đáng tin cậy từ `Authentication`; không được lấy một tham số `userId` do client tự gửi rồi xem như bằng chứng chủ sở hữu.

Nếu endpoint là `GET /api/users/{id}`, `authenticated()` thường **chưa đủ**: người đã đăng nhập có thể truyền ID của người khác. Khi đó phải kiểm tra thêm quyền sở hữu, tenant hoặc quyền quản trị ở tầng thích hợp.

## 6. `hasRole()` và `hasAuthority()`: tài nguyên theo quyền

Đã đăng nhập không đồng nghĩa được phép thực hiện mọi thao tác. Spring Security lưu tập `GrantedAuthority` trong `Authentication` và kiểm tra các điều kiện được yêu cầu.

| Cách khai báo rule | Authority cần có | Trường hợp phù hợp |
| --- | --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` | Trang/endpoint chỉ dành cho quản trị viên |
| `hasAnyRole("USER", "ADMIN")` | `ROLE_USER` **hoặc** `ROLE_ADMIN` | Chức năng dành cho một nhóm role |
| `hasAuthority("SCOPE_reports.read")` | Chính xác `SCOPE_reports.read` | API yêu cầu OAuth2 scope đọc báo cáo |
| `hasAnyAuthority("orders.read", "orders.admin")` | Một trong hai chuỗi được chỉ ra | Phân quyền chi tiết theo authority của ứng dụng |

Mặc định, `hasRole("ADMIN")` tìm authority có tiền tố `ROLE_`; không viết `hasRole("ROLE_ADMIN")` trong cấu hình dùng tiền tố mặc định. `hasAuthority(...)` so sánh trực tiếp giá trị authority, không tự thêm tiền tố. Chính sách role và scope là hai trục quyền khác nhau: một tài khoản quản trị không tự động có `SCOPE_reports.read` nếu ứng dụng không cấp quyền hoặc ánh xạ phù hợp.

Không nên suy diễn rằng có scope `reports.write` thì cũng có `reports.read`. Nếu nghiệp vụ yêu cầu quyền bao hàm hoặc thứ bậc, hãy cấu hình rõ ràng bằng authorization manager, role hierarchy hoặc dịch vụ kiểm quyền, rồi có kiểm thử riêng cho quy tắc đó.

## 7. Lập ma trận danh tính và kỳ vọng

Ta dùng bốn nhóm request:

- **Anonymous:** không gửi thông tin xác thực.
- **User:** đã xác thực, có `ROLE_USER`.
- **Admin:** đã xác thực, có `ROLE_ADMIN` nhưng không có scope báo cáo.
- **Report reader:** đã xác thực, có `SCOPE_reports.read` nhưng không có `ROLE_ADMIN`.

Với HTTP Basic và controller ở mục 3, ma trận dự kiến là:

| Request | Anonymous | User | Admin | Report reader |
| --- | ---: | ---: | ---: | ---: |
| `GET /public/catalog` | `200` | `200` | `200` | `200` |
| `GET /api/me` | `401` | `200` | `200` | `200` |
| `PATCH /api/me` | `401` | `204` | `204` | `204` |
| `GET /api/reports` | `401` | `403` | `403` | `200` |
| `DELETE /api/users/42` | `401` | `403` | `204` | `403` |

**Điều kiện bắt buộc khi đọc hai dòng `PATCH` và `DELETE`:** mọi request trong hai dòng đều có **CSRF token hợp lệ**. Nếu cố tình bỏ token với CSRF bật, request ghi dữ liệu có thể nhận `403` **trước khi** Spring Security đánh giá vai trò hay yêu cầu đăng nhập. Một kiểm thử âm chỉ kiểm tra `403` nhưng quên CSRF rất dễ cho kết quả xanh sai nguyên nhân.

Mỗi hàng là một *hợp đồng bảo mật*. Tên test nên diễn đạt hành vi cần chứng minh, chẳng hạn `anonymousCannotReadProfile`, `ordinaryUserCannotReadReports` hoặc `reportReaderCanReadReports`. Với endpoint có dữ liệu hoặc tác dụng phụ thật, kiểm tra thêm rằng request bị từ chối **không** trả nội dung nhạy cảm và **không** sửa dữ liệu.

## 8. Kiểm thử Servlet bằng MockMvc và spring-security-test

Để dùng `@WithMockUser`, `user()`, `anonymous()`, `csrf()` và `jwt()`, dự án cần dependency `spring-security-test` ở test scope:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Với Spring Boot, `@WebMvcTest` tạo test slice MVC, còn `@Import` thêm cấu hình security đang được kiểm tra:

```java
@WebMvcTest(AccessController.class)
@Import(AccessSecurityConfig.class)
class AccessAuthorizationMvcTest {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCanReadPublicCatalog() throws Exception {
        mvc.perform(get("/public/catalog"))
           .andExpect(status().isOk())
           .andExpect(content().string("public-catalog"));
    }

    @Test
    void anonymousCannotReadMyProfile() throws Exception {
        mvc.perform(get("/api/me"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void loggedInUserCanReadOwnProfile() throws Exception {
        mvc.perform(get("/api/me"))
           .andExpect(status().isOk())
           .andExpect(content().string("alice"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotReadReports() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminWithoutScopeStillCannotReadReports() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void userWithReportScopeCanReadReports() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isOk())
           .andExpect(content().string("protected-report"));
    }

    @Test
    @WithMockUser(roles = "USER")
    void ordinaryUserCannotDeleteAccountEvenWithCsrf() throws Exception {
        mvc.perform(delete("/api/users/42").with(csrf()))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDeleteAccountWithCsrf() throws Exception {
        mvc.perform(delete("/api/users/42").with(csrf()))
           .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(roles = "USER")
    void loggedInUserCanUpdateProfileWithCsrf() throws Exception {
        mvc.perform(patch("/api/me").with(csrf()))
           .andExpect(status().isNoContent());
    }
}
```

Cần các static import phù hợp từ `MockMvcRequestBuilders` (`get`, `patch`, `delete`), `MockMvcResultMatchers` (`status`, `content`) và `SecurityMockMvcRequestPostProcessors` (`csrf`). Các lớp test dùng JUnit Jupiter (`@Test`), Spring Boot Test (`@WebMvcTest`) và Spring Security Test (`@WithMockUser`). Nếu ứng dụng còn các dependency khác của controller, cần mock hoặc import chúng theo đúng ranh giới của test slice.

Khi dùng `@AutoConfigureMockMvc` trong full context, hoặc `@WebMvcTest` với security filters được cấu hình, các request đi qua filter chain. Nếu tự dựng `MockMvcBuilders`, hãy áp dụng `springSecurity()` vào builder; bằng không test có thể bỏ qua security và cho kết quả sai.

### Tạo danh tính riêng theo từng request

`@WithMockUser` thiết lập danh tính ở cấp phương thức test. Khi một phương thức cần đối chiếu nhiều danh tính, dùng request postprocessor để mỗi request có bối cảnh độc lập:

```java
@Test
void sameEndpointWithDifferentIdentities() throws Exception {
    mvc.perform(get("/api/reports").with(anonymous()))
       .andExpect(status().isUnauthorized());

    mvc.perform(get("/api/reports").with(user("alice").roles("USER")))
       .andExpect(status().isForbidden());

    mvc.perform(get("/api/reports").with(
            user("reader").authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
       .andExpect(status().isOk());
}
```

Các processor trên tạo principal giả lập trong request; chúng không gửi thông tin đăng nhập thật lên bộ xác thực. Với test cần kiểm chứng HTTP Basic, hãy cung cấp `UserDetailsService` phù hợp và gửi `httpBasic("alice", "password")` để đi qua `BasicAuthenticationFilter`. Với JWT, tương tự phải phân biệt một test dùng `jwt()` với test gửi Bearer token qua bộ giải mã thật.

## 9. Kiểm tra CSRF riêng để tránh kết luận sai

CSRF được bật mặc định trong cấu hình Servlet ví dụ. Một request `GET` thường không cần CSRF; request `POST`, `PUT`, `PATCH` và `DELETE` thường cần token hợp lệ nếu CSRF áp dụng cho đường dẫn đó. `permitAll` hoặc `authenticated` **không tự tắt CSRF**.

```java
@Test
@WithMockUser(roles = "ADMIN")
void missingCsrfBlocksDeletionEvenForAdmin() throws Exception {
    mvc.perform(delete("/api/users/42"))
       .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void invalidCsrfAlsoBlocksDeletion() throws Exception {
    mvc.perform(delete("/api/users/42").with(csrf().useInvalidToken()))
       .andExpect(status().isForbidden());
}

@Test
void anonymousWithCsrfStillNeedsAuthentication() throws Exception {
    mvc.perform(patch("/api/me").with(csrf()))
       .andExpect(status().isUnauthorized());
}
```

Hai bước kiểm thử tách biệt giúp xác định nguyên nhân:

1. **Kiểm tra authorization:** gửi CSRF hợp lệ khi cần, chỉ thay đổi danh tính và authority.
2. **Kiểm tra CSRF:** giữ danh tính có đủ quyền, lần lượt gửi token hợp lệ, thiếu token và token sai.

Một API thuần Bearer token không sử dụng cookie phiên có thể được cấu hình để không áp dụng CSRF ở những endpoint thích hợp. Khi đó phải theo chính sách CSRF **đang triển khai**; không nên áp kỳ vọng về CSRF của ví dụ HTTP Basic/session cho tất cả Resource Server.

## 10. Khi chạy trên WebFlux: cùng ý tưởng, công cụ khác

Ứng dụng Reactive dùng `SecurityWebFilterChain` và `authorizeExchange`. Có thể viết chính sách tương tự:

```java
@Configuration
class ReactiveAccessSecurityConfig {
    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/public/catalog").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.DELETE, "/api/users/{id}")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.PATCH, "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Giả sử ứng dụng có `ReactiveAccessController` cung cấp các endpoint tương ứng. Với Spring Boot có thể dùng `@WebFluxTest` và `WebTestClient`:

```java
@WebFluxTest(ReactiveAccessController.class)
@Import(ReactiveAccessSecurityConfig.class)
class ReactiveAccessAuthorizationTest {
    @Autowired WebTestClient client;

    @Test
    void publicCatalogAllowsAnonymous() {
        client.get().uri("/public/catalog")
              .exchange().expectStatus().isOk();
    }

    @Test
    void anonymousCannotReadProfile() {
        client.get().uri("/api/me")
              .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void anyAuthenticatedUserCanReadProfile() {
        client.mutateWith(mockUser("alice").roles("USER"))
              .get().uri("/api/me")
              .exchange().expectStatus().isOk();
    }

    @Test
    void userWithoutReportScopeIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
              .get().uri("/api/reports")
              .exchange().expectStatus().isForbidden();
    }

    @Test
    void userWithReportScopeCanReadReports() {
        client.mutateWith(mockUser("reader").authorities(
                  new SimpleGrantedAuthority("SCOPE_reports.read")))
              .get().uri("/api/reports")
              .exchange().expectStatus().isOk();
    }

    @Test
    void adminCanDeleteWithCsrf() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
              .mutateWith(csrf())
              .delete().uri("/api/users/42")
              .exchange().expectStatus().isNoContent();
    }
}
```

Ở WebFlux, `mockUser()` và `csrf()` đến từ `SecurityMockServerConfigurers`; ở Servlet, `user()` và `csrf()` đến từ `SecurityMockMvcRequestPostProcessors`. Chúng có cùng mục đích nhưng thuộc hai bộ API khác nhau.

Nếu tự cấu hình `WebTestClient` bằng builder, hãy chắc chắn test client thực sự được kết nối với ứng dụng và được tích hợp `springSecurity()`. Trong WebFlux, authentication/security context còn phải đi qua **Reactor Context** đúng cách; không dựa vào `SecurityContextHolder` dạng `ThreadLocal` của Servlet để suy ra danh tính trong một reactive pipeline.

## 11. JWT, OAuth2 và OIDC: quyền của token khác role đăng nhập

Một **OAuth2 Resource Server** thường nhận Bearer access token. Sau khi JWT được xác thực, Spring Security có thể chuyển scope của token thành các authority có tiền tố `SCOPE_`. Chẳng hạn scope `reports.read` tương ứng với authority `SCOPE_reports.read` trong cấu hình mặc định thông dụng.

Phần phân quyền của ví dụ vẫn giữ nguyên:

```java
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports.read")
```

Tuy nhiên, cơ chế xác thực khi chạy thật cần được cấu hình phù hợp, ví dụ `oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))` và `JwtDecoder` tương ứng. Test **quyền sau khi có principal** có thể dùng `jwt()` trong MockMvc:

```java
@Test
void jwtWithReportAuthorityCanReadReports() throws Exception {
    mvc.perform(get("/api/reports").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
       .andExpect(status().isOk());
}

@Test
void jwtWithoutReportAuthorityIsForbidden() throws Exception {
    mvc.perform(get("/api/reports").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read"))))
       .andExpect(status().isForbidden());
}
```

Với Reactive:

```java
client.mutateWith(mockJwt().authorities(
          new SimpleGrantedAuthority("SCOPE_reports.read")))
      .get().uri("/api/reports")
      .exchange().expectStatus().isOk();
```

`jwt()` và `mockJwt()` tạo Authentication để **mô phỏng người đã qua xác thực**. Chúng không chứng minh rằng JWT hết hạn bị từ chối, chữ ký được kiểm tra đúng, issuer/audience hợp lệ hoặc decoder ánh xạ claim thành authority đúng trong request HTTP thật. Những điều đó phải được kiểm thử riêng qua cấu hình Resource Server và decoder phù hợp.

Với **OAuth2 Login** và **OIDC Login** trên trình duyệt, các tiện ích `oauth2Login()`, `oidcLogin()` (Servlet) hoặc `mockOAuth2Login()`, `mockOidcLogin()` (Reactive) hỗ trợ tạo principal sau đăng nhập. Các principal này khác với Bearer access token của Resource Server. Chọn công cụ giả lập theo **cơ chế xác thực mà endpoint thực tế sử dụng**, và kiểm thử role/authority/claim mà chính sách đang đọc, không chỉ kiểm tra rằng danh tính tồn tại.

### Ma trận khi dùng Bearer token

Nếu chuyển endpoint báo cáo sang Resource Server và giữ rule `SCOPE_reports.read`:

| Request | Kỳ vọng thông thường | Phần cần kiểm chứng |
| --- | --- | --- |
| Không có Bearer token | `401` | Entry point yêu cầu xác thực |
| Bearer token hợp lệ nhưng thiếu scope | `403` | Quy tắc authority |
| Bearer token hợp lệ có scope đọc báo cáo | `200` | Được phép truy cập |
| Token hết hạn, sai chữ ký, issuer không hợp lệ | `401` | Decoder và quy trình xác thực **thật** |

Kết quả cụ thể còn phụ thuộc exception handling và cách ứng dụng cấu hình Resource Server. Không viết test token bất hợp lệ chỉ bằng `jwt()` rồi kết luận rằng xác thực chữ ký hoặc thời hạn đã được kiểm chứng.

## 12. Lưu ý về quyền sở hữu và ranh giới kiểm thử

Ba mức truy cập ở URL chưa đủ để giải quyết tất cả câu hỏi nghiệp vụ. Ví dụ, `GET /api/me` có thể chỉ cần `authenticated()` vì luôn đọc từ danh tính của request. Nhưng với `GET /api/users/42` hoặc `PATCH /api/documents/17`, điều kiện thường là **người sở hữu tài nguyên hoặc người có quyền quản trị**.

Một cách phổ biến là áp dụng method security tại service:

```java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig { }

@Service
class DocumentService {
    @PreAuthorize("hasRole('ADMIN') or @documentPermission.canRead(#id, authentication.name)")
    public DocumentDto getDocument(long id) {
        return loadDocument(id);
    }
}
```

Ví dụ giả định bean `documentPermission` được triển khai để kiểm tra chủ sở hữu dựa trên dữ liệu tin cậy của server. Muốn kiểm chứng chính sách này, test phải thực sự đi qua service được Spring quản lý cùng method security. Nếu `@WebMvcTest` mock `DocumentService`, lời gọi `@PreAuthorize` trong service có thể không hề được thực thi; test chỉ chứng minh quyền ở URL, chưa chứng minh quyền sở hữu.

Tương tự, có thể có nhiều `SecurityFilterChain`/`SecurityWebFilterChain` phục vụ các vùng khác nhau, ví dụ web session và API token. `securityMatcher` chọn chain nào áp dụng; `requestMatchers`/`pathMatchers` bên trong chain chọn chính sách của request. Nhầm hai tầng này có thể khiến quy tắc đặt đúng cú pháp nhưng không hề bảo vệ endpoint.

## 13. Chẩn đoán nhanh khi một ca kiểm thử cho kết quả sai

| Hiện tượng | Nguyên nhân nên kiểm tra trước | Cách cô lập |
| --- | --- | --- |
| Anonymous truy cập tài nguyên bảo vệ vẫn nhận `200` | Test chưa gắn security filter, hoặc matcher cấp `permitAll` quá rộng | Kiểm tra cấu hình `MockMvc`/`WebTestClient` và thứ tự matcher |
| Anonymous nhận `302` thay vì `401` | Ứng dụng dùng form login | Xác minh `Location` trỏ đến login, hoặc cấu hình cơ chế API cần thử |
| `USER` có thể đọc endpoint admin | Matcher `authenticated` hoặc `/api/**` chạy trước `hasRole` | Đưa rule quyền cụ thể lên trước, chạy lại ca âm |
| Admin nhận `403` tại endpoint scope | Có `ROLE_ADMIN` nhưng không có `SCOPE_reports.read` | Kiểm tra toàn bộ GrantedAuthority của principal |
| Admin gửi `DELETE` và nhận `403` | Thiếu/sai CSRF hoặc thiếu role | Gửi CSRF hợp lệ trước, sau đó thay đổi riêng role |
| Anonymous gửi `POST` không CSRF nhận `403` | CSRF filter từ chối trước authentication | Gửi CSRF hợp lệ để kiểm tra kỳ vọng `401` |
| Test HTTP trả `200` dù ownership bị sai | Service thực bị mock, hoặc không kích hoạt method security | Kiểm thử service/proxy và dữ liệu ownership thật |
| Mock JWT được chấp nhận nhưng token thật bị từ chối | Fixture giả lập bỏ qua decoder, chữ ký, issuer, audience hoặc mapping scope | Viết integration test qua Resource Server thực tế |

Đừng đổi kỳ vọng `401` thành `403` chỉ để test xanh. Hãy xác định request đang thất bại ở bước **xác thực**, **CSRF**, **ủy quyền URL**, **ủy quyền nghiệp vụ** hay **routing**. Mỗi bước cần một phép thử có chủ đích.

## 14. Bài thực hành: phân loại tài nguyên và viết test âm

Một dịch vụ quản lý khóa học có các endpoint:

| Endpoint | Chính sách yêu cầu |
| --- | --- |
| `GET /courses` | Công khai |
| `GET /students/me` | Bất kỳ người đăng nhập |
| `POST /enrollments` | Người đăng nhập; CSRF phù hợp cấu hình |
| `GET /admin/enrollments` | Role `ADMIN` |
| `GET /api/analytics` | Authority `SCOPE_analytics.read` |

Yêu cầu thực hành:

1. Viết các `requestMatchers` hoặc `pathMatchers` chính xác theo method và URL, kết thúc bằng `denyAll` cho request không nằm trong chính sách.
2. Tạo ma trận anonymous, `ROLE_STUDENT`, `ROLE_ADMIN`, principal chỉ có `SCOPE_analytics.read`; ghi mã kỳ vọng theo cơ chế xác thực đã chọn.
3. Viết ít nhất một test anonymous truy cập `/courses` thành công và một test anonymous truy cập `/students/me` bị yêu cầu xác thực.
4. Kiểm chứng `ROLE_STUDENT` bị từ chối `/admin/enrollments` trong khi `ROLE_ADMIN` được phép; kiểm chứng chỉ principal có `SCOPE_analytics.read` được truy cập `/api/analytics`.
5. Với `POST /enrollments`, tách test phân quyền và CSRF: gửi token hợp lệ để kiểm tra người đăng nhập; sau đó thử thiếu/sai token khi principal đã được phép.

**Tiêu chí hoàn thành:** mọi tài nguyên được phân loại theo đúng chính sách, các test âm thất bại vì **đúng lý do**, client kiểm thử thực sự đi qua security chain, và không có đường dẫn/phương thức nào vô tình được cấp quyền bởi matcher rộng. Khi đã hoàn thành các ca này, người học có nền tảng để mở rộng ma trận sang sở hữu tài nguyên, tenant, JWT scopes và các quyền nghiệp vụ chuyên biệt.
