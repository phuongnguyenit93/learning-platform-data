# Kiểm chứng 400, 401, 403 và header WWW-Authenticate

## 1. Vì sao phải kiểm tra cả status và WWW-Authenticate?

Một API Resource Server có thể trả về cùng một HTTP status trong nhiều tình huống, nhưng ý nghĩa của lỗi và cách client xử lý khác nhau. Ví dụ, `400 Bad Request` có thể xuất phát từ JSON không hợp lệ hoặc từ Bearer request sai cú pháp; `401 Unauthorized` có thể do thiếu token hoặc token không được xác minh; `403 Forbidden` có thể do thiếu OAuth scope hoặc do policy nghiệp vụ từ chối.

Với OAuth 2.0 Bearer Token, response còn có header `WWW-Authenticate` để mô tả authentication scheme và error challenge. Chỉ assert status code là chưa đủ để xác nhận Resource Server phản hồi đúng giao thức.

Một test tốt nên kiểm tra:

- Request thất bại ở tầng nào: request parsing, authentication hay authorization?
- Status code có đúng ngữ nghĩa không?
- Header `WWW-Authenticate` có scheme và error phù hợp không?
- Error description có tiết lộ token, claim nhạy cảm hoặc chi tiết nội bộ không?
- Request bị từ chối có tạo side effect hoặc trả dữ liệu không được phép không?

## 2. Phân biệt 400, 401 và 403

### 2.1. 400 Bad Request

`400` biểu thị server không thể hoặc không muốn xử lý request vì request có lỗi ở cú pháp hoặc cách biểu diễn. Trong API Resource Server, có hai nhóm cần phân biệt:

1. **Lỗi request/API thông thường:** JSON malformed, body không thỏa validation, parameter sai định dạng, thiếu field bắt buộc.
2. **OAuth Bearer invalid_request:** request mang thông tin token sai cách, ví dụ gửi token bằng nhiều phương thức cùng lúc hoặc cú pháp truyền token không hợp lệ theo Bearer protocol.

Không phải mọi lỗi 400 đều là lỗi OAuth. Một lỗi Bean Validation ở request body không tự động cần header Bearer challenge.

### 2.2. 401 Unauthorized

`401` có nghĩa request thiếu thông tin xác thực hợp lệ. Với Bearer Resource Server, các trường hợp thường gặp:

- Không gửi access token tới endpoint yêu cầu authentication.
- Token hết hạn.
- Chữ ký JWT sai hoặc không xác minh được.
- Issuer/audience không được chấp nhận.
- Token inactive hoặc invalid theo introspection.
- Token không đúng profile/algorithm được cấu hình.

Theo HTTP semantics, response 401 phải có ít nhất một challenge trong `WWW-Authenticate`. Với Resource Server dùng Bearer, challenge thường là `Bearer`.

Khi request không có credential, server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Khi token đã được gửi nhưng không hợp lệ, RFC 6750 định nghĩa error `invalid_token`:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Server có thể thêm `realm`, `error_description` hoặc `error_uri` theo policy.

### 2.3. 403 Forbidden

`403` có nghĩa server hiểu request và Authentication đã được xác lập, nhưng principal không có quyền thực hiện hành động.

Ví dụ:

- JWT hợp lệ nhưng thiếu `SCOPE_orders.read`.
- Principal không có role mà endpoint yêu cầu.
- User không có membership trong tenant đang truy cập.
- Resource thuộc owner/team khác.
- Policy nghiệp vụ từ chối thao tác.

Trong OAuth Bearer, trường hợp access token hợp lệ nhưng thiếu scope được RFC 6750 mô tả bằng `insufficient_scope` và status 403:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

Không phải mọi lỗi authorization đều là thiếu scope. Nếu user có scope API nhưng bị tenant/ownership policy từ chối, hãy dùng error contract phù hợp với ứng dụng; không gắn `insufficient_scope` nếu điều đó mô tả sai nguyên nhân.

## 3. Bảng quyết định theo RFC và API behavior

