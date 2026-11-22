# Đánh đổi giữa cache kết quả introspection và độ trễ thu hồi

## 1. Bối cảnh và mục tiêu

Trong hệ thống **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, Resource Server có thể xác minh access token dạng JWT bằng chữ ký và claims. Với access token dạng reference/opaque, Resource Server thường gọi **Token Introspection Endpoint** để hỏi Authorization Server token còn active hay không và lấy các thuộc tính như scope, client, subject, audience, thời hạn.

Gọi introspection cho từng request giúp Resource Server nhận trạng thái token mới nhất theo khả năng nhất quán của Authorization Server, nhưng tạo thêm độ trễ mạng, tải cho endpoint và phụ thuộc availability của Authorization Server. Cache kết quả introspection giảm số lần gọi mạng, nhưng tạo ra một khoảng thời gian mà Resource Server có thể tiếp tục chấp nhận token đã bị thu hồi.

Ví dụ xuyên suốt: Orders API nhận 8.000 request/giây từ các service dùng opaque access token. Authorization Server có thể xử lý introspection, nhưng mỗi lần gọi mạng làm tăng latency và tải. Đội vận hành muốn cache kết quả <code>active=true</code> trong một khoảng ngắn. Đồng thời, khi quản trị viên thu hồi token do service account bị lộ, API phải ngừng chấp nhận token trong một SLA đã cam kết.

Sau bài học, bạn có thể:

1. Giải thích chính xác cache introspection tiết kiệm gì và làm chậm thu hồi như thế nào.
2. Tính cửa sổ tối đa mà một cache có thể tiếp tục tin kết quả <code>active=true</code> cũ.
3. Chọn TTL dựa trên <code>exp</code>, yêu cầu revocation SLA, thời gian phân phối invalidation và rủi ro của API.
4. Phân biệt cache positive, cache negative, cache lỗi và cache HTTP; biết trường hợp nào không được lưu.
5. Thiết kế cache một tầng hoặc nhiều tầng mà không vô tình gia hạn freshness.
6. Bọc <code>OpaqueTokenIntrospector</code> trong Spring Security bằng cache có TTL và key an toàn.
7. Xử lý revocation event, token family, introspection outage và quyết định fail-open/fail-closed.
8. Đo latency, hit ratio, stale acceptance window và kiểm thử thu hồi end-to-end.

**Phạm vi phiên bản:** Ví dụ dùng Spring Security 6.x và Spring Authorization Server 1.x với Servlet Resource Server. <code>OpaqueTokenIntrospector</code> là extension point của Spring Security. Caffeine là thư viện cache minh họa; có thể thay bằng cache phân tán. API tạo introspector HTTP có thể khác giữa các phiên bản, vì vậy phần cấu hình tập trung vào cách bọc một introspector đã được cấu hình đúng.

## 2. Introspection là quyết định trạng thái token

### 2.1. Request và response cơ bản

Resource Server gửi token tới introspection endpoint qua HTTPS và xác thực chính nó theo policy của Authorization Server:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-credential>
Content-Type: application/x-www-form-urlencoded

token=opaque-access-token-value
~~~

Response active có thể chứa các metadata:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "scope": "orders.read",
  "client_id": "orders-worker",
  "sub": "service-account-orders",
  "aud": ["https://orders-api.example.com"],
  "iss": "https://auth.example.com",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "token-7f31"
}
~~~

Response trên chỉ là ví dụ về các trường thường gặp; <code>exp</code>, <code>aud</code>, <code>sub</code>, <code>jti</code> và các metadata khác phụ thuộc token và cấu hình. Header <code>Cache-Control: no-store</code> được đưa vào để minh họa một response cấm lưu cache. Nếu Authorization Server thực tế trả <code>no-store</code>, Resource Server phải tôn trọng chỉ thị đó; không được lách bằng cách bọc introspector trong một cache ứng dụng rồi vẫn lưu response.

### 2.2. <code>active</code> có nghĩa gì?

<code>active=true</code> có nghĩa Authorization Server xác nhận token đang active theo trạng thái và policy của nó tại thời điểm xử lý introspection. Token có thể bị xem là inactive vì không tồn tại, sai, hết hạn, bị thu hồi hoặc không còn được phép sử dụng. Authorization Server không nhất thiết tiết lộ lý do cụ thể.

<code>active=false</code> là câu trả lời về trạng thái token, không đồng nghĩa endpoint bị lỗi. Cần phân biệt:

| Kết quả | Ý nghĩa | Hành động của Resource Server |
| --- | --- | --- |
| <code>active=true</code> | Token active theo Authorization Server. | Tiếp tục kiểm tra issuer, audience, expiry, scope và policy API. |
| <code>active=false</code> | Token không được phép dùng tại thời điểm introspection. | Từ chối request xác thực. |
| Timeout/connection failure | Không biết trạng thái token vì không nhận được câu trả lời. | Áp dụng chính sách outage; không coi timeout là <code>active=true</code> hay <code>active=false</code>. |
| 401/403 từ introspection | Client xác thực introspection không hợp lệ hoặc không được phép. | Sửa cấu hình/credential và từ chối quyết định dựa trên kết quả không hợp lệ. |
| 5xx/JSON lỗi | Endpoint hoặc giao thức gặp sự cố. | Báo lỗi dịch vụ, không cache như một kết quả token. |

Introspection chỉ là một phần của authorization. Token <code>active=true</code> vẫn có thể không được phép gọi Orders API nếu audience không đúng hoặc scope không đủ.

### 2.3. Vì sao introspection hỗ trợ thu hồi?

Với reference token, Authorization Server có thể tra cứu trạng thái token trong kho authorization. Khi token bị revoke, trạng thái có thể chuyển từ active sang inactive. Request introspection kế tiếp sẽ nhận được trạng thái mới sau khi thay đổi đã được commit và nhất quán trên hệ thống.

Resource Server chỉ biết thay đổi đó khi hỏi lại Authorization Server hoặc nhận được một tín hiệu invalidation đáng tin cậy. Nếu Resource Server đang dùng kết quả active đã cache, nó vẫn có thể chấp nhận token cho đến khi cache hết hạn hoặc bị xóa.

