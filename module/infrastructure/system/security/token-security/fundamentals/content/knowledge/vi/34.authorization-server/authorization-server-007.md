# Authorization service trong OAuth 2.0 Authorization Server

## 1. Authorization service là gì?

Trong mô hình **OAuth 2.0/OIDC**, **authorization server (AS)** là thành phần xác thực người dùng hoặc client, xử lý yêu cầu ủy quyền và cấp token để client truy cập tài nguyên. Sau khi AS cấp một **authorization code**, **access token** hay **refresh token**, hệ thống cần theo dõi trạng thái cấp quyền, điều kiện sử dụng và hiệu lực của chúng. Chức năng đó thuộc lớp **authorization service**.

Trong **Spring Authorization Server**, **OAuth2AuthorizationService** là interface lưu, tìm và xóa các đối tượng **OAuth2Authorization**. Đây là trọng tâm của bài học. Cần phân biệt:

- **Authorization service** quản lý trạng thái authorization/grant phía AS.
- **OAuth2TokenGenerator** tạo giá trị token; không phải authorization service tự ký mọi JWT.
- **OAuth2AuthorizationConsentService** lưu sự đồng ý của người dùng với client/scopes, khác vòng đời từng authorization.
- **RegisteredClientRepository** lưu thông tin client đã đăng ký, ví dụ client_id, redirect URI và grant types.
- **Resource server** kiểm tra access token và thực thi quyền đối với API; nó không trực tiếp cấp refresh token.
- **AuthorizationFilter** ở Spring Security Resource Server bảo vệ endpoint; nó khác **OAuth2AuthorizationService** ở phía AS.

Một ứng dụng đăng nhập qua Authorization Code Flow cần lưu code được phát hành để **lần đổi code sau** kiểm tra đúng client, redirect URI, PKCE và trạng thái chưa dùng. Sau khi đổi code, AS lưu trạng thái access/refresh token để phục vụ refresh, introspection, revocation và các chính sách liên quan.

**Authorization service không tự bảo đảm an toàn chỉ vì có dữ liệu trong database.** Sự an toàn đến từ cách provider kiểm tra token, transaction đồng bộ, cấu hình client và chính sách bảo mật được thực thi xuyên suốt.

## 2. Vị trí trong luồng OAuth 2.0/OIDC

| Thành phần | Vai trò |
|---|---|
| Client | Bắt đầu flow, nhận authorization code/token và sử dụng access token đúng audience |
| Resource owner | Người dùng/chủ thể có thể cấp đồng ý cho một yêu cầu ủy quyền |
| Authorization server | Xác thực, cho phép grant, cấp token, phục vụ refresh/revocation/introspection |
| OAuth2AuthorizationService | Lưu và tìm trạng thái OAuth2Authorization của grant |
| OAuth2AuthorizationConsentService | Lưu/tìm thông tin consent của principal cho registered client |
| RegisteredClientRepository | Lưu đăng ký client, redirect URI, scope và các thiết lập |
| OAuth2TokenGenerator | Tạo authorization/access/refresh/ID token theo flow thích hợp |
| Resource server | Xác thực access token rồi kiểm tra scope, audience và quyền nghiệp vụ |

~~~mermaid
flowchart LR
    C[Client] -->|Authorization và token requests| AS[Authorization Server]
    AS --> P[OAuth2 Authentication Providers]
    P --> RC[RegisteredClientRepository]
    P --> CS[OAuth2AuthorizationConsentService]
    P --> S[OAuth2AuthorizationService]
    P --> TG[OAuth2TokenGenerator]
    S --> DB[(Authorization Store)]
    CS --> CBD[(Consent Store)]
    AS -->|Access token| C
    C -->|Access token| RS[Resource Server]
    RS -->|Introspection nếu dùng| AS
~~~

Trong kiến trúc này, **access token** có thể là **JWT tự chứa** hoặc **opaque token**. Resource server có thể tự xác thực JWT bằng chữ ký của issuer hoặc hỏi AS qua introspection; **refresh token** chỉ dành cho token endpoint của AS. **OIDC ID token** phục vụ OIDC client xác minh đăng nhập, không mặc nhiên là access token dành cho API.

Mối quan hệ tin cậy phải được giữ: **client_id** không phải bí mật; public client không thể giữ client_secret an toàn trong browser; authorization code cần giới hạn một lần sử dụng; resource server chỉ chấp nhận issuer/audience và scope được phép.

## 3. Đối tượng OAuth2Authorization lưu những gì?

**OAuth2Authorization** là mô hình trạng thái của một grant. Nó gắn một registered client với principal, grant type, tập scope đã được cấp và các token/metadata trong phạm vi authorization đó.

| Thuộc tính | Ý nghĩa bảo mật |
|---|---|
| id | Định danh nội bộ của bản ghi authorization |
| registeredClientId | Kết nối grant với client đã được AS đăng ký/kiểm tra |
| principalName | Chủ thể liên quan tới grant |
| authorizationGrantType | Loại grant, ví dụ authorization_code hoặc client_credentials |
| authorizedScopes | Phạm vi thực sự được cấp, có thể hẹp hơn scope client yêu cầu |
| attributes | Ngữ cảnh giao thức do provider lưu, không tùy tiện tin từ client |
| authorizationCode | Mã ủy quyền nếu flow cấp code, có trạng thái sử dụng/hết hạn |
| accessToken | Access token và metadata liên quan |
| refreshToken | Refresh token nếu grant/chính sách cho phép |
| OIDC ID token | ID token nếu flow OIDC cấp một token như vậy |
| token metadata | Thông tin trạng thái như invalidated và claims tùy loại token |

