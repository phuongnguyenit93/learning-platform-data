# Security Scheme Object và Security Requirement Object

Một tài liệu OpenAPI cần mô tả hai điều khác nhau về bảo mật: API hỗ trợ cơ chế xác thực nào và operation nào yêu cầu cơ chế đó. OpenAPI biểu diễn phần định nghĩa cơ chế bằng **Security Scheme Object** trong `components.securitySchemes`; phần áp dụng cho toàn API hoặc từng operation được biểu diễn bằng **Security Requirement Object** trong thuộc tính `security`.

springdoc-openapi có thể tạo các cấu trúc này từ annotation của swagger-annotations hoặc từ `OpenAPI` bean. Khi thiết kế, hãy giữ tên scheme nhất quán giữa phần định nghĩa và phần yêu cầu, mô tả đúng cách client gửi thông tin xác thực và kiểm tra đặc tả được sinh. Các object này mô tả hợp đồng cho công cụ và người tích hợp; chúng không tự cấu hình bộ lọc xác thực của Spring Security.

## 1. Hai object có vai trò khác nhau

**Security Scheme Object** mô tả cách client cung cấp thông tin xác thực. Ví dụ: gửi bearer token trong header `Authorization`, gửi API key trong header `X-API-Key`, dùng OAuth 2.0 hoặc OpenID Connect.

**Security Requirement Object** tham chiếu một hay nhiều scheme đã định nghĩa để cho biết operation cần cơ chế nào. Nó không định nghĩa lại cách xác thực và cũng không chứa token thật.

| Thành phần | Vị trí trong OpenAPI | Câu hỏi được trả lời |
| --- | --- | --- |
| Security Scheme Object | `components.securitySchemes` | API hỗ trợ cơ chế xác thực nào và client gửi thông tin xác thực ở đâu? |
| Security Requirement Object | `security` ở cấp OpenAPI hoặc Operation | API hoặc operation yêu cầu scheme nào? |

Ví dụ ngắn:

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

Phần `components.securitySchemes` định nghĩa scheme có tên `bearerAuth`. Phần `security` yêu cầu client dùng scheme đó cho các operation kế thừa cấu hình toàn cục. Tên `bearerAuth` trong requirement phải khớp chính xác tên được khai báo trong components.

## 2. Các loại Security Scheme Object

OpenAPI 3.1.2 định nghĩa năm loại scheme chính:

| `type` | Mục đích | Các trường quan trọng |
| --- | --- | --- |
| `apiKey` | API key được gửi qua header, query hoặc cookie | `name`, `in` |
| `http` | HTTP Authentication như Basic hoặc Bearer | `scheme`, có thể có `bearerFormat` |
| `oauth2` | Xác thực/ủy quyền qua OAuth 2.0 | `flows` |
| `openIdConnect` | Đăng nhập dựa trên OpenID Connect | `openIdConnectUrl` |
| `mutualTLS` | Xác thực client bằng chứng thư TLS | `description` tùy chọn |

`mutualTLS` được hỗ trợ trong OpenAPI 3.1. Nếu tài liệu hoặc toolchain vẫn dùng OpenAPI 3.0.x, cần kiểm tra khả năng tương thích trước khi dùng loại scheme này. Không giả định mọi validator và code generator xử lý mọi scheme giống nhau.

## 3. API key qua header, query hoặc cookie

Với `apiKey`, OpenAPI yêu cầu hai thuộc tính:

- `name`: tên header, query parameter hoặc cookie parameter mà client phải gửi.
- `in`: vị trí của key, nhận một trong các giá trị `header`, `query` hoặc `cookie`.

Ví dụ API yêu cầu header `X-API-Key`:

~~~yaml
components:
  securitySchemes:
    partnerApiKey:
      type: apiKey
      in: header
      name: X-API-Key
      description: API key do cổng đối tác cấp.

security:
  - partnerApiKey: []
~~~

Request tương ứng có header:

~~~http
GET /api/partner/orders HTTP/1.1
Host: api.example.com
X-API-Key: <partner-api-key>
~~~

Không ghi API key thật vào OpenAPI, ví dụ hoặc source code. Giá trị trong request chỉ là chỗ giữ chỗ để người dùng Swagger UI nhập key qua nút Authorize.

API key có thể nằm trong query:

~~~yaml
components:
  securitySchemes:
    queryApiKey:
      type: apiKey
      in: query
      name: api_key
~~~

