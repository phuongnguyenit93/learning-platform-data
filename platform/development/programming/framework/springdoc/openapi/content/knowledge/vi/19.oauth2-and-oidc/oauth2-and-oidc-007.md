# Cấu hình OAuth client trên Swagger UI

Swagger UI có thể khởi chạy quy trình OAuth 2.0 để người dùng đăng nhập và cấp quyền trước khi thử gọi API. Khi dùng springdoc-openapi, phần mô tả OAuth flow được khai báo trong đặc tả OpenAPI, còn thông tin client dành cho giao diện được cấu hình bằng các thuộc tính `springdoc.swagger-ui.oauth`. Hai phần này phối hợp với nhau: OpenAPI cho Swagger UI biết authorization server, token endpoint và scope; cấu hình client cho biết client ID, redirect URL và cách thực hiện quy trình cấp quyền.

Với giao diện chạy trong trình duyệt, lựa chọn phù hợp cho ứng dụng mới thường là Authorization Code Flow kết hợp PKCE. Swagger UI là ứng dụng phía trình duyệt, vì vậy không thể giữ bí mật một client secret được nhúng trong cấu hình JavaScript hoặc gửi xuống trình duyệt. Hãy đăng ký Swagger UI như một public client, cấu hình redirect URI chính xác tại nhà cung cấp danh tính và bật PKCE.

## 1. Phân biệt cấu hình OAuth trong OpenAPI và OAuth client của Swagger UI

Có hai lớp cấu hình riêng:

| Lớp | Nơi khai báo | Vai trò |
| --- | --- | --- |
| OAuth Security Scheme | `components.securitySchemes` trong OpenAPI | Khai báo flow, authorization URL, token URL và các scope API hỗ trợ |
| OAuth Security Requirement | `security` ở cấp API hoặc operation | Chỉ ra operation cần scheme và scope nào |
| OAuth client của Swagger UI | `springdoc.swagger-ui.oauth` hoặc `ui.initOAuth(...)` | Cung cấp client ID, scope được chọn ban đầu và tùy chọn PKCE cho giao diện |
| OAuth redirect URL | `springdoc.swagger-ui.oauth2-redirect-url` | Địa chỉ callback mà authorization server chuyển trình duyệt về sau khi người dùng cấp quyền |

Ví dụ: OpenAPI có thể khai báo `authorizationUrl` là `https://identity.example.com/oauth2/authorize` và `tokenUrl` là `https://identity.example.com/oauth2/token`. Swagger UI dùng client ID đã đăng ký tại identity provider, chuyển người dùng đến authorization endpoint rồi nhận callback tại redirect URI đã đăng ký.

`clientId` của Swagger UI phải khớp client registration tại identity provider. Nó không phải client ID của API resource server, cũng không phải tên Security Scheme trong OpenAPI. Tên scheme là khóa mà operation dùng để tham chiếu; client ID là danh tính ứng dụng giao diện khi yêu cầu token.

## 2. Khai báo Authorization Code Flow trong OpenAPI

Trước khi cấu hình giao diện, hãy mô tả đúng OAuth flow trong đặc tả. Ví dụ API quản lý đơn hàng dùng Authorization Code Flow:

~~~yaml
components:
  securitySchemes:
    ordersOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://identity.example.com/oauth2/authorize
          tokenUrl: https://identity.example.com/oauth2/token
          scopes:
            openid: Xác thực danh tính người dùng
            profile: Đọc thông tin hồ sơ cơ bản
            orders:read: Đọc đơn hàng
            orders:write: Tạo và cập nhật đơn hàng

paths:
  /api/orders:
    get:
      security:
        - ordersOAuth:
            - orders:read
      responses:
        '200':
          description: Danh sách đơn hàng
~~~

Các trường quan trọng:

- `type: oauth2` cho biết scheme dùng OAuth 2.0.
- `flows.authorizationCode` chọn Authorization Code Flow.
- `authorizationUrl` là endpoint bắt đầu đăng nhập và cấp quyền.
- `tokenUrl` là endpoint đổi authorization code lấy access token.
- `scopes` liệt kê các quyền API công bố.
- `security` trên operation yêu cầu scope mà client phải có để gọi operation.

