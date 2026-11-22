# Bật endpoint đăng ký động theo phạm vi và phiên bản sử dụng

## 1. Mục tiêu và phạm vi của bài học

Trong mô-đun **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng **Spring Security**, **Spring Authorization Server** và **Spring Boot**. Bài này hướng dẫn bật **OpenID Connect Dynamic Client Registration Endpoint** trong Spring Authorization Server, giới hạn quyền đăng ký theo scope và chọn cấu hình phù hợp với phiên bản thư viện đang sử dụng.

Thông thường, client được quản trị viên đăng ký trước trong `RegisteredClientRepository`. Khi một hệ thống có nhiều tenant, nhiều ứng dụng tích hợp hoặc cần tự động tạo client theo quy trình onboarding, việc đăng ký thủ công từng client có thể trở thành nút thắt. Dynamic Client Registration (DCR) cho phép một client/developer gửi metadata đăng ký tới Authorization Server và nhận `client_id` cùng các thông tin cấu hình được chấp nhận.

Spring Authorization Server hỗ trợ **OpenID Connect Dynamic Client Registration 1.0**. Endpoint này **bị tắt mặc định** vì nhiều hệ thống không cần chức năng đăng ký động. Khi bật, endpoint vẫn là một OAuth 2.0 protected resource: bên đăng ký phải có Access Token hợp lệ với scope phù hợp. Đây là điểm quan trọng khi quyết định bật tính năng trong môi trường thật.

Sau bài này, bạn có thể:

1. Phân biệt OIDC Dynamic Client Registration với việc thêm client tĩnh vào repository.
2. Xác định API cấu hình theo nhánh Spring Authorization Server đang dùng.
3. Bật Client Registration Endpoint trong `SecurityFilterChain`.
4. Khai báo `JwtDecoder`, endpoint path và registrar client.
5. Cấp initial access token có đúng scope `client.create`.
6. Gửi registration request, đọc response và truy xuất client registration.
7. Giới hạn metadata, redirect URI, grant type, scope và bảo vệ credential.
8. Kiểm thử endpoint, chẩn đoán lỗi và vận hành an toàn.

**Phạm vi ví dụ:** code cấu hình chính trong bài dùng API Spring Authorization Server **1.5.x**, đối chiếu tài liệu **1.5.8**. Bài cũng nêu các nhánh stable khác để bạn kiểm tra đúng tài liệu của dependency đang dùng. Ví dụ sử dụng registrar đã được cấp quyền, không triển khai đăng ký công khai vô danh.

## 2. Dynamic Client Registration là gì?

### 2.1. Đăng ký tĩnh và đăng ký động

| Cách đăng ký | Ai tạo client? | Khi nào phù hợp? |
| --- | --- | --- |
| Static registration | Quản trị viên hoặc provisioning job tạo `RegisteredClient` trước khi ứng dụng sử dụng | Số client ít, quy trình phê duyệt thủ công, cấu hình ổn định |
| Dynamic registration | Client/developer gửi metadata tới Registration Endpoint; Authorization Server kiểm tra và tạo registration | Onboarding nhiều tenant/client, tích hợp tự động có kiểm soát |

Dynamic registration **không có nghĩa client tự chọn mọi quyền**. Authorization Server vẫn quyết định metadata nào được chấp nhận, thay thế bằng giá trị mặc định hay từ chối request. `redirect_uris`, `grant_types`, `response_types`, `scope`, phương thức xác thực client, JWK và các metadata khác phải được kiểm tra theo policy.

### 2.2. Phân biệt ba loại token/credential

Quy trình Spring Authorization Server sử dụng các credential có mục đích khác nhau:

| Credential | Ai sử dụng? | Mục đích |
| --- | --- | --- |
| Registrar client credentials | Dịch vụ quản lý đăng ký | Xác thực registrar tại Token Endpoint để xin initial access token |
| Initial access token | Registrar/developer được cấp quyền | Cho phép thực hiện một lần đăng ký client mới với scope `client.create` |
| `registration_access_token` | Bên quản lý client đã tạo | Gọi Client Read Endpoint qua `registration_client_uri` |

Không nhầm `client_secret` của registrar với secret được cấp cho client mới. Cũng không dùng Access Token của client nghiệp vụ để gọi Registration Endpoint nếu token đó không có quyền `client.create`.

### 2.3. OIDC DCR trong Spring Authorization Server và RFC 7591

RFC 7591 định nghĩa OAuth 2.0 Dynamic Client Registration Protocol. OIDC Dynamic Client Registration 1.0 mở rộng mô hình metadata và quy trình này cho OpenID Connect. Spring Authorization Server mô tả chức năng của mình là triển khai **OpenID Connect Dynamic Client Registration 1.0**.

Có một khác biệt vận hành cần nhớ:

- RFC 7591 cho phép mô hình open registration không có initial access token, nếu Authorization Server chọn hỗ trợ.
- Endpoint của Spring Authorization Server được tài liệu hóa là **OAuth2 protected resource**, yêu cầu Bearer Access Token.
- Spring guide dùng registrar client đã đăng ký trước, initial token chỉ có scope `client.create` và chỉ dùng một lần.
- Spring guide minh họa đăng ký và đọc client registration. Không suy ra rằng chỉ bật endpoint này là có toàn bộ chức năng quản lý registration theo RFC 7592 (update/delete) hoặc một portal quản trị hoàn chỉnh.

