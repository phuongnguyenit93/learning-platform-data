# `@SecurityRequirement` và tên tham chiếu phải khớp scheme

OpenAPI mô tả bảo mật bằng hai phần liên kết với nhau: **security scheme** định nghĩa cơ chế xác thực, còn **security requirement** tham chiếu đến scheme đó để chỉ ra API hoặc operation nào yêu cầu cơ chế này. Trong Springdoc, `@SecurityScheme` dùng để khai báo scheme; `@SecurityRequirement` dùng tên scheme để gắn yêu cầu bảo mật.

Tên tham chiếu phải khớp chính xác với tên đã khai báo. Nếu scheme có tên `bearerAuth` nhưng operation tham chiếu `BearerAuth`, OpenAPI không có một scheme tương ứng với tên đó. Swagger UI có thể không hiển thị cơ chế Authorize như mong muốn và client generator có thể tạo cấu hình bảo mật sai.

## 1. Phân biệt security scheme và security requirement

Hai khái niệm này giải quyết hai câu hỏi khác nhau:

- **Security scheme:** API sử dụng loại xác thực nào và thông tin xác thực được truyền ở đâu? Ví dụ HTTP Bearer, API key trong header hoặc OAuth2.
- **Security requirement:** API hoặc operation nào yêu cầu scheme đã định nghĩa? Requirement tham chiếu scheme bằng tên.

Trong OpenAPI 3, scheme được đặt trong `components.securitySchemes`. Requirement ở cấp tài liệu hoặc operation tham chiếu key của scheme đó:

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

Trong ví dụ này, `bearerAuth` là tên scheme. Requirement cũng dùng chính xác `bearerAuth`; mảng rỗng biểu thị HTTP Bearer không có danh sách OAuth scope.

Chỉ khai báo `components.securitySchemes` chưa có nghĩa mọi operation đều bắt buộc xác thực. Scheme mới chỉ mô tả cơ chế. Cần thêm security requirement ở cấp tài liệu hoặc operation để gắn cơ chế đó vào API.

## 2. Khai báo HTTP Bearer scheme bằng `@SecurityScheme`

Với API dùng Bearer token, có thể khai báo scheme trong cấu hình OpenAPI:

```java
package com.example.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Books API",
        version = "1.0.0",
        description = "API quản lý và tra cứu sách"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Nhập access token do hệ thống cấp"
)
public class OpenApiSecurityConfig {}
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `name` | Tên key trong `components.securitySchemes` và tên được requirement tham chiếu |
| `type` | Loại scheme, ví dụ `HTTP`, `APIKEY`, `OAUTH2`, `OPENIDCONNECT` |
| `scheme` | Tên scheme HTTP, ví dụ `bearer` hoặc `basic` |
| `bearerFormat` | Gợi ý định dạng token, ví dụ `JWT`; đây là thông tin mô tả |
| `description` | Giải thích cách dùng scheme |

Ở đây, `name = "bearerAuth"` tạo tên tham chiếu. Tên này phân biệt chữ hoa/chữ thường và phải được giữ nguyên khi khai báo `@SecurityRequirement`.

`bearerFormat = "JWT"` chỉ mô tả định dạng token cho người đọc. Nó không bật xác minh chữ ký JWT, kiểm tra issuer/audience, thời hạn hoặc quyền truy cập trong Spring Security.

## 3. Gắn requirement ở cấp toàn bộ API

Nếu phần lớn endpoint đều yêu cầu Bearer token, có thể đặt security requirement trong `@OpenAPIDefinition`:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@OpenAPIDefinition(
    security = {
        @SecurityRequirement(name = "bearerAuth")
    }
)
```

Khi đó, OpenAPI mô tả yêu cầu bảo mật ở cấp gốc:

```yaml
security:
  - bearerAuth: []
```

Security requirement cấp tài liệu là mặc định cho các operation. Người đọc có thể hiểu rằng các operation kế thừa chính sách Bearer token, trừ operation có khai báo security riêng để thay thế hoặc loại bỏ yêu cầu đó.

