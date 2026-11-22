# Cache stampede và phối hợp nạp lại dữ liệu

Một API đọc thông tin sản phẩm từ Redis cache và dùng một cơ sở dữ liệu NoSQL làm nguồn sự thật. Sản phẩm đang nổi bật có 12.000 lượt đọc mỗi giây. Bình thường, Redis trả kết quả rất nhanh, nên NoSQL chỉ nhận số ít truy vấn. Nhưng khi một cache key vừa hết TTL, hàng nghìn request cùng đọc được cache miss. Nếu mỗi request tự truy vấn NoSQL và ghi lại cache, một sự kiện hết hạn đơn lẻ tạo ra hàng nghìn truy vấn trùng lặp. Khi source database chậm, các truy vấn đang chờ tích tụ, request timeout rồi retry, dẫn đến áp lực tăng thêm.

Hiện tượng đó được gọi là **cache stampede** (còn có tên *dogpile effect* hoặc *cache breakdown* trong một số tài liệu). Vấn đề không chỉ là tỷ lệ cache hit thấp; **một miss trên key nóng có thể tạo ra burst tải cực lớn trong thời gian ngắn**, kéo theo queueing, connection exhaustion, retry storm và giảm khả năng phục vụ của database.

Bài thuộc **Database No SQL → Bộ nhớ đệm dữ liệu**, giải thích nguyên nhân và cách phối hợp nạp lại cache giữa nhiều request, threads, pods và regions. Nội dung gồm in-process singleflight, Redis distributed refill lease, TTL jitter, stale-while-revalidate, soft/hard expiry, negative caching, version-aware fill, nguyên tắc consistency với NoSQL, Java 21, Caffeine, Redis, metrics, fault injection và runbook.

> **Nguyên tắc:** Khi nhiều request cùng cần một key chưa có trong cache, **không để mỗi request tự tải lại từ NoSQL**. Hãy chia sẻ một công việc nạp, giới hạn concurrency, phân tán retry/TTL và cho phép trả stale chỉ khi hợp đồng nghiệp vụ cho phép. Cơ chế phối hợp nạp cache không phải transaction lock để xác nhận booking, thanh toán hay quyền truy cập.

> **Phạm vi:** Số liệu và TTL trong các ví dụ là giả định học tập. Cách thức refresh, cache expiration, locking và consistency cụ thể phụ thuộc sản phẩm, thư viện, phiên bản và topology. Không dùng các thông số minh họa làm cấu hình production mặc định.

## 1. Nhìn thấy stampede qua luồng request

Một cache-aside read cơ bản:

~~~~text
HTTP GET /products/SKU9
    |
    v
cache.get(key)
    | HIT
    +----> return value
    |
    | MISS
    v
NoSQL read
    |
    v
cache.set(key, value, TTL)
    |
    v
return value
~~~~

Trong một request đơn lẻ, flow này có vẻ hợp lý. Vấn đề xảy ra khi nhiều request chạy đồng thời:

~~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant C as Request C
    participant K as Cache
    participant D as NoSQL source
    A->>K: GET hot key
    B->>K: GET hot key
    C->>K: GET hot key
    K-->>A: MISS
    K-->>B: MISS
    K-->>C: MISS
    A->>D: Load hot key
    B->>D: Load hot key
    C->>D: Load hot key
    D-->>A: value v7
    D-->>B: value v7
    D-->>C: value v7
    A->>K: SET v7
    B->>K: SET v7
    C->>K: SET v7
~~~~

Nếu có 10.000 callers, cùng một database read có thể bị lặp hàng nghìn lần.

### 1.1. Stampede nguy hiểm ở những điểm nào?

- **Source read amplification:** một giá trị cần nạp trở thành hàng nghìn reads.
- **Hot partition:** cùng document/partition bị truy cập quá mức.
- **Connection exhaustion:** NoSQL client pool bị chiếm bởi loads trùng.
- **CPU/IO pressure:** serialization, index reads, disk/cache misses bị nhân lên.
- **Queueing:** source chậm làm nhiều callers cùng giữ threads/futures.
- **Retry storm:** client timeout rồi phát lại request.
- **Cascading failure:** hệ thống khác dùng chung database bị ảnh hưởng.
- **Stale overwrite:** loader cũ hoàn tất sau update mới và ghi dữ liệu lạc hậu vào cache.
- **Recovery chậm:** khi database trở lại, backlog và cache warming tạo burst mới.

### 1.2. Công thức ước lượng đơn giản

Giả sử một hot key nhận \(\lambda=10.000\) request/s và một source load mất \(W=0,4\) giây. Trong mô hình không phối hợp, lượng requests bắt đầu load trong khoảng ấy có thể gần:

\[
L \approx \lambda W=10.000 \times 0,4 = 4.000
\]

Đây là trực giác từ quan hệ throughput–latency và không phải một phép đo thực. Thời gian load càng kéo dài, số loads/waiters chồng lên nhau có thể càng lớn.

### 1.3. Cache hit ratio theo giờ có thể đánh lừa

Cache hit rate 99,9% theo một giờ vẫn có thể che đợt 4.000 source requests trong vài trăm mili giây. Cần theo dõi **short-window miss bursts**, số origin loads cho cùng key, p99, connection pool waits và thời gian hồi phục, không chỉ tỷ lệ hit trung bình.

## 2. Phân biệt stampede, avalanche, penetration và thundering herd

| Hiện tượng | Cơ chế | Ví dụ | Phòng tránh trọng tâm |
| --- | --- | --- | --- |
| **Cache stampede** | Nhiều requests cùng miss một key nóng | Product SKU9 vừa hết TTL | Singleflight, per-key coordinated refill, SWR |
| **Cache avalanche** | Nhiều keys cùng mất/hết hạn | Một triệu keys warm cùng lúc, hoặc Redis restart | TTL jitter, staggered warmup, origin admission |
| **Cache penetration** | Liên tục hỏi keys không tồn tại | Bot quét product IDs ngẫu nhiên | Negative caching, validation, filter phù hợp |
| **Thundering herd** | Nhiều callers cùng thức dậy theo một sự kiện | Tất cả retry sau đúng 100 ms | Jitter, bounded retries, backpressure |
| **Hot-key pressure** | Một key luôn có lưu lượng lớn | Product sale flash event | L1/L2, refresh-ahead, replication theo contract |

Những tình huống có thể chồng nhau. Redis outage gây avalanche; sản phẩm hot tạo stampede; gateway retries đồng thời tạo thundering herd.

### 2.1. Stampede không chỉ xảy ra do TTL

Những nguyên nhân khác:
- Eviction do memory pressure dù TTL chưa hết.
- Manual invalidation sau source update.
- Deployment đổi cache namespace.
- Cache node crash hoặc failover.
- Cold start nhiều pods cùng lúc.
- Read-through loader thất bại.
- Một hot key bị xóa sau publish event.
- Redis cluster chuyển slot và cache mapping thay đổi.
- Region traffic failover tới một cache cold.

**Tăng TTL không xử lý được tất cả nguyên nhân.**

## 3. Ba ranh giới nhất thiết phải phân biệt

1. **Source of truth:** NoSQL database có thẩm quyền quyết định data/transaction state nào đã được commit.
2. **Cache:** dữ liệu dẫn xuất nhằm giảm độ trễ/tải; có expiry và có thể stale.
3. **Refill coordinator:** ngăn quá nhiều loaders trùng nhau; không quyết định invariant nghiệp vụ.

Một Redis refill lock không tự tạo ra:
- Global serializable transaction.
- Exactly-once increment.
- Một leader hợp lệ để đặt phòng.
- Strong freshness sau mỗi update.
- Security revocation tức thời.

Mọi endpoint phải xác định consistency contract trước khi chọn cache policy.

## 4. Kiến trúc cache-aside trong ứng dụng Java

Một thiết kế hai tầng:

~~~~mermaid
flowchart LR
    API["Java HTTP request"] --> L1[("L1: Caffeine / local")]
    L1 -->|MISS| L2[("L2: Redis")]
    L2 -->|MISS| LOAD["Refill coordination"]
    LOAD --> D[("NoSQL source")]
    D --> LOAD
    LOAD --> L2
    L2 --> L1
~~~~

- **L1:** giảm RTT và tải Redis cho từng JVM.
- **L2:** chia sẻ kết quả giữa pods.
- **Coordinator:** hạn chế loads trùng lặp.
- **NoSQL:** source authoritative.

### 4.1. Cache key phải chuẩn hóa

Một logical product có thể bị biểu diễn dưới các key khác nhau:

~~~~text
product:SKU9
Product:SKU9
product:000SKU9
~~~~

Nếu chúng thật sự cùng object nhưng không chuẩn hóa, có thể tải ba lần. Ngược lại, không được gộp những kết quả khác nhau:

~~~~text
tenant:T42:product:SKU9:locale:vi-VN:currency:VND
tenant:T42:product:SKU9:locale:en-US:currency:USD
~~~~

