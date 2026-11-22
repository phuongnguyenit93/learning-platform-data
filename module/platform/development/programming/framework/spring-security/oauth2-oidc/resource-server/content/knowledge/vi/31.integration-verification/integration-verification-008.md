# Cache introspection và thời gian phản ánh token bị thu hồi

Với OAuth 2.0 Opaque Token, Resource Server thường gọi Authorization Server (AS) để introspect access token trước khi tạo Authentication. Mỗi lần gọi introspection đều có chi phí network, latency, tải lên AS và phụ thuộc vào độ sẵn sàng của token endpoint. Cache introspection giúp giảm số lần gọi đó, nhưng tạo ra một đánh đổi bảo mật quan trọng: **một token đã được cache là active có thể tiếp tục được chấp nhận trong một khoảng thời gian sau khi AS thu hồi token**.

Khoảng thời gian này thường được gọi là *revocation propagation delay*, *revocation latency* hoặc *stale authorization window*. Nếu cache TTL là 30 giây, một Resource Server có thể còn chấp nhận token đã bị thu hồi gần 30 giây sau lần introspection active cuối cùng, cộng thêm độ trễ cập nhật trạng thái ở AS, truyền sự kiện invalidation và sai lệch đồng hồ.

Không thể chọn TTL chỉ dựa trên hiệu năng. Cần xác định mức độ rủi ro của endpoint, tuổi thọ token, cách AS thực hiện revocation, số lượng Resource Server instances và khả năng invalidation chủ động. Bài học này giải thích RFC 7662 introspection, cache positive/negative, TTL, Spring Security Servlet/WebFlux, cache phân tán, test và cách vận hành khi token bị thu hồi.

## 1. Introspection là gì?

OAuth 2.0 Token Introspection được định nghĩa trong RFC 7662. Resource Server gửi token tới một endpoint được AS công bố; AS trả về metadata về trạng thái token. Thuộc tính `active` cho biết token có được coi là đang hoạt động hay không.

Một request minh họa:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <RESOURCE_SERVER_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
token_type_hint=access_token
~~~

Response active có thể trông như sau:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "username": "alice",
  "token_type": "Bearer",
  "sub": "alice",
  "aud": ["orders-api"],
  "iss": "https://login.example.test",
  "iat": 1924991700,
  "exp": 1924992000
}
~~~

Các thuộc tính ngoài `active` là tùy theo token profile và chính sách AS. Resource Server phải kiểm tra những thuộc tính cần thiết cho resource của mình, chẳng hạn audience, scope, subject, issuer hoặc thời gian.

Response inactive thường có dạng:

~~~json
{
  "active": false
}
~~~

`active: false` có thể có nghĩa token không tồn tại, hết hạn, bị thu hồi, không được phép introspect bởi client gọi endpoint hoặc không còn hợp lệ theo policy của AS. Resource Server không nên suy luận lý do chi tiết nếu AS không cung cấp.

### 1.1. Luồng request không cache

~~~text
Client
  |
  | Authorization: Bearer <opaque token>
  v
Resource Server
  |
  | POST /introspect
  v
Authorization Server
  |
  | active=true + claims
  v
Resource Server
  |
  | build Authentication
  v
Controller / API
~~~

Nếu Resource Server introspect token trên mỗi request, trạng thái revocation được hỏi lại AS thường xuyên. Đổi lại, mỗi request phụ thuộc vào network và AS, làm tăng latency, chi phí và áp lực lên hạ tầng identity.

### 1.2. Luồng có cache

~~~text
Client
  |
  | Bearer token
  v
Resource Server
  |
  v
Introspection cache
  |
  +-- cache hit, entry còn hạn --> Authentication
  |
  +-- cache miss/expired
          |
          v
      Authorization Server
          |
          v
      Cache active result
          |
          v
      Authentication
~~~

Cache lưu kết quả introspection, thường gồm principal attributes và authorities được tạo từ response. Cache hit có thể bỏ qua network call tới AS. Vì vậy, Resource Server có thể chưa biết token vừa bị thu hồi nếu entry active vẫn còn trong cache.

## 2. Cache thay đổi semantics của revocation như thế nào?

Giả sử Resource Server introspect token T tại thời điểm 10:00:00 và nhận `active=true`. Nó cache kết quả trong 30 giây. AS thu hồi T tại 10:00:05.

~~~text
10:00:00  Introspection(T) → active=true
          Cache T until 10:00:30

10:00:05  AS revokes T

10:00:08  Request with T → cache hit → accepted
10:00:20  Request with T → cache hit → accepted
10:00:29  Request with T → cache hit → accepted

10:00:30  Cache entry expires

10:00:31  Introspection(T) → active=false
          Resource Server rejects T
~~~

Trong ví dụ, token vẫn được chấp nhận khoảng 25 giây sau khi bị thu hồi. Đây là hệ quả có chủ đích của caching, không phải cache bị lỗi.

### 2.1. Revocation không tự động đẩy vào cache

RFC 7009 định nghĩa token revocation endpoint, nhưng một cache riêng trong Resource Server không tự biết AS vừa xử lý revocation request. RFC 7662 cũng không bắt buộc AS phải gửi push notification tới mọi Resource Server khi trạng thái token thay đổi.

Nếu không có cơ chế invalidation riêng, Resource Server chỉ phát hiện revocation khi:

- Entry cache hết hạn và token được introspect lại.
- Resource Server chủ động xóa entry qua một kênh invalidation đã triển khai.
- Một request khác làm mới trạng thái theo policy của hệ thống.

### 2.2. TTL là một giới hạn độ trễ, không phải thời điểm thu hồi

TTL không quyết định khi nào AS thu hồi token. TTL quyết định Resource Server có thể tiếp tục dùng **kết quả introspection cũ** trong bao lâu trước khi hỏi lại AS.

Nếu cache TTL là 10 giây, điều đó không có nghĩa token sẽ bị thu hồi sau 10 giây. Nó chỉ có nghĩa cache entry không nên được sử dụng sau thời điểm hết TTL.

### 2.3. Revocation có thể có nhiều tầng trễ

Độ trễ thực tế có thể bao gồm:

1. AS cập nhật trạng thái token trong database/cluster.
2. Introspection replicas nhận trạng thái mới.
3. Sự kiện revocation được phát tới Resource Server (nếu có).
4. Resource Server instance nhận và xử lý invalidation.
5. Cache entry cũ được xóa hoặc hết TTL.
6. Request đang chạy trước thời điểm invalidation hoàn tất.

Chỉ giảm TTL không xử lý được mọi độ trễ ở AS hoặc event transport. Cần đo và thiết kế cả chuỗi.

## 3. Định nghĩa revocation propagation delay

Gọi:

- `T_cache`: TTL tối đa của positive introspection cache.
- `T_as`: độ trễ tối đa để trạng thái revocation có hiệu lực trên các introspection nodes.
- `T_event`: độ trễ tối đa của kênh push invalidation (nếu có).
- `T_clock`: sai lệch đồng hồ và sai số lập lịch/expiration.
- `T_inflight`: khoảng thời gian một request đã vượt qua authentication trước khi revocation được nhận biết.

Nếu chỉ dựa vào TTL và không có push invalidation, một giới hạn bảo thủ cho thời gian stale là:

\[
T_{\text{stale}} \lesssim T_{\text{as}} + T_{\text{cache}} + T_{\text{clock}} + T_{\text{inflight}}
\]

Nếu push invalidation hoạt động tin cậy, độ trễ có thể được giới hạn bởi thời gian AS phát sự kiện, truyền sự kiện và xóa cache:

\[
T_{\text{push}} \lesssim T_{\text{as}} + T_{\text{event}} + T_{\text{clock}} + T_{\text{inflight}}
\]

