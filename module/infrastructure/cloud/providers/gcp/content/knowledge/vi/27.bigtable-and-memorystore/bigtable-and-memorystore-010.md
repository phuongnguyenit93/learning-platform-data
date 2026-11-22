# Cache-aside, TTL, eviction và phòng cache stampede

> **Chương:** Bigtable và Memorystore  
> **Bài học:** Cache-aside, TTL, eviction và phòng cache stampede  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu Google Cloud từ project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; qua các tình huống triển khai biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Với ứng dụng Java thường xuyên đọc cùng dữ liệu, **Memorystore** là lớp cache in-memory giúp giảm độ trễ và số lần truy vấn kho dữ liệu gốc như **Bigtable**. Tuy vậy, một cache cấu hình sai có thể gây **dữ liệu cũ, Redis hết bộ nhớ, lỗi lan truyền và đột biến lưu lượng khi nhiều key hết hạn**.

Bài tập trung vào bốn khái niệm liên kết chặt chẽ:

- **Cache-aside:** ứng dụng tự đọc cache trước, nếu miss thì lấy từ nguồn dữ liệu và nạp cache.
- **TTL (time to live):** khoảng thời gian một cache entry được xem là còn hiệu lực về mặt lưu trữ.
- **Eviction:** Redis chủ động loại key khi tiến sát giới hạn bộ nhớ theo chính sách `maxmemory-policy`.
- **Cache stampede:** nhiều request đồng thời thấy cache miss/hết hạn cho cùng hot key rồi cùng đánh vào backend.

Kiến trúc ví dụ là **Java Orders API trên Cloud Run → Memorystore for Redis → Bigtable**. Bigtable giữ bản ghi bền vững; Redis chỉ là **dữ liệu dẫn xuất, có thể mất và tái tạo**. Một số mẫu áp dụng tương tự cho Cloud SQL, Firestore hoặc AlloyDB. Không dùng cache làm sổ cái thanh toán, nguồn quyết định tồn kho hoặc bằng chứng quyền truy cập duy nhất.

**Phạm vi:** minh họa chủ yếu **Memorystore for Redis (non-cluster)**; **Memorystore for Redis Cluster** và **Memorystore for Valkey** có những khác biệt về cấu hình, kết nối, HA, mở rộng và IAM. Đối chiếu tài liệu đúng sản phẩm trước khi dùng lại lệnh. Các lệnh tạo/xóa tài nguyên có thể phát sinh phí; chỉ thử trong sandbox được phê duyệt.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Vẽ luồng **cache hit, cache miss, refresh, write-invalidate** và xác định Bigtable là nguồn sự thật.
2. Chọn dữ liệu nên cache, đặt **cache key theo tenant/version** và giới hạn kích thước payload.
3. Phân biệt **TTL expiration** với **memory eviction**, đọc các chính sách `volatile-*`, `allkeys-*` và `noeviction`.
4. Thiết kế **TTL có jitter**, negative caching, soft TTL/hard TTL và stale-while-revalidate khi nghiệp vụ cho phép.
5. Phân biệt **cache stampede**, cache avalanche và cache penetration.
6. Giảm stampede bằng **local single-flight, distributed lease/lock, bounded waiting, request coalescing** và backpressure.
7. Dùng Redis `SET ... NX PX` và **compare-and-delete Lua** để tránh xóa nhầm lock của tiến trình khác; hiểu giới hạn khóa này.
8. Viết Java **Lettuce client** cache-aside có TTL jitter và chiến lược giới hạn đồng thời.
9. Thiết kế invalidation khi Bigtable cập nhật, tránh race condition và dữ liệu lỗi thời.
10. Theo dõi hit ratio, evicted keys, expired keys, memory pressure, độ trễ Bigtable và chi phí.

## 2. Kiến trúc cache-aside trên Google Cloud

~~~mermaid
flowchart LR
    Client["Web/Mobile/API caller"] --> Java["Cloud Run Java Orders API"]
    Java -->|"GET key"| Redis["Memorystore for Redis<br/>in-memory cache"]
    Redis -->|"HIT: value"| Java
    Redis -. "MISS / expired / evicted" .-> Java
    Java -->|"ReadRow(rowKey)"| BT["Cloud Bigtable<br/>source of truth"]
    BT -->|"canonical value + version"| Java
    Java -->|"SET key EX ttl"| Redis
    Java --> Client
    Mon["Cloud Monitoring/Logging<br/>p95, hit ratio, memory"] -.-> Java
    Mon -.-> Redis
    Mon -.-> BT
~~~

**Vì sao không đọc Bigtable cho mọi request?** Bigtable được thiết kế cho lượng dữ liệu lớn, truy cập theo row key/range và throughput cao; một số endpoint truy vấn **cùng hot row** hàng nghìn lần có thể tốn I/O, chi phí và tăng p99 latency. Cache giúp hấp thụ đọc lặp. Tuy nhiên, **Bigtable vẫn phải chịu được cache miss có kiểm soát**, còn Redis phải có phương án failover/fallback.

### 2.1. Chọn dữ liệu nào đưa vào cache?

| Dữ liệu | Có nên cache? | Điều kiện |
|---|---|---|
| Thông tin sản phẩm ít thay đổi | **Có** | TTL phút, invalidate khi cập nhật |
| Snapshot trạng thái đơn hàng đã hoàn tất | **Có, có điều kiện** | Giới hạn độ trễ chấp nhận, key có tenant/order |
| Metadata chỉ đọc từ Bigtable | **Có** | Row key rõ, kích thước nhỏ, thay đổi không quá thường xuyên |
| Bảng giá đang mở bán | **Có, nhưng kiểm soát freshness** | Event invalidation + version, TTL ngắn |
| Quyền truy cập người dùng | **Rất thận trọng** | Không để cache stale làm lộ dữ liệu; revalidate policy nhạy cảm |
| Số dư, lệnh chuyển tiền, tồn kho cần tính nhất quán nghiêm ngặt | **Không làm nguồn quyết định cuối cùng** | Đọc/ghi tại source với kiểm soát đồng thời |
| Payload hàng MB hoặc danh sách không giới hạn | **Không nên** | Tăng memory/network latency; cache snapshot có giới hạn |
| Kết quả tìm kiếm cá nhân hóa | **Có, nếu key bao gồm scope** | Tenant, filters, permissions/version và TTL ngắn |

**Quy tắc:** cache là bản sao có thể mất bất cứ lúc nào. Thiết kế nghiệp vụ **đúng ngay cả khi cache trả MISS liên tục**, nhưng áp giới hạn để nguồn gốc không bị đánh sập khi miss hàng loạt.

## 3. Quy trình cache-aside: đọc, ghi và nhất quán

### 3.1. Read path

