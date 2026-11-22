# Cache phản ứng và tránh gọi đồng thời lặp lại cùng một công việc

Trong **Spring Security OAuth 2.0 / OIDC Resource Server** sử dụng **Spring WebFlux**, một API có thể nhận hàng trăm hoặc hàng nghìn HTTP requests đồng thời mang **cùng một opaque Bearer Access Token**. Nếu mỗi request đều phải gọi **Authorization Server token introspection endpoint**, Resource Server có thể tạo ra rất nhiều HTTP requests giống hệt nhau, làm tăng độ trễ, chi phí mạng và tải lên hệ thống định danh.

Vấn đề có hai lớp khác nhau:

1. **Cache kết quả introspection** trong một khoảng thời gian an toàn: một kết quả `active: true` đã xác thực có thể được dùng lại trong thời gian ngắn, với điều kiện cache không vượt expiration của token và giới hạn thu hồi quyền.
2. **Gộp những lời gọi đang diễn ra (single-flight, request coalescing)**: nếu 50 requests đồng thời cần introspect *cùng một token* khi cache đang trống, chỉ một yêu cầu introspection nên thực hiện trong một instance, còn những người chờ khác cùng nhận kết quả đó.

Trong lập trình phản ứng, cả hai yêu cầu đều liên quan đến **thời điểm subscribe vào `Mono`**, cách `Mono.cache()` chia sẻ subscription, vòng đời lỗi/cancel và giới hạn bộ nhớ. Một giải pháp “cache cho nhanh” viết không cẩn thận có thể **tái sử dụng token đã thu hồi, cache lỗi 503, trộn authorities của hai token, làm rò rỉ Bearer token qua cache key hoặc mất Reactor Context**.

Bài học đi từ **RFC 7662**, `ReactiveOpaqueTokenIntrospector`, `Mono.cache`, TTL, Caffeine, HMAC token fingerprint, cancellation, retry, nhiều instance cho đến **thiết kế và kiểm thử single-flight**. Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux, Reactor 3.x**; tên miền, token, scope và key đều là giá trị minh họa. Đây là bài về **introspection phản ứng**, không phải cache response của REST endpoint hay một cache user profile chung.

## 1. Bắt đầu từ luồng xác thực opaque Access Token

Client gọi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer OPAQUE_ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Nếu Resource Server được cấu hình **opaque token**, luồng tổng quát:

~~~text
HTTP request / Bearer token
            |
            v
Spring Security WebFlux
            |
            v
Reactive Authentication
            |
            v
ReactiveOpaqueTokenIntrospector.introspect(token)
            |
            | HTTPS POST /oauth2/introspect
            | token=...
            v
Authorization Server
            |
            +--- {"active":false} -> token bị từ chối
            |
            +--- {"active":true, ...}
                      |
                      v
              OAuth2AuthenticatedPrincipal
                      |
                      v
              Authentication / authorities
                      |
                      v
              authorizeExchange / method security
                      |
                      v
              Owner / tenant / domain policy
~~~

RFC 7662 định nghĩa phản hồi introspection có trường **`active` dạng JSON boolean**. Ví dụ:

~~~json
{
  "active": true,
  "sub": "external-person-42",
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iss": "https://identity.example.test/realms/demo",
  "exp": 1893456000
}
~~~

Ngược lại, một token không được chấp nhận:

~~~json
{"active": false}
~~~

**HTTP 200 từ introspection không đồng nghĩa token active.** Client HTTP có thể nhận 200 kèm `active:false`, vì request introspection thành công về mặt giao thức nhưng token được xác định là không được dùng.

### 1.1. Vì sao không được cache `active:true` vô thời hạn?

Một token có thể:

- **Hết hạn** theo `exp`.
- Bị **thu hồi** trước `exp` bằng quy trình của Authorization Server.
- Không còn hợp lệ vì grant/session/client bị thay đổi theo chính sách issuer.
- Không được Resource Server hiện tại phép introspect, khi đó endpoint có thể trả `active:false`.
- Vẫn active tại IdP nhưng local account, tenant membership hoặc quyền trên bản ghi **đã thay đổi**.

Giữ một kết quả `active:true` quá lâu đồng nghĩa Resource Server có thể chấp nhận token mà Authorization Server đã thu hồi. **Mỗi giây TTL cache là một lựa chọn đánh đổi giữa hiệu năng và độ trễ thu hồi quyền**, không phải một tối ưu không có rủi ro.

### 1.2. Dữ liệu nào thật sự được cache?

Nếu triển khai cache introspection, dữ liệu đầu ra thích hợp là **metadata đã được introspector tiêu chuẩn xác thực**, chẳng hạn `OAuth2AuthenticatedPrincipal` và authorities tương ứng với **token cụ thể**, cùng giới hạn thời gian.

Không nên cache toàn bộ:

- `ServerWebExchange` hoặc HTTP request.
- `SecurityContext` của một subscriber rồi tái sử dụng cho subscriber khác.
- Session, cookie, Authorization header hay principal “current user” theo biến toàn cục.
- Quyết định owner/tenant đối với **một bản ghi đang thay đổi** rồi áp cho toàn bộ request sau.

Spring Security vẫn phải tạo/duy trì **authentication của từng request** và áp các bước authorization sau introspection. Cache không được biến một scope chung thành quyền truy cập mọi bản ghi.

## 2. Hai mục tiêu khác nhau: result cache và single-flight

Giả sử trong cùng 10 mili-giây có 30 HTTP requests cùng Bearer token `T`.

**Không cache, không single-flight:**

~~~text
Request 01 -- introspect(T) --\
Request 02 -- introspect(T) ---\
Request 03 -- introspect(T) ----> Authorization Server
 ...                            /
Request 30 -- introspect(T) ---/

30 introspection requests cho cùng token T
~~~

**Chỉ có result cache thông thường, không phối hợp cache miss:**

~~~text
Cache(T) = miss
   |
   +-- R1 kiểm tra: miss -> bắt đầu gọi upstream
   +-- R2 kiểm tra: miss -> bắt đầu gọi upstream
   +-- R3 kiểm tra: miss -> bắt đầu gọi upstream
   ...

Khi lời gọi đầu tiên xong mới có cache hit,
nhưng các lời gọi song song đã được gửi đi.
~~~

**Single-flight cộng cache:**

~~~text
                  Cache lookup theo token T
                        |
                        +-- Có result còn hạn -> trả result
                        |
                        +-- Miss
                              |
                              v
                        In-flight lookup(T)
                              |
                 +------------+-------------+
                 |                          |
           Chưa có lời gọi             Đang có Mono
                 |                          |
                 v                          v
           Tạo 1 Mono               Dùng chung Mono
           rồi lưu vào map                |
                 |                        |
                 +------------+-----------+
                              |
                              v
                    Chỉ 1 call introspection
                              |
                              v
                  N subscribers nhận cùng signal
~~~

| Khái niệm | Giải quyết | Không tự giải quyết |
| --- | --- | --- |
| **Result cache** | Giảm số introspection calls **sau khi đã có kết quả**, khi còn TTL. | “Cache stampede” khi nhiều requests đến cùng lúc lúc miss. |
| **Single-flight** | Gộp nhiều concurrent calls cùng key khi một lời gọi đang chạy. | Tái sử dụng kết quả lâu dài sau khi lời gọi xong, nếu không có cache. |
| **Timeout/bulkhead** | Giới hạn thời gian và đồng thời gọi introspection. | Không quyết định token còn hợp lệ hay phạm vi quyền. |
| **Revocation invalidation** | Giảm thời gian sử dụng kết quả active cũ. | Không thay JWT/opaque authentication và domain authorization. |

Đối với introspection, cache và single-flight thường được thiết kế **cùng nhau** nhưng có policy riêng: cache TTL có thể rất ngắn, còn single-flight vẫn cần để giảm lời gọi đồng thời khi TTL đã hết.

