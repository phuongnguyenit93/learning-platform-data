# Cache client, authorization và cơ chế vô hiệu hóa cache

## 1. Bối cảnh và mục tiêu

Trong **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, nhiều protocol endpoint đọc lặp lại cùng dữ liệu: client configuration, authorization đã cấp và consent của người dùng. Khi số lượng request tăng, việc đọc database cho mỗi lần xác thực client, introspection, refresh token hoặc authorization request có thể tạo độ trễ và tải I/O đáng kể.

Cache giúp giảm số lần đọc persistence store, nhưng dữ liệu Authorization Server có đặc tính khác cache danh mục hoặc dữ liệu tham khảo thông thường. Một thay đổi nhỏ có thể làm thay đổi quyền truy cập:

- Client bị disable hoặc secret bị rotate.
- Redirect URI, grant type, authentication method hoặc scope của client bị thay đổi.
- Access token hoặc refresh token bị revoke.
- Refresh token rotation làm token cũ mất hiệu lực và token mới được phát hành.
- Người dùng rút consent đã cấp cho một client.

Nếu cache giữ bản cũ sau khi database đã cập nhật, Authorization Server có thể tiếp tục chấp nhận client secret cũ, trả introspection active cho token đã revoke hoặc bỏ qua việc người dùng vừa rút consent. Vì vậy, cache phải được thiết kế cùng cơ chế đồng bộ và vô hiệu hóa dữ liệu.

Ví dụ xuyên suốt: Authorization Server tại `https://auth.example.com` chạy ba instance sau load balancer. Instance A xử lý request refresh token; instance B xử lý introspection; instance C xử lý authorization request. Cả ba instance dùng cùng database nhưng mỗi instance có cache Caffeine cục bộ. Khi instance A revoke token, cache ở B và C cũng phải được cập nhật theo một chính sách nhất quán.

Sau bài học, bạn có thể:

1. Phân biệt dữ liệu của `RegisteredClientRepository`, `OAuth2AuthorizationService` và `OAuth2AuthorizationConsentService`.
2. Xác định dữ liệu nào phù hợp để cache, cache key nào cần dùng và TTL nên phụ thuộc vào điều kiện nào.
3. Xây cache decorator cho các core service của Spring Authorization Server.
4. Vô hiệu hóa cache khi client, authorization hoặc consent được lưu, cập nhật hay xóa.
5. Xử lý token rotation, token revocation và thay đổi client secret.
6. Đồng bộ cache giữa nhiều Authorization Server instance.
7. Dùng transaction after-commit, transactional outbox và version để giảm cache inconsistency.
8. Phân biệt eventual consistency với yêu cầu revoke có hiệu lực ngay.
9. Kiểm thử stale cache, race condition, event trùng lặp và node mất kết nối.
10. Theo dõi cache hit ratio, eviction, invalidation lag và tác động tới protocol endpoint.

**Phạm vi phiên bản:** Nội dung tham chiếu Spring Authorization Server 1.5.8, Spring Security 6.x và Spring Framework 6.x. Spring Authorization Server cung cấp các repository/service in-memory và JDBC; bài học trình bày cách bọc chúng bằng cache do ứng dụng quản lý. Không có cache decorator mặc định được bật tự động cho ba core service này.

## 2. Ba nhóm dữ liệu cần cache

### 2.1. RegisteredClient

`RegisteredClientRepository` quản lý client đã đăng ký. Các API chính:

~~~java
RegisteredClient findById(String id);
RegisteredClient findByClientId(String clientId);
void save(RegisteredClient registeredClient);
~~~

Một `RegisteredClient` chứa client ID, client secret đã encode, authentication methods, grant types, redirect URI, post-logout redirect URI, scopes, client settings và token settings.

Đây là dữ liệu tương đối ổn định so với authorization. Một client có thể được đọc hàng nghìn lần trong khi metadata chỉ thay đổi vài lần mỗi ngày. Vì vậy, cache client thường đem lại hiệu quả tốt.

Các luồng có thể đọc RegisteredClient:

- Client authentication tại Token Endpoint.
- Authorization Code Flow và các grant khác.
- Token introspection/revocation khi cần xác định client.
- OIDC Dynamic Client Registration và Client Configuration.
- Xử lý consent và metadata discovery có liên quan đến client.

Cache phải hỗ trợ cả hai khóa tra cứu: internal ID và client ID. Nếu chỉ cache theo client ID, lời gọi `findById` vẫn có thể đi xuống database; nếu chỉ cache theo ID, lookup trong client authentication vẫn có thể miss.

### 2.2. OAuth2Authorization

`OAuth2AuthorizationService` quản lý authorization đã cấp. Các API chính:

~~~java
void save(OAuth2Authorization authorization);
void remove(OAuth2Authorization authorization);
OAuth2Authorization findById(String id);
OAuth2Authorization findByToken(
    String token,
    OAuth2TokenType tokenType
);
~~~

Một `OAuth2Authorization` có thể chứa nhiều token tùy grant type:

- Authorization Code Flow: authorization code, access token và có thể có refresh token.
- OIDC Authorization Code Flow: authorization code, ID Token, access token và có thể có refresh token.
- Client Credentials: access token.
- Device Authorization Flow: device code, user code và các trạng thái liên quan.

Authorization cũng chứa principal, client ID nội bộ, grant type, scopes, attributes và metadata. Trạng thái token có thể thay đổi khi token hết hạn hoặc bị invalidated. `OAuth2Authorization.Token` cung cấp `isExpired()`, `isInvalidated()` và `isActive()`.

Đây là nhóm dữ liệu nhạy cảm nhất đối với cache. Nếu cache giữ authorization trước khi revoke, một lần introspection có thể nhìn thấy token vẫn active. Nếu cache giữ bản cũ sau refresh rotation, token cũ có thể tiếp tục được tìm thấy hoặc token mới chưa được nhận diện.

### 2.3. OAuth2AuthorizationConsent

`OAuth2AuthorizationConsentService` quản lý consent theo cặp RegisteredClient ID và principal name:

~~~java
OAuth2AuthorizationConsent findById(
    String registeredClientId,
    String principalName
);

void save(OAuth2AuthorizationConsent authorizationConsent);
void remove(OAuth2AuthorizationConsent authorizationConsent);
~~~

Consent chứa các authority mà resource owner đã cấp cho client. Một authority có thể đại diện cho scope, claim, permission hoặc role.

Cache key phải bao gồm cả `registeredClientId` và `principalName`. Chỉ dùng client ID sẽ khiến consent của một người dùng có thể bị trả cho người dùng khác.

### 2.4. So sánh ba nhóm cache

