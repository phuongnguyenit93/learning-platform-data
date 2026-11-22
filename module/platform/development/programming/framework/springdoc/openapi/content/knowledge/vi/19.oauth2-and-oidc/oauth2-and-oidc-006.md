# Khai báo OpenID Connect discovery URL

OpenID Connect (OIDC) bổ sung lớp xác thực danh tính lên OAuth 2.0. Một OpenID Provider công bố tài liệu discovery chứa metadata như issuer, authorization endpoint, token endpoint và địa chỉ JSON Web Key Set (JWKS). Client có thể đọc tài liệu này để biết cách bắt đầu luồng đăng nhập và tìm khóa công khai dùng để kiểm tra token.

Trong OpenAPI, security scheme có kiểu `openIdConnect` liên kết đến tài liệu discovery bằng thuộc tính `openIdConnectUrl`. Với `springdoc-openapi`, có thể khai báo scheme này bằng annotation `@SecurityScheme` hoặc tạo model `SecurityScheme` trong bean `OpenAPI`. URL phải trỏ đúng tài liệu discovery JSON của nhà cung cấp danh tính; nó không phải URL issuer đơn thuần, authorization endpoint hay token endpoint.

## 1. Phân biệt issuer và discovery URL

Issuer là định danh của OpenID Provider. Nó xuất hiện trong metadata discovery và trong claim `iss` của ID token. Discovery URL là địa chỉ HTTP(S) để tải tài liệu metadata của issuer.

Ví dụ với một realm có issuer:

```text
Issuer:
https://sso.example.com/realms/store

Discovery document:
https://sso.example.com/realms/store/.well-known/openid-configuration
```

Đối với OIDC Discovery 1.0, đường dẫn `/.well-known/openid-configuration` được nối vào issuer identifier theo quy tắc của đặc tả. Khi issuer có path như realm hoặc tenant, phần path đó vẫn thuộc URL discovery. Nhiều nhà cung cấp hiển thị sẵn discovery URL trong trang cấu hình ứng dụng; ưu tiên URL chính xác do nhà cung cấp công bố thay vì tự ghép khi chưa xác minh.

Phân biệt các URL sau:

| Giá trị | Mục đích | Ví dụ |
| --- | --- | --- |
| Issuer | Định danh nhà cung cấp danh tính | `https://sso.example.com/realms/store` |
| Discovery URL | Tải metadata OIDC | `https://sso.example.com/realms/store/.well-known/openid-configuration` |
| Authorization endpoint | Bắt đầu luồng đăng nhập/ủy quyền | URL có trong `authorization_endpoint` |
| Token endpoint | Đổi authorization code hoặc refresh token | URL có trong `token_endpoint` |
| JWKS URI | Tải tập khóa công khai của issuer | URL có trong `jwks_uri` |

Không truyền `authorization_endpoint`, `token_endpoint` hoặc `jwks_uri` vào `openIdConnectUrl`. OpenAPI cần URL của tài liệu discovery để client hoặc công cụ đọc metadata và tự tìm các endpoint còn lại.

## 2. Tài liệu discovery chứa thông tin gì?

Một OpenID Provider thường trả tài liệu JSON tại discovery URL. Ví dụ rút gọn:

```json
{
  "issuer": "https://sso.example.com/realms/store",
  "authorization_endpoint": "https://sso.example.com/realms/store/protocol/openid-connect/auth",
  "token_endpoint": "https://sso.example.com/realms/store/protocol/openid-connect/token",
  "userinfo_endpoint": "https://sso.example.com/realms/store/protocol/openid-connect/userinfo",
  "jwks_uri": "https://sso.example.com/realms/store/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "code_challenge_methods_supported": ["S256"]
}
```

Các trường cốt lõi và thường gặp:

- `issuer`: định danh của OpenID Provider; phải khớp issuer mà client tin cậy và giá trị `iss` trong ID token.
- `authorization_endpoint`: endpoint nhận yêu cầu authorization.
- `token_endpoint`: endpoint cấp token hoặc đổi authorization code.
- `jwks_uri`: endpoint cung cấp khóa công khai để xác minh chữ ký token.
- `response_types_supported`: các response type mà provider hỗ trợ, ví dụ `code`.
- `subject_types_supported`: các kiểu subject identifier.
- `id_token_signing_alg_values_supported`: thuật toán ký ID token mà provider công bố.
- `scopes_supported`: danh sách scope provider hỗ trợ; đây là metadata tùy chọn trong discovery.
- `code_challenge_methods_supported`: phương thức PKCE được hỗ trợ nếu provider công bố.

