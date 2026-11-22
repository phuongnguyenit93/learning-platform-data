# Chi phí xác minh JWT cục bộ và gọi introspection từ xa

Spring Security Resource Server có hai verification path phổ biến cho access token: **xác minh JWT cục bộ** bằng chữ ký và claims, hoặc **gọi token introspection endpoint** của Authorization Server để hỏi token còn active hay không và lấy metadata liên quan. Hai cách có chi phí vận hành khác nhau.

Với JWT local verification, Resource Server thường xác minh chữ ký trên mỗi request bằng public key đã tải và cache từ JWKS. Phần lớn request không cần gọi Authorization Server; chi phí chính nằm ở parse token, cryptographic verification, validators, object allocation và CPU tại Resource Server. Với introspection, Resource Server gửi token tới endpoint từ xa. Nếu không cache kết quả, mỗi request tạo thêm network round trip và tải xử lý trên Authorization Server. Cache giảm chi phí đó nhưng kéo dài thời gian Resource Server có thể tiếp tục dùng một kết quả active cũ sau khi token bị revoke.

Không có lựa chọn luôn nhanh hơn hoặc luôn an toàn hơn. Quyết định phụ thuộc request rate, latency giữa các service, khả năng chịu tải của Authorization Server, yêu cầu thu hồi token, token format, cache policy và availability của identity infrastructure.

Bài học thuộc chương **Hiệu năng và vận hành**, tập trung vào chi phí CPU của JWT signature verification, chi phí network của introspection, khác biệt giữa JWKS cache và introspection-result cache, cấu hình Spring Security, capacity planning, benchmark, metrics, timeout, retry và outage behavior.

> **Ngữ cảnh minh họa:** Orders API chạy Spring Boot 3.x / Spring Security 6.x, nhận access token từ một Authorization Server. Ta so sánh JWT access token được xác minh cục bộ với opaque access token được xác minh qua RFC 7662 introspection. Một JWT cũng có thể được introspect nếu kiến trúc yêu cầu trạng thái tập trung; hai lựa chọn nói về cách Resource Server xác minh, không chỉ về hình dạng chuỗi token.

## 1. Hai mô hình xác thực access token

### 1.1. JWT: Resource Server tự xác minh

JWT access token chứa claims và chữ ký. Resource Server lấy public key từ JWKS, sau đó xác minh chữ ký và kiểm tra issuer, audience, thời hạn, token profile và authorities.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant JWKS as JWKS Endpoint
    Note over RS,JWKS: Key set thường được tải và cache
    C->>RS: Request + Bearer JWT
    RS->>RS: Parse JWT
    RS->>RS: Verify signature using cached public key
    RS->>RS: Validate issuer, audience, exp, nbf
    RS->>RS: Map claims to authorities
    RS-->>C: Response
~~~

Trong steady state, mỗi request không cần gọi JWKS endpoint. JWKS được tải khi decoder cần key set, cache hết hạn hoặc cần refresh do key ID chưa biết, tùy JWK source và cấu hình.

### 1.2. Introspection: Resource Server hỏi Authorization Server

Resource Server gửi token tới endpoint được cấu hình. Authorization Server trả kết quả cho biết token active hay không và có thể kèm subject, scope, audience, client ID, expiry hoặc attributes khác.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: Request + access token
    RS->>AS: POST /introspect
    AS->>AS: Check token state and policy
    AS-->>RS: active + token metadata
    RS->>RS: Build authenticated principal
    RS-->>C: Response
~~~

Nếu không có cache, mỗi request được xác thực tạo một lần gọi introspection. Khi Resource Server cache kết quả, chỉ cache miss mới cần gọi Authorization Server.

### 1.3. Định dạng token và verification path là hai khái niệm riêng

Các cặp thường gặp:

- JWT + local validation là mô hình phổ biến vì JWT có claims và chữ ký có thể kiểm tra offline.
- Opaque token + introspection là mô hình phổ biến vì Resource Server không tự giải mã được token.
- JWT + introspection vẫn có thể được dùng nếu muốn kiểm tra trạng thái tập trung.
- Opaque token có thể được xác minh qua cơ chế riêng nếu hệ thống có trust contract phù hợp.

Khi so sánh chi phí, hãy xác định **verification path** thực tế. Không kết luận mọi JWT đều local hoặc mọi opaque token đều phải introspect theo cùng một cách trong mọi kiến trúc.

## 2. Chi phí của xác minh JWT cục bộ

Một request JWT thường thực hiện các bước:

1. Trích access token từ Authorization header.
2. Parse compact JWT và protected header.
3. Tìm public key phù hợp với issuer và kid trong JWK set cache.
4. Xác minh chữ ký bằng thuật toán được cho phép.
5. Kiểm tra issuer, audience, thời gian và token profile.
6. Chuyển claims thành principal và authorities.
7. Thực hiện authorization cho endpoint/service.

### 2.1. CPU là chi phí chính trên đường request

Chi phí xác minh chữ ký phụ thuộc thuật toán ký như RS256, PS256 hoặc ES256; kích thước RSA key/curve; kích thước JWT và số lượng claims; JOSE/JWT library; CPU architecture; JVM/JIT; garbage collector; validators và custom converter.