## 3. Reactor: assembly, subscribe và cùng một Publisher

Trong Reactor, `Mono` thường là **cold Publisher**: tạo `Mono` chưa tự gửi HTTP request; **subscription** mới kích hoạt công việc.

~~~java
import reactor.core.publisher.Mono;

Mono<String> source = Mono.defer(() -> {
    System.out.println("Executing introspection-like work");
    return Mono.just("active");
});

// Chưa gọi lambda trong defer.

source.subscribe(System.out::println);
source.subscribe(System.out::println);
~~~

Với cold `source`, hai lần subscribe dẫn đến hai lần thực hiện phần bên trong `defer`. Nếu bên trong là `WebClient.post().retrieve().bodyToMono(...)`, nó có thể gửi **hai network requests**.

### 3.1. Vì sao Mono.just không phải deferred HTTP call?

~~~java
// Method createResult() được gọi ngay trước Mono.just().
Mono<Result> eager = Mono.just(createResult());

// createResult() được gọi tại subscription.
Mono<Result> deferred =
    Mono.fromCallable(() -> createResult());

// Publisher được tạo tại subscription.
Mono<Result> deferredPublisher =
    Mono.defer(() -> makeReactiveRequest());
~~~

`Mono.fromCallable` trì hoãn công việc đồng bộ, **không làm nó non-blocking**. Với introspection phản ứng, ưu tiên `WebClient`/reactive HTTP client; không gọi `block()` hoặc `Future.get()` trên event loop chỉ để đơn giản hóa cache.

### 3.2. Dùng Mono.cache() để chia sẻ một lần thực hiện

~~~java
Mono<OAuth2AuthenticatedPrincipal> shared =
    delegate.introspect(token).cache();
~~~

Khi **nhiều subscribers dùng cùng object `shared`**, `Mono.cache()` có thể chia sẻ subscription upstream và tái phát **terminal signal** cho subscribers đến sau. Đây là nền tảng cho **single-flight**.

Nhưng ví dụ trên có rủi ro khi đặt `shared` vào cache ứng dụng không có eviction:

- `cache()` không có TTL có thể **giữ result lâu vô hạn** trong vòng đời `Mono`.
- Nó cũng có thể **cache error** hoặc empty completion; lỗi 503 không nên trở thành kết luận lâu dài.
- Một cached `active:true` không tự biết token vừa bị revoke.
- Nếu vô tình dùng chung `Mono` giữa **các token khác nhau**, authorities có thể bị trộn.

Vì vậy, `Mono.cache()` không tham số phù hợp hơn để chia sẻ công việc **trong phạm vi rất ngắn hoặc một request được kiểm soát**. Cache introspection **giữa nhiều HTTP requests** nên có **TTL, giới hạn kích thước và key đúng**.

### 3.3. Một Mono.cache() local không tự gộp mọi HTTP requests

Ví dụ:

~~~java
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token).cache();
}
~~~

Mỗi lần method được gọi, nó tạo **một `Mono` khác**. Nếu 30 HTTP requests gọi method, có thể có 30 cached Monos tách biệt, mỗi cái gửi một upstream request. **Single-flight cần một registry/cache dùng chung theo key**, không phải chỉ thêm `.cache()` ở cuối hàm.

## 4. Cache key: phải dựa trên token cụ thể và security namespace

Các token có cùng `sub` không nhất thiết có cùng quyền hoặc trạng thái:

~~~text
Token A:
  sub = person-42
  scope = orders.read
  aud = orders-api
  exp = 10:05

Token B:
  sub = person-42
  scope = orders.write
  aud = orders-api
  exp = 10:15
~~~

Nếu cache theo `sub`, token A có thể bị gán metadata `orders.write` của token B. Đây là **lỗi tăng quyền nghiêm trọng**.

| Cache key | Có phù hợp không? | Lý do |
| --- | --- | --- |
| `sub` hoặc email | **Không** | Nhiều tokens cùng user nhưng khác scope, audience, expiration, revocation. |
| `client_id` | **Không** | Một OAuth client có nhiều Access Tokens. |
| `tenant_id` | **Không** | Không đại diện cho token riêng biệt. |
| Toàn bộ raw token làm metric label/log | **Không** | Rò rỉ Bearer credential. |
| Fingerprint có khóa HMAC của token + issuer/resource namespace | **Có thể phù hợp** | Không lộ trực tiếp token trong cache key và phân biệt context tin cậy. |

### 4.1. Vì sao nên dùng HMAC thay vì log/hash đơn giản?

Bearer Access Token là một secret. Mặc dù opaque token thường có entropy cao, không nên mặc định mọi issuer cấp token có entropy đủ để **hash không có khóa** không bị đoán ngược bằng dictionary.

Một cache key có thể là:

~~~text
HMAC-SHA256(
    secretKey,
    introspectionEndpointId + "\0" +
    resourceId + "\0" +
    rawAccessToken
)
~~~

HMAC secret do ứng dụng quản lý, không dùng chung tùy tiện với JWT signing key hay OAuth client secret. Resource/issuer namespace giúp tránh reuse kết quả của một introspection policy sang API/tenant khác.

**Không đưa raw token, HMAC digest hoặc secret vào logs/metrics labels**: dù HMAC khó đảo ngược, digest ổn định vẫn có thể trở thành định danh theo dõi hoặc hỗ trợ correlation không cần thiết. Giữ cache private, giới hạn heap dumps và quyền truy cập observability.

### 4.2. Namespace phải được server kiểm soát

Không dùng issuer URL do client tự khai hoặc header `X-Issuer` chưa xác thực để chọn introspection endpoint/cache namespace. Introspection endpoint và **resource audience** phải xuất phát từ cấu hình được kiểm soát hoặc cơ chế multi-issuer routing đã được thẩm định.

Nếu cùng một token string được introspect bởi hai Authorization Server hoặc hai chính sách resource khác nhau, cache không được mặc nhiên dùng lại kết quả giữa hai security domains.

## 5. Cache TTL: luôn đặt giới hạn thời gian có ý nghĩa bảo mật

Với một token active:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

Một cache TTL cơ bản:

~~~text
effectiveTtl = min(
    configuredPositiveMaxTtl,
    tokenExpiration - now - safetyMargin
)
~~~

Nếu không có `exp` hoặc response có metadata thời gian không dùng được, lựa chọn bảo thủ là **không cache thành công** nhưng vẫn có thể gộp các requests đang chờ chung một lời introspection.

### 5.1. Ví dụ chọn TTL

| Token / chính sách | Positive max TTL | Token còn hạn | TTL cache tối đa trước safety margin |
| --- | --- | --- | --- |
| API đọc dữ liệu ít nhạy cảm | 10 giây | 15 phút | 10 giây |
| API đọc dữ liệu ít nhạy cảm | 10 giây | 3 giây | 3 giây |
| API quản trị nhạy cảm | 0 giây | 15 phút | Không tái sử dụng kết quả đã hoàn tất. |
| Không có `exp` nhưng contract cho phép | Policy đặc biệt | Không biết | Không cache theo mặc định an toàn. |
| Token đã hết hạn | 10 giây | 0 giây | 0 giây; token cần bị từ chối theo validator/issuer contract. |

**Các con số chỉ là ví dụ đánh đổi**, không phải giá trị chuẩn của RFC 7662 hay Spring Security. Hệ thống phải xác định **revocation SLA**: một token bị thu hồi được phép tiếp tục được chấp nhận tối đa bao lâu trong thiết kế? TTL không nên vượt giới hạn đó.

### 5.2. Cần phân biệt cache TTL với expiration của Access Token

Một token có `exp` sau 30 phút không đồng nghĩa cho cache `active:true` 30 phút. Authorization Server có thể revoke token trước `exp`; cache chỉ biết trạng thái tại **lần introspection trước**.

