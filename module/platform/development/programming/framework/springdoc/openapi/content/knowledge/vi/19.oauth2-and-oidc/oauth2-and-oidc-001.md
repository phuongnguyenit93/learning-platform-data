# OAuth Flows Object và các URL thuộc cấu hình mô tả

OpenAPI mô tả OAuth2 bằng một **OAuth Flows Object**. Đối tượng này cho biết API hỗ trợ flow nào và các URL của authorization server được dùng trong flow đó. Với Springdoc, khai báo này thường được tạo bằng `@SecurityScheme`, `@OAuthFlows` và `@OAuthFlow`.

Ba URL thường gặp có vai trò khác nhau: `authorizationUrl` đưa người dùng đến authorization endpoint, `tokenUrl` là nơi client đổi authorization code hoặc thông tin grant lấy token, còn `refreshUrl` mô tả URL được dùng trong quá trình trao đổi refresh token theo flow mà nhà cung cấp hỗ trợ. Các URL này thuộc cấu hình mô tả OAuth2, không phải URL gốc của REST API.

## 1. OAuth Flows Object là gì?

Trong OpenAPI 3, OAuth2 security scheme chứa thuộc tính `flows`. Đây là một OAuth Flows Object, có thể mô tả một hoặc nhiều flow mà API hỗ trợ.

Các flow được định nghĩa bằng những key sau:

| Flow | Mục đích | URL quan trọng |
| --- | --- | --- |
| `implicit` | Flow cũ đưa access token trực tiếp qua authorization response | `authorizationUrl` |
| `password` | Client gửi thông tin đăng nhập của người dùng đến token endpoint | `tokenUrl` |
| `clientCredentials` | Ứng dụng xác thực bằng thông tin của chính client | `tokenUrl` |
| `authorizationCode` | Người dùng cấp quyền, client nhận code rồi đổi code lấy token | `authorizationUrl`, `tokenUrl` |

Mỗi flow là một OAuth Flow Object. Object này có thể chứa:

- `authorizationUrl`: URL của authorization endpoint.
- `tokenUrl`: URL của token endpoint.
- `refreshUrl`: URL dùng trong quá trình lấy/làm mới token bằng refresh token, nếu được mô tả riêng.
- `scopes`: danh sách scope mà flow hỗ trợ, kèm mô tả cho từng scope.

Trong Java annotation, `@OAuthFlows` chứa các thuộc tính tương ứng với tên flow: `implicit`, `password`, `clientCredentials` và `authorizationCode`. Mỗi thuộc tính nhận một `@OAuthFlow`.

## 2. Phân biệt các URL OAuth2

| Thuộc tính | Vai trò | Ví dụ đường dẫn |
| --- | --- | --- |
| `authorizationUrl` | Trình duyệt hoặc user-agent chuyển người dùng đến đây để bắt đầu cấp quyền | `https://identity.example.com/oauth2/authorize` |
| `tokenUrl` | Client gửi grant để nhận access token; có thể dùng cho authorization code, client credentials hoặc refresh grant theo cấu hình nhà cung cấp | `https://identity.example.com/oauth2/token` |
| `refreshUrl` | URL dùng cho quá trình trao đổi refresh token khi nhà cung cấp công bố endpoint phù hợp | `https://identity.example.com/oauth2/refresh` |

Các URL này thường thuộc identity provider hoặc authorization server. Ví dụ, `https://api.example.com` có thể là REST API server, trong khi `https://identity.example.com/oauth2/authorize` và `/oauth2/token` là endpoint OAuth2.

Không đặt URL của controller Spring MVC vào `authorizationUrl` hoặc `tokenUrl`. Những endpoint đó không nhận request nghiệp vụ như `/api/books`; chúng thực hiện quy trình cấp token.

## 3. Trường nào bắt buộc trong từng flow?

Theo cấu trúc OAuth2 Flow Object của OpenAPI:

| Flow | `authorizationUrl` | `tokenUrl` | `refreshUrl` |
| --- | --- | --- | --- |
| `implicit` | Bắt buộc | Không dùng | Tùy chọn |
| `password` | Không dùng | Bắt buộc | Tùy chọn |
| `clientCredentials` | Không dùng | Bắt buộc | Tùy chọn |
| `authorizationCode` | Bắt buộc | Bắt buộc | Tùy chọn |

