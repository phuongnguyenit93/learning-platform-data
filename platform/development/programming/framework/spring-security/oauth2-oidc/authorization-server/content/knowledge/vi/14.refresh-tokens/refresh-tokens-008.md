# Xử lý đồng thời nhiều yêu cầu refresh và bảo đảm tính nhất quán

> **Chương: Refresh Token.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**: học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm là **race condition khi nhiều request cùng dùng một refresh token**, thiết kế **refresh token rotation an toàn**, tính nguyên tử khi cập nhật trạng thái và cách phối hợp giữa **OAuth2 Client** với **Authorization Server** trong môi trường nhiều instance.

## 1. Vì sao refresh token là điểm nóng về đồng thời?

Access token có thời hạn ngắn giúp giảm thiểu hậu quả khi bị lộ. Khi hết hạn, một OAuth2 Client có thể gửi refresh token đến `/oauth2/token` để lấy access token mới mà không bắt người dùng đăng nhập lại ngay. Nhưng một trình duyệt hoặc một service backend thường có **nhiều request API chạy cùng lúc**. Nếu cả năm request phát hiện access token sắp hết hạn, cả năm có thể cố refresh **cùng một refresh token**.

Tình huống ví dụ:

- **Authorization Server (AS/OP):** `https://login.example.vn`, dùng Spring Authorization Server.
- **Confidential web client / Backend for Frontend (BFF):** `portal-web` tại `https://portal.example.vn`, dùng Spring Security OAuth2 Client.
- **Resource Server:** `https://api.example.vn`; Client dùng access token gọi API.
- **Grant ban đầu:** Authorization Code + PKCE, client được phép `refresh_token`.
- **Trạng thái hiện tại:** access token `A0` sắp hết hạn; refresh token hiện hành `R0`.
- **Hai request đồng thời:** `GET /orders` và `GET /profile` cần token mới tại cùng thời điểm.

Nếu chính sách **rotation** đang bật, yêu cầu refresh thành công bằng `R0` sẽ phát `R1` rồi không cho `R0` dùng tiếp. Request thứ hai dùng `R0` có thể bị từ chối với `invalid_grant`. Không được “sửa” lỗi này bằng cách cho cả hai request dùng token cũ tùy ý, vì điều đó có thể phá **replay detection**.

### 1.1. Các loại lỗi cần phân biệt

| Hiện tượng | Vấn đề thực sự | Kết quả có thể thấy |
|---|---|---|
| Hai luồng trong **một JVM** dùng cùng `R0` | Client không gom nhiều lần refresh thành một lần (single-flight) | Một lần thành công, lần kia `invalid_grant` |
| Hai **pod Client** dùng chung session/token store nhưng refresh độc lập | Khóa `synchronized` chỉ bảo vệ một JVM | Race liên instance, ghi đè token mới bằng token cũ |
| Hai **pod Authorization Server** cùng đọc `R0` trước khi có pod nào lưu `R1` | Chuyển trạng thái không nguyên tử | Nguy cơ cả hai chấp nhận token cũ hoặc last-write-wins |
| AS cấp `R1` nhưng response bị mất | Client vẫn giữ `R0` dù server đã chuyển sang `R1` | Retry có thể trông như replay, user buộc đăng nhập lại |
| Client lưu `R1` nhưng request khác ghi đè bằng snapshot cũ `R0` | Lost update ở token store của Client | Request sau dùng refresh token đã bị vô hiệu |
| Kẻ tấn công dùng refresh token đã bị đánh cắp | **Replay thật** | Phải phát hiện theo chính sách rotation/sender-constraining |
| Access token hết hạn và không có refresh token | Không phải race condition | Client cần authorization grant mới hoặc cơ chế phù hợp |

**Mục tiêu đúng:** tối đa một lần chuyển trạng thái refresh có hiệu lực cho mỗi phiên bản refresh token; mọi Client instance quan sát trạng thái mới nhất; thất bại được xử lý **không làm rò token hoặc cấp quyền ngoài chính sách**.

## 2. Phân biệt reuse refresh token và refresh token rotation

Spring Authorization Server cung cấp `TokenSettings.Builder.reuseRefreshTokens(boolean)`.

| Chính sách | Khi refresh thành công | Khi hai request cùng dùng `R0` | Đánh đổi |
|---|---|---|---|
| `reuseRefreshTokens(true)` | Refresh token `R0` được **tái sử dụng** trong token response theo policy | Nhiều yêu cầu có thể được chấp nhận khi token còn hiệu lực và điều kiện khác phù hợp | Dễ phối hợp Client nhưng **không cung cấp replay detection bằng rotation** |
| `reuseRefreshTokens(false)` | AS phát refresh token mới `R1`; token cũ không được tiếp tục dùng sau chuyển trạng thái hợp lệ | Yêu cầu thứ hai cần bị xử lý như token cũ/không hợp lệ; cách phát hiện và xử lý replay phụ thuộc implementation | Hỗ trợ mô hình rotation; yêu cầu atomicity, lưu trạng thái nhất quán và chiến lược replay |
| **Sender-constrained refresh token** | Client phải chứng minh sở hữu khóa/chứng chỉ ràng buộc token | Hai client instance chỉ dùng được nếu có credential hợp lệ theo binding; vẫn cần kiểm soát phiên bản/lưu trữ | Giảm khả năng sử dụng token bị lấy trộm; cần hạ tầng DPoP/mTLS tương thích |

**Điểm quan trọng về chuẩn:** RFC 9700 §4.14 yêu cầu Authorization Server **MUST** dùng **refresh token rotation hoặc sender-constraining** để phát hiện việc phát lại với **public clients** khi cấp refresh token. Với confidential clients, token phải được ràng buộc đúng client; chính sách bổ sung còn tùy threat model. Không phát refresh token cho mọi client mà không đánh giá rủi ro, phạm vi và nhu cầu thực tế.

**Điểm quan trọng về Spring:** Với Spring Authorization Server 1.5.x, `TokenSettings.isReuseRefreshTokens()` có giá trị mặc định là **`true`**. Gọi `reuseRefreshTokens(false)` tạo chính sách cấp refresh token mới khi refresh, nhưng **không đủ để suy ra** triển khai hiện tại đã có atomic compare-and-swap, sổ theo dõi cả họ token (token family), hoặc chính sách thu hồi cả family khi phát hiện replay. Các tính chất này phải được kiểm tra theo phiên bản, repository và luồng xử lý thực tế.

### 2.1. Ví dụ refresh token request/response

