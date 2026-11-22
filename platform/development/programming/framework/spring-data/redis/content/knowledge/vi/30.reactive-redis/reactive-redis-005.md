# Sử dụng các nhóm Reactive Operations trong Spring Data Redis

Khi xây dựng ứng dụng Spring WebFlux hoặc một luồng xử lý dựa trên Project Reactor, ta thường muốn truy cập Redis theo kiểu **không chặn luồng chờ I/O**. Spring Data Redis cung cấp `ReactiveRedisTemplate` và `ReactiveStringRedisTemplate` để thực hiện điều đó. Thay vì gọi `RedisTemplate` rồi nhận kết quả ngay trên thread đang chạy, API reactive trả về `Mono<T>` hoặc `Flux<T>`; lệnh Redis được thực hiện khi luồng reactive được subscribe.

Điểm quan trọng của bài học là **các nhóm Reactive Operations**. Một template không chỉ cung cấp `GET`/`SET`: nó có những nhóm API theo loại dữ liệu Redis, như **Value, Hash, List, Set, Sorted Set, Geo, HyperLogLog và Stream**. Chọn đúng nhóm operations giúp code diễn đạt rõ cấu trúc dữ liệu, dùng đúng lệnh Redis và kết hợp được với luồng Reactor.

Ví dụ:

```java
Mono<String> value =
        reactiveStringRedisTemplate.opsForValue().get("config:theme");

Mono<Long> number =
        reactiveStringRedisTemplate.opsForValue().increment("metrics:views");

Flux<String> members =
        reactiveStringRedisTemplate.opsForSet().members("tags:article:42");
```

Ba biểu thức trên **không trả về dữ liệu đồng bộ**. Chúng tạo các publisher phản ứng; phía gọi cần compose các publisher bằng `map`, `flatMap`, `zip`, `collectList`, `then`... hoặc trả trực tiếp chúng cho WebFlux. Không gọi `.block()` để ép luồng phản ứng thành đồng bộ trên event-loop.

Bài này đi từ cách cấu hình template, hiểu `Mono`/`Flux`, sử dụng từng nhóm operations, đến kết hợp nhiều thao tác, giới hạn đồng thời, xử lý lỗi, serialization và các sai lầm thường gặp.

## 1. Reactive Redis nằm ở đâu trong ứng dụng?

Một luồng điển hình:

```text
HTTP request
    |
    v
Spring WebFlux Controller
    |
    | Mono<ProductDto> / Flux<ProductDto>
    v
Reactive Service
    |
    | ReactiveRedisTemplate / ReactiveStringRedisTemplate
    v
ReactiveRedisConnectionFactory
    |
    | Redis client hỗ trợ reactive (thường là Lettuce)
    v
Redis server
    |
    v
Kết quả đi ngược lại dưới dạng tín hiệu Reactor
```

Ở đây, *reactive* chủ yếu mô tả **cách phía Java tổ chức thao tác I/O**:

- Không giữ một thread chỉ để chờ mỗi phản hồi Redis theo kiểu blocking.
- Có thể compose các tác vụ bất đồng bộ bằng `Mono` và `Flux`.
- Có cơ chế truyền tín hiệu hoàn thành, lỗi và cancellation.
- Có thể giới hạn số thao tác đang thực hiện đồng thời khi xử lý nhiều key.

Reactive **không có nghĩa** Redis tự thực thi mọi lệnh song song hoặc mỗi lệnh Redis trở nên nguyên tử hơn. Redis vẫn có những ràng buộc về server, connection, key type, transaction, cluster và độ bền dữ liệu như khi truy cập bằng API thông thường.

### 1.1. `Mono` và `Flux` khác nhau thế nào?

| Kiểu Reactor | Ý nghĩa | Ví dụ Redis |
|---|---|---|
| `Mono<String>` | Tối đa một giá trị, hoặc rỗng/lỗi | `GET` một key |
| `Mono<Boolean>` | Một kết quả logic | `SET`, `HSET`/thao tác kiểm tra có kiểu Boolean |
| `Mono<Long>` | Một kết quả số | `INCR`, `SADD`, `DEL` |
| `Flux<String>` | Nhiều giá trị theo luồng | Thành viên Redis Set, phần tử Redis List |
| `Flux<Map.Entry<...>>` | Nhiều entry | Các field/value của Redis Hash |
| `Flux<MapRecord<...>>` | Nhiều bản ghi | Đọc Redis Stream |

Một key không tồn tại thường làm `opsForValue().get(key)` hoàn thành bằng `Mono.empty()`, **không phát ra Java `null`** làm giá trị của `Mono`.

Ví dụ:

```java
Mono<String> theme =
        redis.opsForValue()
                .get("user:42:theme")
                .defaultIfEmpty("light");
```

Nếu Redis không tìm thấy key, luồng trả `"light"`. Nếu Redis trả lỗi kết nối, đây là **tín hiệu lỗi**, không phải cache miss; `defaultIfEmpty` không tự biến lỗi kết nối thành giá trị mặc định.

### 1.2. Lệnh thường chỉ chạy khi có subscriber

```java
Mono<Boolean> write =
        redis.opsForValue().set("demo:reactive:key", "hello");
```

Đoạn code trên chỉ tạo một publisher. Trong mô hình Reactor thông thường, lời gọi Redis được kích hoạt khi có subscription. Ví dụ trong ứng dụng WebFlux, framework subscribe vào publisher do controller trả về.

Không nên viết:

```java
public void update() {
    redis.opsForValue().set("demo:key", "value");
    // Publisher bị bỏ qua: không có luồng nào đảm nhận việc chạy.
}
```

Thay vào đó:

```java
public Mono<Boolean> update() {
    return redis.opsForValue().set("demo:key", "value");
}
```

Hoặc nếu phương thức chỉ cần biểu diễn hoàn tất:

```java
public Mono<Void> update() {
    return redis.opsForValue()
            .set("demo:key", "value")
            .then();
}
```

`then()` chờ publisher phía trước hoàn thành, bỏ qua giá trị Boolean và đưa tín hiệu hoàn tất/lỗi về `Mono<Void>`.

## 2. Khởi tạo Spring Data Redis Reactive

Với Spring Boot sử dụng WebFlux, dependency thường gặp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
```

Nếu ứng dụng đã có những dependency phù hợp từ module khác, không cần khai báo trùng. Chọn phiên bản Spring Boot/Spring Data Redis đồng bộ với BOM đang dùng; những ví dụ dưới đây minh họa nhóm API phổ biến, không đặt một phiên bản cụ thể làm yêu cầu cố định.

Cấu hình kết nối minh họa trong `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

Trong môi trường production, thay `localhost` bằng địa chỉ Redis tương ứng và cấu hình TLS, xác thực, topology standalone/Sentinel/Cluster theo triển khai thực tế.

Spring Boot có thể cung cấp `ReactiveRedisConnectionFactory`, `ReactiveRedisTemplate` hoặc `ReactiveStringRedisTemplate` khi thỏa điều kiện auto-configuration. Các ví dụ bên dưới ưu tiên `ReactiveStringRedisTemplate` vì **key và value đều là String**, giúp quan sát Redis bằng CLI.