Ví dụ trạng thái khái niệm sau khi đổi authorization code thành công:

~~~text
Authorization grant:
  id                 = auth-123
  registeredClientId = browser-app-registered
  principalName      = user-42
  grantType          = authorization_code
  authorizedScopes   = { "orders.read" }

  CODE_A -> USED / INACTIVE
  AT1    -> ACTIVE, expiresAt: ...
  RT1    -> ACTIVE, expiresAt: ...
~~~

Đây là **mô hình diễn giải**, không phải định dạng serialization chính thức. Không phải mọi grant có code, refresh token hay ID token. Ví dụ grant **client_credentials** thường không có authorization code và không nên được giả định có refresh token.

### 3.1. Bản ghi tồn tại chưa chắc token còn hiệu lực

Authorization service có thể tìm thấy bản ghi chứa token đã **hết hạn**, **vô hiệu hóa** hoặc không còn đủ điều kiện sử dụng. Vì vậy logic OAuth không thể dừng ở việc gọi findByToken và thấy kết quả khác null.

Đối với token được lưu trong mô hình Spring Authorization Server, trạng thái **active** cần được kiểm tra trong ngữ cảnh phù hợp. Các ràng buộc khác như registered client, redirect URI, PKCE, scope, sender binding và chính sách của grant vẫn phải do provider thực thi.

### 3.2. Authorization khác consent

**OAuth2AuthorizationConsent** lưu việc người dùng đã đồng ý cho client thực hiện những quyền nào. Consent có thể vẫn tồn tại sau khi một authorization code đã dùng hoặc access token đã hết hạn. Ngược lại, việc xóa consent **không tự chứng minh** toàn bộ refresh token đang có đã bị thu hồi.

Khi sản phẩm có tính năng “Gỡ quyền truy cập của ứng dụng”, hãy quyết định rõ phải **xóa consent**, **thu hồi authorization/token**, hoặc thực hiện cả hai theo chính sách. Không đồng nhất các thao tác đó.

## 4. Bốn phương thức của OAuth2AuthorizationService

Ở mức khái niệm, interface có bốn thao tác:

~~~java
public interface OAuth2AuthorizationService {
    void save(OAuth2Authorization authorization);
    void remove(OAuth2Authorization authorization);
    OAuth2Authorization findById(String id);
    OAuth2Authorization findByToken(
        String token, OAuth2TokenType tokenType
    );
}
~~~

Chữ ký đã được rút gọn để tập trung vào ý nghĩa; import, annotations và các khác biệt nhỏ giữa phiên bản không được trình bày.

| Phương thức | Cách sử dụng | Rủi ro nếu dùng sai |
|---|---|---|
| save | Lưu authorization mới hoặc cập nhật trạng thái sau đổi code/refresh/revoke | Ghi đè, mất cập nhật hoặc phát hành token khi state không được lưu |
| remove | Xóa authorization theo chính sách | Không tự vô hiệu hóa JWT mà resource server đang kiểm tra offline |
| findById | Tìm grant theo định danh nội bộ | Trả dữ liệu nhạy cảm cho bên không có quyền |
| findByToken | Tìm authorization liên quan tới token của loại được chỉ định | Nhầm “tìm thấy” với “còn active/được phép sử dụng” |

Ví dụ minh họa bước tra cứu refresh token:

~~~java
OAuth2Authorization authorization =
    authorizationService.findByToken(
        presentedRefreshToken,
        OAuth2TokenType.REFRESH_TOKEN
    );

if (authorization == null
        || authorization.getRefreshToken() == null
        || !authorization.getRefreshToken().isActive()) {
    throw invalidGrant();
}

// Cần kiểm tra thêm client binding, scope, thời hạn,
// sender-constraining và chính sách refresh grant.
~~~

Đây là **pseudocode**: invalidGrant là hàm minh họa, không phải hàm Spring bắt buộc có sẵn. Đoạn mã này không phải token endpoint hoàn chỉnh; xác thực client và kiểm tra tính nguyên tử không được phép bỏ qua.

Không ghi raw token vào log khi tra cứu, kể cả trường hợp không tìm thấy.

## 5. Authorization service trong Authorization Code Flow

Authorization Code Flow có hai bước độc lập theo thời gian: **cấp code** qua redirect và **đổi code** tại token endpoint. Authorization service lưu trạng thái để kết nối hai bước.

### 5.1. Cấp authorization code

