# 5.5. ProviderDetails và cấu hình các endpoint

## 1. ProviderDetails giải quyết vấn đề gì?

Một ứng dụng Spring Boot đóng vai trò **OAuth 2.0 / OpenID Connect (OIDC) Client** phải biết gửi người dùng tới đâu để đăng nhập, gửi authorization code tới đâu để đổi token, lấy khóa công khai ở đâu để xác minh ID Token và có thể truy vấn thông tin người dùng ở đâu. Mỗi nhà cung cấp danh tính (*provider*) có các URL, chính sách và metadata riêng. Đó là lý do `ClientRegistration` của Spring Security tách thông tin **client** khỏi thông tin **provider**.

Ví dụ, một công ty vận hành ứng dụng Spring Boot ở `https://portal.example.com`, trong khi Identity Provider (IdP) có issuer `https://login.example.com/realms/company`. Ứng dụng cần:

- `client-id` và, với confidential client, `client-secret` của **ứng dụng đã đăng ký**;
- `redirect-uri` để provider trả browser về ứng dụng;
- `authorization-uri` để chuyển browser đến nơi đăng nhập và chấp thuận quyền;
- `token-uri` để backend đổi code lấy token hoặc làm mới token;
- `jwk-set-uri` để tải bộ khóa công khai xác minh chữ ký khi cần, đặc biệt ID Token OIDC;
- `user-info-uri` để lấy thêm claim hồ sơ khi provider hỗ trợ;
- `issuer-uri` làm định danh nhà phát hành và là đầu mối khám phá metadata tự động (*discovery*).

Trong Spring Security, các thông số về provider được truy cập qua:

~~~java
ClientRegistration registration = /* lấy theo registrationId */;
ClientRegistration.ProviderDetails details = registration.getProviderDetails();
~~~

**ProviderDetails là phần dữ liệu mô tả OAuth 2.0 Authorization Server / OIDC Provider bên trong ClientRegistration.** Nó không phải một HTTP client, không phải nơi lưu Access Token và cũng không tự đại diện cho một người dùng đã đăng nhập.

## 2. Đặt ProviderDetails đúng vị trí trong mô hình ClientRegistration

`ClientRegistration` đại diện cho một client đã đăng ký với nhà cung cấp OAuth 2.0/OIDC. Các thuộc tính được chia thành hai nhóm:

| Nhóm | Ví dụ thuộc tính | Ý nghĩa |
| --- | --- | --- |
| **Thuộc client** | `registrationId`, `clientId`, `clientSecret`, `clientAuthenticationMethod`, `authorizationGrantType`, `redirectUri`, `scopes`, `clientName` | Ứng dụng nào đang xin quyền, dùng grant nào và provider trả kết quả về đâu |
| **Thuộc provider** | `providerDetails.authorizationUri`, `tokenUri`, `issuerUri`, `jwkSetUri`, `userInfoEndpoint`, `configurationMetadata` | Nhà cung cấp triển khai các endpoint và công bố metadata như thế nào |

Một cách hình dung:

~~~mermaid
flowchart TB
    R["ClientRegistration: corp-login"] --> C["Client config: clientId, secret, grant, redirectUri, scopes"]
    R --> P["ProviderDetails"]
    P --> I["issuerUri"]
    P --> AU["authorizationUri"]
    P --> TO["tokenUri"]
    P --> JW["jwkSetUri"]
    P --> UI["UserInfoEndpoint: uri, authenticationMethod, userNameAttributeName"]
    P --> MD["configurationMetadata"]
    AU --> AS["Authorization Server / OIDC Provider"]
    TO --> AS
    JW --> AS
    UI --> AS
~~~

**Đừng nhầm các định danh:**

| Thuật ngữ | Ví dụ | Ai định nghĩa? |
| --- | --- | --- |
| `registrationId` | `corp-login` | Ứng dụng Spring Boot, dùng để tìm registration |
| `providerId` | `company-oidc` | Khóa cấu hình dưới `spring.security.oauth2.client.provider` |
| `client-id` | `portal-web` | Authorization Server cấp khi đăng ký ứng dụng |
| `issuer-uri` | `https://login.example.com/realms/company` | Định danh issuer mà provider công bố |
| `redirect-uri` | `https://portal.example.com/login/oauth2/code/corp-login` | Endpoint **của client**, được đăng ký với provider |
| `authorization-uri` | `https://login.example.com/realms/company/protocol/openid-connect/auth` | Endpoint **của provider** để browser bắt đầu ủy quyền |

Các URL trên chỉ là minh họa, không phải URL mặc định của mọi sản phẩm. `registrationId`, `providerId`, `client-id` và issuer không nhất thiết giống nhau.

## 3. Những endpoint cốt lõi trong ProviderDetails

### 3.1. Bảng tổng quan

