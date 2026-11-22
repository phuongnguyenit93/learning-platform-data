# Giới hạn Repository phản ứng và lựa chọn Template thay thế trong Spring Data Redis

> **Module:** Spring Data Redis  
> **Chương:** Redis phản ứng (*Reactive Redis*)  
> **Bài học:** Phân biệt hỗ trợ Redis Repository theo mô hình imperative với API Redis phản ứng, tìm hiểu vì sao không thể tự động thay `CrudRepository` bằng `ReactiveCrudRepository`, và cách thiết kế với `ReactiveRedisTemplate`/`ReactiveStringRedisTemplate` mà không nhầm lẫn về mapping, TTL, index, transaction hay lỗi mạng.

## 1. Bối cảnh: vì sao cần nói riêng về Reactive Redis Repository?

Một ứng dụng Spring WebFlux thường sử dụng `Mono<T>` và `Flux<T>` để xử lý nhiều request có thao tác I/O mà không cần giữ một thread đang đợi phản hồi của mỗi request. Redis có thể là nơi lưu cache, session, token, rate limit, counter hoặc các cấu trúc dữ liệu thời gian thực.

Spring Data Redis cung cấp cả API truy cập Redis theo mô hình **imperative** và **reactive**. Nhưng không phải tính năng imperative nào cũng có một phiên bản reactive tương đương.

Ví dụ về Repository imperative:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.annotation.Id;

@RedisHash("products")
public class ProductRedisEntity {
    @Id
    private String id;
    private String name;
    // Constructor, getters, setters...
}

public interface ProductRedisRepository
        extends CrudRepository<ProductRedisEntity, String> {
}
~~~

Repository này cung cấp những thao tác như `save`, `findById`, `deleteById` theo cách gọi đồng bộ. Khi repository truy cập Redis, thread gọi phương thức có thể phải đợi thao tác I/O hoàn thành.

Một cách viết khác có vẻ hấp dẫn:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ReactiveProductRedisRepository
        extends ReactiveCrudRepository<ProductRedisEntity, String> {
}
~~~

**Không thể mặc định coi interface thứ hai là một Redis Repository hoạt động.** Trong các dòng Spring Data Redis được tài liệu hóa với Reactive Redis support, **Redis repositories không có hỗ trợ reactive repository tương đương**. Việc `ReactiveCrudRepository` tồn tại trong Spring Data Commons **không chứng minh** module Spring Data Redis biết tạo reactive repository proxy cho Redis.

Nếu muốn thực sự truy cập Redis theo reactive model, lựa chọn trực tiếp là:

- `ReactiveRedisTemplate<K, V>`.
- `ReactiveStringRedisTemplate`, được tối ưu cho key/value dạng String.
- `ReactiveRedisOperations<K, V>` để lập trình theo interface.
- Reactive Redis connection hoặc scripting/Streams API thích hợp khi cần điều khiển thấp hơn.

Điều này **không có nghĩa Redis chỉ hỗ trợ API blocking**. Ngược lại, Reactive Redis Template có thể gửi command trên driver non-blocking; sự thiếu hụt ở đây là **tầng repository abstraction**, không phải ở khả năng Redis server tiếp nhận command.

## 2. Ba lớp cần phân biệt

### 2.1. Spring Data Commons

Spring Data Commons định nghĩa những interface như:

- `Repository<T, ID>`.
- `CrudRepository<T, ID>`.
- `PagingAndSortingRepository<T, ID>`.
- `ReactiveCrudRepository<T, ID>`.
- `ReactiveSortingRepository<T, ID>`.

Các interface này chỉ là hợp đồng lập trình chung. Để có implementation hoạt động, **một Spring Data module cụ thể** phải hỗ trợ repository factory, mapping, query execution và store-specific operations tương ứng.

Ví dụ Reactive MongoDB Repository và R2DBC Repository có cơ chế reactive repository riêng, nhưng không nên suy luận rằng tất cả các datastore cũng cung cấp mức hỗ trợ đó.

### 2.2. Spring Data Redis Repository

Redis Repository sử dụng cơ chế mapping để lưu entity vào Redis Hash. Một entity có thể có:

- `@RedisHash` cho keyspace và TTL mặc định.
- `@Id` cho identifier.
- `@TimeToLive` cho thời gian sống.
- `@Indexed` cho secondary index và finder phù hợp.
- `RedisConverter`, mapping context và metadata của Spring Data.
- Cơ chế liên quan đến key expiration events để hỗ trợ dọn chỉ mục.

Đây là một tầng chức năng **cao hơn** việc chỉ chạy `SET`/`GET` trên Redis.

### 2.3. Spring Data Redis Reactive Template

Reactive Template tập trung vào **các Redis operations** trả về Reactor publishers:

~~~java
Mono<String> value = reactiveRedisTemplate
        .opsForValue()
        .get("cache:product:101");
~~~

Với `ReactiveRedisTemplate`, application quyết định key schema, format dữ liệu, TTL, index và logic lỗi. Template không tự đóng vai Redis Repository có query derivation và mapping entity đầy đủ chỉ vì kiểu kết quả là `Mono` hoặc `Flux`.

### 2.4. Sơ đồ ranh giới

~~~mermaid
flowchart TD
    APP["WebFlux / Reactive service"] --> CHOICE{"Lựa chọn truy cập dữ liệu"}
    CHOICE --> R["ReactiveCrudRepository"]
    CHOICE --> T["ReactiveRedisTemplate / ReactiveStringRedisTemplate"]
    CHOICE --> I["Imperative Redis CrudRepository"]
    R --> STORES["Store module có reactive repository implementation, ví dụ R2DBC"]
    T --> OPS["ReactiveRedisOperations"]
    OPS --> FACTORY["ReactiveRedisConnectionFactory"]
    FACTORY --> DRIVER["Redis driver non-blocking, thường Lettuce"]
    DRIVER --> REDIS["Redis server"]
    I --> BLOCK["Repository imperative + Redis mapping"]
    BLOCK --> REDIS
    R -. "Không tự tạo Redis reactive repository" .-> REDIS
~~~

Câu hỏi cần trả lời trước khi chọn API là **ứng dụng cần reactive Redis commands hay cần cả repository mapping/query abstraction?** Hai nhu cầu không giống nhau.

## 3. Repository imperative không tương đương ReactiveRedisTemplate

| Khả năng | Redis Repository imperative | ReactiveRedisTemplate |
|---|---|---|
| Kiểu API | `CrudRepository`, tìm theo id, derived queries được hỗ trợ | Reactive Redis commands |
| Kiểu kết quả | Object/`Optional`/`Iterable`, đồng bộ | `Mono`/`Flux`, bất đồng bộ |
| Mapping entity với `@RedisHash` | Có | Không tự động giống repository |
| Sinh key theo id/keyspace | Có theo mapping | Ứng dụng tự thiết kế |
| Secondary index qua `@Indexed` | Có theo phạm vi repository hỗ trợ | Phải tự lưu/duy trì nếu muốn |
| `@TimeToLive` trên entity | Có theo mapping | Không tự nhận annotation trên POJO |
| Finder dựa trên index | Có theo hỗ trợ repository | Tự viết Redis commands/query model |
| Key expiration handling | Cơ chế repository riêng | Ứng dụng tự đăng ký listener/thiết kế nếu cần |
| Redis Hash mapping | Có | Có `opsForHash()` nhưng phải tự chọn map/serializer |
| Redis native types/counters/lists/sets/streams | Không phải trọng tâm | Có nhiều operation nhóm tương ứng |
| Non-blocking I/O kiểu Reactor | Không | Có với connection factory/driver thích hợp |
| Tự động bảo đảm transaction đa key | Không | Không |
| Dùng ReactiveTransactionManager cho DB và Redis cùng commit | Không | Không tự động |

**Giữ nguyên chú giải:** “Có” ở cột Repository có nghĩa trong phạm vi mapping và repository features của Spring Data Redis; không phải toàn bộ query của SQL/JPA đều tồn tại với Redis. “Có” ở cột Template có nghĩa cung cấp các Redis operations thích hợp, không đồng nghĩa mọi command trên mọi phiên bản driver đều có cùng semantics.

## 4. Vì sao không thể chỉ đổi extends sang ReactiveCrudRepository?

Một interface Repository có thể được Spring tạo implementation khi module store cung cấp:

1. **Repository factory** hiểu cách xác định Redis entity.
2. **Mapping layer** biết chuyển entity thành Redis Hash và ngược lại.
3. **Query execution** biết xử lý id, criteria và derived finder.
4. **Reactive execution model** dùng reactive Redis connections.
5. **Lifecycle/TTL/index management** tương thích với reactive pipeline.