Vì vậy, hãy xem DCR là một API provisioning cần được giới hạn theo danh tính registrar và policy của Authorization Server, không phải một biểu mẫu public để bất kỳ ai tạo client tùy ý.

## 3. Chọn phiên bản Spring Authorization Server

### 3.1. Phiên bản tài liệu và API sử dụng

Tại thời điểm đối chiếu tài liệu, trang Spring Authorization Server công bố các nhánh stable gồm 1.5.8, 1.4.8, 1.3.7 và 1.2.7; nhánh 2.0.0-M2 là preview. Dynamic Client Registration có tài liệu hướng dẫn trong nhánh 1.5.x và cũng có tài liệu ở nhánh 1.3.x/1.4.x.

| Nhánh | Tài liệu đối chiếu | Cách làm trong bài |
| --- | --- | --- |
| 1.5.x | Stable docs 1.5.8 | Dùng code mẫu chính |
| 1.4.x | Stable docs 1.4.8 | Mở đúng tài liệu 1.4.x và kiểm tra signature API khi nâng cấp |
| 1.3.x | Stable docs 1.3.7 | DCR cũng có guide; kiểm tra phiên bản Spring Security tương ứng |
| 1.2.x | Stable docs 1.2.7 | Đối chiếu API/configuration reference của nhánh này |
| 2.0 preview | 2.0.0-M2 | Chỉ thử nghiệm; không lấy preview API áp vào ứng dụng production đang chạy 1.x |

Không trộn `spring-security` và `spring-authorization-server` từ các nhánh không tương thích. Với Spring Boot, ưu tiên dùng dependency management/BOM được Spring khuyến nghị cho đúng phiên bản Boot; tránh tự ghim từng module Security ở các version khác nhau.

### 3.2. Kiểm tra dependency thực tế

Trước khi áp dụng ví dụ, kiểm tra dependency tree hoặc file build để xác nhận artifact `spring-security-oauth2-authorization-server` đang ở nhánh nào. Nếu IDE không nhận ra `clientRegistrationEndpoint(...)`, hãy kiểm tra:

1. Dependency thực tế có phải Spring Authorization Server hay không.
2. Phiên bản có chứa `OidcClientRegistrationEndpointConfigurer` hay không.
3. Đang dùng API `OAuth2AuthorizationServerConfigurer.authorizationServer()` của nhánh tương ứng hay một cấu hình cũ.
4. Dependency management có vô tình kéo một version khác với version khai báo không.

Không thêm class filter hoặc controller tự viết chỉ để bù cho một method không có trong dependency. Hãy chọn đúng version/API trước, rồi dùng extension point được cung cấp.

### 3.3. Các lớp API quan trọng

| Lớp/API | Vai trò |
| --- | --- |
| `OAuth2AuthorizationServerConfigurer` | Cấu hình các protocol endpoint của Authorization Server |
| `OidcConfigurer` | Bật và tùy biến OIDC endpoints |
| `clientRegistrationEndpoint(...)` | Bật/cấu hình Dynamic Client Registration Endpoint |
| `OidcClientRegistrationEndpointConfigurer` | Tùy biến converter, provider, response handler và error handler |
| `OidcClientRegistrationEndpointFilter` | Nhận Client Registration và Client Read request |
| `OidcClientRegistrationAuthenticationProvider` | Xử lý registration request |
| `OidcClientConfigurationAuthenticationProvider` | Xử lý client configuration/read request |
| `RegisteredClientRepository` | Lưu và tra cứu registrar/client mới |
| `JwtDecoder` | Xác minh JWT Access Token dùng để bảo vệ endpoint |

## 4. Bật OIDC Client Registration Endpoint

### 4.1. Cấu hình tối thiểu cho Spring Authorization Server 1.5.x

Endpoint được bật qua OIDC configurer. Ví dụ dưới đây giữ lại cấu hình mặc định của converter/provider và bật riêng Client Registration Endpoint:

```java
package com.example.authserver;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer
                    .oidc(oidc ->
                        oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                    )
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            );

        return http.build();
    }
}
```

Nếu ứng dụng đã bật OIDC cho Provider Configuration, UserInfo hoặc Logout, hãy **thêm `clientRegistrationEndpoint(...)` vào cùng lời gọi `oidc(...)` hiện tại**. Ví dụ:

```java
.oidc(oidc -> oidc
    .userInfoEndpoint(Customizer.withDefaults())
    .clientRegistrationEndpoint(Customizer.withDefaults())
)
```

Không tạo hai `SecurityFilterChain` cùng `securityMatcher(getEndpointsMatcher())` chỉ để bật thêm một endpoint. Giữ một filter chain cho các Authorization Server endpoints và mở rộng OIDC configurer trong bean đang có.

### 4.2. Endpoint mặc định

Trong Spring Authorization Server, đường dẫn mặc định thường dùng là:

```text
/connect/register
```

Filter này xử lý cả:

- **Client Registration Request**: `POST` JSON để tạo registration.
- **Client Read Request**: `GET` tới URI cấu hình client được trả về trong registration response.

Đây là endpoint OIDC, không phải OAuth Token Endpoint. Token Endpoint `/oauth2/token` được dùng trước đó để xin initial access token.

### 4.3. Tùy chỉnh endpoint path

