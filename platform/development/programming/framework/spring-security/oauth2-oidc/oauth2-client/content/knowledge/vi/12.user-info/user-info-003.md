# 12.3. Cấu hình UserInfo Endpoint và cách gửi access token

## 1. UserInfo Endpoint nằm ở đâu trong quá trình đăng nhập OIDC?

Trong hệ thống **Spring Security OAuth 2.0 OIDC Client**, người dùng thường đăng nhập bằng **Authorization Code flow**. Sau khi đổi authorization code tại token endpoint, ứng dụng nhận **ID Token** và **Access Token**. ID Token cung cấp thông tin cần thiết để client xác thực người dùng theo OpenID Connect (OIDC); Access Token có thể cho phép client truy vấn thêm thông tin hồ sơ tại **UserInfo Endpoint** do OpenID Provider (OP) công bố.

Hãy xét ứng dụng web Spring Boot muốn hiển thị tên, ảnh đại diện và email của nhân viên sau khi đăng nhập. ID Token có thể chỉ chứa các claim tối thiểu như `iss`, `sub`, `aud` và `exp`. Thông tin như `name`, `picture` hoặc `email` có thể được OP cung cấp qua UserInfo. Để gọi đúng endpoint, Spring Security cần biết **URL UserInfo** và **cách gửi Access Token**.

Bài học tập trung vào:

1. Vai trò của UserInfo trong OIDC và sự khác biệt với ID Token.
2. Cấu hình `user-info-uri` qua OIDC Discovery hoặc cấu hình provider tường minh.
3. Các cách gửi Access Token: **Bearer Authorization header**, form body và query string.
4. Cách Spring Security Servlet sử dụng `OidcUserService` và `DefaultOAuth2UserService`.
5. Quy tắc xác minh `sub`, xử lý claim thiếu, lỗi HTTP và các yêu cầu bảo mật.

**Phạm vi:** Ví dụ chủ yếu áp dụng cho Spring Boot dùng **Spring MVC/Servlet** với `HttpSecurity` và `SecurityFilterChain`. WebFlux sử dụng các thành phần reactive khác; không nên sao chép cấu hình Servlet nguyên xi sang WebFlux.

## 2. UserInfo không phải ID Token, cũng không phải API nghiệp vụ

Ba thành phần thường xuất hiện cùng nhau nhưng phục vụ những mục đích khác nhau:

| Thành phần | Được lấy từ đâu? | Mục đích | Ai sử dụng? |
| --- | --- | --- | --- |
| **ID Token** | Token Endpoint trong OIDC flow hợp lệ | Bằng chứng xác thực theo OIDC, sau khi client xác minh | OIDC Client |
| **Access Token** | Token Endpoint | Cho phép truy cập tài nguyên/endpoint được cấp quyền | UserInfo Endpoint hoặc Resource Server tương ứng |
| **UserInfo response** | UserInfo Endpoint | Cung cấp các claim về người dùng được phép chia sẻ | OIDC Client, sau khi đối chiếu danh tính |

**UserInfo là endpoint và dữ liệu phản hồi, không phải một loại token thứ ba.** Cũng không thể lấy Access Token từ UserInfo; Access Token được cấp tại Token Endpoint và được client dùng khi gọi UserInfo.

Ví dụ, một ID Token đã được giải mã để minh họa:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "user-4a7f",
  "aud": "portal-web",
  "iat": 1925000000,
  "exp": 1925003600
}
~~~

UserInfo response có thể cung cấp dữ liệu bổ sung:

~~~json
{
  "sub": "user-4a7f",
  "name": "Nguyen An",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true,
  "picture": "https://cdn.example.com/avatars/u4a7f.png"
}
~~~

Ứng dụng **không được chỉ nhìn vào email hoặc name rồi coi đó là cùng người dùng**. Trong OIDC, trường `sub` của UserInfo phải khớp `sub` trong ID Token đã được xác minh; nếu không khớp, **không sử dụng UserInfo response**.

### 2.1. UserInfo Endpoint khác API hồ sơ OAuth 2.0 thuần

Một provider **OAuth 2.0 không hỗ trợ OIDC** vẫn có thể cung cấp API như `/api/me` để lấy JSON:

~~~json
{
  "id": 789,
  "displayName": "Nguyen An",
  "account": "an.nguyen"
}
~~~

API này có thể được Spring Security `DefaultOAuth2UserService` gọi theo cấu hình `user-info-uri`, nhưng **không mặc nhiên là OIDC UserInfo Endpoint**: OAuth 2.0 thuần không chuẩn hóa ID Token và ràng buộc `UserInfo.sub == IDToken.sub`.

Vì vậy:

- Với **OIDC**, sử dụng `openid`, xác minh ID Token và đối chiếu `sub` của UserInfo.
- Với **OAuth2 Login thuần**, xác định trường định danh ổn định theo hợp đồng provider, ví dụ `id`, thông qua `user-name-attribute`.
- Với **API nghiệp vụ** như đơn hàng/lịch làm việc, dùng HTTP client gọi **Resource Server phù hợp**, không tự nhận API đó là UserInfo.

## 3. Luồng gọi UserInfo trong Authorization Code + OIDC

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant Client as Spring Boot Servlet OIDC Client
    participant OP as OpenID Provider
    Browser->>Client: Mở /me chưa đăng nhập
    Client-->>Browser: Redirect tới /oauth2/authorization/company
    Browser->>OP: Authorization request (openid profile email, state, PKCE...)
    OP-->>Browser: Callback với code + state
    Browser->>Client: GET /login/oauth2/code/company?code=...
    Client->>OP: POST Token Endpoint với code
    OP-->>Client: Access Token + ID Token
    Client->>Client: Xác minh ID Token (chữ ký, iss, aud, exp, nonce nếu áp dụng)
    opt UserInfo được cấu hình và cần tải hồ sơ
        Client->>OP: GET UserInfo Endpoint - Authorization: Bearer Access Token
        OP-->>Client: UserInfo response có sub và các claim được phép
        Client->>Client: Kiểm tra UserInfo.sub == ID Token.sub
    end
    Client-->>Browser: Hoàn tất Authentication và session
    Browser->>Client: GET /me có session
    Client-->>Browser: Chỉ những claim ứng dụng chọn công bố
