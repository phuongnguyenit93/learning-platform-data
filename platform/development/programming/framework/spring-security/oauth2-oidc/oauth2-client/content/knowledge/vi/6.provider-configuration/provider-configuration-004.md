# 6.4. Cấu hình issuer-uri và lấy metadata qua discovery

## Mục tiêu bài học

Trong **Spring Security OAuth 2.0 / OpenID Connect Client**, việc cấu hình một OpenID Provider (OP) không chỉ là biết địa chỉ trang đăng nhập. Ứng dụng cần xác định chính xác **issuer** mà nó tin cậy và biết các endpoint để chuyển hướng người dùng, đổi authorization code lấy token, tải khóa công khai và có thể truy vấn thông tin người dùng. **Discovery** giúp lấy các thông tin này từ metadata được provider công bố.

Sau bài học, bạn có thể:

- Giải thích `issuer` là gì, vì sao `issuer-uri` là định danh quan trọng đối với một OIDC Provider.
- Phân biệt **issuer URI**, **discovery endpoint**, **authorization endpoint**, **token endpoint**, **JWK Set URI** và **UserInfo endpoint**.
- Cấu hình `spring.security.oauth2.client.provider.<providerId>.issuer-uri` trong Spring Boot.
- Mô tả quá trình Spring Security phát hiện metadata và xây dựng `ClientRegistration`.
- Hiểu ranh giới giữa **OIDC Discovery** và **OAuth 2.0 Authorization Server Metadata**.
- Chẩn đoán lỗi sai issuer, metadata không truy cập được, cấu hình reverse proxy, endpoint hoặc chứng chỉ TLS.
- Biết khi nào nên khai báo endpoint thủ công, và những điều vẫn phải cấu hình ngay cả khi discovery thành công.

## 1. Vấn đề cần giải quyết: một provider có nhiều endpoint

Giả sử một ứng dụng **Employee Portal** viết bằng Spring Boot cần đăng nhập nhân viên bằng OpenID Connect. Hệ thống định danh nội bộ được triển khai tại:

~~~text
https://login.example.com/realms/company
~~~

Khi đăng nhập OIDC Authorization Code, Portal phải biết:

1. Gửi browser đến **authorization endpoint** nào để người dùng xác thực.
2. Gửi authorization code đến **token endpoint** nào để lấy token.
3. Lấy public keys của OP ở **JWK Set URI** nào để xác minh chữ ký ID token.
4. Có **UserInfo endpoint** hay không để lấy thêm claim hồ sơ.
5. Cần kỳ vọng **issuer** nào trong ID token và metadata.
6. OP hỗ trợ những thuật toán, response type và khả năng giao thức nào.

Một cách làm là cấu hình riêng từng URL. Nhưng nếu URL thay đổi hoặc có nhiều môi trường, việc sao chép dễ khiến ứng dụng lấy authorization endpoint ở môi trường này nhưng token endpoint hoặc issuer ở môi trường khác.

**OIDC Discovery** cho phép RP bắt đầu với một **issuer URI được tin cậy**, rồi tải tài liệu metadata do OP công bố để lấy các endpoint và thông tin cần thiết.

~~~mermaid
flowchart TD
    A["Spring Boot Client / RP"] --> B["issuer-uri đã cấu hình"]
    B --> C["Discovery metadata của OP"]
    C --> D["authorization_endpoint"]
    C --> E["token_endpoint"]
    C --> F["jwks_uri"]
    C --> G["userinfo_endpoint nếu có"]
    C --> H["issuer và khả năng giao thức"]
    D --> I["Khởi tạo OIDC Authorization Code"]
    E --> J["Trao đổi authorization code lấy token"]
    F --> K["Xác minh chữ ký ID token"]
~~~

**Discovery giúp nhận biết provider**, nhưng **không tự đăng ký client với provider**. Ứng dụng vẫn cần `client-id`, phương thức xác thực client và các cấu hình đăng ký thích hợp.

## 2. Issuer là gì?

### 2.1. Issuer là định danh của nhà phát hành

Trong OIDC, `issuer` là định danh URL của OP; ID token có claim `iss` chứa issuer đã phát hành token.

Ví dụ:

~~~text
Issuer:
https://login.example.com/realms/company
~~~

ID token hợp lệ do OP đó phát hành có thể chứa:

~~~json
{
  "iss": "https://login.example.com/realms/company",
  "sub": "employee-8217",
  "aud": "employee-portal",
  "iat": 1760000000,
  "exp": 1760003600
}
~~~

*Payload minh họa, không phải một ID token có chữ ký thực tế.*

Trong một giao dịch OIDC, RP cần kiểm tra `iss` theo issuer đã cấu hình và các kiểm tra token bắt buộc khác như chữ ký, audience, thời hạn, nonce nếu áp dụng. **Chỉ giải mã JWT và đọc `iss` không phải là xác minh token.**

Issuer đóng vai trò **ranh giới tin cậy**: ứng dụng phải biết mình đang chấp nhận kết quả xác thực từ provider nào.

### 2.2. Issuer không phải là URL trang đăng nhập

Một OP có thể công bố:

~~~text
Issuer:
https://login.example.com/realms/company

Authorization endpoint:
https://login.example.com/realms/company/protocol/openid-connect/auth

Token endpoint:
https://login.example.com/realms/company/protocol/openid-connect/token

JWKS endpoint:
https://login.example.com/realms/company/protocol/openid-connect/certs
~~~

Các URL này phục vụ mục đích khác nhau:

| URL | Ý nghĩa |
|---|---|
| **Issuer URI** | Định danh nhà phát hành được tin cậy; đối chiếu với metadata và `iss` của ID token |
| **Discovery URL** | Địa chỉ tải tài liệu metadata |
| **Authorization endpoint** | Nơi browser chuyển đến để bắt đầu ủy quyền/đăng nhập |
| **Token endpoint** | Nơi client trao đổi code hoặc thực hiện token request phù hợp |
| **JWK Set URI** | Nơi công bố các khóa công khai cần cho xác minh chữ ký |
| **UserInfo endpoint** | Nơi cung cấp claim bổ sung về End-User khi được truy cập đúng cách |

Không thay `issuer-uri` bằng authorization endpoint hoặc token endpoint. Chẳng hạn, giá trị dưới đây không đúng nếu provider thực tế có issuer ở `/realms/company`:

~~~yaml
# Ví dụ sai: đây là authorization endpoint, không phải issuer
issuer-uri: https://login.example.com/realms/company/protocol/openid-connect/auth
~~~

### 2.3. Issuer phải được đối chiếu chính xác

Trong OIDC, giá trị `issuer` công bố ở metadata phải tương ứng chính xác với issuer được kỳ vọng theo chuẩn. Không nên mặc định URL khác nhau chỉ do dấu `/` cuối chuỗi, scheme `http`/`https`, tên miền alias hoặc path realm/tenant là tương đương.

Ví dụ:

~~~text
https://login.example.com/realms/company
https://login.example.com/realms/partner
~~~

là **hai issuer khác nhau**, kể cả khi cùng được phục vụ từ một host. Chúng có thể đại diện cho hai realm/tenant với tập người dùng, client và chính sách khác nhau.

Trong thiết kế định danh người dùng OIDC, thông thường nên dùng cặp **`iss` + `sub`** thay cho `sub` một mình; `sub` chỉ được bảo đảm duy nhất trong phạm vi issuer tương ứng.

## 3. Discovery hoạt động thế nào?

### 3.1. OpenID Connect Discovery

OpenID Connect Discovery quy định cơ chế công bố **OpenID Provider Configuration** tại một well-known URL. Với issuer ví dụ:

~~~text
https://login.example.com/realms/company
~~~

OIDC discovery document thường nằm tại:

~~~text
https://login.example.com/realms/company/.well-known/openid-configuration
~~~

RP thực hiện HTTPS GET đến URL discovery, nhận một tài liệu JSON mô tả OP, rồi sử dụng các thông tin cần thiết để thực hiện giao thức.

Ví dụ lệnh xem metadata:

~~~bash
curl --include \
  "https://login.example.com/realms/company/.well-known/openid-configuration"
~~~

Địa chỉ trên chỉ là minh họa; hãy thay bằng issuer đúng của OP trong môi trường của bạn.

### 3.2. Ví dụ nội dung metadata

Một OP có thể công bố tài liệu như sau:

~~~json
{
  "issuer": "https://login.example.com/realms/company",
  "authorization_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/token",
  "userinfo_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/userinfo",
  "jwks_uri": "https://login.example.com/realms/company/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic"]
}
~~~

Đây là **JSON minh họa** cho các trường liên quan đến bài học. Metadata của provider thực tế thường có nhiều trường khác và có thể hỗ trợ thêm giá trị.

Cách hiểu các trường:

| Trường trong metadata | Mục đích |
|---|---|
| `issuer` | Giá trị issuer mà RP dùng để đối chiếu với issuer được cấu hình và claim `iss` |
| `authorization_endpoint` | URL cho bước chuyển hướng browser đến OP |
| `token_endpoint` | URL mà client gửi token request |
| `jwks_uri` | URL tải JWK Set có các khóa công khai của OP |
| `userinfo_endpoint` | URL UserInfo, nếu provider công bố và client cần |
| `response_types_supported` | Các response type OP hỗ trợ, ví dụ `code` |
| `subject_types_supported` | Loại subject identifier OP hỗ trợ |
| `id_token_signing_alg_values_supported` | Thuật toán ký ID token OP công bố hỗ trợ |
| `scopes_supported` | Các scope OP có thể công bố |
| `token_endpoint_auth_methods_supported` | Phương thức xác thực client OP công bố hỗ trợ |

**Metadata cho biết khả năng của provider, không khẳng định mọi client được phép sử dụng tất cả khả năng đó.** Ví dụ, OP có thể hỗ trợ `client_secret_basic` nhưng một client cụ thể lại được đăng ký sử dụng phương thức khác.

### 3.3. Discovery và JWK Set là hai tài liệu khác nhau

Tài liệu metadata có thể chứa:

~~~json
{
  "jwks_uri": "https://login.example.com/realms/company/protocol/openid-connect/certs"
}
~~~

Khi cần xác minh ID token có chữ ký, thành phần bảo mật có thể tải **JWK Set** từ URL này để lấy khóa công khai phù hợp.

Ví dụ JWK Set có dạng tổng quát:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "signing-key-2026",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

Giá trị `n` trong ví dụ là placeholder nên JSON này không phải JWK có thể dùng để xác minh. Trong hệ thống thật, thư viện xử lý việc lấy key, chọn key theo header và xác minh chữ ký theo cấu hình tin cậy.

**Không nên nhầm:**

- Discovery document: mô tả provider và URL kỹ thuật.
- JWK Set: công bố các khóa để xác minh chữ ký tương ứng.
- ID token: bằng chứng xác thực người dùng do OP phát hành cho RP.
- Access token: dùng để truy cập Resource Server theo quyền đã được cấp.

Discovery không có nghĩa RP được bỏ qua xác minh chữ ký hay kiểm tra issuer/audience trong ID token.

## 4. OIDC Discovery và OAuth 2.0 Authorization Server Metadata

Hai cơ chế có liên quan nhưng phục vụ những đối tượng có thể khác nhau:

- **OpenID Connect Discovery**: mô tả **OpenID Provider**, bao gồm những thông tin cần cho RP thực hiện xác thực OIDC.
- **OAuth 2.0 Authorization Server Metadata** (RFC 8414): mô tả thông tin của Authorization Server phục vụ các cơ chế OAuth 2.0.

### 4.1. Cùng ý tưởng, có thể khác đường dẫn well-known

Với issuer có path, quy tắc hình thành URL well-known giữa các chuẩn không hoàn toàn giống nhau.

Ví dụ issuer:

~~~text
https://auth.example.com/tenant/acme
~~~

Các vị trí thường gặp:

~~~text
OIDC Discovery:
https://auth.example.com/tenant/acme/.well-known/openid-configuration

OAuth 2.0 Authorization Server Metadata (RFC 8414):
https://auth.example.com/.well-known/oauth-authorization-server/tenant/acme
~~~

Trong các phiên bản hỗ trợ, Spring Security có thể dùng phương thức tìm metadata tương ứng với issuer và các endpoint well-known theo cơ chế được thư viện hỗ trợ. **Không nên tự giả định** chỉ có một biến thể đường dẫn mà chưa kiểm tra cấu hình của provider.

Nếu OP công bố tài liệu ở một vị trí không theo chuẩn hoặc Spring không tìm được, cần tham khảo tài liệu của nhà cung cấp, kiểm tra các URL, rồi cân nhắc khai báo endpoint thủ công.

### 4.2. OAuth metadata chưa chắc đủ cho OIDC Login

Một Authorization Server chỉ hỗ trợ OAuth 2.0 có thể công bố metadata nhưng **không phát hành ID token**. Trong trường hợp đó, nó có thể phục vụ OAuth client gọi API, nhưng không tự trở thành OpenID Provider.

Ngược lại, để đăng nhập OIDC, client cần scope `openid` cùng OP hỗ trợ OIDC và xử lý ID token hợp lệ.

Vì vậy:

- `issuer-uri` là điểm bắt đầu discovery, nhưng không tự bảo đảm provider hỗ trợ mọi tính năng OIDC.
- `client_credentials` chỉ cần metadata/endpoint phục vụ grant tương ứng; không phải một luồng xác thực người dùng cuối.
- `oauth2Login()` yêu cầu cấu hình phù hợp với luồng đăng nhập được chọn, đặc biệt khi muốn nhận principal OIDC.

## 5. Cấu hình `issuer-uri` trong Spring Boot

### 5.1. Dependency OAuth 2.0 Client

Với dự án Maven sử dụng Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Starter này cung cấp hỗ trợ OAuth 2.0 Client và OIDC Login tương ứng với phiên bản Spring Boot/Spring Security đang dùng.

### 5.2. Cấu hình tối thiểu cho một OIDC registration

Giả sử client đã được đăng ký tại OP:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
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
            client-name: Corporate SSO
        provider:
          company-oidc:
            issuer-uri: https://login.example.com/realms/company
~~~

Cấu hình được chia thành hai phần có vai trò khác nhau.

**`registration.corporate`** mô tả client cụ thể:

| Thuộc tính | Ý nghĩa |
|---|---|
| `corporate` | `registrationId` của Spring Security |
| `provider: company-oidc` | Chỉ định provider config tham chiếu |
| `client-id` | Định danh đã được OP cấp cho ứng dụng |
| `client-secret` | Secret của confidential client; nạp từ môi trường |
| `client-authentication-method` | Cách client xác thực tại token endpoint |
| `authorization-grant-type` | Luồng `authorization_code` |
| `redirect-uri` | Callback để nhận code từ OP |
| `scope` | Các scope OIDC, có `openid` |

**`provider.company-oidc`** mô tả OP:

- `issuer-uri` cho Spring biết issuer đáng tin cậy.
- Khi discovery hoạt động, Spring lấy metadata liên quan từ OP, thay vì buộc bạn tự khai báo `authorization-uri`, `token-uri`, `jwk-set-uri` và các giá trị khác trong YAML.

Tên `corporate` và `company-oidc` do ứng dụng đặt; không bắt buộc giống nhau và không nhất thiết giống `client-id`.

### 5.3. Tạo luồng đăng nhập bằng Spring Security

Ví dụ dùng Servlet stack và Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Người dùng có thể bắt đầu luồng login bằng endpoint mặc định:

~~~http
GET /oauth2/authorization/corporate HTTP/1.1
Host: portal.example.com
~~~

Spring Security tra cứu `ClientRegistration` với `registrationId=corporate`, sử dụng endpoint provider đã được discovery xác định, rồi xây OIDC Authorization Request để chuyển hướng browser.

Khi OP hoàn tất xác thực/consent, browser quay lại:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

với authorization code và state thích hợp. Spring xử lý callback, token exchange, ID token và principal theo cấu hình OIDC đã chọn.

**Lưu ý:** Redirect URI phải được đăng ký tại OP và khớp địa chỉ public thực tế. Discovery không tự động đăng ký callback hoặc sửa cấu hình client tại provider.

### 5.4. Cấu hình cho nhiều provider

Một ứng dụng có thể dùng hai OP độc lập:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employee:
            provider: employee-idp
            client-id: ${EMPLOYEE_CLIENT_ID}
            client-secret: ${EMPLOYEE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          partner:
            provider: partner-idp
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, email]
        provider:
          employee-idp:
            issuer-uri: https://id.example.com/realms/employee
          partner-idp:
            issuer-uri: https://id.example.com/realms/partner
~~~

Hai registration này có thể sử dụng chung host nhưng **issuer khác nhau** do realm/path khác nhau. Spring sẽ phân biệt theo registration và provider tương ứng.

Các điểm cần nhớ khi hỗ trợ nhiều provider:

- Chọn registration thông qua một **danh sách được ứng dụng cho phép**, không ghép issuer URI từ input bất kỳ.
- Kiểm tra danh tính người dùng theo issuer và subject của ID token; không tự gộp hai người dùng chỉ vì email giống nhau.
- Token/client secret của từng registration cần được quản lý theo đúng client/provider.
- Các issuer có thể khác khả năng, chính sách consent, thuật toán ký và endpoint.

## 6. Spring Security xử lý discovery và `ClientRegistration`

### 6.1. Từ YAML đến đối tượng `ClientRegistration`

Trong cấu hình Spring Boot thông dụng, nhóm `spring.security.oauth2.client.*` được bind thành các cấu hình client và provider. Spring Boot có thể tạo `ClientRegistrationRepository` khi các điều kiện auto-configuration thỏa mãn.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Spring Boot startup
    participant Config as Client properties
    participant OP as OpenID Provider
    participant Repo as ClientRegistrationRepository
    participant Login as OAuth2 Login
    App->>Config: Đọc registration + provider issuer-uri
    App->>OP: GET metadata qua discovery
    OP-->>App: JSON metadata (issuer, endpoints, JWKS...)
    App->>App: Tạo ClientRegistration
    App->>Repo: Đăng ký registrationId -> ClientRegistration
    Login->>Repo: findByRegistrationId("corporate")
    Repo-->>Login: ClientRegistration với metadata provider
    Login->>OP: Bắt đầu Authorization Code theo endpoint đã biết
~~~

Luồng trên mô tả triển khai phổ biến. **Discovery có thể diễn ra khi tạo cấu hình/client registration**, nên nếu OP hoặc metadata không truy cập được ở thời điểm khởi tạo, ứng dụng có thể thất bại trong quá trình startup tùy cách cấu hình.

Phân biệt rõ:

- **Lấy metadata**: xác định mô tả provider.
- **Lấy JWK Set**: lấy khóa cần thiết khi xác minh token; thời điểm tải và cache phụ thuộc implementation.
- **Đổi code lấy token**: giao tiếp tại token endpoint sau callback.
- **Lấy UserInfo**: chỉ diễn ra nếu luồng và cấu hình có yêu cầu.
- **Đăng ký client tại OP**: tác vụ quản trị riêng, không xảy ra chỉ vì ứng dụng khởi động.

### 6.2. Tra cứu metadata trong code

Sau khi Spring tạo registration, ứng dụng có thể đọc một số thông tin provider:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Component;

@Component
public class ProviderEndpointInspector {

    private final ClientRegistrationRepository registrations;

    public ProviderEndpointInspector(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String describeProvider() {
        ClientRegistration client = registrations.findByRegistrationId("corporate");
        if (client == null) {
            throw new IllegalStateException("Missing registration: corporate");
        }

        ClientRegistration.ProviderDetails provider = client.getProviderDetails();

        return "issuer=" + provider.getIssuerUri()
                + ", authorizationEndpoint=" + provider.getAuthorizationUri()
                + ", tokenEndpoint=" + provider.getTokenUri()
                + ", jwksUri=" + provider.getJwkSetUri();
    }
}
~~~

Đoạn code dùng để **quan sát metadata không nhạy cảm** ở ngữ cảnh nội bộ. Không cần tự xây token exchange từ các URL trả về; Spring Security đã có các thành phần giao thức. Không ghi `clientSecret` hay token thật vào log để chẩn đoán.

### 6.3. Xây registration từ issuer bằng Java

Nếu cần đăng ký thủ công, Spring Security cung cấp `ClientRegistrations.fromIssuerLocation(...)` để sử dụng metadata:

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
public class RegistrationConfiguration {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${OIDC_CLIENT_ID}") String clientId,
            @Value("${OIDC_CLIENT_SECRET}") String clientSecret) {

        ClientRegistration corporate = ClientRegistrations
                .fromIssuerLocation("https://login.example.com/realms/company")
                .registrationId("corporate")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .clientName("Corporate SSO")
                .build();

        return new InMemoryClientRegistrationRepository(corporate);
    }
}
~~~

Ý nghĩa:

1. `fromIssuerLocation(...)` dùng issuer để tìm metadata provider theo cơ chế Spring Security hỗ trợ.
2. `registrationId("corporate")` đặt khóa nội bộ.
3. `clientId(...)` và `clientSecret(...)` được cung cấp từ cấu hình bảo mật; metadata **không cung cấp thông tin bí mật của client**.
4. `authorizationGrantType(...)` và `scope("openid", ...)` xác định luồng đăng nhập OIDC.
5. `InMemoryClientRegistrationRepository` làm nơi tra cứu registration.

Ví dụ này là **phương án thay thế cho repository được auto-configure từ YAML**. Khi đã tự khai báo bean repository, cần chịu trách nhiệm tập registration mà bean cung cấp.

Spring Security còn có các API tiện ích khác dành cho metadata OIDC tùy phiên bản. Khi triển khai, chọn API phù hợp với phiên bản dependency; ý tưởng chính không thay đổi: **issuer đáng tin cậy → lấy metadata → hoàn thiện registration**.

## 7. Discovery cung cấp gì và không cung cấp gì?

### 7.1. Những trường có thể xác định từ metadata

Thông thường, discovery giúp biết:

- `issuer` chính thức.
- URL authorization, token, JWK Set và các endpoint OIDC liên quan.
- Các response type, scope, phương thức client authentication hoặc thuật toán mà provider công bố.
- Một số khả năng mở rộng, ví dụ logout endpoint hoặc PKCE method theo metadata mà provider hỗ trợ.

