# Mô tả API khác với cài đặt hành vi hoặc bảo mật API

Springdoc-openapi tạo tài liệu OpenAPI từ controller, DTO và các metadata của ứng dụng Spring Boot. Tài liệu này cho client biết API có endpoint nào, nhận parameter/body ra sao, trả response gì, dùng schema nào và yêu cầu cơ chế xác thực nào. Tuy nhiên, mô tả một quy tắc không đồng nghĩa với việc thực thi quy tắc đó.

Một OpenAPI document có thể khai báo endpoint cần Bearer JWT, field không được để trống, response lỗi 403 hoặc giới hạn page size. Những khai báo này giúp client và công cụ hiểu hợp đồng. Chúng không tự xác minh chữ ký JWT, kiểm tra vai trò người dùng, từ chối chuỗi rỗng, chặn truy cập trái phép hoặc giới hạn số request. Các hành vi đó phải được triển khai và kiểm thử trong Spring MVC, Bean Validation, Spring Security, filter/interceptor, service hoặc API gateway.

Bài học này phân biệt rõ ba lớp:

1. **Mô tả hợp đồng:** OpenAPI, Springdoc annotations, schema, examples, security schemes và responses.
2. **Hành vi ứng dụng:** request mapping, binding, validation, business rules, exception handling và serialization.
3. **Chính sách bảo mật/vận hành:** authentication, authorization, CORS, CSRF, rate limiting, network policy, logging và gateway.

Mục tiêu là tránh tình trạng Swagger UI trông có vẻ an toàn nhưng endpoint thật vẫn mở, hoặc tài liệu công bố một quy tắc mà server không thực thi.

## 1. Hợp đồng API và hành vi runtime là hai việc khác nhau

Hợp đồng API là cam kết có thể quan sát từ phía client. Hành vi runtime là những gì server thật sự làm khi nhận request.

| Chủ đề | Mô tả trong OpenAPI/Springdoc | Thực thi runtime |
| --- | --- | --- |
| Endpoint | @Operation, @Parameter, Swagger @RequestBody, @ApiResponse và mapping metadata được Springdoc đọc | @GetMapping, @PostMapping, Spring @RequestBody, controller, handler mapping |
| Kiểu dữ liệu | @Schema, @ArraySchema, examples, required properties | Java type, Jackson, validation, converter |
| Bắt buộc nhập | required trong Parameter/Schema | @RequestParam(required = true), @NotNull, @NotBlank, @Valid |
| Xác thực | @SecurityScheme, @SecurityRequirement | Spring Security filter chain, JWT decoder, session/authentication provider |
| Phân quyền | Mô tả security scope/role trong operation | requestMatcher, @PreAuthorize, authorization manager |
| CORS | Có thể mô tả thông tin liên quan trong tài liệu riêng hoặc extension | CorsConfigurationSource, Security CORS config, @CrossOrigin |
| CSRF | Mô tả cơ chế/điều kiện bảo vệ cho client | CsrfFilter và CsrfTokenRepository |
| Rate limit | Có thể mô tả quota bằng description hoặc extension | Gateway, Bucket4j, Redis, filter hoặc service chuyên trách |
| Response lỗi | @ApiResponse mô tả status/schema/example | ResponseEntity, @ResponseStatus, @ExceptionHandler |
| Phiên bản | server URL, path/header parameter, deprecated metadata | Route mapping, version resolver, compatibility logic |

Ví dụ: @SecurityRequirement(name = "bearerAuth") nói rằng client cần gửi Bearer token theo security scheme đã định nghĩa. Annotation đó không tạo filter kiểm tra token. Muốn endpoint từ chối token thiếu hoặc sai, ứng dụng phải cấu hình Spring Security.

## 2. Ba câu hỏi cần trả lời trước khi công bố tài liệu

Với mỗi quy tắc xuất hiện trong Swagger UI, hãy tự hỏi:

1. **Tài liệu nói gì?** Client có thể đọc được quy tắc đó trong OpenAPI JSON/YAML hay không?
2. **Server thực thi ở đâu?** Có controller, validator, security filter, service hoặc gateway thực sự áp dụng quy tắc không?
3. **Có test chứng minh không?** Request vi phạm quy tắc có bị từ chối đúng status và response body không?

Một quy tắc chỉ được xem là hoàn chỉnh khi cả ba câu trả lời đều rõ. Không nên coi một annotation OpenAPI là biện pháp bảo mật hoặc validation.

## 3. @Operation chỉ mô tả operation

@Operation giúp đặt summary, description, operationId, tags và các metadata cho endpoint:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Lấy đơn hàng theo mã",
        description = """
            Trả về thông tin đơn hàng mà người dùng hiện tại được phép xem.
            Endpoint yêu cầu Bearer JWT.
            """
    )
    public OrderResponse getById(@PathVariable UUID id) {
        return orderService.getVisibleOrder(id);
    }
}
~~~

@Operation không tự:

- Kiểm tra token.
- Kiểm tra người gọi có quyền xem đơn hàng hay không.
- Kiểm tra đơn hàng có thuộc tenant hiện tại hay không.
- Tạo transaction hoặc gọi service.
- Thay đổi status code của response.

Những việc đó nằm ở Spring Security, controller/service và các thành phần runtime khác. Description là thông tin dành cho người đọc; nó không phải executable policy.

## 4. @Parameter mô tả parameter, không thay thế binding hoặc validation

Ví dụ tài liệu:

~~~java
@GetMapping
@Operation(summary = "Tìm đơn hàng")
public List<OrderResponse> search(
        @Parameter(
            description = "Trạng thái đơn hàng",
            example = "PAID"
        )
        @RequestParam(required = false) String status) {
    return orderService.search(status);
}
~~~

@Parameter bổ sung description/example cho OpenAPI. @RequestParam mới là annotation tham gia binding query parameter trong Spring MVC.

Nếu status chỉ được nhận một tập giá trị, hãy dùng enum hoặc validator:

~~~java
public enum OrderStatus {
    PENDING, PAID, SHIPPED, CANCELLED
}

@GetMapping
public List<OrderResponse> search(
        @RequestParam(required = false) OrderStatus status) {
    return orderService.search(status);
}
~~~

Khi client gửi một giá trị không chuyển đổi được thành enum, Spring MVC có thể trả lỗi binding. Nếu cần error response thống nhất, cấu hình @RestControllerAdvice để chuẩn hóa lỗi.

## 5. @Schema mô tả dữ liệu, không tự kiểm tra dữ liệu

@Schema có thể cung cấp type, format, description, example, allowable values, minimum, maximum, minLength, maxLength, pattern và access mode:

~~~java
public record CreateCustomerRequest(
    @Schema(
        description = "Tên hiển thị",
        example = "Nguyen An",
        minLength = 2,
        maxLength = 100
    )
    String displayName,

    @Schema(
        description = "Tuổi của khách hàng",
        example = "28",
        minimum = "18",
        maximum = "120"
    )
    Integer age
) {}
~~~

Các metadata trên giúp OpenAPI mô tả ràng buộc. Chúng không tự đảm bảo Spring MVC từ chối request không hợp lệ. Hãy thêm Bean Validation:

~~~java
public record CreateCustomerRequest(
    @NotBlank
    @Size(min = 2, max = 100)
    String displayName,

    @NotNull
    @Min(18)
    @Max(120)
    Integer age
) {}
~~~

Và kích hoạt validation ở controller:

~~~java
@PostMapping
public ResponseEntity<CustomerResponse> create(
        @Valid @RequestBody CreateCustomerRequest request) {
    CustomerResponse created = customerService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(created);
}
~~~

Hai nhóm annotation có vai trò bổ trợ:

- @Schema giúp client hiểu ràng buộc được công bố.
- @NotBlank, @Size, @Min, @Max và @Valid tham gia kiểm tra request runtime.

Nếu chỉ khai báo minLength trong @Schema nhưng không có validation thực tế, client có thể gửi chuỗi rỗng và server vẫn chấp nhận nếu service không kiểm tra.

## 6. required trong OpenAPI khác nullable và validation

Trong OpenAPI, required thường mô tả việc property hoặc parameter phải có mặt trong request. Nullable mô tả giá trị null có được chấp nhận hay không. Đây không phải cùng một khái niệm.

Ví dụ:

~~~yaml
type: object
required:
  - displayName
properties:
  displayName:
    type: string
    minLength: 1
  nickname:
    type: string
    nullable: true
~~~

Ví dụ nullable trên dùng cách biểu diễn OpenAPI 3.0. Với OpenAPI 3.1, null được biểu diễn theo JSON Schema type/union tương ứng; hãy kiểm tra version document mà ứng dụng phát hành.

displayName bắt buộc phải xuất hiện; nickname không bắt buộc và có thể null theo schema trên. Runtime phải có DTO, Jackson và Bean Validation tương ứng. Không suy luận rằng OpenAPI required tự làm cho Spring MVC trả 400.

Một số lưu ý:

- @NotNull kiểm tra giá trị không null.
- @NotBlank kiểm tra chuỗi không null, không rỗng và không chỉ có whitespace.
- @NotEmpty kiểm tra chuỗi/collection/map không rỗng nhưng chuỗi chỉ có khoảng trắng vẫn có thể qua.
- @Size kiểm tra kích thước, không thay thế @NotNull.
- @Schema(requiredMode = REQUIRED) mô tả required trong tài liệu; nó không thay thế constraint runtime.

## 7. @ApiResponse mô tả response, không tạo status code

Ví dụ:

~~~java
@GetMapping("/{id}")
@Operation(summary = "Lấy khách hàng")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Tìm thấy khách hàng",
        content = @Content(
            schema = @Schema(implementation = CustomerResponse.class)
        )
    ),
    @ApiResponse(responseCode = "404", description = "Không tìm thấy")
})
public CustomerResponse getById(@PathVariable UUID id) {
    return customerService.getById(id);
}
~~~