| Tình huống | Tầng thất bại | Status thường dùng | Bearer challenge |
|---|---|---:|---|
| JSON body malformed | Request parsing | 400 | Không cần Bearer error |
| Body thiếu field/validation fail | API validation | 400 | Không cần Bearer error |
| Bearer request có nhiều cách truyền token hoặc syntax sai | Token request parsing | 400 | `error="invalid_request"` |
| Không có token trên protected endpoint | Authentication | 401 | `Bearer`; thường không có error parameter |
| JWT signature/issuer/audience/expiry sai | Authentication | 401 | `error="invalid_token"` |
| Opaque token inactive | Authentication | 401 | `error="invalid_token"` |
| Token hợp lệ, thiếu scope cần thiết | Authorization | 403 | `error="insufficient_scope"`; scope có thể được nêu |
| Token hợp lệ nhưng tenant/owner policy deny | Authorization | 403 hoặc 404 theo contract | Không mặc định là insufficient_scope |
| Resource không tồn tại hoặc được che giấu | Resource lookup/policy | 404 | Thông thường không có Bearer error |

Các status trong bảng là cách dùng phổ biến và theo contract OAuth/HTTP tương ứng. API có thể có exception mapping riêng cho domain errors; điều quan trọng là không nhầm authentication failure với authorization failure.

### 3.1. Phân biệt invalid_request và invalid_token

Hai lỗi này dễ bị gộp nhầm:

- `invalid_request`: request đưa token tới server sai cách hoặc request Bearer không đúng cú pháp/format transport.
- `invalid_token`: token được nhận nhưng token không hợp lệ, hết hạn, bị thu hồi hoặc không được chấp nhận.

Ví dụ token JWT có ba segment nhưng chữ ký sai thường là `invalid_token`, không phải `invalid_request`. Ngược lại, request gửi token qua nhiều phương thức đồng thời là malformed token request.

### 3.2. Không trả 401 cho lỗi thiếu quyền

Nếu token đã xác thực và có Authentication, thiếu authority thường là 403. Trả 401 cho mọi lỗi khiến client nghĩ credential không hợp lệ và có thể refresh token vô ích.

Ngược lại, không trả 403 cho JWT có chữ ký sai. Chữ ký sai là authentication failure, nên phải được xử lý như 401.

## 4. Header WWW-Authenticate là gì?

`WWW-Authenticate` là response header dùng để gửi authentication challenge. Nó cho client biết server hỗ trợ scheme nào và, với OAuth Bearer, có thể cung cấp mã lỗi liên quan token.

Header này khác với request header `Authorization`:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

- `Authorization`: client gửi credential lên server.
- `WWW-Authenticate`: server thông báo challenge/error cho client.

Header challenge không phải access token, không phải response body và cũng không phải token endpoint error JSON.

### 4.1. Các tham số Bearer challenge

| Tham số | Ý nghĩa |
|---|---|
| `realm` | Không gian bảo vệ/resource area |
| `error` | Mã lỗi Bearer theo RFC 6750 |
| `error_description` | Mô tả ngắn cho client/developer |
| `error_uri` | URI tài liệu mô tả lỗi |
| `scope` | Scope cần thiết hoặc phạm vi liên quan tới lỗi |

Các mã lỗi Bearer quan trọng:

| Error code | Ý nghĩa | Status theo RFC 6750 |
|---|---|---:|
| `invalid_request` | Request token sai hoặc thiếu cấu trúc cần thiết | 400 |
| `invalid_token` | Token hết hạn, bị thu hồi, malformed hoặc invalid | 401 |
| `insufficient_scope` | Token không có quyền/scope cần thiết | 403 |

Không phải response nào cũng cần tất cả các tham số. Đặc biệt, khi client không gửi token, server thường chỉ gửi challenge scheme và không cần đưa `error="invalid_token"` vì không có token nào được trình bày để xác định là invalid.

### 4.2. Header có thể chứa nhiều challenge

Một server hỗ trợ nhiều authentication schemes có thể gửi nhiều challenge trong response. Client cần parse challenge theo HTTP authentication grammar, không giả định header chỉ có một scheme hoặc một chuỗi cố định.

Ví dụ minh họa:

~~~http
WWW-Authenticate: Bearer realm="api"
WWW-Authenticate: Basic realm="legacy"
~~~

