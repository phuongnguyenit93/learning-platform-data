# Chống cache stampede khi nhiều yêu cầu cùng tải lại dữ liệu

**Cache stampede** xảy ra khi nhiều yêu cầu đồng thời cùng cần một dữ liệu đang không có trong cache hoặc vừa hết hạn. Thay vì chỉ một yêu cầu tải lại dữ liệu từ database/API nguồn rồi ghi cache, **nhiều yêu cầu cùng thực hiện thao tác tải lại**. Một khóa “nóng” được hàng nghìn request truy cập có thể khiến database nhận hàng nghìn truy vấn giống hệt nhau trong một khoảng thời gian rất ngắn.

Trong **Spring Data Redis**, Redis thường là cache dùng chung cho nhiều instance ứng dụng. Khả năng chia sẻ kết quả rất có ích, nhưng Redis **không mặc nhiên gom các cache miss đồng thời thành một lần tải nguồn**. Vì vậy, chỉ thêm `@Cacheable` hoặc một lệnh `GET` rồi `SET` chưa chắc đã tránh được stampede.

Mục tiêu của bài học là thiết kế đường đọc sao cho cache miss không biến thành “bão truy vấn nguồn”, đồng thời giữ giới hạn độ cũ dữ liệu, độ trễ, tính nhất quán và cách phục hồi sau lỗi rõ ràng.

## 1. Cache stampede diễn ra như thế nào?

Giả sử một website bán hàng có sản phẩm `p-100` rất phổ biến. Trạng thái lúc 10:00:

```text
Redis:
    cache:product:p-100  -> tồn tại, TTL còn 1 giây

Database:
    products(id=p-100)   -> một bản ghi
```

Đúng khi TTL kết thúc, 500 request cùng tới:

```text
                500 HTTP requests
                      |
                      v
             GET cache:product:p-100
                      |
                      v
                 CACHE MISS
                      |
       +--------------+--------------+
       |              |              |
   Request 1      Request 2      Request 500
       |              |              |
       v              v              v
   SELECT DB       SELECT DB       SELECT DB
       |              |              |
       +--------------+--------------+
                      |
                      v
         Nhiều kết quả giống nhau
         được ghi lại vào cùng key
```

Tất cả request nhìn thấy miss trước khi một request kịp ghi giá trị mới vào Redis. Nếu mỗi truy vấn nguồn tiêu tốn 100 ms, số lượng truy vấn dư thừa có thể làm cạn connection pool, tăng độ trễ và tạo thêm request đang chờ. Nguồn chậm đi lại khiến cửa sổ miss kéo dài, làm càng nhiều request cùng lọt vào.

Đây là một **vòng khuếch đại tải**:

```text
Khóa nóng hết hạn
       |
       v
Nhiều request miss
       |
       v
Database/API bị dồn tải
       |
       v
Thời gian tải nguồn tăng
       |
       v
Nhiều request tiếp tục miss
       |
       +----> Tải nguồn tăng tiếp
```

### Ước lượng sơ bộ

Giả sử một endpoint nhận 1.000 request/giây đến cùng một key và thời gian tải nguồn là 200 ms. Trong cửa sổ 200 ms, có thể có khoảng **200 request** cùng nhìn thấy miss trước khi entry đầu tiên được tạo; đây chỉ là mô hình ước lượng khi lưu lượng tương đối đều, không phải số đo cố định.

Nếu hệ thống có 10 instance, mỗi instance tự gọi database khi miss, Redis dùng chung cũng không giải quyết được vấn đề. Cần cơ chế giảm số **lần tính lại dữ liệu** trên toàn nhóm request.

## 2. Phân biệt stampede, avalanche và cache penetration

Ba vấn đề thường cùng xuất hiện nhưng nguyên nhân và biện pháp có điểm khác nhau.

| Hiện tượng | Dấu hiệu | Nguyên nhân chính | Biện pháp đáng cân nhắc |
|---|---|---|---|
| **Cache stampede** | Rất nhiều request cùng tải lại một key nóng | Cùng một key miss/hết hạn đồng thời | Request coalescing, single-flight, lock, stale-while-revalidate |
| **Cache avalanche** | Nhiều key cùng hết hạn hoặc cache ngừng hoạt động | TTL đồng loạt, Redis outage hoặc invalidate diện rộng | TTL jitter, phân đợt nạp lại, bảo vệ nguồn, phục hồi cache |
| **Cache penetration** | Nhiều request hỏi key không tồn tại và luôn miss | ID sai, dữ liệu thiếu, lưu lượng không hợp lệ | Negative caching, kiểm tra ID, giới hạn tốc độ, lọc ở tầng ứng dụng |

Ví dụ:

- Một sản phẩm đang rất hot hết hạn và 500 request cùng query database: **stampede**.
- 100.000 sản phẩm được cache cùng lúc với TTL 5 phút, rồi cùng hết hạn: **avalanche**.
- Bot liên tục yêu cầu sản phẩm không tồn tại, mỗi lần đều vào database: **penetration**.

Một hệ thống có thể vừa bị avalanche vừa bị stampede: hàng loạt key hết hạn, trong đó một số key cực nóng kéo theo nhiều truy vấn trùng. Chiến lược bảo vệ cần tính cả hai cấp độ.

## 3. Mức bảo đảm cần xác định trước

Không phải dữ liệu nào cũng chấp nhận cách giảm stampede giống nhau. Hãy phân loại theo yêu cầu nghiệp vụ:

| Loại dữ liệu | Có thể phục vụ bản cũ? | Độ cũ có thể chấp nhận | Hướng xử lý |
|---|---|---|---|
| Bài viết, metadata danh mục | Thường có | Vài phút tùy nghiệp vụ | TTL + single-flight + stale-while-revalidate |
| Giá tham khảo, khuyến mại | Có điều kiện | Ngắn, phải rõ điểm quyết định giá | Invalidate theo event, TTL phù hợp, tái kiểm tra khi thanh toán |
| Số lượng hàng hiển thị | Có điều kiện | Có thể khác tồn kho giao dịch | Cache đọc nhưng xác nhận lại khi giữ hàng |
| Quyền truy cập, trạng thái khóa tài khoản | Thường không nên dựa vào stale tùy tiện | Rất thấp | Nguồn xác thực, invalidation đáng tin cậy |
| Số dư/ghi nhận giao dịch tài chính | Không dùng stale làm căn cứ cuối cùng | Theo quy tắc nhất quán chặt | Giao dịch ở nguồn dữ liệu thích hợp |

Câu hỏi quan trọng: khi Redis miss hoặc nguồn chậm, ứng dụng được phép **chờ**, **trả bản cũ**, **từ chối có kiểm soát** hay **trả một giá trị dự phòng**?

Nếu yêu cầu bắt buộc chính xác tức thời, không nên dùng dữ liệu stale chỉ để giảm tải. Có thể chấp nhận tăng độ trễ hoặc bảo vệ nguồn bằng giới hạn đồng thời rồi trả lỗi rõ ràng.