| Nhóm | Khóa tra cứu | Tần suất thay đổi | Rủi ro khi stale |
| --- | --- | --- | --- |
| RegisteredClient | ID và client ID | Thấp đến trung bình | Chấp nhận secret cũ, client bị disable vẫn được dùng, metadata redirect/grant cũ tiếp tục có hiệu lực. |
| OAuth2Authorization | Authorization ID, token value và token type | Cao | Token đã revoke vẫn có thể bị xem là active; token rotation không được phản ánh. |
| OAuth2AuthorizationConsent | RegisteredClient ID + principal name | Trung bình | Quyền đã rút vẫn có thể được xem là đã consent. |

Không nên áp dụng cùng TTL, cache key hoặc invalidation policy cho cả ba nhóm.

## 3. Cache nằm ở đâu trong kiến trúc?

### 3.1. Cache decorator bao quanh core service

Spring Authorization Server sử dụng core service thông qua interface. Có thể đặt một decorator giữa protocol endpoint và persistence implementation:

~~~mermaid
flowchart TD
    A["Authorization / Token / Introspection Endpoints"] --> B["RegisteredClientRepository"]
    A --> C["OAuth2AuthorizationService"]
    A --> D["OAuth2AuthorizationConsentService"]
    B --> E["Cache Decorator"]
    C --> F["Cache Decorator"]
    D --> G["Cache Decorator"]
    E --> H["JDBC / JPA Repository"]
    F --> I["JDBC / JPA Authorization Store"]
    G --> J["JDBC / JPA Consent Store"]
    H --> K[("Database")]
    I --> K
    J --> K
~~~

Decorator giữ nguyên contract của interface và ủy quyền các thao tác đọc/ghi cho implementation gốc. Cách này giúp protocol endpoint không cần biết cache đang dùng Caffeine, Redis hay một distributed cache khác.

### 3.2. Không nhầm InMemory service với cache

Spring Authorization Server có `InMemoryRegisteredClientRepository`, `InMemoryOAuth2AuthorizationService` và `InMemoryOAuth2AuthorizationConsentService`. Các implementation này lưu dữ liệu trực tiếp trong bộ nhớ và phù hợp cho development/testing theo tài liệu framework.

Chúng không phải cache đặt trước JDBC persistence. Nếu một instance dùng InMemory service và instance khác dùng JDBC, hai instance không chia sẻ cùng trạng thái. Khi restart hoặc scale out, dữ liệu trong memory không tự đồng bộ.

Trong production, cache thường là một lớp bổ sung trước persistent repository/service. Database hoặc durable store vẫn là nguồn dữ liệu chính.

### 3.3. Local cache và distributed cache

| Kiểu cache | Ví dụ | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Local in-process | Caffeine | Độ trễ thấp, không cần network, giảm tải database. | Mỗi instance có bản cache riêng; phải phát invalidation tới mọi node. |
| Distributed cache | Redis | Các instance chia sẻ một cache namespace. | Thêm network hop, phụ thuộc cache cluster và vẫn cần xử lý race với transaction database. |
| Hybrid | Caffeine + Redis | Local read nhanh, Redis chia sẻ trạng thái. | Phức tạp hơn; phải quản lý hai tầng cache và invalidation cả hai. |

Với local cache, invalidation event phải tới tất cả node. Với distributed cache, xóa một key có thể tác động mọi node đọc cùng key, nhưng dữ liệu cache vẫn có thể stale nếu ghi database và cache không được phối hợp đúng.

## 4. Thiết kế cache key

### 4.1. Namespace riêng cho từng loại dữ liệu

Không dùng chung một key space cho nhiều domain object. Ví dụ:

~~~text
client:{tenant}:{issuer}:id:{registeredClientId}
client:{tenant}:{issuer}:client-id:{clientId}

authorization:{tenant}:{issuer}:id:{authorizationId}
authorization:{tenant}:{issuer}:token:{tokenType}:{tokenDigest}
authorization:{tenant}:{issuer}:token:ANY:{tokenDigest}

consent:{tenant}:{issuer}:{registeredClientId}:{principalName}
~~~

Nếu một hệ thống phục vụ nhiều tenant hoặc nhiều issuer, tenant/issuer phải nằm trong cache namespace. Nếu không, hai Authorization Server dùng cùng client ID hoặc authorization ID có thể đọc nhầm dữ liệu của nhau.

### 4.2. Không dùng raw bearer token làm cache key

Token value là credential. Nếu dùng trực tiếp token làm key, giá trị có thể xuất hiện trong Redis key listing, monitoring, cache diagnostic dump, log của cache client hoặc snapshot/backup.

Nên dùng HMAC-SHA-256 với secret key do ứng dụng quản lý:

~~~java
String tokenCacheKey(
        SecretKey lookupKey,
        String tokenType,
        String token) throws GeneralSecurityException {

    Mac mac = Mac.getInstance("HmacSHA256");
    mac.init(lookupKey);
    mac.update(tokenType.getBytes(StandardCharsets.UTF_8));
    mac.update((byte) 0);
    byte[] digest = mac.doFinal(
        token.getBytes(StandardCharsets.UTF_8));

    return HexFormat.of().formatHex(digest);
}
~~~

Thành phần `tokenType` tạo domain separation: cùng một chuỗi ở hai loại token khác nhau tạo hai cache key khác nhau. Với lookup `tokenType=null`, dùng namespace `ANY` riêng. HMAC key không được lưu trong database cache, event payload hoặc source code; dùng secret manager/KMS.

### 4.3. Consent key phải có cả client và principal

Cache consent theo composite key có thể dùng structured key object trong local cache hoặc canonical encoding trong distributed cache. Ví dụ:

~~~java
record ConsentCacheKey(
    String registeredClientId,
    String principalName
) {}
~~~

Nếu cần chuỗi key, encode từng thành phần có phân cách an toàn hoặc dùng digest; không ghép hai chuỗi bằng dấu `:` nếu identifier có thể chứa chính dấu đó mà không escape. Principal name phải dùng cùng canonical form mà persistence service dùng; không tự lower-case hoặc normalize nếu hệ thống phân biệt hoa/thường.

### 4.4. Key phải ổn định qua các instance

Nếu cache phân tán hoặc invalidation event được phát giữa các instance, mọi node phải tạo cùng cache key từ cùng dữ liệu. Không dùng:

- Identity hash của object.
- Random UUID cho cache lookup.
- Java serialization phụ thuộc class version làm key.
- Hash code không được định nghĩa ổn định giữa process.

Hãy dùng canonical string/byte encoding và version namespace khi thay đổi định dạng key.

## 5. Cache RegisteredClient

### 5.1. Cache hai chiều lookup

`RegisteredClientRepository` có hai phương thức đọc:

- `findById(id)`.
- `findByClientId(clientId)`.

Có thể dùng hai cache alias trỏ tới cùng một immutable RegisteredClient snapshot:

~~~java
RegisteredClient findById(String id) {
    return byId.get(id, () -> {
        RegisteredClient client = delegate.findById(id);
        if (client != null) {
            byClientId.put(client.getClientId(), client);
        }
        return client;
    });
}