Địa chỉ trong ví dụ là placeholder. Thay bằng endpoint thực tế do identity provider cung cấp. Không tự suy đoán URL nếu nhà cung cấp có tenant, realm hoặc path riêng. Các endpoint OAuth phải dùng HTTPS trong môi trường triển khai.

Có thể khai báo cùng cấu trúc bằng annotation:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

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
public class OAuthApiDocumentationConfiguration {
}
~~~

Operation có thể yêu cầu scope cụ thể:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import org.springframework.web.bind.annotation.GetMapping;

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
~~~

Tên `ordersOAuth` trong requirement phải trùng tên scheme. Scope trong requirement phải được khai báo trong flow tương ứng và phải khớp với scope mà authorization server cấp.

## 3. Đăng ký Swagger UI như một OAuth public client

Swagger UI chạy bằng JavaScript trong trình duyệt của người dùng. Mọi cấu hình client được tải về trình duyệt đều có thể được xem qua Developer Tools, source map, Network response hoặc bộ nhớ của trang. Do đó, hãy xem Swagger UI là một public client.

Khi tạo client registration tại identity provider, thường cần khai báo:

| Trường đăng ký | Giá trị cần xác định |
| --- | --- |
| Client type | Public client hoặc SPA/public application theo thuật ngữ của nhà cung cấp |
| Grant type | Authorization Code |
| PKCE | Bắt buộc hoặc bật cho client |
| Client ID | Một định danh công khai dành cho Swagger UI |
| Redirect URI | URL callback chính xác của Swagger UI |
| Allowed scopes | Các scope mà giao diện cần yêu cầu, ví dụ `openid`, `profile`, `orders:read` |
| Allowed web origins | Origin của trang tài liệu nếu identity provider cần cấu hình CORS cho luồng trình duyệt |

Không đăng ký Swagger UI như một confidential client chỉ để có thể nhúng client secret vào application.yml. Client secret đặt trong cấu hình server sẽ được springdoc đưa vào cấu hình giao diện và gửi đến trình duyệt; người dùng có thể lấy được giá trị đó. Mã nguồn Java hoặc biến môi trường không làm secret trở thành bí mật sau khi giá trị đã được xuất ra client.

Nếu chính sách tổ chức bắt buộc dùng confidential client secret, hãy đặt OAuth client ở backend thông qua mô hình Backend for Frontend (BFF) hoặc một thành phần server-side phù hợp. Trình duyệt làm việc với phiên của BFF; secret được giữ ở server và không được gửi xuống Swagger UI.

## 4. Xác định redirect URI

Sau khi người dùng đăng nhập và chấp thuận quyền, authorization server chuyển trình duyệt về redirect URI của ứng dụng. Swagger UI cung cấp trang callback riêng, mặc định của springdoc là:

~~~text
/swagger-ui/oauth2-redirect.html
~~~

Nếu tài liệu được phục vụ tại:

~~~text
https://docs.example.com/swagger-ui.html
~~~

redirect URI công khai thường có dạng:

~~~text
https://docs.example.com/swagger-ui/oauth2-redirect.html
~~~

Đăng ký chính xác URI này tại identity provider. Scheme, hostname, port, context path và path phải khớp với URL mà trình duyệt thực sự sử dụng. Nhiều nhà cung cấp so khớp redirect URI chính xác và từ chối URI chỉ khác một dấu gạch chéo hoặc một prefix.

Có thể cấu hình redirect URL tường minh trong application.yml:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
~~~

Nếu ứng dụng chạy dưới context path `/store`, hoặc reverse proxy công bố tài liệu dưới prefix khác, redirect URI phải chứa prefix công khai tương ứng. Không đăng ký URL nội bộ như `http://localhost:8080/...` cho môi trường production nếu người dùng bên ngoài không truy cập ứng dụng tại địa chỉ đó.