`refreshUrl` là tùy chọn. Nếu authorization server dùng chính token endpoint để xử lý refresh token grant, tài liệu có thể không cần một URL refresh riêng; nếu nhà cung cấp có endpoint refresh riêng thì mô tả URL đó. Ý nghĩa và cách dùng cụ thể của endpoint refresh phụ thuộc hợp đồng của provider. Hãy theo tài liệu chính thức của identity provider, không tự suy ra đường dẫn từ tên flow.

Không khai báo một URL giả chỉ để làm đầy annotation. Flow phải phản ánh endpoint mà authorization server thực sự cung cấp.

## 4. Khai báo authorization code flow bằng Springdoc

Authorization Code là lựa chọn phổ biến cho ứng dụng có người dùng đăng nhập. Với ứng dụng public client như SPA hoặc ứng dụng di động, nên sử dụng PKCE theo cấu hình của authorization server.

Ví dụ cấu hình Spring Boot 3 và Springdoc 2.x:

```java
package com.example.config;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.Scopes;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Books API", version = "1.0.0")
)
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    description = "OAuth2 Authorization Code flow",
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            refreshUrl = "https://identity.example.com/oauth2/refresh",
            scopes = @Scopes({
                @OAuthScope(name = "books:read", description = "Đọc thông tin sách"),
                @OAuthScope(name = "books:write", description = "Tạo và cập nhật sách")
            })
        )
    )
)
public class OpenApiOAuthConfig {}
```

Trong ví dụ, `authorizationUrl` và `tokenUrl` là hai endpoint bắt buộc của Authorization Code flow. `refreshUrl` được khai báo vì ví dụ giả định nhà cung cấp có endpoint refresh riêng. Nếu hệ thống dùng token endpoint chung cho refresh grant, hãy điều chỉnh theo hợp đồng của nhà cung cấp.

`@OAuthScope` tạo từng scope cùng mô tả. `@Scopes` gom chúng thành danh sách scope cho flow. Tên scope phải khớp với scope mà authorization server và API thực sự hỗ trợ.

## 5. Gắn security requirement và scope vào operation

