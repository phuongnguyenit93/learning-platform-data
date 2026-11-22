# Giới hạn số tenant, số decoder và dữ liệu cache

Một Spring Security Resource Server multi-tenant có thể phải xác minh token cho hàng trăm hoặc hàng nghìn tenants. Mỗi tenant có thể có issuer, JWKS endpoint, audience, thuật toán, introspection endpoint, client credentials và permission policy riêng. Nếu ứng dụng tạo một decoder/manager cho mọi request, lưu mọi tenant vô thời hạn hoặc cache kết quả introspection không có giới hạn, bộ nhớ, kết nối mạng và chi phí xác thực sẽ tăng theo traffic và số tenant.

Thiết kế multi-tenant cần có **giới hạn số tenant được onboard, giới hạn số authentication managers/decoders được giữ trong bộ nhớ, và chính sách cache riêng cho từng loại dữ liệu**.

Có ba nguyên tắc cần giữ:

1. Chỉ tenant đã được quản trị và cho phép mới được tạo trust configuration.
2. Decoder/manager và các cache phải có giới hạn, lifecycle, eviction và invalidation rõ ràng.
3. Cache không được làm suy yếu issuer, audience, tenant isolation, revocation SLA hoặc fail-closed behavior.

Bài học tập trung vào quản lý dung lượng cho WebFlux Resource Server: tenant registry, ReactiveAuthenticationManager, ReactiveJwtDecoder, JWKS/key cache, introspection cache, revocation state, cache key, TTL, eviction, cold start, cache stampede, observability và capacity testing.

## 1. Vì sao số tenant ảnh hưởng tới hiệu năng?

Với một tenant JWT đơn giản, ứng dụng có thể dùng một decoder và một manager. Khi có nhiều tenants, mỗi tenant có thể kéo theo:

- Một hoặc nhiều ReactiveAuthenticationManager.
- ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector.
- JWKS endpoint và cache public keys riêng.
- HTTP client/connection pool hoặc cấu hình TLS riêng.
- Issuer, audience, algorithm và validator configuration.
- Introspection client credentials.
- Cache metadata và trạng thái tenant.
- Metrics, circuit breaker, rate limiter và health information.

Nếu mỗi tenant có một bộ thành phần riêng, chi phí tăng theo số tenant hoạt động.

~~~mermaid
flowchart TD
    REG[Tenant registry] --> RES[ReactiveAuthenticationManagerResolver]
    RES --> MA[Manager tenant A]
    RES --> MB[Manager tenant B]
    RES --> MC[Manager tenant C]
    MA --> DA[Decoder / introspector A]
    MB --> DB[Decoder / introspector B]
    MC --> DC[Decoder / introspector C]
    DA --> KA[JWKS / token state cache A]
    DB --> KB[JWKS / token state cache B]
    DC --> KC[JWKS / token state cache C]
~~~

Đây là mô hình logic. Một số tenants có thể dùng chung issuer hoặc hạ tầng, nhưng chỉ chia sẻ thành phần khi trust contract thực sự giống nhau.

### 1.1. Số tenant, số issuer và số decoder không phải một

Ví dụ:

| Cấu hình | Số tenant | Số issuer | Số decoder có thể cần |
|---|---:|---:|---:|
| Mỗi tenant có issuer riêng | 100 | 100 | Có thể gần 100 |
| Nhiều tenants dùng chung issuer và cùng policy | 100 | 1 | Có thể dùng chung decoder |
| Cùng issuer nhưng audience/validators khác nhau | 100 | 1 | Có thể cần nhiều manager/decoder policy |
| Một tenant có JWT và opaque token | 1 | Có thể 1 hoặc nhiều AS | Có thể có nhiều managers |

Không lấy tenant count làm đại diện duy nhất cho decoder count. Cần thống kê số **distinct trust configurations**: issuer, JWKS/introspection endpoint, audience, algorithm policy, validator set và client authentication.

### 1.2. Đối tượng nào tốn tài nguyên?

| Đối tượng | Tài nguyên chính | Vòng đời cần quản lý |
|---|---|---|
| Tenant configuration | Bộ nhớ, metadata | Onboard, update, disable, delete |
| ReactiveAuthenticationManager | Object graph, decoder/introspector reference | Tạo, cache, evict |
| ReactiveJwtDecoder | Key source, HTTP client/configuration, validators | Tạo, cache, key refresh |
| JWKS/public key set | Bộ nhớ, network refresh | TTL, rotation, invalidation |
| ReactiveOpaqueTokenIntrospector | HTTP connections, client credentials | Pool, timeout, secret rotation |
| Introspection result | Bộ nhớ, sensitive token-derived data | TTL, revoke, eviction |
| Revocation/session cache | Bộ nhớ, consistency | TTL, event update, cleanup |
| Metrics/circuit breaker | Bộ nhớ và cardinality | Giới hạn label, lifecycle |

Một decoder không nhất thiết tự mở một connection pool riêng; điều đó tùy implementation và HTTP client được cấu hình. Tuy vậy, tạo decoder/HTTP client lặp lại có thể nhân bản cache, connection resources và initialization work.

## 2. Đặt giới hạn tenant từ bước onboarding

Giới hạn tenant nên được áp dụng ở **tenant provisioning/configuration layer**, trước khi tenant có thể gửi request.

Một tenant record nên có các thông tin cần thiết:

~~~yaml
tenantId: tenant-a
status: ACTIVE
issuer: https://id-a.example.com
jwksUri: https://id-a.example.com/.well-known/jwks.json
audience:
  - orders-api-a
tokenStrategy: JWT
policyVersion: 4
~~~

Đây là cấu hình minh họa. Production có thể lưu trong database/config service và quản lý secrets riêng.

### 2.1. Không tự tạo tenant từ request

Không làm:

~~~text
Request gửi X-Tenant-ID: tenant-new
  -> ứng dụng tự tạo tenant config
  -> tải issuer metadata từ URL request cung cấp
  -> tạo decoder
  -> chấp nhận token
~~~

