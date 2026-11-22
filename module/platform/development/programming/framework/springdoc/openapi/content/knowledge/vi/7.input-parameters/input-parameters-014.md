# Vì sao Authorization không nên chỉ được khai báo như header parameter thông thường

Header `Authorization` mang thông tin xác thực mà client gửi để chứng minh danh tính hoặc quyền truy cập. Khi mô tả API bằng OpenAPI, header này cần được biểu diễn bằng cơ chế bảo mật (`security scheme` và `security requirement`), không nên chỉ khai báo như một header parameter thông thường.

Lý do nằm ngay trong quy tắc của OpenAPI Specification: các header parameter có tên `Accept`, `Content-Type` và `Authorization` bị bỏ qua. Ba header này có ý nghĩa chuẩn ở cấp giao thức và được mô tả qua những cấu trúc chuyên biệt của OpenAPI. `Accept` và `Content-Type` được thể hiện thông qua media type trong `content`; thông tin xác thực được mô tả bằng `components.securitySchemes` và `security`.

Với Spring Boot, `springdoc-openapi` có thể đọc các annotation bảo mật để tạo những cấu trúc đó. Swagger UI dùng chúng để hiển thị nút **Authorize** và gửi thông tin xác thực khi thử request. Spring Security hoặc cơ chế xác thực của ứng dụng vẫn chịu trách nhiệm kiểm tra token và quyết định quyền truy cập.

## 1. Vì sao `Authorization` khác một header thông thường?

Một header như `X-Request-Id`, `X-Tenant-Id` hoặc `If-Match` có thể là một phần của hợp đồng request. Có thể mô tả chúng bằng `@Parameter` hoặc `@RequestHeader` để client biết tên, kiểu dữ liệu, ý nghĩa và yêu cầu của header.

`Authorization` có vai trò khác: nó truyền credentials theo cơ chế xác thực HTTP. Ví dụ:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
Accept: application/json
```

Trong request trên:

- `Authorization` mang Bearer access token.
- `Accept` cho biết client muốn nhận representation nào.
- `GET /api/orders/42` xác định operation được gọi.

OpenAPI dành cấu trúc riêng để mô tả ba header có ý nghĩa đặc biệt này. Theo quy tắc của Parameter Object, header parameter có tên `Accept`, `Content-Type` hoặc `Authorization` bị bỏ qua. Vì vậy, khai báo `@Parameter(name = "Authorization", in = HEADER, ...)` không phải cách đúng để mô tả xác thực và có thể không xuất hiện như mong đợi trong tài liệu được tiêu thụ bởi validator hoặc client generator.

| Header | Cách mô tả trong OpenAPI |
|---|---|
| `Authorization` | `components.securitySchemes` và `security` |
| `Accept` | Media type trong `responses.content` |
| `Content-Type` | Media type trong `requestBody.content` |
| `X-Request-Id` | Header parameter thông thường |
| `X-Tenant-Id` | Header parameter thông thường, nếu nó thực sự là dữ liệu request chứ không phải credentials |

Không nên đặt token thật trong ví dụ `@Parameter`, `@ExampleObject` hoặc mô tả API. Token là bí mật và không phải dữ liệu mẫu cố định của hợp đồng.

## 2. Khai báo HTTP Bearer authentication

Nếu API nhận access token dạng Bearer trong header `Authorization`, khai báo một HTTP security scheme với `scheme: bearer`.

Đặc tả OpenAPI tương ứng:

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
  /api/orders/{id}:
    get:
      summary: Lấy đơn hàng theo mã
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: integer
            format: int64
      responses:
        '200':
          description: Tìm thấy đơn hàng
```

Các phần có ý nghĩa:

- `components.securitySchemes.bearerAuth` định nghĩa cơ chế xác thực có tên `bearerAuth`.
- `type: http` nói rằng đây là HTTP authentication scheme.
- `scheme: bearer` chỉ định cơ chế Bearer.
- `bearerFormat: JWT` là gợi ý về định dạng token để người đọc hiểu; nó không làm validator kiểm tra chữ ký JWT và cũng không bắt buộc token phải là JWT.
- `security` ở cấp tài liệu áp dụng yêu cầu bảo mật cho các operation, trừ operation có quy định riêng.
- `bearerAuth: []` không khai báo OAuth2 scope; với HTTP Bearer, mảng scope để trống.

