# Bảo mật được khai báo không tự tạo SecurityFilterChain hoặc kiểm tra token

Khi mô tả API bằng springdoc-openapi, có thể khai báo bearer token, API key, Basic Authentication hoặc OAuth2 để Swagger UI hiển thị nút Authorize và client generator biết cách gửi thông tin xác thực. Tuy nhiên, những khai báo này chỉ mô tả **hợp đồng bảo mật** trong OpenAPI. Chúng không tự tạo bộ lọc bảo mật, không xác minh chữ ký JWT, không kiểm tra API key và cũng không quyết định người dùng có quyền gọi endpoint hay không.

Trong Spring Boot, bảo vệ request thực tế thường do Spring Security đảm nhiệm thông qua **SecurityFilterChain**, authentication provider, resource server và quy tắc authorization. Hai phần cần được cấu hình đồng bộ: OpenAPI nói client phải gửi credential nào; backend thực sự xác minh credential đó và áp dụng quyền tương ứng.

## 1. Hai lớp bảo mật cần phân biệt

Một API có hai lớp bảo mật liên quan nhưng độc lập:

1. **Mô tả bảo mật trong OpenAPI:** cho biết operation yêu cầu cơ chế xác thực nào và client cần gửi credential ở đâu.
2. **Bảo vệ request tại runtime:** xác minh danh tính, kiểm tra quyền, áp dụng CSRF/CORS và quyết định cho phép hay từ chối request.

Ví dụ, OpenAPI có thể khai báo bearer JWT:

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

Cấu hình này cho Swagger UI biết rằng request cần header:

~~~http
Authorization: Bearer <access-token>
~~~

Nhưng nếu ứng dụng không có SecurityFilterChain hoặc resource server phù hợp, server có thể vẫn chấp nhận request không có token. Ngược lại, backend có thể bắt buộc token nhưng tài liệu OpenAPI không khai báo security scheme; khi đó client đọc tài liệu sẽ không biết cách xác thực.

Cần kiểm tra cả tài liệu lẫn hành vi thực tế, không dùng một bên làm bằng chứng cho bên còn lại.

## 2. @SecurityScheme định nghĩa cơ chế trong tài liệu

Annotation @SecurityScheme của swagger-annotations đăng ký một security scheme trong components.securitySchemes.

Ví dụ bearer JWT:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Access token dạng JWT"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

Kết quả OpenAPI tương ứng:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Access token dạng JWT
~~~

Các thuộc tính có ý nghĩa:

- name: khóa của scheme trong components.securitySchemes.
- type: loại xác thực như http, apiKey, oauth2 hoặc openIdConnect.
- scheme: tên HTTP authentication scheme, ví dụ bearer hoặc basic.
- bearerFormat: gợi ý định dạng token; giá trị JWT chỉ là metadata.
- in và paramName: vị trí và tên parameter khi dùng API key.
- flows hoặc openIdConnectUrl: thông tin bổ sung cho OAuth2/OpenID Connect.

Đăng ký scheme không tạo ra bộ lọc Spring Security. bearerFormat = JWT cũng không khiến ứng dụng tự phân tích hoặc xác minh JWT.

## 3. @SecurityRequirement gắn scheme vào operation

Một scheme đã được đăng ký cần được gắn vào operation hoặc toàn bộ tài liệu bằng security requirement. Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/me")
@Operation(
    summary = "Lấy hồ sơ của người dùng hiện tại",
    security = @SecurityRequirement(name = "bearerAuth")
)
public ProfileResponse getCurrentProfile() {
    return profileService.currentProfile();
}
~~~

Tên bearerAuth trong @SecurityRequirement phải khớp chính xác với khóa đã khai báo trong @SecurityScheme.

OpenAPI đầu ra có thể có:

~~~yaml
paths:
  /api/me:
    get:
      security:
        - bearerAuth: []
~~~

Có thể đặt security requirement ở cấp tài liệu bằng @OpenAPIDefinition:

~~~java
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

Khi khai báo security ở cấp root, các operation thường kế thừa yêu cầu đó nếu không có security riêng. Hãy xem JSON sinh ra để xác minh operation nào thực sự được đánh dấu bảo vệ.

@SecurityRequirement chỉ nói rằng client cần dùng scheme đã đăng ký. Nó không kiểm tra token và không thay thế authorizeHttpRequests trong Spring Security.

