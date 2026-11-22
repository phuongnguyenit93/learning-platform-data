# Danh sách scope và ý nghĩa đối với operation

OAuth 2.0 cho phép ứng dụng yêu cầu quyền truy cập theo từng phạm vi (scope). Một access token có thể được cấp một hoặc nhiều scope như `products:read`, `products:write` hoặc `orders:cancel`. API dùng các scope đó để xác định client được phép thực hiện nhóm hành động nào. OpenAPI có thể mô tả danh sách scope trong security scheme và chỉ rõ scope cần thiết cho từng operation, giúp người tích hợp hiểu quyền nào phải có khi gọi endpoint.

Trong springdoc-openapi, phần mô tả này được tạo từ annotation như `@SecurityScheme`, `@OAuthFlow`, `@OAuthScope` và `@SecurityRequirement`, hoặc được khai báo trong OpenAPI YAML. Cần phân biệt rõ hai việc: đặc tả OpenAPI công bố yêu cầu bảo mật cho client; Spring Security và resource server mới thực thi việc kiểm tra token cùng quyền truy cập khi request đến ứng dụng.

Bài học này tập trung vào cách định nghĩa scope, liên kết scope với operation, đọc semantics OR/AND của Security Requirement Object và kiểm tra tài liệu được sinh.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích scope trong OAuth 2.0 và OpenID Connect.
- Phân biệt scope, role, authority và quyền truy cập một tài nguyên cụ thể.
- Định nghĩa scope trong OAuth2 flow của OpenAPI.
- Liên kết scope với từng operation bằng Security Requirement Object.
- Hiểu quan hệ OR giữa các requirement object và AND giữa các scheme trong một object.
- Dùng `@SecurityScheme`, `@OAuthScope` và `@SecurityRequirement` với springdoc-openapi.
- Thiết kế danh sách scope theo nguyên tắc quyền tối thiểu và tên gọi nhất quán.
- Đồng bộ tài liệu OpenAPI với chính sách kiểm tra quyền trong Spring Security.
- Kiểm thử scope trong `/v3/api-docs` và kiểm thử quyền truy cập ở runtime.

## 1. Scope là gì?

Scope là một chuỗi định danh phạm vi quyền mà client yêu cầu khi xin access token. Authorization server quyết định có cấp các scope đó hay không dựa trên client, người dùng, consent, policy và grant type. Resource server nhận token rồi kiểm tra các quyền được thể hiện trong token trước khi cho phép thao tác.

Ví dụ API quản lý sản phẩm có thể định nghĩa:

| Scope | Ý nghĩa |
|---|---|
| `products:read` | Đọc thông tin sản phẩm |
| `products:write` | Tạo hoặc cập nhật sản phẩm |
| `products:delete` | Xóa sản phẩm |
| `orders:read` | Đọc đơn hàng |
| `orders:cancel` | Hủy đơn hàng |

Một client chỉ cần xem danh sách sản phẩm có thể xin `products:read`. Một ứng dụng quản trị có thể cần cả `products:read` và `products:write`. Token không nhất thiết chứa mọi scope mà API biết; authorization server chỉ cấp những quyền được chấp thuận cho lần cấp token đó.

Scope thường xuất hiện trong access token dưới dạng claim `scope` hoặc `scp`, tùy authorization server và cấu hình. Giá trị có thể là chuỗi chứa các scope cách nhau bằng dấu cách hoặc một mảng chuỗi. OpenAPI mô tả tên và ý nghĩa scope; nó không quy định duy nhất cách authorization server serialize claim trong token.

### Scope không phải là role

Scope và role có thể cùng tham gia quyết định truy cập nhưng phục vụ các mục đích khác nhau:

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Scope | Token được cấp quyền thực hiện nhóm hành động nào? | `products:read` |
| Role | Người dùng hoặc principal thuộc nhóm nghiệp vụ nào? | `PRODUCT_MANAGER` |
| Authority | Spring Security dùng quyền nào để đánh giá rule? | `SCOPE_products:read` |
| Quyền trên tài nguyên | Principal có được thao tác trên bản ghi cụ thể không? | Được sửa sản phẩm thuộc tenant hiện tại |

Một authorization server có thể ánh xạ role thành scope khi cấp token, hoặc ứng dụng có thể chuyển claim thành authority. Không nên mặc định tên role và scope là một. Scope cũng không thay thế kiểm tra quyền trên từng bản ghi: token có `products:read` không đồng nghĩa người dùng được đọc mọi sản phẩm thuộc mọi tenant.

### Scope không phải tên security scheme

Security scheme là cơ chế xác thực được khai báo trong `components.securitySchemes`, ví dụ `oauth2`, `bearerAuth` hoặc `apiKeyAuth`. Scope là quyền nằm bên trong OAuth2 flow hoặc được nêu trong security requirement.

Ví dụ:

- `oauth2` là tên scheme.
- `products:read` là scope.
- Operation yêu cầu scheme `oauth2` với scope `products:read`.

Tên scheme trong security requirement phải khớp chính xác với tên đã khai báo trong components. Scope cũng cần khớp với tên scope được định nghĩa trong OAuth2 flow.

