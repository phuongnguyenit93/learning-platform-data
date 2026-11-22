# Cache-aside, write-through và chính sách TTL

> **Chương:** Cache và dữ liệu chuyên dụng  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

Một cửa hàng trực tuyến có hàng triệu lượt xem thông tin sản phẩm mỗi ngày, nhưng dữ liệu giá và mô tả thay đổi ít hơn nhiều so với tần suất đọc. Nếu mỗi request đều truy vấn database, hệ thống phải trả chi phí I/O, connection và compute cho những kết quả lặp đi lặp lại. **Cache** giữ bản sao dữ liệu thường dùng trong bộ nhớ để giảm độ trễ và giảm tải nguồn dữ liệu chính.

Ba quyết định quan trọng khi thiết kế cache là:

- **Cache-aside:** ứng dụng chủ động đọc cache; cache miss thì lấy dữ liệu từ database rồi nạp lại cache.
- **Write-through:** thao tác ghi cập nhật cache và nguồn dữ liệu theo một quy trình đồng bộ được xác định rõ.
- **TTL (Time To Live):** thời gian một cache entry được xem là còn hợp lệ trước khi hết hạn.

Không có pattern nào tự giải quyết mọi vấn đề consistency. Cache có thể chứa dữ liệu cũ, bị xóa bởi eviction, mất khi node lỗi hoặc được nhiều application instances cập nhật đồng thời. Vì vậy, cần xác định **nguồn dữ liệu chuẩn (source of truth)**, mức stale data chấp nhận được, cách invalidation, xử lý cache stampede và hành vi khi cache không hoạt động.

Trong AWS, các lựa chọn phổ biến gồm **Amazon ElastiCache for Valkey/Redis OSS**, **Amazon ElastiCache for Memcached** và **Amazon DynamoDB Accelerator (DAX)**. Chúng phục vụ các mô hình dữ liệu và consistency khác nhau; không phải dịch vụ cache nào cũng là một Redis endpoint thay thế được cho nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cache hit/miss, source of truth, cache key, cache entry, eviction và invalidation.
2. Phân biệt **cache-aside, write-through, write-around và write-behind**; chọn pattern theo yêu cầu đọc/ghi.
3. Thiết kế **TTL** theo độ mới dữ liệu, traffic và rủi ro stale data; phân biệt TTL của cache với TTL xóa dữ liệu trong database.
4. Giải quyết cache stampede, thundering herd, cache penetration, hot keys và cache avalanche.
5. Chọn ElastiCache Valkey/Redis OSS, Memcached hoặc DynamoDB DAX theo use case.
6. Áp dụng cache trong ứng dụng Java/Spring Boot, thiết kế key, invalidation và serialization an toàn.
7. Quan sát cache hit ratio, latency, evictions, memory, connections và replication lag.
8. Xây dựng fallback, bảo mật, HA, capacity planning và kiểm soát chi phí khi cache lỗi hoặc quá tải.

## 2. Cache hoạt động như thế nào?

Cache là một lớp lưu trữ nhanh hơn nguồn dữ liệu chính, thường nằm trong RAM. Ứng dụng tra cache bằng một **key**. Nếu key tồn tại và entry còn hợp lệ, ứng dụng nhận **cache hit**; nếu không, xảy ra **cache miss** và ứng dụng phải lấy dữ liệu từ source of truth.

~~~mermaid
flowchart TD
    REQ["Application request"] --> LOOK["Lookup cache by key"]
    LOOK --> HIT{"Entry exists\nand valid?"}
    HIT -->|"Hit"| RETURN["Return cached value"]
    HIT -->|"Miss / expired"| DB["Read source of truth"]
    DB --> FILL["Populate cache with TTL"]
    FILL --> RETURNDB["Return database value"]
~~~

### 2.1. Những khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Source of truth** | Nơi lưu dữ liệu chuẩn, ví dụ RDS/Aurora hoặc DynamoDB |
| **Cache key** | Định danh duy nhất của một entry trong cache |
| **Cache entry/value** | Dữ liệu được lưu theo key, có thể kèm metadata/version |
| **Cache hit** | Tìm thấy entry còn hợp lệ |
| **Cache miss** | Không tìm thấy entry, entry đã hết hạn hoặc bị eviction |
| **TTL** | Thời gian hiệu lực của entry trong cache |
| **Invalidation** | Chủ động làm entry không còn được dùng, thường là xóa hoặc thay đổi version |
| **Eviction** | Cache tự loại entry để giải phóng bộ nhớ theo policy |
| **Hit ratio** | Tỷ lệ request cache hit trên tổng request lookup |
| **Stale data** | Dữ liệu cache cũ hơn source of truth |

**TTL và invalidation không giống nhau:** TTL là giới hạn thời gian; invalidation là phản ứng với một thay đổi cụ thể. Một sản phẩm vừa đổi giá có thể cần invalidation ngay, dù TTL còn 20 phút.

### 2.2. Ví dụ hit ratio

Giả sử trong một phút ứng dụng có 10.000 cache lookups:

~~~text
Cache hits  = 9.200
Cache misses = 800

Hit ratio = 9.200 / 10.000 = 92%
Miss ratio = 800 / 10.000 = 8%
~~~

Hit ratio cao thường giảm tải database, nhưng **không tự chứng minh hệ thống tốt**:

- Cache có thể trả dữ liệu sai hoặc cũ.
- Một hot key có hit ratio cao nhưng tạo nghẽn trên một shard.
- Một miss có thể gọi database rất đắt.
- Cache có thể tăng chi phí compute/network lớn hơn phần database tiết kiệm.

Nên đo cả **latency, stale data, downstream load và business correctness**, không chỉ hit ratio.

## 3. Cache-aside: ứng dụng chủ động quản lý cache

**Cache-aside** (còn gọi là lazy loading) là pattern phổ biến khi đọc dữ liệu. Ứng dụng kiểm tra cache trước; nếu miss thì truy vấn database, sau đó đưa kết quả vào cache.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache
    participant D as Database
    A->>C: GET product:42
    C-->>A: MISS
    A->>D: SELECT product WHERE id=42
    D-->>A: Product data
    A->>C: SET product:42 value EX TTL
    C-->>A: OK
    A-->>A: Return product
    Note over A,C: Request tiếp theo thường là cache HIT
~~~

### 3.1. Quy trình đọc

1. Xây cache key từ các thuộc tính xác định dữ liệu.
2. Đọc cache.
3. Nếu hit, deserialize và kiểm tra version/schema cần thiết rồi trả kết quả.
4. Nếu miss, truy vấn source of truth.
5. Nếu tìm thấy, ghi cache với TTL phù hợp.
6. Trả kết quả cho caller.

Nếu database không tìm thấy dữ liệu, ứng dụng có thể **negative cache** một marker “not found” trong thời gian ngắn. Không lưu một giá trị `null` không phân biệt với “cache miss”, nếu thư viện không hỗ trợ rõ semantics đó.

### 3.2. Ví dụ cache-aside với Redis/Valkey (Java pseudocode)

~~~java
public Product findProduct(String tenantId, String productId) {
    String key = "product:v3:" + tenantId + ":" + productId;

    Product cached = cache.get(key);
    if (cached != null) {
        return cached;
    }

    Product product = productRepository
        .findByTenantIdAndId(tenantId, productId)
        .orElse(null);

    if (product != null) {
        cache.set(key, product, Duration.ofMinutes(5));
    } else {
        // Negative cache ngắn để tránh truy vấn lặp cho ID không tồn tại.
        cache.set(key, NOT_FOUND_MARKER, Duration.ofSeconds(20));
    }
    return product;
}
~~~

Đây là pseudocode để giải thích pattern; `cache`, `NOT_FOUND_MARKER` và repository cần được triển khai theo thư viện cụ thể. Nếu cache chứa marker, code đọc phải phân biệt **marker not found** với **cache miss**.

### 3.3. Ghi và invalidation trong cache-aside

~~~mermaid
sequenceDiagram
    participant A as Application
    participant D as Database
    participant C as Cache
    A->>D: UPDATE product SET price=...
    D-->>A: Commit success
    A->>C: DEL product:42
    C-->>A: Deleted
    Note over A,C: Lần đọc tiếp theo sẽ reload từ DB
~~~

Thứ tự **commit database trước, rồi invalidate cache** giúp tránh xóa cache rồi để một request khác nạp lại giá trị cũ trước khi database commit. Nhưng vẫn có race condition:

1. Request A đọc giá cũ từ database.
2. Request B cập nhật giá mới, commit và xóa cache.
3. Request A ghi giá cũ vào cache sau khi B đã xóa.

Kết quả: cache có thể stale dù invalidation đã chạy. Có thể giảm rủi ro bằng **versioned keys**, write serialization, conditional update, outbox/event-driven invalidation hoặc TTL ngắn theo SLA.

### 3.4. Ưu và nhược điểm

| Ưu điểm | Đánh đổi |
| --- | --- |
| Chỉ cache dữ liệu thực sự được đọc | Lần đọc đầu tiên chịu latency database |
| Dễ áp dụng lên hệ thống database hiện có | Ứng dụng phải quản lý miss, fill và invalidation |
| Cache có thể mất mà dữ liệu chuẩn vẫn còn | Cache outage có thể dồn tải vào database |
| TTL giới hạn tuổi entry | Dữ liệu có thể stale trong khoảng TTL |

**Phù hợp:** product catalog, hồ sơ người dùng, cấu hình đọc nhiều/ghi ít, trang chi tiết và dữ liệu có thể tái tạo từ source of truth.

## 4. Write-through: ghi cache và nguồn dữ liệu trong cùng quy trình

