# Thiết lập TTL, cache token phía client và chính sách xoay credential

## 1. Bối cảnh: ba vòng đời khác nhau trong Client Credentials Grant

Trong hệ thống OAuth 2.0/OpenID Connect Authorization Server được xây dựng bằng **Spring Security**, **Spring Authorization Server** và Spring Boot, nhiều dịch vụ backend cần gọi API nội bộ mà **không có người dùng cuối đăng nhập**.

Ví dụ: `billing-service` phải gọi `inventory-api` để đọc tồn kho. Với **Client Credentials Grant**, `billing-service` xác thực chính nó ở Token Endpoint, nhận access token rồi gửi token đó khi gọi Resource Server. Nếu dịch vụ xin token mới cho từng API request, tải lên Authorization Server sẽ tăng không cần thiết. Nếu dùng token quá hạn, API từ chối. Nếu xoay client secret đột ngột, ứng dụng có thể đang chạy ổn với token cache nhưng thất bại ở lần xin token tiếp theo.

Ba vấn đề cần tách biệt:

1. **Access token TTL:** Authorization Server phát hành token có thời hạn bao lâu?
2. **Client-side token cache:** Ứng dụng giữ, tái sử dụng và thay access token vào thời điểm nào?
3. **Credential rotation:** Client thay secret, private key hoặc chứng chỉ xác thực như thế nào mà không gây gián đoạn hoặc lộ bí mật?

**Không được đồng nhất thời hạn access token với thời hạn client credential.** Secret có thể được dùng để xin nhiều token trong một giai đoạn; ngược lại, token đã cấp có thể vẫn dùng được sau khi secret bị thay, tùy chính sách thu hồi và cơ chế Resource Server.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Cấu hình `TokenSettings.accessTokenTimeToLive` cho từng `RegisteredClient`.
- Giải thích tại sao Client Credentials thường không có refresh token, ID token, user session hoặc consent.
- Cấu hình Spring Security OAuth2 Client dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` để xin và cache access token trong tác vụ backend.
- Thiết kế ngưỡng hết hạn sớm, khóa cache, xử lý concurrent request và chạy nhiều instance.
- Xây dựng chính sách xoay `client_secret_basic`, `private_key_jwt` và mTLS.
- Kiểm thử TTL, cache hit/miss, token acquisition failure, 401/403 và rotation.
- Giám sát token issuance và credential lifecycle mà không log token hay bí mật.

## 2. Luồng Client Credentials trong kiến trúc Spring

```mermaid
sequenceDiagram
    participant C as billing-service / OAuth Client
    participant AS as Spring Authorization Server
    participant RS as inventory-api / Resource Server

    C->>C: Tra cache access token
    alt Không có token đủ hạn
        C->>AS: POST /oauth2/token + client authentication
        AS->>AS: Kiểm tra client, grant, scope, credential
        AS-->>C: access_token, token_type, expires_in
        C->>C: Lưu token và expiresAt
    end
    C->>RS: GET /inventory + Bearer access token
    RS->>RS: Xác minh token, audience, scope, chính sách
    RS-->>C: Trả dữ liệu
    C->>C: Các request sau tái sử dụng token còn hạn
    Note over C,AS: Khi token sắp hết hạn
    C->>AS: POST /oauth2/token bằng client_credentials
    AS-->>C: Access token mới
```

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `RegisteredClientRepository` tại AS | Lưu client ID, phương thức xác thực, grant, scope và token settings |
| Token Endpoint tại AS | Xác thực client, kiểm tra `client_credentials` và phát token |
| `OAuth2AuthorizationService` tại AS | Quản lý authorization/token state theo cấu hình |
| `ClientRegistrationRepository` tại client | Giữ cấu hình cách gọi Token Endpoint |
| `OAuth2AuthorizedClientService` tại client | Lưu/tìm authorized client chứa access token |
| `OAuth2AuthorizedClientManager` tại client | Điều phối sử dụng token còn hiệu lực hoặc xin token mới |
| Resource Server | Kiểm tra access token và quyền đối với API |

**Client Credentials Grant không cần Authorization Code + PKCE**, không có redirect login của người dùng và không phát ID token chỉ vì client được xác thực. Theo RFC 6749 `4.4, refresh token **SHOULD NOT** được cấp cho grant này. Thông thường client chỉ cần dùng lại grant `client_credentials` khi token cũ gần hết hạn.

### 2.1. Client secret không phải access token

Client secret là credential dùng tại **Token Endpoint** để chứng minh danh tính confidential client. Access token là credential được gửi tới **Resource Server**. Không bao giờ đưa `client_secret` vào header gọi `inventory-api` hoặc trả client secret trong API response.

Trong OAuth, `client_id` là định danh và **không phải bí mật**. Khi dùng `client_secret_basic`, phần bí mật phải được bảo vệ bằng HTTPS và hệ thống lưu trữ an toàn. Base64 trong HTTP Basic chỉ là cách biểu diễn dữ liệu, **không phải mã hóa**.

## 3. TTL: ai quyết định, đo bằng gì?

**TTL (time to live)** là khoảng thời gian access token được dự định có hiệu lực. Authorization Server là nơi xác định token TTL khi phát hành. Client không thể tự kéo dài `exp` của JWT bằng cách giữ token trong cache lâu hơn.

