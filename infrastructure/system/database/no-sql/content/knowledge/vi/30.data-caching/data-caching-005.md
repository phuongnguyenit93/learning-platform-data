# Eviction, giới hạn bộ nhớ và sự khác biệt với xóa dữ liệu gốc

Trong một hệ thống NoSQL phục vụ lượng truy cập lớn, **bộ nhớ đệm (cache)** thường được đặt trước cơ sở dữ liệu gốc để giảm độ trễ, bớt số lần đọc, giảm chi phí truy vấn và tránh làm quá tải các phân vùng dữ liệu nóng. Cache có thể là `Caffeine` bên trong ứng dụng Java, Redis/Memcached bên ngoài, bộ nhớ của một proxy, một lớp near-cache gần client hoặc nhiều tầng kết hợp.

Nhưng RAM có giới hạn. Khi lượng dữ liệu vượt ngân sách bộ nhớ, cache phải chọn dữ liệu nào được giữ và dữ liệu nào bị loại. Quá trình loại mục này gọi là **eviction**. Một lập trình viên có thể quan sát thấy key `product:SKU-42` biến mất khỏi Redis rồi tưởng rằng sản phẩm đã bị xóa trong MongoDB hoặc DynamoDB; thực tế, nếu Redis chỉ giữ một bản sao được phép tái tạo, cache miss đơn giản khiến ứng dụng cần đọc lại dữ liệu từ nguồn. Ngược lại, nếu **Redis chính là nơi lưu dữ liệu có thẩm quyền**, cho phép một chính sách eviction xóa key có thể trở thành mất dữ liệu nghiệp vụ.

Hãy xét một luồng đọc sản phẩm:

~~~text
Client
  |
  v
Java ProductService
  | 1. GET product:tenant-A:SKU-42
  v
Redis Cache  -- key bị eviction vì thiếu bộ nhớ --> MISS
  |
  | 2. Cache miss không có nghĩa sản phẩm bị xóa.
  v
NoSQL Source of Truth (Product Collection)
  | 3. Read authoritative Product.
  v
Java Service -- 4. Populate cache -- trả kết quả
~~~

Trong mô hình này, eviction làm **mất lợi ích tăng tốc** và có thể gây tăng tải lên database, nhưng **không tự thực hiện lệnh xóa sản phẩm gốc**. Tuy vậy, nếu xóa sản phẩm ở database mà cache còn bản cũ, ứng dụng có thể tiếp tục hiển thị một sản phẩm đã bị xóa. Do đó, phân biệt eviction, expiration, invalidation và **deletion tại nguồn có thẩm quyền** là nền tảng để thiết kế đúng.

Bài học thuộc chương **Bộ nhớ đệm dữ liệu** của module **Database No SQL** sẽ phân tích chính sách giữ/loại cache entries, ý nghĩa thực tế của giới hạn bộ nhớ, các trường hợp Redis và Java, cache-aside, write-through, write-behind, TTL, invalidation, concurrency, sizing, monitoring, sự cố và kiểm thử.

> **Nguyên tắc xuyên suốt:** Trước khi cấu hình eviction, hãy trả lời **“cache này có thể bị xóa hoàn toàn rồi tái tạo từ đâu, với điều kiện gì?”**. Nếu không có câu trả lời an toàn, tầng lưu trữ đó có thể không phải là một cache thuần túy.

## 1. Bản đồ thuật ngữ: eviction, expiry, invalidation, delete

Các từ “mất key”, “xóa cache”, “hết hạn”, “xóa bản ghi” thường bị dùng thay thế nhau dù ngữ nghĩa khác:

| Thuật ngữ | Tác nhân kích hoạt | Đối tượng bị tác động | Có phải xóa dữ liệu gốc không? |
|---|---|---|---|
| **Eviction** | Áp lực bộ nhớ hoặc chính sách admission/capacity | Cache entry | **Không**, nếu nguồn nằm ngoài cache |
| **Expiration/expiry** | TTL, thời hạn idle hoặc quy tắc hết hiệu lực | Cache entry hoặc record tùy loại store | Phụ thuộc nơi áp TTL |
| **Invalidation** | Ứng dụng, event, version hoặc policy nhận ra dữ liệu cache không còn hợp lệ | Cache entry, namespace hoặc tag | Thường không xóa dữ liệu gốc |
| **Explicit cache deletion** | `DEL cache-key`, `cache.invalidate(key)` | Entry ở cache | Không nếu thao tác chỉ tới cache |
| **Source deletion** | Nghiệp vụ yêu cầu xóa record gốc | Authoritative database | **Có** |
| **Logical deletion** | Cập nhật `deleted=true` hoặc ghi tombstone | Trạng thái ở source | Có thay đổi ngữ nghĩa record |
| **Storage TTL deletion** | TTL của chính database gốc | Record trong nguồn, theo semantics sản phẩm | **Có thể có**, không phải eviction cache |
| **Process GC/OS reclaim** | JVM GC, OS memory pressure | Object memory hoặc process | Không trực tiếp là source deletion |

### 1.1. Cùng một động từ “delete”, hai đối tượng

~~~text
cache.delete("product:SKU-42")
    => bỏ bản sao tăng tốc.

productRepository.deleteById("SKU-42")
    => thực hiện thao tác xóa nghiệp vụ tại source.
~~~

Hai lệnh không thể được coi là tương đương chỉ vì đều có chữ `delete`.

### 1.2. TTL cũng là một hợp đồng theo tầng

`SET cache-key value EX 300` đặt thời hạn trong cache. Nó **không** yêu cầu NoSQL source xóa document sau năm phút. Nếu database gốc tự có TTL field/index, đó là **cơ chế khác** và có thể làm record nguồn hết hạn thật sự.

### 1.3. Cache entry có thể bị loại dù TTL còn xa

Một key có TTL một giờ vẫn có thể bị eviction sau vài giây vì memory pressure. **TTL thường đặt giới hạn thời gian hiệu lực, không phải bảo đảm residency trong RAM**.

### 1.4. TTL đến hạn không đồng nghĩa giải phóng RAM ngay

Nhiều hệ có lazy/active expiration hoặc cleanup bất đồng bộ. Key hết hạn có thể bị coi là vô hiệu ở read path trước khi vật lý bị dọn hết. Monitoring cần phân biệt expired logical entries và memory reclaim.

## 2. “Dữ liệu gốc” là gì và ai là nguồn có thẩm quyền?

Một kiến trúc điển hình:

~~~mermaid
flowchart LR
    APP["Java Application"] --> LC["L1 In-process Cache"]
    LC --> RC["L2 Redis Cache"]
    RC --> ORIG["NoSQL Source of Truth"]
    ORIG --> CHANGE["CDC / Outbox Events"]
    CHANGE --> INVALIDATE["Invalidation / Refresh"]
    INVALIDATE --> RC
    INVALIDATE --> LC
~~~

**Source of truth** là nơi ứng dụng dựa vào để xác định trạng thái chính thức của một thực thể và thực thi các bất biến nghiệp vụ. Cache thường giữ **bản sao có thể tái tạo** hoặc kết quả tính toán từ nguồn.

### 2.1. Vai trò là quyết định kiến trúc, không phải thuộc tính của tên sản phẩm

- MongoDB có thể là source of truth cho sản phẩm.
- Redis có thể chỉ là cache của MongoDB.
- Redis cũng có thể được dùng như nguồn có thẩm quyền cho một trạng thái cụ thể, nếu ứng dụng thiết kế durability/failover phù hợp.
- Memcached thường được dùng làm cache tạm thời, nhưng vẫn phải xác định liệu hệ có trông cậy vào nó cho state không thể tái tạo.
- In-process cache trong JVM mất khi service restart; không nên là nơi duy nhất lưu giao dịch quan trọng.

Không được áp kết luận “eviction không bao giờ mất dữ liệu” cho một Redis deployment đang đóng vai trò **nguồn duy nhất của session/quota/queue/ledger**.

### 2.2. Câu hỏi kiểm tra một cache có thể mất được không

1. Nếu `FLUSHDB` hoặc restart JVM làm mất tất cả entries, hệ có phục hồi đầy đủ từ nguồn không?
2. Trong lúc chưa warm-up, ứng dụng có phục vụ đúng kết quả hoặc trả lỗi phù hợp không?
3. Có entry nào chứa kết quả write chưa được ghi vào nguồn không?
4. Có state như payment token, one-time nonce, reservation, quota không thể tính lại?
5. Có metadata chống duplicate/idempotency chỉ nằm ở cache không?
6. Nếu TTL/eviction xóa entry, có làm mất quyền xác nhận một giao dịch đã commit không?

Một câu trả lời “không thể tái tạo” báo hiệu cache đang giữ **dữ liệu có thẩm quyền hoặc state cần durable workflow**, phải đánh giá lại giới hạn bộ nhớ và eviction policy.

### 2.3. Rebuild được không đồng nghĩa rebuild rẻ

Một cache kết quả báo cáo được tính từ database có thể tái tạo đúng, nhưng chi phí tính lại rất lớn. Eviction quá mạnh làm CPU/DB tăng và p99 latency xấu. Tính đúng đắn và tính kinh tế đều cần xem xét, nhưng chúng không phải một vấn đề.

### 2.4. Cache-aside có thể dùng khi nguồn tạm không sẵn sàng?

Nếu Redis hit, có thể trả dữ liệu cũ theo policy; nếu miss mà nguồn down, không thể “bịa” authoritative state. Trả stale cached view, fallback khác hay `503` là quyết định **có chủ đích theo use case**, đặc biệt với tồn kho và quyền truy cập.

## 3. Vòng đời một cache entry

~~~mermaid
stateDiagram-v2
    [*] --> Absent
    Absent --> Present: Fill / write cache
    Present --> Present: Hit / refresh / update metadata
    Present --> Expired: TTL or idle timeout
    Present --> Evicted: Memory pressure / capacity policy
    Present --> Invalidated: Source changed / explicit invalidate
    Present --> Removed: Explicit cache delete
    Expired --> Absent
    Evicted --> Absent
    Invalidated --> Absent
    Removed --> Absent
    Absent --> Present: Future cache fill
~~~

Trong sơ đồ, **Absent** chỉ nói cache hiện không có usable entry; không kết luận trạng thái của database gốc.

### 3.1. Cache hit

Ứng dụng tìm thấy entry phù hợp với key và policy độ mới. Cache hit về mặt kỹ thuật chưa chứng minh dữ liệu **đủ mới cho nghiệp vụ** nếu invalidation bị trễ hoặc TTL quá dài.

### 3.2. Cache miss

Ứng dụng không tìm thấy entry usable. Nguyên nhân có thể là:

- Key chưa từng được cache.
- Eviction.
- Expiry.
- Invalidation.
- Key đổi vì schema/version/tenant.
- Cache node failover, restart hoặc flush.
- Routing sai, data migration, bộ nhớ đang cold.

Không thể dùng một counter `miss` để biết **record gốc tồn tại hay không**.

### 3.3. Cache fill/admission

Sau miss, ứng dụng lấy dữ liệu từ nguồn và cân nhắc đưa vào cache. **Không phải mọi dữ liệu đọc được đều nên cache**: scan kết quả một lần có thể đẩy các hot entries ra khỏi bộ nhớ.

### 3.4. Entry vừa được fill vẫn có thể bị eviction sớm

Nếu dataset nóng lớn hơn capacity hoặc một item quá nặng, cache liên tục churn. Một TTL dài không bảo vệ nó.

## 4. Vì sao cần giới hạn bộ nhớ?

