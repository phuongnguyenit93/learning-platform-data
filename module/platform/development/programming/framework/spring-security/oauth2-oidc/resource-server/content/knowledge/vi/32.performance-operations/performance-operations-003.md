# Cache JWKS, cache introspection và các mục tiêu khác nhau

## 1. Hai loại cache giải quyết hai bài toán khác nhau

Spring Security OAuth 2.0 Resource Server thường xác thực access token theo hai cách:

- **JWT validation**: Resource Server xác minh chữ ký JWT bằng public keys lấy từ JSON Web Key Set (JWKS), sau đó kiểm tra issuer, audience, thời gian và các claims theo policy.
- **Opaque token introspection**: Resource Server gửi token tới Authorization Server (AS), nhận kết quả introspection và tạo principal nếu token active.

Cả hai flow đều có thể dùng cache, nhưng dữ liệu được cache và mục tiêu vận hành khác nhau.

**JWKS cache** lưu tập public keys (JWK Set) để Resource Server không phải tải khóa từ AS cho mọi request. Nó chủ yếu tối ưu việc phân phối và làm mới trust material dùng để xác minh chữ ký.

**Introspection cache** lưu kết quả xác minh của từng access token, thường gồm active, scope, subject, audience, expiration và các attributes khác. Nó giảm số lần Resource Server gọi introspection endpoint, nhưng có thể làm chậm thời điểm Resource Server nhìn thấy việc token bị revoke hoặc quyền thay đổi.

| Khía cạnh | JWKS cache | Introspection cache |
|---|---|---|
| Cache object | Tập public JWK của issuer | Kết quả introspection của một token |
| Cache key | JWKS URI / issuer trust domain | Token fingerprint + issuer/resource context |
| Dữ liệu đại diện | Khóa xác minh chữ ký | Trạng thái và metadata của token |
| Tần suất truy cập | Khi decoder cần JWK set hoặc refresh | Có thể liên quan đến từng request/token |
| Mục tiêu chính | Giảm fetch key, hỗ trợ key rotation và availability | Giảm network round trip tới AS, giảm tải introspection |
| Ảnh hưởng revoke | Key removal có thể ảnh hưởng nhiều token cùng key | Positive result có thể còn được dùng sau khi token bị revoke |
| Đơn vị freshness | JWK set | Token-specific authentication result |
| Rủi ro chính | Dùng key cũ hoặc refresh không đúng lúc | Chấp nhận trạng thái active/claims đã stale |
| Dữ liệu nhạy cảm | Public keys, metadata trust | Principal attributes, scopes, subject, tenant data |
| Invalidation | Key rotation, issuer/JWKS changes | Token revoke, grant/permission changes, exp |

**Không dùng một cache thay cho cache còn lại.** Cache JWKS không làm giảm số lần introspection của opaque token. Cache introspection không cung cấp public key để xác minh chữ ký JWT.

## 2. Hai luồng xác thực nhìn từ góc độ cache

### JWT: cache khóa, vẫn xác minh từng token

~~~mermaid
flowchart TD
    A["HTTP Bearer JWT"] --> B["JWT Decoder"]
    B --> C{"JWK set còn dùng được trong cache?"}
    C -->|Có| D["Dùng public key phù hợp"]
    C -->|Không| E["Fetch / refresh trusted JWKS"]
    E --> D
    D --> F["Verify signature"]
    F --> G["Validate iss, aud, exp, nbf, profile"]
    G --> H["Authentication"]
~~~

Cache giữ public keys. Mỗi JWT request vẫn phải qua signature verification và validators. Một JWK set cached không có nghĩa mọi token ký bằng key trong set đều hợp lệ; token vẫn có thể sai chữ ký, hết hạn, sai audience hoặc sai issuer.

### Opaque: cache kết quả token-specific

~~~mermaid
flowchart TD
    A["HTTP Bearer opaque token"] --> B["ReactiveOpaqueTokenIntrospector"]
    B --> C{"Có entry còn hạn?"}
    C -->|Có| D["Dùng kết quả cached theo policy"]
    C -->|Không| E["Gọi trusted introspection endpoint"]
    E --> F{"active?"}
    F -->|true| G["Cache kết quả active có TTL giới hạn"]
    F -->|false| H["Từ chối; có thể cache negative ngắn hạn"]
    G --> I["Tạo authenticated principal"]
    D --> J["Kiểm tra freshness và expiration"]
    J --> I
~~~

Introspection cache giữ kết quả theo token. Nếu AS revoke token ngay sau khi Resource Server cache active=true, RS có thể tiếp tục chấp nhận token đến khi entry hết TTL hoặc được invalidated. Đây là trade-off cần được quyết định bằng revocation SLA.

## 3. JWKS là gì và vì sao Resource Server cần cache?

JWKS là JSON object chứa một tập JSON Web Keys. Với JWT ký bất đối xứng, Authorization Server công bố public key để Resource Server xác minh chữ ký.

Ví dụ:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.com
~~~

Response minh họa:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-signing-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "base64url-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

JWT JOSE header có thể chỉ ra key ID:

~~~json
{
  "alg": "RS256",
  "kid": "shop-signing-2026-02",
  "typ": "at+jwt"
}
~~~

Decoder dùng kid để tìm candidate key trong trusted JWK set, rồi verify chữ ký. kid là một key-selection hint trong phạm vi JWK set đã được tin cậy; nó không tự xác thực token.

### Nếu không cache JWKS

Giả sử một API nhận 5.000 request mỗi giây. Nếu mỗi request phải tải JWKS:
- AS phải phục vụ hàng nghìn HTTP calls không cần thiết.
- Latency của API phụ thuộc trực tiếp vào network tới AS.
- AS outage có thể làm toàn bộ API không xác minh được JWT.
- Nhiều Resource Server instances có thể tạo thundering herd.
- Chi phí network và TLS handshakes tăng.

Với cache, decoder thường tái sử dụng key set đã lấy và chỉ refresh theo cache policy, khi cần key chưa biết hoặc khi cache hết hạn theo implementation.

### Cache JWKS không cache kết quả authorization

Giả sử key K1 được cache:

~~~text
Request 1:
  JWT signature hợp lệ với K1
  iss/aud/exp/nbf hợp lệ
  -> Authentication success

