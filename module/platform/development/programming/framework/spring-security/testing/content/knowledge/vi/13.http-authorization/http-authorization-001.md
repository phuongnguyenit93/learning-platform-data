# Ma trận endpoint, HTTP method và danh tính

## 1. Từ quy tắc phân quyền đến hợp đồng kiểm thử

Trong ứng dụng Spring Security, câu hỏi "người dùng đã đăng nhập chưa?" mới chỉ là một phần của phân quyền HTTP. Cùng một URL có thể cho phép `GET` nhưng từ chối `DELETE`; cùng một phương thức có thể cho phép quản trị viên nhưng từ chối người dùng thông thường; cùng một người dùng có thể đọc tài nguyên của mình nhưng không được đọc tài nguyên của người khác.

**Ma trận phân quyền HTTP** biểu diễn các điều kiện đó dưới dạng những ca kiểm thử cụ thể:

> **HTTP method + đường dẫn + danh tính/quyền + điều kiện của request → kết quả mong đợi.**

Ở đây, "danh tính" bao gồm trạng thái ẩn danh hoặc đã xác thực, vai trò (`ROLE_USER`, `ROLE_ADMIN`), authority như `SCOPE_orders.read`, và khi cần, quan hệ giữa người dùng với tài nguyên. "Điều kiện của request" có thể gồm CSRF token, kiểu xác thực, dữ liệu đầu vào, hoặc trạng thái của tài nguyên.

Sau bài học, người học có thể:

- Chuyển chính sách `authorizeHttpRequests` (Servlet) hoặc `authorizeExchange` (Reactive) thành ma trận ca kiểm thử dương và âm.
- Kiểm chứng quyền truy cập bằng `MockMvc`, `spring-security-test`, `@WithMockUser` và `WebTestClient` mà không cần mở cổng HTTP thật.
- Phân biệt lỗi xác thực `401`, lỗi phân quyền `403`, redirect đến trang đăng nhập và lỗi định tuyến `404`/`405`.
- Kiểm thử request thay đổi trạng thái với CSRF và giả lập danh tính JWT/OAuth2/OIDC đúng theo kiểu bảo mật ứng dụng.
- Phát hiện các lỗ hổng thường bị bỏ qua: thiếu phương thức trong ma trận, kiểm tra nhầm role/authority, quyền sở hữu tài nguyên và thứ tự matcher.

## 2. Thiết kế một ma trận cho API đơn hàng

Giả sử API có chính sách:

1. `GET /public/health` công khai.
2. `GET /api/orders` và `GET /api/orders/{id}` dành cho `USER` hoặc `ADMIN`.
3. `POST /api/orders` dành cho `USER` hoặc `ADMIN`.
4. `DELETE /api/orders/{id}` và `GET /api/reports` chỉ dành cho `ADMIN`.
5. Các request khác bị từ chối theo chính sách bảo mật.

Để dự đoán mã HTTP nhất quán, ví dụ này sử dụng **HTTP Basic** cho API, bật **CSRF mặc định** và giả định controller thực sự tồn tại, trả về các mã thành công được ghi trong bảng. Nếu ứng dụng dùng form login, người dùng ẩn danh có thể nhận `302` chuyển hướng đến trang đăng nhập thay vì `401`. Nếu endpoint không có handler, kết quả từ tầng MVC/WebFlux cũng có thể là `404` hoặc `405` sau khi request vượt qua tầng bảo mật.

| HTTP method | Endpoint | Anonymous | `ROLE_USER` | `ROLE_ADMIN` | Điều kiện |
| --- | --- | ---: | ---: | ---: | --- |
| `GET` | `/public/health` | `200` | `200` | `200` | Công khai |
| `GET` | `/api/orders` | `401` | `200` | `200` | Không cần CSRF |
| `GET` | `/api/orders/42` | `401` | `200` | `200` | Chưa kiểm tra quyền sở hữu |
| `POST` | `/api/orders` | `401` | `201` | `201` | Gửi **CSRF token hợp lệ** |
| `DELETE` | `/api/orders/42` | `401` | `403` | `204` | Gửi **CSRF token hợp lệ** |
| `GET` | `/api/reports` | `401` | `403` | `200` | Chỉ quản trị viên |