**Write-through** mô tả mô hình mà thao tác ghi cập nhật **cache và backing store đồng bộ trong cùng luồng ghi** theo hợp đồng của cache layer. Một số framework/library định nghĩa write-through là ghi cache trước rồi cache loader ghi backing store; một số kiến trúc ứng dụng thực hiện database commit rồi cập nhật cache trước khi trả response. Điểm cốt lõi là **không trả thành công như thể cả hai nơi đã đồng bộ nếu chỉ một nơi được cập nhật**.

~~~mermaid
flowchart TD
    W["Application write"] --> TW["Write-through layer"]
    TW --> DB["Persist to source of truth"]
    DB -->|"Success"| CACHE["Update cache entry"]
    CACHE -->|"Success"| ACK["Acknowledge write"]
    DB -->|"Failure"| ERR["Return failure / retry"]
    CACHE -->|"Failure"| REPAIR["Repair / invalidate / reconcile"]
~~~

Sơ đồ minh họa một biến thể **database commit trước rồi cache update**. Thứ tự chính xác phụ thuộc implementation. Một write-through layer có thể ghi cache rồi synchronously persist vào database; khi đó nó phải xử lý lỗi backing store và không để cache trở thành dữ liệu chuẩn ngoài ý muốn.

### 4.1. Luồng ghi đồng bộ kiểu database-first

1. Validate request và quyền cập nhật.
2. Ghi database trong transaction.
3. Commit database thành công.
4. Cập nhật cache với giá trị mới hoặc xóa entry để request sau reload.
5. Trả kết quả theo contract.

Nếu bước 4 thất bại sau khi bước 3 đã commit, database là source of truth nhưng cache chưa được cập nhật. Ứng dụng cần **invalidation/reconciliation**, event/outbox hoặc TTL để khôi phục trạng thái.

### 4.2. Write-through không tạo distributed transaction tự động

Database và Redis/Valkey thường không cùng một ACID transaction. Không thể giả định:

~~~text
DB COMMIT thành công
Redis SET thất bại
→ toàn bộ hai thao tác tự rollback như một transaction
~~~

Nếu cần bảo đảm cập nhật cache cuối cùng:

- Ghi **outbox event** trong cùng transaction với database business update.
- Một worker đọc outbox và cập nhật/xóa cache.
- Event có `eventId`/version, worker idempotent và retry có giới hạn.
- Có DLQ/reconciliation khi event không thể xử lý.

Đây là **eventual cache consistency** nếu cache cập nhật bất đồng bộ. Nó khác write-through đồng bộ nghiêm ngặt về thời điểm response.

### 4.3. Khi nào write-through hữu ích?

- Dữ liệu thường xuyên được đọc ngay sau khi tạo/cập nhật.
- Cần giảm cache miss ngay sau write.
- Cache layer có cơ chế đồng bộ backing store phù hợp.
- Chấp nhận thêm latency ghi và có phương án khi một trong hai hệ thống lỗi.

**Không phù hợp** khi write volume rất lớn nhưng read rate thấp: phải duy trì cache cho dữ liệu ít được dùng và trả thêm chi phí mỗi lần ghi.

## 5. Cache-aside, write-through, write-around và write-behind

| Pattern | Đọc | Ghi | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- | --- | --- |
| **Cache-aside** | App đọc cache, miss thì đọc DB và fill | App ghi DB rồi invalidate/update cache | Dễ áp dụng, cache chỉ chứa dữ liệu được dùng | Miss latency, race invalidation, app quản lý cache |
| **Write-through** | Thường đọc cache | Ghi backing store và cache theo một luồng đồng bộ | Entry mới có sẵn sau write nếu thành công | Write latency tăng, lỗi giữa hai nơi cần xử lý |
| **Write-around** | App đọc cache, miss thì DB/fill theo policy | Ghi trực tiếp DB, không đưa ngay entry vào cache | Tránh cache các record chỉ ghi mà ít đọc | Lần đọc ngay sau write có thể miss |
| **Write-behind / write-back** | Đọc từ cache | Cache nhận ghi trước, persist DB bất đồng bộ | Write latency thấp, gom batch ghi | Có thể mất dữ liệu chưa flush, ordering/retry phức tạp |

### 5.1. Ví dụ chọn pattern

- **Danh mục sản phẩm:** cache-aside, TTL vài phút và invalidate khi giá/tồn kho thay đổi.
- **Cấu hình hiếm khi đổi nhưng luôn đọc sau khi cập nhật:** write-through hoặc DB commit + synchronous cache update.
- **Log/event có tần suất ghi cao, đọc ít:** write-around có thể hợp lý.
- **Counter/telemetry cần gom batch:** write-behind chỉ khi chấp nhận durability/consistency trade-offs và có cơ chế persist đáng tin.

**Write-behind là pattern có rủi ro dữ liệu rõ rệt.** Redis/Valkey cache không mặc định là durable database thay thế RDS/DynamoDB. Nếu cache node restart hoặc dữ liệu chưa flush bị mất, hệ thống có thể mất writes. Chỉ dùng khi có persistence/replication/queue và recovery semantics phù hợp với yêu cầu nghiệp vụ.

## 6. TTL: chính sách tuổi thọ cache entry

**TTL** xác định một entry được xem là hợp lệ trong bao lâu. Khi TTL hết hạn, cache không còn phải trả entry đó như dữ liệu hợp lệ; request tiếp theo thường phải load lại từ source of truth.

Ví dụ:

~~~text
SET product:42 '{"price":350000}' EX 300

EX = 300 seconds
→ Entry có TTL 5 phút
~~~

TTL **không có nghĩa** database record bị xóa sau 5 phút. TTL của cache là chính sách freshness; TTL của DynamoDB table hoặc lifecycle S3 có thể thực hiện việc xóa dữ liệu gốc theo semantics riêng.

### 6.1. Chọn TTL theo dữ liệu, không chọn một con số cho mọi key

| Loại dữ liệu | TTL khởi đầu để đánh giá | Cân nhắc |
| --- | --- | --- |
| **Danh mục/mô tả sản phẩm** | 5–30 phút | Có thể invalidate khi sản phẩm đổi |
| **Giá và khuyến mãi** | Vài chục giây đến vài phút | Sai giá có thể gây thiệt hại, cần event invalidation |
| **Profile ít thay đổi** | 5–60 phút | Cân nhắc cập nhật profile và phiên người dùng |
| **Feature/configuration** | Vài phút hoặc lâu hơn | Có thể dùng version/config event để invalidate |
| **Session/token metadata** | Theo thời hạn bảo mật của session | Không để cache TTL vượt authorization expiry |
| **Leaderboard/counter realtime** | Vài giây | Độ mới quan trọng hơn hit ratio |
| **Negative cache (not found)** | Vài giây đến vài chục giây | Tránh che khuất record mới vừa được tạo |

Các khoảng thời gian trên chỉ là **điểm bắt đầu cho load test và SLO**, không phải best practice phổ quát. TTL phù hợp phụ thuộc tần suất thay đổi, độ nghiêm trọng của stale data và khả năng invalidation.

### 6.2. TTL cố định có thể gây cache avalanche

Nếu một đợt import ghi 100.000 entries cùng lúc và tất cả có TTL đúng 10 phút, chúng có thể hết hạn gần nhau. Database đột nhiên nhận một lượng lớn cache misses.

Một kỹ thuật đơn giản là **TTL jitter**:

~~~text
baseTTL = 600 seconds
jitter = random(0..120 seconds)
actualTTL = baseTTL + jitter

→ Entry hết hạn trong khoảng 10–12 phút,
  giảm khả năng nhiều key cùng hết hạn một lúc.
~~~

Không dùng jitter nếu contract đòi thời hạn tối đa chính xác mà không điều chỉnh được; trong trường hợp đó, cần refresh/eviction strategy khác.

### 6.3. TTL, absolute expiration và sliding expiration

- **Relative TTL:** entry tồn tại thêm N giây từ lúc set.
- **Absolute expiration:** entry hết hạn tại một timestamp xác định.
- **Sliding expiration:** mỗi lần truy cập hợp lệ, TTL được gia hạn.

Sliding expiration có thể giữ dữ liệu “hot” vô thời hạn nếu luôn được đọc. Với session, điều đó có thể phù hợp nếu có **maximum lifetime** riêng. Với dữ liệu nghiệp vụ, sliding expiration có thể làm stale data tồn tại quá lâu nếu không có invalidation.

### 6.4. Expiration không nhất thiết là xóa ngay tại đúng mili giây

Cache engine có thể thực hiện expiration theo cách tối ưu nội bộ; một số entry hết hạn được loại bỏ khi truy cập hoặc qua hoạt động dọn nền. Ứng dụng nên dựa trên **semantics không còn được trả như dữ liệu hợp lệ sau TTL**, không dựa vào quan sát RAM để khẳng định key đã bị giải phóng đúng thời điểm.

Đối với Redis/Valkey, TTL thường được cấu hình theo seconds hoặc milliseconds và có thể xem bằng lệnh TTL/PTTL. Memcached dùng expiration theo quy tắc riêng của engine. DynamoDB TTL xóa item **bất đồng bộ**, không phải cache expiration đồng bộ.

## 7. Cache invalidation: khi nào dữ liệu cũ phải biến mất?

TTL là lưới an toàn cuối cùng, nhưng với dữ liệu nhạy cảm freshness, nên có **invalidation theo sự kiện**.

~~~mermaid
flowchart LR
    APP["Application update"] --> DB["Commit database"]
    DB --> OUT["Outbox event"]
    OUT --> BUS["EventBridge / SNS / SQS"]
    BUS --> WORK["Invalidation worker"]
    WORK --> CACHE["DEL / version bump"]
    CACHE --> NEXT["Next read reloads current data"]