Một số HTTP libraries gộp nhiều giá trị header khi đọc. Trong test, ưu tiên kiểm tra scheme/error cần thiết thay vì so sánh toàn bộ chuỗi nếu thứ tự hoặc format có thể thay đổi theo server/container.

## 5. Spring Security tạo 400/401/403 như thế nào?

### 5.1. Authentication failure và AuthenticationEntryPoint

Trong Servlet stack, Bearer token authentication được xử lý trong security filter chain. Khi request không có Authentication hợp lệ hoặc token bị từ chối, Spring Security gọi `AuthenticationEntryPoint` để bắt đầu authentication challenge.

Với OAuth 2.0 Resource Server, các handler thường dùng là:

- `BearerTokenAuthenticationEntryPoint`: tạo Bearer challenge cho authentication failure.
- `BearerTokenAccessDeniedHandler`: xử lý access denied trong Bearer Resource Server.

Khi cấu hình Resource Server theo mặc định:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Spring Security thiết lập các thành phần xử lý Bearer authentication phù hợp. Vì vậy, trước khi tự viết handler, hãy xác định default behavior của version đang dùng và test response thực tế.

### 5.2. BearerTokenAuthenticationEntryPoint

Entry point này chuyển OAuth authentication error thành status và challenge header. Các tình huống quan trọng:

- Không có token: 401 và Bearer challenge.
- Token invalid/expired: 401 với error `invalid_token`.
- Bearer request bị xác định là `invalid_request`: 400 với error tương ứng.

Ví dụ dùng trực tiếp trong cấu hình:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    entryPoint.setRealmName("orders");

    return http
        .exceptionHandling(errors -> errors
            .authenticationEntryPoint(entryPoint)
        )
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationEntryPoint(entryPoint)
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Trong ứng dụng, có thể để Resource Server dùng default entry point nếu không cần tùy biến realm/error policy. Nếu cấu hình global exception handling và Resource Server-specific entry point cùng tồn tại, xác định handler nào xử lý lỗi Bearer trong từng path.

### 5.3. BearerTokenAccessDeniedHandler

Khi Authentication đã được xác lập nhưng authorization từ chối, Spring Security gọi `AccessDeniedHandler`. Resource Server có handler dành cho Bearer token:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    BearerTokenAccessDeniedHandler deniedHandler =
        new BearerTokenAccessDeniedHandler();

    return http
        .exceptionHandling(errors -> errors
            .accessDeniedHandler(deniedHandler)
        )
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

Với token hợp lệ nhưng thiếu scope, response thường là 403 và Bearer challenge mô tả `insufficient_scope`. Có thể nêu scope cần thiết theo policy.

Đối với authorization failure không phải thiếu OAuth scope, chẳng hạn tenant membership hoặc resource ownership, hãy xem xét error contract riêng. Không biến mọi access denied thành thông báo “thiếu orders.read” nếu nguyên nhân thật là user không sở hữu resource.

### 5.4. Tùy biến error response body

`WWW-Authenticate` là protocol header; response body có thể là rỗng, Problem Detail hoặc error envelope theo API contract. Nếu muốn chuẩn hóa body:

- Giữ nguyên status code và challenge header.
- Không ghi đè hoặc xóa `WWW-Authenticate` khi tạo ProblemDetail.
- Không trả raw exception message, JWT, claims nhạy cảm hoặc introspection response.
- Dùng request ID để nối response với server logs.
- Không biến authentication failure thành HTTP 200 với error object.

Ví dụ một body API có thể dùng:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required",
  "requestId": "req-7f2c"
}
~~~

Đây là body minh họa, không phải body mặc định của Bearer entry point. Client nên dựa vào HTTP status và challenge header để xử lý OAuth authentication; body phục vụ API diagnostics theo contract.

## 6. Khi nào cần custom AuthenticationEntryPoint hoặc AccessDeniedHandler?

Chỉ tùy biến khi ứng dụng có yêu cầu cụ thể như chuẩn hóa Problem Detail, gắn correlation/request ID, dùng realm name riêng, localize message cho UI nhưng vẫn giữ challenge, phân loại domain authorization errors hoặc giữ tương thích API error schema cũ.