Nếu cần path riêng, khai báo trong bean `AuthorizationServerSettings`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcClientRegistrationEndpoint("/connect/v1/register")
            .build();
}
```

Nếu ứng dụng đã có `AuthorizationServerSettings` để khai báo issuer, authorization endpoint, token endpoint, introspection hoặc revocation, hãy bổ sung `oidcClientRegistrationEndpoint(...)` vào **bean hiện tại**. Không tạo thêm một bean settings cạnh tranh nhau.

Sau khi đổi path, kiểm tra Provider Configuration/Discovery có công bố `registration_endpoint` đúng URL công khai hay không. Nếu triển khai sau reverse proxy, URL phải khớp issuer và external HTTPS host; không để client nhận URL nội bộ của container hoặc địa chỉ HTTP không tin cậy.

## 5. Các bean cần có

### 5.1. RegisteredClientRepository

Dynamic registration tạo `RegisteredClient` mới và lưu thông qua `RegisteredClientRepository`. Hệ thống đã có repository thì tái sử dụng repository đó; không khai báo bean repository thứ hai chỉ để thêm registrar.

Ví dụ đơn giản cho lab:

```java
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
public class RegistrarClientConfig {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder) {

        RegisteredClient registrar = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("registration-service")
                .clientSecret(passwordEncoder.encode("change-this-lab-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("client.create")
                .scope("client.read")
                .build();

        return new InMemoryRegisteredClientRepository(registrar);
    }
}
```

Đây là ví dụ standalone chỉ có một registrar và giả định ứng dụng đã có bean `PasswordEncoder`. Nếu ứng dụng đã có client khác, đưa registrar vào repository hiện hữu hoặc thêm registration bằng provisioning phù hợp. `InMemoryRegisteredClientRepository` chỉ phù hợp lab/test hoặc một tiến trình không cần lưu bền vững; production thường cần `JdbcRegisteredClientRepository` hoặc repository bền vững tương đương.

Secret lab phải thay bằng secret được quản lý an toàn. Không dùng `{noop}` hoặc ghi secret production trực tiếp trong source code.

### 5.2. JwtDecoder là yêu cầu của endpoint

Spring Authorization Server yêu cầu bean `JwtDecoder` cho Client Registration Endpoint vì endpoint được bảo vệ bằng OAuth2 Access Token; resource server support được cấu hình nhưng decoder vẫn phải có:

```java
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
```

Ví dụ giả định Authorization Server đã có `JWKSource<SecurityContext>` dùng để ký JWT. Nếu đã có `JwtDecoder` bean phù hợp thì dùng lại. Key cần được quản lý bền vững, có rotation và không được tạo lại ngẫu nhiên mỗi lần restart.

### 5.3. Không nhầm client.create với scope nghiệp vụ của client mới

Có hai lớp scope độc lập:

| Scope | Thuộc về ai? | Dùng để làm gì? |
| --- | --- | --- |
| `client.create` | Registrar client / initial access token | Cho phép tạo registration mới |
| `client.read` | Registrar/client management permission | Cho phép đọc thông tin registration |
| `openid`, `profile`, `email`, `orders.read`... | Client mới được đăng ký | Quyền mà client mới có thể yêu cầu khi thực hiện OAuth/OIDC flow sau này |

Một registration request có thể đề nghị scope `openid profile email`, nhưng initial access token để gọi `POST /connect/register` vẫn phải chỉ có scope `client.create` theo hướng dẫn Spring Authorization Server. Không cấp `client.create` cho mọi client nghiệp vụ chỉ vì chúng cần scope `orders.read`.

## 6. Cấp initial access token cho registrar

### 6.1. Registrar client phải được đăng ký trước

Registrar là một client đặc biệt có quyền tạo client khác. Trong ví dụ, registrar dùng:

- Grant type `client_credentials` để xin Access Token trực tiếp.
- Client authentication method `client_secret_basic`.
- Scope `client.create` để đăng ký client.
- Scope `client.read` nếu registrar cần đọc registration.

Đây là quyền quản trị, không phải scope mà ứng dụng web/mobile mới được đăng ký sẽ nhận.

### 6.2. Request tới Token Endpoint

Lấy initial access token với **chỉ một scope `client.create`**:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64(registration-service:REGISTRAR_SECRET)
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=client.create
```

Response minh họa:

```json
{
  "access_token": "INITIAL_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "client.create"
}
```

Không thêm `client.read`, `openid`, `profile` hoặc scope nghiệp vụ vào lần xin initial token này. Spring Authorization Server yêu cầu token registration có **duy nhất** scope `client.create`; token có thêm scope sẽ bị từ chối khi gọi Client Registration Endpoint.

### 6.3. Initial token chỉ dùng một lần

Trong hướng dẫn Spring Authorization Server, initial access token được dùng một lần. Sau khi đăng ký client thành công, token này bị invalidated. Vì vậy:

- Không lưu initial token để dùng làm token quản lý client lâu dài.
- Không retry POST registration vô hạn với cùng token nếu client bị timeout.
- Nếu response bị mất sau khi server đã tạo client, hãy xử lý như tình huống kết quả không rõ ràng; kiểm tra trạng thái qua quy trình quản trị hoặc registration read nếu đã có thông tin cần thiết.
- Không ghi initial token vào log, ticket, shell history hoặc telemetry.

`registration_access_token` trong response là credential riêng cho thao tác đọc registration; nó không phải initial token.

## 7. Gửi Client Registration Request

### 7.1. JSON metadata

Ví dụ đăng ký một confidential web client dùng Authorization Code:

```http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "inventory-web",
  "application_type": "web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile email"
}
```

Metadata là dữ liệu do registrar đề nghị. Authorization Server có thể chấp nhận, thay thế bằng giá trị phù hợp hoặc từ chối. Client không được mặc định rằng mọi trường gửi lên đều sẽ được lưu nguyên trạng.

### 7.2. Kiểm tra tính nhất quán của metadata

| Metadata | Điều cần kiểm tra |
| --- | --- |
| `redirect_uris` | HTTPS ở production; khớp chính xác với domain/path được phê duyệt; không wildcard |
| `grant_types` | Chỉ bật grant cần thiết; không tự cấp grant nguy hiểm hoặc đã lỗi thời |
| `response_types` | Phù hợp với grant type; Authorization Code tương ứng `code` |
| `token_endpoint_auth_method` | Phù hợp loại client và credential được cấp |
| `scope` | Nằm trong tập scope cho phép của tenant/client và không vượt quyền registrar |
| `jwks_uri` / `jwks` | Chỉ chấp nhận khóa public; kiểm tra HTTPS, nguồn và nội dung JWK |
| `post_logout_redirect_uris` | Kiểm tra tương tự redirect URI đăng nhập |
| `client_name`, `logo_uri`, `client_uri` | Xem là metadata hiển thị do bên đăng ký cung cấp; không coi là bằng chứng danh tính |

Không bật Implicit Grant hoặc Resource Owner Password Credentials chỉ vì client yêu cầu. Với ứng dụng mới, thường ưu tiên Authorization Code + PKCE và chọn phương thức xác thực client phù hợp.

### 7.3. Registration response

Response thành công theo ví dụ Spring Authorization Server có thể chứa:

```json
{
  "client_id": "generated-client-id",
  "client_secret": "GENERATED_CLIENT_SECRET",
  "client_id_issued_at": 1800000000,
  "client_secret_expires_at": 0,
  "client_name": "inventory-web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile email",
  "registration_access_token": "REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://auth.example.com/connect/register/generated-client-id"
}
```

Đây là response rút gọn để minh họa. Tập metadata thực tế phụ thuộc loại client, converter và phiên bản. `client_secret` chỉ được cấp cho loại client phù hợp; `registration_access_token` và `client_secret` là dữ liệu nhạy cảm, cần lưu vào secret manager ngay khi nhận. Không hiển thị chúng trong log hoặc UI quản trị không được bảo vệ.

### 7.4. Đọc lại registration

Spring Authorization Server hỗ trợ Client Read qua `registration_client_uri` được trả về. Request dùng `registration_access_token`:

```http
GET /connect/register/generated-client-id HTTP/1.1
Host: auth.example.com
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
```

Client Read Response trả metadata đã đăng ký; theo Spring guide, response đọc lại không trả lại trường `registration_access_token`. Hãy lưu token quản lý riêng ở nơi an toàn nếu cần thao tác đọc về sau.

Client Read request cũng là protected resource và cần Access Token có scope `client.read`. Trong flow của Spring guide, registrar được cấu hình scope `client.read` để có thể đọc registration; hãy bảo đảm registration access token được phát hành cho đúng quyền đọc và không dùng initial token `client.create` thay thế.

**Giới hạn phạm vi:** tính năng được hướng dẫn ở đây bao gồm đăng ký và đọc client. Nếu hệ thống cần update/delete registration, cần xác nhận API cụ thể của phiên bản đang dùng hoặc xây dựng quy trình quản trị riêng; không suy ra đầy đủ RFC 7592 chỉ từ việc endpoint registration đã bật.

## 8. Tùy biến validator và metadata khi cần

### 8.1. Bắt đầu bằng converter/provider mặc định

Nếu chỉ dùng các metadata OIDC chuẩn mà Spring Authorization Server hỗ trợ, hãy bật endpoint với `Customizer.withDefaults()` trước. Cấu hình mặc định đã có:

- `OidcClientRegistrationAuthenticationConverter` để đọc registration/read request.
- `OidcClientRegistrationAuthenticationProvider` để xác thực và tạo client.
- `OidcClientConfigurationAuthenticationProvider` để xử lý client read.
- Success/error handler để trả registration response hoặc OAuth error.

Không cần viết controller REST hoặc tự tạo `AuthenticationProvider` chỉ để endpoint hoạt động.

### 8.2. Custom metadata không tự động được lưu

Nếu ứng dụng muốn hỗ trợ trường riêng như `logo_uri`, `contacts`, `tenant_id` hoặc metadata nội bộ, cần xác định:

1. Metadata đó có thuộc chuẩn OIDC/OAuth registry hay là extension riêng?
2. Giá trị nào được phép client tự khai báo, giá trị nào phải lấy từ registrar policy?
3. Dữ liệu được lưu trong `RegisteredClient`/`ClientSettings` hay kho metadata riêng?
4. Client Read có trả lại cùng metadata đã chấp nhận không?
5. Metadata có được dùng cho quyết định bảo mật hay chỉ hiển thị?

Spring guide minh họa việc cấu hình custom converter cho cả `OidcClientRegistrationAuthenticationProvider` và `OidcClientConfigurationAuthenticationProvider`, cùng converter chuyển đổi giữa `OidcClientRegistration` và `RegisteredClient`. Nếu chỉ mở rộng converter chiều ghi mà không mở rộng chiều đọc, client read có thể mất custom metadata.

### 8.3. Giữ lại validation mặc định

Có một khác biệt quan trọng ở nhánh mới: từ Spring Authorization Server 1.5.7, `DEFAULT_SCOPE_VALIDATOR` từ chối mọi registration request có scope không rỗng. Vì vậy, ví dụ registration ở mục 7.1 có `scope` sẽ cần một validator scope tùy chỉnh; chỉ bật endpoint với `Customizer.withDefaults()` chưa đủ để chấp nhận metadata scope đó.

Spring cung cấp `SIMPLE_SCOPE_VALIDATOR` để giữ hành vi cũ và chấp nhận mọi scope, nhưng API này **không tạo allowlist**. Không dùng nó như một giải pháp production nếu chưa có policy khác giới hạn scope. Ví dụ dưới đây minh họa validator allowlist tĩnh; trong hệ thống nhiều tenant, thay tập scope tĩnh bằng policy tra theo registrar đã xác thực:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationValidator;

private static Consumer<List<AuthenticationProvider>> registrationValidator() {
    Set<String> allowedScopes = Set.of("openid", "profile", "email");

    return providers -> providers.forEach(authenticationProvider -> {
        if (authenticationProvider instanceof OidcClientRegistrationAuthenticationProvider provider) {
            provider.setAuthenticationValidator(context -> {
                OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_REDIRECT_URI_VALIDATOR.accept(context);
                OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR.accept(context);
                OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_JWK_SET_URI_VALIDATOR.accept(context);

                OidcClientRegistrationAuthenticationToken request =
                        context.getAuthentication();
                OidcClientRegistration registration = request.getClientRegistration();
                List<String> requestedScopes = registration.getScopes();
                if (requestedScopes == null) {
                    requestedScopes = List.of();
                }

                if (!allowedScopes.containsAll(requestedScopes)) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_SCOPE));
                }
            });
        }
    });
}
```

Nối validator này vào endpoint configurer:

```java
.oidc(oidc -> oidc
    .clientRegistrationEndpoint(endpoint ->
        endpoint.authenticationProviders(registrationValidator())
    )
)
```

Đoạn ví dụ thay validator của `OidcClientRegistrationAuthenticationProvider`, nhưng vẫn gọi lại các validator mặc định cho redirect URI, post-logout redirect URI và JWK Set URI trước khi áp dụng scope allowlist. Trong production, scope allowlist phải được lấy từ registrar/tenant policy phía server; không lấy tập scope được phép từ chính registration request.

Khi thay `authenticationProviders(...)` để tùy biến, đừng xóa toàn bộ validator chỉ để cho phép một scope hoặc metadata mới. Giữ lại các kiểm tra mặc định cho:

- redirect URI;
- post-logout redirect URI;
- JWK Set URI;
- và thêm scope policy riêng phù hợp với tenant/registrar.

Không thay các kiểm tra trên bằng validator kiểu “accept all” cho `redirect_uris` hoặc `jwks_uri`. Đặc biệt, `SIMPLE_SCOPE_VALIDATOR` chấp nhận mọi scope; chỉ dùng khi thật sự cần tương thích ngược và đã có lớp policy khác ngăn scope injection.

### 8.4. Registrar scope và client metadata scope là hai chính sách

Kiểm tra quyền ở hai thời điểm khác nhau:

| Thời điểm | Chính sách |
| --- | --- |
| Xin initial access token | Registrar có được cấp `client.create` hay không? |
| Gửi registration request | Metadata `scope` mà client mới yêu cầu có được cho phép không? |
| Client thực hiện authorize/token request sau này | Scope có nằm trong registration và được authorization policy cho phép không? |

Không dùng việc registrar có `client.create` để suy ra rằng client mới được phép có mọi scope. Registrar chỉ được phép yêu cầu tạo registration; server vẫn phải đánh giá metadata của registration.

## 9. Bảo mật và vận hành Dynamic Client Registration

### 9.1. Bảo vệ endpoint bằng TLS và registrar identity

RFC 7591 yêu cầu Registration Endpoint được bảo vệ bằng transport-layer security. Spring Authorization Server còn yêu cầu Access Token Bearer cho Client Registration và Client Read. Trong production:

- Chỉ cấp registrar credentials cho dịch vụ provisioning đã được phê duyệt.
- Phát hành initial access token qua quy trình out-of-band có xác thực và audit.
- Bảo vệ Token Endpoint và Registration Endpoint bằng HTTPS; kiểm tra certificate ở mọi client gọi endpoint.
- Giới hạn mạng, rate limit và quota theo registrar/tenant.
- Thu hồi registrar credential khi dịch vụ bị xâm nhập hoặc không còn nhiệm vụ.
- Không mở endpoint qua browser/SPA hoặc nhúng registrar secret vào ứng dụng public.

Nếu tổ chức cần người dùng tự bắt đầu onboarding, hãy để portal/backend đã xác thực thực hiện bước phê duyệt và cấp initial token cho dịch vụ provisioning. Đừng bỏ Bearer authentication ở Registration Endpoint để biến nó thành API public.

### 9.2. Bảo vệ initial access token và registration access token

- Initial access token chỉ cấp cho đúng registrar và đúng mục đích tạo client.
- Với Spring Authorization Server, request xin initial token chỉ có scope `client.create`; token sau khi đăng ký thành công bị invalidated.
- `registration_access_token` có quyền đọc cấu hình client tương ứng; coi nó như credential quản trị.
- `client_secret` mới chỉ hiển thị ở registration response; chuyển ngay vào secret manager và không log response body.
- Không dùng chung registration access token giữa tenant/client.
- Khi registration không còn cần thiết, dùng quy trình quản trị phù hợp để thu hồi client/credential và dọn metadata.

### 9.3. Kiểm tra metadata và chống lạm dụng

Đặt policy ở server cho:

- số lượng registration tối đa theo registrar, tenant hoặc software publisher;
- allowlist `redirect_uris` và `post_logout_redirect_uris`;
- grant types, response types, scopes và authentication methods được phép;
- JWK Set URL, logo URI và các URL do bên đăng ký cung cấp;
- loại client public/confidential và yêu cầu PKCE;
- thời hạn client secret, token lifetime và chính sách rotation;
- custom metadata nào được phép lưu/trả lại.

Các URL do client gửi lên có thể khiến server hoặc hệ thống quản trị truy cập tài nguyên ngoài dự kiến. Nếu ứng dụng tự fetch `jwks_uri`, logo hoặc metadata URL, áp dụng allowlist, giới hạn redirect, chặn địa chỉ loopback/private/link-local và giới hạn thời gian/kích thước phản hồi để giảm rủi ro SSRF.

### 9.4. Lưu trữ bền vững và nhiều instance

Trong production, `RegisteredClientRepository` cần lưu bền vững và dùng chung giữa các instance. Nếu một node đăng ký client nhưng node khác không đọc được registration đó, client sẽ gặp lỗi ngẫu nhiên ở Authorization Endpoint hoặc Token Endpoint.

Kiểm tra:

- repository dùng chung (ví dụ `JdbcRegisteredClientRepository`) và transaction commit trước khi trả registration success;
- unique constraint cho client ID và dữ liệu định danh registration;
- backup/restore và migration schema;
- cache invalidation khi client bị cập nhật hoặc thu hồi;
- audit ai đã tạo client, registrar nào, tenant nào và metadata nào được chấp nhận;
- quy trình xử lý initial token đã tiêu thụ nhưng response bị mất;
- dọn registration không còn sử dụng theo retention policy.

### 9.5. Discovery và endpoint path

OIDC Provider Configuration có metadata `registration_endpoint` để công bố URL đăng ký động khi OP hỗ trợ. Sau khi bật endpoint hoặc thay đổi path, kiểm tra discovery response từ issuer tin cậy và so khớp URL với `AuthorizationServerSettings`.

Không lấy `registration_endpoint` từ query parameter hoặc metadata do một client chưa tin cậy tự cung cấp. Client/developer phải biết issuer trước, xác minh issuer/discovery, rồi mới gửi credential tới endpoint được công bố.

## 10. Kiểm thử endpoint theo scope và version

### 10.1. Ma trận kiểm thử

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| DCR-01 | OIDC bật nhưng Client Registration Endpoint chưa bật | Endpoint registration chưa được đăng ký trong filter chain |
| DCR-02 | Bật `clientRegistrationEndpoint(Customizer.withDefaults())` | Filter xử lý registration/read được đăng ký |
| DCR-03 | Gọi `POST /connect/register` với initial token hợp lệ | Client được tạo và trả registration response |
| DCR-04 | Thiếu Bearer token | Request bị từ chối |
| DCR-05 | Bearer token sai/hết hạn | Request bị từ chối do Access Token không hợp lệ |
| DCR-06 | Initial token có duy nhất `client.create` và scope validator cho metadata được cấu hình | Registration được phép nếu metadata hợp lệ |
| DCR-07 | Initial token chứa thêm `client.read` hoặc scope khác | Registration bị từ chối theo policy của Spring Authorization Server |
| DCR-08 | Token không có `client.create` | Không được tạo client |
| DCR-09 | Dùng lại initial token sau registration thành công | Request tiếp theo bị từ chối vì token đã invalidated |
| DCR-10 | Đăng ký redirect URI không được chấp nhận | Registration bị từ chối |
| DCR-11 | Metadata grant/response type không nhất quán | Registration bị từ chối hoặc metadata bị điều chỉnh theo validator |
| DCR-12 | Client yêu cầu scope ngoài policy | Server không cấp scope vượt quyền; response/error phản ánh quyết định |
| DCR-13 | `JwtDecoder` bean bị thiếu | Cấu hình endpoint không hoàn chỉnh; test startup/integration phải phát hiện |
| DCR-14 | `AuthorizationServerSettings` đổi path nhưng client gọi path cũ | Request không tới endpoint đã cấu hình |
| DCR-15 | Discovery công bố `registration_endpoint` | URL phải khớp path và issuer công khai |
| DCR-16 | Đọc registration với registration access token hợp lệ | Client Read trả metadata đã đăng ký |
| DCR-17 | Đọc registration bằng token sai hoặc registration URI khác | Request bị từ chối |
| DCR-18 | Client Read response | Không lộ lại `registration_access_token` theo hướng dẫn Spring |
| DCR-19 | Registrar client không có `client.create` trong RegisteredClient | Không thể xin initial access token với scope này |
| DCR-20 | Registrar client xin token `client.create` và `client.read` cùng lúc | Token không phù hợp yêu cầu initial registration; phải chỉ xin `client.create` |
| DCR-21 | Nhiều registrar tạo client đồng thời | Client ID không trùng; repository lưu nhất quán |
| DCR-22 | Hai Authorization Server instance dùng chung repository | Node còn lại đọc được client mới sau khi commit |
| DCR-23 | Custom metadata chỉ được map khi ghi | Test phát hiện metadata bị mất khi Client Read |
| DCR-24 | Custom validator bỏ qua redirect URI validation | Security test phải thất bại; giữ lại validator mặc định |
| DCR-25 | Registrar vượt quota | Registration bị từ chối và có audit event |
| DCR-26 | Đăng ký `jwks_uri` trỏ tới địa chỉ nội bộ | Policy URL từ chối hoặc không fetch tài nguyên |
| DCR-27 | Initial token response bị mất sau khi server tạo client | Không retry mù với token cũ; xử lý reconciliation |
| DCR-28 | Nâng Spring Authorization Server từ 1.4.x lên 1.5.x | Compile/integration test xác nhận configurer, decoder và metadata hoạt động |
| DCR-29 | Chạy trên nhánh 2.0 preview | Test tách riêng; không giả định tương thích với API 1.x |
| DCR-30 | Client mới dùng Authorization Code + PKCE | Registration metadata và Authorization Endpoint policy chấp nhận đúng cấu hình |
| DCR-31 | SAS 1.5.7+ dùng validator scope mặc định với request có `scope` | Request bị từ chối cho tới khi cấu hình scope validator riêng |
| DCR-32 | Scope validator allowlist nhận `openid profile email` | Chỉ scope trong allowlist được chấp nhận; scope ngoài danh sách bị từ chối |
| DCR-33 | Client Read dùng Access Token thiếu `client.read` | Request bị từ chối dù token còn hạn |

### 10.2. Test tích hợp luồng end-to-end

Một kịch bản integration test cơ bản:

1. Khởi động Authorization Server với OIDC và Client Registration Endpoint được bật.
2. Đăng ký registrar client có `client_credentials`, `client.create` và `client.read`.
3. Xin initial access token với duy nhất `scope=client.create`.
4. Gửi POST registration với redirect URI và metadata hợp lệ.
5. Xác nhận response có `client_id`, cùng `registration_client_uri` và `registration_access_token` khi được cấp.
6. Dùng registration access token gọi Client Read Endpoint.
7. Xác nhận metadata đọc lại khớp registration đã được chấp nhận.
8. Thử lại POST bằng initial token cũ và xác nhận bị từ chối.
9. Thử POST bằng token thiếu scope hoặc chứa scope bổ sung.
10. Xác nhận client mới có thể thực hiện flow được đăng ký, ví dụ Authorization Code với redirect URI tương ứng.

Không chỉ test `POST /connect/register` trả thành công. Cần kiểm tra client được lưu vào repository và thực sự được Authorization Endpoint/Token Endpoint nhận diện.

### 10.3. Kiểm tra tương thích theo phiên bản

Khi thay phiên bản:

- compile lại filter chain và `AuthorizationServerSettings`;
- xác nhận `OidcClientRegistrationEndpointConfigurer` và provider classes còn trong API;
- xác nhận `JwtDecoder` được wiring đúng;
- chạy lại test registrar scopes, one-time token và Client Read;
- kiểm tra discovery metadata sau khi nâng cấp;
- đọc release notes/migration notes của đúng nhánh trước khi đổi custom converter hoặc validator.

## 11. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `404` tại `/connect/register` | Endpoint chưa bật hoặc path đã tùy chỉnh | Kiểm tra `.oidc(...clientRegistrationEndpoint(...))` và `AuthorizationServerSettings` |
| `401` khi đăng ký | Thiếu/sai/hết hạn initial access token | Kiểm tra Bearer header và token được cấp từ đúng issuer |
| Token hợp lệ nhưng registration bị từ chối | Token không có đúng scope `client.create` hoặc có thêm scope | Xin initial token chỉ với `client.create` |
| `invalid_client` khi xin token | Registrar client credentials/authentication method sai | Kiểm tra `RegisteredClient`, secret encoder và `client_secret_basic` |
| `invalid_scope` tại Token Endpoint | Registrar chưa được cấp `client.create` | Thêm scope vào registrar registration theo policy |
| `invalid_client_metadata` | Redirect URI, grant type, scope hoặc metadata không hợp lệ | Đọc error response và validator; không tắt toàn bộ validation |
| Không tạo được registration trong database | Repository không hỗ trợ lưu hoặc transaction/schema lỗi | Kiểm tra repository và database migration |
| `JwtDecoder` bean không có | Endpoint protected resource không thể xác minh JWT Access Token | Khai báo decoder tương ứng với JWK source |
| Client mới không authorize được | Metadata đã bị thay thế, redirect URI mismatch hoặc grant không được chấp nhận | Đọc lại registration response và kiểm tra `RegisteredClient` đã lưu |
| Client Read bị `401` | Registration access token sai/hết hạn hoặc không đúng registration | Dùng token và URI trong đúng registration response |
| Custom metadata không xuất hiện khi đọc | Chỉ tùy biến converter chiều registration | Cấu hình cả converter chiều RegisteredClient → OidcClientRegistration |
| Client registration chạy được trên một node | Repository/cache không chia sẻ giữa các node | Dùng repository chung và đồng bộ cache |
| Retry registration luôn lỗi | Initial token đã bị dùng và invalidated | Xin token mới theo policy; trước đó reconciliation xem client đã được tạo chưa |
| Discovery không có `registration_endpoint` | Metadata chưa công bố hoặc provider config tùy biến | Kiểm tra `OidcProviderConfiguration` và metadata customizer |
| IDE không nhận `clientRegistrationEndpoint` | Sai version hoặc dependency conflict | Kiểm tra dependency tree và docs đúng nhánh |

### 11.1. Phân biệt lỗi registrar và lỗi metadata client mới

1. **Registrar authentication failure:** Authorization Server không xác thực được registrar ở Token Endpoint.
2. **Initial token authorization failure:** registrar được xác thực nhưng token không có đúng scope để đăng ký.
3. **Registration metadata failure:** token hợp lệ nhưng metadata client mới không vượt qua validation.
4. **Persistence/runtime failure:** metadata hợp lệ nhưng repository hoặc database không lưu được.

Phân biệt các lớp lỗi giúp không phải nới lỏng validator hoặc cấp quyền quá rộng để chữa một vấn đề cấu hình.

### 11.2. Những cách sửa lỗi không an toàn

- Không bỏ Bearer token validation để xử lý lỗi `401`.
- Không cấp `client.create` cho mọi client chỉ để tránh `invalid_scope`.
- Không cho phép redirect URI wildcard hoặc mọi host.
- Không bỏ validator mặc định khi thêm custom metadata.
- Không log initial access token, registration access token hoặc client secret.
- Không dùng `InMemoryRegisteredClientRepository` cho cụm production cần dữ liệu bền vững.
- Không tự nhận endpoint hỗ trợ đầy đủ update/delete nếu phiên bản chỉ được cấu hình/test cho register và read.

## 12. Checklist production và tài liệu đối chiếu

### 12.1. Checklist trước khi bật endpoint

- [ ] Phiên bản Spring Authorization Server được xác nhận và code dùng đúng API của nhánh đó.
- [ ] OIDC được bật trong Authorization Server configurer.
- [ ] Client Registration Endpoint chỉ bật khi có nhu cầu provisioning rõ ràng.
- [ ] Endpoint path và `registration_endpoint` discovery khớp URL công khai.
- [ ] `JwtDecoder` bean có mặt và xác minh Access Token theo key/issuer tin cậy.
- [ ] Registrar client được đăng ký trước, dùng `client_credentials` và phương thức xác thực phù hợp.
- [ ] Registrar chỉ được cấp scope quản trị cần thiết (`client.create`, tùy nhu cầu `client.read`).
- [ ] Initial access token được xin với duy nhất `client.create`.
- [ ] Initial token được xem là one-time credential và không lưu/log để tái sử dụng.
- [ ] Metadata `redirect_uris`, grant types, response types, scopes và auth method được validate.
- [ ] Không cho client tự cấp scope vượt quyền tenant/registrar.
- [ ] Custom metadata có converter cho cả chiều ghi và chiều đọc.
- [ ] Validator mặc định cho redirect URI/JWK/scope được giữ lại hoặc thay bằng policy tương đương chặt chẽ.
- [ ] `RegisteredClientRepository` lưu bền vững và chia sẻ giữa các node.
- [ ] `client_secret` và `registration_access_token` được lưu trong secret manager.
- [ ] Có rate limit, quota, audit và quy trình thu hồi registrar/client.
- [ ] Có integration test cho registration, read, invalid token, scope sai, one-time token và version upgrade.
- [ ] Có quy trình reconciliation khi POST đã tạo client nhưng response bị mất.

### Bản đồ ghi nhớ

```text
Provisioning service / Registrar
       |
       | client_id + client_secret (registrar)
       v
