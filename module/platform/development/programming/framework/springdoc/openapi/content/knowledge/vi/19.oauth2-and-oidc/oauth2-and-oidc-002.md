# Authorization Code và hỗ trợ PKCE của công cụ giao diện

Swagger UI có thể cho phép người dùng đăng nhập qua OAuth 2.0 hoặc OpenID Connect (OIDC), sau đó dùng access token để gọi API ngay trong trình duyệt. Với một công cụ giao diện chạy phía browser, mô hình phù hợp là **Authorization Code Flow kết hợp Proof Key for Code Exchange (PKCE)**. PKCE giúp bảo vệ authorization code nếu code bị chặn hoặc bị đánh cắp trên đường chuyển hướng.

Trong Spring Boot, springdoc-openapi tạo đặc tả OpenAPI từ controller và cấu hình Swagger UI. Để luồng đăng nhập hoạt động, cần phối hợp ba phần:

1. **OpenAPI security scheme** mô tả authorization URL, token URL và scopes của Authorization Code Flow.
2. **Swagger UI** được cấu hình client ID, redirect URL và bật PKCE.
3. **Authorization Server / OpenID Provider** đăng ký đúng public client, redirect URI, scopes và bắt buộc xác minh PKCE.

Chỉ khai báo flow trong OpenAPI không tự bật PKCE và cũng không biến ứng dụng thành Authorization Server. API vẫn cần xác minh access token ở phía server, thường bằng Spring Security Resource Server.

## 1. Authorization Code Flow phù hợp với công cụ giao diện

OAuth 2.0 Authorization Code Flow có hai giai đoạn chính:

- Trình duyệt chuyển người dùng đến Authorization Server để đăng nhập và cấp quyền.
- Client nhận authorization code qua redirect URI, sau đó đổi code lấy token tại token endpoint.

Swagger UI chạy trong browser nên không thể giữ an toàn một client secret tĩnh. Client được triển khai trong browser là **public client**. Khi dùng Authorization Code Flow, public client phải sử dụng PKCE theo OAuth 2.0 Security Best Current Practice.

PKCE bổ sung một bí mật ngẫu nhiên ngắn hạn cho từng lần đăng nhập. Client tạo:

- **code_verifier**: chuỗi ngẫu nhiên có entropy cao, chỉ giữ ở client trong giao dịch hiện tại.
- **code_challenge**: giá trị được tính từ verifier để gửi đến Authorization Server.
- **code_challenge_method**: phương pháp biến đổi verifier, nên dùng S256.

Với S256:

~~~text
code_challenge =
  BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
~~~

Authorization Server lưu challenge cùng authorization code. Khi client đổi code lấy token, client gửi verifier. Server tính lại challenge từ verifier và so sánh với giá trị đã lưu. Nếu không khớp, token endpoint từ chối cấp token.

Kẻ tấn công có thể nhìn thấy authorization code nhưng không thể đổi code thành token nếu không có verifier tương ứng. PKCE vì vậy giảm rủi ro authorization code interception và injection.

## 2. Luồng đăng nhập từ Swagger UI

Quy trình điển hình:

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant UI as Swagger UI
    participant AS as Authorization Server
    participant API as Spring Boot API

    User->>UI: Chọn Authorize
    UI->>UI: Tạo code_verifier và code_challenge S256
    UI->>AS: Redirect /authorize với response_type=code, state, challenge
    AS->>User: Đăng nhập và xin consent
    User->>AS: Xác thực và chấp thuận
    AS-->>UI: Redirect URI kèm authorization code và state
    UI->>AS: POST /token với code và code_verifier
    AS->>AS: Tính lại challenge và xác minh PKCE
    AS-->>UI: Access token (và ID token nếu là OIDC)
    UI->>API: Request API với Bearer access token
    API->>API: Xác minh chữ ký, issuer, audience, expiry và quyền
    API-->>UI: Response API
~~~

Chi tiết các bước:

1. Người dùng bấm **Authorize** trong Swagger UI.
2. Swagger UI tạo verifier ngẫu nhiên, tính challenge bằng SHA-256 và lưu verifier cho giao dịch hiện tại.
3. Swagger UI chuyển trình duyệt đến authorization endpoint với các tham số như **response_type=code**, **client_id**, **redirect_uri**, **scope**, **state**, **code_challenge** và **code_challenge_method=S256**.
4. Người dùng đăng nhập tại Authorization Server và chấp thuận các scope được yêu cầu.
5. Authorization Server chuyển hướng về redirect URI đã đăng ký, kèm authorization code và state.
6. Swagger UI kiểm tra state, sau đó gửi token request với authorization code và code_verifier.
7. Authorization Server xác minh verifier khớp challenge đã lưu, kiểm tra các điều kiện khác rồi trả token.
8. Swagger UI dùng access token trong header Authorization: Bearer khi gọi operation được bảo vệ.

**state** liên kết request authorization với callback và giúp bảo vệ giao dịch khỏi request giả mạo. Với OIDC, client còn có thể dùng **nonce** để liên kết ID token với lần đăng nhập. PKCE, state và nonce có mục đích liên quan nhưng không thay thế hoàn toàn cho nhau.

## 3. PKCE với S256 và yêu cầu từ Authorization Server

PKCE có hai phương pháp thường được nhắc đến:

| Phương pháp | Cách tính | Đánh giá |
| --- | --- | --- |
| **plain** | code_challenge bằng chính code_verifier | Chỉ dành cho môi trường tương thích cũ khi không hỗ trợ S256 |
| **S256** | SHA-256 rồi Base64URL encode | Nên dùng; không để lộ verifier trong authorization request |

Client có khả năng dùng S256 phải chọn S256. RFC 9700 yêu cầu Authorization Server hỗ trợ PKCE và yêu cầu kiểm tra code_verifier khi authorization request đã gửi code_challenge. Server cũng cần ngăn downgrade, không được chấp nhận verifier trong token request nếu authorization request tương ứng không có challenge.

Khi cấu hình Authorization Server, cần:

- Cho phép grant type Authorization Code.
- Đánh dấu Swagger UI là public client nếu client chạy hoàn toàn trong browser.
- Bắt buộc PKCE và ưu tiên phương pháp S256.
- Đăng ký redirect URI chính xác.
- Cấu hình scopes được phép cấp cho client.
- Không yêu cầu client secret đối với public client.
- Đặt thời hạn authorization code ngắn và bảo đảm code chỉ dùng một lần.

Một số Authorization Server công bố khả năng PKCE trong metadata, ví dụ trường **code_challenge_methods_supported**. Nếu metadata không được công bố, cần xác nhận bằng cấu hình của nhà cung cấp hoặc tài liệu triển khai.

## 4. Khai báo Authorization Code Flow trong OpenAPI

OpenAPI mô tả OAuth 2.0 bằng Security Scheme Object có **type: oauth2**. Với Authorization Code Flow, khai báo **flows.authorizationCode**, **authorizationUrl**, **tokenUrl** và các scopes.

Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  version: 1.0.0

components:
  securitySchemes:
    shopOAuth:
      type: oauth2
      description: Đăng nhập qua Authorization Code Flow với PKCE.
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            openid: Xác thực người dùng bằng OpenID Connect
            profile: Đọc thông tin hồ sơ cơ bản
            orders.read: Đọc đơn hàng
            orders.write: Tạo và cập nhật đơn hàng

paths:
  /api/orders:
    get:
      summary: Liệt kê đơn hàng
      security:
        - shopOAuth:
            - orders.read
      responses:
        '200':
          description: Danh sách đơn hàng
        '401':
          description: Chưa xác thực hoặc access token không hợp lệ
        '403':
          description: Token không có scope cần thiết
~~~

Trong ví dụ:

- **authorizationUrl** là endpoint người dùng được chuyển đến để đăng nhập và chấp thuận.
- **tokenUrl** là endpoint nhận authorization code và trả token.
- **scopes** liệt kê quyền mà Authorization Server có thể cấp.
- **security** trên operation chỉ rõ scope cần thiết để gọi API.

Nếu một operation không cần xác thực, có thể đặt **security: []** ở operation đó để ghi đè yêu cầu bảo mật cấp tài liệu. Không nên thêm scope chỉ để làm nút Authorize hiển thị; scope phải phản ánh quyền thật của API.