Một request không được phép tự làm tăng tenant count, tạo manager hoặc kích hoạt network lookup tới một issuer chưa được quản trị.

Cách đúng:

1. Tenant được đăng ký qua quy trình onboarding có xác thực.
2. Issuer, JWKS URI, audience và token strategy được kiểm tra.
3. Tenant được thêm vào registry đã được quản lý.
4. Hệ thống áp quota tenant active và tenant pending.
5. Manager/decoder được chuẩn bị theo policy.
6. Tenant chỉ chuyển sang ACTIVE sau khi cấu hình cần thiết sẵn sàng.

### 2.2. Phân biệt active, disabled và deleted

| Trạng thái | Ý nghĩa | Có được resolve manager? |
|---|---|---|
| PENDING | Đang onboarding | Không |
| ACTIVE | Được phép nhận request | Có, nếu manager sẵn sàng |
| DISABLED | Tạm ngừng truy cập | Không |
| DELETING | Đang offboard/drain | Không cho request mới |
| DELETED | Đã xóa theo retention policy | Không |

Không dùng cache manager làm nguồn chân lý cho trạng thái tenant. Tenant registry phải quyết định tenant còn được phép hoạt động hay không; cache chỉ giữ các thành phần đã dựng theo registry.

### 2.3. Đặt quota có thể vận hành

Có thể giới hạn:

- Tổng số tenants được onboard.
- Số tenants ACTIVE.
- Số issuer khác nhau.
- Số trust configurations.
- Số tenants có introspection endpoint riêng.
- Số tenants được phép dùng custom JWKS URI.
- Số lần thay đổi issuer/policy trong một khoảng thời gian.
- Tốc độ tạo decoder/manager mới.

Không chọn con số tùy tiện. Hãy xác định từ ngân sách memory, connection pool, network capacity, AS rate limit và yêu cầu sản phẩm. Quota phải được kiểm tra cả ở API onboarding và service/database layer để tránh hai yêu cầu đồng thời vượt giới hạn.

## 3. Giới hạn số ReactiveAuthenticationManager và ReactiveJwtDecoder

Một cách đơn giản cho hệ thống nhỏ là tạo sẵn manager cho một danh sách tenants hữu hạn:

~~~java
Map<String, ReactiveAuthenticationManager> managers = Map.of(
    "tenant-a", managerA,
    "tenant-b", managerB
);
~~~

Resolver chỉ lookup trong registry:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String tenantId = resolveTenantFromTrustedRoute(exchange);

        ReactiveAuthenticationManager manager = managers.get(tenantId);
        if (manager == null) {
            return Mono.error(unknownTenant());
        }

        return Mono.just(manager);
    };
~~~

Cách này dễ kiểm soát nhưng manager count gần bằng số tenant được cấu hình. Nếu số tenants lớn hoặc có thể thay đổi, cần lifecycle và cache có giới hạn.

### 3.1. Không tạo decoder mới trên mỗi request

Anti-pattern:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String issuer = resolveIssuer(exchange);

        return Mono.fromCallable(
            () -> ReactiveJwtDecoders.fromIssuerLocation(issuer)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .map(JwtReactiveAuthenticationManager::new);
    };
~~~

Mỗi request có thể tạo decoder mới, lặp metadata discovery, key cache và object graph. Khi traffic tăng, ứng dụng tạo nhiều decoder cho cùng một issuer và gây áp lực lên Authorization Server/JWKS endpoint.

**Decoder/manager nên được tạo theo trust configuration và được tái sử dụng**, không tạo theo request.

### 3.2. Cache key phải đại diện cho policy, không chỉ tenant name

Một manager/decoder cache key có thể cần:

~~~text
tenantId
issuer
jwksUri
audience
algorithm policy
validator policy version
client/introspection configuration version
~~~

Nếu chỉ dùng tenantId, thay đổi audience hoặc issuer có thể vô tình tái sử dụng manager cũ với policy cũ.

Có thể dùng một key bất biến:

~~~java
record DecoderKey(
    String tenantId,
    String issuer,
    String jwksUri,
    String audience,
    long policyVersion
) {}
~~~

Không đưa raw client secret vào key hoặc log. Dùng secret/configuration version hoặc reference ID để nhận biết cấu hình đã đổi.

### 3.3. Chỉ chia sẻ decoder khi trust policy tương đương

Hai tenants cùng issuer chưa chắc có thể dùng chung toàn bộ decoder/manager.

Ví dụ:

~~~text
Tenant A:
  issuer = https://id.example.com
  audience = orders-api-a

Tenant B:
  issuer = https://id.example.com
  audience = orders-api-b
~~~

Có thể chia sẻ nguồn public key/JWKS ở tầng phù hợp, nhưng audience validator và tenant policy phải khác nhau. Nếu dùng chung decoder với validator quá rộng, token của tenant A có thể vượt qua audience policy của tenant B.

**Chia sẻ key retrieval không đồng nghĩa chia sẻ authorization policy.**

### 3.4. Giới hạn cache manager bằng Caffeine

Caffeine có thể dùng để giới hạn số manager được giữ trong process:

~~~java
import java.time.Duration;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

Cache<DecoderKey, ReactiveAuthenticationManager> managerCache =
    Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterAccess(Duration.ofMinutes(30))
        .recordStats()
        .build();
~~~

Các giá trị 500 và 30 phút chỉ minh họa cấu hình; cần chọn theo capacity và tenant lifecycle thực tế.

Một cache object không thay thế tenant registry. Resolver phải kiểm tenant còn ACTIVE trước khi lấy manager. Nếu manager không còn trong cache, hệ thống phải có quy trình tái tạo có kiểm soát hoặc trả lỗi tạm thời; không tự tin một issuer tùy ý.

### 3.5. Cache eviction không giống tenant offboarding

Evict manager do ít được dùng chỉ giải phóng một object/cache entry. Tenant vẫn có thể ACTIVE và được provision lại ở request sau.

