# Sử dụng BoundOperations cho chuỗi thao tác trên cùng khóa

Trong Spring Data Redis, các thao tác thông thường thường bắt đầu từ `RedisTemplate` hoặc `StringRedisTemplate`:

~~~java
redis.opsForValue().set("session:42", "ACTIVE");
String state = redis.opsForValue().get("session:42");
redis.expire("session:42", Duration.ofMinutes(15));
~~~

Cách viết trên đúng và rõ ràng. Tuy nhiên, khi một phương thức phải thực hiện nhiều thao tác **trên chính một Redis key**, việc lặp lại tên key nhiều lần vừa dài dòng, vừa dễ gõ nhầm hoặc vô tình dùng key khác. Spring Data Redis cung cấp nhóm **BoundOperations** để gắn một đối tượng thao tác với một key cố định.

Ví dụ cùng ý tưởng với `BoundValueOperations`:

~~~java
BoundValueOperations<String, String> session =
        redis.boundValueOps("session:42");

session.set("ACTIVE");
String state = session.get();
session.expire(Duration.ofMinutes(15));
~~~

Điểm khác biệt nằm ở **cách tổ chức API phía Java**:

- Với `opsForValue()`, key thường được truyền vào mỗi phương thức như `set(key, value)` hoặc `get(key)`.
- Với `boundValueOps(key)`, key được chọn khi tạo đối tượng bound operations; các thao tác tiếp theo dùng lại chính key đó.
- Các lời gọi vẫn được chuyển thành **Redis command** gửi đến **Redis Server**. BoundOperations không phải bản sao dữ liệu trong JVM, không tự mở một transaction và không tự gom các lệnh thành một lần gửi.

Chủ đề của bài học là **khi nào nên bind key, cách dùng từng loại BoundOperations và giới hạn cần biết khi chạy chuỗi lệnh**.

## 1. “Bound” nghĩa là gắn thao tác với một key

Tên *BoundOperations* có thể hiểu là **operations bound to a key**: đối tượng chứa ngữ cảnh một key, để mỗi phương thức có thể thao tác với key đó mà không phải nhận lại tham số key.

~~~text
                   Spring Boot Service
                          |
                          | boundHashOps("cart:42")
                          v
               BoundHashOperations
                 key = "cart:42"
                    /    |    \
                   /     |     \
             put(...) get(...) entries()
                   \     |     /
                    \    |    /
                          v
                     RedisTemplate
                          |
                  RedisConnectionFactory
                          |
                   Lettuce / Jedis
                          |
                     Redis Server
                     key: cart:42
~~~

Mỗi lời gọi trong sơ đồ được Spring Data Redis xử lý thành lệnh Redis tương ứng. Redis Server giữ dữ liệu thực tế; BoundOperations chỉ cung cấp **API thuận tiện cho cùng key**.

Ví dụ:

~~~java
BoundHashOperations<String, String, String> cart =
        redis.boundHashOps("cart:42");

cart.put("SKU-A", "2");           // HSET cart:42 SKU-A 2
cart.put("SKU-B", "1");           // HSET cart:42 SKU-B 1
String quantity = cart.get("SKU-A"); // HGET cart:42 SKU-A
~~~

Tên key `cart:42` xuất hiện một lần khi khởi tạo đối tượng. Hai lệnh ghi và lệnh đọc đều nhắm đến **cùng Redis Hash**.

### BoundOperations không “khóa” Redis key

Chữ *bound* **không phải** distributed lock. Nó cũng không đồng nghĩa:

- Giữ một TCP connection riêng trong suốt vòng đời đối tượng.
- Đọc key một lần rồi cache dữ liệu trên Java heap.
- Đảm bảo key không bị xóa hoặc hết TTL giữa các lệnh.
- Làm cả chuỗi `put() → get() → expire()` trở thành atomic.
- Ngăn instance Spring Boot khác sửa cùng key.

Nếu ứng dụng khác xóa `cart:42`, lời gọi `cart.get("SKU-A")` sau đó vẫn có thể trả `null`. Nếu key được tạo lại với kiểu dữ liệu khác, thao tác Hash có thể gặp lỗi `WRONGTYPE`.

## 2. Các loại BoundOperations thường dùng

`RedisTemplate<K, V>` cung cấp nhiều cổng thao tác. Bảng sau nêu các dạng phổ biến; generic cụ thể thay đổi theo loại dữ liệu.

| Cách tạo | Interface nhận được | Kiểu Redis | Lệnh/nhu cầu thường gặp |
|---|---|---|---|
| `boundValueOps(key)` | `BoundValueOperations<K, V>` | String | SET, GET, INCR, append |
| `boundHashOps(key)` | `BoundHashOperations<K, HK, HV>` | Hash | HSET, HGET, HDEL, HGETALL |
| `boundListOps(key)` | `BoundListOperations<K, V>` | List | LPUSH, RPUSH, LPOP, LRANGE |
| `boundSetOps(key)` | `BoundSetOperations<K, V>` | Set | SADD, SISMEMBER, SMEMBERS, SREM |
| `boundZSetOps(key)` | `BoundZSetOperations<K, V>` | Sorted Set | ZADD, ZSCORE, ZREVRANGE |

Trong bảng, `K` là kiểu key Redis, `V` là value, còn `HK` và `HV` là kiểu hash field và hash value phía Java.

Các API và overload cụ thể cần được đối chiếu với phiên bản Spring Data Redis đang sử dụng. Những ví dụ tiếp theo tập trung vào các thao tác nền tảng và sử dụng `StringRedisTemplate` để key, hash field và value được xử lý theo chuỗi.

## 3. Chuẩn bị Spring Boot và StringRedisTemplate

Với Spring Boot 3.x và Gradle, ứng dụng có thể thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ví dụ `application.yml` khi Redis Server chạy ở máy phát triển:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Starter đưa Spring Data Redis và Redis driver (thường là Lettuce theo cấu hình mặc định) vào ứng dụng. **Redis Server vẫn phải chạy riêng**; starter không tự cung cấp một Redis Server.

