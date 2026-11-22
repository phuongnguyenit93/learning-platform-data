# 3.5. Discovery Document và quan hệ với issuer

## 1. Vì sao OIDC cần Discovery Document?

Trong OpenID Connect (OIDC), ứng dụng đăng nhập được gọi là **Relying Party (RP)** hay **OIDC Client**; hệ thống xác thực người dùng được gọi là **OpenID Provider (OP)**. Để đăng nhập, Client phải biết authorization endpoint, token endpoint, nơi lấy khóa công khai để xác minh ID Token, những thuật toán được hỗ trợ và các khả năng của nhà cung cấp.

Nếu mỗi ứng dụng phải khai báo thủ công tất cả URL và khả năng của OP, việc tích hợp rất dễ nhầm môi trường, realm/tenant, phiên bản endpoint hoặc khóa ký. **OpenID Connect Discovery 1.0** cung cấp một cơ chế tiêu chuẩn: OP xuất bản tài liệu JSON mô tả chính mình. Tài liệu đó thường được gọi là **Discovery Document**, **OpenID Provider Configuration** hoặc **OIDC metadata**.

Client thường bắt đầu từ một **issuer URI đáng tin cậy**, truy vấn tài liệu discovery của issuer đó, xác nhận JSON thực sự mô tả đúng issuer rồi lấy các endpoint và thông tin xác minh token. Mối liên hệ này rất quan trọng trong Spring Security OAuth 2.0/OIDC Client: chỉ cần cấu hình issuer phù hợp, Spring Security có thể tự khám phá thông tin cần thiết để thực hiện OIDC Login.

Ví dụ issuer:

~~~text
https://login.example.org/realms/training
~~~

OIDC Discovery Document tương ứng thường nằm tại:

~~~text
https://login.example.org/realms/training/.well-known/openid-configuration
~~~

Đây là URL minh họa; các địa chỉ thuộc <code>example.org</code> không phải provider thật.

> **Nguyên tắc:** Issuer xác định **OP nào được tin cậy**; Discovery Document mô tả **cách giao tiếp với OP đó**. Discovery URL không phải giá trị issuer và không được đưa nguyên cả đuôi well-known vào cấu hình issuer.

## 2. Issuer là gì?

### 2.1. Định danh của OpenID Provider

Issuer là một URL định danh OP, dùng lược đồ <code>https</code>, có thể gồm path và không có query hay fragment theo OIDC Discovery. Một số dạng ví dụ:

~~~text
https://identity.example.com
https://identity.example.com/realms/team-a
https://login.example.org/tenant/contoso
~~~

Issuer có thể định danh một realm hoặc tenant, không nhất thiết chỉ một máy chủ vật lý. Hai realm cùng chạy trên một host có thể có hai issuer khác nhau. Client cần biết chính xác issuer nào đã được quản trị viên ứng dụng cho phép.

Issuer được đưa vào claim <code>iss</code> của **ID Token** do OP phát hành. Một payload ID Token minh họa:

~~~json
{
  "iss": "https://login.example.org/realms/training",
  "sub": "248289761001",
  "aud": "training-web-client",
  "exp": 1999999999,
  "iat": 1999999000
}
~~~

JSON trên chỉ cho thấy một số claim, không phải JWT hoàn chỉnh. Trong thực tế, ID Token cần được kiểm tra chữ ký và các claim OIDC liên quan. Giá trị <code>iss</code> phải khớp issuer mà Client đang tin cậy.

### 2.2. Phân biệt issuer với các URL và định danh khác

| Giá trị | Ví dụ | Mục đích |
|---|---|---|
| **Issuer URI** | <code>https://login.example.org/realms/training</code> | Định danh OP được tin cậy |
| Discovery URL | <code>https://login.example.org/realms/training/.well-known/openid-configuration</code> | Lấy metadata của OP |
| Authorization endpoint | <code>https://login.example.org/realms/training/protocol/openid-connect/auth</code> | Nơi trình duyệt bắt đầu quy trình xác thực |
| Token endpoint | <code>https://login.example.org/realms/training/protocol/openid-connect/token</code> | Nơi Client đổi authorization code lấy token |
| JWKS URI | <code>https://login.example.org/realms/training/protocol/openid-connect/certs</code> | Địa chỉ lấy khóa công khai dùng xác minh chữ ký |
| Client ID | <code>training-web-client</code> | Định danh của ứng dụng đã đăng ký với OP |
| Registration ID | <code>training</code> | Tên nội bộ trong Spring Security để chọn ClientRegistration |
| Redirect URI | <code>https://app.example.org/login/oauth2/code/training</code> | Địa chỉ callback thuộc ứng dụng Client |