Offboarding phải cập nhật tenant registry và ngăn request mới trước khi evict. Nếu chỉ xóa manager khỏi cache mà tenant vẫn active, hệ thống có thể liên tục tạo lại manager hoặc trả lỗi ngẫu nhiên.

## 4. Lazy initialization và giới hạn cold-start

Tạo tất cả decoder ngay khi ứng dụng startup có thể làm:

- Startup chậm theo số tenants.
- Một issuer outage làm chậm toàn bộ ứng dụng.
- Nhiều JWKS discovery requests cùng lúc.
- Memory tăng dù phần lớn tenants không có traffic.

Lazy initialization chỉ tạo manager khi tenant thực sự cần. Nhưng lazy không đồng nghĩa không giới hạn: attacker có thể tạo nhiều requests tới nhiều tenants để buộc hệ thống khởi tạo hàng loạt manager.

### 4.1. Kết hợp lazy creation với tenant admission

Một chiến lược:

1. Chỉ tenants ACTIVE trong registry được resolve.
2. Mỗi tenant có tối đa một initialization đang chạy.
3. Giới hạn tổng số initialization đồng thời.
4. Cache kết quả manager theo trust configuration.
5. Giới hạn số manager resident.
6. Khi eviction, giữ metadata registry để có thể tái tạo theo policy.
7. Nếu không còn capacity, từ chối/giới hạn request theo một lỗi vận hành rõ ràng.

### 4.2. Tránh cache stampede

Nếu 500 requests đầu tiên cùng tới tenant chưa có decoder, không nên tạo 500 decoders và gửi 500 discovery/JWKS requests.

Cần **single-flight initialization**: nhiều requests cùng tenant chờ một quá trình tạo manager. Kết quả thành công được chia sẻ; lỗi được xử lý với backoff và retry policy có giới hạn.

Có thể thực hiện bằng một future/Mono được chia sẻ theo cache key, async loading cache hoặc initialization registry. Nếu dùng Reactor, bảo đảm factory không chạy blocking trên event loop.

### 4.3. Không cache lỗi khởi tạo vô thời hạn

Nếu issuer tạm thời down, một lỗi manager creation bị cache mãi sẽ khiến tenant không phục hồi khi AS hoạt động lại.

Ngược lại, retry mỗi request có thể tạo một cơn bão network.

Dùng:

- Retry có backoff và jitter.
- Thời gian cache lỗi ngắn hoặc circuit breaker.
- Một giới hạn số lần initialization đồng thời.
- Metrics cho initialization failure và recovery.
- Một cơ chế quản trị để retry/refresh tenant config.

Không fail-open bằng cách tạo Authentication giả khi manager không khởi tạo được.

## 5. Các loại cache trong Resource Server

Không nên gọi mọi cache là “token cache”. Mỗi loại dữ liệu có mục đích, TTL và rủi ro khác nhau.

| Cache | Dữ liệu | Mục tiêu | Rủi ro nếu TTL/eviction sai |
|---|---|---|---|
| Tenant metadata | issuer, audience, trạng thái, policy version | Giảm đọc config | Tenant disabled vẫn được coi active |
| Manager/decoder | object xác minh token | Tái sử dụng object | Giữ policy cũ hoặc tăng memory |
| JWKS/key set | public JWKs | Giảm tải key endpoint | Chậm nhận key rotation/emergency removal |
| Introspection result | active, scope, subject, expiry | Giảm gọi AS | Token revoked vẫn được chấp nhận |
| Revocation/denylist | jti/session/user version | Từ chối token đã revoke | Revocation bị bỏ sót |
| Authorization data | role, tenant entitlement, policy | Giảm truy vấn policy | Quyền cũ còn hiệu lực |
| Discovery metadata | issuer endpoints, supported algorithms | Giảm discovery requests | Endpoint/policy cũ tiếp tục được dùng |

Không dùng cùng một TTL cho tất cả các cache. Ví dụ JWKS cache phục vụ key distribution; introspection cache ảnh hưởng trực tiếp tới độ mới của trạng thái token; tenant status cache ảnh hưởng khả năng disable tenant.

## 6. JWKS cache và key rotation

JWT decoder thường lấy public keys từ JWKS endpoint của issuer. Public key set có thể được cache để tránh tải lại cho mỗi request.

~~~mermaid
sequenceDiagram
    participant R as Resource Server
    participant C as JWKS cache
    participant J as JWKS endpoint

    R->>C: Lookup kid
    alt Key có trong cache
        C-->>R: Public key
        R->>R: Verify JWT
    else Cache miss / cần refresh
        R->>J: Fetch JWKS
        J-->>R: Public JWK set
        R->>C: Update cache
        R->>R: Verify JWT
    end
~~~

### 6.1. Cache public keys theo issuer

JWKS cache cần namespace theo nguồn tin cậy. Không trộn public keys của các issuers chỉ vì chúng dùng cùng kid.

kid không phải globally unique. Hai issuers có thể cùng dùng kid=key-1 nhưng public keys hoàn toàn khác nhau.

Key cache nên gắn với issuer/JWKS source đã được allowlist và policy version phù hợp.

### 6.2. TTL quá dài làm chậm emergency rotation

Nếu AS bỏ một key bị compromise khỏi JWKS nhưng Resource Server vẫn giữ key trong cache, token ký bằng private key cũ có thể tiếp tục được xác minh cho tới khi cache refresh hoặc key bị invalidated.

TTL JWKS cần cân bằng:

- Tải lên issuer/JWKS endpoint.
- Thời gian nhận key mới.
- Thời gian loại key bị compromise.
- Availability khi issuer tạm thời không truy cập được.

Không tuyên bố key removal có hiệu lực tức thời nếu Resource Servers có cache độc lập chưa được invalidated.

### 6.3. TTL quá ngắn cũng gây vấn đề

Nếu JWKS cache hết hạn quá thường xuyên, nhiều Resource Servers có thể cùng gọi endpoint trong mỗi chu kỳ, gây tải lớn và làm authentication phụ thuộc mạng nhiều hơn.

Dùng cache hợp lý, refresh coordination, jitter và giới hạn outbound concurrency.