~~~

### 7.1. Những chiến lược invalidation

| Chiến lược | Cách làm | Đặc điểm |
| --- | --- | --- |
| **Delete key** | Xóa entry khi dữ liệu thay đổi | Đơn giản; request tiếp theo reload |
| **Update key** | Ghi giá trị mới vào cache | Read-after-write nhanh; phải xử lý lỗi ghi cache |
| **Versioned key** | Tăng version trong key hoặc namespace | Tránh race ghi giá trị cũ vào key mới; cần quản lý version |
| **Event-driven invalidation** | Phát event sau DB commit | Tách app khỏi cache nhưng có eventual delay |
| **TTL only** | Chờ entry hết hạn | Dễ vận hành nhưng stale window dài hơn |

### 7.2. Outbox tránh mất invalidation event

Một anti-pattern:

~~~text
1. UPDATE database thành công
2. App crash trước khi publish invalidation
3. Cache giữ dữ liệu cũ tới hết TTL
~~~

Pattern **transactional outbox** ghi business change và outbox record trong cùng database transaction. Một publisher/worker đọc outbox, phát event rồi đánh dấu xử lý. Nếu worker publish lặp, consumer phải idempotent.

### 7.3. Versioned cache key

Ví dụ:

~~~text
product:tenant-7:42:v18
~~~

Khi dữ liệu được cập nhật từ version 18 sang 19, ứng dụng tra key `product:tenant-7:42:v19`. Một request cũ ghi lại key version 18 không làm bẩn namespace mới. Tuy nhiên, phải có **nguồn version đáng tin** và cách lấy version mới; nếu version pointer cũng cache quá lâu thì stale issue vẫn còn.

### 7.4. Invalidation theo quan hệ dữ liệu

Một trang sản phẩm có thể phụ thuộc:

- Product detail.
- Price/promotion.
- Inventory.
- Product category.
- Recommendation result.

Chỉ xóa `product:42` có thể không đủ nếu cache còn `category:shoes:page:1` hoặc `recommendations:user:42`. Hãy xác định **cache dependency graph** và chọn namespace/tag/version invalidation có thể quản lý.

## 8. Cache stampede, thundering herd và các kiểu cache failure

### 8.1. Cache stampede

Một key rất phổ biến hết TTL. 5.000 requests cùng lúc nhận miss và cùng truy vấn database:

~~~mermaid
flowchart TD
    R["5.000 requests"] --> C["Cache: key expired"]
    C --> DB["5.000 concurrent DB reads"]
    DB --> LOAD["DB CPU / connections spike"]
    LOAD --> TIMEOUT["Latency / timeout / retry"]
~~~

Giải pháp:

- **Single-flight/request coalescing:** chỉ một request refresh key, request khác chờ hoặc nhận stale value nếu policy cho phép.
- **Distributed lock:** khóa theo key có TTL ngắn, token owner duy nhất và cách release an toàn.
- **TTL jitter:** tránh nhiều keys hết hạn cùng lúc.
- **Refresh-ahead:** refresh key trước thời điểm hết hạn khi có tín hiệu hotness.
- **Stale-while-revalidate:** trả giá trị stale trong cửa sổ chấp nhận được trong khi một worker refresh.
- **Rate limit DB fallback:** bảo vệ database khi cache bị mất.

### 8.2. Distributed lock cần fencing/token

Một lock đơn giản `SET key token NX PX ...` có thể ngăn nhiều workers refresh cùng lúc, nhưng cần:

1. Token ngẫu nhiên riêng cho owner.
2. TTL lock ngắn hơn giới hạn xử lý và có cơ chế gia hạn nếu cần.
3. Chỉ release lock khi token vẫn khớp owner hiện tại (Lua compare-and-delete hoặc cơ chế atomic tương đương).
4. Không giả định lock hết hạn là worker cũ đã dừng; worker cũ có thể vẫn chạy.
5. Với side effect quan trọng, dùng **fencing token/version** ở resource được bảo vệ để ngăn owner cũ ghi đè owner mới.

Lock cache chỉ giảm trùng lặp computation; nó không thay thế transaction hay concurrency control của database.

### 8.3. Cache penetration (cache miss liên tục)

Nếu người dùng gửi hàng nghìn IDs không tồn tại, mỗi request đều miss và truy vấn DB. Biện pháp:

- Validate input và rate limit.
- Negative caching với TTL ngắn.
- Dùng Bloom filter hoặc cấu trúc tương tự nếu use case và false-positive semantics phù hợp.
- Không lưu kết quả `not found` quá lâu nếu record có thể được tạo ngay sau đó.

### 8.4. Cache breakdown và hot key

Một key được hàng chục nghìn requests đọc mỗi giây có thể tạo hotspot trên một node/shard. Khi key hết hạn, stampede làm tải nặng hơn.

- Replicate/read replicas hoặc phân phối key theo thiết kế hỗ trợ.
- Local in-process cache ngắn hạn có thể giảm network requests nhưng tạo thêm invalidation complexity.
- Dùng precomputed value, sharded counters hoặc key partitioning nếu semantics cho phép.
- Refresh trước TTL và theo dõi key-level access pattern khi có thể.

### 8.5. Cache avalanche

Nhiều keys cùng hết hạn hoặc một cache cluster mất khả năng phục vụ, dẫn đến hàng loạt miss. Dùng jitter, warm-up có kiểm soát, fallback concurrency cap và capacity test.

**Không fallback vô hạn:** nếu cache lỗi, cho phép tất cả request gọi DB có thể khiến DB sập theo. Cache nên có **bulkhead**, timeout ngắn, circuit breaker và giới hạn tải.

## 9. Eviction và memory management

Cache có dung lượng hữu hạn. Khi memory gần giới hạn, engine có thể từ chối ghi hoặc loại bỏ keys theo **eviction policy**.

### 9.1. Một số policy phổ biến trong Redis/Valkey

| Policy (tên phổ biến) | Ý nghĩa khái quát |
| --- | --- |
| `noeviction` | Không tự loại keys; ghi mới có thể thất bại khi hết memory |
| `allkeys-lru` | Chọn keys ít được dùng gần đây trong toàn bộ keyspace |
| `allkeys-lfu` | Ưu tiên giữ keys có tần suất truy cập cao |
| `volatile-lru` | Chọn trong nhóm keys có TTL |
| `volatile-lfu` | Chọn trong nhóm keys có TTL theo tần suất |
| `volatile-ttl` | Ưu tiên keys có TTL còn lại ngắn theo semantics engine |

Tên và khả năng cấu hình phụ thuộc engine/version/parameter group. **TTL expiration và eviction là hai cơ chế khác nhau:** key có thể bị eviction trước TTL khi memory pressure cao.

### 9.2. Chọn policy theo loại dữ liệu

- **Cache có thể tái tạo:** policy LRU/LFU có thể phù hợp; mất key làm phát sinh miss.
- **Cache chứa state quan trọng chưa persist:** không nên xem eviction là cơ chế an toàn; cần lưu durable source trước.
- **Không có TTL cho một phần keys:** `volatile-*` chỉ chọn trong nhóm có expiration; nếu không có key phù hợp, ghi mới có thể thất bại.
- **`noeviction`:** phù hợp khi muốn tránh tự động xóa dữ liệu nhưng ứng dụng phải xử lý write failures và memory alarms.

### 9.3. Ước lượng memory

Giả sử:

~~~text
Số keys                    = 2.000.000
Payload trung bình/key     = 700 bytes
Key + object/metadata      = 180 bytes (ước lượng)

Raw estimate = 2.000.000 × 880 bytes
             = 1.760.000.000 bytes
             ≈ 1,76 GB (decimal)
~~~

Đây **không phải kích thước RAM cần cấp**. Cần thêm overhead cấu trúc dữ liệu, allocator fragmentation, replication buffers, client output buffers, temporary memory, persistence/AOF nếu dùng và headroom để tránh OOM. Hãy benchmark bằng dữ liệu có phân bố key/value gần thực tế.

## 10. Chọn dịch vụ cache trong AWS

Không phải workload nào cũng cần Redis/Valkey. Trước khi chọn dịch vụ, xác định:

1. Dữ liệu cache là **key/value tổng quát**, object, session, counter hay chỉ là kết quả đọc từ DynamoDB?
2. Có cần **data structures**, pub/sub, scripting, sorted sets hoặc atomic operations không?
3. Có cần **replication, Multi-AZ failover, persistence/snapshot** hay dữ liệu có thể tạo lại?
4. Cần throughput, latency, số connections, memory và khả năng scale đến mức nào?
5. Ứng dụng có thể chấp nhận **eventual consistency** hay cần strongly consistent reads?

### 10.1. So sánh các lựa chọn phổ biến

| Dịch vụ | Mô hình | Điểm mạnh | Cân nhắc |
| --- | --- | --- | --- |
| **Amazon ElastiCache for Valkey** | Managed in-memory key/value/data structures | Tương thích giao thức Redis theo mức hỗ trợ của engine, nhiều data structures, replication/topology options | Cần hiểu cluster mode, shard, failover, memory và engine compatibility |
| **Amazon ElastiCache for Redis OSS** | Managed Redis OSS-compatible cache engine | Ecosystem Redis, data structures và tooling rộng | Engine/version/feature support cần kiểm tra; không tự coi giống Valkey tuyệt đối |
| **Amazon ElastiCache for Memcached** | Distributed in-memory key/value cache | Đơn giản, scale ngang qua nhiều nodes, phù hợp object cache | Không có mô hình persistence/replication và data structures phong phú như Redis-compatible engines |
| **Amazon DynamoDB Accelerator (DAX)** | Managed in-memory cache chuyên cho DynamoDB | Giảm latency đọc DynamoDB với client tương thích; write-through cache | Chỉ dành cho DynamoDB access pattern; eventual consistency và strongly consistent reads cần hiểu rõ |
| **Local in-process cache** | Cache trong RAM của từng application instance | Rất nhanh, không có network hop | Mỗi instance có bản riêng; invalidation, memory và cold start phức tạp |