## 2. Định nghĩa scope trong OAuth2 flow

OpenAPI đặt các scope trong security scheme loại `oauth2`, bên trong flow tương ứng. Mỗi flow có thể công bố tập scope cùng mô tả riêng.

Ví dụ authorization code flow:

~~~yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://auth.example.com/oauth2/authorize
          tokenUrl: https://auth.example.com/oauth2/token
          scopes:
            products:read: Đọc thông tin sản phẩm
            products:write: Tạo và cập nhật sản phẩm
            products:delete: Xóa sản phẩm
            orders:read: Đọc đơn hàng
            orders:cancel: Hủy đơn hàng
~~~

Trong ví dụ:

- `oauth2` là tên security scheme.
- `authorizationCode` là OAuth2 flow.
- `authorizationUrl` là endpoint điều hướng người dùng đến authorization server.
- `tokenUrl` là endpoint đổi authorization code lấy token.
- `scopes` là map giữa tên scope và mô tả hiển thị cho người tích hợp.

Tên scope là key của map; phần mô tả là giá trị. Không dùng mô tả tiếng Việt làm tên scope nếu API cần một định danh ổn định. Client gửi tên scope trong request cấp token; mô tả chỉ giúp người đọc hiểu quyền đó.

### Scope theo từng flow

OpenAPI cho phép khai báo các flow khác nhau:

- `authorizationCode`: thường dùng cho ứng dụng có người dùng đăng nhập và cần luồng authorization code.
- `clientCredentials`: thường dùng cho giao tiếp giữa service với service.
- `implicit`: flow cũ, không nên chọn cho ứng dụng mới.
- `password`: resource owner password credentials grant cũ, không nên dùng cho thiết kế mới.

Mỗi flow có map `scopes` của riêng nó. Nếu một scheme công bố nhiều flow, hãy bảo đảm operation chỉ yêu cầu scope có ý nghĩa với flow mà client có thể sử dụng. Ví dụ ứng dụng máy chủ có thể xin `products:read` bằng client credentials, trong khi ứng dụng người dùng có thể nhận cùng scope qua authorization code flow nếu authorization server hỗ trợ.

Không nên khai báo scope trong OpenAPI rồi giả định authorization server tự biết cấp scope đó. Scope phải được cấu hình và hỗ trợ tại authorization server; resource server cũng phải kiểm tra nó theo policy.

## 3. Security Requirement Object và danh sách scope

OpenAPI liên kết scope với operation bằng Security Requirement Object. Với OAuth2, object này dùng tên security scheme làm key và danh sách scope bắt buộc làm value:

~~~yaml
security:
  - oauth2:
      - products:read
~~~

Nội dung có nghĩa operation yêu cầu access token qua scheme `oauth2` và token phải có scope `products:read`.

Nếu operation cần nhiều scope:

~~~yaml
security:
  - oauth2:
      - products:read
      - inventory:read
~~~

Trong một requirement object, tất cả scope được liệt kê cho scheme OAuth2 đều là scope được yêu cầu. Client cần có token thỏa mãn toàn bộ danh sách đó theo semantics của authorization server và resource server.

### Scope phải khớp định nghĩa

Nếu `products:read` được yêu cầu ở operation, scope này nên được khai báo trong `scopes` của OAuth2 flow tương ứng:

~~~yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://auth.example.com/oauth2/token
          scopes:
            products:read: Đọc thông tin sản phẩm
~~~

Tránh lỗi chính tả hoặc dùng tên khác nhau cho cùng quyền, ví dụ khai báo `product:read` nhưng operation yêu cầu `products:read`. Công cụ có thể vẫn sinh tài liệu, nhưng người tích hợp sẽ yêu cầu scope không được mô tả trong flow.

Với security scheme không phải OAuth2 hoặc OpenID Connect, danh sách scope phải rỗng. Ví dụ bearer HTTP authentication hoặc API key không dùng scope trong Security Requirement Object:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

Không gắn `products:read` vào `bearerAuth` chỉ vì access token JWT có claim scope. Nếu muốn OpenAPI biểu diễn scope theo chuẩn, hãy khai báo scheme OAuth2 hoặc OpenID Connect phù hợp. Bearer scheme chỉ mô tả cơ chế gửi bearer token.

## 4. Ý nghĩa OR và AND trong security

Một điểm dễ nhầm là OpenAPI dùng hai cấp collection để biểu diễn quan hệ logic:

- Danh sách `security` chứa nhiều Security Requirement Object: các object là các lựa chọn thay thế (OR).
- Một Security Requirement Object chứa nhiều security scheme: tất cả scheme trong cùng object phải được đáp ứng (AND).

Ví dụ client có thể chọn bearer token hoặc API key:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

Đây là OR: chỉ cần thỏa mãn một trong hai cách xác thực.

Ví dụ operation yêu cầu cả OAuth2 scope lẫn API key:

~~~yaml
security:
  - oauth2:
      - products:write
    apiKeyAuth: []
~~~

Đây là AND: token OAuth2 phải có `products:write` và request đồng thời phải gửi API key.

Nếu cùng một scheme OAuth2 yêu cầu nhiều scope:

~~~yaml
security:
  - oauth2:
      - products:write
      - inventory:read
~~~

Client phải có cả hai scope trong token. Nếu muốn một trong hai scope là đủ, biểu diễn thành hai requirement object:

~~~yaml
security:
  - oauth2:
      - products:write
  - oauth2:
      - inventory:read
~~~

Đây là hai lựa chọn thay thế. Resource server phải thực thi policy tương ứng với hợp đồng này; tài liệu chỉ mô tả logic mà client cần đáp ứng.

### Bảng đọc nhanh

| Cấu trúc | Ý nghĩa |
|---|---|
| Một object, một scheme, một scope | Yêu cầu một scope |
| Một object, một scheme, nhiều scope | Yêu cầu tất cả scope đã liệt kê |
| Một object, nhiều scheme | Yêu cầu tất cả scheme |
| Nhiều object trong danh sách `security` | Chấp nhận một trong các phương án |
| Một object rỗng `{}` trong danh sách | Cho phép truy cập ẩn danh như một phương án |
| `security: []` trên operation | Không yêu cầu security cho operation đó |

Không dùng danh sách requirement như thể nó là danh sách quyền cộng dồn. Nếu đặt hai object riêng biệt với `products:read` và `products:write`, semantics là OR, không phải yêu cầu cả hai.

## 5. Scope ở cấp tài liệu và cấp operation

Có thể đặt `security` ở root của OpenAPI để áp dụng mặc định cho các operation:

~~~yaml
security:
  - oauth2:
      - products:read
~~~

Operation kế thừa security mặc định nếu không khai báo `security` riêng. Khi operation có property `security`, property đó thay thế yêu cầu ở root cho operation đó.

Ví dụ:

~~~yaml
paths:
  /api/products:
    get:
      summary: Đọc danh sách sản phẩm
      security:
        - oauth2:
            - products:read
    post:
      summary: Tạo sản phẩm
      security:
        - oauth2:
            - products:write
  /api/health:
    get:
      summary: Kiểm tra tình trạng dịch vụ
      security: []
~~~

Trong ví dụ, GET `/api/products` yêu cầu `products:read`, POST `/api/products` yêu cầu `products:write`, còn `/api/health` công khai dù root có thể đặt security mặc định. `security: []` là cách biểu đạt rõ operation không yêu cầu security.

### Phân biệt bỏ qua security và cho phép ẩn danh

Hai cấu hình sau có ý nghĩa khác nhau:

~~~yaml
security: []
~~~

Danh sách rỗng có nghĩa không áp dụng security requirement nào cho operation.

~~~yaml
security:
  - {}
  - oauth2:
      - products:read
~~~

Danh sách có object rỗng cho phép truy cập ẩn danh như một lựa chọn, đồng thời cũng chấp nhận phương án OAuth2 với scope đã nêu. Đây là cách biểu diễn endpoint có thể được gọi công khai hoặc có xác thực tùy request.

Hãy chọn cấu hình theo hành vi thực tế của server. Không dùng object rỗng để mô tả endpoint bắt buộc đăng nhập.

## 6. Khai báo scope bằng annotation của springdoc

Có thể định nghĩa OAuth2 security scheme bằng annotation swagger-core mà springdoc đọc khi tạo tài liệu:

~~~java
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth2/authorize",
            tokenUrl = "https://auth.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products:read",
                    description = "Đọc thông tin sản phẩm"
                ),
                @OAuthScope(
                    name = "products:write",
                    description = "Tạo và cập nhật sản phẩm"
                ),
                @OAuthScope(
                    name = "products:delete",
                    description = "Xóa sản phẩm"
                )
            }
        )
    )
)
public class OpenApiSecurityConfiguration {
}
~~~

Annotation này tạo `components.securitySchemes.oauth2` và khai báo các scope trong authorization code flow. Các URL trong ví dụ là địa chỉ minh họa; thay bằng endpoint thực của authorization server. Không đặt client secret trong OpenAPI annotation hoặc tài liệu được công bố.

Các annotation nằm trong package `io.swagger.v3.oas.annotations.security`, còn `SecuritySchemeType` nằm trong `io.swagger.v3.oas.annotations.enums`. Tên package có thể được IDE tự import từ dependency swagger-annotations do springdoc quản lý.

### Gắn scope vào từng operation