## 4. Tại sao @Cacheable đơn thuần chưa đủ?

Spring Cache cho phép:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogQueryService {

    private final ProductStore store;

    public CatalogQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "productById", key = "#p0")
    public ProductView findById(String productId) {
        return store.findById(productId);
    }
}
```

Luồng hoạt động:

1. Spring Cache kiểm tra key trong cache `productById`.
2. Nếu hit, trả giá trị đã cache mà không gọi `store.findById`.
3. Nếu miss, chạy method tải nguồn và đưa kết quả vào cache.

Điểm còn thiếu là **phối hợp giữa những request cùng miss**. Nếu 200 request đến trước khi lần tải đầu hoàn tất, các request có thể đồng thời đi qua nhánh miss và chạy method.

### 4.1. @Cacheable(sync = true) có thể giúp gì?

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        sync = true)
public ProductView findById(String productId) {
    return store.findById(productId);
}
```

`sync = true` yêu cầu Spring Cache dùng cơ chế hỗ trợ đồng bộ việc tải value cho cùng key nếu cache provider triển khai tương ứng. Ý tưởng là tránh nhiều luồng cùng tính một giá trị trong phạm vi mà provider bảo đảm.

Nhưng **đừng mặc định `sync = true` bảo đảm chỉ có đúng một request tới database trên toàn bộ 10 instance ứng dụng**. Tính chất khóa cục bộ hay phân tán, phạm vi khóa, cách xử lý concurrent load và timeout phụ thuộc `Cache` implementation, Redis cache writer và cấu hình của phiên bản thư viện đang chạy.

Một số giới hạn của `sync = true` trong Spring Cache cần lưu ý:

- Chỉ khai báo **một cache** cho cùng thao tác.
- Không kết hợp với `unless` vì việc tải được đồng bộ theo hợp đồng cache loader.
- Không coi annotation là cơ chế distributed lease, fencing token hoặc consistency lock của nghiệp vụ.
- Nếu dùng cấu hình khóa ở mức Redis cache writer, phải hiểu **phạm vi khóa** có thể rộng hơn một entry; một cấu hình khóa ở mức cache name có thể giảm trùng tải nhưng làm các key độc lập chờ nhau.

Hãy đo thực tế với nhiều instance trước khi chọn đây là giải pháp duy nhất cho hot key.

## 5. Các tầng phòng vệ chống stampede

Không nên phụ thuộc duy nhất vào một kỹ thuật. Một chiến lược vững chắc thường kết hợp nhiều lớp:

```text
           Request đọc dữ liệu
                  |
                  v
              Redis GET
                  |
           +------+------+
           |             |
         HIT            MISS
           |             |
           v             v
        Trả value     Lớp chống stampede
                         |
                +--------+--------+
                |                 |
            Có người           Chưa ai
            đang tải           đang tải
                |                 |
                v                 v
          Chờ có giới hạn     Giành quyền tải
          hoặc trả stale          |
                |                 v
                |              Gọi nguồn
                |                 |
                +---------+-------+
                          |
                          v
                     Cache value
                          |
                          v
                      Trả kết quả
```

Các lớp có thể phối hợp:

1. **TTL hợp lý và TTL jitter** để giảm hết hạn hàng loạt.
2. **Single-flight trong một JVM** để gom request trùng tại một instance.
3. **Distributed lock/lease trên Redis** nếu cần gom việc tải xuyên nhiều instance.
4. **Stale-while-revalidate** nếu nghiệp vụ cho phép trả dữ liệu đã cũ trong thời gian ngắn.
5. **Refresh-ahead / prewarming** cho key nóng dự đoán được.
6. **Giới hạn concurrency, timeout, circuit breaker** để bảo vệ nguồn khi cache không cứu được.
7. **Negative caching** để giảm truy vấn lặp tới ID không tồn tại.
8. **Đo lường và điều chỉnh** vì tăng hit rate không tự đảm bảo hết stampede.

Không nhất thiết bật tất cả. Chọn kỹ thuật theo độ nóng của key, số instance, chi phí tải nguồn và yêu cầu freshness.

## 6. TTL jitter: rải thời điểm hết hạn

Nếu nhiều cache key được tạo vào cùng phút và có TTL giống nhau, chúng dễ hết hạn đồng loạt. Jitter thêm một mức ngẫu nhiên vào thời gian sống để rải thời điểm hết hạn.

Ví dụ Spring Data Redis với `StringRedisTemplate`:

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public void cacheProduct(
        String productId,
        String jsonValue,
        StringRedisTemplate redis) {

    String key = "cache:product:v1:" + productId;

    // Ví dụ: TTL từ 240 tới 300 giây, không vượt trần 300 giây.
    long seconds = ThreadLocalRandom.current().nextLong(240, 301);

    redis.opsForValue().set(
            key,
            jsonValue,
            Duration.ofSeconds(seconds));
}
```

Phân bố TTL thay vì:

```text
Tạo 10.000 key lúc 10:00:00
TTL cố định 300s
=> gần như cùng hết hạn lúc 10:05:00
```

sẽ là:

```text
10:04:00 ├───── nhiều key hết hạn rải rác ─────┤ 10:05:00
```

**Lưu ý quan trọng:** TTL jitter rất có ích để chống avalanche, nhưng **không tự giải quyết stampede của một key cực nóng**. Nếu `cache:product:v1:p-hot` vừa hết hạn và hàng trăm request cùng tới, chúng vẫn cần coordination.

Nếu nghiệp vụ có trần độ cũ tối đa 5 phút, không dùng jitter kiểu “300 ± 60 giây” dẫn đến TTL 360 giây vượt giới hạn. Một lựa chọn là lấy ngẫu nhiên trong khoảng **không vượt trần**, hoặc thiết kế refresh/invalidation giúp dữ liệu đủ mới theo hợp đồng.

## 7. Single-flight trong một ứng dụng: gom nhiều request cùng key

**Single-flight** (request coalescing) có ý tưởng:

- Request đầu tiên gặp miss trở thành người tải dữ liệu.
- Những request khác cùng key **dùng chung kết quả đang được tính** thay vì gọi nguồn thêm lần nữa.
- Khi hoàn tất, trạng thái đang tải phải được giải phóng để lần miss tương lai có thể nạp tiếp.

Nếu một instance nhận 100 request đồng thời tới key `p-hot`, single-flight có thể giúp instance đó chỉ gọi nguồn một lần trong cửa sổ tải lại.

### 7.1. Ví dụ Java với ConcurrentHashMap và CompletableFuture

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Supplier;

public final class LocalSingleFlight<V> {

    private final ConcurrentMap<String, CompletableFuture<V>> inFlight =
            new ConcurrentHashMap<>();

    public V call(String key, Supplier<V> loader) {
        CompletableFuture<V> mine = new CompletableFuture<>();
        CompletableFuture<V> existing =
                inFlight.putIfAbsent(key, mine);

        // Có request khác đang tải cùng key.
        if (existing != null) {
            return existing.join();
        }

        try {
            V value = loader.get();
            mine.complete(value);
            return value;
        } catch (Throwable error) {
            mine.completeExceptionally(error);
            throw error;
        } finally {
            inFlight.remove(key, mine);
        }
    }
}
```

