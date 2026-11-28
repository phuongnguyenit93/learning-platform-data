# Chi phí key lookup trong xác thực HTTP request bằng HMAC

## 1. Bài toán: tìm secret trước khi xác minh chữ ký

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client và server sử dụng **shared secret** để tạo và kiểm tra HMAC trên một **canonical request** được thỏa thuận. Canonical request có thể bao gồm phương thức HTTP, URI, các header và/hoặc digest của body. Để chặn request giả mạo và replay, verifier còn phải kiểm tra timestamp, nonce, trạng thái key khi rotation và gắn đúng danh tính client/tenant trước khi đưa request đến tầng **phân quyền**.

Ở chương **Performance**, bài **Chi phí key lookup** phân tích một câu hỏi thực tế: **mỗi lần request đến, server phải mất bao nhiêu tài nguyên để xác định key/secret dùng xác minh HMAC?**

Giả sử đối tác gửi:

~~~http
POST /api/signed/payments?source=partner HTTP/1.1
X-Key-Id: merchant-a-key-v3
X-Timestamp: 2026-11-28T03:30:00Z
X-Nonce: 8f974195-8aa5-46f8-8ce0-00d693c46730
X-Signature: <base64-hmac-sha256>
Content-Type: application/json

{"amount":125000,"currency":"VND"}
~~~

Server phải tra thông tin của `merchant-a-key-v3` từ nguồn đáng tin cậy để biết secret, thuật toán được phép, client/tenant sở hữu, trạng thái active/revoked và thời gian hiệu lực. Phần lớn trường hợp, phép tính HMAC-SHA256 trên một payload nhỏ tương đối rẻ so với một lần truy vấn database, Redis, secret manager hoặc HSM qua mạng. Tuy nhiên **không có tỷ lệ cố định cho mọi hệ thống**: body lớn, HSM từ xa, quota dịch vụ quản lý secret, khoảng cách mạng và cách triển khai đều làm thay đổi phân bổ chi phí.

Sau bài này, người học sẽ có thể:

1. Phân rã độ trễ xác thực để xác định phần **key lookup** tác động đến p50, p95, p99 và throughput.
2. Lựa chọn giữa lookup trực tiếp, cache có giới hạn, preload, single-flight và các mô hình quản lý secret.
3. Bảo toàn **key rotation, revoke, tenant isolation, TTL và fail-closed** khi tối ưu.
4. Ngăn attacker biến `X-Key-Id` chưa xác thực thành nguồn bão truy vấn hoặc tăng cardinality cache/metrics.
5. Thiết kế metric, benchmark và kiểm thử để đánh giá lợi ích hiệu năng mà **không phá vỡ tính đúng đắn của HMAC**.

> Đây là bài học về hiệu năng **của bước lấy key**, không phải cách bỏ qua HMAC. Ví dụ code và số liệu sau chỉ phục vụ giải thích mô hình; cần benchmark trên môi trường, kích thước payload và kho khóa của hệ thống thực tế.

## 2. Key lookup nằm ở đâu trong pipeline?

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Giới hạn kích thước và kiểm tra header]
    B --> C{Timestamp đúng hợp đồng?}
    C -- Không --> R[401; không chạy nghiệp vụ]
    C -- Có --> D[Đọc key ID chưa đáng tin]
    D --> E{Tra key theo policy}
    E -- Có cache hit --> F[Key metadata + key material còn được phép]
    E -- Cache miss --> G[Lookup store / KMS / HSM]
    G -- Không tìm thấy --> R
    G -- Không khả dụng --> U[503; fail closed]
    G -- Tìm được --> F
    F --> H[Kiểm tra hiệu lực / trạng thái key]
    H -- Sai --> R
    H -- Hợp lệ --> I[Tạo canonical và xác minh HMAC]
    I -- Sai --> R
    I -- Đúng --> J[Atomic claim nonce]
    J -- Replay --> R
    J -- Kho nonce lỗi --> U
    J -- Thành công --> K[Authentication từ dữ liệu server]
    K --> L{Authorization: scope / tenant / resource}
    L -- Không đủ quyền --> M[403]
    L -- Đủ quyền --> N[Handler nghiệp vụ]
~~~

Đây là thứ tự **minh họa**. Có thể kiểm tra timestamp trước khi tra key để loại request rõ ràng hết hạn, hoặc có hợp đồng yêu cầu signature verification trước khi kết luận timestamp để giảm khác biệt quan sát được. Dù chọn thứ tự nào, `X-Key-Id` chưa được HMAC xác thực vẫn là **dữ liệu do client khai báo**; lookup không tự chứng minh danh tính.

