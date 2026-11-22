# Bộ nhớ tăng, eviction cao và hiệu năng giảm trong Spring Data Redis

> **Module:** Spring Data Redis  
> **Chương:** Chẩn đoán  
> **Chủ đề:** Phân tích bộ nhớ Redis tăng, eviction cao và độ trễ giảm sút trong ứng dụng Spring Boot; điều tra bằng các chỉ số Redis, Spring Cache, RedisTemplate, Repository, Stream, driver và downstream để chọn giải pháp an toàn.

## 1. Tình huống mở đầu

Một dịch vụ Spring Boot dùng Redis làm cache sản phẩm. Dashboard báo:

~~~text
used_memory:          2.0 GiB -> 7.8 GiB
maxmemory:            8.0 GiB
evictions/sec:        0 -> 4,000
cache hit ratio:      96% -> 60%
DB queries/sec:      400 -> 6,000
HTTP p99:             140 ms -> 1,100 ms
~~~

Có vẻ vấn đề là Redis “hết RAM”, nhưng có ít nhất ba hiện tượng khác nhau:

- **Memory growth:** Redis đang giữ thêm keys/values, metadata, buffers hoặc allocator memory.
- **Eviction:** Redis loại bỏ keys vì memory pressure theo `maxmemory-policy`.
- **Hiệu năng giảm:** Redis trực tiếp chậm, hoặc cache misses tăng khiến database/source API phải làm việc nhiều hơn.

Không phải mọi memory growth đều là leak, không phải mọi eviction đều là lỗi và không phải HTTP chậm nào cũng do Redis thực thi lệnh chậm.

### 1.1. Những câu hỏi phải trả lời

1. Redis này chỉ là cache có thể tái tạo hay có sessions, locks, counters, idempotency hoặc dữ liệu chuẩn?
2. Memory tăng ở dataset hay RSS/allocator/client buffers?
3. Eviction rate tăng ở mọi shards hay một Redis primary?
4. Có keys không TTL, values quá lớn hoặc cache keys gần như không được tái sử dụng?
5. Cache hit ratio thay đổi như thế nào, database fallback tăng bao nhiêu?
6. Redis command p95/p99 tăng, hay chỉ HTTP p95/p99 tăng?
7. Redis maxmemory policy có phù hợp loại dữ liệu không?
8. Gần đây có deploy thay serializer, cache prefix, data model hoặc TTL?

Mục tiêu là tìm **nguyên nhân có bằng chứng**, không phải giảm biểu đồ RAM bằng mọi giá.

## 2. Cơ chế memory pressure gây chậm

~~~mermaid
flowchart TD
    A["Cache key count hoặc value size tăng"] --> B["used_memory gần maxmemory"]
    B --> C["Redis eviction tăng"]
    C --> D["Cache hit ratio giảm"]
    D --> E["DB / upstream fallback tăng"]
    E --> F["HTTP latency tăng"]
    F --> G["Concurrency và retries tăng"]
    G --> E
    B --> H["Server CPU/queue/allocator overhead"]
    H --> F
~~~

Có hai đường ảnh hưởng.

**Đường gián tiếp:** Redis GET vẫn nhanh, nhưng một cache miss phải đọc database trong 300 ms. Khi hot keys bị evicted, miss ratio tăng và database bị quá tải.

**Đường trực tiếp:** Redis server bận xử lý memory eviction, những commands lớn, persistence hoặc CPU/queue backlog; lệnh Redis tại client cũng chậm.

### 2.1. Tác động của hit ratio

Giả sử API có 10.000 requests/giây, mỗi request tra cache một lần:

| Hit ratio | Cache misses/giây |
|---|---:|
| 95% | 500 |
| 80% | 2.000 |
| 60% | 4.000 |

Hit ratio giảm từ 95% xuống 60% làm downstream nhận nhiều misses hơn **8 lần** trong mô hình này.

Các con số chỉ minh họa; thực tế còn local caches, negative caching, request coalescing và nhiều Redis commands/request.

### 2.2. Eviction cao chưa chắc là Redis lỗi

Với Redis chỉ dành cho cache, `allkeys-lru` có thể chủ động loại cold keys để giữ dataset trong memory budget.

Điều cần xem là **keys bị loại có hot không**, cache hits có giảm nghiêm trọng không, downstream có đủ công suất không và các state quan trọng có bị ảnh hưởng không.

## 3. Hiểu các loại bộ nhớ của Redis

Một mô hình:

~~~text
Redis process
├─ Key/value dataset
├─ Key dictionary + expiry metadata
├─ Data structure overhead
├─ Client input/output buffers
├─ Replication buffers
├─ Redis internal structures
├─ Allocator fragmentation / reserved pages
└─ Persistence fork / copy-on-write overhead
~~~

### 3.1. used_memory

`used_memory` là lượng memory theo Redis allocator accounting. Một key chứa value 100 bytes không chỉ chiếm 100 bytes RAM vì còn key name, dictionary entry, metadata, expiry record và allocator alignment.

### 3.2. used_memory_rss

`used_memory_rss` là resident memory của process theo OS. Nó có thể lớn hơn `used_memory` vì allocator fragmentation, retained pages, COW hoặc các loại process overhead.

Nếu `used_memory` giảm nhưng RSS không giảm ngay, không thể kết luận dữ liệu vẫn đang được lưu tại các keys cũ.

### 3.3. mem_fragmentation_ratio

Ví dụ:

~~~text
used_memory:               3.0 GiB
used_memory_rss:           5.0 GiB
mem_fragmentation_ratio:   1.67
~~~

Đây là tín hiệu cần xem allocator, RSS và host metrics. Không dùng một ngưỡng cố định như 1.5 để kết luận “memory leak” cho mọi Redis versions.

Có thể kết hợp `allocator_frag_ratio`, `allocator_rss_ratio` và `MEMORY STATS` nếu version hỗ trợ.

### 3.4. maxmemory không phải giới hạn RSS tuyệt đối

`maxmemory` quyết định Redis cần eviction hoặc trả lỗi OOM theo policy khi memory accounting vượt ngưỡng.

