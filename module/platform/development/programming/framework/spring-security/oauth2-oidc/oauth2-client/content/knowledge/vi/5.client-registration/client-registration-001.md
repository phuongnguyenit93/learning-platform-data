# 5.1. ClientRegistration và thông tin đăng ký của một client

## Mục tiêu bài học

Trong Spring Security OAuth 2.0 Client, **`ClientRegistration` là đối tượng mô tả một client đã đăng ký với Authorization Server hoặc OpenID Provider**. Đối tượng này trả lời các câu hỏi: ứng dụng được nhận diện bằng `client_id` nào, sử dụng grant type gì, phải chuyển hướng người dùng đến đâu, có thể yêu cầu những scope nào và gọi endpoint nào để nhận token.

Sau bài học, bạn có thể:

- Giải thích vai trò của `ClientRegistration` trong OAuth 2.0 Client và OpenID Connect Relying Party (RP).
- Phân biệt thông tin **đăng ký client**, thông tin **nhà cung cấp**, dữ liệu **ủy quyền đã cấp** và danh tính người dùng.
- Nhận biết ý nghĩa các trường quan trọng: `registrationId`, `clientId`, `clientSecret`, `clientAuthenticationMethod`, `authorizationGrantType`, `redirectUri`, `scopes`, `clientName` và `providerDetails`.
- Cấu hình một hoặc nhiều client registration bằng `application.yml` trong Spring Boot.
- Đọc và tạo `ClientRegistration` trong Java, tra cứu qua `ClientRegistrationRepository` và liên hệ nó với quá trình đăng nhập OIDC hoặc gọi API.
- Tránh những nhầm lẫn cấu hình thường gặp về callback, scope, issuer, secret và môi trường triển khai.

## 1. Vì sao ứng dụng cần thông tin đăng ký client?

Giả sử có một web application **Order Portal** viết bằng Spring Boot. Portal muốn:

1. Cho nhân viên đăng nhập thông qua OpenID Provider (OP) của doanh nghiệp.
2. Sau đăng nhập, dùng access token để gọi một API quản lý đơn hàng.
3. Có thể triển khai một tác vụ nền khác chỉ cần token theo `client_credentials` để gọi API báo cáo.

Để Authorization Server biết ứng dụng nào đang yêu cầu quyền, quản trị viên phải **đăng ký client ở phía Authorization Server/OP**. Việc đăng ký thường cung cấp hoặc xác nhận:

- Một `client_id`, và có thể có `client_secret` hoặc phương thức xác thực client khác.
- Các redirect URI được chấp nhận.
- Grant type và loại client được cho phép.
- Các scope mà client được phép yêu cầu.
- Chính sách cấp token, consent, PKCE hoặc các thiết lập riêng của nhà cung cấp.

Ở phía Spring Boot, cần lưu thông tin cấu hình tương ứng để Spring Security biết **cách tham gia giao thức**. Spring biểu diễn phần cấu hình này bằng **`ClientRegistration`**.

> Phân biệt hai việc: **đăng ký client tại OP/Authorization Server** là một thao tác quản trị hoặc quy trình cấp phát phía nhà cung cấp; **khai báo `ClientRegistration` trong Spring** là mô tả cục bộ về client đó để ứng dụng thực hiện các luồng OAuth 2.0/OIDC. Khai báo trong Spring không tự tạo client tại OP.

Ví dụ, nếu nhà cung cấp cấp `client_id=order-portal-web` và chấp nhận callback `https://orders.example.com/login/oauth2/code/corporate`, cấu hình Spring phải phản ánh đúng các giá trị đó.

## 2. `ClientRegistration` là gì?

`ClientRegistration` là kiểu dữ liệu của Spring Security:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistration
~~~

Nó chứa thông tin cần thiết để **một cấu hình OAuth 2.0 Client cụ thể** tương tác với Authorization Server/OP.

Một ứng dụng có thể có:

- **Một registration**: chỉ đăng nhập với hệ thống định danh doanh nghiệp.
- **Nhiều registration cho các provider khác nhau**: chẳng hạn OP doanh nghiệp và một provider bên ngoài.
- **Nhiều registration cùng provider**: ví dụ một client ID dùng đăng nhập nhân viên và một client ID khác dùng để gọi API service.
- **Registration cho grant không có người dùng**: chẳng hạn `client_credentials`.

### 2.1. `ClientRegistration` không phải token hay phiên đăng nhập

Trong hệ thống Spring Security có các kiểu dữ liệu gần nhau nhưng mang trách nhiệm khác nhau:

| Thành phần | Chứa hoặc thực hiện điều gì? | Ví dụ |
|---|---|---|
| **`ClientRegistration`** | Cấu hình client và thông tin provider cần để bắt đầu luồng OAuth 2.0/OIDC | Client ID, grant type, redirect URI, token endpoint |
| **`ClientRegistrationRepository`** | Lưu và tra cứu các registration theo `registrationId` | Tra cứu registration `corporate` |
| **`OAuth2AuthorizedClient`** | Một registration đã được cấp quyền trong ngữ cảnh principal/client; chứa access token và có thể refresh token | Access token được cấp cho nhân viên A |
| **`OAuth2AuthorizedClientService` / `OAuth2AuthorizedClientRepository`** | Lưu và lấy trạng thái authorized client/token | Token của tài khoản A cho registration `corporate` |
| **`OAuth2AuthorizedClientManager`** | Điều phối xin token, dùng lại token hoặc ủy quyền lại theo grant/provider đã cấu hình | Xin access token cho tác vụ nền |
| **`Authentication` / `OidcUser`** | Thông tin principal và kết quả đăng nhập tại ứng dụng | Người dùng A đã đăng nhập OIDC |