OpenAPI mô tả loại flow và các endpoint OAuth. **OpenAPI không có trường chuẩn để bật PKCE hoặc bắt buộc code_challenge_method=S256.** Việc bật PKCE trong Swagger UI là cấu hình của công cụ giao diện; việc bắt buộc và xác minh PKCE là trách nhiệm của Authorization Server.

## 5. Khai báo security scheme bằng annotation Swagger

Springdoc đọc các annotation OpenAPI từ controller và cấu hình. Có thể khai báo OAuth2 Security Scheme ở một lớp cấu hình:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "shopOAuth",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl =
                "https://identity.example.com/oauth2/authorize",
            tokenUrl =
                "https://identity.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "openid",
                    description = "Xác thực người dùng bằng OIDC"
                ),
                @OAuthScope(
                    name = "profile",
                    description = "Đọc thông tin hồ sơ"
                ),
                @OAuthScope(
                    name = "orders.read",
                    description = "Đọc đơn hàng"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Tạo và cập nhật đơn hàng"
                )
            }
        )
    )
)
class OpenApiOAuthConfiguration {}
~~~

Gắn security requirement lên operation:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    @SecurityRequirement(
        name = "shopOAuth",
        scopes = {"orders.read"}
    )
    List<OrderView> findOrders() {
        return orderService.findOrders();
    }
}
~~~

Tên **shopOAuth** trong SecurityRequirement phải khớp chính xác với tên scheme. Scope trong requirement phải được khai báo trong OAuth Flow Object. Annotation chỉ sinh metadata; Spring Security hoặc API gateway vẫn phải thực thi việc xác thực và phân quyền.

## 6. Bật PKCE trong springdoc và Swagger UI

Springdoc cung cấp các thuộc tính cấu hình Swagger UI. Với Authorization Code Flow, bật thuộc tính **usePkceWithAuthorizationCodeGrant**.

Ví dụ trong application.yml:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
    oauth:
      client-id: shop-swagger-ui-public
      scopes:
        - openid
        - profile
        - orders.read
      use-pkce-with-authorization-code-grant: true
    persist-authorization: false
~~~

Hoặc application.properties:

~~~properties
springdoc.swagger-ui.oauth2-redirect-url=https://docs.example.com/swagger-ui/oauth2-redirect.html
springdoc.swagger-ui.oauth.client-id=shop-swagger-ui-public
springdoc.swagger-ui.oauth.scopes=openid,profile,orders.read
springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant=true
springdoc.swagger-ui.persist-authorization=false
~~~

Ý nghĩa:

| Thuộc tính | Vai trò |
| --- | --- |
| **oauth2-redirect-url** | URL nhận redirect sau khi người dùng xác thực |
| **oauth.client-id** | Client ID đã đăng ký cho Swagger UI |
| **oauth.scopes** | Các scope ban đầu được chọn trong giao diện |
| **oauth.use-pkce-with-authorization-code-grant** | Bật tạo code verifier và challenge cho Authorization Code Flow |
| **persist-authorization** | Quyết định có lưu trạng thái authorization qua lần tải lại/đóng mở browser hay không |

Springdoc UI Properties Reference ghi nhận **usePkceWithAuthorizationCodeGrant** chỉ áp dụng cho Authorization Code Flow và mặc định là **false**. Vì vậy, hãy bật rõ ràng thay vì giả định Swagger UI tự dùng PKCE.

Không cấu hình **springdoc.swagger-ui.oauth.client-secret** cho client chạy trong browser ở môi trường production. Client secret nhúng vào JavaScript hoặc cấu hình được tải xuống browser không còn bí mật. PKCE là cơ chế bảo vệ authorization code; nó không biến browser thành confidential client.

## 7. Cấu hình Swagger UI độc lập bằng initOAuth

Nếu ứng dụng tự nhúng Swagger UI thay vì dùng trang do springdoc phục vụ, có thể gọi **initOAuth** sau khi tạo Swagger UI instance:

~~~javascript
const ui = SwaggerUIBundle({
    url: "/v3/api-docs",
    dom_id: "#swagger-ui",
    oauth2RedirectUrl:
        "https://docs.example.com/swagger-ui/oauth2-redirect.html"
});

