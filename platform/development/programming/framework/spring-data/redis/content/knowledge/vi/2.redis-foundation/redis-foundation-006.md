# Phân biệt dữ liệu hết hạn với dữ liệu bị loại do thiếu bộ nhớ trong Redis

Khi gọi `GET` và nhận về `nil` (hoặc `null` qua Spring Data Redis), ứng dụng chỉ biết rằng **khóa không còn giá trị có thể đọc được tại thời điểm truy vấn**. Kết quả đó không cho biết vì sao khóa biến mất. Trong Redis, hai nguyên nhân rất dễ nhầm lẫn là:

- **Expiration (hết hạn):** Khóa đã đến hạn sống (`TTL`) do ứng dụng cấu hình.
- **Eviction (loại bỏ vì áp lực bộ nhớ):** Redis chủ động loại bỏ khóa để giải phóng bộ nhớ khi áp dụng giới hạn `maxmemory` và một chính sách eviction cho phép loại bỏ khóa.

Hai cơ chế có thể cùng tác động lên một khóa. Một khóa có TTL 30 phút vẫn có thể bị eviction sau vài giây nếu Redis thiếu bộ nhớ; ngược lại, Redis vẫn cho khóa hết hạn theo TTL ngay cả khi không bật eviction. Đây là khác biệt quan trọng khi xây dựng cache, session, OTP, rate limiter và các hệ thống dùng Spring Data Redis.

## 1. So sánh nhanh hai cơ chế

| Tiêu chí | Expiration — hết hạn | Eviction — loại bỏ do bộ nhớ |
|---|---|---|
| Nguyên nhân | Đến thời điểm hết hạn đã gắn cho khóa | Redis cần giải phóng bộ nhớ theo giới hạn `maxmemory` |
| Cấu hình quyết định | `EX`, `PX`, `EXPIRE`, `PEXPIRE`, `EXPIREAT`, `PEXPIREAT` hoặc TTL của Spring Cache | `maxmemory` và `maxmemory-policy` của Redis Server |
| Khóa nào chịu tác động? | Chỉ khóa có thời gian hết hạn | Tùy policy: toàn bộ khóa (`allkeys-*`) hoặc chỉ khóa có TTL (`volatile-*`) |
| Có cần áp lực bộ nhớ không? | Không | Có, theo cơ chế kiểm soát bộ nhớ của Redis |
| Khóa chưa đến TTL có thể biến mất không? | Không do expiration; vẫn có thể bị xóa theo cách khác | Có |
| Khóa không đặt TTL có bị ảnh hưởng không? | Không do expiration | Có thể, nếu policy là `allkeys-*` |
| Thống kê liên quan | `expired_keys` trong `INFO stats` | `evicted_keys` trong `INFO stats` |
| Ứng dụng đọc sau khi mất khóa | Nhận `nil`/`null` | Cũng nhận `nil`/`null` |

**Điểm mấu chốt:** TTL mô tả *thời hạn tối đa để một giá trị được coi là còn hiệu lực*, chứ không phải cam kết rằng Redis sẽ giữ khóa đó trong bộ nhớ đến đúng thời hạn.

## 2. Expiration: khóa hết hạn theo TTL

### 2.1. Đặt và kiểm tra thời hạn

`TTL` (*time to live*) là số giây còn lại trước khi khóa hết hạn. Redis cũng có `PTTL` để trả về mili giây.

```redis
SET session:1001 "user-1001" EX 120
TTL session:1001
GET session:1001
```

Ở ví dụ này, `session:1001` được đặt thời hạn 120 giây. Sau thời hạn đó, khóa không còn được coi là hợp lệ. Có thể gắn TTL lên khóa đã tồn tại:

```redis
SET report:temp "processing"
EXPIRE report:temp 300
TTL report:temp
```

Các giá trị của `TTL` cần được hiểu chính xác:

| Kết quả | Ý nghĩa |
|---|---|
| Số nguyên `>= 0` | Khóa tồn tại và có TTL; số giây còn lại (làm tròn xuống) |
| `-1` | Khóa tồn tại nhưng không có TTL |
| `-2` | Khóa không tồn tại khi Redis kiểm tra; không nói được nguyên nhân biến mất |

`PTTL` dùng chung quy ước `-1` và `-2`, nhưng trả thời gian còn lại theo mili giây. Đừng suy ra `TTL = -2` đồng nghĩa với *đã hết hạn*: khóa cũng có thể bị `DEL`, `UNLINK`, eviction hoặc chưa từng được tạo.

Lưu ý một thao tác ghi đè như `SET session:1001 "new-value"` thường xóa TTL cũ của khóa. Nếu muốn ghi đè mà giữ nguyên TTL hiện tại, Redis hỗ trợ tùy chọn `KEEPTTL`:

```redis
SET session:1001 "new-value" KEEPTTL
```

`PERSIST session:1001` thì loại bỏ thời hạn, khiến khóa tồn tại không có TTL cho đến khi được xóa bằng cách khác.

### 2.2. Redis xóa khóa hết hạn bằng cách nào?

Redis dùng hai cơ chế bổ sung nhau:

1. **Passive expiration (xóa khi truy cập):** Khi một lệnh truy cập khóa đã quá hạn, Redis phát hiện và xử lý khóa hết hạn, thay vì trả về giá trị cũ.
2. **Active expiration (quét nền):** Redis định kỳ kiểm tra các khóa có TTL và loại bỏ một phần khóa đã quá hạn, kể cả khi không có lệnh nào truy cập chúng.

Vì vậy, **khóa không nhất thiết bị xóa vật lý vào đúng mili giây mà TTL chạm 0**. Redis vẫn không cung cấp giá trị đã hết hạn cho một lần đọc thông thường; nhưng sự kiện hết hạn và việc thu hồi bộ nhớ có thể diễn ra muộn hơn thời điểm hết hạn lý thuyết.

```text
Thời gian  ───────────────────────────────────────────────────►
Tạo khóa          Đến hạn TTL                    Dọn vật lý
   │                   │                              │
   ├── đọc bình thường ┤                              │
   │                   └── khóa không còn hợp lệ ─────┘
   │                      (xóa khi đọc hoặc quét nền)
```

Ví dụ ứng dụng đặt OTP có TTL 3 phút. Khi qua 3 phút, OTP không được chấp nhận nữa dù Redis chưa kịp dọn khóa vật lý trong một vòng quét nền.

## 3. Eviction: Redis chủ động loại bỏ khóa khi thiếu bộ nhớ

### 3.1. `maxmemory` và `maxmemory-policy`