POST /oauth2/token
grant_type=client_credentials
scope=client.create
       |
       v
Initial Access Token (one-time)
       |
       | Authorization: Bearer <initial-token>
       v
POST /connect/register
Content-Type: application/json
       |
       v
Spring Authorization Server
  - authenticate bearer token
  - require client.create only
  - validate client metadata
  - save RegisteredClient
       |
       v
Registration response
  client_id
  client_secret (if applicable)
  registration_access_token
  registration_client_uri
       |
       v
GET registration_client_uri
Authorization: Bearer <registration-access-token>
       |
       v
Client Read Response

Security boundary:
  registrar permission != new client's OAuth scopes
```

**Điểm cần nhớ:** Spring Authorization Server tắt OIDC Client Registration Endpoint mặc định. Với API 1.5.x, bật endpoint bằng `oidc.clientRegistrationEndpoint(...)`, cấu hình `JwtDecoder`, đăng ký một registrar client và cấp initial access token chỉ có `client.create`. Endpoint dùng token đó để tạo `RegisteredClient`; response trả client metadata cùng thông tin truy cập registration. Client Read dùng registration access token riêng. Hãy giữ metadata validation, giới hạn registrar scope, lưu repository bền vững và xác nhận API theo đúng phiên bản trước khi đưa DCR vào production.

## Tài liệu chuẩn để đối chiếu

- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): bật endpoint, registrar scopes, initial access token, registration và client read.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, filter, provider, protected resource và scope requirements.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` và cấu hình protocol endpoints.
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): strict/default validators, scope behavior và compatibility validators.
- [Spring Authorization Server 1.4.8 — Dynamic Client Registration guide](https://docs.spring.io/spring-authorization-server/reference/1.4/guides/how-to-dynamic-client-registration.html): đối chiếu nhánh 1.4.x.
- [Spring Authorization Server 1.3.7 — Dynamic Client Registration guide](https://docs.spring.io/spring-authorization-server/reference/1.3/guides/how-to-dynamic-client-registration.html): đối chiếu nhánh 1.3.x.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client metadata, registration request/response, software statement và initial access token.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): OIDC client registration metadata và quy tắc giao thức.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): giao thức quản lý registration riêng, cần đối chiếu trước khi thiết kế update/delete.
