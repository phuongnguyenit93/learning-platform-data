# Mô tả Bearer hoặc OAuth2 rồi kiểm chứng bằng cấu hình bảo mật thực

OpenAPI có thể mô tả cách client gửi access token, nhưng bản thân tài liệu không bảo vệ endpoint. Để API thực sự yêu cầu Bearer JWT hoặc OAuth2, ứng dụng phải có cấu hình Spring Security xác thực token và phân quyền cho từng request. Hai phần cần khớp nhau:

1. **Mô tả trong OpenAPI:** khai báo security scheme, scope và operation nào yêu cầu xác thực.
2. **Thực thi trong Spring Security:** kiểm tra token, xác minh chữ ký, issuer, expiry và quyết định request được phép truy cập hay không.

Với springdoc-openapi, có thể khai báo scheme bằng annotation hoặc cấu hình OpenAPI bean. Sau đó dùng integration test với MockMvc để kiểm tra document sinh ra và gọi endpoint với các trạng thái chưa xác thực, thiếu quyền và có quyền. Cách này giúp phát hiện tình huống Swagger UI hiển thị ổ khóa nhưng API vẫn public, hoặc API đã bảo vệ nhưng document không chỉ ra cách lấy token.

## 1. Phân biệt Bearer JWT và OAuth2

Hai thuật ngữ liên quan nhưng không cùng một lớp:

- **Bearer authentication** là cách client gửi credential trong HTTP header `Authorization: Bearer <token>`. Server chấp nhận token nếu token hợp lệ và request có đủ quyền.
- **JWT** là một định dạng token có cấu trúc, thường chứa claims như `iss`, `sub`, `aud`, `exp` và `scope`. JWT có thể được ký để resource server xác minh.
- **OAuth2** là framework ủy quyền quy định cách client nhận access token và cách scope biểu diễn quyền. Access token OAuth2 có thể là JWT hoặc token opaque.
- **Resource Server** là API nhận và xác minh access token. Nó không nhất thiết là nơi cấp token.

Nếu hệ thống chỉ cần mô tả header Bearer, dùng OpenAPI HTTP security scheme với `scheme: bearer`. Nếu cần mô tả luồng OAuth2 để developer lấy token, dùng OAuth2 security scheme với flow và scope tương ứng.

| Nhu cầu | Scheme OpenAPI thường dùng |
|---|---|
| Client nhận JWT từ một hệ thống khác rồi gửi Bearer token | HTTP Bearer |
| Swagger UI đăng nhập qua Identity Provider bằng Authorization Code + PKCE | OAuth2 Authorization Code |
| Service-to-service lấy token từ token endpoint | OAuth2 Client Credentials |
| API nhận token opaque và introspect qua Identity Provider | HTTP Bearer hoặc OAuth2 scheme tùy cách công bố contract |

Không khai báo `bearerFormat: JWT` chỉ vì header có chữ Bearer nếu token thực tế không phải JWT. `bearerFormat` chỉ là gợi ý cho người đọc/công cụ; nó không làm Spring Security xác minh chữ ký JWT.

## 2. Mô tả HTTP Bearer trong OpenAPI

Với API nhận JWT trong Authorization header, khai báo security scheme:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Access token dạng JWT trong Authorization header"
)
public class OpenApiBearerConfiguration {
}
~~~

Trong OpenAPI document, scheme tương ứng có dạng:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token dạng JWT trong Authorization header
security:
  - bearerAuth: []
~~~

`components.securitySchemes` chỉ định nghĩa cơ chế xác thực. Mảng `security` ở cấp root áp dụng requirement đó cho các operation trong document, trừ operation có security riêng ghi đè.

Nếu chỉ muốn bảo vệ một controller, có thể đặt `@SecurityRequirement(name = "bearerAuth")` ở cấp class hoặc operation thay vì áp dụng global. Cách này hữu ích khi một tài liệu chứa cả endpoint public và endpoint cần token.

### Đánh dấu operation public

Khi đã khai báo security requirement toàn cục, operation public cần ghi đè bằng security rỗng:

~~~java
@Operation(
    summary = "Kiểm tra trạng thái dịch vụ",
    security = {}
)
@GetMapping("/health")
public HealthResponse health() {
    return new HealthResponse("UP");
}
~~~

Trong OpenAPI, `security: []` ở cấp operation có nghĩa operation không yêu cầu security scheme toàn cục. Điều này chỉ mô tả contract; Spring Security vẫn phải cấu hình `/health` là public nếu đó là hành vi runtime mong muốn.