Nó không đảm bảo Redis process RSS luôn nhỏ hơn chính xác giá trị đó. Còn có buffers, allocator fragmentation, persistence/replication overhead và OS/container memory.

Một số versions có `mem_not_counted_for_evict` để giúp phân tích bộ nhớ không được tính vào eviction accounting.

### 3.5. used_memory_dataset và overhead

`used_memory_dataset` giúp ước lượng dataset, còn `used_memory_overhead` giúp hiểu overhead. Không cộng những fields đã bao hàm nhau để tính process total; phải đọc semantics của đúng phiên bản Redis.

### 3.6. Dataset growth và RSS growth khác nhau

Ví dụ:

~~~text
used_memory_dataset:  3.0 -> 3.1 GiB
used_memory:          4.0 -> 4.1 GiB
RSS:                  5.0 -> 7.2 GiB
keys:                 gần ổn định
~~~

Với trường hợp này nên xem fragmentation, OS memory, client buffers và persistence trước khi giảm cache TTL.

## 4. Lệnh Redis đầu tiên nên kiểm tra

Chạy từ môi trường được phép, đúng endpoint và credential:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli INFO clients
redis-cli INFO commandstats
redis-cli INFO cpu
redis-cli INFO persistence
~~~

Redis Cluster phải xem **từng primary**, không chỉ một node hoặc trung bình toàn cluster.

Managed Redis providers có thể giới hạn `CONFIG`, `MEMORY` hoặc diagnostic commands; dùng monitoring được cung cấp nếu cần.

### 4.1. INFO memory

| Field | Ý nghĩa |
|---|---|
| `used_memory` | Memory Redis allocator ghi nhận |
| `used_memory_rss` | Resident memory theo OS |
| `used_memory_peak` | Memory peak |
| `used_memory_dataset` | Dataset memory estimate |
| `used_memory_overhead` | Memory overhead estimate |
| `maxmemory` | Memory eviction limit |
| `maxmemory_policy` | Eviction strategy |
| `mem_fragmentation_ratio` | Chỉ dấu fragmentation |
| `allocator_frag_ratio` | Allocator fragmentation, nếu có |
| `mem_not_counted_for_evict` | Memory bị loại khỏi eviction accounting, nếu có |
| `lazyfree_pending_objects` | Đối tượng đang chờ free nền |

Các field phụ thuộc Redis version; không phải field nào cũng tồn tại trên mọi instance.

### 4.2. INFO stats

Thường có:

~~~text
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
total_commands_processed
instantaneous_ops_per_sec
rejected_connections
~~~

`evicted_keys` và `expired_keys` thường là **counters tích lũy**, không phải rate hiện tại.

### 4.3. Tính evictions/sec

Ví dụ:

~~~text
T1: evicted_keys = 120000
T2 sau 60s:     = 150000
~~~

\[
\text{evictions/sec}=\frac{150000-120000}{60}=500
\]

Nếu Redis restart, counters có thể reset. Khi tính rate cần phát hiện reset và xử lý đúng time window.

### 4.4. INFO keyspace

Ví dụ:

~~~text
db0:keys=2000000,expires=800000,avg_ttl=600000
~~~

Khoảng 40% keys có expiration, nhưng chưa thể kết luận 60% còn lại bị leak. Có thể đó là state chuẩn, secondary indexes hoặc keys cần giữ lâu.

Phải phân loại **theo namespace/owner**.

### 4.5. INFO clients

Số lượng clients và output buffers có thể giải thích memory tăng dù key count ổn định. Một Redis client đọc response rất lớn nhưng xử lý chậm khiến Redis giữ pending bytes trong buffer.

## 5. MEMORY STATS, MEMORY USAGE và MEMORY DOCTOR

~~~bash
redis-cli MEMORY STATS
redis-cli MEMORY DOCTOR
redis-cli MEMORY USAGE app:prod:cache:product:101
~~~

### 5.1. MEMORY STATS

Hỗ trợ phân tích dataset, overhead, allocator, fragmentation và buffers theo Redis version.

### 5.2. MEMORY USAGE

Đo footprint của một key. Với collections Redis có thể dùng sampling khi tính estimate, nên xem tham số `SAMPLES` và cách đo của phiên bản cụ thể.

Không chạy hàng triệu `MEMORY USAGE` calls dồn dập trên production.

### 5.3. MEMORY DOCTOR

Đưa ra gợi ý theo heuristic, không phải công cụ chứng minh nguyên nhân cuối cùng.

### 5.4. Bộ lệnh kiểm tra một key

~~~bash
redis-cli TYPE app:prod:cache:product:101
redis-cli MEMORY USAGE app:prod:cache:product:101
redis-cli PTTL app:prod:cache:product:101
~~~

Nếu key không phải String, không dùng `GET` để cố lấy nội dung của nó.

## 6. Eviction và expiration là hai chuyện khác nhau

### 6.1. Expiration

Key có TTL:

~~~redis
SET cache:product:101 "json" EX 300
~~~

Key sẽ hết hạn theo expiration semantics. Redis có thể xử lý expiration lúc truy cập hoặc qua active expiration sampling.

`expired_keys` tăng cho biết keys hết TTL đã bị loại.

### 6.2. Eviction

Khi Redis gặp memory pressure theo `maxmemory`, nó có thể chọn keys để loại theo `maxmemory-policy`.

`evicted_keys` tăng cho biết keys bị loại vì eviction, không phải chỉ hết TTL.

### 6.3. Bảng so sánh

| Nội dung | Expiration | Eviction |
|---|---|---|
| Nguyên nhân | Hết TTL | Memory pressure |
| Counter | `expired_keys` | `evicted_keys` |
| Cần maxmemory? | Không | Thường có |
| Key chưa hết TTL có thể bị loại? | Không vì expiration | Có nếu policy cho phép |
| Key không TTL bị loại? | Không vì expiration | Có với allkeys policies |
| Có thể tăng cache miss? | Có | Có |

### 6.4. TTL không phải quyền được giữ RAM

Một key được đặt TTL 1 giờ vẫn có thể bị evict sau 5 phút nếu Redis thiếu RAM và policy cho phép.

### 6.5. Expiration nhiều vẫn gây hiệu năng xấu