Chỉ đặt bảo mật toàn cục nếu điều đó đúng với hợp đồng API. Nếu API có endpoint công khai như health check, đăng nhập hoặc lấy metadata không cần token, cần mô tả ngoại lệ rõ ràng ở operation tương ứng và kiểm tra đặc tả đầu ra.

## 4. Gắn requirement cho một operation bằng `@Operation`

Nếu chỉ một số endpoint yêu cầu xác thực, gắn requirement trực tiếp vào operation:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/api/account/profile")
    @Operation(
        summary = "Xem hồ sơ tài khoản",
        security = {
            @SecurityRequirement(name = "bearerAuth")
        }
    )
    public ProfileResponse profile() {
        return new ProfileResponse("user_demo_001");
    }
}

record ProfileResponse(String userId) {}
```

`@SecurityRequirement(name = "bearerAuth")` không tạo scheme mới. Nó tham chiếu scheme đã khai báo bằng `@SecurityScheme(name = "bearerAuth", ...)`.

Có thể gắn cùng một requirement cho nhiều operation. Nếu một controller có nhiều method cùng dùng cơ chế bảo mật, hãy cân nhắc cách khai báo ở phạm vi phù hợp và kiểm tra OpenAPI được sinh ra để tránh lặp hoặc tạo khác biệt không chủ ý.

## 5. Tên scheme phải khớp chính xác

Quy tắc quan trọng nhất là tên ở requirement phải bằng tên ở scheme:

| Khai báo scheme | Requirement hợp lệ | Requirement không khớp |
| --- | --- | --- |
| `name = "bearerAuth"` | `name = "bearerAuth"` | `name = "BearerAuth"` |
| `name = "apiKeyAuth"` | `name = "apiKeyAuth"` | `name = "api-key-auth"` |
| `name = "partnerOAuth"` | `name = "partnerOAuth"` | `name = "partnerOauth"` |

Ví dụ cấu hình đúng:

```java
@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key"
)
```

Requirement phải tham chiếu đúng `apiKeyAuth`:

```java
@Operation(
    security = @SecurityRequirement(name = "apiKeyAuth")
)
```

Các tên `apiKeyAuth`, `api-key-auth` và `ApiKeyAuth` là những chuỗi khác nhau. Nên đặt tên ngắn gọn theo quy ước thống nhất, ví dụ `bearerAuth`, `apiKeyAuth`, `oauth2`.

## 6. Scheme API key và requirement tương ứng

API key có thể được truyền qua header, query hoặc cookie. Ví dụ khai báo API key trong header:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "apiKeyAuth",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-API-Key",
    description = "API key do quản trị viên cấp cho ứng dụng"
)
```

Gắn requirement:

```java
@Operation(
    summary = "Lấy báo cáo đối tác",
    security = @SecurityRequirement(name = "apiKeyAuth")
)
```

OpenAPI tương ứng:

```yaml
components:
  securitySchemes:
    apiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
paths:
  /api/partner/report:
    get:
      security:
        - apiKeyAuth: []
```

Không khai báo API key bằng một parameter header thông thường nếu mục đích thực sự là xác thực. Security scheme giúp Swagger UI, client generator và công cụ OpenAPI hiểu đây là thông tin xác thực.

## 7. OAuth2 requirement và scopes

Với OAuth2, requirement tham chiếu tên scheme và liệt kê các scope cần thiết cho operation. Ví dụ scheme dùng authorization code flow:

```java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.Scopes;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth/authorize",
            tokenUrl = "https://auth.example.com/oauth/token",
            scopes = @Scopes({
                @OAuthScope(name = "books:read", description = "Đọc sách"),
                @OAuthScope(name = "books:write", description = "Tạo và cập nhật sách")
            })
        )
    )
)
```

Operation yêu cầu scope đọc:

```java
@Operation(
    summary = "Liệt kê sách",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"books:read"}
    )
)
```

Operation ghi dữ liệu có thể yêu cầu scope khác:

```java
@Operation(
    summary = "Tạo sách",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"books:write"}
    )
)
```

Tên `oauth2` trong hai requirement phải khớp `@SecurityScheme(name = "oauth2", ...)`. Các scope trong requirement phải được định nghĩa trong flow tương ứng của scheme. Việc khai báo scope trong OpenAPI không tự cấp quyền; authorization server và resource server vẫn phải kiểm tra token và scope lúc chạy.

## 8. Hiểu quy tắc OR và AND của security requirement

Trong OpenAPI, trường `security` là một mảng các Security Requirement Object. Cách nhóm các scheme có ý nghĩa logic:

- Nhiều object trong mảng `security` là các lựa chọn **OR**: client có thể đáp ứng một trong các lựa chọn.
- Nhiều scheme trong cùng một object là điều kiện **AND**: client phải đáp ứng tất cả scheme được liệt kê trong object đó.

Ví dụ hai cách xác thực thay thế nhau (Bearer **hoặc** API key):

```yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
```

Ví dụ cần đồng thời Bearer và API key:

```yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
```

Ví dụ kết hợp: chấp nhận (Bearer **và** API key) **hoặc** OAuth2 với scope `books:read`:

```yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
  - oauth2:
      - books:read
```

Đừng nhầm việc lặp nhiều annotation `@SecurityRequirement` với cách nhóm AND. Các requirement độc lập thường được biểu diễn thành những lựa chọn riêng. Nếu cần một tổ hợp AND phức tạp, hãy kiểm tra cấu trúc OpenAPI cuối cùng và cân nhắc tùy biến model bằng `OpenApiCustomizer` để tạo một Security Requirement Object chứa nhiều scheme key trong cùng một object.

## 9. Security toàn cục và security theo operation

OpenAPI cho phép đặt `security` ở cấp root hoặc cấp operation:

| Vị trí | Phạm vi | Cách dùng |
| --- | --- | --- |
| `@OpenAPIDefinition(security = ...)` | Mặc định cho toàn tài liệu | Khi phần lớn hoặc tất cả operation yêu cầu cùng cơ chế |
| `@Operation(security = ...)` | Một operation | Khi operation có cơ chế riêng hoặc scope riêng |
| `security: []` ở operation | Operation công khai, không yêu cầu security scheme kế thừa | Khi cần loại bỏ security toàn cục cho endpoint công khai |

Ví dụ tài liệu mặc định dùng Bearer nhưng endpoint health check công khai:

```yaml
security:
  - bearerAuth: []
paths:
  /actuator/health:
    get:
      security: []
      responses:
        '200':
          description: Trạng thái ứng dụng
```

Trong OpenAPI, security ở operation thay thế yêu cầu cấp root cho operation đó. Nếu operation có `security: []`, nó không kế thừa security requirement toàn cục.

Khi cấu hình bằng annotation, hãy xác minh Springdoc thực sự sinh `security: []` cho operation công khai trong phiên bản đang dùng. Nếu annotation mặc định không tạo ra mảng rỗng như mong muốn, có thể dùng `OpenApiCustomizer` hoặc cơ chế tùy biến tương ứng để đặt security rỗng rõ ràng. Không để endpoint công khai vô tình kế thừa requirement toàn cục trong tài liệu.

## 10. Ví dụ hoàn chỉnh: scheme và operation cùng tham chiếu một tên

Một cấu hình đơn giản cho Books API:

```java
package com.example.books.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Books API", version = "1.0.0"),
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfig {}
```

Controller:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookController {

    @GetMapping("/api/books")
    @Operation(
        summary = "Liệt kê sách",
        security = @SecurityRequirement(name = "bearerAuth")
    )
    public List<BookResponse> list() {
        return List.of(new BookResponse(1L, "Spring Boot căn bản"));
    }
}