Dùng `@Operation` để mô tả scope cần thiết cho endpoint:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/api/products")
    @Operation(
        summary = "Đọc danh sách sản phẩm",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"products:read"}
        )
    )
    public List<ProductResponse> list() {
        return productService.findAll();
    }

    @PostMapping("/api/products")
    @Operation(
        summary = "Tạo sản phẩm",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"products:write"}
        )
    )
    public ProductResponse create(@RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
~~~

Operation GET yêu cầu `products:read`; operation POST yêu cầu `products:write`. `@SecurityRequirement.name` phải trùng với tên scheme `oauth2`, còn `scopes` chứa tên scope, không phải mô tả scope.

Đoạn controller trên tập trung vào annotation bảo mật; trong ứng dụng thật cần khai báo constructor injection cho `ProductService` và các DTO `ProductResponse`, `CreateProductRequest`. Import thêm `org.springframework.web.bind.annotation.RequestBody` cho tham số body.

### Scope hiển thị trong Swagger UI

Khi Swagger UI đọc OAuth2 scheme có map `scopes`, hộp thoại Authorize có thể hiển thị các scope cùng mô tả để người dùng chọn khi thực hiện OAuth2 authorization. Security requirement của operation cho biết scope nào được yêu cầu trong hợp đồng. Swagger UI không tự cấp quyền: authorization server vẫn quyết định scope được cấp cho client và người dùng.

Để Authorize hoạt động, ứng dụng còn cần cấu hình OAuth client phù hợp như client ID, redirect URL và PKCE theo loại client. Không đưa client secret vào tài liệu công khai hoặc JavaScript chạy trong trình duyệt.

Nếu một operation cần nhiều scope đồng thời, liệt kê chúng trong cùng annotation:

~~~java
@Operation(
    summary = "Xuất báo cáo tồn kho",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"products:read", "inventory:read"}
    )
)
~~~

Điều này tương ứng một requirement object có một OAuth2 scheme và hai scope được yêu cầu. Nó không có nghĩa client được chọn một trong hai scope.

### Nhiều phương án xác thực bằng annotation

`@SecurityRequirements` là annotation container để khai báo nhiều security requirement. Mỗi requirement riêng trong danh sách là một phương án thay thế (OR):

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityRequirements;

@GetMapping("/api/partner/products")
@SecurityRequirements({
    @SecurityRequirement(
        name = "oauth2",
        scopes = {"products:read"}
    ),
    @SecurityRequirement(name = "partnerApiKey")
})
public List<ProductResponse> partnerProducts() {
    return productService.findAll();
}
~~~

Tài liệu biểu diễn OAuth2 với scope `products:read` hoặc API key `partnerApiKey`. Client chỉ cần đáp ứng một trong hai requirement object. Nếu muốn nhiều scheme bắt buộc cùng lúc (AND), hãy kiểm tra cấu trúc OpenAPI cuối cùng; khai báo nhiều annotation `@SecurityRequirement` không tự động tạo một object AND.

Để biểu diễn AND giữa nhiều scheme, YAML OpenAPI thể hiện rõ nhất:

~~~yaml
security:
  - oauth2:
      - products:write
    partnerApiKey: []
~~~

Một requirement object duy nhất chứa cả hai scheme, nên request cần token có scope và API key. Nếu phải tạo cấu trúc này bằng Java, dùng một customizer trên OpenAPI model và kiểm thử kết quả JSON thay vì dựa vào cách đọc annotation.

### Scope ở cấp controller và method

Swagger annotations cho phép đặt security metadata ở cấp type hoặc method. Khi dùng kết hợp, hãy xác minh operation cuối cùng trong `/v3/api-docs` để biết annotation được kế thừa hoặc thay thế như thế nào trong phiên bản swagger-core/springdoc của dự án. Với API có quyền khác nhau theo endpoint, khai báo rõ trên từng `@Operation` giúp người đọc thấy trực tiếp scope của operation đó.

## 7. OpenID Connect scopes

OpenID Connect xây dựng trên OAuth 2.0 và dùng scope để yêu cầu thông tin nhận diện người dùng. Các scope chuẩn thường gặp:

- `openid`: bắt buộc để một request trở thành OpenID Connect authentication request.
- `profile`: yêu cầu các claim hồ sơ người dùng được hỗ trợ.
- `email`: yêu cầu thông tin email được hỗ trợ.
- `address` và `phone`: yêu cầu nhóm claim địa chỉ hoặc số điện thoại nếu provider hỗ trợ.

OpenAPI có thể khai báo OpenID Connect scheme bằng discovery URL:

~~~yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://auth.example.com/.well-known/openid-configuration
~~~

Operation có thể yêu cầu các scope OIDC:

~~~yaml
security:
  - oidc:
      - openid
      - profile
      - email
~~~

Với `openIdConnect`, scope được ghi trong security requirement theo tên scope của provider. Không có map `flows.*.scopes` trong OpenAPI scheme này như OAuth2 scheme; metadata discovery được lấy từ `openIdConnectUrl`.

Scope OIDC `profile` hoặc `email` mô tả quyền yêu cầu claim identity. Chúng không tự cấp quyền đọc dữ liệu nghiệp vụ như sản phẩm hay đơn hàng. Nếu API cần quyền nghiệp vụ, hãy dùng scope API do authorization server định nghĩa, hoặc mô tả rõ cách provider kết hợp scope OIDC với scope API.

## 8. Thiết kế danh sách scope dễ quản lý

Danh sách scope nên phản ánh hành động API và nhu cầu tích hợp. Một cách đặt tên dễ đọc là `resource:action`:

| Nhóm | Scope đề xuất | Operation ví dụ |
|---|---|---|
| Sản phẩm | `products:read` | GET `/api/products`, GET `/api/products/{id}` |
| Sản phẩm | `products:write` | POST `/api/products`, PUT `/api/products/{id}` |
| Sản phẩm | `products:delete` | DELETE `/api/products/{id}` |
| Đơn hàng | `orders:read` | GET `/api/orders` |
| Đơn hàng | `orders:cancel` | POST `/api/orders/{id}/cancel` |
| Báo cáo | `reports:read` | GET `/api/reports/sales` |