~~~

Cần để ý **đường đi của Access Token**: nó được gửi **từ backend của client đến UserInfo Endpoint qua HTTPS**, không cần đưa qua JavaScript frontend, URL browser hoặc trang HTML. Với ứng dụng server-side Servlet, đây là mô hình *back-channel request*.

Việc gọi UserInfo **không nhất thiết diễn ra sau mọi lần đăng nhập hoặc mỗi lần mở trang**. Spring Security có thể quyết định tải UserInfo trong giai đoạn dựng principal theo cấu hình provider, grant, scope và user service; sau đó ứng dụng sử dụng principal đã có trong SecurityContext/session.

## 4. Cấu hình UserInfo qua OIDC Discovery

### 4.1. Discovery tìm endpoint như thế nào?

OIDC Provider có thể công bố tài liệu metadata, thường thông qua đường dẫn chuẩn dựa trên issuer:

~~~text
Issuer:
  https://id.example.com/realms/company

OpenID Provider Configuration:
  https://id.example.com/realms/company/.well-known/openid-configuration
~~~

Ví dụ metadata rút gọn:

~~~json
{
  "issuer": "https://id.example.com/realms/company",
  "authorization_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://id.example.com/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/userinfo"
}
~~~

Những URL này là **ví dụ minh họa**, không phải endpoint thật của một provider xác định. Nhà cung cấp có thể dùng cách đặt đường dẫn khác. `userinfo_endpoint` là tên trường trong **OIDC Discovery metadata**; Spring Security ánh xạ vào `ClientRegistration.ProviderDetails.UserInfoEndpoint`.

### 4.2. application.yml dùng issuer-uri

Một cách cấu hình thông dụng trong Spring Boot Servlet:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Với OIDC Discovery hợp lệ, Spring Boot/Spring Security lấy được các endpoint, trong đó có **UserInfo URI nếu provider công bố**. Không nhất thiết phải sao chép `user-info-uri` từ metadata vào YAML.

**Điểm quan trọng:**

- `issuer-uri` dùng để xác định issuer tin cậy và tìm metadata, **không phải URL UserInfo**.
- `registration.company` là một client registration, còn `provider.company-oidc` là cấu hình nhà cung cấp.
- `openid` chuyển yêu cầu đăng nhập sang OIDC; `profile` và `email` yêu cầu thêm những claim tương ứng theo chính sách OP.
- Secret lấy từ biến môi trường hoặc secret manager; không commit vào source control.
- OIDC discovery có thể cần kết nối mạng khi khởi tạo registration; nếu issuer không truy cập được hoặc metadata sai, ứng dụng có thể lỗi startup.

Trong nhiều cấu hình thông dụng, **đặt `issuer-uri` là lựa chọn tốt hơn cấu hình từng endpoint**, vì giúp đồng bộ token endpoint, JWKS, UserInfo và issuer với metadata thực của OP.

## 5. Cấu hình UserInfo URI tường minh

