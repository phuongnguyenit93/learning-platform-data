# Chọn cấu trúc dữ liệu phù hợp trước khi áp dụng một mẫu

Trong **Spring Data Redis**, cùng một bài toán có thể được triển khai bằng nhiều cấu trúc Redis khác nhau. Một sản phẩm có thể được cache thành một `String` JSON hoặc một `Hash`; danh sách việc cần làm có thể dùng `List` hoặc `Stream`; bảng xếp hạng nên dùng `Sorted Set` thay vì tự tải một danh sách về Java để sắp xếp.

Chọn sai cấu trúc có thể khiến ứng dụng phải quét toàn bộ dữ liệu, tạo race condition, gặp `CROSSSLOT` trong Redis Cluster, không thể đặt TTL đúng yêu cầu hoặc phải tự xây lại những khả năng Redis đã hỗ trợ bằng lệnh nguyên tử.

**Nguyên tắc xuất phát:** đừng bắt đầu từ câu hỏi “nên dùng String hay Hash?”, mà hãy bắt đầu từ **những thao tác nghiệp vụ cần thực hiện**, tính nhất quán cần bảo đảm và cách dữ liệu sẽ tăng trưởng. Sau đó mới chọn một cấu trúc Redis và ánh xạ nó sang API phù hợp của Spring Data Redis.

Bài học này đưa ra một quy trình lựa chọn, đối chiếu các loại cấu trúc, ví dụ Java và những trường hợp cần chuyển thiết kế khi yêu cầu ban đầu thay đổi.

## 1. Mô hình hóa cách truy cập dữ liệu trước khi chọn kiểu Redis

Trước khi viết `RedisTemplate.opsForValue()` hay `opsForHash()`, hãy mô tả đường đọc/ghi của tính năng.

Ví dụ hệ thống thương mại điện tử có các nhu cầu:

| Nhu cầu | Câu hỏi phải trả lời | Tác động đến cấu trúc |
|---|---|---|
| Cache chi tiết sản phẩm | Đọc toàn bộ object hay chỉ vài field? | `String` JSON hoặc `Hash` |
| Đếm số lượt xem | Có cần tăng nguyên tử với nhiều request cùng lúc? | `String` và `INCR` |
| Danh sách ID sản phẩm yêu thích | Có cần kiểm tra thành viên nhanh và không trùng lặp? | `Set` |
| Top sản phẩm bán chạy | Có cần lấy top N theo điểm, lấy hạng và cập nhật điểm? | `Sorted Set` |
| Hàng đợi tác vụ | Có cần ACK/retry sau khi worker chết? | `Stream` thường hợp hơn `List` đơn giản |
| Kiểm soát tốc độ request | Đếm trong cửa sổ thời gian hay cần sliding window? | `String`/`Sorted Set` với lệnh nguyên tử hoặc Lua |
| Đếm người dùng duy nhất | Có chấp nhận ước lượng không? | `HyperLogLog` nếu chấp nhận sai số |
| Vị trí cửa hàng | Có tìm theo tọa độ/khoảng cách không? | Redis GEO commands |
| Cờ bật/tắt hàng triệu vị trí | Chỉ số vị trí có rõ và tương đối dày không? | Bitmap/bit operations trên String |

Những ràng buộc cần ghi trước khi thiết kế:

1. **Phép truy cập quan trọng nhất:** lấy cả object, lấy một field, kiểm tra tồn tại, lấy top N, thêm/nhận message hay tìm theo khoảng cách.
2. **Cardinality:** có khoảng bao nhiêu key, bao nhiêu phần tử trong mỗi key, kích thước một phần tử là bao nhiêu.
3. **Độ biến động:** một giây có bao nhiêu lần ghi, có nhiều client sửa cùng khóa không.
4. **TTL:** cả nhóm dữ liệu hết hạn cùng lúc hay từng phần tử cần TTL riêng.
5. **Thứ tự:** cần FIFO, thứ tự theo score, hay không quan tâm thứ tự.
6. **Trùng lặp:** có được thêm cùng phần tử nhiều lần không.
7. **Độ bền và khôi phục:** dữ liệu mất có tái tạo được không; có cần ACK/replay.
8. **Redis topology:** standalone, primary/replica hay Cluster; có thao tác nhiều key không.
9. **Nguồn sự thật:** Redis là cache của database, chỉ số tạm, hay chính là nơi sở hữu dữ liệu nghiệp vụ.
10. **Cách kiểm thử và vận hành:** quan sát kích thước, TTL, lỗi, lag và chính sách dọn dữ liệu bằng gì.

Một mẫu ứng dụng có thể đúng với một bộ ràng buộc nhưng sai ngay khi yêu cầu “cần replay khi worker chết” hoặc “từng item có thời gian hết hạn độc lập” được bổ sung.

## 2. Bản đồ nhanh các cấu trúc dữ liệu Redis

| Cấu trúc/lệnh | Dạng dữ liệu | Điểm mạnh | Thường không phù hợp khi |
|---|---|---|---|
| **String** | Byte string, số nguyên dạng chuỗi, JSON đã serialize | `GET`/`SET`, counter, TTL cho từng key, cache nguyên object | Cần cập nhật nhiều field độc lập mà không đọc/ghi cả payload |
| **Hash** | Một key chứa nhiều field → value | Đọc/ghi một field, `HINCRBY`, object thuộc cùng key | Mỗi field cần lifecycle/TTL độc lập trên phiên bản/config chưa hỗ trợ |
| **List** | Dãy phần tử có thứ tự | Push/pop ở hai đầu, hàng đợi đơn giản, danh sách ngắn | Cần ACK/replay, nhiều group độc lập, truy vấn thành viên/sắp xếp |
| **Set** | Tập hợp phần tử không trùng, không sắp thứ tự | Membership, thêm/xóa phần tử, tập giao/hợp | Cần vị trí/hạng hoặc giữ trùng lặp |
| **Sorted Set (ZSet)** | Thành viên duy nhất + score số | Xếp hạng, top N, truy vấn theo score, lịch xử lý theo thời gian | Cần hàng đợi có ACK/Pending Entries List |
| **Stream** | Chuỗi entry có ID tăng theo stream | Event log, consumer group, pending/ACK và replay trong retention | Chỉ cần một counter hoặc một flag |
| **Pub/Sub** | Kênh thông báo thời gian thực, không phải key/value bền vững | Broadcast thông báo tới subscriber đang kết nối | Cần replay/ACK khi subscriber offline |
| **Bitmap / bit operations** | Các bit trên String | Cờ boolean theo chỉ số, đếm bit | ID rời rạc rất lớn làm cấp phát vùng bit không hiệu quả |
| **HyperLogLog** | Cấu trúc xác suất cho cardinality | Ước lượng số phần tử duy nhất với bộ nhớ nhỏ | Cần đếm chính xác hoặc liệt kê các member |
| **GEO** | Chỉ mục tọa độ dựa trên Sorted Set | Tìm thành viên gần vị trí và theo bán kính | Cần phép toán hình học GIS phức tạp ngoài khả năng Redis |
| **Modules tùy chọn** | RedisJSON, RedisBloom, Search... | Nâng cao truy vấn JSON, approximate membership, search | Server không cài module hoặc ứng dụng chỉ cần core Redis |

Redis Strings, Hashes, Lists, Sets, Sorted Sets và Streams là các cấu trúc dữ liệu cốt lõi. Bitmap, HyperLogLog và GEO có các **họ command chuyên biệt** và cơ chế biểu diễn nội bộ; không nên coi tất cả như các Java collection có khả năng giống nhau.

**Không có kiểu dữ liệu tốt nhất cho mọi mẫu.** Chi phí đọc/ghi, memory overhead, cách concurrency và TTL thường quyết định lựa chọn.

## 3. Cây quyết định chọn cấu trúc ban đầu