## 3. Cache giúp gì và đánh đổi điều gì?

### 3.1. Không cache: trạng thái mới nhất nhưng có chi phí mạng

Với mỗi API request:

1. Resource Server nhận bearer token.
2. Gọi introspection endpoint qua HTTPS.
3. Chờ Authorization Server xác minh token.
4. Nhận active/metadata.
5. Kiểm tra scope, audience và authorization của request.

Ưu điểm là không giữ kết quả active cũ lâu trong Resource Server. Nhược điểm là mỗi request phụ thuộc network và introspection capacity; nếu API có lưu lượng lớn, số request introspection gần bằng số request API.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API Client
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    C->>RS: GET /orders + opaque access token
    RS->>AS: POST /oauth2/introspect
    AS-->>RS: active=true + scope + aud + exp
    RS->>RS: Kiểm tra scope/audience
    RS-->>C: 200 OK
~~~

### 3.2. Cache: giảm gọi introspection nhưng chấp nhận trạng thái cũ

Nếu Resource Server cache <code>active=true</code>, những request tiếp theo với cùng token có thể được xác thực cục bộ trong thời gian cache còn fresh:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API Client
    participant RS as Orders Resource Server + Cache
    participant AS as Authorization Server
    C->>RS: Request 1 với token T
    RS->>AS: Introspect T (cache miss)
    AS-->>RS: active=true
    RS->>RS: Cache metadata của T
    RS-->>C: 200 OK
    C->>RS: Request 2 với token T
    RS->>RS: Cache hit, chưa gọi AS
    RS-->>C: 200 OK
    Note over AS,RS: Token T bị revoke tại AS
    C->>RS: Request 3 với token T
    RS->>RS: Cache vẫn fresh
    RS-->>C: Có thể vẫn 200 cho đến khi cache hết hạn
    RS->>AS: Introspect lại sau khi cache hết hạn
    AS-->>RS: active=false
    RS-->>C: 401 Unauthorized
~~~

Cache không làm Authorization Server revoke chậm hơn; nó làm **Resource Server phát hiện trạng thái revoke chậm hơn**. Đây là khác biệt quan trọng khi xác định SLA.

### 3.3. Bảng đánh đổi

| Không cache | Cache kết quả |
| --- | --- |
| Mỗi request tạo network round trip. | Cache hit không cần gọi introspection. |
| Latency phụ thuộc Authorization Server và mạng. | Latency thấp, ổn định hơn khi cache hit. |
| Tải introspection tăng theo lưu lượng API. | Tải giảm theo số token khác nhau và TTL. |
| Trạng thái revoke được nhận biết ở lần introspection tiếp theo. | Token active cũ có thể được chấp nhận đến khi cache hết hạn/invalidate. |
| Availability API phụ thuộc khả năng gọi AS. | Cache fresh có thể phục vụ request trong lúc AS tạm thời lỗi. |
| Dễ quan sát trạng thái trung tâm. | Phải quản lý cache consistency, invalidation và stale data. |

## 4. Định lượng cửa sổ trễ thu hồi

### 4.1. Công thức cơ bản

Giả sử:

- <code>T</code> là TTL tối đa của kết quả <code>active=true</code> trong Resource Server.
- <code>t_r</code> là thời điểm Authorization Server commit việc revoke token.
- <code>t_c</code> là thời điểm cache entry được tạo hoặc refresh gần nhất.
- <code>t_e = t_c + T</code> là thời điểm cache entry hết hạn.

Nếu không có invalidation push, Resource Server có thể tiếp tục tin kết quả cũ đến <code>t_e</code>. Trong trường hợp xấu nhất, cache vừa được làm mới ngay trước khi revoke xảy ra:

\[
W_{\text{stale}} \leq T + \epsilon
\]

Trong đó <code>ε</code> bao gồm thời gian xử lý request đang chạy, sai số đồng hồ và các khoảng trễ triển khai. Nếu TTL được tính theo đồng hồ monotonic và cache không phục vụ entry quá hạn, phần sai số có thể được kiểm soát nhỏ.

**Ví dụ:** Cache active introspection 30 giây. Token bị revoke ngay sau một cache hit/fill. Resource Server có thể chấp nhận token thêm gần 30 giây. Nếu SLA yêu cầu token bị revoke phải ngừng được chấp nhận trong tối đa 5 giây, TTL 30 giây không đáp ứng.

### 4.2. Có invalidation push

Giả sử hệ thống có event revocation được phát từ Authorization Server tới các Resource Server. Gọi <code>P</code> là thời gian lớn nhất từ lúc revoke được commit đến khi tất cả cache liên quan nhận và áp dụng invalidation. Nếu event được giao tin cậy và cache xóa đúng entry, độ trễ stale có thể được chặn bởi TTL hoặc thời gian phân phối event:

\[
W_{\text{stale}} \leq \min(T, P) + \epsilon
\]

Đây chỉ là giới hạn khi invalidation được bảo đảm đến mọi verifier. Nếu event có thể mất, subscriber có thể offline hoặc node mới không tải lại trạng thái revoked, TTL là fallback và bound thực tế phải tính theo đường khôi phục event. Không lấy thời gian publish event làm bằng chứng mọi cache đã xóa.

### 4.3. Tính TTL theo revocation SLA

Gọi:

- <code>D</code> là SLA tối đa từ lúc revoke commit đến lúc API từ chối token.
- <code>P</code> là ngân sách phân phối invalidation lớn nhất.
- <code>M</code> là margin cho clock skew, request in-flight, scheduler và propagation.

Nếu không có invalidation tin cậy, chọn:

\[
T \leq D - M
\]

Nếu có invalidation tin cậy và đã đo/kiểm soát được propagation:

\[
\min(T, P) + M \leq D
\]

Khi không thể bảo đảm <code>P</code>, không dùng công thức có <code>P</code> để biện minh cho TTL lớn. Dùng TTL fallback và đo thời gian invalidation thực tế.