Các metadata khác có thể bao gồm `userinfo_endpoint`, `end_session_endpoint`, phương thức xác thực ở token endpoint, claims được hỗ trợ và cấu hình logout. Không giả định mọi provider đều công bố tất cả trường tùy chọn hoặc có cùng tên extension.

Client nên kiểm tra tài liệu discovery được trả về qua HTTPS, xác nhận `issuer` chính xác và chỉ tin metadata từ provider đã cấu hình. Không lấy discovery URL từ input không đáng tin cậy của người dùng rồi tự động truy cập, vì điều đó có thể tạo rủi ro SSRF hoặc khiến ứng dụng tin nhầm issuer.

## 3. Khai báo OpenID Connect scheme bằng annotation

Swagger Annotations cung cấp `@SecurityScheme` với kiểu `SecuritySchemeType.OPENIDCONNECT`. Thuộc tính `openIdConnectUrl` nhận URL của discovery document:

```java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(title = "Store API", version = "1.0.0"),
    security = {
        @SecurityRequirement(
            name = "storeOidc",
            scopes = {"openid", "profile"}
        )
    }
)
@SecurityScheme(
    name = "storeOidc",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl = "https://sso.example.com/realms/store/.well-known/openid-configuration",
    description = "OpenID Connect provider dành cho Store API"
)
class OpenApiOidcConfiguration {}
```

Ý nghĩa các thành phần:

- `name = "storeOidc"` là tên scheme được tham chiếu trong security requirement.
- `type = SecuritySchemeType.OPENIDCONNECT` tạo scheme kiểu OpenID Connect.
- `openIdConnectUrl` trỏ đến discovery document JSON.
- `@OpenAPIDefinition.security` áp dụng requirement ở cấp document; các operation kế thừa requirement này nếu không ghi đè.
- `scopes` liệt kê scope cần thiết cho operation/client theo hợp đồng API.

Tên `storeOidc` phải khớp chính xác giữa `@SecurityScheme` và `@SecurityRequirement`. Tên này là khóa nội bộ trong OpenAPI, không phải issuer, client ID hay tên realm.

Nếu chỉ một số operation yêu cầu OIDC, không đặt security toàn cục; hãy gắn `@SecurityRequirement(name = "storeOidc", scopes = {...})` trên từng `@Operation` tương ứng. Operation công khai có thể ghi đè yêu cầu toàn cục bằng `@SecurityRequirements` rỗng như quy tắc bảo mật của OpenAPI.

## 4. Khai báo scheme bằng bean `OpenAPI`

Nếu dự án quản lý tài liệu bằng Java configuration thay vì annotation, có thể tạo `SecurityScheme` trực tiếp:

```java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class OpenApiOidcBeanConfiguration {

    @Bean
    OpenAPI storeOpenAPI() {
        SecurityScheme oidc = new SecurityScheme()
            .type(SecurityScheme.Type.OPENIDCONNECT)
            .openIdConnectUrl(
                "https://sso.example.com/realms/store/.well-known/openid-configuration"
            )
            .description("OpenID Connect provider dành cho Store API");

        SecurityRequirement requirement = new SecurityRequirement()
            .addList("storeOidc", List.of("openid", "profile"));

        return new OpenAPI()
            .info(new Info().title("Store API").version("1.0.0"))
            .components(new Components().addSecuritySchemes("storeOidc", oidc))
            .addSecurityItem(requirement);
    }
}
```

Ở đây, `.type(SecurityScheme.Type.OPENIDCONNECT)` và `.openIdConnectUrl(...)` tạo cùng cấu trúc với annotation. `addSecuritySchemes` đăng ký scheme; `addSecurityItem` áp dụng requirement. Chọn một cách khai báo chính để tránh vô tình tạo hai scheme cùng ý nghĩa hoặc hai tên khác nhau cho cùng provider.

Nếu dùng nhiều OpenAPI document qua `GroupedOpenApi`, cần xác định scheme và requirement nào dùng chung, scheme nào riêng cho từng nhóm. Kiểm tra từng URL `/v3/api-docs/{group}` vì customizer riêng của group có thể làm tài liệu khác với document mặc định.

## 5. OpenAPI document được sinh ra trông như thế nào?

Với cấu hình annotation ở trên, cấu trúc quan trọng trong OpenAPI sẽ tương tự:

```yaml
openapi: 3.0.3
components:
  securitySchemes:
    storeOidc:
      type: openIdConnect
      openIdConnectUrl: https://sso.example.com/realms/store/.well-known/openid-configuration
      description: OpenID Connect provider dành cho Store API
security:
  - storeOidc:
      - openid
      - profile
paths:
  /api/orders:
    get:
      responses:
        '200':
          description: Danh sách đơn hàng
```

Điểm cần kiểm tra là `type` có giá trị `openIdConnect`, `openIdConnectUrl` đúng URL discovery và security requirement tham chiếu đúng tên `storeOidc`. OpenAPI document chỉ lưu URL và yêu cầu scope; nó không nhúng toàn bộ discovery JSON vào `components`.

Nếu scheme được khai báo nhưng không xuất hiện trong `security`, Swagger UI có thể không biết operation cần dùng scheme đó. Ngược lại, nếu requirement tham chiếu tên chưa được khai báo trong `components.securitySchemes`, document không nhất quán.

## 6. Scope OIDC và scope của API

Scope `openid` là scope đặc biệt để yêu cầu một luồng OpenID Connect và ID token. Các scope chuẩn như `profile`, `email`, `address` hoặc `phone` yêu cầu claims tương ứng nếu provider hỗ trợ và chính sách consent cho phép.

API cũng có thể định nghĩa scope ủy quyền riêng, ví dụ `orders.read` hoặc `orders.write`. Các scope này thường biểu đạt quyền truy cập tài nguyên API, không đồng nghĩa với scope profile của OIDC. Khi ghi trong OpenAPI security requirement, hãy dùng tên scope mà authorization server và API thực sự hiểu.

Ví dụ operation chỉ đọc đơn hàng:

```java
@GetMapping("/api/orders")
@Operation(
    summary = "Liệt kê đơn hàng",
    security = @SecurityRequirement(
        name = "storeOidc",
        scopes = {"openid", "orders.read"}
    )
)
List<OrderResponse> listOrders() {
    return orderService.findAll();
}
```

Tên scope trong security requirement là một phần hợp đồng. Hãy đồng bộ với cấu hình client, authorization server và policy mà API kiểm tra. Việc thêm `orders.read` vào annotation không tự tạo scope trên Identity Provider và cũng không tự áp dụng quyền trong Spring Security.

## 7. Phân biệt `openIdConnect` với `oauth2` và HTTP Bearer

Ba kiểu security scheme thường gặp có ý nghĩa khác nhau:

| Kiểu OpenAPI | Cách mô tả | Khi phù hợp |
| --- | --- | --- |
| `openIdConnect` | Liên kết đến OIDC discovery document bằng `openIdConnectUrl`. | API dùng OpenID Provider và muốn công bố metadata discovery cho client/tooling. |
| `oauth2` | Khai báo rõ OAuth2 `flows`, authorization URL, token URL và scopes. | Hợp đồng cần mô tả trực tiếp các OAuth2 flow mà client sử dụng. |
| `http` với `scheme: bearer` | Mô tả client gửi bearer token trong `Authorization` header. | API chỉ cần công bố cách gửi access token; không cần mô tả discovery/authorization flow. |

OIDC được xây dựng trên OAuth 2.0 nhưng bổ sung danh tính người dùng và ID token. Nếu API chỉ xác minh access token dạng bearer và không cần công bố luồng đăng nhập, HTTP Bearer có thể đơn giản hơn. Nếu client cần discovery để tìm endpoint đăng nhập, `openIdConnect` diễn đạt rõ hơn. Nếu cần kiểm soát chi tiết từng OAuth2 flow trong OpenAPI, dùng scheme `oauth2` với `flows` phù hợp.

Không nhầm ID token với access token. ID token chứng minh kết quả xác thực người dùng cho client OIDC; access token được cấp để truy cập resource server/API. API cần kiểm tra loại token, audience và policy của chính nó; không mặc định chấp nhận ID token làm access token.

## 8. Discovery URL không thay thế cấu hình Swagger UI OAuth client

`openIdConnectUrl` mô tả vị trí metadata của provider. Nó không phải client ID, không chứa client secret và không tự đăng ký ứng dụng Swagger UI với Identity Provider.

Nếu muốn dùng nút **Authorize** để thực hiện đăng nhập tương tác, còn cần cấu hình OAuth client phù hợp trong Swagger UI và đăng ký redirect URI mà Swagger UI sử dụng ở phía provider. Với ứng dụng chạy trong trình duyệt, nên dùng public client và Authorization Code Flow với PKCE; không nhúng client secret vào JavaScript hoặc OpenAPI document.

