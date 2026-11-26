# Thứ tự rule và chính sách mặc định cho request không khớp

## 1. Vì sao thứ tự matcher có thể mở nhầm quyền?

Giả sử API có hai vùng:

- `/api/admin/**`: chỉ quản trị viên được truy cập.
- `/api/**`: người có scope đọc API được truy cập.

Nếu cấu hình rule tổng quát trước rule quản trị:

```java
.requestMatchers("/api/**").hasAuthority("SCOPE_api.read")
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

request `GET /api/admin/audit` cũng khớp `/api/**`. Rule đầu tiên đã quyết định quyền, nên rule `hasRole("ADMIN")` phía sau không được xét. Một người có `SCOPE_api.read` nhưng không có `ROLE_ADMIN` có thể truy cập audit.

Spring Security đánh giá các rule authorization **theo thứ tự khai báo**. Với các matcher chồng lấp, matcher đầu tiên khớp sẽ quyết định AuthorizationManager được dùng. Vì vậy, rule cụ thể và nhạy cảm phải đứng trước rule tổng quát.

Trong module **SPRING_SECURITY_TESTING**, người học dùng `spring-security-test` để kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế trên Servlet/Reactive bằng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào hai câu hỏi:

1. **Request khớp rule nào đầu tiên?**
2. **Nếu không có rule nào khớp, chính sách cuối cùng là gì?**

Sau bài học, bạn có thể sắp xếp matcher đúng, chọn fallback phù hợp, phân biệt authorization rule với filter chain, và viết test hồi quy cho cả endpoint đã khai báo lẫn request chưa được dự kiến.

## 2. First-match-wins: rule đầu tiên khớp sẽ được áp dụng

Ví dụ cấu hình đúng:

```java
.authorizeHttpRequests(auth -> auth
    // Vùng quản trị: rule cụ thể, nhạy cảm
    .requestMatchers("/api/admin/**").hasRole("ADMIN")

    // Endpoint công khai nằm bên trong /api
    .requestMatchers("/api/public/**").permitAll()

    // Rule tổng quát cho API đọc
    .requestMatchers(HttpMethod.GET, "/api/**")
        .hasAuthority("SCOPE_api.read")

    // Mọi request còn lại bị từ chối
    .anyRequest().denyAll()
)
```

Hãy đọc từ trên xuống:

| Request | Matcher đầu tiên khớp | Chính sách |
| --- | --- | --- |
| `GET /api/admin/audit` | `/api/admin/**` | `ROLE_ADMIN` |
| `POST /api/admin/users` | `/api/admin/**` | `ROLE_ADMIN` |
| `GET /api/public/status` | `/api/public/**` | Công khai |
| `GET /api/orders` | `GET /api/**` | `SCOPE_api.read` |
| `POST /api/orders` | Không có rule trước fallback | `denyAll` |
| `GET /internal/health` | Không có rule trước fallback | `denyAll` |

Matcher `/api/admin/**` phải nằm trước `/api/**` vì mọi đường dẫn admin cũng thuộc vùng API tổng quát. Tương tự, nếu `/api/public/**` cần công khai, rule đó phải đứng trước rule `GET /api/**`.

### Rule không được cộng dồn

Không nên hình dung các rule như một danh sách điều kiện mà request phải vượt qua tất cả. Trong DSL authorization thông thường, một request không nhận đồng thời cả `hasRole("ADMIN")` và `hasAuthority("SCOPE_api.read")` chỉ vì nó khớp hai pattern. Rule đầu tiên khớp được chọn.

Nếu muốn người gọi phải có **cả hai** quyền, hãy kết hợp điều kiện trong cùng một authorization manager hoặc dùng policy nghiệp vụ rõ ràng. Ví dụ về mặt ý nghĩa:

```text
ROLE_ADMIN AND SCOPE_api.read
```

Đây là logic AND; nó khác với hai matcher riêng biệt đặt nối tiếp nhau. Cũng không nhầm với `hasAnyRole`/`hasAnyAuthority`, vốn biểu diễn lựa chọn OR trong nhóm quyền.

## 3. Thứ tự cụ thể trước tổng quát

Một quy tắc thực hành hữu ích:

1. Matcher cho vùng quản trị hoặc thao tác nhạy cảm.
2. Matcher cho endpoint công khai có phạm vi hẹp.
3. Matcher có điều kiện method/path cụ thể.
4. Matcher cho vùng API tổng quát.
5. Fallback áp dụng cho mọi request còn lại.

Đây là cách tổ chức dễ đọc, không phải thứ tự máy móc bắt buộc cho mọi ứng dụng. Điều cần bảo đảm là **mọi cặp matcher chồng lấp đều có thứ tự được chủ ý**.

Ví dụ sai khác:

| Cấu hình | Hậu quả |
| --- | --- |
| `/api/**` trước `/api/admin/**` | Rule tổng quát che rule admin |
| `GET /api/**` trước `GET /api/public/**` | Endpoint public GET không còn được permit |
| `/api/**` với `authenticated()` trước matcher `DELETE /api/users/**` với `hasRole("ADMIN")` | Người dùng đã đăng nhập có thể vượt rule admin nếu request khớp rule tổng quát |
| `anyRequest().permitAll()` ở cuối | Mọi request không được mô tả trước đó đều được mở |
| `anyRequest().authenticated()` ở cuối | Endpoint mới thêm vào có thể tự động mở cho mọi người đăng nhập |

Đừng chỉ xem cấu hình có đủ matcher hay không. Hãy kiểm tra **vị trí** của chúng và viết test cho các path có thể khớp nhiều rule.

## 4. Fallback: denyAll, authenticated hay permitAll?

`anyRequest()` là matcher cuối cùng đại diện cho mọi request trong phạm vi filter chain đang cấu hình mà chưa được rule trước đó xử lý. Quyết định sau `anyRequest()` định nghĩa chính sách mặc định:

| Fallback | Người anonymous | Người đã xác thực | Ý nghĩa |
| --- | --- | --- | --- |
| `anyRequest().denyAll()` | Bị từ chối (thường qua entry point thành `401` hoặc redirect) | Bị từ chối `403` | Mặc định đóng |
| `anyRequest().authenticated()` | Cần xác thực (thường `401` hoặc redirect) | Được phép qua bước URL authorization | Mặc định mở cho mọi principal đã đăng nhập |
| `anyRequest().permitAll()` | Được phép qua bước URL authorization | Được phép qua bước URL authorization | Mặc định công khai |

Trong DSL `authorizeHttpRequests` hiện đại, nếu không có matcher nào khớp và không khai báo `anyRequest()`, `RequestMatcherDelegatingAuthorizationManager` cũng từ chối request. Tuy vậy, nên khai báo tường minh `anyRequest().denyAll()` để chính sách mặc định hiển thị ngay trong cấu hình và được kiểm thử như một phần hợp đồng. Với WebFlux, dùng `anyExchange().denyAll()` tương ứng.

### Khi nào dùng denyAll?

Đây là lựa chọn phù hợp cho API có danh sách endpoint được duyệt rõ ràng:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/profile/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
```

Nếu một endpoint mới được thêm vào mà chưa có chính sách, request không tự động được cấp quyền chỉ vì người gọi đã đăng nhập. Nhóm phát triển phải chủ động thêm rule và test tương ứng.

### Khi nào dùng authenticated?

Một ứng dụng web có thể chủ ý yêu cầu đăng nhập cho tất cả trang còn lại:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**", "/login").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated())
```

Đây là chính sách hợp lệ nếu **mọi route mới** thực sự phải yêu cầu đăng nhập. Tuy nhiên, nó không có nghĩa mọi endpoint đã được phân quyền đầy đủ: bất kỳ người dùng đăng nhập nào cũng vượt qua fallback, trừ khi có rule cụ thể hơn.

### Vì sao tránh permitAll làm fallback?

`anyRequest().permitAll()` khiến endpoint mới được thêm vào có thể công khai ngoài dự kiến. Nếu chỉ một vài endpoint được mở, hãy chỉ định từng path/method và dùng `denyAll` cho phần còn lại.

### Fallback ở lớp authorization không tắt các filter khác

`permitAll()` chỉ cho phép request vượt qua **bước authorization URL**. Request vẫn có thể bị filter khác từ chối, ví dụ:

- CSRF chặn request ghi dữ liệu thiếu token.
- CORS không chấp nhận origin/method/header của browser.
- Authentication filter xử lý credentials sai theo cơ chế xác thực.
- Firewall/container từ chối request không hợp lệ trước khi tới authorization.

Vì vậy, không suy luận rằng `permitAll` đồng nghĩa mọi request sẽ nhận `200`. Nó chỉ nói rằng rule authorization này không yêu cầu principal có quyền cụ thể.

## 5. Request không khớp và route chưa tồn tại

Một request không khớp rule cụ thể sẽ rơi vào fallback nếu có `anyRequest()` trong chain:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers(HttpMethod.GET, "/api/**")
    .hasAuthority("SCOPE_api.read")
.anyRequest().denyAll()
```

Với cấu hình trên, `GET /new-feature`, `POST /api/orders` và `DELETE /api/orders/42` đều rơi vào `denyAll` nếu chưa có rule tương ứng.

### Request không có controller mapping vẫn có thể bị security từ chối trước

Giả sử `GET /internal/feature` không có controller. Với `anyRequest().denyAll()`:

- Người đã xác thực thường nhận `403` do authorization từ chối.
- Anonymous có thể nhận `401` hoặc redirect tùy AuthenticationEntryPoint.
- Controller không nhất thiết được gọi, nên MVC chưa có cơ hội trả `404`.

Nếu fallback là `authenticated()`, anonymous vẫn bị yêu cầu đăng nhập; người đã xác thực có thể đi qua security và sau đó nhận `404` vì không có handler. Với `permitAll()`, request được qua authorization và routing mới quyết định `404` hay kết quả khác.

Điều này quan trọng khi viết test: **`403` từ fallback denyAll không chứng minh route tồn tại**; `404` cũng không chứng minh endpoint đã được bảo vệ. Cần kiểm tra tầng đang tạo ra phản hồi.

## 6. Một cấu hình Servlet hoàn chỉnh

Giả sử controller cung cấp:

| Endpoint | Chính sách |
| --- | --- |
| `GET /api/public/status` | Công khai |
| `GET /api/orders` | `SCOPE_api.read` |
| `GET /api/admin/audit` | `ROLE_ADMIN` |
| `GET /api/profile` | Chỉ cần xác thực |
| Các request còn lại | Từ chối |

Cấu hình:

```java
@Configuration
class OrderedAuthorizationConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Cụ thể và nhạy cảm trước
                .requestMatchers("/api/admin/**").hasRole("ADMIN")

                // Public hẹp trước rule API tổng quát
                .requestMatchers("/api/public/**").permitAll()

                // Profile chỉ cần đăng nhập: đặt trước rule GET tổng quát
                .requestMatchers("/api/profile/**").authenticated()

                // Rule theo method
                .requestMatchers(HttpMethod.GET, "/api/**")
                    .hasAuthority("SCOPE_api.read")

                // Mọi request chưa được liệt kê bị từ chối
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Các rule được xếp theo thứ tự cụ thể trước tổng quát: admin, public, profile, rồi mới đến GET API. Vì vậy, principal chỉ cần đăng nhập có thể đọc profile mà không cần `SCOPE_api.read`. Nếu profile cũng cần scope đọc, hãy bỏ rule riêng hoặc đổi điều kiện theo hợp đồng API.

## 7. Kiểm thử thứ tự rule bằng MockMvc

Thêm `spring-security-test` ở test scope. Ví dụ dùng `@WebMvcTest`, cấu hình trên và controller fixture:

```java
@RestController
class AuthorizationDemoController {
    @GetMapping("/api/public/status")
    String publicStatus() { return "ok"; }

    @GetMapping("/api/orders")
    String orders() { return "orders"; }

    @GetMapping("/api/admin/audit")
    String audit() { return "audit"; }

    @GetMapping("/api/profile")
    String profile() { return "profile"; }
}

@WebMvcTest(AuthorizationDemoController.class)
@Import(OrderedAuthorizationConfig.class)
class OrderedAuthorizationMvcTest {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCanAccessPublicEndpoint() throws Exception {
        mvc.perform(get("/api/public/status"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_api.read")
    void apiReaderCanReadOrders() throws Exception {
        mvc.perform(get("/api/orders"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_api.read")
    void apiReaderCannotAccessAdminEvenThoughBroadRuleMatches()
            throws Exception {
        mvc.perform(get("/api/admin/audit"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanAccessAdminWithoutApiReadScope() throws Exception {
        mvc.perform(get("/api/admin/audit"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser
    void authenticatedUserCanReadProfile() throws Exception {
        mvc.perform(get("/api/profile"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_api.read")
    void unmatchedAuthenticatedRequestIsDenied() throws Exception {
        mvc.perform(get("/internal/feature"))
           .andExpect(status().isForbidden());
    }

    @Test
    void unmatchedAnonymousRequestNeedsAuthentication() throws Exception {
        mvc.perform(get("/internal/feature"))
           .andExpect(status().isUnauthorized());
    }
}
```

Test quan trọng nhất để bắt lỗi thứ tự là cặp:

- `SCOPE_api.read` gọi `/api/admin/audit` phải nhận `403`.
- `ROLE_ADMIN` gọi cùng endpoint phải nhận `200`.

Nếu rule `/api/**` đứng trước `/api/admin/**`, ca đầu tiên có thể nhận `200` và phát hiện lỗi cấp quyền quá rộng. Ca fallback xác minh endpoint chưa được khai báo không tự động mở cho principal đã xác thực.

`@WithMockUser` tạo principal giả lập để kiểm tra authorization. Nó không kiểm tra HTTP Basic credentials hoặc JWT decoder. Với test slice/full context, bảo đảm Spring Security filter được tích hợp; khi tự dựng `MockMvcBuilders`, áp dụng `springSecurity()`.

### Kiểm thử fallback với các loại danh tính

| Danh tính | Request chưa khai báo | Kỳ vọng với `denyAll` |
| --- | --- | --- |
| Anonymous | `GET /internal/feature` | `401` với HTTP Basic API trong ví dụ |
| Người đã xác thực | `GET /internal/feature` | `403` |
| Admin | `DELETE /internal/feature` | `403` |

Admin không được miễn fallback. Quyền quản trị chỉ áp dụng trong matcher được khai báo; không phải quyền vượt qua mọi chính sách.

## 8. Thử nghiệm có chủ ý: fallback khác nhau tạo kết quả khác nhau

Giả sử cùng một endpoint chưa được khai báo `GET /internal/feature`. Thay đổi fallback sẽ làm hành vi đổi:

| Fallback | Anonymous | User đã đăng nhập | Controller không tồn tại |
| --- | --- | --- | --- |
| `denyAll()` | `401`/redirect | `403` | Không tới MVC routing |
| `authenticated()` | `401`/redirect | Được qua security, sau đó `404` | Có thể tới MVC routing |
| `permitAll()` | Được qua security | Được qua security | Có thể tới MVC routing |

Để kiểm tra `authenticated()`, tạo một cấu hình test riêng hoặc thay fallback trong cấu hình ứng dụng, rồi xác minh user đã đăng nhập nhận `404` cho route không tồn tại. Đừng thay đổi cấu hình production chỉ để làm test xanh; hãy dùng profile/test configuration có chính sách được kiểm tra rõ.

```java
@Test
@WithMockUser
void authenticatedFallbackLetsUnknownRouteReachMvc() throws Exception {
    mvc.perform(get("/internal/feature"))
       .andExpect(status().isNotFound());
}
```

Test trên chỉ đúng khi cấu hình test đang dùng `anyRequest().authenticated()`, không phải cấu hình `denyAll` ở mục trước. Hãy ghi rõ cấu hình nào đang được test để không tạo kỳ vọng mâu thuẫn.

## 9. Nhiều SecurityFilterChain: thứ tự chain khác thứ tự rule

Ứng dụng có thể có nhiều `SecurityFilterChain`, ví dụ API dùng bearer token và web UI dùng form login. Spring Security xét các chain theo thứ tự; **chain đầu tiên có `securityMatcher` khớp request sẽ xử lý request đó**. Các chain sau không được xét tiếp cho request đã chọn chain.

Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .requestMatchers(HttpMethod.GET, "/api/**")
                .hasAuthority("SCOPE_api.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/assets/**", "/login").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

`/api/**` đi vào API chain; fallback `denyAll` của chain đó chỉ áp dụng cho request đã được chain nhận. `/internal/feature` không khớp API chain nên đi tới web chain và có thể được yêu cầu đăng nhập theo fallback của web chain.

Một lỗi thường gặp là đặt chain tổng quát ở `@Order(1)` với matcher mặc định bao phủ mọi request; khi đó chain API ở order sau không bao giờ được chọn. Ngược lại, nếu API chain không có matcher phù hợp và không có chain fallback, request có thể không được bảo vệ bởi chain mà nhóm phát triển mong muốn.

Nếu **không có `SecurityFilterChain` nào khớp request**, `FilterChainProxy` không tự áp dụng fallback `anyRequest()` của một chain khác. Vì vậy, ứng dụng nhiều chain thường cần một chain cuối có phạm vi bao phủ các request còn lại và chính sách rõ ràng. `anyRequest()` chỉ là fallback **bên trong chain đã được chọn**, không phải fallback toàn cục cho mọi chain.

**Không đồng nhất hai loại thứ tự:**

| Loại thứ tự | Phạm vi | Quyết định |
| --- | --- | --- |
| `@Order` của filter chain | Giữa các `SecurityFilterChain` | Request vào chain nào |
| Thứ tự `requestMatchers` | Bên trong một chain | Rule authorization nào được áp dụng |

Test nên có ít nhất một request thuộc API chain và một request thuộc web chain để phát hiện chain tổng quát che chain chuyên biệt.

## 10. Reactive/WebFlux: thứ tự pathMatchers và anyExchange

Với WebFlux, DSL tương ứng là `authorizeExchange`:

```java
@Configuration
class ReactiveAuthorizationConfig {
    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/admin/**").hasRole("ADMIN")
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/profile/**").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/**")
                    .hasAuthority("SCOPE_api.read")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

`anyExchange().denyAll()` là fallback trong chain Reactive. Nó bao phủ các exchange không khớp rule trước đó trong chain đang xử lý, bao gồm method/path chưa được liệt kê.

### Kiểm thử WebTestClient

Giả sử `ReactiveDemoController` có các endpoint tương ứng:

```java
@WebFluxTest(ReactiveDemoController.class)
@Import(ReactiveAuthorizationConfig.class)
class ReactiveAuthorizationOrderTest {
    @Autowired WebTestClient client;

    @Test
    void anonymousCanReadPublicStatus() {
        client.get().uri("/api/public/status")
              .exchange().expectStatus().isOk();
    }

    @Test
    void apiReaderCannotReadAdmin() {
        client.mutateWith(mockUser("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_api.read")))
              .get().uri("/api/admin/audit")
              .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminCanReadAdminWithoutApiScope() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
              .get().uri("/api/admin/audit")
              .exchange().expectStatus().isOk();
    }

    @Test
    void unmatchedAuthenticatedExchangeIsDenied() {
        client.mutateWith(mockUser("reader").authorities(
                    new SimpleGrantedAuthority("SCOPE_api.read")))
              .get().uri("/internal/feature")
              .exchange().expectStatus().isForbidden();
    }

    @Test
    void unmatchedAnonymousExchangeNeedsAuthentication() {
        client.get().uri("/internal/feature")
              .exchange().expectStatus().isUnauthorized();
    }
}
```

Trong WebFlux, `mockUser` thuộc `SecurityMockServerConfigurers`. Với ứng dụng Reactive dùng JWT Resource Server, `mockJwt()` có thể tạo principal cùng authority; test decoder thật cần một luồng kiểm thử riêng. Nếu tự dựng `WebTestClient`, phải bảo đảm client đi qua `SecurityWebFilterChain`.

## 11. Viết test phát hiện matcher chồng lấp

Một cách kiểm thử hữu ích là lập danh sách các path nằm trong nhiều pattern. Ví dụ:

| Path | Matcher tổng quát | Matcher cụ thể | Quy tắc mong muốn |
| --- | --- | --- | --- |
| `/api/admin/audit` | `/api/**` | `/api/admin/**` | Admin |
| `/api/public/status` | `/api/**` | `/api/public/**` | Public |
| `/api/profile` | `/api/**` | `/api/profile/**` | Authenticated |
| `/api/orders` | `/api/**` | Không có | Scope đọc |
| `/internal/feature` | Không có | Không có | Deny all trong API-only chain; tùy chain khác nếu không thuộc API |

Với mỗi path chồng lấp, tạo ít nhất hai principal có quyền khác nhau:

- Principal chỉ có scope tổng quát, không có role đặc biệt.
- Principal có role đặc biệt nhưng không có scope tổng quát.

Nếu test chỉ dùng principal có **cả hai** quyền, cấu hình sai thứ tự có thể vẫn xanh vì principal vượt qua cả rule rộng lẫn rule hẹp. Hai principal tách biệt mới chứng minh được matcher đúng đang quyết định kết quả.

### Test mutation của thứ tự rule

Một cách kiểm chứng tư duy là tạm đổi thứ tự matcher trong test configuration:

```java
// Cấu hình sai để minh họa:
.requestMatchers("/api/**").hasAuthority("SCOPE_api.read")
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Test `apiReaderCannotReadAdmin` phải thất bại vì reader có scope tổng quát được phép vào audit. Nếu một test không phát hiện thay đổi này, bộ test chưa đủ nhạy để bảo vệ chính sách.

Không giữ cấu hình sai trong ứng dụng; mục đích là hiểu vì sao ca hồi quy phải dùng danh tính thiếu quyền đặc biệt.

## 12. Chẩn đoán lỗi và checklist review

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| User scope thường vào được vùng admin | Matcher tổng quát đứng trước matcher admin | Dùng principal chỉ có scope và gọi path admin |
| Admin bị từ chối dù có role | Matcher scope tổng quát khớp trước | Đưa rule admin lên trước; kiểm tra `ROLE_ADMIN` thực tế |
| Endpoint mới tự mở cho user đăng nhập | Fallback `authenticated()` | Xác định endpoint nào thật sự cần login; cân nhắc `denyAll` |
| Request lạ vẫn public | Fallback `permitAll()` hoặc chain khác mở rộng | Kiểm tra tất cả chain và fallback |
| API bị áp dụng form login | Chain web tổng quát đứng trước API chain | Kiểm tra `@Order` và `securityMatcher` |
| `403` dù matcher đúng | Thiếu authority, CSRF hoặc filter khác từ chối | Cô lập từng tầng bằng request có điều kiện hợp lệ |
| Test unknown route nhận `404` thay vì `403` | Fallback đang `authenticated()`/`permitAll()` hoặc request không vào chain dự kiến | Xác nhận chain và fallback thực tế |
| Reactive và Servlet có kết quả khác | Cấu hình `anyExchange`/`anyRequest`, matcher hoặc test client khác nhau | So sánh rule và bảo đảm client đi qua đúng security chain |

Trước khi merge thay đổi authorization, review các câu hỏi:

- Matcher cụ thể có đứng trước matcher tổng quát không?
- Có pattern nào chồng lấp nhưng chưa có test phân biệt principal không?
- Mọi method nhạy cảm đã có rule riêng chưa?
- Fallback có phản ánh đúng chính sách cho endpoint mới chưa?
- Các `SecurityFilterChain` có thứ tự và phạm vi rõ ràng không?
- Test anonymous, user thường, admin và principal thiếu scope có kết quả đúng không?
- Có test cho path chưa tồn tại/chưa khai báo và xác minh đúng tầng tạo response không?
- CSRF/CORS có bị nhầm với authorization không?

## 13. Thực hành: đóng mặc định cho API mới

Một hệ thống nội bộ có các vùng:

| Path | Chính sách |
| --- | --- |
| `/public/status` | Công khai |
| `/api/admin/**` | `ROLE_ADMIN` |
| `/api/reports/**` | `SCOPE_reports.read` |
| `/api/profile/**` | Chỉ cần đăng nhập |
| `/api/**` còn lại với `GET` | `SCOPE_api.read` |
| Request còn lại | Từ chối |

Hãy thực hiện:

1. Viết matcher cụ thể trước matcher tổng quát và thêm `anyRequest().denyAll()`.
2. Tạo test cho một path chồng lấp, ví dụ `/api/admin/audit`, với hai principal: scope reader và admin không có scope đọc API.
3. Tạo test cho `/api/profile` để chứng minh rule `authenticated()` được áp dụng trước rule scope tổng quát.
4. Tạo test anonymous và authenticated cho `/new-feature` hoặc `/internal/feature` để chứng minh fallback.
5. Nếu có nhiều `SecurityFilterChain`, thêm test chứng minh request API vào API chain và request web vào web chain.
6. Lặp lại chính sách bằng `authorizeExchange`/`anyExchange` trong WebFlux và viết test `WebTestClient`.
7. Tạm đảo thứ tự hai matcher trong một nhánh thử nghiệm và xác nhận test hồi quy phát hiện lỗi.

**Tiêu chí hoàn thành:** mỗi request chồng lấp được xử lý bởi rule đúng; request không khớp không tự được cấp quyền; fallback được khai báo và kiểm thử; thứ tự filter chain không che chain chuyên biệt; các ca âm chứng minh được rằng người chỉ có quyền tổng quát không thể truy cập vùng cần quyền đặc biệt.
