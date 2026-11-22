# OAuth2 và OpenID Connect như cơ chế được mô tả trong hợp đồng

API hiện đại thường yêu cầu client chứng minh quyền truy cập trước khi đọc hoặc thay đổi dữ liệu. OAuth 2.0 cung cấp cơ chế ủy quyền để client nhận access token và gửi token đó đến resource server. OpenID Connect (OIDC) bổ sung lớp xác thực danh tính trên OAuth 2.0, cho phép client nhận thông tin về người dùng đã đăng nhập.

Trong tài liệu OpenAPI, springdoc-openapi có thể mô tả các cơ chế này bằng security scheme và security requirement. Tài liệu cho biết API chấp nhận loại xác thực nào, authorization flow nào được hỗ trợ và operation yêu cầu scope gì. Swagger UI có thể dùng thông tin đó để hỗ trợ thử request qua nhà cung cấp danh tính.

Hợp đồng OpenAPI mô tả cách client tương tác với API. Nó không tự cấp token, xác thực chữ ký JWT, kiểm tra quyền hay cấu hình Spring Security. Các phần đó phải được triển khai ở authorization server và resource server.

## 1. OAuth2 và OpenID Connect giải quyết vấn đề gì?

OAuth 2.0 là framework ủy quyền. Thay vì chia sẻ mật khẩu của người dùng với mọi ứng dụng, client xin quyền truy cập thông qua authorization server và nhận access token. Client gửi token tới API; resource server xác minh token và quyết định request có được phép thực hiện hay không.

OIDC xây dựng trên OAuth 2.0 để chuẩn hóa việc xác thực người dùng. OIDC định nghĩa ID token cùng các endpoint và thông tin discovery để client biết danh tính người dùng và cách tương tác với OpenID Provider.

| Thành phần | Vai trò |
|---|---|
| Resource owner | Người dùng hoặc chủ thể có quyền đối với tài nguyên |
| Client | Ứng dụng yêu cầu quyền truy cập |
| Authorization server | Xác thực, cấp authorization code và token |
| Resource server | API bảo vệ dữ liệu, kiểm tra access token |
| OpenID Provider (OP) | Nhà cung cấp danh tính triển khai OIDC |
| Access token | Token client gửi tới API để chứng minh quyền truy cập |
| ID token | Token OIDC chứa thông tin xác thực về người dùng, dành cho client |

Một hệ thống có thể dùng cùng một nhà cung cấp cho authorization server và OpenID Provider. Tuy nhiên, vai trò của access token và ID token vẫn khác nhau.

## 2. Phân biệt OAuth2 với OIDC

OAuth2 trả lời câu hỏi: **client được phép truy cập tài nguyên nào?** OIDC trả lời thêm câu hỏi: **người dùng đã đăng nhập là ai?**

| Tiêu chí | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Mục đích chính | Ủy quyền truy cập tài nguyên | Xác thực danh tính người dùng trên nền OAuth 2.0 |
| Token thường gặp | Access token | ID token và access token |
| Scope ví dụ | products.read, orders.write | openid, profile, email và scope API |
| Metadata | Endpoint và cấu hình OAuth tùy nhà cung cấp | Discovery document chuẩn hóa |
| API sử dụng token | Thường nhận access token | Resource server vẫn sử dụng access token |
| Client đăng nhập | Có thể ủy quyền mà không cần biết danh tính người dùng | Có thể nhận danh tính qua ID token và UserInfo |

Không gửi ID token tới API như thể đó là access token. ID token được phát hành cho client và có audience của client; access token được phát hành để resource server kiểm tra quyền truy cập. API cần xác minh access token theo chính sách của authorization server.

OIDC không thay thế OAuth2. Một client OIDC vẫn sử dụng các flow OAuth2 để nhận token, đồng thời yêu cầu scope openid để kích hoạt ngữ nghĩa OpenID Connect.

## 3. Access token, ID token và scope

### 3.1. Access token

Access token đại diện cho quyền mà client được cấp. API thường nhận token qua HTTP Authorization header:

~~~http
GET /api/v1/products
Authorization: Bearer eyJhbGciOi...
~~~

Resource server xác minh token theo định dạng và chính sách đã thống nhất. Với JWT, các kiểm tra thường gồm chữ ký, issuer (iss), audience (aud), thời hạn (exp, nbf) và các claim cần thiết cho authorization. Nếu token là opaque token, resource server có thể cần introspection endpoint thay vì tự giải mã JWT.

Không nên ghi token thật vào ví dụ OpenAPI, log hoặc tài liệu. Dùng chuỗi minh họa đã che hoặc ví dụ giả.

### 3.2. ID token

ID token là bằng chứng xác thực danh tính do OpenID Provider phát hành cho client. ID token thường chứa các claim như:

- iss: issuer phát hành token.
- sub: định danh chủ thể tại issuer.
- aud: client được token hướng tới.
- exp: thời điểm hết hạn.
- iat: thời điểm phát hành.
- nonce: giá trị liên kết request đăng nhập với phản hồi, khi flow sử dụng nonce.

Client phải xác minh ID token theo OIDC, bao gồm chữ ký, issuer, audience và các kiểm tra thời gian; với request có nonce, phải đối chiếu nonce. API không nên dùng ID token thay cho access token chỉ vì cả hai đều có thể là JWT.

### 3.3. Scope

Scope giới hạn quyền được cấp. Ví dụ:

| Scope | Ý nghĩa nghiệp vụ |
|---|---|
| products.read | Đọc danh sách và chi tiết sản phẩm |
| products.write | Tạo hoặc cập nhật sản phẩm |
| orders.read | Đọc đơn hàng |
| orders.write | Tạo hoặc thay đổi đơn hàng |
| openid | Yêu cầu ngữ nghĩa xác thực OIDC |
| profile | Yêu cầu một số claim hồ sơ chuẩn |
| email | Yêu cầu thông tin email theo OIDC |

Scope là chuỗi do authorization server và API thống nhất. Tên scope có phân biệt chữ hoa/chữ thường theo quy tắc OAuth; hãy giữ tên ổn định giữa cấu hình cấp token, kiểm tra quyền và tài liệu OpenAPI.

## 4. Các OAuth2 flow thường dùng

OAuth 2.0 có nhiều grant type, nhưng không phải flow nào cũng phù hợp với ứng dụng hiện đại.

| Flow | Trường hợp sử dụng | Đặc điểm |
|---|---|---|
| Authorization Code + PKCE | Ứng dụng web, SPA, mobile hoặc client có tương tác người dùng | Người dùng đăng nhập tại authorization server; client đổi code lấy token |
| Client Credentials | Giao tiếp service-to-service | Client xác thực bằng danh tính ứng dụng, không đại diện cho người dùng cuối |
| Device Authorization | Thiết bị có giao diện nhập liệu hạn chế | Thiết bị hiển thị mã để người dùng hoàn tất xác thực ở thiết bị khác |
| Refresh token | Xin access token mới khi token cũ hết hạn | Là cơ chế cấp token tiếp theo, không phải một flow độc lập trong OpenAPI |

OpenAPI OAuth2 flows có các trường chuẩn implicit, password, clientCredentials và authorizationCode. Device Authorization không có field flow riêng trong mô hình OAuth2 của OpenAPI; nếu API sử dụng flow này, cần mô tả cách lấy token trong phần hướng dẫn tích hợp.

Implicit flow không còn được khuyến nghị cho ứng dụng mới. Resource Owner Password Credentials (password grant) cũng không nên dùng; hướng dẫn bảo mật OAuth hiện đại khuyến nghị Authorization Code với PKCE cho client tương tác. Không đưa password flow vào hợp đồng mới chỉ vì annotation hoặc OpenAPI vẫn có thể biểu diễn nó.

## 5. Authorization Code với PKCE

Đây là lựa chọn thường dùng cho ứng dụng có người dùng đăng nhập, đặc biệt là SPA và ứng dụng mobile. PKCE bổ sung cơ chế chứng minh client đang đổi authorization code chính là client đã khởi tạo request, giảm nguy cơ code bị đánh cắp và sử dụng lại.

