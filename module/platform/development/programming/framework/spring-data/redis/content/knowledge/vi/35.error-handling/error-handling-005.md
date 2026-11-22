# Lỗi xác thực, quyền ACL, bộ nhớ và chế độ chỉ đọc

Trong ứng dụng **Spring Data Redis**, thao tác `GET`, `SET`, `HSET`, `XADD` hoặc `@Cacheable` có thể thất bại dù code Java đúng và Redis vẫn mở cổng kết nối. Bốn nhóm lỗi phổ biến là **xác thực**, **quyền ACL**, **giới hạn bộ nhớ** và **ghi tới node chỉ đọc**. Chúng đều có thể được báo dưới dạng exception từ Lettuce/Spring Data Redis, nhưng nguyên nhân và cách khôi phục rất khác nhau.

Ví dụ cùng một lệnh:

```java
stringRedisTemplate.opsForValue()
        .set("app:product:42", "active");
```

có thể gặp:

```text
NOAUTH Authentication required.
WRONGPASS invalid username-password pair or user is disabled.
NOPERM this user has no permissions to run the 'set' command
OOM command not allowed when used memory > 'maxmemory'.
READONLY You can't write against a read only replica.
```

Không nên xử lý cả năm trường hợp bằng một đoạn `catch` rồi retry vô hạn. `WRONGPASS` đòi hỏi sửa secret/tài khoản; `NOPERM` đòi hỏi điều chỉnh quyền tối thiểu; `OOM` đòi hỏi xem chính sách bộ nhớ/retention; `READONLY` đòi hỏi sửa định tuyến đến primary. Việc retry mù quáng vừa không giải quyết nguyên nhân vừa có thể làm hệ thống đang quá tải chịu thêm áp lực.

Bài học trình bày cách phân loại, cấu hình an toàn trong Spring Boot/Spring Data Redis, điều tra bằng Redis CLI, xử lý lỗi ở code, chiến lược fallback và các bài thực hành trong môi trường cô lập.

## 1. Bản đồ nhanh: lỗi phát sinh ở lớp nào?

```text
Spring Service / Cache / Repository / Stream Listener
                         |
                         v
               RedisTemplate / ReactiveRedisTemplate
                         |
                         v
            RedisConnectionFactory (thường Lettuce)
                         |
                     TCP / TLS
                         |
                         v
                       Redis
               /          |           \
          Authentication  Authorization  Node state
           NOAUTH /       NOPERM         READONLY
           WRONGPASS                     / OOM
```

Một số lỗi có thể phát sinh **trước khi gửi lệnh Redis** (DNS, TLS, kết nối); những lỗi đang xét thường xuất hiện khi Redis đã nhận được kết nối hoặc command và quyết định không cho phép xử lý theo trạng thái của nó.

| Phản hồi Redis | Ý nghĩa chính | Nhóm cần điều tra |
|---|---|---|
| `NOAUTH` | Client chưa hoàn thành xác thực cần thiết | Credentials/client authentication handshake |
| `WRONGPASS` | Cặp user/password không hợp lệ hoặc user bị vô hiệu hóa | Secret, username, ACL user state |
| `NOPERM` | Đã xác thực nhưng thiếu quyền command, key hoặc channel | ACL rules, key prefix, Pub/Sub channels |
| `OOM` | Redis không thể cấp thêm bộ nhớ theo giới hạn/chính sách hiện có | `maxmemory`, eviction, TTL, dung lượng |
| `READONLY` | Ghi tới replica/read-only Redis node | Node role, Sentinel/Cluster routing, failover |
| `MOVED` / `ASK` | Cần chuyển command sang node khác của Redis Cluster | Slot map, topology refresh; không phải ACL |
| `CROSSSLOT` | Command nhiều key không hợp lệ theo hash slot | Thiết kế key/command; không phải OOM |
| Timeout/connection refused | Không nhận được phản hồi/không kết nối được | Network, TLS, DNS, Redis health, pool |

**Hai câu hỏi đầu tiên khi chẩn đoán:** lỗi này do server Redis **từ chối một command đã nhận**, hay ứng dụng **không kết nối/không biết command đã thực thi chưa**? Sự phân biệt ảnh hưởng trực tiếp đến quyết định retry.

## 2. Spring Data Redis truyền lỗi như thế nào?

Spring Data Redis có lớp trừu tượng và cơ chế dịch ngoại lệ từ Redis driver vào hệ thống `DataAccessException` của Spring.

Một đường đi điển hình:

```text
Redis server trả lỗi
         |
         v
Lettuce command error (chẳng hạn RedisCommandExecutionException)
         |
         v
Spring Data Redis exception translation
         |
         v
DataAccessException / RedisSystemException / exception phù hợp
         |
         v
Service, Controller, Cache Interceptor
```

Các tên exception cụ thể phụ thuộc phiên bản Spring Data Redis, driver và API được gọi. **Không nên giả định mọi `NOAUTH` hay `NOPERM` luôn được ánh xạ vào một class Spring duy nhất trên mọi phiên bản.** Khi điều tra, hãy ghi nhận:

- Loại exception ngoài cùng mà service nhận được.
- Loại và nội dung nguyên nhân sâu nhất (*root cause*).
- Redis error code/message nếu thực sự có phản hồi.
- Command/operation đang thực thi: đọc, ghi, cache put, stream ACK...
- Redis endpoint và node role (tránh log đầy đủ thông tin nhạy cảm).
- Thời điểm, instance, version cấu hình và tình trạng failover.

Ví dụ bắt lỗi ở tầng kỹ thuật:

```java
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisStatusStore {

    private final StringRedisTemplate redis;

    public RedisStatusStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStatus(String userId, String status) {
        try {
            redis.opsForValue().set(
                    "app:user:" + userId + ":status", status);
        } catch (DataAccessException ex) {
            // Ghi nhận operation, namespace và loại lỗi, không log secret.
            // Truyền lỗi cho chính sách xử lý ở tầng phù hợp.
            throw ex;
        }
    }
}
```

Đoạn `catch` minh họa ranh giới quan sát; trong sản phẩm thật, nên thêm structured logging/metrics hoặc một error classifier tập trung. Việc bắt rồi ném lại không cần thiết nếu không có tác dụng giám sát.

Trong API reactive, lỗi đến qua tín hiệu `onError`:

```java
return reactiveStringRedisTemplate.opsForValue()
        .get("app:user:" + userId + ":status")
        .doOnError(error -> recordRedisFailure("GET", error));
```

Không biến tất cả `onError` thành `Mono.empty()`: đó sẽ làm lỗi xác thực hoặc Redis offline trông giống một **cache miss** hợp lệ.

## 3. NOAUTH: client chưa được xác thực

Một phản hồi thường gặp:

```text
NOAUTH Authentication required.
```

Nó có nghĩa Redis yêu cầu xác thực trước khi chấp nhận command đang được gửi. Những nguyên nhân thường thấy:

1. Ứng dụng không cung cấp username/password dù Redis đã bật xác thực.
2. Một connection được mở nhưng chưa thực hiện AUTH/HELLO authentication đúng cách.
3. Cấu hình môi trường bị thiếu secret hoặc một profile ghi đè thông số.
4. Connection mới sau failover/reconnect không nhận được cùng cấu hình auth.
5. Có hai connection factory khác nhau; chỉ một factory có credentials.
6. Một Redis endpoint mới trong topology sử dụng thiết lập auth khác dự kiến.

Với ứng dụng Spring Boot, trước tiên xác định **bean RedisConnectionFactory thực tế** mà RedisTemplate/CacheManager/Stream listener đang dùng. Một service đọc Redis được nhưng service khác nhận NOAUTH đôi khi không phải Redis server bất ổn, mà do hai bean/ứng dụng trỏ vào hai cấu hình khác nhau.

### 3.1. Kiểm tra bằng Redis CLI mà không lộ password

Ví dụ trên môi trường được phép truy cập:

```bash
redis-cli -h redis.internal -p 6379 --user app_rw --askpass PING
```

`--askpass` cho phép nhập password theo prompt thay vì viết password trực tiếp trong history của shell. Nếu Redis yêu cầu TLS, thêm các tùy chọn TLS/chứng chỉ được cấp cho môi trường đó; đừng bỏ qua TLS chỉ để làm lệnh chẩn đoán chạy được.

Sau khi xác thực, một số ACL command như `ACL WHOAMI` có thể giúp xác nhận tên user đang có hiệu lực nếu tài khoản được phép dùng command đó:

```bash
redis-cli -h redis.internal -p 6379 --user app_rw --askpass ACL WHOAMI
```

`ACL WHOAMI` giúp xem user hiện tại; nó **không tự chứng minh user có quyền thực hiện mọi command**.

### 3.2. NOAUTH khác WRONGPASS

