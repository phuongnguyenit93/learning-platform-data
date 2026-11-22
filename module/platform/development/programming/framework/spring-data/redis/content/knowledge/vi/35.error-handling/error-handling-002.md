# Hệ phân cấp DataAccessException khi truy cập Redis

> **Module:** Spring Data Redis  
> **Chương:** Xử lý lỗi  
> **Chủ đề:** Phân loại ngoại lệ truy cập Redis theo hệ `DataAccessException` của Spring, hiểu cơ chế chuyển đổi lỗi từ Lettuce/Jedis, xác định nguyên nhân gốc và xây dựng cách retry, fallback, xử lý HTTP, quan sát hệ thống và bảo vệ tính đúng đắn của thao tác ghi.

## 1. Vì sao cần hiểu DataAccessException khi sử dụng Redis?

Xem một thao tác tưởng chừng đơn giản:

~~~java
String value = stringRedisTemplate.opsForValue()
        .get("product:101:name");
~~~

Phía sau dòng code này là nhiều tầng:

~~~mermaid
flowchart TD
    APP["Service / Controller"] --> TEMPLATE["Spring RedisTemplate"]
    TEMPLATE --> CONNECTION["Spring Data Redis connection"]
    CONNECTION --> DRIVER["Lettuce / Jedis"]
    DRIVER --> NETWORK["TCP, TLS, DNS, Network"]
    NETWORK --> REDIS["Redis server / Redis Cluster"]
    REDIS --> RESULT{"Kết quả"}
    RESULT --> VALUE["Dữ liệu hoặc key không tồn tại"]
    RESULT --> ERROR["Server error, timeout, disconnect"]
    ERROR --> RAW["Driver exception"]
    RAW --> TRANSLATE["Spring exception translation"]
    TRANSLATE --> DAO["DataAccessException / subtype"]
    DAO --> HANDLE["Retry / fallback / fail / reconcile"]
~~~

Những lỗi có thể gặp:

- Redis server không hoạt động hoặc không thể kết nối.
- Redis command quá thời hạn xử lý.
- Key đang là `list` nhưng code dùng `GET` cho String.
- Redis Cluster nhận lệnh nhiều key khác slot và báo `CROSSSLOT`.
- Sai Redis ACL, user/password hoặc command không được cấp quyền.
- Hết RAM hoặc `maxmemory` policy khiến ghi thất bại.
- Serializer không đọc được dữ liệu cũ.
- Code truyền tham số Java không hợp lệ.
- Redis đã thực hiện lệnh ghi nhưng response bị mất.

Các trường hợp này **không có cùng giải pháp**. Retry có thể hữu ích khi mạng vừa phục hồi, nhưng sẽ không chữa được key sai type hay một multi-key command khác slot. Với lệnh `INCR`, retry sau timeout thậm chí có thể khiến dữ liệu bị thay đổi hai lần.

Vì vậy, nên xem exception hierarchy là **đầu vào để ra quyết định**, không phải cơ chế tự động sửa mọi lỗi Redis.

### 1.1. DataAccessException giúp giải quyết điều gì?

`org.springframework.dao.DataAccessException` là abstraction exception của Spring dành cho các lỗi truy cập dữ liệu. Nó không chỉ dành cho SQL. Những Spring Data modules và các infrastructure components có thể chuyển lỗi driver/store thành các lớp thuộc hệ này.

Lợi ích:

1. **Không phụ thuộc trực tiếp driver** trong mỗi service: code có thể bắt kiểu Spring thay vì viết đầy đủ Lettuce/Jedis exception.
2. **Có khái niệm phân loại** như transient, non-transient, recoverable.
3. **Giữ nguyên nhân gốc** bằng cause chain để chẩn đoán.
4. **Hỗ trợ policy chung** ở tầng adapter, service hoặc API.
5. **Phân biệt cache miss hợp lệ với lỗi truy cập dữ liệu.**

Hạn chế: không phải mọi lỗi Redis đều được chuyển thành cùng subtype ở mọi phiên bản. Một lỗi phát sinh ngoài Redis connection abstraction có thể còn là driver exception, serializer exception hoặc Java runtime exception.

## 2. DataAccessException nằm ở đâu trong Java exception hierarchy?

`DataAccessException` là **unchecked exception**: nó kế thừa `RuntimeException` qua `NestedRuntimeException` của Spring. Không bắt buộc thêm `throws DataAccessException` vào mọi method.

~~~text
java.lang.RuntimeException
  └─ org.springframework.core.NestedRuntimeException
      └─ org.springframework.dao.DataAccessException
          ├─ NonTransientDataAccessException
          ├─ TransientDataAccessException
          └─ RecoverableDataAccessException
~~~

Đây là sơ đồ ba nhánh chính, chưa liệt kê mọi lớp con trong Spring Framework.

### 2.1. NonTransientDataAccessException

Diễn giải chung: lỗi không được kỳ vọng biến mất chỉ bằng việc thực thi lại y nguyên operation ngay lập tức.

Một số subtype trong Spring DAO:

- `InvalidDataAccessApiUsageException`.
- `InvalidDataAccessResourceUsageException`.
- `NonTransientDataAccessResourceException`.
- `DataAccessResourceFailureException`.
- `PermissionDeniedDataAccessException`.
- `UncategorizedDataAccessException`.

**Lưu ý quan trọng:** tên nhánh `NonTransient` là cách framework phân loại exception, không phải định luật vật lý nói lỗi tuyệt đối không thể phục hồi. Một lỗi kết nối Redis có thể do sự cố mạng ngắn hạn, dù loại exception của Spring thuộc nhánh lỗi resource không transient.

### 2.2. TransientDataAccessException

Diễn giải chung: lỗi có thể khắc phục bằng một lần thử lại trong điều kiện thích hợp, nhưng vẫn phải xét tính lũy đẳng của thao tác.

Ví dụ:

- `QueryTimeoutException`.
- `TransientDataAccessResourceException`.
- `ConcurrencyFailureException` và một số subtype liên quan.

**Một exception transient không có nghĩa có thể retry một write không lũy đẳng.** Redis có thể đã thực thi `INCR` trước khi client nhận lỗi timeout.

### 2.3. RecoverableDataAccessException

Spring DAO có nhánh `RecoverableDataAccessException` cho những tình huống muốn tiếp tục cần một bước khôi phục nhất định.

Không nên cho rằng mọi lỗi Redis mất kết nối được chuyển vào nhánh này. Trong Spring Data Redis thực tế, các lỗi phổ biến thường được biểu diễn qua `RedisConnectionFailureException`, `QueryTimeoutException` hoặc `RedisSystemException`.

### 2.4. Sơ đồ các subtype có liên quan đến Redis

~~~text
DataAccessException
├─ NonTransientDataAccessException
│  ├─ NonTransientDataAccessResourceException
│  │  └─ DataAccessResourceFailureException
│  │      └─ RedisConnectionFailureException       [Spring Data Redis]
│  ├─ InvalidDataAccessApiUsageException
│  ├─ InvalidDataAccessResourceUsageException
│  ├─ PermissionDeniedDataAccessException
│  └─ UncategorizedDataAccessException
│      └─ RedisSystemException                    [Spring Data Redis]
├─ TransientDataAccessException
│  ├─ QueryTimeoutException
│  ├─ TransientDataAccessResourceException
│  └─ ConcurrencyFailureException
└─ RecoverableDataAccessException
~~~

Cây này **rút gọn**, chỉ tập trung vào các lớp đáng biết khi xử lý Redis. Các nhánh khác của `DataAccessException` vẫn tồn tại.

## 3. Các ngoại lệ Redis thường gặp nhất