Không phải provider nào cũng công bố đủ discovery metadata. Đối với **OAuth2 provider thuần** có API hồ sơ riêng, có thể chỉ định các URI:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          community:
            provider: community-oauth
            client-id: ${COMMUNITY_CLIENT_ID}
            client-secret: ${COMMUNITY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          community-oauth:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://api.example.net/v1/me
            user-info-authentication-method: header
            user-name-attribute: id
~~~

Ở ví dụ trên, provider **không được giả định là OIDC** vì registration không yêu cầu `openid` và không có ID Token theo chuẩn. `user-name-attribute: id` nói Spring Security lấy trường `id` từ response của API hồ sơ để làm định danh principal cho `OAuth2User`.

Ví dụ JSON của API:

~~~json
{
  "id": "member-789",
  "display_name": "Nguyen An",
  "email": "an@example.com"
}
~~~

Nếu provider sử dụng trường `user_id` thay `id`, cần thay cấu hình `user-name-attribute` đúng theo tài liệu chính thức. Nếu JSON lồng nhiều cấp hoặc cần header đặc biệt, có thể cần custom `OAuth2UserService`.

### 5.1. Mapping giữa Spring Boot properties và Java API

| Thuộc tính Spring Boot | Thành phần trong ClientRegistration | Ý nghĩa |
| --- | --- | --- |
| `spring.security.oauth2.client.provider.<id>.user-info-uri` | `getProviderDetails().getUserInfoEndpoint().getUri()` | URI để tải claim/profile |
| `...user-info-authentication-method` | `getUserInfoEndpoint().getAuthenticationMethod()` | Cách gửi Access Token |
| `...user-name-attribute` | `getUserInfoEndpoint().getUserNameAttributeName()` | Trường định danh trong response OAuth2 UserInfo-like API |
| `...issuer-uri` | `getProviderDetails().getIssuerUri()` | Issuer OIDC, đầu mối discovery |
| `...authorization-uri` | `getProviderDetails().getAuthorizationUri()` | Authorization Endpoint |
| `...token-uri` | `getProviderDetails().getTokenUri()` | Token Endpoint |
| `...jwk-set-uri` | `getProviderDetails().getJwkSetUri()` | URL JWKS |

`<id>` trong bảng chỉ là placeholder cho provider ID. Trong YAML thực tế, dùng tên như `company-oidc` hoặc `community-oauth`, **không đưa dấu `<`/`>` vào khóa cấu hình**.

**Với OIDC provider, không nên tự cấu hình một tập endpoint tùy ý mà bỏ kiểm tra issuer, JWKS và ID Token.** Khi provider không hỗ trợ discovery, việc tạo registration tường minh phải đi cùng cấu hình tin cậy và đầy đủ cho OIDC validation.

### 5.2. Đọc UserInfo Endpoint đã được cấu hình

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

public final class ProviderDetailsInspector {

    private final ClientRegistrationRepository repository;

    public ProviderDetailsInspector(ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public String userInfoUri() {
        ClientRegistration registration =
            repository.findByRegistrationId("company");

        if (registration == null) {
            throw new IllegalStateException("Missing registration: company");
        }

        return registration.getProviderDetails()
            .getUserInfoEndpoint().getUri();
    }
}
~~~

`ClientRegistrationRepository` và `ProviderDetails` chỉ mô tả cấu hình; **đọc URI không gửi HTTP request**. Phần HTTP call được xử lý bởi user service hoặc HTTP client tương ứng.

## 6. Ba cách gửi Access Token tới UserInfo

OIDC UserInfo Endpoint được bảo vệ bằng Access Token. Với Bearer Token, cơ chế truyền token có thể dựa trên HTTP Authorization header, form body hoặc URI query theo các quy tắc liên quan của OAuth 2.0 Bearer Token Usage.

### 6.1. Cách nên ưu tiên: Authorization header

Yêu cầu HTTP:

~~~http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: id.example.com
Accept: application/json
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Ý nghĩa:

- `Authorization` là HTTP header được dùng để truyền Bearer credential.
- `Bearer` là token type; phần theo sau là giá trị Access Token do Token Endpoint cấp.
- UserInfo Endpoint kiểm tra token rồi trả những claim mà OP cho phép.
- Không cần đặt Access Token vào query string hoặc vào route của browser.

Đây thường là cách dễ triển khai và an toàn hơn so với query token, miễn là kết nối dùng **HTTPS**, TLS được xác minh và ứng dụng không ghi Authorization header vào log.

Cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-oidc:
            user-info-authentication-method: header
~~~

Đây là đoạn **minh họa thuộc tính**, không phải YAML độc lập đầy đủ: provider và registration thực tế còn phải được định nghĩa. Khi provider hỗ trợ cách truyền Bearer qua header, thông thường không cần thêm custom user service.

### 6.2. Form-encoded body khi provider yêu cầu

Bearer Token Usage cũng mô tả truyền token trong form body với `application/x-www-form-urlencoded` theo ràng buộc của cơ chế đó:

~~~http
POST /userinfo HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

access_token=ACCESS_TOKEN_VALUE
~~~

Cách này chỉ sử dụng khi provider thực sự hỗ trợ/đòi hỏi. Access Token nằm trong **request body**, không phải JSON profile response.

Cấu hình tương ứng nếu provider chấp nhận:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-oidc:
            user-info-authentication-method: form
~~~

Không tự chuyển sang form để “sửa” một lỗi 401 khi provider đang kỳ vọng Bearer header. Trước tiên hãy xác định token có đúng issuer, audience/resource, scope và còn hạn hay không.

### 6.3. Token trong query string: nên tránh

Một URL có thể trông như:

~~~http
GET /userinfo?access_token=ACCESS_TOKEN_VALUE HTTP/1.1
Host: id.example.com
~~~

Cách này được mô tả cho một số tình huống tương thích nhưng **không khuyến nghị** khi có lựa chọn khác vì URI thường bị ghi vào access logs, tracing, monitoring, reverse proxy logs, browser history hoặc các hệ thống phân tích.

Một provider legacy có thể yêu cầu:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          legacy-provider:
            user-info-authentication-method: query
~~~

Chỉ dùng sau khi đánh giá rủi ro và xác nhận đây là hợp đồng bắt buộc. Đối với hệ thống mới, ưu tiên **`header`**.

### 6.4. So sánh các phương thức

| Phương thức | Vị trí Access Token | Điểm mạnh | Nguy cơ / lưu ý |
| --- | --- | --- | --- |
| `header` | `Authorization: Bearer ...` | Chuẩn, phổ biến, tránh đưa token vào URI | Phải bảo vệ header khỏi log/trace, dùng HTTPS |
| `form` | Body `access_token=...` của POST form | Hữu ích nếu provider chỉ hỗ trợ kiểu này | Body cũng nhạy cảm; cần content type/method đúng |
| `query` | `?access_token=...` | Tương thích một số API legacy | URL dễ bị ghi log/rò rỉ, nên tránh |

**Không gửi cùng Access Token ở nhiều vị trí trong một request.** Việc gửi Bearer Token qua nhiều phương thức đồng thời bị cấm trong cách sử dụng Bearer Token chuẩn; hãy chọn **một** cách phù hợp hợp đồng provider.

### 6.5. Đừng nhầm UserInfo authentication với client authentication

Hai thuộc tính có tên giống nhau nhưng phục vụ bước khác:

| Thuộc tính | Áp dụng khi nào? | Giá trị ví dụ |
| --- | --- | --- |
| `client-authentication-method` | Client xác thực với **Token Endpoint** khi xin token | `client_secret_basic`, `client_secret_post`, `private_key_jwt`, `none` tùy client |
| `user-info-authentication-method` | Client gửi **Access Token đến UserInfo Endpoint** | `header`, `form`, `query` |

Không dùng `client-secret` để thay Access Token khi gọi UserInfo. Với request UserInfo kiểu Bearer, client trình bày **Access Token của người dùng đã được cấp quyền**, không phải ID Token hoặc client credentials.

## 7. UserInfo Endpoint trả những gì?

Trong OIDC, UserInfo response có thể chứa `sub` và nhiều claim hồ sơ:

~~~json
{
  "sub": "user-4a7f",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true,
  "locale": "vi-VN",
  "picture": "https://cdn.example.com/avatars/u4a7f.png"
}
~~~

### 7.1. Claim được phép không đồng nghĩa claim luôn được trả

Những scope OIDC phổ biến:

| Scope | Nhóm claim thường liên quan | Lưu ý |
| --- | --- | --- |
| `openid` | Danh tính OIDC qua ID Token | Cần cho OIDC login |
| `profile` | `name`, `given_name`, `family_name`, `preferred_username`, `picture`, `locale`... | Claim có thể thiếu do user/provider policy |
| `email` | `email`, `email_verified` | Email có thể không tồn tại hoặc chưa được xác minh |
| `phone` | `phone_number`, `phone_number_verified` | Phụ thuộc provider và consent |
| `address` | `address` | Có thể là object và chứa dữ liệu cá nhân nhạy cảm |

Nếu yêu cầu `email` mà UserInfo không trả email, **không nên coi đó mặc nhiên là lỗi xác thực**; cần xem chính sách cấp claim của OP và cách xử lý dữ liệu thiếu trong ứng dụng.

### 7.2. Quy tắc bắt buộc: so khớp `sub`

Ví dụ ID Token đã xác minh:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "user-4a7f",
  "aud": "portal-web"
}
~~~

UserInfo response bất ngờ:

~~~json
{
  "sub": "user-OTHER",
  "email": "an@example.com"
}
~~~

**Phải từ chối sử dụng dữ liệu UserInfo này**, vì `user-OTHER` không bằng `user-4a7f`. Việc hai response có cùng email hoặc tên hiển thị không giải quyết được sai lệch subject.

Trong Spring Security, `OidcUserService` thực hiện logic lấy và kiểm tra thông tin OIDC phù hợp; dùng triển khai mặc định thường an toàn hơn việc tự gọi UserInfo rồi ghép claim tùy ý vào principal.

### 7.3. Khóa nhận diện tài khoản

Với OIDC, một định danh bền vững nên dựa trên **`issuer + subject`**, không dựa chỉ vào email:

~~~text
trusted_issuer                                subject        internal_user_id
https://id.example.com/realms/company        user-4a7f      1207
https://login.partner.example.net            user-4a7f      9815
~~~

Hai dòng có `sub` giống nhau nhưng issuer khác nhau **không tự biểu thị cùng một người dùng**. Nếu cần liên kết tài khoản giữa providers, phải có quy trình xác minh quyền sở hữu và chính sách account linking riêng.

### 7.4. Có cần gọi UserInfo ở mọi request HTTP không?

Không. UserInfo thường phục vụ **xây dựng principal** trong giai đoạn đăng nhập hoặc đồng bộ claim khi ứng dụng chủ động thiết kế. Sau khi login thành công, `OidcUser` có thể được truy xuất từ SecurityContext/session.

Gọi lại UserInfo trên mọi request:

- Tăng latency và phụ thuộc mạng/OP.
- Tăng số lần truyền Access Token.
- Có thể gặp rate limit, throttling hoặc token hết hạn.
- Không phải bảo đảm dữ liệu luôn mới nếu provider cache claim.

Nếu yêu cầu dữ liệu hồ sơ được làm mới, nên xác định rõ chiến lược refresh, lifecycle và quyền thay vì ngầm gọi UserInfo ở mỗi controller.

## 8. Spring Security Servlet xử lý UserInfo bằng thành phần nào?

### 8.1. Các lớp liên quan

| Thành phần | Vai trò |
| --- | --- |
| `ClientRegistration` | Mô tả client, grant, scope, provider |
| `ClientRegistration.ProviderDetails.UserInfoEndpoint` | Cấu hình URI, authentication method và user-name attribute |
| `OAuth2AccessTokenResponseClient` | Nhận token từ Token Endpoint |
| `DefaultOAuth2UserService` | Lấy attributes từ UserInfo-like endpoint trong luồng OAuth2 Login |
| `OidcUserService` | Tạo OIDC principal, có thể truy vấn UserInfo và xử lý điều kiện OIDC |
| `OAuth2UserRequest` | Yêu cầu tải OAuth2 user với client registration và Access Token |
| `OidcUserRequest` | OIDC user request có thêm thông tin ID Token |
| `OAuth2User` | Principal của OAuth2 Login |
| `OidcUser` | Principal OIDC có ID Token và có thể có UserInfo |
| `OAuth2AuthorizedClient` | Access Token/Refresh Token đã được cấp cho client/principal |

**Hai service khác nhau:** `DefaultOAuth2UserService` thường phục vụ OAuth2 provider thuần, còn `OidcUserService` chịu trách nhiệm điều phối danh tính OIDC (và có thể sử dụng một OAuth2 user service để gọi UserInfo).

### 8.2. Spring Security không luôn gọi UserInfo

Có UserInfo URI trong metadata **không đồng nghĩa chắc chắn request UserInfo luôn xảy ra**. Các yếu tố ảnh hưởng gồm:

1. Registration có đang dùng **OIDC** (scope `openid`) không.
2. OP có công bố `userinfo_endpoint` không.
3. Authorization grant và Access Token có phù hợp không.
4. Scope/claim nhu cầu và quyết định của `OidcUserService` theo phiên bản.
5. Ứng dụng có custom user service hoặc chính sách không gọi UserInfo không.

Ví dụ khi chỉ yêu cầu `openid`, ứng dụng có thể hoàn tất xác thực danh tính từ ID Token mà **không cần truy vấn UserInfo**. Khi cần claim hồ sơ, kiểm tra scope `profile`/`email` và chính sách user service, nhưng cũng không nên kỳ vọng provider trả mọi claim.

Nếu `user.getUserInfo() == null`, điều đó có thể chỉ nghĩa là UserInfo không được tải hoặc provider không cung cấp; **không tự kết luận ID Token đã xác minh là không hợp lệ**.

## 9. Ví dụ cấu hình Spring Boot và SecurityFilterChain

### 9.1. Dependency Servlet OAuth2 Client

Với Spring Boot 3.x, `build.gradle` có thể bao gồm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Với Spring Boot 4.x, các starter tương ứng có tên `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`. Chọn theo phiên bản Boot thực tế và dependency management/BOM; không tùy ý trộn các phiên bản Spring Security.

### 9.2. SecurityFilterChain cho login OIDC

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> {
                    // Có thể cấu hình userService/oidcUserService tại đây.
                    // Ví dụ mặc định không cần thay các service.
                }))
            .build();
    }
}
~~~