Signature verification thường rẻ hơn một network round trip tới Authorization Server, nhưng không miễn phí. Với request rate rất lớn hoặc token/claims lớn, parse, cryptography và object allocation có thể tiêu thụ CPU đáng kể.

### 2.2. Public key được cache, chữ ký vẫn phải verify cho mỗi token

JWKS caching tránh tải public key liên tục. Nó không có nghĩa Resource Server cache kết quả xác thực của mọi access token.

Thông thường, mỗi request vẫn cần đọc token, parse hoặc xử lý compact JWT, xác minh chữ ký, kiểm tra validators và tạo Authentication/authorities cho request. Public key cache giảm network và key parsing overhead; nó không thay thế chữ ký của request hiện tại bằng một kết quả xác thực cũ.

### 2.3. JWKS fetch là chi phí amortized, không phải mỗi request

| Công việc | Tần suất điển hình | Tác động |
|---|---|---|
| JWT parse/signature/claims validation | Mỗi request | CPU, allocation, latency nội bộ |
| JWKS fetch/refresh | Khởi tạo, refresh hoặc unknown kid | Network, latency phụ thuộc identity provider |

Nếu Resource Server có cache key set ổn định, số JWKS fetch thường thấp hơn nhiều số API requests. Cold start, key rotation, cache expiry hoặc unknown kid có thể tạo đợt refresh. Cần đo cả steady state và cold/rotation behavior.

### 2.4. Local validation giảm coupling vào availability của Authorization Server

Khi key đã có trong cache, Resource Server có thể xác minh token mà không cần Authorization Server phản hồi cho từng request. Điều này giảm dependency đồng bộ giữa API traffic và introspection service.

Dù vậy, hệ thống vẫn phụ thuộc issuer/JWKS để tải key mới, khởi động theo một số cấu hình discovery và xử lý rotation. JWT local validation không có nghĩa identity infrastructure có thể ngừng hoạt động vô thời hạn.

### 2.5. Local validation không tự phát hiện revocation ngay lập tức

Nếu token đã được ký hợp lệ và chưa hết hạn, Resource Server có thể tiếp tục chấp nhận token sau khi user bị disable hoặc AS muốn revoke token, trừ khi có cơ chế bổ sung.

Các cách giảm cửa sổ này gồm access token lifetime ngắn, denylist/revocation store, token version/session state, event-driven invalidation, introspection cho endpoint nhạy cảm hoặc emergency deny theo signing key. Mỗi cơ chế bổ sung có chi phí consistency, latency và availability. Nếu mỗi request lại hỏi một revocation store từ xa, một phần lợi ích local JWT có thể giảm.

## 3. Chi phí của introspection từ xa

### 3.1. Network round trip nằm trên đường xác thực

Không cache thì một request API thường tạo thêm request HTTP tới Authorization Server. Latency phụ thuộc khoảng cách network, DNS/TLS/connection setup nếu không reuse connection, connection pool, AS queueing, database/cache phía AS, serialization và network congestion.

Ngay cả khi introspection endpoint xử lý nhanh, round trip qua network có thể chiếm phần lớn latency thêm vào.

### 3.2. Introspection tăng tải theo request rate

Giả sử một Resource Server nhận 5.000 API requests/second và mỗi request đều introspect token. Nếu không cache, AS phải xử lý xấp xỉ 5.000 introspection requests/second từ workload đó, chưa tính retries hoặc traffic của các Resource Server khác.

Nếu có 12 instances cùng nhận traffic, tổng tải phải tính trên toàn cluster. Không capacity-plan chỉ dựa vào một pod.

### 3.3. Introspection tạo dependency availability trực tiếp

Nếu AS introspection endpoint unavailable, Resource Server không thể lấy trạng thái mới của token khi cache miss. Với cache còn hiệu lực, request có thể tiếp tục theo cached result nếu policy cho phép. Khi không có kết quả đáng tin cậy, Resource Server phải fail closed.

~~~text
API request
   |
   v
Resource Server
   |
   v
Introspection endpoint
   |
   v
Authorization Server state
~~~

Một sự cố ở AS, network hoặc connection pool có thể ảnh hưởng đồng thời nhiều API. Cần xem introspection là dependency production quan trọng với SLO, capacity, timeout và alert riêng.

### 3.4. Introspection có thể mang lại trạng thái tập trung mới nhất

Authorization Server có thể trả lời dựa trên trạng thái token hiện tại: token còn active không, đã bị revoke chưa, client/user/session có bị disable không, scope/audience nào được cấp và metadata nào được phép chia sẻ.

Khả năng này phụ thuộc cách AS triển khai và cache nội bộ. RFC 7662 định nghĩa response active, nhưng không tự bảo đảm mọi thay đổi trạng thái được phản ánh tức thời nếu AS có cache hoặc replication delay.

## 4. So sánh chi phí tổng thể