Một kết quả cache active có thể đã cũ:

~~~text
12:00:00 introspect token-A -> active=true; cache TTL 5s
12:00:02 Authorization Server revoke token-A
12:00:03 cache hit -> API có thể vẫn xem token active
12:00:06 cache miss -> introspect -> active=false -> 401
~~~

Thiết kế này chấp nhận một **cửa sổ dùng token đã revoke** tối đa liên quan TTL, network/clock/replication. Không hứa “opaque token revoke là chặn tức thời” khi đã bật positive cache.

### 5.3. Safety margin

Giảm một khoảng nhỏ trước `exp` có thể tránh dùng cache sát hạn do latency và clock differences. Không cộng thêm clock-skew tùy tiện làm token **sống lâu hơn**:

~~~text
ttl = min(maxTtl, exp - now - margin)
~~~

nếu kết quả âm hoặc bằng 0 thì không cache. Nếu Authorization Server đã cam kết `exp` và `active` được đánh giá theo clock policy riêng, cần có cách thống nhất lệch đồng hồ, thay vì biến local cache thành nguồn gia hạn token.

## 6. Không cache mọi kết quả với cùng một chính sách

| Kết quả introspection | Có nên giữ result? | Khuyến nghị |
| --- | --- | --- |
| **`active:true`**, metadata đúng contract | Có thể cache ngắn. | TTL `min(policy, exp)`; resource/audience đúng. |
| **`active:false`** | Có thể negative-cache **rất ngắn** nếu đã đánh giá. | Mặc định không cache lâu; tránh DoS bằng token rác. |
| Introspection timeout / TLS / DNS | **Không** cache như trạng thái token. | Fail closed, metrics/alert; retry có kiểm soát. |
| HTTP 429/503/5xx upstream | **Không** cache như inactive. | Phân loại upstream outage; backoff/circuit breaker. |
| HTTP 401 của introspection client credential | **Không** coi user token invalid. | Điều tra client secret/mTLS/configuration. |
| JSON thiếu `active` hoặc `active:"true"` | **Không** thành principal valid. | Lỗi protocol, sửa integration. |
| Token active nhưng sai audience | **Không** cấp quyền resource này. | Từ chối theo resource policy; không dùng cache của API khác. |
| Active token nhưng local account bị khóa | Token có thể active, domain vẫn từ chối. | Revalidate local account/tenant theo security policy. |

### 6.1. Vì sao error caching gây sự cố?

Nếu viết:

~~~java
Mono<OAuth2AuthenticatedPrincipal> shared =
    delegate.introspect(token).cache();
~~~

và giữ `shared` lâu dài trong registry, một lần lỗi `503` có thể được tái phát cho mọi request sau dù Authorization Server đã hồi phục.

Lỗi `BadOpaqueTokenException` do token inactive cũng khác lỗi transport; **không suy tất cả exceptions đều là active=false**. Với Reactor cache theo TTL, nên đặt **error TTL = 0** nếu chưa có chính sách negative caching tường minh.

### 6.2. Không cache kết quả xác thực độc lập với authorizations

Một `OAuth2AuthenticatedPrincipal` có thể chứa `scope`, `client_id`, `sub`, `aud`. Nhưng việc user có quyền đọc **order 42** có thể thay đổi ngay trong database:

~~~text
Introspection cached: active=true, scope=orders.read
Domain database: quyền đối với order 42 vừa bị thu hồi
~~~

Domain authorization phải kiểm tra dữ liệu hiện thời theo chính sách. Cache introspection **không thay thế** kiểm tra account status, tenant membership, owner/ACL hoặc transaction constraints.

## 7. Thiết kế cache phản ứng với Reactor và Caffeine

Một thiết kế thực dụng trong **một instance**:

1. `Concurrent`/atomic cache lookup theo **HMAC token key**.
2. Khi miss, chỉ tạo **một `Mono` được chia sẻ** cho key đó.
3. Publisher thực hiện `delegate.introspect(token)` **khi subscribe**.
4. `Mono.cache(ttlForValue, ttlForError, ttlForEmpty)` chia sẻ **in-flight work** và chỉ giữ kết quả thành công theo TTL ngắn.
5. Caffeine giới hạn **số entries** và **tuổi entry**, tránh registry phình vô hạn.
6. Timeout của HTTP introspection nằm **bên trong shared source**, để một lời gọi treo không giữ hàng loạt subscribers quá lâu.

Thư viện:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'com.github.ben-manes.caffeine:caffeine'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Spring Boot dependency management thường quản lý các phiên bản tương thích cho những dependency phổ biến; nếu dự án khóa phiên bản riêng, cần chọn Caffeine/Reactor/Spring Security tương thích.

### 7.1. TokenCacheKey: sinh fingerprint bằng HMAC

Ví dụ Java:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class TokenCacheKey {

    private final byte[] hmacSecret;
    private final String namespace;

    public TokenCacheKey(byte[] hmacSecret, String namespace) {
        if (hmacSecret == null || hmacSecret.length < 32) {
            throw new IllegalArgumentException(
                "Use a randomly generated HMAC secret of at least 32 bytes");
        }
        if (namespace == null || namespace.isBlank()) {
            throw new IllegalArgumentException(
                "Trusted introspection namespace required");
        }
        this.hmacSecret = hmacSecret.clone();
        this.namespace = namespace;
    }

    public String forToken(String token) {
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("Token is empty");
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(
                new SecretKeySpec(hmacSecret, "HmacSHA256"));

            mac.update(
                namespace.getBytes(StandardCharsets.UTF_8));
            mac.update((byte) 0); // Phân tách namespace và token

            byte[] digest = mac.doFinal(
                token.getBytes(StandardCharsets.UTF_8));

            return HexFormat.of().formatHex(digest);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "HMAC-SHA256 is unavailable", ex);
        }
    }
}
~~~

**Điều kiện sử dụng thực tế:**

- `hmacSecret` phải là **secret ngẫu nhiên**, đọc từ secret manager/configuration an toàn, không tạo từ password ngắn hoặc client input.
- `namespace` do server cấu hình, ví dụ `"issuer-demo|orders-api|rs-client-v1"`, không lấy từ Bearer header.
- Mỗi lần gọi tạo `Mac` riêng vì `Mac` không an toàn để chia sẻ tùy ý giữa threads.
- Không log digest/token trong production.
- HMAC key không phải công cụ mã hóa token trong heap; các đoạn reactive code vẫn có thể giữ raw token trong closure trong một khoảng thời gian.

### 7.2. SingleFlightCachingIntrospector