RegisteredClient findByClientId(String clientId) {
    return byClientId.get(clientId, () -> {
        RegisteredClient client =
            delegate.findByClientId(clientId);
        if (client != null) {
            byId.put(client.getId(), client);
        }
        return client;
    });
}
~~~

Đây là pseudocode minh họa cache decorator; `byId` và `byClientId` là cache abstraction do ứng dụng cấu hình, còn `delegate` là RegisteredClientRepository gốc.

### 5.2. Invalidate cả hai alias khi save

Khi cập nhật client:

1. Đọc bản cũ để biết client ID cũ nếu metadata cho phép thay đổi.
2. Ghi bản mới qua delegate.
3. Sau khi transaction commit, evict key theo internal ID.
4. Evict alias client ID cũ và client ID mới.
5. Phát invalidation event để các instance khác xóa cùng namespace.

Nếu chỉ evict `byId`, cache `byClientId` có thể tiếp tục trả bản cũ. Nếu client ID thay đổi mà chỉ evict ID mới, alias cũ vẫn còn.

### 5.3. Thay đổi nào cần invalidation?

Mọi thay đổi có ảnh hưởng đến protocol behavior cần làm mới cache:

- Client secret hoặc thời hạn secret.
- Client authentication methods và thuật toán xác thực.
- Authorization grant types.
- Redirect URI và post-logout redirect URI.
- Scopes được phép.
- PKCE/consent requirements trong ClientSettings.
- Access token/refresh token settings.
- Trạng thái enabled/disabled nếu ứng dụng có thuộc tính này.

Đặc biệt, khi rotate client secret, các instance không được tiếp tục chấp nhận secret cũ lâu hơn mức consistency policy cho phép.

### 5.4. Cache secret và dữ liệu nhạy cảm

`RegisteredClient` có thể chứa client secret đã encode. Javadoc của `RegisteredClientRepository` yêu cầu sensitive information như client secret được encode bên ngoài repository implementation.

Cache không thay thế PasswordEncoder. Không lưu secret plaintext, không ghi object RegisteredClient đầy đủ vào log, không đưa secret vào metric label và giới hạn quyền truy cập cache snapshot. Khi secret rotate, evict bản cũ sau commit.

## 6. Cache OAuth2Authorization

### 6.1. Cache theo authorization ID

`findById(id)` có thể được cache theo authorization ID. Cache value là một snapshot `OAuth2Authorization`:

~~~java
OAuth2Authorization findById(String id) {
    return authorizationById.get(
        id,
        () -> delegate.findById(id));
}
~~~

Không sửa trực tiếp object đã cache. Khi cần cập nhật token metadata hoặc invalidated state, tạo object mới bằng builder/copy mechanism của framework và gọi `save`. Nếu custom attributes bên trong chứa object mutable, phải bảo đảm snapshot không bị thay đổi ngoài luồng persistence.

### 6.2. Cache theo token value và token type

`findByToken(token, tokenType)` có thể được cache theo digest của token:

~~~text
authorization:token:access_token:{digest}
authorization:token:refresh_token:{digest}
authorization:token:code:{digest}
authorization:token:id_token:{digest}
authorization:token:user_code:{digest}
authorization:token:device_code:{digest}
authorization:token:ANY:{digest}
~~~

Cache có thể lưu toàn bộ authorization snapshot hoặc authorization ID. Nếu lưu ID, lần đọc tiếp theo cần cache hit theo ID để tránh quay lại database. Nếu lưu snapshot trực tiếp, phải evict mọi alias khi authorization thay đổi.

Trường hợp `tokenType=null` cần semantics tìm trên tất cả loại token mà implementation hỗ trợ. Không cache kết quả ANY như thể nó tương đương access token. Khi authorization thay đổi, phải evict cả typed key và ANY key của mọi token value liên quan.

### 6.3. Lập danh sách token alias cần evict

Một authorization có thể có nhiều token. Khi update, cache decorator cần biết cả token cũ và token mới. Có thể tạo helper ở tầng persistence để trích xuất:

- Authorization code.
- Access token.
- Refresh token.
- OIDC ID Token.
- User code.
- Device code.
- State nếu implementation cho phép tra cứu state qua `findByToken`.

`OAuth2Authorization` cung cấp các accessor như `getAccessToken()`, `getRefreshToken()` và `getToken(Class)`. Helper phải phản ánh đúng các loại token mà service lưu/tra cứu; không chỉ lấy access token.

Cache lookup theo token có thể dùng cùng một loader pattern:

~~~java
OAuth2Authorization findByToken(
        String token, OAuth2TokenType tokenType) {

    String key = tokenKeyFactory.create(token, tokenType);
    return byToken.get(
        key,
        () -> delegate.findByToken(token, tokenType));
}
~~~

`tokenKeyFactory` phải dùng HMAC digest và tạo namespace ANY riêng khi `tokenType` là null. Ví dụ này không cache raw token trong key. Cần bảo đảm cache entry được evict khi authorization thay đổi, kể cả trường hợp token value không đổi nhưng invalidated metadata thay đổi.

### 6.4. Invalidation khi save

Khi `save(authorization)` cập nhật cùng một authorization ID, có thể xảy ra:

- Token value giữ nguyên nhưng invalidated flag thay đổi.
- Refresh token cũ bị invalidated và token mới được thêm.
- Authorization code được đánh dấu consumed.
- Claims/metadata được cập nhật.
- Device/user code thay đổi trạng thái.

Vì vậy, chỉ evict cache theo authorization ID là chưa đủ nếu `findByToken` có cache alias riêng. Cần evict toàn bộ token key của snapshot cũ và snapshot mới.

Một quy trình write an toàn:

1. Đọc authorization cũ trong cùng transaction hoặc lấy token key từ reverse index đáng tin cậy.
2. Ghi authorization mới vào durable store.
3. Tạo invalidation event chứa authorization ID, version và fingerprint của token aliases cũ/mới.
4. Ghi event vào outbox trong cùng transaction.
5. Sau commit, evict local cache.
6. Các node còn lại xử lý event và evict cache tương ứng.

Pseudocode cho write path:

~~~java
@Transactional
public void save(OAuth2Authorization next) {
    OAuth2Authorization previous =
        delegate.findById(next.getId());

    delegate.save(next);

    long version = versionRepository.nextVersion(next.getId());
    Set<String> oldKeys = tokenKeyFactory.keysFor(previous);
    Set<String> newKeys = tokenKeyFactory.keysFor(next);

    outbox.append(AuthorizationChanged.of(
        next.getId(), version, oldKeys, newKeys));

    afterCommit(() -> {
        authorizationById.evict(next.getId());
        oldKeys.forEach(byToken::evict);
        newKeys.forEach(byToken::evict);
    });
}
~~~