**Không đưa client ID/tenant/authority trực tiếp từ header request vào `Authentication`.** Metadata gắn với key phải đến từ kho khóa và được dùng để xác thực/giới hạn quyền. Sau HMAC, tầng authorization vẫn xác định quyền thao tác thực tế. Nonce nên được claim nguyên tử **sau khi chữ ký đã hợp lệ** để tránh kẻ tấn công chiếm nonce bằng request giả.

## 3. Phân rã chi phí để đo đúng nút thắt

Với một request, có thể tách tổng thời gian bảo vệ API:

~~~text
T_security =
    T_input_validation
  + T_key_resolution
  + T_canonicalization_and_hash
  + T_hmac_verify
  + T_nonce_claim
  + T_authentication_context
  + T_authorization
~~~

Một phần thời gian có thể chồng lấn trong thiết kế bất đồng bộ, nên tổng trên chỉ là **mô hình diễn giải đường găng**, không phải công thức bắt buộc phải cộng từ mọi metric timer. Nếu filter đọc body và key lookup song song, việc đo latency theo span và request end-to-end phải phản ánh đúng những bước phụ thuộc nhau.

Riêng `T_key_resolution` có thể gồm:

~~~text
T_key_resolution =
    T_cache_check
  + (nếu cache miss) T_network
  + T_store_queue
  + T_store_query_or_crypto_operation
  + T_deserialization
  + T_policy_and_validity_check
~~~

Một mô hình gần đúng về **trung bình** khi có cache:

\[
E[T_{\mathrm{lookup}}] \approx h\,T_{\mathrm{hit}} + (1-h)\,T_{\mathrm{miss}}
\]

Trong đó `h` là hit ratio của **các phép lookup đã đủ điều kiện sử dụng cache**. Công thức này không dự đoán p99: độ trễ đuôi phụ thuộc phân phối miss, request đồng thời, queueing, retry, giới hạn kết nối và cơ chế chống stampede.

Ví dụ hoàn toàn giả định: local cache hit gần như tức thời, nhưng một phần nhỏ request miss phải gọi secret manager qua mạng. Khi có hàng nghìn request/giây, **chỉ một tỷ lệ miss nhỏ vẫn có thể tạo lượng I/O và chi phí đáng kể**. Đừng sử dụng số liệu ví dụ làm mục tiêu SLO; hãy đo chính xác hit/miss, thời gian lookup và sức tải store.

### 3.1. Đừng chỉ xem p50

| Chỉ số | Cho biết điều gì? | Cần cảnh giác |
|---|---|---|
| p50 lookup duration | Độ trễ phổ biến; thường phản ánh cache hit | Có thể bỏ qua miss rất chậm |
| p95/p99 lookup duration | Ảnh hưởng của remote lookup, quá tải hoặc cache churn | Cần đủ sample và histogram phù hợp |
| Cache hit ratio | Tỷ lệ request tránh được backend lookup | Ratio cao vẫn có thể che một nhóm key ít lưu lượng bị lỗi |
| Miss/eviction rate | Hiệu quả kích thước cache và TTL | Spike có thể do rollout, rotation hoặc key ID random |
| In-flight remote lookups | Mức đồng thời đè lên DB/KMS | Nhiều request cùng miss một key gây stampede |
| Lookup error/timeout rate | Sự cố backend có làm xác thực gián đoạn? | Không được xử lý lỗi như “key không tồn tại” |
| Key staleness/revocation lag | Cache có chấp nhận key không còn hợp lệ? | Lợi ích latency không được vượt yêu cầu revoke |
| End-to-end authentication latency | Hiệu năng người dùng thực nhận | Nonce store và body hash có thể là nút thắt khác |

Khi đánh giá hiệu năng, cần **đo tail latency của cả request và lookup**. Một lookup trung bình nhanh không có nghĩa request p99 nhanh, vì request có thể phải đọc body lớn hoặc claim nonce qua Redis.

## 4. Các chiến lược lấy key và đánh đổi

| Chiến lược | Ưu điểm | Rủi ro / chi phí | Phù hợp khi |
|---|---|---|---|
| Lookup trực tiếp mọi request | Trạng thái key khá mới; logic cache đơn giản | Mỗi request thêm network I/O, load, độ trễ và chi phí dịch vụ | QPS thấp hoặc chính sách key cực nghiêm ngặt |
| In-memory TTL cache | Cache hit nhanh; giảm tải kho khóa | Key stale, chiếm heap, cache ở từng replica khác nhau | Key được dùng lặp lại và có cơ chế invalidation/revoke |
| Distributed cache | Nhiều service/replica chia sẻ kết quả lookup | Thêm một hop mạng, rủi ro stale ở lớp cache và nguồn gốc dữ liệu | Lượng replica cao, metadata thống nhất, có policy |
| Preload key được phép | Giảm miss trên đường nóng | Khó làm mới, key set lớn; phân phối secret nhiều nơi | Tập key nhỏ, kiểm soát được và cập nhật an toàn |
| Secret manager/KMS trực tiếp | Secret có thể tập trung hoặc không export; audit truy cập | Latency, quota, chi phí, availability, rate limiting | Policy/crypto boundary yêu cầu |
| HSM/KMS thực hiện MAC từ xa | Secret không cần xuất khỏi vùng bảo vệ | Mỗi verify có thể thành remote crypto operation, throughput hạn chế | Bảo vệ key vật lý/quy định cao |