Mẫu trên cho thấy cấu trúc phối hợp: chỉ một request trong cùng JVM chạy `loader` cho mỗi key ở một thời điểm; những request đến trong lúc tải chờ `CompletableFuture` của leader.

Trong mã production, cần bổ sung chính sách:

- **Timeout và giới hạn chờ:** `join()` không có timeout. Đối với request HTTP, tránh giữ thread chờ vô hạn; có thể dùng future với deadline hoặc API bất đồng bộ.
- **Giới hạn số key đang tải:** `ConcurrentHashMap` có thể tăng lớn khi hàng triệu key khác nhau cùng miss.
- **Không giữ kết quả lỗi mãi:** khi leader lỗi, map phải được xóa để có cơ hội retry có kiểm soát; đồng thời tránh lập tức tạo làn sóng retry.
- **Ngữ nghĩa lỗi follower:** follower có thể nhận `CompletionException` thay vì exception gốc; tầng service cần phân loại và ánh xạ lỗi.
- **Vòng đời instance:** ứng dụng restart sẽ mất bảng `inFlight`, không có dữ liệu phối hợp xuyên process.

Ví dụ sử dụng:

```java
private final LocalSingleFlight<ProductView> singleFlight =
        new LocalSingleFlight<>();

public ProductView loadProduct(String id) {
    return singleFlight.call(id, () -> productStore.findById(id));
}
```

Với dữ liệu Redis dùng chung, nhiều instance vẫn có thể cùng tải `p-hot`, mỗi instance một lần. Nếu có 8 replica, single-flight cục bộ có thể giảm 500 truy vấn trùng thành khoảng 8 truy vấn, nhưng **không cam kết còn đúng 1 truy vấn trên toàn hệ thống**.

## 8. Distributed lock trên Redis: chỉ một instance tải lại

Khi có nhiều instance cùng chia sẻ Redis, một cách phối hợp là dùng khóa có TTL:

```text
cache:product:v1:p-hot      -> cache data
lock:cache:product:v1:p-hot -> quyền tải lại tạm thời
```

Request xử lý như sau:

1. Thử đọc cache.
2. Nếu miss, dùng Redis `SET lockKey token NX PX leaseMs` để giành quyền.
3. Nếu giành được lock, **đọc lại cache lần nữa**: một request khác có thể đã vừa nạp xong.
4. Nếu vẫn miss, gọi nguồn, ghi dữ liệu vào cache.
5. Giải phóng lock **chỉ khi token của mình còn là chủ sở hữu**.
6. Nếu không lấy được lock, chờ có giới hạn rồi đọc cache lại, hoặc trả bản stale theo chính sách.

### 8.1. Vì sao phải dùng SET NX và TTL?

`SET ... NX` chỉ tạo lock nếu chưa có khóa. TTL của lock (lease) giúp tránh giữ khóa vĩnh viễn nếu process bị crash giữa chừng.

Ví dụ Redis:

```redis
SET lock:cache:product:v1:p-hot "unique-token" NX PX 15000
```

Nếu thành công, request hiện tại nắm một lease 15 giây; nếu lock đã tồn tại, lệnh không tạo khóa mới.

**Không dùng `SETNX` rồi `EXPIRE` bằng hai lệnh riêng** nếu có thể dùng `SET ... NX PX`. Khi process chết giữa hai lệnh, lock có thể tồn tại mà không có TTL.

**Không giải phóng lock bằng `DEL lockKey` vô điều kiện.** Lock cũ có thể đã hết hạn và request khác đã giành lại với token mới. Xóa vô điều kiện sẽ xóa lock thuộc request khác.

### 8.2. Script Lua giải phóng lock an toàn theo token

```lua
-- KEYS[1]: lock key
-- ARGV[1]: token của request đang giữ lock
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Script được thực thi như một đơn vị tại Redis: chỉ xóa nếu token vẫn trùng, tránh khoảng hở giữa `GET` kiểm tra và `DEL`.

Trong Redis phiên bản hỗ trợ thao tác compare-and-delete chuyên dụng phù hợp, có thể cân nhắc API tương ứng. Với mã Java dùng Spring Data Redis, script Lua so token là lựa chọn phổ biến và dễ thể hiện hợp đồng.

## 9. Ví dụ Spring Data Redis: tải một giá trị với Redis lease

Ví dụ dưới đây minh họa đường đọc dùng `StringRedisTemplate`. Dữ liệu được biểu diễn dưới dạng chuỗi JSON để tập trung vào phối hợp cache; việc serialize JSON và truy vấn nguồn là trách nhiệm của `ProductSource`.

### 9.1. Định nghĩa nguồn dữ liệu

```java
public interface ProductSource {