`ReactiveCrudRepository` chỉ mô tả hợp đồng ở tầng Spring Data Commons. Nó không tự sinh implementation cho Redis.

### 4.1. Các kết quả có thể gặp

Nếu khai báo:

~~~java
public interface ReactiveProductRepository
        extends ReactiveCrudRepository<ProductRedisEntity, String> {
}
~~~

mà ứng dụng không có store module nhận interface này, khi khởi động có thể:

- Không xuất hiện bean repository mong muốn.
- Xuất hiện lỗi injection vì không có bean.
- Bị Spring Data repository scanning báo không xác định được store phù hợp nếu có nhiều module.
- Hoặc được một module **khác** nhận nếu entity/package/config không được phân định rõ.

Không nên đưa ra một thông báo exception cố định vì nó thay đổi theo Spring Data version và cơ chế scan.

### 4.2. Tại sao wrapper Mono không tự giải quyết?

Ví dụ:

~~~java
public Mono<ProductRedisEntity> find(String id) {
    return Mono.justOrEmpty(repository.findById(id));
}
~~~

Thao tác `repository.findById(id)` **đã chạy trước** khi `Mono.justOrEmpty(...)` trả về; thread gọi `find` vẫn có thể bị chặn. Đây không phải native reactive I/O.

Ngay cả khi viết:

~~~java
public Mono<ProductRedisEntity> find(String id) {
    return Mono.fromCallable(() -> repository.findById(id))
            .flatMap(Mono::justOrEmpty);
}
~~~

hàm `findById` được trì hoãn cho tới subscription, nhưng nó **vẫn blocking** ở thread thực thi callable. Cần phân biệt **lười thực thi** (*lazy*) và **không chặn luồng** (*non-blocking*).

## 5. Lựa chọn thay thế chính: ReactiveRedisTemplate

Spring Data Redis cung cấp các thành phần:

- `ReactiveRedisOperations<K,V>`: giao diện các thao tác Redis reactive.
- `ReactiveRedisTemplate<K,V>`: implementation tổng quát.
- `ReactiveStringRedisTemplate`: template cho dữ liệu chuỗi, thường tiện dùng với JSON được encode tường minh.
- `ReactiveRedisConnectionFactory`: factory cấp Redis reactive connections.
- `ReactiveValueOperations`, `ReactiveHashOperations`, `ReactiveListOperations`, `ReactiveSetOperations` và những operation groups khác.

### 5.1. Các lệnh điển hình

~~~java
Mono<String> read =
        redis.opsForValue().get("products:101");

Mono<Boolean> write =
        redis.opsForValue().set(
                "products:101", "json-payload",
                Duration.ofMinutes(10));

Mono<Long> deleted =
        redis.delete("products:101");

Mono<Boolean> exists =
        redis.hasKey("products:101");

Mono<Duration> remaining =
        redis.getExpire("products:101");
~~~

Ở đây `redis` là `ReactiveStringRedisTemplate`. Các signatures thể hiện cách sử dụng thông thường; đối chiếu với Spring Data Redis version của dự án khi gọi những overload nâng cao.

Điểm khác imperative API: mỗi thao tác trả về `Mono` hoặc `Flux`. Để thực sự chạy, nó phải được subscribe bởi framework (ví dụ WebFlux) hoặc một subscriber hợp lệ. Không dùng `block()` trên Netty event-loop.

### 5.2. Lựa chọn driver

Spring Data Redis Reactive support thường được sử dụng với **Lettuce** và `LettuceConnectionFactory` do driver này cung cấp non-blocking/reactive Redis access. Không suy ra chỉ vì ứng dụng có Jedis/imperative RedisTemplate thì có thể dùng reactive API tương đương.

Dù sử dụng non-blocking client, Redis server vẫn chịu giới hạn CPU, memory, network và số connections. Reactive I/O giúp giảm thread chờ của phía ứng dụng, **không làm Redis command chạy “miễn phí”**.

### 5.3. Những gì Template không tự tạo

Khi dùng:

~~~java
redis.opsForValue().set("products:101", json);
~~~

Template không tự biết:

- `products:101` có phải keyspace từ `@RedisHash("products")` không.
- `101` có phải `@Id` của một entity nào đó không.
- Có phải thêm id vào secondary index `products:name:Desk` không.
- Có phải tạo phantom copy để xử lý expiration event không.
- Có cần read-through database khi key không tồn tại không.
- Giá trị phải tồn tại bao lâu nếu bạn không truyền TTL.
- Một field Java được lưu thành Redis Hash field nào.

Đây là **trách nhiệm mới của ứng dụng** nếu rời bỏ repository abstraction.

## 6. Cấu hình Spring Boot cho Reactive Redis

### 6.1. Dependency

Với Spring Boot dùng Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-redis-reactive")
}
~~~

Một số dự án Spring Boot đã có các transitive dependencies tương ứng, nhưng biểu diễn trên giúp thể hiện rõ việc dùng Reactive Redis starter. Cần giữ các version theo Spring Boot dependency management; không trộn tùy tiện Spring Data Redis version độc lập.

### 6.2. Application configuration

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Nếu Redis yêu cầu ACL/TLS/Cluster hoặc Sentinel, hãy dùng thuộc tính connection tương ứng với hạ tầng. Không hard-code password/token trong source code hay ví dụ triển khai.

### 6.3. Inject ReactiveStringRedisTemplate

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingStore {

    private final ReactiveStringRedisTemplate redis;

    public GreetingStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(String userId, String greeting) {
        return redis.opsForValue().set(
                "greetings:" + userId, greeting);
    }

    public Mono<String> read(String userId) {
        return redis.opsForValue().get("greetings:" + userId);
    }
}
~~~

Trong một ứng dụng WebFlux, controller có thể trả thẳng `Mono<String>`. WebFlux subscribe tại ranh giới HTTP, nên service không cần tự gọi `subscribe()`.

~~~java
@RestController
@RequestMapping("/greetings")
public class GreetingController {

    private final GreetingStore store;

    public GreetingController(GreetingStore store) {
        this.store = store;
    }

    @GetMapping("/{userId}")
    public Mono<String> greeting(@PathVariable String userId) {
        return store.read(userId);
    }
}
~~~

Ví dụ controller chỉ minh họa wiring. Nếu key không tồn tại, `Mono.empty()` cần được controller chuyển thành HTTP 404 hoặc response khác theo contract API; WebFlux không tự đoán “cache miss = 404” theo yêu cầu nghiệp vụ của mọi hệ thống.

## 7. Thay Repository bằng Template: thiết kế key và serializer

Giả sử entity imperative trước đây:

~~~java
@RedisHash(value = "products", timeToLive = 600)
public class ProductRedisEntity {

    @Id
    private String id;

    @Indexed
    private String category;

    private String name;
}
~~~

Redis Repository quản lý id, Hash mapping, TTL và secondary index theo quy ước nội bộ. Nếu chuyển sang ReactiveStringRedisTemplate với JSON String, phải **thiết kế schema riêng**:

~~~text
Key:
  app:products:v1:p-101

Value JSON:
  {
    "id": "p-101",
    "category": "furniture",
    "name": "Adjustable Desk"
  }

TTL:
  600 giây khi ghi
~~~

### 7.1. Vì sao không ghi thẳng vào key cũ của Repository?

Repository có thể lưu entity thành Redis Hash và tạo index Sets/metadata khác. Nếu một ReactiveStringRedisTemplate đặt Redis String vào chính key đó:

- Redis data type thay đổi từ `hash` sang `string`.
- Repository tiếp tục đọc Hash có thể nhận `WRONGTYPE`.
- Index Set có thể giữ tham chiếu không còn hợp lệ.
- TTL và expiration cleanup có thể không còn đúng.
- Những key phụ mà Repository tạo có thể bị bỏ mồ côi.

Vì vậy, **không nên giả định dữ liệu có thể được dùng chung giữa Redis Repository và Reactive Template theo đúng một key layout**. Khi migration, hãy tách namespace và xây dựng lộ trình chuyển đổi.

### 7.2. Chọn serializer rõ ràng

Có hai hướng:

**Hướng A: `ReactiveStringRedisTemplate` + JSON String chủ động.**

- Key là chuỗi UTF-8.
- Value là chuỗi JSON do Jackson/ObjectMapper tạo.
- Ứng dụng kiểm soát schema/version.
- Tương tác với service không dùng Java thường thuận tiện hơn.

**Hướng B: `ReactiveRedisTemplate<K,V>` với `RedisSerializationContext` tùy chỉnh.**