`StringRedisTemplate` được Spring Boot auto-configure khi các điều kiện cần thiết được đáp ứng. Nó dùng serializer chuỗi cho key/value, phù hợp với các bài thực hành cơ bản. Ví dụ:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisExampleService {

    private final StringRedisTemplate redis;

    public RedisExampleService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // Các ví dụ BoundOperations sẽ sử dụng bean redis này.
}
~~~

### Cần phân biệt RedisTemplate và StringRedisTemplate

`RedisTemplate<K, V>` có thể được cấu hình serializer cho đối tượng Java tùy nhu cầu. `StringRedisTemplate` là phiên bản tiện dụng cho String. Việc bind key **không thay đổi serializer**:

~~~text
StringRedisTemplate + boundHashOps("cart:42")
    -> key và field/value chuỗi theo serializer của template

RedisTemplate<String, SomeObject> + boundValueOps("object:42")
    -> dùng serializer đã được cấu hình trên RedisTemplate
~~~

Nếu một service ghi key bằng kiểu serializer khác, service còn lại không thể mặc nhiên đọc cùng key như một chuỗi. BoundOperations chỉ cố định **key ở tầng API**, không thay đổi định dạng bytes của Redis.

## 4. BoundValueOperations: nhiều thao tác trên cùng String key

Giả sử cần lưu trạng thái phiên làm việc. Các thao tác nghiệp vụ:

1. Ghi trạng thái phiên.
2. Đọc lại trạng thái.
3. Cập nhật trạng thái nếu có hoạt động mới.
4. Kiểm tra/xóa dữ liệu theo vòng đời phiên.

### 4.1. Viết bằng OpsForValue thông thường

~~~java
String key = "session:status:" + sessionId;

redis.opsForValue().set(
        key, "ACTIVE", Duration.ofMinutes(15));

String current = redis.opsForValue().get(key);

redis.opsForValue().set(
        key, "IDLE", Duration.ofMinutes(15));
~~~

### 4.2. Viết bằng BoundValueOperations

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.BoundValueOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionStatusStore {

    private static final Duration SESSION_TTL =
            Duration.ofMinutes(15);

    private final StringRedisTemplate redis;

    public SessionStatusStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void activate(String sessionId) {
        BoundValueOperations<String, String> session =
                redis.boundValueOps(keyFor(sessionId));

        // Ghi giá trị và TTL bằng một thao tác SET có expiration.
        session.set("ACTIVE", SESSION_TTL);
    }

    public String getStatus(String sessionId) {
        BoundValueOperations<String, String> session =
                redis.boundValueOps(keyFor(sessionId));
        return session.get();
    }

    public void markIdle(String sessionId) {
        BoundValueOperations<String, String> session =
                redis.boundValueOps(keyFor(sessionId));
        session.set("IDLE", SESSION_TTL);
    }

    private String keyFor(String sessionId) {
        return "session:status:" + sessionId;
    }
}
~~~

Ở đây, một phương thức có thể nhận bound operations rồi gọi các thao tác tiếp theo **mà không truyền lại key**. Phần tạo key cũng tập trung tại `keyFor(...)`, giảm nguy cơ dùng sai namespace.

### 4.3. BoundValueOperations với counter

Redis hỗ trợ lệnh `INCR` để tăng số nguyên một cách atomic **ở cấp lệnh**.

~~~java
import org.springframework.data.redis.core.BoundValueOperations;

public long incrementPageViews(
        StringRedisTemplate redis,
        String pageId) {

    BoundValueOperations<String, String> views =
            redis.boundValueOps("page:views:" + pageId);

    Long next = views.increment();
    if (next == null) {
        throw new IllegalStateException(
                "Redis did not return a counter result");
    }
    return next;
}
~~~

Cơ chế lệnh:

~~~text
boundValueOps("page:views:home")
             |
             +-- increment() -> INCR page:views:home
             +-- increment() -> INCR page:views:home
             +-- get()       -> GET  page:views:home
~~~

Lợi thế của BoundOperations ở đây là **ngữ cảnh key ổn định**. Bản thân tính atomic của phép tăng đến từ **lệnh INCR của Redis Server**, không đến từ việc dùng `BoundValueOperations`.

## 5. TTL khi dùng BoundOperations: tiện nhưng cần hiểu ngữ nghĩa

Nhiều BoundOperations có các thao tác quản lý key thông qua khả năng kế thừa chung, chẳng hạn `expire(Duration)`. Ví dụ:

~~~java
BoundValueOperations<String, String> token =
        redis.boundValueOps("demo:token:123");

token.set("PENDING");
token.expire(Duration.ofMinutes(5));
~~~

Ví dụ này tạo **hai Redis command**:

~~~text
SET demo:token:123 PENDING
EXPIRE demo:token:123 300
~~~

Giữa hai lệnh có thể xảy ra sự cố. Nếu SET hoàn tất mà ứng dụng dừng trước EXPIRE, key có thể không có TTL. Vì vậy, khi một **String value phải có TTL ngay lúc ghi**, nên ưu tiên overload kết hợp ghi và thời hạn:

~~~java
token.set("PENDING", Duration.ofMinutes(5));
~~~

Thao tác này yêu cầu Redis thực hiện tương đương một `SET ... EX ...`, tránh khoảng trống giữa ghi và đặt TTL.

### 5.1. Đừng cho rằng mọi lệnh cập nhật đều giữ nguyên TTL

TTL phụ thuộc kiểu lệnh Redis:

- `SET key value` cho String thông thường **loại bỏ TTL cũ**, trừ khi dùng tùy chọn giữ TTL hoặc gán TTL mới trong lệnh.
- `SET key value EX ...` thay giá trị và thiết lập TTL theo yêu cầu.
- `HSET` thêm/sửa field của Hash hiện có **không tự gia hạn TTL** của toàn bộ Hash.
- `INCR` trên String key đã có TTL thường **giữ TTL hiện có**; việc tạo một key mới bằng INCR không tự gán TTL.
- Khi key tự hết hạn, đối tượng BoundOperations ở phía Java vẫn tồn tại nhưng các lệnh tiếp theo thao tác trên key **đã biến mất**.