@ApiResponse responseCode = "404" chỉ khai báo response 404 trong tài liệu. Nó không khiến method tự trả 404 khi ID không tồn tại.

Runtime có thể dùng exception chuyên biệt:

~~~java
public CustomerResponse getById(UUID id) {
    return repository.findById(id)
        .map(mapper::toResponse)
        .orElseThrow(() -> new CustomerNotFoundException(id));
}
~~~

Và exception handler:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(
            CustomerNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Customer not found");
        problem.setDetail("Không tìm thấy khách hàng được yêu cầu.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

Hãy kiểm tra cả tài liệu lẫn runtime để chắc chắn response 404 thực sự có body đúng schema đã công bố.

## 8. Phân biệt authentication và authorization

**Authentication (xác thực)** trả lời: người gửi request là ai? Ví dụ xác minh chữ ký JWT, issuer, audience, expiration hoặc session.

**Authorization (phân quyền)** trả lời: người đó được phép làm hành động nào trên tài nguyên nào? Ví dụ chỉ chủ đơn hàng hoặc nhân viên có role phù hợp mới được xem đơn hàng.

OpenAPI security scheme thường mô tả cách client cung cấp thông tin xác thực. Phân quyền ở mức nghiệp vụ vẫn phải được thực thi ở server.

| Tình huống | Kết quả thường gặp |
| --- | --- |
| Không có thông tin xác thực ở endpoint yêu cầu login | 401 Unauthorized |
| Token/session không hợp lệ hoặc hết hạn | 401 Unauthorized |
| Đã xác thực nhưng không đủ quyền | 403 Forbidden |
| Được phép truy cập nhưng tài nguyên không tồn tại | 404 Not Found |

Không dùng 404 như một cách thay thế tùy tiện cho authorization. Một số hệ thống chủ động che giấu sự tồn tại của tài nguyên bằng 404; nếu chọn chính sách đó, phải áp dụng nhất quán và mô tả đúng hợp đồng.

## 9. Khai báo Bearer JWT trong OpenAPI

Springdoc có thể mô tả HTTP Bearer scheme bằng @SecurityScheme:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "JWT access token trong header Authorization"
)
public class OpenApiSecurityConfiguration {
}
~~~

Khi đó OpenAPI có thể sinh security scheme tương tự:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
~~~

Swagger UI sẽ hiển thị cơ chế Authorize để người dùng nhập token. Đây là trải nghiệm client và metadata của hợp đồng; nó không xác minh token thay server.

## 10. Gắn security requirement ở mức operation

Nếu không khai báo security toàn cục, có thể gắn requirement lên controller hoặc operation:

~~~java
@RestController
@RequestMapping("/api/profile")
@SecurityRequirement(name = "bearerAuth")
public class ProfileController {

    @GetMapping
    @Operation(summary = "Xem hồ sơ hiện tại")
    public ProfileResponse me() {
        return profileService.currentProfile();
    }
}
~~~

Security requirement trong OpenAPI nói client phải dùng scheme có tên bearerAuth. Tên này phải khớp với key được khai báo trong components.securitySchemes.

Nếu tên không khớp, tài liệu có thể chứa reference không hợp lệ hoặc Swagger UI không hiển thị đúng cơ chế xác thực.

## 11. Endpoint công khai khi tài liệu có security toàn cục

Nếu OpenAPI khai báo security requirement toàn cục, endpoint public cần được mô tả là không yêu cầu security:

~~~java
@GetMapping("/health")
@Operation(
    summary = "Kiểm tra trạng thái dịch vụ",
    security = {}
)
public HealthResponse health() {
    return healthService.currentStatus();
}
~~~

Trong OpenAPI, security array rỗng ở operation có thể ghi đè requirement toàn cục. Điều này chỉ ảnh hưởng mô tả hợp đồng.

Runtime vẫn phải cấu hình endpoint tương ứng là permitAll nếu đó là chính sách mong muốn. Ngược lại, nếu tài liệu đánh dấu endpoint public nhưng Spring Security yêu cầu token, Swagger UI sẽ hướng dẫn client sai.

## 12. Cài đặt JWT resource server bằng Spring Security

Ví dụ cấu hình runtime cho API nhận Bearer JWT:

~~~java
@Configuration
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/v3/api-docs/**",
                    "/swagger-ui/**",
                    "/swagger-ui.html"
                ).permitAll()
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ trên minh họa filter chain, không phải cấu hình dùng nguyên xi cho mọi hệ thống. Cần quyết định:

- API dùng JWT stateless hay session/cookie.
- CSRF có cần bật hay không.
- Tài liệu Swagger có public hay yêu cầu đăng nhập.
- Endpoint nào permitAll, endpoint nào authenticated hoặc yêu cầu role.
- JWT issuer, audience, key rotation và claim mapping được cấu hình ở đâu.

Khi dùng JWT resource server, ứng dụng còn cần dependency phù hợp và cấu hình decoder/issuer, ví dụ spring.security.oauth2.resourceserver.jwt.issuer-uri. Không có issuer/decoder hợp lệ thì khai báo @SecurityScheme trong OpenAPI không làm JWT hoạt động.

## 13. Phân quyền ở mức method bằng @PreAuthorize

Có thể bảo vệ hành động nghiệp vụ bằng method security:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasRole('ADMIN') or @orderAccess.canRead(#id, authentication)")
    public OrderResponse getVisibleOrder(UUID id) {
        return repository.findById(id)
            .map(mapper::toResponse)
            .orElseThrow(() -> new OrderNotFoundException(id));
    }
}
~~~

@PreAuthorize là cơ chế runtime khi method security đã được bật bằng @EnableMethodSecurity. Biểu thức kiểm tra role hoặc bean authorization trước khi method thực thi.

Đối chiếu:

- @SecurityRequirement mô tả scheme xác thực trong OpenAPI.
- authenticated() trong SecurityFilterChain yêu cầu request đã được xác thực.
- hasRole('ADMIN') hoặc @PreAuthorize kiểm tra quyền runtime.
- OAuth2 scope trong OpenAPI mô tả scope mà client cần; server vẫn phải kiểm tra authority/scope tương ứng.

Không để controller trả dữ liệu theo ID do client truyền mà không xác minh quyền truy cập đối với chính tài nguyên đó. Authentication thành công không có nghĩa là user được xem mọi orderId.

## 14. OAuth2 scopes trong tài liệu và kiểm tra authority runtime

OpenAPI có thể mô tả OAuth2 authorization flow và scopes:

~~~java
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth/authorize",
            tokenUrl = "https://identity.example.com/oauth/token",
            scopes = {
                @OAuthScope(name = "orders:read", description = "Đọc đơn hàng"),
                @OAuthScope(name = "orders:write", description = "Tạo hoặc sửa đơn hàng")
            }
        )
    )
)
~~~

Operation có thể khai báo scope:

~~~java
@Operation(
    summary = "Đọc đơn hàng",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders:read"}
    )
)
~~~

Đây là hợp đồng dành cho client. Runtime phải map claim/scope trong token thành GrantedAuthority và kiểm tra quyền, ví dụ:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public OrderResponse getOrder(UUID id) {
    return orderService.load(id);
}
~~~

Nếu OpenAPI khai báo orders:read nhưng server không kiểm tra authority, tài liệu đang hứa một chính sách mà runtime không thực hiện. Ngược lại, nếu server yêu cầu scope nhưng tài liệu không nêu, client sẽ khó tích hợp.

## 15. API key không tự được xác minh bởi @SecurityScheme

OpenAPI có thể mô tả API key:

~~~java
@SecurityScheme(
    name = "partnerApiKey",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-Partner-Key",
    description = "API key do hệ thống đối tác cấp"
)
~~~

Điều này giúp Swagger UI biết cần gửi header X-Partner-Key. Server vẫn phải có filter hoặc authentication provider kiểm tra:

- Header có tồn tại không.
- Key có hợp lệ, còn hiệu lực và chưa bị thu hồi không.
- Key thuộc partner nào.
- Partner có quyền gọi operation đó không.
- Quota của partner còn hay đã vượt giới hạn.

Không đưa API key thật vào example, source code, file cấu hình commit lên Git hoặc OpenAPI document công khai.

## 16. Ẩn Swagger UI không bảo vệ endpoint

Các annotation/configuration ẩn tài liệu chỉ tác động đến khả năng hiển thị:

- @Hidden hoặc @Operation(hidden = true) có thể loại operation khỏi OpenAPI.
- GroupedOpenApi có thể giới hạn path được đưa vào một group.
- Swagger UI có thể bị tắt hoặc không được expose.
- /v3/api-docs có thể bị bảo vệ riêng.

Không điều nào trong số đó tự thay thế authorization cho business endpoint.

Ví dụ, ẩn /api/admin/** khỏi Swagger UI nhưng SecurityFilterChain vẫn permitAll thì endpoint vẫn có thể bị gọi trực tiếp bằng curl hoặc HTTP client.

Ngược lại, giữ tài liệu public không có nghĩa business endpoint phải public. Có thể cho phép đọc OpenAPI document nhưng bảo vệ mọi operation bằng Spring Security. Cần phân biệt quyền đọc tài liệu với quyền gọi API.

## 17. CORS là chính sách runtime của browser, không phải authentication

CORS (Cross-Origin Resource Sharing) quyết định browser có cho JavaScript từ origin này đọc response của origin khác hay không. CORS không xác thực người dùng và không thay thế authorization.

Cấu hình CORS trong Spring:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://app.example.com"));
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE")
    );
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Request-Id")
    );
    configuration.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
~~~

Kích hoạt CORS trong filter chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Khi dùng credentials, không đặt allowedOrigins thành wildcard *. Hãy giới hạn origin đáng tin cậy. CORS chủ yếu là kiểm soát browser; một HTTP client không phải browser vẫn có thể gọi endpoint, vì vậy backend vẫn phải xác thực và phân quyền.

## 18. CSRF phụ thuộc cách lưu thông tin xác thực

CSRF (Cross-Site Request Forgery) thường quan trọng khi browser tự động gửi credential như session cookie. Nếu ứng dụng dùng cookie/session, cần đánh giá CSRF token và cấu hình phù hợp.

Với API dùng Bearer token được gửi tường minh trong Authorization header và không dựa vào cookie tự động, mô hình CSRF có thể khác. Tuy nhiên, không nên tắt CSRF chỉ vì ứng dụng có URL bắt đầu bằng /api.

Quyết định bật/tắt CSRF cần dựa trên:

- Credential có được browser tự động gửi không.
- Session cookie có được dùng không.
- Có endpoint form/login hoặc cookie-authenticated nào không.
- Frontend gửi token trong header hay cookie.
- Cấu hình SameSite, Secure và HttpOnly của cookie.

OpenAPI có thể mô tả header/token mà client phải gửi, nhưng không tự triển khai CSRF protection.

## 19. Rate limiting và quota không được tạo bởi OpenAPI

Một operation description có thể ghi:

~~~java
@Operation(
    summary = "Gửi OTP",
    description = """
        Tối đa 3 lần gửi trong 10 phút cho một số điện thoại.
        Khi vượt quota, API trả HTTP 429.
        """
)
@ApiResponse(responseCode = "429", description = "Đã vượt giới hạn yêu cầu")
~~~

Các metadata trên không đếm request và không chặn người dùng. Runtime phải có cơ chế rate limit ở gateway, filter hoặc service.

Ví dụ thuật toán thường gặp:

- Fixed window: đếm request trong từng cửa sổ thời gian cố định.
- Sliding window: tính quota trên cửa sổ trượt.
- Token bucket: token được bổ sung theo tốc độ, request tiêu thụ token.
- Leaky bucket: xử lý lưu lượng theo tốc độ ổn định.

Rate limit nên được định danh theo policy phù hợp: IP, user, API key, tenant, endpoint hoặc kết hợp. Với hệ thống nhiều instance, bộ đếm cần chia sẻ qua Redis hoặc hạ tầng tương đương; bộ nhớ cục bộ của một instance không đảm bảo quota toàn cụm.

Khi vượt giới hạn, runtime thường trả 429 và có thể kèm Retry-After hoặc các header quota. Nếu công bố các header này, hãy mô tả chúng trong OpenAPI và kiểm tra chúng có thật trong response.

## 20. Security scheme, server policy và gateway policy

Không phải mọi chính sách bảo mật đều thuộc cùng một lớp:

| Chính sách | Lớp thường chịu trách nhiệm |
| --- | --- |
| JWT signature, issuer, expiration | Resource server / authentication provider |
| Role, scope, ownership, tenant | Spring Security method authorization / service |
| TLS termination, IP allowlist | Load balancer, ingress hoặc API gateway |
| WAF, bot protection | WAF/gateway |
| Rate limit, quota theo API key | Gateway hoặc distributed limiter |
| CORS | Browser policy được cấu hình ở gateway hoặc ứng dụng |
| Audit log | Application security/audit layer |
| OpenAPI security scheme | Hợp đồng mô tả cách client xác thực |

Một endpoint có thể đi qua nhiều lớp. Ví dụ gateway kiểm tra API key và rate limit, Spring Security kiểm tra JWT, service kiểm tra quyền sở hữu đơn hàng. OpenAPI cần mô tả đúng phần client phải làm, nhưng không thể thay thế cấu hình ở bất kỳ lớp runtime nào.

## 21. Mô tả response 401 và 403

Có thể khai báo response lỗi ở operation:

~~~java
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Thành công"),
    @ApiResponse(
        responseCode = "401",
        description = "Thiếu hoặc không hợp lệ thông tin xác thực",
        content = @Content(
            schema = @Schema(implementation = ProblemDetail.class)
        )
    ),
    @ApiResponse(
        responseCode = "403",
        description = "Đã xác thực nhưng không đủ quyền",
        content = @Content(
            schema = @Schema(implementation = ProblemDetail.class)
        )
    )
})
~~~

Để runtime thực sự trả đúng status:

- AuthenticationEntryPoint xử lý request chưa xác thực hoặc credential không hợp lệ.
- AccessDeniedHandler xử lý request đã xác thực nhưng không được phép.
- Exception handler của ứng dụng xử lý lỗi nghiệp vụ như tài nguyên không tồn tại.

Không giả định @RestControllerAdvice sẽ bắt mọi lỗi từ Spring Security filter chain. Nhiều lỗi bảo mật xảy ra trước khi request đi vào controller, do đó cần cấu hình handler tương ứng trong HttpSecurity.

## 22. Tách security error response khỏi business error response

Có thể thống nhất schema lỗi công khai bằng ProblemDetail hoặc DTO riêng. Tuy nhiên, cần xác định lớp nào phát sinh lỗi:

| Lỗi | Nơi thường phát sinh | Cơ chế xử lý |
| --- | --- | --- |
| JWT thiếu/sai | Security filter chain | AuthenticationEntryPoint |
| Đã đăng nhập nhưng thiếu quyền | Authorization filter/method security | AccessDeniedHandler |
| Request body không hợp lệ | Spring MVC/Bean Validation | MethodArgumentNotValidException handler |
| Parameter không parse được | Spring MVC binding | TypeMismatch/MethodArgumentTypeMismatch handler |
| Không tìm thấy tài nguyên | Controller/service | Exception handler |
| Vượt quota | Gateway/filter | Rate-limit response handler |

Nếu các lớp trả body khác nhau, OpenAPI nên mô tả đúng từng response hoặc chuẩn hóa runtime trước. Đừng công bố một ErrorResponse duy nhất nếu 401, 403, 400 và 429 thực tế có cấu trúc khác nhau.

## 23. Phiên bản API và deprecation

OpenAPI có thể mô tả version qua server URL, path, header parameter hoặc metadata. Ví dụ:

~~~java
@Operation(
    summary = "Lấy hồ sơ",
    deprecated = true,
    description = "Endpoint cũ; dùng /api/v2/profile thay thế."
)
~~~

deprecated = true đánh dấu operation không còn được khuyến nghị. Nó không tắt endpoint và không tự chuyển request sang phiên bản mới.

Runtime cần giữ route cũ trong thời gian tương thích, xử lý version resolver hoặc trả lỗi theo chính sách sunset đã công bố. Việc xóa mapping là thay đổi runtime; việc đánh dấu deprecated là thông tin hợp đồng.

## 24. Phân biệt @Hidden với bảo vệ truy cập

Ví dụ:

~~~java
@Hidden
@RestController
@RequestMapping("/internal/diagnostics")
public class DiagnosticsController {

    @GetMapping
    public DiagnosticsResponse inspect() {
        return diagnosticsService.inspect();
    }
}
~~~

@Hidden có thể loại controller khỏi tài liệu. Nhưng nếu SecurityFilterChain không chặn /internal/diagnostics, người dùng vẫn có thể gọi URL trực tiếp.

Hãy kết hợp với chính sách runtime:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/internal/diagnostics/**").hasRole("OPS")
    .anyRequest().authenticated()
);
~~~

Không dùng ẩn tài liệu như một cách bảo vệ bí mật. Security through obscurity không thay thế authentication, authorization, network isolation hoặc audit.

## 25. Kiểm thử tài liệu và kiểm thử runtime là hai bộ test

Một integration test tải /v3/api-docs có thể kiểm tra security scheme và response metadata:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentsBearerAuthentication() throws Exception {
        String json = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(json);

        assertThat(
            spec.at("/components/securitySchemes/bearerAuth/scheme").asText()
        ).isEqualTo("bearer");
    }
}
~~~

Test này chỉ chứng minh tài liệu có khai báo Bearer scheme. Nó không chứng minh token được xác minh.

## 26. Kiểm thử runtime: thiếu token phải bị từ chối

Với endpoint yêu cầu authentication:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsAnonymousRequest() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Kết quả phụ thuộc SecurityFilterChain thật và test configuration. Nếu test đang dùng mock user hoặc filter bị tắt, nó không chứng minh request anonymous bị chặn.

## 27. Kiểm thử runtime: user có authentication nhưng không đủ quyền

Với method security hoặc request authorization:

~~~java
@Test
@WithMockUser(roles = "CUSTOMER")
void deniesCustomerFromAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
        .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void allowsAdminToReadAdminEndpoint() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
        .andExpect(status().isOk());
}
~~~

Các test này xác minh authorization ở runtime với security context mô phỏng. Nếu ứng dụng dùng JWT claim mapping riêng, nên bổ sung test JWT converter hoặc resource server với token test có claim/scope phù hợp.

## 28. Kiểm thử validation runtime

OpenAPI schema có minLength không đủ. Hãy kiểm tra request vi phạm:

~~~java
@Test
void rejectsBlankDisplayName() throws Exception {
    mockMvc.perform(post("/api/customers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "displayName": "   ",
                  "age": 28
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Test này cần controller dùng @Valid và DTO có @NotBlank. Nếu response body theo ProblemDetail, hãy assert thêm title, status và field error theo contract đã công bố.

## 29. Kiểm thử 401/403 và response schema đồng bộ

Tài liệu security và runtime phải được kiểm tra song song:

~~~java
@Test
void documentsUnauthorizedAndForbiddenResponses() throws Exception {
    JsonNode spec = loadOpenApi();
    JsonNode responses = spec.at(
        "/paths/~1api~1orders/get/responses"
    );

    assertThat(responses.has("401")).isTrue();
    assertThat(responses.has("403")).isTrue();
}
~~~

Và test runtime:

~~~java
@Test
void anonymousAndForbiddenRequestsHaveExpectedStatuses() throws Exception {
    mockMvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());

    mockMvc.perform(get("/api/admin/reports")
            .with(user("customer").roles("CUSTOMER")))
        .andExpect(status().isForbidden());
}
~~~

Các ví dụ trên giả định test có helper loadOpenApi(), Spring Security test dependency và filter chain tương ứng. Hãy điều chỉnh endpoint/path JSON Pointer theo document thực tế.

## 30. Swagger UI Authorize không phải bằng chứng endpoint đã bảo vệ

Khi bấm Authorize và nhập token trong Swagger UI:

1. UI lưu token theo cơ chế của phiên làm việc.
2. UI thêm Authorization header vào request phù hợp với security requirement.
3. Server nhận request.
4. Spring Security hoặc gateway xác minh credential.
5. Authorization layer quyết định user có được phép thực hiện hành động hay không.

Nếu bước 4 hoặc 5 không tồn tại, giao diện vẫn có thể hiển thị nút Authorize nhưng server không được bảo vệ. Ngược lại, nếu server bảo vệ endpoint nhưng tài liệu không khai báo scheme, client có thể không biết cách gửi token.

Không đưa token thật hoặc thông tin bí mật vào ảnh chụp Swagger UI, log, example hoặc tài liệu chia sẻ.

## 31. Cấu hình bảo vệ Swagger UI và OpenAPI endpoint

Tùy chính sách tổ chức, tài liệu API có thể public, internal-only hoặc yêu cầu authentication. Đây là một quyết định runtime riêng.

Ví dụ bảo vệ docs:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/v3/api-docs/**", "/swagger-ui/**")
        .hasRole("DEVELOPER")
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Nếu docs yêu cầu login, người dùng cần có cách truy cập phù hợp. Với OAuth2, có thể cấu hình Swagger UI OAuth redirect/client settings; không nhúng client secret vào frontend công khai.

Nếu docs public, rà soát kỹ:

- Có endpoint nội bộ nào vô tình được đưa vào group public không?
- Có schema/example tiết lộ dữ liệu nội bộ hoặc token mẫu không?
- Có server URL trỏ nhầm môi trường development không?
- Có endpoint quản trị cần tách group hoặc ẩn khỏi tài liệu public không?

Việc giới hạn tài liệu giúp giảm lộ thông tin, nhưng vẫn phải bảo vệ endpoint runtime.

## 32. GroupedOpenApi chỉ chia tài liệu, không chia quyền truy cập

Ví dụ tạo group public và internal:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .build();
}

@Bean
GroupedOpenApi internalApi() {
    return GroupedOpenApi.builder()
        .group("internal")
        .pathsToMatch("/api/internal/**")
        .build();
}
~~~

Group điều khiển operation nào được đưa vào document. Nó không tạo SecurityFilterChain riêng và không tự bảo vệ /api/internal/**.

Muốn giới hạn truy cập internal API, cần cấu hình request matcher, role/scope, network policy hoặc gateway. Muốn giới hạn ai đọc internal OpenAPI document, bảo vệ URL group tương ứng bằng security runtime.

## 33. Các ví dụ annotation dễ bị hiểu nhầm

| Annotation/cấu hình | Tác động chính | Không tự làm gì |
| --- | --- | --- |
| @Operation | Mô tả operation | Không xử lý request |
| @Parameter | Mô tả parameter | Không tự bind query |
| @Schema | Mô tả schema | Không tự validate body |
| @ApiResponse | Mô tả response | Không tự tạo status code |
| @SecurityScheme | Khai báo cơ chế xác thực | Không xác minh token |
| @SecurityRequirement | Gắn security requirement cho operation | Không cấp quyền |
| @Hidden | Ẩn khỏi OpenAPI | Không chặn URL |
| @Deprecated hoặc deprecated metadata | Thông báo API cũ | Không tắt endpoint |
| @Valid | Kích hoạt validation ở điểm được hỗ trợ | Không thay thế mọi business rule |
| @PreAuthorize | Kiểm tra quyền khi method được gọi | Không thay thế xác thực credential ở filter chain |
| @CrossOrigin | Cấu hình CORS cho mapping | Không phải authentication |
| @GetMapping | Đăng ký route GET | Không tự yêu cầu login |

Một số annotation thuộc Spring runtime, một số thuộc Swagger/OpenAPI. Cần nhận biết package/import để tránh nhầm lẫn.

## 34. Lỗi thường gặp khi tài liệu và runtime không đồng bộ

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Swagger UI có Authorize nhưng request không bị chặn khi thiếu token | Chỉ khai báo @SecurityScheme/@SecurityRequirement | Cấu hình Spring Security authentication |
| Tài liệu nói endpoint public nhưng server trả 401 | Security requirement hoặc mô tả public sai | Đồng bộ OpenAPI với permitAll/authentication policy |
| Tài liệu ghi 403 nhưng runtime trả 200 | Chỉ khai báo @ApiResponse | Thực thi authorization và viết security test |
| Schema có minLength nhưng server nhận chuỗi rỗng | Chỉ có @Schema | Dùng Bean Validation và @Valid |
| Tài liệu ghi 429 nhưng không có rate limit | Chỉ thêm @ApiResponse | Cài limiter ở gateway/filter và test quota |
| Endpoint bị @Hidden nhưng curl vẫn gọi được | Ẩn docs không chặn route | Cấu hình authorization runtime |
| CORS lỗi nhưng token hợp lệ | Origin/header/method chưa được allow | Cấu hình CORS; không nới lỏng authentication |
| Browser gọi được nhưng client khác bị từ chối | Khác biệt credential/CORS/proxy | Phân tích request thực và policy từng lớp |
| 401 và 403 có body khác schema | Security handlers chưa thống nhất | Cấu hình AuthenticationEntryPoint/AccessDeniedHandler |
| Swagger docs không truy cập được sau khi bật security | URL docs chưa được permit hoặc chưa có role | Quyết định docs public/internal và cấu hình đúng |
| Group internal vẫn truy cập được endpoint bằng URL trực tiếp | GroupedOpenApi chỉ lọc document | Bảo vệ route bằng security matcher/gateway |
| Endpoint cũ vẫn chạy dù deprecated | Deprecated chỉ là metadata | Thực hiện lifecycle/version policy ở runtime |

## 35. Quy trình review một API trước khi công bố

Với mỗi operation:

1. Xác định audience: public, partner, internal hay admin.
2. Ghi request/response contract bằng OpenAPI.
3. Xác định authentication scheme và scopes/roles cần thiết.
4. Cấu hình Spring Security hoặc gateway để thực thi policy.
5. Thêm validation runtime cho request.
6. Kiểm tra quyền sở hữu/tenant trong service, không chỉ dựa vào ID client gửi.
7. Chuẩn hóa 400, 401, 403, 404, 409, 422 và 429 nếu endpoint có thể trả các lỗi đó.
8. Kiểm tra CORS, CSRF và rate limit theo cách credential được sử dụng.
9. Viết test OpenAPI để xác nhận hợp đồng.
10. Viết test runtime cho anonymous, authenticated, forbidden và invalid request.
11. Kiểm tra gateway/ingress policy ở môi trường triển khai.
12. So sánh document với hành vi thực tế trước khi publish.

## 36. Checklist hoàn thành

- [ ] Mỗi operation có summary, description và parameter rõ ràng.
- [ ] @Schema mô tả đúng kiểu, format, example và giới hạn dữ liệu.
- [ ] Ràng buộc quan trọng có Bean Validation hoặc business validation runtime.
- [ ] @ApiResponse khớp status code thực tế.
- [ ] Security scheme có tên nhất quán với security requirement.
- [ ] Endpoint public được mô tả public và runtime permitAll đúng chủ đích.
- [ ] Endpoint protected được mô tả security và runtime yêu cầu credential.
- [ ] Role/scope/ownership được kiểm tra tại runtime.
- [ ] Không coi @Hidden hoặc GroupedOpenApi là biện pháp bảo vệ URL.
- [ ] CORS được cấu hình cho origin cần thiết; không dùng wildcard tùy tiện với credentials.
- [ ] CSRF được đánh giá theo cách credential được lưu và gửi.
- [ ] Rate limit thực sự hoạt động nếu tài liệu công bố quota/429.
- [ ] Security handlers trả 401/403 đúng schema.
- [ ] Swagger UI và /v3/api-docs được bảo vệ theo chính sách đã chọn.
- [ ] Có OpenAPI contract test và runtime security/validation test.
- [ ] Gateway, ingress và application policy không mâu thuẫn nhau.
- [ ] Không đưa secret hoặc token thật vào document/example.

## 37. Kết luận

Springdoc-openapi giúp công bố hợp đồng API một cách có cấu trúc: endpoint, parameter, schema, response và cơ chế xác thực mà client cần sử dụng. Nhưng OpenAPI document là bản mô tả, không phải bộ máy thực thi chính sách. @SecurityRequirement không xác minh JWT; @Schema không validate request; @ApiResponse không tạo status code; @Hidden không chặn endpoint; GroupedOpenApi không tạo quyền truy cập.

Một API đáng tin cậy cần đồng bộ ba phần: tài liệu mô tả chính xác, ứng dụng thực thi đúng và test chứng minh cả hai. Hãy dùng Springdoc để giao tiếp hợp đồng với client, Spring MVC/Bean Validation để xử lý request, Spring Security để xác thực/phân quyền, gateway/filter để áp dụng chính sách vận hành, rồi kiểm thử runtime độc lập với kiểm thử OpenAPI. Đó là cách tránh cảm giác an toàn giả tạo do tài liệu Swagger đẹp nhưng endpoint thật không được bảo vệ.

## Tài liệu tham khảo

- [Springdoc OpenAPI — Documentation and FAQ](https://springdoc.org/)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [OpenAPI Specification — Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
