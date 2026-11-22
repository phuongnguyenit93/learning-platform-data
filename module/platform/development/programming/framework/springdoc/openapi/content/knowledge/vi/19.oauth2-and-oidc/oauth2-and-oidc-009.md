# Ranh giới giữa Swagger UI với authorization server và resource server

Swagger UI, Authorization Server và Resource Server có thể cùng xuất hiện trong một quy trình thử API, nhưng chúng đảm nhiệm những vai trò khác nhau. Swagger UI là giao diện tài liệu và HTTP client chạy trong trình duyệt. Authorization Server xác thực người dùng hoặc client rồi cấp token theo OAuth2/OIDC. Resource Server bảo vệ tài nguyên, kiểm tra access token và quyết định request có đủ quyền hay không.

springdoc-openapi giúp mô tả cơ chế xác thực trong hợp đồng OpenAPI để Swagger UI biết cách bắt đầu luồng cấp quyền và gửi credential khi gọi API. Việc mô tả này không biến Swagger UI thành máy chủ cấp token, cũng không thay thế việc xác thực và phân quyền tại Resource Server.

## 1. Ba vai trò trong một quy trình

| Thành phần | Trách nhiệm chính | Việc không đảm nhiệm |
|---|---|---|
| Swagger UI | Hiển thị OpenAPI, cho phép chọn operation, nhập tham số và gửi request từ trình duyệt | Không cấp token, không xác minh chữ ký token và không quyết định quyền truy cập |
| Authorization Server (AS) | Xác thực người dùng/client, xử lý consent khi cần, cấp và quản lý access token | Không thực thi nghiệp vụ của API được bảo vệ |
| Resource Server (RS) | Nhận request, xác minh access token, kiểm tra audience/scope/authority và bảo vệ tài nguyên | Không cấp access token cho client trong vai trò resource server |

Một sản phẩm có thể cung cấp cả Authorization Server và Resource Server, nhưng đây vẫn là hai vai trò logic riêng. Ví dụ, một nền tảng định danh có thể cấp token, trong khi ứng dụng Spring Boot chỉ nhận token và bảo vệ các endpoint đơn hàng.

Swagger UI có thể được phục vụ từ chính ứng dụng Spring Boot hoặc từ một host tài liệu riêng. Vị trí triển khai không làm thay đổi vai trò của nó: giao diện vẫn là OAuth2 client hỗ trợ người dùng thử API.

## 2. Luồng tổng quát khi dùng Swagger UI với OAuth2

Với Authorization Code flow có PKCE, trình duyệt thường thực hiện các bước:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant UI as Swagger UI (browser client)
    participant AS as Authorization Server
    participant RS as Resource Server

    U->>UI: Chọn operation và Authorize
    UI->>AS: Điều hướng đến authorization endpoint
    AS->>U: Đăng nhập và consent nếu cần
    U->>AS: Hoàn tất xác thực
    AS-->>UI: Redirect về callback kèm authorization code
    UI->>AS: Đổi code + PKCE verifier lấy token
    AS-->>UI: Access token (và ID token nếu dùng OIDC)
    UI->>RS: Gọi API với Authorization: Bearer access_token
    RS->>RS: Xác minh token và quyền
    RS-->>UI: HTTP response
    UI-->>U: Hiển thị request và response
~~~

Điểm cần nhớ là có hai lần gọi đến hai vai trò khác nhau:

1. Swagger UI trao đổi với Authorization Server để lấy token.
2. Swagger UI gửi access token đến Resource Server để gọi operation.

Nếu token endpoint lỗi, request nghiệp vụ chưa chắc đã được gửi đến Resource Server. Nếu token lấy được nhưng API trả 401 hoặc 403, cần kiểm tra Resource Server và quyền của token.

## 3. Authorization Server chịu trách nhiệm cấp token

Authorization Server quản lý luồng OAuth2/OIDC. Trong Authorization Code flow, nó thường:

- Xác thực người dùng bằng cơ chế đăng nhập của tổ chức.
- Kiểm tra client ID, redirect URI và các tham số của authorization request.
- Hiển thị consent nếu chính sách yêu cầu người dùng chấp thuận quyền.
- Phát hành authorization code ngắn hạn, dùng một lần.
- Đổi code hợp lệ thành access token và có thể kèm refresh token hoặc ID token tùy flow.
- Công bố metadata, signing keys hoặc endpoint introspection theo cấu hình.

