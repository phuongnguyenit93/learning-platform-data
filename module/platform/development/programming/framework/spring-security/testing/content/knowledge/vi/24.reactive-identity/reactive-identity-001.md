# mockUser với tên, vai trò hoặc UserDetails

## 1. Tạo danh tính Reactive cho từng request kiểm thử

Khi kiểm thử ứng dụng Spring WebFlux, một endpoint có thể yêu cầu người dùng đã đăng nhập, một role cụ thể hoặc một authority nghiệp vụ. Ta cần tạo được các danh tính khác nhau để kiểm tra cả ca được phép và bị từ chối.

Trong **SPRING_SECURITY_TESTING**, mục tiêu là kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Người học sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào `SecurityMockServerConfigurers.mockUser()` dành cho WebFlux: tạo người dùng mặc định, đổi username, gán role/authority hoặc cung cấp một đối tượng `UserDetails`.

Sau bài học, bạn có thể:

- Dùng `mockUser()` để tạo người dùng mặc định trong `WebTestClient`.
- Dùng `mockUser("alice")` để đặt username cho principal.
- Dùng `roles("ADMIN")` và `authorities(...)` đúng quy ước tiền tố.
- Truyền một đối tượng `UserDetails` có sẵn bằng `mockUser(userDetails)`.
- Phân biệt danh tính giả lập với quá trình xác thực bằng password, `ReactiveUserDetailsService` hoặc JWT decoder.
- Kiểm tra `Authentication` và `SecurityContext` trong luồng Reactive.

## 2. mockUser() tạo ra gì?