1. Client tạo authorization request với **client_id, redirect_uri, response_type=code, scope, state** và **code_challenge** nếu dùng PKCE.
2. AS tìm registered client, kiểm tra redirect URI, grant type, scope và chính sách.
3. Người dùng xác thực/consent nếu yêu cầu; AS xác định tập scope thực sự được cấp.
4. AS tạo code ngắn hạn, ngẫu nhiên, gắn với registered client và các điều kiện grant.
5. Provider lưu OAuth2Authorization chứa code vào authorization service.
6. Browser được redirect về redirect URI hợp lệ cùng code và state.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as OAuth Client
    participant AS as Authorization Server
    participant S as OAuth2AuthorizationService
    B->>C: Đăng nhập
    C-->>B: Redirect tới authorize + state + PKCE challenge
    B->>AS: Authorization request
    AS->>AS: Client validation, login, consent
    AS->>S: save authorization có CODE_A
    S-->>AS: Saved
    AS-->>B: Redirect code=CODE_A, state
    B->>C: Callback code + state
~~~

**PKCE code_verifier** không được gửi trong authorization request. Với public browser client, nên bắt buộc **S256** và giữ verifier ngẫu nhiên của từng giao dịch phía client cho đến token request.

### 5.2. Đổi authorization code

Token request điển hình:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=browser-app&code=<AUTH_CODE>&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=<VERIFIER>
~~~

AS/provider phải:

1. Xác định đúng registered client và xác thực client nếu là confidential client.
2. Tìm authorization theo code; xác nhận code chưa dùng, chưa hết hạn và còn active.
3. So khớp client/redirect URI với dữ liệu đã gắn khi cấp code.
4. Với PKCE, kiểm tra code_verifier và so S256(verifier) với code_challenge đã lưu.
5. **Tiêu thụ code chỉ một lần**, phát hành access token, refresh token nếu được phép.
6. Lưu authorization cập nhật và trả token response.

~~~mermaid
flowchart TD
    A[Token request với code] --> B[Tìm authorization]
    B --> C{Code active?}
    C -- Không --> X[invalid_grant]
    C -- Có --> D{Đúng client/redirect URI?}
    D -- Không --> X
    D -- Có --> E{PKCE và policy hợp lệ?}
    E -- Không --> X
    E -- Có --> F[Tiêu thụ code, phát hành token]
    F --> G[save trạng thái authorization]
    G --> H[Trả token response]
~~~

**Lưu ý về race condition:** Hai request cùng dùng CODE_A không được đồng thời đổi thành công nếu cả hai đều đọc trạng thái ACTIVE. Giao diện save/findByToken **không tự bảo đảm atomic compare-and-swap**; kiểm tra và cập nhật phải được đồng bộ trong provider/store/transaction phù hợp và được kiểm thử qua nhiều instance.

## 6. Access token: JWT, opaque token và trạng thái authorization

### 6.1. JWT access token

Ví dụ JWT claims đã được AS ký:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "browser-app",
  "scope": "orders.read",
  "iat": 1795400000,
  "exp": 1795400300
}
~~~

Khi resource server xác minh **chữ ký, issuer, audience, thời gian, token type và scope** tại chỗ, nó có thể không hỏi authorization service trong mỗi request.

Hệ quả: **xóa hoặc invalidated authorization tại AS không tự làm JWT này bị từ chối tức thì** ở resource server nếu RS chỉ xác minh offline. Cần cơ chế bổ sung như TTL ngắn, denylist, introspection hoặc kiểm tra trạng thái phù hợp nếu chính sách yêu cầu thu hồi ngay.

### 6.2. Opaque access token

Opaque token là chuỗi không có claims mà resource server có thể tự giải mã theo JWT. RS thường gọi **OAuth Token Introspection** tới AS, rồi AS tìm trạng thái token qua authorization service hoặc nguồn dữ liệu tương đương.

Một phản hồi minh họa:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "browser-app",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 1795400300
}
~~~

Ngoài **active**, nhiều trường metadata là tùy chọn theo RFC 7662 và cách AS triển khai. RS phải biết rõ mình đang hỏi **đúng AS tin cậy** và kiểm tra resource/audience, scope, client/tenant cũng như quyền nghiệp vụ. **active=true** không có nghĩa token cho phép mọi hành động.

Khi AS thu hồi token, introspection có thể báo **active=false**. Nhưng nếu RS cache kết quả introspection, thời gian phản ánh thu hồi phụ thuộc vào TTL cache và thiết kế nhất quán.

### 6.3. Token type và audience

**ID token** được cấp cho OIDC client để xác minh đăng nhập; **access token** cấp cho API; **refresh token** dành cho token endpoint. Chữ ký hợp lệ không làm chúng thay thế được cho nhau. Mỗi thành phần cần kiểm tra **type, issuer, audience, expiry và quyền phù hợp**.

## 7. Refresh token và chính sách rotation

Refresh token được gửi tới AS token endpoint để xin access token mới. Authorization service giúp AS tìm grant liên quan tới refresh token và kiểm tra token có còn active hay không.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Token Endpoint
    participant S as Authorization Service
    C->>AS: refresh_token=RT0
    AS->>S: findByToken RT0
    S-->>AS: Authorization + token state
    AS->>AS: Kiểm tra client, scope, expiry, binding
    AS->>AS: Cấp AT1, có thể cấp RT1
    AS->>S: save authorization cập nhật
    S-->>AS: Saved
    AS-->>C: Token response
~~~

Trước khi cấp token mới, AS phải kiểm tra **đúng client**, phạm vi quyền không tăng vượt grant, expiration, trạng thái revoked và proof/binding khi áp dụng.

### 7.1. Rotation khác reuse detection