### 6.4. Unknown kid và refresh storm

Một JWT có thể mang kid không tồn tại trong JWKS. Decoder có thể cần refresh key set để kiểm tra key mới vừa được publish.

Nếu attacker gửi nhiều JWT với kid ngẫu nhiên, có nguy cơ kích hoạt nhiều refresh attempts. Cần:

- Giới hạn request rate.
- Coalesce refresh requests theo issuer.
- Bounded HTTP concurrency/timeouts.
- Không tạo decoder/JWKS client mới cho từng token.
- Theo dõi refresh failures và unknown-kid rates.
- Có negative-cache/rate-limit strategy ngắn và an toàn nếu implementation hỗ trợ.

Không cache vĩnh viễn kết quả “kid không tồn tại”, vì key mới hợp lệ có thể được publish sau đó.

## 7. Introspection cache và revocation lag

Với opaque token, ReactiveOpaqueTokenIntrospector gọi Authorization Server để biết token active và lấy attributes.

Có thể cache kết quả introspection để giảm network traffic, nhưng cache active=true tạo một cửa sổ chấp nhận kết quả cũ.

Ví dụ:

~~~text
10:00:00  introspection -> active=true, cache 30s
10:00:05  Authorization Server revoke token
10:00:20  Resource Server cache hit active=true
10:00:30  cache hết hạn
10:00:31  introspection -> active=false
~~~

Trong ví dụ, token bị revoke lúc 10:00:05 nhưng có thể vẫn được chấp nhận tới khi cache hết hạn.

### 7.1. TTL phải theo revocation SLA

Nếu business yêu cầu revoke được nhận biết trong tối đa 5 giây, không thể cache active=true trong 60 giây mà vẫn tuyên bố đáp ứng yêu cầu.

TTL introspection nên được giới hạn bởi:

- Thời gian còn lại tới token exp.
- Revocation SLA.
- Tốc độ cập nhật trạng thái tại AS.
- Network/cache propagation.
- Yêu cầu availability.

Không cache một kết quả active vượt quá exp của token.

### 7.2. Cache key cần tách issuer và resource context

Không dùng token value làm cache key hiển thị trong log. Có thể dùng hash có tính ổn định của token để tạo lookup key:

~~~text
issuer-id : resource-id : SHA-256(token)
~~~

Nếu cùng token được introspect trong các tenant/resource contexts khác nhau, cache key phải giữ các ranh giới tương ứng. Không để active=true từ AS A được dùng cho AS B.

### 7.3. Không lưu raw token trong cache key hoặc metrics

Token là Bearer credential. Dùng raw token làm Redis key, metric label hoặc log value có thể làm lộ credential qua tooling vận hành.

Dùng token fingerprint/hash phù hợp; bảo vệ cả cache values vì chúng có thể chứa subject, scopes và thông tin cá nhân.

### 7.4. Active=false cũng cần cache có giới hạn

Cache kết quả inactive có thể giảm việc gọi introspection lặp lại cho token không hợp lệ, nhưng cần TTL ngắn và giới hạn cardinality. Attacker có thể gửi vô số token ngẫu nhiên để làm cache tăng không giới hạn.

Không để một cache negative trở thành nơi lưu trữ vô hạn mọi credential attacker gửi.

## 8. Revocation và authorization cache

Ngoài introspection, ứng dụng có thể cache:

- jti denylist.
- User/session token version.
- Account enabled status.
- Tenant entitlement.
- Role và permission mapping.
- Domain authorization decisions.

Những cache này quyết định request được phép hay bị từ chối. TTL và invalidation phải phù hợp yêu cầu thu hồi.

### 8.1. Revocation state không được eviction tùy tiện

Giả sử một jti đã bị revoke được lưu trong cache. Nếu entry bị eviction trước exp, Resource Server có thể chấp nhận lại token.

Đối với denylist, entry thường cần tồn tại tới exp cộng clock-skew margin, hoặc tới khi một cơ chế khác bảo đảm token không còn hợp lệ.

Nếu cache có maximumSize và tự evict entry quan trọng trước thời hạn, hệ thống có thể mất bảo đảm revocation. Cần lựa chọn store/eviction policy phù hợp; không dùng một LRU cache chung cho dữ liệu revocation quan trọng mà không phân tích hậu quả.

### 8.2. Cache user enabled/disabled

Nếu account bị disable, cache user status có thể còn enabled trong một khoảng thời gian.

Định nghĩa rõ:

- TTL tối đa.
- Invalidation event.
- Behavior khi event bị mất.
- Behavior khi cache backend lỗi.
- Fail-open/fail-closed cho thao tác nhạy cảm.

### 8.3. Không cache quyết định authorization quá rộng

Một decision “user X được đọc order Y” có thể thay đổi khi owner, tenant, order state hoặc policy thay đổi.

Cache key phải bao gồm những inputs ảnh hưởng quyết định, và TTL phải phù hợp. Với thao tác nhạy cảm, kiểm tra quyền trực tiếp tại domain/repository thường an toàn hơn việc tái sử dụng một decision cache cũ.

## 9. Cache key và tenant isolation

Một cache key thiếu tenant/issuer namespace có thể làm dữ liệu của tenant này được sử dụng cho tenant khác.

Ví dụ key không đủ:

~~~text
decoder:issuer-a
introspection:token-hash
user:123:roles
~~~

Tùy dữ liệu, cần namespace:

~~~text
tenant:{tenantId}:issuer:{issuer}:policy:{version}:...
~~~

### 9.1. Những dữ liệu nên có trong key

| Cache | Các thành phần key thường cần |
|---|---|
| Tenant config | tenant ID + config revision |
| Manager/decoder | issuer/tenant + trust policy version |
| JWKS | issuer/JWKS URI đã chuẩn hóa + key-source version |
| Introspection | issuer + resource/client context + token fingerprint |
| Revocation | issuer + jti |
| User/session version | issuer + subject/session ID |
| Authorization decision | tenant + subject + resource + action + policy revision |