- Template serialize key/value tự động.
- Có thể dùng Jackson serializer hoặc codec khác tương ứng Spring Data Redis version.
- Cần thống nhất với mọi writer/reader và quản lý versioning.

Đối với hướng B, đối tượng quan trọng là `RedisSerializationContext<K,V>`. Nó xác định các serialization pairs cho key, value, hash key và hash value. Cấu hình phải đồng nhất giữa đường ghi/đọc. Không nên phụ thuộc serializer nhị phân mặc định không được kiểm soát nếu dữ liệu sẽ tồn tại lâu hoặc được nhiều service sử dụng.

### 7.3. Quy ước prefix và version

Ví dụ:

~~~text
cache:products:v1:p-101
cache:products:v1:p-102
views:product:p-101
rate-limit:user:u-123
~~~

Không đặt tất cả dữ liệu vào một prefix chung rồi xóa bằng wildcard trên Redis production. Hãy phân vùng keyspace theo chức năng, quyền sở hữu dữ liệu và vòng đời TTL.

Khi đổi serializer/schema:

~~~text
cache:products:v1:p-101 -> format cũ
cache:products:v2:p-101 -> format mới
~~~

Việc đặt version vào prefix giúp tránh consumer mới vô tình deserialize payload cũ bằng codec mới. Key v1 có thể tự hết TTL hoặc được dọn bằng migration.

## 8. Ví dụ hoàn chỉnh: reactive cache-aside với JSON và TTL

Bài toán: lấy thông tin sản phẩm từ một nguồn dữ liệu reactive. Ưu tiên Redis nếu cache còn; cache miss thì đọc nguồn, serialize JSON và lưu vào Redis với TTL 10 phút.

### 8.1. Định nghĩa DTO và nguồn dữ liệu

~~~java
// File ProductView.java
public record ProductView(
        String id,
        String name,
        long priceMinor,
        String currency) {
}
~~~

~~~java
// File ReactiveProductSource.java
import reactor.core.publisher.Mono;

public interface ReactiveProductSource {
    Mono<ProductView> findById(String id);
}
~~~

`ReactiveProductSource` là **interface ứng dụng tự định nghĩa**. Implementation có thể dùng R2DBC Repository, Reactive MongoDB Repository, WebClient hoặc một nguồn non-blocking phù hợp. Nó không phải Redis reactive repository.

### 8.2. Reactive cache service

~~~java
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCache {

    private static final Duration TTL = Duration.ofMinutes(10);

    private final ReactiveStringRedisTemplate redis;
    private final ReactiveProductSource source;
    private final ObjectMapper mapper;

    public ReactiveProductCache(
            ReactiveStringRedisTemplate redis,
            ReactiveProductSource source,
            ObjectMapper mapper) {
        this.redis = redis;
        this.source = source;
        this.mapper = mapper;
    }

    public Mono<ProductView> findById(String id) {
        String key = "cache:products:v1:" + id;

        return redis.opsForValue()
                .get(key)
                .flatMap(json -> Mono.fromCallable(
                        () -> mapper.readValue(
                                json, ProductView.class)))
                .switchIfEmpty(Mono.defer(
                        () -> loadAndCache(id, key)));
    }

    private Mono<ProductView> loadAndCache(
            String id, String key) {

        return source.findById(id)
                .flatMap(product ->
                        Mono.fromCallable(
                                () -> mapper.writeValueAsString(product))
                            .flatMap(json ->
                                    redis.opsForValue()
                                            .set(key, json, TTL)
                                            .thenReturn(product)));
    }

    public Mono<Long> evict(String id) {
        return redis.delete("cache:products:v1:" + id);
    }
}
~~~

Dòng chảy:

~~~mermaid
sequenceDiagram
    participant C as WebFlux Controller
    participant S as ReactiveProductCache
    participant R as Redis
    participant D as ReactiveProductSource
    C->>S: findById("p-101")
    S->>R: Reactive GET cache:products:v1:p-101
    alt Cache hit
        R-->>S: JSON
        S->>S: Deserialize ProductView
        S-->>C: Mono<ProductView>
    else Cache miss
        R-->>S: Empty
        S->>D: findById("p-101")
        D-->>S: ProductView
        S->>S: Serialize JSON
        S->>R: SET key JSON EX 600
        R-->>S: OK
        S-->>C: ProductView
    end
~~~

Một số lưu ý:

1. `switchIfEmpty(Mono.defer(...))` chỉ chạy fallback khi Redis không có value, không phải khi Redis lỗi.
2. `ObjectMapper` serialize object trong pipeline, nhưng đây là công việc CPU. Đối với payload nhỏ, thường có thể chấp nhận; với payload cực lớn cần theo dõi event-loop latency và cân nhắc bố trí công việc CPU thích hợp.
3. `opsForValue().set(key, json, TTL)` yêu cầu Redis lưu value **cùng TTL** trong một thao tác hỗ trợ, tránh khoảng trống khi `SET` và `EXPIRE` được gửi tách rời.
4. `thenReturn(product)` trả sản phẩm sau khi thao tác ghi cache hoàn tất. Nếu Redis SET lỗi, ví dụ đang viết sẽ **propagate error** thay vì âm thầm trả sản phẩm.
5. Nếu `source.findById` trả `Mono.empty()` thì service cũng trả empty và không cache negative result.
6. Code này chưa giải quyết cache stampede hoặc dữ liệu stale do concurrent writes; đó là vấn đề thiết kế riêng.

### 8.3. Vì sao dùng Mono.defer?

Hãy so sánh:

~~~java
// Tránh tạo eager side-effect hoặc tính toán blocking bên ngoài publisher.
return cacheRead.switchIfEmpty(loadSourceEagerly());

// Đúng hướng khi fallback cần được tạo tại lúc subscribe/miss.
return cacheRead.switchIfEmpty(
        Mono.defer(() -> loadFromSource()));
~~~

Nếu `loadSourceEagerly()` chỉ trả về một cold Mono không side-effect, nó có thể không thực thi truy vấn trước; tuy nhiên `Mono.defer` giúp giữ cả việc tạo luồng fallback và những side effects tiềm ẩn ở thời điểm cần. Trong reactive code, **subscription** quyết định khi nào chuỗi lệnh bắt đầu chạy.

### 8.4. Chính sách lỗi cache phải tách khỏi lỗi nguồn

Với cache-aside, nếu Redis không sẵn sàng nhưng nguồn chuẩn còn, có thể muốn trả kết quả từ nguồn. Nhưng một `onErrorResume` đặt sai vị trí có thể nuốt luôn lỗi database.

Ví dụ chỉ fallback trên lỗi khi **đọc cache**:

~~~java
public Mono<ProductView> findWithReadFallback(String id) {
    String key = "cache:products:v1:" + id;

    Mono<ProductView> readCache =
            redis.opsForValue()
                    .get(key)
                    .flatMap(json ->
                            Mono.fromCallable(
                                    () -> mapper.readValue(
                                            json, ProductView.class)))
                    .onErrorResume(
                            org.springframework.data.redis.RedisConnectionFailureException.class,
                            ex -> Mono.empty());

    return readCache.switchIfEmpty(
            Mono.defer(() -> source.findById(id)));
}
~~~

Mẫu này **không ghi lại cache sau miss**, nhằm minh họa điểm đặt error handler. Với sản phẩm thực tế, có thể nối vào `loadAndCache` hoặc một hàm “best effort cache put” riêng, ghi metrics và bảo vệ database khỏi bùng tải.

Không nên vô điều kiện dùng:

~~~java
return redisOperation.onErrorResume(error -> Mono.empty());
~~~

cho mọi lỗi. Nó che giấu lỗi serialization, dữ liệu sai và thậm chí lỗi logic lập trình. Đối với dữ liệu quan trọng, fail-open cache không phải lúc nào cũng an toàn.

## 9. TTL với Reactive Template khác TTL của Redis Repository

### 9.1. Redis Repository

~~~java
@RedisHash(value = "sessions", timeToLive = 900)
public class SessionEntity {
    @Id
    private String id;
}
~~~

Trong repository, framework mapping xử lý quy ước lưu entity có TTL 900 giây; có thêm cơ chế liên quan expiration events và index.

### 9.2. Reactive Template

~~~java
Mono<Boolean> saved =
        redis.opsForValue().set(
                "session:v1:" + sessionId,
                json,
                Duration.ofMinutes(15));
~~~

Khi dùng template, **TTL phải được chỉ định tại thao tác ghi**, hoặc đặt sau bằng `expire(...)` theo giao thức bạn thiết kế. Một `@TimeToLive` trên DTO không tự kích hoạt TTL trong ReactiveStringRedisTemplate.