## 5. Cấu hình client ID và PKCE trong application.yml

Với springdoc-openapi, các tùy chọn OAuth của Swagger UI nằm dưới prefix `springdoc.swagger-ui.oauth`. Ví dụ cấu hình Authorization Code Flow cho một public client:

~~~yaml
springdoc:
  swagger-ui:
    oauth2-redirect-url: https://docs.example.com/swagger-ui/oauth2-redirect.html
    oauth:
      client-id: swagger-ui-public
      app-name: Store API Documentation
      scopes:
        - openid
        - profile
        - orders:read
      use-pkce-with-authorization-code-grant: true
    persist-authorization: false
~~~

Ý nghĩa:

- `client-id` là client ID công khai đã đăng ký tại identity provider.
- `app-name` là tên ứng dụng hiển thị trong cửa sổ cấp quyền.
- `scopes` là các scope được chọn trước trong giao diện Authorize.
- `use-pkce-with-authorization-code-grant` bật PKCE cho Authorization Code Flow.
- `persist-authorization: false` giữ hành vi mặc định không lưu thông tin xác thực qua lần tải lại hoặc đóng trình duyệt.
- `oauth2-redirect-url` là callback URL của Swagger UI.

Các thuộc tính Swagger UI được springdoc hỗ trợ như Spring Boot properties. Có thể dùng cùng cấu hình trong application.properties:

~~~properties
springdoc.swagger-ui.oauth2-redirect-url=https://docs.example.com/swagger-ui/oauth2-redirect.html
springdoc.swagger-ui.oauth.client-id=swagger-ui-public
springdoc.swagger-ui.oauth.app-name=Store API Documentation
springdoc.swagger-ui.oauth.scopes=openid,profile,orders:read
springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant=true
springdoc.swagger-ui.persist-authorization=false
~~~

Tên cấu hình trong YAML dùng kebab-case theo relaxed binding của Spring Boot. Nếu IDE không nhận thuộc tính hoặc phiên bản springdoc đang dùng khác, hãy đối chiếu Configuration Properties của đúng phiên bản dependency.

## 6. PKCE hoạt động như thế nào?

PKCE (Proof Key for Code Exchange) bổ sung bằng chứng mà client phải cung cấp khi đổi authorization code lấy token. Nó giúp giảm nguy cơ kẻ khác chặn được authorization code rồi dùng code đó để lấy token.

Trong Authorization Code Flow có PKCE, quy trình ở mức khái quát:

1. Swagger UI tạo một chuỗi ngẫu nhiên gọi là `code_verifier`.
2. Giao diện tính `code_challenge` từ verifier, thường dùng phương thức `S256`.
3. Trình duyệt chuyển đến authorization endpoint với `response_type=code`, `client_id`, `redirect_uri`, `state`, scope và code challenge.
4. Người dùng đăng nhập và chấp thuận quyền tại identity provider.
5. Identity provider chuyển trình duyệt về redirect URI cùng authorization code và state.
6. Swagger UI xác minh state, sau đó gửi authorization code cùng `code_verifier` đến token endpoint.
7. Identity provider kiểm tra verifier có khớp challenge ban đầu hay không rồi mới cấp token.

Khi bật:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      use-pkce-with-authorization-code-grant: true
~~~

Swagger UI tự xử lý việc tạo và gửi các giá trị PKCE trong flow được hỗ trợ. Không tự thêm code challenge hoặc verifier vào query parameter bằng tay. Hãy kiểm tra cấu hình authorization server cho phép PKCE và chấp nhận phương thức `S256`.

PKCE không thay thế client secret và client secret cũng không thay thế PKCE. Với Swagger UI chạy trong trình duyệt, nên dùng public client + PKCE thay vì cố giữ secret trong frontend. Tài liệu Swagger UI cũng ghi rõ tùy chọn PKCE không ẩn trường client secret.

## 7. Chọn scope trong Swagger UI

Có hai nơi mô tả scope:

- Trong OpenAPI flow, `scopes` xác định các scope mà API công bố.
- Trong cấu hình Swagger UI, `springdoc.swagger-ui.oauth.scopes` xác định các scope được chọn trước trong giao diện.

Ví dụ OpenAPI công bố:

~~~yaml
flows:
  authorizationCode:
    authorizationUrl: https://identity.example.com/oauth2/authorize
    tokenUrl: https://identity.example.com/oauth2/token
    scopes:
      orders:read: Đọc đơn hàng
      orders:write: Tạo và cập nhật đơn hàng
~~~

Swagger UI có thể chọn trước:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      scopes:
        - orders:read
~~~

Operation đọc đơn hàng yêu cầu `orders:read`:

~~~yaml
security:
  - ordersOAuth:
      - orders:read
~~~

Scope được chọn trước không tự cấp quyền cho người dùng. Identity provider quyết định scope nào được cấp dựa trên client registration, consent, người dùng và chính sách của nó. API resource server phải kiểm tra access token và quyền tương ứng khi request đến.

Nếu người dùng chọn thêm scope trong hộp thoại Authorize, hãy chắc rằng scope đó tồn tại trong OpenAPI flow, client registration và chính sách của identity provider. Không yêu cầu scope rộng hơn mức cần thiết; dùng quyền tối thiểu cho thao tác đang kiểm thử.

## 8. Cấu hình scope separator và tham số bổ sung

Swagger UI hỗ trợ `scopeSeparator` để xác định cách ghép các scope khi gửi authorization request. Mặc định là dấu cách, được URL encode thành `%20`. Thông thường không cần đổi giá trị này nếu identity provider hỗ trợ định dạng OAuth chuẩn.

Có thể cấu hình thêm query parameter nếu nhà cung cấp có yêu cầu riêng:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      scope-separator: " "
      additional-query-string-params:
        audience: https://api.example.com
~~~

`additional-query-string-params` thêm tham số vào authorization URL và token URL theo cơ chế của Swagger UI. Chỉ dùng cho tham số công khai, được identity provider yêu cầu và không chứa mật khẩu, client secret, API key hay token. Tránh dùng nó để lách cấu hình OAuth chuẩn hoặc đưa dữ liệu nhạy cảm vào URL.

Nếu cần tham số khác nhau giữa authorization request và token request, hoặc cần logic phức tạp, hãy kiểm tra khả năng của identity provider và Swagger UI hiện hành. Có thể cần cấu hình OAuth client ở backend thay vì cố nhồi toàn bộ logic vào cấu hình giao diện.

## 9. Khi nào dùng HTTP Basic ở token endpoint?

Một số authorization server yêu cầu client xác thực tại token endpoint bằng HTTP Basic khi đổi authorization code. Swagger UI có tùy chọn:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      use-basic-authentication-with-access-code-grant: true
~~~

Tùy chọn này yêu cầu Swagger UI gửi thông tin client bằng HTTP Basic trong request token theo cơ chế được hỗ trợ. Chỉ bật khi hợp đồng của identity provider yêu cầu cách xác thực đó và client phù hợp với mô hình triển khai.

Với Swagger UI chạy trực tiếp trong trình duyệt, không dùng tùy chọn này để gửi một client secret production được nhúng vào giao diện. Nếu token endpoint yêu cầu confidential client secret, nên chuyển quy trình đổi code sang backend/BFF. Với public client + PKCE, thông thường không gửi client secret.

Không nhầm HTTP Basic của client tại token endpoint với Basic Authentication của API resource. Đây là hai mục đích khác nhau: một cái xác thực OAuth client với authorization server; cái còn lại bảo vệ request đến API.

## 10. Không đặt client secret trong môi trường production

springdoc có thuộc tính `springdoc.swagger-ui.oauth.client-secret` và Swagger UI có tùy chọn `clientSecret`. Tài liệu Swagger UI cảnh báo rõ không dùng thuộc tính này trong production vì nó làm lộ thông tin bảo mật; mục đích của nó chỉ dành cho môi trường phát triển và kiểm thử.