Ví dụ sau là một **`ReactiveOpaqueTokenIntrospector` decorator**. `delegate` phải là introspector chuẩn đã xác minh `active`; cache không được thay thế bước đó.

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class SingleFlightCachingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final Duration MAX_POSITIVE_TTL =
        Duration.ofSeconds(5);
    private static final Duration UPSTREAM_TIMEOUT =
        Duration.ofSeconds(2);

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final TokenCacheKey cacheKeys;
    private final Clock clock;

    // Caffeine quản lý một registry dùng chung cho cả instance.
    private final Cache<String, Mono<OAuth2AuthenticatedPrincipal>>
        entries = Caffeine.newBuilder()
            .maximumSize(20_000)
            .expireAfterWrite(Duration.ofSeconds(5))
            .build();

    public SingleFlightCachingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            TokenCacheKey cacheKeys,
            Clock clock) {
        this.delegate = Objects.requireNonNull(delegate);
        this.cacheKeys = Objects.requireNonNull(cacheKeys);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        if (token == null || token.isBlank()) {
            return Mono.error(new BadOpaqueTokenException(
                "Bearer token is missing"));
        }

        return Mono.defer(() -> {
            // Chỉ lookup registry khi có subscription.
            String key = cacheKeys.forToken(token);

            Mono<OAuth2AuthenticatedPrincipal> shared =
                entries.get(key, ignored ->
                    Mono.defer(() -> delegate.introspect(token))
                        // Timeout nằm bên trong nguồn được chia sẻ.
                        .timeout(UPSTREAM_TIMEOUT)
                        // Coalesce cùng một in-flight subscription.
                        // Success cache ngắn, errors/empty không giữ.
                        .cache(
                            this::positiveTtl,
                            error -> Duration.ZERO,
                            () -> Duration.ZERO));

            return shared;
        });
    }

    private Duration positiveTtl(
            OAuth2AuthenticatedPrincipal principal) {

        // RFC 7662: exp thường ở dạng NumericDate;
        // Spring converter có thể biểu diễn thành Instant.
        Object raw = principal.getAttribute("exp");
        Instant expiresAt;

        if (raw instanceof Instant instant) {
            expiresAt = instant;
        } else if (raw instanceof Number seconds) {
            expiresAt =
                Instant.ofEpochSecond(seconds.longValue());
        } else {
            // Không có exp theo contract: không lưu result lâu.
            return Duration.ZERO;
        }

        Duration remaining = Duration.between(
            clock.instant().plusSeconds(1), expiresAt);

        if (remaining.isNegative() || remaining.isZero()) {
            return Duration.ZERO;
        }
        return remaining.compareTo(MAX_POSITIVE_TTL) < 0
            ? remaining : MAX_POSITIVE_TTL;
    }
}
~~~

**Phân tích quyết định trong code:**

1. `Mono.defer` giúp registry lookup và tạo source theo **subscription**, không thực hiện network work tại assembly.
2. `entries.get(key, mappingFunction)` của Caffeine **đồng bộ hóa phép tạo value theo key**, để nhiều cache miss cùng lúc không tạo nhiều `Mono` khác nhau trong một instance.
3. `Mono.defer(() -> delegate.introspect(token))` giữ lời gọi delegate trong reactive chain.
4. `timeout(2s)` giới hạn thời gian introspection call; nó không biến timeout thành `active:false`.
5. `Mono.cache(valueTtl, errorTtl, emptyTtl)` **chia sẻ in-flight source** và chỉ giữ kết quả thành công trong thời gian do `positiveTtl` quyết định. Error và empty có TTL bằng 0.
6. `expireAfterWrite(5s)` của Caffeine đặt giới hạn lưu **entry chứa Mono** kể từ lúc tạo, còn `positiveTtl` đặt giới hạn giữ **signal của Publisher** kể từ lúc kết thúc. Cả hai ràng buộc thời gian theo cách bảo thủ.
7. `maximumSize` giúp registry không phình vô hạn khi có nhiều token khác nhau; eviction có thể tạo một lời introspection mới cho cùng token, được chấp nhận theo trade-off.

**Giới hạn của ví dụ:** cơ chế này **gộp best-effort trong một JVM instance**, không đảm bảo tuyệt đối “đúng một call” nếu entry bị eviction/hết TTL trong khi upstream còn chạy, có instance khác, hoặc request đến sát thời điểm hết hạn. Timeout 2s nhỏ hơn thời gian giữ entry 5s giúp giảm một loại overlap nhưng không tạo phân tán lock. Không dùng nó làm bằng chứng về exactly-once processing.

### 7.3. Vì sao không cache lỗi quá thời gian thực?

Nếu Authorization Server trả `active:false`, delegate chuẩn phát lỗi, ví dụ `BadOpaqueTokenException`. Nhờ:

~~~java
.cache(
    this::positiveTtl,
    error -> Duration.ZERO,
    () -> Duration.ZERO)
~~~

những subscribers **đang chờ cùng một call** có thể cùng nhận lỗi, nhưng lần subscribe sau sẽ có cơ hội thực hiện introspection mới. Điều này tránh **negative caching lâu** và tránh giữ lỗi 503 trong cache.

Tuy nhiên, nếu một client gửi liên tục token sai ở tốc độ cao, không cache negative results sẽ tạo nhiều introspection calls theo thời gian. Giải pháp là **rate-limit, quota, WAF, bounded concurrency** và — nếu thật sự cần — một chính sách negative TTL cực ngắn **chỉ cho lỗi xác định inactive**, không trộn với network outages.

### 7.4. Thận trọng với raw token bị capture trong Mono

Trong:

~~~java
Mono.defer(() -> delegate.introspect(token))
~~~

lambda **giữ tham chiếu tới chuỗi raw token** cho đến khi Publisher và closure có thể được giải phóng. Dù cache key chỉ là HMAC, cache entry chứa Mono có thể khiến token tồn tại trong heap trong vài giây.

Đối với hệ thống có yêu cầu nghiêm ngặt về lưu credential:

- Dùng TTL rất ngắn và cache tối thiểu.
- Giới hạn heap dump và instrumentation.
- Không giữ references đến Publisher lâu sau khi cần.
- Cân nhắc **in-flight registry với cleanup tường minh** hoặc cache kết quả không giữ closure chứa raw token.
- Xem xét rủi ro token secret ở memory theo mô hình bảo mật của tổ chức.

HMAC cache key chỉ giảm rủi ro lộ token **qua cache key**, không loại bỏ mọi bản sao token khỏi bộ nhớ.

## 8. Tích hợp với Spring Security WebFlux

### 8.1. Cấu hình introspection endpoint

Trong `application.yml` cho WebFlux opaque token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Ý nghĩa:

- `introspection-uri`: HTTPS endpoint của Authorization Server được server tin cậy.
- `client-id` và `client-secret`: credentials của **Resource Server khi introspect**, không phải Access Token của user.
- `active` phải được validate bằng delegate chuẩn, không chỉ nhìn HTTP 200.

Không commit client secret vào source control. Nếu dùng mTLS hoặc phương thức introspection authentication khác Basic, cấu hình HTTP client và reactive introspector theo contract thực tế.

### 8.2. Bọc delegate thành bean

Ví dụ khi cần tự cấu hình decorator:

~~~java
import java.time.Clock;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

@Configuration
public class ReactiveIntrospectionConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${app.introspection.uri}") String uri,
            @Value("${app.introspection.client-id}") String clientId,
            @Value("${app.introspection.client-secret}") String secret,
            @Value("${app.introspection.cache-key-base64}") String key64) {

        ReactiveOpaqueTokenIntrospector delegate =
            new NimbusReactiveOpaqueTokenIntrospector(
                uri, clientId, secret);

        byte[] hmacSecret = Base64.getDecoder().decode(key64);
        TokenCacheKey keys = new TokenCacheKey(
            hmacSecret,
            "issuer-demo|orders-api|rs-client-v1");

        return new SingleFlightCachingIntrospector(
            delegate, keys, Clock.systemUTC());
    }
}
~~~

Cấu hình tương ứng:

~~~yaml
app:
  introspection:
    uri: https://identity.example.test/oauth2/introspect
    client-id: orders-resource-server
    client-secret: ${INTROSPECTION_CLIENT_SECRET}
    # Giá trị base64 của >=32 byte random, lấy từ secret manager.
    cache-key-base64: ${INTROSPECTION_CACHE_HMAC_KEY_BASE64}
~~~

**Đây là phương án tự cấu hình thay thế:** khi khai báo bean `ReactiveOpaqueTokenIntrospector` tùy chỉnh, Spring Boot auto-configuration có thể nhường chỗ cho bean đó. Do vậy URL và credentials của delegate phải thực sự được lấy từ các thuộc tính `app.introspection.*` hoặc cơ chế cấu hình tương đương. Không nghĩ rằng Boot vẫn tự inject các thuộc tính `spring.security.oauth2.resourceserver.opaque-token.*` vào bean tự tạo.