### 9.3. Dùng expire riêng có rủi ro gì?

~~~java
redis.opsForValue().set(key, value)
    .then(redis.expire(key, Duration.ofMinutes(15)));
~~~

Hai command này không phải một thao tác nguyên tử ở cấp Redis. Nếu kết nối lỗi sau khi SET nhưng trước EXPIRE, key có thể tồn tại không có TTL. Với Redis String value, nên dùng `set(key, value, Duration)` để kết hợp trong một operation khi phù hợp.

Với Redis Hash và nhiều field, thường cần thao tác `HSET`/`HSETALL` rồi `EXPIRE`. Nếu phải đảm bảo atomic nhiều lệnh, cân nhắc Redis Lua/Redis Function hoặc cơ chế phù hợp với key-slot; không cho rằng reactive composition `.then(...)` tạo Redis transaction.

### 9.4. TTL không đồng nghĩa event expiration

Redis sẽ loại key khi TTL hết ngay cả khi Spring không đăng ký listener. Nếu muốn chủ động xử lý expiration, cần hiểu keyspace notifications, quyền cấu hình server và đặc tính Pub/Sub không bền vững.

Reactive Template **không tự tái tạo** sự kiện `RedisKeyExpiredEvent` của Redis Repository, cũng không tự tạo shadow copy. Khi event bị mất, cleanup index do ứng dụng tự viết có thể không chạy; cần cơ chế bù trừ.

## 10. Reactive Template có thể lưu Redis Hash, nhưng không thành Repository

Giả sử muốn lưu sản phẩm trong Redis Hash thay vì JSON String:

~~~text
HSET product:p-101 id p-101 name Desk category furniture
EXPIRE product:p-101 600
~~~

Reactive Redis cung cấp nhóm `opsForHash()` để thao tác hash fields. Ở mức ý tưởng:

~~~java
// Pseudocode về cấu trúc thao tác; type và serializer
// được cấu hình phù hợp cho ReactiveRedisTemplate.
return redis.opsForHash()
        .putAll(
                "product:p-101",
                Map.of(
                        "id", "p-101",
                        "name", "Desk",
                        "category", "furniture"))
        .then(redis.expire(
                "product:p-101",
                Duration.ofMinutes(10)));
~~~

Đoạn trên là *minh họa*: kiểu `ReactiveHashOperations` và serializers phải khớp generic của bean `ReactiveRedisTemplate` thực tế.

### 10.1. Khác biệt so với @RedisHash

`@RedisHash` + repository có thể:

- Tạo key từ id/keyspace theo mapping.
- Chuyển thuộc tính entity thành Hash fields.
- Duy trì một số metadata/index.
- Áp TTL theo annotation.
- Đọc lại entity từ Hash.

Còn `opsForHash().putAll(...)` chỉ ghi các field được yêu cầu. Nó **không** tự:

- Đọc `@Id` từ entity.
- Xây dựng tên key từ `@RedisHash`.
- Tạo secondary indexes cho `@Indexed`.
- Dùng `@TimeToLive` trên entity.
- Gửi Spring repository lifecycle events.
- Dọn secondary index khi TTL hết.

Muốn semantics tương tự repository, ứng dụng phải triển khai các bước đó hoặc chọn kiến trúc khác.

### 10.2. Vì sao không nên sao chép layout nội bộ của Repository?

Redis Repository có thể lưu index sets, keyspace metadata và phantom copies với quy ước cụ thể. Việc tự tái tạo toàn bộ bằng nhiều Redis commands có thể:

- Phụ thuộc chi tiết nội bộ của phiên bản Spring Data Redis.
- Gây mồ côi index khi lưu/đổi/xóa.
- Không atomic khi nhiều service cùng cập nhật.
- Khó nâng cấp và khó sửa lỗi khi failover.

Một **reactive repository tự viết** nên có data model riêng, schema rõ ràng và các test/operational policies tương ứng, thay vì cố ghi đúng mọi key nội bộ của Redis Repository cũ.

## 11. Thiếu Repository query derivation thì truy vấn thế nào?

Repository cho phép một số finder methods dựa trên index được hỗ trợ. Với template, bạn phải thiết kế query pattern trực tiếp theo Redis.

Ví dụ cần tìm sản phẩm theo category:

~~~text
products:v1:p-101          -> JSON của sản phẩm 101
products:v1:p-102          -> JSON của sản phẩm 102
products:by-category:desk  -> Redis Set gồm p-101, p-102
~~~

Đường ghi có thể:

1. Ghi value sản phẩm.
2. Thêm id vào Redis Set theo category.
3. Khi đổi category, xóa id khỏi Set cũ rồi thêm vào Set mới.
4. Khi xóa sản phẩm, xóa key và xóa id khỏi các indexes liên quan.
5. Khi TTL hết, bảo đảm index không giữ stale ids bằng một chiến lược lifecycle.

### 11.1. Tính nhất quán của index

Nếu lưu JSON thành công nhưng thêm index thất bại, truy vấn theo category có thể không tìm thấy sản phẩm. Nếu update category nhưng chỉ thêm Set mới mà không xóa Set cũ, id có thể xuất hiện sai nhóm.

Với nhiều key phải cập nhật cùng nhau, cần xác định:

- Redis transaction hoặc Lua script nếu cùng Redis node/hash slot và được hỗ trợ.
- Quy tắc idempotency khi retry.
- Cách xử lý lỗi mạng không biết command đã chạy chưa.
- Cách rebuild index từ nguồn chuẩn.
- Mức độ eventual consistency có thể chấp nhận.

**Không gọi `reactiveRedisTemplate.opsForHash()` rồi suy luận các bước sẽ tự atomic**. Redis đảm bảo atomicity ở cấp từng command như `HSET`/`SADD`, nhưng nhiều commands riêng không tự là một transaction.

### 11.2. Redis Cluster

Khi dùng Redis Cluster, các lệnh nhiều key và Lua scripts có ràng buộc **hash slot**. Những key cần cập nhật nguyên tử cùng nhau phải được đặt phù hợp hoặc phải dùng một thiết kế eventual consistency.

Ví dụ hash tag:

~~~text
products:{p-101}:value
products:{p-101}:metadata
~~~

Hai key cùng tag `{p-101}` thường nằm cùng slot. Không nên gắn mọi sản phẩm vào một tag chung, vì có thể tạo hot spot trên một shard.

### 11.3. Khi nào không nên tạo secondary index trong Redis?

Nếu yêu cầu có tìm kiếm phức tạp, filter/sort/pagination lớn, join và query linh hoạt, có thể để database hoặc search index chuyên dụng làm nguồn truy vấn, còn Redis chỉ cache kết quả. Tự xây một bộ query engine bằng Redis Sets/ZSets thường đắt bảo trì hơn lợi ích mà nó mang lại.

## 12. ReactiveRedisTemplate không phải Reactive Repository nhưng có những Redis primitives mạnh

### 12.1. Counter nguyên tử

Đối với lượt xem hoặc rate metrics:

~~~java
public Mono<Long> incrementViewCount(String productId) {
    return redis.opsForValue()
            .increment("stats:views:" + productId);
}
~~~

`INCR` là một Redis command có semantics nguyên tử; không cần repository query abstraction hay một chuỗi read-modify-write.

### 12.2. Rate limiting

Có thể dùng Redis counters với TTL hoặc Lua script để kiểm tra quota và cập nhật nguyên tử. Không nên chỉ viết:

~~~text
GET counter
if counter < limit:
    SET counter + 1
~~~

dưới nhiều request đồng thời, vì dễ bị race. Reactive API giúp tổ chức I/O bất đồng bộ nhưng **không thay thế atomic server-side logic**.

### 12.3. Collections và cấu trúc dữ liệu

Reactive Redis operation groups cho phép làm việc với:

- String values.
- Hashes.
- Lists.
- Sets.
- Sorted Sets.
- Geo structures.
- Streams và Pub/Sub theo khả năng API/phiên bản.

Mỗi cấu trúc có semantics riêng: Sorted Set phù hợp bảng xếp hạng, Hash phù hợp field updates, Streams phù hợp event log có retention; không cần ép tất cả thành entities kiểu Repository.

### 12.4. Lua và server-side execution

Khi phải kiểm tra và cập nhật Redis atomically, một Redis Lua script chạy phía server có thể thích hợp. Trình tự logic:

~~~lua
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])

if current >= limit then
    return 0
end

return redis.call('INCR', KEYS[1])
~~~

Script giả định key là counter hợp lệ và có limit được cung cấp; thực tế cần xử lý TTL, input validation và ràng buộc Redis Cluster. Redis server chạy script nguyên tử về interleaving command, nhưng script chạy lâu có thể chặn Redis.