`delegate`, `versionRepository`, `tokenKeyFactory` và `outbox` là thành phần do ứng dụng cung cấp. Chúng phải tham gia cùng transaction manager/database transaction; nếu outbox ghi ở database khác mà không có distributed transaction, cần một cơ chế đảm bảo tương đương. `keysFor` chỉ tạo fingerprint/HMAC cache key, không đưa raw token vào event. Ví dụ thể hiện ý tưởng; cần giữ semantics của mọi loại token và state mà implementation hỗ trợ.

### 6.5. Invalidation khi remove

`remove(authorization)` phải evict:

- Cache theo authorization ID.
- Cache theo mọi token value và token type của authorization.
- Cache alias ANY cho các token đó.
- Reverse index lưu danh sách alias của authorization.

Nếu chỉ xóa row trong database mà giữ token alias trong cache, `findByToken` có thể tiếp tục trả authorization đã bị xóa.

### 6.6. Không cache trạng thái active độc lập quá lâu

`OAuth2Authorization.Token.isActive()` được tính từ expiry và invalidated state. Nếu cache toàn bộ authorization snapshot, thời điểm expiry vẫn có thể được đánh giá khi đọc; nhưng invalidated state chỉ đổi khi snapshot được refresh/evict.

Không cache một boolean `active=true` với TTL dài hơn token lifetime hoặc invalidation SLA. Đối với introspection, nếu token đã revoke thì kết quả phải phản ánh trạng thái mới theo policy của hệ thống.

## 7. Cache OAuth2AuthorizationConsent

### 7.1. Cache theo composite key

Cache consent theo:

~~~text
consent:{registeredClientId}:{principalName}
~~~

Key cần encode an toàn như phần thiết kế cache key. Principal name phải dùng cùng canonical form mà persistence service dùng; không tự lower-case hoặc normalize nếu hệ thống phân biệt hoa/thường.

### 7.2. Invalidate khi save/remove

Khi `save(consent)` hoặc `remove(consent)` hoàn tất:

- Evict key của cặp RegisteredClient ID + principal name.
- Phát event cho các instance khác.
- Nếu có cache tổng hợp theo user hoặc theo client, evict thêm các view phụ thuộc.

Consent là dữ liệu quyết định user đã chấp thuận những authority nào. Nếu user rút consent, cache cũ có thể khiến authorization request tiếp theo không hiển thị consent screen hoặc tiếp tục cấp quyền đã bị rút.

### 7.3. Consent cache không thay authorization revocation

Rút consent và revoke các authorization/token đã cấp là hai nghiệp vụ khác nhau. Xóa consent ngăn việc tiếp tục dựa vào quyết định consent cũ trong các authorization flow tiếp theo. Những access token/refresh token đã phát hành có thể vẫn tồn tại tùy policy.

Nếu yêu cầu nghiệp vụ là “rút consent phải làm mọi token đã cấp mất hiệu lực”, quy trình phải:

1. Xóa/cập nhật consent.
2. Tìm authorization liên quan theo client và principal.
3. Invalidate token theo policy.
4. Ghi invalidation events cho authorization cache.
5. Chỉ thông báo hoàn tất sau khi đạt consistency guarantee đã cam kết.

Không giả định `OAuth2AuthorizationConsentService.remove()` tự động xóa mọi authorization liên quan.

## 8. Cache-aside, TTL và negative caching

### 8.1. Cache-aside

Cache-aside là mô hình đơn giản:

1. Đọc cache.
2. Nếu hit, trả kết quả.
3. Nếu miss, đọc durable store.
4. Ghi kết quả vào cache.
5. Khi ghi dữ liệu, cập nhật durable store rồi invalidation cache.

~~~mermaid
flowchart TD
    A["Protocol endpoint cần dữ liệu"] --> B["Đọc cache"]
    B --> C{"Cache hit?"}
    C -->|Có| D["Trả snapshot"]
    C -->|Không| E["Đọc database"]
    E --> F["Đưa snapshot vào cache"]
    F --> D
    G["save / remove"] --> H["Ghi durable store"]
    H --> I["Commit transaction"]
    I --> J["Evict local cache"]
    I --> K["Outbox event"]
    K --> L["Phát invalidation tới các node"]
~~~

Cache-aside dễ triển khai nhưng cần xử lý race giữa cache fill và invalidation, đặc biệt khi nhiều node đọc/ghi đồng thời.

### 8.2. TTL theo loại dữ liệu

Không có một TTL phù hợp cho mọi deployment. Hãy chọn TTL theo tần suất cập nhật và mức stale chấp nhận:

| Dữ liệu | TTL tham khảo để bắt đầu | Điều kiện cần cân nhắc |
| --- | --- | --- |
| RegisteredClient | Vài chục giây đến vài phút | Client secret rotation, disable, redirect/grant update và SLA invalidation. |
| Authorization by ID | Vài giây đến ngắn hơn token lifetime | Tần suất refresh/revoke và introspection consistency. |
| Token lookup alias | Ngắn, không vượt token expiry | Revocation, rotation, cache size và hit ratio. |
| Consent | Vài chục giây đến vài phút | SLA khi user rút consent hoặc admin sửa quyền. |
| Negative lookup | Không cache hoặc TTL rất ngắn | Client/token có thể vừa được tạo sau lần miss. |

Các con số chỉ là điểm bắt đầu cho benchmark. Production TTL phải xuất phát từ workload và yêu cầu bảo mật, không sao chép mặc định từ ví dụ.

### 8.3. Giới hạn TTL theo token expiry

Với token lookup alias, thời hạn cache không được vượt thời điểm token hết hạn. Nếu token expires tại thời điểm `exp`, cache entry phải hết hạn không muộn hơn thời điểm đó.

Tuy nhiên, TTL theo expiry không xử lý revoke. Token có thể bị invalidated trước expiry, do đó vẫn cần explicit invalidation hoặc authoritative check.

### 8.4. Negative caching

Negative cache lưu kết quả “không tìm thấy”. Nó có thể giảm database lookup khi attacker gửi nhiều token ngẫu nhiên, nhưng có rủi ro:

- Client vừa được đăng ký nhưng cache vẫn trả not found.
- Token vừa được cấp nhưng cache miss cũ vẫn còn.
- Cache key cho unknown token tăng không giới hạn và tạo memory pressure.
- Attacker có thể làm đầy cache bằng token ngẫu nhiên.

Nếu dùng negative cache:

- TTL rất ngắn.
- Giới hạn kích thước và eviction.
- Không lưu raw token.
- Invalidate negative key khi client/token tương ứng được tạo.
- Rate limit request không tìm thấy.

Với Authorization Server, thường nên tránh negative cache dài cho token và client lookup.

### 8.5. Chống cache stampede

Khi một key hết hạn, nhiều request có thể cùng miss và cùng query database. Cần cân nhắc:

- Atomic get-with-loader/single-flight theo cache key.
- TTL jitter để tránh nhiều key hết hạn cùng lúc.
- Giới hạn concurrency của loader.
- Timeout và bulkhead cho database lookup.
- Không giữ lock toàn cục trong lúc truy vấn database.

Không để cache loader gọi ngược lại chính decorator theo cách gây recursion hoặc deadlock.

## 9. Cơ chế vô hiệu hóa cache

### 9.1. Các sự kiện cần phát

| Sự kiện | Cache cần evict |
| --- | --- |
| RegisteredClient được tạo | Client ID và internal ID mới. |
| RegisteredClient được cập nhật | Cả alias cũ và mới; mọi view phụ thuộc client. |
| Client secret rotate | Client aliases trên mọi node; không tiếp tục dùng secret cũ. |
| Client bị disable/xóa | Client aliases; authorization/consent liên quan theo policy. |
| Authorization được tạo | ID và token aliases mới; xóa negative cache tương ứng nếu có. |
| Authorization được cập nhật | ID, token aliases cũ và mới, typed và ANY. |
| Authorization bị revoke | ID và mọi token aliases; introspection phải nhìn thấy invalidated state. |
| Authorization bị xóa | ID, mọi token aliases và reverse index. |
| Refresh token rotation | Alias refresh token cũ và mới; các alias authorization liên quan. |
| Consent được cấp/sửa | Composite key client + principal. |
| Consent bị rút | Composite key và các aggregate view phụ thuộc. |

### 9.2. Evict hay update cache?

Có hai lựa chọn:

- **Evict:** xóa cache entry; lần đọc kế tiếp load lại từ database. Đây là cách đơn giản, ít nguy cơ ghi nhầm snapshot.
- **Update:** thay cache bằng snapshot mới sau khi persistence commit. Cách này giảm cache miss nhưng yêu cầu object/version chính xác.

Với authorization và token status, evict thường an toàn hơn vì update có thể quên một token alias hoặc ghi snapshot trước khi transaction commit.

### 9.3. Evict phải xảy ra sau commit

Nếu evict trước khi transaction commit, một request khác có thể:

1. Nhìn thấy cache miss.
2. Đọc bản cũ từ database vì transaction ghi chưa commit.
3. Đưa bản cũ trở lại cache.
4. Transaction ban đầu commit nhưng không có lần evict thứ hai.

Kết quả là cache stale dù write transaction thành công.

Vì vậy, local cache eviction cần chạy sau commit. Nếu không có transaction, có thể evict ngay sau khi delegate save/remove thành công.

### 9.4. TransactionSynchronization afterCommit

Một helper có thể đăng ký callback:

~~~java
void afterCommit(Runnable invalidation) {
    if (!TransactionSynchronizationManager
            .isActualTransactionActive()) {
        invalidation.run();
        return;
    }

    if (!TransactionSynchronizationManager
            .isSynchronizationActive()) {
        throw new IllegalStateException(
            "Transaction synchronization is required");
    }

    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                invalidation.run();
            }
        });
}
~~~

Đây là ví dụ cho local process. Khi transaction commit thành công, callback mới evict cache. Nếu rollback, callback không chạy.

Nếu invalidation lỗi sau commit, database không thể rollback theo. Vì vậy, callback after-commit không thay thế cơ chế durable retry cho invalidation liên node.

## 10. Đồng bộ cache giữa nhiều Authorization Server instance

### 10.1. Vấn đề cache cục bộ

Giả sử instance A và B đều cache authorization `auth-100`. Instance A revoke access token và commit database. Nếu chỉ evict cache A, instance B có thể vẫn trả snapshot cũ và coi token active.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant DB as Database
    participant B as Instance B
    A->>DB: UPDATE authorization: token invalidated
    DB-->>A: Commit thành công
    A->>A: Evict local cache
    B->>B: Cache vẫn chứa snapshot cũ
    B->>B: Introspection đọc stale authorization
    Note over A,B: Cần invalidation event liên instance
~~~

### 10.2. Pub/Sub đơn thuần có thể mất event

Redis Pub/Sub hoặc một message broadcast không lưu bền có thể mất message khi consumer offline hoặc reconnect. Nếu một instance không nhận event revoke, stale cache có thể tồn tại đến khi TTL hết.

Pub/Sub có thể dùng để giảm độ trễ, nhưng không nên là cơ chế duy nhất bảo đảm invalidation cho dữ liệu bảo mật quan trọng.

### 10.3. Transactional outbox

Transactional outbox lưu invalidation event trong cùng database transaction với thay đổi dữ liệu:

1. Cập nhật authorization/client/consent.
2. Ghi một hàng vào bảng outbox trong cùng transaction.
3. Commit cả hai.
4. Publisher đọc các outbox row chưa gửi và phát event tới message broker.
5. Consumer trên từng instance evict cache.
6. Đánh dấu event đã được xử lý hoặc lưu consumer offset.

Ví dụ payload event:

~~~json
{
  "eventId": "evt-92f1",
  "entityType": "authorization",
  "entityId": "auth-100",
  "version": 42,
  "tenant": "tenant-a",
  "evictKeys": [
    "authorization:tenant-a:id:auth-100",
    "authorization:tenant-a:token:access_token:<hmac-digest>"
  ]
}
~~~

Payload chỉ chứa cache key/fingerprint, không chứa raw access token, refresh token, client secret hoặc claims nhạy cảm.

### 10.4. Event phải idempotent và có version

Broker có thể gửi event lặp hoặc khác thứ tự. Consumer nên:

- Dùng `eventId` để nhận diện event đã xử lý.
- Mang version tăng đơn điệu theo entity.
- Bỏ qua event cũ hơn version đã áp dụng.
- Evict là thao tác idempotent; nhận cùng event hai lần vẫn an toàn.
- Retry khi cache unavailable.

Nếu update version 43 đến trước version 42, consumer không được để event 42 ghi đè state/version mới. Với invalidation-only event, event cũ thường vẫn có thể evict an toàn, nhưng version vẫn hữu ích để chống cache refill stale.

### 10.5. Chống race khi cache loader đang chạy

Một race khác xảy ra khi node B đang load bản cũ từ database trong lúc node A commit thay đổi và event invalidation đến B:

1. B bắt đầu cache miss và đọc bản cũ.
2. A commit bản mới và phát event.
3. B nhận event và evict cache.
4. B hoàn tất query cũ và ghi snapshot cũ vào cache sau khi evict.

Một giải pháp là generation/version fencing:

~~~java
long generationBefore = generations.current(key);
OAuth2Authorization loaded = delegate.findById(id);

if (generationBefore == generations.current(key)) {
    cache.put(key, loaded);
}
return loaded;
~~~

Khi consumer nhận invalidation event, nó tăng generation cho key/entity. Nếu loader bắt đầu trước event nhưng kết thúc sau event, generation đã đổi nên loader không được ghi snapshot cũ vào cache.

