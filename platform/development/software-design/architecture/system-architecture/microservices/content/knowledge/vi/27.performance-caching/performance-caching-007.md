# Cache stampede, khóa làm mới và ngăn nhiều yêu cầu tải lại đồng thời

> **Chủ đề:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm kiến thức:** Hiệu năng và bộ nhớ đệm (Performance & Caching)  
> **Mục tiêu:** Nhận biết tình trạng nhiều request cùng cache miss và tải lại một dữ liệu, thiết kế single-flight theo key, phối hợp khóa làm mới giữa các replica, bảo vệ database/API bằng giới hạn tải và bảo đảm kết quả đúng khi TTL hết, cache lỗi hoặc các tác vụ refresh cạnh tranh.

## 1. Cache stampede là gì?

Cache thường giảm số lần gọi database hoặc dịch vụ phụ thuộc bằng cách phục vụ dữ liệu đã lưu. Nhưng khi một cache entry được nhiều người truy cập cùng hết hạn, hàng trăm hoặc hàng nghìn request có thể cùng thấy MISS và **đồng thời** chạy cùng một tác vụ nạp lại dữ liệu.

Hiện tượng này gọi là **cache stampede**; trong một số tài liệu còn gọi là cache dogpile, và nó có đặc điểm của thundering herd. Một lần miss đơn lẻ không phải vấn đề. Vấn đề là **công việc nạp lại cho cùng một key bị nhân lên theo số caller** thay vì chỉ thực hiện một lần rồi chia sẻ kết quả.

Giả sử sản phẩm A đang được quảng cáo và có 5.000 request/giây:

~~~text
                5.000 requests/second
                         |
                         v
                  Cache GET(product:A)
                         |
                        MISS
                         |
           +-------------+-------------+
           |             |             |
           v             v             v
        Request 1     Request 2     Request N
           |             |             |
           +-------------+-------------+
                         |
               Product DB / Catalog API
                         |
        Connections, CPU, I/O, locks increase
                         |
         Latency increases -> more requests wait
                         |
           Timeouts and retries amplify load
~~~

Nếu database mất 300 ms để đọc và dựng payload, trong thời gian chờ đó có thể có khoảng 1.500 request mới đến cùng key. Nếu tất cả đều gọi database, một lượt hết hạn TTL gây hàng nghìn truy vấn dư thừa. Khi database chậm lên 2 giây, số request tích tụ còn tăng nhiều hơn.

Một hiệu ứng vòng lặp nguy hiểm: DB chậm làm cache refresh kéo dài; nhiều caller tiếp tục miss; DB nhận thêm tải, càng chậm; client retry khiến tải tăng tiếp. Sự cố có thể lan sang những endpoint khác cùng sử dụng DB, pool kết nối hoặc CPU.

**Mục tiêu:** Khi nhiều caller cần cùng dữ liệu, chỉ có một số rất nhỏ tác vụ được phép tải từ nguồn trong một phạm vi phối hợp; các caller còn lại chia sẻ kết quả, dùng stale data khi hợp lệ hoặc được từ chối có kiểm soát.

## 2. Phân biệt những sự cố cache gần nhau

| Tình huống | Điểm nổi bật | Ví dụ | Biện pháp chính |
|---|---|---|---|
| Cache miss bình thường | Key chưa từng được lưu hoặc đã hết hạn | Lần đầu mở một SKU | Load rồi cache |
| Cache stampede / dogpile | Nhiều caller cùng key nạp lại đồng thời | SKU hot vừa hết TTL | Single-flight, per-key refresh lock |
| Hot-key expiration / breakdown | Một key cực nóng hết hạn | Giá khuyến mại đang viral | SWR, refresh-ahead, coalescing |
| Cache avalanche | Nhiều key hết hạn cùng lúc, hoặc cache mất dữ liệu diện rộng | Restart Redis, TTL đồng loạt | TTL jitter, warmup có giới hạn |
| Cache penetration | Nhiều truy vấn đến key không tồn tại | Bot dò ID giả | Negative caching, validation, rate limit |
| Cache stampede sau failure | Nguồn lỗi khiến mỗi request tiếp tục thử làm mới | DB 503, miss liên tục | Breaker, retry budget, stale-if-error |

Thuật ngữ trong thực tế có thể khác nhau. Khi điều tra, quan trọng hơn là xác định: bao nhiêu key miss, key nào nóng, bao nhiêu caller chờ, bao nhiêu loader thật sự chạy, nguồn dữ liệu đang chịu mức tải nào.

### 2.1. Những nguyên nhân kích hoạt phổ biến

- TTL hết hạn trên hot key.
- Nhiều key cùng có TTL cố định và cùng được tạo ở một đợt warmup/deploy.
- Cache bị eviction vì memory pressure.
- Redis/Memcached restart, failover hoặc mất một shard.
- Thay đổi schema/version key sau release khiến toàn bộ request nhìn thấy key mới chưa có dữ liệu.
- Invalidation hàng loạt sau cập nhật bảng dữ liệu.
- Cấu hình cache client gặp lỗi mạng, khiến hit bị coi là miss.
- Loader bị timeout, thất bại, hoặc cache SET không thành công.
- Retry không giới hạn từ nhiều tầng ứng dụng.
- Single-flight chỉ áp dụng trong một pod, trong khi nhiều pod cùng miss.

**Đừng coi cache miss và cache backend unavailable là một trạng thái.** Cache chưa có entry và Redis đang lỗi hoàn toàn có thể cần chính sách khác nhau.

## 3. Tác động đến năng lực và độ trễ của hệ thống

Định luật Little, trong trạng thái ổn định:

\[
L = \lambda W
\]

Với \(\lambda\) là tốc độ đến/hoàn tất trung bình, \(W\) là thời gian trung bình công việc tồn tại trong hệ thống, \(L\) là số công việc trung bình đang có.

Ví dụ 2.000 request/s cùng chờ nạp key:
- Loader mất 0,1 giây: có thể có khoảng 200 caller đang trong khoảng chờ.
- Loader mất 1 giây: có thể có khoảng 2.000 caller đang chờ.
- Nếu mỗi caller độc lập gọi DB, nhu cầu DB connection và query tăng mạnh.
- Nếu chỉ một caller được làm loader, số caller chờ vẫn có thể lớn, nhưng DB chỉ thấy một lượt load cho key trong phạm vi single-flight.

Đây là phép minh họa trung bình, không phải cam kết p99 hay con số thực của một hệ thống mất ổn định. Cần quan sát queueing, fan-out, retry và timeout.

### 3.1. Đo đúng nhu cầu từ request

Có thể chia hai đại lượng:
- **Logical misses:** số request mà ban đầu không thấy cache entry phù hợp.
- **Actual source loads:** số lượt thật sự truy vấn nguồn dữ liệu để nạp lại.

Không chống stampede: actual source loads có thể gần số logical misses khi mọi request đều tự nạp. Có single-flight tốt: nhiều logical misses chia sẻ một actual source load.

Một thước đo minh họa:

~~~text
coalescingFactor =
  eligibleMissRequests / max(actualSourceLoads, 1)
~~~

Hệ số cao thường cho thấy hiệu quả gom lời gọi, nhưng không đủ để khẳng định người dùng được phục vụ tốt: có thể hàng nghìn request đang chờ một loader quá chậm. Cần kết hợp latency, stale served ratio, timeout và số waiter.

## 4. Cache-aside: điểm phát sinh stampede phổ biến

Mẫu cache-aside thông thường:

~~~text
GET /products/42
    |
    v
Cache GET
    |
    +-- HIT --> Return
    |
    +-- MISS --> Database SELECT
                     |
                     v
                   Cache SET
                     |
                     v
                   Return
~~~

Khi 100 request vào cùng lúc, tất cả có thể thực hiện GET trước khi bất kỳ request nào SET cache. Nếu loader tốn 300 ms, đó là một cửa sổ rất rộng để nhiều request cùng chạy SELECT.

Một thiết kế an toàn hơn:

~~~text
GET /products/42
    |
    v
Cache GET
    |
    +-- HIT --> Return
    |
    +-- MISS --> Join / create in-flight load for key
                         |
                         +-- Winner: load DB, write cache
                         |
                         +-- Followers: await same result
                         |
                         v
                    Return / fallback
~~~

Không nên khóa toàn cache trong lúc gọi DB. Một key chậm không được làm chậm các key khác không liên quan. Khóa hoặc future phải được tổ chức **theo key**, kèm giới hạn tổng concurrent loads.

### 4.1. Định nghĩa key trước khi tối ưu

Ví dụ key product:42 là chưa đủ nếu payload phụ thuộc tenant, locale, currency hoặc quyền của người gọi. Có thể cần:

~~~text
catalog:v3:tenant-9:locale-vi:currency-VND:product-42
~~~

Không đưa secret, access token hoặc PII thô vào key. Dữ liệu theo quyền riêng tư có thể không phù hợp cho shared cache. **Sự chính xác và ranh giới dữ liệu quan trọng hơn việc cache hit nhiều.**

## 5. Bộ chiến lược giảm stampede

| Cơ chế | Mục đích | Điều chưa giải quyết |
|---|---|---|
| TTL jitter | Tránh nhiều key hết hạn cùng một thời điểm | Một key nóng vẫn hết hạn |
| Single-flight trong process | Gom caller cùng key vào một loader | Pod khác vẫn có loader riêng |
| Distributed refresh lock | Phối hợp các pod làm mới cùng key | Lock expiry, split owner, stale write |
| Soft TTL + stale-while-revalidate | Trả dữ liệu cũ trong lúc refresh | Chỉ phù hợp khi được phép stale |
| Refresh-ahead | Nạp trước hạn sử dụng | Chi phí background work, scheduling |
| Bounded loader executor | Giới hạn loads đồng thời | Có thể phải từ chối/đợi request |
| Rate limit/backpressure | Bảo vệ DB/API trước nhu cầu quá năng lực | Không tạo thêm capacity |
| Negative cache | Giảm truy vấn tới key xác nhận không tồn tại | Dữ liệu mới tạo có thể bị che tạm |
| Circuit breaker và retry budget | Không dồn tải vào downstream đang lỗi | Cần fallback đúng hợp đồng |
| Prewarm có kiểm soát | Tránh cold miss cho hot key quan trọng | Tốn dung lượng và công suất nguồn |
| Versioned writes/fencing | Tránh loader cũ đè cache mới | Cần cơ chế ghi nguyên tử/đáng tin |

Một thiết kế tốt thường dùng **nhiều lớp**, chứ không lựa chọn một cơ chế duy nhất. TTL jitter giúp tránh avalanche, single-flight giúp cùng key không nạp trùng, còn global admission control bảo vệ DB trước hàng nghìn key khác nhau miss.

## 6. TTL jitter và hiện tượng hết hạn đồng loạt

Giả sử sau deployment, service prewarm 50.000 key trong 5 giây, tất cả TTL bằng 600 giây. Sau 10 phút, 50.000 key có thể đồng loạt hết hạn, gây burst vào database.

TTL jitter làm lệch thời hạn:

~~~text
baseTTL  = 600 giây
jitter   = random(-60, +60) giây
actualTTL = baseTTL + jitter
~~~

Có thể chọn jitter theo một khoảng chỉ làm giảm TTL để không vượt giới hạn dữ liệu được phép cũ. Phân bố ngẫu nhiên và khoảng thời gian phải có lý do dựa trên SLO, memory, truy cập và mức độ biến động dữ liệu.

**Giới hạn:** chỉ có một entry cho hot key X. Bất kể TTL ngẫu nhiên là 553 hay 642 giây, nó vẫn hết hạn đúng một thời điểm. Hàng nghìn caller cùng miss key X cần single-flight hoặc phục vụ stale, không chỉ jitter.

### 6.1. Chọn TTL theo dữ liệu

| Dữ liệu | Freshness contract | Chính sách có thể xét |
|---|---|---|
| Mô tả sản phẩm / ảnh | Cho phép cũ ít phút | Soft/hard TTL, SWR |
| Danh sách gợi ý | Có thể cũ hoặc rỗng | Refresh-ahead, stale-if-error |
| Giá hiển thị | Tùy chiến dịch và thời điểm hiệu lực | Event invalidation, version, TTL phù hợp |
| Tồn kho khi chốt đơn | Cần kiểm tra/giữ hàng ở nguồn giao dịch | Cache hỗ trợ đọc, xác minh khi ghi |
| Quyền truy cập bị thu hồi | Có yêu cầu bảo mật chặt | Không phục vụ stale ngoài policy |
| Trạng thái thanh toán cuối | Không được xác nhận thành công giả | Đọc nguồn hoặc trạng thái đã xác minh |

Không có TTL mặc định phù hợp cho mọi loại. Đặt TTL là một quyết định về độ đúng, hiệu năng và chi phí.

## 7. Single-flight trong một instance

**Single-flight** là kỹ thuật để những caller đồng thời cùng key chờ **một tác vụ load đang chạy**, thường thông qua map key → Future/Promise.

~~~text
Request A(keyX) ──┐
Request B(keyX) ──┤
Request C(keyX) ──┼─> inFlight[keyX] ─> ONE source load
Request D(keyX) ──┤                      |
Request E(keyX) ──┘                      v
                                  Cache updated
                                       |
                                Shared result
~~~

Một key Y khác có thể load song song. Cần bảo đảm:
1. Winner được chọn nguyên tử.
2. Follower không tự gọi DB.
3. Future được complete đúng một lần.
4. Map entry được xóa cả khi thành công và thất bại.
5. Cache được ghi theo thứ tự hợp lý trước khi mở khóa cho request mới.
6. Khi một waiter hủy chờ, nó không phá shared load còn phục vụ waiter khác.
7. Có thời hạn và giới hạn số key/future đang in-flight.

### 7.1. Java: single-flight với ConcurrentHashMap