Vì thế, với session cần *sliding expiration*, code phải xác định thao tác nào làm mới TTL và sử dụng lệnh phù hợp. Không nên coi việc bind key đồng nghĩa key có vòng đời tự động.

### 5.2. Hai lệnh không tự tạo một thao tác atomic

~~~java
Long count = counter.increment();
counter.expire(Duration.ofMinutes(10));
~~~

Đây vẫn là hai lệnh riêng. Nếu cần thiết lập TTL **chỉ ở lần tăng đầu tiên** với bảo đảm atomic, phải thiết kế một cơ chế phù hợp như Lua script hoặc một giải pháp transaction/điều kiện theo Redis; dùng BoundOperations không tự giải quyết race condition.

## 6. BoundHashOperations: thao tác nhiều field của một Hash key

Một trường hợp rất phù hợp với BoundOperations là **một Hash cho mỗi đối tượng hoặc aggregate**, vì nhiều thao tác nhắm đến cùng Redis key nhưng khác field.

Giả sử giỏ hàng của user 42 được lưu trong Redis Hash:

~~~text
Key: cart:42
Type: Hash
Fields:
    SKU-101 -> "2"
    SKU-205 -> "1"
    SKU-310 -> "4"
~~~

### 6.1. Code với BoundHashOperations

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.data.redis.core.BoundHashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartStore {

    private static final Duration CART_TTL =
            Duration.ofMinutes(30);

    private final StringRedisTemplate redis;

    public CartStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void addItem(String userId, String sku, int quantity) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        cart.put(sku, Integer.toString(quantity));
        cart.expire(CART_TTL);
    }

    public String getQuantity(String userId, String sku) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        return cart.get(sku);
    }

    public Map<String, String> getCart(String userId) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        return cart.entries();
    }

    public void removeItem(String userId, String sku) {
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(cartKey(userId));

        cart.delete(sku);
    }

    public void removeCart(String userId) {
        redis.delete(cartKey(userId));
    }

    private String cartKey(String userId) {
        return "cart:" + userId;
    }
}
~~~

Đoạn code minh họa một ranh giới **Hash key theo người dùng**:

| Phương thức Java | Lệnh Redis tương ứng | Phần bị tác động |
|---|---|---|
| `cart.put("SKU-101", "2")` | `HSET cart:42 SKU-101 2` | Một field |
| `cart.get("SKU-101")` | `HGET cart:42 SKU-101` | Một field |
| `cart.entries()` | `HGETALL cart:42` | Toàn bộ Hash |
| `cart.delete("SKU-101")` | `HDEL cart:42 SKU-101` | Một field |
| `cart.expire(Duration...)` | `EXPIRE cart:42 ...` | TTL của key Hash |
| `redis.delete("cart:42")` | `DEL cart:42` | Toàn bộ Hash |

### 6.2. Khi nào BoundHashOperations có lợi rõ nhất?

Khi một phương thức cần đọc/sửa nhiều field của **cùng một aggregate**:

~~~java
BoundHashOperations<String, String, String> profile =
        redis.boundHashOps("profile:42");

profile.put("displayName", "Lan");
profile.put("locale", "vi-VN");
profile.put("theme", "dark");

String theme = profile.get("theme");
Map<String, String> allFields = profile.entries();
~~~

Thay vì truyền `"profile:42"` trong từng lời gọi, mỗi dòng chỉ cần field. Điều này làm rõ rằng các thao tác tác động **một đối tượng logic**.

### 6.3. Lưu ý với TTL và cập nhật đồng thời

`cart.put(...)` và `cart.expire(...)` trong ví dụ là **hai Redis command**. Với yêu cầu “mỗi cập nhật phải gắn TTL bằng một thao tác atomic”, phải dùng transaction/script phù hợp. Bên cạnh đó:

- Hai service có thể sửa **hai field khác nhau** của cùng Hash mà không phải ghi lại toàn bộ JSON.
- Nếu nghiệp vụ cần cập nhật **nhiều field cùng lúc** theo một ràng buộc, các lệnh `put` liên tiếp không tự atomic như một nhóm.
- `entries()` đọc toàn bộ Hash; nếu Hash có số field rất lớn, nên ưu tiên đọc các field cần thiết hoặc cơ chế scan/phân trang phù hợp, tránh trả dữ liệu khổng lồ trong mỗi request.

**BoundHashOperations là API làm việc với một Hash key, không phải cơ chế khóa giao dịch trên Hash đó.**

## 7. BoundListOperations: một danh sách với nhiều thao tác

Redis List thường dùng khi cần giữ một dãy giá trị theo thứ tự. Ví dụ một danh sách thông báo gần đây cho mỗi user:

~~~text
Key: notifications:user42
Type: List
Items:
  event-C
  event-B
  event-A
~~~

### 7.1. Ví dụ dùng BoundListOperations

~~~java
import java.util.List;

import org.springframework.data.redis.core.BoundListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentNotificationStore {

    private final StringRedisTemplate redis;

    public RecentNotificationStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void push(String userId, String eventId) {
        BoundListOperations<String, String> notifications =
                redis.boundListOps(key(userId));

        // Phần tử mới được thêm ở bên trái (đầu List).
        notifications.leftPush(eventId);

        // Giữ tối đa 100 phần tử, index 0..99.
        notifications.trim(0, 99);
    }

    public List<String> recent(String userId, long limit) {
        if (limit <= 0) {
            return List.of();
        }

        BoundListOperations<String, String> notifications =
                redis.boundListOps(key(userId));

        List<String> values = notifications.range(0, limit - 1);
        return values == null ? List.of() : values;
    }

    private String key(String userId) {
        return "notifications:" + userId;
    }
}
~~~

Ở đây, `leftPush` và `trim` cùng tác động một List key. Mỗi lệnh Redis có ngữ nghĩa riêng:

~~~text
LPUSH notifications:42 event-C
LTRIM notifications:42 0 99
~~~

**Điều cần nhớ:** đây là hai lệnh riêng. Nếu nhiều publisher cùng thêm thông báo, có khoảng xen kẽ giữa `LPUSH` và `LTRIM`; khi yêu cầu giới hạn List được áp dụng atomic với thao tác ghi, cần Lua script hoặc cơ chế tương ứng.

### 7.2. List blocking không thay đổi chỉ vì dùng BoundOperations

Các API List có thể hỗ trợ thao tác pop theo thời gian chờ, tương ứng `BLPOP`/`BRPOP` tùy phương thức. Chẳng hạn `rightPop(Duration.ofSeconds(5))` có thể đợi khi List rỗng:

~~~java
BoundListOperations<String, String> queue =
        redis.boundListOps("jobs:pending");

String jobId = queue.rightPop(Duration.ofSeconds(5));

if (jobId == null) {
    // Hết thời hạn chờ nhưng chưa có job.
}
~~~

BoundOperations vẫn chỉ cố định key. **Blocking call vẫn chặn thread gọi** trong API đồng bộ và có thể cần connection chuyên biệt theo driver/factory. Không gọi thao tác blocking đồng bộ trực tiếp trên event-loop WebFlux; nên sử dụng worker/executor phù hợp hoặc API reactive thích hợp.

Nếu dùng List làm queue, cũng cần thiết kế cơ chế xử lý lỗi: một phần tử đã bị pop ra khỏi List không tự được đưa lại vào hàng đợi khi consumer chết. BoundOperations không thêm acknowledgement hay retry.

## 8. BoundSetOperations: quản lý tập phần tử không trùng

Ví dụ mỗi khóa học có một tập user đã đăng ký:

~~~text
Key: course:redis:members
Type: Set
Members:
  user-42
  user-57
  user-91
~~~

### 8.1. Thao tác cùng một Redis Set

~~~java
import java.util.Set;

import org.springframework.data.redis.core.BoundSetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CourseMemberStore {

    private final StringRedisTemplate redis;

    public CourseMemberStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void enroll(String courseId, String userId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");
        members.add(userId);
    }

    public boolean isEnrolled(String courseId, String userId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");

        return Boolean.TRUE.equals(members.isMember(userId));
    }

    public void leave(String courseId, String userId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");
        members.remove(userId);
    }

    public Set<String> getMembers(String courseId) {
        BoundSetOperations<String, String> members =
                redis.boundSetOps("course:" + courseId + ":members");
        return members.members();
    }
}
~~~

Lợi ích:

- `add(...)` thêm member, Redis Set không chứa trùng giá trị theo định nghĩa của nó.
- `isMember(...)` kiểm tra một user có thuộc Set không.
- `remove(...)` xóa một member.
- `members()` trả về tập member, phù hợp khi tập có kích thước được kiểm soát.

Với tập rất lớn, `members()` có thể truyền lượng dữ liệu khổng lồ; nên cân nhắc scan/phân trang hoặc thay đổi cách lưu trữ theo access pattern. Việc gắn key không làm chi phí đọc toàn Set biến mất.

### 8.2. Set khác List

Nếu cần xác định **membership không trùng**, Set phù hợp. Nếu cần duy trì **thứ tự và số lần xuất hiện** của phần tử, List có ngữ nghĩa khác. BoundOperations chỉ là API theo cấu trúc dữ liệu đã chọn; chọn sai kiểu Redis thì bind key cũng không khắc phục được mô hình.

## 9. BoundZSetOperations: bảng xếp hạng cho cùng một key

Một Redis Sorted Set gắn mỗi member với một score. Ví dụ bảng xếp hạng điểm theo ngày:

~~~text
Key: leaderboard:2026-11-12
Type: Sorted Set
Members / Scores:
  user-42 -> 120.0
  user-57 -> 87.5
  user-91 -> 150.0
~~~

### 9.1. Thao tác với BoundZSetOperations

~~~java
import java.util.Set;

import org.springframework.data.redis.core.BoundZSetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class LeaderboardStore {

    private final StringRedisTemplate redis;

    public LeaderboardStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private BoundZSetOperations<String, String> board(String day) {
        return redis.boundZSetOps("leaderboard:" + day);
    }

    public void recordScore(
            String day,
            String userId,
            double score) {
        board(day).add(userId, score);
    }

    public Double scoreOf(String day, String userId) {
        return board(day).score(userId);
    }

    public Set<String> topTen(String day) {
        return board(day).reverseRange(0, 9);
    }

    public void removeUser(String day, String userId) {
        board(day).remove(userId);
    }
}
~~~

Lệnh tương ứng:

~~~text
ZADD leaderboard:2026-11-12 120.0 user-42
ZSCORE leaderboard:2026-11-12 user-42
ZREVRANGE leaderboard:2026-11-12 0 9
ZREM leaderboard:2026-11-12 user-42
~~~

Lưu ý: `add(member, score)` thường thiết lập score được truyền vào, **không có nghĩa cộng thêm điểm**. Nếu nghiệp vụ yêu cầu cộng delta một cách atomic, cần dùng thao tác tăng score tương ứng (ví dụ `incrementScore(...)`) thay vì đọc score rồi tự cộng và ghi lại.

BoundZSetOperations thuận tiện vì mọi thao tác trên một bảng xếp hạng cùng dùng một Redis key, nhưng nếu bảng xếp hạng tăng vô hạn phải có chính sách retention, giới hạn số member hoặc phân vùng theo ngày/tenant. Một Sorted Set rất lớn vẫn là một key nằm trong một hash slot khi dùng Redis Cluster.

## 10. So sánh BoundOperations với các API opsFor...

Hai cách gọi **cùng thao tác trên cùng dữ liệu Redis** khi template, key và arguments tương đương:

| Dùng template trực tiếp | Dùng bound operations | Lệnh Redis tương đương |
|---|---|---|
| `redis.opsForValue().get(key)` | `redis.boundValueOps(key).get()` | GET |
| `redis.opsForValue().set(key, value)` | `redis.boundValueOps(key).set(value)` | SET |
| `redis.opsForHash().put(key, field, value)` | `redis.boundHashOps(key).put(field, value)` | HSET |
| `redis.opsForHash().get(key, field)` | `redis.boundHashOps(key).get(field)` | HGET |
| `redis.opsForList().leftPush(key, value)` | `redis.boundListOps(key).leftPush(value)` | LPUSH |
| `redis.opsForSet().add(key, member)` | `redis.boundSetOps(key).add(member)` | SADD |
| `redis.opsForZSet().add(key, member, score)` | `redis.boundZSetOps(key).add(member, score)` | ZADD |

Điểm đáng chú ý là **sự khác biệt chủ yếu về biểu đạt ý định và cấu trúc mã**:

~~~java
// Dùng OpsForHash: key được truyền vào mọi lần.
redis.opsForHash().put(cartKey, "SKU-A", "2");
redis.opsForHash().put(cartKey, "SKU-B", "1");
redis.opsForHash().get(cartKey, "SKU-A");

// Dùng BoundHashOperations: biểu đạt cùng một aggregate.
BoundHashOperations<String, String, String> cart =
        redis.boundHashOps(cartKey);
cart.put("SKU-A", "2");
cart.put("SKU-B", "1");
cart.get("SKU-A");
~~~

Đừng mặc định chuyển sang BoundOperations sẽ:

- Giảm ba lệnh Redis thành một lệnh.
- Tiết kiệm ba lượt mạng bằng cách tự bật pipeline.
- Giữ một RedisConnection vật lý trong cả ba lệnh.
- Làm mọi thao tác atomic cùng nhau.
- Tự tăng tốc xử lý Redis trên server.

Muốn giảm round trips cần cân nhắc **lệnh Redis hỗ trợ batch**, `RedisTemplate.executePipelined(...)` hoặc cách tổ chức câu lệnh phù hợp. Muốn có atomicity cần một lệnh Redis atomic, transaction hoặc script theo yêu cầu. BoundOperations không thay thế những cơ chế đó.

## 11. Thời điểm tạo và giữ BoundOperations

Đối tượng BoundOperations gắn với key được tạo như sau:

~~~java
BoundValueOperations<String, String> bound =
        redis.boundValueOps("session:42");
~~~

Đây là một đối tượng API bên Java. **Nó không có nghĩa Redis Server đã cấp phát key**, và cũng không có nghĩa kết nối mạng đã được mở chỉ vì bạn bind key.

### 11.1. Nên tạo theo phạm vi nghiệp vụ

Ví dụ khi xử lý một yêu cầu thêm sản phẩm:

~~~java
public void changeCart(String userId) {
    String cartKey = "cart:" + userId;
    BoundHashOperations<String, String, String> cart =
            redis.boundHashOps(cartKey);

    cart.put("SKU-A", "3");
    cart.put("SKU-B", "1");
    String count = cart.get("SKU-A");
}
~~~

Một biến local `cart` vừa giúp code ngắn, vừa giúp reviewer thấy rõ mọi thao tác đang làm việc với **cùng một giỏ**.

### 11.2. Tránh bind key của một người dùng vào singleton service

Thiết kế có vấn đề:

~~~java
@Service
public class WrongCartStore {

    private final BoundHashOperations<String, String, String> cart;

    public WrongCartStore(StringRedisTemplate redis) {
        // Mọi request sau đó đều thao tác cart của user 42.
        this.cart = redis.boundHashOps("cart:42");
    }
}
~~~

Khi service phục vụ nhiều user, một field bound operations gắn cứng với `cart:42` làm nghiệp vụ ghi nhầm vào giỏ của user 42. Thiết kế tốt hơn là giữ **template/factory** trong singleton và tạo BoundOperations theo key được xác định cho **request/ngữ cảnh hiện tại**.

Trường hợp key thực sự là key chung bất biến của service (ví dụ một counter toàn cục được thiết kế có chủ đích), việc giữ một đối tượng BoundOperations cho key đó có thể hợp lý. Vấn đề không nằm ở việc tạo object, mà ở **độ đúng của key và cách sử dụng đồng thời**.

### 11.3. Đừng tự quản lý RedisConnection chỉ vì đã dùng BoundOperations

Đối với các thao tác thông thường, template tự quản lý việc lấy và trả connection thông qua `RedisConnectionFactory`. Bạn không cần:

~~~java
// Không cần tự lấy connection cho ví dụ boundValueOps thông thường.
RedisConnection conn = connectionFactory.getConnection();
~~~

Hãy dùng template/bound API theo vòng đời của Spring. Nếu cần callback mức thấp, transaction hoặc pipeline, xem API của template và quy tắc quản lý connection tương ứng.

## 12. BoundOperations không tạo transaction hoặc snapshot

Đây là giới hạn cần hiểu rõ nhất của bài học.

Giả sử:

~~~java
BoundValueOperations<String, String> balance =
        redis.boundValueOps("balance:user42");

String current = balance.get();
long next = Long.parseLong(current) - 100;
balance.set(Long.toString(next));
~~~

Đó vẫn là:

~~~text
GET balance:user42
(Java trừ 100)
SET balance:user42 newValue
~~~

Hai ứng dụng có thể cùng đọc cùng số dư ban đầu rồi ghi đè kết quả của nhau. Việc dùng **cùng một đối tượng BoundValueOperations** trong một phương thức không làm chuỗi đó atomic.

### 12.1. Dùng lệnh atomic khi có thể

Nếu nhu cầu chỉ là tăng/giảm một counter, thay chuỗi đọc–sửa–ghi bằng thao tác Redis tương ứng:

~~~java
BoundValueOperations<String, String> counter =
        redis.boundValueOps("stock:SKU-A");

Long remaining = counter.decrement();
~~~