### 3.1. RedisConnectionFailureException

Tên đầy đủ:

~~~java
org.springframework.data.redis.RedisConnectionFailureException
~~~

Biểu thị lỗi liên quan tới việc không thể kết nối hoặc duy trì kết nối Redis theo cơ chế chuyển đổi của Spring Data Redis. Thường gặp khi:

- Server Redis không hoạt động.
- Sai hostname/port.
- Network bị ngắt, packet loss hoặc partition.
- TCP connect timeout.
- Redis Cluster failover hoặc kết nối tới node không sẵn sàng.
- DNS, firewall, TLS hoặc các tầng liên quan có vấn đề.

Ví dụ message có thể là:

~~~text
RedisConnectionFailureException: Unable to connect to Redis
~~~

Nội dung message không phải contract ổn định. Cần xem **cause** và kết nối thực tế để phân biệt lỗi mạng với cấu hình.

Trong các phiên bản phổ biến, ngoại lệ này kế thừa `DataAccessResourceFailureException` thuộc nhánh non-transient resource errors.

### 3.2. RedisSystemException

Tên đầy đủ:

~~~java
org.springframework.data.redis.RedisSystemException
~~~

Đây là ngoại lệ Redis-specific cho lỗi không được phân loại cụ thể hơn. Nó thường thuộc nhánh `UncategorizedDataAccessException`.

Một exception dạng này có thể bọc:

- Redis command execution error.
- Redis server trả `WRONGTYPE`.
- Lỗi Redis Cluster command hoặc error reply.
- Lỗi driver Redis chưa được converter ánh xạ sang subtype chính xác.
- Những lỗi thuộc Redis command execution path.

**Không được suy ra Redis server bị hỏng chỉ vì có chữ “System”.** Có thể lỗi bắt nguồn từ key schema hoặc command của ứng dụng.

### 3.3. QueryTimeoutException

Tên đầy đủ:

~~~java
org.springframework.dao.QueryTimeoutException
~~~

Là subtype của `TransientDataAccessException`, có thể xuất hiện khi driver báo Redis command timeout.

Nguyên nhân có thể là:

- Redis server quá tải.
- Lệnh quá nặng hoặc script chạy lâu.
- Network RTT cao.
- Driver command queue tích tụ.
- Timeout của client được đặt quá ngắn.
- GC pause hoặc thread scheduling delay.
- Cluster topology/failover làm tăng độ trễ.

Điểm cốt lõi: **timeout chỉ xác nhận client không nhận được kết quả đúng thời hạn; nó không chứng minh Redis chưa xử lý command.**

### 3.4. InvalidDataAccessApiUsageException

~~~java
org.springframework.dao.InvalidDataAccessApiUsageException
~~~

Thể hiện một kiểu sử dụng API hoặc thao tác data access không hợp lệ theo translator/framework.

Không phải tất cả Redis server errors đều được map sang lớp này. Ví dụ `WRONGTYPE` có thể được bọc thành `RedisSystemException` tùy driver/version.

Khi gặp lỗi usage, sửa code, tham số, data type, key schema hoặc thao tác không được hỗ trợ; retry liên tục cùng một command thường không giúp ích.

### 3.5. DataAccessResourceFailureException

~~~java
org.springframework.dao.DataAccessResourceFailureException
~~~

Là nhánh lỗi resource của Spring DAO; `RedisConnectionFailureException` nằm trong nhánh này. Nếu code bắt nó rất rộng, có thể đồng thời bắt lỗi resource từ những datastore khác trong ứng dụng.

Nếu policy chỉ áp cho Redis, ưu tiên bắt Redis-specific exception ở **Redis adapter** hoặc xác định dependency rõ ràng.

### 3.6. UncategorizedDataAccessException

~~~java
org.springframework.dao.UncategorizedDataAccessException
~~~

Đây là nhánh cho data access error không được translator nhận diện thành một loại chuyên biệt hơn. `RedisSystemException` thường thuộc nhánh này.

Với nhóm này, cần phân tích root cause thay vì kết luận retry được hay không chỉ từ tên exception.

### 3.7. PermissionDeniedDataAccessException

~~~java
org.springframework.dao.PermissionDeniedDataAccessException
~~~

Spring DAO có loại lỗi quyền. Tuy nhiên Redis trả `NOAUTH`/`NOPERM` không nhất thiết được mọi Redis exception converter biến thành đúng lớp này. Có thể nhận `RedisSystemException` hoặc lỗi command execution được bọc.

Không nên thiết kế một catch `PermissionDeniedDataAccessException` rồi tin rằng nó bao phủ mọi lỗi Redis ACL.

## 4. Bảng nhận diện và cách xử lý theo subtype

| Ngoại lệ Spring | Bối cảnh thường thấy | Hướng xử lý |
|---|---|---|
| `RedisConnectionFailureException` | Mất kết nối, không tới Redis | Check health/network, retry GET có giới hạn hoặc fallback |
| `QueryTimeoutException` | Command chờ quá hạn | Xem command đã thực thi chưa; retry đọc an toàn |
| `RedisSystemException` | Lỗi Redis chưa phân loại | Xem cause: WRONGTYPE, CROSSSLOT, ACL, OOM… |
| `InvalidDataAccessApiUsageException` | Sai API/command/arguments | Sửa code/input/cấu hình |
| `PermissionDeniedDataAccessException` nếu được dịch | Thiếu quyền | Sửa ACL và credentials, không retry mù |
| `DataAccessResourceFailureException` | Resource access problem | Xác định đúng datastore/operation |
| `DataAccessException` chung | Lỗi đã được translate | Catch ở boundary chung, không coi tất cả như nhau |
| Exception ngoài `DataAccessException` | Invalid argument, serializer, raw driver | Phân loại theo nguyên nhân thật |

Một subtype là **tín hiệu** chứ không phải bản mô tả đầy đủ. Cần kết hợp với Redis command, key type, kết quả có thể đã commit và tính chất nghiệp vụ.

## 5. Cơ chế chuyển đổi exception từ Lettuce và Jedis

### 5.1. Driver và Spring là hai tầng riêng

Spring Data Redis thường truy cập Redis qua một driver:

- **Lettuce:** Redis client dựa trên Netty, hỗ trợ APIs synchronous/async/reactive tùy cách dùng.
- **Jedis:** Redis client với các kiểu connection/API riêng.

Lettuce có các kiểu ngoại lệ điển hình:

~~~java
io.lettuce.core.RedisConnectionException
io.lettuce.core.RedisCommandTimeoutException
io.lettuce.core.RedisCommandExecutionException
io.lettuce.core.RedisException
~~~

Jedis cũng có các exception kết nối và lỗi command trong package `redis.clients.jedis.exceptions` tùy phiên bản.

Spring Data Redis có connection abstraction và cơ chế exception translation để chuyển các lỗi phù hợp thành `DataAccessException`.

### 5.2. Bảng mapping minh họa

| Nguồn lỗi | Driver exception có thể gặp | Spring exception thường phù hợp |
|---|---|---|
| Connect thất bại | Lettuce `RedisConnectionException` | `RedisConnectionFailureException` |
| Redis command timeout | Lettuce `RedisCommandTimeoutException` | `QueryTimeoutException` |
| Server command error | Lettuce `RedisCommandExecutionException` | `RedisSystemException` hoặc lớp khác |
| Redis error chưa phân loại | Lettuce `RedisException` | `RedisSystemException` |
| Code truyền key null | `IllegalArgumentException` | Có thể không dịch sang `DataAccessException` |
| JSON parse lỗi sau khi GET | Jackson exception | Không mặc định là Redis connection exception |