Đây là quy ước, không phải cú pháp bắt buộc của OAuth2. Một số hệ thống dùng dấu chấm hoặc dấu gạch ngang; điều quan trọng là tên ổn định, nhất quán và được authorization server hỗ trợ.

### Nguyên tắc đặt scope

1. Dùng tên ngắn, ổn định và mô tả một nhóm hành động rõ ràng.
2. Tách quyền đọc và ghi khi client có nhu cầu khác nhau.
3. Chỉ tạo scope riêng cho hành động nhạy cảm như xóa, phê duyệt, hoàn tiền hoặc hủy.
4. Tránh tạo một scope cho từng URL nếu các operation có cùng quyền nghiệp vụ.
5. Tránh scope quá rộng như `admin:all` nếu có thể biểu diễn quyền tối thiểu hơn.
6. Không nhúng user ID, tenant ID hoặc resource ID động vào scope; các giá trị đó thuộc token claim hoặc kiểm tra quyền tài nguyên.
7. Giữ đúng chữ hoa/thường và dấu phân cách giữa authorization server, resource server và OpenAPI.
8. Viết mô tả scope theo hành động mà client được phép thực hiện, không mô tả theo tên vai trò nội bộ.

Tên scope OAuth2 là token định danh và nên được coi là phân biệt chữ hoa/chữ thường. `products:read` và `Products:Read` không nên được xem là cùng một scope. Tránh đổi tên scope đã phát hành nếu chưa có kế hoạch tương thích cho client và token hiện hữu.

### Tránh scope quá rộng hoặc quá vụn

Scope quá rộng làm client có nhiều quyền hơn nhu cầu. Scope quá vụn khiến authorization server, tài liệu và client phải quản lý một danh sách lớn, khó hiểu. Hãy bắt đầu từ nhóm hành động nghiệp vụ và chia nhỏ khi có yêu cầu phân quyền thực tế.

Ví dụ, `products:manage` có thể bao gồm đọc, tạo, cập nhật và xóa. Nếu nhiều client chỉ cần đọc hoặc cập nhật, các scope `products:read`, `products:write` và `products:delete` cho phép cấp quyền tối thiểu hơn.

Ngược lại, không nhất thiết tạo `products:read:name`, `products:read:price` và `products:read:description` nếu API không có yêu cầu tách quyền theo từng trường. Việc che dữ liệu nhạy cảm theo field có thể cần policy hoặc DTO riêng thay vì tạo scope cho từng property.

## 9. Đồng bộ scope OpenAPI với Spring Security

OpenAPI annotation không cấp scope cho token và cũng không chặn request. Nó chỉ mô tả hợp đồng cho client. Ở runtime, resource server phải xác thực token, chuyển scope thành authority và kiểm tra authority đó trước khi xử lý operation.

Với Spring Security Resource Server dùng JWT, `JwtGrantedAuthoritiesConverter` mặc định có thể đọc claim `scope` hoặc `scp` và chuyển mỗi scope thành authority có tiền tố `SCOPE_`. Ví dụ token có scope `products:read` sẽ tương ứng authority `SCOPE_products:read` theo cấu hình mặc định.

Có thể bảo vệ method bằng method security:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/api/products")
    @PreAuthorize("hasAuthority('SCOPE_products:read')")
    @Operation(
        summary = "Đọc danh sách sản phẩm",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"products:read"}
        )
    )
    public List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

Để `@PreAuthorize` có hiệu lực, bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Nếu dùng URL authorization thay vì method security, có thể kiểm tra authority theo HTTP method và path trong `SecurityFilterChain`. Dù chọn cách nào, rule runtime cần khớp scope được mô tả trong OpenAPI.

### Phân biệt 401 và 403

- `401 Unauthorized`: request không có thông tin xác thực hợp lệ, token thiếu, hết hạn hoặc không xác thực được.
- `403 Forbidden`: principal đã được xác thực nhưng không có authority/scope cần thiết cho operation.

Tên status `401` có thể gây nhầm với nghĩa thông thường của từ “Unauthorized”; trong HTTP semantics, nó chỉ ra thiếu hoặc không hợp lệ thông tin xác thực. `403` thể hiện server hiểu request nhưng từ chối quyền truy cập.

### Kiểm tra cả scope và quyền tài nguyên

Scope thường biểu diễn quyền ở mức nhóm hành động. Ứng dụng vẫn cần kiểm tra:

- Principal có thuộc tenant sở hữu tài nguyên không.
- Người dùng có được đọc đơn hàng cụ thể không.
- Bản ghi có ở trạng thái cho phép cập nhật hoặc hủy không.
- Người dùng có quyền truy cập dữ liệu thuộc đơn vị hoặc khách hàng hiện tại không.

Ví dụ `products:write` cho phép nhóm thao tác ghi sản phẩm, nhưng service vẫn phải kiểm tra người gọi có quyền sửa sản phẩm có ID cụ thể hay không. Không nên dùng scope làm cách duy nhất để kiểm tra ownership hoặc phân tách tenant.