Client gửi **refresh token** qua HTTPS tới token endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Authorization: Basic REDACTED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R0_REDACTED&scope=orders.read
```

Mẫu phản hồi thành công (minh họa, **không phải token thật**):

```json
{
  "access_token": "A1_REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "R1_REDACTED",
  "scope": "orders.read"
}
```

Khi rotation được bật, Client phải lưu **`A1` và `R1` cùng nhau như một phiên bản trạng thái mới** trước khi để các luồng khác bắt đầu refresh. Trong chế độ reuse, server có thể trả cùng refresh token; Client vẫn phải xử lý response chính xác. Không giả định mọi response của mọi Authorization Server đều có `refresh_token`: cập nhật Client phải tuân theo response và hợp đồng OAuth2 Client đang dùng, **không gán `null`** rồi vô tình xóa credential còn hiệu lực.

`scope` được gửi khi refresh không được mở rộng vượt phạm vi authorization đã cấp. Refresh không phải cách để xin quyền mới hoặc làm lại consent. Access token/ID Token được cấp sau đó vẫn phải qua validation của Resource Server/Relying Party; refresh token không phải credential dùng để gọi API.

## 3. Dòng thời gian của race condition

### 3.1. Hai request Client cùng dùng một token cũ

```mermaid
sequenceDiagram
    autonumber
    participant R1 as Request 1
    participant R2 as Request 2
    participant Store as Client token store
    participant AS as Authorization Server

    R1->>Store: Đọc A0 đã hết hạn + R0
    R2->>Store: Đọc A0 đã hết hạn + R0
    R1->>AS: POST refresh_token=R0
    R2->>AS: POST refresh_token=R0
    AS-->>R1: Thành công: A1, R1 (rotate)
    AS-->>R2: invalid_grant vì R0 đã bị dùng
    R1->>Store: Ghi A1, R1
    Note over Store: Rủi ro: failure handler của R2<br/>xóa hoặc ghi đè trạng thái vừa lưu
    R2->>Store: Thao tác xử lý lỗi trên snapshot A0,R0
```

Nếu lỗi ở Request 2 kích hoạt handler xóa một `OAuth2AuthorizedClient` khỏi storage theo key chung, nó có thể xóa **cả trạng thái vừa được Request 1 lưu**. Vì vậy **khi thất bại, không xóa mù theo key**; nếu custom failure handler, phải kiểm tra record/version hiện hành còn là record mà request lỗi đã sử dụng hay không.

### 3.2. Hai pod AS chấp nhận cùng một refresh token

```mermaid
sequenceDiagram
    autonumber
    participant C1 as Client request A
    participant C2 as Client request B
    participant AS1 as AS pod 1
    participant AS2 as AS pod 2
    participant DB as Authorization store

    C1->>AS1: refresh R0
    C2->>AS2: refresh R0
    AS1->>DB: Tải authorization có current=R0
    AS2->>DB: Tải authorization có current=R0
    AS1->>AS1: Tạo A1,R1 từ snapshot R0
    AS2->>AS2: Tạo A2,R2 từ snapshot R0
    AS1->>DB: Ghi R1
    AS2->>DB: Ghi R2 nếu không có concurrency guard
    Note over DB: Last-write-wins hoặc trạng thái không nhất quán
```

Trong mô hình rotation **đúng**, một giao dịch phải thắng và **duy nhất một trạng thái kế tiếp** được commit từ `R0`. Nếu hai giao dịch cùng phát token và đều trả thành công, tính nhất quán đã bị vi phạm. Nếu một giao dịch nhận lỗi dùng lại token cũ, chính sách replay cần phân biệt cách **xử lý an toàn** chứ không cố đoán request nào là kẻ tấn công.

## 4. Cấu hình Spring Authorization Server: bật rotation đúng nơi

Một `RegisteredClient` confidential dùng Authorization Code và Refresh Token (Spring Authorization Server 1.x):

```java
import java.time.Duration;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

static RegisteredClient portalClient(String encodedClientSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientName("Portal Web")
            .clientSecret(encodedClientSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                    AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(5))
                    .refreshTokenTimeToLive(Duration.ofHours(8))
                    .reuseRefreshTokens(false) // Yêu cầu rotate khi refresh
                    .build())
            .build();
}
```

**Phạm vi ví dụ:** Đặt phương thức vào một class và lưu kết quả bằng `RegisteredClientRepository`. `encodedClientSecret` phải là chuỗi đã hash bằng `PasswordEncoder` của Spring Security; secret bản rõ nằm ở secret manager phía Client. Authorization Server hoàn chỉnh còn cần `SecurityFilterChain`, `AuthorizationServerSettings`, `OAuth2AuthorizationService`, cơ chế xác thực user, consent và JWK signing (nếu phát JWT).

Giải thích:

- `authorizationGrantType(REFRESH_TOKEN)` cho phép client được dùng Refresh Token grant; **không** có nghĩa mọi yêu cầu đều được phát refresh token.
- `reuseRefreshTokens(false)` cấu hình phát token mới trong response refresh khi điều kiện cấp phát phù hợp; chính sách này **không thay thế** atomic store hay phát hiện replay theo token family.
- `refreshTokenTimeToLive(...)` là TTL theo chính sách, **khác** với idle timeout, absolute family lifetime hoặc việc thu hồi cả họ token. Nếu muốn các giới hạn đó, cần thiết kế thêm.
- Các giá trị TTL 5 phút/8 giờ chỉ minh họa, phụ thuộc loại client, độ nhạy tài nguyên và yêu cầu phiên.
- Cấu hình `requireProofKey(true)` dành cho Authorization Code gốc; PKCE không thay cơ chế kiểm tra refresh token tại token endpoint.

### 4.1. Những thành phần thực sự liên quan đến refresh

| Thành phần Spring | Trách nhiệm |
|---|---|
| `RegisteredClientRepository` | Xác định client, grant type được phép, authentication method và `TokenSettings` |
| `OAuth2RefreshTokenAuthenticationProvider` | Xử lý Refresh Token grant trong AS theo cơ chế thư viện |
| `OAuth2AuthorizationService` | Tra cứu/lưu authorization cùng trạng thái access/refresh token |
| `JdbcOAuth2AuthorizationService` hoặc custom storage | Persistence; **không tự suy ra atomic rotation** nếu chưa xác minh hợp đồng cập nhật |
| `OAuth2TokenGenerator` / `OAuth2RefreshTokenGenerator` | Sinh token theo chính sách của authorization/token settings |
| `OAuth2AuthorizedClientRepository` hoặc `OAuth2AuthorizedClientService` | **Phía Client**: lưu authorized client/access/refresh token sau khi exchange |
| `OAuth2AuthorizedClientManager` và `RefreshTokenOAuth2AuthorizedClientProvider` | **Phía Client**: thực hiện re-authorization/refresh khi điều kiện phù hợp |

**Không nhầm:** `OAuth2AuthorizationService` là kho **phía AS**, còn `OAuth2AuthorizedClientService` là kho **phía OAuth2 Client**. Chúng nằm ở hai ứng dụng/tầng tin cậy khác nhau, nên phải thiết kế concurrency ở **cả hai phía**.

Spring Security hỗ trợ `OAuth2AuthorizedClientManager` tự làm mới access token khi có refresh token và access token cần refresh, nhưng **không coi mỗi lần gọi `authorize(...)` là một distributed single-flight lock**. Nhiều caller có thể đọc cùng snapshot cũ trước khi kết quả mới được lưu.

## 5. Phía Client: gom nhiều request thành một lần refresh (single-flight)

**Single-flight** nghĩa là nhiều request cần token mới cho **cùng authorized-client/session** cùng đợi **một thao tác refresh** thay vì đồng thời dùng refresh token cũ. Khóa phải có phạm vi đúng:

```text
lock key = tenant/issuer + client registration ID + principal/session identity
```

Không dùng một lock toàn hệ thống cho mọi user/client: nó biến refresh của user A thành nút thắt của user B. Nhưng cũng không dùng lock theo request ID: hai request cùng phiên lại nhận hai lock khác nhau, không giải quyết race.

### 5.1. Mẫu double-check trong một JVM

Mã Java dưới đây là **thuật toán minh họa**, độc lập API cụ thể của Spring Security. `TokenStore`, `TokenEndpoint` và `TokenPair` là interface/record do ứng dụng định nghĩa để thể hiện ranh giới đọc/lưu; cần triển khai chúng bằng OAuth2 Client API và storage thật.

```java
import java.time.Duration;
import java.time.Instant;