TTL vẫn nên là fallback khi sự kiện bị mất hoặc Resource Server tạm offline. Trong thực tế không nên tuyên bố một upper bound nếu chưa đo/đảm bảo các thành phần trên.

### 3.1. Ví dụ tính cửa sổ stale

Giả sử:

| Thành phần | Giá trị giả định |
|---|---:|
| AS replication delay | 2 giây |
| Cache TTL | 20 giây |
| Event invalidation | Không có |
| Clock skew allowance | 1 giây |
| Request đã qua authentication | 1 giây |

Giới hạn ước lượng theo thiết kế TTL là khoảng 24 giây. Nếu yêu cầu nghiệp vụ là token bị thu hồi phải ngừng truy cập trong tối đa 5 giây, TTL 20 giây không đáp ứng yêu cầu, dù introspection endpoint phản hồi rất nhanh.

### 3.2. Request đã xác thực trước khi revocation

Cache invalidation không nhất thiết hủy một request đã vượt qua authentication. Ví dụ request tải một báo cáo mất 2 phút; token bị thu hồi giữa lúc xử lý. Resource Server thường không kiểm tra introspection lại ở giữa mỗi service call.

Nếu cần dừng cả tác vụ đang chạy, cần cancellation/session/task revocation mechanism riêng. Không giả định xóa cache sẽ tự rollback giao dịch hoặc hủy các request đang thực thi.

## 4. Chọn TTL theo yêu cầu bảo mật

TTL càng ngắn, trạng thái revocation được phản ánh càng nhanh nhưng số lần introspection tăng. TTL càng dài, cache hit nhiều và AS ít tải hơn, nhưng token đã thu hồi có thể được chấp nhận lâu hơn.

| TTL positive cache | Revocation freshness | Introspection load | Phù hợp khi |
|---:|---|---|---|
| 0 giây / không cache | Hỏi AS mỗi lần | Cao nhất | Cần trạng thái gần realtime và AS đủ năng lực |
| 1–5 giây | Rất nhanh theo giới hạn cache | Cao | Endpoint nhạy cảm, giao dịch có rủi ro cao |
| 10–30 giây | Cân bằng theo policy | Trung bình | API thông thường, cần đo latency và revocation SLA |
| 1–5 phút | Chậm hơn | Thấp | Rủi ro thấp hơn, token ngắn hạn, có compensating controls |
| Bằng hoặc dài hơn token lifetime | Có thể không introspect lại trước khi token hết hạn | Thấp | Thường triệt tiêu mục tiêu revocation nhanh |

Các dải thời gian trên chỉ là ví dụ để thảo luận. Không có TTL chuẩn phù hợp cho mọi hệ thống.

### 4.1. TTL không được vượt quá thời điểm hết hạn token

Nếu introspection response có `exp`, entry cache không nên sống lâu hơn thời điểm token hết hạn:

\[
T_{\text{effective}} = \min(T_{\text{configured}}, exp - now)
\]

Ví dụ configured TTL là 30 giây nhưng token chỉ còn 8 giây, cache entry tối đa 8 giây (thường trừ thêm safety margin). Nếu không cap theo `exp`, Resource Server có thể sử dụng principal active sau thời hạn token.

Nếu introspection profile không cung cấp `exp`, dùng TTL ngắn đã được policy chấp thuận; AS vẫn phải là nguồn quyết định `active`. Không tự suy diễn expiry từ opaque token string.

### 4.2. Token hết hạn và token bị thu hồi là hai sự kiện khác nhau

- **Expiry:** hết hạn theo `exp` hoặc thời gian hiệu lực do AS quyết định.
- **Revocation:** AS chủ động đánh dấu token không còn active trước expiry.

Cache cần xử lý cả hai. Một TTL dài không thể được biện minh chỉ bằng việc access token có expiry ngắn nếu AS có thể revoke token trước expiry và hệ thống yêu cầu phản ánh nhanh.

### 4.3. Token có quyền nhạy cảm nên có policy riêng

Có thể dùng TTL ngắn hơn hoặc không cache cho:

- Thanh toán, chuyển tiền, thay đổi tài khoản.
- Quản trị user/role/permission.
- Đổi email, credential, recovery settings.
- Hành động cần thu hồi session ngay khi có sự cố.

Không nhất thiết mọi API phải có cùng TTL. Resource Server có thể áp dụng cache policy theo audience, route hoặc risk class, miễn là cache key và authorization context được thiết kế an toàn.

## 5. Positive cache và negative cache

### 5.1. Positive cache: introspection trả active=true

Đây là loại cache chính:

~~~text
token fingerprint → {
    active = true,
    principal = alice,
    authorities = [SCOPE_orders.read],
    validUntil = min(now + TTL, token exp)
}
~~~

Positive cache giảm số lần AS được gọi. Đổi lại, nó tạo stale-active window sau revocation.

### 5.2. Negative cache: introspection trả active=false

Có thể cache kết quả inactive trong một khoảng rất ngắn để tránh gọi AS liên tục cho cùng một token không hợp lệ:

~~~text
token fingerprint → {
    active = false,
    validUntil = now + negativeTTL
}
~~~

Negative TTL thường nên ngắn và được thiết kế riêng. Một token có thể vừa được cấp hoặc trạng thái có thể thay đổi theo provider flow; cache inactive quá lâu có thể từ chối token vừa active.

### 5.3. Không cache lỗi hạ tầng thành inactive

Phân biệt rõ:

| Kết quả introspection | Có nên cache? | Lý do |
|---|---|---|
| HTTP thành công, `active=true` | Có, theo positive TTL | Có principal/claims để dùng |
| HTTP thành công, `active=false` | Có thể, negative TTL rất ngắn | Giảm lặp request cho token inactive |
| Timeout / connection refused | Không | Không biết token active hay inactive |
| HTTP 5xx từ AS | Không | Lỗi dịch vụ không phải kết quả token inactive |
| `invalid_client` / lỗi xác thực Resource Server | Không | Cấu hình client/secret có vấn đề |
| Response malformed / thiếu `active` | Không | Không có kết quả hợp lệ để cache |

Nếu cache timeout/5xx thành inactive, một sự cố ngắn của AS có thể khiến mọi token bị từ chối lâu hơn sự cố. Nếu cache lỗi thành active, hệ thống có thể fail open và chấp nhận token mà không có xác nhận mới.

### 5.4. Negative cache có thể bị lạm dụng

Attacker có thể gửi nhiều chuỗi token ngẫu nhiên để làm cache tăng kích thước. Dùng maximum size, eviction policy, rate limiting và giới hạn kích thước token. Không lưu cache vô hạn theo mỗi token sai.

### 5.5. Cẩn trọng với BadOpaqueTokenException

Spring Security opaque token introspector thường báo token inactive bằng exception như `BadOpaqueTokenException`. Nếu muốn negative caching, cần phân biệt exception biểu diễn **kết quả token inactive hợp lệ** với lỗi network/AS/client configuration. Không bắt mọi `RuntimeException` rồi coi đó là inactive.

## 6. Cache key: không lưu raw access token

Access token là credential. Không dùng nguyên token làm cache key nếu cache backend có thể lộ key trong metrics, management UI, logs, heap dump hoặc diagnostic endpoint.

Một cache key nên kết hợp:

~~~text
cache namespace
    + issuer/introspection endpoint
    + resource-server client identity
    + tenant/resource context (nếu có)
    + token fingerprint
~~~

Token fingerprint có thể là HMAC-SHA-256 của token bằng secret riêng của Resource Server:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

final class TokenFingerprint {

    private final SecretKey key;

    TokenFingerprint(byte[] secret) {
        this.key = new SecretKeySpec(secret, "HmacSHA256");
    }