Request sẽ có dạng `GET /api/orders?api_key=...`. Cách này thường kém an toàn hơn header vì URL có thể xuất hiện trong access log, lịch sử trình duyệt, hệ thống phân tích và các log trung gian. Chỉ dùng khi hợp đồng hoặc nền tảng bắt buộc; ưu tiên HTTPS và tránh ghi giá trị key vào log.

API key cũng có thể truyền qua cookie:

~~~yaml
components:
  securitySchemes:
    sessionKey:
      type: apiKey
      in: cookie
      name: SESSION_KEY
~~~

Với cookie, cần xem xét thêm thuộc tính `Secure`, `HttpOnly`, `SameSite`, domain, path và chính sách gửi cookie của trình duyệt. OpenAPI chỉ mô tả tên và vị trí cookie; nó không cấu hình các thuộc tính cookie của máy chủ.

## 4. HTTP Basic và Bearer authentication

Với HTTP authentication, dùng `type: http` và chỉ rõ `scheme`.

Basic authentication:

~~~yaml
components:
  securitySchemes:
    basicAuth:
      type: http
      scheme: basic
      description: HTTP Basic authentication.

security:
  - basicAuth: []
~~~

Client gửi thông tin đăng nhập trong header:

~~~http
Authorization: Basic <base64-credentials>
~~~

Base64 chỉ là cách mã hóa biểu diễn, không phải mã hóa bảo mật. Basic authentication phải được dùng qua HTTPS để tránh lộ thông tin đăng nhập khi truyền trên mạng. Không đưa username hoặc password thật vào đặc tả.

Với bearer token:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: Gửi access token trong Authorization header.

security:
  - bearerAuth: []
~~~

Client gửi:

~~~http
Authorization: Bearer <access-token>
~~~

`bearerFormat: JWT` chỉ là gợi ý để người đọc biết token thường có định dạng JWT. Nó không bắt buộc token phải là JWT, không xác minh chữ ký, issuer, audience, expiration hay claim, và không cấu hình JWT decoder cho ứng dụng. Các kiểm tra đó phải được thực hiện ở hệ thống xác thực runtime.

Không khai báo bearer token bằng `type: apiKey` với `name: Authorization` nếu thực tế API dùng HTTP Bearer. Dùng `type: http`, `scheme: bearer` giúp Swagger UI và các công cụ hiểu đúng cơ chế chuẩn.

## 5. OAuth 2.0 và OAuth Flows Object

Với `type: oauth2`, Security Scheme Object phải có `flows`. Mỗi flow mô tả cách client lấy token và các scope mà API hỗ trợ. OpenAPI 3.1.2 định nghĩa bốn flow:

| Flow | Trường URL chính | Tình huống |
| --- | --- | --- |
| `authorizationCode` | `authorizationUrl`, `tokenUrl` | Ứng dụng chuyển người dùng đến authorization server, nhận authorization code rồi đổi lấy token |
| `clientCredentials` | `tokenUrl` | Dịch vụ backend xác thực với tư cách client |
| `password` | `tokenUrl` | Flow cũ dùng username/password của người dùng trực tiếp; không nên chọn cho thiết kế mới |
| `implicit` | `authorizationUrl` | Flow cũ trả token trực tiếp qua authorization response; không khuyến nghị cho thiết kế mới |

Ví dụ authorization code:

~~~yaml
components:
  securitySchemes:
    ordersOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          refreshUrl: https://identity.example.com/oauth2/refresh
          scopes:
            orders:read: Đọc đơn hàng
            orders:write: Tạo và cập nhật đơn hàng
            profile:read: Đọc thông tin hồ sơ cơ bản
~~~

`authorizationUrl` là nơi client bắt đầu luồng cấp quyền; `tokenUrl` là nơi đổi code lấy token; `refreshUrl` là URL tùy chọn để lấy token mới. URL của OAuth endpoint phải dùng HTTPS. Danh sách `scopes` ánh xạ tên scope với mô tả ngắn để client biết quyền có thể yêu cầu.

Với ứng dụng người dùng chạy trên trình duyệt hoặc thiết bị di động, Authorization Code Flow kết hợp PKCE thường là lựa chọn nên ưu tiên. OpenAPI mô tả các endpoint và scope; việc bật PKCE, client registration, redirect URI và chính sách cấp token phải được cấu hình tại authorization server và Swagger UI/client tương ứng.

Ví dụ client credentials cho giao tiếp service-to-service:

~~~yaml
components:
  securitySchemes:
    serviceOAuth:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            inventory:read: Đọc dữ liệu tồn kho
            inventory:write: Cập nhật dữ liệu tồn kho