Đây là bảng **định hướng tư duy**, không phải bản cam kết chính xác cho mọi phiên bản Spring Data Redis/Lettuce/Jedis. Khi xây policy gắn với exception type, cần quan sát type thực tế của stack sử dụng.

### 5.3. Những nơi có thể không được translate giống nhau

- `RedisTemplate` và `StringRedisTemplate`.
- `ReactiveRedisTemplate`.
- Redis Repository.
- `RedisCacheManager` thông qua Spring Cache.
- `RedisConnection` và APIs mức thấp.
- Lời gọi **raw Lettuce/Jedis** trực tiếp từ application.
- Lỗi serialize/deserialize trước/sau khi Redis command chạy.

Ví dụ nếu code gọi trực tiếp `StatefulRedisConnection.sync().get(...)` của Lettuce, exception có thể vẫn thuộc `io.lettuce.core`. Spring không tự dịch mọi method bất kỳ của một driver được inject từ bên ngoài.

## 6. Phân biệt cache miss và Redis failure

Một tình huống thường gây nhầm:

~~~java
String value = stringRedisTemplate.opsForValue().get(key);
~~~

Có hai kết quả khác nhau:

1. Redis có kết nối và key không tồn tại: `value == null` là kết quả hợp lệ.
2. Redis không thể truy cập: method có thể ném `RedisConnectionFailureException` hoặc exception liên quan.

Không nên viết catch mọi exception rồi trả null:

~~~java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null;
}
~~~

Nó xóa dấu hiệu hệ thống đang lỗi, đồng thời làm caller nhầm “Redis unavailable” với “dữ liệu không tồn tại”.

Nếu Redis chỉ là **cache**, cả hai trường hợp có thể dẫn tới đọc database, nhưng cần log/metrics **khác nhau**. Nếu Redis là nguồn chuẩn, tự coi lỗi là key miss có thể gây sai nghiệp vụ.

### 6.1. Một adapter mô tả ba trạng thái

~~~java
public sealed interface CacheLookup
        permits CacheLookup.Hit,
                CacheLookup.Miss,
                CacheLookup.Unavailable {

    record Hit(String value) implements CacheLookup {}

    record Miss() implements CacheLookup {}

    record Unavailable(String reason) implements CacheLookup {}
}
~~~