**DAX không phải Redis thay thế**; Memcached cũng không phải Redis-compatible engine. Nếu ứng dụng cần Redis protocol/data structures, DAX không thể chỉ thay hostname trong connection string.

### 10.2. ElastiCache Valkey/Redis OSS

ElastiCache phù hợp khi ứng dụng cần cache key/value linh hoạt, data structures hoặc các thao tác nguyên tử ở tầng cache.

Các thành phần thường gặp:

- **Node:** một cache server instance với memory/compute cụ thể.
- **Replication group:** nhóm nodes phục vụ một logical cache; topology primary/replicas tùy engine và cấu hình.
- **Shard:** partition dữ liệu trong cluster-mode enabled; key được phân phối theo hash slot.
- **Cluster mode disabled:** một primary và các replicas theo cấu hình; dễ quản lý hơn nhưng scale write theo một primary.
- **Cluster mode enabled:** nhiều shards/primaries để phân phối dữ liệu và throughput; client phải hỗ trợ cluster topology/redirects.
- **Multi-AZ/automatic failover:** tăng khả năng chịu lỗi cho topology được hỗ trợ; failover vẫn có thể làm connection reset và replication lag.

~~~mermaid
flowchart TB
    APP["Application fleet"] --> EP["ElastiCache configuration endpoint"]
    EP --> S1["Shard 1\nPrimary"]
    EP --> S2["Shard 2\nPrimary"]
    EP --> S3["Shard 3\nPrimary"]
    S1 --> R1["Replica"]
    S2 --> R2["Replica"]
    S3 --> R3["Replica"]
~~~

*Sơ đồ khái niệm cho cluster-mode enabled. Endpoint, replica count và cách client khám phá topology phụ thuộc cấu hình thật.*

Khi thiết kế:

- Dùng **private subnets**, security groups và subnet groups phù hợp.
- Chọn node family/memory dựa trên working set, peak traffic và replication overhead.
- Bật encryption at rest/in transit theo yêu cầu và xác thực bằng cơ chế được engine hỗ trợ.
- Xác định eviction policy, max memory, snapshot/backup nếu cần.
- Dùng client hỗ trợ reconnect, cluster topology và TLS; tránh tự parse endpoint rồi hardcode node IP.
- Kiểm thử failover, resharding/scale và ứng xử khi cache tạm unavailable.

### 10.3. ElastiCache Memcached

Memcached là lựa chọn phù hợp cho **object cache đơn giản**, nơi ứng dụng có thể tái tạo dữ liệu từ database khi node mất.

Đặc điểm:

- Key/value đơn giản, API cache cơ bản.
- Có thể phân phối keys trên nhiều nodes qua client-side hashing/auto discovery tùy client.
- Node failure có thể làm mất những keys đang nằm trên node; cache miss sẽ quay về source of truth.
- Không nên dùng Memcached làm kho dữ liệu durable hoặc nơi giữ workflow state chưa persist.
- Không có cùng hệ sinh thái data structures, scripting và replication semantics của Redis-compatible engines.

Memcached phù hợp khi muốn cache object để giảm read load mà không cần sorted sets, streams, pub/sub hoặc atomic scripts phức tạp.

### 10.4. DynamoDB Accelerator (DAX)

DAX là **in-memory cache được thiết kế riêng cho DynamoDB**. Ứng dụng dùng DAX client tương thích để gửi những thao tác DynamoDB; DAX có thể cache các kết quả đọc và thực hiện write-through tới DynamoDB theo mô hình của dịch vụ.

Điểm cần hiểu:

- **Eventually consistent reads** có thể được phục vụ từ cache.
- **Strongly consistent reads** được chuyển tới DynamoDB theo semantics DAX hỗ trợ; không được kỳ vọng cache trả kết quả strong read như một local Redis GET.
- Write-through giúp cập nhật cache khi ứng dụng ghi qua DAX, nhưng thay đổi đi **ngoài DAX client path** cần được đánh giá về cache coherence/invalidation.
- DAX có item cache/query cache và các TTL/cấu hình liên quan; cần phân biệt freshness của từng loại result.
- DAX phù hợp khi workload chủ yếu là DynamoDB read patterns; không phải cache tổng quát cho RDS, HTTP response hay session arbitrary.

**Ví dụ quyết định:** một ứng dụng Java đã dùng DynamoDB SDK, read-heavy và chấp nhận eventual consistency có thể đánh giá DAX. Nếu ứng dụng cần Redis sorted set cho leaderboard hoặc distributed lock, hãy đánh giá ElastiCache Valkey/Redis OSS thay vì DAX.

### 10.5. Local cache + distributed cache

Một kiến trúc có thể dùng hai tầng:

~~~text
Application instance
  → L1 local cache (milliseconds, short TTL)
  → L2 ElastiCache (shared cache)
  → RDS/Aurora/DynamoDB (source of truth)
~~~

L1 giảm network hops nhưng mỗi instance có dữ liệu riêng. Nếu product price thay đổi, phải invalidate/refresh **cả L1 lẫn L2** hoặc đặt L1 TTL rất ngắn theo freshness contract. Đừng thêm L1 chỉ để cải thiện benchmark microseconds nếu chi phí invalidation và stale data vượt lợi ích.

## 11. Thiết kế cache key và value an toàn

### 11.1. Cache key phải bao gồm mọi chiều ảnh hưởng kết quả

Ví dụ key:

~~~text
product:v3:tenant-17:product-42:locale-vi
~~~

Nếu response phụ thuộc tenant, locale, currency, role, feature flags hoặc version, key cần thể hiện những dimension cần thiết. Nếu bỏ tenant ID, dữ liệu một tenant có thể bị trả cho tenant khác — đây là **data isolation/security bug**.

Một quy tắc hữu ích:

~~~text
cache key =
  domain + schemaVersion + tenant + entityId + relevantDimensions
~~~

Không nhét dữ liệu nhạy cảm, access token hoặc thông tin nhận dạng đầy đủ vào key; key có thể xuất hiện trong metrics/logs và cache inspection.

### 11.2. Serialization và schema version

Khi cache object Java, ứng dụng cần serialization format ổn định:

- JSON/MessagePack/CBOR hoặc format được kiểm soát.
- Có `schemaVersion` để phân biệt format khi deploy.
- Không mặc định Java native serialization an toàn cho dữ liệu không tin cậy.
- Xử lý cache entries được ghi bởi phiên bản ứng dụng cũ trong rolling deployment.
- Có TTL/namespace migration để dọn schema cũ.

Ví dụ envelope:

~~~json
{
  "schemaVersion": 3,
  "entityVersion": 18,
  "cachedAt": "2026-11-20T03:00:00Z",
  "value": {
    "productId": "product-42",
    "price": 350000
  }
}
~~~

`schemaVersion` nói về format cache; `entityVersion` nói về phiên bản dữ liệu nghiệp vụ. Hai giá trị có mục đích khác nhau.

### 11.3. Tránh cache nhầm kết quả lỗi

Không cache:

- HTTP 500/503 hoặc exception như thể đó là response hợp lệ.
- Authorization failure nếu key không bao gồm identity/permission context phù hợp.
- Một kết quả query bị timeout/cancel.
- Dữ liệu partial khi query chưa hoàn tất, trừ khi contract cho phép rõ.

Negative cache chỉ nên lưu **kết quả nghiệp vụ xác định** như “record không tồn tại” với TTL ngắn; không lưu “database tạm unavailable” như not found.

## 12. Java/Spring Boot: cache-aside với Spring Cache

Spring Cache abstraction cung cấp annotation để mô tả caching ở method boundary. Backend thực tế có thể là Redis/Valkey thông qua Spring Data Redis, Caffeine local cache hoặc provider khác.

### 12.1. Bật cache và định nghĩa service

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Ví dụ service:

~~~java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "product",
        key = "#tenantId + ':' + #productId",
        unless = "#result == null"
    )
    public Product find(String tenantId, String productId) {
        return repository.findByTenantIdAndId(tenantId, productId)
            .orElse(null);
    }

    @CacheEvict(
        cacheNames = "product",
        key = "#tenantId + ':' + #productId"
    )
    public void evict(String tenantId, String productId) {
        // Method này được dùng như một explicit invalidation command.
    }
}
~~~

Giải thích:

- `@Cacheable`: lookup cache trước; nếu miss thì chạy method và cache kết quả theo key.
- `key`: chứa tenant và product ID để tránh trộn dữ liệu giữa tenant.
- `unless`: bỏ cache khi kết quả là null, tránh negative cache ngoài ý muốn.
- `@CacheEvict`: xóa entry khi method chạy thành công theo mặc định `beforeInvocation=false`.

**Spring caching thường dùng proxy/AOP:** gọi method cacheable từ method khác trong cùng instance (self-invocation) có thể không đi qua proxy và annotation không được áp dụng như mong muốn. Kiểm tra cách gọi service và proxy mode.

SpEL key trong ví dụ dùng tên tham số `tenantId` và `productId`. Bảo đảm build giữ parameter names (ví dụ compiler flag `-parameters`) hoặc dùng vị trí tham số như `#p0`/`#p1` theo cấu hình Spring, nếu không expression có thể không resolve đúng.

### 12.2. Cấu hình TTL cho Redis cache

~~~java
@Configuration
public class CacheManagerConfig {
    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        org.springframework.data.redis.cache.RedisCacheConfiguration defaults =
            org.springframework.data.redis.cache.RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .disableCachingNullValues();