### Khi claim scope có định dạng khác

Một số identity provider đặt quyền trong claim tùy chỉnh hoặc dùng tên claim khác. Khi đó cần cấu hình `JwtAuthenticationConverter`/`JwtGrantedAuthoritiesConverter` để chuyển claim thành authority nhất quán. Nếu token phát ra `permissions: ["products:read"]` nhưng Spring Security chỉ đọc `scope` hoặc `scp`, rule `SCOPE_products:read` sẽ không tự khớp.

Khi thay converter, hãy kiểm thử token thực tế hoặc JWT fixture. Không đổi tên scope trong OpenAPI chỉ để che giấu khác biệt mapping; hãy làm rõ hợp đồng giữa authorization server và resource server.

## 10. Ví dụ OpenAPI hoàn chỉnh cho nhiều operation

Ví dụ sau mô tả ba operation với scope khác nhau:

~~~yaml
openapi: 3.0.3
info:
  title: Product API
  version: 1.0.0
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://auth.example.com/oauth2/authorize
          tokenUrl: https://auth.example.com/oauth2/token
          scopes:
            products:read: Đọc thông tin sản phẩm
            products:write: Tạo và cập nhật sản phẩm
            products:delete: Xóa sản phẩm
paths:
  /api/products:
    get:
      summary: Đọc danh sách sản phẩm
      security:
        - oauth2:
            - products:read
      responses:
        '200':
          description: Danh sách sản phẩm
    post:
      summary: Tạo sản phẩm
      security:
        - oauth2:
            - products:write
      responses:
        '201':
          description: Sản phẩm đã được tạo
  /api/products/{id}:
    delete:
      summary: Xóa sản phẩm
      security:
        - oauth2:
            - products:delete
      responses:
        '204':
          description: Sản phẩm đã được xóa
        '403':
          description: Token không có scope cần thiết
~~~

Khi người tích hợp xem tài liệu:

- GET `/api/products` hiển thị yêu cầu `products:read`.
- POST `/api/products` hiển thị yêu cầu `products:write`.
- DELETE `/api/products/{id}` hiển thị yêu cầu `products:delete`.

Nếu operation có nhiều response, hãy mô tả cả lỗi xác thực và lỗi quyền theo hành vi thực tế. Response `403` không tự xuất hiện chỉ vì operation có scope; hãy khai báo response bằng annotation hoặc cấu hình response chung nếu API thực sự trả status này.

## 11. Kiểm tra scope trong tài liệu được sinh

Sau khi thêm annotation, gọi:

~~~http
GET /v3/api-docs
~~~

Trong JSON, kiểm tra hai vùng:

1. `components.securitySchemes.oauth2.flows.authorizationCode.scopes` chứa tên và mô tả scope.
2. `paths` của operation chứa `security` với đúng scheme và scope.

Ví dụ phần tài liệu mong đợi:

~~~json
{
  "components": {
    "securitySchemes": {
      "oauth2": {
        "type": "oauth2",
        "flows": {
          "authorizationCode": {
            "authorizationUrl": "https://auth.example.com/oauth2/authorize",
            "tokenUrl": "https://auth.example.com/oauth2/token",
            "scopes": {
              "products:read": "Đọc thông tin sản phẩm",
              "products:write": "Tạo và cập nhật sản phẩm"
            }
          }
        }
      }
    }
  },
  "paths": {
    "/api/products": {
      "get": {
        "security": [
          {
            "oauth2": [
              "products:read"
            ]
          }
        ]
      }
    }
  }
}
~~~

Tên scheme và scope phải khớp giữa components và operation. Nếu security requirement tham chiếu `oauth2` nhưng components chỉ có `oauth`, Swagger UI không thể liên kết đúng scheme.

### Kiểm thử bằng MockMvc

Có thể xác minh scope được mô tả trong `/v3/api-docs`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProductSecurityDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsProductReadScope() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$.components.securitySchemes.oauth2.flows.authorizationCode.scopes['products:read']"
            ).value("Đọc thông tin sản phẩm"))
            .andExpect(jsonPath(
                "$.paths['/api/products'].get.security[0].oauth2[0]"
            ).value("products:read"));
    }
}
~~~

JSONPath dùng bracket notation cho key có dấu hai chấm. Nếu tài liệu được chia group, gọi endpoint `/v3/api-docs/{group}` tương ứng và kiểm tra scope trong đúng group đó.

Các import chính cho test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

## 12. Kiểm thử quyền truy cập ở runtime

Kiểm thử tài liệu không thay thế kiểm thử authorization. Cần xác minh request có scope phù hợp được phép, request thiếu scope bị từ chối.

Với Spring Security Test và JWT request post-processor, một test có thể gán authority trực tiếp:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void allowsProductReadAuthority() throws Exception {
    mockMvc.perform(get("/api/products")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_products:read")
            )))
        .andExpect(status().isOk());
}

@Test
void deniesRequestWithoutProductReadAuthority() throws Exception {
    mockMvc.perform(get("/api/products")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read")
            )))
        .andExpect(status().isForbidden());
}
~~~