Đừng lấy URL trang đăng nhập, authorization endpoint, JWKS URL hay URL discovery rồi xem nó là issuer. Các endpoint cũng không bắt buộc cùng host/path với issuer: Client phải đọc endpoint từ metadata được xác minh, không tự ghép đường dẫn theo suy đoán.

### 2.3. Yêu cầu so khớp issuer

Giả sử Client đã cấu hình:

~~~text
https://login.example.org/realms/training
~~~

Nhưng tài liệu discovery trả:

~~~json
{
  "issuer": "https://login.example.org/realms/other",
  "authorization_endpoint": "https://login.example.org/realms/other/protocol/openid-connect/auth"
}
~~~

Metadata này **không mô tả issuer được cấu hình** và phải bị từ chối. Tương tự, ID Token có <code>iss</code> của realm <code>other</code> không được chấp nhận trong luồng của realm <code>training</code>.

OIDC yêu cầu issuer metadata khớp chính xác issuer dùng để thực hiện discovery. Khác biệt ở hostname, scheme, path, chữ hoa/thường trong path hoặc dấu <code>/</code> cuối có thể gây mismatch. Không chủ động nới lỏng hoặc bỏ qua kiểm tra issuer chỉ để đăng nhập thành công. Khi có mismatch, phải kiểm tra cấu hình và public issuer do OP công bố.

Danh tính người dùng OIDC được nhận biết ổn định theo **cặp (<code>iss</code>, <code>sub</code>)**. Hai token của hai issuer khác nhau có cùng <code>sub</code> không mặc nhiên đại diện một tài khoản; email cũng không phải khóa định danh liên provider đáng tin cậy.

## 3. Nội dung chính của Discovery Document

OIDC Provider Configuration được cung cấp qua HTTP GET dưới dạng JSON. Ví dụ request:

~~~http
GET /realms/training/.well-known/openid-configuration HTTP/1.1
Host: login.example.org
Accept: application/json
~~~

Ví dụ response rút gọn:

~~~json
{
  "issuer": "https://login.example.org/realms/training",
  "authorization_endpoint": "https://login.example.org/realms/training/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.org/realms/training/protocol/openid-connect/token",
  "userinfo_endpoint": "https://login.example.org/realms/training/protocol/openid-connect/userinfo",
  "jwks_uri": "https://login.example.org/realms/training/protocol/openid-connect/certs",
  "response_types_supported": ["code", "id_token"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "claims_supported": ["sub", "iss", "aud", "exp", "iat", "name", "email"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "code_challenge_methods_supported": ["S256"]
}
~~~

Đây là dữ liệu minh họa, không phải metadata được kiểm tra từ một provider thực tế. OP có thể trả thêm nhiều trường hoặc bỏ các trường tùy chọn. Không giả định rằng các trường như <code>userinfo_endpoint</code>, <code>code_challenge_methods_supported</code>, <code>claims_supported</code> đều hiện diện.

### 3.1. Metadata nhận dạng và endpoint

| Trường | Ý nghĩa | Lúc sử dụng |
|---|---|---|
| <code>issuer</code> | Định danh OP | So khớp với issuer yêu cầu và claim <code>iss</code> |
| <code>authorization_endpoint</code> | Endpoint nhận Authorization Request | Chuyển trình duyệt đến đăng nhập |
| <code>token_endpoint</code> | Endpoint nhận Token Request | Đổi code lấy token qua back channel |
| <code>jwks_uri</code> | Endpoint công bố JSON Web Key Set | Tìm khóa công khai để xác minh chữ ký ID Token |
| <code>userinfo_endpoint</code> | Endpoint UserInfo nếu OP hỗ trợ | Lấy thông tin profile bằng access token |
| <code>end_session_endpoint</code> | Endpoint đăng xuất liên thông, nếu được công bố | Hỗ trợ RP-Initiated Logout tùy provider |

Trong Authorization Code Flow, Client cần biết authorization endpoint và token endpoint. Khi xác minh ID Token ký bất đối xứng, JWKS công bố public key dùng kiểm tra chữ ký. **JWKS không chứa mật khẩu người dùng hay client secret**, và các public key công bố ở đây không phải private key của OP.

### 3.2. Metadata mô tả khả năng

| Trường | Nội dung cần hiểu |
|---|---|
| <code>response_types_supported</code> | Các response type OP công bố; cần hỗ trợ <code>code</code> để dùng Authorization Code Flow |
| <code>subject_types_supported</code> | Các dạng subject như <code>public</code> và <code>pairwise</code> |
| <code>id_token_signing_alg_values_supported</code> | Thuật toán ký ID Token, ví dụ <code>RS256</code> |
| <code>scopes_supported</code> | Các scope công bố, bao gồm <code>openid</code> với OP OIDC |
| <code>claims_supported</code> | Một số claim OP có khả năng cung cấp |
| <code>grant_types_supported</code> | Các grant type được công bố nếu OP có trường này |
| <code>token_endpoint_auth_methods_supported</code> | Phương thức Client authentication tại token endpoint |
| <code>code_challenge_methods_supported</code> | Phương thức PKCE, ví dụ <code>S256</code>, nếu OP công bố |

Discovery phản ánh **khả năng của server**, không phải danh sách quyền của một Client cụ thể. OP có thể hỗ trợ <code>client_secret_basic</code> và <code>client_secret_post</code>, nhưng Client chỉ được sử dụng phương thức đã đăng ký. OP công bố scope <code>email</code> cũng không đồng nghĩa Client chắc chắn được cấp scope đó.

Discovery Document không cung cấp client secret, authorization code hay token của ứng dụng. Những thông tin này có vòng đời và kênh trao đổi độc lập.

## 4. Quan hệ tin cậy: issuer → metadata → ID Token

Có ba điểm kiểm tra liên kết với nhau:

1. **Issuer cấu hình:** ứng dụng biết trước OP được tin cậy, ví dụ <code>https://login.example.org/realms/training</code>.
2. **Issuer trong metadata:** OP công bố trường <code>issuer</code> trùng issuer đã cấu hình. Chỉ sau khi kiểm tra nguồn và tính nhất quán, Client mới sử dụng các endpoint trong metadata.
3. **Issuer trong ID Token:** claim <code>iss</code> phải khớp issuer tin cậy, đồng thời chữ ký và các claim bắt buộc phải hợp lệ.

~~~mermaid
flowchart TD
    A["Cấu hình issuer-uri"] --> B["Tra cứu OIDC Discovery Document"]
    B --> C{"metadata.issuer trùng issuer-uri?"}
    C -->|Không| X["Từ chối metadata / phát hiện sai OP"]
    C -->|Có| D["Lấy authorization endpoint, token endpoint, JWKS URI"]
    D --> E["Hoàn tất Authorization Code Flow"]
    E --> F["Nhận ID Token"]
    D --> G["Lấy / cache public key từ JWKS URI"]
    G --> H["Xác minh chữ ký ID Token"]
    F --> H
    H --> I{"iss, aud, exp và điều kiện OIDC khác hợp lệ?"}
    I -->|Không| Y["Từ chối đăng nhập"]
    I -->|Có| J["Chấp nhận danh tính người dùng"]
~~~

Một ID Token có chữ ký kiểm tra thành công về mặt toán học **chưa chắc đến từ issuer Client tin cậy**. Client phải kiểm tra <code>iss</code>, <code>aud</code> (thường chứa Client ID), <code>exp</code>, các thời điểm liên quan và các điều kiện OIDC như <code>nonce</code> khi flow sử dụng nonce. Ngược lại, <code>iss</code> khớp vẫn chưa đủ nếu chữ ký sai, token hết hạn hoặc audience không phù hợp.

Đặc biệt, không dùng claim <code>iss</code> trong token **chưa được xác minh** để tự động tin một provider mới. Issuer đáng tin cậy phải do cấu hình hoặc chính sách cho phép của ứng dụng quyết định trước.

### 4.1. Vai trò của JWKS và key rotation

Header của JWT có thể chứa:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

Trong JWKS của issuer đã tin cậy, Client tìm public key có <code>kid</code> phù hợp, bảo đảm thuật toán được cho phép rồi xác minh chữ ký. OP có thể công bố nhiều khóa cùng lúc để xoay vòng khóa ký. Thư viện Spring Security/Nimbus hỗ trợ cơ chế tìm key, cache và cập nhật tùy cấu hình; tránh hardcode một public key khi provider dự kiến dùng JWKS động.

## 5. Discovery và luồng OIDC Login

Lấy metadata thường xảy ra khi Spring Security khởi tạo hoặc resolve <code>ClientRegistration</code>, tùy phiên bản và cấu hình. Client **không nhất thiết gọi Discovery Document trên từng lần đăng nhập**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Spring Security Client
    participant OP as OpenID Provider
    participant B as Trình duyệt
    C->>OP: GET OIDC Configuration Endpoint
    OP-->>C: JSON metadata: issuer, endpoints, jwks_uri
    C->>C: Đối chiếu metadata.issuer với issuer-uri
    B->>C: GET /oauth2/authorization/training
    C-->>B: Redirect đến authorization_endpoint
    B->>OP: Authorization Request: scope=openid, response_type=code...
    OP-->>B: Callback redirect có code và state
    B->>C: GET /login/oauth2/code/training?code=...&state=...
    C->>OP: POST token_endpoint để đổi code lấy token
    OP-->>C: ID Token và token liên quan
    C->>OP: GET jwks_uri (khi cần tải/cập nhật key)
    OP-->>C: JWKS công khai
    C->>C: Xác minh chữ ký, iss, aud, exp, các claim liên quan
    C-->>B: Hoàn tất phiên đăng nhập
~~~

Các bước có chức năng khác nhau: discovery dùng để tìm cấu hình OP; authorization endpoint tiếp nhận yêu cầu đăng nhập; token endpoint xử lý đổi code; JWKS cung cấp dữ liệu xác minh chữ ký. **Issuer xuyên suốt luồng**, bảo đảm Client nhận đúng cấu hình và ID Token của đúng nhà cung cấp.

Nếu dùng PKCE, Client còn gửi code challenge trong authorization request và verifier trong token request để bảo vệ authorization code. PKCE giải quyết một rủi ro khác; nó không thay cho kiểm tra issuer hay chữ ký ID Token.

## 6. Sử dụng issuer-uri trong Spring Security OAuth2 Client

### 6.1. Ví dụ Spring Boot 3 / Spring Security 6

Ứng dụng OIDC web Client thường cần dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Cấu hình <code>application.yml</code>:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training-oidc
            client-id: training-web-client
            client-secret: replace-with-secret-from-vault
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          training-oidc:
            issuer-uri: https://login.example.org/realms/training
~~~

Giá trị client secret là placeholder dành cho bài học. Trong dự án thật, đọc secret từ cơ chế quản lý bí mật/biến môi trường an toàn, không commit vào repository; tại OP phải đăng ký đúng Client ID, phương thức xác thực và redirect URI.

Giải thích các thành phần:

- <code>training</code>: **registration ID** trong ứng dụng Spring, đồng thời xuất hiện ở đường dẫn bắt đầu đăng nhập mặc định <code>/oauth2/authorization/training</code>.
- <code>training-oidc</code>: **provider ID** nội bộ để liên kết registration tới cấu hình OP; không cần giống issuer.
- <code>issuer-uri</code>: URL issuer **gốc**. Không ghi thêm hậu tố <code>/.well-known/openid-configuration</code>.
- Metadata discovery cho Spring Security biết <code>authorizationUri</code>, <code>tokenUri</code>, <code>jwkSetUri</code> và các chi tiết cần thiết.
- Scope <code>openid</code> thể hiện yêu cầu OIDC; Client kỳ vọng nhận ID Token và xác minh nó theo OIDC.

Một cấu hình đăng nhập tối thiểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Sau xác thực OIDC thành công, có thể lấy principal <code>OidcUser</code> để đọc các claim đã được thư viện xác minh. Ví dụ endpoint chỉ trả thông tin định danh tối thiểu:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getSubject()
        );
    }
}
~~~