Điểm quan trọng: **`ClientRegistration` không chứa access token của người dùng**. Nó cũng không chứng minh một người đã đăng nhập. Token và thông tin principal được tạo ra trong các bước sau, khi luồng authorization hoặc authentication hoàn thành.

### 2.2. Vị trí của `ClientRegistration` trong luồng OIDC

~~~mermaid
flowchart TD
    A["Spring Boot application"] --> B["ClientRegistrationRepository"]
    B --> C["ClientRegistration: corporate"]
    C --> D["Thông tin client: ID, secret, grant, scope, redirect"]
    C --> E["Thông tin provider: issuer, authorize, token, JWK, UserInfo"]
    D --> F["Tạo OIDC Authorization Request"]
    E --> F
    F --> G["OpenID Provider xác thực và xử lý consent"]
    G --> H["Callback + authorization code"]
    H --> I["Trao đổi code lấy token"]
    I --> J["OidcUser / Authentication"]
    I --> K["OAuth2AuthorizedClient"]
    K --> L["Dùng access token gọi Resource Server"]
~~~

Sơ đồ cho thấy registration là **cấu hình đầu vào của luồng**, còn principal và authorized client là **kết quả phụ thuộc quá trình đăng nhập/cấp quyền**.

## 3. Những thuộc tính quan trọng của `ClientRegistration`

### 3.1. Nhóm thông tin định danh client

| Trường / getter | Ý nghĩa | Ví dụ |
|---|---|---|
| `registrationId` / `getRegistrationId()` | Khóa nội bộ duy nhất để Spring tìm registration | `corporate` |
| `clientId` / `getClientId()` | Định danh client do AS/OP cấp | `order-portal-web` |
| `clientSecret` / `getClientSecret()` | Bí mật xác thực client khi phương thức được chọn cần secret | Giá trị từ secret manager |
| `clientName` / `getClientName()` | Tên dễ đọc để hiển thị hoặc phân biệt registration | `Corporate SSO` |
| `clientAuthenticationMethod` | Cơ chế client dùng để xác thực với token endpoint khi cần | `client_secret_basic` |

#### `registrationId` khác `clientId`

Ví dụ:

~~~text
registrationId = corporate
clientId       = order-portal-web
clientName     = Corporate SSO
~~~

Ba giá trị này có vai trò khác nhau:

- `registrationId` là **khóa trong ứng dụng Spring**. Bạn dùng nó khi chọn provider/registration, ví dụ `/oauth2/authorization/corporate`.
- `clientId` là **định danh được nhà cung cấp biết đến**; giá trị này xuất hiện trong giao thức OAuth 2.0/OIDC, ví dụ `client_id=order-portal-web`.
- `clientName` là **nhãn có thể đọc được**; không dùng nó thay `client_id`.

Không nên mặc định `registrationId` phải bằng `clientId`. Hai giá trị có thể khác nhau; đó là cách phổ biến để giữ tên nội bộ ổn định ngay cả khi ID mà nhà cung cấp cấp thay đổi.

Trong cùng một `ClientRegistrationRepository`, mỗi `registrationId` phải nhận diện rõ một registration. Nếu ứng dụng có nhiều OP hoặc nhiều tenant, hãy quy hoạch tên dễ hiểu như `employee-sso`, `partner-sso`, `reporting-service`.

#### `clientSecret` có phải lúc nào cũng cần?

Không. Một số client có thể bảo vệ thông tin xác thực của mình và sử dụng client secret; một số loại client công khai không thể giữ bí mật đáng tin cậy.

- **Confidential web client**: backend Spring Boot có thể lưu secret phía server.
- **Public client**: SPA hoặc ứng dụng di động không thể coi một secret nhúng trong ứng dụng là bí mật an toàn.
- **Các phương thức khác**: nhà cung cấp có thể hỗ trợ xác thực client bằng khóa hoặc cơ chế tương ứng thay cho shared secret.

`client_id` luôn là định danh công khai của client; **`client_id` không phải mật khẩu**. Nếu cấu hình một client có secret, phải quản lý secret như dữ liệu nhạy cảm.

### 3.2. `clientAuthenticationMethod`: xác thực client ở token endpoint

Trường này quy định cách client tự chứng minh danh tính với Authorization Server khi thực hiện giao tiếp yêu cầu client authentication, thường là token request.

Một số phương thức thường gặp:

| Giá trị cấu hình | Ý nghĩa |
|---|---|
| `client_secret_basic` | Gửi client ID và secret theo HTTP Basic authentication tại token endpoint |
| `client_secret_post` | Gửi thông tin client qua body của token request |
| `none` | Không sử dụng client authentication bằng secret, phù hợp với một số public client |
| `private_key_jwt` | Sử dụng JWT assertion được ký bằng khóa riêng của client, khi provider và client được cấu hình phù hợp |

Trong Java, các giá trị chuẩn được biểu diễn bằng `ClientAuthenticationMethod`.

~~~java
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientAuthenticationMethod method =
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC;
~~~

**Chọn phương thức theo đăng ký thực tế tại provider**. Không nên tự đổi từ `client_secret_basic` sang `client_secret_post` để “thử cho chạy” mà không kiểm tra chính sách, và không đưa client secret lên phía trình duyệt để xây dựng token request từ JavaScript.

### 3.3. `authorizationGrantType`: client lấy quyền bằng luồng nào?

Grant type quyết định **quy trình nhận access token**.

| Grant type | Tình huống điển hình | Có người dùng tương tác? |
|---|---|---|
| `authorization_code` | Đăng nhập OIDC hoặc xin quyền thay mặt người dùng bằng authorization code | Thường có, trừ khi OP tái sử dụng phiên SSO |
| `client_credentials` | Backend hoặc tác vụ nền xin token bằng danh tính client | Không cần người dùng cuối |
| `refresh_token` | Sử dụng refresh token đã được cấp để xin token mới | Thường không có tương tác tại thời điểm refresh |