~~~

Không dùng `password` hoặc `implicit` cho hệ thống mới nếu không có ràng buộc tương thích đặc biệt. OAuth 2.0 Security Best Current Practice khuyến nghị loại bỏ các flow này trong thiết kế mới; Authorization Code với PKCE phù hợp hơn cho ứng dụng có người dùng.

## 6. OpenID Connect

OpenID Connect xây dựng trên OAuth 2.0 và bổ sung lớp nhận diện người dùng. Trong OpenAPI, khai báo scheme bằng `type: openIdConnect` và `openIdConnectUrl` trỏ đến endpoint discovery của nhà cung cấp:

~~~yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://identity.example.com/.well-known/openid-configuration
      description: Đăng nhập qua nhà cung cấp OpenID Connect.

security:
  - oidc: []
~~~

URL trên là địa chỉ metadata discovery theo cấu hình của identity provider. Tài liệu discovery cung cấp thông tin như issuer, authorization endpoint, token endpoint và các endpoint liên quan. Hãy dùng URL discovery thực tế của nhà cung cấp, không tự đoán đường dẫn nếu issuer có cấu trúc riêng.

Với `openIdConnect` và `oauth2`, Security Requirement Object có thể liệt kê các scope cần thiết. Nếu không yêu cầu scope cụ thể, danh sách scope có thể rỗng.

## 7. Mutual TLS

Mutual TLS (mTLS) xác thực cả máy chủ và client trong quá trình bắt tay TLS. Client cung cấp chứng thư số; máy chủ kiểm tra chứng thư theo trust store và chính sách của mình.

OpenAPI 3.1 biểu diễn scheme này bằng:

~~~yaml
components:
  securitySchemes:
    clientCertificate:
      type: mutualTLS
      description: Client phải trình chứng thư do CA của đối tác tin cậy cấp.

security:
  - clientCertificate: []
~~~

Không có trường `name` hoặc `in` cho mTLS. Việc chọn chứng thư, kiểm tra chuỗi tin cậy, thu hồi chứng thư và ánh xạ danh tính client là cấu hình TLS/runtime ở gateway hoặc máy chủ. Swagger UI không thể tự tạo hay thay thế chứng thư client chỉ từ định nghĩa scheme.

## 8. Định nghĩa Security Scheme bằng annotation springdoc

springdoc hỗ trợ annotation `@SecurityScheme` để đưa scheme vào `components.securitySchemes`. Ví dụ cấu hình bearer JWT:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT",
    description = "Access token gửi trong Authorization header."
)
public class OpenApiSecurityConfiguration {
}
~~~

Tên `bearerAuth` là định danh trong OpenAPI. Có thể dùng tên khác, nhưng phần Security Requirement phải tham chiếu đúng tên đó.

Có thể khai báo API key bằng annotation:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@SecurityScheme(
    name = "partnerApiKey",
    type = SecuritySchemeType.APIKEY,
    paramName = "X-API-Key",
    in = SecuritySchemeIn.HEADER,
    description = "API key của đối tác."
)
public class PartnerApiKeyConfiguration {
}
~~~

Với OAuth2 authorization code:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;

@Configuration
@SecurityScheme(
    name = "ordersOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "orders:read",
                    description = "Đọc đơn hàng"
                ),
                @OAuthScope(
                    name = "orders:write",
                    description = "Tạo và cập nhật đơn hàng"
                )
            }
        )
    )
)
public class OAuthOpenApiConfiguration {
}
~~~

Đặt annotation trên một lớp cấu hình được Spring quét. Các import và enum phải khớp phiên bản `swagger-annotations` mà springdoc đang quản lý. Khi một annotation field không có trong phiên bản hiện tại, hãy kiểm tra Javadoc của dependency thay vì tự thêm thuộc tính không được hỗ trợ.

## 9. Định nghĩa scheme bằng OpenAPI bean

Nếu muốn cấu hình bằng Java thay vì annotation, có thể thêm scheme vào `Components` của `OpenAPI` bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.security.SecurityScheme;

@Configuration
public class OpenApiSecurityConfiguration {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
            .components(new Components()
                .addSecuritySchemes(
                    "bearerAuth",
                    new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")
                )
            );
    }
}
~~~

Đoạn code này chỉ định nghĩa scheme. Để yêu cầu scheme trên toàn tài liệu, cần thêm Security Requirement:

~~~java
import io.swagger.v3.oas.models.security.SecurityRequirement;