Request 2:
  JWT dùng K1 nhưng exp đã qua
  -> Authentication failure

Request 3:
  JWT dùng K1 nhưng aud sai
  -> Authentication failure
~~~

Cùng public key có thể xác minh chữ ký của nhiều token khác nhau. Mỗi token vẫn phải được kiểm tra claims và policy riêng.

## 4. Cache JWKS có thể nằm ở đâu?

~~~text
Resource Server
   |
   +-- Nimbus/JWK source in-process cache
   |
   +-- HTTP client / proxy cache (nếu được phép)
   |
   +-- CDN or gateway cache (nếu được cấu hình an toàn)
   |
   +-- Authorization Server JWKS service
~~~

Không phải ứng dụng nào cũng dùng tất cả tầng này. Mỗi tầng có thể có TTL, stale behavior và invalidation khác nhau.

### In-memory cache của decoder

Spring Security JWT Resource Server thường dùng Nimbus JOSE + JWT để tải JWK set từ URI. Remote JWK retrieval có cache behavior do Nimbus/Spring Security version và cách cấu hình quyết định.

Không nên khẳng định một TTL mặc định giống nhau cho mọi phiên bản. Hãy kiểm tra dependency đang chạy, JWK source, HTTP client và cache configuration thực tế.

### HTTP cache / CDN

Nếu JWKS endpoint đặt sau reverse proxy/CDN, cần bảo đảm:
- Cache key bao gồm đúng host/path và các yếu tố ảnh hưởng response.
- Không cache metadata hoặc key set của issuer khác dưới cùng key.
- Cache-Control/max-age phù hợp key rotation SLA.
- TLS origin được xác minh.
- Invalidation/purge có quy trình.
- Không cho request tùy ý tạo JWKS URL hoặc cache namespace.
- Không áp dụng stale-if-error vượt policy đã phê duyệt.

Public key không phải secret, nhưng **nguồn public key là trust material**. Cache sai issuer hoặc sai endpoint vẫn có thể làm sai kết quả xác thực.

### Discovery metadata là một cache riêng

OIDC discovery metadata thường cung cấp issuer, jwks_uri và các endpoint khác. Metadata cache và JWKS cache là hai đối tượng khác nhau.

~~~text
Issuer metadata:
  issuer
  jwks_uri
  authorization_endpoint
  token_endpoint
       |
       v
JWKS:
  keys[]
       |
       v
JWT signature verification
~~~

Một test hoặc metric xác nhận JWKS cache hit không tự chứng minh metadata discovery cache hoạt động, và ngược lại.

## 5. JWKS TTL ảnh hưởng key rotation như thế nào?

Giả sử AS đang ký bằng K1 và muốn chuyển sang K2.

~~~text
Phase 1 - Publish:
  JWKS = { K1, K2 }
  AS vẫn ký token bằng K1

Phase 2 - Switch signer:
  JWKS = { K1, K2 }
  AS bắt đầu ký token mới bằng K2

Phase 3 - Overlap:
  JWKS = { K1, K2 }
  Tokens signed by K1 và K2 còn tồn tại

Phase 4 - Retire:
  JWKS = { K2 }
  K1 được loại sau khi token cũ hết hạn và overlap policy hoàn tất
~~~

Quy trình an toàn thường cần:
1. Publish public key mới trước khi AS bắt đầu ký bằng private key tương ứng.
2. Cho Resource Servers đủ thời gian refresh JWKS.
3. Chuyển signer sang key mới.
4. Giữ public key cũ trong khoảng overlap đủ dài cho các JWT còn hiệu lực.
5. Loại key cũ sau khi token ký bằng key đó hết hạn, cộng clock skew và cache/propagation margin theo policy.
6. Theo dõi unknown-kid, signature failure và JWKS refresh errors.

### Vì sao remove K1 khỏi JWKS không có hiệu lực tức thì?

Một Resource Server có thể đang giữ JWKS cached gồm K1. Nếu cache chưa refresh, decoder vẫn có thể tìm K1 và verify token cũ. Một CDN hoặc proxy cũng có thể đang giữ bản JWKS cũ.

Do đó thời điểm remove K1 trên AS không đồng nghĩa mọi RS lập tức quên K1.

### Unknown kid và refresh

Khi JWT có kid không nằm trong cached JWK set, implementation có thể cố refresh remote JWK set để tìm key mới. Behavior cụ thể phụ thuộc Nimbus/Spring Security version và JWK source.

Cần bảo vệ endpoint JWKS khỏi refresh storm:
- Giới hạn tần suất refresh khi gặp unknown kid.
- Coalesce concurrent refresh requests nếu implementation hỗ trợ.
- Dùng timeout và bounded retries.
- Không fetch URL từ jku/x5u chưa được trust.
- Không thử issuer khác chỉ vì kid không tồn tại.
- Theo dõi lượng unknown-kid requests để phát hiện abuse hoặc rotation lỗi.

Attacker có thể gửi nhiều JWT với kid ngẫu nhiên để kích hoạt refresh. Cache policy phải tính đến DoS, không chỉ latency.

## 6. Cache JWKS và availability khi AS outage

Khi AS/JWKS endpoint unavailable, kết quả phụ thuộc Resource Server có key phù hợp trong cache hay không và cache policy cho phép dùng cached key trong bao lâu.

| Trạng thái | Hành vi có thể có |
|---|---|
| Cached JWK còn dùng được, token dùng key đó | Decoder có thể xác minh bằng key cached mà không cần network |
| Cache miss, cần key mới, JWKS unavailable | Không đủ key để verify; request phải fail closed |
| Token có kid lạ, refresh thất bại | Không được tự tin token |
| JWKS endpoint trả malformed set | Không cập nhật trust material từ response lỗi |
| Cache quá hạn và implementation yêu cầu refresh | Behavior phụ thuộc cache/stale policy |
| Key compromise được thông báo nhưng cache chưa invalidated | Có thể còn cửa sổ sử dụng key cũ |

### Cached key khi outage là trade-off

Tiếp tục dùng public key đã được tải từ trusted issuer có thể giữ API hoạt động khi AS tạm thời down. Nhưng nếu key vừa bị compromise và bị remove khỏi JWKS, cache stale có thể kéo dài thời gian chấp nhận token ký bằng key đó.

