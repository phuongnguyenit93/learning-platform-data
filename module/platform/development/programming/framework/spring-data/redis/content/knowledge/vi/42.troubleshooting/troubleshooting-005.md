# TTL biến mất, không được gia hạn hoặc khóa hết hạn ngoài dự kiến trong Spring Data Redis

## 1. Bài toán: TTL hoạt động không đúng như kỳ vọng

Một dịch vụ Spring Boot dùng Redis để lưu cache, session, mã xác minh, bộ đếm và khóa phân tán. Nhóm phát triển quan sát những hiện tượng khó hiểu:

- Một key được tạo với TTL 30 phút, nhưng sau khi cập nhật value, `TTL` trả `-1`.
- Người dùng liên tục đọc cache nhưng key vẫn hết hạn đúng sau 10 phút.
- Worker đã lấy Redis lock, đang chạy job thì khóa hết hạn; worker khác lấy khóa và cùng làm việc.
- Ứng dụng gọi hàm gia hạn TTL nhưng kết quả thực tế không đổi.
- Một key biến mất khi vẫn còn nhiều phút TTL; Redis đồng thời chịu áp lực bộ nhớ.
- Sau Sentinel/Cluster failover, khóa hoặc expiration khác với trạng thái primary cũ vừa ACK.

Những sự cố này thuộc các nhóm khác nhau:

```text
Key "không đúng TTL"
  |
  +-- PTTL = -1: Key còn tồn tại, nhưng không có expiry.
  |
  +-- PTTL = -2: Key không tồn tại.
  |                  |
  |                  +-- Hết hạn theo TTL?
  |                  +-- DEL/UNLINK/cache eviction?
  |                  +-- Eviction do bộ nhớ?
  |                  +-- Đọc sai key, DB hoặc Redis node?
  |
  +-- PTTL > 0: Key có expiry.
                     |
                     +-- TTL giảm như bình thường?
                     +-- GET không gia hạn?
                     +-- Renew thất bại hay bị ghi đè?
```

Điểm khởi đầu khi chẩn đoán là **phân biệt TTL bị xóa, TTL không được gia hạn và key thực sự biến mất**. Không nên tăng TTL lên một con số lớn rồi coi đó là giải pháp cho mọi nguyên nhân.

Trong bài này, chúng ta sử dụng Spring Data Redis với `StringRedisTemplate`, `RedisCacheConfiguration`, Redis Repository, Lettuce và Redis CLI. Ví dụ tập trung vào Spring Boot 3.x và Redis 6.2/7.x trở lên ở những tính năng yêu cầu phiên bản cụ thể.

## 2. TTL là thuộc tính của key Redis

Redis có thể đặt thời điểm hết hạn cho một key, rồi xem key như không còn tồn tại khi thời điểm đó đi qua.

```redis
SET session:user-42 active EX 1800
TTL session:user-42
PTTL session:user-42
```

- `EX 1800`: đặt thời gian sống 1.800 giây.
- `TTL`: số giây còn lại.
- `PTTL`: số mili giây còn lại.

Redis có **passive expiration** khi truy cập key và **active expiration** để dọn key ở nền. Thời điểm thu hồi bộ nhớ nội bộ có thể trễ hơn thời điểm key hết hạn, nhưng các phép truy cập phù hợp không nên coi một key đã hết hạn như dữ liệu còn hợp lệ.

### 2.1. TTL của Hash, List, Set cũng là key-level TTL

```redis
HSET profile:42 name Linh city HCM
EXPIRE profile:42 600
PTTL profile:42
```

Khi key `profile:42` hết hạn, **cả Hash** biến mất. Một lệnh `HSET` sửa field của key còn tồn tại không mặc nhiên gia hạn expiry của cả Hash.

Các Redis version mới có thêm cơ chế hết hạn riêng cho hash field. Đó là tính năng phụ thuộc phiên bản và **khác** với key-level `TTL`/`PTTL` trong bài này.

## 3. Diễn giải chính xác TTL và PTTL

| Kết quả | Ý nghĩa | Hướng điều tra |
|---|---|---|
| Số dương | Key còn tồn tại, có expiry | Kiểm tra thời điểm tạo/gia hạn |
| `TTL=0` | Key có thể còn dưới một giây TTL | Dùng `PTTL` để đọc độ phân giải ms |
| `-1` | Key còn tồn tại **không có expiry** | Tìm SET ghi đè, PERSIST, policy sai |
| `-2` | **Key không tồn tại** | Tìm expire, delete, eviction, key mismatch |

**`-1` không có nghĩa key đã hết hạn.** Trái lại, nó có nghĩa key đang tồn tại nhưng Redis không có thời điểm tự xóa.

**`-2` cũng không tự chứng minh key hết hạn.** Một key chưa từng được tạo, bị xóa bằng `DEL` hoặc bị eviction đều có thể trả kết quả này.

### 3.1. Tránh assertion TTL chính xác tuyệt đối

```redis
SET lab:ttl:k1 hello PX 1000
PTTL lab:ttl:k1
```

Lệnh thứ hai có thể trả khoảng 997–999 ms tùy network/scheduling. Một integration test nên kiểm tra khoảng hợp lý, không yêu cầu bằng đúng 1.000 ms.

### 3.2. Race giữa hai lệnh quan sát

```text
T0: EXISTS key -> 1
T1: key hết hạn
T2: PTTL key -> -2
```

Hai lệnh chạy riêng nên kết quả có thể phản ánh hai thời điểm khác nhau. Khi cần snapshot nguyên tử một nhóm quan sát trên cùng Redis node, có thể dùng Lua script chỉ đọc; nhưng đừng làm hệ thống chẩn đoán nặng nề cho mọi request.

## 4. Nguyên nhân thường gặp nhất: SET làm mất TTL

Hãy chạy trên Redis test:

```redis
SET product:42 v1 EX 600
PTTL product:42

SET product:42 v2
PTTL product:42
```

Lệnh `SET product:42 v2` thông thường **ghi đè value và xóa expiration cũ**. Kết quả `PTTL=-1` là hành vi Redis đúng, không phải lỗi bộ đếm thời gian.

### 4.1. Cách sửa nếu muốn reset TTL khi ghi

```redis
SET product:42 v2 EX 600
```

Value và expiry được ghi trong **một command**. Mỗi lần cập nhật sẽ bắt đầu thời hạn mới.

### 4.2. Cách sửa nếu muốn giữ đúng expiry cũ

```redis
SET product:42 v2 KEEPTTL
```

`KEEPTTL` giữ nguyên thời điểm hết hạn đang có. Nếu key chỉ còn 30 giây thì sau cập nhật cũng chỉ còn khoảng 30 giây.

**Giữ TTL khác gia hạn TTL.** `KEEPTTL` không biến 30 giây thành 600 giây, và cũng không tạo expiry cho key vốn đã có `PTTL=-1`.

### 4.3. Một lỗi dễ gặp trong Java