Ví dụ làm rõ DSL `oauth2Login().userInfoEndpoint(...)`. Trong trường hợp tiêu chuẩn, có thể dùng `.oauth2Login(Customizer.withDefaults())` để Spring Security tự quản lý OIDC Login, UserInfo service và xử lý callback.

Việc khai báo `userInfoEndpoint` ở đây **không thay thế** `user-info-uri`/`issuer-uri` thuộc `ClientRegistration`. Một phần cấu hình mô tả endpoint, phần còn lại điều chỉnh service xử lý user.

### 9.3. Đọc dữ liệu OIDC trong controller

~~~java
package com.example.web;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("issuer", user.getIdToken().getIssuer().toString());
        result.put("subject", user.getSubject());
        result.put("displayName", user.getFullName());

        if (user.getUserInfo() != null) {
            result.put("userInfoAvailable", true);
            // Chỉ chọn các claim được phép hiển thị.
        } else {
            result.put("userInfoAvailable", false);
        }

        return result;
    }
}
~~~

Controller này **không tự gọi UserInfo**; nó đọc principal đã được tạo sau OIDC login. Với một hệ thống nhận cả OAuth2 Login thuần và OIDC Login, không phải mọi principal đều là `OidcUser`; khi đó cần xử lý `OAuth2User` tương ứng.