Cache key cần chứa các dimensions ảnh hưởng data:
- Tenant/authorization scope.
- Entity ID đã canonicalize.
- Locale/currency/price tier khi cần.
- Query/view variant.
- Schema/cache namespace version.

**Coalesce hai callers khác tenant/role dưới một shared key có thể là lỗi rò dữ liệu**, không chỉ lỗi cache.

### 4.2. Nguồn đọc khác nguồn quyết định

Cached available room có thể phục vụ UI preview. Nhưng khi confirm booking, source phải dùng conditional update/transaction phù hợp, không chỉ dựa vào cache trả “còn trống”.

## 5. Chiến lược giảm stampede

| Cơ chế | Giảm tải thế nào? | Giới hạn |
| --- | --- | --- |
| **Singleflight trong một JVM** | Chia sẻ cùng loading future theo key | Mỗi pod vẫn có thể load |
| **Distributed refill lease** | Chọn ít loaders giữa pods | Lease expire, crash/failover, waiters |
| **Stale-while-revalidate (SWR)** | Trả stale trong lúc refresh | Phải chấp nhận staleness |
| **Soft/hard TTL** | Phân biệt cần refresh và không được dùng bản cũ | Cần policy cho mỗi data class |
| **TTL jitter** | Trải thời điểm hết hạn nhiều keys | Không chữa một hot key hết hạn |
| **Refresh-ahead** | Nạp trước khi cần | Load nguồn thừa và scheduler coordination |
| **Negative caching** | Cache authoritative NOT_FOUND | Có thể che entity mới |
| **Origin admission** | Giới hạn concurrent source loads | Callers cần wait/fallback |
| **Circuit breaker** | Ngăn đổ load xuống source đang lỗi | Có thể phải fail fast |
| **Versioned cache fill** | Tránh loader cũ overwrite bản mới | Cần source version/generation |
| **L1/L2 caching** | Giảm lưu lượng tới từng tầng | Invalidation/freshness phức tạp |

Một hệ production thường cần **kết hợp** hơn một giải pháp.

## 6. Singleflight: một load, nhiều người đợi

Singleflight hay request coalescing thực hiện:

~~~~text
Request A for K ─┐
Request B for K ─┼─> inFlight[K] ─> one NoSQL read
Request C for K ─┘                      |
                                        v
                               Shared result/failure
~~~~

Thay vì ba độc lập source reads, mọi callers cùng K nhận kết quả của cùng một load.

### 6.1. Theo key, không khóa toàn bộ cache

Nếu K1 và K2 độc lập, K1 refresh không nên ngăn K2. Một global lock gây **head-of-line blocking**, có thể khiến một hot tenant làm chậm toàn bộ hệ thống.

### 6.2. In-flight map

~~~~text
inFlight:
    K1 -> CompletableFuture #101
    K2 -> CompletableFuture #102
    K3 -> CompletableFuture #103
~~~~

Nếu K1 đang tải:
- Request K1 mới join future #101.
- Request K2 không chờ K1.
- Khi K1 hoàn tất hoặc fail, entry inFlight K1 được xóa.

### 6.3. Một JVM khác vẫn có in-flight map riêng

Nếu có 100 pods:
- Local singleflight có thể giảm 10.000 loads xuống khoảng 100 trong một đợt.
- Nhưng không đảm bảo toàn cụm chỉ có một load.
- Distributed coordination hoặc L2 shared cache có thể giảm thêm.

### 6.4. Đừng để một waiter cancel công việc chung

Một request timeout không có nghĩa 99 requests khác không cần kết quả. Caller nên nhận **dependent future** hoặc một wrapper có cancellation cục bộ, không hủy shared load khi một waiter rời đi.

### 6.5. Bounded waiting vẫn quan trọng

Một load có 10.000 waiters:
- Database chỉ xử lý một read.
- Nhưng application vẫn giữ 10.000 HTTP requests/futures.
- Memory, socket count và timeout vẫn có thể quá tải.

Cần limits, deadlines, stale fallback hoặc fail fast theo contract.

## 7. Java 21: SingleFlight với CompletableFuture

Một class thuần Java minh họa per-key in-process singleflight:

~~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;
import java.util.function.Supplier;

public final class SingleFlight<K, V> {

    private final ConcurrentHashMap<K, CompletableFuture<V>> inFlight =
            new ConcurrentHashMap<>();

    public CompletionStage<V> load(
            K key,
            Supplier<? extends CompletionStage<V>> loader
    ) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(loader, "loader");

        CompletableFuture<V> flight = new CompletableFuture<>();
        CompletableFuture<V> existing =
                inFlight.putIfAbsent(key, flight);

        if (existing != null) {
            // Waiter cannot cancel the shared flight by
            // cancelling this dependent completion stage.
            return existing.thenApply(Function.identity());
        }

        try {
            CompletionStage<V> task =
                    Objects.requireNonNull(loader.get(), "loader stage");

            task.whenComplete((value, error) -> {
                try {
                    if (error != null) {
                        flight.completeExceptionally(error);
                    } else {
                        flight.complete(value);
                    }
                } finally {
                    inFlight.remove(key, flight);
                }
            });
        } catch (RuntimeException error) {
            flight.completeExceptionally(error);
            inFlight.remove(key, flight);
        }

        return flight.thenApply(Function.identity());
    }
}
~~~~

Ví dụ gọi:

~~~~java
SingleFlight<String, Product> flights = new SingleFlight<>();

CompletionStage<Product> result = flights.load(
        "tenant:T42:product:SKU9",
        () -> repository.loadProductAsync("T42", "SKU9")
);
~~~~

Các kiểu Product/repository do ứng dụng định nghĩa.

### 7.1. Khi thành công

- Caller đầu tiên tạo placeholder future và đưa vào map.
- Caller khác nhận dependent future.
- Source load hoàn thành, shared future được complete.
- Map entry bị xóa; lần load sau có thể bắt đầu.

### 7.2. Khi load thất bại

- Lỗi được gửi cho mọi waiters.
- Entry bị xóa, không giữ future lỗi mãi.
- Một đợt requests tiếp theo có thể thử load mới.

**Singleflight không tự chống vòng lặp lỗi liên tục**: cần backoff, retry budget và circuit breaker.

### 7.3. Các giới hạn của ví dụ

- Chỉ phối hợp **trong một JVM**.
- Không cache kết quả; cần cache store riêng.
- Loader phải **không block vô hạn**.
- Nếu CompletionStage không hoàn tất, inFlight key bị giữ; cần hard timeout/watchdog.
- Không giới hạn số keys đang tải; thêm semaphore/queue caps.
- Không bảo vệ cache population khỏi stale overwrite.
- Không xử lý permission/tenant scope ngoài việc caller tạo key đúng.
- Không tự hủy source read khi không còn waiters.
- Thread pool I/O, cancellation và shutdown cần production implementation.
- Không tự chuyển một result NOT_FOUND thành negative cache hợp lệ.

## 8. Kết hợp SingleFlight với cache-aside

Pseudo-flow:

~~~~text
getProduct(tenantId, sku):
    key = canonicalKey(tenantId, sku)
    cached = cache.get(key)

    if cached is fresh:
        return cached.value

    return flights.load(key, async () -> {
        again = cache.get(key) # double check
        if again is fresh:
            return again.value

        permit = originBudget.acquire(deadline)
        if no permit:
            fail or use allowed stale

        source = noSql.getProductWithVersion(tenantId, sku)
        cache.putIfCurrentVersionAllows(key, source)
        return source.value
    })
~~~~

### 8.1. Double-check sau khi thắng flight

Có thể cache đã được populate giữa lần miss đầu và lúc loader bắt đầu. Đọc lại cache giúp tránh load thừa. **Nó không đủ** để xử lý source update race sau khi read bắt đầu.

### 8.2. Tách errors khỏi NOT_FOUND

- NoSQL trả authoritative NOT_FOUND: có thể negative cache theo policy.
- NoSQL trả timeout/throttle/quorum error: **không được cache như NOT_FOUND**.
- Authorization denied: không trả cached data từ principal khác.
- Source load bị cancel: không tự kết luận entity vắng mặt.

### 8.3. Cache write có thể fail

Nếu source trả value nhưng Redis SET fail:
- Có thể trả value cho caller nếu consistency contract cho phép.
- Nhưng không hứa key đã được warm.
- Không retry SET vô hạn.
- Metrics cần source load success và cache fill failure riêng.

## 9. Caffeine trong Java: local loading và refreshing

Caffeine là thư viện Java phổ biến cho cache trong process. AsyncLoadingCache và refresh-after-write có thể giúp phối hợp loading trong một JVM.

Ví dụ minh họa:

~~~~java
import com.github.benmanes.caffeine.cache.AsyncLoadingCache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

public final class ProductLocalCache {
    private final AsyncLoadingCache<String, Optional<Product>> cache;