Spring Data Redis cung cấp scripting API và reactive execution phù hợp; cần chọn RedisScript/serializer/argument types theo phiên bản ứng dụng. Không dựa vào một `flatMap` để bảo đảm kiểm tra-quota-và-cập nhật là atomic.

## 13. Reactive không đồng nghĩa parallel hoặc pipeline tự động

Có ba ý tưởng dễ nhầm:

| Khái niệm | Mục tiêu | Có đảm bảo atomic nhiều lệnh? |
|---|---|---|
| **Reactive** | Non-blocking composition, xử lý kết quả dưới dạng Mono/Flux | Không |
| **Pipelining** | Gửi nhiều Redis commands mà không đợi từng response để giảm round trips | Không |
| **Transaction/Lua** | Bảo vệ thao tác nhiều lệnh hoặc logic điều kiện phía server | Có semantics riêng, cần cấu hình đúng |

Reactive client có thể quản lý nhiều Redis commands in-flight và sử dụng connection hiệu quả, nhưng `Mono.zip(...)` không biến các command thành Redis transaction.

Ví dụ:

~~~java
Mono<String> a = redis.opsForValue().get("cache:a");
Mono<String> b = redis.opsForValue().get("cache:b");

Mono<Tuple2<String, String>> both = Mono.zip(a, b);
~~~

`Mono.zip` giúp kết hợp kết quả từ hai publisher, nhưng không đảm bảo snapshot nhất quán giữa hai key. Nếu một client khác cập nhật trong lúc đọc, mỗi `GET` có thể nhìn thấy trạng thái tại thời điểm khác nhau.

Khi cần một lệnh native có semantics thích hợp như `MGET` trên một Redis instance và các key cùng slot (nếu Cluster), nó có thể phù hợp hơn nhiều GET riêng. Khi cần điều kiện atomic, dùng Redis command/Lua/transaction phù hợp.

## 14. Điều khiển concurrency và backpressure khi đọc Redis

Reactive không có nghĩa tạo số lượng command vô hạn là an toàn.

Ví dụ xử lý nhiều id:

~~~java
Flux<ProductView> products =
        Flux.fromIterable(productIds)
                .flatMap(cache::findById, 16);
~~~

Tham số `16` giới hạn số inner publishers được `flatMap` subscribe đồng thời. Điều này giúp kiểm soát **concurrency cấp ứng dụng**, giảm nguy cơ gửi hàng nghìn GET và database fallback cùng lúc.

### 14.1. flatMap và concatMap

- `flatMap` cho phép nhiều inner publishers thực thi đồng thời; thứ tự phát kết quả có thể khác thứ tự input.
- `concatMap` giữ thứ tự bằng cách chờ từng inner publisher theo trình tự; throughput có thể thấp hơn khi nhiều I/O độc lập.
- `flatMapSequential` cho phép concurrent inner subscriptions nhưng phát theo thứ tự đầu vào, với chi phí giữ kết quả chờ.

Chọn theo yêu cầu nghiệp vụ. Với tra cứu độc lập theo danh sách product IDs, `flatMap(..., concurrency)` thường hợp lý; với cập nhật phải đúng trình tự của cùng thực thể, có thể cần serialization/ordering ở mức cao hơn.

### 14.2. Backpressure giới hạn điều gì?

Reactor hỗ trợ demand và backpressure trong luồng Publisher–Subscriber. Nhưng Redis server không thể “thu hồi” command đã gửi; tùy driver và operation, dữ liệu có thể đã được tải vào memory buffer.

Vì vậy:

- Giới hạn concurrency từ đầu.
- Tránh tạo `Flux.range(1, millions).flatMap(...)` không có hạn.
- Xem xét batch/paging khi đọc nhiều key.
- Theo dõi Redis latency, connection queue, CPU và memory.
- Dùng timeout và circuit breaker phù hợp khi Redis quá tải.

Backpressure hữu ích nhưng **không thay thế rate limit và capacity planning** của Redis.

### 14.3. Không gọi subscribe trong service

Sai về mặt tổ chức lifecycle:

~~~java
public Mono<Void> save(String key, String value) {
    redis.opsForValue().set(key, value).subscribe();
    return Mono.empty();
}
~~~

Cách viết này detach thao tác ghi khỏi caller:

- Caller có thể nhận completed trước khi Redis ghi xong.
- Lỗi Redis có thể không được propagate đúng.
- Cancellation, retries, tracing và transaction context không nhất quán.

Nên trả publisher:

~~~java
public Mono<Void> save(String key, String value) {
    return redis.opsForValue()
            .set(key, value)
            .then();
}
~~~

WebFlux hoặc caller chuyên trách sẽ subscribe ở ranh giới phù hợp.

### 14.4. Không dùng block trong event loop

Sai:

~~~java
String value = redis.opsForValue().get(key).block();
~~~

Trên Netty event-loop/WebFlux request thread, `block()` phá lợi ích non-blocking và có thể gây lỗi hoặc làm cạn khả năng xử lý request khi tải cao.

Nếu cần tương tác với API imperative, hãy cân nhắc một boundary được cô lập trên boundedElastic (xem phần migration). Đừng dùng `block()` như cách “biến reactive API thành Repository đồng bộ” trong đường request.

## 15. Nếu buộc phải dùng Redis Repository imperative trong một luồng reactive?

Có những hệ thống đã có:

- Redis `CrudRepository` và mapping entity phức tạp.
- Nhiều finder methods dùng secondary indexes.
- Logic hiện tại đã phụ thuộc `@RedisHash` và `@Indexed`.
- Kế hoạch migration theo giai đoạn, chưa thể viết lại.

Có thể **bọc lời gọi blocking vào boundedElastic scheduler** để bảo vệ event-loop:

~~~java
import org.springframework.data.repository.CrudRepository;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class TransitionalProductAccess {

    private final ProductRedisRepository repository;

    public TransitionalProductAccess(
            ProductRedisRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductRedisEntity> findById(String id) {
        return Mono.fromCallable(
                    () -> repository.findById(id))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(optional -> Mono.justOrEmpty(optional));
    }
}
~~~

Ví dụ trên **không tạo native reactive repository**. Repository vẫn blocking; nó chỉ chạy trên scheduler được thiết kế cho tác vụ blocking thay vì chiếm event-loop.

### 15.1. Giới hạn của chiến lược boundedElastic

- Mỗi lời gọi I/O vẫn giữ một worker thread trong thời gian chờ.
- Có số lượng thread/queue giới hạn; throughput có thể chạm trần khi Redis chậm.
- Không hưởng đầy đủ cơ chế reactive connection của Lettuce.
- Cần kiểm soát cancellation, timeout và retries.
- Dùng nhiều lời gọi song song có thể làm đầy pool.
- Transaction/session context của repository imperative không tự chuyển thành reactive context.

Cách bọc này có thể là **bridge tạm thời**, không phải giải pháp thay thế lâu dài cho số lượng lớn Redis operations non-blocking.

### 15.2. Khi nào nên chọn migration từng phần?

Nếu Repository cũ đang phục vụ một tập query phức tạp, có thể:

1. Giữ Repository ở tầng adapter blocking với boundedElastic.
2. Chuyển các đường cache/GET/SET đơn giản sang ReactiveStringRedisTemplate.
3. Đo latency/throughput và memory khi dịch chuyển traffic.
4. Thiết kế namespace/schema riêng thay vì ghi đè key cũ.
5. Chỉ loại bỏ Repository sau khi logic mapping, index và TTL đã có giải pháp thay thế.

Cách này giảm rủi ro hơn một lần đổi toàn bộ interface sang ReactiveCrudRepository không được Redis store hỗ trợ.

## 16. Khi cần Reactive Repository thật: cân nhắc nơi lưu dữ liệu

Không phải mọi dữ liệu nên trở thành Redis-first entity.

### 16.1. Database reactive repository + Redis reactive cache

Một kiến trúc phổ biến:

~~~text
WebFlux Controller
      |
      v
Reactive Service
      |
      +--> ReactiveRedisTemplate: cache/fast lookup
      |
      +--> R2DBC Repository / Reactive Mongo Repository: nguồn chuẩn
~~~

Ví dụ:

- PostgreSQL qua Spring Data R2DBC quản lý Product entity và truy vấn.
- Redis Reactive Template giữ bản cache JSON với TTL.
- Update trong database làm invalidation cache sau commit bằng cơ chế thích hợp.

Ưu điểm: tận dụng reactive repositories nơi chúng được hỗ trợ, còn Redis đảm nhận bài toán cache và native Redis data structures.

### 16.2. Nếu Redis là nguồn dữ liệu chính

Có thể xây dựng **custom reactive data-access adapter** dựa trên ReactiveRedisTemplate:

~~~java
public interface ReactiveProductStore {
    Mono<ProductView> save(ProductView product);
    Mono<ProductView> findById(String id);
    Mono<Boolean> deleteById(String id);
}
~~~

Implementation phải định nghĩa:

- Key schema, ID, serialization.
- TTL và vòng đời dữ liệu.
- Cách query theo các thuộc tính.
- Secondary index consistency.
- Atomicity/concurrency.
- Error/timeout/retry/idempotency.
- Migration và compatibility.

Đặt tên interface là `ReactiveProductStore` hoặc `ProductGateway` thường giúp tránh nhầm nó là một Spring Data Redis reactive repository có đầy đủ cơ chế framework.

### 16.3. Không lạm dụng Redis cho query engine

Nếu cần join, filter động, phân trang theo nhiều tiêu chí, transactional relational constraints và reporting, một reactive database repository có thể phù hợp hơn. Redis Template có thể hỗ trợ index thủ công bằng Set/Sorted Set, nhưng điều đó cần tự thiết kế consistency và query semantics.

**Tiêu chí chọn datastore bắt đầu từ data model**, không chỉ từ mong muốn mọi API phải trả `Mono`.

## 17. Spring Cache annotation có thay Reactive Redis Repository không?

Một số ứng dụng dùng:

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public Mono<ProductView> findProduct(String id) {
    return reactiveDatabase.findById(id);
}
~~~

Cần phân biệt:

- `@Cacheable` là **Spring Cache abstraction** ở mức method result.
- `RedisCacheManager` là implementation cache dùng Redis.
- `ReactiveRedisTemplate` là API thao tác Redis non-blocking.
- `ReactiveCrudRepository` là repository abstraction riêng ở tầng Spring Data Commons.

Từ Spring Framework 6.1, cache abstraction có hỗ trợ đặc biệt cho reactive return types trong những điều kiện phù hợp; nhưng hành vi thực tế phụ thuộc `CacheManager`/`Cache` implementation và cấu hình. **Không được suy ra dùng `@Cacheable` + RedisCacheManager đồng nghĩa Redis cache I/O native non-blocking**. RedisCacheManager có lịch sử API imperative/blocking và không tự biến thành Redis reactive repository.

Nếu yêu cầu đường HTTP thật sự non-blocking end-to-end, cần đánh giá stack cache cụ thể. Trong nhiều trường hợp, compose `ReactiveRedisTemplate` với nguồn reactive cho phép kiểm soát rõ hơn.

Một nguồn sai lầm khác là cache chính `Mono` object thay vì kết quả của nó. Hành vi cache reactive publisher thay đổi theo phiên bản Spring Framework và implementation; kiểm tra chính xác semantics khi dùng annotations với Reactor.

## 18. Consistency với database và transaction

Một chain reactive có thể trông rất gọn:

~~~java
return productRepository.save(product)
        .flatMap(saved ->
                redis.delete("cache:products:v1:" + saved.getId())
                     .thenReturn(saved));
~~~

Nhưng ý nghĩa là:

1. Database lưu dữ liệu.
2. Redis cache key được xóa.
3. Caller nhận kết quả nếu cả hai operation thành công.

**Không có distributed transaction tự động** giữa database và Redis.

Ví dụ database commit thành công nhưng Redis DELETE lỗi: database có dữ liệu mới, cache có thể vẫn giữ dữ liệu cũ. Caller thấy error nhưng retry tùy tiện có thể ghi dữ liệu hai lần hoặc phát event trùng.

### 18.1. Các lựa chọn tăng độ tin cậy

- Invalidate cache **sau database commit** bằng cơ chế reactive transaction synchronization hoặc event được ghi bền vững.
- Dùng transactional outbox/CDC nếu cập nhật cache từ nhiều service.
- Đặt TTL dự phòng để dữ liệu stale không tồn tại vô hạn.
- Dùng versioned cache key khi phù hợp.
- Thiết kế retry idempotent, có backoff và giới hạn.
- Quy định độ cũ tối đa được phép phục vụ.

Một `@Transactional` của R2DBC không làm Redis commands tự tham gia cùng giao dịch ACID. Redis transaction/Lua cũng không khiến transaction database và Redis trở thành một.

### 18.2. Race giữa cache miss và update

Giả sử:

~~~text
T1  Reader đọc nguồn dữ liệu v1, chuẩn bị cache
T2  Writer cập nhật database thành v2, xóa cache
T3  Reader ghi v1 vào cache sau khi Writer đã xóa
T4  Request tiếp theo đọc lại v1
~~~

Dù cả hai luồng dùng non-blocking Mono/Flux, race vẫn tồn tại. Cần TTL đủ ngắn theo freshness requirement hoặc version check/invalidation protocol cẩn thận.

### 18.3. Reactive cancellation và side effect

Một HTTP client disconnect có thể làm subscriber cancel reactive pipeline. Tuy nhiên Redis command đã gửi đi **có thể đã được Redis thực thi**; cancellation không đồng nghĩa rollback. Các thao tác nghiệp vụ quan trọng cần idempotency và trạng thái bền vững, không phụ thuộc giả định “cancel = chưa ghi”.

## 19. Lỗi, timeout và retry trong reactive Redis

### 19.1. Timeout

~~~java
Mono<String> response = redis.opsForValue()
        .get("cache:product:101")
        .timeout(Duration.ofSeconds(2));
~~~

Timeout giúp bảo vệ resource budget phía ứng dụng, nhưng không bảo đảm Redis chưa thực thi command. Với read-only GET, retry có thể đơn giản hơn. Với `INCR` hoặc các lệnh ghi có side effect, retry sau timeout có thể gây thay đổi **hai lần** nếu lệnh đầu tiên đã chạy.

### 19.2. Retry có điều kiện

Với thao tác đọc:

~~~java
Mono<String> read = redis.opsForValue()
        .get(key)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                     .filter(this::isTransientRedisFailure));
~~~

Trong đoạn mẫu, `isTransientRedisFailure` là predicate do ứng dụng tự triển khai. Phải giới hạn số lần retry, timeout toàn luồng và số request đồng thời; không retry mọi exception kể cả schema errors hay input invalid.

Với write, cần phân biệt:

- `SET key fixedValue` có thể tương đối an toàn để retry nếu không có điều kiện/cạnh tranh làm thay đổi semantics.
- `INCR`/`LPUSH`/event append có thể lặp side effect.
- Script có idempotency key hoặc conditional write có thể giúp xây dựng giao thức retry an toàn.

### 19.3. Redis bị lỗi nhưng nguồn còn hoạt động

Với cache-aside, một chiến lược fail-open có thể cho phép đọc database dù Redis GET lỗi. Nhưng nếu toàn bộ Redis cluster lỗi, rất nhiều request có thể cùng tràn về database. Cần:

- Giới hạn concurrency.
- Circuit breaker/cooldown.
- Rate limiting và bulkhead.
- Giám sát cache read failures.
- Bảo vệ nguồn chuẩn khi xảy ra miss storm.

Không che giấu lỗi Redis bằng `onErrorResume(error -> Mono.empty())` trên mọi đoạn code, vì sẽ khó phát hiện lỗi logic và cache invalidation thất bại.

## 20. Reactive Streams và Redis Pub/Sub không phải Repository

Ngoài simple key/value, Spring Data Redis còn có reactive access cho một số messaging use cases.

### 20.1. Redis Pub/Sub

Pub/Sub thích hợp với thông báo thời gian thực mà việc bỏ lỡ khi subscriber offline có thể chấp nhận. Reactive API có thể expose một `Flux` các message.

Tuy nhiên Pub/Sub **không có persistence/replay** cho các message khi subscriber offline. Dùng reactive Flux chỉ cải thiện cách ứng dụng consume I/O, không thay đổi delivery semantics của Redis.

### 20.2. Redis Streams

Redis Streams giữ các entries tới khi bị trim, có consumer groups và `XACK`. Spring Data Redis Reactive Streams API có thể trả record dạng Map/Object theo serialization/mapping được cấu hình.

Nó phù hợp hơn Pub/Sub nếu cần lịch sử, pending/reclaim và retry theo chính sách. Tuy vậy:

- Consumer cần quản lý offset, ACK và idempotency.
- Stream có retention/trim riêng.
- Reactive processing không tự đảm bảo exactly-once business effect.
- MapRecord/ObjectRecord cho Streams **không tạo reactive entity repository**.

Nếu ứng dụng cần event log, chọn Stream operations thay vì ép chúng vào CRUD repository interface.