record TokenPair(
        String accessToken,
        Instant accessTokenExpiresAt,
        String refreshToken,
        long version) {}

interface TokenStore {
    TokenPair load(String key);

    // Thay trạng thái nếu record vẫn đúng phiên bản đã đọc.
    boolean replaceIfVersion(String key, long oldVersion, TokenPair next);
}

interface TokenEndpoint {
    // Gửi POST /oauth2/token qua TLS; không log credential.
    TokenPair refresh(String oldRefreshToken, long expectedNextVersion);
}

final class SingleFlightTokenService {
    private final Object monitor = new Object();
    private final String key;
    private final TokenStore store;
    private final TokenEndpoint endpoint;

    SingleFlightTokenService(
            String key, TokenStore store, TokenEndpoint endpoint) {
        this.key = key;
        this.store = store;
        this.endpoint = endpoint;
    }

    TokenPair getUsableToken() {
        TokenPair snapshot = store.load(key);
        if (usable(snapshot)) {
            return snapshot; // Fast path: không cần lock
        }

        synchronized (monitor) {
            TokenPair latest = store.load(key); // Double-check trong lock
            if (usable(latest)) {
                return latest;
            }
            if (latest == null || latest.refreshToken() == null) {
                throw new IllegalStateException("Reauthorization required");
            }

            TokenPair rotated = endpoint.refresh(
                    latest.refreshToken(), latest.version() + 1);

            if (!store.replaceIfVersion(key, latest.version(), rotated)) {
                // Có cập nhật đồng thời: đọc record mới, không dùng lại R cũ.
                TokenPair afterConflict = store.load(key);
                if (usable(afterConflict)) {
                    return afterConflict;
                }
                throw new IllegalStateException(
                        "Token state changed during refresh");
            }
            return rotated;
        }
    }

    private boolean usable(TokenPair pair) {
        return pair != null
                && pair.accessTokenExpiresAt() != null
                && pair.accessTokenExpiresAt().isAfter(
                        Instant.now().plus(Duration.ofSeconds(30)));
    }
}
```

**Phải đọc giới hạn của ví dụ:**

1. Một instance `SingleFlightTokenService` có một `monitor`, nên chỉ serialize những luồng **đang dùng đúng instance đó**. Khi triển khai nhiều bean, nhiều pod hoặc nhiều JVM, `synchronized` **không** bảo vệ chéo instance.
2. `replaceIfVersion` mang tính **optimistic concurrency** ở Client storage, nhưng không cứu được việc **hai pod đã gửi cùng `R0` đến AS**. Muốn ngăn duplicate refresh ngay từ trước token endpoint cần phối hợp liên instance.
3. Nếu call HTTP thành công nhưng lưu storage thất bại, token đã rotate ở AS. **Không được tự động gọi lại token endpoint bằng refresh token cũ** trong catch/finally. Phải đối chiếu/recover từ nguồn trạng thái tin cậy hoặc bắt đầu authorization mới.
4. API thật của Spring Security `OAuth2AuthorizedClientManager` có model token/authorized client riêng; ví dụ này chỉ giải thích double-check + CAS, **không phải class có sẵn** của framework.
5. `refreshToken` chỉ nên được giữ ở backend/secret-aware store; không ghi chuỗi này vào exception, log hoặc metrics label.

### 5.2. Spring Security OAuth2 Client và persist bản token mới

Ở phía Spring Security Client, `OAuth2AuthorizedClient` chứa `OAuth2AccessToken` và có thể có `OAuth2RefreshToken`. `OAuth2AuthorizedClientManager.authorize(...)` phối hợp `OAuth2AuthorizedClientProvider` (trong đó có refresh grant) với repository/service lưu trạng thái.

Thông thường, manager có thể lưu authorized client mới sau khi refresh thành công và **có thể loại bỏ authorized client cũ khi nhận `invalid_grant`** thông qua default failure handler. Với race, request thứ hai nhận `invalid_grant` có thể thao tác trên snapshot cũ. Nếu cần tùy biến failure handler, hãy áp dụng **compare-and-delete by version** hoặc kiểm tra token hiện hành trong storage trước khi xóa; không xóa mù bản ghi đã được một luồng khác cập nhật.

Ví dụ dùng Spring Security (chỉ minh họa bean manager, **không tự thêm single-flight lock**):

```java
@Bean
OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients) {

    OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .authorizationCode()
                    .refreshToken()
                    .build();

    DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                    registrations, authorizedClients);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

Mã trên thuộc **ứng dụng Client web servlet**. Khi dùng một service nền không có `HttpServletRequest`, cân nhắc `AuthorizedClientServiceOAuth2AuthorizedClientManager` với `OAuth2AuthorizedClientService` tương ứng. Cần chọn key theo `registrationId` và `principalName` nhất quán giữa các request; không dùng principal cố định cho các người dùng khác nhau.

**Lưu ý:** Không override success/failure handler tùy tiện rồi quên việc persist authorized client. Thay đổi nào cũng cần test rằng `refresh_token` mới thực sự được lưu và request tiếp theo dùng đúng phiên bản.

## 6. Nhiều Client pod: khóa phân tán, fencing và cập nhật nguyên tử

Giả sử hai pod của `portal-web` cùng phục vụ một user; cả hai dùng chung `OAuth2AuthorizedClientService` ở DB. Mỗi pod có lock `synchronized` riêng, nên vẫn có thể cùng dùng `R0`. Một chiến lược mạnh hơn gồm **single-flight liên instance** và **optimistic concurrency**.

### 6.1. Quy trình phối hợp liên instance