| Tiêu chí | JWT local verification | Remote introspection |
|---|---|---|
| Công việc mỗi request | Parse, verify signature, validate claims | HTTP call hoặc cache lookup, parse response |
| CPU Resource Server | Có cryptographic verification | Thấp hơn ở phần JWT crypto nếu không tự verify JWT |
| Network steady state | Thường không gọi AS | Có request nếu cache miss |
| Latency | Chủ yếu CPU và request processing | Thêm network + AS processing khi miss |
| Tải Authorization Server | JWKS refresh/discovery và token issuance | Tăng theo introspection traffic |
| Revocation visibility | Không tức thời nếu thiếu cơ chế bổ sung | Có thể gần thời gian thực theo AS state/cache |
| Dependency khi AS outage | Có thể tiếp tục với cached public key | Cache hit có thể tiếp tục; miss cần AS |
| Cache quan trọng | Public JWK set | Introspection result theo token |
| Quy mô | Verification CPU tại mỗi Resource Server | AS throughput và network fan-out |
| Metadata | Claims trong JWT | Attributes trong introspection response |

### 4.1. Không chỉ so CPU với network

Chỉ đo CPU signature verification và latency introspection là chưa đủ. Cần tính CPU của AS, TLS/network overhead, cache memory, JWKS fetch khi rotation/cold start, retry amplification, revocation delay do cache và chi phí vận hành của identity infrastructure.

Một phương án giảm CPU ở Resource Server nhưng chuyển tải lớn sang Authorization Server có thể làm tổng chi phí hệ thống tăng.

## 5. Cost model đơn giản để ước lượng

Đặt:

- R: tổng API requests mỗi giây cần authentication.
- Cj: CPU time để xác minh một JWT, tính bằng giây CPU.
- Ci: CPU time của Resource Server cho introspection response handling.
- L: latency của một introspection round trip.
- h: cache hit ratio của introspection, từ 0 đến 1.
- Ca: CPU time Authorization Server tiêu tốn cho một introspection.
- J: số JWKS refresh requests mỗi giây trong steady state.

### 5.1. JWT local verification

~~~text
ResourceServer CPU cores for verification
    ~= R * Cj
~~~

Ví dụ nếu một verification tiêu tốn 0,25 ms CPU và hệ thống xử lý 4.000 requests/second:

~~~text
4,000 * 0.00025 seconds
    = 1 CPU core
~~~

Đây là ví dụ số học, không phải benchmark cho Spring Security hay một thuật toán cụ thể. CPU thực tế cần đo trên hardware/JVM của ứng dụng.

JWKS traffic được tính riêng: JWKS fetch rate xấp xỉ J. Trong steady state J có thể thấp; khi rollout hoặc unknown-kid flood, nó có thể tăng đột biến.

### 5.2. Introspection không cache

~~~text
Introspection request rate ~= R
AS CPU demand ~= R * Ca
Additional latency ~= L
~~~

Nếu request rate là 4.000/second, AS cần xử lý xấp xỉ 4.000 introspection requests/second cho workload đó. Latency L nằm trên đường xác thực của request đồng bộ.

### 5.3. Introspection có cache

Nếu cache hit ratio là h:

~~~text
Introspection request rate ~= R * (1 - h)
AS CPU demand ~= R * (1 - h) * Ca
~~~

Ví dụ R = 4.000 requests/second và hit ratio 95%:

~~~text
4,000 * (1 - 0.95) = 200 remote requests/second
~~~

Cache làm giảm AS traffic đáng kể, nhưng không loại bỏ miss, eviction, cold start hoặc concurrent duplicate misses.

### 5.4. Latency trung bình và tail latency

~~~text
Average auth latency
    ~= h * L_hit + (1 - h) * L_miss
~~~

L_hit thường là local cache lookup và xử lý principal. L_miss bao gồm network round trip, AS processing và response parsing. Công thức trung bình không phản ánh đầy đủ p95/p99. Một tỷ lệ nhỏ cache miss có thể chi phối tail latency khi AS thỉnh thoảng bị chậm.

### 5.5. Tính trên toàn cluster

~~~text
Cluster introspection QPS
    = sum(request rate of every Resource Server)
      * (1 - effective cache hit ratio)
~~~

Nếu mỗi pod có cache riêng, hit ratio có thể thấp hơn khi traffic phân tán trên nhiều token ít lặp lại. Scale-out có thể tạo cold cache trên pod mới. Cache tập trung có thể tăng hit ratio nhưng thêm network hop và dependency riêng.

## 6. Introspection cache: giảm tải và giới hạn revocation delay

### 6.1. Cache key phải đại diện exact token mà không lưu raw token

Introspection result thuộc về một access token cụ thể. Cache key phải phân biệt chính xác token, nhưng tránh lưu raw token trong key/log/metrics. Có thể dùng cryptographic hash hoặc HMAC của token làm cache key.

Không dùng prefix token, subject hoặc client ID làm key vì nhiều token có thể cùng subject/client nhưng trạng thái, scope, audience và expiry khác nhau. Fingerprint vẫn có thể là identifier nhạy cảm; không đưa nó vào log hoặc metric labels.

### 6.2. Cache response active theo TTL có giới hạn

Nếu introspection trả:

~~~json
{
  "active": true,
  "sub": "customer-42",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 2000000600
}
~~~

Resource Server có thể cache principal/metadata trong TTL ngắn. TTL nên không vượt quá thời gian còn lại tới token expiry, revocation staleness window được chấp nhận và TTL tối đa theo security policy.