Đây là hướng thiết kế, không phải một chuỗi key bắt buộc cho mọi ứng dụng. Hãy bảo đảm các dữ liệu có cùng key thực sự có cùng trust semantics.

### 9.2. Canonicalize issuer và URI

Các issuer URI có thể được cấu hình với dạng khác nhau. Hãy chuẩn hóa theo quy tắc đã thống nhất trước khi dùng làm registry/cache key, nhưng không tự gộp hai issuer khác nhau.

Không dùng issuer URL lấy trực tiếp từ token chưa xác minh làm cache key rồi tạo resource/network client cho URL đó. Phải lookup trong trusted registry trước.

### 9.3. Policy version giúp invalidation

Khi audience, JWKS URI, allowed algorithms hoặc role mapping thay đổi, tăng policy/config revision.

Key cache có revision mới sẽ không vô tình tái sử dụng manager được tạo theo policy cũ. Sau khi publish cấu hình mới, chủ động evict entries cũ và theo dõi số manager/decoder còn tồn tại.

## 10. Eviction, expiration và invalidation khác nhau

| Cơ chế | Ý nghĩa | Ví dụ |
|---|---|---|
| Expiration | Entry hết hạn theo thời gian | Introspection cache 10 giây |
| Eviction | Cache loại entry do capacity/policy | Manager LRU bị loại khi vượt maximumSize |
| Invalidation | Chủ động xóa entry khi dữ liệu thay đổi | Tenant disabled hoặc JWKS key bị compromise |
| Refresh | Cập nhật dữ liệu trước/sau khi cache hết hạn | Tải JWKS mới |
| Reconciliation | Đối chiếu lại state khi event/cache không đồng bộ | Rebuild tenant registry sau reconnect |

Không dùng expiration làm cơ chế duy nhất cho tenant offboarding. Khi tenant bị disable, cần invalidation chủ động để request mới không dùng manager/cache cũ.

### 10.1. Eviction manager có ảnh hưởng request đang chạy không?

Nếu một request đã lấy reference tới manager, việc xóa entry khỏi cache thường không tự hủy object đang được request đó sử dụng. Tuy nhiên, nếu manager sở hữu HTTP client/resource riêng và ứng dụng đóng chúng ngay khi eviction, request đang chạy có thể lỗi.

Cần quản lý lifecycle:

- Ngừng cấp manager cho request mới.
- Cho request đang chạy hoàn tất trong giới hạn.
- Đóng resource do ứng dụng sở hữu khi không còn dùng.
- Tránh đóng shared HTTP client khi một tenant eviction nếu client được dùng chung.

### 10.2. Tenant offboarding

Một quy trình offboarding có thể:

1. Chuyển tenant sang DISABLED/DELETING trong registry.
2. Từ chối request mới và không resolve manager.
3. Revoke refresh tokens/sessions theo policy của AS.
4. Vô hiệu hóa issuer/audience/tenant trust configuration.
5. Invalidate tenant metadata, manager/decoder và introspection caches.
6. Xử lý revocation/authorization cache theo retention policy.
7. Drain request đang chạy.
8. Đóng tenant-specific clients/resources do ứng dụng sở hữu.
9. Audit kết quả và xác nhận tenant không thể được tái tạo từ request.

Chỉ xóa decoder cache không đủ nếu tenant registry vẫn ACTIVE.

## 11. Cache local hay distributed?

Không phải mọi cache đều cần Redis hoặc một shared cache.

| Loại dữ liệu | Local cache | Shared/distributed store |
|---|---|---|
| Decoder/manager object | Phù hợp vì object nằm trong process | Không truyền object Java giữa nodes |
| JWKS/public keys | Thường phù hợp | Có thể dùng shared key material nếu kiến trúc hỗ trợ |
| Tenant metadata | Nhanh, cần invalidation giữa nodes | Hữu ích khi nhiều replicas cần cùng revision |
| Introspection results | Nhanh nhưng mỗi node có state riêng | Có thể chia sẻ active/revoked state |
| jti denylist | Không đủ nếu chỉ lưu ở một node | Thường cần shared store/event propagation |
| User/session version | Local cache có propagation lag | Shared store hoặc event-driven invalidation |

### 11.1. Local cache

Ưu điểm:

- Đọc nhanh.
- Không có network round trip.
- Dễ tích hợp với object lifecycle của decoder/manager.

Nhược điểm:

- Mỗi node có bản cache riêng.
- Restart làm mất cache.
- Invalidation phải lan tới tất cả replicas.
- Memory được nhân theo số nodes.

### 11.2. Distributed cache

Ưu điểm:

- Nhiều nodes chia sẻ dữ liệu.
- Có thể cập nhật revocation/configuration tập trung.
- Giảm khác biệt cache giữa replicas.

Chi phí:

- Network latency và dependency mới.
- Cần timeout, connection pool, retry và circuit breaker.
- Phải bảo vệ dữ liệu nhạy cảm.
- Cache outage có thể ảnh hưởng authentication/authorization.
- Không nên serialize decoder/manager object để chia sẻ.

Với WebFlux, không gọi blocking Redis client trực tiếp trên event loop. Dùng reactive client hoặc đưa blocking work sang scheduler được quản lý.

## 12. Giới hạn outbound connections và introspection traffic

Một tenant có introspection endpoint riêng có thể tạo thêm HTTP traffic và connection pool.

Nếu mỗi tenant có một WebClient/connection pool không giới hạn, số tenants lớn có thể làm tăng socket, file handles, TLS handshakes và memory.

Cần xem xét:

- Tái sử dụng HTTP client khi trust/TLS policy tương đương.
- Giới hạn connections theo host/tenant.
- Đặt connect/read/response timeout.
- Giới hạn pending acquire và concurrency.
- Áp rate limit cho introspection.
- Circuit breaker cho AS outage.
- Retry có backoff, jitter và giới hạn.
- Không retry vô hạn cho token invalid.
- Không dùng client credentials của tenant này ở tenant khác.

### 12.1. Tách lỗi token và lỗi Authorization Server