Swagger UI không thực hiện những bước này. Nó chuyển trình duyệt đến authorization endpoint, nhận callback và trao đổi code theo cấu hình OAuth2 client. Việc kiểm tra mật khẩu, MFA, session, consent, client registration và phát hành token thuộc Authorization Server.

Các URL như authorization endpoint, token endpoint và issuer phải đến từ môi trường định danh thật. Trong ví dụ tài liệu, có thể dùng hostname minh họa, nhưng không được nhầm chúng với endpoint của ứng dụng API.

## 4. Resource Server chịu trách nhiệm bảo vệ API

Resource Server nhận request chứa access token, thường qua header:

~~~http
Authorization: Bearer eyJ...access-token
~~~

Với JWT access token, Resource Server cần kiểm tra chữ ký bằng key tin cậy, issuer, thời hạn và các điều kiện token khác theo chính sách. API cũng cần kiểm tra audience để bảo đảm token được phát hành cho đúng resource server. Việc kiểm tra audience có thể cần validator bổ sung tùy cấu hình framework.

Với opaque access token, Resource Server thường gọi introspection endpoint của Authorization Server để xác minh token còn hiệu lực và lấy thông tin quyền. Dù dùng JWT hay opaque token, quyết định cuối cùng vẫn thuộc Resource Server.

Sau khi token hợp lệ, ứng dụng còn phải kiểm tra quyền truy cập tài nguyên:

- Người gọi có scope cần thiết như <code>orders:read</code> hay không?
- Người gọi có authority hoặc role phù hợp không?
- Người gọi có được phép truy cập đúng bản ghi hoặc tenant này không?
- Quy tắc nghiệp vụ có cho phép hành động tại thời điểm hiện tại không?

Token hợp lệ không đồng nghĩa mọi thao tác đều được phép. Đây là lý do một request có thể nhận <code>403 Forbidden</code> dù người dùng đã đăng nhập thành công.

## 5. Swagger UI là OAuth2 client trong trình duyệt

Khi OpenAPI mô tả OAuth2 scheme, Swagger UI có thể hiển thị nút Authorize và khởi chạy flow mà giao diện hỗ trợ. Trong Authorization Code flow, Swagger UI dùng redirect callback để nhận code, sau đó trao đổi code lấy token.

Swagger UI không phải Authorization Server:

- Không lưu mật khẩu người dùng để xác thực.
- Không tạo authorization code hoặc access token.
- Không quản lý client registration hay consent.
- Không xác minh chữ ký và issuer của access token như Resource Server.

Swagger UI cũng không phải Resource Server:

- Không bảo vệ endpoint nghiệp vụ.
- Không kiểm tra quyền trên dữ liệu.
- Không thay thế Spring Security filter chain.
- Không thể bảo đảm request bị từ chối nếu server cấu hình sai.

Giao diện chỉ giữ và gửi thông tin xác thực theo cấu hình của nó. Server nhận request phải tự xác minh token.

## 6. Mô tả OAuth2 flow trong OpenAPI

Với springdoc-openapi, đăng ký scheme và flow bằng annotation. Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

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
                    name = "openid",
                    description = "Yêu cầu xác thực OpenID Connect"
                ),
                @OAuthScope(
                    name = "profile",
                    description = "Đọc các claim hồ sơ cơ bản của người dùng"
                ),
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
    ),
    description = "Đăng nhập qua Authorization Server của tổ chức"
)
class OAuthDocumentation {
}
~~~

Tên scheme <code>ordersOAuth</code> được dùng để tham chiếu từ operation. Authorization URL và token URL thuộc Authorization Server, không phải URL của Resource Server. Các hostname trong ví dụ cần được thay bằng địa chỉ thực tế của môi trường triển khai.

Hai scope <code>openid</code> và <code>profile</code> được khai báo để ví dụ có thể dùng OIDC cùng Authorization Code flow. Scope <code>orders:read</code> và <code>orders:write</code> là quyền truy cập API do hệ thống định nghĩa.