**Không trả `getIdToken().getTokenValue()`, Access Token, Refresh Token hoặc toàn bộ `getClaims()` ra browser**. Những dữ liệu đó có thể chứa thông tin nhạy cảm và không cần cho UI.

## 10. Tùy biến request gửi tới UserInfo khi provider có yêu cầu đặc biệt

Với provider tuân thủ OIDC và chấp nhận Bearer header, Spring Security mặc định thường đã đủ. Chỉ tùy biến khi cần một header được tài liệu provider yêu cầu, thời gian chờ HTTP riêng, hoặc một cấu trúc request đặc biệt.

### 10.1. Tùy biến DefaultOAuth2UserService

`DefaultOAuth2UserService` cho phép tùy chỉnh `RequestEntity` dùng để truy vấn endpoint. Ví dụ dưới đây **vẫn gửi Access Token qua Authorization header**:

~~~java
package com.example.security;

import java.net.URI;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.RequestEntity;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;

public final class UserInfoServices {

    private UserInfoServices() {}

    public static DefaultOAuth2UserService oauth2UserService() {
        DefaultOAuth2UserService service = new DefaultOAuth2UserService();

        service.setRequestEntityConverter(userRequest -> {
            String uri = userRequest.getClientRegistration()
                .getProviderDetails()
                .getUserInfoEndpoint()
                .getUri();

            if (uri == null || uri.isBlank()) {
                throw new IllegalStateException("UserInfo URI chưa cấu hình");
            }

            String accessToken = userRequest.getAccessToken().getTokenValue();

            return RequestEntity.get(URI.create(uri))
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                .accept(MediaType.APPLICATION_JSON)
                .build();
        });

        return service;
    }

    public static OidcUserService oidcUserService() {
        OidcUserService oidcService = new OidcUserService();
        oidcService.setOauth2UserService(oauth2UserService());
        return oidcService;
    }
}
~~~

**Cách hiểu đoạn mã:**

- `OAuth2UserRequest` cung cấp `ClientRegistration` và **Access Token** đã nhận.
- Service lấy **UserInfo URI từ cấu hình provider**, không từ input người dùng.
- `RequestEntity.get(...)` tạo request GET; `Authorization: Bearer` đặt token trong header.
- `OidcUserService` có thể sử dụng `DefaultOAuth2UserService` để tải UserInfo, đồng thời giữ logic OIDC của nó.
- Nếu `user-info-uri` không có, ví dụ chủ động từ chối thay vì tự ghép URL từ issuer.

Ví dụ này là **phương án tùy biến**. Không cần áp dụng chỉ để bật Bearer header mặc định. Nếu provider yêu cầu `form` hoặc `query`, ưu tiên cấu hình `user-info-authentication-method` chính xác khi Spring Security hỗ trợ, thay vì viết custom request builder bỏ qua các điều kiện của giao thức.

### 10.2. Gắn user service tùy biến vào Servlet DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomUserInfoConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(endpoint -> endpoint
                    .userService(UserInfoServices.oauth2UserService())
                    .oidcUserService(UserInfoServices.oidcUserService())))
            .build();
    }
}
~~~

Đây là **một SecurityFilterChain thay thế** cho ví dụ mặc định ở phần trước, không phải chain thứ hai cần chạy song song. Nếu dự án có nhiều `SecurityFilterChain`, phải gắn user service vào chain thực sự xử lý callback OAuth2/OIDC Login.

### 10.3. Cần giữ những bảo đảm nào khi custom?

Khi custom `DefaultOAuth2UserService` hoặc `OidcUserService`:

1. **Không gửi ID Token thay Access Token** trong HTTP request tới UserInfo.
2. Không lấy UserInfo URI từ một query parameter hoặc JWT chưa xác minh; chỉ dùng provider đã cấu hình tin cậy.
3. Không tắt TLS certificate/hostname verification.
4. Với OIDC, bảo toàn kiểm tra **UserInfo `sub` khớp ID Token `sub`**.
5. Không bỏ xác minh ID Token, issuer, audience hoặc nonce chỉ để làm API trả 200.
6. Không ghi `Authorization` header, token hoặc toàn bộ UserInfo response vào log.
7. Dùng timeout/connection pool hợp lý khi lưu lượng cao; tránh treo request đăng nhập vì endpoint chậm.

