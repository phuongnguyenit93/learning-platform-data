# Luồng cũ hoặc không còn được khuyến nghị cần được nhận diện riêng

## 1. Vì sao phải nhận diện riêng các luồng OAuth2/OIDC cũ?

OAuth 2.0 và OpenID Connect (OIDC) cung cấp nhiều luồng cấp quyền và xác thực. Một số luồng được thiết kế cho bối cảnh ứng dụng cũ, khi trình duyệt, ứng dụng di động và cách lưu token còn khác hiện nay. Các khuyến nghị bảo mật đã thay đổi; việc tiếp tục dùng một luồng cũ có thể làm lộ thông tin xác thực, đưa token vào front channel hoặc khiến ứng dụng khó hỗ trợ MFA và đăng nhập liên kết.

Trong module Springdoc OpenAPI, tài liệu cần mô tả chính xác cách client lấy token và gọi API. Khi ứng dụng vẫn hỗ trợ một luồng cũ vì lý do tương thích, tài liệu nên nhận diện rõ luồng đó là legacy, nêu giới hạn và chỉ ra phương án thay thế. Không nên đặt luồng cũ cạnh luồng mới như thể chúng có mức khuyến nghị ngang nhau.

Cần phân biệt ba trạng thái:

- **Không còn được khuyến nghị cho ứng dụng mới**: không nên chọn khi thiết kế tích hợp mới; cần có kế hoạch chuyển đổi nếu đang sử dụng.
- **Cũ nhưng vẫn tồn tại vì tương thích**: có thể cần mô tả để client hiện hữu tiếp tục hoạt động; phải gắn nhãn và giới hạn phạm vi.
- **Vẫn phù hợp cho một trường hợp cụ thể**: không nên gọi là lỗi thời chỉ vì nó khác luồng đăng nhập người dùng phổ biến.

Bài này phân loại các luồng OAuth2/OIDC thường gặp, giải thích rủi ro và cách nhận diện chúng trong tài liệu Springdoc OpenAPI.

## 2. Phân loại nhanh các luồng

| Luồng | Trạng thái và phạm vi hiện nay | Hướng xử lý |
|---|---|---|
| OAuth2 Implicit Grant | Không còn được khuyến nghị; OAuth 2.0 Security BCP yêu cầu không dùng cho ứng dụng mới | Chuyển sang Authorization Code với PKCE |
| Resource Owner Password Credentials (ROPC/Password Grant) | Không còn được khuyến nghị; không dùng trong thiết kế mới | Chuyển sang Authorization Code với PKCE hoặc luồng phù hợp theo loại client |
| Authorization Code không có PKCE | Cách triển khai cũ, đặc biệt rủi ro với public client | Bổ sung PKCE, ưu tiên phương thức S256 |
| OIDC Implicit Flow | Luồng cũ; token được trả qua front channel | Dùng OIDC Authorization Code Flow với PKCE |
| OIDC Hybrid Flow | Vẫn được định nghĩa trong OIDC Core nhưng ít phù hợp với đa số ứng dụng hiện đại | Ưu tiên Authorization Code Flow với PKCE nếu không có yêu cầu đặc biệt |
| Client Credentials | Vẫn phù hợp cho giao tiếp máy-máy, không đại diện cho đăng nhập người dùng | Tiếp tục dùng khi client service cần truy cập resource server |
| Device Authorization Grant | Vẫn phù hợp cho thiết bị khó nhập liệu hoặc không có browser đầy đủ | Dùng khi đúng bối cảnh thiết bị |

Implicit và ROPC là hai luồng cần nhận diện rõ nhất là không còn được khuyến nghị. OIDC Hybrid cần được mô tả thận trọng: OIDC Core vẫn định nghĩa luồng này, vì vậy không nên tuyên bố nó đã bị loại khỏi chuẩn; tuy nhiên, với đa số ứng dụng mới, Authorization Code Flow kết hợp PKCE thường là lựa chọn đơn giản và an toàn hơn.

## 3. OAuth2 Implicit Grant: luồng cũ cần thay thế

Implicit Grant được thiết kế cho các ứng dụng chạy trong trình duyệt, nơi client không thể giữ client secret an toàn và trước đây không có mô hình trao đổi authorization code phù hợp. Authorization server trả access token trực tiếp về redirect URI của client thay vì trả authorization code để client đổi token tại token endpoint.