ui.initOAuth({
    clientId: "shop-swagger-ui-public",
    scopes: "openid profile orders.read",
    usePkceWithAuthorizationCodeGrant: true
});
~~~

**oauth2RedirectUrl** là cấu hình cấp Swagger UI instance; **usePkceWithAuthorizationCodeGrant** là tùy chọn OAuth được truyền vào **initOAuth**. Không đặt tùy chọn PKCE trong OpenAPI Security Scheme vì đó không phải trường chuẩn của đặc tả.

Khi dùng springdoc, nên cấu hình qua application properties/yaml để springdoc truyền các giá trị vào Swagger UI. Chỉ dùng **initOAuth** trực tiếp khi bạn tự quản lý trang hoặc bundle Swagger UI.

## 8. Đăng ký redirect URI chính xác

Redirect URI là địa chỉ Swagger UI nhận authorization response. Với cấu hình mặc định của springdoc, đường dẫn thường là:

~~~text
/swagger-ui/oauth2-redirect.html
~~~

Khi triển khai production, nên cấu hình URL đầy đủ mà browser thực sự truy cập, ví dụ:

~~~text
https://docs.example.com/swagger-ui/oauth2-redirect.html
~~~

Đăng ký đúng URI này trong cấu hình client tại Authorization Server. URI gửi trong authorization request phải khớp với URI đã đăng ký theo quy tắc so khớp chính xác của nhà cung cấp và OAuth security best practice.

Kiểm tra các trường hợp:

- Ứng dụng chạy sau reverse proxy.
- Có context path như /shop.
- Swagger UI được đổi đường dẫn bằng **springdoc.swagger-ui.path**.
- TLS kết thúc tại load balancer hoặc ingress.
- Tên miền tài liệu khác tên miền API.

Nếu external URL là **https://docs.example.com/shop/swagger-ui/oauth2-redirect.html**, cả cấu hình Swagger UI và redirect URI đã đăng ký phải dùng địa chỉ ngoài này. Không đăng ký một URI localhost rồi đưa client đó vào production.

## 9. Cấu hình Authorization Server cho public client

Trong Identity Provider, tạo client dành riêng cho Swagger UI. Tên và giao diện cấu hình thay đổi theo nhà cung cấp, nhưng các thuộc tính cần tương đương:

| Thuộc tính | Giá trị gợi ý |
| --- | --- |
| Client ID | **shop-swagger-ui-public** |
| Client type | Public |
| Grant type | Authorization Code |
| PKCE | Required |
| PKCE method | S256 |
| Client secret | Không dùng cho public browser client |
| Redirect URI | URL **oauth2-redirect.html** chính xác |
| Allowed scopes | **openid**, **profile**, **orders.read** |
| Token endpoint | HTTPS |

Không bật Implicit Flow chỉ để Swagger UI dễ đăng nhập. Authorization Code với PKCE là lựa chọn phù hợp hơn cho public client chạy trong browser.

Nếu Authorization Server có tùy chọn “require PKCE”, bật tùy chọn đó. Chỉ bật PKCE phía Swagger UI nhưng server vẫn chấp nhận code exchange không có verifier sẽ làm mất mục tiêu bảo vệ.

Nếu hệ thống dùng OIDC, kiểm tra discovery document tại endpoint well-known để xác nhận issuer, authorization endpoint, token endpoint và khả năng PKCE. Không tự đoán endpoint từ tên realm hoặc tenant.

## 10. Phân biệt OAuth2 và OpenID Connect

OAuth 2.0 tập trung vào **ủy quyền truy cập tài nguyên**. OpenID Connect bổ sung lớp xác thực danh tính trên OAuth 2.0.

| Khái niệm | Mục đích |
| --- | --- |
| Access token | Cho phép client gọi resource server theo quyền được cấp |
| ID token | Mang thông tin xác thực người dùng cho OIDC client |
| Scope **openid** | Kích hoạt yêu cầu OIDC |
| Scope **profile** | Yêu cầu một số claim hồ sơ người dùng |
| Scope API như **orders.read** | Quyền truy cập tài nguyên đơn hàng |
| PKCE | Ràng buộc authorization code với client đã khởi tạo giao dịch |
| OIDC nonce | Liên kết ID token với yêu cầu xác thực cụ thể |