```mermaid
flowchart TD
    Start["API request cần access token"] --> Load["Đọc authorized client từ shared store"]
    Load --> Valid{"Access token còn<br/>dùng được?"}
    Valid -->|Có| Return["Dùng token hiện hành"]
    Valid -->|Không| Lock["Nhận distributed lock/lease<br/>cho key issuer+client+principal"]
    Lock --> Reload["Đọc lại record + version dưới lock"]
    Reload --> Valid2{"Có pod khác<br/>đã refresh?"}
    Valid2 -->|Có| Unlock["Release lock, dùng record mới"]
    Valid2 -->|Không| HTTP["POST refresh với refresh token hiện hành"]
    HTTP --> Persist["CAS save token response + version<br/>trước khi release lock"]
    Persist --> OK{"Commit thành công?"}
    OK -->|Có| Unlock
    OK -->|Không| Recover["Không retry R cũ<br/>Re-read/reconcile/fail closed"]
    Recover --> Unlock
    Unlock --> Return
```

Bước thiết yếu:

1. **Load token**, nếu access token còn hiệu lực sau một mức **clock skew** hợp lý thì không refresh.
2. **Acquire distributed lock theo authorized-client key**, có timeout, lease và cơ chế biết ai đang giữ lock.
3. **Re-read trong lock** vì pod khác có thể đã refresh xong ngay trước khi lock được cấp.
4. Nếu vẫn cần, gửi **một** request refresh. Lưu toàn bộ cặp access/refresh token mới **nguyên tử**, kèm version mới; không để thất bại ghi một nửa.
5. Sau commit mới release lock. Các caller còn lại đọc trạng thái mới; không tự dùng lại `R0`.
6. Nếu lock hết hạn khi refresh chậm, cần **fencing token/phiên bản** và CAS storage để tiến trình giữ lock cũ không ghi đè kết quả mới.

### 6.2. Vì sao một Redis `SET NX PX` đơn giản chưa đủ?

Distributed lock bằng Redis có thể phù hợp trong một số kiến trúc, nhưng **lease expiry** tạo vấn đề: pod A giữ lock, token endpoint chậm; lease hết hạn; pod B lấy lock mới và cũng refresh. Nếu A vẫn tiếp tục ghi sau khi B đã cập nhật, xảy ra lost update. Do đó:

- Lock phải có owner token, TTL phù hợp và release bằng thao tác kiểm tra ownership, không `DEL` mù một lock đã thuộc pod khác.
- Cần **fencing token tăng dần** hoặc storage version/CAS để chặn chủ lock cũ ghi dữ liệu.
- Không giả định lock phân tán bảo vệ được tất cả token endpoint request trong sự cố mạng, timeout hoặc pause dài. Phía Authorization Server **vẫn phải từ chối duplicate consumption**.
- Cân nhắc DB row lock nếu Client token store nằm cùng RDBMS; nhưng không giữ DB transaction/row lock lâu qua external HTTP call nếu độ trễ lớn — cần thiết kế lease/serialization an toàn và thử tải.

Một chiến lược thực tế là gom refresh qua **một token broker** hoặc service có quyền sở hữu token-state duy nhất, nhưng điểm trung tâm đó vẫn cần high availability, fencing và persistence bền vững.

## 7. Phía Authorization Server: kiểm tra và thay refresh token **nguyên tử**

Client cố tránh gửi trùng, nhưng **AS không thể tin Client luôn đúng**: attacker, mạng không ổn định, retry hoặc một Client library lỗi vẫn có thể gửi cùng `R0` nhiều lần. Authorization Server cần bảo đảm:

- Một refresh token không bị dùng quá số lần mà chính sách cho phép.
- Với rotation, **một phiên bản cũ chỉ có tối đa một successor hợp lệ**.
- Không có hai pod AS cùng báo thành công với hai successor khác nhau của cùng `R0`.
- Dữ liệu authorization/token và lịch sử cần thiết để phát hiện replay được commit nhất quán trước khi trả response.
- Nếu phát hiện replay thực sự, thực hiện chính sách thu hồi token family/sender binding phù hợp.

### 7.1. Thiết kế token family/lineage (mô hình đề xuất)

**Token family** là chuỗi refresh token sinh từ cùng một authorization grant, ví dụ:

```text
Authorization grant G42
  refresh family F42:
     R0 --rotate--> R1 --rotate--> R2
     R0: consumed
     R1: consumed
     R2: current
```

Một mô hình lưu trữ **tùy biến** có thể dùng:

| Trường | Ý nghĩa |
|---|---|
| `family_id` | Định danh family không đoán được / khóa nội bộ |
| `authorization_id` | Tham chiếu grant/authorization chủ sở hữu |
| `registered_client_id` và `principal_id` | Binding client/người dùng |
| `current_token_digest` | Digest an toàn cho token đang có hiệu lực |
| `generation` và `version` | Thế hệ rotation và phiên bản CAS |
| `status`, `revoked_at` | Active/revoked/expired và thời điểm |
| `absolute_expires_at`, `idle_expires_at` | Giới hạn family nếu chính sách yêu cầu |
| `last_rotated_at`, `last_used_at` | Audit tối thiểu, phát hiện bất thường |

Thêm một **token history/ledger** lưu `digest/token identifier` của token đã dùng và `family_id`, generation, consumed timestamp (thời gian giữ phù hợp với cửa sổ phát hiện replay). Khi `R0` đã bị thay, vẫn cần biết `R0` thuộc family nào để xử lý reuse. Nếu chỉ lưu **refresh token hiện tại** rồi xóa sạch mọi dấu vết `R0`, không thể tự khẳng định có replay detection theo mô hình RFC 9700.

Không đặt raw refresh token trong log, metrics hoặc SQL audit. Vì refresh token phải có entropy cao và khó đoán, có thể lưu **digest/HMAC có khóa riêng** để tra cứu và so khớp theo kiến trúc; bảo vệ khóa digest và kiểm soát giới hạn truy xuất. Không dùng hash của một token yếu như cách “bù” cho việc sinh token không đủ entropy.

### 7.2. Atomic compare-and-swap (CAS)

Ví dụ SQL minh họa cho một storage riêng (không phải schema có sẵn của Spring Authorization Server):

```sql
-- PSEUDOSQL: thực hiện trong một transaction có cách ly phù hợp.
-- :old_digest phải đã được nhận diện và ràng buộc với đúng family/client.
UPDATE refresh_family
SET current_token_digest = :new_digest,
    generation = generation + 1,
    version = version + 1,
    last_rotated_at = CURRENT_TIMESTAMP
WHERE family_id = :family_id
  AND current_token_digest = :old_digest
  AND version = :expected_version
  AND revoked_at IS NULL
  AND absolute_expires_at > CURRENT_TIMESTAMP;
```

Giả sử hai transaction đều muốn chuyển `R0` → successor. Chỉ **một** transaction được phép cập nhật với điều kiện `current_token_digest=hash(R0)` và `version=v`. Nếu update count bằng `0`, transaction thua **không được phát response thành công** với refresh token do nó đã sinh. Cần kiểm tra có phải token đã hết hạn, bị thu hồi, thuộc client khác, hoặc đã dùng rồi; nếu phát hiện reuse, xử lý chính sách replay.

Với thiết kế thực tế:

1. Tra cứu record theo hash/identifier của token và client binding, **không tin client_id do request tự tuyên bố nếu chưa xác thực**.
2. Mở transaction; khóa hoặc CAS record family và lưu ledger cho token cũ (hoặc kiểm tra ledger đã tồn tại).
3. Tạo token mới bằng bộ sinh số ngẫu nhiên mật mã, xây dựng trạng thái/authorization successor.
4. Atomically commit **family/version + ledger + token metadata/authorization** trong cùng giao dịch có thể kiểm chứng; unique constraint ngăn hai successor cho cùng thế hệ.
5. **Sau commit** mới trả token response. Nếu transaction rollback, không trả token mới.
6. Khi loser phát hiện conflict, không “retry CAS” bằng chính token cũ để cố thắng. Đánh giá replay theo policy và trả lỗi an toàn.

**Giới hạn rất quan trọng:** SQL trên chỉ minh họa ý tưởng CAS. Nếu refresh token/authorization còn được lưu trong `OAuth2AuthorizationService` ở một DB hoặc transaction khác, việc cập nhật family table **riêng rẽ** chưa đủ atomic; phải thiết kế adapter và transaction boundary nhất quán. Không áp đặt SQL này trực tiếp lên schema `oauth2_authorization` có sẵn rồi giả định concurrency sẽ an toàn.

### 7.3. Không mặc định `JdbcOAuth2AuthorizationService` đã là token-family CAS

`JdbcOAuth2AuthorizationService` giúp lưu `OAuth2Authorization` bền vững bằng JDBC, nhưng việc **lưu dữ liệu xuống DB** không tự chứng minh rằng logic **đọc → xác thực → rotate → save** đã được serialize dưới cạnh tranh hay duy trì toàn bộ lineage của refresh token. Khi đưa lên production:

- Kiểm tra behavior, schema và concurrency contract đúng **phiên bản thư viện đang chạy**.
- Test hai request đồng thời vào **hai pod AS** cùng refresh token cũ.
- Kiểm tra DB sau test: đúng một successor được chấp nhận, version không bị rollback, ledger đủ nhận diện old token nếu đang hứa replay detection.
- Nếu thiếu, triển khai cơ chế phù hợp qua custom service/provider/transactional layer hoặc nâng cấp khi upstream có bảo đảm được kiểm chứng; **không chỉ thêm `@Transactional` vào một controller bọc token endpoint** rồi mặc định đã đạt atomicity.

### 7.4. Cô lập giao dịch và khóa

| Kỹ thuật | Giải quyết được | Không tự giải quyết |
|---|---|---|
| `SELECT ... FOR UPDATE` ở hàng family | Serialize các transaction sửa cùng hàng trong DB | Client gửi request trùng; giao dịch quá dài; ledger/replay policy |
| Optimistic locking bằng `version` | Chặn lost update khi tất cả writer kiểm tra version | HTTP response đã mất; token phát ngoài transaction; xử lý conflict |
| Unique constraint `(family_id, consumed_generation)` | Chặn hai lần ghi successor cho cùng thế hệ | Ràng buộc xác thực client, phạm vi cấp quyền và UX |
| Transaction DB | All-or-nothing cho những bảng **thuộc cùng transaction** | Distributed transaction với KMS, service ngoài, cache, token response qua mạng |
| Distributed lock trước request | Hạn chế work/race liên pod | Lease expiry, fencing và các actor ngoài lock |
| Serializable isolation | Hạn chế một số anomaly | Thiết kế replay/rotation, lỗi retry hoặc mất response; vẫn có serialization failures phải xử lý |

## 8. Replay detection: đồng thời hợp lệ và tấn công trông giống nhau

RFC 9700 §4.14 mô tả rotation như sau: khi một refresh token đã bị thay thế xuất hiện trở lại, server biết có dấu hiệu **replay** nhưng **không thể xác định** request đến từ người dùng hợp lệ hay attacker chỉ bằng token đó. Vì vậy mô hình detection chặt có thể **thu hồi refresh token đang còn hiệu lực của cả family**, buộc client phải có authorization grant mới.

### 8.1. Ba tình huống khác nhau

| Tình huống | Trạng thái ở server | Phương án an toàn |
|---|---|---|
| Hai request hợp lệ từ cùng client cùng dùng `R0` | Một request rotate thành `R1`, request sau dùng `R0` đã consumed | Client single-flight để **tránh tạo** race; AS xử lý old token theo chính sách replay |
| Attacker có `R0`, user đã chuyển tới `R1` | Attacker dùng lại `R0` | Phát hiện token đã consumed, revocation family, alert/reauthorization |
| Response `R1` bị mất, client retry `R0` | AS đã commit `R1`; client không biết successor | **Không retry mù**; cần recovery/reauthorization đã thiết kế, tránh cho qua replay |

**Không thể quyết định an toàn chỉ dựa trên khoảng cách 50 ms hay IP giống nhau.** Một “grace window” cho phép token cũ được dùng lại sau rotation có thể che giấu replay thật. Nếu hệ thống chọn cơ chế giảm false positive, phải có threat model rõ ràng, ràng buộc instance/sender, giới hạn cực chặt và đánh giá xem còn đáp ứng yêu cầu **phát hiện replay** của RFC 9700 hay không. Không nên mô tả grace period là tính năng bảo mật mặc định.

### 8.2. Rotation và sender-constrained token

Với một public client, nếu không rotation thì RFC 9700 yêu cầu cơ chế sender-constrained như DPoP/mTLS phù hợp. Sender-constrained token có thể giảm khả năng kẻ lấy token đơn thuần sử dụng nó, nhưng:

- Cần đối chiếu binding trong **mọi refresh request**.
- Việc mất/private key bị lộ vẫn cần chính sách xử lý riêng.
- Các client instance dùng khóa khác nhau có thể không dùng chung token nếu token gắn với khóa của instance ban đầu.
- Chạy nhiều request đồng thời vẫn có thể gây lost update nếu Client token store không nhất quán; sender-constraining **không phải distributed single-flight**.

## 9. Mất response, timeout, retry và cách phục hồi

### 9.1. Vì sao HTTP timeout không có nghĩa là request chưa được xử lý?

Giả sử Client gửi `R0`, AS commit `R1`, nhưng response mất giữa đường. Client chỉ biết request **timeout**; nó không biết server đã commit hay chưa. Gửi lại `R0` là không an toàn trong mô hình rotation chặt vì:

- Nếu AS đã commit, `R0` là token đã dùng và request retry có thể kích hoạt cảnh báo/revocation family.
- Nếu AS chưa commit, `R0` có thể còn hợp lệ, nhưng Client không thể phân biệt hai tình huống từ một timeout.
- Nếu client tự tạo request refresh thứ hai sau khi mất response, nguy cơ tạo **hai successor** ở AS lỗi atomicity tăng lên.

**Chính sách Client nên tách loại lỗi:**