Không trả nguyên access token, refresh token hay ID Token trong API chỉ để kiểm tra đăng nhập. Các token này có thể cho phép truy cập tài nguyên và cần được bảo vệ.

### 6.2. Lợi ích và giới hạn của cấu hình issuer-uri

Khi metadata hợp lệ, Spring Security dùng endpoint provider công bố và JWKS để phục vụ luồng OIDC. Ứng dụng tránh phải hardcode nhiều URL; việc xoay key hoặc thay đổi endpoint do OP công bố có thể được thư viện xử lý theo vòng đời metadata/cache thích hợp.

Tuy nhiên, cấu hình issuer không thay thế <code>client-id</code>, Client authentication, redirect URI, scope, cấp quyền hay session management. Discovery hoạt động chỉ xác nhận Client thu được metadata; chưa có nghĩa người dùng đã đăng nhập hoặc token đã hợp lệ.

Theo cách Boot/Spring Security xây dựng ClientRegistration, việc lấy metadata có thể cần kết nối tới OP trong giai đoạn khởi động. Nếu OP lỗi, DNS sai, chứng chỉ TLS không hợp lệ hoặc metadata trả về sai, ứng dụng có thể gặp lỗi khi dựng cấu hình. Cần bảo đảm OP ổn định và hạ tầng có đường kết nối cần thiết.