Ví dụ JDK, giả định Cache và Repository là interface được triển khai theo ứng dụng:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executor;
import java.util.concurrent.RejectedExecutionException;

public final class ProductReader {
    private final ConcurrentHashMap<String, CompletableFuture<Product>>
            inFlight = new ConcurrentHashMap<>();

    private final Cache cache;
    private final Repository repository;
    private final Executor loaderExecutor;

    public ProductReader(
            Cache cache,
            Repository repository,
            Executor loaderExecutor
    ) {
        this.cache = cache;
        this.repository = repository;
        this.loaderExecutor = loaderExecutor;
    }

    public CompletableFuture<Product> get(String key) {
        Product hit = cache.getIfPresent(key);
        if (hit != null) {
            return CompletableFuture.completedFuture(hit);
        }

        CompletableFuture<Product> mine = new CompletableFuture<>();
        CompletableFuture<Product> prior = inFlight.putIfAbsent(key, mine);

        if (prior != null) {
            // Dependent stage tránh trao future gốc cho caller.
            return prior.thenApply(v -> v);
        }

        try {
            loaderExecutor.execute(() -> {
                try {
                    Product value = repository.load(key);
                    cache.put(key, value);
                    mine.complete(value);
                } catch (Throwable failure) {
                    mine.completeExceptionally(failure);
                } finally {
                    inFlight.remove(key, mine);
                }
            });
        } catch (RejectedExecutionException rejected) {
            inFlight.remove(key, mine);
            mine.completeExceptionally(rejected);
        }

        return mine.thenApply(v -> v);
    }

    public interface Cache {
        Product getIfPresent(String key);
        void put(String key, Product value);
    }

    public interface Repository {
        Product load(String key);
    }

    public record Product(String id, String name) {}
}
~~~

Các điểm cần hiểu:

- putIfAbsent chọn winner trước khi khởi chạy loader; một key chỉ có một shared future đang đăng ký tại thời điểm đó.
- previous.thenApply tạo stage cho follower, giúp một caller không trực tiếp điều khiển future gốc.
- Ghi cache trước khi complete và remove để giảm khoảng trống tạo loader mới.
- remove(key, mine) chỉ xóa đúng future của owner, tránh xóa entry mới không liên quan.
- Loader executor phải có giới hạn worker/queue. Single-flight cùng key không bảo vệ trước hàng nghìn key khác nhau.
- Cần deadline cho thao tác load và thời gian chờ của caller, phân loại lỗi để xử lý retry/fallback.
- Nếu cache.put thất bại sau khi DB load thành công, ví dụ trên trả lỗi; một lựa chọn khác có thể trả dữ liệu vừa load và báo cache write failure riêng, tùy hợp đồng.
- Bắt Throwable trong ví dụ nhằm không để future treo; trong triển khai thực cần phân biệt lỗi nghiêm trọng của runtime và quản lý log/exception phù hợp.
- Code không xử lý per-tenant auth, multi-pod lock, stale policy hoặc shutdown. Đó là các lớp bổ sung.

### 7.2. Những race cần chú ý

**Future hoàn tất trước khi cache được cập nhật:** request mới đến có thể không thấy cache và tự tạo loader thứ hai. Chọn thứ tự put → complete → remove hợp lý.

**Entry future lỗi không được xóa:** mọi caller về sau nhận lỗi cũ mãi. Phải remove sau lỗi hoặc dùng một failed-result cooldown riêng có TTL ngắn.

**Caller cancel shared future:** nếu đưa trực tiếp Future gốc ra ngoài, caller hủy có thể làm hỏng những caller khác. Bao một stage phụ thuộc hoặc dùng API chờ phù hợp.

**Lock quá thô:** synchronized quanh toàn bộ cache làm một key chậm chặn mọi key. Chỉ coalesce theo đúng key.

**In-flight map tăng vô hạn:** traffic tới nhiều key ngẫu nhiên có thể làm map và executor đầy. Giới hạn số loader tổng, số waiter và rate của các key không hợp lệ.

### 7.3. Caffeine và cache loader

Các thư viện như Caffeine có cơ chế loading cache và refresh theo key trong phạm vi cache instance, nhưng cần đọc đúng semantics của phiên bản đang dùng. Ví dụ refreshAfterWrite thường đánh dấu entry đủ điều kiện refresh khi được truy cập, không nhất thiết chạy theo đồng hồ cho mọi entry không còn ai đọc.

Quan trọng nhất: một cache Caffeine ở mỗi JVM **không tự biến thành distributed single-flight**. Nếu 20 pod cùng có L1 miss, vẫn có thể có 20 source loaders khi L2/lock không bảo vệ.

## 8. Nhiều pod cần khóa làm mới phân tán

Một cache L2 như Redis được dùng chung bởi nhiều pod. Nếu L2 miss cùng key, local single-flight không đủ bảo vệ backend trên toàn cluster.

~~~text
Pod A          Pod B          Pod C
  |              |              |
  +--------------+--------------+
                 |
             Redis GET(key)
                 |
                MISS
                 |
           Try lock(key)
                 |
       +---------+----------+
       |                    |
      WINNER               LOSERS
       |                    |
     Load DB          Return stale
       |              or bounded wait
     Cache SET               |
       |                 Recheck cache
    Release lock             |
       +--------------------+
                 |
               Return
~~~

Khóa cần có phạm vi **một đối tượng cache**. Không đặt một global mutex cho tất cả dữ liệu nếu các key độc lập.

### 8.1. Acquire lease an toàn hơn SETNX trần

Ví dụ Redis:

~~~text
SET refresh:product:42 <random-owner-token> NX PX 10000
~~~

- NX: chỉ tạo lock nếu chưa có.
- PX: thời hạn 10.000 ms, tránh lock tồn tại mãi khi owner chết.
- Owner token ngẫu nhiên: nhận diện quyền xóa lock của đúng tác vụ.

Con số 10 giây chỉ minh họa. Phải chọn theo loader p99, pause/GC, network delay và yêu cầu phục hồi. Lease quá ngắn dễ hết trước khi owner hoàn tất; quá dài làm người khác đợi lâu khi owner chết.

### 8.2. Release phải kiểm owner nguyên tử

Không được chỉ gọi DEL vì:

~~~text
A lấy lease
A bị pause quá hạn
Lease của A hết
B lấy lease mới
A tỉnh lại, DEL làm mất khóa B
C có thể lấy lease thứ ba
~~~

Một Lua script compare-and-delete minh họa:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
~~~

Chỉ xóa khi owner token hiện tại khớp với người gọi. Tuy nhiên, cơ chế này **chỉ bảo vệ thao tác unlock**; nó chưa ngăn owner A đã hết lease ghi dữ liệu cũ sau khi B ghi dữ liệu mới.

### 8.3. Double-check cache sau khi lấy lock

Một workflow refresh:

1. GET key → MISS.
2. Cố lấy lease.
3. Khi lấy được lease, GET key lần nữa.
4. Nếu một tác vụ khác vừa ghi cache trong lúc cạnh tranh, trả cache hit; không gọi DB nữa.
5. Nếu vẫn miss, load DB trong deadline.
6. Ghi cache có kiểm tra version khi cần.
7. Release lease bằng so khớp owner.
8. Trả dữ liệu hoặc lỗi/fallback đúng hợp đồng.