`NOAUTH` nhấn mạnh rằng command được gửi khi kết nối chưa xác thực hợp lệ. `WRONGPASS` xuất hiện khi thông tin xác thực đã cung cấp nhưng không được Redis chấp nhận. Cả hai cùng thuộc nhóm xác thực, nhưng cách xử lý tập trung vào việc “đã gửi credentials chưa?” và “credentials có hợp lệ không?”.

Nếu error message không phân biệt rõ do driver bọc exception, xem root cause và thử kết nối bằng cùng username/password qua kênh quản trị an toàn.

## 4. WRONGPASS: sai thông tin xác thực hoặc user bị khóa

Redis có thể trả:

```text
WRONGPASS invalid username-password pair or user is disabled.
```

Những khả năng cần kiểm tra:

- Username khác tài khoản thực tế trong ACL.
- Password đã xoay vòng nhưng application instance còn dùng secret cũ.
- Secret được thêm newline/whitespace không mong muốn khi inject từ file.
- User đã bị đặt `off` hoặc xóa khỏi ACL.
- Application vẫn dùng kiểu password-only dành cho user `default` trong khi Redis đã áp dụng ACL user riêng.
- Một deployment mới trỏ sang Redis service khác có user/password khác.
- Client dùng URI có password bị encode/parse sai.
- Tài khoản có nhiều password trong quá trình rotation nhưng application dùng password đã bị thu hồi.

### Redis ACL và user default

Các Redis phiên bản hỗ trợ ACL cho phép tài khoản có **username, password và tập quyền**. Tài khoản `default` là một user ACL đặc biệt; nhiều cấu hình cũ kết nối chỉ bằng password và ngầm định sử dụng default user.

Khi chuyển sang user riêng, ứng dụng cần cấu hình **cả username lẫn password**. Không nên sửa lỗi bằng cách bật rộng quyền user default hoặc vô hiệu hóa authentication trên server production.

### Quy trình kiểm tra khi thay secret

1. Xác định secret version đang được deployment sử dụng, không in giá trị ra log.
2. So sánh user/endpoint được gắn với secret đó.
3. Kiểm tra user đang `on` và password đã được cấp hợp lệ qua đường quản trị.
4. Nếu vừa rotate password, xem từng pod/instance có được cập nhật/restart để mở connection mới không.
5. Xác nhận application có thể tạo **kết nối mới** sau rotation, không chỉ tái sử dụng connection đã mở trước.
6. Thu hồi secret cũ theo kế hoạch sau khi các client đã chuyển đổi.

**Không retry nhiều lần WRONGPASS** với cùng credentials. Lỗi sẽ không tự biến mất nếu secret vẫn sai và có thể tạo log flood hoặc chính sách chặn xác thực của môi trường quản lý.

## 5. Cấu hình credentials và TLS trong Spring Boot

Ví dụ cấu hình Spring Boot cho Redis một endpoint:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      username: app_rw
      password: "REPLACE_VIA_ENV_OR_SECRET_MANAGER"
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 3s
```

Chuỗi `REPLACE_VIA_ENV_OR_SECRET_MANAGER` là ký hiệu minh họa, **không phải password để đưa vào production**. Giá trị thật nên đi từ secret manager hoặc environment property tương ứng, không commit vào Git.

Trong các phiên bản Spring Boot hiện đại, Redis properties thường dùng prefix `spring.data.redis`. Khi ứng dụng dùng phiên bản khác, phải đối chiếu tên property chính xác với BOM/configuration metadata đang chạy.

Nếu không dùng auto-configuration, có thể cấu hình tường minh connection factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisConnectionConfig {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration standalone =
                new RedisStandaloneConfiguration(
                        "redis.internal", 6379);

        standalone.setUsername("app_rw");
        standalone.setPassword(
                org.springframework.data.redis.connection.RedisPassword
                        .of("ONLY_A_LAB_PLACEHOLDER"));

        // Chỉ minh họa username/password wiring.
        // Production phải lấy secret và bật TLS theo môi trường.
        return new LettuceConnectionFactory(standalone);
    }
}
```

Đoạn Java có password **placeholder** và chưa cấu hình TLS; không dùng nguyên xi cho production. Nếu Spring Boot đã tạo LettuceConnectionFactory đúng, nên sử dụng bean đó thay vì tạo thêm factory thứ hai dẫn đến cấu hình không nhất quán.

### 5.1. Vì sao lỗi TLS đôi khi bị nhầm thành lỗi xác thực?

TLS handshake lỗi thường tạo exception ở tầng network/SSL trước khi Redis xử lý AUTH. Một số log tổng hợp có thể chỉ ghi “failed to connect to Redis”. Cần phân biệt:

- Sai CA certificate/hostname → handshake fail.
- Sai username/password → Redis trả WRONGPASS.
- Không gửi AUTH → Redis trả NOAUTH khi command yêu cầu xác thực.
- Sai ACL permission → Redis trả NOPERM sau khi auth thành công.

Không tắt certificate verification hoặc chuyển sang kết nối plaintext để giải quyết một lỗi mà chưa xác định đúng nguyên nhân.

## 6. NOPERM: đã xác thực nhưng thiếu quyền ACL

Một user có thể đăng nhập thành công nhưng bị Redis từ chối command:

```text
NOPERM this user has no permissions to run the 'set' command
```

hoặc bị từ chối do key pattern/channel pattern không được phép.

Redis ACL có thể giới hạn:

1. **Commands/categories:** user được chạy `GET`, `SET`, `DEL`, `XADD` hay các nhóm command nào.
2. **Keys:** user được truy cập key nào, ví dụ `app:cache:*`.
3. **Pub/Sub channels:** user được publish/subscribe tới channel nào.
4. **Read/write key permissions:** một số cấu hình ACL có thể giới hạn quyền đọc/ghi theo key pattern.
5. **Trạng thái user:** `on`/`off` và các password hợp lệ.

Thế nên `NOPERM` không nhất thiết là “thiếu quyền GET”. Nó có thể là:

```text
GET app:product:42           -> OK
SET app:product:42 value     -> NOPERM command
GET other:product:42         -> NOPERM key pattern
SUBSCRIBE internal:alerts    -> NOPERM channel
```

### 6.1. Nguyên tắc cấp quyền tối thiểu

Không mở quyền `+@all` và `~*` chỉ để lỗi biến mất. Thay vào đó, liệt kê **chính xác operations** ứng dụng dùng và prefix key/channel mà nó sở hữu.

Ví dụ user chỉ đọc/ghi key dưới `app:demo:*` có thể được cấp command cần thiết theo mô hình lab:

```text
ACL SETUSER app_demo on >LAB_ONLY_CHANGE_ME ~app:demo:* +ping +get +set +del +expire +ttl
```

Đây là cú pháp Redis ACL dùng khi nhập vào **redis-cli interactive session** từ tài khoản quản trị trên Redis lab. Không dán `>...` thẳng vào shell một cách bất cẩn vì ký tự `>` có thể là toán tử redirect của shell. Không dùng mật khẩu mẫu cho môi trường thật.

Dùng user này có thể `GET`/`SET` trong namespace được phép, nhưng `HSET`, `XADD` hoặc truy cập key ở namespace khác có thể bị từ chối — đúng theo nguyên tắc least privilege.

### 6.2. ACL command dùng để chẩn đoán

Tài khoản quản trị được ủy quyền có thể xem:

```text
ACL LIST
ACL GETUSER app_demo
ACL CAT
ACL DRYRUN app_demo GET app:demo:key
ACL DRYRUN app_demo SET app:demo:key value
ACL LOG
```

- `ACL GETUSER` cho biết cấu hình user, trạng thái và những ACL rules được áp dụng.
- `ACL CAT` cho biết các nhóm command.
- `ACL DRYRUN` giúp thử theo quyền của một user mà không cần thực thi command thật; hữu ích để chẩn đoán rule.
- `ACL LOG` cung cấp thông tin về các lần ACL denial/auth failure theo Redis version và cấu hình.

Các lệnh ACL quản trị có thể bị chặn trong managed Redis hoặc yêu cầu tài khoản đặc quyền. **Không cấp quyền ACL admin cho application user** chỉ để ứng dụng tự chẩn đoán. Cần tách tài khoản vận hành khỏi tài khoản nghiệp vụ.

## 7. Quyền ACL nên được thiết kế theo Redis operations thực tế

Spring Data Redis có nhiều API; một phép gọi ở mức framework có thể tương ứng với **nhiều Redis commands**.