    String of(String token) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] digest = mac.doFinal(
                token.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Cannot fingerprint access token", ex);
        }
    }
}
~~~

Secret HMAC phải được quản lý như một key bảo mật, không hard-code trong source. HMAC fingerprint giúp tránh việc cache key trở thành nơi lưu token nguyên văn và tránh fingerprint có thể được đối chiếu tùy tiện giữa các hệ thống.

### 6.1. Vì sao phải đưa issuer/client/resource vào namespace?

Một token có thể được introspect trong nhiều security context hoặc qua nhiều AS. Kết quả có thể khác nhau theo introspection endpoint, authenticated resource server client, tenant hoặc policy resource-specific.

Không dùng cùng cache entry giữa:

- Hai issuer khác nhau.
- Hai tenant khác nhau.
- Hai Resource Server client registrations có quyền introspection khác nhau.
- Hai resource audience có policy authorization khác nhau nếu introspection/conversion phụ thuộc resource.

### 6.2. Không dùng sub làm cache key

Một user có thể có nhiều token khác nhau với scope, audience, expiry, client và trạng thái revocation khác nhau. Cache theo `sub=alice` sẽ có nguy cơ trả principal/authority của token này cho token khác.

Cache key phải định danh **token**, không chỉ định danh người dùng.

## 7. Cache những gì?

Thông thường cache kết quả introspection đã được xác minh, chẳng hạn `OAuth2AuthenticatedPrincipal` và attributes/authorities được tạo từ response. Không cache riêng một boolean `active=true` rồi bỏ qua claims.

Nếu chỉ cache `active=true` nhưng mỗi request lại dùng claims từ một nguồn khác, có thể ghép trạng thái token với subject/scope không tương ứng.

Một entry có thể lưu:

~~~text
CacheEntry
    principal
    authorities
    issuer/resource context
    introspectedAt
    validUntil
    token fingerprint
~~~

Không lưu raw access token trong value. Tránh sửa mutable attributes/authorities sau khi cache; coi cached principal là immutable hoặc tạo immutable snapshot.

### 7.1. Không cache kết quả authorization nghiệp vụ một cách vô tình

Introspection trả metadata token. Quyết định user có được đọc order 42 hay không có thể còn phụ thuộc ownership, tenant, trạng thái đơn hàng, policy hiện hành hoặc dữ liệu nghiệp vụ.

Cache principal không đồng nghĩa cache toàn bộ authorization decision. Nếu cache thêm quyết định nghiệp vụ, phải có TTL/invalidation policy riêng cho dữ liệu đó.

### 7.2. exp và validUntil

Nên tính:

~~~text
validUntil = now + configuredPositiveTtl

if introspection response contains exp:
    validUntil = min(validUntil, exp - safetyMargin)

if validUntil <= now:
    do not cache as a reusable active entry
~~~

Safety margin giúp tránh cache hit đúng sát thời điểm expiry khi đồng hồ các node lệch nhau. Margin phải tương thích clock synchronization và thời hạn token; không tự đặt quá lớn khiến token bị từ chối sớm bất hợp lý.
## 8. Tích hợp cache vào Spring Security Resource Server

Spring Security cung cấp các abstraction introspector:

| Stack | Interface | Vai trò |
|---|---|---|
| Servlet | `OpaqueTokenIntrospector` | Introspect token đồng bộ và trả `OAuth2AuthenticatedPrincipal` |
| WebFlux | `ReactiveOpaqueTokenIntrospector` | Introspect token theo reactive type, thường là `Mono<OAuth2AuthenticatedPrincipal>` |

Có thể bọc introspector hiện tại bằng decorator cache. Security authentication provider vẫn gọi abstraction như trước; decorator quyết định dùng cache hay gọi delegate.

### 8.1. Servlet authentication flow

~~~text
BearerTokenAuthenticationFilter
        |
        v
OpaqueTokenAuthenticationProvider
        |
        v
CachingOpaqueTokenIntrospector
        |
        +-- hit --> cached principal
        |
        +-- miss --> delegate introspector --> AS
        |
        v
BearerTokenAuthentication
        |
        v
Authorization / Controller
~~~

### 8.2. WebFlux authentication flow

~~~text
Bearer token WebFilter
        |
        v
Reactive opaque-token authentication manager
        |
        v
CachingReactiveOpaqueTokenIntrospector
        |
        +-- hit --> cached principal Mono
        |
        +-- miss --> delegate introspector Mono --> AS
        |
        v
Reactive Authentication
        |
        v
Authorization / Handler
~~~

Điểm mở rộng nằm ở introspector, vì vậy cache được áp dụng trước khi principal được đưa vào authentication context. Không cache một Authentication gắn với request cụ thể hoặc `SecurityContext` toàn cục.

## 9. Cài đặt CachingOpaqueTokenIntrospector cho Servlet

Ví dụ sau dùng Caffeine làm local in-memory cache. Caffeine cần được thêm vào runtime dependencies:

~~~gradle
dependencies {
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

### 9.1. Cache entry có validUntil

Không chỉ lưu principal; lưu cả thời điểm entry được phép sử dụng:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

record CachedIntrospection(
    OAuth2AuthenticatedPrincipal principal,
    Instant validUntil
) {}
~~~

`validUntil` là giá trị nhỏ hơn giữa configured TTL và expiry của token trừ safety margin.

### 9.2. Decorator đồng bộ

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class CachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Cache<String, CachedIntrospection> cache;
    private final TokenFingerprint fingerprint;
    private final Clock clock;
    private final Duration ttl;
    private final Duration safetyMargin;

    CachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            TokenFingerprint fingerprint,
            Clock clock,
            Duration ttl,
            Duration safetyMargin,
            long maximumSize) {
        this.delegate = delegate;
        this.fingerprint = fingerprint;
        this.clock = clock;
        this.ttl = ttl;
        this.safetyMargin = safetyMargin;
        this.cache = Caffeine.newBuilder()
            .maximumSize(maximumSize)
            .expireAfterWrite(ttl)
            .build();
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String key = fingerprint.of(token);

        CachedIntrospection entry = cache.get(
            key, ignored -> load(token));

        if (!entry.validUntil().isAfter(clock.instant())) {
            cache.invalidate(key);
            return introspect(token);
        }

        return entry.principal();
    }

    void invalidate(String token) {
        cache.invalidate(fingerprint.of(token));
    }

    void invalidateFingerprint(String tokenFingerprint) {
        cache.invalidate(tokenFingerprint);
    }

    private CachedIntrospection load(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Instant now = clock.instant();
        Instant validUntil = now.plus(ttl);
        Instant tokenExpiry = asInstant(principal.getAttribute("exp"));

        if (tokenExpiry != null) {
            Instant expiryLimit = tokenExpiry.minus(safetyMargin);
            if (!expiryLimit.isAfter(now)) {
                throw new InvalidBearerTokenException(
                    "Introspection returned an expired token");
            }
            if (expiryLimit.isBefore(validUntil)) {
                validUntil = expiryLimit;
            }
        }

        return new CachedIntrospection(principal, validUntil);
    }

    private Instant asInstant(Object value) {
        if (value instanceof Instant instant) {
            return instant;
        }
        if (value instanceof Date date) {
            return date.toInstant();
        }
        if (value instanceof Number epochSeconds) {
            return Instant.ofEpochSecond(epochSeconds.longValue());
        }
        return null;
    }
}
~~~

Đây là mẫu decorator cho Java 17+. `TokenFingerprint` là helper HMAC ở phần trước. Caffeine `cache.get(key, loader)` giúp hợp nhất các lần load đồng thời cho cùng một key trong một local cache. `expireAfterWrite(ttl)` đặt giới hạn vật lý tối đa; kiểm tra `validUntil` đảm bảo token có `exp` ngắn hơn TTL không được dùng quá hạn.