Nếu bỏ bước kiểm cache lần hai, các worker lấy lock nối tiếp nhau có thể tiếp tục tải cùng key dù entry đã được nạp.

### 8.4. Follower nên làm gì khi không lấy được lock?

Không busy-poll Redis mỗi 1 ms; hàng nghìn follower sẽ tạo quá tải mới lên Redis. Có thể:
- Trả stale last-known-good nếu dữ liệu còn trong cửa sổ được phép.
- Chờ boundedly, recheck cache theo backoff + jitter.
- Dùng local future để một pod chỉ có một tác vụ poll/đợi đại diện cho key.
- Dừng chờ khi request deadline hết.
- Trả 503/429/fallback phù hợp nếu không thể đáp ứng chính xác.
- Chỉ cố trở thành owner mới khi lease đã hết và vẫn có quyền/budget.

Khi có notification đánh thức waiter, vẫn cần recheck cache và xử lý notification mất, đến trước hoặc bị trùng. Không thể xem Pub/Sub không bền vững là cam kết giao hàng tuyệt đối.

## 9. Vì sao lock hết hạn có thể làm kết quả bị cũ?

Một race xảy ra:

~~~text
T0: A lấy lease L1 và đọc product version=10
T1: A bị GC pause hoặc loader rất chậm
T2: L1 hết hạn
T3: B lấy lease L2
T4: B đọc product version=11
T5: B cache SET version=11
T6: A tỉnh lại, cache SET version=10
~~~

Dù B có khóa hợp lệ, bản cũ của A vẫn có thể ghi đè kết quả mới. Kiểm owner khi release không giải quyết race ghi.

### 9.1. Version-aware conditional cache write

Một hướng là lưu payload kèm source version:

~~~json
{
  "sourceVersion": 11,
  "data": {
    "productId": "42",
    "displayName": "Product 42"
  }
}
~~~

Khi ghi, chỉ chấp nhận value mới nếu sourceVersion không nhỏ hơn version đã lưu. So sánh và ghi phải là thao tác nguyên tử trong backend cache hoặc tầng lưu trữ có hỗ trợ. Nếu tách GET version và SET payload thành hai lệnh không nguyên tử, race vẫn có thể xảy ra.

Version phải mang ý nghĩa thứ tự đáng tin trong phạm vi aggregate/stream. Một timestamp cập nhật từ nhiều máy có clock skew không nhất thiết là version tăng đơn điệu.

### 9.2. Fencing token

Một cách khác là cấp fencing token tăng đơn điệu cho mỗi lần được trao quyền:

~~~text
A obtains fence = 101
B obtains fence = 102

Storage accepts write from B (102)
Storage rejects delayed write from A (101)
~~~

**Điều kiện bắt buộc:** nơi nhận side effect phải kiểm và lưu token cao nhất **nguyên tử**. Tạo token rồi chỉ log hoặc gửi theo request mà storage không kiểm tra sẽ không có tác dụng. Nguồn cấp token và semantics failover của hệ thống điều phối cũng phải được đánh giá.

Không dùng Redis lease như một bảo đảm exactly-once cho thao tác có side effect quan trọng như thanh toán. Những nghiệp vụ đó cần idempotency, transaction, reconciliation và state machine riêng.

## 10. Soft TTL, hard TTL và stale-while-revalidate

Một số dữ liệu có thể được phục vụ khi hơi cũ, ví dụ danh sách gợi ý, ảnh đại diện, mô tả sản phẩm. Khi đó, thay vì xóa entry đúng lúc soft TTL hết hạn, có thể giữ dữ liệu cũ để trả ngay và refresh ngầm.

- **Soft TTL / refreshAt:** thời điểm bắt đầu cần làm mới.
- **Hard TTL / expiresAt:** sau thời điểm này không được trả dữ liệu cũ, trừ khi chính sách stale-if-error riêng cho phép.

~~~text
T0: Entry written
  |
  v
FRESH window
  |  requests return cached value
  v
Soft TTL reached
  |  return stale-but-allowed
  |  trigger ONE background refresh
  v
Hard TTL reached
  |  old data no longer valid
  |  bounded load / reject / explicit fallback
  v
EXPIRED
~~~

Ví dụ minh họa:
- 0–60 giây: dữ liệu fresh.
- 60–180 giây: trả cache cũ, đồng thời refresh bất đồng bộ.
- Sau 180 giây: không phục vụ cache cũ theo hợp đồng bình thường.

Con số này không phù hợp với mọi dữ liệu. Nếu thông tin là quyền truy cập vừa bị thu hồi, không được tự cho phép stale 2 phút chỉ để đạt hit rate.

### 10.1. SWR vẫn cần single-flight

Nếu mỗi request sau soft TTL đều tự tạo refresh task, SWR chỉ đổi stampede đồng bộ thành **background refresh stampede**. Cần per-key refresh ownership, bounded executor và cooldown/backoff sau lỗi.

### 10.2. State machine của entry

~~~text
MISSING
  |
  | successful load
  v
FRESH
  |
  | soft expiry
  v
STALE_REFRESHABLE
  |
  +--> acquire refresh ownership
  |         |
  |         v
  |      REFRESHING
  |         | success
  |         v
  |        FRESH
  |
  +--> refresh failed -> cooldown + stale if allowed
  |
  | hard expiry
  v
EXPIRED / NOT_SERVABLE
~~~

Không nên để refresh failure làm stale entry tiếp tục sống vô hạn nếu hợp đồng có hard freshness limit.

### 10.3. Stale-if-error khác SWR

- **Stale-while-revalidate:** trả bản cũ có chủ đích trong lúc đang nạp bản mới.
- **Stale-if-error:** khi không thể nạp bản mới vì lỗi, tạm trả last-known-good nếu chưa vượt cửa sổ được phép.
- **Hard correctness limit:** điểm dừng buộc phải từ chối hoặc đọc nguồn chính xác, bất chấp hit rate.

Cần đo stale age và stale served ratio để tránh việc HTTP 200 che giấu database đang lỗi.

## 11. Refresh-ahead và prewarming

**Refresh-ahead** làm mới dữ liệu trước khi hard TTL hết. Nó hữu ích cho tập hot key có thể dự báo, ví dụ SKU flash sale sắp bắt đầu hoặc danh mục được đọc liên tục.

Các cách:
1. Scheduler làm mới top hot keys theo chu kỳ có jitter.
2. Trigger refresh khi entry gần soft TTL và có request.
3. Event từ source thúc đẩy refresh hoặc invalidation.
4. Prewarm tập key dự kiến dùng trước campaign.
5. Background work queue có concurrency/rate giới hạn.

Nhưng refresh-ahead **không miễn phí**. Nếu mọi pod cùng refresh 1.000 hot keys mỗi phút, nguồn sẽ chịu thêm số lần gọi nhân theo replica. Dùng một ownership scheme hoặc shared refresh lease. Khi có nhiều key, phải giữ ngân sách loader để không ảnh hưởng giao dịch chính.

