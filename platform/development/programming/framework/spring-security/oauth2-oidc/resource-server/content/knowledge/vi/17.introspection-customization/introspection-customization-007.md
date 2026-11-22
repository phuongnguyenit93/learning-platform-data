# Cache kết quả hợp lệ, thời hạn token và cửa sổ chậm thu hồi

Trong **Spring Security OAuth 2.0 Resource Server**, xác thực **opaque access token** thường dựa vào **token introspection**: Resource Server gọi Authorization Server để hỏi một access token có còn hoạt động hay không, sau đó nhận attributes và authorities để quyết định quyền truy cập API. So với xác minh JWT bằng public key tại chỗ, introspection có thể tạo thêm độ trễ mạng và tải cho Authorization Server trên mỗi lần xác thực.

Một hướng tối ưu là **cache kết quả introspection thành công** trong một khoảng ngắn. Tuy nhiên, cache đặt ra một đánh đổi bảo mật: **Authorization Server có thể đã thu hồi token, nhưng Resource Server vẫn đang giữ một kết quả `active: true` cũ**. Khoảng thời gian token bị thu hồi vẫn có thể được chấp nhận vì cache được gọi là **cửa sổ chậm thu hồi (revocation lag/window)**.

Thiết kế đúng không phải đơn giản thêm `@Cacheable` vào `OpaqueTokenIntrospector.introspect(...)`. Cần hiểu **token expiration**, **cache TTL**, **cách tính thời hạn lưu an toàn**, **thu hồi token**, **scope/claims thay đổi**, **cache key**, **lỗi introspection**, **nhiều instance**, và yêu cầu **fail closed**.

Bài học tập trung vào việc tùy chỉnh introspection trong Spring Security OAuth 2.0/OIDC Resource Server, với ví dụ Java Servlet stack dùng `OpaqueTokenIntrospector`, Caffeine và các chính sách cache ngắn hạn.

## 1. Introspection và vai trò của cache

Request tới Orders API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer opaque-access-token-example
~~~

Trong Resource Server sử dụng opaque token:

1. `BearerTokenAuthenticationFilter` trích chuỗi token.
2. `OpaqueTokenAuthenticationProvider` chuyển token tới `OpaqueTokenIntrospector`.
3. Introspector gửi token đến introspection endpoint đáng tin của Authorization Server, theo giao thức được hai bên hỗ trợ.
4. Nếu Authorization Server xác nhận token hợp lệ, introspector trả `OAuth2AuthenticatedPrincipal` có attributes và authorities.
5. Provider tạo `BearerTokenAuthentication` đã xác thực.
6. Spring Security tiếp tục authorization, ví dụ kiểm tra `SCOPE_orders.read` và quyền với đúng order.

Không cache, luồng thông dụng là:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant F as BearerTokenAuthenticationFilter
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant A as AuthorizationFilter
    C->>F: Authorization: Bearer T
    F->>I: introspect(T) qua AuthenticationProvider
    I->>AS: POST /introspect, token=T
    AS-->>I: active=true + exp + scope + ...
    I-->>F: OAuth2AuthenticatedPrincipal
    F->>A: BearerTokenAuthentication
    A-->>C: Response theo quyền
    Note over C,AS: Request sau có thể lặp lại lời gọi introspection
~~~

Khi thêm cache ở phía Resource Server:

~~~mermaid
flowchart TD
    A["Bearer token T"] --> B["CachingOpaqueTokenIntrospector"]
    B --> C{"Cache có positive entry còn hiệu lực?"}
    C -- "Có" --> D["Dùng principal đã được introspect trước đó"]
    C -- "Không" --> E["Delegate tới trusted OpaqueTokenIntrospector"]
    E --> F{"Introspection chấp nhận token?"}
    F -- "Không" --> G["Từ chối authentication; không cache positive"]
    F -- "Có" --> H["Tính reuseUntil theo TTL và exp"]
    H --> I["Cache positive entry nếu đủ điều kiện"]
    I --> J["Trả OAuth2AuthenticatedPrincipal"]
    D --> J
    J --> K["Provider → Authentication → Authorization"]
~~~

Một cache hit tránh lời gọi mạng, nhưng **không hỏi Authorization Server xem token vừa bị thu hồi hay chưa**. Vì vậy cache phải có chính sách thời gian và thu hồi rõ ràng.

## 2. Kết quả introspection là gì?

Theo **RFC 7662**, Authorization Server có thể trả:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.export",
  "exp": 1893456000,
  "iat": 1893452400,
  "tenant_id": "t-7"
}
~~~

Khi token không hoạt động:

~~~json
{
  "active": false
}
~~~

`active: true` thể hiện quyết định của Authorization Server **tại thời điểm introspection**. Nó không phải cam kết token sẽ còn hoạt động trong suốt những phút tiếp theo, cũng không tự chứng minh token có đủ scope hoặc được phép truy cập một tài nguyên của tenant khác.

Metadata trong response có thể thay đổi theo Authorization Server và quyền của client introspection:

| Trường | Ý nghĩa đối với cache/authorization |
| --- | --- |
| `active` | Token đang hoạt động theo kết quả introspection hiện tại |
| `exp` | Thời điểm token hết hạn; không nên cache kết quả quá thời điểm này |
| `nbf` | Thời điểm token bắt đầu có hiệu lực nếu được cung cấp |
| `iat` | Thời điểm phát hành, không phải thời hạn cache |
| `iss` | Issuer; phải khớp miền tin cậy được cấu hình khi hợp đồng yêu cầu |
| `aud` | API/resource nhận token; tránh chấp nhận token dành cho API khác |
| `scope` | Scope đã được cấp; thường chuyển sang authorities `SCOPE_...` |
| `sub`, `client_id` | User subject/client identity, không tự xác lập quyền sở hữu bản ghi |
| `tenant_id`, `permissions` | Claim riêng cần hiểu theo chính sách và schema đã thống nhất |

Trong Spring Security, một `OpaqueTokenIntrospector` hợp lệ thường trả **`OAuth2AuthenticatedPrincipal`**, không đơn thuần trả JSON. Principal chứa `getAttributes()`, `getName()` và `getAuthorities()`. Cache ở tầng introspector nên lưu một **kết quả đã được xác minh và đã áp dụng chính sách** phù hợp, không lưu response `active: true` thô rồi bỏ qua bước chuyển quyền.

### JWT cũng có thể được introspect