```java
redis.opsForValue().set(key, value, Duration.ofMinutes(10));
// ... một luồng khác cập nhật cùng key:
redis.opsForValue().set(key, updatedValue); // TTL bị xóa.
```

Khi điều tra, phải tìm **mọi writer** của key, không chỉ nơi key được tạo lần đầu.

## 5. SET rồi EXPIRE là hai lệnh, có cửa sổ lỗi

```redis
SET session:42 active
EXPIRE session:42 1800
```

Giữa hai lệnh, process có thể crash, connection có thể mất hoặc một writer khác thay value. Key có thể bị bỏ lại với `PTTL=-1`.

Ưu tiên:

```redis
SET session:42 active EX 1800
```

Với distributed lock:

```redis
SET lock:report owner-token NX PX 30000
```

`NX` chỉ tạo key khi chưa có. `PX` đặt expiry trong **cùng lần thực thi nguyên tử**.

**Không dùng `SETNX` rồi `EXPIRE` thành hai lệnh để tạo lock.** Nếu crash giữa hai lệnh, lock có thể sống vô thời hạn.

## 6. Những lệnh nào giữ hoặc làm mất TTL?

| Lệnh / trường hợp | Ảnh hưởng điển hình |
|---|---|
| `SET key value` | Ghi đè value, xóa expiry |
| `SET key value EX n` hoặc `PX n` | Đặt TTL mới |
| `SET key value KEEPTTL` | Giữ expiry đang có |
| `MSET` ghi đè một key | Có thể xóa expiry của key được thay thế |
| `GETSET` legacy | Thay value và xóa expiry |
| `PERSIST key` | Giữ key, xóa expiry |
| `EXPIRE` / `PEXPIRE` | Đặt hoặc thay expiry |
| `INCR` trên key đang có | Giữ TTL hiện tại |
| `HSET` / `HDEL` trên Hash đang có | Giữ TTL của Hash key |
| `LPUSH` / `RPUSH` trên List đang có | Giữ key-level TTL |
| `SADD` / `ZADD` trên key đang có | Giữ key-level TTL |
| `DEL` / `UNLINK` | Xóa key; PTTL thành -2 |
| `RENAME` | Chuyển key cùng expiry sang tên mới theo command semantics |

Đừng dùng một quy tắc chung như "lệnh ghi sẽ gia hạn TTL". Semantics thay đổi theo command, việc key đã tồn tại hay chưa và các tùy chọn đã truyền.

### 6.1. INCR trên key mới không tự có TTL

```redis
INCR rate:login:u42
PTTL rate:login:u42
```

Nếu key không tồn tại từ trước, `INCR` tạo counter **không có expiry**, nên `PTTL=-1`.

Đây là lỗi phổ biến ở rate limiter tự viết: tạo counter thành công nhưng quên đặt TTL cho cửa sổ.

## 7. PERSIST chủ động xóa expiration

```redis
SET lab:ttl:persist temp EX 60
PERSIST lab:ttl:persist
PTTL lab:ttl:persist
```

Sau `PERSIST` thành công, key vẫn tồn tại nhưng không hết hạn tự động.

Cần tìm cả:

- `RedisTemplate.persist(...)` trong Java.
- Lua script gọi `PERSIST`.
- Admin scripts/migration jobs.
- Thao tác chuyển một key temporary thành permanent.

Không gắn lại expiry cho **mọi** key có -1 mà không xem namespace: một số key được thiết kế tồn tại vĩnh viễn.

## 8. EXPIRE, PEXPIRE và kết quả thực sự

```redis
EXPIRE session:42 1800
PEXPIRE lock:report 15000
```

- `EXPIRE` nhận giây.
- `PEXPIRE` nhận mili giây.
- Lệnh có thể trả 0 nếu key không tồn tại hoặc một điều kiện không được thỏa.

### 8.1. Bỏ qua Boolean là lỗi chẩn đoán

Code không đủ an toàn:

```java
redis.expire(key, Duration.ofMinutes(30));
log.info("TTL renewed");
```

Nếu key không tồn tại, log vẫn khẳng định đã gia hạn.

Thay bằng:

```java
Boolean renewed = redis.expire(key, Duration.ofMinutes(30));
if (!Boolean.TRUE.equals(renewed)) {
    throw new IllegalStateException(
        "TTL was not renewed: key absent or condition not met"
    );
}
```

Giá trị `null` có thể xuất hiện trong ngữ cảnh pipeline/transaction tùy API; không xem `null` là thành công.

### 8.2. Thời hạn bằng 0 hoặc âm có thể xóa key

```redis
EXPIRE key 0
```

Redis coi expiration không dương là yêu cầu xóa key theo semantics command. Một phép tính `Duration.between(now, expiresAt)` có thể trả 0/âm nếu timestamp đã qua. Hãy validate thời hạn trước khi gửi vào Redis.

## 9. EXPIRE với NX, XX, GT và LT

Các Redis version hỗ trợ điều kiện:

```redis
EXPIRE key 600 NX
EXPIRE key 600 XX
EXPIRE key 600 GT
EXPIRE key 600 LT
```

| Option | Chỉ đặt expiry khi |
|---|---|
| `NX` | Key chưa có expiry |
| `XX` | Key đã có expiry |
| `GT` | Thời điểm hết hạn mới xa hơn hiện tại |
| `LT` | Thời điểm hết hạn mới sớm hơn hiện tại |

Redis xử lý key không có expiry như có thời điểm hết hạn vô hạn khi so sánh `GT/LT`. Vì vậy, `EXPIRE key 600 GT` có thể **không** gắn TTL cho một key permanent.

### 9.1. Gia hạn bằng XX bị từ chối sau SET

```text
SET key v1 EX 60   -> key có TTL
SET key v2         -> TTL bị xóa, key vẫn tồn tại
EXPIRE key 60 XX   -> điều kiện không thỏa
```

Nếu code chỉ kiểm tra key tồn tại thì rất dễ hiểu nhầm. Hãy phân biệt **không có key** và **key có nhưng không có TTL** khi phân tích kết quả.

### 9.2. GT không xác minh quyền sở hữu lock

`EXPIRE key 30 GT` có thể hữu ích để không rút ngắn thời hạn trong một số workflow; nó **không** chứng minh worker gọi lệnh vẫn giữ distributed lock.

## 10. GETEX: đọc và gia hạn cùng một lệnh

Redis 6.2+ hỗ trợ `GETEX` cho String key:

```redis
GETEX session:42 EX 1800
GETEX session:42 PX 30000
GETEX session:42 PERSIST
```

`GETEX key EX n` đọc value và đặt lại expiry trong một command.

**Cẩn thận:** `GETEX key PERSIST` làm mất TTL, không phải gia hạn.

### 10.1. GET và GETEX không giống nhau

```text
GET key         -> đọc, không gia hạn
GETEX key EX n  -> đọc và đặt expiry mới
```

Nếu yêu cầu "còn hoạt động thì session tiếp tục sống", một lời gọi `GET` thông thường không thực hiện hợp đồng đó.