        Map<String, org.springframework.data.redis.cache.RedisCacheConfiguration> perCache =
            Map.of(
                "product",
                defaults.entryTtl(Duration.ofMinutes(5)),
                "profile",
                defaults.entryTtl(Duration.ofMinutes(20)),
                "hot-price",
                defaults.entryTtl(Duration.ofSeconds(30))
            );

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(perCache)
            .build();
    }
}
~~~

Đây là ví dụ Spring Data Redis; imports và bean wiring cần khớp Spring Boot/Spring Data version thực tế. TTL ở đây là **mặc định theo cache region**, không phải từng key tùy ý. Với TTL jitter theo entry hoặc freshness khác nhau, có thể dùng RedisTemplate/CacheWriter hoặc abstraction riêng.

### 12.3. Ghi cập nhật với `@CachePut`

~~~java
@CachePut(
    cacheNames = "product",
    key = "#tenantId + ':' + #productId"
)
public Product update(
        String tenantId,
        String productId,
        UpdateProductCommand command) {
    return repository.update(tenantId, productId, command);
}
~~~

`@CachePut` **luôn chạy method** rồi cập nhật cache bằng kết quả trả về, khác `@Cacheable` có thể bỏ qua method khi hit. Ví dụ minh họa write-through ở tầng application: repository commit xong method trả Product, sau đó Spring cache cập nhật cache. Nếu cache write thất bại sau DB commit, caller có thể nhận lỗi dù DB đã thay đổi; cần invalidation/reconciliation và idempotency ở API update.

### 12.4. Khi cần xóa nhiều keys

~~~java
@CacheEvict(cacheNames = "product", allEntries = true)
public void rebuildProductCatalog() {
    // Rebuild operation
}
~~~

`allEntries=true` có thể tạo lượng miss lớn ngay sau invalidation. Với cache lớn, cân nhắc versioned namespace, batch warm-up hoặc xóa theo nhóm thay vì flush toàn bộ khi traffic cao.

## 13. Redis/Valkey TTL và lệnh quan sát cơ bản

Các lệnh dưới đây minh họa giao thức Redis-compatible. Cú pháp/khả năng thực tế cần khớp engine và version.

### 13.1. Ghi key kèm TTL

~~~text
SET product:42 '{"price":350000}' EX 300

EX = 300 seconds
→ Entry có TTL 5 phút
~~~

~~~text
TTL product:42
PTTL product:42
~~~

- `SET ... EX 300`: ghi value và đặt TTL 300 giây trong cùng một lệnh.
- `TTL`: xem thời gian còn lại theo giây.
- `PTTL`: xem thời gian còn lại theo milliseconds.
- TTL trả số âm có thể biểu thị key không tồn tại hoặc key không có expiration theo semantics Redis; cần phân biệt mã trả về.

### 13.2. Xóa và cập nhật TTL

~~~text
DEL product:42
EXPIRE product:42 120
PERSIST product:42
~~~

- `DEL`: xóa key.
- `EXPIRE`: đặt lại TTL cho key đã tồn tại.
- `PERSIST`: loại bỏ expiration, khiến key không còn TTL.

**Cẩn trọng với PERSIST:** key cache không có TTL có thể chiếm memory lâu dài và làm tăng nguy cơ memory pressure. Không chạy lệnh thay đổi key production chỉ để thử trong console.

### 13.3. Không dùng KEYS * để kiểm tra production

Lệnh `KEYS *` có thể quét keyspace và gây latency/blocking tùy engine/khối lượng dữ liệu. Khi cần duyệt key, cân nhắc `SCAN` theo cursor, giới hạn COUNT và kiểm soát tải. Ngay cả SCAN cũng có thể trả duplicate keys hoặc quan sát keyspace thay đổi trong lúc scan; không dùng nó làm transaction snapshot.

### 13.4. Atomic update và giữ TTL

Một thao tác `SET` mới có thể **thay thế value và làm mất TTL cũ** nếu không truyền expiration/keep-TTL option phù hợp với engine/version. Khi cập nhật value:

- Đặt TTL trong cùng lệnh khi có thể.
- Hoặc dùng script/transaction được thiết kế để update value và TTL nguyên tử.
- Không giả định `GET` → `SET` → `EXPIRE` là atomic; crash giữa các bước có thể để key không TTL.

## 14. AWS architecture: cache trong ứng dụng nhiều tầng

### 14.1. Cache-aside với ElastiCache và RDS/Aurora

~~~mermaid
flowchart LR
    CLIENT["Web / Mobile"] --> ALB["ALB / API"]
    ALB --> APP["Spring Boot services\nECS / EKS / Lambda"]
    APP -->|"GET / SET / DEL"| CACHE["ElastiCache\nValkey / Redis OSS"]
    APP -->|"Miss / write"| DB["RDS / Aurora\nsource of truth"]
    DB -->|"Commit + outbox"| OUT["Outbox publisher"]
    OUT --> BUS["SQS / EventBridge"]
    BUS --> INV["Invalidation worker"]
    INV -->|"DEL / version bump"| CACHE
    CACHE -.-> MON["CloudWatch metrics"]
    DB -.-> MON
~~~

**Cache không phải source of truth** trong sơ đồ. Khi cache cluster mất dữ liệu, ứng dụng vẫn có thể đọc database và dựng lại entries, nhưng cần kiểm soát tải để không làm database quá tải.

### 14.2. Multi-AZ và replication

Với ElastiCache Valkey/Redis OSS, topology có thể gồm primary và replicas; khi bật các tùy chọn HA được hỗ trợ, dịch vụ có thể failover sang replica khi node gặp sự cố.

Lưu ý:

- Replication có thể **asynchronous**; một số writes mới nhất có thể chưa replicate khi node lỗi.
- Failover đổi primary và có thể làm mất connections đang mở.
- Client cần reconnect, khám phá topology/endpoint và retry operation an toàn.
- Read replicas có thể trả dữ liệu trễ hơn primary; không dùng replica cho read-after-write bắt buộc strong consistency.
- Snapshot/persistence là công cụ recovery tùy engine/cấu hình, không phải cam kết mọi cache write đều được phục hồi như database transaction.

Với cache-aside, mất một phần entries thường có thể phục hồi từ source of truth. Với session/counter/workflow state chưa persist, cần đánh giá lại liệu cache có đang bị dùng như database ngoài ý muốn.

### 14.3. Cluster mode và key distribution

Cluster mode enabled chia keyspace thành shards. Client phải hiểu **cluster redirection/topology** và xử lý MOVED/ASK hoặc cơ chế tương đương của protocol.

- Key cùng hash tag có thể được đặt cùng slot khi dùng pattern hash tag, ví dụ `cart:{user-42}:items` và `cart:{user-42}:total`.
- Hash tag quá tập trung có thể tạo hot shard.
- Multi-key operations/Lua scripts có thể bị giới hạn bởi yêu cầu keys ở cùng hash slot.
- Resharding có thể làm tăng network/latency; kiểm thử client và operations trước khi scale.

Đừng đặt mọi keys vào một hash tag chung chỉ để dùng multi-key commands — cách đó triệt tiêu lợi ích phân phối shards.

### 14.4. ElastiCache và VPC connectivity

ElastiCache thường được đặt trong VPC và truy cập từ workload được phép qua network/security group:

1. Chọn subnet group gồm các subnets phù hợp với topology.
2. Security group chỉ cho phép application security group truy cập port engine cần thiết.
3. Xác minh route, DNS, NACL và VPC peering/Transit Gateway nếu app ở VPC khác.
4. Bật TLS và cấu hình client trust/hostname validation.
5. Không expose cache endpoint trực tiếp ra Internet công cộng.

Một lỗi thường gặp là database Security Group đã mở cho ECS task nhưng cache Security Group chưa cho phép source group; app sẽ báo connection timeout dù cache cluster status vẫn Available.

## 15. Cache consistency và race conditions

### 15.1. Định nghĩa freshness contract

Trước khi chọn TTL, hãy trả lời:

- Dữ liệu được phép cũ tối đa bao lâu?
- Có yêu cầu read-after-write cho chính người dùng vừa cập nhật không?
- Có chấp nhận một user khác nhìn thấy dữ liệu cũ trong vài giây không?
- Giá, số dư, quyền truy cập hoặc tồn kho có mức rủi ro stale khác nhau không?
- Khi cache không truy cập được, app đọc DB, trả stale value hay từ chối request?

Một bảng contract minh họa:

| Dữ liệu | Freshness requirement | Pattern gợi ý |
| --- | --- | --- |
| Product description | Có thể cũ 5 phút | Cache-aside + TTL + event invalidation |
| Price/discount | Cần cập nhật nhanh | Cache-aside TTL ngắn + invalidation/version; kiểm tra giá ở DB trước checkout |
| Account balance | Không dùng cache làm kết quả chuẩn cho giao dịch | Đọc source of truth/strong consistency theo thiết kế |
| Feature flags | Có thể cũ vài giây | Cache ngắn + publish invalidation |
| Public reference data | Có thể cũ lâu hơn | Cache-aside TTL dài, refresh-ahead |

**Không dùng cache để quyết định cuối cùng một giao dịch tài chính hoặc authorization nhạy cảm** nếu source of truth phải được kiểm tra theo yêu cầu consistency.

### 15.2. Read-after-write

Một user vừa đổi tên profile rồi ngay sau đó GET profile. Nếu write commit DB nhưng invalidation event xử lý chậm, GET có thể trả cache cũ.

Các lựa chọn:

- Sau write, cập nhật/invalidate cache đồng bộ trước khi trả response.
- Trả dữ liệu vừa commit trực tiếp cho caller và dùng cache cho request tiếp theo.
- Dùng version token trong response/request để client yêu cầu tối thiểu version đó.
- Đọc thẳng database cho read-after-write window hoặc critical paths.

### 15.3. Race giữa cache fill và invalidation

~~~mermaid
sequenceDiagram
    participant A as Reader A
    participant B as Writer B
    participant D as Database
    participant C as Cache
    A->>C: GET key
    C-->>A: MISS
    A->>D: Read old value v10
    B->>D: Commit new value v11
    B->>C: DEL key
    A->>C: SET old value v10
    Note over A,C: Cache lại chứa dữ liệu cũ
~~~

Versioned key giúp request cũ chỉ ghi version 10, trong khi reader mới dùng version 11 nếu version pointer được cập nhật đáng tin cậy. Một cách khác là dùng lock/version check ở lúc fill. Không có một TTL đơn lẻ nào xóa hết race conditions.

### 15.4. Eventual consistency từ outbox

Khi outbox worker cập nhật cache bất đồng bộ:

- Database commit trước.
- Event có thể đến trễ hoặc lặp.
- Consumer phải idempotent và xử lý version ordering.
- Có thể nhận event version 12 sau version 13 nếu hệ thống cho phép reorder; không để event cũ ghi đè cache mới.
- Reconciliation định kỳ có thể phát hiện key/version lệch.

Ví dụ conditional update: chỉ ghi cache nếu incoming `entityVersion` **không nhỏ hơn** version hiện tại theo logic atomic của cache/datastore. Nếu không có atomic compare, phải thiết kế lại luồng.

## 16. TTL trong các dịch vụ AWS: không nhầm semantics

| Cơ chế | Ý nghĩa | Xóa khi nào? |
| --- | --- | --- |
| **ElastiCache Redis/Valkey TTL** | Thời hạn key trong cache | Engine hết hạn theo semantics của nó; key không còn được xem là hợp lệ |
| **Memcached expiration** | Thời hạn item cache | Theo quy tắc expiration của Memcached |
| **DAX item/query cache TTL** | Thời hạn kết quả cache DAX | Theo cấu hình và behavior dịch vụ |
| **DynamoDB TTL** | Thuộc tính expiration để xóa item khỏi bảng | Xóa **bất đồng bộ**, không đúng chính xác tại timestamp |
| **S3 Lifecycle expiration** | Quy tắc vòng đời object/version | Theo lifecycle processing, không phải cache miss |

### 16.1. DynamoDB TTL không phải Redis TTL

DynamoDB TTL dùng một thuộc tính Number biểu diễn **Unix epoch time tính bằng giây**. Khi timestamp đã qua, DynamoDB đủ điều kiện xóa item trong nền; việc xóa có thể trễ đáng kể.

Điều này có nghĩa:

- Item hết TTL vẫn có thể xuất hiện trong `GetItem`/`Query` trước khi bị xóa.
- Ứng dụng cần lọc `expiresAt` nếu không được phép dùng item đã hết hạn.
- TTL deletion không phải cơ chế chính xác để khóa session ngay lập tức.
- TTL không tự invalidate một Redis key khác đang cache cùng dữ liệu.

Ví dụ item:

~~~json
{
  "sessionId": "session-123",
  "userId": "user-42",
  "expiresAt": 1795143600
}
~~~

`expiresAt` là Unix seconds; không lưu ISO string nếu DynamoDB TTL được cấu hình cho attribute Number này.

### 16.2. DAX TTL khác DynamoDB TTL

DAX có TTL cho cache entries/query results theo cấu hình dịch vụ. Khi entry hết TTL, DAX cần lấy dữ liệu lại theo cơ chế cache của nó. DynamoDB TTL lại xóa item trong bảng gốc. Hai cơ chế có thể cùng tồn tại nhưng **không thay thế nhau**.

### 16.3. TTL của session và quyền truy cập

Với session/token metadata, TTL cache phải nằm trong **security contract**:

- Không để cache giữ quyền truy cập sau khi token/session bị revoke nếu yêu cầu revoke tức thì.
- Có thể cần denylist/version check hoặc invalidate theo event logout/role change.
- Cache outage không được khiến authorization chuyển sang allow-by-default.
- Không cache authorization result quá lâu nếu quyền thay đổi thường xuyên.

## 17. Bảo mật cache trên AWS

### 17.1. Network isolation

- Đặt ElastiCache trong private networking phù hợp; không mở endpoint cache ra public Internet.
- Security group chỉ cho phép source application groups và ports cần thiết.
- Phân tách production/staging/dev bằng VPC, subnets, security groups hoặc boundary thích hợp.
- Với VPC peering/Transit Gateway, kiểm tra routing, DNS và security boundaries ở cả hai phía.

### 17.2. Encryption và authentication

- Bật **encryption in transit (TLS)** khi engine/config hỗ trợ và client xác minh certificate/hostname.
- Bật **encryption at rest** theo yêu cầu; quản lý KMS key policy, rotation và quyền decrypt.
- Dùng AUTH token/user groups/ACL hoặc cơ chế IAM authentication được engine/service hỗ trợ.
- Không hardcode credentials trong source code, image, logs hoặc shell history.
- Rotate secrets có kế hoạch để client pools không bị outage hàng loạt.

Khả năng TLS, AUTH, ACL, IAM authentication và encryption options phụ thuộc **engine, engine version, node type và deployment mode**. Kiểm tra đúng feature matrix trước khi viết IaC.

### 17.3. Least privilege

Tách:

- **Application role:** chỉ có quyền kết nối đến cache qua network và credentials cần thiết.
- **Provisioning role:** tạo/đổi cluster, parameter group, subnet group.
- **Operations role:** quan sát metrics/logs, failover/scale theo quy trình.
- **Security role:** quản lý secrets, KMS keys, audit và policy.

Không cấp quyền quản trị toàn bộ AWS cho application chỉ vì ứng dụng cần đọc/ghi cache. IAM không thay thế network security và cache ACL; cần cả hai lớp.

### 17.4. Multi-tenant isolation

Cache key nên có tenant namespace và code phải kiểm tra tenant authorization ở application layer. Một key khó đoán **không phải** cơ chế phân quyền. Với dữ liệu nhạy cảm, cân nhắc cache namespace riêng, encryption và phân tách workload theo mức độ cô lập cần thiết.

## 18. Resilience: khi cache chậm hoặc không truy cập được

### 18.1. Cache failure policy

| Tình trạng | Hành vi cần thiết kế |
| --- | --- |
| Cache GET timeout | Fail-open đọc DB có giới hạn, hoặc trả stale value nếu được phép |
| Cache SET lỗi sau DB commit | Giữ DB là source of truth, phát invalidation/reconciliation |
| Cache cluster unavailable | Circuit breaker, bulkhead, giới hạn DB fallback |
| Cache trả corrupt/deserialize lỗi | Bỏ entry, log metric, reload từ source of truth |
| Failover/reconnect | Client reconnect với backoff/jitter, không retry vô hạn |
| Memory full/eviction | Theo dõi evictions/write errors, scale/tune TTL/policy |

### 18.2. Timeout ngắn và bulkhead

Cache được dùng để giảm latency; nếu cache GET có timeout 5 giây thì request có thể chậm hơn truy vấn DB. Đặt timeout theo latency budget, có connection pool riêng và không để thread pool bị chiếm vô hạn.

Khi cache unavailable:

1. Circuit breaker mở sau ngưỡng lỗi.
2. Application không tiếp tục chờ từng request cache timeout.
3. Fallback DB có semaphore/concurrency cap.
4. Khi cache hồi phục, đóng circuit theo half-open probes.
5. Warm-up có giới hạn để tránh cache stampede sau outage.

### 18.3. Stale-if-error

Với dữ liệu có freshness contract cho phép, có thể lưu metadata `cachedAt`/`staleUntil` và trả stale entry trong thời gian ngắn khi source of truth hoặc cache refresh gặp lỗi. Tuy nhiên:

- Không dùng stale-if-error cho số dư, quyền truy cập hoặc giá checkout nếu nghiệp vụ yêu cầu dữ liệu mới.
- Stale window phải có giới hạn rõ.
- Gắn metric để biết bao nhiêu response đã dùng stale data.
- Background refresh phải idempotent và có concurrency control.

### 18.4. Warm-up sau deploy/failover

Không preload toàn bộ database vào cache một lúc. Xác định **working set** dựa trên access logs/metrics, warm những key hot theo batch, giới hạn QPS và quan sát DB. Với cache-aside, có thể để traffic tự làm nóng nếu database chịu được cold-start miss.

## 19. Monitoring và metrics cho cache trên AWS

Cache có thể vẫn trả request thành công trong khi memory gần đầy, eviction tăng hoặc latency đang xấu đi. Cần kết hợp **CloudWatch metrics, application metrics và database metrics**.

### 19.1. ElastiCache metrics cần quan sát

| Metric (tên phổ biến) | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| **CacheHits** | Số lần đọc cache hit | Giảm đột ngột sau deploy/flush |
| **CacheMisses** | Số lần đọc cache miss | Tăng cao làm database load tăng |
| **Evictions** | Số keys bị loại do memory policy | Tăng liên tục có thể thiếu memory/TTL policy không phù hợp |
| **CurrConnections** | Số client connections hiện tại | Tăng bất thường, connection leak |
| **EngineCPUUtilization** | CPU của cache engine | CPU cao dù node CPU tổng thể chưa cao |
| **CPUUtilization** | CPU node | Saturation hoặc workload mất cân bằng |
| **FreeableMemory / BytesUsedForCache** | Memory còn lại / memory cache sử dụng | Thiếu headroom, nguy cơ eviction/write failure |
| **ReplicationLag** | Độ trễ replication khi metric được hỗ trợ | Read replica có thể stale |
| **NetworkBytesIn/Out** | Throughput mạng | Băng thông, payload lớn hoặc client burst |