Đây là pseudocode. Generation store phải được chia sẻ hoặc cập nhật nhất quán trong phạm vi cache node; với distributed cache có thể dùng version trong database/cache hoặc compare-and-set.

### 10.6. Khởi động lại và mất kết nối broker

Khi một instance khởi động lại:

- Bắt đầu với local cache rỗng hoặc namespace generation mới.
- Khôi phục consumer offset/replay event nếu broker hỗ trợ.
- Không nạp snapshot từ disk nếu không có cách xác minh version.
- Theo dõi khoảng thời gian consumer bị lag.

Khi node mất kết nối trong lúc đang chạy, cần clear cache hoặc đồng bộ event từ offset cuối trước khi tiếp tục phục vụ request nhạy cảm. Nếu không thể chứng minh cache đã bắt kịp, bypass cache cho các thao tác cần trạng thái mới nhất.

## 11. Consistency và yêu cầu revoke có hiệu lực ngay

### 11.1. Eventual consistency

Outbox + broker + local cache thường tạo eventual consistency. Sau khi database commit, các node sẽ nhận invalidation sau một khoảng trễ.

Đây là lựa chọn có thể chấp nhận nếu hệ thống xác định rõ:

- Thời gian stale tối đa.
- TTL backstop.
- Retry policy và alert khi event lag.
- Endpoint nào chấp nhận stale window.

Không gọi hệ thống là strongly consistent nếu invalidation được gửi bất đồng bộ.

### 11.2. Stronger consistency cho introspection và revocation

Nếu policy yêu cầu token bị revoke phải được introspection xem là inactive ngay khi revoke trả thành công, có thể:

- Bỏ qua cache authorization trên đường introspection/revocation.
- Dùng shared authoritative store cho trạng thái token active/invalidated.
- Thực hiện synchronous invalidation và chờ các node/cache liên quan xác nhận trước khi báo thành công.
- Dùng version/fencing check trên read path nhạy cảm.

Mỗi lựa chọn có trade-off giữa latency, availability và độ nhất quán. Nếu hệ thống không thể hoàn tất invalidation đồng bộ, không nên khẳng định revoke đã có hiệu lực toàn cụm.

### 11.3. JWT self-contained không bị thu hồi bởi cache Authorization Server

Resource Server có thể xác minh JWT self-contained bằng chữ ký và claims mà không gọi Authorization Server. Evict cache tại Authorization Server không tự làm JWT đã phát hành mất hiệu lực tại Resource Server.

Nếu cần thu hồi JWT trước `exp`, cần một cơ chế khác như:

- Token introspection thay cho xác minh local-only.
- Denylist/`jti` revocation lookup.
- Token TTL ngắn và policy chấp nhận thời gian tồn tại tối đa.
- Kiểm tra session/version tại Resource Server.

Không nhầm invalidation cache nội bộ của Authorization Server với việc thu hồi token trên toàn hệ sinh thái.

## 12. Spring Cache và cách tích hợp

### 12.1. Spring Cache là abstraction, không phải consistency protocol

Spring Framework cung cấp `@Cacheable`, `@CachePut`, `@CacheEvict` và `CacheManager`. Chúng giúp chuẩn hóa thao tác cache nhưng không tự giải quyết:

- Evict nhiều alias của một entity.
- Phát invalidation event tới node khác.
- Ghi outbox cùng transaction database.
- Chống race giữa cache loader và invalidation.
- Bảo đảm revoke có hiệu lực ngay.

Vì vậy, với core service Authorization Server, decorator tường minh thường dễ kiểm soát hơn việc chỉ gắn vài annotation.

### 12.2. Ví dụ decorator RegisteredClientRepository

~~~java
public final class CachingRegisteredClientRepository
        implements RegisteredClientRepository {

    private final RegisteredClientRepository delegate;
    private final Cache byId;
    private final Cache byClientId;

    public CachingRegisteredClientRepository(
            RegisteredClientRepository delegate,
            Cache byId,
            Cache byClientId) {
        this.delegate = delegate;
        this.byId = byId;
        this.byClientId = byClientId;
    }

    @Override
    public RegisteredClient findById(String id) {
        return byId.get(id, () -> {
            RegisteredClient client = delegate.findById(id);
            if (client != null) {
                byClientId.put(client.getClientId(), client);
            }
            return client;
        });
    }

    @Override
    public RegisteredClient findByClientId(String clientId) {
        return byClientId.get(clientId, () -> {
            RegisteredClient client =
                delegate.findByClientId(clientId);
            if (client != null) {
                byId.put(client.getId(), client);
            }
            return client;
        });
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        RegisteredClient previous =
            delegate.findById(registeredClient.getId());

        delegate.save(registeredClient);

        afterCommit(() -> {
            byId.evict(registeredClient.getId());
            byClientId.evict(registeredClient.getClientId());
            if (previous != null) {
                byClientId.evict(previous.getClientId());
            }
        });
    }
}
~~~

Đây là ví dụ minh họa cấu trúc decorator dùng Spring `Cache`. Trong production, cần bổ sung transaction boundary chung cho đọc bản cũ, save và outbox event; version/generation fencing; invalidation event liên instance; policy khi client bị xóa bằng extension operation riêng; và xử lý cache miss/loader exception.

Đoạn code đọc bản cũ để evict alias cũ. Nếu client ID bất biến theo policy ứng dụng, có thể đơn giản hóa; nếu cho phép thay đổi, phải bảo đảm đọc bản cũ trong cùng consistency boundary với update.

### 12.3. Cấu hình cache decorator

Có thể cấu hình local cache Caffeine qua Spring Cache:

~~~java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager(
        "registeredClientById",
        "registeredClientByClientId",
        "authorizationById",
        "authorizationByToken",
        "authorizationConsent");

    manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(100_000)
        .expireAfterWrite(Duration.ofMinutes(2))
        .recordStats());

    return manager;
}
~~~

TTL trong ví dụ chỉ để minh họa. Thực tế nên cấu hình TTL riêng cho từng cache region; authorization/token thường cần thời gian ngắn hơn RegisteredClient. Không dùng một TTL chung nếu các domain có mức độ nhạy cảm và tần suất cập nhật khác nhau.

### 12.4. Đăng ký decorator với AuthorizationServerConfigurer

Core service có thể được cấu hình qua `OAuth2AuthorizationServerConfigurer`:

~~~java
http.with(authorizationServerConfigurer, authorizationServer -> authorizationServer
    .registeredClientRepository(cachingRegisteredClientRepository)
    .authorizationService(cachingAuthorizationService)
    .authorizationConsentService(cachingConsentService)
);
~~~

Đảm bảo mọi protocol endpoint và custom provider dùng cùng các decorator. Không tạo một bean cache riêng cho một endpoint trong khi endpoint khác vẫn đọc trực tiếp delegate, vì như vậy có thể có hai đường đọc với consistency khác nhau.