Cần quyết định:
- Cache max age.
- Có cho phép stale-if-error hay không.
- Khi nào buộc refresh.
- Có cơ chế purge cache khẩn cấp không.
- Có thể revoke trust toàn bộ key ngay không.
- RTO/RPO và mức availability được chấp nhận.

Không tự động chấp nhận key chưa xác minh khi JWKS fetch lỗi. Nếu không có trusted key phù hợp, fail closed.

## 7. JWKS cache không phải user-token revocation cache

Giả sử K1 ký token của 10.000 users. Một user bị revoke:

~~~text
K1:
  User A token
  User B token
  User C token
  ...
  User 10,000 token
~~~

Xóa K1 khỏi JWKS sẽ ảnh hưởng mọi token dùng K1 sau khi các RS cập nhật cache. Nó không phải cách thu hồi chính xác token của riêng User A.

Ngược lại, giữ K1 trong JWKS không chứng minh mọi token của K1 còn active. JWT vẫn có thể:
- Hết hạn.
- Bị sai audience.
- Sai issuer.
- Chưa tới nbf.
- Có scope không phù hợp.
- Bị denylist theo jti.
- Không còn được phép theo domain policy.

**JWKS cache quản lý key availability/trust material; revocation là trạng thái của token/grant/user hoặc signing key.**

Nếu private key bị compromise, key-level emergency removal có thể cần thiết và phạm vi ảnh hưởng rộng. Nếu chỉ một token bị lộ, cân nhắc jti denylist, introspection, token version hoặc lifetime ngắn.

## 8. Opaque token introspection cache lưu gì?

RFC 7662 định nghĩa token introspection: Resource Server gửi token tới AS và nhận metadata về trạng thái token.

Request ví dụ:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic RESOURCE_SERVER_CREDENTIALS

token=opaque-access-token&token_type_hint=access_token
~~~

Response active:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iat": 1794729600,
  "exp": 1794730500
}
~~~

Introspection cache có thể giữ:
- active.
- issuer/subject/client_id.
- scope và authorities sau mapping.
- audience/resource binding.
- exp/iat/nbf nếu AS cung cấp.
- Các attributes được ứng dụng sử dụng.

Đây là dữ liệu **token-specific**. Hai token của cùng subject có thể khác scope, audience, client, lifetime hoặc trạng thái revoke. Không cache principal theo subject rồi dùng lại cho mọi token của user.

### Cache response hay cache principal?

Có thể cache:
- Raw/normalized introspection response.
- OAuth2AuthenticatedPrincipal đã được tạo.
- Một cấu trúc domain-specific chứa active, expiry, claims và authorities.

Dù chọn kiểu nào, phải giữ đúng contract và không dùng entry cho token, issuer, resource hoặc client context khác. Nếu authorities được mapping theo audience/client/route, cache key và cached value phải phản ánh các yếu tố đó.

## 9. Vì sao introspection cache có trade-off revocation?

Giả sử:

~~~text
10:00:00 AS trả active=true
10:00:01 RS cache positive result trong 60 giây
10:00:10 Admin revoke token tại AS
10:00:11 Request tiếp tục dùng positive cache
10:01:01 Entry hết hạn
10:01:02 RS gọi AS và nhận active=false
~~~

Token có thể được chấp nhận thêm gần 51 giây sau revoke trong ví dụ. Đó là **revocation visibility delay** do cache.

Không có TTL nào vừa loại bỏ hoàn toàn network call vừa đảm bảo mọi revoke được nhìn thấy tức thời nếu không có invalidation mechanism đồng bộ.

### Đặt TTL theo revoke SLA

Nếu tổ chức yêu cầu token bị revoke phải ngừng được chấp nhận trong tối đa 30 giây, positive cache TTL phải được chọn thấp hơn hoặc bằng ngân sách còn lại sau khi tính:
- AS replication/propagation delay.
- Cache invalidation delay.
- Request đang chạy/in-flight.
- Clock skew.
- CDN/proxy/cache layers nếu có.
- Failure/retry behavior.

Một mô hình đơn giản:

~~~text
Revocation visibility delay
  <= AS propagation delay
     + positive cache remaining TTL
     + invalidation delivery delay
     + bounded in-flight request duration
~~~

Đây là mô hình ước lượng cho thiết kế SLA, không phải bảo đảm tuyệt đối nếu hệ thống có stale cache không giới hạn hoặc partition mạng.

## 10. TTL positive introspection cache

Một positive cache entry thường được giới hạn bởi:
- TTL tối đa do Resource Server đặt.
- Thời gian còn lại tới exp nếu introspection response cung cấp exp.
- Revocation SLA.
- Policy về thay đổi scope/permission.
- Token audience/resource context.

Công thức tham khảo:

~~~text
positiveTTL =
  min(configuredMaxPositiveTTL,
      exp - now,
      remainingRevocationFreshnessBudget)
~~~

Nếu exp không có trong response, không thể suy ra lifetime vô hạn. Phải dùng một max positive TTL ngắn theo contract hoặc không cache positive result nếu yêu cầu freshness không cho phép.

### Không dùng TTL vượt exp

Nếu token còn 10 giây tới exp nhưng cache TTL là 60 giây, một cache hit ở giây thứ 30 không được trả principal active. Entry cần hết hạn tại exp hoặc code phải kiểm tra exp trên mỗi cache hit.

Nên tính TTL từ đồng hồ monotonic cho duration trong cache nếu thư viện hỗ trợ, đồng thời giữ absolute expiry để kiểm tra token validity. Không phụ thuộc vào timezone local.

### Cache active=true không thay timestamp validation

Nếu AS trả active=true nhưng response có exp đã qua do lỗi contract, clock mismatch hoặc cache stale, Resource Server phải áp dụng acceptance policy của mình. Không coi positive cache entry là miễn trừ hết hạn.

## 11. Negative introspection cache

AS có thể trả:

~~~json
{
  "active": false
}
~~~

Có thể cache negative result trong một khoảng ngắn để giảm việc liên tục introspect một token đã bị từ chối.

Lợi ích:
- Giảm tải AS với token invalid lặp lại.
- Hạn chế repeated network round trips.
- Có thể giảm abuse từ một credential đã bị revoke.