Nếu provider trả JWT đã ký hoặc mã hóa từ UserInfo thay vì JSON thông thường, đó là một **kiểu response có yêu cầu xác minh riêng** theo OIDC. Không tự parse nó như JSON không xác minh, và không giả định `DefaultOAuth2UserService` mặc định hỗ trợ mọi biến thể response; hãy kiểm tra khả năng thư viện và đăng ký thuật toán của OP/client.

## 11. Truy vấn UserInfo bằng HTTP thủ công: khi nào và làm sao?

Đôi khi ứng dụng cần gọi lại UserInfo **sau khi đã đăng nhập**, ví dụ khi người dùng yêu cầu đồng bộ hồ sơ. Trong trường hợp đó, nên ưu tiên dữ liệu principal đang có và chỉ tạo HTTP request riêng nếu nghiệp vụ thật sự cần claim mới.

Một thao tác thủ công cần:

- Access Token hợp lệ **được cấp cho UserInfo Endpoint**.
- URI đáng tin cậy lấy từ ClientRegistration/metadata.
- Bearer Authorization header nếu provider hỗ trợ.
- Timeout, xử lý lỗi, chính sách bảo mật và giới hạn việc ghi log.
- Đối chiếu claim `sub` với danh tính OIDC đã xác minh trước khi cập nhật hồ sơ.

Ví dụ **minh họa cách xây dựng yêu cầu với RestClient** (không chứa logic đầy đủ để truy xuất authorized client):

~~~java
import java.util.Map;
import org.springframework.web.client.RestClient;

public final class UserInfoHttpClient {

    private final RestClient restClient = RestClient.create();

    public Map<?, ?> fetch(String trustedUserInfoUri, String accessToken) {
        return restClient.get()
            .uri(trustedUserInfoUri)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(Map.class);
    }
}
~~~

Ví dụ chỉ phù hợp khi **hai tham số đều được cấp từ nguồn server-side tin cậy**, không phải input của người dùng. Nó **chưa** xử lý timeout, các mã lỗi, cấu trúc JSON đặc biệt hoặc kiểm tra `sub`; phải bổ sung những phần đó trước khi dùng production. Với ứng dụng có `OidcUserService` mặc định, thông thường **không cần tự viết lớp này**.

Trong ứng dụng thật, có thể lấy Access Token bằng cơ chế `OAuth2AuthorizedClient`/`OAuth2AuthorizedClientManager` tương ứng rồi gọi endpoint theo hợp đồng. Không lấy token từ JavaScript/browser hoặc cố suy ra token từ ID Token.

## 12. Các lỗi HTTP thường gặp từ UserInfo

### 12.1. HTTP 401 — Unauthorized

Ví dụ response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json
~~~

Nguyên nhân có thể:

- Access Token hết hạn, bị thu hồi hoặc không hợp lệ.
- Gửi nhầm **ID Token** trong Authorization header.
- Token không dành cho provider/UserInfo Endpoint đó.
- Token bị cắt hoặc thêm prefix Bearer sai.
- Client đã dùng token của **registration khác**.

Cách xử lý: kiểm tra nguồn token, thời hạn, issuer/provider, phương thức trình bày và token lifecycle. Không giải quyết bằng cách bỏ qua `401` hoặc tự sửa JWT.

### 12.2. HTTP 403 — Forbidden

Provider có thể từ chối do Access Token thiếu scope hoặc policy không cho lấy các claim. Ví dụ Bearer challenge có thể chứa `insufficient_scope`. Không mặc định request `email` khiến UserInfo phải trả đầy đủ email khi người dùng/provider không cấp phép.

Ứng dụng nên xử lý thiếu quyền theo nghiệp vụ và xin scope cần thiết qua một authorization flow hợp lệ khi có lý do; **không dùng Client Secret để bypass consent**.

### 12.3. HTTP 404 hoặc endpoint sai

Nếu `user-info-uri` trỏ nhầm tenant/realm/hostname hoặc một provider không có endpoint đó, client có thể nhận 404. Kiểm tra tài liệu discovery và provider registration; không tự đoán `/userinfo` rồi gắn thêm vào issuer một cách tùy ý.

### 12.4. HTTP 429, timeout, 5xx

Một UserInfo Endpoint có thể rate-limit, mất kết nối hoặc lỗi tạm thời. Nên có **timeout hợp lý**, giám sát và thông điệp login failure thích hợp. Không retry vô hạn với Access Token; việc retry nhiều lần có thể làm tăng tải và kéo dài login.

### 12.5. HTTP 200 nhưng JSON không đúng

HTTP 200 không đủ để xác nhận UserInfo hợp lệ. Các khả năng:

- JSON không có `sub` trong OIDC UserInfo.
- `sub` khác subject trong ID Token.
- Phản hồi là HTML hoặc JSON sai schema.
- Trường định danh của provider OAuth2 thuần không có hoặc sai kiểu.
- Provider trả cấu trúc nested hoặc JWT UserInfo mà client không hỗ trợ.

Trong OIDC, **không nhận claim từ response thiếu/sai `sub`**. Với OAuth2 thuần, cần kiểm tra schema và cấu hình `user-name-attribute` theo provider.