| Tình huống | Ý nghĩa |
|---|---|
| Introspection trả active=false | Token không hợp lệ/inactive |
| Introspection trả active=true | Có thể tiếp tục validation/authorization |
| Timeout | Không biết trạng thái token |
| AS 5xx | Không có kết quả xác minh tin cậy |
| TLS/client authentication failure | Cấu hình hoặc trust failure |

Timeout/5xx không đồng nghĩa token inactive, nhưng cũng không được coi token active. Authentication không có kết quả xác minh tin cậy phải thất bại hoặc được xử lý theo availability policy fail-closed đã định nghĩa.

## 13. Bảo vệ resolver khỏi cardinality và request abuse

Resolver chạy trên đường đi authentication. Nếu logic resolve có thể tạo cache entry hoặc gọi network theo input tùy ý, đây là điểm dễ bị khai thác để tiêu tốn tài nguyên.

Các biện pháp:

- Chỉ lookup tenant trong registry hữu hạn.
- Không tạo tenant/decoder từ header tùy ý.
- Allowlist issuer và JWKS/introspection endpoint.
- Giới hạn số distinct issuers/tenants.
- Rate limit unknown tenant/issuer.
- Không tạo cache entry cho mọi token hoặc mọi kid ngẫu nhiên vô thời hạn.
- Coalesce initialization và JWKS refresh.
- Giới hạn concurrency của discovery/introspection.
- Không log raw token hoặc secret.
- Dùng bounded cache với cardinality được đo.

### 13.1. Unknown tenant không được tạo cache entry vô hạn

Nếu mỗi request gửi một tenant ID ngẫu nhiên và resolver cache cả kết quả not-found, cache có thể tăng vô hạn.

Có thể không cache unknown IDs, hoặc dùng negative cache có TTL rất ngắn và maximum size. Đồng thời rate-limit request theo nguồn và route.

### 13.2. Không để metric cardinality tăng theo token

Không đưa raw token, jti, subject hoặc toàn bộ issuer URL tùy ý vào metric label. Metrics có cardinality cao làm tăng memory và chi phí monitoring.

Dùng tenant ID có giới hạn, logical issuer ID hoặc nhóm trạng thái. Token fingerprint chỉ dùng trong cache/internal lookup nếu cần, không dùng làm label metrics.

## 14. Đo capacity thay vì chọn giới hạn theo cảm tính

Trước khi chọn maximumSize hoặc TTL, cần đo:

- Số tenants onboarded và active.
- Số distinct issuers/trust configurations.
- Số managers/decoders đang resident.
- Memory per manager/decoder theo implementation.
- Số JWKS entries và key count mỗi issuer.
- Introspection QPS theo tenant.
- Introspection cache hit ratio.
- JWKS refresh rate và unknown-kid rate.
- Initialization latency/failure.
- Outbound connection count/pending acquire.
- Event/revocation propagation lag.
- Cache eviction và miss rates.
- GC pauses và heap pressure.

### 14.1. Mô hình ước lượng đơn giản

Có thể dùng công thức định hướng:

~~~text
Estimated heap
  ≈ active tenant metadata
  + resident manager/decoder objects
  + cached JWKS/public keys
  + introspection result entries
  + revocation/authorization entries
  + HTTP client/cache overhead
~~~

Hoặc:

~~~text
M_total
  ≈ N_active × M_tenant_config
  + N_manager × M_manager
  + N_decoder × M_decoder
  + N_jwks × M_jwks
  + N_introspection_entries × M_introspection
~~~

Đây là mô hình ước lượng, không phải số đo chính xác. Một decoder có thể chia sẻ client hoặc key cache; một tenant có thể có nhiều decoder. Hãy profile heap và đo dưới tải thật.

### 14.2. Đo theo tenant và toàn hệ thống

Theo từng tenant:

- Request rate.
- Authentication success/failure.
- Introspection latency.
- Cache hit/miss.
- Decoder initialization.
- JWKS refresh.
- Timeout/circuit breaker state.

Toàn hệ thống:

- Heap usage.
- Cache size/eviction.
- Active connections.
- Pending requests.
- Scheduler/event-loop saturation.
- GC.
- Authentication p95/p99.
- Number of active tenants/managers/decoders.

Không log dữ liệu token để đạt observability.

## 15. Cấu hình Caffeine minh họa

Caffeine phù hợp cho cache local trong process, đặc biệt với manager/decoder references hoặc metadata có lifecycle rõ.

~~~java
import java.time.Duration;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

Cache<String, TenantConfig> tenantConfigCache =
    Caffeine.newBuilder()
        .maximumSize(2_000)
        .expireAfterWrite(Duration.ofMinutes(5))
        .recordStats()
        .build();

Cache<DecoderKey, ReactiveAuthenticationManager> managerCache =
    Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterAccess(Duration.ofMinutes(30))
        .recordStats()
        .build();
~~~

Các kích thước và TTL trên chỉ là ví dụ để minh họa API. Hãy chọn dựa trên tenant quota, memory profile và revocation/configuration SLA.

### 15.1. Vì sao cache config và manager có TTL khác nhau?

Tenant config có thể thay đổi khi admin disable tenant hoặc thay issuer/audience. TTL dài mà không có invalidation sẽ khiến node dùng config cũ.

Manager/decoder object có thể tồn tại lâu hơn nếu trust config ổn định. Tuy nhiên, khi policy version thay đổi, cần invalidate ngay manager cũ.

### 15.2. Caffeine không phải distributed cache

Mỗi application instance có một Caffeine cache riêng. Nếu chạy 10 replicas, maximumSize=500 có thể cho phép tới khoảng 10 × 500 entries trên toàn cụm, tùy cache nào được tạo ở mỗi instance.

Không dùng local cache để khẳng định mọi node đã nhận revoke event. Với state cần chia sẻ, dùng distributed store hoặc event propagation có consistency policy.

### 15.3. Eviction listener và resource cleanup