return new OpenAPI()
    .components(new Components()
        .addSecuritySchemes(
            "bearerAuth",
            new SecurityScheme()
                .type(SecurityScheme.Type.HTTP)
                .scheme("bearer")
                .bearerFormat("JWT")
        )
    )
    .addSecurityItem(
        new SecurityRequirement().addList("bearerAuth")
    );
~~~

Trong ứng dụng đã có `OpenAPI` bean để khai báo `Info`, server, tag hoặc scheme khác, hãy mở rộng bean hiện có và hợp nhất components. Không tạo các bean cạnh tranh cùng quản lý một phần tài liệu nếu điều đó làm cấu hình khó theo dõi.

## 10. Security Requirement Object ở cấp toàn API

Thuộc tính `security` ở cấp OpenAPI áp dụng mặc định cho các operation trong tài liệu. Ví dụ:

~~~yaml
openapi: 3.1.0
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
  /orders:
    get:
      summary: Liệt kê đơn hàng
      responses:
        '200':
          description: Thành công
~~~

Trong ví dụ, operation `/orders` kế thừa requirement toàn cục. Mảng rỗng `[]` là danh sách scope của scheme; với HTTP Bearer, Basic hoặc API key, không khai báo OAuth scope nên dùng mảng rỗng.

Nếu API có nhiều scheme toàn cục thay thế nhau, có thể khai báo nhiều Security Requirement Object:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Đây là quan hệ **OR**: client có thể dùng bearer token hoặc API key. Chỉ cần đáp ứng một requirement object trong danh sách.

## 11. Security Requirement Object ở cấp operation

Một operation có thể khai báo `security` riêng để ghi đè cấu hình toàn cục. Ví dụ endpoint đọc đơn hàng yêu cầu scope `orders:read`:

~~~yaml
paths:
  /orders:
    get:
      security:
        - ordersOAuth:
            - orders:read
      responses:
        '200':
          description: Thành công
~~~

Nếu một operation yêu cầu nhiều scope của cùng một OAuth2 scheme, liệt kê các scope trong mảng của scheme đó. Tên scope phải được khai báo trong flow tương ứng và phải khớp với scope mà authorization server cấp.

Với springdoc, có thể gắn requirement vào operation bằng `@SecurityRequirement`:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/orders")
    @Operation(
        summary = "Liệt kê đơn hàng",
        security = @SecurityRequirement(
            name = "ordersOAuth",
            scopes = {"orders:read"}
        )
    )
    public List<OrderResponse> findAll() {
        return orderService.findAll();
    }
}
~~~

`@SecurityRequirement.name` phải khớp tên scheme đã khai báo. `scopes` dùng cho OAuth2 hoặc OpenID Connect; với HTTP Basic, Bearer hoặc API key, để scopes rỗng.

Nếu muốn áp dụng một scheme cho phần lớn API ngay từ annotation, có thể khai báo security ở `@OpenAPIDefinition`:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@Configuration
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
public class OpenApiGlobalSecurityConfiguration {
}
~~~

Ví dụ này giả định scheme `bearerAuth` đã được định nghĩa bằng `@SecurityScheme` hoặc `OpenAPI` bean. Các operation sẽ kế thừa requirement toàn cục; operation có cấu hình security riêng sẽ ghi đè requirement đó.

## 12. Phân biệt OR và AND trong Security Requirement

Đây là quy tắc quan trọng nhất khi đọc mảng `security`:

- Nhiều object trong mảng `security` là các lựa chọn thay thế nhau (**OR**).
- Nhiều scheme trong cùng một object phải được đáp ứng đồng thời (**AND**).

Ví dụ OR: chấp nhận bearer token hoặc API key:

~~~yaml
security:
  - bearerAuth: []
  - partnerApiKey: []
~~~

Ví dụ AND: yêu cầu cả bearer token và tenant key:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
    tenantKey:
      type: apiKey
      in: header
      name: X-Tenant-Key

security:
  - bearerAuth: []
    tenantKey: []
~~~

Trong ví dụ AND, client phải gửi cả:

~~~http
Authorization: Bearer <access-token>
X-Tenant-Key: <tenant-key>
~~~

Nếu viết thành hai object riêng như sau:

~~~yaml
security:
  - bearerAuth: []
  - tenantKey: []
~~~

thì kết quả là OR, nghĩa là chỉ cần một trong hai scheme. Đặt nhầm dấu gạch đầu dòng hoặc thụt lề YAML có thể làm thay đổi hoàn toàn chính sách được công bố.