    // Trả JSON đã được định dạng theo hợp đồng cache.
    // Có thể ném exception nếu nguồn không sẵn sàng.
    String loadProductJson(String productId);
}
```

### 9.2. Service đọc và chống tải trùng

```java
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheLoader {

    private static final Duration CACHE_TTL = Duration.ofMinutes(5);
    private static final Duration LOCK_LEASE = Duration.ofSeconds(15);

    // Giới hạn thời gian request không sở hữu lock chờ kết quả.
    private static final long MAX_WAIT_MS = 600;

    private static final RedisScript<Long> UNLOCK_SCRIPT = unlockScript();

    private final StringRedisTemplate redis;
    private final ProductSource source;

    public ProductCacheLoader(
            StringRedisTemplate redis,
            ProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public String getProductJson(String productId) {
        String dataKey = "cache:product:v1:" + productId;
        String lockKey = "lock:cache:product:v1:" + productId;

        String cached = redis.opsForValue().get(dataKey);
        if (cached != null) {
            return cached;
        }

        String token = UUID.randomUUID().toString();
        Boolean locked =
                redis.opsForValue().setIfAbsent(lockKey, token, LOCK_LEASE);

        if (Boolean.TRUE.equals(locked)) {
            try {
                // Double-check: tránh tải khi request khác vừa ghi cache.
                String again = redis.opsForValue().get(dataKey);
                if (again != null) {
                    return again;
                }

                String fresh = source.loadProductJson(productId);
                if (fresh == null) {
                    // Ví dụ không cache null; production cần negative caching.
                    return null;
                }

                redis.opsForValue().set(dataKey, fresh, CACHE_TTL);
                return fresh;
            } finally {
                // Chỉ xóa lock nếu token vẫn là của mình.
                redis.execute(UNLOCK_SCRIPT, List.of(lockKey), token);
            }
        }

        // Có request khác đang tải. Chờ có giới hạn rồi đọc cache lại.
        return waitForCachedValue(dataKey);
    }

    private String waitForCachedValue(String dataKey) {
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(MAX_WAIT_MS);

        while (System.nanoTime() < deadline) {
            String value = redis.opsForValue().get(dataKey);
            if (value != null) {
                return value;
            }

            long pauseMs = ThreadLocalRandom.current().nextLong(20, 61);
            try {
                Thread.sleep(pauseMs);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while waiting for cache", interrupted);
            }
        }

        throw new CacheBusyException(
                "Timed out waiting for another cache loader");
    }

    private static RedisScript<Long> unlockScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(
                "if redis.call('GET', KEYS[1]) == ARGV[1] then " +
                "return redis.call('DEL', KEYS[1]) " +
                "else return 0 end");
        script.setResultType(Long.class);
        return script;
    }

    public static class CacheBusyException extends RuntimeException {
        public CacheBusyException(String message) {
            super(message);
        }
    }
}
```

Điểm nổi bật:

- Đọc cache trước để tránh chi phí lock trên đường hit.
- `setIfAbsent(lockKey, token, duration)` tương đương ý tưởng `SET NX` kèm thời hạn lease.
- **Double-check** sau khi giành lock tránh thực hiện truy vấn nguồn khi value đã xuất hiện.
- Chỉ request giữ lock mới gọi nguồn; request khác chờ rồi đọc lại Redis.
- Sử dụng token riêng và Lua compare-delete để tránh xóa lock của request khác.
- Thời gian chờ có giới hạn; thay vì cùng đổ về database sau một timeout, ví dụ ném lỗi có ý nghĩa để tầng API quyết định trả `503` hoặc fallback.

### 9.3. Đây là ví dụ phối hợp, không phải distributed lock bảo đảm tuyệt đối

Có nhiều giới hạn cần thiết kế bổ sung trước khi dùng cho nghiệp vụ quan trọng:

1. Nếu tải nguồn mất **lâu hơn 15 giây**, lease hết hạn, instance khác có thể giành lock và tải cùng key; khi đó có thể lại có hai loader.
2. Một loader cũ hoàn thành sau loader mới có thể ghi đè dữ liệu mới bằng kết quả cũ. Redis lease một mình **không bảo vệ thứ tự version của dữ liệu**.
3. Redis failover/replication có thể khiến trạng thái lock không còn như kỳ vọng của cả hai phía.
4. Nếu Redis lỗi sau khi nguồn đã tải nhưng trước khi cache được ghi, caller có thể nhận lỗi; không được retry nguồn vô hạn.
5. Nếu nguồn trả `null` hoặc exception, follower không thấy cache key được tạo và có thể chờ hết deadline. Cần negative caching hoặc tín hiệu thất bại nếu bài toán gặp nhiều key không tồn tại.
6. `Thread.sleep` giữ thread HTTP đang chờ. Dưới tải lớn, cách này có thể làm cạn thread pool; ứng dụng reactive nên dùng cơ chế không chặn phù hợp và tuyệt đối tránh `block()` trên event loop.
7. Ví dụ không có cơ chế gia hạn lock. Nếu cần lease dài hơn, phải gia hạn có kiểm tra token hoặc thiết kế giới hạn thời gian tải nguồn và phục hồi khi lease hết.
8. Kết quả trả về sau khi ghi cache vẫn phải tuân theo yêu cầu freshness và authorization của ứng dụng.

**Nguyên tắc:** Redis lock để chống stampede là cơ chế tối ưu tải, không nên đồng thời được dùng làm khóa nhất quán tuyệt đối cho thanh toán, ghi nhận số dư hoặc quyết định stock cuối cùng.

## 10. Độ dài lease, token và fencing: vì sao lock có thể hết hạn khi loader còn chạy?

Xét hai instance:

```text
10:00:00  A lấy lock, TTL 10s
10:00:01  A bắt đầu gọi database nhưng bị chậm
10:00:10  Lock của A hết hạn
10:00:11  B lấy lock mới và gọi database
10:00:12  B ghi cache với phiên bản dữ liệu mới
10:00:15  A hoàn thành và ghi cache bản cũ
```

Lua unlock theo token giúp **A không xóa lock của B**, nhưng chưa ngăn **A ghi dữ liệu stale vào data key**. Hai vấn đề này khác nhau:

- **Ownership của lock:** ai được phép giải phóng/gia hạn lock?
- **Thứ tự ghi kết quả:** dữ liệu từ loader nào còn hợp lệ để ghi vào cache?

Các hướng xử lý tùy mức độ rủi ro:

- Chọn lease dài hơn **thời gian tải nguồn p99** trong điều kiện bình thường, kèm timeout cho lệnh gọi nguồn.
- Gia hạn lease khi thực sự cần và chỉ khi token vẫn trùng. Không tự gia hạn vô hạn.
- Dùng **version nguồn** (ví dụ số phiên bản bản ghi hoặc timestamp đơn điệu đáng tin) và chỉ ghi cache khi version mới không cũ hơn version hiện tại.
- Dùng fencing token do một bộ cấp số tăng đơn điệu đáng tin cậy và hệ nhận ghi thực sự kiểm tra token. Chỉ tạo token mà bên lưu không kiểm tra **không có tác dụng fencing**.
- Với dữ liệu cache chấp nhận stale ngắn, có thể để TTL giải quyết độ cũ nhưng phải hiểu nguy cơ ghi đè; với dữ liệu cần nhất quán mạnh, hãy thay đổi thiết kế cập nhật hoặc nguồn sự thật.

Không chọn `lock TTL = 5 giây` chỉ vì “thường database nhanh”. Phải tính kết nối, GC pause, timeout, tải cao và failover.

## 11. Stale-while-revalidate: trả dữ liệu cũ khi đang tải bản mới

Trong nhiều hệ thống, người dùng chấp nhận thông tin danh mục cũ thêm một hoặc hai phút để đổi lại API phản hồi ổn định. Khi đó có thể dùng **logical TTL** thay vì để Redis xóa hoàn toàn dữ liệu ngay khi cần refresh.

Một entry mang cả nội dung và hạn logic:

```json
{
  "value": {
    "id": "p-100",
    "name": "Wireless Mouse",
    "price": 199000
  },
  "refreshAfterEpochMs": 1780000000000,
  "hardExpireAtEpochMs": 1780000120000,
  "version": 42
}
```

Đây là **ví dụ định dạng**, không phải payload bắt buộc của Spring Data Redis. Các timestamp ở đây minh họa hai mốc; trong ứng dụng thực tế phải tính từ thời gian hiện tại và có chính sách đồng hồ/độ lệch đồng hồ phù hợp.

- Trước `refreshAfterEpochMs`: dữ liệu **fresh**, trả trực tiếp.
- Sau `refreshAfterEpochMs` nhưng trước `hardExpireAtEpochMs`: dữ liệu **stale nhưng còn trong thời hạn cho phép**; có thể trả ngay và chỉ một worker thực hiện refresh.
- Sau `hardExpireAtEpochMs`: dữ liệu **không được phép phục vụ nữa**, request cần chờ tải mới hoặc xử lý lỗi/fallback.

Redis key TTL vật lý phải được đặt đủ dài để giữ entry trong cửa sổ stale, nhưng không dài hơn chính sách lưu trữ cần thiết. Ví dụ refresh logic sau 5 phút, cho phép stale tối đa 2 phút, Redis TTL vật lý khoảng 7 phút hoặc được thiết kế tương ứng.

### 11.1. Luồng đọc với soft TTL và hard TTL

```text
          GET cache:product:p-100
                    |
              +-----+-----+
              |           |
           Không có      Có entry
              |           |
              v           v
       Cold miss flow   Kiểm tra mốc thời gian
                          |
                +---------+---------+
                |         |         |
             Fresh      Stale     Quá hard TTL
                |         |         |
                v         v         v
            Trả ngay   Trả bản cũ  Không trả stale
                         |           |
                         v           v
                    Thử giành    Chờ/tải mới có
                    refresh lock  kiểm soát
                         |
                   +-----+-----+
                   |           |
                 Leader      Follower
                   |           |
                   v           v
              Refresh nền   Không gọi nguồn
                   |
                   v
              Ghi bản mới