Với kiểu dữ liệu số phù hợp, Redis thực thi lệnh giảm/increment atomic tại server. **Tuy nhiên**: một lệnh giảm atomic vẫn có thể khiến stock xuống số âm; nếu nghiệp vụ bắt buộc “chỉ giảm khi còn đủ hàng”, cần thêm điều kiện atomic qua Lua script hoặc cơ chế phù hợp, không thể chỉ dựa vào decrement.

### 12.2. Chuỗi nhiều field/lệnh phải có cơ chế riêng

Ví dụ:

~~~java
BoundHashOperations<String, String, String> order =
        redis.boundHashOps("order:42");

order.put("status", "PAID");
order.put("paidAt", "2026-11-12T10:00:00Z");
order.expire(Duration.ofDays(7));
~~~

Các thao tác này không trở thành một lệnh chỉ vì chúng dùng cùng `order`. Nếu cần “status và paidAt luôn cập nhật cùng nhau” thì xem:

- Một thao tác Hash hỗ trợ ghi nhiều field trong **một lệnh HSET** khi đủ đáp ứng invariant.
- Redis transaction `MULTI/EXEC` với semantics và giới hạn phù hợp.
- Lua script chạy tại Redis Server nếu cần điều kiện/logic atomic.

Nếu có cả cơ sở dữ liệu quan hệ và Redis trong một nghiệp vụ, BoundOperations cũng **không** tạo transaction phân tán giữa hai hệ thống.

## 13. BoundOperations và pipeline khác nhau

Giả sử cần ghi 1000 field của **một** Hash. Hai cách tiếp cận:

**Cách 1 — Nhiều lời gọi trên một bound operations:**

~~~java
BoundHashOperations<String, String, String> batch =
        redis.boundHashOps("batch:example");

for (int i = 0; i < 1000; i++) {
    batch.put("field-" + i, "value-" + i);
}
~~~

Đây là nhiều lời gọi `HSET`. BoundOperations giúp tránh truyền key 1000 lần trong code nhưng **không mặc nhiên giảm round trips**.

**Cách 2 — Một lệnh HSET nhiều field** khi có dữ liệu sẵn:

~~~java
Map<String, String> fields = Map.of(
        "field-1", "value-1",
        "field-2", "value-2",
        "field-3", "value-3"
);

BoundHashOperations<String, String, String> batch =
        redis.boundHashOps("batch:example");

batch.putAll(fields);
~~~

`putAll(...)` cho phép cập nhật nhiều field trong cùng một thao tác Hash theo API của Spring Data Redis, phù hợp khi số field/payload không quá lớn.

Khi yêu cầu trải rộng qua nhiều key hoặc nhiều command không có dạng batch trực tiếp, `RedisTemplate.executePipelined(...)` có thể giảm chi phí round trips. Pipeline **không phải transaction atomic**, và một số phương thức được gọi bên trong pipeline có semantics trả kết quả khác lời gọi độc lập.

### 13.1. Khi nào dùng công cụ nào?

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Nhiều thao tác cùng key, code dễ đọc | BoundOperations |
| Một lần ghi nhiều field của cùng Hash | `BoundHashOperations.putAll(...)` / HashOperations |
| Một lần đọc nhiều field của Hash | `multiGet(...)` trên Hash operations |
| Gửi nhiều lệnh giảm round trips | Pipeline, batch command |
| Nhiều lệnh phải atomic theo ngữ nghĩa Redis | Lệnh atomic, transaction hoặc Lua script |
| Cần lệnh trên nhiều key khác nhau | Các `opsFor...` thông thường hoặc tạo bound operations riêng cho từng key |

Các lựa chọn này có thể kết hợp, miễn tuân thủ lifecycle và API mà Spring Data Redis hỗ trợ. Bind key không phủ định nhu cầu xử lý concurrency, transaction hay performance.

## 14. Thiết kế key và đối tượng BoundOperations

Khi chọn BoundOperations, nên đặt key theo aggregate rõ ràng:

~~~text
profile:user:42
cart:user:42
session:status:42
course:redis:members
leaderboard:2026-11-12
~~~

Từ đó, code thể hiện cùng ngữ cảnh:

~~~java
String key = "profile:user:" + userId;
BoundHashOperations<String, String, String> profile =
        redis.boundHashOps(key);

profile.put("locale", "vi-VN");
profile.put("theme", "dark");
~~~

Điểm cần chú ý:

1. **Không ghép dữ liệu nhạy cảm trực tiếp vào tên key** (mật khẩu, token bí mật, thông tin cá nhân không cần thiết).
2. **Không lấy key của user khác** do nhầm ID hoặc xử lý sai quyền nghiệp vụ. API Redis không tự thực hiện phân quyền ứng dụng theo userId.
3. Chọn prefix và cơ chế đặt tên nhất quán để tránh key String/Hash/List bị dùng lẫn kiểu.
4. Nếu có nhiều tenant, cần thiết kế namespace/ACL phù hợp; BoundOperations không tách tenant tự động.
5. Với Redis Cluster, toàn bộ nội dung của **một key** nằm trong một hash slot. Dùng bound operations không giúp một key khổng lồ phân tán sang nhiều shard.

### 14.1. BoundOperations không dành để thay đổi key liên tục

Nếu đang xử lý một danh sách 1000 user và mỗi user có một key khác nhau, viết:

~~~java
for (String userId : userIds) {
    BoundValueOperations<String, String> state =
            redis.boundValueOps("state:" + userId);
    state.set("ACTIVE");
}
~~~

là hợp lệ, nhưng ở đây việc bind key chỉ dùng một lệnh trước khi bỏ đối tượng. Một lời gọi trực tiếp có thể ngắn và rõ hơn:

~~~java
for (String userId : userIds) {
    redis.opsForValue().set("state:" + userId, "ACTIVE");
}
~~~

Nếu cần hiệu năng ghi hàng loạt trên nhiều key, xem batch/pipeline hoặc mô hình dữ liệu thay vì giả định tạo BoundOperations sẽ giúp nhanh hơn.

## 15. Phân biệt lỗi từ BoundOperations với lỗi dữ liệu/Redis

