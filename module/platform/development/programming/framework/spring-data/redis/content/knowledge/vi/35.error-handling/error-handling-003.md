# Phân biệt khóa không tồn tại với lỗi truy cập dữ liệu

Khi ứng dụng Java truy vấn Redis qua **Spring Data Redis**, hai tình huống có vẻ giống nhau ở tầng nghiệp vụ nhưng có ý nghĩa hoàn toàn khác:

1. **Khóa không tồn tại:** Redis xử lý lệnh hợp lệ và xác nhận rằng tại thời điểm đó không có giá trị phù hợp. Đây thường là một **cache miss** hoặc kết quả tra cứu bình thường.
2. **Lỗi truy cập dữ liệu:** ứng dụng không thể hoàn thành hoặc không thể tin cậy kết quả truy vấn vì mất kết nối, timeout, thiếu quyền, sai kiểu Redis, lỗi serialization hoặc lỗi khác. Đây là một **failure**, không phải bằng chứng rằng key không tồn tại.

Nhầm lẫn hai trường hợp có thể dẫn tới hậu quả nghiêm trọng. Ví dụ, một API kiểm tra phiên đăng nhập nhận lỗi Redis nhưng lại trả `null` như thể session không tồn tại; một dịch vụ kiểm tra giới hạn quyền truy cập lại cho phép thao tác vì “không tìm thấy bản ghi khóa”; hoặc một cache-aside service liên tục dồn truy vấn về database khi Redis gặp sự cố.

Mục tiêu của bài học là xây dựng **hợp đồng kết quả rõ ràng** cho thao tác Redis, nhận diện cách các command biểu diễn “không có dữ liệu”, phân loại lỗi ở Spring Data Redis, và đưa ra quyết định retry, fallback hay trả lỗi theo mức độ quan trọng của dữ liệu.

## 1. Mô hình kết quả: hit, miss và failure

Một thao tác đọc cache không chỉ có hai trạng thái “có giá trị” và “không có giá trị”.

| Kết quả quan sát | Ý nghĩa | Hướng xử lý thường gặp |
|---|---|---|
| **HIT** | Command thành công và có value hợp lệ | Trả giá trị cho caller |
| **MISS** | Command thành công nhưng key/field không có theo ngữ nghĩa command | Đọc nguồn sự thật hoặc trả not found theo hợp đồng |
| **ACCESS ERROR** | Redis không trả được kết quả tin cậy | Phân loại lỗi, retry giới hạn hoặc fallback có kiểm soát |
| **INVALID VALUE** | Redis trả bytes/value nhưng ứng dụng không giải mã hoặc không chấp nhận được | Coi là lỗi dữ liệu/serialization, không giả định key không tồn tại |
| **UNKNOWN OUTCOME** | Với một số lệnh có side effect, client mất phản hồi và không biết command đã thực thi chưa | Đối soát hoặc dùng idempotency, không retry mù |

Hai trường hợp đầu là **kết quả nghiệp vụ bình thường** của một lệnh đọc hợp lệ. Những trường hợp sau là **tình huống thất bại hoặc thiếu chắc chắn**, cần chính sách rõ ràng.

Sơ đồ quyết định cho một phép `GET` thông thường:

```text
               Ứng dụng gọi Redis GET
                         |
                         v
                 Command hoàn tất?
                    /          \
                  Có            Không / lỗi
                  |                 |
                  v                 v
           Redis trả value?    ACCESS ERROR
              /      \              |
             Có      Nil             v
             |        |       Retry/fallback/fail
             v        v       theo yêu cầu nghiệp vụ
         Decode     MISS
             |
       +-----+-----+
       |           |
     Hợp lệ      Lỗi decode/schema
       |           |
       v           v
      HIT       INVALID VALUE
```

**Không gộp ACCESS ERROR hoặc INVALID VALUE vào MISS chỉ để trả về `Optional.empty()`.** Làm như vậy khiến caller không phân biệt “dữ liệu thật sự không có” với “hệ thống đang lỗi”.

## 2. Redis trả “không tồn tại” thế nào?

Redis có nhiều cấu trúc dữ liệu và nhiều lệnh. Không có một quy tắc chung rằng “key thiếu thì luôn trả `null`”.

### 2.1. GET với String key không tồn tại

Ví dụ trong Redis CLI:

```bash
redis-cli DEL demo:product:42
redis-cli GET demo:product:42
```

Sau khi xóa, `GET` trả Redis **nil/null bulk reply** (CLI thường hiển thị `(nil)`). Với `StringRedisTemplate.opsForValue().get(...)` thông thường, reply này được chuyển thành Java `null`.

```java
String value = stringRedisTemplate.opsForValue()
        .get("demo:product:42");

if (value == null) {
    // Redis GET đã trả nil trong một lần gọi bình thường.
    // Đây là cache miss, không phải exception.
}
```

Điều kiện “lần gọi bình thường” rất quan trọng: trong pipeline hoặc transaction Redis của Spring Data Redis, giá trị trả về tại thời điểm queue command có thể là `null` vì **chưa có reply thực tế**, không phải vì key thiếu. Phần sau sẽ tách trường hợp này.

### 2.2. Một chuỗi rỗng vẫn là value tồn tại

```bash
redis-cli SET demo:empty ""
redis-cli GET demo:empty
redis-cli EXISTS demo:empty
```

Key `demo:empty` đang tồn tại và value là chuỗi rỗng. Trong Java:

```java
String value = stringRedisTemplate.opsForValue().get("demo:empty");

if ("".equals(value)) {
    // Value tồn tại nhưng rỗng.
}
```

**`""` khác `null`.** Không dùng `value == null || value.isBlank()` để kết luận key không tồn tại nếu chuỗi rỗng là một giá trị hợp lệ của domain.

Tương tự, chuỗi `"null"` hoặc JSON literal `null` được lưu như nội dung string không phải Redis nil. Nó có thể được deserialize thành giá trị `null` ở tầng ứng dụng, nhưng đó là một câu chuyện khác với việc Redis báo không có key.

### 2.3. GET trên key có sai kiểu trả lỗi

Tạo một Set thay cho String:

```bash
redis-cli SADD demo:wrong-type member-1
redis-cli GET demo:wrong-type
```

`GET` trên key kiểu Set sẽ dẫn đến lỗi **WRONGTYPE**, không phải một cache miss. Nếu một ứng dụng bắt mọi exception rồi trả `null`, nó sẽ che khuất việc Redis chứa dữ liệu sai kiểu hoặc hai module đã ghi trùng namespace.

Trong Spring Data Redis, lỗi này thường được thể hiện bằng exception do Redis driver/Spring exception translation phát ra. Loại exception cụ thể có thể khác theo command, driver và phiên bản; nên phân loại dựa trên ý nghĩa lỗi thay vì dựa vào một chuỗi message cứng.

### 2.4. MGET có một khác biệt đáng chú ý

Đối với Redis `MGET`, từng phần tử trong kết quả có thể là nil **khi key không tồn tại hoặc không chứa String value**. Vì vậy, một vị trí `null` trong `MGET` không nhất thiết chứng minh rằng key không tồn tại; nó cũng có thể che một key sai kiểu.

```bash
redis-cli SET demo:a A
redis-cli SADD demo:b set-member
redis-cli MGET demo:a demo:b demo:absent
```

Ví dụ này có thể trả value cho `demo:a` nhưng nil cho cả `demo:b` (sai kiểu String đối với MGET) và `demo:absent` (không tồn tại).

**Quy tắc:** hiểu ngữ nghĩa của **lệnh cụ thể** trước khi diễn giải `null`. Đừng áp logic của `GET` một-key cho mọi thao tác nhiều key.

## 3. HGET, collections, EXISTS và TTL cũng có ý nghĩa riêng

### 3.1. HGET: hash thiếu hay field thiếu?

```bash
redis-cli DEL demo:user:1
redis-cli HGET demo:user:1 email

redis-cli HSET demo:user:1 name "An"
redis-cli HGET demo:user:1 email
```

Cả hai lần `HGET` đều có thể trả nil:

- Lần đầu: **hash key không tồn tại**.
- Lần sau: hash có tồn tại nhưng **field `email` không tồn tại**.

Nếu nghiệp vụ cần phân biệt hai trường hợp, phải thiết kế một kiểm tra riêng hoặc dữ liệu phù hợp. `HGET` một mình không cung cấp hai mã kết quả khác nhau cho “hash không có” và “field không có”.

Với Spring Data Redis:

```java
Object email = redisTemplate.opsForHash()
        .get("demo:user:1", "email");

// Trong ngữ cảnh đọc thông thường, null có thể nghĩa là
// hash/field không có. Không mặc định rằng toàn bộ hash không tồn tại.
```

Nhớ rằng serializer cho hash key và hash value có thể khác serializer của String value. Dữ liệu bytes hợp lệ ở Redis nhưng decode sai cũng có thể tạo lỗi không thuộc loại MISS.

### 3.2. Collection rỗng không phải exception

Một số lệnh với key thiếu trả kết quả rỗng hoặc số không theo quy tắc của Redis:

| Command | Kết quả điển hình khi key không tồn tại | Lưu ý |
|---|---|---|
| `GET key` | nil | Key sai kiểu gây WRONGTYPE |
| `HGET key field` | nil | Không phân biệt hash thiếu với field thiếu |
| `EXISTS key` | 0 | Chỉ phản ánh thời điểm thực thi |
| `TTL key` | -2 | -1 nghĩa là key còn nhưng không có expiry |
| `PTTL key` | -2 | Tương tự TTL nhưng đơn vị millisecond |
| `SCARD key` | 0 | Không phân biệt Set rỗng theo ý nghĩa domain |
| `SMEMBERS key` | tập rỗng | Một empty collection có thể là kết quả thành công |
| `LLEN key` | 0 | Không có list hoặc list rỗng về mặt số phần tử |
| `LRANGE key 0 -1` | danh sách rỗng | Không dùng list empty làm “Redis lỗi” |
| `MGET key1 key2 ...` | nil ở vị trí tương ứng | Nil còn có thể do key không phải String |

Ví dụ Spring Data Redis:

```java
Long size = stringRedisTemplate.opsForSet()
        .size("demo:missing-set");

if (Long.valueOf(0L).equals(size)) {
    // Đây là kết quả số 0 hợp lệ trong một lời gọi thông thường.
}
```

Không nên viết API generic “nếu collection empty thì trả RedisUnavailableException”. Redis thiếu Set cũng có thể là một trạng thái bình thường của nghiệp vụ.

### 3.3. TTL giúp chẩn đoán nhưng không phải giao thức xác thực

```bash
redis-cli TTL demo:product:42
```

Redis dùng các giá trị điển hình:

- **`-2`**: key không tồn tại tại thời điểm chạy `TTL`.
- **`-1`**: key tồn tại nhưng không có thời hạn hết hạn.
- **`0` hoặc số dương**: thời gian còn lại theo giây; với `PTTL` là millisecond.

Vậy:

```text
GET key => nil
TTL key => -2
```

là một dấu hiệu mạnh rằng key không có trong hai thời điểm quan sát. Nhưng hai lệnh **không nguyên tử với nhau**; key có thể được thêm hoặc hết hạn giữa hai lần gọi.

Không dùng `TTL` như nguồn sự thật cho trạng thái authentication hay tồn kho, và không coi `TTL=-1` là lỗi kết nối Redis. Nó là một kết quả hợp lệ: key có tồn tại nhưng không có expiry.

## 4. Phân biệt missing key với lỗi bằng Redis CLI

Trên một Redis test, có thể thử:

```bash
# 1. Key không tồn tại
redis-cli DEL lesson:missing
redis-cli GET lesson:missing

# 2. Key tồn tại chứa String
redis-cli SET lesson:value "READY"
redis-cli GET lesson:value

# 3. Key tồn tại nhưng sai kiểu
redis-cli SADD lesson:set member
redis-cli GET lesson:set

# 4. Kiểm tra tồn tại và TTL
redis-cli EXISTS lesson:value
redis-cli TTL lesson:value
redis-cli EXISTS lesson:missing
redis-cli TTL lesson:missing
```

Diễn giải:

- `GET lesson:missing`: Redis xử lý thành công và trả nil.
- `GET lesson:value`: Redis xử lý thành công và trả chuỗi `READY`.
- `GET lesson:set`: Redis trả lỗi WRONGTYPE.
- `EXISTS lesson:missing`: Redis trả số 0.
- `TTL lesson:missing`: Redis trả -2.
- `TTL lesson:value`: Redis trả -1 nếu chưa có EXPIRE.

Khi kiểm tra lỗi kết nối, **không cần phá hỏng Redis đang dùng chung**. Thực hiện trên môi trường test riêng, chẳng hạn dùng endpoint sai/Redis test bị tắt có kiểm soát, rồi quan sát exception của client. Kết quả “connection refused/timeout” không nên bị gộp với kết quả nil trả từ Redis.

## 5. Spring Data Redis: API bình thường trả null hay ném exception?

Một lời gọi đồng bộ đơn giản:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class StatusCacheReader {

    private final StringRedisTemplate redis;

    public StatusCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String readStatus(String orderId) {
        return redis.opsForValue()
                .get("cache:order:v1:" + orderId);
    }
}
```

Trong ngữ cảnh lệnh `GET` thông thường:

1. Nếu Redis trả một String value hợp lệ, service trả String.
2. Nếu Redis xác nhận key không có, service trả `null`.
3. Nếu Redis không thể truy cập hoặc lệnh bị từ chối, thao tác thường **ném exception**, không trả `null` để thay thế.
4. Nếu dữ liệu không thể deserialize hợp lệ bằng serializer đã cấu hình, thao tác có thể thất bại bằng serialization-related exception.

Spring Data Redis dùng hệ thống exception của Spring Data Access, nổi bật là `org.springframework.dao.DataAccessException` và các subtype/exception được chuyển đổi từ driver. Lỗi connection, timeout, lệnh bị từ chối, type mismatch và lỗi hệ thống không nên được coi là cùng một kiểu business MISS.

### 5.1. Bắt lỗi truy cập đúng phạm vi

```java
import org.springframework.dao.DataAccessException;