Ví dụ: SLA là 10 giây, event invalidation có mục tiêu tối đa 3 giây, margin 2 giây. Khi event hoạt động đúng, stale window được chặn bởi event; nhưng nếu event mất, TTL fallback phải vẫn đáp ứng SLA. Vì vậy, nếu không có cơ chế xác nhận/repair event mạnh, TTL an toàn vẫn nên không vượt 8 giây (<code>D - M</code>).

### 4.4. TTL phải bị giới hạn bởi exp

Nếu introspection trả <code>exp</code>, cache không được giữ entry active lâu hơn thời điểm token hết hạn:

\[
T_{\text{effective}} =
\min(T_{\text{configured}},\; exp - now,\; T_{\text{revocation-budget}})
\]

Không cache quá thời điểm <code>exp</code>, kể cả cache TTL cấu hình còn dài. Nếu response không có <code>exp</code>, dùng TTL tối đa được thỏa thuận với Authorization Server và vẫn phải tuân thủ revocation SLA.

Thêm margin nếu clock giữa Resource Server và Authorization Server không đồng bộ. Không kéo dài cache entry để bù clock skew; hãy đồng bộ thời gian và dùng khoảng đệm an toàn để token không được chấp nhận quá hạn.

## 5. Những loại cache và chính sách tương ứng

### 5.1. Positive cache: <code>active=true</code>

Đây là cache đem lại phần lớn lợi ích hiệu năng. Tuy nhiên, nó cũng là nơi tạo ra stale-positive window khi token bị revoke.

Chỉ lưu positive result khi:

- Introspection response đến từ Authorization Server đã được xác thực qua HTTPS và client authentication đúng.
- Response hợp lệ, parse thành công và <code>active=true</code>.
- Cache policy của Authorization Server/contract cho phép lưu.
- TTL không vượt <code>exp</code>, revocation SLA hoặc policy của resource.
- Principal/attributes được lưu là immutable hoặc không bị request khác sửa đổi.

Không biến một response lỗi hoặc timeout thành positive result. Không cache principal với scope/audience được suy ra từ request hiện tại thay vì introspection response.

### 5.2. Negative cache: <code>active=false</code>

Cache <code>active=false</code> không làm chậm việc revoke; nó có thể giảm request lặp lại cho token không hợp lệ. Nhưng nếu Authorization Server có eventual consistency hoặc token vừa được phát hành chưa đồng bộ tới mọi node, negative cache có thể làm chậm việc chấp nhận token hợp lệ.

Khuyến nghị:

- Mặc định không cache inactive response nếu không có nhu cầu rõ ràng.
- Nếu cần chống lặp request cho token không hợp lệ, dùng TTL rất ngắn và giới hạn dung lượng.
- Không cache lỗi introspection, timeout, 5xx, 401/403 hoặc JSON không hợp lệ thành <code>active=false</code>.
- Dùng token hash làm cache key; không lưu raw bearer token trong key/log.
- Đánh giá nguy cơ token scanning và không để cache negative trở thành oracle tiết lộ trạng thái token.

### 5.3. Error cache

Không cache các lỗi như:

- Timeout hoặc connection reset.
- Authorization Server trả 5xx.
- Client introspection credential sai.
- TLS certificate validation thất bại.
- JSON response hỏng hoặc không đúng schema.
- Rate limit/429.

Các lỗi này nói rằng Resource Server chưa có quyết định hợp lệ. Cache chúng như inactive có thể gây từ chối nhầm token sau khi dịch vụ phục hồi; cache chúng như active là fail-open nguy hiểm. Hãy dùng circuit breaker/retry có giới hạn và chính sách outage riêng.

### 5.4. HTTP cache và application cache

HTTP cache tuân theo semantics của HTTP headers như <code>Cache-Control</code>, <code>Age</code>, <code>Date</code>, <code>Expires</code>, <code>Vary</code> và các chỉ thị liên quan. Application cache trong Java (Caffeine, Redis, cache decorator) là một tầng logic khác.

Nếu Authorization Server trả:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

thì client không được lưu response để tái sử dụng. Không được bỏ qua <code>no-store</code> chỉ vì muốn giảm latency. Nếu Authorization Server cho phép cache theo một hợp đồng riêng, phải xác định TTL, scope của cache, cách xử lý token revoke và header thực tế; không tự suy ra cache được phép chỉ vì response là HTTP 200.

Một <code>OpaqueTokenIntrospector</code> tiêu chuẩn trả về <code>OAuth2AuthenticatedPrincipal</code>, thường không phơi bày HTTP response headers cho lớp bọc. Nếu cần tôn trọng cache directive động từ từng response, tầng HTTP transport phải đưa cache policy vào lớp cache hoặc không dùng cache decorator đơn giản. Đừng viết cache wrapper không thể quan sát <code>no-store</code> rồi mặc định lưu mọi principal.

## 6. Thiết kế cache key và dữ liệu cache

### 6.1. Không dùng raw bearer token làm cache key

Bearer token là credential: ai có token có thể sử dụng quyền của nó. Nếu cache key được ghi vào log, dump, metrics label hoặc distributed cache, raw token có thể bị lộ.

Dùng một digest một chiều của token:

\[
K = SHA\text{-}256(issuer \parallel 0x00 \parallel token)
\]

Có thể bổ sung resource-server identity, introspection endpoint hoặc policy version nếu cache dùng chung cho nhiều issuer/resource server. Không dùng token string trong log, tracing span, metric label hay exception.

Ví dụ helper:

~~~java
static String cacheKey(String issuer, String token) {
    try {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        digest.update(issuer.getBytes(StandardCharsets.UTF_8));
        digest.update((byte) 0);
        digest.update(token.getBytes(StandardCharsets.UTF_8));
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest.digest());
    } catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException("SHA-256 unavailable", ex);
    }
}
~~~

SHA-256 ở đây dùng để tạo cache key, không phải xác minh tính hợp lệ của token. Không đưa cache key vào metric label vì cardinality sẽ rất lớn; log key chỉ khi cần điều tra và vẫn phải tuân theo policy dữ liệu.