Tên “opaque token Resource Server” thường nói tới **cách xác minh qua introspection**. Nếu issuer hỗ trợ, một JWT access token cũng có thể được introspect thay vì xác minh offline. Nguyên tắc TTL và revocation lag vẫn áp dụng cho **kết quả introspection được cache**, bất kể chuỗi token có hình thức JWT hay opaque.

## 3. Phân biệt ba loại thời gian

Đặt:

- `t₀`: thời điểm Resource Server nhận kết quả introspection thành công.
- `C`: thời gian cache tối đa được cho phép, ví dụ 30 giây.
- `E`: thời điểm `exp` của access token nếu issuer cung cấp.
- `δ`: biên an toàn trước lúc token hết hạn, ví dụ 5 giây.
- `R`: thời điểm token bị thu hồi tại Authorization Server.

Ba khái niệm độc lập:

| Khái niệm | Bắt đầu từ đâu? | Quyết định gì? |
| --- | --- | --- |
| **Access token lifetime** | Quyết định cấp token của Authorization Server; thường qua `iat` và `exp` | Token có còn được dùng về mặt thời hạn không |
| **Cache TTL** | Thời điểm ghi entry cache tại Resource Server | Dữ liệu introspection đã xác nhận được tái sử dụng bao lâu |
| **Revocation lag/window** | Khi issuer thu hồi token nhưng Resource Server chưa nhận biết | Token đã bị thu hồi có thể tiếp tục được chấp nhận trong cache bao lâu |

**Cache TTL không thay đổi `exp` của token.** Một token hết hạn trong 10 giây không nên được cache để dùng tiếp 30 giây chỉ vì TTL đã cấu hình là 30 giây.

### Công thức thời hạn tái sử dụng

Với token có `exp` đáng tin:

~~~text
reuseUntil = min(t₀ + C, E - δ)

TTL_effective = max(0, reuseUntil - t₀)
~~~

Giả sử policy cho phép cache 30 giây và chừa 5 giây an toàn trước `exp`:

| Token hết hạn sau | TTL cấu hình | TTL hiệu dụng tối đa | Lý do |
| --- | --- | --- | --- |
| 10 phút | 30 giây | 30 giây | Cửa sổ cache là giới hạn chặt hơn |
| 40 giây | 30 giây | 30 giây | `exp - 5s` còn cách 35 giây |
| 20 giây | 30 giây | 15 giây | Không lưu đến sát `exp` |
| 5 giây | 30 giây | 0 giây | Không đủ biên an toàn để cache |
| Đã hết hạn | 30 giây | 0 giây; token phải bị từ chối theo chính sách | Không thể kéo dài token nhờ cache |
| Không có `exp` đáng tin | 30 giây | Chính sách thận trọng: không cache | Không có mốc cứng để chặn dùng quá hạn |

Con số 30 giây và 5 giây chỉ là **ví dụ thiết kế**, không phải TTL bắt buộc của OAuth 2.0 hoặc Spring Security.

### NumericDate và kiểu Java của exp

Trong JWT và các metadata OAuth liên quan, `exp` thường là **NumericDate: số giây từ Unix epoch**, không phải milliseconds. Tuy nhiên, introspector có thể chuyển `exp` thành `Instant` trước khi trả `OAuth2AuthenticatedPrincipal`:

~~~java
Object rawExpiry = principal.getAttribute("exp");

if (rawExpiry instanceof java.time.Instant instant) {
    // Dùng instant như một thời điểm tuyệt đối.
}
else if (rawExpiry instanceof Number number) {
    // Chỉ xử lý như epoch seconds khi hợp đồng issuer cho phép.
    java.time.Instant exp =
        java.time.Instant.ofEpochSecond(number.longValue());
}
~~~

Không mặc định `(Long) principal.getAttribute("exp")` luôn thành công; cũng không dùng `Instant.ofEpochMilli(...)` cho một NumericDate tính bằng giây. Với NumericDate thập phân, cần converter chính xác theo schema; ví dụ cache phía dưới cố ý xử lý dạng số giây nguyên thông dụng một cách thận trọng.

## 4. Cửa sổ chậm thu hồi được tạo ra như thế nào?

Giả sử token T đã introspect tại **10:00:00**, Resource Server cache kết quả `active: true` với TTL **60 giây**:

~~~text
10:00:00  Introspection T -> active=true
          Cache T, authorities = [SCOPE_orders.read]

10:00:10  Authorization Server thu hồi T

10:00:25  Client gửi lại T
          Resource Server cache hit -> có thể chấp nhận T!

10:01:00  Cache entry hết hiệu lực

10:01:05  Client gửi lại T
          Resource Server introspect -> active=false -> từ chối
~~~

Đó là một **revocation lag** do cache. Với TTL tối đa `C`, trường hợp bất lợi thường xảy ra khi token bị thu hồi **ngay sau một lần cache refresh thành công**. Khi cache chỉ cho phép tái sử dụng trong `C` và không có tầng cache khác kéo dài tuổi dữ liệu, độ trễ thu hồi do cache có thể gần `C`, cộng thêm độ trễ liên quan đến request đang xử lý và khả năng lan truyền trạng thái của issuer.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client giữ T
    participant RS as Resource Server cache TTL=30s
    participant AS as Authorization Server
    C->>RS: Request với T
    RS->>AS: introspect(T)
    AS-->>RS: active=true
    RS-->>C: Cho qua nếu đủ quyền
    Note over RS: Cache T đến t0+30s hoặc trước exp
    AS->>AS: Thu hồi T tại t0+5s
    C->>RS: Request với T tại t0+10s
    Note over RS: Cache hit; chưa biết trạng thái đã bị thu hồi
    RS-->>C: Có thể vẫn chấp nhận T
    C->>RS: Request sau khi cache hết hạn
    RS->>AS: introspect(T)
    AS-->>RS: active=false
    RS-->>C: Từ chối xác thực
~~~

**Không thể vừa cache kết quả tích cực độc lập trong một khoảng thời gian đáng kể, vừa bảo đảm mọi lệnh revoke sẽ có hiệu lực ngay lập tức**, trừ khi có cơ chế chủ động thông báo/invalidation đủ tin cậy và được thực thi nhất quán. Ngay cả push invalidation cũng phải tính đến race và lỗi kết nối.

### Lưu ý về “TTL đúng 30 giây”

Một hệ thống có thể có nhiều lớp cache:

~~~text
Resource Server A: local introspection cache
Resource Server B: local introspection cache
                 |
          Shared cache (nếu có)
                 |
         HTTP/proxy/issuer cache
                 |
          Authorization Server
~~~