### 11.1. Tránh warmup toàn bộ đồng loạt

Khi một cluster restart, không khởi chạy hàng trăm pod rồi mỗi pod đọc hàng triệu key từ DB. Chia batch, jitter thời điểm, giới hạn số loader, ưu tiên hot key và đo impact. Nếu cluster có hàng trăm nghìn key không được truy cập thường xuyên, warmup tất cả còn lãng phí memory.

### 11.2. Event invalidation cần bảo đảm phiên bản

Giả sử loader A đọc version 10, source cập nhật version 11 và gửi invalidate, rồi A ghi version 10 vào cache. Đây là race giữa load và invalidation. Cần versioned cache writes, version floor hoặc key versioning khi consistency yêu cầu. Transactional outbox có thể giúp chuyển sự kiện cập nhật từ DB tới pipeline bền vững.

## 12. Negative caching để chặn truy vấn key không tồn tại

Một key không tồn tại vẫn thường xuyên bị truy vấn: URL cũ, bot dò ID, dữ liệu sai tham chiếu. Nếu mọi request không tồn tại đều gọi DB, hệ thống có thể bị cache penetration.

**Negative caching** lưu kết quả không tồn tại đã được xác minh với TTL ngắn:

~~~text
key = product:9999999
value = NOT_FOUND
negativeTTL = 15 seconds  # ví dụ minh họa
~~~

Những điều cần làm:
- Chỉ negative-cache NOT_FOUND thực sự từ nguồn có thẩm quyền.
- Không biến timeout, 500 hoặc lỗi kết nối thành NOT_FOUND.
- Tách ranh giới tenant/authorization; tránh dùng negative cache để tiết lộ dữ liệu tồn tại cho người không có quyền.
- Giữ TTL ngắn và invalidate khi dữ liệu có thể được tạo mới.
- Giới hạn số negative entries tránh kẻ tấn công làm cache đầy bằng key ngẫu nhiên.
- Kết hợp validation/rate limiting vì mỗi key ngẫu nhiên vẫn có thể đòi một truy vấn lần đầu.

Single-flight chỉ gom request cùng key; khi attacker gửi hàng triệu key khác nhau, cần global budget bảo vệ nguồn.

## 13. Giới hạn tổng tải loader: single-flight theo key chưa đủ

Nếu Redis restart và 20.000 key khác nhau cùng miss, một loader/key vẫn tương đương 20.000 loader. Database có thể quá tải ngay cả khi mỗi key chỉ một winner.

Một tầng admission control:

~~~text
Cache Miss
    |
    v
Per-key single-flight / refresh ownership
    |
    v
Global loader semaphore / rate limiter
    |
    +-- permit -> DB/API load with deadline
    |
    +-- no permit
           |
           +--> serve stale if allowed
           +--> bounded wait
           +--> reject / degrade according to contract
~~~

### 13.1. Concurrency limit và rate limit khác nhau

- Concurrency limit: số loader đang chạy đồng thời.
- Rate limit: số lượt bắt đầu loader mỗi giây.
- Bounded queue: số waiter/tác vụ đang chờ.
- Backpressure: thông báo hoặc điều tiết upstream để không sinh thêm việc vượt năng lực.

Một limiter 100 loads/s vẫn có thể tích 1.000 loader in-flight nếu mỗi load mất 10 giây. Một semaphore 100 slot có thể cho phép hàng nghìn loads/s nếu mỗi load rất ngắn. Cần chọn theo ranh giới thật của DB hoặc API provider.

### 13.2. Giới hạn toàn cluster hay trên mỗi pod?

Giả sử DB cho phép 80 concurrent cache-miss loads toàn hệ thống. Nếu có 20 pod và mỗi pod cho 80 slot, tổng giới hạn có thể là 1.600, sai ngân sách. Có thể phân bổ 4 slot/pod trong trường hợp replica count ổn định, hoặc dùng coordinated global limiter khi cần thích ứng HPA và traffic lệch pod.

Ngoài loader cache, DB còn nhận:
- Transaction ghi nghiệp vụ.
- Background consumers.
- Batch/report jobs.
- Queries của service khác.
- Migration, backup và operational access.

Bulkhead chỉ có tác dụng nếu giới hạn thật được tôn trọng ở nguồn hoặc qua một cơ chế phân bổ.

### 13.3. Request deadline và chờ có giới hạn

Người dùng có 900 ms deadline, loader 500 ms và caller đã tiêu 400 ms trước khi tới cache. Việc xếp hàng thêm 300 ms rồi bắt đầu loader gần như chắc chắn không kịp. Cần xét remaining deadline, timeout nguồn, chi phí response và policy fallback.

Đừng để một cache miss giữ worker/connection vô hạn chỉ vì có future đang chạy. Waiter có thể timeout mà loader vẫn tiếp tục phục vụ các waiter khác, tùy chính sách.

## 14. Cache đa tầng L1/L2 và ranh giới phối hợp

Một mô hình:

~~~text
Request
  |
  v
L1 Caffeine / local cache
  |
  +-- hit -> return
  |
  v
L2 Redis shared cache
  |
  +-- hit -> fill L1 -> return
  |
  v
Local single-flight
  |
  v
Distributed per-key refresh ownership
  |
  v
Global backend load budget
  |
  v
Source DB / API
~~~

L1 giảm độ trễ network, L2 chia sẻ cache giữa pod, local single-flight chặn nhiều request trong pod, distributed coordination chặn nhiều pod nạp cùng key và global limiter chặn nhiều key gây quá tải.

### 14.1. Cache consistency giữa L1 và L2

Nếu L2 đã có version mới nhưng L1 một pod còn version cũ, người dùng vẫn có thể thấy stale. Thiết kế:
- L1 TTL ngắn theo freshness contract.
- Invalidation message có version từ source.
- Key versioning hoặc version-aware replacement.
- Periodic reconciliation nếu notification có thể mất.
- Strict source verification ở thao tác nghiệp vụ bắt buộc.

Đừng xem Redis Pub/Sub thông thường là durable log. Nếu mất notification có thể gây hậu quả nghiêm trọng, cần cơ chế đảm bảo và phục hồi phù hợp.

### 14.2. Tránh cache lẫn dữ liệu nhiều tenant

Cache key phải chứa những chiều ảnh hưởng payload: tenant, locale, loại khách hàng, currency, API version hoặc access scope khi cần. Không dùng một key chung cho dữ liệu riêng tư. Không dùng token hoặc password thô làm key. Nếu dữ liệu phụ thuộc quyền từng người, có thể không cache ở shared layer nếu không có thiết kế an toàn.

## 15. Race giữa update và refresh

Một kịch bản nguy hiểm:

~~~text
T0: Loader A bắt đầu đọc product version 10
T1: Admin cập nhật product thành version 11
T2: Event invalidate cache được gửi
T3: Redis key bị xóa
T4: Loader A hoàn tất và SET version 10 với TTL mới
~~~