Lớp `NimbusReactiveOpaqueTokenIntrospector` và constructor trên có trong nhiều bản Spring Security 6.x; ở bản mới hơn có thể có triển khai/builder khác. Chọn API introspector **của phiên bản dự án** và giữ các điều kiện bảo mật như nhau. Khi cần timeout cụ thể hơn cho connect/read, cấu hình `WebClient`/HTTP client mà delegate dùng; `Mono.timeout` ngoài cùng là giới hạn tổng thể, không thay mọi network timeout/config.

### 8.3. SecurityWebFilterChain cho API nhận opaque token

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // Ví dụ API thuần Bearer header, không dùng session cookie
            // để xác thực. Cấu hình CSRF riêng nếu có web login.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(
                    HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(
                    HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Spring Security sẽ dùng reactive introspector bean phù hợp với configuration. Nếu introspection thành công, principal/authorities được dùng để tạo Authentication cho **mỗi request**. Cache không được bỏ qua `authorizeExchange`, method security hoặc resource-level authorization.

Ví dụ dùng:

~~~text
GET /api/orders/42
Bearer token đã introspect active=true
Authority SCOPE_orders.read
        |
        v
HTTP policy pass
        |
        v
Domain policy kiểm tra order 42 thuộc user/tenant
~~~

Một kết quả cache active không chứng minh quyền của user đối với order cụ thể đã không thay đổi.

## 9. Caching và Reactor Context không được trộn lẫn

Trong WebFlux, Spring Security sử dụng **Reactor Context** để truyền `SecurityContext` theo subscription. Đọc current user đúng cách:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication());
~~~

Nhưng **không cache `ReactiveSecurityContextHolder.getContext()` vào biến global**:

~~~java
// KHÔNG LÀM trong singleton:
private final Mono<SecurityContext> cachedContext =
    ReactiveSecurityContextHolder.getContext().cache();
~~~

Nếu publisher đó được subscribe dưới context của user A rồi cache kết quả, request user B có thể nhận **SecurityContext của A**. Đây là nguy cơ rất nghiêm trọng.

### 9.1. Cache token metadata, không cache current user

Khác biệt:

| Dữ liệu | Cache theo token và TTL ngắn? | Cảnh báo |
| --- | --- | --- |
| Metadata introspection của token cụ thể | Có thể, khi đúng chính sách. | Key theo token fingerprint, giới hạn revocation window. |
| `SecurityContext` hiện tại | **Không** cache liên request. | Mỗi subscription có principal riêng. |
| `ServerWebExchange` | **Không**. | Request/response lifecycle riêng. |
| HTTP Authorization header | **Không** dưới dạng giá trị cache công khai. | Bearer secret; chỉ delegate cần nhận token. |
| Quyền owner/tenant của record | Cache domain riêng nếu thực sự cần. | Phải có invalidation và dữ liệu/identity key đúng. |
| JWKS public key cho JWT | Bài toán cache khác. | Không thay introspection/cảnh báo revoke của opaque token. |

### 9.2. Introspector chuẩn lý tưởng không cần request SecurityContext

Một `ReactiveOpaqueTokenIntrospector` nhận **token string** và dùng **cấu hình đáng tin cậy** để gọi Authorization Server. Nó nên diễn giải token dựa trên client credentials/introspection endpoint được cấu hình, không dựa vào “current HTTP user” đọc từ `ReactiveSecurityContextHolder` trước lúc authentication.

Nếu custom introspector phụ thuộc Reactor Context của request, cần xét kỹ cách `Mono.cache()` **chia sẻ một upstream subscription giữa nhiều callers**. Upstream có thể thấy context của **subscriber kích hoạt đầu tiên**, trong khi subscriber tiếp theo khác context. Nếu kết quả introspection thực sự thay đổi theo tenant/resource, **đưa ngữ cảnh đã kiểm chứng vào cache key hoặc tách introspector policy**, không dùng context ngầm rồi coalesce mọi request cùng token.

### 9.3. Thread scheduling và detached subscriptions

`publishOn` và `subscribeOn` thay thread thực thi theo semantics Reactor nhưng **subscriber context vẫn được truyền trong một pipeline được compose đúng**. Ngược lại:

~~~java
// KHÔNG LÀM.
delegate.introspect(token).subscribe();
return Mono.empty();
~~~

tạo **subscription riêng**, có thể mất request context, quản lý lỗi kém và không liên kết với cancellation của request chính. Trong Spring WebFlux hãy **trả Publisher**, để framework subscribe; trong cache loader dùng `Mono.defer` và `cache` có chủ đích, không `block()` hoặc tự `subscribe()`.

## 10. Cancellation: một subscriber hủy có làm hủy introspection chung?

Giả sử 20 HTTP requests đang cùng chờ một shared introspection `Mono`:

~~~text
Request A ----\
Request B -----\
Request C ------> shared introspection Mono ---> Authorization Server
Request D -----/
...         ---/
~~~

Nếu A đóng tab/hủy request giữa chừng, nhưng B/C/D vẫn cần kết quả, một thiết kế single-flight thường **không muốn tự hủy upstream vì A bỏ đi**. `Mono.cache()` phù hợp ở chỗ: sau khi đã được subscribe và khởi động source, cache operator giữ upstream subscription cho kết quả và có thể phát lại cho những người chờ khác.

**Hệ quả:** ngay cả khi **tất cả** HTTP request subscribers cancel, upstream introspection có thể tiếp tục chạy cho đến khi hoàn tất/timeout. Vì vậy cần:

- **Timeout ở shared source**.
- Giới hạn số introspection calls đồng thời toàn instance.
- Caffeine `maximumSize` và TTL bounded.
- Metrics về in-flight calls và upstream latency.
- Không giữ credential trong closure lâu hơn cần thiết.

### 10.1. Mono.cache và Mono.share không giống nhau

Ở Reactor 3.x có các operators với semantics khác nhau:

| Cách dùng | Hành vi chính | Đánh đổi |
| --- | --- | --- |
| `source.cache()` | Lưu terminal signal trong vòng đời object. | Dễ giữ success/error vô hạn. |
| `source.cache(Duration)` | Cache terminal signal trong TTL cố định. | Cùng TTL cho success/error; cần cân nhắc outage. |
| `source.cache(valueTtl, errorTtl, emptyTtl)` | Phân biệt thời gian cache theo outcome. | Tốt hơn khi cần success ngắn, error/empty bằng 0. |
| `source.share()` | Chia sẻ một in-flight task theo semantics của Mono share. | Khi tất cả subscribers hủy, source có thể bị hủy; cache replay khác cache(). |
| `source.publish().refCount(...)` | Chia sẻ nguồn theo số subscribers của Flux. | Cần hiểu cancellation/reconnection; không thay cache policy. |

Không có operator “tốt nhất cho mọi trường hợp”. Với introspection, chọn theo yêu cầu **gộp requests, timeout, rủi ro revoke và chi phí upstream**, rồi kiểm thử behavior đúng với phiên bản Reactor.

### 10.2. Cancellation không phải lý do trả token active

Nếu introspection đang chờ mà request cancel, không thể tạo `OAuth2AuthenticatedPrincipal` bằng fallback chỉ để giữ luồng chạy. Nếu request sau đến cùng token, nó phải dùng một kết quả đã thực sự được xác thực theo cache policy hoặc introspect lại.

Đặc biệt không viết:

~~~java
// KHÔNG LÀM: lỗi timeout/network không được cấp quyền.
return delegate.introspect(token)
    .onErrorResume(error ->
        Mono.just(makeAdminPrincipal()));
~~~

Ngay cả lỗi `BadOpaqueTokenException` báo token inactive cũng phải được tôn trọng; không catch mọi exception và biến thành `active:true`.

## 11. Retry, circuit breaker và thundering herd

### 11.1. Retry trước hay sau cache?

Nếu thêm retry:

~~~java
delegate.introspect(token)
    .retryWhen(...)
    .cache(...)
~~~