Khi dùng Bearer authentication, client gửi header theo dạng `Authorization: Bearer <token>`. Swagger UI có thể tạo header này từ security scheme sau khi người dùng nhập token ở nút **Authorize**.

## 3. Cấu hình Bearer scheme bằng Swagger annotations

Với Springdoc, có thể khai báo security scheme bằng `@SecurityScheme`. Ví dụ:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Nhập access token để xác thực request"
)
class OpenApiSecurityConfiguration {
}
```

Annotation trên tạo phần định nghĩa trong `components.securitySchemes`. Nó chỉ mô tả cách client gửi credentials.

Để yêu cầu token cho các operation của controller, gắn `@SecurityRequirement`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
class OrderController {

    @GetMapping("/{id}")
    @Operation(summary = "Lấy đơn hàng theo mã")
    OrderResponse getById(@PathVariable Long id) {
        return orderService.getById(id);
    }
}
```

Ở ví dụ này, `@SecurityRequirement` gắn yêu cầu `bearerAuth` lên các operation của controller. Có thể đặt annotation ở method khi chỉ một số operation cần xác thực. Tên trong `@SecurityRequirement(name = "bearerAuth")` phải khớp chính xác với `name` của security scheme.

Nếu muốn khai báo yêu cầu bảo mật toàn tài liệu, có thể đặt security requirement trong `@OpenAPIDefinition` hoặc dùng bean/customizer OpenAPI. Khi đã áp dụng security ở cấp tài liệu, hãy kiểm tra những operation công khai có cần ghi đè yêu cầu đó hay không.

## 4. Phân biệt Security Scheme và Security Requirement

Hai thành phần này có vai trò khác nhau:

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| Security Scheme | Ứng dụng hỗ trợ cơ chế xác thực nào và client gửi credentials ra sao? | HTTP Bearer, HTTP Basic, OAuth2, API key |
| Security Requirement | Operation hoặc toàn tài liệu yêu cầu dùng scheme nào? | `security: - bearerAuth: []` |

Chỉ khai báo `components.securitySchemes` chưa có nghĩa mọi endpoint đều bắt buộc xác thực. Scheme chỉ là định nghĩa có thể tham chiếu. Muốn áp dụng, phải thêm `security` ở cấp tài liệu hoặc operation.

Ví dụ chỉ định security cho một operation:

```yaml
paths:
  /api/profile:
    get:
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Hồ sơ người dùng
```

Ví dụ khai báo security ở cấp tài liệu:

```yaml
security:
  - bearerAuth: []
```

Khi security được khai báo ở cấp tài liệu, nó là mặc định cho các operation. Một operation có trường `security` riêng sẽ ghi đè yêu cầu bảo mật cấp tài liệu cho operation đó.

## 5. Mô tả endpoint công khai khi tài liệu có security toàn cục

Một dịch vụ thường có cả endpoint công khai và endpoint yêu cầu đăng nhập. Ví dụ `/api/catalog` có thể công khai, còn `/api/orders` yêu cầu Bearer token.

Trong OpenAPI, nếu tài liệu có security toàn cục nhưng một operation không cần xác thực, operation đó phải khai báo `security: []` để xóa yêu cầu kế thừa:

```yaml
security:
  - bearerAuth: []
paths:
  /api/catalog:
    get:
      summary: Xem danh mục công khai
      security: []
      responses:
        '200':
          description: Danh sách danh mục
  /api/orders:
    get:
      summary: Xem đơn hàng của người dùng hiện tại
      responses:
        '200':
          description: Danh sách đơn hàng
```

`security: []` có nghĩa operation không yêu cầu security scheme nào theo hợp đồng OpenAPI. Nó không tự cấu hình Spring Security cho phép truy cập ẩn danh. Nếu runtime vẫn yêu cầu đăng nhập, Swagger UI có thể gọi operation công khai theo tài liệu nhưng nhận `401` hoặc `403`.

Ngược lại, nếu tài liệu không có security requirement nhưng runtime bắt buộc token, người dùng Swagger UI có thể không thấy yêu cầu **Authorize** và request thử sẽ thất bại. Tài liệu và chính sách bảo mật runtime cần được đồng bộ.

## 6. Các loại security scheme phổ biến

OpenAPI hỗ trợ nhiều kiểu xác thực. Cần chọn loại phản ánh cách server thực sự kiểm tra credentials.