Không cấu hình như sau trong production:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: confidential-client
      client-secret: do-not-put-a-real-secret-here
~~~

Ngay cả khi giá trị được đọc từ biến môi trường, ví dụ:

~~~yaml
client-secret: <environment variable OAUTH_CLIENT_SECRET>
~~~

thì secret vẫn được xuất ra cấu hình mà trình duyệt nhận được. Biến môi trường chỉ thay đổi cách ứng dụng lấy giá trị; nó không bảo vệ secret sau khi gửi xuống client.

Với Swagger UI public client:

- Dùng client ID công khai.
- Bật Authorization Code + PKCE.
- Không khai báo client secret.
- Giới hạn redirect URI và scope tại identity provider.
- Chỉ công bố tài liệu cho người dùng phù hợp và bảo vệ trang docs nếu cần.

Với confidential client:

- Giữ client secret trong secret manager hoặc kho bí mật server-side.
- Thực hiện đổi code lấy token tại backend/BFF.
- Không trả secret hoặc token có đặc quyền cao vào JavaScript cấu hình công khai.

## 11. OAuth redirect và CORS khi triển khai

OAuth flow chạy qua trình duyệt, vì vậy cần kiểm tra nhiều origin khác nhau:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Swagger UI | `https://docs.example.com` | Nơi người dùng thao tác |
| Authorization endpoint | `https://identity.example.com/oauth2/authorize` | Đăng nhập và cấp quyền qua chuyển hướng trình duyệt |
| Token endpoint | `https://identity.example.com/oauth2/token` | Nhận authorization code và PKCE verifier để cấp token |
| API resource server | `https://api.example.com` | Nhận request thử nghiệm từ Swagger UI |

Authorization endpoint thường được truy cập bằng chuyển hướng trình duyệt. Token endpoint được Swagger UI gọi từ JavaScript, nên nếu khác origin với Swagger UI, identity provider phải cho phép CORS từ origin tài liệu. API resource server cũng cần CORS riêng nếu nằm khác origin.

Đây là ba luồng truy cập khác nhau. Cấu hình CORS cho API không tự động cho phép trình duyệt gọi token endpoint; CORS của identity provider cũng không tự động cho phép Swagger UI gọi API.

Nếu Swagger UI nằm sau reverse proxy, hãy xác minh redirect URI là địa chỉ HTTPS công khai mà trình duyệt nhìn thấy. Không dùng địa chỉ backend nội bộ hoặc port container trong redirect URI đăng ký với identity provider.

## 12. Cấu hình Swagger UI độc lập bằng initOAuth

Nếu không dùng springdoc để phục vụ Swagger UI, có thể cấu hình OAuth sau khi khởi tạo Swagger UI:

~~~javascript
const ui = SwaggerUIBundle({
  dom_id: "#swagger-ui",
  url: "https://api.example.com/v3/api-docs",
  oauth2RedirectUrl: "https://docs.example.com/swagger-ui/oauth2-redirect.html"
});

ui.initOAuth({
  clientId: "swagger-ui-public",
  appName: "Store API Documentation",
  scopes: ["openid", "profile", "orders:read"],
  usePkceWithAuthorizationCodeGrant: true
});
~~~

`initOAuth` là instance method của Swagger UI và được gọi sau khi tạo instance bằng `SwaggerUIBundle`. Các thuộc tính tương ứng với cấu hình springdoc:

| Swagger UI `initOAuth` | springdoc property |
| --- | --- |
| `clientId` | `springdoc.swagger-ui.oauth.client-id` |
| `appName` | `springdoc.swagger-ui.oauth.app-name` |
| `scopes` | `springdoc.swagger-ui.oauth.scopes` |
| `scopeSeparator` | `springdoc.swagger-ui.oauth.scope-separator` |
| `usePkceWithAuthorizationCodeGrant` | `springdoc.swagger-ui.oauth.use-pkce-with-authorization-code-grant` |
| `useBasicAuthenticationWithAccessCodeGrant` | `springdoc.swagger-ui.oauth.use-basic-authentication-with-access-code-grant` |