```

Đặc tính quan trọng: với entry stale vẫn còn dùng được, request follower **không phải chờ** database; nó nhận bản cũ trong một cửa sổ đã được nghiệp vụ chấp nhận.

### 11.2. Mẫu giả mã triển khai

```text
read(key):
    entry = redis.get(key)

    if entry exists and now < entry.refreshAfter:
        return entry.value

    if entry exists and now < entry.hardExpireAt:
        if tryAcquireRefreshLease(key):
            scheduleRefreshWithoutBlockingRequest(key, entry.version)
        return entry.value

    // Không có entry hoặc đã vượt hạn cứng.
    return loadThroughSingleFlightOrLock(key)
```

Phần `scheduleRefreshWithoutBlockingRequest` phải dùng executor/queue có giới hạn và chính sách xử lý lỗi. **Không tạo một thread mới cho mỗi request stale**. Nếu chỉ có một Redis lock nhưng mỗi request vẫn xếp một task refresh vào executor, hàng đợi có thể tăng dù tác vụ sau đó không lấy được lock; nên khử trùng lặp ở tầng scheduling hoặc thử lock trước.

### 11.3. Những điều kiện không được dùng stale

Không dùng stale-while-revalidate khi dữ liệu cũ có thể gây hậu quả không chấp nhận được, ví dụ:

- Quyền truy cập vừa bị thu hồi.
- Tài khoản đã bị khóa.
- Giá thanh toán cuối cùng chưa được xác nhận ở nguồn.
- Dữ liệu ảnh hưởng trực tiếp tới quyết định giao dịch không có cơ chế kiểm tra lại.

Dữ liệu stale cần gắn giới hạn thời gian rõ ràng và, nếu hữu ích, metadata quan sát như `dataAgeSeconds`. Đừng biến hard TTL thành “phục vụ stale mãi cho đến khi nguồn hồi phục” nếu nghiệp vụ chưa cho phép điều đó.

## 12. Refresh-ahead và prewarming cho hot key

Một cách khác là **không chờ entry hết hạn rồi mới tải lại**.

- **Refresh-ahead:** khi entry còn ít TTL hoặc đã qua một mốc soft TTL, chủ động tải bản mới.
- **Scheduled warming:** một job định kỳ nạp trước những key được dự báo có lưu lượng cao.
- **Event-driven invalidation/refresh:** khi nguồn thay đổi, phát sự kiện để làm mới cache.

Ví dụ danh mục sản phẩm có những key được truy vấn thường xuyên:

```text
cache:product:p-hot-1
cache:product:p-hot-2
cache:product:p-hot-3
```

Một job có thể quét danh sách hot key đã biết rồi refresh từng lô, với concurrency được giới hạn. Tránh quét `KEYS *` trên Redis production để “tìm mọi khóa nóng”; nên dùng danh sách top-key từ metric truy cập hoặc một registry riêng.

Đối với refresh-ahead, cần giải quyết:

1. **Làm sao xác định key đáng refresh?** Không refresh mọi key ít được sử dụng.
2. **Bao nhiêu key được refresh song song?** Giới hạn để không biến job thành tải nền quá lớn.
3. **Nếu refresh thất bại?** Có tiếp tục phục vụ stale trong giới hạn không?
4. **Nếu hai instance cùng chạy scheduler?** Dùng ownership/lease phù hợp.
5. **Khi nguồn có event thay đổi?** Đảm bảo refresh không ghi đè phiên bản mới bằng dữ liệu đọc trước event.

Refresh-ahead thường giảm số lần cold miss, nhưng vẫn cần fallback khi cache trống vì deploy mới, Redis bị evict hoặc failover.

## 13. Negative caching: chống dồn tải cho key không tồn tại

Nếu `productStore.findById("missing-id")` luôn trả `null`, cách cache thông thường có thể **không lưu kết quả miss**. Những request tiếp theo lại truy vấn nguồn.

Một chiến lược là lưu một **sentinel** hoặc DTO kết quả “not found” với TTL ngắn:

```text
cache:product:v1:p-404
    -> {"found":false}
    -> TTL 15 giây
```

Các quy tắc:

- Phân biệt “không tồn tại” với “nguồn lỗi” hoặc “không có quyền truy cập”.
- TTL negative nên ngắn nếu bản ghi có thể sớm được tạo.
- Khi entity được tạo hoặc trạng thái thay đổi, chủ động xóa/ghi lại negative cache.
- Không cache dữ liệu từ response 5xx hoặc timeout như một kết quả “không tồn tại”.
- Giới hạn số key lạ để tránh người dùng hoặc bot tạo vô hạn sentinel.

Trong ví dụ distributed lock ở phần trước, leader trả `null` nhưng không ghi gì vào Redis. Những follower chờ cache cũng sẽ không thấy value; nếu luồng này phổ biến, có thể dùng negative sentinel để leader thông báo kết quả miss cho follower và tránh lặp truy vấn.

**Spring Cache `unless = "#result == null"`** sẽ ngăn caching null. Nếu muốn negative caching, cần thiết kế cụ thể cách lưu null/Optional hoặc một DTO bọc kết quả, đồng thời kiểm tra khả năng serializer/cache manager hỗ trợ.

## 14. Giới hạn đồng thời, timeout và backpressure

Single-flight và lock có thể giảm truy vấn trùng cho **cùng một key**, nhưng không giải quyết được việc hàng nghìn key khác nhau cùng miss. Ví dụ khi Redis bị xóa sạch, mọi key đều khác nhau và đều cần database.

Vì vậy, cần thêm **giới hạn tổng số loader**:

```text
Tổng cache miss
     |
     v
Semaphore / bulkhead (ví dụ tối đa 30 DB loaders)
     |
  +--+----------------+
  |                   |
Được cấp slot       Không có slot
  |                   |
  v                   v
Gọi database       Chờ ngắn / stale /
có timeout         503 / fallback
  |
  v
