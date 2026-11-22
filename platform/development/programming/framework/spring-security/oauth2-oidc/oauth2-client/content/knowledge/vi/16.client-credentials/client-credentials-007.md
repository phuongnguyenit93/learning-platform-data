# 16.7. Tái sử dụng token còn hạn và lấy token mới khi hết hạn

## 1. Vì sao Client Credentials cần tái sử dụng access token?

Trong **Spring Security OAuth 2.0/OIDC Client**, ứng dụng backend có thể cần gọi một API được bảo vệ mà không có người dùng đang đăng nhập. Ví dụ:

- Một inventory service gọi API kiểm tra tồn kho.
- Một billing worker gọi API đối soát.
- Một scheduled job đồng bộ dữ liệu với hệ thống đối tác.
- Một backend-for-backend integration gọi API nội bộ bằng quyền đã được cấp cho chính ứng dụng.

Những tình huống này thường sử dụng **OAuth 2.0 Client Credentials Grant**. Client chứng minh danh tính với Authorization Server (AS) rồi được cấp một **access token** dùng để gọi Resource Server (API).

Một cách triển khai không hợp lý là **gọi Token Endpoint trước mọi API request**:

```text
Request API #1 -> POST /token -> access token -> GET /inventory
Request API #2 -> POST /token -> access token -> GET /inventory
Request API #3 -> POST /token -> access token -> GET /inventory
...
```

Nếu access token có thời hạn 30 phút, những token requests liên tiếp như trên thường là dư thừa. Chúng làm tăng độ trễ, tải của Authorization Server, số connection ra ngoài và nguy cơ gặp rate limiting.

Cách hợp lý hơn:

```text
Lần gọi đầu:
    Chưa có token
    -> POST /token
    -> nhận access token AT1
    -> lưu OAuth2AuthorizedClient
    -> dùng AT1 gọi API

Các lần tiếp theo khi AT1 còn hạn:
    -> tìm lại OAuth2AuthorizedClient
    -> dùng AT1 gọi API
    -> không POST /token

Khi AT1 hết hạn hoặc gần hết hạn:
    -> POST /token bằng client_credentials
    -> nhận access token AT2
    -> thay authorized client đã lưu
    -> dùng AT2 gọi API
```

Trong Spring Security, cách này có thể được thực hiện thông qua **`OAuth2AuthorizedClientManager`** và **`ClientCredentialsOAuth2AuthorizedClientProvider`**, kết hợp một **`OAuth2AuthorizedClientService`** để giữ token giữa các lần gọi.

**Ý tưởng cốt lõi:** _Không phải tự viết một biến `static String accessToken`_. Hãy để các thành phần OAuth2 Client của Spring Security quản lý token, thời hạn, client registration, principal và nơi lưu.

### Mục tiêu bài học

Sau bài học, bạn sẽ:

1. Hiểu sự khác nhau giữa **tái sử dụng access token** và **gửi token request mới**.
2. Biết vì sao Client Credentials thường không sử dụng refresh token.
3. Hiểu các lớp `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientService`, `OAuth2AuthorizedClientProvider` và `OAuth2AuthorizedClientManager`.
4. Nắm cách Spring Security quyết định token còn hạn hay cần cấp lại, bao gồm `expiresAt` và `clockSkew`.
5. Cấu hình `AuthorizedClientServiceOAuth2AuthorizedClientManager` cho ứng dụng backend và scheduled job.
6. Thực hiện các ví dụ Java sử dụng token để gọi API.
7. Hiểu khóa lưu token gồm **`registrationId` và `principalName`**.
8. So sánh lưu token InMemory, JDBC và nơi lưu phân tán.
9. Nhận diện vấn đề đồng thời khi nhiều luồng hoặc nhiều instance cùng xin token.
10. Xử lý lỗi, bảo mật credentials và tránh tái sử dụng token sai audience/scope.

Trong ví dụ, các URL, ID, secret và giá trị token đều là dữ liệu minh họa.

## 2. Client Credentials Grant: token dành cho ứng dụng, không phải người dùng

Client Credentials Grant được định nghĩa trong OAuth 2.0. Một **confidential client** chứng minh danh tính của chính nó với AS để lấy access token theo quyền đã đăng ký.

Sơ đồ:

```mermaid
sequenceDiagram
    autonumber
    participant C as Spring Boot Service
    participant AS as Authorization Server
    participant API as Resource Server

    C->>AS: POST /token: grant_type=client_credentials + client authentication
    AS-->>C: access_token, token_type, expires_in
    C->>API: Authorization: Bearer access_token
    API-->>C: Dữ liệu
```

Ví dụ token request:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.net
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=client_credentials&scope=inventory.read
```

Một token response điển hình:

```json
{
  "access_token": "ACCESS_TOKEN_EXAMPLE",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "inventory.read"
}
```

Các trường:

| Trường | Ý nghĩa |
|---|---|
| `access_token` | Credential gửi tới API được bảo vệ. |
| `token_type` | Cách sử dụng token, thường là `Bearer`. |
| `expires_in` | Số giây token có hiệu lực kể từ thời điểm cấp theo hợp đồng AS. |
| `scope` | Quyền được cấp cho token. |
| `refresh_token` | **Thông thường không được cấp** với Client Credentials Grant. |

Theo OAuth 2.0, phản hồi Client Credentials **không nên bao gồm refresh token**. Khi access token hết hạn, client thường **thực hiện lại Client Credentials Grant** để nhận token mới.

Đây là sự khác biệt quan trọng:

```text
Authorization Code / User Delegation:
    access token hết hạn
    -> có thể dùng refresh token nếu AS cấp và còn hợp lệ

Client Credentials:
    access token hết hạn
    -> gọi lại grant_type=client_credentials
    -> chứng minh lại client identity với AS
```

Không nên thêm `refresh_token` vào token request của Client Credentials chỉ vì thấy phương thức `refreshToken()` trong Spring Security.

### 2.1. Có OIDC ID Token không?

Mặc dù module này đề cập **OAuth 2.0/OIDC Client**, Client Credentials Grant không phải cơ chế OIDC Login của một người dùng. Không có bước browser login, không có End-User consent trong flow này và không nên chờ một ID Token để xác nhận người dùng.

Access token Client Credentials thường biểu diễn quyền của **client/service**. Tùy AS, token có thể ở dạng JWT hoặc opaque. Client không được mặc định giải mã JWT để suy ra một người dùng đang đăng nhập.

## 3. Vì sao không cần xin token mới cho từng request?

Access token thường được cấp cùng thời hạn nhất định. Một token còn hiệu lực có thể được dùng nhiều lần, trong phạm vi chính sách của Authorization Server và Resource Server.

Ví dụ:

```text
10:00:00 -> Token Endpoint cấp AT1, expires_in = 1800 giây
10:00:03 -> Gọi API lần 1 bằng AT1
10:00:20 -> Gọi API lần 2 bằng AT1
10:02:10 -> Gọi API lần 3 bằng AT1
10:15:00 -> Gọi API lần 4 bằng AT1

Nếu không có yêu cầu cấp lại sớm:
10:30:00 -> AT1 hết hạn
```

Mỗi lần gọi API **không cần một access token khác** nếu token hiện tại vẫn đủ điều kiện sử dụng.

Lợi ích:

- Giảm số request tới Authorization Server.
- Giảm latency cho API calls thông thường.
- Giảm khả năng bị giới hạn tốc độ phát hành token.
- Giảm kết nối TLS/client authentication lặp lại.
- Giảm tải cho AS khi có lượng request lớn.
- Cho phép ứng dụng hoạt động tạm thời với access token còn hạn ngay cả khi Token Endpoint gặp lỗi ngắn hạn, **nếu API vẫn chấp nhận token đó**.

Tuy nhiên, **tái sử dụng không có nghĩa dùng token vô hạn**. Khi token hết hạn, bị revoke, sai audience/scope hoặc không còn được Resource Server chấp nhận, việc có token trong memory/database không khiến token trở lại hợp lệ.

## 4. OAuth2AuthorizedClient: đối tượng lưu access token

Spring Security biểu diễn authorization của một client thông qua:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
```

Nó chứa thông tin chính:

```text
OAuth2AuthorizedClient
    |
    +-- ClientRegistration
    |       registrationId
    |       authorizationGrantType
    |       tokenUri
    |       clientId
    |
    +-- principalName
    |
    +-- OAuth2AccessToken
    |       tokenValue
    |       issuedAt
    |       expiresAt
    |       scopes
    |
    +-- OAuth2RefreshToken (nếu được cấp)
```

Với Client Credentials, `getRefreshToken()` thông thường là `null`.

Ví dụ đọc metadata **mà không lộ credential**:

```java
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

void inspect(OAuth2AuthorizedClient authorizedClient) {
    String registrationId = authorizedClient
        .getClientRegistration()
        .getRegistrationId();

    String principalName = authorizedClient.getPrincipalName();

    OAuth2AccessToken token = authorizedClient.getAccessToken();

    Instant issuedAt = token.getIssuedAt();
    Instant expiresAt = token.getExpiresAt();

    // Chỉ dùng metadata phục vụ quan sát.
    // Không in token.getTokenValue() ra log.
}
```

`issuedAt` và `expiresAt` được Spring Security xây dựng từ dữ liệu token response/metadata liên quan. Chúng có thể được dùng để xác định token cần cấp lại.

### 4.1. Authorized Client khác ClientRegistration

| `ClientRegistration` | `OAuth2AuthorizedClient` |
|---|---|
| Cấu hình client và provider. | Authorization/token đã cấp cho client và principal. |
| Chứa client ID, token URI, grant type, scope yêu cầu. | Chứa access token và thời hạn, có thể có refresh token. |
| Thường được khai báo qua YAML/code. | Sinh ra sau khi authorization thành công. |
| Tìm bằng `registrationId`. | Thường lưu theo `registrationId` + `principalName`. |
| Không phải kho lưu access token. | Là object đại diện dữ liệu cần được cache/persist. |

Nếu bạn chỉ có `ClientRegistrationRepository`, ứng dụng biết **cách xin token** nhưng chưa có nơi lưu token đã được cấp. Vì vậy cần thêm authorized client service/repository và manager phù hợp.

## 5. Các thành phần điều phối việc tái sử dụng token

Spring Security cung cấp các lớp:

| Thành phần | Vai trò |
|---|---|
| `ClientRegistrationRepository` | Đọc cấu hình client/provider. |
| `OAuth2AuthorizedClientService` | Lưu và truy xuất authorized client giữa các lần gọi. |
| `OAuth2AuthorizedClientManager` | Điều phối việc tìm token hiện tại và authorize/re-authorize. |
| `OAuth2AuthorizedClientProvider` | Quyết định có cần/được phép cấp token theo một grant. |
| `ClientCredentialsOAuth2AuthorizedClientProvider` | Chiến lược dành cho Client Credentials Grant. |
| `OAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>` | Gửi token request tới AS và đọc phản hồi. |

Một sơ đồ đúng vai trò:

```mermaid
flowchart TD
    A["Ứng dụng cần gọi API"] --> B["OAuth2AuthorizedClientManager.authorize()"]
    B --> C["OAuth2AuthorizedClientService.loadAuthorizedClient()"]
    C --> D{"Có token đã lưu?"}
    D -->|Không| E["ClientCredentialsOAuth2AuthorizedClientProvider"]
    D -->|Có| E
    E --> F{"Token có cần cấp lại?"}
    F -->|"Không: còn hạn"| G["Provider trả null"]
    G --> H["Manager trả authorized client hiện tại"]
    F -->|"Có: chưa có hoặc sắp hết hạn"| I["POST /token bằng client_credentials"]
    I --> J["Nhận access token mới"]
    J --> K["Manager lưu authorized client mới"]
    K --> L["Trả authorized client mới"]
    H --> M["Ứng dụng gọi API"]
    L --> M
```

Sơ đồ là mô tả hành vi khái niệm, không phải toàn bộ implementation source code của một version Spring Security. Điểm quan trọng là **manager kết hợp nơi lưu và provider**, nên ứng dụng không tự phải kiểm tra token theo mỗi request nếu dùng API này đúng cách.

## 6. `ClientCredentialsOAuth2AuthorizedClientProvider` quyết định lúc nào lấy token mới

Implementation dành cho Client Credentials:

```java
org.springframework.security.oauth2.client.ClientCredentialsOAuth2AuthorizedClientProvider
```

Nó thực thi hợp đồng:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider
```

với phương thức:

```java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizationContext context
);
```

### 6.1. Các nhánh chính

Giả sử context chứa `ClientRegistration` có grant type `client_credentials`:

1. **Chưa có authorized client:** gọi Token Endpoint để xin access token mới.
2. **Đã có authorized client và access token còn đủ hạn:** provider không cần authorize lại; thường trả `null`.
3. **Access token hết hạn hoặc gần hết hạn:** thực hiện Client Credentials Grant mới để lấy token khác.
4. **Grant type của registration không phải `client_credentials`:** provider không áp dụng, trả `null`.
5. **Token request gặp lỗi:** ném exception hoặc chuyển lỗi theo Spring Security; không tự trả một token giả.

Đặc biệt, khi provider trả `null` vì token hiện tại còn hợp lệ, **manager có thể trả lại authorized client đã được tìm thấy trước đó**. Không nên hiểu `null` từ provider là phải bỏ token đang có.

### 6.2. Pseudocode minh họa

Đoạn sau chỉ là **mô hình hóa ý tưởng**, không phải mã nội bộ Spring Security:

```java
OAuth2AuthorizedClient existing =
    authorizedClientService.loadAuthorizedClient(
        registrationId, principalName
    );

OAuth2AuthorizedClient replacement =
    clientCredentialsProvider.authorize(
        contextContaining(registration, principal, existing)
    );

if (replacement != null) {
    authorizedClientService.saveAuthorizedClient(
        replacement, principal
    );
    return replacement;
}

return existing;
```

Ứng dụng thực tế nên gọi `OAuth2AuthorizedClientManager.authorize(...)`, không tự mô phỏng manager bằng pseudocode này. Manager có các quy tắc riêng về ngữ cảnh, success/failure handlers và lưu trữ.

### 6.3. Provider không chủ động chạy theo lịch

Thông thường, token không tự được lấy lại đúng khoảnh khắc `expiresAt` khi ứng dụng không làm gì cả. Provider được kích hoạt khi **manager được yêu cầu authorize**, chẳng hạn trước khi backend gọi API.

Nói cách khác:

```text
Token hết hạn lúc 10:30.
Không có request nào lúc 10:30 -> thường chưa gọi /token.

Request gọi API lúc 10:41
    -> manager nhận thấy token cũ đã hết hạn
    -> lấy token mới ngay lúc này
    -> dùng token mới cho API.
```

Đó là cơ chế **lấy token mới theo nhu cầu (on-demand)**, không mặc định là scheduled refresh.

## 7. `expiresAt` và `clockSkew`: không nên đợi đến giây cuối

Một request được gửi trước khi token hết hạn không bảo đảm API nhận/kiểm tra nó khi token vẫn còn hạn. Chẳng hạn token còn 5 giây nhưng network latency, retry hoặc queueing làm API nhận muộn.

Spring Security cung cấp **clock skew** để coi token là “cần cấp lại” sớm hơn một khoảng.

Ví dụ:

```text
Token AT1:
    issuedAt = 10:00:00
    expiresAt = 10:30:00

clockSkew = 60 giây

Ngưỡng xem là cần cấp lại:
    10:29:00
```

Dòng thời gian:

| Thời điểm | Còn bao lâu đến `expiresAt`? | Cách xử lý minh họa với skew 60s |
|---|---:|---|
| 10:10:00 | 20 phút | Reuse AT1. |
| 10:25:00 | 5 phút | Reuse AT1. |
| 10:28:59 | 61 giây | Thường vẫn có thể reuse. |
| 10:29:10 | 50 giây | Chủ động xin token mới. |
| 10:30:01 | Đã hết hạn | Bắt buộc không tiếp tục dùng AT1 theo expiry. |

Cách tính ở đây mang tính khái niệm:

```text
token cần cấp lại nếu:
    now >= expiresAt - clockSkew