`maxmemory` là ngưỡng bộ nhớ Redis dùng để kiểm soát tiêu thụ bộ nhớ; `maxmemory-policy` quyết định Redis có được loại bỏ khóa và chọn khóa nào khi cần giải phóng bộ nhớ.

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
```

Ví dụ cấu hình dành cho một Redis chuyên làm cache:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

Khi lệnh ghi khiến Redis cần thêm bộ nhớ trong lúc đã chạm/vượt ngưỡng, Redis có thể chọn và loại bỏ các khóa phù hợp với policy để nhường chỗ. Redis không chờ TTL của khóa được chọn hết hạn.

Giới hạn `maxmemory` là cơ chế ở cấp **Redis Server**, không phải cấu hình TTL trong Spring Data Redis. Nếu `maxmemory` không được thiết lập giới hạn hữu hiệu (chẳng hạn giá trị `0` trên Redis 64-bit thông thường), Redis không tự eviction theo một ngưỡng ứng dụng mong muốn. Hết RAM thực tế ở hệ điều hành có thể dẫn đến lỗi hoặc tiến trình bị dừng, và điều đó **không đồng nghĩa** với eviction do Redis thực hiện.

### 3.2. Các chính sách eviction phổ biến

| Policy | Khóa có thể bị chọn | Nguyên tắc chọn |
|---|---|---|
| `noeviction` | Không khóa nào bị eviction | Khi không thể cấp thêm bộ nhớ theo giới hạn, các lệnh cần thêm bộ nhớ có thể báo lỗi OOM; khóa có TTL vẫn hết hạn bình thường |
| `allkeys-lru` | Mọi khóa | Ưu tiên khóa ít được sử dụng gần đây (*least recently used*) |
| `allkeys-lfu` | Mọi khóa | Ưu tiên khóa ít được truy cập thường xuyên (*least frequently used*) |
| `allkeys-random` | Mọi khóa | Chọn ngẫu nhiên |
| `volatile-lru` | Chỉ khóa có TTL | Ưu tiên khóa có TTL ít được dùng gần đây |
| `volatile-lfu` | Chỉ khóa có TTL | Ưu tiên khóa có TTL ít được truy cập thường xuyên |
| `volatile-random` | Chỉ khóa có TTL | Chọn ngẫu nhiên trong các khóa có TTL |
| `volatile-ttl` | Chỉ khóa có TTL | Ưu tiên khóa có thời gian sống còn lại ngắn |

Các cơ chế LRU/LFU trong Redis dựa trên lấy mẫu và thông tin xấp xỉ để tối ưu hiệu năng; không nên diễn giải chúng là một thứ tự tuyệt đối, chính xác 100% giữa mọi khóa. Với nhóm `volatile-*`, nếu không có khóa đủ điều kiện để loại bỏ, lệnh ghi vẫn có thể gặp lỗi thiếu bộ nhớ.

**Hai tình huống dễ gây nhầm lẫn:**

- Đặt `maxmemory-policy noeviction` **không vô hiệu hóa TTL**. Khóa có TTL vẫn hết hạn dù Redis không eviction khóa nào.
- Đặt `maxmemory-policy allkeys-lru` khiến **khóa không có TTL cũng có thể bị xóa** vì thiếu bộ nhớ. `TTL = -1` không đồng nghĩa với được Redis bảo vệ trước eviction.

### 3.3. Một khóa có TTL có thể bị loại trước hạn

Giả sử ứng dụng lưu giỏ hàng tạm thời:

```redis
SET cart:customer-42 "{\"items\":[101,205]}" EX 1800
```

Ở thời điểm tạo, giỏ hàng có TTL 30 phút. Nếu Redis chạy `allkeys-lru`, có áp lực bộ nhớ và khóa này được chọn làm nạn nhân sau 2 phút, chuỗi sự kiện sẽ là:

```text
00:00   SET cart:customer-42 ... EX 1800
        │
02:00   Redis thiếu bộ nhớ → policy chọn khóa → EVICTION
        │
02:01   GET cart:customer-42 → nil
        TTL cart:customer-42 → -2
        │
30:00   Hạn TTL dự kiến (khóa đã không còn từ phút 02:00)
```

Nếu không có eviction hay thao tác xóa nào khác, khóa sẽ hết hạn khi thời gian TTL kết thúc. **Spring Data Redis không thể dựa vào `GET == null` để kết luận khóa đã hết TTL hay bị eviction.**

## 4. Quan sát và xác định nguyên nhân khóa biến mất

### 4.1. Kiểm tra từ Redis CLI

```redis
TTL cart:customer-42
PTTL cart:customer-42
INFO memory
INFO stats
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Các chỉ số hữu ích nhất:

| Chỉ số | Cách sử dụng |
|---|---|
| `expired_keys` (`INFO stats`) | Số khóa đã được Redis loại bỏ vì hết hạn, tính cộng dồn theo vòng đời bộ đếm |
| `evicted_keys` (`INFO stats`) | Số khóa bị loại bởi cơ chế eviction, tính cộng dồn theo vòng đời bộ đếm |
| `used_memory` (`INFO memory`) | Bộ nhớ Redis đang ghi nhận sử dụng |
| `maxmemory` (`INFO memory`) | Ngưỡng giới hạn đang có hiệu lực trong Redis |
| `maxmemory_policy` (`INFO memory`) | Policy eviction đang có hiệu lực |