Đọc một ô trong bảng thành câu kiểm thử: **"Khi `ROLE_USER` gọi `DELETE /api/orders/42` cùng CSRF hợp lệ, server phải trả `403`"**. Với endpoint nhạy cảm, nên kiểm tra ít nhất một người được phép, một người bị cấm và người chưa xác thực. Cần giữ các điều kiện khác như CSRF giống nhau khi so sánh danh tính.

Phạm vi ma trận này chỉ bao gồm **phân quyền ở lớp URL/method**. Nó chưa thể khẳng định người dùng sở hữu đơn hàng `42`. Quyền sở hữu cần thêm chính sách ở service hoặc truy vấn dữ liệu, được kiểm thử riêng ở mục 7.

## 3. Cấu hình Servlet tương ứng

Với ứng dụng Servlet dùng Spring MVC, chính sách có thể được triển khai bằng `SecurityFilterChain`:

```java
@Configuration
class HttpSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports").hasRole("ADMIN")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/{id}").hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAnyRole("USER", "ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/{id}")
                    .hasAnyRole("USER", "ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build(); // CSRF vẫn bật theo mặc định
    }
}
```

Các matcher được xét **theo thứ tự khai báo**, và quy tắc khớp đầu tiên quyết định quyền. Nếu khai báo một matcher quá rộng như `requestMatchers("/api/**").authenticated()` trước matcher dành riêng cho `ADMIN`, quy tắc phía sau có thể không được xét. Đưa matcher cụ thể lên trước, kết thúc bằng một quy tắc mặc định rõ ràng, rồi kiểm thử các URL dễ trùng nhau.

`hasRole("ADMIN")` kiểm tra authority thực tế **`ROLE_ADMIN`**; `hasAuthority("SCOPE_orders.read")` kiểm tra đúng chuỗi **`SCOPE_orders.read`**. Không thêm tiền tố `ROLE_` vào đối số của `hasRole`. Cấu hình và danh tính giả lập phải cùng mô hình quyền thì phép thử mới có ý nghĩa.

Để có controller trả về đúng các mã thành công của bảng, ví dụ tối giản sau không phụ thuộc cơ sở dữ liệu:

```java
@RestController
class DemoController {
    @GetMapping("/public/health")
    String health() { return "ok"; }

    @GetMapping("/api/orders")
    List<String> orders() { return List.of("order-42"); }

    @GetMapping("/api/orders/{id}")
    String order(@PathVariable String id) { return "order-" + id; }

    @PostMapping("/api/orders")
    ResponseEntity<Void> create() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    @DeleteMapping("/api/orders/{id}")
    ResponseEntity<Void> delete(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/reports")
    String report() { return "restricted-report"; }
}
```

Đây là ví dụ có chủ ý chỉ kiểm chứng cổng HTTP. Trong ứng dụng thật, controller, nghiệp vụ, cơ sở dữ liệu và quy tắc sở hữu phải được kiểm thử ở mức thích hợp.

## 4. Kiểm thử bảng quyền với MockMvc và `@WithMockUser`

Thêm dependency kiểm thử **`spring-security-test`** vào phạm vi test, cùng Spring Boot Test/JUnit Jupiter nếu dự án sử dụng Spring Boot. Với Maven có thể khai báo:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

`@WebMvcTest` tạo một lát cắt MVC; `@Import(HttpSecurityConfig.class)` đưa cấu hình bảo mật đang cần kiểm tra vào context. Khi dùng `@WebMvcTest`/`@AutoConfigureMockMvc` của Spring Boot với security được cấu hình, `MockMvc` được gắn filter chain. Nếu tự dựng `MockMvc` bằng `MockMvcBuilders`, cần tích hợp `springSecurity()` để các kiểm thử thực sự đi qua Spring Security.