Metric names/dimensions có thể khác theo engine và node type. Đọc đúng namespace **AWS/ElastiCache**, dimensions của replication group/cache cluster/node và tài liệu metrics hiện hành.

### 19.2. Application metrics bổ sung

CloudWatch không tự biết một cache hit có trả dữ liệu stale hay business result đúng. Ứng dụng nên phát:

- **cache_lookup_total** với nhãn cache name và kết quả hit/miss/error.
- **cache_lookup_latency**.
- **cache_fill_total** và **cache_fill_error_total**.
- **cache_invalidation_lag_seconds**.
- **cache_stale_response_total**.
- **cache_fallback_db_total**.
- **cache_deserialization_error_total**.
- **cache_stampede_lock_wait_seconds**.

Không gắn tenant ID, user ID hoặc cache key đầy đủ vào metric labels với cardinality lớn. Dùng dimensions có giới hạn và log correlation IDs theo chính sách.

### 19.3. DAX metrics

Với DAX, theo dõi cache hits/misses cho item/query/scan caches theo loại workload, request count, throttling, CPU/memory và latency. Một hit ratio tổng hợp có thể che khuất việc **ItemCache hit cao nhưng QueryCache miss cao**; hãy xem đúng nhóm operation mà ứng dụng đang gọi.

Đồng thời theo dõi DynamoDB:

- Consumed read/write capacity hoặc request units theo billing mode.
- Throttled requests.
- Latency và system errors.
- Hot partitions/key skew.

Nếu DAX giảm read latency nhưng không giảm DynamoDB load như dự kiến, kiểm tra consistency mode, query patterns và những requests không được cache.

### 19.4. Đặt alarm theo symptom

~~~text
Warning:
  Evictions tăng liên tục trong 10 phút
  CacheMisses tăng mạnh so với baseline
  EngineCPUUtilization vượt ngưỡng đã benchmark

Critical:
  Cache connection errors tăng
  Application fallback DB vượt concurrency budget
  Database CPU/connection pool đồng thời tăng

Recovery:
  Cache hits phục hồi
  Evictions/latency trở về baseline
  Database load giảm
~~~

Không dùng một ngưỡng CPU cố định cho mọi node family/workload. Đặt alarm theo **baseline, latency SLO và downstream capacity**.

## 20. Capacity planning và chi phí

### 20.1. Cache có thể giảm database cost nhưng tăng chi phí tổng

Chi phí cache có thể gồm:

- ElastiCache node hours/Serverless capacity theo mô hình giá đang dùng.
- Replicas, shards, Multi-AZ và node family.
- Data transfer, cross-AZ traffic và network.
- Backups/snapshots, storage, monitoring/logging.
- DAX node hours và các chi phí DynamoDB còn lại.
- Application compute và operational overhead.

So sánh chi phí phải tính **toàn hệ thống**:

~~~text
Net benefit =
  Database cost avoided
  + latency/SLO value
  - Cache service cost
  - Added network/monitoring cost
  - Engineering/operations cost
~~~

Cache hit ratio cao không tự động đồng nghĩa tiết kiệm nếu node cache được provision quá lớn hoặc data transfer đắt.

### 20.2. Ước lượng hit rate và database offload

Giả sử:

~~~text
Read requests/day       = 50.000.000
Expected hit ratio      = 90%
Database reads avoided  = 45.000.000/day
Database reads remaining=  5.000.000/day
~~~

Đây là phép tính lý tưởng giả định mỗi hit thay thế một DB read tương đương. Trong thực tế:

- Một miss có thể phát sinh nhiều DB queries.
- Một cache entry có thể phục vụ nhiều loại request.
- TTL/invalidation làm hit ratio thay đổi theo thời gian.
- Query cost và request units không đồng nhất.
- Stale reads có thể làm sai nghiệp vụ nếu không được chấp nhận.

### 20.3. Sizing theo working set

Không cần cache mọi row trong database. Xác định:

1. **Working set:** những keys thường được truy cập trong cửa sổ thời gian đại diện.
2. Kích thước payload thực sau serialization.
3. Overhead key/object, fragmentation và metadata.
4. Replication memory, buffers, client connections.
5. Headroom cho burst, failover và resharding.
6. Eviction rate có thể chấp nhận.

Benchmark với key distribution **Zipf/hot-key** gần production. Benchmark chỉ dùng keys uniform có thể bỏ sót hot shard và stampede.

### 20.4. So sánh chi phí trước/sau

| Chỉ số | Trước cache | Sau cache (mục tiêu) |
| --- | --- | --- |
| Database reads | 100% baseline | Giảm theo hit ratio thực |
| DB CPU/connection | Cao ở peak | Giảm nhưng vẫn đủ headroom |
| API p95/p99 | Theo baseline | Cải thiện có đo lường |
| Cache service cost | 0 | Tăng theo node/throughput |
| Data freshness | DB read trực tiếp | Có stale window/invalidation |
| Operational complexity | Ít thành phần | Tăng do cache, failover, keys, TTL |

Hãy đánh giá trên cùng workload/time window và cùng mức traffic; tránh so một ngày thấp tải với một ngày cao tải.

## 21. AWS CLI chỉ đọc: kiểm tra cấu hình cache

Các lệnh sau chỉ đọc metadata, không tạo, sửa, reboot hoặc xóa cluster. Thay Region/identifier bằng tài nguyên bạn được phép quan sát.

### 21.1. Xem ElastiCache clusters

~~~bash
aws elasticache describe-cache-clusters \
  --region ap-southeast-1 \
  --show-cache-node-info \
  --query "CacheClusters[].{Id:CacheClusterId,Engine:Engine,Version:EngineVersion,Status:CacheClusterStatus,NodeType:CacheNodeType,Nodes:NumCacheNodes}" \
  --output table
~~~

Đối chiếu engine, version, node type và số nodes. Không mặc định lệnh **describe-cache-clusters** là đủ để hiểu toàn bộ replication group/cluster-mode topology.

### 21.2. Xem replication groups

~~~bash
aws elasticache describe-replication-groups \
  --region ap-southeast-1 \
  --query "ReplicationGroups[].{Id:ReplicationGroupId,Status:Status,ClusterMode:ClusterEnabled,MultiAZ:MultiAZ,AutomaticFailover:AutomaticFailover,NodeGroups:NodeGroups}" \
  --output json
~~~

Kiểm tra cluster mode, Multi-AZ, automatic failover và node group membership. Endpoint/configuration details thay đổi theo topology; không hardcode IP từ output vào ứng dụng.

### 21.3. Xem parameter groups

~~~bash
aws elasticache describe-cache-parameters \
  --region ap-southeast-1 \
  --cache-parameter-group-name cache-lab-params \
  --output json
~~~

Parameter group và supported parameters phụ thuộc engine/version. Lệnh này không áp dụng thay đổi; muốn sửa parameter cần quy trình change riêng.

### 21.4. Xem DAX clusters

~~~bash
aws dax describe-clusters \
  --region ap-southeast-1 \
  --query "Clusters[].{Name:ClusterName,Status:Status,NodeType:NodeType,Nodes:TotalNodes,Endpoint:ClusterDiscoveryEndpoint}" \
  --output json
~~~

DAX endpoint dùng với DAX client tương thích. Không đưa endpoint này vào Redis client hoặc Spring Data Redis connection factory.

### 21.5. Xem CloudWatch metrics metadata

~~~bash
aws cloudwatch list-metrics \
  --region ap-southeast-1 \
  --namespace AWS/ElastiCache \
  --metric-name CacheHits

aws cloudwatch list-metrics \
  --region ap-southeast-1 \
  --namespace AWS/ElastiCache \
  --metric-name Evictions
~~~

Lệnh **list-metrics** liệt kê series metadata, không trả chuỗi datapoints để phân tích. Dùng CloudWatch Console hoặc **get-metric-data** với dimensions/time range phù hợp để xem trend.

## 22. Case study: cache-aside cho product catalog

### 22.1. Bối cảnh

Một cửa hàng có:

~~~text
Application:       Spring Boot trên ECS Fargate
Source of truth:   Amazon Aurora PostgreSQL
Cache:             Amazon ElastiCache Valkey
Traffic:           8.000 product reads/s ở peak (giả định)
Writes:            20 product updates/s
Freshness target:  Mô tả < 5 phút; giá < 30 giây
Availability:      Cache có thể fail nhưng DB phải được bảo vệ
~~~

### 22.2. Thiết kế

- Cache-aside cho product detail.
- Key gồm schema version, tenant ID, product ID và locale.
- TTL description 5 phút; price 30 giây kèm event invalidation.
- DB update và outbox event trong một transaction.
- Worker đọc outbox, xóa/version bump các keys liên quan.
- TTL jitter giảm avalanche khi warm cache.
- Single-flight refresh cho hot products.
- Application fallback DB qua semaphore/concurrency cap khi cache lỗi.
- ElastiCache đặt trong private subnets, TLS/auth và Multi-AZ topology phù hợp.

### 22.3. Flow cập nhật giá

~~~mermaid
sequenceDiagram
    participant API as Product API
    participant DB as Aurora
    participant O as Outbox
    participant Q as SQS
    participant W as Invalidation worker
    participant C as ElastiCache
    API->>DB: UPDATE price + INSERT outbox
    DB-->>API: Commit
    API-->>API: Return committed product
    O->>Q: Publish ProductPriceChanged
    Q->>W: Deliver event
    W->>C: DEL / version bump
    Note over C: Next request loads latest value