### 10.2. GET rồi EXPIRE có race

```redis
GET session:42
EXPIRE session:42 1800
```

Giữa hai lệnh, key có thể hết hạn hoặc bị một luồng khác thu hồi. Với String key và policy read-and-touch, `GETEX` giảm race của cặp lệnh này.

Không vì thế mà coi `GETEX` là giao thức quản lý session đầy đủ; logout, revocation, absolute lifetime và authorization vẫn cần logic riêng.

## 11. TTL cố định, sliding expiration và time-to-idle

| Chính sách | Key hết hạn khi | Lần đọc có kéo dài? |
|---|---|---|
| Fixed TTL | N giây sau lần ghi/đặt TTL | Không |
| Sliding expiration | N giây sau hoạt động hợp lệ gần nhất | Có, nếu client thực hiện touch |
| Time-to-idle (TTI) | N giây không có truy cập được tính là hoạt động | Có, nếu đường đọc dùng cơ chế TTI |

Ví dụ fixed TTL:

```text
T0  SET key v EX 600
T5  GET key -> TTL còn khoảng 300 giây
T8  GET key -> TTL còn khoảng 120 giây
T10 key hết hạn
```

Ví dụ sliding:

```text
T0  SET key v EX 600
T5  GETEX key EX 600 -> TTL được đặt lại
T8  GETEX key EX 600 -> TTL được đặt lại
T18 hết hạn nếu không có lần touch mới
```

**Không lấy tên method HTTP GET để suy ra Redis dùng GETEX.** Phải kiểm tra command được phát ra thực tế.

### 11.1. Idle timeout khác maximum session age

Một session có idle timeout 30 phút và maximum lifetime 24 giờ cần hai điều kiện riêng. Nếu chỉ dùng `GETEX ... EX 1800`, session có thể tiếp tục sống nhiều ngày khi luôn có hoạt động.

## 12. Spring Data Redis với StringRedisTemplate

Ví dụ:

```java
package com.example.redis.ttl;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionValueStore {

    private final StringRedisTemplate redis;

    public SessionValueStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void create(String id, String value) {
        redis.opsForValue().set(
            "session:" + id,
            value,
            Duration.ofMinutes(30)
        );
    }

    public void updateIncorrectly(String id, String value) {
        // Minh họa bug: overload không TTL sẽ xóa expiry.
        redis.opsForValue().set("session:" + id, value);
    }

    public Long remainingMillis(String id) {
        return redis.getExpire(
            "session:" + id, TimeUnit.MILLISECONDS
        );
    }
}
```

Điểm cần xem khi chẩn đoán:

- Overload `set(key,value)` hay `set(key,value,Duration)`?
- Có writer khác cùng namespace không?
- Thời lượng có bị tính thành 0/âm không?
- Key đã tồn tại nhưng dùng `SET` để overwrite thay vì sửa field?

Không mặc định Spring Data Redis tự bảo toàn TTL cho mọi thao tác thay value.

## 13. Lỗi Duration và đơn vị thời gian

Một số hệ thống trộn giây, mili giây và giá trị cấu hình:

```java
long ttl = 600; // 600 gì? giây hay mili giây?
```

Rủi ro:

- Tưởng 600 giây nhưng gọi API nhận milliseconds.
- `Duration.ofMillis(600)` làm key hết hạn sau 0,6 giây.
- `Duration.between(Instant.now(), expiry)` trả âm.
- Dùng lệnh `EXPIREAT` với milliseconds, trong khi lệnh này nhận seconds.
- Kiểm tra `TTL` với giá trị ms và kết luận bị rút ngắn.

Ưu tiên `Duration` có đơn vị rõ ràng và log `requested_ttl_ms` sau khi chuẩn hóa. Validate TTL tối thiểu, tối đa và overflow theo chính sách ứng dụng.

### 13.1. TTL khóa rất ngắn không phù hợp với mạng dao động

Nếu lock TTL 50 ms mà mỗi Redis RTT bình thường có thể vài chục ms và Java có GC pause, một lần renew có thể không đến kịp. Cần chọn lease theo tail latency/failure model, không chỉ dựa trên thời gian xử lý trung bình.

## 14. Spring Cache: đọc cache không tự renew TTL

Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return repository.findById(productId);
}
```

Khi một entry được ghi với TTL cố định, các cache hits qua đường GET thông thường **không tự gia hạn** thời gian sống của nó.

Người dùng có thể liên tục gọi API và cache vẫn hết hạn đúng sau 10 phút. Đây có thể là hành vi thiết kế.

### 14.1. Cấu hình TTL cố định

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Bean
RedisCacheConfiguration redisCacheConfiguration() {
    return RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(10));
}
```

Ứng dụng cần xác minh `RedisCacheManager` thực sự dùng configuration trên, thay vì một per-cache override hoặc một bean tự tạo khác.

### 14.2. Cấu hình mới không sửa TTL của mọi entry cũ

Nếu đổi TTL từ 30 phút thành 5 phút, các key đã được cache trước đó có thể tiếp tục mang expiry cũ cho tới khi được ghi lại/touch theo policy. Không giả định Spring Cache quét và cập nhật tất cả key ngay khi deploy.

Khi migration, cần quyết định clear cache có chọn lọc, chờ hết hạn tự nhiên hoặc viết job chuyển đổi với kiểm soát tải nguồn dữ liệu.

## 15. Spring Data Redis time-to-idle

Spring Data Redis hỗ trợ mô phỏng TTI ở các phiên bản thích hợp, ví dụ Spring Data Redis 3.2+, bằng `RedisCacheConfiguration.enableTimeToIdle()` kết hợp Redis `GETEX`.

```java
import java.time.Duration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

RedisCacheConfiguration cfg =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(10))
        .enableTimeToIdle();
```

Khi cache manager thật sự dùng cấu hình đó, những cache reads đi qua cơ chế tương ứng có thể gia hạn expiry.

**Điều kiện cần kiểm tra:**

1. Redis server hỗ trợ GETEX (Redis 6.2+).
2. Spring Data Redis version hỗ trợ API TTI.
3. Cache manager dùng đúng configuration.
4. Không có đường truy cập khác dùng GET thuần cho cùng key trong khi nghiệp vụ kỳ vọng mọi lượt đọc đều được touch.

Đừng kết luận TTI hoạt động chỉ vì mã nguồn gọi `enableTimeToIdle()` nhưng runtime sử dụng Redis driver/cache manager khác.

## 16. TTL động và per-cache override

Một cache manager có thể quản lý:

```text
products: TTL 10 phút
stock:    TTL 30 giây
profile:  TTL 1 giờ
```

Một số Spring Data Redis versions còn hỗ trợ TTL động theo value, chẳng hạn qua `RedisCacheWriter.TtlFunction`.

Nếu entry cụ thể có TTL bất thường, kiểm tra:

- Per-cache configuration có ghi đè default không?
- TTL function nhận value/null sentinel nào?
- Cache writer được chọn có thực sự dùng function không?
- Negative caching có TTL ngắn khác positive caching không?
- Có key cũ tồn tại từ trước deploy không?