**Cache metadata và cache secret là hai quyết định khác nhau.** Một ứng dụng có thể cache trạng thái/tenant/secret reference nhưng vẫn gọi HSM để verify MAC. Nếu secret được phép export để tính HMAC cục bộ, cache secret phải tính đến bảo vệ bộ nhớ, quyền tiến trình, heap dump, rotate/revoke và bản sao trên nhiều node. Không mặc định kéo secret về mọi pod chỉ vì tăng tốc.

Một kiến trúc thường gặp:

~~~mermaid
flowchart LR
    R[Request có key ID] --> V[HMAC verifier]
    V --> L[Bounded in-memory key cache]
    L -->|Hit| A[Kiểm tra hiệu lực + verify]
    L -->|Miss| S[Trusted key repository / secret manager]
    S -->|Found| L
    S -->|Unavailable| F[Fail closed]
    A --> N[Nonce store, authorization]
~~~

**Không thêm cache trước khi xác minh tính đúng đắn của hợp đồng canonical.** Cache không thể sửa lỗi ký sai method/URI/header/body qua gateway; nó chỉ thay cách lấy key. Tối ưu tốt nhất là không làm sai semantics.

## 5. Key ID là input chưa đáng tin: bảo vệ trước khi lookup

Một attacker có thể gửi hàng loạt giá trị `X-Key-Id` không tồn tại để ép service gọi kho key trên từng request. Đây là dạng **lookup amplification**: mỗi HTTP request giá rẻ biến thành một truy vấn nội bộ đắt, thậm chí vượt quota KMS hoặc secret manager.

Các hàng rào cần có:

1. **Bắt buộc đúng một key ID**, kiểm tra kích thước, charset, ký tự điều khiển, định dạng và version trước mọi I/O. Từ chối duplicate header; đừng chọn giá trị đầu/cuối tùy framework.
2. **Giới hạn body, header và connection** tại ingress lẫn service, tránh để thao tác đọc body hoặc parsing vô hạn chiếm tài nguyên trước lookup.
3. **Rate limit và concurrency limit** trên route HMAC, đặc biệt ở mức pre-authentication; một giới hạn theo key ID tự khai có thể bị attacker vượt bằng cách đổi key ID ngẫu nhiên.
4. **Không dùng raw key ID làm metric label**, cache name, thread name hoặc chuỗi log không được làm sạch. Metric dùng outcome, route ID, service và error class hữu hạn.
5. **Giới hạn cache entry** bằng maximum size/weight; không cho random key ID tạo hàng triệu negative entries.
6. **Không dò mọi secret trong hệ thống** khi key ID không tìm thấy. Key lookup phải có đường định danh xác định và được giới hạn bởi quyền truy cập/tenant.

Nếu key ID chỉ duy nhất trong một tenant, phải xác định tenant **từ một nguồn đáng tin** (ví dụ route/hợp đồng đã ràng buộc hoặc một định danh được xác thực ở tầng riêng), rồi mới lookup theo composite key. Không tin `X-Tenant-Id` tự khai để chọn không gian key và tạo principal. Một thiết kế khác là dùng key ID duy nhất toàn cục và lấy tenant từ bản ghi key phía server sau verify.

## 6. Cache TTL, rotation và revocation: điểm đánh đổi bảo mật

Cache giúp giảm latency nhưng có thể làm service chấp nhận một key vừa bị thu hồi. Với HMAC, đây không chỉ là dữ liệu cũ trên dashboard: **một secret đã revoke vẫn có thể xác thực request mới** nếu cache còn coi nó là active.

### 6.1. Những thời điểm phải phân biệt

- `notBefore`: thời gian key được phép bắt đầu sử dụng.
- `notAfter`: thời gian key hết hiệu lực theo policy.
- `revokedAt`: thời điểm nhà quản trị vô hiệu hóa key ngay lập tức.
- `loadedAt`: thời điểm một cache entry được lấy từ nguồn tin cậy.
- `refreshAt/expiresAt` của cache: mốc cần hỏi lại nguồn hoặc từ chối dùng bản cũ.