| Tính năng Spring Data Redis | Redis commands có thể liên quan | Rủi ro ACL |
|---|---|---|
| `opsForValue().get` | `GET` | Thiếu quyền đọc/key prefix |
| `opsForValue().set(..., ttl)` | `SET` và tùy chọn expiration | Thiếu `SET`/quyền ghi key |
| `opsForValue().increment` | `INCR` | User chỉ có `GET`/`SET` vẫn có thể thiếu `INCR` |
| `opsForHash()` | `HGET`, `HSET`, `HGETALL`, `HINCRBY` | Quyền Hash commands và key pattern |
| `opsForSet()` | `SADD`, `SREM`, `SISMEMBER`, `SMEMBERS` | Thiếu một thao tác thành viên |
| `opsForZSet()` | `ZADD`, `ZRANGE`, `ZREM`... | Quyền Sorted Set |
| `RedisCacheManager` | `GET`, `SET`, `DEL`, `SCAN`/`KEYS` tùy writer/clear strategy | Cache hit được nhưng `evict`/`clear` bị từ chối |
| Redis Repository | `HSET`, `HGETALL`, `DEL`, `SADD`/`SREM`, TTL và metadata commands | Keyspace/index ngoài namespace dự kiến |
| Redis Streams producer | `XADD` | Đọc stream được nhưng không phát message được |
| Stream consumer group | `XREADGROUP`, `XACK`, `XPENDING`, `XAUTOCLAIM`... | Nhận message được nhưng ACK/reclaim bị NOPERM |
| Pub/Sub | `PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE` | Cần quyền command và channel pattern phù hợp |
| Lua script | `EVAL`/`EVALSHA`/`FCALL` và các lệnh dùng trong script tùy Redis/ACL | Quyền script và key/command bị từ chối |
| Rate limiter | `INCR`, `EXPIRE`, `EVAL` hoặc script khác | Chỉ cho `GET`/`SET` là không đủ |

Bảng không phải danh sách lệnh đầy đủ cho mọi phiên bản framework. Muốn cấp quyền chuẩn, hãy ghi lại chính xác các đường Spring Cache/Repository/Stream mà ứng dụng thực sự thực hiện, thử trên môi trường tương đương và áp dụng quy tắc least privilege.

### 7.1. Cache hit được nhưng cache eviction lỗi

Một `@Cacheable` có thể chỉ cần `GET` khi hit; còn một `@CacheEvict` cần `DEL` hoặc thao tác xóa tương đương. Nếu ACL chỉ cấp `GET`:

```text
GET app:cache:product:42 -> OK
DEL app:cache:product:42 -> NOPERM
```

Kết quả là dữ liệu cache cũ không được xóa. Khi có `transactionAware()`, eviction có thể được hoãn tới callback sau database commit; nếu Redis từ chối lúc đó, **database đã commit nhưng cache vẫn stale**.

### 7.2. Redis Streams: đọc được chưa chắc ACK được

`XREADGROUP` và `XACK` là hai command khác nhau. Consumer có thể nhận message thành công nhưng bị `NOPERM` lúc ACK. Message sẽ còn pending và có thể được giao lại khi recovery.

Không thể sửa bằng cách “bỏ ACK” nếu yêu cầu là at-least-once processing có recovery; phải cấp quyền tương ứng hoặc thay đổi kiến trúc/identity. Cần có xử lý idempotency để chịu được message được giao lại.

### 7.3. Pub/Sub có channel ACL riêng

ACL key pattern `~app:*` không đồng nghĩa user được subscribe vào các channel `app:*`. Redis ACL còn có **channel patterns**, thường qua cú pháp `&pattern`, cùng quyền cho các Pub/Sub commands.

Một account có `GET app:x` thành công nhưng `SUBSCRIBE app:events` bị từ chối không phải lỗi Redis Stream; đó là hai nhóm tài nguyên khác nhau.

### 7.4. Script không phải “đường vòng” ACL

Không nên dùng Lua để né hạn chế của ACL. Redis kiểm soát quyền command và key phù hợp với cơ chế script. Nếu một user bị từ chối quyền thao tác dữ liệu, tự bọc những lệnh đó trong `EVAL` không phải một mô hình cấp quyền an toàn.

## 8. Tách user theo use case khi cần

Một service có thể làm nhiều việc: đọc cache, cập nhật cache, phát sự kiện Stream, chạy job admin. Dùng một Redis account có quyền rộng cho mọi thao tác tăng diện tích ảnh hưởng nếu credentials bị lộ.

Cách phân nhóm có thể phù hợp:

```text
app_cache_rw:
  chỉ dùng app:cache:*
  GET, SET, DEL, TTL, SCAN/expire khi thực sự cần

app_events_producer:
  chỉ dùng app:events:*
  XADD và commands phục vụ producer

app_events_consumer:
  chỉ dùng app:events:*
  XREADGROUP, XACK, pending/reclaim phù hợp

redis_ops_admin:
  quyền quản trị qua kênh vận hành riêng
  ACL/CONFIG/CLUSTER theo chính sách hạ tầng
```

Nếu tách accounts, Spring Data Redis có thể cần các `LettuceConnectionFactory`/template beans riêng theo username/permission. Phải chọn đúng bean bằng tên/`@Qualifier` và bảo đảm service không nhầm factory cache với factory producer.

Tách account làm cấu hình phức tạp hơn; chỉ triển khai khi giúp giảm rủi ro và có phương án secret rotation, lifecycle, monitoring rõ ràng. Không tạo quá nhiều identity mà không có ownership.

## 9. OOM: Redis đã tới giới hạn bộ nhớ hoặc không thể evict

Một lỗi thường gặp:

```text
OOM command not allowed when used memory > 'maxmemory'.
```

Redis đang từ chối một thao tác cần thêm bộ nhớ theo cấu hình hiện có. Đây không nhất thiết là hệ điều hành đã hết toàn bộ RAM; cần kiểm tra **Redis maxmemory policy, memory accounting, keyspace và dữ liệu có thể evict**.

Những yếu tố:

- `maxmemory`: giới hạn bộ nhớ mà Redis xét khi áp dụng eviction policy.
- `maxmemory-policy`: chính sách xử lý khi bộ nhớ tới ngưỡng.
- TTL/expiration: key nào có thời hạn sống, đã được dọn hết hạn chưa.
- Eviction: Redis loại bỏ những key nào để nhường chỗ.
- Dung lượng key/collection, stream retention, dữ liệu trong các Hash/ZSet/List lớn.
- Fragmentation, client buffers, replication/AOF buffers và các khoản memory overhead.
- Managed Redis quota/giới hạn riêng ngoài Redis `maxmemory`.

**OOM khác với NOPERM.** `NOPERM` là user không được phép gọi command dù Redis còn nhiều memory. `OOM` là Redis không thể đáp ứng nhu cầu cấp phát theo chính sách bộ nhớ, dù user có đầy đủ quyền.

### 9.1. Các lệnh quan sát bộ nhớ

Tài khoản được phép có thể dùng:

```bash
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO memory
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO stats
redis-cli -h redis.internal -p 6379 --user ops_reader --askpass INFO keyspace
```

Khi có quyền cấu hình:

```text
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
MEMORY STATS
MEMORY USAGE app:cache:product:42
```

Những command như `CONFIG`, `MEMORY` hoặc `INFO` có thể bị hạn chế bởi ACL/managed service; thiếu quyền để chẩn đoán không phải lý do mở quyền admin cho app user.

Một số chỉ số hữu ích:

| Chỉ số | Ý nghĩa cơ bản |
|---|---|
| `used_memory` | Bộ nhớ Redis đang báo sử dụng theo cách accounting của Redis |
| `used_memory_rss` | Bộ nhớ resident của tiến trình theo OS, có thể cao hơn used_memory |
| `maxmemory` | Ngưỡng áp dụng chính sách bộ nhớ Redis |
| `maxmemory_policy` | Chính sách khi chạm ngưỡng |
| `mem_fragmentation_ratio` | Tín hiệu về fragmentation/overhead, không phải công thức dự báo OOM duy nhất |
| `evicted_keys` | Số key bị Redis evict do policy (cumulative counter) |
| `expired_keys` | Số key hết hạn do TTL (cumulative counter) |
| `keyspace_hits/misses` | Chỉ số đọc Redis, không tự chứng minh dữ liệu đúng |
| `MEMORY USAGE key` | Ước lượng bộ nhớ một key đang chiếm theo Redis |
| Client/replication buffers | Bộ nhớ hạ tầng có thể nằm ngoài tập dữ liệu user keys |

Trong một số phiên bản/cấu hình, bộ nhớ bộ đệm được loại trừ khỏi phép so sánh maxmemory để tránh vòng lặp eviction khi replication/AOF phát sinh thêm buffer; dù vậy, tiến trình vẫn cần **RAM thực tế** cho chúng. Vì thế `maxmemory` không đồng nghĩa một cam kết rằng `used_memory_rss` sẽ không vượt ngưỡng đó.

## 10. Hiểu maxmemory-policy trước khi sửa OOM

Các chính sách Redis phổ biến:

| Policy | Ý tưởng | Hậu quả cần biết |
|---|---|---|
| `noeviction` | Không chủ động evict key để nhận write cần thêm memory | Những write cần bộ nhớ có thể bị từ chối bằng OOM |
| `allkeys-lru` | Evict key theo LRU xấp xỉ trong toàn bộ keyspace | Key quan trọng không có TTL vẫn có thể bị evict |
| `allkeys-lfu` | Evict theo tần suất truy cập xấp xỉ | Không được hiểu là bảo đảm giữ key nóng tuyệt đối |
| `allkeys-random` | Chọn key ngẫu nhiên để evict | Dễ dự đoán policy nhưng khó ưu tiên giá trị nghiệp vụ |
| `volatile-lru` | Chỉ chọn key có TTL, theo LRU xấp xỉ | Key không TTL không là ứng viên |
| `volatile-lfu` | Chỉ chọn key có TTL, theo LFU xấp xỉ | Nếu không có đủ key TTL, OOM vẫn có thể xuất hiện |
| `volatile-ttl` | Ưu tiên key có TTL còn ngắn để evict | Không thay thế chủ động đặt TTL đúng |
| `volatile-random` | Evict ngẫu nhiên trong key có TTL | Không thể chọn key không TTL |
| `allkeys-lru` vs `volatile-*` | Toàn keyspace vs chỉ key có TTL | Quyết định an toàn dữ liệu/caching khác nhau |

Các policy cụ thể hỗ trợ còn phụ thuộc phiên bản Redis. Không nên đổi policy chỉ vì thấy một câu trả lời trên diễn đàn mà chưa hiểu dữ liệu nào đang lưu trong cùng Redis instance.

### 10.1. Tại sao volatile-* vẫn có thể OOM?

Giả sử keyspace có:

```text
cache:product:*   -> 10.000 key có TTL
stream:orders     -> 1 stream lớn, không TTL
leaderboard:all   -> 1 ZSet lớn, không TTL
session:*         -> nhiều Hash không TTL
```

Khi dùng `volatile-lru`, Redis chỉ có thể lựa chọn key có expiration làm ứng viên eviction. Nếu những key này đã bị loại hết mà bộ nhớ vẫn áp lực vì stream/ZSet/Hash không TTL, write mới vẫn có thể thất bại.

**Không phải cứ bật eviction policy là Redis luôn tìm được key để giải phóng.** Đừng dựa vào volatile policy để quản lý một stream không có retention.

### 10.2. noeviction khi Redis lưu dữ liệu không dễ mất

Với Redis là nguồn sự thật cho counter/tác vụ hoặc dữ liệu chưa lưu bền vững ở nơi khác, evict một key có thể làm mất trạng thái nghiệp vụ. `noeviction` có thể được chọn để tránh Redis tự loại key, đổi lại **ứng dụng phải xử lý write failure/OOM**, theo dõi memory chặt và có kế hoạch mở rộng.

Chọn `allkeys-lru` chỉ phù hợp khi **mọi key trong instance đều có thể bị loại** theo hợp đồng hệ thống, ví dụ một Redis chuyên dụng làm cache có thể tái tạo từ database.

Không nên để Redis instance chứa đồng thời cache có thể mất và trạng thái nghiệp vụ không được mất, rồi bật eviction toàn keyspace mà không phân chia trách nhiệm.

## 11. TTL, eviction và expiration là ba khái niệm khác nhau

- **TTL**: thời gian còn lại trước khi một key hết hạn.
- **Expiration**: Redis loại bỏ key khi thời hạn hết (có thể lazy hoặc active).
- **Eviction**: Redis loại key do áp lực bộ nhớ và maxmemory policy.

`EXPIRE key 60` không có nghĩa Redis sẽ lập tức giải phóng memory khi hết 60 giây tại một mốc chính xác theo realtime. Redis có cơ chế xử lý expiration, nhưng không phải hệ thống scheduler có SLA millisecond cho tác vụ nghiệp vụ.

Mặt khác, Redis có thể evict một key **trước TTL** nếu policy cho phép và bộ nhớ bị áp lực.