TTL quá ngắn có thể khiến cache miss thường xuyên. `evicted_keys=0` không có nghĩa cache hiệu quả.

## 7. maxmemory-policy và tập keys đủ điều kiện

| Policy | Keys được xét | Cách chọn |
|---|---|---|
| `noeviction` | Không tự evict | Write tăng memory có thể trả OOM |
| `allkeys-lru` | Tất cả keys | Approximate least recently used |
| `allkeys-lfu` | Tất cả keys | Approximate least frequently used |
| `allkeys-random` | Tất cả keys | Ngẫu nhiên |
| `volatile-lru` | Chỉ keys có TTL | Approximate LRU |
| `volatile-lfu` | Chỉ keys có TTL | Approximate LFU |
| `volatile-random` | Chỉ keys có TTL | Ngẫu nhiên |
| `volatile-ttl` | Chỉ keys có TTL | Ưu tiên TTL còn ngắn |

### 7.1. LRU/LFU không phải thuật toán tuyệt đối

Redis thực hiện lựa chọn dựa trên các cơ chế approximation/sampling. LFU có thể phù hợp dữ liệu được truy cập thường xuyên, nhưng không mặc định tốt hơn LRU mọi workload.

### 7.2. volatile-lru và lỗi OOM

Giả sử:

~~~text
maxmemory:                 8 GiB
keys không TTL:            7.4 GiB
keys có TTL:               0.3 GiB
maxmemory-policy:          volatile-lru
~~~

Khi keys có TTL quá ít hoặc không thể giải phóng đủ, Redis có thể từ chối memory-increasing writes dù vẫn tồn tại nhiều keys không TTL.

Đó không phải lỗi của thuật toán LRU, mà là **không đủ keys eligible**.

### 7.3. allkeys-lru với Redis chỉ làm cache

Có thể phù hợp khi toàn bộ dữ liệu có thể tái tạo và eviction không phá nghiệp vụ. Phải đo cache hit, miss penalty, memory và latency thực tế.

### 7.4. allkeys-lru trên Redis có sessions/locks/idempotency

Nguy hiểm nếu những state quan trọng này không được phép mất. Redis có thể loại chúng giống các cache keys thông thường.

Nên tách Redis cache khỏi canonical/session/queue resources khi retention requirements khác nhau.

### 7.5. noeviction

Không tự loại keys theo memory eviction, nhưng memory-increasing writes có thể trả:

~~~text
OOM command not allowed when used memory > 'maxmemory'
~~~

Ứng dụng phải xử lý thất bại và có capacity plan. `noeviction` không thay persistence/backup.

## 8. Những nguyên nhân làm bộ nhớ tăng

### 8.1. Cache warming bình thường

~~~text
10:00 used_memory 0.6 GiB
10:05 used_memory 2.0 GiB
10:15 used_memory 3.7 GiB
10:30 used_memory 4.0 GiB
10:50 used_memory 4.0 GiB
~~~

Nếu memory đạt plateau, eviction thấp và cache hit tăng, tăng memory là một phần hoạt động bình thường.

### 8.2. RedisTemplate không đặt TTL

~~~java
redis.opsForValue().set("cache:product:" + id, json);
~~~

Nếu không có expiration/lifecycle policy khác, dữ liệu mới có thể tồn tại vô hạn.

### 8.3. TTL quá dài

Cache một search query hiếm lặp với TTL 30 ngày sẽ giữ cold keys chiếm RAM, có thể đẩy hot keys ra khỏi cache.

### 8.4. Key cardinality cao

~~~text
cache:search:desk:request:uuid1
cache:search:desk:request:uuid2
cache:search:desk:request:uuid3
~~~

Nếu thêm request UUID, timestamp hoặc non-canonical query params vào key, có thể mỗi request tạo một key mới.

### 8.5. Big values

Một JSON 5 MiB nhân 10.000 keys đã cần khoảng 48.8 GiB payload chưa tính overhead. Cần đo serialized bytes và key footprint.

### 8.6. Rất nhiều tiny keys

Hàng triệu keys chứa value 20 bytes vẫn tốn metadata, dictionary và allocator overhead. Không tính capacity chỉ bằng value bytes.

### 8.7. Repository secondary indexes

Spring Data Redis Repository có thể thêm index keys, expiration metadata, shadow copies tùy version và config. Entity count không bằng Redis key count.

### 8.8. Redis Streams và collections

Một Stream chỉ `XADD` mà không có retention có thể tăng mãi. Các List/Set/ZSet cũng vậy nếu producer luôn thêm còn consumer/cleanup không theo kịp.

### 8.9. Buffers và RSS

Key count ổn định nhưng memory tăng có thể do client output buffers, replication, persistence hoặc fragmentation.

### 8.10. Cache namespace version overlap

Sau deploy:

~~~text
products:v1::101
products:v2::101
~~~

V1 và V2 tồn tại cùng lúc làm memory tăng tạm thời hoặc lâu dài nếu old keys không TTL/cleanup.

## 9. Tìm big keys và namespaces tăng mạnh

### 9.1. redis-cli --bigkeys

~~~bash
redis-cli --bigkeys
~~~

Dùng để khảo sát kích thước collections/keys. Công cụ vẫn tạo work; chạy khi được phép, có giới hạn tác động và hiểu node scope của Redis Cluster.

### 9.2. Dùng các lệnh cardinality

~~~bash
redis-cli TYPE app:prod:cache:catalog
redis-cli HLEN app:prod:cache:catalog
redis-cli LLEN app:prod:queue:jobs
redis-cli SCARD app:prod:index:products
redis-cli ZCARD app:prod:ranking
redis-cli XLEN app:prod:stream:orders
redis-cli STRLEN app:prod:cache:product:101
~~~

Không dùng `HGETALL` hoặc `LRANGE 0 -1` trên collection rất lớn chỉ để xem size.

### 9.3. Dùng SCAN thay vì KEYS toàn Redis

~~~bash
redis-cli --scan --pattern 'app:prod:cache:*'
~~~

SCAN:

- Không đảm bảo snapshot khi keyspace thay đổi.
- Có thể gặp key lặp.
- COUNT chỉ là hint.
- Có thể phải scan từng primary của Redis Cluster.
- Pattern match raw key bytes, không phải mọi Java logical key.
- Có thể lộ tenant IDs/PII trong key name.

### 9.4. Gắn owner cho namespace

| Namespace | Dữ liệu | Retention | Owner cần kiểm tra |
|---|---|---|---|
| `cache:products:*` | Product DTO | 5–30 phút | Catalog |
| `cache:search:*` | Search results | Ngắn và bounded | Search |
| `session:*` | Login sessions | Theo session lifecycle | Identity |
| `idem:payment:*` | Idempotency | Theo business retention | Billing |
| `stream:orders:*` | Events/work | Retention/ack | Order processor |

Không xóa key chỉ vì tên lạ. Xác định nó thuộc disposable cache hay state không được mất.

## 10. TTL không phải memory quota

### 10.1. Ước lượng số live keys

Khi tạo 1.000 unique keys/giây với TTL 600 giây trong steady-state:

\[
N_{\text{live}}\approx 1000 \times 600 = 600000
\]

Các con số giả định, chưa tính overwrite, expiration, eviction và traffic không đều.

### 10.2. TTL ngắn quá

Tăng cache misses, DB fallback và HTTP p99, dù Redis memory giảm.

### 10.3. TTL dài quá

Giữ nhiều cold keys, tăng memory pressure và có thể làm hot keys bị loại theo eviction policy.

### 10.4. TTL theo freshness và reuse

Nên cân nhắc:

- Data update frequency.
- Maximum tolerated staleness.
- Cost của một cache miss.
- Value size.
- Reuse probability.
- Memory budget.
- Có reliable invalidation sau write không?

### 10.5. TTL jitter

Để tránh nhiều keys expire cùng thời điểm:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public Duration ttlWithJitter() {
    long seconds = ThreadLocalRandom.current()
            .nextLong(480, 601);
    return Duration.ofSeconds(seconds);
}
~~~

Nếu giới hạn freshness là tối đa 600 giây, chọn jitter không vượt 600 giây. Không mặc định cộng thêm jitter vượt SLA.

## 11. Đặt TTL tường minh bằng RedisTemplate

### 11.1. Ghi cache có thời hạn

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductCache {
    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String key, String json) {
        redis.opsForValue()
                .set(key, json, Duration.ofMinutes(10));
    }

    public String read(String key) {
        return redis.opsForValue().get(key);
    }
}
~~~

Code chỉ minh họa. Key cần có namespace/service/tenant scope được xác thực, không tin raw user header.

### 11.2. Đọc TTL

~~~java
Long ttl = redis.getExpire(key, TimeUnit.SECONDS);
~~~

Thông thường:

- `ttl > 0`: key còn thời hạn.
- `ttl == -1`: key tồn tại nhưng không expiration.
- `ttl == -2`: key không tồn tại.

Trong pipeline/transaction context cần xem API return behavior riêng.

### 11.3. Redis Hash

~~~java
redis.opsForHash().put(key, "name", "Desk");
redis.expire(key, Duration.ofMinutes(10));
~~~

TTL truyền thống là **TTL của toàn key Hash**, không tự gắn cho field. Hai calls riêng không atomic, nên khi cần đảm bảo persist+TTL cùng nhau phải thiết kế transaction/script thích hợp.

Một số Redis versions mới có hash field expiration commands, nhưng không giả định Spring Data Redis/Redis deployment nào cũng hỗ trợ API đó.

### 11.4. List, Set, ZSet

`LPUSH`, `SADD` và `ZADD` không tự thêm TTL. Temporary indexes/queues cần retention và cleanup riêng.

## 12. Spring Cache và RedisCacheManager

### 12.1. Spring Cache annotations

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public ProductDto getProduct(String id) {
    return source.load(id);
}
~~~

Thời hạn và serializer do Redis Cache configuration quyết định, không mặc định theo bất kỳ custom RedisTemplate nào trong project.

### 12.2. Spring Boot properties

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
~~~

Ví dụ cho Spring Boot phiên bản phù hợp; cấu hình thực tế có thể bị custom CacheManager override.

### 12.3. TTL khác nhau cho từng cache

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
class RedisCacheConfig {

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .disableCachingNullValues()
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withCacheConfiguration(
                        "products",
                        defaults.entryTtl(Duration.ofMinutes(30)))
                .withCacheConfiguration(
                        "searchResults",
                        defaults.entryTtl(Duration.ofMinutes(2)))
                .build();
    }
}
~~~

Dùng API/config cụ thể theo Spring Data Redis version. TTL thay đổi cho writes mới, không tự migrate mọi key đang tồn tại.

### 12.4. Cache key quá nhiều biến thể

Các query params không ảnh hưởng response không nên góp phần tạo cache key. Nếu cache key chứa trace ID, timestamp hoặc full object không ổn định, Redis có thể tạo hàng triệu unique keys.

### 12.5. @CacheEvict khác Redis eviction

`@CacheEvict` là application xóa một key theo nghiệp vụ. `evicted_keys` là Redis server loại key do memory pressure.

Không dùng counter evicted_keys để đếm những lần Spring `@CacheEvict` chạy.

### 12.6. allEntries=true có thể tạo miss storm

~~~java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearAllProducts() {}
~~~

Trên cache dùng chung, thao tác này có thể clear hàng loạt entries, tạo DB fallback spikes, thậm chí ảnh hưởng nhiều tenants. Cần key-specific invalidation hoặc controlled cleanup.

## 13. Redis Repository và metadata memory

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "products", timeToLive = 600)
public class ProductEntity {
    @Id
    private String id;
    private String name;
}
~~~

`timeToLive` trong ví dụ annotation thường tính bằng giây theo contract Spring Data Redis.

Một Repository có thể tạo ngoài entity Hash:

- Secondary index keys do `@Indexed`.
- Keyspace bookkeeping.
- TTL-related metadata.
- Phantom/shadow copies trong cấu hình expiration events.

Không xem mỗi entity chỉ chiếm một key. Cần đo toàn bộ keyspace và biết data owner.