Không cấu hình đồng thời hai nơi với các giá trị mâu thuẫn. Với springdoc, nên quản lý các giá trị trong application.yml/application.properties để dễ kiểm soát theo profile và môi trường. Với Swagger UI độc lập, cấu hình bằng initOAuth sau khi khởi tạo UI.

## 13. Lưu trạng thái xác thực trong trình duyệt

Swagger UI có tùy chọn `persistAuthorization`. Mặc định là false; khi bật, thông tin xác thực được giữ lại qua lần tải lại hoặc đóng/mở trình duyệt theo cơ chế lưu trữ của Swagger UI.

Trong springdoc:

~~~yaml
springdoc:
  swagger-ui:
    persist-authorization: false
~~~

Chỉ bật lưu trạng thái khi có nhu cầu rõ ràng và môi trường phù hợp. Trên máy dùng chung, máy phòng lab hoặc máy tính công cộng, việc giữ token làm tăng nguy cơ người dùng tiếp theo sử dụng lại phiên xác thực. Token lưu trong trình duyệt cũng có thể bị truy cập bởi mã JavaScript độc hại chạy cùng origin.

Sau khi thử nghiệm xong, người dùng nên bấm Logout/Authorize để xóa thông tin xác thực khỏi giao diện và đóng phiên đăng nhập theo chính sách identity provider. Việc xóa trạng thái Swagger UI không nhất thiết thu hồi access token ở authorization server; nếu cần thu hồi, dùng cơ chế revoke hoặc logout của nhà cung cấp.

## 14. Quy trình kiểm thử OAuth client trên Swagger UI

Thực hiện theo thứ tự để dễ tìm nguyên nhân khi authorization thất bại:

1. Mở OpenAPI JSON tại `/v3/api-docs` và xác nhận scheme có `type: oauth2`, đúng `authorizationUrl`, `tokenUrl`, flow và scope.
2. Kiểm tra operation có Security Requirement tham chiếu đúng tên scheme và scope.
3. Kiểm tra client registration: public client, authorization code grant, PKCE và redirect URI.
4. Mở Swagger UI và kiểm tra endpoint callback thực tế mà giao diện sử dụng.
5. Bấm Authorize, chọn đúng scope và xác nhận trình duyệt chuyển đến identity provider.
6. Đăng nhập, chấp thuận quyền và quan sát trình duyệt quay về redirect URI.
7. Xác nhận token exchange thành công; nếu lỗi, kiểm tra request token endpoint, CORS, redirect URI, code verifier và client registration.
8. Chọn operation cần thử, bấm Try it out và xác nhận request gửi access token đúng cách.
9. Gọi endpoint với token hợp lệ, token thiếu scope và không có token để kiểm tra phản hồi của resource server.
10. Sau thử nghiệm, xóa trạng thái Authorize và đóng phiên nếu cần.

Khi kiểm tra Network, không sao chép hoặc chia sẻ access token, refresh token, authorization code, cookie hay client secret vào ticket/log công khai. Có thể che giá trị nhạy cảm và chỉ giữ lại tên header, URL, status code cùng thông tin lỗi không bí mật.