| Loại lỗi | Ý nghĩa | Hành động an toàn |
|---|---|---|
| `invalid_grant` từ AS | Refresh token sai/hết hạn/đã dùng/bị thu hồi hoặc không còn hợp lệ | Re-read shared token store; nếu có version mới dùng version đó, nếu không thì yêu cầu authorization mới |
| `invalid_client` | Client authentication không hợp lệ | Dừng tự động refresh, sửa cấu hình/credential và báo vận hành |
| HTTP 429 / 503 **trước khi request chắc chắn được gửi/commit** | Server đang quá tải/tạm không sẵn sàng | Có thể retry với backoff theo policy **nếu trạng thái chưa bị thay đổi đã được xác nhận** |
| Timeout/connection reset **sau khi đã gửi request** | Kết quả **không xác định** | Không retry cùng `R0` mù; thử đọc trạng thái dùng chung hoặc quy trình recover/reauth |
| CAS ghi Client token store thất bại | Có thể pod khác đã cập nhật; AS có thể đã rotate | Re-read version; không ghi đè bằng bản cũ hay gửi lại refresh token cũ |
| AS trả token response không hợp lệ | Response thiếu trường cần thiết, TLS/issuer sai, decode lỗi | Fail closed, không ghi trạng thái nửa vời; đánh giá recovery nếu AS đã rotate |

Việc “retry chỉ khi chắc chắn request chưa được xử lý” trên thực tế khó đảm bảo qua HTTP; client thường nên **fail closed và reauthorize** thay vì tự tạo một cơ chế retry có thể kích hoạt replay. Nếu sản phẩm cần trải nghiệm liền mạch khi response mất, có thể thiết kế một **protocol idempotency/recovery có xác thực riêng** giữa client và AS, nhưng phải ràng buộc client, token generation, request identity, TTL và tính nhất quán của response; đây **không phải** tính năng sẵn có của OAuth2 Refresh Token grant.

### 9.2. Lưu token phải theo cặp, có version

Trạng thái của Client không chỉ là một refresh token string, mà là một bản ghi có version:

```text
AuthorizedClientState {
  key: (issuer, registrationId, principalId, tenantId),
  accessToken: A1,
  accessTokenExpiresAt: ...,
  refreshToken: R1,
  refreshTokenExpiresAt: ...,
  version: 18,
  updatedAt: ...
}
```

Khi đổi `R0` → `R1`, phải commit **access token mới, refresh token mới, expiry và version** trong một thao tác storage nhất quán. Nếu dùng Redis, một thao tác Lua/transaction có CAS hoặc cấu trúc versioned atomic; nếu RDBMS, update có `WHERE version = :old_version`. Không cập nhật lần lượt từng field trong nhiều lệnh độc lập rồi để request khác đọc trạng thái dở dang.

Client nên **đọc lại** record sau khi nhận conflict, thay vì tự hoàn tác sang token cũ. Một request API đã có access token A0 còn hạn có thể tiếp tục theo chính sách; request mới cần token A1 phải dùng state mới nhất. Token không còn hạn hoặc family bị revoke ⇒ yêu cầu login/authorization phù hợp.

## 10. Quyền truy cập, token scope và logout khi refresh đồng thời

Concurrency không làm thay đổi các bất biến bảo mật của OAuth2:

1. AS phải xác thực confidential client, bảo đảm refresh token thuộc đúng client, grant và subject. Public client phải có cơ chế bảo vệ refresh theo RFC 9700.
2. Scope của access token mới **không vượt quá** các quyền đã cấp và phạm vi request/consent phù hợp. Không cho phép attacker mở rộng scope bằng refresh.
3. Token bị revoke, authorization bị xóa hoặc user/consent/chính sách đã thay đổi phải được xử lý theo policy. Một refresh đang chạy đồng thời với logout/revoke cần có **thứ tự commit** và hành vi rõ: không phát token mới sau khi quyết định thu hồi có hiệu lực.
4. Nếu AS cấp JWT access token, việc revoke refresh token **không tự động thu hồi JWT đã phát** đang còn hạn. Resource Server có thể cần TTL ngắn, introspection/status check hoặc danh sách thu hồi tùy yêu cầu.
5. Trong OIDC, refresh grant **không đồng nghĩa người dùng mới đăng nhập lại**. Không coi `iat` mới của access token là `auth_time` mới; nếu ID Token được cấp ở refresh, kiểm tra quy tắc OIDC và claim tương ứng.
6. Không trộn token state của hai người dùng, hai tenant hoặc hai client registration chỉ vì chung một browser, một pod hoặc một Redis key.

### 10.1. Refresh song song với revoke/logout

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant Client as Client BFF
    participant AS as Authorization Server
    participant DB as Shared token/authorization store

    Client->>AS: Refresh R0
    User->>AS: Thu hồi phiên/authorization grant
    par Hai giao dịch tranh trạng thái
        AS->>DB: Kiểm tra và chuyển R0 -> R1 (transaction)
    and
        AS->>DB: Đặt grant/family revoked (transaction)
    end
    DB-->>AS: Thứ tự commit được quyết định
    Note over AS,DB: Không được để refresh từ snapshot cũ<br/>phục hồi family sau khi revoked
    AS-->>Client: Token mới nếu refresh thắng hợp lệ, hoặc lỗi nếu đã revoke
