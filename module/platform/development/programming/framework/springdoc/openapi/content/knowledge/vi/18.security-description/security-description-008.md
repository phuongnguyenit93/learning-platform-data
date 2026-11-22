# Yêu cầu bảo mật ở cấp tài liệu và cấp operation

OpenAPI mô tả cơ chế xác thực mà client cần dùng để gọi API thông qua hai phần riêng: `components.securitySchemes` định nghĩa các cơ chế bảo mật, còn `security` chỉ ra operation nào yêu cầu cơ chế nào. Hai phần này thường đi cùng nhau nhưng có trách nhiệm khác nhau. Chỉ định nghĩa Bearer token hoặc API key chưa có nghĩa mọi endpoint đều yêu cầu credentials; tài liệu phải gắn security requirement ở cấp tài liệu hoặc operation.

OpenAPI cho phép đặt `security` ở cấp root của document để áp dụng mặc định cho các operation. Một operation có thể ghi đè yêu cầu chung, ví dụ endpoint đăng nhập hoặc health check không cần xác thực. Khi dùng Springdoc, có thể khai báo bằng `@OpenAPIDefinition`, `@SecurityScheme`, `@SecurityRequirement`, `@Operation` và `@SecurityRequirements`, hoặc cấu hình trực tiếp OpenAPI model bằng bean.

Điều quan trọng là security trong OpenAPI chỉ mô tả hợp đồng cho Swagger UI, client generator và người tích hợp. Nó không tự cấu hình Spring Security, không phát hành token và không chặn request ở runtime.

## 1. Phân biệt Security Scheme và Security Requirement

`Security Scheme` mô tả cách client cung cấp thông tin xác thực. Ví dụ:

- HTTP Bearer token trong header `Authorization`.
- HTTP Basic authentication.
- API key trong header, query parameter hoặc cookie.
- OAuth 2.0 với các flow và scope.
- OpenID Connect.

`Security Requirement` tham chiếu đến một scheme đã được định nghĩa và chỉ ra scheme đó cần được dùng cho operation. Trong OpenAPI, scheme được lưu dưới `components.securitySchemes`, còn requirement nằm trong `security` ở cấp document hoặc operation.

Ví dụ rút gọn:

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

security:
  - bearerAuth: []
```

Trong ví dụ này:

- `bearerAuth` là tên scheme.
- `type: http` và `scheme: bearer` mô tả HTTP Bearer authentication.
- `bearerFormat: JWT` là thông tin gợi ý cho người đọc, không phải quy tắc xác minh token.
- `security` ở root yêu cầu các operation dùng Bearer token theo mặc định.
- Mảng scope rỗng `[]` là đúng với HTTP Bearer; scope chỉ có ý nghĩa với OAuth 2.0 hoặc OpenID Connect.

Tên `bearerAuth` trong requirement phải khớp chính xác key đã khai báo trong `components.securitySchemes`. Tên này phân biệt chữ hoa và chữ thường.

## 2. Security ở cấp document

Khi phần lớn endpoint cần cùng một cơ chế xác thực, khai báo `security` ở root để tránh lặp lại trên từng operation.

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: 1.0.0
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
paths:
  /api/orders:
    get:
      summary: Liệt kê đơn hàng
      responses:
        '200':
          description: Danh sách đơn hàng
  /api/orders/{id}:
    get:
      summary: Xem đơn hàng
      responses:
        '200':
          description: Chi tiết đơn hàng
```

`security` ở root là mặc định cho các operation trong document. Khi operation không khai báo thuộc tính `security` riêng, nó kế thừa yêu cầu ở cấp document.

Với cấu hình trên, Swagger UI biết rằng các operation cần Bearer token và hiển thị nút **Authorize**. Sau khi người dùng nhập token, UI gửi request có header `Authorization: Bearer ...` đến server đã chọn.

Không nên hiểu root `security` là luật bảo vệ runtime. Một người gọi API bằng cURL hoặc client riêng vẫn có thể gửi request mà không mở Swagger UI. Spring Security phải tự xác thực và từ chối request không hợp lệ.

## 3. Security ở cấp operation ghi đè mặc định

