# Áp dụng cache-aside và xử lý cache stampede

Trong một ứng dụng thương mại điện tử, trang chi tiết sản phẩm có thể được đọc hàng nghìn lần mỗi giây nhưng giá, tồn kho hoặc mô tả chỉ thay đổi vài lần mỗi ngày. Nếu mỗi HTTP request đều gọi Azure SQL Database hoặc Azure Cosmos DB, cơ sở dữ liệu dễ bị quá tải ở giờ cao điểm. **Cache** giúp phục vụ nhiều lần đọc từ bộ nhớ nhanh, giảm độ trễ và lượng truy cập tới hệ thống lưu trữ gốc. Tuy nhiên, cache cũng đưa vào những vấn đề mới: dữ liệu có thể cũ, khóa có thể hết hạn đồng loạt và lúc cache trống, quá nhiều request có thể đổ về database trong cùng một thời điểm.

**Cache-aside** (*lazy loading*) là chiến lược ứng dụng chủ động kiểm tra cache trước khi đọc nguồn dữ liệu gốc và tự điền lại cache khi không tìm thấy. **Cache stampede** (*thundering herd*) là hiện tượng nhiều request đồng thời thấy cache miss ở một khóa hoặc nhóm khóa nóng, rồi cùng truy vấn backend hoặc tính toán lại dữ liệu đắt đỏ. Biết sử dụng cache-aside là bước đầu; biết ngăn stampede mà vẫn giữ **tính đúng đắn dữ liệu, độ sẵn sàng và chi phí** mới là yêu cầu cho hệ thống production.

Bài học thuộc chương **Cache và giao tiếp thời gian thực**, module **CLOUD_PROVIDERS_AZURE**. Ví dụ kết nối Java/Spring Boot, Redis trên Azure, Azure SQL hoặc Cosmos DB, Azure Container Apps/AKS, Microsoft Entra ID, VNet/Private Endpoint, Azure Monitor và Cost Management. Khái niệm được minh họa bằng Redis-compatible cache, nhưng các mẫu thiết kế cũng áp dụng cho cache phân tán khác có khả năng tương ứng.

> **Phạm vi sản phẩm:** Azure cung cấp các lựa chọn Redis managed như **Azure Managed Redis** và những môi trường dùng **Azure Cache for Redis**. Tên SKU, cơ chế identity-based authentication, chức năng clustering, replication, Private Endpoint và vòng đời sản phẩm có thể thay đổi. Với triển khai mới hoặc chuyển đổi tài nguyên cũ, phải xác minh **dịch vụ/region/SKU đang được hỗ trợ và thông báo vòng đời chính thức**. Lệnh và mã minh họa cần điều chỉnh theo SDK, Redis protocol và service được tổ chức chấp thuận.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích khi nào cache tăng tốc hệ thống và tại sao cache **không phải nguồn dữ liệu có thẩm quyền** trong mô hình cache-aside.
2. Mô tả luồng **cache hit, cache miss, load từ database, populate cache**, cùng luồng **write database rồi invalidate cache**.
3. Nhận diện **cache stampede**, phân biệt với *cache avalanche*, *cache penetration* và *hot key*.
4. Chọn TTL, jitter, negative caching, soft TTL/hard TTL và refresh-ahead theo tính chất dữ liệu.
5. Triển khai **singleflight/request coalescing** trong một JVM và biết giới hạn khi chạy nhiều pods/instances.
6. Thiết kế **per-key distributed lock/lease** bằng Redis với token, thời hạn và atomic release; hiểu vì sao lock không đủ đảm bảo tính đúng đắn nghiệp vụ.
7. Phân tích race giữa đọc cache, cập nhật database và vô hiệu hóa cache; cân nhắc version, event/outbox và các điều kiện chống ghi đè dữ liệu cũ.
8. Viết ví dụ Java dùng Spring Data Redis và database repository cho cache-aside.
9. Thiết lập metrics, alerts, test tải có kiểm soát, runbook Redis failure và chính sách bảo mật.
10. Ước lượng tác động tới backend throughput, latency, availability và tổng chi phí.

## 2. Vì sao cần cache?

Giả sử API trả hồ sơ sản phẩm:

- Đọc trực tiếp database trung bình mất **25 ms** trong môi trường thử nghiệm.
- Đọc từ Redis mất **2 ms** trong cùng điều kiện mạng.
- Có **5.000 GET/s**, trong đó 90% truy cập lặp lại các sản phẩm phổ biến.

Nếu mọi GET đều tới database, backend nhận gần 5.000 reads/s. Nếu cache hit 90% và mỗi GET hit không cần database, backend chỉ nhận khoảng **500 reads/s** cho luồng này (chưa tính refresh, retry và công việc khác).

| Tín hiệu | Không có cache | Cache hit 90% (minh họa) |
|---|---:|---:|
| HTTP GET mỗi giây | 5.000 | 5.000 |
| Read tới database mỗi giây | 5.000 | Khoảng 500 |
| Độ trễ khi cache hit | Không áp dụng | Khoảng 2 ms cho cache lookup |
| Khả năng dữ liệu cũ | Phụ thuộc database/replication | Có nếu TTL/invalidation sai |
| Điểm lỗi bổ sung | Không có Redis | Redis/network/client pool |

Các số chỉ mô tả **một workload giả định**; độ trễ thực thay đổi theo region, serialization, TLS, cache hit size, network và DB query. Một cache có hit ratio cao nhưng cứ mỗi lần cache miss thì database bị quá tải vẫn có thể khiến SLO thất bại.

### Cache đúng chỗ

Cache hữu ích khi dữ liệu:

- Đọc thường xuyên hơn ghi.
- Tái sử dụng qua nhiều request.
- Tính toán hoặc truy vấn nguồn khá tốn kém.
- Có thể chấp nhận độ cũ được xác định rõ ràng.
- Có khóa tra cứu đơn giản, ổn định.
- Không vi phạm quyền riêng tư khi lưu ngoài data store gốc.

**Không dùng cache để che một query không có index hoặc dữ liệu không có mô hình nhất quán** mà chưa hiểu nguyên nhân. Cache thường là lớp tối ưu trước database, không thay thế schema/index/query tuning.

## 3. Phân biệt các mô hình cache

| Mô hình | Cách nạp dữ liệu | Cách ghi | Đặc điểm |
|---|---|---|---|
| **Cache-aside** | App đọc cache; miss thì đọc DB, tự set cache | DB là nguồn chính; app invalidate/update cache | Đơn giản, kiểm soát tốt theo use case |
| **Read-through** | Cache layer tự gọi loader khi miss | Tùy triển khai | App ít phải tự xử lý load, nhưng cần cache hỗ trợ |
| **Write-through** | Ghi qua cache layer, đồng thời cập nhật source theo cơ chế | Cache và source phối hợp | Cần hiểu atomicity/failure semantics |
| **Write-behind / write-back** | Cache nhận write trước, đẩy xuống source sau | Bất đồng bộ | Rủi ro mất/chậm dữ liệu nếu cache lỗi |
| **Local in-process cache** | Mỗi process có dữ liệu riêng | Invalidate giữa các process khó hơn | Latency rất thấp, nhưng memory và coherence phức tạp |
| **Distributed cache** | Nhiều app instances dùng chung Redis/cache | Dùng giao thức chung | Chia sẻ dữ liệu, thêm network dependency |

Bài này chọn **distributed Redis cache-aside**. Với Java service chạy trên nhiều replicas AKS hoặc Azure Container Apps, một Redis backend dùng chung giúp tránh cache mỗi pod có nội dung hoàn toàn độc lập. Tuy nhiên **mỗi pod vẫn có local threads và connection pools**, nên stampede có thể xuất hiện ở hai cấp: trong từng pod và giữa nhiều pods.

## 4. Cache-aside: luồng đọc chuẩn

~~~mermaid
sequenceDiagram
  participant U as Client
  participant A as Java API
  participant R as Redis cache
  participant D as Database
  U->>A: GET /products/42
  A->>R: GET catalog:tenant-A:42
  alt Cache hit
    R-->>A: Serialized Product
    A-->>U: 200 Product
  else Cache miss
    R-->>A: Nil
    A->>D: SELECT Product by tenant + id
    D-->>A: Product v3
    A->>R: SET key Product v3 EX TTL
    A-->>U: 200 Product
  end
~~~

Thuật toán đọc cơ bản:

~~~text
function getProduct(tenantId, productId):
    key = makeCacheKey(tenantId, productId)

    cached = redis.GET(key)
    if cached is valid:
        return deserialize(cached)             // cache hit

    product = repository.findByTenantAndId(...) // cache miss

    if product exists:
        redis.SET(key, serialize(product), TTL)
    else:
        redis.SET(key, NOT_FOUND_SENTINEL, shortTTL)  // tùy nhu cầu

    return product
~~~

### Chi tiết quan trọng

- **Nguồn dữ liệu gốc là database**, cache có thể bị xóa và được tái tạo.
- **TTL không phải điều kiện bắt buộc về kỹ thuật** cho mọi cache-aside, nhưng thường được dùng để giới hạn độ cũ và memory.
- Không serialize entity ORM chứa lazy proxies, quan hệ vòng hoặc trường bí mật một cách vô ý. Nên dùng **DTO rõ schema**.
- Đọc database xong rồi set cache có thể thất bại; ứng dụng cần chính sách có trả kết quả từ DB hay không.
- Nếu Redis trả lỗi mạng, phải có **fallback có kiểm soát** hoặc fail-fast theo nghiệp vụ; không coi lỗi cache là cache miss bình thường rồi để toàn bộ traffic đánh sập database.
- Không thể suy luận cache hit từ status HTTP 200; phải instrument cache lookup riêng.