**TTL cache là giới hạn về độ cũ của dữ liệu, không phải thời hạn hiệu lực của key.** Một cache entry còn TTL chưa chắc key còn active; trước khi verify phải kiểm tra notBefore/notAfter và trạng thái hiệu lực hiện có. Ngược lại, việc entry hết TTL không có nghĩa key bị revoke: nó chỉ cần được resolve lại trước khi cho phép xác thực.

Một chính sách cache có thể dùng:

~~~text
cacheLifetime = min(
    maximumConfiguredCacheTTL,
    timeUntilKeyNotAfter,
    maximumAcceptedRevocationStaleness
)
~~~

Đây là khung tư duy, **không phải giải pháp revoke tức thì**. Nếu yêu cầu “revoke ngay”, chỉ giới hạn TTL không đủ; cần invalidation/push policy tin cậy hoặc recheck online, và cân nhắc điều gì xảy ra khi kênh invalidation bị ngắt. Không chấp nhận key cũ theo kiểu **stale-if-error** nếu vi phạm chính sách revoke.

### 6.2. Key rotation và cache nhiều replica

Ví dụ key cũ `K1` và key mới `K2` cùng thuộc một client:

~~~text
T0: K1 active
T1: tạo K2, bắt đầu overlap
T2: client chuyển sang ký bằng K2
T3: K1 hết overlap hoặc bị revoke
~~~

Trong khoảng overlap, verifier chỉ chấp nhận **những key ID còn hợp lệ theo policy**, không thử tuần tự secret K1/K2 tới khi MAC khớp. Khi K1 bị revoke, mọi replica phải áp dụng trạng thái mới trong mức độ trễ revoke đã được thiết kế; nếu một replica giữ entry K1 cũ lâu hơn thì việc xác thực không nhất quán.

Các test đặc biệt quan trọng: revoke key rồi gửi request vào **tất cả** replica, simulate mất thông điệp invalidation, rollback deployment, cache warm/cold và clock lệch. Nếu key store không phản hồi, không sử dụng key stale một cách tùy tiện để giữ uptime.

### 6.3. Negative caching: hữu ích nhưng dễ bị lạm dụng

Khi key ID không tồn tại, negative cache có thể giảm lookup lặp lại từ cùng một giá trị:

~~~text
resolve("unknown-id")
  → store returns NOT_FOUND
  → cache absence for a short bounded period
  → repeated identical requests avoid extra store lookup
~~~

Nhưng cần:

- Dùng **TTL ngắn** và **số entry tối đa**, vì key mới tạo có thể chưa xuất hiện khi negative cache còn tồn tại.
- Không biến lỗi timeout/5xx của key store thành `NOT_FOUND` để cache. `NOT_FOUND` chỉ được ghi khi lookup thành công và nguồn xác nhận không có key.
- Hạn chế request với key ID ngẫu nhiên; negative cache không xử lý được attacker dùng key ID mới ở mọi request.
- Không để negative cache hay phản hồi HTTP làm lộ rằng một key ID có tồn tại. Ở bên ngoài, unknown key và bad MAC thường nhận lỗi 401 chung theo policy.
- Cân nhắc nhất quán khi tạo/rotate key: invalidation hoặc giới hạn thời gian cache âm để key vừa phát hành không bị từ chối kéo dài.

## 7. Thundering herd, single-flight và backpressure

Một secret phổ biến vừa hết TTL, hàng nghìn request đồng thời đều gọi lookup cùng key ID. Nếu không đồng bộ các miss, một lần cache expiry có thể nhân thành hàng nghìn query, tạo **cache stampede**.

~~~text
Không có single-flight:
  request 1 ─┐
  request 2 ─┼─> cùng key ID ─> N lần network lookup
  request N ─┘

Có single-flight:
  request 1 ─┐
  request 2 ─┼─> cùng key ID ─> 1 in-flight lookup ─> nhiều waiter
  request N ─┘
~~~

**Single-flight** gom các lookup đang chạy cho **cùng cache key** thành một future/`Mono` được chia sẻ trong phạm vi thiết kế. Nó không thay thế:

- Giới hạn số lượng key ID khác nhau được tra cùng lúc.
- Timeout và deadline riêng của lần lookup.
- Circuit breaker hoặc bulkhead để bảo vệ kho khóa khi quá tải.
- Chính sách cancel khi không còn waiter và khống chế bộ nhớ của hàng đợi.
- Xử lý invalidation đúng lúc; một lookup chậm từ trước revoke không được ghi đè dữ liệu mới và làm sống lại key.

Khi key ID liên tục thay đổi, single-flight gần như không giúp ích; cần **admission control** và rate limiting. Khi cache miss rất chậm, tăng số request đang đợi có thể làm cạn thread/connection/memory trước cả khi CPU tính HMAC bị đầy.

### Spring MVC và Spring WebFlux