| Trường của ProviderDetails | Property Spring Boot | Vai trò | Ai gọi? |
| --- | --- | --- | --- |
| `authorizationUri` | `authorization-uri` | Authorization endpoint: bắt đầu đăng nhập/consent và phát authorization code thông qua redirect | Browser của người dùng theo điều hướng do client tạo |
| `tokenUri` | `token-uri` | Token endpoint: đổi code lấy token, refresh hoặc dùng grant tương ứng | Backend client qua HTTP request trực tiếp |
| `issuerUri` | `issuer-uri` | Định danh nhà phát hành; dùng discovery và kiểm tra issuer khi áp dụng | Spring Security ở bước cấu hình / xác minh |
| `jwkSetUri` | `jwk-set-uri` | JWKS endpoint: công bố các khóa để xác minh chữ ký JWT | Thành phần xác minh token / JWK client |
| `userInfoEndpoint.uri` | `user-info-uri` | UserInfo endpoint: trả claim người dùng theo OIDC | OIDC client với Access Token phù hợp |
| `userInfoEndpoint.authenticationMethod` | `user-info-authentication-method` | Cách gửi Access Token đến UserInfo | OIDC/OAuth2 user service |
| `userInfoEndpoint.userNameAttributeName` | `user-name-attribute` | Tên trường dùng nhận diện principal từ UserInfo trong các luồng thích hợp | OAuth2 user service |
| `configurationMetadata` | Metadata từ discovery | Các dữ liệu provider công bố, gồm phần không có thuộc tính riêng | Hạ tầng cấu hình và logic mở rộng |

### 3.2. Authorization endpoint: `authorization-uri`

Với Authorization Code grant, Spring Security chuyển browser tới **authorization endpoint** bằng URL có những tham số như:

~~~http
GET /realms/company/protocol/openid-connect/auth
    ?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorp-login
    &scope=openid%20profile%20email
    &state=RANDOM_STATE
    &code_challenge=RANDOM_PKCE_CHALLENGE
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

Đây là request minh họa được xuống dòng để dễ đọc. Giá trị `authorization-uri` là URL **gốc của endpoint**, còn Spring Security xây dựng query string cho giao dịch. Người dùng được xác thực tại provider; sau đó provider redirect trở lại `redirect-uri` đã đăng ký với `code` và `state`.

**Phân biệt:** `authorization-uri` nằm ở provider; `redirect-uri` nằm ở client. Nhầm hai URI này là lỗi cấu hình rất phổ biến.

### 3.3. Token endpoint: `token-uri`

Spring Security gửi yêu cầu qua kênh backend (*back channel*) đến **token endpoint** sau khi nhận code:

~~~http
POST /realms/company/protocol/openid-connect/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_VALUE&redirect_uri=...&code_verifier=...
~~~

Request thực tế còn cần phương thức xác thực client phù hợp: `client_secret_basic`, `client_secret_post`, `private_key_jwt`, `none` cho public client, hoặc phương thức khác provider hỗ trợ. Đoạn request trên chỉ thể hiện form body, không dùng làm hướng dẫn bỏ qua xác thực client.

Một token response OIDC có thể trả:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "SIGNED_ID_TOKEN_JWT",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN"
}
~~~

Token endpoint còn được dùng khi refresh token hoặc Client Credentials grant, nếu provider và registration cho phép. **Không gửi refresh token đến authorization endpoint hay UserInfo endpoint.** Trên hệ thống thật, token endpoint phải dùng HTTPS với kiểm tra chứng chỉ và client authentication chính xác.

### 3.4. JWKS endpoint: `jwk-set-uri`

`jwk-set-uri` chỉ đến một **JSON Web Key Set (JWKS)**, thường chứa các khóa công khai mà provider công bố để xác minh chữ ký JWT do họ phát hành. Ví dụ response rút gọn:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

Với OIDC, Spring Security cần xác minh **ID Token** trước khi coi người dùng đã đăng nhập. Nó có thể chọn khóa theo `kid` của JWT và khóa mà provider công bố, đồng thời kiểm tra issuer, audience, thời gian và các ràng buộc giao dịch khác.

Lưu ý quan trọng:

- `jwks_uri` trong discovery là metadata của provider; `jwk-set-uri` là property ánh xạ tương ứng tại Spring Boot.
- **JWKS URL không phải Token endpoint.** Không gửi `code`, Access Token hay client secret tới URL này.
- Chữ ký hợp lệ là điều kiện cần, **chưa đủ**: phải kiểm tra issuer, audience, expiration và quy tắc của loại token.
- Provider có thể **xoay khóa**. Spring Security/JWT decoder thường có cơ chế tải và cache keys; đừng hard-code một `kid`/khóa cố định khi tích hợp provider quản lý khóa tự động.
- Cấu hình `jwk-set-uri` của **OAuth2 Client** cho xác minh ID Token khác với cấu hình `jwk-set-uri` của **Resource Server** dùng xác minh Access Token đến API của mình.

### 3.5. UserInfo endpoint: `user-info-uri`

OIDC provider có thể công bố endpoint cung cấp thêm thông tin người dùng:

~~~http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO
~~~

Response có thể là:

~~~json
{
  "sub": "opaque-subject-123",
  "name": "Nguyen An",
  "email": "an@example.com",
  "email_verified": true
}
~~~

**UserInfo không phải ID Token.** Đây là endpoint được bảo vệ bằng Access Token; các claim nhận về bổ sung cho danh tính đã xác minh qua ID Token. OIDC client phải **so khớp `sub` trong UserInfo response với `sub` trong ID Token** trước khi sử dụng thông tin. Không mặc định `name`, `email` hoặc `picture` luôn hiện diện, dù client đã xin `profile` hoặc `email`.