Một operation có thể cần cơ chế bảo mật khác với yêu cầu chung. Khi operation khai báo `security`, danh sách đó thay thế security requirement ở cấp document cho operation đó.

Ví dụ document mặc định yêu cầu Bearer token, nhưng endpoint đăng nhập công khai:

```yaml
security:
  - bearerAuth: []
paths:
  /api/auth/login:
    post:
      summary: Đăng nhập
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/LoginRequest'
      responses:
        '200':
          description: Đăng nhập thành công
  /api/orders:
    get:
      summary: Liệt kê đơn hàng
      responses:
        '200':
          description: Danh sách đơn hàng
```

Ở đây:

- `POST /api/auth/login` có `security: []`, nghĩa là operation không yêu cầu security scheme nào.
- `GET /api/orders` không khai báo security riêng, nên tiếp tục kế thừa `bearerAuth` từ root.

`security: []` là mảng rỗng. Nó khác với việc bỏ hẳn thuộc tính `security` khỏi operation. Bỏ thuộc tính nghĩa là kế thừa root; mảng rỗng nghĩa là không áp dụng security requirement nào cho operation đó.

### Endpoint cho phép cả anonymous và authenticated request

Nếu muốn một operation chấp nhận cả người dùng chưa đăng nhập lẫn người dùng đã có Bearer token, có thể khai báo một lựa chọn anonymous:

```yaml
security:
  - {}
  - bearerAuth: []
```

Object rỗng `{}` biểu thị lựa chọn không cần xác thực. Object còn lại biểu thị lựa chọn dùng Bearer token. Hai lựa chọn là các phương án thay thế nhau.

Đây là trường hợp khác với `security: []`: mảng rỗng loại bỏ toàn bộ yêu cầu bảo mật, còn mảng có `{}` mô tả rõ một phương án anonymous trong tập lựa chọn bảo mật. Chỉ dùng cấu trúc này khi server thực sự chấp nhận cả hai kiểu request.

## 4. Quy tắc OR và AND trong Security Requirement

Đây là phần dễ gây nhầm lẫn nhất khi một operation hỗ trợ nhiều cơ chế xác thực.

- Nhiều object trong mảng `security` biểu thị **OR**: client có thể thỏa mãn một trong các object.
- Nhiều scheme key bên trong cùng một object biểu thị **AND**: client phải thỏa mãn tất cả scheme trong object đó.

### OR: Bearer token hoặc API key

```yaml
security:
  - bearerAuth: []
  - tenantApiKey: []
```

Client có thể dùng Bearer token hoặc API key. Không bắt buộc gửi cả hai.

### AND: Bearer token và API key cùng lúc

```yaml
security:
  - bearerAuth: []
    tenantApiKey: []
```

Client phải gửi cả Bearer token lẫn tenant API key để thỏa mãn requirement này.

### Hai phương án, trong đó một phương án cần hai scheme

```yaml
security:
  - bearerAuth: []
    tenantApiKey: []
  - partnerOAuth:
      - orders:read
```

Client có thể chọn một trong hai cách:

1. Gửi cả Bearer token và tenant API key.
2. Dùng OAuth2 token có scope `orders:read`.

Không đưa các scheme thành nhiều object nếu muốn bắt buộc gửi đồng thời. Cấu trúc YAML quyết định phép OR/AND, không phải thứ tự các scheme.

## 5. Định nghĩa các loại Security Scheme thường gặp

### HTTP Bearer

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

Request thường có dạng:

```http
Authorization: Bearer eyJhbGciOi...
```

### HTTP Basic

```yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
```

Client gửi thông tin user/password qua HTTP Authorization Basic. Chỉ dùng Basic qua TLS/HTTPS; không đưa mật khẩu thật vào ví dụ tài liệu.

### API key trong header

```yaml
components:
  securitySchemes:
    tenantApiKey:
      type: apiKey
      in: header
      name: X-Tenant-Key
```

Client gửi:

```http
X-Tenant-Key: <TENANT_API_KEY>
```

### API key trong query hoặc cookie

OpenAPI cũng hỗ trợ `in: query` và `in: cookie`:

```yaml
components:
  securitySchemes:
    queryApiKey:
      type: apiKey
      in: query
      name: api_key
    sessionCookie:
      type: apiKey
      in: cookie
      name: SESSION
```

API key trong query dễ bị lưu trong access log, browser history, proxy log hoặc referrer. Chỉ chọn vị trí này nếu hệ thống có lý do tương thích rõ ràng và đã đánh giá rủi ro lộ key. Cookie authentication còn phụ thuộc chính sách cookie của trình duyệt và CSRF protection.

## 6. OAuth 2.0 và scopes

Với OAuth 2.0, Security Scheme khai báo flow và scope được cấp bởi authorization server. Security Requirement của operation liệt kê các scope cần có.

Ví dụ authorization code flow:

```yaml
components:
  securitySchemes:
    partnerOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            orders:read: Đọc thông tin đơn hàng
            orders:write: Tạo và cập nhật đơn hàng
security:
  - partnerOAuth:
      - orders:read
```

Trong ví dụ này, operation yêu cầu token OAuth2 có scope `orders:read`. Nếu cần cả hai scope, liệt kê cả hai:

```yaml
security:
  - partnerOAuth:
      - orders:read
      - orders:write
```

Các scope trong cùng requirement là tập scope cần có. Scope phải được định nghĩa trong flow của scheme tương ứng và phải khớp tên. Với scheme HTTP hoặc API key, danh sách scope phải để rỗng.

OpenID Connect dùng `type: openIdConnect` cùng `openIdConnectUrl`. Security Requirement có thể liệt kê scope được provider công bố. Cần phân biệt scope trong OpenAPI với role/authority nội bộ của Spring Security: chúng có thể được ánh xạ với nhau, nhưng không tự động đồng nghĩa.

## 7. Khai báo Security Scheme và requirement bằng Springdoc annotations

Springdoc sử dụng Swagger annotations để chuyển metadata bảo mật sang OpenAPI.

Ví dụ khai báo Bearer scheme và yêu cầu bảo mật mặc định ở cấp document:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0",
        description = "API quản lý đơn hàng"
    ),
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
```

Kết quả mong đợi:

- `components.securitySchemes.bearerAuth` định nghĩa Bearer scheme.
- `security` ở root có requirement `bearerAuth`.
- Các operation không khai báo security riêng kế thừa requirement root.

Có thể khai báo scheme bằng một bean `OpenAPI` thay cho `@SecurityScheme`, đặc biệt khi cần tạo cấu hình động từ properties:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiBeanConfiguration {

    @Bean
    OpenAPI customOpenAPI() {
        return new OpenAPI()
            .info(new Info().title("Order API").version("1.0.0"))
            .components(new Components().addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            ))
            .addSecurityItem(new SecurityRequirement().addList("bearerAuth"));
    }
}
```

Không cần định nghĩa cùng một scheme bằng cả annotation và bean nếu không có chủ đích. Tránh tạo hai nguồn cấu hình cùng tên nhưng khác loại hoặc khác tham số.

### Khai báo OAuth2 scheme bằng annotation

Với OAuth2, `@SecurityScheme` có thể mô tả flow và scope tương ứng:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "partnerOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(name = "orders:read", description = "Đọc đơn hàng"),
                @OAuthScope(name = "orders:write", description = "Tạo và cập nhật đơn hàng")
            }
        )
    )
)
class OAuthSchemeConfiguration {
}
```

Sau đó operation có thể tham chiếu scope bằng `@SecurityRequirement(name = "partnerOAuth", scopes = {"orders:read"})`. URL authorization/token phải là endpoint thật của identity provider; ví dụ trên chỉ minh họa cấu trúc.

## 8. Yêu cầu bảo mật riêng cho một operation

Nếu một operation cần OAuth2 scope cụ thể, khai báo security tại method:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
@Operation(
    summary = "Đọc danh sách đơn hàng",
    security = {
        @SecurityRequirement(
            name = "partnerOAuth",
            scopes = {"orders:read"}
        )
    }
)
List<OrderResponse> listOrders() {
    return orderService.findAll();
}
```