Một entry point tùy biến phải giữ semantics của 401 và `WWW-Authenticate`:

~~~java
@Component
public class ApiAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        delegate.commence(request, response, exception);

        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.getWriter().write("""
            {
              "type": "about:blank",
              "title": "Unauthorized",
              "status": 401,
              "detail": "Authentication is required"
            }
            """);
    }
}
~~~

Ví dụ tối giản minh họa delegate để giữ Bearer challenge. Trong production, body nên được serialize bằng ObjectMapper/ProblemDetail, đặt encoding và content length phù hợp, đồng thời tránh ghi đè header do delegate đã tạo. Nếu response đã committed, không ghi body lần nữa.

Một handler 403 tùy biến cần giữ challenge khi lỗi thực sự là `insufficient_scope`. Có thể delegate sang `BearerTokenAccessDeniedHandler` trước rồi bổ sung body an toàn. Với domain policy riêng, dùng error code/domain handler có ý nghĩa chính xác.

### 6.1. Cẩn thận với exception handling toàn cục

Nếu cấu hình:

~~~java
.exceptionHandling(errors -> errors
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customDeniedHandler)
)
~~~

hãy xác định thứ tự và phạm vi handler so với Resource Server configurer. Resource Server có thể có entry point riêng cho Bearer requests. Việc cài handler global không đảm bảo mọi authentication exception đi qua cùng một handler.

Hãy test qua filter chain thực tế, không chỉ gọi handler trực tiếp.

## 7. Không nhầm lỗi OAuth với lỗi API thông thường

Một endpoint có thể trả 400 mà không liên quan Bearer:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <VALID-TOKEN>
Content-Type: application/json

{"quantity": "not-a-number"}
~~~

Nếu token hợp lệ nhưng body sai kiểu dữ liệu, request đã qua authentication và bị từ chối ở tầng binding/validation. Response thường là 400 với API error body. Không cần Bearer challenge có error `invalid_token`.

Ngược lại:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <EXPIRED-TOKEN>
~~~

Request có thể parse đúng nhưng authentication thất bại, nên trả 401 và challenge `invalid_token`.

| Tầng | Ví dụ lỗi | Status | Header Bearer |
|---|---|---:|---|
| HTTP/request parsing | JSON malformed | 400 | Không cần |
| Bean Validation | Field không hợp lệ | 400 | Không cần |
| Bearer request parsing | Token transport sai | 400 | `invalid_request` |
| Authentication | Không có token | 401 | `Bearer` |
| Authentication | JWT invalid | 401 | `invalid_token` |
| Authorization | Thiếu scope | 403 | `insufficient_scope` |
| Domain authorization | Sai tenant/owner | 403/404 | Theo policy; không tự nhận insufficient_scope |


## 8. Kiểm thử bằng MockMvc trên Servlet stack

### 8.1. Đảm bảo MockMvc chạy qua Spring Security filter chain

Một integration test cơ bản:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BearerErrorResponseTests {

    @Autowired
    MockMvc mvc;
}
~~~

Nếu tự dựng MockMvc từ WebApplicationContext, áp dụng Spring Security:

~~~java
mvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Không dùng `@AutoConfigureMockMvc(addFilters = false)` khi mục tiêu là kiểm tra Bearer extraction, authentication entry point hoặc access denied handler. Khi filter bị tắt, status có thể đến từ controller và không chứng minh Resource Server behavior.

### 8.2. Không gửi token: 401 và Bearer challenge

~~~java
@Test
void missingTokenReturns401WithBearerChallenge() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            startsWith("Bearer")
        ));
}
~~~

Test này xác nhận endpoint protected yêu cầu authentication và server quảng bá Bearer scheme. Với request không có token, không nên bắt buộc header có `error="invalid_token"` vì client chưa gửi token nào để server kết luận token invalid.

### 8.3. Token invalid: 401 và invalid_token

Khi dùng decoder thật, hãy gửi compact JWT được ký sai hoặc có claim không hợp lệ qua Authorization header. Ví dụ kiểm tra signature/issuer/audience/expiry bằng test key sẽ xác nhận cả decoder lẫn filter chain.