Ngoài YAML, Spring Security còn có các factory API trong <code>ClientRegistrations</code> để dựng đăng ký Client từ issuer. Trong ứng dụng thông thường, nên để framework thực hiện discovery và xác minh token; tự gọi HTTP, parse JSON và tự lắp ghép ClientRegistration dễ bỏ sót kiểm tra quan trọng.

## 7. Phân biệt OIDC Discovery và OAuth 2.0 Authorization Server Metadata

Hai tiêu chuẩn liên quan nhưng không hoàn toàn giống nhau:

- **OpenID Connect Discovery 1.0** mô tả OpenID Provider Configuration, thường với hậu tố <code>/.well-known/openid-configuration</code>. Metadata có các trường đặc thù OIDC như <code>subject_types_supported</code>, <code>id_token_signing_alg_values_supported</code>.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata** mô tả metadata của OAuth Authorization Server, có well-known suffix mặc định <code>/.well-known/oauth-authorization-server</code> và quy tắc chèn path khác khi issuer có path.

Ví dụ:

| Khái niệm | URL ví dụ |
|---|---|
| Issuer | <code>https://login.example.org/realms/training</code> |
| OIDC Discovery URL | <code>https://login.example.org/realms/training/.well-known/openid-configuration</code> |
| RFC 8414 metadata URL (suffix mặc định) | <code>https://login.example.org/.well-known/oauth-authorization-server/realms/training</code> |

Lưu ý vị trí <code>/.well-known/</code>: ví dụ OIDC đặt **sau path issuer**, còn RFC 8414 đặt well-known **trước path issuer**. Một số OP và thư viện hỗ trợ nhiều dạng URL tương thích, nhưng không nên tự giả định mọi provider triển khai đủ mọi biến thể.

Để triển khai **OIDC Login**, Client cần metadata và cơ chế xác minh đúng OIDC. Một Authorization Server chỉ cung cấp metadata OAuth 2.0 không có nghĩa nó tự động phát ID Token hoặc đáp ứng đầy đủ các yêu cầu OIDC.

## 8. Issuer khi có nhiều môi trường và tenant

### 8.1. Development, staging, production

~~~text
Development: https://login-dev.example.org/realms/training
Staging:     https://login-staging.example.org/realms/training
Production:  https://login.example.org/realms/training
~~~

Mỗi môi trường cần issuer, Client ID, secret/method và redirect URI phù hợp. Một ứng dụng production không nên chấp nhận ID Token do issuer staging phát hành chỉ vì cả hai hệ thống cùng tên realm hoặc cùng mã nguồn.

Khi OP chạy sau reverse proxy, metadata có thể trả issuer nội bộ:

~~~text
http://identity-service:8080/realms/training
~~~

Trong khi Client dùng public issuer:

~~~text
https://login.example.org/realms/training
~~~

Mismatch trong trường hợp đó là lỗi bảo vệ chính đáng. Cần cấu hình public hostname/external issuer và proxy headers trên OP đúng với URL bên ngoài, không bỏ kiểm tra issuer để vượt qua lỗi.

### 8.2. Nhiều ClientRegistration

Ứng dụng có thể khai báo hai OP riêng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-a:
            provider: company-a
            client-id: web-company-a
            client-secret: replace-with-secret-a
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          company-b:
            provider: company-b
            client-id: web-company-b
            client-secret: replace-with-secret-b
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company-a:
            issuer-uri: https://login.example.org/realms/company-a
          company-b:
            issuer-uri: https://login.example.org/realms/company-b
~~~

Đây là ví dụ minh họa; triển khai thật cần registration chính thức và secret/authentication method phù hợp với từng OP. Ứng dụng không được gộp định danh dựa trên <code>sub</code> đơn lẻ qua hai issuer.

Nếu cho phép người dùng nhập issuer URL để ứng dụng tự fetch metadata, hãy sử dụng danh sách provider được phép hoặc quy trình xác minh riêng. **Không tự động tải một issuer tùy ý nhận từ request** vì có thể tạo rủi ro SSRF và chấp nhận nhà cung cấp giả mạo. Nên chọn ClientRegistration tin cậy đã được quản trị viên đăng ký.

## 9. Nếu OP không hỗ trợ Discovery

Với một số hệ thống OAuth/OIDC cũ, có thể phải khai báo endpoint thủ công:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy:
            provider: legacy
            client-id: legacy-web
            client-secret: replace-with-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          legacy:
            authorization-uri: https://legacy.example.org/oauth/authorize
            token-uri: https://legacy.example.org/oauth/token
            jwk-set-uri: https://legacy.example.org/oauth/jwks
            user-info-uri: https://legacy.example.org/oauth/userinfo
            user-name-attribute: sub
~~~

Các URL và secret đều là placeholder. Cấu hình thủ công chỉ hợp lệ với OIDC nếu OP thực sự phát ID Token đúng chuẩn và Client có cơ chế xác minh phù hợp. Đặc biệt, **phải xác nhận issuer được xác định và kiểm tra như thế nào khi dùng cấu hình manual trong phiên bản Spring Security hiện tại**. Việc điền riêng authorization endpoint, token endpoint và JWKS URI không tự động bảo đảm các ràng buộc issuer giống khi lấy từ discovery.

Nếu provider chỉ hỗ trợ OAuth 2.0, không phát ID Token OIDC, thì dù Authorization Code Flow hoạt động cũng **không phải** một tích hợp OIDC đầy đủ. Access token không được mặc nhiên xem là ID Token hoặc bằng chứng danh tính dành cho Client.

## 10. Kiểm tra Discovery Document khi tích hợp

Trên môi trường phát triển, có thể đọc public metadata bằng công cụ HTTP:

~~~bash
curl --fail --silent --show-error \
  "https://login.example.org/realms/training/.well-known/openid-configuration"
~~~

Hoặc dùng PowerShell:

~~~powershell
$metadata = Invoke-RestMethod -Uri "https://login.example.org/realms/training/.well-known/openid-configuration"
$metadata.issuer
$metadata.authorization_endpoint
$metadata.token_endpoint
$metadata.jwks_uri
~~~

Trước hết đối chiếu <code>issuer</code> trong JSON với issuer được cấu hình. Chỉ thấy HTTP 200 hoặc JSON hợp lệ chưa đủ để kết luận đúng OP; proxy/tenant router có thể trả metadata của realm khác.

Trình tự kiểm tra hữu ích:

1. Lấy issuer chính thức từ cấu hình quản trị hoặc tài liệu của OP, không dùng trang login hay discovery URL làm issuer.
2. Truy cập discovery qua HTTPS, kiểm tra chứng chỉ, status và cấu trúc metadata.
3. Xác nhận <code>issuer</code> được trả về khớp với issuer đã cấu hình, kể cả path và dấu <code>/</code>.
4. Xác nhận endpoint do metadata công bố có thể truy cập từ ứng dụng; kiểm tra <code>response_types_supported</code> hỗ trợ <code>code</code>.
5. Kiểm tra Client ID, authentication method, redirect URI và scope đã đăng ký với OP.
6. Thử đăng nhập; nếu lỗi token, kiểm tra issuer, audience, thời hạn token, JWKS và <code>kid</code> mà không in nguyên token ra log.

### 10.1. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Discovery URL trả HTTP 404 | Sai issuer/path, OP chưa bật discovery hoặc nhầm quy ước URL OIDC/RFC 8414 | Kiểm tra issuer và metadata URL được OP công bố chính thức |
| ClientRegistration khởi tạo thất bại | DNS/TLS/proxy lỗi, OP không sẵn sàng hoặc JSON không hợp lệ | Kiểm tra mạng, certificate trust, response và cấu hình Spring |
| <code>issuer mismatch</code> khi đọc metadata | <code>metadata.issuer</code> khác issuer cấu hình | Sửa public issuer tại OP hoặc issuer-uri ở Client cho đúng provider |
| ID Token bị từ chối do <code>iss</code> | Token phát hành từ realm/tenant khác | Xác minh route đăng nhập và đúng ClientRegistration |
| Chữ ký ID Token không hợp lệ | JWKS sai, không tìm được <code>kid</code>, thuật toán không được phép hoặc key rotation | Kiểm tra đúng JWKS của issuer và bộ giải mã token |
| Authorization thành công nhưng token endpoint lỗi | Sai Client ID/secret, authentication method, redirect URI hoặc grant | Kiểm tra registration thực tế và token endpoint metadata |
| Có access token nhưng không có ID Token | Không gửi <code>openid</code> hoặc OP chỉ hỗ trợ OAuth 2.0 | Phân biệt OAuth 2.0 với OIDC và kiểm tra hỗ trợ của OP |
| Người dùng của hai tenant bị gộp tài khoản | Lưu user chỉ theo email hoặc <code>sub</code> | Dùng cặp <code>(iss, sub)</code> để định danh liên issuer |

## 11. Các nguyên tắc bảo mật

**Issuer là cấu hình tin cậy:** chỉ chấp nhận các OP được phép. Không tải metadata theo URL không được kiểm soát do người dùng gửi vì có nguy cơ SSRF và đăng nhập qua OP giả.

**Metadata phải được xác minh:** tải qua HTTPS với TLS validation, đối chiếu metadata issuer và endpoint theo chính sách tin cậy của ứng dụng. Không tin nhà cung cấp mới chỉ vì JSON có các khóa <code>authorization_endpoint</code> và <code>token_endpoint</code>.

**Không bỏ kiểm tra ID Token:** chữ ký, issuer, audience, expiration và điều kiện OIDC liên quan phải hợp lệ. Một JWT tự khai <code>iss</code> không đủ để khiến Client chấp nhận token đó.

**Chuẩn bị cho thay đổi hợp lệ:** OP có thể xoay public key, đổi endpoint hoặc cấu hình lại metadata. Dùng thư viện OIDC phù hợp, quản lý cache và monitor lỗi discovery/JWKS; tránh hardcode khóa công khai duy nhất khi provider hỗ trợ JWKS động.

**Phân biệt Client và Resource Server:** <code>spring.security.oauth2.client.provider.*.issuer-uri</code> dùng để cấu hình OAuth2/OIDC Client. <code>spring.security.oauth2.resourceserver.jwt.issuer-uri</code> dùng khi ứng dụng đóng vai trò Resource Server xác minh JWT của request đến. Một ứng dụng có thể đảm nhiệm cả hai vai trò nhưng chúng có cấu hình và luồng xử lý riêng.

## 12. Câu hỏi và bài thực hành

### Tình huống A — Tính URL Discovery

OP công bố issuer:

~~~text
https://sso.example.net/tenant/alpha
~~~

**Câu hỏi:** URL discovery theo OIDC Discovery, giá trị <code>issuer-uri</code> và claim <code>iss</code> mong đợi là gì?

**Đáp án:**