Yêu cầu ở operation thay thế requirement ở root cho operation này. Trong ví dụ, operation dùng `partnerOAuth` với scope `orders:read`, không đồng thời kế thừa `bearerAuth` từ root.

Có thể đặt `@SecurityRequirement` trực tiếp trên method thay cho thuộc tính `security` của `@Operation`. Đặt ở cấp controller áp dụng yêu cầu cho các operation của controller theo cơ chế annotation processing; đặt trong `@OpenAPIDefinition.security` là mức document.

Khi khai báo nhiều `@SecurityRequirement` lặp lại, chúng biểu thị các phương án thay thế (OR). Để bắt buộc nhiều scheme cùng lúc (AND), OpenAPI Security Requirement Object cần chứa nhiều scheme trong cùng một object. Swagger annotations mới có thuộc tính `combine`/`SecurityRequirementEntry` cho trường hợp kết hợp; nếu dùng phiên bản annotations cũ hoặc muốn biểu diễn rõ ràng, hãy tùy biến OpenAPI model và kiểm tra output.

## 9. Vô hiệu hóa security kế thừa cho operation công khai

Đây là trường hợp quan trọng khi document có root `security`, nhưng một số endpoint như login, đăng ký hoặc health check không cần token.

Trong OpenAPI, cách biểu diễn chuẩn là:

```yaml
paths:
  /api/health:
    get:
      security: []
      responses:
        '200':
          description: Trạng thái dịch vụ
```

Với Swagger annotations, dùng `@SecurityRequirements` rỗng trên method để biểu thị operation không có requirement và ghi đè yêu cầu ở cấp cao hơn:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/health")
@Operation(summary = "Kiểm tra trạng thái dịch vụ")
@SecurityRequirements
HealthResponse health() {
    return healthService.currentStatus();
}
```

Không dựa vào `@Operation(security = {})` để xóa security toàn cục. Một mảng annotation rỗng có thể được hiểu là không khai báo override và không sinh trường `security` ở operation. `@SecurityRequirements` rỗng được dùng để tạo override rỗng; hãy kiểm tra JSON OpenAPI được sinh ra và xác nhận operation có `security: []`.

Nếu phiên bản Swagger Core/Springdoc đang dùng chưa xử lý annotation rỗng như mong đợi, có thể dùng `OperationCustomizer` để đặt danh sách security rỗng cho operation được chọn:

```java
import java.util.ArrayList;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OperationCustomizer publicHealthSecurityOverride() {
    return (operation, handlerMethod) -> {
        if (handlerMethod.getMethod().getName().equals("health")) {
            operation.setSecurity(new ArrayList<>());
        }
        return operation;
    };
}
```

Trong ứng dụng thực tế, nên đánh dấu operation bằng annotation riêng hoặc kiểm tra path/method thay vì phụ thuộc tên method. Nếu chỉ muốn áp dụng trong một `GroupedOpenApi`, đăng ký customizer trên builder của group tương ứng. Sau khi tùy biến, xác nhận operation có `security: []` trong document đích.

## 10. Security requirement không thay thế Spring Security

OpenAPI mô tả client phải gửi credentials như thế nào. Spring Security quyết định server có chấp nhận request hay không. Hai cấu hình cần thống nhất nhưng độc lập.

Ví dụ cấu hình runtime:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/health", "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**").hasAuthority("SCOPE_orders:read")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Đây là ví dụ minh họa cho ứng dụng Resource Server dùng JWT; cấu hình decoder, issuer và authority mapping phải được thiết lập phù hợp với identity provider thực tế. `hasAuthority("SCOPE_orders:read")` là một quy tắc Spring Security, còn `scopes: [orders:read]` trong OpenAPI là metadata cho client. Cần bảo đảm hai bên cùng phản ánh chính sách được triển khai.

Nếu OpenAPI đánh dấu endpoint cần Bearer token nhưng Spring Security cho phép anonymous, tài liệu và runtime không nhất quán. Nếu OpenAPI đánh dấu endpoint công khai nhưng Spring Security vẫn yêu cầu đăng nhập, Swagger UI sẽ gửi request không có token và nhận 401/403. Hãy kiểm thử cả document lẫn request thực tế.

## 11. Áp dụng security cho từng GroupedOpenApi

Mỗi group tạo một OpenAPI document riêng. Nếu mọi group đều cần scheme dùng chung, có thể định nghĩa scheme trong OpenAPI bean hoặc dùng cơ chế cấu hình chung tương thích với phiên bản Springdoc. Nếu chỉ một group cần security requirement riêng, gắn customizer vào group đó.

Ví dụ chỉ group admin yêu cầu Bearer token ở cấp document:

```java
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;