Gắn requirement vào operation:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders")
    @SecurityRequirement(
        name = "ordersOAuth",
        scopes = {"orders:read"}
    )
    List<OrderResponse> listOrders() {
        // Trả danh sách đơn hàng
        return List.of();
    }
}
~~~

Requirement cho Swagger UI biết operation cần scope <code>orders:read</code>. Nó không tự cấp scope đó cho người dùng; Authorization Server quyết định scope được cấp, còn Resource Server kiểm tra scope khi request đến.

## 7. Cấu hình Swagger UI cho Authorization Code + PKCE

Swagger UI chạy trong trình duyệt là public client. Mã JavaScript và cấu hình được gửi xuống trình duyệt nên không thể giữ bí mật client secret. Với Authorization Code flow cho browser client, bật PKCE và đăng ký redirect URI chính xác ở Authorization Server.

Ví dụ cấu hình springdoc trong <code>application.yml</code>:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
    oauth:
      client-id: swagger-ui
      use-pkce-with-authorization-code-grant: true
      scopes:
        - openid
        - profile
        - orders:read
~~~

Tên property cấu hình bên ngoài dùng kebab-case; có thể dùng camelCase theo cách binding được hỗ trợ bởi Spring Boot. Địa chỉ redirect phải khớp chính xác URI đã đăng ký cho client tại Authorization Server, gồm scheme, host, port, path và dấu slash nếu có.

Nếu UI được phục vụ ở đường dẫn tùy chỉnh hoặc sau reverse proxy, hãy kiểm tra URL callback thực tế. Không giả định redirect URI luôn là đường dẫn mặc định nếu ứng dụng đã đổi <code>springdoc.swagger-ui.path</code>.

Không đặt client secret trong <code>application.yml</code> được gửi đến browser, trong cấu hình JavaScript hoặc trong source code frontend. Với public client, dùng client ID và PKCE. Nếu một flow yêu cầu confidential client secret, hãy thực hiện ở backend hoặc công cụ phù hợp có khả năng giữ bí mật, không nhúng secret vào Swagger UI.

## 8. Redirect URI, PKCE và CORS thuộc những ranh giới nào?

Ba cấu hình này thường bị trộn lẫn:

| Cấu hình | Thành phần chịu trách nhiệm | Mục đích |
|---|---|---|
| Redirect URI registration | Authorization Server và OAuth2 client | Chỉ cho phép callback đã đăng ký |
| PKCE | OAuth2 client và Authorization Server | Ràng buộc authorization code với client đã khởi tạo yêu cầu |
| CORS của token endpoint | Authorization Server | Cho phép browser gửi token request cross-origin nếu flow yêu cầu |
| CORS của API | Resource Server | Cho phép browser đọc response từ API khác origin |

PKCE dùng code verifier và code challenge để giảm nguy cơ authorization code bị đánh cắp rồi đổi token bởi client khác. Swagger UI tạo verifier và gửi challenge trong authorization request; khi đổi code, nó gửi verifier tương ứng. Ưu tiên phương thức challenge <code>S256</code> theo cấu hình và khả năng của Authorization Server.

Authorization endpoint thường được mở bằng điều hướng trình duyệt, không phải XHR. Token endpoint thường được gọi từ browser để đổi code, do đó nếu khác origin thì Authorization Server cần CORS policy cho origin của Swagger UI. Sau khi lấy token, request API cross-origin còn cần Resource Server cho phép origin, method và header như <code>Authorization</code>.

Không bật wildcard origin cùng credential tùy tiện trong production. Hãy cho phép chính xác origin của trang tài liệu và chỉ các method/header cần thiết.

## 9. OIDC: ID token và access token có mục đích khác nhau

OpenID Connect bổ sung lớp định danh trên OAuth2. Khi dùng OIDC, Authorization Server/Identity Provider có thể trả:

- **ID token**: chứa thông tin xác thực về người dùng và được phát hành cho OIDC client. Audience của ID token thường là client ID.
- **Access token**: credential để client gọi Resource Server. Audience và scope phải phù hợp với API được bảo vệ.