~~~text
cacheTTL = min(
    configuredMaximumTTL,
    tokenExpiry - now,
    allowedRevocationStaleness
)
~~~

Nếu response không có expiry claim đáng tin, chỉ dùng configured TTL nhỏ theo policy. Không cache active result lâu hơn thời gian token có thể hợp lệ.

### 6.3. Cache active result làm chậm phát hiện revoke

Giả sử Resource Server cache active result trong 60 giây. User bị disable ngay sau khi cache entry được tạo. Resource Server có thể tiếp tục chấp nhận token cho tới khi entry hết hạn hoặc bị invalidated.

TTL không chỉ là tham số hiệu năng; nó là quyết định security policy. Nếu yêu cầu revoke có hiệu lực trong tối đa 5 giây, TTL 60 giây không đáp ứng yêu cầu đó.

### 6.4. Cache negative result cẩn thận

Negative caching ngắn có thể giảm tải khi cùng một token inactive được gửi lặp lại, nhưng:

- Không cache lỗi network/timeout như thể token inactive.
- Không cache lỗi server như kết quả xác thực.
- Dùng TTL ngắn cho inactive result.
- Giới hạn cache size để tránh token ngẫu nhiên làm cạn memory.
- Phân biệt active=false với introspection service unavailable.

Không biến lỗi tạm thời của AS thành cache negative kéo dài khiến token hợp lệ tiếp tục bị từ chối sau khi dịch vụ phục hồi.

### 6.5. Cache miss đồng thời và stampede

Nhiều request cùng token có thể tới một pod ngay sau khi cache entry hết hạn. Nếu mọi request cùng introspect, chúng tạo burst tới AS.

Các kỹ thuật có thể dùng:

- Per-key single-flight/loading cache.
- Cache provider có atomic loading semantics.
- Giới hạn concurrency tới introspection endpoint.
- Connection pooling.
- TTL jitter để tránh nhiều entry hết hạn cùng lúc.
- Rate limit hoặc bulkhead cho introspection calls.

Không dùng một global lock chặn tất cả token khi chỉ một key bị miss. Cơ chế đồng bộ nên giới hạn theo token fingerprint.

### 6.6. Cache result cần được cô lập theo issuer/resource policy

Nếu ứng dụng hỗ trợ nhiều issuer, cache key phải bao gồm trust context phù hợp hoặc cache namespace phải tách theo issuer/introspection client. Không dùng cùng một cache entry cho hai authorization server có policy khác nhau.

Nếu principal mapping phụ thuộc resource/audience hoặc client registration, cache key và cached result cần phản ánh context đó.

## 7. Caching OpaqueTokenIntrospector trong Spring

Spring Security cho phép tùy biến OpaqueTokenIntrospector. Có thể bọc introspector thật bằng cache để cache principal từ introspection.

~~~java
public final class CachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Cache cache;

    public CachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            Cache cache) {
        this.delegate = delegate;
        this.cache = cache;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String key = hmacFingerprint(token);

        Cache.ValueWrapper cached = cache.get(key);
        if (cached != null) {
            return (OAuth2AuthenticatedPrincipal) cached.get();
        }

        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        // Cache only successful active results.
        // The cache provider must enforce a bounded TTL and size.
        cache.put(key, principal);
        return principal;
    }
}
~~~

Đây là skeleton để minh họa decorator; các import, HMAC helper và cache provider được lược bỏ. Production cần cache provider có TTL và giới hạn kích thước; TTL không vượt quá token expiry hoặc revocation staleness policy; per-entry expiry nếu token lifetime khác nhau; single-flight để tránh duplicate misses; không cache exception từ network/AS; cân nhắc principal attributes immutable hoặc defensive copy; tách cache namespace theo issuer; và metric hit, miss, eviction, expiry.

Không dùng một TTL dài cố định cho mọi token nếu token lifetime khác nhau. Nếu không thể xác định expiry đáng tin cậy từ introspection response, giới hạn TTL theo policy chặt hơn.

### 7.1. Cấu hình introspection endpoint

Ví dụ application YAML:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: SECRET_FROM_ENVIRONMENT
~~~

Hoặc DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspectionUri(
            "https://id.example.com/oauth2/introspect"
        )
        .introspectionClientCredentials(
            "orders-resource-server",
            introspectionClientSecret
        )
    )
);
~~~

Client credentials ở đây xác thực Resource Server với introspection endpoint. Chúng không phải access token của end user. Giữ secret trong secret manager/environment injection, không commit vào source hoặc log.

### 7.2. Gắn caching introspector vào Resource Server

Cấu hình khái niệm:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        CacheManager cacheManager,
        IntrospectionProperties properties) {

    OpaqueTokenIntrospector remote =
        new NimbusOpaqueTokenIntrospector(
            properties.introspectionUri(),
            properties.clientId(),
            properties.clientSecret()
        );

    return new CachingOpaqueTokenIntrospector(
        remote,
        cacheManager.getCache("activeAccessTokens")
    );
}
~~~

Resource Server dùng bean introspector theo cấu hình tương ứng:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(opaqueTokenIntrospector)
    )
)
~~~