## 3. Khai báo OAuth2 Authorization Code + PKCE

Với developer đăng nhập qua Identity Provider ngay trong Swagger UI, Authorization Code flow kết hợp PKCE thường phù hợp cho public browser client. OpenAPI cần mô tả authorization endpoint, token endpoint và các scope mà API yêu cầu.

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = {
        @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders.read"}
        )
    }
)
@SecurityScheme(
    name = "ordersOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://id.example.com/oauth2/authorize",
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "orders.read",
                    description = "Đọc đơn hàng"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Tạo và cập nhật đơn hàng"
                )
            }
        )
    )
)
public class OpenApiOAuthConfiguration {
}
~~~

Document sinh ra sẽ mô tả OAuth2 flow và scope trong `components.securitySchemes.ordersOAuth.flows.authorizationCode`. Requirement ở root yêu cầu scope `orders.read`.

Để một operation cần scope khác, gắn requirement tại operation:

~~~java
@Operation(
    summary = "Tạo đơn hàng",
    security = {
        @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders.write"}
        )
    }
)
@PostMapping("/api/orders")
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Scope trong OpenAPI mô tả quyền client cần có. Nó không tự tạo scope trong Identity Provider và cũng không tự cấu hình Spring Security. Scope phải tồn tại trong hệ thống cấp token và được resource server ánh xạ sang authority mà ứng dụng kiểm tra.

## 4. Cấu hình Spring Security thực thi Bearer JWT

Với Spring Boot 3 và Spring Security 6, có thể cấu hình ứng dụng như một OAuth2 Resource Server. Ví dụ sau yêu cầu JWT có scope tương ứng khi gọi API:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/acme
~~~

`issuer-uri` cho phép Spring Security khám phá metadata của issuer và khóa công khai dùng để xác minh JWT. Môi trường production cần dùng HTTPS và issuer đúng với token do Identity Provider phát hành.

Cấu hình filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/v3/api-docs",
                    "/v3/api-docs/**",
                    "/v3/api-docs.yaml",
                    "/swagger-ui/**",
                    "/swagger-ui.html"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Trong ví dụ, tài liệu OpenAPI và Swagger UI public để developer đọc contract; business endpoint yêu cầu token. Nếu tài liệu nội bộ, thay `permitAll()` bằng policy authentication/authorization của tổ chức và viết test cho policy đó.

Việc tắt CSRF chỉ phù hợp với API stateless xác thực bằng Bearer token trong header và không dùng cookie/session để xác thực request. Nếu ứng dụng dùng session cookie, form login hoặc browser gửi credential tự động, không sao chép cấu hình `csrf.disable()` một cách máy móc; cần thiết kế CSRF protection phù hợp.

`SessionCreationPolicy.STATELESS` yêu cầu Spring Security không tạo session để lưu trạng thái xác thực. Token được gửi lại trong từng request.

### Spring Security ánh xạ scope thành authority

Với JWT có claim `scope` hoặc `scp`, Spring Security Resource Server mặc định thường chuyển scope thành authority có tiền tố `SCOPE_`. Ví dụ:

~~~json
{
  "iss": "https://id.example.com/realms/acme",
  "sub": "user-42",
  "scope": "orders.read orders.write",
  "exp": 1900000000
}
~~~

Các authority tương ứng:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Vì vậy, `hasAuthority("SCOPE_orders.read")` kiểm tra scope `orders.read`. Nếu Identity Provider dùng custom claim hoặc format khác, cần cấu hình `JwtAuthenticationConverter`/`JwtGrantedAuthoritiesConverter` để ánh xạ đúng; không giả định mọi token đều dùng cùng tên claim.

## 5. Spring Security không cấp access token

Khi cấu hình:

~~~java
.oauth2ResourceServer(resourceServer -> resourceServer
    .jwt(Customizer.withDefaults())
)
~~~

ứng dụng đang xác minh access token được gửi đến. Nó không trở thành OAuth2 Authorization Server và không tự tạo endpoint `/oauth2/authorize` hay `/oauth2/token`.

Các endpoint authorization/token trong `@SecurityScheme` phải trỏ tới Identity Provider hoặc Authorization Server thực tế. Không điền URL của API Resource Server vào các trường này nếu API không cung cấp chức năng cấp token.