RAM cache cạnh tranh với nhiều thành phần:

- Giá trị và keys thực sự được lưu.
- Object headers, hash tables, metadata về TTL/LRU/LFU.
- JVM heap, native/off-heap buffers, thread stacks và GC overhead.
- Connection buffers, network output buffers, replication/persistence buffers.
- Allocator fragmentation, internal bookkeeping, temporary objects.
- OS và quá trình khác trên cùng host/pod.

Không đặt giới hạn có thể gây **out-of-memory**, process bị kill, swap/paging mạnh, latency spike và availability failure.

### 4.1. Giới hạn entries khác giới hạn bytes

`maximumSize(100_000)` giới hạn số entries theo policy, không bảo đảm tổng kích thước nhỏ nếu mỗi value có thể từ 1 KiB đến 10 MiB.

`maximumWeight(...)` với weigher phù hợp có thể phản ánh kích thước tương đối, nhưng vẫn không nhất thiết trùng tổng heap RSS hoặc native memory.

### 4.2. Memory hard limit khác eviction threshold

Một container có giới hạn RAM 4 GiB, nhưng Redis/Java cache chỉ nên dùng **một phần**. Cần chừa headroom cho peak memory, hoạt động nền, buffers, fragmentation và tiến trình khác.

### 4.3. Cache fill nhanh có thể làm hệ mất ổn định

Nếu 10.000 requests đồng thời miss và cùng tải mỗi value 2 MiB, memory allocations có thể tăng đột biến trước khi eviction kịp cân bằng. Cần admission, concurrency caps, bounded result sizes và request coalescing.

### 4.4. RSS khác logical cache size

Sau khi xóa keys, allocator có thể chưa trả toàn bộ pages về OS; `used_memory` và RSS không giảm theo cùng tỷ lệ. Không suy rằng eviction “không hoạt động” chỉ từ một biểu đồ RSS.

## 5. Eviction khác expiration, invalidation và source deletion ra sao?

Xét vòng đời:

~~~text
T0: Product SKU-A tồn tại ở NoSQL source.
T1: Product được cache trong Redis, TTL=1 giờ.
T2: Redis thiếu RAM, eviction SKU-A sau 5 phút.
T3: GET SKU-A thấy cache MISS, đọc lại source.
T4: Product được fill vào Redis lần nữa.
T5: Admin xóa Product ở source theo nghiệp vụ.
T6: Event invalidation loại SKU-A khỏi Redis.
T7: GET SKU-A đọc source, trả NOT_FOUND.
~~~

T2 và T5 đều có thể dẫn đến cùng kết quả `GET redis-key -> nil`, nhưng chỉ **T5** làm thay đổi trạng thái nghiệp vụ gốc.

### 5.1. Eviction không phải delete event nghiệp vụ

Nếu một Redis cache key bị loại vì LRU, **không** tự phát `ProductDeleted` cho các consumers. Nếu consumer cần sự kiện xóa sản phẩm, nó phải nghe source CDC/outbox hoặc domain event có thẩm quyền.

### 5.2. Expired cache không nghĩa source expired

Một token/session có TTL cả trong cache lẫn source phải có contract rõ. Cache expiration có thể chỉ là “phải tra nguồn”; source expiry có thể là kết thúc hiệu lực thật. Hai mốc không được gộp vì trùng tên field.

### 5.3. Invalidation không phải xóa bản ghi

Sau khi Product đổi giá, ứng dụng invalidates `product:SKU-A` để request sau tải giá mới. Không ai yêu cầu xóa Product khỏi database.

### 5.4. Source deletion không tự xóa mọi cache

Xóa ở database nhưng invalidation event thất lạc có thể khiến cache còn hàng cũ. Muốn deletion thật sự có hiệu lực với người dùng, phải thiết kế propagation và freshness guarantee, không chỉ gọi `DELETE source`.

## 6. Các nhóm chính sách eviction

| Chính sách | Tiêu chí chọn entry | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|---|
| **LRU** (Least Recently Used) | Ít được dùng gần đây | Hữu ích khi dữ liệu có locality theo thời gian | Scan một lượt có thể đẩy hot keys; metadata/cost |
| **LFU** (Least Frequently Used) | Tần suất truy cập thấp | Giữ những keys phổ biến lâu dài | Dữ liệu nổi tiếng quá khứ có thể bám lâu nếu không decay |
| **FIFO** | Vào cache trước bị loại trước | Dễ giải thích/triển khai | Không quan tâm hotness thực tế |
| **Random** | Lựa chọn ngẫu nhiên | Overhead đơn giản | Hit rate có thể kém khi skew lớn |
| **TTL-priority** | Ưu tiên keys gần hết hạn | Tận dụng expiration metadata | TTL ngắn chưa chắc ít quan trọng |
| **Cost-/weight-aware** | Cân nhắc kích thước, chi phí tái tạo, benefit | Có thể tối ưu RAM theo workload | Cần ước lượng/điều chỉnh chính xác |
| **Admission + eviction** | Quyết định cái gì đáng đưa vào, rồi chọn victim | Chống scan pollution tốt hơn | Phức tạp hơn LRU đơn giản |

### 6.1. Eviction policy thường là heuristic

Không có thuật toán duy nhất luôn tối ưu cho mọi workload. Access pattern thay đổi theo giờ, tenant, query shape và đợt backfill.

### 6.2. LRU vs LFU: ví dụ

~~~text
Key A được đọc 1000 lần mỗi ngày, nhưng không đọc 10 phút gần đây.
Key B vừa được đọc một lần.
~~~

LRU có thể ưu tiên B vì mới dùng. LFU có thể ưu tiên A vì tần suất cao. Với sản phẩm bán chạy ổn định, LFU có thể hợp lý; với dữ liệu trending biến đổi nhanh, cần decay/admission strategy.

### 6.3. FIFO dễ bị scan pollution

Một job quét 1 triệu keys một lần có thể làm các keys đang hot nhưng đã vào cache trước bị loại; sau job, ứng dụng lại phải warm-up. TTL và capacity không chữa tận gốc vấn đề thiếu admission control.

### 6.4. Tính “tốt” đo bằng miss cost, không chỉ hit ratio

Cache giữ 100 keys nhỏ và dễ tải có thể có hit ratio cao, trong khi bỏ một query cực đắt gây tăng latency/DB load lớn. Đo byte hit rate, origin requests và **miss penalty** cùng với hit ratio.

## 7. Redis `maxmemory` và chính sách eviction

Redis có khả năng thiết lập ngân sách bộ nhớ qua `maxmemory` và chọn `maxmemory-policy`. Ví dụ cấu hình minh họa:

~~~conf
maxmemory 2gb
maxmemory-policy allkeys-lfu
~~~

Hoặc trong quá trình vận hành trên instance được phép:

~~~redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
INFO stats
~~~

> Cấu hình, tên metrics, đặc điểm thuật toán và khả năng sửa config khi đang chạy cần kiểm theo **Redis version, Redis-compatible implementation, managed service và topology cụ thể**. Không coi ví dụ cấu hình là mặc định của mọi dịch vụ Redis.

### 7.1. Nhóm `allkeys-*`

Các chính sách thuộc nhóm `allkeys-*` có thể chọn keys trong phạm vi bộ nhớ Redis theo thuật toán, **kể cả keys không có TTL**, tùy implementation. Phù hợp khi Redis chuyên dùng làm cache, mọi entry có thể mất an toàn.

### 7.2. Nhóm `volatile-*`

Nhóm `volatile-*` thường chỉ xét keys có TTL/expire được thiết lập. Một key không có TTL có thể không đủ điều kiện eviction theo policy. Đây không phải cách bảo đảm độ bền tuyệt đối cho dữ liệu không TTL: nếu chỉ có keys không eligible khi vượt memory limit, writes cần cấp phát thêm bộ nhớ có thể bị từ chối.

### 7.3. `noeviction`

`noeviction` không chủ động loại keys để giải phóng memory khi vượt giới hạn; những lệnh cần bộ nhớ có thể trả lỗi theo Redis/API/version. Nó **không biến Redis thành hệ lưu trữ không mất dữ liệu**: process crash, failover, persistence configuration, OOM bên ngoài và lỗi vận hành vẫn phải được xem xét.

### 7.4. Memory limit là ranh giới điều tiết, không luôn là tổng RAM vật lý

Redis có những vùng bộ nhớ/buffers được kế toán khác nhau khi xét eviction. RSS có thể lớn hơn mức `maxmemory` do fragmentation và overhead. Phải chừa headroom cho container/host và đo metrics thực tế.

## 8. Bảng chính sách Redis thường gặp

| `maxmemory-policy` | Nhóm keys eligible | Tiêu chí |
|---|---|---|
| `noeviction` | Không loại keys để lấy chỗ | Từ chối/không hoàn tất một số lệnh tăng memory theo giới hạn |
| `allkeys-lru` | Mọi keys | Ưu tiên loại keys ít dùng gần đây |
| `allkeys-lfu` | Mọi keys | Ưu tiên loại keys được truy cập ít theo bộ đếm/tính toán tần suất |
| `allkeys-random` | Mọi keys | Chọn ngẫu nhiên |
| `volatile-lru` | Keys có TTL | LRU trong tập đủ điều kiện |
| `volatile-lfu` | Keys có TTL | LFU trong tập đủ điều kiện |
| `volatile-random` | Keys có TTL | Random trong tập đủ điều kiện |
| `volatile-ttl` | Keys có TTL | Ưu tiên keys sắp hết hạn |

### 8.1. LRU/LFU trong Redis có thể là xấp xỉ

Không suy Redis duy trì danh sách LRU hoàn hảo toàn bộ keys. Nhiều phiên bản Redis dùng sampling/metadata xấp xỉ để kiểm soát overhead; behavior và knobs cần kiểm theo version.

### 8.2. LFU có decay/điều chỉnh

Một key từng hot nhiều tháng trước không nên được giữ mãi khi không ai truy cập. Redis LFU có cơ chế counters/decay theo implementation; cần quan sát workload thay vì lấy số truy cập tuyệt đối làm chân lý.

### 8.3. `volatile-ttl` không có nghĩa key bị xóa chỉ khi TTL=0

Khi memory pressure, key có TTL **còn dương** vẫn có thể bị eviction nếu nó được ưu tiên làm victim. TTL còn 15 phút không bảo đảm cache residency 15 phút.

### 8.4. Mọi `volatile-*` đều cần eligible keys

Nếu chỉ có keys không TTL hoặc số keys có TTL quá ít so với pressure, eviction không giải phóng đủ memory. Ứng dụng có thể gặp OOM-related command failures dù nhìn tổng số keys vẫn còn nhiều.

### 8.5. Tại sao không đơn giản chọn `allkeys-lru` mọi nơi?

Nếu Redis chứa cả cache có thể tái tạo và state quan trọng không thể tái tạo, `allkeys-lru` có thể xóa loại thứ hai. **Trộn data classes với durability requirements khác nhau trong một eviction domain** là rủi ro kiến trúc. Tách instances/roles hoặc đổi storage authority phù hợp.

## 9. Eviction không được dùng như một cơ chế xóa dữ liệu gốc

Giả sử backend Product sử dụng MongoDB hoặc DynamoDB làm source và Redis làm cache:

~~~text
DELETE cache key
    -> delete local cached copy
    -> no database mutation

DELETE product in source
    -> business state changes
    -> outbox/CDC invalidation propagates to caches
~~~

### 9.1. Không phát event xóa nghiệp vụ từ Redis key eviction

