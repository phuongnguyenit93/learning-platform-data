# Cùng đường dẫn nhưng khác HTTP method có thể có chính sách khác nhau

## 1. Một URL không đồng nghĩa với một quyền duy nhất

Trong API REST, cùng một tài nguyên có thể hỗ trợ nhiều hành động. Với đường dẫn `/api/orders/42`:

- `GET` đọc thông tin đơn hàng.
- `PATCH` thay đổi một phần thông tin đơn hàng.
- `DELETE` xóa hoặc hủy đơn hàng.

Ba request dùng cùng URL nhưng rủi ro và yêu cầu quyền khác nhau. Người dùng có quyền đọc chưa chắc được sửa; người được sửa chưa chắc được xóa. Nếu cấu hình Spring Security chỉ xét đường dẫn mà bỏ qua HTTP method, ứng dụng có thể vô tình cấp quyền rộng hơn chính sách nghiệp vụ.

Trong module **SPRING_SECURITY_TESTING**, chúng ta kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng **Servlet** và **Reactive**. Bài này tập trung vào việc kết hợp **HTTP method + path + danh tính/authority** để bảo vệ từng thao tác, rồi kiểm thử các trường hợp được phép và bị từ chối bằng `MockMvc` và `WebTestClient`.

Sau bài học, bạn có thể:

- Viết matcher phân quyền riêng cho `GET`, `POST`, `PATCH`, `PUT`, `DELETE` và các method cần thiết khác.
- Hiểu thứ tự matcher, rule mặc định và sự khác nhau giữa chọn `SecurityFilterChain` với chọn rule authorization bên trong chain.
- Kiểm thử cùng một path với nhiều method, gồm cả `HEAD`, `OPTIONS` và preflight CORS.
- Phân biệt lỗi do authentication, authorization, CSRF và routing.
- Dùng `@WithMockUser`, request postprocessor, `mockUser` và `mockJwt` để tạo danh tính đúng quyền cho từng ca.

## 2. Mô hình API và ma trận quyền theo method

Giả sử API quản lý đơn hàng có hợp đồng:

| HTTP method | Endpoint | Quyền cần có | Kết quả khi được phép |
| --- | --- | --- | --- |
| `GET` | `/api/orders` | `SCOPE_orders.read` | `200 OK` |
| `GET` | `/api/orders/{id}` | `SCOPE_orders.read` | `200 OK` |
| `HEAD` | `/api/orders` hoặc `/api/orders/{id}` | `SCOPE_orders.read` | `200 OK`, không có response body |
| `POST` | `/api/orders` | `SCOPE_orders.create` | `201 Created` |
| `PATCH` | `/api/orders/{id}` | `SCOPE_orders.write` | `204 No Content` |
| `DELETE` | `/api/orders/{id}` | `ROLE_ADMIN` | `204 No Content` |
| `PUT` | `/api/orders/{id}` | Không hỗ trợ trong API này | Bị từ chối theo rule mặc định |

Trong ví dụ, `ROLE_ADMIN` không tự động có các scope đọc, tạo hay sửa. Nếu admin cần thực hiện những hành động đó, hệ thống phải cấp thêm authority tương ứng hoặc định nghĩa chính sách kết hợp rõ ràng.

Các scope thường đến từ OAuth2 access token; với JWT Resource Server mặc định, scope `orders.read` có thể được ánh xạ thành authority `SCOPE_orders.read`. Đối với role, `hasRole("ADMIN")` kiểm tra `ROLE_ADMIN` theo tiền tố mặc định.

**Điều quan trọng:** quyền được gắn với từng cặp method/path. Không thể kết luận `GET` được phép thì `DELETE` cũng được phép chỉ vì URL giống nhau.

## 3. Spring Security chọn rule như thế nào?

Có hai bước cần phân biệt:

1. **Chọn filter chain:** `securityMatcher(...)` của từng `SecurityFilterChain` hoặc `SecurityWebFilterChain` xác định chain nào xử lý request.
2. **Chọn chính sách authorization:** bên trong chain, `requestMatchers(...)` hoặc `pathMatchers(...)` được xét theo thứ tự khai báo; matcher đầu tiên khớp sẽ quyết định rule.