Với OAuth2 Authorization Code + PKCE, Swagger UI chuyển người dùng đến Identity Provider, nhận authorization code, đổi code lấy access token rồi gửi Bearer token đến API. Identity Provider phải đăng ký redirect URI chính xác của Swagger UI, ví dụ URL public của trang `oauth2-redirect.html`. Domain, scheme HTTPS và context path phải khớp cấu hình ở cả hai phía.

Không đặt client secret trong JavaScript hoặc cấu hình Swagger UI chạy trên browser. Browser client nên dùng PKCE và client registration phù hợp với public client.

## 6. Cấu hình Swagger UI để đăng nhập OAuth2

Nếu dùng Authorization Code flow, Swagger UI cần biết client ID và bật PKCE:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: swagger-ui-public-client
      use-pkce-with-authorization-code-grant: true
~~~

Tên property và khả năng hỗ trợ có thể khác giữa các dòng springdoc/Swagger UI. Đối chiếu configuration properties của đúng phiên bản đang dùng và xác minh URL redirect public trong cấu hình Identity Provider.

Sau khi mở Swagger UI:

1. Chọn **Authorize**.
2. Chọn security scheme OAuth2.
3. Chọn scope cần cấp, ví dụ `orders.read`.
4. Hoàn tất đăng nhập tại Identity Provider.
5. Swagger UI nhận access token và gửi request với `Authorization: Bearer ...`.

Với HTTP Bearer scheme, người dùng thường dán access token trực tiếp vào hộp Authorize. Swagger UI tự thêm tiền tố Bearer theo scheme HTTP bearer; không dán thêm `Bearer ` nếu giao diện đã yêu cầu token thuần.

Không bật lưu credential trong browser dùng chung hoặc máy công cộng. Cũng không dùng Swagger UI làm nơi quản lý token production; giao diện này chủ yếu phục vụ khám phá và thử API trong môi trường developer.

## 7. Gắn security requirement cho controller và operation

Nếu không muốn áp dụng security toàn cục, có thể khai báo scheme ở cấu hình và gắn requirement tại controller:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
public class OrderController {
    // Các operation trong controller yêu cầu Bearer token.
}
~~~

Một operation cần scope cụ thể có thể dùng:

~~~java
@Operation(
    summary = "Đọc đơn hàng",
    security = {
        @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders.read"}
        )
    }
)
~~~

Không khai báo một security requirement chỉ vì endpoint có header bất kỳ. Scheme và requirement phải phản ánh cơ chế runtime thực tế: HTTP bearer, OAuth2, API key hay một cơ chế khác.

Nếu dùng global security nhưng có endpoint public, dùng `@Operation(security = {})` cho operation đó và cấu hình Spring Security `permitAll()` tương ứng. Hai phía phải thống nhất.

## 8. Kiểm tra cấu hình bảo mật thật bằng MockMvc

Có thể dùng `spring-boot-starter-test` cùng `spring-security-test`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Test cần xác minh ba tình huống cơ bản:

| Request | Kết quả mong đợi |
|---|---|
| Không có token | `401 Unauthorized` |
| Token hợp lệ nhưng thiếu authority/scope | `403 Forbidden` |
| Token hợp lệ và có authority/scope cần thiết | `200 OK` hoặc status thành công theo endpoint |

Ví dụ dùng MockMvc và JWT test post-processor:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedTokenWithoutReadScopeIsForbidden() throws Exception {
        mockMvc.perform(
                get("/api/orders")
                    .with(jwt().authorities(() -> "SCOPE_profile.read"))
            )
            .andExpect(status().isForbidden());
    }

    @Test
    void tokenWithReadScopeCanReadOrders() throws Exception {
        mockMvc.perform(
                get("/api/orders")
                    .accept(MediaType.APPLICATION_JSON)
                    .with(jwt().authorities(() -> "SCOPE_orders.read"))
            )
            .andExpect(status().isOk());
    }
}
~~~

`jwt()` tạo một JwtAuthenticationToken giả cho test authorization. Nó giúp kiểm tra rule phân quyền và mapping authority mà không cần gọi Identity Provider. Tuy nhiên, nó **bỏ qua bước xác minh chữ ký, issuer, expiry và giải mã token thật**. Không dùng riêng test này để kết luận JWT decoder hoạt động đúng.

### Kiểm tra token thật

Để xác minh JWT decoder, cần một integration test dùng JWT được ký bởi test key/JWKS hoặc Identity Provider dành riêng cho test. Gửi token qua HTTP header:

~~~http
Authorization: Bearer eyJ...test-token
~~~

Kiểm tra:

- Token có chữ ký hợp lệ được chấp nhận.
- Token sai chữ ký hoặc không tìm được key bị từ chối.
- Token hết hạn bị từ chối.
- Claim `iss` không đúng issuer bị từ chối.
- Token thiếu scope nhận `403` ở endpoint yêu cầu scope.

Nếu chỉ mock `JwtDecoder`, test có thể xác minh luồng filter xử lý token hợp lệ/không hợp lệ theo decoder result, nhưng không kiểm chứng thuật toán chữ ký và JWKS thực tế. Nên có ít nhất một test với key pair/JWKS kiểm soát được trong test environment.

## 9. Kiểm tra security scheme trong OpenAPI document

Test runtime không xác nhận springdoc đã mô tả security đúng. Hãy kiểm tra `/v3/api-docs`:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;

@Test
void openApiDocumentDeclaresBearerScheme() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.securitySchemes.bearerAuth.type"
        ).value("http"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.bearerAuth.scheme"
        ).value("bearer"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.bearerAuth.bearerFormat"
        ).value("JWT"))
        .andExpect(jsonPath("$.security[0].bearerAuth").exists());
}
~~~

Nếu document dùng OAuth2, kiểm tra flow và scope:

~~~java
@Test
void openApiDocumentDeclaresOAuth2AuthorizationCodeFlow() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.securitySchemes.ordersOAuth.type"
        ).value("oauth2"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.ordersOAuth.flows.authorizationCode.authorizationUrl"
        ).value("https://id.example.com/oauth2/authorize"))
        .andExpect(jsonPath(
            "$.components.securitySchemes.ordersOAuth.flows.authorizationCode.scopes.orders.read"
        ).exists());
}
~~~

Nếu security requirement được khai báo ở cấp operation thay vì root, JSONPath cần kiểm tra `paths` của operation cụ thể. Nếu một endpoint public, kiểm tra operation đó không kế thừa requirement toàn cục.

## 10. Kiểm tra endpoint tài liệu khi có Spring Security

Trong ví dụ ở trên, `/v3/api-docs/**` và Swagger UI được cho phép truy cập công khai. Test nên khóa chính sách đó:

~~~java
@Test
void publicOpenApiDocumentCanBeReadWithoutToken() throws Exception {
    mockMvc.perform(get("/v3/api-docs")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaType.APPLICATION_JSON
        ));
}
~~~

Nếu tài liệu chỉ dành cho developer đã đăng nhập, hãy kiểm tra cả request anonymous bị từ chối và request có role phù hợp được chấp nhận. Đừng tắt toàn bộ filter chain bằng `addFilters = false` trong test security; làm vậy sẽ bỏ qua chính cấu hình cần kiểm chứng.

Các URL cần xem xét theo cấu hình thực tế gồm:

- `/v3/api-docs` và `/v3/api-docs/**` cho document mặc định/group.
- `/v3/api-docs.yaml` nếu công bố YAML; thêm path này vào security matcher nếu tài liệu được phép public.
- `/v3/api-docs/swagger-config` cho cấu hình Swagger UI.
- `/swagger-ui.html` và `/swagger-ui/**` cho trang và tài nguyên UI.
- OAuth2 redirect endpoint mà Swagger UI sử dụng.

Nếu đổi `springdoc.api-docs.path` hoặc `springdoc.swagger-ui.path`, cập nhật matcher và test theo URL mới. Không mở toàn bộ `/v3/**` nếu chỉ cần cho phép endpoint tài liệu.

## 11. Phân biệt 401 và 403

Hai status này thể hiện hai lỗi khác nhau:

- `401 Unauthorized`: request chưa được xác thực thành công, ví dụ không có token, token sai chữ ký hoặc token hết hạn.
- `403 Forbidden`: request đã được xác thực nhưng principal không có quyền cần thiết, ví dụ thiếu scope `orders.read`.

Với OAuth2 Resource Server, response 401 thường đi kèm `WWW-Authenticate: Bearer`. Không nên trả 200 với body lỗi cho trường hợp thiếu token nếu API muốn tuân thủ HTTP semantics và contract đã công bố.

Nếu API dùng custom `AuthenticationEntryPoint` hoặc `AccessDeniedHandler`, response body có thể được chuẩn hóa theo Problem Details. Khi đó OpenAPI phải mô tả đúng status, media type và schema lỗi; test cần kiểm tra cả ba.

