# TTL, serialization và cập nhật metadata token trong kho tùy chỉnh

> **Chương:** Lưu trữ tùy chỉnh  
> **Module:** `SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi kỹ thuật:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x. Ví dụ sử dụng Servlet stack và `OAuth2AuthorizationService`; phần persistence có thể triển khai bằng JDBC, JPA hoặc kho key-value.

## 1. Mục tiêu và bối cảnh

Khi Authorization Server chuyển từ lưu trữ in-memory sang database hoặc distributed store, việc lưu một chuỗi token và một thời điểm hết hạn là chưa đủ. Spring Authorization Server cần khôi phục được toàn bộ trạng thái của một authorization để tiếp tục xử lý các protocol flow.

Một `OAuth2Authorization` có thể chứa:

- Registered Client và principal đã tham gia grant.
- Grant type, scopes được cấp và attributes của authorization request.
- Authorization Code, Access Token, Refresh Token, ID Token, Device Code hoặc User Code tùy grant.
- Thời điểm phát hành, hết hạn, token claims và metadata của từng token.
- Trạng thái token đã bị invalidated/revoked hay còn active.

Một authorization có thể chứa nhiều token với vòng đời khác nhau. Ví dụ, Authorization Code đã hết hạn hoặc đã sử dụng, Access Token vẫn còn hiệu lực, trong khi Refresh Token tiếp tục cho phép cấp Access Token mới. Vì vậy, kho lưu trữ cần quản lý TTL theo từng token và giữ authorization record đủ lâu để xử lý các token còn lại.

Sau bài học, bạn có thể:

1. Phân biệt TTL của token với thời gian lưu giữ authorization record.
2. Cấu hình TTL theo client bằng `TokenSettings`.
3. Thiết kế schema lưu token value, issuedAt, expiresAt, metadata và claims.
4. Serialization/deserialization `OAuth2Authorization` an toàn và có khả năng tương thích schema.
5. Triển khai các phương thức `save`, `remove`, `findById` và `findByToken` của `OAuth2AuthorizationService`.
6. Cập nhật token metadata bằng `OAuth2Authorization.from(...)` mà không làm mất metadata sẵn có.
7. Lưu trạng thái invalidation và refresh token rotation chính xác.
8. Xử lý concurrency, cleanup, indexing và distributed cache.
9. Kiểm thử round-trip serialization, token expiry, revocation và metadata update.

**Nguyên tắc thiết kế:** Thời hạn của token được quyết định khi token được phát hành; kho lưu trữ phải giữ nguyên các mốc thời gian đó, lưu đủ trạng thái token để framework kiểm tra, và chỉ dọn authorization record khi không còn token hoặc protocol state cần thiết.

## 2. OAuth2Authorization và hợp đồng persistence

### 2.1. Authorization là aggregate chứa nhiều token

`OAuth2Authorization` là biểu diễn trạng thái authorization được cấp cho một client bởi resource owner hoặc bởi chính client trong grant `client_credentials`.

Các thuộc tính cốt lõi:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `id` | Định danh duy nhất của authorization |
| `registeredClientId` | ID nội bộ của RegisteredClient |
| `principalName` | Tên principal hoặc client |
| `authorizationGrantType` | Grant type đã sử dụng |
| `authorizedScopes` | Các scope đã được cấp |
| `tokens` | Các token và metadata gắn với từng token |
| `attributes` | Dữ liệu bổ sung của grant, ví dụ principal đã xác thực và authorization request |

Các token có thể xuất hiện tùy grant:

| Grant/flow | Token hoặc state thường cần lưu |
| --- | --- |
| Authorization Code | Authorization Code, Access Token, Refresh Token tùy client |
| OpenID Connect Authorization Code | Authorization Code, ID Token, Access Token, Refresh Token tùy client |
| Client Credentials | Access Token |
| Device Authorization | Device Code, User Code và token sau khi user hoàn tất xác minh |
| Refresh Token | Token mới và trạng thái token cũ theo chính sách rotation |

Không giả định mọi authorization đều có đủ các token trên. Schema và serializer phải xử lý được trường không tồn tại.

### 2.2. OAuth2AuthorizationService là ranh giới persistence

`OAuth2AuthorizationService` là thành phần trung tâm lưu authorization mới và truy vấn authorization hiện có. Các protocol component dùng service này trong authorization grant processing, client authentication, token introspection, token revocation và các flow liên quan.

Interface có bốn phương thức:

~~~java
public interface OAuth2AuthorizationService {

    void save(OAuth2Authorization authorization);

    void remove(OAuth2Authorization authorization);

    OAuth2Authorization findById(String id);

    OAuth2Authorization findByToken(
        String token, OAuth2TokenType tokenType);
}
~~~

Hợp đồng cần giữ:

| Phương thức | Hành vi của custom store |
| --- | --- |
| `save` | Lưu authorization mới hoặc cập nhật trạng thái authorization hiện tại |
| `remove` | Xóa toàn bộ authorization theo ID |
| `findById` | Khôi phục đầy đủ authorization theo ID |
| `findByToken` | Tìm authorization đang chứa token được cung cấp; trả `null` nếu không có |

`findByToken` nhận `tokenType` có thể là `null`. Khi null, implementation cần tìm trên các loại token/state mà nó hỗ trợ, thay vì mặc định chỉ tìm Access Token. Token type cụ thể giúp giới hạn lookup và sử dụng index phù hợp.

### 2.3. Tách ba core service

Không trộn ba loại dữ liệu sau vào một bảng hoặc một service chỉ vì chúng có liên quan:

- `RegisteredClientRepository` lưu client registration, redirect URI, grant types, scopes, client settings và token settings.
- `OAuth2AuthorizationService` lưu trạng thái từng authorization và token đã phát hành.
- `OAuth2AuthorizationConsentService` lưu quyết định consent của user đối với client.

Một RegisteredClient có thể có nhiều authorization. Một user cũng có thể có nhiều authorization với cùng client. Consent có vòng đời riêng và không tự mất khi authorization record bị xóa.

## 3. TTL của token trong Spring Authorization Server

### 3.1. TokenSettings là chính sách phát hành

`TokenSettings` được gắn với `RegisteredClient` và định nghĩa thời hạn của các token mà client được cấp. Trong Spring Authorization Server 1.5.x, builder hỗ trợ:

- `authorizationCodeTimeToLive(Duration)`
- `accessTokenTimeToLive(Duration)`
- `refreshTokenTimeToLive(Duration)`
- `deviceCodeTimeToLive(Duration)`
- `reuseRefreshTokens(boolean)`
- `accessTokenFormat(OAuth2TokenFormat)`

Ví dụ:

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
    .authorizationCodeTimeToLive(Duration.ofMinutes(5))
    .accessTokenTimeToLive(Duration.ofMinutes(8))
    .refreshTokenTimeToLive(Duration.ofDays(7))
    .deviceCodeTimeToLive(Duration.ofMinutes(5))
    .reuseRefreshTokens(false)
    .build();

RegisteredClient portalClient = RegisteredClient
    .withId("portal-registration")
    .clientId("portal-client")
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://portal.example.test/login/oauth2/code/portal")
    .scope(OidcScopes.OPENID)
    .scope("orders.read")
    .tokenSettings(tokenSettings)
    .build();
~~~

Ví dụ này minh họa chính sách cho một client. Hãy chọn TTL dựa trên loại client, độ nhạy cảm của resource, khả năng refresh, rủi ro token bị lộ và yêu cầu vận hành.

### 3.2. Giá trị mặc định

Với Spring Authorization Server 1.5.8, các giá trị mặc định trong `TokenSettings` gồm:

| Loại | TTL mặc định |
| --- | ---: |
| Authorization Code | 5 phút |
| Access Token | 5 phút |
| Device Code | 5 phút |
| Refresh Token | 60 phút |

`reuseRefreshTokens` mặc định là `true`. Khi đặt `false`, server phát hành Refresh Token mới trong refresh flow thay vì tái sử dụng token cũ.

`TokenSettings` không có builder method riêng tên `idTokenTimeToLive` trong API 1.5.8. ID Token vẫn có `issuedAt` và `expiresAt` trong đối tượng `OidcIdToken`; custom persistence phải lưu các mốc thời gian thực tế của token, không tự tạo một TTL giả định khi deserialize.

### 3.3. Token TTL và storage TTL là hai chính sách

| Chính sách | Câu hỏi cần trả lời | Nơi áp dụng |
| --- | --- | --- |
| Token TTL | Credential được chấp nhận tới thời điểm nào? | TokenSettings và issued/expires timestamps |
| Authorization retention | Authorization record cần được giữ đến khi nào? | Database/Redis retention policy |
| Cache TTL | Bản cache được dùng trong bao lâu trước khi đọc lại nguồn chính? | Cache layer |
| Audit retention | Lịch sử token/revocation cần giữ bao lâu? | Audit store và retention policy |

Không đặt Redis TTL của toàn bộ authorization bằng TTL ngắn nhất trong các token. Nếu Authorization Code hết hạn sau 5 phút nhưng Refresh Token còn 7 ngày, xóa cả authorization record sau 5 phút sẽ làm refresh flow thất bại.

### 3.4. Thời điểm phát hành và hết hạn là dữ liệu có thẩm quyền

Khi token được tạo, đối tượng token mang `issuedAt` và `expiresAt`. Custom store phải lưu nguyên các giá trị này dưới dạng thời điểm tuyệt đối, thường dùng `Instant` và cột timestamp có timezone.

Không tính lại `expiresAt` từ TokenSettings hiện tại khi đọc record. Nếu admin đổi Access Token TTL từ 10 phút xuống 5 phút, token đã phát hành trước đó vẫn có thời điểm hết hạn ban đầu. Thay đổi policy áp dụng cho token mới, trừ khi có quy trình revoke hoặc migrate token đang tồn tại.

Ví dụ thời gian:

~~~java
Instant issuedAt = accessToken.getIssuedAt();
Instant expiresAt = accessToken.getExpiresAt();

if (expiresAt != null && !expiresAt.isAfter(clock.instant())) {
    // Token đã hết hạn theo thời gian hiện tại.
}
~~~

Dùng UTC/Instant nhất quán ở application và database. Cân nhắc precision của timestamp, clock skew giữa node và khoảng grace phục vụ cleanup. Không kéo dài thời hạn token chỉ để phù hợp với cache TTL.

## 4. Thiết kế retention và cleanup

### 4.1. Tính thời điểm có thể dọn authorization

Một authorization có thể chứa nhiều token. Thời điểm dọn toàn bộ record cần xét tất cả token hiện còn cần thiết:

~~~text
authorizationRetentionUntil =
    max(
        authorizationCodeExpiresAt,
        accessTokenExpiresAt,
        refreshTokenExpiresAt,
        idTokenExpiresAt,
        deviceCodeExpiresAt,
        userCodeExpiresAt
    ) + retentionGrace
~~~

Đây là cách tính khái niệm; triển khai cần bỏ qua token không tồn tại và xử lý token không có expiresAt theo policy. Nếu Refresh Token có thời hạn không giới hạn hoặc custom grant không có expiry, không được tự đặt một TTL ngắn để xóa record.

### 4.2. Không xóa record ngay khi một token hết hạn

Ví dụ:

- Authorization Code hết hạn sau 5 phút.
- Access Token hết hạn sau 10 phút.
- Refresh Token hết hạn sau 7 ngày.

Sau 5 phút, authorization vẫn cần được giữ vì Access Token hoặc Refresh Token còn liên quan. Sau 10 phút, refresh flow vẫn cần record. Chỉ khi tất cả token cần thiết đã hết hạn/invalidated và không còn protocol state hoặc yêu cầu audit, record mới đủ điều kiện cleanup.

### 4.3. Cleanup vật lý không thay thế trạng thái invalidation

Token có thể đã bị revoke trước khi expiresAt đến. Trạng thái invalidation phải được lưu trong metadata của token và được đọc bởi các protocol component. Xóa row vật lý là thao tác retention; nó không thay thế quy trình revoke.

Nên tách:

- Trạng thái hiệu lực của token.
- Trạng thái authorization aggregate.
- Thời điểm record được phép dọn.
- Audit record nếu cần giữ dấu vết lâu hơn.

### 4.4. Cleanup job có thể chạy lặp lại

Cleanup job nên idempotent, chia batch và có index theo `retention_until` hoặc `expires_at`. Không khóa toàn bộ bảng. Nếu job bị chạy lại, nó không được làm hỏng authorization đang hoạt động.

Một query minh họa:

~~~sql
DELETE FROM oauth2_authorization
WHERE retention_until < CURRENT_TIMESTAMP
  AND no_token_is_still_retained = TRUE;
~~~

`no_token_is_still_retained` là điều kiện khái niệm; thay bằng subquery/logic phù hợp với schema thực tế. Nếu có audit retention, chuyển bản ghi cần giữ sang audit store trước khi xóa operational record.
## 5. Serialization của OAuth2Authorization

### 5.1. Vì sao serialization phức tạp?

`OAuth2Authorization` chứa nhiều loại dữ liệu:

- Các token implement `OAuth2Token` nhưng có kiểu cụ thể khác nhau.
- `AuthorizationGrantType` có thể là giá trị chuẩn hoặc custom grant.
- `attributes` là Map với value có thể là object framework hoặc custom principal.
- `tokens` là Map theo token class.
- Token metadata chứa claims, invalidation flag và dữ liệu bổ sung.

Chỉ serialize một JSON đơn giản gồm `id`, `principalName` và `accessTokenValue` sẽ làm mất dữ liệu cần cho các flow khác như refresh token, device authorization, OIDC hoặc token revocation.

### 5.2. Dùng JSON với module của Spring Security

Spring Authorization Server cung cấp `OAuth2AuthorizationServerJackson2Module`. Hướng dẫn JPA chính thức kết hợp module này với các module do `SecurityJackson2Modules` cung cấp để serialize các kiểu Spring Security.

Ví dụ khởi tạo mapper:

~~~java
ObjectMapper objectMapper = new ObjectMapper();

ClassLoader classLoader =
    JpaOAuth2AuthorizationService.class.getClassLoader();

List<Module> securityModules =
    SecurityJackson2Modules.getModules(classLoader);

objectMapper.registerModules(securityModules);
objectMapper.registerModule(
    new OAuth2AuthorizationServerJackson2Module());
~~~

Trong ứng dụng thực, tạo mapper qua bean/configuration dùng chung và kiểm soát module được đăng ký. Phiên bản Jackson và module phải tương thích với dependency tree của ứng dụng.

### 5.3. Tránh Java native serialization cho kho lâu dài

Không nên dùng Java native serialization làm format lưu trữ lâu dài nếu không có lý do đặc biệt. Format này phụ thuộc class name, serialVersionUID và cấu trúc object của phiên bản ứng dụng. Khi nâng cấp framework hoặc thay đổi custom principal, việc deserialize có thể lỗi hoặc không tương thích.

JSON với schema version và type mapping rõ ràng giúp:

- Quan sát được dữ liệu.
- Thực hiện migration có kiểm soát.
- Hỗ trợ nhiều phiên bản ứng dụng cùng đọc dữ liệu trong rolling deployment.
- Xác định trường nào là framework metadata và trường nào là application metadata.

### 5.4. Deserialization phải có allowlist

`OAuth2Authorization.attributes` có thể chứa object phức tạp, bao gồm Authentication hoặc custom principal. Không bật polymorphic default typing rộng trên JSON lấy từ kho có thể bị sửa đổi hoặc từ nguồn không tin cậy.

Chỉ đăng ký các subtype/module thực sự cần. Nếu principal tùy chỉnh khó serialize, cân nhắc lưu một principal snapshot ổn định gồm subject, issuer, tenant và authorities cần thiết cho flow; khôi phục thành kiểu được hỗ trợ ở adapter. Không lưu credential/password hoặc session secret vào attributes.

### 5.5. Lưu schema version

Một JSON document nên có version riêng:

~~~json
{
  "schemaVersion": 2,
  "authorizationId": "auth-7c1f",
  "registeredClientId": "portal-registration",
  "principalName": "alice",
  "grantType": "authorization_code",
  "authorizedScopes": ["openid", "orders.read"],
  "attributes": {},
  "tokens": []
}
~~~

Ví dụ trên chỉ minh họa envelope. Token value, claims và metadata thật cần được mã hóa/bảo vệ theo chính sách. Khi schema thay đổi, triển khai reader có thể đọc version cũ và migrate dần khi ghi; không giả định mọi record được cập nhật ngay lập tức.

## 6. Những dữ liệu cần giữ nguyên khi serialize

### 6.1. Authorization-level attributes

Attributes có thể chứa:

- Principal đã xác thực.
- OAuth2AuthorizationRequest.
- State hoặc dữ liệu grant-specific.
- Thông tin context mà protocol component cần ở bước sau.

Nếu loại bỏ attributes để JSON ngắn hơn, refresh/token flow hoặc custom grant có thể không khôi phục được ngữ cảnh ban đầu. Chỉ loại bỏ sau khi đã xác định attribute không còn cần thiết và có test cho mọi flow liên quan.

### 6.2. Token-level metadata

Mỗi `OAuth2Authorization.Token` bao bọc một token và metadata đi kèm. Hai metadata name quan trọng trong SAS:

| Constant | Mục đích |
| --- | --- |
| `CLAIMS_METADATA_NAME` | Tên metadata lưu claims gắn với token |
| `INVALIDATED_METADATA_NAME` | Tên metadata thể hiện token đã bị invalidated |

`OAuth2Authorization.Token` cung cấp:

- `getToken()`
- `getMetadata()` và `getMetadata(name)`
- `getClaims()`
- `isExpired()`
- `isInvalidated()`
- `isActive()`

Không đổi tên hoặc ghi đè metadata chuẩn khi lưu custom metadata.

### 6.3. Phân biệt token claims và application metadata

| Dữ liệu | Ví dụ | Nơi lưu |
| --- | --- | --- |
| JWT claim | `sub`, `aud`, `scope`, `tenant_id` | Bên trong JWT đã ký |
| Token claims metadata | Claims gắn với token trong OAuth2Authorization.Token | Token metadata |
| Invalidation state | Token đã bị revoke | Token metadata |
| Authorization attribute | Authorization request, principal snapshot | OAuth2Authorization.attributes |
| Application metadata | Risk label, policy version, source system | Namespace riêng trong metadata/attributes |

Metadata ở database không tự trở thành claim bên trong JWT. Nếu JWT đã được ký, sửa JSON metadata trong kho không thay đổi payload hoặc chữ ký của JWT đó.

## 7. Cập nhật metadata của authorization

### 7.1. Dùng OAuth2Authorization.from(...)

Không tạo lại authorization từ đầu chỉ để thay đổi một thuộc tính. `OAuth2Authorization.from(existing)` tạo builder đã được khởi tạo từ authorization hiện có, giúp giữ lại ID, Registered Client ID, principal, grant type, scopes, attributes và token state.

Ví dụ cập nhật application attribute:

~~~java
OAuth2Authorization updated = OAuth2Authorization
    .from(existingAuthorization)
    .attributes(attributes ->
        attributes.put("com.example.risk.label", "reviewed"))
    .build();

authorizationService.save(updated);
~~~

Tên attribute nên có namespace để tránh xung đột với key do framework hoặc custom grant khác sử dụng.

### 7.2. Cập nhật token metadata mà vẫn giữ metadata cũ

Dùng `getAccessToken()` để lấy wrapper của Access Token. Sau đó truyền token value và metadata consumer cho builder:

~~~java
OAuth2Authorization.Token<OAuth2AccessToken> accessToken =
    existingAuthorization.getAccessToken();

if (accessToken == null) {
    throw new IllegalStateException("Authorization has no access token");
}

OAuth2Authorization updated = OAuth2Authorization
    .from(existingAuthorization)
    .token(accessToken.getToken(), metadata -> {
        metadata.putAll(accessToken.getMetadata());
        metadata.put("com.example.risk.reviewed", Boolean.TRUE);
        metadata.put("com.example.policy.version", 3);
    })
    .build();

authorizationService.save(updated);
~~~

`putAll(accessToken.getMetadata())` giữ lại metadata hiện có, bao gồm claims và invalidation state. Nếu tạo metadata map mới rồi chỉ ghi key tùy chỉnh, có thể vô tình làm mất metadata chuẩn.

### 7.3. Cập nhật claims metadata không sửa JWT đã phát hành

Nếu Access Token là JWT self-contained, claim đã nằm trong payload được ký. Thay đổi claims trong persistence sau khi phát hành không tạo ra một JWT mới và không làm thay đổi chữ ký của JWT đó.

Muốn thay đổi claim của token mới, hãy tùy biến trước bước ký token qua `OAuth2TokenCustomizer`. Nếu cần thay đổi quyền của một token đã phát hành, thường phải revoke token cũ và cấp token mới theo policy, thay vì chỉnh sửa metadata trong database rồi kỳ vọng Resource Server thấy claim mới.

### 7.4. Invalidate token bằng Builder API

Trong SAS 1.5.x, `OAuth2Authorization.Builder.invalidate(token)` có thể đánh dấu token đã invalidated. Ví dụ:

~~~java
OAuth2Authorization.Token<OAuth2RefreshToken> refreshToken =
    existingAuthorization.getRefreshToken();

if (refreshToken == null) {
    return;
}

OAuth2Authorization updated = OAuth2Authorization
    .from(existingAuthorization)
    .invalidate(refreshToken.getToken())
    .build();

authorizationService.save(updated);
~~~

Đây là cập nhật trạng thái token trong authorization. Phải lưu lại đối tượng mới qua `OAuth2AuthorizationService.save` để database/cache được cập nhật. Không chỉ thay đổi một Map cục bộ rồi bỏ qua persistence.

## 8. Cập nhật claims trước khi phát hành token

### 8.1. JWT claims được quyết định trước khi ký

Với self-contained Access Token, custom claim cần được đưa vào JWT trước khi ký. `OAuth2TokenCustomizer<JwtEncodingContext>` là extension point cho JWT generation.

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
        TenantResolver tenantResolver) {

    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            String tenantId =
                tenantResolver.resolve(context.getPrincipal());

            context.getClaims().claim("tenant_id", tenantId);
        }
    };
}
~~~

`TenantResolver` là service thuộc ứng dụng, minh họa cách lấy tenant từ principal đã được xác thực. Không lấy tenant từ request parameter chưa được xác minh.

### 8.2. Lưu metadata sau khi token được phát hành

Sau khi token được tạo, SAS đưa token và metadata vào `OAuth2Authorization` rồi gọi `OAuth2AuthorizationService.save(...)`. Custom store cần lưu:

- Token value hoặc representation có thể khôi phục.
- Issued-at và expires-at.
- Token type, scopes nếu có.
- Claims metadata.
- Invalidation metadata.
- Các application metadata đã được thêm hợp lệ.

Với JWT, token payload đã ký là nguồn claim mà Resource Server xác minh. Claims được lưu trong authorization metadata phục vụ truy vấn/introspection hoặc logic nội bộ; chúng không thay thế chữ ký.

### 8.3. Opaque token và introspection

Opaque Access Token không tự mang payload có thể giải mã ở Resource Server. Khi introspection được sử dụng, Authorization Server tra authorization record và trả trạng thái/claims theo cấu hình.

Custom store phải bảo đảm introspection đọc được đúng:

- Trạng thái active/inactive.
- Expiry.
- Client/principal.
- Scope.
- Claims hoặc metadata được phép công bố.

Không trả mọi application metadata hoặc dữ liệu nội bộ trong introspection response. Chỉ công bố claims phù hợp với protocol và authorization policy.
## 9. Thiết kế schema cho custom store

### 9.1. Mô hình aggregate và token index

Một thiết kế có thể tách authorization record và token records:

~~~sql
CREATE TABLE oauth2_authorization (
    id                    varchar(100) PRIMARY KEY,
    registered_client_id  varchar(100) NOT NULL,
    principal_name        varchar(255) NOT NULL,
    authorization_grant_type varchar(255) NOT NULL,
    authorized_scopes     jsonb NOT NULL,
    attributes_json       jsonb NOT NULL,
    schema_version        integer NOT NULL,
    version               bigint NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL,
    updated_at            timestamptz NOT NULL,
    retention_until       timestamptz
);

CREATE TABLE oauth2_authorization_token (
    token_id              uuid PRIMARY KEY,
    authorization_id      varchar(100) NOT NULL
        REFERENCES oauth2_authorization(id) ON DELETE CASCADE,
    token_type            varchar(80) NOT NULL,
    token_value_ciphertext bytea,
    token_lookup_hash     bytea,
    issued_at             timestamptz,
    expires_at            timestamptz,
    token_type_value      varchar(40),
    scopes_json           jsonb,
    claims_json           jsonb,
    metadata_json         jsonb NOT NULL,
    invalidated           boolean NOT NULL DEFAULT false,
    is_current            boolean NOT NULL DEFAULT true,
    UNIQUE (token_type, token_lookup_hash)
);

CREATE INDEX idx_oauth2_authorization_client_principal
    ON oauth2_authorization(registered_client_id, principal_name);

CREATE INDEX idx_oauth2_authorization_retention
    ON oauth2_authorization(retention_until);

CREATE INDEX idx_oauth2_authorization_token_lookup
    ON oauth2_authorization_token(token_type, token_lookup_hash);
~~~

Đây là schema định hướng cho PostgreSQL, không phải schema bắt buộc của SAS. Điều chỉnh kiểu dữ liệu, độ dài, JSON type, khóa và index theo database/workload thực tế.

### 9.2. Vì sao tách token records?

Token records có thời hạn, trạng thái invalidation và metadata riêng. Tách chúng giúp:

- Lookup token theo type và hash nhanh.
- Index expiry để cleanup.
- Cập nhật token metadata mà không serialize lại toàn bộ aggregate ở tầng SQL.
- Mã hóa token value riêng.
- Giữ token history nếu cần phát hiện refresh token replay.

`OAuth2Authorization` hiện biểu diễn các token hiện tại theo token class. Nếu cần giữ lịch sử các refresh token đã rotation, hãy có bảng history/replay riêng; không cố nhét mọi token cũ vào map token hiện tại của framework.

### 9.3. Token lookup index

Authorization Server thường cần tìm authorization bằng raw token. Không scan toàn bảng.

Có thể tạo lookup hash bằng HMAC-SHA-256 với secret key quản lý riêng:

~~~java
byte[] lookupHash = tokenHasher.hmacSha256(rawToken);
~~~

Khi nhận request, tính lại HMAC từ token gửi vào và query index theo token type. Dùng khóa HMAC có version để có thể rotate; trong thời gian chuyển đổi có thể lookup bằng tập key hiện hành theo policy.

Nếu cần khôi phục token value để dựng lại `OAuth2Authorization`, lưu bản token được mã hóa có xác thực (ví dụ AES-GCM) với key version. HMAC hash chỉ phục vụ lookup, không thể giải mã thành token.

### 9.4. Kích thước cột

Token, attributes, claims và metadata có thể dài hơn varchar mặc định. Dùng TEXT/CLOB/JSONB hoặc kiểu phù hợp; đặt giới hạn thực tế theo kích thước payload. Spring Authorization Server JPA guide cũng lưu ý cần tùy chỉnh chiều dài/kiểu cột theo database và thử nghiệm trước production.

## 10. Serialization/deserialization với mapper

### 10.1. Mapping hai chiều

Custom persistence nên có một component riêng chịu trách nhiệm chuyển đổi:

~~~text
OAuth2Authorization
        |
        v
AuthorizationRecord + TokenRecords
        |
        v
JSON metadata / encrypted token values
        |
        v
Database or distributed store
~~~

Khi đọc:

1. Tải authorization record.
2. Tìm RegisteredClient bằng `registered_client_id`.
3. Khôi phục grant type và authorized scopes.
4. Deserialize attributes bằng mapper đã cấu hình.
5. Khôi phục từng token đúng kiểu cụ thể.
6. Khôi phục token metadata, claims và invalidation state.
7. Tạo lại `OAuth2Authorization` bằng Builder.

### 10.2. RegisteredClient là dependency khi deserialize

`OAuth2Authorization.withRegisteredClient(registeredClient)` cần đối tượng RegisteredClient, không chỉ chuỗi client ID. Vì vậy custom service phải phụ thuộc `RegisteredClientRepository`.

Nếu client ID nội bộ không còn tồn tại, không được âm thầm tạo một client mặc định. Hãy báo lỗi retrieval rõ ràng, phát metric và xử lý dữ liệu orphan theo quy trình quản trị.

### 10.3. Khôi phục token đúng loại

Không khôi phục mọi token thành `OAuth2AccessToken`. Cần map đúng loại:

| Token class | Dữ liệu cần phục hồi |
| --- | --- |
| `OAuth2AuthorizationCode` | Value, issuedAt, expiresAt |
| `OAuth2AccessToken` | Type, value, issuedAt, expiresAt, scopes |
| `OAuth2RefreshToken` | Value, issuedAt, expiresAt |
| `OidcIdToken` | Value, issuedAt, expiresAt, claims |
| `OAuth2DeviceCode` | Value, issuedAt, expiresAt |
| `OAuth2UserCode` | Value, issuedAt, expiresAt |

Với token metadata, gọi Builder token overload nhận metadata consumer để khôi phục Map metadata tương ứng.

### 10.4. Custom grant type

`AuthorizationGrantType` cho phép giá trị custom. Khi deserialize, không giả định chỉ có các hằng số grant type chuẩn. Lưu chuỗi `authorizationGrantType.getValue()` và khôi phục bằng hằng số chuẩn nếu khớp, nếu không dùng `new AuthorizationGrantType(value)`.

Cùng nguyên tắc áp dụng cho custom token type hoặc metadata key: lưu giá trị ổn định, có namespace và có mapping rõ.

## 11. Triển khai OAuth2AuthorizationService tùy chỉnh

### 11.1. Skeleton service

Ví dụ sau minh họa ranh giới giữa service, codec và repository. Các interface `AuthorizationStore`, `AuthorizationCodec` và `TokenHasher` là abstraction của ứng dụng:

~~~java
public final class StoreOAuth2AuthorizationService
        implements OAuth2AuthorizationService {

    private final AuthorizationStore store;
    private final AuthorizationCodec codec;
    private final TokenHasher tokenHasher;

    public StoreOAuth2AuthorizationService(
            AuthorizationStore store,
            AuthorizationCodec codec,
            TokenHasher tokenHasher) {

        Assert.notNull(store, "store cannot be null");
        Assert.notNull(codec, "codec cannot be null");
        Assert.notNull(tokenHasher, "tokenHasher cannot be null");

        this.store = store;
        this.codec = codec;
        this.tokenHasher = tokenHasher;
    }

    @Override
    public void save(OAuth2Authorization authorization) {
        Assert.notNull(authorization, "authorization cannot be null");

        AuthorizationRecord record = codec.toRecord(authorization);
        store.upsert(record);
    }

    @Override
    public void remove(OAuth2Authorization authorization) {
        Assert.notNull(authorization, "authorization cannot be null");

        store.deleteById(authorization.getId());
    }

    @Override
    public OAuth2Authorization findById(String id) {
        Assert.hasText(id, "id cannot be empty");

        return store.findById(id)
            .map(codec::toObject)
            .orElse(null);
    }

    @Override
    public OAuth2Authorization findByToken(
            String token, OAuth2TokenType tokenType) {

        Assert.hasText(token, "token cannot be empty");

        byte[] lookupHash = tokenHasher.hash(token);

        return store.findByToken(lookupHash, tokenType)
            .map(codec::toObject)
            .orElse(null);
    }
}
~~~

Skeleton này cần được hoàn thiện bằng transaction, error mapping, key rotation và implementation cụ thể của store. Điểm quan trọng là `save` phải hỗ trợ update trạng thái authorization hiện có, không chỉ insert một row mới.

### 11.2. save phải là upsert có kiểm soát

SAS gọi `save` khi tạo authorization và khi cập nhật token/state. Vì vậy:

- Record chưa tồn tại: insert.
- Record đã tồn tại: update.
- Token mới được thêm: cập nhật token index.
- Token cũ bị invalidated: cập nhật metadata/index.
- Token rotation: thay current token và giữ history nếu policy cần.
- Metadata update: không làm mất attributes/token khác.

Trong JDBC/JPA, dùng transaction bao trùm việc ghi parent, token records và token indexes. Nếu chỉ cập nhật parent mà token index vẫn trỏ tới token cũ, token lookup có thể trả authorization sai.

### 11.3. findByToken phải hỗ trợ đúng token type

Với `tokenType` cụ thể, lookup nên dùng index tương ứng. Với `tokenType == null`, cần tìm trên các token/state mà service hỗ trợ, giống cách implementation mặc định có thể tìm nhiều loại token.

Không trả authorization chỉ vì hash khớp nếu token type không khớp. Kiểm tra thêm token value sau giải mã khi cần để phòng collision hoặc sai key version. Không log raw token trong query diagnostics.

### 11.4. remove khác revoke

`remove(authorization)` xóa toàn bộ authorization aggregate. Revocation một token thường cần đánh dấu token đó invalidated và `save` authorization đã cập nhật, để các token khác trong cùng authorization vẫn giữ trạng thái.

Không gọi remove chỉ vì Access Token bị revoke nếu Refresh Token còn active hoặc cần record cho introspection/audit.

## 12. Cập nhật metadata và token theo lifecycle

### 12.1. Authorization Code được redeem

Khi Authorization Code được dùng, code cần trở thành inactive/invalidated theo protocol flow. Custom store phải persist trạng thái này cùng token mới được phát hành. Không xóa toàn bộ authorization nếu Access Token/Refresh Token mới vừa được gắn vào cùng aggregate.

### 12.2. Refresh Token rotation

Khi `reuseRefreshTokens(false)`, refresh flow cấp Refresh Token mới. Custom store cần:

1. Xác minh Refresh Token cũ còn active.
2. Xử lý token cũ theo trạng thái rotation/invalidation mà SAS cung cấp.
3. Lưu token mới và thời điểm phát hành/hết hạn mới.
4. Cập nhật Access Token mới nếu flow phát hành.
5. Cập nhật lookup index trong cùng transaction.
6. Lưu history/hash token cũ nếu cần replay detection.

Không để refresh token cũ vẫn được lookup như active sau khi đã rotation. Nếu cần phát hiện replay, lưu token hash cũ trong history với trạng thái đã sử dụng/revoked và retention policy riêng.

### 12.3. Revocation

Khi token revocation endpoint xử lý một token, provider tìm authorization qua `findByToken`, xác định token type và cập nhật trạng thái. Custom service cần bảo toàn invalidation metadata và lưu thay đổi.

Nếu Access Token JWT được Resource Server xác minh offline, cập nhật database tại AS không tự làm JWT mất hiệu lực ở Resource Server. Muốn revoke có hiệu lực sớm, Resource Server phải có introspection, denylist hoặc cơ chế online/propagated revocation.

### 12.4. Cập nhật client TokenSettings

Khi admin cập nhật TokenSettings của RegisteredClient, các token đã phát hành vẫn giữ `issuedAt`/`expiresAt` gốc. Không deserialize authorization rồi tự thay expiresAt bằng TTL mới. Nếu muốn chặn token cũ, thực hiện revocation rõ ràng.
## 13. Concurrency và tính nhất quán

### 13.1. Authorization Code chỉ được dùng một lần

Hai request đồng thời có thể cùng đọc một authorization code trước khi một request kịp lưu invalidation. Nếu store chỉ thực hiện read rồi write thông thường, cả hai request có nguy cơ đi qua kiểm tra active.

`OAuth2AuthorizationService` không có phương thức riêng kiểu `consumeAuthorizationCodeAtomically`. Với yêu cầu one-time use nghiêm ngặt trong distributed deployment, cần thiết kế transaction/locking hoặc cơ chế atomic claim phối hợp với grant processing, chẳng hạn:

- Lock row theo authorization ID.
- Optimistic version và retry khi conflict.
- Conditional update trạng thái code từ active sang consumed.
- Unique/compare-and-set constraint cho code consumption.

Chỉ thêm trường version mà không kiểm tra version khi ghi không tạo ra optimistic locking thực sự.

### 13.2. Refresh token rotation cần atomicity

Hai refresh request cùng dùng một token có thể gây race. Nếu cả hai cùng đọc trạng thái active rồi cấp token mới, hệ thống có thể tạo hai nhánh refresh.

Dùng row lock hoặc conditional update cho token cũ, và chỉ phát hành token mới khi thao tác consume token cũ thành công. Kiểm thử bằng nhiều request đồng thời, không chỉ test tuần tự.

### 13.3. Cache và database

Nếu dùng cache:

- Database/store bền vững là nguồn trạng thái chính.
- Invalidation/revocation phải cập nhật cache hoặc phát event.
- Cache không được giữ token active sau khi database đã đánh dấu invalidated.
- TTL cache không được kéo dài hơn token expiry.
- Cache miss phải đọc được bản mới nhất từ nguồn chính theo consistency policy.

Với token revocation, stale cache có thể làm Resource Server hoặc introspection endpoint tiếp tục coi token active. Chọn consistency và propagation delay dựa trên mức rủi ro.

## 14. Cấu hình custom service vào Authorization Server

Custom service có thể được cung cấp như bean và gắn vào `OAuth2AuthorizationServerConfigurer`:

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationServerPersistenceConfiguration {

    @Bean
    OAuth2AuthorizationService authorizationService(
            AuthorizationStore store,
            AuthorizationCodec codec,
            TokenHasher tokenHasher) {

        return new StoreOAuth2AuthorizationService(
            store, codec, tokenHasher);
    }

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizationService authorizationService)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.authorizationService(authorizationService));

        return http.build();
    }
}
~~~

Đây là fragment minh họa wiring. Ứng dụng hoàn chỉnh vẫn cần RegisteredClientRepository, AuthorizationServerSettings, token generator/JWK configuration và user authentication chain. Nếu application context đã tự nhận bean service, tránh tạo thêm implementation khác khiến endpoint dùng nhầm bean.

## 15. JDBC, JPA và Redis: chọn cấu trúc phù hợp

### 15.1. JdbcOAuth2AuthorizationService

SAS cung cấp `JdbcOAuth2AuthorizationService` dùng `JdbcOperations` và schema SQL đi kèm. Đây là implementation đơn giản có thể dùng trong production, nhưng API docs lưu ý nó có thể không phù hợp workload throughput cao; ứng dụng có thể cần implementation riêng.

Có thể tùy chỉnh `OAuth2AuthorizationParametersMapper` và `OAuth2AuthorizationRowMapper` để thay cách map dữ liệu. Trước khi viết custom service hoàn toàn, đánh giá liệu mở rộng mapper hoặc schema hiện có đã đủ chưa.

### 15.2. JPA

JPA guide chính thức cung cấp một mô hình entity/repository để map `OAuth2Authorization`. Đây là điểm khởi đầu, không phải schema tối ưu cho mọi database. Các trường token, metadata, settings và claims có thể dài; cần điều chỉnh column type/length và index.

### 15.3. Redis hoặc key-value store

Redis phù hợp cho lookup nhanh, TTL theo key và distributed cache. Tuy nhiên, cần xử lý:

- Nhiều token thuộc cùng authorization aggregate.
- Atomic update khi refresh/revoke.
- Serialization versioning.
- Token lookup index và key rotation.
- Persistence durability/replication/failover.
- Backup/restore và cleanup.
- Khả năng truy vấn phục vụ audit.

Không đặt toàn bộ authorization vào một Redis key có TTL bằng token ngắn nhất. Có thể dùng parent aggregate key và token index riêng, hoặc giữ database làm source of truth và Redis làm cache.

## 16. Bảo vệ token value và metadata

### 16.1. Token value là credential

Access Token, Refresh Token, Authorization Code, Device Code và User Code đều có thể cho phép thực hiện hành động trong protocol. Không lưu raw token vào log, tracing span, metric label hoặc exception message.

Nếu cần khôi phục token value:

- Mã hóa authenticated encryption như AES-GCM.
- Lưu key version để hỗ trợ rotation.
- Quản lý encryption key qua KMS/secret manager.
- Hạn chế quyền đọc bảng/token store.
- HMAC token để index lookup thay vì plaintext index.

### 16.2. Không đưa secret vào metadata không kiểm soát

Không lưu client secret dạng plaintext trong authorization attributes. Không lưu password, private key, session cookie hoặc raw credentials vào custom metadata. Chỉ lưu dữ liệu cần cho protocol và vận hành.

### 16.3. Claims có thể chứa dữ liệu cá nhân

Claims và principal attributes có thể chứa PII hoặc thông tin phân quyền nhạy cảm. Áp dụng data minimization, encryption at rest, retention phù hợp và kiểm soát quyền truy cập. Không trả toàn bộ metadata nội bộ qua introspection hoặc API quản trị.

### 16.4. Audit riêng với operational state

Operational authorization record có thể bị cleanup sau khi mọi token hết hạn. Nếu cần audit dài hạn, ghi sự kiện cấp token, refresh, revoke và cleanup vào audit/event store riêng. Không kéo dài TTL của token chỉ để giữ audit.

## 17. Kiểm thử custom persistence

### 17.1. Round-trip serialization

Tạo authorization có các token và attributes đại diện, lưu xuống store rồi đọc lại:

~~~java
OAuth2Authorization original = createAuthorizationFixture();

authorizationService.save(original);

OAuth2Authorization restored =
    authorizationService.findById(original.getId());

assertThat(restored).isNotNull();
assertThat(restored.getRegisteredClientId())
    .isEqualTo(original.getRegisteredClientId());
assertThat(restored.getPrincipalName())
    .isEqualTo(original.getPrincipalName());
assertThat(restored.getAuthorizationGrantType())
    .isEqualTo(original.getAuthorizationGrantType());
assertThat(restored.getAuthorizedScopes())
    .isEqualTo(original.getAuthorizedScopes());
~~~

Bổ sung assertion cho từng token value/type, issuedAt, expiresAt, claims, metadata, invalidation và attributes. Test riêng custom principal, custom grant type và record schema version cũ.

### 17.2. Test TTL và cleanup

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Authorization Code hết hạn | Code inactive; record còn nếu token khác cần |
| Access Token hết hạn | Access token inactive; Refresh Token vẫn được tra cứu |
| Refresh Token còn hạn | Authorization không bị cleanup |
| Mọi token hết hạn | Record đủ điều kiện retention cleanup |
| Token không có expiresAt | Cleanup theo policy riêng, không xóa sớm |
| TokenSettings đổi | Token cũ giữ expiresAt ban đầu |
| Clock skew | Không tạo token sống lâu hơn policy ngoài dự kiến |
| Cache TTL | Không vượt token expiry hoặc giữ trạng thái revoked |

### 17.3. Test token metadata

- Cập nhật custom metadata nhưng giữ claims metadata.
- Đọc lại metadata sau restart.
- Invalidate token rồi xác nhận `isInvalidated()` và `isActive()` đúng.
- Thêm claim trước khi phát hành JWT và xác minh claim trong JWT đã ký.
- Sửa metadata trong database sau phát hành và xác nhận JWT cũ không thay đổi.
- Kiểm tra introspection chỉ trả claims được phép.

### 17.4. Test findByToken

Test với Authorization Code, Access Token, Refresh Token, ID Token, Device Code, User Code và các token type custom mà ứng dụng hỗ trợ.

Kiểm tra cả trường hợp `tokenType` cụ thể, `tokenType == null`, token không tồn tại, token đã expired, token đã invalidated và token lookup bằng hash/key version sau khi rotate HMAC key.

### 17.5. Test concurrency

Chạy đồng thời:

- Hai request redeem cùng Authorization Code.
- Hai request dùng cùng Refresh Token khi rotation bật.
- Revocation và introspection cùng thời điểm.
- Metadata update và token refresh cùng thời điểm.
- Cleanup job và refresh request cùng thời điểm.

Kết quả cần bảo đảm token one-time không được consume hai lần, token revoked không quay lại active do stale write và cleanup không xóa authorization còn token cần dùng.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Refresh Token bị từ chối sau vài phút | Cleanup dùng TTL của Authorization Code hoặc Access Token cho cả aggregate | Tính retention theo token còn cần |
| findByToken trả null dù token có trong record | Token index chưa cập nhật hoặc hash key version sai | Kiểm tra token type, HMAC và index transaction |
| Introspection báo inactive sai | Metadata invalidation/expiry deserialize sai | Kiểm tra issuedAt, expiresAt và metadata chuẩn |
| Refresh Token rotation không hoạt động | save chỉ insert, không update | Triển khai upsert và transaction |
| Token cũ vẫn refresh được | Trạng thái invalidation không được lưu | Persist token metadata và kiểm tra atomicity |
| Authorization không deserialize sau nâng cấp | JSON schema/class type thay đổi | Schema version, migration và compatibility reader |
| Claims biến mất sau round-trip | Serializer bỏ metadata claims | Khôi phục token metadata đầy đủ |
| JWT vẫn chứa claim cũ | Sửa database metadata sau khi JWT đã ký | Reissue token qua token customizer |
| Device flow lỗi sau khi cleanup | Device/User Code bị xóa trước khi flow hoàn tất | Tách TTL theo từng token |
| Cluster node trả trạng thái khác nhau | Cache invalidation hoặc replication lag | Source of truth và propagation policy |
| Duplicate authorization record | save không upsert theo authorization ID | Primary key và transactional upsert |
| Dữ liệu bị mất sau refresh | Mapper chỉ ghi token mới, bỏ các token khác | Round-trip toàn aggregate trước khi save |
| Token lộ trong log | Debug SQL/request ghi raw token | Redaction và token-safe diagnostics |

## 19. Checklist production

- [ ] RegisteredClient có TokenSettings riêng theo loại client và mức rủi ro.
- [ ] TTL được cấu hình cho Authorization Code, Access Token, Refresh Token và Device Code.
- [ ] Không giả định ID Token có builder method TTL riêng trong TokenSettings 1.5.8.
- [ ] Mỗi token lưu issuedAt/expiresAt thực tế.
- [ ] Storage retention không ngắn hơn vòng đời token còn cần.
- [ ] Authorization record không bị xóa khi một token trong aggregate vừa hết hạn.
- [ ] save là upsert có transaction.
- [ ] remove chỉ xóa toàn bộ authorization khi đúng policy.
- [ ] findByToken hỗ trợ token type và trường hợp null.
- [ ] Token metadata claims/invalidation được serialize đầy đủ.
- [ ] Authorization attributes được serialize an toàn.
- [ ] Custom grant type được khôi phục từ string value.
- [ ] JSON schema có version và migration strategy.
- [ ] Jackson module/subtype được allowlist.
- [ ] Token value được mã hóa hoặc bảo vệ phù hợp; lookup index không chứa raw token.
- [ ] HMAC/encryption key có version và rotation plan.
- [ ] Token metadata update giữ lại metadata chuẩn.
- [ ] JWT claims được thêm trước khi ký token.
- [ ] Refresh token rotation cập nhật token/index/history atomically.
- [ ] Authorization Code one-time use được bảo vệ trước concurrency.
- [ ] Cache không giữ token active sau revocation.
- [ ] Cleanup job idempotent, có batch và metric.
- [ ] Audit được lưu riêng nếu cần retention dài hạn.
- [ ] Có round-trip, expiry, revoke, rotation, concurrency và migration tests.
- [ ] Không log raw token, credential hoặc claims nhạy cảm.

## 20. Tài liệu tham khảo và kết luận

Tài liệu chính thức:

- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationService.html)
- [Spring Authorization Server 1.5.8 — OAuth2Authorization API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html)
- [Spring Authorization Server 1.5.8 — OAuth2Authorization.Token API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Token.html)
- [Spring Authorization Server 1.5.8 — OAuth2Authorization.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Builder.html)
- [Spring Authorization Server 1.5.8 — TokenSettings API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.html)
- [Spring Authorization Server 1.5.8 — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html)
- [Spring Authorization Server — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html)
- [Spring Authorization Server 1.5.8 — JdbcOAuth2AuthorizationService API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/JdbcOAuth2AuthorizationService.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)

**Kết luận:** Custom persistence cần bảo toàn cả authorization aggregate chứ không chỉ token value. `TokenSettings` quyết định TTL khi phát hành; `issuedAt` và `expiresAt` của token đã tạo là dữ liệu có thẩm quyền để khôi phục. Storage retention phải xét tất cả token còn cần trong authorization. Serialization cần giữ attributes, token class, claims và metadata chuẩn; custom metadata phải có namespace và không được làm mất invalidation flag hoặc claims metadata. Khi cập nhật, dùng `OAuth2Authorization.from(existing)`, thay đổi đúng field rồi gọi `OAuth2AuthorizationService.save`. Với refresh rotation, revocation và authorization code one-time use, persistence phải có transaction/concurrency control và token index đồng bộ. Khi các quy tắc này được kiểm thử cùng nhau, Authorization Server có thể khôi phục trạng thái nhất quán sau restart, scale-out và nâng cấp schema.