Việc một trường có trong JSON không có nghĩa tất cả phiên bản Spring Security đều tự động sử dụng trường đó cho mọi tính năng. Cách các thành phần tiêu thụ metadata tùy thư viện và phần cấu hình.

### 7.2. Những trường phải được cung cấp riêng

Discovery **không** thay thế các thông tin được cấp khi đăng ký ứng dụng:

| Thông tin | Có tự có từ discovery không? | Nguồn thực tế |
|---|---|---|
| `client-id` | Không | OP hoặc hệ thống quản trị client |
| `client-secret` | Không | OP/secret manager, khi dùng |
| `client-authentication-method` cụ thể của client | Không được suy ra hoàn toàn | Thiết lập đăng ký client |
| `redirect-uri` của ứng dụng | Không | Ứng dụng và danh sách callback tại OP |
| `authorization-grant-type` mà client được cấp | Không được suy ra hoàn toàn | Đăng ký và chính sách của client |
| Scope ứng dụng muốn yêu cầu | Không | Nhu cầu nghiệp vụ và quyền client được cấp |
| Chính sách phân quyền API | Không | Resource Server và ứng dụng |
| Quy tắc liên kết tài khoản nội bộ | Không | Ứng dụng RP |

Ví dụ metadata có thể liệt kê `scopes_supported: ["openid", "profile", "email"]`, nhưng đăng ký `employee-portal` vẫn có thể bị giới hạn ở tập scope nhỏ hơn.

### 7.3. Discovery không chứng minh người dùng đã đăng nhập

Truy cập được metadata chỉ chứng minh endpoint đó đang cung cấp cấu hình provider; **nó không xác thực người dùng cuối**.

OIDC Login còn cần:

1. Authorization Request có `scope=openid` và các tham số an toàn như `state`, `nonce`/PKCE theo luồng.
2. Người dùng được OP xác thực và việc cấp quyền hoàn tất theo chính sách.
3. Client đổi authorization code lấy token tại endpoint phù hợp.
4. RP kiểm tra ID token và xây principal.
5. Ứng dụng áp dụng phân quyền nghiệp vụ riêng.

Tương tự, một ứng dụng nhận bearer access token để bảo vệ API là **Resource Server**, cần cấu hình xác minh token riêng. `spring.security.oauth2.client.provider.*.issuer-uri` phục vụ client/provider config; nó không thay thế `spring.security.oauth2.resourceserver.jwt.issuer-uri` khi thiết lập JWT Resource Server.

## 8. Phân biệt cấu hình Client và Resource Server

Hai properties có cùng tên cuối `issuer-uri` nhưng thuộc **hai chức năng khác nhau**.

### 8.1. OAuth 2.0 Client / OIDC RP

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          corporate-idp:
            issuer-uri: https://login.example.com/realms/company
~~~

Ứng dụng là **Client/RP**: bắt đầu đăng nhập, nhận token, kiểm tra ID token và có thể gọi API bằng access token.

### 8.2. OAuth 2.0 Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/company
~~~

Ứng dụng là **Resource Server**: nhận bearer JWT tại API, định vị cấu hình/khóa xác minh theo cơ chế được hỗ trợ và kiểm tra issuer cùng những điều kiện xác thực token tương ứng.

Hai đoạn YAML có thể xuất hiện cùng lúc nếu một ứng dụng vừa là RP/OAuth Client vừa cung cấp API nhận bearer token, nhưng trách nhiệm và chain bảo mật phải được thiết kế phù hợp. Việc cấu hình Client **không** tự bật xác thực bearer token cho API.

### 8.3. Vì sao dễ cấu hình nhầm?

Cả hai đều có thể sử dụng cùng issuer để tìm metadata hoặc khóa xác minh, nhưng:

- Client Registration tập trung vào **authorization/token endpoints** để xin quyền và đăng nhập.
- Resource Server tập trung vào **kiểm tra token đến** do client gửi tới API.
- Resource Server có thể cần cấu hình audience, scope/authority mapping và chính sách API riêng.
- Client Registration cần `client-id`, có thể client secret và callback; Resource Server bình thường không cần những giá trị đó để xác minh JWT đến.

Không sao chép một cấu hình client sang resource server rồi giả định ứng dụng đã hoàn tất mọi cơ chế OAuth/OIDC.

## 9. Nếu provider không hỗ trợ discovery thì sao?

Không phải mọi Authorization Server đều có tài liệu OIDC `.well-known/openid-configuration`, hoặc có thể metadata không truy cập được từ mạng ứng dụng.

Spring Security vẫn có thể sử dụng **các endpoint cấu hình thủ công** trong một số trường hợp, với điều kiện provider hỗ trợ luồng cần thiết.

### 9.1. Khai báo endpoint trong YAML

Ví dụ OIDC OP có các endpoint tường minh:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-manual
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
          company-manual:
            issuer-uri: https://login.example.com/realms/company
            authorization-uri: https://login.example.com/realms/company/protocol/openid-connect/auth
            token-uri: https://login.example.com/realms/company/protocol/openid-connect/token
            jwk-set-uri: https://login.example.com/realms/company/protocol/openid-connect/certs
            user-info-uri: https://login.example.com/realms/company/protocol/openid-connect/userinfo
~~~

**Lưu ý về ví dụ:** Khi `issuer-uri` được cấu hình trong Spring Boot, quá trình tạo registration có thể vẫn chủ động dùng issuer discovery tùy phiên bản và auto-configuration. Nếu mục tiêu là **tránh discovery hoàn toàn vì provider không có metadata**, không nên giả định chỉ bổ sung các endpoint bên cạnh `issuer-uri` sẽ tắt discovery.