```

Chi tiết biên thời gian do provider triển khai, nên không dùng bảng minh họa làm tài liệu xác định từng mili-giây.

### 7.1. Clock skew giải quyết điều gì?

- Giảm rủi ro token hết hạn giữa lúc gửi và xử lý API request.
- Bù một phần sai lệch thời gian nhỏ giữa client và AS.
- Giúp ứng dụng chủ động xin token mới khi token sắp hết hạn.

### 7.2. Clock skew không làm gì?

- Không gia hạn access token cũ.
- Không chứng minh token chưa bị revoke.
- Không tự sửa JWT có sai audience/scope.
- Không bảo đảm token endpoint luôn khả dụng.
- Không thay thế việc đồng bộ đồng hồ hệ thống.

Skew quá lớn có thể khiến client xin token liên tục, nhất là khi AS cấp token sống rất ngắn. Skew quá nhỏ có thể khiến API nhận token sát thời điểm hết hạn. Hãy chọn dựa trên token lifetime, p95/p99 network latency và đồng hồ của hạ tầng.

## 8. Cấu hình Spring Boot cho Client Credentials Grant

Ví dụ Spring Boot 3.x Servlet application có các dependencies Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Với Spring Boot 4.x, tên starters được khuyến nghị tương ứng có thể là `spring-boot-starter-webmvc` và `spring-boot-starter-security-oauth2-client`; cần dùng BOM/plugin cùng một dòng phiên bản.

### 8.1. `application.yml`

Giả sử service gọi `https://inventory.example.net/v1/items`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: corporate-as
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          corporate-as:
            token-uri: https://auth.example.net/oauth2/token
```

Giải thích:

- `registrationId = inventory-service`: khóa chọn cấu hình trong Spring Security.
- `client-id` và `client-secret`: credentials do AS cấp, giữ bí mật ở backend.
- `client-authentication-method: client_secret_basic`: client xác thực với AS theo phương thức đã đăng ký.
- `authorization-grant-type: client_credentials`: không yêu cầu browser/redirect URI.
- `scope`: các phạm vi client yêu cầu; token thực tế được cấp theo policy AS.
- `token-uri`: nơi client gửi grant request.

**Không cần `redirect-uri` hoặc `oauth2Login()` để thực hiện Client Credentials Grant** trong scheduled/backend service-only use case.

Có thể dùng metadata/discovery của provider nếu phù hợp, nhưng ví dụ dùng `token-uri` tường minh để tập trung vào cơ chế tái sử dụng token.

### 8.2. Không để client secret trong repository

Dùng secret manager, environment variables hoặc secret injection do nền tảng triển khai cung cấp. Không hardcode `INVENTORY_CLIENT_SECRET` vào Java, không commit vào YAML và không log header Basic Authentication.

Nếu AS yêu cầu `private_key_jwt` hoặc mTLS thay cho client secret, đăng ký client và cấu hình token HTTP client phải phản ánh đúng phương thức đó. Cơ chế cache token không thay thế client authentication.

## 9. Cấu hình `OAuth2AuthorizedClientService` để giữ token

Một backend không cần HTTP session có thể dùng:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
```

Các implementation phổ biến:

- `InMemoryOAuth2AuthorizedClientService`: lưu trong RAM của application instance.
- `JdbcOAuth2AuthorizedClientService`: lưu trong cơ sở dữ liệu thông qua JDBC.
- Custom service: lưu qua kho riêng như database, token vault hoặc một distributed store được kiểm soát.

Để minh họa, dùng InMemory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {

        return new InMemoryOAuth2AuthorizedClientService(registrations);
    }
}
```

Lưu ý: đây là bean của ứng dụng minh họa, **không phải yêu cầu phải tự tạo nếu Spring Boot đã cấu hình phù hợp**. Khi tạo custom bean, hãy chắc rằng manager dùng chính bean đó.

### 9.1. Token được lưu theo khóa nào?

Thông thường:

```text
(clientRegistrationId, principalName)
```

Ví dụ:

```text
("inventory-service", "inventory-backend")
    -> OAuth2AuthorizedClient chứa AT1

("billing-service", "billing-backend")
    -> OAuth2AuthorizedClient chứa AT2
```

**`principalName` quan trọng ngay cả với Client Credentials Grant.** Nó là khóa logic để quản lý authorized client, không có nghĩa token được cấp cho một người dùng thật.

Nếu mỗi lần gọi manager bạn dùng một principal khác nhau, Spring Security có thể không tìm thấy authorized client đã lưu và phải xin token mới liên tục.

## 10. Dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`

Đối với service-to-service hoặc scheduled job **không có Servlet HTTP request**, dùng:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

Nó được thiết kế để làm việc với:

- `ClientRegistrationRepository`.
- `OAuth2AuthorizedClientService`.
- `OAuth2AuthorizedClientProvider`.

Ví dụ cấu hình đầy đủ:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ClientCredentialsManagerConfig {

    @Bean("inventoryAuthorizedClientManager")
    OAuth2AuthorizedClientManager inventoryAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(clientCredentials -> clientCredentials
                    .clockSkew(Duration.ofSeconds(60))
                )
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                service
            );

        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
```

Trong cấu hình này:

1. Manager được tạo **một lần** dưới dạng Spring bean.
2. Manager lấy registration theo `registrationId`.
3. Manager tra `OAuth2AuthorizedClientService` trước khi quyết định cần token mới.
4. Provider `clientCredentials` chỉ xin token nếu chưa có hoặc token hiện tại cần cấp lại.
5. Thành công thì manager lưu authorized client mới thông qua service và success handling.
6. Các lần gọi sau tra cùng service và principal name để tái sử dụng token.

`Duration.ofSeconds(60)` chỉ là ví dụ **clock skew**, không phải yêu cầu cố định cho mọi token.

### 10.1. Vì sao không dùng `DefaultOAuth2AuthorizedClientManager` cho mọi trường hợp?

`DefaultOAuth2AuthorizedClientManager` thuộc **Servlet web request context**, thường kết hợp `OAuth2AuthorizedClientRepository` và có thể cần `HttpServletRequest`/`HttpServletResponse`.

Trong scheduled job hoặc worker không có HTTP request, `AuthorizedClientServiceOAuth2AuthorizedClientManager` phù hợp hơn vì nó làm việc trực tiếp với authorized client service.

So sánh:

| Nhu cầu | Manager phù hợp |
|---|---|
| MVC web request có principal/session và authorized client repository | `DefaultOAuth2AuthorizedClientManager` |
| Scheduled job, worker, backend service không có Servlet request | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| WebFlux reactive application | Reactive authorized client managers tương ứng |

Từng manager cần provider và storage được cấu hình cho đúng use case.

## 11. Lấy access token trước khi gọi API

Khi ứng dụng muốn gọi API, nó tạo một `OAuth2AuthorizeRequest` với registration ID và **principal name ổn định**:

```java
OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-service")
        .principal("inventory-backend")
        .build();
```

Sau đó:

```java
OAuth2AuthorizedClient authorizedClient =
    manager.authorize(authorizeRequest);
```

- Lần đầu: manager có thể gọi Token Endpoint và lưu token.
- Lần sau khi token còn đủ hạn: manager tìm token đã lưu và trả lại.
- Khi token cần cấp lại: manager gọi Token Endpoint, lưu kết quả mới rồi trả nó.

### 11.1. Service Java lấy token một cách có kiểm soát

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class InventoryAccessTokenService {

    private static final String REGISTRATION_ID = "inventory-service";
    private static final String PRINCIPAL_NAME = "inventory-backend";

    private final OAuth2AuthorizedClientManager manager;

    public InventoryAccessTokenService(
            @Qualifier("inventoryAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String currentAccessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(PRINCIPAL_NAME)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "Unable to authorize inventory-service"
            );
        }

        return client.getAccessToken().getTokenValue();
    }
}
```

`getTokenValue()` được sử dụng **trong backend** để gửi tới API đã được tin cậy. Không ghi nó vào log hoặc trả cho browser không cần thiết. Trong ứng dụng thật, có thể giới hạn thêm cách nhận token chỉ dành cho một gateway client, thay vì để mọi controller tùy ý lấy token.

### 11.2. Tại sao `principal("inventory-backend")` phải ổn định?

Vì authorized client service thường tra dữ liệu theo:

```text
("inventory-service", "inventory-backend")
```

Nếu mỗi lần gọi lại tạo một principal ngẫu nhiên:

```java
// Sai khi mục tiêu là dùng chung authorization của cùng một service.
.principal(java.util.UUID.randomUUID().toString())
```

thì mỗi lần manager có thể tra **một khóa khác**, không tìm thấy token cũ và xin token mới không cần thiết.