    public ProductLocalCache(ProductRepository repository) {
        this.cache = Caffeine.newBuilder()
                .maximumSize(20_000)
                .refreshAfterWrite(Duration.ofMinutes(3))
                .expireAfterWrite(Duration.ofMinutes(10))
                .buildAsync((key, executor) ->
                        CompletableFuture.supplyAsync(
                                () -> repository.loadOptional(key),
                                executor
                        )
                );
    }

    public CompletableFuture<Optional<Product>> get(String key) {
        return cache.get(key);
    }
}
~~~~

Các kiểu Product và ProductRepository là giả định. Cấu hình/library methods phải phù hợp với phiên bản Caffeine và operation thực tế.

### 9.1. RefreshAfterWrite không phải cron bắt buộc

Trong caching libraries, refresh may be triggered by access/maintenance theo semantics cụ thể, không nên giả định cứ đúng phút thứ ba sẽ có một scheduled refresh dù không ai đọc.

### 9.2. Vì sao dùng Optional?

Một source read có thể trả Optional.empty cho NOT_FOUND. Nhiều cache API không lưu null như một value thông thường. Optional giúp thể hiện absence, nhưng negative result nên có TTL theo policy riêng nếu có thể.

### 9.3. Blocking source call và executor

Nếu repository.loadOptional là blocking:
- Executor cần sizing/capacity.
- Không chạy một lượng lớn source reads trên event-loop.
- Timeout và circuit breaker phải được thiết lập.
- Không tạo executor mới trên mỗi read.
- Không nhầm virtual threads với giảm tải database.

### 9.4. L1 không phối hợp across pods

100 pods vẫn có thể tạo 100 loads khi L2 miss. Dùng L1 để giảm local contention, phối hợp L2/distributed origin budget nếu lượng tải cần.

## 10. Phối hợp nạp lại giữa các instances

Một shared cache Redis có thể chứa refill lease theo key:

~~~~mermaid
flowchart TD
    A["Pod A miss K"] --> L[("Redis lease K")]
    B["Pod B miss K"] --> L
    C["Pod C miss K"] --> L
    L -->|Winner| SRC["Bounded NoSQL load"]
    SRC --> SET["Version-aware cache fill"]
    SET --> L
    L -->|Losers| WAIT["Stale or bounded wait"]
    WAIT --> RETRY["Recheck Redis with jitter"]
~~~~

### 10.1. Một key, một lease namespace

~~~~text
cache:tenant:T42:product:SKU9
refill-lock:tenant:T42:product:SKU9
~~~~

Không dùng global refill lock cho mọi products và tenants.

### 10.2. Distributed lease không phải tuyệt đối singleloader

Khi:
- Holder bị pause.
- Lease hết hạn.
- Process chết.
- Redis failover.
- Network partition.

có thể có nhiều loaders. Thiết kế phải **chịu được duplicate loads** và version-safe cache population, thay vì dựa vào guarantee “chỉ có một writer” mà lease không bảo đảm dưới mọi lỗi.

### 10.3. Lock chỉ giảm duplicate source loads

Không dùng Redis cache refill lease để bảo vệ:
- Booking slot uniqueness.
- Debit/credit balance.
- Inventory decrement.
- Idempotent order creation.
- ACL modification.

Những việc đó cần authoritative conditional write, transaction, ledger hoặc quyền phân bổ được thiết kế riêng.

## 11. Redis SET NX PX và ownership token

Một lệnh minh họa:

~~~~text
SET refill-lock:product:T42:SKU9 random-token NX PX 5000
~~~~

- **NX:** chỉ set khi key chưa tồn tại.
- **PX 5000:** lease hết hạn sau 5 giây.
- **random-token:** đánh dấu lease holder, không dùng để phân loại data version.

### 11.1. Flow

~~~~text
1. GET cache.
2. Nếu miss, SET refill-lock token NX PX.
3. Nếu giành được:
     GET cache lại.
     Nếu fresh -> không cần load.
     Nếu vẫn miss -> read NoSQL với deadline.
     Populate cache có version guard.
     Release lock nếu token khớp.
4. Nếu không giành được:
     Return stale nếu policy cho phép.
     Hoặc chờ có giới hạn, GET lại với jitter.
     Hết deadline -> 503/429/pending theo contract.
~~~~

### 11.2. Vì sao không DEL vô điều kiện?

Timeline:

~~~~text
T0 A lấy lease 5s
T1 A bị GC pause 10s
T2 Lease A hết; B lấy lease mới
T3 A tỉnh lại
T4 A DEL lockKey vô điều kiện -> xóa nhầm lock B
~~~~

Giải pháp là **compare token trước khi xóa**.

~~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
~~~~

Lua script chạy atomically với Redis key trong scope được hỗ trợ.

### 11.3. Lease expiration và renew

Nếu source load có p99 vượt 5 giây:
- Lease có thể hết trước khi fill.
- Loader khác có thể bắt đầu.
- Có thể cần lease duration tương thích bounded source timeout hoặc renewal.
- Renewal chỉ khi vẫn là owner.
- Long-running load không được vô hạn giữ lease.

### 11.4. Redis failover

Lock state có thể chịu replication/failover semantics riêng; không tuyên bố Redis lock là một distributed consensus lock cho mọi fault model. Đối với cache refill, một số duplicate loads có thể được chấp nhận nếu không có business side effect và cache fill an toàn.

### 11.5. Một random token không phải fencing epoch

- Random token: so sánh ownership khi release.
- Monotonic epoch/fencing token: protected resource kiểm tra writer nào cũ hơn.
- Source version: cache biết data nào mới hơn.
- OperationId: chống duplicate business effects.

Bốn thứ không thay nhau.

## 12. Request thua lease: không đổ xuống NoSQL

Một số lựa chọn:

| Cách xử lý | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| Return stale | Data có freshness window | Staleness |
| Bounded wait for cache fill | Caller cần fresh nhưng có thời gian | Waiters/memory |
| Poll Redis with jitter | Fill đang tiến triển | Redis polling burst |
| Return 202/PENDING | Có API async semantics | Caller phải poll |
| Return 429/503 | Source quá tải/không có fresh data | Availability tạm giảm |
| Use secondary source | Read consistency được hỗ trợ | Khác freshness/cost |
| Allow second loader after timeout | Holder có thể chết | Duplicate work, risk stampede |

### 12.1. Polling không theo cùng một mốc

Nếu 10.000 waiters cùng sleep đúng 100 ms, chúng lại cùng GET Redis. Dùng bounded randomized delay hoặc backoff+jitter.

### 12.2. Hết deadline

Không để waiter tự gọi source trực tiếp khi lock chờ quá lâu, vì như vậy **xóa tác dụng của coordination**. Cần fail/return stale theo contract hoặc qua origin admission/controlled fallback.

### 12.3. Limit waiters per key

Nếu 100.000 callers chờ một future:
- Application có thể hết memory.
- Gateway timeout.
- User retries gây thêm đợt mới.

Hạn chế pending waiters, fast-fail hoặc stale serving và đo queue length.

## 13. Soft TTL, hard TTL và stale-while-revalidate

Một entry có thể có:

~~~~json
{
  "key": "product:T42:SKU9",
  "value": {"name":"Sản phẩm A","priceMinor":120000},
  "sourceVersion": 42,
  "freshUntil": "2026-11-14T09:05:00Z",
  "serveStaleUntil": "2026-11-14T09:07:00Z"
}
~~~~

### 13.1. Ba trạng thái

| Khi nào | Trạng thái | Hành vi |
| --- | --- | --- |
| Trước freshUntil | FRESH | Return ngay |
| Giữa freshUntil và serveStaleUntil | STALE_ALLOWED | Return stale và trigger **một** refresh |
| Sau serveStaleUntil | HARD_EXPIRED | Chờ fresh bounded hoặc unavailable |

### 13.2. Stale-while-revalidate

~~~~text
Request GET K
  |
  +-- Fresh -> return cached value
  |
  +-- Stale but allowed:
  |     return cached value immediately
  |     trigger ONE coordinated refresh
  |
  +-- Hard expired:
        load/join with deadline
        or fail if cannot get fresh
~~~~

### 13.3. Ưu điểm

- Hầu hết callers không chờ nguồn.
- Refresh load được coalesce.
- P99 tránh spike ngay soft expiry.
- Có thể phục vụ trong source outage ngắn.
- Giảm retry và sudden source load.

### 13.4. Đánh đổi

- Trả dữ liệu cũ có chủ đích.
- Source outage kéo dài có thể đưa stale age đến hard limit.
- Nếu refresh fail liên tục mà retry nhanh, vẫn có load storm.
- Data nhạy cảm như ACL/stock/payment không được tự bật stale.

### 13.5. Stale-if-error khác SWR

- **SWR:** trả stale trong khi refresh.
- **Stale-if-error:** trả stale khi refresh lỗi, nếu vẫn trong cửa sổ cho phép.