Một key bị Redis loại khi nóng RAM không chứng minh product bị xóa. Dùng eviction notification để xử lý **business deletion** là sai authority boundary.

### 9.2. Keyspace notifications không phải durable business log

Redis có các cơ chế thông báo một số keyspace/keyevent events tùy cấu hình và phiên bản, nhưng không nên xem những notifications ấy là một change-data-capture log bền vững hay exactly-once. Nếu cần event xóa nghiệp vụ, phát từ source/outbox.

### 9.3. Full cache flush không phải data reset

`FLUSHDB`/`FLUSHALL` trên cache có thể gây miss storm, nhưng không được làm source records biến mất. Không bao giờ dùng lệnh này trên môi trường có Redis là source of truth mà không hiểu hậu quả và quyền phê duyệt.

### 9.4. Redis có thể là nguồn gốc

Nếu API cho phép tạo một session state chỉ trong Redis và không có store khác, eviction của session key là **mất state thật**, dù không có document MongoDB để xóa. Nhãn “cache” trong tên biến không bảo vệ dữ liệu.

## 10. Cache TTL và database TTL là hai cơ chế khác nhau

Ví dụ:

~~~text
Redis Product cache TTL = 5 minutes.
NoSQL Product source retention = indefinite until business delete.
~~~

Sau năm phút, Product vẫn tồn tại ở source. Ngược lại:

~~~text
NoSQL Session source expiresAt = 2026-11-15T00:00:00Z.
Redis cache TTL = 30 minutes.
~~~

Nếu source hết hạn session nhưng Redis cache vẫn trả cached authorization, hệ có thể chấp nhận session đã hết hiệu lực.

### 10.1. Source TTL có thể thực sự xóa dữ liệu

Trong một số NoSQL, TTL tại source có thể làm record không còn tồn tại hoặc được cleanup theo background schedule. Cần hiểu semantics cụ thể: query visibility, purge timing, tombstones, backup, replication và CDC.

### 10.2. Đừng dùng TTL cleanup làm duy nhất security gate

Với session hoặc token, **đường xác thực phải kiểm tra `expiresAt`/revocation policy**, ngay cả khi physical TTL daemon chưa xóa item. Cache TTL có thể ngắn nhưng cũng không tự bảo đảm revoke tức thì.

### 10.3. Expiration và eviction có metric khác

Một cache có `expired_keys` tăng vì TTL ngắn; `evicted_keys` tăng vì capacity pressure. Nếu gộp chung, dễ chẩn đoán sai rằng cần tăng RAM trong khi thực tế TTL đang quá ngắn.

### 10.4. Expiry tombstone và dữ liệu cũ

Khi nguồn có TTL/tombstone, replica cũ hoặc offline client có thể giữ bản ghi trước khi xóa. Sync/repair phải hiểu delete markers, không đưa dữ liệu hết hạn trở lại chỉ vì cache miss gây refill từ replica lag.

## 11. Cache invalidation khi dữ liệu nguồn thay đổi

Eviction là lựa chọn tự động do memory policy. **Invalidation** là hành động xác định một cached value không còn phù hợp với state mới:

~~~text
Source Product v7: price=100
Cache Product v7: price=100

Update source to v8: price=120
Invalidate cache Product v7
Next read fills Product v8
~~~

### 11.1. Invalidate-after-commit

Một pattern:

~~~text
1. Update authoritative DB successfully.
2. Invalidate affected cache key(s).
3. Future reads reload.
~~~

Nếu invalidation thất bại, cache có thể stale. Có thể dùng transactional outbox/CDC và idempotent cache consumers để tăng độ tin cậy, nhưng vẫn cần hiểu độ trễ.

### 11.2. Invalidate-before-write có cửa sổ nguy hiểm

Nếu xóa cache trước khi source commit, một read song song có thể refill giá trị cũ rồi nằm cache sau commit. Thứ tự invalidation và version control cần được thiết kế chủ động.

### 11.3. Cache-aside không có strong read guarantee mặc định

Ngay cả sau invalidation, một slow read có thể fill lại state cũ (xem phần race sau). Với nghiệp vụ cần **read-your-writes hoặc linearizable decision**, bypass cache hoặc có version-aware protocol.

### 11.4. Delete nguồn cần chặn stale refill

Source Product đã delete, nhưng client cũ đọc replica lag có thể thấy Product cũ rồi fill cache. Cần authoritative read/causal consistency/tombstone/version checks khi yêu cầu xóa phải có hiệu lực ngay.

## 12. Cache-aside: eviction thường là một cache miss có thể phục hồi

**Cache-aside/lazy loading**:

~~~mermaid
flowchart TD
    Q["Read Product"] --> C{"Cache hit?"}
    C -->|"Yes, usable"| HIT["Return cached view"]
    C -->|"No"| DB["Read authoritative NoSQL"]
    DB --> E{"Exists and cacheable?"}
    E -->|"Yes"| PUT["Fill cache with bounded TTL"]
    PUT --> RETURN["Return source value"]
    E -->|"No"| MISS["Return not-found / bounded negative cache"]
~~~

### 12.1. Dữ liệu nguồn phải độc lập

Eviction không làm thay đổi database. Nếu cache miss, source read phải là thao tác được phép và đủ tính đúng đắn.

### 12.2. Cache miss đắt

Một key rất nóng bị eviction có thể tạo 50.000 source reads trong vài giây. Phải có request coalescing/single-flight, giới hạn concurrency và admission policy.

### 12.3. Không lưu mọi response

Không cache errors tùy tiện, kết quả có PII trong key namespace công khai, hoặc response phụ thuộc quyền user mà thiếu identity/authorization scope.

### 12.4. Đừng cache `Optional.empty` không có TTL chính sách

Nếu source trả not-found và cache giữ negative result quá lâu, entity được tạo sau đó có thể tiếp tục “không tồn tại” với người dùng. Negative caching là một policy riêng.

### 12.5. Nguồn không có thì không invent data

Nếu cache miss và source unavailable, có thể trả `503`, stale fallback trong policy, hoặc pending, nhưng không giả tạo Product mới từ thông tin cũ chưa được xác minh.

## 13. Write-through: cập nhật nguồn và cache theo hợp đồng

Trong **write-through**, ứng dụng viết qua một lớp điều phối:

~~~text
Application write
    -> authoritative DB commit
    -> cache write or invalidate
    -> application response
~~~

Một biến thể đặt cache layer làm coordinator, nhưng guarantee phụ thuộc chính xác nơi commit/ACK.

### 13.1. Hai writes độc lập không tạo transaction

DB commit thành công, cache write fail: nguồn đúng nhưng cache stale hoặc thiếu. Cache write trước, DB commit fail: cache có trạng thái chưa hợp lệ. Phải định nghĩa **order, retry và failure result**.

### 13.2. Không báo business success chỉ dựa vào cache SET

Nếu nghiệp vụ đòi dữ liệu bền, ACK của Redis cache không thay cho ACK của DB nguồn. Chỉ trả `COMMITTED` khi source đạt commit contract.

### 13.3. Invalidate thường đơn giản hơn update cache

Sau write nguồn, invalidate để lần đọc sau fetch mới có thể tránh cần map nhiều projections. Nhưng invalidation cũng có race/delivery failure, cần SLO độ mới.

### 13.4. Retry cache update nên idempotent

Ghi một cache value có version ổn định và TTL có thể retry; gửi counter increment không có commandId có thể double-apply. Phân biệt tác dụng phụ và outcome.

## 14. Write-behind/write-back: eviction có thể nguy hiểm

**Write-behind** lưu update vào cache/queue trước rồi ghi nguồn **bất đồng bộ**.

~~~text
Application UPDATE
    -> Cache accepts dirty value
    -> App responds
    -> Background flusher writes NoSQL source later
~~~

Nếu dirty entry bị eviction, process crash hoặc queue mất trước khi source commit, **dữ liệu gốc không có update ấy**.

### 14.1. Dirty vs clean cache entry

| Trạng thái | Ý nghĩa | Có thể eviction tự do? |
|---|---|---|
| Clean | Bản sao phản ánh nguồn theo một version đã biết | Có thể nếu source rebuild được |
| Dirty/unflushed | Chứa cập nhật chưa durable ở source | **Không**, nếu chưa có durable log/queue thay thế |
| Pending ambiguous | Không biết source đã commit chưa | Cần reconciliation |
| Stale | Source đã đổi, cached value cũ | Nên invalidate/refresh theo policy |

### 14.2. Write-behind an toàn cần buffer bền hoặc protocol

Nếu workload đòi durability, cần durable write-ahead log/queue, idempotent command IDs, ordering, replay, backpressure và kiểm thử crash. Một Redis key có TTL không thể tự đóng vai transaction log bền.

### 14.3. ACK của write-behind không đồng nghĩa source committed

API nên phân biệt `ACCEPTED/PENDING` với `COMMITTED` nếu chỉ durable queue đã nhận mà source chưa ghi. Không dùng tên method `save()` để đánh tráo kết quả.

### 14.4. Eviction chỉ hợp lệ khi dirty data đã được bảo vệ

Một write-back cache có thể flush-before-evict hoặc dùng durable journal; khi tài nguyên cạn, nó có thể **block/throttle writes** thay vì loại dirty entry. Thiết kế tùy engine nhưng bất biến cần được ghi rõ.

## 15. Nhiều tầng cache và sự khác biệt về eviction domain

Một ứng dụng Java có thể có:

~~~text
L1: Caffeine trong từng JVM pod (tối đa ~100 MiB/pod)
L2: Redis phân tán (ví dụ ngân sách tổng nhiều GiB)
L3: CDN/edge cache cho public assets
Origin: NoSQL source
~~~

### 15.1. Eviction tại L1 không xóa L2

Một pod JVM loại key khỏi Caffeine, request sau có thể hit Redis. Không có nghĩa source phải được đọc lại ngay.

### 15.2. Eviction tại L2 không xóa L1

Redis mất key, nhưng một pod vẫn còn stale local copy. Nếu event invalidation chỉ tác động Redis mà không tới L1, pods có thể trả dữ liệu không nhất quán.

### 15.3. Bộ nhớ cache nhân theo replicas

100 MiB per pod × 20 pods là tới khoảng 2 GiB entries/overhead cấp cluster, chưa kể duplicates. Local caches không tự chia sẻ một ngân sách tổng.

### 15.4. Near-cache consistency

Near-cache đôi khi có event-based invalidation. Nếu network partition hoặc subscriber disconnect, nó có thể tiếp tục giữ stale entries. Cần disconnect policy, versioned invalidations, epoch/reset và TTL fallback.

### 15.5. Caches và source có SLA khác nhau

Cache mất một node có thể phục hồi từ source; source mất quorum là failure cần xử lý chặt hơn. Không dùng thiết kế “source phải luôn được đọc qua cache” để che một outage của source.

## 16. Memory accounting: những con số phải đo

Giả sử:

~~~text
Logical entries:
    key bytes + value bytes

Additional:
    object/hashtable metadata
    expiration metadata
    LRU/LFU bookkeeping
    allocator fragmentation
    per-client/replication/persistence buffers
    framework/JVM overhead
~~~

Một bộ cache có 1 triệu JSON strings mỗi string 600 bytes **không tự chỉ dùng 600 MB RAM**; cần keys và overhead.

### 16.1. Dự toán đơn giản

\[
M_{\text{logical}} \approx \sum_{k=1}^{N}
(S_{\text{key},k}+S_{\text{value},k}+S_{\text{metadata},k}).
\]

Với 1.000.000 entries, giả định mỗi entry trung bình:

~~~text
Key       = 60 bytes
Value     = 600 bytes
Metadata  = 140 bytes (giả định đo mẫu)
---------------------------------
Total     = 800 bytes

1,000,000 x 800 = 800,000,000 bytes ≈ 800 MB decimal.
~~~

Đây là **bài toán minh họa**, không phải định mức Redis. Overhead thực phụ thuộc data structure, allocator, encoding, key distribution, version và workload.

### 16.2. Replication overhead

Nếu cùng tập keys tồn tại ở hai replicas, memory được tiêu thụ trên hai nodes. Nếu sharded, mỗi shard chứa một phần và replica copies riêng; không nhân một hệ số tùy ý khi không biết topology.

### 16.3. Fragmentation và RSS

`used_memory_rss` có thể cao hơn logical memory do allocator và OS. Cũng có các hoạt động temporary allocations, snapshot/fork/copy-on-write cần headroom. Không cấu hình cache tới 100% physical/container RAM.

### 16.4. Java heap/off-heap

Caffeine giữ objects trên Java heap theo thông lệ, nhưng framework, compression, buffers, Netty/native allocations có thể bổ sung off-heap footprint. `maximumSize` không giới hạn total process memory. Cần đo heap histogram/GC/RSS và memory per entry.

### 16.5. P95/P99 entry size quan trọng

Nếu 99% entries 1 KiB nhưng 1% entries 5 MiB, average thấp che rủi ro memory spikes. Cân nhắc cap value size và không cache quá lớn.

## 17. Giới hạn theo bytes và theo số entries

### 17.1. `maximumSize`

Một cache local giới hạn 50.000 entries có thể ổn nếu values gần như bằng kích thước; nhưng nếu sizes phân tán lớn, count không biểu diễn memory pressure.

### 17.2. `maximumWeight`

Một thư viện như Caffeine có thể dùng weigher để ước lượng weight của entries. Ví dụ một entry 1 KiB có weight 1, entry 1 MiB có weight 1024. Cần định nghĩa unit và cap phù hợp.

### 17.3. Estimated weight không phải real-time heap accounting

Weigher có thể được tính khi entry được ghi/cập nhật; nếu value là mutable collection phình to sau đó mà cache không biết, trọng lượng có thể bị đánh giá sai. Dùng immutable values hoặc cập nhật entry để giữ weight đúng.

### 17.4. Đừng cho một item chiếm cả cache

Một report 100 MiB trong cache tổng 128 MiB có thể gây eviction gần toàn bộ hot keys. Admission policy hoặc max cacheable entry size giúp tránh workload một lần làm ô nhiễm cache.

### 17.5. Admission và eviction là hai quyết định

**Admission:** có nên cache item mới không? **Eviction:** nếu cần chỗ, loại item nào? TinyLFU/Window TinyLFU và các mô hình admission khác tìm cách bảo vệ working set khỏi scan pollution, nhưng cần kiểm workload thực.

## 18. LRU, LFU và TinyLFU dưới góc nhìn workload

### 18.1. LRU phù hợp khi recent-use dự báo near future

Một user vừa mở detail một sản phẩm có thể mở lại ngay; LRU ghi nhớ locality. Nhưng một batch scan tuần tự sẽ làm entries một lần xuất hiện mới hơn hot keys cũ.

### 18.2. LFU phù hợp khi long-term popularity rõ

Catalog có một nhóm SKU bán chạy liên tục. LFU có thể giữ chúng dù nhiều request hiếm lẻ ghé qua. Cần decay để không bị lịch sử cũ khóa bộ nhớ.

### 18.3. TinyLFU thiên về ước lượng frequency để admission

Ý tưởng: ước lượng access frequency của candidate so với victim để quyết định candidate có đáng chiếm capacity. Cấu trúc cụ thể tùy implementation; **không đồng nhất TinyLFU với một LRU list đơn giản**.

### 18.4. TTL là freshness policy, không phải popularity policy

Một config item luôn hot nhưng TTL=10 giây sẽ liên tục expire/refill; tăng memory không giải quyết số lần read origin do TTL. Ngược lại, TTL dài không làm key ít dùng tránh eviction.

### 18.5. Chọn chính sách bằng replay/simulation

Nếu có traces của access patterns, replay các chính sách/capacity khác nhau để ước lượng hit ratio, byte hit ratio, miss cost và tail latency. Số “LFU luôn tốt hơn LRU” không phải định luật.

## 19. Cache thrashing và working set

**Working set** là tập dữ liệu được truy cập đủ thường xuyên trong một khoảng thời gian có ý nghĩa. Nếu working set lớn hơn memory budget, cache có thể liên tục nạp/loại cùng entries.

Ví dụ:

~~~text
Hot working set: 5 GiB.
Usable cache capacity: 2 GiB.

Requests shift across many hot keys.
=> repeated misses, origin reads, eviction spikes.
~~~

### 19.1. Dấu hiệu thrashing

- `evicted_keys` tăng rất nhanh.
- Miss rate cao, origin QPS tăng cùng lúc.
- p95/p99 latency tăng dù cache memory luôn đầy.
- Network và CPU của database source tăng.
- Warming/recovery kéo dài sau failover.

### 19.2. Tăng RAM không phải lúc nào cũng đủ

Nếu cache một lần đọc 100 triệu keys không bao giờ dùng lại, tăng capacity có thể chỉ làm lần scan lớn hơn. Cần admission/bypass cache cho batch jobs hoặc tách cache pools theo workload.

### 19.3. Tách workload nóng và lạnh

Một analytics exporter có thể làm LRU của API online mất hiệu quả. Dùng cache namespace/pool hoặc memory budget riêng và policies khác nhau cho online reads vs analytics.

### 19.4. Định nghĩa cacheability theo query

Query có key/filter/sort không ổn định và result quá lớn có thể không đáng cache. Cache nên phục vụ patterns có locality/hit potential rõ, không trở thành kho tạm mọi response.

## 20. Cache stampede sau eviction hoặc expiry

Một sản phẩm rất hot bị eviction lúc T0. 5.000 requests tới trong giây tiếp theo:

~~~text
All requests see MISS.
All requests query NoSQL source.
Origin overloads.
Timeouts trigger retries.
More requests pile up.
~~~

Eviction của một key nhỏ có thể trở thành **sự cố phụ thuộc nguồn** nếu không có bảo vệ.

### 20.1. Single-flight/request coalescing

Trong cùng process, chỉ một caller tải mỗi key từ source; các callers còn lại chờ kết quả (có timeout/budget). Với nhiều pods, coalescing local không giảm toàn bộ concurrent fills; có thể cần distributed lock/lease có giới hạn hoặc staggered TTL.

### 20.2. Jitter TTL

Nếu hàng triệu keys được ghi đồng thời TTL=300s, chúng có thể expire cùng lúc. Chọn TTL có jitter trong ngưỡng freshness cho phép để rải misses.

### 20.3. Stale-while-revalidate

Với dữ liệu cho phép stale, có thể trả cached value trong cửa sổ stale và refresh background. Không dùng cho permission, balance hoặc trạng thái nghiệp vụ đòi authoritative read trừ khi contract cho phép.

### 20.4. Rate limit origin loads

Giới hạn số concurrent cache misses đi xuống database để tránh làm hỏng nguồn. Khi vượt budget, fallback/stale/503 theo chính sách; không tạo một hàng đợi vô hạn trong JVM.

### 20.5. Prewarm có chọn lọc

Preload hot keys sau deploy/failover có thể giảm cold-start nhưng cũng có thể tạo thundering herd và đẩy keys khác ra ngoài. Prewarm theo top-K, có concurrency/cost budget.

## 21. Negative caching và xóa nguồn

Negative cache lưu kết quả **không tìm thấy**, ví dụ:

~~~text
product:T1:SKU-NEW -> NOT_FOUND, TTL 10 seconds
~~~

Nó giảm tải cho các request dò những ID không tồn tại.

### 21.1. Vì sao cần TTL ngắn/khác positive cache?

Một Product mới được tạo sau khi negative result được cache. Nếu NOT_FOUND được lưu 1 giờ, user không nhìn thấy sản phẩm mới dù source đã commit. TTL ngắn và invalidation on-create giảm rủi ro.

### 21.2. Negative cache cần authorization scope

`NOT_FOUND` có thể được trả để che existence của resource thuộc tenant khác. Không reuse một negative cached result giữa principals/tenants nếu security/visibility policy khác nhau.

### 21.3. Không cache network error như NOT_FOUND

Nếu NoSQL timeout, application không biết Product có tồn tại không. Caching `NOT_FOUND` khi source `UNAVAILABLE` làm lỗi hạ tầng trở thành thông tin sai kéo dài.

### 21.4. Deleted vs temporarily absent

Khi xóa source, negative cache có thể thích hợp, nhưng sau restore/recreate cùng ID cần generation/version để phân biệt entity cũ/mới. Một 404 từ eventual index không chứng minh source đã xóa.

## 22. Race condition: stale data được fill sau invalidation

Một lỗi phổ biến của cache-aside:

~~~text
T1: Reader R thấy cache miss.
T2: R đọc database Product version 7.
T3: Writer W cập nhật Product lên version 8.
T4: W invalidate cache key.
T5: R (đang chậm) SET cache = version 7.
T6: Các readers tiếp theo hit version 7.
~~~

Đây là **stale repopulation race**. Chỉ nói “DB write xong thì cache delete” **chưa bảo đảm** mọi reads sau đó đều thấy v8.

### 22.1. TTL giới hạn thời gian stale, không ngăn race

Nếu cache v7 có TTL 30 giây, nó có thể sống thêm tối đa gần cửa sổ đó theo policy. Điều này có thể chấp nhận với catalog, nhưng không với số dư hay quyền truy cập cần tức thời.

### 22.2. Version-aware fill

Kèm mỗi cached value một revision/source version. Chỉ cho phép fill nếu không ghi đè một version cao hơn/marker mới hơn theo giao thức. Tuy nhiên, nếu cache có thể eviction cả **version marker**, đảm bảo monotonicity chỉ dựa vào cache có thể sụp.

### 22.3. Key có version/generation

Một mô hình:

~~~text
product:T1:SKU-A:v8 -> cached value v8
~~~

Khi source version tăng, read route phải biết current authoritative version hoặc một generation token đáng tin để chọn key; nếu chỉ đọc “latest pointer” cũng được cache eventual, stale-pointer vẫn có thể xảy ra. Versioned key không tự giải quyết mọi strong consistency requirement.

### 22.4. Strong decisions nên bypass cache nếu cần

Để xác nhận tồn kho, update payment hoặc authorization, source/transaction authority nên enforce invariant. Cache có thể cung cấp hint/UI nhưng không là bằng chứng cuối.

### 22.5. Invalidation event ordering

CDC events `v7`, `v8` có thể tới consumer không đúng thứ tự ở một số pipelines. Nếu consumer áp v7 sau v8, có thể downgrade cache. Giữ sequence/revision, idempotent handlers và scope của ordering theo source protocol.

## 23. Mẫu dữ liệu cached có version và thời điểm

Một envelope:

~~~json
{
  "entity": {
    "tenantId": "T1",
    "sku": "SKU-A",
    "name": "Notebook",
    "displayPriceMinor": 125000
  },
  "sourceVersion": 42,
  "cachedAt": "2026-11-14T10:00:00Z",
  "expiresAt": "2026-11-14T10:05:00Z",
  "schemaVersion": 3
}
~~~

### 23.1. Source version khác cache TTL