Một thiết lập trong Spring Authorization Server là:

~~~java
TokenSettings.builder()
    .accessTokenTimeToLive(Duration.ofMinutes(5))
    .refreshTokenTimeToLive(Duration.ofHours(8))
    .reuseRefreshTokens(false)
    .build();
~~~

Thiết lập này hướng tới **cấp refresh token mới** trong refresh grant. Nó **không tự chứng minh** implementation có khả năng phát hiện mọi trường hợp token cũ bị phát lại và liên kết lần phát lại với một **token family**.

| Nhu cầu | Trạng thái/cơ chế cần có |
|---|---|
| Rotation | RT0 dùng thành công thì RT1 được cấp; RT0 không còn đổi được |
| Reuse detection | Nhận ra RT0 đã USED khi nó xuất hiện lại |
| Family revocation | Khi reuse có căn cứ, thu hồi RT1 và những successor của family |
| Race safety | Hai request đồng thời dùng RT0 không phát hành hai successor hợp lệ |
| Sender-constraining | Người gửi chứng minh quyền sở hữu khóa/chứng chỉ gắn với token |

Một mô hình chỉ giữ **refresh token hiện hành** có thể không còn bản ghi tra cứu của RT0 sau rotation. Khi đó server thấy một token lạ, nhưng chưa đủ thông tin để biết nó thuộc family nào. Muốn phát hiện reuse theo family cần giữ **token digest, family ID, generation, trạng thái USED/ACTIVE, thời gian và phạm vi thu hồi** phù hợp.

### 7.2. Retry hợp lệ và cạnh tranh đồng thời

Một client có thể gửi lại RT0 vì phản hồi chứa RT1 bị mất. Máy chủ nhận được RT0 đã dùng, nhưng không thể kết luận chỉ từ token rằng đó là retry hợp lệ hay kẻ tấn công. Cần chính sách rõ cho tình huống này; **không tự động trả RT1 cho mọi bên còn giữ RT0 trong một grace period** vì điều đó giúp kẻ đánh cắp token có cơ hội tiếp tục truy cập.

Khi hai tab gửi RT0 đồng thời, backend cần serialize hoặc dùng **transaction + khóa/CAS** để không tạo hai refresh token hiện hành. Client cũng nên gom các refresh calls thành một tác vụ duy nhất, nhưng server vẫn phải an toàn trước cạnh tranh.

## 8. Authorization service và token state trong hệ thống bảo mật

Một authorization có thể chuyển qua những trạng thái logic:

~~~mermaid
stateDiagram-v2
    [*] --> Created: Cấp authorization/code
    Created --> Issued: Đổi code hợp lệ
    Created --> Expired: Code hết hạn
    Issued --> Refreshed: Refresh token hợp lệ
    Refreshed --> Refreshed: Refresh tiếp
    Issued --> Revoked: Thu hồi
    Refreshed --> Revoked: Thu hồi hoặc reuse
    Issued --> Expired: Token/authorization hết hạn
    Refreshed --> Expired: Hết hạn
    Revoked --> [*]
    Expired --> [*]
~~~

Đây là **sơ đồ vòng đời ở mức khái niệm**, không phải enum trạng thái bắt buộc của OAuth2Authorization. Trong implementation, các token có trạng thái riêng về thời hạn/invalidated, và một authorization có thể chứa cả token đã dùng lẫn token đang hoạt động.

Sự tồn tại của authorization service giúp AS theo dõi grant, nhưng **tính chính xác giao thức** vẫn phụ thuộc providers, validators, database consistency và chính sách client.

## 9. Cấu hình OAuth2AuthorizationService trong Spring Authorization Server

### 9.1. Dùng in-memory ở môi trường học tập

Spring Authorization Server cung cấp **InMemoryOAuth2AuthorizationService**, thuận tiện khi dựng ví dụ hoặc test đơn giản.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.InMemoryOAuth2AuthorizationService;

@Configuration
public class DevAuthorizationStoreConfig {

    @Bean
    OAuth2AuthorizationService authorizationService() {
        return new InMemoryOAuth2AuthorizationService();
    }
}
~~~

In-memory có các giới hạn:

- **Restart mất dữ liệu**, có thể làm authorization code/refresh token không còn tìm được.
- Nhiều instance giữ trạng thái khác nhau, không phù hợp xử lý grant phân tán.
- Không có cơ chế lưu trữ bền vững, kiểm toán và dọn dữ liệu ở quy mô lớn.
- Không nên đánh đồng bài demo hoạt động đúng ở một JVM với kiến trúc production.

### 9.2. Dùng JDBC cho trạng thái bền vững

Một triển khai có sẵn khác là **JdbcOAuth2AuthorizationService**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
public class JdbcAuthorizationStoreConfig {

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClients) {

        return new JdbcOAuth2AuthorizationService(
            jdbcTemplate,
            registeredClients
        );
    }
}
~~~

**Hai đoạn cấu hình là các lựa chọn thay thế**, không đăng ký cả hai bean cùng kiểu trong một ứng dụng nếu chưa có cơ chế lựa chọn rõ ràng.

Để JDBC hoạt động đúng, cần:

1. Tạo **schema tương thích** với phiên bản Spring Authorization Server đang dùng, đặc biệt bảng authorization và các cột token/metadata.
2. Có **RegisteredClientRepository** phù hợp để authorization tham chiếu đúng registered client.
3. Quản lý migration DB, index, connection pool và backup.
4. Bảo vệ credential DB; phân quyền truy cập theo nguyên tắc tối thiểu.
5. Đánh giá lưu trữ token/attributes nhạy cảm và mã hóa dữ liệu lưu trữ khi phù hợp.
6. Xác minh **transaction và concurrency** khi trao đổi code, refresh, revocation.
7. Kiểm thử thực tế với nhiều instance, failover và các request đồng thời.

**Không mặc định rằng JdbcOAuth2AuthorizationService băm toàn bộ token khi lưu.** Hãy xem schema và cách serialize của phiên bản đang chạy; đối xử với authorization store và bản sao lưu như nguồn chứa bí mật. Nếu chọn thiết kế lưu digest/HMAC cho opaque token có entropy cao, phải có implementation tra cứu custom tương thích; không chỉ tự thay cột database rồi mong findByToken vẫn hoạt động.

### 9.3. Thiết lập registered client và token policy

Authorization service làm việc với authorization thuộc một registered client. Cấu hình đăng ký client, PKCE, grant types, token lifetime và scopes được quản lý riêng. Ví dụ phác thảo dành cho **public browser client**:

~~~java
RegisteredClient browserClient = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("browser-app")
    .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://app.example.test/callback")
    .scope("orders.read")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .build())
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofHours(8))
        .reuseRefreshTokens(false)
        .build())
    .build();
~~~

Đoạn code chỉ thể hiện **các thiết lập có liên quan**, chưa có imports, repository và cấu hình đầy đủ. Việc cho public client nhận refresh token phải đi kèm chính sách bảo vệ phù hợp, chẳng hạn rotation hoặc sender-constraining theo OAuth 2.0 Security Best Current Practice.

**RegisteredClientRepository** quyết định đăng ký và policy client; **OAuth2AuthorizationService** lưu trạng thái authorization thực tế. Không thể dùng cấu hình TokenSettings để thay thế kiểm tra replay, revocation, PKCE hoặc atomicity.

## 10. Ranh giới giữa authorization service và thành phần khác

Để biết sửa ở đâu khi một flow có lỗi, cần xác định đúng trách nhiệm.

| Thành phần | Làm gì? | Không tự làm gì? |
|---|---|---|
| RegisteredClientRepository | Lưu thông tin client, redirect URI, grant và settings | Lưu trạng thái code đã dùng |
| OAuth2AuthorizationService | Lưu/tìm/xóa grant và token metadata | Xác thực mật khẩu hoặc tự ký JWT |
| OAuth2AuthorizationConsentService | Lưu đồng ý của chủ thể với client | Tự thu hồi mọi token khi consent bị xóa |
| OAuth2TokenGenerator | Tạo token theo token context | Lưu authorization có transaction an toàn |
| Authorization Code Authentication Provider | Kiểm tra và xử lý code grant | Thay toàn bộ persistence |
| Refresh Token Authentication Provider | Xử lý refresh grant và token policy | Tự bảo đảm lịch sử token family ở mọi cấu hình |
| Token Introspection Provider | Đánh giá token theo policy khi có yêu cầu introspection | Thay resource authorization của API |
| Token Revocation Provider | Xử lý yêu cầu thu hồi token | Làm JWT offline ở mọi RS mất hiệu lực tức thời |
| Resource Server JwtDecoder | Xác minh chữ ký/claims tại API | Cấp authorization code hoặc refresh token |

Tên class và điểm mở rộng cụ thể cần đối chiếu với **phiên bản Spring Authorization Server** của ứng dụng khi triển khai thực tế. Dù framework cung cấp protocol providers, một extension của authorization service vẫn phải tôn trọng lifecycle và các điều kiện bảo mật đã được thiết kế.

## 11. Revocation, introspection và logout

### 11.1. Thu hồi token qua RFC 7009

Client có thể gửi token tới revocation endpoint của AS:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_AUTHENTICATION>

token=<TOKEN_TO_REVOKE>&token_type_hint=refresh_token
~~~

Ví dụ này giả định confidential client có phương thức xác thực phù hợp. Public client không được nhúng một client secret cố định trong JavaScript; endpoint phải áp dụng ràng buộc đúng theo kiểu client.

AS kiểm tra client/quyền, định vị token liên quan và ghi quyết định thu hồi vào authorization state. Theo RFC 7009, phản hồi của revocation thường tránh tiết lộ token có tồn tại hay không. **Không để client bất kỳ thu hồi token của client khác** nếu không được policy cho phép.

Việc revoke refresh token có thể đi kèm việc vô hiệu hóa các access token liên quan tùy chính sách và khả năng của kiến trúc. Phải phân biệt **trạng thái tại AS** với **khả năng quan sát revocation ở resource server**.

### 11.2. Introspection qua RFC 7662

Resource server có thể yêu cầu AS kiểm tra một access token:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <RESOURCE_SERVER_AUTHENTICATION>

token=<ACCESS_TOKEN>
~~~

Một token đã hết hạn, bị vô hiệu hóa hoặc không còn được AS chấp nhận có thể nhận:

~~~json
{
  "active": false
}
~~~

Không được cho rằng mọi RS đều gọi introspection. Resource server xác minh **JWT offline** sẽ không tự động thấy việc token đã bị đánh dấu revoked trong authorization service. Với RS dùng introspection và cache, độ trễ thu hồi phụ thuộc TTL cache.

### 11.3. Logout, xóa consent và revoke token không đồng nghĩa

Một ứng dụng có thể:

- Xóa **session cookie** khi người dùng logout cục bộ.
- Kết thúc session tại **OpenID Provider** nếu hỗ trợ logout OIDC.
- Xóa **OAuth2AuthorizationConsent** khi người dùng gỡ quyền ứng dụng.
- Thu hồi **refresh token/authorization** liên quan tới phiên hoặc ứng dụng.
- Vô hiệu hóa access token nếu có cơ chế phối hợp với resource server.

Đây là các thao tác riêng, cần được kết nối theo chính sách cụ thể. Ví dụ, người dùng logout một thiết bị không nhất thiết phải đăng xuất mọi thiết bị; ngược lại, khi phát hiện refresh token bị đánh cắp, chính sách có thể yêu cầu thu hồi một **token family**.

## 12. Tính nhất quán, độ bền và chống replay

Một **authorization store** là thành phần bảo mật quan trọng vì nó ảnh hưởng trực tiếp đến quyết định token có còn được đổi hoặc kiểm tra hay không.

### 12.1. Những bất biến cần được bảo vệ

1. **Authorization code chỉ dùng một lần** dù có nhiều token requests đồng thời.
2. Code và refresh token phải ràng buộc **đúng registered client** và các điều kiện grant.
3. **Redirect URI, PKCE và issuer** không được thay bằng giá trị tùy ý từ token request sau.
4. **Scope được cấp** không bị mở rộng ngoài authorization ban đầu.
5. Token **expired/invalidated** không được dùng để cấp token mới.
6. **Refresh rotation** không tạo nhiều successor hợp lệ do race.
7. **Revocation** phải được lưu nhất quán trước khi báo thành công.
8. Không phát hành token nếu AS không thể ghi trạng thái cần thiết một cách an toàn.
9. Trạng thái lưu ở nhiều instance không được mâu thuẫn khi quyết định token active.
10. Các token trong database, cache, backup và log phải được bảo vệ như dữ liệu bí mật.

### 12.2. Vì sao cần khóa hoặc compare-and-swap?

Hai request đồng thời đổi CODE_A:

~~~text
Thread 1: findByToken(CODE_A) -> ACTIVE
Thread 2: findByToken(CODE_A) -> ACTIVE
Thread 1: issue tokens, save CODE_A USED
Thread 2: issue tokens, save CODE_A USED

Kết quả sai: cùng code được đổi hai lần.
~~~

Một transaction thông thường không luôn ngăn được tình huống này nếu cả hai đều đọc state cũ rồi ghi. Cần **atomic conditional update**, row locking, optimistic locking/version hoặc cơ chế serialization phù hợp, với kết quả update được kiểm tra rõ ràng.

Đối với refresh rotation, trường hợp tương tự có thể tạo RT1a và RT1b từ RT0. Những lỗi đó cần kiểm thử với cơ sở dữ liệu và mức isolation thực tế, kể cả nhiều process/instance.

### 12.3. Không rollback quyết định thu hồi

Nếu ứng dụng ghi trạng thái revoked trong transaction rồi ném một exception làm rollback toàn bộ trước khi trả OAuth error, quyết định revoke có thể **không được lưu**. Cần thiết kế ranh giới transaction để quyết định thu hồi bền vững trước khi trả phản hồi lỗi hoặc thông báo hoàn tất.

Không nên dùng thông báo HTTP thành công làm bằng chứng đã revoke nếu database commit thất bại.

### 12.4. Dọn dữ liệu nhưng không đánh mất bằng chứng reuse

Bản ghi authorization hết hạn cần được dọn theo retention policy. Tuy nhiên, xóa lịch sử refresh token đã dùng quá sớm có thể khiến AS không biết một token cũ đang bị replay và thuộc family nào.

Nếu chính sách yêu cầu reuse detection, cần giữ **digest hoặc định danh token đã dùng**, family, trạng thái và thời điểm trong cửa sổ được định nghĩa. Thời gian lưu phải cân bằng khả năng phát hiện với bảo vệ dữ liệu cá nhân và chi phí storage.

## 13. Issuer, audience và multi-tenant

Authorization service lưu grant theo registered client/principal, nhưng **resource server** còn phải kiểm tra issuer và audience của access token.

~~~text
Tenant A:
  issuer = https://identity.example.test/tenant-a
  audience = orders-a

Tenant B:
  issuer = https://identity.example.test/tenant-b
  audience = orders-b
~~~

Nếu hệ thống cho token từ Tenant B truy cập orders-a chỉ vì cùng domain hoặc cùng key infrastructure, đây là lỗ hổng **issuer/audience confusion**. Các ràng buộc cần có:

- Issuer được cấu hình từ nguồn tin cậy, không tự lấy một URL tùy ý từ token chưa xác thực.
- JWKS và khóa ký gắn với đúng issuer; **kid không duy nhất toàn hệ thống**.
- Audience của access token phải trỏ đúng API/resource server.
- Principal có thể cần được biểu diễn bằng cặp **(issuer, subject)** để tránh trùng sub giữa các IdP.
- Registered client và authorization thuộc tenant nào phải được thực thi xuyên suốt flow.
- Introspection/revocation phải được phục vụ trong đúng phạm vi AS/tenant và xác thực caller.

Authorization service không nên thay thế các kiểm tra ở token generator và resource server. Một access token có chữ ký hợp lệ nhưng **sai audience hoặc token type** vẫn phải bị từ chối ở API.

## 14. Vận hành, logging và bảo vệ dữ liệu

Một authorization store có thể chứa raw access/refresh token hoặc attributes nhạy cảm. Tối thiểu cần:

- **Không ghi raw authorization code, access token, refresh token, PKCE verifier hoặc client_secret** vào log.
- Hạn chế quyền DB; bảo vệ backup, snapshot và môi trường thử nghiệm có dữ liệu nhạy cảm.
- Kiểm tra cách các class serialize/toString token metadata trước khi bật log debug.
- Áp dụng TLS giữa AS và database/các service liên quan theo mô hình triển khai.
- Có TTL, retention và job cleanup rõ ràng.
- Giám sát lỗi transaction, độ trễ findByToken/save, số authorization hết hạn và trạng thái DB.
- Thực hiện fail closed khi không xác định được authorization state mà giao thức cần.

Các event có thể ghi:

| Sự kiện | Khi nào ghi |
|---|---|
| authorization_created | Cấp code/grant mới |
| authorization_code_exchanged | Đổi code thành công |
| authorization_code_reuse_rejected | Code đã dùng xuất hiện lại |
| refresh_succeeded | Refresh grant thành công |
| refresh_reuse_detected | Token history xác định reuse |
| authorization_revoked | Grant/token bị thu hồi |
| introspection_inactive | Token không còn active |
| consent_changed | Consent được cập nhật/xóa |
| authorization_store_error | Save/find/transaction thất bại |

Nên lưu request ID, client ID đã xác thực, issuer/tenant đã xác minh, loại grant, loại lỗi và fingerprint không dùng được làm token; tránh lộ credential trong payload observability. Tăng đột ngột lỗi **invalid_grant** có thể đến từ retry client, lệch giờ, bug cạnh tranh hoặc tấn công: cần điều tra theo ngữ cảnh.

## 15. Kiểm thử authorization service

### 15.1. Ma trận kiểm thử cần thiết

| Kịch bản | Kỳ vọng |
|---|---|
| Save và findById authorization | Truy xuất đúng client, principal, scope và token state |
| findByToken với token hợp lệ | Trả đúng authorization liên quan |
| Tìm token không tồn tại | Không trả grant, không lộ thông tin nhạy cảm |
| Code hợp lệ, đúng client/redirect/PKCE | Một lần đổi thành công |
| Dùng lại authorization code | Bị từ chối |
| Hai request cùng đổi một code | Tối đa một lần thành công |
| Authorization code hết hạn | Không cấp token |
| PKCE verifier sai hoặc thiếu | Không cấp token khi PKCE được yêu cầu |
| Client không khớp hoặc redirect URI sai | Bị từ chối |
| Scope request vượt authorized scopes | Không được tự mở rộng quyền |
| JWT bị thu hồi trong AS | Introspection phản ánh trạng thái; kiểm tra giới hạn RS offline |
| Opaque token inactive | Introspection trả inactive |
| Refresh hợp lệ | Cấp token mới với quyền trong phạm vi ban đầu |
| Refresh token đã dùng sau rotation | Không được đổi; xử lý reuse/family nếu policy yêu cầu |
| Hai refresh đồng thời | Không tạo hai successor hợp lệ trái policy |
| Retry sau khi mất refresh response | Theo chính sách retry/replay đã xác định |
| Xóa consent | Tác động tới grant/token được thực hiện theo policy, không tự giả định |
| Restart server dùng JDBC | Dữ liệu còn hiệu lực được truy xuất lại |
| Hai AS instances | Nhìn cùng trạng thái, không cấp token hai lần do race |
| DB lỗi khi save state | Không báo token issuance thành công trái thực tế |
| Thu hồi authorization | Grant không được dùng tiếp; JWT offline xử lý riêng |
| API nhận token sai issuer/audience | Resource server từ chối |
| Quan sát log và backup | Không rò raw credential |

### 15.2. Kiểm tra ở mức service

Pseudocode Java:

~~~java
OAuth2Authorization original =
    createAuthorizationForTest(registeredClient, principal);

authorizationService.save(original);

OAuth2Authorization loaded =
    authorizationService.findById(original.getId());

assertNotNull(loaded);
assertEquals(
    original.getRegisteredClientId(),
    loaded.getRegisteredClientId()
);

authorizationService.remove(loaded);

assertNull(
    authorizationService.findById(original.getId())
);
~~~

Test trên chỉ chứng minh **CRUD**. Nó **không chứng minh** code dùng một lần, refresh rotation an toàn hay các kiểm tra PKCE/client binding đã được thực thi.

### 15.3. Kiểm thử end-to-end và concurrency