## 12. CORS khi Swagger UI gọi API khác origin

Swagger UI có thể chạy ở domain tài liệu còn API chạy ở domain khác. Browser khi đó áp dụng CORS cho request Try it out. Bearer token thường khiến browser gửi preflight vì header `Authorization` không phải simple header.

Ví dụ cấu hình CORS cho Spring MVC:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(
            List.of("https://docs.example.com")
        );
        configuration.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
        );
        configuration.setAllowedHeaders(
            List.of("Authorization", "Content-Type", "Accept")
        );
        configuration.setExposedHeaders(List.of("Location"));

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }
}
~~~

Bật CORS trong filter chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Chỉ cho phép origin cần thiết. Nếu dùng cookie/session và `allowCredentials`, không kết hợp credentialed requests với wildcard origin. CORS chỉ là chính sách browser; nó không thay thế xác thực hoặc phân quyền ở server.

Nếu Swagger UI và API cùng origin, CORS có thể không cần thiết. Nếu CORS bị cấu hình sai, request có thể bị browser chặn trước khi response của API đến được JavaScript, dù gọi endpoint bằng curl vẫn thành công.

## 13. Ma trận kiểm chứng giữa tài liệu và cấu hình runtime

Sau khi cấu hình, so sánh các lớp:

| Hành vi | OpenAPI document | Spring Security runtime | Test cần có |
|---|---|---|---|
| API dùng Bearer JWT | `type: http`, `scheme: bearer` | `oauth2ResourceServer().jwt()` | Scheme có trong `/v3/api-docs`, token hợp lệ được nhận |
| API dùng OAuth2 scope | OAuth2 flow và scopes | Authority `SCOPE_...` | Có scope nhận 200; thiếu scope nhận 403 |
| Request không có token | Operation có security requirement | Request bị từ chối | 401 |
| Token sai/hết hạn | Security scheme vẫn được mô tả | Decoder từ chối token | 401 với token thật |
| Endpoint public | Operation `security: []` hoặc không có requirement tương ứng | `permitAll()` | Anonymous nhận status thành công |
| Tài liệu public | Không nhất thiết có security requirement | `/v3/api-docs/**` và UI `permitAll()` | Anonymous đọc được document |
| Tài liệu nội bộ | Có thể mô tả access policy trong tài liệu triển khai | Endpoint docs cần role phù hợp | Anonymous bị từ chối, role hợp lệ được phép |

Một bài kiểm tra hoàn chỉnh nên có ít nhất một test document, một test authorization theo authority, và một test xác minh token thật trong môi trường tích hợp.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Swagger UI hiện ổ khóa nhưng endpoint vẫn public | Chỉ khai báo `@SecurityScheme`/`@SecurityRequirement`, chưa cấu hình Spring Security | Thêm Resource Server/filter chain và kiểm tra request anonymous |
| API trả 401 nhưng Swagger UI không gửi token | Scheme chưa được gắn vào operation hoặc chưa bấm Authorize | Kiểm tra `security` trong document và cấu hình Authorize |
| Token hợp lệ vẫn nhận 401 | Issuer/JWKS sai, token hết hạn, chữ ký hoặc audience validation không khớp | Kiểm tra claim, issuer, JWK và decoder |
| Token nhận 403 | Đã xác thực nhưng thiếu authority/scope | Kiểm tra claim `scope`/`scp` và converter |
| Scope trong OpenAPI không có tác dụng runtime | Scope chỉ là metadata document | Ánh xạ scope thành authority và dùng `hasAuthority` |
| OAuth2 login quay về trang lỗi | Redirect URI chưa đăng ký hoặc không khớp public URL | Đồng bộ redirect URL, HTTPS, context path và IdP client registration |
| Swagger UI không lấy được token | Authorization URL/token URL sai hoặc CORS/PKCE chưa đúng | Kiểm tra IdP metadata, PKCE, redirect và browser console |
| `@WithMockUser` test pass nhưng JWT thật lỗi | Mock user bỏ qua JWT decoder | Thêm integration test với JWT/JWKS thật |
| `/v3/api-docs` trả 401 | Security matcher chưa cho phép endpoint tài liệu | Cập nhật matcher hoặc cấp quyền docs phù hợp |
| Swagger UI tải được nhưng Try it out lỗi CORS | API server chưa cho phép origin docs và header Authorization | Cấu hình CORS cho API endpoint |
| Endpoint public bị hiện ổ khóa | Global security áp dụng cho mọi operation | Đánh dấu `@Operation(security = {})` và cấu hình `permitAll()` |
| Dùng `csrf.disable()` làm hở ứng dụng session | Sao chép cấu hình stateless sang ứng dụng cookie/session | Chỉ tắt CSRF khi API thực sự stateless và dùng Bearer token |
| Client secret xuất hiện trong browser | Đặt secret vào Swagger UI OAuth config | Dùng public client với PKCE; không phân phối client secret |