record BookResponse(Long id, String title) {}
```

Trong ví dụ, cả security ở cấp tài liệu và operation cùng tham chiếu `bearerAuth`. Security khai báo ở operation thay thế security cấp tài liệu cho operation đó, không cộng dồn với nó. Vì vậy, có thể bỏ requirement ở operation nếu muốn kế thừa security toàn cục; giữ khai báo tường minh chỉ hữu ích khi operation cần cơ chế hoặc scope riêng hay muốn thể hiện rõ chính sách ngay tại method.

## 11. Swagger UI sử dụng scheme như thế nào?

Khi OpenAPI có `components.securitySchemes` và requirement tham chiếu đúng tên, Swagger UI có thể hiển thị nút **Authorize** và biểu mẫu nhập thông tin xác thực.

Với HTTP Bearer:

1. Mở Swagger UI.
2. Chọn **Authorize**.
3. Chọn scheme `bearerAuth`.
4. Nhập access token do môi trường thử nghiệm cấp.
5. Xác nhận và gửi request đến operation có requirement.

Với API key, giao diện sẽ yêu cầu giá trị cho scheme `apiKeyAuth`; Swagger UI gắn giá trị vào vị trí đã khai báo, ví dụ header `X-API-Key`. Với OAuth2, UI có thể khởi động quy trình cấp quyền tùy flow và cấu hình client.

Không đưa token thật vào mã nguồn, annotation, `@ExampleObject` hoặc tài liệu. Hãy nhập credential thử nghiệm qua giao diện Authorize hoặc dùng cơ chế bí mật phù hợp của môi trường.

Nút Authorize chỉ hỗ trợ người dùng cung cấp thông tin xác thực để thử API. Nó không tự bảo vệ endpoint và không thay thế cấu hình Spring Security, resource server hoặc gateway.

## 12. Mỗi tài liệu group phải có scheme được tham chiếu

Nếu Springdoc tạo nhiều tài liệu qua `GroupedOpenApi`, mỗi tài liệu OpenAPI được kiểm tra độc lập. Requirement trong một group phải tham chiếu scheme có mặt trong `components.securitySchemes` của chính tài liệu group đó.

Ví dụ, tài liệu `partner` chứa:

```yaml
components:
  securitySchemes:
    partnerApiKey:
      type: apiKey
      in: header
      name: X-Partner-Key
security:
  - partnerApiKey: []
```

Nếu group `public` không khai báo scheme `partnerApiKey` nhưng operation trong group vẫn tham chiếu tên đó, tài liệu public có thể chứa requirement không hợp lệ hoặc không hoàn chỉnh. Khi tạo group, kiểm tra cả scheme definitions lẫn requirements, không chỉ kiểm tra paths.

Nếu mỗi group có cơ chế xác thực khác nhau, hãy thiết kế tên scheme và phạm vi requirement rõ ràng. Tránh dùng chung một tên cho hai cơ chế khác nhau giữa các tài liệu nếu điều đó khiến client hiểu sai cách gửi credential.

## 13. Kiểm tra OpenAPI sau khi khai báo bảo mật

Sau khi chạy ứng dụng, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml`. Với mỗi scheme, xác nhận:

1. Scheme xuất hiện trong `components.securitySchemes`.
2. Key scheme đúng chính tả và đúng chữ hoa/chữ thường.
3. `type`, `scheme`, `in`, `name`, OAuth flow và scopes phù hợp với cơ chế thực tế.
4. Mỗi `security` requirement tham chiếu đến key đã khai báo.
5. Scope trong requirement tồn tại trong OAuth2/OpenID scheme tương ứng.
6. Operation công khai có security rỗng nếu nó cần loại bỏ security toàn cục.
7. Từng tài liệu group có đủ scheme definitions mà requirements của nó tham chiếu.