Không nên khẳng định “revoke có hiệu lực tối đa sau 30 giây” chỉ vì **một** cache trong JVM đặt TTL 30 giây. Issuer có thể cập nhật trạng thái không tức thời; proxy hoặc cache khác có thể giữ response cũ; request đang xử lý vẫn có thể hoàn tất.

**Để cam kết thời gian thu hồi**, phải đo toàn bộ đường đi từ hành động revoke đến quyết định xác thực của mọi Resource Server instance.

## 5. Chọn cache cái gì và tránh cache cái gì

Đối tượng nên cache khi đủ điều kiện:

~~~text
Token T được introspect thành công
    -> OAuth2AuthenticatedPrincipal đáng tin
       attributes + name + authorities
    -> reuseUntil tính từ cache TTL và token exp
~~~

**Chỉ cache kết quả thành công (positive caching)** là chiến lược ban đầu dễ kiểm soát. Tránh nhầm:

| Dữ liệu/kết quả | Chính sách khởi điểm thận trọng |
| --- | --- |
| Principal từ introspection `active: true`, đúng issuer/audience/profile | Có thể cache rất ngắn nếu còn xa `exp` |
| Introspection `active: false` | Không cache theo cùng chính sách positive |
| Kết nối introspection timeout, 5xx hoặc TLS lỗi | Không cache như token hợp lệ; **fail closed** |
| Token thiếu `exp` hoặc `exp` sai kiểu | Không cache nếu không có hợp đồng thời hạn rõ ràng |
| Principal thiếu claim bắt buộc theo profile | Từ chối theo policy; không cache |
| Token sắp hết hạn trong biên an toàn | Trả kết quả theo policy hiện hành nhưng không lưu cache quá `exp` |
| Quyền phụ thuộc membership/share thay đổi từng request | Kiểm tra quan hệ hiện hành riêng hoặc có invalidation chuyên dụng |

### Có nên negative cache?

**Negative caching** là lưu kết quả `active: false` hoặc một lỗi token để tránh gọi issuer lặp lại. Cách này có thể giảm tải khi attacker gửi đi gửi lại một token sai, nhưng có vấn đề riêng:

- Một token được coi không hoạt động ở thời điểm t₀ có thể có trạng thái khác theo chính sách issuer, hoặc có lỗi hạ tầng không phải trạng thái token.
- Cache các lỗi mạng thành `invalid_token` làm khó chẩn đoán và có thể gây gián đoạn dài hơn.
- Có nguy cơ tăng dung lượng cache do attacker tạo vô số chuỗi token khác nhau.

Nếu hệ thống quyết định dùng negative cache, cần chính sách **riêng**, TTL rất ngắn, giới hạn dung lượng và phân biệt lỗi `active: false` với lỗi mạng/issuer. Bài này tập trung vào **positive cache**; không mặc định negative cache là an toàn hoặc cần thiết.

## 6. Chọn cache key: đừng dùng raw access token như khóa tùy tiện

Khóa cache đơn giản nhất là chuỗi token:

~~~java
// Ý tưởng đơn giản nhưng cần tránh ở hệ thống có log/cache monitoring:
cache.getIfPresent(rawAccessToken);
~~~

Bearer token là một **credential**. Nếu hệ thống log key cache, dump heap, hiển thị dashboard key hoặc đặt cache trong dịch vụ ngoài, raw token có thể bị lộ. Một cách giảm rủi ro là dùng **HMAC-SHA-256 của token với secret riêng** làm cache key:

~~~text
raw bearer token
      |
      v
HMAC-SHA-256(token, cache-secret)
      |
      v
Cache key dạng Base64URL/HMAC digest
~~~

Ưu điểm của HMAC so với hash không khóa:

- Không lưu trực tiếp chuỗi bearer token làm key.
- Khi token không có entropy đủ lớn, secret HMAC giúp giảm rủi ro đoán token từ hash bị lộ.
- Có thể đổi HMAC secret và xóa cache trong các sự kiện bảo mật cần thiết.

Nhưng HMAC cache key **không tự mã hóa principal attributes trong value**. Dữ liệu người dùng trong cached value vẫn phải được bảo vệ, giới hạn truy cập và không đưa vào log/metrics.

Cache key còn cần được **phân vùng theo miền tin cậy**. Nếu cùng một cache dùng cho nhiều issuer, nhiều introspection endpoint, nhiều resource audience hoặc nhiều policy xác thực, nên đưa các thành phần ngữ cảnh đó vào khóa hoặc dùng **cache instance riêng cho từng cấu hình**. Không để kết quả được chấp nhận ở API A tự nhiên được dùng như bằng chứng hợp lệ ở API B.

## 7. Ví dụ Java: decorator cache kết quả hợp lệ với Caffeine

Cách tùy chỉnh thuận tiện là xây một lớp triển khai `OpaqueTokenIntrospector` rồi **bọc một delegate đã kiểm tra token thật**. Spring Security sẽ gọi decorator này thay vì gọi trực tiếp introspector từ xa.

Ví dụ dưới đây có các lựa chọn có chủ đích:

1. Cache **chỉ khi** delegate introspection thành công.
2. Không lưu raw bearer token trong cache key; dùng HMAC.
3. Dùng `expireAfterWrite(maxTtl)` để giữ **giới hạn tuổi cache**, không gia hạn khi đọc.
4. Còn kiểm tra `reuseUntil` trên từng hit, giới hạn bởi `exp - safetyMargin`.
5. Không cache nếu thiếu `exp` hoặc không thể hiểu `exp` theo kiểu đã cho phép.
6. Không bắt/làm mất ngoại lệ introspection: lỗi vẫn đi lên authentication layer.
7. Có thể cache principal đã tạo từ introspection nhưng không dùng cache để quyết định quan hệ sở hữu tài nguyên.