Hãy theo dõi **mức tăng của các bộ đếm theo khoảng thời gian**, chẳng hạn mỗi phút, thay vì chỉ nhìn giá trị tổng hiện tại. `expired_keys` tăng nhanh có thể là hành vi bình thường đối với hệ thống chứa nhiều TTL ngắn; `evicted_keys` tăng cùng lúc tỷ lệ cache miss tăng có thể cho thấy kích thước cache không đủ hoặc policy chưa phù hợp.

Các bộ đếm này phản ánh toàn Redis instance (hoặc từng node, tùy mô hình triển khai), **không xác nhận trực tiếp nguyên nhân biến mất của một khóa cụ thể**. Một lần `GET` trả `nil` không có metadata nêu lý do.

### 4.2. Keyevent notifications khi cần quan sát sự kiện

Redis có thể phát thông báo khi khóa được xử lý hết hạn hoặc bị eviction. Trong môi trường thử nghiệm, có thể bật các loại sự kiện tương ứng:

```redis
CONFIG SET notify-keyspace-events Exe
```

Trong đó `E` là thông báo dạng *keyevent*, `x` là expired và `e` là evicted. Mở một kết nối `redis-cli` riêng để đăng ký:

```redis
PSUBSCRIBE __keyevent@0__:expired __keyevent@0__:evicted
```

Ví dụ các channel nhận được là:

```text
__keyevent@0__:expired  → session:1001
__keyevent@0__:evicted  → cart:customer-42
```

Đây là **kênh quan sát**, không phải nhật ký bền vững: thông báo Pub/Sub không được lưu lại cho client ngắt kết nối; expired event được phát khi Redis thực sự xử lý xóa khóa hết hạn, có thể trễ so với mốc TTL. Một số dịch vụ Redis được quản lý có thể hạn chế `CONFIG SET`. Trong Redis Cluster, cần theo dõi node chứa khóa tương ứng, thay vì giả định một kết nối nhận được tất cả sự kiện.

## 5. Thử nghiệm cô lập để nhìn thấy cả hai cơ chế

Chỉ chạy ví dụ sau trên Redis thử nghiệm riêng; thao tác sinh tải nhằm kích hoạt eviction.

### Bước 1: khởi tạo Redis có giới hạn bộ nhớ nhỏ

```bash
docker run --rm --name redis-expiry-lab -p 6380:6379 redis:7 \
  redis-server --save "" --appendonly no \
  --maxmemory 8mb --maxmemory-policy allkeys-lru
```

Mở terminal khác để dùng `redis-cli -p 6380`. Port `6380` giúp tách thử nghiệm khỏi Redis mặc định trên `6379`.

### Bước 2: quan sát expiration

```bash
redis-cli -p 6380 SET lab:expire "short-lived" EX 2
redis-cli -p 6380 TTL lab:expire
# Sau hơn 2 giây:
redis-cli -p 6380 GET lab:expire
redis-cli -p 6380 TTL lab:expire
redis-cli -p 6380 INFO stats
```

Sau khi hết hạn, `GET` trả `(nil)` và `TTL` trả `-2`; `expired_keys` sẽ tăng khi Redis xử lý việc loại bỏ khóa đã hết hạn.

### Bước 3: quan sát eviction

```bash
redis-cli -p 6380 SET lab:no-ttl "may-be-evicted"
redis-cli -p 6380 TTL lab:no-ttl
redis-cli -p 6380 INFO stats

# redis-benchmark tạo nhiều khóa SET, mỗi giá trị khoảng 4 KB.
redis-benchmark -p 6380 -t set -n 5000 -d 4096 -r 100000

redis-cli -p 6380 INFO stats
redis-cli -p 6380 INFO memory
redis-cli -p 6380 EXISTS lab:no-ttl
```