Nếu muốn cô lập response mapping, có thể mock decoder trong test context:

~~~java
@MockitoBean
JwtDecoder jwtDecoder;

@Test
void invalidJwtReturns401WithInvalidTokenChallenge() throws Exception {
    when(jwtDecoder.decode("invalid-fixture"))
        .thenThrow(new JwtException("Invalid test token"));

    mvc.perform(get("/api/orders/42")
            .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer invalid-fixture"
            ))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.WWW_AUTHENTICATE,
            allOf(
                startsWith("Bearer"),
                containsString("error=\"invalid_token\"")
            )
        ));
}
~~~

`@MockitoBean` có trong Spring Framework 6.2+/Spring Boot 3.4+. Với version cũ, dự án có thể dùng `@MockBean`. Test này xác nhận error mapping qua filter chain nhưng mock decoder không kiểm tra chữ ký JWT. Để kiểm tra chữ ký, issuer và audience, dùng decoder thật cùng key fixture.

### 8.4. Token hợp lệ nhưng thiếu scope: 403

Dùng MockMvc JWT post-processor để tạo principal JWT đã authenticated với authority không đủ:

~~~java
@Test
void jwtWithoutReadScopeReturns403() throws Exception {
    mvc.perform(get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile.read")
            )))
        .andExpect(status().isForbidden());
}
~~~

Để kiểm tra Bearer challenge của access-denied handler, có thể assert scheme:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    startsWith("Bearer")
));
~~~

Nếu application dùng `BearerTokenAccessDeniedHandler` và policy thực sự là thiếu scope, có thể assert thêm:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    containsString("error=\"insufficient_scope\"")
));
~~~

Header cụ thể phụ thuộc handler và version/configuration. Nếu endpoint bị từ chối vì tenant/ownership policy, đừng assert `insufficient_scope` trừ khi application chủ ý biểu diễn policy đó bằng OAuth scope.

### 8.5. Request body invalid: 400 nhưng không phải Bearer error

Dùng một JWT principal đủ quyền để request đi tới controller, rồi gửi body sai validation:

~~~java
@Test
void invalidBodyReturns400WithoutInvalidTokenChallenge() throws Exception {
    mvc.perform(post("/api/orders")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")
            ))
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {"quantity": -1}
                """))
        .andExpect(status().isBadRequest())
        .andExpect(header().doesNotExist(
            HttpHeaders.WWW_AUTHENTICATE
        ));
}
~~~

Assertion về header phù hợp khi lỗi 400 được tạo bởi MVC validation/binding và không phải Bearer token parsing. Nếu application có policy luôn thêm challenge cho mọi response, điều chỉnh test theo contract đã công bố.

Trong ví dụ, DTO cần validation constraint như `@Min(1)` và controller cần `@Valid` để giá trị âm thực sự tạo 400. Nếu chain vẫn bật CSRF cho request POST, thêm `.with(csrf())` vào request test để cô lập lỗi body validation thay vì bị CSRF filter từ chối trước.

### 8.6. Kiểm tra invalid_request ở Bearer entry point

Có thể kiểm tra mapping của `invalid_request` bằng unit test entry point:

~~~java
@Test
void invalidBearerRequestMapsTo400Challenge() throws Exception {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpServletResponse response = new MockHttpServletResponse();

    OAuth2AuthenticationException exception =
        new OAuth2AuthenticationException(
            new OAuth2Error(OAuth2ErrorCodes.INVALID_REQUEST)
        );

    entryPoint.commence(request, response, exception);

    assertThat(response.getStatus()).isEqualTo(400);
    assertThat(response.getHeader(HttpHeaders.WWW_AUTHENTICATE))
        .contains("error=\"invalid_request\"");
}
~~~

Unit test này kiểm tra mapping từ OAuth error sang HTTP response. Để xác nhận request resolver thực sự phát ra `invalid_request`, cần một integration test dùng đúng BearerTokenResolver/transport configuration của ứng dụng. Không bật query/form token transport chỉ để làm test dễ hơn.

## 9. Kiểm thử bằng WebTestClient trên WebFlux

Reactive Resource Server có các handler tương ứng cho server web exchange:

- `BearerTokenServerAuthenticationEntryPoint`.
- `BearerTokenServerAccessDeniedHandler`.

Một test class có thể dùng:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveBearerErrorResponseTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

### 9.1. Không token: 401

~~~java
@Test
void missingTokenReturnsBearerChallenge() {
    webTestClient.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueMatches(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer.*"
        );
}
~~~

### 9.2. JWT thiếu authority: 403

~~~java
@Test
void jwtWithoutReadScopeIsForbidden() {
    webTestClient.get()
        .uri("/api/orders/42")
        .mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read")
        ))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

`mockJwt()` tạo Authentication giả lập để kiểm tra authorization. Nó không gọi `ReactiveJwtDecoder` và không kiểm tra signature. Nếu muốn kiểm tra decoder, gửi signed compact token bằng Bearer header và cấu hình decoder thật.

### 9.3. Kiểm tra challenge header

Nếu reactive Resource Server được cấu hình với Bearer server handlers, có thể kiểm tra header sau khi request bị từ chối:

~~~java
.expectHeader().valueMatches(
    HttpHeaders.WWW_AUTHENTICATE,
    "Bearer.*"
);
~~~

Đối với error parameter, kiểm tra chính xác policy và handler đang dùng. Không giả định mọi WebFlux 403 đều phải có `error="insufficient_scope"`.

## 10. Assert header bền vững

### 10.1. Kiểm tra scheme và error cần thiết

Một assertion thường ổn định hơn so sánh cả header:

~~~java
.andExpect(header().string(
    HttpHeaders.WWW_AUTHENTICATE,
    allOf(
        startsWith("Bearer"),
        containsString("error=\"invalid_token\"")
    )
));
~~~

Header có thể chứa thêm realm, scope hoặc error description. Thứ tự tham số và cách serialize có thể khác giữa version. Chỉ assert các phần thuộc contract cần thiết.

### 10.2. Không parse header bằng split đơn giản

Không nên:

~~~java
String[] parts = header.split(",");
~~~

Giá trị challenge có thể chứa quoted string, dấu phẩy hoặc nhiều challenge. Dùng HTTP client/parser hiểu authentication challenge grammar nếu cần xử lý tổng quát. Trong test, Hamcrest assertions trên các fragment cần thiết thường đủ.

### 10.3. Không yêu cầu error_description cố định

`error_description` là thông tin bổ sung cho developer/client. Nội dung có thể thay đổi theo version, locale hoặc cấu hình. Không gắn test vào raw exception message như “JWT expired at ...” hoặc chi tiết thư viện.

Nếu API công bố error code ổn định, assert code đó. Tránh trả hoặc assert nội dung chứa token, signature, issuer nội bộ, key ID nhạy cảm hay stack trace.

## 11. Kiểm tra status và challenge theo một bộ regression matrix

Một test suite nên có cả positive và negative cases:

| Case | Request | Status mong đợi | WWW-Authenticate |
|---|---|---:|---|
| Public endpoint | Không token | 2xx | Không cần |
| Protected endpoint, không token | Không Authorization | 401 | Bearer challenge |
| JWT hết hạn | Bearer token đã hết hạn | 401 | Bearer, `invalid_token` |
| JWT signature sai | Bearer token ký bằng key không tin | 401 | Bearer, `invalid_token` |
| Issuer/audience sai | Bearer JWT không đạt validator | 401 | Bearer, `invalid_token` |
| Opaque token inactive | Bearer token bị introspection từ chối | 401 | Bearer, `invalid_token` |
| Bearer request malformed | Token transport/syntax sai | 400 | Bearer, `invalid_request` nếu lỗi được map theo RFC 6750 |
| Token hợp lệ, thiếu scope | Authenticated, thiếu authority | 403 | Có thể có Bearer `insufficient_scope` |
| Token hợp lệ, tenant policy deny | Authenticated, sai tenant | 403/404 | Theo domain contract |
| JSON body invalid | Token hợp lệ, request body sai | 400 | Không cần Bearer error |

Với từng test, ngoài status và header, kiểm tra response body không chứa credential, stack trace hoặc dữ liệu resource bị từ chối.

## 12. Chẩn đoán khi status đúng nhưng header sai

### 12.1. 401 nhưng thiếu WWW-Authenticate

Kiểm tra:

- Endpoint có thật sự đi qua Resource Server filter chain không?
- Có custom `AuthenticationEntryPoint` ghi status rồi quên challenge header không?
- Exception có bị `@ControllerAdvice` bắt và đổi thành 401 không?
- Gateway có strip response header không?
- Một `SecurityFilterChain` khác có matcher/entry point khác không?

Một controller tự trả `ResponseEntity.status(401)` không tự tạo Bearer challenge. Nếu endpoint yêu cầu Bearer authentication, hãy để security layer xử lý authentication failure hoặc dùng handler có challenge phù hợp.

### 12.2. 401 có error sai

Nếu token đã được gửi nhưng invalid, challenge nên mô tả `invalid_token`. Nếu không có token, chỉ gửi Bearer challenge là phù hợp hơn.

Kiểm tra exception mapping và custom handler. Đừng gán `invalid_token` cho mọi 401 từ controller vì lỗi 401 có thể đến từ một authentication scheme khác.

### 12.3. 403 bị gắn insufficient_scope không chính xác

Một principal có thể bị deny bởi tenant membership, object ownership hoặc business policy dù đã có scope. Nếu challenge ghi `insufficient_scope`, client sẽ hiểu rằng cần xin thêm scope từ Authorization Server.

Chỉ trả error này khi scope thực sự là điều kiện bị thiếu. Domain authorization có thể dùng error body riêng và 403/404 theo API contract.

### 12.4. 400 bị gắn invalid_token

Nếu request body sai hoặc query parameter validation fail, đừng dùng Bearer `invalid_token`. Xác định lỗi xảy ra trước hay sau authentication. Một invalid JWT không phải malformed JSON; một malformed JSON không phải invalid access token.

### 12.5. Gateway thay đổi challenge header

Một số proxy/gateway có thể rewrite, normalize hoặc gộp response headers. So sánh response trực tiếp từ backend và response qua public route. Nếu chỉ public route sai, kiểm tra gateway response-header policies và CORS exposure.

Nếu browser JavaScript cần đọc header, CORS có thể cần expose `WWW-Authenticate`:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

Expose header chỉ cho phép browser JavaScript đọc header; nó không thay thế authentication challenge và không cấp quyền truy cập API.

## 13. Client nên xử lý challenge như thế nào?

Client không nên chỉ nhìn status rồi refresh token trong mọi trường hợp.

| Response | Hành động client thường phù hợp |
|---|---|
| 400 API validation | Sửa request/body/parameters |
| 400 `invalid_request` | Sửa cách gửi Bearer credential; không retry y nguyên |
| 401 không có token | Thực hiện authentication/token acquisition |
| 401 `invalid_token` | Có thể refresh/acquire token mới nếu flow hỗ trợ; tránh vòng lặp vô hạn |
| 403 `insufficient_scope` | Yêu cầu grant/scope phù hợp hoặc báo user thiếu quyền |
| 403 domain policy | Báo quyền truy cập bị từ chối; không refresh token vô ích |
| 404 resource hidden | Xử lý như resource không khả dụng theo contract |

Khi refresh token, client cần tránh nhiều request đồng thời cùng refresh một credential nếu provider có rotation. Sau khi nhận 401, không tự lặp request vô hạn với token cũ. Với 403, refresh token thường không giải quyết được thiếu role, tenant membership hoặc ownership.

## 14. Những lỗi thường gặp khi viết test

### Lỗi 1 — Chỉ assert status code

401 có thể thiếu challenge header; 403 có thể mang sai error code. Assert status cùng header quan trọng.

### Lỗi 2 — Mong 401 khi token hợp lệ nhưng thiếu scope

Đây là authorization failure, thường là 403. 401 dành cho authentication failure.

### Lỗi 3 — Gắn invalid_token cho request không có token

Không có credential thì server không thể kết luận token đã gửi là invalid. Bearer challenge có thể chỉ chứa scheme/realm.

### Lỗi 4 — Dùng jwt() để test chữ ký

MockMvc `jwt()` hoặc WebFlux `mockJwt()` tạo Authentication giả lập. Chúng không chạy decoder. Dùng signed JWT qua Bearer header và decoder thật để kiểm tra signature/issuer/audience.

### Lỗi 5 — Dùng @WithMockUser để kiểm tra WWW-Authenticate Bearer

`@WithMockUser` tạo một Authentication đã authenticated theo test context. Nó phù hợp cho authority-only tests, không tạo Bearer authentication failure. Dùng request không token hoặc token invalid qua filter chain để test entry point.

### Lỗi 6 — Dùng 403 cho mọi lỗi do token

JWT sai chữ ký, issuer hoặc expiry là 401. Principal đã xác thực nhưng thiếu quyền mới là 403.

### Lỗi 7 — Dùng 400 cho mọi JWT malformed

Token được truyền đúng Bearer transport nhưng JWT không parse/verify được thường là `invalid_token` và 401. `invalid_request` dành cho request/token transport sai theo Bearer protocol.

### Lỗi 8 — So sánh nguyên chuỗi WWW-Authenticate

Realm, scope và error description có thể thêm/bớt hoặc khác thứ tự. Assert scheme và error parameter cần thiết.

### Lỗi 9 — Ghi token hoặc exception detail vào error_description

Header là một phần response gửi cho client. Không đưa raw JWT, signature, internal hostname, key path, stack trace hoặc sensitive claim vào đó.

### Lỗi 10 — ControllerAdvice che mất security challenge

Một exception handler toàn cục có thể tạo body 401/403 mà không giữ header do security entry point/access-denied handler tạo. Test qua filter chain và kiểm tra cả status, header lẫn body.

## 15. Checklist trước khi phát hành API Resource Server

- [ ] Protected endpoint không có token trả 401.
- [ ] Response 401 có `WWW-Authenticate` Bearer challenge.
- [ ] Request không token không bị gắn `error="invalid_token"` một cách sai ngữ nghĩa.
- [ ] JWT invalid/expired/signature/issuer/audience sai trả 401 và `invalid_token`.
- [ ] Bearer request malformed được phân loại `invalid_request` và 400 khi áp dụng.
- [ ] Token hợp lệ nhưng thiếu scope trả 403.
- [ ] `insufficient_scope` chỉ dùng khi scope thật sự thiếu.
- [ ] Tenant/owner denial có error contract đúng domain.
- [ ] API validation 400 không bị biến thành Bearer invalid_token.
- [ ] Custom entry point giữ challenge header.
- [ ] Custom access-denied handler giữ semantics của scope denial.
- [ ] Gateway không xóa hoặc rewrite `WWW-Authenticate`.
- [ ] Browser client cần đọc header đã được CORS expose đúng nếu cần.
- [ ] Body/error_description không lộ token, claims nhạy cảm hoặc stack trace.
- [ ] MockMvc/WebTestClient test chạy qua filter chain.
- [ ] Có test signed token qua decoder thật cho authentication validation.
- [ ] Có test riêng cho authorization và request validation.
- [ ] Client không refresh token vô hạn khi nhận 401/403.

## 16. Kết luận

`400`, `401` và `403` mô tả các failure layer khác nhau. `400` thường là request không hợp lệ; với Bearer protocol, `invalid_request` cũng là 400. `401` là authentication failure như thiếu token hoặc `invalid_token` và phải có challenge `WWW-Authenticate`. `403` là authorization denial; nếu token hợp lệ nhưng thiếu scope, RFC 6750 định nghĩa `insufficient_scope`.

Khi kiểm thử Spring Security Resource Server, hãy đi qua filter chain thực tế, assert status và challenge header, đồng thời tách lỗi request validation khỏi lỗi Bearer authentication. Dùng `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` hoặc handler tương đương trên WebFlux để giữ protocol semantics khi tùy biến response. Kiểm tra cả response body, side effects và hành vi client để tránh biến lỗi xác thực thành vòng refresh hoặc retry vô hạn.

### Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics, 401/403 and WWW-Authenticate](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage, Section 3](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [Spring Security Reference — Testing MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security Reference — Testing Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)