```

Nếu revoke commit **trước** khi refresh đổi trạng thái, refresh phải bị từ chối. Nếu refresh commit **trước** revoke, revoke tiếp đó phải vô hiệu hóa family/successor phù hợp. Không cho một update dùng snapshot cũ xóa `revoked_at` hoặc chuyển family về `active` sau revoke. Luồng revoke và refresh cần dùng cùng cơ chế atomic state/transaction.

## 11. Kiểm thử race condition một cách có kiểm soát

Không thể kiểm thử concurrency đáng tin bằng cách gọi refresh tuần tự hai lần rồi kết luận hệ thống an toàn. Cần **đồng bộ thời điểm bắt đầu**, cho hai request đọc cùng snapshot, đo kết quả và kiểm tra DB thật sau commit. Dùng token/credential giả ở môi trường staging hoặc integration test; không hiển thị refresh token nguyên văn trong log/test report.

### 11.1. Ma trận kiểm thử

| Ca kiểm thử | Thiết lập | Kỳ vọng |
|---|---|---|
| Refresh một lần | `R0` hợp lệ, access token hết hạn | Cấp `A1` và nếu rotation bật thì `R1`; version tăng đúng |
| Hai request trong cùng JVM | 10 caller cùng authorized client hết hạn | Client single-flight tạo **một** token endpoint call (trong cùng service instance) |
| Hai Client pod | Pod A/B dùng cùng record expired | Chỉ một refresh được gửi theo chiến lược distributed coordination; pod còn lại dùng kết quả đã persist |
| Hai AS pod nhận cùng `R0` | Bypass Client single-flight, gửi đồng thời | **Không** có hai successor thành công; DB chỉ có trạng thái hợp lệ cuối và xử lý loser theo policy |
| Lost update tại Client store | Cố ghi record version cũ sau khi R1 đã commit | CAS từ chối; không trở lại R0 |
| Replay token cũ | Dùng `R0` sau khi R1 đã commit | Từ chối; nếu có family policy thì revoke successor và ghi security event |
| Timeout sau commit | AS đã commit R1 nhưng chặn response | Client không tự retry mù R0; có đường reauthorize/recover rõ |
| Crash trước commit | Dừng AS khi transaction chưa commit | Không trả thành công; DB không có trạng thái nửa vời |
| Crash sau commit trước response | AS commit xong rồi mất kết nối | Client nhận biết kết quả không xác định và xử lý an toàn |
| Lease hết hạn | Pod A refresh chậm; pod B nhận lock | Fencing/CAS ngăn pod A stale ghi đè; AS không chấp nhận duplicate |
| Refresh song song revoke | Một transaction refresh, một transaction revoke | Không “hồi sinh” family đã revoke sau commit; thứ tự nhất quán |
| Refresh token hết hạn | Token đã quá TTL/idle/absolute lifetime | `invalid_grant`/lỗi phù hợp, không cấp token |
| Scope vượt quyền | Refresh request thêm scope chưa được cấp | Từ chối/không cấp quyền vượt authorization |
| Client sai | Token R0 thuộc Client A nhưng B cố refresh | Từ chối, không tiết lộ thông tin family A |
| Sai tenant/principal | Cùng client registration, khác principal | Không dùng chung token state/lock một cách nhầm lẫn |
| Load test | Hàng trăm user/phiên refresh đồng thời | Không khóa toàn hệ thống; latency, DB contention và tỷ lệ lỗi trong SLO |
| Multi-node persistence | Pod AS A cấp R1; pod AS B xác minh R1 | R1 được chấp nhận theo policy, trạng thái đồng nhất |
| Reuse mode | `reuseRefreshTokens(true)`, hai request hợp lệ | Kiểm tra hành vi server và giới hạn công suất; **không** khẳng định replay detection bằng rotation |
| Public client | Client có refresh token và chính sách public | Verify rotation hoặc sender-constraining theo RFC 9700 |
| Client failure handler | Request A đã lưu R1; request B `invalid_grant` trên R0 | Handler B không xóa record mới R1 một cách mù |

### 11.2. Dùng barrier để tạo cạnh tranh thực

Ví dụ JUnit 5/Java minh họa điều phối đồng thời **vào một hàm gọi refresh đã có trong test**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

@Test
void onlyOneRefreshMayCommitForSameOldToken() throws Exception {
    int callers = 2;
    CountDownLatch ready = new CountDownLatch(callers);
    CountDownLatch start = new CountDownLatch(1);

    ExecutorService pool = Executors.newFixedThreadPool(callers);
    try {
        List<Future<RefreshResult>> futures = new ArrayList<>();
        for (int i = 0; i < callers; i++) {
            futures.add(pool.submit(() -> {
                ready.countDown();
                if (!start.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Barrier timeout");
                }
                return callTokenEndpointWithSameR0();
            }));
        }
        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        List<RefreshResult> results = new ArrayList<>();
        for (Future<RefreshResult> future : futures) {
            results.add(future.get(15, TimeUnit.SECONDS));
        }

        assertEquals(1, results.stream()
                .filter(RefreshResult::success).count());
        // Kiểm tra DB thật: đúng một successor đã commit, history hợp lệ.
        assertPersistedFamilyHasAtMostOneSuccessorForR0();
    } finally {
        pool.shutdownNow();
    }
}
```

**Đây là đoạn test skeleton**, các phương thức `callTokenEndpointWithSameR0()`, `assertPersistedFamilyHasAtMostOneSuccessorForR0()` và kiểu `RefreshResult` phải được dự án định nghĩa. Mẫu kiểm tra `success==1` phù hợp hệ thống được thiết kế chấp nhận một lần refresh hợp lệ; nếu có **revocation family ngay khi phát hiện reuse**, successor có thể bị thu hồi sau đó và test phải kiểm tra thêm trạng thái `revoked`.

Barrier ở phía caller chỉ giúp các request được gửi gần nhau. Để chứng minh atomicity của AS, có thể dùng test hook/barrier ở chỗ **cả hai request đã đọc cùng version** trước khi CAS, hoặc điều khiển DB transaction bằng test harness; tránh thêm hook này vào production. Chạy test lặp lại trên **hai instance thật** và trên database/driver/isolation level giống production.

### 11.3. Assert những bất biến nào?

- **Không double-success:** tối đa một chuyển đổi `R0 → Rnext` được commit thành công.
- **No lost update:** Client store không thể quay về R0 sau khi đã ghi R1; DB AS không có hai current token của cùng family.
- **No replay bypass:** R0 đã tiêu thụ không còn dùng phát token mới trái policy.
- **No token leakage:** test/log/trace không có raw token, client secret hoặc Authorization header.
- **No accidental deletion:** một failed refresh trên snapshot cũ không xóa state mới của Client.
- **Revocation wins:** revoke đã commit không thể bị refresh “hồi sinh”.
- **Multi-tenant isolation:** các client/user khác nhau không chặn nhau vô lý hoặc chia sẻ token.
- **Observability:** có metrics cho conflict/replay/failure mà không biến token value thành label.

## 12. Vận hành, giám sát và xử lý sự cố

### 12.1. Metrics và log có ích

| Nhóm metric/event | Mục đích |
|---|---|
| `refresh_attempt_total{outcome}` | Tỷ lệ thành công/`invalid_grant`/`invalid_client`/timeout |
| `refresh_rotation_conflict_total` | Phát hiện tranh chấp khi đổi token; tăng bất thường có thể do client không single-flight |
| `refresh_family_replay_detected_total` | Giám sát token cũ đã tiêu thụ bị gửi lại theo policy |
| `refresh_family_revoked_total{reason}` | Đánh giá tác động bảo mật và trải nghiệm đăng nhập lại |
| `client_singleflight_wait_seconds` | Thời gian request chờ một lần refresh, phân biệt cùng JVM và liên pod |
| `token_store_cas_conflict_total` | Tìm lost update tiềm ẩn ở Client storage |
| `refresh_token_endpoint_latency` | Phát hiện latency khiến lease hết hạn/timeout |
| `reauthorization_required_total{reason}` | Đo số lần người dùng bị buộc đăng nhập lại |

Dùng nhãn **low cardinality** như outcome, environment, loại client; không đặt raw `refresh_token`, `access_token`, user ID, session ID hoặc email làm label. Với audit cần điều tra riêng, có thể dùng **correlation ID/hashed identifier** với quyền truy cập phù hợp và retention hạn chế. Tránh request/response body logging tại token endpoint.

### 12.2. Runbook khi xuất hiện nhiều `invalid_grant`