Luồng khái quát:

~~~text
Client                 Authorization Server             Resource API
  |                              |                            |
  |-- authorize + code_challenge>|                            |
  |<-- user authenticates -------|                            |
  |<-- authorization code -------|                            |
  |                              |                            |
  |-- code + code_verifier ----->|                            |
  |<-- access token / ID token --|                            |
  |                                                           |
  |---------------- access token ---------------------------->|
  |<--------------- protected API response ------------------|
~~~

Các điểm cần thống nhất:

- Authorization URL là endpoint nơi client chuyển người dùng tới để cấp quyền.
- Token URL là endpoint nơi client đổi authorization code lấy token.
- Redirect URI phải được đăng ký chính xác với authorization server.
- Client tạo code_verifier ngẫu nhiên và gửi code_challenge tương ứng trong authorization request.
- Token request gửi lại code_verifier để authorization server kiểm tra.
- Với OIDC, client yêu cầu scope openid; có thể yêu cầu thêm profile hoặc email nếu cần.

PKCE là yêu cầu của flow và cấu hình client/authorization server. OpenAPI OAuth2 flow mô tả authorization URL, token URL và scopes, nhưng không có thuộc tính chuẩn riêng để đánh dấu code_challenge_method=S256. Hãy ghi rõ yêu cầu PKCE trong mô tả tích hợp và cấu hình Swagger UI tương ứng.

## 6. Client Credentials cho service-to-service

Client Credentials phù hợp khi một dịch vụ gọi API bằng danh tính của chính ứng dụng, không có người dùng tương tác:

~~~text
Backend Service                Authorization Server           Resource API
      |                                  |                          |
      |-- client authentication ------->|                          |
      |<-- access token ----------------|                          |
      |                                                             |
      |---------------- access token ------------------------------>|
      |<--------------- API response -------------------------------|
~~~

Client xác thực bằng cơ chế đã đăng ký, chẳng hạn client secret hoặc private key. Không nhúng client secret vào ứng dụng trình duyệt hoặc mobile vì người dùng có thể trích xuất được. Với workload production, cân nhắc cơ chế xác thực client mạnh hơn theo khả năng của authorization server.

Token Client Credentials thường đại diện cho ứng dụng, vì vậy quyền được cấp cần gắn với service account, client hoặc policy tương ứng. Không giả định token này có danh tính người dùng cuối.

## 7. Khai báo OAuth2 Security Scheme trong OpenAPI

Trong OpenAPI, OAuth2 được mô tả bằng security scheme có type oauth2. Mỗi flow khai báo endpoint và các scope được hỗ trợ. Springdoc có thể sinh mô hình này từ annotation của Swagger:

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
            authorizationUrl = "https://id.example.com/oauth2/authorize",
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products.read",
                    description = "Đọc thông tin sản phẩm."
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Tạo và cập nhật đơn hàng."
                )
            }
        )
    )
)
public class OAuth2OpenApiConfiguration {
}
~~~

Các giá trị URL trong ví dụ là địa chỉ minh họa. Thay bằng endpoint chính thức của authorization server đang sử dụng. Tên oauth2 là khóa định danh của scheme trong OpenAPI; security requirement phải tham chiếu đúng tên này.

Nếu ứng dụng chỉ dùng Client Credentials, khai báo flow tương ứng:

~~~java
@SecurityScheme(
    name = "serviceOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products.read",
                    description = "Đọc dữ liệu sản phẩm."
                )
            }
        )
    )
)
~~~

Không khai báo flow mà hệ thống không thực sự hỗ trợ. Nếu authorization server có nhiều flow, chỉ mô tả những flow client được phép sử dụng cho API đó.

## 8. Khai báo OpenID Connect Security Scheme

OpenAPI có security scheme riêng cho OpenID Connect với type openIdConnect. Scheme này trỏ tới discovery document của OpenID Provider:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "oidc",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://id.example.com/.well-known/openid-configuration"
)
public class OidcOpenApiConfiguration {
}
~~~

