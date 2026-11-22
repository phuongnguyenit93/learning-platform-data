# Cache-aside, read-through, write-through và write-behind

## 1. Vì sao cần phân biệt bốn chiến lược cache?

Trong hệ thống NoSQL, cache thường được đặt giữa ứng dụng và nơi lưu dữ liệu chính để giảm độ trễ, giảm số lần truy cập database và hấp thụ một phần tải đọc. Những hệ như Redis, Memcached, cache trong tiến trình Java, CDN hoặc bộ nhớ đệm tích hợp của database đều có thể tham gia, nhưng **cách ứng dụng phối hợp cache với nguồn dữ liệu** mới quyết định hành vi khi đọc, ghi và gặp lỗi.

Xét một dịch vụ sản phẩm:

```text
                  Java API
                     |
                     v
               Cache Layer
                     |
                     v
            NoSQL Source of Truth
         MongoDB / DynamoDB / Cassandra ...
```

Người dùng liên tục xem sản phẩm `P100` và thỉnh thoảng người bán cập nhật giá. Nếu hệ chỉ đặt một Redis `GET` trước MongoDB mà không xác định quy tắc ghi/xóa cache, sản phẩm có thể vẫn hiển thị giá cũ. Nếu ghi vào cache trước rồi để database cập nhật sau, khi Redis hoặc worker ghi nền gặp lỗi, có thể mất một thay đổi mà API đã báo thành công.

Bốn chiến lược cốt lõi:

1. **Cache-aside (lazy loading):** ứng dụng tự đọc cache trước, khi miss mới đọc database và điền cache; ứng dụng thường ghi database rồi xóa/cập nhật cache.
2. **Read-through:** ứng dụng đọc qua cache abstraction; chính cache layer/loader chịu trách nhiệm nạp từ database khi miss.
3. **Write-through:** đường ghi đi qua cache và hoàn tất thao tác lưu xuống backing store **đồng bộ** trước khi xác nhận theo hợp đồng cấu hình.
4. **Write-behind (write-back):** cập nhật được chấp nhận tại tầng cache/queue trước, còn backing store được ghi **bất đồng bộ**.

Chúng khác nhau chủ yếu ở **ai điều phối cache miss, ai điều phối write và thời điểm một write được xem là thành công**. Không nên gọi mọi ứng dụng “đọc Redis rồi đọc DB” là read-through, hoặc gọi thao tác “DB write rồi xóa key Redis” là write-through.

## 2. Bốn thành phần phải gọi tên rõ

| Thành phần | Vai trò | Câu hỏi quan trọng |
|---|---|---|
| Client | Gửi request tới Java API | Khi nhận success thì dữ liệu đã ở đâu? |
| Application/service | Thực thi nghiệp vụ | Có tự xử lý cache miss/invalidation không? |
| Cache | Giữ dữ liệu để đọc nhanh | Có thể bị eviction, hết TTL, mất dữ liệu hay stale không? |
| Backing store/NoSQL DB | Lưu trạng thái chính theo thiết kế | Có là source of truth không? |
| Loader/writer/worker | Kết nối giữa cache và DB | Đồng bộ hay async? Retry, ordering, idempotency ra sao? |

**“Cache” không mặc định luôn là dữ liệu không quan trọng.** Trong cache-aside thông dụng, NoSQL DB là nguồn sự thật. Trong write-behind, cache hoặc một hàng đợi bền vững có thể tạm giữ **write đã được nhận nhưng database chưa có**. Khi ấy rủi ro mất write và trách nhiệm phục hồi khác hẳn.

Một dữ liệu được lưu trong cache cũng không tự “được bảo vệ” chỉ vì cache có replication. Cần kiểm tra persistence, failover, write acknowledgements và quy trình replay thật.

## 3. Hai luồng cần xem riêng: đọc và ghi

Không có một thiết kế cache đầy đủ chỉ bằng luồng đọc. Mỗi hệ phải công bố cả:

- **Read path:** hit/miss; lấy dữ liệu ở đâu; có chấp nhận stale không; làm gì khi cache lỗi.
- **Write path:** client ghi vào đâu trước; điều kiện commit; invalidate/update cache thế nào; nếu một bước thất bại thì rollback, retry hay reconcile.
- **Failure path:** mất cache, mất DB, mất mạng giữa hai hệ, client timeout, duplicate requests, node failover.
- **Consistency contract:** đọc sau ghi có được thấy giá trị mới không, trên tất cả instances hay chỉ một session?
- **Durability contract:** khi API trả success, dữ liệu tồn tại ở nguồn chính hay chỉ còn trong cache/queue?

Sơ đồ tư duy:

```text
                Request
                   |
        +----------+-----------+
        |                      |
       READ                   WRITE
        |                      |
  Cache hit/miss?       Who accepts first?
        |                      |
  When load source?     When persisted?
        |                      |
  Stale acceptable?     When invalidate?
        |                      |
  What if cache down?   What if worker down?
```

## 4. Cache-aside: ứng dụng chủ động điều phối cache

**Cache-aside**, còn gọi lazy caching, là mô hình rất phổ biến trong ứng dụng Java kết nối Redis và MongoDB/DynamoDB/Cassandra.

### 4.1. Luồng đọc

```text
Client
  |
  v
Application
  |
  | 1. GET key
  v
Cache -------- hit --------> Return cached value
  |
  | miss
  v
Application
  |
  | 2. Read from NoSQL
  v
Database
  |
  | 3. Value
  v
Application
  |
  | 4. SET key with TTL
  v
Cache
  |
  v
Return value to client
```

Giả mã:

```text
read(productId):
    cached = cache.get(productId)
    if cached exists:
        return cached

    product = database.findById(productId)
    if product exists:
        cache.set(productId, product, ttl)

    return product
```

**Ai chịu trách nhiệm tải dữ liệu?** Ứng dụng. Cache thường không tự biết cách gọi NoSQL khi miss.

### 4.2. Luồng ghi thông dụng: DB trước, cache invalidation sau

```text
Client -> Application
              |
              | UPDATE product P100
              v
          Database
              |
              | COMMIT success
              v
         Application
              |
              | DELETE cache key P100
              v
            Cache
              |
              v
         Return success
```

Giả mã:

```text
update(productId, patch):
    committed = database.update(productId, patch)
    cache.delete(cacheKey(productId))
    return committed
```

Đây là **cache-aside với invalidation**, không phải write-through. Giá trị mới sẽ được nạp vào cache khi có read miss tiếp theo.

### 4.3. Tại sao invalidate thay vì update giá trị mới?

- Tránh phải tái tạo mọi dạng cache projection ngay trên đường ghi.
- Giảm logic đồng bộ khi một object có nhiều keys/query caches.
- Khi có read sau, dữ liệu được tải lại từ nguồn authoritative.
- Có thể tránh ghi sai một representation không còn phù hợp.

Nhưng cache miss ngay sau write tăng database reads. Hệ có thể cập nhật cache theo một chính sách khác nếu kiểm soát được ordering và bản ghi mới.

### 4.4. Ưu điểm

- Dễ hiểu, dễ áp dụng với Redis/Memcached.
- Ứng dụng kiểm soát TTL, dữ liệu nào được cache và format.
- Cache chỉ chứa những keys được truy cập; hiệu quả với tập dữ liệu nóng.
- DB vẫn là nguồn sự thật, dễ xây đường fallback khi cache unavailable.
- Không bắt buộc cache hỗ trợ loader/writer abstraction.

### 4.5. Nhược điểm

- Cold miss tăng latency và tải DB.
- Logic cache được cài trong service/repository wrapper.
- Invalidation sai hoặc bị bỏ qua gây stale data.
- Query/list caches và derived keys khó invalidation toàn bộ.
- Có race giữa read miss và concurrent update.
- Cache stampede khi nhiều requests cùng miss.

## 5. Cache-aside: race khi đọc bản cũ rồi điền lại cache

Một lỗi đặc biệt quan trọng:

```text
T0: Cache key P100 đang trống
T1: Reader A miss cache, đọc DB: price=100
T2: Reader A tạm dừng trước cache.set()
T3: Writer B update DB price=120 -> COMMIT
T4: Writer B DELETE cache key P100
T5: Reader A tiếp tục SET cache price=100
T6: Request mới đọc cache price=100
```

Tại T5, dữ liệu **đã cũ được tái nạp sau invalidation**. TTL cuối cùng có thể làm nó hết hạn, nhưng trong khoảng đó người dùng thấy sai.

Đây không phải lỗi Redis “đọc không nhất quán”; nó là **lỗi phối hợp hai thao tác không nguyên tử** giữa NoSQL và cache.

### 5.1. Những cách giảm hoặc loại trừ race theo yêu cầu

- **Short TTL:** giới hạn thời gian stale trong một số tình huống, nhưng không bảo đảm không stale.
- **Version-aware fill:** chỉ ghi vào cache nếu version nạp từ source không thấp hơn version hiện có/được biết tại authority.
- **Invalidation event sau source commit:** giảm những trường hợp quên xóa key, nhưng event cũng có thể đến muộn; cần version/tombstone guard.
- **Per-key coordination:** serialize fill và write/invalidate theo một cơ chế an toàn; cân nhắc availability/complexity.
- **Read authoritative source:** dùng cho quyết định không chấp nhận stale.
- **Double delete với delay:** đôi khi giảm race theo giả định thời gian, nhưng **không phải bảo đảm correctness** nếu reader bị chậm quá thời gian delay.

### 5.2. Version phải có provenance

Version nên được cấp bởi nguồn authoritative trong phạm vi aggregate/key, ví dụ `Product.version=42`. Không coi timestamp do các writers tự tạo trên nhiều vùng là một thứ tự global đáng tin nếu chưa có giao thức.

### 5.3. Eviction làm mất version guard

Nếu cache giữ `(version=42, value)` rồi toàn key bị evict, một event cũ `version=41` đến sau có thể tái tạo key nếu writer không kiểm tra source/current authoritative version. Với dữ liệu quan trọng, cần marker/epoch có retention phù hợp hoặc chuyển kiểm tra về authority.

## 6. Cache-aside: database commit nhưng invalidation thất bại

Một timeline khác:

```text
T0: Cache P100=100
T1: DB UPDATE P100=120 -> COMMIT
T2: Redis DELETE P100 -> timeout
T3: API trả lỗi hoặc tiến trình crash
T4: Cache vẫn có P100=100
```

DB đã có 120, cache vẫn có 100. Nếu API trả lỗi, client có thể retry; nếu API trả success, reader có thể thấy stale.

### 6.1. Không thể rollback DB chỉ vì Redis lỗi

DB và Redis thường không nằm trong cùng ACID transaction. Một `try/catch` không biến chúng thành một đơn vị atomic.

### 6.2. Hướng thiết kế

- Chọn **DB authoritative** và chấp nhận stale có giới hạn trong một số paths.
- Ghi invalidation intent vào **outbox** cùng transaction với DB mutation rồi relay đến cache.
- Dùng CDC để phát event thay đổi.
- Giữ TTL như một lớp bảo vệ khi invalidation bị bỏ qua.
- Có metrics và reconciliation cho invalidation lag/failures.
- Với business-critical read, tránh cache hoặc xác thực source version.

### 6.3. Outbox không đảm bảo mọi read tức thì mới

Một outbox event sẽ được relay sau commit. Trong thời gian giữa source commit và cache invalidation, cached value có thể vẫn cũ. Nếu yêu cầu linearizable read, phải dùng đường authoritative hoặc protocol coherence mạnh hơn.

## 7. Read-through: cache layer tự gọi loader khi miss