Một request minh họa có dạng:

~~~http
GET /authorize?
  response_type=token&
  client_id=browser-client&
  redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
  scope=products.read&
  state=random-state
~~~

Trong response redirect, access token có thể được trả về trong fragment của URL. Trình duyệt không gửi fragment trong HTTP request tới server đích, nhưng JavaScript của trang nhận redirect có thể đọc được token. Điều này làm token nằm trong front channel và tăng bề mặt rủi ro từ script độc hại, XSS, extension trình duyệt hoặc các lỗi xử lý URL.

Các vấn đề chính:

- Access token được phát hành trực tiếp qua authorization endpoint.
- Client không có bước đổi authorization code tại token endpoint.
- Khó áp dụng các biện pháp bảo vệ dựa trên code exchange.
- Token được trao cho môi trường trình duyệt, nơi có thể bị mã độc JavaScript đọc.
- Luồng này không còn là lựa chọn phù hợp cho SPA hiện đại.

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), implicit grant không nên được sử dụng. Với ứng dụng mới, hãy dùng Authorization Code Grant cùng PKCE.

## 4. Resource Owner Password Credentials Grant (ROPC)

ROPC, còn gọi là Password Grant, cho phép client nhận trực tiếp username và password của người dùng rồi gửi chúng tới token endpoint để đổi lấy token.

Ví dụ request cũ:

~~~http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=password&
username=alice&
password=user-password&
client_id=legacy-client&
scope=products.read
~~~

Luồng này khiến ứng dụng client trực tiếp tiếp xúc với mật khẩu người dùng. Nó làm suy yếu ranh giới bảo mật của authorization server và gây khó khăn cho các cơ chế đăng nhập hiện đại.

Các hạn chế:

- Client phải thu thập và xử lý mật khẩu của người dùng.
- Khó tích hợp MFA, passkey, đăng nhập liên kết và chính sách xác thực tương tác.
- Người dùng phải tin tưởng ứng dụng client với credential của mình.
- Ứng dụng có thể vô tình lưu hoặc ghi log mật khẩu.
- Việc đổi nhà cung cấp định danh hoặc áp dụng chính sách đăng nhập mới trở nên khó hơn.
- Không phù hợp với mô hình ủy quyền nơi authorization server kiểm soát tương tác đăng nhập.

OAuth 2.0 Security BCP (RFC 9700) nêu rõ Resource Owner Password Credentials Grant không được sử dụng. Không nên triển khai ROPC cho client mới và không nên tiếp tục quảng bá nó như một phương án đăng nhập thông thường.

Nếu hệ thống cũ vẫn cần hỗ trợ, hãy giới hạn theo client hiện hữu, đánh dấu legacy trong tài liệu, lập kế hoạch ngừng hỗ trợ và chuyển người dùng sang Authorization Code Flow với PKCE. Không thay thế ROPC bằng cách gửi username/password qua một endpoint tự tạo khác; việc đó chỉ chuyển rủi ro sang vị trí khác.

## 5. Authorization Code không có PKCE: triển khai cũ cần nâng cấp

Authorization Code Flow vẫn là luồng phù hợp cho nhiều loại ứng dụng. Tuy nhiên, một triển khai cũ có thể dùng authorization code mà không có Proof Key for Code Exchange (PKCE).

PKCE bổ sung một cặp giá trị:

- **code_verifier**: chuỗi ngẫu nhiên bí mật tạm thời do client tạo và giữ trong phiên giao dịch.
- **code_challenge**: giá trị dẫn xuất từ verifier, được gửi ở authorization request.
- **code_challenge_method**: phương thức dẫn xuất, nên dùng S256.

Client gửi challenge khi yêu cầu authorization. Khi đổi code tại token endpoint, client gửi verifier. Authorization server xác minh verifier khớp challenge đã nhận trước đó. Nếu authorization code bị chặn hoặc đánh cắp, bên khác không có verifier sẽ khó đổi code thành token.

Ví dụ authorization request:

~~~http
GET /authorize?
  response_type=code&
  client_id=web-client&
  redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
  scope=openid%20profile%20products.read&
  state=random-state&
  code_challenge=BASE64URL_SHA256_CHALLENGE&
  code_challenge_method=S256
~~~

Khi đổi code:

~~~http
POST /token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
client_id=web-client&
code_verifier=ORIGINAL_RANDOM_VERIFIER
~~~

Public client phải dùng PKCE. Với confidential client, PKCE cũng được khuyến nghị để tăng bảo vệ authorization code. Không nên xem client secret là lý do để bỏ PKCE.

## 6. OIDC Implicit Flow và Hybrid Flow

OIDC mở rộng OAuth2 để cung cấp thông tin xác thực danh tính. Ngoài access token, OIDC có thể trả ID Token để client xác minh người dùng đã đăng nhập. OIDC Core định nghĩa Authorization Code Flow, Implicit Flow và Hybrid Flow.

**OIDC Implicit Flow** trả ID Token và/hoặc access token qua front channel. Đây là mô hình cũ, có những rủi ro tương tự OAuth2 Implicit Grant. Với ứng dụng mới, ưu tiên OIDC Authorization Code Flow với PKCE.

**OIDC Hybrid Flow** kết hợp response từ authorization endpoint với việc đổi code tại token endpoint. Tùy response type, client có thể nhận code cùng một hoặc nhiều token ở front channel. Luồng này vẫn được OIDC Core định nghĩa, nhưng làm tăng độ phức tạp và không phải lựa chọn mặc định cho hầu hết ứng dụng hiện đại.

Không nên gộp hai khái niệm thành một nhãn “đã bị loại bỏ”:

- OIDC Implicit Flow là lựa chọn cũ cần thay thế trong ứng dụng mới.
- OIDC Hybrid Flow vẫn có trong chuẩn OIDC, nhưng chỉ nên duy trì khi có yêu cầu kiến trúc cụ thể và đã đánh giá rủi ro.

Nếu không cần nhận token từ front channel, Authorization Code Flow với PKCE thường đơn giản hơn và giúp token được trả qua token endpoint.

## 7. OAuth2 và OIDC không phải cùng một khái niệm

OAuth2 là framework ủy quyền. Nó cho phép client nhận access token để truy cập resource server trong phạm vi được cấp.

OpenID Connect là lớp định danh xây dựng trên OAuth2. OIDC bổ sung các thành phần như:

- **ID Token**: JWT chứa các claim xác thực về người dùng và phiên đăng nhập.
- **UserInfo Endpoint**: endpoint cung cấp claim người dùng theo quyền được cấp.
- **openid scope**: scope bắt buộc để một authorization request trở thành OIDC authentication request.
- **Discovery**: metadata về authorization endpoint, token endpoint, JWKS URI và các capability khác.
- **JWKS**: khóa công khai dùng để xác minh chữ ký token.

Cần phân biệt:

| Token | Mục đích | Nơi sử dụng |
|---|---|---|
| Access Token | Cho phép truy cập API/resource server | Gửi tới API theo cơ chế bearer hoặc token binding phù hợp |
| ID Token | Cho client biết kết quả xác thực và danh tính người dùng | Client OIDC xác minh issuer, audience, signature, nonce và thời hạn |
| Refresh Token | Xin access token mới khi được authorization server cho phép | Client gửi tới token endpoint; không gửi tới resource API |

Resource server không nên nhận ID Token thay cho Access Token. ID Token được phát hành cho OIDC client; access token được dùng để truy cập API. Việc kiểm tra audience và mục đích sử dụng token phải phù hợp với loại token.

## 8. Luồng nên ưu tiên: Authorization Code với PKCE

Với SPA, ứng dụng native và nhiều ứng dụng web, lựa chọn thường phù hợp là Authorization Code Flow với PKCE.

Các bước chính:

1. Client tạo state, nonce nếu dùng OIDC, và code_verifier ngẫu nhiên.
2. Client tạo code_challenge bằng S256.
3. Client chuyển trình duyệt tới authorization endpoint.
4. Người dùng đăng nhập và cấp quyền tại authorization server.
5. Authorization server redirect về client cùng authorization code và state.
6. Client xác minh state.
7. Client gửi code cùng code_verifier tới token endpoint.
8. Authorization server xác minh PKCE và trả token.
9. Với OIDC, client xác minh ID Token, gồm issuer, audience, chữ ký, thời hạn và nonce.
10. Client dùng access token để gọi resource API.

PKCE không thay thế state. State bảo vệ luồng redirect khỏi CSRF và liên kết response với giao dịch do client khởi tạo. Với OIDC, nonce liên kết ID Token với authentication request và giúp chống replay trong ngữ cảnh tương ứng.