Sau T4, cache lại chứa bản cũ dù sự kiện invalidation đã được xử lý. Nếu chỉ dùng DEL khi dữ liệu thay đổi và SET vô điều kiện khi load, hệ thống có thể phục vụ dữ liệu lỗi thời trong cả một chu kỳ TTL mới.

Các hướng giảm race:
- Lưu sourceVersion/rowVersion trong payload.
- Cache write bằng compare-and-set nguyên tử, chỉ cho version không lùi.
- Giữ một version watermark hoặc invalidation floor theo aggregate.
- Dùng immutable/versioned cache keys và chuyển pointer theo cơ chế nguyên tử.
- Khi dữ liệu cực nhạy, đọc nguồn xác thực ở bước ghi hoặc không phục vụ stale.
- Kết hợp outbox và reconciliation để phát hiện event bị bỏ sót.

**Không có bảo đảm exactly-once chỉ vì có khóa Redis.** Data version và transition phải được xác nhận tại nơi chứa dữ liệu thật khi nghiệp vụ yêu cầu.

## 16. Timeout, retry và circuit breaker trong đường refresh

Khi loader lỗi, nếu mọi caller retry ngay sẽ tạo thêm tải:

~~~text
One request: initial attempt + 2 retries = 3 loads
1.000 logical misses/s -> up to 3.000 load attempts/s
~~~

Nếu Gateway, service và HTTP client đều retry độc lập, số attempts có thể nhân qua các tầng. Với cache miss, retry nên:
- Chỉ áp cho lỗi tạm phù hợp.
- Có max attempts và tổng deadline.
- Backoff mũ và jitter.
- Tôn trọng Retry-After/quota downstream.
- Dừng khi không còn khả năng đáp ứng deadline.
- Không khiến mọi follower tự retry trong khi winner vẫn đang xử lý.
- Có circuit breaker/cooldown khi nguồn đang lỗi.
- Giữ tính idempotent với thao tác có side effect.

Không cache một timeout như kết luận “không có sản phẩm”; đây là hai trạng thái khác nhau. Trong trường hợp loader lỗi, có thể trả stale nếu hợp đồng cho phép hoặc trả lỗi có nghĩa rõ.

### 16.1. Circuit breaker không thay semaphore

Circuit breaker ngắt lời gọi khi dependency lỗi/chậm theo chính sách. Nhưng khi breaker đang closed, nhiều miss vẫn có thể làm cạn pool trước khi breaker quyết định mở. Cần concurrency limit/queue bound, timeout và rate budget song song.

### 16.2. Khi lock service lỗi

Nếu Redis không tới được:
- Dữ liệu có thể stale trong L1: cân nhắc sử dụng trong giới hạn.
- Nguồn cần tính đúng đắn mạnh: fail safe hoặc truy vấn trực tiếp trong ngân sách cứng.
- Không fail-open để tất cả request tự tải DB không giới hạn.
- Ghi metric cache backend unavailable, fallback path và actual source loads.
- Khi Redis hồi phục, tránh đồng loạt refill toàn bộ key trong một giây.

## 17. Observability: phát hiện stampede và chứng minh bảo vệ có tác dụng

| Metric | Kiểu | Ý nghĩa |
|---|---|---|
| cache_lookup_total{result} | Counter | Hit/miss/stale/error |
| cache_miss_requests_total | Counter | Số caller ban đầu thấy miss |
| cache_source_load_total{outcome} | Counter | Số loader thật sự gọi nguồn |
| cache_source_load_seconds | Histogram | p50/p95/p99 loader duration |
| cache_inflight_loader | Gauge | Số loader đang chạy |
| cache_waiter_count | Gauge | Số caller đang chờ kết quả |
| cache_lock_attempt_total{result} | Counter | Lease acquired/contended/failed |
| cache_lock_wait_seconds | Histogram | Thời gian chờ lock/kết quả |
| cache_lease_expired_total | Counter | Lease hết khi loader chưa hoàn tất |
| cache_refresh_total{result} | Counter | Refresh success/failure/timeout |
| cache_stale_served_total | Counter | Số request được phục vụ stale |
| cache_data_age_seconds | Histogram | Tuổi dữ liệu được trả |
| cache_loader_rejected_total | Counter | Admission control chặn loader |
| cache_backend_error_total | Counter | Lỗi Redis/cache |
| cache_eviction_total | Counter | Eviction theo nguyên nhân |
| cache_invalidation_total | Counter | Số sự kiện invalidate |
| db_cache_reload_queries_total | Counter | DB queries do refresh/miss |

Không gắn raw cache key, product ID, user ID, saga ID hoặc token vào metric label nếu chúng có cardinality lớn hoặc nhạy cảm. Dùng cache_name, endpoint, key_class, environment, tier, outcome. Để điều tra hot key cụ thể, dùng sampled logs hoặc top-K được bảo vệ quyền truy cập.

### 17.1. Nhìn đồng thời cache và backend

Tín hiệu điển hình:

~~~text
cache hit rate ↓
logical misses ↑
actual source loads ↑
DB active connections / QPS ↑
DB p99 ↑
waiters / timeouts ↑
client retries ↑
API p99 / 5xx ↑
~~~

Nếu logical misses tăng mạnh nhưng actual loads chỉ tăng nhẹ, single-flight có thể đang hoạt động. Tuy nhiên nhiều waiter vẫn có thể chờ quá lâu; cần kiểm p99 end-to-end và stale response. Nếu source loads không tăng nhưng stale age liên tục tăng, refresh có thể chết âm thầm.

### 17.2. Alert theo hậu quả thực

- Actual source loads/s vượt ngân sách hoặc DB active connections gần trần.
- Cache miss rate tăng đồng thời với DB p99/timeout.
- Lock contention hoặc lease-expired rate tăng nhanh.
- Stale served ratio cao và data age vượt policy.
- Loader rejection tăng kéo dài.
- Redis error rate/evictions tăng trùng với cache miss spike.
- Cache key version thay đổi sau rollout khiến hit rate sụt trên mọi pod.

Không alert chỉ vì hit rate hơi thấp trên các key hiếm khi được truy cập; gắn ngưỡng với SLO và dependency saturation.

## 18. Load test cache stampede

Một bài thử tốt cần chứng minh số loader, độ đúng dữ liệu và hành vi khi lỗi.

### 18.1. Cùng một hot key

1. Warm entry X trong cache.
2. Chuẩn bị hàng nghìn caller cùng bắt đầu khi entry hết TTL.
3. Đo cache miss, local coalescing, distributed lock contenders, số source calls.
4. Kiểm tra DB p99, connection saturation và request p99.
5. So sánh 1 pod với nhiều pod.
6. Kiểm các response trả payload/version đúng.

Kỳ vọng: local single-flight gom trong một process; distributed coordination giảm trùng giữa pod trong lease window. Dù có lease, cần bảo vệ stale write nếu owner vượt hạn.

### 18.2. Nhiều key hết hạn đồng loạt