Version giúp nhận diện state/ordering; TTL định nghĩa giới hạn freshness/residency. Một version 42 có thể bị eviction trước thời điểm hết hạn; một value 41 có thể chưa hết TTL nhưng đã stale.

### 23.2. `cachedAt` không chứng minh source version mới nhất

Một follower lag có thể trả version 41 lúc 10:01 dù leader đã commit 42 lúc 10:00. `cachedAt=10:01` không làm payload 41 thành mới hơn.

### 23.3. SchemaVersion không thay entityVersion

`schemaVersion=3` có nghĩa encoding của cache entry; `sourceVersion=42` có nghĩa revision state. Chúng phục vụ hai mục đích khác nhau.

### 23.4. Payload cần được validate

Không dùng cached JSON có field user-controlled để bypass validation/authorization. Cached data có thể bị corrupt, cũ schema hoặc không còn phù hợp với permissions.

### 23.5. Cache encoding khi triển khai nhiều phiên bản Java

Trong rolling deployment, pods cũ có thể không đọc được cached value do pod mới ghi. Dùng schema version/compatible serializer hoặc namespace versioned cache keys, tránh cache corruption/retry storms.

## 24. Java với Caffeine: cache local giới hạn entries và TTL

Một ví dụ Java với thư viện Caffeine (cần dependency và version tương thích):

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import java.time.Duration;
import java.util.Optional;

public record ProductView(
    String tenantId,
    String sku,
    String name,
    long priceMinor,
    long sourceVersion
) {}

public interface ProductSource {
    Optional<ProductView> findAuthoritative(
        String tenantId, String sku
    );
}

public final class ProductLocalCache {
    private final ProductSource source;

    private final Cache<String, Optional<ProductView>> cache =
        Caffeine.newBuilder()
            .maximumSize(50_000)
            .expireAfterWrite(Duration.ofMinutes(3))
            .recordStats()
            .build();

    public ProductLocalCache(ProductSource source) {
        this.source = source;
    }

    public Optional<ProductView> get(String tenantId, String sku) {
        String key = tenantId + "|" + sku;
        return cache.get(
            key,
            ignored -> source.findAuthoritative(tenantId, sku)
        );
    }

    public void invalidate(String tenantId, String sku) {
        cache.invalidate(tenantId + "|" + sku);
    }

    public String metrics() {
        return cache.stats().toString();
    }
}
~~~

### 24.1. Điều ví dụ bảo đảm

Caffeine có thể giữ một tập entries bounded theo `maximumSize`; entry có `expireAfterWrite` và có thể bị eviction do capacity. Sau eviction, `get` gọi lại `source.findAuthoritative`.

### 24.2. Điều ví dụ chưa bảo đảm

- Không xác thực/ủy quyền tenant từ context tin cậy.
- Không ngăn hoàn toàn race stale refill/invalidation.
- Negative result `Optional.empty()` được cache cùng TTL 3 phút, có thể quá dài.
- Không có per-key deadline, circuit breaker, backpressure.
- `maximumSize` không giới hạn bytes thực.
- Không có invalidation broadcast giữa các JVM pods.

### 24.3. Không dùng mutable shared objects

Nếu cached object là mutable và caller sửa trực tiếp, nhiều requests thấy trạng thái lẫn nhau. `record` với các fields bất biến là hướng tốt; với nested lists/maps vẫn phải tạo immutable copies hoặc deep-copy khi cần.

### 24.4. Không suy từ `Optional.empty()` rằng source không tồn tại mãi

Trong ví dụ, negative cache cần TTL/invalidations phù hợp. Một thiết kế thực tế có thể dùng cache riêng với TTL ngắn cho misses, hoặc không cache misses khi entity mới được tạo thường xuyên.

## 25. Java Caffeine: giới hạn theo weight

Một ứng dụng cache kết quả báo cáo có sizes khác nhau. Dùng `maximumWeight` và `weigher` để ước lượng chi phí entry:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;

public record CachedBytes(byte[] data) {
    public CachedBytes {
        data = data.clone();
    }
    @Override public byte[] data() {
        return data.clone();
    }
    public int estimatedSize() { return data.length; }
}

Cache<String, CachedBytes> byteCache = Caffeine.newBuilder()
    .maximumWeight(64L * 1024 * 1024)
    .weigher((String key, CachedBytes value) -> {
        // Weight units approximated as bytes; clamp to valid int.
        long estimated = 64L + 2L * key.length()
            + value.estimatedSize();
        return (int) Math.min(Integer.MAX_VALUE, estimated);
    })
    .expireAfterAccess(Duration.ofMinutes(10))
    .recordStats()
    .build();
~~~

### 25.1. Weight chỉ là ước lượng

64 bytes overhead và 2 bytes/char ở đây là công thức minh họa; không phản ánh chính xác mọi JVM encoding/object layout. Test thực tế cần heap/RSS sampling.

### 25.2. Đừng để value mutable ngoài cache

`CachedBytes` clone array khi nhận/đọc để tránh caller làm data phình hoặc sửa sau khi tính weight. Với nested objects cần chính sách immutability tương tự.

### 25.3. `expireAfterAccess` khác `expireAfterWrite`

Expire-after-access gia hạn theo thời gian truy cập, thích hợp cho session-like caches có policy hợp lệ. Expire-after-write không tự gia hạn khi hit, phù hợp muốn tái xác minh nguồn sau một khoảng cố định.

### 25.4. Size và TTL cùng được áp dụng

Entry có thể hết hạn vì idle timeout hoặc bị eviction vì vượt weight. Dùng metric để tách hai nguyên nhân; không giả định một timeout thay thế capacity.

### 25.5. Vẫn cần heap headroom

MaximumWeight=64 MiB không bao gồm đầy đủ Java object/metadata/internal overhead theo cách ước lượng này. Đừng cấu hình nó bằng đúng container memory limit.

## 26. Java Redis cache-aside: tách client cache khỏi nguồn

Có thể giữ repository độc lập với SDK Redis:

~~~java
import java.time.Duration;
import java.util.Optional;

public interface CacheClient {
    Optional<String> get(String key);
    void set(String key, String json, Duration ttl);
    void delete(String key);
}

public interface ProductRepository {
    Optional<ProductView> getFromSource(
        String tenantId, String sku
    );
}

public interface ProductJsonCodec {
    String encode(ProductView view);
    ProductView decode(String json);
}

public final class RedisBackedProductRead {
    private final CacheClient cache;
    private final ProductRepository source;
    private final ProductJsonCodec codec;
    private final Duration ttl = Duration.ofMinutes(2);

    public RedisBackedProductRead(
        CacheClient cache,
        ProductRepository source,
        ProductJsonCodec codec
    ) {
        this.cache = cache;
        this.source = source;
        this.codec = codec;
    }

    public Optional<ProductView> read(String tenantId, String sku) {
        String key = "product:" + tenantId + ":" + sku;
        Optional<String> cached = cache.get(key);
        if (cached.isPresent()) {
            return Optional.of(codec.decode(cached.get()));
        }

        Optional<ProductView> fromSource =
            source.getFromSource(tenantId, sku);
        fromSource.ifPresent(product ->
            cache.set(key, codec.encode(product), ttl)
        );
        return fromSource;
    }
}
~~~

### 26.1. Không dùng ví dụ như production complete

Mẫu chưa xử lý cache unavailable, stampede, stale repopulation race, authentication/authorization, negative caching, tenant key escaping, dual writes, timeout và version-aware cache fill.

### 26.2. Cache failure không nên mặc định thành source delete

Nếu `cache.get` timeout, service có thể bypass cache để đọc source theo policy; không trả NOT_FOUND. Nếu `cache.set` lỗi sau source read, vẫn có thể trả dữ liệu nguồn mà không coi bản ghi bị mất.

### 26.3. Secure key encoding

Trong ví dụ, key ghép string trực tiếp chỉ để dễ đọc. Production cần encode tenantId/SKU không gây collision/delimiter ambiguity, xác thực tenant, và bảo vệ dữ liệu nhạy cảm.

### 26.4. Codec schema version

Cache entries nên có versioned encoding nếu nhiều Java releases dùng chung Redis. Không để deserializer cũ đọc sai entry mới rồi ghi trở lại nguồn.

### 26.5. Command side không nằm trong cache helper

Việc sửa Product phải đi qua authoritative write service, dùng domain validation/version/CAS. Sau commit, phát invalidation/update event theo policy, không chỉ `cache.set` rồi coi như source đã thay đổi.

## 27. Redis CLI: cấu hình và quan sát thực tế

Các câu lệnh sau mang tính minh họa cho môi trường phát triển hoặc môi trường được cấp quyền:

~~~redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
INFO stats
DBSIZE
MEMORY STATS
MEMORY USAGE product:T1:SKU-A
TTL product:T1:SKU-A
PTTL product:T1:SKU-A
~~~

### 27.1. `TTL`

Thời gian còn lại của key theo seconds trong Redis nếu có expiry. Giá trị đặc biệt có thể biểu thị key không tồn tại hoặc không có expire; kiểm tra theo Redis version/API. `TTL` không đo khả năng key bị eviction sớm.

### 27.2. `MEMORY USAGE`

Ước tính bytes Redis dùng cho key và value theo khả năng API/encoding; các đối tượng phức tạp có sampling/đặc điểm riêng. Không suy đây là tổng RSS hoặc tất cả buffers của instance.

### 27.3. `INFO stats`

Các counters như `evicted_keys`, `expired_keys`, `keyspace_hits`, `keyspace_misses` hỗ trợ chẩn đoán. Counters thường là tích lũy từ lúc instance/server được tính lại; theo dõi **rate qua thời gian**, không so một giá trị tuyệt đối.

### 27.4. `INFO memory`

Những chỉ số thường quan tâm gồm `used_memory`, `used_memory_rss`, `maxmemory`, fragmentation và các buffers được báo theo version. Đọc nhiều chỉ số cùng nhau.

### 27.5. `CONFIG SET` là thay đổi vận hành

Thay `maxmemory`/eviction policy trên production cần review memory headroom, workload, security permissions, persistence của cấu hình và managed-service constraints. Không thử `FLUSHALL`, `CONFIG SET` hoặc stress fill trên dữ liệu thật chỉ để học bài.

## 28. Tại sao `noeviction` không đồng nghĩa lưu trữ bền

Một ứng dụng dùng Redis làm store:

~~~text
maxmemory-policy noeviction
append-only persistence configured
replication enabled
~~~

Nghe có vẻ “không bị mất”, nhưng:

1. Giới hạn memory có thể khiến một số writes không thành công.
2. Process/host có thể crash trước khi dữ liệu đủ durable theo policy.
3. Replica promotion trong replication bất đồng bộ có thể thiếu acknowledged writes tùy cấu hình.
4. AOF/RDB/persistence retention có failure windows và recovery semantics cụ thể.
5. Backup, disk space, corruption, human error và failover cần kế hoạch riêng.

### 28.1. Eviction policy khác persistence policy

`allkeys-lru` hoặc `noeviction` quyết định hành vi trước memory pressure. AOF/RDB và replication quyết định các phần của durability/recovery. Không thể thay thế lẫn nhau.

### 28.2. Cấu hình `noeviction` phù hợp khi không chấp nhận mất key tùy tiện

Nhưng ứng dụng phải xử lý memory pressure bằng backpressure/reject/scale; đồng thời duy trì backups/replication/persistence nếu source data cần sống qua crash.

### 28.3. TTL trên source-of-truth là deletion policy