Nếu delegate ném `BadOpaqueTokenException`, timeout hoặc lỗi AS, loader không trả về một `CachedIntrospection`; Caffeine không lưu kết quả active giả. Mẫu này cũng từ chối nếu AS bất thường trả `active=true` nhưng `exp` đã qua safety margin. Đặc biệt, không bắt lỗi delegate rồi trả một principal cũ đã hết hạn.

### 9.3. Wire decorator vào SecurityWebFilterChain Servlet

Security DSL cho opaque token nhận một `OpaqueTokenIntrospector`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletResourceServerConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            OpaqueTokenIntrospector cachingIntrospector) throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque -> opaque
                    .introspector(cachingIntrospector))
            )
            .build();
    }
}
~~~

Bean `cachingIntrospector` phải được tạo bằng cách bọc delegate introspector đã cấu hình với đúng introspection URI, client ID/secret, HTTP client, timeout và error handling. Tên builder/constructor để tạo delegate phụ thuộc Spring Security version; giữ nguyên delegate đang dùng trong dự án và bọc nó là cách ít làm thay đổi behavior nhất.

Không cấu hình hai introspector cạnh tranh rồi không chắc chain đang dùng bean nào. Trong test/integration, xác nhận request thật đi qua chính decorator này.

### 9.4. Cấu hình delegate

Ở nơi tạo bean, cấu trúc nên là:

~~~java
OpaqueTokenIntrospector remoteIntrospector =
    createExistingRemoteIntrospector(
        introspectionUri,
        resourceServerClientId,
        resourceServerClientSecret);

OpaqueTokenIntrospector cachingIntrospector =
    new CachingOpaqueTokenIntrospector(
        remoteIntrospector,
        tokenFingerprint,
        clock,
        Duration.ofSeconds(10),
        Duration.ofSeconds(1),
        50_000);
~~~

`createExistingRemoteIntrospector(...)` là vị trí giữ cấu hình Nimbus/Spring introspector hiện có của ứng dụng; đây không phải API Spring Security có tên như vậy. Ví dụ này cho thấy thứ tự decorator: remote delegate ở trong, cache wrapper ở ngoài.

## 10. Cache cho ReactiveOpaqueTokenIntrospector

Trong WebFlux, không gọi blocking introspector hoặc blocking cache/network operation trên event-loop. Dùng reactive delegate và một async cache để các request cùng token có thể chia sẻ kết quả đang tải.

### 10.1. Reactive decorator

Ví dụ dùng Caffeine `AsyncCache`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import com.github.benmanes.caffeine.cache.AsyncCache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

final class CachingReactiveOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final AsyncCache<String, CachedIntrospection> cache;
    private final TokenFingerprint fingerprint;
    private final Clock clock;
    private final Duration ttl;
    private final Duration safetyMargin;

    CachingReactiveOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            TokenFingerprint fingerprint,
            Clock clock,
            Duration ttl,
            Duration safetyMargin,
            long maximumSize) {
        this.delegate = delegate;
        this.fingerprint = fingerprint;
        this.clock = clock;
        this.ttl = ttl;
        this.safetyMargin = safetyMargin;
        this.cache = Caffeine.newBuilder()
            .maximumSize(maximumSize)
            .expireAfterWrite(ttl)
            .buildAsync();
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        String key = fingerprint.of(token);
        return Mono.defer(() -> Mono.fromFuture(
            cache.get(key, (ignored, executor) ->
                delegate.introspect(token)
                    .map(this::toEntry)
                    .toFuture()
            )
        )).flatMap(entry -> {
            if (!entry.validUntil().isAfter(clock.instant())) {
                cache.synchronous().invalidate(key);
                return introspect(token);
            }
            return Mono.just(entry.principal());
        });
    }

    void invalidate(String token) {
        cache.synchronous().invalidate(fingerprint.of(token));
    }

    void invalidateFingerprint(String tokenFingerprint) {
        cache.synchronous().invalidate(tokenFingerprint);
    }

    private CachedIntrospection toEntry(
            OAuth2AuthenticatedPrincipal principal) {
        Instant now = clock.instant();
        Instant validUntil = now.plus(ttl);
        Object rawExpiry = principal.getAttribute("exp");
        Instant tokenExpiry = asInstant(rawExpiry);

        if (tokenExpiry != null) {
            Instant expiryLimit = tokenExpiry.minus(safetyMargin);
            if (!expiryLimit.isAfter(now)) {
                throw new InvalidBearerTokenException(
                    "Introspection returned an expired token");
            }
            if (expiryLimit.isBefore(validUntil)) {
                validUntil = expiryLimit;
            }
        }
        return new CachedIntrospection(principal, validUntil);
    }

    private Instant asInstant(Object value) {
        if (value instanceof Instant instant) return instant;
        if (value instanceof Date date) return date.toInstant();
        if (value instanceof Number seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }
        return null;
    }
}
~~~

`AsyncCache.get` trả về cùng một in-flight future cho các lần load trùng key trong cache instance, giúp giảm request đồng thời tới introspection endpoint. Khi delegate trả lỗi, future thất bại và không được giữ như một active principal. Nếu AS trả `active=true` nhưng `exp` đã qua safety margin, decorator từ chối token thay vì cache hoặc lặp lại introspection.

### 10.2. Wire decorator vào SecurityWebFilterChain WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector cachingIntrospector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque -> opaque
                    .introspector(cachingIntrospector))
            )
            .build();
    }
}
~~~

Delegate reactive introspector phải dùng reactive HTTP client và timeout phù hợp. Không bọc synchronous `OpaqueTokenIntrospector` trong `Mono.fromCallable()` rồi chạy nó trên event-loop; nếu cần dùng một API blocking legacy, phải offload sang bounded scheduler và đánh giá backpressure/capacity.

### 10.3. Servlet và WebFlux không chia sẻ cùng implementation

Hai interface có execution model khác nhau. Có thể chia sẻ token fingerprint, cache policy, cache entry và metrics naming, nhưng không nên dùng một blocking `Cache.get` trong reactive request path. Chọn `Cache` cho Servlet và `AsyncCache`/reactive adapter cho WebFlux.

## 11. Revocation endpoint và ý nghĩa đối với introspection cache

RFC 7009 định nghĩa OAuth 2.0 Token Revocation. Client gửi token tới revocation endpoint; AS xác thực client và xử lý việc thu hồi token theo policy. Response thành công không nhất thiết cung cấp chi tiết token đã tồn tại hay đã bị thu hồi từ trước, nhằm hạn chế việc dò token.

Request minh họa:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.test
Authorization: Basic <CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN>
token_type_hint=access_token
~~~

Sau khi AS xử lý revoke, introspection endpoint nên phản ánh token inactive theo semantics và consistency guarantees của provider. Tuy nhiên cache active tại Resource Server không tự bị xóa chỉ vì revocation endpoint trả thành công.

### 11.1. Thu hồi access token và refresh token

Hai loại token có vai trò khác nhau:

- Thu hồi **access token** nhằm ngăn Resource Server tiếp tục chấp nhận credential hiện tại.
- Thu hồi **refresh token** nhằm ngăn client xin access token mới bằng refresh credential đó.

Việc revoke refresh token không nhất thiết tự động làm access token đã phát hành trở thành inactive ngay lập tức. Một số AS có thể revoke token liên quan theo policy; provider khác để access token tiếp tục hợp lệ tới expiry. Cần kiểm tra contract của AS và test hành vi thực tế.

### 11.2. Logout không đồng nghĩa mọi access token đã bị vô hiệu hóa