## 5. Cache-aside: luồng ghi và vô hiệu hóa

Với thông tin thay đổi, hướng thường dễ hiểu là:

~~~text
function updateProduct(command):
    validate authorization and business rules
    database.TRANSACTION:
        update product
        increment productVersion
    COMMIT
    cache.DELETE(productKey)  // invalidate sau khi DB commit
    return updated product
~~~

Vì sao thường **ghi database trước, xóa cache sau**?

1. DB là nguồn dữ liệu chuẩn, nên commit phải thành công trước khi tuyên bố write thành công.
2. Nếu xóa cache trước rồi database update thất bại, có thể tạo thêm cache misses không cần thiết.
3. Sau commit, xóa cache khiến GET tiếp theo có cơ hội đọc giá trị mới.

Nhưng cách này **không bảo đảm linearizable cache**. Một GET có thể đọc dữ liệu cũ từ DB ngay trước khi update commit, rồi set lại cache sau khi writer vừa xóa cache. Chúng ta sẽ phân tích race này ở phần sau.

### Invalidate hay update cache?

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| **Invalidate on write** | Dễ vận hành; request sau load lại dữ liệu chuẩn | Miss burst; race với loader; chi phí đọc |
| **Update cache on write** | Có dữ liệu mới ngay khi ghi | Thứ tự write race; cache update thất bại; object serialization khác |
| **Versioned cache key** | Giảm khả năng ghi đè version cũ lên version mới | Cần version ổn định/lookup version; key cũ còn tồn tại tới TTL |
| **Event-based invalidation** | Dùng khi nhiều dịch vụ cập nhật cùng dữ liệu | Delivery delay/duplicate/loss; cần outbox/idempotency |

Với ứng dụng cần **đọc ngay giá/định mức giao dịch chính xác**, nhiều thao tác phải **đọc trực tiếp DB hoặc dùng cơ chế phiên bản/điều kiện đúng đắn** thay vì mặc định tin cache còn sống.

## 6. Dùng Redis trên Azure

Một kiến trúc điển hình:

~~~mermaid
flowchart LR
  U["Clients"] --> G["APIM / Ingress"]
  G --> API["Java API: AKS / Container Apps"]
  API --> C["Azure-managed Redis cache qua private network"]
  API --> DB["Azure SQL / Cosmos DB"]
  API --> MON["Azure Monitor / Application Insights"]
  C --> MON
  DB --> MON
  OPS["Entra ID / Key Vault / RBAC"] -.-> API
~~~

Các thành phần cần xác định:

- **VNet/Private Endpoint hoặc network access path** cho đúng Azure Redis service/SKU.
- **TLS và hostname validation** của Redis client.
- **Authentication/authorization** qua cơ chế được product version/SKU hỗ trợ; managed identity/Entra ID nếu phù hợp, hoặc credentials được quản lý trong Key Vault.
- **Client pooling và timeouts** để giảm số connections và tránh request bị treo.
- **HA/replication/failover** của cache và thời gian reconnect.
- **Memory capacity, eviction policy, persistence** nếu cần theo tính năng hỗ trợ.
- **Metrics/alerts**, backup strategy của DB và cost tagging.

### Redis là lớp tăng tốc, không phải nguồn dữ liệu bền vững

Các cache managed có thể có tùy chọn persistence/replication, nhưng với cache-aside **không được coi Redis là nơi duy nhất chứa đơn hàng hoặc payment state**. Nếu toàn bộ cache mất, ứng dụng phải có kế hoạch warm-up lại và bảo vệ backend khỏi lượng cache misses đột ngột.

### Không nhầm Azure Managed Redis với Azure Cache for Redis

Cả hai có thể xuất hiện trong tổ chức tùy thời điểm và trạng thái migration. Tên ARM resource type, CLI, tier, private network, cơ chế Entra auth và timeline vòng đời **không nhất thiết giống nhau**. Tránh tự động dùng lệnh của một dịch vụ cho dịch vụ kia. Khi lập dự án mới, kiểm tra lựa chọn được Azure khuyến nghị tại thời điểm triển khai và chính sách nội bộ.

## 7. Thiết kế cache key an toàn, ổn định

Một mẫu key dễ quản trị:

~~~text
catalog:prod:tenant-A:product:42:v1
~~~

Có thể phân tích:

- `catalog`: domain.
- `prod`: môi trường nếu nhiều môi trường dùng chung cache (thường nên cô lập cấp resource).
- `tenant-A`: tenant boundary khi có multi-tenancy.
- `product`: loại đối tượng.
- `42`: ID nghiệp vụ.
- `v1`: version của **schema cache key/value**, không nhất thiết version từng item.

### Quy tắc thiết kế

1. **Không lấy key từ raw URL/headers chưa validate**; giới hạn độ dài và ký tự.
2. Bao gồm tenant/security scope nếu dữ liệu khác nhau theo người gọi.
3. Không đưa token, số thẻ, password, email nguyên văn hoặc PII vào key.
4. Nếu key chứa ID nhạy cảm, cân nhắc hashing/HMAC hoặc namespace không lộ trực tiếp.
5. Nhất quán canonicalization: chữ hoa/thường, Unicode, URL encoding và format ID.
6. Khi đổi cache value schema không tương thích, có version trong key hoặc cơ chế migration.
7. Không dùng **một key toàn cục** cho dữ liệu của các tenants khác nhau.
8. Tách key dữ liệu, key lock và key metadata để tránh xóa nhầm.

### Cache key cardinality

Nếu mỗi request dùng một UUID mới làm key, hit ratio gần bằng 0 và cache chỉ tốn RAM. Muốn cache hiệu quả, phải có **tính tái sử dụng**; với kết quả search chứa hàng chục tham số, cần canonicalize query, xét quyền dữ liệu và giới hạn biến thể được cache.

## 8. Chọn TTL theo yêu cầu freshness

**TTL (Time to Live)** là thời gian key tồn tại trước khi hết hạn theo Redis semantics. TTL dài:

- Tăng cache hit ratio.
- Giảm query database.
- Tăng nguy cơ dữ liệu cũ nếu không invalidate đúng.

TTL ngắn:

- Giảm độ cũ tối đa trong nhiều trường hợp.
- Tăng miss rate và backend load.
- Có thể khiến stampede xảy ra thường xuyên hơn.

Ví dụ để thảo luận:

| Dữ liệu | Độ cũ chấp nhận | Hướng TTL |
|---|---|---|
| Danh mục/description sản phẩm | Vài phút nếu có invalidation | Vài phút, đo thực tế |
| Tồn kho hiển thị | Có thể vài giây tùy nghiệp vụ | Ngắn; giao dịch vẫn kiểm tra DB |
| Giá tại thời điểm thanh toán | Cần correctness nghiêm ngặt | Không dựa duy nhất vào cache |
| Cấu hình ít đổi | Có thể dài hơn kèm event invalidation | Dài vừa phải + refresh khi đổi |
| Kết quả không tìm thấy | Chỉ chịu stale-negative rất ngắn | Negative TTL ngắn |
| Public reference data | Ít đổi, có version | TTL dài + versioned key |

**Không coi TTL là SLA freshness tuyệt đối** nếu backend thay đổi mà invalidation/event propagation bị chậm. TTL giới hạn một phần thời gian lưu dữ liệu, nhưng races, replication và stale-serving policy cũng tác động.

### Cài TTL đúng

~~~text
SET catalog:prod:tenant-A:product:42:v1 "{...json...}" EX 600
~~~

Lệnh Redis minh họa lưu trong **600 giây**. Các hệ Redis-compatible có semantics khác biệt theo cấu hình và client; xác minh version hỗ trợ lệnh. Không dùng `SET` không TTL cho dữ liệu luôn thay đổi nếu không có lifecycle/invalidation chắc chắn.

## 9. Cache stampede là gì?

Giả sử một sản phẩm cực phổ biến có 3.000 GET/s. Toàn bộ requests trước đó được cache. Đúng 12:00:00, key hết hạn:

~~~mermaid
sequenceDiagram
  participant R as 3.000 concurrent requests
  participant A as API replicas
  participant C as Redis
  participant D as Database
  R->>A: GET hot product
  A->>C: GET product:42
  C-->>A: Nil (TTL expired)
  par Workers miss cùng lúc
    A->>D: SELECT product 42
    A->>D: SELECT product 42
    A->>D: SELECT product 42
  end
  D-->>A: Product
  A->>C: SET product:42
~~~

Nếu request mất 40 ms để load dữ liệu, trong cửa sổ đó có thể xuất hiện khoảng **120 requests** cho key nóng (3.000 × 0,040). Nếu backend chậm dần tới 500 ms do contention, số requests cùng chờ có thể tăng lên khoảng **1.500**. Con số là mô hình gần đúng theo traffic đều; thực tế phụ thuộc concurrency, scheduler, cache round-trip và timeouts.

**Bản chất:** nhiều request cùng làm **một công việc tái nạp lặp lại**, làm backend chậm, kéo dài miss window và tạo phản hồi khuếch đại.