Ngược lại, dùng cùng một principal name cho những tenants/clients **không được phép chia sẻ quyền** cũng nguy hiểm. Stable key phải có **ý nghĩa bảo mật đúng với loại authorization**, không chỉ giúp cache hit.

## 12. Dùng token để gọi REST API trong backend

Với Spring Framework có `RestClient` (ví dụ Boot 3.2+), có thể tạo gateway:

```java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private final RestClient api;
    private final InventoryAccessTokenService tokenService;

    public InventoryGateway(
            RestClient.Builder restClientBuilder,
            InventoryAccessTokenService tokenService) {

        this.api = restClientBuilder
            .baseUrl("https://inventory.example.net")
            .build();

        this.tokenService = tokenService;
    }

    public StockResponse getStock(String sku) {
        String accessToken = tokenService.currentAccessToken();

        return api.get()
            .uri("/v1/stocks/{sku}", sku)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(StockResponse.class);
    }

    public record StockResponse(String sku, int available) {
    }
}
```

Các lớp `InventoryAccessTokenService`, `InventoryGateway` và các beans ở phần trên thuộc cùng ứng dụng minh họa.

Ý nghĩa:

1. `InventoryGateway` không biết client secret.
2. Khi cần gọi API, gateway yêu cầu token qua manager.
3. Manager quyết định dùng token đã có hay xin token mới.
4. API request gửi `Authorization: Bearer ...`.
5. JSON API response được ánh xạ về DTO `StockResponse`.

**Không hardcode access token** trong `RestClient`. Token phải được quản lý theo vòng đời, không phải biến cấu hình cố định.

### 12.1. Có cần gọi manager trước mọi API request?

Có thể. Đây là cách đơn giản, vì manager/service kiểm tra trạng thái authorized client và thường **không gọi Token Endpoint** nếu token còn đủ hạn.

Tuy nhiên, việc gọi manager có thể bao gồm lookup vào database hoặc store khác. Với tải rất lớn, cần đo latency và cân nhắc cơ chế lưu trữ/cache phù hợp. Không thay manager bằng một `static String token` chỉ để giảm một bước lookup mà đánh mất kiểm tra thời hạn và chính sách.

### 12.2. Có thể dùng interceptor tự động gắn Bearer token không?

Có. Các phiên bản Spring Security hiện đại có tích hợp OAuth2 Client với `RestClient`/`WebClient` và interceptors/filters phù hợp. Cách này giúp tự động lấy authorized client và thêm Bearer token.

Dù dùng interceptor hay code gateway minh họa, **cơ chế tái sử dụng vẫn phụ thuộc vào manager, provider và nơi lưu authorized client**. Interceptor không phải Authorization Server và không tự thay thế hết hạn token nếu manager/store bị cấu hình sai.

Khi dùng phiên bản khác nhau, kiểm tra tài liệu Spring Security tương ứng về tên interceptor/filter và cách chọn registration ID/principal.

## 13. Diễn biến lần đầu, lần thứ hai và sau khi token hết hạn

Giả sử `expires_in = 1800` giây và `clockSkew = 60` giây.

### 13.1. Lần đầu: chưa có authorized client

```text
Thời điểm: 09:00:00

InventoryGateway.getStock("SKU-01")
    |
    v
manager.authorize(registration=inventory-service,
                  principal=inventory-backend)
    |
    v
OAuth2AuthorizedClientService.load(...)
    -> null
    |
    v
ClientCredentialsOAuth2AuthorizedClientProvider
    -> POST /oauth2/token
    -> nhận AT1 (expiresAt=09:30:00)
    |
    v
Manager lưu OAuth2AuthorizedClient chứa AT1
    |
    v
Gateway gọi API bằng AT1
```

### 13.2. Lần thứ hai: token vẫn còn hạn

```text
Thời điểm: 09:05:00

Gateway yêu cầu token
    |
    v
Service tìm thấy AT1
    |
    v
Provider kiểm tra thời hạn:
    09:05:00 < 09:29:00
    -> chưa cần cấp lại
    -> trả null
    |
    v
Manager trả lại authorized client hiện có
    |
    v
Gateway gọi API bằng AT1
```

**Không có `POST /token` mới** trong nhánh reuse thành công.

### 13.3. Lần thứ ba: token sắp hết hạn

```text
Thời điểm: 09:29:20

Gateway yêu cầu token
    |
    v
Service tìm thấy AT1
    |
    v
Provider thấy token trong cửa sổ clockSkew
    -> yêu cầu token mới
    |
    v
POST /oauth2/token grant_type=client_credentials
    -> AS trả AT2 (expiresAt=09:59:20)
    |
    v
Manager cập nhật store với AT2
    |
    v
Gateway gọi API bằng AT2
```

Từ đó các API requests tiếp tục dùng AT2 cho đến khi gần hết hạn.

### 13.4. Sequence diagram tổng hợp

```mermaid
sequenceDiagram
    autonumber
    participant API as InventoryGateway
    participant M as AuthorizedClientManager
    participant S as OAuth2AuthorizedClientService
    participant P as ClientCredentialsProvider
    participant AS as Authorization Server
    participant RS as Resource Server

    API->>M: authorize(registrationId, stablePrincipal)
    M->>S: loadAuthorizedClient
    S-->>M: null
    M->>P: authorize(context)
    P->>AS: POST /token client_credentials
    AS-->>P: AT1, expires_in
    P-->>M: OAuth2AuthorizedClient(AT1)
    M->>S: saveAuthorizedClient(AT1)
    M-->>API: AT1
    API->>RS: GET resource with AT1
    RS-->>API: 200

    Note over API,M: Gọi API lần kế tiếp, AT1 còn hạn
    API->>M: authorize(registrationId, samePrincipal)
    M->>S: loadAuthorizedClient
    S-->>M: AT1
    M->>P: authorize(context with AT1)
    P-->>M: null - chưa cần cấp token mới
    M-->>API: AT1
    API->>RS: GET resource with AT1
    RS-->>API: 200

    Note over API,M: Lần sau, AT1 gần hết hạn
    API->>M: authorize(registrationId, samePrincipal)
    M->>S: loadAuthorizedClient
    S-->>M: AT1
    M->>P: authorize(context with AT1)
    P->>AS: POST /token client_credentials
    AS-->>P: AT2, expires_in
    P-->>M: OAuth2AuthorizedClient(AT2)
    M->>S: saveAuthorizedClient(AT2)
    M-->>API: AT2
```

## 14. Tái sử dụng token không đồng nghĩa refresh token

Thuật ngữ “refresh access token” thường được dùng theo nghĩa rộng, nhưng cần phân biệt **grant protocol**:

| Hành động | Token Endpoint request | Điều kiện |
|---|---|---|
| **Reuse token còn hạn** | Không gửi request | Authorized client chứa access token có thể tiếp tục sử dụng. |
| **Client Credentials lấy token mới** | `grant_type=client_credentials` | Chưa có token hoặc token cần cấp lại. |
| **Refresh Token Grant** | `grant_type=refresh_token` | Có refresh token được cấp và được AS chấp nhận. |
| **Authorization Code Grant mới** | Browser authorize rồi `grant_type=authorization_code` | Cần user authorization mới hoặc chưa có token. |

Với Client Credentials, grant mới sử dụng **client authentication** để xin token, không phụ thuộc vào một refresh token cũ.

Vì vậy builder thường chỉ cần:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

**Không cần `.refreshToken()` để Client Credentials tự lấy token mới khi hết hạn.** Thêm refresh provider vào một manager có nhiều grants có thể hợp lý trong ứng dụng khác, nhưng nó không biến Client Credentials thành Refresh Token Grant.

## 15. Vì sao không nên tự cache bằng biến static?

Cách không nên dùng:

```java
public final class BadTokenHolder {

    public static String accessToken;

    // Không lưu expiresAt, principal, client registration, audience...
}
```

Rủi ro:

1. Không biết token hết hạn khi nào.
2. Không có cơ chế clock skew.
3. Không phân biệt token của những registrations khác nhau.
4. Không phân biệt tenant hay quyền truy cập.
5. Có thể gửi token của API A sang API B.
6. Khó xử lý concurrency khi nhiều threads cùng cập nhật biến.
7. Không có lifecycle/cleanup an toàn.
8. Không tự tích hợp token errors và success/failure handlers.
9. Không có persistence qua restart nếu đó là yêu cầu.
10. Khó chuyển từ InMemory sang shared store mà không viết lại mọi nơi gọi API.