| Triệu chứng | Nguyên nhân cần xem | Hướng xử lý |
|---|---|---|
| `boundHashOps(key).get(field)` trả `null` | Key/field chưa tồn tại hoặc đã hết hạn | Kiểm tra tên key, field và TTL |
| Sau khi dùng `boundValueOps`, gọi `boundHashOps` trên cùng tên key bị `WRONGTYPE` | Key trên server đang là String, không phải Hash | Chọn key namespace và kiểu dữ liệu nhất quán |
| `get()` thấy giá trị cũ dù code vừa `set()` trong một nhánh khác | Ghi đè đồng thời, endpoint khác, thời điểm đọc, logic cache/replica | Kiểm tra access pattern, concurrency và topology |
| Thay `set(value, Duration)` bằng `set(value)` thì key mất TTL | SET không có TTL thường xóa thời hạn cũ | Đặt TTL ngay trong SET hoặc dùng tùy chọn phù hợp |
| `put()` rồi `expire()` nhưng đôi khi key không có TTL | Hai lệnh không atomic hoặc bị ngắt giữa chừng | Dùng giải pháp atomic khi TTL là invariant bắt buộc |
| Code bind xong nhưng Redis không có key | Tạo bound object chưa thực hiện lệnh ghi | Gọi thao tác phù hợp; kiểm tra kết quả |
| Một singleton ghi dữ liệu của mọi user vào cùng key | BoundOperations được khởi tạo với key cố định không đúng phạm vi | Tạo bound object theo user/request |
| `entries()` hoặc `members()` chậm | Collection quá lớn hoặc tải toàn bộ dữ liệu | Đọc chọn lọc, scan có kiểm soát, giới hạn kích thước |
| GET/SET timeout | Kết nối, Redis Server, driver/pool hoặc mạng | Chẩn đoán RedisConnectionFailure/timeout ở đúng tầng |
| Kết quả bytes/chuỗi không đọc được như dự kiến | Serializer/key encoding giữa các client khác nhau | Kiểm tra template serializer và namespace |

### 15.1. Ví dụ WRONGTYPE

~~~bash
SET demo:mixed hello
HGET demo:mixed field
~~~

Redis Server sẽ báo lỗi vì `demo:mixed` đang là **String** nhưng client lại gửi lệnh cho **Hash**. Tương tự, nếu code Spring bind:

~~~java
redis.boundValueOps("demo:mixed").set("hello");
redis.boundHashOps("demo:mixed").put("field", "value");
~~~

việc dùng BoundOperations không tự chuyển String key thành Hash. Cần thiết kế tiền tố key rõ ràng hoặc quản lý migration dữ liệu.

### 15.2. Key hết hạn giữa chuỗi thao tác

~~~text
T0: boundHashOps("cart:42")
T1: HSET cart:42 SKU-A 2
T2: EXPIRE cart:42 1
T3: (hết 1 giây; Redis xóa key)
T4: HGET cart:42 SKU-A -> nil
~~~

Đối tượng `cart` ở Java vẫn có thể được gọi tiếp tại T4, nhưng Redis Server đã xóa key. **Bound không đồng nghĩa pin key trong bộ nhớ Redis**.

## 16. Bài thực hành: một giỏ hàng, một BoundHashOperations

Để thấy rõ ý nghĩa “cùng key”, thử một bài lab có thể chạy trong service hoặc test. Redis Server phải đang hoạt động và ứng dụng đã cấu hình `StringRedisTemplate`.

### 16.1. Code minh họa

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.UUID;