Không nên chỉ nhìn một thuộc tính trong `application.yml` rồi kết luận tất cả cache entries có cùng TTL.

## 17. Redis Repository: @RedisHash và @TimeToLive

Spring Data Redis Repository có thể khai báo TTL ở entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "customerSession", timeToLive = 1800)
public class CustomerSession {
    @Id
    private String id;
    private String state;
}
```

Hoặc TTL theo instance:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("customerSession")
public class CustomerSession {
    @Id
    private String id;

    @TimeToLive
    private Long ttlSeconds;
}
```

Khi dùng repository:

- Xem TTL đến từ annotation, property hay method.
- Hiểu đơn vị của numeric property theo API tương ứng.
- Không đặt nhiều nguồn TTL mà không rõ thứ tự ưu tiên.
- Kiểm tra repository `save(...)` có cập nhật expiration theo metadata entity không.
- Không coi save Redis entity tương đương một SQL UPDATE chỉ thay đúng một field.

### 17.1. Save có thể reset TTL theo mapping

Một application flow khác save entity với TTL cũ hoặc không đúng có thể làm TTL bị thay đổi. Trong tình huống concurrency, cần kiểm tra trình tự đọc, sửa, save và những đường cập nhật khác trên cùng keyspace.

## 18. Keyspace notifications và phantom copies

Spring Data Redis repositories có thể sử dụng Redis keyspace notifications cho expiration events. Ở những cấu hình/phiên bản tương ứng, framework còn có thể tạo **phantom/shadow copy** của entity để cung cấp dữ liệu khi key chính hết hạn.

Điều này có thể khiến keyspace còn một key phụ sau khi key entity chính đã mất. Tên và lifetime của các key phụ phụ thuộc implementation/version, không nên dựa vào một suffix cứng.

Quan trọng:

- Có key phụ không chứng minh key chính chưa expire.
- Secondary indexes cần được xử lý theo cơ chế repository.
- Notification dựa trên Redis Pub/Sub, có thể bị bỏ lỡ nếu subscriber offline.
- Expiration event có thể trễ và không phải realtime scheduler.

**Không dùng notification làm nguồn duy nhất để chạy công việc bắt buộc chính xác thời điểm hoặc để hủy quyền session.**

## 19. TTL đúng nhưng key vẫn biến mất sớm: expiration khác eviction

```redis
INFO stats
INFO memory
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Trong `INFO stats`:

```text
expired_keys:...
evicted_keys:...
```

- **Expired:** Redis đã loại key vì hết thời hạn.
- **Evicted:** Redis đã loại key do chính sách quản lý bộ nhớ.

Một key có TTL 30 phút vẫn có thể bị eviction sau 5 phút nếu `maxmemory` và policy cho phép.

### 19.1. Ví dụ eviction policies

- `allkeys-lru`: có thể chọn key trong toàn bộ keyspace để evict theo xấp xỉ LRU.
- `volatile-ttl`: xét những key có TTL và ưu tiên thời hạn gần.
- `noeviction`: không chủ động loại key để giải phóng bộ nhớ theo cache policy, có thể khiến lệnh ghi bị từ chối.

Không dùng câu "TTL bảo đảm key phải tồn tại ít nhất N phút". Nó là **điều kiện hết hạn**, không phải bảo đảm chống eviction, DEL hoặc failover.

### 19.2. Counter toàn node không phải chứng cứ cho một key

`evicted_keys` tăng mạnh là tín hiệu hữu ích nhưng không chứng minh riêng `session:42` bị evict. Hãy đối chiếu workload, time window, namespace và logs/traces.

## 20. Keyspace notifications giúp phân biệt expired và evicted

Kiểm tra:

```redis
CONFIG GET notify-keyspace-events
```

Trong Redis test riêng, có thể bật các keyevent notifications cho expiration và eviction:

```redis
CONFIG SET notify-keyspace-events Exe
```

Ví dụ channels:

```text
__keyevent@0__:expired
__keyevent@0__:evicted
```

Trong chuỗi cấu hình minh họa, `E` bật keyevent, `x` cho expired và `e` cho evicted. Bản cấu hình thực tế có thể phải giữ thêm các nhóm notification mà ứng dụng khác đang dùng.

**Không chạy CONFIG SET tùy tiện trên production.** Notifications có overhead; Redis managed services có thể không cho phép thay đổi qua CLI. Event là Pub/Sub, không durable và không phản ánh chính xác mọi thay đổi key trong quá khứ.

## 21. Các lệnh xóa chủ động dễ bị nhầm với TTL

Một key cũng biến mất khi code gọi:

```redis
DEL product:42
UNLINK product:42
```

hoặc qua Spring:

```java
redis.delete("product:42");
```

Spring Cache có thể:

```java
@CacheEvict(cacheNames = "products", key = "#productId")
public void updateProduct(String productId) {
    // Update database...
}
```

Nếu key bị invalidated sau khi database thay đổi, đó có thể là **hành vi đúng**, không phải expiration sớm.

Cần tìm:

- `@CacheEvict`, `@Caching`, `@CachePut`.
- `RedisTemplate.delete(...)` và `UNLINK`.
- Scheduled cleanup hoặc migration scripts.
- Lua scripts có `DEL`.
- Tác động của `FLUSHDB`/`FLUSHALL` trong môi trường test hay lỗi vận hành.

Không sửa bằng cách tái tạo cache entry một cách mù quáng, đặc biệt khi việc xóa là để ngăn trả dữ liệu cũ.

## 22. Clock, EXPIREAT và thời gian tuyệt đối

Redis lưu thời điểm expiration; đồng hồ hệ thống có ảnh hưởng tới việc key hết hạn và tới những thao tác dùng timestamp tuyệt đối.

```redis
EXPIREAT key 1794500000
PEXPIREAT key 1794500000000
```

`EXPIREAT` nhận Unix timestamp **giây**, còn `PEXPIREAT` nhận **mili giây**. Truyền nhầm đơn vị có thể tạo expiry quá gần, quá xa hoặc đã trong quá khứ.

### 22.1. Duration tính từ timestamp đã hết hạn

```java
Duration remain = Duration.between(
    Instant.now(), expiresAt
);
```

Nếu `expiresAt` đã qua, `remain` có thể âm. Phải chọn chính sách rõ: reject, xóa key hay xử lý phiên hết hạn — không chuyển Duration âm qua helper `expire` rồi coi Redis là nguyên nhân.

### 22.2. Snapshot/restore và đồng hồ

Key có expiry tuyệt đối có thể đã hết hạn khi khôi phục snapshot cũ. Không coi đó là lỗi restore chỉ vì sau khi nạp key không còn.

Với session hoặc mã xác minh, việc không hồi sinh dữ liệu đã quá hạn thường là yêu cầu bảo mật.

## 23. Đọc sai key, serializer hoặc Redis database

Một service:

```text
Service A:
  key: session:42
  StringRedisSerializer
  database 0