## 13. Endpoint công khai và ghi đè security toàn cục

Nếu tài liệu có `security` toàn cục nhưng một endpoint cho phép truy cập ẩn danh, có hai cách biểu diễn cần phân biệt:

`security: []` đặt trên operation có nghĩa không yêu cầu scheme nào và ghi đè security kế thừa:

~~~yaml
paths:
  /health:
    get:
      security: []
      responses:
        '200':
          description: Trạng thái dịch vụ
~~~

`security: [{}]` biểu thị requirement rỗng, tức cho phép truy cập ẩn danh:

~~~yaml
paths:
  /catalog:
    get:
      security:
        - {}
        - bearerAuth: []
      responses:
        '200':
          description: Danh mục sản phẩm
~~~

Ở ví dụ thứ hai, operation cho phép truy cập không xác thực hoặc dùng bearer token. Nếu chỉ muốn công bố endpoint hoàn toàn không có bảo mật, `security: []` là cách rõ ràng hơn.

Khi một operation có thuộc tính `security` riêng, nó thay thế requirement ở cấp OpenAPI; không tự động cộng thêm vào requirement toàn cục. Hãy kiểm tra output JSON để chắc rằng operation công khai không vô tình kế thừa yêu cầu xác thực.

## 14. Security Scheme không phải cấu hình Spring Security

`@SecurityScheme` và `security` chỉ tạo metadata OpenAPI. Chúng không:

- Tạo user, password, API key hoặc JWT.
- Xác thực chữ ký hay thời hạn của token.
- Cấp OAuth scope hoặc kiểm tra quyền của người dùng.
- Cấu hình filter chain, CORS, CSRF hoặc session trong Spring Security.
- Chặn request khi client không gửi thông tin xác thực.

Ví dụ, khai báo `bearerAuth` trong OpenAPI không tự bảo vệ controller. Ứng dụng vẫn phải cấu hình Spring Security resource server hoặc cơ chế xác thực phù hợp, kiểm tra issuer/audience/chữ ký token và phân quyền cho endpoint.

Ngược lại, việc Spring Security đã bảo vệ endpoint cũng không đảm bảo springdoc tự suy ra scheme và requirement chính xác. Hãy khai báo tài liệu OpenAPI rõ ràng, rồi kiểm tra nó khớp với chính sách runtime.

Swagger UI có nút Authorize để người dùng nhập thông tin xác thực hoặc thực hiện flow OAuth được cấu hình. Nút này chỉ giúp gửi request thử nghiệm; nó không thay thế authorization server hoặc cơ chế xác thực của API.

## 15. Kiểm tra Security Scheme và Requirement trong đặc tả

Sau khi khởi động ứng dụng, mở `/v3/api-docs` hoặc endpoint group tương ứng. Trong JSON, kiểm tra:

1. `components.securitySchemes` có định nghĩa scheme với tên mong muốn.
2. `type` và các trường bắt buộc đúng loại scheme.
3. API key có đúng `name` và `in`.
4. HTTP auth có đúng `scheme`; bearer token không bị khai báo thành query parameter.
5. OAuth2 có đúng flow, authorization URL, token URL và scope.
6. OpenID Connect có đúng discovery URL.
7. Requirement tham chiếu đúng tên scheme.
8. Scope trong requirement đã được khai báo trong flow tương ứng.
9. Global security và operation security có đúng phạm vi.
10. Các operation công khai có `security: []` hoặc requirement rỗng đúng ý định.
11. Quy tắc OR/AND khớp với cách client phải gửi credential.

Có thể tải tài liệu bằng curl:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Sau đó mở Swagger UI và thử:

- Nút Authorize có hiển thị scheme đúng tên và loại không.
- Bearer token được gửi trong header `Authorization` với tiền tố `Bearer`.
- API key được gửi đúng header/query/cookie.
- OAuth flow yêu cầu đúng authorization URL, token URL và scope.
- Operation công khai không tự động gửi credential nếu không cần.

Cuối cùng, gọi endpoint thật với các trường hợp thiếu credential, credential sai và credential hợp lệ. Đối chiếu status thực tế với response được mô tả trong OpenAPI. Đây là bước xác minh riêng với việc kiểm tra giao diện Swagger UI.