Nếu Redis là nguồn duy nhất cho session, dùng `EXPIRE` làm session hết hạn là business decision. Nó không được gọi là “vô hại vì chỉ xóa cache”.

### 28.4. Khi nào cần chuyển state ra nguồn bền khác?

Nếu keys chứa inventory reservation, money ledger, unreplayed commands hoặc idempotency records phải sống dài hơn window của cache, xem xét durable database/ledger/queue với transaction/conditional semantics thích hợp.

## 29. Giới hạn bộ nhớ trong JVM: OOM và GC

Một ứng dụng dùng `ConcurrentHashMap<String, Product>` làm cache không có eviction:

~~~java
private final java.util.concurrent.ConcurrentHashMap<String, Object>
    unbounded = new java.util.concurrent.ConcurrentHashMap<>();
~~~

Nếu keys tăng liên tục, heap có thể phình cho tới khi GC tốn nhiều thời gian hoặc ném `OutOfMemoryError`.

### 29.1. Không gọi `HashMap` là cache an toàn khi thiếu bounds

Một map “tạm” nhưng không TTL/maximumSize có thể thành memory leak về mặt vận hành.

### 29.2. `WeakReference` không thay eviction policy

Weak references có lifecycle phụ thuộc GC và reachable graph, khó bảo đảm hit rate hoặc capacity ổn định. Chúng không thay một cache có admission/eviction/freshness policies.

### 29.3. `SoftReference` cũng không là lời hứa memory management

Hành vi thu hồi phụ thuộc JVM/heap/GC và không thích hợp để đảm bảo mức lưu trú hay thời gian sống của dữ liệu nghiệp vụ.

### 29.4. GC pressure có thể lớn hơn DB latency savings

Cache quá lớn tạo nhiều objects sống lâu, tăng pause/CPU và làm p99 xấu dù hit ratio cao. Theo dõi GC, heap usage, allocation rate cùng source QPS.

### 29.5. Một local cache trên mỗi pod

Scale service từ 5 lên 50 pods có thể tăng tổng memory cache và giảm hit ratio vì traffic được chia. L1 nên bounded per pod, còn L2 chia sẻ có thể giảm duplicate warming tùy workload.

## 30. Khi bộ nhớ cạn: hệ sẽ làm gì?

### 30.1. Cache có eviction

Để thêm entry, cache loại entry kém ưu tiên. Hệ có thể tiếp tục hoạt động nhưng miss ratio và origin load tăng.

### 30.2. Cache `noeviction`

Một số operations cần cấp phát bộ nhớ bị từ chối. Application phải xử lý lỗi, backpressure và SLO, không gộp thành `key not found`.

### 30.3. Cache nằm trong cùng process với app

Trước khi policy chạy kịp, allocation peak/GC hoặc OOM kill có thể xảy ra. Memory limit và request concurrency controls là hai tầng khác nhau.

### 30.4. Dirty write-back queue

Không được giải phóng dirty state chưa bền bằng cách lặng lẽ eviction. Cần flush, spill vào durable queue hoặc từ chối thêm writes.

### 30.5. Cache down nhưng source up

Nếu use case cho phép, bypass cache và dùng origin có rate limit. Tránh tất cả traffic cùng dồn xuống source: circuit breaker, admission control và degration policy cần được chuẩn bị.

## 31. Phân loại lỗi cache đúng cách

| Tình huống | Ý nghĩa | Hành động |
|---|---|---|
| Cache `MISS` | Không có usable entry | Đọc source nếu được phép |
| Cache `EXPIRED` | Entry không còn hợp lệ theo TTL | Revalidate/refill |
| Cache `EVICTED` | Entry đã bị loại vì capacity/policy | Treat as miss; quan sát memory pressure |
| Redis `OOM`/write rejected | Cache không chấp nhận write | Bỏ cache fill hoặc backpressure theo role |
| Cache connection timeout | Cache unavailable | Fallback/circuit breaker, không suy source not-found |
| Source `NOT_FOUND` | Authoritative absence theo read contract | Trả not-found; negative caching có giới hạn |
| Source `UNAVAILABLE` | Không xác minh được source | Trả unavailable/stale fallback theo policy |
| Source version conflict | Conditional write không đạt | Re-read/đánh giá nghiệp vụ |
| Source commit outcome unknown | ACK mất | Reconcile stable commandId, không retry mutation mù |

### 31.1. Cache miss không phải exception nghiệp vụ

Một ứng dụng coi `cache.get == null` là `ProductNotFound` đang khóa correctness vào capacity của Redis.

### 31.2. Cache write rejection có thể được bỏ qua khi cache thuần túy

Nếu DB source read thành công và cache SET thất bại do memory, application có thể trả source value; vẫn cần metric/alert. Nếu Redis là source, cùng lỗi đó không thể bỏ qua.

### 31.3. Circuit breaker có phạm vi

Tắt cache tạm thời khi Redis chập chờn có thể giảm retries nhưng làm tăng tải nguồn; cần giới hạn origin concurrency và monitoring.

### 31.4. Retry không sửa memory thiếu kéo dài

Redis liên tục ở maxmemory và `noeviction` sẽ không tự có thêm RAM vì client retry 100 lần. Cần giảm dữ liệu, thay chính sách phù hợp, tăng capacity hoặc thay data model.

## 32. Theo dõi hit ratio cùng miss penalty

Với một cache layer:

\[
\text{HitRatio}=\frac{\text{Hits}}{\text{Hits}+\text{Misses}}.
\]

Giả sử 100.000 requests, có 92.000 cache hits:

~~~text
Hit ratio = 92%.
Misses = 8,000 source lookups (trừ negative-cache và special paths).
~~~

### 32.1. Hit ratio cao vẫn có thể tệ

8% misses có thể tập trung vào các query rất đắt, tạo p99 latency/DB load xấu. Cần tính miss cost, origin QPS, byte hit ratio và cost theo tenant/query class.

### 32.2. Hit ratio thấp chưa chắc cache vô ích

Nếu cache chủ yếu giữ một tập kết quả tính toán cực đắt, chỉ cần tiết kiệm vài lần tính là có ích. Đánh giá cost-benefit thực thay vì chạy theo một tỷ lệ đẹp.

### 32.3. Measure latency cuối cùng

Cache hit 1 ms nhưng nguồn 50 ms; nếu cache miss storm làm nguồn 500 ms, p99 của người dùng có thể tệ hơn nhiều so với dự kiến. Nhìn theo end-to-end SLO.

### 32.4. Phân tách L1/L2

L1 miss nhưng L2 hit không tạo origin read. Đừng cộng tất cả misses của từng layer rồi coi là database QPS.

### 32.5. Eviction counters không cho biết key nào bị loại

Muốn biết workload gây thrash, quan sát keyspace/key sizes, hot keys, top commands, memory usage sampling và per-tenant metrics an toàn; không chỉ đọc tổng `evicted_keys`.

## 33. Monitoring và cảnh báo

| Nhóm chỉ số | Ví dụ | Phát hiện |
|---|---|---|
| Capacity | Used memory, maxmemory, headroom | Nguy cơ tới ngưỡng |
| RSS/fragmentation | RSS, allocator fragmentation | Memory pressure ngoài logical keys |
| Eviction | Evictions/s, victim patterns | Working set vượt capacity hoặc policy không phù hợp |
| Expiration | Expired keys/s, TTL distribution | TTL quá ngắn, expiry waves |
| Hits/misses | Hit ratio, origin reads | Hiệu quả cache |
| Origin impact | DB QPS, latency, throttling | Miss storm làm hỏng nguồn |
| Value sizes | p50/p95/p99 entry bytes | Outliers chiếm RAM |
| Churn | Key inserts/deletes/s | Cache thrashing |
| Contention | Inflight fills, coalescing waiters | Stampede |
| Read freshness | Stale age, version mismatches | Invalidation lag |
| Memory failures | OOM/write rejections | `noeviction` hoặc full capacity |
| Replication/failover | Replica lag, restarts | Cache cold/memory duplication |
| Java | Heap/RSS, GC pause, allocation rate | In-process cache overhead |
| Business | Missing products vs source not-found | Semantic errors |

### 33.1. Tỷ lệ quan trọng hơn counter tuyệt đối

`evicted_keys=1.000.000` từ lúc Redis khởi động không đủ nói hiện đang gặp sự cố. Quan sát delta theo phút, cùng source QPS và memory usage.

### 33.2. Tách keyspaces/tenants

Nếu tenant lớn tạo 90% cache churn, một alert chung che nguyên nhân. Dùng metrics theo nhóm tenant/tier và bounded cardinality. Không đưa raw PII hoặc tất cả entity IDs làm time-series labels.

### 33.3. Alert theo user impact

Evictions tăng nhưng p99 ổn và origin còn dư capacity có thể là cache làm việc bình thường. Evictions cùng với origin throttling, 5xx và pending queries mới là tín hiệu khẩn hơn.

### 33.4. Cache health không phải data health

Redis khỏe nhưng database source đã xóa Product mà cache vẫn trả Product cũ là lỗi correctness. Cần test và metric version/freshness, không chỉ cache uptime.

## 34. Case study: catalog giá thay đổi trong giờ cao điểm

Ứng dụng thương mại điện tử có:

~~~text
Source: NoSQL Products
Cache: Redis allkeys-lfu, TTL 5 minutes
Use case: Product detail, thousands reads/second
~~~

### 34.1. Eviction SKU nóng

Một đợt analytics scan làm cache thiếu RAM và key `SKU-A` bị loại. Những request tới SKU-A sau đó miss rồi tải từ source. **Sản phẩm không bị xóa**.

### 34.2. Thay đổi giá

Writer cập nhật giá v7→v8 ở database, phát outbox event để invalidation. Nếu invalidation chậm, cache có thể trả giá v7 trong TTL window. Màn hình hiển thị có thể chấp nhận stale trong giới hạn nhưng checkout price phải xác minh source/price authority.

### 34.3. Không dùng cached price như hợp đồng thanh toán

Giá hiển thị có thể là estimate; khi đặt hàng, cần tính giá theo rule/current quote đã cam kết và có version/expiry thích hợp. Eviction không thể dùng làm cách xác nhận giá mới.

### 34.4. Khi nào chọn LFU?

SKU phổ biến ổn định có thể hưởng lợi từ LFU. Tuy vậy, nếu flash-sale làm hot set thay đổi nhanh, cần đánh giá decay, TTL và admission. Không áp policy theo trực giác mà bỏ monitoring.

### 34.5. Kế hoạch sự cố

Nếu Redis restart và cold, rate limit cache fills, warm top products, cho phép fallback source với giới hạn. Không cho tất cả application pods đồng thời scan toàn bộ catalog.

## 35. Case study: session và quyền truy cập

Một ứng dụng dùng Redis lưu login sessions:

~~~text
sessionId -> userId, tenantId, roles, expiresAt
~~~

Nếu đây là **nguồn duy nhất** xác nhận session, eviction key khiến session bị mất, user bị logout. Nếu app vẫn coi TTL/session presence là quyền truy cập, phải nêu điều kiện hiệu lực và khả năng recovery.

### 35.1. Session có thể chủ ý expire

TTL của session là một business/security rule; không nhầm với eviction do thiếu RAM. Eviction sớm có thể tạo logout không mong muốn, dù không nhất thiết là lộ quyền.

### 35.2. Cache quyền có rủi ro ngược

Nếu nguồn đã revoke quyền nhưng cached `ADMIN` chưa invalidated, user có thể được phép quá lâu. Memory eviction có thể tình cờ loại entry, nhưng **không được dựa vào eviction để thi hành revoke**.