Logout có thể xóa session cookie hoặc đăng xuất khỏi browser session, nhưng access token đã được cấp có thể tiếp tục tồn tại. Để bảo đảm logout/revoke có hiệu lực ở Resource Server, cần:

- AS revoke access token hoặc token family theo policy.
- Introspection trả inactive khi token đã revoke.
- Resource Server cache có TTL/invalidation phù hợp.
- Các downstream Resource Servers cũng nhận được trạng thái mới theo SLA.

Không kết luận logout đã thu hồi access token chỉ vì browser không còn session.

### 11.3. Revocation propagation là hợp đồng giữa AS và Resource Server

Tài liệu vận hành cần nêu:

| Câu hỏi | Hợp đồng cần xác định |
|---|---|
| AS cập nhật revocation khi nào? | Synchronous commit hay eventual consistency |
| Introspection replicas cập nhật khi nào? | Replication SLA |
| Resource Server cache TTL bao lâu? | Positive/negative TTL theo risk |
| Có push invalidation không? | Event type, delivery, retry, authentication |
| Event bị mất xử lý ra sao? | TTL fallback, replay event, reconciliation |
| Khi AS unavailable? | Fail closed, cache hit policy, stale-if-error nếu được phê duyệt |
| SLA revocation được đo ở đâu? | Từ revoke acceptance tới request cuối cùng bị từ chối |

## 12. Local cache, distributed cache và push invalidation

### 12.1. Local cache trên mỗi Resource Server instance

~~~text
                 Authorization Server
                   /      |      \
                  /       |       \
                 v        v        v
             RS node A  RS node B  RS node C
              cache A    cache B    cache C
~~~

Ưu điểm:

- Độ trễ cache hit thấp.
- Không thêm network dependency cho mỗi lookup.
- Mỗi node có thể hoạt động độc lập trong giới hạn TTL.

Hạn chế:

- Mỗi node có bản sao cache riêng.
- Invalidation phải đến tất cả nodes.
- Node mới/khởi động lại có cache state khác.
- Một request sau revocation có thể được node A từ chối nhưng node B vẫn chấp nhận.

Nếu dùng local cache, phải xác định maximum TTL và cách broadcast invalidation tới toàn bộ instances.

### 12.2. Distributed cache dùng chung

~~~text
RS node A ----\
RS node B -----+---- Redis / shared cache
RS node C ----/
                    |
                    +-- key fingerprint
                    +-- principal/claims
                    +-- TTL
~~~

Ưu điểm:

- Một lần cache invalidation có thể ảnh hưởng tới mọi nodes.
- Cache hit không phụ thuộc node nào nhận request.
- Có thể tập trung capacity, metrics và eviction policy.

Hạn chế:

- Mỗi request có thêm network hop tới cache.
- Shared cache trở thành dependency quan trọng.
- Serialization principal/authorities cần được kiểm soát.
- Network partition hoặc cache outage cần failure policy.
- Cần bảo vệ cache data và credentials như dữ liệu bảo mật.

Distributed cache không tự giải quyết revocation nếu AS không xóa key hoặc gửi event. Nó chỉ chia sẻ trạng thái cache.

### 12.3. Push invalidation qua event

Một kiến trúc có thể phát sự kiện sau khi revoke:

~~~text
Admin / Client
     |
     v
Authorization Server
     |
     +--> persist revocation
     |
     +--> publish TokenRevoked event
                |
                v
          Event broker
             /  |  \
            v   v   v
          RS-A RS-B RS-C
            |   |   |
            v   v   v
         invalidate cache entry
~~~

Event có thể chứa token identifier nội bộ, issuer, tenant, timestamp, event ID và loại token. Với opaque token, AS có thể phát một revocation identifier ổn định đã được Resource Server ánh xạ tới cache key. Tránh gửi raw access token qua broker.

### 12.4. Yêu cầu của invalidation event

- **Authenticated producer:** chỉ AS hoặc thành phần được ủy quyền mới phát event.
- **Authenticated consumers:** Resource Server xác minh nguồn event/broker ACL.
- **At-least-once safe:** event có thể đến nhiều lần; invalidation phải idempotent.
- **Ordering:** xử lý event theo version/sequence nếu có thể đến sai thứ tự.
- **Retry/DLQ:** event lỗi cần được retry và theo dõi.
- **Replay:** node offline cần lấy lại event hoặc thực hiện reconciliation.
- **TTL fallback:** nếu event bị mất, cache vẫn tự hết hạn theo policy.
- **Observability:** đo event lag, consumer lag và số cache entries được invalidated.

### 12.5. Race giữa introspection đang chạy và revoke event

Một race quan trọng:

~~~text
T0  RS cache miss, bắt đầu introspection request
T1  AS revoke token
T2  Revocation event đến RS, cache key bị xóa
T3  Introspection request cũ trả active=true từ replica chưa cập nhật
T4  RS ghi lại active=true vào cache
~~~

Nếu không xử lý, một entry stale có thể được tạo lại sau invalidation. Các biện pháp có thể dùng:

- AS bảo đảm introspection đọc trạng thái revocation nhất quán sau revoke commit.
- Event mang version/sequence và cache entry chỉ được ghi nếu không có revocation version mới hơn.
- Lưu revocation tombstone trong một khoảng tối thiểu, để cache miss không thể tạo active entry cũ.
- Kiểm tra event timestamp/request start time trước khi chấp nhận kết quả introspection đang in-flight.
- Dùng một invalidation generation theo token fingerprint.

Chỉ xóa key khỏi Redis/local cache chưa đủ nếu có request introspection đang chạy và có thể ghi lại kết quả sau đó.

### 12.6. Event không thay thế TTL

Push invalidation giúp giảm thời gian stale khi hoạt động bình thường. Nhưng event có thể mất, consumer offline, broker chậm hoặc một node không nhận event. TTL vẫn là safety bound dự phòng.

## 13. Caching và availability khi Authorization Server gặp sự cố

Cache vừa giảm tải vừa có thể giúp một Resource Server tiếp tục xác thực token đã introspect trước đó khi AS tạm thời không truy cập được. Tuy nhiên, cách xử lý cache miss và cache entry cũ phải rõ ràng.

### 13.1. Cache hit còn hạn trong lúc AS outage

Nếu entry active vẫn còn trong TTL, Resource Server có thể dùng entry đó theo policy đã phê duyệt. Revocation trong thời gian outage có thể chưa được phản ánh nếu không có push invalidation.

### 13.2. Cache miss trong lúc AS outage

Resource Server không có bằng chứng token active. Chính sách mặc định an toàn là từ chối authentication khi không thể introspect, thường trả 401/503 tùy error handling. Không biến timeout thành active=true.

### 13.3. Stale-if-error

Một số hệ thống cân nhắc tiếp tục dùng cached active result sau TTL khi AS unavailable. Đây là chế độ *stale-if-error* và phải được coi là một quyết định security policy riêng:

- Giới hạn stale grace period rất rõ.
- Chỉ áp dụng với entry trước đó đã active.
- Không áp dụng cho token chưa từng introspect thành công.
- Không vượt quá token expiry.
- Có thể vô hiệu hóa với endpoint rủi ro cao.
- Ghi metric/alert mỗi lần dùng stale result.
- Không áp dụng nếu nhận revocation event hoặc có dấu hiệu token compromise.

Stale-if-error làm tăng cửa sổ chấp nhận token đã revoke. Không bật mặc định chỉ để tăng availability.

### 13.4. Fail-open và fail-closed

| Policy | Khi introspection thất bại | Hệ quả |
|---|---|---|
| Fail closed | Không có kết quả hợp lệ thì từ chối | Bảo mật cao hơn, phụ thuộc AS availability |
| Fail open | Chấp nhận dù không xác minh được | Có thể cho phép token không hợp lệ |
| Bounded stale-if-error | Chỉ dùng cached active entry trong grace period giới hạn | Trade-off rõ nhưng có stale revocation risk |