| Cơ chế | Khai báo OpenAPI | Cách gửi credentials thường gặp |
|---|---|---|
| HTTP Bearer | `type: http`, `scheme: bearer` | `Authorization: Bearer <token>` |
| HTTP Basic | `type: http`, `scheme: basic` | `Authorization: Basic <credentials>` |
| API key trong header | `type: apiKey`, `in: header`, `name: X-API-Key` | `X-API-Key: <key>` |
| API key trong cookie | `type: apiKey`, `in: cookie`, `name: SESSION` | Cookie có tên được khai báo |
| OAuth2 | `type: oauth2`, khai báo flow và scopes | Access token theo OAuth2 flow; thường được gửi dưới dạng Bearer |
| OpenID Connect | `type: openIdConnect`, khai báo discovery URL | Xác thực dựa trên OpenID Connect |

### HTTP Basic

```yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
security:
  - basicAuth: []
```

Basic authentication gửi thông tin username/password được mã hóa Base64 trong header Authorization. Base64 không phải mã hóa bảo mật; chỉ sử dụng qua TLS và theo chính sách xác thực của hệ thống.

### API key trong custom header

```yaml
components:
  securitySchemes:
    apiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
security:
  - apiKeyAuth: []
```

`X-API-Key` là header tùy chỉnh nên có thể được mô tả bằng API key security scheme. Nếu một API cũ sử dụng header `Authorization` với một quy ước riêng, cần mô hình hóa đúng HTTP authentication scheme nếu phù hợp và kiểm tra khả năng hỗ trợ của các công cụ. Không chuyển nó thành header parameter thông thường.

### Khai báo API key bằng annotation

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "API key do hệ thống cấp"
)
class ApiKeySecurityConfiguration {
}
```

Khi áp dụng scheme này, tham chiếu bằng `@SecurityRequirement(name = "apiKeyAuth")` hoặc khai báo trong `security` của tài liệu.

## 7. OAuth2 và scopes

OAuth2 khác với HTTP Bearer scheme ở mức mô tả. Bearer scheme cho biết client gửi token trong Authorization header. OAuth2 mô tả thêm flow mà client dùng để lấy access token và scopes mà token có thể được cấp.

Ví dụ OpenAPI:

```yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            orders:read: Đọc đơn hàng
            orders:write: Tạo hoặc cập nhật đơn hàng
paths:
  /api/orders:
    get:
      security:
        - oauth2:
            - orders:read
      responses:
        '200':
          description: Danh sách đơn hàng
```

Trong `security`, danh sách scope chỉ có ý nghĩa với OAuth2 hoặc OpenID Connect. Với HTTP Bearer, Basic và API key, giá trị scope thường là mảng rỗng.

Khi dùng OAuth2, cần khai báo flow đúng với loại client và quy trình identity provider đang vận hành. Không dùng URL ví dụ làm endpoint thật; lấy authorization URL, token URL và scopes từ cấu hình identity provider của hệ thống. Swagger UI có thể hỗ trợ khởi tạo OAuth2 flow, nhưng việc đăng ký client, redirect URI, PKCE và chính sách token vẫn phải được cấu hình phù hợp ở identity provider.

## 8. Logic OR và AND trong Security Requirement

OpenAPI cho phép một operation chấp nhận nhiều phương thức xác thực.

Các object trong mảng `security` biểu thị các phương án thay thế (OR). Các scheme cùng nằm trong một Security Requirement Object phải được đáp ứng đồng thời (AND).

Ví dụ chấp nhận Bearer token hoặc API key:

```yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
```

Client chỉ cần thỏa mãn một trong hai phương án.

Ví dụ yêu cầu cả Bearer token và tenant API key:

```yaml
security:
  - bearerAuth: []
    tenantKey: []