| Giá trị | Nguồn | Ý nghĩa |
|---|---|---|
| `TokenSettings.accessTokenTimeToLive` | Registered client ở AS | Chính sách TTL cho token mới |
| `expires_in` | Token response | Số giây hiệu lực được AS thông báo |
| `iat`, `exp` | JWT access token nếu dùng JWT | Thời điểm phát hành/hết hạn dưới dạng claims |
| `OAuth2AccessToken.expiresAt` | Model token phía Spring Security OAuth2 Client | Thời điểm để token manager đánh giá còn hạn |
| **Safety margin / clock skew** | Chính sách client/RS | Biên sớm đề phòng network latency và lệch đồng hồ |
| **Client credential validity** | Kho bí mật/PKI/chính sách AS | Thời gian secret/khóa được phép xác thực client, độc lập token TTL |

Ví dụ nếu AS phát token có `expires_in=600`, không nên giữ nguyên token tới giây cuối cùng rồi mới gửi API request. Token có thể hết hạn giữa khi bắt đầu gửi request và khi Resource Server kiểm tra.

### 3.1. Cân bằng TTL với bảo mật và tải hệ thống

| TTL minh họa | Lợi ích | Đánh đổi |
|---|---|---|
| 2–5 phút | Giảm thời gian có thể lạm dụng token bị lộ | Token Endpoint chịu nhiều lần xin token hơn |
| 10–15 phút | Cân bằng tương đối giữa tải và hiệu lực token | Cần cơ chế xử lý revocation nếu muốn ngắt truy cập tức thời |
| 30 phút trở lên | Giảm tần suất token acquisition | JWT/claims cũ có thể tiếp tục có hiệu lực lâu hơn |

Các khoảng trên **chỉ để phân tích**, không phải mặc định của Spring Authorization Server hoặc khuyến nghị bắt buộc. Cần đo hiệu năng thực tế, độ nhạy tài nguyên và yêu cầu thu hồi.

Với JWT tự xác minh, Resource Server có thể tiếp tục nhận token cũ tới `exp` nếu không có kiểm tra trạng thái thu hồi bổ sung. TTL ngắn thường giúp giới hạn thời gian này nhưng không thay thế khả năng thu hồi khi cần.

## 4. Cấu hình TTL trong Spring Authorization Server

Mỗi `RegisteredClient` có `TokenSettings` riêng. Ví dụ confidential client `billing-service` chỉ được dùng Client Credentials với scope `inventory.read`:

```java
RegisteredClient billingClient = RegisteredClient
    .withId("billing-service-internal-id")
    .clientId("billing-service")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("inventory.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(10))
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .build())
    .build();
```

Đây là ví dụ tạo **mô hình registered client**. Ứng dụng thực còn cần `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer, JWK/khóa ký, `SecurityFilterChain` và các thành phần Spring Authorization Server khác theo phiên bản dùng trong dự án.

Các điểm quan trọng:

1. `clientSecret` lấy từ **secret manager** hoặc kênh cấu hình bảo vệ, không hard-code trong source.
2. `CLIENT_SECRET_BASIC` là phương thức client authentication; Token Endpoint phải xác minh credential.
3. `CLIENT_CREDENTIALS` không cấp quyền dùng grant khác như Authorization Code.
4. `inventory.read` là scope client được phép xin, không phải quyền xem mọi đối tượng dữ liệu.
5. `accessTokenTimeToLive` áp dụng cho **token mới**; thay TTL không tự sửa `exp` trên token cũ.
6. `SELF_CONTAINED` chỉ định dạng token; Resource Server vẫn phải kiểm tra issuer, chữ ký, audience, thời gian và scope.

**Lưu ý ID:** Internal ID của `RegisteredClient` nên được tạo/giữ ổn định trong repository. Không tạo lại ID ngẫu nhiên mỗi lần khởi động ứng dụng nếu client và authorization state cần tồn tại qua restart.

### 4.1. Hai client có TTL khác nhau

```java
TokenSettings readerPolicy = TokenSettings.builder()
    .accessTokenTimeToLive(Duration.ofMinutes(5))
    .build();

TokenSettings reportingPolicy = TokenSettings.builder()
    .accessTokenTimeToLive(Duration.ofMinutes(15))
    .build();
```

Gắn hai settings vào hai `RegisteredClient` tương ứng. Hệ thống có thể đặt giới hạn TTL tối đa ở tầng quản trị/policy để operator không vô ý phát token sống quá lâu.

Đừng dựa vào tham số TTL do caller tự gửi để quyết định thời hạn token. Grant và token policy là dữ liệu được kiểm soát phía Authorization Server.

### 4.2. Không dùng refresh token TTL để xử lý Client Credentials

`TokenSettings.refreshTokenTimeToLive` không phải giải pháp cache cho grant `client_credentials`. Theo RFC 6749, refresh token không nên được cấp trong grant này; client dùng **client authentication + grant_type=client_credentials** để lấy access token mới.

Không viết logic như “khi hết access token thì gửi refresh_token” cho M2M chỉ vì thấy class `OAuth2RefreshToken` có sẵn trong thư viện.

## 5. Token Request và phản hồi mẫu

Confidential client dùng HTTP Basic tới Token Endpoint qua TLS:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_ENCODED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

Header Basic ở trên **chỉ là placeholder**, không phải credential thật. Client ID và secret phải được mã hóa đúng quy tắc HTTP Basic/OAuth. AS kiểm tra registration, phương thức xác thực, credential, grant, scope và policy.

Ví dụ phản hồi thành công:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "inventory.read"
}
```