- **Servlet/MVC:** dùng data source và connection pool có giới hạn, timeout rõ ràng; tránh một request giữ thread quá lâu vì lookup. Cân nhắc cache/single-flight trước khi tăng thread pool vô hạn.
- **WebFlux:** dùng client/reactive driver không blocking cho Redis/database/key service; không gọi `block()` trên Netty event-loop. Nếu dependency chỉ có API blocking, cần cách cô lập trên scheduler phù hợp với giới hạn tải, không coi việc bọc `Mono.just(...)` là biến I/O đồng bộ thành reactive.

Ở cả hai, một hệ thống hoạt động đúng phải **từ chối có kiểm soát** khi không thể xác minh an toàn thay vì fallback “cho phép request nếu key lookup chậm”.

## 8. Ví dụ Java 17+: phân biệt key not found với store unavailable

Ví dụ dùng Spring WebFlux/Reactor để cho thấy đường đi **bất đồng bộ** và cách đo lookup. Cấu trúc key record, repository và scope được tối giản; code minh họa chưa phải implementation của toàn bộ HMAC verifier.

~~~java
import java.time.Instant;
import reactor.core.publisher.Mono;

public record HmacKeyMetadata(
        String keyId,
        String clientId,
        String tenantId,
        Instant notBefore,
        Instant notAfter,
        boolean revoked,
        String secretReference) {
    // secretReference chỉ là tham chiếu nội bộ, không phải shared secret.
}

public interface ReactiveHmacKeyRepository {
    // Mono.just(record): tìm thấy bản ghi.
    // Mono.empty(): lookup thành công và key không tồn tại.
    // Mono.error(...): hạ tầng không khả dụng hoặc lookup thất bại.
    Mono<HmacKeyMetadata> findByKeyId(String keyId);
}
~~~

Lớp resolver tách biệt quyết định **key không có** với **không tra cứu được**:

~~~java
import java.time.Clock;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.authentication.BadCredentialsException;
import reactor.core.publisher.Mono;

public final class HmacKeyResolver {
    private final ReactiveHmacKeyRepository repository;
    private final Clock clock;

    public HmacKeyResolver(
            ReactiveHmacKeyRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Mono<HmacKeyMetadata> resolveActive(String keyId) {
        return Mono.defer(() -> repository.findByKeyId(keyId))
                // Chỉ hạ tầng lỗi mới được ánh xạ sang 503 sau đó.
                .onErrorMap(error -> new AuthenticationServiceException(
                        "Key lookup unavailable", error))
                .switchIfEmpty(Mono.error(
                        new BadCredentialsException("Invalid HMAC credentials")))
                .flatMap(key -> {
                    var now = clock.instant();
                    boolean permitted = !key.revoked()
                            && !now.isBefore(key.notBefore())
                            && now.isBefore(key.notAfter());
                    return permitted
                            ? Mono.just(key)
                            : Mono.error(new BadCredentialsException(
                                    "Invalid HMAC credentials"));
                });
    }
}
~~~

Những điểm quan trọng:

1. `Mono.empty()` là **“không tồn tại”** chỉ khi repository thực sự trả kết quả lookup thành công. Timeout/đứt mạng phải là `Mono.error(...)`; không `onErrorReturn(null)` hoặc biến thành unknown key.
2. `onErrorMap` ở **trước** `switchIfEmpty`/`flatMap` để không biến chính `BadCredentialsException` do resolver tạo thành lỗi store.
3. Thời hạn hiệu lực được kiểm tra tại lúc sử dụng key, không chỉ tại lúc đưa vào cache. Nếu kênh revoke riêng tồn tại, tính đúng đắn phụ thuộc việc phản ánh revoke kịp thời.
4. Secret chưa được lấy từ `secretReference`; thiết kế thực tế cần một lớp có quyền truy cập secret hoặc dịch vụ thực hiện MAC. Không log secret reference, key ID raw hoặc thông tin key record trong lỗi HTTP.
5. Signature vẫn phải được xác minh trên **canonical request đúng hợp đồng** và so sánh theo byte an toàn về thời gian; sau đó mới claim nonce và tạo `Authentication`. Resolver không tự cấp quyền.

**Giới hạn của ví dụ:** không có body buffer, cache, nonce store, error handler hay distributed invalidation. Hãy hoàn thiện các thành phần đó trước khi dùng trong production. `keyId` cần được kiểm tra format/kích thước/duy nhất header từ lớp HTTP trước khi gọi `resolveActive`.

### 8.1. Instrument lookup bằng Micrometer

Metric nên đo outcome theo bộ giá trị hữu hạn, không dùng key ID/tenant ID làm tag. Có thể instrument **repository lookup** riêng với **cache lookup**, giúp phân biệt cache hit và remote miss:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.publisher.Mono;

public final class MeteredKeyLookup {
    private final ReactiveHmacKeyRepository repository;
    private final MeterRegistry registry;