### 6.2. Cache principal và metadata cần thiết

Một cache entry có thể chứa:

- <code>OAuth2AuthenticatedPrincipal</code> từ introspector.
- Thời điểm <code>freshUntil</code> tuyệt đối.
- Token expiration (<code>exp</code>) nếu có.
- Issuer/resource-server policy version để invalidation khi policy đổi.
- Metadata phục vụ index invalidation như authorization ID hoặc <code>jti</code> nếu được introspection trả về và contract cho phép.

Không cache nguyên request HTTP, client secret introspection hoặc raw token. Không dùng một cache key chỉ dựa trên <code>jti</code> nếu <code>jti</code> không duy nhất trên mọi issuer; ít nhất phải namespace theo issuer.

### 6.3. Cache object phải không bị mutate

Nếu principal hoặc attributes chứa collection mutable, một request có thể sửa dữ liệu rồi ảnh hưởng request tiếp theo dùng chung cache entry. Nên lưu representation immutable hoặc deep-copy những cấu trúc cần thiết. Không gắn request-specific state như correlation ID, servlet request hay security context vào object cache dùng chung.

## 7. Caching OpaqueTokenIntrospector trong Spring Security

### 7.1. Extension point

Spring Security dùng interface:

~~~java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
~~~

Resource Server gọi <code>introspect(token)</code> khi xử lý bearer token dạng opaque. Một implementation HTTP gọi Authorization Server; cache có thể được đặt thành decorator bên ngoài implementation đó:

~~~text
BearerTokenAuthenticationFilter
  -> OpaqueTokenAuthenticationProvider
    -> CachingOpaqueTokenIntrospector
      -> Remote OpaqueTokenIntrospector
        -> Authorization Server /oauth2/introspect
~~~

Decorator chỉ cache kết quả introspection đã thành công. Nó không thay đổi cách xác thực client tại introspection endpoint hoặc cách Authorization Server xác định token active.

### 7.2. Caffeine cache với TTL bị giới hạn

Ví dụ sau minh họa positive cache. Cấu hình chỉ được bật khi hợp đồng introspection cho phép lưu kết quả và response không có <code>no-store</code>. Mã lược bỏ import:

~~~java
public final class CachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Cache<String, CacheEntry> cache;
    private final Clock clock;
    private final String issuer;
    private final Duration maxTtl;
    private final Duration revocationBudget;

    public CachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            Cache<String, CacheEntry> cache,
            Clock clock,
            String issuer,
            Duration maxTtl,
            Duration revocationBudget) {
        this.delegate = Objects.requireNonNull(delegate);
        this.cache = Objects.requireNonNull(cache);
        this.clock = Objects.requireNonNull(clock);
        this.issuer = Objects.requireNonNull(issuer);
        this.maxTtl = Objects.requireNonNull(maxTtl);
        this.revocationBudget = Objects.requireNonNull(revocationBudget);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        Instant now = clock.instant();
        String key = cacheKey(issuer, token);

        CacheEntry cached = cache.getIfPresent(key);
        if (cached != null) {
            if (cached.freshUntil().isAfter(now)) {
                return cached.principal();
            }
            cache.invalidate(key);
        }

        // Nếu token inactive hoặc introspection lỗi, delegate ném exception.
        // Những exception đó không được biến thành active hoặc cache.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Instant freshUntil = now
            .plus(min(maxTtl, revocationBudget));
        Instant tokenExpiry = readExpiry(principal);
        if (tokenExpiry != null && tokenExpiry.isBefore(freshUntil)) {
            freshUntil = tokenExpiry;
        }

        if (freshUntil.isAfter(now)) {
            cache.put(key, new CacheEntry(principal, freshUntil));
        }

        return principal;
    }

    public void invalidate(String token) {
        cache.invalidate(cacheKey(issuer, token));
    }

    private static Duration min(Duration left, Duration right) {
        return left.compareTo(right) <= 0 ? left : right;
    }

    private static Instant readExpiry(
            OAuth2AuthenticatedPrincipal principal) {
        Object value = principal.getAttribute("exp");
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

    private record CacheEntry(
        OAuth2AuthenticatedPrincipal principal,
        Instant freshUntil) {}
}
~~~

<code>Cache</code> trong ví dụ là <code>com.github.benmanes.caffeine.cache.Cache</code>. Khởi tạo giới hạn kích thước và TTL cứng:

~~~java
Cache<String, CacheEntry> cache =
    Caffeine.newBuilder()
        .maximumSize(50_000)
        .expireAfterWrite(Duration.ofSeconds(10))
        .build();
~~~

Đoạn trên minh họa thuật toán; cần đặt <code>CacheEntry</code> ở visibility phù hợp để bean cấu hình tạo cache. <code>expireAfterWrite</code> là giới hạn cứng của cache; <code>freshUntil</code> trong entry tiếp tục giới hạn theo <code>exp</code> và revocation budget. Không cấu hình cache engine có stale-while-revalidate/stale-if-error vượt quá <code>freshUntil</code>.

**Lưu ý về expiry type:** Spring introspection converter có thể biểu diễn <code>exp</code> thành <code>Instant</code> hoặc kiểu khác theo version/response converter. Hãy xác minh kiểu thực tế trong ứng dụng. Nếu không đọc được expiry, cache vẫn phải bị giới hạn bởi <code>maxTtl</code> và revocation budget; không mặc định token không hết hạn.

### 7.3. Gắn decorator vào Resource Server

Ví dụ cấu hình:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        @Qualifier("cachingOpaqueTokenIntrospector")
        OpaqueTokenIntrospector introspector) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/health").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.opaqueToken(opaque ->
                opaque.introspector(introspector)));

    return http.build();
}
~~~

Bean <code>cachingOpaqueTokenIntrospector</code> cần được tạo bằng cách bọc một remote introspector đã cấu hình đúng endpoint, client authentication và TLS. Không inject chính bean cache wrapper vào constructor delegate của nó; đặt tên/qualifier riêng cho remote introspector để tránh vòng phụ thuộc.