Một cách cấu hình tường minh không cần issuer discovery tại thời điểm tạo registration là dùng **`ClientRegistration.Builder`** với các endpoint và issuer do ứng dụng quản lý, hoặc dùng cấu hình Boot chỉ định đầy đủ các endpoint mà không kích hoạt nhánh discovery, đồng thời kiểm tra khả năng xác minh ID token theo phiên bản thư viện.

### 9.2. Tạo `ClientRegistration` thủ công

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration client = ClientRegistration
        .withRegistrationId("corporate")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile", "email")
        .issuerUri("https://login.example.com/realms/company")
        .authorizationUri(
                "https://login.example.com/realms/company/protocol/openid-connect/auth")
        .tokenUri(
                "https://login.example.com/realms/company/protocol/openid-connect/token")
        .jwkSetUri(
                "https://login.example.com/realms/company/protocol/openid-connect/certs")
        .userInfoUri(
                "https://login.example.com/realms/company/protocol/openid-connect/userinfo")
        .clientName("Corporate SSO")
        .build();
~~~

Trong đoạn code, `clientId` và `clientSecret` là các biến đã được cấp từ cấu hình an toàn; endpoint được đặt sẵn từ thông tin tin cậy của OP.

Cách này giúp chủ động khai báo đủ thông tin mà không cần dựa vào metadata từ `fromIssuerLocation(...)`. **Tuy nhiên nó chuyển trách nhiệm duy trì endpoint và issuer chính xác sang ứng dụng.** Một OIDC OP vẫn phải hỗ trợ các hành vi và token theo chuẩn; việc bỏ discovery tự động không cho phép bỏ qua kiểm tra ID token.

### 9.3. Có nên hard-code endpoint không?

Có thể phù hợp khi provider hỗ trợ OAuth 2.0 nhưng không có metadata, hoặc doanh nghiệp cần một cấu hình cố định đáng tin cậy. Đổi lại:

- Mỗi môi trường phải duy trì các endpoint chuẩn.
- Khi nhà cung cấp thay URL/token endpoint/JWKS, ứng dụng có thể cần thay cấu hình và triển khai lại.
- Dễ cấu hình nhầm issuer và JWKS của các tenant/realm.
- Cần đánh giá lại khi nhà cung cấp thêm hoặc thay đổi chính sách bảo mật.

Khi discovery hoạt động đúng, **ưu tiên issuer-uri** để giảm sao chép cấu hình và giúp endpoint bám theo metadata được OP công bố.

## 10. Bảo mật khi tải và sử dụng metadata

### 10.1. Issuer phải đến từ nguồn đáng tin cậy

Nếu ứng dụng cho phép request như:

~~~text
/login?issuer=https://some-user-input.example
~~~

rồi tự động tải metadata từ issuer do người dùng chỉ định, nó có thể tạo điều kiện cho việc truy cập URL ngoài ý muốn hoặc tin cậy một nhà phát hành chưa được kiểm soát.

Một thiết kế an toàn thường:

- Duy trì tập issuer được quản trị và cho phép trước.
- Chọn `registrationId` từ danh sách đã cấu hình.
- Không ghép issuer, token endpoint hoặc JWKS URI từ giá trị client/browser gửi lên.
- Nếu cần hỗ trợ tenant động, xác định quy trình tin cậy, kiểm tra metadata, quản lý khóa và cô lập tenant riêng.

**Discovery không phải cơ chế tự động tin mọi máy chủ có thể truy cập được.** Mấu chốt là RP đã xác định issuer đáng tin cậy trước khi tải metadata.

### 10.2. Dùng HTTPS và xác minh chứng chỉ TLS

Các endpoint OIDC thường vận hành qua HTTPS. Trong production, ứng dụng cần tin cậy chuỗi chứng chỉ phù hợp và tránh giải pháp “tắt kiểm tra TLS” để xử lý lỗi kết nối.

Nếu discovery báo lỗi TLS, hãy kiểm tra:

- Chứng chỉ và chuỗi CA mà máy chủ sử dụng.
- Truststore/JVM trust configuration của ứng dụng.
- Cấu hình reverse proxy và hostname trong certificate.
- Có đang truy cập domain đúng của issuer không.

Vô hiệu hóa TLS verification có thể khiến metadata hoặc endpoint bị thay đổi bởi bên không tin cậy.

### 10.3. Xác minh issuer trong metadata và token

Nếu RP cấu hình issuer:

~~~text
https://login.example.com/realms/company
~~~

nhưng metadata trả:

~~~json
{
  "issuer": "https://login.example.com/realms/other-tenant"
}
~~~

đó là dấu hiệu cấu hình không khớp. Không sửa bằng cách bỏ qua issuer validation. Cần sửa URI, tenant hoặc cấu hình OP để chúng thống nhất.

Sau đó, ID token trả về vẫn cần được kiểm tra `iss`, chữ ký, audience, thời hạn và các điều kiện OIDC tương ứng.

### 10.4. Thay đổi khóa ký và khả năng cache

OP có thể thay khóa ký ID token. JWK Set URI giúp RP có một nguồn xác minh khóa công khai.

Tuy nhiên, không nên mặc định:

- Public key không bao giờ thay đổi.
- Metadata luôn được tải lại ở mỗi request.
- JWK Set và metadata có cùng vòng đời cache.
- Bất kỳ khóa nào lấy được từ một issuer khác cũng có thể xác minh token mong muốn.

Cơ chế tải/cache/refresh key phụ thuộc vào Spring Security và thư viện xác minh JWT được sử dụng. Khi vận hành, cần theo dõi thay khóa, khả năng truy cập JWKS và chính sách cache phù hợp.

## 11. Các lỗi thường gặp và cách suy luận nguyên nhân