    public MeteredKeyLookup(
            ReactiveHmacKeyRepository repository, MeterRegistry registry) {
        this.repository = repository;
        this.registry = registry;
    }

    public Mono<HmacKeyMetadata> find(String keyId) {
        // Mono.defer tạo phép đo riêng cho mỗi subscription.
        return Mono.defer(() -> {
            long started = System.nanoTime();
            AtomicReference<String> outcome =
                    new AtomicReference<>("cancelled");

            return repository.findByKeyId(keyId)
                    .doOnNext(found -> outcome.set("found"))
                    .switchIfEmpty(Mono.defer(() -> {
                        outcome.set("not_found");
                        return Mono.empty();
                    }))
                    .doOnError(error -> outcome.set("error"))
                    .doFinally(signal -> Timer.builder("hmac.key.lookup.duration")
                            .description("Trusted key repository lookup duration")
                            .tag("outcome", outcome.get())
                            .register(registry)
                            .record(System.nanoTime() - started,
                                    TimeUnit.NANOSECONDS));
        });
    }
}
~~~

Lớp này đo **thời gian repository lookup** mỗi subscription với `found/not_found/error/cancelled`. Nó không tự đo cache hit: để phân biệt cache, cần instrument tầng cache riêng và xác định rõ “request hit”, “load”, “coalesced waiter” là các mẫu đo khác nhau. Khi instrument production, cần kiểm tra behavior cancel và điều kiện kết thúc để mỗi subscription được ghi đúng một outcome.

Ở hệ thống quan sát thực tế, cấu hình percentile histogram/SLO buckets theo nhu cầu, tránh tự xây label với raw request. Log phục vụ điều tra có thể liên kết bằng request ID từ gateway đáng tin cậy, nhưng **request ID không được là metric tag**.

## 9. Cache design minh họa: lookup, refresh và invariant

Pseudocode một cache bounded có single-flight:

~~~text
resolve(keyId):
    validateKeyIdShapeAndSize(keyId)
    scope = trustedLookupScope(keyId)      // không lấy quyền từ header tự khai
    cacheKey = scope + keyId

    if cache.getFresh(cacheKey) exists:
        assertKeyValidityAtCurrentTime(cacheEntry)
        return cacheEntry

    if concurrencyBudgetExhausted:
        failUnavailableOrRejectByPolicy   // không tự cho phép bypass

    result = singleFlight(cacheKey, () ->
        trustedRepository.lookup(cacheKey) with bounded timeout)

    if result == FOUND:
        checkVersionAndRevocationPolicy(result)
        cacheForBoundedTTL(result, keyNotAfter, allowedStaleness)
        return result

    if result == NOT_FOUND:
        optionallyNegativeCacheWithShortTTLAndBoundedSize(cacheKey)
        rejectAsInvalidCredential