### 11.1. Ví dụ Spring Data Redis đặt TTL

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TokenCache {

    private final StringRedisTemplate redis;

    public TokenCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String key, String value) {
        redis.opsForValue().set(
                "app:token:" + key,
                value,
                Duration.ofMinutes(10));
    }
}
```

`SET` kèm TTL trong một lệnh giúp tránh khoảng lỗi giữa ghi value và một lệnh `EXPIRE` riêng.

Tuy nhiên, chỉ đặt TTL không đủ nếu một writer khác về sau gọi `SET key value` không kèm TTL và reset expiration. Đường ghi phải tuân thủ cùng quy ước lifecycle.

### 11.2. Cẩn trọng với dữ liệu nhạy cảm

Dù TTL làm key hết hạn, không nên tự suy luận đó là một bảo đảm “xóa dữ liệu an toàn” ở mọi bản sao, backup và log. Với token hoặc thông tin cá nhân, cần tính cả thời gian lưu trong persistence, replicas, snapshots và hệ thống quan sát.

## 12. Giảm áp lực bộ nhớ bằng thiết kế dữ liệu

Khi gặp OOM, tăng `maxmemory` có thể chỉ hoãn vấn đề nếu dữ liệu tăng không giới hạn.

Các hướng thiết kế cần xem:

1. **Cache TTL:** mỗi nhóm cache có thời gian sống dựa trên yêu cầu freshness và tốc độ thay đổi.
2. **Giới hạn cardinality:** tránh lưu vô hạn member trong một Set/Hash/ZSet.
3. **Stream retention:** `XTRIM` hoặc cấu hình `XADD ... MAXLEN` phù hợp với nhu cầu replay của consumer groups.
4. **Key naming:** prefix/version rõ ràng để có thể biết dữ liệu nào có thể dọn.
5. **Payload size:** không lưu cả object graph lớn khi chỉ cần vài field.
6. **Serializer:** cân nhắc overhead JSON/JDK serialization và khả năng migration.
7. **Big keys/hot keys:** một key khổng lồ có thể gây memory/CPU/latency bất thường.
8. **Phân tách workloads:** cache có thể evict khác với dữ liệu phiên/queue cần độ bền.
9. **Backpressure:** giới hạn tốc độ producer/consumer thay vì đẩy dữ liệu vào Redis vô hạn.
10. **Capacity planning:** đo tăng trưởng giờ cao điểm, retention và headroom cho failover/replication.

Ví dụ với Redis Streams:

```text
Producer XADD -> stream dài ra
Consumer XACK -> message không còn pending của group
XACK KHÔNG tự xóa entry vật lý khỏi stream
```

Nếu chỉ ACK mà không có retention/trim, stream có thể tiếp tục tăng tới khi Redis OOM. Nhưng trim quá sớm có thể xóa entry mà consumer chậm còn cần để retry/replay. Phải cân bằng dung lượng và thời gian lưu theo consumer group chậm nhất, không chọn MAXLEN tùy tiện.

### 12.1. Tránh chữa OOM bằng FLUSHDB

`FLUSHDB` và `FLUSHALL` xóa dữ liệu quy mô lớn, có thể ảnh hưởng mọi ứng dụng chia sẻ Redis. **Không dùng chúng làm phản xạ đầu tiên khi thấy OOM.** Cần xác định dữ liệu nào có thể evict/xóa, có nguồn tái tạo hay không và thao tác dọn có thể thực hiện theo namespace/partition có kiểm soát.

`KEYS *` trên Redis production lớn cũng không thích hợp để chẩn đoán vì có thể làm Redis bận quét. Dùng `SCAN` theo cursor và giới hạn tốc độ; trên Redis Cluster cần quét các primary phù hợp chứ không chỉ một seed node.

## 13. OOM ở Redis có tác động thế nào tới ứng dụng Spring?

Tác động phụ thuộc command đang chạy:

- `GET` có thể vẫn đọc được dù các write cần thêm bộ nhớ bị từ chối.
- `SET`/`HSET`/`XADD` có thể bị từ chối nếu cần thêm memory và policy không thể evict.
- `DEL` có thể giúp giải phóng dữ liệu và vẫn có thể được phép chạy.
- Cache miss dẫn đến cache fill `SET` bị OOM; service có thể thất bại dù **database đọc thành công**.
- Redis Stream producer `XADD` bị OOM: sự kiện không được ghi, có thể phá pipeline nếu không có nguồn phát lại.
- Cache invalidation xóa key có thể vẫn hoạt động, nhưng không nên dựa vào điều này như bảo đảm tuyệt đối giữa các phiên bản/trạng thái Redis.

### 13.1. Cache failure và source-of-truth

Nếu Redis chỉ là cache của database, có thể chọn **bỏ qua lỗi cache write** và trả dữ liệu nguồn trong điều kiện đã kiểm soát:

```java
public ProductView findById(long id) {
    String key = "app:cache:product:" + id;

    try {
        String payload = redis.opsForValue().get(key);
        if (payload != null) {
            return decodeProduct(payload);
        }
    } catch (org.springframework.dao.DataAccessException ex) {
        recordCacheFailure("GET", ex);
    }

    ProductView fromDb = repository.findById(id)
            .map(ProductView::from)
            .orElseThrow();

    try {
        redis.opsForValue().set(
                key,
                encodeProduct(fromDb),
                Duration.ofMinutes(5));
    } catch (org.springframework.dao.DataAccessException ex) {
        recordCacheFailure("SET", ex);
        // DB là nguồn thật; không coi cache fill là điều kiện thành công.
    }

    return fromDb;
}
```

Ví dụ giả định đã có `repository`, `encodeProduct`, `decodeProduct` và `recordCacheFailure` theo ứng dụng; đây là mảnh minh họa cho **chính sách best-effort cache**, không phải class độc lập có thể biên dịch ngay.

Nếu Redis là nơi lưu **session, queue, lock, quota, inventory**, bỏ lỗi write rồi trả thành công có thể sai nghiêm trọng. Khi đó cần fail-closed, retry có kiểm soát, outbox hoặc nguồn dữ liệu đáng tin cậy khác.

### 13.2. Cẩn trọng với transaction SQL đã commit

Giả sử một service lưu đơn hàng vào database rồi cập nhật cache ở callback after-commit. Nếu Redis bị OOM, SQL có thể **đã commit thành công** nhưng Redis cache update thất bại.

Không retry toàn bộ `createOrder` một cách mù quáng dựa trên exception sau commit; request trùng có thể tạo hai đơn hàng. Cần idempotency key của command nghiệp vụ và cơ chế đồng bộ cache bền vững khi phù hợp.

## 14. READONLY: ghi nhầm vào replica

Một lỗi điển hình:

```text
READONLY You can't write against a read only replica.
```

Redis replica nhận dữ liệu từ primary và mặc định không chấp nhận các command ghi từ application. Khi service gửi `SET`/`INCR`/`XADD` tới replica, Redis từ chối.

Điều này **khác với `NOPERM`**:

- `NOPERM`: ACL không cho user dùng command/key/channel.
- `READONLY`: node hiện tại không có vai trò/trạng thái phù hợp để chấp nhận ghi, dù user có quyền ghi trong ACL.

Các nguyên nhân:

1. Application trỏ thẳng đến hostname/IP của một replica.
2. Sentinel đã failover nhưng client giữ endpoint primary cũ, giờ node đó đã thành replica.
3. Redis Cluster đã đổi primary/slot owner nhưng slot map của client còn cũ.
4. App dùng Redis connection factory standalone dù thực tế kết nối tới Redis Cluster/Sentinel.
5. Load balancer trộn cả primary và replica trong pool endpoint ghi.
6. Trong một quá trình maintenance, node bị chuyển vai trò nhưng application chưa refresh connection/topology.
7. Một cấu hình read preference/connection routing không đúng cho đường ghi.

### 14.1. Kiểm tra vai trò node

Trên endpoint mà ứng dụng thực sự gửi command, dùng tài khoản có quyền:

```bash
redis-cli -h redis-node.internal -p 6379 --user ops_reader --askpass INFO replication
```

Ở Redis thông thường, thông tin có thể cho biết:

```text
role:master
```

hoặc:

```text
role:slave
```

Từ ngữ `master/slave` có thể vẫn xuất hiện trong một số output/config của Redis dù tài liệu hiện đại thường dùng **primary/replica**. Không suy ra endpoint đang là primary chỉ từ tên hostname như `redis-master`.

Lệnh `ROLE` cũng cho biết vai trò nhưng có thể yêu cầu quyền ACL thích hợp:

```text
ROLE
```

Trong Redis Cluster, cần kết hợp role với **slot ownership**; một node primary không nhất thiết sở hữu slot của key đang ghi.

### 14.2. Không sửa READONLY bằng cách cho replica nhận ghi

Redis có thiết lập replica read-only và các command liên quan cluster read mode, nhưng **cho phép ứng dụng ghi trực tiếp vào replica không phải cách khắc phục an toàn**. Ghi cục bộ vào replica có thể bị ghi đè khi đồng bộ từ primary, gây sai lệch dữ liệu hoặc làm mô hình replication không còn đúng.

Cách khắc phục là **route write đến primary đang sở hữu dữ liệu**, sửa cấu hình Sentinel/Cluster/client hoặc khôi phục failover cho đúng.

## 15. Redis Cluster READONLY command khác replica role

Trong Redis Cluster có command `READONLY` dành cho cluster client trong một số chế độ đọc từ replica. Nó cho phép connection thực hiện một số **read operations** trên cluster replica cho các slot tương ứng.

Cần phân biệt:

| Khái niệm | Tác dụng |
|---|---|
| Replica ở trạng thái chỉ đọc | Node không chấp nhận các write nghiệp vụ bình thường |
| `READONLY` command trong Cluster | Bật chế độ đọc phù hợp trên một connection tới cluster replica |
| `READWRITE` command trong Cluster | Trả connection về chế độ routing/read thông thường theo giao thức |
| `NOPERM` từ ACL | User không có quyền thực hiện command/key/channel |
| Failover/promotion | Chuyển role primary/replica theo cơ chế quản trị cluster/Sentinel |

`READWRITE` **không biến replica thành primary**; nó chỉ điều chỉnh một trạng thái giao thức ở cấp client connection. Vì vậy không sử dụng `READWRITE` như một “cách sửa” lỗi ghi vào replica.

Nếu thiết kế có read-from-replica, nhớ rằng Redis replication thường bất đồng bộ: sau khi ghi primary, một read ở replica có thể nhận giá trị cũ.

## 16. Sentinel: ứng dụng phải theo dõi primary hiện tại

Redis Sentinel giúp giám sát một Redis primary và các replica, đồng thời hỗ trợ phát hiện/promote primary mới khi failover. Ứng dụng cần một Sentinel-aware connection factory để cập nhật endpoint chính xác.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: redis-primary-group
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
      timeout: 3s
```

Tên master và endpoints chỉ minh họa. Khi có TLS/ACL, cần cấu hình cả phần xác thực Redis/Sentinel theo môi trường và phiên bản Spring Boot. Không giả định Redis password và Sentinel password luôn là cùng một secret.

Nếu chỉ hard-code một endpoint Redis primary cũ, sau failover ứng dụng có thể tiếp tục gửi write tới node đã trở thành replica và gặp `READONLY`. Hãy để driver/Sentinel-aware factory giải quyết việc tìm primary, đồng thời có chính sách reconnect/timeout.

### 16.1. Không dùng load balancer tùy tiện cho cả read và write

Nếu một load balancer gửi kết nối ứng dụng đến cả primary và replica, một vài request `SET` có thể thành công, vài request khác lại `READONLY`. Đây không phải lỗi Redis ngẫu nhiên mà là cấu hình routing.

Cần endpoint hoặc proxy có cơ chế phân biệt write-primary và read-replica chính xác; với nhiều topology, driver cluster/sentinel-aware phù hợp hơn một DNS round-robin đơn giản.

## 17. Redis Cluster: stale topology có thể dẫn đến lỗi sau failover

Trong Redis Cluster, mỗi key thuộc một trong 16.384 hash slots và được một primary sở hữu. Lettuce cluster client thường tự tính slot, định tuyến và xử lý `MOVED`/`ASK`.

Khi failover/resharding:

```text
Trước:
  slot S -> primary A

Sau:
  slot S -> primary B
  A có thể offline hoặc trở thành replica

Ứng dụng giữ slot map cũ:
  SET key thuộc slot S -> A -> READONLY/timeout/MOVED...
```

Một cluster-aware connection factory cần khám phá và làm mới topology. Nếu ứng dụng dùng standalone factory trỏ vào một node cluster, việc xử lý các thay đổi slot/role có thể thất bại.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.internal:7000
          - redis-b.internal:7001
          - redis-c.internal:7002
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
```

Khi cấu hình Lettuce cluster client nâng cao, có thể bật topology refresh định kỳ và adaptive refresh để giảm khoảng thời gian slot map lỗi thời. Không tăng `max-redirects` vô hạn nhằm che giấu sai địa chỉ node hoặc topology chưa đồng thuận.

Cần kiểm tra endpoint Redis quảng bá trong `CLUSTER SHARDS`/`CLUSTER SLOTS` có thể kết nối từ ứng dụng. Trên Kubernetes/NAT, seed endpoint có thể truy cập được nhưng target primary trong topology lại dùng IP chỉ có hiệu lực bên trong mạng Redis.

### 17.1. Một primary không sở hữu mọi slot

Node là primary chưa đủ để ghi được **mọi key** trong Cluster. Nếu lệnh gửi tới primary không sở hữu slot, Redis có thể trả `MOVED` để chỉ hướng, không phải `READONLY`.

Đừng nhầm một lỗi redirect do slot owner với việc node bị biến thành replica. Để chẩn đoán, cần biết slot của key và owner hiện tại, không chỉ role của node.

## 18. Đọc từ replica: lựa chọn độ trễ với nhất quán dữ liệu

Lettuce có thể hỗ trợ cấu hình read preference để đọc từ replica trong các topology phù hợp.

Ví dụ một lựa chọn client:

```java
import io.lettuce.core.ReadFrom;

