# 6.8. Provider OAuth 2.0 thuần và provider hỗ trợ OIDC

## 1. Hai loại provider: giống luồng ủy quyền, khác bảo đảm về danh tính

Ứng dụng **Spring Security OAuth 2.0 OIDC Client** có thể kết nối đến những nhà cung cấp có khả năng rất khác nhau:

- **OAuth 2.0 provider thuần** cung cấp cơ chế xin và cấp quyền truy cập tài nguyên: authorization endpoint, token endpoint, Access Token, scope và có thể có API hồ sơ riêng. OAuth 2.0 **không định nghĩa chuẩn xác thực người dùng** hoặc định dạng ID Token.
- **OIDC provider (OpenID Provider, OP)** hỗ trợ **OpenID Connect**, một lớp xác thực danh tính xây trên OAuth 2.0. Khi client yêu cầu OIDC đúng quy tắc, provider cấp **ID Token** và có thể cung cấp **UserInfo endpoint**, discovery metadata, JWKS để xác minh chữ ký.

Ví dụ: một hệ thống Spring Boot cần cho nhân viên đăng nhập bằng máy chủ định danh doanh nghiệp có OIDC, đồng thời cho phép đăng nhập bằng một dịch vụ bên ngoài chỉ hỗ trợ OAuth 2.0 Login và API trả thông tin tài khoản. Cả hai có thể khởi tạo Authorization Code flow, nhưng cách Spring Security **xác lập danh tính người dùng** sau khi đổi code lấy token khác nhau.

**OIDC provider cũng là OAuth 2.0 authorization server, nhưng OAuth 2.0 provider không mặc nhiên là OIDC provider.** Hơn nữa, một provider có hỗ trợ OIDC vẫn có thể xử lý một giao dịch OAuth 2.0 thuần nếu client không yêu cầu scope `openid` và nhà cung cấp cho phép.

### 1.1. Bảng phân biệt cốt lõi

| Tiêu chí | OAuth 2.0 provider thuần | Provider hỗ trợ OIDC |
| --- | --- | --- |
| Mục tiêu giao thức | Ủy quyền cho client truy cập tài nguyên | Ủy quyền OAuth 2.0 **và** xác thực người dùng theo OIDC |
| Authorization Code flow | Có thể hỗ trợ | Hỗ trợ như một luồng phổ biến |
| Access Token | Có, dùng gọi resource server | Có, dùng gọi resource server hoặc UserInfo |
| ID Token | **Không được OAuth 2.0 quy định** | Được cấp trong OIDC Authorization Code flow hợp lệ |
| Scope `openid` | Không phải scope chuẩn của OAuth 2.0 thuần; provider có thể từ chối | Dấu hiệu kích hoạt yêu cầu OIDC |
| UserInfo | Có thể có API hồ sơ **riêng**, định dạng không thống nhất | Có thể cung cấp **UserInfo endpoint chuẩn OIDC** |
| Định danh tài khoản | Theo API/contract riêng, ví dụ `id`, `login` | Cặp **`iss` + `sub`** đã được xác minh |
| Xác minh danh tính | Phụ thuộc cơ chế riêng của provider và quy ước ứng dụng | Theo ID Token và quy tắc xác minh OIDC |
| Discovery/JWKS | Có thể hỗ trợ OAuth authorization server metadata nhưng không bắt buộc | Thường dùng OIDC discovery/JWKS, nếu provider công bố |
| Spring Security principal | Thường là `OAuth2User` | Thường là `OidcUser`, cũng là một loại `OAuth2User` |
| User service | Thường dùng `DefaultOAuth2UserService` | Thường dùng `OidcUserService` |

Trong bảng, “thường” phản ánh cấu hình mặc định khi dùng `oauth2Login()`. Một hệ thống có thể tùy biến principal, user service hoặc mapping; không nên suy đoán toàn bộ tính năng của provider chỉ dựa vào tên sản phẩm.

## 2. OAuth 2.0 thuần không phải giao thức đăng nhập chuẩn hóa

OAuth 2.0 định nghĩa việc **ủy quyền**: resource owner cho phép client truy cập một tài nguyên được bảo vệ, thường bằng Access Token. Giao thức không định nghĩa một “người dùng đã đăng nhập” chuẩn với các claim như issuer, subject và authentication time.

Ví dụ một provider cho phép:

1. Browser đi đến authorization endpoint để người dùng chấp thuận.
2. Provider redirect về ứng dụng với authorization code.
3. Spring Security đổi code tại token endpoint lấy Access Token.
4. Ứng dụng gọi endpoint hồ sơ riêng với Access Token.
5. Ứng dụng sử dụng trường định danh tài khoản, chẳng hạn `id`, để tạo session login cục bộ.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant C as Spring Boot OAuth2 Client
    participant P as OAuth2 Provider
    U->>C: Truy cập trang cần đăng nhập
    C-->>U: Redirect tới authorization endpoint
    U->>P: Đăng nhập và chấp thuận quyền
    P-->>U: Redirect với code + state
    U->>C: Callback Authorization Code
    C->>P: POST token endpoint, đổi code
    P-->>C: Access Token
    C->>P: GET API hồ sơ riêng + Bearer Access Token
    P-->>C: {"id": 456, "login": "an.nguyen", ...}
    Note over C: Ánh xạ id theo hợp đồng provider
    C-->>U: Tạo Authentication/session cục bộ
~~~