Service B:
  key nhìn trên code cũng là session:42
  JdkSerializationRedisSerializer
  database 1
```

Service B có thể đọc nhầm bytes/keyspace và nhận `PTTL=-2` dù key A ghi vẫn tồn tại.

Kiểm tra:

1. Redis endpoint, environment và logical DB.
2. Key prefix, cache prefix và namespace.
3. Key serializer sử dụng bởi từng template.
4. Redis Cache key generation.
5. Redis Cluster routing và slot (Cluster thường dùng DB 0).
6. Read-from-replica settings và failover.

**Không kết luận Redis tự xóa key chỉ vì `redis-cli EXISTS session:42` trả 0** khi ứng dụng thực tế ghi key với binary serialization khác.

## 24. Redis replication và failover

Redis replication thông thường là bất đồng bộ:

```text
Primary P:
   SET lock tokenA NX PX 30000 -> OK
   chưa replicate tới R

P lỗi, R được promote.

Client GET lock trên R -> nil
```

Tương tự, một lần renew TTL có thể được primary cũ ACK nhưng replica được promote chưa áp dụng. Một lần đọc từ replica cũng có thể cho thấy TTL/state chưa bắt kịp primary.

Khi chẩn đoán:

```redis
ROLE
INFO replication
```

Ghi rõ node trả `PTTL`, role primary/replica, thời điểm failover và replication lag.

### 24.1. Không xem failover là bảo đảm giữ mọi write

Client reconnect thành công không chứng minh mọi write và expiration update trước failover đã xuất hiện ở primary mới. Với lock, session và idempotency marker, phải hiểu failure model và có reconciliation hoặc nguồn sự thật phù hợp.

## 25. Khóa phân tán là lease có thời hạn

```redis
SET lock:job:nightly tokenA NX PX 30000
```

Worker A lấy được khóa trong thời hạn 30 giây. Nhưng Redis không biết lúc nào job Java hoàn thành:

```text
T0  A acquire lock
T5  A gọi API chậm
T20 A bị GC pause
T30 Redis cho lock hết TTL
T31 B acquire cùng key với tokenB
T35 B bắt đầu xử lý
T40 A chạy tiếp sau pause
```

**Redis không thể tự dừng Java thread hoặc rollback side effect của A.** Khi TTL hết, owner khác có thể acquire.

### 25.1. TTL phù hợp phải xét tail latency

Nếu job trung bình 4 giây nhưng đôi khi 50 giây, lease 10 giây có nguy cơ tạo overlap. Cần xét tail latency, GC, network, failover và khả năng dừng job, không chỉ thời gian trung bình.

TTL quá dài cũng có hại: worker chết giữa job sẽ khiến các worker khác đợi lâu.

## 26. Sai lầm: gia hạn khóa bằng EXPIRE không xác minh owner

```text
A có lock, bị pause quá TTL.
B acquire lock với tokenB.
A tỉnh dậy và gọi EXPIRE lock 30.
```

`EXPIRE` chỉ sửa expiry của key, **không biết A có còn sở hữu key hay không**. A có thể kéo dài lease của B ngoài ý muốn.

Tương tự, nếu A dùng `DEL lock` vô điều kiện khi hoàn tất, nó có thể xóa khóa của B.

**Mọi renew và release của distributed lock phải xác minh owner token nguyên tử.**

### 26.1. Owner token phải khác nhau mỗi lần acquire

Không dùng cùng value `"locked"` cho tất cả owners. Tạo token mới:

```java
String ownerToken = UUID.randomUUID().toString();
```

Owner token dùng so sánh ai đang có quyền renew/release. Nó không mặc định là fencing token có thứ tự tăng dần.

## 27. Lua script gia hạn nếu owner còn đúng

```lua
-- KEYS[1] = lock key
-- ARGV[1] = owner token
-- ARGV[2] = TTL mới (milliseconds)

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
```

Script kiểm tra token và gia hạn trong một Redis atomic execution.

| Trạng thái | Kỳ vọng |
|---|---|
| Key còn, token trùng | Trả 1, gia hạn |
| Key còn, token khác | Trả 0, không gia hạn khóa của owner khác |
| Key đã hết hạn | Trả 0, không tạo lại |
| Network timeout | Kết quả không chắc chắn, phải xử lý theo protocol |

Không thay script bằng `EXPIRE key n XX`, vì XX chỉ kiểm tra key có expiry, **không kiểm tra owner**.

## 28. Spring Data Redis: service quản lý lock an toàn

```java
package com.example.redis.lock;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public final class RedisLeaseService {

    private static final DefaultRedisScript<Long> RENEW;
    private static final DefaultRedisScript<Long> RELEASE;

    static {
        RENEW = new DefaultRedisScript<>();
        RENEW.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('PEXPIRE', KEYS[1], ARGV[2])
            end
            return 0
            """);
        RENEW.setResultType(Long.class);

        RELEASE = new DefaultRedisScript<>();
        RELEASE.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """);
        RELEASE.setResultType(Long.class);
    }

    private final StringRedisTemplate redis;

    public RedisLeaseService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String tryAcquire(String key, Duration lease) {
        validateLease(lease);
        String token = UUID.randomUUID().toString();
        Boolean ok = redis.opsForValue()
            .setIfAbsent(key, token, lease);
        return Boolean.TRUE.equals(ok) ? token : null;
    }

    public boolean renew(String key, String token, Duration lease) {
        validateLease(lease);
        Long result = redis.execute(
            RENEW,
            List.of(key),
            token,
            Long.toString(lease.toMillis())
        );
        return Long.valueOf(1L).equals(result);
    }

    public boolean release(String key, String token) {
        Long result = redis.execute(
            RELEASE, List.of(key), token
        );
        return Long.valueOf(1L).equals(result);
    }

    private static void validateLease(Duration lease) {
        if (lease == null || lease.isZero()
                || lease.isNegative() || lease.toMillis() <= 0) {
            throw new IllegalArgumentException(
                "Lease must be at least 1 ms"
            );
        }
    }
}
```

Đây là minh họa cơ chế trên Redis primary đơn lẻ. Nó không tự tạo một distributed coordination protocol an toàn tuyệt đối qua failover hoặc ngăn worker cũ làm side effect sau TTL.

### 28.1. Timeout khi renew là kết quả không chắc chắn

Một `renew(...)` bị timeout có thể đã được Redis thực thi nhưng response không đến. Không tự coi timeout là success; cũng không tiếp tục làm việc khi không còn bằng chứng ownership theo protocol.

## 29. Watchdog renew định kỳ: hiệu quả và giới hạn

Một worker chạy job dài có thể gia hạn định kỳ:

```text
Lease = 30s
Renew interval = 10s (ví dụ)