public String readStatusOrThrow(String orderId) {
    String key = "cache:order:v1:" + orderId;

    try {
        String value = redis.opsForValue().get(key);

        if (value == null) {
            // Miss được Redis xác nhận trong lời gọi GET bình thường.
            return null;
        }

        return value;
    } catch (DataAccessException error) {
        // Không đổi exception thành null.
        throw new CacheReadUnavailableException(
                "Cannot read order status cache", error);
    }
}
```

Custom exception minh họa:

```java
public class CacheReadUnavailableException extends RuntimeException {
    public CacheReadUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Lưu ý: một số lỗi serialization hoặc mapping có thể **không thuộc mọi subtype của `DataAccessException`** trong tất cả version/serializer. Cần xử lý các lỗi đó tại ranh giới giải mã tương ứng, không dùng `catch (Exception) { return null; }` để gộp tất cả thành miss.

### 5.2. Vì sao catch-all trả null là sai?

Mẫu nguy hiểm:

```java
public String readStatusWrong(String orderId) {
    try {
        return redis.opsForValue().get("cache:order:" + orderId);
    } catch (Exception ignored) {
        return null; // Sai: Redis outage bị giả thành missing key.
    }
}
```

Caller không thể biết lý do `null`:

- Key chưa từng được tạo.
- Key vừa hết TTL.
- Redis bị mất kết nối.
- Command timeout.
- ACL từ chối truy cập.
- Key sai kiểu hoặc serializer không giải mã được.

Hệ quả có thể là API trả `404` sai, tự tạo dữ liệu trùng, hoặc bỏ qua một điều kiện bảo mật mà trước đó được Redis quản lý.

**Không có ngoại lệ truy cập nào là bằng chứng key không tồn tại chỉ vì thông điệp lỗi chứa từ `null` hoặc `not found`.** Cần dựa vào contract của command và loại failure.

## 6. Một hợp đồng kết quả tường minh: Hit, Miss, Error

Trong nhiều ứng dụng, phương thức repository chỉ cần biểu diễn **có giá trị hoặc không có giá trị**, còn lỗi được truyền qua exception. Đây là cách đơn giản và thường phù hợp.

```java
import java.util.Optional;

public Optional<String> findCachedStatus(String orderId) {
    String key = "cache:order:v1:" + orderId;
    String result = redis.opsForValue().get(key);

    // Chỉ gọi Optional.empty khi GET hoàn tất và trả Redis nil.
    return Optional.ofNullable(result);
}
```

Hợp đồng:

- `Optional.of(value)`: Redis GET thành công và có value.
- `Optional.empty()`: Redis GET thành công nhưng key không có.
- Exception: Redis/driver/serialization không cung cấp một kết quả đọc hợp lệ.

Trong một hệ thống cần audit hoặc phản hồi nhiều loại lỗi, có thể tạo model explicit:

```java
public enum CacheLookupStatus {
    HIT,
    MISS
}

public record CacheLookup<T>(
        CacheLookupStatus status,
        T value) {

    public static <T> CacheLookup<T> hit(T value) {
        if (value == null) {
            throw new IllegalArgumentException("Hit value cannot be null");
        }
        return new CacheLookup<>(CacheLookupStatus.HIT, value);
    }

    public static <T> CacheLookup<T> miss() {
        return new CacheLookup<>(CacheLookupStatus.MISS, null);
    }
}
```

Service:

```java
public CacheLookup<String> lookup(String orderId) {
    String key = "cache:order:v1:" + orderId;
    String value = redis.opsForValue().get(key);

    if (value == null) {
        return CacheLookup.miss();
    }

    return CacheLookup.hit(value);
}
```

**Lỗi truy cập vẫn được ném**, không bị gán `MISS`. Nếu API cần trả lỗi như một trường của result model, hãy thêm trạng thái `FAILURE` cùng cause có cấu trúc, nhưng không tạo `MISS` cho exception.

Trên ranh giới HTTP, không nhất thiết trả `404` cho Redis cache miss. **MISS ở cache** chỉ có nghĩa cần hỏi database nguồn, không phải “tài nguyên nghiệp vụ không tồn tại”.

## 7. Cache miss và business not found khác nhau

Giả sử database lưu sản phẩm và Redis chỉ là cache.

```text
HTTP GET /products/p-100
          |
          v
Redis cache lookup
     +----+----+
     |         |
    HIT       MISS
     |         |
     v         v
  Trả DTO   Đọc database
                |
         +------+------+
         |             |
       Tìm thấy      Không thấy
         |             |
         v             v
    Ghi lại cache   Trả 404 theo
    và trả 200      quy tắc API
```

Nếu Redis không sẵn sàng, đường đọc có thể có chính sách **fail-open về database** đối với cache không quan trọng. Nhưng đây là một nhánh thứ ba **ERROR**, không phải MISS:

```text
Redis ERROR
     |
     v
Log/metric cache access failure
     |
     v
Chọn fallback nguồn có giới hạn hoặc trả 503
     |
     v
Không tuyên bố "key không tồn tại"
```

Nếu database tìm thấy sản phẩm trong nhánh lỗi Redis, ứng dụng vẫn có thể trả kết quả hợp lệ. Tuy nhiên metric phải ghi là **Redis unavailable**, không ghi là một cache miss bình thường.

### 7.1. Mẫu service cache-aside có phân biệt lỗi

```java
import java.time.Duration;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductReadService {

    private static final Logger log =
            LoggerFactory.getLogger(ProductReadService.class);

    private final StringRedisTemplate redis;
    private final ProductSource source;

    public ProductReadService(
            StringRedisTemplate redis, ProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public Optional<String> findProductJson(String id) {
        String key = "cache:product:v1:" + id;

        final String cached;
        try {
            cached = redis.opsForValue().get(key);
        } catch (DataAccessException error) {
            // Redis cache lỗi: fallback là quyết định chủ động.
            log.warn("Redis cache read unavailable for product key", error);
            return source.findProductJson(id);
        }

        if (cached != null) {
            return Optional.of(cached);
        }

        // Redis đã xác nhận cache miss.
        Optional<String> fromSource = source.findProductJson(id);

        fromSource.ifPresent(json -> {
            try {
                redis.opsForValue().set(
                        key, json, Duration.ofMinutes(5));
            } catch (DataAccessException error) {
                // Policy riêng cho cache write: nguồn đã đọc xong,
                // vẫn có thể trả dữ liệu nếu cache chỉ là tối ưu.
                log.warn("Cannot populate product cache", error);
            }
        });

        return fromSource;
    }
}
```

Interface dữ liệu nguồn:

```java
import java.util.Optional;

public interface ProductSource {
    Optional<String> findProductJson(String id);
}
```

Ở ví dụ này:

- Cache hit trả ngay JSON đang cache.
- Cache miss đọc database; database mới quyết định “không tìm thấy sản phẩm”.
- Redis read failure được **log riêng**, sau đó fail-open sang nguồn theo chính sách minh họa.
- Redis write failure sau khi đọc được nguồn không nhất thiết làm API thất bại vì cache chỉ là tối ưu.
- Nếu source cũng lỗi, không được tự biến lỗi nguồn thành `Optional.empty()`.
- JSON cache giả định đã được tạo đúng và có schema hợp lệ; cần bổ sung validation/deserialization nếu ứng dụng xử lý DTO, không chỉ trả nguyên String.

Đối với hệ thống có lưu lượng lớn, khi Redis outage, hàng nghìn request đồng thời có thể cùng fallback về database. Vì vậy fail-open phải đi kèm **bulkhead, rate limit, circuit breaker, retry có giới hạn và bảo vệ nguồn**; nếu không, Redis outage có thể kéo theo database outage.

## 8. Khi nào không được fail-open?

Không phải mọi dữ liệu Redis đều là cache dễ tái tạo. Redis có thể chứa session, rate-limit counters, lock, nonce, anti-replay tokens hoặc trạng thái nghiệp vụ ngắn hạn.

| Dữ liệu lưu Redis | Redis báo key không tồn tại | Redis access error |
|---|---|---|
| Cache sản phẩm có database nguồn | Đọc lại nguồn | Có thể fallback về nguồn có giới hạn |
| Session đăng nhập | Phiên không hợp lệ hoặc cần xác thực lại theo policy | Không cho phép truy cập chỉ vì lookup lỗi |
| Rate limit dùng để bảo vệ endpoint nhạy cảm | Áp dụng chính sách khởi tạo bộ đếm phù hợp | Chọn fail-closed hoặc cơ chế bảo vệ thay thế theo threat model |
| Nonce/anti-replay token | Chưa từng sử dụng hoặc hết hạn theo contract | Không mặc định coi request là chưa từng dùng nonce |
| Distributed lock | Lock chưa tồn tại có thể cho phép thử acquire | Lỗi truy cập không đồng nghĩa lock đang trống |
| Giới hạn tồn kho/đặt chỗ | Xử lý thiếu dữ liệu theo invariant nghiệp vụ | Không coi thiếu phản hồi là đủ hàng |
| Idempotency key | Chưa có dấu xử lý, có thể bắt đầu thao tác theo giao thức | Không retry side effect khi outcome không chắc chắn |

Một lỗi Redis không được phép làm ranh giới xác thực yếu đi. Ví dụ, nếu không đọc được session vì connection timeout, không thể suy ra request không cần đăng nhập; với endpoint bảo vệ, ứng dụng thường cần trả lỗi hoặc yêu cầu xác thực theo cách an toàn.

**Fail-open hay fail-closed là quyết định theo dữ liệu và threat model**, không phải tính năng mặc định cho mọi `DataAccessException`.

## 9. Reactive Redis: Mono.empty() khác Mono.error()

Trong Spring Data Redis reactive, phương thức có thể trả `Mono<T>` hoặc `Flux<T>` thay vì value đồng bộ.

Với một thao tác như:

```java
Mono<String> result = reactiveRedisTemplate.opsForValue()
        .get("cache:product:v1:p-100");
```

Trong lời gọi bình thường:

- **Có value:** publisher phát `onNext(value)` rồi `onComplete`.
- **Không có key:** publisher có thể kết thúc bằng `onComplete` mà không phát value, tức `Mono.empty()`.
- **Redis lỗi:** publisher phát `onError(error)`.

Sơ đồ tín hiệu Reactor:

```text
GET hit:
    onNext("READY") -> onComplete

GET miss:
    onComplete             (không onNext)

GET access error:
    onError(exception)     (không onComplete bình thường)
```

Vì vậy, `Mono.empty()` trong kết quả của một `GET` reactive thông thường là biểu diễn phù hợp cho miss. Nhưng cũng như API đồng bộ, phải xem đúng contract của command và serializer. Không suy luận mọi `Flux.empty()` luôn tương đương key thiếu: với các lệnh collection, empty có thể là kết quả tập rỗng hợp lệ.

### 9.1. switchIfEmpty chỉ xử lý nguồn kết thúc rỗng

```java
import reactor.core.publisher.Mono;

public Mono<String> findStatus(String id) {
    String key = "cache:order:v1:" + id;

    return reactiveRedisTemplate.opsForValue()
            .get(key)
            .switchIfEmpty(Mono.defer(
                    () -> statusSource.loadFromDatabase(id)));
}
```

`statusSource.loadFromDatabase(id)` là phương thức reactive giả định trả `Mono<String>`; khi nguồn không có record, nó có thể trả `Mono.empty()`.

Điểm chính:

- `switchIfEmpty(...)` chạy fallback khi Redis GET hoàn tất **không có value**.
- Nếu Redis GET phát `onError`, `switchIfEmpty` **không nuốt lỗi**.
- `Mono.defer(...)` giúp tạo publisher fallback khi nhánh miss thực sự xảy ra.
- Nếu muốn fallback khi Redis lỗi, cần xử lý bằng nhánh lỗi riêng, không trông chờ `switchIfEmpty`.

### 9.2. Cách sai: biến lỗi Redis thành empty

```java
return reactiveRedisTemplate.opsForValue()
        .get(key)
        .onErrorResume(error -> Mono.empty())
        .switchIfEmpty(statusSource.loadFromDatabase(id));
```

Code trên gộp tất cả exception (kể cả lỗi programming/serializer) vào kết quả empty. Caller không phân biệt miss với outage, metric hit/miss bị méo và đường source có thể bị dồn tải.

Tệ hơn, nếu `switchIfEmpty` không có đường nguồn, API có thể báo tài nguyên không tồn tại chỉ vì Redis timeout.

### 9.3. Nếu cố ý fail-open, phải quan sát và giới hạn

```java
import org.springframework.dao.DataAccessException;

public Mono<String> readStatusWithFallback(String id) {
    String key = "cache:order:v1:" + id;

    return reactiveRedisTemplate.opsForValue()
            .get(key)
            .switchIfEmpty(Mono.defer(
                    () -> statusSource.loadFromDatabase(id)))
            .onErrorResume(
                    DataAccessException.class,
                    error -> {
                        log.warn("Redis/source data access error", error);
                        return statusSource.loadFromDatabase(id);
                    });
}
```

Đoạn này chỉ mang tính **minh họa cấu trúc operator**. Khi ghép `onErrorResume` **sau** `switchIfEmpty`, nó còn có thể bắt cả lỗi `DataAccessException` của database source; điều đó có thể khiến source bị gọi hai lần. Để chỉ fallback đối với lỗi Redis, nên gắn error handler **ngay trên Redis publisher trước khi nối nhánh miss**, và tách rõ metric/operation:

```java
public Mono<String> readStatusSafely(String id) {
    String key = "cache:order:v1:" + id;

    Mono<String> cacheLookup = reactiveRedisTemplate
            .opsForValue()
            .get(key)
            .onErrorResume(
                    DataAccessException.class,
                    redisError -> {
                        log.warn("Redis read failure", redisError);
                        return Mono.empty();
                    });

    // Chỉ chọn cách chuyển lỗi thành empty ở đây khi
    // nghiệp vụ CHO PHÉP fail-open và đã ghi metric riêng.
    return cacheLookup.switchIfEmpty(
            Mono.defer(() -> statusSource.loadFromDatabase(id)));
}
```

Trong mã production, nên giữ thông tin lý do fallback dưới dạng metric/tracing hoặc kết quả có trạng thái riêng thay vì để downstream tưởng mọi empty đều là miss. Nếu không thể phân biệt lỗi Redis khỏi sự thiếu dữ liệu ở một nơi downstream quan trọng, hãy dùng một wrapper explicit hoặc cho lỗi đi xuyên qua.

### 9.4. Đừng dùng defaultIfEmpty để che lỗi

```java
return reactiveRedisTemplate.opsForValue()
        .get(key)
        .defaultIfEmpty("UNKNOWN");
```

`defaultIfEmpty` biến **MISS** thành một value mặc định, nhưng không xử lý `onError`. Việc này có thể đúng nếu `UNKNOWN` thực sự là domain default, song nguy hiểm nếu nó khiến tầng quyền truy cập xem một trạng thái “không rõ” là “được phép”.

Một chuỗi rỗng `Mono.just("")` vẫn là một value được phát, khác `Mono.empty()`. Reactive flow có ba trạng thái tách biệt: giá trị, completion rỗng, error.

## 10. Java Optional, null và exception: hợp đồng nên chọn thế nào?

Với service đọc một object, một chữ ký hợp lý là:

```java
public Optional<ProductView> findById(String id);
```

Nếu đó là **repository nghiệp vụ**, `Optional.empty()` có thể nghĩa là database đã được hỏi và không có sản phẩm. Nhưng với **cache repository**, `Optional.empty()` chỉ nghĩa là không có entry trong cache.

Chữ ký giống nhau không có nghĩa semantics giống nhau. Đặt tên cụ thể:

```java
Optional<ProductView> findInCache(String id);
Optional<ProductView> findInDatabase(String id);
```

Sau đó service kết hợp:

```java
public Optional<ProductView> findProduct(String id) {
    Optional<ProductView> cached = cache.findInCache(id);

    if (cached.isPresent()) {
        return cached;
    }

    return database.findInDatabase(id);
}
```

Với code này, lỗi cache được truyền ra qua exception nếu cache method không bắt/fallback. Quyết định fail-open có thể được thực hiện ở một tầng riêng, nơi biết rõ rủi ro khi Redis outage.

Nếu dùng kiểu kết quả có trạng thái riêng, có thể phân biệt:

```text
CacheLookup.Hit(value)
CacheLookup.Miss
CacheLookup.Failure(cause)
```

Nhưng đừng dùng một kiểu `Optional.empty()` để đại diện cho cả miss, lỗi mạng và deserialize failure. Làm vậy khiến mọi caller phải đoán điều gì đã xảy ra.

## 11. Lỗi serialization không phải missing key

Spring Data Redis có thể serialize key/value bằng String, JSON, JDK serialization hoặc cơ chế tùy chỉnh. Redis lưu bytes; Spring Data Redis chuyển bytes thành đối tượng Java.

```text
Redis GET key
      |
      v
Trả byte[] thực tế
      |
      v
RedisSerializer.deserialize(bytes)
      |
   +--+----------------------+
   |                         |
 Decode thành công        Decode thất bại
   |                         |
   v                         v
Value hợp lệ          Serialization/Schema error
```

Ví dụ:

- App v1 lưu JSON có field `price` dạng string.
- App v2 kỳ vọng `price` là object không tương thích.
- Redis vẫn trả bytes, key vẫn tồn tại.
- Jackson/serializer không tạo được `ProductView` tương ứng.

Nếu ứng dụng thấy exception rồi trả `Optional.empty()`, nó đã làm mất dấu **lỗi tương thích dữ liệu**.

### 11.1. Ví dụ phân loại khi tự decode JSON

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public ProductView decodeProduct(
        String redisJson, ObjectMapper mapper) {

    try {
        ProductView value =
                mapper.readValue(redisJson, ProductView.class);

        if (value == null) {
            throw new CachePayloadException(
                    "Cached product payload decoded to null");
        }

        return value;
    } catch (JsonProcessingException error) {
        throw new CachePayloadException(
                "Invalid cached product JSON", error);
    }
}
```

Custom exception:

```java
public class CachePayloadException extends RuntimeException {