Luồng trên thường được gọi là **OAuth2 Login** trong nhiều framework. Nó cho phép ứng dụng tạo session dựa trên kết quả gọi API hồ sơ của provider, nhưng **bảo đảm danh tính phụ thuộc provider và cách ứng dụng kiểm tra dữ liệu trả về**. OAuth 2.0 thuần không tự mang đến những ràng buộc của ID Token OIDC.

### 2.1. Access Token không phải bằng chứng OIDC

Đừng suy luận “có Access Token thì chắc chắn đã xác thực được một người”:

- Một Access Token có thể đại diện cho **chính client**, ví dụ Client Credentials grant, mà không có người dùng tương tác.
- Token có thể ở dạng **opaque**, không có cấu trúc JWT để ứng dụng đọc.
- Ngay cả khi token là JWT, OAuth 2.0 thuần không yêu cầu nó chứa `iss`/`sub`/`aud` theo ngữ nghĩa ID Token.
- Access Token được thiết kế cho **resource server**, không nhất thiết có audience bằng client ID của ứng dụng web.

Trong OAuth2 Login thuần, client thường dùng Access Token để gọi API hồ sơ tin cậy và lấy định danh theo hợp đồng của provider. Không lấy `email` hoặc `name` làm khóa tài khoản chỉ vì những trường đó dễ hiển thị.

### 2.2. API hồ sơ riêng khác OIDC UserInfo

Một OAuth provider có thể trả:

~~~json
{
  "id": 456,
  "login": "an.nguyen",
  "display_name": "Nguyen An",
  "email": "an@example.com"
}
~~~

Các tên trường `id`, `login`, `display_name` không thuộc một schema hồ sơ OAuth 2.0 bắt buộc. Provider khác có thể trả `user_id`, `account` hoặc nested JSON. Vì vậy Spring Security cần biết **thuộc tính nào định danh principal** qua `user-name-attribute` hoặc custom user service.

Ngược lại, một UserInfo response đúng chuẩn OIDC yêu cầu trường `sub` để ràng buộc với ID Token; không thể coi API hồ sơ bất kỳ có trả email là UserInfo chuẩn OIDC.

## 3. OIDC chuẩn hóa việc xác thực người dùng như thế nào?

OIDC bổ sung **ID Token**, một JWT chứa claim xác thực, cho phép client xác minh sự kiện đăng nhập từ provider đã tin cậy. Trong Authorization Code flow, yêu cầu có scope `openid`; sau khi client đổi code tại token endpoint, phản hồi hợp lệ theo OIDC chứa ID Token bên cạnh Access Token.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant C as Spring Boot OIDC Client
    participant OP as OpenID Provider
    U->>C: Truy cập tài nguyên cần login
    C-->>U: Redirect authorization endpoint với scope openid, state, PKCE
    U->>OP: Đăng nhập/consent nếu cần
    OP-->>U: Redirect code + state
    U->>C: Callback code + state
    C->>OP: POST token endpoint (code, PKCE, client auth nếu cần)
    OP-->>C: Access Token + ID Token (+ Refresh Token nếu được cấp)
    Note over C: Xác minh chữ ký, iss, aud, exp, nonce nếu có
    opt Cần bổ sung claim hồ sơ
        C->>OP: GET UserInfo với Access Token hợp lệ
        OP-->>C: UserInfo {sub, name, email...}
        Note over C: Kiểm tra UserInfo.sub = ID Token.sub
    end
    C-->>U: Session/principal OIDC đã xác thực
~~~

### 3.1. ID Token khác Access Token

Một ID Token đã giải mã để minh họa:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "external-subject-6b19",
  "aud": "spring-portal",
  "exp": 1925003600,
  "iat": 1925000000,
  "auth_time": 1924999950,
  "nonce": "RANDOM_NONCE"
}
~~~

| Claim | Ý nghĩa trong ID Token |
| --- | --- |
| `iss` | Issuer đáng tin cậy đã phát hành ID Token |
| `sub` | Subject identifier của người dùng trong phạm vi issuer |
| `aud` | Audience chứa client ID mà ID Token được phát hành cho |
| `exp` | Hạn dùng của ID Token |
| `iat` | Thời điểm phát hành |
| `auth_time` | Thời điểm xác thực người dùng; cần dùng trong những quy trình yêu cầu xác thực lại |
| `nonce` | Gắn ID Token với yêu cầu xác thực có gửi nonce, chống một số kiểu phát lại |

Client phải **xác minh ID Token**, không chỉ Base64URL-decode. Kiểm tra bao gồm chữ ký/thuật toán, issuer, audience, thời gian và nonce khi áp dụng. Nếu ID Token được mã hóa, cần giải mã theo cấu hình tin cậy rồi thực hiện các bước xác minh phù hợp.

**ID Token phục vụ OIDC client**, còn **Access Token phục vụ resource server**. Không gửi ID Token thay Access Token tới API nghiệp vụ, kể cả khi ID Token là JWT có chữ ký hợp lệ. API phải kiểm tra audience, scope và policy trên token mà API dự kiến chấp nhận.

### 3.2. OIDC UserInfo và kiểm tra `sub`

Khi provider công bố UserInfo endpoint, client có thể gửi Access Token phù hợp để nhận claim:

~~~http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: id.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO
~~~

Phản hồi ví dụ:

~~~json
{
  "sub": "external-subject-6b19",
  "name": "Nguyen An",
  "preferred_username": "an.nguyen",
  "picture": "https://cdn.example.com/avatar/456.png",
  "email": "an@example.com",
  "email_verified": true
}
~~~