T0   Acquire
T10  Renew if token matches
T20  Renew if token matches
T30  Renew if token matches
...
Finish -> Release if token matches
```

Watchdog cần:

- Cùng token cho một lần acquire.
- Renew bằng Lua compare-and-PEXPIRE.
- Kiểm tra false và timeout.
- Dừng công việc nhạy cảm khi không đủ bằng chứng lease vẫn thuộc mình.
- Dừng scheduler khi job hoàn thành hoặc bị hủy.
- Không tự tạo lock mới dưới job cũ rồi tiếp tục.

### 29.1. Renew quá sát expiry sẽ dễ thất bại

Renew lúc giây 29 cho lease 30 giây chỉ cần một lần GC pause hoặc network delay là quá muộn. Chừa biên theo latency/GC thực tế; cũng tránh renew quá dày cho số lượng locks rất lớn.

### 29.2. Watchdog không chống được JVM pause dài

Nếu tiến trình bị đóng băng hơn TTL, watchdog cũng ngừng chạy. Khi nó tỉnh lại, owner mới có thể đã giữ khóa. Đó là lý do cần owner check và, trong trường hợp quan trọng, fencing/versioning.

## 30. Fencing token: chặn stale owner cập nhật dữ liệu

Owner token ngẫu nhiên bảo vệ renew/release, nhưng không ngăn owner đã hết TTL gửi SQL update muộn.

```text
Worker A fencing=41, bị pause.
Lease A hết, Worker B fencing=42.
B ghi resource version=42.
A tỉnh dậy, cố ghi version=41.
Storage từ chối stale generation.
```

Ví dụ điều kiện tại authoritative database:

```sql
UPDATE protected_resource
SET payload = :new_payload,
    last_fencing = :new_fencing
WHERE id = :resource_id
  AND last_fencing < :new_fencing;
```

Điều kiện phải nguyên tử tại nơi tạo side effect.

**Không dùng UUID random như fencing token:** UUID không có thứ tự. Một sequence từ Redis `INCR` cũng cần đánh giá nguy cơ quay lùi qua primary–replica failover bất đồng bộ khi đòi hỏi strict monotonicity.

## 31. GET token trước khi ghi không đủ ngăn race

Một phương án dễ sai:

```text
T0: A GET lock -> tokenA
T1: lock A hết TTL
T2: B acquire và cập nhật dữ liệu
T3: A tiếp tục cập nhật dữ liệu
```

Việc A thấy đúng token ở T0 **không chứng minh** lease còn hiệu lực tại T3.

Nếu một nghiệp vụ yêu cầu chống stale writes, phải kiểm tra quyền/version tại tài nguyên đích hoặc dùng một cơ chế transactional/coordinator có hợp đồng phù hợp. Một Redis GET riêng lẻ không tạo tính nguyên tử xuyên Redis và PostgreSQL.

## 32. Reactive Redis: timeout không rollback command

Ví dụ:

```java
Mono<Boolean> acquired =
    reactiveRedis.opsForValue()
        .setIfAbsent(
            "lock:job", ownerToken,
            Duration.ofSeconds(30)
        )
        .timeout(Duration.ofMillis(200));
```

Nếu Redis đã thực thi SET nhưng response mất, `Mono` có thể timeout dù key đã được tạo. Reactor cancellation **không rollback Redis write**.

Với reactive lock, còn cần:

- Quản lý cleanup theo success/error/cancellation, ví dụ `usingWhen` khi phù hợp.
- Compare-and-delete nguyên tử khi release.
- Xử lý ambiguous acquisition outcome.
- Không gọi `block()` trên Reactor event loop.
- Không dùng `onErrorResume` để biến mọi timeout thành "lock acquired".

Redis timeout và network reconnect cũng không tự làm non-idempotent operations an toàn để retry.

## 33. Kiểm thử TTL bằng Redis thật

Khi cần xác nhận semantics TTL, không nên chỉ mock `RedisTemplate` bằng một Java Map: mock không tự mô phỏng expiry, atomic commands, event timing và TTL races.

Ví dụ Gradle test dependencies (version phải phù hợp dependency management dự án):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.awaitility:awaitility'
}
```

### 33.1. Spring Boot Testcontainers setup

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.beans.factory.annotation.Autowired;

@Testcontainers
@SpringBootTest
class RedisTtlIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    // Đặt các test methods bên trong lớp này.
}
```

Chỉ dùng Redis test riêng; không chạy các thí nghiệm xóa key, thay CONFIG hoặc fault injection trên Redis đang phục vụ người dùng.

## 34. Test: SET không TTL xóa expiration

Trong integration-test class có field `redis`:

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

@Test
void plainSetRemovesExistingTtl() {
    String key = "test:ttl:" + UUID.randomUUID();

    redis.opsForValue().set(
        key, "v1", Duration.ofMinutes(5)
    );
    assertThat(redis.getExpire(key, TimeUnit.MILLISECONDS))
        .isPositive();

    redis.opsForValue().set(key, "v2");
    assertThat(redis.getExpire(key, TimeUnit.MILLISECONDS))
        .isEqualTo(-1L);

    redis.delete(key);
}
```

Test này cho thấy rõ giá trị `-1` sau lệnh ghi đè; nó không liên quan tới key bị xóa.

## 35. Test: key hết TTL thật

Sử dụng Awaitility để chờ **trạng thái Redis**:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import java.time.Duration;
import java.util.UUID;

@Test
void keyEventuallyExpires() {
    String key = "test:expires:" + UUID.randomUUID();

    redis.opsForValue().set(
        key, "v1", Duration.ofMillis(500)
    );

    await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> Boolean.FALSE.equals(redis.hasKey(key)));

    assertThat(redis.getExpire(
        key, java.util.concurrent.TimeUnit.MILLISECONDS
    )).isEqualTo(-2L);
}
```

Không yêu cầu scheduler chính xác đến mili giây. Test nên có timeout hữu hạn và keyspace riêng để tránh ảnh hưởng từ các test chạy song song.

## 36. Test: owner cũ không gia hạn khóa mới

Kịch bản:

1. A lấy lock TTL 250 ms.
2. Đợi Redis báo khóa A đã mất.
3. B lấy cùng key với TTL dài hơn.
4. A renew bằng token cũ.
5. Script phải trả false và khóa B phải còn.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import java.time.Duration;
import java.util.UUID;

@Test
void expiredOwnerCannotRenewNewOwnersLock() {
    String key = "test:lock:" + UUID.randomUUID();
    RedisLeaseService lease = new RedisLeaseService(redis);

    String tokenA = lease.tryAcquire(
        key, Duration.ofMillis(250)
    );
    assertThat(tokenA).isNotNull();

    await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> Boolean.FALSE.equals(redis.hasKey(key)));

    String tokenB = lease.tryAcquire(
        key, Duration.ofSeconds(10)
    );
    assertThat(tokenB).isNotNull();

    assertThat(
        lease.renew(key, tokenA, Duration.ofSeconds(30))
    ).isFalse();

    assertThat(redis.opsForValue().get(key))
        .isEqualTo(tokenB);
    assertThat(lease.release(key, tokenB)).isTrue();
}
```