### 35.3. Token self-contained có kiểm chứng

Với một số JWT, verifier có thể xác minh chữ ký/hạn dùng mà không cần session store, nhưng revocation/token rotation vẫn có yêu cầu riêng. Cache hoặc Redis key absence không tự mô tả toàn bộ security policy.

### 35.4. Chọn eviction domain

Không trộn session store cần đảm bảo retention/expiry chính xác với catalog cache `allkeys-lru` trong một Redis instance nếu mất key gây hành vi nghiệp vụ không chấp nhận. Tách roles hoặc thiết kế session management thích hợp.

## 36. Case study: inventory và reservation

Nguồn NoSQL giữ `Inventory.available=10`, Redis cache trả số tồn kho gần nhất để UI hiển thị.

~~~text
UI displays: Available ~10 (cached estimate).
Checkout reserves 2:
    source executes atomic condition available >= 2
    source decrements and commits receipt
    cache invalidated/updated asynchronously
~~~

### 36.1. Eviction của inventory cache

Không làm tăng/giảm stock source. Lần đọc sau tải lại số lượng hiện tại.

### 36.2. Xóa item Inventory ở nguồn

Là thao tác domain/data lifecycle khác; cần xử lý reservations còn tồn tại, soft delete/tombstones và authorization. Cache không quyết định kết quả.

### 36.3. Không lấy cached stock để bảo vệ invariant

Hai clients đều thấy cache `available=10`, cùng reserve 8; nếu chỉ check trong cache hoặc read-then-write thiếu atomicity, hệ có thể oversell. Source phải enforce condition/quota authority.

### 36.4. Tránh idempotency metadata trong cache dễ eviction

Nếu `processedCommandId` chỉ tồn tại trong Redis cache với `allkeys-lru`, eviction có thể làm backend quên lệnh đã reserve và thực hiện lại khi retry. Dedupe record cần durability/retention phù hợp business horizon.

### 36.5. Unknown commit và cache

Sau timeout, cache `available=8` không chứng minh reservation command đã commit; có thể là write khác. Đối soát theo stable commandId tại authoritative source.

## 37. Khi Redis vừa là cache vừa là store

Một instance Redis chứa:

~~~text
cache:product:*      -> tái tạo từ Product DB.
session:*            -> state đăng nhập.
pending-payment:*    -> command state đang chờ.
dedupe:*             -> idempotency records.
~~~

Nếu chọn `allkeys-lru`, mọi keys thuộc cùng eviction domain có thể là ứng viên bị loại, bao gồm những keys mà ứng dụng **không chấp nhận mất**.

### 37.1. Phân vùng logical namespace chưa chắc đủ

Prefixes không tự tạo memory quota riêng nếu mọi keys dùng cùng global eviction policy. Dùng các instances/clusters/roles tách biệt hoặc giải pháp có per-namespace quotas thật sự theo công nghệ.

### 37.2. Nhóm có thể tái tạo

Catalog/display/search projections có thể chịu eviction, miễn còn source và fallback controls.

### 37.3. Nhóm cần durability

Unflushed writes, payment intents, unreplayed queue messages, idempotency logs và trạng thái quota có thể cần durable database/queue/transaction log, không nên bị loại ngẫu nhiên bởi cache policy.

### 37.4. Chọn noeviction không giải quyết memory capacity vô hạn

Nếu dùng Redis làm source, cần explicit sizing, reject/backpressure, persistence/replication, backup và failure recovery. `noeviction` không thay các yêu cầu đó.

### 37.5. Data classification là bước trước cấu hình

Mỗi key family cần trả lời: ai là owner, có thể mất không, TTL theo nghiệp vụ hay freshness, khôi phục từ đâu, idempotency retention bao lâu, có PII không, có cần region residency không?

## 38. Kiểm thử eviction, expiry và deletion

Không nên dựa chỉ vào một unit test giả lập `cache.get()` trả null. Cần những tình huống thực:

| Kiểm thử | Hành động trong môi trường test | Kết quả mong đợi |
|---|---|---|
| Capacity eviction | Đưa entries vượt ngân sách | Cache miss tăng nhưng source records còn |
| TTL expiry | Chờ/điều chỉnh clock test theo cơ chế thích hợp | Cache entry hết hiệu lực, source không bị delete |
| Source deletion | Delete record qua domain authority | Các reads sau propagation không trả dữ liệu cũ |
| Cache unavailable | Chặn cache connection | Fallback source/503 theo contract, không giả NOT_FOUND |
| Origin unavailable + cache miss | Chặn source | Trả unavailable hoặc stale có điều kiện |
| Eviction hot key | Loại key hot rồi burst reads | Có coalescing/backpressure, không stampede |
| Negative cache | Read missing rồi create source | Cache được invalidate hoặc TTL ngắn đủ |
| Stale refill race | Slow source read, concurrent update | Không vi phạm freshness contract |
| Redis `noeviction` full | Giới hạn RAM test và ghi thêm | Errors được phân loại đúng |
| `volatile-*` with no eligible keys | Tạo non-TTL keys | Không giả định cache luôn tự giải phóng được RAM |
| JVM cache OOM pressure | Tạo many large values trong test | Bounds/GC/memory controls hoạt động |
| CDC invalidation lag | Trì hoãn event | Stale age trong SLO hoặc fail-safe |
| L1 vs L2 inconsistency | Invalidate L2, giữ L1 | Propagation/TTL kiểm soát stale |
| Dirty write-behind eviction | Chưa flush source nhưng pressure tăng | Không mất dirty state không có durable copy |

### 38.1. Test nguồn còn nguyên sau eviction

1. Seed Product ở source với id và version rõ.
2. Fill cache.
3. Gây eviction hợp lệ trong **môi trường cô lập**.
4. Xác nhận source vẫn có Product.
5. Lần đọc tiếp theo trả lại Product từ source.

### 38.2. Test khác biệt TTL của cache với TTL của source

Đặt cache TTL ngắn; chờ hết hạn và xác nhận document nguồn vẫn tồn tại. Với TTL của source, kiểm query semantics và deletion/cleanup contract riêng.

### 38.3. Test source delete không bị cache hồi sinh

Gây race: một slow read lấy v7, writer delete v8 và invalidate, slow read cố fill v7. Kiểm application không trả data đã delete sau thời điểm contract yêu cầu, hoặc stale nằm trong cửa sổ đã công bố.

### 38.4. Test retry và idempotency

Nếu cache giữ dedupe hints, cố eviction rồi retry commandId cũ. Source authority phải không double-apply mutation. Dedupe chỉ ở cache dễ mất là anti-pattern.

### 38.5. Không thử phá production tùy tiện

Tăng maxmemory pressure, `FLUSHDB`, kill Redis primary hay chặn network có thể gây outage. Dùng test instance/dataset cô lập, quyền phê duyệt, monitoring và cleanup.

## 39. Runbook khi cache liên tục eviction

### 39.1. Bước 1 — Xác nhận tình trạng

Thu metrics memory, maxmemory policy, eviction rate, expiry rate, hit ratio, origin QPS, p95/p99 và errors. Xác định đây là **eviction** hay **expiration/invalidation**.

### 39.2. Bước 2 — Xác định data role

Kiểm cache có chứa state không thể tái tạo không. Nếu Redis là source/dirty write buffer, xử lý như một sự cố **data durability**, không chỉ performance.

### 39.3. Bước 3 — Phân tích workload

Top hot keys/key sizes, scan jobs, tenant whale, data churn, TTL distribution, one-off large values và batch fills. Tách theo pool/key family để tránh đo sai.

### 39.4. Bước 4 — Bảo vệ nguồn

Nếu misses tăng làm DB nguồn quá tải: rate limit fills, single-flight, circuit breaker, stale-if-error chỉ khi được phép, query cacheability và priority shedding.

### 39.5. Bước 5 — Điều chỉnh policy/capacity

Đánh giá tăng RAM, scale shards, TTL, admission, `allkeys-lru`/LFU, value compression/size caps, split workloads. Không đổi policy khi chưa biết data classes có thể mất hay không.

### 39.6. Bước 6 — Kiểm tra correctness

Đối chiếu source reads, version/invalidation lag, source deletes, idempotency state và auth/cache scopes. Hit ratio hồi phục không chứng minh dữ liệu đúng.

### 39.7. Bước 7 — Recovery và hậu kiểm

Warm top keys có giới hạn, giảm scan pollution, kiểm p99, origin load và alert. Ghi root cause: capacity thiếu, TTL waves, dirty data trộn cache, routing hoặc invalidation pipeline lỗi.

## 40. Những ngộ nhận thường gặp

### “Redis evict key thì MongoDB document cũng bị xóa”

Sai trong mô hình Redis chỉ là cache. Eviction không phát lệnh delete nguồn.

### “Redis luôn chỉ là cache”

Sai. Có ứng dụng dùng Redis như authoritative store; eviction lúc ấy có thể mất state quan trọng.

### “Key còn TTL nên không bị eviction”

Sai. Memory pressure có thể loại key trước expiry.

### “TTL=0 hay vừa hết hạn nghĩa RAM đã được giải phóng tức thì”

Không luôn đúng; cleanup/allocator/RSS có thời điểm khác nhau.

### “`volatile-ttl` chỉ loại keys đã hết hạn”

Sai; nó có thể chọn keys còn TTL dương, ưu tiên những keys gần hết hạn hơn.

### “`noeviction` bảo đảm không mất dữ liệu”

Không. Nó chỉ thay cách xử lý memory pressure; crash, replication/persistence và lỗi vận hành vẫn tồn tại.

### “`allkeys-lru` thích hợp cho mọi Redis instance”

Không nếu instance chứa state không được phép eviction.

### “LRU là chính xác tuyệt đối trong mọi sản phẩm”

Không. Một số implementations xấp xỉ để giảm overhead.

### “LFU luôn tốt hơn LRU”

Không. Lựa chọn phụ thuộc access pattern, decay và miss cost.

### “Tăng `maximumSize` là giới hạn RAM chính xác”

Không. Count khác bytes; còn metadata, GC, buffers, fragmentation.

### “Cache miss nghĩa Product không tồn tại”

Không. Miss chỉ nói cache không có usable entry.

### “Cache hit nghĩa thông tin luôn mới”

Không. Invalidation lag và TTL có thể trả stale.

### “Xóa cache key đồng nghĩa revoke quyền ngay trên mọi node”

Không nếu L1 caches hoặc replicas còn state cũ.

### “Viết source rồi xóa cache là linearizable”

Không mặc định vì stale repopulation race, invalidation failure, follower reads.

### “Eviction event là ProductDeleted event”

Không. ProductDeleted phải đến từ authoritative business change.

### “Cache key không có thì trả 404 luôn”

Không. Cần fallback authoritative read trước khi kết luận absence.

### “Cache lỗi OOM nghĩa Product not found”

Không. Đó là resource pressure, không phải kết quả nghiệp vụ.

### “Chỉ hit ratio là đủ đánh giá cache”

Không. Cần memory, miss penalty, origin QPS, p99 và correctness metrics.

### “Một batch scan nên cache mọi kết quả”

Không. Có thể làm pollute working set và đẩy hot keys ra khỏi cache.

### “Write-behind dirty value eviction cũng vô hại”

Không. Nếu update chưa được lưu bền ở nơi khác, có thể mất dữ liệu.

### “Eviction xóa commandId dedupe record không sao”

Nguy hiểm: retry command có thể double-apply mutation.

### “Tăng bộ nhớ là cách duy nhất chữa eviction”