Tên constructor, property binding và cách Spring Boot tự tạo introspector có thể thay đổi theo version. Nếu cung cấp custom bean, kiểm tra auto-configuration back-off và đảm bảo chỉ có một introspector được dùng trong filter chain.

## 8. Cấu hình JWT local verification trong Spring Security

### 8.1. Dùng issuer-uri và JWKS

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
~~~

Spring Security dùng issuer metadata/JWKS discovery theo cấu hình để tạo decoder. Ở runtime, public keys được tải và cache theo JWK source behavior; JWT signature được xác minh cho từng token.

Có thể cấu hình JWKS URI trực tiếp:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

Cấu hình trực tiếp JWKS URI có thể giảm nhu cầu discovery metadata trong một số startup paths, nhưng issuer validation vẫn cần được giữ. Kiểm tra behavior của Spring Boot/Spring Security version đang dùng.

### 8.2. Thêm audience validator

JWT signature hợp lệ chưa đủ; token cần được cấp cho API này.

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }

    OAuth2Error error = new OAuth2Error(
        "invalid_token",
        "Required audience is missing",
        null
    );

    return OAuth2TokenValidatorResult.failure(error);
};
~~~

Kết hợp với default issuer/time validators:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://id.example.com";
    String jwkSetUri = "https://id.example.com/oauth2/jwks";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    OAuth2TokenValidator<Jwt> validator =
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator()
        );

    decoder.setJwtValidator(validator);
    return decoder;
}
~~~

Không thay default timestamp/issuer validation bằng custom audience validator đơn lẻ nếu không chủ đích. Compose các validators để giữ đủ điều kiện.

### 8.3. Signature verification vẫn tiêu tốn CPU

JWT local validation không phải decode payload rồi tin claims. Resource Server phải verify chữ ký bằng public key đáng tin cậy. Chỉ sau khi chữ ký và validators thành công mới tạo authenticated principal.

Không cache một quyết định authentication vô thời hạn dựa trên token string. Nếu có cache kết quả đã verify, phải tính đến exp, key rotation, issuer/audience policy, revocation và cache invalidation. Trong nhiều hệ thống, cache public JWK là đủ và dễ kiểm soát hơn.

## 9. Tối ưu hiệu năng cho JWT verification

### 9.1. Giữ JWK source và connection pooling ổn định

JWKS fetch nên dùng HTTP client có connection reuse, timeout rõ ràng và TLS configuration đúng. Tránh tạo HTTP client mới cho mỗi request hoặc mỗi decoder instance. Đảm bảo decoder/JWK source được quản lý singleton phù hợp với application context.

### 9.2. Tránh refresh storm khi key ID chưa biết

Khi key rotation xảy ra, nhiều request đầu tiên có thể mang kid mới. Nếu mỗi request cùng trigger JWKS refresh, AS/JWKS endpoint bị burst. Kiểm tra cơ chế cache/refresh của Nimbus/Spring version và dùng giới hạn concurrency/rate control ở lớp phù hợp.

Unknown kid cũng có thể bị attacker khai thác để gây tải. Không refresh vô hạn hoặc đồng bộ vô hạn trên request path.

### 9.3. Giữ token và claims vừa đủ

JWT quá lớn làm tăng header parsing, base64url decoding, JSON parsing, allocation, network bytes ở mọi hop, logging/tracing risk và proxy header limits. Chỉ đưa claims cần thiết vào access token. Tránh nhúng profile, danh sách quyền rất dài hoặc dữ liệu nghiệp vụ có thể truy vấn từ service riêng.

### 9.4. Chọn thuật toán theo policy và benchmark

RSA và EC có profile hiệu năng khác nhau trên từng CPU/JVM. Không chọn thuật toán chỉ vì benchmark một máy đơn lẻ. Cần cân nhắc interoperability, key management, issuer support, security policy và kết quả benchmark trên production-like hardware.

Không giảm key size hoặc chuyển sang thuật toán yếu hơn chỉ để đạt throughput. Algorithm allowlist phải được cấu hình rõ.

### 9.5. Đừng cache principal JWT mà bỏ qua validators

Cache kết quả authentication theo token fingerprint có thể bỏ qua expiry vừa xảy ra, issuer/audience policy thay đổi, key bị deny/compromise, token revocation hoặc tenant/permission policy thay đổi.

Nếu buộc phải cache, entry TTL phải bị chặn bởi exp và staleness budgets; có invalidation khi key/policy thay đổi; không coi cache hit là quyền vô hạn. Với đa số hệ thống, cache JWK set và xác minh token mỗi request là mô hình đơn giản hơn.

## 10. Tối ưu hiệu năng cho remote introspection

### 10.1. Dùng HTTP connection pool

Introspection client nên reuse connections và TLS sessions. Không tạo HTTP client mới cho mỗi request. Đặt giới hạn pool phù hợp concurrency và AS capacity; đo thời gian chờ connection lease riêng với thời gian AS xử lý.

### 10.2. Đặt timeout hữu hạn

Cần connection timeout, response/read timeout, pool acquisition timeout và tổng deadline phù hợp với API request budget.

Không để request giữ thread/connection vô hạn khi AS treo. Timeout quá ngắn gây lỗi giả lúc tải cao; timeout quá dài kéo dài tail latency và giữ tài nguyên.