Một hệ có thể hỗ trợ cả hai, nhưng hard expiry không được bị nới vô hạn nếu contract cấm.

### 13.6. HTTP stale-while-revalidate không tự cấu hình cache Java

Một HTTP Cache-Control directive liên quan stale-while-revalidate có thể được CDN/proxy/browser xử lý theo chuẩn. Nó **không tự triển khai** singleflight hay refresh semantics trong Redis/Caffeine/NoSQL layer.

## 14. Khi nào có thể trả stale?

| Data class | Policy thường có thể | Ranh giới |
| --- | --- | --- |
| Product description | SWR theo age bound | Không ảnh hưởng giao dịch |
| Category metadata | TTL dài, invalidation | Schema version |
| Search facets | Eventual cache | Freshness được công bố |
| Recommendations | SWR | Không chứa dữ liệu chéo tenant |
| Price hiển thị | Tùy sản phẩm | Checkout phải reprice từ authority |
| Stock preview | Chỉ ước lượng | Reserve/confirm không dựa vào stale |
| Booking availability | Có thể để hiển thị | Không CONFIRMED từ stale |
| Wallet balance | Không dùng stale cho strong balance | Authority |
| Permission revoke | Phải có revocation bound mạnh | Không cho đặc quyền từ cached ALLOW cũ |
| Order commit status | Không kết luận từ stale | Operation ledger/source |
| User preferences | Tùy scope | Tenant/user privacy |
| Negative NOT_FOUND | TTL ngắn | Entity có thể được tạo mới |

### 14.1. Security policy cache

Nếu quyền WRITE vừa bị thu hồi nhưng local cache còn ALLOW:
- Trả ALLOW có thể là lỗi bảo mật.
- Không được “SWR mọi query” mà bỏ qua revocation.
- Có thể cần policy version, short TTL, strong revalidation hoặc fail closed.

### 14.2. Có thể dùng stale để hiển thị, không để xác nhận

Danh sách phòng có thể hiển thị “còn phòng” từ cache với nhãn cần kiểm tra, nhưng thao tác confirm phải thực hiện conditional reservation trên source.

## 15. TTL jitter: chống avalanche

Nếu 100.000 cache keys được ghi cùng thời điểm với TTL đúng 600 giây, chúng có thể hết hạn đồng loạt.

Một chính sách jitter:

\[
TTL_{\text{effective}}=TTL_{\text{base}}\times U(0{,}9;1{,}1)
\]

Nếu TTL base 600 giây, kết quả nằm khoảng 540–660 giây trong mô hình này.

### 15.1. Lợi ích

- Phân tán expiry của nhiều keys.
- Giảm wave sau deploy/cold warmup.
- Tránh quá nhiều refresh cùng lúc.

### 15.2. Không chữa một hot key

Hot SKU9 dù hết hạn lúc 540 hay 660 giây vẫn có thể bị 12.000 requests/s tấn công đúng lúc đó. Cần singleflight/SWR.

### 15.3. Freshness hard cap

Nếu dữ liệu không được quá 600 giây tuổi:
- Không thể dùng jitter lên 660 giây nếu nó vi phạm contract.
- Dùng jitter trong [540,600] hoặc soft TTL random/hard age cố định.

### 15.4. Phân bổ jitter theo batch và tenant

Nếu một bulk load ghi nhiều keys của cùng tenant/hot partition, cần coi nguồn và failure domain chung. Jitter giúp trải thời gian nhưng có thể vẫn còn hot partition.

## 16. Proactive refresh và refresh-ahead

Một hướng khác: **nạp trước khi key hết hạn**, thường cho hot keys có lưu lượng dự đoán được.

~~~~text
Popular key age approaches soft TTL
  -> enqueue refresh if no active job
  -> rate-limited source read
  -> version-aware cache fill
  -> keep serving old within policy
~~~~

### 16.1. Ưu điểm

- Giảm first-miss latency.
- Dễ giữ hot keys sẵn sàng.
- Tránh source burst tại hard expiry.
- Có thể warm cache sau region failover.

### 16.2. Chi phí

- Refresh có thể xảy ra dù không có ai đọc.
- Nhiều keys cold bị đọc thừa.
- Scheduler/queue cần budget.
- Source index/compaction pressure có thể tăng.
- Refresh đồng bộ giữa pods vẫn là stampede.

### 16.3. Sai lầm cron trên mọi pod

Nếu 100 pods cùng cron refresh mỗi 5 phút:
- 100 requests vẫn đổ tới source.
- Các pods đồng bộ về thời gian.
- Có thể làm p99 dao động đều theo lịch.

Dùng leader per shard, work queue dedup, distributed lease hoặc stagger/jitter theo policy.

### 16.4. Prewarming không có nghĩa load toàn bộ dataset

Chọn top hot keys, đặt concurrency/rate budget, ưu tiên critical endpoints và dừng nếu origin saturation. Nạp hàng triệu cold keys sau restart có thể gây avalanche chủ động.

## 17. Negative caching và cache penetration

Một request hỏi key không tồn tại:

~~~~text
GET product:unknown-id
  -> cache MISS
  -> NoSQL NOT_FOUND
~~~~

Nếu bot hỏi lại cùng key, mỗi lần đều chạm NoSQL. **Negative caching** lưu authoritative absence có TTL ngắn:

~~~~json
{
  "key": "product:T42:unknown",
  "resultType": "NOT_FOUND",
  "ttlSeconds": 20
}
~~~~

### 17.1. Chỉ cache NOT_FOUND khi nguồn xác nhận

Không biến:
- 503.
- Timeout.
- Auth/permission denied.
- Throttle.
- No quorum.

thành NOT_FOUND. Đây là những lỗi, không phải bằng chứng entity không tồn tại.

### 17.2. TTL negative ngắn

Nếu item được tạo ngay sau kết quả NOT_FOUND, negative cache dài có thể che item mới. Dùng TTL ngắn hoặc invalidation on create, theo business requirement.

### 17.3. Scope của negative cache

Nếu item 42 không tồn tại ở tenant A nhưng có ở tenant B, negative key phải tenant-aware. Không dùng một global NOT_FOUND cache che dữ liệu hợp lệ của tenant khác.

### 17.4. Bloom filter

Bloom filter cho tập keys hiện có có thể giúp tránh một phần reads không cần thiết:
- Một filter hợp lệ có thể có **false positives**, đưa key không tồn tại đi qua tới database.
- Trong mô hình tập không đổi và cập nhật đúng, filter không có false negatives.
- Nhưng nếu filter bị stale sau khi thêm key mới, hệ có thể **bỏ nhầm key mới** nếu tin filter như authority.

Không dùng một filter không được cập nhật làm bằng chứng vĩnh viễn key vắng mặt.

## 18. Cache refill race và stale overwrite

Một lỗi subtle:

~~~~text
T0 A miss; bắt đầu đọc NoSQL v7, response chậm.
T1 B cập nhật NoSQL lên v8.
T2 B invalidate cache.
T3 A nhận dữ liệu v7.
T4 A SET cache=v7 với TTL 10 phút.
~~~~

**Singleflight không ngăn lỗi này. Redis lease cũng không.** Cần phối hợp giữa source updates và cache population.

### 18.1. DELETE cache không đủ

DELETE chỉ xóa giá trị hiện có. Nó **không chặn một loader đang chạy** tới sau và SET dữ liệu cũ.

### 18.2. Versioned envelope

~~~~json
{
  "value": {"sku":"SKU9","priceMinor":120000},
  "sourceVersion": 8,
  "cachedAt": "2026-11-14T09:00:00Z"
}
~~~~

Có thể yêu cầu:

~~~~text
if candidate.sourceVersion < currentAllowedVersion:
    reject cache fill
else:
    store candidate
~~~~

### 18.3. Watermark/generation marker

Cần chú ý:
- Nếu B đã invalidate v8 bằng DELETE, entry v8 không còn để so.
- A đến với v7 có thể ghi lại.

Vì vậy cần một **invalidation fence/watermark** hoặc mechanism tương đương giữ thông tin “ít nhất v8 đã tồn tại”, đủ lâu để stale loads không hồi sinh v7.

### 18.4. Atomic compare

Nếu nhiều loaders cùng fill, compare version và SET phải atomic trong shared cache store để tránh write race.

### 18.5. Marker cũng có TTL

Fencing marker không được GC trước khi những source loads cũ có thể hoàn tất, theo bounds của hệ. Nếu loaders có thể chạy vô hạn, khó chọn retention an toàn; **hard timeout** cho source loads là thành phần của giải pháp.

### 18.6. Khi invalidation event đến chậm

Một version marker có thể vẫn chưa tới Redis khi source commit v8. Dưới eventual invalidation, stale reads vẫn có thể xuất hiện. Nếu API yêu cầu strong read:
- Bypass cache.
- Hoặc xác minh version với source/read barrier theo contract.
- Không suy rằng event bus luôn giao ngay.