Với Spring Security, `ClientRegistration.authorizationGrantType` mô tả **grant chính của registration**. Việc refresh access token, khi có refresh token, là một bước quản lý authorized client liên quan; không nên hiểu rằng cứ muốn refresh thì phải tạo một registration đăng nhập riêng với `authorization-grant-type: refresh_token`.

Đối với ứng dụng web đăng nhập bằng OIDC, lựa chọn phổ biến là:

~~~yaml
authorization-grant-type: authorization_code
~~~

Đối với tác vụ service-to-service:

~~~yaml
authorization-grant-type: client_credentials
~~~

**`client_credentials` không đồng nghĩa với OIDC Login**: không có người dùng cuối được xác thực bằng ID token trong luồng này. Không thêm `openid` chỉ để biến một service token thành token đăng nhập.

### 3.4. `redirectUri`: nơi OP/AS trả kết quả authorization

Trong Authorization Code, sau khi người dùng xác thực và hoàn tất việc cấp quyền, browser được đưa về redirect URI đã đăng ký.

Cấu hình Spring thường có mẫu:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Giả sử ứng dụng chạy tại `https://orders.example.com` và registration ID là `corporate`, callback tương ứng là:

~~~text
https://orders.example.com/login/oauth2/code/corporate
~~~

Hai placeholder quan trọng:

- `{baseUrl}`: URL gốc mà Spring xác định cho request đang xử lý, có thể phụ thuộc cấu hình proxy.
- `{registrationId}`: registration ID được chọn.

Mẫu URI cần phù hợp với callback được khai báo phía provider. **Chỉ khai báo callback ở Spring chưa đủ**: provider phải chấp nhận URI đó. Sai scheme, host, port, path hoặc cách cấu hình reverse proxy có thể dẫn đến lỗi `redirect_uri_mismatch` hoặc lỗi tương đương.

`redirectUri` chủ yếu có ý nghĩa đối với các luồng có browser redirect như Authorization Code. Với `client_credentials`, ứng dụng giao tiếp trực tiếp với token endpoint nên không có callback của người dùng.

### 3.5. `scopes`: phạm vi quyền client yêu cầu

`ClientRegistration` lưu tập scope được yêu cầu trong luồng OAuth 2.0/OIDC.

Ví dụ dành cho đăng nhập OIDC:

~~~yaml
scope:
  - openid
  - profile
  - email
~~~

Ý nghĩa:

- `openid`: yêu cầu chức năng OpenID Connect; cần có để giao dịch được xử lý như yêu cầu xác thực OIDC.
- `profile`: yêu cầu các claim hồ sơ tương ứng theo chính sách OP.
- `email`: yêu cầu thông tin email tương ứng nếu OP cấp.

Ví dụ dành cho API:

~~~yaml
scope:
  - orders.read
  - orders.write
~~~

Các scope API như `orders.read` phụ thuộc vào Authorization Server và Resource Server của hệ thống. **Client yêu cầu scope không có nghĩa scope chắc chắn được cấp**: provider có thể giới hạn, từ chối hoặc yêu cầu consent; Resource Server vẫn phải kiểm tra quyền truy cập thực tế.

Trong OIDC, ID token xác thực người dùng tại RP; khi gọi API nghiệp vụ, client sử dụng **access token phù hợp với API**, không gửi ID token thay thế.

### 3.6. `providerDetails`: thông tin của Authorization Server / OpenID Provider

`ClientRegistration.ProviderDetails` gom các endpoint và thông tin kỹ thuật của provider mà Spring cần dùng.

| Thuộc tính của provider | Mục đích |
|---|---|
| `issuerUri` | Định danh issuer của OP/AS; quan trọng khi xác minh thông tin định danh và discovery |
| `authorizationUri` | Endpoint chuyển hướng người dùng để bắt đầu Authorization Code |
| `tokenUri` | Endpoint để client trao đổi code hoặc xin token theo grant |
| `jwkSetUri` | Địa chỉ lấy public keys/JWK của provider phục vụ xác minh chữ ký khi phù hợp |
| `userInfoEndpoint.uri` | UserInfo Endpoint trong OIDC, khi có và được dùng |
| `userInfoEndpoint.userNameAttributeName` | Tên thuộc tính nhận diện principal trong trường hợp tương ứng |
| `configurationMetadata` | Metadata provider/discovery mà Spring ghi nhận khi tạo registration từ metadata |

Ví dụ một OP có thể cung cấp:

~~~text
issuer:
https://id.example.com/realms/company

authorization endpoint:
https://id.example.com/realms/company/protocol/openid-connect/auth

token endpoint:
https://id.example.com/realms/company/protocol/openid-connect/token

JWKS endpoint:
https://id.example.com/realms/company/protocol/openid-connect/certs

UserInfo endpoint:
https://id.example.com/realms/company/protocol/openid-connect/userinfo
~~~

*Đây là URL minh họa; endpoint thực tế do provider công bố.*

Các trường trong `providerDetails` **không thuộc về người dùng đang đăng nhập**; chúng mô tả nhà cung cấp chung cho registration.

## 4. Phân biệt registration và provider

Spring Boot có thể khai báo **registration** và **provider** thành hai nhóm cấu hình riêng:

~~~text
spring.security.oauth2.client.registration.<registrationId>
spring.security.oauth2.client.provider.<providerId>
~~~

- **Registration** nói ứng dụng này là client nào: `client-id`, `client-secret`, grant, scope, redirect, tên hiển thị.
- **Provider** nói phải giao tiếp với máy chủ nào: issuer, endpoint ủy quyền, endpoint token, khóa xác minh, UserInfo.