~~~

Event có thể được xử lý trễ hoặc lặp, nên worker idempotent. Trong khoảng trước invalidation, cache có thể trả giá cũ tối đa theo contract; checkout vẫn phải xác minh giá trên source of truth trước khi xác nhận giao dịch.

### 22.4. Khi cache cluster failover

1. Client nhận timeout/connection reset và reconnect theo backoff.
2. Circuit breaker giới hạn requests đang chờ cache.
3. Application fallback DB có concurrency cap, không cho 8.000 requests/s dồn thẳng vào Aurora.
4. Sau khi cache hồi phục, warm key hot theo batch.
5. Quan sát hit ratio, eviction, DB CPU và p99 API để xác nhận recovery.

### 22.5. Kết quả cần đo

Không đặt mục tiêu “hit ratio 99%” một cách tùy ý. Đo:

- Database QPS và CPU trước/sau.
- Cache hit/miss ratio theo cache region.
- p50/p95/p99 latency của product endpoint.
- Invalidation lag và stale response count.
- Cache memory/evictions và hot shard load.
- Cost của ElastiCache, data transfer và phần database giảm được.

## 23. Bài tập củng cố

### Bài tập 1 — Cache-aside

Một request GET product lần đầu không có cache entry. Hãy mô tả thứ tự các bước.

**Gợi ý:** lookup cache → miss → đọc source of truth → fill cache với TTL → trả dữ liệu. Lần đọc tiếp theo có thể hit.

### Bài tập 2 — Write-through và lỗi một phần

Database commit thành công nhưng Redis SET lỗi. API có nên trả thành công không?

**Gợi ý:** phụ thuộc API contract. Database đã commit nên không được giả định rollback; cần invalidation/outbox/reconciliation. Caller cần biết kết quả nghiệp vụ và không được retry write mù gây duplicate.

### Bài tập 3 — Chọn TTL

Product description thay đổi vài lần mỗi ngày; giá flash sale thay đổi mỗi phút. Có nên dùng cùng TTL 30 phút?

**Gợi ý:** không. Chọn TTL theo freshness risk; giá cần TTL ngắn/invalidation event và kiểm tra source of truth ở checkout.

### Bài tập 4 — Cache stampede

Một key hết hạn và 2.000 requests đồng thời miss. Đề xuất ít nhất ba biện pháp.

**Gợi ý:** single-flight, distributed lock an toàn, stale-while-revalidate, refresh-ahead, TTL jitter và DB fallback limit.

### Bài tập 5 — TTL và DynamoDB

Một DynamoDB item có **expiresAt** đã qua nhưng vẫn xuất hiện trong Query. Có phải TTL bị lỗi?

**Gợi ý:** không nhất thiết. DynamoDB TTL xóa bất đồng bộ; ứng dụng cần lọc timestamp nếu không được dùng item hết hạn.

### Bài tập 6 — Chọn AWS service

Ứng dụng cần Redis sorted set để xếp hạng người chơi. Nên chọn DAX hay ElastiCache?

**Gợi ý:** ElastiCache Valkey/Redis OSS phù hợp data structure sorted set. DAX chỉ chuyên cho DynamoDB.

### Bài tập 7 — Memcached node mất

Một node Memcached bị thay thế và nhiều keys mất. Hệ thống có mất dữ liệu chuẩn không?

**Gợi ý:** nếu cache chỉ giữ bản sao có thể tái tạo, database vẫn là source of truth; ứng dụng chịu cache misses và cần bảo vệ DB khỏi cold-start surge.

### Bài tập 8 — Tenant leakage

Cache key chỉ gồm product ID, nhưng cùng product ID có thể tồn tại trong hai tenants với giá khác nhau. Điều gì có thể xảy ra?

**Gợi ý:** một tenant có thể nhận giá của tenant khác. Thêm tenant namespace và kiểm tra authorization; key khó đoán không thay thế phân quyền.

### Bài tập 9 — Eviction tăng

Hit ratio giảm và **Evictions** tăng liên tục. Những hướng điều tra nào cần thực hiện?

**Gợi ý:** working set/memory sizing, value size, TTL, eviction policy, hot keys, replication overhead và memory fragmentation.

### Bài tập 10 — DAX consistency

Một màn hình cần strongly consistent read sau khi cập nhật DynamoDB nhưng ứng dụng đọc qua DAX. Cần kiểm tra gì?

**Gợi ý:** DAX strongly consistent reads được chuyển tới DynamoDB theo semantics hỗ trợ; xác nhận client/API call thực sự yêu cầu strong consistency, không giả định mọi cache read đều strong.

### Bài tập 11 — Cache outage

ElastiCache mất kết nối trong khi traffic vẫn ở peak. Vì sao fail-open không giới hạn có thể làm Aurora sập?

**Gợi ý:** mọi request miss/fallback cùng lúc dồn về DB. Dùng circuit breaker, bulkhead, semaphore, rate limit và stale policy phù hợp.

### Bài tập 12 — Invalidation race

Reader A đọc version 10, writer B commit version 11 và xóa key, sau đó A ghi version 10 trở lại cache. Làm sao giảm rủi ro?

**Gợi ý:** versioned keys, conditional version checks/atomic scripts, lock/coalescing và outbox ordering; TTL chỉ giới hạn stale window chứ không xóa race.

## 24. Checklist triển khai production

- [ ] Đã xác định source of truth và freshness contract theo từng loại dữ liệu.
- [ ] Pattern cache-aside/write-through/write-around/write-behind phù hợp read/write ratio.
- [ ] Cache keys bao gồm tenant, locale, version và các dimension ảnh hưởng kết quả.
- [ ] TTL có cơ sở từ SLA, có jitter/refresh strategy khi phù hợp.
- [ ] Invalidation sau DB commit có outbox/retry/idempotency hoặc reconciliation.
- [ ] Cache stampede, hot keys, negative caching và cache avalanche đã được kiểm thử.
- [ ] Eviction policy, working set, memory headroom và node sizing đã benchmark.
- [ ] Đã chọn đúng ElastiCache Valkey/Redis OSS, Memcached, DAX hoặc local cache theo access pattern.
- [ ] Cluster mode/client topology, Multi-AZ, failover và reconnect đã kiểm thử.
- [ ] Application cache timeout ngắn, circuit breaker/bulkhead và DB fallback concurrency cap.
- [ ] Dữ liệu nhạy cảm không bị lộ trong key/value/logs; tenant isolation được xác thực.
- [ ] TLS, encryption at rest, secrets, ACL/IAM và security groups được cấu hình theo least privilege.
- [ ] CloudWatch/application metrics có hit/miss, latency, evictions, memory, replication lag và stale response.
- [ ] Có runbook cache failover, warm-up, cache flush/invalidation và downstream overload.
- [ ] Chi phí cache, data transfer, replicas, backups và database savings đã được so sánh.
- [ ] Cache không được dùng làm durable source of truth nếu chưa có durability/recovery design riêng.

## 25. Ghi nhớ

**Cache-aside, write-through và TTL** là ba quyết định bổ sung cho nhau:

1. **Cache-aside** giúp ứng dụng chỉ nạp những dữ liệu thực sự được đọc; miss sẽ đọc source of truth rồi fill cache.
2. **Write-through** giữ cache và backing store được cập nhật trong cùng luồng ghi theo một contract rõ; nó không tạo distributed ACID transaction tự động.
3. **TTL** giới hạn freshness window; invalidation theo event giúp phản ứng nhanh khi dữ liệu thay đổi.
4. Cache có thể stale, bị eviction hoặc mất khi node lỗi. Cần idempotency, outbox, cache stampede protection, bounded fallback và reconciliation.
5. **ElastiCache Valkey/Redis OSS**, **Memcached** và **DAX** phục vụ các workload khác nhau. DAX chuyên cho DynamoDB, không thay Redis.
6. TTL của Redis/Memcached/DAX khác **DynamoDB TTL**, vốn xóa item bất đồng bộ.
7. Cache chỉ có giá trị khi hệ thống đo được latency, correctness, downstream load và cost — không chỉ hit ratio.

Thiết kế cache tốt không phải là cache càng nhiều càng tốt. Đó là chọn đúng dữ liệu có thể tái tạo, đặt freshness contract rõ, bảo vệ source of truth khi cache miss/outage và chứng minh được lợi ích bằng số liệu production.

### Tài liệu AWS chính thức

- [Amazon ElastiCache User Guide](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.html) — kiến trúc và vận hành ElastiCache.
- [ElastiCache for Valkey](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.core.html) — engine Valkey và các khái niệm.
- [ElastiCache for Redis OSS](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.core.html) — Redis OSS-compatible deployment.
- [ElastiCache for Memcached](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.core.html) — cache nodes và Memcached.
- [ElastiCache best practices](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/BestPractices.html) — sizing, connections và vận hành.
- [ElastiCache metrics](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/CacheMetrics.html) — CloudWatch metrics.
- [ElastiCache security](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.Overview.html) — network và bảo mật dịch vụ.
- [DynamoDB Accelerator (DAX)](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.html) — DAX architecture và client.
- [DAX consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.consistency.html) — strongly/eventually consistent reads.
- [DynamoDB TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html) — expiration và xóa item bất đồng bộ.
- [Redis commands](https://redis.io/docs/latest/commands/) — TTL, EXPIRE, eviction và key operations.
- [Spring Cache abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html) — cache annotations.
- [Spring Data Redis](https://docs.spring.io/spring-data/redis/reference/redis.html) — Redis connections, templates và cache manager.
- [Amazon ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/) — node/capacity và chi phí.
- [Amazon DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/) — đánh giá chi phí khi dùng DAX và DynamoDB.