Sau khi định nghĩa scheme, operation tham chiếu tên scheme bằng `@SecurityRequirement`:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookController {

    @GetMapping("/api/books")
    @Operation(
        summary = "Liệt kê sách",
        security = @SecurityRequirement(
            name = "oauth2",
            scopes = {"books:read"}
        )
    )
    public String listBooks() {
        return "books";
    }
}
```

Tên `oauth2` trong requirement phải khớp với `name = "oauth2"` trong `@SecurityScheme`. Scope `books:read` phải tồn tại trong `scopes` của flow tương ứng. Nếu tên scheme hoặc scope khác nhau, tài liệu có thể tham chiếu đến cấu hình không tồn tại hoặc khiến Swagger UI/client generator hiểu sai quyền cần cấp.

Requirement chỉ mô tả quyền mà operation yêu cầu. Spring Security hoặc resource server vẫn phải xác minh access token và kiểm tra authority/scope khi request đến ứng dụng.

## 6. Mô tả client credentials flow

Client Credentials thường dùng cho giao tiếp service-to-service khi không có người dùng cuối tham gia trực tiếp. Flow này cần `tokenUrl`, không cần `authorizationUrl`:

```java
@SecurityScheme(
    name = "serviceOAuth",
    type = SecuritySchemeType.OAUTH2,
    description = "OAuth2 Client Credentials cho tích hợp hệ thống",
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "inventory:read", description = "Đọc tồn kho"),
                @OAuthScope(name = "inventory:sync", description = "Đồng bộ tồn kho")
            })
        )
    )
)
```

Operation có thể tham chiếu scheme và scope:

```java
@Operation(
    summary = "Đọc tồn kho",
    security = @SecurityRequirement(
        name = "serviceOAuth",
        scopes = {"inventory:read"}
    )
)
```

`clientCredentials` không có bước chuyển người dùng đến authorization endpoint. Client gửi thông tin xác thực của chính nó đến token endpoint theo cấu hình của authorization server.

Không đưa `client_id`, `client_secret` thật vào annotation, OpenAPI example hoặc tài liệu. Các giá trị bí mật phải được quản lý bằng secret store hoặc cấu hình bảo mật của môi trường chạy.

## 7. Password và implicit flow trong tài liệu hiện đại

OpenAPI vẫn định nghĩa `password` và `implicit` để mô tả hệ thống OAuth2 cũ:

```java
@SecurityScheme(
    name = "legacyPasswordOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        password = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "profile:read", description = "Đọc hồ sơ")
            })
        )
    )
)
```

Implicit flow chỉ cần `authorizationUrl`:

```java
@SecurityScheme(
    name = "legacyImplicitOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        implicit = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            scopes = @Scopes({
                @OAuthScope(name = "profile:read", description = "Đọc hồ sơ")
            })
        )
    )
)
```

Đây là ví dụ để nhận diện cấu trúc OpenAPI, không phải khuyến nghị dùng cho thiết kế mới. Resource Owner Password Credentials (password grant) và Implicit flow không còn được khuyến nghị cho ứng dụng mới; ưu tiên Authorization Code với PKCE cho ứng dụng có người dùng và Client Credentials cho giao tiếp giữa các dịch vụ.

Nếu hệ thống hiện tại vẫn hỗ trợ hai flow cũ, tài liệu nên mô tả đúng trạng thái thực tế và có kế hoạch chuyển đổi. Không công bố một flow chỉ vì annotation cho phép khai báo nó.

## 8. Nhiều flow trong cùng một OAuth2 scheme

OAuth Flows Object có thể chứa nhiều flow nếu authorization server và API thực sự hỗ trợ chúng. Ví dụ một scheme mô tả Authorization Code cho người dùng và Client Credentials cho service:

```java
@SecurityScheme(
    name = "platformOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://identity.example.com/oauth2/authorize",
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "orders:read", description = "Đọc đơn hàng")
            })
        ),
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://identity.example.com/oauth2/token",
            scopes = @Scopes({
                @OAuthScope(name = "orders:sync", description = "Đồng bộ đơn hàng")
            })
        )
    )
)
```

Trong ví dụ, hai flow dùng chung token endpoint nhưng có mục đích và tập scope khác nhau. Không phải mọi identity provider đều bật cả hai flow cho cùng một client; cần cấu hình client và quyền tương ứng tại authorization server.

Nếu hai loại client có chính sách, audience hoặc endpoint hoàn toàn khác nhau, có thể tách thành hai security scheme riêng để Swagger UI và client generator thể hiện rõ lựa chọn.

## 9. OpenAPI YAML được sinh ra như thế nào?

Từ annotation ở trên, Springdoc tạo một cấu trúc tương tự:

```yaml
components:
  securitySchemes:
    oauth2:
      type: oauth2
      description: OAuth2 Authorization Code flow
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          refreshUrl: https://identity.example.com/oauth2/refresh
          scopes:
            books:read: Đọc thông tin sách
            books:write: Tạo và cập nhật sách
paths:
  /api/books:
    get:
      security:
        - oauth2:
            - books:read
```

Điểm cần kiểm tra:

1. Scheme nằm dưới `components.securitySchemes` và có `type: oauth2`.
2. Flow được đặt đúng key, ví dụ `authorizationCode` hoặc `clientCredentials`.
3. Các URL xuất hiện đúng trường và đúng endpoint.
4. `scopes` là map tên scope sang mô tả.
5. Security requirement tham chiếu đúng tên scheme và scope.

Đây là ví dụ rút gọn; tài liệu thực tế còn chứa `info`, `servers`, paths và response của API.

## 10. Phân biệt OAuth flow URL với API server URL

OpenAPI có thuộc tính `servers` để mô tả base URL của API. Các URL OAuth2 nằm trong flow object và trỏ đến authorization server. Hai nhóm URL không thay thế nhau:

```yaml
servers:
  - url: https://api.example.com
components:
  securitySchemes:
    oauth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes: {}