Rủi ro:
- Cache pollution nếu attacker gửi vô số token ngẫu nhiên.
- Token được kích hoạt lại theo policy đặc biệt có thể tiếp tục bị từ chối trong TTL.
- Token rotation/new grant không được phản ánh ngay nếu cache key không đúng.
- Negative entry dùng chung sai issuer/resource context có thể từ chối nhầm.

Chính sách:
- TTL negative thường ngắn hơn positive.
- Giới hạn cache size và eviction.
- Rate-limit các nguồn gửi token ngẫu nhiên.
- Không cache mọi upstream failure thành active=false.
- Phân biệt AS trả active=false với timeout, HTTP 5xx, TLS failure và invalid_client.

### Không biến dependency error thành negative cache

Những lỗi sau không phải câu trả lời token inactive:
- Introspection endpoint timeout.
- HTTP 500/503.
- DNS/TLS failure.
- HTTP 401 invalid_client.
- HTTP 403 Resource Server không được phép introspect.
- Response malformed.

Không cache chúng như active=false. Cũng không cache chúng như active=true. Giữ failure semantics, fail closed và áp dụng retry/circuit breaker theo policy.

## 12. Cache key cho introspection phải cô lập trust context

Không dùng subject làm cache key:

~~~text
Cache key = user-42
~~~

Vì cùng user có thể có:
- Access token read-only.
- Access token read/write.
- Token audience khác.
- Token từ issuer khác.
- Client khác.
- Tenant context khác.
- Token cũ đã revoke và token mới active.

Không nên lưu raw Bearer token làm key trong logs hoặc hệ thống cache nếu có thể tránh. Một lựa chọn là **keyed HMAC fingerprint** của token.

~~~text
cacheKey =
  HMAC(cacheKeySecret,
       issuerId || introspectionEndpointId || resourceId || token)
~~~

Các thành phần chính xác tùy contract:
- Issuer/AS identity.
- Introspection endpoint.
- Resource/audience context.
- Token type hint.
- Client/tenant policy nếu ảnh hưởng response.

HMAC key phải được quản lý an toàn và rotation có kế hoạch. Hash không keyed vẫn có thể dễ bị dò nếu token entropy thấp; access tokens cần đủ entropy và cache keys không được log.

### Cache namespace cho nhiều issuer

Hai AS có thể tình cờ phát cùng chuỗi token hoặc dùng cùng subject. Cache key phải phân biệt issuer/endpoint. Không dùng một global map từ token string tới principal cho mọi trust domain.

## 13. Cache introspection trong Spring Security WebFlux

Reactive contract của introspector:

~~~java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
~~~

Spring Security cung cấp introspector thực hiện HTTP introspection. Cache có thể được triển khai bằng một decorator hoặc thành phần caching riêng.

~~~text
OpaqueTokenReactiveAuthenticationManager
                 |
                 v
       CachingReactiveIntrospector
                 |
          +------+------+
          |             |
       Cache hit      Cache miss
          |             |
          v             v
   Principal/result   Delegate introspector
          |             |
          |             v
          |         Authorization Server
          |             |
          +-------------+
                 |
                 v
      OAuth2AuthenticatedPrincipal
~~~

Decorator phải:
- Trả đúng principal đã xác thực.
- Không đổi authorities/attributes sai contract.
- Tính TTL không vượt exp và freshness policy.
- Phân biệt active=false với dependency errors.
- Giới hạn kích thước cache.
- Không block event loop.
- Không để một request chưa hoàn tất tạo hàng nghìn concurrent introspection calls.
- Không dùng cached result từ issuer/resource khác.

### Không mặc định Spring Boot tự cache introspection

~~~yaml
spring:
  cache:
    type: caffeine
~~~

Cấu hình trên không tự động chứng minh ReactiveOpaqueTokenIntrospector đã được bọc bằng cache. Spring Cache abstraction chỉ có tác dụng khi có code/bean thực sự sử dụng nó. Cần cấu hình decorator, cache manager hoặc implementation có chủ đích.

Tương tự, không phải cứ khai Caffeine dependency là JWKS cache của Nimbus tự chuyển sang Caffeine. Kiểm tra JWK source và integration thực tế.

## 14. Minh họa decorator: cache có giới hạn và TTL theo token

Một triển khai production cần chọn thư viện cache và semantics phù hợp. Đoạn dưới là **pseudo-code về thuật toán**, không phải một class copy-paste hoàn chỉnh:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    String key = hmacFingerprint(
            issuerId, introspectionEndpointId, resourceId, token);

    return cache.getOrLoad(key, () ->
            delegate.introspect(token)
                    .map(principal -> {
                        Instant expiresAt = readExpiration(principal);

                        Duration ttl = calculatePositiveTtl(
                                clock.instant(),
                                expiresAt,
                                maxPositiveTtl,
                                revocationBudget);

                        return CacheEntry.positive(principal, ttl);
                    })
                    .onErrorMap(this::preserveDependencyFailure));
}
~~~

Các thành phần giả định:
- Cache có bounded size và expiry per entry.
- getOrLoad coalesce concurrent misses cho cùng key.
- Cache chỉ ghi khi delegate trả kết quả introspection hợp lệ.
- Hàm tính TTL trả giá trị dương nhưng không vượt exp hoặc SLA.
- Dependency errors không biến thành positive/negative entries.
- Error path được giữ nguyên theo authentication contract.

Nếu response active=false, có thể tạo negative entry với TTL ngắn theo policy. Không nên dùng chung TTL với positive result nếu revoke/freshness requirements khác nhau.

### Reactive implementation phải không blocking

Tránh:

~~~java
OAuth2AuthenticatedPrincipal principal =
        delegate.introspect(token).block();
~~~

Blocking trong WebFlux request pipeline có thể chặn event loop. Dùng Mono composition và cache library hỗ trợ asynchronous loading hoặc một design reactive phù hợp.

Không dùng một ConcurrentHashMap<String, Mono<...>> không giới hạn trong production mà không có eviction, TTL, in-flight cleanup và bảo vệ concurrent misses.

## 15. Spring Cache, Caffeine và Redis: chọn theo deployment