### 7.4. Cache chỉ là một lớp tối ưu

Resource Server vẫn phải kiểm tra authorization trên mỗi request:

- Scope đủ cho endpoint/action.
- Audience đúng API.
- Tenant/principal phù hợp resource.
- Token type và client policy hợp lệ.
- Các điều kiện nghiệp vụ có thể thay đổi nhanh (account disabled, entitlement revoked) nếu yêu cầu SLA đòi hỏi.

Không cache một quyết định <code>hasAuthority("orders.write")</code> vô thời hạn chỉ vì principal introspection được cache 10 giây. Nếu permission nghiệp vụ có cache riêng, phải đưa nó vào cùng phân tích revocation/freshness.

## 8. Invalidation chủ động khi token bị revoke

### 8.1. TTL-only và event invalidation

Có hai chiến lược:

| Chiến lược | Cách hoạt động | Đặc điểm |
| --- | --- | --- |
| TTL-only | Entry tự hết hạn sau TTL. | Dễ triển khai; stale window bị chặn bởi TTL nếu không có stale extension. |
| Event invalidation | Authorization Server phát sự kiện khi revoke; Resource Server xóa entry liên quan. | Thu hồi nhanh hơn; cần delivery, retry, ordering, fan-out và xác nhận áp dụng. |
| Kết hợp | Event xóa cache sớm, TTL là safety net nếu event bị mất. | Thường phù hợp hệ thống cần latency thấp và có thể vận hành event bus đáng tin. |

RFC 7662 không định nghĩa một giao thức push invalidation tiêu chuẩn cho mọi Resource Server. Event channel là phần mở rộng kiến trúc của hệ thống, cần bảo vệ và vận hành riêng.

### 8.2. Nội dung event

Event có thể mang authorization ID, token ID (<code>jti</code>), issuer, thời điểm revoke, reason code và policy version. Không gửi raw bearer token trong event. Ví dụ:

~~~json
{
  "event_type": "TOKEN_REVOKED",
  "issuer": "https://auth.example.com",
  "authorization_id": "authorization-42",
  "jti": "token-7f31",
  "revoked_at": "2026-11-16T10:15:30Z",
  "policy_version": 1842
}
~~~

Đây là event schema do ứng dụng định nghĩa, không phải payload chuẩn RFC 7662. Event phải được xác thực nguồn phát, chống replay và có version/sequence để Resource Server không áp dụng trạng thái cũ đè lên trạng thái mới.

### 8.3. Invalidate một token hoặc cả authorization

Một authorization có thể liên quan access token, refresh token và nhiều token phát hành theo các lần refresh. Khi revoke cả authorization/session, chỉ xóa cache của token vừa được gửi tới revoke endpoint có thể chưa đủ. Cần map authorization ID/token family sang mọi token cache liên quan hoặc dùng policy version để buộc re-introspection.

Nếu cache key chỉ là hash token, event cần có digest của token đó. Nếu cần invalidate theo <code>jti</code>, cache có thể duy trì secondary index; cân nhắc bộ nhớ, race và cleanup index. Với token opaque, Authorization Server có thể không trả <code>jti</code>; khi đó dùng authorization ID hoặc token digest theo một contract nội bộ.

### 8.4. Race giữa introspection và revoke event

Một race có thể xảy ra:

1. Resource Server bắt đầu introspection.
2. Authorization Server trả <code>active=true</code>.
3. Token bị revoke và event invalidation được phát.
4. Resource Server nhận event, xóa cache.
5. Response introspection cũ đến trễ và cache wrapper ghi lại <code>active=true</code>.

Nếu không có version/fence, stale entry có thể xuất hiện lại sau invalidation. Cách xử lý:

- Mỗi token/authorization có revocation version hoặc epoch.
- Invalidation event cập nhật tombstone/version trước khi xóa cache.
- Khi response introspection về, chỉ cache nếu response không cũ hơn version hiện hành.
- Nếu không thể so version, ghi nhận thời điểm invalidation và không cho response bắt đầu trước thời điểm đó tái tạo entry.
- TTL ngắn là safety net khi event ordering không hoàn hảo.

## 9. Cache nhiều tầng và stale data

### 9.1. Các tầng cache thường gặp

Một request có thể đi qua:

1. Cache trong <code>OpaqueTokenIntrospector</code> tại từng JVM.
2. Cache ở sidecar/API gateway.
3. Cache trong shared Redis/distributed store.
4. Cache HTTP/proxy giữa Resource Server và Authorization Server.
5. Cache trạng thái authorization ở một policy service khác.

Không có một TTL duy nhất nếu nhiều tầng độc lập giữ bản sao.

### 9.2. Không reset tuổi dữ liệu ở mỗi tầng

Giả sử gateway cache active result 10 giây. Một service lấy kết quả từ gateway ở giây thứ 9 rồi cache thêm 10 giây tính từ lúc nhận. Dữ liệu có thể được tin gần 19 giây kể từ lần introspection thật. Nếu thêm tầng cache thứ ba, cửa sổ có thể tăng thêm.

Để giữ bound:

- Truyền/duy trì **absolute freshness deadline** từ lần introspection gốc.
- Tính <code>remaining_ttl = fresh_until - now</code> ở mỗi tầng.
- Tôn trọng <code>Age</code>/<code>Date</code>/<code>max-age</code> nếu dùng HTTP cache và contract cho phép.
- Không cấp TTL mới đầy đủ khi đọc từ một cache upstream.
- Không dùng stale-while-revalidate hoặc stale-if-error ngoài ngân sách revocation đã duyệt.

Nếu mỗi tầng reset TTL độc lập, hãy tính worst case bảo thủ bằng tổng TTL các tầng cộng propagation/in-flight delay, hoặc bỏ bớt tầng cache.

### 9.3. Local cache hay distributed cache?