OIDC client **phải kiểm tra `sub` trong UserInfo trùng với `sub` của ID Token** trước khi sử dụng claim. Nếu không khớp, bỏ toàn bộ UserInfo response. Trường `name`, `picture` hoặc `email` là dữ liệu tùy chọn; ngay cả khi xin `profile` và `email`, provider không nhất thiết trả đủ.

UserInfo là một **endpoint và dữ liệu hồ sơ**, không phải “token thứ ba” được cấp cùng ID Token/Access Token. Một OIDC provider có thể đưa claim hồ sơ trực tiếp vào ID Token hoặc chỉ cung cấp những claim được phép qua UserInfo, tùy chính sách.

### 3.3. Dùng `iss` + `sub` làm khóa nhận diện

`sub` là định danh subject trong một issuer. Hai provider có thể cùng cấp chuỗi `sub` giống nhau cho hai người khác nhau, và cùng một người có thể nhận subject khác nhau giữa các client hoặc sector tùy cách provider tạo *pairwise subject*.

Một cấu trúc tài khoản nội bộ phù hợp:

~~~text
idp_issuer                                  idp_subject              local_user_id
https://id.example.com/realms/company      external-subject-6b19    1207
https://login.partner.example.net          external-subject-6b19    9981
~~~

Không tự gộp hai dòng vì `sub` giống nhau. Email, số điện thoại hoặc tên hiển thị có thể đổi và không nên là khóa duy nhất cho liên kết tài khoản OIDC.

## 4. Khi nào một provider thực sự đang được sử dụng như OIDC?

**Tên sản phẩm “hỗ trợ OIDC” chưa đủ để khẳng định giao dịch login hiện tại dùng OIDC.** Cần nhìn vào client registration và phản hồi giao thức.

| Dấu hiệu | Ý nghĩa |
| --- | --- |
| Client yêu cầu scope `openid` | Đang yêu cầu xác thực OIDC |
| Provider trả ID Token đúng chuẩn từ token endpoint trong Authorization Code flow | Có kết quả OIDC cần được client xác minh |
| Client xác minh ID Token và tạo `OidcUser` | Spring Security đang xử lý OIDC login |
| Có `issuer-uri` và OIDC discovery metadata hợp lệ | Client có thể tự cấu hình các endpoint/khóa và issuer |
| Provider chỉ trả Access Token, không có ID Token | Không đủ điều kiện gọi kết quả là OIDC login |
| API hồ sơ của provider trả `name`/`email` | **Chưa chứng minh** API là UserInfo chuẩn OIDC |
| Provider trả JWT Access Token | **Chưa chứng minh** giao dịch OIDC; JWT Access Token khác ID Token |

**Một OAuth2 provider không hỗ trợ `openid` thường trả lỗi như `invalid_scope`** khi bị yêu cầu scope này. Nếu provider có OIDC nhưng response thiếu ID Token khi đã thực hiện yêu cầu OIDC hợp lệ, hãy coi đó là lỗi giao thức/cấu hình cần xử lý; không âm thầm bỏ qua ID Token để hạ cấp xác thực.

OIDC Core mô tả Authorization Code, Implicit và Hybrid flow; với ứng dụng hiện đại, **Authorization Code + PKCE** thường là lựa chọn phù hợp. Không chọn Implicit chỉ vì ID Token được phát hành trong front channel. Các ứng dụng Servlet có backend giữ được client secret vẫn nên sử dụng PKCE nếu provider hỗ trợ.

## 5. Spring Security xử lý OAuth2 Login và OIDC Login

Spring Security Servlet dùng chung DSL `oauth2Login()` để kích hoạt cơ chế đăng nhập qua các provider đã đăng ký, nhưng các bước sau khi nhận token khác nhau:

~~~mermaid
flowchart TD
    A["Browser bắt đầu /oauth2/authorization/{registrationId}"] --> B["Authorization Code + state (+ PKCE)"]
    B --> C["Đổi code tại token endpoint"]
    C --> D{"Registration có scope openid?"}
    D -->|Không| E["OAuth2 Login"]
    E --> F["Access Token -> User API của provider"]
    F --> G["DefaultOAuth2UserService / custom user service"]
    G --> H["OAuth2User principal"]
    D -->|Có| I["OIDC Login"]
    I --> J["ID Token validation: iss, aud, signature, exp, nonce..."]
    J --> K["OidcUserService: UserInfo nếu áp dụng"]
    K --> L["OidcUser principal"]
    H --> M["OAuth2AuthenticationToken + session"]
    L --> M
~~~

Tên các thành phần quan trọng:

| API | Trách nhiệm |
| --- | --- |
| `ClientRegistration` | Cấu hình client, grant, scope, redirect và provider endpoints |
| `ClientRegistrationRepository` | Tra cứu registration theo `registrationId` |
| `OAuth2LoginAuthenticationFilter` | Xử lý callback Authorization Code và tạo kết quả login |
| `OAuth2LoginAuthenticationProvider` | Xử lý OAuth2 login không OIDC |
| `OidcAuthorizationCodeAuthenticationProvider` | Xử lý xác thực OIDC Authorization Code và ID Token |
| `DefaultOAuth2UserService` | Gọi UserInfo-like API của provider OAuth2 để tải `OAuth2User` |
| `OidcUserService` | Xây principal OIDC, có thể tải UserInfo nếu phù hợp |
| `OAuth2User` | Hợp đồng principal của OAuth2 Login |
| `OidcUser` | Principal OIDC, có ID Token và có thể có UserInfo; mở rộng `OAuth2User` |
| `OAuth2AuthorizedClient` | Client đã được cấp Access Token, có thể kèm Refresh Token |