`user-info-authentication-method` xác định cách truyền Access Token:

| Giá trị | Cách dùng | Khuyến nghị |
| --- | --- | --- |
| `header` | `Authorization: Bearer ...` | Thường là lựa chọn ưu tiên |
| `form` | Access Token trong form body theo cách endpoint hỗ trợ | Chỉ dùng nếu provider yêu cầu |
| `query` | Access Token trong query string | Tránh khi có lựa chọn an toàn hơn, vì URL dễ xuất hiện trong log và history |

`user-name-attribute` cho biết thuộc tính nào của UserInfo response xác định principal trong luồng OAuth2 Login khi không dùng OIDC, ví dụ `id` hoặc `login`. Với OIDC, `sub` là định danh bắt buộc và phải khớp ID Token; **không thay `sub` bằng email** chỉ để thuận tiện.

### 3.6. Issuer: `issuer-uri` là định danh, không đơn giản là một endpoint

`issuer-uri` chẳng hạn `https://login.example.com/realms/company` là **issuer identifier**. Nó thường được dùng để:

1. Xác định nhà phát hành đáng tin cậy.
2. Tìm URL **discovery metadata**.
3. So khớp với giá trị `iss` của ID Token OIDC đã xác minh.

Issuer có thể chứa **đường dẫn tenant/realm**. Không suy đoán rằng issuer luôn là hostname gốc hay rằng mọi provider đều có đường dẫn `/realms/...`. Khác biệt về hostname, path hoặc dấu `/` ở cuối có thể làm so khớp issuer thất bại.

**Không dùng issuer URI như endpoint nhận token.** `token-uri` và `authorization-uri` có vai trò khác nhau, dù đều thuộc cùng provider.

## 4. Cấu hình OIDC provider bằng Discovery

### 4.1. Discovery là gì?

Thay vì tự khai báo từng URL, nhiều OIDC provider công bố **OpenID Provider Configuration** theo chuẩn discovery. Ví dụ issuer:

~~~text
https://login.example.com/realms/company
~~~

Một metadata URL phổ biến tương ứng:

~~~text
https://login.example.com/realms/company/.well-known/openid-configuration
~~~

Metadata response rút gọn minh họa:

~~~json
{
  "issuer": "https://login.example.com/realms/company",
  "authorization_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "code_challenge_methods_supported": ["S256"]
}
~~~

Đây là ví dụ giả lập để giải thích **tên trường**, không phải metadata đã lấy từ provider đang hoạt động. Một provider thật có thể hỗ trợ nhiều giá trị và thêm các trường khác. Trường metadata như `authorization_endpoint` là tên theo chuẩn OIDC; Spring Boot ánh xạ nó sang `ProviderDetails.authorizationUri`.

### 4.2. Cấu hình `application.yml` tối thiểu

Ví dụ ứng dụng Servlet sử dụng Spring Security OAuth2 Client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-login:
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
            issuer-uri: https://login.example.com/realms/company
~~~

Khi ứng dụng Spring Boot có OAuth2 Client starter và discovery thành công, framework tạo một `ClientRegistration` với thông tin provider được lấy từ metadata. Cấu hình như vậy dễ bảo trì hơn khi provider quản lý tập endpoint của chính họ.

**Không điền client secret trực tiếp vào YAML.** Mã mẫu dùng biến môi trường; môi trường triển khai thực tế có thể dùng secret manager. `redirect-uri` cần khớp URI client đã đăng ký tại authorization server.

### 4.3. Dòng chảy khi khởi tạo ứng dụng

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Boot as OAuth2 Client Auto-Configuration
    participant IdP as OIDC Provider
    App->>Boot: Đọc registration + provider.issuer-uri
    Boot->>IdP: GET discovery metadata URL
    IdP-->>Boot: issuer, authorization_endpoint, token_endpoint, jwks_uri, userinfo_endpoint...
    Boot->>Boot: Tạo ClientRegistration + ProviderDetails
    Boot-->>App: ClientRegistrationRepository sẵn sàng
    Note over App,IdP: Khi browser login, Spring Security sử dụng endpoint đã cấu hình
~~~

Tùy cách khai báo và phiên bản, discovery có thể được thực hiện trong lúc xây dựng application context / client registration. Nếu IdP không khả dụng, chứng chỉ TLS không hợp lệ hoặc issuer không đúng metadata, **ứng dụng có thể thất bại ngay lúc khởi động**. Đây là phụ thuộc vận hành cần cân nhắc cho các môi trường mạng bị cô lập hoặc thời điểm IdP có sự cố.

### 4.4. `ClientRegistrations.fromIssuerLocation()` khi cấu hình bằng Java

Spring Security cũng cung cấp API tạo builder từ metadata:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;

ClientRegistration registration = ClientRegistrations
    .fromIssuerLocation("https://login.example.com/realms/company")
    .registrationId("corp-login")
    .clientId(System.getenv("OIDC_CLIENT_ID"))
    .clientSecret(System.getenv("OIDC_CLIENT_SECRET"))
    .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
    .scope("openid", "profile", "email")
    .build();