Ví dụ một đoạn OpenAPI hợp lệ:

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
paths:
  /api/books:
    get:
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Danh sách sách
```

Nếu Swagger UI không hiển thị Authorize, kiểm tra tài liệu JSON trước. Nếu scheme có nhưng operation không yêu cầu nó, kiểm tra `security` ở cấp root và operation. Nếu Authorize xuất hiện nhưng request không gửi credential, kiểm tra requirement, cấu hình scheme, trạng thái authorize và request thực tế trong Network.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Swagger UI không có nút Authorize | Chưa khai báo scheme hoặc tài liệu không chứa `components.securitySchemes` | Khai báo `@SecurityScheme` và kiểm tra OpenAPI |
| Có scheme nhưng operation không hiện yêu cầu bảo mật | Chưa gắn `@SecurityRequirement` ở root hoặc operation | Thêm requirement tham chiếu đúng tên |
| Requirement không tìm thấy scheme | Tên trong `@SecurityRequirement` khác tên `@SecurityScheme` | Đồng bộ chính xác chuỗi `name` |
| Chỉ khác chữ hoa/chữ thường nhưng vẫn lỗi | Tên scheme được tham chiếu như key phân biệt chữ hoa/chữ thường | Dùng một hằng quy ước và sao chép cùng tên |
| Authorize xuất hiện nhưng header không đúng | Scheme khai báo sai type, scheme, `in` hoặc `paramName` | Đối chiếu cấu hình với cơ chế xác thực runtime |
| OAuth2 báo scope không hợp lệ | Scope requirement chưa được khai báo trong flow | Đồng bộ scope ở `@OAuthScope` và `@SecurityRequirement` |
| Endpoint public vẫn hiển thị yêu cầu Bearer | Operation kế thừa security cấp root | Đảm bảo operation có `security: []` trong OpenAPI |
| Scheme có trong tài liệu mặc định nhưng thiếu ở group | Group document không chứa scheme definition tương ứng | Bổ sung scheme vào từng tài liệu hoặc cấu hình dùng chung phù hợp |
| Nhầm requirement là cơ chế xác thực thực tế | Chỉ mô tả OpenAPI mà chưa cấu hình Spring Security | Triển khai xác thực/phân quyền ở runtime |

## 15. Checklist bảo đảm requirement khớp scheme

- [ ] Đã khai báo scheme bằng `@SecurityScheme` hoặc cấu hình OpenAPI tương ứng.
- [ ] `name` của scheme có quy ước ổn định, ví dụ `bearerAuth`.
- [ ] Mọi `@SecurityRequirement(name = ...)` dùng đúng tên đã khai báo.
- [ ] Không nhầm tên scheme với tên header như `Authorization` hoặc `X-API-Key`.
- [ ] Scheme HTTP Bearer có `type = HTTP` và `scheme = "bearer"`.
- [ ] Scheme API key khai báo đúng `in` và `paramName`.
- [ ] OAuth2 requirement dùng đúng scheme name và scopes đã định nghĩa.
- [ ] Đã quyết định security ở cấp toàn tài liệu hay từng operation.
- [ ] Endpoint công khai có `security: []` nếu cần bỏ requirement toàn cục.
- [ ] Các requirement OR/AND được nhóm đúng trong OpenAPI.
- [ ] Mỗi tài liệu group có đầy đủ scheme mà requirement tham chiếu.
- [ ] Đã kiểm tra `/v3/api-docs`, Swagger UI Authorize và request thực tế.
- [ ] Spring Security hoặc resource server thực thi xác thực và phân quyền độc lập với metadata OpenAPI.

`@SecurityScheme` định nghĩa cơ chế bảo mật; `@SecurityRequirement` tham chiếu cơ chế đó bằng tên. Hai tên phải khớp chính xác trong cùng tài liệu OpenAPI. Khi scheme, requirement, scope và phạm vi áp dụng được khai báo nhất quán, Swagger UI có thể hướng dẫn người tích hợp xác thực đúng cách và client generator có thể tạo cấu hình bảo mật phù hợp với hợp đồng API.