Giả định Java 17+, Spring Security Resource Server và Caffeine tương thích với phiên bản build. Các import và code là ví dụ triển khai **local in-memory positive cache**, không phải implementation mặc định của Spring Security.

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class PositiveCachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private record CachedPrincipal(
        OAuth2AuthenticatedPrincipal principal,
        Instant reuseUntil
    ) {}

    private final OpaqueTokenIntrospector delegate;
    private final Cache<String, CachedPrincipal> cache;
    private final Clock clock;
    private final Duration maxTtl;
    private final Duration safetyMargin;
    private final byte[] hmacSecret;

    public PositiveCachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            Clock clock,
            byte[] hmacSecret,
            Duration maxTtl,
            Duration safetyMargin) {

        if (delegate == null || clock == null ||
                hmacSecret == null || hmacSecret.length < 32 ||
                maxTtl == null || maxTtl.isZero() || maxTtl.isNegative() ||
                safetyMargin == null || safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Invalid cache configuration");
        }

        this.delegate = delegate;
        this.clock = clock;
        this.hmacSecret = hmacSecret.clone();
        this.maxTtl = maxTtl;
        this.safetyMargin = safetyMargin;
        this.cache = Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(maxTtl)
            .build();
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String key = cacheKey(token);
        Instant now = clock.instant();
        CachedPrincipal hit = cache.getIfPresent(key);

        if (hit != null && now.isBefore(hit.reuseUntil())) {
            return hit.principal();
        }

        if (hit != null) {
            // Chỉ xóa đúng entry cũ, tránh xóa entry mới của thread khác.
            cache.asMap().remove(key, hit);
        }

        // BẮT BUỘC: delegate thực hiện introspection và kiểm tra token.
        // Nếu active=false hoặc có lỗi, không được tạo positive entry.
        OAuth2AuthenticatedPrincipal verified = delegate.introspect(token);

        Object rawExpiry = verified.getAttribute("exp");
        Instant expiry = expiryInstant(rawExpiry);
        now = clock.instant();

        // Không biết exp -> không cache; policy bắt buộc exp có thể
        // từ chối sớm hơn trong trusted delegate hoặc policy validator.
        if (expiry == null) {
            return verified;
        }

        if (!now.isBefore(expiry)) {
            throw new BadOpaqueTokenException("Access token expired");
        }

        Instant safeExpiry = expiry.minus(safetyMargin);
        Instant cacheLimit = now.plus(maxTtl);
        Instant reuseUntil = safeExpiry.isBefore(cacheLimit)
            ? safeExpiry
            : cacheLimit;

        if (!now.isBefore(reuseUntil)) {
            return verified; // Còn quá ít thời gian để cache an toàn.
        }

        // Sao chép lớp map/collection bên ngoài để tránh mutation trực tiếp.
        // Nếu attributes có object lồng nhau mutable, cần deep freeze/copy
        // theo schema sản phẩm trước khi dùng shared cache.
        OAuth2AuthenticatedPrincipal snapshot =
            new DefaultOAuth2AuthenticatedPrincipal(
                verified.getName(),
                new LinkedHashMap<>(verified.getAttributes()),
                List.copyOf(verified.getAuthorities())
            );

        cache.put(key, new CachedPrincipal(snapshot, reuseUntil));
        return snapshot;
    }

    private static Instant expiryInstant(Object raw) {
        if (raw instanceof Instant instant) {
            return instant;
        }
        if (raw instanceof Date date) {
            return date.toInstant();
        }
        if (raw instanceof Long seconds) {
            return Instant.ofEpochSecond(seconds);
        }
        if (raw instanceof Integer seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }
        // Nếu exp dạng BigDecimal/phân số hoặc kiểu riêng, không đoán đơn vị:
        // chuẩn hóa bằng converter có kiểm tra schema trước khi cache.
        return null;
    }

    private String cacheKey(String token) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacSecret, "HmacSHA256"));
            byte[] digest = mac.doFinal(token.getBytes(
                java.nio.charset.StandardCharsets.UTF_8));
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HMAC unavailable", e);
        }
    }
}
~~~

### Hiểu giới hạn của ví dụ

Đây là **một mẫu triển khai**, không thay thế việc chọn policy phù hợp production:

- **Không có single-flight mặc định:** nhiều request cùng token khi cache miss có thể đồng thời gọi delegate. Khi cần chống cache stampede, hãy dùng cơ chế coalescing theo key và đảm bảo exception không bị biến thành cached success.
- **Cache nằm trong một JVM:** mỗi replica có cache riêng. Muốn invalidation toàn cụm cần thiết kế thêm.
- **Không kiểm tra mọi claim của token ở decorator:** delegate và lớp policy được tin cậy vẫn phải xác minh trạng thái token, issuer, audience, mục đích token và các ràng buộc cần thiết.
- **`exp` không có hoặc sai schema:** ví dụ chọn không cache. Nếu profile bắt buộc `exp`, nơi đánh giá policy phải **từ chối** token không đạt yêu cầu chứ không chỉ bỏ cache.
- **`expireAfterWrite` bảo vệ tuổi entry theo thời gian trôi qua:** đọc cache không gia hạn tuổi dữ liệu; `reuseUntil` ngăn trả principal sau mốc có hiệu lực.
- **Attributes lồng nhau:** bản sao map ở ví dụ là **shallow copy**. Không chia sẻ object mutable hoặc sửa authorities sau khi cache; cần immutable snapshot/deep copy theo schema nếu ứng dụng có mutation.
- **Secret cache key:** phải sinh ngẫu nhiên từ nguồn bảo mật, không hard-code, không log; khi xoay secret cần clear cache nếu cần.
- **Token value vẫn được truyền cho delegate:** HMAC chỉ che giá trị **khóa cache**, không làm token “vô danh” với Authorization Server.

### Công thức thực tế trong ví dụ

Với `maxTtl=30s` và `safetyMargin=5s`:

~~~text
cacheLimit = now + 30s
safeExpiry = exp - 5s
reuseUntil = min(cacheLimit, safeExpiry)

Chỉ cache nếu reuseUntil > now.
Mỗi cache hit yêu cầu now < reuseUntil.
~~~

Điều này ngăn việc **cache tự kéo dài thời hạn token** trong điều kiện đồng hồ và metadata đã được chuẩn hóa đúng. Nó không giải quyết việc issuer thu hồi token **trước `exp`**: kết quả cached vẫn có thể bị chậm thu hồi tới khi hết TTL.

## 8. Cấu hình Spring Boot Resource Server dùng decorator

Dependency Resource Server:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Thêm Caffeine phù hợp với phiên bản dự án:

~~~xml
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
~~~

Ví dụ cấu hình:

~~~yaml
orders:
  introspection:
    uri: https://auth.example.com/oauth2/introspect
    client-id: orders-resource-server
    client-secret: ${INTROSPECTION_CLIENT_SECRET}
    cache-hmac-key-base64: ${INTROSPECTION_CACHE_HMAC_KEY_B64}
    max-cache-seconds: 30
    expiry-safety-seconds: 5
~~~

Secret introspection và HMAC phải được nạp từ secret manager hoặc cấu hình runtime được bảo vệ, không commit giá trị thật vào repository.