Một biến static có thể tạo cảm giác caching hoạt động trong demo nhỏ, nhưng dễ phá ranh giới an toàn khi hệ thống phát triển.

**Thay thế:** dùng `OAuth2AuthorizedClientManager` cùng `OAuth2AuthorizedClientService`/repository, và chọn key đúng.

## 16. Khi cache hit nhưng API vẫn trả 401 hoặc 403

Manager có thể thấy token **chưa tới `expiresAt`**, nhưng Resource Server vẫn từ chối token.

Một số nguyên nhân:

- Token đã bị revoke từ Authorization Server.
- API yêu cầu một audience khác.
- API yêu cầu scope chưa được cấp.
- JWT signature/issuer sai theo policy Resource Server.
- API và AS có sai lệch đồng hồ quá lớn.
- Client dùng token của registration sai.
- Token được cấp hợp lệ nhưng không đủ business authorization.

Phân biệt:

| Phản hồi | Ý nghĩa thường gặp |
|---|---|
| HTTP 401 `invalid_token` | Token thiếu/không hợp lệ/hết hạn theo Resource Server. |
| HTTP 403 `insufficient_scope` | Token có thể hợp lệ nhưng không có scope cần thiết. |
| HTTP 403 do policy API | Token có thể hợp lệ nhưng caller không có quyền với tài nguyên cụ thể. |
| HTTP 429 từ Token Endpoint | AS rate limit cấp token. |
| HTTP 400 `invalid_client` | Client authentication với AS không thành công. |
| HTTP 400 `invalid_scope` | Scope yêu cầu không được chấp nhận. |

**Không tự retry vô hạn** khi API trả 401 bằng cách xin token mới liên tục. Nếu audience/scope/config sai, token mới vẫn sai và có thể làm quá tải AS.

Tùy hợp đồng API, ứng dụng có thể:

1. Xác định 401 có thực sự do token bị hết hạn/revoke không.
2. Xóa authorized client tương ứng nếu policy cho phép.
3. Thực hiện một lần re-authorize có giới hạn rồi retry API nếu HTTP operation an toàn/idempotent hoặc có cơ chế idempotency.
4. Nếu vẫn lỗi, báo lỗi đúng nguyên nhân thay vì che bằng một token khác.

Với POST tạo giao dịch, retry API cần đánh giá **idempotency**: API có thể đã xử lý request trước khi response bị mất. Không áp chính sách retry chung cho mọi operation.

## 17. Đúng khóa cache: registration ID và principal name

`OAuth2AuthorizedClientService` thường lưu theo:

```text
clientRegistrationId + principalName
```

Ví dụ:

| `registrationId` | `principalName` | Authorized client |
|---|---|---|
| `inventory-service` | `inventory-backend` | Token cho inventory API. |
| `billing-service` | `billing-backend` | Token cho billing API. |
| `inventory-service` | `inventory-tenant-a` | Token riêng cho tenant A, nếu authorization được thiết kế như vậy. |
| `inventory-service` | `inventory-tenant-b` | Token riêng cho tenant B, nếu authorization được thiết kế như vậy. |

### 17.1. Những hành vi làm mất khả năng reuse

Không nên:

```java
.principal("request-" + UUID.randomUUID())
```

Không nên tạo một manager/store mới cho mỗi API request:

```java
// Minh họa anti-pattern:
OAuth2AuthorizedClientService service =
    new InMemoryOAuth2AuthorizedClientService(registrations);

// Nếu làm lại trong mỗi request, token vừa lưu lập tức mất
// khỏi góc nhìn của request kế tiếp.
```

Hãy dùng singleton beans hoặc store dùng chung theo kiến trúc.

### 17.2. Cẩn thận với `principalName` trong Client Credentials

Trong Client Credentials, principal name trong API manager có thể là một tên service ổn định. Nó **không phải user login** và không chứng minh token mang quyền của user.

Không dùng tên user thật thay cho service principal nếu mục tiêu là dùng chung một client authorization, vì ứng dụng sẽ tạo nhiều entries và gọi AS không cần thiết. Nhưng cũng không gộp những authorizations thuộc tenants/quyền tách biệt vào một tên service nếu AS yêu cầu isolation.

### 17.3. Token khác scope/audience không được reuse tùy ý

Giả sử:

```text
Token A:
    scope = inventory.read
    audience = inventory-api

Token B cần:
    scope = billing.write
    audience = billing-api
```

Không dùng Token A để gọi billing API chỉ vì nó chưa hết hạn. Cơ chế cache key `registrationId`/`principalName` cần phù hợp với **client registration, scope, audience và tenant** mà ứng dụng đang sử dụng.

Nếu một provider hỗ trợ tham số `resource`/`audience` khác nhau trong token request, phải thiết kế phân tách registrations hoặc custom authorized client storage/key rõ ràng. Không chèn audience khác vào token request nhưng vẫn dùng cùng một cache entry rồi giả định manager sẽ biết mọi biến thể.

## 18. InMemory: tái sử dụng trong một application instance

`InMemoryOAuth2AuthorizedClientService` thường phù hợp cho:

- Demos và thực hành học tập.
- Backend chạy một instance.
- Tác vụ đơn giản có thể xin token mới sau restart.
- Môi trường test không cần persistent token storage.

Ví dụ:

```text
Process A:
    ("inventory-service", "inventory-backend") -> AT1
    AT1 reuse trong mọi request được xử lý bởi process A.

Process restart:
    InMemory store trống.
    Lần gọi sau sẽ POST /token để lấy AT2.
```

**Mất cache không nhất thiết làm hỏng chức năng** nếu Token Endpoint hoạt động và client credentials vẫn hợp lệ; nhưng nó làm tăng token requests và có thể gây “burst” sau deploy/restart nhiều instances.

### 18.1. InMemory không phải cache toàn cluster

Nếu backend có 3 pods:

```text
Pod A: AT1
Pod B: AT2
Pod C: AT3
```

Mỗi pod có thể tự xin token và reuse trong bộ nhớ riêng. Đây không nhất thiết là lỗi nhưng có thể gây dư thừa cấp token khi nhiều pods cùng khởi động.

Nếu hệ thống cần một authorization cache chia sẻ, phải cân nhắc persistent/shared store và tính đồng thời. Không chỉ tạo một bean InMemory rồi kỳ vọng nó tự đồng bộ qua mạng.

## 19. JDBC và nơi lưu bền vững

Spring Security có:

```java
org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService
```

Có thể cấu hình khi muốn tokens tồn tại qua restart hoặc chia sẻ giữa instances.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class PersistentTokenStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcOperations jdbc,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbc,
            registrations
        );
    }
}
```

Đoạn cấu hình này **thay thế** bean InMemory cùng kiểu ở mục trước, không định nghĩa cả hai mà không có qualifier/selection policy.

Ứng dụng cần database schema phù hợp với **phiên bản Spring Security** đang dùng. Các cột thường bao gồm:

```text
oauth2_authorized_client
    client_registration_id
    principal_name
    access_token_value
    access_token_issued_at
    access_token_expires_at
    access_token_scopes
    refresh_token_value
    ...
```

Với Client Credentials, refresh token thường không xuất hiện, nhưng schema vẫn có thể hỗ trợ nhiều grant types.

### 19.1. Khi nào nên chọn JDBC?

- Nhiều nodes cần nhìn thấy cùng một authorized client.
- Muốn giảm token requests sau restart/deploy.
- Có quy định audit/retention token.
- Cần một nơi lưu được quản trị riêng với process memory.
- Có chính sách chia sẻ token giữa workloads đã được xác định.

Tuy nhiên, **shared database không tự giải quyết việc hai requests cùng xin token mới**. Vấn đề concurrency được giải thích ở phần sau.

### 19.2. Token storage phải được bảo vệ

Access token là credential. Với JDBC/custom store, cần xem xét:

- TLS trên kết nối database.
- Encryption at rest và, nếu threat model yêu cầu, mã hóa ở tầng ứng dụng/cột.
- Quyền đọc/ghi tối thiểu cho database account.
- Không log SQL bind parameters chứa access token.
- Bảo vệ backups, exports, replicas và snapshots.
- Quy tắc xóa token hết hạn hoặc bị revoke.
- Quản trị key/secret rotation.
- Isolation giữa tenants và services.

Không nên coi một bảng chứa token plaintext là an toàn chỉ vì database nằm trong private subnet.

## 20. Nhiều request đồng thời: tránh “thundering herd” tại Token Endpoint

Một rủi ro quan trọng xuất hiện khi hàng trăm requests tới cùng lúc và token vừa hết hạn:

```text
12:00:00 - AT1 hết hạn