**Read-through** đặt trách nhiệm nạp dữ liệu trong cache/provider abstraction thay vì ứng dụng tự viết `cache.get` rồi `database.find`.

```text
Client -> Application
               |
               | cache.read(P100)
               v
           Cache Layer
             /     \
            /       \ hit: return cached value
           v
         miss
           |
           | invoke configured loader
           v
       NoSQL Database
           |
           | load data
           v
       Cache stores value
           |
           v
       Return to application
```

Pseudo-API:

```java
Product product = loadingCache.get("P100");
```

Cache biết cách gọi `ProductLoader` do ứng dụng cấu hình.

### 7.1. Khác cache-aside ở đâu?

- Cache-aside: **service** tự kiểm tra miss và gọi DB.
- Read-through: **cache/provider/loader** tự thực hiện miss-to-source flow.

Về hiệu năng, hai mô hình có thể tương tự nếu đều đọc DB khi miss; khác biệt chính nằm ở vị trí quản lý logic, API contract và khả năng load/coalesce/refresh của cache layer.

### 7.2. Read-through không tự quy định write path

Ứng dụng có thể:

- Dùng read-through cho đọc, rồi ghi DB và invalidate cache.
- Kết hợp read-through + write-through nếu provider hỗ trợ.
- Dùng read-through trên một dữ liệu read-only.
- Dùng read-through cùng refresh-ahead.

**Read-through không đồng nghĩa write-through.**

### 7.3. Ưu điểm

- Đường đọc ở service ngắn gọn.
- Tập trung loader logic.
- Provider có thể hỗ trợ coalescing miss, expiry/refresh và metrics.
- Dễ tái sử dụng caching policy qua nhiều consumers nếu loader contract phù hợp.

### 7.4. Nhược điểm

- Logic truy cập database bị giấu trong cache configuration.
- Cache miss có thể kích hoạt DB request bất ngờ.
- Loader lỗi/timeout phải có policy rõ.
- Không phải cache nào cũng có built-in read-through.
- Distributed loader chạy ở đâu? Trong JVM app hay trên cache server? Phụ thuộc sản phẩm.

## 8. Read-through và `@Cacheable` trong Spring không hoàn toàn đồng nghĩa

Spring Cache:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public Product getProduct(String productId) {
    return productRepository.findById(productId)
            .orElseThrow();
}
```

Khi cache miss, Spring interceptor có thể gọi method được đánh dấu, rồi lưu kết quả theo `CacheManager`. Với cách nhìn từ caller, đây giống **read-through ở tầng Spring cache abstraction**. Nhưng:

- Đường nạp dữ liệu được định nghĩa bởi **method ứng dụng**, không nhất thiết bởi native cache server.
- Redis không tự biết gọi `productRepository.findById`.
- Tùy cấu hình, `@Cacheable(sync = true)` có thể nhờ cache provider đồng bộ một số concurrent loads trong phạm vi hỗ trợ; **không tự tạo distributed lock toàn cụm**.
- Self-invocation trong cùng một bean có thể không đi qua proxy interception của Spring AOP theo chế độ phổ biến.
- Cache key, serializer, TTL và null handling phải cấu hình.
- `@Cacheable` không tự xử lý distributed invalidation giữa nhiều service writers.

Để phân biệt chính xác:

| Cách viết | Trách nhiệm miss |
|---|---|
| Service gọi `redis.get`, miss thì `repository.findById` | Cache-aside |
| Spring interceptor gọi annotated method khi cache miss | Framework-managed lazy caching, read-through-like |
| Native cache `get` tự gọi registered database loader | Read-through do cache provider/loader cung cấp |

Đừng đoán cơ chế chỉ qua annotation; xem đường thực thi và chỗ loader thực sự chạy.

## 9. Write-through: đồng bộ giá trị với backing store trên đường ghi

**Write-through** thường được định nghĩa là ứng dụng gửi write qua cache layer, và cache layer **ghi đồng bộ xuống backing store** trước khi báo hoàn thành theo hợp đồng.

```text
Client
  |
  v
Application
  |
  | write(P100, value)
  v
Cache / Cache Writer
  |
  | synchronous persist
  v
Backing Store (NoSQL)
  |
  | acknowledged
  v
Cache Layer updates/keeps value
  |
  v
Client receives success
```

Điểm phân biệt với write-behind: đường ghi **đợi kết quả backing-store write** thay vì chỉ chấp nhận mutation vào cache/queue để persist sau.

### 9.1. Ai gọi DB?

Trong read-through/write-through kết hợp, ứng dụng thường thao tác qua cache abstraction và cache writer chịu trách nhiệm gọi database.

Nếu service tự gọi `db.save` rồi `redis.set`, có thể mô phỏng đồng bộ hóa tương tự về kết quả, nhưng theo ngôn ngữ kiến trúc nên mô tả rõ là **application-managed dual write**, không mặc nhiên là provider-managed write-through.

### 9.2. Ưu điểm

- Dữ liệu vừa ghi có thể đã ở cache cho lần read sau.
- Backing store được cập nhật đồng bộ, giảm cửa sổ writes chưa persist so với write-behind.
- Một điểm điều phối policy có thể giảm lệch logic nhiều services.
- Phù hợp với dữ liệu đọc lại nhiều ngay sau khi ghi.

### 9.3. Nhược điểm

- Write latency có thêm chi phí của cả backing store và cache.
- Hai hệ khác nhau không có atomic commit mặc định.
- Cache writer/provider trở thành một điểm ảnh hưởng availability của writes.
- Mỗi lần ghi có thể update cache dù key ít khi được đọc, tốn memory.
- Concurrent writes có thể cập nhật cache sai thứ tự nếu không có version guard.
- Write-through không đồng nghĩa mọi replicas/readers đều nhất quán tức thì.

## 10. Write-through: chọn thứ tự và xử lý partial failure

Từ “đồng bộ” không có nghĩa cả cache và DB cùng commit trong một transaction.

### 10.1. Cache trước, DB sau

```text
1. Cache SET value=120
2. DB WRITE value=120
```

Nếu DB ghi thất bại, cache có thể đang hiển thị 120 dù source vẫn là 100. Nếu cache ghi thành công nhưng worker/process crash trước DB, giá trị chưa authoritative đã lộ.

### 10.2. DB trước, cache sau

```text
1. DB WRITE value=120 (COMMIT)
2. Cache SET value=120
```

Nếu bước 2 thất bại, DB đã là 120 nhưng cache có thể giữ 100. Trả lỗi cho client ở bước 2 không làm DB rollback.

### 10.3. Một cache writer có thể quản lý lỗi tốt hơn

Provider-managed write-through có thể quy định rõ thứ tự và khi nào ACK. Nhưng nó vẫn phải giải quyết sự cố giữa hai hệ nếu không có atomic transaction chung.

### 10.4. Ma trận lỗi khái quát

| Điểm lỗi | Hệ quả | Chính sách có thể dùng |
|---|---|---|
| Cache update fail trước DB write | Không có write source | Trả lỗi, retry idempotent |
| Cache update success, DB write fail | Cache chứa giá trị chưa authoritative | Rollback/invalidate cache, tránh expose sớm |
| DB commit, cache update fail | Cache stale hoặc miss | Invalidate/retry/outbox/TTL |
| Client timeout sau DB commit | Unknown outcome ở client | Operation ID, tra trạng thái DB |
| Hai writers commit DB đúng thứ tự nhưng cache updates đảo | Cache giữ bản cũ | Source version và conditional cache update |
| Cache evict ngay sau write | Read kế tiếp miss | Fallback/loader, không coi eviction là mất source data |

### 10.5. Một phân biệt thực tế

Nếu nghiệp vụ cho phép cache lỗi mà write DB vẫn thành công, API có thể chọn **DB first + best-effort invalidation**. Nhưng đó là hợp đồng **write path có degraded cache**, không phải bảo đảm “cả hai luôn cùng cập nhật” như nhiều người suy khi nghe write-through.

## 11. Write-behind: chấp nhận ghi nhanh, persist DB sau

**Write-behind**, còn gọi **write-back caching**, đặt thao tác ghi vào cache hoặc một hàng đợi cập nhật và thực hiện ghi xuống backing store ở tiến trình nền.

```text
Client
  |
  v
Application
  |
  | write(P100, value=120)
  v
Cache / Write Buffer
  |
  | accepted
  +----------------------> Client success/accepted
  |
  | async queue
  v
Background Flusher
  |
  | batch / retry / coalesce
  v
NoSQL Backing Store
```

Đường ghi có thể có latency thấp vì không chờ database write. Nhưng **thời điểm ACK thay đổi ý nghĩa**: DB có thể vẫn giữ giá trị cũ.

### 11.1. Ví dụ

```text
T0: DB P100.price=100
T1: App ghi cache price=120
T2: API trả "accepted"
T3: Worker chưa flush DB
T4: DB vẫn price=100
T5: Worker flush thành công
T6: DB price=120
```

Tại T3, nếu cache bị mất và write buffer không durable, mutation 120 có thể biến mất.

### 11.2. Khi phù hợp

- Các cập nhật có tần suất cao và có thể batch/coalesce.
- Một số metrics/counters hoặc state có thể mất phần rất nhỏ theo contract.
- Workload yêu cầu write latency thấp hơn backing-store RTT.
- Có durable log/queue và recovery cho các writes không được phép mất.
- Hệ có thể chịu được khoảng chậm giữa accepted và persisted.

### 11.3. Khi không phù hợp nếu thiết kế sơ sài

- Payment capture/ledger authoritative.
- Inventory cuối cùng cần reservation atomic ở source.
- Security permission revocation tức thì.
- Ghi dữ liệu phải audit đầy đủ mọi intermediate mutation.
- Các hệ không thể chịu delayed persistence hoặc rollback sau crash.
- API hứa “đã lưu bền vững” nhưng chỉ ghi RAM.

**Nếu business không chấp nhận mất write, dùng một cache volatile làm nơi duy nhất giữ accepted writes là rủi ro nghiêm trọng.**

## 12. Write-behind: độ bền của queue mới là trọng tâm

Một kiến trúc write-behind đáng tin hơn có thể dùng durable operation log:

```text
                 Application
                      |
                      | append operationId, key, version, payload
                      v
               Durable Write Log
                      |
                      | acknowledged according to durability policy
                      +-------> API returns ACCEPTED
                      |
                      v
                Async Flusher
                      |
                      v
                NoSQL Database
                      |
                      v
              Mark checkpoint / status
```

Cache có thể được cập nhật cùng đường hoặc như một projection từ log:

```text
Durable Log ---> Cache View
         |
         +----> Backing Store
```

Nhưng lưu log và cập nhật cache **không tự atomic** với nhau. Nếu cache update fail sau log ACK, hệ vẫn phải replay để tái dựng cache hoặc đọc trạng thái pending từ authority/queue.

### 12.1. Chọn nơi làm source of truth ở từng mốc

- Trước flusher commit: accepted mutation có thể chỉ nằm trong durable log.
- Sau flusher commit: NoSQL backing store chứa trạng thái đã persist.
- Cache là materialized latest view, nhưng có thể mất/rebuild.
- Read path cần biết có pending mutation chưa flush hay không.

### 12.2. “Redis có AOF” chưa chứng minh write-behind an toàn

Cache persistence và replication có cấu hình/ACK riêng. AOF fsync policy, failover, queue durability, process crash và consistency giữa cache key với queue entry phải được phân tích như một hệ thống, không phải nhìn thấy AOF rồi coi là database transaction.

### 12.3. Nếu queue không durable

Phải công bố rõ loss window: ví dụ trạng thái có thể mất khi node cache crash trước flush. Đừng áp dụng cho dữ liệu tài chính hoặc các writes không được phép mất.

### 12.4. API response phải đúng nghĩa

Trả `202 Accepted` có thể phù hợp khi operation đã được lưu bền theo hợp đồng và đang chờ apply. `200 OK` với thông điệp “đã commit vào NoSQL” khi DB chưa ghi là sai về semantics.

## 13. Write-behind: thứ tự, retry và idempotency

Giả sử một key nhận:

```text
W1: P100.version=41, price=100
W2: P100.version=42, price=120
W3: P100.version=43, price=130
```

Nếu flusher xử lý W3 trước W2 do retry:

```text
DB receives version 43
DB later receives version 42
```

Một blind overwrite sẽ khiến DB quay về 120.

### 13.1. Version-aware conditional upsert

Giữ `version` trên mỗi aggregate, do authority cấp đúng thứ tự:

```text
if incoming.version > stored.version:
    apply incoming