Ví dụ sai:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/orders/**").authenticated()
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*").hasRole("ADMIN")
    .anyRequest().denyAll())
```

Rule tổng quát `/api/orders/**` đứng trước đã khớp mọi method ở đường dẫn đó. Request `DELETE /api/orders/42` của một người dùng bất kỳ đã đăng nhập có thể được chấp nhận trước khi rule admin phía sau được xét.

Hãy đặt các matcher cụ thể theo method/path trước:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/orders/*").hasRole("ADMIN")
    .requestMatchers(HttpMethod.PATCH, "/api/orders/*")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers(HttpMethod.POST, "/api/orders")
        .hasAuthority("SCOPE_orders.create")
    .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/*")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll())
```

Trong ví dụ hoàn chỉnh bên dưới, `HEAD` cũng được khai báo riêng. Rule `anyRequest().denyAll()` đóng các method/path chưa được đưa vào hợp đồng, ví dụ `PUT` hoặc một endpoint mới chưa được xem xét.

`securityMatcher` và `requestMatchers` không thay thế nhau. Nếu request không đi vào chain chứa các rule trên, việc sắp xếp matcher bên trong chain đó không có tác dụng. Với ứng dụng có nhiều chain (ví dụ web session và API bearer token), hãy kiểm tra chain được chọn trước khi điều tra quyền của endpoint.

## 4. Cấu hình Servlet: một path, nhiều chính sách

Ví dụ dùng Spring MVC và `SecurityFilterChain`:

```java
@Configuration
class OrderHttpSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/orders", "/api/orders/*")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.HEAD, "/api/orders", "/api/orders/*")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.PATCH, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/*")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Chỉ phù hợp với API Bearer token không dùng cookie để xác thực.
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Các matcher dùng method cụ thể và path cụ thể:

- Collection `/api/orders` cho `GET` và `POST`.
- Một order `/api/orders/*` cho `GET`, `HEAD`, `PATCH` và `DELETE`.
- `PUT` không có matcher riêng nên bị `denyAll`.

Đây là cấu hình cho API xác thực bằng Bearer token, không dùng cookie/session để xác thực request. Trong ứng dụng dùng cookie hoặc session, CSRF là một lớp bảo vệ quan trọng; không tắt CSRF chỉ vì endpoint có `POST`/`PATCH`/`DELETE`. Hãy giữ CSRF phù hợp và gửi token hợp lệ trong test kiểm tra authorization để không nhầm nguyên nhân `403`.

### Controller tương ứng

Controller mẫu giúp test đi qua cả filter chain lẫn MVC handler:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    @GetMapping
    List<String> list() {
        return List.of("order-42");
    }

    @GetMapping("/{id}")
    String get(@PathVariable String id) {
        return "order-" + id;
    }

    @PostMapping
    ResponseEntity<Void> create() {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }

    @PatchMapping("/{id}")
    ResponseEntity<Void> update(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(@PathVariable String id) {
        return ResponseEntity.noContent().build();
    }
}
```

Spring MVC có thể xử lý `HEAD` thông qua handler `GET` tương ứng và không gửi response body. Tuy nhiên, authorization matcher có method `GET` thường so khớp đúng method `GET`; nó không tự động biến matcher đó thành matcher `HEAD`. Nếu API cần hỗ trợ `HEAD`, hãy cho phép rõ ràng như cấu hình trên và kiểm thử riêng. Nếu không muốn hỗ trợ `HEAD`, hãy để request bị từ chối theo chính sách mặc định và ghi rõ trong hợp đồng API.

## 5. Đọc ma trận kết quả và phân biệt các nguyên nhân từ chối

Giả sử mọi request dưới đây đi vào API Bearer Resource Server, và mỗi principal có đúng tập authority được ghi:

| Danh tính | Authority |
| --- | --- |
| Reader | `SCOPE_orders.read` |
| Creator | `SCOPE_orders.create` |
| Writer | `SCOPE_orders.write` |
| Admin | `ROLE_ADMIN` |
| Manager | `SCOPE_orders.read`, `SCOPE_orders.write` |

Kết quả mong đợi:

| Request | Reader | Creator | Writer | Admin | Manager |
| --- | ---: | ---: | ---: | ---: | ---: |
| `GET /api/orders/42` | `200` | `403` | `403` | `403` | `200` |
| `HEAD /api/orders/42` | `200` | `403` | `403` | `403` | `200` |
| `POST /api/orders` | `403` | `201` | `403` | `403` | `403` |
| `PATCH /api/orders/42` | `403` | `403` | `204` | `403` | `204` |
| `DELETE /api/orders/42` | `403` | `403` | `403` | `204` | `403` |
| `PUT /api/orders/42` | `403` | `403` | `403` | `403` | `403` |

Anonymous thường nhận `401` với Bearer Resource Server khi truy cập endpoint được bảo vệ. Với form login, anonymous có thể nhận `302` chuyển đến trang đăng nhập. Một request đã xác thực nhưng thiếu authority nhận `403`. Với `PUT` trong ma trận, `403` là kết quả của `denyAll` khi principal đã xác thực; controller không cần có `@PutMapping` vì authorization có thể từ chối trước khi MVC xử lý.

Đừng gộp mọi `403` vào một loại lỗi. `CsrfFilter` có thể từ chối request ghi dữ liệu trước khi authorization chạy; CORS có thể từ chối preflight; rule method/path có thể từ chối do thiếu quyền; controller/service cũng có thể trả lỗi nghiệp vụ. Mỗi nhóm cần test riêng.

## 6. `HEAD`, `OPTIONS` và CORS preflight

Hai method thường bị bỏ quên khi tạo ma trận:

### `HEAD`

`HEAD` yêu cầu metadata/headers tương tự `GET` nhưng không cần response body. Spring MVC có thể phục vụ `HEAD` bằng mapping `GET`. Tuy nhiên, rule security có điều kiện `HttpMethod.GET` không nhất thiết khớp request `HEAD`. Vì vậy:

- Nếu hỗ trợ `HEAD`, khai báo matcher `HttpMethod.HEAD` với cùng mức quyền đọc phù hợp.
- Nếu không hỗ trợ, đừng vô tình cho phép chỉ vì matcher path tổng quát.
- Kiểm tra status, header cần thiết và response body rỗng.

### `OPTIONS` và CORS preflight

Browser có thể gửi CORS preflight:

```http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://frontend.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Đây là request hỏi server liệu origin, method và headers có được phép hay không. Nó không phải request `PATCH` thật. Khi bật CORS đúng cách, Spring Security cần xử lý CORS trước bước authorization để preflight hợp lệ được trả lời:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://frontend.example.test"));
    config.setAllowedMethods(
        List.of("GET", "HEAD", "POST", "PATCH", "DELETE"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Request-Id"));
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

Kết nối cấu hình CORS trong security chain:

```java
http.cors(Customizer.withDefaults());
```

Origin ở đây chỉ là ví dụ. Trong ứng dụng thật, chỉ khai báo origin tin cậy và method/header cần thiết. Nếu dùng cookie với `allowCredentials(true)`, không thể dùng wildcard origin `*` theo cách cho phép credentials; cần cấu hình origin cụ thể và bảo vệ CSRF tương ứng.

Không nên thêm `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` chỉ để browser preflight chạy qua. Rule đó mở mọi request OPTIONS ở tầng authorization và có thể che giấu cấu hình CORS sai. Hãy cấu hình CORS và kiểm thử preflight hợp lệ; một request OPTIONS không phải preflight vẫn cần chính sách rõ ràng.

## 7. Kiểm thử Servlet với MockMvc

Thêm dependency `spring-security-test` vào test scope. Với Spring Boot, có thể dùng `@WebMvcTest` để kiểm tra controller và security config:

```java
@WebMvcTest(OrderController.class)
@Import(OrderHttpSecurityConfig.class)
class OrderMethodAuthorizationTest {
    @Autowired MockMvc mvc;

    @Test
    void anonymousCannotReadOrder() throws Exception {
        mvc.perform(get("/api/orders/42"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.read")
    void readerCanGetOrder() throws Exception {
        mvc.perform(get("/api/orders/42"))
           .andExpect(status().isOk())
           .andExpect(content().string("order-42"));
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.read")
    void readerCanHeadOrder() throws Exception {
        mvc.perform(head("/api/orders/42"))
           .andExpect(status().isOk())
           .andExpect(content().string(""));
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.read")
    void readerCannotPatchOrder() throws Exception {
        mvc.perform(patch("/api/orders/42"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.create")
    void creatorCanPostOrder() throws Exception {
        mvc.perform(post("/api/orders"))
           .andExpect(status().isCreated());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.write")
    void writerCanPatchOrder() throws Exception {
        mvc.perform(patch("/api/orders/42"))
           .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.write")
    void writerCannotDeleteOrder() throws Exception {
        mvc.perform(delete("/api/orders/42"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanDeleteOrder() throws Exception {
        mvc.perform(delete("/api/orders/42"))
           .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCannotPostWithoutCreateScope() throws Exception {
        mvc.perform(post("/api/orders"))
           .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(authorities = "SCOPE_orders.write")
    void putIsDeniedBecauseItIsNotInThePolicy() throws Exception {
        mvc.perform(put("/api/orders/42"))
           .andExpect(status().isForbidden());
    }
}
```

Các ví dụ dùng `@WithMockUser` để dựng `Authentication` cho test. Dù security config ví dụ có Resource Server, `@WithMockUser` không xác minh JWT; test chỉ kiểm tra authorization sau khi principal đã có authority được chỉ định. Để context khởi động, test slice/full context vẫn cần các bean phụ thuộc mà cấu hình Resource Server yêu cầu, ví dụ `JwtDecoder`; có thể cung cấp decoder mock trong cấu hình test mà không nhầm nó với test chữ ký token thật.

Nếu test dùng `httpBasic` thay vì `@WithMockUser`, cần cấu hình `UserDetailsService`/authentication provider và gửi credentials để kiểm tra xác thực HTTP Basic. Không trộn hai mục tiêu thành một test rồi kết luận rằng cả đăng nhập lẫn phân quyền đều đã được xác minh.

### Khi ứng dụng dùng CSRF

Cấu hình ở mục 4 tắt CSRF vì chỉ dùng Bearer token và không dùng cookie. Nếu ứng dụng dùng session/cookie, giữ CSRF bật. Khi đó các test quyền cho `POST`, `PATCH` và `DELETE` cần gửi token hợp lệ:

```java
@Test
@WithMockUser(authorities = "SCOPE_orders.write")
void writerCanPatchWhenCsrfIsValid() throws Exception {
    mvc.perform(patch("/api/orders/42").with(csrf()))
       .andExpect(status().isNoContent());
}

@Test
@WithMockUser(roles = "ADMIN")
void adminStillNeedsCsrfWhenCsrfIsEnabled() throws Exception {
    mvc.perform(delete("/api/orders/42"))
       .andExpect(status().isForbidden());
}
```

Trong test thứ hai, `403` là do thiếu CSRF, không phải do thiếu role. Để chứng minh role admin có quyền xóa, gửi `.with(csrf())`; để chứng minh CSRF bắt buộc, giữ admin và thay đổi riêng token.

## 8. Dùng parameterized test để kiểm tra ma trận method

Khi endpoint tăng, có thể lưu các ca như dữ liệu. Ví dụ dưới đây minh họa cách tạo request từ method/path/authority; đặt trong lớp test có `MockMvc mvc`:

```java
static Stream<Arguments> methodCases() {
    return Stream.of(
        arguments("reader GET", GET, "/api/orders/42",
            "SCOPE_orders.read", 200),
        arguments("reader PATCH", PATCH, "/api/orders/42",
            "SCOPE_orders.read", 403),
        arguments("writer PATCH", PATCH, "/api/orders/42",
            "SCOPE_orders.write", 204),
        arguments("writer DELETE", DELETE, "/api/orders/42",
            "SCOPE_orders.write", 403),
        arguments("admin DELETE", DELETE, "/api/orders/42",
            "ROLE_ADMIN", 204),
        arguments("admin POST", POST, "/api/orders",
            "ROLE_ADMIN", 403)
    );
}

@ParameterizedTest(name = "{0}")
@MethodSource("methodCases")
void methodAndAuthorityMatrix(
        String label, HttpMethod method, String path,
        String authority, int expectedStatus) throws Exception {

    MockHttpServletRequestBuilder request;
    if (HttpMethod.GET.equals(method)) {
        request = get(path);
    } else if (HttpMethod.PATCH.equals(method)) {
        request = patch(path);
    } else if (HttpMethod.DELETE.equals(method)) {
        request = delete(path);
    } else if (HttpMethod.POST.equals(method)) {
        request = post(path);
    } else {
        throw new IllegalArgumentException("Unsupported method " + method);
    }

    mvc.perform(request.with(user("tester").authorities(
                new SimpleGrantedAuthority(authority))))
       .andExpect(status().is(expectedStatus));
}
```

Ví dụ dùng các static import `GET`, `PATCH`, `DELETE`, `POST` từ `MockMvcRequestBuilders`, `arguments` và JUnit Jupiter `@ParameterizedTest`/`@MethodSource`. Có thể bổ sung `HEAD` vào switch nếu cần kiểm tra HEAD. Nếu CSRF bật, hãy thêm token hợp lệ vào các request ghi dữ liệu trong ma trận authorization.

Parameterized test không nên làm mất thông tin khi thất bại. Tên ca cần thể hiện method và quyền, và mỗi hàng phải giữ điều kiện request giống nhau để nguyên nhân khác biệt chỉ nằm ở quyền hoặc HTTP method đang kiểm tra.

## 9. Reactive/WebFlux: khai báo method-specific pathMatchers

Trong ứng dụng WebFlux, dùng `SecurityWebFilterChain` và `authorizeExchange`:

```java
@Configuration
class ReactiveOrderSecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(
                    HttpMethod.GET, "/api/orders", "/api/orders/*")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(
                    HttpMethod.HEAD, "/api/orders", "/api/orders/*")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .pathMatchers(HttpMethod.PATCH, "/api/orders/*")
                    .hasAuthority("SCOPE_orders.write")
                .pathMatchers(HttpMethod.DELETE, "/api/orders/*")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
```

Như ví dụ Servlet, việc tắt CSRF chỉ phù hợp với API bearer token không dùng cookie. Nếu dùng session/cookie trong WebFlux, giữ CSRF và dùng tiện ích `csrf()` của Spring Security Test WebFlux cho các request thay đổi trạng thái.

Với `WebTestClient` đã được gắn vào ứng dụng Reactive, các ca có thể viết:

```java
@WebFluxTest(ReactiveOrderController.class)
@Import(ReactiveOrderSecurityConfig.class)
class ReactiveOrderMethodAuthorizationTest {
    @Autowired WebTestClient client;

    @Test
    void anonymousCannotReadOrder() {
        client.get().uri("/api/orders/42")
              .exchange()
              .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanGetOrder() {
        client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")))
              .get().uri("/api/orders/42")
              .exchange()
              .expectStatus().isOk();
    }

    @Test
    void readerCannotPatchOrder() {
        client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")))
              .patch().uri("/api/orders/42")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void writerCanPatchOrder() {
        client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write")))
              .patch().uri("/api/orders/42")
              .exchange()
              .expectStatus().isNoContent();
    }

    @Test
    void writerCannotDeleteOrder() {
        client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write")))
              .delete().uri("/api/orders/42")
              .exchange()
              .expectStatus().isForbidden();
    }

    @Test
    void adminCanDeleteOrder() {
        client.mutateWith(mockJwt().authorities(
                    new SimpleGrantedAuthority("ROLE_ADMIN")))
              .delete().uri("/api/orders/42")
              .exchange()
              .expectStatus().isNoContent();
    }
}
```

Ở Reactive, `mockJwt()` và `mockUser()` đến từ `SecurityMockServerConfigurers`; ở Servlet, `jwt()`/`user()` đến từ `SecurityMockMvcRequestPostProcessors`. Chúng là hai bộ API khác nhau. `mockJwt()` tạo principal giả để kiểm tra quyền; nó không kiểm tra chữ ký, issuer, audience hoặc thời hạn JWT thật.

Vì cấu hình Resource Server cần Reactive JWT decoder, test slice/full context cũng cần bean decoder phù hợp để khởi tạo context; có thể cung cấp decoder mock trong test khi chỉ kiểm tra authorization. Điều đó không thay thế integration test cho decoder thật.

Nếu tự dựng `WebTestClient`, hãy gắn client với ứng dụng và Spring Security filter chain theo cách phù hợp. Một test chỉ gọi handler trực tiếp mà không đi qua `SecurityWebFilterChain` không chứng minh rule method/path đang hoạt động.

## 10. CORS, method không hỗ trợ và method override

### CORS không phải authorization theo method

CORS quyết định browser có được phép thực hiện/chia sẻ request cross-origin theo origin, method và headers hay không. Nó không chứng minh người dùng có scope `orders.write` hoặc role admin. Một preflight `OPTIONS` thành công chỉ cho biết browser có thể gửi request dự kiến; request `PATCH` thực tế vẫn phải qua authentication và authorization.

Test CORS nên xác minh:

- Origin được phép nhận `Access-Control-Allow-Origin` phù hợp.
- `Access-Control-Allow-Methods` có method dự kiến, ví dụ `PATCH`.
- `Access-Control-Allow-Headers` cho phép headers cần thiết, ví dụ `Authorization` và `Content-Type`.
- Origin hoặc method không được phép không nhận phản hồi CORS chấp thuận.

Đừng dùng CORS như một lớp thay thế cho Spring Security. Client không phải browser có thể không thực thi chính sách CORS; server vẫn phải bảo vệ endpoint.

### Method không được hỗ trợ

Giả sử API không có `PUT`. Có hai câu hỏi riêng:

1. **Security có cho phép method này không?** Với `anyRequest().denyAll()`, request đã xác thực nhưng không có matcher sẽ bị chặn.
2. **MVC có handler cho method này không?** Nếu request vượt qua security mà không có mapping, MVC có thể trả `405 Method Not Allowed`.

Vì security có thể chặn trước routing, kết quả `403` không chứng minh controller có mapping PUT. Khi kiểm tra hợp đồng API, cần test cả status security dự kiến và hành vi routing trong một cấu hình test phù hợp.

### Method override

Một số ứng dụng/form có cơ chế chuyển một request POST thành method khác thông qua filter hoặc tham số như `_method`. Khi có cơ chế override, cần biết filter chuyển đổi chạy ở đâu so với Spring Security và matcher nhìn thấy method nào. Đừng giả định một header `X-HTTP-Method-Override` hoặc form parameter sẽ tự được Spring Security hỗ trợ. Nếu ứng dụng bật method override, viết test tích hợp cho chính filter đó và bảo đảm không thể dùng nó để né rule của `DELETE`/`PATCH`.

## 11. Các lỗi cấu hình và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| User có scope đọc gọi `DELETE` vẫn thành công | Rule path tổng quát đứng trước rule method-specific | Đưa matcher cụ thể lên trước, thêm test âm cho DELETE |
| `GET` được phép nhưng `HEAD` nhận `403` | Matcher `GET` không khớp `HEAD` | Khai báo `HttpMethod.HEAD` riêng hoặc chủ động từ chối HEAD |
| Browser preflight `OPTIONS` nhận `401/403` | CORS chưa được cấu hình hoặc không chạy trước authorization | Bật CORS integration, kiểm tra origin/method/headers |
| `OPTIONS` mọi path đều được phép | Rule permitAll rộng cho mọi OPTIONS | Chỉ xử lý preflight CORS hợp lệ, rà lại rule OPTIONS |
| POST/PATCH/DELETE luôn nhận `403` trong ứng dụng session | CSRF token thiếu/sai | Gửi CSRF hợp lệ khi test quyền, test CSRF riêng |
| Test trả `200` nhưng request thật bị từ chối | Test bỏ qua filter chain hoặc dùng principal giả khác thực tế | Kiểm tra MockMvc/WebTestClient integration và token decoder |
| Method lạ nhận `405` thay vì `403` | Request đã qua authorization nhưng không có handler | Xem matcher, chain và MVC mapping |
| Thêm matcher DELETE nhưng không có tác dụng | Request vào filter chain khác hoặc matcher rộng đã khớp trước | Kiểm tra `securityMatcher` và thứ tự authorization matcher |

### Quy trình điều tra một request

Khi `PATCH /api/orders/42` cho kết quả bất ngờ, hãy kiểm tra theo trình tự:

1. Request thực tế đến server có method nào? Có proxy, gateway hoặc method override biến đổi không?
2. `SecurityFilterChain` nào được chọn? Request có khớp `securityMatcher` của chain dự kiến?
3. Matcher method/path nào khớp đầu tiên? Có rule path tổng quát đứng trước không?
4. Principal có authority chính xác mà rule yêu cầu không? `ROLE_ADMIN` khác `SCOPE_orders.write`.
5. Request có bị CSRF hoặc CORS chặn trước authorization không?
6. Sau khi qua security, controller có handler cho method đó không? Service có thêm kiểm tra quyền đối tượng không?

Phân biệt rõ `401` (cần xác thực/xác thực thất bại), `403` (thiếu quyền hoặc bị một lớp bảo vệ từ chối), `405` (method không được handler hỗ trợ) và `302` (redirect đăng nhập trong một số cấu hình). Không đổi kỳ vọng test trước khi xác định đúng tầng tạo ra phản hồi.

## 12. Thực hành: bảo vệ cùng một tài nguyên theo hành động

Một API quản lý tài liệu hỗ trợ:

| Method | Endpoint | Chính sách |
| --- | --- | --- |
| `GET` | `/api/documents` và `/api/documents/{id}` | `SCOPE_documents.read` |
| `HEAD` | `/api/documents/{id}` | `SCOPE_documents.read` |
| `POST` | `/api/documents` | `SCOPE_documents.create` |
| `PUT` | `/api/documents/{id}` | `SCOPE_documents.write` |
| `PATCH` | `/api/documents/{id}` | `SCOPE_documents.write` |
| `DELETE` | `/api/documents/{id}` | `ROLE_ADMIN` |

Yêu cầu:

1. Viết `SecurityFilterChain` hoặc `SecurityWebFilterChain` dùng matcher kết hợp method và path, rule cụ thể trước, mặc định `denyAll`.
2. Tạo các persona reader, creator, writer, admin, manager có tập authority riêng; lập ma trận cho từng method.
3. Viết test anonymous và test cho từng persona bằng MockMvc hoặc WebTestClient; ít nhất một ca dương và một ca âm cho mỗi method.
4. Kiểm tra `HEAD` riêng, không mặc định rằng matcher GET bao phủ HEAD.
5. Nếu API được gọi từ browser, cấu hình CORS và test preflight `OPTIONS`; chứng minh request thật vẫn cần authority.
6. Nếu ứng dụng dùng cookie/session, bật CSRF và gửi token hợp lệ trong test authorization; viết test thiếu/sai token riêng.
7. Gửi `PUT` hoặc một method không được khai báo và xác minh chính sách từ chối như dự kiến.

**Tiêu chí hoàn thành:** cùng một path có kết quả khác nhau theo method đúng hợp đồng; không có matcher rộng cấp quyền ngoài ý muốn; test thực sự đi qua security filter chain; CORS/CSRF được tách khỏi authorization; mọi method không được hỗ trợ đều có kết quả được xác định rõ.