Không dùng ID token thay cho access token khi gọi API trừ khi hợp đồng của hệ thống có thiết kế riêng và Resource Server được cấu hình rõ để chấp nhận loại token đó. Thông thường, Swagger UI gửi access token trong header Bearer; Resource Server xác minh token dành cho chính nó.

Ví dụ OIDC Discovery scheme trong OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "companyOidc",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://identity.example.com/.well-known/openid-configuration",
    description = "OpenID Connect discovery của tổ chức"
)
class OidcDocumentation {
}
~~~

URL discovery mô tả metadata của OpenID Provider. Nó không phải endpoint nghiệp vụ của Resource Server. Mức hỗ trợ tương tác OpenID Connect trực tiếp trong Swagger UI phụ thuộc phiên bản UI và cách scheme được mô tả; với luồng thử API OAuth2 phổ biến, cấu hình OAuth2 Authorization Code + PKCE thường được dùng để lấy access token.

## 10. Resource Server trong Spring Boot

Với JWT access token, Spring Security có thể cấu hình ứng dụng ở vai trò OAuth2 Resource Server. Ví dụ cơ bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Issuer URI giúp Resource Server khám phá metadata và khóa công khai để xác minh JWT theo cấu hình. Ứng dụng vẫn cần xác định chính sách audience, scope và quyền nghiệp vụ phù hợp. Không mặc định rằng chỉ khai báo issuer là đã kiểm tra đầy đủ mọi điều kiện riêng của API.

Ví dụ giới hạn operation theo scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Spring Security thường ánh xạ scope trong JWT thành authority có tiền tố <code>SCOPE_</code>. Ví dụ scope <code>orders:read</code> trở thành <code>SCOPE_orders:read</code>. Nếu token dùng claim tùy chỉnh hoặc cách đặt quyền khác, cần cấu hình converter phù hợp.

Ví dụ trên chỉ minh họa kiểm tra scope ở endpoint. Với thao tác theo từng đơn hàng, ứng dụng còn phải kiểm tra người dùng có quyền trên chính đơn hàng đó hay không.

## 11. JWT và opaque token: Resource Server xác minh bằng cách nào?

| Loại access token | Cách Resource Server kiểm tra | Đặc điểm |
|---|---|---|
| JWT | Kiểm tra chữ ký và các claim bằng key tin cậy | Có thể xác minh cục bộ sau khi lấy key; cần xử lý key rotation và chính sách claim |
| Opaque token | Gọi introspection endpoint của Authorization Server | AS trả trạng thái token và metadata; request phụ thuộc kết nối introspection |

Swagger UI không cần giải mã hoặc xác minh token để gửi request. Nó chuyển access token do Authorization Server cấp đến Resource Server. Resource Server mới là nơi xác minh token.

Không suy luận rằng JWT hợp lệ chỉ vì có ba phần phân tách bằng dấu chấm hoặc decode được payload. Nội dung JWT có thể đọc được nhưng chữ ký và claim vẫn cần được xác minh. Tương tự, opaque token không nên được xem là chuỗi ngẫu nhiên mà ứng dụng có thể tự kiểm tra bằng logic tùy tiện.

## 12. Các lỗi thường gặp theo từng ranh giới

**Không mở được trang đăng nhập sau khi nhấn Authorize.** Kiểm tra authorization URL, client registration, redirect URI, HTTPS và cấu hình OAuth2 flow trong OpenAPI.

**Authorization Server báo redirect URI không hợp lệ.** So sánh URI Swagger UI thực sự dùng với URI đã đăng ký; kiểm tra cả context path, reverse proxy và slash cuối.

**Token endpoint bị CORS chặn.** Kiểm tra CORS policy của Authorization Server cho origin Swagger UI. CORS của Resource Server không sửa được lỗi ở token endpoint.

**Swagger UI nhận token nhưng API trả 401.** Kiểm tra Swagger UI gửi access token hay ID token, header Bearer, chữ ký, issuer, expiry, audience và cấu hình decoder/introspection của Resource Server.

**API trả 403.** Token có thể hợp lệ nhưng thiếu scope, role hoặc quyền trên tài nguyên. Đối chiếu scope trong token, requirement OpenAPI và authorization rule của backend.