### 12.5. Cẩn trọng với @CacheEvict

`@CacheEvict` mặc định evict sau khi method invocation thành công. Điều đó không tự bảo đảm thao tác diễn ra sau khi transaction database bên ngoài đã commit; thứ tự transaction/cache advisor có thể ảnh hưởng.

Nếu cần gắn cache với commit, dùng transaction-aware cache strategy hoặc đăng ký invalidation trong `TransactionSynchronization.afterCommit()`. Với invalidation liên node, ghi outbox trong cùng transaction; callback after-commit chỉ là tối ưu local.

Ngoài ra, Spring caching annotation dựa vào proxy. Self-invocation trong cùng object có thể bỏ qua interceptor. Hãy kiểm tra call path trước khi dựa vào annotation để bảo đảm cache được áp dụng.

## 13. Các lỗi thường gặp

### Lỗi 1: Chỉ cache RegisteredClient theo client ID

**Triệu chứng:** Client authentication nhanh hơn nhưng luồng tra cứu theo internal ID vẫn query database.

**Nguyên nhân:** Chỉ có một alias cache.

**Cách xử lý:** Cache cả `findById` và `findByClientId`, evict đồng thời hai alias.

### Lỗi 2: Evict cache trước database commit

**Triệu chứng:** Một request khác reload bản cũ và ghi trở lại cache.

**Nguyên nhân:** Invalidation chạy trước commit.

**Cách xử lý:** Evict sau commit và dùng version/generation fencing để chống cache-fill race.

### Lỗi 3: Chỉ evict node thực hiện revoke

**Triệu chứng:** Node khác tiếp tục trả introspection active cho token đã revoke.

**Nguyên nhân:** Local cache không được đồng bộ.

**Cách xử lý:** Dùng transactional outbox/durable event và theo dõi invalidation lag.

### Lỗi 4: Chỉ evict authorization ID

**Triệu chứng:** `findById` trả miss nhưng `findByToken` vẫn trả authorization cũ.

**Nguyên nhân:** Token alias cache còn tồn tại.

**Cách xử lý:** Evict mọi typed token key, ANY key và reverse index.

### Lỗi 5: Không xử lý refresh token rotation

**Triệu chứng:** Refresh token cũ vẫn tìm thấy trong cache hoặc token mới không được nhận diện.

**Nguyên nhân:** Chỉ evict token mới hoặc chỉ evict authorization ID.

**Cách xử lý:** Thu thập token aliases của snapshot cũ và mới; evict cả hai sau commit.

### Lỗi 6: Cache consent chỉ theo principal

**Triệu chứng:** Consent của client A bị trả cho client B.

**Nguyên nhân:** Cache key thiếu RegisteredClient ID.

**Cách xử lý:** Dùng composite key `(registeredClientId, principalName)`.

### Lỗi 7: Dùng TTL dài để thay invalidation

**Triệu chứng:** Client secret cũ hoặc token đã revoke vẫn có hiệu lực trong suốt TTL.

**Nguyên nhân:** Không có event invalidation.

**Cách xử lý:** TTL là backstop; vẫn cần invalidation theo write event.

### Lỗi 8: Dùng raw token làm cache key

**Triệu chứng:** Bearer token xuất hiện trong cache diagnostics hoặc key listing.

**Nguyên nhân:** Dùng credential làm key trực tiếp.

**Cách xử lý:** Dùng HMAC digest, không log key và giữ secret HMAC ngoài database.

### Lỗi 9: Pub/Sub mất event nhưng không phát hiện

**Triệu chứng:** Một node giữ cache cũ cho đến khi TTL hết hạn.

**Nguyên nhân:** Dựa vào message broadcast không bền vững.

**Cách xử lý:** Outbox, durable broker/offset, retry và clear cache khi node không thể replay event.

### Lỗi 10: Nhầm cache invalidation với JWT revocation

**Triệu chứng:** JWT đã phát hành vẫn được Resource Server chấp nhận sau khi cache Authorization Server đã xóa.

**Nguyên nhân:** Resource Server xác minh JWT local-only và không hỏi Authorization Server.

**Cách xử lý:** Dùng introspection, denylist/version check hoặc token TTL phù hợp.

### Lỗi 11: Cache miss bị ghi đè bởi loader cũ

**Triệu chứng:** Invalidation đã tới nhưng snapshot cũ xuất hiện lại.

**Nguyên nhân:** Loader bắt đầu trước commit, kết thúc sau invalidation.

**Cách xử lý:** Generation/version fencing và không put nếu generation đã thay đổi.

### Lỗi 12: Cache object mutable

**Triệu chứng:** Một luồng thay đổi attributes khiến các request khác nhìn thấy state không mong muốn.

**Nguyên nhân:** Chia sẻ mutable object giữa các request.

**Cách xử lý:** Cache immutable snapshot, không sửa trực tiếp object đã cache và tạo object mới khi cập nhật.

## 14. Kiểm thử cache và invalidation

### 14.1. Unit test cho cache decorator

Kiểm thử:

- `findById` gọi delegate một lần khi cache hit.
- `findByClientId` gọi delegate một lần khi cache hit.
- Cache một RegisteredClient theo ID đồng thời tạo alias theo client ID.
- Save evict cả alias cũ và mới.
- Cache consent theo đúng cặp client/principal.
- Authorization token alias phân biệt token type.
- Token type null có cache key riêng.
- Token miss không bị cache quá lâu.

### 14.2. Integration test transaction

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Save client trong transaction commit | Cache evict sau commit. |
| Save client rồi rollback | Cache cũ vẫn hợp lệ; không phát invalidation event commit. |
| Save authorization rồi rollback | Token alias cũ không bị xóa sai; không có event đã commit. |
| Revoke token và commit | Cache authorization/token alias bị evict. |
| Revoke token rồi rollback | Cache không bị cập nhật theo thay đổi chưa commit. |
| Save consent | Composite key bị evict sau commit. |
| Remove consent | Composite key bị evict sau commit. |
| Refresh token rotation | Token cũ và mới đều được xử lý đúng. |

### 14.3. Integration test nhiều node

Khởi chạy ít nhất hai instance A/B:

1. A và B cùng load một RegisteredClient/authorization vào cache.
2. A cập nhật client hoặc revoke token và commit.
3. Kiểm tra B nhận invalidation event.
4. Kiểm tra B reload bản mới từ database.
5. Gửi event trùng lặp và event sai thứ tự.
6. Ngắt B khỏi broker, thay đổi authorization trên A, sau đó reconnect B.
7. Xác minh B replay event hoặc clear cache trước khi phục vụ request.
8. Mô phỏng loader B đọc bản cũ trong khi A commit; kiểm tra generation fence không cho cache stale.