### 18.7. Version từ source authority

Không dùng client wall-clock timestamp làm sourceVersion nếu clock skew/concurrent writes. Có thể dùng aggregate version, commit sequence hoặc opaque generation từ authority phù hợp.

Nếu hai regions độc lập cùng version=8 với nội dung khác, so integer không giải quyết causal conflict; cần một authority hoặc versioning model khác.

## 19. Write-side invalidation và write-through

### 19.1. Cache-aside write

Một pattern phổ biến:

~~~~text
Update NoSQL source
    -> invalidate cached key
    -> future reads refill
~~~~

Đơn giản nhưng có race với in-flight read. Cần version fence hoặc chính sách phù hợp.

### 19.2. Write-through

Application cập nhật nguồn và cache:
- Có thể giảm miss sau write.
- Nhưng hai writes khác hệ không tự atomic.
- Source commit và cache write fail phải có reconciliation.
- Cache write đến sai thứ tự có thể đưa state đi lùi.

Không tự coi “có write-through” là không cần versioning.

### 19.3. Write-behind/write-back

Cache chấp nhận write trước và đẩy xuống database sau:
- Có thể nhanh.
- Nhưng mất durability/ordering khi cache crash.
- Cần dedup/replay.
- Rủi ro lớn cho booking, balance, payment.

Stampede mitigation không giúp tự biến write-behind thành transaction an toàn.

### 19.4. Event-driven invalidation

Outbox/CDC có thể mang:
- TenantId/aggregateId.
- SourceVersion.
- EventId.
- OperationId.
- Change type.

Consumers phải xử lý duplicate/out-of-order và backlog. Event arrival order không tự là source commit order.

## 20. Origin protection: nhiều keys cùng miss

Per-key singleflight bảo vệ một key. Nhưng khi 50.000 keys khác nhau miss, vẫn có thể có 50.000 source loads.

### 20.1. Global/cell semaphore

Ví dụ:

~~~~text
Max concurrent origin cache fills per cell = 200
~~~~

Khi hơn 200 keys đang load:
- Còn lại chờ trong bounded queue.
- Serve stale nếu cho phép.
- Fail fast khi quá deadline.
- Không tạo vô hạn tasks.

### 20.2. Per-tenant budget

Tenant lớn có thể chiếm hết refill slots, gây noisy neighbor. Cần cân nhắc quota/fairness theo tenant tier, shard/cell và workload class.

### 20.3. Circuit breaker

Khi source lỗi:
- Ngưng phần lớn new load attempts.
- Half-open probe hạn chế khi hồi phục.
- Không để mọi miss retry mù.
- Scope breaker đúng failure domain, tránh sự cố một shard chặn mọi shard.

### 20.4. Retry budget

Singleflight có thể giúp một wave chỉ một loader, nhưng nếu load fail rồi ngay lập tức wave mới xuất hiện, DB vẫn bị gọi liên tục. Dùng:
- Bounded attempts.
- Backoff+jitter.
- Total deadline.
- Origin retry tokens.
- Error classification.
- Admission control.

### 20.5. Background tasks dùng budget riêng

Prewarm, compaction-triggered refresh, bulk reindex và analytics không nên chiếm mọi pool slots cần cho interactive reads.

## 21. Timeout và caller cancellation

Một request có thể đi qua:

~~~~text
Gateway deadline 1500 ms
  -> Redis GET
  -> Refill lock acquisition
  -> Wait on flight
  -> NoSQL read
  -> Cache SET
  -> Respond
~~~~

Nếu mỗi tầng tự cho timeout 1000 ms, tổng có thể vượt gateway deadline rất xa.

### 21.1. End-to-end deadline

\[
B_{\text{remaining}}=T_{\text{deadline}}-T_{\text{now}}
\]

Mỗi bước chỉ bắt đầu nếu còn budget. Đo elapsed trong JVM với System.nanoTime thay vì wall-clock khi phù hợp.

### 21.2. Cancellation của một waiter

Một waiter timeout không nhất thiết hủy shared load. Nhưng nếu toàn bộ waiters đã biến mất, loader cũng cần một policy để tránh tiêu source work vô ích; có thể vẫn muốn populate cache nếu việc tải gần hoàn tất.

### 21.3. Hard timeout cho loader

Nếu Future không bao giờ complete, per-key inFlight sẽ không được dọn. Cần:
- Underlying NoSQL read timeout thực sự được thực thi.
- Watchdog/hard deadline.
- Cleanup inFlight.
- Metrics stalled flights.
- Bounded concurrent source loads.

Không chỉ cho caller timeout mà bỏ source load chạy mãi.

## 22. Java: biểu diễn freshness windows

Một entry local có thể mang:

~~~~java
public record CachedValue<V>(
        V value,
        long sourceVersion,
        long freshUntilNanos,
        long serveStaleUntilNanos
) {
    public boolean isFresh(long now) {
        return now - freshUntilNanos < 0;
    }

    public boolean mayServeStale(long now) {
        return now - freshUntilNanos >= 0
                && now - serveStaleUntilNanos < 0;
    }
}
~~~~

**Lưu ý:**
- System.nanoTime phù hợp elapsed time trong cùng JVM.
- Không serialize deadline nanoTime giữa machines/restarts.
- sourceVersion phải đến từ data authority, không lấy nanoTime làm version.
- Record chỉ mô tả state, chưa giải quyết atomic cache replacement.
- Freshness policy phải theo data class.

### 22.1. Luồng SWR

~~~~text
entry = localCache.get(key)
now = monotonicNow()

if entry fresh:
    return entry.value

if entry staleAllowed:
    refreshCoordinator.triggerIfAbsent(key)
    return response(entry.value, stale=true)

return refreshCoordinator.loadOrJoin(key, callerDeadline)
~~~~

Nếu refresh fail:
- Giữ stale trong cửa sổ cho phép.
- Backoff trước refresh tiếp.
- Không cache failure như NOT_FOUND.
- Sau hard expiry phải theo policy unavailable/force fresh.

## 23. Multi-tier coordination: L1 Caffeine, L2 Redis

### 23.1. Những đợt miss khác nhau

- Một pod có 100 concurrent threads cùng miss L1.
- 100 pods cùng miss L2.
- Redis node failover, tất cả requests tới L2 bị timeout.
- 100 pods đồng loạt invalidate L1 theo event.
- Region mới nhận traffic, cả L1/L2 cold.

Mỗi tầng cần metrics và phương án bảo vệ.

### 23.2. L1 có thể che outage ngắn của L2

Nếu L1 có entry stale được phép:
- Trả giá trị theo SWR contract.
- Không cho mỗi request bypass xuống NoSQL.
- Dùng bounded retry/backoff ở tầng L2.
- Hết hard age cap thì fail nếu không lấy được fresh.

### 23.3. L1 invalidation

Pub/Sub invalidation có thể bị mất khi pod tạm disconnect. Cần cân nhắc:
- Short local TTL.
- Version check.
- Replayable changelog nếu cần.
- Session minVersion.
- Periodic reconciliation.

Không hứa strong consistency chỉ từ event invalidation best-effort.

### 23.4. Avoid cache poisoning across scopes

Một shared future/cache value cho tenant A không được trả cho tenant B. Cache key hoặc ACL checks phải bảo vệ scope. Cùng với dữ liệu nhạy cảm, không lưu raw keys/values vào metrics rộng rãi.

## 24. Hot key và hot partition

Một product metadata hot key có thể cache rất tốt. Nhưng tồn kho của cùng SKU có thể là một mutable authoritative state.

### 24.1. Không tăng TTL bừa cho stock

- Display có thể chấp nhận approximation.
- Reserve/checkout cần source conditional authority.
- Cached “in stock” không phải bằng chứng đủ để confirm đơn.

### 24.2. Không tự sharding một key bảo vệ invariant

Nếu quota hoặc booking slot là một atomic key, tách nó thành nhiều keys chỉ để giảm load có thể làm mất invariant. Phải dùng mô hình distributed allocation/escrow hoặc authority chuyên biệt nếu cần.

### 24.3. Memory eviction

Nếu cache bị memory pressure:
- Hot key bị evict trước TTL.
- Stampede lặp dù TTL dài.
- Cần đo eviction reasons, memory footprint, entry sizes và policies.

## 25. Security và data classification

Không phải cache nào cũng được chứa mọi dữ liệu.

| Rủi ro | Biện pháp |
| --- | --- |
| Cross-tenant value leak | Tenant-aware key và authz |
| User permission leak | Cache scope theo policy/version, không stale ALLOW trái revocation |
| PII retention quá lâu | TTL/erase/invalidation/backup policy |
| Secret trong cache | Tránh lưu secrets không cần thiết; encrypt/access controls nếu thật sự phải có |
| Cached NOT_FOUND chéo tenant | Negative keys có tenant scope |
| Cache key trong logs | Redaction hoặc hash có policy |
| Redis traffic không mã hóa | TLS/auth/network ACL |
| Poisoned refill value | Validate source/serializer/version |
| Replay invalidation cũ | Event version guard/dedup |
| Service principal có quyền quá rộng | Least privilege cho Redis/NoSQL |