else:
    ignore as stale/replayed
```

Điều kiện phải được thực thi nguyên tử tại DB. Nếu events là **delta** (ví dụ `+1`) chứ không phải snapshots, bỏ qua version gaps có thể mất thay đổi; cần ordering, idempotent operation IDs hoặc replay thiếu.

### 13.2. Retry của worker

- Ghi DB có thể commit nhưng response mất.
- Worker có thể retry cùng operation.
- Consumer có thể nhận message trùng.
- Một batch có thể chỉ thành công một phần.

Cần idempotency theo `operationId`/`aggregateVersion`, phân loại lỗi, backoff và checkpoint sau commit.

### 13.3. Tránh thừa nhận exactly-once end-to-end

Một broker có exactly-once mode không tự khiến DB ngoài broker ghi một lần chính xác. Phải dùng atomic guard tại sink hoặc reconciliation.

### 13.4. Poison message

Nếu một item không bao giờ hợp lệ, worker cần quarantine/dead-letter và alert. Không để một message hỏng ngăn toàn bộ queue của mọi keys nếu có cách cô lập đúng.

## 14. Write-behind và write coalescing

Một lợi ích của write-behind là **gộp nhiều cập nhật cuối cùng thành một write**.

```text
Cache P100.price:
  100 -> 110 -> 120 -> 125

Flusher writes DB:
  price=125
```

Nếu business chỉ cần **trạng thái cuối cùng** của một preference, việc bỏ qua intermediate values có thể hợp lệ.

### 14.1. Không coalesce những event có ý nghĩa riêng

Các lệnh:

```text
DEBIT 10
DEBIT 20
CREDIT 5
```

không thể được gộp tùy tiện thành “balance=75” rồi bỏ audit nếu ứng dụng là ledger. Mỗi operation có identity và nghĩa vụ kế toán riêng.

### 14.2. Snapshot vs delta

- **Snapshot write:** có thể giữ version mới nhất nếu intermediate states không có giá trị nghiệp vụ.
- **Delta operation:** cần áp dụng đúng số lần/đúng thứ tự hoặc hỗ trợ CRDT/atomic counter.
- **Side effect:** không được xóa mất một email, payment hay shipment instruction đã được cam kết.

### 14.3. Backpressure

Nếu producer tạo 10.000 writes/s nhưng flusher chỉ persist được 5.000 writes/s, backlog tăng không giới hạn:

\[
\text{backlog growth}=10\,000-5\,000=5\,000\ \text{operations/s}
\]

Sau 10 phút, theo mô hình đơn giản backlog tăng khoảng 3 triệu operations. Cần queue capacity, admission control, batching, rate limiting và alert khi độ trễ tăng.

## 15. Write-around: chiến lược liên quan cần biết

Dù đề bài chính có bốn chiến lược, **write-around** thường được nhắc trong cùng bảng so sánh.

Write-around:

```text
WRITE -> NoSQL DB
         (không đưa dữ liệu mới vào cache)

READ  -> Cache
           miss -> DB -> cache
```

Nó giống một biến thể write path của cache-aside:

- Đỡ ô nhiễm cache do nhiều writes chưa từng được đọc.
- Read đầu tiên sau write có thể miss.
- Phải **invalidate entry cũ** nếu key đã có cache, nếu không read sẽ trả dữ liệu cũ.

Vì vậy câu “write-around không đụng cache” chỉ an toàn cho key chưa từng cached hoặc có invalidation/version protocol khác. Khi update một key đã cached, bỏ qua invalidation gây stale.

## 16. Bảng so sánh bốn chiến lược

| Tiêu chí | Cache-aside | Read-through | Write-through | Write-behind |
|---|---|---|---|---|
| Đường được định nghĩa chính | Đọc (và invalidation do app) | Đọc | Ghi | Ghi |
| Ai xử lý read miss? | Application | Cache/loader abstraction | Tùy cách kết hợp | Tùy cách kết hợp |
| Ai gọi backing store khi ghi? | Application | Không do read-through tự quy định | Cache writer đồng bộ | Worker/flusher bất đồng bộ |
| Cache có data ngay sau write? | Thường không nếu invalidate | Không có quy tắc mặc định | Thường có, nếu thành công | Thường có ở tầng nhận write |
| DB có data khi ACK? | Có nếu write DB đã commit theo contract | Phụ thuộc write path đi kèm | Theo write-through contract, thường có | Chưa chắc |
| Write latency | Thường theo DB + invalidate | Phụ thuộc write path khác | Chờ DB + cache work | Có thể thấp nếu chỉ chờ buffer/queue |
| Stale read risk | Invalidation/race/TTL | Loader/TTL/invalidation | Partial failure/order/replica lag | Pending writes/read routing/flush lag |
| Rủi ro mất accepted write khi cache crash | Thường thấp nếu DB đã commit | Không do read-through quyết định | Tùy backing-store commit | Cao nếu write buffer không durable |
| Cache pollution do write-only data | Thường thấp | Thường thấp | Có thể cao | Có thể cao |
| Phức tạp vận hành | Vừa | Vừa, tùy provider | Vừa–cao | Cao |
| Use case điển hình | Catalog/profile reads | Cache provider có loader | Đọc lại ngay sau ghi, write sync | High write rate, async persistence chấp nhận được |

**Không thể so sánh độ bền hoặc consistency mà không biết read/write path đi kèm và ACK contract thực tế.** Một hệ có thể dùng **read-through + write-through**, hoặc **read-through + write-behind**.

## 17. Tính nhất quán: đọc mới nhất là yêu cầu khác với tăng cache hit

Các mức yêu cầu thường gặp:

### 17.1. Eventual/bounded staleness

Cache có thể giữ giá trị cũ trong một khoảng theo TTL/invalidation lag. Phù hợp catalog, feature flags không nhạy cảm, một số dashboards.

### 17.2. Read-your-writes

Sau khi cùng một client cập nhật profile, lần đọc tiếp theo của client phải thấy thay đổi của chính mình.

Có thể dùng:

- Trả object mới trực tiếp từ write response.
- Route read tạm thời đến authoritative DB.
- Gắn session version để chỉ nhận cached version đủ mới.
- Cập nhật cache với version guard theo protocol.
- Đợi projection/invalidation watermark (nếu SLO cho phép).

Không tự suy write-through hoặc cache-aside luôn bảo đảm read-your-writes trên mọi region.

### 17.3. Monotonic reads

Nếu client đã thấy version 42, lần sau không nên nhận version 41 trong cùng session. Có thể sử dụng session token/minimum version và fallback khi cache cũ.

### 17.4. Linearizable decision

Khi cần kiểm tra inventory còn đúng một sản phẩm hoặc quyền đã bị thu hồi, quyết định phải được bảo vệ tại authority/conditional write hoặc bằng giao thức mạnh tương ứng. Cache-aside với TTL 1 giây **không tự tạo linearizability**.

### 17.5. Strict freshness vs fast fallback

Có tính năng có thể trả stale-if-error, có tính năng phải fail closed. Đây là quyết định theo business invariant, không phải chỉ bật `cacheFallbackEnabled=true` cho mọi endpoint.

## 18. TTL: một lớp giới hạn thời gian, không phải cơ chế đồng bộ hoàn chỉnh

**Time to Live (TTL)** xác định thời hạn tồn tại của một cache entry theo semantics cache.

```text
SET product:P100 value ttl=300 seconds
```

Nếu write không invalidation, trong mô hình đơn giản một entry có thể stale tới lúc hết TTL. Nhưng cần tính thêm:

- TTL có reset khi refresh/overwrite không?
- Cache có stale-while-revalidate không?
- Replica/CDN tier khác có TTL riêng không?
- Clock và expiration semantics;
- Cache fill race có tạo entry stale sau invalidation không?
- Dữ liệu mới có bị lặp lại từ projection cũ không?

**TTL=60 giây không phải lời hứa chắc chắn “dữ liệu stale tối đa 60 giây”** trong mọi pipeline. Một entry được tái nạp từ source stale hoặc tầng cache khác có thể kéo dài sai lệch.

### 18.1. TTL quá dài

Giảm miss nhưng tăng thời gian dữ liệu cũ/khó rollout sửa lỗi.

### 18.2. TTL quá ngắn

Giảm stale window nhưng tăng DB load, stampede và pressure lên kết nối.

### 18.3. TTL jitter

Nếu một triệu keys cùng hết hạn sau đúng 5 phút, nhiều misses có thể xuất hiện đồng thời.

```text
baseTTL = 300s
jitter  = random 0..60s
effectiveTTL = 300..360s
```

Jitter giúp phân tán expiration. Không dùng một random TTL để thay consistency policy.

### 18.4. Expiration và eviction

Entry có thể biến mất trước TTL do memory pressure/eviction. Read path phải coi cache miss là bình thường và không gây lỗi nghiệp vụ nếu DB vẫn có dữ liệu.

## 19. Invalidation theo key, list query và derived projections

Cache một item theo ID tương đối rõ:

```text
product:P100 -> Product P100
```

Nhưng một sản phẩm có thể xuất hiện trong nhiều cached queries:

```text
product:P100
category:books:page:1
search:java:page:2
home:recommendations:VN
seller:S10:products
```

Update Product P100 phải xét những keys/collections nào phụ thuộc nội dung mới.

### 19.1. Cache invalidation khó vì dependency graph

Không phải mọi query cache đều có thể xác định danh sách keys phụ thuộc một item, nhất là full-text search/recommendations.

### 19.2. Các hướng xử lý

- Invalidate object key và cho list cache TTL ngắn hơn.
- Tag-based invalidation nếu cache hỗ trợ.
- Generation/namespace key, ví dụ `category:books:v12:page1`.
- Query cache theo snapshot/version watermark.
- CDC/outbox cập nhật các projections.
- Tránh cache một số query biến đổi quá thường xuyên.

### 19.3. Versioned namespace

Thay vì xóa hàng nghìn keys:

```text
Old: category:books:g17:page1
New: category:books:g18:page1
```

Readers dùng generation 18; keys generation 17 tự hết hạn. Nhưng generation phải được cấp/cập nhật atomically theo scope phù hợp và có plan dọn old keys.

### 19.4. Security/permissions không nên dựa vào list cache cũ

Một danh sách cached cho user A không thể dùng lại cho user B nếu có ACL/tenant-specific data mà cache key không chứa đúng scope quyền.

## 20. Cache stampede (thundering herd)

Khi một hot key hết hạn, hàng trăm requests cùng miss và đồng loạt đọc DB:

```text
            1000 requests
                  |
                  v
          Cache P100 expired
             /  / | \  \
            v  v  v  v  v
         Many database reads