ReadFrom readPreference = ReadFrom.REPLICA_PREFERRED;
```

Khi đọc từ replica, application có thể giảm tải primary nhưng chấp nhận **replication lag**: một lần `GET` ngay sau `SET` có thể thấy giá trị trước đó.

Read-from-replica không có nghĩa cho phép ghi vào replica. Driver vẫn phải định tuyến writes tới primary. Nếu ứng dụng vừa muốn read-your-writes vừa đọc replica, cần đánh giá mức nhất quán và cơ chế đọc lại primary, không chỉ đặt read preference.

Tránh dùng read-replica cho các quyết định nghiệp vụ phụ thuộc trạng thái mới nhất như kiểm tra quyền đã thu hồi hoặc giới hạn giao dịch nếu không có bảo đảm khác.

## 19. Khi Redis lỗi, nên retry hay fail fast?

Quyết định phụ thuộc **lý do lỗi** và **độ an toàn của thao tác**.

| Lỗi | Retry ngay với cùng cấu hình? | Hướng phản ứng |
|---|---|---|
| `NOAUTH` | Không | Sửa/gắn credentials, xác định factory |
| `WRONGPASS` | Không | Kiểm tra user, secret, rotation; không log password |
| `NOPERM` | Không | Xác định command/key/channel thiếu quyền, sửa least-privilege ACL |
| `OOM` | Thường không retry dồn dập | Giảm tải, sửa memory/retention/capacity; theo chính sách fallback |
| `READONLY` từ replica sai tuyến | Không cứ gửi lại node cũ | Định tuyến tới primary/factory đúng, chờ topology/failover ổn định |
| `MOVED`/`ASK` | Driver cluster-aware có thể xử lý redirect | Giới hạn redirect, refresh topology |
| Timeout/connection reset | Có thể retry có giới hạn | Cần xem command đã thực thi chưa và idempotency |
| `CROSSSLOT` | Không | Sửa thiết kế key/command |

### 19.1. Retry sau timeout cần xét command có side effect

```text
App -> Redis: INCR app:counter
Redis thực thi thành công
Mạng mất phản hồi
App nghĩ timeout rồi gọi lại INCR
=> Giá trị có thể tăng hai lần
```

Với `GET`, retry thường ít rủi ro side effect hơn. Với `INCR`, `XADD`, `LPUSH` hoặc script sửa dữ liệu, retry có thể tạo trùng nếu command trước đó đã chạy.

Không đánh đồng **Redis trả một lỗi từ chối rõ ràng** với **client không nhận được phản hồi và không biết lệnh đã chạy hay chưa**.

### 19.2. Giới hạn retry và dùng backoff

Một chính sách retry tốt có:

- Nhận diện lỗi thực sự tạm thời.
- Giới hạn số lần thử và tổng thời gian cho request.
- Backoff/jitter tránh các instance retry đồng loạt.
- Idempotency key/operation ID cho side effects quan trọng.
- Metric để biết retry thành công hay đang làm tải tăng.
- Circuit breaker/degraded mode khi Redis mất khả dụng kéo dài.

Không áp dụng `@Retryable` hoặc Reactor `retryWhen` cho mọi `DataAccessException` mà không có bộ lọc phù hợp. Redis OOM hoặc WRONGPASS sẽ không biến mất nhờ thêm hàng nghìn request.

## 20. Xử lý lỗi ở tầng Cache, Repository, Stream và Reactive Redis

### 20.1. Spring Cache

Với `RedisCacheManager`, các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict` có thể phát sinh Redis operations ở các thời điểm khác nhau.

Một CacheErrorHandler có thể được dùng để quyết định chính sách lỗi cache:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.cache.interceptor.SimpleCacheErrorHandler;

public final class ObservingCacheErrorHandler
        extends SimpleCacheErrorHandler {

    @Override
    public void handleCacheGetError(
            RuntimeException exception,
            Cache cache,
            Object key) {
        // Ghi metric/log theo cache name, không log payload/secret.
        super.handleCacheGetError(exception, cache, key);
    }
}
```

Ví dụ này **ghi nhận rồi để lỗi đi tiếp**, không tự động fallback. Nếu muốn bỏ lỗi cache GET để đi về database, cần xác định rõ vai trò cache và hợp đồng của Spring Cache interceptor/error handler ở version đang dùng. Không bỏ lỗi evict/put bừa bãi vì có thể để lại stale data trong thời gian dài.

Nếu dùng transaction-aware cache mutation, lỗi trong callback sau database commit có thể xuất hiện khi database đã commit. Không dùng kết quả Redis callback như căn cứ để retry toàn bộ transaction SQL.

### 20.2. Redis Repository

Redis Repository có thể dùng Redis Hash và các key metadata/index khác. Một user chỉ được `GET`/`SET` sẽ không đủ nếu Repository cần `HSET`, `DEL`, `SADD`, `SREM` hay commands liên quan expiration. Một tác vụ dọn TTL, listener keyspace notification hoặc secondary index có thể dùng đường Redis riêng.

Đọc/ghi Repository lỗi do ACL cần xác định **command và key prefix thực** mà Repository tạo. Không sửa bằng cách trực tiếp ghi Hash ngoài Repository rồi bỏ qua các index/keyspace mappings.

### 20.3. Redis Streams

Producer `XADD` có thể bị OOM; consumer `XREADGROUP` có thể bị NOPERM; ACK `XACK` có thể lỗi vì ACL hoặc Redis unavailable. Tác động hoàn toàn khác nhau:

- Producer failure: event chưa chắc đã được lưu.
- Consumer read failure: không nhận event mới.
- ACK failure: message có thể còn pending và được giao lại.
- Reclaim failure: recovery worker không thể thu hồi message idle.

Cần ghi nhận stream, group, consumer, record ID, loại lỗi và có đường retry/idempotency phù hợp. **Không ACK trước khi tác động nghiệp vụ đã hoàn tất** chỉ để tránh backlog.

### 20.4. ReactiveRedisTemplate

Publisher Redis reactive có thể hoàn tất rỗng khi key không tồn tại, hoặc phát lỗi khi Redis từ chối command.

```java
return reactiveStringRedisTemplate.opsForValue()
        .get("app:flag:checkout")
        .doOnError(error -> recordRedisFailure("GET", error))
        .onErrorResume(error -> {
            // Chỉ fallback nếu hợp đồng tính năng cho phép.
            return Mono.just("DISABLED");
        });
```

`Mono` trong ví dụ là `reactor.core.publisher.Mono`; `recordRedisFailure` là hàm quan sát do ứng dụng triển khai. Không áp dụng `DISABLED` như giá trị an toàn cho mọi tính năng; trong nhiều trường hợp fail-closed hoặc trả lỗi cho caller mới đúng.

## 21. Mối quan hệ giữa OOM và transaction/atomicity

Một Redis transaction `MULTI`/`EXEC` hay script Lua **không đồng nghĩa** mọi lỗi command sẽ làm rollback toàn bộ các thao tác Redis đã chạy.

Những lưu ý:

- Redis `MULTI`/`EXEC` có ngữ nghĩa riêng khi lỗi xảy ra ở giai đoạn enqueue so với giai đoạn thực thi.
- Một số command trong `EXEC` có thể thất bại khi thực thi mà các command khác vẫn thành công; Redis không cung cấp rollback như database quan hệ cho mọi runtime error.
- Lua script chạy nguyên tử đối với sự xen kẽ command của client khác, nhưng nếu script có lỗi runtime sau một số lệnh ghi, những thay đổi đã xảy ra không được tự hoàn tác.
- OOM có thể khiến một thao tác tăng bộ nhớ bị từ chối, nhưng không phải cứ có một lỗi OOM là mọi thao tác trước đó trong cùng luồng Java được rollback.
- `@Transactional` quản lý transaction manager của tài nguyên được chọn; database JPA và Redis không tự có chung commit nguyên tử.

Ví dụ:

```text
Database UPDATE thành công
Database COMMIT
Cache PUT vào Redis
Redis trả OOM