Các thuộc tính cấu hình Swagger UI liên quan OAuth có thể gồm `springdoc.swagger-ui.oauth.client-id`, `springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant` và URL redirect theo cấu hình của giao diện. Khả năng tự đọc discovery và trải nghiệm **Authorize** phụ thuộc phiên bản Swagger UI cùng cấu hình client. Sau khi khai báo scheme, hãy kiểm tra UI thực tế thay vì giả định discovery URL đã hoàn tất toàn bộ đăng nhập.

Discovery URL cũng không làm Spring Security tự cấu hình resource server. Ứng dụng Spring Boot vẫn cần cấu hình issuer/JWK hoặc bộ xác minh token, kiểm tra chữ ký, `iss`, `aud`, `exp`, thời gian hiệu lực và authority/scope theo policy. Với Spring Security Resource Server, cấu hình `issuer-uri` có thể cho phép framework dùng metadata của issuer để khám phá khóa và xác minh JWT, nhưng đó là cấu hình runtime riêng với `openIdConnectUrl` trong OpenAPI.

## 9. Bảo vệ và quản lý discovery URL

Discovery URL là metadata công khai theo thiết kế của OIDC, nhưng cần được quản lý như một phần cấu hình tin cậy:

- Dùng HTTPS và chứng thư TLS hợp lệ.
- Lấy URL từ cấu hình môi trường hoặc thông tin chính thức của Identity Provider.
- Xác minh trường `issuer` trong document khớp chính xác issuer đã cấu hình.
- Kiểm tra `jwks_uri`, authorization endpoint và token endpoint thuộc provider dự kiến.
- Không đưa client secret, mật khẩu, access token hoặc refresh token vào URL discovery hay OpenAPI document.
- Nếu dùng nhiều tenant/realm, mỗi issuer cần discovery URL đúng phạm vi tenant đó.
- Khi đổi domain, realm hoặc issuer, cập nhật cấu hình tài liệu và cấu hình xác minh token runtime đồng bộ.

Discovery document có thể được cache theo chính sách của provider. Không nên tải lại tùy tiện ở mỗi request nghiệp vụ; thư viện OIDC/resource server thường quản lý metadata và JWKS cache riêng. Khi xoay khóa, cần tuân thủ cơ chế refresh/caching của thư viện xác minh token.

## 10. Kiểm tra discovery và OpenAPI document

Trước khi công bố tài liệu, xác minh cả metadata từ provider lẫn schema springdoc sinh ra:

1. Mở discovery URL trực tiếp hoặc gọi bằng curl để xác nhận trả JSON qua HTTPS.
2. Kiểm tra `issuer` khớp chính xác issuer được cấu hình.
3. Xác nhận có các endpoint cần thiết như `authorization_endpoint`, `token_endpoint` và `jwks_uri`.
4. Kiểm tra `response_types_supported`, thuật toán ký ID token và PKCE method nếu luồng client cần dùng.
5. Mở `/v3/api-docs` và tìm `components.securitySchemes.storeOidc`.
6. Xác nhận `type` là `openIdConnect` và `openIdConnectUrl` trỏ đúng discovery document.
7. Kiểm tra `security` ở root hoặc operation tham chiếu `storeOidc` với scope đúng.
8. Mở Swagger UI, xác nhận scheme được hiển thị và thử **Authorize** nếu ứng dụng đã cấu hình OAuth client/redirect URI.
9. Gọi API runtime với access token hợp lệ, token sai issuer/audience và token hết hạn để xác nhận resource server kiểm tra đúng.

Ví dụ kiểm tra nhanh discovery:

```bash
curl -i https://sso.example.com/realms/store/.well-known/openid-configuration
```

Ví dụ kiểm tra OpenAPI:

```bash
curl -s http://localhost:8080/v3/api-docs
```

Nếu chạy qua nhiều group, lặp lại kiểm tra với `/v3/api-docs/{group}` cho từng document cần công bố.

## 11. Kiểm thử tài liệu bằng MockMvc