## 13. Những lỗi cấu hình Spring Security thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| UserInfo không được gọi dù đã khai báo URI | User service quyết định không cần; scope/grant/flow không phù hợp | Kiểm tra `openid`, `profile`/`email`, metadata và điều kiện của `OidcUserService` |
| Không thấy `getUserInfo()` sau login | ID Token có thể đủ, không phát sinh request UserInfo | Không giả định UserInfo luôn tồn tại; xem principal và policy gọi endpoint |
| HTTP 401 từ UserInfo | Access Token sai/hết hạn, gửi sai phương thức | Kiểm tra Bearer header, registration, token lifecycle |
| HTTP 403 từ UserInfo | Scope/consent/policy chưa đủ | Xin đúng scope qua luồng cấp quyền; xử lý claim thiếu |
| HTTP 404 | `user-info-uri` sai hoặc provider không có endpoint | Đối chiếu discovery metadata/tài liệu provider |
| `OAuth2AuthenticationException` vì `sub` mismatch | UserInfo response không cùng subject của ID Token | Từ chối claim; điều tra issuer, token và provider |
| Principal không phải `OidcUser` | Registration không yêu cầu `openid` hoặc đang dùng OAuth2 thuần | Xem scope và user service tương ứng |
| Principal OAuth2 thiếu username | `user-name-attribute` không khớp JSON | Dùng trường định danh ổn định đúng hợp đồng |
| Tự gọi UserInfo bằng ID Token | Nhầm mục đích hai token | Dùng Access Token được OP chấp nhận |
| Đăng nhập thất bại khi OP không có UserInfo | Tùy biến đã bắt buộc luôn gọi endpoint | Cho phép flow dựa trên ID Token nếu phù hợp chuẩn và yêu cầu sản phẩm |
| Client đăng nhập chậm | UserInfo endpoint mạng chậm hoặc timeout quá dài | Đo latency, cấu hình timeout, tránh nhiều request không cần |
| Có hai IdP nhưng UserInfo sai người | Dùng Access Token/URI từ registration khác | Ràng buộc authorized client, provider URI và danh tính đúng registration |
| Claim email có nhưng `email_verified=false` | Provider chưa xác minh email | Không dùng email này cho hành vi đòi hỏi verified email |

### 13.1. Cách tìm nguyên nhân khi “UserInfo không có email”

Đừng bắt đầu bằng cách sửa controller để đọc nhiều claim hơn. Hãy xác định:

1. Registration có scope `openid`, `profile`, `email` theo nhu cầu không?
2. UserInfo Endpoint có được OP công bố và client đã dùng đúng URI không?
3. `OidcUserService` có thực hiện request UserInfo với Access Token hợp lệ không?
4. OP có cấp claim email trong ID Token, UserInfo, cả hai hay không cấp?
5. Consent/policy của OP có giới hạn claim không?
6. Email có được đánh dấu `email_verified` không, và ứng dụng cần xử lý điều đó thế nào?

**Định danh người dùng OIDC vẫn là `iss` + `sub`, không phải email**. Thiếu email không đồng nghĩa không thể xây một principal hợp lệ.

### 13.2. Cách hiểu sai thường gặp về `user-name-attribute`

Đối với OAuth2 Login thuần, `user-name-attribute` có thể cần để Spring Security chọn trường định danh từ UserInfo-like API. Đối với OIDC, `sub` của ID Token là nền tảng danh tính; **không nên dùng `user-name-attribute: email` để thay thế xác minh OIDC**.

## 14. Xử lý lỗi và trải nghiệm người dùng

Khi UserInfo thất bại trong quá trình tạo principal, Spring Security có thể coi đăng nhập OAuth2/OIDC là thất bại tùy luồng/cấu hình. `AuthenticationFailureHandler` có thể điều hướng người dùng đến trang public giải thích sự cố mà không làm lộ Access Token hoặc response chi tiết của OP.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class LoginFailureConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/auth/failed", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/auth/failed")))
            .build();
    }
}
~~~

Đây là **cấu hình SecurityFilterChain thay thế** cho các ví dụ trước, không phải đoạn cần khai báo thêm một chain chạy song song. Trang `/auth/failed` phải được ứng dụng cung cấp và cho phép truy cập chưa xác thực để tránh vòng lặp redirect.

Thông điệp UI nên trung tính: “Chưa thể lấy thông tin tài khoản từ nhà cung cấp đăng nhập. Bạn có thể thử lại hoặc liên hệ hỗ trợ.” Không hiển thị nguyên `error_description`, URL có token, JSON UserInfo hoặc stack trace cho người dùng.

Nếu UserInfo chỉ phục vụ tính năng bổ sung chứ không cần thiết cho một phiên đăng nhập, có thể cân nhắc thiết kế không phụ thuộc vào dữ liệu hồ sơ tùy chọn khi dựng principal. Nhưng **không** được chấp nhận dữ liệu UserInfo sai `sub` hay bỏ qua xác minh ID Token để tăng tỷ lệ đăng nhập.

## 15. Các nguyên tắc bảo mật quan trọng

### 15.1. Bảo vệ Access Token trên đường đến UserInfo

- **Dùng HTTPS** và kiểm tra certificate/hostname của provider.
- **Ưu tiên Bearer Authorization header** thay vì query string.
- Không đưa token vào URL browser, JavaScript frontend hoặc HTML.
- Không gửi một token đến endpoint do người dùng nhập; chỉ dùng `user-info-uri` từ cấu hình trusted provider.
- Không dùng Access Token của registration A để gọi UserInfo của provider B.
- Không ghi request headers nhạy cảm vào trace/log; cấu hình masking ở reverse proxy và APM.
- Không cache response UserInfo chứa dữ liệu cá nhân trong cache dùng chung nếu chưa có chính sách rõ ràng.

### 15.2. Bảo vệ claim và dữ liệu cá nhân