Một provider có thể phục vụ **nhiều registration**. Ví dụ cùng OP phát hành hai client ID: một cho đăng nhập web, một cho service gọi API.

### 4.1. Ba loại tên không nên nhầm

~~~text
registrationId: corporate
providerId:     company-oidc
clientId:       order-portal-web
~~~

| Tên | Ai sử dụng? | Có bắt buộc giống nhau? |
|---|---|---|
| `corporate` | Spring Security tra cứu registration, xây authorization endpoint và callback | Không |
| `company-oidc` | Spring Boot ánh xạ registration tới cấu hình provider | Không |
| `order-portal-web` | Authorization Server/OP nhận diện client | Không |

Một registration đặt `provider: company-oidc` sẽ tham chiếu thông tin trong `spring.security.oauth2.client.provider.company-oidc`. Không có quy tắc bắt buộc registration ID phải bằng provider ID.

### 4.2. Discovery bằng `issuer-uri`

Với OpenID Connect, OP thường cung cấp một tài liệu metadata để RP khám phá các endpoint cần thiết. Cấu hình:

~~~yaml
provider:
  company-oidc:
    issuer-uri: https://id.example.com/realms/company
~~~

cho phép Spring Boot/Spring Security xác định thông tin provider từ cơ chế **discovery** khi nhà cung cấp tương thích.

Những lợi ích chính:

- Giảm việc sao chép nhiều endpoint vào cấu hình.
- Dựa trên issuer đã được chọn để nhận các giá trị endpoint và thông tin khóa công khai do OP công bố.
- Hạn chế lỗi do khai báo sai URL thành phần.

Nhưng cần nhớ:

- `issuer-uri` phải chính xác và trỏ đến issuer đáng tin cậy, không phải URL bất kỳ người dùng có thể cung cấp.
- OP cần công bố metadata ở vị trí và định dạng được thư viện hỗ trợ; ứng dụng cần truy cập được metadata khi khởi tạo cấu hình.
- Nếu provider không có discovery tương thích, phải khai báo các endpoint cần thiết theo cách thủ công.
- Discovery **không thay cho đăng ký client** ở OP: Spring vẫn cần client ID và thông tin xác thực phù hợp.

## 5. Cấu hình `ClientRegistration` trong Spring Boot

### 5.1. Dependency

Với Maven và Spring Boot, thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Starter cung cấp tích hợp Spring Security OAuth 2.0 Client và các thành phần cần thiết theo phiên bản Spring Boot đang dùng.

### 5.2. Ví dụ đầy đủ: registration đăng nhập OIDC

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${CORP_OIDC_CLIENT_ID}
            client-secret: ${CORP_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: Corporate SSO
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Đọc cấu hình theo từng lớp:

1. `corporate` là **registration ID** để Spring tìm cấu hình khi bắt đầu login.
2. `company-oidc` là **provider ID**, nơi khai báo issuer.
3. `client-id` và `client-secret` là thông tin đã được cấp tại OP.
4. `client_secret_basic` quy định cách confidential client xác thực tại token endpoint.
5. `authorization_code` chọn luồng tương tác có callback.
6. `redirect-uri` khai báo callback của Spring Security; phải khớp đăng ký tại OP.
7. `scope` bao gồm `openid`, vì đây là đăng nhập OIDC.
8. `client-name` là nhãn mô tả, không tham gia thay `client_id` trong giao thức.

Trong hệ thống thật, biến môi trường hoặc secret manager cung cấp các giá trị `CORP_OIDC_CLIENT_ID` và `CORP_OIDC_CLIENT_SECRET`. Không commit client secret thật vào repository.

### 5.3. Bật OIDC Login trong Spring Security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(requests -> requests
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated()
                )
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Khi Spring Boot tạo repository từ `application.yml` và ứng dụng cấu hình `oauth2Login()`, luồng tiêu biểu có thể bắt đầu tại:

~~~text
GET /oauth2/authorization/corporate
~~~

Sau khi xác thực tại OP, callback thông thường là:

~~~text
GET /login/oauth2/code/corporate?code=...&state=...
~~~

Spring Security sử dụng registration tương ứng để hoàn tất trao đổi authorization code và xử lý đăng nhập. Với yêu cầu OIDC có `openid` và OP tương thích, Spring xử lý ID token để xây principal OIDC.

Đường dẫn trên là đường dẫn Spring Security mặc định trong cấu hình minh họa. Nếu ứng dụng tùy biến base URI cho authorization hoặc redirection, endpoint và redirect URI phải được điều chỉnh đồng bộ.

### 5.4. Ví dụ khác: backend dùng `client_credentials`

Một service có thể chỉ cần gọi API mà không đưa người dùng đến OP. Khi đó đăng ký client có cấu hình khác:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: internal-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          internal-auth:
            token-uri: https://auth.example.com/oauth2/token
~~~

Ở đây:

- `reporting-service` là một OAuth 2.0 Client registration phục vụ trao đổi **client-to-server**.
- Chỉ cần token endpoint cho grant này trong cấu hình ví dụ.
- Không có `scope=openid` hay ID token xác thực người dùng cuối.
- Không có redirect URI hoặc màn hình login dành cho user.
- Có `ClientRegistration` **chưa làm phát sinh token tự động**; mã ứng dụng cần sử dụng cơ chế authorized client phù hợp để xin và quản lý token.

Nếu ứng dụng có đồng thời `corporate` và `reporting-service`, chúng là hai registration độc lập với grant và chính sách riêng. Không nên sử dụng token theo `client_credentials` để biểu diễn danh tính của một người dùng cụ thể.

## 6. Spring Boot xây `ClientRegistration` như thế nào?

Ở mức tổng quan:

~~~mermaid
flowchart LR
    A["application.yml / properties"] --> B["Spring Boot configuration binding"]
    B --> C["ClientRegistration"]
    C --> D["ClientRegistrationRepository"]
    D --> E["oauth2Login / oauth2Client"]
    E --> F["Authorization request / Token request"]
~~~

Spring Boot đọc nhóm properties `spring.security.oauth2.client.*`, kết hợp thông tin registration và provider, rồi cấu hình các đối tượng client tương ứng khi điều kiện auto-configuration thỏa mãn.

Bạn không bắt buộc phải tự khai báo `@Bean ClientRegistrationRepository` nếu cấu hình properties đã đủ. Ngược lại, nếu tự cung cấp một repository bean, hãy hiểu rằng ứng dụng đang chủ động quản lý tập registration; đừng kỳ vọng cấu hình tự động của Boot lúc nào cũng tạo thêm repository thứ hai.

### 6.1. Tra cứu bằng `ClientRegistrationRepository`

Interface cơ bản:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

ClientRegistration registration =
        clientRegistrationRepository.findByRegistrationId("corporate");
~~~

`findByRegistrationId(...)` trả về registration phù hợp hoặc `null` nếu không tìm thấy, tùy hợp đồng interface.

Ví dụ dùng trong một component để **đọc metadata an toàn**, không in secret:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class ClientRegistrationInspector {

    private final ClientRegistrationRepository registrations;

    public ClientRegistrationInspector(
            ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String describe(String registrationId) {
        ClientRegistration registration =
                registrations.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown registration: " + registrationId);
        }

        return "registrationId=" + registration.getRegistrationId()
                + ", clientId=" + registration.getClientId()
                + ", grantType="
                + registration.getAuthorizationGrantType().getValue()
                + ", scopes=" + registration.getScopes();
    }
}
~~~

Ví dụ chỉ dùng nội bộ để quan sát cấu hình. Ngay cả khi không in secret, việc công khai danh sách client ID và cấu hình bảo mật vẫn có thể không phù hợp. Không biến component này thành endpoint public nếu không có nhu cầu và kiểm soát truy cập.

### 6.2. `InMemoryClientRegistrationRepository`

Spring Security cung cấp một repository đơn giản lưu các registration trong bộ nhớ:

~~~java
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
~~~

Nó phù hợp khi danh sách registration là cấu hình tương đối ổn định được xác định tại thời điểm ứng dụng khởi chạy. Nếu ứng dụng có nhiều tenant, liên tục thêm/bớt client hoặc quản lý metadata động, có thể cần một implementation `ClientRegistrationRepository` riêng và mô hình quản lý secret/cấu hình phù hợp.

**Repository không phải nơi lưu access token**. Việc sử dụng `InMemoryClientRegistrationRepository` không đồng nghĩa với lưu token trong memory; đó là trách nhiệm của các thành phần authorized client khác.

## 7. Tạo `ClientRegistration` trực tiếp bằng Java

Bên cạnh `application.yml`, Spring Security có builder để tạo `ClientRegistration` trong code. Cách này hữu ích khi cấu hình được cung cấp từ một hệ thống khác hoặc cần khởi tạo thủ công.

### 7.1. Dùng discovery từ issuer

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class ManualClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${CORP_OIDC_CLIENT_ID}") String clientId,
            @Value("${CORP_OIDC_CLIENT_SECRET}") String clientSecret) {

        ClientRegistration corporate = ClientRegistrations
                .fromIssuerLocation(
                        "https://id.example.com/realms/company")
                .registrationId("corporate")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .clientName("Corporate SSO")
                .build();

        return new InMemoryClientRegistrationRepository(corporate);
    }
}
~~~

Đoạn code minh họa:

- `ClientRegistrations.fromIssuerLocation(...)` tra cứu metadata từ issuer tương thích để khởi tạo builder với thông tin provider.
- `registrationId("corporate")` đặt khóa dùng trong Spring.
- `clientId(...)`, `clientSecret(...)` và `clientAuthenticationMethod(...)` thiết lập danh tính và phương thức xác thực client.
- `authorizationGrantType(...)`, `redirectUri(...)` và `scope(...)` mô tả luồng login.
- `InMemoryClientRegistrationRepository` cung cấp registration cho các thành phần Spring Security cần tra cứu.

Điều kiện: issuer phải thật sự hỗ trợ discovery mà thư viện sử dụng và ứng dụng phải truy cập được endpoint metadata ở môi trường triển khai. Nếu provider không hỗ trợ, cần chỉ rõ endpoint theo tài liệu của họ.

**Lưu ý:** ví dụ đăng ký bean này là **một lựa chọn thay cho cấu hình repository qua properties**, không nhất thiết đặt song song với cách auto-configuration trước đó.

### 7.2. Tạo builder từ các endpoint khai báo thủ công

Khi không thể dùng discovery, có thể khai báo metadata tương ứng bằng builder:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration registration = ClientRegistration
        .withRegistrationId("corporate")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile", "email")
        .issuerUri("https://id.example.com/realms/company")
        .authorizationUri(
                "https://id.example.com/realms/company/protocol/openid-connect/auth")
        .tokenUri(
                "https://id.example.com/realms/company/protocol/openid-connect/token")
        .jwkSetUri(
                "https://id.example.com/realms/company/protocol/openid-connect/certs")
        .userInfoUri(
                "https://id.example.com/realms/company/protocol/openid-connect/userinfo")
        .clientName("Corporate SSO")
        .build();
~~~

Ở ví dụ trên, `clientId` và `clientSecret` là các biến đã được cung cấp một cách an toàn; toàn bộ URL chỉ mang tính minh họa.