Một service đơn giản:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingRedisService {

    private final ReactiveStringRedisTemplate redis;

    public GreetingRedisService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> writeGreeting(String userId, String greeting) {
        return redis.opsForValue()
                .set("greeting:" + userId, greeting);
    }

    public Mono<String> readGreeting(String userId) {
        return redis.opsForValue()
                .get("greeting:" + userId);
    }
}
```

Nếu chỉ triển khai API reactive, không thay `ReactiveStringRedisTemplate` bằng `StringRedisTemplate` trong cùng service rồi giả định nó vẫn không blocking. Hai template có cách sử dụng và kiểu trả về khác nhau.

## 3. Tổng quan các nhóm Reactive Operations

`ReactiveRedisTemplate<K, V>` cung cấp các nhóm operations theo kiểu dữ liệu Redis. Với `ReactiveStringRedisTemplate`, `K` và `V` thông dụng là `String`.

| Nhóm | API truy cập | Cấu trúc Redis | Trường hợp phổ biến |
|---|---|---|---|
| **Value** | `opsForValue()` | String | Cache đơn giản, counter, token |
| **Hash** | `opsForHash()` | Hash | Field của profile, metadata |
| **List** | `opsForList()` | List | Danh sách có thứ tự, hàng đợi đơn giản |
| **Set** | `opsForSet()` | Set | Membership, tag, quan hệ không trùng |
| **Sorted Set** | `opsForZSet()` | Sorted Set | Leaderboard, ranking, dữ liệu có điểm |
| **Geo** | `opsForGeo()` | Geospatial index dựa trên sorted set | Vị trí và khoảng cách |
| **HyperLogLog** | `opsForHyperLogLog()` | HyperLogLog | Ước lượng cardinality |
| **Stream** | `opsForStream()` | Redis Stream | Nhật ký sự kiện, consumer group |

Tùy nhóm và lệnh, giá trị trả về có thể là `Mono<T>` hoặc `Flux<T>`. Không thể đoán chắc một thao tác trả Boolean, Long hay Flux chỉ từ tên nhóm; phải nhìn hợp đồng của phương thức đang gọi.

Phần này dùng các API quen thuộc trong Spring Data Redis Reactive; kiểu generic cụ thể có thể tùy serializer và phiên bản thư viện.

## 4. Value Operations: String, counter và cache

Nhóm `opsForValue()` làm việc với Redis String, bao gồm cả chuỗi văn bản, số nguyên biểu diễn bằng chuỗi và những byte được serializer chuyển đổi.

### 4.1. `SET` và `GET` với TTL

```java
import java.time.Duration;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class OneTimeTokenCache {

    private final ReactiveStringRedisTemplate redis;

    public OneTimeTokenCache(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(String requestId, String tokenHash) {
        return redis.opsForValue().set(
                "otp:" + requestId,
                tokenHash,
                Duration.ofMinutes(2)
        );
    }

    public Mono<String> find(String requestId) {
        return redis.opsForValue()
                .get("otp:" + requestId);
    }
}
```

`set(key, value, Duration)` giúp ghi dữ liệu kèm TTL ngay trong thao tác Redis tương ứng. Điều này tốt hơn kiểu `set(...)` rồi gọi `expire(...)` ở hai bước khi nghiệp vụ yêu cầu key vừa tạo phải có TTL.

`GET` trả publisher một giá trị; nếu key thiếu, `Mono` thường kết thúc rỗng. Lệnh Redis lỗi thì publisher phát `onError`, không phải rỗng.

### 4.2. Bộ đếm nguyên tử bằng `increment`

Một bộ đếm lượt xem:

```java
public Mono<Long> increaseViews(String articleId) {
    return redis.opsForValue()
            .increment("views:article:" + articleId);
}
```

Redis thực hiện `INCR` như một lệnh nguyên tử đối với các client khác trên server tương ứng. Tránh thay bằng một chuỗi `GET` → parse → `SET(value + 1)` ở phía Java, vì các request đồng thời có thể cùng đọc một giá trị cũ rồi ghi đè.

Lưu ý:

- `INCR` không tự đặt TTL cho key.
- Gọi `INCR` rồi `EXPIRE` ở hai publisher khác nhau **không trở thành một transaction** chỉ vì dùng `flatMap`.
- Nếu yêu cầu “khởi tạo counter và TTL nguyên tử”, cần lệnh/cơ chế phù hợp, chẳng hạn Lua/Redis Function hoặc một thiết kế đảm bảo khác.
- Redis String chứa nội dung không phải số hợp lệ khiến lệnh tăng bị lỗi, phát `onError`.

### 4.3. Lấy giá trị dự phòng với `switchIfEmpty`

```java
public Mono<String> readTheme(String userId) {
    String key = "theme:" + userId;

    return redis.opsForValue()
            .get(key)
            .switchIfEmpty(Mono.just("light"));
}
```

Ví dụ trả `"light"` nếu key chưa tồn tại. Nếu việc đọc database cũng reactive, dùng `Mono.defer` để chỉ gọi nguồn dữ liệu khi cache miss:

```java
public Mono<String> findTheme(String userId) {
    String key = "theme:" + userId;

    return redis.opsForValue()
            .get(key)
            .switchIfEmpty(
                Mono.defer(() -> loadThemeFromDatabase(userId))
            );
}

// Đây là phương thức của ứng dụng, phải triển khai bằng
// nguồn dữ liệu reactive thực tế.
private Mono<String> loadThemeFromDatabase(String userId) {
    return reactivePreferenceStore.findTheme(userId);
}
```

`Mono.defer` hữu ích vì phần truy vấn nguồn dữ liệu chỉ được tạo/chạy khi cache trả rỗng, thay vì thực hiện công việc eager ngoài publisher. Một `Mono` được tạo từ nguồn reactive lạnh thường cũng lazy, nhưng `defer` làm rõ ranh giới fallback và các tính toán xây dựng publisher.

## 5. Hash Operations: lưu nhiều field dưới một key

Redis Hash phù hợp khi một đối tượng có nhiều thuộc tính nhỏ cần cập nhật hoặc đọc theo field.

Ví dụ dữ liệu:

```redis
HSET profile:u42 name "An" city "Da Nang" status "ACTIVE"
HGET profile:u42 name
HGETALL profile:u42
```

Với reactive template, nhóm tương ứng là `opsForHash()`.

### 5.1. Cấu hình Hash operations kiểu String

```java
import java.util.Map;

import org.springframework.data.redis.core.ReactiveHashOperations;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class ReactiveProfileStore {

    private final ReactiveHashOperations<String, String, String> hashOps;

    public ReactiveProfileStore(ReactiveStringRedisTemplate redis) {
        this.hashOps = redis.opsForHash();
    }

    public Mono<Boolean> setStatus(String userId, String status) {
        return hashOps.put(
                "profile:" + userId,
                "status",
                status
        );
    }

    public Mono<String> getStatus(String userId) {
        return hashOps.get(
                "profile:" + userId,
                "status"
        );
    }

    public Mono<Map<String, String>> readAll(String userId) {
        return hashOps.entries("profile:" + userId)
                .collectMap(
                    Map.Entry::getKey,
                    Map.Entry::getValue
                );
    }
}
```

`hashOps.get(...)` trả một `Mono` chứa giá trị field nếu tồn tại. `entries(...)` trả nhiều cặp field/value bằng `Flux`; `collectMap` gom chúng vào một `Mono<Map<...>>`.

Với những Hash có số field rất lớn, `entries().collectMap(...)` tạo map trong bộ nhớ JVM. Không dùng một cách vô thức cho Hash không giới hạn kích thước.

### 5.2. Hash field không phải key Redis độc lập

```text
Redis key: profile:u42
  ├── name   = An
  ├── city   = Da Nang
  └── status = ACTIVE
```

Redis TTL thường được đặt trên **key `profile:u42`**, không phải từng field Hash trong mô hình thông thường. Nếu mỗi field cần hạn sử dụng khác nhau, cần xem kỹ khả năng của phiên bản Redis và Spring Data đang dùng, hoặc chọn mô hình các key riêng phù hợp.

Không nên tưởng:

```java
hashOps.put("profile:u42", "status", "ACTIVE");
```

có nghĩa Redis đã tạo một key riêng mang tên `status`. Nó cập nhật field trong Hash tại key `profile:u42`.

### 5.3. Hash và JSON object khác nhau thế nào?

- **Hash:** phù hợp khi cập nhật/đọc field riêng lẻ, ví dụ thay `status` mà không phải serialize lại toàn bộ object.
- **JSON trong Redis String:** phù hợp khi đọc/ghi toàn bộ object bằng một payload; cần serialize/deserialize toàn bộ object theo policy ứng dụng.

Với Hash, tên field và value cần serializer phù hợp. Với JSON string, schema/version của payload cần được kiểm soát. Không có cách nào tự động thay thế hoàn toàn cách còn lại.

## 6. List Operations: thứ tự và thao tác đầu/cuối

Redis List lưu các phần tử theo thứ tự. Nhóm Reactive List Operations có thể dùng để thêm phần tử vào đầu/cuối và đọc một khoảng phần tử.

Ví dụ:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class RecentActivityStore {

    private final ReactiveStringRedisTemplate redis;

    public RecentActivityStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> add(String userId, String activityId) {
        return redis.opsForList()
                .leftPush("recent:activity:" + userId, activityId);
    }

    public Flux<String> recent(String userId) {
        return redis.opsForList()
                .range("recent:activity:" + userId, 0, 19);
    }

    public Mono<String> takeLatest(String userId) {
        return redis.opsForList()
                .leftPop("recent:activity:" + userId);
    }
}
```

Ý nghĩa:

- `leftPush`: thêm phần tử vào đầu List.
- `range(key, 0, 19)`: đọc tối đa 20 phần tử đầu theo thứ tự List.
- `leftPop`: lấy và loại bỏ phần tử đầu; đây là thao tác thay đổi dữ liệu Redis.

Với Redis CLI, có thể quan sát:

```redis
LPUSH recent:activity:u42 a1
LPUSH recent:activity:u42 a2
LRANGE recent:activity:u42 0 19
LPOP recent:activity:u42
```

### 6.1. Reactive List có thay thế Redis Streams cho hàng đợi công việc không?

List có thể làm nền tảng cho một hàng đợi đơn giản, nhưng một `leftPop`/`rightPop` **lấy phần tử ra khỏi List**. Nếu worker nhận phần tử rồi crash trước khi xử lý xong, ứng dụng cần thiết kế riêng cơ chế recovery.

Redis Streams với consumer group hỗ trợ tracking pending và ACK rõ ràng hơn cho nhu cầu xử lý message có thể replay. Khi công việc không được phép mất, không nên chỉ dựa vào một `pop` không kèm cơ chế lưu trạng thái hoặc chuyển giao nguyên tử phù hợp.

### 6.2. Lưu ý khi đọc List lớn

`range(key, 0, -1)` có thể đọc toàn bộ List rồi tạo rất nhiều phần tử đi qua `Flux`. Reactor `Flux` không biến một lệnh Redis đã trả toàn bộ tập dữ liệu thành truy vấn phân trang ở server. Cần giới hạn khoảng đọc (`0..19`, `20..39`...) khi List có thể tăng lớn.

## 7. Set Operations: membership và tập phần tử không trùng

Redis Set hữu ích khi chỉ cần biết **một phần tử có thuộc nhóm hay không**, không quan tâm thứ tự.

Ví dụ lưu các tag của một bài viết:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ArticleTagStore {

    private final ReactiveStringRedisTemplate redis;

    public ArticleTagStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> addTags(String articleId, String... tags) {
        return redis.opsForSet()
                .add("tags:article:" + articleId, tags);
    }

    public Mono<Boolean> hasTag(String articleId, String tag) {
        return redis.opsForSet()
                .isMember("tags:article:" + articleId, tag);
    }

    public Flux<String> tags(String articleId) {
        return redis.opsForSet()
                .members("tags:article:" + articleId);
    }
}
```

Một Redis Set không lưu phần tử trùng như List. Lời gọi `add(...)` thường trả số phần tử **mới** được thêm, không phải tổng số tham số đầu vào.

### 7.1. Không dùng Set khi cần thứ tự

`members(...)` trả `Flux`, nhưng thứ tự phần tử không phải thứ tự nghiệp vụ ổn định. Đừng lấy phần tử đầu từ `Flux` rồi coi đó là “tag được thêm đầu tiên”.

Nếu thứ tự thời gian hoặc điểm số là yêu cầu quan trọng, cân nhắc List hoặc Sorted Set tùy nghiệp vụ.

### 7.2. Membership hiệu quả hơn tải cả Set

Một cách không phù hợp:

```java
return redis.opsForSet().members("tags:article:" + articleId)
        .any(tag::equals);
```

Nó có thể khiến phía ứng dụng phải xét nhiều phần tử. Nếu chỉ cần hỏi phần tử có tồn tại, sử dụng:

```java
return redis.opsForSet()
        .isMember("tags:article:" + articleId, tag);
```

Như vậy phép kiểm tra thuộc tập được thực hiện bằng thao tác Redis thích hợp, không yêu cầu tải toàn bộ Set về để tìm trong Java.

## 8. Sorted Set Operations: xếp hạng bằng score

Redis Sorted Set (ZSet) lưu phần tử kèm **score**, hỗ trợ sắp xếp và truy vấn theo vị trí/range.

Bài toán: leaderboard người dùng.

```redis
ZADD leaderboard:week:46 120 user:42
ZADD leaderboard:week:46 350 user:99
ZADD leaderboard:week:46 270 user:17
ZREVRANGE leaderboard:week:46 0 2
```

Với Reactive Operations:

```java
import org.springframework.data.domain.Range;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveLeaderboard {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveLeaderboard(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> setScore(
            String boardKey,
            String userId,
            double score
    ) {
        return redis.opsForZSet()
                .add(boardKey, userId, score);
    }

    public Flux<String> topTen(String boardKey) {
        return redis.opsForZSet()
                .reverseRange(boardKey, Range.closed(0L, 9L));
    }
}
```

Trong API Reactive ZSet, `Range<Long>` thể hiện khoảng **thứ hạng/vị trí** (index range), khác với truy vấn theo khoảng score. Cần phân biệt `Range<Long>` cho vị trí và `Range<Double>`/kiểu tương ứng khi dùng các phương thức `rangeByScore` trong phiên bản Spring Data cụ thể.

Nếu muốn lấy score đi cùng phần tử, có các phương thức thuộc nhóm “with scores”, trả những bản ghi chứa giá trị và score; hãy chọn đúng API thay vì gọi `reverseRange` rồi đoán rằng nó đã trả score.

### 8.1. Khi nào chọn ZSet thay vì Set?

| Nhu cầu | Cấu trúc thích hợp |
|---|---|
| Kiểm tra tag có tồn tại không | Set |
| Liệt kê các thành viên không trùng, không yêu cầu thứ tự | Set |
| Xếp hạng theo điểm | Sorted Set |
| Lấy top N | Sorted Set |
| Lưu danh sách theo thứ tự chèn đầu/cuối | List |
| Xử lý dòng sự kiện cần ID/consumer group | Stream |

Sorted Set vẫn có thể tăng kích thước rất lớn. Nên giới hạn top N và chính sách xóa thành viên cũ khi điểm không còn hữu ích, thay vì luôn đọc toàn bộ leaderboard.

## 9. Geo Operations: tọa độ và tìm kiếm theo vị trí

Redis cung cấp các lệnh geospatial (dữ liệu tọa độ được lưu qua cấu trúc tương thích Sorted Set), và Spring Data Redis Reactive có nhóm `opsForGeo()`.

Ví dụ lưu vị trí:

```java
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class DriverLocationStore {

    private final ReactiveStringRedisTemplate redis;

    public DriverLocationStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> updateLocation(
            String driverId,
            double longitude,
            double latitude
    ) {
        return redis.opsForGeo().add(
                "drivers:geo",
                new Point(longitude, latitude),
                driverId
        );
    }
}
```

Điều cần nhớ:

- `Point` được truyền theo thứ tự **longitude, latitude**.
- Tọa độ phải thuộc phạm vi Redis GEO hỗ trợ và được chuẩn hóa trước khi lưu.
- Nếu ghi vị trí thường xuyên, cần quyết định dữ liệu cũ được xóa/expire thế nào và làm sao phân biệt tài xế đang online với vị trí đã lỗi thời.
- Tìm trong bán kính có thể trả nhiều kết quả; cần giới hạn count/sắp xếp nếu chỉ muốn một số tài xế gần nhất.
- Redis GEO không tự giải quyết kiểm soát quyền truy cập vào dữ liệu vị trí cá nhân.

Ví dụ đọc khoảng cách giữa hai thành viên đã có trong cùng Geo key:

```java
Mono<org.springframework.data.geo.Distance> distance =
        redis.opsForGeo()
                .distance("drivers:geo", "driver:42", "driver:99");
```

Nếu thành viên không tồn tại, kết quả có thể rỗng theo API. Không diễn giải một khoảng cách không có dữ liệu thành khoảng cách `0` nếu nghiệp vụ cần phân biệt “đứng cùng vị trí” với “thiếu vị trí”.

Các API radius/search cụ thể có thể phụ thuộc phiên bản Redis và Spring Data; chọn overload phù hợp với `Distance`, `Circle`, `GeoResults` và kiểu kết quả cần nhận.

## 10. HyperLogLog Operations: ước lượng số phần tử duy nhất

HyperLogLog (HLL) hữu ích khi muốn **ước lượng cardinality**, ví dụ số người truy cập duy nhất trong ngày, mà không lưu từng user ID trong một Redis Set lớn.

Redis CLI:

```redis
PFADD visitors:2026-11-13 u42 u99 u17
PFCOUNT visitors:2026-11-13
```

Reactive API:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class UniqueVisitorCounter {

    private final ReactiveStringRedisTemplate redis;

    public UniqueVisitorCounter(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> recordVisitor(String day, String userId) {
        return redis.opsForHyperLogLog()
                .add("visitors:" + day, userId);
    }

    public Mono<Long> estimatedVisitors(String day) {
        return redis.opsForHyperLogLog()
                .size("visitors:" + day);
    }
}
```

Về mặt ngữ nghĩa:

- `add(...)` cập nhật cấu trúc HLL và trả kết quả theo hợp đồng API.
- `size(...)` đưa ra **ước lượng**, không phải bộ đếm chính xác tuyệt đối.
- HyperLogLog phù hợp với phân tích số lượng unique ở quy mô lớn, **không thích hợp** để trả lời “user X có thuộc tập này hay không?”.
- Nếu bắt buộc biết đúng từng thành viên hoặc yêu cầu thống kê chính xác, nên xem Redis Set hoặc nguồn dữ liệu khác.

Không nên sử dụng HLL để kiểm soát quyền, chống trùng đơn hàng hoặc bất kỳ bất biến nghiệp vụ nào đòi hỏi độ chính xác tuyệt đối về membership.

## 11. Stream Operations: bản ghi có ID và consumer group

Redis Stream dùng để lưu sự kiện có thứ tự ID, có thể đọc lại theo vị trí đã biết và hỗ trợ consumer group.

Một ví dụ gửi event:

```redis
XADD stream:orders * type CREATED orderId o-42
```

Spring Data Redis Reactive có nhóm `opsForStream()` để thao tác Stream. Dạng Java minh họa:

```java
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

public class OrderEventWriter {

    private final ReactiveStringRedisTemplate redis;

    public OrderEventWriter(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<RecordId> publishCreated(String orderId) {
        MapRecord<String, String, String> record =
                StreamRecords.newRecord()
                        .in("stream:orders")
                        .ofMap(Map.of(
                                "type", "CREATED",
                                "orderId", orderId
                        ));

        return redis.opsForStream().add(record);
    }
}
```

`RecordId` xác định vị trí event được thêm. Nếu producer cần tính idempotent, không nên coi mỗi lần retry `XADD` là thao tác không tạo duplicate: với `*`, Redis có thể cấp một ID mới cho cùng event nghiệp vụ.

### 11.1. Đọc một lần từ một offset

```java
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import reactor.core.publisher.Flux;

public Flux<?> readExisting() {
    return redis.opsForStream()
            .read(
                StreamOffset.create(
                    "stream:orders",
                    ReadOffset.from("0-0")
                )
            );
}
```

Ví dụ `Flux<?>` chỉ nhằm nhấn mạnh loại publisher khi minh họa API. Trong service thực tế, nên khai báo kiểu `MapRecord<K, HK, HV>` hoặc record phù hợp với serializer và overload cụ thể của `opsForStream().read(...)`.

`ReadOffset.from("0-0")` đọc các entry **có ID lớn hơn `0-0`** còn nằm trong stream. Nó không tự tạo vòng lặp poll vô hạn, không tự quản lý checkpoint và không đảm bảo các entry bị trim vẫn đọc được.

### 11.2. `ReadOffset.latest()` và `lastConsumed()` không tương đương

- `latest()` được dùng khi muốn đọc từ cuối stream ở thời điểm đọc, thường tương ứng `$` với `XREAD`; sử dụng lặp lại mà không giữ ID đã xử lý có thể **bỏ qua các entry đến giữa các đợt poll**.
- `from(id)` đọc sau một ID cụ thể; thích hợp khi có checkpoint.
- `lastConsumed()` thường gắn với **consumer group** và ngữ nghĩa nhận các entry chưa từng được group giao, tương ứng `>` trong `XREADGROUP`.

Với consumer group, phải thiết kế **ACK**, quản lý pending entries, reclaim và retention. `Flux` ở tầng Java không tự bảo đảm message đã được xử lý đúng nghiệp vụ hay được ACK trên Redis.

### 11.3. Redis Streams không đồng nghĩa reactive application luôn an toàn

Dù dùng `Flux<MapRecord<...>>`, vẫn cần:

- Checkpoint hoặc consumer group bắt đầu ở offset đúng.
- Không ACK trước khi side effect quan trọng hoàn thành.
- Idempotency khi message có thể được giao lại.
- Cơ chế reclaim pending nếu consumer chết.
- Giới hạn số message xử lý đồng thời và thời gian retry.
- Retention đủ dài để không trim dữ liệu chưa xử lý.

Chọn `opsForStream()` vì cấu trúc dữ liệu và delivery semantics của Stream, không chỉ vì method trả `Flux`.

## 12. Tổng hợp những kiểu trả về của các nhóm operations

Một điểm gây lỗi phổ biến là nhầm `Mono` với `Flux` hoặc hiểu giá trị rỗng sai.

| Thao tác | Kiểu publisher thường gặp | Ý nghĩa |
|---|---|---|
| Value `get` | `Mono<V>` | 0 hoặc 1 value; key thiếu thì rỗng |
| Value `set` | `Mono<Boolean>` | Một kết quả lệnh ghi |
| Value `increment` | `Mono<Long>` | Giá trị số sau khi tăng |
| Hash `get` | `Mono<HV>` | 0 hoặc 1 field value |
| Hash `entries` | `Flux<Map.Entry<HK, HV>>` | Nhiều field/value |
| List `leftPush` | `Mono<Long>` | Kích thước/giá trị kết quả theo lệnh |
| List `range` | `Flux<V>` | Nhiều phần tử List |
| Set `isMember` | `Mono<Boolean>` | Một câu trả lời membership |
| Set `members` | `Flux<V>` | Nhiều thành viên, không bảo đảm thứ tự |
| ZSet `reverseRange` | `Flux<V>` | Dữ liệu theo khoảng thứ hạng |
| Geo `distance` | `Mono<Distance>` | Khoảng cách nếu đủ dữ liệu |
| HyperLogLog `size` | `Mono<Long>` | Ước lượng cardinality |
| Stream `add` | `Mono<RecordId>` | ID entry vừa tạo |
| Stream `read` | `Flux<...Record...>` | Các entry đọc được |

Lưu ý: một số thao tác Redis có thể trả kết quả Boolean hoặc số theo kiểu khác tùy phiên bản API. Bảng trình bày các nhóm và kiểu phổ biến, không thay thế việc nhìn chữ ký của overload thực tế trong dự án.

## 13. Kết hợp operations bằng Reactor

Reactive API phát huy tác dụng khi các thao tác được **nối thành một pipeline** thay vì được thực thi rời rạc rồi bỏ qua kết quả.

### 13.1. Nối bước phụ thuộc bằng `flatMap`

Bài toán: lấy ID nhóm của người dùng, sau đó đọc tập thành viên của nhóm đó.

```java
public Flux<String> membersOfUsersGroup(String userId) {
    return redis.opsForValue()
            .get("user:" + userId + ":group-id")
            .flatMapMany(groupId ->
                redis.opsForSet().members("group:" + groupId + ":members")
            );
}
```

Ở đây:

1. `GET` group ID là `Mono<String>`.
2. `flatMapMany` biến kết quả group ID thành một `Flux<String>` của các thành viên.
3. Nếu group ID không có trong Redis, `Mono` rỗng và không thực hiện bước đọc Set.
4. Nếu một bước lỗi, tín hiệu lỗi đi tiếp trừ khi ứng dụng có chính sách recovery rõ ràng.

Không viết:

```java
String groupId =
        redis.opsForValue().get("user:" + userId + ":group-id").block();
```

rồi dùng `groupId` để đọc tiếp trong WebFlux event-loop. Nó chặn thread chờ Redis, có thể gây giảm throughput hoặc lỗi runtime khi gọi `.block()` trên thread không cho phép blocking.

### 13.2. Chạy độc lập và ghép kết quả bằng `Mono.zip`

Nếu cần đọc hai key **độc lập**:

```java
public Mono<UserDashboard> dashboard(String userId) {
    Mono<String> theme = redis.opsForValue()
            .get("theme:" + userId)
            .defaultIfEmpty("light");

    Mono<Long> views = redis.opsForValue()
            .get("views:user:" + userId)
            .map(Long::parseLong)
            .defaultIfEmpty(0L);

    return Mono.zip(theme, views)
            .map(tuple -> new UserDashboard(
                    userId,
                    tuple.getT1(),
                    tuple.getT2()
            ));
}

public record UserDashboard(
        String userId,
        String theme,
        long views
) {}
```

`zip` có thể đăng ký các nguồn độc lập trong cùng luồng, nhưng **không tạo snapshot nguyên tử**: một client khác vẫn có thể cập nhật `theme` giữa các lần đọc.

Một lưu ý quan trọng: nếu một trong các `Mono` kết thúc rỗng và không có `defaultIfEmpty`, `Mono.zip` có thể hoàn thành rỗng mà không tạo tuple. Khi thiết kế response nhiều trường, cần quyết định rõ cách biểu diễn cache miss.

### 13.3. `then` và `thenReturn` khi chỉ cần kết quả bước sau

Muốn ghi cache rồi trả lại DTO:

```java
public Mono<ProductDto> saveCache(
        String key,
        ProductDto product
) {
    String json = serializeProduct(product);

    return redis.opsForValue()
            .set(key, json)
            .thenReturn(product);
}
```

`thenReturn(product)` chỉ phát `product` **khi publisher SET hoàn tất bình thường**. Nó không biến kết quả Boolean `false` thành exception; nếu lệnh ghi có ngữ nghĩa Boolean cần kiểm tra, hãy xử lý nó rõ ràng thay vì bỏ qua.

Nếu cache chỉ là tối ưu, có thể cho phép bỏ qua lỗi cache theo chính sách, nhưng phải giới hạn đúng vùng catch. Nếu yêu cầu cache phải tồn tại để duy trì invariant, không nên nuốt lỗi ghi.

## 14. Ví dụ cache-aside reactive với nguồn dữ liệu cũng reactive

Giả sử service đọc sản phẩm theo ID. Redis lưu JSON và database là nguồn sự thật.

Interface nguồn:

```java
public interface ReactiveProductStore {
    Mono<ProductDto> findById(String id);
}
```

DTO:

```java
public record ProductDto(String id, String name) {}
```

Service:

```java
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.core.JsonProcessingException;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProductCacheService {

    private static final Duration TTL = Duration.ofMinutes(5);

    private final ReactiveStringRedisTemplate redis;
    private final ReactiveProductStore store;
    private final ObjectMapper mapper;

    public ProductCacheService(
            ReactiveStringRedisTemplate redis,
            ReactiveProductStore store,
            ObjectMapper mapper
    ) {
        this.redis = redis;
        this.store = store;
        this.mapper = mapper;
    }

    public Mono<ProductDto> findById(String productId) {
        String key = "cache:product:v1:" + productId;

        Mono<ProductDto> fromCache = redis.opsForValue()
                .get(key)
                .map(this::decode);

        Mono<ProductDto> fromSource = Mono.defer(() ->
                store.findById(productId)
                    .flatMap(product ->
                        redis.opsForValue()
                            .set(key, encode(product), TTL)
                            .thenReturn(product)
                    )
        );

        return fromCache.switchIfEmpty(fromSource);
    }

    private String encode(ProductDto product) {
        try {
            return mapper.writeValueAsString(product);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot serialize product", ex
            );
        }
    }

    private ProductDto decode(String json) {
        try {
            return mapper.readValue(json, ProductDto.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                "Invalid cached product JSON", ex
            );
        }
    }
}
```

Luồng:

```text
GET Redis key
    |
    +-- HIT  -> decode JSON -> Mono<ProductDto>
    |
    +-- MISS -> ReactiveProductStore.findById()
                    |
                    +-- DB có dữ liệu
                    |      |
                    |      +-- SET Redis EX TTL
                    |      +-- trả ProductDto
                    |
                    +-- DB không có -> Mono.empty()
```

### 14.1. Những giới hạn của ví dụ cache-aside

- Nếu nguồn DB không tìm thấy, service trả `Mono.empty()` mà **không negative-cache** kết quả; có thể bổ sung sentinel/TTL ngắn nếu cần.
- Nếu Redis đọc lỗi, `switchIfEmpty` **không chạy** vì Redis phát `onError`, không phải `onComplete` rỗng.
- Nếu Redis ghi lỗi sau khi DB đã trả sản phẩm, code hiện tại sẽ phát lỗi thay vì trả sản phẩm. Với cache không bắt buộc, có thể xử lý riêng lỗi ở bước ghi để vẫn phục vụ từ DB.
- Nếu nhiều request đồng thời miss, chúng có thể cùng gọi DB; reactive không tự chống cache stampede.
- JSON serialization trong ví dụ là thao tác CPU tại JVM, không phải I/O Redis. Với payload lớn cần quản lý CPU/heap và phiên bản schema.
- Nếu product cập nhật, service ghi cần invalidate cache hoặc cập nhật entry theo chiến lược nhất quán phù hợp.

### 14.2. Cho phép cache lỗi nhưng vẫn đọc nguồn dữ liệu

Nếu chính sách nghiệp vụ coi Redis là lớp tối ưu có thể bỏ qua khi lỗi, có thể tách logic fallback:

```java
public Mono<ProductDto> findByIdAllowCacheFailure(String id) {
    String key = "cache:product:v1:" + id;

    Mono<ProductDto> fromSource = Mono.defer(() ->
        store.findById(id)
            .flatMap(product ->
                redis.opsForValue()
                    .set(key, encode(product), Duration.ofMinutes(5))
                    .onErrorResume(cacheWriteError -> {
                        // Ghi metric/log về cacheWriteError.
                        return Mono.just(false);
                    })
                    .thenReturn(product)
            )
    );

    return redis.opsForValue()
            .get(key)
            .map(this::decode)
            .onErrorResume(cacheReadError -> {
                // Ghi metric/log; lỗi đọc cache không phải DB not found.
                return Mono.empty();
            })
            .switchIfEmpty(fromSource);
}
```

Ở đây:

- `onErrorResume` ở **bước đọc Redis** biến lỗi cache đọc thành cache miss theo chính sách fail-open.
- `onErrorResume` ở **bước ghi Redis** cho phép trả product dù Redis không lưu được.
- Lỗi từ `store.findById(id)` không bị nuốt bởi hai handler lỗi cache, vì vị trí xử lý được giới hạn rõ.

Không nên đặt một `.onErrorResume(ex -> Mono.empty())` bao quanh **toàn bộ** pipeline nếu điều đó khiến lỗi DB, lỗi parse, lỗi kiểm tra quyền truy cập cũng bị xem như “không tìm thấy”.

## 15. Reactive serialization: template chuỗi và template object

`ReactiveStringRedisTemplate` tiện cho chuỗi, counter, JSON text. Khi ứng dụng muốn Redis trả trực tiếp DTO, có thể tạo `ReactiveRedisTemplate<String, ProductDto>` với serializer cấu hình.

Ví dụ tương thích với kiểu API Spring Data Redis/Jackson 2 phổ biến:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductReactiveRedisConfiguration {

    @Bean
    public ReactiveRedisTemplate<String, ProductDto> productRedisTemplate(
            ReactiveRedisConnectionFactory connectionFactory
    ) {
        var keySerializer = new StringRedisSerializer();
        var valueSerializer =
                new Jackson2JsonRedisSerializer<>(ProductDto.class);

        RedisSerializationContext<String, ProductDto> context =
                RedisSerializationContext
                    .<String, ProductDto>newSerializationContext(
                        keySerializer
                    )
                    .value(valueSerializer)
                    .build();

        return new ReactiveRedisTemplate<>(
                connectionFactory,
                context
        );
    }
}
```

Các phiên bản Spring Data Redis và Jackson khác nhau có thể cung cấp serializer hoặc builder khác; khi nâng cấp lên stack Jackson mới cần chọn API tương thích. Ở mọi phiên bản, nguyên tắc không đổi: **serializer của key, value, hash key và hash value phải nhất quán với cách dữ liệu đã được ghi**.

Dùng template object:

```java
public Mono<Boolean> save(ProductDto product) {
    return productRedisTemplate.opsForValue()
            .set("product:object:" + product.id(), product);
}

public Mono<ProductDto> find(String productId) {
    return productRedisTemplate.opsForValue()
            .get("product:object:" + productId);
}
```

### 15.1. Mỗi template có quy ước byte riêng

Nếu cùng key:

```text
product:object:p42
```

được ghi bởi một template với serializer JSON nhưng đọc bởi một template dùng String serializer hoặc JDK serializer, ứng dụng có thể thấy lỗi deserialize hoặc dữ liệu khó hiểu.

Đừng cho rằng key nhìn giống nhau trong Java là đủ để hai template hiểu cùng value. Redis lưu byte; serializer quy định ý nghĩa của chúng.

### 15.2. Cẩn thận khi dùng JSON có metadata kiểu

Một số generic JSON serializer lưu thông tin type trong JSON. Khi dữ liệu đến từ nguồn không đáng tin, deserialize polymorphic type cần kiểm soát các kiểu cho phép và quyền đọc/ghi Redis. Với DTO có cấu trúc rõ, serializer gắn kiểu cụ thể thường dễ quản lý hơn.

Nếu schema DTO thay đổi giữa hai phiên bản ứng dụng đang cùng chạy, cần có chiến lược tương thích ngược, version namespace hoặc xóa/tái tạo cache an toàn.

## 16. Reactor composition không tự tạo transaction Redis

Giả sử code:

```java
return redis.opsForValue().set("order:42:status", "PAID")
        .then(redis.opsForValue().increment("metrics:paid-orders"));
```

Hai lệnh chạy theo thứ tự: bước tăng chỉ được subscribe sau khi bước `set` hoàn tất bình thường.

Nhưng điều đó **không bảo đảm**:

- Cả hai ghi được thực thi nguyên tử.
- Không có lệnh của client khác chen vào giữa.
- Nếu `increment` lỗi, Redis tự rollback `set`.
- Redis và một transaction PostgreSQL đồng bộ commit.

`then`, `flatMap`, `concatMap` là công cụ **điều phối publisher**, không phải lệnh `MULTI`/`EXEC` của Redis.

Nếu nghiệp vụ cần cập nhật nhiều key không bị chen giữa hoặc kiểm tra điều kiện rồi ghi nguyên tử, phải dùng cơ chế Redis phù hợp như Lua/Redis Function hoặc API transaction được hỗ trợ với đúng phạm vi connection. Ngay cả `MULTI`/`EXEC` cũng không có rollback tổng quát cho các lệnh runtime đã thực thi thành công.

### 16.1. Atomic command vẫn là lựa chọn ưu tiên khi đủ dùng

Thay vì:

```java
return redis.opsForValue().get("counter")
        .map(Long::parseLong)
        .flatMap(v ->
            redis.opsForValue().set("counter", Long.toString(v + 1))
        );
```

hãy dùng:

```java
return redis.opsForValue().increment("counter");
```

Lệnh `INCR` giúp tránh lost update mà hai lệnh `GET` + `SET` có thể gặp. *Reactive* không xóa race condition của các phép đọc–sửa–ghi.

## 17. Đồng thời, thứ tự và giới hạn số lời gọi Redis

Khi có danh sách nhiều ID:

```java
List<String> ids = List.of("p1", "p2", "p3");
```

Có thể đọc bằng `Flux`:

```java
public Flux<String> cachedValues(List<String> ids) {
    return Flux.fromIterable(ids)
            .flatMap(id ->
                redis.opsForValue().get("cache:product:" + id)
            );
}
```

Các lời gọi `GET` được tạo từ các item đầu vào. Tuy nhiên, `flatMap` cho phép kết quả đến **không nhất thiết theo thứ tự IDs**, và mặc định có thể mở một số lượng thao tác đồng thời đáng kể.

### 17.1. Giới hạn concurrency

```java
public Flux<String> cachedValuesBounded(List<String> ids) {
    int concurrency = 16;

    return Flux.fromIterable(ids)
            .flatMap(
                id -> redis.opsForValue()
                        .get("cache:product:" + id),
                concurrency
            );
}
```

Giới hạn `16` chỉ là ví dụ. Chọn giới hạn dựa trên latency Redis, kích thước dữ liệu, tài nguyên connection và tốc độ xử lý của ứng dụng.

### 17.2. Khi cần giữ thứ tự đầu vào

Nếu muốn luồng đầu ra theo thứ tự ID:

```java
public Flux<String> cachedValuesOrdered(List<String> ids) {
    return Flux.fromIterable(ids)
            .concatMap(id ->
                redis.opsForValue()
                    .get("cache:product:" + id)
                    .defaultIfEmpty("NOT_CACHED")
            );
}
```

`concatMap` xử lý các publisher con theo thứ tự, hữu ích khi cần thứ tự rõ ràng nhưng giảm concurrency.

Một lựa chọn khác là `flatMapSequential`, cho phép thực thi một số publisher đồng thời rồi phát kết quả theo thứ tự nguồn; cần cân nhắc khả năng buffer kết quả trong thời gian đợi publisher trước hoàn thành.

**Lưu ý:** khi một `Mono` rỗng, `flatMap`/`concatMap` không phát item tương ứng. Nếu phải giữ liên kết `id -> kết quả`, nên trả một wrapper chứa cả ID và trạng thái miss thay vì chỉ trả `Flux<String>`.

Ví dụ:

```java
public record CacheLookup(String id, String value, boolean found) {}

public Flux<CacheLookup> lookupAll(List<String> ids) {
    return Flux.fromIterable(ids)
            .flatMapSequential(
                id -> redis.opsForValue()
                    .get("cache:product:" + id)
                    .map(value -> new CacheLookup(id, value, true))
                    .defaultIfEmpty(new CacheLookup(id, "", false)),
                16
            );
}
```

Ở đây `""` chỉ là giá trị placeholder trong record khi `found=false`; không được dùng nó để suy ra rằng một value hợp lệ luôn khác chuỗi rỗng.

### 17.3. `Flux` không phải Redis pipeline tự động

Nhiều thao tác `GET` được khởi tạo bởi `flatMap` có thể được driver sắp lịch hiệu quả, nhưng **không được mặc định coi đây là một Redis transaction** hoặc một lệnh `MGET`.

Nếu tất cả là cùng loại thao tác và Redis có lệnh multi-key phù hợp, có thể cân nhắc API tương ứng để giảm round trip, đồng thời xem giới hạn Redis Cluster hash slot và kiểu kết quả.

Điều cần tối ưu là **tổng thời gian và tài nguyên thực tế**, không chỉ số lượng publisher được tạo ra.

## 18. Backpressure trong Reactor và giới hạn của Redis

Reactor hỗ trợ **backpressure**: subscriber có thể yêu cầu lượng dữ liệu mà nó có khả năng tiêu thụ. Nhưng không nên suy luận rằng `Flux` từ Redis tự động biến mọi command thành một thao tác đọc từng phần chính xác theo số lượng request.

Ví dụ:

```java
redis.opsForSet()
        .members("huge:set")
        .take(20)
```

`take(20)` giới hạn số item đi xuống subscriber. Tuy nhiên, tùy lệnh Redis và cách driver thực hiện, thao tác ở server có thể đã lấy một tập dữ liệu lớn trước khi tầng Reactor cắt xuống 20. Với Set lớn, chọn lệnh quét/phân trang phù hợp hơn thay vì luôn gọi `SMEMBERS`.

Tương tự:

```java
redis.opsForList().range("huge:list", 0, -1)
```

có thể yêu cầu toàn bộ List từ Redis. Đổi consumer sang xử lý `Flux` từng item không sửa được chi phí của `LRANGE 0 -1` trên server.

Một số nguyên tắc:

- Dùng `LRANGE` với khoảng nhỏ, ZSet range giới hạn top N.
- Với Hash/Set lớn, cân nhắc scan-based API khi phiên bản Spring Data Redis hỗ trợ và hiểu tính không nhất quán snapshot của SCAN khi dữ liệu thay đổi.
- Giới hạn số request đồng thời bằng `flatMap(..., concurrency)`.
- Tránh `collectList()` hoặc `collectMap()` trên một `Flux` có thể vô hạn hoặc rất lớn.
- Với Stream consumer, cân nhắc batch size, ack/retry, retention và năng lực handler, không chỉ `Flux` demand.

## 19. Timeout, lỗi và fallback

Mỗi publisher Redis có thể kết thúc theo ba hướng chính:

```text
onNext(value) + onComplete -> có kết quả
onComplete                 -> không có giá trị
onError(error)             -> lỗi
```

Đây là ba trạng thái khác nhau.

### 19.1. Phân biệt thiếu key với lỗi Redis

```java
Mono<String> value = redis.opsForValue()
        .get("config:feature-x")
        .defaultIfEmpty("OFF");
```

Nếu key không có, trả `"OFF"`. Nếu mất kết nối Redis, vẫn có thể phát lỗi.

Nếu muốn cache lỗi thì dùng fallback:

```java
Mono<String> value = redis.opsForValue()
        .get("config:feature-x")
        .onErrorResume(ex -> {
            // Log/metric rõ ràng: Redis không sẵn sàng.
            return Mono.just("OFF");
        })
        .defaultIfEmpty("OFF");
```

Nhưng **không nên dùng fallback chung** cho dữ liệu kiểm soát bảo mật hoặc những giá trị buộc phải chính xác. Ví dụ không được tự chuyển lỗi đọc quyền truy cập thành “được phép” chỉ để API luôn trả dữ liệu.

### 19.2. Timeout ở phía client

```java
import java.time.Duration;

public Mono<String> readWithTimeout(String key) {
    return redis.opsForValue()
            .get(key)
            .timeout(Duration.ofSeconds(2));
}
```

`timeout` của Reactor đưa ra tín hiệu lỗi nếu publisher không hoàn tất trong khoảng chờ. Nó **không tự chứng minh** Redis server chưa nhận hoặc chưa thực hiện lệnh. Với lệnh có side effect như `INCR`, tự động retry sau timeout có thể làm thay đổi dữ liệu lần hai.

Timeout của Reactor, timeout của Redis client và timeout của network có thể có ngữ nghĩa/hành vi khác nhau; nên cấu hình các giới hạn chờ có chủ đích, không lẫn lộn.

### 19.3. `retryWhen` cần idempotency

Với thao tác đọc:

```java
return redis.opsForValue()
        .get(key)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
        );
```

Đây chỉ là minh họa; trong production nên **lọc đúng loại lỗi tạm thời** và tránh retry lỗi dữ liệu như `WRONGTYPE` hoặc lỗi serialization.

Với thao tác ghi:

```java
redis.opsForValue().increment("payment:counter");
```

không nên retry tự động mà không có cơ chế idempotency, vì lệnh có thể đã tăng thành công trước khi kết nối mất phản hồi.

## 20. Đừng `.subscribe()` thủ công trong service rồi bỏ qua kết quả

Một lỗi phổ biến:

```java
public Mono<ProductDto> findProduct(String id) {
    redis.opsForValue()
        .set("audit:last-product", id)
        .subscribe(); // fire-and-forget

    return productStore.findById(id);
}
```

Vấn đề:

- Service tạo một subscription nằm ngoài publisher trả về.
- Request có thể hoàn tất trước thao tác Redis.
- Lỗi trong subscription riêng có thể không đi qua cơ chế error handling của request.
- Không rõ thứ tự giữa ghi Redis và đọc DB.
- Cancellation của luồng trả về không điều khiển được tác vụ đã tự subscribe.

Nếu ghi audit phải xảy ra trước khi đọc DB:

```java
public Mono<ProductDto> findProduct(String id) {
    return redis.opsForValue()
        .set("audit:last-product", id)
        .then(productStore.findById(id));
}
```

Nếu audit chỉ là best-effort, vẫn cần một cơ chế async có giám sát và handling lỗi rõ ràng thay vì tự subscribe không kiểm soát.

Quy tắc thực tế: **trả publisher hoặc compose publisher**, để tầng gọi/web framework quản lý subscription. Chỉ tự subscribe ở ranh giới đã được thiết kế để quản lý vòng đời, ví dụ một worker/event processor.

## 21. Cảnh giác với `block()`, JPA và I/O không reactive

Ví dụ không thích hợp trong service WebFlux:

```java
public Mono<String> find(String key) {
    String cached = reactiveRedis.opsForValue().get(key).block();

    if (cached != null) {
        return Mono.just(cached);
    }

    return Mono.just(jpaRepository.findById(key).toString());
}
```

Vấn đề:

- `block()` chặn thread đang thực thi, có thể gây lỗi trên event-loop.
- JPA thông thường là API blocking; gọi trực tiếp trong pipeline reactive cũng chặn thread.
- Ghép `Mono.just(...)` bên ngoài không biến một lời gọi DB blocking đã chạy thành non-blocking.

Nếu cần dùng nguồn blocking trong một giai đoạn chuyển đổi kiến trúc, có thể cô lập nó trên scheduler dành cho công việc blocking theo thiết kế Reactor, ví dụ:

```java
Mono<ProductDto> productMono =
        Mono.fromCallable(() -> blockingProductStore.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
```

Đây là **cầu nối tạm thời cho nguồn blocking**, không thay thế R2DBC hoặc một nguồn reactive thực sự. Nếu lưu lượng cao, cần quản lý pool, số tác vụ đồng thời và giới hạn tài nguyên, thay vì đẩy toàn bộ JDBC/JPA lên scheduler không kiểm soát.

Với ứng dụng dùng reactive từ đầu đến cuối, nên kết hợp `ReactiveRedisTemplate` với DB/client reactive tương ứng.

## 22. Lệnh Redis nguyên tử, transaction và script trong mô hình reactive

Chọn đúng nhóm Reactive Operations còn liên quan tới **đảm bảo nghiệp vụ**:

| Nhu cầu | API/chiến lược nên xem |
|---|---|
| Tăng counter | `opsForValue().increment(...)` |
| Thêm thành viên không trùng | `opsForSet().add(...)` |
| Cập nhật một field Hash | `opsForHash().put(...)` |
| Thêm điểm vào leaderboard | `opsForZSet().add(...)` |
| Ghi hai key cùng thứ tự | Reactor `.then(...)` chỉ điều phối thứ tự, chưa phải transaction |
| Kiểm tra số dư rồi trừ | Lua/Redis Function hoặc optimistic concurrency phù hợp |
| Ghi sự kiện cần ACK/replay | `opsForStream()` + consumer group + recovery |
| Đồng bộ Redis và PostgreSQL nguyên tử | Không có từ một Reactive Operation; phải thiết kế ranh giới transaction và cơ chế phục hồi |

Khi thao tác cần nhiều bước đọc–kiểm tra–ghi tại Redis server, có thể sử dụng scripting API của Spring Data Redis nếu phiên bản reactive đang dùng cung cấp overload tương ứng. Dù gọi script thông qua `Flux`/`Mono`, script vẫn có những giới hạn thông thường của Redis Lua: có tính không xen giữa khi thực thi nhưng có thể chặn lệnh khác nếu chạy lâu, và không rollback tổng quát khi script lỗi sau một số ghi.

Reactive transaction management của Spring và Redis transaction là những phạm vi riêng. Không tự suy luận `@Transactional` trên một phương thức trả `Mono` sẽ biến các thao tác Redis thành `MULTI`/`EXEC`, cũng không tự tạo distributed commit với database.

## 23. Ví dụ WebFlux Controller dùng Reactive Operations

Một controller trả publisher trực tiếp:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {

    private final ArticleMetricsService metrics;

    public ArticleController(ArticleMetricsService metrics) {
        this.metrics = metrics;
    }

    @PostMapping("/{id}/views")
    public Mono<ResponseEntity<Long>> increase(
            @PathVariable String id
    ) {
        return metrics.increaseViews(id)
                .map(ResponseEntity::ok);
    }

    @GetMapping("/{id}/views")
    public Mono<ResponseEntity<Long>> current(
            @PathVariable String id
    ) {
        return metrics.currentViews(id)
                .map(ResponseEntity::ok);
    }
}
```

Service:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ArticleMetricsService {

    private final ReactiveStringRedisTemplate redis;

    public ArticleMetricsService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increaseViews(String articleId) {
        return redis.opsForValue()
                .increment("views:article:" + articleId);
    }

    public Mono<Long> currentViews(String articleId) {
        return redis.opsForValue()
                .get("views:article:" + articleId)
                .map(Long::parseLong)
                .defaultIfEmpty(0L);
    }
}
```

Ở đây:

- Controller không gọi `.subscribe()` hay `.block()`.
- WebFlux subscribe khi cần tạo HTTP response.
- Bộ đếm dùng Redis atomic `INCR`.
- `GET` cache miss được xử lý rõ bằng `defaultIfEmpty(0L)`.
- Nếu Redis lỗi, lỗi được phát qua `Mono`; ứng dụng cần xử lý bằng controller advice hoặc chính sách lỗi tương ứng.

Nếu API phải phân biệt “key counter chưa từng tồn tại” với “bộ đếm bằng 0”, không dùng `defaultIfEmpty(0L)` mà không bổ sung trạng thái biểu diễn.

## 24. Kiểm thử Reactive Operations bằng `StepVerifier`

Project Reactor có `reactor-test` và `StepVerifier` để kiểm tra chuỗi tín hiệu của publisher.

Ví dụ một kiểm thử tích hợp chạy với Redis test instance:

```java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class ArticleMetricsServiceTest {

    private final ArticleMetricsService metrics;

    ArticleMetricsServiceTest(ArticleMetricsService metrics) {
        this.metrics = metrics;
    }

    @Test
    void incrementEmitsNewValue() {
        StepVerifier.create(metrics.increaseViews("test-article-1"))
                .expectNextCount(1)
                .verifyComplete();
    }
}
```

Ví dụ trên minh họa API `StepVerifier`; trong một dự án thật, fixture cần inject `ArticleMetricsService` qua Spring test context và chuẩn bị/xóa Redis key trước mỗi test để bảo đảm giá trị có thể dự đoán. Nếu key đã có sẵn, `INCR` vẫn trả một số nhưng giá trị cụ thể sẽ khác.

Ví dụ test hành vi cache miss:

```java
StepVerifier.create(
    reactiveStringRedisTemplate.opsForValue()
        .get("test:missing:key")
)
    .verifyComplete();
```

Điều kiện tiền đề là key này thực sự không tồn tại trong Redis test instance. `verifyComplete()` xác nhận publisher kết thúc rỗng, khác với `expectNext("...")`.

### 24.1. Vì sao không gọi `.block()` trong mọi test?

Một số kiểm thử tích hợp có thể dùng `.block()` trên thread test thích hợp để chuẩn bị dữ liệu, nhưng dùng `StepVerifier` giúp biểu diễn chính xác tín hiệu `onNext`, `onComplete`, `onError` và thời gian xử lý trong mô hình Reactor.

Không nên kiểm thử chỉ bằng việc tạo `Mono` rồi kết thúc test, vì không có subscription nên thao tác Redis có thể chưa bao giờ được thực thi.

### 24.2. Những kịch bản nên có

- `GET` với key có và không tồn tại.
- Lỗi kết nối Redis và behavior fallback.
- Redis value sai định dạng, ví dụ không parse được số.
- Thao tác Hash/List/Set/ZSet với dữ liệu test cô lập.
- TTL thực tế của cache sau ghi.
- Đồng thời nhiều request `INCR` để quan sát tính nguyên tử của lệnh.
- Thứ tự đầu ra với `flatMap`/`concatMap`.
- Luồng Stream có consumer group, ACK/pending và idempotency nếu được dùng.
- Cancellation/timeouts khi phụ thuộc mạng chậm.

Các tình huống cần Redis server thật có thể sử dụng một instance kiểm thử cô lập hoặc Testcontainers theo hạ tầng dự án. Không dùng dữ liệu production làm fixture.

## 25. Quan sát và vận hành ứng dụng Redis Reactive

Để kết luận reactive operations cải thiện throughput, cần quan sát dữ liệu thực tế thay vì chỉ thay kiểu trả về thành `Mono`.

| Chỉ số | Ý nghĩa |
|---|---|
| Redis command latency | Thời gian thao tác Redis theo loại lệnh |
| Request p50/p95/p99 | Độ trễ nhìn từ API/WebFlux |
| Redis server CPU/memory | Xác định giới hạn throughput |
| Network throughput/RTT | Thấy ảnh hưởng của giao tiếp Redis |
| Concurrent Redis operations | Phát hiện overload do `flatMap` fan-out |
| Client connection usage | Kiểm tra connection pool/routing |
| Reactor scheduler blocking | Phát hiện `block()` hoặc thư viện blocking trong event-loop |
| Cache hit/miss | Đánh giá tần suất tránh truy vấn nguồn |
| Serialization errors | Phát hiện dữ liệu không tương thích |
| Redis timeout/retry | Phát hiện mạng chậm, lỗi driver hoặc retry storm |
| Stream lag/pending | Khi dùng consumer group, theo dõi bản ghi chưa xử lý |

Micrometer/observability có thể đo độ trễ của các thao tác Redis và API tùy cấu hình Spring Boot, driver và công cụ tracing. Không nên gắn mỗi user ID hay Redis key duy nhất làm label metric, vì cardinality sẽ tăng quá lớn.

Lưu ý: reactive không xóa giới hạn của Redis server. Một request `SMEMBERS` trên Set cực lớn, script Lua chạy lâu hoặc command đòi xử lý nhiều dữ liệu vẫn có thể làm Redis tăng latency của các lệnh khác.

## 26. Những lỗi phổ biến khi chuyển từ `RedisTemplate` sang Reactive Operations

**“Tạo `Mono` là lệnh đã chạy.”** Không nhất thiết. Publisher thông thường là lazy, cần được subscribe bởi tầng có trách nhiệm.

**“Trong service gọi `.subscribe()` để lệnh chạy nhanh hơn.”** Đây thường là fire-and-forget không kiểm soát, dễ mất lỗi và làm sai thứ tự nghiệp vụ.

**“Dùng `.block()` trong WebFlux để lấy value rồi xử lý Java.”** Nó chặn thread và phá mô hình reactive, có thể gây lỗi trên event-loop.

**“`Mono.empty()` nghĩa là Redis server lỗi.”** Không. Key thiếu/field thiếu có thể trả rỗng; lỗi Redis đi theo `onError`.

**“`defaultIfEmpty` tự xử lý cả timeout.”** Không. Muốn xử lý error cần operator có semantics lỗi như `onErrorResume` và policy phù hợp.

**“`flatMap` bảo đảm kết quả theo thứ tự input.”** Không. Dùng `concatMap` hoặc `flatMapSequential` khi cần thứ tự.

**“`flatMap` với hàng nghìn key là miễn phí vì không chặn thread.”** Không. Redis server, network, client buffers và memory vẫn có giới hạn. Cần concurrency limit.

**“`Flux` từ `SMEMBERS` có backpressure nên Redis chỉ đọc vài phần tử.”** Không được suy luận như vậy. Lệnh nguồn có thể đọc toàn bộ Set, rồi Reactor mới phát từng phần tử.

**“`ReactiveRedisTemplate` tự hiểu mọi JSON object.”** Không. Serializer và schema phải được cấu hình tương ứng.

**“Hash field có TTL riêng giống một Redis key.”** Không đúng với mô hình TTL trên Hash key thông thường; cần xem API/phiên bản nếu có tính năng chuyên biệt.

**“Redis Set luôn có thứ tự ổn định vì trả `Flux`.”** Không. Flux mô tả cách phát dữ liệu, không tạo thứ tự cho Redis Set.

**“HyperLogLog là bộ đếm unique chính xác.”** Không. Nó là cấu trúc ước lượng.

**“Stream `lastConsumed` tự ACK mọi bản ghi.”** Không. Delivery và ACK là hai việc riêng, pending cần recovery.

**“`.then(...)` tạo transaction nguyên tử.”** Không. Nó chỉ nối thứ tự các publisher.

**“Reactive Redis làm được distributed transaction với PostgreSQL.”** Không. Hai hệ thống độc lập cần kiến trúc nhất quán và phục hồi riêng.

## 27. Bảng chọn Reactive Operations theo bài toán

| Bài toán | Nhóm nên chọn | Lưu ý |
|---|---|---|
| Cache chuỗi/cấu hình | Value | TTL, serializer, cache miss |
| Counter và rate metric | Value | Dùng `increment`, không tự `GET`/`SET` |
| Hồ sơ gồm nhiều thuộc tính | Hash | Field-level update, TTL theo key |
| Danh sách hoạt động gần đây | List | Giới hạn `range`, tránh đọc toàn bộ |
| Tag, membership, danh sách ID không trùng | Set | Không có thứ tự |
| Xếp hạng người dùng | Sorted Set | Score, rank, giới hạn top N |
| Vị trí tài xế/kho | Geo | Tọa độ, phạm vi truy vấn, quyền dữ liệu |
| Ước lượng user unique | HyperLogLog | Chấp nhận sai số |
| Event cần replay/consumer group | Stream | ID, offset, ACK, pending, retention |
| Kết hợp hai Redis read độc lập | Reactor `Mono.zip` | Không tạo snapshot nguyên tử |
| Bước B phụ thuộc A | Reactor `flatMap` | Không bảo đảm atomicity nhiều key |
| Nhiều key độc lập | `Flux` + concurrency limit | Tránh fan-out quá lớn |
| Thao tác nhiều bước phải nguyên tử | Redis script/transaction phù hợp | Không chỉ dùng Reactor chain |
| DB blocking trong WebFlux | Cô lập blocking hoặc chuyển nguồn reactive | Tránh chặn event-loop |

Không nhất thiết mọi dữ liệu đều phải lưu Redis theo một kiểu. Chọn cấu trúc gần với phép toán cần thực hiện giúp giảm số lệnh và cải thiện khả năng bảo trì hơn là dùng một Redis String JSON chung cho tất cả trường hợp.

## 28. Quy trình thiết kế một thao tác Redis Reactive

Trước khi viết code, hãy trả lời lần lượt:

1. **Dữ liệu được biểu diễn bằng cấu trúc Redis nào?** String, Hash, List, Set, ZSet, Geo, HyperLogLog hay Stream?
2. **Phép toán Redis native nào diễn đạt yêu cầu chính xác nhất?** `INCR`, `HGET`, `SISMEMBER`, `ZADD`, `XADD`...
3. **Kết quả có tối đa một giá trị hay nhiều giá trị?** Dùng đúng `Mono`/`Flux` và hiểu trường hợp rỗng.
4. **Các thao tác độc lập hay phụ thuộc?** Dùng `zip`, `flatMap`, `then` theo semantics mong muốn.
5. **Có yêu cầu nguyên tử hoặc ordering không?** Nếu có, xem cơ chế Redis và transaction, đừng suy luận từ Reactor operator.
6. **Có cần TTL, serialization hoặc namespace riêng không?** Xác định ngay trong thiết kế key.
7. **Dữ liệu có thể rất lớn không?** Giới hạn range, phân trang/scan phù hợp, tránh collect vô hạn.
8. **Ứng dụng có thể gặp retry, timeout hoặc cancellation không?** Với write, xác định idempotency và trạng thái kết quả không chắc chắn.
9. **Mức concurrency dự kiến là bao nhiêu?** Giới hạn fan-out, đo Redis/server/client.
10. **Ai chịu trách nhiệm subscribe publisher?** Controller, worker, scheduler hoặc tầng quản lý vòng đời khác.
11. **Cần quan sát gì ở production?** Độ trễ, lỗi, memory, reconnect và các chỉ số nghiệp vụ liên quan.
12. **Luồng có điểm blocking nào không?** Tránh `.block()` và I/O blocking trên event-loop.

## 29. Kết luận

Các nhóm Reactive Operations trong Spring Data Redis đưa các cấu trúc Redis vào mô hình Project Reactor:

- **`opsForValue()`** cho String, cache đơn giản và counter.
- **`opsForHash()`** cho dữ liệu nhiều field.
- **`opsForList()`** cho danh sách có thứ tự và thao tác đầu/cuối.
- **`opsForSet()`** cho membership không trùng.
- **`opsForZSet()`** cho ranking/score.
- **`opsForGeo()`** cho tọa độ và truy vấn vị trí.
- **`opsForHyperLogLog()`** cho ước lượng số phần tử duy nhất.
- **`opsForStream()`** cho các bản ghi sự kiện có ID và cơ chế consumer group.

Những API này trả `Mono`/`Flux`, cho phép dùng `map`, `flatMap`, `zip`, `concatMap`, `then` và các operator khác để xây dựng luồng bất đồng bộ không blocking chờ Redis. Nhưng **Reactor chỉ điều phối luồng**, không tự tạo transaction Redis, không chống race condition cho chuỗi `GET`/`SET`, không biến lệnh lớn thành nhẹ và không loại bỏ nhu cầu thiết kế retry/idempotency.

Một ứng dụng Redis Reactive vững chắc bắt đầu từ **chọn đúng cấu trúc dữ liệu, dùng đúng nhóm operations, giữ publisher được compose đầy đủ, quản lý concurrency và hiểu chính xác tính nhất quán mà Redis thực sự cung cấp**. Khi những ranh giới này rõ ràng, Reactive Redis trở thành công cụ hiệu quả cho cả API WebFlux lẫn xử lý bất đồng bộ ở quy mô lớn.