Các class provider/user service có thể được cấu hình hoặc thay thế; bảng mô tả đường đi thường gặp trong Spring Security Servlet. **Không cần tự phân nhánh giao thức bằng cách kiểm tra response JWT** nếu dùng `oauth2Login()` với client registration đã cấu hình đúng.

### 5.1. Spring Boot dependency và SecurityFilterChain

Trong một ứng dụng Spring Boot **Servlet** cần Spring MVC và OAuth2 Client starter phù hợp phiên bản Boot. Ví dụ tên starter phổ biến của Boot 3:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Với Spring Boot 4, dùng các tên starter tương ứng `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client` theo BOM của Boot 4. Không trộn các nhánh/version Spring Security thủ công khi đã dùng Boot dependency management.

Một `SecurityFilterChain` cho cả hai registration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
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
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` hỗ trợ chuyển browser tới provider và xử lý callback; `oauth2Client()` hỗ trợ cơ chế lấy và sử dụng authorized client để gọi downstream API. Tùy yêu cầu, có thể tùy biến trang login, user service, success/failure handler hoặc authorized client manager.

## 6. Cấu hình provider OAuth 2.0 thuần trong `application.yml`

Giả sử một provider chỉ cung cấp OAuth2 authorization/token endpoints và API hồ sơ trả thuộc tính `id`. Không có ID Token, issuer OIDC hay UserInfo schema chuẩn.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          external-oauth:
            provider: external-provider
            client-id: ${EXTERNAL_OAUTH_CLIENT_ID}
            client-secret: ${EXTERNAL_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - read_profile
        provider:
          external-provider:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://api.example.net/account
            user-info-authentication-method: header
            user-name-attribute: id
~~~

Giá trị URL, scope, auth method và thuộc tính `id` trong ví dụ **phải thay theo tài liệu của provider thật**. Spring Security không có một `user-info-uri` dùng chung cho mọi OAuth2 provider. Với provider yêu cầu API hồ sơ đặc biệt (header khác, nested JSON, request phụ, mapping riêng), có thể phải tạo custom `OAuth2UserService`.

Trong cấu hình trên:

- `registration.external-oauth` tạo registration ID để kích hoạt bằng `/oauth2/authorization/external-oauth`.
- `provider: external-provider` trỏ tới các URI của provider; không liên quan đến `client-id`.
- `authorization-uri` là nơi browser đến xin code; `token-uri` là nơi backend đổi code.
- `user-info-uri` là API được dùng lấy thông tin người dùng sau khi có Access Token.
- `user-name-attribute: id` nói Spring Security sử dụng trường `id` của JSON response để định danh principal.
- **Không có `openid`**; Spring Security xử lý **OAuth2 Login**, không yêu cầu ID Token.

API hồ sơ ví dụ:

~~~http
GET /account HTTP/1.1
Host: api.example.net
Authorization: Bearer ACCESS_TOKEN_FROM_EXTERNAL_PROVIDER
~~~

~~~json
{
  "id": 456,
  "login": "an.nguyen",
  "display_name": "Nguyen An"
}
~~~

Nếu API hồ sơ yêu cầu `Accept` header đặc biệt, cấu trúc response nested hoặc OAuth 2.0 token không dùng Bearer header tiêu chuẩn, cần xem tài liệu provider và tùy biến user service. Không đặt `openid` trong scope chỉ để ép hệ thống cấp ID Token khi provider không hỗ trợ.

### 6.1. Khi nào dùng `CommonOAuth2Provider`?

Spring Security hỗ trợ một số provider phổ biến bằng `CommonOAuth2Provider` hoặc cấu hình mẫu có sẵn. Khi dùng registration ID trùng provider được hỗ trợ, Spring Boot có thể điền nhiều endpoint mặc định.

Ví dụ OAuth2 Login truyền thống với GitHub OAuth App:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
              - user:email
~~~

Ví dụ này minh họa provider OAuth2 login: **không mặc định có ID Token chỉ vì provider có nhiều sản phẩm liên quan đến OIDC**. Nhà cung cấp có thể triển khai OIDC cho mục đích khác (như workload identity) mà luồng OAuth login dành cho người dùng không cung cấp OIDC ID Token.

Các URI, scope mặc định và tập provider được Spring Security dựng sẵn phụ thuộc phiên bản. Khi provider của tổ chức không có cấu hình mặc định, khai báo endpoint rõ ràng theo contract chính thức.

## 7. Cấu hình provider hỗ trợ OIDC bằng `issuer-uri`

Với OIDC provider có discovery metadata, thường không cần copy từng URL authorization, token, JWKS và UserInfo. Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-oidc:
            provider: company-provider
            client-id: ${COMPANY_OIDC_CLIENT_ID}
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

`issuer-uri` là định danh nhà phát hành. Khi provider công bố discovery metadata theo chuẩn, Spring Security/Spring Boot có thể tìm:

~~~json
{
  "issuer": "https://id.example.com/realms/company",
  "authorization_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://id.example.com/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/userinfo"
}
~~~

Đây là **metadata minh họa**, không phải dữ liệu của một provider đang hoạt động. Metadata thực tế còn có nhiều trường như các response type, signing algorithms và client authentication methods hỗ trợ.

Lợi ích của discovery là giảm cấu hình lặp và giúp Spring Security nắm được đúng issuer/JWKS để kiểm tra ID Token. Một số provider không công bố discovery hoặc cung cấp metadata đặc thù; lúc đó phải cấu hình endpoint tường minh hoặc cung cấp `ClientRegistration` tùy chỉnh, đồng thời đảm bảo các ràng buộc OIDC. **Không tự coi URL bất kỳ là issuer tin cậy**.

### 7.1. Scope của OIDC

| Scope | Ý nghĩa |
| --- | --- |
| `openid` | Bắt buộc để yêu cầu OIDC |
| `profile` | Xin tập claim hồ sơ chuẩn, ví dụ tên hoặc ảnh, theo policy provider |
| `email` | Xin `email` và `email_verified` nếu provider cung cấp |
| `phone` | Xin claim số điện thoại, nếu hỗ trợ |
| `address` | Xin claim địa chỉ, nếu hỗ trợ |
| `offline_access` | Có thể liên quan đến yêu cầu cấp Refresh Token theo chính sách OIDC/provider |
| Scope API riêng như `tasks.read` | Xin quyền gọi API nghiệp vụ, do provider/resource server định nghĩa |

`profile` hoặc `email` không cam kết claim tương ứng chắc chắn hiện diện. `openid` không trao quyền gọi mọi API. `offline_access` cũng không tự bảo đảm có Refresh Token; việc cấp còn phụ thuộc grant, client và chính sách provider.

### 7.2. Endpoint của OIDC provider

| Endpoint | Mục đích | Có thể tìm bằng discovery? |
| --- | --- | --- |
| Authorization endpoint | Browser đăng nhập và chấp thuận quyền | Thường có |
| Token endpoint | Đổi code, refresh, các grant được hỗ trợ | Thường có |
| JWKS endpoint | Lấy khóa công khai để xác minh chữ ký JWT/ID Token | Thường có |
| UserInfo endpoint | Lấy thêm claim người dùng bằng Access Token | Nếu provider cung cấp |
| End-session/logout endpoint | Hỗ trợ đăng xuất liên kết/federated logout theo extension | Nếu provider công bố và hỗ trợ |

Không mặc định mọi endpoint được discovery đều được Spring Security tự sử dụng. Ví dụ, **OIDC RP-Initiated Logout** đòi hỏi cấu hình logout handler thích hợp; UserInfo được gọi theo chính sách user service, không nhất thiết mỗi HTTP request.

## 8. Một ứng dụng hỗ trợ cả OAuth2 và OIDC provider

Spring Boot có thể lưu nhiều registration cùng lúc. Ví dụ một ứng dụng có hai lựa chọn đăng nhập:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-oidc
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          community:
            provider: community-oauth
            client-id: ${COMMUNITY_CLIENT_ID}
            client-secret: ${COMMUNITY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [read_profile]

        provider:
          corp-oidc:
            issuer-uri: https://id.example.com/realms/company
          community-oauth:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://api.example.net/account
            user-info-authentication-method: header
            user-name-attribute: id
~~~

Ở đây:

- `/oauth2/authorization/corp` khởi tạo OIDC login với `openid`.
- `/oauth2/authorization/community` khởi tạo OAuth2 Login thuần.
- Callback mặc định là `/login/oauth2/code/corp` hoặc `/login/oauth2/code/community`.
- Cả hai sử dụng cùng Servlet `SecurityFilterChain` nếu cấu hình không có yêu cầu chia tách đặc biệt.
- Spring Security có thể tạo principal `OidcUser` hoặc `OAuth2User` tương ứng; không nên ép toàn bộ request phải có `OidcUser`.

Một giao diện đăng nhập có thể hiển thị hai lựa chọn rõ ràng, nhưng việc cho phép tài khoản từ provider nào truy cập chức năng nào vẫn cần chính sách riêng của ứng dụng.

### 8.1. Đọc principal mà không ép kiểu sai

Ví dụ controller trả thông tin công khai tối thiểu và phân biệt OIDC với OAuth2:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, Object> currentUser(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken oauthLogin)) {
            throw new IllegalStateException("Endpoint chỉ dành cho OAuth2/OIDC login");
        }

        OAuth2User principal = oauthLogin.getPrincipal();
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("registrationId", oauthLogin.getAuthorizedClientRegistrationId());
        response.put("principalName", principal.getName());

        if (principal instanceof OidcUser oidcUser) {
            response.put("loginProtocol", "OIDC");
            response.put("issuer", oidcUser.getIdToken().getIssuer().toString());
            response.put("subject", oidcUser.getSubject());
        } else {
            response.put("loginProtocol", "OAuth2");
            response.put("providerUserName", principal.getName());
        }
        return response;
    }
}
~~~

Ví dụ dùng Java hỗ trợ pattern matching `instanceof`. Trong ứng dụng thật, `/me` nên yêu cầu authentication thông qua security chain, xử lý lỗi bằng response thích hợp và chỉ trả dữ liệu được phép. Không trả nguyên `principal.getAttributes()`, Access Token, ID Token hoặc Refresh Token cho browser.

`getAuthorizedClientRegistrationId()` giúp nhận biết **registration nào** đã dùng, hữu ích khi ánh xạ tài khoản nội bộ. Với OAuth2 Login thuần, `principal.getName()` lấy trường do `user-name-attribute` hoặc custom user service định nghĩa; không có tính tương đương toàn cầu với OIDC `sub`.

### 8.2. Thiết kế khóa tài khoản nội bộ cho nhiều provider

Một hệ thống cho phép đăng nhập bằng nhiều nhà cung cấp nên lưu danh tính bên ngoài có namespace:

| Loại provider | Khóa bên ngoài nên dùng | Ví dụ |
| --- | --- | --- |
| OIDC | `(issuer, sub)` | `(https://id.example.com/realms/company, external-subject-6b19)` |
| OAuth2 thuần | `(provider/registration namespace, stable provider user ID)` | `(community-oauth, 456)` |

Với OAuth2 thuần, hãy dùng trường ID ổn định **theo tài liệu provider**, không dùng display name. Một registration có thể thay client ID theo môi trường; việc quyết định namespace nên dựa vào chính nguồn định danh và chính sách dữ liệu, không mặc định lấy tên tùy ý không ổn định của UI.

**Không tự động hợp nhất tài khoản chỉ vì hai provider trả cùng email.** Việc link account nên là một quy trình đã xác thực quyền sở hữu và có consent/bảo vệ chống account takeover.

## 9. Khi nào cần tùy biến OAuth2UserService hoặc OidcUserService?

Các provider khác nhau có thể trả claim theo schema riêng hoặc đòi hỏi HTTP request đặc thù. Spring Security cho phép thiết lập user service:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuthLoginServicesConfig {

    @Bean
    SecurityFilterChain loginFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo -> userInfo
                    .userService(new DefaultOAuth2UserService())
                    .oidcUserService(new OidcUserService())))
            .build();
    }
}
~~~