```

- `servers.url` là địa chỉ gốc mà client gọi operation như `/api/books`.
- `authorizationUrl` là nơi bắt đầu quy trình cấp quyền.
- `tokenUrl` là nơi đổi grant lấy token.
- `refreshUrl` là URL refresh riêng nếu được authorization server công bố.

Nếu thay đổi môi trường từ staging sang production, có thể cả API server lẫn OAuth endpoints đều thay đổi. Hãy cấu hình và kiểm tra từng nhóm URL riêng biệt.

## 11. Phân biệt `authorizationUrl` với redirect/callback URL

`authorizationUrl` là endpoint của authorization server mà browser điều hướng đến để bắt đầu cấp quyền. `redirect_uri` là địa chỉ callback của client, nơi authorization server chuyển người dùng trở lại cùng authorization code hoặc kết quả tương ứng.

Redirect URI không phải thuộc tính của OAuth Flow Object trong OpenAPI. Nó được cấu hình tại OAuth client và đăng ký với identity provider. Với Swagger UI, đường dẫn callback OAuth thường là endpoint redirect riêng của giao diện, có thể cấu hình qua tùy chọn Swagger UI `oauth2RedirectUrl` hoặc property tương ứng của Springdoc.

Ví dụ về các URL có vai trò khác nhau:

| URL | Vai trò |
| --- | --- |
| `https://identity.example.com/oauth2/authorize` | Authorization endpoint (`authorizationUrl`) |
| `https://identity.example.com/oauth2/token` | Token endpoint (`tokenUrl`) |
| `https://docs.example.com/swagger-ui/oauth2-redirect.html` | Callback của Swagger UI/client (`redirect_uri`) |

Authorization server phải đăng ký chính xác redirect URI được client sử dụng. Không đặt callback của Swagger UI vào `authorizationUrl`; làm vậy khiến browser gọi nhầm endpoint và OAuth flow không hoạt động.

## 12. Phân biệt OAuth2 flow với OpenID Connect discovery URL

OpenID Connect xây dựng trên OAuth2 nhưng có security scheme riêng trong OpenAPI: `type: openIdConnect`. Scheme này sử dụng `openIdConnectUrl` để trỏ đến tài liệu discovery của provider, thường là endpoint `/.well-known/openid-configuration`.

Ví dụ:

```yaml
components:
  securitySchemes:
    oidc:
      type: openIdConnect
      openIdConnectUrl: https://identity.example.com/.well-known/openid-configuration
```

`openIdConnectUrl` không phải `authorizationUrl`, `tokenUrl` hay `refreshUrl`. Discovery document của OIDC cung cấp metadata như authorization endpoint, token endpoint, JWKS URI và các capability của provider. Nếu khai báo scheme `openIdConnect`, không đặt các URL OAuth Flow Object vào trường `openIdConnectUrl`.

## 13. URL theo môi trường và tùy biến OpenAPI

Annotation Java yêu cầu giá trị thuộc tính là hằng số tại thời điểm biên dịch. Vì vậy, không thể đặt trực tiếp placeholder cấu hình Spring như `${OAUTH_TOKEN_URL}` vào `@OAuthFlow` rồi kỳ vọng annotation tự đọc giá trị từ environment.

Nếu các môi trường dùng URL khác nhau, có thể:

- Dùng `OpenApiCustomizer` để cập nhật URL trong model OpenAPI từ cấu hình Spring.
- Tạo tài liệu riêng cho từng môi trường hoặc group khi hợp đồng cần công bố khác nhau.
- Dùng cấu hình build/deployment để tạo tài liệu đã thay thế giá trị trước khi phát hành.

Ví dụ ý tưởng cập nhật authorization code flow bằng `OpenApiCustomizer` trong Springdoc 2.x:

```java
import io.swagger.v3.oas.models.security.OAuthFlow;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OAuthDocsCustomizerConfig {

    @Bean
    OpenApiCustomizer oauthUrlsCustomizer(
            @Value("${docs.oauth.authorization-url}") String authorizationUrl,
            @Value("${docs.oauth.token-url}") String tokenUrl) {

        return openApi -> {
            if (openApi.getComponents() == null
                    || openApi.getComponents().getSecuritySchemes() == null) {
                return;
            }

            SecurityScheme scheme = openApi.getComponents()
                .getSecuritySchemes().get("oauth2");
            if (scheme == null || scheme.getFlows() == null) {
                return;
            }

            OAuthFlow flow = scheme.getFlows().getAuthorizationCode();
            if (flow != null) {
                flow.setAuthorizationUrl(authorizationUrl);
                flow.setTokenUrl(tokenUrl);
            }
        };
    }
}
```