```

Một hot key làm DB quá tải dù tổng cache hit rate trước đó rất cao.

### 20.1. Single-flight/coalescing

Một leader trong phạm vi phù hợp tải dữ liệu, các requests khác chờ cùng result:

```text
Cache MISS
   |
   +--> loader 1 -> DB -> fill cache
   |
   +--> waiters -> reuse loaded result
```

In-process single-flight chỉ coalesce trong một JVM. Multi-instance system có thể cần distributed coordination nếu mọi instances cùng gây tải lớn.

### 20.2. Lock cần timeout

Một loader chết khi giữ lock có thể khiến requests chờ vô hạn nếu không có TTL/deadline. Stale lock owner cũng có thể ghi giá trị cũ, nên cần generation/version guard cho fill quan trọng.

### 20.3. Stale-while-revalidate

Cho một reader trả dữ liệu hơi cũ trong lúc một worker refresh. Phù hợp read endpoint chấp nhận stale, không phù hợp quyết định tài chính/quyền hạn cần current state.

### 20.4. Refresh-ahead

Refresh key trước khi TTL hết, dựa trên popularity/freshness policy. Tốn tài nguyên background ngay cả khi key không còn được truy cập.

### 20.5. Negative caching

Cache một kết quả “không tồn tại” trong thời gian ngắn để tránh DB query liên tục với keys không tồn tại. Nhưng cần tránh giữ “not found” quá lâu sau khi entity vừa được tạo.

## 21. Negative caching: tránh cache miss không giới hạn

Ví dụ bot liên tục gọi product IDs không tồn tại:

```text
GET /products/random-id
  -> cache MISS
  -> DB NOT_FOUND
  -> lặp lại hàng trăm nghìn lần
```

Nếu chỉ cache kết quả dương, mọi request đều vào DB.

Có thể lưu một sentinel:

```text
cache product:unknown-id = __NOT_FOUND__  TTL=10s
```

### 21.1. Rủi ro

- Product có thể vừa được tạo sau khi negative result được cache.
- Negative cache key không được bỏ qua tenant/ACL scope.
- Đừng biến temporary DB timeout thành “not found”.
- Không cache security denial như một trạng thái vĩnh viễn nếu quyền có thể đổi.
- TTL negative thường ngắn hơn TTL positive, tùy workload.

### 21.2. Phân biệt không tồn tại với lỗi

```text
DB returns 404/not found -> negative cache candidate
DB returns timeout/5xx -> failure path, không đánh dấu absent
```

Caching một transient failure thành not-found có thể biến sự cố tạm thời thành lỗi dữ liệu hiển thị dai dẳng.

## 22. Multi-tier caches: local L1 và Redis L2

Ứng dụng Java có thể dùng:

```text
Application Instance A       Application Instance B
      |                            |
   L1 Caffeine                  L1 Caffeine
      |                            |
      +-----------+----------------+
                  |
               L2 Redis
                  |
                NoSQL
```

### 22.1. Lợi ích

- L1 giảm network RTT đến Redis.
- L2 chia sẻ cached data giữa nhiều application instances.
- DB chỉ bị truy cập khi cả L1/L2 đều miss.

### 22.2. Invalidation phức tạp hơn

Xóa Redis không tự xóa L1 tại mọi JVM. Các instances cần:

- Local TTL ngắn;
- Pub/sub invalidation hoặc event stream có recovery;
- Version checks;
- Generation keys;
- Fallback đến authoritative source khi có session minVersion.

### 22.3. Pub/sub không là durable event log

Một instance offline có thể bỏ lỡ invalidation pub/sub. Đừng coi phát một message Pub/Sub như proof mọi L1 caches đã xóa key.

### 22.4. Cascading stale

Một L1 cache cũ có thể tiếp tục trả bản stale ngay cả sau khi L2 Redis được cập nhật. Đo freshness theo **end-to-end read path**, không chỉ Redis state.

## 23. Redis cache key và serialization trong Java

Một key design dễ đọc:

```text
prod:product:tenant=T42:id=P100:v1
```

Cần quan tâm:

- Environment: dev/staging/prod không dùng chung namespace vô ý.
- Tenant/user/role scope nếu dữ liệu có quyền truy cập.
- Schema version để thay đổi format JSON.
- Độ dài key và memory usage.
- Dữ liệu có PII/secrets hay không.
- Hash slot khi thực hiện multi-key Redis Cluster scripts.
- TTL theo loại dữ liệu.

### 23.1. Cache payload với metadata

```json
{
  "schemaVersion": 1,
  "sourceVersion": 42,
  "cachedAt": "2026-11-14T10:00:00Z",
  "value": {
    "id": "P100",
    "name": "Java Handbook",
    "priceMinor": 120000
  }
}
```

`cachedAt` giúp observability, nhưng version từ nguồn là cơ sở tốt hơn để tránh ghi đè bằng một mutation cũ.

### 23.2. Không dùng Java native serialization tùy tiện

Java binary serialization có rủi ro tương thích và an ninh nếu deserialize dữ liệu không đáng tin. Với Redis chung nhiều services, JSON/MessagePack/Protobuf và schema version rõ ràng thường dễ quản lý hơn, theo nhu cầu.

### 23.3. Giá tiền

Không dùng `double` để thể hiện giá bán chính xác. Lưu `long priceMinor` hoặc decimal type phù hợp currency, và bảo đảm mapper không đổi precision.

### 23.4. Cache key injection và cardinality

Nếu user input trở thành key hoặc prefix không giới hạn, attacker có thể tạo hàng triệu keys riêng gây memory pressure. Cần validation, quota và TTL.

## 24. Java Spring Boot: cache-aside với StringRedisTemplate

Một ví dụ tương đối đầy đủ. `ProductStore` là adapter tới NoSQL authoritative; có thể triển khai bằng MongoDB, DynamoDB hoặc engine khác. Ví dụ dùng Redis để cache JSON.

```java
import java.util.Optional;

public interface ProductStore {
    Optional<Product> findById(String id);
}

public record Product(
        String id,
        String name,
        long priceMinor,
        long sourceVersion
) {}
```

Service:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public final class ProductCacheAsideService {

    private static final Duration TTL = Duration.ofMinutes(5);

    private final ProductStore source;
    private final StringRedisTemplate redis;
    private final ObjectMapper json;

    public ProductCacheAsideService(
            ProductStore source,
            StringRedisTemplate redis,
            ObjectMapper json
    ) {
        this.source = source;
        this.redis = redis;
        this.json = json;
    }

    public Optional<Product> findById(String productId) {
        String key = "product:v1:" + productId;

        String cached = redis.opsForValue().get(key);
        if (cached != null) {
            try {
                return Optional.of(
                        json.readValue(cached, Product.class)
                );
            } catch (JsonProcessingException malformed) {
                // Một payload cache hỏng không là nguồn sự thật.
                redis.delete(key);
            }
        }

        Optional<Product> fromDb = source.findById(productId);

        fromDb.ifPresent(product -> {
            try {
                redis.opsForValue().set(
                        key,
                        json.writeValueAsString(product),
                        TTL
                );
            } catch (JsonProcessingException serializationError) {
                throw new IllegalStateException(
                        "Cannot encode product", serializationError
                );
            }
        });

        return fromDb;
    }
}
```

### 24.1. Đường đọc của code

1. Gọi Redis.
2. Nếu có JSON hợp lệ, trả cached product.
3. Nếu miss/malformed, gọi database qua `ProductStore`.
4. Nếu tìm thấy, serialize JSON và set TTL.
5. Trả kết quả.

### 24.2. Giới hạn cần nói rõ

- Ví dụ **chưa** xử lý Redis unavailable fallback; `RedisConnectionFailureException` có thể làm read fail. Nếu sản phẩm muốn fail-open, cần policy có giới hạn.
- Chưa có negative caching.
- Chưa có single-flight hay anti-stampede.
- Chưa có race-safe versioned fill.
- `productId` cần validate/key encode để tránh key collisions/cardinality abuse.
- `ProductStore` có thể đọc từ một replica stale; version guard phải dựa vào authoritative semantics.
- JSON mapping cần cấu hình phù hợp version/Jackson hỗ trợ records.
- Đã có một GET từ cache nhưng `fromDb` được trả dù Redis SET lỗi hay không tùy error handling trong block; quyết định đó phải rõ theo SLO.

**Đoạn mã minh họa cache-aside, không chứng minh đã đạt strong consistency.**

## 25. Java: đường ghi DB-first và invalidation

Một interface ghi source:

```java
public interface ProductCommandStore {
    Product changePrice(
            String productId,
            long newPriceMinor,
            long expectedVersion
    );
}
```

Service minh họa:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

public final class ProductCommandService {
    private final ProductCommandStore source;
    private final StringRedisTemplate redis;

    public ProductCommandService(
            ProductCommandStore source,
            StringRedisTemplate redis
    ) {
        this.source = source;
        this.redis = redis;
    }

    public Product changePrice(
            String productId,
            long newPriceMinor,
            long expectedVersion
    ) {
        // Contract: source.changePrice trả về sau khi
        // NoSQL authoritative write đã commit.
        Product updated = source.changePrice(
                productId, newPriceMinor, expectedVersion
        );

        // Nếu DELETE cache fail: DB vẫn đã commit.
        redis.delete("product:v1:" + productId);
        return updated;
    }
}
```

### 25.1. `expectedVersion` cần được kiểm tra ở DB

`ProductCommandStore` phải dùng một atomic conditional update/CAS. Nếu chỉ đọc trước rồi `save` vô điều kiện, version parameter không giúp gì.

### 25.2. Điểm lỗi quan trọng

DB commit thành công nhưng Redis DELETE lỗi. Client có thể nhận exception sau khi DB đã ghi; retry cần operation identity/version để tránh ghi lặp.

### 25.3. `@Transactional` cần chú ý thời điểm commit

Nếu method Spring `@Transactional` bao quanh cả `changePrice` và `redis.delete`, DB transaction có thể chưa commit khi Redis bị xóa (tùy transaction manager và flow). Một cách là invalidation **sau commit**, nhưng callback sau commit vẫn có thể bị mất nếu process crash.

### 25.4. Chọn outbox khi cần reliable invalidation

Trong DB transaction:

```text
UPDATE Product price/version
INSERT Outbox(ProductChanged, productId, version)
COMMIT
```

Relay/consumer đọc event và invalidate/version-update cache. Vì invalidation event có thể đến sau, read path vẫn có một khoảng stale; source authority phù hợp cho quyết định cần đọc tức thì.

## 26. Spring Cache annotations: dùng đúng hợp đồng

Một ví dụ:

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;

public class ProductService {

    @Cacheable(cacheNames = "products", key = "#id")
    public Product get(String id) {
        return loadFromNoSql(id);
    }

    @CacheEvict(cacheNames = "products", key = "#id")
    public void invalidate(String id) {
        // Chỉ là nơi kích hoạt cache eviction.
    }

    private Product loadFromNoSql(String id) {
        throw new UnsupportedOperationException(
                "Implement authoritative read"
        );
    }
}
```

Với code thực tế, `loadFromNoSql` phải được thay bằng repository/driver; Spring Cache phải được bật, `CacheManager` và serializer/TTL được cấu hình.

### 26.1. `@CachePut`

`@CachePut` thường khiến method được thực thi và kết quả đưa vào cache, theo annotation semantics. Nó **không tự tạo một transaction đồng bộ giữa Redis và NoSQL**.

### 26.2. `@CacheEvict` và transaction boundary