| Triệu chứng | Khả năng nguyên nhân | Cách xem xét |
|---|---|---|
| Khởi động ứng dụng lỗi khi tạo `ClientRegistration` | Metadata không truy cập được, JSON không hợp lệ, issuer sai hoặc thiếu trường cần thiết | Thử URL discovery từ **mạng chạy ứng dụng**, xem response HTTP và metadata |
| HTTP 404 tại `.well-known/openid-configuration` | Dùng sai issuer, sai tenant/realm hoặc provider không triển khai OIDC discovery | Đối chiếu issuer OP công bố và quy tắc well-known mà provider hỗ trợ |
| TLS handshake failure | Chứng chỉ/truststore/hostname không phù hợp | Xác minh chứng chỉ và cấu hình trust của JVM |
| Metadata trả issuer khác cấu hình | OP chạy sau proxy sai public URL hoặc cấu hình nhầm tenant | Sửa cấu hình issuer tại OP/ứng dụng; không bỏ xác minh |
| Authorization Request bị từ chối | Client ID, redirect URI, grant hoặc scope không được OP cho phép | Kiểm tra client registration tại OP |
| Token exchange trả `invalid_client` | Secret hoặc phương thức client auth không khớp | Xem secret, cơ chế rotation, `client-authentication-method` |
| Callback thất bại do `redirect_uri_mismatch` | Callback public khác redirect URI đã đăng ký | So sánh scheme, host, port, path, reverse proxy |
| Đăng nhập OIDC không tạo principal như kỳ vọng | Thiếu `openid` hoặc provider không phát hành ID token hợp lệ | Kiểm tra scope, metadata OIDC, token response |
| Xác minh ID token thất bại | Sai issuer/audience, chữ ký/key hoặc token hết hạn | Kiểm tra `iss`, `aud`, `exp` và JWKS thuộc đúng OP |
| Cấu hình chạy local nhưng lỗi trên production | DNS, proxy, CA, URL public hoặc cấu hình môi trường khác nhau | Kiểm tra từ chính container/host production |

Bảng trên chỉ nêu hướng điều tra. Lỗi thực tế được trả ở giai đoạn nào và dạng exception nào còn phụ thuộc phiên bản framework, cấu hình OP và giao thức được dùng.

### 11.1. Sai issuer do nhầm tenant hoặc realm

Giả sử OP có hai realm:

~~~text
https://login.example.com/realms/dev
https://login.example.com/realms/prod
~~~

Nếu `client-id` được cấp cho `prod` nhưng `issuer-uri` trỏ tới `dev`, có thể xảy ra lỗi `invalid_client` hoặc lỗi xác minh token/issuer.

Hướng xử lý: xem client được đăng ký ở realm nào, dùng issuer đúng realm đó và xác nhận redirect URI của client được phép.

### 11.2. Sai issuer do reverse proxy

Giả sử bên ngoài OP công bố:

~~~text
https://login.example.com/realms/company
~~~

nhưng metadata lại trả:

~~~text
http://idp:8080/realms/company
~~~

Nguyên nhân có thể là OP không được cấu hình đúng hostname public hoặc forwarded headers ở reverse proxy. **Không đổi cấu hình Spring sang URL nội bộ chỉ để discovery thành công** nếu OP thực tế phát hành ID token với issuer public khác.

Địa chỉ public trong metadata và claim `iss` phải nhất quán với issuer được RP tin cậy. Proxy và OP cần được cấu hình để quảng bá đúng địa chỉ công khai.

### 11.3. Metadata truy cập được nhưng khởi tạo vẫn lỗi

Trả HTTP 200 chưa đảm bảo JSON hợp lệ cho client cần tạo. Hãy kiểm tra:

- Response có đúng `Content-Type` và JSON cần thiết không?
- `issuer` có khớp URI kỳ vọng?
- Có `authorization_endpoint`, `token_endpoint` và thông tin OIDC cần thiết?
- `jwks_uri` có đúng và truy cập được không?
- Có đang nhận redirect tới trang HTML login/thông báo lỗi thay vì metadata không?
- Provider có hỗ trợ flow và phương thức xác thực client đã đăng ký không?

Thông thường metadata endpoint là endpoint công khai để client có thể discovery; nó không nên yêu cầu client có phiên đăng nhập trước khi đọc.

### 11.4. Cấu hình callback khi chạy sau proxy

Một Spring Boot application có thể nhận request nội bộ tại:

~~~text
http://portal-service:8080
~~~

nhưng người dùng truy cập qua:

~~~text
https://portal.example.com
~~~

Mẫu redirect URI:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

phải được giải quyết thành địa chỉ public đúng. Nếu Spring suy ra `http://portal-service:8080`, OP có thể từ chối callback. Cần cấu hình proxy và cơ chế forwarded headers đáng tin cậy, hoặc chọn mẫu callback phù hợp kiến trúc.

Lỗi này liên quan đến **redirect URI của client**, không nhất thiết do discovery sai. Đừng sửa `issuer-uri` để giải quyết một lỗi vốn do proxy của chính ứng dụng RP.

## 12. Phương pháp kiểm tra một provider trước khi tích hợp

Để chuẩn bị một cấu hình Spring Security OIDC Client, có thể thực hiện các bước sau.

### Bước 1. Lấy issuer chính thức

Thu thập issuer mà OP công bố từ tài liệu cấu hình/quản trị provider. Với tenant/realm, cần lấy **issuer đúng tenant**, không chỉ domain gốc.

Ví dụ:

~~~text
https://login.example.com/realms/company
~~~

### Bước 2. Xem metadata

Với OIDC discovery endpoint theo dạng phổ biến:

~~~bash
curl --include \
  "https://login.example.com/realms/company/.well-known/openid-configuration"
~~~