Dùng S256 thay vì phương thức plain. Verifier phải được tạo ngẫu nhiên đủ mạnh, chỉ dùng cho giao dịch tương ứng và không ghi vào log.

## 9. Các luồng vẫn phù hợp trong đúng bối cảnh

Không phải mọi flow khác Authorization Code đều lỗi thời.

**Client Credentials Grant** phù hợp cho giao tiếp máy-máy khi service client truy cập API bằng danh tính của chính client, không có người dùng đang đăng nhập. Client xác thực với authorization server bằng phương thức phù hợp như client secret được bảo vệ, private_key_jwt hoặc mTLS tùy nền tảng.

Client Credentials không đại diện cho đăng nhập người dùng và không phải OIDC login flow. Không dùng nó để giả lập danh tính người dùng nếu hệ thống cần quyền theo người dùng.

**Device Authorization Grant** phù hợp với thiết bị khó nhập liệu hoặc không có trình duyệt đầy đủ, ví dụ TV hoặc thiết bị chuyên dụng. Thiết bị hiển thị mã, người dùng dùng một thiết bị khác để xác thực và cấp quyền. Đây là luồng riêng được chuẩn hóa, không phải một biến thể của ROPC.

**Refresh Token** là grant type tại token endpoint để xin token mới khi refresh token còn hợp lệ. Nó không phải luồng đăng nhập ban đầu. Client cần tuân thủ chính sách rotation hoặc sender-constrained refresh token của authorization server và xử lý reuse detection.

## 10. Chọn luồng thay thế theo loại client

| Loại client hoặc nhu cầu | Lựa chọn phù hợp |
|---|---|
| SPA chạy trong browser | Authorization Code + PKCE |
| Ứng dụng mobile/native | Authorization Code + PKCE qua external user-agent/browser |
| Ứng dụng web có backend | Authorization Code; dùng PKCE để tăng bảo vệ |
| Service gọi service, không có người dùng | Client Credentials |
| Thiết bị có bàn phím hoặc browser hạn chế | Device Authorization Grant |
| Ứng dụng cần đăng nhập và nhận danh tính OIDC | OIDC Authorization Code + PKCE |
| Ứng dụng đang dùng Implicit | Lập kế hoạch chuyển sang Authorization Code + PKCE |
| Ứng dụng đang dùng ROPC | Chuyển sang authorization flow có tương tác tại authorization server |

Với native app, không nên nhúng client secret cố định vào ứng dụng cài trên thiết bị vì người dùng có thể trích xuất nó. Hãy coi native app là public client và dùng PKCE.

Với SPA, mọi giá trị trong JavaScript bundle hoặc browser storage có thể bị người dùng hoặc script trên cùng origin quan sát. Không đưa client secret dài hạn vào frontend.

## 11. Mô tả Authorization Code Flow trong Springdoc

Springdoc đọc các annotation của Swagger Core để mô tả OAuth2 security scheme. Ví dụ:

~~~java
@Configuration
@SecurityScheme(
    name = "oauth2AuthCode",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://id.example.com/oauth2/authorize",
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "openid",
                    description = "Xác thực người dùng bằng OpenID Connect"
                ),
                @OAuthScope(
                    name = "profile",
                    description = "Đọc thông tin hồ sơ cơ bản"
                ),
                @OAuthScope(
                    name = "products.read",
                    description = "Đọc danh sách và chi tiết sản phẩm"
                )
            }
        )
    )
)
public class OpenApiSecurityConfiguration {
}
~~~

Security Scheme trên mô tả authorization endpoint, token endpoint và scopes. Để operation yêu cầu scheme:

~~~java
@GetMapping("/api/products")
@Operation(
    summary = "Danh sách sản phẩm",
    security = @SecurityRequirement(name = "oauth2AuthCode")
)
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

Tên scheme trong Security Requirement phải khớp với tên đã khai báo trong @SecurityScheme. Scope được khai báo trong OAuth Flow giúp tài liệu và Swagger UI biết các quyền mà client có thể yêu cầu.

OpenAPI mô tả flow và scope nhưng không triển khai authorization server. Các URL phải trỏ tới identity provider thực tế và được cấu hình đúng cho môi trường.