Nếu cache entry giữ một HTTP client/resource riêng, eviction có thể cần cleanup. Chỉ đóng resource do entry thực sự sở hữu; không đóng shared client mà manager khác đang dùng.

Eviction listener nên ngắn, không chạy blocking cleanup trên event loop. Với lifecycle phức tạp, quản lý resource qua một registry riêng và drain/close có kiểm soát.

## 16. Kiểm thử giới hạn và hành vi cache

Không chỉ test authentication thành công. Cần kiểm cả giới hạn capacity, eviction, tenant disable và concurrent initialization.

### 16.1. Tenant admission tests

- Tenant mới trong quota được onboard.
- Tenant vượt quota bị từ chối.
- Hai requests onboarding đồng thời không vượt quota.
- Tenant DISABLED không resolve manager.
- Issuer ngoài allowlist không tạo decoder.
- Custom JWKS URL không được lấy từ request.
- Tenant bị xóa không được tái tạo từ stale cache.

### 16.2. Manager/decoder cache tests

- Cùng trust configuration tái sử dụng manager.
- Policy version mới tạo manager mới.
- Maximum size không bị vượt theo semantics của cache.
- Entry hết hạn được loại bỏ.
- Cache miss không tạo nhiều managers đồng thời.
- Initialization failure có backoff và recovery.
- Tenant eviction không đóng shared resources đang dùng.

### 16.3. JWKS tests

- Key cache hit không gọi endpoint lại trong thời gian cache hợp lệ.
- Key rotation được nhận trong thời hạn policy.
- Unknown kid không tạo refresh storm.
- JWKS timeout không làm token chưa xác minh được chấp nhận.
- Emergency key removal được truyền tới nodes theo SLA.
- Issuer A không dùng key cache của issuer B.

### 16.4. Introspection cache tests

- Active=true được cache không vượt exp hoặc revocation SLA.
- Revoke token làm cache bị invalidated theo policy.
- Active=false negative cache có TTL và maximum size.
- Cache key có issuer/resource namespace.
- Raw token không xuất hiện trong cache key logs/metrics.
- Introspection timeout không được chuyển thành active=true.

### 16.5. Multi-node tests

Với nhiều application instances:

1. Gửi token qua node A và B.
2. Revoke token hoặc disable tenant.
3. Kiểm cả A và B nhận state mới theo SLA.
4. Ngắt event bus hoặc cache backend.
5. Kiểm behavior fail-closed/stale window.
6. Khởi động lại node và xác nhận registry/cache được rebuild an toàn.
7. Kiểm không có tenant hoặc principal bị lẫn.

## 17. Vận hành khi tenant registry hoặc cache gặp lỗi

| Sự cố | Behavior cần xác định |
|---|---|
| Tenant registry không truy cập được | Không tự tạo tenant; fail closed hoặc dùng snapshot có giới hạn tuổi |
| Manager cache đầy | Evict theo policy hoặc từ chối initialization mới có kiểm soát |
| JWKS endpoint timeout | Không chấp nhận key mới chưa xác minh; key cache hiện tại theo stale policy |
| Introspection timeout | Không tạo Authentication thành công |
| Revocation cache unavailable | Fail closed cho thao tác nhạy cảm hoặc theo SLA đã định nghĩa |
| Tenant config đổi nhưng event mất | Reconcile bằng revision/snapshot |
| Caffeine cache bị clear khi restart | Rebuild manager từ trusted registry |
| Một tenant gửi traffic đột biến | Rate limit/concurrency budget theo tenant |

Không có một fallback chung phù hợp cho mọi cache. Key cache, introspection cache và revocation store có các semantics khác nhau.

### 17.1. Stale-while-revalidate

Với metadata hoặc JWKS, một hệ thống có thể tiếp tục dùng dữ liệu cache trong một khoảng stale window khi refresh lỗi. Nhưng stale policy phải phân biệt:

- Known public key đang được dùng để xác minh token đã phát hành.
- Key mới chưa được tải.
- Key cũ đã bị emergency revoke.
- Tenant vừa bị disabled.
- Introspection active result đã cũ.

Không dùng stale-while-revalidate cho tenant disabled hoặc revocation state theo cách vẫn cho phép token bị thu hồi. Stale JWKS có thể tăng availability nhưng cũng kéo dài thời gian tin key bị compromise.

### 17.2. Config revision và reconciliation

Mỗi tenant config có thể mang revision:

~~~text
tenant-a policyVersion = 12
tenant-b policyVersion = 8
~~~

Khi node nhận config revision mới:

1. Cập nhật registry.
2. Ngăn request mới dùng manager revision cũ.
3. Tạo/activate manager mới nếu cần.
4. Invalidate manager/decoder entries cũ.
5. Reconcile nếu node bỏ lỡ event.
6. Ghi metric revision lag.

Event giúp cập nhật nhanh; snapshot/reconciliation giúp phục hồi sau mất event.

## 18. Những anti-pattern thường gặp

**Tạo decoder trên mỗi request.** Gây lặp discovery, key cache và object allocation.

**Tạo decoder cho issuer tùy ý trong JWT chưa verify.** Mở SSRF và trust boundary.

**Không giới hạn tenant registry.** Tenant count và decoder count có thể tăng không kiểm soát.

**Dùng tenant ID làm cache key duy nhất dù policy thay đổi.** Có thể tái sử dụng manager với audience/validator cũ.

**Chia sẻ decoder giữa tenants có audience khác nhau mà validator quá rộng.** Gây cross-tenant token acceptance.

**Dùng một TTL cho mọi cache.** JWKS, introspection, revocation và tenant status có yêu cầu khác nhau.

**Cache active=true quá lâu.** Token đã revoke vẫn có thể được chấp nhận.

**Evict jti denylist trước exp.** Token bị revoke có thể được chấp nhận lại.

**Cache unknown tenant vô hạn.** Attacker có thể tăng cache cardinality.

**Không coalesce manager/JWKS initialization.** Có thể tạo cache stampede và network storm.

**Đóng HTTP client dùng chung khi evict một tenant.** Có thể làm hỏng requests của tenant khác.