Ví dụ giả định endpoint được bảo vệ bởi `@PreAuthorize` hoặc URL authorization và test context đã cấu hình resource server. Cần import `spring-security-test`, `jwt()` từ `SecurityMockMvcRequestPostProcessors` và `SimpleGrantedAuthority`. Nếu endpoint dùng method security, bật `@EnableMethodSecurity` trong cấu hình được nạp bởi test.

Với URL authorization, hãy dùng đúng request matcher tương ứng. Nếu test dùng `@WebMvcTest`, import cấu hình bảo mật và mock service cần thiết; nếu dùng `@SpringBootTest`, nạp cấu hình ứng dụng đầy đủ.

Kiểm thử bằng authority trực tiếp xác minh rule Spring Security. Để xác minh mapping claim thực tế, bổ sung test cho `JwtAuthenticationConverter` hoặc dùng JWT fixture có claim `scope`/`scp` giống token do authorization server phát hành.

### Ma trận kiểm thử đề xuất

| Token/request | Kết quả mong đợi | Điều cần xác minh |
|---|---|---|
| Không có token | `401` | Resource server yêu cầu xác thực |
| Token hợp lệ có `products:read` | `200` với GET | Scope đọc được ánh xạ đúng |
| Token hợp lệ chỉ có `orders:read` | `403` với GET sản phẩm | Không cấp quyền chéo |
| Token hợp lệ có `products:write` | `201` với POST | Scope ghi được ánh xạ đúng |
| Token hợp lệ chỉ có `products:read` | `403` với POST | Scope đọc không cấp quyền ghi |
| Token có scope đúng nhưng khác tenant | Theo policy, thường `403` | Kiểm tra quyền tài nguyên/tenant riêng |

Mã status cụ thể còn phụ thuộc exception handler và cấu hình resource server. Hãy kiểm tra kết quả thực tế của ứng dụng rồi mô tả response tương ứng trong OpenAPI.

## 13. Lỗi thường gặp khi mô tả scope

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng tên scope làm tên security scheme | Swagger UI không tìm thấy scheme tương ứng | Khai báo scheme riêng như `oauth2`, scope là `products:read` |
| Operation yêu cầu scope chưa khai báo trong flow | Client không biết scope đó có ý nghĩa gì | Đồng bộ key trong `flows.*.scopes` và operation requirement |
| Đặt nhiều scope trong hai requirement object riêng khi muốn yêu cầu tất cả | OpenAPI hiểu là OR, client chỉ cần một phương án | Đặt các scope trong cùng requirement object |
| Đặt hai scope trong cùng object khi chỉ cần một trong hai | OpenAPI thể hiện yêu cầu cả hai | Tạo hai requirement object để biểu diễn OR |
| Đưa scope vào bearer scheme | Không đúng semantics scope của security scheme | Dùng OAuth2/OIDC scheme nếu muốn mô tả scope chuẩn |
| Chỉ khai báo scope trong OpenAPI | Tài liệu nói cần quyền nhưng server không kiểm tra | Cấu hình authorization ở resource server |
| Chỉ kiểm tra scope mà bỏ qua tenant/ownership | Token có quyền rộng có thể truy cập dữ liệu ngoài phạm vi | Kiểm tra quyền trên tài nguyên ở service/policy |
| Nhầm `security: []` với object rỗng | Operation công khai hoặc yêu cầu đăng nhập sai ý định | Dùng `[]` để bỏ security; `{}` để cho phép anonymous như một phương án |
| Dùng scope quá rộng | Client được cấp nhiều quyền hơn nhu cầu | Chia scope theo hành động nghiệp vụ và nguyên tắc quyền tối thiểu |
| Đổi tên scope mà không quản lý tương thích | Client cũ có thể bị 403 hoặc không xin được token | Có giai đoạn chuyển tiếp và cập nhật authorization server cùng client |
| Scope trong token không map thành `SCOPE_...` authority | Rule `hasAuthority` không khớp | Kiểm tra claim và cấu hình JwtAuthenticationConverter |
| Annotation class và method tạo kết quả khác dự kiến | Operation nhận security requirement không đúng | Kiểm tra JSON cuối cùng tại `/v3/api-docs` |

## 14. Quản lý thay đổi scope và tương thích API

Scope là một phần hợp đồng giữa client, authorization server và resource server. Thay đổi scope có thể ảnh hưởng đến client ngay cả khi URL và schema response không đổi.

### Thêm scope mới

Thêm scope mới thường tương thích nếu operation mới sử dụng scope đó và client hiện tại không cần gọi operation mới. Nếu gắn scope mới vào operation đang được sử dụng, client có thể cần xin token với quyền bổ sung.

Ví dụ operation trước đây chỉ yêu cầu `products:read`, sau đó yêu cầu đồng thời `products:read` và `inventory:read`. Đây là thay đổi làm tăng điều kiện truy cập; client cũ có thể nhận 403 dù token vẫn hợp lệ.

### Đổi tên hoặc xóa scope

Không đổi tên scope đang được client sử dụng mà không có kế hoạch chuyển tiếp. Một lộ trình có thể gồm:

1. Khai báo scope mới ở authorization server và OpenAPI.
2. Cho resource server tạm chấp nhận scope cũ và mới theo policy đã xác định.
3. Cập nhật client để xin scope mới.
4. Theo dõi token và client còn dùng scope cũ.
5. Chỉ xóa scope cũ sau khi hết thời gian tương thích và có kiểm chứng.

Không nên giữ scope cũ vô thời hạn nếu nó đại diện quyền rộng hoặc không còn đúng policy. Lộ trình cần có thời hạn và chủ sở hữu.

### Tăng quyền và giảm quyền

Thêm một scope vào requirement trong cùng object thường làm operation yêu cầu thêm quyền (AND). Thêm một requirement object mới có thể mở thêm phương án xác thực (OR), do đó thay đổi semantics theo hướng khác. Khi review OpenAPI diff, cần đọc cả cấu trúc collection, không chỉ so sánh số lượng scope.

Nếu giảm quyền được yêu cầu, hãy kiểm tra resource server có thực sự chấp nhận token ít scope hơn hay không. Không để tài liệu mô tả quyền tối thiểu nhưng code runtime vẫn yêu cầu scope cũ rộng hơn.

## 15. Quy trình đối chiếu tài liệu và runtime

Khi thêm hoặc thay scope cho một operation, thực hiện theo thứ tự:

1. Xác định hành động nghiệp vụ và client nào cần gọi operation.
2. Chọn scope đã tồn tại hoặc thiết kế scope mới theo nguyên tắc quyền tối thiểu.
3. Khai báo scope cùng mô tả trong OAuth2 flow hoặc xác minh scope OIDC do provider hỗ trợ.
4. Gắn scope vào operation bằng `@SecurityRequirement` hoặc OpenAPI YAML.
5. Cấu hình authorization server để có thể cấp scope cho đúng client/grant.
6. Cấu hình resource server chuyển claim scope thành authority.
7. Bảo vệ endpoint bằng URL authorization hoặc method security.
8. Kiểm tra quyền tài nguyên và tenant riêng nếu nghiệp vụ yêu cầu.
9. Gọi `/v3/api-docs` để xác minh scheme, scope và requirement.
10. Kiểm thử token có scope, thiếu scope, token không hợp lệ và trường hợp không có token.
11. Cập nhật response `401`/`403` trong OpenAPI nếu endpoint thực sự trả các status đó.
12. Đánh giá tương thích với client đang sử dụng trước khi phát hành.

## 16. Bài thực hành tổng hợp

Xây dựng mô tả bảo mật cho API quản lý sản phẩm và đơn hàng:

1. Định nghĩa OAuth2 authorization code flow tên `oauth2` với các scope `products:read`, `products:write`, `products:delete`, `orders:read` và `orders:cancel`.
2. Gắn `products:read` vào GET `/api/products`.
3. Gắn `products:write` vào POST và PUT `/api/products`.
4. Gắn `products:delete` vào DELETE `/api/products/{id}`.
5. Gắn `orders:read` vào GET `/api/orders`.
6. Gắn `orders:cancel` vào POST `/api/orders/{id}/cancel`.
7. Tạo một operation cần đồng thời `products:read` và `inventory:read`; biểu diễn cả hai scope trong cùng requirement object.
8. Tạo một operation chấp nhận OAuth2 `products:read` hoặc API key; kiểm tra hai requirement object được biểu diễn như OR.
9. Đặt security mặc định ở root và tạo health endpoint với `security: []`.
10. Dùng Spring Security để chuyển scope trong JWT thành authority và bảo vệ endpoint.
11. Viết test cho token đúng scope, token thiếu scope, token hết hạn hoặc không hợp lệ.
12. Kiểm tra `/v3/api-docs` để xác nhận scope description và security requirement của từng operation.
13. Đối chiếu OpenAPI với authorization server và rule runtime, sau đó sửa mọi khác biệt.

### Tiêu chí hoàn thành

- [ ] OAuth2 scheme có flow và danh sách scope được mô tả đầy đủ.
- [ ] Mỗi operation yêu cầu đúng scope theo hành động nghiệp vụ.
- [ ] Tên scope trong operation khớp chính xác scope được định nghĩa.
- [ ] Phân biệt đúng OR giữa requirement object và AND bên trong một object.
- [ ] Không gắn scope vào bearer/API key scheme theo cách sai semantics.
- [ ] Security mặc định và operation công khai được mô tả đúng.
- [ ] Spring Security thực thi cùng policy với OpenAPI.
- [ ] Token thiếu scope bị từ chối và token có scope phù hợp được phép.
- [ ] Quyền trên tenant/tài nguyên được kiểm tra ngoài scope khi cần.
- [ ] Có test xác minh `/v3/api-docs` và hành vi runtime.
- [ ] Thay đổi scope được đánh giá về tương thích với client hiện hữu.

## Tiếp tục học

Sau bài này, hãy kết hợp scope với OAuth2 flows, OpenID Connect discovery, JWT claim mapping và security requirement ở cấp root/operation. Khi thay đổi quyền của operation, hãy review đồng thời OpenAPI, cấu hình authorization server, resource server và test tích hợp để client nhận được hợp đồng chính xác.