```java
@WebMvcTest(DemoController.class)
@Import(HttpSecurityConfig.class)
class OrderAuthorizationMvcTest {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCanGetPublicHealth() throws Exception {
        mvc.perform(get("/public/health"))
           .andExpect(status().isOk());
    }

    @Test
    void anonymousCannotReadOrders() throws Exception {
        mvc.perform(get("/api/orders"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCanReadOrders() throws Exception {
        mvc.perform(get("/api/orders"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotReadAdminReport() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAdminReport() throws Exception {
        mvc.perform(get("/api/reports"))
           .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCanCreateWithCsrf() throws Exception {
        mvc.perform(post("/api/orders").with(csrf()))
           .andExpect(status().isCreated());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDeleteWithCsrf() throws Exception {
        mvc.perform(delete("/api/orders/42").with(csrf()))
           .andExpect(status().isNoContent());
    }
}
```

Các ví dụ Java lược bỏ phần `import` cho dễ đọc. Những import đáng chú ý là `org.springframework.security.test.context.support.WithMockUser`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf` và các phương thức tĩnh `get`, `post`, `delete`, `status` từ `MockMvcRequestBuilders`/`MockMvcResultMatchers`.

`@WithMockUser(roles = "USER")` đặt một `Authentication` giả lập có `ROLE_USER` vào `SecurityContext` của bài test. Nó phù hợp để kiểm chứng phân quyền nhưng **không chứng minh** rằng endpoint đăng nhập, mật khẩu, Basic header hay bộ xác minh JWT hoạt động. Nếu muốn kiểm tra đường đi xác thực HTTP Basic thực sự, tạo tài khoản test trong `UserDetailsService` và gửi `httpBasic("username", "password")`; khi đó cả bước xác thực cũng nằm trong phạm vi kiểm thử.

## 5. Biến ma trận thành parameterized test

Khi số endpoint tăng, mỗi ô bảng viết thành một phương thức test riêng sẽ khó duy trì. Có thể biểu diễn mỗi ca bằng dữ liệu và dùng `@ParameterizedTest`; như vậy bổ sung một role, HTTP method hoặc endpoint chỉ cần thêm một dòng.

```java
@ParameterizedTest(name = "{index}: {0}")
@MethodSource("authorizationCases")
void authorizationMatrix(
        String label, HttpMethod method, String path,
        String role, boolean includeCsrf, int expectedStatus) throws Exception {

    MockHttpServletRequestBuilder request;
    if (HttpMethod.GET.equals(method)) {
        request = get(path);
    } else if (HttpMethod.POST.equals(method)) {
        request = post(path);
    } else if (HttpMethod.DELETE.equals(method)) {
        request = delete(path);
    } else {
        throw new IllegalArgumentException("Unexpected method: " + method);
    }

    if (role == null) {
        request.with(anonymous());
    } else {
        request.with(user("tester").roles(role));
    }
    if (includeCsrf) request.with(csrf());

    mvc.perform(request).andExpect(status().is(expectedStatus));
}

