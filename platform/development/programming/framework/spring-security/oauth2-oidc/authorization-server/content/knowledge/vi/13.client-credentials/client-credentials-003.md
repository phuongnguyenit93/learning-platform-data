# Xác thực client và gửi yêu cầu cấp access token

## Mục tiêu bài học

Trong chương **Client Credentials** thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, chúng ta học cách một dịch vụ tự **xác thực client** với Authorization Server và gửi yêu cầu cấp **access token** bằng OAuth 2.0 Client Credentials Grant. Bài học đặt trong bối cảnh xây dựng, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server với **Spring Security**, **Spring Authorization Server** và **Spring Boot**.

Sau bài này, người học có thể:

- Giải thích bản chất machine-to-machine (M2M) của `client_credentials` và điểm khác với Authorization Code + PKCE.
- Đăng ký `RegisteredClient` với grant `CLIENT_CREDENTIALS`, phương thức xác thực, scope và thời hạn token.
- Gửi request HTTP POST đúng RFC 6749 đến Token Endpoint bằng `client_secret_basic` và `application/x-www-form-urlencoded`.
- Diễn giải `access_token`, `token_type`, `expires_in`, `scope` và chính sách không phụ thuộc refresh token.
- Dùng Spring Security OAuth2 Client để xin, lưu và tái sử dụng token trong background job.
- Nhận diện lỗi `invalid_client`, `unauthorized_client`, `invalid_scope` và lỗi xác minh Bearer token ở Resource Server.
- Kiểm thử, bảo vệ credential, giới hạn scope/audience, kiểm soát timeout, retry, token caching và rotation trong production.

> **Tình huống xuyên suốt:** Service `inventory-worker` chạy mỗi năm phút, gọi API `https://inventory-api.example.com/inventory`. Nó không đăng nhập thay người dùng; service tự xác thực với Authorization Server `https://auth.example.com` và chỉ xin scope `inventory.read`.

## 1. Client Credentials Grant là gì?

RFC 6749 mục 4.4 định nghĩa Client Credentials Grant: client sử dụng chính credential của nó làm cơ sở yêu cầu access token khi có quyền truy cập tài nguyên do client kiểm soát hoặc theo một ủy quyền đã được sắp xếp trước với Authorization Server.

Đây là luồng **confidential client**: hệ thống gọi có khả năng bảo vệ credential (secret, private key hoặc chứng chỉ tương ứng) trong môi trường máy chủ được kiểm soát. Không có người dùng thao tác, không có trang login hay consent, không dùng authorization code.

```mermaid
sequenceDiagram
    autonumber
    participant W as Inventory Worker
    participant AS as Authorization Server
    participant RS as Inventory API / Resource Server
    W->>AS: POST /oauth2/token + client auth + grant_type=client_credentials
    AS->>AS: Kiểm client, credential, grant, scope và policy
    alt Hợp lệ
        AS-->>W: 200 access_token, token_type, expires_in, scope
        W->>RS: GET /inventory với Authorization: Bearer token
        RS->>RS: Kiểm issuer, audience, signature/active, expiry, scope
        RS-->>W: Dữ liệu theo inventory.read
    else Không hợp lệ
        AS-->>W: OAuth2 error response
    end
```

Các tình huống thường gặp: worker chạy lịch, service xử lý hàng đợi, backend gọi API đối tác, tiến trình đồng bộ dữ liệu hoặc công cụ tự động hóa hạ tầng. **Không dùng Client Credentials để mạo danh người dùng**: nếu nghiệp vụ cần quyết định của người dùng, phải chọn grant/delegation phù hợp.

### 1.1. So sánh với Authorization Code

| Khía cạnh | Client Credentials | Authorization Code + PKCE |
|---|---|---|
| Ai khởi tạo? | Service/backend giữ credential. | Client khởi tạo và browser tương tác với người dùng. |
| Người dùng đăng nhập? | Không. | Có trong luồng thông thường. |
| Đi qua Authorization Endpoint? | Không cần. | Có. |
| Có redirect URI/state/PKCE? | Không áp dụng cho grant này. | Có theo yêu cầu bảo mật. |
| Consent của người dùng? | Không có. | Có thể cần. |
| Xác thực client? | **Bắt buộc**, dùng cơ chế được AS hỗ trợ. | Confidential client phải xác thực; public client có cơ chế riêng. |
| Token thể hiện? | Quyền của client/service. | Quyền gắn với authorization có người dùng. |
| Refresh token? | RFC 6749 mục 4.4.3 khuyến nghị **SHOULD NOT** cấp. | Có thể có theo chính sách. |

`client_credentials` không phải luồng OIDC xác thực người dùng và **không phát ID Token theo grant OAuth2 tiêu chuẩn**. Không đưa `openid`, `nonce`, `response_type=code`, `redirect_uri` hoặc `code_verifier` vào request để biến nó thành login.