Có thể kiểm tra scheme được springdoc sinh ra bằng JSONPath:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OidcOpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesOpenIdConnectDiscoveryUrl() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.components.securitySchemes.storeOidc.type")
                .value("openIdConnect"))
            .andExpect(jsonPath("$.components.securitySchemes.storeOidc.openIdConnectUrl")
                .value("https://sso.example.com/realms/store/.well-known/openid-configuration"))
            .andExpect(jsonPath("$.security[0].storeOidc").isArray());
    }
}
```

Test này xác nhận metadata OpenAPI được công bố đúng. Nó không gọi Identity Provider và không chứng minh JWT được xác minh đúng. Nên có kiểm thử riêng cho resource server hoặc integration test với môi trường Identity Provider giả lập để xác nhận issuer, audience, chữ ký, expiry và scope.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| OpenAPI có `type: openIdConnect` nhưng không có `openIdConnectUrl` | Thiếu thuộc tính URL hoặc dùng nhầm annotation/type | Khai báo `openIdConnectUrl` trên `@SecurityScheme` hoặc model `SecurityScheme`. |
| Discovery URL trả `404` | Ghép sai well-known path, realm hoặc tenant | Dùng URL discovery chính xác từ nhà cung cấp và kiểm tra issuer path. |
| Discovery document tải được nhưng `issuer` không khớp | Dùng nhầm realm/tenant hoặc proxy làm thay đổi issuer | Đồng bộ issuer chính xác giữa metadata, client và resource server. |
| Swagger UI không biết operation cần xác thực | Có scheme nhưng thiếu security requirement | Thêm root `security` hoặc `@SecurityRequirement` ở operation. |
| Scheme không xuất hiện trong Authorize | Security requirement tham chiếu sai tên hoặc UI không hỗ trợ cấu hình đó | Đồng bộ tên scheme và kiểm tra phiên bản Swagger UI. |
| Nút Authorize mở sai redirect URI | Chưa đăng ký redirect URI của Swagger UI hoặc cấu hình client sai | Cập nhật client registration và OAuth UI settings; dùng PKCE cho public client. |
| API trả `401` dù OpenAPI khai báo OIDC | Discovery metadata không cấu hình resource server hoặc token không hợp lệ | Kiểm tra JWT decoder, issuer, audience, JWKS và thời hạn token. |
| API nhận ID token nhưng từ chối access token hoặc ngược lại | Dùng nhầm loại token hoặc audience | Dùng access token cho resource server và kiểm tra audience/policy đúng. |
| URL hoạt động ở local nhưng sai sau proxy | Host, scheme hoặc prefix công khai khác URL nội bộ | Kiểm tra forwarded headers và URL discovery/issuer mà provider công bố. |
| Mỗi group có security scheme khác nhau | Customizer hoặc cấu hình OpenAPI riêng theo group | Kiểm tra từng `/v3/api-docs/{group}` và thống nhất cấu hình cần dùng chung. |

## 13. Nguyên tắc áp dụng

- Phân biệt issuer, discovery URL, authorization endpoint, token endpoint và JWKS URI.
- Dùng `SecuritySchemeType.OPENIDCONNECT` cùng `openIdConnectUrl` để mô tả OIDC discovery trong OpenAPI.
- Đặt security requirement tham chiếu đúng tên scheme và scope mà API thực sự yêu cầu.
- Dùng `openIdConnect` khi cần công bố discovery; dùng `oauth2` khi cần mô tả chi tiết OAuth2 flows; dùng HTTP Bearer khi chỉ cần mô tả cách gửi access token.
- Không nhầm ID token với access token.
- Không coi discovery URL là cấu hình OAuth client hoặc cấu hình resource server.
- Dùng HTTPS, xác minh issuer và chỉ tin metadata từ Identity Provider đã cấu hình.
- Kiểm tra OpenAPI JSON, Swagger UI, discovery document và token validation runtime như các bước riêng.
- Kiểm tra từng group document nếu ứng dụng có nhiều `GroupedOpenApi`.

`openIdConnectUrl` kết nối security scheme trong OpenAPI với tài liệu discovery của OpenID Provider. Khi URL trỏ đúng metadata, tên scheme và scope được khai báo nhất quán, client có thể tìm hiểu cách xác thực mà API công bố. Phần đăng nhập tương tác, cấp access token và xác minh token vẫn cần được cấu hình riêng ở Swagger UI, Identity Provider và Spring Security resource server.

## Tài liệu tham khảo

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenAPI Specification – OpenID Connect URL](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@SecurityScheme`](https://docs.swagger.io/swagger-core/v2.2.53/apidocs/io/swagger/v3/oas/annotations/security/SecurityScheme.html)
- [Springdoc OpenAPI – tài liệu chính thức](https://springdoc.org/)
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