Nếu Redis Repository lưu **canonical data**, policy `allkeys-lru` có thể không phù hợp vì entity có thể bị mất.

## 14. Redis Streams và Queue data

### 14.1. Stream không có retention

~~~redis
XADD orders:events * type CREATED orderId 101
~~~

Nếu liên tục ghi nhưng không trim, Stream tăng theo thời gian.

Kiểm tra:

~~~bash
redis-cli XLEN orders:events
redis-cli XINFO STREAM orders:events
redis-cli XINFO GROUPS orders:events
redis-cli XPENDING orders:events worker-group
~~~

Xem PEL, consumers và retention trước khi dùng `XTRIM` hay `MAXLEN`. Trim các entries chưa được xử lý có thể ảnh hưởng delivery/replay guarantees.

### 14.2. List và Sorted Set

~~~bash
redis-cli LLEN queue:jobs
redis-cli ZCARD queue:scheduled
~~~

Nếu producer nhanh hơn consumer, length và RAM tăng. TTL trên các cache Strings khác không giúp các collections này.

### 14.3. Pub/Sub khác Stream

Redis Pub/Sub thường không giữ durable history như Streams, nhưng slow subscribers/client output buffers có thể làm memory tăng.

## 15. Serialization và payload bytes

Redis value có thể là JDK bytes, String JSON, generic JSON có `@class`, hoặc binary DTO format. Memory footprint khác nhau theo schema/serializer.

Các yếu tố:

- Class metadata.
- Field names lặp trong JSON.
- Object graph/nested arrays.
- Compression.
- Per-key metadata.
- Hash internal encodings.

Không kết luận JSON luôn nhỏ hơn JDK hoặc ngược lại. Đo raw serialized length và `MEMORY USAGE` trên dữ liệu mẫu.

### 15.1. Giảm big payload

Thay vì cache toàn bộ product catalog khi request chỉ cần tên và giá, cân nhắc:

- Field-level data.
- Pagination.
- Smaller DTO.
- Split aggregates theo access patterns.
- Bounded responses.

### 15.2. Compression có trade-offs

Giảm bytes nhưng tăng CPU decode/encode và độ phức tạp migration. Chỉ áp dụng sau benchmark cả Redis RAM, network, JVM GC và p99.

## 16. Đo cache hit/miss đúng cách

### 16.1. Redis GET có thể nhanh dù HTTP chậm

~~~text
HTTP GET /products/101     500 ms
├─ Redis GET                 2 ms
├─ Cache MISS                0 ms
├─ DB query                450 ms
└─ Response processing      48 ms
~~~

Đây là vấn đề cache hiệu quả giảm hoặc DB fallback, không phải Redis GET server execution chậm.

### 16.2. Micrometer Timer mẫu

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.data.redis.core.StringRedisTemplate;

public class MeasuredRedisCache {

    private final StringRedisTemplate redis;
    private final MeterRegistry registry;

    public MeasuredRedisCache(
            StringRedisTemplate redis,
            MeterRegistry registry) {
        this.redis = redis;
        this.registry = registry;
    }