@Bean
GroupedOpenApi adminApi() {
    return GroupedOpenApi.builder()
        .group("admin")
        .pathsToMatch("/api/admin/**")
        .addOpenApiCustomizer(openApi -> {
            if (openApi.getComponents() == null) {
                openApi.setComponents(new io.swagger.v3.oas.models.Components());
            }
            openApi.getComponents().addSecuritySchemes(
                "bearerAuth",
                new SecurityScheme()
                    .type(SecurityScheme.Type.HTTP)
                    .scheme("bearer")
                    .bearerFormat("JWT")
            );
            openApi.addSecurityItem(
                new SecurityRequirement().addList("bearerAuth")
            );
        })
        .build();
}
```

Nếu customizer thêm requirement nhưng quên định nghĩa scheme trong chính document đó, requirement sẽ tham chiếu tên không tồn tại. Nếu scheme đã được thêm từ cấu hình dùng chung, không cần thêm trùng lặp; hãy kiểm tra document group cuối cùng.

Đối với operation công khai nằm trong group admin, có thể dùng `@SecurityRequirements` rỗng hoặc operation customizer để ghi đè root requirement. Group không phải ranh giới bảo mật runtime: Spring Security vẫn phải bảo vệ từng route theo chính sách.

## 12. Kiểm tra Security trong tài liệu OpenAPI

Sau khi ứng dụng chạy, kiểm tra document mặc định:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '{schemes: .components.securitySchemes, security: .security}'
```

Kiểm tra requirement của một operation:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders"].get.security'
```

Kiểm tra operation công khai có override rỗng:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/health"].get | has("security"), .security'
```

Kết quả mong đợi là `true` và `[]`. Nếu trường `security` không tồn tại, operation có thể đang kế thừa requirement root.

Kiểm tra group cụ thể bằng URL `/v3/api-docs/{group}`. Không suy luận rằng scheme/requirement ở document mặc định chắc chắn có mặt trong mọi group; hãy kiểm tra từng tài liệu mà Swagger UI công bố.

## 13. Kiểm thử hợp đồng và runtime

Nên có kiểm thử cho cả hai lớp:

1. OpenAPI document có đúng security scheme và requirement.
2. Spring Security thực thi đúng chính sách khi request không token, token hợp lệ hoặc token thiếu scope.