### Stampede có thể xảy ra khi

- Một hot key hết TTL.
- Cache node bị restart/failover và mất một phần keys.
- Deployment hoặc thay key schema khiến nhiều key chưa được warm.
- Redis eviction xóa hot key do thiếu memory.
- Database/Redis lỗi tạm khiến lần populate trước không thành công.
- Nhiều replicas được scale-out và cùng truy cập một key mới.

## 10. Phân biệt stampede, avalanche, penetration và hot key

| Hiện tượng | Nguyên nhân | Ví dụ | Biện pháp chính |
|---|---|---|---|
| **Cache stampede** | Nhiều requests đồng thời recompute cùng key đắt đỏ | Top product hết TTL | Singleflight, per-key lease, stale-while-revalidate |
| **Cache avalanche** | Rất nhiều keys hết hạn/mất đồng thời | 100.000 keys có TTL 600s được tạo cùng lúc | TTL jitter, warm-up, partition traffic, load shedding |
| **Cache penetration** | Requests liên tục vào các keys không tồn tại | Bot quét random product IDs | Negative caching, validation, rate limit, Bloom filter khi phù hợp |
| **Hot key** | Một key bị truy cập quá dày | Banner/sản phẩm nổi bật | Local cache, sharding/replication nếu phù hợp, throttling |
| **Hot partition/backing DB** | Phân bố dữ liệu không đều | Một tenant chiếm gần hết RU/s | Thiết kế partition key, không chỉ thêm cache |

Những vấn đề này có thể xảy ra cùng lúc. Một hot key là **đối tượng dễ gây stampede**, nhưng chính hot key không đồng nghĩa cache miss. TTL jitter tốt để tránh **nhiều keys cùng hết hạn**, nhưng **không đủ** ngăn nhiều request cùng miss **một key**.

## 11. Chiến lược 1 — Singleflight trong một JVM

**Singleflight** còn gọi là *request coalescing*: những luồng đồng thời của **cùng key** chia sẻ một công việc load thay vì mỗi luồng gọi DB riêng.

~~~text
GET product:42 -> miss
  Request A (leader) -> load DB once -> populate Redis
  Request B (follower) -> await result from A
  Request C (follower) -> await result from A
  Request D (follower) -> await result from A
~~~

### Thuật toán

1. Kiểm tra Redis cache.
2. Nếu miss, tìm **in-flight future** theo key trong process.
3. Nếu đã có, đợi future theo timeout thích hợp.
4. Nếu chưa, trở thành leader, **re-check cache** rồi load DB.
5. Leader complete future (thành công hoặc exception).
6. Xóa entry in-flight bằng compare-remove, tránh memory leak.
7. Follower nhận kết quả/exception theo policy.

### Java: component singleflight đơn giản

Ví dụ Java 17, class độc lập minh họa request coalescing. **Cần giới hạn concurrent keys, timeout và circuit breaker ở production**; snippet tập trung vào nguyên tắc:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;

public final class SingleFlight {
    private final ConcurrentHashMap<String, CompletableFuture<Object>> inFlight =
        new ConcurrentHashMap<>();

    @SuppressWarnings("unchecked")
    public <T> T run(String key, Callable<T> load) {
        CompletableFuture<Object> mine = new CompletableFuture<>();
        CompletableFuture<Object> existing = inFlight.putIfAbsent(key, mine);

        if (existing != null) {
            // Follower: cùng một key chờ leader.
            return (T) existing.join();
        }

        try {
            // Leader: caller phải re-check cache trước khi truy vấn DB.
            T result = load.call();
            mine.complete(result);
            return result;
        } catch (Exception ex) {
            mine.completeExceptionally(ex);
            throw new CompletionException(ex);
        } finally {
            inFlight.remove(key, mine);
        }
    }
}
~~~

### Giới hạn cần hiểu

- Tất cả người gọi **cùng key phải dùng cùng kiểu dữ liệu**; không trộn Java types cho một cache key.
- `join()` có thể chờ lâu nếu loader treo; production cần timeout/cancellation và giới hạn số followers.
- Nếu loader trả exception, followers cũng nhận exception; cần fallback/retry có budget.
- Nếu loader gọi đệ quy singleflight trên **chính key đó**, có thể gây deadlock.
- `ConcurrentHashMap` chỉ dùng trong **một JVM**. Với 20 pods, có thể vẫn còn 20 leaders cho cùng key Redis.
- Không dùng map in-flight làm cơ chế đồng bộ transaction hoặc bảo đảm exactly-once.
- Nếu leader bị dừng đột ngột, process cũng mất futures; hệ thống khác sẽ tự load lại khi có miss.

**Kết luận:** singleflight là biện pháp ít phức tạp, hiệu quả để chặn trùng lặp **nội bộ mỗi instance**. Dùng thêm biện pháp giữa các instances nếu backend dễ bị quá tải.

## 12. Chiến lược 2 — Per-key distributed lease với Redis

Nhiều Java replicas không dùng chung `ConcurrentHashMap`. Có thể dùng một **Redis per-key lock/lease**:

~~~text
data key: catalog:prod:tenant-A:product:42:v1
lock key: lock:catalog:prod:tenant-A:product:42:v1

Replica A: SET lockKey token-A NX PX 5000 -> OK
Replica B: SET lockKey token-B NX PX 5000 -> nil
Replica C: SET lockKey token-C NX PX 5000 -> nil

Replica A: re-check cache -> load DB -> SET data TTL
Replica A: release lock if value == token-A
Replica B/C: bounded wait + retry cache GET -> hit
~~~

Đây là **lease có thời hạn**, không phải lock vĩnh viễn. TTL lock phải đủ để thao tác load thông thường hoàn tất nhưng vẫn có phương án khi worker chết.

### Tại sao dùng token ngẫu nhiên?

Nếu chỉ gọi `DEL lockKey` trong `finally`, tình huống nguy hiểm:

1. A lấy lock, sau đó load chậm và lease hết hạn.
2. B lấy lock mới và bắt đầu load.
3. A kết thúc muộn, gọi DEL.
4. A xóa **lock của B**, cho C tiếp tục lấy lock.

Do đó mỗi lock owner cần token độc nhất và giải phóng **atomic compare-and-delete**.

### Redis Lua: release đúng lock của mình

~~~lua
-- KEYS[1] = lock key
-- ARGV[1] = unique token of current owner
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
~~~

Client gửi script atomically đến Redis instance/shard chứa key theo khả năng server. Không tách thành `GET` rồi `DEL` trong hai network calls vì race giữa chúng.

### Các điều kiện bắt buộc

1. Lock **theo key**, không một global lock cho toàn bộ cache.
2. Re-check data key **sau khi lấy lock**, vì replica khác có thể đã populate.
3. Giới hạn thời gian DB load, lock lease và thời gian follower đợi.
4. Nếu không lấy lock, không busy-wait nóng; dùng short bounded backoff/jitter.
5. Khi lock hết hạn hoặc Redis failover, phải tính đến **hai loaders đồng thời**.
6. Không dùng Redis lock như **nguồn đúng đắn** cho thanh toán, trừ tồn kho hoặc transaction quan trọng.
7. Lock owner lỗi vẫn phải release nếu giữ token; cuối cùng lease timeout giúp hệ thống tự phục hồi.
8. Đặt metrics lock contention, wait duration, lease expiry và backend loads.

### Lock giúp tiết kiệm tài nguyên, không chứng minh dữ liệu mới nhất

Lease hết hạn khi A đang đọc DB v1, B có thể lấy lock mới, đọc v2 và set cache. A chạy xong muộn rồi set v1: **stale overwrite** có thể xảy ra. Giải pháp cần **version/fencing/conditional write** hoặc bảo đảm trình tự cập nhật theo dữ liệu nguồn, không chỉ so token của lock.

### Redis replication/failover và distributed lock

Không mặc định một Redis cluster có asynchronous replication sẽ bảo đảm lock không bị mất khi primary failover. Trong trường hợp lock data thất lạc, có thể có nhiều owners. Với **cache recomputation**, điều này có thể chấp nhận nếu side effect chỉ là đọc DB và populate cache có bảo vệ version; với **distributed business critical sections**, phải dùng cơ chế đồng bộ/correctness có bảo đảm phù hợp hơn.

## 13. Chiến lược 3 — TTL jitter

**TTL jitter** thêm biến thiên ngẫu nhiên có giới hạn để nhiều keys không hết hạn cùng một giây.

Ví dụ:

~~~text
Base TTL = 600 giây
Jitter   = số nguyên ngẫu nhiên trong [-60, +60]

TTL thực tế có thể trong khoảng 540..660 giây
~~~

Java:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class CacheTtl {
    public static Duration withJitterSeconds(long baseSeconds, long jitter) {
        if (baseSeconds <= jitter || jitter < 0) {
            throw new IllegalArgumentException("TTL must remain positive");
        }
        long adjustment = ThreadLocalRandom.current()
            .nextLong(-jitter, jitter + 1);
        return Duration.ofSeconds(baseSeconds + adjustment);
    }
}
~~~

**Phù hợp:** hàng loạt keys được load cùng giờ và có TTL giống nhau, ví dụ đợt deploy hoặc warm-up.

**Không đủ:** 10.000 requests cùng truy cập **một** key ngay khi nó hết hạn. Key đó vẫn có cùng expiry đối với mọi readers; cần singleflight, lease hoặc stale-serving.