Ghi cache
```

Mẫu Java minh họa:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public class LoadBulkhead {

    private final Semaphore slots = new Semaphore(30);

    public <T> T withPermit(Supplier<T> loader) {
        boolean acquired;
        try {
            acquired = slots.tryAcquire(100, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }

        if (!acquired) {
            throw new IllegalStateException("Cache source is busy");
        }

        try {
            return loader.get();
        } finally {
            slots.release();
        }
    }
}
```

`30` và `100 ms` chỉ là tham số ví dụ. Cần chọn theo sức chịu tải database, thời gian gọi nguồn, số instance và SLO của endpoint.

Khi kết hợp nhiều kỹ thuật, nên đặt bulkhead ngay trước thao tác **thật sự gọi nguồn**, không giới hạn mọi cache hit. Nếu một request chờ lock mà vẫn chiếm slot bulkhead, các loader thật có thể bị chặn bởi chính follower.

Ngoài semaphore:

- Giới hạn số request đang chờ (queue length) và deadline.
- Dùng timeout nguồn ngắn hơn timeout API tổng.
- Bật circuit breaker khi database/API gặp lỗi liên tục.
- Dùng retry có giới hạn, backoff với jitter; không retry dồn đồng loạt.
- Với API reactive, dùng concurrency control không chặn event loop.
- Khi cache server ngừng hoạt động, quyết định fail-open sang nguồn hay fail-closed theo rủi ro quá tải và tính quan trọng của dữ liệu.

## 15. Cache expiration và eviction không giống nhau

Trong Redis:

- **Expiration:** key bị xóa khi TTL hết hạn.
- **Eviction:** Redis loại bỏ key theo chính sách `maxmemory-policy` khi chịu áp lực bộ nhớ.
- **Explicit invalidation:** ứng dụng gọi `DEL` hoặc Spring Cache eviction khi dữ liệu gốc đổi.

Một request chỉ nhìn thấy miss không thể tự phân biệt chính xác các nguyên nhân nếu không có metric hoặc thông tin phụ trợ. Chống stampede cần bao phủ cả ba:

| Nguyên nhân miss | Hành vi nên cân nhắc |
|---|---|
| TTL của hot key vừa hết | Single-flight/lease, stale-while-revalidate, refresh-ahead |
| Redis eviction do thiếu bộ nhớ | Giảm kích thước value, tối ưu cache policy, giữ bulkhead |
| Triển khai mới khiến cache cold | Prewarm và giới hạn nạp theo lô |
| Database vừa cập nhật và evict cache | Load mới có phối hợp, không phục vụ stale nếu bị cấm |
| Redis outage | Circuit breaker, hạn chế tải nguồn, fallback theo chính sách |
| Key không tồn tại | Negative caching và validation |

Tăng TTL để né stampede có thể giúp giảm tần suất miss nhưng cũng làm tăng độ cũ dữ liệu và chiếm bộ nhớ. Chỉ tăng TTL khi phù hợp freshness, không coi đây là biện pháp thay thế coordination.

## 16. Bài toán Spring Cache: chọn sync=true hay distributed lease?

Nếu ứng dụng dùng `@Cacheable` với `RedisCacheManager`, có thể thử `sync = true` vì ít mã hơn. Nhưng cần xác nhận mức phối hợp ở **đúng phiên bản Spring Data Redis và RedisCacheWriter**.

### 16.1. Trường hợp đơn giản

```java
@Cacheable(
        cacheNames = "catalogDetail",
        key = "#p0",
        sync = true)
public CatalogDetail getDetail(String productId) {
    return source.loadDetail(productId);
}
```

Ứng dụng có ít instance, nguồn chịu được một số lần tải trùng hiếm gặp, và kết quả đo chứng minh cấu hình cache thực tế đã giảm đồng thời đủ tốt. Khi đó, giải pháp annotation có thể phù hợp.

### 16.2. Khi nào cần cơ chế phối hợp minh bạch?

Cân nhắc một flow dùng Redis lease/soft TTL riêng khi:

- Có nhiều replica với cùng hot key.
- Nguồn chịu tải kém, một đợt stampede có thể gây sự cố.
- Cần điều chỉnh chính xác thời gian follower chờ hay phục vụ stale.
- Muốn ghi metric lock owner, số follower, refresh time và stale response.
- Cần phân biệt soft TTL/hard TTL hoặc TTL per-entry không phù hợp cách cấu hình hiện có.
- Cần tránh các key độc lập bị khóa lẫn nhau do phạm vi khóa quá rộng.

**Đừng xếp chồng các cơ chế khóa mà không hiểu tác động:** vừa `@Cacheable(sync = true)`, vừa Redis lock thủ công, vừa single-flight cục bộ có thể tạo nhiều tầng chờ và khó debug. Mỗi lớp phải có vai trò cụ thể, thứ tự deadline và metric rõ ràng.

### 16.3. Self-invocation vẫn là bẫy

Với Spring Cache dùng proxy, lời gọi từ một method vào method khác **trong chính bean** thường không đi qua cache advice:

```java
@Service
public class CatalogService {

    @Cacheable(cacheNames = "catalogDetail", key = "#p0", sync = true)
    public CatalogDetail getDetail(String id) {
        return source.loadDetail(id);
    }

    public CatalogDetail exportOne(String id) {
        return getDetail(id); // self-invocation: có thể bypass cache advice.
    }
}
```

Giải pháp dễ hiểu là tách `getDetail` sang một Spring bean được inject ở service gọi. Nếu proxy không được áp dụng, `sync = true` cũng không có tác dụng.

## 17. Invalidation khi dữ liệu nguồn thay đổi