Điều này chứng minh Lua không renew nhầm owner. Nó chưa chứng minh worker A không tiếp tục side effect sau khi đã mất lease.

## 37. Test: owner cũ không xóa khóa của B

```java
@Test
void expiredOwnerCannotReleaseNewOwnersLock() {
    String key = "test:unlock:" + UUID.randomUUID();
    RedisLeaseService lease = new RedisLeaseService(redis);

    String tokenA = lease.tryAcquire(
        key, Duration.ofMillis(250)
    );

    await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> Boolean.FALSE.equals(redis.hasKey(key)));

    String tokenB = lease.tryAcquire(
        key, Duration.ofSeconds(10)
    );

    assertThat(lease.release(key, tokenA)).isFalse();
    assertThat(redis.opsForValue().get(key))
        .isEqualTo(tokenB);
    assertThat(lease.release(key, tokenB)).isTrue();
}
```

Nếu dùng `DEL key` vô điều kiện thay vì compare-owner-and-delete, test này có thể bộc lộ lỗi xóa nhầm lease của owner mới.

## 38. Test concurrency, GC pause và failover

Một bộ test nâng cao nên tái hiện thứ tự sự kiện thay vì chỉ dùng `Thread.sleep`:

```text
Worker A acquire lock
A báo đã vào critical section
Test giữ A ở một barrier
Đợi TTL hết hạn thật trên Redis test
Worker B acquire và ghi version mới
Thả barrier để A chạy tiếp
Storage từ chối stale version của A
```

Dùng `CountDownLatch`, `CyclicBarrier` và timeouts hữu hạn để điều phối; xác nhận **trạng thái nghiệp vụ cuối** thay vì chỉ đếm log.

Với bài test failover:

- Dùng Redis Sentinel/Cluster test đúng topology.
- Ghi nhận những ACKed writes/renewals sát thời điểm chuyển role ở ngoài Redis.
- Kiểm tra owner token và TTL trên primary mới.
- Không giả định lock được giữ qua mọi unplanned failover.
- Dùng fencing/versioning hoặc nguồn dữ liệu transactional khi correctness yêu cầu.

Một test nhiều thread trong một JVM không thay thế test nhiều instances/containers nếu code sử dụng local synchronized state.

## 39. Chẩn đoán bằng Redis CLI

Trên Redis test hoặc key có quyền kiểm tra:

```redis
TYPE session:42
EXISTS session:42
PTTL session:42
INFO stats
INFO memory
INFO keyspace
INFO replication
ROLE
```

Các truy vấn này giúp phân biệt key type, availability, expiration, memory pressure và role của node.

### 39.1. MONITOR có ích nhưng không phải công cụ mặc định

`MONITOR` có thể giúp xem lệnh `SET`, `EXPIRE` hoặc `PERSIST` đi qua Redis khi tái hiện bug.

Nhưng MONITOR có overhead và có thể lộ key/value/credentials trong output. Chỉ dùng có giới hạn trong lab hoặc theo quy trình quản trị phù hợp, không bật lâu trên production bận rộn.

### 39.2. SLOWLOG trống không chứng minh không có writer khác

Một `SET` làm mất TTL có thể hoàn thành trong vài microseconds, nên không xuất hiện trong slowlog. SLOWLOG không phải nhật ký thay đổi key đầy đủ.

## 40. Log và metrics nên thu theo semantic operation

Ví dụ log có cấu trúc:

```text
redis.operation=LEASE_RENEW
redis.key_type=job-lock
redis.result=owner_mismatch
redis.requested_ttl_ms=30000
redis.pttl_after_ms=-2
redis.node_role=primary
request_id=<safe-correlation-id>
```

Không log raw session token, Redis password, private keys hoặc toàn bộ key chứa PII.

Metric:

| Chỉ số | Ý nghĩa |
|---|---|
| Key-without-TTL count theo namespace | Phát hiện expiry bị xóa |
| Unexpected key-absent rate | Phát hiện key biến mất ngoài dự kiến |
| Lease renewal success/failure | Theo dõi watchdog |
| Owner token mismatch | Phát hiện stale-owner race |
| Jobs vượt lease duration | Đánh giá lease TTL |
| Expired/evicted keys rate | Phân biệt expiration với eviction |
| Cache hit/miss theo cache name | Đánh giá TTI/fixed TTL |
| Redis reconnect/command timeout | Nhận diện ambiguous results |
| Redis role/failover events | Tương quan với state change |
| API p95/p99 và DB fallback | Tác động nghiệp vụ |

**Không dùng key hoặc session ID làm tag metric:** cardinality cao gây chi phí lưu trữ và rò rỉ metadata.

## 41. Case study: đọc cache liên tục nhưng vẫn hết hạn

Tình huống:

```text
Cache entry TTL = 10 phút
User gọi GET mỗi 30 giây
Sau khoảng 10 phút xảy ra cache miss
```

Nếu Spring Cache đang dùng **fixed TTL**, đây là hành vi đúng.

Quy trình:

1. Xem `RedisCacheConfiguration` thật sự được cache manager dùng.
2. Tạo entry test và đo `PTTL`.
3. Gọi một cache hit, kiểm tra TTL tiếp tục giảm hay được gia hạn.
4. Nếu yêu cầu TTI, cấu hình và kiểm tra `enableTimeToIdle()` cùng Redis GETEX.
5. Xem các đường truy cập khác có đọc qua GET thuần không.
6. Kiểm tra stale cache/invalidation khi entry được giữ lâu hơn.

Đừng kéo dài TTL bằng một lần viết giả ở mỗi HTTP GET nếu chưa xác định side effects và consistency mong muốn.

## 42. Case study: rate limiter counter không có TTL

```redis
INCR rate:login:u42
PTTL rate:login:u42
```

Nếu counter mới, kết quả có thể là -1. Với một fixed-window rate limiter, có thể gắn TTL nguyên tử khi count tăng từ 0 lên 1:

```lua
-- KEYS[1] = counter key
-- ARGV[1] = TTL in ms
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return count
```

**Giới hạn:** nếu key bị lỗi sẵn có count lớn hơn 1 và PTTL=-1, script đơn giản này không sửa marker cũ. Cần migration policy riêng. Retry một increment sau timeout cũng có thể tăng hai lần; nếu nghiệp vụ cần đúng một lần theo request ID thì phải có dedup/idempotency.

Đừng gọi kịch bản này là sliding-window algorithm; nó chỉ minh họa fixed-window counter TTL.

## 43. Case study: session bị xóa trong lúc renew

```text
T0: GET session -> exists
T1: một request logout gọi DEL session
T2: EXPIRE session 1800 -> false
T3: code bỏ qua Boolean và ghi log success
```

Đây có thể là race đúng giữa logout và refresh. **Không tự SET lại session đã bị revoke** chỉ để hàm renew trả thành công.

Với session security, cần bảo đảm renew thất bại không vô tình hồi sinh credentials hết hạn/thu hồi, và absolute max session age vẫn được thực thi.