~~~

`ClientRegistrations.fromIssuerLocation(...)` khám phá metadata theo các chuẩn OIDC/OAuth Authorization Server được hỗ trợ. `fromOidcIssuerLocation(...)` dành cho trường hợp chỉ muốn dùng OIDC discovery. API builder này hữu ích khi tạo registration bằng code, nhưng với Spring Boot thông thường, **cấu hình `issuer-uri` trong YAML là đủ**.

Không sử dụng issuer lấy trực tiếp từ request chưa tin cậy để tùy ý thực hiện discovery: điều đó có thể tạo rủi ro SSRF hoặc tin nhầm một authorization server. Danh sách issuer tin cậy phải được quản lý bằng cấu hình hoặc quy trình đăng ký provider được kiểm soát.

## 5. Cấu hình tường minh từng endpoint khi không dùng Discovery

Không phải mọi OAuth 2.0 provider đều hỗ trợ OIDC discovery. Một số provider dùng OAuth 2.0 Login thuần, metadata không chuẩn hoặc vận hành trong môi trường chặn truy cập discovery. Khi đó có thể cấu hình từng endpoint rõ ràng.

Ví dụ **OAuth 2.0 Login không phải OIDC** với UserInfo-like API có trường `id`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-login:
            provider: legacy-oauth
            client-id: ${LEGACY_CLIENT_ID}
            client-secret: ${LEGACY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          legacy-oauth:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://auth.example.net/api/user
            user-info-authentication-method: header
            user-name-attribute: id
~~~

Trong ví dụ này:

1. Browser được đưa đến `authorization-uri`.
2. Spring Security gửi code tới `token-uri`.
3. Sau khi có Access Token, OAuth2 user service có thể lấy profile từ `user-info-uri`.
4. `user-name-attribute: id` cho biết trường định danh của response OAuth2 UserInfo-like API.

Vì không có `openid`, **không mặc định có ID Token**; đây là OAuth2 Login thay vì OIDC Login. Thuộc tính `jwk-set-uri` không phải yêu cầu phổ quát cho mọi OAuth2 provider. Nếu client sử dụng OIDC và cần xác minh ID Token ký số, phải cấu hình nguồn khóa và kiểm tra issuer chính xác; dùng discovery là hướng đi nên ưu tiên khi provider hỗ trợ.

### Bảng ánh xạ đầy đủ giữa Spring Boot properties và ProviderDetails

| Spring Boot configuration | Spring Security Java API |
| --- | --- |
| `spring.security.oauth2.client.provider.<providerId>.issuer-uri` | `registration.getProviderDetails().getIssuerUri()` |
| `...authorization-uri` | `getAuthorizationUri()` |
| `...token-uri` | `getTokenUri()` |
| `...jwk-set-uri` | `getJwkSetUri()` |
| `...user-info-uri` | `getUserInfoEndpoint().getUri()` |
| `...user-info-authentication-method` | `getUserInfoEndpoint().getAuthenticationMethod()` |
| `...user-name-attribute` | `getUserInfoEndpoint().getUserNameAttributeName()` |

`<providerId>` trong bảng là chỗ trống đại diện cho khóa nhà cung cấp trong file YAML, chẳng hạn `company-oidc` hoặc `legacy-oauth`. Khi viết YAML thật, **không đặt dấu ngoặc nhọn hay ký tự `<` vào khóa cấu hình**.

### Một lưu ý về `issuer-uri` khi khai báo thủ công

Đặt `issuer-uri` trong Spring Boot thường yêu cầu **khám phá metadata**. Nếu mục tiêu là triển khai **không liên hệ discovery endpoint**, không nên nghĩ rằng chỉ cần khai báo `issuer-uri` rồi “ghi đè” thêm các URL sẽ luôn bỏ qua discovery. Hãy kiểm tra cơ chế tạo registration của phiên bản đang dùng.

Với OIDC Provider tùy biến không hỗ trợ discovery, có thể cần chủ động tạo `ClientRegistration` bằng Java, thiết lập các endpoint, issuer và JWK rõ ràng, đồng thời bảo đảm kiểm tra ID Token phù hợp. Cách làm đó đòi hỏi hiểu sâu yêu cầu bảo mật OIDC; tốt nhất yêu cầu provider công bố metadata hợp chuẩn nếu có thể.

## 6. Tạo ClientRegistration bằng Java và đọc ProviderDetails

### 6.1. Tạo thủ công một registration OAuth2

Đoạn mã minh họa dùng Java và Spring Security Servlet client, không dùng OIDC:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthenticationMethod;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class LegacyOAuthClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration legacy = ClientRegistration
            .withRegistrationId("legacy-login")
            .clientId(System.getenv("LEGACY_CLIENT_ID"))
            .clientSecret(System.getenv("LEGACY_CLIENT_SECRET"))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("profile.read")
            .authorizationUri("https://auth.example.net/oauth/authorize")
            .tokenUri("https://auth.example.net/oauth/token")
            .userInfoUri("https://auth.example.net/api/user")
            .userInfoAuthenticationMethod(AuthenticationMethod.HEADER)
            .userNameAttributeName("id")
            .clientName("Legacy OAuth2")
            .build();

        return new InMemoryClientRegistrationRepository(legacy);
    }
}
~~~