1. Kiểm tra liệu sự cố bắt đầu cùng lúc bật `reuseRefreshTokens(false)`, triển khai thêm Client pod, đổi storage hoặc cập nhật Spring Security.
2. Dùng metrics để phân biệt: refresh **trùng tại Client**, **token đã hết hạn/đã thu hồi**, **clock skew**, hay **DB conflict** tại Authorization Server.
3. Xác nhận Client đã lưu `refresh_token` mới, key lưu đúng user/client/tenant, và failure handler không xóa record mới của request khác.
4. Kiểm tra lock/lease/fencing của các Client pod; không suy từ một pod hoạt động tốt rằng toàn cluster đã an toàn.
5. Kiểm tra persistence/transaction isolation và audit ledger tại AS. Tìm duplicate successor, missing consumed state hoặc revoke bị ghi đè.
6. Nếu nghi **token bị đánh cắp**, áp dụng xử lý sự cố bảo mật, thu hồi family/authorization theo chính sách và buộc cấp grant mới; không “chữa cháy” bằng nới acceptance của refresh token cũ.
7. Thử tải và test race trên staging, quan sát cải thiện sau fix. Không bật debug log ghi token raw trên production.

### 12.3. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Một user phải đăng nhập lại khi mở nhiều tab | Nhiều refresh cùng R0; loser kích hoạt revoke/failure handler | Single-flight theo session, đọc lại token trước refresh, CAS failure handler |
| Có lúc token mới, có lúc token cũ sau refresh | Pod Client ghi đè authorized client snapshot cũ | Versioned storage và atomic compare-and-swap |
| AS trả hai refresh token mới từ một R0 | Đọc/sửa/save không được serialize trong AS store | Atomic consumption/transaction + constraint, test đa pod |
| Redis lock vẫn xuất hiện race | Lease expired, thiếu fencing, release nhầm owner | Fencing token, CAS storage, kiểm soát lease và latency |
| `invalid_grant` tăng sau mạng timeout | Client retry R0 trong khi AS đã commit R1 | Không retry mù, re-read/recover hoặc reauthorize |
| `invalid_grant` nhưng record còn hiệu lực bị xóa | Default/custom failure handler xử lý key mà không so version | Compare-and-delete hoặc custom handling theo tình huống |
| Hai người dùng chia sẻ token | Key storage quá rộng (chỉ có `client_id`) | Thêm principal/tenant/issuer/registration ID |
| Dữ liệu AS nhất quán khi chạy một pod, lỗi khi scale | In-memory store hoặc local cache stale | Shared DB + transaction, cache invalidation, concurrency tests |
| Logout rồi vẫn refresh được | Race refresh/revoke hoặc revoke không tác động family | Dùng chung trạng thái revoke và transaction CAS |
| Token bị lộ trong APM/log | Ghi HTTP body/headers hoặc response JSON | Bỏ raw token logs, secret scanning và rotate khi đã lộ |
| Bật reuse để “hết lỗi” | Che race Client, mất replay detection bằng rotation | Giải quyết concurrency, đánh giá bảo vệ public client theo RFC 9700 |
| Refresh liên tục trước hạn | Skew quá lớn hoặc expiry parsing sai, nhiều request gọi manager đồng thời | Chọn skew hợp lý và single-flight, đo token endpoint load |

## 13. Checklist triển khai production

- [ ] Đã quyết định **có cần phát refresh token** cho từng loại client hay không; không dùng Refresh Token grant cho `client_credentials` khi không phù hợp.
- [ ] Đã phân biệt reuse vs rotation; với **public client**, đáp ứng RFC 9700 bằng rotation hoặc sender-constraining nếu phát refresh token.
- [ ] `RegisteredClient` có `AuthorizationGrantType.REFRESH_TOKEN` và `TokenSettings` phù hợp (TTL, `reuseRefreshTokens(false)` nếu cần rotation).
- [ ] Client thực hiện **single-flight theo authorized-client key**, double-check state và dùng versioned atomic storage.
- [ ] Với nhiều Client pod, có phối hợp liên instance hoặc một token broker được thiết kế đúng; `synchronized` không được coi là distributed lock.
- [ ] Lock/lease có owner, timeout, fencing/CAS; không để holder cũ ghi đè successor.
- [ ] AS có **atomic consumption**/commit của refresh token, không chấp nhận hai successor cùng một thế hệ.
- [ ] Nếu tuyên bố **replay detection bằng rotation**, có lưu lineage/consumed token state và chính sách revoke family khi phát hiện reuse.
- [ ] Client không tự retry refresh token cũ khi response timeout hoặc trạng thái AS không xác định.
- [ ] Token response được persist theo cặp access/refresh + expiry + version, không có partial write.
- [ ] Failure handler không xóa bản ghi đã được caller khác refresh thành công.
- [ ] Refresh grant vẫn giới hạn client binding, scope, subject, consent và revocation; token mới không tự mở rộng quyền.
- [ ] Các storage/authorization service được chia sẻ giữa các AS pod, có isolation/transaction/constraint phù hợp.
- [ ] Có test đồng thời trong một JVM, multi Client pod, multi AS pod, lost response, stale write, logout/revoke và replay.
- [ ] Có metric, alert, audit và runbook nhưng không log raw token/credential; private key/client secret được bảo vệ qua secret manager.
- [ ] Đã xác minh các bảo đảm concurrency bằng **phiên bản Spring Security/Spring Authorization Server và DB driver đang triển khai**, không chỉ dựa vào tên API.

**Câu hỏi tự kiểm tra**

1. Vì sao `reuseRefreshTokens(false)` không tự bảo đảm chỉ một request đồng thời được phép thay `R0` bằng token mới?
2. `synchronized` ở OAuth2 Client giải quyết trường hợp nào và vì sao không giải quyết trường hợp hai pod?
3. Một request nhận `invalid_grant` sau khi request khác đã lưu R1. Vì sao xóa authorized client theo key không kiểm version có thể gây mất phiên?
4. Khi AS đã commit R1 nhưng HTTP response bị mất, vì sao retry R0 không luôn an toàn?
5. Token family/consumed ledger giúp phát hiện replay khác gì chỉ lưu refresh token hiện hành?
6. CAS ở AS khác CAS ở Client storage thế nào? Cần cả hai vì sao?
7. Vì sao Redis lock có TTL cần thêm fencing/version ở storage?
8. Thu hồi consent/refresh token có tự vô hiệu mọi JWT access token còn hạn ở Resource Server không?
9. Với public client được cấp refresh token, RFC 9700 yêu cầu cơ chế chống replay thuộc loại nào?
10. Bạn sẽ dùng barrier và kiểm tra DB thế nào để chứng minh hai AS pod không đồng thời cấp hai successor hợp lệ?

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Refresh Token grant, client binding và token endpoint.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): §2.2.2 và §4.14 về bảo vệ refresh token, rotation, sender-constraining và replay detection.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constraining ở các triển khai hỗ trợ DPoP.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): binding chứng chỉ theo hạ tầng hỗ trợ.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationService` và token settings.
- [Spring Authorization Server — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html): giá trị mặc định `reuseRefreshTokens`, refresh TTL.
- [Spring Authorization Server — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html): `reuseRefreshTokens(boolean)`.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): token endpoint, providers và extension points.
- [Spring Security — OAuth2 Client Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `OAuth2AuthorizedClientManager` và persistence handlers.
- [Spring Security — OAuth2 Client Authorization Grant Support](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Refresh Token provider và client behavior.
- [Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): xử lý save sau thành công và removal khi `invalid_grant`.