static Stream<Arguments> authorizationCases() {
    return Stream.of(
        arguments("public / anonymous", GET, "/public/health", null, false, 200),
        arguments("orders / anonymous", GET, "/api/orders", null, false, 401),
        arguments("orders / user", GET, "/api/orders", "USER", false, 200),
        arguments("reports / user", GET, "/api/reports", "USER", false, 403),
        arguments("reports / admin", GET, "/api/reports", "ADMIN", false, 200),
        arguments("create / anonymous", POST, "/api/orders", null, true, 401),
        arguments("create / user", POST, "/api/orders", "USER", true, 201),
        arguments("delete / user", DELETE, "/api/orders/42", "USER", true, 403),
        arguments("delete / admin", DELETE, "/api/orders/42", "ADMIN", true, 204)
    );
}
```

Đặt đoạn này trong lớp test có `@Autowired MockMvc mvc` như mục 4 và dùng các static import tương ứng: `arguments`, `GET`, `POST`, `DELETE`, `user`, `anonymous`, `csrf`. Phần phân nhánh bằng `HttpMethod.GET.equals(method)` tương thích với các phiên bản Spring Framework mà `HttpMethod` là một class, không phải enum.

Một kiểm thử dữ liệu tốt nên ghi rõ **tên ca**, **danh tính**, **CSRF** và **mã kỳ vọng**. Khi thất bại, tên ca cho biết chính xác phần nào trong hợp đồng phân quyền bị phá vỡ.

## 6. Phân biệt lỗi xác thực, phân quyền và CSRF

Các mã thường gặp không thay thế cho nhau:

| Kết quả | Ý nghĩa cần kiểm tra | Ví dụ |
| --- | --- | --- |
| `200`/`201`/`204` | Request được chấp thuận và handler xử lý thành công | `ADMIN` xóa đơn hàng trả `204` |
| `401 Unauthorized` | Cần xác thực hoặc xác thực không hợp lệ; thường có challenge theo cơ chế được cấu hình | Anonymous gọi API bảo vệ bằng HTTP Basic |
| `403 Forbidden` | Danh tính đã có nhưng thiếu quyền; **hoặc** request không vượt qua một lớp bảo vệ khác như CSRF | `USER` gọi API chỉ dành cho `ADMIN` |
| `302 Found` | Chuyển hướng đến trang đăng nhập trong ứng dụng form login | Anonymous truy cập trang yêu cầu đăng nhập |
| `404 Not Found` | Không có handler/tài nguyên tương ứng (hoặc ứng dụng chủ động che giấu) | Gọi sai URL sau khi qua security |
| `405 Method Not Allowed` | Đường dẫn có handler nhưng không hỗ trợ HTTP method đó, nếu security cho request đi tiếp | Gọi `PATCH` đến controller chỉ khai báo `GET` |

**CSRF là nguồn gây nhầm lẫn rất thường gặp.** Với cấu hình Servlet ở trên, CSRF được bật mặc định; `POST`, `PUT`, `PATCH`, `DELETE` thường cần token hợp lệ. `CsrfFilter` có thể trả `403` **trước** khi kiểm tra quyền truy cập, làm một ca dự kiến `401` với anonymous cho request ghi dữ liệu thất bại vì sai nguyên nhân.

```java
@Test
@WithMockUser(roles = "ADMIN")
void csrfIsRequiredForDelete() throws Exception {
    mvc.perform(delete("/api/orders/42"))
       .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void invalidCsrfIsRejected() throws Exception {
    mvc.perform(delete("/api/orders/42").with(csrf().useInvalidToken()))
       .andExpect(status().isForbidden());
}

@Test
void anonymousWithValidCsrfStillNeedsAuthentication() throws Exception {
    mvc.perform(post("/api/orders").with(csrf()))
       .andExpect(status().isUnauthorized());
}
```

Nguyên tắc tách kiểm thử: khi kiểm tra **quyền**, cung cấp CSRF hợp lệ để kết quả phản ánh chính sách quyền; khi kiểm tra **CSRF**, giữ danh tính được phép và thay đổi riêng trạng thái token. Với API bearer token hoàn toàn stateless, nhóm dự án có thể chủ động vô hiệu hóa CSRF cho các endpoint phù hợp; nếu vậy, ma trận phải phản ánh cấu hình thực tế chứ không mặc định rằng mọi `POST` đều cần token.

## 7. Phân quyền theo tài nguyên: role chưa đủ

`GET /api/orders/42` cho phép `ROLE_USER` vượt qua lớp HTTP, nhưng chưa trả lời được câu hỏi người dùng có sở hữu đơn hàng `42` hay không. Nếu nghiệp vụ yêu cầu "chỉ chủ đơn hàng hoặc quản trị viên được đọc", cần kiểm tra thêm ở tầng dịch vụ, ví dụ:

```java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfig { }

@Service
class OrderService {
    @PreAuthorize("hasRole('ADMIN') or @orderPermission.isOwner(#id, authentication.name)")
    public OrderDto findById(long id) {
        return loadOrder(id);
    }
}
```

`orderPermission.isOwner` ở đây là một bean do ứng dụng cung cấp, kiểm tra chủ sở hữu **từ dữ liệu tin cậy trên server**. Không lấy `ownerId` do client tự khai trong request làm bằng chứng về quyền sở hữu.

Mở rộng bảng bằng hai danh tính cùng `ROLE_USER`:

| HTTP method và tài nguyên | `alice` sở hữu | `bob` không sở hữu | `ADMIN` |
| --- | ---: | ---: | ---: |
| `GET /api/orders/42` | `200` | `403` | `200` |

Các giá trị chỉ đúng khi `OrderService` thực sự được gọi qua proxy có method security và `orderPermission` trả về đúng theo fixture. Nếu dùng `@WebMvcTest` rồi mock toàn bộ `OrderService`, lời gọi `@PreAuthorize` ở service có thể không chạy: một test MVC xanh **không chứng minh** quyền sở hữu. Với luồng này, nên viết integration test có service thật hoặc kiểm thử method security riêng, đồng thời xác minh response/body và tác dụng phụ tương ứng.

## 8. Áp dụng cho ứng dụng Reactive với WebTestClient

Trong ứng dụng WebFlux, điểm chặn là `SecurityWebFilterChain` và DSL `authorizeExchange`. Dùng `WebTestClient` cùng hỗ trợ từ `spring-security-test` để kiểm tra cả ca được phép lẫn bị cấm.

```java
@Configuration
class ReactiveSecurityConfig {
    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports").hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAnyRole("USER", "ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/orders")
                    .hasAnyRole("USER", "ADMIN")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Giả sử có controller Reactive trả `Mono<String>` tại `/api/orders` và `/api/reports`, cùng endpoint `POST /api/orders` trả `201`:

```java
@WebFluxTest(ReactiveOrderController.class)
@Import(ReactiveSecurityConfig.class)
class ReactiveAuthorizationTest {
    @Autowired WebTestClient client;

    @Test
    void anonymousCannotReadOrders() {
        client.get().uri("/api/orders")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void userCanReadOrders() {
        client.mutateWith(mockUser("alice").roles("USER"))
              .get().uri("/api/orders")
              .exchange()
              .expectStatus().isOk();
    }

    @Test
    void userCannotReadAdminReport() {
        client.mutateWith(mockUser("alice").roles("USER"))
              .get().uri("/api/reports")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void userCanCreateWithCsrf() {
        client.mutateWith(mockUser("alice").roles("USER"))
              .mutateWith(csrf())
              .post().uri("/api/orders")
              .exchange()
              .expectStatus().isCreated();
    }
}
```

Ở ví dụ này, `mockUser` và `csrf` là các phương thức tĩnh của `SecurityMockServerConfigurers`. Trong các test độc lập, gọi `client.mutateWith(...)` để tạo client tương ứng với danh tính của ca; tránh gắn một người dùng chung rồi vô tình làm cho ca "anonymous" có xác thực. Nếu tự bind WebTestClient không qua ứng dụng test do Spring Boot cấu hình, cần dùng tích hợp `springSecurity()` của WebFlux để chuỗi security filter được thực thi.

**Servlet và Reactive có cùng ý tưởng ma trận, nhưng không dùng chung bộ giả lập request**: Servlet dùng các `SecurityMockMvcRequestPostProcessors` như `user()`, `jwt()` và `csrf()`; Reactive dùng `SecurityMockServerConfigurers` như `mockUser()`, `mockJwt()` và `csrf()`.

## 9. Ma trận khi dùng JWT, OAuth2 hoặc OIDC

Ở ứng dụng dùng OAuth2 Resource Server, quyền thường gắn với **scope** của access token. Chẳng hạn chính sách cho API đọc đơn hàng là:

```java
.requestMatchers(HttpMethod.GET, "/api/orders")
    .hasAuthority("SCOPE_orders.read")
```

Khi đó, bảng cần phân biệt token không có scope, token có scope và request không có token; kiểm tra mỗi trường hợp với cấu hình Resource Server thực tế:

| Danh tính/token | `GET /api/orders` | Ý nghĩa |
| --- | ---: | --- |
| Không có access token | `401` | Chưa xác thực |
| JWT hợp lệ nhưng thiếu `orders.read` | `403` | Đã xác thực, thiếu authority |
| JWT hợp lệ có `orders.read` | `200` | Được phép |
| JWT hết hạn hoặc chữ ký sai | `401` | Token không đạt kiểm tra xác thực thực |

Trong test **phân quyền** Servlet, `jwt()` giả lập `JwtAuthenticationToken`, không cần gửi JWT đã được ký:

```java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
   .andExpect(status().isOk());

mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile"))))
   .andExpect(status().isForbidden());
```

Trong WebFlux, dùng `mockJwt()` tương ứng:

```java
client.mutateWith(mockJwt().authorities(
          new SimpleGrantedAuthority("SCOPE_orders.read")))
      .get().uri("/api/orders")
      .exchange()
      .expectStatus().isOk();
```

`jwt()`/`mockJwt()` kiểm tra **quy tắc ủy quyền sau khi đã có danh tính**. Chúng không xác minh chữ ký, hạn sử dụng, issuer, audience hoặc hành vi thực của `JwtDecoder`/Reactive JWT decoder. Để kiểm tra token không hợp lệ hoặc thiếu bearer header, phải đi qua cơ chế Resource Server thật với decoder cấu hình phù hợp hoặc giả lập decoder theo đúng trường hợp; ở test slice cần bảo đảm bean decoder mà cấu hình yêu cầu có mặt.

Với **OAuth2 Login** hoặc **OpenID Connect login** (người dùng đăng nhập qua trình duyệt), Servlet có các processor `oauth2Login()` và `oidcLogin()`, còn WebFlux có `mockOAuth2Login()` và `mockOidcLogin()`. Chúng tạo principal đăng nhập cho test. Chúng không tương đương với access token bearer của Resource Server: lựa chọn bộ giả lập theo cơ chế ứng dụng đang sử dụng. Nếu endpoint xét claim, nhóm, tenant hoặc authority tùy biến, hãy đặt chúng rõ trong fixture và kiểm tra cả trường hợp thiếu claim/quyền.

## 10. Mở rộng ma trận để tìm lỗi phân quyền thật

Ma trận cơ bản là điểm bắt đầu. Trước khi coi một nhóm endpoint đã được bảo vệ, cần cân nhắc các chiều sau:

| Chiều cần phủ | Ca kiểm thử nên có | Lỗi dễ phát hiện |
| --- | --- | --- |
| **HTTP method** | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` tùy API | Cho phép đọc nhưng quên chặn xóa/sửa; cấu hình quá rộng |
| **Vai trò/authority** | Anonymous, USER, ADMIN, thiếu scope, sai scope | `hasRole`/`hasAuthority` không khớp; cấp quyền quá mức |
| **Đường dẫn** | Collection, từng ID, nested path, path lạ | Matcher bỏ sót, pattern quá rộng, thứ tự matcher sai |
| **Sở hữu và tenant** | Cùng tenant/khác tenant; của mình/của người khác | IDOR: lấy hoặc sửa tài nguyên không sở hữu |
| **Kiểu xác thực** | Basic, session, Bearer JWT hoặc OIDC theo ứng dụng | Lẫn lộn principal giả và xác thực thực |
| **CSRF** | Hợp lệ, thiếu, sai token với phương thức ghi | Hiểu nhầm `403` do CSRF thành kiểm tra role thành công |
| **Dữ liệu phản hồi** | Status và body; không lộ dữ liệu khi bị từ chối | Chỉ kiểm tra status mà bỏ qua rò rỉ thông tin |

Với CORS, `OPTIONS` preflight chứa `Origin` và `Access-Control-Request-Method` nên được kiểm thử theo cấu hình CORS thực tế; không đánh đồng nó với một request `OPTIONS` bất kỳ. Nếu có nhiều `SecurityFilterChain`/`SecurityWebFilterChain`, kiểm tra request chọn **đúng chain** trước khi đánh giá quyền; một matcher ở chain khác sẽ không bảo vệ request theo cách mong đợi.

Đối với endpoint có tác dụng phụ, khi kỳ vọng `401`/`403` nên kiểm tra thêm rằng nghiệp vụ **không thực thi**: không tạo đơn hàng, không xóa dữ liệu, không phát sự kiện. Với endpoint trả dữ liệu cá nhân, kiểm tra cả phạm vi dữ liệu trả về. Bảo mật đúng là **từ chối hành vi trái phép và ngăn tác dụng phụ**, không chỉ trả một status thuận mắt.

## 11. Chẩn đoán một ca kiểm thử thất bại

Khi một ô của ma trận không khớp kết quả, lần lượt xác định:

1. **Có đi qua security filter chain không?** Nếu dùng `MockMvcBuilders` hoặc bind WebTestClient thủ công, kiểm tra đã gắn Spring Security vào bộ kiểm thử.
2. **Request đã khớp matcher nào?** Đối chiếu HTTP method, pattern, thứ tự matcher và chain được chọn. Kiểm tra endpoint thực sự được controller ánh xạ.
3. **Principal đang có quyền gì?** `roles = "ADMIN"` sinh `ROLE_ADMIN`; JWT scope thường ánh xạ thành `SCOPE_...`; claim tùy biến chỉ thành quyền khi converter xử lý.
4. **Có bộ lọc nào từ chối trước khi đến authorization không?** Đặc biệt xem CSRF ở các phương thức ghi dữ liệu, hoặc redirect do form login.
5. **Quyền nằm ở tầng nào?** URL matcher không thay thế `@PreAuthorize`, quy tắc ownership, tenant hoặc kiểm tra ở database. Một service bị mock có thể làm mất phần bảo vệ cần chứng minh.
6. **Status có phản ánh đúng lỗi không?** `401` cần cơ chế entry point thích hợp; `403` có thể do thiếu quyền hoặc CSRF; `404`/`405` liên quan routing khi request đã qua bước bảo mật.

Không nên "sửa" một ca kiểm thử bằng cách đổi `403` thành `401` cho khớp hiện trạng ngay lập tức. Trước tiên xác định **vì sao** server trả mã đó, rồi quyết định có lỗi trong chính sách, fixture, cấu hình xác thực hay kỳ vọng của bài test.

## 12. Bài thực hành củng cố

Hãy bổ sung `PATCH /api/orders/{id}` với yêu cầu: chỉ chủ đơn hàng hoặc quản trị viên được sửa; request cần CSRF nếu ứng dụng dùng bảo vệ CSRF. Thực hiện theo thứ tự:

1. Viết bảng cho anonymous, chủ đơn hàng `alice`, người khác `bob`, `ADMIN` và hai trạng thái CSRF (hợp lệ/thiếu).
2. Viết cấu hình URL yêu cầu xác thực/role, sau đó thực thi kiểm tra ownership ở tầng nghiệp vụ có `@EnableMethodSecurity` hoặc cơ chế tương đương.
3. Thêm test `MockMvc` hoặc `WebTestClient` cho cả trường hợp được phép và từ chối; với trường hợp bị từ chối, xác minh dữ liệu đơn hàng không đổi.
4. Nếu chuyển sang Resource Server JWT, thay cột role bằng các tổ hợp scope/claim phù hợp và bổ sung test token thực sự bị từ chối khi không hợp lệ.

**Tiêu chí hoàn thành:** từng hàng của bảng có ca test chạy qua security thật ở cấp đang kiểm tra, phản hồi đúng kỳ vọng, các ca âm không gây tác dụng phụ, và các điều kiện như CSRF hay ownership được kiểm chứng riêng để xác định đúng nguyên nhân từ chối.