`mockUser()` là tiện ích kiểm thử của package:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
```

Nó cấu hình `ServerWebExchange` cho request kiểm thử với một `UserDetails` và một `UsernamePasswordAuthenticationToken` đã được xác thực. Giá trị mặc định:

| Thuộc tính | Giá trị mặc định |
| --- | --- |
| Username | `user` |
| Password trong đối tượng UserDetails | `password` |
| Authorities | `ROLE_USER` |
| Authentication | `UsernamePasswordAuthenticationToken` đã authenticated |
| Principal | Đối tượng triển khai `UserDetails` |

Ví dụ:

```java
client.mutateWith(mockUser())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
```

Nếu endpoint cần người dùng đã xác thực, principal mặc định có thể truy cập. Nếu endpoint yêu cầu `ROLE_ADMIN` hoặc authority khác, người dùng mặc định sẽ bị từ chối.

### Đây là danh tính được dựng cho test

`mockUser()` không gửi username/password qua form login hoặc HTTP Basic. Nó không gọi `ReactiveAuthenticationManager`, không truy vấn `ReactiveUserDetailsService` và không kiểm tra password bằng `PasswordEncoder`. Test nhận một Authentication giả lập đã được đánh dấu authenticated để tập trung vào authorization.

Vì vậy, dùng `mockUser()` để chứng minh:

- `authenticated()` cho phép principal đã xác thực.
- `hasRole("ADMIN")` chỉ cho phép principal có authority role phù hợp.
- `hasAuthority("invoice:read")` yêu cầu authority đúng chuỗi.
- Controller/service nhận đúng username và authorities đã dựng.

Không dùng riêng test này để kết luận form login, HTTP Basic, password hashing hoặc quá trình đăng nhập thật hoạt động đúng. Những luồng đó cần test riêng với authentication provider thực tế.

## 3. Đổi username bằng mockUser(String)

Khi chỉ cần thay danh tính nhưng giữ password và role mặc định, truyền username:

```java
client.mutateWith(mockUser("alice"))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .isEqualTo("alice");
```

`mockUser("alice")` vẫn dùng password mặc định `password` và authority mặc định `ROLE_USER`. Đây là cách ngắn gọn khi test ownership, audit hoặc nội dung phản hồi phụ thuộc username.

Ví dụ, controller có thể đọc tên principal từ Reactive Security Context:

```java
@RestController
class IdentityController {
    @GetMapping("/api/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

Trong WebFlux, `SecurityContext` được truyền qua Reactor Context. `ReactiveSecurityContextHolder` lấy Authentication từ context của publisher hiện tại; không dựa vào `SecurityContextHolder` dạng ThreadLocal như trong ứng dụng Servlet.

## 4. Gán role bằng roles(...)

`roles(...)` nhận tên role chưa có tiền tố. Spring Security tự thêm `ROLE_`:

```java
client.mutateWith(mockUser("alice").roles("ADMIN"))
    .get()
    .uri("/api/admin")
    .exchange()
    .expectStatus().isOk();
```

Principal trên có authority `ROLE_ADMIN`. Vì vậy, nó thỏa:

```java
.pathMatchers("/api/admin").hasRole("ADMIN")
```

Không truyền tiền tố vào `roles`:

```java
// Sai quy ước: roles tự thêm ROLE_
mockUser("alice").roles("ROLE_ADMIN");
```

Hãy dùng `roles("ADMIN")`. Nếu bạn muốn chỉ định chuỗi authority chính xác, dùng `authorities(...)`.

### Role mặc định không tự bao hàm role khác

`mockUser()` mặc định tạo `ROLE_USER`. Nó không tự có `ROLE_ADMIN`, `ROLE_MANAGER` hoặc scope API. Nếu endpoint cần role khác, hãy khai báo role đó rõ ràng.

| Cấu hình test | Authority được tạo |
| --- | --- |
| `mockUser()` | `ROLE_USER` |
| `mockUser("alice")` | `ROLE_USER` |
| `mockUser("alice").roles("ADMIN")` | `ROLE_ADMIN` |
| `mockUser("alice").roles("MANAGER", "AUDITOR")` | `ROLE_MANAGER`, `ROLE_AUDITOR` |

## 5. Gán authority chính xác bằng authorities(...)

Role là một quy ước đặt tên authority. Với quyền nghiệp vụ hoặc scope, thường nên dùng `authorities(...)` để truyền chính xác chuỗi cần kiểm tra:

```java
client.mutateWith(mockUser("alice").authorities(
        new SimpleGrantedAuthority("invoice:read"),
        new SimpleGrantedAuthority("invoice:approve")))
    .get()
    .uri("/api/invoices")
    .exchange()
    .expectStatus().isOk();
```

`authorities` không tự thêm `ROLE_`. Các giá trị được dùng nguyên trạng:

| Cấu hình | Authority |
| --- | --- |
| `roles("ADMIN")` | `ROLE_ADMIN` |
| `authorities("ADMIN")` | `ADMIN` |
| `authorities("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `authorities("SCOPE_orders.read")` | `SCOPE_orders.read` |
| `authorities("invoice:read")` | `invoice:read` |

Ví dụ, `hasRole("ADMIN")` theo mặc định kiểm tra `ROLE_ADMIN`. Vì vậy, `authorities("ADMIN")` không thỏa điều kiện đó. Ngược lại, `hasAuthority("ADMIN")` kiểm tra đúng chuỗi `ADMIN`.

Bạn cũng có thể truyền trực tiếp chuỗi authority:

```java
client.mutateWith(mockUser("alice")
        .authorities("ROLE_USER", "invoice:read"))
    .get()
    .uri("/api/invoices")
    .exchange()
    .expectStatus().isOk();
```

Hoặc truyền collection/đối tượng `GrantedAuthority` nếu test cần xây dựng quyền động:

```java
Collection<GrantedAuthority> permissions = List.of(
    new SimpleGrantedAuthority("ROLE_USER"),
    new SimpleGrantedAuthority("invoice:read")
);

client.mutateWith(mockUser("alice").authorities(permissions))
    .get()
    .uri("/api/invoices")
    .exchange()
    .expectStatus().isOk();
```

Khi một principal cần cả role và authority nghiệp vụ, dùng `authorities` và liệt kê đầy đủ các chuỗi, gồm cả tiền tố role:

```java
mockUser("alice").authorities(
    "ROLE_USER",
    "invoice:read",
    "invoice:approve"
);
```

Không giả định `roles` và `authorities` sẽ tự cộng dồn nếu gọi nối tiếp. Hãy chọn một cách khai báo cho tập quyền cuối cùng; khi dùng `authorities`, ghi cả các role cần thiết dưới dạng `ROLE_...`.

## 6. Tùy chỉnh password và trạng thái UserDetails

`UserExchangeMutator` cho phép tùy chỉnh thêm:

```java
client.mutateWith(mockUser("alice")
        .password("test-only-password")
        .roles("ADMIN"))
    .get()
    .uri("/api/admin")
    .exchange()
    .expectStatus().isOk();
```

Password được lưu trong đối tượng `UserDetails` dùng làm principal của test. Nó không được gửi đến authentication provider và không được xác minh. Không cần dùng password production hoặc dữ liệu bí mật trong test.

Builder cũng có các tùy chọn trạng thái như `disabled(boolean)`, `accountLocked(boolean)`, `accountExpired(boolean)` và `credentialsExpired(boolean)`. Cần hiểu giới hạn: `mockUser` dựng một Authentication đã authenticated từ UserDetails được cung cấp; nó không chạy các bước kiểm tra account status mà `ReactiveAuthenticationManager`/authentication provider thường thực hiện khi đăng nhập. Vì vậy, đặt `disabled(true)` không phải cách đáng tin cậy để kiểm thử rằng login thật bị từ chối.

Nếu mục tiêu là kiểm tra tài khoản disabled/locked, hãy dùng test tích hợp với authentication manager và `ReactiveUserDetailsService` thật hoặc fixture tương ứng, gửi credentials qua cơ chế xác thực thực tế và xác minh lỗi đăng nhập.

## 7. Truyền một UserDetails có sẵn bằng mockUser(UserDetails)

Khi ứng dụng có principal triển khai `UserDetails` riêng, hoặc test đã tạo sẵn user fixture, dùng overload:

```java
mockUser(UserDetails userDetails)
```

Ví dụ với `User` chuẩn của Spring Security:

```java
UserDetails reviewer = User.withUsername("reviewer")
    .password("unused-in-this-test")
    .authorities(
        new SimpleGrantedAuthority("ROLE_AUDITOR"),
        new SimpleGrantedAuthority("reports:export"))
    .build();

client.mutateWith(mockUser(reviewer))
    .get()
    .uri("/api/reports/export")
    .exchange()
    .expectStatus().isOk();
```

Overload này dùng chính đối tượng `UserDetails` được truyền làm principal để tạo `UsernamePasswordAuthenticationToken`. Authorities lấy từ `userDetails.getAuthorities()`; username lấy từ `userDetails.getUsername()`.

### Khi ứng dụng có custom principal

Một số ứng dụng dùng lớp principal riêng triển khai `UserDetails` để chứa thêm dữ liệu domain, ví dụ mã nhân viên hoặc tenant:

```java
final class EmployeePrincipal implements UserDetails {
    private final String username;
    private final String employeeCode;
    private final Collection<? extends GrantedAuthority> authorities;

    EmployeePrincipal(
            String username,
            String employeeCode,
            Collection<? extends GrantedAuthority> authorities) {
        this.username = username;
        this.employeeCode = employeeCode;
        this.authorities = authorities;
    }

    public String getEmployeeCode() {
        return this.employeeCode;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return this.authorities;
    }

    @Override
    public String getPassword() {
        return "unused-in-this-test";
    }

    @Override
    public String getUsername() {
        return this.username;
    }

    @Override
    public boolean isAccountNonExpired() { return true; }

    @Override
    public boolean isAccountNonLocked() { return true; }

    @Override
    public boolean isCredentialsNonExpired() { return true; }

    @Override
    public boolean isEnabled() { return true; }
}
```

Tạo fixture:

```java
UserDetails employee = new EmployeePrincipal(
    "alice",
    "EMP-1042",
    List.of(new SimpleGrantedAuthority("ROLE_REVIEWER"))
);

client.mutateWith(mockUser(employee))
    .get()
    .uri("/api/employee-code")
    .exchange()
    .expectStatus().isOk();
```

Controller/service có thể ép kiểu principal về `EmployeePrincipal` khi cần truy cập thuộc tính domain. Trong production, việc ép kiểu phải phù hợp với authentication mechanism thật; test principal không được che giấu sự không nhất quán giữa kiểu principal của test và kiểu principal do hệ thống đăng nhập phát ra.

### mockUser(UserDetails) không gọi UserDetailsService

Overload nhận `UserDetails` không tra cứu username trong database hoặc gọi `ReactiveUserDetailsService`. Bạn truyền trực tiếp đối tượng đã chuẩn bị. Đây là lợi thế khi muốn tạo fixture riêng cho một ca, nhưng cũng có nghĩa test không xác minh quá trình load user từ kho dữ liệu.

Nếu cần xác minh user lookup, password, trạng thái tài khoản hoặc mapping quyền từ database, viết test riêng gọi authentication manager thực tế.

## 8. Cấu hình WebTestClient để chạy qua Spring Security

Các mutator của `SecurityMockServerConfigurers` được dùng với `WebTestClient`. Với test slice:

```java
@WebFluxTest(ReactiveIdentityController.class)
@Import(ReactiveIdentitySecurityConfig.class)
class ReactiveMockUserTest {
    @Autowired
    WebTestClient client;
}
```

Khi tự dựng client từ application context, áp dụng Spring Security test support:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

`springSecurity()` tích hợp các thành phần hỗ trợ kiểm thử Spring Security vào `WebTestClient`. Nếu client được tạo thủ công mà bỏ qua bước này, mutator hoặc security filter chain có thể không hoạt động như kỳ vọng.

Import tĩnh thường dùng:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

Trong `@WebFluxTest` hoặc `@SpringBootTest`, hãy xác minh client được cấu hình đi qua `SecurityWebFilterChain`. Không dùng một client chỉ bind trực tiếp vào controller handler rồi kết luận authorization đã được kiểm tra.

## 9. Ví dụ hoàn chỉnh: role, authority và identity endpoint

Security configuration:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveIdentitySecurityConfig {
    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/me").authenticated()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/reports/export")
                    .hasAuthority("reports:export")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Controller fixture:

```java
@RestController
class ReactiveIdentityController {
    @GetMapping("/public")
    Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping("/api/admin")
    Mono<String> admin() {
        return Mono.just("admin");
    }

    @GetMapping("/api/reports/export")
    Mono<String> export() {
        return Mono.just("export");
    }
}
```

Test:

```java
@WebFluxTest(ReactiveIdentityController.class)
@Import(ReactiveIdentitySecurityConfig.class)
class ReactiveMockUserAuthorizationTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        this.client = WebTestClient.bindToApplicationContext(this.context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void anonymousCanReadPublicEndpoint() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void anonymousCannotReadIdentity() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void defaultMockUserHasUsernameUser() {
        client.mutateWith(mockUser())
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user");
    }

    @Test
    void usernameCanBeCustomized() {
        client.mutateWith(mockUser("alice"))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void defaultUserCannotAccessAdmin() {
        client.mutateWith(mockUser())
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanAccessAdmin() {
        client.mutateWith(mockUser("alice").roles("ADMIN"))
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void rawAdminAuthorityDoesNotSatisfyHasRole() {
        client.mutateWith(mockUser("alice").authorities("ADMIN"))
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void exactBusinessAuthorityCanExport() {
        client.mutateWith(mockUser("reviewer")
                    .authorities("reports:export"))
            .get().uri("/api/reports/export")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void adminRoleDoesNotAutomaticallyGrantExportAuthority() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get().uri("/api/reports/export")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Các ca này chứng minh username, role và authority độc lập với nhau. `ROLE_ADMIN` không tự động cấp `reports:export`; nếu chính sách cần admin được export, hãy cấp authority hoặc cấu hình policy thể hiện điều đó.

## 10. Dùng UserDetails fixture trong WebTestClient

Khi test cần principal phức tạp hơn builder username/roles, chuẩn bị `UserDetails` trước:

```java
@Test
void suppliedUserDetailsBecomesPrincipal() {
    UserDetails reviewer = User.withUsername("reviewer")
        .password("unused")
        .authorities(
            new SimpleGrantedAuthority("ROLE_AUDITOR"),
            new SimpleGrantedAuthority("reports:export"))
        .build();

    client.mutateWith(mockUser(reviewer))
        .get().uri("/api/reports/export")
        .exchange()
        .expectStatus().isOk();
}
```

Nếu endpoint cần đọc principal tùy chỉnh, kiểm tra kiểu và thuộc tính principal trong controller/service test fixture. Ví dụ, một endpoint nội bộ chỉ phục vụ test có thể trả về:

```java
@GetMapping("/api/principal-type")
Mono<String> principalType() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getPrincipal)
        .map(principal -> principal.getClass().getSimpleName());
}
```

Khi dùng `mockUser(reviewer)` với `User` chuẩn, principal là đối tượng `UserDetails` đã truyền. Khi truyền `EmployeePrincipal`, principal giữ kiểu custom đó.

## 11. @WithMockUser và mockUser khác nhau thế nào?

Spring Security Reactive Test hỗ trợ cả annotation `@WithMockUser` và mutator `mockUser()` khi `WebTestClient` đã tích hợp Spring Security test support.

Ví dụ annotation:

```java
@Test
@WithMockUser(username = "alice", roles = "ADMIN")
void annotationCanSetReactiveTestUser() {
    client.get().uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
}
```

Ví dụ mutator:

```java
@Test
void requestCanUseMockUserMutator() {
    client.mutateWith(mockUser("alice").roles("ADMIN"))
        .get().uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
}
```

| Cách | Điểm mạnh | Khi nên chọn |
| --- | --- | --- |
| `@WithMockUser` | Ngắn gọn, đặt danh tính ở cấp test method/class | Test có danh tính cố định, cần đọc test nhanh |
| `mockUser()` | Gắn danh tính trực tiếp vào WebTestClient request; dễ tạo nhiều principal trong cùng test | Cần đổi username/role theo request hoặc dùng nhiều request khác nhau |
| `mockUser(UserDetails)` | Giữ principal là đối tượng UserDetails được chuẩn bị | Ứng dụng yêu cầu custom principal |

Nếu một test gửi nhiều request với các danh tính khác nhau, mutator theo từng request giúp nhìn thấy rõ request nào đang dùng principal nào. Không giả định danh tính của một request sẽ tự trở thành danh tính của request tiếp theo.

## 12. Phân biệt mockUser với JWT và OAuth2 login

`mockUser()` tạo `UsernamePasswordAuthenticationToken` với principal kiểu `UserDetails`. Nó phù hợp khi authorization dựa trên username, role và authorities.

Nếu ứng dụng hoặc service yêu cầu principal là `JwtAuthenticationToken`, cần claim như `sub`/`tenant_id` hoặc kiểm tra converter JWT, dùng `mockJwt()` sẽ phù hợp hơn:

```java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("alice")
            .claim("tenant_id", "tenant-a"))
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
```

Tương tự, ứng dụng OAuth2 Login hoặc OIDC Login có thể cần `mockOAuth2Login()` hoặc `mockOidcLogin()`. Chọn mutator theo **loại Authentication mà ứng dụng thực sự nhận**, không chỉ theo tên người dùng.

Các mutator JWT/OAuth2/OIDC cũng dựng principal giả lập; chúng không thay thế test chữ ký token, issuer, audience, thời hạn hoặc quá trình login với authorization server thật.

## 13. Các lỗi thường gặp khi dùng mockUser

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `hasRole("ADMIN")` trả `403` | Dùng `authorities("ADMIN")` thay vì `ROLE_ADMIN` | Dùng `roles("ADMIN")` hoặc `authorities("ROLE_ADMIN")` |
| Endpoint yêu cầu `reports:export` bị từ chối | Principal chỉ có `ROLE_ADMIN` | Cấp authority `reports:export` riêng |
| Controller nhận username `user` thay vì username mong muốn | Dùng `mockUser()` mặc định | Dùng `mockUser("alice")` |
| Custom principal bị ép kiểu lỗi | Test dùng `mockUser("alice")` nên principal là UserDetails mặc định | Dùng `mockUser(customUserDetails)` |
| Test không chứng minh password login | `mockUser` tạo Authentication đã authenticated | Gửi credentials qua authentication provider thật |
| UserDetails disabled vẫn đi qua authorization | Mutator không chạy account-status checks của provider | Test ReactiveAuthenticationManager với user disabled |
| Mutator không tác dụng | WebTestClient chưa tích hợp Spring Security test support | Áp dụng `springSecurity()` khi bind client thủ công |
| Test trả kết quả khác request thật | Test principal khác loại Authentication production | Dùng mockJwt/mockOAuth2Login hoặc integration test phù hợp |
| Request không bị chặn dù thiếu role | Test không đi qua `SecurityWebFilterChain` | Kiểm tra cách bind WebTestClient và filter chain |

### Checklist trước khi hoàn thành test

- Username có đúng với danh tính cần kiểm tra không?
- Test đang dùng role hay authority? Chuỗi cuối cùng là gì?
- Nếu cần nhiều quyền, đã liệt kê đầy đủ trong một tập authority chưa?
- Endpoint có yêu cầu custom principal hoặc JWT claim không?
- WebTestClient có đi qua Spring Security test support và security chain không?
- Test có đang nhầm principal giả lập với quá trình đăng nhập thật không?
- Có ca dương và ca âm cho cùng endpoint không?

## 14. Thực hành: kiểm thử quyền của người duyệt hóa đơn

API có các endpoint:

| Endpoint | Chính sách |
| --- | --- |
| `GET /api/me` | Đã xác thực |
| `GET /api/invoices` | `invoice:read` |
| `POST /api/invoices/{id}/approve` | `invoice:approve` |
| `GET /api/admin/audit` | `ROLE_ADMIN` |
| Request còn lại | Từ chối |

Hãy thực hiện:

1. Dùng `mockUser()` để xác minh username mặc định và role mặc định.
2. Dùng `mockUser("alice")` để kiểm tra endpoint trả username hiện tại.
3. Dùng `mockUser("reviewer").roles("REVIEWER")` và xác minh nó tạo `ROLE_REVIEWER`.
4. Dùng `authorities("invoice:read")` để kiểm tra endpoint đọc hóa đơn; xác minh role REVIEWER không tự cấp quyền này.
5. Dùng `authorities("invoice:approve")` để kiểm tra thao tác duyệt; principal chỉ có quyền đọc phải bị từ chối.
6. Tạo một `UserDetails` có cả `ROLE_REVIEWER` và `invoice:approve`, rồi truyền qua `mockUser(userDetails)`.
7. Tạo custom `UserDetails` có employee code và xác minh controller/service đọc được principal đúng kiểu.
8. Viết một integration test riêng với `ReactiveAuthenticationManager` để xác minh password hoặc account status nếu nghiệp vụ yêu cầu.

**Tiêu chí hoàn thành:** test tạo đúng username, role và authority; phân biệt `ROLE_` với chuỗi permission; custom `UserDetails` được giữ làm principal; WebTestClient đi qua security chain; các test không nhầm việc dựng Authentication giả lập với xác thực credentials thật.

## 15. Tài liệu tham khảo

- [Spring Security Reference — Testing Authentication for WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — UserExchangeMutator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.UserExchangeMutator.html)