Ví dụ trên chỉ thể hiện điểm mở rộng của DSL; hai service được truyền vào là service mặc định, nên trong ứng dụng không cần tự khai báo nếu không tùy biến. Khi provider yêu cầu logic đặc thù, có thể implement `OAuth2UserService<OAuth2UserRequest, OAuth2User>` cho OAuth2 hoặc `OAuth2UserService<OidcUserRequest, OidcUser>` cho OIDC.

Các trường hợp đáng cân nhắc custom service:

1. Provider OAuth2 trả JSON có nhiều cấp hoặc trường định danh không thể ánh xạ bằng `user-name-attribute`.
2. Provider yêu cầu header đặc biệt, tham số phụ hoặc API hồ sơ bổ sung.
3. Ứng dụng cần ánh xạ claim sang hồ sơ nội bộ, vai trò ứng dụng hoặc chuẩn hóa tên hiển thị.
4. OIDC provider trả claim ở UserInfo và ứng dụng cần xử lý hoặc áp dụng policy riêng trước khi tạo principal.

**Không dùng custom service để bỏ xác minh ID Token, bỏ qua `state`, bỏ kiểm tra `sub` của UserInfo hoặc biến Access Token thành ID Token.** Nếu provider tự nhận OIDC nhưng vi phạm chuẩn cần thiết, tốt nhất sửa cấu hình/tích hợp với nhà cung cấp thay vì vô hiệu hóa cơ chế bảo mật.