Stampede thường được nhắc đến khi TTL hết hạn, nhưng **một thao tác invalidation** cũng có thể tạo miss đồng loạt. Ví dụ sau khi cập nhật sản phẩm hot, hệ thống gọi:

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void updateProduct(String id, UpdateCommand command) {
    productStore.update(id, command);
}
```

Ngay sau khi evict, hàng trăm request có thể cùng hỏi ID đó. Vẫn cần một đường reload có phối hợp.

Có hai mâu thuẫn cần giải quyết:

1. **Độ mới:** không phục vụ bản cũ sau khi dữ liệu đã thay đổi nếu nghiệp vụ không cho phép.
2. **Tải:** không để mọi request đi vào nguồn trong cùng cửa sổ reload.

Một số lựa chọn:

- Sau commit, write-through cache bằng bản mới nếu có thể tính/đọc đúng value.
- Phát event invalidation kèm version rồi refresh theo single-flight.
- Tạm thời dùng stale trong giới hạn cho phép, nhưng **không** dùng stale bị vô hiệu hóa do thay đổi nhạy cảm.
- Với API có nhiều cache phụ thuộc, xác định tất cả key bị ảnh hưởng, tránh một phần còn stale lâu hơn dự kiến.
- Dùng key version để tránh loader cũ ghi đè bản mới.

Chỉ đặt TTL rất dài và không invalidation có thể giảm miss nhưng đánh đổi bằng dữ liệu cũ không kiểm soát.

## 18. Thử nghiệm tải: đánh giá chống stampede bằng số lần gọi nguồn

Đo hiệu năng cache bình thường khi hit rate cao chưa đủ. Phải **tạo ra tình huống nhiều yêu cầu miss cùng một key**.

### 18.1. Kịch bản đo

Chuẩn bị một key thử nghiệm `p-hot` và một endpoint tải dữ liệu từ nguồn có độ trễ giả lập đủ ổn định. Chạy nhiều instance ứng dụng nếu hệ thống production dùng nhiều instance.

Các bước:

1. **Warm cache:** nạp `p-hot` rồi xác nhận các request hit không truy vấn nguồn.
2. **Cold burst:** xóa đúng key thử nghiệm và phát 100–1.000 request đồng thời.
3. **Expiration burst:** đặt TTL ngắn có kiểm soát để nhiều request đến khi entry vừa hết hạn.
4. **Slow source:** tăng độ trễ truy vấn nguồn để quan sát cửa sổ miss.
5. **Leader failure:** làm loader nhận exception hoặc timeout; quan sát follower có dồn truy vấn hay không.
6. **Lease expiry:** cho thời gian tải lâu hơn lease; quan sát xuất hiện loader thứ hai và nguy cơ ghi đè.
7. **Redis outage:** kiểm tra ứng dụng bảo vệ database như thế nào.
8. **Multiple-key miss:** cùng miss nhiều key khác nhau để đánh giá bulkhead, không chỉ single-flight.

### 18.2. Chỉ số cần theo dõi

| Metric | Câu hỏi cần trả lời |
|---|---|
| `cache_hit_total` / `cache_miss_total` | Mức độ miss và hit thay đổi thế nào? |
| `source_load_total` gắn với key/category | Một burst tạo bao nhiêu lần gọi nguồn thực? |
| `inflight_loads` | Bao nhiêu loader đang tải đồng thời? |
| `coalesced_requests_total` | Bao nhiêu request dùng chung kết quả của leader? |
| `lock_acquired_total` / `lock_contended_total` | Bao nhiêu lần lấy lock thành công, bao nhiêu lần cạnh tranh? |
| `lock_wait_duration` | Follower chờ bao lâu? |
| `lock_lease_expired_total` | Loader có vượt thời gian lease không? |
| `stale_served_total` và `data_age_seconds` | Có bao nhiêu lần trả dữ liệu cũ, cũ đến mức nào? |
| `source_load_duration` p50/p95/p99 | Loader chậm có kéo dài cửa sổ miss không? |
| `source_bulkhead_rejected_total` | Bao nhiêu request bị từ chối để bảo vệ nguồn? |
| `cache_reload_error_total` | Tỷ lệ lỗi của reload và khả năng phục hồi |
| Redis memory/evictions/command rate | Có tăng tải Redis hoặc bị evict ngoài dự kiến? |

Đặt ngưỡng theo mục tiêu nghiệp vụ. Ví dụ nếu có 500 request đồng thời tới **một key**, mục tiêu có thể là chỉ 1–vài lần gọi nguồn trong cửa sổ tải; con số thật tùy phạm vi coordination, lease và lỗi, không nên lấy một con số tuyệt đối làm lời hứa kiến trúc khi chưa thử nghiệm.

### 18.3. Quan sát Redis

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

`INFO` là số liệu toàn instance, không tự phân biệt cache miss của một endpoint. `SLOWLOG` tập trung thời gian xử lý lệnh phía Redis, không bao gồm thời gian chờ nguồn dữ liệu. Chống stampede thành công có thể tạo **nhiều lần đọc Redis hơn** do follower polling, nhưng **ít lần query database hơn**; cần xem tổng thể thay vì chỉ số lệnh Redis.

Nếu muốn theo dõi lock bị giữ quá lâu, có thể khảo sát TTL của một lock key cụ thể trong môi trường phù hợp:

```bash
redis-cli PTTL 'lock:cache:product:v1:p-hot'
```

Không cần dùng `MONITOR` liên tục trên Redis production bận rộn để đo toàn bộ command; công cụ này tạo tải và có nguy cơ lộ dữ liệu lệnh.

## 19. Các mẫu thiết kế và chi phí đánh đổi

| Kỹ thuật | Giảm cùng tải một key? | Qua nhiều instance? | Độ trễ follower | Đánh đổi chính |
|---|---|---|---|---|
| TTL jitter | Không bảo đảm | Có tác dụng trên lịch hết hạn | Không thay đổi cách miss | Giảm avalanche hơn là stampede đơn-key |
| `@Cacheable(sync = true)` | Có thể, theo cache provider | Không mặc định bảo đảm toàn cluster | Có thể chờ loader | Phụ thuộc implementation/phạm vi khóa |
| Local single-flight | Có trong JVM | Không | Chờ future leader | Không bảo vệ giữa replica |
| Redis lease/lock | Có khi lease còn hiệu lực | Có thể, trên Redis được chia sẻ | Chờ có giới hạn hoặc fallback | Quản lý lease, token, lỗi và version |
| Stale-while-revalidate | Có, do follower trả stale | Có nếu hợp đồng refresh phối hợp | Thường rất thấp | Phải cho phép dữ liệu cũ |
| Refresh-ahead/prewarm | Giảm cơ hội xảy ra miss | Có nếu job được điều phối | Thấp khi warm thành công | Tải nền và lịch refresh |
| Negative caching | Giảm miss cho dữ liệu không tồn tại | Có khi lưu Redis chung | Thấp sau sentinel được tạo | Có nguy cơ trả “không tồn tại” trong thời gian TTL |
| Bulkhead/queue limit | Bảo vệ tổng nguồn | Theo phạm vi triển khai | Có thể từ chối/chờ | Không tự sinh ra cache hit |

Khi tổ chức nhiều lớp, nên thống nhất deadline:

```text
HTTP timeout tổng:      1.000 ms
Redis cache GET:           50 ms (ngân sách minh họa)
Chờ lock tối đa:          300 ms
Nguồn tải tối đa:         500 ms
Bộ đệm xử lý/serialize:   phần còn lại
```

Những con số trên chỉ minh họa cách phân bổ; timeout thực tế phụ thuộc hạ tầng. Không đặt ba timeout độc lập mỗi cái 2 giây rồi kỳ vọng endpoint đáp ứng SLO 1 giây.

## 20. Tình huống vận hành: 8 instance và một sản phẩm rất nóng

Một ứng dụng chạy 8 instance, dùng Redis cache cho sản phẩm `p-top`. Một lúc có 800 request gần như đồng thời. Database cần 150 ms để tải sản phẩm.

### Thiết kế A — Chỉ cache-aside thông thường

```text
800 request -> cùng thấy MISS
            -> nhiều request tự query database
            -> gần như cùng SET cache
```

Số truy vấn nguồn có thể tăng rất cao nếu nhiều request vào cửa sổ miss trước khi cache được ghi. Database dễ quá tải; thời gian tải càng chậm thì số request chồng lên càng nhiều.

### Thiết kế B — Local single-flight trên từng instance

```text
800 request
  |
  +-- Instance 1 -> một loader, follower chờ
  +-- Instance 2 -> một loader, follower chờ
  ...
  +-- Instance 8 -> một loader, follower chờ