## 21. Vấn đề mapping và migration từ Repository cũ

Khi chuyển từ imperative Redis Repository sang Reactive Template, nên lập bảng đối chiếu từng tính năng:

| Chức năng cũ | Repository trước đây | Phương án Reactive Template |
|---|---|---|
| `save(entity)` | Lưu entity theo Redis mapping | Serialize DTO và `SET`/`HSET` |
| `findById(id)` | Đọc entity từ Hash | `GET`/`HGETALL` + decode |
| `deleteById(id)` | Xóa entity và metadata liên quan | `DEL`/`UNLINK` và cleanup riêng |
| `@TimeToLive` | Áp TTL theo mapping | Truyền `Duration` khi ghi hoặc `expire` |
| `@Indexed` | Quản lý index metadata | Redis Set/ZSet hoặc database query |
| Finder theo field | Dựa trên secondary index hỗ trợ | Tự thiết kế query/index |
| Expiration event | Repository event listener | Keyspace notification riêng hoặc không dựa vào event |
| Mapping object | `RedisConverter` | JSON serializer/Hash mapper do ứng dụng chọn |
| Schema version | Theo mapping và application contract | Định nghĩa prefix/schema version tường minh |
| Atomic nhiều key | Không được mặc định bảo đảm | Lua/transaction/giao thức consistency |

### 21.1. Chuyển đổi an toàn theo namespace

Một lộ trình:

~~~text
Phase 1:
  Reader cũ -> Repository ở namespace cũ
  Reader mới -> Template ở namespace v2
  Nguồn dữ liệu chuẩn không đổi

Phase 2:
  Populate/backfill namespace v2
  Kiểm tra functionality và load profile

Phase 3:
  Đổi traffic dần sang reader v2
  Quan sát cache miss, latency, serializer errors

Phase 4:
  Ngừng ghi namespace cũ
  Dọn index/key cũ có kiểm soát
~~~

Nếu dữ liệu Redis là nguồn chuẩn duy nhất, migration càng cần chiến lược snapshot/backfill/dual-write an toàn, không thể chỉ chờ key cũ tự hết TTL như cache có thể tạo lại.

### 21.2. Dual write không tự atomic

Trong một thời gian, ứng dụng có thể ghi cả repository cũ và template mới. Nếu một lệnh thành công và lệnh còn lại lỗi, hai namespace lệch nhau. Cần:

- Xác định nguồn chuẩn.
- Thiết kế replay/reconciliation.
- Versioned records và idempotent upsert.
- Monitor mismatch.
- Tiêu chí chuyển hẳn sang format mới.

Đừng dùng một chuỗi Reactor `then(...)` để suy ra dual write sẽ atomic.

## 22. Testing Reactive Template đúng mô hình

### 22.1. StepVerifier

Với method trả về `Mono`:

~~~java
import reactor.test.StepVerifier;

@Test
void shouldSaveAndRead() {
    StepVerifier.create(store.save("u-101", "Hello"))
            .expectNext(true)
            .verifyComplete();

    StepVerifier.create(store.read("u-101"))
            .expectNext("Hello")
            .verifyComplete();
}
~~~

Đây là ví dụ test với Redis hoạt động; cần có dependency `reactor-test` và hạ tầng Redis test tương ứng. Kiểm tra `Mono<Boolean>` có thể phụ thuộc kết quả của Redis command và key hợp lệ.

### 22.2. Dùng Redis test instance

Testcontainers hoặc Redis instance dành riêng cho integration test giúp kiểm tra:

- Bytes thực tế sau serialization.
- TTL qua `TTL`/`PTTL`.
- `Mono.empty()` khi key không tồn tại.
- Error handling khi Redis bị ngắt kết nối.
- Duplicate writes và concurrent updates.
- Redis Cluster slot constraints nếu production dùng Cluster.
- Reactive listener/Streams offset nếu nghiệp vụ có dùng.

Mock đơn thuần không thể kiểm chứng rằng key/serializer được cấu hình đúng ở Redis.

### 22.3. Không dùng block trong production chỉ vì test làm vậy

Trong unit/integration tests, dùng StepVerifier hoặc `block()` ở một test thread có thể chấp nhận khi mục tiêu kiểm tra một publisher. Điều đó **không có nghĩa** dùng `block()` trong reactive HTTP request handler cũng an toàn.

### 22.4. Quan sát để đánh giá lựa chọn

Cần đo:

- P50/P95/P99 của Redis GET/SET.
- Số connection và pending requests của Lettuce.
- Reactor event-loop blocked time.
- Concurrency của `flatMap`.
- Cache hit/miss và fallback DB QPS.
- Redis CPU/memory/eviction.
- Serialization overhead và payload size.
- Retry count, timeouts, errors.
- Secondary index drift nếu tự quản lý.

Một codebase toàn `Mono` không được coi là reactive hiệu quả nếu phía dưới vẫn chủ yếu là blocking repository calls hoặc serialization/CPU work quá nặng trên event-loop.

## 23. Các tình huống lựa chọn thực tế

### Tình huống A: Cache sản phẩm trong WebFlux

**Yêu cầu:** đọc sản phẩm bằng reactive database và cache Redis 10 phút; không cần query Redis theo field.

**Chọn:** `ReactiveStringRedisTemplate` + JSON DTO + TTL.

Lý do: key-value access đơn giản, dễ compose cache-aside, không cần mô phỏng repository. Theo dõi dữ liệu cũ và invalidation sau database commit.

### Tình huống B: Redis là nơi lưu entity với index theo email

**Yêu cầu:** CRUD entity, tìm theo email và giữ index nhất quán khi TTL hết.

**Lựa chọn:** cân nhắc giữ imperative Redis Repository ở một adapter được cô lập (nếu tải cho phép), hoặc thiết kế custom reactive store/index lifecycle rõ ràng. Nếu tính nhất quán, unique constraint và query phức tạp là trọng tâm, cân nhắc datastore có reactive repository phù hợp.

Lý do: Template không tự tạo derived finder, secondary index hay expiration cleanup.

### Tình huống C: Rate limiter nhiều request đồng thời

**Yêu cầu:** đếm và kiểm tra quota nguyên tử với latency thấp.

**Chọn:** ReactiveRedisTemplate cho Redis primitive/Lua script.

Lý do: đây là bài toán Redis command và atomic server-side logic, không phải entity repository query.

### Tình huống D: Hệ thống có Redis CrudRepository từ trước

**Yêu cầu:** chuyển sang WebFlux theo giai đoạn, giữ tính đúng của hệ thống hiện tại.

**Chọn:** adapter boundedElastic tạm thời cho repository, chuyển các đường đơn giản sang reactive template sau khi có namespace/schema riêng.

Lý do: tránh chặn event-loop và giảm nguy cơ phá vỡ key layout cũ.

### Tình huống E: Gửi sự kiện cần xử lý lại

**Yêu cầu:** subscriber offline vẫn đọc lại được event; có ACK và retry.

**Chọn:** reactive Redis Streams operations hoặc broker bền vững thích hợp.

Lý do: reactive Pub/Sub không cung cấp retention; Streams có model log/consumer group, nhưng cần quản lý pending và idempotency.

### Tình huống F: Search và pagination phức tạp

**Yêu cầu:** lọc nhiều trường, sort, pagination, cập nhật liên tục.

**Chọn:** reactive repository của R2DBC/MongoDB/search service nơi query được hỗ trợ; dùng Redis template cho cache hoặc các thao tác có lợi thế Redis.

Lý do: không nên dựng hệ thống index thủ công trên Redis chỉ để đạt mục tiêu “Reactive Redis Repository”.

## 24. Những sai lầm thường gặp

### 24.1. “Spring Data có ReactiveCrudRepository nên Redis cũng tự có”

Không đúng. Interface nằm ở Spring Data Commons, nhưng khả năng tạo implementation là đặc thù từng store. Không được giả định Redis hỗ trợ reactive repository như Reactive MongoDB/R2DBC.

### 24.2. “Dùng Mono.just(repository.findById()) là non-blocking”

Sai. Repository đã chạy trước khi tạo Mono. Việc chỉ đổi return type không thay đổi I/O.

### 24.3. “Mono.fromCallable tự chuyển blocking I/O sang reactive driver”

Sai. Nó trì hoãn execution nhưng callable vẫn blocking. Có thể đặt `subscribeOn(Schedulers.boundedElastic())` để cô lập blocking code, nhưng đó chỉ là bridge.

### 24.4. “ReactiveRedisTemplate tự hỗ trợ @RedisHash/@Indexed/@TimeToLive”