**Cache miss coordination không được làm mất ranh giới authorization.**

## 26. Cache outage và cold start

### 26.1. Redis unavailable

Nếu Redis L2 mất:
- L1 có thể giúp một số keys.
- Những keys không có L1 có thể đổ xuống NoSQL.
- Không cho fallback trực tiếp không giới hạn.
- Dùng origin semaphore, circuit breaker và stale policy.
- Trả unavailable khi data class không cho stale.

### 26.2. Cold start nhiều pods

Autoscaling thêm 100 pods:
- Mỗi pod L1 trống.
- Các pods cùng load top hot keys.
- L2 shared giảm origin loads.
- Nhưng L2 vẫn chịu burst; nên đo hit ratio theo pod age và warm theo jitter.

### 26.3. Namespace migration

Một release đổi key prefix v3→v4:
- V4 hoàn toàn cold.
- Mọi requests có thể miss dù cache v3 còn đầy.

Cần canary, rate-limited prewarm, staged rollout và khả năng dual-read được thiết kế đúng schema/freshness, không chuyển namespace toàn bộ cùng một thời điểm.

### 26.4. Region failover

Region B nhận lưu lượng của A khi NoSQL đang replay/repair:
- Cache B có thể cold.
- Source B đang giảm capacity.
- Nếu stampede xảy ra, RTO bị kéo dài.

Cache warming phải nằm trong **disaster recovery/capacity plan**, không chỉ được coi là performance optimization.

## 27. Tính capacity trong một hệ 100 pods

Giả sử:
- 100 pods.
- Mỗi pod phục vụ 2.000 req/s.
- 20% traffic nhắm vào một product key.
- Source read latency 200 ms.

Hot-key traffic:

\[
100\times2.000\times0,2=40.000\text{ req/s}
\]

Nếu key mất cache và mọi request tự load trong 0,2 giây:

\[
40.000\times0,2=8.000
\]

Có thể có xấp xỉ 8.000 concurrent source requests trong mô hình lý tưởng.

### 27.1. Local singleflight

Nếu mỗi pod load tối đa một lần:
- Khoảng 100 source requests vẫn có thể xảy ra.
- Đây là cải thiện lớn, nhưng một source hot partition có thể vẫn bị áp lực.

### 27.2. Distributed refill

Nếu toàn cụm chỉ có một owner:
- Nỗ lực giảm source load tới gần một lần.
- Nhưng lease expiry/failover có thể sinh duplicate loads.
- 40.000 req/s callers vẫn cần chờ/trả stale/fail.
- Không được giữ hàng trăm nghìn waiters vô hạn.

### 27.3. 50.000 keys cùng miss

Kể cả một load mỗi key vẫn là 50.000 source loads. Cần origin global/cell budget, jitter và queueing có giới hạn.

### 27.4. Không hiểu sai benchmark

Một hệ có source requests thấp nhất nhưng trả stale quá hạn hoặc lộ tenant data **không thể coi là thắng**. Đo hiệu năng và correctness cùng nhau.

## 28. Observability

| Chỉ số | Câu hỏi |
| --- | --- |
| L1/L2 hit ratio | Miss ở tầng nào? |
| Miss rate by short time window | Có burst 100 ms/1 s? |
| Distinct missed keys | Một hot key hay nhiều keys? |
| Origin loads started | Bao nhiêu read thật sự đến NoSQL? |
| Coalesced waiters | Bao nhiêu callers chia shared future? |
| In-flight keys | Có bao nhiêu loads đang chạy? |
| Waiters per key max/p95 | Memory/queue có căng? |
| Refill lease acquisition failures | Có contention? |
| Lease expired while loading | Timeout lease có đúng? |
| Source p50/p95/p99 | Database chịu tác động gì? |
| Connection pool wait time | Có exhaustion? |
| Cache TTL expiration vs eviction | Vì sao mất entry? |
| Refresh failures | Source/loader có lỗi? |
| Stale age p95/max | Có vượt policy? |
| Negative cache hits | Có penetration? |
| Source-version rejected fills | Có chặn stale overwrite? |
| Invalidation lag | Event đến cache chậm bao lâu? |
| Retry amplification | Có storm? |
| Circuit breaker state | Source có được bảo vệ? |
| User response p99/error/deadline | UX/SLO thực? |
| Booking/permission anomalies | Cache có phá invariant không? |

### 28.1. Cache load amplification

Một metric:

\[
A=\frac{\text{Origin load attempts}}{\text{Logical cache miss requests}}
\]

Nếu 10.000 requests miss một key và chỉ một origin load: \(A=0,0001\). Nếu 10.000 loads: \(A=1\).

Cần định nghĩa window, loại cache miss, retries và multi-tier behavior rõ. Đừng so con số A giữa hai hệ với định nghĩa khác nhau.

### 28.2. High-cardinality metrics

Không đưa mọi raw cache key/userId/operationId thành time-series label. Dùng:
- Tenant tier/cell/region.
- Key class.
- Histogram cho waiters.
- Top-N hot keys theo sampling/on-demand diagnostics.
- Logs/traces được bảo vệ cho chi tiết.

### 28.3. Hit ratio chưa đủ

Một hệ có hit rate 99% nhưng mọi misses xảy ra cùng 100 ms vẫn có thể có database outage. Theo dõi short-window peak và load queue.

## 29. Fault injection cho cache stampede

| Kịch bản | Cách mô phỏng | Điều mong đợi |
| --- | --- | --- |
| Hot key expiry | Warm K rồi hết TTL khi 10.000 concurrent callers | Loads trùng được coalesce |
| Mass expiry | Warm 100.000 keys cùng TTL | Jitter giảm peak |
| Redis restart | L2 unavailable | Origin admission, không flood |
| Holder crash | Kill process giữ lease | Lease hết, loaders mới tiến triển |
| Lease expires early | Pause holder > lease TTL | Không xóa nhầm lease holder khác |
| Source slow query | Tăng latency từ 60 ms lên 3 s | Bounded waiters/timeouts |
| In-flight never completes | Loader hung | Watchdog cleanup |
| Stale overwrite race | A đọc v7, B update v8, A SET v7 | Version fence chặn stale fill |
| Lost invalidation | Drop event update v8 | Cảnh báo lag, freshness policy |
| Read-after-write | Client yêu cầu >=v8 | Không trả v7 dưới strong/session contract |
| Negative cache after create | NOT_FOUND rồi item được tạo | TTL/invalidation tránh che lâu |
| Cache namespace migration | v3→v4 trên 100 pods | Gradual warmup |
| Hot tenant burst | Một tenant chiếm miss traffic | Other tenants được bảo vệ |
| Permission revoke | Cache còn ALLOW | Không cho privileged action sai |
| DB no quorum | Source unavailable | Fail/backoff, không xác nhận booking stale |
| Network partition Redis | Lease replication/failover | Duplicate loaders có thể xảy ra nhưng data đúng |
| CDC backlog | Invalidation trễ 30 s | Freshness SLO được đo/vi phạm được phát hiện |
| Retry storm | API retries synchronized | Jitter/budget giảm amplification |

### 29.1. Pass/fail về tính đúng

- Không trả dữ liệu chéo tenant.
- Không xác nhận booking từ stale availability.
- Không dùng NOT_FOUND khi source timeout.
- Không ghi cache version nhỏ hơn watermark đã biết.
- Không vượt hard stale age policy.
- Không mất ability refresh sau loader failure.
- Không xóa lease holder mới bằng token cũ.

### 29.2. Pass/fail hiệu năng

- Origin QPS peak dưới ngưỡng thử nghiệm.
- Source pool waiters không tăng vô hạn.
- Per-key flight counts đúng kỳ vọng.
- API deadline misses dưới SLO hoặc fail fast rõ.
- Recovery time đạt mục tiêu.
- Không có unexpected retry amplification.

### 29.3. Test kịch bản lỗi tương quan

Một random 1% miss không đại diện hiện tượng cache toàn cụm down. Cần test:
- 100 pods cùng cold.
- 10.000 callers cùng một key.
- 100.000 keys cùng hết hạn.
- Một region mất và traffic chuyển vùng.
- Source chậm đúng lúc cache mất.

## 30. Benchmark cấu hình minh họa

~~~~yaml
experiment: cache-stampede-nosql
application:
  javaVersion: 21
  pods: 100
cache:
  l1: caffeine
  l2: redis
source:
  type: nosql
workload:
  logicalRps: 40000
  hotKeySharePercent: 80
  distribution: zipfian
policies:
  - naive_cache_aside
  - local_singleflight
  - distributed_refill_lease
  - stale_while_revalidate
  - ttl_jitter
  - all_with_origin_budget