| Lựa chọn | Ưu điểm | Rủi ro/cần cân nhắc |
|---|---|---|
| In-memory bounded cache | Đơn giản, latency thấp, không thêm network dependency | Mỗi instance có cache riêng, restart mất cache |
| Caffeine | Expiration, eviction, high-performance local cache | Cần integration đúng; không tự wrap introspector/JWKS |
| Redis/distributed cache | Chia sẻ entry giữa nhiều RS instances, invalidation tập trung | Thêm network/availability/security dependency |
| CDN/proxy cho JWKS | Giảm tải AS và hỗ trợ edge distribution | Phải giữ issuer/path/cache headers và rotation semantics |
| No introspection cache | Freshness gần AS theo mỗi request | Latency và AS load cao hơn |
| Short-lived positive cache | Giảm calls nhưng giới hạn stale window | Revocation vẫn trễ tối đa theo TTL/invalidation |

### In-memory cache

Phù hợp khi số instances nhỏ, token volume vừa phải và revocation SLA cho phép cache local.

Nếu có 20 pods, mỗi pod có cache riêng, cùng token có thể:
- Pod A đã nhận active=false.
- Pod B vẫn giữ active=true.
- Pod C vừa restart và gọi AS.

Đây là consistency model cần hiểu, không nhất thiết là bug.

### Distributed cache

Redis có thể giúp chia sẻ kết quả và invalidate tập trung. Tuy nhiên:
- Cache outage có thể ảnh hưởng authentication.
- Network latency của Redis trở thành một phần request latency.
- Cache data chứa subject/scope/tenant metadata cần ACL, TLS, encryption và retention.
- Key namespace phải cô lập issuer/resource.
- Event invalidation có thể mất hoặc trễ; TTL vẫn là safety bound.
- Không được dùng stale positive entry vô thời hạn khi Redis/AS outage.

### Khi cache là dependency bắt buộc

Nếu cache backend down:
- Có thể bypass cache và gọi AS trực tiếp nếu AS còn hoạt động và capacity cho phép.
- Có thể fail closed nếu không thể kiểm tra trạng thái.
- Không tự động dùng stale positive results ngoài freshness budget.
- Không chuyển sang issuer/introspection endpoint khác chưa được trust.

Bypass cache để gọi cùng AS khác với chuyển trust authority.

## 16. Cache stampede, concurrency và backpressure

Khi positive entry hết TTL, nhiều request cùng token có thể đồng thời gọi introspection:

~~~text
Cache entry expires
       |
       +-- Request A -> AS
       +-- Request B -> AS
       +-- Request C -> AS
       +-- ...
       +-- Request N -> AS
~~~

Đây là cache stampede. Cách giảm:
- Single-flight loading/coalescing cho cùng key.
- TTL jitter để tránh hàng loạt entries hết hạn cùng lúc.
- Bounded concurrent introspection requests.
- Per-AS connection pool và timeout.
- Rate limit theo client/route nếu cần.
- Circuit breaker để bảo vệ dependency.
- Backoff có giới hạn cho transient errors.

### TTL jitter phải giữ SLA

Nếu positive cache TTL tối đa là 30 giây theo revoke SLA, không thêm jitter khiến TTL thành 45 giây. Jitter nên phân tán thời điểm refresh nhưng không vượt freshness ceiling.

### Circuit breaker không được mở đường fail-open

Khi introspection AS lỗi liên tục, circuit breaker có thể ngăn gọi network dồn dập. Nhưng circuit open không chứng minh token active. Protected request vẫn phải fail closed hoặc theo một explicit, bounded stale policy đã được phê duyệt.

## 17. Cache invalidation khi revoke hoặc đổi quyền

Có thể invalidation theo các sự kiện:
- Token revoked.
- Refresh token family revoked.
- User disabled.
- Client disabled.
- Consent/grant revoked.
- Scope/role assignment changed.
- Tenant membership removed.
- Issuer key compromised.

### Token-specific invalidation

Nếu event có token ID hoặc jti, cache entry tương ứng có thể bị xóa. Với opaque token, AS và RS cần một cách liên hệ token event với cache key mà không phát tán raw token.

### Subject/grant-wide invalidation

Nếu user bị khóa hoặc toàn bộ grant bị revoke, có thể invalidation nhiều entries theo:
- Issuer + subject.
- Issuer + client ID.
- Grant/session identifier.
- Tenant/user version.

Một index secondary hoặc version namespace có thể giúp invalidation. Cần tránh xóa nhầm entries của issuer khác có cùng subject.

### Event delivery không thay TTL

Pub/sub event có thể mất do network partition, consumer restart hoặc message retention. Vì vậy:
- TTL vẫn phải đáp ứng maximum stale window.
- Có retry/dead-letter/replay.
- Metrics theo dõi event lag.
- Invalidation handler idempotent.
- Có reconciliation nếu cần.
- Không coi event đã publish là mọi RS đã xử lý.

## 18. JWKS cache và introspection cache không đồng nghĩa cache revocation

| Flow | Cache | Điều được cache | Điều không được bảo đảm |
|---|---|---|---|
| JWT | JWKS cache | Public signing keys | Revocation của một token cụ thể |
| JWT | Denylist/status cache bổ sung | jti/token/user status | Key set freshness |
| Opaque | Introspection cache | Token active và attributes | Revoke được nhìn thấy tức thời |
| Opaque | JWKS cache | Không liên quan đến introspection | Không làm opaque token nhanh hơn |

Một hệ thống có thể cần cả:
- JWKS cache để verify JWT.
- Denylist hoặc token-version cache để phát hiện revoke.
- Introspection cache để giảm AS calls cho opaque tokens.
- OIDC metadata cache để giảm discovery requests.

Mỗi cache cần owner, TTL, key namespace, invalidation và metric riêng.

## 19. Token expiry phải được kiểm tra trên cache hit

Một lỗi thường gặp:

~~~text
10:00 Cache stores active=true, exp=10:01.
10:00:50 Cache hit.
10:01:10 Cache hit again due cache TTL=60s.
10:01:10 RS returns cached active=true without checking exp.
~~~