**Dùng local Caffeine cache làm revocation store toàn cụm.** Các replicas không tự chia sẻ entries.

**Cache principal/Authentication giữa requests.** Có thể rò rỉ identity hoặc authorities giữa users/tenants.

**Log raw access token hoặc token làm metric label.** Rò rỉ credential và tăng cardinality.

**Fail-open khi introspection/cache/registry lỗi.** Không có kết quả xác minh tin cậy nhưng vẫn tạo Authentication.

**Offboard tenant chỉ bằng xóa decoder.** Tenant registry hoặc cache khác có thể tiếp tục cho phép request.

## 19. Quy trình thiết kế capacity và cache

**Bước 1 — Đếm trust configurations.** Thống kê tenants active, issuers, audiences, JWKS/introspection endpoints và số manager/decoder cần thiết.

**Bước 2 — Đặt admission quota.** Giới hạn tenant, issuer, initialization concurrency và thay đổi cấu hình.

**Bước 3 — Chọn manager lifecycle.** Static registry cho số tenants nhỏ; bounded cache/controlled lazy creation cho registry lớn hoặc dynamic.

**Bước 4 — Định nghĩa cache key.** Gắn issuer, tenant, resource và policy version khi chúng ảnh hưởng trust semantics.

**Bước 5 — Phân loại cache.** Tenant metadata, manager/decoder, JWKS, introspection, revocation và authorization phải có TTL/eviction riêng.

**Bước 6 — Định nghĩa consistency.** Xác định cache local hay distributed, invalidation events, snapshot/reconciliation và stale window.

**Bước 7 — Giới hạn network resources.** Connection pool, timeout, concurrency, rate limit và circuit breaker theo tenant/issuer.

**Bước 8 — Thiết kế cold-start.** Single-flight initialization, bounded executor, backoff và capacity limit.

**Bước 9 — Thiết kế offboarding.** Disable route/tenant trước, ngăn request mới, invalidate caches, drain requests và cleanup resources.

**Bước 10 — Đo metrics.** Cache size/hit/miss/eviction, decoder count, initialization latency, JWKS refresh, introspection QPS, heap và connection pool.

**Bước 11 — Test failure modes.** Cache full, AS timeout, unknown kid, event loss, tenant disable, concurrent onboarding và multi-node propagation.

**Bước 12 — Revisit khi thêm tenant hoặc issuer.** Mỗi trust configuration mới tiêu thụ memory/network budget và làm thay đổi cache cardinality.

## 20. Câu hỏi tự kiểm tra

**1. Số tenant có luôn bằng số decoder không?**

Không. Nhiều tenants có thể chia sẻ issuer và trust policy, nhưng cùng issuer với audience/validators khác nhau có thể cần manager/decoder policy riêng.

**2. Có nên tạo ReactiveJwtDecoder trên mỗi request không?**

Không. Tạo theo trust configuration và tái sử dụng.

**3. Vì sao cache key chỉ có tenant ID có thể không đủ?**

Issuer, audience, JWKS URI hoặc validator policy có thể thay đổi. Cần policy/config revision để tránh tái sử dụng object cũ.

**4. JWKS cache và introspection cache có cùng TTL không?**

Không. Một cache giữ public keys; cache kia giữ trạng thái token. Revocation SLA ảnh hưởng trực tiếp introspection TTL.

**5. Caffeine local cache có chia sẻ entries giữa replicas không?**

Không. Mỗi process có cache riêng.

**6. Có nên cache active=true vô thời hạn không?**

Không. Token có thể bị revoke hoặc hết hạn trong khi cache còn active.

**7. Có thể evict jti denylist trước exp để tiết kiệm memory không?**

Không nếu chưa có cơ chế khác bảo đảm token không thể được chấp nhận lại.

**8. Vì sao cần single-flight manager initialization?**

Để nhiều requests đồng thời cho cùng tenant không tạo nhiều decoder/managers và discovery requests trùng lặp.

**9. Unknown tenant có nên tự tạo decoder từ issuer trong request không?**

Không. Tenant và issuer phải thuộc registry được quản trị.

**10. Offboarding tenant chỉ cần xóa manager cache không?**

Không. Phải disable tenant trong registry, chặn request mới, invalidate các cache liên quan và xử lý lifecycle resources.

**11. Có nên cache Authentication hoặc principal dùng chung giữa requests không?**

Không. Authentication/SecurityContext thuộc request; cache dùng chung có nguy cơ rò rỉ danh tính/quyền.

**12. Khi introspection timeout, có thể coi token active để giữ availability không?**

Không. Không có kết quả xác minh tin cậy thì không được tạo Authentication thành công.

## Kết luận

Multi-tenant Resource Server cần quản lý **tenant count, manager/decoder count và cache cardinality** như các giới hạn vận hành thực sự. Mỗi trust configuration mới có thể làm tăng object graph, JWKS state, HTTP traffic và chi phí initialization. Không tạo decoder theo request, không tự tạo tenant từ input không tin cậy và không giữ mọi manager/cache vô thời hạn.

Tách cache theo semantics: tenant metadata, manager/decoder, JWKS, introspection, revocation và authorization có TTL, invalidation và consistency khác nhau. **Introspection cache ảnh hưởng revocation lag; JWKS cache ảnh hưởng key rotation; tenant cache ảnh hưởng disable/offboarding; revocation cache ảnh hưởng việc token đã bị revoke có thể được chấp nhận lại hay không.**

Dùng bounded cache, tenant admission quota, single-flight initialization, trusted issuer registry, cache key có policy version, connection/concurrency limits và observability. Khi cache hoặc Authorization Server gặp lỗi, giữ fail-closed behavior theo security policy. **Capacity planning phải được xác nhận bằng metrics, heap profiling và load/failure tests, không chỉ bằng một con số maximumSize đặt theo cảm tính.**

### Tài liệu tham khảo

- [Spring Security — Reactive OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — ReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html)
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Caffeine — High Performance Java Caching](https://github.com/ben-manes/caffeine/wiki)
- [Caffeine — Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