Vì khối lượng giá trị ghi lớn hơn ngân sách 8 MB, `evicted_keys` thường tăng rõ rệt. `lab:no-ttl` **có thể** bị eviction dù TTL ban đầu là `-1`; policy LRU có tính xấp xỉ nên không được kỳ vọng khóa cụ thể nào chắc chắn sẽ bị chọn. Nếu so sánh thông số trên server chạy lâu, hãy lấy chênh lệch bộ đếm trước và sau thử nghiệm.

## 6. Liên hệ với Spring Data Redis

### 6.1. TTL do ứng dụng thiết lập

`StringRedisTemplate` cho phép ghi một giá trị cùng TTL bằng `Duration`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OtpStore {
    private final StringRedisTemplate redis;

    public OtpStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveOtp(String accountId, String otp) {
        redis.opsForValue().set(
            "otp:" + accountId,
            otp,
            Duration.ofMinutes(3)
        );
    }

    public String findOtp(String accountId) {
        return redis.opsForValue().get("otp:" + accountId);
    }

    public Long remainingSeconds(String accountId) {
        return redis.getExpire("otp:" + accountId, TimeUnit.SECONDS);
    }
}
```

`findOtp()` có thể trả `null` nếu OTP đã hết hạn, bị eviction hoặc bị xóa vì lý do khác. `remainingSeconds()` có thể trả `-2` nếu khóa không tồn tại, `-1` nếu khóa không đặt TTL, hoặc số giây còn lại nếu đang có TTL; cần xử lý cả giá trị `null` nếu thao tác không có kết quả do lỗi/không hỗ trợ ở tầng kết nối.

Phần code Java **chỉ đặt TTL**. Nó không cấu hình `maxmemory`, không chọn chính sách eviction và không bảo đảm khóa tồn tại đủ 3 phút.

### 6.2. TTL trong Spring Cache không thay thế Redis eviction policy

Với Spring Cache + Redis, có thể cấu hình TTL cho entry thông qua `RedisCacheManager`:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheConfig {
    @Bean
    public RedisCacheManager redisCacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration defaults = RedisCacheConfiguration
            .defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .build();
    }
}
```

TTL 10 phút ở đây quyết định thời hạn của cache entry. Nếu Redis Server dùng `allkeys-lru` và chạm ngưỡng `maxmemory`, entry vẫn có thể biến mất trước 10 phút. Trong ứng dụng dùng `@Cacheable`, điều này thường dẫn đến cache miss và tải lại dữ liệu từ nguồn chính khi phương thức được gọi tiếp theo.

### 6.3. Chọn cách thiết kế theo loại dữ liệu

| Dữ liệu | Cách nhìn đúng về việc mất khóa |
|---|---|
| Cache kết quả truy vấn có thể tính lại | Chấp nhận expiration hoặc eviction; xử lý cache miss và giới hạn tải truy vấn lại |
| Session hoặc giỏ hàng tạm | TTL phục vụ vòng đời phiên, nhưng cần đánh giá tác động khi bị eviction trước hạn |
| OTP, token ngắn hạn | TTL là giới hạn hiệu lực; nếu mất khóa sớm thì từ chối xác thực hoặc cho phép tạo lại an toàn |
| Khóa idempotency/rate limiter | Eviction sớm có thể làm sai bảo đảm chống trùng lặp hoặc giới hạn lượt; cân nhắc cách lưu/kiểm soát bộ nhớ phù hợp |
| Trạng thái nghiệp vụ không thể khôi phục | Không dựa vào Redis cache với eviction làm nguồn dữ liệu duy nhất; cần nơi lưu bền vững và cơ chế khôi phục phù hợp |

Nếu cần giữ các khóa không TTL khỏi eviction, nhóm `volatile-*` có thể phục vụ một số mô hình dữ liệu hỗn hợp, nhưng phải chấp nhận khả năng lỗi ghi khi không còn khóa có TTL thích hợp để loại bỏ. Nếu không muốn Redis tự eviction, chọn `noeviction` và dự trù bộ nhớ cùng xử lý lỗi ghi; **điều đó vẫn không bảo đảm chống mất dữ liệu do lỗi máy, cấu hình persistence hay thao tác xóa**.