Ví dụ bean wiring, với **dòng phiên bản còn có `NimbusOpaqueTokenIntrospector` constructor tương ứng**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class IntrospectionCacheConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${orders.introspection.uri}") String uri,
            @Value("${orders.introspection.client-id}") String clientId,
            @Value("${orders.introspection.client-secret}") String clientSecret,
            @Value("${orders.introspection.cache-hmac-key-base64}") String keyB64,
            @Value("${orders.introspection.max-cache-seconds}") long maxSeconds,
            @Value("${orders.introspection.expiry-safety-seconds}") long guardSeconds) {

        OpaqueTokenIntrospector remote = new NimbusOpaqueTokenIntrospector(
            uri, clientId, clientSecret);

        // Trong hệ thống thật: có thể bọc thêm introspector xác minh
        // audience/issuer/client policy trước khi bọc cache.
        return new PositiveCachingOpaqueTokenIntrospector(
            remote,
            Clock.systemUTC(),
            Base64.getDecoder().decode(keyB64),
            Duration.ofSeconds(maxSeconds),
            Duration.ofSeconds(guardSeconds)
        );
    }
}
~~~

**Lưu ý phiên bản:** Tên class, constructor và builder của introspector từ xa có thể khác giữa các dòng Spring Security; một số class Nimbus được đánh dấu deprecated trong dòng mới hơn. Cần dùng API supported trong version hiện tại, ví dụ triển khai Spring-based khi phiên bản cung cấp. **Nguyên tắc giữ nguyên:** `trusted remote introspector → policy checks → positive cache decorator → Resource Server`.

Security filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {

    @Bean
    SecurityFilterChain apiChain(
            HttpSecurity http,
            OpaqueTokenIntrospector introspector) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(opaque ->
                opaque.introspector(introspector)))
            .build();
    }
}
~~~

Trong ví dụ này:

- Controller/API **không tự cache JWT claims**. Cache được gắn vào introspector dùng bởi provider.
- `SCOPE_orders.read` đến từ authorities của principal mà introspector đã xây. Nếu custom introspector không ánh xạ scope, cần mapping tương ứng.
- Cấu hình tắt CSRF chỉ hợp lý với **stateless API xác thực bằng Bearer token**, không sử dụng cookie/session xác thực tự động từ browser. Ứng dụng có cookie cần đánh giá CSRF riêng.
- `permitAll()` **không tự tắt Bearer filter**. Token sai được gửi đến `/health` vẫn có thể kích hoạt authentication và bị từ chối, trừ khi route dùng chain/resolver riêng theo thiết kế.

### Không cache trước khi kiểm tra audience và issuer

Nếu Authorization Server introspect T và trả `active: true`, nhưng `aud` là `payments-api`, Orders API cần **từ chối token trước khi tạo positive cache entry**. Tương tự, issuer không nằm trong danh sách tin cậy hoặc client không được phép gọi Orders API thì không nên đi vào cache hợp lệ.

Điều này đặc biệt quan trọng khi một introspection endpoint dùng chung cho nhiều tài nguyên. Có thể đặt một **policy-aware decorator** trước positive cache:

~~~text
remote introspection
    -> validate active + issuer/audience/client policy
    -> map attributes và authorities theo contract
    -> positive cache giới hạn TTL/exp
    -> Resource Server authentication
~~~

Nếu policy thay đổi theo request hoặc theo tenant, cần tránh cache một quyết định quá rộng và đem dùng cho ngữ cảnh khác. Khi đó chỉ cache **token metadata đã được issuer xác nhận** và đánh giá quan hệ nghiệp vụ theo request ở tầng service.

## 9. Cache không thay thế quyền theo tenant, owner và đối tượng

Giả sử introspection trả:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read",
  "tenant_id": "t-7",
  "exp": 1893456000
}
~~~

Vài giây sau, user bị **xóa khỏi tenant t-7**. Nếu Resource Server cache principal trong 30 giây, scope/claim cũ vẫn có thể được tái sử dụng. Nhưng **việc một access token có `SCOPE_orders.read` không có nghĩa user vẫn là thành viên của tenant hoặc sở hữu order cụ thể**.

Nên phân tách:

~~~text
CachingOpaqueTokenIntrospector:
    Token có active + scope + identity đáng tin?

OrderPolicy / TenantMembershipService:
    Actor hiện còn quyền ở tenant và order này không?

OrderRepository:
    Truy vấn theo orderId VÀ tenantId được phép.
~~~

Nếu yêu cầu thu hồi membership/share gần tức thời, có thể cần tra DB/service quyền **mỗi request**, hoặc có cache riêng với invalidation khi membership thay đổi. Không dùng TTL introspection dài để mặc định giữ nguyên quyền nghiệp vụ nhạy cảm.

### Scope thay đổi ở Authorization Server

Một issuer có thể thay đổi quyền gắn với token theo chính sách server. Nếu introspection result mới mất `orders.export` nhưng bản cũ trong cache vẫn có `SCOPE_orders.export`, API có thể tiếp tục cho phép export đến khi cache hết hạn. Vì vậy:

- Thời gian cache phải được chọn theo **độ nhạy quyền**, không chỉ latency.
- Với thao tác đặc biệt như duyệt thanh toán, xóa dữ liệu hàng loạt hoặc xuất PII, có thể cần **re-introspection ngay tại thao tác** hoặc cơ chế revocation/invalidation riêng.
- Một token dùng cho nhiều loại endpoint có thể đòi policy thống nhất; tránh giả định “GET rủi ro thấp, POST rủi ro cao” mà không xem nội dung thực.

## 10. Những chiến lược giảm revocation lag

| Chiến lược | Hiệu năng | Tác động thu hồi | Đánh đổi |
| --- | --- | --- | --- |
| **Không cache** | Nhiều request introspection | Thấy trạng thái issuer sớm nhất theo khả năng endpoint | Độ trễ và phụ thuộc mạng cao |
| **Positive cache TTL rất ngắn** | Giảm một phần mạng | Cửa sổ chậm thu hồi ngắn hơn | Vẫn có khoảng stale, cần sizing đúng |
| **Cache TTL theo min(C, exp)** | Không tái sử dụng sau token expiration | Giới hạn theo thời hạn token | Không xử lý revoke trước hạn |
| **Push invalidation/event** | Giảm request lặp | Có thể rút ngắn độ trễ nếu truyền đúng đến mọi instance | Cần vận hành event delivery, idempotency và race handling |
| **Shared cache + invalidation** | Giảm introspection qua nhiều replica | Có một nơi quản lý entry | Cần bảo mật, HA, partition theo issuer/policy, consistency |
| **Local cache + distributed notification** | Latency thấp khi cache hit | Có thể xóa local entries khi có revoke event | Nếu event mất hoặc node offline, vẫn cần TTL cứng |
| **TTL ngắn cho quyền nhạy cảm** | Có thể thêm introspection ở thao tác nhạy cảm | Giảm thời gian stale cho nghiệp vụ quan trọng | Tăng độ phức tạp và phải định nghĩa endpoint/action rõ ràng |