Phải bảo đảm các URL/issuer được lấy từ cấu hình đáng tin cậy của OP. Đặc biệt, **không xây token endpoint hoặc JWK Set URI từ tham số đầu vào tùy ý của request người dùng**, vì điều đó có thể dẫn đến sử dụng sai máy chủ, làm lộ thông tin xác thực hoặc token.

### 7.3. Khi nào nên dùng properties, khi nào nên dùng Java?

| Cách cấu hình | Phù hợp khi | Điểm cần chú ý |
|---|---|---|
| `application.yml` / biến môi trường | Tập client cố định, dễ triển khai theo môi trường | Quản lý secret và URL theo môi trường |
| Java builder | Cấu hình do code hoặc dịch vụ cấu hình đáng tin cậy cung cấp | Chịu trách nhiệm khởi tạo chính xác tất cả trường cần thiết |
| Custom `ClientRegistrationRepository` | Nhiều tenant/client có lifecycle động | Thiết kế cache, cập nhật, đồng bộ, cô lập tenant và bảo vệ secret |

Không nên đưa lựa chọn xây Java builder thành một cơ chế đăng ký client động ở OP nếu OP không thực sự hỗ trợ protocol hoặc quy trình cấp phát đó.

## 8. Quan hệ giữa `ClientRegistration` và `OAuth2AuthorizedClient`

Đây là một trong những phân biệt quan trọng nhất khi phát triển ứng dụng OAuth 2.0.

Giả sử có registration:

~~~text
registrationId = corporate
clientId       = order-portal-web
scope          = openid profile email orders.read
~~~

Hai người dùng Alice và Bob có thể cùng đăng nhập qua registration `corporate`, nhưng mỗi người có **token và trạng thái authorized client riêng**.

~~~mermaid
flowchart TD
    R["ClientRegistration: corporate"] --> A["OAuth2AuthorizedClient của Alice"]
    R --> B["OAuth2AuthorizedClient của Bob"]
    A --> AT["Access token / refresh token của Alice"]
    B --> BT["Access token / refresh token của Bob"]
~~~

Registration là **bản mô tả chung của client**; authorized client là **trạng thái đã được cấp quyền trong ngữ cảnh principal tương ứng**.

Trong Spring Security, một `OAuth2AuthorizedClient` thường liên kết:

- `ClientRegistration`;
- tên principal được ủy quyền;
- access token hiện có;
- refresh token nếu được cấp.

Một cơ chế lưu trữ và quản lý authorized client có thể dùng registration để thực hiện token request theo grant type được chọn. Việc có registration chưa bảo đảm được cấp token; token còn phụ thuộc giao thức, xác thực client, quyền, consent và phản hồi của Authorization Server.

### 8.1. Ví dụ đọc authorized client sau OIDC Login

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientInfoController {

    @GetMapping("/client-status")
    public String clientStatus(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient authorizedClient) {

        return "registrationId="
                + authorizedClient.getClientRegistration().getRegistrationId()
                + ", accessTokenAvailable="
                + (authorizedClient.getAccessToken() != null);
    }
}
~~~

Ví dụ trả về trạng thái đơn giản **không tiết lộ giá trị token**. Trong ứng dụng thật, token được gắn vào lời gọi đến **đúng Resource Server** qua HTTP client/cơ chế authorized client hỗ trợ, còn API tự kiểm tra token, issuer/audience/scope và quyền truy cập.

### 8.2. Khi một registration có nhiều người dùng

Không được lấy token của Alice rồi dùng cho Bob chỉ vì cả hai cùng có `registrationId=corporate`. Nếu ứng dụng lưu token thủ công, khóa lưu trữ phải phản ánh đúng client registration và principal/ngữ cảnh được cấp quyền.

Tương tự, khi có chức năng **chuyển tài khoản OIDC**, ứng dụng cần bảo đảm trạng thái token cũ không bị tái sử dụng cho tài khoản mới.

## 9. Một ứng dụng có nhiều `ClientRegistration`

Ví dụ Portal hỗ trợ hai hệ thống đăng nhập: **Corporate OP** và **Partner OP**. Mỗi provider cấp client ID khác nhau.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, email]
        provider:
          corporate-oidc:
            issuer-uri: https://id.company.example/realms/staff
          partner-oidc:
            issuer-uri: https://id.partner.example/realms/external
~~~

Ứng dụng có thể chọn một trong hai luồng:

~~~text
GET /oauth2/authorization/corporate
GET /oauth2/authorization/partner
~~~

Sau đăng nhập, hãy lưu ý:

- Hai OP có thể phát hành **`sub` trùng chuỗi nhưng thuộc hai người khác nhau**. Trong OIDC, danh tính thường phải được xác định bằng cặp **`iss` + `sub`**.
- Email có thể giống nhau giữa hai issuer; không tự gộp tài khoản nội bộ chỉ vì email trùng.
- Scope, client authentication method và cơ chế consent có thể khác nhau theo provider.
- Nếu giao diện cho người dùng chọn cách đăng nhập, các lựa chọn phải ánh xạ tới registration đã được hệ thống cho phép, tránh biến user input thành địa chỉ issuer/token endpoint tùy ý.
- Cấu hình `clientSecret` và callback phải đúng cho từng registration.

### 9.1. Một provider, nhiều client ID

Ngược lại, một Authorization Server cũng có thể cấp hai client ID riêng cho cùng ứng dụng theo các luồng:

~~~text
Registration 1: corporate-login
Provider:       internal-op
Grant:          authorization_code
Scope:          openid profile email

Registration 2: reporting-job
Provider:       internal-op
Grant:          client_credentials
Scope:          reports.read
~~~

Hai registration có thể tham chiếu cùng provider, nhưng client ID, secret, grant, scope và lifecycle token khác nhau. Đây là cách phân tách quyền theo chức năng để giảm phạm vi ảnh hưởng của thông tin xác thực.