### 14.4. Kiểm thử yêu cầu revoke ngay

Nếu hệ thống cam kết revoke có hiệu lực ngay:

- Gửi introspection đồng thời với revoke.
- Xác định điểm tuyến tính hóa mà revoke được xem là hoàn tất.
- Đảm bảo request introspection sau điểm đó không nhận `active=true`.
- Nếu cache/broker không khả dụng, kiểm tra endpoint có fail closed hoặc bypass cache theo policy.
- Không chỉ test local single-node.

## 15. Observability và vận hành

### 15.1. Cache metrics

Theo dõi:

- Hit ratio và miss ratio theo cache region.
- Load latency và loader error.
- Eviction count và expiration count.
- Cache size/estimated size.
- Cache loader concurrency và stampede.
- Số event outbox chưa publish.
- Consumer lag và invalidation delay.
- Event retry/dead-letter count.
- Số lần generation/version mismatch ngăn cache put.

Không gắn raw client secret, token, principal name hoặc authorization ID nhạy cảm vào metric label. Dùng cache region, operation và tenant class/opaque tag có giới hạn cardinality.

### 15.2. Đặt SLO cho invalidation

Một hệ thống nhiều node nên định nghĩa:

- Thời gian tối đa từ DB commit đến khi node cuối cùng evict cache.
- Tỷ lệ invalidation event được xử lý đúng hạn.
- Thời gian tối đa broker consumer có thể bị lag.
- Hành vi khi node offline hoặc broker unavailable.
- Endpoint nào được phép eventual consistency.
- Endpoint nào phải đọc authoritative state.

TTL chỉ là backstop nếu event bị mất hoặc node không nhận được thông báo.

### 15.3. Runbook khi invalidation bị lỗi

Khi phát hiện invalidation lag vượt SLO:

1. Xác định entity type và cache region bị ảnh hưởng.
2. Kiểm tra outbox backlog, broker lag và consumer error.
3. Kiểm tra node nào chưa nhận event.
4. Bypass cache hoặc clear cache ở node không đồng bộ nếu policy yêu cầu.
5. Replay event từ offset an toàn.
6. Xác minh token/client/consent mới nhất trực tiếp từ durable store.
7. Chỉ khôi phục cache read path sau khi node đã bắt kịp.

Không xóa toàn bộ cache cluster theo phản xạ nếu chỉ một region lỗi; việc này có thể tạo database thundering herd.

## 16. Checklist production

| Hạng mục | Điều kiện cần xác nhận |
| --- | --- |
| Core services | Có decorator riêng cho RegisteredClient, authorization và consent? |
| Source of truth | Database/durable store vẫn là nguồn dữ liệu chính? |
| Client aliases | Cache theo cả internal ID và client ID? |
| Authorization aliases | Cache theo ID, token type và token digest? |
| Consent key | Có cả RegisteredClient ID và principal name? |
| Token privacy | Không dùng raw bearer token làm cache key hoặc event payload? |
| TTL | TTL riêng theo domain, token expiry và consistency SLA? |
| Negative cache | Có TTL ngắn, size bound và invalidation khi dữ liệu mới được tạo? |
| Write invalidation | Save/remove evict đúng alias cũ và mới? |
| Transaction | Evict local cache sau commit? |
| Outbox | Invalidation event được ghi cùng transaction với durable update? |
| Multi-node | Mọi instance nhận event hoặc replay khi reconnect? |
| Event ordering | Event idempotent và có version/generation? |
| Cache-fill race | Loader cũ không thể ghi đè snapshot mới? |
| Revocation | Introspection phản ánh revoke theo SLO đã cam kết? |
| Consent withdrawal | Policy xử lý authorization/token đã cấp được xác định rõ? |
| JWT | Phân biệt cache server-side với self-contained JWT validation ở Resource Server? |
| Secret | Client secret đã encode, không log và được evict khi rotate? |
| Observability | Có hit ratio, invalidation lag, outbox backlog và event retry metrics? |
| Recovery | Có runbook bypass/clear/replay cache khi node mất đồng bộ? |

## 17. Bài tập thực hành

Một Authorization Server chạy ba instance A, B và C. Cả ba dùng cùng PostgreSQL nhưng cache Caffeine cục bộ. Hệ thống có 200.000 RegisteredClient, 15 triệu authorization và 4 triệu consent. Introspection p95 cần dưới 30 ms. Một token có thể bị revoke bất kỳ lúc nào; yêu cầu nghiệp vụ nói introspection sau khi revoke trả thành công không được tiếp tục trả `active=true`.

1. Thiết kế cache namespace và key cho ba core service.
2. Chọn dữ liệu cache, TTL và negative cache policy cho từng service.
3. Viết decorator `RegisteredClientRepository` hỗ trợ lookup theo ID và client ID.
4. Thiết kế authorization token alias cho access token, refresh token, authorization code, ID Token và `tokenType=null`.
5. Thiết kế invalidation khi refresh token rotation, revoke và remove authorization.
6. Thiết kế composite key cho consent và luồng invalidation khi user rút consent.
7. Dùng transaction after-commit cho local eviction và outbox để phát event tới các node khác.
8. Giải quyết race khi instance B đang load snapshot cũ trong lúc instance A commit revoke.
9. Định nghĩa cách xử lý nếu B mất kết nối broker trong 30 giây.
10. Quyết định endpoint nào được cache eventual consistency và endpoint nào phải bypass cache để đạt revoke SLA.
11. Viết integration test hai node chứng minh token bị revoke không còn active sau điểm commit được cam kết.
12. Đo p50/p95/p99, DB QPS, cache hit ratio và invalidation lag trước/sau khi bật cache.

**Tiêu chí đạt:** Cache giảm tải database nhưng không làm thay đổi semantics của core service; client/authorization/consent được evict đúng key sau commit; event không chứa raw credential; node reconnect không tiếp tục phục vụ stale snapshot; revoke SLA được kiểm thử trên nhiều instance.

## 18. Tài liệu đối chiếu

- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClientRepository, OAuth2AuthorizationService, OAuth2AuthorizationConsentService, token lifecycle và các core model.
- [Spring Authorization Server 1.5.8 — RegisteredClientRepository Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/client/RegisteredClientRepository.html): findById, findByClientId, save và xử lý client secret.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationService Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationService.html): contract quản lý authorization.
- [Spring Authorization Server 1.5.8 — OAuth2Authorization Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html): token accessors, attributes và authorization identity.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationConsentService Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2AuthorizationConsentService.html): composite lookup, save và remove consent.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình core service qua OAuth2AuthorizationServerConfigurer.
- [Spring Authorization Server 1.5.8 — How-to: Implement core services with JPA](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-jpa.html): triển khai custom persistence service.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): @Cacheable, @CachePut, @CacheEvict và cache abstraction.
- [Spring Framework 6.2 — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): callback afterCommit.