Khi gọi API, Swagger UI thường gửi **access token** trong header Bearer. Không gửi ID token thay cho access token chỉ vì cả hai đều có dạng JWT. Resource Server cần kiểm tra audience, issuer, chữ ký, thời hạn và quyền phù hợp.

Nếu chỉ cần OAuth2 để lấy quyền gọi API, có thể không yêu cầu scope **openid**. Nếu muốn đăng nhập và hiển thị danh tính người dùng trong luồng OIDC, thêm **openid** và các scope cần thiết theo cấu hình Identity Provider.

## 11. Token endpoint và CORS

Authorization endpoint thường được mở bằng điều hướng trình duyệt đến trang đăng nhập. Token endpoint lại được Swagger UI gọi bằng request JavaScript sau khi nhận authorization code. Nếu token endpoint nằm ở origin khác với trang Swagger UI, Authorization Server cần cho phép origin của tài liệu qua CORS.

Kiểm tra:

- **Access-Control-Allow-Origin** khớp origin Swagger UI.
- Token endpoint cho phép phương thức POST.
- Các header và content type mà Swagger UI gửi được chấp nhận.
- Response token có CORS headers phù hợp để JavaScript đọc được.
- Không dùng wildcard origin khi request có credentials theo cấu hình yêu cầu.

Không phải mọi lỗi CORS đều nằm ở Spring Boot API. Có thể request API đã thành công nhưng bước đổi code tại token endpoint bị browser chặn. Khi đó, mở Network panel và xác định request thất bại là /token hay endpoint resource server.

Nếu Swagger UI và API được phục vụ cùng origin, việc gọi API không cần CORS. Nhưng token endpoint vẫn có thể là origin khác, do đó cần kiểm tra riêng cấu hình CORS tại Identity Provider.

## 12. Spring Boot Resource Server xác minh access token

Swagger UI chỉ là OAuth client dùng để lấy token. API Spring Boot vẫn phải xác minh access token trước khi xử lý request. Với JWT, Spring Security Resource Server có thể dùng issuer URI để khám phá metadata và khóa xác minh:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/
~~~

Issuer URI phải khớp với claim **iss** trong access token và cấu hình của Authorization Server. Ứng dụng cũng cần kiểm tra audience nếu hệ thống phát hành token cho nhiều resource server.

Ví dụ cấu hình security chain tối giản:

~~~java
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
                .requestMatchers("/v3/api-docs/**", "/swagger-ui/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest()
                    .authenticated()
            )
            .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Ví dụ dùng authority **SCOPE_orders.read** để minh họa mapping scope phổ biến của Spring Security. Cấu hình thực tế cần thống nhất claim scope/scp của nhà cung cấp, audience và quy tắc phân quyền. Không mở toàn bộ API chỉ vì Swagger UI đã có nút Authorize.