### 10.3. Giới hạn concurrency và retry

Bulkhead hoặc semaphore có thể giới hạn số introspection calls đồng thời. Khi AS quá tải, từ chối sớm theo policy tốt hơn để tất cả request xếp hàng vô hạn.

Retry chỉ nên dùng cho lỗi transient được xác định, với số lần nhỏ, backoff/jitter và deadline. Không retry token inactive hoặc invalid credentials. Không retry mọi 4xx. Retry có thể nhân đôi tải trong outage nếu không có budget.

### 10.4. Cache có chủ đích

Cache active result có thể giảm QPS tới AS. Chọn TTL theo revocation SLA, token expiry và khả năng invalidation. Cache local có latency thấp và consistency per pod; distributed cache chia sẻ state nhưng thêm network hop và dependency riêng.

### 10.5. Phân biệt introspection failure với inactive token

Hai tình huống khác nhau:

- AS trả response thành công với active=false: token không active.
- Resource Server không thể gọi AS hoặc response malformed: không xác định được token state.

Không cache dependency failure thành inactive token. Không biến dependency failure thành authenticated. Error mapping nên phân biệt token invalid với identity provider unavailable theo API contract và observability.

## 11. Availability và fail-closed behavior

### 11.1. JWT local validation khi JWKS endpoint outage

Nếu public key cần thiết còn trong cache, Resource Server có thể tiếp tục xác minh JWT theo behavior của JWK source. Nếu cần key mới mà không tải được JWKS, token không thể được xác minh và phải bị từ chối.

Không bypass signature verification khi JWKS unavailable.

### 11.2. Introspection outage

Nếu cache có active result còn trong TTL và policy cho phép, Resource Server có thể dùng kết quả đó. Khi cache miss và AS không truy cập được, Resource Server không biết token còn active hay không. Phải fail closed cho request cần xác thực.

Không coi timeout là active. Không chấp nhận token chỉ vì request đã từng thành công.

### 11.3. Có nên trả 401 hay 503?

Token invalid/inactive thường được xử lý như authentication failure, thường là 401 với semantics Bearer phù hợp. Dependency unavailable lại là operational failure. API gateway/error handling có thể chọn 503 khi xác định identity dependency đang unavailable, nhưng không được biến nó thành access granted.

Spring Security default exception mapping và loại exception từ decoder/introspector có thể ảnh hưởng status cuối cùng. Nếu API cần phân biệt 401 invalid token với 503 identity provider outage, hãy cấu hình và integration-test mapping theo version; không chỉ thay đổi status mà làm lộ chi tiết nội bộ hoặc token.

### 11.4. Circuit breaker không phải fallback allow

Circuit breaker ngăn gọi một AS đang lỗi và bảo vệ thread pool. Khi circuit open, request cần introspection vẫn không có kết quả đáng tin cậy. Fallback an toàn là từ chối/return dependency error theo contract, không tự động chấp nhận token.

## 12. Capacity planning cho Resource Server và Authorization Server

### 12.1. Ước lượng CPU JWT

Dùng benchmark thực tế để đo CPU time cho token representative:

~~~text
JWT verification CPU cores
    ~= request rate * CPU seconds per verification
~~~

Cộng thêm CPU cho controller, database, serialization, TLS và filters khác. Không dành toàn bộ core budget cho signature verification.

### 12.2. Ước lượng AS introspection QPS

Không cache:

~~~text
AS introspection QPS ~= authenticated API request QPS
~~~

Có cache:

~~~text
AS introspection QPS
    ~= API request QPS * (1 - cache hit ratio)
~~~

Cộng thêm retry, cold starts, multiple resources, token churn và cache eviction. Cache hit ratio phải đo theo workload thật; không dùng giả định 99% nếu mỗi request có token khác nhau.

### 12.3. Tính concurrency theo latency

Một ước lượng theo Little's Law:

~~~text
in-flight introspection calls
    ~= introspection arrival rate * average response time
~~~

Ví dụ 1.000 calls/second với average round trip 40 ms:

~~~text
1,000 * 0.040 = 40 concurrent calls
~~~

Đây là concurrency trung bình lý tưởng hóa. p95/p99, burst traffic và connection pool contention có thể yêu cầu headroom cao hơn.

### 12.4. Scale-out có thể làm cache lạnh hơn

Nếu cache introspection nằm local mỗi pod, thêm pod làm phân tán token traffic và tạo cache cold start. Nếu mỗi token chỉ được dùng ít lần, hit ratio có thể thấp. Distributed cache tăng khả năng chia sẻ nhưng thêm network/availability dependency.

So sánh cả hai bằng cùng traffic distribution và token reuse pattern.

## 13. Benchmark đúng cách

### 13.1. Đo từng thành phần trước

Có thể tách benchmark thành:

1. JWT parse + signature verification.
2. JWT validators + authority conversion.
3. Introspection HTTP client tới AS mock có latency cố định.
4. Introspection tới AS test thực.
5. Cache hit lookup.
6. Cache miss + remote introspection.
7. End-to-end request qua SecurityFilterChain.

Benchmark micro của cryptography hữu ích để hiểu CPU, nhưng không thay thế load test end-to-end.