thì các subscribers có thể chia sẻ **một chuỗi upstream có retry**; nhưng retry có thể làm **nhiều HTTP calls** cho cùng token. Single-flight không có nghĩa upstream được gọi “đúng một lần” nếu đã cho phép retry.

Nguyên tắc:

- **Không retry** `active:false` hoặc lỗi invalid token theo nghĩa bảo mật.
- Chỉ retry một số lỗi **transient** đã phân loại, ví dụ timeout/HTTP 503, với giới hạn tổng thời gian.
- Bounded exponential backoff và jitter khi cần để tránh bão retry.
- Không retry HTTP 401 do introspection client secret/mTLS sai vô hạn.
- Không nuốt exception rồi trả một principal mặc định.
- Đặt retry budget dưới deadline của API để không khiến request treo quá lâu.

Khi muốn thêm `Retry` từ Reactor, dùng `filter` chỉ chấp nhận **những exception của upstream network đã biết**. Không đặt một `retry(3)` mù quáng quanh toàn bộ authentication, vì nó có thể retry token chắc chắn invalid, gây tải lớn và khiến authentication latency tăng.

### 11.2. Thundering herd khi TTL hết đồng loạt

Nếu một token T rất phổ biến và cache TTL 5 giây:

~~~text
T0: 2.000 requests dùng cache hit
T0+5s: Cache entry hết hạn
T0+5.001s: 400 requests đồng thời nhìn thấy cache miss
~~~

Một **atomic cache get** kết hợp **shared Mono** làm giảm 400 upstream calls thành khoảng một call **trên mỗi instance**, nếu cache entry không bị eviction và đúng namespace.

Nhưng nếu có 20 instances, mỗi instance vẫn có thể introspect cùng T một lần: **20 calls**, không phải một call toàn cluster. Nếu cần giảm tải toàn cụm, cân nhắc distributed cache hoặc giới hạn đồng thời toàn cụm, với trade-off security rõ ràng.

### 11.3. Bounded concurrency

Không nên để hàng chục nghìn token khác nhau đều tạo introspection calls đồng thời. Single-flight chỉ gộp **cùng token key**, còn token khác nhau vẫn gây tải.

Cần các lớp giới hạn:

- Rate limits ở edge/gateway theo client/IP và chính sách.
- Connection pool + max concurrent upstream requests.
- Timeout cho connect, response và tổng introspection.
- Bulkhead/circuit breaker với lỗi upstream.
- Caffeine maximum size và eviction.
- Metrics/alerts cho authentication latency, 429/5xx và số requests đang chờ.

Nếu bộ giới hạn bão hòa, **fail closed** hoặc trả lỗi dịch vụ theo contract; không bypass authentication để bảo toàn throughput.

## 12. Lỗi upstream và phân biệt 401/403

Một cache layer không được làm mất ranh giới giữa xác thực và phân quyền.

| Điều kiện | Kết luận | HTTP thường gặp |
| --- | --- | --- |
| Không có Bearer token | Chưa xác thực. | **401**, Bearer challenge. |
| Introspection trả `active:false` | Token không được chấp nhận. | **401 invalid_token** khi handler tương ứng. |
| Introspection timeout/503 | Không thể xác minh credential. | **Fail closed**; status có thể 5xx/503 theo handler. |
| Token active, thiếu `SCOPE_orders.read` | Authenticated nhưng thiếu quyền endpoint. | **403 insufficient_scope** trong trường hợp OAuth scope. |
| Token active, scope đủ nhưng sai owner/tenant | Domain policy từ chối. | **403/404**, không nhất thiết insufficient_scope. |
| Token được cache active nhưng đã revoke upstream | Cửa sổ staleness của positive cache. | Có thể đi tiếp trong TTL; cần rủi ro được chấp thuận. |

**Không lấy HTTP status của introspection endpoint làm HTTP status của API một cách máy móc.** Ví dụ Authorization Server trả **HTTP 401** khi Resource Server dùng client secret sai là lỗi **credential của Resource Server**, không chứng minh user token đã hết hạn.

### 12.1. Không dùng stale-on-error cho token một cách vô thức

Một cache HTTP bình thường có thể phục vụ **stale data khi upstream lỗi**. Đối với token introspection, logic:

~~~text
Introspection 503 -> dùng active=true cũ dù TTL đã hết
~~~

có thể phá giới hạn revocation window. Nếu muốn có **stale-while-revalidate** hoặc fallback cache khi IdP outage, đó phải là **security policy độc lập được phê duyệt**, với giới hạn tuổi tuyệt đối, loại endpoint và rủi ro rõ; không phải mặc định an toàn. Với endpoint nhạy cảm, chọn **không chấp nhận token khi không thể xác minh**.

### 12.2. Phân biệt error metrics

Nên tách:

~~~text
introspection_success_active
introspection_token_inactive
introspection_timeout
introspection_http_401_client_credentials
introspection_http_429_rate_limited
introspection_http_503
introspection_invalid_json
authorization_insufficient_scope
authorization_domain_denied
~~~

Không đưa raw token/HMAC digest làm metric label. Lưu request correlation ID theo chính sách bảo mật, không log HTTP request body introspection chứa token hoặc Basic Authorization client secret.

## 13. Nhiều replicas: cache cục bộ và cache phân tán

### 13.1. Cache cục bộ theo JVM

Ưu điểm:

- Không thêm network dependency cho cache.
- Caffeine lookup nhanh và atomic theo key trong một instance.
- Không lưu token result vào Redis/shared database.
- Dễ giới hạn memory và cache lifetime.

Nhược điểm:

- Mỗi replica có cache khác nhau.
- Lần đầu dùng một token trên mỗi replica có thể đều gọi introspection.
- Khi revoke, invalidation phải đến **mọi replica** nếu muốn giảm staleness sớm hơn TTL.
- Load balancer phân phối request khiến hit rate thấp hơn khi token ít được lặp lại trên cùng replica.

Đó là lý do **single-flight trong một process không thể hứa exactly-once toàn hệ thống**.

### 13.2. Distributed cache cần thêm ranh giới bảo mật

Nếu dùng Redis/distributed cache, cần xem xét:

1. **Encryption in transit và at rest** theo chính sách.
2. Không dùng raw Access Token như key được ghi log/monitoring.
3. Namespace gồm issuer/introspection client/resource và phiên bản policy.
4. TTL tuyệt đối không vượt token expiration/revocation SLA.
5. Cách invalidation đến các nodes khi token revoke hoặc client policy thay đổi.
6. Tránh lẫn metadata của các token khác nhau hoặc các Authorization Servers.
7. Không bỏ qua kiểm tra `active`, audience, token type, scope và domain policy.
8. Distributed lock/single-flight có lease và fencing thích hợp, nếu thật sự cần, để không kẹt khi instance chết.
9. Outage cache không được biến thành cho phép token không xác thực.
10. Giới hạn quyền truy cập cache và dữ liệu PII trong introspection response.

**Phân tán cache không phải mặc định tốt hơn**. Với introspection, nhiều hệ thống chọn local cache rất ngắn + single-flight + upstream rate limits để giới hạn rủi ro, thay vì một distributed cache phức tạp chứa authentication metadata.

### 13.3. Key theo resource và policy

Ví dụ cùng token T:

~~~text
orders-api introspection:
  active=true, aud=orders-api, scope=orders.read

billing-api introspection:
  active=false (không thuộc audience/quyền introspect)
~~~

Nếu distributed cache chỉ keyed bằng token digest mà không phân biệt **resource identity**, billing-api có thể dùng nhầm active result của orders-api. Do đó key/policy cần namespace rõ, và **mỗi Resource Server phải tự đánh giá audience/resource tương ứng**.

## 14. Test single-flight với Reactor Test