faults:
  - hot_key_expiry
  - mass_ttl_expiry
  - redis_restart
  - stale_fill_after_invalidation
  - source_slowdown
  - lease_holder_crash
  - deployment_cold_start
measure:
  - origin_attempts_per_second
  - unique_origin_loads_per_key
  - coalesced_waiters
  - lock_contention
  - p50_p95_p99_end_to_end
  - connection_pool_waits
  - stale_age
  - rejected_stale_fills
  - source_error_rate
  - recovery_duration
~~~~

Đây là một **đặc tả thí nghiệm**, không phải cấu hình native của Caffeine/Redis/NoSQL.

### 30.1. Bảng kết quả giả định

| Policy | Peak loads K | p99 trong miss spike | Ghi chú |
| --- | ---: | --- | --- |
| Naive cache-aside | 5.000 | Rất cao/timeout | Stampede |
| Local singleflight 100 pods | Khoảng 100 | Còn chờ source | Không coalesce across pods |
| Distributed refill lease | Gần 1–vài | Waiters vẫn phải quản lý | Lease/failover |
| SWR | Gần 1–vài refresh | Thấp cho data stale-allowed | Staleness |
| TTL jitter | Vẫn có burst một hot key | Cải thiện mass expiry | Không thay singleflight |
| Full combination | Bounded | Phụ thuộc load/SLO | Phải test correctness |

Các số trong bảng **chỉ minh họa**, không phải benchmark thực tế hay bảo đảm của thư viện.

## 31. Runbook khi stampede đang xảy ra

### Bước 1 — Nhận diện

- User QPS có thật sự tăng không?
- Cache miss spike bắt đầu lúc nào?
- TTL, eviction, invalidation, deployment hay Redis restart?
- Một hot key hay nhiều keys?
- NoSQL p99 và connection pool có tăng?
- Có nested retry storm?

### Bước 2 — Phân loại

- Single hot key → stampede.
- Mass keys → avalanche.
- Unknown IDs → penetration.
- Source slow → waiters tích tụ.
- Redis outage → origin fallback.
- Version race → stale data corruption.

### Bước 3 — Bảo vệ source

- Bật/siết origin concurrency limit.
- Rate limit hot tenant/key.
- Circuit breaker theo shard/cell.
- Giảm background refresh/prewarm.
- SWR cho data được phép.
- Fail fast cho strong-read endpoints không có fresh source.
- Không tăng pool size vô hạn.

### Bước 4 — Kiểm tra coordinator

- InFlight map có entry per key và dọn sau failure?
- Có hard timeout không?
- Có bounded waiters không?
- Distributed lease TTL đủ so source p99?
- Release có compare ownership token?
- Losers có poll bằng jitter?
- Có fallback gọi thẳng NoSQL bỏ qua coordinator không?

### Bước 5 — Kiểm tra freshness

- SourceVersion có đi qua cache envelope?
- Watermark/invalidation fence có sống đủ lâu?
- Có A-read-v7/B-update-v8 race?
- CDC invalidation có lag?
- Strong reads có bypass/check version?
- Negative cache có che keys mới?

### Bước 6 — Phục hồi từ từ

- Warm top hot keys có budget.
- Stagger refresh/deploy.
- Monitor origin p99 và database health.
- Tăng gradual traffic thay vì bật mọi waiters đồng loạt.
- Xác nhận stale age không vượt hard bound.
- Giữ interactive workload ưu tiên.

### Bước 7 — Hậu kiểm

- Origin amplification về bình thường?
- Miss rate/hit ratio theo tầng được phục hồi?
- Có stale overwrite hoặc leak cross-tenant?
- SLO p99 và error budget đạt chưa?
- Cache memory/eviction có ổn định?
- Có postmortem về TTL, burst, capacity, invalidation, retry?

## 32. Những hiểu nhầm dễ gây lỗi

1. **“TTL dài là hết stampede.”** Eviction/invalidation vẫn xảy ra.
2. **“TTL jitter chữa một hot key.”** Chỉ phân tán thời điểm, không giảm lượng concurrent miss của key.
3. **“Singleflight trên một pod là toàn cluster chỉ một load.”** Mỗi pod có map riêng.
4. **“Distributed refill lock là transaction lock.”** Không đủ bảo vệ booking/payment.
5. **“SET NX không cần TTL.”** Process crash có thể khóa mãi.
6. **“TTL lock cho phép DEL vô điều kiện.”** Có thể xóa lease của holder mới.
7. **“Random lock token là fencing token.”** Không có thứ tự monotonic.
8. **“Lease 5 giây chắc chắn load xong trong 5 giây.”** GC/network có thể pause.
9. **“Redis failover không ảnh hưởng lock.”** Phải hiểu fault model.
10. **“Một loader thì không thể ghi cache stale.”** Source update race vẫn tồn tại.
11. **“DELETE cache sau update là đủ.”** Loader cũ có thể ghi lại.
12. **“Chỉ so version với existing cache value đủ.”** DELETE có thể xóa watermark.
13. **“Client timestamp luôn là source version.”** Clock skew/concurrency.
14. **“CDC event đến ngay sau commit.”** Có lag và reorder.
15. **“Cache hit nghĩa state mới nhất.”** TTL/async invalidation có thể stale.
16. **“SWR dùng được cho mọi dữ liệu.”** ACL/balance/booking có bất biến khác.
17. **“Stale-if-error nghĩa trả mãi tới khi DB khỏe.”** Hard age cap cần được giữ.
18. **“HTTP SWR directive tự cấu hình Caffeine.”** Tầng khác.
19. **“Cache miss là database failure.”** Miss bình thường; stampede là load amplification.
20. **“Timeout tương đương NOT_FOUND.”** Không được negative cache lỗi.
21. **“Negative TTL càng dài càng tốt.”** Có thể che item mới.
22. **“Bloom filter luôn đúng khi tập dữ liệu thay đổi.”** Filter stale có thể bỏ nhầm key mới.
23. **“Một waiter cancel thì hủy shared future.”** Còn người khác cần load.
24. **“Coalescing xóa chi phí memory của waiters.”** HTTP/futures vẫn tồn tại.
25. **“Một loader mỗi key nghĩa NoSQL an toàn.”** Nhiều keys cùng miss vẫn avalanche.
26. **“Global lock làm hệ an toàn hơn.”** Head-of-line blocking và blast radius.
27. **“Shared cache key không cần tenant.”** Có nguy cơ lộ dữ liệu.
28. **“Caffeine refresh chạy đúng lịch như cron.”** Refresh trigger theo semantics thư viện.
29. **“Virtual threads loại bỏ source overload.”** Không giảm QPS database.
30. **“Refresh job trên mọi pod là proactive refresh tốt.”** Tạo scheduled herd.
31. **“Prewarm toàn dataset luôn hữu ích.”** Có thể tự tạo source outage.
32. **“Trả stale lúc nguồn lỗi luôn hơn 503.”** Có trường hợp sai business/security.
33. **“Coalescing đảm bảo read-after-write.”** Không có version/session guard.
34. **“Cache-aside write và invalidate là ACID transaction.”** Hai hệ có partial failure.
35. **“Write-behind mặc định an toàn cho payment.”** Không.
36. **“Cache hit ratio 99,9% chứng minh không burst.”** Cần short-window metrics.
37. **“Redis chậm thì bypass toàn bộ xuống DB.”** Có thể tạo avalanche.
38. **“Tăng worker threads sẽ xử lý miss nhanh.”** Có thể làm nguồn quá tải.
39. **“Khi waiter timeout nên tự load DB.”** Phá coordinator.
40. **“Retry liên tục sau source lỗi sẽ sớm hồi phục.”** Tạo retry storm.
41. **“Một circuit breaker global đủ mọi shards.”** Có thể lan lỗi một shard.
42. **“Stale availability đủ để confirm booking.”** Source conditional authority mới quyết định.
43. **“Một version integer tự giải quyết multi-leader conflict.”** Có thể hai phiên bản concurrent cùng số.
44. **“Cache key raw có thể đưa vào mọi metric label.”** Cardinality/PII risks.
45. **“Chỉ test happy path là đủ.”** Cần crash, lease expiry, stale fill, cold-start, partition.
46. **“Giảm origin QPS nghĩa system đã đúng.”** Cần correctness/freshness/security.

## 33. Bài tập: thiết kế chống stampede cho SaaS đặt chỗ

Một hệ có:
- Java 21 + Spring Boot.
- 100 pods.
- Redis L2, Caffeine L1.
- NoSQL source lưu Product, Inventory và Booking.
- Peak 40.000 product reads/s.
- 80% traffic đổ vào một SKU nổi bật.
- Source read bình thường 60 ms, khi overload 500 ms.
- TTL product 10 phút.
- Search index eventual.
- Một booking slot chỉ được CONFIRMED cho một người.
- Một region có thể failover, một release có thể làm cache cold.