## 10. Hệ quả của việc cấu hình sai từng trường

| Cấu hình sai | Biểu hiện thường gặp | Điều cần xem xét |
|---|---|---|
| Sai `registrationId` trong URL | Spring không tìm được client registration hoặc không bắt đầu login đúng | Tên sau `/oauth2/authorization/` có khớp không? |
| Sai `clientId` | OP từ chối yêu cầu hoặc token exchange | Client ID có đúng tenant/realm/provider không? |
| Sai hoặc hết hạn `clientSecret` | Token endpoint từ chối xác thực client | Secret, cơ chế rotation và method có đúng không? |
| Sai `clientAuthenticationMethod` | Token endpoint trả lỗi xác thực client | Phương thức có được OP cho phép không? |
| Sai `redirectUri` | OP từ chối redirect URI hoặc callback thất bại | Scheme, domain, port, path, proxy headers và cấu hình tại OP |
| Sai `authorizationGrantType` | Ứng dụng bắt đầu luồng không được hỗ trợ | Grant đã được đăng ký và được OP cho phép chưa? |
| Thiếu `openid` trong luồng muốn OIDC | Không nhận hành vi đăng nhập OIDC/ID token như mong đợi | Registration có yêu cầu scope OIDC không? |
| Sai `issuer-uri` hoặc metadata không truy cập được | Khởi tạo client/discovery hoặc xác minh token lỗi | Issuer, kết nối mạng, certificate và metadata |
| Sai `token-uri` / `authorization-uri` | Redirect hoặc token request thất bại | Có đang dùng đúng endpoint của cùng issuer/tenant không? |
| Scope không được cấp | Consent hoặc yêu cầu API thất bại | OP/client/Resource Server có hỗ trợ scope đó không? |

Bảng chỉ nêu nhóm nguyên nhân để định hướng chẩn đoán. **Mã lỗi chính xác phụ thuộc phiên bản Spring Security, nhà cung cấp và giai đoạn giao thức**.

### 10.1. Trường hợp reverse proxy

Một ứng dụng Spring Boot có thể chạy nội bộ tại:

~~~text
http://localhost:8080
~~~

nhưng bên ngoài được truy cập qua:

~~~text
https://orders.example.com
~~~

Nếu `{baseUrl}` được xác định từ địa chỉ nội bộ thay vì địa chỉ public, redirect URI được xây thành `http://localhost:8080/login/oauth2/code/corporate` và không khớp đăng ký tại OP.

Cần cấu hình reverse proxy và cơ chế nhận các forwarded header một cách đáng tin cậy, hoặc dùng redirect URI xác định rõ theo kiến trúc triển khai. Không chấp nhận các header nguồn gốc không tin cậy làm căn cứ dựng redirect URI.

### 10.2. Trường hợp đổi secret

Khi client secret bị xoay vòng tại OP nhưng ứng dụng vẫn dùng giá trị cũ, registration phía Spring **không tự biết secret mới**. Cần cập nhật secret nguồn, bảo đảm ứng dụng nhận cấu hình mới theo cơ chế triển khai và xác nhận rằng client auth method vẫn đúng.

Không in toàn bộ `ClientRegistration`, toàn bộ environment hoặc token request vào log để tìm lỗi; những dữ liệu này có thể chứa bí mật.

### 10.3. Trường hợp chuyển môi trường

Development, staging và production thường có:

- Client ID/secret riêng.
- Domain redirect URI riêng.
- Issuer/realm/tenant riêng hoặc chính sách khác nhau.
- Scope và thông tin provider khác nhau.

Có thể dùng profile và biến môi trường của Spring Boot để quản lý sự khác biệt. Đừng dùng production client secret trong máy phát triển hoặc trỏ production callback về localhost.

## 11. Quy trình thiết lập một registration trong dự án thực tế

### Bước 1: Xác định đúng vai trò của ứng dụng

Ứng dụng cần:

- **Đăng nhập người dùng bằng OIDC** → thường là Authorization Code với scope `openid`.
- **Gọi API thay mặt người dùng** → chọn grant và scope được AS cho phép, quản lý authorized client sau khi cấp quyền.
- **Gọi API bằng danh tính service** → thường là `client_credentials`, không có login người dùng.

Một ứng dụng có thể hỗ trợ nhiều kịch bản, với các registration riêng nếu cần.

### Bước 2: Đăng ký client tại provider

Thống nhất với quản trị viên:

- Client ID và phương thức xác thực client.
- Redirect URI hợp lệ cho Authorization Code.
- Grant type được bật.
- Scopes cần xin và chính sách consent.
- Issuer hoặc endpoint được sử dụng.
- Yêu cầu PKCE, client authentication và các chính sách bảo mật khác.

### Bước 3: Khai báo `ClientRegistration`

Chọn `registrationId` dễ hiểu. Khai báo `client-id`, `client-secret` (nếu cần), `authorization-grant-type`, `client-authentication-method`, `redirect-uri`, `scope` và thông tin provider qua `issuer-uri` hoặc endpoint thủ công.

### Bước 4: Kết nối vào Spring Security

- Dùng `oauth2Login()` cho đăng nhập web.
- Dùng `oauth2Client()` và/hoặc các thành phần `OAuth2AuthorizedClientManager` cho việc xin/sử dụng token để gọi API.
- Nếu ứng dụng **nhận bearer token để bảo vệ API của chính mình**, đó còn là vai trò **Resource Server**, cần cấu hình khác (ví dụ `oauth2ResourceServer()`). Chỉ có `ClientRegistration` không làm API tự động xác minh bearer token.

### Bước 5: Vận hành và quản lý vòng đời cấu hình