    public String get(String key) {
        long started = System.nanoTime();
        String outcome = "error";

        try {
            String result = redis.opsForValue().get(key);
            outcome = result == null ? "miss" : "hit";
            return result;
        } finally {
            Timer.builder("app.redis.cache.lookup.duration")
                    .tag("operation", "GET")
                    .tag("outcome", outcome)
                    .register(registry)
                    .record(
                            System.nanoTime() - started,
                            TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Trong production có thể pre-register meters. Không dùng full key, userId hoặc tenantId làm metric labels vì cardinality cao và có thể lộ dữ liệu.

### 16.3. Cache miss khác Redis error

`GET` trả null nghĩa key không tồn tại. Timeout/connection exception không nên bị catch rồi biến thành null một cách vô điều kiện; nếu làm vậy metrics sẽ nhầm Redis outage thành cache miss.

### 16.4. Hit ratio

\[
HitRatio = \frac{\Delta hits}{\Delta hits+\Delta misses}
\]

`keyspace_hits`/`keyspace_misses` từ Redis Server không hoàn toàn trùng application-level Spring Cache hit/miss; Redis counters có thể bao gồm nhiều clients và nhiều commands cho mỗi business request.

## 17. Redis latency vs database fallback

Đo theo tầng:

| Tầng | Công cụ |
|---|---|
| HTTP/API | Actuator metrics, tracing |
| RedisTemplate | Timer quanh operation |
| Lettuce/Jedis | Command latency, connection/pool metrics |
| Redis Server | INFO cpu/commandstats, SLOWLOG, LATENCY |
| Network | Redis PING từ pod, TCP telemetry |
| Database | QPS, query p95/p99, connection wait |
| JVM | GC pause, CPU, heap allocations |

### 17.1. SLOWLOG đo execution

~~~bash
redis-cli SLOWLOG GET 20
~~~

Không đo network RTT hay client queue. SLOWLOG trống không đảm bảo Redis hoàn toàn không bận vì nhiều commands nhanh vẫn có thể gây queueing.

### 17.2. LATENCY events

~~~bash
redis-cli LATENCY LATEST
redis-cli LATENCY DOCTOR
~~~

Latency monitoring có thể cần được bật. Dùng để tìm Redis server stalls như fork, AOF fsync, Lua dài. Không coi đây là end-to-end HTTP timer.

### 17.3. JVM GC và large values

Redis GET value vài MiB có thể làm JVM allocate nhiều bytes/objects, gây GC hoặc chậm deserialize. Đo JFR/GC/CPU cùng Redis latency.

## 18. Cache stampede sau eviction

~~~text
Hot key bị evicted
  -> Pod A: MISS -> DB query
  -> Pod B: MISS -> DB query
  -> Pod C: MISS -> DB query
  -> 1000 requests MISS -> DB quá tải
~~~

### 18.1. Các biện pháp

- Single-flight/coalescing.
- Giới hạn DB fallback concurrency.
- Cache warming.
- TTL jitter.
- Negative caching có TTL phù hợp.
- Soft TTL/stale-while-revalidate nếu nghiệp vụ cho phép.
- Background refresh.
- Bulkhead/circuit breaker.
- Distributed locks có lease/owner semantics khi thực sự cần.

Single-flight trong một pod không tự ngăn các pod khác cũng cùng tải DB. Cần thiết kế theo topology.

### 18.2. Không đổi correctness lấy cache hit

Không phục vụ dữ liệu stale nhạy cảm như số dư, quyền truy cập hoặc tồn kho checkout nếu contract không cho phép.

### 18.3. Retry storms

Retry Redis/DB quá nhiều có thể nhân tải khi đã overload. Dùng bounded retries, backoff và timeout budget. Với Redis writes có side effects, timeout không chứng minh command chưa chạy; cần idempotency.

## 19. Chẩn đoán qua các tình huống

### 19.1. Memory tăng do cache không TTL

~~~text
used_memory tăng hàng ngày
key count tăng
expires/keys thấp
namespace cache:search:* tăng rất nhanh
~~~

Hướng xử lý: tìm writer, sửa TTL/key schema, kiểm tra key reuse, cleanup scoped keys sau khi xác định owner.

### 19.2. Eviction cao và DB fallback cao

~~~text
evictions/sec       3,000
Redis GET p95       2 ms
cache hit ratio     95% -> 60%
DB query p95        150 -> 500 ms
HTTP p99            200 -> 1,200 ms
~~~

Ưu tiên giảm cold key cardinality, tăng cache admission quality, xử lý stampede; tăng RAM nếu hot working set thực sự cần.

### 19.3. volatile-lru nhưng writes OOM

~~~text
maxmemory-policy = volatile-lru
non-TTL keys = gần hết RAM
TTL keys = ít
SET returns OOM
~~~

Nút thắt là eligible eviction set không đủ. Cần phân loại data, đặt TTL cho đúng cache keys, tách state hoặc chọn policy phù hợp mà không làm mất dữ liệu quan trọng.

### 19.4. RSS cao nhưng dataset ổn

~~~text
used_memory 2.0 -> 2.1 GiB
RSS         3.4 -> 5.5 GiB
key count   ổn định
evictions   thấp
~~~

Điều tra fragmentation, allocator, client buffers, persistence/CoW; đừng chỉ điều chỉnh cache TTL.

### 19.5. Redis Cluster hot shard

~~~text
Primary A  95% maxmemory, evictions/sec=2000
Primary B  35% maxmemory, evictions/sec=0
Primary C  42% maxmemory, evictions/sec=0
~~~

Kiểm tra hash tag, hot key/tenant, slot distribution và per-node capacity.

### 19.6. New cache prefix sau deploy

~~~text
products:v1::...
products:v2::...
~~~

Hai keyspaces tồn tại cùng lúc làm memory tăng. Xem rollback window, TTL, cross-version invalidation và cleanup plan.

### 19.7. Redis Stream chưa trim

~~~text
XLEN orders:events tăng hàng triệu entries
XPENDING worker-group tăng
cache key count không đổi nhiều
~~~

Đây là retention/consumer backlog issue, không sửa bằng cách đổi Spring Cache TTL.

## 20. Redis Cluster và memory không cân bằng

Redis Cluster phân keys vào 16.384 hash slots. Một primary có thể memory pressure dù tổng cluster vẫn nhiều RAM.

### 20.1. Hot hash tag

~~~text
cache:{all}:tenant:A:product:101
cache:{all}:tenant:B:product:102
~~~

Cùng tag `all` khiến keys chung slot, dễ tạo hot shard. Thêm primary nodes không tự tách slot đó.

### 20.2. Theo dõi từng primary

Xem:

- used_memory/maxmemory.
- eviction rate.
- CPU/commands/sec.
- Hot slots/key distribution.
- Big key concentration.
- Replication/network overhead.

### 20.3. Rebalancing cũng có chi phí

Chuyển slots/keys tạo network/CPU work và có thể ảnh hưởng latency tạm thời. Cần canary/monitoring khi rebalance.

## 21. Noisy neighbor và multi-tenant

Redis keys có tenant prefix:

~~~text
app:prod:tenant:A:cache:...
app:prod:tenant:B:cache:...
~~~

ngăn collision nhưng không tạo quota RAM/CPU. Tenant B ghi hàng triệu keys có thể khiến hot keys của A bị evicted.

Các lựa chọn:

- Per-tenant rate/write limits.
- Cache value-size bounds.
- TTL/admission policies theo workload.
- Top-N tenant analytics.
- Separate Redis resources cho tenant/workload cần hard isolation.

Không gắn hàng trăm nghìn tenant IDs vào metric labels.

## 22. Big keys và UNLINK

Một big Hash, List, Set hoặc Stream có thể chiếm nhiều RAM và tạo latency khi đọc/xóa.

### 22.1. Đọc giới hạn

Nếu chỉ cần vài fields:

~~~redis
HMGET product:101 name price thumbnail
~~~

Tránh `HGETALL` toàn bộ huge Hash nếu không cần. Dùng pagination/SCAN-like operations khi phù hợp.

### 22.2. UNLINK vs DEL

~~~bash
redis-cli UNLINK app:prod:cache:legacy:big
~~~

`UNLINK` có thể unlink key và xử lý reclaim memory bất đồng bộ, giảm blocking so với một số trường hợp dùng DEL.

Nó không bảo đảm RSS giảm tức thì. Theo dõi `lazyfree_pending_objects` và allocator metrics. Không xóa state không rõ owner.

### 22.3. Không dùng FLUSHALL để chữa cháy

`FLUSHALL` có thể xóa sessions, locks, counters và pending events của services khác, đồng thời gây cache miss storm.

Dùng cleanup theo validated namespace, SCAN/batches và plan có kiểm soát.

## 23. Capacity planning

Một ước lượng đơn giản:

\[
M_{\text{logical}} \approx
N_{\text{live keys}}
\times
(\text{average value bytes}+\text{per-key overhead})
\]

Ví dụ tạo 300 unique keys/giây, TTL 20 phút:

\[
N_{\text{live}}\approx 300 \times 1200 = 360000
\]

Nếu `MEMORY USAGE` samples cho thấy trung bình 1.5 KiB/key:

\[
M\approx 360000\times1.5\ \mathrm{KiB}
\approx 527\ \mathrm{MiB}
\]

Đây là ước lượng để bắt đầu. Cần thêm headroom cho size distribution, Redis overhead, RSS/fragmentation, buffers, replication, persistence/failover và Cluster skew.

### 23.1. Working set khác toàn bộ dataset

Nếu 5% keys được tái sử dụng thường xuyên, giữ các hot keys có thể mang lại hit ratio tốt mà không cần lưu mọi cold key.

Nếu hot working set lớn hơn RAM, eviction liên tục có thể làm miss ratio cao. Lúc đó tăng RAM là hợp lý nếu reuse và miss penalty biện minh.

### 23.2. Tăng RAM không chữa key leak

Nếu mỗi request có UUID mới trong key, số keys có thể tăng vô hạn. Thêm RAM chỉ kéo dài thời gian trước khi đầy.

### 23.3. Headroom cho container/managed Redis

Không đặt `maxmemory` bằng toàn bộ container limit mà không dành chỗ cho allocator, RSS, buffers, replication và persistence. Tính theo deployment/provider docs.

## 24. Runbook production

### Bước 1 — Ghi phạm vi và thời gian

~~~text
Incident: Redis memory/eviction
Window: 10:00-10:30
Shard: primary-2
used/maxmemory: 94%
evictions/sec: 2,500
HTTP p99: 900 ms
DB QPS increase: +350%
~~~

### Bước 2 — Phân loại dữ liệu

Xác định cache, sessions, idempotency, locks, counters, Streams hay canonical state. Không thay policy khi chưa biết keys nào được phép mất.

### Bước 3 — Thu metrics

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli MEMORY STATS
~~~

Lấy snapshots theo thời gian, tính rate từ delta.

### Bước 4 — Kiểm tra maxmemory policy

Xem policy, TTL coverage và lỗi OOM. Đặc biệt kiểm tra `volatile-*` khi phần lớn memory là non-TTL keys.

### Bước 5 — Tìm namespace và big keys

Dùng SCAN/bigkeys với giới hạn, phân theo owner. Không in raw sensitive keys/values vào ticket công khai.

### Bước 6 — Phân biệt dataset với RSS

So used_memory_dataset, used_memory, RSS, fragmentation, client buffers và persistence events.

### Bước 7 — Đo tác động tới ứng dụng

So Redis GET p95/p99, cache hits/misses, DB fallback, HTTP p99, retries và JVM GC cùng time window.

### Bước 8 — Viết giả thuyết có thể bác bỏ

Ví dụ:

> “Mỗi search request sinh key chứa trace UUID và TTL 24 giờ. Khi bỏ UUID và giảm TTL theo data freshness, key creation rate và RAM phải giảm, còn hit ratio cải thiện.”

### Bước 9 — Thay đổi một yếu tố chính

Sửa TTL/key builder/cache admission, giảm big payload, tách critical state, thay policy hoặc scale RAM/shards theo bằng chứng.

### Bước 10 — Đo trước/sau

Xem used_memory, RSS, evictions/sec, key count, hit ratio, DB QPS/p99, Redis command p99, HTTP p99/error rate và tính đúng dữ liệu.

### Bước 11 — Có rollback

Nếu TTL/policy/cache namespace mới gây stale data hoặc tăng DB load, phải có cách quay về mà không xóa canonical state.

## 25. Những sai lầm thường gặp

1. **Redis memory tăng nghĩa là leak.** Có thể là warming, value growth, buffers hoặc fragmentation.
2. **Eviction cao nghĩa Redis command chắc chắn chậm.** Redis GET có thể nhanh nhưng downstream misses mới gây HTTP chậm.
3. **expired_keys và evicted_keys là một.** Chúng phản ánh hai cơ chế khác nhau.
4. **volatile-lru sẽ loại mọi key cũ.** Chỉ keys có TTL eligible.
5. **allkeys-lru luôn tốt.** Có thể loại sessions/locks/idempotency state.
6. **TTL ngắn ngăn đầy RAM chắc chắn.** Unique-key rate cao vẫn có thể làm live key count rất lớn.
7. **Tăng TTL luôn tăng hiệu năng.** Cold keys giữ RAM lâu có thể đẩy hot keys ra.
8. **used_memory và RSS giống nhau.** Allocator/OS accounting khác.
9. **maxmemory bằng OS RAM limit là an toàn.** Không để headroom cho buffers/fragmentation/persistence.
10. **Cluster tổng RAM dư thì mọi nodes đều ổn.** Một primary có thể đầy.
11. **RedisTemplate tự gắn TTL cho mọi cache key.** Không nên giả định.
12. **Spring Cache dùng TTL của RedisTemplate.** RedisCacheConfiguration là cơ chế riêng.
13. **Repository mỗi entity chỉ có một key.** Index/metadata cũng tốn RAM.
14. **UNLINK trả RAM về OS ngay.** Không đảm bảo.
15. **Có thể FLUSHALL để reset cache khi đầy.** Nguy hiểm trên shared Redis.
16. **Retry Redis OOM vô hạn sẽ tự khỏi.** Thường chỉ làm tăng tải.
17. **Tắt persistence để giảm memory là vô hại.** Có thể làm mất recovery guarantees.
18. **Một screenshot RAM đủ để chọn giải pháp.** Cần trends/rates/data classification.

## 26. Câu hỏi thường gặp

**1. Evicted keys tăng có phải Redis bị lỗi không?**  
Không mặc định. Với disposable cache, eviction có thể nằm trong thiết kế. Cần xem hit ratio và SLO.

**2. TTL còn hạn mà key vẫn mất?**  
Redis có thể evict trước TTL do memory pressure, hoặc app có thể delete/overwrite key.

**3. Vì sao có TTL nhưng RAM vẫn tăng?**  
Key creation rate cao, TTL dài, size tăng, các namespaces khác không TTL, buffers hoặc fragmentation.

**4. volatile-lru có thể OOM không?**  
Có nếu không đủ keys có TTL để evict.

**5. noeviction tốt hơn allkeys-lru không?**  
Tùy vai trò dữ liệu. Nó tránh evict nhưng writes có thể fail khi memory đầy.

**6. Vì sao Redis GET nhanh mà HTTP p99 cao?**  
Cache miss tăng có thể khiến database fallback quá tải.

**7. RSS cao hơn used_memory thì có leak không?**  
Chưa đủ bằng chứng. Cần xem fragmentation, allocator, buffers và persistence.

**8. Tại sao maxmemory thấp hơn RSS?**  
Memory accounting khác RSS và còn overhead ngoài dataset.

**9. Spring Cache có TTL tự động không?**  
Tùy RedisCacheManager/Boot configuration. Phải kiểm tra bean và TTL của keys thật.

**10. RedisTemplate.set không truyền Duration thì sao?**  
Đừng giả định key mới có TTL; cần lifecycle/expiration policy rõ và xem overwrite semantics.

**11. Redis Repository có thêm index keys?**  
Có thể. Secondary indexes và expiration metadata cần được tính vào capacity.

**12. Redis Stream có thể tăng không giới hạn?**  
Có nếu retention/trim không phù hợp hoặc producer nhanh hơn consumer. Xem pending work trước khi xóa.

**13. Có nên dùng redis-cli --bigkeys trên production?**  
Chỉ khi được phép và có kiểm soát tác động; công cụ scan vẫn gây load.

**14. Có nên luôn dùng LFU thay LRU?**  
Không. Chọn sau benchmark theo hotness/reuse và miss penalty.

**15. Redis Cluster có thể evict khi tổng RAM còn dư?**  
Có, nếu một primary shard riêng lẻ chạm memory limit.

**16. Tăng RAM có giải quyết hoàn toàn?**  
Chỉ khi working set hợp lệ thiếu capacity. Với key cardinality vô hạn sẽ đầy lại.

**17. Có nên xóa key lớn ngay không?**  
Không trước khi xác định owner và data classification.

**18. Có thể dùng FLUSHALL để giảm eviction?**  
Không trên shared production Redis vì có thể mất state quan trọng và gây cache miss storm.

**19. Cache stampede có liên quan eviction?**  
Có. Mất hot key khiến nhiều requests đồng loạt đọc nguồn chuẩn.

**20. Metrics quan trọng nhất là gì?**  
Không chỉ một metric: used_memory, RSS, evictions/sec, hit ratio, DB fallback, Redis p99 và HTTP p99 cùng nhau.

## 27. Checklist triển khai chẩn đoán

1. **Phân loại dữ liệu Redis** theo cache/critical state.
2. **Xác định SLO** cho Redis, HTTP, cache hit và database fallback.
3. **Lấy INFO memory/stats/keyspace** trên đúng primary.
4. **Tính evictions/sec** từ delta và xử lý counter reset.
5. **Phân biệt expiration và eviction**.
6. **Kiểm tra maxmemory/maxmemory-policy**.
7. **Kiểm tra TTL coverage** theo namespace.
8. **Tìm big keys và millions of tiny keys**.
9. **Đo value bytes/serialization overhead**.
10. **Kiểm tra cache key cardinality**.
11. **Kiểm tra RedisTemplate TTL**.
12. **Kiểm tra RedisCacheConfiguration và @Cacheable**.
13. **Kiểm tra Repository indexes/TTL metadata**.
14. **Kiểm tra Stream/List/ZSet retention**.
15. **So used_memory với RSS/fragmentation/buffers**.
16. **Đo DB miss amplification và cache stampede**.
17. **Giới hạn retries, concurrency và downstream fallback**.
18. **Chọn TTL theo freshness/reuse** và jitter khi hữu ích.
19. **Tách critical state khỏi disposable cache** nếu policy xung đột.
20. **Đo mỗi Cluster primary**, tránh chỉ nhìn aggregate.
21. **Dành headroom cho allocator, replication và persistence**.
22. **Cleanup scoped keys có owner validation**, không FLUSHALL.
23. **Đo trước/sau** trên workload tương đương.
24. **Bảo vệ correctness, tenant isolation và rollback**.

## 28. Tổng kết

**Bộ nhớ Redis tăng, eviction cao và hiệu năng Spring Boot giảm** là một chuỗi dấu hiệu cần được phân tích theo tầng.

- **Memory:** phân biệt dataset/key count/value bytes với RSS, buffers, fragmentation và persistence.
- **Eviction:** xác định keys eligible theo `maxmemory-policy`, không nhầm với TTL expiration.
- **Application:** đo cache hit/miss, database fallback, Redis command latency và HTTP p95/p99 để biết phần nào thật sự chậm.
- **Khắc phục:** sửa key schema/TTL/value size, giới hạn Streams/collections, chọn eviction policy phù hợp, tăng capacity khi working set thật sự cần và chống cache stampede.
- **An toàn:** không evict nhầm sessions/locks/idempotency state, không xóa toàn Redis, không hy sinh freshness, security hoặc durability chỉ để giảm RAM.

Quy trình đáng tin cậy là **đo xu hướng → tìm nguyên nhân theo namespace và data type → thay đổi có kiểm soát → đối chiếu SLO, hit ratio, RAM và tính đúng dữ liệu**.

## Tài liệu tham khảo

- Redis — [Key eviction](https://redis.io/docs/latest/develop/reference/eviction/).
- Redis — [INFO](https://redis.io/docs/latest/commands/info/).
- Redis — [MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/).
- Redis — [MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/).
- Redis — [MEMORY DOCTOR](https://redis.io/docs/latest/commands/memory-doctor/).
- Redis — [TTL](https://redis.io/docs/latest/commands/ttl/).
- Redis — [PTTL](https://redis.io/docs/latest/commands/pttl/).
- Redis — [SCAN](https://redis.io/docs/latest/commands/scan/).
- Redis — [UNLINK](https://redis.io/docs/latest/commands/unlink/).
- Redis — [SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
- Redis — [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/).
- Redis — [Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- Spring Data Redis — [Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- Spring Data Redis — [Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html).
- Spring Data Redis — [Expirations](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html).
- Spring Boot — [Caching](https://docs.spring.io/spring-boot/reference/io/caching.html).
- Spring Boot — [Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