Thread 1 -> Load AT1 -> hết hạn -> POST /token
Thread 2 -> Load AT1 -> hết hạn -> POST /token
Thread 3 -> Load AT1 -> hết hạn -> POST /token
...
Thread 50 -> Load AT1 -> hết hạn -> POST /token
```

Dù service lưu một authorized client theo key, **không được giả định mọi bước load-check-POST-save được đồng bộ hóa toàn cục**. Với nhiều threads hoặc nhiều instances, có thể phát sinh nhiều token requests đồng thời.

### 20.1. Tác động

- Authorization Server chịu spike tải.
- Token endpoint rate limit và trả HTTP 429.
- Nhiều token được cấp gần như cùng lúc cho một client.
- Các nodes có thể lưu token mới khác nhau theo thứ tự response.
- Gia tăng kết nối, CPU và latency.
- Nếu AS áp chính sách giới hạn số token còn hiệu lực, các token phát hành nhiều lần có thể tương tác không mong muốn với policy đó.

Client Credentials tokens thường không gặp refresh token rotation giống Refresh Token Grant, nhưng **vẫn có nguy cơ token request storm**.

### 20.2. Các chiến lược giảm tải

Có thể cân nhắc:

1. Reuse authorized client từ một store ổn định.
2. Đặt **clock skew** hợp lý để không đợi đến giây hết hạn.
3. Dùng connection pooling và timeout phù hợp.
4. Giới hạn concurrency token acquisition theo **`registrationId` + `principalName`**.
5. Với một node, dùng cơ chế **single-flight** cho các requests cùng key.
6. Với nhiều nodes, dùng distributed locking hoặc shared coordination nếu thật sự cần.
7. Sau khi lấy lock, **đọc lại store** trước khi xin token mới, vì node khác có thể đã cập nhật.
8. Giới hạn retries/backoff cho lỗi tạm thời và HTTP 429 theo hợp đồng AS.
9. Tránh tạo manager/service mới trên mỗi request.
10. Quan sát số lần cấp token so với số lần gọi API.

### 20.3. Vì sao “double-check sau lock” quan trọng?

Ví dụ:

```text
Node A: Thấy AT1 hết hạn
Node B: Thấy AT1 hết hạn

Node A lấy distributed lock
    -> load lại AT1
    -> POST /token, nhận AT2
    -> lưu AT2
    -> nhả lock

Node B lấy lock
    -> phải load lại store
    -> thấy AT2 còn hạn
    -> reuse AT2, không POST /token
```

Nếu Node B không đọc lại store sau khi lấy lock, nó có thể xin thêm AT3 không cần thiết.

### 20.4. Không lock mọi API call vô điều kiện

Một lock phân tán trên tất cả các lần gọi API có thể trở thành nút thắt và làm tăng latency. Thông thường chỉ cần coordination khi token **chưa có hoặc cần cấp lại**. Với token còn hạn, đa số requests nên sử dụng token đã lưu một cách nhanh chóng.

Cách tích hợp lock cụ thể phụ thuộc kiến trúc và không nên làm mất success/failure handling của manager. Nếu viết wrapper, phải bảo đảm nó vẫn dùng manager/provider và store đúng cách.

## 21. Quy tắc clock skew và token lifetime rất ngắn

Giả sử AS cấp token với `expires_in = 30` giây nhưng cấu hình `clockSkew = 60` giây.

Ứng dụng có thể xem token là gần hết hạn **ngay khi nhận** hoặc rất sớm, khiến gần như mỗi API call đều xin token mới.

Bảng minh họa:

| Token lifetime | Clock skew | Nhận định |
|---:|---:|---|
| 60 phút | 60 giây | Khoảng đệm thường không đáng kể so với lifetime. |
| 10 phút | 60 giây | Có thể phù hợp, tùy latency. |
| 2 phút | 60 giây | Cần cân nhắc vì 50% lifetime bị coi là gần hết hạn. |
| 30 giây | 60 giây | Có thể gây cấp token lại liên tục. |
| 10 phút | 0 giây | Có nguy cơ token hết hạn trong thời gian API xử lý. |

**Không có giá trị skew đúng cho mọi hệ thống.** Hãy đánh giá theo lifetime AS cấp, độ trễ cấp token, độ trễ API, clock sync và tần suất request.

### 21.1. Nếu Token Endpoint không trả `expires_in`?

Đây là trường hợp phụ thuộc hợp đồng Authorization Server. Spring Security thường dựa vào token response/metadata để xây thông tin thời hạn của access token.

Nếu provider không công bố thời hạn đáng tin, không nên tự giả định token sống vô hạn. Cần làm rõ contract với AS hoặc dùng token response conversion phù hợp theo chuẩn/provider, rồi thiết lập chính sách cache an toàn.

### 21.2. Nếu access token là JWT, có nên tự parse `exp` để quyết định reuse?

Thông thường không cần. `OAuth2AuthorizedClient` đã có thời điểm hết hạn mà Spring Security sử dụng trong token lifecycle. Một access token **không nhất thiết là JWT**; nhiều provider dùng opaque tokens.

Tự giải mã JWT mà không có hợp đồng hoặc cơ chế validation dễ làm client phụ thuộc vào định dạng không ổn định của token dành cho Resource Server.

## 22. Cơ chế lỗi: không lấy token mới bằng mọi giá

Các lỗi có thể xảy ra ở nhiều tầng khác nhau:

| Tầng | Ví dụ lỗi | Hướng xử lý |
|---|---|---|
| ClientRegistration | Sai `registrationId`, thiếu token URI | Sửa cấu hình client/provider. |
| Client authentication | HTTP 400 `invalid_client` | Kiểm tra client ID/secret, method, mTLS hoặc JWT assertion. |
| Scope | HTTP 400 `invalid_scope` | Yêu cầu scope mà AS đã cấp cho client. |
| Token Endpoint | Connect/read timeout, TLS/PKIX | Kiểm tra network, proxy, truststore và HTTP transport. |
| Token Endpoint | HTTP 429 | Tôn trọng rate limit, backoff có giới hạn, tránh thundering herd. |
| Token Endpoint | HTTP 500/503 | Giảm retries, quan sát AS outage; không loop vô hạn. |
| Resource Server | HTTP 401 | Token invalid/expired/revoked, issuer/audience sai. |
| Resource Server | HTTP 403 | Scope/quyền nghiệp vụ không đủ. |
| Storage | JDBC/Redis không truy cập được | Xem availability của authorized client store. |

### 22.1. Còn token hợp lệ trong cache khi AS outage

Nếu AT1 **còn hạn và API chấp nhận**, ứng dụng thường có thể tiếp tục gọi API bằng AT1 mà không cần Token Endpoint. Đây là một lợi ích của reuse.

Nếu AT1 hết hạn, không dùng nó vô thời hạn chỉ để bỏ qua AS outage. Resource Server có thể từ chối; việc gửi token hết hạn làm giảm tính đúng đắn và tạo thêm lỗi downstream.

### 22.2. Không tự retry liên tục khi `invalid_client`

`invalid_client` thường là lỗi cấu hình hoặc credential, không phải lỗi tải tạm thời. Nếu client secret đã rotate nhưng ứng dụng chưa cập nhật, mỗi lần retry chỉ gửi lại credential sai.

Cần cập nhật bí mật, đảm bảo token client dùng đúng phương thức xác thực, và làm việc với AS theo chính sách rotation.

### 22.3. Retry phải có giới hạn

Với Client Credentials, retry token request có thể khả thi hơn Authorization Code Grant vì không có authorization code dùng một lần. Tuy nhiên:

- Một timeout không chứng minh AS chưa cấp token.
- Retry bừa bãi có thể gây ra nhiều token hợp lệ.
- Đặt số lần retry và backoff phù hợp.
- Phân biệt `invalid_client`/`invalid_scope` với timeout/503.
- Khi nhận 429, tôn trọng policy/rate-limit headers đáng tin nếu provider cung cấp.
- Không retry API operation không idempotent chỉ vì đã xin được token mới.

## 23. Tự động dùng token với WebClient/RestClient

Ứng dụng hiện đại thường không muốn viết thủ công:

```java
String accessToken = service.currentAccessToken();
headers.setBearerAuth(accessToken);
```

ở mọi API call. Spring Security cung cấp các cơ chế tích hợp OAuth2 Client với HTTP client. Tên class và API cụ thể khác nhau theo phiên bản và stack:

- Servlet ứng dụng sử dụng `RestClient` có thể dùng OAuth2 client request interceptors phù hợp.
- WebFlux ứng dụng sử dụng `WebClient` có thể dùng OAuth2 authorized client exchange filters.
- Backend jobs có thể dùng service manager chuyên biệt và principal name ổn định.

Điểm cốt lõi không đổi:

```text
API HTTP client
    |
    v