## 4. Hiểu security requirement trong OpenAPI

OpenAPI biểu diễn security requirement bằng danh sách. Mỗi phần tử trong danh sách là một lựa chọn có thể đáp ứng; các scheme nằm trong cùng một phần tử phải được đáp ứng đồng thời.

Ví dụ chỉ cần bearer token:

~~~yaml
security:
  - bearerAuth: []
~~~

Nếu operation chấp nhận một trong hai cách xác thực, có thể biểu diễn thành hai lựa chọn:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

Nếu cả bearer token và API key đều bắt buộc cùng lúc, đặt chúng trong cùng một phần tử:

~~~yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
~~~

Một operation có thể công khai dù tài liệu đặt security ở cấp root. Trong OpenAPI, security: [] ở operation biểu thị operation đó không yêu cầu security; một requirement có object rỗng {} biểu thị lựa chọn truy cập ẩn danh bên cạnh lựa chọn có xác thực:

~~~yaml
paths:
  /api/catalog:
    get:
      security: []
      summary: Danh sách công khai
      responses:
        '200':
          description: Thành công
  /api/profile:
    get:
      security:
        - bearerAuth: []
        - {}
~~~

Không nhầm security: [] với việc bỏ qua trường security. Nếu operation không khai báo security riêng, nó có thể kế thừa yêu cầu ở cấp root.

## 5. SecurityFilterChain mới bảo vệ request thực tế

Trong Spring Security, SecurityFilterChain xác định request nào đi qua bộ lọc nào, cần xác thực ra sao và được phép truy cập tài nguyên nào.

Ví dụ cấu hình API stateless dùng bearer JWT với Spring Boot 3 và Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    "/v3/api-docs/**",
                    "/swagger-ui/**",
                    "/swagger-ui.html"
                ).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Cấu hình trên thực hiện các việc khác nhau:

- csrf: xác định chính sách chống CSRF.
- sessionManagement: không lưu session xác thực cho API stateless.
- authorizeHttpRequests: quyết định request nào công khai, cần scope hoặc cần đăng nhập.
- oauth2ResourceServer().jwt(...): bật cơ chế xác minh bearer JWT.
- SecurityFilterChain: đăng ký chuỗi filter thực sự xử lý request.