Lưu ý TTL jitter không được khiến dữ liệu vượt giới hạn freshness mà nghiệp vụ cho phép. Nếu hard maximum freshness là 600s, dùng **base 540 + jitter 0..60** thay vì cho phép TTL 660s.

## 14. Chiến lược 4 — Soft TTL, hard TTL và stale-while-revalidate

Với dữ liệu đọc nhiều nhưng có thể chấp nhận độ cũ ngắn hạn, một phương án hiệu quả là **stale-while-revalidate**:

- **Soft TTL:** thời điểm nên refresh.
- **Hard TTL:** thời điểm không được phục vụ dữ liệu cũ hơn nữa.
- Giữa soft và hard TTL, request có thể nhận **stale value** nhanh trong khi một worker duy nhất bắt đầu refresh.

Ví dụ:

~~~text
11:00:00   Giá trị v4 được lưu
11:04:00   Soft TTL đến hạn
11:04:01   Request A trả v4, kick off one refresh
11:04:02   Request B trả v4, không kích hoạt refresh trùng
11:04:03   Refresh đọc DB v5 và cập nhật cache
11:10:00   Hard TTL tối đa nếu chưa refresh thành công
~~~

### Envelope lưu trong Redis

~~~json
{
  "schemaVersion": 1,
  "dataVersion": 5,
  "cachedAt": "2026-11-20T11:00:00Z",
  "softExpiresAt": "2026-11-20T11:04:00Z",
  "hardExpiresAt": "2026-11-20T11:10:00Z",
  "value": {
    "id": "42",
    "name": "Bình giữ nhiệt",
    "priceMinor": 259000
  }
}
~~~

**Redis TTL vật lý** có thể đặt theo hard TTL; soft TTL là metadata do ứng dụng kiểm soát. Nếu refresh không thành công, chỉ serve stale **trong giới hạn cho phép**.

### Khi nào không được serve stale?

- Kiểm tra quyền, revoked session, policy truy cập.
- Xác nhận còn tồn kho trước khi trừ kho.
- Số dư tài khoản hoặc hạn mức thanh toán.
- Giá cần chốt đúng tại giao dịch.
- Dữ liệu có yêu cầu pháp lý về độ mới tức thời.

Cùng một object có thể có endpoint **display** chấp nhận stale vài giây, còn endpoint **checkout** bắt buộc lấy số liệu chuẩn/validate transaction ở DB.

### Async refresh cần kiểm soát

Đừng tạo một thread mới cho mỗi request stale. Dùng bounded executor, queue/scheduler và singleflight/lease. Theo dõi refresh failures; không để hàng nghìn refresh jobs chạy song song vì cache hot.

## 15. Chiến lược 5 — Refresh-ahead và prewarming

**Refresh-ahead** chủ động làm mới hot keys trước lúc hết hạn, dựa trên access pattern hoặc lịch.

Một cách:

1. Xác định top-N keys có tỷ lệ truy cập cao.
2. Trước soft TTL, chọn một worker/lease holder refresh.
3. Nếu refresh thành công, set value mới với TTL.
4. Nếu lỗi, giữ stale trong hard TTL hoặc fallback theo policy.
5. Giới hạn concurrency và tốc độ để không tạo batch spike tới DB.

**Prewarming** phù hợp sau khi deploy, thay schema version hoặc phục hồi Redis từ trạng thái trống. Có thể lấy danh sách top products từ DB hoặc một bảng/cấu hình riêng rồi nạp tuần tự.

Không warm mọi product của hệ thống nếu phần lớn không bao giờ được đọc: bạn sẽ trả phí Redis memory và load DB để phục vụ dữ liệu không dùng tới. **Warm hot set dựa trên đo lường**, tránh đồng thời nạp một triệu keys không có rate limit.

## 16. Chiến lược 6 — Negative caching và chống cache penetration

Nếu client yêu cầu một product ID không tồn tại, mỗi request cache miss lại truy vấn DB. Một bot quét ngẫu nhiên hàng triệu ID có thể gây load khổng lồ dù không đọc dữ liệu hợp lệ.

**Negative caching** lưu kết quả "không tồn tại" trong thời gian ngắn:

~~~text
GET product:unknown-123
  -> Redis miss
  -> DB NOT FOUND
  -> Redis SET key "NOT_FOUND" EX 15
  -> HTTP 404

Request cùng key trong 15s
  -> Redis NOT_FOUND
  -> HTTP 404, không gọi DB
~~~

### Rủi ro

- Key vừa được tạo sau khi cache 404, nhưng sentinel cũ còn tồn tại → **stale negative**.
- Không phân biệt **404 thật** với timeout/500 DB: tuyệt đối **không cache lỗi backend như NOT_FOUND**.
- Nếu mỗi request mang ID ngẫu nhiên mới, negative caching khó có hit và có thể chiếm memory; cần validation/rate limit.
- Sentinel phải có type rõ, tránh trùng với JSON payload hoặc "null" bình thường.
- Quyền truy cập: không cache kết quả "không thấy vì không có quyền" chung với tenant khác nếu điều đó làm rò rỉ thông tin.

**Negative TTL thường ngắn hơn positive TTL** và nên invalidate khi tạo mới đối tượng.

### Bloom filter có phù hợp?

Bloom filter có thể giảm DB lookup cho IDs chắc chắn không tồn tại trong một tập đã biết, nhưng có **false positives**, cần cập nhật khi data thay đổi, có memory/maintenance cost. Nó không thay thế authorization hoặc nguồn dữ liệu chuẩn và không cần thiết cho mọi API.

## 17. Viết Java cache-aside cơ bản với Spring Data Redis

Ví dụ này minh họa **cache-first read + database fallback + TTL + negative caching + invalidation after commit**. Nó giả định dự án Spring Boot Java 17+, Spring Data Redis, Jackson, và một repository được người học triển khai cho Azure SQL/Cosmos DB. Đây là mẫu kiến trúc, **không phải ứng dụng Spring Boot hoàn chỉnh có thể chạy nếu chưa thêm datasource và dependencies**.

### Maven dependencies ở mức khái niệm

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
  </dependency>
  <!-- Thêm driver/repository của Azure SQL hoặc Cosmos DB nếu cần. -->
</dependencies>
~~~

Phiên bản dependency thường do Spring Boot BOM quản lý; với Java 17 cần chọn Spring Boot version tương thích. Redis client có thể là Lettuce/Jedis theo cấu hình. **Không dùng dependency version ngẫu nhiên** hoặc chèn account key vào POM.

### Model và repository

~~~java
package com.example.catalog;

import java.util.Optional;

public record ProductDto(
    String id,
    String tenantId,
    String name,
    long priceMinor,
    long version
) {}

interface ProductRepository {
    Optional<ProductDto> findByTenantAndId(String tenantId, String id);
    ProductDto updatePrice(String tenantId, String id, long newPriceMinor);
}
~~~

`ProductRepository` ở đây là **interface minh họa**. Production cần hiện thực bằng Spring Data JDBC/JPA, Cosmos SDK hay repository tương thích, kiểm soát transaction, version, permissions và retry. Giá trị tiền dùng đơn vị nhỏ nhất theo hợp đồng nghiệp vụ, không tùy tiện dùng `double`.

### Service Java

~~~java
package com.example.catalog;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public final class ProductCacheService {
    private static final String ABSENT = "__CACHE_NOT_FOUND__";

    private final StringRedisTemplate redis;
    private final ProductRepository repository;
    private final ObjectMapper json;

    public ProductCacheService(
            StringRedisTemplate redis,
            ProductRepository repository,
            ObjectMapper json) {
        this.redis = redis;
        this.repository = repository;
        this.json = json;
    }

    public Optional<ProductDto> find(String tenantId, String id) {
        String key = productKey(tenantId, id);
        String cached = redis.opsForValue().get(key);

        if (ABSENT.equals(cached)) {
            return Optional.empty(); // negative hit
        }
        if (cached != null) {
            return Optional.of(fromJson(cached)); // positive hit
        }

        Optional<ProductDto> result =
            repository.findByTenantAndId(tenantId, id);

        if (result.isPresent()) {
            long jitter = ThreadLocalRandom.current().nextLong(0, 61);
            redis.opsForValue().set(
                key, toJson(result.get()), Duration.ofSeconds(540 + jitter));
        } else {
            redis.opsForValue().set(key, ABSENT, Duration.ofSeconds(15));
        }
        return result;
    }

    public ProductDto updatePrice(
            String tenantId, String id, long priceMinor) {
        // Repository phải commit transaction trước khi trả về.
        ProductDto updated = repository.updatePrice(tenantId, id, priceMinor);

        // Sau DB commit mới invalidate. Xem race trong phần sau.
        redis.delete(productKey(tenantId, id));
        return updated;
    }

    private static String productKey(String tenantId, String id) {
        if (!tenantId.matches("[a-zA-Z0-9_-]{1,64}")
                || !id.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid cache key components");
        }
        return "catalog:prod:" + tenantId + ":product:" + id + ":v1";
    }

    private String toJson(ProductDto value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize product", ex);
        }
    }

    private ProductDto fromJson(String value) {
        try {
            return json.readValue(value, ProductDto.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Invalid cached product JSON", ex);
        }
    }
}
~~~

### Những gì mẫu trên **chưa** giải quyết