OAuth2AuthorizedClientManager
    |
    v
ClientCredentials provider + AuthorizedClientService
    |
    +-- Còn token? -> reuse
    |
    +-- Cần token? -> POST /token
    |
    v
HTTP request gửi Bearer access token
```

Nếu sử dụng integration tự động, cần cấu hình **đúng registration ID và principal**, không vô tình lấy token của user đang đăng nhập khi muốn token của service hoặc ngược lại.

### 23.1. Spring WebFlux/reactive

Trong một ứng dụng WebFlux, sử dụng những API reactive tương ứng, ví dụ:

```text
ReactiveOAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientProviderBuilder
ReactiveOAuth2AuthorizedClientService
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

Ý nghĩa vẫn tương tự:

- Reuse authorized client nếu token còn hạn.
- Xin token mới bằng Client Credentials nếu chưa có hoặc cần cấp lại.
- Dùng `Mono`/reactive pipeline thay vì blocking calls.
- Không chặn Reactor event loop bằng `RestTemplate` hoặc `block()` trong request processing.

Đừng trộn Servlet `OAuth2AuthorizedClientManager` với reactive manager mà không thiết kế rõ ràng.

## 24. Vòng đời token trong nhiều môi trường triển khai

### 24.1. Một instance, token trong RAM

```text
Service A
    |
    +-- InMemory authorized client service
            |
            +-- AT1 -> API calls reuse AT1
```

Ứng dụng restart thì store bị mất, lần gọi API tiếp theo xin token mới.

### 24.2. Nhiều instances, mỗi instance có InMemory

```text
Pod A -> token AT1
Pod B -> token AT2
Pod C -> token AT3
```

Mỗi pod có thể cache token riêng. Đây là lựa chọn hợp lệ trong một số hệ thống nếu AS cho phép và không yêu cầu chia sẻ, nhưng cần đo số token requests.

### 24.3. Nhiều instances, shared authorized client service

```text
Pod A \
Pod B  ---> JDBC / distributed store ---> AT1
Pod C /
```

Các nodes có thể cùng thấy authorized client. Tuy nhiên, cache lookup và token replacement vẫn có khả năng race; cần concurrency control khi AS/rate limits yêu cầu.

### 24.4. Khi nào không cần persistence?

Nếu token cấp nhanh, lifetime dài, số pods ít và AS không bị rate limit đáng kể, InMemory có thể đáp ứng. Không cần thêm JDBC chỉ vì “caching phải dùng database”.

Nếu cần giữ authorization qua restart, chia sẻ giữa nodes, audit hoặc nhiều hệ thống dùng chung credential, persistent store có thể phù hợp hơn — với điều kiện bảo mật và lifecycle được quản trị.

## 25. Phân biệt reuse token với caching API response

Hai loại cache khác nhau:

| Loại cache | Lưu gì? | Hết hạn theo gì? |
|---|---|---|
| OAuth2 Authorized Client cache | Access token, metadata và có thể refresh token. | OAuth2 token lifetime và policy cấp lại. |
| Business/API response cache | Dữ liệu như danh sách sản phẩm, giá, tồn kho. | TTL/ETag/business freshness của API. |

Một access token còn hạn không có nghĩa response tồn kho từ 10 phút trước vẫn còn chính xác. Và một API response còn trong cache không có nghĩa được phép dùng token cũ để gọi API khác.

Tránh trộn token cache với business cache trong cùng key/value mà không có lifecycle và security boundaries rõ ràng.

## 26. Quan sát hiệu quả tái sử dụng token

Muốn biết cấu hình có hoạt động hiệu quả, nên đo:

- Số API requests cần token.
- Số lần manager authorize được gọi.
- Số token requests thực sự được gửi tới AS.
- Tỷ lệ reuse token so với cấp token mới.
- Thời gian token endpoint phản hồi.
- Số lần token endpoint trả 429/500/503.
- Số lỗi client authentication.
- Số API 401/403.
- Số lần cache miss sau restart hoặc deploy.
- Số token requests trùng nhau theo một registration trong cùng khoảng thời gian.

Ví dụ:

```text
Trong 10 phút:
    API requests: 15.000
    Token Endpoint POSTs: 3
    Số service instances: 3
    Token lifetime: 30 phút
```

Đây có thể là hành vi hợp lý nếu mỗi instance xin một token và reuse. Nếu có **15.000 token requests cho 15.000 API calls**, cần kiểm tra key, service lifecycle và manager wiring.

### 26.1. Những gì có thể ghi log

Có thể ghi:

```text
registrationId=inventory-service
grantType=client_credentials
action=token_acquired / token_reused
tokenExpiresAt=...
httpStatus=200
elapsedMs=...
```

Không ghi:

```text
access_token
client_secret
client_assertion
Authorization header
mTLS private key
```

Không đưa token vào span tags, analytics hoặc SQL logs. Nếu cần correlation, dùng request ID ngẫu nhiên và metadata không nhạy cảm.

## 27. Lỗi thường gặp khi tái sử dụng token

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi lần gọi API đều POST `/token` | Principal name thay đổi, store được tạo lại mỗi request hoặc skew quá lớn | Giữ principal ổn định, dùng singleton manager/store, kiểm tra skew. |
| Token vẫn được dùng sau khi hết hạn | Tự cache token bằng biến String, không dùng manager/provider | Dùng OAuth2AuthorizedClientManager và expiresAt/clockSkew. |
| Token mất sau restart | InMemory store | Chấp nhận cache miss hoặc dùng persistent store. |
| Token không share giữa pods | InMemory ở mỗi node | Dùng shared service nếu thật sự cần. |
| Nhiều POST `/token` cùng thời điểm | Các requests đồng thời thấy token hết hạn | Single-flight/lock theo key, re-read store. |
| API 401 dù token chưa hết hạn | Token revoke, issuer/audience/scope sai | Kiểm tra Resource Server validation. |
| API 403 | Thiếu scope/quyền | Kiểm tra AS registration và API policy. |
| Token Endpoint 400 `invalid_client` | Secret/mTLS/assertion sai | Sửa client authentication. |
| Token Endpoint 400 `invalid_scope` | Scope không được cấp cho client | Sửa requested scopes. |
| Token Endpoint 429 | Xin token quá nhiều | Cải thiện reuse, hạn chế concurrency, backoff. |
| Token Endpoint timeout | Proxy, TLS, network hoặc AS chậm | Cấu hình HTTP transport, timeout, TLS đúng. |
| Manager trả `null` | Registration/provider/context không cho authorize như mong đợi | Kiểm tra provider chain, registration ID và manager. |
| Không có request HTTP nhưng manager yêu cầu Servlet context | Dùng sai manager cho background service | Dùng AuthorizedClientServiceOAuth2AuthorizedClientManager. |
| Token inventory được gửi sang billing API | Chọn sai registration/HTTP client | Tách registrations, audience và resource boundaries. |
| Đã thêm `.refreshToken()` nhưng Client Credentials vẫn POST `/token` | Grant không dựa vào refresh token | Đây là cơ chế đúng: xin access token mới bằng client credentials. |
| Refresh token field là null | Client Credentials thường không cấp refresh token | Không coi là lỗi. |
| Token được coi là gần hết hạn ngay sau khi cấp | Token lifetime ngắn hơn/equal clock skew | Điều chỉnh skew theo lifetime. |
| Không lấy được token mới sau secret rotation | Ứng dụng còn giữ credential cũ | Reload secrets/transport theo policy. |