## 15. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Nút Authorize không có OAuth scheme | OpenAPI thiếu Security Scheme hoặc sai type/flows | Kiểm tra components.securitySchemes trong /v3/api-docs |
| Authorization server báo invalid_client | Client ID sai, loại client không phù hợp hoặc server đòi xác thực client khác | Đối chiếu client registration; dùng public client cho Swagger UI và không nhúng secret |
| Báo redirect_uri_mismatch | Redirect URI gửi đi khác URI đã đăng ký | Kiểm tra oauth2-redirect-url, context path, HTTPS và URL công khai |
| Đăng nhập thành công nhưng token exchange lỗi CORS | Token endpoint chưa cho phép origin Swagger UI | Cấu hình CORS trên identity provider cho origin docs |
| Báo invalid_grant khi đổi code | Code hết hạn/đã dùng, redirect URI hoặc PKCE verifier không khớp | Thử flow mới, kiểm tra redirect URI và bật PKCE nhất quán |
| Scope không xuất hiện trong hộp thoại | Scope chưa khai báo trong OpenAPI hoặc cấu hình scopes | Đồng bộ scope giữa flow, UI, client registration và authorization server |
| Token nhận được nhưng API trả 403 | Token thiếu scope/role hoặc API kiểm tra quyền khác | Kiểm tra claim và authorization policy của resource server |
| Swagger UI gửi request nhưng thiếu Bearer token | Operation không tham chiếu đúng Security Requirement hoặc scheme name không khớp | Kiểm tra security của operation và tên component |
| Callback trả 404 | Redirect URI sai path hoặc proxy không phục vụ file callback | Kiểm tra /swagger-ui/oauth2-redirect.html trên URL công khai |
| PKCE không được gửi | Chưa bật tùy chọn hoặc flow không phải Authorization Code | Bật use-pkce-with-authorization-code-grant và kiểm tra flow |
| Secret xuất hiện trong trình duyệt | Cấu hình client-secret trong Swagger UI | Xóa secret khỏi cấu hình client; dùng public client + PKCE hoặc BFF |
| Người dùng khác vẫn dùng được token cũ | Đã bật persistAuthorization hoặc phiên IdP còn hiệu lực | Tắt persistence trên máy dùng chung, xóa authorization và logout/revoke theo chính sách |

## 16. Checklist triển khai

- [ ] OpenAPI khai báo đúng Authorization Code Flow, authorization URL, token URL và scopes.
- [ ] Operation tham chiếu đúng Security Scheme và yêu cầu scope phù hợp.
- [ ] Swagger UI được đăng ký là public client nếu chạy trực tiếp trong trình duyệt.
- [ ] Client registration bật Authorization Code và PKCE với phương thức S256.
- [ ] Client ID khớp với registration.
- [ ] Redirect URI công khai khớp chính xác URI đã đăng ký.
- [ ] Cấu hình use-pkce-with-authorization-code-grant: true.
- [ ] Không cấu hình client secret trong Swagger UI production.
- [ ] CORS cho token endpoint và API đã được cấu hình theo origin cần thiết.
- [ ] Scope được giới hạn theo quyền tối thiểu.
- [ ] persist-authorization được cân nhắc theo môi trường và thiết bị.
- [ ] Đã kiểm thử authorization, token exchange, Try it out và quyền truy cập API.
- [ ] Log và ảnh chụp kiểm thử không chứa token hoặc thông tin xác thực.

## 17. Tài liệu tham khảo chính thức

- [Swagger UI — OAuth 2.0 Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/oauth2/) — initOAuth, client ID, client secret, scopes, PKCE và HTTP Basic tại token endpoint.
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/) — oauth2RedirectUrl, cấu hình Swagger UI và các instance method.
- [springdoc-openapi Configuration Properties](https://springdoc.org/properties.html) — các thuộc tính springdoc.swagger-ui.oauth.*, oauth2RedirectUrl, persistAuthorization và cấu hình Swagger UI trong Spring Boot.
- [springdoc-openapi Features v2](https://springdoc.org/v2/features.html) — cách khai báo các thuộc tính Swagger UI bằng Spring Boot properties.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html) — cơ chế PKCE, code verifier, code challenge và phương thức S256.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html) — khuyến nghị bảo mật OAuth 2.0 hiện hành.

Để cấu hình OAuth client trên Swagger UI, hãy đồng bộ ba phần: flow và scope trong OpenAPI, client registration và redirect URI tại identity provider, cùng client ID và PKCE trong cấu hình giao diện. Với Swagger UI chạy trong trình duyệt, public client + Authorization Code + PKCE giúp thử API mà không phải đưa client secret production xuống frontend.