Không dùng câu “cache giúp API chạy khi AS down” mà bỏ qua câu hỏi token có thể đã bị thu hồi trong outage hay không.

### 13.5. Timeout, retry và circuit breaker

- Đặt connect/read/response timeout cho introspection HTTP client.
- Retry chỉ với lỗi transient, có giới hạn và exponential backoff/jitter.
- Không retry invalid token hoặc invalid client credentials.
- Circuit breaker giúp bảo vệ AS khỏi retry storm; khi open, xử lý theo fail-closed/stale policy.
- Giới hạn concurrent introspection để tránh token flood.
- Không để retry kéo dài hơn deadline của request inbound.

## 14. Capacity, cache stampede và concurrency

### 14.1. Ước lượng cache size

Nếu có N token khác nhau hoạt động trong TTL window, cache cần giữ khoảng N entries (trừ eviction). Ví dụ 2.000 request/s, mỗi request dùng token mới và TTL 30 giây có thể tạo khoảng 60.000 active entries.

Token user thường được reuse qua nhiều request, vì vậy số entry thực tế phụ thuộc số token distinct, không phải tổng request count.

### 14.2. Cache stampede

Khi một entry hết hạn, nhiều request cùng token có thể đồng thời gọi AS. Dùng loading cache/single-flight để gộp các lần load cùng key trong một instance. Với nhiều nodes, local single-flight vẫn có thể tạo một introspection request trên mỗi node; distributed lock chỉ nên thêm khi chi phí và độ phức tạp thực sự cần thiết.

### 14.3. Refresh cache entry

Không nên refresh mọi entry nền chỉ vì gần hết TTL nếu không có nhu cầu. Background refresh có thể tạo lượng introspection lớn ngay cả khi token không còn được dùng. Có thể dùng expire-after-write đơn giản; nếu dùng refresh-ahead, chỉ refresh entry đang được truy cập và vẫn phải tôn trọng expiry/revocation policy.

### 14.4. Maximum size và eviction

Cache phải có giới hạn capacity. Eviction sớm chỉ làm tăng số introspection request; nó không được làm token hết hạn trở thành hợp lệ. Khi entry bị evict, lần sau phải gọi AS lại.

### 14.5. Không để cache key/metrics chứa token

Metrics chỉ nên có labels bounded như issuer alias, result, cache outcome, resource server ID. Không dùng raw token, fingerprint duy nhất, subject hoặc token ID làm label vì high cardinality và nguy cơ rò dữ liệu.

## 17. Metrics, logs và SLO cho revocation

Nếu không đo được thời gian từ revoke tới lần request cuối cùng được chấp nhận, tổ chức không thể biết TTL có đáp ứng yêu cầu hay không.

### 17.1. Metrics cache

Các metric hữu ích:

| Metric | Mục đích |
|---|---|
| `oauth2_introspection_requests_total` | Số lần gọi delegate/AS |
| `oauth2_introspection_duration_seconds` | Latency của introspection |
| `oauth2_introspection_errors_total` | Timeout, 5xx, invalid client, malformed response |
| `oauth2_introspection_cache_hits_total` | Số cache hit |
| `oauth2_introspection_cache_misses_total` | Số cache miss |
| `oauth2_introspection_cache_evictions_total` | Số entry bị eviction |
| `oauth2_introspection_cache_size` | Số entries hiện tại |
| `oauth2_introspection_cache_stale_served_total` | Số lần stale-if-error được dùng |
| `oauth2_revocation_events_received_total` | Số event revocation đã nhận |
| `oauth2_revocation_event_lag_seconds` | Độ trễ từ event phát tới consumer xử lý |
| `oauth2_revocation_cache_invalidations_total` | Số cache entry được invalidated |
| `oauth2_revocation_last_accept_delay_seconds` | Độ trễ đo được từ revoke tới lần request cuối cùng được chấp nhận |

Tên metric là gợi ý; cần theo convention telemetry của dự án. Labels chỉ dùng giá trị bounded như issuer alias, resource-server alias, outcome và environment. Không dùng token, fingerprint, subject hoặc jti làm label.

### 17.2. Tính cache hit ratio

Một cách tính đơn giản:

\[
\text{hit ratio} =
\frac{\text{cache hits}}
{\text{cache hits} + \text{cache misses}}
\]

Hit ratio cao giúp giảm tải AS nhưng không tự chứng minh hệ thống an toàn. Một cache hit ratio 99.9% với TTL 10 phút có thể không đáp ứng revocation SLA 5 giây.

### 17.3. Đo revocation SLA

Có thể định nghĩa:

~~~text
revocation acceptedAt:
    thời điểm AS xác nhận revoke thành công

lastAcceptedAt:
    thời điểm Resource Server cuối cùng vẫn chấp nhận token

revocationDelay:
    lastAcceptedAt - acceptedAt
~~~

Đo trên mọi Resource Server nodes, qua load balancer và qua cả cache invalidation path. Với request đang in-flight, cần xác định SLO tính theo thời điểm authentication hay thời điểm response hoàn tất.

### 17.4. Structured logs

Có thể log sự kiện không chứa credential:

~~~text
event=introspection outcome=active issuer=shop-rs cache=miss
event=introspection outcome=cache_hit issuer=shop-rs
event=introspection outcome=inactive issuer=shop-rs cache=miss
event=revocation_invalidation outcome=success issuer=shop-rs
event=revocation_invalidation outcome=retry event_id=evt-123
event=introspection outcome=error reason=timeout issuer=shop-rs
~~~

Không log:

~~~text
token=eyJ...
Authorization: Bearer ...
refresh_token=...
full_introspection_request_body=...
~~~

Ngay cả khi opaque token không đọc được claims, nó vẫn là credential có thể bị sử dụng. Hãy redaction ở application logs, proxy logs, traces, broker payload inspection và exception output.

## 18. Runbook khi phát hiện token bị thu hồi nhưng vẫn truy cập được

Khi incident cho thấy token đã revoke nhưng API vẫn trả 2xx, kiểm tra theo thứ tự:

1. Xác nhận AS đã trả revoke success và token type đúng.
2. Gọi introspection bằng resource server client hợp lệ, xác nhận AS trả `active=false`.
3. Kiểm tra Resource Server đang dùng opaque introspection path hay JWT local decoder.
4. Kiểm tra cache hit/miss, entry age, TTL và `validUntil`.
5. Kiểm tra cache key namespace/issuer/tenant có trùng đúng entry không.
6. Kiểm tra event revocation đã được publish, consume và invalidation thành công ở mọi node chưa.
7. Kiểm tra request introspection cũ có ghi lại active entry sau invalidation không.
8. Kiểm tra cache shared/local và node nhận request từ load balancer.
9. Kiểm tra stale-if-error hoặc fallback policy có được bật không.
10. Ghi nhận thời điểm request cuối cùng được chấp nhận và so với revocation SLA.

### 18.1. Hành động giảm thiểu

Tùy mức độ incident:

- Giảm positive TTL theo policy đã được duyệt.
- Invalidate cache entry theo token identifier đã xác minh.
- Tạm thời disable cache cho resource nhạy cảm.
- Dừng stale-if-error nếu đang bật.
- Kiểm tra và sửa event consumer/replication lag.
- Revoke token family/session hoặc yêu cầu cấp token mới theo quy trình AS.
- Giới hạn endpoint/operation có rủi ro trong thời gian khắc phục.