Ví dụ integration test kiểm tra metadata OpenAPI:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpenApiSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void orderOperationRequiresBearerScheme() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.components.securitySchemes.bearerAuth.scheme")
                .value("bearer"))
            .andExpect(jsonPath("$.paths['/api/orders'].get.security[0].bearerAuth")
                .isArray());
    }

    @Test
    void healthOperationExplicitlyDisablesInheritedSecurity() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/health'].get.security").isArray())
            .andExpect(jsonPath("$.paths['/api/health'].get.security.length()")
                .value(0));
    }
}
```

Đối với runtime, dùng test riêng để xác nhận `/api/orders` trả 401 khi không có token, trả kết quả mong đợi khi token hợp lệ và từ chối token thiếu scope. Endpoint `/api/health` chỉ trả công khai nếu Spring Security cũng cấu hình `permitAll()`.

Khi test JSONPath, cú pháp có thể cần điều chỉnh theo phiên bản thư viện test. Điều quan trọng là kiểm tra trường `security` tồn tại và mảng có đúng phần tử hoặc rỗng; kiểm tra chỉ `securitySchemes` là chưa đủ.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Swagger UI không hiển thị Authorize | Chỉ định nghĩa scheme nhưng không có security requirement, hoặc document UI tải không đúng | Kiểm tra `components.securitySchemes` và `security` của document/operation |
| Requirement tham chiếu scheme không tồn tại | Tên key khác nhau hoặc group thiếu scheme | Đồng bộ tên và thêm scheme vào đúng document |
| Endpoint public vẫn hiển thị yêu cầu Bearer | Operation không có `security: []` override | Dùng `@SecurityRequirements` rỗng và xác minh output |
| `@Operation(security = {})` không xóa security root | Annotation array rỗng không được xử lý thành override | Dùng `@SecurityRequirements` hoặc customizer đặt security list rỗng |
| Client phải gửi cả Bearer và API key dù chỉ cần một | Hai scheme nằm trong cùng một Security Requirement Object | Tách thành hai object riêng để biểu diễn OR |
| Client chỉ gửi một scheme nhưng server yêu cầu cả hai | Hai scheme được khai báo thành các object riêng | Đặt cả hai key trong cùng object để biểu diễn AND |
| OAuth2 token bị từ chối dù có token | Thiếu scope, scope sai tên hoặc runtime mapping khác | Đối chiếu scopes trong OpenAPI với authority/claim của server |
| OpenAPI yêu cầu token nhưng server cho anonymous | Thiếu authorization rule trong Spring Security | Bảo vệ endpoint ở runtime và thêm integration test |
| Group admin thiếu security | Customizer chỉ sửa document mặc định hoặc thiếu scheme trong group | Dùng customizer đúng group và kiểm tra URL group |
| API key xuất hiện thành query parameter không mong muốn | Scheme khai báo `in: query` thay vì `header` | Chọn đúng vị trí scheme theo hợp đồng runtime |

## 15. Checklist thiết kế security ở hai cấp

- [ ] Mỗi security scheme có tên duy nhất trong `components.securitySchemes`.
- [ ] Scheme mô tả đúng loại xác thực và vị trí credentials.
- [ ] Security requirement chỉ tham chiếu scheme đã định nghĩa.
- [ ] Root `security` thể hiện đúng yêu cầu mặc định của document.
- [ ] Operation cần xác thực khác có requirement override phù hợp.
- [ ] Operation công khai có `security: []` nếu cần xóa yêu cầu kế thừa.
- [ ] Endpoint chấp nhận anonymous hoặc authenticated được mô tả bằng `{}` và scheme như các phương án OR khi phù hợp.
- [ ] Đã phân biệt OR giữa các object và AND giữa các scheme trong cùng object.
- [ ] OAuth2/OIDC scope được khai báo và dùng đúng tên.
- [ ] Không mô tả Authorization như header parameter thông thường.
- [ ] Mỗi GroupedOpenApi có scheme và requirement đúng trong document của nó.
- [ ] Spring Security runtime thực thi cùng chính sách với OpenAPI.
- [ ] Đã kiểm tra `/v3/api-docs` và từng `/v3/api-docs/{group}`.
- [ ] Đã kiểm thử request anonymous, authenticated và thiếu quyền.

`components.securitySchemes` định nghĩa cách client xác thực; `security` gắn cơ chế đó vào toàn document hoặc từng operation. Root requirement được kế thừa khi operation không khai báo override; `security: []` chủ động bỏ yêu cầu cho operation công khai. Mảng nhiều requirement object biểu thị OR, còn nhiều scheme trong cùng object biểu thị AND. Khi tài liệu Springdoc và Spring Security runtime cùng phản ánh một chính sách, Swagger UI, client generator và người tích hợp sẽ hiểu chính xác endpoint nào cần credentials và cần loại credentials nào.

## Tài liệu tham khảo

- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/v3.1.1.html#security-scheme-object)
- [OpenAPI Specification – Security Requirement Object](https://spec.openapis.org/oas/v3.1.1.html#security-requirement-object)
- [Springdoc OpenAPI v2 – FAQ: Security schemes](https://springdoc.org/v2/faq.html)
- [Swagger Core – `@SecurityRequirement` Javadoc](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html)
- [Swagger Core – `@SecurityRequirements` Javadoc](https://docs.swagger.io/swagger-core/v2.2.27/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirements.html)