## 2. Các vai trò và điều kiện cần

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Confidential Client | Giữ credential, gửi token request, bảo vệ và dùng access token. | `inventory-worker` |
| Authorization Server | Xác thực client, kiểm grant/scope, cấp token, quản lý khóa và metadata. | `auth.example.com` |
| `RegisteredClientRepository` | Lưu client ID, phương thức xác thực, grant, scope, token policy. | `inventory-worker` với `inventory.read` |
| Token Endpoint | Xử lý POST theo OAuth2 `client_credentials`. | `/oauth2/token` |
| Resource Server | Xác minh token và cấp quyền cho API. | `inventory-api.example.com` |

Một luồng hợp lệ cần khớp những điều sau:

1. Client ID đã được đăng ký; chỉ **một** phương thức client authentication được chấp nhận cho request.
2. Client có grant `AuthorizationGrantType.CLIENT_CREDENTIALS` và credential đúng.
3. Token Endpoint đúng host, path, HTTPS và content type.
4. Scope yêu cầu được đăng ký và phù hợp policy. Audience được phát hành đúng cho API đích.
5. Authorization Server có khả năng phát access token, ví dụ cấu hình signing keys/JWKS cho JWT hoặc storage/introspection cho opaque token.
6. Resource Server tin issuer, xác minh token và áp dụng quyền.

**Client ID không tự là credential bí mật.** Người biết `client_id` không được nhận token khi chưa cung cấp phương thức xác thực hợp lệ. Không cho public client `ClientAuthenticationMethod.NONE` dùng Client Credentials chỉ vì nó có client ID.

## 3. Cấu hình `RegisteredClient` trong Spring Authorization Server

Spring Authorization Server biểu diễn client bằng `RegisteredClient`, lưu qua `RegisteredClientRepository`. Đối với M2M, khai báo `CLIENT_CREDENTIALS` cùng auth method và scope cụ thể.

### 3.1. Ví dụ đăng ký client bằng HTTP Basic

```java
package com.example.authserver.config;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

@Configuration(proxyBeanMethods = false)
class InventoryClientRegistrationConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder,
            @Value("${INVENTORY_WORKER_SECRET}") String rawSecret) {

        RegisteredClient inventoryWorker = RegisteredClient
                .withId("inventory-worker-v1")
                .clientId("inventory-worker")
                .clientName("Inventory Worker")
                .clientSecret(passwordEncoder.encode(rawSecret))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("inventory.read")
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(inventoryWorker);
    }
}
```

Đoạn code **chỉ minh họa đăng ký một client**. Ứng dụng hoàn chỉnh cần SecurityFilterChain cho Authorization Server, issuer, token generator/khóa ký, repository và persistence phù hợp, cùng các Bean/framework dependencies. `INVENTORY_WORKER_SECRET` phải lấy từ nguồn bí mật ngoài source code và được tạo với entropy đủ cao.

| Cấu hình | Mục đích |
|---|---|
| `withId("inventory-worker-v1")` | ID nội bộ của registration; ổn định nếu dùng DB. |
| `clientId("inventory-worker")` | Giá trị client gửi tới Token Endpoint. |
| `clientSecret(passwordEncoder.encode(...))` | Lưu hash của secret để xác minh khi nhận credential. |
| `CLIENT_SECRET_BASIC` | Cho phép xác thực client bằng HTTP Basic. |
| `CLIENT_CREDENTIALS` | Cấp quyền sử dụng M2M grant. |
| `scope("inventory.read")` | Giới hạn quyền có thể yêu cầu. |
| `accessTokenTimeToLive(5 phút)` | Giới hạn vòng đời access token để giảm tác động khi bị lộ. |

**Không thêm `redirectUri(...)`, `requireProofKey(true)` hay `requireAuthorizationConsent(true)` chỉ vì muốn “an toàn hơn” cho grant này:** không có browser, authorization code hoặc người dùng consent trong Client Credentials. Bảo mật phải tập trung vào client authentication, scope/audience, token lifecycle, TLS và Resource Server.

`InMemoryRegisteredClientRepository` phù hợp demo/kiểm thử, không nên là kho client production. Dùng `JdbcRegisteredClientRepository` hoặc một triển khai persistence bền vững đã kiểm soát migration, client ownership, approval, rotation, quyền truy cập và backup. Với nhiều replica, tất cả instance phải nhìn thấy cùng registration và token policy.

### 3.2. Có thể đăng ký nhiều scope nhưng xin ít quyền hơn

Một client được đăng ký:

```java
.scope("inventory.read")
.scope("inventory.write")
```