## 44. Case study: lock được renew đều nhưng job vẫn chạy trùng

```text
A acquire lock 30s
A renew mỗi 10s
A bị GC pause 40s
B acquire khi lease A hết
A tỉnh dậy, tiếp tục ghi
```

Watchdog có thể được cài đặt đúng nhưng vẫn không chạy trong thời gian pause. Cách xử lý không chỉ là giảm khoảng renew:

- Check ownership khi bắt đầu những side effects mới.
- Dừng việc mới khi lease mất hoặc không chắc chắn.
- Dùng fencing/version check tại storage.
- Thiết kế job idempotent và có reconciliation.
- Test delayed stale write khi A quay lại.

Một distributed lock tự xây không tự bảo đảm mutual exclusion nghiêm ngặt qua mọi pause, partition và failover.

## 45. Checklist chẩn đoán theo thứ tự

1. Xác định đúng Redis endpoint, role, logical database, key prefix và serializer.
2. Đọc `PTTL`, phân loại -1 / -2 / số dương.
3. Với -1, tìm SET không expiry, PERSIST, MSET, repository/cache save.
4. Với -2, tìm expiration, DEL/UNLINK/cache invalidation, eviction và key mismatch.
5. Với TTL còn dương, tìm writer đặt expiry ngắn hoặc thời gian tuyệt đối sai.
6. Kiểm tra `EXPIRE` trả true/false; xem NX/XX/GT/LT conditions.
7. Kiểm tra Duration đơn vị giây/ms và khả năng giá trị 0/âm.
8. Nếu cache, xác định fixed TTL hay TTI và GET hay GETEX.
9. Nếu Redis Repository, xem `@TimeToLive`, save paths và shadow copies.
10. Nếu lock, kiểm tra owner-token compare/renew/release atomic.
11. Nếu worker dài, xem GC pause, scheduler lag, job tail latency và fencing.
12. Xem `expired_keys` vs `evicted_keys`, memory pressure và maxmemory policy.
13. Đối chiếu Redis replication lag, failover/Cluster role changes.
14. Tái hiện nguyên command sequence bằng Redis test.
15. Đo lại TTL, số duplicate jobs, cache miss, API latency và tác động nghiệp vụ.

## 46. Những hiểu nhầm cần tránh

### "TTL=-1 là key đã hết hạn"

Sai. Key vẫn tồn tại, nhưng không có expiry.

### "TTL=-2 chỉ có nghĩa Redis cho key hết TTL"

Sai. DEL, eviction, key mismatch hoặc chưa từng tạo key đều có thể gây kết quả này.

### "Mọi lệnh ghi gia hạn TTL"

Sai. HSET/INCR thường giữ TTL hiện có; SET không KEEPTTL có thể xóa.

### "KEEPTTL nghĩa là bắt đầu lại TTL"

Sai. Nó giữ thời điểm hết hạn cũ.

### "GET luôn làm session sống thêm"

Sai. GET không tự gia hạn.

### "Spring Cache @Cacheable mặc định bật TTI"

Sai. Cần cấu hình hỗ trợ TTI và dùng đường đọc phù hợp.

### "Đã gọi expire() thì chắc chắn renew thành công"

Sai. Cần kiểm tra Boolean và các expiry conditions.

### "EXPIRE XX đặt được TTL cho key permanent"

Không. XX yêu cầu key đã có expiry.

### "Key có TTL không thể bị xóa trước hạn"

Sai. Eviction và delete có thể xóa sớm.

### "Không nhận expired event nghĩa là key vẫn còn"

Sai. Event Pub/Sub có thể không đến hoặc đến trễ.

### "Lock hết TTL thì Java thread dừng"

Sai. Redis không hủy công việc của worker.

### "EXPIRE XX đủ để renew lock an toàn"

Sai. Nó không xác minh owner token.

### "UUID random là fencing token tốt"

Không. UUID không biểu diễn thứ tự tăng.

### "Tăng TTL rất lớn giải quyết mọi race"

Không. Nó làm recovery sau worker crash chậm hơn và không chữa stale-owner/failover.

### "Failover luôn giữ các expiry updates đã ACK"

Không bảo đảm với replication bất đồng bộ.

### "Một Redis PTTL khác nhau chắc chắn là Redis lỗi"

Không nếu đọc khác node/role, khác thời điểm hoặc key bị ghi lại.

## 47. Tổng kết

Các sự cố **TTL biến mất**, **không được gia hạn** và **khóa hết hạn ngoài dự kiến** thường đến từ sự khác biệt giữa kỳ vọng của ứng dụng và semantics thực tế của Redis:

- `SET` ghi đè xóa expiry nếu không đặt TTL mới hoặc dùng KEEPTTL.
- `PTTL=-1` nghĩa key tồn tại không expiry; `PTTL=-2` nghĩa key không còn, cần tìm nguyên nhân.
- `GET` không gia hạn; `GETEX` hoặc cơ chế Spring Cache TTI mới thực hiện read-and-touch khi được cấu hình đúng.
- `EXPIRE` có thể thất bại do key không còn hoặc điều kiện NX/XX/GT/LT không thỏa.
- Eviction, delete, serializer mismatch và failover có thể khiến key trông như hết hạn sớm.
- Distributed lock có TTL là **lease tạm thời**; renewal/release phải kiểm tra owner atomically và thao tác quan trọng cần chống stale writes.

**Nguyên tắc chẩn đoán quan trọng nhất:** bắt đầu từ `PTTL` trên đúng key/node, tìm command đã thay đổi value/expiry và kiểm chứng bằng integration test. Đừng sửa một key mất TTL bằng cách tăng timeout và đừng sửa một stale-owner race bằng EXPIRE vô điều kiện.

## Tài liệu tham khảo

- [Redis Documentation — SET](https://redis.io/docs/latest/commands/set/)
- [Redis Documentation — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis Documentation — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/)
- [Redis Documentation — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis Documentation — PTTL](https://redis.io/docs/latest/commands/pttl/)
- [Redis Documentation — GETEX](https://redis.io/docs/latest/commands/getex/)
- [Redis Documentation — PERSIST](https://redis.io/docs/latest/commands/persist/)
- [Redis Documentation — INCR](https://redis.io/docs/latest/commands/incr/)
- [Redis Documentation — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis Documentation — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis Documentation — Distributed locks](https://redis.io/docs/latest/develop/use/patterns/distributed-locks/)
- [Redis Documentation — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis Documentation — INFO](https://redis.io/docs/latest/commands/info/)
- [Spring Data Redis Reference — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis Reference — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis Reference — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis Reference — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis API — RedisCacheConfiguration](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/cache/RedisCacheConfiguration.html)
- [Spring Data Redis API — ValueOperations](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ValueOperations.html)
- [Spring Data Redis API — DefaultRedisScript](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/script/DefaultRedisScript.html)
- [Testcontainers — Java](https://java.testcontainers.org/)
- [Awaitility — Documentation](https://github.com/awaitility/awaitility/wiki/Usage)