Không xóa toàn bộ cache trong production mà không đánh giá tải introspection tăng đột biến; thao tác đó có thể tạo cache stampede lên AS. Nếu cần flush rộng, chuẩn bị rate limit/concurrency limit và phối hợp với đội vận hành identity.

### 18.2. Khi AS introspection trả active=true sau revoke

Nếu AS đã nhận revoke nhưng introspection vẫn trả active:

- Xác minh token ID/token type được revoke có đúng token đang kiểm tra không.
- Xác minh consistency/replication của AS.
- Kiểm tra revoke semantics của provider và việc revoke access token hay chỉ refresh token.
- Kiểm tra resource server client có đủ quyền introspection và đang gọi đúng issuer/tenant.
- Xác nhận policy AS có cascade revoke token liên quan hay không.

Resource Server cache không phải nguyên nhân duy nhất; phải phân biệt stale ở AS với stale trong cache.

## 19. Những lỗi triển khai thường gặp

### 19.1. TTL quá dài vì muốn giảm tải AS

TTL dài có thể làm revocation delay vượt SLA. Chọn TTL dựa trên threat model và đo tải, không chỉ theo cache hit ratio.

### 19.2. Cache active vô thời hạn

Không dùng cache không expiry cho principal/token active. Nếu không có TTL, token đã revoke có thể được chấp nhận cho tới khi entry bị evict hoặc node restart.

### 19.3. Không cap TTL theo exp

Entry có thể tồn tại lâu hơn access token lifetime. Tính validUntil bằng min(configured TTL, token expiry trừ safety margin).

### 19.4. Cache timeout/5xx thành active hoặc inactive

Lỗi kết nối không phải kết quả introspection. Không cache lỗi hạ tầng như một quyết định token validity.

### 19.5. Cache theo subject thay vì token

Nhiều token của cùng một user có scope/audience/expiry khác nhau. Cache theo subject có thể trả quyền của token khác.

### 19.6. Chỉ invalidation một node

Local cache ở các nodes khác vẫn giữ active result. Broadcast invalidation, dùng shared cache hoặc giữ TTL fallback và test cross-node.

### 19.7. Push invalidation không có chống race

In-flight introspection cũ có thể ghi lại active entry sau event. Dùng generation/tombstone/version hoặc consistency guarantees của AS.

### 19.8. Cache raw token làm key

Cache key có thể lộ qua metrics, logs, management tools hoặc heap dump. Dùng HMAC fingerprint và namespace theo issuer/client/resource.

### 19.9. Fail-open khi AS unavailable

Nếu cache miss và AS down, không có bằng chứng token active. Chỉ dùng stale-if-error trong grace period được phê duyệt, không chấp nhận token chưa từng introspect thành công.

### 19.10. Nhầm JWKS cache với introspection cache

JWKS cache lưu public keys để xác minh JWT signatures; nó không chứa trạng thái revoke từng access token. Hai loại cache có mục tiêu và TTL khác nhau.

### 19.11. Nghĩ revoke refresh token sẽ tự revoke access token

Access token đã cấp có thể vẫn active tới expiry tùy AS. Kiểm tra semantics của provider và introspection result sau revoke.

### 19.12. Không test mọi Resource Server node

Một node nhận event và node khác không nhận có thể tạo behavior không nhất quán. Test qua load balancer và quan sát từng node.

## 20. Checklist thiết kế cache introspection

### 20.1. Security semantics

- [ ] AS trả `active=false` cho token expired/revoked theo contract đã xác nhận.
- [ ] Đã phân biệt revoke access token với revoke refresh token.
- [ ] TTL positive được chọn theo revocation SLA và risk class.
- [ ] TTL entry không vượt token expiry trừ safety margin.
- [ ] Không cache lỗi timeout/5xx/invalid client thành token active hoặc inactive.
- [ ] Negative cache (nếu có) có TTL ngắn và capacity limit riêng.
- [ ] Cache key định danh token, không dùng subject làm key.
- [ ] Cache key không lưu raw token; dùng HMAC fingerprint.
- [ ] Cache namespace phân biệt issuer, tenant, resource server client và resource context.
- [ ] Cached principal/authorities không bị mutate sau khi lưu.

### 20.2. Spring integration

- [ ] Servlet dùng OpaqueTokenIntrospector decorator.
- [ ] WebFlux dùng ReactiveOpaqueTokenIntrospector và non-blocking async cache.
- [ ] SecurityWebFilterChain thực sự dùng caching introspector bean.
- [ ] Delegate giữ nguyên introspection URI, client authentication, HTTP timeout và error mapping.
- [ ] Cache hit trả principal tương ứng với đúng token.
- [ ] Cache miss gọi AS và chỉ cache response hợp lệ.
- [ ] Cache eviction/invalidation không tạo đường fail-open.

### 20.3. Cluster và revocation

- [ ] Đã chọn local cache, distributed cache hoặc kết hợp.
- [ ] Local cache invalidation được broadcast tới mọi instances nếu cần.
- [ ] Distributed cache có ACL/encryption/network policy và capacity phù hợp.
- [ ] Push event có authentication, retry, idempotency và replay/reconciliation.
- [ ] In-flight introspection không thể ghi đè revocation event mới hơn.
- [ ] TTL vẫn là fallback nếu event mất.
- [ ] AS replication delay và introspection consistency đã được đo.
- [ ] Có test qua load balancer và mọi Resource Server nodes.

### 20.4. Availability và observability

- [ ] Có timeout, retry bounded, circuit breaker và concurrency limit.
- [ ] Cache miss khi AS unavailable có fail-closed policy rõ ràng.
- [ ] Stale-if-error (nếu có) bị giới hạn, có metric và được phê duyệt.
- [ ] Theo dõi hit ratio, miss, introspection latency/error, cache size/eviction.
- [ ] Theo dõi revocation event lag và thời gian last-accepted-after-revoke.
- [ ] Không log token, raw fingerprint, refresh token hoặc full introspection body.
- [ ] Runbook có bước phân biệt AS stale với Resource Server cache stale.

## 21. Ví dụ policy theo mức độ rủi ro

Một tổ chức có thể định nghĩa các profile policy minh họa:

| Profile | Positive TTL | Push invalidation | Stale-if-error | Ví dụ use case |
|---|---:|---|---|---|
| High risk | 0–2 giây | Bắt buộc hoặc cơ chế tương đương | Tắt | Payment/admin/recovery |
| Standard API | 5–15 giây | Có nếu AS hỗ trợ | Tắt hoặc rất ngắn | Orders/customer data |
| Low risk internal | 30–60 giây | Tùy chọn | Chỉ khi được duyệt | Read-only metadata |

Đây chỉ là ví dụ để bắt đầu thảo luận. Policy cuối cùng phải dựa trên revocation SLA, AS capacity, token lifetime, user impact và threat model. Không sao chép TTL của một service sang mọi API mà không xét rủi ro.

## 22. Kết luận

Cache introspection giúp Resource Server giảm latency và số lần gọi Authorization Server khi xác thực opaque access token. Nhưng cache một kết quả `active=true` cũng có nghĩa Resource Server có thể tiếp tục chấp nhận token sau khi AS đã revoke nó.

Thời gian stale phụ thuộc positive TTL, AS replication, event invalidation, clock skew và request đang in-flight. TTL là fallback quan trọng; push invalidation có thể rút ngắn thời gian phản ánh revocation nhưng cần xử lý event loss, node offline và race với introspection request đang chạy.

Trong Spring Security, bọc `OpaqueTokenIntrospector` hoặc `ReactiveOpaqueTokenIntrospector` bằng cache decorator là một điểm tích hợp phù hợp. Cache phải giữ principal/authorities theo token, dùng fingerprint thay raw token, cap validUntil theo exp, giới hạn capacity và không cache lỗi hạ tầng như một quyết định token validity. WebFlux cần async/reactive cache để tránh blocking event loop.