Cần xem annotation được áp dụng trước hay sau method invocation và quan hệ với DB transaction. Nếu muốn invalidation sau commit, dùng tích hợp transaction-aware/after-commit phù hợp, hoặc outbox/CDC cho tính bền vững khi crash.

### 26.3. AOP proxy

Một method được gọi từ chính object đó có thể bỏ qua Spring proxy và không kích hoạt `@Cacheable` trong cấu hình proxy thường gặp.

### 26.4. Cache key

Đừng dùng `#id` cho một cache chứa nhiều tenant nếu `id` chỉ duy nhất trong từng tenant. Cache key phải có đúng scope dữ liệu.

## 27. Java: read-through loader abstraction

Read-through đúng nghĩa cần một loader được cache layer đăng ký.

Một interface minh họa:

```java
import java.util.Optional;

public interface LoadingCache<K, V> {

    // Cache layer tự gọi loader khi miss.
    Optional<V> get(K key);

    interface Loader<K, V> {
        Optional<V> load(K key);
    }
}
```

Cấu hình khái niệm:

```java
LoadingCache.Loader<String, Product> loader =
        productId -> productStore.findById(productId);

// API tạo loading cache phụ thuộc cache provider.
// Không có cú pháp create() phổ quát cho mọi cache.
LoadingCache<String, Product> products =
        configureCacheWithLoader(loader);
```

Dòng `configureCacheWithLoader` ở trên là **giả mã**, không phải một hàm Java đã định nghĩa trong JDK.

### 27.1. Ví dụ library cụ thể: Caffeine LoadingCache

Caffeine cung cấp local in-memory `LoadingCache` trong JVM:

```java
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.LoadingCache;
import java.time.Duration;

LoadingCache<String, Product> cache =
        Caffeine.newBuilder()
                .maximumSize(100_000)
                .expireAfterWrite(Duration.ofMinutes(5))
                .build(productId ->
                        productStore.findById(productId)
                                .orElse(null));

Product product = cache.get("P100");
```

Caffeine có semantics riêng với null/missing values; ví dụ chỉ minh họa loader. Dùng negative cache/optional cần chọn representation phù hợp; không mặc định mọi implementation lưu `null` như một positive entry.

### 27.2. Local read-through không có distributed coherence

Mỗi JVM có cache riêng. Nếu instance B cập nhật DB, cache instance A không tự biết. Cần TTL, broadcast invalidation có recovery hoặc version checking theo yêu cầu.

### 27.3. Read-through ở distributed cache provider

Một số providers có CacheLoader/CacheWriter tích hợp hoặc extensions. Cần kiểm tra loader chạy ở client hay server, security, remote latency, retry và cluster failover.

## 28. Java: write-through qua cache writer

Một abstraction khái niệm:

```java
public interface SynchronousWriteThroughCache<K, V> {

    // Contract của abstraction:
    // Chỉ trả success khi backing store write được xác nhận.
    void put(K key, V value);

    V get(K key);
}
```

Một cache writer:

```java
public interface BackingStoreWriter<K, V> {
    void persist(K key, V value);
}
```

Luồng:

```text
cache.put(P100, value)
  |
  +-- writer.persist(P100, value) [synchronous]
  |
  +-- cache update/invalidate according to policy
  |
  +-- return or propagate failure
```

**Đây là pseudocode architecture**, không phải bảo đảm về atomic commit giữa Redis và MongoDB. Phải xác định:

- Nếu DB commit rồi cache set fail, `put` trả gì?
- Nếu source version 42 đã commit, một cache update từ version 41 tới muộn bị chặn bằng gì?
- Nếu người dùng retry, operation có idempotent không?
- Nếu cache unavailable, hệ có cho phép ghi trực tiếp DB không?
- Nếu cache evict value ngay sau `put`, read miss xử lý thế nào?

Một provider có thể cung cấp hợp đồng cụ thể mạnh hơn hoặc yếu hơn ví dụ; luôn đọc tài liệu sản phẩm.

## 29. Java: write-behind worker cần một hợp đồng bền vững

Thiết kế minh họa:

```java
public record UpdatePriceCommand(
        String operationId,
        String productId,
        long newPriceMinor,
        long aggregateVersion
) {}

public interface DurableCommandLog {
    void appendAndConfirm(UpdatePriceCommand command);
}

public interface ProductWriter {
    // Atomic conditional write + idempotency ở NoSQL.
    void applyIfNewer(UpdatePriceCommand command);
}
```

Producer:

```java
public final class PriceWriteBehindApi {
    private final DurableCommandLog log;

    public PriceWriteBehindApi(DurableCommandLog log) {
        this.log = log;
    }

    public String accept(UpdatePriceCommand command) {
        log.appendAndConfirm(command);
        // "ACCEPTED": command durable trong log,
        // chưa hứa NoSQL backing store đã persist.
        return "ACCEPTED";
    }
}
```

Consumer:

```java
public final class PriceFlusher {
    private final ProductWriter writer;

    public PriceFlusher(ProductWriter writer) {
        this.writer = writer;
    }

    public void handle(UpdatePriceCommand command) {
        // Must be idempotent / version-aware at sink.
        writer.applyIfNewer(command);

        // Broker checkpoint/ACK chỉ sau khi DB xác nhận
        // theo contract. Nếu ACK mất, retry vẫn an toàn.
    }
}
```

### 29.1. Còn thiếu cache view

API có thể cập nhật Redis cache view từ durable log hoặc từ command vừa accepted. Nhưng cache view có thể trễ; nếu cần read-your-writes ngay, phải thiết kế read-your-pending-writes, session token hoặc overlay từ authoritative pending log.

### 29.2. Không coi code là hệ write-behind production hoàn chỉnh

Chưa có broker implementation, retry/backpressure, dead-letter handling, transaction metadata, payload validation, permission/authentication, failure recovery hoặc cache coherence.

### 29.3. Version guard không đủ cho delta events

Nếu command là `INCREMENT 1`, bỏ qua một version cũ sau khi version mới đã tới có thể mất một increment. Cần applied operation ID/sequence hoặc ordered stream per key.

### 29.4. API nên trả operation status

Một read endpoint:

```text
GET /operations/{operationId}
```

có thể trả:

```json
{
  "operationId": "op-100",
  "status": "ACCEPTED",
  "sourcePersisted": false
}
```

Sau flusher:

```json
{
  "operationId": "op-100",
  "status": "PERSISTED",
  "sourcePersisted": true
}
```

Không công bố “đã cập nhật NoSQL” khi dữ liệu mới chỉ được accepted vào queue.

## 30. Redis transactions, Lua và giới hạn atomicity

Redis có thể hỗ trợ các thao tác nguyên tử trên một server/đường script thích hợp, nhưng điều này **không tự là transaction xuyên Redis và một NoSQL khác**.

### 30.1. MULTI/EXEC

Một transaction Redis điều phối các commands trong Redis theo semantics riêng, không bao gồm MongoDB transaction hoặc payment provider.

### 30.2. Lua/script

Một script có thể atomically kiểm tra version và cập nhật cache hash theo key trên một Redis node khi điều kiện được hỗ trợ.

Giả mã:

```text
cacheUpdateIfNewer(key, incomingVersion, incomingPayload):
    current = HGET key version
    if incomingVersion > current:
        HSET key version=incomingVersion,
                 payload=incomingPayload
        EXPIRE key ttl
        return UPDATED
    else:
        return IGNORED_STALE
```

Trong Redis Cluster, một script đa key cần tuân thủ hash slot restrictions. Nếu key bị evict và mất version, một old event có thể tạo key trở lại; cần retention/source checks theo yêu cầu.

### 30.3. Atomic cache update không tạo DB commit

Ngay cả khi version guard script an toàn trong Redis, DB authoritative vẫn có thể fail. Cần làm rõ write-through/write-behind và recovery ở biên Redis–NoSQL.

### 30.4. Cache locks không thay source transaction

Một distributed lock từ Redis không tự bảo vệ inventory update nếu lease hết mà worker cũ vẫn ghi. Dùng fencing/version guard tại source.

## 31. Cache-aside cho hồ sơ: read-your-writes và OCC

User U42 cập nhật địa chỉ:

```text
GET /profiles/U42
  -> cache hit version 7

PATCH /profiles/U42
  If-Match version 7
  -> source commits version 8
  -> cache invalidate pending

GET /profiles/U42
  -> cache may still be version 7
```

Để giữ UX:

- Trả profile version 8 từ PATCH response.
- Client yêu cầu minimum version 8 cho GET kế tiếp.
- Nếu cache trả v7, bypass cache và đọc authoritative source.
- Relay invalidation giúp các users khác nhanh chóng thấy v8.
- TTL làm giới hạn phụ trợ khi invalidation bị chậm.

**Version check phải so trong cùng entity/aggregate**, không so version Order với version Profile.

### 31.1. Concurrent updates

Hai clients sửa profile từ version 7; nếu không muốn lost update, source dùng CAS/optimistic concurrency control. Cache invalidation không tự ngăn cả hai ghi stale version.

### 31.2. Áp dụng write-through có luôn read-your-writes?

Không nếu read từ một L1 cache cũ hoặc region replica chưa đồng bộ. Cần end-to-end path bảo đảm version minimum.

### 31.3. Không đọc cache để quyết định quyền

Một cached profile không nên là nguồn xác nhận quyền admin khi revocation cần hiệu lực tức thì. Có thể hiển thị tên/ảnh từ cache nhưng kiểm tra ACL tại authority.

## 32. Cache cho catalog và giá sản phẩm

Catalog đọc nhiều, cập nhật ít là ví dụ phù hợp với cache-aside hoặc read-through.

```text
Read QPS  = 1000
Cache hit = 90%
Source reads ~100/s trong mô hình đơn giản
```

Giá sản phẩm có thể thay đổi và cần người dùng thấy giá đúng tại checkout.

### 32.1. Product detail

Cache detail có thể chứa giá hiển thị, tên và mô tả với TTL/invalidation.

### 32.2. Checkout

Ngay trước khi tính tổng tiền/đặt hàng, backend phải áp dụng chính sách giá authoritative và version phù hợp, thay vì tin giá client/cache stale.

### 32.3. Price promotion

Một promotion có `effectiveFrom`/`effectiveTo`; TTL ngẫu nhiên không tự đảm bảo thời điểm bắt đầu/kết thúc chính xác. Có thể dùng scheduled invalidation và source verification tại purchase.

### 32.4. Query caches

Danh sách “sản phẩm giảm giá” có thể có hàng nghìn query keys; invalidate từng object P100 không xóa hết list cache. Cần projection freshness strategy.

## 33. Inventory và đặt vé: đừng dùng cache làm nguồn quyết định

Giả sử còn đúng một sản phẩm:

```text
Cache inventory P100.available = 1
Client A reads cache => 1
Client B reads cache => 1
```

Nếu cả hai clients tự giảm cache rồi ACK, có thể oversell; nếu sau đó LWW/repair giữ một giá trị cuối cùng, hai xác nhận đã xảy ra.

### 33.1. Đường phù hợp

```text
Client -> Inventory Authority
             |
             | atomic condition available >= quantity
             v
         NoSQL source
             |
             | reservation outcome committed
             v
         Outbox/Cache invalidation
```

### 33.2. Cache có ích gì?

- Hiển thị “còn hàng” ước lượng trên trang catalog.
- Giảm tải các lượt đọc không quyết định.
- Dùng read model có watermark cho browsing.

### 33.3. Cache không làm gì?

Không thay thế conditional reservation tại source nếu business invariant cần không oversell.

### 33.4. “Còn hàng” và “đặt thành công” khác nhau