```

Nếu request phân phối đều và mỗi instance gom thành công các miss cùng key, số query nguồn trong cửa sổ có thể giảm từ rất nhiều xuống khoảng **8 lần**. Nhưng nhiều instance vẫn tải trùng nhau.

### Thiết kế C — Redis lease theo key + recheck cache

```text
800 request
  |
  +-- Nhiều instance thấy MISS
         |
         +-- Một instance giành lease
         |      |
         |      +-- đọc lại cache
         |      +-- query database
         |      +-- SET cache
         |      +-- release lock theo token
         |
         +-- Các instance còn lại chờ ngắn và GET lại
```

Ở điều kiện bình thường, có thể giảm gần về một lần tải nguồn cho một chu kỳ miss. Nhưng nếu lease hết hạn sớm, nguồn lỗi, process chết hoặc Redis failover, nhiều loader vẫn có thể xảy ra. Đây là **mục tiêu giảm tải**, không phải chứng minh exactly-once.

### Thiết kế D — Stale-while-revalidate

Khi đến mốc soft TTL:

```text
800 request -> đọc được entry stale trong giới hạn
             -> trả ngay cho client
             -> một leader refresh nền
             -> cập nhật cache khi thành công
```

Đường đọc ổn định hơn nếu dữ liệu stale được phép. Đến hard TTL mà chưa refresh thành công, hệ thống phải chuyển sang flow cold miss hoặc trả lỗi/fallback theo chính sách; không phục vụ dữ liệu stale vô hạn.

### Thiết kế tổng hợp gợi ý

- Redis lưu entry với soft/hard TTL cho dữ liệu được phép stale.
- Một cơ chế coordination theo key cho refresh/cold miss.
- TTL jitter để tránh nhiều key cùng rơi vào hard miss.
- Bulkhead cho mọi loader gọi database.
- Negative caching cho ID không tồn tại khi hợp lệ.
- Invalidation khi nguồn thay đổi, kèm bảo vệ không ghi đè phiên bản mới.
- Metric số lần query nguồn cho mỗi burst, thời gian chờ và số response stale.

## 21. Các lỗi dễ gặp khi chống stampede

### 21.1. Dùng Redis lock mà không có TTL

Nếu leader crash, lock tồn tại mãi; mọi follower chờ hoặc lỗi. Phải có lease có thời hạn hoặc cơ chế phục hồi phù hợp.

### 21.2. Xóa lock bằng DEL vô điều kiện

Một request có lock cũ hết hạn có thể xóa lock của request mới. Dùng token và thao tác compare-and-delete nguyên tử.

### 21.3. Không double-check cache sau khi lấy lock

Trong lúc request đợi lấy lock, key đã được người khác nạp. Nếu không đọc lại, ứng dụng có thể query nguồn thừa.

### 21.4. Chỉ có lock mà không có timeout cho follower

Khi leader chậm hoặc chết, follower chờ không giới hạn và có thể làm cạn thread pool. Cần deadline, fallback hoặc trả lỗi có kiểm soát.

### 21.5. Lease ngắn hơn thời gian tải nguồn

Lock hết hạn, loader mới vào; kết quả cũ có thể ghi đè mới. Cần tính p99 loader, renewal có điều kiện và version/fencing khi cần.

### 21.6. Retry nguồn ngay khi không lấy được lock

Mục tiêu lock là tránh mọi request cùng gọi nguồn. Nếu follower không lấy được lock nhưng tự query database ngay, cơ chế chống stampede bị vô hiệu hóa.

### 21.7. Chỉ rải TTL rồi cho rằng đã giải quyết

Jitter giảm đồng loạt giữa **nhiều key**, không chắc giảm stampede của **một key nóng** khi nó hết hạn.

### 21.8. Phục vụ stale cho dữ liệu không được phép cũ

Không dùng stale trong quyết định tài chính, bảo mật hay kiểm soát tồn kho cuối cùng nếu không có quy tắc xác nhận lại.

### 21.9. Tạo một async refresh task cho mỗi request stale

Dù Redis lock cho phép một task refresh nguồn, executor vẫn có thể nhận hàng nghìn task cùng key. Cần khử trùng lặp scheduling và giới hạn queue.

### 21.10. Không phân biệt nguồn trả null và nguồn lỗi

Nếu không cache negative hợp lệ, tất cả request tới ID không tồn tại có thể chờ rồi query lại. Nếu cache timeout như “not found”, ứng dụng sẽ trả thông tin sai cho dữ liệu thực có.

### 21.11. Dựa vào sync=true mà không thử nhiều replica

Phạm vi và mức bảo đảm đồng bộ phụ thuộc provider. Phải đo trên deployment thật, không suy luận từ tên annotation.

### 21.12. Mất Redis thì mở toàn bộ request sang database

Redis outage có thể gây avalanche toàn hệ thống. Nếu mọi request fail-open đồng loạt, database trở thành điểm sự cố thứ hai. Cần bulkhead, rate limit, circuit breaker và lựa chọn degrade phù hợp.

## 22. Quy trình chọn chiến lược

```text
Cache miss xảy ra?
        |
        v
Đây là hot key hay nhiều key cùng miss?
        |
  +-----+-----+
  |           |
Hot key     Nhiều key
  |           |
  v           v
Single-flight/ TTL jitter +
lock theo key  bulkhead/prewarm
  |           |
  +-----+-----+
        |
        v
Có thể trả dữ liệu cũ trong giới hạn?
        |
   +----+----+
   |         |
  Có        Không
   |         |
   v         v
Soft/hard  Chờ loader với
TTL + SWR deadline rõ ràng
   |         |
   +----+----+
        |
        v
Nguồn trả null hoặc lỗi?
        |
   +----+----+
   |         |
  Null      Lỗi
   |         |
   v         v
Negative   Retry giới hạn /
cache có   circuit breaker /
TTL ngắn   không tạo bão tải
   |         |
   +----+----+
        |
        v
Đo số lần gọi nguồn thực,
p95/p99, chờ lock và stale age
```

**Kết luận:** Chống cache stampede không đơn thuần là đặt TTL dài hơn. Trong Spring Data Redis, cần **phối hợp những yêu cầu đang nạp cùng một key**, chọn giới hạn chờ và fallback rõ ràng, đồng thời bảo vệ database khi rất nhiều key cùng miss. `@Cacheable(sync = true)`, single-flight trong JVM, Redis lease, stale-while-revalidate và refresh-ahead là các công cụ với phạm vi và đánh đổi khác nhau. Thiết kế tốt phải giảm số lần gọi nguồn thực, không làm dữ liệu vượt giới hạn độ cũ, không tự retry gây tải lặp và có thể quan sát được khi leader lỗi, lease hết hạn hoặc Redis tạm thời không sẵn sàng.