Không. Có thể phải giảm entry size, thay admission policy, phân pool hoặc giới hạn scans.

### “TTL cache có thể thay TTL nghiệp vụ”

Không. Cache freshness và session/business expiry có vai trò khác.

### “Cache có thể tái tạo nghĩa không cần backup source”

Sai. Cache không thay backup/recovery của nguồn có thẩm quyền.

## 41. Checklist thiết kế eviction và giới hạn bộ nhớ

1. **Phân loại data:** Entry có thể tái tạo từ authoritative source không?
2. **Xác định owner:** Source ở đâu, ACK/durability/failover contract nào?
3. **Chọn caching strategy:** Cache-aside, write-through, read-through hoặc write-behind.
4. **Không trộn dirty data với eviction tùy ý.**
5. **Định nghĩa key namespace:** Tenant, resource ID, schema/revision và authorization scope.
6. **Chọn TTL theo freshness,** không dùng TTL như residency guarantee.
7. **Chọn capacity:** Max entries/bytes, real memory headroom.
8. **Chọn eviction policy theo workload:** LRU, LFU, random, TTL-priority hoặc admission.
9. **Đánh giá eligible keys:** Đặc biệt với Redis `volatile-*`.
10. **Kiểm chứng `noeviction` errors:** Không loop retry vô hạn.
11. **Giữ source deletion riêng cache deletion.**
12. **Thiết kế invalidation sau source commits** bằng outbox/CDC khi cần.
13. **Phòng stale repopulation race:** CAS/versioned fill hoặc authoritative bypass cho strong decisions.
14. **Bảo vệ origin khỏi stampede:** Single-flight, jitter, rate limits, bounded concurrency.
15. **Dùng negative caching có TTL và invalidation riêng.**
16. **Tách L1/L2 responsibilities**, không quên local cache invalidation.
17. **Cấm cache-only business authority không được phép mất.**
18. **Kiểm thử eviction, expiry và source delete tách rời.**
19. **Theo dõi evictions/s, expirations/s, hit ratio, memory/RSS, DB load và p99.**
20. **Quản lý schema/cache codec versions** khi nhiều bản Java chạy song song.
21. **Định nghĩa failure policy:** Cache down vs source down, stale fallback theo use case.
22. **Kiểm thử restart/failover/persistence** nếu Redis là source chứ không chỉ cache.
23. **Kiểm tra privacy/security:** PII và permission changes không bị stale quá SLO.
24. **Có runbook khi memory pressure kéo dài** và không thao tác phá dữ liệu thật.

### 41.1. Một mẫu policy review

~~~yaml
cacheName: product-detail
role: "disposable read projection"
sourceOfTruth: "authoritative NoSQL product store"

key:
  identity: "(tenantId, sku)"
  schemaVersion: 3
  containsPII: false

freshness:
  ttlSeconds: 120
  invalidation: "source outbox / CDC event"
  staleReadAllowed: "UI only within documented window"
  strongDecisionPath: "bypass cache"

capacity:
  maxMemory: "<measured budget>"
  headroom: "<based on RSS and buffers>"
  evictionPolicy: "<based on workload traces>"
  maximumCacheableValue: "<measured cap>"

failure:
  cacheMiss: "read source"
  cacheUnavailable: "bounded source fallback"
  sourceUnavailable: "return unavailable or policy-approved stale"
  stampede: "single-flight + rate limit"
  negativeCache: "short TTL with create invalidation"

correctness:
  versionAwareFill: "<protocol if required>"
  deletionAuthority: "source only"
  commandDedupe: "durable source, not evictable cache"

validation:
  evictionVsDeleteTest: "required"
  staleFillRaceTest: "required"
  capacityLoadTest: "required"
~~~

Các placeholder cần số đo và triển khai đã kiểm chứng; mẫu không phải cấu hình chuẩn cho mọi sản phẩm.

## 42. Bài tập thực hành

### Bài 1 — Eviction so với source delete

Product `SKU-A` có trong MongoDB và Redis. Redis loại cache key khi đầy RAM. Hãy mô tả lần đọc tiếp theo và chứng minh tại sao không nên phát `ProductDeleted`.

### Bài 2 — TTL và eviction

Cache key có TTL một giờ nhưng biến mất sau hai phút. Nêu những nguyên nhân có thể xảy ra và cách phân biệt bằng metrics/operation logs.

### Bài 3 — Source TTL

Session có TTL trong Redis cache 5 phút nhưng authoritative database giữ `expiresAt` 30 phút. Phân tích business expiry và cache refresh policy.

### Bài 4 — Redis `allkeys-lru`

Một Redis instance chứa `cache:product:*` và `dedupe:payment:*`. Giải thích rủi ro nếu chọn allkeys-lru và đề xuất tách role/durable dedupe.

### Bài 5 — Redis `volatile-*`

Cache dùng `volatile-lru` nhưng 90% keys không có TTL. Khi bộ nhớ cạn, vì sao writes có thể bị lỗi dù có nhiều keys? Thiết kế policy/TTL/classification sửa vấn đề.

### Bài 6 — `noeviction`

Hệ chọn `noeviction` để “không mất data”, nhưng Redis bắt đầu từ chối write khi đạt memory limit. Viết response/backpressure policy cho cache-only và Redis-source cases.

### Bài 7 — LRU vs LFU

Cho trace một key A được đọc 1.000 lần hôm qua và key B vừa đọc một lần. Phân tích lựa chọn LRU/LFU và vai trò của decay.

### Bài 8 — Scan pollution

Một job analytics quét 10 triệu items, nhiều items chỉ đọc một lần. Sau đó hit ratio của API online giảm. Hãy đề xuất admission/bypass cache và phân tách pools.

### Bài 9 — Memory sizing

Ước lượng RAM cho 1 triệu keys với trung bình key=60 bytes, value=600 bytes, metadata=140 bytes; bổ sung những chi phí mà 800 MB logical chưa bao gồm.

### Bài 10 — Large value

Cache 64 MiB nhận một report 50 MiB. Vì sao maximumSize theo count không đủ? Thiết kế maximumWeight/admission và giới hạn value.

### Bài 11 — Java Caffeine

Viết cache `maximumSize=10_000`, `expireAfterWrite=120s`, `recordStats`; giải thích sự khác nhau giữa eviction và expiry trong metrics.

### Bài 12 — Mutable objects

Một cached `List<Order>` bị caller thêm items sau khi put vào cache. Phân tích rủi ro correctness/weight và đề xuất immutable copy.

### Bài 13 — Cache-aside miss

Redis không có `SKU-B`, nhưng source còn record. Thiết kế flow GET đúng, bao gồm source unavailable và serialization error.

### Bài 14 — Negative caching

Cache trả NOT_FOUND cho Product mới được tạo sau 10 giây. Đề xuất negative TTL và invalidation on-create; vì sao không cache backend timeout như NOT_FOUND?

### Bài 15 — Stampede

Một hot key bị eviction, 5.000 requests đồng thời miss. Thiết kế local single-flight, distributed fill budget, rate limiting và graceful degradation.

### Bài 16 — TTL herd

Một triệu keys đều được ghi với TTL=300s vào cùng thời điểm. Sau năm phút, origin QPS tăng mạnh. Thiết kế TTL jitter và kiểm soát concurrency.

### Bài 17 — Stale repopulation

Reader lấy Product v7, Writer commit v8 và invalidate, Reader lại fill v7. Vẽ timeline và đề xuất version-aware fill hoặc authoritative bypass cho strong read.

### Bài 18 — Source delete và tombstone

Product bị xóa ở nguồn nhưng một replica đọc chậm còn v7; cache miss khiến ứng dụng fill lại v7. Làm sao dùng delete marker, consistency và version guard để không resurrect?

### Bài 19 — Write-through

DB ghi thành công, Redis SET thất bại. API trả gì? Cache xử lý thế nào? Nếu Redis ghi trước DB rồi DB fail, có thể có lỗi gì?

### Bài 20 — Write-behind

Ứng dụng ACK sau khi ghi dirty value vào cache, chưa flush source. Entry bị eviction. Hãy chỉ ra rủi ro mất dữ liệu và thiết kế durable log/flush-before-evict.

### Bài 21 — Redis persistence

So sánh `noeviction`, AOF/RDB, replication và backups. Vì sao không yếu tố nào riêng lẻ đủ bảo đảm durability trong mọi fault model?

### Bài 22 — L1/L2

L1 Caffeine còn Product v7, L2 Redis đã invalidate và source là v8. Thiết kế invalidation propagation và fallback TTL khi event bị mất.

### Bài 23 — Security

Cache chứa permission ADMIN, nguồn đã revoke quyền. Eviction có phải cách bảo đảm revoke không? Chọn authoritative check/versioning và freshness SLO.

### Bài 24 — Inventory

Cached inventory hiển thị 10, nhưng hai users muốn reserve 8 cùng lúc. Vì sao không thể dựa trên cache? Viết conditional reservation tại source.

### Bài 25 — Monitoring

Một dashboard cho thấy Redis used_memory gần maxmemory, evicted_keys/s tăng, hit ratio giảm, source p99 tăng. Viết kế hoạch điều tra ưu tiên và khả năng load shedding.

### Bài 26 — Cache key collisions

Hai tenants cùng dùng `SKU-A`, nhưng cache key chỉ là `product:SKU-A`. Giải thích rủi ro dữ liệu và đề xuất tenant-scoped key cùng authorization.

### Bài 27 — Warm-up sau restart

Một Redis node restart khiến hot keys biến mất. Thiết kế prewarm top-K có rate limit và fallback source mà không tạo stampede.

### Bài 28 — Dirty state classification

Một Redis instance chứa catalog cache, payment intents và command dedupe records. Phân loại thứ có thể eviction, thứ cần durability/retention, rồi đề xuất physical separation.

### Bài 29 — Fault injection

Thiết kế integration test gây eviction trên instance cô lập; assert Product source không đổi, client đọc lại đúng và không phát domain deletion event.

### Bài 30 — Review thiết kế sai

Một tài liệu đề xuất: “Đặt TTL=24h để key không bị eviction; dùng Redis `allkeys-lru` cho cả cache và payment state; Redis miss nghĩa Product bị xóa; khi nguồn cập nhật, chỉ xóa L2; hit ratio cao là đủ chứng minh đúng.” Hãy phản biện từng giả định và đề xuất thiết kế an toàn hơn.

---

**Kết luận:** **Eviction** là chính sách loại cache entries để tuân thủ ngân sách bộ nhớ; **expiration** là hết thời hạn hiệu lực, **invalidation** là làm bản sao cache trở nên không dùng được khi nguồn thay đổi, còn **source deletion** mới là thao tác xóa dữ liệu nghiệp vụ tại nơi có thẩm quyền. Trong cache-aside, eviction có thể làm tăng miss và tải database nhưng **không xóa document NoSQL gốc**. Ngược lại, nếu Redis hoặc write-behind buffer đang giữ **bản duy nhất của dữ liệu chưa được lưu bền**, eviction có thể là mất dữ liệu thật. Chọn `maxmemory`, LRU/LFU/TTL policy, giới hạn entries/bytes và headroom phải dựa trên **vai trò của từng key, working set, miss cost và fault model**, không chỉ một hit ratio. Để vận hành an toàn, cần **source-of-truth rõ ràng, bounded memory, chống stampede, invalidation có version/consistency, retry/fallback đúng nghĩa, kiểm thử eviction tách khỏi deletion và quan sát ảnh hưởng lên nguồn**.