openIdConnectUrl phải trỏ tới OpenID Provider Configuration Document, thường có đường dẫn /.well-known/openid-configuration. Đây là tài liệu discovery chứa metadata như issuer, authorization endpoint, token endpoint, UserInfo endpoint và JWKS URI. Không dùng trực tiếp JWKS URI thay cho discovery URL.

Discovery document giúp client biết các endpoint và khả năng của provider. Nó không thay thế bước xác minh token tại API. Resource server vẫn phải xác minh access token theo issuer, audience, chữ ký và các claim cần thiết.

## 9. Chọn OAuth2 scheme hay OpenID Connect scheme?

Nếu API cần mô tả rõ từng OAuth2 flow và scope, type oauth2 là lựa chọn trực tiếp. Nếu hợp đồng muốn tham chiếu cấu hình OIDC discovery của provider, có thể dùng type openIdConnect.

| Nhu cầu | Security scheme phù hợp |
|---|---|
| Công bố authorization code, token URL và scopes cụ thể | OAuth2 |
| Công bố client credentials và scopes | OAuth2 |
| Tham chiếu OIDC discovery document | OpenID Connect |
| Chỉ dùng Bearer JWT mà không mô tả OAuth flow | HTTP Bearer |

Không cần khai báo đồng thời nhiều scheme cho cùng một cơ chế nếu điều đó khiến client hiểu rằng họ phải chọn giữa các phương án không tồn tại. Chọn cách biểu diễn phản ánh đúng cách client nhận token và API kiểm tra token.

Một API có thể dùng OAuth2 để mô tả quyền truy cập và OIDC cho đăng nhập ở client. Tuy nhiên, ID token vẫn dành cho client; API bảo vệ resource bằng access token.

## 10. Yêu cầu scope cho từng operation

Khai báo security scheme mới chỉ định nghĩa cơ chế xác thực. Để nói operation nào cần scope nào, phải thêm security requirement.

Ví dụ operation chỉ đọc sản phẩm:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/v1/products")
@Operation(
    summary = "Liệt kê sản phẩm",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"products.read"}
    )
)
public List<ProductResponse> listProducts() {
    return productService.findAll();
}
~~~

Ví dụ operation tạo đơn hàng:

~~~java
@PostMapping("/api/v1/orders")
@Operation(
    summary = "Tạo đơn hàng",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.write"}
    )
)
public OrderResponse createOrder(
        @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Tên scope trong requirement phải tồn tại trong flow của scheme OAuth2. Scope không được khai báo hoặc sai chính tả có thể làm tài liệu gây hiểu nhầm và một số công cụ có thể cảnh báo.

Với OIDC scheme, requirement cũng có thể liệt kê các scope OIDC như openid hoặc profile nếu đó là scope client cần yêu cầu. Scope OIDC phục vụ yêu cầu danh tính; scope nghiệp vụ của API vẫn cần được authorization server và resource server thống nhất.

## 11. Security requirement toàn tài liệu và theo operation

Có thể đặt security requirement ở cấp tài liệu để áp dụng mặc định cho mọi operation. Trong annotation, có thể khai báo qua @OpenAPIDefinition:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;

@OpenAPIDefinition(
    security = {
        @SecurityRequirement(
            name = "oauth2",
            scopes = {"products.read"}
        )
    }
)
public class ApiOpenApiDefinition {
}
~~~

Requirement toàn cục phù hợp khi mọi operation trong tài liệu cùng có chính sách bảo vệ. Nếu API có cả endpoint public và protected, nên mô tả security theo operation để tránh áp dụng nhầm.

Trong OpenAPI, security requirement cấp operation ghi đè requirement cấp tài liệu. Một security array có nhiều object biểu diễn các phương án thay thế (OR); nhiều scheme trong cùng một object biểu diễn các điều kiện phải đồng thời đáp ứng (AND). Cần hiểu ngữ nghĩa này khi một operation chấp nhận OAuth2 hoặc API key, hoặc yêu cầu đồng thời nhiều cơ chế.

Nếu một endpoint public nằm trong tài liệu có security toàn cục, OpenAPI biểu diễn ngoại lệ bằng security requirement rỗng ở operation đó. Hãy kiểm tra JSON cuối cùng để chắc chắn công cụ annotation hoặc customizer đã tạo đúng mảng security rỗng.

## 12. Mô tả OAuth2 và OIDC trong YAML OpenAPI

Đặc tả rút gọn dưới đây minh họa cả hai loại scheme:

~~~yaml
openapi: 3.0.3
info:
  title: Store API
  version: 1.0.0
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://id.example.com/oauth2/authorize
          tokenUrl: https://id.example.com/oauth2/token
          scopes:
            products.read: Đọc thông tin sản phẩm.
            orders.write: Tạo và cập nhật đơn hàng.
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://id.example.com/.well-known/openid-configuration
paths:
  /api/v1/products:
    get:
      summary: Liệt kê sản phẩm
      security:
        - oauth2:
            - products.read
      responses:
        '200':
          description: Danh sách sản phẩm.
  /api/v1/profile:
    get:
      summary: Lấy hồ sơ người dùng hiện tại
      security:
        - oidc:
            - openid
            - profile
      responses:
        '200':
          description: Hồ sơ người dùng.
~~~

Đây là ví dụ về cấu trúc tài liệu. Khi dùng một scheme OIDC, client cần tham chiếu discovery document chính xác. Khi dùng OAuth2, flow phải phản ánh flow thực tế của authorization server. Không sao chép URL mẫu vào môi trường production.

## 13. Cấu hình Swagger UI cho Authorization Code và PKCE

Swagger UI có thể khởi tạo OAuth authorization flow để người tích hợp thử API. Với Authorization Code + PKCE, cấu hình client ID và bật PKCE:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: store-swagger-ui
      use-pkce-with-authorization-code-grant: true
~~~

Client ID phải được đăng ký ở authorization server. Redirect URI của Swagger UI cũng phải được đăng ký chính xác; URI mặc định thường nằm dưới đường dẫn swagger-ui/oauth2-redirect.html, nhưng có thể thay đổi theo context path hoặc cấu hình UI.

Không cấu hình client secret trong Swagger UI cho SPA hoặc ứng dụng trình duyệt. Mã JavaScript và cấu hình được gửi tới trình duyệt nên secret không thể được giữ bí mật. Nếu cần client secret, hãy dùng confidential client chạy ở backend và thiết kế flow phù hợp.

Một số cấu hình Swagger UI khác có thể được cung cấp qua springdoc.swagger-ui.oauth, nhưng tên và hành vi thuộc tính cần được xác minh theo phiên bản springdoc đang cài. Chỉ công bố client ID và các thông tin được phép xuất hiện ở phía trình duyệt.

## 14. Cấu hình Swagger UI cho Client Credentials

Swagger UI hỗ trợ nhập thông tin OAuth2 để lấy token theo flow đã mô tả. Tuy nhiên, Client Credentials thường yêu cầu client authentication. Nếu nhập client secret vào giao diện chạy trên trình duyệt, secret sẽ lộ cho người sử dụng và có thể bị trích xuất.

Với tài liệu dành cho đối tác hoặc nhân viên kỹ thuật, có thể dùng Swagger UI để xem flow và scope. Việc thực hiện Client Credentials nên dùng một công cụ hoặc backend có thể bảo vệ credential. Không bật client secret trên trang Swagger UI public.

Nếu tổ chức dùng private_key_jwt, mutual TLS hoặc cơ chế xác thực client khác, cần mô tả rõ yêu cầu đó trong tài liệu tích hợp vì cấu hình OAuth2 flow cơ bản không thể diễn đạt mọi chi tiết triển khai của authorization server.

## 15. Liên hệ với Spring Security Resource Server

Spring Security Resource Server là phần thực thi việc bảo vệ endpoint bằng bearer token. Ví dụ cấu hình JWT thường dùng issuer URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
~~~

Spring Security có thể dùng issuer metadata để tìm khóa xác minh và kiểm tra issuer. Ứng dụng vẫn cần xác định audience, scope, role và các điều kiện authorization phù hợp với hệ thống.

Ví dụ kiểm tra scope trong cấu hình authorization:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/api/v1/products/**")
        .hasAuthority("SCOPE_products.read")
    .requestMatchers(HttpMethod.POST, "/api/v1/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyRequest().authenticated()
);
~~~

Với JWT resource server, Spring Security thường ánh xạ scope thành authority có tiền tố SCOPE_. Quy tắc trên chỉ là ví dụ; cần cấu hình authentication, CSRF, CORS, session và các matcher khác theo ứng dụng.

Metadata OpenAPI và cấu hình Spring Security phải khớp nhau. Nếu tài liệu nói operation cần orders.write nhưng runtime chỉ kiểm tra orders.read, client sẽ nhận hợp đồng sai. Ngược lại, nếu runtime yêu cầu scope mà tài liệu không mô tả, người tích hợp khó gọi API đúng.

## 16. Discovery, issuer và JWKS

OIDC Discovery cung cấp metadata cho client. Một discovery document thường công bố:

- issuer: định danh OpenID Provider.
- authorization_endpoint: nơi bắt đầu authorization request.
- token_endpoint: nơi đổi code lấy token.
- userinfo_endpoint: endpoint lấy thông tin người dùng.
- jwks_uri: nơi tải JSON Web Key Set để xác minh chữ ký token.
- scopes_supported: các scope provider hỗ trợ.
- response_types_supported và grant_types_supported: các loại response và grant.

Resource server dùng issuer metadata hoặc cấu hình tương đương để tìm khóa công khai tại JWKS URI. Khi khóa được xoay vòng, thư viện xác minh token cần cập nhật JWKS theo cơ chế phù hợp.

Issuer trong cấu hình phải khớp claim iss của token theo chính sách provider. Không chỉ kiểm tra chữ ký; một JWT có chữ ký hợp lệ nhưng phát hành bởi issuer không tin cậy hoặc dành cho audience khác vẫn phải bị từ chối.

OpenAPI openIdConnectUrl trỏ tới discovery document. OAuth2 authorizationUrl và tokenUrl trỏ trực tiếp tới endpoint tương ứng. Hai kiểu URL này có vai trò khác nhau.

## 17. Phân biệt scope, role và claim

Scope thường mô tả quyền mà client được cấp theo hợp đồng OAuth. Role thường biểu diễn vai trò nghiệp vụ của người dùng hoặc service. Claim là thuộc tính được mang trong token.

Ví dụ access token có thể chứa:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-123",
  "aud": ["store-api"],
  "scope": "products.read orders.write",
  "roles": ["ORDER_MANAGER"],
  "exp": 1920000000
}
~~~

Đây là payload minh họa, không phải token có thể sử dụng. products.read và orders.write là scope; ORDER_MANAGER là role; sub và aud là claim chuẩn hoặc claim theo ngữ cảnh token.

OpenAPI OAuth2 security requirement phù hợp để mô tả scope. Nếu API còn kiểm tra role hoặc claim tùy chỉnh, hãy mô tả điều kiện nghiệp vụ trong description hoặc tài liệu bảo mật bổ sung. Không cố biểu diễn mọi policy nội bộ thành OAuth scope nếu authorization server không cấp các scope đó.

## 18. Các lỗi thường gặp khi mô tả OAuth2/OIDC

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng ID token để gọi resource API | Audience hoặc mục đích token không phù hợp | Gửi access token tới resource server |
| Chỉ khai báo security scheme mà không thêm requirement | Operation không thể hiện rõ yêu cầu xác thực | Gắn security requirement ở cấp tài liệu hoặc operation |
| Requirement tham chiếu sai tên scheme | Tài liệu không liên kết được cơ chế xác thực | Dùng tên trùng với SecurityScheme name |
| Scope trong requirement không tồn tại trong flow | Tài liệu và authorization server không thống nhất | Đồng bộ danh sách scope |
| Dùng password grant cho ứng dụng mới | Tăng rủi ro lộ thông tin xác thực người dùng | Dùng Authorization Code + PKCE |
| Bật PKCE trong Swagger UI nhưng không đăng ký redirect URI | Authorization server từ chối callback | Đăng ký chính xác redirect URI |
| Đưa client secret vào trình duyệt | Secret có thể bị người dùng trích xuất | Dùng public client với PKCE hoặc confidential backend |
| Dùng JWKS URL làm openIdConnectUrl | Client không lấy được discovery metadata | Dùng OpenID Provider Configuration URL |
| Nghĩ OpenAPI security thay thế Spring Security | Endpoint runtime vẫn có thể không được bảo vệ | Cấu hình và kiểm thử Resource Server |
| Chỉ kiểm tra chữ ký JWT | Token sai issuer hoặc audience vẫn có thể được chấp nhận | Xác minh issuer, audience, thời hạn và policy |
| Mô tả OAuth flow không được provider hỗ trợ | Swagger UI tạo request không hợp lệ | Chỉ công bố flow thực tế được cấp phép |

## 19. Kiểm tra tài liệu và hành vi bảo mật

Sau khi chạy ứng dụng, mở tài liệu OpenAPI:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Kiểm tra:

1. components.securitySchemes có scheme OAuth2 hoặc OpenID Connect đúng loại.
2. OAuth2 flow có authorization URL, token URL và scope phù hợp.
3. OIDC scheme trỏ tới discovery document, không trỏ nhầm tới JWKS.
4. Mỗi operation có security requirement và scope chính xác.
5. Operation public không bị áp security requirement ngoài ý muốn.
6. Swagger UI dùng client ID, PKCE và redirect URI đúng cấu hình.
7. Tài liệu không chứa client secret, access token hoặc dữ liệu nhạy cảm.

Tiếp theo, kiểm thử runtime:

- Không có token: endpoint được bảo vệ phải từ chối request.
- Token sai chữ ký, issuer hoặc audience: resource server phải từ chối.
- Token hết hạn: request phải bị từ chối.
- Token thiếu scope: API phải trả lỗi authorization phù hợp.
- Token đủ scope: client được phép thực hiện operation tương ứng.
- Endpoint public: hoạt động theo chính sách công khai đã công bố.

Kiểm thử tài liệu và kiểm thử runtime là hai việc riêng. Cả hai cần đạt để hợp đồng OAuth2/OIDC phản ánh đúng hệ thống.

## 20. Ghi nhớ

- OAuth2 là framework ủy quyền; OIDC bổ sung xác thực danh tính người dùng.
- Access token dành cho resource API; ID token dành cho client OIDC.
- Scope mô tả quyền được cấp và có thể khai báo trong OAuth2 security scheme.
- Authorization Code + PKCE phù hợp với client tương tác; Client Credentials phù hợp cho service-to-service.
- Không dùng Implicit hoặc Resource Owner Password Credentials cho thiết kế mới.
- OpenAPI mô tả OAuth2 bằng type oauth2 và flows; OIDC dùng type openIdConnect cùng discovery URL.
- Security scheme định nghĩa cơ chế; security requirement gắn cơ chế và scope vào operation.
- Swagger UI có thể hỗ trợ authorization flow, nhưng không được chứa client secret của public client.
- openIdConnectUrl là discovery document; jwks_uri là địa chỉ khóa xác minh token.
- OpenAPI không cấu hình authorization server hoặc Spring Security Resource Server.
- Luôn đối chiếu scope, issuer, audience, token validation và policy runtime với tài liệu.

Khi mô tả OAuth2 và OpenID Connect bằng springdoc-openapi, hãy công bố đúng flow, endpoint, scope và security requirement mà client cần dùng. Phân biệt access token với ID token, bảo vệ credential của client và xác minh tài liệu sinh ra cùng hành vi Spring Security để hợp đồng tích hợp đáng tin cậy.