    public CachePayloadException(String message) {
        super(message);
    }

    public CachePayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Khi Redis trả JSON string `"null"` như một payload, Jackson có thể decode thành Java `null`. Điều đó **không phải Redis GET nil**; ở đây code coi value này vi phạm hợp đồng cache và phát lỗi payload.

Với một ứng dụng cache-aside, có thể coi payload không hợp lệ là lý do để **invalidate rồi nạp lại dữ liệu** nếu có nguồn sự thật đáng tin. Nhưng cần ghi metric, giới hạn retry và cẩn thận với race: chỉ xóa key nếu có cơ chế phù hợp khi nhiều writer đang cập nhật cache, tránh xóa một bản mới được người khác ghi sau lúc mình đọc.

### 11.2. Key serializer khác nhau tạo “miss giả”

Nếu một service dùng `StringRedisTemplate` còn service khác dùng `RedisTemplate` với key serializer JDK mặc định/khác, hai service có thể đang đọc **hai tên khóa vật lý khác nhau** dù truyền cùng Java String.

```text
Java key: "product:100"

String serializer:
  Redis key bytes = UTF-8("product:100")

Serializer khác:
  Redis key bytes = dãy bytes khác
```

Khi đó `GET` có thể trả nil một cách hoàn toàn hợp lệ, vì **key vật lý mà service truy vấn không phải key đang được service khác ghi**. Về mặt Redis, đó là miss thật; về mặt hệ thống, nguyên nhân là cấu hình namespace/serializer sai.

Cần kiểm tra serializer của cả key, value, hash key, hash value và phiên bản schema. Không tự kết luận “Redis làm mất dữ liệu” khi chỉ một ứng dụng vừa đổi serializer hoặc prefix.

## 12. Spring Cache: không có entry và entry chứa null

Spring Cache abstraction có thể lưu **giá trị null được biểu diễn qua một sentinel nội bộ**, tùy provider và cấu hình. Do đó, ý nghĩa `null` ở lớp Spring Cache không hoàn toàn giống trực tiếp Redis `GET`.

Ví dụ dùng `CacheManager`:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

public void inspectCache(CacheManager cacheManager) {
    Cache cache = cacheManager.getCache("productById");

    if (cache == null) {
        // Không tồn tại cache name hoặc không được tạo,
        // phụ thuộc cách cấu hình CacheManager.
        return;
    }

    Cache.ValueWrapper wrapper = cache.get("p-100");

    if (wrapper == null) {
        // Không có entry theo contract Cache.get(key).
    } else {
        Object cached = wrapper.get();

        if (cached == null) {
            // Có một entry đã cache null, nếu provider hỗ trợ.
        } else {
            // Có entry và có value.
        }
    }
}
```

Ba trường hợp cần tách:

1. `cacheManager.getCache(name) == null`: cache name không có hoặc không được tạo theo configuration.
2. `cache.get(key) == null`: không có entry trong cache.
3. `cache.get(key) != null` nhưng `wrapper.get() == null`: cache provider đang biểu diễn một giá trị null đã cache.

Lỗi kết nối Redis tại `cache.get(...)` vẫn là **failure**, không phải nhánh 2.

### 12.1. @Cacheable với giá trị null

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        unless = "#result == null")
public ProductView findById(String id) {
    return database.findProductOrNull(id);
}
```

`unless = "#result == null"` ngăn caching kết quả null ở cấp method. Ở Redis Cache manager cũng có thể cấu hình:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .disableCachingNullValues();
```

**Không cache null** phù hợp khi dữ liệu mới có thể xuất hiện nhanh và không muốn trả “không có” sau khi database tạo bản ghi. Nhưng nếu các ID không tồn tại bị truy vấn lặp liên tục, **negative caching** với TTL ngắn có thể hữu ích. Quyết định phải dựa trên workload.

Nếu provider vẫn được cấu hình cache null, hãy hiểu rằng một cached-null entry có thể làm phương thức `@Cacheable` **không chạy lại** trong thời gian TTL. Không nên nhầm “method trả null từ cache” với “Redis đang mất kết nối”.

### 12.2. CacheErrorHandler: xử lý lỗi không phải đổi mọi lỗi thành miss

Spring Cache cho phép cấu hình `CacheErrorHandler` để kiểm soát lỗi get/put/evict/clear ở lớp cache abstraction. Nhưng cần cân nhắc:

- Bỏ qua lỗi **GET** có thể làm method nguồn chạy lại; phù hợp với cache thuần tối ưu khi nguồn được bảo vệ.
- Bỏ qua lỗi **PUT** có thể cho phép request trả dữ liệu nguồn dù cache chưa được cập nhật.
- Bỏ qua lỗi **EVICT** sau database mutation có thể khiến cache cũ vẫn được phục vụ trong TTL.
- Với cache chứa quyền truy cập, session hoặc điều kiện bảo mật, bỏ qua lỗi có thể không an toàn.
- Ghi metric và logging riêng cho lỗi cache; không tính chúng là cache miss bình thường.

Một error handler rộng mà nuốt tất cả exception có thể che lỗi serializer, cấu hình và invalidation. Không bật theo mặc định chỉ vì muốn ứng dụng “không chết khi Redis lỗi”.

## 13. Negative caching: biểu diễn “không tồn tại” như dữ liệu có TTL

Khi database xác nhận một record không tồn tại, ứng dụng có thể cache **kết quả âm tính** trong thời gian ngắn để tránh cùng một ID bị query nguồn liên tục.

Thay vì dùng Redis nil, có thể lưu một object/sentinel:

```json
{
  "found": false,
  "checkedAtEpochMs": 1780000000000
}
```

Hoặc:

```text
cache:product:v1:p-404 -> "NOT_FOUND" (TTL 15 giây)
```

Quan trọng: `NOT_FOUND` là **một value Redis thực sự tồn tại**. Khi `GET` trả chuỗi `NOT_FOUND`, đó là cache HIT biểu diễn **business not found**, không phải Redis miss.

Phân loại:

| Redis response | Cache interpretation | Business interpretation |
|---|---|---|
| nil | MISS | Chưa biết sản phẩm có hay không |
| JSON product hợp lệ | HIT-positive | Sản phẩm tồn tại |
| Sentinel `NOT_FOUND` | HIT-negative | Nguồn đã xác nhận không có tại thời điểm trước |
| Exception | ERROR | Không biết trạng thái dữ liệu |
| Payload không hợp lệ | INVALID VALUE | Không thể tin bản cache |

Những giới hạn:

- Negative TTL nên ngắn nếu entity có thể được tạo.
- Khi tạo entity mới, phải xóa hoặc ghi đè negative entry.
- Không lưu timeout/Redis error/database error như một negative value.
- Sentinel phải không xung đột với value hợp lệ trong domain.
- Với multi-tenant, key phải có tenant ID nếu kết quả khác theo tenant.
- Nếu ID có thể vô hạn do user nhập, negative caching cần giới hạn để tránh tạo hàng triệu key rác.

**Không dùng “tạo sentinel NOT_FOUND khi Redis timeout”**: timeout không chứng minh dữ liệu nguồn không tồn tại.

## 14. EXISTS + GET có loại bỏ sự nhập nhằng không?

Có thể nghĩ rằng chỉ cần:

```java
Boolean exists = stringRedisTemplate.hasKey(key);
String value = stringRedisTemplate.opsForValue().get(key);
```

là phân biệt được mọi tình huống. Nhưng hai command không nguyên tử với nhau.

```text
Request A                            Request B
    |                                    |
    +-- EXISTS key -> true               |
    |                               DEL key
    +-- GET key -> nil                    |
```

Hoặc ngược lại:

```text
Request A                            Request B
    |                                    |
    +-- EXISTS key -> false              |
    |                               SET key value
    +-- GET key -> value                 |
```

Như vậy, `EXISTS` hữu ích để chẩn đoán một thời điểm nhưng không đảm bảo trạng thái ổn định tới lần `GET` kế tiếp. Nếu chỉ cần đọc String value, **một lệnh GET thường là đủ** để phân biệt hit với miss theo contract.

### 14.1. Khi cần tính nhất quán theo điều kiện

Nếu nghiệp vụ cần “nếu key chưa có thì tạo, và chỉ một request được tạo”, không dùng:

```text
EXISTS key
if false:
    SET key value
```

vì có race. Dùng Redis command phù hợp như `SET key value NX` với TTL nếu cần, hoặc Lua script để kiểm tra–ghi trên server trong ranh giới nguyên tử.

Ví dụ:

```bash
redis-cli SET lock:order:42 unique-token NX PX 10000
```

Thao tác này giải quyết một bất biến cụ thể (chỉ tạo lock nếu chưa có). Nó không giải quyết mọi yêu cầu về transaction và không đồng nghĩa việc đọc/ghi khác trên nhiều key đã nguyên tử.

### 14.2. Pipeline và transaction là ngoại lệ quan trọng với null

Trong Spring Data Redis synchronous API, khi thực thi trong **pipeline hoặc transaction Redis**, nhiều operation trả về `null` tại thời điểm Java gọi vì kết quả chưa được trả ngay. Ví dụ kết quả thực tế của các lệnh pipeline sẽ được thu thập sau khi pipeline hoàn tất.

```text
Trong callback pipeline:
    GET key -> Java có thể thấy null ngay lúc queue command
    (chưa có reply để kết luận key thiếu)

Sau executePipelined:
    Danh sách kết quả mới chứa reply đã được chuyển đổi.
```

Do đó, không viết logic:

```java
// Pseudocode sai nếu đang queue command trong pipeline:
String result = operations.opsForValue().get(key);
if (result == null) {
    createMissingRecord();
}
```

bởi vì `null` lúc queue không có cùng nghĩa với Redis nil trả về sau khi lệnh đã chạy. Tương tự, lệnh được queue trong `MULTI` phải được đánh giá qua `EXEC`, không qua return value tạm thời tại lúc queue.

**Trước khi diễn giải null từ Spring Data Redis, phải biết đang ở normal execution, pipeline hay transaction.**

## 15. Lỗi nào nên retry, lỗi nào không?

Không phải mọi lỗi truy cập Redis có cùng phương án xử lý.

| Loại lỗi | Có thể retry? | Lưu ý |
|---|---|---|
| Timeout/connection failure trên **GET idempotent** | Có thể retry ngắn có backoff | Nhưng retry quá nhiều làm tăng tải và latency |
| Redis unavailable trên cache-aside read | Có thể fallback database | Phải bảo vệ database khỏi bão tải |
| `WRONGTYPE` | Không retry mù | Cần sửa schema, namespace hoặc data |
| ACL/NOAUTH/NOPERM | Không retry như lỗi mạng | Sửa cấu hình/quyền |
| Key/slot routing lỗi trong Redis Cluster | Driver có thể xử lý redirect | Không coi mọi lỗi cross-slot là transient |
| Serialization/schema error | Không retry network mù | Kiểm tra serializer/migration/payload |
| Missing key từ GET | Không phải lỗi cần retry | Cache miss hoặc negative cache theo policy |
| Timeout sau `INCR`/ghi có side effect | Không retry vô điều kiện | Outcome có thể đã thành công |
| Redis replica read trả giá trị cũ | Retry không luôn đủ | Consistency/read preference/version |
| Eviction/invalidation failure | Có thể cần xử lý bù/reconcile | Tránh tiếp tục trả cache stale không giới hạn |

### 15.1. Retry trên GET chỉ khi nằm trong ngân sách

Một `GET` thuần túy là idempotent theo ý nghĩa đọc. Có thể retry khi gặp lỗi transient, nhưng cần giới hạn tổng thời gian API:

```text
HTTP deadline:          800 ms
Redis GET timeout:      150 ms
Retry backoff:           50 ms
Database fallback:      400 ms
Response processing:     phần còn lại
```

Các số chỉ minh họa. Nếu Redis đang outage hoàn toàn, retry ba lần trên mỗi request có thể làm bão connection và tăng độ trễ; trong trường hợp này circuit breaker/fallback có giới hạn thường hiệu quả hơn.

### 15.2. Với thao tác ghi, timeout có thể cho outcome bất định

```text
Client: INCR rate:login:failed
        |
        v
Redis thực thi INCR thành công
        |
        v
Mất kết nối trước reply
        |
        v
Client nhận timeout
```

Nếu client retry `INCR` như thể lệnh trước chưa chạy, bộ đếm tăng hai lần. Vì vậy, lesson “phân biệt missing với lỗi” cũng áp dụng cho **mutation**: lỗi truy cập không chứng minh Redis chưa thay đổi.

Thiết kế operation ID/idempotency, Lua script có kiểm tra duplicate hoặc cơ chế đối soát khi cần at-most-once business effect.

## 16. Redis Cluster và replica đọc làm việc chẩn đoán phức tạp hơn

Trong Redis Cluster:

- Key có slot và primary owner.
- MOVED/ASK redirect có thể xuất hiện khi topology thay đổi.
- Multi-key command có giới hạn slot.
- Mất kết nối tới một node không có nghĩa toàn bộ Cluster không có dữ liệu.
- Read preference tới replica có thể trả trạng thái chậm hơn primary.

Ví dụ:

```text
T0: Primary A nhận SET key=value.
T1: Replica A chưa replicate xong.
T2: Client được định tuyến GET key tới replica A.
T3: Replica A trả nil.
```

Ở T3, reply nil là một kết quả đọc hợp lệ **của replica tại thời điểm đó**, nhưng không khẳng định key không tồn tại trên primary hoặc trong nguồn dữ liệu authoritative. Vì vậy, thuật ngữ “Redis xác nhận key không tồn tại” luôn phải gắn với **node/consistency policy được dùng để đọc**.

Nếu một ứng dụng dùng Redis session, distributed lock hoặc dữ liệu cần read-your-writes, phải chọn nguồn đọc thích hợp. Không bật replica reads cho các quyết định bảo mật quan trọng mà chưa xác định được tính nhất quán.

### 16.1. Phân biệt cache miss với namespace sai

Một service có thể sử dụng:

```text
Service A: cache:product:v1:p-100
Service B: cache:product:v2:p-100
```

Service B nhận nil, nhưng service A vẫn có dữ liệu. Đây không phải lỗi mạng; đó là hai key khác nhau. Tương tự Redis Cluster hash tag, tenant prefix, environment prefix và serializer đều ảnh hưởng key vật lý.

Để điều tra, ghi nhận **namespace và mã định danh không nhạy cảm** thay vì log session ID/token thật. Trong production, tránh dùng `KEYS *` để tìm mọi key; dùng kiểm tra các key cụ thể hoặc `SCAN` có giới hạn theo topology phù hợp.

## 17. Spring Session và session login: không thể coi lỗi Redis là phiên hết hạn

Một ứng dụng dùng Spring Session Data Redis có thể lưu thông tin đăng nhập trong Redis. Khi request mang session cookie, framework tìm session theo ID.

Cần tách:

1. Session ID không tồn tại hoặc đã hết hạn thật: ứng dụng có thể yêu cầu đăng nhập lại.
2. Redis kết nối lỗi: ứng dụng chưa xác định session còn hợp lệ hay không.
3. Session payload không deserialize được: có thể có lỗi version/migration, không phải session bị xóa.
4. Replica lag: một node có thể chưa thấy thay đổi session/revocation.

Đối với endpoint bảo vệ, **không được cấp quyền chỉ vì Redis unavailable**. Một hệ thống có thể fail closed hoặc áp dụng cơ chế xác thực dự phòng được thiết kế, nhưng không biến một Redis timeout thành “guest được phép truy cập mọi thứ”.

Đối với UI, có thể hiển thị trang thông báo lỗi tạm thời khác với trang yêu cầu login lại. Phân loại rõ giúp người vận hành biết người dùng bị logout thật hay hạ tầng session đang lỗi.

## 18. Quan sát lỗi và cache miss bằng metric

Nếu mọi lỗi bị gộp vào một biểu đồ `cache_miss_total`, người vận hành có thể thấy miss rate tăng mà không phát hiện Redis đang mất kết nối.

Nên có các nhóm metric:

| Metric | Ý nghĩa |
|---|---|
| `cache_lookup_hit_total` | Đọc cache thành công có value |
| `cache_lookup_miss_total` | Đọc cache thành công nhưng không có entry |
| `redis_read_error_total` | Lỗi khi truy cập Redis |
| `cache_payload_invalid_total` | Redis trả value nhưng không giải mã/xác thực được |
| `cache_fallback_to_source_total` | Số lần chọn đọc nguồn do lỗi Redis |
| `cache_miss_source_load_total` | Số lần đọc nguồn do cache miss bình thường |
| `redis_command_latency` | Độ trễ lệnh Redis, phân nhóm theo loại command |
| `redis_timeout_total` | Timeout theo command và endpoint |
| `redis_connection_failure_total` | Lỗi kết nối/reconnect |
| `cache_write_error_total` | Lỗi populate cache hoặc update |
| `cache_evict_error_total` | Lỗi invalidation có thể dẫn tới stale data |
| `source_load_error_total` | Lỗi nguồn database/API |
| `negative_cache_hit_total` | Truy vấn gặp bản ghi not-found đã cache |
| `cache_consistency_anomaly_total` | Phát hiện bất nhất qua đối soát |

Không nên gắn nguyên product ID, session ID hoặc mọi Redis key vào metric label vì cardinality có thể tăng không giới hạn và có nguy cơ lộ dữ liệu nhạy cảm. Thay vào đó, dùng cache name, command, error category, environment, node/slot group khi phù hợp.

### 18.1. Theo dõi Redis từ CLI

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO clients
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

Một số câu hỏi:

- Redis có bị evict key trước TTL vì memory pressure không?
- Kết nối client có tăng hoặc bị từ chối?
- Lệnh có bị chậm ở server hay client timeout do mạng?
- `GET` chạy thành công nhưng miss tăng, hay lệnh thất bại?
- Có thay đổi serializer, namespace hoặc cache version gần thời điểm lỗi không?

`INFO` và `SLOWLOG` không trực tiếp cho biết business not found hoặc vì sao ứng dụng giải mã lỗi; phải kết hợp metric phía Java và truy vết theo request.

## 19. Tình huống thực tế: trả 404 sai khi Redis outage

Một API quản lý sản phẩm:

```java
@GetMapping("/products/{id}")
public ResponseEntity<?> getProduct(@PathVariable String id) {
    ProductView product = cacheService.find(id);

    if (product == null) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.ok(product);
}
```

Nếu `cacheService.find` có `catch (Exception) { return null; }`, API trả `404` cho cả trường hợp Redis đang timeout.

Vấn đề:

- Khách hàng nhận thông tin “sản phẩm không tồn tại” dù sản phẩm vẫn có trong database.
- Hệ thống giám sát có thể không báo lỗi hạ tầng vì HTTP chỉ trả 404.
- Client có thể cache nhầm response not-found.
- Điều tra sự cố khó vì exception đã bị nuốt.

Thiết kế rõ hơn:

```text
Cache hit -> trả sản phẩm 200

Cache miss -> hỏi database
             |
             +-- database có -> 200
             +-- database không -> 404

Redis error -> nếu cache chỉ là tối ưu:
               hỏi database với giới hạn tải
               |
               +-- database có -> 200
               +-- database không -> 404
               +-- database cũng lỗi -> 503/5xx theo policy

Redis error -> nếu dữ liệu Redis là nguồn quyết định bắt buộc:
               trả lỗi thích hợp, không suy ra missing
```

Điểm then chốt là **404 chỉ xuất hiện khi nguồn có thẩm quyền xác nhận tài nguyên không tồn tại**, không xuất hiện chỉ vì một cache lookup thất bại.

## 20. Tình huống thực tế: kiểm tra khóa trước khi tạo resource

Một service có logic:

```java
Boolean exists = redisTemplate.hasKey(key);

if (Boolean.FALSE.equals(exists)) {
    // Tạo resource
}
```

Trong một lời gọi thông thường, `false` có thể là kết quả Redis xác nhận key chưa có tại thời điểm kiểm tra. Nhưng:

- `hasKey` có thể ném exception nếu lỗi Redis.
- Trong transaction/pipeline, giá trị immediate có thể là `null` vì lệnh đang được queue.
- Kết quả `false` đã có thể lỗi thời khi request khác tạo key.
- Nếu đây là nghiệp vụ chỉ cho phép tạo một resource, `EXISTS` rồi `SET` không đủ nguyên tử.

Vì vậy:

```text
hasKey == false  -> Quan sát key không tồn tại lúc kiểm tra.
hasKey == true   -> Quan sát key tồn tại lúc kiểm tra.
hasKey throws    -> Không có bằng chứng để quyết định.
hasKey == null trong pipeline/transaction
                 -> Chưa có kết quả lệnh tức thời.
```

Đối với bất biến “chỉ tạo nếu chưa có”, dùng `SET ... NX` hoặc Lua script phù hợp; không xử lý `DataAccessException` như `false`.

## 21. Tình huống thực tế: lỗi invalidation sau khi ghi database

Giả sử code:

```text
1. UPDATE product trong database thành công.
2. DEL cache:product:v1:p-100 trong Redis.
3. Redis DEL timeout.
```

Bây giờ:

- Database có dữ liệu mới.
- Redis có thể vẫn giữ bản cũ, hoặc eviction đã thành công nhưng client không nhận reply.
- Nếu trả thành công mà không giám sát lỗi invalidation, request sau có thể đọc cache stale.
- Nếu retry `DEL`, thao tác xóa thường idempotent về hiệu quả, nhưng vẫn cần cân nhắc race: một request khác có thể vừa nạp giá trị mới rồi bị xóa; thường ảnh hưởng performance hơn là consistency nếu nguồn có thẩm quyền, nhưng phải hiểu trình tự.

Lỗi eviction không phải “cache miss” và cũng không phải “dữ liệu nguồn không tồn tại”. Cần có TTL như giới hạn độ cũ khi phù hợp, event/outbox invalidation hoặc một đường reconcile cho những trường hợp quan trọng.

## 22. Kiểm thử phân loại kết quả

Một bộ test nên kiểm tra cả **kết quả Redis bình thường** lẫn **failure path**.

### 22.1. Bảng test đồng bộ

| Kịch bản | Kết quả từ Redis | Hợp đồng service |
|---|---|---|
| GET key tồn tại | `"READY"` | HIT, value `READY` |
| GET key thiếu | nil/Java `null` | MISS, không exception |
| GET key chứa chuỗi rỗng | `""` | HIT với value rỗng nếu hợp lệ |
| GET key sai kiểu | WRONGTYPE | Failure, không MISS |
| Redis connection refused | Exception | Failure hoặc explicit fallback |
| Redis timeout | Exception | Failure hoặc explicit fallback |
| Key serializer sai | Redis nil ở key vật lý khác | Cần phát hiện lỗi cấu hình, không đánh đồng lỗi mạng |
| JSON payload lỗi | Value bytes nhưng decode thất bại | INVALID VALUE |
| Redis key chứa cached negative sentinel | Value `NOT_FOUND` | HIT-negative, không Redis miss |
| `HGET` field thiếu | nil | Field missing, không nhất thiết hash missing |
| `TTL` trả -1 | Key tồn tại không expiry | Không báo missing |
| `TTL` trả -2 | Key không tồn tại tại thời điểm command | Missing theo TTL contract |
| `MGET` có vị trí null | Nil của vị trí đó | Có thể missing **hoặc** key sai type |

### 22.2. Reactive: kiểm tra tín hiệu bằng StepVerifier

Với một phương thức `Mono<String>` dựa trên GET, có thể viết các test theo contract:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

// Mô phỏng Redis GET trả value:
StepVerifier.create(Mono.just("READY"))
        .expectNext("READY")
        .verifyComplete();

// Mô phỏng Redis GET miss:
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();

// Mô phỏng Redis GET lỗi:
StepVerifier.create(
                Mono.<String>error(
                        new IllegalStateException("Redis unavailable")))
        .expectError(IllegalStateException.class)
        .verify();
```

Đây là ví dụ về **các loại tín hiệu Reactor**, không tự kiểm thử tích hợp Spring Data Redis. Muốn xác nhận thật, dùng Redis test/connection factory và các tình huống timeout, WRONGTYPE, serializer mismatch với key cụ thể.

Đối với một reactive service sử dụng `switchIfEmpty`, cần kiểm tra rằng fallback chỉ chạy khi upstream empty. Đối với `onErrorResume`, cần kiểm tra nhánh lỗi được log/metric và không bị tính là cache miss.

### 22.3. Kiểm thử với Redis thật

Một quy trình tích hợp:

1. Khởi động Redis trong môi trường test.
2. Gọi `GET` trên key chưa tồn tại; xác nhận kết quả MISS.
3. Ghi value rỗng; xác nhận HIT không bị xem là MISS.
4. Ghi Set vào cùng key rồi dùng GET; xác nhận xuất hiện failure.
5. Tắt Redis test hoặc cấu hình endpoint sai; xác nhận connection failure được xử lý riêng.
6. Dùng serializer không tương thích; xác nhận payload error không thành MISS.
7. Bật giới hạn TTL ngắn; xác nhận key hết hạn được nhìn nhận như miss bình thường.
8. Với reactive API, xác nhận `Mono.empty()` và `Mono.error()` đi vào hai nhánh khác nhau.
9. Với CacheManager, thử cached null khi provider hỗ trợ và trường hợp không có entry.
10. Thử fallback khi Redis outage dưới tải đồng thời để đảm bảo không gây quá tải database.

Không cần chạy destructive commands trên Redis production để chứng minh các nguyên lý này.

## 23. Các sai lầm phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| `catch (Exception) { return null; }` | Nuốt Redis outage, báo sai not-found | Phân loại exception, chỉ chọn fallback có chủ đích |
| `onErrorResume(e -> Mono.empty())` cho mọi lỗi | Error bị giả thành reactive miss | Chỉ fallback khi policy cho phép và ghi metric riêng |
| `null` từ pipeline/transaction là key thiếu | Tạo nhầm dữ liệu vì chưa có reply | Đọc kết quả sau pipeline/EXEC |
| `MGET` null nghĩa là key chắc chắn thiếu | Bỏ qua khả năng value sai type | Hiểu contract MGET, kiểm tra schema |
| HGET null nghĩa là cả hash không tồn tại | Kết luận sai về object | Phân biệt hash và field nếu nghiệp vụ cần |
| Empty Set/List nghĩa là Redis lỗi | Trả lỗi sai với dữ liệu rỗng hợp lệ | Hiểu return type từng lệnh |
| `EXISTS` rồi `SET` là nguyên tử | Race giữa nhiều client | `SET NX`/Lua |
| GET trả String `"null"` coi như key missing | Nhầm serialized value với Redis nil | Tách cache payload và Redis reply |
| Serializer lỗi được convert thành Optional.empty | Che lỗi deploy/schema | Báo INVALID VALUE, migration/fallback |
| Redis cache miss trả HTTP 404 ngay | Nhầm cache với nguồn sự thật | Hỏi database nguồn |
| Redis lỗi vẫn cho qua authentication/rate limit | Có thể bypass bảo vệ | Fail-closed hoặc cơ chế được đánh giá |
| Redis outage thì tất cả request đổ vào DB | Gây cache avalanche/dồn tải | Circuit breaker/bulkhead/rate limit |
| Retry `INCR` sau timeout không kiểm tra | Side effect lặp | Idempotency và unknown-outcome handling |
| Redis replica nil coi primary cũng thiếu | Có thể đọc dữ liệu stale | Consistency policy/read primary khi cần |
| Không phân biệt negative cache với miss | Sai semantics not-found | Sentinel/DTO/TTL rõ ràng |
| Log mọi Redis key/session ID | Rò rỉ secret, metric cardinality lớn | Log namespace/category, sanitize |
| Cache get error và evict error cùng bị nuốt | Dữ liệu stale lâu hoặc nguy cơ bảo mật | Chính sách khác nhau cho read/write/invalidate |

## 24. Quy trình lựa chọn cho một Redis lookup

```text
Cần đọc một key từ Redis
             |
             v
Chọn đúng command và serializer
             |
             v
Thực thi lệnh (không nhầm pipeline/transaction)
             |
       +-----+-------+------------------+
       |             |                  |
    Value          Nil/Empty          Exception
       |             |                  |
       v             v                  v
  Deserialize    Hiểu contract     ACCESS ERROR
       |          command               |
   +---+---+         |              +----+----+
   |       |         v              |         |
  OK      Fail      MISS         Cache-only  Security /
   |       |         |             read?     critical?
   v       v         |              |         |
  HIT   INVALID      |              v         v
        VALUE        |          Fallback    Fail closed/
                     |          giới hạn    explicit error
                     |
                     v
              Redis có phải
              nguồn sự thật?
                +----+----+
                |         |
               Có        Không
                |         |
                v         v
         Chính sách     Đọc database
         missing domain     |
                |       +---+---+
                |       |       |
                |      Có     Không
                |       |       |
                v       v       v
             Kết quả  Trả     Business
             domain   value   not found
```

### Nguyên tắc ghi nhớ

1. **Miss là một kết quả thành công của lệnh đọc**, không phải tên khác của exception.
2. **Null/empty mang nghĩa theo từng command và execution context**: GET, HGET, MGET, collection operations, pipeline và transaction có semantics khác nhau.
3. **Redis reply, serializer và business domain là ba tầng khác nhau**: key có thể tồn tại nhưng payload không hợp lệ, hoặc cache có thể chứa sentinel “not found”.
4. **Lỗi Redis không chứng minh dữ liệu nguồn không có**. Nếu cần business 404, hãy để nguồn có thẩm quyền xác nhận.
5. **Fallback phải phụ thuộc nghiệp vụ**: cache-aside read có thể fail-open; authentication, idempotency và các điều kiện an toàn thường không được tùy tiện fail-open.
6. **Retry cần phân loại lỗi và tính idempotent**. Timeout của lệnh ghi có thể khiến outcome không xác định, còn WRONGTYPE/serializer error thường không được giải quyết bằng retry mạng.
7. **Monitoring phải tách MISS, ACCESS ERROR và INVALID VALUE** để không che sự cố hạ tầng hoặc migration.

## 25. Kết luận

Trong **Spring Data Redis**, việc một khóa không tồn tại thường được thể hiện như một **kết quả đọc bình thường**: `GET` trả nil, `StringRedisTemplate.opsForValue().get` trả Java `null` khi chạy trực tiếp, còn reactive `GET` thường hoàn thành bằng `Mono.empty()`. Ngược lại, **lỗi truy cập dữ liệu** đi theo đường exception hoặc `Mono.error()`; lỗi serializer, sai kiểu Redis, timeout và thiếu quyền không thể bị biến thành “không tìm thấy” mà không làm mất ý nghĩa của hệ thống.

Tính đúng đắn nằm ở **hợp đồng từng tầng**: biết command trả gì, biết serializer xử lý gì, biết cache miss có cần hỏi database, và biết lỗi Redis có được fallback hay phải trả lỗi. Với ứng dụng chỉ dùng Redis làm cache, có thể chọn fallback nguồn có kiểm soát. Với session, quyền truy cập, khóa, idempotency và các trạng thái nghiệp vụ quan trọng, phải ưu tiên bảo đảm an toàn và tính nhất quán.

**Quy tắc cốt lõi: không lấy “không đọc được dữ liệu” làm bằng chứng rằng “dữ liệu không tồn tại”.**