Frontend có thể hiển thị còn hàng theo cache, nhưng API reserve phải trả `RESERVED` chỉ sau authority commit. Nếu hết hàng, trả conflict/hết hàng dù UI vừa hiển thị số dương.

## 34. Dữ liệu tài chính, permissions và session state

### 34.1. Balance/ledger

Đừng write-behind một số dư đã được công bố như committed chỉ vào cache volatile. Ledger entries phải được persist theo financial durability/integrity contract.

### 34.2. Security permissions

Một cached `isAdmin=true` có thể không còn hợp lệ sau revocation. Đối với hành động nhạy cảm, dùng authoritative check, revocation epoch hoặc token version/fail-closed policy.

### 34.3. Session/token cache

Redis thường dùng cho sessions hoặc token metadata với TTL. Nhưng TTL expiration, replication và failover phải phù hợp yêu cầu security. Nếu logout/revoke cần tức thì, cần thiết kế revocation path và stale-session rejection.

### 34.4. Rate limiter

Một Redis atomic increment có thể phù hợp để đếm request trong một window, nhưng failover/eviction có thể reset count. Với quota tài chính cứng hoặc billing, cần nguồn authority và reconciliation riêng.

### 34.5. Counters/metrics

Write-behind/coalescing có thể chấp nhận với telemetry approximation, nhưng phải nêu rõ độ chính xác, mất mát cho phép và cách tránh duplicate increments.

## 35. Multi-region caches và consistency

Một ứng dụng có Redis caches ở nhiều regions:

```text
             Global Product Source
                /             \
               v               v
          Region East       Region West
           Redis E           Redis W
              |                 |
             API E             API W
```

Một update ở East commit nguồn, còn West cache key chưa invalidated. Người dùng di chuyển regions có thể thấy giá cũ.

### 35.1. CDC/outbox multi-region

Một event có thể được gửi đến mỗi cache region với `aggregateVersion`. Consumers phải idempotent, xử lý out-of-order và giữ tombstone/version khi cần.

### 35.2. Chênh lệch clock

Nếu dùng wall-clock timestamps trên nhiều regions để chọn giá trị cache “mới hơn”, clock skew có thể khiến old update thắng. Source version/commit token theo phạm vi hợp lệ tốt hơn.

### 35.3. Eviction không phải đồng bộ

Một region tự evict key không khiến region khác thấy version mới.

### 35.4. Mất mạng liên vùng

Nếu cache E vẫn cho stale public product views khi source unavailable, API phải biết đó là degraded mode. Không thể dùng stale permission hoặc inventory count để xác nhận business operations.

### 35.5. Session minVersion

Có thể gắn `minSourceVersion` trong client session và reject cache payload có version thấp hơn; fallback phải biết authoritative source hoặc đường đủ mới, không vô tình bypass sang một stale replica khác.

## 36. Cache warming và cold start

Khi triển khai Redis mới hoặc cache cluster vừa mất dữ liệu, hit ratio có thể giảm mạnh.

### 36.1. Cold miss surge

```text
Before restart: hit rate 95%
After restart:  hit rate 0%
Source QPS: tăng đột ngột
```

Nếu source không chịu được 100% read traffic, cache outage có thể kéo theo DB outage.

### 36.2. Những cách warm cache

- Preload nhóm hot keys đã đo được.
- Lazy warm với single-flight.
- Gradual traffic shift/canary.
- Rate-limit read fills.
- Serve stale fallback chỉ nơi cho phép.
- Increase source capacity tạm thời.
- Prefetch theo pattern, có giới hạn.

### 36.3. Không preload toàn bộ database vô điều kiện

Nếu dataset hàng TB nhưng working set chỉ vài GB, warm toàn bộ làm tốn memory và đẩy hot keys khỏi cache.

### 36.4. Cache warming cần permission scope

Không preload dữ liệu riêng tư vào shared keys thiếu tenant/user context.

## 37. Sự cố cache unavailable: fail-open hay fail-closed?

### 37.1. Fail-open

Nếu Redis down, đọc trực tiếp NoSQL DB. Phù hợp các read-only/catalog paths nếu source có capacity và deadline:

```text
Cache timeout -> guarded fallback to DB
```

Rủi ro: tất cả clients đồng loạt fallback có thể tạo avalanche lên database. Cần circuit breaker, concurrency budget và rate limiting.

### 37.2. Fail-closed

Từ chối thao tác nếu không thể xác minh trạng thái an toàn hoặc quyền. Phù hợp khi cache/authority chứa state bắt buộc để quyết định và không có đường thay thế đủ mạnh.

### 37.3. Stale-if-error

Có thể trả dữ liệu cache đã hết freshness khi DB down:

```json
{
  "productId": "P100",
  "priceMinor": 120000,
  "dataFreshness": "STALE"
}
```

Đây là một lựa chọn sản phẩm cần quy định rõ, không áp dụng cho payment, ACL hoặc inventory reservation.

### 37.4. Write-behind cache down

Nếu write-behind dùng cache làm nơi duy nhất giữ writes đã ACK nhưng chưa flush, cache down có thể là **nguy cơ mất dữ liệu**, không chỉ giảm performance. Recovery phải dựa vào durable log và replay theo hợp đồng.

## 38. Ma trận lỗi theo chiến lược

| Sự cố | Cache-aside | Read-through | Write-through | Write-behind |
|---|---|---|---|---|
| Cache miss | App gọi DB | Cache loader gọi DB | Theo read path kết hợp | Theo read path kết hợp |
| Cache down khi đọc | App có thể fallback DB | Loader/provider có thể fail/fallback theo contract | Tùy read path | Có thể không thấy pending write |
| DB down khi đọc miss | Miss không load được, có thể stale fallback | Loader fail hoặc stale theo policy | Tùy read path | Cache có thể giữ provisional data |
| DB down khi ghi | DB-first write fail | Không do read-through quy định | Write đồng bộ fail theo contract | Queue có thể tiếp nhận, backlog tăng |
| Cache update/invalidation fail sau DB commit | Stale; cần retry/outbox/TTL | Tương tự nếu read-through đi kèm invalidate | Partial failure phải có policy | Cache view có thể lệch pending log |
| Worker/flusher down | Thường không có | Không do read-through quy định | Không cần async flusher theo định nghĩa | Backlog tăng; durability dựa vào queue |
| Cache eviction | Read miss, reload | Loader reload | Read miss có thể reload | Pending write có nguy cơ nếu chỉ lưu cache |
| Writes đến đảo thứ tự | Stale fill/invalidation race | Tùy loader policy | Cache update race | DB flush/replay race |
| API timeout sau DB commit | Unknown write outcome | Theo write path khác | Unknown/partial outcome | Accepted vs persisted cần tách |
| Miss storm | DB overload | Loader overload | Tùy read path | Tùy read path |

Ma trận là mô hình khái quát, không thay thế tài liệu của cache provider hoặc thiết kế dự án cụ thể.

## 39. Monitoring: hit rate không đủ

Một cache có hit rate 99% vẫn có thể trả dữ liệu cũ cho 1% reads business-critical. Một cache hit rate 70% có thể tối ưu tốt nếu các misses rơi vào keys ít quan trọng.

### 39.1. Chỉ số hit/miss

\[
\text{hit ratio}=
\frac{\text{cache hits}}{\text{cache hits}+\text{cache misses}}
\]

Ví dụ 9.000 hits trên 10.000 lookups → hit ratio 90%.

### 39.2. Latency

- Cache GET p50/p95/p99.
- Source DB read p50/p95/p99.
- End-to-end API read latency.
- Eviction refill latency.
- Write-through latency.
- Write-behind accepted latency và persistence delay.

### 39.3. Write-behind lag

\[
\text{flush lag}=\text{time persisted}-\text{time accepted}
\]

Cần đo p50/p95/p99, oldest pending operation age và backlog size.

### 39.4. Consistency/freshness

- Source version − cached version theo cùng key.
- Stale read rate qua sampling/validation.
- Invalidation delivery delay.
- Out-of-order/replayed events.
- Version-guard rejections.
- Negative-cache false misses.
- Clock skew nếu có timestamps.
- Source-read failovers/forced bypass.

### 39.5. Capacity

- Redis memory used và eviction count.
- Cache key cardinality.
- Hot keys/hot tenants.
- Connection pool utilization.
- Read amplification khi miss.
- DB CPU/IO during cold start.
- Queue storage/headroom và retry DLQ.

### 39.6. Business metrics

- Oversell sau cached inventory read.
- Sai giá tại checkout.
- Permission revoked nhưng được cho phép.
- Payment status mismatch.
- Session invalidation delay.
- Lost accepted writes trong write-behind.

**Mục tiêu cache là giảm chi phí mà vẫn giữ hợp đồng dữ liệu**, không phải tối đa hóa hit ratio bằng mọi giá.

## 40. Chi phí và bài toán tải đọc

Giả sử:

- Tốc độ đọc: 2.000 requests/giây.
- Hit ratio kỳ vọng: 85%.
- Mỗi miss tạo một DB read (bỏ qua duplicate load, retries và prefetch).
- Cache lookup trên mọi request.

Khi đó:

\[
\text{DB reads/s}\approx 2000\times(1-0.85)=300
\]

DB giảm từ khoảng 2.000 reads/s xuống 300 reads/s trong mô hình đơn giản.

### 40.1. Không suy latency p99 bằng trung bình có trọng số

Giả sử cache hit mất 2 ms, DB miss mất 50 ms. Mean đơn giản:

\[
E[L]\approx 0.85\times2+0.15\times50=9.2\text{ ms}
\]

Nhưng p99 sẽ bị chi phối bởi đường miss nếu miss chiếm 15%, chưa tính queueing và hot keys. Không dùng công thức mean để tuyên bố p99=9.2ms.

### 40.2. Chi phí cache cũng phải cộng

- Memory và replication của Redis/cache cluster.
- Serialization/deserialization CPU.
- Network hops và TLS.
- Cache invalidation/events/CDC.
- Cache stampede mitigation.
- Operational maintenance.
- Dung lượng durable queue cho write-behind.

### 40.3. Với write-heavy workload

Write-through có thể thêm cache writes không được đọc lại. Write-behind có thể giảm DB write volume nhờ coalescing nhưng cần queue/persistence/recovery. Chỉ đo throughput không đủ; phải đo durability và business error.

## 41. Testing: cache-aside

### Test 1 — Hit

Cache có `P100` version 5. Gọi `read(P100)`: không cần source query theo contract.

### Test 2 — Miss

Cache trống. Source trả version 5. App lưu key có TTL rồi trả dữ liệu.

### Test 3 — Source not found

Source trả absent. Nếu negative caching bật, lưu sentinel TTL ngắn; không cache transient error thành absent.

### Test 4 — Update + invalidate

Source commit version 6; cache key bị xóa; lần read sau tải version 6.

### Test 5 — Slow miss race

Reader A đọc version 5 nhưng tạm dừng trước fill; Writer B commit version 6 rồi invalidate; A tiếp tục fill. Kiểm tra version guard hoặc chính sách stale được thiết kế rõ.

### Test 6 — Cache delete failure

Source commit nhưng Redis DELETE timeout. Kiểm tra outbox/retry/TTL, API outcome và freshness SLO.

### Test 7 — Concurrent cold miss

100 clients cùng miss. Quan sát DB QPS và single-flight/lock.

### Test 8 — Cache outage

Redis down. Đường read fail-open có concurrency limit hay làm DB quá tải?

## 42. Testing: read-through và write-through

### Test 9 — Loader invoked once per miss

Trong phạm vi cache provider hứa coalescing, nhiều concurrent misses chỉ tạo số loads phù hợp hợp đồng.