Đây là ví dụ trình bày dữ liệu để dễ đọc, không phải body HTTP thực tế có thể chứa thêm nguyên dòng status/headers ở trong JSON. Token phải được bảo vệ như credential, ngay cả khi có thời hạn ngắn.

Nếu client secret sai, Token Endpoint thường trả lỗi như `invalid_client`. Nếu grant hoặc scope không được phép, các lỗi phù hợp như `unauthorized_client` hoặc `invalid_scope` có thể xuất hiện. **Không redirect một M2M client sang trang đăng nhập người dùng**.

## 6. Vì sao cache access token phía client?

Access token còn hiệu lực có thể dùng lại trong nhiều request API. Nếu một instance gọi Inventory API hàng trăm lần mỗi phút mà mỗi lần đều xin token mới, Token Endpoint sẽ chịu tải tỷ lệ với traffic API thay vì tỷ lệ với thời hạn token.

```mermaid
flowchart TD
    REQ["billing-service cần gọi Inventory API"]
    KEY["Xác định token cache key"]
    HIT{"Có token còn đủ hạn?"}
    USE["Dùng token hiện có"]
    SINGLE["Single-flight theo cache key nếu cần"]
    AS["Client Credentials Token Request"]
    SAVE["Lưu token, expiresAt và metadata"]
    API["Gọi Inventory API"]

    REQ --> KEY --> HIT
    HIT -->|"Có"| USE --> API
    HIT -->|"Không"| SINGLE --> AS --> SAVE --> API
```

Cache chỉ phục vụ **tái sử dụng token hợp lệ**, không làm thay đổi quyền, hạn sử dụng hoặc trạng thái thu hồi.

### 6.1. Cache key: đừng dùng một token cho mọi client

Một cache key thường được quản lý theo:

```text
(clientRegistrationId, principalName)
```

Trong Spring Security OAuth2 Client, `principalName` là định danh cho đối tượng authorized client. Với Client Credentials chạy nền, nó có thể là tên workload ổn định như `svc:billing`, **không phải người dùng đăng nhập**.

| Tình huống | Phân vùng cache |
|---|---|
| Một workload, một registration | `inventory-api` + `svc:billing` |
| Gọi nhiều Resource Server | Registration riêng theo API/audience |
| Nhiều tenant dùng credential khác nhau | Phân vùng theo tenant/registration đáng tin |
| Scope/audience thay đổi theo request | Không tái sử dụng token sai scope/audience; thiết kế registration/khóa riêng |

Không dùng biến static `lastAccessToken` cho tất cả API. Một token chỉ có `inventory.read` không được dùng làm credential gọi `payments-api`, dù cả hai hệ thống đều nhận Bearer token.

### 6.2. Lấy token mới trước khi hết hạn

Biên an toàn lý tưởng được chọn từ clock skew, thời gian mạng và thời gian xử lý:

```text
token_usable = (now + safety_margin) < expiresAt
```

Ví dụ, access token còn 20 giây nhưng API request có thể kéo dài 30 giây thì nên xin token mới trước khi gọi API. Safety margin 30–60 giây là ví dụ thông dụng để phân tích; với token TTL rất ngắn phải chọn biên nhỏ hơn để tránh liên tục xin token mới.

**Cache TTL phải không vượt quá thời hạn access token.** Đừng cộng thêm thời gian vào `expiresAt` vì Resource Server vẫn kiểm tra hạn đã phát hành.

### 6.3. Jitter và tránh thundering herd

Hàng trăm instance có thể cùng xin token khi vừa khởi động, rồi cùng hết hạn trong khoảng thời gian tương tự. Điều đó gây *thundering herd*.

Có thể giảm bằng:

- **Jitter nhỏ có giới hạn** để mỗi instance xin token **sớm hơn** tại một thời điểm khác nhau.
- **Single-flight** để nhiều thread cùng một cache key chỉ phát một Token Request tại một thời điểm.
- Giới hạn retry và backoff khi Token Endpoint trả 429/5xx.
- Distributed lock/lease nếu cache được chia sẻ giữa các instance và tải đủ lớn để cần.

Jitter không bao giờ được kéo dài thời hạn token vượt `exp`.

## 7. Spring Security OAuth2 Client: dùng manager thay vì tự viết cache

Với `billing-service` là OAuth client, Spring Security cung cấp các thành phần:

| Lớp | Vai trò |
|---|---|
| `ClientRegistrationRepository` | Client ID, Token URI, scope, grant và authentication method |
| `OAuth2AuthorizedClientService` | Lưu/tìm/xóa authorized client, bao gồm access token |
| `ClientCredentialsOAuth2AuthorizedClientProvider` | Thực hiện grant Client Credentials khi cần token mới |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Quản lý access token của background service không cần request/session người dùng |