Có thể chỉ xin `inventory.read` cho tác vụ đọc. Authorization Server phải từ chối yêu cầu vượt phạm vi cho phép hoặc áp dụng chính sách giảm quyền; Resource Server tiếp tục quyết định quyền trên từng API. Tránh đăng ký scope rộng chỉ để “đỡ phải cấu hình”.

Không dùng chung một client secret cho nhiều service. Credential theo từng workload giúp audit, rotation, thu hồi và giới hạn ảnh hưởng khi một hệ thống bị lộ.

## 4. Gửi HTTP POST yêu cầu cấp token

Theo RFC 6749 mục 4.4.2, Client Credentials Token Request cần:

- HTTP **POST** tới Token Endpoint.
- Body mã hóa `application/x-www-form-urlencoded` bằng UTF-8.
- `grant_type=client_credentials` **bắt buộc**.
- `scope` **tùy chọn**; quyền mặc định khi bỏ qua tùy chính sách server, không được giả định là tất cả scope.
- Client authentication bắt buộc, ví dụ `client_secret_basic`, `private_key_jwt` hoặc mTLS theo registration.

### 4.1. Raw request với Basic

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic [BASE64_ENCODED_CREDENTIALS]
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=inventory.read
```

Phần `[BASE64_ENCODED_CREDENTIALS]` chỉ là placeholder. Theo RFC 6749 mục 2.3.1, client ID và secret phải được xử lý mã hóa form theo quy tắc OAuth2 trước khi ghép làm chuỗi Basic; sử dụng OAuth2 client SDK giúp tránh lỗi với ký tự đặc biệt. **Basic Base64 không phải mã hóa bí mật**: cần HTTPS/TLS đúng chứng chỉ và không log `Authorization` header.

Khi dùng HTTP Basic, không đồng thời gửi `client_secret` trong form body; dùng hai phương thức client authentication trong cùng request là request không hợp lệ.

### 4.2. Thử bằng cURL an toàn hơn

Ví dụ Bash dưới đây cho phép cURL **hỏi mật khẩu tương tác**; không viết secret trực tiếp vào lệnh:

```bash
export M2M_CLIENT_ID="inventory-worker"
export M2M_TOKEN_URI="https://auth.example.com/oauth2/token"

curl --request POST \
  --url "$M2M_TOKEN_URI" \
  --user "$M2M_CLIENT_ID" \
  --header "Accept: application/json" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=inventory.read"
```

Trên PowerShell/Windows dùng `curl.exe` (PowerShell 5.1 thường có alias `curl`):

```powershell
$env:M2M_CLIENT_ID = "inventory-worker"
$env:M2M_TOKEN_URI = "https://auth.example.com/oauth2/token"
curl.exe --request POST --url "$env:M2M_TOKEN_URI" --user "$env:M2M_CLIENT_ID" --header "Accept: application/json" --data-urlencode "grant_type=client_credentials" --data-urlencode "scope=inventory.read"
```

Lệnh với `--user` chỉ chứa username thường yêu cầu nhập password khi chạy. Trên CI, dùng secret injection và HTTP/OAuth2 client an toàn, tránh khiến secret xuất hiện trong command line, shell history, process list hoặc output logs. Không dùng `--insecure` để bỏ TLS certificate validation.

`--data-urlencode` bảo đảm body có dạng form-urlencoded. Nếu scope gồm nhiều giá trị, gửi `scope=inventory.read inventory.write` dưới dạng **một** chuỗi phân tách bằng dấu cách, được encode đúng.

### 4.3. Phương thức xác thực khác

| Phương thức | Credential ở đâu? | Khi nào dùng? |
|---|---|---|
| `client_secret_basic` | HTTP Basic `Authorization` header. | M2M có shared secret, TLS và bảo vệ secrets tốt. |
| `client_secret_post` | Form body `client_id` + `client_secret`. | Chỉ khi client được đăng ký phương thức này; rủi ro body logging cần kiểm soát. |
| `private_key_jwt` | JWT client assertion do client ký. | Khi muốn dùng cặp khóa và quản trị rotation/identity mạnh hơn shared secret. |
| `client_secret_jwt` | JWT assertion được xác minh bằng shared secret. | Khi hệ thống hỗ trợ rõ và có chính sách cho JWT assertion. |
| `tls_client_auth` / `self_signed_tls_client_auth` | Chứng chỉ client mTLS. | Môi trường có PKI và hạ tầng TLS mutual authentication. |
| `none` | Không có credential bảo mật. | Public client ở grant phù hợp; **không dùng để bỏ xác thực cho Client Credentials**. |

JWT assertion phải được kiểm chữ ký, audience, thời hạn, issuer/subject và replay protection khi áp dụng. Với mTLS kết thúc ở proxy, phải ràng buộc thông tin chứng chỉ với **proxy tin cậy**, không chấp nhận header chứng chỉ tự khai báo từ Internet.

Không có `redirect_uri`, `code`, `state`, `code_verifier`, `nonce` hay bước `/oauth2/authorize` trong grant tiêu chuẩn. Nếu có tham số `resource` theo RFC 8707, nó chỉ có ý nghĩa khi Authorization Server **thực sự triển khai extension** và kiểm soát resource indicator/audience tương ứng.

## 5. Access token response và vòng đời token

Khi client hợp lệ, grant và scope được chấp nhận, Token Endpoint phát access token:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
```