### Test 10 — Loader fails

Cache miss, DB timeout. Cache có giữ error như một positive value không? Có stale-if-error không?

### Test 11 — Write-through success

Cache writer xác nhận backing-store commit trước khi API báo thành công, theo thiết kế.

### Test 12 — DB fails after provisional cache update

Không được giữ một giá trị chưa authoritative như committed.

### Test 13 — DB commit rồi cache set fail

Xác định client outcome và recovery. Không retry như một business operation mới nếu DB đã commit.

### Test 14 — Out-of-order cache updates

Source version 42 commit sau 41, nhưng cache update version 41 tới sau. Cache phải giữ version 42 nếu protocol yêu cầu monotonic view.

### Test 15 — Cache evicted after write

Read miss reload được giá trị committed; eviction không được làm mất source data.

## 43. Testing: write-behind

### Test 16 — Crash trước durable queue ACK

Nếu operation chưa được accepted bền vững, API không được nói đã persist.

### Test 17 — Crash sau durable ACK, trước DB flush

Khởi động lại worker và replay operation.

### Test 18 — DB commit, worker ACK queue lost

Operation được giao lại; sink idempotency/version guard phải ngăn double effect.

### Test 19 — Queue reordering

v43 tới DB trước v42. Sink không rollback về v42 đối với state snapshot theo protocol.

### Test 20 — Delta counter

Hai INCREMENT messages được giao trùng và đảo thứ tự; không được mất hoặc nhân đôi increment khi invariant cần đếm chính xác.

### Test 21 — DB down lâu

Backlog tăng; đo oldest age, queue capacity, backpressure, API admission decisions.

### Test 22 — Poison event

Một message schema lỗi không được giữ cả hệ bị nghẽn vô thời hạn; DLQ/quarantine và alert rõ.

### Test 23 — Cache view lost, queue intact

Khôi phục cache từ durable log/source mà không mất accepted operations.

### Test 24 — Client read after accepted write

Hợp đồng yêu cầu read-your-pending-writes hay chỉ read-after-persist? Test theo session.

### Test 25 — Coalescing

P100: v41→v42→v43; nếu chỉ giữ v43, phải chứng minh các intermediate writes không có side effects/audit bắt buộc.

## 44. Case study A: trang sản phẩm đọc nhiều, ghi ít

**Bối cảnh:** 5.000 product reads/s, vài chục product edits/phút. MongoDB là authoritative source, Redis cache dùng chung các instances Java.

### 44.1. Hướng chọn

**Cache-aside + DB-first invalidation** hoặc **read-through loader** là lựa chọn dễ bắt đầu:

```text
GET Product -> Redis hit/miss -> MongoDB
EDIT Product -> MongoDB update/CAS -> outbox invalidation
```

### 44.2. Bảo đảm đề xuất

- TTL hợp lý theo độ mới của catalog.
- Product payload chứa sourceVersion.
- Single-flight cho hot keys.
- Invalidation qua outbox/CDC.
- Cache miss fallback có rate limit.
- Checkout dùng authoritative price/version.
- Search/list caches có policy refresh riêng.

### 44.3. Không cần write-behind cho mọi product edit

Edit không nhiều; đổi sang write-behind chỉ để giảm vài mili-giây trên đường seller update có thể thêm rủi ro durability không tương xứng.

### 44.4. Hệ có thể kết hợp

Read-through tại L1 Caffeine, Redis L2 và cache-aside ở API adapter là hợp lý nếu team hiểu rõ ownership của loader/invalidation. Tránh để ba tầng tự refresh với versions khác nhau mà không có rule.

## 45. Case study B: telemetry tốc độ cao

**Bối cảnh:** ứng dụng nhận 20.000 telemetry points/s. Không phải point nào cũng cần lưu riêng; dashboard cần aggregates theo phút, và nguồn lâu dài lưu aggregated results.

### 45.1. Cân nhắc write-behind

```text
Telemetry producers
      |
      v
Durable stream/log
      |
      +--> Real-time cache view
      |
      +--> Window aggregator/flusher
                      |
                      v
               NoSQL time buckets
```

### 45.2. Hợp đồng

- Event IDs/partition ordering.
- Durable queue đủ sức chịu outage.
- Watermarks và late-event handling.
- Aggregation theo window, retries idempotent.
- Nếu coalescing bỏ raw events, phải công bố retention/loss policy.
- Dashboard có watermark/freshness lag.
- API accepted khác persisted.

### 45.3. Khi không được coalesce

Nếu telemetry là audit bắt buộc từng sự kiện hoặc billing có giá trị tài chính, phải giữ log từng event và idempotent processing thay vì chỉ ghi giá trị cuối.

### 45.4. Write-through có thể phù hợp hơn cho thiết bị cấu hình

Lệnh cập nhật cấu hình cần persist ngay trước ACK có thể dùng synchronous write path. Một hệ có thể dùng write-behind cho telemetry nhưng write-through/DB-first cho configuration.

## 46. Case study C: quản lý phiên đăng nhập và quyền

**Bối cảnh:** Redis giữ session/token metadata, NoSQL DB giữ user profile và revocation state.

### 46.1. Đọc profile

Cache-aside/read-through có thể hợp lý cho tên hiển thị/avatar.

### 46.2. Đọc quyền

Đường đọc quyền cần kiểm tra revocation epoch/authority đúng theo policy. Không cho user tiếp tục thao tác nhạy cảm chỉ vì profile cache còn `role=ADMIN`.

### 46.3. Ghi revocation

Không write-behind revoke permission rồi báo “đã khóa ngay” nếu backing-store authority chưa commit. Có thể dùng authoritative CAS/transaction, sau đó invalidate caches và chặn stale tokens bằng epoch.

### 46.4. Redis failover

Nếu security decision dựa trên Redis, cần đánh giá Redis persistence/failover và khả năng state bị rollback theo mode. Nên có authoritative policy/fail-closed path khi không thể xác minh.

## 47. Các lỗi thiết kế thường gặp

**“Có Redis rồi nên dữ liệu luôn nhanh và đúng.”** Không. Cache có thể stale, evict hoặc outage.

**“Cache-aside đồng nghĩa đọc từ DB mỗi request.”** Không; chỉ miss mới cần DB theo thiết kế.

**“Write-through là DB save rồi cache delete.”** Không; đó thường là DB-first cache invalidation, có semantics khác.

**“Read-through tức database tự đẩy updates sang Redis.”** Không; read-through nói về cache miss loader.

**“Write-behind nghĩa không cần quan tâm durability.”** Sai; càng cần durable queue và recovery nếu ACK quan trọng.

**“Ghi Redis rồi trả 200 OK nghĩa MongoDB đã commit.”** Sai trong write-behind nếu chưa flush.

**“TTL ngắn bảo đảm không bao giờ stale.”** Sai; race/fill nguồn stale vẫn có thể xảy ra.

**“Cache DELETE ngay sau DB UPDATE loại bỏ mọi race.”** Sai; slow cache fill có thể nạp giá trị cũ sau DELETE.

**“Đồng bộ sau commit nghĩa atomic hai hệ.”** Sai; process crash giữa commit và invalidation vẫn có thể xảy ra.

**“Dùng Pub/Sub là đủ để invalidation mọi L1 cache.”** Không; subscriber offline có thể bỏ lỡ message.

**“Spring `@Cacheable` khiến Redis tự gọi MongoDB loader.”** Không mặc định; method application được interceptor gọi.

**“`@CachePut` là write-through ACID.”** Không; không tự atomically commit DB và cache.

**“Write-behind worker retry mọi thứ là an toàn.”** Không; cần idempotency/version/ordering.

**“Có AOF nên accepted write chắc chắn an toàn qua mọi failover.”** Không; cần xét fsync, replicas, log–cache consistency và fault model.

**“Đọc cache inventory đủ để bán sản phẩm cuối.”** Không; cần atomic reservation tại authority.

**“Cache hit rate 99% đồng nghĩa p99 API latency tốt.”** Không; 1% misses có thể quyết định tail.

**“Cache nóng trước release thì không cần tăng DB capacity.”** Không; cold start/failover có thể làm miss spike.

**“Negative cache 404 có thể giữ mãi.”** Không; entity có thể được tạo sau.

**“Đọc key Redis có TTL là đủ cho authorization.”** Không khi quyền cần revocation tức thì.

**“Write-behind mọi thay đổi thành một snapshot cuối giúp giảm chi phí.”** Không nếu intermediate operations có audit/side effects cần giữ.

## 48. Bộ câu hỏi chọn chiến lược

Trước khi chọn cache pattern, trả lời theo thứ tự:

1. **Read/write ratio thế nào?** Đọc nhiều/ghi ít hay ghi dày đặc?
2. **Source of truth ở đâu?** NoSQL DB, cache hay durable operation log?
3. **Khi API trả success, đã persist ở đâu?** RAM, replica, queue hay authoritative DB?
4. **Có chấp nhận stale không?** Bao lâu, cho endpoint nào?
5. **Có read-your-writes không?** Session cần minVersion không?
6. **Cache mất thì sao?** Fallback DB, fail closed, hoặc mất accepted writes?
7. **Miss burst có nguy hiểm không?** Hot key, single-flight, refresh-ahead?
8. **Write order có quan trọng không?** Snapshot hay delta, version guard?
9. **Ghi có thể coalesce không?** Mất intermediate event có chấp nhận?
10. **Có ràng buộc bảo mật/tiền/quota không?** Cần authority/transaction?
11. **Invalidation đáng tin thế nào?** Outbox, CDC, TTL và recovery?
12. **Có nhiều cache tiers/regions không?** L1 coherence, multi-region lag?
13. **Có kiểm thử failover/replay chưa?** Unknown outcome, duplicate?
14. **Có metrics freshness và business correctness chưa?** Không chỉ hit ratio.

### 48.1. Cây lựa chọn gợi ý

```text
Dữ liệu có cần commit ngay vào NoSQL trước ACK?
|
+-- Có
|    |
|    +-- Đọc nhiều, write vừa/ít
|    |     -> Cache-aside hoặc read-through
|    |        + DB-first invalidation / version guard
|    |
|    +-- Cần cache được cập nhật cùng đường ghi
|          -> Write-through có explicit failure policy
|
+-- Không, được phép persist async
     |
     +-- Accepted writes được phép mất khi crash?
     |     |
     |     +-- Có, theo business contract
     |     |     -> Write-behind buffer có loss budget rõ
     |     |
     |     +-- Không
     |           -> Durable log/queue + idempotent flusher
     |              + read-your-pending-writes policy
     |
     +-- Có delta/audit quan trọng?
           -> Không coalesce mù quáng
```

Cây này là gợi ý thiết kế, không phải thuật toán quyết định thay benchmark và kiểm tra product contract.

## 49. Bài tập thực hành

### Bài tập 1 — Gọi tên mô hình

Service Java `GET Redis`, miss thì `GET MongoDB`, sau đó `SET Redis`.

**Câu hỏi:** Mô hình nào?

**Gợi ý:** Cache-aside.

### Bài tập 2 — Read-through thực sự

Cache provider đã đăng ký loader, `cache.get(P100)` tự tải MongoDB khi miss.

**Câu hỏi:** Ai chịu trách nhiệm nạp dữ liệu?

**Gợi ý:** Cache/loader layer, đây là read-through.

### Bài tập 3 — Spring annotation

`@Cacheable` đánh dấu method `ProductService.find`.

**Câu hỏi:** Redis server có tự gọi MongoDB không?

**Gợi ý:** Không mặc định; Spring interception gọi method khi miss.

### Bài tập 4 — Write-through