Tạo nhiều key bằng cùng TTL, rồi so sánh:
- Không jitter.
- Có jitter.
- Jitter + single-flight.
- Jitter + global limiter.
- Refresh-ahead và SWR.

Đo peak actual loader concurrency, backend QPS, latency, số rejected requests và stale age. Một lần chạy tốt trên warm cache chưa chứng minh cold-start an toàn.

### 18.3. Tình huống lỗi cần thử

| Fault injection | Tín hiệu | Hành vi mong đợi |
|---|---|---|
| Loader chậm 10× | Waiters, p99 tăng | Không tạo loader vô hạn |
| DB trả 503 | Refresh failures tăng | Breaker/backoff, không retry storm |
| Holder lease chết | Lock tồn tại đến expiry | Worker khác có đường phục hồi |
| Holder bị pause quá lease | Có owner kế tiếp | Version/fencing chặn stale overwrite |
| Redis outage | Cache errors tăng | Không fail-open load DB vô hạn |
| Cache SET thất bại | Load success nhưng cache error | Response/fallback theo policy |
| Nhiều key không tồn tại | Negative cache/rate limit hoạt động | DB không bị đánh sập |
| 20.000 key đồng thời miss | Global limiter bị sử dụng | DB trong ngân sách |
| Source update giữa refresh | Version conflict | Cache không lùi version khi policy yêu cầu |
| Rollout đổi key schema | Hit rate giảm | Warmup/rollout không tạo avalanche |
| Cache entry bị eviction hàng loạt | Miss burst | Capacity và admission control bảo vệ nguồn |

Tất cả thử nghiệm tải phải ở môi trường được kiểm soát hoặc được cho phép; tránh tạo chi phí/side effect trên API thanh toán hoặc bên thứ ba thật.

## 19. Runbook khi cache miss khiến database nghẽn

**Bước 1 — Bảo vệ dependency:** kiểm tra DB CPU, I/O, lock, active connections và p99. Giảm loader concurrency/rate theo ngân sách, tạm ngừng prewarm/reporting ít ưu tiên, chặn retry vô điều kiện.

**Bước 2 — Xác định loại sự cố:** một hot key hết hạn, nhiều key cùng TTL, Redis outage, eviction, thay đổi key version hay refresh failure? Đo logical misses, actual loaders và lock contention.

**Bước 3 — Khoanh vùng:** endpoint, cache namespace, tenant/cohort, release/config revision, region và các pod cùng bị ảnh hưởng.

**Bước 4 — Khôi phục theo hợp đồng:** nếu dữ liệu có thể stale, bật đường last-known-good trong giới hạn. Với dữ liệu bắt buộc mới, dùng bounded load hoặc trả lỗi phù hợp. Chọn warmup từng đợt, không flush toàn cache như phản xạ mặc định.

**Bước 5 — Sửa nguyên nhân:** bổ sung single-flight nếu thiếu; chỉnh TTL jitter, distributed lock expiry, versioned write, executor bounds, retry budget hoặc truy vấn DB quá chậm.

**Bước 6 — Kiểm chứng:** actual source loads giảm, cache hit phục hồi, DB p99/active connections về vùng an toàn, stale age không vượt policy, không có payload cũ ghi đè mới, request quan trọng đạt SLO.

Không dùng “đặt TTL rất dài” để che lỗi consistency; nếu dữ liệu giá/tồn kho/authorization thay đổi, TTL dài có thể tạo hậu quả nghiệp vụ lớn hơn.

## 20. Ví dụ kiến trúc cho flash sale

Giả sử:
- 25 pod API.
- 12.000 request/s vào trang chi tiết sản phẩm.
- Khoảng 300 SKU rất nóng.
- DB chỉ có ngân sách 500 query/s dành cho cache refresh trong giờ cao điểm.
- Mô tả và hình ảnh có thể stale 2 phút; giá khi checkout cần xác minh theo quy trình giao dịch.
- L1 in-process cache và L2 Redis dùng chung.

Thiết kế có thể gồm:
1. Tách key dữ liệu mô tả ít đổi khỏi stock/price cập nhật nhanh.
2. Dùng L1 TTL ngắn có jitter để giảm Redis reads.
3. Dùng L2 với soft/hard freshness timestamps và source version.
4. Local single-flight theo key trong mỗi pod.
5. Shared per-key refresh lease trên Redis, safe compare-and-delete.
6. Version-aware cache write, không cho nguồn version cũ đè mới.
7. Global loader concurrency/rate limit dựa vào 500 DB queries/s và chi phí query.
8. Refresh-ahead cho tập SKU hot, giới hạn batch và có jitter.
9. Stale-while-revalidate cho mô tả và danh sách gợi ý, không dùng stale inventory làm quyết định chốt đơn.
10. Negative caching có giới hạn cho SKU được xác nhận không tồn tại.
11. Theo dõi source loads, waiters, stale age, cache errors và completed orders.

### 20.1. Tính ngân sách

Nếu mỗi lần load một Product Detail cần 2 DB queries, ngân sách 500 queries/s cho đường này tương đương khoảng 250 loads/s theo giả định chi phí tương đối đồng nhất. Điều đó không đồng nghĩa có thể chạy 250 loader **đồng thời**; concurrency còn phụ thuộc thời gian truy vấn và mức saturation DB.

Nếu 25 pod chỉ có local single-flight, mỗi hot key có thể vẫn có tới 25 loader cùng lúc. Với 300 hot key đồng loạt miss, số loader tiềm năng rất lớn. Distributed coordination và global limit cần bảo vệ cùng lúc. Còn nếu nhiều key đều làm mới thường xuyên, phải kiểm tra liệu 250 loads/s có đủ để giữ freshness SLO không; nếu không, cần giảm nhu cầu source load bằng data model/index/event update hoặc tăng năng lực nguồn.

### 20.2. Cache là optimization, source vẫn phải đúng

Một API có thể dùng stale giá hiển thị tạm thời nếu chính sách cho phép, nhưng bước thanh toán phải xác nhận giá cuối và trả thông tin rõ cho người dùng. Inventory reservation cần kiểm soát oversell ở source-of-truth. Không biến caching thành thay thế transaction hoặc authorization.

## 21. Những sai lầm thường gặp

**“Tăng TTL là hết stampede.”** TTL dài giảm tần suất miss nhưng một hot key vẫn sẽ hết hạn; còn tăng stale window có thể sai dữ liệu.

**“Jitter giải quyết mọi trường hợp.”** Jitter làm lệch thời điểm nhiều key hết hạn, không giảm nhiều request cùng một hot key khi key đó hết TTL.

**“Redis tự gom các cache miss.”** Redis chia sẻ giá trị nhưng không tự gọi DB thay mọi pod. Nhiều pod vẫn thấy MISS đồng thời.

**“synchronized trong Java là khóa toàn cluster.”** Nó chỉ hoạt động trong JVM đó. Multi-pod cần cơ chế phối hợp riêng.

**“Dùng SETNX là đã có mutex tuyệt đối.”** Lease có thể hết khi owner vẫn đang chạy; cần version/fencing cho stale write và release bằng owner token.