Giữ secret ở nguồn bảo mật; kiểm soát thay đổi issuer, callback và scope giữa các môi trường. Với nhiều registration, bảo đảm chọn đúng client ở từng hành trình và không trộn authorized client/token giữa các principal.

## 12. Các câu hỏi thường gặp

**Câu 1. Có thể đặt `registrationId` thành bất kỳ chuỗi nào không?**

Nó là tên nội bộ do ứng dụng chọn, nhưng cần nhất quán và phân biệt giữa các registration trong repository. Tên phải được sử dụng đúng khi cấu hình URL hoặc tham chiếu registration. Tránh thay đổi tùy tiện vì tên này có thể xuất hiện trong đường dẫn callback và cấu hình ứng dụng.

**Câu 2. Nếu chỉ muốn đăng nhập OIDC, có cần cấu hình `token-uri` không?**

Luồng Authorization Code cần token endpoint để đổi code lấy token. Nếu OP hỗ trợ discovery qua `issuer-uri`, Spring có thể lấy endpoint từ metadata; khi cấu hình thủ công thì phải cung cấp thông tin cần thiết.

**Câu 3. Có client secret thì client chắc chắn là một OIDC Relying Party?**

Không. Có secret chỉ cho biết cơ chế xác thực client có thể sử dụng một bí mật. Một client dùng `client_credentials` có thể chỉ là OAuth 2.0 Client. OIDC Login cần yêu cầu xác thực người dùng theo OIDC, thường có `openid` và xử lý ID token.

**Câu 4. Tạo `ClientRegistration` có tự xin access token không?**

Không. `ClientRegistration` chỉ chứa cấu hình. Khi luồng authorization hoặc cơ chế authorized client manager được kích hoạt, hệ thống mới thực hiện yêu cầu cấp token tương ứng.

**Câu 5. Có thể sử dụng một `ClientRegistration` cho tất cả người dùng không?**

Có. Cùng một registration thường đại diện cho ứng dụng web trước OP, còn token và trạng thái authorized client được quản lý theo từng principal và ngữ cảnh phù hợp. Không chia sẻ access token của một người cho người khác.

**Câu 6. Tại sao `registrationId` là `corporate` nhưng OP chỉ biết `order-portal-web`?**

Vì OP sử dụng `client_id`, còn Spring sử dụng `registrationId` để chọn cấu hình nội bộ. Hai tên có vai trò khác nhau và không cần trùng nhau.

**Câu 7. Scope `openid` có cần cho `client_credentials` không?**

Không phải scope dùng để đăng nhập người dùng trong service-to-service. Với `client_credentials`, hãy yêu cầu scope API mà Authorization Server hỗ trợ; không mong chờ ID token người dùng chỉ vì thêm `openid`.

**Câu 8. Có thể dùng `issuer-uri` từ query parameter của người dùng để thêm provider mới không?**

Không nên. Issuer và endpoint dùng trong xác thực/trao đổi token phải được quản lý từ cấu hình đáng tin cậy. Nếu hệ thống cần hỗ trợ multi-tenant hoặc dynamic provider, phải thiết kế rõ danh sách issuer được chấp nhận, cách kiểm tra metadata và quy tắc cô lập tenant.

## 13. Bài tập áp dụng

Một ứng dụng **Inventory Portal** cần cho người dùng đăng nhập qua một OP doanh nghiệp. Nhà cung cấp cấp các thông tin:

~~~text
Issuer:         https://login.example.com/realms/staff
Client ID:      inventory-web
Client secret:  lấy từ biến môi trường INVENTORY_CLIENT_SECRET
Grant type:     authorization_code
Redirect URI:   https://inventory.example.com/login/oauth2/code/staff
Requested scope: openid profile email
~~~

**Yêu cầu:** thiết kế một registration Spring Boot, dùng `registrationId=staff` và `providerId=staff-oidc`.

Một cấu hình phù hợp:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff:
            provider: staff-oidc
            client-id: inventory-web
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          staff-oidc:
            issuer-uri: https://login.example.com/realms/staff
~~~

Trong cấu hình đó:

1. Spring tìm registration bằng `staff`.
2. Authorization Request dùng `client_id=inventory-web`.
3. Browser được chuyển đến endpoint ủy quyền của OP do discovery cung cấp.
4. OP chuyển hướng về `https://inventory.example.com/login/oauth2/code/staff` sau khi hoàn tất bước tương tác phù hợp.
5. Spring hoàn tất token exchange và đăng nhập OIDC theo cấu hình.
6. Token đã cấp, nếu được lưu, thuộc cơ chế `OAuth2AuthorizedClient` tương ứng với principal và registration.

Nếu sau này có thêm tác vụ nền gọi API không có người dùng cuối, hãy xem xét **registration riêng theo `client_credentials`** với scope đúng chức năng, thay vì tái sử dụng token đăng nhập của một nhân viên.

## Ghi nhớ

**`ClientRegistration` là bản mô tả cấu hình một OAuth 2.0 Client trong Spring Security**. Nó tập hợp định danh client, phương thức xác thực, grant type, redirect URI, scopes, nhãn và metadata của nhà cung cấp. `ClientRegistrationRepository` tra cứu các bản mô tả này bằng `registrationId`; khi một luồng cấp quyền diễn ra, `OAuth2AuthorizedClient` mới đại diện cho trạng thái token đã được cấp.

Khi cấu hình OIDC, hãy luôn phân biệt **`registrationId` trong Spring**, **`clientId` tại OP**, **`issuerUri` của provider**, **danh tính người dùng** và **access token được cấp**. Việc phân biệt đó giúp bạn cấu hình đúng luồng đăng nhập, gọi API đúng quyền và quản lý an toàn các registration trong hệ thống có nhiều client hoặc nhiều provider.