**Không có chiến lược nào tự động biến việc cache thành thu hồi tức thời.** Đặc biệt với event invalidation, phải tính đến:

- Event revoke đến trước hoặc sau một introspection response đang bay trên mạng.
- Node mất kết nối trong lúc event được phát.
- Một node mới khởi động, một node cũ chưa nhận event.
- Issuer có nhiều vùng/replica đồng bộ trạng thái revoke không đồng thời.

TTL cứng vẫn là một **giới hạn an toàn cuối cùng** khi notification thất bại.

## 11. Caching có thể làm mới trạng thái revoke chậm hơn vì sao?

Một anti-pattern là dùng cache **expire after access**:

~~~java
// KHÔNG phù hợp nếu bạn muốn tuổi thông tin introspection
// được giới hạn cứng theo thời điểm fetch.
Caffeine.newBuilder()
    .expireAfterAccess(Duration.ofMinutes(5));
~~~

Với `expireAfterAccess`, mỗi cache hit có thể kéo dài thời gian lưu nếu token tiếp tục được gọi thường xuyên. Một token đã bị thu hồi nhưng vẫn được attacker gọi liên tục có thể được tái sử dụng lâu hơn thời gian mà người vận hành nghĩ là “TTL 5 phút”.

Ưu tiên một cách tính **tuổi tuyệt đối từ lần introspection** như `expireAfterWrite` hoặc `reuseUntil`, không reset chỉ vì token được gửi lại.

### Coi mỗi lần request là “refresh” là sai

Một cache hit không phải một lần Authorization Server xác nhận token vẫn active. Không được cập nhật `validatedAt = now` trên mỗi cache hit nếu muốn xác định thời gian từ **lần introspection gần nhất**.

~~~text
lastVerifiedAt = thời điểm kết quả thực sự được xác nhận bởi issuer
lastUsedAt     = thời điểm token gần nhất được client gửi tới API

Không dùng lastUsedAt để kéo dài lastVerifiedAt.
~~~

Để hạn chế cửa sổ revoke, `reuseUntil` phải được tính từ **lần kết quả đáng tin được nhận**, không từ lần truy cập cache gần nhất.

## 12. Timeout, fail closed và cache trong thời gian sự cố

Nếu introspection endpoint gặp sự cố, Resource Server có thể thấy:

- Lỗi DNS, TLS, connect/read timeout.
- HTTP 429, 5xx hoặc response không hợp lệ.
- Credentials introspection bị thu hồi/sai.
- Authorization Server không đồng bộ trạng thái token.

Các tình huống:

| Tình trạng cache | Introspection endpoint | Hành vi an toàn |
| --- | --- | --- |
| **Cache hit**, entry còn trước `reuseUntil` | Không cần gọi issuer ở request đó | Có thể dùng cached principal theo policy đã chấp nhận revocation lag |
| **Cache miss** | Hoạt động, trả active | Kiểm tra policy và có thể cache positive |
| **Cache miss** | Trả inactive | Từ chối token; không tạo positive entry |
| **Cache miss** | Timeout/5xx | Không có kết quả tin cậy; **không cho qua** |
| **Cache entry đã hết hạn** | Timeout/5xx | Không kéo dài entry chỉ vì issuer lỗi, trừ khi có policy stale-on-error được phê duyệt riêng |
| **Token đã đến `exp`** | Bất kỳ | Không dùng cache để kéo dài thời hạn token |

**Fail closed** nghĩa là không chấp nhận token chưa được xác minh theo chính sách. Nó không đồng nghĩa mọi lỗi hạ tầng phải được mô tả là `401 invalid_token`; HTTP response có thể tùy handler/implementation và cách phân biệt lỗi token với lỗi dịch vụ.

### Stale-while-error rất nhạy cảm

Một hệ thống có thể muốn dùng cache cũ khi issuer outage để duy trì availability. Đây là quyết định rủi ro riêng: token có thể đã revoke, scope có thể đã bị thu hẹp, hoặc issuer đang xử lý sự cố an ninh.

Không mặc định triển khai:

~~~java
// KHÔNG LÀM VỚI MỌI LỖI:
// try introspection, catch Exception -> return cached principal mãi mãi
~~~

Nếu thật sự được phép stale-on-error, cần giới hạn tuổi stale tuyệt đối, không bao giờ vượt `exp`, xác định endpoint/action nào đủ rủi ro thấp, log/audit, và có cơ chế dừng khi nghi ngờ token compromise. Với các thao tác nhạy cảm, **không chấp nhận việc dùng cache hết hạn như một fallback mặc định**.

## 13. Hiệu năng, cache stampede và giới hạn tài nguyên

Giả sử API có 2.000 request/giây nhưng chỉ 50 token đang được sử dụng. Positive cache TTL ngắn có thể giảm đáng kể số lời gọi introspection vì mỗi token được xác minh lại theo chu kỳ thay vì mỗi request.

Tuy nhiên, hiệu năng cache phụ thuộc phân bố traffic:

- **Nhiều request lặp lại cùng token:** cache hit cao.
- **Nhiều token chỉ dùng một lần:** cache hit thấp, tốn bộ nhớ cho entry hiếm khi được tái sử dụng.
- **Token TTL rất ngắn:** thời gian cache hiệu dụng bị giới hạn bởi `exp`.
- **Nhiều replica:** mỗi replica có cache riêng và có thể introspect cùng token ở thời điểm khác nhau.
- **Cache miss đồng thời:** nhiều thread cùng gọi issuer với một token hoặc nhiều token.

Trong ví dụ Java ở mục 7, `getIfPresent → delegate → put` có thể gây **cache stampede** trên cùng một key khi nhiều request đến đồng thời. Một bản production có thể bổ sung **single-flight/per-key request coalescing**, nhưng phải:

1. Chỉ chia sẻ **kết quả đang xác minh**, không chấp nhận token trước khi delegate trả thành công.
2. Không biến timeout/exception thành cached principal.
3. Giới hạn số lượng request đang chờ để tránh giữ thread vô hạn.
4. Không giữ lock toàn cục khi gọi introspection; điều này sẽ làm mọi token chờ nhau.
5. Phân biệt cache key theo issuer/policy nếu hệ thống nhiều nguồn token.