Đoạn trên dùng sealed types của Java 17, là abstraction do ứng dụng định nghĩa.

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisCacheLookup {

    private final StringRedisTemplate redis;

    public RedisCacheLookup(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public CacheLookup get(String key) {
        try {
            String value = redis.opsForValue().get(key);

            return value == null
                    ? new CacheLookup.Miss()
                    : new CacheLookup.Hit(value);

        } catch (RedisConnectionFailureException ex) {
            return new CacheLookup.Unavailable("CONNECTION");
        } catch (QueryTimeoutException ex) {
            return new CacheLookup.Unavailable("TIMEOUT");
        }
    }
}
~~~

Những lỗi khác như `RedisSystemException` sẽ tiếp tục propagate vì code chưa định nghĩa policy tương ứng. Đó thường là lựa chọn tốt hơn nuốt mọi lỗi thành cache miss.

## 7. Vì sao RedisSystemException cần xem root cause?

Giả sử Redis có một List:

~~~redis
LPUSH queue:tasks task-1 task-2
~~~

Application lại đọc bằng String API:

~~~java
String value = redis.opsForValue().get("queue:tasks");
~~~

Redis server có thể trả:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

Tùy converter, exception ở tầng Spring có thể là `RedisSystemException`. Tuy nhiên bản chất không phải Redis server đang chết, mà là **ứng dụng gọi nhầm operation cho key type**.

Dùng lệnh trong môi trường test:

~~~bash
redis-cli TYPE queue:tasks
redis-cli LRANGE queue:tasks 0 -1
~~~

Nếu key thuộc `list`, sửa code đọc List thay vì retry GET.

### 7.1. Lấy nguyên nhân sâu nhất

`DataAccessException` kế thừa helper từ `NestedRuntimeException`:

~~~java
import org.springframework.dao.DataAccessException;

public void logRedisFailure(
        String operation, DataAccessException ex) {

    Throwable root = ex.getMostSpecificCause();

    log.warn(
            "Redis operation={}, springType={}, rootType={}",
            operation,
            ex.getClass().getSimpleName(),
            root.getClass().getSimpleName(),
            ex);
}
~~~

Trong code, `log` là logger do ứng dụng khai báo. Trên production, có thể lấy cause chain và phân loại lỗi vào metrics; không log stack trace lặp lại hàng chục nghìn lần/giây khi Redis outage.

### 7.2. Không dựa hoàn toàn vào exception message

Mẫu mong manh:

~~~java
if (ex.getMessage().contains("WRONGTYPE")) {
    // Phân loại lỗi.
}
~~~

Lý do không nên làm ở khắp service:

- Message có thể đổi theo version driver.
- Lỗi gốc nằm ở cause chứ không phải message ngoài.
- Message có thể null.
- Message có thể chứa chi tiết nội bộ hoặc value nhạy cảm.

Nếu Redis error reply chỉ có thể nhận diện qua text, nên tập trung logic mapping tại một Redis adapter được test với phiên bản Redis/driver thực tế.

## 8. Một số lỗi Redis server và cách chẩn đoán

### 8.1. WRONGTYPE

Triệu chứng:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

Kiểm tra:

- Data type của key (`TYPE`).
- Có trùng namespace giữa Redis String/Hash/List không?
- Có đổi serializer/data model nhưng vẫn dùng key cũ không?
- Một service khác có ghi đè key bằng loại dữ liệu khác không?

Không chữa bằng tăng timeout hoặc retry vô hạn.

### 8.2. CROSSSLOT

Trong Redis Cluster:

~~~redis
MGET 'order:{o-101}:status' 'order:{o-202}:status'
~~~

Nếu hai key thuộc hai hash slots, native multi-key command sẽ bị:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

Hướng xử lý:

- Tính slot bằng `CLUSTER KEYSLOT`.
- Nếu cần một command atomic, thiết kế keys có cùng hash tag.
- Nếu các keys độc lập, đọc bằng các GET riêng/cluster-aware scatter tùy API.
- Đừng nhầm driver routing `MOVED`/`ASK` với `CROSSSLOT`.
- Không retry y nguyên một command vi phạm slot constraints.

Không nên mặc định mọi `multiGet` Java đều ném CROSSSLOT vì một số client có thể tách command thành nhiều sub-requests; nhưng **native MGET xuyên slots không trở thành atomic**.

### 8.3. NOAUTH và NOPERM

Redis có thể trả:

~~~text
NOAUTH Authentication required
NOPERM this user has no permissions to run the command
~~~

Kiểm tra:

- Username/password hoặc ACL token đã cấu hình đúng chưa.
- Redis ACL có cho phép command, key pattern và channel pattern không.
- Secrets có bị rotate không.
- Service có kết nối nhầm môi trường không.

Lỗi có thể được dịch thành RedisSystemException hoặc subtype khác tùy converter. Không mặc định mọi Redis ACL error đều trở thành `PermissionDeniedDataAccessException`.

### 8.4. OOM và maxmemory

Redis có thể từ chối write khi hết bộ nhớ:

~~~text
OOM command not allowed when used memory > 'maxmemory'
~~~

Hãy kiểm tra:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
~~~

Một số managed Redis chặn `CONFIG GET`; dùng control plane và metrics do provider cung cấp. Retry write liên tục khi Redis vẫn hết RAM có thể tạo retry storm và làm sự cố nghiêm trọng hơn.

### 8.5. Connection refused / DNS / TLS

Nếu root cause báo `Connection refused` hoặc lỗi TLS handshake, việc đầu tiên là kiểm tra connectivity, không phải key serializer.

Những điểm cần kiểm tra:

- Endpoint và port.
- Container/Kubernetes Service/pod readiness.
- Firewall/network policy, DNS.
- TLS on/off và chứng chỉ phù hợp.
- Redis Cluster nodes trả topology endpoints reachable từ client.
- Redis clients/connection limits.

### 8.6. TRYAGAIN, MOVED và ASK

Trong Redis Cluster:

- `MOVED`: command gửi tới node không sở hữu slot, cluster-aware client thường cập nhật routing.
- `ASK`: redirection tạm thời trong resharding.
- `TRYAGAIN`: điều kiện cluster tạm thời có thể cần retry.
- `CROSSSLOT`: command sử dụng nhiều keys khác slots, cần sửa data model/command.

Không gộp tất cả lỗi này vào một vòng lặp retry không có giới hạn.

## 9. Timeout là lỗi đặc biệt nguy hiểm với lệnh ghi

### 9.1. Một lệnh GET timeout

~~~text
Client          Redis
  |-- GET key -->|
  |             | xử lý chậm
  | x timeout   |
  |             | có thể trả reply muộn
~~~

GET là lệnh đọc. Có thể retry ngắn hoặc fallback database khi đó là cache, tùy mức độ tải và SLA.

### 9.2. Lệnh INCR có thể đã thực thi

~~~text
Client                Redis
  |---- INCR count ---->|
  |                     | count: 10 -> 11
  |    reply bị mất     |
  | x QueryTimeout      |
  |---- retry INCR ---->|
  |                     | count: 11 -> 12
~~~

Ứng dụng muốn tăng một lần nhưng thực tế tăng hai. Cũng cần thận trọng với:

- `DECR` và `INCRBY`.
- `LPUSH`/`RPUSH`.
- `XADD *`.
- `PUBLISH`.
- Lua script cập nhật trạng thái.
- `SET` khi có concurrent writers.
- External side effects được kích hoạt sau khi nhận kết quả Redis.

### 9.3. Bảng retry theo operation

| Operation | Retry sau timeout | Ghi chú |
|---|---|---|
| `GET`/`HGET`/`EXISTS` | Thường an toàn hơn | Read-only, giới hạn attempts/backoff |
| `SET key sameValue` | Có điều kiện | Có thể ghi đè writer mới nếu thứ tự thay đổi |
| `SET NX` | Cần đọc/đối soát | Claim đầu có thể đã thành công |
| `INCR`/`DECR` | Không retry mù | Cần idempotency ID/script |
| `LPUSH` | Không retry mù | Có thể tạo phần tử trùng |
| `XADD *` | Không retry mù | Auto-generated ID có thể tạo entry mới |
| `PUBLISH` | Không retry mù nếu duplicate gây hại | Subscriber có thể nhận trùng hoặc offline |
| `DEL`/`UNLINK` | Thường chấp nhận với cache | Cần xét concurrent recreate |
| `MGET` | Tùy client/cluster | Một số high-level API scatter/gather |
| Lua write script | Phụ thuộc idempotency | Script có thể đã chạy trước timeout |

**Nguyên tắc:** lớp exception không cung cấp bảo đảm về việc side effect đã xảy ra hay chưa.

### 9.4. TTL và điều kiện ghi ảnh hưởng tính lũy đẳng

`SET key fixedValue` có thể giống lũy đẳng ở trạng thái cuối nếu không có cạnh tranh. Nhưng retry muộn có thể ghi đè giá trị mới:

~~~text
T1: Request A gửi SET key=old -> timeout
T2: Request B SET key=new -> thành công
T3: A retry SET key=old -> ghi lùi dữ liệu
~~~

Cần conditional write, version check, CAS/Lua hoặc hệ thống nguồn chuẩn phù hợp khi dữ liệu quan trọng.

## 10. Phân loại transient không phải retry policy

Một lỗi thuộc `TransientDataAccessException` nói rằng lỗi có thể mang tính tạm thời, nhưng vẫn phải hỏi:

1. Lệnh là read hay write?
2. Lệnh đã có thể được thực thi trước khi client thấy exception không?
3. Retry có thay đổi kết quả nghiệp vụ không?
4. Redis đang quá tải, retry có làm trầm trọng hơn không?
5. Có operation ID hoặc idempotency key không?
6. Có nguồn bền vững để đối soát không?

Tương tự, một `RedisConnectionFailureException` có thể thuộc nhánh non-transient resource failure nhưng mạng có thể phục hồi nhanh. Không nên dùng cách lọc “chỉ retry `TransientDataAccessException`” mà bỏ qua mọi đặc điểm command và hệ thống.

### 10.1. Retry có giới hạn

Một helper minh họa cho `GET`:

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RetryingRedisReader {

    private final StringRedisTemplate redis;

    public RetryingRedisReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String getWithOneRetry(String key) {
        try {
            return redis.opsForValue().get(key);
        } catch (RedisConnectionFailureException |
                 QueryTimeoutException ex) {

            // Chỉ retry một GET read-only.
            // Production cần backoff, metrics và circuit breaker.
            return redis.opsForValue().get(key);
        }
    }
}
~~~

Mẫu này chỉ retry một lần ngay lập tức để minh họa. Với production, cần:

- Exponential backoff và jitter.
- Tổng timeout budget cho cả request.
- Retry attempts có giới hạn.
- Bulkhead và circuit breaker.
- Metrics số lần thử lại.
- Không retry các lỗi WRONGTYPE/CROSSSLOT/ACL/schema.

### 10.2. Tại sao retry storm nguy hiểm?

Giả sử mỗi request HTTP có 3 attempts ở gateway, 3 ở service và 3 ở Redis adapter. Tùy cách đếm attempts, một logical request có thể dẫn tới rất nhiều lệnh Redis thực tế. Khi Redis quá tải, những retry này khiến latency và CPU tăng tiếp.

Mỗi tầng cần biết retry đã được xử lý ở đâu, tránh nhân chồng retries không có kiểm soát.

## 11. Fail-open cho cache, fail-closed cho dữ liệu quan trọng

### 11.1. Redis chỉ làm cache

Nếu Redis lưu bản sao từ database, khi lỗi connectivity/timeout có thể fallback:

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;

public String getProductJson(String id) {
    String key = "cache:product:v1:" + id;

    try {
        String cached = redis.opsForValue().get(key);
        if (cached != null) {
            return cached;
        }
    } catch (RedisConnectionFailureException |
             QueryTimeoutException ex) {

        // Fallback với điều kiện nguồn chuẩn chịu được tải.
        return productSource.loadProductJson(id);
    }

    return productSource.loadProductJson(id);
}
~~~

`redis` là StringRedisTemplate; `productSource` là dependency application.

Với code này:

- Cache miss dẫn đến đọc source.
- Cache lỗi kết nối/timeout cũng dẫn đến đọc source.
- RedisSystemException/serializer errors không bị tự động che.
- Cần metrics riêng cho cache miss và cache error.
- Nếu Redis outage trên toàn hệ thống, có thể tạo database stampede; cần giới hạn concurrency.

### 11.2. Redis làm nguồn chuẩn

Ví dụ Redis lưu hạn mức quan trọng. Một catch kiểu:

~~~java
catch (RedisConnectionFailureException ex) {
    return "UNLIMITED";
}
~~~

là **nguy hiểm** nếu làm hệ thống tự cho phép thao tác khi không xác minh được quota. Cần fail-closed hoặc nguồn dự phòng có semantics đáng tin cậy.

Chọn fail-open/fail-closed theo:

- Có nguồn chuẩn khác không?
- Dữ liệu cũ được phép dùng không?
- Tác động khi trả default là gì?
- Redis outage làm tải fallback tăng bao nhiêu?
- Có thể quan sát và cảnh báo sự cố không?

### 11.3. Không gộp Redis error với lỗi database

Không tốt:

~~~java
try {
    String cached = redis.opsForValue().get(key);
    return cached == null ? database.load(id) : cached;
} catch (DataAccessException ex) {
    return "fallback";
}
~~~

Nếu `database.load(id)` cũng ném `DataAccessException`, catch này có thể nhầm **database outage** thành Redis cache failure.

Đặt try/catch quanh Redis call hoặc tách Redis adapter khỏi lớp nguồn chuẩn.

## 12. Spring Cache abstraction và CacheErrorHandler

Với:

~~~java
@Cacheable(cacheNames = "productDetails", key = "#id")
public ProductView findProduct(String id) {
    return repository.findById(id).orElseThrow();
}
~~~

Nếu dùng RedisCacheManager, Redis GET/PUT có thể ném exception. **Không mặc định `@Cacheable` tự fail-open** trên mọi lỗi Redis.

Spring Cache có `CacheErrorHandler` để tùy chọn policy cho:

- Cache get.
- Cache put.
- Cache evict.
- Cache clear.

### 12.1. Ví dụ chính sách fail-open riêng cho cache GET/PUT

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;

public class ProductCacheErrorHandler implements CacheErrorHandler {

    private boolean canIgnore(RuntimeException ex) {
        return ex instanceof RedisConnectionFailureException
                || ex instanceof QueryTimeoutException;
    }

    @Override
    public void handleCacheGetError(
            RuntimeException ex, Cache cache, Object key) {
        if (canIgnore(ex)) {
            // Ghi metrics rồi cho method nguồn chạy tiếp.
            return;
        }
        throw ex;
    }

    @Override
    public void handleCachePutError(
            RuntimeException ex, Cache cache,
            Object key, Object value) {
        if (canIgnore(ex)) {
            // Put cache là best effort trong use case này.
            return;
        }
        throw ex;
    }

    @Override
    public void handleCacheEvictError(
            RuntimeException ex, Cache cache, Object key) {
        // Không bỏ qua khi stale data có thể vi phạm SLA.
        throw ex;
    }

    @Override
    public void handleCacheClearError(
            RuntimeException ex, Cache cache) {
        throw ex;
    }
}
~~~

Ví dụ dùng Spring Cache API. Trong ứng dụng cần thực hiện metrics/logging thật thay vì comment.

### 12.2. Vì sao eviction failure khác cache GET failure?

Nếu database đổi giá sản phẩm nhưng Redis cache key cũ không được evict:

~~~text
Database: price 100 -> 90
Redis: cached price = 100
Evict Redis: connection error
Next GET: trả 100 cho tới khi TTL hết
~~~

Nếu hệ thống đòi freshness chặt, nuốt lỗi eviction có thể khiến người dùng thấy dữ liệu sai. Cần:

- TTL safety net.
- Invalidation retry/outbox.
- Versioned key hoặc kiểm tra dữ liệu nguồn.
- Đường xác nhận nghiệp vụ đọc nguồn chuẩn.

`CacheErrorHandler` không tự khiến transaction database và Redis trở thành một transaction nguyên tử.

### 12.3. Cấu hình CacheErrorHandler

Một cách qua `CachingConfigurer`:

~~~java
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheErrorConfiguration implements CachingConfigurer {

    @Override
    public CacheErrorHandler errorHandler() {
        return new ProductCacheErrorHandler();
    }
}
~~~

Cách wiring cụ thể phụ thuộc Spring Framework và hệ thống configuration của ứng dụng. Handler ở Spring Cache layer **không tự áp dụng** cho lời gọi RedisTemplate trực tiếp ở các service khác.

## 13. ReactiveRedisTemplate: exception đi qua Mono/Flux

Reactive Redis API thường trả `Mono<T>` hoặc `Flux<T>`. Lỗi I/O có thể xuất hiện khi publisher được **subscribe** dưới dạng Reactor error signal.

~~~java
Mono<String> result = reactiveRedisTemplate
        .opsForValue()
        .get("cache:product:101");
~~~

Một try/catch chỉ bao quanh việc **tạo** Mono có thể không bắt được lỗi Redis xảy ra về sau.

### 13.1. Fallback khi Redis GET lỗi

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import reactor.core.publisher.Mono;

public Mono<String> getProduct(String id) {
    String key = "cache:product:v1:" + id;

    return reactiveRedisTemplate.opsForValue()
            .get(key)
            .onErrorResume(
                    RedisConnectionFailureException.class,
                    ex -> productSource.loadProductJson(id))
            .onErrorResume(
                    QueryTimeoutException.class,
                    ex -> productSource.loadProductJson(id))
            .switchIfEmpty(Mono.defer(
                    () -> productSource.loadProductJson(id)));
}
~~~

Đoạn code dùng `ReactiveStringRedisTemplate` và nguồn reactive do application định nghĩa.

- `onErrorResume`: xử lý lỗi kết nối/timeout đã chỉ định.
- `switchIfEmpty`: xử lý cache miss.
- Các exception khác sẽ propagate, không bị nuốt.
- Nếu fallback source lỗi, lỗi mới cần được xử lý ở tầng phù hợp.

### 13.2. RetryWhen với GET

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;

Mono<String> value = reactiveRedisTemplate
        .opsForValue()
        .get(key)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                     .maxBackoff(Duration.ofSeconds(1))
                     .filter(ex ->
                             ex instanceof RedisConnectionFailureException
                             || ex instanceof QueryTimeoutException));