- Stampede giữa nhiều requests và nhiều replicas.
- Thời gian chờ Redis/DB, circuit breaker, fallback và rate limit.
- Transaction DB update và invalidation **atomic** (thực tế không atomic).
- Race làm stale loader ghi đè sau khi writer xóa cache.
- Redis connection failures khi DB đã commit: write vẫn thành công nhưng invalidate lỗi.
- Nhiều services cùng sửa giá, version conflict và reliable invalidation event.
- Serialization/schema migration, malformed entry repair và compression.
- Authorization và kiểm tra tính tách biệt tenants từ token đã xác thực.
- Negative cache invalidation khi tạo product mới.
- Telemetry, retries, timeout, metrics và kiểm thử tải.

**Đây là bản nền tảng để người học phát triển**, không phải hàm phù hợp trực tiếp cho giao dịch tài chính. Với kiến trúc production, bổ sung singleflight/per-key lease/stale policy và bảo vệ version theo yêu cầu.

## 18. Kết hợp singleflight vào cache-aside

Để áp dụng class `SingleFlight` đã giới thiệu:

~~~java
private final SingleFlight singleFlight = new SingleFlight();

public Optional<ProductDto> findWithSingleFlight(
        String tenantId, String id) {
    String key = productKey(tenantId, id);

    // Đọc cache trước; phân biệt positive hit / negative hit / miss.
    CacheLookup<ProductDto> lookup = readCache(key);
    if (lookup.isHit()) {
        return lookup.value();
    }

    return singleFlight.run(key, () -> {
        // Re-check rất quan trọng: leader khác có thể vừa populate.
        CacheLookup<ProductDto> second = readCache(key);
        if (second.isHit()) {
            return second.value();
        }

        Optional<ProductDto> source =
            repository.findByTenantAndId(tenantId, id);
        populateWithTtl(key, source);
        return source;
    });
}
~~~

`CacheLookup`, `readCache` và `populateWithTtl` là **abstractions cần hiện thực**: phải phân biệt "negative hit" với "cache miss". Không thể chỉ trả `Optional.empty()` cho cả hai rồi đánh nhầm.

### Vì sao double-check quan trọng?

Giả sử leader mất 20 ms để có quyền, trong lúc đó một replica khác đã nạp dữ liệu. Nếu không GET cache lần nữa, leader vẫn truy vấn DB vô ích. Double-check cũng cần sau khi lấy Redis lock.

### Không block vô hạn

Trong production, follower nên có timeout hữu hạn, giới hạn tổng request timeout và fallback an toàn. Một request HTTP với SLO 300 ms không thể đợi leader DB 10 giây rồi vẫn kỳ vọng SLA. Với endpoint không chấp nhận stale, có thể trả 503/429 có kiểm soát thay vì vượt tải downstream.

## 19. Kết hợp singleflight, Redis lease và stale serving

Một chính sách cho dữ liệu ít thay đổi nhưng có tải cao:

~~~mermaid
flowchart TD
  A["GET Product"] --> B{"Cache entry còn fresh?"}
  B -->|Có| H["Return fresh"]
  B -->|Không| C{"Có stale hợp lệ trước hard TTL?"}
  C -->|Có| S["Return stale nhanh"]
  S --> REF["Schedule 1 refresh per key"]
  C -->|Không| L["Local singleflight per key"]
  L --> D{"Acquire distributed per-key lease?"}
  D -->|Có| R["Double-check cache rồi load source"]
  R --> V["Publish version-safe cache value + TTL"]
  V --> OK["Return fresh"]
  D -->|Không| W["Bounded wait + jitter + reread cache"]
  W --> E{"Cache đã có giá trị hợp lệ?"}
  E -->|Có| OK
  E -->|Không| F["Fallback/503 theo SLO, không flood database"]
~~~

**Đừng dùng mọi cơ chế cùng lúc nếu không cần.** Với traffic vừa phải, cache-aside + TTL jitter có thể đủ. Với hot keys, thêm local singleflight. Với nhiều replicas và DB yếu, xem per-key lease. Nếu latency cực quan trọng và dữ liệu chấp nhận stale, thêm soft TTL/hard TTL và background refresh.

### Fallback khi không lấy lease

Các lựa chọn có chủ đích:

1. Đợi ngắn có jitter rồi GET cache lại.
2. Trả stale nếu còn trong hard TTL và nghiệp vụ cho phép.
3. Dùng bounded semaphore cho số requests được phép query DB trực tiếp.
4. Trả 503 hoặc 429 theo API contract khi backend đang bảo vệ capacity.
5. Với công việc không đồng bộ, đưa job vào Queue và trả 202 nếu đúng semantics.

**Không** cho tất cả followers đồng loạt bỏ lock và gọi database: như vậy lock không còn bảo vệ backend.

## 20. Race nguy hiểm: cache-aside stale overwrite

Xét một key có giá trị v1, rồi writer cập nhật lên v2.

~~~text
T1  Reader A: Redis GET -> miss
T2  Reader A: DB SELECT -> v1
T3  Writer B: DB UPDATE -> v2, COMMIT
T4  Writer B: Redis DEL key
T5  Reader A: Redis SET key = v1, TTL 10 phút
T6  Reader C: GET -> v1, dù database là v2
~~~

Đây là **read-write race**. Quy tắc "DB first, delete cache after" giảm một số lỗi phổ biến nhưng **không tự ngăn** trường hợp trên.

### Biện pháp cần cân nhắc theo mức độ nghiêm trọng

**A. TTL ngắn + invalidation:** chấp nhận stale tối đa trong khoảng ngắn khi display data, dễ triển khai. Không đủ cho correctness nghiêm ngặt.

**B. Versioned cache envelope:** dữ liệu từ DB có `version`/`updatedAt` đáng tin. Khi ghi cache, dùng atomic compare-and-set (ví dụ Lua trong Redis) để không ghi version cũ đè version mới **nếu cache hiện còn version mới**. Cần thiết kế khi key đã bị DEL (không còn thông tin version) để tránh stale repopulation.

**C. Durable generation/version marker:** writer tăng một generation hoặc lưu version ở nguồn đáng tin cậy; loader chỉ set khi version/generation phù hợp. Phải đảm bảo marker không mất do Redis failover/eviction hoặc dùng data store bền vững; nếu không vẫn có lỗ hổng.

**D. Per-key coordination cho cả writer và loader:** reader loader và writer tham gia cùng cơ chế khóa/versioning. Redis lease đơn thuần vẫn có expiry/failover, nên không dùng làm correctness lock tuyệt đối.

**E. Tránh cache trên đường giao dịch bắt buộc đúng:** checkout, trừ kho, quyết toán đọc/ghi DB với điều kiện transaction/ETag/unique constraints.

### Version và cache key

Một mô hình:

~~~text
product current version in authoritative source: 7
cache data: catalog:tenant-A:product:42:version:7

Reader biết version 7 -> đọc đúng key v7
Writer update v8 -> người đọc mới chọn key v8
Key v7 để TTL tự xóa
~~~

Nhưng **reader cần biết version chuẩn**; nếu phải query DB để biết version ở mỗi GET, lợi ích cache có thể giảm. Có thể dùng metadata cập nhật tin cậy/CDC/outbox hoặc một policy staleness có chủ đích. Không dùng công thức versioned key như một lời bảo đảm miễn phí khi version discovery chưa giải quyết.

## 21. Reliable invalidation với outbox và events

Khi sản phẩm thay đổi qua nhiều services, không thể tin một instance sẽ luôn chạy tới lệnh `DEL`. Ví dụ:

~~~text
DB commit thành công
    -> ứng dụng crash
    -> Redis DEL chưa chạy
    -> cache giữ giá cũ cho tới TTL
~~~

**Transactional outbox** giúp ghi sự kiện thay đổi cùng transaction database. Một publisher gửi event tới Service Bus/Event Grid/Queue theo thiết kế phù hợp; cache invalidator nhận event và xóa/refresh key.

~~~mermaid
flowchart LR
  W["Product service"] --> DB["DB transaction: Product v8 + Outbox"]
  DB --> P["Outbox publisher"]
  P --> B["Service Bus / event delivery"]
  B --> I["Cache invalidator"]
  I --> C["Redis DEL / version-aware update"]
  B --> M["Monitoring / replay"]
~~~

Những điều cần hiểu:

- Event có thể giao **trùng hoặc chậm**. Handler phải idempotent.
- Nếu event v8 đến sau v9, handler xóa key chung có thể chỉ làm tăng misses, nhưng **update cache bằng v8** có thể ghi stale nếu không so version.
- Pub/Sub notification không bền vững một mình nếu subscriber offline; cần broker/outbox phù hợp khi yêu cầu reliable invalidation.
- Event propagation có độ trễ; với nghiệp vụ cần strong correctness, không chỉ dựa vào eventual invalidation.
- Log/metrics phải ghi lag của outbox, số events lỗi, cache invalidations và DLQ.
- Cần đảm bảo cùng key được tạo từ mọi service theo cùng cache-key spec.

### Cache key invalidation và đa tenant

Nếu update của tenant-A chỉ xóa `catalog:tenant-A:product:42`, tuyệt đối tránh xóa một key tương tự của tenant-B vì bỏ quên scope. Ngược lại, nếu cache key thiếu tenant nhưng data khác nhau, có thể gây **rò rỉ dữ liệu xuyên tenant**.