### 27.1. Quy trình khoanh vùng

Nếu ứng dụng liên tục xin token mới:

1. Kiểm tra `registrationId` có cố định và đúng không.
2. Kiểm tra `principalName` có ổn định qua các lần gọi không.
3. Kiểm tra manager và authorized client service có phải singleton/shared beans hợp lý không.
4. Kiểm tra `loadAuthorizedClient()` có tìm được authorized client vừa lưu không.
5. Kiểm tra `expiresAt` từ token response và `clockSkew`.
6. Kiểm tra AS có thực sự trả `expires_in`/lifetime phù hợp không.
7. Kiểm tra một custom handler/provider có luôn xóa hoặc ghi đè token không.
8. Nếu nhiều instances, kiểm tra store có dùng chung hoặc chỉ InMemory theo node.
9. Kiểm tra số requests đồng thời ngay lúc token hết hạn.
10. Phân biệt lỗi token endpoint và Resource Server trước khi thay đổi configuration.

Không cần log token value để trả lời những câu hỏi này.

## 28. Bài tập tư duy

### Bài tập 1 — Lần đầu chưa có token

Một backend có `registrationId = inventory-service`, `principalName = inventory-backend`, service chưa lưu authorized client.

**Hỏi:** Manager có thể làm gì?

**Đáp án:** Provider Client Credentials gửi token request tới AS, nhận access token, manager lưu một `OAuth2AuthorizedClient` rồi trả nó cho ứng dụng.

### Bài tập 2 — Token còn hạn

Sau 5 phút, ứng dụng gọi API lại. Token còn 25 phút, clock skew 60 giây.

**Hỏi:** Có cần POST `/token` không?

**Đáp án:** Không. Provider thường không cần cấp lại; manager có thể trả authorized client đã lưu.

### Bài tập 3 — Token còn 20 giây

Token còn 20 giây, skew 60 giây.

**Hỏi:** Manager có thể làm gì?

**Đáp án:** Xem token là gần hết hạn và xin token mới bằng `client_credentials`.

### Bài tập 4 — Không có refresh token

Token response Client Credentials không có `refresh_token`.

**Hỏi:** Có phải AS bị lỗi không?

**Đáp án:** Không. Với Client Credentials, refresh token thường không được cấp; lấy token mới bằng chính Client Credentials Grant.

### Bài tập 5 — Principal luôn thay đổi

Code dùng `.principal(UUID.randomUUID().toString())`.

**Hỏi:** Vì sao mỗi request có thể xin token mới?

**Đáp án:** Manager tra authorized client theo registration ID và principal name; principal khác tạo key khác, không reuse entry cũ.

### Bài tập 6 — Ba pods dùng InMemory

Mỗi pod khởi động và cùng gọi API.

**Hỏi:** Có nhất thiết chỉ một token request cho toàn cluster không?

**Đáp án:** Không. Mỗi pod có store RAM riêng, nên có thể xin token riêng và reuse trong pod đó.

### Bài tập 7 — Shared DB nhưng vẫn có 10 token requests đồng thời

Nhiều threads thấy token hết hạn tại cùng một thời điểm.

**Hỏi:** Vì sao có thể xảy ra?

**Đáp án:** Shared storage không bảo đảm toàn bộ chuỗi load-check-POST-save được đồng bộ như một thao tác atomic. Cần coordination theo key nếu tải/rate limit yêu cầu.

### Bài tập 8 — API trả 403 sau khi nhận token mới

**Hỏi:** Có nên xóa token và xin lại liên tục?

**Đáp án:** Không. 403 có thể do thiếu scope/business permission, không giải quyết bằng token mới nếu registration/policy không đổi.

### Bài tập 9 — Scheduled job dùng Servlet manager

Một background task gọi `DefaultOAuth2AuthorizedClientManager` và không có HTTP request.

**Hỏi:** Manager nào phù hợp hơn?

**Đáp án:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientService`.

### Bài tập 10 — Token sống 30 giây, skew 60 giây

**Hỏi:** Có thể dẫn đến gì?

**Đáp án:** Token có thể bị coi là gần hết hạn ngay, làm mất hiệu quả reuse và tăng token requests. Cần chỉnh skew.

### Bài tập 11 — Token API A dùng cho API B

Một service có token `inventory.read` còn hạn, nhưng dùng nó gọi `billing.write`.

**Hỏi:** Có được reuse không?

**Đáp án:** Không nếu token không có scope/audience cần thiết. Reuse chỉ đúng trong phạm vi authorization đã được cấp.

### Bài tập 12 — AS outage, token vẫn còn 10 phút

**Hỏi:** Có cần cố gọi Token Endpoint để chắc chắn nhận token mới không?

**Đáp án:** Thông thường không. Nếu token còn đủ hạn và API tiếp tục chấp nhận, manager có thể reuse token hiện tại. Không nên tự xin token mới trước mọi API call.

## 29. Tổng kết nhanh theo thành phần

| Thành phần | Điều cần nhớ |
|---|---|
| `client_credentials` | Grant để service lấy access token bằng quyền của chính client. |
| `OAuth2AuthorizedClient` | Chứa access token, hạn dùng, client registration và principal name. |
| `OAuth2AuthorizedClientService` | Giữ authorized client giữa các lần gọi. |
| `OAuth2AuthorizedClientManager` | Điều phối lookup, authorize và lưu token. |
| `ClientCredentialsOAuth2AuthorizedClientProvider` | Chọn reuse hay xin token mới theo ngữ cảnh và thời hạn. |
| `OAuth2AuthorizedClientProviderBuilder.clientCredentials()` | Bật provider Client Credentials trong manager. |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manager phù hợp cho background/service context. |
| `expiresAt` | Thời điểm token hết hiệu lực theo metadata. |
| `clockSkew` | Khoảng đệm để xin token trước khi nó hết hạn. |
| `registrationId + principalName` | Khóa thường dùng để lưu/reuse authorized client. |
| `InMemoryOAuth2AuthorizedClientService` | Cache trong một application instance. |
| `JdbcOAuth2AuthorizedClientService` | Persistence chia sẻ qua database khi được cấu hình. |
| Client Credentials token mới | Thường xin bằng `grant_type=client_credentials`, không phải refresh token. |
| Concurrency control | Giảm nhiều token requests đồng thời khi cache miss/hết hạn. |
| Resource Server 401/403 | Cần phân tích issuer/audience/scope/policy, không tự retry token vô hạn. |

**Kết luận:** Trong Client Credentials Grant, **tái sử dụng token còn hạn** là cơ chế quan trọng để giảm tải cho Authorization Server và giảm latency khi gọi API. Spring Security hỗ trợ cơ chế này thông qua **`OAuth2AuthorizedClientManager` + `ClientCredentialsOAuth2AuthorizedClientProvider` + `OAuth2AuthorizedClientService`**. Manager tìm authorized client theo registration/principal; khi token còn đủ hạn, nó có thể dùng lại token đó, còn khi token hết hạn hoặc gần hết hạn, provider **gửi Client Credentials Token Request mới** và manager lưu kết quả.

Để cơ chế hoạt động đúng trong production, cần giữ `principalName` ổn định, chọn storage phù hợp số instances, đặt `clockSkew` theo token lifetime, kiểm soát concurrency lúc cấp lại token và bảo vệ access token/client credentials. **Không dùng token của service như token đại diện người dùng và không lấy token mới chỉ để né các lỗi scope/audience/authorization.**

## Tài liệu tham khảo chính thức

- [RFC 6749 — OAuth 2.0, Client Credentials Grant](https://datatracker.ietf.org/doc/html/rfc6749#section-4.4): grant, token request/response và lưu ý về refresh token.
- [Spring Security — OAuth2 Client Authorized Clients (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): authorized client manager và storage.
- [Spring Security — OAuth2 Client Authorization Grants (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Client Credentials và tùy chỉnh grant/token response clients.
- [Spring Security API — ClientCredentialsOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ClientCredentialsOAuth2AuthorizedClientProvider.html): điều kiện authorize và clock skew.
- [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html): cấu hình provider.
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): manager dùng authorized client service ngoài HTTP request.
- [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html): contract lưu và truy xuất authorized clients.