~~~

Đây là policy minh họa cho **GET read-only**. Nếu bọc cả business pipeline có write side effect vào retryWhen, bạn có thể chạy lại nhiều bước không lũy đẳng.

### 13.3. doOnError không phải recovery

~~~java
return reactiveRedisTemplate.opsForValue()
        .get(key)
        .doOnError(ex -> log.warn("Redis read failed", ex));
~~~

`doOnError` chỉ thực hiện side effect như logging, **không đổi error thành success**. Muốn fallback, dùng `onErrorResume` với policy rõ.

### 13.4. Không gọi block trong event-loop

~~~java
String value = reactiveRedisTemplate.opsForValue()
        .get(key)
        .block();
~~~

Trong WebFlux/Netty event-loop, `block()` phá mô hình non-blocking và có thể gây chặn luồng hoặc lỗi. Nên truyền Mono/Flux tới caller thay vì ép kết quả đồng bộ trong request handler.

### 13.5. Lỗi đồng bộ trước subscription

Key null, input sai hoặc setup không hợp lệ có thể khiến method ném exception ngay lúc gọi, trước khi có Mono. Vì vậy tách:

- Validation tại ranh giới method/controller.
- Error signals của Redis I/O trong reactive pipeline.
- Serialization/mapping errors cần policy riêng.

## 14. @RestControllerAdvice: trả lỗi HTTP an toàn