Ví dụ `application.yml`:

```yaml
docs:
  oauth:
    authorization-url: https://identity.example.com/oauth2/authorize
    token-url: https://identity.example.com/oauth2/token
```

Nếu dùng nhiều `GroupedOpenApi`, hãy bảo đảm customizer được áp dụng cho từng tài liệu group cần cập nhật; cách đăng ký customizer toàn cục và theo group phụ thuộc phiên bản Springdoc. Kiểm tra từng endpoint `/v3/api-docs/{group}` sau khi cấu hình.

Không để tài liệu production trỏ nhầm authorization server staging hoặc ngược lại. URL trong OpenAPI là thông tin công khai cho client, vì vậy phải được kiểm tra cùng cấu hình môi trường trước khi phát hành.

## 14. URL phải hợp lệ và an toàn

Các URL OAuth2 trong tài liệu nên đáp ứng những quy tắc sau:

1. Dùng HTTPS trong môi trường thực tế để bảo vệ authorization code, token và dữ liệu trao đổi.
2. Dùng endpoint chính thức do authorization server công bố; không tự đoán đường dẫn `/authorize`, `/token` hoặc `/refresh`.
3. Không nhúng client secret, access token, refresh token hoặc API key vào URL.
4. Tránh query parameter chứa thông tin nhạy cảm hoặc giá trị có thể hết hạn.
5. Kiểm tra URL có thể truy cập từ browser/client trong môi trường triển khai.
6. Đồng bộ hostname, path và phiên bản endpoint giữa tài liệu, cấu hình OAuth client và authorization server.
7. Nếu có nhiều tenant hoặc realm, ghi rõ URL tương ứng và không trộn endpoint giữa các tenant.

`authorizationUrl`, `tokenUrl` và `refreshUrl` là metadata mô tả điểm cuối. Springdoc không gọi thử endpoint, không kiểm tra chứng chỉ TLS, không xác thực client và không bảo đảm server đang hoạt động.

## 15. Cấu hình Swagger UI là phần riêng

OAuth Flow Object mô tả khả năng OAuth2 của API. Để Swagger UI thực hiện quy trình đăng nhập, cần cấu hình OAuth client của giao diện phù hợp với authorization server.

Ví dụ các thông tin Swagger UI có thể cần:

- Client ID dành riêng cho Swagger UI.
- Scope mặc định mà giao diện yêu cầu.
- Redirect URI của Swagger UI đã được đăng ký với identity provider.
- PKCE cho public client nếu authorization server hỗ trợ và yêu cầu.

Các giá trị này thuộc cấu hình OAuth client của Swagger UI, không phải tất cả đều là thuộc tính của `@OAuthFlow`. Không đặt client secret của confidential client trong JavaScript chạy trên trình duyệt hoặc tài liệu OpenAPI. Với public client, không dùng client secret như thể nó có thể được giữ bí mật.

Trong Springdoc, các tùy chọn OAuth của Swagger UI được cấu hình riêng dưới `springdoc.swagger-ui.oauth.*`; URL callback của UI cũng là một cấu hình riêng. Tên property cụ thể cần đối chiếu với phiên bản Springdoc/Swagger UI mà dự án đang dùng.

## 16. Kiểm tra cấu hình flow được sinh ra

Sau khi chạy ứng dụng, mở `/v3/api-docs` hoặc `/v3/api-docs.yaml` và tìm `components.securitySchemes`. Kiểm tra:

- Scheme có `type: oauth2`.
- Key scheme đúng với tên được `@SecurityRequirement` tham chiếu.
- Flow được đặt đúng key, ví dụ `authorizationCode`.
- `authorizationUrl` và `tokenUrl` không bị đảo vai trò.
- `refreshUrl` chỉ xuất hiện khi có endpoint phù hợp.
- Scopes có tên và mô tả chính xác.
- Operation tham chiếu đúng scheme và chỉ yêu cầu scope đã khai báo.
- URL trỏ đến đúng môi trường.

Trong Swagger UI, chọn **Authorize** và kiểm tra scheme hiển thị đúng flow, URL và scopes. Nếu cần thử đăng nhập, dùng client ID và redirect URI được cấu hình cho môi trường thử nghiệm. Kiểm tra request thực tế trong browser developer tools để xác nhận authorization request được gửi đến đúng `authorizationUrl` và token exchange được thực hiện theo cấu hình client.