**Cache hit ratio không phải thước đo bảo mật.** Điều cần đo là từ lúc AS xác nhận revoke tới lúc request cuối cùng bị Resource Server từ chối, trên toàn bộ cluster. Chọn TTL và invalidation strategy sao cho độ trễ đo được đáp ứng SLA revocation của từng loại endpoint.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — OpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Caffeine Cache — User Guide](https://github.com/ben-manes/caffeine/wiki)

## 15. JWT self-contained khác với opaque token introspection

Không nhầm cache introspection với cache JSON Web Key Set (JWKS).

| Opaque access token | JWT access token tự xác minh |
|---|---|
| Resource Server thường hỏi AS qua introspection | Resource Server xác minh chữ ký/claims cục bộ |
| Cache có thể lưu active state và principal từ introspection | Decoder thường cache public signing keys/JWKS metadata |
| Revocation có thể phản ánh qua introspection sau khi AS cập nhật | JWT hợp lệ về chữ ký vẫn có thể được chấp nhận tới expiry nếu không có revocation mechanism riêng |
| TTL introspection trực tiếp ảnh hưởng stale revocation window | JWKS cache TTL chủ yếu ảnh hưởng key rotation, không tự tạo token revocation check |

### 15.1. JWKS cache không phải revocation cache

JWKS cache lưu public keys để verify chữ ký. Khi AS revoke một JWT access token, public key thường vẫn cần được giữ để xác minh các token khác được ký bằng key đó. Xóa signing key khỏi JWKS chỉ để revoke một token có thể ảnh hưởng mọi token ký bằng key đó.

### 15.2. Cách revoke JWT sớm

Các lựa chọn tùy hệ thống:

- Access token lifetime ngắn và refresh token rotation.
- Denylist/revocation store theo `jti` hoặc token fingerprint.
- Introspection cho JWT nếu AS hỗ trợ và Resource Server dùng opaque/introspection path.
- Event invalidation để Resource Server cập nhật revocation state.
- Token profile/architecture có version hoặc session epoch được kiểm tra tại request.

Mỗi lựa chọn có chi phí network/state và độ trễ khác nhau. JWT self-contained không tự cung cấp revocation realtime.

### 15.3. Cache claims và permission changes

Ngay cả khi token chưa bị revoke, quyền của user có thể thay đổi sau lần introspection. Nếu AS trả scope/roles trong introspection response, cache principal cũng cache snapshot quyền đó. TTL và invalidation policy cần xét cả permission changes, logout và account disable, không chỉ token revoke.

## 16. Kiểm thử cache introspection và revocation delay

Nên test decorator ở unit level, test SecurityWebFilterChain ở integration level và test nhiều node/event ở hệ thống triển khai.

### 16.1. Test cache hit giảm số lần gọi delegate

Ví dụ synchronous test với delegate stub:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class CachingOpaqueTokenIntrospectorTest {

    @Test
    void repeatedRequestsUseOneIntrospectionResult() {
        AtomicInteger calls = new AtomicInteger();

        OAuth2AuthenticatedPrincipal principal =
            new DefaultOAuth2AuthenticatedPrincipal(
                "alice",
                Map.of("scope", "orders.read"),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        OpaqueTokenIntrospector delegate = token -> {
            calls.incrementAndGet();
            return principal;
        };

        var caching = new CachingOpaqueTokenIntrospector(
            delegate,
            new TokenFingerprint(new byte[32]),
            Clock.systemUTC(),
            Duration.ofSeconds(10),
            Duration.ofSeconds(1),
            1_000);

        caching.introspect("opaque-token-1");
        caching.introspect("opaque-token-1");
        caching.introspect("opaque-token-1");

        assertEquals(1, calls.get());
    }
}
~~~

Test này chứng minh cùng token được introspect một lần trong TTL của local cache. Nó không chứng minh revocation được phản ánh ngay; cần test invalidation/expiry riêng.

### 16.2. Test invalidation sau revoke event

Giả sử AS stub ban đầu trả active, sau đó chuyển sang inactive:

~~~java
AtomicBoolean active = new AtomicBoolean(true);
AtomicInteger calls = new AtomicInteger();

OpaqueTokenIntrospector delegate = token -> {
    calls.incrementAndGet();
    if (!active.get()) {
        throw new BadOpaqueTokenException("Token is inactive");
    }
    return principal;
};

var caching = new CachingOpaqueTokenIntrospector(
    delegate,
    fingerprint,
    Clock.systemUTC(),
    Duration.ofSeconds(30),
    Duration.ofSeconds(1),
    1_000);

caching.introspect("opaque-token-1");  // cache active
active.set(false);                    // AS revokes token

// Cache hit vẫn có thể trả active nếu chưa invalidated.
caching.introspect("opaque-token-1");

// Event consumer xử lý TokenRevoked.
caching.invalidate("opaque-token-1");

// Lần sau gọi delegate và bị từ chối.
assertThrows(
    BadOpaqueTokenException.class,
    () -> caching.introspect("opaque-token-1"));
~~~

Đây là minh họa behavior của local cache. Trong test thật, event consumer nên nhận một event đã xác thực, chuyển identifier sang cache key đúng namespace rồi gọi invalidation method. Không đưa raw token qua event broker chỉ để test đơn giản.

### 16.3. Test negative result không bị cache nhầm thành transient failure

Các test riêng:

- Token inactive: delegate ném `BadOpaqueTokenException`; lần sau phải gọi lại nếu không bật negative cache.
- Timeout: delegate ném timeout; lỗi không được biến thành principal active.
- HTTP 5xx: không cache kết quả active giả.
- Invalid client credentials: phát hiện lỗi cấu hình và alert; không coi token user là inactive.

Nếu có negative cache, assert inactive entry chỉ tồn tại trong negative TTL đã cấu hình và không ảnh hưởng positive cache.

### 16.4. Test TTL và exp

Với clock/ticker có thể điều khiển trong test:

1. Tạo principal có exp còn 5 giây và configured TTL 30 giây.
2. Assert validUntil không vượt exp trừ safety margin.
3. Tăng clock vượt validUntil.
4. Assert lần introspect tiếp theo gọi delegate lại.
5. Tạo token hết hạn; assert decorator không cache active principal.

Nên inject Clock và Caffeine Ticker vào cache factory để test thời gian deterministic thay vì dùng `Thread.sleep` dài.

### 16.5. Test concurrent requests

Khởi chạy nhiều request đồng thời với cùng một token và assert delegate được gọi một lần cho cùng một cache miss trong một instance. Với nhiều nodes, xác định rõ kỳ vọng: local single-flight có thể vẫn tạo một lần introspection trên mỗi node nếu không có shared cache/distributed coordination.

### 16.6. Test revocation propagation end-to-end

Một test hệ thống có thể đo:

~~~text
1. Obtain opaque access token T
2. Send request to Resource Server A → accepted
3. Send request to Resource Server B → accepted
4. Revoke T at Authorization Server
5. Wait for AS state propagation
6. Deliver invalidation event (if configured)
7. Send request repeatedly to every Resource Server node
8. Record time of last accepted request
9. Assert last-accept time <= configured revocation SLA
~~~

Không chỉ kiểm tra một node. Load balancer có thể chuyển request giữa nodes có cache state khác nhau; test phải bao phủ toàn bộ cluster.

### 16.7. Kiểm thử race condition

Giả lập:

- Introspection request bắt đầu trước khi revoke.
- Revocation event tới trong lúc request đang chạy.
- Introspection response cũ trả về sau event.

Assert entry active không được ghi lại sau invalidation version mới hơn. Đây là test quan trọng nếu dùng push invalidation và async cache.