Client gọi `cache.put`, cache writer chờ DB commit mới trả success.

**Câu hỏi:** Khác write-behind thế nào?

**Gợi ý:** Write-through đợi backing-store write đồng bộ.

### Bài tập 5 — Write-behind

API ACK sau khi buffer nhận mutation nhưng DB chưa có.

**Câu hỏi:** Rủi ro lớn nhất nếu cache chỉ lưu RAM?

**Gợi ý:** Crash trước flush làm mất accepted write.

### Bài tập 6 — DB-first invalidation

Service ghi DB rồi xóa Redis.

**Câu hỏi:** Đó có mặc định là write-through không?

**Gợi ý:** Không; thường là cache-aside invalidation.

### Bài tập 7 — Slow read race

Reader lấy DB version 5 rồi pause. Writer commit v6, xóa cache. Reader fill v5.

**Câu hỏi:** Vì sao dữ liệu stale xuất hiện sau invalidation?

**Gợi ý:** Cache fill và source write không nguyên tử.

### Bài tập 8 — Partial failure

DB commit version 6, Redis DELETE fail.

**Câu hỏi:** Có thể rollback DB chỉ nhờ Java catch không?

**Gợi ý:** Không; cần TTL/outbox/reconciliation hoặc policy mạnh hơn.

### Bài tập 9 — TTL

Key expire sau 60 giây.

**Câu hỏi:** Có bảo đảm mọi read stale tối đa 60 giây không?

**Gợi ý:** Không nếu cache refill từ nguồn/projection cũ hoặc có các tiers khác.

### Bài tập 10 — Jitter

Một triệu keys cùng hết hạn đúng 5 phút.

**Câu hỏi:** Vì sao thêm jitter?

**Gợi ý:** Phân tán miss burst và giảm stampede.

### Bài tập 11 — Negative cache

Key K không tồn tại; cache lưu NOT_FOUND 10 giây.

**Câu hỏi:** Khi K được tạo sau 1 giây, có thể xảy ra gì?

**Gợi ý:** Còn false negative tới khi entry hết hạn hoặc bị invalidate.

### Bài tập 12 — Timeout

DB timeout nhưng cache layer ghi `NOT_FOUND`.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Transient failure khác absent state.

### Bài tập 13 — Stampede

1000 requests miss cùng hot key và cùng gọi DB.

**Câu hỏi:** Cách giảm?

**Gợi ý:** Single-flight/coalescing, jitter, refresh-ahead, bounded fallback.

### Bài tập 14 — Distributed L1

Hai Java instances có Caffeine L1 và Redis L2. Redis key bị xóa.

**Câu hỏi:** Instance có L1 cũ tự biết không?

**Gợi ý:** Không, cần TTL/invalidation/version path.

### Bài tập 15 — Write-through order

DB ghi v42 thành công, cache update v42 thất bại.

**Câu hỏi:** Hệ phải mô tả response ra sao?

**Gợi ý:** DB đã commit, không thể coi là rollback; cần failure policy.

### Bài tập 16 — Write-behind queue

Queue persist v42 nhưng cache update lỗi.

**Câu hỏi:** Có mất command không nếu durable queue thật sự giữ nó?

**Gợi ý:** Không nhất thiết; cần replay/rebuild cache view và status chính xác.

### Bài tập 17 — Out-of-order flusher

DB nhận v43 rồi v42.

**Câu hỏi:** Cần gì cho snapshot writes?

**Gợi ý:** Atomic version-guarded upsert.

### Bài tập 18 — Delta

Hai `INCREMENT +1` được thực hiện, nhưng coalesce giữ chỉ một snapshot thiếu một operation.

**Câu hỏi:** Tại sao sai?

**Gợi ý:** Delta/audit cần identity/ordering; không bỏ intermediate operations tùy tiện.

### Bài tập 19 — Flusher crash

DB commit nhưng worker crash trước queue ACK.

**Câu hỏi:** Điều gì khiến retry an toàn?

**Gợi ý:** Idempotency/operation ID tại sink.

### Bài tập 20 — Write-behind backlog

Ingress 10k/s, flusher 6k/s trong 5 phút.

**Câu hỏi:** Backlog tăng khoảng bao nhiêu?

**Gợi ý:** (10k−6k) × 300 = 1.2 triệu operations, chưa tính batching/coalescing.

### Bài tập 21 — Stale-if-error

DB catalog down, cache có giá cũ.

**Câu hỏi:** Có thể phục vụ stale không?

**Gợi ý:** Tùy SLO; gắn nhãn và không dùng giá stale làm quyết định checkout.

### Bài tập 22 — Inventory

Còn một sản phẩm. Cache báo 1 cho hai clients.

**Câu hỏi:** Ai được quyền xác nhận reserve?

**Gợi ý:** Inventory source với atomic conditional mutation.

### Bài tập 23 — Revocation

Admin đã bị thu hồi quyền nhưng cache còn `isAdmin=true`.

**Câu hỏi:** Dùng cached role cho giao dịch nhạy cảm có an toàn không?

**Gợi ý:** Không, cần authoritative revocation/epoch policy.

### Bài tập 24 — Cache key multi-tenant

Hai tenants cùng productId P100, key đều là `product:P100`.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Lẫn dữ liệu/vi phạm quyền giữa tenants.

### Bài tập 25 — Read-after-write

Client vừa cập nhật v8, cache trả v7.

**Câu hỏi:** Có thể dùng minVersion token thế nào?

**Gợi ý:** Bỏ qua cached v7 và đọc nguồn đủ mới hoặc chờ phiên bản tối thiểu.

### Bài tập 26 — Cache warming

Cache restart, hit ratio từ 95% về 0%.

**Câu hỏi:** Nguy cơ?

**Gợi ý:** Source DB bị sudden read load; cần warm/rate-limit/fallback.

### Bài tập 27 — Hit ratio

10000 requests, 8500 cache hits.

**Câu hỏi:** Hit ratio và số DB miss reads đơn giản là bao nhiêu?

**Gợi ý:** 85%, khoảng 1500 misses nếu mỗi miss gọi DB.

### Bài tập 28 — p99

Hit latency 2ms, miss 100ms, hit rate 90%.

**Câu hỏi:** Có thể kết luận p99≈11.8ms từ weighted mean không?

**Gợi ý:** Không; misses 10% chi phối tail.

### Bài tập 29 — Derived query cache

Cập nhật Product P100 nhưng danh sách cached `category:books:page1` không được invalidate.

**Câu hỏi:** Lỗi gì?

**Gợi ý:** Dependency invalidation chưa đầy đủ; TTL/generation/projection policy.

### Bài tập 30 — Thiết kế cuối

Một nền tảng gồm catalog, inventory, user profile, telemetry, payment và search.

**Yêu cầu:** Chọn giữa cache-aside/read-through/write-through/write-behind cho từng đường và nêu nơi cần authority.

**Gợi ý:** Catalog/profile reads phù hợp cache-aside/read-through; inventory/payment quyết định ở source; telemetry aggregation có thể write-behind với durable log; search là projection qua CDC/outbox; nếu dùng write-through, nêu rõ partial failure.

## 50. Checklist trước khi triển khai production

- [ ] Đã xác định source of truth và quyền ghi cho từng loại dữ liệu.
- [ ] Đã phân biệt cache-aside, read-through, write-through và write-behind ở cả đọc/ghi.
- [ ] Đã biết cache miss do application hay provider loader xử lý.
- [ ] Đã xác định khi nào write được ACK và nơi nào đã persist.
- [ ] Không gọi DB-first invalidate là provider-managed write-through.
- [ ] Có TTL và eviction policy theo loại dữ liệu.
- [ ] Có kế hoạch đối phó cache stampede/cold start.
- [ ] Có negative caching khi cần và tách NOT_FOUND khỏi lỗi.
- [ ] Có single-flight/refresh-ahead/stale-if-error trong phạm vi phù hợp.
- [ ] Đã xem race read-fill vs DB-update/invalidation.
- [ ] Có version guard/CAS hoặc chính sách stale minh bạch.
- [ ] Không tin wall-clock timestamp như một global version nếu chưa được bảo đảm.
- [ ] Có invalidation event/outbox/CDC nếu cần giảm bỏ sót.
- [ ] Có cache key namespace/schema/tenant scope an toàn.
- [ ] Đã thiết kế L1/L2 coherence và multi-region propagation.
- [ ] Có serialization schema version và numeric precision đúng.
- [ ] Không dùng cache stale để xác nhận inventory/payment/ACL.
- [ ] Có read-your-writes/minVersion path khi sản phẩm cần.
- [ ] Nếu write-through, đã có policy cho DB commit/cache update fail.
- [ ] Nếu write-behind, đã định nghĩa loss budget và durability của accepted writes.
- [ ] Có durable queue, idempotency, ordering và flusher replay khi cần.
- [ ] Đã chọn rõ snapshot coalescing hay delta retention.
- [ ] Có queue backpressure, DLQ/quarantine và retry budget.
- [ ] API phân biệt ACCEPTED với PERSISTED/COMMITTED.
- [ ] Có metrics hit/miss, p99, stale reads và invalidation lag.
- [ ] Có metrics write-behind oldest pending age/backlog/flush errors.
- [ ] Đã thử cache outage, DB outage, lost ACK, duplicate và out-of-order.
- [ ] Đã thử eviction, restart và hot-key expiration storm.
- [ ] Có runbook khôi phục cache từ source/durable log.
- [ ] Không gọi cache replication/persistence là DB transaction nếu hợp đồng không hỗ trợ.

## 51. Tổng kết

Bốn chiến lược cache khác nhau chủ yếu ở **vị trí điều phối đọc/ghi và thời điểm xác nhận kết quả**:

- **Cache-aside:** ứng dụng đọc cache, miss thì đọc NoSQL DB và điền cache; writes thường commit DB trước rồi invalidate cache. Đơn giản, linh hoạt, nhưng cần xử lý stale fills, invalidation và stampede.
- **Read-through:** cache/provider/loader chịu trách nhiệm nạp dữ liệu từ source khi miss. Giúp tập trung logic đọc, nhưng **không tự quy định cách ghi** hoặc bảo đảm mọi cached value là mới nhất.
- **Write-through:** cache writer đồng bộ thao tác đến backing store trên đường ghi. Có thể giữ cache gần source hơn và làm rõ thời điểm backing-store ACK, nhưng hai hệ **không tự commit nguyên tử**; partial failure vẫn phải thiết kế.
- **Write-behind:** accepted writes đi vào buffer/cache/queue, backing store được cập nhật bất đồng bộ. Có thể tăng write throughput và batching, nhưng phải làm rõ accepted vs persisted, durability, ordering, retries, idempotency, coalescing và backpressure.

**TTL, replication hoặc cache hit rate cao không thay thế consistency contract.** Với dữ liệu nghiệp vụ cần uniqueness, số dư, tồn kho, thanh toán và quyền truy cập, hãy thực thi quyết định tại **authoritative source** qua điều kiện/giao dịch phù hợp. Cache có thể tăng tốc quan sát, nhưng không được tự nhận quyền xác nhận một business operation mà source chưa commit.

Nguyên tắc thiết kế đáng nhớ: **“Cache có thể mất và được dựng lại; dữ liệu đã được hệ thống hứa lưu bền vững hoặc đã xác nhận nghiệp vụ thì không được biến mất chỉ vì cache, worker hay mạng gặp lỗi.”** Chọn chiến lược theo read/write ratio, độ mới cần đạt, loss budget, transaction boundary và khả năng phục hồi đã được kiểm chứng, không chỉ theo latency trên happy path.