## 12. Mô tả OpenID Connect Discovery trong Springdoc

Nếu identity provider cung cấp OpenID Provider Configuration, có thể mô tả bằng Security Scheme kiểu openIdConnect:

~~~java
@Configuration
@SecurityScheme(
    name = "openId",
    type = SecuritySchemeType.OPENIDCONNECT,
    openIdConnectUrl =
        "https://id.example.com/.well-known/openid-configuration"
)
public class OpenIdConnectConfiguration {
}
~~~

OpenID Connect Discovery document cung cấp metadata như issuer, authorization_endpoint, token_endpoint, jwks_uri, userinfo_endpoint và các thuật toán được hỗ trợ.

Security Scheme kiểu openIdConnect tham chiếu discovery URL. Nó không tự xác minh ID Token và cũng không tự cấu hình Spring Security resource server. Ứng dụng vẫn phải cấu hình issuer, audience và cơ chế kiểm tra JWT phù hợp.

Với OIDC, client phải xác minh ID Token theo OIDC Core. Resource server phải xác minh access token theo định dạng và chính sách mà authorization server công bố.

## 13. Cấu hình Swagger UI dùng PKCE

Khi dùng Authorization Code Flow cho Swagger UI, có thể bật PKCE bằng cấu hình Swagger UI tương ứng. Ví dụ application.yml trong các phiên bản Springdoc hỗ trợ thuộc tính này:

~~~yaml
springdoc:
  swagger-ui:
    oauth:
      client-id: swagger-ui-public-client
      use-pkce-with-authorization-code-grant: true
~~~

Thuộc tính này yêu cầu Swagger UI dùng PKCE khi thực hiện Authorization Code Grant. Authorization server cũng phải hỗ trợ PKCE và cấu hình client/redirect URI phù hợp.

Không đặt client secret dài hạn vào Swagger UI khi trang được phục vụ cho browser hoặc người dùng bên ngoài. Mã JavaScript và cấu hình trình duyệt có thể được quan sát. Với public client, dùng client ID và PKCE; nếu cần client authentication bí mật, hãy thực hiện ở backend confidential client.

Tên property và cách ánh xạ cấu hình có thể khác theo phiên bản Springdoc/Swagger UI. Kiểm tra cấu hình được hỗ trợ của dependency dự án và kiểm tra authorization request thực tế có chứa code_challenge cùng code_challenge_method=S256 hay không.

## 14. Cách nhận diện riêng flow cũ trong tài liệu

OpenAPI OAuthFlows vẫn có các thuộc tính cho implicit, password, clientCredentials và authorizationCode để mô tả tài liệu hiện hữu. Việc chuẩn OpenAPI còn biểu diễn được một flow không có nghĩa flow đó vẫn được khuyến nghị sử dụng.

Nếu phải tài liệu hóa một hệ thống cũ, nên:

- Dùng tên scheme thể hiện rõ legacy, ví dụ legacyPassword.
- Ghi từ LEGACY hoặc KHÔNG KHUYẾN NGHỊ trong description.
- Nêu rõ client nào còn được phép dùng và điều kiện chuyển đổi.
- Không đặt flow cũ làm ví dụ mặc định cho client mới.
- Công bố Authorization Code + PKCE như hướng tích hợp thay thế.
- Có kế hoạch thời hạn hỗ trợ hoặc ngày ngừng hoạt động nếu đã được quyết định.

Ví dụ mô tả Password Grant chỉ để duy trì tài liệu tương thích:

~~~java
@SecurityScheme(
    name = "legacyPassword",
    type = SecuritySchemeType.OAUTH2,
    description =
        "LEGACY: Chỉ dành cho client cũ đang được chuyển đổi. " +
        "Không dùng cho tích hợp mới; hãy chuyển sang Authorization Code + PKCE.",
    flows = @OAuthFlows(
        password = @OAuthFlow(
            tokenUrl = "https://id.example.com/oauth2/token",
            scopes = {
                @OAuthScope(
                    name = "products.read",
                    description = "Đọc sản phẩm"
                )
            }
        )
    )
)
~~~

Đây là mô tả tài liệu cho hệ thống hiện hữu, không phải hướng dẫn triển khai ROPC mới. Không tạo client mới chỉ để làm ví dụ chạy thử flow này.