Các lớp này thuộc **ứng dụng OAuth client**, không phải bean mặc định của Authorization Server.

### 7.1. Khai báo client registration

`application.yml` phía `billing-service`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-api:
            provider: corporate-as
            client-id: billing-service
            client-secret: ${INVENTORY_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          corporate-as:
            token-uri: https://auth.example.com/oauth2/token
```

Ký hiệu `${INVENTORY_OAUTH_CLIENT_SECRET}` biểu thị secret được nạp từ môi trường/secret manager; **không** commit giá trị thực vào Git hoặc ghi trong log startup. Token URI phải dùng HTTPS và trỏ đúng issuer/Authorization Server được tin cậy.

### 7.2. Manager cho scheduled jobs và service-to-service

```java
@Configuration
class OAuthClientConfiguration {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {
        return new InMemoryOAuth2AuthorizedClientService(registrations);
    }

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        ClientCredentialsOAuth2AuthorizedClientProvider provider =
            new ClientCredentialsOAuth2AuthorizedClientProvider();

        provider.setClockSkew(Duration.ofSeconds(45));

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Giải thích:

- `InMemoryOAuth2AuthorizedClientService` là cache trong tiến trình, tiện cho ví dụ và instance đơn.
- `setClockSkew(...)` giúp provider coi token là cần gia hạn trước lúc hết hạn.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` thích hợp cho **background process**, không cần `HttpServletRequest`.
- Nếu token chưa có hoặc đã gần hết hạn, provider có thể **xin access token mới bằng client_credentials**, không dùng refresh token.

Tùy Spring Boot version, các bean repository/service có thể đã được auto-configure; không tạo bean trùng hoặc ghi đè cấu hình đang được ứng dụng sử dụng mà không có chủ đích. Test runtime với phiên bản dependency thực tế.

### 7.3. Service gọi Inventory API bằng token được quản lý

Ví dụ sử dụng `RestClient` trong ứng dụng blocking:

```java
@Service
public class InventoryGateway {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient inventoryClient;

    public InventoryGateway(
            OAuth2AuthorizedClientManager manager,
            RestClient.Builder restClientBuilder) {
        this.manager = manager;
        this.inventoryClient = restClientBuilder
            .baseUrl("https://inventory.example.com")
            .build();
    }

    public String readInventory() {
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
            .withClientRegistrationId("inventory-api")
            .principal("svc:billing")
            .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "No authorized client for inventory-api");
        }

        String token = client.getAccessToken().getTokenValue();

        return inventoryClient.get()
            .uri("/inventory")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
```

Mã tập trung vào luồng lấy token và gọi API; cần import, cấu hình RestClient timeout, exception handling và test tích hợp. `RestClient` thuộc Spring Framework hiện đại. Với dịch vụ WebFlux reactive, nên dùng lớp quản lý OAuth2 client **reactive**, không chặn event loop bằng blocking manager.

**Không log biến `token`.** `principal("svc:billing")` là tên workload ổn định để phân vùng authorized client, không phải bằng chứng có người dùng cuối.

### 7.4. Giới hạn của cache mặc định

Manager/service giúp quản lý token lifecycle nhưng không tự bảo đảm:

- Chỉ có một Token Request trong tất cả thread khi cache miss cạnh tranh.
- Cache dùng chung giữa nhiều JVM/pod.
- Token được mã hóa khi lưu trong distributed cache tùy biến.
- Cache key được mở rộng đúng với audience/tenant động.
- Tự động xử lý mọi API 401 do token bị thu hồi.
- Không có outage trong khi xoay client secret.

Cần đánh giá nhu cầu thực và bổ sung cơ chế phù hợp thay vì giả định “có manager là production-ready cho mọi topology”.

## 8. In-memory và distributed token cache

| Phương án | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|
| In-memory theo instance | Dễ vận hành, token không đi qua shared cache | Restart mất token; nhiều instance xin token độc lập |
| Persistent `OAuth2AuthorizedClientService` | Có thể giữ state qua restart | Phải bảo vệ token at rest, phân quyền, cleanup |
| Distributed cache/locking tùy biến | Giảm Token Request trên toàn cụm | Tăng độ phức tạp race, consistency, lock expiry và cache security |
| Không cache | Đơn giản nhưng nhiều request hơn | Tải/latency Token Endpoint tăng; outage lan nhanh |

**In-memory theo instance thường là lựa chọn đầu tiên hợp lý** cho M2M, nếu số instance và tải Token Endpoint cho phép. Chỉ thêm distributed cache khi đo được lợi ích và đã có mô hình bảo vệ token.

### 8.1. Race condition trên cache miss

Giả sử 30 thread cùng phát hiện token hết hạn. Nếu tất cả gọi AS, một thời điểm sẽ có 30 access token mới dù thực tế một token là đủ.

Single-flight nên khóa **theo cache key** chứ không khóa toàn bộ ứng dụng. Các thread cùng key chờ một token acquisition; thread gọi client khác vẫn chạy độc lập. Với nhiều node, mutex JVM không phải distributed lock.

Nếu có retry, dùng backoff và jitter; không biến Token Endpoint thành điểm nghẽn do mọi request API đồng loạt refresh.

### 8.2. Không lưu token quá hạn trong cache chỉ vì AS đang lỗi

Nếu AS bị outage nhưng access token vẫn hợp lệ, client có thể tiếp tục dùng token đang cache. Khi token đã hết hạn, **không được cố dùng token cũ** rồi yêu cầu Resource Server bỏ qua `exp`. Cần báo lỗi có kiểm soát, giảm tải retry và có phương án vận hành khác phù hợp SLA.

## 9. Xử lý 401, 403 và lỗi Token Endpoint

| Tình huống | Phân tích | Phản ứng phù hợp |
|---|---|---|
| Resource Server trả `401 invalid_token` | Token hết hạn/không hợp lệ/bị thu hồi | Có thể xóa cache có điều kiện, xin token mới và retry phù hợp tối đa một lần |
| Resource Server trả `403` | Token đã xác thực nhưng không đủ quyền | Kiểm tra scope/audience/policy; không retry xin token vô hạn |
| Token Endpoint trả `invalid_client` | Credential client không được AS chấp nhận | Kiểm tra secret/key/cert, rotation, clock nếu dùng assertion |
| Token Endpoint trả `unauthorized_client` | Client không được phép dùng grant | Kiểm tra registration; không “tăng TTL” để khắc phục |
| Token Endpoint trả `invalid_scope` | Scope yêu cầu không hợp lệ | Kiểm tra registration và policy |
| Token Endpoint trả `429` hoặc `5xx` | Rate limiting hoặc sự cố AS | Backoff, retry giới hạn, circuit breaker và metrics |
| Token Endpoint timeout | Mạng/AS không phản hồi rõ ràng | Retry có giới hạn, chống thundering herd |

Lưu ý khi retry một API request: không tự gửi lại thao tác thay đổi dữ liệu **không idempotent** nếu không có cơ chế idempotency phù hợp. Nếu có nhiều thread, thao tác xóa cache phải tránh xóa nhầm token mới vừa được thread khác lưu.

`OAuth2AuthorizedClientService.removeAuthorizedClient(registrationId, principalName)` có thể loại authorized client khỏi storage, nhưng production cần quản lý concurrency và nguyên nhân xóa đúng.

### 9.1. 401 không phải lúc nào cũng do token hết hạn

Một token mới vẫn bị 401 nếu Resource Server cấu hình sai issuer, audience, JWKS, mTLS token binding hoặc nhận sai môi trường. Không thiết kế vòng lặp `401 → xin token mới → 401 → xin token mới` vô hạn.

Tương tự, 403 vì thiếu scope không được giải bằng xin lại token cùng grant/scope rồi hi vọng khác kết quả. Hãy kiểm tra policy và các claims được cấp thực tế.

## 10. Client credential rotation là bài toán khác token TTL

Giả sử AS đã cấp access token A với `exp` sau 10 phút. Sau 3 phút, operator xoay secret:

```mermaid
flowchart LR
    OLD["Client secret cũ"] --> TOKEN["AS phát access token A"]
    TOKEN --> RS["Resource Server kiểm tra token A"]
    NEW["Client secret mới"] --> TOKEN2["AS phát access token B"]
    TOKEN2 --> RS
```

Khi AS ngừng chấp nhận secret cũ:

- Secret cũ **không còn dùng để xin token mới**.
- Access token A **không tự mất hiệu lực**; JWT tự xác minh có thể còn dùng được tới `exp` nếu RS không kiểm tra thu hồi.
- Client đang cache token A vẫn có thể gọi API bình thường, rồi thất bại ở lượt token acquisition tiếp theo nếu chưa nhận secret mới.
- Nếu secret bị xâm nhập và cần ngắt quyền ngay, phải xử lý **cả credential và token đang sống** theo chính sách ứng cứu.

### 10.1. Phân biệt các loại khóa/credential

| Thành phần | Dùng để làm gì? |
|---|---|
| Client secret | Xác thực client với AS ở Token Endpoint |
| Private key `private_key_jwt` | Client ký assertion để AS xác minh client |
| Client certificate/private key mTLS | Xác thực client ở TLS và có thể hỗ trợ sender-constrained token |
| Khóa ký JWT của AS | AS ký token; Resource Server dùng public key xác minh |
| Access token | Client gọi Resource Server |

**Xoay client secret không phải xoay khóa ký JWT của AS.** Khóa ký AS cần được giữ/rotate theo thời hạn token còn sống và cache JWKS; đây là vòng đời riêng.

## 11. Chính sách xoay client secret theo từng giai đoạn

Một quy trình rotation có kiểm soát:

| Bước | Hành động | Xác minh |
|---|---|---|
| **Prepare** | Sinh secret mới bằng CSPRNG, lưu secret manager, giới hạn người có thể xem | Không lộ trong Git/CI/log/ticket |
| **Enable** | Đưa secret mới vào cơ chế AS chấp nhận theo phương án thiết kế | Token Request **mới** bằng secret mới thành công |
| **Roll out** | Cập nhật secret version cho từng client instance | Instances thực sự dùng version mới khi xin token |
| **Observe** | Theo dõi `invalid_client`, Token Endpoint và API 401 | Không có đợt lỗi do token cache hết hạn |
| **Retire** | Ngừng chấp nhận secret cũ | Token Request dùng secret cũ bị từ chối |
| **Audit** | Ghi actor, client, version, mốc thời gian và kết quả | Không lưu giá trị secret trong event |

### 11.1. Giới hạn của `RegisteredClient.clientSecret`

Mô hình `RegisteredClient` chuẩn thường chỉ có **một trường `clientSecret` hiện hành**. Không được giả định một `RegisteredClientRepository.save(...)` đơn giản hỗ trợ **hai secret cùng hiệu lực** để zero-downtime rotation.

Nếu cần giai đoạn chồng lấn secret:

- Xác nhận framework/triển khai đang dùng có hỗ trợ nhiều credential hợp lệ hay không.
- Nếu không, cần thiết kế custom credential store/client authentication provider thích hợp, hoặc chọn phương thức bất đối xứng có overlap được quản trị.
- Nếu không hỗ trợ overlap, phải lên kế hoạch rollout đồng bộ/cửa sổ bảo trì, đo tác động và có rollback **không sử dụng lại secret đã bị lộ**.

**Không thiết kế zero-downtime rotation trên một tính năng multi-secret chưa tồn tại.**

### 11.2. Ví dụ cập nhật secret trong repository

```java
RegisteredClient existing =
    registeredClientRepository.findByClientId("billing-service");

if (existing == null) {
    throw new IllegalStateException("Client not found");
}

RegisteredClient updated = RegisteredClient.from(existing)
    .clientSecret(passwordEncoder.encode(newSecretFromSecureStore))
    .build();

registeredClientRepository.save(updated);
```

Snippet chỉ minh họa cách bảo toàn các field khác của `RegisteredClient`. Để đưa vào production phải có phân quyền admin, validate, revision/optimistic locking, audit, approval khi cần và đồng bộ client repository cache giữa các node AS.

**Không ghi secret cũ/mới hoặc secret hash vào audit diff.** Chỉ ghi sự kiện như `CLIENT_SECRET_ROTATED` với actor, client ID và credential version.

## 12. Xoay khóa `private_key_jwt`

Với `private_key_jwt`, client giữ private key và ký JWT assertion để xác thực ở Token Endpoint. Authorization Server xác minh assertion bằng public key tin cậy. Cơ chế này có thể thuận tiện cho rotation khi JWK Set của client có **cả public key cũ và mới** trong khoảng chuyển tiếp.

Quy trình tham khảo:

1. Tạo cặp khóa mới, `kid` mới; bảo vệ private key.
2. Công bố public key mới trong JWK Set được AS tin cậy, giữ key cũ nếu chính sách cho phép.
3. Kiểm tra AS chấp nhận assertion ký bằng key mới.
4. Chuyển từng client instance sang key mới.
5. Theo dõi lỗi `invalid_client`, cache JWKS, clock skew của `iat`/`exp` và audience assertion.
6. Sau thời hạn chuyển tiếp, loại public key cũ; thu hồi/xóa private key cũ.
7. Ghi audit rotation không chứa private key hoặc raw assertion.

Ví dụ đăng ký phương thức:

```java
RegisteredClient jwtClient = RegisteredClient
    .withId("billing-internal-id")
    .clientId("billing-service")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.PRIVATE_KEY_JWT)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("inventory.read")
    .clientSettings(ClientSettings.builder()
        .jwkSetUrl("https://keys.example.com/billing/jwks.json")
        .build())
    .build();
```

Đây là mô hình minh họa, chưa bao gồm JWT assertion generator, validator, khóa ký và cấu hình triển khai hoàn chỉnh. `jwkSetUrl` phải thuộc nguồn đáng tin, được kiểm soát và tránh SSRF/trust arbitrary URL. Hỗ trợ cụ thể tùy phiên bản Spring Authorization Server.

## 13. Xoay certificate mTLS

mTLS yêu cầu client trình chứng chỉ và server xác minh chuỗi tin cậy/danh tính trên kết nối TLS. Nó **khác HTTPS thông thường**, nơi chỉ server có certificate.

Rotation mTLS gồm:

- Quản lý CA/PKI và thời hạn chứng chỉ.
- Cấp chứng chỉ/key mới trước khi chứng chỉ cũ hết hạn.
- Cho phép giai đoạn overlap có kiểm soát trong trust policy khi cần.
- Cập nhật client keystore/truststore và cấu hình reverse proxy.
- Kiểm thử AS nhận đúng client identity trong các kịch bản TLS termination.
- Thu hồi chứng chỉ cũ và audit thời điểm chuyển đổi.

mTLS còn có thể tham gia sender-constrained access tokens khi triển khai RFC 8705 phù hợp. Khi đó token có thể được ràng buộc với chứng chỉ và RS phải thực sự xác minh binding; không được giả định “dùng mTLS tại Token Endpoint là mọi Bearer token tự được ràng buộc”.

## 14. Mô phỏng sự cố rotation với token cache

Giả sử có ba pod A, B, C. Token TTL 10 phút, các pod đều đang cache token.

| Thời điểm giả định | Sự kiện | Kết quả |
|---|---|---|
| 10:00 | A/B/C xin token bằng secret cũ | Tất cả hoạt động |
| 10:03 | AS chuyển sang secret mới | Token cũ còn hạn vẫn có thể gọi API |
| 10:04 | A cập nhật secret mới | Lần xin token tiếp theo của A sẽ thành công |
| 10:06 | B/C chưa cập nhật; vẫn dùng token cache | API còn có thể thành công |
| 10:09 | Token B gần hết hạn, B xin token mới | `invalid_client` vì secret cũ |
| 10:10 | Token cache C hết hạn | C cũng có thể thất bại |
| 10:11 | B/C cập nhật secret mới, xin token mới | Hoạt động lại |

**Token cache có thể che giấu lỗi rotation cho đến lần token acquisition tiếp theo.** Do đó, kiểm thử rotation không được chỉ gọi API bằng access token đã cache. Phải thử **Token Request mới** với credential mới, kiểm tra từng pod đã nạp phiên bản secret mới và theo dõi `invalid_client`.

### 14.1. Kiểm tra thực tế sau rotation

1. Bắt buộc một Token Request mới bằng credential mới qua đường tích hợp phù hợp.
2. Kiểm tra Token Endpoint xác thực client và cấp token đúng scope/audience.
3. Gọi Resource Server bằng token mới.
4. Kiểm tra toàn bộ instances đang dùng credential version mới.
5. Thu hồi secret cũ theo kế hoạch.
6. Kiểm tra secret cũ không còn xin token được.
7. Quyết định cách xử lý access token đã phát hành trước rotation, nhất là khi nghi bị lộ.

## 15. Xử lý Authorization Server outage với cache token

Khi Token Endpoint tạm lỗi:

- Nếu token cache **vẫn còn hạn và đúng scope/audience**, client có thể tiếp tục dùng token.
- Nếu token đã hết hạn, không được gửi token hết hạn hoặc yêu cầu RS bỏ qua validation.
- Retry Token Endpoint phải có giới hạn, exponential backoff/jitter và circuit breaker phù hợp.
- Khi AS phục hồi, tránh để toàn cụm gửi một lượng lớn Token Request đồng thời.

Mô hình đơn giản để ước lượng tải token acquisition ổn định:

```text
token_requests_per_second ≈
    number_of_instances × number_of_distinct_cache_keys
    / effective_token_ttl_seconds
```

Giả sử 100 instance, mỗi instance có một cache key và token TTL hiệu dụng 500 giây, mức tải ổn định khoảng 0,2 request/giây. Đây chỉ là gần đúng; startup burst, retry và nhiều registration có thể làm số request cao hơn.

**Không tăng token TTL lên quá mức chỉ để chữa lỗi mạng/caching.** Hãy đo cache hit ratio và xử lý token acquisition hiệu quả trước.

## 16. Kiểm thử TTL, cache và credential rotation

### 16.1. Kiểm thử Authorization Server

| Ca | Thiết lập | Kỳ vọng |
|---|---|---|
| Grant hợp lệ | Client có `CLIENT_CREDENTIALS` và secret đúng | AS cấp access token |
| Grant không đăng ký | Client chỉ được Authorization Code | AS từ chối `client_credentials` |
| Scope sai | Xin `inventory.write` khi chỉ được `inventory.read` | AS từ chối hoặc không cấp vượt quyền |
| TTL theo client | Client A/B có `TokenSettings` khác nhau | Token mới có expiry tương ứng |
| JWT/opaque format | Cấu hình token format | RS xác minh bằng cơ chế phù hợp |
| Secret sai | Token Request với secret cũ/bị thu hồi | `invalid_client` hoặc lỗi tương ứng |
| Không có refresh token | Client Credentials Token Response | Client không mặc định có refresh token |

### 16.2. Kiểm thử token cache

| Ca | Kết quả cần chứng minh |
|---|---|
| Cache miss | Có Token Request để lấy token |
| Cache hit khi token đủ hạn | Không gọi Token Endpoint lần nữa |
| Token sát `expiresAt` | Manager xin token mới theo clock skew |
| Hai thread cache miss | Concurrency được xử lý theo chính sách, không stampede không kiểm soát |
| Nhiều registration | Không dùng token của API A cho API B |
| Tenant khác nhau | Không dùng chung token sai identity/scope/audience |
| Cache restart | Token acquisition hoạt động lại sau khi cache mất |
| AS outage, token còn hiệu lực | Có thể tiếp tục gọi API theo policy |
| AS outage, token hết hạn | Không cố dùng token đã hết hạn |
| RS 401 | Invalidate/retry có giới hạn và tránh race |
| RS 403 | Không spam xin token mới |

### 16.3. Kiểm thử rotation

| Ca | Kết quả cần chứng minh |
|---|---|
| Secret mới trước retire | AS nhận Token Request mới qua cơ chế transition đã thiết kế |
| Secret cũ sau retire | Bị từ chối |
| Access token cũ còn hạn | RS xử lý theo `exp`/revocation, không giả định tự hết hạn |
| Pod chưa nhận secret mới | Phát hiện lỗi khi cache cần token mới |
| `private_key_jwt` đổi `kid` | AS tin key mới trong giai đoạn phù hợp |
| mTLS certificate đổi | AS xác minh chứng chỉ mới |
| Concurrent admin updates | Revision/locking ngăn lost update |
| Log/audit | Không xuất hiện secret, raw token, private key |

### 16.4. Unit test boundary với `Clock`

Có thể tự kiểm tra logic “token đủ hạn để gọi API” bằng một hàm nhỏ dùng `Clock` điều khiển được:

```java
static boolean hasEnoughLifetime(
        OAuth2AccessToken accessToken,
        Clock clock,
        Duration safetyMargin) {

    Instant expiresAt = accessToken.getExpiresAt();
    return expiresAt != null
        && Instant.now(clock)
            .plus(safetyMargin)
            .isBefore(expiresAt);
}
```

Hàm chỉ minh họa điều kiện TTL. Nếu sử dụng `OAuth2AuthorizedClientManager` chuẩn, hãy ưu tiên cơ chế clock skew của provider và test hành vi thực tế, tránh hai bộ logic expiry mâu thuẫn. Test trước/sát/sau ngưỡng expiry bằng clock giả thường ổn định hơn `Thread.sleep(...)`.

## 17. Observability, audit và ứng cứu

### 17.1. Dữ liệu cần đo

- Token Endpoint QPS theo client và loại grant.
- `invalid_client`, `unauthorized_client`, `invalid_scope` rate.
- Cache hit/miss ratio và token acquisition latency.
- Số requests gần token expiration.
- API 401/403 theo registration/Resource Server.
- Single-flight waits, retry/backoff và circuit breaker activation.
- Credential version, `kid`/certificate identifier và tiến độ rotation (không chứa bí mật).
- Số instances đang dùng phiên bản credential cũ.
- Số sự kiện token acquisition thất bại trong thời gian AS outage.

### 17.2. Tuyệt đối không ghi

- `client_secret` hoặc raw `Authorization: Basic ...`.
- `access_token`/`refresh_token` hoặc raw `Authorization: Bearer ...`.
- Private key, raw client assertion JWT hoặc mTLS private key.
- Token Endpoint body/response chưa che dữ liệu.
- Cache dump chứa token, secret manager response hay secret hash.

Dùng correlation ID, client registration ID, TTL còn lại, loại lỗi và thời gian xử lý thay cho credential thô.

### 17.3. Nếu client credential bị lộ

1. Xác định client và workload bị ảnh hưởng, hạn chế quyền/đường sử dụng tiếp.
2. Thu hồi credential cũ, cấp credential mới an toàn.
3. Xác minh mọi client instance đã chuyển sang credential mới.
4. Điều tra access token có thể đã được phát hành từ credential bị lộ.
5. Nếu cần ngắt truy cập tức thời, triển khai revocation/introspection/denylist hoặc chính sách RS phù hợp, không chỉ xoay secret.
6. Ghi audit, bảo vệ bằng chứng và bổ sung kiểm soát ngăn tái diễn.

## 18. Checklist trước khi chạy production

- [ ] Client chỉ được đăng ký grant `CLIENT_CREDENTIALS` và các scope cần thiết.
- [ ] Client authentication phù hợp; secret/khóa được lưu trong secret manager.
- [ ] `TokenSettings.accessTokenTimeToLive` được chọn dựa trên threat model và tải thực.
- [ ] Resource Server xác minh issuer, chữ ký hoặc introspection, audience, expiry và scope/policy.
- [ ] Client tái sử dụng access token còn hạn bằng manager/cache đã được kiểm thử.
- [ ] Cache key không lẫn registration, workload, tenant hoặc audience.
- [ ] Cache làm mới token trước hạn, dùng clock skew/jitter thích hợp.
- [ ] Có kiểm soát cache stampede khi nhiều thread/instance.
- [ ] 401 và 403 được xử lý khác nhau; không retry vô hạn.
- [ ] Không mặc định có refresh token trong Client Credentials.
- [ ] Chính sách credential rotation có prepare/enable/rollout/verify/retire/audit.
- [ ] Đã xác minh có hoặc không hỗ trợ dual-secret trước khi hứa zero downtime.
- [ ] Đã kiểm thử request xin token mới sau rotation, không chỉ gọi API bằng token cache.
- [ ] Signing key rotation của AS tách khỏi client credential rotation.
- [ ] Logs, traces, metrics và audit không chứa raw secret/token/key.
- [ ] Có runbook cho secret leakage, AS outage và token revocation.

### Kiến thức cốt lõi

**Token TTL** là chính sách do Authorization Server quyết định khi phát hành; **token cache** là trách nhiệm của OAuth client, giúp tái sử dụng token đủ hạn và xin token mới khi cần; **credential rotation** là quá trình thay phương tiện xác thực client ở Token Endpoint. Ba vòng đời liên quan nhưng **không tự kết thúc cùng nhau**.

Spring Authorization Server cung cấp `TokenSettings` trên từng `RegisteredClient`. Spring Security OAuth2 Client cung cấp `AuthorizedClientServiceOAuth2AuthorizedClientManager` và `ClientCredentialsOAuth2AuthorizedClientProvider` cho workload M2M. Để vận hành an toàn, cần thêm chính sách cache key, expiry skew, concurrency, bảo vệ credential, rotation có kiểm chứng và giám sát thực tế.

## Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework, Client Credentials `4.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.4)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Security — OAuth 2.0 Client: Authorized Client Manager](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