### 13.2. Giữ điều kiện so sánh công bằng

Cố định CPU/memory/JVM flags, Spring Security/JWT library version, request mix, authorization rules, token size/claims representative, TLS, connection pool, JVM warm-up và concurrency. Tách database/downstream effects hoặc đo riêng.

Không so local JWT trong JVM warm với introspection cold connection mỗi lần rồi kết luận về kiến trúc.

### 13.3. Đo p50, p95, p99 và throughput

Thu thập request throughput, end-to-end latency p50/p95/p99, authentication latency, CPU utilization và CPU time/request, allocation/GC, JWKS fetch count/latency, introspection QPS/latency, cache hit ratio, timeout/retry/error rate, AS CPU/queue depth/connection saturation.

Average latency có thể che giấu tail latency khi AS hoặc network có spike.

### 13.4. Test cold start, rotation và outage

Ngoài steady state, chạy các kịch bản: Resource Server mới khởi động với JWKS cache rỗng; JWKS endpoint chậm hoặc 503; JWT mang kid mới sau rotation; introspection cache rỗng sau deploy; AS latency tăng; AS outage và phục hồi; cache backend unavailable; token churn cao; burst nhiều request cùng token; nhiều token khác nhau gây cache eviction.

Đây là các kịch bản thường quyết định hệ thống có chịu được sự cố hay không.

## 14. Kiểm thử hiệu năng và hành vi với Spring Security

### 14.1. JWT integration test

Dùng Nimbus decoder thật với test key/JWKS endpoint. Kiểm tra token ký đúng được chấp nhận, signature sai bị từ chối, issuer/audience/expiry validators hoạt động, JWKS fetch theo cache/refresh behavior, rotation với kid mới và outage khi key còn cache hoặc cache miss.

Không dùng jwt() MockMvc postprocessor để benchmark JWT verification; postprocessor cài authentication giả lập và bỏ qua signature verification.

### 14.2. Introspection integration test

Dùng WireMock/MockWebServer hoặc test Authorization Server. Kiểm tra request POST đúng endpoint, client authentication đúng, token được gửi theo protocol chứ không nằm trong URL, active=true tạo principal phù hợp, active=false bị từ chối, timeout/5xx không trở thành authenticated, cache hit không gọi AS, cache expiry tạo call mới và revocation sau cache fill được nhìn thấy trong giới hạn TTL/invalidation policy.

### 14.3. Test cache TTL bằng clock/test cache

Không dùng Thread.sleep dài để đợi TTL. Dùng cache provider hỗ trợ ticker/clock có thể điều khiển hoặc test abstraction có thể advance time. Kiểm tra thời gian còn lại của token expiry được áp dụng vào cache TTL.

### 14.4. Test không log credential

Dùng log capture hoặc test instrumentation để xác nhận raw access token không xuất hiện trong log, metric label, exception message hoặc cache diagnostic. Introspection request body chứa token và cần được bảo vệ khỏi HTTP wire logging.

## 15. Metrics và observability

### 15.1. JWT local verification metrics

| Metric | Ý nghĩa |
|---|---|
| jwt.validation.success | Token JWT hợp lệ |
| jwt.validation.failure | Token JWT bị từ chối |
| jwt.signature.validation.time | Thời gian verify chữ ký |
| jwt.claim.validation.time | Thời gian validators |
| jwt.authority.conversion.time | Thời gian map authorities |
| jwks.fetch.count | Số lần tải JWKS |
| jwks.fetch.latency | Latency lấy key set |
| jwks.fetch.failure | Lỗi tải JWKS |
| jwks.cache.hit / miss | Cache behavior |
| jwt.unknown_kid | Token dùng kid chưa biết |

Không phải tất cả metric này được Spring Security phát ra sẵn. Có thể cần instrument decoder, JWK source hoặc HTTP client.

### 15.2. Introspection metrics

| Metric | Ý nghĩa |
|---|---|
| introspection.request.count | Số request tới AS |
| introspection.request.latency | Thời gian round trip |
| introspection.request.failure | Timeout, network hoặc HTTP errors |
| introspection.active | Response active |
| introspection.inactive | Response inactive |
| introspection.cache.hit | Cache hit |
| introspection.cache.miss | Cache miss |
| introspection.cache.eviction | Entry bị eviction |
| introspection.inflight | Số call đồng thời |
| introspection.retry.count | Số lần retry |

### 15.3. Tránh high-cardinality và secret labels

Không dùng raw token, token hash, sub, email, session ID hoặc jti làm metric labels. Fingerprint token vẫn có thể là identifier nhạy cảm và tạo cardinality lớn. Dùng labels giới hạn như issuer alias, outcome, resource server name và error category.

Log không chứa Authorization header, introspection request body, client secret hoặc full claims. Có thể ghi correlation ID và reason code đã chuẩn hóa.

## 16. Lựa chọn theo workload

### 16.1. API traffic cao, token lifetime ngắn, revocation window chấp nhận được

JWT local validation thường phù hợp khi request rate lớn, Resource Server cần latency thấp, issuer/JWKS có availability tốt, token có audience/scope rõ, access token lifetime ngắn và hệ thống chấp nhận revocation delay theo TTL hoặc có cơ chế bổ sung.