Trong OpenAPI 3.0 và 3.1, Security Scheme Object không có thuộc tính chuẩn chung để đánh dấu riêng một OAuth flow là deprecated. Có thể dùng description và vendor extension như x-deprecated để truyền trạng thái cho công cụ nội bộ, nhưng extension không được mọi Swagger UI hoặc client generator hiểu. Không nhầm thuộc tính deprecated của Operation Object với trạng thái của một flow.

## 15. Đánh dấu flow legacy bằng vendor extension

Nếu muốn hệ thống kiểm tra tài liệu nhận diện scheme cũ, có thể thêm vendor extension bằng OpenApiCustomizer:

~~~java
@Bean
public OpenApiCustomizer markLegacyOAuthScheme() {
    return openApi -> {
        if (openApi.getComponents() == null ||
            openApi.getComponents().getSecuritySchemes() == null) {
            return;
        }

        var legacy = openApi.getComponents()
            .getSecuritySchemes()
            .get("legacyPassword");

        if (legacy != null) {
            legacy.addExtension("x-deprecated", true);
            legacy.addExtension(
                "x-migration-target",
                "oauth2AuthCode"
            );
            legacy.setDescription(
                "LEGACY: Chỉ duy trì cho client hiện hữu. " +
                "Chuyển sang Authorization Code + PKCE."
            );
        }
    };
}
~~~

Các extension x-deprecated và x-migration-target là metadata riêng của tổ chức, không phải trường chuẩn bắt buộc trong OpenAPI. Có thể dùng chúng trong lint rule, báo cáo hoặc developer portal để lọc flow cũ.

Nếu muốn đánh dấu cả operation đã ngừng khuyến nghị, có thể dùng @Operation(deprecated = true) cho endpoint tương ứng. Thuộc tính này đánh dấu operation, không tự đánh dấu riêng một grant type trong Security Scheme. Chỉ đánh dấu operation deprecated khi chính endpoint hoặc hợp đồng operation đó đang được thay thế.

## 16. Không dùng nhãn legacy cho các flow vẫn còn phù hợp

Một số cấu hình có thể trông khác Authorization Code nhưng vẫn có mục đích hợp lệ:

- Client Credentials dành cho workload/service identity.
- Device Authorization dành cho thiết bị có khả năng nhập liệu hạn chế.
- Refresh Token dùng để duy trì phiên theo chính sách authorization server.
- Authorization Code + PKCE là lựa chọn phổ biến cho client có người dùng.
- OIDC Authorization Code + PKCE là lựa chọn phù hợp khi client cần xác thực danh tính.

Không nên gắn nhãn deprecated cho Client Credentials chỉ vì nó không có trang đăng nhập người dùng. Nó giải quyết bài toán khác: service xác thực chính nó để truy cập resource.

Tương tự, Device Authorization không phải phiên bản lỗi thời của Password Grant. Nó cho phép người dùng hoàn tất đăng nhập trên một thiết bị khác mà không cần client thu thập mật khẩu.

Việc phân loại đúng giúp client chọn flow theo bản chất ứng dụng thay vì chọn theo tên hoặc thói quen cũ.

## 17. Kiểm tra flow được mô tả trong OpenAPI

Sau khi cấu hình Springdoc, tải OpenAPI JSON:

~~~http
GET /v3/api-docs
~~~

Kiểm tra các mục sau:

1. Security Scheme có đúng type oauth2 hoặc openIdConnect.
2. Authorization URL và token URL trỏ đúng identity provider.
3. Scopes có tên và mô tả đúng.
4. Operation yêu cầu đúng Security Requirement.
5. Public operation không bị kế thừa security ngoài ý muốn.
6. Authorization Code Flow được mô tả rõ khi dùng PKCE.
7. Swagger UI gửi code_challenge và code_challenge_method phù hợp.
8. OIDC discovery URL trỏ tới metadata đúng issuer.
9. Không đưa client secret hoặc token thật vào document.
10. Flow legacy có description và extension nhận diện riêng nếu tổ chức sử dụng quy ước đó.
11. Flow legacy không bị trình bày như lựa chọn mặc định cho tích hợp mới.
12. Access Token và ID Token được mô tả đúng mục đích.

OpenAPI document chỉ xác minh nội dung hợp đồng. Để kiểm tra flow thật, cần thử với identity provider trong môi trường phù hợp và xác minh redirect URI, PKCE, state, nonce, issuer, audience, chữ ký và thời hạn token.