## 15. Quy trình triển khai và kiểm thử

Thực hiện theo thứ tự để hai lớp contract và enforcement luôn khớp:

1. Xác định API dùng Bearer token đơn giản hay OAuth2 flow; ghi rõ issuer, audience, scope và token format.
2. Cấu hình Resource Server để xác minh token; không tự giả định API là Authorization Server.
3. Thiết lập authorization rule theo path, HTTP method, role hoặc scope.
4. Khai báo OpenAPI security scheme và requirement tương ứng bằng annotation hoặc OpenAPI bean.
5. Đánh dấu endpoint public rõ ràng trong document và `permitAll()` ở runtime.
6. Cấu hình Swagger UI OAuth2 client/PKCE nếu cần đăng nhập tương tác.
7. Cấu hình CORS nếu UI và API khác origin.
8. Test document `/v3/api-docs` để xác nhận scheme, flow, scope và operation security.
9. Test 401/403/200 bằng MockMvc và JWT test post-processor.
10. Test JWT chữ ký/issuer/expiry thật bằng test key/JWKS hoặc Identity Provider test.
11. Kiểm tra Try it out trên domain public và xác minh token không bị lộ trong log.
12. Chạy regression test trước khi phát hành.

## 16. Checklist trước khi phát hành

- [ ] Đã xác định rõ Bearer JWT, OAuth2 access token hay token opaque.
- [ ] Security scheme trong OpenAPI đúng với cách client gửi credential.
- [ ] `bearerFormat` chỉ được dùng như mô tả, không bị nhầm là cơ chế xác minh JWT.
- [ ] OAuth2 authorization/token URL trỏ tới Identity Provider thật.
- [ ] Scope trong OpenAPI khớp scope được cấp và kiểm tra ở runtime.
- [ ] Spring Security xác minh chữ ký, issuer và thời hạn token.
- [ ] Có kiểm tra audience nếu hệ thống yêu cầu audience cụ thể.
- [ ] Rule phân quyền được áp dụng theo endpoint/method cần thiết.
- [ ] Endpoint public được mô tả và cấu hình `permitAll()` nhất quán.
- [ ] Tài liệu API được bảo vệ hoặc public theo đúng policy.
- [ ] Swagger UI dùng PKCE cho public browser client khi dùng Authorization Code.
- [ ] Không đưa client secret vào JavaScript/browser.
- [ ] CORS cho phép đúng origin và header `Authorization` nếu cần.
- [ ] Test document xác minh security scheme và requirement.
- [ ] Test runtime xác minh 401, 403 và truy cập thành công.
- [ ] Có test xác minh JWT thật, không chỉ dùng mock authentication.

## 17. Tài liệu tham khảo chính thức

- [springdoc-openapi — Security](https://springdoc.org/#javadoc-support) — tích hợp annotation Swagger/OpenAPI để mô tả security scheme và requirement.
- [OpenAPI Specification — Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object) — mô tả HTTP bearer và OAuth2 flows.
- [OpenAPI Specification — Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object) — áp dụng security scheme ở root hoặc operation.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — cấu hình JWT decoder, issuer và authorities.
- [Spring Security — Testing OAuth2](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html) — kiểm thử request được xác thực bằng OAuth2/JWT với MockMvc.
- [Swagger UI — OAuth2 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/) — cấu hình OAuth2 và PKCE trong Swagger UI.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) — cấu hình CORS trong Spring MVC.

OpenAPI cho developer biết API yêu cầu Bearer hoặc OAuth2 như thế nào; Spring Security mới là lớp thực sự xác minh token và quyết định quyền truy cập. Hãy kiểm tra cả document được springdoc sinh và hành vi runtime bằng các trường hợp không token, token sai, thiếu scope và đủ scope. Chỉ khi hai phía thống nhất, Swagger UI mới trở thành công cụ thử API đáng tin cậy.