**Swagger UI gửi request nhưng browser không đọc được response.** Kiểm tra CORS của Resource Server, đặc biệt preflight và header <code>Authorization</code>. Request có thể đã đến server nhưng browser chặn JavaScript đọc response.

**Đặt client secret trong cấu hình Swagger UI.** Cấu hình frontend được gửi đến browser nên secret có thể bị người dùng xem. Dùng public client với PKCE hoặc chuyển luồng confidential client sang backend.

**Tài liệu khai báo scope nhưng backend không kiểm tra.** <code>@SecurityRequirement</code> chỉ mô tả hợp đồng. Cấu hình Resource Server và authorization rule phải thực thi quyền thật.

**Bảo vệ Swagger UI nhưng để lộ OpenAPI JSON.** Nếu chính sách yêu cầu tài liệu riêng tư, bảo vệ cả trang UI, JSON/YAML và các endpoint tài liệu theo cùng chính sách.

## 13. Cách điều tra một request thất bại

Đi theo thứ tự để xác định request dừng ở đâu:

1. **Authorize chưa hoàn tất:** kiểm tra redirect, đăng nhập, consent, authorization code và token endpoint ở Authorization Server.
2. **Không nhận được access token:** xem lỗi đổi code, PKCE verifier, client ID, redirect URI và CORS của token endpoint.
3. **Có token nhưng không gửi được API:** kiểm tra server URL, request URL, header Authorization và CORS của Resource Server.
4. **API trả 401:** kiểm tra loại token, chữ ký, issuer, expiry, audience và trạng thái introspection.
5. **API trả 403:** kiểm tra scope, role, authority, tenant và quyền trên tài nguyên.
6. **API trả 2xx nhưng dữ liệu sai:** kiểm tra logic nghiệp vụ, response schema và dữ liệu trả về.

Khi ghi log hoặc chia sẻ lỗi, không đưa access token, refresh token, authorization code, cookie phiên hay client secret vào tài liệu. Che credential và thông tin cá nhân trước khi gửi log hoặc ảnh chụp.

## 14. Danh sách rà soát trước khi công bố luồng thử API

- [ ] OpenAPI khai báo đúng OAuth2 flow và scope.
- [ ] Authorization URL và token URL trỏ đến Authorization Server đúng môi trường.
- [ ] Swagger UI được đăng ký như public client phù hợp và dùng Authorization Code + PKCE.
- [ ] Redirect URI khớp chính xác cấu hình client tại Authorization Server.
- [ ] Không nhúng client secret vào frontend hoặc Swagger UI.
- [ ] CORS của token endpoint cho phép đúng origin tài liệu nếu cần.
- [ ] Swagger UI gửi access token đến Resource Server bằng Bearer header.
- [ ] Resource Server xác minh chữ ký/trạng thái, issuer, thời hạn và audience theo policy.
- [ ] Scope/authority trong token được kiểm tra ở endpoint và tầng nghiệp vụ.
- [ ] CORS của Resource Server cho phép đúng origin và header nếu UI khác origin.
- [ ] Tài liệu OpenAPI và Swagger UI được bảo vệ theo chính sách công bố.
- [ ] Đã thử riêng các tình huống token thiếu, token hết hạn, sai audience và thiếu scope.

## Tài liệu tham khảo

- [OpenAPI Specification – OAuth Flows Object](https://spec.openapis.org/oas/latest.html#oauth-flows-object): mô tả các OAuth2 flow trong OpenAPI.
- [Swagger UI – OAuth 2.0 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/): cấu hình OAuth2, redirect URL và PKCE cho Swagger UI.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700): hướng dẫn bảo mật OAuth2 hiện hành.
- [OAuth 2.0 Authorization Framework (RFC 6749)](https://www.rfc-editor.org/rfc/rfc6749): vai trò client, authorization server, resource owner và resource server.
- [Proof Key for Code Exchange (RFC 7636)](https://www.rfc-editor.org/rfc/rfc7636): cơ chế PKCE.
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html): ID token, access token và luồng xác thực OIDC.
- [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT access token trong Resource Server.
- [Spring Security – OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection với opaque token.
- [springdoc-openapi](https://springdoc.org/): tích hợp OpenAPI và Swagger UI với Spring Boot.