## 18. Lộ trình chuyển đổi từ flow cũ

Một kế hoạch migration có thể thực hiện theo các bước:

1. Liệt kê client đang dùng Implicit, ROPC hoặc Authorization Code không có PKCE.
2. Xác định client là SPA, native, web backend hay service-to-service.
3. Chọn flow thay thế phù hợp với loại client.
4. Đăng ký client mới hoặc cập nhật cấu hình tại identity provider.
5. Cấu hình redirect URI, scope và PKCE S256.
6. Cập nhật Springdoc Security Scheme và Swagger UI.
7. Kiểm thử đăng nhập, consent, refresh, logout và thu hồi token.
8. Chạy song song trong giai đoạn chuyển tiếp nếu chính sách cho phép.
9. Theo dõi client còn sử dụng flow cũ.
10. Thông báo thời hạn ngừng hỗ trợ và loại bỏ flow cũ khi không còn client phụ thuộc.

Không nên tắt flow cũ ngay khi tài liệu được cập nhật nếu vẫn có client production phụ thuộc và chưa có kế hoạch chuyển đổi. Ngược lại, không nên để flow cũ tồn tại vô thời hạn mà không có owner, thời hạn và cơ chế theo dõi.

## 19. Các lỗi thường gặp khi phân loại OAuth2/OIDC

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Swagger UI gợi ý Implicit cho SPA mới | Tài liệu vẫn giữ flow cũ làm lựa chọn mặc định |
| Client gửi username/password tới token endpoint | Đang dùng ROPC thay cho authorization flow tương tác |
| Authorization Code bị đánh cắp có thể đổi thành token | Chưa bật PKCE hoặc kiểm tra verifier không đúng |
| Dùng client secret trong JavaScript | Nhầm public client thành confidential client |
| API nhận ID Token làm access token | Nhầm mục đích token OIDC |
| Gắn nhãn Hybrid là đã bị xóa khỏi chuẩn | Nhầm “ít phù hợp” với “đã bị loại bỏ” |
| Client Credentials được dùng để đăng nhập người dùng | Chọn sai flow và sai loại principal |
| Device flow bị xem là legacy | Nhầm flow cho thiết bị hạn chế với ROPC |
| OpenAPI có scheme nhưng backend không bảo vệ | Mới mô tả security, chưa cấu hình resource server |
| Swagger UI không gửi PKCE | Chưa bật tùy chọn PKCE hoặc IdP không hỗ trợ |
| Flow cũ không có ghi chú | Scheme thiếu description hoặc extension nhận diện |
| Tài liệu ghi endpoint token không đúng | URL authorization/token lấy từ cấu hình IdP sai môi trường |

## 20. Nguyên tắc tài liệu hóa OAuth2/OIDC

Khi viết tài liệu Springdoc cho OAuth2 và OIDC:

1. Nhận diện riêng Implicit Grant và ROPC là các luồng không còn được khuyến nghị.
2. Xem Authorization Code không PKCE là triển khai cũ cần nâng cấp, đặc biệt với public client.
3. Không tuyên bố OIDC Hybrid đã bị loại khỏi chuẩn; mô tả đúng trạng thái và lý do ít được chọn.
4. Ưu tiên Authorization Code + PKCE cho ứng dụng có người dùng.
5. Dùng Client Credentials cho giao tiếp máy-máy, không dùng để đăng nhập người dùng.
6. Dùng Device Authorization cho thiết bị có giới hạn tương tác.
7. Phân biệt access token, ID token và refresh token.
8. Dùng description và vendor extension để đánh dấu flow legacy còn phải tài liệu hóa.
9. Không đưa client secret hoặc token thật vào Swagger UI công khai.
10. Kiểm tra OpenAPI document cùng quy trình authorization thực tế.

OpenAPI có thể mô tả cả các OAuth flow cũ để duy trì khả năng tương thích, nhưng tài liệu phải giúp người đọc nhận ra trạng thái và rủi ro của chúng. Khi tách riêng flow legacy, đưa Authorization Code với PKCE lên làm hướng tích hợp hiện đại và phân biệt đúng OAuth2 với OIDC, tài liệu Springdoc sẽ giúp client chọn cơ chế xác thực phù hợp thay vì tiếp tục sao chép một cấu hình đã lỗi thời.