| Tiêu chí | Local cache (Caffeine) | Distributed cache (Redis, v.v.) |
| --- | --- | --- |
| Latency hit | Rất thấp, không cần network. | Có network round trip. |
| Chia sẻ giữa instance | Không; mỗi JVM có bản riêng. | Có thể chia sẻ. |
| Invalidation | Phải broadcast tới mọi instance. | Có thể xóa tập trung, nhưng vẫn cần xử lý replica/partition. |
| Availability | Cache sống cùng process. | Phụ thuộc cache cluster/network. |
| Dung lượng | Giới hạn theo heap từng node. | Quản lý tập trung, có thể lớn hơn. |
| Rủi ro | Mỗi node có trạng thái khác nhau nếu event miss. | Stale read/replication lag hoặc cache outage. |

Local cache phù hợp khi TTL ngắn, số token vừa phải và có cơ chế broadcast invalidation. Distributed cache hữu ích khi nhiều instance cần chia sẻ kết quả hoặc cần xóa tập trung, nhưng không tự động bảo đảm consistency tuyệt đối.

## 10. Outage và quyết định fail-open/fail-closed

### 10.1. Cache hit còn fresh khi Authorization Server lỗi

Nếu cache entry còn trong freshness deadline, Resource Server có thể tiếp tục dùng kết quả đã xác minh theo policy. Đây là một lợi ích availability của cache. Nhưng khi entry hết hạn và không gọi được introspection, Resource Server không có bằng chứng mới rằng token vẫn active.

### 10.2. Fail-closed

Fail-closed nghĩa là khi không thể xác minh token bằng một kết quả còn fresh, không cấp quyền. Hệ thống có thể trả lỗi dịch vụ phù hợp (ví dụ 503 khi Authorization Server unavailable) thay vì giả định token invalid và trả 401 trong mọi trường hợp. Cần phân biệt:

- Token được xác minh inactive: 401.
- Không thể xác minh do introspection outage: lỗi phụ thuộc dịch vụ (thường 503/5xx theo API contract).

Fail-closed bảo vệ authorization nhưng có thể làm API gián đoạn khi Authorization Server gặp sự cố.

### 10.3. Fail-open hoặc stale-if-error

Fail-open dùng kết quả active đã hết TTL hoặc bỏ qua introspection lỗi để tiếp tục request. Nó có thể tăng availability nhưng làm mất giới hạn revocation SLA. Nếu dùng stale-if-error, phải định nghĩa:

- Chỉ dùng cho loại API/risk nào.
- Stale tối đa bao lâu.
- Chỉ dùng khi lỗi nào (timeout/5xx; không dùng khi AS trả active=false).
- Token còn trong <code>exp</code> và scope/audience vẫn phù hợp không.
- Ai phê duyệt và cách quan sát stale authorization.

Không biến fail-open thành hành vi mặc định ẩn trong cache library. Với thao tác tài chính, quản trị, dữ liệu nhạy cảm hoặc quyền cao, thường cần fail-closed.

### 10.4. Circuit breaker và retry

Circuit breaker có thể ngăn Resource Server tạo quá nhiều request khi introspection endpoint đang lỗi. Tuy nhiên:

- Retry phải có giới hạn và backoff; không retry liên tục mỗi API request.
- Không retry các lỗi <code>active=false</code>, <code>invalid_client</code> hoặc response lỗi logic như thể chúng là network transient.
- Khi circuit open và cache miss/expired, áp dụng fail-closed hoặc stale policy được phê duyệt.
- Không kéo dài TTL chỉ vì circuit breaker đang mở.
- Theo dõi circuit state, introspection error rate và cache stale usage.

## 11. Cấu hình TTL theo từng loại tài nguyên

Không phải mọi API có cùng mức chấp nhận rủi ro. Có thể chia policy:

| Loại API | Ví dụ mục tiêu | Cache policy gợi ý |
| --- | --- | --- |
| API đọc thông tin ít nhạy cảm | Catalog, nội dung công khai có xác thực | TTL ngắn/vừa nếu revocation SLA cho phép. |
| API nghiệp vụ thông thường | Orders read, profile | TTL ngắn, clamp theo <code>exp</code>, invalidation khi revoke. |
| API thay đổi dữ liệu | Orders write, billing operation | TTL rất ngắn hoặc introspection mỗi request, tùy SLA. |
| API quản trị/privileged | Admin, key management, permission change | Ưu tiên kiểm tra trạng thái mới nhất; thường không dùng stale positive. |
| API xử lý tiền/tài sản | Thanh toán, chuyển tiền | Fail-closed, TTL cực ngắn hoặc trạng thái tập trung theo yêu cầu nghiệp vụ. |

Các mức TTL phải xuất phát từ threat model và SLA, không lấy bảng trên làm cấu hình mặc định cho mọi hệ thống. Cũng cần xem xét quyền của token: token có scope rộng hơn thường cần freshness ngắn hơn.

### 11.1. TTL theo token lifetime

Một token có <code>exp</code> còn 2 giây thì không thể được cache active thêm 10 giây. Cache deadline phải bị clamp về <code>exp</code> hoặc sớm hơn theo clock-skew policy. Token không có <code>exp</code> trong introspection response cần TTL nhỏ do server contract định nghĩa; không hiểu thiếu exp là vô hạn.

### 11.2. TTL theo revocation class

Nếu hệ thống có token cho client batch và token cho thao tác admin, có thể chọn TTL theo client/scope/audience:

- Token chỉ đọc, quyền thấp: có thể có TTL cache dài hơn nếu SLA cho phép.
- Token có quyền ghi hoặc quản trị: TTL ngắn hơn, invalidation chủ động.
- Token gắn với một tenant/session cần revoke nhanh: cache key và invalidation event phải gắn được với tenant/authorization tương ứng.

Không cho client tự gửi một header như <code>X-Cache-TTL</code> để kéo dài thời gian cache quyền của chính nó. TTL là policy phía Resource Server, không phải quyền do bearer token quyết định.

## 12. Quan sát cache và revocation