## 7. Cách điều tra khi ứng dụng báo “Redis tự mất key”

Đi từ dữ liệu quan sát được đến giả thuyết, tránh kết luận chỉ từ một lần `GET`:

1. **Xác nhận khóa và Redis đích:** Đúng hostname, database, Redis Cluster shard, prefix và serializer của `RedisTemplate` chưa? Khác namespace có thể trông như mất khóa.
2. **Kiểm tra TTL ngay sau khi ghi:** Dùng `TTL`/`PTTL` để xác nhận giá trị thực tế; xem có `SET` ghi đè làm mất TTL, `EXPIRE` đặt thời gian quá ngắn hoặc `PERSIST` không mong muốn không.
3. **Kiểm tra cấu hình bộ nhớ:** Đọc `INFO memory`, `maxmemory`, `maxmemory-policy`. Policy `allkeys-*` cho phép loại cả khóa không TTL.
4. **So sánh bộ đếm theo thời gian:** `expired_keys` tăng là dấu hiệu expiration đang diễn ra; `evicted_keys` tăng là dấu hiệu Redis đã thực hiện eviction. Hai hiện tượng có thể đồng thời xảy ra.
5. **Kiểm tra thao tác xóa ở ứng dụng:** `DEL`, `UNLINK`, `FLUSHDB`, `FLUSHALL`, cập nhật key, lỗi serializer hoặc đổi tên key cũng gây cache miss nhưng không phải hai cơ chế đang học.
6. **Đánh giá ảnh hưởng nghiệp vụ:** Với cache có thể tái tạo, tối ưu tỷ lệ hit/miss và tải nguồn chính; với dữ liệu cần bảo đảm tồn tại, xem lại kiến trúc lưu trữ và cấu hình Redis Server.

Không nên dùng `KEYS *` để điều tra trên instance có nhiều khóa vì có thể gây nghẽn; dùng `SCAN` theo từng đợt nếu thật sự cần khảo sát tên khóa. Các thông số `used_memory` cũng không thể thay thế kiểm tra bộ nhớ thực tế của host/container, đặc biệt khi có AOF, replication hoặc nhiều tiến trình dùng chung tài nguyên.

## 8. Những kết luận cần ghi nhớ

- **Expiration** phụ thuộc vào TTL của từng khóa, không cần thiếu RAM.
- **Eviction** phụ thuộc vào giới hạn bộ nhớ và policy của Redis Server; có thể xóa một khóa trước TTL hoặc xóa khóa hoàn toàn không có TTL.
- `noeviction` chỉ vô hiệu hóa cơ chế loại khóa để giải phóng bộ nhớ; **không tắt expiration**.
- `TTL = -2` và `GET = nil` chỉ cho biết khóa không còn đọc được; không đủ để kết luận nguyên nhân.
- Dùng `expired_keys`, `evicted_keys`, thông tin bộ nhớ và thời điểm sự kiện để điều tra ở cấp Redis; cần log/ngữ cảnh bổ sung nếu muốn truy vết một khóa cụ thể.
- Trong Spring Data Redis, `Duration` và `RedisCacheConfiguration.entryTtl()` đặt thời gian sống của dữ liệu, còn `maxmemory`/`maxmemory-policy` do Redis Server quản lý.

**Câu hỏi tự kiểm tra:** Một khóa cache có TTL 1 giờ nhưng bị mất sau 5 phút, đồng thời `evicted_keys` tăng và Redis chạy `allkeys-lru`. Có thể giải thích thế nào? → Khóa *có thể* đã bị eviction trước hạn do áp lực bộ nhớ; cần thêm thông tin để quy kết chính xác cho khóa đó. Nếu Redis chạy `noeviction` mà `expired_keys` vẫn tăng thì có mâu thuẫn không? → Không, vì hai cơ chế độc lập.