| Trường | Ý nghĩa | Cách dùng |
|---|---|---|
| `access_token` | Credential tạm thời dùng gọi API. | Giữ kín; không ghi log, không trả ra UI. |
| `token_type` | Thường là `Bearer` với thiết kế phổ biến. | Gửi `Authorization: Bearer token` tới Resource Server. |
| `expires_in` | Số giây tới thời điểm hết hạn; 300 giây trong ví dụ. | Chủ động xin token mới trước khi hết hạn một khoảng đệm. |
| `scope` | Scope cuối cùng được cấp, khi response có trường này. | Không giả định server đã cấp tất cả scope đã xin. |
| `refresh_token` | RFC 6749 mục 4.4.3 quy định **SHOULD NOT** cấp cho client_credentials. | Không thiết kế worker phải có refresh token. |

Client Credentials khi access token hết hạn sẽ **gửi request Client Credentials mới**, tự xác thực lại bằng credential hợp lệ. Điều này khác refresh token grant. Thực hành tốt là tái sử dụng token còn hạn và cấp lại khi cần, tránh gọi Token Endpoint mỗi lần gọi API.

### 5.1. Token đại diện cho client, không phải người dùng

`inventory-worker` được xác thực là application/service. Nếu token dùng JWT có `sub`, cách biểu diễn principal phụ thuộc token profile và cấu hình issuer; trong nhiều hệ thống nó là client ID. **Đừng suy diễn `sub` này là một người dùng đã đăng nhập.**

Resource Server phải phân biệt machine principal với human principal khi nghiệp vụ yêu cầu. API “xem hồ sơ cá nhân hiện tại” không được cho token M2M tự nhận một user bất kỳ để truy cập.

### 5.2. Scope khác audience

- Scope `inventory.read` diễn tả hành động được cho phép.
- Audience `inventory-api` hoặc URI API diễn tả **đích nhận token**.
- Issuer `https://auth.example.com` diễn tả nhà phát hành tin cậy.

Access token có đúng chữ ký và scope nhưng **sai `aud`** vẫn phải bị API đích từ chối khi áp dụng JWT access token profile. Resource Server dùng `issuer-uri` để khám phá metadata/JWKS và xác minh issuer, nhưng cần cấu hình validation **audience** cho API của mình; không mặc định chỉ đặt `issuer-uri` là đã xong.

Spring Authorization Server có khả năng tùy biến claims qua token customizer và những extension phù hợp. Việc đặt `resource` trong token request hoặc cấu hình một custom property **không tự bảo đảm** framework mặc định tạo audience đúng nếu không có implementation/chính sách kiểm tra tương ứng.

### 5.3. JWT hay opaque token?

| Định dạng | Kiểm chứng tại Resource Server | Lưu ý |
|---|---|---|
| JWT self-contained | Chữ ký/public JWKS, `iss`, `aud`, `exp`, scope, token type và policy. | Revocation không tự có hiệu lực tức thời khi API xác minh offline. |
| Opaque token | Introspection/kiểm tra trạng thái qua kênh tin cậy. | Cần timeout, cache và độ sẵn sàng của Authorization Server. |

Không coi một token là “đáng tin” vì client có thể Base64-decode hoặc đọc được JWT payload. Resource Server mới phải làm validation mật mã và chính sách.

## 6. Gửi access token đến Resource Server

Sau khi nhận token, client gọi API:

```http
GET /inventory HTTP/1.1
Host: inventory-api.example.com
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

Resource Server cần kiểm tra:

1. Chữ ký JWT/JWKS hoặc introspection và nguồn issuer tin cậy.
2. Thời hạn `exp`, `nbf` nếu có, token type và khả năng thu hồi theo chính sách.
3. Audience đúng API.
4. Scope `inventory.read` và permission/tenant/đối tượng nghiệp vụ nếu cần.
5. Tách machine token khỏi token người dùng nếu API có cả hai.

Với Spring Security Resource Server JWT, cấu hình khởi đầu:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
```

Ví dụ rule bảo vệ GET:

```java
@Bean
SecurityFilterChain resourceServerChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/inventory/**")
                .hasAuthority("SCOPE_inventory.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()));
    return http.build();
}
```