## 16. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Nút Authorize không xuất hiện scheme | Chỉ khai báo requirement mà chưa định nghĩa scheme, hoặc annotation chưa được quét | Kiểm tra `components.securitySchemes` trong `/v3/api-docs` |
| Operation không hiện biểu tượng khóa | Thiếu `security` toàn cục/operation hoặc tên requirement sai | Đối chiếu tên trong `security` với tên component |
| Swagger UI gửi token sai header | Scheme khai báo nhầm thành apiKey hoặc dùng sai `scheme` | Dùng `type: http`, `scheme: bearer` cho bearer token |
| OAuth không hiển thị scope | Scope chưa được khai báo trong flow hoặc requirement dùng tên khác | Đồng bộ tên scope trong flow và operation requirement |
| Endpoint public vẫn có biểu tượng khóa | Operation kế thừa security toàn cục | Đặt `security: []` trên operation công khai |
| Chỉ một credential được chấp nhận dù cần cả hai | Hai scheme bị đặt thành hai requirement object riêng | Đặt cả hai scheme trong cùng một object để biểu diễn AND |
| Swagger UI cho phép chọn một scheme trong khi API yêu cầu cả hai | Requirement list bị hiểu nhầm OR/AND | Kiểm tra cấu trúc mảng và thụt lề YAML |
| `bearerFormat: JWT` nhưng token sai vẫn qua Swagger UI | bearerFormat chỉ là gợi ý hiển thị | Xác thực JWT ở runtime bằng resource server/security filter |
| Định nghĩa mTLS không được validator chấp nhận | Tài liệu đang xuất OpenAPI 3.0.x hoặc toolchain cũ | Dùng phiên bản hỗ trợ OpenAPI 3.1 và kiểm tra validator |
| Spring Security đã bảo vệ API nhưng tài liệu không có Authorize | Security runtime và metadata OpenAPI là hai cấu hình riêng | Thêm `@SecurityScheme`/OpenAPI bean và Security Requirement |

## 17. Nguyên tắc thiết kế

Đặt mỗi scheme trong `components.securitySchemes` với tên ngắn, ổn định và mô tả rõ cách client gửi thông tin xác thực. Dùng `apiKey` cho key ở header, query hoặc cookie; dùng `http` cho Basic/Bearer; dùng `oauth2` hoặc `openIdConnect` cho hệ thống ủy quyền tập trung; dùng `mutualTLS` khi API thực sự xác thực client bằng chứng thư và tài liệu tương thích OpenAPI 3.1.

Đặt `security` toàn cục khi hầu hết operation dùng cùng chính sách. Dùng requirement cấp operation khi endpoint có scope khác, cho phép nhiều cách xác thực hoặc công khai. Luôn nhớ: các object requirement trong mảng là OR, còn các scheme trong cùng object là AND. Khi có OAuth2/OIDC, đồng bộ scope giữa flow, requirement và authorization server.

Sau khi cấu hình, kiểm tra OpenAPI JSON, Swagger UI và hành vi bảo mật thật của ứng dụng. Một hợp đồng tốt cần mô tả đúng cơ chế mà client phải sử dụng, đồng thời phản ánh chính xác những gì Spring Security hoặc gateway đang thực thi.

## 18. Tài liệu tham khảo chính thức

- [OpenAPI Specification 3.1.2 — Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object) — các loại scheme, trường bắt buộc, OAuth flow và ví dụ.
- [OpenAPI Specification 3.1.2 — Security Requirement Object](https://spec.openapis.org/oas/v3.1.2.html#security-requirement-object) — quy tắc tham chiếu scheme, OR/AND và truy cập ẩn danh.
- [springdoc-openapi v2 FAQ — Define SecurityScheme](https://springdoc.org/v2/faq.html) — khai báo `@SecurityScheme`, `@SecurityRequirement` và OpenAPI bean.
- [Swagger Annotations — SecurityScheme](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/security/SecurityScheme.html) — thuộc tính annotation cho scheme.
- [Swagger Annotations — SecurityRequirement](https://docs.swagger.io/swagger-core/v2.2.25/apidocs/io/swagger/v3/oas/annotations/security/SecurityRequirement.html) — annotation gắn security requirement vào API.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html) — khuyến nghị bảo mật OAuth 2.0, bao gồm loại bỏ các flow không còn phù hợp cho thiết kế mới.

Security Scheme Object mô tả cách xác thực; Security Requirement Object cho biết nơi và cách áp dụng cơ chế đó. Tách bạch hai lớp này giúp springdoc tạo tài liệu dễ hiểu, giúp Swagger UI gửi credential đúng cách và giúp nhóm phát triển đối chiếu hợp đồng OpenAPI với chính sách bảo mật thực thi.