```text
Cần lưu gì?
   |
   +--> Một giá trị/counter/cache payload
   |       |
   |       +--> GET/SET/counter --------------------> String
   |       |
   |       +--> Sửa riêng field của một object -----> Hash
   |
   +--> Nhiều member cùng một nhóm
   |       |
   |       +--> Chỉ cần biết có thuộc nhóm? --------> Set
   |       |
   |       +--> Cần thứ tự theo score/time? --------> Sorted Set
   |       |
   |       +--> Cần push/pop theo thứ tự? ----------> List
   |
   +--> Luồng sự kiện hoặc tác vụ
   |       |
   |       +--> Có ACK/retry/replay/group? ---------> Stream
   |       |
   |       +--> Chỉ broadcast cho online listener? -> Pub/Sub
   |
   +--> Chỉ số/hình học
           |
           +--> Đếm unique xấp xỉ -----------------> HyperLogLog
           |
           +--> Cờ boolean theo index -------------> Bitmap
           |
           +--> Tìm tọa độ/khoảng cách -------------> GEO
```

Cây quyết định chỉ là **điểm khởi đầu**. Ví dụ một rate limiter có thể dùng String counter cho cửa sổ cố định, Sorted Set cho sliding window, hoặc một thuật toán khác với Lua. Cả ba đều là “rate limiting”, nhưng yêu cầu nghiệp vụ khác nhau sẽ dẫn đến thiết kế khác nhau.

## 4. String: giá trị đơn, counter và cache nguyên object

### 4.1. Dùng String khi nào?

String phù hợp khi mỗi key cần chứa **một giá trị**:

```text
app:feature:checkout       -> ENABLED
product:42:price           -> 950000
rate:login:{user-42}:60s   -> 17
cache:product:v1:42        -> JSON của ProductSnapshot
```