Đoạn Java rút gọn, chưa có imports và cấu hình `aud` validator. Scope được Spring Security ánh xạ thành authority với tiền tố `SCOPE_` trong cấu hình mặc định phù hợp. Không dựa vào rule scope này để bỏ kiểm tra tenant hoặc phân quyền đối tượng.

## 7. Cấu hình OAuth2 Client ở ứng dụng worker

Gọi token request bằng cURL là cách học giao thức, còn production nên dùng thư viện client được duy trì, nhất là khi cần cache token, retry và xử lý expiry. Spring Security OAuth2 Client dùng `ClientRegistration` (phía ứng dụng gọi API) khác `RegisteredClient` (phía Authorization Server).

### 7.1. Cấu hình trong `application.yml` của worker

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-worker:
            provider: internal-as
            client-id: ${INVENTORY_WORKER_CLIENT_ID}
            client-secret: ${INVENTORY_WORKER_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          internal-as:
            token-uri: https://auth.example.com/oauth2/token
```

Cấu hình này **nằm ở OAuth2 Client/worker**, không đặt vào Spring Authorization Server để thay RegisteredClient. Với grant chỉ cần token endpoint, có thể cấu hình `token-uri` trực tiếp mà không bắt buộc OIDC login/discovery. Host/path phải đúng URL công khai của AS, kể cả khi Token Endpoint đã được tùy chỉnh.

| Authorization Server | OAuth2 Client |
|---|---|
| `RegisteredClientRepository` | `ClientRegistrationRepository` |
| Xác định client được phép dùng auth method/grant/scope nào. | Chọn phương thức gửi credential và xin token. |
| Lưu hash secret hoặc public key/certificate metadata. | Giữ credential gốc trong secret manager/keystore. |
| Cấp access token. | Xin, lưu và sử dụng access token. |

Đừng nhầm `client-secret` ở phía worker với hash secret lưu phía AS. Worker phải có credential đúng, AS kiểm chứng nó bằng hash/key/certificate tương ứng.

### 7.2. Background worker dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`

Trong ứng dụng chạy nền không dựa vào HTTP session người dùng, Spring Security cung cấp manager dành cho service applications:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration(proxyBeanMethods = false)
class MachineToMachineClientConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

`AuthorizedClientServiceOAuth2AuthorizedClientManager` có thể lấy access token bằng grant `client_credentials` và tái cấp khi hết hạn theo `OAuth2AuthorizedClientProvider`. Nó sử dụng `OAuth2AuthorizedClientService` để giữ thông tin authorized client; cần xem xét lifetime/storage của service này trong hệ thống nhiều replica.

### 7.3. Ví dụ service gọi API

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryApiClient {
    private final OAuth2AuthorizedClientManager manager;
    private final RestClient restClient = RestClient.create();

    InventoryApiClient(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String fetchInventory() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-worker")
                .principal("inventory-worker-process")
                .build();

        OAuth2AuthorizedClient authorized = manager.authorize(request);
        if (authorized == null) {
            throw new IllegalStateException("Không thể lấy access token");
        }

        return restClient.get()
                .uri("https://inventory-api.example.com/inventory")
                .headers(headers -> headers.setBearerAuth(
                        authorized.getAccessToken().getTokenValue()))
                .retrieve()
                .body(String.class);
    }
}
```

Giá trị `principal("inventory-worker-process")` là **khóa quản lý authorized client** của tác vụ hệ thống, không đại diện user login. Ví dụ dùng `RestClient.create()` cho ngắn; production nên cấu hình RestClient Bean để quản lý timeout, TLS, metrics và policy URL.

Một số phiên bản Spring Security có `OAuth2ClientHttpRequestInterceptor` cho `RestClient` để tự lấy/gắn Bearer token. Có thể dùng nó khi ứng dụng đã quản lý `ClientRegistration` và `OAuth2AuthorizedClientManager` phù hợp, tránh viết lại logic OAuth bằng tay.

### 7.4. Chính sách tái sử dụng token

Client cần cân bằng giữa giảm tải Token Endpoint và tránh token hết hạn giữa request:

- Tái sử dụng token còn hạn, xin token mới khi gần hết hạn; có buffer chống lệch clock.
- Không refresh bằng `refresh_token` khi grant này không cấp loại token đó.
- Chặn vòng retry vô hạn khi nhận `invalid_client` (thường cần sửa credential/config).
- Backoff có jitter khi AS tạm lỗi; tránh nhiều thread hoặc replica cùng tạo “token storm”.
- Cache được phân tách theo client registration, principal, scope và audience thực sự được triển khai.
- Không log token, không dùng token từ API A để gọi API B nếu audience sai.

## 8. Phân loại lỗi Token Endpoint và Resource Server

| Lỗi | Bản chất | Cách điều tra |
|---|---|---|
| `invalid_client` | Client authentication thất bại: sai secret, unknown client, sai method. | Kiểm tra registration, secret injection, client authentication method, TLS. |
| `unauthorized_client` | Client xác thực hợp lệ nhưng không được phép `client_credentials`. | Kiểm tra `authorizationGrantType` của RegisteredClient. |
| `invalid_scope` | Xin quyền ngoài scope/policy. | Đối chiếu requested scope với registered scopes. |
| `invalid_request` | Body thiếu/sai trường, duplicate parameter hoặc nhiều cơ chế auth. | Xác minh POST form-urlencoded, grant_type, auth method. |
| `unsupported_grant_type` | AS không hỗ trợ grant được gửi. | Kiểm tra server implementation/metadata và request. |
| HTTP 404 ở Token Endpoint | Sai path, context path hoặc gateway rewrite. | Kiểm tra endpoint URL công khai/discovery. |
| HTTP 405 | Gửi method không được phép. | Dùng POST, content type phù hợp. |
| HTTP 401 của Resource Server | Token hết hạn/sai chữ ký/issuer/audience/không gửi token. | Kiểm tra Bearer validation tại API, phân biệt với auth client ở AS. |
| HTTP 403 của Resource Server | Token hợp lệ nhưng thiếu scope/quyền. | Đánh giá token scopes và policy API, không tự cấp rộng quyền. |

Với `client_secret_basic`, khi client cố xác thực qua HTTP Authorization header nhưng sai, RFC 6749 mục 5.2 yêu cầu **HTTP 401** và `WWW-Authenticate` phù hợp. Ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="oauth2-client"
Content-Type: application/json

{"error":"invalid_client"}
```

Không trả thông điệp công khai “client ID X tồn tại, secret đã hết hạn” vì có thể giúp dò registry. Thông tin kỹ thuật chi tiết cần nằm trong audit có kiểm soát, không chứa raw secret/token.

### 8.1. Tách lỗi cấp token khỏi lỗi sử dụng token

Nếu AS đã trả HTTP 200 nhưng Resource Server trả 403, thường là lỗi authorization tại API (scope/role/tenant), không phải `invalid_client`. Nếu Resource Server trả 401, kiểm tra token header, expiry, issuer, audience và JWKS/introspection trước khi kết luận cần rotate secret.

## 9. Kiểm thử Client Credentials

### 9.1. Ma trận kiểm thử

| Request | Kết quả mong đợi |
|---|---|
| Đúng client, secret, grant, scope | 200, access token, token type và expiry phù hợp. |
| Thiếu/sai Basic secret | `invalid_client`; không cấp token. |
| ID client không có thật | `invalid_client`; không tiết lộ trạng thái registry. |
| Client hợp lệ nhưng không đăng ký grant `client_credentials` | `unauthorized_client` hoặc lỗi chuẩn tương ứng; không cấp token. |
| Scope ngoài registration | `invalid_scope` hoặc bị từ chối đúng chính sách; không cấp thêm quyền. |
| Thiếu `grant_type` | `invalid_request`. |
| Gửi GET hoặc JSON | Token Endpoint không xử lý như POST form hợp lệ. |
| Basic và form `client_secret` cùng request | Request bị từ chối theo chuẩn. |
| Public client `none` thử `client_credentials` | Không được cấp token chỉ dựa trên `client_id`. |
| Dùng token read-only tại API yêu cầu write | 403/authorization denied. |
| Sai JWT signature, issuer, audience hoặc expiry | API từ chối token. |
| Rotate client secret | Token mới yêu cầu secret hợp lệ; token cũ có chính sách hiệu lực riêng. |
| Restart/rolling deploy nhiều replica | Registration/keys/token policy nhất quán. |
| Client gửi request token quá thường xuyên | Rate limit/backoff hoạt động, không làm DoS. |

### 9.2. Ví dụ MockMvc kiểm tra sai secret

```java
@SpringBootTest
@AutoConfigureMockMvc
class ClientCredentialsTokenEndpointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidBasicSecretDoesNotReceiveToken() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("inventory-worker", "wrong-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "inventory.read"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_client"));
    }
}
```

Đoạn test giả định context Spring Authorization Server, fixture client đúng, imports JUnit/MockMvc và dependencies đã được cấu hình. Kiểm thử hợp lệ cần dùng secret test đúng để lấy token, xác minh claims/expiry, gọi Resource Server và kiểm tra response; riêng MockMvc test sai secret không chứng minh toàn bộ flow hoạt động.

### 9.3. Các assertion cần có ở happy path

- `access_token`, `token_type=Bearer`, `expires_in` và scope thực tế phù hợp.
- Không phụ thuộc refresh token; với chính sách thông thường không có `refresh_token`.
- JWT/opaque token dùng đúng issuer, audience và machine principal.
- `SCOPE_inventory.read` cho phép GET, không cho phép endpoint `inventory.write`.
- Token chỉ dành cho inventory API không dùng được ở billing API.
- Logs, traces và HTTP dumps không chứa Basic secret, JWT assertion, raw token.
- Token còn hạn có thể tiếp tục xác minh sau rolling deploy/key rotation hợp lệ.
- Khi credential lỗi hoặc signer/KMS không khả dụng, server không phát token giả hoặc fallback secret yếu.

## 10. Bảo mật và vận hành production

### 10.1. Quản lý credential

Client secret/private key/chứng chỉ phải được cấp riêng cho từng workload và môi trường, lưu trong secret manager/KMS/keystore hoặc hạ tầng được kiểm soát. Không commit secret, không nhúng vào image, không gửi trong ticket hỗ trợ và không để trong request query string. Xoay vòng có audit, owner, hạn sử dụng và quy trình xử lý khi lộ.

HTTP Basic dùng Base64 nên không có tính bảo mật riêng; TLS và xác minh hostname/certificate là bắt buộc. Với yêu cầu mạnh, đánh giá `private_key_jwt` hoặc mTLS khi toàn bộ AS, client, gateway và Resource Server hỗ trợ.

### 10.2. Giới hạn rủi ro token

- TTL ngắn và scope tối thiểu.
- Audience dành riêng cho API; Resource Server kiểm tra `aud`.
- Bảo vệ token trong cache/bộ nhớ; không đưa vào browser hoặc dịch vụ khác.
- Theo yêu cầu, đánh giá sender-constrained access token bằng mTLS hoặc DPoP.
- JWT xác minh offline có thể còn hợp lệ tới `exp` khi client secret bị revoke. Cần TTL, introspection, denylist hoặc kiểm soát phiên/token bổ sung nếu phải thu hồi tức thời.
- Đồng bộ key rotation/JWKS và thời gian chồng lấp cho token chưa hết hạn.

### 10.3. Quan sát và hạn chế tải

Giám sát: tỷ lệ request client_credentials, thành công/`invalid_client`, độ trễ Token Endpoint, lỗi DB/KMS, số token cấp theo client category, rate limit và token cache hit rate. Không log secret/access token; dùng request ID và reason category trong hệ thống audit có quyền truy cập giới hạn.

Rate limiting phải tính đến NAT, nhiều replica và khả năng attacker dùng client ID của người khác để làm nghẽn họ. Không để limiter trả khác biệt giúp dò client có tồn tại hay không.

### 10.4. Ảnh hưởng của các thay đổi chính sách

| Thao tác | Request token mới | Token đã phát |
|---|---|---|
| Rotate secret | Secret cũ hết hiệu lực sau khi thay đổi được áp dụng. | Access token có thể còn hợp lệ tới khi hết hạn. |
| Bỏ `client_credentials` | Không cấp token mới với grant đó. | Không tự thu hồi mọi JWT đã cấp. |
| Giảm scope cho client | Grant mới phải theo scope/policy mới. | Token cũ có thể còn claim quyền cũ tới khi bị vô hiệu hóa. |
| Thay signing key | Token mới ký bằng khóa mới theo policy. | Giữ public key cũ trong giai đoạn chồng lấp cần thiết. |
| Đổi issuer/audience | Client và API phải cùng cập nhật trust configuration. | Cần migration, không tắt issuer/audience validator. |

## 11. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| “`client_id` tương đương user ID.” | Client Credentials là danh tính của service, không phải người dùng. |
| “M2M cần đi qua `/oauth2/authorize` và consent.” | Grant này xác thực trực tiếp ở Token Endpoint. |
| “Thêm `openid` sẽ nhận ID Token.” | Không phải OIDC authentication flow tiêu chuẩn. |
| “Không cần secret vì API đã nằm trong VPN.” | Confidential client vẫn phải xác thực theo grant và trust policy. |
| “Client Credentials luôn nhận refresh token.” | RFC 6749 khuyến nghị không cấp refresh token. |
| “Token có đúng scope thì API nào cũng nhận.” | Phải xác minh audience, issuer và các quyền khác. |
| “Base64 Basic là mã hóa an toàn.” | Base64 có thể giải mã, phải dùng TLS và bảo vệ log. |
| “Thay secret sẽ làm token cũ lập tức vô hiệu.” | Access token đã cấp có vòng đời và chính sách revoke riêng. |
| “Nên xin token mới cho mỗi request API.” | Tái sử dụng token còn hạn, quản lý cache và backoff. |
| “Cấu hình `issuer-uri` tự đủ để kiểm audience.” | Resource Server cần xác định và thực thi audience validator theo thiết kế. |

## 12. Bài tập thực hành

**Bối cảnh:** `report-worker` chạy mỗi 10 phút, cần đọc API `https://reports-api.example.com` bằng token từ AS `https://auth.example.com`. Service không đại diện cho người dùng, chỉ có scope `reports.read`.

Thực hiện:

1. Đăng ký `report-worker` là confidential client, `CLIENT_SECRET_BASIC`, `CLIENT_CREDENTIALS`, scope `reports.read`, token TTL khoảng năm phút.
2. Đưa credential vào secret manager/biến môi trường test, lưu hash phía AS.
3. Gửi token request POST form-urlencoded bằng cURL, xác minh response.
4. Thử thiếu credential, secret sai, grant sai, scope `reports.write` chưa đăng ký; ghi lại OAuth error.
5. Cấu hình worker `ClientRegistration` và `AuthorizedClientServiceOAuth2AuthorizedClientManager` với provider `clientCredentials()`.
6. Gọi reports API với Bearer token, xác minh issuer, audience, scope và quyền.
7. Đặt một endpoint yêu cầu `reports.write` và xác minh read-only token bị từ chối.
8. Thử token sai audience hoặc hết hạn, xác minh HTTP 401 tương ứng.
9. Rotate client secret ở staging và kiểm tra yêu cầu cấp token mới; ghi nhận hành vi token đã phát.
10. Kiểm tra log, tracing, CI output và tài liệu API không để lộ secret hoặc token.

**Tiêu chí đạt:** worker tự xin access token với grant Client Credentials và gọi API đúng quyền; request sai bị từ chối; không yêu cầu user login, consent hoặc refresh token.

## 13. Checklist trước khi triển khai

- [ ] Confidential client được đăng ký đúng ID, owner, auth method và grant `client_credentials`.
- [ ] Scope và audience giới hạn theo service/Resource Server cần thiết.
- [ ] Token Endpoint đúng URL, HTTPS; request dùng POST form-urlencoded.
- [ ] Client authentication hoạt động đúng và không cho public client bypass.
- [ ] Secret/private key/certificate được bảo vệ và có rotation.
- [ ] Không đưa redirect URI, state, code, PKCE hoặc login/consent vào grant này.
- [ ] Token response có access token, token type, expiry; client không phụ thuộc refresh token.
- [ ] Resource Server kiểm chữ ký/introspection, issuer, audience, thời hạn, scope và quyền nghiệp vụ.
- [ ] Client tái sử dụng token còn hạn, có buffer, backoff và giới hạn retry.
- [ ] Đã test success, `invalid_client`, `unauthorized_client`, `invalid_scope` và request sai method/body.
- [ ] Đã test sai audience, token hết hạn, sai scope, rollback và rotate credential.
- [ ] Không log Basic header, raw token, client secret, JWT assertion hoặc private key.
- [ ] Có rate limit, audit, monitoring, HA và runbook xử lý sự cố cấp token.

## Tổng kết

Client Credentials Grant là luồng OAuth 2.0 **máy với máy**: confidential client xác thực trực tiếp tại **Token Endpoint**, gửi `grant_type=client_credentials` cùng scope phù hợp và nhận **access token**. Không có Authorization Code, browser, PKCE hay consent của người dùng. RFC 6749 khuyến nghị không cấp refresh token cho grant này.

Với Spring Authorization Server, `RegisteredClient` quy định credential method, grant và scope; với Spring Security OAuth2 Client, `OAuth2AuthorizedClientManager` giúp worker xin và tái sử dụng token. Để vận hành an toàn cần TLS, least privilege, đúng audience, TTL phù hợp, secret rotation, Resource Server validation và kiểm thử cả request hợp lệ lẫn sai.

## Tài liệu tham khảo

1. [RFC 6749, mục 4.4 — Client Credentials Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.4): client authentication, token request, scope và refresh token.
2. [RFC 6749, mục 5.2 — Token Error Response](https://www.rfc-editor.org/rfc/rfc6749#section-5.2): `invalid_client`, `unauthorized_client` và các OAuth2 error code.
3. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `RegisteredClientRepository`, `TokenSettings`.
4. [Spring Authorization Server — Dynamic Client Registration](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): ví dụ Client Credentials registration/request.
5. [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `AuthorizedClientServiceOAuth2AuthorizedClientManager` cho service app.
6. [Spring Security — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): RestClient/WebClient và quản lý token.
7. [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWKS/token validation.
8. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`.
9. [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707): khai báo Resource Server đích khi extension hỗ trợ.
10. [RFC 9068 — JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068): `iss`, `aud` và xác minh access token.