```

Client phải gửi cả hai credentials. Cần xác nhận server thật sự thực thi cùng logic AND/OR này; mô tả OpenAPI không tự thay đổi filter hoặc authorization rule trong Spring Security.

## 9. Vì sao không dùng `@RequestHeader` hoặc `@Parameter` cho Authorization?

Spring MVC có thể nhận header bằng `@RequestHeader`:

```java
@GetMapping("/profile")
ProfileResponse getProfile(
    @RequestHeader("X-Request-Id") String requestId
) {
    return profileService.getProfile(requestId);
}
```

Đây là cách phù hợp cho header nghiệp vụ hoặc metadata của request như correlation ID. Với `Authorization`, Spring Security thường đọc và xác thực credentials thông qua security filter chain trước khi request đến controller. Controller không cần khai báo token thành tham số chỉ để Springdoc đưa nó vào tài liệu.

Ví dụ không nên dùng:

```java
// Không dùng cách này để mô tả xác thực trong OpenAPI.
@GetMapping("/profile")
ProfileResponse getProfile(
    @RequestHeader("Authorization") String authorization
) {
    // ...
}
```

Việc khai báo như trên có thể tạo cảm giác rằng controller trực tiếp chịu trách nhiệm xác thực, trong khi token thường được xử lý ở filter chain. Quan trọng hơn, OpenAPI bỏ qua header parameter có tên Authorization. Hãy định nghĩa security scheme và gắn security requirement.

Nếu ứng dụng thực sự cần đọc header `Authorization` thủ công cho một giao thức đặc biệt, cần tách biệt quyết định xử lý runtime với cách mô tả hợp đồng. Không nên dựa vào header parameter thông thường để thay thế security scheme.

## 10. Spring Security mới thực thi xác thực và phân quyền

Khai báo `@SecurityScheme` hoặc `@SecurityRequirement` chỉ tạo mô tả OpenAPI. Chúng không:

- Kiểm tra chữ ký JWT hoặc thời hạn token.
- Xác minh issuer, audience hoặc quyền trong claim.
- Tạo `Authentication` trong `SecurityContext`.
- Chặn request chưa đăng nhập hoặc trả `401`/`403`.
- Cấp token hoặc refresh token.

Với Spring Security Resource Server, cấu hình runtime có thể sử dụng JWT như sau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/catalog/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Ví dụ trên chỉ minh họa cách bảo vệ API ở runtime; ứng dụng còn cần dependency Resource Server và cấu hình issuer/JWK hoặc decoder phù hợp. Nếu tài liệu Swagger UI/API Docs được bảo vệ, cần quyết định rõ matcher nào được phép truy cập và matcher nào yêu cầu xác thực. Khi tùy biến đường dẫn API Docs hoặc Swagger UI, cập nhật các matcher tương ứng.

Một endpoint được đánh dấu `security: []` trong tài liệu vẫn có thể bị Spring Security chặn. Ngược lại, endpoint được đánh dấu yêu cầu Bearer trong tài liệu vẫn có thể đang mở công khai nếu runtime chưa được cấu hình đúng. Kiểm thử cả hai lớp là bắt buộc.

## 11. Swagger UI sử dụng security scheme như thế nào?

Khi tài liệu có `components.securitySchemes` và operation có `security`, Swagger UI có thể:

1. Hiển thị nút **Authorize** với tên scheme.
2. Cho phép người dùng nhập token hoặc credentials phù hợp với scheme.
3. Gắn header Authorization, API key header hoặc thông tin xác thực tương ứng vào request **Try it out**.
4. Hiển thị trạng thái đã/đang áp dụng credentials trong phiên giao diện.

Với HTTP Bearer, người dùng thường nhập access token vào hộp Authorize. Swagger UI tự thêm tiền tố `Bearer` theo scheme. Cần đọc hướng dẫn của phiên bản Swagger UI được đóng gói nếu cách nhập token hoặc OAuth2 flow có khác biệt.

Không bật lưu trữ credentials lâu dài trong trình duyệt dùng chung hoặc môi trường công khai nếu không có lý do và biện pháp phù hợp. Không đưa token vào query string, ví dụ tài liệu, log hoặc ảnh chụp màn hình. Khi thử API, dùng token có quyền tối thiểu và môi trường phù hợp.

## 12. CORS khi Swagger UI gọi API có xác thực

Nếu Swagger UI và API nằm ở hai origin khác nhau, trình duyệt áp dụng chính sách CORS. Header `Authorization` thường khiến request cần preflight `OPTIONS`. Server phải cho phép origin, method và header cần thiết.

Ví dụ cấu hình CORS minh họa:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(List.of("https://docs.example.com"));
    configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    configuration.setAllowedHeaders(List.of("Authorization", "Content-Type", "X-Request-Id"));

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", configuration);
    return source;
}
```

Đây là ví dụ cho một origin được xác định trước. Không nên mở wildcard origin tùy tiện khi dùng credentials. CORS chỉ kiểm soát quyền truy cập cross-origin của trình duyệt; nó không xác minh token và không thay thế authorization.