## 10. Token và phạm vi quyền khi có nhiều provider

Sau OAuth2 hoặc OIDC Login, Spring Security lưu thông tin OAuth2 authorized client cho registration/principal tương ứng. Một `OAuth2AuthorizedClient` chứa Access Token và có thể có Refresh Token. Khi gọi API, phải dùng token đúng provider và đúng resource server.

~~~text
Login OAuth2 / OIDC
    -> ClientRegistration (registrationId + provider endpoints)
    -> OAuth2AuthorizedClient (Access Token, có thể Refresh Token)
    -> Resource Server mà token được cấp cho
~~~

Một Access Token từ `corp` không mặc nhiên được `community` chấp nhận, và ngược lại. Ngay cả trong cùng issuer, Access Token dùng để gọi UserInfo có thể không có audience/scope của API nghiệp vụ.

| Nhu cầu | Thành phần cần dùng |
| --- | --- |
| Xác thực danh tính từ OIDC provider | ID Token đã được OIDC client xác minh |
| Lấy thêm profile OIDC | UserInfo endpoint bằng Access Token được provider chấp nhận |
| Lấy profile provider OAuth2 thuần | API hồ sơ riêng bằng Access Token theo hợp đồng provider |
| Gọi API nghiệp vụ | Access Token có audience/scope đúng cho API |
| Xin token mới | Refresh Token nếu được cấp và còn hiệu lực, hoặc grant được hỗ trợ |
| Đăng xuất khỏi session ứng dụng | Spring Security logout/session policy |
| Đăng xuất đồng thời khỏi OIDC provider | Cơ chế OIDC logout được provider hỗ trợ và ứng dụng cấu hình riêng |

Khi API trả `401`, điều tra token hết hạn, audience, issuer, chữ ký hoặc phương thức kiểm tra token. Khi trả `403`, kiểm tra scope, role và resource policy. “Đăng nhập OIDC thành công” chỉ có nghĩa client đã xác thực danh tính theo quy trình tương ứng; không bảo đảm Access Token gọi được mọi API.