=> Database vẫn có thể đã commit.
=> Cache chưa phản ánh bản mới.
=> Cần retry/invalidation/outbox có kiểm soát.
```

Với dữ liệu cache, TTL hoặc outbox giúp hội tụ về nguồn. Với Redis là nơi giữ dữ liệu gốc, cần có cơ chế giảm tải/khôi phục và ý thức rõ durability, không dựa vào rollback tưởng tượng.

## 22. Chẩn đoán hệ thống: từ error đến nguyên nhân gốc

Một quy trình chung nên theo thứ tự:

1. **Ghi nhận operation và Redis error code**: `NOAUTH`, `WRONGPASS`, `NOPERM`, `OOM` hay `READONLY`.
2. **Xác định đường gọi**: `RedisTemplate`, `RedisCacheManager`, Repository, Stream, reactive publisher.
3. **Xác định endpoint thực**: host, port, Redis DB/topology, role/slot, không log password.
4. **Kiểm tra kết nối có xác thực được không** bằng cùng user/endpoint từ môi trường được phép.
5. **Nếu NOPERM**, xác định command/key/channel và ACL user hiện hành.
6. **Nếu OOM**, xem `INFO memory`, `maxmemory-policy`, `evicted_keys` và các key/stream lớn.
7. **Nếu READONLY**, xác nhận role node, Sentinel/Cluster topology và hướng write-primary.
8. **Phân biệt lỗi có thể retry với lỗi cấu hình**, đặt hạn mức retry.
9. **Thử lại đường nghiệp vụ thật** trên môi trường an toàn, không chỉ thử một lệnh CLI khác.
10. **Đảm bảo khả năng phục hồi dữ liệu** nếu một write Redis đã thất bại sau commit ở hệ thống khác.

### Ma trận quyết định nhanh

| Triệu chứng | Bằng chứng nên lấy | Hành động ưu tiên |
|---|---|---|
| NOAUTH trên mọi command | App credentials có được truyền? Redis yêu cầu auth? | Sửa authentication wiring |
| WRONGPASS sau deploy | Secret version, username, ACL user `on/off` | Sửa/rotate secret có kiểm soát |
| NOPERM chỉ với evict | `DEL` hoặc cache writer command thiếu quyền | Cấp đúng ACL cho cache namespace |
| NOPERM chỉ với Streams ACK | `XACK`, group key pattern | Sửa ACL consumer và recovery policy |
| OOM khi cache fill | Memory, maxmemory policy, TTL và keyspace | Giảm cache pressure/retention, chọn policy phù hợp |
| OOM khi XADD | Stream length, retention, memory | Khống chế producer/trim theo nhu cầu replay |
| READONLY sau failover | `INFO replication`, Sentinel/Cluster owner | Refresh connection/routing đến primary |
| GET đúng nhưng SET READONLY | Node replica, read preference, LB | Tách read/write routing đúng |
| Một số cluster key lỗi | Slot owner, advertised endpoint | Kiểm tra topology/DNS/TLS theo node |
| GET trả empty nhưng không exception | Key/prefix/serializer/TTL | Đừng quy thành NOAUTH/NOERROR khi chưa điều tra |

## 23. Runbook xử lý sự cố trong môi trường production

### 23.1. Việc nên làm ngay

- Xác định mức độ ảnh hưởng: toàn bộ ứng dụng, chỉ cache fills hay một dòng xử lý nghiệp vụ quan trọng.
- Ghi lại error code, thời điểm, endpoint, operation, request/correlation ID và số instance bị ảnh hưởng.
- So sánh lần thay đổi gần nhất của secret, ACL, maxmemory, topology hoặc deployment.
- Nếu Redis chỉ là cache, đánh giá degraded mode/fallback và bảo vệ database khỏi thác cache misses.
- Nếu Redis là nguồn dữ liệu quan trọng, giảm tốc độ producer/write traffic để tránh mất thêm dữ liệu và kích hoạt kế hoạch khôi phục.
- Với READONLY, xác minh primary hiện tại trước khi chỉnh client routing.
- Với OOM, xem memory pressure và retention thay vì xóa toàn bộ dữ liệu.
- Với WRONGPASS/NOPERM, xác định đúng user/command/key; không nới quyền sang admin không cần thiết.

### 23.2. Việc không nên làm

- Không in credentials/Redis URL có password vào log hoặc ticket.
- Không vô hiệu hóa authentication/TLS hoặc cấp `+@all ~*` cho application để xử lý nhanh.
- Không đổi replica thành writable chỉ để `SET` không còn READONLY.
- Không tăng `maxmemory` vượt khả năng RAM thực tế mà không đánh giá overhead/failover.
- Không bật `allkeys-lru` khi Redis giữ dữ liệu nghiệp vụ không thể tái tạo.
- Không gọi `FLUSHALL` để chữa OOM khi chưa có quy trình được duyệt.
- Không retry vô hạn các write có side effect sau timeout.
- Không giả định “SQL rollback” khi callback Redis lỗi sau database commit.
- Không chạy lệnh quản trị `CONFIG SET`/`ACL SETUSER` trực tiếp trên production nếu chưa có ownership, change plan và quyền phù hợp.

### 23.3. Xác nhận đã khôi phục

Không chỉ xác nhận Redis `PING` trả `PONG`. Cần thử **chính command và key namespace từng lỗi** qua account thực tế:

```text
Authentication:
  app user mở connection mới và thực thi lệnh hợp lệ.

ACL:
  command GET/SET/DEL/XACK... đúng tính năng chạy được;
  command ngoài quyền vẫn bị chặn.

Memory:
  memory không còn tăng không giới hạn;
  write được chấp nhận;
  không phá policy retention/khả năng phục hồi.

Read-only:
  write đến primary đúng;
  topology ổn định;
  failover không khiến một số instance giữ endpoint cũ.