Trước khi test Spring Security HTTP, có thể kiểm tra trực tiếp **nhiều subscribers dùng một shared Mono**. Ví dụ JUnit 5:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReactorSingleFlightTest {

    @Test
    void concurrentSubscribersShareOneUpstreamSubscription() {
        AtomicInteger upstreamSubscriptions =
            new AtomicInteger();
        Sinks.One<String> gate = Sinks.one();

        Mono<String> source = Mono.defer(() -> {
            upstreamSubscriptions.incrementAndGet();
            return gate.asMono();
        });

        Mono<String> shared = source.cache();
        List<String> results = new CopyOnWriteArrayList<>();

        // Cả hai subscriptions đã đăng ký,
        // nguồn vẫn chưa emit terminal signal.
        shared.subscribe(results::add);
        shared.subscribe(results::add);

        assertEquals(1, upstreamSubscriptions.get());

        gate.tryEmitValue("active");
        assertEquals(
            List.of("active", "active"), results);
    }
}
~~~

Test này minh họa **`Mono.cache()` chia sẻ một in-flight source**. Nó không chứng minh TTL/revocation hay behavior của Spring Security, và dùng `cache()` không TTL chỉ trong phạm vi local test object.

### 14.1. Test TTL thành công và lỗi không bị cache lâu

Với Caffeine/decorator ở mục 7, cần những trường hợp:

| Test | Điều cần chứng minh |
| --- | --- |
| Hai subscriptions cùng token lúc source chưa trả lời | Delegate chỉ được subscribe một lần trong một instance. |
| Hai subscriptions **khác token** | Delegate được gọi riêng, không lẫn principal/authorities. |
| Token active và `exp` còn xa | Kết quả được chia sẻ trong TTL cấu hình. |
| Token gần `exp` | TTL không kéo dài sau `exp`. |
| Response không có `exp` | Với policy ví dụ, không cache kết quả sau completion. |
| Introspection `active:false` | Các subscribers đang chờ cùng nhận lỗi; không trở thành principal. |
| Upstream 503/timeout | Không cache lỗi dài hạn; lần sau có cơ hội thử lại. |
| Tạo hơn `maximumSize` tokens | Cache vẫn bounded, có eviction. |
| Có `retryWhen` | Số HTTP introspection calls phản ánh retry policy; không retry inactive. |
| Subscriber A hủy, B vẫn chờ | Kết quả tới B theo behavior của shared source. |
| Tất cả subscribers hủy | Shared source vẫn có timeout; không treo mãi. |

### 14.2. Test với fake ReactiveOpaqueTokenIntrospector

Ví dụ fixture mô phỏng introspection chậm:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

AtomicInteger calls = new AtomicInteger();
Sinks.One<OAuth2AuthenticatedPrincipal> gate = Sinks.one();

ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return gate.asMono();
    });

OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "person-A",
        Map.of(
            "sub", "person-A",
            "scope", "orders.read",
            "exp", Instant.now().plusSeconds(60)),
        List.of(new SimpleGrantedAuthority(
            "SCOPE_orders.read")));

// Sau đó tạo SingleFlightCachingIntrospector với
// tokenKey HMAC key test và Clock.systemUTC().
// Hai subscriptions của cùng opaque token
// cùng chờ gate.asMono(), rồi:
gate.tryEmitValue(principal);
// assert: calls == 1, cả hai nhận principal.
~~~

Đoạn này là **fixture minh họa**, không phải một test method có tất cả assertions. HMAC secret fixture cần được sinh riêng trong test; không sao chép secret production. `Mono.defer` bảo đảm `calls` tăng khi thật sự subscribe vào delegate, không phải khi Java tạo lambda.

### 14.3. Test lỗi không được cache

Một fake delegate có thể trả:

~~~java
AtomicInteger calls = new AtomicInteger();

ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.defer(() -> {
        int attempt = calls.incrementAndGet();
        if (attempt == 1) {
            return Mono.error(
                new RuntimeException("simulated timeout"));
        }
        return Mono.just(testPrincipal());
    });
~~~

`testPrincipal()` ở đây là helper test trả `OAuth2AuthenticatedPrincipal` hợp lệ cho fixture. Khi chạy qua cache có `errorTtl=Duration.ZERO`, lần đầu phải nhận lỗi; lần sau có thể gọi delegate lại và nhận thành công. **Không** dùng logic thay lỗi timeout bằng user có quyền admin.

Trong test production-like, dùng exception loại cụ thể của HTTP client/introspection để kiểm tra phân loại lỗi. Một `RuntimeException("simulated timeout")` chỉ giúp minh họa không cache error signal.

## 15. Test Spring WebFlux HTTP với WebTestClient

`spring-security-test` hỗ trợ test reactive security. Ví dụ:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