## 11. Lỗi thường gặp khi phân loại và cấu hình provider

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Provider OAuth2 báo `invalid_scope` khi thêm `openid` | Provider không hỗ trợ OIDC cho luồng/client này | Bỏ yêu cầu OIDC hoặc chọn provider hỗ trợ OIDC thực sự |
| OIDC login fail vì thiếu `id_token` | Giao dịch yêu cầu OIDC nhưng token endpoint không trả ID Token hợp lệ | Kiểm tra `openid`, client registration, token endpoint và hỗ trợ OIDC của provider |
| Spring không tạo được OIDC registration | `issuer-uri`, metadata discovery, TLS hoặc network sai | Đối chiếu issuer và discovery metadata chính thức |
| `invalid_redirect_uri` hoặc `redirect_uri_mismatch` | Callback URI chưa đăng ký hoặc bị thay đổi qua proxy | Khớp scheme/host/port/path; kiểm tra forwarded headers và trusted proxy |
| OAuth2 Login nhận Access Token nhưng không load được profile | Sai `user-info-uri`, thiếu scope hoặc user service không hiểu response | Kiểm tra API hồ sơ provider và `user-name-attribute` |
| OAuth2 Login lỗi `Missing attribute 'id'` hoặc tương tự | JSON không có trường đã chọn làm principal name | Dùng trường ổn định có thật hoặc custom mapping |
| ID Token bị từ chối vì issuer/audience | Sai tenant, client ID hoặc dùng token của registration khác | Kiểm tra `iss`, `aud`, cấu hình issuer và registration |
| UserInfo không có email | Claim tùy chọn, scope/consent/policy không cấp | Xử lý null, chỉ hiển thị dữ liệu được cung cấp |
| UserInfo `sub` khác ID Token `sub` | Token/request trộn giữa người dùng hoặc provider | Từ chối response, kiểm tra nguồn token và session |
| OAuth login có tên email nhưng app tạo trùng tài khoản | Dùng email không ổn định làm khóa | Dùng provider namespace + stable ID, quản lý account linking |
| Principal không phải `OidcUser` như code mong đợi | Luồng OAuth2 thuần hoặc registration không có `openid` | Kiểm tra protocol và xử lý `OAuth2User` tương ứng |
| API khác trả `401/403` dù login thành công | Access Token không dành cho API đó hoặc thiếu scope | Xin token đúng resource/scope, kiểm tra cấu hình resource server |
| Đăng xuất web nhưng IdP vẫn giữ SSO | App logout không phải logout của provider | Thiết kế OIDC logout hoặc phiên SSO theo nhu cầu |

### 11.1. Phân biệt lỗi dependency với lỗi provider

Nếu Java không import được `OAuth2User` hay `OidcUser`, hoặc không có bean OAuth2 Client, đó có thể là thiếu dependency/module hoặc sai phiên bản Spring Security. Nếu chương trình khởi động được, chuyển browser sang IdP nhưng lỗi `invalid_scope`, `invalid_client` hoặc token/claim, hãy kiểm tra **cấu hình provider và giao thức** trước khi thay starter.

### 11.2. Không “sửa” lỗi ID Token bằng cách tắt kiểm tra

Nếu OIDC ID Token bị từ chối vì issuer, audience, signature hoặc expiration, việc bỏ xác minh làm mất nền tảng xác thực của OIDC. Cần sửa issuer URI, client registration, đồng bộ clock, metadata/JWKS hoặc hợp đồng provider. Tương tự, UserInfo có `sub` không khớp thì phải từ chối dữ liệu, không bỏ qua vì email có vẻ giống nhau.

## 12. Tiêu chí chọn provider cho sản phẩm

Trước khi tích hợp một nhà cung cấp, đội phát triển nên xác định chính xác nhu cầu:

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Đăng nhập tập trung doanh nghiệp với claim định danh chuẩn | Ưu tiên OIDC provider hỗ trợ Authorization Code + PKCE |
| Chỉ xin quyền gọi API bên ngoài | OAuth 2.0 thuần có thể đủ, không cần OIDC |
| Đăng nhập bằng provider chỉ có OAuth2 và API tài khoản riêng | Có thể tích hợp `oauth2Login()`; cần mapping danh tính và bảo đảm provider riêng |
| Cần thống nhất nhiều IdP/SSO và quản lý phiên đăng nhập | OIDC thường thuận lợi hơn nhờ `iss`/`sub`, ID Token và metadata chuẩn |
| Service-to-service không có người dùng | OAuth2 Client Credentials; không coi đó là OIDC user login |
| Cần hiển thị hồ sơ | OIDC UserInfo hoặc provider-specific profile API, tùy loại provider |
| Cần gọi API ứng dụng với quyền cụ thể | Access Token có scope/audience phù hợp, bất kể login bằng OAuth2 hay OIDC |

**Một provider “nhiều tính năng” không đồng nghĩa ứng dụng cần bật mọi scope và endpoint.** Chọn flow và scope tối thiểu đáp ứng chức năng, đặc biệt với dữ liệu hồ sơ người dùng.

## 13. Những nguyên tắc bảo mật dùng cho cả hai loại provider