Khi Redis là dependency bắt buộc của một endpoint, có thể dùng `@RestControllerAdvice` để trả response theo HTTP contract thay vì leak stack trace.

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DataAccessApiExceptionHandler {

    @ExceptionHandler({
            RedisConnectionFailureException.class,
            QueryTimeoutException.class
    })
    public ResponseEntity<ProblemDetail> redisUnavailable(
            RuntimeException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Data dependency unavailable");
        problem.setDetail(
                "The request cannot be completed at this time.");

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }

    @ExceptionHandler(RedisSystemException.class)
    public ResponseEntity<ProblemDetail> redisError(
            RedisSystemException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Data access error");
        problem.setDetail("Unexpected data operation failure.");

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

Đoạn code minh họa Spring Framework 6+ và `ProblemDetail`. Với ứng dụng sử dụng version framework cũ hơn, thay kiểu response thích hợp.

**Không trả `ex.getMessage()` ra client** một cách vô điều kiện vì có thể lộ host, Redis key, topology hoặc chi tiết khác.

### 14.1. Không ánh xạ mọi DataAccessException thành HTTP 503

Một lỗi Redis `WRONGTYPE` có thể do sai code; `CROSSSLOT` do mô hình key; `NOAUTH` do cấu hình quyền. Trả 503 và khuyên client retry ngay có thể làm tăng tải mà không giải quyết lỗi.

HTTP status phải phản ánh endpoint:

- `503` khi dependency không sẵn sàng tạm thời.
- `500` cho lỗi server/config/schema chưa được xử lý.
- `400` cho request input không hợp lệ.
- `409` cho conflict nghiệp vụ đã xác định, không chỉ vì Redis trả lỗi command.
- `202` hoặc response async riêng khi operation đang xử lý, nếu API hỗ trợ.

Không dùng exception hierarchy để thay thế validation và domain error model.

## 15. Repository, Template và serializer failures

Spring Data Redis Repository có thể thực hiện nhiều bước để lưu một entity:

- Chuyển Java entity thành Redis Hash.
- Gắn TTL theo `@RedisHash` hoặc `@TimeToLive`.
- Cập nhật secondary indexes.
- Tạo keyspace metadata.
- Gửi nhiều Redis commands.

Một lần `repository.save(entity)` bị exception không tự nói được **mọi command trước đó đã rollback**. Redis có semantics khác RDBMS.

### 15.1. Partial side effects có thể xảy ra

Ví dụ ý tưởng:

~~~text
HSET product:101 ...                -> OK
SADD product:category:desk 101     -> TIMEOUT
repository.save(product)            -> exception
~~~

Không thể kết luận bước `HSET` chưa xảy ra. Khi index, cache và resource quan trọng phải đồng bộ, cần idempotency, reconciliation và cơ chế transaction phù hợp.

### 15.2. Lỗi serializer là một nhóm riêng

Các tình huống:

- Writer dùng StringRedisSerializer, reader dùng JDK serialization.
- Đổi Java package/class trong JDK-serialized value.
- JSON schema version mới không còn tương thích code cũ.
- Hash value được encode theo serializer khác mong đợi.

Lỗi có thể là `SerializationFailedException` hoặc exception khác tùy đường chạy; không nhất thiết được dịch sang `RedisConnectionFailureException`.

Nếu GET trả bytes thành công nhưng deserialize hỏng, retry GET sẽ vẫn đọc cùng bytes lỗi. Phải sửa format/version/migration hoặc chọn đúng reader.

## 16. Redis transactions và pipelines: exception không đồng nghĩa rollback

### 16.1. Pipeline

Pipelining gửi nhiều commands mà không chờ kết quả riêng của từng lệnh để giảm overhead. Một command có thể thành công, command sau thất bại.

~~~text
Pipeline:
  SET a 1      -> thành công
  INCR b       -> lỗi WRONGTYPE
  GET c        -> có thể trả kết quả
~~~

Một exception được ném khi xử lý pipeline replies không có nghĩa Redis hoàn tác `SET a 1`. Khi thiết kế retry cho cả pipeline, phải xét tác dụng phụ của mỗi command.

### 16.2. MULTI/EXEC

Redis `MULTI`/`EXEC` đảm bảo các lệnh trong transaction được thực hiện liên tiếp theo semantics Redis, nhưng **không rollback** tất cả lệnh đã chạy thành công khi một lệnh khác lỗi runtime.

Ví dụ:

~~~redis
MULTI
SET counter:status active
INCR counter:status
EXEC
~~~

`SET` có thể thành công còn `INCR` lỗi vì `active` không phải số nguyên. Đừng xem Redis transaction giống SQL transaction.

### 16.3. WATCH

`WATCH` giúp optimistic locking. Nếu watched keys bị thay đổi, `EXEC` có thể abort và API biểu diễn kết quả abort theo cách riêng. Không mặc định mọi WATCH abort sẽ thành `OptimisticLockingFailureException` hoặc một subtype Spring cụ thể; phải kiểm tra API result.

### 16.4. Redis Cluster

Các multi-key commands, transaction và Lua có giới hạn hash slots. `CROSSSLOT` là vấn đề key placement; retry y nguyên không giải quyết.

### 16.5. Lua/Redis Function

Server-side script có thể bảo đảm các bước trong script thực thi atomically trên một shard hợp lệ. Nhưng client timeout sau script **có thể là một kết quả mơ hồ**: script đã chạy hoặc chưa. Dùng business operation ID/conditional updates nếu retry cần an toàn.

## 17. Redis command có thể thành công dù client thấy exception

Đây là nguyên tắc cần áp dụng cho mọi thao tác có side effect:

~~~mermaid
sequenceDiagram
    participant C as Spring service
    participant R as Redis
    C->>R: INCR counter
    R->>R: Giá trị 10 thành 11
    R--xC: Reply mất / timeout
    Note over C: QueryTimeoutException
    C->>R: Retry INCR counter
    R->>R: Giá trị 11 thành 12
    R-->>C: 12
~~~

Khi business requirement chỉ cho phép tăng một lần, phải thiết kế idempotency **ở nơi thực hiện side effect**.

Ví dụ Redis Lua có thể dùng một operation key:

~~~lua
-- KEYS[1]: counter key
-- KEYS[2]: idempotency record key
-- ARGV[1]: operation ID
-- ARGV[2]: TTL seconds

local exists = redis.call('GET', KEYS[2])
if exists then
    return tonumber(exists)
end

local result = redis.call('INCR', KEYS[1])
redis.call('SET', KEYS[2], result, 'EX', tonumber(ARGV[2]))
return result
~~~

Khi dùng Redis Cluster, `KEYS[1]` và `KEYS[2]` phải cùng hash slot. Với script này, chỉ một operation ID được lưu có TTL, nên sau TTL idempotency protection hết. Cần thiết kế TTL và durability phù hợp nghiệp vụ.

Script là **ví dụ mô hình**, không tự giải quyết database/payment side effects bên ngoài Redis hay Redis failover durability.

## 18. Observability: log, metrics và cause chain

### 18.1. Nên log những gì?

Một Redis failure có thể được mô tả bởi:

- Operation: GET, SET, INCR, EVAL, XREADGROUP…
- Key namespace/cache name, không nhất thiết toàn bộ key.
- Spring exception type.
- Root cause type.
- Redis error code nếu có.
- Latency và timeout threshold.
- Retry count.
- Redis node/Cluster context khi cần.
- Circuit breaker/fallback decision.
- Request trace ID hoặc business operation ID.

Không log Redis passwords, raw access tokens, session values, PII hoặc toàn bộ payload của người dùng. Cần redaction/sampling khi traffic cao.

### 18.2. Metrics có ích

| Metric đề xuất | Mục đích |
|---|---|
| `redis_operations_total` | Throughput theo operation/outcome |
| `redis_errors_total` | Error count theo type |
| `redis_command_latency` | P50/P95/P99 latency |
| `redis_retry_attempts_total` | Retry rate |
| `redis_fallback_total` | Cache fallback count |
| `redis_connection_failures_total` | Kết nối lỗi |
| `redis_command_timeouts_total` | Timeout |
| `redis_serialization_failures_total` | Codec/schema mismatch |
| `redis_circuit_breaker_state` | Trạng thái bảo vệ |
| `redis_reconciliation_total` | Operation outcome mơ hồ |
| `redis_evicted_keys` | Eviction từ Redis monitoring |

Tên metrics là ví dụ **do ứng dụng tự định nghĩa**, không khẳng định Micrometer/Spring Boot tự tạo toàn bộ.

Không dùng full key, exception message hoặc event ID làm metric labels vì cardinality tăng rất mạnh.

### 18.3. Redis CLI diagnostics

~~~bash
redis-cli PING
redis-cli INFO server
redis-cli INFO clients
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli SLOWLOG GET 10
~~~

`SLOWLOG` theo dõi commands chậm trên Redis theo ngưỡng cấu hình, không đo mọi network wait phía client. `INFO` trên một Redis Cluster node không có nghĩa phản ánh toàn bộ cluster. Managed Redis có thể giới hạn quyền đối với một số commands.

## 19. Một runbook phân loại lỗi

Khi ứng dụng log exception, hãy xử lý theo trình tự:

### Bước 1. Xác nhận lỗi xuất hiện ở đâu

Lời gọi đến từ:

- RedisTemplate/StringRedisTemplate?
- ReactiveRedisTemplate?
- RedisCacheManager/@Cacheable?
- Redis Repository?
- Raw Lettuce/Jedis?
- Serializer/Jackson?
- Business code sau khi Redis trả kết quả?

### Bước 2. Lấy Spring type và cause type

Ví dụ:

~~~text
Spring: RedisSystemException
Cause: RedisCommandExecutionException
Server reply: WRONGTYPE
~~~

Hoặc:

~~~text
Spring: QueryTimeoutException
Cause: RedisCommandTimeoutException
Command: INCR
~~~

Với cùng Spring exception, cách xử lý có thể khác vì command khác nhau.

### Bước 3. Xác định side effect

- GET: read-only.
- SET: có thể ghi đè.
- INCR: tăng giá trị, non-idempotent.
- XADD: append event, có thể trùng.
- PUBLISH: phát thông điệp, có thể trùng/lost.
- Pipeline: một phần commands có thể thành công.
- MULTI/EXEC: không rollback kiểu SQL.

### Bước 4. Xem có nguyên nhân cố định không

- WRONGTYPE: sửa data type/schema.
- CROSSSLOT: sửa hash tag/multi-key command.
- NOPERM: sửa ACL.
- OOM: điều chỉnh capacity/eviction.
- Serializer mismatch: sửa codec/migration.

### Bước 5. Nếu là lỗi tạm thời, quyết định retry có an toàn không

- Giới hạn attempts/backoff/jitter.
- Timeout tổng.
- Circuit breaker/bulkhead.
- Idempotency cho writes.
- Reconciliation khi không biết trạng thái.

### Bước 6. Xác nhận kết quả cuối ở nguồn chuẩn

Nếu ghi đơn hàng, thanh toán, số dư hoặc tồn kho, Redis exception không đủ để kết luận nghiệp vụ chưa commit. Tra cứu business operation ID và trạng thái bền vững.

## 20. Kiểm thử exception handling

### 20.1. Unit tests

Giả lập từng loại lỗi tại Redis adapter:

- `RedisConnectionFailureException`.
- `QueryTimeoutException`.
- `RedisSystemException` với root cause tương ứng nếu policy cần.
- Serializer exception.
- Key miss trả null.

Kiểm tra caller:

- Có fallback đúng không?
- Có phân biệt miss và unavailable không?
- Có retry write sai không?
- Có propagate lỗi chưa được hỗ trợ không?
- Có gọi source database quá nhiều không?

### 20.2. Integration tests

Dùng Redis test instance/containers hoặc môi trường staging để thử:

1. Kết nối tới endpoint không hoạt động.
2. Redis restart giữa request.
3. WRONGTYPE trên key có type khác mong đợi.
4. Serializer mismatch khi đọc dữ liệu cũ.
5. Cluster CROSSSLOT nếu production dùng Redis Cluster.
6. ACL NOAUTH/NOPERM ở môi trường test riêng.
7. Redis memory pressure theo cách có kiểm soát.
8. Reactive pipeline timeout/fallback.
9. CacheErrorHandler behavior.

Loại exception cuối phụ thuộc driver/version, nên test nên xác nhận **business policy và data correctness**, không chỉ exact message string.

### 20.3. StepVerifier cho reactive code

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> result = reactiveCacheGateway.get("product:101");

StepVerifier.create(result)
        .expectNext("fallback-data")
        .verifyComplete();
~~~

`reactiveCacheGateway` ở đây là lớp ứng dụng đã cài đặt fallback; test fixture tự định nghĩa dữ liệu và source. Với trường hợp muốn propagate lỗi, có thể dùng `expectErrorMatches(...)` theo subtype mong muốn.

### 20.4. Test tình huống write đã chạy nhưng reply mất

Một test bắt buộc cho nghiệp vụ nhạy cảm nên mô phỏng:

~~~text
Redis nhận và chạy INCR
Client timeout trước khi nhận reply
Retry được kích hoạt
Kết quả nghiệp vụ vẫn chỉ tăng một lần (nếu đây là contract)
~~~

Mock luôn ném exception trước khi command gửi không chứng minh được tình huống này. Cần test idempotent operation protocol ở nơi có side effect.

## 21. Những sai lầm phổ biến

### 21.1. Bắt DataAccessException rồi trả null cho mọi lỗi

Sai vì nhầm connection failure với key miss và nuốt lỗi mapping/schema.

### 21.2. Retry mọi TransientDataAccessException

Sai với những lệnh đã có thể tạo side effect trước timeout. Luôn xét command và idempotency.

### 21.3. Coi RedisConnectionFailureException là Redis server chắc chắn đã chết

Chưa chắc: có thể là DNS, network, TLS, cluster topology, kết nối client. Phải xem cause và metrics.

### 21.4. Coi RedisSystemException luôn là lỗi infrastructure tạm thời

Sai: có thể bọc WRONGTYPE, CROSSSLOT, NOAUTH/NOPERM hoặc command usage lỗi.

### 21.5. Coi WRONGTYPE là vấn đề serializer thuần túy

Sai: WRONGTYPE là Redis data type mismatch; serializer mismatch có thể gây lỗi decode khác. Có thể cả hai cùng xuất hiện khi namespace bị đổi.

### 21.6. Coi QueryTimeoutException chứng minh write thất bại

Sai: Redis có thể đã thực thi trước khi reply mất.

### 21.7. Ánh xạ mọi DataAccessException thành HTTP 503

Sai: có lỗi code, ACL/schema và business conflict cần xử lý khác.

### 21.8. Cho rằng @Cacheable tự fail-open

Không mặc định. CacheErrorHandler có thể được cấu hình, nhưng cần policy riêng cho get/put/evict.

### 21.9. Cho rằng try/catch quanh tạo Mono bắt được Redis I/O error

Không đúng cho lỗi xuất hiện lúc subscription. Dùng Reactor error operators.

### 21.10. Cho rằng pipeline hoặc transaction rollback hết khi có exception

Sai: Redis có semantics riêng, nhiều commands có thể đã chạy.

### 21.11. Bỏ cause khi wrap exception

Nếu chuyển thành custom exception mà không giữ cause, việc điều tra driver/server error khó hơn.

### 21.12. Retry storm khi Redis đang quá tải

Retry không giới hạn làm tăng latency và CPU. Dùng backoff, jitter, circuit breaker và giới hạn concurrency.

## 22. Câu hỏi thường gặp

**Câu 1. DataAccessException có phải checked exception không?**

Không. Nó thuộc `RuntimeException` hierarchy qua `NestedRuntimeException`.

**Câu 2. DataAccessException chỉ dùng cho cơ sở dữ liệu quan hệ?**

Không. Spring Data Redis cũng dùng exception hierarchy này cho nhiều lỗi truy cập Redis.

**Câu 3. RedisConnectionFailureException có phải là subtype của TransientDataAccessException không?**

Trong hierarchy Spring Data Redis phổ biến, nó kế thừa `DataAccessResourceFailureException` thuộc nhánh non-transient resource errors. Nhưng nguyên nhân mất kết nối vẫn có thể phục hồi; retry policy không nên chỉ dựa vào nhãn nhánh.

**Câu 4. RedisSystemException có nghĩa Redis process lỗi nghiêm trọng?**

Không nhất thiết. Nó thường là Redis-specific error chưa phân loại, có thể bọc một lỗi command của ứng dụng.

**Câu 5. QueryTimeoutException có nên tự động retry?**

Với GET có thể retry ngắn; với INCR/LPUSH/XADD cần idempotency/reconciliation trước.

**Câu 6. GET key không tồn tại trả exception không?**

Thông thường Redis GET key không tồn tại trả nil, Spring imperative template có thể trả null; reactive API thường trả empty publisher.

**Câu 7. WRONGTYPE nên bắt lớp nào?**

Không có bảo đảm một lớp Spring cụ thể cho mọi driver/version. Quan sát actual exception và root Redis error reply, rồi sửa type/schema.

**Câu 8. CROSSSLOT có thể sửa bằng tăng Redis timeout không?**

Không. Phải sửa multi-key operation/hash slots hoặc dùng lệnh độc lập khi không cần atomicity.

**Câu 9. Nên bắt raw Lettuce exception hay DataAccessException?**

Qua Spring Data Redis abstractions, ưu tiên Spring exceptions khi translator đã chuyển. Nếu dùng raw driver, cần xử lý driver exceptions tại adapter.

**Câu 10. Nếu Redis chỉ là cache, có thể nuốt tất cả lỗi không?**

Không nên. Có thể fail-open với connectivity/timeout có kiểm soát; lỗi serialization, eviction hoặc schema cần metrics/recovery riêng để không phục vụ dữ liệu sai lâu dài.

**Câu 11. ReactiveRedisTemplate ném exception lúc nào?**

Nhiều Redis I/O errors được phát khi publisher subscribe, dưới dạng Reactor error signal. Lỗi input có thể ném đồng bộ sớm hơn.

**Câu 12. CacheErrorHandler có áp dụng cho RedisTemplate trực tiếp không?**

Không. Nó dành cho Spring Cache abstraction và các cache operations tương ứng.

**Câu 13. MULTI/EXEC có rollback lệnh trước khi một lệnh trong EXEC lỗi không?**

Redis không rollback các lệnh đã thực thi thành công như SQL. Phải hiểu transaction semantics và error results.

**Câu 14. Có thể dùng Spring Retry cho Redis không?**

Có thể, nhưng phải thiết kế filter exception, backoff, timeout và giới hạn theo semantics lệnh. Không áp một policy cho mọi write.

**Câu 15. Vì sao cần nguyên nhân gốc nếu đã có subtype Spring?**

Vì translator có thể gộp nhiều Redis server errors vào một `RedisSystemException`. Cause giúp phân biệt lỗi schema, permission, OOM và cluster.

**Câu 16. Spring Boot có tự retry mọi Redis command không?**

Không nên giả định. Driver có thể tự reconnect/route nhưng application-level retry và idempotency là trách nhiệm riêng.

## 23. Checklist triển khai xử lý lỗi Redis

1. **Xác định API:** RedisTemplate, RedisCacheManager, Repository, ReactiveRedisTemplate hay raw driver.
2. **Phân biệt key miss với Redis unavailable.**
3. **Nhận diện subtype:** RedisConnectionFailureException, QueryTimeoutException, RedisSystemException và các DAO exceptions liên quan.
4. **Giữ cause chain** khi wrap exception.
5. **Phân tích Redis command** trước khi quyết định retry.
6. **Không retry mù writes có side effect** như INCR/LPUSH/XADD.
7. **Kiểm tra key type/serializer** khi gặp WRONGTYPE hoặc decoding failure.
8. **Kiểm tra hash slots** khi gặp CROSSSLOT trên cluster.
9. **Kiểm tra ACL/credentials** khi server trả NOAUTH/NOPERM.
10. **Đo memory/capacity** khi gặp OOM hoặc maxclients.
11. **Dùng retry có giới hạn**, backoff, jitter, circuit breaker và timeout tổng.
12. **Fallback chỉ khi nghiệp vụ cho phép**, đặc biệt với cache có nguồn chuẩn.
13. **Không nuốt cache invalidation error** nếu yêu cầu freshness chặt.
14. **Xử lý reactive error signals** và không block trên event-loop.
15. **Không giả định transaction/pipeline hoàn toàn rollback** sau exception.
16. **Dùng idempotency và đối soát** khi outcome write không rõ.
17. **Kiểm thử Redis outage, timeout, WRONGTYPE, ACL, Cluster và serializer mismatch.**
18. **Ghi metrics/logs có cấu trúc** với redaction và không tạo label cardinality cao.
19. **Tránh lộ message nội bộ** qua HTTP error response.
20. **Đối chiếu Spring Data Redis/driver version** khi ràng buộc policy vào một exception translation cụ thể.

## 24. Tổng kết

`DataAccessException` là hệ ngoại lệ thống nhất của Spring cho các lỗi truy cập dữ liệu. Spring Data Redis có thể chuyển lỗi từ Lettuce/Jedis thành những subtype như:

- **`RedisConnectionFailureException`**: lỗi kết nối/tài nguyên truy cập Redis.
- **`QueryTimeoutException`**: command timeout trong những đường translation phù hợp.
- **`RedisSystemException`**: Redis-specific error chưa được phân loại chi tiết.
- Các loại `DataAccessException` khác tùy API và phiên bản.

**Exception hierarchy là công cụ phân loại, không phải chính sách retry tự động.** Khi Redis command timeout, thao tác ghi có thể đã xảy ra; khi Redis báo WRONGTYPE/CROSSSLOT/ACL/OOM, retry y nguyên thường không giải quyết nguyên nhân. Với cache, có thể fallback nguồn chuẩn nếu được phép; với dữ liệu nghiệp vụ quan trọng, phải bảo vệ idempotency, tính nhất quán và khả năng đối soát.

Đối với Spring Boot, nên cô lập logic Redis vào adapter rõ ràng, ghi nhận root cause/operation, thiết kế retry/fallback theo semantics, và xử lý đúng sự khác nhau giữa synchronous exceptions, Spring Cache errors và Reactor error signals. Cách này giúp lỗi Redis không âm thầm biến thành sai lệch dữ liệu hoặc lệnh ghi bị thực hiện trùng.

## Tài liệu tham khảo

- Spring Framework — [DataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html).
- Spring Framework — [TransientDataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/TransientDataAccessException.html).
- Spring Framework — [NonTransientDataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/NonTransientDataAccessException.html).
- Spring Framework — [QueryTimeoutException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/QueryTimeoutException.html).
- Spring Data Redis — [RedisConnectionFailureException API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/RedisConnectionFailureException.html).
- Spring Data Redis — [RedisSystemException API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/RedisSystemException.html).
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- Spring Data Redis — [Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html).
- Spring Framework — [Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html).
- Redis — [Command reference](https://redis.io/docs/latest/commands/).
- Redis — [Transactions](https://redis.io/docs/latest/develop/interact/transactions/).
- Redis — [Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