Đây là **phương án thay thế** cho Spring Boot tự tạo `ClientRegistrationRepository` từ `application.yml`. Không tự động khai báo cả hai bean rồi hy vọng Spring Boot gộp registrations; nếu bạn cung cấp bean repository tùy chỉnh, hãy chủ động đưa vào **tất cả** registrations mà ứng dụng cần.

Nên dùng configuration properties cho các URL và secrets trong môi trường thực tế. Ví dụ Java dùng URL minh họa cố định và biến môi trường để tập trung trình bày API builder.

### 6.2. Đọc ProviderDetails từ ClientRegistrationRepository

Đây là ví dụ Java đọc metadata đã được Spring Boot đăng ký:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

public class ProviderInspector {

    private final ClientRegistrationRepository registrations;

    public ProviderInspector(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public void inspect() {
        ClientRegistration registration =
            registrations.findByRegistrationId("corp-login");
        if (registration == null) {
            throw new IllegalStateException("Không có registration: corp-login");
        }

        ClientRegistration.ProviderDetails provider =
            registration.getProviderDetails();

        String issuerUri = provider.getIssuerUri();
        String authorizationUri = provider.getAuthorizationUri();
        String tokenUri = provider.getTokenUri();
        String jwkSetUri = provider.getJwkSetUri();
        String userInfoUri = provider.getUserInfoEndpoint().getUri();

        // Các URI này là metadata cấu hình, không phải Access Token.
        // Chỉ dùng chúng để chẩn đoán trong môi trường được phép.
    }
}
~~~

Các trường có thể **không được cấu hình hoặc không áp dụng cho grant hiện tại**: chẳng hạn Client Credentials không cần authorization endpoint, OAuth2 Login không OIDC có thể không có JWKS, provider không cung cấp UserInfo có thể có URI rỗng. Không viết logic luôn gọi mọi endpoint chỉ vì có `ProviderDetails`.

### 6.3. Metadata bổ sung: `getConfigurationMetadata()`

Nếu registration được tạo bằng discovery, `ProviderDetails` có thể chứa `configurationMetadata` theo dữ liệu provider trả về:

~~~java
ClientRegistration.ProviderDetails details = registration.getProviderDetails();
Map<String, Object> metadata = details.getConfigurationMetadata();

Object responseTypes = metadata.get("response_types_supported");
Object pkceMethods = metadata.get("code_challenge_methods_supported");
Object logoutEndpoint = metadata.get("end_session_endpoint");
~~~

Đoạn ví dụ giả định đã có `registration` và import `java.util.Map`. Những giá trị này tùy provider: chúng có thể vắng mặt hoặc có kiểu dữ liệu khác nhau, nên **không ép kiểu mù quáng**.

Phân biệt metadata mở rộng với các thuộc tính có getter chính thức:

- `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, `jwks_uri` có cách ánh xạ cơ bản vào ProviderDetails.
- `end_session_endpoint`, `revocation_endpoint`, `introspection_endpoint` hoặc metadata PKCE có thể được provider công bố, nhưng **không mặc nhiên có API tự động tương ứng** trong mọi cấu hình Spring Security.
- Một số chức năng như OIDC logout, revocation hoặc introspection phải được cấu hình bổ sung với thành phần phù hợp; không suy ra rằng chúng hoạt động chỉ vì metadata chứa URL.

## 7. Kết nối ProviderDetails với SecurityFilterChain Servlet

Khi đã có ClientRegistration, bạn có thể bật login OIDC trên Servlet stack:

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
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Trong cấu hình mẫu:

| Bước | Thành phần Spring Security | ProviderDetails được sử dụng |
| --- | --- | --- |
| Browser mở URL cần đăng nhập | `SecurityFilterChain`, OAuth2 authorization request resolver | Tìm `ClientRegistration` theo `registrationId` |
| Spring Redirect tới IdP | OAuth2 authorization request redirect filter | `authorizationUri` |
| Browser về `/login/oauth2/code/{registrationId}` | OAuth2 login authentication filter | Client redirect URI, state và code |
| Backend đổi code lấy token | OAuth2 authorization code token response client | `tokenUri` |
| Xác minh OIDC ID Token | OIDC authentication provider/JWT verification | `issuerUri`, `jwkSetUri` và metadata liên quan |
| Tải UserInfo nếu cần | OIDC user service | `userInfoEndpoint.uri` và authentication method |
| Gọi API nghiệp vụ khác | OAuth2 authorized client + HTTP client | Access Token thích hợp; API endpoint **không** nằm trong ProviderDetails |

Những đường dẫn của Spring Security Servlet có thể gồm:

~~~text
/oauth2/authorization/corp-login
    -> authorizationUri của provider company-oidc

/login/oauth2/code/corp-login
    <- browser callback từ provider sau khi đăng nhập
~~~

`corp-login` là registration ID trong ứng dụng. Khi thay callback URI mặc định, ngoài cấu hình `redirect-uri` ở registration, cần cấu hình endpoint xử lý callback của `oauth2Login()` cho khớp và cập nhật whitelist tại provider.

### Sequence diagram: endpoint nào được gọi, ở thời điểm nào?

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Servlet OAuth2 Client
    participant AS as OAuth2/OIDC Provider
    participant API as Downstream Resource Server
    B->>C: GET /oauth2/authorization/corp-login
    C-->>B: 302 Location = authorizationUri + query
    B->>AS: GET authorization endpoint
    AS-->>B: 302 về redirect_uri với code + state
    B->>C: GET /login/oauth2/code/corp-login?code=...
    C->>AS: POST tokenUri, đổi code lấy token
    AS-->>C: ID Token + Access Token
    C->>AS: GET jwkSetUri nếu cần khóa xác minh
    AS-->>C: JWK Set
    Note over C: Xác minh ID Token / issuer / audience / expiry
    opt Provider có UserInfo và ứng dụng cần claim
        C->>AS: GET userInfoUri với Access Token
        AS-->>C: Claims, bao gồm sub
        Note over C: Kiểm tra UserInfo.sub khớp ID Token.sub
    end
    C-->>B: Thiết lập session đăng nhập
    opt Access Token được cấp cho API
        C->>API: Authorization: Bearer Access Token
        API-->>C: Dữ liệu hoặc 401/403
    end
~~~

**Lưu ý:** việc tải JWKS thường được cache hoặc thực hiện khi cần, không phải lúc nào cũng là một request mới ở mỗi lần đăng nhập. Sơ đồ cho thấy quan hệ chức năng, không buộc thứ tự lấy key là cố định.

## 8. Tái sử dụng một provider cho nhiều ClientRegistration

Một provider có thể phục vụ nhiều ứng dụng hoặc nhiều registration dùng chung tập endpoint nhưng khác client ID, scope hay redirect URI.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employee-portal:
            provider: corp-provider
            client-id: ${EMPLOYEE_PORTAL_CLIENT_ID}
            client-secret: ${EMPLOYEE_PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
          reporting-client:
            provider: corp-provider
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - report.read
        provider:
          corp-provider:
            issuer-uri: https://login.example.com/realms/company
~~~

`employee-portal` có user login; `reporting-client` xin token theo Client Credentials. Cả hai tham chiếu `corp-provider` để dùng metadata chung, nhưng **khác client ID, secret, scope và grant**. Với client credentials, ứng dụng cần authorized client manager phù hợp cho tác vụ server; không cần browser redirect hay login session.

**Nhiều tenant/realm khác issuer** nên được xem là các provider khác nhau nếu mỗi realm công bố issuer/endpoint riêng. Không cấu hình một issuer rồi lấy token từ tenant khác; việc đó có thể dẫn đến sai issuer, audience và ranh giới bảo mật.

## 9. CommonOAuth2Provider và mặc định của provider quen thuộc

Spring Security có `CommonOAuth2Provider` chứa một số cấu hình mặc định cho các nhà cung cấp phổ biến. Ví dụ, khi đặt `registrationId` là `google`, Spring Boot có thể dùng các endpoint mặc định của Google mà không yêu cầu khai báo mọi `provider.*-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
~~~

Nếu muốn `registrationId` là `google-login` nhưng vẫn dùng provider mặc định:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google-login:
            provider: google
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
~~~

Các provider có sẵn và endpoint mặc định phụ thuộc phiên bản Spring Security; hãy kiểm tra tài liệu đúng phiên bản dự án. Với IdP của doanh nghiệp, tenant riêng hoặc môi trường private, **`issuer-uri` thường rõ ràng và đáng tin hơn** việc đoán URL authorization/token từ tên nhà cung cấp.

## 10. Các lỗi cấu hình endpoint thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Điều cần kiểm tra |
| --- | --- | --- |
| Không tạo được `ClientRegistration` khi khởi động | Discovery URL sai, IdP không truy cập được, TLS lỗi, metadata không hợp lệ | Giá trị issuer, HTTPS trust, DNS, proxy, metadata JSON, log startup |
| Lỗi issuer mismatch | `issuer-uri` không khớp `issuer` trong metadata hoặc `iss` trong ID Token | So sánh nguyên văn host, path, trailing slash, tenant |
| Login redirect sai trang | `authorization-uri` trỏ nhầm host/tenant/endpoint | Metadata thật của provider và registration đang dùng |
| Provider báo `redirect_uri_mismatch` | Redirect URI của **client** chưa đăng ký hoặc bị tạo sai sau reverse proxy | `redirect-uri`, public base URL, HTTPS, port, context path, trusted proxy |
| Token endpoint trả `invalid_client` | `client-id`, secret hoặc `client-authentication-method` sai | Cấu hình client tại provider và cách gửi client credentials |
| Token endpoint trả `invalid_grant` | Code hết hạn/đã dùng, sai redirect URI, PKCE không khớp | State/session, thời hạn code, PKCE, callback |
| Nhận ID Token nhưng xác minh JWT thất bại | `jwk-set-uri` sai, khóa quay vòng, `kid` không khớp, thuật toán không được chấp nhận | Issuer metadata, JWKS, thuật toán ký, clock skew |
| UserInfo trả `401` | Sai `user-info-uri`, Access Token không hợp lệ hoặc không dành cho endpoint | Endpoint thực, Bearer token, scope/audience, expiry |
| Đăng nhập nhưng principal thiếu tên/email | UserInfo endpoint không có hoặc provider không cấp claim | Scope, metadata UserInfo, claims, user service |
| OAuth2 Login không nhận ra user | `user-name-attribute` không tồn tại trong response của provider không OIDC | JSON trả về và trường định danh đúng, ví dụ `id` |
| `No ClientRegistration found` | Gọi nhầm registration ID hoặc không có registration tương ứng | `registration.*` và `/oauth2/authorization/{registrationId}` |
| Đăng nhập thành công nhưng API bên ngoài trả 403 | Access Token thiếu scope hoặc audience không phù hợp API | Chính sách API, resource indicators, token grant |

### Phân biệt các tình huống hay bị nhầm

**Nhầm 1 — Authorization endpoint và Token endpoint:** browser đi tới authorization endpoint để người dùng xác thực; backend gọi token endpoint để nhận token. Không đưa `client-secret` lên URL browser.

**Nhầm 2 — Issuer và metadata URL:** issuer là định danh nhà phát hành, không luôn trùng URL `/.well-known/openid-configuration`. Discovery là bước tìm metadata từ issuer.

**Nhầm 3 — Redirect URI và ProviderDetails:** redirect URI là đường về phía ứng dụng client; không nằm trong ProviderDetails. Thay `authorization-uri` sẽ không sửa được `redirect_uri_mismatch` nếu đường callback sai.

**Nhầm 4 — JWKS của OAuth2 Client và Resource Server:** đăng nhập OIDC cần xác minh ID Token do IdP cấp, còn một REST API cần xác minh Access Token nhận được. Chúng có thể dùng chung issuer/keys trong hệ thống cụ thể, nhưng hai cấu hình và trách nhiệm tách biệt.

**Nhầm 5 — UserInfo và API nghiệp vụ:** UserInfo endpoint trả claim danh tính, không phải API cho đơn hàng. Một Access Token gọi UserInfo thành công không có nghĩa nó đủ quyền gọi bất kỳ API nào.

**Nhầm 6 — Metadata có URL là tự bật chức năng:** discovery công bố endpoint không có nghĩa Spring Security tự gọi revocation, logout, introspection, token exchange hoặc mọi endpoint mở rộng. Cần cấu hình chức năng tương ứng.

## 11. Lưu ý bảo mật khi cấu hình ProviderDetails

Endpoint OAuth2/OIDC là một phần của ranh giới tin cậy. Cấu hình sai có thể gửi authorization code, token hoặc credential đến server ngoài ý muốn.

1. **Chỉ tin provider đã được cho phép:** quản lý issuer và endpoint bằng cấu hình tin cậy; không nhận URL từ query parameter người dùng rồi đưa thẳng vào discovery hoặc token call.
2. **Dùng HTTPS:** Authorization Server, token, JWKS và UserInfo production cần TLS hợp lệ. Không bỏ qua xác minh chứng chỉ để giải quyết lỗi môi trường.
3. **Phân tách metadata và secret:** ProviderDetails chứa endpoint/public metadata; `client-secret` thuộc registration và phải bảo vệ riêng. Không ghi secrets hoặc token khi debug provider.
4. **So khớp issuer:** metadata và ID Token phải xuất phát từ issuer tin cậy. Cẩn thận với tenant và trường hợp nhiều issuer dùng chung một hostname.
5. **Ràng buộc redirect:** provider phải kiểm tra redirect URI đã đăng ký; Spring Security phải so khớp state và xử lý authorization code/PKCE đúng quy trình.
6. **Kiểm tra JWKS và token:** không tải khóa từ URL tùy ý mà JWT tự chỉ định nếu chưa có chính sách trust; sử dụng cấu hình issuer/JWK tin cậy, xác minh chữ ký, audience, expiry, nonce khi cần.
7. **Không đưa token vào URL:** UserInfo ưu tiên Bearer header; tránh log callback chứa `code` hoặc Authorization header.
8. **Phân định quyền ứng dụng:** client login bằng OIDC không đồng nghĩa được gọi tất cả API. Scope, audience và policy resource server vẫn quyết định.

Đối với các hệ thống multi-tenant, nên định nghĩa rõ quan hệ **tenant → trusted issuer → client registration** và không dùng issuer wildcard. Nếu hỗ trợ dynamic registration, phải có bước xác minh và danh sách tin cậy trước khi dùng endpoint được nhận.

## 12. Cách đọc provider đã cấu hình để chẩn đoán

Trong quá trình vận hành, cần xác nhận ba lớp dữ liệu:

**Lớp cấu hình ứng dụng** — Các giá trị trong `spring.security.oauth2.client.registration.*` và `spring.security.oauth2.client.provider.*` có đúng registration ID, provider ID, client ID, grant, redirect, scope và issuer?

**Lớp metadata provider** — Discovery (nếu dùng) có trả đúng `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri` và `userinfo_endpoint`? Chứng chỉ TLS có hợp lệ, provider có công bố thuật toán và client authentication method phù hợp?

**Lớp runtime** — Khi browser đăng nhập, request có đi đúng authorization endpoint; backend có đổi code ở đúng token endpoint; Spring Security có nhận và xác minh ID Token; UserInfo có được gọi khi cần; API nghiệp vụ có nhận đúng Access Token?

Có thể kiểm tra metadata công khai (không gửi token hay secret) tại môi trường được phép, ví dụ:

~~~bash
curl --fail-with-body --show-error \
  "https://login.example.com/realms/company/.well-known/openid-configuration"
~~~

Một số môi trường curl cũ không hỗ trợ `--fail-with-body`; khi đó dùng `--fail`. Chỉ thực hiện bước kiểm tra nếu URL thực sự thuộc nhà cung cấp được phép; URL bài học là ví dụ.

Khi debug, ưu tiên log tên `registrationId`, issuer đã được tin cậy, HTTP status và correlation ID. Không log authorization code, client secret, ID Token, Access Token, Refresh Token hay toàn bộ query string callback.

## 13. Bài tập ứng dụng theo từng tình huống

### Tình huống A: Provider công bố discovery hợp chuẩn

Ứng dụng Spring Boot đăng nhập nhân viên tại một OIDC provider có `issuer` xác định. Bạn chỉ cần một registration và không muốn copy URL dễ thay đổi.

**Lựa chọn:** khai báo `registration.*` cùng `provider.*.issuer-uri`. Để Spring Security lấy metadata và ánh xạ các endpoint. Kiểm tra redirect URI đã đăng ký và phương thức xác thực client.

### Tình huống B: OAuth2 provider không hỗ trợ discovery

Ứng dụng muốn dùng OAuth2 Login cho một provider cung cấp `authorize`, `token`, API hồ sơ trả `id` nhưng không cấp ID Token.

**Lựa chọn:** khai báo `authorization-uri`, `token-uri`, `user-info-uri`, `user-name-attribute: id`. Không suy luận rằng OAuth2 Login đã trở thành OIDC; nếu không có ID Token, ứng dụng không có các bảo đảm OIDC tương ứng.

### Tình huống C: Access Token dùng Client Credentials, không có browser login

Một backend job chỉ cần xin token để gọi báo cáo.

**Lựa chọn:** `registration.authorization-grant-type: client_credentials`; phần provider tối thiểu cần token endpoint (hoặc metadata phục vụ token endpoint). Không cần `authorization-uri` hay `redirect-uri` trong giao dịch này. Dùng authorized client manager phù hợp cho background job, không dựa vào Servlet login session.

### Tình huống D: Có hai realm của cùng một nhà cung cấp

Tenant A có issuer `https://login.example.com/realms/a`, Tenant B có issuer `https://login.example.com/realms/b`.

**Lựa chọn:** cấu hình riêng hai provider/registration hoặc một cơ chế multi-tenant có danh sách issuer được tin cậy. Không dùng issuer A để kiểm tra ID Token do realm B phát hành; hostname giống nhau không làm hai issuer tương đương.

### Tình huống E: Đã login OIDC, gọi API nhiệm vụ vẫn lỗi

Spring Security đã dùng ProviderDetails đúng và xác thực ID Token thành công, nhưng Task API trả `401` hoặc `403`.

**Cách nghĩ:** ProviderDetails cấu hình các endpoint của **Authorization Server**. Task API là **Resource Server khác**. Kiểm tra Access Token có được cấp cho Task API, audience/scope có đúng và API chấp nhận issuer/format token hay không.

## 14. Tài liệu tham khảo chính thức

- Spring Security — Servlet OAuth2 Client, Core Interfaces and Classes: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — Servlet OAuth2 Login, Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — `ClientRegistration.ProviderDetails` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistration.ProviderDetails.html
- Spring Security — `ClientRegistrations` (issuer discovery) Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistrations.html
- Spring Boot — OAuth2 Client configuration: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html

## 15. Tổng kết kiến thức

`ProviderDetails` là cầu nối giữa **ClientRegistration** và các endpoint của OAuth2/OIDC Provider:

~~~text
ClientRegistration
├── Thông tin client
│   ├── registrationId, clientId, clientSecret
│   ├── authorizationGrantType, scopes
│   └── redirectUri  -> callback về ứng dụng
└── ProviderDetails
    ├── issuerUri    -> danh tính nhà phát hành / đầu mối discovery
    ├── authorizationUri -> browser đi đến để đăng nhập/ủy quyền
    ├── tokenUri         -> backend đổi code hoặc xin/refresh token
    ├── jwkSetUri        -> lấy khóa công khai xác minh JWT/ID Token
    ├── userInfoEndpoint -> lấy claim hồ sơ bằng Access Token hợp lệ
    └── configurationMetadata -> metadata mở rộng từ provider
~~~

Khi provider hỗ trợ OIDC discovery, **`issuer-uri`** giúp tự cấu hình các endpoint và giảm lỗi sao chép URL. Khi không có discovery, dùng các property **`authorization-uri`, `token-uri`, `user-info-uri`, `jwk-set-uri`** theo nhu cầu thực tế và đảm bảo ranh giới tin cậy. Trong Spring Security Servlet Client, phải luôn phân biệt **endpoint của provider**, **redirect URI của ứng dụng**, và **API nghiệp vụ là resource server riêng**.