1. **HTTPS ở production:** bảo vệ browser redirect, token endpoint, UserInfo và API profile. Không tắt xác minh chứng chỉ TLS.
2. **Đăng ký chính xác Redirect URI:** authorization server chỉ redirect đến URI được phép; client kiểm tra `state` gắn với giao dịch.
3. **Ưu tiên Authorization Code + PKCE:** kể cả confidential server-side web client khi provider hỗ trợ; không dùng Implicit hay password grant cho đăng nhập mới.
4. **Bảo vệ client credentials:** secret chỉ lưu phía backend/secret manager; public client không nhúng secret vào browser/mobile code.
5. **Chỉ tin provider cấu hình:** không lấy issuer/endpoint tùy ý từ user input để làm discovery hoặc gửi code/token; phòng chống SSRF và nhầm authorization server.
6. **Không log credential:** authorization code, Access Token, ID Token, Refresh Token và client secret không nên xuất hiện trong URL/log/analytics.
7. **Phân quyền tại ứng dụng:** scope của login provider không tự trở thành quyền quản trị; kiểm tra role/ownership/policy trong chính hệ thống.
8. **Xác minh đúng loại token:** ID Token cho OIDC login; Access Token cho API; UserInfo và API hồ sơ chỉ bổ sung claim sau bước xác thực phù hợp.
9. **Không gộp tài khoản bằng email:** dùng khóa định danh ổn định theo provider và cơ chế account linking an toàn.
10. **Quản lý phiên và refresh:** vòng đời HTTP session, Access Token, Refresh Token và SSO session tại provider khác nhau; xử lý hết hạn, revoke và logout rõ ràng.

## 14. Các tình huống luyện tập

### Tình huống A — Đăng nhập bằng OAuth2 provider thuần

Provider trả Access Token, có endpoint `/account` chứa `id=456` và `login=an.nguyen`, không có ID Token.

**Cách tích hợp:** `oauth2Login()` với `authorization-uri`, `token-uri`, `user-info-uri`, `user-name-attribute: id`. Principal là `OAuth2User`. Khi liên kết tài khoản nội bộ, lưu namespace provider cùng ID ổn định `456`, không chỉ lưu email.

### Tình huống B — Đăng nhập bằng OIDC provider

Provider công bố issuer, discovery metadata, JWKS; token endpoint trả Access Token và ID Token khi scope có `openid`.

**Cách tích hợp:** registration có `openid` và provider có `issuer-uri`. Spring Security OIDC login xác minh ID Token; ứng dụng dùng cặp `iss` + `sub` để xác định tài khoản. Nếu cần UserInfo, dùng Access Token hợp lệ và đối chiếu `sub`.

### Tình huống C — Provider công bố JWT Access Token nhưng không có ID Token

**Kết luận:** JWT Access Token không làm provider thành OIDC trong giao dịch này. Không giải mã JWT Access Token để tự tạo OIDC Authentication. Nếu sản phẩm yêu cầu xác thực OIDC chuẩn, cần provider/flow cấp ID Token hợp lệ.

### Tình huống D — Cùng provider nhưng hai registration

Ứng dụng có registration `corp-web` với `openid` cho người dùng, và `corp-service` dùng Client Credentials để gọi API.

**Kết luận:** cả hai dùng chung authorization server nhưng **khác grant và chủ thể**. `corp-web` có thể tạo OIDC principal; `corp-service` xin Access Token dưới danh nghĩa service và không có ID Token đăng nhập người dùng.

### Tình huống E — UserInfo trả subject không khớp

ID Token có `sub=employee-123`; UserInfo trả `sub=employee-999` nhưng email giống nhau.

**Kết luận:** từ chối UserInfo response. Email không thay được ràng buộc subject và không chứng minh hai đối tượng là một.

### Tình huống F — OIDC login thành công nhưng API trả 403

ID Token đã được xác minh; Access Token chỉ có `openid profile` trong khi API yêu cầu `tasks.read`.

**Kết luận:** login thành công chỉ xác nhận danh tính. Cần xin đúng scope/consent, có audience phù hợp và đáp ứng policy của API; không dùng ID Token thay Access Token.

## 15. Tài liệu tham khảo

- **Spring Security — OAuth2 Login (Servlet):** https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- **Spring Security — OAuth2 Client (Servlet):** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- **Spring Security — OAuth2 Login Core Configuration:** https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- **Spring Security — ClientRegistration and ProviderDetails:** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- **OpenID Connect Core 1.0:** https://openid.net/specs/openid-connect-core-1_0.html
- **OpenID Connect Discovery 1.0:** https://openid.net/specs/openid-connect-discovery-1_0.html
- **OAuth 2.0 Authorization Framework (RFC 6749):** https://www.rfc-editor.org/rfc/rfc6749
- **Proof Key for Code Exchange (RFC 7636):** https://www.rfc-editor.org/rfc/rfc7636

## 16. Ghi nhớ

~~~text
OAuth 2.0 provider thuần
  Authorization Code -> Access Token -> provider-specific profile API
  -> OAuth2User (theo hợp đồng định danh riêng của provider)

OIDC provider, với scope openid
  Authorization Code -> Access Token + ID Token
  -> Xác minh ID Token (iss, aud, signature, exp, nonce...)
  -> UserInfo tùy chọn, kiểm tra sub
  -> OidcUser (khóa định danh: issuer + subject)

Cả hai loại:
  Access Token đúng resource/audience/scope -> gọi API
  Quyền nghiệp vụ -> resource server / chính sách ứng dụng
~~~

Trong Spring Security, cùng `oauth2Login()` có thể làm việc với **OAuth2 provider thuần** và **OIDC provider**, nhưng mục đích và độ tin cậy của dữ liệu đăng nhập không giống nhau. **OAuth 2.0 cung cấp cơ chế ủy quyền; OIDC bổ sung chứng cứ xác thực người dùng với ID Token và chuẩn hóa định danh `iss` + `sub`.** Cấu hình đúng loại provider, scope, endpoint và user service là nền tảng để ứng dụng đăng nhập an toàn và dùng token đúng mục đích.