## 22. Khi cache hoặc Redis gặp sự cố

Cache-aside thông thường coi cache là **best effort**: nếu Redis không đọc/ghi được, ứng dụng có thể rơi về DB. Nhưng nếu 10.000 RPS đồng thời fallback, database có thể sập.

### Chính sách failure có kiểm soát

- Đặt **timeout ngắn, hữu hạn** cho Redis operations phù hợp SLO.
- Có circuit breaker để tránh dồn threads/connection pool vào cache đã lỗi.
- Giới hạn **DB fallback concurrency** bằng bulkhead/semaphore.
- Dùng rate limiting hoặc load shedding khi DB gần capacity.
- Nếu có stale local cache trong phạm vi policy, có thể phục vụ tạm cho display data.
- Trả 503/429 kèm cách retry có kiểm soát khi không thể đáp ứng an toàn.
- Theo dõi Redis reconnect, timeout, failover, memory/evictions, backend QPS.
- Sau phục hồi, **warm-up hot keys có giới hạn** để tránh avalanche do cache cold.

### Không nên làm

~~~text
Redis timeout
  -> catch Exception
  -> 10.000 requests cùng SELECT DB
  -> DB pool exhausted
  -> API timeouts, retry từ client
  -> thêm tải vào DB
~~~

Bắt exception không đủ. Fallback phải có **ngân sách tài nguyên** và xác định mức độ ưu tiên của từng endpoint.

### Cache operation failure

- **Redis GET lỗi:** quyết định fallback/fail theo SLO và độ nhạy nghiệp vụ.
- **Redis SET lỗi sau DB read:** có thể trả dữ liệu từ DB nếu hợp policy; báo metric cache populate failure.
- **Redis DEL lỗi sau DB commit:** không rollback transaction DB một cách tùy tiện; ghi outbox/retry invalidation và có TTL/mitigation.
- **Redis timeout không rõ kết quả write:** thao tác có thể đã thành công. Không dùng việc không nhận reply làm bằng chứng SET/DEL chưa xảy ra.
- **Redis failover:** client cần tự reconnect theo cơ chế hỗ trợ; dữ liệu cache/locks có thể thay đổi.

## 23. Eviction, memory và cache hot keys

Redis có memory limit và eviction policies tùy service/configuration. Cache hit ratio không chỉ do TTL; khi thiếu RAM, Redis có thể **evict keys** trước TTL, tạo nhiều misses và stampede.

### Đánh giá memory

1. Số unique keys thực sự được truy cập trong cache window.
2. Serialized item size, metadata/version, key length và overhead Redis.
3. Tỷ lệ hit/miss, eviction count và keyspace size.
4. Memory fragmentation/allocator behavior theo metric có sẵn.
5. Kích thước hot set và phân bố theo tenant.
6. Failover/restart behavior và warm-up time.
7. Chi phí nâng RAM/SKU so với giảm dữ liệu hoặc TTL.

### Một hot key có thể gây CPU/network bottleneck ở Redis

Ngay cả cache hit 100%, một key rất hot có thể tạo **network bandwidth/CPU contention**, nhất là value lớn và hàng chục nghìn GET/s. Cân nhắc:

- Local near-cache TTL rất ngắn cho read-only data phổ biến.
- Giảm kích thước serialized value.
- Chia tải/replica caching theo khả năng Redis service và consistency policy.
- CDN hoặc HTTP caching khi dữ liệu public.
- Hạn chế per-client QPS và requests dạng bot.
- Tối ưu HTTP endpoint để không decode JSON lớn mỗi request.

**Local near-cache** cần chiến lược invalidation riêng; không áp dụng cho dữ liệu phải cập nhật ngay chỉ vì muốn giảm Redis QPS.

## 24. Security: không biến cache thành điểm rò rỉ dữ liệu

Cache thường chứa dữ liệu mà nhiều services cùng truy cập. Bảo mật cần xét **network, authentication, tenant isolation và data retention**.

### Checklist

1. Dùng TLS và xác minh hostname/certificate.
2. Ưu tiên truy cập private khi loại Azure Redis service/SKU hỗ trợ; kiểm tra DNS, route, VNet integration.
3. Dùng Microsoft Entra authentication/managed identity khi **được sản phẩm/SDK hỗ trợ**, hoặc credential/ACL được quản trị theo policy.
4. Không nhúng password/access key trong source, build logs, container images hoặc command line.
5. Quản lý secret trong Azure Key Vault/secret store được phê duyệt; rotate và test reconnect.
6. Phân quyền Redis theo ứng dụng và môi trường, tránh chia sẻ credential toàn quyền.
7. Key có scope theo tenant và dữ liệu được ủy quyền; **cache hit không thay authorization**.
8. Không lưu token, số thẻ hoặc personal data không cần thiết trong Redis.
9. Chọn TTL/retention phù hợp quy định, bao gồm dữ liệu từng khách hàng.
10. Redact request logs, cache keys, diagnostic traces và connection strings.
11. Hạn chế các lệnh vận hành nguy hiểm như `FLUSHALL`, `KEYS *` trên production qua policy và quyền phù hợp.
12. Có audit và owner cho thao tác thay đổi Redis access/config.

### Phân biệt 401/403 với cache miss

Nếu ứng dụng đọc cache theo một key không có tenant/authorization scope, có thể trả dữ liệu của người khác. Phải xác thực request và kiểm tra quyền trước khi dùng dữ liệu cache. **Một cache hit hợp lệ về kỹ thuật không chứng minh caller có quyền xem object**.

## 25. Theo dõi cache-aside và cache stampede

Các metrics quan trọng:

| Metric | Mục đích |
|---|---|
| Cache hit count/rate | Đo tỷ lệ tránh được DB reads |
| Cache miss count/rate | Phát hiện cold cache/evictions/TTL |
| Cache lookup p50/p95/p99 | Xem Redis/client network latency |
| Cache populate success/failure | Biết có nạp lại được không |
| DB loads per key/window | Đo stampede trực tiếp |
| Singleflight followers/leaders | Coalescing có giảm recomputes không |
| Lease acquisition success/contended | Quan sát distributed coordination |
| Lease wait duration/expiry | Có lock timeout/hung loaders không |
| Stale served count và age | Dữ liệu cũ được phục vụ bao lâu |
| Eviction/expired keys | Memory pressure và TTL distribution |
| Backend DB QPS/CPU/latency | Cache miss có bảo vệ backend không |
| Redis connections/CPU/memory/network | Cache service có bị nghẽn không |
| API 5xx/429 và p95 latency | Mức ảnh hưởng đến người dùng |
| Business correctness metrics | Đơn hàng/giá/tồn kho có lệch không |
| Cache cost + DB cost | Tổng chi phí tối ưu có thực giảm không |

### Hit ratio không đủ

~~~text
1.000.000 requests
  999.000 cache hits
  1.000 misses

Hit ratio = 99,9%
~~~

Nhìn qua có vẻ tốt, nhưng nếu **1.000 misses xuất hiện trong 100 ms** cho cùng hot key, backend vẫn có thể bị đánh sập. Cần đo **miss burst, per-key DB load amplification và tail latency**, không chỉ average hit ratio.

### Không tạo high-cardinality metrics

Không gắn mỗi product ID/user ID/trace ID làm label cho time-series metric vô hạn. Dùng route, cache namespace, status/operation, environment/region. Với khóa nóng cụ thể, có thể dùng **sampled diagnostic logs hoặc top-N aggregate an toàn**, giới hạn quyền và giữ không quá lâu.

## 26. Azure Monitor, Application Insights và Redis diagnostics

Có thể kết hợp:

- **Azure Monitor Metrics** ở resource Redis: memory, CPU, connection, operations, evictions, latency/throttling theo khả năng product.
- **Application Insights/OpenTelemetry** trong Java API: Redis dependency spans, cache hit/miss custom metrics, DB dependency spans.
- **Azure SQL/Cosmos DB metrics**: DB CPU/DTU/vCore hoặc RU/s/429, latency và connection load theo dịch vụ.
- **Log Analytics**: platform logs và application logs được cấu hình về workspace.
- **Azure Service Health/Resource Health**: tín hiệu sự cố ở dịch vụ/nền tảng khi có.
- **Cost Management**: chi phí cache SKU, database, compute, network và log ingestion.

Tùy dịch vụ Redis trên Azure, **tên resource type, metric và dimensions khác nhau**. Phải mở metric definitions ở đúng resource; không lấy tên metric của Azure Cache for Redis rồi dùng nguyên xi cho Azure Managed Redis.

### Lệnh Azure CLI chỉ đọc

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table

REDIS_ID="<EXISTING_AZURE_REDIS_RESOURCE_ID>"

az resource show \
  --ids "$REDIS_ID" \
  --query "{id:id,name:name,type:type,location:location,sku:sku}" \
  --output json

az monitor metrics list-definitions \
  --resource "$REDIS_ID" \
  --output table
~~~

Chỉ sau khi có **metric name hợp lệ** hãy dùng `az monitor metrics list` với time range/dimensions phù hợp. Không in credentials, connection strings hoặc secrets từ resource properties. Lệnh đọc resource không chứng minh Redis đã được ứng dụng kết nối thành công.

### Alert có hành động