## 13. Kiểm tra tài liệu được Springdoc sinh ra

Sau khi cấu hình, mở endpoint API Docs, thường là `/v3/api-docs`, và kiểm tra các trường:

```json
{
  "components": {
    "securitySchemes": {
      "bearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT"
      }
    }
  },
  "security": [
    {
      "bearerAuth": []
    }
  ]
}
```

Kiểm tra operation cụ thể có yêu cầu scheme phù hợp, operation công khai có `security: []` nếu cần, và không xuất hiện `Authorization` như một parameter thông thường. Có thể dùng công cụ validator OpenAPI để phát hiện cấu trúc sai hoặc tham chiếu security scheme không tồn tại.

Kiểm tra hành vi runtime bằng các request độc lập:

```bash
# Không gửi token: endpoint được bảo vệ phải từ chối theo chính sách.
curl -i http://localhost:8080/api/orders/42

# Gửi token hợp lệ trong môi trường kiểm thử.
curl -i -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/orders/42
```

Thay `<ACCESS_TOKEN>` bằng token kiểm thử được cấp cho môi trường tương ứng. Không ghi token thật vào source code hoặc tài liệu lưu trữ.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Authorization` không xuất hiện trong danh sách Parameters | OpenAPI bỏ qua header parameter tên Authorization | Dùng `securitySchemes` và `security` |
| Không thấy nút Authorize trong Swagger UI | Chưa khai báo scheme hoặc operation chưa tham chiếu scheme | Kiểm tra `components.securitySchemes` và `security` |
| Có scheme nhưng operation không hiển thị yêu cầu bảo mật | Chưa gắn Security Requirement | Khai báo security ở cấp tài liệu, controller hoặc operation |
| Swagger UI gửi request nhưng nhận `401` | Token thiếu, sai định dạng, hết hạn hoặc không hợp lệ | Kiểm tra header, token, issuer, audience và decoder |
| Nhận `403` dù token hợp lệ | Người dùng thiếu authority/scope cần thiết | Kiểm tra authorization rule và mapping scope thành authority |
| Endpoint công khai vẫn hiện khóa bảo mật | Operation kế thừa security toàn cục | Khai báo `security: []` cho operation công khai |
| Tài liệu nói cần Bearer nhưng API cho phép anonymous | Runtime Spring Security chưa yêu cầu xác thực | Kiểm tra SecurityFilterChain và test anonymous request |
| Request từ Swagger UI bị CORS error | Origin hoặc header Authorization chưa được cho phép | Kiểm tra preflight OPTIONS và CORS configuration |
| API key không được gửi đúng header | Khai báo sai `in` hoặc `name` trong API key scheme | Đối chiếu `in: header` và tên header thực tế |

## 15. Checklist mô tả Authorization đúng cách

- [ ] Xác định cơ chế thật: Bearer, Basic, API key, OAuth2 hay OpenID Connect.
- [ ] Khai báo security scheme trong `components.securitySchemes` hoặc bằng `@SecurityScheme`.
- [ ] Gắn security requirement ở cấp tài liệu, controller hoặc operation theo chính sách.
- [ ] Không khai báo `Authorization` bằng `@Parameter` hoặc `@RequestHeader` chỉ để mô tả credentials.
- [ ] Dùng `security: []` cho operation công khai nếu tài liệu có security toàn cục.
- [ ] Chỉ khai báo OAuth2 scopes khi scheme là OAuth2/OpenID Connect và scope có ý nghĩa thực tế.
- [ ] Kiểm tra Swagger UI hiển thị Authorize và gửi đúng credentials khi Try it out.
- [ ] Kiểm tra Spring Security thực sự từ chối request thiếu hoặc sai credentials.
- [ ] Kiểm tra CORS nếu giao diện và API khác origin.
- [ ] Không đưa token, API key hoặc mật khẩu thật vào tài liệu, ví dụ hay log.

`Authorization` là một phần của cơ chế bảo mật HTTP, vì vậy OpenAPI mô tả nó bằng security scheme và security requirement. Cách này giúp Swagger UI và công cụ sinh client hiểu cách gửi credentials, đồng thời giữ rõ ranh giới giữa hợp đồng API và cơ chế bảo vệ thực tế. Spring Security vẫn phải xác thực token và phân quyền cho từng request; tài liệu chỉ có giá trị khi nó phản ánh đúng chính sách đó.