### 12.1. Metrics cần theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| <code>introspection_requests_total</code> | Số lần gọi Authorization Server. |
| <code>introspection_latency</code> | Độ trễ của request introspection. |
| <code>introspection_errors_total</code> | Lỗi kết nối, HTTP hoặc parse. |
| <code>introspection_cache_hits_total</code> | Số lần cache hit. |
| <code>introspection_cache_misses_total</code> | Số lần cache miss. |
| <code>introspection_cache_evictions_total</code> | Entry bị evict vì TTL/dung lượng. |
| <code>introspection_active_total</code> | Số kết quả active theo thống kê tổng hợp. |
| <code>introspection_inactive_total</code> | Số kết quả inactive. |
| <code>revocation_event_lag</code> | Độ trễ từ revoke commit đến cache invalidation. |
| <code>revocation_policy_version</code> | Version policy đang được instance áp dụng. |
| <code>stale_cache_served_total</code> | Số lần dùng stale entry theo policy đặc biệt, nếu có. |

Không gắn raw token, token hash, <code>jti</code>, username hoặc client secret làm label metric. Dùng label có cardinality thấp như resource server, issuer alias, result class và cache tier.

### 12.2. Đo revocation latency thực tế

Trong staging/production drill:

1. Cấp token test và gọi API để tạo cache hit.
2. Revoke token tại Authorization Server.
3. Ghi thời điểm revoke commit.
4. Ghi thời điểm event được publish/consume nếu có.
5. Gửi request liên tục từ các vùng/instance.
6. Ghi thời điểm request đầu tiên bị từ chối ở từng Resource Server.
7. Tính max, p95, p99 của revocation latency và so với SLA.

Không chỉ đo thời gian API revoke endpoint trả 200. Điều cần đo là thời gian từ **revoke đã commit** đến **mọi verifier không còn chấp nhận token**.

### 12.3. Log an toàn

Log có thể ghi issuer alias, resource server ID, result (<code>active</code>/<code>inactive</code>/<code>error</code>), cache hit/miss, policy version, latency và request correlation ID. Không log raw bearer token hoặc body introspection chứa thông tin nhạy cảm. Nếu cần liên kết sự cố, dùng identifier đã được thiết kế và bảo vệ.

## 13. Kiểm thử cache và độ trễ thu hồi

### 13.1. Unit test TTL và expiration

Tách clock và cache policy để kiểm thử không cần <code>Thread.sleep</code>. Các trường hợp:

- Active response được cache và lần gọi tiếp theo là hit.
- TTL hết hạn thì gọi delegate lại.
- <code>exp</code> sớm hơn configured TTL thì entry hết tại <code>exp</code>.
- <code>active=false</code> ném exception và không tạo positive entry.
- Timeout/5xx không tạo cache entry.
- Cache entry hết hạn không được trả dù cache engine chưa kịp eviction vật lý.
- Cache key khác nhau theo issuer/token digest.

### 13.2. Test revocation latency

Một test tích hợp có thể mô phỏng:

~~~text
T0: Introspect token T -> active=true
T1: Resource Server cache T trong 5 giây
T2: Authorization Server revoke T
T3: Request dùng T trước khi invalidation/TTL -> có thể được chấp nhận
T4: Invalidation event tới Resource Server -> cache entry bị xóa
T5: Request dùng T -> introspect lại -> active=false -> 401
~~~

Assert cần đo <code>T5 - T2</code>, không chỉ assert event handler đã được gọi. Nếu không có event, xác minh token bị từ chối khi TTL hết. Nếu có nhiều instance, test từng instance và node mới vừa khởi động.

### 13.3. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Cache miss, introspection active | Gọi AS, cache theo TTL hợp lệ và cho phép nếu scope/audience đúng. |
| Cache hit còn fresh | Không gọi AS; dùng metadata đã xác minh. |
| Cache entry hết hạn | Gọi AS lại trước khi quyết định. |
| Token revoke ngay sau cache fill | Bị chấp nhận tối đa trong cửa sổ TTL/event đã công bố. |
| Invalidation event tới trước TTL | Cache entry bị xóa và lần request sau introspect lại. |
| Invalidation event bị mất | TTL fallback vẫn giới hạn stale window theo SLA. |
| Response <code>active=false</code> | Từ chối; không tạo positive cache entry. |
| Timeout/5xx | Không cache như active/inactive; áp dụng outage policy. |
| Response có <code>Cache-Control: no-store</code> | Không lưu response vào cache. |
| Token hết hạn trước cache TTL | Cache không phục vụ sau <code>exp</code>. |
| Nhiều cache tầng | Freshness deadline không bị reset ở mỗi tầng. |
| Event đến trễ sau response introspection cũ | Không để response cũ tái tạo entry đã invalidated. |
| Token family bị revoke | Xóa mọi cache entry liên quan hoặc cập nhật policy version. |
| Registry/event bus lỗi | Hành vi fail-safe theo policy và có cảnh báo. |
| Resource Server mới autoscale | Nạp revocation state trước khi nhận traffic. |
| Introspection credential sai | Báo lỗi cấu hình, không cache. |
| Audience sai | Từ chối dù introspection trả active=true. |
| Scope không đủ | Từ chối dù introspection trả active=true. |
| Token hash làm cache key | Raw token không xuất hiện trong log/metric/cache key hiển thị. |

## 14. Những lỗi thiết kế thường gặp

### Lỗi 1: Cache active=true quá lâu vì muốn tối ưu latency

**Triệu chứng:** Token bị revoke nhưng API vẫn chấp nhận nhiều phút.

**Nguyên nhân:** TTL được chọn theo hiệu năng mà không tính revocation SLA.

**Cách sửa:** Định lượng stale window, đặt TTL theo SLA và bổ sung invalidation đáng tin cậy.

### Lỗi 2: Cache token active lâu hơn exp

**Triệu chứng:** Token hết hạn nhưng cache hit vẫn cho phép request.

**Nguyên nhân:** Cache TTL cố định không clamp theo expiration.

**Cách sửa:** <code>freshUntil = min(configuredDeadline, exp, revocationDeadline)</code> và kiểm tra freshness mỗi lần hit.

### Lỗi 3: Bỏ qua Cache-Control: no-store

**Triệu chứng:** Response introspection bị lưu dù Authorization Server cấm lưu.