**“Một câu DEL là đủ nhả khóa.”** Owner cũ có thể xóa nhầm lock của owner mới sau lease expiry.

**“Có distributed lock là backend không thể quá tải.”** Nhiều key khác nhau vẫn tạo nhiều winner; giới hạn global loader mới bảo vệ ngân sách DB.

**“Trả stale thì không cần quan sát lỗi.”** Nếu mọi response vẫn 200 nhưng dữ liệu cũ hàng giờ, người dùng có thể bị sai lệch mà dashboard chỉ báo xanh.

**“Mọi failure đều nên negative-cache.”** Timeout không phải NOT_FOUND; authorization failure không phải missing product.

**“Mỗi follower nên retry ngay để giảm latency.”** Điều này tạo retry storm và khiến DB recovery lâu hơn.

**“Cache key càng đơn giản càng tốt.”** Bỏ tenant, currency, locale hoặc authorization scope có thể trả dữ liệu sai hay rò rỉ thông tin.

**“Flush Redis là cách nhanh nhất sửa cache.”** Flush toàn bộ trong giờ cao điểm có thể tạo cache avalanche nghiêm trọng.

**“Một shared future có thể bị bất kỳ waiter nào cancel.”** Cần đảm bảo một caller không vô tình hủy computation đang phục vụ những caller khác.

**“Cache đúng khi đọc thì sẽ đúng khi ghi.”** Race giữa refresh và invalidation có thể làm version cũ ghi đè bản mới.

## 22. Bài tập tình huống

Một hệ thống NewsFeed có 16 pod API, mỗi pod dùng Caffeine L1 và Redis L2. Feed nổi bật nhận 4.000 request/giây. Redis entry hết hạn sau 60 giây. DB cần 500 ms để dựng feed. Mỗi pod có synchronized riêng cho key. Khi Redis restart, API p99 tăng từ 90 ms lên 6 giây và DB connection pool cạn.

**Câu hỏi:**

1. Vì sao synchronized của từng pod không thể bảo đảm chỉ một source load trên toàn cluster?
2. Trong một đợt miss một key, có thể có bao nhiêu loader nếu tất cả 16 pod cùng nhận traffic?
3. Vì sao 16 loader/key vẫn gây sự cố khi hàng nghìn key đồng thời miss?
4. Nếu Feed cho phép stale tối đa 120 giây, thiết kế soft TTL/hard TTL thế nào?
5. Khi holder lease bị pause quá TTL và owner khác ghi version mới, chống ghi đè bằng gì?
6. Metric nào giúp phân biệt logical miss với actual source load?
7. Nếu DB trả 503, vì sao không nên để 4.000 caller cùng retry?
8. Nếu cache L2 mất kết nối, fallback thế nào để DB không bị đổ tải vượt trần?
9. Negative caching có giúp truy vấn feed key sai không? Điều kiện áp dụng?
10. Khi source feed thay đổi, làm sao tránh refresh cũ ghi đè event invalidation mới?

**Định hướng giải:** local single-flight giúp một loader/key/pod, nhưng 16 pod vẫn có thể tạo 16 loader. Dùng shared refresh ownership, version-aware writes, soft/hard TTL và stale response hợp lệ để giảm latency. Thêm global loader limiter bảo vệ DB trước nhiều key khác nhau. Khi nguồn lỗi, dùng backoff, breaker và budget; không coi lỗi 503 là dữ liệu không tồn tại. Dùng metric cache miss, source loads, lock contention, stale age, DB p99 và thời gian chờ của caller để kiểm chứng.

## 23. Checklist áp dụng

1. **Phân loại dữ liệu:** stale có được phép không, hard freshness limit là gì?
2. **Thiết kế key:** có phân biệt đúng tenant, locale, currency, version, permissions không?
3. **Đo tải:** request/key, hot-key distribution, loader p95/p99 và backend QPS/connection budget.
4. **TTL:** base TTL, jitter, soft/hard TTL và invalidation rules.
5. **Single-flight local:** map/future per-key, lifecycle success/error/cancellation, bounded memory.
6. **Coordination cross-pod:** per-key lease, owner token, timeout, safe release.
7. **Chống stale writes:** version-aware atomic write hoặc fencing ở đích thực.
8. **Double-check:** sau khi lấy lock, kiểm cache lần nữa trước khi gọi nguồn.
9. **Follower policy:** stale response, bounded wait, jitter, fail fast theo contract.
10. **Global budget:** concurrency limit, rate limit, bounded queue và backpressure.
11. **Refresh policy:** refresh-ahead/SWR, không tạo một refresh task cho mỗi request.
12. **Negative cache:** chỉ cho kết quả không tồn tại đã xác minh, TTL và size limit hợp lý.
13. **Retry:** budget, deadline, backoff+jitter, circuit breaker và không retry nhiều tầng.
14. **Consistency:** source version, invalidation race, L1/L2 divergence và transactional outbox khi cần.
15. **Failure behavior:** Redis outage, DB 503, lease expiry, cache write fail, process crash.
16. **Security:** không cache lẫn dữ liệu tenant/user, không cache secret, không trả stale authorization sai.
17. **Observability:** logical miss, actual loaders, waiters, stale age, lock contention, error và DB saturation.
18. **Load test:** hot key, many-key avalanche, multi-pod, holder crash, slow loader, Redis failover.
19. **Runbook:** giới hạn tải, có khả năng warmup/rollback, đối chiếu dữ liệu sau sự cố.
20. **Review lại theo traffic thật:** cache size, TTL, lock lease, top hot key, p99 và global headroom.

## 24. Ghi nhớ cốt lõi

- **Cache stampede là việc nhiều caller cùng nạp lại dữ liệu do cache miss**, khiến áp lực lên DB/API tăng mạnh và có thể gây lỗi dây chuyền.
- **TTL jitter** giúp phân tán nhiều key hết hạn; **single-flight** gom nhiều caller cùng key; **distributed refresh coordination** giảm loader trùng giữa pod; **global admission control** bảo vệ trước nhiều key cùng miss.
- **Lease không đồng nghĩa quyền ghi vô hạn:** owner cũ có thể tiếp tục chạy sau khi lease hết. Cần so owner khi release và kiểm version/fencing khi ghi nếu freshness có yêu cầu.
- **SWR và refresh-ahead** giúp người dùng không phải chờ mọi lần nạp, nhưng stale chỉ được dùng trong ranh giới nghiệp vụ cho phép.
- **Negative cache, timeout, retry budget, breaker, bounded queue và backpressure** là các lớp bổ sung để xử lý key không tồn tại, nguồn lỗi và cache outage.
- **Cache hit rate cao không đủ chứng minh hệ thống khỏe.** Phải đo actual loader calls, waiters, stale age, DB saturation, latency và tính đúng đắn của kết quả.
- **Thiết kế phải chịu được cả cold start, hot key, Redis restart, lock expiry và source update racing with refresh**, đồng thời bảo vệ source-of-truth và quyền truy cập dữ liệu.