webTestClient
    .mutateWith(mockOpaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

**`mockOpaqueToken()` tạo Authentication giả**, không gửi HTTP introspection và không test `active`. Nó phù hợp để test **`authorizeExchange`** hoặc domain policy khi có fixture order 42. Nếu không có controller hoặc không có dữ liệu, status thực tế có thể là 404 thay vì 200 dù authorization cho phép.

### 15.1. Test introspection thật bằng mock Authorization Server

Để test cache/single-flight **đúng ranh giới HTTP**, cần fake introspection endpoint:

~~~text
POST /oauth2/introspect
token=active-reader
  -> HTTP 200
     {"active":true,"scope":"orders.read",
      "sub":"person-A","aud":["orders-api"],"exp":...}

token=inactive
  -> HTTP 200 {"active":false}

token=upstream-503
  -> HTTP 503 Service Unavailable
~~~

Quy trình:

1. Dựng WireMock/MockWebServer hoặc một HTTP server cục bộ cho test.
2. Cấu hình **`ReactiveOpaqueTokenIntrospector` thật** trỏ tới test endpoint.
3. Gửi `Authorization: Bearer active-reader` qua **WebTestClient**, **không dùng `mockOpaqueToken()`**.
4. Gửi nhiều requests song song với cùng token; ghi số lần mock introspection endpoint nhận POST.
5. Kiểm tra số calls giảm theo single-flight/cache policy và principal/scope đúng.
6. Đổi phản hồi thành `active:false`, đợi hết TTL theo đồng hồ test hoặc chính sách, rồi xác nhận **401**.
7. Test token khác nhưng cùng `sub` có scope khác; không được lẫn authorities.
8. Test timeout/503 và credentials introspection sai; không được cho request chạy như authenticated.

**Lưu ý:** test HTTP localhost không TLS chỉ phù hợp môi trường kiểm thử cô lập. Kết nối production tới Authorization Server phải dùng HTTPS và certificate/hostname verification đúng.

### 15.2. Ma trận HTTP 401/403

| Trạng thái | Kết quả |
| --- | --- |
| No Bearer token tới endpoint cần authentication | **401**. |
| Introspection trả `active:false` | **401 invalid_token** khi handler phù hợp. |
| Introspection active nhưng thiếu `orders.read` | **403**. |
| Introspection active có `orders.read`, order thuộc tenant khác | **403/404** theo domain policy. |
| Token đang cache active, vừa bị revoke upstream | Có thể tạm được nhận trong TTL; cần test giới hạn. |
| Token revoked, sau cache TTL | Phải introspect lại và từ chối. |
| Introspection service 503 | Fail closed; status lỗi vận hành phụ thuộc handler, không được là authorization success. |

## 16. Quan sát hiệu năng mà không làm lộ dữ liệu

Nên theo dõi:

- **Cache hit rate**: số lần dùng lại kết quả cache so với cache lookup.
- **Single-flight deduplication ratio**: số caller chờ chung so với số upstream introspection calls.
- **Introspection request rate** và latency p50/p95/p99.
- **In-flight upstream requests** và số timeouts.
- **Cache size**, eviction count và allocation/memory.
- **401 inactive**, **403 insufficient_scope**, lỗi credential của Resource Server và upstream 429/503.
- Độ trễ revocation có thể quan sát được trong bài test/kiểm tra vận hành.

**Không gắn token hoặc HMAC digest vào metric labels**. Những giá trị có cardinality cao làm tăng chi phí và có thể tiết lộ thông tin định danh/credential. Dùng nhóm lỗi, endpoint logical name, issuer cấu hình và region/node IDs phù hợp thay thế.

### 16.1. Tránh một tối ưu làm tăng tải

Nếu introspection timeout được cấu hình quá dài (ví dụ 60 giây) và nhiều tokens khác nhau đều cache miss, hệ thống có thể chứa hàng chục nghìn pending requests, giữ kết nối HTTP và bộ nhớ. Single-flight chỉ giúp **một token lặp lại**; nó không thay max in-flight limits, timeouts, quotas và circuit breakers.

### 16.2. Đo trước khi chọn TTL

Các câu hỏi thực tế:

1. Một Access Token trung bình được dùng bao nhiêu requests mỗi giây?
2. Có bao nhiêu **unique tokens** cùng hoạt động?
3. Độ trễ HTTP introspection trung bình và p99 là bao nhiêu?
4. Authorization Server cho phép bao nhiêu QPS / resource client?
5. Revocation phải phản ánh trong bao lâu?
6. API có thao tác nhạy cảm nào không nên dùng cache active?
7. Có bao nhiêu replicas và load balancer có phân phối đồng đều không?

Từ số liệu đó, cân đối cache TTL nhỏ, single-flight per node, rate limit và sức chịu tải của Authorization Server. Không chọn TTL lớn chỉ để che giấu một introspection endpoint đang lỗi/thiếu tài nguyên.

## 17. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `delegate.introspect(token).cache()` mới ở mỗi HTTP request. | Mỗi request vẫn tạo Mono riêng, **không gộp cross-request**. | Dùng registry keyed theo token fingerprint. |
| Cache key theo `sub` hoặc `client_id`. | Trộn scope/audience/revocation giữa nhiều tokens. | Key theo token + namespace. |
| Cache `OAuth2AuthenticatedPrincipal` mãi mãi. | Token revoke/expired tiếp tục được chấp nhận. | TTL ngắn, ràng buộc `exp` và revocation SLA. |
| Cache mọi lỗi bằng `Mono.cache()` không TTL. | Outage được phát lại ngay cả khi IdP hồi phục. | Error TTL 0 hoặc policy lỗi riêng. |
| Cache HTTP 503 như `active:false`. | Nhầm upstream failure với token invalid. | Phân loại lỗi, fail closed, metrics riêng. |
| Khi introspection timeout, trả principal mặc định. | **Fail-open** và có thể cấp quyền trái phép. | Không tạo Authentication khi không xác minh được. |
| Dùng raw token trong log hoặc cache metrics. | Rò rỉ Bearer credential. | HMAC token fingerprint, không log khóa/digest. |
| Cho rằng HMAC xóa token khỏi heap. | Lambda cache vẫn có thể giữ raw token. | TTL nhỏ, bounded memory, quản lý heap dumps. |
| Không đưa resource/issuer context vào cache namespace. | Dùng kết quả active của API này tại API khác. | Tách cache theo trust domain và audience. |
| Cache `ReactiveSecurityContextHolder.getContext()` trong singleton. | Rò rỉ Authentication giữa requests. | Cache token metadata, không cache current user context. |
| `subscribe()` thủ công trong loader/controller. | Detached subscription, mất context/error/cancel coordination. | `Mono.defer` và composition, WebFlux subscribe. |
| `block()` để chờ cache future trên event loop. | Chặn event-loop, tăng latency/timeout. | Reactive cache APIs / `Mono`. |
| Cho rằng `Mono.cache` hủy source khi mọi callers cancel. | Upstream có thể vẫn chạy dù không ai chờ. | Shared-source timeout và concurrency bounds. |
| Gọi retry mọi lỗi. | Lặp token inactive/credential sai, tạo tải. | Chỉ retry transient failures với budget. |
| Tưởng single-flight có hiệu lực trên mọi replicas. | Mỗi node vẫn gọi introspection. | Đo QPS toàn cụm, quyết định local/distributed policy. |
| Lấy `active:true` làm quyền xem mọi order. | BOLA/IDOR, cross-tenant access. | Scope + owner/tenant checks độc lập. |
| Chỉ test `mockOpaqueToken()` rồi kết luận cache hoạt động. | Helper bỏ qua introspection thật. | HTTP test server + verify số POST và active transitions. |
| Khi client ngắt kết nối, mặc định cancel upstream đã dừng. | Shared source có thể còn chạy; giữ resources. | Timeout, eviction và cancellation tests. |

## 18. Quy trình áp dụng vào một dự án Resource Server

1. **Xác nhận token contract:** opaque Access Token, introspection endpoint, issuer/resource/audience, `scope`, `exp`, `active` và chính sách revoke.
2. **Cấu hình WebFlux security đúng:** `SecurityWebFilterChain` + `ReactiveOpaqueTokenIntrospector`; HTTP và method authorization vẫn hoạt động cho mỗi request.
3. **Đo traffic thực:** tần suất dùng lại token, unique-token cardinality, request concurrency, introspection latency và error rate.
4. **Chọn revocation SLA:** token active được phép dùng lại trong bao lâu sau khi Authorization Server revoke? TTL không được vượt yêu cầu đó.
5. **Thiết kế cache key an toàn:** fingerprint HMAC token và namespace issuer/resource được server kiểm soát, không key theo user hoặc email.
6. **Gộp cache miss đồng thời:** atomic `Cache.get` trả về một shared `Mono`, dùng `Mono.defer` và `cache` với TTL theo outcome.
7. **Giới hạn result cache:** positive TTL ngắn, không vượt `exp`; lỗi/empty không được cache lâu; bounded max entries.
8. **Phân loại upstream failures:** `active:false` khác timeout/503/client credential 401; mọi lỗi không xác minh được phải fail closed.
9. **Thiết kế cancel và retry:** timeout trong shared source; retry chỉ transient; không gửi hàng loạt calls khi cache stampede.
10. **Tách quyền nghiệp vụ:** local account, tenant, owner và trạng thái order phải được kiểm tra theo dữ liệu hiện thời, không dựa duy nhất vào cached principal.
11. **Kiểm thử single-flight và TTL:** StepVerifier/Sinks để chứng minh một upstream subscription, fake introspector/test HTTP server để đo calls, thử revoked token trước/sau TTL.
12. **Kiểm tra nhiều replicas:** local cache QPS, invalidation và yêu cầu distributed cache nếu thật sự cần, với ranh giới bảo mật riêng.
13. **Bảo vệ observability và secrets:** không log Bearer token/introspection credentials; theo dõi cache/timeout/401/403 bằng metrics không chứa credential.

**Ghi nhớ:** Với **introspection phản ứng**, tối ưu đúng không đơn thuần là thêm `Mono.cache()`. Cần phân biệt **result caching** với **single-flight in-flight deduplication**, tạo **registry theo token identity an toàn**, giữ **TTL ngắn giới hạn bởi `exp` và revocation policy**, **không cache lỗi upstream như kết luận active**, và **không tái sử dụng SecurityContext giữa requests**. `ReactiveOpaqueTokenIntrospector` vẫn là ranh giới xác thực; `authorizeExchange` và domain policy vẫn quyết định quyền trên từng endpoint/tài nguyên.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security — ReactiveOpaqueTokenIntrospector API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html).
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Reactive Security Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html).
- [Project Reactor — Mono API, cache operators](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).
- [Project Reactor — Reactor 3 Reference Guide](https://projectreactor.io/docs/core/release/reference/).
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html).
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html).
- [Caffeine — Java Cache library](https://github.com/ben-manes/caffeine).
- [OWASP — API Security Top 10 (2023)](https://owasp.org/API-Security/editions/2023/en/0x00-header/).