Token đã hết hạn nhưng cache vẫn còn. Cách đúng:
- Positive entry TTL không vượt thời gian còn lại đến exp.
- Kiểm tra absolute exp trên mỗi cache hit nếu entry lưu exp.
- Áp dụng clock skew policy nhất quán.
- Nếu exp thiếu, dùng max TTL được policy phê duyệt hoặc không cache.
- Không coi cache TTL là thay thế cho token lifetime validation.

Với JWT, decoder vẫn phải kiểm tra exp/nbf ở mỗi request, kể cả khi JWK set được cache.

## 20. Cache key rotation và issuer isolation

### JWKS cache key

Cache JWK set theo **trusted JWKS endpoint/issuer namespace**. Không cache bằng kid một mình:

~~~text
Bad:
  cache["key-2026"] = publicKey

Better:
  cache[(issuerA, jwksUriA)] = JWKSet
  cache[(issuerB, jwksUriB)] = JWKSet
~~~

kid chỉ có ý nghĩa trong JWK set tương ứng. Hai issuer có thể dùng cùng kid nhưng public key khác nhau.

### Introspection cache key

Cache theo token fingerprint và trust/resource context:

~~~text
(issuerId, introspectionEndpointId, audience/resourceId, tokenFingerprint)
~~~

Không dùng:
- subject một mình.
- client_id một mình.
- raw token làm metric label.
- unverified iss làm namespace tùy ý.
- token fingerprint mà không phân biệt endpoint/resource khi response phụ thuộc các yếu tố đó.

## 21. Security của cached principal và JWK set

JWKS chứa public key nhưng vẫn là trust material. Nếu cache bị thay thế bởi dữ liệu attacker kiểm soát, Resource Server có thể verify token theo key sai. Bảo vệ:
- TLS và hostname validation.
- Trust issuer/JWKS URI từ configuration/metadata được xác minh.
- Không tin jku/x5u tùy ý.
- Cache integrity và access control nếu dùng shared cache.
- Không dùng cache namespace do request cung cấp.
- Audit key source và refresh failures.

Introspection result có thể chứa subject/user ID, email/username, tenant ID, scopes/roles, client ID và audience. Cache data này cần:
- Encryption in transit/at rest khi phù hợp.
- ACL chỉ cho Resource Server được phép.
- TTL và retention ngắn.
- Không ghi principal object hoặc raw claims vào logs.
- Key rotation và namespace isolation.
- Không chia sẻ cache giữa environments/dev/prod hoặc issuers khác nhau.

## 22. Observability: đo hai cache riêng biệt

Không dùng một metric auth_cache_hit chung mà không biết cache nào. Nên tách:

~~~text
jwks_cache_hit_total
jwks_cache_miss_total
jwks_refresh_total
jwks_refresh_failure_total
jwks_unknown_kid_total
jwks_fetch_latency_seconds

introspection_cache_hit_total
introspection_cache_miss_total
introspection_positive_hit_total
introspection_negative_hit_total
introspection_upstream_request_total
introspection_upstream_failure_total
introspection_latency_seconds
introspection_entry_expired_total
introspection_invalidation_total
~~~

Các labels nên có cardinality thấp:
- Configured issuer ID.
- Resource Server ID.
- Cache outcome.
- Failure category.
- Environment/region nếu cần.

Không dùng raw token, raw sub, kid không giới hạn hoặc unverified issuer URL làm metric label.

### Chỉ số quan trọng

**JWKS**
- Cache hit ratio.
- Refresh latency/failure rate.
- Unknown-kid rate.
- Age của JWK set hiện tại.
- Key rotation overlap.
- Signature failures theo issuer/key source đã cấu hình.

**Introspection**
- Positive/negative hit ratio.
- AS request rate.
- AS latency/error rate.
- Age của positive entry.
- TTL remaining khi revoke event được xử lý.
- Invalidation event lag.
- Số lần stale result bị từ chối.

Hit ratio cao chỉ nói về hiệu năng. Freshness và correctness mới quyết định an toàn.

## 23. Thiết kế mục tiêu vận hành cho hai cache

| Mục tiêu | JWKS cache | Introspection cache |
|---|---|---|
| Giảm latency | Tránh fetch public key thường xuyên | Tránh gọi AS trên cache hit |
| Giảm tải AS | Giảm GET JWKS | Giảm POST introspection |
| Availability | Có thể verify bằng trusted cached keys khi AS tạm down theo policy | Có thể dùng cached active result trong freshness window nếu policy cho phép |
| Key rotation | Cần refresh kịp thời để thấy key mới/loại key cũ | Không xử lý key rotation |
| Individual token revoke | Không giải quyết trực tiếp | Có thể chậm nhìn thấy revoke theo positive TTL |
| Permission changes | Không tự cập nhật token claims | Có thể cache claims cũ; cần invalidation/freshness |
| Security boundary | Đúng issuer/JWKS source | Đúng issuer, endpoint, resource và token |
| Failure policy | Không có key trusted thì fail closed | Không có positive introspection mới/cached còn hợp lệ thì fail closed |
| Primary SLA | Key freshness / rotation propagation | Revocation visibility / active-result freshness |

### Đừng tối ưu một mục tiêu bằng cách phá mục tiêu kia

- JWKS TTL quá dài giảm network calls nhưng tăng thời gian dùng key cũ.
- JWKS TTL quá ngắn tăng refresh load và phụ thuộc AS.
- Introspection TTL quá dài giảm latency nhưng tăng revoke delay.
- Introspection TTL quá ngắn tăng AS load và request latency.
- Không có cache có thể đạt freshness cao hơn nhưng tăng dependency pressure.
- Stale-if-error có thể tăng availability nhưng làm stale credential tiếp tục được chấp nhận.

Chọn TTL từ SLO/SLA cụ thể, không sao chép một con số từ blog hoặc môi trường khác.

## 24. Ví dụ policy cho hệ thống có JWT và opaque tokens

Một API có hai loại Resource Server route:

~~~text
/api/jwt/**
  JWT issuer Shop
  JWKS cache max age = 5 minutes (illustrative policy)
  Rotation overlap = 15 minutes (illustrative policy)
  exp <= 10 minutes
  Emergency key purge procedure

/api/opaque/**
  Introspection AS Partner
  Positive cache max TTL = 10 seconds (illustrative policy)
  Negative cache TTL = 2 seconds (illustrative policy)
  Positive TTL also bounded by exp
  Revoke visibility target <= 15 seconds
~~~

Các con số chỉ minh họa cách viết policy; không phải Spring Security defaults hoặc khuyến nghị phổ quát. Chúng cần được kiểm chứng với:
- AS propagation delay.
- Clock skew.
- Network/replica topology.
- Maximum token lifetime.
- Key rotation process.
- Business risk của stale authorization.
- Load test và failure test.

Với opaque cache positive TTL 10 giây nhưng AS replication delay 20 giây, mục tiêu revoke 15 giây không đạt được. Phải tính toàn bộ pipeline, không chỉ TTL local cache.

## 25. Test JWKS cache

| Test | Setup | Kỳ vọng |
|---|---|---|
| JWKS first load | Cache rỗng, token ký bằng trusted key | Có GET JWKS, token verify |
| Cache hit | Gửi token tiếp theo dùng cùng set | Không cần fetch lại trong cache freshness window |
| New kid | JWKS được cập nhật có key mới | Decoder refresh theo behavior của version |
| Unknown kid | Token dùng kid không có trong set | Reject; refresh có giới hạn |
| Wrong signature | kid đúng nhưng token ký bằng private key khác | Reject |
| JWKS malformed | Response không phải valid JWK Set | Không cập nhật trusted cache |
| JWKS timeout | Không có cached key phù hợp | Fail closed |
| Cached key + outage | Key còn cached theo policy | Behavior đúng stale/cache policy |
| Remove old key | JWKS bỏ key cũ sau overlap | Old token bị reject sau refresh/cache expiry |
| Two issuers same kid | Cùng kid nhưng key khác | Cache namespace không trộn issuer |
| Refresh storm | Nhiều request cùng unknown kid | Bounded/coalesced refresh theo implementation |

Không assert mỗi request luôn đúng một JWKS call. Cache và refresh policy có thể làm số request khác nhau. Assert behavior theo cache contract và version thực tế.

## 26. Test introspection cache

| Test | Setup | Kỳ vọng |
|---|---|---|
| First positive | Cache miss, AS active=true | Một introspection call, cache positive |
| Positive hit | Cùng token trong TTL | Không gọi AS lại, principal đúng |
| Exp boundary | Cache entry còn nhưng exp đã qua | Reject |
| TTL boundary | Entry hết TTL | Introspect lại |
| Revoke after positive | AS đổi active=true thành false | Stale window đúng TTL/invalidation SLA |
| Explicit invalidation | Revoke event đến cache | Entry bị xóa, request tiếp theo introspect |
| Negative result | AS active=false | Reject; negative cache TTL ngắn nếu bật |
| Negative expiry | Token state thay đổi theo test policy | Sau TTL gọi AS lại |
| Upstream 500/timeout | Cache miss | Fail closed; không cache active |
| invalid_client | AS trả 401 cho RS credentials | Phân loại dependency/config error |
| Different audience | Same token under different resource context | Không dùng nhầm cached result |
| Different issuer | Same token string in two issuer domains | Cache entries độc lập |
| Concurrent miss | Nhiều requests cùng token | Single-flight/bounded concurrency |
| Cache backend down | Redis/local cache failure | Policy bypass/fail closed rõ ràng |
| User role change | Claims stale trong positive entry | Invalidation/freshness theo contract |

### Đo revocation delay thực tế

1. Request đầu tiên tạo positive cache entry.
2. Revoke token tại AS.
3. Gửi request lặp lại theo thời gian.
4. Ghi thời điểm lần đầu RS từ chối.
5. So sánh với TTL, propagation và invalidation event lag.
6. Chạy nhiều RS instances để phát hiện cache inconsistency.

Kết quả đo được mới chứng minh revocation SLA trong topology thực tế.

## 27. Failure policy cho từng cache

| Lỗi | JWKS cache | Introspection cache |
|---|---|---|
| Cache miss, source hoạt động | Fetch JWK set | Gọi AS |
| Cache miss, source unavailable | Không verify nếu không có trusted key | Không có kết quả active; fail closed |
| Cache backend unavailable | Có thể dùng in-process trusted key cache nếu policy cho phép | Có thể bypass tới cùng AS nếu capacity cho phép, hoặc fail closed |
| Cached entry hết hạn | Refresh theo policy | Introspect lại |
| Source trả malformed response | Không thay trusted JWK set bằng response lỗi | Không tạo principal |
| Source trả explicit negative | Không áp dụng cho JWK set | active=false, reject |
| Source timeout | Không coi là key mới hợp lệ | Không coi là active=false hay active=true |
| Emergency invalidation | Purge compromised key set/entry | Xóa token/grant/subject entries |
| Unknown issuer/endpoint | Không fetch arbitrary JWKS | Không gửi token đến arbitrary AS |

### Stale positive result là quyết định bảo mật

Nếu AS unavailable và introspection cache vẫn còn positive entry:
- Nếu entry còn trong TTL/freshness budget, policy có thể cho dùng.
- Nếu entry quá hạn, không được coi nó là kết quả mới.
- Nếu đã có revoke event, entry cần bị invalidated.
- Nếu emergency revoke/compromise, stale-positive exception có thể bị vô hiệu ngay.

Không tự mở rộng TTL khi AS outage để giữ availability nếu điều đó vi phạm revocation SLA.

## 28. Những hiểu nhầm phổ biến

**“Bật Spring Cache là tự cache JWKS.”**

Không nhất thiết. JWKS retrieval/cache thuộc JWK source/Nimbus và cấu hình liên quan. Spring Cache abstraction không tự thay thế JWK source.

**“Bật Caffeine là introspection tự được cache.”**

Không. Cần một caching decorator/bean hoặc integration cụ thể quanh ReactiveOpaqueTokenIntrospector.

**“JWKS cache hit có nghĩa JWT đã authenticated.”**

Không. Cache hit chỉ cung cấp key candidate. Decoder vẫn phải verify signature và validate issuer, audience, exp, nbf, token purpose.

**“Introspection cache hit nghĩa token vẫn active ở AS ngay lúc này.”**

Không. Nó chỉ nghĩa Resource Server có một kết quả active trước đó còn trong local freshness policy. Token có thể đã bị revoke sau thời điểm cache.

**“JWKS cache TTL và introspection TTL nên bằng nhau.”**

Không có lý do mặc định. Hai cache có dữ liệu, invalidation, security objectives và SLA khác nhau.

**“Xóa key cũ khỏi JWKS sẽ revoke một token.”**

Không. Key có thể được dùng bởi nhiều tokens; cache cũng có thể giữ key cũ. Token-specific revoke cần mechanism phù hợp.

**“Cache timeout response như active=false để giảm calls.”**

Không. Timeout không phải câu trả lời từ AS rằng token inactive. Phải giữ failure semantics.

**“Nếu cache backend down, dùng stale principal vô hạn.”**

Không. Stale-positive behavior phải có bounded freshness budget và được phê duyệt.

## 29. Checklist thiết kế

Trước khi bật JWKS cache:
1. Issuer/JWKS URI đến từ trust configuration nào?
2. JWK cache TTL/refresh policy của version đang chạy là gì?
3. Key rotation overlap bao lâu?
4. Unknown kid có thể gây refresh storm không?
5. AS outage với cached key và cache miss được xử lý ra sao?
6. Emergency key purge mất bao lâu tới mọi RS instances?
7. CDN/proxy có giữ stale key set không?
8. Metrics có đo cache age, refresh errors và unknown kid không?

Trước khi bật introspection cache:
1. Revocation visibility SLA là bao nhiêu?
2. Positive TTL bị giới hạn bởi exp thế nào?
3. Có exp trong response không; nếu không thì max TTL nào được phép?
4. Negative TTL bao lâu và cache pollution được kiểm soát ra sao?
5. Cache key có issuer/endpoint/resource context không?
6. Có dùng keyed fingerprint thay raw token không?
7. Upstream errors có bị loại khỏi cache không?
8. Revoke event invalidation có đảm bảo delivery/replay không?
9. Cache backend outage có bypass tới cùng AS hay fail closed?
10. Cache principal attributes được bảo vệ ra sao?

Trước khi production:
- Test rotation và revoke.
- Test nhiều instances.
- Test AS/JWKS outage.
- Test cache outage.
- Test concurrency/stampede.
- Đo p95/p99 latency và upstream load.
- Đo freshness/revocation delay.
- Ghi rõ failure policy và owner của từng cache.

## 30. Tổng kết

~~~text
JWT request
   |
   v
JWT Decoder
   |
   v
JWKS cache
  stores public keys
   |
   v
Verify signature + validate claims
   |
   v
Authentication

Opaque request
   |
   v
ReactiveOpaqueTokenIntrospector
   |
   v
Introspection cache
  stores token-specific active/claims
   |
   v
On miss: call Authorization Server
   |
   v
Build authenticated principal
~~~

Các nguyên tắc chính:

1. **JWKS cache lưu public signing keys** để giảm key fetch và hỗ trợ JWT validation availability.
2. **Introspection cache lưu kết quả theo token** để giảm AS round trips.
3. **JWT signature và claims vẫn phải được kiểm tra trên mỗi request**; cached key không phải cached authentication.
4. **Positive introspection cache có thể trì hoãn revoke visibility**; TTL phải xuất phát từ revocation SLA.
5. **TTL positive không được vượt exp hoặc freshness budget**.
6. **Negative result khác upstream error**; timeout/5xx/invalid_client không phải active=false.
7. **Cache key phải cô lập issuer, endpoint, resource và token identity**; tránh dùng subject một mình.
8. **JWKS cache freshness ảnh hưởng key rotation và emergency key removal**, nhưng không thu hồi riêng một user token.
9. **Spring Cache/Caffeine không tự động bật cả hai loại cache**; phải cấu hình integration cụ thể.
10. **Bounded cache, single-flight, rate limit và metrics** giúp tránh stampede và DoS.
11. **In-memory và distributed cache có consistency/availability trade-offs khác nhau**.
12. **Stale-if-error phải có giới hạn rõ ràng**; không dùng stale positive result vô hạn khi dependency down.

**Kết luận:** JWKS cache và introspection cache cùng giảm network work nhưng phục vụ hai mục tiêu khác nhau. JWKS cache tối ưu việc phân phối public keys cho JWT signature verification; introspection cache tối ưu kết quả xác minh từng opaque token và trực tiếp ảnh hưởng độ trễ nhìn thấy revocation. Thiết kế đúng phải có TTL, namespace, invalidation, outage behavior và metrics riêng cho từng cache, dựa trên yêu cầu key rotation, revocation freshness, availability và tải của Authorization Server.

## 31. Tài liệu tham khảo

- **Spring Security Reference — Reactive JWT Resource Server:** cấu hình ReactiveJwtDecoder, issuer và JWK Set URI. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet JWT Resource Server:** NimbusJwtDecoder, JWKS và key rotation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive Opaque Token Resource Server:** ReactiveOpaqueTokenIntrospector và introspection. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Servlet Opaque Token Resource Server:** OpaqueTokenIntrospector và token active state. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Nimbus JOSE + JWT Documentation:** Remote JWK Set, JWK source và cache/refresh behavior. https://connect2id.com/products/nimbus-jose-jwt
- **RFC 7517 — JSON Web Key (JWK):** JWK và JWKS representation. https://www.rfc-editor.org/rfc/rfc7517
- **RFC 7515 — JSON Web Signature (JWS):** JWS header, kid và signature validation. https://www.rfc-editor.org/rfc/rfc7515
- **RFC 7519 — JSON Web Token (JWT):** iss, aud, exp, nbf và claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** active flag và introspection response. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7009 — OAuth 2.0 Token Revocation:** token/grant revocation. https://www.rfc-editor.org/rfc/rfc7009
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** issuer metadata và jwks_uri. https://www.rfc-editor.org/rfc/rfc8414
- **OpenID Connect Discovery 1.0:** provider metadata discovery. https://openid.net/specs/openid-connect-discovery-1_0.html
- **Caffeine Cache Documentation:** bounded local cache, expiration, eviction và loading. https://github.com/ben-manes/caffeine/wiki
- **Spring Framework Cache Abstraction:** cache abstraction và integration boundaries. https://docs.spring.io/spring-framework/reference/integration/cache.html