Trong một số ứng dụng, /v3/api-docs/** hoặc /swagger-ui/** cũng cần được bảo vệ bằng authentication riêng. Quyết định này phụ thuộc việc tài liệu có công khai hay chứa thông tin nội bộ; không bắt buộc phải permitAll.

## 13. Access token, scopes và security requirement

OpenAPI dùng Security Requirement Object để mô tả scope cần cho từng operation. Ví dụ:

~~~yaml
paths:
  /api/orders:
    get:
      security:
        - shopOAuth:
            - orders.read
    post:
      security:
        - shopOAuth:
            - orders.write
~~~

Swagger UI dùng security scheme để hiển thị nút Authorize và các scope được chọn. Khi người dùng cấp quyền, Swagger UI lấy token theo flow được khai báo. Khi bấm Try it out, UI gửi access token đến operation.

Scope trong OpenAPI phải khớp với scope mà Authorization Server thực sự cấp. Nếu tài liệu yêu cầu **orders.read** nhưng token chỉ có **profile**, API có thể trả 403 dù token đã hợp lệ về chữ ký và thời hạn.

Phân biệt:

- **401 Unauthorized:** thiếu token, token không hợp lệ, hết hạn hoặc không thể xác minh.
- **403 Forbidden:** token hợp lệ nhưng không có quyền/scope cần thiết.

## 14. Lưu authorization trong Swagger UI

Springdoc có thuộc tính **springdoc.swagger-ui.persist-authorization**. Mặc định là **false**. Khi bật, dữ liệu authorization được giữ lại qua refresh hoặc đóng/mở browser theo cơ chế lưu trữ của Swagger UI.

Chỉ bật persistence khi có nhu cầu rõ ràng và đã đánh giá môi trường sử dụng. Trên máy dùng chung, máy phòng lab hoặc máy tính công cộng, việc giữ token làm tăng khả năng người khác tiếp tục dùng phiên đã xác thực. Trong tài liệu nội bộ, nên hướng dẫn người dùng logout hoặc xóa authorization sau khi kiểm thử.

Không đưa access token, refresh token, client secret hoặc thông tin tài khoản thật vào:

- application.yml được commit.
- JavaScript tĩnh hoặc cấu hình Swagger UI công khai.
- ví dụ OpenAPI.
- ảnh chụp màn hình hoặc log CI.

PKCE bảo vệ authorization code. Nó không ngăn XSS đọc token đang được ứng dụng sử dụng, không thay thế HTTPS và không tự giải quyết việc lưu token an toàn trong browser.

## 15. Kiểm thử Authorization Code và PKCE

### Kiểm tra OpenAPI JSON

Khởi động ứng dụng và tải đặc tả:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra security scheme:

~~~bash
jq '.components.securitySchemes.shopOAuth' openapi.json
~~~

Kết quả cần có:

- **type** là **oauth2**.
- **flows.authorizationCode** tồn tại.
- **authorizationUrl** và **tokenUrl** đúng với Identity Provider.
- Scopes có tên và mô tả phù hợp.
- Operation có security requirement và scope tương ứng.

### Kiểm tra cấu hình Swagger UI

Mở trang Swagger UI, bấm Authorize và kiểm tra:

1. Client ID đúng là public client đã đăng ký.
2. Redirect URI đúng URL ngoài mà browser đang dùng.
3. Scope ban đầu có các scope cần thiết.
4. Authorization request có **response_type=code**.
5. Có **code_challenge** và **code_challenge_method=S256**.
6. Không có **code_verifier** trong authorization URL.

### Kiểm tra token request

Sau khi đăng nhập, xem request đến token endpoint:

- Có **grant_type=authorization_code**.
- Có authorization code.
- Có **redirect_uri** trùng với URI của authorization request.
- Có **client_id** của public client.
- Có **code_verifier**.
- Không gửi client secret cho public client.

Authorization Server phải tính lại challenge từ verifier và chỉ trả token nếu giá trị khớp challenge đã lưu cùng code.

### Kiểm tra request API

Sau khi token được cấp:

- Request API có **Authorization: Bearer ...**.
- Access token có issuer và audience đúng.
- Token chưa hết hạn.
- Scope/authority đáp ứng operation.
- API trả 200 khi đủ quyền, 401 khi token không hợp lệ và 403 khi thiếu quyền.

## 16. Lỗi thường gặp

**Nút Authorize không dùng PKCE.** Kiểm tra flow là **authorizationCode**, cấu hình **use-pkce-with-authorization-code-grant** đã bật và Swagger UI version hỗ trợ tùy chọn này. Tùy chọn PKCE không áp dụng cho Implicit hoặc Client Credentials Flow.

**Authorization Server báo PKCE required nhưng token request thiếu verifier.** Kiểm tra Swagger UI đang dùng đúng Authorization Code Flow và cấu hình PKCE được truyền đến **initOAuth**. Không chỉ kiểm tra file YAML OpenAPI vì YAML không bật PKCE.

**Token endpoint báo invalid_grant hoặc code_verifier mismatch.** Kiểm tra client có giữ đúng verifier của giao dịch hiện tại, authorization code chưa hết hạn/chưa dùng và Authorization Server lưu challenge đúng với code.

**Authorization Server báo redirect_uri mismatch.** So sánh chính xác scheme, host, port, path và dấu slash cuối giữa cấu hình springdoc, request authorization và client registration.

**Swagger UI quay lại trang lỗi sau khi đăng nhập.** Kiểm tra **oauth2-redirect.html** có truy cập được, reverse proxy có giữ context path và cấu hình external URL có đúng không.

**Đăng nhập thành công nhưng API trả 401.** Kiểm tra Swagger UI gửi access token hay ID token, token có đúng audience/issuer, chữ ký hợp lệ và chưa hết hạn không.

**API trả 403.** Token có thể hợp lệ nhưng thiếu scope. Đối chiếu scope trong OpenAPI, scope được chọn ở Swagger UI, scope được Authorization Server cấp và authority mapping của Spring Security.

**Token endpoint bị CORS chặn.** Kiểm tra origin của Swagger UI trong cấu hình CORS của Authorization Server. Phân biệt request /token với request đến resource server.

**Đã bật PKCE nhưng vẫn cấu hình client secret trong application.yml.** Xóa client secret khỏi cấu hình browser production. PKCE không làm secret trở nên an toàn khi đã công khai.

**Swagger UI tự giữ token sau khi refresh.** Kiểm tra **persist-authorization**. Tắt nếu không cần lưu trạng thái xác thực qua lần tải lại.

**Dùng Implicit Flow vì dễ cấu hình hơn.** Chuyển sang Authorization Code với PKCE cho public client và xác nhận Authorization Server hỗ trợ S256.

## 17. Checklist triển khai

- [ ] Khai báo OAuth2 Security Scheme với **authorizationCode**.
- [ ] Dùng authorization URL và token URL HTTPS chính xác.
- [ ] Khai báo scopes và gắn security requirement vào operation.
- [ ] Đăng ký Swagger UI là public client khi client chạy trong browser.
- [ ] Bật Authorization Code grant và bắt buộc PKCE tại Authorization Server.
- [ ] Dùng PKCE method S256.
- [ ] Bật **springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant=true**.
- [ ] Cấu hình **client-id** nhưng không đưa client secret vào browser production.
- [ ] Đăng ký redirect URI khớp chính xác với URL ngoài.
- [ ] Cấu hình CORS cho token endpoint nếu khác origin.
- [ ] Kiểm tra state và nonce nếu dùng OIDC.
- [ ] Dùng access token cho API và xác minh token ở Spring Security Resource Server.
- [ ] Kiểm tra issuer, audience, expiry và scope.
- [ ] Giữ **persist-authorization** tắt nếu không có nhu cầu lưu token.
- [ ] Kiểm tra request authorization, token và API trong Developer Tools.

## 18. Kết luận

Authorization Code Flow kết hợp PKCE là lựa chọn phù hợp cho Swagger UI chạy trong browser vì client không thể giữ bí mật một client secret. OpenAPI mô tả flow, endpoint và scopes; springdoc truyền cấu hình OAuth vào Swagger UI; Swagger UI tạo verifier/challenge và thực hiện code exchange; Authorization Server bắt buộc xác minh S256 trước khi cấp token. API Spring Boot vẫn phải xác minh access token và quyền ở phía server. Khi redirect URI, client registration, PKCE, CORS và scopes được cấu hình đồng bộ, người dùng có thể đăng nhập trong Swagger UI và thử API theo đúng hợp đồng bảo mật.

## 19. Nguồn tham khảo

- [Springdoc — Swagger UI Properties Reference](https://springdoc.org/ui-properties.html): các thuộc tính **oauth.clientId**, **oauth.scopes**, **oauth.usePkceWithAuthorizationCodeGrant**, **oauth2RedirectUrl** và **persistAuthorization**.
- [Swagger UI — OAuth 2.0 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/): cấu hình **initOAuth** và **usePkceWithAuthorizationCodeGrant**.
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): cấu hình redirect URL của Swagger UI.
- [OpenAPI Specification 3.1.2 — Security Scheme Object](https://spec.openapis.org/oas/v3.1.2.html#security-scheme-object): mô tả OAuth2 và Authorization Code Flow trong OpenAPI.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): tạo và xác minh code verifier/challenge.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): yêu cầu PKCE cho public clients và khuyến nghị S256.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scope openid, ID token và nonce.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT access token tại API.