**Nguyên nhân:** Thêm Caffeine/Redis decorator mà không xét cache directive.

**Cách sửa:** Tôn trọng no-store; chỉ bật cache khi AS contract cho phép và transport có thể áp dụng policy đúng.

### Lỗi 4: Cache timeout thành active=false

**Triệu chứng:** Authorization Server tạm ngừng hoạt động làm tất cả token bị xem là inactive.

**Nguyên nhân:** Gộp lỗi kết nối và kết quả inactive thành cùng một giá trị cache.

**Cách sửa:** Phân biệt token inactive với introspection unavailable; không cache lỗi.

### Lỗi 5: Fail-open sau khi cache hết hạn mà không giới hạn

**Triệu chứng:** API tiếp tục chấp nhận token khi Authorization Server down.

**Nguyên nhân:** Stale-if-error kéo dài không giới hạn.

**Cách sửa:** Chọn fail-closed hoặc stale allowance có deadline, scope và owner rõ ràng; đo stale served.

### Lỗi 6: Cache nhiều tầng reset TTL

**Triệu chứng:** TTL cấu hình 10 giây nhưng token vẫn được chấp nhận lâu hơn nhiều.

**Nguyên nhân:** Mỗi tầng cache tính lại TTL từ lúc nhận dữ liệu cũ.

**Cách sửa:** Dùng absolute freshness deadline/remaining TTL và không reset tuổi dữ liệu.

### Lỗi 7: Invalidation event tới nhưng response cũ ghi lại cache

**Triệu chứng:** Cache entry xuất hiện lại ngay sau revoke.

**Nguyên nhân:** Race giữa introspection in-flight và event handler.

**Cách sửa:** Version/fence/tombstone theo token hoặc authorization, và không cache response cũ hơn revocation version.

### Lỗi 8: Chỉ xóa một token trong khi cả authorization bị revoke

**Triệu chứng:** Refresh-derived access token khác vẫn được chấp nhận.

**Nguyên nhân:** Cache không có quan hệ giữa token và authorization/token family.

**Cách sửa:** Duy trì index hoặc authorization version để invalidate toàn bộ token liên quan.

### Lỗi 9: Dùng raw token làm cache key hoặc log

**Triệu chứng:** Bearer token xuất hiện trong Redis key, heap dump hoặc log.

**Nguyên nhân:** Dùng trực tiếp token string để thuận tiện.

**Cách sửa:** Dùng digest, giới hạn quyền cache, mã hóa dữ liệu nhạy cảm và tránh log.

## 15. Checklist production

| Hạng mục | Câu hỏi cần xác nhận |
| --- | --- |
| Revocation SLA | Bao lâu sau revoke commit thì mọi API phải từ chối token? |
| Cache permission | Introspection response có <code>no-store</code> không? Contract có cho phép application cache không? |
| TTL | TTL có bị giới hạn bởi <code>exp</code>, SLA và propagation margin không? |
| Positive cache | Chỉ cache kết quả active đã xác minh? |
| Negative/error | Không nhầm inactive với timeout/5xx; negative TTL có thật sự cần không? |
| Cache key | Dùng digest token và namespace issuer/resource server? |
| Multi-tier | Freshness deadline có được truyền xuyên tầng mà không reset TTL? |
| Invalidation | Có event cho token/authorization revoke và cơ chế repair khi event miss? |
| Race | Response introspection cũ có thể tái tạo entry sau revoke không? |
| Outage | Fail-open/closed và stale allowance đã được phê duyệt? |
| Expiry | Không trả cached principal sau <code>exp</code>? |
| Authorization | Scope/audience/tenant vẫn được kiểm tra ở Resource Server? |
| Observability | Có hit ratio, latency, event lag, stale served và policy version? |
| Security | Không log raw token, cache key không chứa bearer token, introspection client được xác thực? |
| Testing | Có test TTL, invalidation, event loss, multi-node, outage và token family? |

## 16. Bài tập thực hành

Orders API nhận 5.000 request/giây. Authorization Server có p95 introspection latency 35 ms. Product yêu cầu khi quản trị viên revoke token, tất cả instance Resource Server phải từ chối token trong tối đa 8 giây. Có 6 instance API, mỗi instance dùng Caffeine local cache; event bus có p99 propagation 2 giây nhưng có thể mất event.

1. Tính số request introspection gần đúng nếu không cache và giải thích đây là ước lượng tải, không phải số request chắc chắn.
2. Chọn TTL local cache sao cho vẫn đáp ứng SLA khi event bị mất.
3. Tính stale window khi cache vừa được fill ngay trước thời điểm revoke.
4. Thiết kế event invalidation để xóa cache trên cả 6 instance và xác nhận tất cả instance đã áp dụng.
5. Xử lý race khi introspection <code>active=true</code> trả về sau khi event revoke đã được xử lý.
6. Thiết kế cache key không lưu raw bearer token và có namespace issuer.
7. Xác định hành vi khi Authorization Server down và cache entry còn fresh, hết hạn hoặc đã stale.
8. Kiểm tra response có <code>Cache-Control: no-store</code>; quyết định có được phép bật application cache hay không.
9. Viết test virtual clock cho TTL, <code>exp</code>, invalidation event và token family.
10. Đề xuất metrics để chứng minh revocation latency p95/p99 đáp ứng SLA.

**Tiêu chí đạt:** Có thể giải thích định lượng rằng cache hit giảm round trip và tải introspection, đồng thời chứng minh **thời gian Resource Server tiếp tục tin một kết quả active cũ luôn nằm trong ngân sách thu hồi đã phê duyệt**.

## 17. Tài liệu đối chiếu

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): request/response introspection, <code>active</code>, metadata và security considerations.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token lifecycle, token revocation context và client authentication.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revoke token và semantics của endpoint thu hồi.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): cache directives, freshness, age và validation.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): <code>OpaqueTokenIntrospector</code>, opaque token authentication và introspection configuration.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Introspection Endpoint và xử lý token status.
- [Caffeine Cache](https://github.com/ben-manes/caffeine/wiki): TTL, eviction, maximum size và cache implementation cho Java.