### Phần A — Tính stampede

1. Tính hot-key RPS.
2. Nếu mọi request miss trong 500 ms, ước lượng source attempts đồng thời theo mô hình đơn giản.
3. Nếu áp local singleflight lên 100 pods, giảm xuống khoảng bao nhiêu?
4. Vì sao vẫn cần origin concurrency budget?
5. Hit rate theo giờ có thể che incident thế nào?

**Gợi ý:** Hot traffic = 40.000 × 80% = 32.000 req/s; trong 0,5 s có thể xuất hiện khoảng 16.000 source load attempts nếu không giới hạn.

### Phần B — Singleflight

Thiết kế:
- Canonical key theo tenant/SKU.
- InFlight map.
- Shared/dependent futures.
- Double-check cache.
- Bounded source load.
- Hard timeout.
- Failed flight cleanup.
- Bounded waiters.
- Metrics active flights/coalesced callers.

Tại sao in-process singleflight chưa bảo vệ toàn cluster?

### Phần C — Redis refill lease

1. Tạo lock key theo product.
2. SET NX PX với random token.
3. Double-check cache sau khi thắng.
4. Read source với deadline.
5. Populate version-aware.
6. Release bằng Lua compare-and-delete.
7. Losers dùng stale hoặc bounded poll+jitter.
8. Mô tả holder A pause lâu hơn lease, B lấy lease, A tỉnh.
9. Vì sao không dùng lease này để confirm room reservation?

### Phần D — SWR

Giả sử soft TTL 2 phút, hard TTL 5 phút:
- Request tại phút 1?
- Phút 3 khi DB khỏe?
- Phút 4 khi DB tạm lỗi?
- Phút 6 khi DB vẫn lỗi?
- Khi data là ACL revoke, có được dùng stale không?

### Phần E — TTL jitter

100.000 keys được warm cùng lúc, TTL 600 s:
- Không jitter xảy ra gì?
- Jitter 540–660 trải miss thế nào?
- Nếu max stale age=600 s, chọn jitter thế nào?
- Vì sao hot SKU vẫn cần singleflight?

### Phần F — Stale overwrite

Timeline:
- A load v7 chậm.
- B update v8 và invalidate.
- A SET v7.

1. Tại sao chỉ DELETE không đủ?
2. Thiết kế sourceVersion/fence.
3. Watermark giữ bao lâu?
4. Nếu CDC invalidation đến chậm, strong read phải làm gì?
5. Nếu multi-leader có hai v8 concurrent, số version có đủ không?

### Phần G — Negative caching

Một bot hỏi hàng triệu keys không tồn tại:
- Khi nào NOT_FOUND là authoritative?
- Negative TTL bao lâu?
- Có cache 503 thành NOT_FOUND không?
- Bloom filter có false positives không?
- Filter chưa cập nhật sau create nguy hiểm gì?
- Tenant scope trong key?

### Phần H — Booking và stock

1. Cached availability có được dùng để xác nhận không?
2. Source conditional write bảo vệ gì?
3. Refill lease khác business transaction thế nào?
4. Timeout sau commit vì mất ACK giải quyết với operationId ra sao?
5. Sau source commit, phải invalidate/refresh cache thế nào?

### Phần I — Multi-tier failure

1. Redis down, L1 còn stale trong hard age thì xử lý thế nào?
2. Nếu L1 cũng miss, làm gì để không flood NoSQL?
3. Sau namespace v3→v4, nên warm key ra sao?
4. Một tenant lớn chiếm refill permits thì sao?
5. Region B cold cache nhận traffic từ A: tác động RTO?

### Phần J — Fault injection

Thiết kế test:
1. Hot key TTL expire.
2. Mass keys expire.
3. Lease holder crash.
4. Lease expires while loader running.
5. A load v7, B update v8.
6. Redis failover.
7. NoSQL read timeout.
8. Stalled CompletableFuture.
9. Negative cache after create.
10. 100 pods cold-start.
11. Permission revoked but L1 still ALLOW.
12. Cache key thiếu tenant.
13. Invalidation lag 30 s.
14. Database no-quorum.
15. Caller cancel trong lúc đang join shared future.

Mỗi kịch bản cần expected origin load, waiter behavior, freshness policy, correctness invariant và pass/fail metrics.

### Phần K — Phản biện

Một đồng nghiệp đề xuất:

> “Tăng TTL lên một ngày là xong. Cache miss thì cứ mỗi request tự query source; global lock sẽ ngăn tranh chấp. Nếu lock hết hạn thì DEL cho sạch. Redis down thì bypass tất cả xuống NoSQL. Bất kể dữ liệu gì, cứ trả stale cho đỡ 503.”

Phản biện dựa trên:
- Stampede vs avalanche.
- Freshness max age.
- Per-key coordination.
- Token ownership và lease expiry.
- Source admission/circuit breaker.
- Stale policy theo domain.
- Cache refill version race.
- Security/booking invariants.
- Recovery benchmarking.

### Hướng giải

Một thiết kế hợp lý dùng:
- L1 Caffeine với loading/coalescing theo JVM.
- L2 Redis shared.
- Per-key singleflight/lease, không xem lock là business authority.
- SWR cho catalogue có hard age limit.
- TTL jitter để giảm mass expiry.
- Negative caching chỉ với source NOT_FOUND.
- Source load limits per cell/tenant, circuit và retry budget.
- Source version/generation fence để chặn stale fill.
- Conditional NoSQL write để quyết định booking.
- Metrics origin amplification, p99, waiters, invalidation lag, stale age và invariants.

## 34. Checklist trước production

1. **Đã phân biệt stampede, avalanche và penetration chưa?**
2. **Cache key có canonical và tenant/auth scope đúng?**
3. **Local singleflight theo key có hoạt động?**
4. **Có distributed coordination nếu nhiều pods cùng miss hot key?**
5. **Refill lease có TTL, token ownership và compare-and-delete?**
6. **Có chịu được duplicate loaders khi lease hết/failover?**
7. **Không dùng refill lock cho business invariants?**
8. **Có hard timeout cho loading future?**
9. **Có giới hạn waiters/queue per key?**
10. **Caller cancel không làm hủy shared load của mọi người?**
11. **Cache double-check trước source load?**
12. **Source read có timeout, concurrency budget và circuit breaker?**
13. **Retry có backoff+jitter và tổng deadline?**
14. **SWR có soft/hard expiry cho đúng data classes?**
15. **Hard stale age cap được enforce?**
16. **Không phục vụ stale cho ACL/booking/balance khi contract cấm?**
17. **TTL jitter có tôn trọng freshness SLO?**
18. **Refresh-ahead chỉ cho hot keys và có origin budget?**
19. **Negative caching chỉ từ authoritative NOT_FOUND?**
20. **Negative TTL phù hợp khả năng tạo item mới?**
21. **Bloom filter có update/rebuild strategy?**
22. **SourceVersion được giữ trong cache envelope?**
23. **Cache fill có generation/version fence?**
24. **Watermark tồn tại đủ lâu để chặn stale loader?**
25. **Invalidation CDC có xử lý lag, duplicate, reorder?**
26. **Strong/read-your-writes API có bypass hoặc minVersion check?**
27. **L1/L2 có expiry, memory/eviction metrics riêng?**
28. **Có kế hoạch Redis outage, pod cold start và region failover?**
29. **Không để một tenant chiếm toàn bộ refill slots?**
30. **Có short-window miss burst và origin amplification metrics?**
31. **Có stale age/refresh failures/version-rejected fills metrics?**
32. **Metrics/logs không lộ raw keys/PII hoặc cardinality quá mức?**
33. **Có test lease expiry và stale overwrite?**
34. **Có fault injection mass expiry/Redis outage/no-quorum?**
35. **Có runbook giảm tải và gradual warmup?**

**Kết luận:** **Cache stampede** xảy ra khi nhiều request đồng thời gặp cache miss và cùng tải một giá trị từ NoSQL, biến một lần hết hạn thành hàng nghìn truy vấn trùng lặp. Giải pháp là phối hợp nạp theo key bằng **singleflight** trong Java và **refill lease** phù hợp giữa các instances, đồng thời dùng **TTL jitter, stale-while-revalidate có hard age cap, negative caching, proactive refresh có giới hạn, admission control và retry budget** để giảm tải bùng nổ. Phải đặc biệt tránh nhầm distributed refill lock với quyền ghi nghiệp vụ: booking, tồn kho, số dư và ACL vẫn cần source authority và consistency rules riêng. **Một loader duy nhất cũng có thể ghi bản cũ vào cache sau invalidation**, nên nguồn dữ liệu cần sourceVersion/generation fence và cache write được kiểm soát. Đánh giá kết quả bằng **origin load amplification, số waiters, p99, stale age, invalidation lag, version correctness và bất biến nghiệp vụ**, không chỉ bằng cache hit ratio trung bình.