### Giới hạn số entry

Attacker có thể gửi hàng nghìn token rác, gây tải introspection dù không cache positive. Cần có rate limiting, timeout, connection pool phù hợp và bảo vệ tầng API. Cache nên giới hạn số entry, eviction và memory budget. Đừng dùng token string hoặc digest không giới hạn làm **metric labels** khiến monitoring tăng cardinality.

## 14. Cache trong nhiều Resource Server instance

Giả sử Orders API chạy trên ba replica:

~~~text
Client
  |
Load Balancer
  |
  +-- API instance A -> local cache A
  +-- API instance B -> local cache B
  +-- API instance C -> local cache C
                          |
                   Introspection endpoint
~~~

Cùng token T có thể:

- Được cache tại A lúc 10:00:00.
- Được cache tại B lúc 10:00:10.
- Được cache tại C lúc 10:00:20.

Nếu T bị revoke lúc 10:00:25 và TTL là 30 giây, các instance có mốc cache khác nhau. **Thời điểm revoke có hiệu lực trên toàn cụm phụ thuộc cache entry cuối cùng được xác nhận trước revoke**, cùng điều kiện issuer propagation. Vì thế test trên một instance không đủ kết luận cả cụm đã từ chối token.

Với cache phân tán, cần quan tâm:

- Giá trị cached principal có thể chứa metadata nhạy cảm; phải mã hóa kênh và giới hạn truy cập.
- Serializer/deserializer phải bảo toàn authorities và kiểu thời gian đúng.
- Cache key cần phân vùng theo issuer, audience, tenant/policy nếu phù hợp.
- Invalidation phải đến mọi node hoặc mọi entry cùng khóa.
- Redis/distributed cache có thể gặp consistency lag hoặc lỗi mạng; không được fallback sang chấp nhận token chưa kiểm tra.
- TTL ở distributed cache và TTL ở local cache phải được tính cùng nhau, tránh nhiều tầng kéo dài revocation window.

Không nên chia sẻ một cache principal giữa những Resource Server có **chính sách audience hoặc authority mapping khác nhau** chỉ vì chuỗi bearer token giống nhau.

## 15. Quan sát cache và kiểm thử hành vi thu hồi

Một số chỉ số hữu ích:

| Metric/tín hiệu | Ý nghĩa |
| --- | --- |
| Cache hit/miss theo issuer và application | Đánh giá cache có thực sự giảm introspection |
| Số request introspection mỗi giây | Tải trên issuer và tỷ lệ tái sử dụng token |
| P50/P95/P99 latency introspection | Độ trễ tác động tới request |
| Introspection timeout/5xx/429 | Sự cố mạng/issuer |
| Số active=false theo nguyên nhân tổng quát | Tình trạng token bị từ chối |
| Tuổi entry khi cache hit | Phát hiện cached data quá cũ hoặc bị gia hạn sai |
| Thời gian từ revoke đến lần đầu mọi instance từ chối | Revocation lag đo được end-to-end |
| Tỷ lệ request bị từ chối do thiếu scope/tenant | Phân biệt xác thực token và quyền nghiệp vụ |

Không log **raw access token**, HMAC secret hoặc toàn bộ response introspection. Có thể ghi request ID, issuer đã được xác minh, loại lỗi, kết quả xác thực và cache hit/miss; giới hạn cardinality và thông tin nhận diện.

### Ma trận kiểm thử bắt buộc cho cách triển khai cache

Giả sử policy max TTL 30 giây, safety margin 5 giây:

| Tình huống | Kỳ vọng |
| --- | --- |
| Lần đầu T active, `exp` còn xa | Delegate được gọi, lưu positive entry |
| Request lặp lại T trong TTL | Cache hit, không gọi delegate lại |
| Sau TTL 30 giây | Cache miss, gọi lại introspection |
| Token hết hạn sau 20 giây | Cache chỉ đến trước `exp` khoảng 5 giây |
| Token hết hạn trong 4 giây | Không cache; không tái sử dụng sau `exp` |
| Introspection trả inactive | Từ chối; không tạo positive cache |
| Introspection timeout/5xx | Fail closed; không lưu như token active |
| Token revoked trong TTL | Có thể vẫn được chấp nhận đến khi entry hết hiệu lực |
| Token revoked sau khi cache đã hết hạn | Lần kiểm tra tiếp theo phải phản ánh trạng thái issuer |
| Issuer đổi scope/permission | Cache hit có thể giữ authorities cũ cho tới hết TTL |
| Token thiếu `exp` theo policy không cache | Delegate được gọi ở mỗi request; validator profile quyết định có chấp nhận hay không |
| Cùng token nhưng khác issuer/policy cache | Không dùng lẫn cached principal |
| Nhiều request đồng thời khi cache miss | Kiểm tra load/stampede và giới hạn concurrency |
| Nhiều replica có TTL lệch pha | Đo revoke lag trên tất cả instance, không chỉ một node |

### Test không dùng Thread.sleep để đo mốc biên

Để kiểm tra logic `reuseUntil`, có thể inject `Clock.fixed(...)` hoặc một **MutableClock** trong unit test. Caffeine `expireAfterWrite` dùng ticker riêng theo thời gian trôi qua, vì vậy test chỉ đổi `Clock` không mặc nhiên làm entry trong Caffeine hết hạn. Khi kiểm tra TTL thực tế, cần cấu hình **fake ticker** cho Caffeine hoặc test logic time và cache expiry riêng.

Ví dụ skeleton kiểm tra hành vi:

~~~java
// Pseudocode / test plan:
// 1. fake delegate trả principal với exp = T + 20s.
// 2. Đặt Clock ở T.
// 3. introspect("T") -> delegateCalls == 1, cache positive tới T+15s.
// 4. Đổi Clock thành T+10s; introspect("T") -> cache hit.
// 5. Đổi Clock thành T+16s; introspect("T") -> gọi delegate lại.
// 6. Cho delegate báo inactive; introspect("T") phải thất bại.
//
// Test riêng Caffeine expireAfterWrite(30s) bằng ticker giả
// để xác minh eviction theo thời gian trôi qua.
~~~

### Unit test decorator không thay thế end-to-end revocation test

Một fake introspector trả principal đã được xây bằng tay chỉ chứng minh **cách cache hoạt động**, không chứng minh:

- Kết nối introspection dùng TLS và credentials đúng.
- Response `active: false` được remote introspector xử lý đúng.
- Claims `exp`, `scope`, `aud` được chuyển kiểu chính xác.
- Filter chain thật tạo `BearerTokenAuthentication`, trả 401/403 phù hợp.
- Event thu hồi được truyền giữa các instance và issuer.

Khi triển khai hệ thống, cần kiểm tra tích hợp bằng introspection endpoint test/stub HTTP, token được quản lý bởi Authorization Server test và những request đi qua **SecurityFilterChain thật**. MockMvc post-processor `opaqueToken()` của Spring Security Test thường tạo Authentication thử nghiệm và **bỏ qua introspector/cache thật**, nên không chứng minh revocation lag.

## 16. Khi nào không nên cache kết quả introspection?

Một số tình huống nên tránh positive cache hoặc đặt TTL rất nhỏ:

- Hệ thống có yêu cầu **thu hồi access token gần như tức thời**, chẳng hạn giao dịch tài chính nhạy cảm.
- Token/authorization state có thể thay đổi thường xuyên và quyết định quyền phải phản ánh ngay.
- Introspection response thiếu thời hạn hoặc profile token không cho phép xác định `exp` đáng tin.
- Một cache chung được đề xuất cho nhiều issuer/resource có policy không đồng nhất.
- Không kiểm soát được dữ liệu principal nhạy cảm trong cache/dump/log.
- Không có cơ chế bảo vệ khi issuer outage và cache bị hết hạn.
- Mức độ lợi ích cache thấp do mỗi token hiếm khi được tái sử dụng.

**Không cache** là một lựa chọn bảo mật hợp lệ. Nó tăng số request mạng nhưng giảm khả năng dùng kết quả introspection cũ. Ngay cả khi không cache, trạng thái thu hồi vẫn phụ thuộc thời điểm Authorization Server công bố thay đổi và độ trễ xử lý request.

## 17. Những hiểu nhầm phổ biến

**“Token có `exp` còn 15 phút nên cache introspection 15 phút là an toàn.”**  
Không. Token có thể bị revoke hoặc bị đổi quyền trước `exp`. Cache cần giới hạn riêng theo khả năng chấp nhận revocation lag.

**“TTL cache 30 giây sẽ tự làm JWT hoặc opaque token hết hạn sau 30 giây.”**  
Không. TTL chỉ quyết định thời gian **reuse kết quả introspection**. Token lifetime do Authorization Server và metadata quyết định.

**“`active: true` nghĩa là có thể dùng kết quả mãi đến `exp`.”**  
Không. `active: true` là một snapshot tại thời điểm introspection, không phải một bảo đảm bất biến.

**“Có `exp` thì không cần kiểm tra revoke.”**  
Không. `exp` là thời hạn tối đa, còn revoke có thể xảy ra sớm hơn.

**“Cache hit nghĩa là vừa xác minh lại token.”**  
Không. Cache hit chỉ tái sử dụng một quyết định trước đó. `lastUsedAt` không được coi là `lastVerifiedAt`.

**“Expire-after-access phù hợp vì token hay dùng thì nên được cache lâu.”**  
Không khi mục tiêu là giới hạn revocation lag. Hoạt động đều đặn của token có thể kéo dài entry quá mức dự kiến.

**“Introspection endpoint lỗi thì dùng cached result đã hết hạn để tránh 401.”**  
Đây là stale-on-error và cần phê duyệt rủi ro riêng; không được mặc định mở rộng TTL vô hạn hoặc vượt `exp`.

**“Chỉ cần dùng SHA-256 token làm key là đã giải quyết toàn bộ bảo mật cache.”**  
Không. HMAC với secret giúp bảo vệ key tốt hơn trong một số tình huống, nhưng còn cần bảo vệ cached value, memory, persistence, endpoint, dữ liệu nhiều issuer và log.

**“Cache principal có `SCOPE_orders.read` là đủ để đọc mọi đơn hàng.”**  
Không. Owner, tenant membership, sharing và quyền trên tài nguyên phải được kiểm tra theo nghiệp vụ.

**“Spring Security có mặc định positive cache cho mọi opaque token.”**  
Không được giả định như vậy. Hành vi cache phụ thuộc implementation, phiên bản và cấu hình. Khi cần chính sách TTL/thu hồi cụ thể, hãy cấu hình introspector hoặc tầng cache do ứng dụng quản lý và xác minh đúng đường đi runtime.

## 18. Khung quyết định khi thiết kế caching introspection

Trước khi bật cache kết quả hợp lệ, hãy xác định:

1. **Token được xác minh bởi ai?** Chỉ introspect tại endpoint của issuer đáng tin; bảo vệ credentials và TLS.
2. **Chính sách token nào phải đúng?** `active`, issuer, audience, mục đích access token, thời hạn, client và claim bắt buộc.
3. **Kết quả nào được cache?** Positive principal đã được xác minh và ánh xạ authorities, không cache lỗi mạng như thành công.
4. **TTL tối đa là bao nhiêu?** Chọn từ yêu cầu revocation lag, không chỉ dựa vào thông số hiệu năng.
5. **Có `exp` đáng tin không?** Dùng `reuseUntil=min(now+C, exp-δ)`; thiếu thông tin thì không cache hoặc theo policy chặt hơn.
6. **Có cache nào khác không?** Local JVM, shared cache, proxy hoặc issuer có thể cùng ảnh hưởng trạng thái stale.
7. **Cache key được bảo vệ ra sao?** Không log raw token, ưu tiên HMAC key với secret riêng và phân vùng theo issuer/policy.
8. **Ai thu hồi quyền nghiệp vụ?** Membership, owner, sharing và sensitive actions cần kiểm tra/invalidation riêng.
9. **Lỗi mạng được xử lý thế nào?** Cache miss và lỗi introspection phải fail closed; stale-on-error cần quyết định bảo mật rõ ràng.
10. **Kiểm thử revoke lag ở đâu?** Test từ Authorization Server đến mọi Resource Server instance, bao gồm TTL, cache expiry và propagation.

**Điểm cần nhớ:** Cache introspection giúp giảm độ trễ và tải cho Authorization Server, nhưng mỗi positive cache hit đang **tin lại một quyết định cũ**. Quy tắc an toàn là **cache ngắn, giới hạn bởi `exp`, không kéo dài khi truy cập, không cache lỗi như thành công, bảo vệ cache key/value, giữ nguyên validation và phân quyền nghiệp vụ**. Cửa sổ chậm thu hồi phải là **một đánh đổi được thiết kế, đo lường và chấp nhận rõ ràng**, không phải tác dụng phụ bị bỏ quên khi tối ưu hiệu năng.