import org.springframework.data.redis.core.BoundHashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartBoundDemo {

    private final StringRedisTemplate redis;

    public CartBoundDemo(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void demonstrate() {
        String key = "demo:cart:" + UUID.randomUUID();
        BoundHashOperations<String, String, String> cart =
                redis.boundHashOps(key);

        try {
            cart.put("SKU-A", "2");
            cart.put("SKU-B", "1");
            cart.expire(Duration.ofMinutes(2));

            String quantityA = cart.get("SKU-A");
            Map<String, String> allItems = cart.entries();

            System.out.println("Quantity SKU-A = " + quantityA);
            System.out.println("Cart items = " + allItems);

            cart.delete("SKU-B");
            System.out.println("After remove = " + cart.entries());
        } finally {
            redis.delete(key);
        }
    }
}
~~~

**Cách đọc kết quả:**

- Sau `put(...)` hai lần, key Hash có hai field.
- `cart.get("SKU-A")` thường trả `"2"`.
- `cart.entries()` trả map chứa hai field nếu không có thao tác cạnh tranh/xóa/hết hạn ngoài ví dụ.
- Sau `cart.delete("SKU-B")`, map còn `SKU-A`.
- Cuối cùng, `redis.delete(key)` dọn key demo; đây là thao tác trên toàn key.

Key được tạo với UUID giúp tránh đụng dữ liệu nghiệp vụ. TTL hai phút là phương án dự phòng nếu quá trình chạy dừng trước khi cleanup.

**Lưu ý:** đây là ví dụ thao tác đơn giản. `put(...)` hai lần và `expire(...)` vẫn là những lệnh riêng, không phải một transaction.

### 16.2. Đối chiếu bằng redis-cli

Trong lúc ví dụ còn giữ key, các lệnh Redis tương ứng là:

~~~bash
HSET demo:cart:example SKU-A 2
HSET demo:cart:example SKU-B 1
HGET demo:cart:example SKU-A
HGETALL demo:cart:example
HDEL demo:cart:example SKU-B
EXPIRE demo:cart:example 120
TTL demo:cart:example
DEL demo:cart:example
~~~

Tên `demo:cart:example` được dùng để thao tác thủ công qua redis-cli, khác với key ngẫu nhiên trong code Java. Chúng có cùng semantics Redis nhưng **không phải cùng một key thực tế** trừ khi bạn chủ động đổi tên trong bài thực hành.

### 16.3. Tự thay đổi bài lab

Thử ba thay đổi:

1. **Thay Hash bằng String JSON**: một `BoundValueOperations` lưu trọn giỏ, quan sát việc sửa một SKU yêu cầu cập nhật cả JSON.
2. **Đổi TTL xuống một giây**: sau khi chờ hơn một giây, gọi `cart.get("SKU-A")` và quan sát kết quả; object bound không bảo vệ key khỏi expiration.
3. **Ghi bằng String rồi đọc như Hash trên cùng tên key**: nhận diện lỗi sai kiểu dữ liệu và giải thích vì sao namespace quan trọng.

Những thử nghiệm này có mục đích làm rõ API, không thay thế các bài kiểm tra transaction, concurrency và performance riêng.

## 17. Khi nào nên chọn BoundOperations?

**Nên dùng khi:**

- Một phương thức xử lý nhiều thao tác trên cùng một Redis key.
- Một aggregate được lưu trong Hash/List/Set/Sorted Set và thường cần nhiều lời gọi theo field/member.
- Muốn tránh lặp key ở nhiều dòng và giảm nguy cơ gõ lệch namespace.
- Muốn code thể hiện rõ “đang làm việc với cart của user X” hoặc “đang làm việc với leaderboard của ngày Y”.
- Muốn tập trung quy trình thao tác với một key trong một hàm dễ đọc.

**Không cần thiết khi:**

- Mỗi key chỉ có đúng một lời gọi đơn giản.
- Xử lý hàng loạt nhiều key khác nhau, mỗi key một thao tác.
- Bài toán cốt lõi là atomic transaction, pipeline, Lua script hoặc quản lý nhiều key trong Redis Cluster; đây là những khả năng riêng cần thiết kế đúng.
- Một API cấp thấp cần kiểm soát RedisConnection/driver theo một lifecycle cụ thể.

Điều quan trọng là **tính dễ đọc và nhất quán của mã nghiệp vụ**. BoundOperations có thể là lựa chọn tốt nhưng không phải lúc nào cũng cần thay mọi lời gọi `opsFor...`.

## 18. Câu hỏi tự kiểm tra

**1. Sau khi gọi `redis.boundValueOps("status:42")`, Redis đã tạo key `status:42` chưa?**

Chưa chắc. Việc bind tạo một đối tượng Java gắn với key; key trên Redis Server chỉ xuất hiện khi có lệnh ghi hoặc thao tác tạo dữ liệu phù hợp.

**2. `BoundHashOperations` có giúp nhiều `put(...)` chạy atomic như một nhóm không?**

Không. Các lời gọi là các lệnh riêng; dùng lệnh batch thích hợp, transaction hoặc script khi nghiệp vụ cần atomicity.

**3. Có thể dùng `BoundValueOperations` để lưu JSON, rồi đổi sang `BoundHashOperations` trên cùng key không?**

Không thể tùy tiện. Redis key tại một thời điểm có một kiểu dữ liệu. Gọi lệnh Hash trên key đang là String có thể gây `WRONGTYPE`.

**4. `expire(Duration)` trên BoundHashOperations đặt TTL cho mỗi field hay cả Hash key?**

Trong cách dùng Redis key TTL phổ thông, nó đặt TTL cho **toàn bộ Hash key**. Hết hạn thì toàn bộ field trong key biến mất.

**5. Vì sao không nên giữ bound operations theo userId trong một singleton nếu service phục vụ nhiều user?**

Vì bound object gắn với key đã chọn. Nếu khởi tạo với key của user A rồi tái sử dụng cho user B, dữ liệu có thể bị đọc/ghi sai user.

**6. Dùng BoundOperations có giảm số lần mạng khi có 100 lần `put(...)` không?**

Không tự động. Mỗi `put(...)` vẫn thường là một Redis command. Cần batch/pipeline phù hợp nếu mục tiêu là giảm round trips.

**7. Có thể dùng BoundOperations với `StringRedisTemplate` không?**

Có. Ví dụ `BoundValueOperations<String, String>`, `BoundHashOperations<String, String, String>`. Key/value tuân theo serializer của StringRedisTemplate.

**8. Hai thread có thể thay đổi cùng một key dù mỗi thread tạo BoundOperations riêng không?**

Có. BoundOperations không khóa dữ liệu. Phải xem xét concurrency, atomic command và business invariant.

**9. Tại sao `set(value, Duration)` thường phù hợp hơn `set(value)` rồi `expire(Duration)` cho String cần TTL bắt buộc?**

Vì đặt giá trị và thời hạn trong một lệnh Redis giảm khả năng key được ghi thành công nhưng không có TTL do lỗi giữa hai command.

**10. Sự khác biệt chính giữa `opsForHash().get(key, field)` và `boundHashOps(key).get(field)` là gì?**

Cả hai cùng đọc Hash field tại Redis. Cách thứ hai mang theo key cố định trong đối tượng bound, giúp chuỗi thao tác trên cùng key rõ ràng hơn.

## Ghi nhớ

~~~text
RedisTemplate
    |
    +-- opsForValue().get(key)
    +-- opsForHash().put(key, field, value)
    |
    | Khi cần nhiều thao tác cùng key:
    v
BoundOperations
    |
    +-- boundValueOps(key) -> get(), set(), increment()
    +-- boundHashOps(key)  -> get(field), put(field, value)
    +-- boundListOps(key)  -> leftPush(value), range(...)
    +-- boundSetOps(key)   -> add(member), isMember(member)
    +-- boundZSetOps(key)  -> add(member, score), reverseRange(...)
    |
    v
Vẫn gửi các Redis command thông thường qua driver
đến Redis Server và áp dụng semantics Redis như cũ.
~~~

**BoundOperations là cách biểu diễn một chuỗi thao tác cùng Redis key rõ ràng và ít lặp hơn trong Spring Data Redis.** Hãy dùng nó khi một phương thức làm việc với một aggregate cố định; đồng thời luôn tách bạch việc **bind key** với những yêu cầu độc lập như **TTL, serialization, atomicity, transaction, pipeline, concurrency và quản lý connection**.