~~~mermaid
sequenceDiagram
    participant C as Client
    participant J as Java API
    participant R as Redis
    participant B as Bigtable
    C->>J: GET /v1/orders/OD-42
    J->>R: GET orders:v1:tenantA:OD-42
    alt Cache hit
        R-->>J: Cached snapshot
    else Cache miss
        R-->>J: nil
        J->>B: ReadRow(tenantA#OD-42)
        B-->>J: Snapshot + version
        J->>R: SET key value EX 60
    end
    J-->>C: JSON response
~~~

Các bước:

1. Java xác thực người dùng/tenant **trước khi xác định cache key**.
2. Đọc Redis theo key đã namespace; nếu trả giá trị hợp lệ thì trả nhanh.
3. Nếu miss, truy vấn Bigtable bằng **row key truy cập hiệu quả**, không scan toàn bộ table.
4. Serialize payload với **schema/version rõ** và ghi Redis với TTL.
5. Nếu Redis gặp lỗi (timeout/network), **phân biệt lỗi cache với MISS**; có thể bypass cache nhưng phải giới hạn đồng thời và bảo vệ Bigtable.

Cache hit không loại bỏ kiểm tra quyền nghiệp vụ. **Không trả dữ liệu của tenant A cho tenant B** chỉ vì cả hai request có cùng order ID.

### 3.2. Write path: cập nhật nguồn rồi invalidate

~~~mermaid
sequenceDiagram
    participant J as Java Service
    participant B as Bigtable
    participant R as Redis
    J->>B: MutateRow canonical record
    B-->>J: Commit thành công
    J->>R: DEL orders:v1:tenantA:OD-42
    Note over R: Lần đọc sau là MISS và nạp lại
~~~

**Thứ tự mặc định:** **write Bigtable thành công → invalidate Redis**. Không cập nhật cache trước khi commit nguồn; nếu Bigtable thất bại, cache có thể quảng bá trạng thái chưa từng tồn tại.

**Cửa sổ lỗi cần nhận diện:** Bigtable commit thành công nhưng xóa Redis thất bại → giá trị cũ còn đến hết TTL. Cần retry/invalidation có kiểm soát, event/outbox phù hợp khi yêu cầu chặt. Giao dịch **Bigtable + Redis không nguyên tử**; không quảng bá giải pháp này có tính nhất quán mạnh xuyên hai dịch vụ.

### 3.3. Cache-aside khác write-through và write-behind

| Chiến lược | Bên nào ghi cache? | Đánh đổi |
|---|---|---|
| **Cache-aside** | Ứng dụng nạp trên miss | Đơn giản, kiểm soát rõ; first read chậm, phải invalidate |
| **Read-through** | Lớp cache tự load từ backing store | Client đơn giản, cần loader/proxy phù hợp |
| **Write-through** | Ghi nguồn và cache trong cùng flow | Freshness dễ kiểm soát hơn, tăng write latency; vẫn có partial failures |
| **Write-behind / write-back** | Ghi cache trước, đẩy nguồn sau | Write nhanh nhưng mất dữ liệu nếu cache hỏng/queue không bền vững |

Với Orders API cần bảo vệ dữ liệu bền vững, **cache-aside + source-first invalidation** thường là điểm bắt đầu dễ kiểm toán.

## 4. Thiết kế cache key và payload

### 4.1. Namespace theo tenant và schema

Ví dụ:

~~~text
orders:v1:tenantA:OD-42
products:v3:shopA:SKU-102
feed:v2:tenantA:status=PAID:page=1
not-found:v1:tenantA:OD-999
refresh-lock:v1:tenantA:OD-42
~~~

Một key tốt nên bao gồm:

- **Domain**, ví dụ `orders`, `products`.
- **Schema version**, ví dụ `v1`, để tránh deserialize payload cũ sau deploy.
- **Tenant / audience / quyền phù hợp**, tránh rò rỉ giữa khách hàng.
- **Business identifier** hoặc hash ổn định của các query parameters đã canonicalize.
- **Scope dữ liệu** (locale, currency, pagination, feature flags) nếu ảnh hưởng nội dung.

Không đưa **access token, password, số điện thoại, email cá nhân hoặc JSON chứa PII** trực tiếp vào key. Redis keys thường xuất hiện trong tooling/logs/metrics; nếu ID nhạy cảm, dùng HMAC/hash theo chính sách và không tái sử dụng key xuyên môi trường.

### 4.2. Payload có version

~~~json
{
  "schemaVersion": 1,
  "sourceVersion": 1042,
  "fetchedAt": "2026-11-19T03:00:00Z",
  "order": {
    "id": "OD-42",
    "tenantId": "tenantA",
    "status": "PAID"
  }
}
~~~

`sourceVersion` là phiên bản **do nguồn dữ liệu quản lý**, không phải thời điểm Redis ghi. Nếu hệ thống cần chống stale writer, version được dùng để **kiểm tra trước khi cập nhật cache**; chỉ thêm trường mà không so sánh thì không giải quyết race condition.

**Giới hạn kích thước** của một entry và tránh cache nguyên bản ghi Bigtable có nhiều columns/timestamps nếu endpoint chỉ cần vài fields. Serializing/deserializing JSON và chuyển dữ liệu qua mạng cũng có chi phí.

## 5. TTL: tuổi thọ cache và độ mới dữ liệu

**TTL** quy định thời gian key được giữ trước khi **expire**; Redis hỗ trợ `EX` (giây), `PX` (mili giây), `EXPIRE` và `TTL`/`PTTL` để xem thời gian còn lại.

~~~redis
SET orders:v1:tenantA:OD-42 '{"status":"PAID"}' EX 60
TTL orders:v1:tenantA:OD-42
GET orders:v1:tenantA:OD-42
~~~

Lưu ý:

- `TTL > 0`: số giây còn lại (có thể thay đổi).
- `TTL = -1`: key tồn tại **không có expiration**.
- `TTL = -2`: key **không tồn tại**.
- Redis có thể dùng **lazy expiration** khi truy cập hoặc **active expiration** nền; không suy Redis sẽ phát sự kiện/xóa key chính xác tại một mili giây tuyệt đối.
- Một lệnh `SET` thông thường **ghi đè giá trị đồng thời xóa TTL cũ** nếu không dùng `EX/PX/KEEPTTL` tương ứng. **Mỗi cache SET phải chủ động đặt TTL**.

### 5.1. Chọn TTL theo tính chất dữ liệu

| Loại dữ liệu | TTL ví dụ | Rủi ro |
|---|---|---|
| Product catalog ít thay đổi | 5–15 phút | Giá/thuộc tính có thể chậm cập nhật |
| Order status gần realtime | 10–60 giây | Khách hàng thấy trạng thái cũ nếu không invalidate |
| Thống kê dashboard | 1–5 phút | Không phù hợp kiểm toán/sổ cái chính thức |
| Kết quả **not found** | 5–30 giây | Tạo mới entity bị che trong thời gian ngắn |
| Dữ liệu theo phiên | Phụ thuộc yêu cầu bảo mật | Không lưu session/token như bản sao vô hạn |

Các con số chỉ là **khởi điểm thiết kế**, không phải khuyến nghị mặc định toàn hệ thống. TTL nên dựa trên **SLO freshness**, tần suất cập nhật, chi phí đọc nguồn, kích thước key và khả năng inval­i­date.

### 5.2. TTL jitter tránh hết hạn đồng loạt

Nếu 100.000 keys đều được tạo lúc 12:00 với TTL cố định 300 giây, rất nhiều key có thể hết hạn cùng lúc lúc 12:05 → **cache avalanche**.

Thay TTL cố định `300s` bằng TTL ngẫu nhiên trong một khoảng, ví dụ:

~~~text
baseTtl = 300 seconds
jitter  = random integer [-30, +30]
actualTtl = max(30, baseTtl + jitter)
~~~

Cách này **trải đều thời điểm expire**, nhưng vẫn phải theo **freshness budget**: nếu dữ liệu bắt buộc cũ không quá 300 giây, **không chọn jitter dương khiến max TTL vượt 300**. Khi đó dùng `actualTtl = baseTtl - random(0, 60)` hoặc soft/hard TTL.

**Không dùng cùng random seed/TTL mọi instance**; chọn jitter riêng mỗi key refresh hoặc theo hash ổn định có phân bố tốt.

### 5.3. Negative caching

Nếu API liên tục tìm `orders:OD-DOES-NOT-EXIST`, mỗi miss đều đánh Bigtable. Có thể cache sentinel **NOT_FOUND** trong **TTL rất ngắn**:

~~~text
GET orders:v1:tenantA:OD-404 → nil
Bigtable readRow → absent
SET orders:v1:tenantA:OD-404 __NOT_FOUND__ EX 10
Next request → trả 404 mà không gọi Bigtable
~~~

Phải phân biệt **“Bigtable xác nhận không có row”** với **“Bigtable timeout/403”**. Tuyệt đối không negative-cache lỗi mạng hoặc quyền như thể dữ liệu không tồn tại. Khi entity được tạo, invalidate sentinel; key luôn chứa tenant và các scope truy cập.

## 6. Eviction khác TTL expiration

**TTL expiration** liên quan **thời hạn key**; **eviction** xảy ra do **áp lực bộ nhớ** khi chạm `maxmemory` và có write mới. Key vẫn còn TTL có thể **bị evict sớm**, còn key không có TTL có thể chiếm chỗ lâu dài tùy policy.

Trong **Memorystore for Redis**, default `maxmemory-policy` là **`volatile-lru`**. Các lựa chọn quan trọng:

| Policy | Khi gần đầy bộ nhớ | Thích hợp |
|---|---|---|
| `volatile-lru` (**mặc định**) | Evict các key **có TTL**, ưu tiên key ít truy cập gần đây | Cache có TTL đồng nhất, giữ key không TTL theo ý đồ |
| `allkeys-lru` | Evict key LRU trong **toàn keyspace** | Pure cache, mọi key đều có thể tái tạo |
| `allkeys-lfu` | Evict key ít được sử dụng thường xuyên | Hot set ổn định theo tần suất |
| `volatile-lfu` | LFU chỉ trong các key có TTL | Khi có phân tách key tồn tại lâu/keys expirable |
| `volatile-ttl` | Ưu tiên key có **TTL còn lại ngắn nhất** | Khi business cho phép chọn theo thời gian còn lại |
| `allkeys-random` / `volatile-random` | Evict key ngẫu nhiên trên phạm vi tương ứng | Trường hợp đặc thù |
| `noeviction` | **Không evict**; write cần thêm bộ nhớ có thể lỗi | Dữ liệu không thể tùy tiện mất, nhưng không nên xem Redis như DB chính |

**Bẫy `volatile-lru`:** Nếu cache key **không đặt TTL**, nó không thuộc tập key có thể bị evict; khi không có key có TTL đủ điều kiện, write có thể nhận **OOM error**. Vì vậy với thuần cache-aside, hoặc **đặt TTL cho mọi key**, hoặc cân nhắc **`allkeys-lru`** sau benchmark.

Lựa chọn policy phải theo đúng **Memorystore for Redis / Redis Cluster / Valkey**, vì defaults và cách đặt `maxmemory` có thể khác. Các LRU/LFU Redis dùng thuật toán ước lượng/sampling, không đảm bảo sắp thứ tự tuyệt đối mọi key.

### 6.1. Bộ nhớ cấp instance khác cache payload

- **Instance capacity**: tài nguyên memory được cấp/phải trả phí.
- **`maxmemory-gb`** của Memorystore for Redis: ngưỡng dữ liệu cache trước khi eviction policy chạy. Mặc định bằng dung lượng instance.
- **System memory usage ratio**: bao gồm cả overhead/fragmentation; quan trọng hơn việc chỉ nhìn `used_memory`.
- **Eviction không bảo đảm xử lý kịp một đợt write cực lớn**; áp lực bộ nhớ và fragmentation có thể gây lỗi trước khi hệ thống kịp giải phóng.

Google Cloud khuyên cân nhắc **headroom**, theo dõi **system memory usage ratio** và có cảnh báo khi vượt **80%**. Có thể giảm `maxmemory-gb`, bật defragmentation ở phiên bản hỗ trợ hoặc scale instance sau khi đo. Đừng hạ ngưỡng hay đổi eviction policy trong production mà không dự toán tác động đến hit ratio và Bigtable load.

## 7. Ba kiểu “cache miss storm” khác nhau

| Hiện tượng | Nguyên nhân | Cách giảm |
|---|---|---|
| **Cache stampede** | Một **hot key** hết hạn, nhiều requests cùng miss và cùng load | Single-flight, lock/lease, stale-while-revalidate, bounded wait |
| **Cache avalanche** | **Nhiều keys** expire/evict cùng lúc hoặc cache cluster outage | TTL jitter, prewarming, resource headroom, circuit breaker |
| **Cache penetration** | Request lặp nhiều **key không tồn tại**, mỗi request gây DB lookup | Negative cache ngắn, input validation, rate limits, Bloom filter khi thật cần |

**Ví dụ stampede:** `products:v3:shopA:SKU-102` có 5.000 RPS, TTL hết hạn; một Bigtable read mất 30 ms. Nếu các request không coalesce, hàng trăm/hàng nghìn reads tới cùng row có thể tạo áp lực cao, tăng p99 và chi phí.

**Ví dụ avalanche:** một đợt deploy prewarm toàn bộ key vào lúc 12:00 với TTL 5 phút, đến 12:05 phần lớn keys miss. Jitter từng key giúp phân tán, nhưng không chữa được Redis outage hoàn toàn.

**Ví dụ penetration:** bot quét hàng triệu `orderId` không tồn tại; cần validate format, authorize trước khi query, negative caching giới hạn, rate limiting và tuyệt đối không cache 403 thành “not found” khi không đúng semantics.

## 8. Giảm stampede theo lớp: từ đơn giản đến nâng cao

### 8.1. Local single-flight

Trong **một Java instance**, dùng map `key -> CompletableFuture<Result>` để 100 threads cùng đọc một key **chỉ một thread đi Bigtable**; các thread còn lại chờ cùng future. Sau completion, **xóa entry trong finally/whenComplete**, nếu không sẽ thành memory leak hoặc cache trong RAM vô thời hạn.

**Giới hạn:** khi Cloud Run scale 10 instances, local single-flight có thể vẫn tạo **10 Bigtable reads**. Muốn coalesce toàn hệ thống cần phân tán qua Redis lease hoặc một service phối hợp.

### 8.2. Distributed lease với Redis

Redis có lệnh atomic:

~~~redis
SET refresh-lock:v1:tenantA:OD-42 random-token NX PX 15000
~~~

- `NX`: chỉ ghi khi lock key chưa tồn tại.
- `PX 15000`: lock hết hạn sau **15.000 ms**, tránh kẹt vô thời hạn khi instance crash.
- `random-token`: giá trị **độc nhất/khó đoán** cho mỗi lần acquire, để unlock không xóa nhầm lock mới.

Luồng:

~~~mermaid
sequenceDiagram
    participant A as Java instance A
    participant B as Java instance B
    participant R as Redis
    participant DB as Bigtable
    A->>R: GET hot-key → MISS
    B->>R: GET hot-key → MISS
    A->>R: SET lock token-A NX PX 15000 → OK
    B->>R: SET lock token-B NX PX 15000 → nil
    A->>DB: ReadRow hot row
    DB-->>A: Payload + source version
    A->>R: SET hot-key payload EX ttl
    A->>R: compare token then DEL lock
    B->>R: Poll GET hot-key → HIT
~~~

**Không dùng `DEL lock` đơn thuần:** nếu A bị dừng hơn 15 giây, lock hết hạn rồi B lấy lock mới, A tỉnh dậy và DEL có thể **xóa lock của B**. Unlock phải so token và xóa **atomically**.

### 8.3. Lua unlock an toàn hơn GET rồi DEL

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
~~~

Gọi bằng `EVAL script 1 lock-key token` hoặc thư viện client hỗ trợ. **Không tách thành GET và DEL** vì hai lệnh riêng bị race.

**Giới hạn thiết kế:** khóa `SET NX PX` chỉ là **lease coordination**, không phải distributed transaction chắc chắn. Nếu loader chạy lâu hơn TTL, nhiều tiến trình vẫn có thể cùng tải/cập nhật cache. Với write làm thay đổi nghiệp vụ, cần **fencing token và kiểm soát phiên bản tại source of truth**, không dùng Redis lock làm cơ chế bảo đảm duy nhất. Với dữ liệu dẫn xuất thuần cache, việc tính lại trùng đôi lúc chấp nhận được; vẫn phải bảo vệ backend.

### 8.4. Bounded wait và backpressure

Client không lấy được lock nên:

1. Chờ ngắn với **backoff + jitter** rồi kiểm tra Redis lại.
2. Nếu đã có dữ liệu, dùng cache hit.
3. Nếu vượt **waiting budget**, trả **503/Retry-After**, hoặc trả **stale snapshot trong cửa sổ được phép**, thay vì mọi request cùng bypass lock và đánh Bigtable.
4. Giới hạn concurrent Bigtable reads trên từng instance/toàn hệ thống, đặt timeout/circuit breaker.
5. Khi Redis bị outage, áp **bulkhead** cho fallback thay vì tạo unbounded connection storm.

**Không spin `GET` hàng triệu lần mỗi giây** khi chờ lock; nó có thể biến stampede Bigtable thành stampede Redis.

## 9. Soft TTL, hard TTL và stale-while-revalidate

Đối với catalog/feed nơi **chấp nhận dữ liệu hơi cũ**, có thể lưu metadata:

~~~json
{
  "value": {"sku": "SKU-102", "priceMinor": 129900},
  "softExpiresAt": 1795057200,
  "hardExpiresAt": 1795057260,
  "sourceVersion": 1042
}
~~~

- **Trước soft TTL:** trả cache bình thường.
- **Sau soft TTL nhưng trước hard TTL:** vẫn trả **stale** nhanh; chỉ một worker refresh nền.
- **Sau hard TTL:** không trả stale; chờ refresh có giới hạn hoặc báo tạm không khả dụng.
- Redis key có **physical TTL tới hard expiry** để giải phóng bộ nhớ; không xóa vật lý ở soft expiry.

**Cảnh báo:** stale-while-revalidate không phù hợp trạng thái thu hồi quyền, số dư, thanh toán, trạng thái khóa tài khoản hoặc quyết định tuân thủ phải mới tuyệt đối. Cần quy định **maximum staleness** rõ và audit. Trong Cloud Run, không tùy ý dựa vào thread nền sống mãi sau khi HTTP response trả về; dùng cấu hình CPU/lifecycle được hỗ trợ hoặc **Cloud Tasks/Pub/Sub** để refresh bền vững.

### 9.1. Hot-key prewarming

Với dữ liệu dự báo có traffic cao (sản phẩm khuyến mãi), có thể refresh trước khi soft TTL tới hạn. Tuy nhiên:

- Không tạo 100.000 refresh cùng lúc; dùng jitter/scheduling.
- Tránh refresh dữ liệu không còn được đọc: chỉ prewarm **hot set**.
- Không đặt TTL vĩnh viễn để chữa stampede; dễ tích tụ stale data và memory pressure.
- Nếu Redis failover mất entry, phải có fallback/rate limit khi prewarm lại.

## 10. Java Lettuce: cache-aside với TTL jitter và Redis lock

Ví dụ Java 17 minh họa API đọc **order snapshot từ Bigtable qua một repository**. Mã sẽ:

1. Kiểm tra cache theo tenant/order.
2. Trên miss, cố gắng acquire một lease `SET NX PX`.
3. Owner kiểm tra cache lần nữa, nạp nguồn, ghi Redis với TTL có jitter.
4. Owner chỉ release nếu đúng token.
5. Non-owner chờ có giới hạn; quá hạn trả lỗi tạm thời thay vì tự bắn thêm reads vào Bigtable.

**Phạm vi ví dụ:** kết nối Redis trong VPC sandbox, có thể dùng URI không TLS/Redis AUTH **chỉ khi instance lab được bảo vệ và cấu hình đó đúng**. Với production bật Redis AUTH/TLS theo khả năng sản phẩm và **cấu hình Lettuce TLS/certificate/password từ Secret Manager**, không gắn secret trong URI loggable. Mẫu này không thay thế optimistic version check khi cạnh tranh với writes.

### 10.1. Maven dependencies

Dự án có `pom.xml`, Java 17 và dependency Lettuce:

~~~xml
<dependencies>
  <dependency>
    <groupId>io.lettuce</groupId>
    <artifactId>lettuce-core</artifactId>
    <version>6.5.5.RELEASE</version>
  </dependency>
</dependencies>
~~~

`6.5.5.RELEASE` là một **phiên bản minh họa**, không phải lời khẳng định mới nhất; cần khóa phiên bản phù hợp JDK và quét CVEs trước production. Nếu dùng Spring Boot, có thể thay bằng **Spring Data Redis/RedisTemplate** cùng nguyên tắc cache-aside, TTL và mutex.

### 10.2. Java implementation

~~~java
package com.example.cache;

import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;
import io.lettuce.core.ScriptOutputType;
import io.lettuce.core.SetArgs;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;

public final class OrdersCache implements AutoCloseable {
    private static final String UNLOCK = """
        if redis.call("GET",KEYS[1]) == ARGV[1] then
          return redis.call("DEL",KEYS[1])
        end
        return 0
        """;

    private final RedisClient client;
    private final StatefulRedisConnection<String, String> connection;
    private final RedisCommands<String, String> redis;

    public OrdersCache(String host, int port) {
        // CHỈ LAB trong VPC cách ly. Production: TLS + AUTH + Secret Manager.
        RedisURI uri = RedisURI.create("redis://" + host + ":" + port);
        uri.setTimeout(Duration.ofSeconds(2));
        client = RedisClient.create(uri);
        connection = client.connect();
        redis = connection.sync();
    }

    public String getOrder(String tenant, String orderId,
                           Supplier<String> bigtableLoader)
                           throws InterruptedException {
        String key = "orders:v1:" + tenant + ":" + orderId;
        String lock = "refresh-lock:" + key;
        String value = redis.get(key);
        if (value != null) return value;

        String token = UUID.randomUUID().toString();
        String acquired = redis.set(lock, token,
                SetArgs.Builder.nx().px(15_000));

        if ("OK".equals(acquired)) {
            try {
                // Double-check: owner khác có thể vừa nạp dữ liệu.
                value = redis.get(key);
                if (value != null) return value;

                value = bigtableLoader.get(); // Source lookup, có timeout riêng.
                if (value != null) {
                    // TTL jitter 50–60s, không vượt budget 60s.
                    int ttl = 60 - ThreadLocalRandom.current().nextInt(11);
                    redis.setex(key, ttl, value);
                }
                return value; // null = không tìm thấy, không cache lỗi DB.
            } finally {
                // So token + xóa lock nguyên tử.
                redis.eval(UNLOCK, ScriptOutputType.INTEGER,
                        new String[] {lock}, token);
            }
        }

        // Không sở hữu lock: đợi owner, KHÔNG gọi Bigtable hàng loạt.
        for (int i = 0; i < 20; i++) {
            Thread.sleep(100 + ThreadLocalRandom.current().nextInt(50));
            value = redis.get(key);
            if (value != null) return value;
        }
        throw new IllegalStateException("Cache refresh in progress");
        // HTTP layer: map thành 503 + Retry-After, tùy SLO.
    }

    @Override public void close() {
        connection.close();
        client.shutdown();
    }
}
~~~

**Cách dùng trong Java service (rút gọn):**

~~~java
// Tạo OrdersCache như singleton bean, KHÔNG tạo trên mỗi request.
String value = ordersCache.getOrder(
    "tenantA", "OD-42",
    () -> orderRepository.readSnapshot("tenantA", "OD-42")
);
~~~

`orderRepository.readSnapshot(...)` là **hàm giả định** do ứng dụng hiện thực bằng Bigtable Java client; nó cần đọc đúng row key, serialize JSON, có timeouts và phân biệt **row không tồn tại** với lỗi 403/timeout. Mã trên là **minh họa đọc cache**, không phải một Spring Boot app hoàn chỉnh.

### 10.3. Các giới hạn phải cải thiện trước production

- **Đồng bộ:** một Redis connection sync dùng chung có thể gây nghẽn khi nhiều Java threads; benchmark và chọn async client/pooling theo workload, không mở kết nối mới mỗi HTTP request.
- **Timeout:** 15 giây lock chỉ là ví dụ; nếu Bigtable read p99 lâu hơn, lock có thể hết trước khi owner xong. Giới hạn load timeout và xem xét fencing/source version.
- **Unlock:** Redis hoặc mạng lỗi trong `finally` phải được log/giám sát; lock tự expire khi không release được. Không che exception nghiệp vụ bằng lỗi unlock.
- **Missing row:** mẫu không negative-cache `null`, nên hot missing key có thể thử lại sau mỗi wait; production thêm sentinel TTL ngắn theo mục 5.
- **Exception:** nếu Redis GET/SET timeout, thêm **circuit breaker + bounded Bigtable fallback**; không cho toàn bộ Java request fan out đến nguồn.
- **Data stale:** sau khi Bigtable mutate, phải invalidate và kiểm soát race trước khi cache fill.
- **Security:** validate tenant/order ID; không dùng raw user input chưa chuẩn hóa trong key và không cache response khác scope.
- **Observability:** thêm cache hit/miss, lock contention, wait budget, Bigtable fetch latency và Bigtable read QPS.
- **Thử failure:** lock owner crash, lock expiry, Redis outage, Bigtable timeout, concurrent write, deploy rolling và failover.

**Một lưu ý:** nếu source không tồn tại, owner trả `null` nhưng người chờ không thấy key; đây là trường hợp cần **negative caching với sentinel riêng**, không phải lý do để không kiểm soát concurrency.

## 11. Race condition: giá trị cũ nạp đè cache mới

Xem tình huống:

~~~text
A: Cache MISS → bắt đầu Bigtable read (v1)
B: Update Bigtable lên v2 → DEL cache
B: Request mới đọc v2 → SET cache = v2
A: Bigtable read v1 hoàn tất muộn → SET cache = v1
Kết quả: cache lại chứa dữ liệu cũ dù update đã invalidate.
~~~

**Distributed lock cho cache miss không đủ để chặn sự cố này** nếu luồng write/invalidation không tuân cùng cơ chế/version. Cách xử lý tùy yêu cầu:

1. **Chấp nhận bounded stale:** TTL ngắn và business cho phép trễ; áp cho catalog không nhạy cảm.
2. **Versioned cache entries:** mọi snapshot mang **sourceVersion**, refresh/invalidation chỉ được chấp nhận nếu version mới không nhỏ hơn version đang có; dùng **atomic compare** tại Redis.
3. **Generation keys:** thay namespace key theo version/generation do source ghi bền vững; readers cần cách xác định version đáng tin.
4. **Event invalidation:** sau source commit, publish event (kèm version), consumer xóa/đánh dấu stale; phải chịu event lặp/out-of-order.
5. **Strong consistency route:** với order/payment quan trọng, đọc nguồn trực tiếp hoặc xác minh version/authorization, không dựa cache.

**Không nghĩ “xóa cache sau write” là bằng chứng nhất quán tuyệt đối.** Nếu update/invalidation thất bại giữa Bigtable và Redis hoặc hai tiến trình race, stale vẫn có thể quay lại. Với Bigtable, cập nhật **một row** có thể thực hiện atomically; đừng mở rộng giả định đó thành transaction xuyên nhiều rows và Redis.

## 12. Vận hành Memorystore: tạo, cấu hình, kết nối, dọn lab

**Các lệnh dưới đây chỉ để học trên sandbox**. Chúng có thể tạo Redis instance tính phí liên tục. Nếu đã có instance lab thuộc sở hữu nhóm, ưu tiên quan sát/read-only trước thay vì tạo mới.

### 12.1. Kiểm tra kết nối và cấu hình

~~~bash
gcloud auth list
gcloud config get-value project

gcloud redis instances list \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud redis instances describe cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Quan sát `host`, `port`, `tier`, `memorySizeGb`, `authorizedNetwork`, `redisConfigs`, trạng thái và policy. **Không in AUTH string/password** ra log hoặc tài liệu học.

### 12.2. Tạo một Basic Tier instance minh họa

~~~bash
# CHỈ chạy trong project sandbox đã có VPC được phê duyệt.
gcloud redis instances create cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --size=1 \
  --tier=basic \
  --network=projects/PROJECT_ID/global/networks/VPC_NAME \
  --redis-config=maxmemory-policy=allkeys-lru
~~~

Đây là **Memorystore for Redis** (non-cluster), không phải Redis Cluster hoặc Valkey. Mạng `VPC_NAME` phải tồn tại, IP range/peering/Private Service Access phải hợp lệ với chế độ kết nối. Basic Tier chỉ phù hợp demo; production thường cân nhắc **Standard Tier HA**, nhưng HA không đồng nghĩa dữ liệu cache sẽ không bao giờ mất.

Nếu sử dụng **Private Services Access**, cần cấu hình VPC/service networking trước theo hướng dẫn; không tạo instance trên VPC production chỉ để thử.

### 12.3. Quan sát eviction và TTL bằng redis-cli

**Chạy `redis-cli` từ VM/GKE/workload có đường VPC tới private endpoint**; Cloud Shell hoặc laptop **không mặc nhiên** kết nối được private IP của Memorystore.

~~~bash
# Lấy INSTANCE_HOST và INSTANCE_PORT từ gcloud describe.
redis-cli -h INSTANCE_HOST -p INSTANCE_PORT PING

redis-cli -h INSTANCE_HOST -p INSTANCE_PORT \
  SET orders:v1:tenantA:OD-42 '{"status":"PAID"}' EX 60

redis-cli -h INSTANCE_HOST -p INSTANCE_PORT \
  TTL orders:v1:tenantA:OD-42

redis-cli -h INSTANCE_HOST -p INSTANCE_PORT \
  GET orders:v1:tenantA:OD-42
~~~

Nếu instance có **Redis AUTH hoặc in-transit encryption**, lệnh client phải cấu hình **AUTH/TLS và certificate verification** tương ứng; ví dụ không kèm secret để tránh khuyến khích sao chép credentials. Không sử dụng `KEYS *` hoặc `FLUSHALL` trên instance có workload thật.

Để xem policy của instance mà không thay đổi:

~~~bash
gcloud redis instances describe cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="yaml(redisConfigs,host,port,memorySizeGb,tier)"
~~~

Nếu `redisConfigs` không hiện `maxmemory-policy`, có thể là instance đang dùng **default**. Muốn thay đổi policy dùng cấu hình dịch vụ được hỗ trợ, **không** coi một lệnh `CONFIG SET` từ Redis CLI trên Memorystore là đường quản trị chuẩn.

### 12.4. Kết nối Cloud Run đúng network

Cloud Run cần **Direct VPC egress** hoặc **Serverless VPC Access** để tới private Memorystore endpoint theo thiết kế. Google Cloud khuyên dùng **Direct VPC egress** khi phù hợp vì giảm độ trễ, tăng throughput và tránh chi phí managed connector instances. Quyền **deploy/config network** là Google Cloud IAM; kết nối dữ liệu **Redis AUTH/TLS** là lớp khác.

~~~text
Cloud Run service
  → VPC egress phù hợp + firewall/route
  → Memorystore private IP:port
  → Redis AUTH/TLS theo instance configuration
  → Bigtable API qua service account + Bigtable IAM riêng
~~~

Không mở Redis ra Internet public và không dùng account Owner/Editor chỉ để “sửa timeout”. Nếu client nhận `ECONNREFUSED/timeout`, kiểm tra VPC, region, route/firewall, TLS và DNS/host trước khi kết luận IAM Bigtable sai.

### 12.5. Dọn sandbox

~~~bash
# XÓA instance thật, chỉ sau khi xác minh ownership và không có consumer.
gcloud redis instances delete cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Xóa instance làm mất cache entries và có thể tạo cache miss storm cho các app vẫn đang dùng. Không chạy cleanup khi chưa xác minh instance lab không được chia sẻ.

## 13. Monitoring: đo hiệu quả và phát hiện vấn đề

| Tín hiệu | Cloud Monitoring / app metric | Diễn giải |
|---|---|---|
| Cache hit ratio | `redis.googleapis.com/stats/memory/cache_hit_ratio` và app hit/miss | Tỷ lệ các lần đọc lấy được từ cache |
| Redis keyspace misses | `redis.googleapis.com/stats/keyspace_misses` | Số lookup không thấy key |
| Evicted keys | `redis.googleapis.com/stats/evicted_keys` | Keys bị loại do memory pressure |
| Expired keys | `redis.googleapis.com/stats/expired_keys` | Keys hết hạn vì TTL |
| Key count có TTL | `redis.googleapis.com/keyspace/keys_with_expiration` | Có đang bỏ quên TTL hay không |
| Key TTL trung bình | `redis.googleapis.com/keyspace/avg_ttl` | Đánh giá vòng đời cache |
| Memory usage ratio | `redis.googleapis.com/stats/memory/usage_ratio` | Độ gần ngưỡng maxmemory |
| **System** memory usage ratio | `redis.googleapis.com/stats/memory/system_memory_usage_ratio` | Headroom hệ thống; cảnh báo khi áp lực cao |
| Redis main-thread CPU | `redis.googleapis.com/stats/cpu_utilization_main_thread` | Lệnh tốn CPU/traffic đột biến |
| Request latency | Java p50/p95/p99; Bigtable read latency | Cache thực sự cải thiện người dùng không? |
| Stampede rate | App lock contention, retries, coalesced requests | Có bao nhiêu requests cùng tranh refresh |
| Source load | Bigtable read QPS/latency và billing | Cache miss storm có đánh đổ Bigtable không? |

**Hit ratio cao không đủ:** có thể cache sai dữ liệu/quyền, hoặc giữ payload cũ quá lâu. Theo dõi đồng thời **freshness violations, invalidation failures, backend error rate, p99 và cost**.

### 13.1. Đọc metrics theo nguyên nhân

- **Expired keys tăng nhưng evictions ổn định:** TTL policy hoạt động; tăng tải nguồn có thể do nhiều keys expire cùng lúc.
- **Evicted keys tăng mạnh, memory usage ratio cao:** working set lớn hơn cache capacity; size lại instance, chọn policy, tối ưu payload.
- **Misses tăng, Bigtable p99 tăng, Redis health tốt:** có thể stampede/avalanche hoặc deploy thay đổi key schema.
- **Redis CPU cao, latency cache tăng:** hot key, command nặng, nhiều kết nối hoặc quá nhiều polling.
- **Cache hit cao nhưng báo giá sai:** cache invalidation/version bug; **đừng chữa bằng tăng RAM**.
- **Redis đứt kết nối sau failover/maintenance:** client cần reconnect với **exponential backoff + jitter**; không tái sử dụng socket đã chết vô thời hạn.

### 13.2. SLO ví dụ

~~~text
Orders API (catalog snapshot):
- p95 GET < 150 ms trong điều kiện bình thường
- cache hit ratio mục tiêu > 90% cho hot set
- cache stale không quá 60 s sau source update
- Redis outage không khiến Bigtable read QPS vượt ngưỡng được cấp
- không lộ dữ liệu giữa các tenant
~~~

Các ngưỡng là ví dụ **để nhóm tự đo và đặt SLO**, không phải cam kết Google Cloud. Với các trường hợp cần strong consistency, **độ mới dữ liệu và quyền truy cập** quan trọng hơn mục tiêu cache hit.

## 14. Troubleshooting và runbook

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
|---|---|---|
| Redis GET luôn miss | Key khác namespace, TTL quá ngắn, serialization hoặc eviction | Kiểm tra key schema, `TTL`, app metric |
| Cache ghi xong mất sớm | Memory eviction | `evicted_keys`, policy/capacity |
| Redis OOM trong khi nhiều key tồn tại | `volatile-*` nhưng key thiếu TTL; memory overhead | Kiểm tra `keys_with_expiration` và maxmemory |
| 5000 requests cùng vào Bigtable | Hot key hết hạn, không coalescing | Single-flight/Redis lease, stale data nếu cho phép |
| Nhiều keys cùng miss lúc 12:05 | TTL đồng loạt | Jitter và prewarm hot set có giới hạn |
| Nonexistent ID làm Bigtable tăng QPS | Cache penetration | Validate, negative caching, rate-limit |
| Lock không bao giờ rời | Thiếu TTL hoặc network unlock lỗi | `PX` lease, compare-and-delete, quan sát |
| Instance A xóa lock của B | Unlock bằng `DEL` sau lease expiry | Token + Lua atomic compare-delete |
| Cache chứa v1 sau cập nhật v2 | Slow read fill race hoặc invalidation fail | Source version/fencing và invalidate retries |
| Cloud Run không tới Redis private IP | Sai VPC egress/route/firewall | Kiểm tra Direct VPC egress, network và endpoint |
| Cloud Run có lúc timeout sau maintenance | Client không reconnect/failover | Keepalive, backoff+jitter, short timeouts |
| Bigtable trả 403 | Java runtime SA thiếu Bigtable IAM | Kiểm tra IAM source, không phải Redis `maxmemory` |
| Redis cache có data tenant khác | Key thiếu tenant/permission scope | Ngừng route lỗi, sửa key/auth và invalidate dữ liệu |
| Chi phí Redis tăng nhưng p95 không đổi | Working set/capacity quá lớn | TCO analysis, sample hit/miss và cache payload |

**Runbook 7 bước:**

1. Xác định request/tenant/key class, vị trí Cloud Run và thời điểm phát sinh.
2. Phân biệt **cache miss** với **cache connection error** và **source error**.
3. Xem Redis memory/system memory, expired/evicted keys, hit ratio; phân biệt TTL với eviction.
4. Đo số request cùng hot key, lock contention, waiting budget và Bigtable QPS.
5. Kiểm tra invalidation/write sourceVersion để không khôi phục dữ liệu stale.
6. Sửa trong sandbox: TTL jitter, policy/headroom, bounded waits, local/distributed coalescing; thử failure.
7. Deploy có giám sát, đặt alert p99/freshness/source overload và tính toán chi phí.

**Không khắc phục bằng `FLUSHALL` trên cache production**, vì có thể tạo **mass miss** và làm quá tải Bigtable. Nếu buộc invalidate diện rộng, hãy có cơ chế prewarm, rate limit và rollout/canary.

## 15. Case study: flash sale với Java, Bigtable và Memorystore

**Bối cảnh giả định:** RetailOne có Java Catalog API trên Cloud Run, Bigtable chứa snapshot sản phẩm theo row key `tenant#productId`, Memorystore for Redis giữ cache. Vào 12:00, 20.000 khách cùng xem một sản phẩm đang khuyến mãi.

**Cấu hình ban đầu:**

- Cache key `product:SKU-102` (thiếu tenant).
- TTL đúng 300 giây, cả catalog prewarm cùng lúc.
- Redis mặc định `volatile-lru`, có một số keys ghi không kèm TTL.
- Java xử lý MISS bằng cách **mỗi request** trực tiếp đọc Bigtable.
- Khi cập nhật giá, code cập nhật Bigtable và `DEL` cache không đảm bảo retry.
- Không có lock, không có Bigtable fallback concurrency limit.

### 15.1. Phân tích sự cố

| Triệu chứng | Root cause |
|---|---|
| p99 tăng vọt lúc 12:05 | Avalanche: TTL đồng loạt |
| Bigtable đọc hàng nghìn lần cùng row | Stampede: thiếu coalescing |
| OOM khi cache đầy | Một số key không TTL dưới volatile-lru |
| Đôi lúc thấy giá cũ sau invalidate | Slow-fill race hoặc xóa cache thất bại |
| Rò thông tin giữa shops | Cache key thiếu tenant |
| Redis failover làm source QPS tăng | Chưa có degraded-mode/backpressure |

### 15.2. Kế hoạch sửa

1. Sửa key thành `products:v3:tenantA:SKU-102`, có schema version và tenant.
2. Đặt TTL **có jitter và không vượt freshness SLO**; chọn soft/hard TTL cho catalog cho phép stale có giới hạn.
3. Dùng **local single-flight** trong mỗi Cloud Run instance và **Redis lease** để chỉ một chủ refresh.
4. Khi không có lock, poll ngắn với jitter; hết wait budget thì trả stale/503, **không flood Bigtable**.
5. Có sourceVersion và atomic version comparison; mutate Bigtable trước rồi invalidate qua luồng đáng tin cậy.
6. Với pure cache, đánh giá `allkeys-lru` hoặc đảm bảo toàn bộ keys có TTL; theo dõi evictions/system memory.
7. Dùng Direct VPC egress, Redis AUTH/TLS ở production, runtime SA riêng với Bigtable Reader.
8. Diễn tập cache outage, failover, source 503, timeout, concurrent write, thiếu key và nhiều tenants.
9. Đo p95/p99, Bigtable QPS, hit ratio, hot-key lock contention và **cost per successful request**.

**Không giải quyết bằng cách tăng TTL lên 24 giờ cho bảng giá**: có thể giảm Bigtable reads nhưng đánh đổi thành dữ liệu sai. Bảo mật và freshness phải là ràng buộc trước khi tối ưu hit ratio.

## 16. Bài tập và câu hỏi tự đánh giá

### Bài 1 — TTL khác eviction

Một key được đặt `SET k v EX 300`, nhưng mất sau 20 giây khi Redis memory đầy.

**Hỏi:** có thể xảy ra không? Cần xem metric/policy nào?

**Gợi ý:** có; eviction độc lập TTL. Kiểm tra `evicted_keys`, `maxmemory-policy` và system memory usage.

### Bài 2 — Default volatile-lru

Một instance Memorystore for Redis mặc định `volatile-lru` có 100.000 keys không TTL; khi ghi mới bắt đầu báo OOM.

**Hỏi:** vì sao? Nêu hai giải pháp và cách đo.

**Gợi ý:** key không có TTL không thuộc tập eligible; thêm TTL hoặc dùng `allkeys-lru` cho pure cache, xem memory headroom.

### Bài 3 — Chọn TTL theo SLO

Doanh nghiệp yêu cầu product price cũ tối đa 5 phút; cache `baseTTL=300s` với jitter ±60s.

**Hỏi:** cấu hình này vi phạm SLO không? Đề xuất cách jitter đúng.

**Gợi ý:** TTL tối đa 360s vượt budget; jitter không dương hoặc dùng soft/hard TTL trong giới hạn.

### Bài 4 — Phòng stampede

Hot key hết TTL với 10.000 concurrent requests từ 20 Cloud Run instances.

**Hỏi:** local single-flight giảm còn khoảng bao nhiêu Bigtable reads? Vì sao cần distributed coordination?

**Gợi ý:** có thể còn khoảng một lượt đọc mỗi instance (tới 20), không tự còn một cho toàn hệ thống.

### Bài 5 — Xóa lock an toàn

A có lock token A TTL 15s. Sau 16s B lấy token B; A hoàn tất và gọi `DEL lock`.

**Hỏi:** điều gì sai? Viết nguyên tắc giải phóng an toàn.

**Gợi ý:** compare token + DEL trong một Lua script; lock cũng không thay version/fencing tại source.

### Bài 6 — Cache-aside write race

A bắt đầu load phiên bản v1. B ghi v2 vào Bigtable, xóa cache; B refresh v2; A kết thúc muộn và ghi đè v1.

**Hỏi:** TTL/invalidation một lần đã đủ chưa? Nêu cách tránh stale overwrite.

**Gợi ý:** so sourceVersion atomically, generation key, hoặc đọc source với đường cần nhất quán cao.

### Bài 7 — Negative cache

Một bot gửi 100.000 order IDs không tồn tại. Java đọc Bigtable cho mọi miss.

**Hỏi:** chọn TTL negative cache thế nào? Vì sao không negative-cache lỗi 403/timeout?

**Gợi ý:** TTL ngắn với input validation/rate limit; phân biệt không tồn tại thật với lỗi hệ thống.

### Bài 8 — Redis outage

Redis mất kết nối 2 phút; Java fallback vô hạn sang Bigtable. Bigtable p99 tăng và bị quota.

**Hỏi:** thiết kế degraded mode nào phù hợp?

**Gợi ý:** circuit breaker, bounded fallback, rate limit, 503/Retry-After hoặc stale khi được phép.

### Bài 9 — Cache đa tenant

Hai tenants đều có `orderId=OD-42`, nhưng key chỉ là `orders:OD-42`.

**Hỏi:** nguy cơ gì? Sửa key và chỗ kiểm tra authorization ra sao?

**Gợi ý:** đưa tenant/authorization scope vào key, xác thực caller trước cache read và không dùng cache thay policy check.

### Bài 10 — Production design

Thiết kế Cache-aside cho Java Catalog API có Bigtable source và Redis trên VPC. Trình bày: key schema, TTL jitter, maxmemory policy, two-level single-flight, concurrency limits, source write invalidation/version, AUTH/TLS, monitoring và chi phí. Đưa thêm **test khi hot key expire cùng lúc 5000 requests**.

## 17. Checklist production

- [ ] Bigtable hoặc database gốc là **source of truth**; cache có thể mất và tái tạo.
- [ ] Chỉ cache data có freshness budget rõ, không dùng cache làm quyết định thanh toán/ủy quyền duy nhất.
- [ ] Key bao gồm namespace, schema version, tenant và các tham số ảnh hưởng nội dung.
- [ ] Payload nhỏ, versioned, không chứa token/secret và được serialize theo schema.
- [ ] Mỗi write cache có TTL; phân biệt expiration với memory eviction.
- [ ] TTL jitter không vượt freshness SLO; negative caching ngắn và chỉ cho not-found thật.
- [ ] Biết default Memorystore for Redis `volatile-lru` và nguy cơ keys không TTL.
- [ ] Đã đo `maxmemory-gb`, memory/system memory ratios, evictions/expired keys.
- [ ] Có local single-flight và distributed lease nếu hot keys/scale yêu cầu.
- [ ] Lock dùng `SET NX PX` với token khác nhau, unlock compare-and-delete atomically.
- [ ] Có bounded waiting, jitter và backpressure; không spin-loop hoặc unlimited fallback.
- [ ] Source update → invalidate; có version/đường fallback cho write/read race.
- [ ] Stale-while-revalidate chỉ cho loại dữ liệu cho phép, có hard freshness bound.
- [ ] Redis outage/failover không làm Bigtable bị stampede; client reconnect/backoff.
- [ ] Cloud Run/VPC egress đúng; Redis private networking, AUTH/TLS và Secret Manager khi dùng.
- [ ] Runtime SA có IAM Bigtable tối thiểu; Redis auth khác Google Cloud IAM quản trị.
- [ ] Có alert cho p95/p99, hit ratio, source QPS, memory, evictions, stampede/lock contention.
- [ ] Đã thử concurrency, malformed keys, not-found, concurrent writes, network failures và Redis loss.
- [ ] Dự toán capacity/tier, network, Cloud Run compute, Bigtable reads và monitoring/logging.
- [ ] Không chạy `FLUSHALL` hoặc xóa instance production; cleanup sandbox có kiểm tra ownership.

## 18. Tài liệu chính thức và tham khảo

Đối chiếu sản phẩm/phiên bản, API, giá và cấu hình thực tế trước khi triển khai:

- [Memorystore for Redis — Tổng quan](https://docs.cloud.google.com/memorystore/docs/redis/redis-overview)
- [Memorystore for Redis — Supported Redis configurations](https://docs.cloud.google.com/memorystore/docs/redis/supported-redis-configurations)
- [Memorystore for Redis — Memory management best practices](https://docs.cloud.google.com/memorystore/docs/redis/memory-management-best-practices)
- [Memorystore for Redis — General best practices](https://docs.cloud.google.com/memorystore/docs/redis/general-best-practices)
- [Memorystore for Redis — Create and manage instances](https://docs.cloud.google.com/memorystore/docs/redis/create-manage-instances)
- [Memorystore for Redis — Configure Redis](https://docs.cloud.google.com/memorystore/docs/redis/configure-redis)
- [Memorystore for Redis — Connect from Cloud Run](https://docs.cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run)
- [Memorystore for Redis — Supported monitoring metrics](https://docs.cloud.google.com/memorystore/docs/redis/supported-monitoring-metrics)
- [Memorystore for Redis Cluster — Supported configurations](https://docs.cloud.google.com/memorystore/docs/cluster/supported-instance-configurations)
- [Memorystore for Valkey — Best practices](https://docs.cloud.google.com/memorystore/docs/valkey/general-best-practices)
- [Bigtable — Schema design and row key practices](https://docs.cloud.google.com/bigtable/docs/schema-design)
- [Redis — Key eviction policies](https://redis.io/docs/latest/reference/eviction/)
- [Redis — SET NX/PX and safe lock release](https://redis.io/docs/latest/commands/set/)
- [Lettuce Java client](https://redis.github.io/lettuce/)
- [Google Cloud — Memorystore pricing](https://cloud.google.com/memorystore/pricing)

**Điểm cần nhớ:** **Cache-aside** có lợi khi Java API đọc nhiều lần cùng bản ghi từ Bigtable, nhưng **Redis chỉ là bản sao có thể mất**. **TTL** quyết định thời gian tồn tại; **eviction** phụ thuộc bộ nhớ và `maxmemory-policy` — mặc định Memorystore for Redis là `volatile-lru`. Trước hot-key miss, dùng **TTL jitter, single-flight, Redis lease có token + compare-and-delete, bounded wait và stale data trong giới hạn**. Cần **source-version/invalidation an toàn**, giám sát **freshness, p99, evictions, Bigtable QPS và chi phí**, không hy sinh tính đúng đắn hoặc bảo mật chỉ để tăng hit ratio.