1. Redis hit rate giảm đột ngột **kèm DB QPS tăng**.
2. Redis evictions/memory pressure tăng.
3. Cache populate failure hoặc Redis GET timeout vượt ngưỡng.
4. Stampede amplification (DB loads cùng key trong vài giây) tăng.
5. Stale age vượt giới hạn nghiệp vụ.
6. Redis connection pool bị cạn hoặc reconnect/failover liên tục.
7. API p95/p99 tăng và database saturation.
8. Chi phí Redis tăng nhưng backend query cost/latency không giảm tương xứng.

Cảnh báo nên bao gồm người chịu trách nhiệm, runbook, link dashboard, môi trường và chỉ dấu deployment gần nhất; tránh chỉ báo 1 lỗi GET mà đánh thức cả đội trực.

## 27. Đo hiệu quả: công thức hit ratio, amplification và chi phí

### Hit ratio

~~~text
HitRatio = CacheHits / (CacheHits + CacheMisses)
~~~

Nếu 9.200 hits và 800 misses, hit ratio = **92%**. Nhưng cách đếm cần nhất quán: negative hits có tính hit hay không? Redis timeout có tính miss hay error? Đồng bộ định nghĩa trước khi so release.

### DB amplification khi stampede

~~~text
Expected source loads for one expired key:
  without protection  ≈ number of concurrent misses
  with local singleflight ≈ number of API replicas that miss
  with effective distributed coalescing ≈ 1 loader (không bảo đảm tuyệt đối)
~~~

Ví dụ 12 pods, mỗi pod có 50 requests cùng miss key:

- Không singleflight: có thể tới khoảng **600 source reads**.
- Singleflight trong từng pod: có thể còn khoảng **12 reads**.
- Có lease phối hợp tốt và healthy Redis: có thể còn gần **1 read** trong một refresh wave.

Con số minh họa, không phải SLA. Nếu lock timeout, failover hoặc loader lỗi, số source reads có thể lớn hơn.

### Ước lượng latency trung bình

~~~text
AverageLatency ≈ HitRatio × CacheHitLatency
               + (1 - HitRatio) × MissEndToEndLatency
~~~

Giả sử hit 95%, cache path 3 ms, miss path 45 ms:

~~~text
≈ 0,95 × 3 + 0,05 × 45 = 5,10 ms
~~~

Công thức minh họa không đủ đánh giá **p95/p99**, network queues, refresh contention hoặc phân phối tail; stampede có thể làm latency p99 tăng rất mạnh dù average gần như không đổi.

### Total cost

~~~text
TotalCost =
  Azure-managed Redis capacity + network
  + API/worker compute
  + DB query/storage cost
  + monitoring/logging
  + invalidation/refresh overhead
  + engineering/operations risk
~~~

Một Redis cluster lớn hơn có thể tốn thêm phí cố định nhưng giảm DB reads đủ để **tổng cost thấp hơn**. Ngược lại, một cache có hit 15%, dữ liệu ít tái sử dụng và chi phí quản trị cao có thể không đáng dùng.

## 28. Load test cache stampede có kiểm soát

### Chuẩn bị

- Staging/lab có Redis và database riêng, không dùng production.
- Dataset gần thực tế và có một số hot keys.
- Cấu hình load generator với RPS/concurrency giới hạn.
- Metrics hit/miss, DB QPS, Redis CPU/memory, API latency, errors và refresh count.
- Rate limiting/circuit breaker để bài test không đánh sập tài nguyên khác.
- Đồng bộ mốc thời gian UTC, ghi version build và cache policy.

### Kịch bản A — Baseline cache-aside

1. Làm warm một key bằng GET đầu tiên.
2. Gửi 100–500 RPS trong phạm vi lab được phép.
3. Đo hit ratio/DB reads và latency.
4. Xác minh key TTL có giá trị dương và serialization đúng.
5. Ghi kết quả baseline.

### Kịch bản B — Cache expiry stampede

1. Chờ TTL hoặc chỉ xóa **key lab cụ thể** (không dùng FLUSHALL).
2. Cho 100 requests đồng thời vào cùng hot key.
3. Đo bao nhiêu lần repository thật được gọi.
4. Đo DB CPU/latency và API p95/p99.
5. Kiểm tra việc populate cache/response có cùng business version.

### Kịch bản C — Singleflight

1. Bật singleflight trong từng API instance.
2. Chạy lại cùng test với một JVM.
3. Chạy lại với nhiều replicas.
4. Xác nhận local suppression giảm DB loads/instance nhưng không hứa chỉ còn một load toàn cluster.
5. Theo dõi follower timeout, exception propagation và memory của in-flight map.

### Kịch bản D — Distributed lease

1. Thêm Redis per-key lease + token + TTL + Lua release.
2. Chạy nhiều replicas và re-check cache sau acquire.
3. Chèn delay vào repository để mô phỏng loader chậm.
4. Kiểm tra lease hết hạn không xóa nhầm lock owner mới.
5. Kiểm tra followers không đồng loạt fallback DB.
6. Kiểm tra stale overwrite race khi writer cập nhật DB giữa lúc loader đọc và set.
7. Nếu correctness yêu cầu, bổ sung version guard/transaction policy.

### Kịch bản E — Redis unavailable

1. Trong lab, mô phỏng timeout/mất kết nối Redis.
2. Xác minh bounded fallback thay vì tất cả requests gọi DB.
3. Kiểm tra API status/latency và circuit breaker.
4. Phục hồi Redis, warm hot keys với rate limit.
5. Đo thời gian hồi phục và database surge.

**Chỉ thực hiện mô phỏng lỗi trên tài nguyên thử nghiệm được cấp phép.** Không kill Redis production, không thay public networking/credentials và không chạy `FLUSHALL` trên môi trường chia sẻ.

## 29. Case study: trang sản phẩm và checkout

### Bối cảnh

Một nền tảng bán lẻ chạy Java API trên Azure Container Apps, Azure SQL lưu catalog và đơn hàng, Redis managed cache trước các reads.

- Product detail: 8.000 GET/s tại đỉnh, 3% sản phẩm chiếm 70% lượt xem.
- Catalog update: vài lần/phút.
- Checkout: phải xác minh giá và tồn kho đúng thời điểm commit.
- Redis TTL dùng 10 phút cho product display.
- Khi khuyến mãi bắt đầu, top product hết hạn và DB CPU tăng 95%.

### Phân tích

1. **Cache hit rất cao chưa đủ:** một key hết hạn vẫn kích hoạt nhiều loaders.
2. TTL đúng 600s cho 10.000 keys nạp cùng lúc gây avalanche.
3. Một hot key top product cần **singleflight + distributed coalescing** hoặc stale-serving.
4. Giá hiển thị có thể chấp nhận stale ngắn, nhưng checkout cần kiểm tra DB authoritative.
5. Writer update sản phẩm rồi invalidate cache có race với loader; cần version-aware strategy hoặc staleness policy.
6. Nếu Redis mất kết nối, không cho 8.000 RPS trực tiếp đổ về SQL.

### Thiết kế khuyến nghị để thử nghiệm

- **Product detail:** cache-aside + soft/hard TTL, singleflight, selective per-key lease, negative caching ngắn và TTL jitter.
- **Catalog writer:** commit DB trước, phát outbox event/invalidate, tránh stale overwrite theo mức freshness mục tiêu.
- **Checkout:** transaction/conditional update DB; idempotency key, không tin cache để trừ kho.
- **Security:** tenant scope theo request identity, Redis private/TLS/managed credentials.
- **Observability:** hit/miss, refresh tasks, lock contention, stale age, SQL QPS, p95 latency và business correctness.
- **Cost:** so Redis SKU, SQL read capacity, API compute và monitoring.

~~~mermaid
flowchart LR
  U["Web/Mobile"] --> API["Java API"]
  API --> R["Redis cache: product display"]
  API --> SQL["Azure SQL: authoritative product/order"]
  SQL --> O["Transactional outbox"]
  O --> BUS["Service Bus event"]
  BUS --> INV["Cache invalidator"]
  INV --> R
  API --> OBS["Azure Monitor / App Insights"]
  R --> OBS
  SQL --> OBS
~~~

### Failure drill

- **Redis cold restart:** giới hạn fallback, warm top-N keys, kiểm tra recovered hit ratio.
- **DB update trong lúc loader đang đọc v1:** xác minh stale overwrite không vượt policy; nếu yêu cầu nghiêm ngặt, thêm version guard.
- **Invalidation event bị giao lại:** handler xóa/cache refresh idempotent.
- **Redis lease hết hạn:** worker cũ không release lock mới; không tạo side effect nghiệp vụ ngoài DB.
- **High traffic từ bot:** validation, WAF/APIM rate limit, negative caching và cache-key cardinality monitoring.

## 30. Bảng troubleshooting thực tế