Không chỉ dựa vào việc nút Authorize xuất hiện để kết luận OAuth2 hoạt động. Tài liệu có thể đúng cấu trúc nhưng authorization server chưa đăng ký client, redirect URI sai, scope chưa được cấp hoặc token endpoint không hoạt động.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Authorization Code flow thiếu URL | Thiếu `authorizationUrl` hoặc `tokenUrl` | Khai báo cả hai URL theo provider |
| Client Credentials flow khai báo authorization URL | Nhầm flow có người dùng với flow service-to-service | Chỉ khai báo `tokenUrl` cho `clientCredentials` |
| Browser chuyển đến REST API thay vì identity provider | Đặt API server URL vào `authorizationUrl` | Dùng authorization endpoint của identity provider |
| Token exchange gọi nhầm endpoint | Đảo `authorizationUrl` và `tokenUrl` | Đối chiếu từng trường với tài liệu provider |
| Refresh không hoạt động | `refreshUrl` không đúng hoặc provider dùng token endpoint chung | Xác minh refresh grant và URL thực tế của provider |
| Swagger UI quay lại callback bị lỗi | Nhầm `authorizationUrl` với redirect URI hoặc chưa đăng ký callback | Cấu hình redirect URI riêng cho Swagger UI và đăng ký tại provider |
| Scope không xuất hiện trong Authorize | Scope chưa khai báo trong `@Scopes` hoặc requirement dùng tên khác | Đồng bộ tên scope ở flow và operation |
| OpenAPI dùng URL staging ở production | URL được hard-code trong annotation | Dùng customizer/configuration theo môi trường và kiểm tra tài liệu phát hành |
| Placeholder `${...}` xuất hiện nguyên văn trong tài liệu | Annotation không đọc Spring property placeholder | Dùng `OpenApiCustomizer` hoặc bước build để thay URL |
| Scheme OIDC không có discovery metadata | Đặt OAuth flow URLs vào sai thuộc tính | Dùng `openIdConnectUrl` cho scheme `openIdConnect` |
| Lộ client secret trong Swagger UI | Đặt secret vào cấu hình frontend hoặc tài liệu | Xóa secret, rotate nếu đã lộ và dùng public-client/PKCE hoặc backend phù hợp |

## 18. Checklist cho OAuth Flows Object

- [ ] Scheme có `type = SecuritySchemeType.OAUTH2`.
- [ ] Đã chọn flow phù hợp với loại client và mô hình cấp quyền.
- [ ] Authorization Code có `authorizationUrl` và `tokenUrl`.
- [ ] Client Credentials và Password có `tokenUrl`.
- [ ] Implicit có `authorizationUrl`; chỉ mô tả khi hệ thống cũ thực sự còn dùng.
- [ ] `refreshUrl` được khai báo theo endpoint thực tế, không tự đoán.
- [ ] Scope được khai báo bằng `@Scopes` và `@OAuthScope`.
- [ ] `@SecurityRequirement` tham chiếu đúng tên scheme và scope.
- [ ] Không nhầm OAuth endpoint với `servers.url` hoặc redirect URI.
- [ ] Không nhầm `openIdConnectUrl` với các URL trong OAuth Flow Object.
- [ ] URL HTTPS, không chứa token, secret hoặc query parameter nhạy cảm.
- [ ] URL theo môi trường được quản lý và xác minh trước khi phát hành.
- [ ] Swagger UI OAuth client được cấu hình riêng và không lộ client secret.
- [ ] Đã kiểm tra OpenAPI JSON/YAML và thử quy trình trên môi trường phù hợp.

OAuth Flows Object mô tả những flow mà API hỗ trợ và endpoint của authorization server cho từng flow. `authorizationUrl`, `tokenUrl` và `refreshUrl` có vai trò riêng; chúng cần khớp với cấu hình thật của identity provider. Khi phân biệt đúng các URL này với API server, redirect URI và OIDC discovery URL, tài liệu OpenAPI sẽ giúp client tích hợp OAuth2 chính xác hơn mà không nhầm lẫn giữa metadata mô tả và cấu hình xác thực runtime.