Kiểm tra nội dung `issuer` và các endpoint kỹ thuật. Nếu 404, kiểm tra lại đường dẫn đúng theo provider và các chuẩn metadata được nó hỗ trợ.

### Bước 3. Đối chiếu client đã đăng ký

Xác định:

- `client-id` và phương thức client authentication.
- Grant type được bật, ví dụ Authorization Code.
- Redirect URI public của ứng dụng.
- Các scope cần và được phép, đặc biệt `openid` khi dùng OIDC.
- Chính sách PKCE, consent, logout hoặc yêu cầu chuyên biệt của OP.

### Bước 4. Cấu hình Spring Boot

Đặt thông tin client dưới `spring.security.oauth2.client.registration`, thông tin provider dưới `spring.security.oauth2.client.provider`, sử dụng `issuer-uri` đáng tin cậy nếu discovery hỗ trợ.

Nạp client secret từ biến môi trường hoặc secret manager, không lưu bí mật trong tài liệu hoặc mã nguồn commit công khai.

### Bước 5. Thử luồng đăng nhập đầy đủ

Đăng nhập qua `/oauth2/authorization/<registrationId>`, quan sát browser được chuyển đến **đúng OP**, sau đó trở về callback đã đăng ký và ứng dụng nhận principal OIDC phù hợp.

Thử thêm trường hợp người dùng từ chối, phiên OP hết hạn và khi có nhiều tenant/provider để đảm bảo không vô tình chọn sai issuer.

### Bước 6. Theo dõi khi vận hành

Theo dõi thời điểm OP mất kết nối, metadata/JWKS không truy cập được, thay đổi certificate/keys, cấu hình client secret và issuer sau khi nâng cấp hoặc di chuyển provider. Định kỳ xác nhận cấu hình public URL của OP vẫn nhất quán.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `issuer-uri` không nên trỏ trực tiếp đến URL `/authorize`?

**Trả lời:** Issuer là định danh của provider và được đối chiếu với metadata cũng như `iss` trong ID token. Authorization endpoint chỉ là một URL thực hiện bước chuyển hướng; nó không thay thế issuer.

**Câu 2.** Spring Boot có `issuer-uri` rồi, có thể bỏ `client-id` không?

**Trả lời:** Không. Discovery công bố cấu hình của OP, còn `client-id` xác định ứng dụng đã đăng ký ở OP. Nếu client cần xác thực bằng secret hay cơ chế khác, vẫn phải cấu hình phù hợp.

**Câu 3.** `jwks_uri` trong metadata dùng để làm gì?

**Trả lời:** Đây là URL lấy JWK Set, thường chứa các khóa công khai để xác minh chữ ký ID token do OP phát hành. Nó khác token endpoint.

**Câu 4.** Vì sao metadata của `/realms/dev` không nên dùng thay cho `/realms/prod` dù cùng hostname?

**Trả lời:** Vì issuer khác nhau là ranh giới tin cậy khác nhau. Registration, token, khóa và người dùng có thể khác theo realm. RP phải sử dụng issuer phù hợp với OP đã đăng ký.

**Câu 5.** Ứng dụng có `spring.security.oauth2.client.provider.corporate.issuer-uri` thì endpoint REST của chính nó có tự động chấp nhận JWT bearer token không?

**Trả lời:** Không. Cấu hình này thuộc OAuth Client/OIDC RP. Nếu muốn REST API xác minh access token, phải cấu hình vai trò Resource Server riêng.

**Câu 6.** Nếu provider không có discovery endpoint, có phải không thể dùng OAuth 2.0 Client không?

**Trả lời:** Không nhất thiết. Có thể cấu hình các endpoint cần thiết thủ công theo cơ chế mà Spring Security và provider hỗ trợ. Tuy nhiên, nếu muốn OIDC Login, provider vẫn phải thực sự hỗ trợ OIDC và phát hành ID token hợp lệ.

**Câu 7.** Metadata cho biết OP hỗ trợ `scope=email`. Điều đó có đảm bảo registration của bạn nhận được email không?

**Trả lời:** Không. Metadata mô tả khả năng OP; scope thực sự được cấp, claim có mặt và vị trí trả claim còn phụ thuộc client registration, consent và chính sách OP.

**Câu 8.** Nếu metadata trả `issuer=http://idp:8080/realms/company` nhưng client đang tin `https://login.example.com/realms/company`, nên làm gì?

**Trả lời:** Điều tra cấu hình public issuer, hostname và reverse proxy của OP; sửa để các giá trị nhất quán. Không tắt kiểm tra issuer hoặc đổi sang URL nội bộ một cách tùy tiện.

## Ghi nhớ

- **`issuer-uri` là định danh nhà phát hành mà ứng dụng OIDC Client/RP tin cậy.** Nó cần tương thích với metadata của provider và claim `iss` trong ID token.
- **Discovery** cho phép Spring Security nhận các endpoint và thông tin provider từ một tài liệu metadata, giảm việc cấu hình rời rạc nhiều URL.
- **Metadata không thay cho việc đăng ký client.** Ứng dụng vẫn phải cung cấp client ID, phương thức xác thực, grant type, callback và scope phù hợp.
- **OIDC Discovery và OAuth Authorization Server Metadata** có liên quan nhưng không hoàn toàn giống nhau, đặc biệt về loại metadata và quy tắc well-known URI.
- **Client registration và Resource Server là hai vai trò khác nhau.** Hai nơi cùng có `issuer-uri` nhưng được cấu hình tại các property path khác nhau.
- Khi discovery lỗi, hãy kiểm tra **issuer đúng tenant, HTTPS, metadata, mạng chạy ứng dụng, reverse proxy và callback**; không bỏ các bước kiểm tra bảo mật để làm cho ứng dụng tạm thời chạy được.