    if result == UNAVAILABLE:
        doNotCacheAsNotFound
        failClosedAsServiceUnavailable
~~~

**Không áp dụng nguyên xi như code production.** Các lựa chọn TTL, revocation propagation, single-flight, số lượng inflight và deadline cần khớp chính sách an toàn. Đặc biệt, một kết quả cũ trả về **sau thông điệp revoke** phải không được phép ghi lại trạng thái `active` vào cache.

Những câu hỏi phải trả lời khi review:

| Câu hỏi | Vì sao quan trọng? |
|---|---|
| Cache chứa secret hay chỉ metadata/reference? | Quyết định phạm vi lan truyền bí mật, heap dump và quyền đọc |
| Key ID có unique toàn hệ thống không? | Ngăn lấy nhầm key giữa tenant |
| Entry nào không được cache? | Lỗi hạ tầng, bản ghi malformed, policy bất thường |
| TTL tối đa và cách invalidate là gì? | Ranh giới chấp nhận key bị revoke/hết hạn |
| Khi refresh lỗi có dùng stale không? | Có thể chấp nhận credential đã bị thu hồi |
| Max cache size/weight và cache eviction? | Chống memory exhaustion bởi key ID ngẫu nhiên |
| Single-flight có tách theo scope/version? | Tránh chia sẻ kết quả giữa tenant hoặc key epoch |
| Secret được xóa/đổi khi invalidate thế nào? | Giảm khả năng secret còn trong process memory lâu hơn cần thiết |
| Có giới hạn remote concurrent calls? | Tránh làm sập secret store khi stampede |
| Khi policy không đồng bộ giữa replica? | Ngăn chấp nhận key khác nhau trên các node |

## 10. Tối ưu không được làm hỏng an toàn

### 10.1. Fast reject không phải full authentication

Kiểm tra header thiếu, version sai, timestamp ngoài cửa sổ hoặc body quá lớn **có thể giúp tránh lookup đắt**. Tuy nhiên:

- Timestamp/nonce/header lúc đó chưa có chữ ký hợp lệ; log/metric phải ghi rõ kết quả là pre-auth, không xác nhận danh tính đối tác.
- Chữ ký sai, key không tồn tại và key đã revoke nên có HTTP response đủ thống nhất theo chính sách để tránh bị lợi dụng như key enumeration oracle.
- Không bỏ signature verification dù key cache trả hit; cache chỉ thay nguồn secret.
- Không bỏ qua nonce để tiết kiệm một lần Redis I/O: chữ ký HMAC hợp lệ vẫn có thể bị replay.
- Không tái sử dụng `Authentication` từ request trước chỉ vì cùng key ID; mỗi request cần ràng buộc method/URI/header/body/timestamp/nonce đúng hợp đồng.

### 10.2. Key selection và canonical request phải khớp nhau

Nếu client ký `X-Key-Id` trong canonical string, verifier phải dùng **chính biểu diễn đã thỏa thuận**. Một proxy tự sửa key ID, header trùng hoặc key ID được parser normalization khác nhau có thể khiến service lookup một secret nhưng xác minh trên dữ liệu khác. Đây là lỗi hợp đồng/trust boundary, không phải vấn đề cache.

Khi proxy rewrite public URI sang đường dẫn nội bộ, service phải tái tạo canonical request đúng public target đã được bảo vệ hoặc logical route đã thỏa thuận, không chỉ cache key rồi bỏ qua path mismatch. HMAC hợp lệ không tự chứng minh được quyền `payments:write` hoặc ownership của resource.

### 10.3. Lỗi hạ tầng phải fail closed

| Điều kiện | Phản hồi gợi ý | Điều không được làm |
|---|---|---|
| Key không tồn tại hoặc đã revoke | 401 theo API | Tiết lộ key có tồn tại hay không |
| MAC sai với key còn active | 401 | Thử mọi key/secret để tìm chữ ký khớp |
| Timestamp/nonce không hợp lệ | 401 | Bỏ kiểm tra replay để tăng tốc |
| Kho key timeout/unavailable | 503 hoặc lỗi hệ thống tương ứng | Dùng stale credential trái policy hoặc coi lỗi là “not found” |
| Kho nonce không khả dụng | 503 hoặc lỗi hệ thống tương ứng | Cho qua request đã ký |
| Key đúng nhưng thiếu authority | 403 | Cấp quyền chỉ vì cache hit hoặc signature đúng |
| Body vượt giới hạn | 413 | Buffer vô hạn trước khi lookup |

Khi có key cache và secret manager cùng lỗi, quyết định sử dụng cache phải **phù hợp với chính sách staleness/revoke đã được đánh giá trước**; không tự động “serve stale on error” chỉ vì p99 giảm. Nếu mô hình yêu cầu revoke tức thì, bắt buộc có cơ chế xác định trạng thái hiện hành đủ tin cậy.

## 11. Kế hoạch benchmark và kiểm thử

Để so sánh các chiến lược, test cùng một hợp đồng HMAC, tập client/key, payload và cấu hình nonce store. Không dùng mock repository chỉ trả tức thì để kết luận về performance của remote key lookup.

### 11.1. Các workload nên có

| Workload | Mục tiêu |
|---|---|
| 100% key hot, cache đã warm | Đo chi phí hit và CPU verify |
| Trộn key hot/cold với hit ratio được kiểm soát | Đo miss rate, backend QPS và p95/p99 |
| Nhiều key ID chưa tồn tại, mỗi ID khác nhau | Đánh giá random-key abuse và negative-cache churn |
| Một key hot vừa hết TTL, request đồng thời tăng mạnh | Kiểm tra stampede/single-flight |
| Cache cold sau deployment/scale-out | Kiểm tra warm-up, tự bảo vệ store và readiness |
| Thêm/revoke key khi tải lớn | Đo policy propagation và acceptance correctness |
| KMS/DB tăng latency hoặc timeout một phần | Kiểm tra deadline, bulkhead, không treo hết request |
| Key store hỏng hoàn toàn | Xác minh fail closed và mã lỗi, không có side effect |
| Hai hoặc nhiều replica sau gateway | Kiểm tra cache riêng, invalidation, tenant và nonce store chung |
| Body từ nhỏ đến sát giới hạn | Xác định body hash hay key lookup là nút thắt thật |

**So sánh phải cùng điều kiện:** concurrency, ramp-up, duration, kích thước payload, phân phối key, network latency, number of replicas, rate limit và crypto provider. Chạy đủ lâu để quan sát cache expiry/refresh, chứ không chỉ đo sau khi cache đã warm.

### 11.2. Những chỉ số cần thu

- End-to-end HTTP latency: p50, p95, p99, throughput, error rate và tỷ lệ request hoàn thành nghiệp vụ.
- Key lookup latency theo `cache_hit/cache_miss` và `found/not_found/error`, với schema đo rõ ràng.
- Secret manager/DB/KMS QPS, connection pool, quota, throttling và timeout.
- Cache hit/miss, eviction, weight, number of entries, stale/invalidation events, in-flight loads.
- CPU/memory/GC, thread pool hoặc Netty event-loop saturation; số request đang đợi.
- Nonce store latency và replay rejection để bảo đảm tối ưu key lookup không che chi phí anti-replay.
- Security invariants: key revoke không được dùng, tenant isolation, response 401/403/503 đúng, **không side effect trên request bị từ chối**.

### 11.3. Ví dụ kiểm thử key lookup trong Java

Test đơn vị cần dùng `Clock.fixed` và fake repository để tách các nhánh:

~~~java
// Pseudocode minh họa với Reactor StepVerifier và fake repository.
// Tạo một HmacKeyMetadata đang active tại thời điểm clock cố định.
when(repository.findByKeyId("key-active"))
        .thenReturn(Mono.just(activeKey));
StepVerifier.create(resolver.resolveActive("key-active"))
        .expectNext(activeKey)
        .verifyComplete();

// Không tồn tại -> lỗi credential, không phải 503.
when(repository.findByKeyId("key-unknown"))
        .thenReturn(Mono.empty());
StepVerifier.create(resolver.resolveActive("key-unknown"))
        .expectError(BadCredentialsException.class)
        .verify();

// Store lỗi -> AuthenticationServiceException, phải fail closed.
when(repository.findByKeyId("key-timeout"))
        .thenReturn(Mono.error(new RuntimeException("store unavailable")));
StepVerifier.create(resolver.resolveActive("key-timeout"))
        .expectError(AuthenticationServiceException.class)
        .verify();

// Revoke / notBefore / notAfter -> từ chối dù cache còn entry.
~~~

Đây là **đoạn trích**, không phải file JUnit tự chạy độc lập; cần khai báo fake repository, `activeKey` và resolver theo fixture. Trong integration test, dùng kho key và gateway gần production để phát hiện cache stale, race invalidation và lỗi signature qua proxy.

### 11.4. Acceptance checklist cho bảo mật và hiệu năng

- [ ] Có baseline trước tối ưu; biết p50/p95/p99 của lookup, verify và toàn request.
- [ ] Tính đúng key/tenant/algorithm, không trial-and-error nhiều secret, không coi key ID là danh tính trước verify.
- [ ] Input `X-Key-Id` được giới hạn độ dài/cú pháp/uniqueness trước khi truy vấn.
- [ ] Cache có max entries/weight, TTL, thống kê eviction và giới hạn concurrent remote loads.
- [ ] Lỗi hạ tầng không bị cache thành “unknown key”; cache stale không tự bypass revoke.
- [ ] Key rotation/revocation đồng bộ đủ nhanh trên mọi replica theo yêu cầu đã định nghĩa.
- [ ] Có test cache warm/cold, TTL expiry, stampede, random key IDs và key store timeout.
- [ ] Authn vẫn kiểm tra canonical method/URI/header/body, timestamp và nonce nguyên tử.
- [ ] Authz vẫn xác minh scope/tenant/resource sau khi signature đúng.
- [ ] 401/403/413/503 đúng nguyên nhân; nhánh lỗi không gọi handler hoặc tạo side effect.
- [ ] Metric có tag hữu hạn (outcome, route ID, service), không log secret/raw signature/key ID chưa xác thực.
- [ ] Đã benchmark bằng workload và đường mạng tương đương production; tối ưu không chỉ dựa trên cache hit ratio.

## 12. Tổng kết

**Chi phí key lookup** không chỉ là một phép tìm khóa: nó có thể kéo theo network I/O, queue, quota KMS/secret manager, đồng bộ policy và độ trễ đuôi của toàn request. Cache, preload và single-flight giúp giảm chi phí, nhưng cũng đưa thêm rủi ro **key stale, revoke chậm, cache stampede và bị khai thác qua key ID chưa xác thực**.

Thiết kế tốt cần đo đúng đường găng, giới hạn tài nguyên trước khi lookup, lựa chọn policy TTL/invalidation phù hợp và giữ nguyên ranh giới bảo mật: **key phải còn hiệu lực, HMAC phải khớp canonical request, nonce phải chống replay, authorization phải độc lập và lỗi không xác minh được phải fail closed**. Chỉ coi tối ưu là thành công khi vừa giảm latency/tải backend **vừa vượt qua kiểm thử về key rotation, revoke, tenant isolation và side effect**.