Ví dụ cho phép /v3/api-docs/** và /swagger-ui/** truy cập công khai chỉ phù hợp khi tổ chức muốn công bố tài liệu. Nếu tài liệu nội bộ hoặc chứa thông tin không dành cho công chúng, hãy bảo vệ các đường dẫn này theo chính sách riêng.

Chỉ tắt CSRF khi mô hình xác thực thực sự phù hợp, chẳng hạn API stateless dùng bearer token trong Authorization header và không dựa vào cookie được trình duyệt tự động gửi. Nếu dùng session cookie hoặc cookie authentication, cần đánh giá và giữ cơ chế CSRF phù hợp.

## 6. Cấu hình JWT Resource Server

Để Spring Security xác minh JWT, dự án cần dependency resource server. Với Maven và Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Có thể cấu hình issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
~~~

Spring Security dùng metadata của issuer để tìm khóa công khai và cấu hình decoder. Khi nhận bearer token, resource server kiểm tra chữ ký và các claim thời gian/issuer theo cấu hình. Token hết hạn, chữ ký không hợp lệ hoặc issuer không phù hợp sẽ không được chấp nhận.

Nếu API yêu cầu kiểm tra audience, hãy cấu hình validator bổ sung tương ứng. Không nên cho rằng chỉ khai báo issuer-uri đã tự động đáp ứng mọi quy tắc riêng của hệ thống.

Trong OpenAPI, scheme bearer chỉ mô tả cách client gửi token. Nó không chỉ định issuer URI để Spring tự cấu hình, không tạo JWT và không quyết định claim nào được tin cậy.

## 7. Phân biệt authentication và authorization

Hai bước thường bị nhầm:

- **Authentication (xác thực):** xác định người gọi là ai và credential có hợp lệ không.
- **Authorization (phân quyền):** quyết định người gọi có được phép thực hiện hành động hoặc truy cập tài nguyên đó không.

Ví dụ:

- Không gửi token: request có thể bị từ chối với 401.
- Gửi token hết hạn hoặc sai chữ ký: xác thực thất bại, thường trả 401.
- Token hợp lệ nhưng thiếu scope orders.write: xác thực thành công nhưng không đủ quyền, thường trả 403.
- Token có scope phù hợp: request có thể tiếp tục tới controller, nhưng service vẫn cần kiểm tra quyền sở hữu hoặc quy tắc nghiệp vụ nếu cần.

Không phải cứ có token là được phép gọi mọi endpoint. OpenAPI security requirement mô tả credential; authorization policy cần được triển khai trong SecurityFilterChain hoặc tầng nghiệp vụ.

## 8. Ánh xạ scope và authority

Với JWT OAuth2, Spring Security thường ánh xạ claim scope/scp thành authority có tiền tố SCOPE_.

Ví dụ token có scope:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write"
}
~~~

Có thể kiểm tra authority trong cấu hình HTTP:

~~~java
.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
)
~~~

Hoặc bảo vệ method service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderResponse findById(String id) {
        // Tìm và trả về đơn hàng.
        return repository.findResponseById(id);
    }
}
~~~

Để dùng @PreAuthorize, cần bật method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Cần kiểm tra claim thực tế từ identity provider. Một số hệ thống dùng roles, groups hoặc claim tùy chỉnh thay cho scope; khi đó cần cấu hình converter để ánh xạ sang GrantedAuthority. Không đổi tên authority trong OpenAPI rồi kỳ vọng Spring Security tự hiểu claim.

## 9. Khai báo API key trong OpenAPI

API key thường được gửi qua header, query parameter hoặc cookie. Ví dụ API key qua header:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "API key do hệ thống cấp"
)
@Configuration
class ApiKeyOpenApiConfiguration {
}
~~~

OpenAPI tương ứng:

~~~yaml
components:
  securitySchemes:
    apiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
~~~

Gắn scheme vào operation:

~~~java
@Operation(
    summary = "Tra cứu dữ liệu đối tác",
    security = @SecurityRequirement(name = "apiKeyAuth")
)
@GetMapping("/api/partner/data")
public PartnerDataResponse getPartnerData() {
    return partnerService.loadData();
}
~~~

Khai báo trên giúp Swagger UI hiển thị trường API key và gửi header X-API-Key. Backend vẫn cần filter, authentication provider hoặc cơ chế tương đương để đọc, xác minh key, kiểm tra trạng thái, thời hạn, phạm vi và quyền của key.

Không lưu API key dạng rõ trong mã nguồn hoặc log. Nên hỗ trợ cấp mới, thu hồi và xoay vòng key; giới hạn quyền theo từng key và truyền qua HTTPS. Tránh đặt key trong query string vì URL thường xuất hiện trong log, lịch sử trình duyệt và hệ thống giám sát.

## 10. Basic Authentication cũng cần cấu hình runtime

OpenAPI có thể mô tả HTTP Basic:

~~~java
@SecurityScheme(
    name = "basicAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "basic",
    description = "HTTP Basic Authentication"
)
@Configuration
class BasicAuthOpenApiConfiguration {
}
~~~

Operation dùng scheme:

~~~java
@Operation(
    summary = "Xem báo cáo quản trị",
    security = @SecurityRequirement(name = "basicAuth")
)
@GetMapping("/api/admin/report")
public ReportResponse getReport() {
    return reportService.getReport();
}
~~~

Để xác thực Basic ở runtime, Spring Security cần cấu hình httpBasic, UserDetailsService hoặc authentication provider phù hợp:

~~~java
@Bean
SecurityFilterChain basicSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Đoạn cấu hình này là ví dụ tối giản. Trong ứng dụng thực tế, cần cấu hình nguồn người dùng, mã hóa mật khẩu, phân quyền, HTTPS và chính sách bảo vệ brute force. Basic Authentication chỉ mã hóa credential bằng Base64 trong header, không phải mã hóa nội dung; tuyệt đối không dùng qua kết nối HTTP không bảo vệ.

## 11. OAuth2 và OpenID Connect

OpenAPI có thể mô tả OAuth2 flows hoặc OpenID Connect để client biết cách lấy và gửi token. Ví dụ, scheme OAuth2 có thể khai báo authorization code flow với authorization URL, token URL và scopes.

~~~yaml
components:
  securitySchemes:
    shopOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            orders.read: Đọc đơn hàng
            orders.write: Tạo hoặc cập nhật đơn hàng
~~~

Operation yêu cầu scope:

~~~yaml
security:
  - shopOAuth:
      - orders.read
~~~

Định nghĩa flow trong OpenAPI giúp công cụ biết endpoints và scopes. Nó không biến Spring Boot thành authorization server, không tự đăng ký client và không cấp token. Backend resource server vẫn cần xác minh access token theo issuer, chữ ký, thời hạn, audience và quy tắc quyền.

OpenID Connect là lớp định danh xây dựng trên OAuth2. Khi dùng openIdConnect, OpenAPI tham chiếu discovery URL; hệ thống xác thực và resource server vẫn phải được cấu hình độc lập.

## 12. Security scheme toàn cục và operation công khai

Nếu mọi endpoint đều yêu cầu bearer token, có thể khai báo security requirement ở cấp root. Nhưng nhiều API có cả endpoint công khai và endpoint được bảo vệ.

Ví dụ tài liệu:

~~~yaml
security:
  - bearerAuth: []

paths:
  /api/catalog:
    get:
      security: []
      summary: Danh sách công khai
      responses:
        '200':
          description: Thành công

  /api/me:
    get:
      summary: Hồ sơ hiện tại
      responses:
        '200':
          description: Thành công
~~~

/api/catalog công khai trong hợp đồng OpenAPI vì operation có security: []; /api/me kế thừa bearer requirement từ root.

Phải đồng bộ với backend. Nếu OpenAPI đánh dấu endpoint công khai nhưng SecurityFilterChain yêu cầu authentication, client sẽ gửi request mà không có token và nhận 401. Nếu tài liệu yêu cầu bearer nhưng backend cho phép anonymous, tài liệu sẽ gây khó hiểu cho client.

Một endpoint public trong tài liệu vẫn có thể có rate limit hoặc điều kiện truy cập khác; security requirement chỉ mô tả cơ chế authentication theo OpenAPI.

## 13. Bảo vệ Swagger UI và OpenAPI JSON

Đường dẫn Swagger UI và /v3/api-docs/** thường được mở công khai trong ví dụ phát triển để người dùng tra cứu. Trong môi trường nội bộ, tài liệu có thể tiết lộ:

- Tên endpoint và cấu trúc hệ thống.
- Schema request/response.
- Quy trình nghiệp vụ và mã lỗi.
- Header hoặc security scheme.
- Các endpoint quản trị hoặc tích hợp đối tác.

Hãy quyết định riêng:

1. Ai được mở giao diện Swagger UI?
2. Ai được tải JSON/YAML OpenAPI?
3. Ai được gọi API thực tế?
4. Swagger UI gọi API bằng credential nào?

Nếu bảo vệ /v3/api-docs/**, Swagger UI cũng phải có cách truy cập tài liệu. Nếu UI yêu cầu đăng nhập nhưng file spec bị chặn trước khi UI tải được, trang có thể không hiển thị operation. Có thể dùng cùng cơ chế đăng nhập, reverse proxy hoặc phân phối spec qua kênh nội bộ phù hợp.

Không công khai tài liệu chỉ vì đã tắt Try it out. supportedSubmitMethods chỉ giới hạn thao tác gửi request từ giao diện; nó không ẩn tài liệu hoặc bảo vệ endpoint.

## 14. 401 và 403 cần được xử lý đúng

Trong Spring Security:

- **401 Unauthorized:** người gọi chưa xác thực hoặc credential không hợp lệ.
- **403 Forbidden:** người gọi đã xác thực nhưng không đủ quyền.

Tên Unauthorized của status 401 dễ gây nhầm; về ngữ nghĩa, đây là lỗi authentication. 403 thường biểu thị authorization bị từ chối.

Có thể cấu hình handler để trả lỗi JSON nhất quán:

- AuthenticationEntryPoint xử lý lỗi xác thực.
- AccessDeniedHandler xử lý lỗi phân quyền.

Ví dụ minh họa:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint((request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(
            "{\"code\":\"UNAUTHENTICATED\",\"message\":\"Cần đăng nhập\"}"
        );
    })
    .accessDeniedHandler((request, response, exception) -> {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(
            "{\"code\":\"FORBIDDEN\",\"message\":\"Không đủ quyền truy cập\"}"
        );
    })
);
~~~

Đây là ví dụ ngắn để minh họa hai điểm xử lý; trong ứng dụng thực tế nên dùng ObjectMapper để serialize DTO lỗi, tránh ghép JSON bằng chuỗi và bổ sung header cần thiết theo cơ chế authentication.

OpenAPI nên mô tả response 401 và 403 cho operation được bảo vệ, kèm schema lỗi nếu backend trả body. Metadata response không tự cấu hình AuthenticationEntryPoint hoặc AccessDeniedHandler.

## 15. CSRF và CORS không được giải quyết bằng OpenAPI security

Hai cơ chế này thường bị nhầm với authentication:

- **CSRF** bảo vệ ứng dụng khỏi request giả mạo được gửi tự động kèm cookie/session của người dùng.
- **CORS** là chính sách trình duyệt kiểm soát việc JavaScript từ origin khác truy cập response.

Khai báo bearer scheme hoặc API key trong OpenAPI không tự cấu hình CSRF và CORS.

Nếu API dùng bearer token trong Authorization header và không dựa vào cookie xác thực tự động, nhóm có thể chọn mô hình stateless và cấu hình CSRF phù hợp. Nếu dùng session cookie, cần giữ cơ chế CSRF token đúng cách.

Nếu Swagger UI và API ở hai origin khác nhau, CORS cần cho phép origin, method và header cần thiết, ví dụ Authorization và Content-Type. CORS không chặn curl hoặc Postman và không thay thế authorization.

## 16. Kiểm tra OpenAPI JSON sau khi khai báo security

Sau khi ứng dụng chạy, tải tài liệu:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Xem security scheme:

~~~bash
jq '.components.securitySchemes' openapi.json
~~~

Xem security requirement toàn cục:

~~~bash
jq '.security' openapi.json
~~~

Xem security của operation:

~~~bash
jq '.paths["/api/me"].get.security' openapi.json
~~~

Xem security của endpoint công khai:

~~~bash
jq '.paths["/api/catalog"].get.security' openapi.json
~~~

Đối chiếu:

- Scheme có đúng type, scheme, in, name và URL cần thiết không?
- Tên trong security requirement có khớp khóa component không?
- Operation nào kế thừa security root?
- Operation công khai có thực sự bỏ security requirement không?
- OAuth2 scopes có đúng với scope mà backend kiểm tra không?
- Response 401/403 có được mô tả phù hợp không?

Một tài liệu hợp lệ về cấu trúc vẫn có thể mô tả sai chính sách bảo mật. Hãy so sánh với SecurityFilterChain và method security.

## 17. Kiểm tra backend bằng request thực tế

Không chỉ kiểm tra Swagger UI. Hãy gọi trực tiếp endpoint với các trạng thái credential khác nhau.

Ví dụ:

~~~bash
# Không gửi token
curl -i http://localhost:8080/api/orders

# Gửi token không hợp lệ
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer invalid-token"

# Gửi token hợp lệ
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer <access-token>"
~~~

Kết quả phụ thuộc cấu hình:

- Không token: thường 401 nếu endpoint yêu cầu xác thực.
- Token sai chữ ký, hết hạn hoặc issuer không hợp lệ: thường 401.
- Token hợp lệ nhưng thiếu scope: thường 403.
- Token hợp lệ và đủ quyền: request được xử lý theo nghiệp vụ.

Không dùng token thật trong source code, log hoặc ví dụ được commit. Dùng biến môi trường hoặc secret manager khi kiểm thử.

## 18. Viết test cho authentication và authorization

Có thể dùng MockMvc để kiểm tra status của endpoint được bảo vệ. Với resource server JWT, Spring Security Test hỗ trợ request post-processor jwt() để tạo Authentication giả lập trong test.

~~~java
@WebMvcTest(OrderController.class)
@Import(ApiSecurityConfiguration.class)
class OrderSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsAnonymousRequest() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectsTokenWithoutRequiredScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read")
                )))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowsTokenWithRequiredScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                )))
            .andExpect(status().isOk());
    }
}
~~~

Test cần có dependency spring-security-test, import các static helper và cấu hình mock service phù hợp. jwt() giả lập Authentication đã được tạo; nó không kiểm tra chữ ký JWT thật, issuer hoặc khóa ký. Muốn kiểm tra decoder và token validation, cần integration test riêng với decoder/test issuer hoặc môi trường identity provider phù hợp.

Nên có cả test OpenAPI để xác minh scheme và requirement, lẫn test runtime để xác minh filter chain thực sự từ chối request không hợp lệ.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI có nút Authorize nhưng endpoint vẫn nhận request không token | Chỉ khai báo OpenAPI scheme, chưa cấu hình SecurityFilterChain |
| Backend yêu cầu token nhưng Swagger UI không gửi Authorization | Operation thiếu security requirement hoặc tên scheme không khớp |
| Có @SecurityScheme nhưng operation không hiển thị khóa | Scheme được định nghĩa nhưng chưa gắn @SecurityRequirement hoặc security root |
| Token hợp lệ vẫn nhận 401 | Issuer, chữ ký, thời hạn, audience hoặc decoder cấu hình sai |
| Token hợp lệ nhận 403 | Thiếu scope/authority hoặc quy tắc authorization không khớp |
| API key xuất hiện trong Swagger UI nhưng không được kiểm tra | Chưa triển khai filter/provider xác minh API key |
| Endpoint public vẫn bị yêu cầu token trong tài liệu | Operation kế thừa security root nhưng chưa override bằng security: [] |
| Endpoint bảo vệ lại được mô tả công khai | Security requirement thiếu hoặc khai báo sai |
| Swagger UI không tải được OpenAPI JSON | Đường dẫn docs bị SecurityFilterChain chặn hoặc cấu hình proxy sai |
| Try it out bị lỗi CORS | Chưa cho phép origin/header/method cần thiết |
| Request cookie bị từ chối CSRF | Thiếu CSRF token hoặc cấu hình CSRF không khớp mô hình session |

## 20. Quy trình đồng bộ OpenAPI và Spring Security

Khi thêm hoặc thay đổi cơ chế xác thực, thực hiện theo trình tự:

1. Xác định loại credential: bearer JWT, opaque token, API key, Basic hay OAuth2/OIDC.
2. Cấu hình runtime bằng SecurityFilterChain, resource server hoặc authentication provider phù hợp.
3. Thiết lập authorization cho path, HTTP method, scope/role và method service.
4. Đăng ký security scheme bằng @SecurityScheme hoặc OpenAPI model.
5. Gắn security requirement ở root hoặc operation đúng phạm vi.
6. Khai báo endpoint công khai và response 401/403 đúng thực tế.
7. Quyết định chính sách truy cập Swagger UI và /v3/api-docs.
8. Kiểm tra JSON OpenAPI và request runtime.
9. Viết test anonymous, credential sai, thiếu quyền và đủ quyền.
10. Review lại CORS, CSRF và cấu hình triển khai.

Nếu thay đổi claim hoặc scope ở identity provider, cần cập nhật cả mapping authority, authorization rules và mô tả scope trong OpenAPI.

## 21. Checklist

- [ ] Đã phân biệt security scheme của OpenAPI với SecurityFilterChain runtime.
- [ ] @SecurityScheme khai báo đúng loại và tên scheme.
- [ ] @SecurityRequirement tham chiếu đúng khóa component.
- [ ] Security root và operation-level được áp dụng đúng.
- [ ] Endpoint public có security requirement phù hợp.
- [ ] JWT resource server xác minh issuer, chữ ký và thời hạn.
- [ ] Audience và claim tùy chỉnh được kiểm tra nếu API yêu cầu.
- [ ] Authorization kiểm tra đúng scope/role.
- [ ] API key hoặc Basic có authentication provider/filter thực tế.
- [ ] 401 và 403 được xử lý đúng.
- [ ] Swagger UI và OpenAPI JSON được bảo vệ theo chính sách.
- [ ] CSRF/CORS phù hợp với mô hình cookie hoặc bearer token.
- [ ] Đã kiểm tra request không token, token sai, thiếu quyền và đủ quyền.
- [ ] Đã kiểm tra security requirement trong /v3/api-docs.

## 22. Nguồn tra cứu

- [springdoc-openapi – tài liệu chính thức](https://springdoc.org/)
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/latest.html#security-requirement-object)
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)

@SecurityScheme và @SecurityRequirement giúp công bố cách client xác thực theo OpenAPI. SecurityFilterChain, resource server, authentication provider và authorization rules mới bảo vệ request thực tế. Hãy giữ hai lớp đồng bộ, kiểm tra /v3/api-docs và test các trường hợp không token, token sai, thiếu quyền và đủ quyền trước khi phát hành API.