~~~text
Discovery URL:
https://sso.example.net/tenant/alpha/.well-known/openid-configuration

issuer-uri:
https://sso.example.net/tenant/alpha

ID Token iss:
https://sso.example.net/tenant/alpha
~~~

### Tình huống B — Discovery của realm khác

Client cấu hình <code>https://sso.example.net/realms/alpha</code>, nhưng metadata trả:

~~~json
{
  "issuer": "https://sso.example.net/realms/beta",
  "authorization_endpoint": "https://sso.example.net/realms/beta/auth",
  "token_endpoint": "https://sso.example.net/realms/beta/token",
  "jwks_uri": "https://sso.example.net/realms/beta/jwks"
}
~~~

**Đáp án:** Không được bỏ kiểm tra issuer để dùng endpoint của realm <code>beta</code>. Cần sửa đường dẫn, cấu hình tenant hoặc tạo registration hợp lệ cho realm <code>beta</code> nếu đó là provider thực sự mong muốn.

### Tình huống C — Hai subject có giống nhau không?

~~~text
Token A: iss=https://sso.example.net/realms/alpha, sub=12345
Token B: iss=https://sso.example.net/realms/beta,  sub=12345
~~~

**Đáp án:** Không mặc nhiên là cùng một tài khoản. Subject identifier có ý nghĩa trong phạm vi issuer. Khóa nhận diện xuyên provider nên gồm cả <code>iss</code> và <code>sub</code>. Nếu muốn liên kết hai tài khoản, ứng dụng cần quy trình account linking riêng và có xác minh.

### Bài thực hành với Spring Security

1. Chọn một OP OIDC được phép trong môi trường phát triển và lấy issuer chính thức.
2. Truy cập Discovery Document, quan sát <code>issuer</code>, authorization endpoint, token endpoint, JWKS URI.
3. Cấu hình <code>issuer-uri</code> trong Spring Boot OAuth2 Client, bật <code>oauth2Login()</code>, đăng nhập từ <code>/oauth2/authorization/&lt;registrationId&gt;</code>.
4. Sau đăng nhập, đọc claim <code>iss</code> từ principal OIDC đã được Spring Security xác minh; đối chiếu với issuer gốc.
5. Trong môi trường thử nghiệm, cố ý cấu hình issuer realm khác và quan sát lỗi khi discovery hoặc ID Token validation, không tắt kiểm tra để vượt qua.

## 13. Ghi nhớ

- **Issuer** là danh tính OP được Client tin cậy; giá trị đó xuất hiện trong metadata dưới tên <code>issuer</code> và ID Token dưới claim <code>iss</code>.
- **Discovery Document** mô tả endpoint, JWKS URI và các khả năng của OP. Với OIDC, vị trí thường là <code>&lt;issuer&gt;/.well-known/openid-configuration</code>.
- Client cần **đối chiếu metadata issuer với issuer đã cấu hình**, đồng thời xác minh ID Token về chữ ký, issuer, audience, thời hạn và những điều kiện OIDC liên quan.
- Trong Spring Security OAuth2 Client, dùng <code>spring.security.oauth2.client.provider.&lt;provider-id&gt;.issuer-uri</code> để framework khám phá và xây dựng thông tin ClientRegistration.
- Issuer không phải Discovery URL, authorization endpoint, token endpoint, JWKS URI, Client ID hay redirect URI. Trong hệ thống đa tenant, mỗi issuer có phạm vi tin cậy và định danh riêng.

### Tài liệu tham khảo

- **OpenID Connect Discovery 1.0**: Provider Configuration, issuer, metadata fields và quy tắc khám phá.
- **OpenID Connect Core 1.0**: ID Token, claim <code>iss</code>/<code>aud</code> và yêu cầu xác minh ID Token.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata**: metadata OAuth 2.0 và quy tắc well-known URI.
- **RFC 7517 — JSON Web Key (JWK)** và **RFC 7518 — JSON Web Algorithms (JWA)**: mô tả khóa và thuật toán trong JWT.
- **Spring Security Reference — OAuth2 Client / OAuth2 Login** và **Spring Boot Reference — OAuth2 Client**: ClientRegistration, issuer-uri và OIDC Login.