Ví dụ Spring Data Redis:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class StringExamples {
    private final StringRedisTemplate redis;

    public StringExamples(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveFlag(String name, String value) {
        redis.opsForValue().set(
                "feature:" + name,
                value,
                Duration.ofMinutes(10));
    }

    public String getFlag(String name) {
        return redis.opsForValue().get("feature:" + name);
    }

    public Long incrementViewCount(long productId) {
        return redis.opsForValue().increment(
                "product:" + productId + ":views");
    }
}
```

`INCR`/`DECR` là các Redis commands nguyên tử ở cấp một key. Nếu chỉ cần tăng một counter, không nên viết `GET` rồi `SET` giá trị cộng một ở Java, vì hai request cùng đọc giá trị cũ có thể ghi đè lẫn nhau.

### 4.2. Cache JSON trong một String

Một sản phẩm có thể được lưu thành một payload JSON:

```text
key: cache:product:v2:42

value:
{
  "id": 42,
  "name": "Bàn học",
  "price": 950000,
  "sourceVersion": 12
}
```

Ưu điểm: một `GET` lấy toàn bộ DTO, dễ đặt TTL theo entity, dễ thiết kế schema version và hợp với cache-aside.

Đánh đổi: sửa một field thường phải deserialize toàn bộ value, sửa object rồi ghi lại toàn bộ payload. Với nhiều writer đồng thời, chuỗi `GET → sửa Java object → SET` có thể gây **lost update** nếu không có optimistic version/atomic compare-and-set phù hợp.

### 4.3. TTL và SET

`SET key value EX seconds` có thể tạo/cập nhật value với TTL trong một lệnh. Trong Spring:

```java
redis.opsForValue().set(
        "cache:product:v2:42",
        jsonPayload,
        Duration.ofMinutes(5));
```

Cần nhớ: một lệnh `SET` thông thường thay giá trị có thể **xóa TTL cũ** nếu không đặt TTL mới hoặc không dùng tùy chọn bảo toàn TTL phù hợp. Nếu yêu cầu entry luôn hết hạn, đừng vô tình gọi `set(key,value)` không có expiration sau đó.

### 4.4. Dùng String cho khóa tạm và điều kiện tồn tại

Một số trường hợp cần tạo key nếu chưa có:

```java
Boolean acquired = redis.opsForValue()
        .setIfAbsent(
                "locks:job:{42}",
                "request-unique-token",
                Duration.ofSeconds(30));
```

Điều này gần với ý tưởng `SET key value NX EX ...`: một lần ghi có điều kiện và TTL cùng một command, giảm race so với `SETNX` rồi `EXPIRE` ở hai lệnh.

Nhưng **một khóa tạo bằng NX + TTL chưa phải distributed lock hoàn chỉnh**. Bước release phải kiểm tra đúng token chủ sở hữu, ví dụ bằng Lua; còn lease expiry, gia hạn, fencing và thao tác quá hạn phải được thiết kế riêng.

## 5. Hash: object cần cập nhật từng field

Giả sử ứng dụng quản lý một trạng thái phiên có các thuộc tính thay đổi với tần suất khác nhau:

```text
key: session:{abc123} (Hash)

fields:
  userId      -> 42
  lastPage    -> /catalog
  requestCount-> 19
  status      -> ACTIVE
```

Với Redis Hash, có thể đọc/cập nhật riêng field thay vì đọc và ghi lại toàn bộ JSON.

Spring Data Redis:

```java
import java.time.Duration;
import java.util.Map;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SessionHashService {

    private final StringRedisTemplate redis;

    public SessionHashService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveSession(String sessionId, String userId) {
        String key = "session:{" + sessionId + "}";

        redis.opsForHash().putAll(key, Map.of(
                "userId", userId,
                "status", "ACTIVE",
                "requestCount", "0"));

        redis.expire(key, Duration.ofMinutes(30));
    }

    public Long addRequest(String sessionId) {
        return redis.opsForHash()
                .increment(
                        "session:{" + sessionId + "}",
                        "requestCount",
                        1);
    }

    public Object getStatus(String sessionId) {
        return redis.opsForHash()
                .get("session:{" + sessionId + "}", "status");
    }
}
```

`HINCRBY` cập nhật nguyên tử một field số nguyên. Tuy vậy, phương thức `putAll` rồi `expire` ở ví dụ là **hai Redis operations**. Nếu process chết sau khi ghi hash nhưng trước khi đặt TTL, có thể còn key không hết hạn. Khi TTL là bất biến quan trọng, cần gộp các bước bằng Lua/transaction phù hợp hoặc thiết kế một lệnh ghi có TTL khác.

### 5.1. Hash không đồng nghĩa luôn tiết kiệm bộ nhớ hơn String

Redis có thể dùng encoding tối ưu cho Hash nhỏ, nhưng memory overhead thực tế phụ thuộc số field, kích thước value, encoding thresholds và cách Redis cấp phát bộ nhớ. Không có quy tắc tuyệt đối “Hash luôn tốt hơn JSON String”.

Nếu một object thường được đọc nguyên vẹn và ghi nguyên vẹn, một String JSON có thể đơn giản và hiệu quả hơn. Nếu cần cập nhật một field nóng hoặc dùng `HINCRBY`, Hash có ưu thế rõ hơn.

### 5.2. TTL của Hash

Trong mô hình phổ biến, `EXPIRE key` đặt TTL cho **cả Hash**, không phải tự động cho từng field. Các phiên bản Redis mới có thể có **field expiration commands** cho Hash với điều kiện Redis version và client/API hỗ trợ; không được giả định mọi Spring Data Redis deployment đều có cùng khả năng.

Nếu mỗi field cần TTL độc lập và hỗ trợ chưa được xác nhận, có thể phải dùng các key riêng cho từng phần tử hoặc mô hình Sorted Set theo expiration time. Chọn Hash chỉ vì object có nhiều field sẽ gây khó vận hành nếu từng field phải hết hạn độc lập.

## 6. Chọn String JSON hay Hash cho một entity?

| Câu hỏi | String JSON | Redis Hash |
|---|---|---|
| Thường đọc toàn bộ object? | Tự nhiên, một `GET` | `HGETALL` hoặc nhiều `HMGET` |
| Thường cập nhật một field nhỏ? | Phải ghi lại payload hoặc có công cụ JSON riêng | `HSET`, `HINCRBY` |
| Mỗi entity cần một TTL? | `SET` kèm TTL thuận tiện | `EXPIRE` cho key Hash |
| Có schema JSON/phức tạp/nested object? | Dễ giữ DTO cùng schema | Phải flatten hoặc serialize nested field |
| Cần atomic increment một field? | Có thể dùng key counter riêng, không trực tiếp INCR trên JSON | `HINCRBY` |
| Cần Spring Redis Repository? | Phải tự mapping nếu dùng String | Repository thường mapping aggregate vào Redis Hash và các key phụ |
| Chi phí bộ nhớ? | Phụ thuộc payload và serializer | Phụ thuộc số field và Redis encoding; cần đo |
| Cần truy vấn theo thuộc tính bất kỳ? | Không có index tự động từ String | Hash cũng không tự có secondary index |

**Không nên nhầm Redis Hash với một bảng SQL có thể query mọi cột.** Muốn tìm tất cả phiên có `status=ACTIVE`, việc lưu `status` trong Hash không tự tạo một index hỗ trợ truy vấn đó.

Nếu dùng **Spring Data Redis Repositories**, framework có thể ánh xạ entity thành Hash và quản lý một số cấu trúc metadata/index khác theo annotation và cấu hình. Khi viết trực tiếp bằng RedisTemplate ngoài Repository, cần hiểu việc cập nhật Hash có thể không cập nhật những secondary index do Repository quản lý.

## 7. Set: tập thành viên không trùng và kiểm tra membership

Một wishlist có thể được biểu diễn:

```text
key: wishlist:{user-42} (Set)
members:
  product-100
  product-205
  product-901
```

Các thao tác cần là “thêm sản phẩm”, “xóa sản phẩm”, “sản phẩm này có trong wishlist không?”. Redis Set phù hợp hơn List vì một member không được lưu thành nhiều phần tử trùng trong cùng Set.

Ví dụ:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;

public class WishlistService {

    private final StringRedisTemplate redis;

    public WishlistService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long add(String userId, String productId) {
        return redis.opsForSet().add(
                "wishlist:{" + userId + "}",
                productId);
    }

    public Boolean contains(String userId, String productId) {
        return redis.opsForSet().isMember(
                "wishlist:{" + userId + "}",
                productId);
    }

    public Long remove(String userId, String productId) {
        return redis.opsForSet().remove(
                "wishlist:{" + userId + "}",
                productId);
    }

    public Set<String> members(String userId) {
        return redis.opsForSet().members(
                "wishlist:{" + userId + "}");
    }
}
```

`SADD` và `SISMEMBER` phù hợp khi không cần thứ tự. Lệnh `SADD` trả số member mới được thêm, vì vậy có thể dùng để nhận biết một member đã tồn tại ở mức tập hợp.

### 7.1. Dùng Set cho deduplication

Ví dụ nhóm event ID đã xử lý:

```text
processed-events:{consumer-A} (Set)
  event-101
  event-102
  event-103
```

Gọi `SADD` cùng event ID lần thứ hai không làm Set có hai bản sao. Tuy nhiên, “SADD thành công rồi xử lý nghiệp vụ” **không bảo đảm exactly-once** nếu ứng dụng chết giữa bước đánh dấu và bước ghi database.

Khi cần đồng bộ dedup state với tác động nghiệp vụ ở một database khác, cần transaction ở nguồn chuẩn, unique constraint/idempotency hoặc outbox. Redis Set chỉ cung cấp membership nguyên tử trong Redis.

### 7.2. Giới hạn của Set

- Không có thứ tự business rõ ràng; đừng dựa vào thứ tự `SMEMBERS`.
- Nếu cần top N theo score, dùng Sorted Set.
- Nếu cần TTL cho từng thành viên, `EXPIRE` trên Set key không giải quyết độc lập từng member.
- `SMEMBERS` trả toàn bộ tập, có thể rất nặng khi cardinality lớn; cân nhắc `SSCAN` và giới hạn trang.
- Khi dữ liệu lớn, theo dõi `SCARD`, memory và chính sách expiration/cleanup.

## 8. Sorted Set: score, thứ hạng và lập lịch theo thời gian

Redis Sorted Set (ZSet) gắn mỗi member duy nhất với một **score** số. Redis duy trì thứ tự theo score, hỗ trợ truy vấn top N, khoảng score hoặc thứ hạng.

Ví dụ bảng xếp hạng:

```text
leaderboard:weekly:{game-1} (ZSet)

alice -> score 1250
bob   -> score 990
cara  -> score 1800
```

Ứng dụng cần cập nhật điểm và lấy top đầu:

```java
import java.util.Set;
import org.springframework.data.redis.core.StringRedisTemplate;

public class LeaderboardService {

    private final StringRedisTemplate redis;

    public LeaderboardService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Double addScore(String gameId, String playerId, double delta) {
        return redis.opsForZSet().incrementScore(
                "leaderboard:weekly:{" + gameId + "}",
                playerId,
                delta);
    }

    public Set<String> topPlayers(String gameId, long count) {
        if (count <= 0) {
            return Set.of();
        }

        return redis.opsForZSet().reverseRange(
                "leaderboard:weekly:{" + gameId + "}",
                0,
                count - 1);
    }

    public Long rankFromTop(String gameId, String playerId) {
        return redis.opsForZSet().reverseRank(
                "leaderboard:weekly:{" + gameId + "}",
                playerId);
    }
}
```

`ZINCRBY` tăng score nguyên tử ở cấp một ZSet key/member. `reverseRank` trả vị trí **từ 0**, không phải số hạng bắt đầu từ 1 khi hiển thị cho người dùng. Nếu `reverseRank` trả `null`, member chưa nằm trong ZSet.

### 8.1. Trường hợp bằng điểm

Khi nhiều member có cùng score, Redis áp dụng quy tắc sắp xếp bổ sung theo member. Không giả định thứ tự cùng điểm tự phản ánh thời điểm thi đấu hoặc thứ tự đăng ký. Nếu bài toán cần tie-break cụ thể, thiết kế score kết hợp hoặc dữ liệu bổ sung phải có quy tắc chính xác, tránh encoding gây mất độ chính xác.

### 8.2. Sorted Set cho delayed jobs

Có thể lưu thời điểm “được phép chạy” dưới dạng score:

```text
delayed-jobs (ZSet)

job-A -> 1760000100000
job-B -> 1760000200000
job-C -> 1760000300000
```

Worker truy vấn các job có score nhỏ hơn hoặc bằng thời gian hiện tại. Tuy nhiên, bước “đọc job đã đến hạn” rồi “xóa khỏi ZSet” nếu tách thành hai lệnh có thể khiến nhiều worker cùng nhận một job.

Khi cần **claim nguyên tử**, dùng Lua hoặc một Redis command phù hợp để lấy/xóa một cách có kiểm soát. Sau khi claim, còn cần chính sách retry nếu worker chết giữa lúc thực hiện tác vụ. Nếu yêu cầu chính là **message delivery có ACK**, nên cân nhắc Redis Streams thay vì tự xây toàn bộ PEL và recovery quanh ZSet.

### 8.3. Các giới hạn đáng nhớ

- Score dùng biểu diễn số; cần thận trọng với timestamp quá lớn hoặc nhu cầu so sánh chính xác.
- TTL thường áp dụng cho toàn ZSet key; từng member không tự hết hạn theo score.
- ZSet có overhead cho index/thứ tự; không dùng khi chỉ cần membership.
- ZSet cho phép lấy range theo score/rank hiệu quả hơn tải hết dữ liệu về Java rồi sắp xếp.
- Một key có hàng triệu member có thể trở thành **hot key** hoặc gây tải đáng kể khi truy vấn rộng.

## 9. List: thứ tự push/pop, nhưng không phải queue có ACK

Redis List có thứ tự phần tử và các lệnh thêm/xóa ở hai đầu. Ví dụ một hàng đợi đơn giản:

```text
jobs:thumbnail (List)

producer: LPUSH job-id
consumer: RPOP job-id
```

Spring:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SimpleJobQueue {

    private final StringRedisTemplate redis;

    public SimpleJobQueue(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long submit(String jobId) {
        return redis.opsForList()
                .leftPush("jobs:thumbnail", jobId);
    }

    public String take() {
        return redis.opsForList()
                .rightPop("jobs:thumbnail", Duration.ofSeconds(2));
    }
}
```

`LPUSH` + `RPOP` tạo luồng FIFO nếu chỉ push một phía và pop phía đối diện theo quy ước. Lệnh blocking pop có thể chờ tới timeout thay vì polling liên tục.

**Vấn đề mất message:** khi consumer `RPOP`, phần tử đã bị lấy khỏi List. Nếu consumer chết ngay sau đó, job không còn trong queue và không có Pending Entries List do Redis quản lý.

### 9.1. Reliable queue bằng List có thể xây dựng, nhưng tốn công

Một mô hình truyền thống dùng danh sách “ready” và “processing”:

```text
ready-list
    |
    | atomically move
    v
processing-list
    |
    +--> worker thành công -> remove khỏi processing
    |
    +--> worker chết -> watchdog phát hiện và đưa về ready
```

Redis có các lệnh như `LMOVE`/`BLMOVE` để di chuyển giữa List theo hướng được chỉ định. Dù vậy, bạn vẫn cần thiết kế ownership, timeout, retry, idempotency và khả năng phục hồi. Khi hệ thống cần consumer group, replay và pending recovery, **Stream** thường giảm lượng giao thức tự viết.

List vẫn hợp lý với stack/queue ngắn, job best-effort hoặc khi application đã có cơ chế độ bền ở nơi khác.

## 10. Stream: sự kiện có ID, consumer group và pending recovery

Redis Stream lưu entry có ID theo thứ tự:

```text
stream: orders:events

1730000000000-0 -> {type: OrderCreated, orderId: 42}
1730000000100-0 -> {type: OrderPaid, orderId: 42}
1730000000200-0 -> {type: OrderShipped, orderId: 42}
```

Các khả năng thường khiến Stream phù hợp:

- Producer ghi event bằng `XADD`.
- Consumer đọc `XREAD` hoặc `XREADGROUP`.
- Nhiều consumer trong một group chia nhau các entry mới.
- Redis duy trì Pending Entries List (PEL) cho message đã giao nhưng chưa `XACK`.
- Recovery có thể sử dụng `XPENDING`, `XCLAIM` hoặc `XAUTOCLAIM`.
- Các group độc lập có thể đọc cùng stream theo offset riêng.
- Entry có thể được giữ lại để replay trong phạm vi retention đã thiết kế.

### 10.1. Ghi vào Stream qua Spring Data Redis

Ví dụ producer gửi một MapRecord:

```java
import java.util.Map;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId publish(String orderId, String eventType) {
        MapRecord<String, String, String> record =
                MapRecord.create(
                        "orders:events",
                        Map.of(
                                "orderId", orderId,
                                "eventType", eventType));

        return redis.opsForStream().add(record);
    }
}
```

`RecordId` là ID vị trí trong stream, khác với `orderId` trong payload.

Đọc bằng Spring Data Redis có thể sử dụng `StreamOperations` hoặc `StreamMessageListenerContainer` khi cần worker nền. Consumer group phải được khởi tạo đúng offset và cần chính sách ACK/recovery riêng.

### 10.2. Stream không tự bảo đảm exactly-once

Một consumer có thể ghi database thành công rồi chết **trước khi `XACK`**. Message còn pending, worker khác reclaim và xử lý lại. Vì vậy cần idempotency theo event ID hoặc business operation ID.

`XACK` xóa trạng thái pending của group, **không tự xóa entry vật lý khỏi stream**. Cần retention/trim theo dung lượng và nhu cầu replay của các group.

### 10.3. List hay Stream?

| Nhu cầu | List | Stream |
|---|---|---|
| Push/pop đơn giản | Tốt | Có thể nhưng nhiều cơ chế hơn |
| FIFO một queue | Tốt nếu theo quy ước hai đầu | Đọc theo stream ID |
| ACK sau xử lý | Phải xây thêm | Consumer group/PEL hỗ trợ |
| Retry sau consumer crash | Phải tự quản lý | Có cơ chế claim pending |
| Nhiều group độc lập nhận mỗi event | Không có sẵn tương tự | Có |
| Replay lịch sử | Tự thiết kế lưu giữ | Có trong retention |
| Dung lượng và trim | Quản lý length/list | Quản lý stream retention |
| Exactly-once business | Không | Không; cần idempotency |

Nếu tác vụ cần “chỉ giao cho worker đang chạy và có thể mất khi worker chết”, List đơn giản có thể đủ. Nếu yêu cầu không bỏ mất job, retry và quan sát backlog, hãy đánh giá Stream ngay từ bước chọn cấu trúc.

## 11. Pub/Sub: broadcast tức thời khác với Stream

Redis Pub/Sub không phải một key lưu lịch sử message. Producer `PUBLISH` vào channel, những subscriber đang kết nối và đăng ký channel tại thời điểm đó có thể nhận thông báo.

```text
PUBLISH channel "inventory-updated"

        |
        +--> subscriber đang online A
        +--> subscriber đang online B
        +--> subscriber đang online C

Subscriber offline không có queue riêng để replay.
```

Pub/Sub phù hợp với thông báo ephemeral, ví dụ “có thể cần làm mới trạng thái hiển thị” mà hệ thống có cơ chế đọc lại nguồn khi thiếu thông báo.

Không dùng Pub/Sub một mình cho yêu cầu:

- message phải được xử lý ngay cả khi subscriber offline;
- có ACK/consumer group/retry;
- cần replay event để phục hồi state;
- đảm bảo không bỏ sót một lệnh nghiệp vụ quan trọng.

Trong Spring Data Redis, `RedisMessageListenerContainer` thường được sử dụng cho Pub/Sub imperative, còn `StreamMessageListenerContainer` là thành phần khác dành cho Streams. Hai API có tên gần nhau nhưng **delivery semantics khác nhau**.

## 12. Bitmap: cờ boolean theo offset và giới hạn kích thước

Bitmap trong Redis dựa trên các thao tác bit của String. Ví dụ biết trước user ID là số nguyên liên tục từ 0 đến một giới hạn phù hợp và cần ghi nhận “user đã check-in hôm nay chưa”:

```text
attendance:2026-11-13 (bitmap)

offset 42 -> 1
offset 43 -> 0
offset 44 -> 1
```

Spring Data Redis:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

public class AttendanceBitmap {

    private final StringRedisTemplate redis;

    public AttendanceBitmap(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Boolean markPresent(long userIndex) {
        return redis.opsForValue().setBit(
                "attendance:today",
                userIndex,
                true);
    }

    public Boolean isPresent(long userIndex) {
        return redis.opsForValue().getBit(
                "attendance:today",
                userIndex);
    }
}
```

`SETBIT`/`GETBIT` theo offset cho phép biểu diễn cờ theo bit. Nhưng nếu ID cực kỳ thưa, ví dụ một user có ID vài tỷ, việc ghi vào offset rất lớn có thể buộc Redis tạo String đủ dài để bao phủ offset đó. Bộ nhớ khi ấy có thể lãng phí nghiêm trọng.

Bitmap không tự cung cấp TTL cho mỗi bit; TTL áp dụng cho cả key ngày/nhóm. Phải thống nhất cách ánh xạ ID → offset và đặt key theo partition/time window phù hợp.

## 13. HyperLogLog: đếm distinct xấp xỉ

Một trang web cần ước lượng số khách truy cập duy nhất mỗi ngày, nhưng không nhất thiết cần biết chính xác từng user ID.

Redis HyperLogLog hỗ trợ:

```text
PFADD daily:unique:2026-11-13 user-42 user-43 ...
PFCOUNT daily:unique:2026-11-13
```

Spring Data Redis:

```java
import org.springframework.data.redis.core.StringRedisTemplate;

public class UniqueVisitorEstimator {

    private final StringRedisTemplate redis;

    public UniqueVisitorEstimator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long addVisitor(String day, String userId) {
        return redis.opsForHyperLogLog()
                .add("visitors:unique:" + day, userId);
    }

    public Long estimate(String day) {
        return redis.opsForHyperLogLog()
                .size("visitors:unique:" + day);
    }
}
```

HyperLogLog tiết kiệm bộ nhớ cho ước lượng cardinality với sai số thống kê; nó **không cho phép liệt kê danh sách user thực tế** và không phù hợp nếu kết quả phải chính xác tuyệt đối.

Nếu cần biết “user-42 đã ghé thăm chưa?”, `Set` thích hợp hơn vì nó lưu membership. Nếu chỉ cần biểu đồ số unique visitors với độ chính xác xấp xỉ, HyperLogLog có thể phù hợp hơn nhiều Set rất lớn.

Trong phân tích sản phẩm, cần nói rõ số liệu là **ước lượng**, không ghi nhãn như số đếm chính xác cho thanh toán hoặc tính quyền lợi.

## 14. GEO: lưu vị trí và truy vấn theo khoảng cách

Redis hỗ trợ các Geo commands để đưa thành viên có tọa độ kinh độ/vĩ độ vào một key và truy vấn thành viên gần một điểm.

Ví dụ:

```text
geo:stores

store-42 -> (longitude, latitude)
store-77 -> (longitude, latitude)
```

Spring Data Redis cung cấp `GeoOperations`:

```java
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.StringRedisTemplate;

public class StoreLocationService {

    private final StringRedisTemplate redis;

    public StoreLocationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long addStore(String storeId, double lon, double lat) {
        return redis.opsForGeo()
                .add("geo:stores", new Point(lon, lat), storeId);
    }
}
```

Cần nhớ `Point` trong ví dụ dùng **longitude trước, latitude sau**. Đảo thứ tự tọa độ có thể đưa cửa hàng đến vị trí sai hoặc tạo lỗi dữ liệu.

Redis GEO được xây dựng trên cơ chế Sorted Set trong Redis và hỗ trợ truy vấn địa lý phổ biến; nó không phải một hệ thống GIS tổng quát có đầy đủ phép toán polygon, network road distance hay địa chỉ hóa. Nếu nghiệp vụ cần bản đồ đường đi và thời gian lái xe, cần một hệ thống định tuyến khác.

Một Geo key chứa nhiều thành viên cũng không tự đặt TTL riêng cho từng cửa hàng; phải quản lý lifetime của member và thời điểm cập nhật vị trí.

## 15. Các Redis modules chuyên dụng không có sẵn trên mọi server

Đôi khi yêu cầu vượt core Redis:

- **RedisJSON:** thao tác cấu trúc JSON bằng các command/đường dẫn mà server có module tương ứng hỗ trợ;
- **RedisBloom:** một số cấu trúc membership xác suất khi chấp nhận false positives;
- **RediSearch/Search:** hỗ trợ kiểu truy vấn/search phù hợp với module và schema.

Không nên viết một ví dụ rồi giả định mọi Redis OSS/managed Redis đều có những command này. Cần kiểm tra module/server edition/version và các client operations tương ứng. `RedisTemplate` thường không tự biến String JSON thành một RedisJSON document có khả năng query toàn cấu trúc.

**Quy tắc lựa chọn:** chỉ phụ thuộc vào module khi yêu cầu truy vấn thực sự cần và deployment có khả năng vận hành nó; đối với cache nguyên object đơn giản, String JSON thường đã đủ.

## 16. Chọn cấu trúc theo một số mẫu ứng dụng phổ biến

| Mẫu ứng dụng | Cấu trúc xuất phát | Lý do | Khi cần đổi thiết kế |
|---|---|---|---|
| Cache object | String JSON | Một lần GET/SET, TTL theo entity | Sửa field nóng, cân nhắc Hash |
| Cache vài thuộc tính phiên | Hash | HGET/HSET/HINCRBY theo field | Mỗi field TTL riêng, cân nhắc key độc lập |
| Đếm lượt xem | String counter | INCR nguyên tử | Muốn phân tích theo thời gian, partition counter |
| Danh sách theo dõi | Set | Không trùng, membership | Cần thứ tự, dùng ZSet |
| Leaderboard | ZSet | Score/rank/top N | Cần snapshot nhiều bảng, có thể thêm lưu trữ khác |
| Hàng đợi đơn giản | List | Push/pop hai đầu | Cần ACK/replay, cân nhắc Stream |
| Event pipeline | Stream | ID, group, ACK, PEL | Chỉ broadcast ephemeral, cân nhắc Pub/Sub |
| Dedup membership | Set | SADD/SISMEMBER | Kích thước quá lớn và chấp nhận false positive, xem module |
| Lịch xử lý theo timestamp | ZSet | Query/claim theo score | Cần delivery ACK/recovery, kết hợp Stream |
| Cờ boolean theo index | Bitmap | Bộ nhớ bit khi offset phù hợp | ID thưa, Set có thể tốt hơn |
| Unique count ước lượng | HyperLogLog | Bộ nhớ nhỏ | Cần exact, dùng Set hoặc nguồn thống kê khác |
| Tìm cửa hàng gần nhất | GEO | Tìm theo tọa độ | Cần route/đường đi, tích hợp GIS |
| Cache invalidation broadcast | Pub/Sub | Fan-out tới listener đang online | Cần không mất message, chuyển Stream/broker bền vững |

Bảng này không thay thế khảo sát workload thực. Một mẫu có thể cần **hơn một cấu trúc**: ví dụ hệ thống xếp hạng dùng ZSet cho top N và Hash/String cho hồ sơ người chơi.

## 17. Đặt tên key theo ý nghĩa và vòng đời

Key naming là một phần của thiết kế cấu trúc, không chỉ là một quy ước thẩm mỹ.

Ví dụ:

```text
cache:product:v2:42
counter:product:42:views
wishlist:{user-42}
leaderboard:weekly:{game-1}
orders:events
rate:login:{user-42}:20261113T0300
attendance:2026-11-13
visitors:unique:2026-11-13
```

Một cách đặt key hữu ích thường chứa:

1. **Namespace:** cache, counter, wishlist, jobs...
2. **Domain/entity:** product, user, game...
3. **Schema/version** khi payload thay đổi định dạng.
4. **ID/time bucket** khi cần cô lập TTL và truy vấn.
5. **Hash tag** nếu lệnh nhiều key cần cùng slot trong Redis Cluster.

Không ghi token bí mật, mật khẩu hoặc dữ liệu cá nhân nhạy cảm trực tiếp vào key name: key có thể xuất hiện trong log, metric, command trace hoặc Redis inspection.

### Key quá dài hay quá ngắn?

Key quá dài lặp lại ở hàng triệu entry làm tăng overhead; key quá ngắn khó bảo trì và dễ đụng tên. Chọn quy ước đủ rõ để chẩn đoán và đủ gọn khi cardinality lớn.

### Không trộn Redis data types trên cùng một key

Nếu key `user:42` đang là Hash, không thể tùy ý dùng `GET user:42` như String. Redis trả lỗi `WRONGTYPE`. Vì vậy namespace nên thể hiện mục đích và type hợp lý; tránh hai service cùng ghi một key theo hai schema khác nhau.

## 18. TTL: chọn theo đơn vị sống của dữ liệu

Đây là một trong các yếu tố quyết định **chọn key hay member/field**.

| Đơn vị cần hết hạn | Mô hình dễ hiểu | Điểm lưu ý |
|---|---|---|
| Một object cache | Mỗi entity một String key | `SET` kèm TTL |
| Một session nhiều field hết hạn cùng lúc | Một Hash key | `EXPIRE` trên cả key |
| Một membership cụ thể hết hạn độc lập | Key riêng hoặc mô hình deadline | Set member không tự có TTL truyền thống |
| Một leaderboard theo tuần | ZSet theo tuần | TTL cho cả tuần/partition |
| Các job đến hạn ở thời điểm khác nhau | ZSet score bằng deadline | Score không tự xóa member khi đến hạn |
| Event log có retention | Stream với trim policy | TTL cho cả stream key khác với xóa entry theo retention |
| Visitor count mỗi ngày | HyperLogLog key theo ngày | TTL theo partition ngày |

**Score bằng thời gian không phải TTL.** Ví dụ `ZADD jobs:delayed 1760000100000 job-A` không khiến Redis tự xóa hoặc thực thi job-A vào timestamp đó. Worker phải chủ động truy vấn và xử lý.

Tương tự, `XACK` một stream entry không tự xóa entry khỏi stream. Redis key expiration cũng không bảo đảm event được xử lý ngay tại thời điểm hết hạn.

### Tránh key sống mãi ngoài ý muốn

Ví dụ một pipeline:

```java
redis.opsForHash().putAll(key, fields);
redis.expire(key, Duration.ofMinutes(30));
```

Có cửa sổ lỗi giữa hai command. Nếu process ngừng trước `EXPIRE`, key có thể không được đặt TTL. Với các bất biến TTL quan trọng, xem xét nhóm thao tác nguyên tử hợp lệ hoặc một cách tạo key khác.

## 19. Tính nguyên tử: chọn cấu trúc để tránh race condition

Redis command đơn thường thực thi nguyên tử ở cấp command, nhưng chuỗi nhiều command từ Java **không tự được gom thành một đơn vị nguyên tử**.

Ví dụ thao tác sai khi giới hạn số lượt truy cập:

```java
String oldValue = redis.opsForValue().get(key);
long next = Long.parseLong(oldValue) + 1;

if (next <= limit) {
    redis.opsForValue().set(key, Long.toString(next));
}
```

Hai request có thể đọc cùng `oldValue` rồi ghi đè hoặc cả hai cùng vượt qua điều kiện. Chọn String counter phù hợp mới chỉ là bước đầu: phải dùng một lệnh atomic hoặc Lua cho **kiểm tra + tăng**.

### Ví dụ Lua: counter trong fixed window

```lua
-- KEYS[1] = counter key đã bao gồm bucket thời gian
-- ARGV[1] = TTL tính bằng mili giây
-- ARGV[2] = giới hạn cho cửa sổ

local ttl = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])

if not ttl or ttl <= 0 or not limit or limit <= 0 then
    return -1
end

local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current >= limit then
    return 0
end

local next = redis.call('INCR', KEYS[1])

if next == 1 then
    redis.call('PEXPIRE', KEYS[1], ttl)
end

return 1
```

Script này thực hiện **kiểm tra và tăng** trong một lần thực thi Redis, tránh race giữa request cạnh tranh cùng key. Ứng dụng Spring Data Redis có thể khai báo Lua bằng `DefaultRedisScript<Long>` và gọi `RedisTemplate.execute(script, keys, args...)`.

Giới hạn cần hiểu:

- Đây là **fixed-window limiter**, chưa phải sliding window hay token bucket.
- Tên key phải chứa **bucket thời gian** đúng quy tắc, không phải một key duy nhất chạy mãi.
- Một counter tồn tại bất thường không có TTL từ ngoài luồng không tự được script sửa nếu `next != 1`.
- Một script nguyên tử trên Redis không tạo giao dịch nguyên tử với database khác.
- Timeout sau khi script có thể đã chạy khiến retry có nguy cơ làm tăng counter lần nữa; cần hợp đồng retry phù hợp.
- Lua không hoàn tác tự động những lệnh đã chạy khi script lỗi runtime ở bước sau.

### Khi nào dùng MULTI/EXEC, Lua hay một lệnh đơn?

| Nhu cầu | Hướng tiếp cận |
|---|---|
| Một counter tăng | `INCR`/`HINCRBY` đơn |
| Tạo khóa khi chưa có và gắn TTL | `SET NX EX` hoặc API tương ứng |
| Kiểm tra + cập nhật có điều kiện | Lua khi các key ở phạm vi hợp lệ |
| Nhóm các lệnh Redis theo transaction | `MULTI`/`EXEC` với hiểu biết về lỗi và kết quả |
| Ghi SQL và Redis cùng nguyên tử | Không được bảo đảm chỉ nhờ Redis transaction/Lua |
| Message xử lý lại sau lỗi | Stream + ACK + idempotency/outbox tùy nguồn chuẩn |

Chọn đúng cấu trúc là cần thiết, nhưng cũng phải chọn **đơn vị nguyên tử** phù hợp với thao tác nghiệp vụ.

## 20. Redis Cluster: chọn key layout để không gặp CROSSSLOT

Trong Redis Cluster, khóa được ánh xạ vào **16.384 hash slots**. Một số command nhiều key và Lua script yêu cầu những key liên quan nằm trong cùng slot.

Ví dụ:

```text
cart:{user-42}:items
cart:{user-42}:total
```

Hai key cùng hash tag `{user-42}` nên cùng slot, thuận lợi cho thao tác nhiều key hợp lệ.

Trái lại:

```text
cart:user-42:items
cart:user-43:items
```

không có bảo đảm cùng slot. Một lệnh cần thao tác nguyên tử lên cả hai có thể báo `CROSSSLOT`.

Cần hiểu:

- Hash tag là **quy tắc định tuyến**, không phải index nghiệp vụ.
- Một Lua script thao tác nhiều key không tự phân tán nguyên tử qua nhiều primary.
- Redis Cluster không có một `SCAN` toàn cluster chỉ từ một primary.
- Tập trung quá nhiều key nóng cùng hash tag có thể tạo **hot slot**.
- Lựa chọn data structure cũng tác động phân phối: một ZSet khổng lồ chứa toàn bộ hệ thống luôn là **một Redis key** thuộc một slot, không tự phân tán member qua các primary.

Nếu bảng xếp hạng toàn cầu có một ZSet quá nóng, có thể cần chiến lược sharding theo mùa/nhóm hoặc một tầng tổng hợp top N, nhưng đổi kiến trúc có thể làm việc tính thứ hạng toàn cục phức tạp hơn. Không chia key tùy ý rồi giả định top N của từng shard có thể kết hợp chính xác với mọi yêu cầu rank.

## 21. Mẫu cache của Spring khác dữ liệu của Redis Repository

Spring Data Redis có nhiều tầng API:

| Tầng API | Dữ liệu thường gặp | Điều cần nhớ |
|---|---|---|
| `StringRedisTemplate` | String, Hash, Set, List, ZSet, Stream với serializer chuỗi | Người viết code chủ động thiết kế key/type |
| `RedisTemplate<K,V>` | Dữ liệu theo serializers được cấu hình | Key/value byte format quyết định khả năng tương tác |
| `ReactiveRedisTemplate<K,V>` | Redis reactive operations trả Mono/Flux | Không tự thay đổi Redis data structures |
| Spring Cache + `RedisCacheManager` | Cache entries theo cache name/key serializer | Thường cache payload như một value; TTL theo entry |
| Redis Repository | Aggregate thường ánh xạ vào Redis Hash cùng metadata/index keys | Không được bỏ qua index/keyspace lifecycle khi ghi ngoài Repository |
| `StreamMessageListenerContainer` | Redis Stream entries và consumer group | Nhận message không tự giải quyết ACK/replay/idempotency |

Đừng thấy “Repository entity là một object” rồi nghĩ tương đương việc tự `SET key JSON`. Redis Repository có thể quản lý keyspace, TTL, secondary index và mapping theo cơ chế riêng. Trộn direct template write với Repository mà không cập nhật metadata/index có thể tạo inconsistency.

Tương tự, cấu hình `RedisCacheManager` không tự động biến các key cache thành Hash hoặc Sorted Set chỉ vì DTO Java có các field kiểu tương ứng.

## 22. Serializer, schema và vòng đời dữ liệu

Redis lưu bytes; Spring Data Redis thực hiện mapping giữa Java object và Redis commands. Một quyết định cấu trúc tốt có thể thất bại nếu serializer không tương thích.

Ví dụ:

```text
SET product:42:name Desk
```

được tạo bằng Redis CLI có key string. Nếu `RedisTemplate<Object,Object>` dùng JDK serializer cho key, Java `get("product:42:name")` có thể gửi byte key khác và không đọc được giá trị mong muốn.

Các quy tắc:

1. Với key/field/value chuỗi, `StringRedisTemplate` giúp wire format dễ hiểu.
2. Nếu lưu JSON DTO, đặt serializer và schema version rõ ràng.
3. Khi đổi serializer, các key cũ không tự chuyển format; cần migration, TTL hoặc namespace mới.
4. Đừng ghi một Hash bằng client dùng string fields rồi đọc bằng template dùng field serializer khác.
5. Trước khi đổi kiểu Redis key, xem client khác đang sử dụng key đó theo contract nào.
6. Các command `TYPE`, `TTL`, `MEMORY USAGE` và `SCAN` trong môi trường phù hợp giúp quan sát mà không cần đoán Java type.

Đừng log raw payload nhạy cảm để debug serializer. Ưu tiên metadata, kiểu key và ID đã được làm mờ.

## 23. Chi phí bộ nhớ và độ phức tạp vận hành

Không chỉ so sánh “String hay Hash nhanh hơn”. Để chọn đúng, nên ước lượng:

- Số Redis keys cần tạo.
- Số member/field trong mỗi key.
- Kích thước byte của key, field, value và metadata.
- Tốc độ ghi, tốc độ đọc, peak concurrency.
- Có tải tất cả member bằng một lệnh không.
- Redis eviction policy và giới hạn memory.
- Phần dữ liệu nào phải có TTL hoặc retention.
- Khi một key rất lớn, có tạo áp lực CPU/latency khi quét hoặc cập nhật không.
- Nếu Redis Cluster, các key có được phân tán đều theo slot hay dồn hotspot.

Ví dụ quyết định:

```text
10 triệu sản phẩm
  - Mỗi product cache thành một String JSON có TTL 5 phút:
      dễ đọc toàn object và hết hạn theo entity;
      nhiều keys, payload có thể trùng field names trong JSON.

  - Một Hash khổng lồ chứa toàn bộ product ID -> JSON:
      ít top-level keys hơn nhưng tập trung tải vào một slot,
      khó TTL riêng từng product, khó scale trong Cluster.

  - Mỗi product một Hash:
      cập nhật field thuận tiện, có TTL theo entity,
      số Redis keys vẫn lớn và field overhead cần đo.
```

Không có kết luận tuyệt đối trước khi đo trên workload và payload thực. Redis có các encoding tối ưu tùy kích thước cấu trúc; sự thay đổi encoding có thể ảnh hưởng memory/latency. Chọn dựa trên **access pattern + khả năng vận hành**, không chỉ kích thước trông thấy trong một ví dụ nhỏ.

### Tránh lệnh lấy toàn bộ tập lớn

| Không nên lạm dụng | Vì sao | Hướng khác |
|---|---|---|
| `KEYS *` trên production | Quét keyspace gây tác động lớn | `SCAN` có giới hạn theo node |
| `SMEMBERS` với Set rất lớn | Trả toàn bộ member vào memory ứng dụng | `SSCAN` hoặc phân trang theo thiết kế |
| `HGETALL` với Hash cực lớn | Trả mọi field/value | `HSCAN` hoặc lấy field mục tiêu |
| `LRANGE 0 -1` với List cực lớn | Tải toàn list | Giới hạn range và mô hình queue |
| `ZRANGE 0 -1` với ZSet cực lớn | Tải toàn bảng xếp hạng | Top N hoặc range phù hợp |
| `XRANGE - +` không giới hạn | Tải toàn lịch sử stream | Giới hạn COUNT và retention |

Duyệt theo cursor như `SCAN`/`SSCAN`/`HSCAN`/`ZSCAN` không phải snapshot nguyên tử khi dữ liệu đang thay đổi; kết quả có thể lặp hoặc bị ảnh hưởng bởi cập nhật đồng thời. Cần thiết kế tiêu chí kết thúc và xử lý trùng.

## 24. Ba ví dụ lựa chọn theo yêu cầu thay đổi

### Ví dụ A — Giỏ hàng: từ Set sang Hash

Yêu cầu ban đầu: “Chỉ cần biết user đã chọn những sản phẩm nào”.

```text
cart:{user-42}:products (Set)
  product-100
  product-200
```

Set đáp ứng membership không trùng. Nhưng yêu cầu sau đó: “Mỗi sản phẩm có số lượng 1, 2, 3... và cần thay đổi số lượng nguyên tử”.

Có thể đổi sang Hash:

```text
cart:{user-42}:items (Hash)
  product-100 -> 2
  product-200 -> 5
```

`HINCRBY` có thể tăng/giảm số lượng của từng field. Tuy nhiên, nếu không cho số lượng âm hoặc không được vượt tồn kho, phải thêm logic kiểm tra nguyên tử (Lua/luồng nguồn chuẩn) thay vì chỉ dùng HINCRBY rồi hy vọng hợp lệ.

Nếu cần giữ thứ tự sản phẩm vừa thêm gần nhất, Hash không tự giải quyết; có thể thêm Sorted Set để lưu thời điểm, nhưng việc đồng bộ hai key lại tạo bài toán atomicity và cùng hash slot nếu muốn thao tác gộp.

### Ví dụ B — Hàng đợi email: từ List sang Stream

Yêu cầu ban đầu: “Mỗi worker lấy một email task”.

```text
email:ready (List)
LPUSH -> RPOP
```

List đáp ứng nhanh. Nhưng yêu cầu bổ sung:

- worker chết thì task phải được xử lý lại;
- cần biết pending đã chờ bao lâu;
- có nhiều worker trong một group;
- cần replay event theo ID.

Khi đó Stream thường phù hợp hơn:

```text
email:tasks (Stream)
  XADD
  XREADGROUP
  XACK
  XPENDING / XAUTOCLAIM
```

Vẫn phải có idempotency, retry policy và DLQ. Chỉ đổi cấu trúc không tự bảo đảm email không bị gửi trùng sau khi worker crash.

### Ví dụ C — Bảng xếp hạng: từ List sang Sorted Set

Yêu cầu: “Hiển thị 10 người có điểm cao nhất”.

Nếu dùng List, application phải tải dữ liệu rồi sắp xếp ở Java; nếu điểm đổi thường xuyên, các thao tác trở nên phức tạp.

Dùng ZSet:

```text
leaderboard:weekly:{game-1} (ZSet)

player-1 -> 120
player-2 -> 180
player-3 -> 95
```

Các thao tác `ZINCRBY`, `ZREVRANGE` và `ZREVRANK` đáp ứng tự nhiên. Khi yêu cầu mở rộng sang lưu toàn lịch sử mùa giải và báo cáo sâu, nên cân nhắc database hoặc kho phân tích làm nguồn chuẩn, Redis ZSet là projection phục vụ truy vấn top N.

## 25. Quy trình áp dụng mẫu theo từng bước

Một quy trình giúp tránh chọn cấu trúc chỉ theo thói quen:

1. **Viết ba truy vấn/command quan trọng nhất** của tính năng, theo ngôn ngữ nghiệp vụ.
2. **Xác định nguồn sự thật:** Redis giữ bản chuẩn hay bản cache có thể tái tạo.
3. **Xác định đơn vị dữ liệu:** một object, một member, một event hay một nhóm theo ngày/user.
4. **Chọn cấu trúc phù hợp với phép truy cập chính**, không chỉ format đầu vào Java.
5. **Phân tích race:** thao tác nào cần nhiều lệnh? Có command atomic/Lua/transaction phù hợp không?
6. **Thiết kế TTL/retention:** hết hạn ở cấp key hay member; có cách cleanup không?
7. **Kiểm tra cluster layout:** mọi multi-key operation có cùng slot không; có hot key không?
8. **Chọn serializer và schema version** để writer/reader cùng hiểu bytes.
9. **Xác định chính sách retry/idempotency** khi client timeout hoặc worker được giao lại message.
10. **Đo workload thực tế** và điều chỉnh cấu trúc nếu access pattern thay đổi.

Một mẫu đúng khi giả định “ít dữ liệu, một worker, không replay” có thể không còn đúng khi scale lên hàng triệu member hoặc nhiều ứng dụng cùng cập nhật.

## 26. Bài thực hành: so sánh cấu trúc trên Redis thử nghiệm

Dùng một Redis instance/Cluster **riêng cho lab**, không dùng dữ liệu production.

### Bài 1 — String counter và TTL

```bash
redis-cli SET views:product:42 0 EX 60
redis-cli INCR views:product:42
redis-cli INCR views:product:42
redis-cli GET views:product:42
redis-cli TTL views:product:42
redis-cli TYPE views:product:42
```

Thử gọi `SET views:product:42 10` không kèm TTL rồi quan sát lại TTL. Rút ra kết luận về việc ghi đè String và expiration.

### Bài 2 — Hash so với JSON String

```bash
redis-cli HSET session:lab userId 42 status ACTIVE requestCount 0
redis-cli HINCRBY session:lab requestCount 1
redis-cli HGET session:lab requestCount
redis-cli HGETALL session:lab
redis-cli EXPIRE session:lab 60
redis-cli TTL session:lab
```

Tạo một String JSON tương đương ở key riêng, so sánh số command khi chỉ cập nhật `requestCount`. Nếu dùng `MEMORY USAGE`, hiểu rằng số đo phụ thuộc Redis encoding và kích thước mẫu, không chứng minh một lựa chọn luôn tốt hơn.

### Bài 3 — Set membership và ZSet rank

```bash
redis-cli SADD wishlist:lab p1 p2 p2
redis-cli SCARD wishlist:lab
redis-cli SISMEMBER wishlist:lab p2

redis-cli ZADD leaderboard:lab 10 alice 20 bob 15 cara
redis-cli ZREVRANGE leaderboard:lab 0 2 WITHSCORES
redis-cli ZREVRANK leaderboard:lab bob
redis-cli ZINCRBY leaderboard:lab 5 alice
```

Quan sát Set loại bỏ member trùng, trong khi ZSet lưu mỗi member với một score và có thứ hạng.

### Bài 4 — List queue và mất task khi worker crash

```bash
redis-cli LPUSH jobs:lab job-1 job-2
redis-cli RPOP jobs:lab
redis-cli LRANGE jobs:lab 0 -1
```

Sau `RPOP`, task bị lấy khỏi List. Mô phỏng “worker crash” bằng việc không xử lý task đã nhận; nhận xét vì sao không có PEL và vì sao một reliable queue cần thêm cơ chế.

### Bài 5 — Stream group và ACK

```bash
redis-cli XGROUP CREATE jobs:stream:lab workers 0-0 MKSTREAM
redis-cli XADD jobs:stream:lab '*' type SendEmail id 100
redis-cli XREADGROUP GROUP workers c1 COUNT 1 STREAMS jobs:stream:lab '>'
redis-cli XPENDING jobs:stream:lab workers
```

Ghi lại Redis Stream ID nhận được từ `XADD` hoặc `XREADGROUP` rồi thay vào:

```bash
redis-cli XACK jobs:stream:lab workers <record-id>
redis-cli XPENDING jobs:stream:lab workers
redis-cli XLEN jobs:stream:lab
```

Dòng `<record-id>` chỉ là ký hiệu cần thay bằng ID thực tế. Quan sát ACK xóa pending nhưng `XLEN` vẫn có thể giữ entry.

### Bài 6 — Cluster slot và hash tag

Nếu có cluster lab:

```bash
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:items'
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:total'
```

Hai slot phải khớp. Thử các key không có chung tag và nhận xét vì sao command đa key có thể `CROSSSLOT`.

## 27. Câu hỏi tự đánh giá

**1. Một object thường được đọc toàn bộ, ít sửa riêng field, nên bắt đầu với String hay Hash?**  
Thường bắt đầu với String JSON vì cách đọc/ghi/TTL đơn giản, sau đó đo workload. Nếu thường sửa từng field, Hash có thể phù hợp hơn.

**2. Redis Hash có tự tạo index để query tất cả object có status=ACTIVE không?**  
Không. Hash chỉ tổ chức field/value trong một key. Secondary index cần cơ chế riêng hoặc Repository/index được quản lý thích hợp.

**3. Vì sao wishlist hợp với Set hơn List?**  
Wishlist cần membership không trùng, còn List không tự loại member trùng và không tối ưu cho kiểm tra thành viên.

**4. Vì sao leaderboard hợp với ZSet?**  
Vì cần score, top N và thứ hạng; ZSet hỗ trợ trực tiếp các phép này.

**5. Nếu worker phải ACK/retry khi crash, List hay Stream thường thuận tiện hơn?**  
Stream vì có consumer group, PEL và các lệnh claim/ACK, dù vẫn cần idempotency nghiệp vụ.

**6. Pub/Sub có lưu message cho subscriber offline không?**  
Không. Nó phục vụ subscriber đang kết nối, không có replay/ACK như Streams.

**7. HyperLogLog có thể cho biết user nào đã truy cập không?**  
Không. Nó ước lượng cardinality, không lưu tập member để liệt kê hoặc membership chính xác.

**8. Score của ZSet là timestamp thì job tự chạy đến hạn không?**  
Không. Worker phải lấy và xử lý member đến hạn; score không phải TTL hay scheduler tự động.

**9. Vì sao một ZSet chứa mọi member toàn hệ thống có thể không scale đều trên Redis Cluster?**  
Vì toàn ZSet là một Redis key, thuộc một hash slot/primary, không phân tán từng member tự động.

**10. `@Transactional` cùng một lệnh Redis có tự bảo đảm commit nguyên tử với SQL không?**  
Không. Transaction của database và Redis là hai tài nguyên độc lập; cần thiết kế nhất quán và phục hồi riêng.

**11. Gọi `SMEMBERS` cho Set hàng triệu member có hợp lý không?**  
Thường không khi chỉ cần xử lý từng phần nhỏ; dùng `SSCAN` hoặc thiết kế truy vấn khác.

**12. Tại sao không chỉ nhìn tổng memory để chọn cấu trúc?**  
Vì access pattern, TTL, concurrency, cluster slot, error handling và chi phí vận hành có thể quan trọng hơn một mức tiết kiệm bộ nhớ nhỏ.

## 28. Tóm lược nguyên tắc lựa chọn

- **String:** một giá trị, counter, JSON cache với TTL theo key.
- **Hash:** nhóm field của một entity, cập nhật field hoặc tăng số nguyên theo field.
- **List:** push/pop hai đầu cho hàng đợi/ngăn xếp đơn giản, không có ACK tự nhiên.
- **Set:** membership và phần tử không trùng, không có thứ hạng.
- **Sorted Set:** score/rank/top N và lịch xử lý theo thời gian, không tự cung cấp ACK.
- **Stream:** event log có ID, group, pending, ACK/replay trong phạm vi retention; cần idempotency.
- **Pub/Sub:** thông báo tức thời tới subscriber đang online, không có lưu trữ bền vững.
- **Bitmap:** cờ boolean theo offset nếu ID/index phù hợp.
- **HyperLogLog:** distinct count xấp xỉ, không liệt kê member.
- **GEO:** truy vấn tọa độ/khoảng cách, không thay thế GIS tổng quát.

**Cấu trúc Redis nên được chọn theo thao tác và bất biến của nghiệp vụ trước khi áp dụng một mẫu kiến trúc.** Sau khi chọn kiểu dữ liệu, còn phải xác định TTL, serialization, atomicy, giới hạn Cluster, retry và cơ chế phục hồi. Một mẫu chỉ thật sự phù hợp khi các lệnh Redis phục vụ chính xác những truy vấn mà ứng dụng sẽ thực hiện — với chi phí và giới hạn đã được hiểu rõ.

## Tài liệu tham khảo

- [Redis — Data Types](https://redis.io/docs/latest/develop/data-types/): mô hình Strings, Hashes, Lists, Sets, Sorted Sets, Streams và các cấu trúc chuyên biệt.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): các Redis operations và serialization trong Spring Data Redis.
- [Spring Data Redis — Object Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): mapping aggregate, Hash và hệ quả khi dùng Redis Repository.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Redis Streams, listener, group và ACK.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): lựa chọn cache data, serialization và TTL.
- [Redis — Strings](https://redis.io/docs/latest/develop/data-types/strings/): GET/SET và counter.
- [Redis — Hashes](https://redis.io/docs/latest/develop/data-types/hashes/): field/value và Hash operations.
- [Redis — Sets](https://redis.io/docs/latest/develop/data-types/sets/): membership và tập hợp.
- [Redis — Sorted Sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/): score, rank và ranges.
- [Redis — Lists](https://redis.io/docs/latest/develop/data-types/lists/): push/pop và queue.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): event log và consumer group.
- [Redis — Bitmaps](https://redis.io/docs/latest/develop/data-types/bitmaps/): bit operations trên String.
- [Redis — HyperLogLog](https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs/): distinct count xấp xỉ.
- [Redis — Geospatial](https://redis.io/docs/latest/develop/data-types/geospatial/): GEO commands và vị trí.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, hash tags và giới hạn multi-key.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): duyệt keyspace có giới hạn.