- Chỉ xin scope và lưu những claim cần thiết cho sản phẩm.
- Tôn trọng consent, retention policy và quyền truy cập vào dữ liệu hồ sơ.
- Xác minh `sub` và ràng buộc issuer; không tự gộp tài khoản chỉ vì email giống nhau.
- Với email, kiểm tra `email_verified` nếu nghiệp vụ yêu cầu xác minh email.
- Không coi claim như `groups`, `roles` hoặc `tenant` là quyền admin đã được ứng dụng phê duyệt nếu chưa có mapping/policy đáng tin cậy.
- Không trả toàn bộ `OidcUser.getClaims()` ra UI; chỉ chọn field công khai thực sự cần.

### 15.3. Không dùng UserInfo để thay kiểm tra ID Token

UserInfo là nguồn claim bổ sung, không phải bằng chứng duy nhất cho việc xác thực OIDC. Client cần xác minh ID Token theo quy tắc của OIDC (issuer, audience, signature, expiration, nonce nếu dùng...), sau đó mới sử dụng UserInfo với ràng buộc `sub`.

Không lập luận “UserInfo trả HTTP 200 nên ID Token không cần kiểm tra”. HTTP 200 từ một API không tự chứng minh token được cấp cho đúng client và đúng authentication request.

## 16. Bài tập tình huống

### Tình huống A: OIDC Discovery đã cung cấp UserInfo URI

Provider công bố `userinfo_endpoint` trong metadata và registration có `issuer-uri`.

**Cách làm:** không cần copy URL vào YAML; dùng `OidcUserService` mặc định trước. Nếu không có các claim mong muốn, kiểm tra scope/consent và điều kiện tải UserInfo.

### Tình huống B: Provider yêu cầu Bearer header

Token Endpoint trả Access Token hợp lệ và UserInfo API nhận `Authorization: Bearer ...`.

**Cách làm:** cấu hình `user-info-authentication-method: header` nếu muốn tường minh; tránh truyền token bằng query.

### Tình huống C: Provider legacy chỉ nhận form body

UserInfo API dùng POST form-encoded và đọc `access_token` trong body.

**Cách làm:** xác nhận contract và dùng `user-info-authentication-method: form` nếu thư viện/provider hỗ trợ. Không tự chuyển token sang query hoặc gửi đồng thời qua header và form.

### Tình huống D: UserInfo trả 401 nhưng ID Token đã xác minh

Người dùng login OIDC ở Token Endpoint thành công, song UserInfo API trả `invalid_token`.

**Cách làm:** kiểm tra Access Token dùng cho UserInfo có đúng provider/resource/scope, có hết hạn hoặc bị thu hồi không. Không thử gửi ID Token thay Access Token.

### Tình huống E: UserInfo trả `sub` khác ID Token

ID Token có `sub=user-A`, UserInfo trả `sub=user-B`.

**Cách làm:** từ chối UserInfo data và điều tra nhầm token/registration/session hoặc lỗi OP. Không so bằng email.

### Tình huống F: UserInfo không trả email

Response hợp lệ có `sub` và `name` nhưng không có `email`.

**Cách làm:** hiển thị fallback phù hợp, kiểm tra `email` scope và provider policy, không tự điền email giả. Nếu ứng dụng bắt buộc verified email, thiết kế quy trình xác minh riêng.

### Tình huống G: Có nhiều registration dùng chung nhà cung cấp

Ứng dụng có registration `portal` và `reporting` với scope và Access Token khác nhau. Portal muốn lấy profile người dùng.

**Cách làm:** chọn đúng `OAuth2AuthorizedClient` của user/registration và UserInfo URI tương ứng. Không dùng token Client Credentials của reporting để xác nhận user đăng nhập portal.

### Tình huống H: UI muốn hồ sơ luôn mới

Người dùng vừa đổi ảnh tại IdP, còn principal trong session giữ ảnh cũ.

**Cách làm:** thiết kế refresh hồ sơ có kiểm soát bằng token hợp lệ và timeout, so khớp `sub` trước khi lưu; không mặc định UserInfo được gọi lại ở mọi request.

### Tình huống I: Provider trả signed UserInfo JWT

Provider được cấu hình trả UserInfo dạng JWT đã ký thay vì JSON thông thường.

**Cách làm:** kiểm tra thư viện và thuật toán đã được đăng ký/hỗ trợ, xác minh phản hồi theo chuẩn OIDC hoặc dùng tích hợp phù hợp. Không chuyển JWT thành JSON “tin ngay” chỉ vì lấy qua HTTPS.

## 17. Tài liệu tham khảo

- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — ClientRegistration và ProviderDetails: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — `DefaultOAuth2UserService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultOAuth2UserService.html
- Spring Security — `OidcUserService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html
- OpenID Connect Core 1.0 — UserInfo Endpoint: https://openid.net/specs/openid-connect-core-1_0.html#UserInfo
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750

## 18. Tổng kết thực hành

~~~text
OIDC Authorization Code Login
  -> Token Endpoint
       access_token + id_token
  -> Client xác minh ID Token
       issuer, subject, audience, signature, exp, nonce khi áp dụng
  -> Có UserInfo Endpoint và cần profile?
       |
       +-- Có -> Gửi Access Token tới trusted user-info-uri
       |          Ưu tiên Authorization: Bearer <access_token>
       |          Nhận UserInfo response
       |          BẮT BUỘC so khớp UserInfo.sub với ID Token.sub
       |          Chỉ dùng claim đã kiểm tra và cần thiết
       |
       +-- Không -> Dùng claim OIDC đã được xác minh sẵn có
  -> OidcUser và SecurityContext/session
~~~

**UserInfo Endpoint giúp bổ sung hồ sơ người dùng, không thay thế xác thực OIDC.** Trong Spring Security Servlet, ưu tiên **OIDC Discovery qua `issuer-uri`**, sử dụng `OidcUserService` mặc định khi đáp ứng nhu cầu, và gửi Access Token qua **Bearer Authorization header**. Khi cần tùy biến, hãy giữ nguyên các ranh giới: **đúng token, đúng provider, đúng endpoint, đúng subject và đúng chính sách bảo mật dữ liệu**.