~~~text
Given:
  CODE_A còn ACTIVE, gắn client và PKCE hợp lệ
When:
  Hai token requests đổi CODE_A cùng lúc, trên hai instance
Then:
  Chỉ một request thành công
  CODE_A không thể đổi lần nữa
  Authorization store có trạng thái nhất quán
~~~

~~~text
Given:
  Refresh token RT0 ACTIVE và policy rotation
When:
  Hai refresh requests dùng RT0 cùng lúc
Then:
  Không có hai successor hợp lệ
  RT0 không thể dùng tiếp
  Nếu có token family reuse detection, sự kiện reuse xử lý đúng
~~~

Các integration tests cần dùng datastore/mức isolation đủ gần môi trường production. Mocks chạy tuần tự sẽ bỏ sót race condition. Hãy kiểm thử thêm expiry, lỗi DB, restart, key rotation, revocation/introspection và API issuer/audience validation.

## 16. Những nhầm lẫn phổ biến

**“OAuth2AuthorizationService là bộ kiểm tra chữ ký JWT.”** Sai. Nó quản lý authorization state; token generator/decoder và providers xử lý mật mã và giao thức.

**“findByToken trả kết quả nghĩa token còn active.”** Sai. Cần kiểm tra trạng thái, expiration, client binding và chính sách liên quan.

**“OAuth2AuthorizationConsent thay thế OAuth2Authorization.”** Sai. Consent và vòng đời cấp token khác nhau.

**“Bật refresh token rotation tự động phát hiện mọi replay.”** Sai. Muốn biết token cũ thuộc family nào phải có trạng thái lịch sử phù hợp; còn phải giải quyết concurrency.

**“Xóa authorization làm mọi JWT đã phát hành chết ngay.”** Sai nếu RS vẫn xác minh JWT offline mà không introspect hay kiểm tra denylist.

**“JDBC đã có transaction nên mọi race condition bị loại bỏ.”** Không tự động. Cần kiểm tra khóa, isolation và cập nhật có điều kiện.

**“In-memory phù hợp production nhiều instance.”** Không khi cần authorization state bền vững và chia sẻ nhất quán giữa các node.

**“Token có scope đúng thì được truy cập mọi bản ghi.”** Sai. Resource server còn cần authorization nghiệp vụ theo resource owner, tenant và các điều kiện khác.

## 17. Câu hỏi tự kiểm tra

1. OAuth2AuthorizationService khác RegisteredClientRepository và OAuth2AuthorizationConsentService như thế nào?
2. Bốn phương thức của interface OAuth2AuthorizationService là gì?
3. Vì sao findByToken chưa đủ để xác định token được sử dụng?
4. Authorization code cần được ràng buộc với những thông tin nào trước khi cấp token?
5. Điều gì xảy ra nếu hai requests cùng đổi một authorization code mà không có tính nguyên tử?
6. Vì sao revoke ở AS có thể chưa khiến resource server từ chối một JWT access token ngay?
7. Khi dùng opaque token, introspection có vai trò gì và hạn chế của cache là gì?
8. Sự khác nhau giữa refresh token rotation và reuse detection là gì?
9. Vì sao cần bảo vệ dữ liệu trong bảng authorization, logs và backup như bí mật?
10. Khi nào dùng InMemoryOAuth2AuthorizationService và khi nào dùng JdbcOAuth2AuthorizationService?
11. Vì sao xóa consent không đồng nghĩa xóa mọi token đang hoạt động?
12. Làm thế nào để tách issuer, audience và principal trong hệ thống đa tenant?
13. Thiết kế một test chứng minh một code không thể được đổi hai lần trong hai AS instances.
14. Nếu lưu quyết định revocation nhưng transaction rollback, hệ quả là gì?
15. Khi refresh response thất lạc và client retry token cũ, cần lưu ý điều gì để không tạo cửa sổ replay?

**Ghi nhớ:** Trong **Spring Authorization Server**, **OAuth2AuthorizationService** là thành phần quản lý authorization state. Nó lưu và truy xuất grant/token metadata để các providers xử lý cấp, đổi, refresh, introspection và revocation. Hệ thống chỉ an toàn khi kết hợp **client registration, consent, token generation, kiểm tra issuer/audience/scope, lưu trữ bền vững, giao dịch nguyên tử, thu hồi và chống token theft/replay**.

## Tài liệu tham khảo

- **Spring Authorization Server Reference — Core Model and Components:** OAuth2Authorization, OAuth2AuthorizationService, OAuth2AuthorizationConsentService và RegisteredClientRepository.
- **Spring Authorization Server API — OAuth2AuthorizationService, InMemoryOAuth2AuthorizationService, JdbcOAuth2AuthorizationService:** lưu/truy xuất authorization state.
- **Spring Authorization Server Reference — Protocol Endpoints và Token Settings:** authorization, token, introspection, revocation và chính sách token.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization code, refresh grant, scopes và client.
- **RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE):** bảo vệ authorization code.
- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage:** sử dụng bearer access token tại resource server.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái active và metadata của token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** claims, issuer và audience của access token JWT.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ authorization code, refresh token, token rotation và sender-constraining.
- **OpenID Connect Core 1.0:** ID token, issuer, audience và xác minh đăng nhập.