```

Theo dõi metric sau khôi phục để phát hiện lỗi tái diễn, đặc biệt khi một đợt secret rotation hoặc failover chưa lan tới mọi instance.

## 24. Bài thực hành ACL trên Redis cô lập

Thực hành trên **Redis riêng cho lab**, không sửa user/ACL của Redis đang phục vụ production. Các command ACL quản trị dưới đây yêu cầu tài khoản có quyền; có thể không dùng được trên managed Redis.

### 24.1. Tạo user lab có quyền hạn chế

Trong phiên `redis-cli` interactive bằng tài khoản quản trị của Redis lab:

```text
ACL SETUSER app_demo on >LAB_CHANGE_ME_NOW ~app:demo:* +ping +get +set +del
ACL GETUSER app_demo
ACL DRYRUN app_demo GET app:demo:key
ACL DRYRUN app_demo SET other:key value
```

Password `LAB_CHANGE_ME_NOW` chỉ là mẫu cho lab. Với production, tạo password ngẫu nhiên mạnh, lưu an toàn và có quy trình rotate.

### 24.2. Thử command được phép và bị chặn

Mở một kết nối CLI khác với user `app_demo`, nhập password bằng prompt:

```bash
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass PING
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass SET app:demo:key value
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass GET app:demo:key
redis-cli -h 127.0.0.1 -p 6379 --user app_demo --askpass SET forbidden:key value
```

Lệnh cuối phải bị từ chối theo key rule nếu ACL user đang được áp dụng đúng. Thử thêm `HSET app:demo:hash a b` để thấy user chỉ được cấp `GET`/`SET`/`DEL` không tự có quyền `HSET`.

Sau lab, xóa user và dữ liệu thử nghiệm bằng tài khoản quản trị theo quy trình môi trường cô lập; **không tái sử dụng password lab**.

### 24.3. Phân biệt NOAUTH, WRONGPASS, NOPERM

- **NOAUTH**: kết nối khi chưa AUTH mà gửi command yêu cầu xác thực.
- **WRONGPASS**: gửi username/password không đúng hoặc user đang bị `off`.
- **NOPERM**: AUTH thành công, nhưng command/key/channel không nằm trong ACL được phép.

Không nên thử bừa mật khẩu trên Redis production để tạo nhiều WRONGPASS entries. Thực hành này chỉ dành cho server lab do bạn kiểm soát.

## 25. Bài thực hành OOM và policy bộ nhớ

Để quan sát OOM, dùng **Redis instance/container cô lập**, dữ liệu bỏ được, không dùng chung Redis với ứng dụng khác.

Một hướng thiết lập Redis lab (cú pháp command-line minh họa, cần điều chỉnh cho hệ điều hành/deployment):

```bash
redis-server --port 6381 --maxmemory 4mb --maxmemory-policy noeviction
```

Bật authentication và cô lập network theo chính sách lab; ví dụ không phải hướng dẫn mở Redis công khai không có mật khẩu.

Từ CLI kết nối tới instance lab:

```bash
redis-cli -p 6381 INFO memory
redis-cli -p 6381 INFO stats
redis-cli -p 6381 CONFIG GET maxmemory
redis-cli -p 6381 CONFIG GET maxmemory-policy
```

Sau đó cho một chương trình thử nghiệm ghi nhiều payload có kiểm soát, dừng khi gặp `OOM`. Kiểm tra:

1. `used_memory` tăng như thế nào?
2. `evicted_keys` có tăng không khi policy là `noeviction`?
3. `GET` của key cũ có còn hoạt động không?
4. Lệnh `SET` mới bị từ chối ra sao?
5. `DEL` một số key lab có giúp giải phóng dung lượng không?
6. Khi đổi sang policy dành cho cache trong một **instance lab khác**, key nào bị eviction và TTL có được bảo toàn không?

Một instance Redis nhỏ với số liệu nền khác nhau có thể chạm giới hạn ngay khi khởi động hoặc ở những thời điểm khác nhau; không dùng số liệu tuyệt đối làm mục tiêu. Điều quan trọng là hiểu **cơ chế phản hồi và chính sách memory**, không phải cố tạo hàng triệu key.

## 26. Bài thực hành READONLY an toàn

Dùng Redis primary/replica trong môi trường lab riêng:

1. Xác nhận role mỗi node bằng `INFO replication` hoặc `ROLE`.
2. Đăng nhập account hợp lệ với đủ quyền `GET`/`SET`.
3. `SET` trên primary thử nghiệm và đọc kết quả.
4. Thử `SET` trên replica lab, quan sát `READONLY`.
5. Thử `GET` trên replica; nhận xét sự khác nhau giữa read và write.
6. Nếu có Sentinel/Cluster lab, chủ động failover ở môi trường thử nghiệm và quan sát connection factory refresh topology.
7. Xác nhận write của ứng dụng sau failover đi tới primary mới, không sửa replica thành writable.

Không dùng lệnh `REPLICAOF`, `CLUSTER FAILOVER` hoặc thay đổi role trên production chỉ để tái hiện lỗi. Chúng có thể tác động trực tiếp tới tính sẵn sàng và replication của dữ liệu thật.

## 27. Các phép thử nên có cho ứng dụng Spring Data Redis

| Test | Bố trí | Điều cần xác nhận |
|---|---|---|
| Thiếu credentials | Redis lab bật auth, app không gửi password | Phản hồi lỗi auth, không biến thành cache miss |
| Sai password | Dùng secret không hợp lệ trong test | WRONGPASS được phân loại; không retry vô hạn |
| ACL thiếu GET | User có quyền SET nhưng không GET | Đường đọc lỗi rõ ràng |
| ACL thiếu DEL | Cache đọc/ghi được nhưng evict bị từ chối | Không để cache stale bị bỏ qua im lặng |
| ACL thiếu XACK | Stream consumer nhận message nhưng không ACK được | Message pending và recovery/alert hoạt động |
| OOM noeviction | Redis lab maxmemory thấp | Phân loại write failure, fallback đúng theo vai trò cache |
| Volatile policy | Có key TTL và không TTL | Hiểu candidate eviction và giới hạn |
| Ghi tới replica | Factory test trỏ sai role | READONLY được phát hiện, sửa routing |
| Failover | Sentinel/Cluster lab đổi primary | Ứng dụng cập nhật route, khôi phục trong giới hạn chấp nhận |
| Timeout sau side effect | Mất phản hồi của INCR/XADD | Retry không tạo nghiệp vụ trùng nếu hợp đồng yêu cầu |
| DB commit + Redis cache error | Cho callback cache thất bại | Không giả định DB rollback, có đường repair |
| Reactive Redis | Publisher phát lỗi từ server | onError không bị biến nhầm thành empty |

Chỉ test trên Redis thử nghiệm có thể tái tạo, không dùng Redis production làm nơi gây lỗi cố ý. Kết quả nên được kiểm tra ở tầng API nghiệp vụ thực tế, không chỉ xác nhận một Redis command riêng.

## 28. Câu hỏi tự đánh giá

**1. NOAUTH khác WRONGPASS thế nào?**  
NOAUTH cho biết command chưa được xác thực hợp lệ; WRONGPASS cho biết credentials/user bị Redis từ chối khi xác thực.

**2. Một app user có thể PING thành công nhưng SET bị NOPERM không?**  
Có. ACL command và key patterns có thể cho PING nhưng không cho SET hoặc namespace đang truy cập.

**3. Nếu @Cacheable hit bình thường nhưng @CacheEvict lỗi, cần xem gì?**  
Kiểm tra quyền `DEL`/cache writer commands, key prefix, thời điểm after-commit và cache error handling.

**4. Mọi write Redis đều bị OOM, đổi ngay sang allkeys-lru có an toàn không?**  
Không nếu instance có dữ liệu nghiệp vụ không thể tái tạo. Cần xem dữ liệu, policy, TTL, memory capacity và tác động eviction.

**5. TTL là gì so với eviction?**  
TTL quyết định thời hạn key; eviction có thể loại key trước hạn do memory pressure khi policy cho phép.

**6. Tại sao volatile-lru vẫn có thể báo OOM?**  
Vì chỉ key có TTL là ứng viên. Khi hết key có thể evict hoặc phần lớn bộ nhớ nằm ở key không TTL, policy vẫn không giải phóng đủ dung lượng.

**7. READONLY có luôn nghĩa user ACL thiếu quyền ghi không?**  
Không. Nó thường phản ánh command ghi đến replica/read-only node. ACL denial là `NOPERM`.

**8. Gọi READWRITE trên Redis Cluster replica có nâng replica lên primary không?**  
Không. Đó là command điều chỉnh client read mode, không phải thao tác promote role.

**9. Nếu Redis trả OOM sau khi database SQL đã commit, database có rollback tự động không?**  
Không. Redis và SQL không có commit nguyên tử chỉ nhờ `@Transactional`; cần cơ chế repair/idempotency.

**10. Khi Redis timeout sau INCR, retry có chắc an toàn không?**  
Không. Lệnh INCR có thể đã thực thi; retry có thể tăng lần nữa.

**11. Redis Streams consumer đọc được nhưng XACK bị NOPERM, hậu quả gì?**  
Message có thể còn pending và được giao lại; cần sửa ACL và giữ idempotency.

**12. PING thành công có chứng minh hệ thống đã phục hồi không?**  
Không. Phải thử command/key/channel từng lỗi bằng account thực tế và xác nhận workflow nghiệp vụ.

## 29. Ghi nhớ khi vận hành

- **NOAUTH/WRONGPASS:** kiểm tra authentication wiring, username, secret rotation và connection factory; không vô hiệu hóa security để khắc phục.
- **NOPERM:** user đã auth nhưng thiếu quyền command/key/channel; cấp đúng ACL theo namespace và operations thật, không cấp admin bừa bãi.
- **OOM:** xem `maxmemory`, policy, TTL, keyspace, eviction, stream retention và headroom; phân biệt cache có thể mất với dữ liệu không thể tái tạo.
- **READONLY:** xác minh node role và routing primary trong Sentinel/Cluster; không biến replica thành writable để né lỗi.
- **Redis driver và Spring exceptions:** ghi nhận root cause/error code, không dựa hoàn toàn vào một exception class hay bắt tất cả để trả cache miss.
- **Không retry mọi lỗi:** lỗi cấu hình cần sửa cấu hình; timeout chưa biết trạng thái write cần idempotency và giới hạn retry.
- **Spring Cache, Repository, Streams, Reactive Redis** có các đường command khác nhau; ACL và fallback phải được thiết kế theo use case.
- **Lỗi Redis sau commit SQL không đảo ngược commit SQL**; với đồng bộ dữ liệu quan trọng nên có retry/outbox/reconciliation phù hợp.
- **Production runbook cần bảo vệ dữ liệu:** không FLUSHALL, tắt TLS, cấp `+@all` hoặc thay đổi role/policy bừa bãi.
- **Xác nhận khôi phục bằng workflow thật**, không chỉ bằng `PING`.

Một nguyên tắc thực dụng là: **đọc đúng mã lỗi Redis, xác định tầng gây lỗi, rồi chọn biện pháp phù hợp với vai trò dữ liệu**. Khôi phục quyền truy cập Redis không đủ nếu workflow đã mất event, cache còn stale hoặc một write bị retry gây tác động lặp.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Support](https://docs.spring.io/spring-data/redis/reference/redis.html): tổng quan connection factory, template và hỗ trợ Redis trong Spring.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations, exception translation và serializers.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache manager, TTL, cache writer và transaction-aware.
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): Redis Cluster connection/routing.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): producer, consumer group, ACK và pending.
- [Redis — Authentication](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): ACL users, command/key/channel permissions và cách quản lý ACL.
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/): cú pháp cấp quyền Redis ACL.
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/): mô phỏng kiểm tra quyền command/key cho một user.
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/): thông tin về các lần bị từ chối do ACL/authentication.
- [Redis — Key Eviction](https://redis.io/docs/latest/develop/reference/eviction/): maxmemory, eviction policies và tác động tới keyspace.
- [Redis — INFO](https://redis.io/docs/latest/commands/info/): thông số memory, replication và stats.
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/): quan sát bộ nhớ của một key.
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/): primary/replica, replication lag và vai trò read-only.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): phát hiện primary, failover và client routing.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, redirects, failover và replica reads.
- [Redis — READONLY](https://redis.io/docs/latest/commands/readonly/): chế độ đọc trên cluster replica.
- [Lettuce — Redis Cluster](https://redis.github.io/lettuce/ha-sharding/): topology/routing/failover với Lettuce.