Sai. Những annotation thuộc repository mapping. Với Template, ứng dụng chịu trách nhiệm cấu trúc dữ liệu, secondary index và TTL.

### 24.5. “Đổi Redis repository Hash sang Redis String nhưng giữ nguyên key không sao”

Sai. Redis Hash và String là data types khác nhau. Đụng key có thể sinh `WRONGTYPE` và làm hỏng index metadata.

### 24.6. “Chỉ cần flatMap là atomic”

Sai. `flatMap` là Reactor composition. Redis atomicity ở cấp command hoặc cơ chế transaction/Lua riêng.

### 24.7. “Reactive code không thể bị quá tải”

Sai. Quá nhiều publishers đang in-flight vẫn làm tăng pending commands, connections, memory và tải Redis. Giới hạn concurrency, timeout và queue là cần thiết.

### 24.8. “subscribe() trong service là cách chạy save tốt nhất”

Sai. Tự subscribe có thể tách side effect khỏi caller, khiến lỗi và cancellation không được quản lý đúng. Trả publisher cho layer chịu trách nhiệm.

### 24.9. “RedisCacheManager với @Cacheable là ReactiveRedisTemplate”

Không tương đương. Cache abstraction/RedisCacheManager có semantics và I/O model riêng; annotation có xử lý reactive return types trong một số phiên bản Spring nhưng không tạo Redis reactive repository.

### 24.10. “Reactive Redis giải quyết transaction giữa database và Redis”

Không. Reactive composition không tạo distributed transaction. Cần chiến lược consistency, outbox, versioning và retry.

## 25. Các câu hỏi tự kiểm tra

**Câu 1. Spring Data Redis có cung cấp một reactive repository thay thế trực tiếp cho CrudRepository không?**

Không theo Reactive Redis support được mô tả trong tài liệu Redis Repository/Reactive Redis của Spring Data Redis. API chính cho truy cập Redis non-blocking là ReactiveRedisTemplate và các Reactive Redis operations. Luôn đối chiếu version dự án nếu framework phát triển thêm khả năng mới.

**Câu 2. Nếu chỉ cần GET/SET với TTL trong WebFlux, nên dùng gì?**

`ReactiveStringRedisTemplate` với String/JSON hoặc `ReactiveRedisTemplate` có serialization context phù hợp.

**Câu 3. Vì sao ReactiveRedisTemplate không tự dọn @Indexed secondary indexes?**

Vì template thực hiện Redis commands được yêu cầu, không vận hành Redis Repository mapping/index lifecycle.

**Câu 4. Mono.fromCallable + boundedElastic có phải native reactive Redis I/O?**

Không. Nó cho phép cô lập blocking call khỏi event-loop nhưng vẫn sử dụng thread cho lời gọi blocking.

**Câu 5. Có nên gọi block() trong WebFlux handler?**

Không. `block()` làm chặn thread thực thi và có thể phá throughput/cause lỗi khi gọi trên event-loop.

**Câu 6. Khi cache miss, phương thức findById có được gọi database tự động không?**

Không, trừ khi ứng dụng tự compose fallback như `switchIfEmpty(source.findById(...))`. Template không có cache-aside tự động.

**Câu 7. TTL có tự lấy từ @TimeToLive trên DTO không?**

Không. Khi dùng reactive template phải cấu hình TTL ở thao tác ghi hoặc cơ chế riêng.

**Câu 8. Dùng ReactiveRedisTemplate có tránh được race khi nhiều worker sửa một key không?**

Không. Chọn lệnh atomic như `INCR`, hoặc Lua/transaction và idempotency phù hợp.

**Câu 9. Nếu Redis chỉ làm cache, nguồn dữ liệu chính nên đặt ở đâu?**

Ở hệ lưu trữ đáp ứng yêu cầu nghiệp vụ, chẳng hạn database với reactive repository hỗ trợ; Redis giữ dữ liệu có thể tái tạo và TTL/invalidation.

**Câu 10. Có thể dùng Redis Streams reactive thay cho Repository không?**

Streams phù hợp xử lý event log có retention/consumer group. Nó không cung cấp query-by-entity repository abstraction và không tự quản lý CRUD/index entity.

**Câu 11. Spring @Cacheable trên Mono có nghĩa mọi Redis I/O không blocking không?**

Không thể suy luận như vậy. Cần kiểm tra phiên bản Spring Framework, CacheManager/Cache implementation và cách Redis I/O được thực hiện.

**Câu 12. Tại sao cần namespace mới khi migration?**

Để tránh collision data type, serializer, keyspace metadata và TTL/index giữa repository cũ và template mới.

## 26. Hướng dẫn quyết định ngắn

~~~mermaid
flowchart TD
    A["Ứng dụng cần Redis trong reactive flow"] --> B{"Cần CRUD entity + finder/index tự động?"}
    B -- "Không" --> C{"Đang dùng String/JSON đơn giản?"}
    C -- "Có" --> D["ReactiveStringRedisTemplate"]
    C -- "Không" --> E["ReactiveRedisTemplate + serialization context"]
    B -- "Có" --> F{"Redis có phải nguồn dữ liệu chính?"}
    F -- "Không" --> G["Reactive R2DBC/Mongo repository + Redis reactive cache"]
    F -- "Có" --> H["Custom reactive Redis data-access adapter, thiết kế mapping/index/TTL"]
    H --> I{"Có Redis repository cũ cần giữ?"}
    I -- "Có" --> J["Bridge tạm boundedElastic và migration namespace"]
    I -- "Không" --> K["Triển khai và đo non-blocking I/O"]
~~~

Những yếu tố cần chốt khi thiết kế:

- Dữ liệu là **cache** hay **nguồn chuẩn**?
- Cần **Redis command trực tiếp** hay cần **query/mapping tự động**?
- Có secondary index/TTL không?
- Có cần atomic nhiều key hoặc xác nhận nghiệp vụ?
- Cần khả năng đọc lại event không?
- Connection factory có hỗ trợ reactive I/O phù hợp không?
- Có bao nhiêu request đồng thời và Redis chịu tải bao nhiêu?
- Dữ liệu cũ có phải được migration không?

## 27. Tổng kết

**Reactive Redis không có nghĩa Reactive Redis Repository.** Spring Data Redis cung cấp API Reactive Template/Reactive Operations cho các Redis commands và data structures, nhưng không thể mặc định mở rộng `ReactiveCrudRepository` để được Redis Repository reactive với mapping/query/TTL/index như phiên bản imperative.

Với các use case **cache, counter, rate limiting, key-value, Hash, Set, Sorted Set hoặc Streams**, lựa chọn trực tiếp là `ReactiveRedisTemplate` hoặc `ReactiveStringRedisTemplate` với serializer, key schema và TTL tường minh. Với **entity CRUD/query cần repository abstraction**, có thể sử dụng reactive datastore repository thực sự được hỗ trợ, hoặc tự xây adapter Reactive Template và chịu trách nhiệm mapping/index/consistency.

Nếu đang có Redis Repository cũ, hãy tránh gọi blocking methods ngay trên WebFlux event-loop; `boundedElastic` là giải pháp bridge có giới hạn. Khi migration, không ghi đè namespace/hash layout cũ bằng String/template mới nếu chưa có kế hoạch chuyển đổi. Và dù code dùng Mono/Flux, tính đúng đắn vẫn phụ thuộc Redis atomic commands, TTL, transaction semantics, retry, idempotency và khả năng xử lý lỗi — **reactive chỉ thay đổi mô hình lập trình I/O, không thay thế thiết kế dữ liệu**.

## Tài liệu tham khảo

- Spring Data Redis — [Reactive Redis support](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): ReactiveRedisOperations, ReactiveRedisTemplate và reactive connections.
- Spring Data Redis — [Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity mapping, repository model, keyspace và indexes.
- Spring Data Redis — [Redis Templates](https://docs.spring.io/spring-data/redis/reference/redis/template.html): RedisTemplate, serialization và Redis operations.
- Spring Data Redis — [Redis Serialization](https://docs.spring.io/spring-data/redis/reference/redis/serializers.html): RedisSerializer, serialization context và các định dạng.
- Spring Data Redis — [Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Stream operations, consumer groups và record mapping.
- Spring Data Commons — [Reactive Repositories](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html): repository interfaces và đặc thù implementation theo từng datastore.
- Spring Framework — [WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive request handling và non-blocking execution.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, composition, scheduling và backpressure.
- Redis — [Key expiration](https://redis.io/docs/latest/commands/expire/): TTL ở Redis server.
- Redis — [Transactions](https://redis.io/docs/latest/develop/interact/transactions/): MULTI/EXEC, atomicity và giới hạn.