| Triệu chứng | Nguyên nhân thường gặp | Cách điều tra/khắc phục |
|---|---|---|
| Hit rate thấp | TTL quá ngắn, key quá chi tiết, serialization mismatch | Top keys, key builder, TTL, traffic reuse |
| DB QPS vọt lên theo chu kỳ | Hot key hết TTL, cache avalanche | Plot miss spikes, TTL distribution, singleflight/jitter |
| Nhiều DB loads cùng key | Stampede | Per-key load metric, double-check, coalescing |
| Không đạt hiệu quả với 20 pods | Singleflight chỉ ở từng JVM | Distributed lease/stale-serving nếu cần |
| Redis lock không được giải phóng | Process lỗi, Lua/TTL/permission | Lease expiry, token compare, lock metrics |
| Worker cũ xóa lock của worker mới | Dùng DEL vô điều kiện | Atomic token-check release |
| Dữ liệu cũ xuất hiện lại sau update | Loader stale set sau DEL | Version/generation/fencing hoặc strong source read |
| Người dùng thấy giá/tồn kho cũ | TTL/invalidation không phù hợp semantics | DB verify tại checkout, version, shorter stale policy |
| 404 vẫn tiếp tục tốn DB queries | Không negative cache/keys random | Negative TTL, validation, rate limit |
| Product vừa tạo vẫn 404 | Negative cache chưa invalidate | Xóa sentinel khi create, TTL ngắn |
| Redis memory cao và evictions | Value quá lớn, key cardinality, TTL quá dài | Sizing, key cleanup, compress khi hợp lý |
| Redis CPU cao dù hit tốt | Hot key/QPS rất cao, value lớn | Near-cache có TTL phù hợp, limit, trim value |
| Redis timeout tạo DB outage | Fallback không giới hạn | Bulkhead, circuit breaker, load shedding |
| API 5xx sau Redis failover | Reconnect/TLS/DNS/client pool không đúng | SDK diagnostics, network path, timeout/retry |
| Cache dính dữ liệu tenant khác | Thiếu tenant/authorization trong key | Sửa key scope + authorization, incident response |
| Cloud bill tăng sau thêm cache | Redis fixed capacity vượt giá trị giảm DB | Cost comparison, hit ratio, rightsize |
| Redis metrics trống | Sai resource type, metric name, quyền | List metric definitions, resource health, agent |
| Invalidation bị mất | App crash sau DB commit hoặc pub/sub không bền | Transactional outbox + durable event, TTL bound |

### Thứ tự tìm nguyên nhân

1. Xác định endpoint/key namespace/region/time window.
2. Kiểm tra hit/miss/error breakdown, không trộn cache miss với Redis timeout.
3. Đo concurrent DB loads per key.
4. Xem Redis expiry/evictions/failover và client pool.
5. Xem DB QPS, CPU, RU/s, locks hoặc query latency tương ứng.
6. Kiểm tra release thay TTL, key format, serialization hoặc invalidation.
7. Mô phỏng race trong staging.
8. Khắc phục theo policy freshness/SLO; xác minh hệ thống và chi phí.

## 31. Bài thực hành tổng hợp

> **An toàn:** chỉ tạo và thao tác trên Redis/SQL/Cosmos DB **lab** có quyền sử dụng. Test tải, purge keys và tạo Azure resources có thể làm phát sinh phí. Không chạy lệnh xoá dữ liệu diện rộng, tắt cache sản xuất hoặc truy xuất secrets của tenant thật.

### Phần A — Thiết kế

1. Chọn một endpoint `GET /products/{id}` và source of truth là Azure SQL hoặc Cosmos DB.
2. Vẽ cache-aside read path: hit/miss/populate/return.
3. Thiết kế key gồm namespace, environment, tenant, productId và schema version.
4. Chọn positive TTL theo freshness SLO.
5. Chọn negative TTL và mô tả khi nào phải invalidate sentinel.
6. Chọn Redis managed resource phù hợp SKU/region/network bằng tài liệu hiện hành.
7. Xác định 5 metrics tối thiểu cho cache và DB.
8. Định nghĩa chính sách fallback nếu Redis unavailable.

### Phần B — Java cache-aside

1. Thêm Spring Data Redis/Jackson/repository dependencies theo phiên bản được chấp thuận.
2. Viết `ProductDto` và `ProductRepository`.
3. Triển khai GET cache-first, DB fallback, JSON serialize và TTL.
4. Triển khai update DB commit rồi cache invalidation; ghi chú race.
5. Test positive hit, miss, negative hit, malformed JSON, Redis timeout.
6. Đo cache lookup/DB dependency spans bằng OpenTelemetry/Application Insights.
7. Không để authorization phụ thuộc cache hit/miss.

### Phần C — Stampede

1. Warm top product key.
2. Xóa **riêng key lab** hoặc chờ TTL.
3. Phát 100 concurrent GETs trong giới hạn có thể kiểm soát.
4. Đếm bao nhiêu lần repository được gọi.
5. Thêm singleflight Java rồi test lại trên một instance.
6. Tăng lên nhiều replicas, đo số loaders.
7. Nếu cần, triển khai Redis lease/token/Lua release.
8. Re-check cache sau lock; followers bounded wait.
9. So sánh số DB loads, API p95 và error rate trước/sau.
10. Kiểm tra lease expiry và stale overwrite race.

### Phần D — Freshness và vận hành

1. Thêm TTL jitter cho nhiều keys, chứng minh expiries phân tán.
2. Thêm soft/hard TTL cho dữ liệu hiển thị, cấm stale ở checkout.
3. Thực hiện update sản phẩm khi cache đang refresh, đối chiếu DB version.
4. Mô phỏng Redis timeout, kiểm tra fallback có giới hạn.
5. Dùng Azure CLI đọc Redis resource và metric definitions.
6. Tạo dashboard hit ratio, DB QPS, Redis evictions, stampede count, stale age.
7. Xây alert khi backend reads tăng đột biến sau cache expiry.
8. Tính tác động tới tổng chi phí Redis+DB+compute.
9. Viết runbook xử lý cache cold start/failover và invalidation lost.
10. Dọn resources lab theo quy trình; không xóa resources được chia sẻ.

### Câu hỏi tự kiểm tra

**Câu 1.** Cache-aside khác read-through và write-through ở đâu?

**Câu 2.** Vì sao cache-aside coi database là source of truth mà không coi Redis là bản sao luôn đúng?

**Câu 3.** Nếu 1.000 requests cùng miss hot key, stampede xảy ra như thế nào?

**Câu 4.** Cache stampede khác cache avalanche và cache penetration ra sao?

**Câu 5.** TTL jitter ngăn nhiều keys hết hạn đồng thời; nó có tự ngăn 10.000 requests miss một key không?

**Câu 6.** Singleflight trong Java chặn được bao nhiêu loaders khi hệ thống có 20 replicas?

**Câu 7.** Tại sao sau khi lấy distributed lock phải GET cache thêm một lần?

**Câu 8.** Vì sao Redis lock cần token riêng và Lua compare-and-delete khi release?

**Câu 9.** Nếu Redis lease hết hạn trước khi loader hoàn thành, còn những race nào?

**Câu 10.** Tại sao Redis lease không đủ để bảo đảm exactly-once transaction?

**Câu 11.** Soft TTL/hard TTL có ích ở endpoint nào? Khi nào tuyệt đối không nên serve stale?

**Câu 12.** Negative caching có thể gây stale 404 sau khi tạo mới item như thế nào?

**Câu 13.** Vì sao writer commit DB rồi xóa cache vẫn có nguy cơ loader cũ set lại value stale?

**Câu 14.** Versioned key/conditional write giúp gì và cần nguồn version đáng tin cậy thế nào?

**Câu 15.** Outbox/invalidation event giảm rủi ro ứng dụng crash sau DB commit ra sao?

**Câu 16.** Redis failover ảnh hưởng điều gì tới lock state và cache warm-up?

**Câu 17.** Cache hit ratio 99,9% có đủ chứng minh không có stampede hay không?

**Câu 18.** Tại sao không gắn productId/userId vào mọi metric dimension?

**Câu 19.** Nếu Redis down, tại sao fallback DB không giới hạn có thể tạo cascading failure?

**Câu 20.** Trong một ứng dụng nhiều tenant, cache key và authorization phải được thiết kế thế nào?

**Câu 21.** Những yếu tố nào ảnh hưởng tổng chi phí khi bổ sung Redis vào kiến trúc Azure?

**Tiêu chí hoàn thành:** người học mô tả đúng cache-aside, viết được Java cache-first code, nhận diện stampede, phân biệt TTL jitter với singleflight, trình bày lease an toàn và các giới hạn, phân tích invalidation race, đặt freshness policy và có kế hoạch giám sát/fallback/benchmark.

## Kết luận

**Cache-aside** là cách sử dụng cache linh hoạt: ứng dụng đọc Redis trước, tải dữ liệu từ nguồn chuẩn khi miss rồi cập nhật cache với TTL phù hợp. Nó có thể giảm mạnh database reads và cải thiện latency cho API Java trên Azure, nhưng chỉ khi cache key, TTL, serialization, invalidation và phân quyền được thiết kế nhất quán.

**Cache stampede** cho thấy một cache hit ratio cao chưa đủ bảo vệ backend: đúng lúc hot key hết hạn, hàng trăm hoặc hàng nghìn request có thể đồng thời tái nạp dữ liệu. Có thể giảm rủi ro bằng **singleflight trong JVM, per-key distributed lease, TTL jitter để chống avalanche, soft/hard TTL với stale-while-revalidate, refresh-ahead, negative caching và bounded fallback**. Điều quan trọng hơn là hiểu **read/write races, lease expiry, Redis failover và giới hạn consistency**: không dùng cache lock thay cho transaction nghiệp vụ. Trên Azure, kết hợp Redis có quản trị, private networking/identity, Azure Monitor, Application Insights, backup/runbook ở nguồn dữ liệu và Cost Management giúp hệ thống có thể mở rộng mà vẫn bảo vệ dữ liệu và kiểm soát chi phí.