Chi phí cryptographic verification được phân tán trên các Resource Server instances thay vì tập trung vào AS.

### 16.2. Cần kiểm soát trạng thái tập trung

Introspection phù hợp khi token opaque, token revocation/state phải được kiểm tra thường xuyên, metadata nằm trong AS, có yêu cầu thay đổi trạng thái nhanh và AS đủ capacity/availability.

Nếu cache quá lâu, lợi ích về trạng thái mới nhất bị giảm. Nếu không cache, AS phải gánh QPS và latency cho mỗi request.

### 16.3. Mô hình kết hợp

Có thể dùng JWT local cho phần lớn API read traffic, introspection cho endpoint nhạy cảm cần trạng thái gần thời gian thực, access token lifetime ngắn, cache introspection rất ngắn cho workload có token reuse cao, hoặc service identity/token exchange cho outbound calls.

Mô hình kết hợp tăng độ phức tạp. Cần xác định rõ endpoint/token class nào dùng decoder hoặc introspector nào và không vô tình fallback giữa hai cơ chế khi một cơ chế lỗi.

## 17. Các sai lầm thường gặp

1. **Cho rằng JWT verification không có chi phí vì public key đã cache:** chữ ký và claims vẫn được kiểm tra cho từng request.
2. **Cho rằng Resource Server gọi JWKS trên mọi request:** JWK set thường được cache; fetch xảy ra theo lifecycle/refresh behavior.
3. **Cho rằng introspection luôn chậm:** kết quả phụ thuộc network, AS, connection pool và cache hit ratio.
4. **Không cache introspection dù token reuse cao:** AS có thể bị tải theo toàn bộ API QPS.
5. **Cache active result quá lâu:** revocation bị trì hoãn vượt policy.
6. **Cache lỗi timeout thành inactive:** dependency outage bị biến thành token invalid kéo dài.
7. **Cache inactive vô thời hạn:** token hợp lệ có thể tiếp tục bị từ chối sau phục hồi hoặc thay đổi state.
8. **Không giới hạn cache size:** token ngẫu nhiên có thể làm cạn memory.
9. **Dùng raw token làm cache key/log:** tăng rủi ro lộ credential.
10. **Không có single-flight:** concurrent cache miss tạo introspection stampede.
11. **Retry không giới hạn:** làm AS outage nghiêm trọng hơn.
12. **Fail open khi AS unavailable:** request được chấp nhận mà không có trạng thái token đáng tin.
13. **Benchmark chỉ average latency:** bỏ qua p95/p99 và cache miss tail.
14. **Benchmark JWT bằng jwt() test postprocessor:** không đo signature verification.
15. **Chỉ đo Resource Server CPU:** bỏ qua AS CPU/network và tổng cost của cluster.
16. **Dùng introspection cache nhưng không tính revocation SLA:** tối ưu hiệu năng làm sai security requirement.

## 18. Checklist thiết kế và vận hành

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Token model | JWT hay opaque? Có cần introspect JWT không? |
| Verification path | Local decoder hay remote introspector? |
| JWT crypto | Algorithm/key size có allowlist và benchmark chưa? |
| JWKS | TTL, refresh, unknown-kid và outage behavior ra sao? |
| Issuer/audience | Validators được cấu hình đầy đủ chưa? |
| Introspection | Endpoint, client authentication và TLS đã bảo vệ chưa? |
| Connection pool | Có reuse connection và giới hạn concurrency không? |
| Timeout | Connect/read/overall deadline có hữu hạn không? |
| Retry | Retry budget/backoff có giới hạn không? |
| Cache | TTL, size, key fingerprint và namespace ra sao? |
| Revocation | Cache TTL có nằm trong revocation SLA không? |
| Cache outage | Cache unavailable thì policy fail như thế nào? |
| Stampede | Concurrent miss có single-flight không? |
| Capacity | AS QPS và Resource Server CPU được tính trên toàn cluster chưa? |
| Benchmark | Có p50/p95/p99, throughput, CPU, GC và network không? |
| Failure tests | Có test timeout, 5xx, JWKS outage và rotation không? |
| Observability | Có cache hit/miss, fetch latency, AS saturation và error categories không? |
| Logging | Không log token, secret hoặc introspection body? |
| Fallback | Không chấp nhận token khi không thể xác minh? |

## 19. Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response và token active state.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách gửi Bearer token và error semantics.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và token structure.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS format.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation và algorithm/key security.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile và validation access token.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer, JWKS và validators.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và opaque token authentication.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): cấu hình Servlet Resource Server.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): JWT, JWK/JWKS và remote key source.

**Kết luận:** JWT local verification chuyển phần lớn chi phí xác thực sang CPU của từng Resource Server và chỉ cần JWKS fetch/refresh theo key lifecycle; introspection chuyển một phần chi phí sang network và Authorization Server, đặc biệt khi không cache. Cache introspection giảm QPS và latency nhưng tạo revocation delay cần nằm trong security SLA. Hãy benchmark end-to-end trên workload thực, đo p95/p99, CPU, AS QPS, cache hit ratio và outage behavior; sau đó chọn verification path phù hợp với yêu cầu revocation, availability, latency và tổng chi phí của cả hệ thống.
