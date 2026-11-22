# Cấu hình ReactiveRedisConnectionFactory và ReactiveRedisTemplate

Trong **Spring Data Redis**, ứng dụng có thể truy cập Redis theo mô hình đồng bộ qua `RedisTemplate` hoặc theo mô hình phản ứng qua `ReactiveRedisTemplate<K,V>`. Mô hình phản ứng phù hợp với Spring WebFlux và Project Reactor khi ứng dụng cần hợp thành các thao tác I/O bất đồng bộ mà không giữ một thread ứng dụng chỉ để chờ Redis trả lời.

Hai thành phần quan trọng là:

- `ReactiveRedisConnectionFactory`: interface cung cấp kết nối Redis có API reactive;
- `ReactiveRedisTemplate<K,V>`: lớp thao tác Redis ở mức cao, trả `Mono`/`Flux` và sử dụng serialization context cho key/value.

Cấu hình đúng đòi hỏi hơn việc đổi tên bean từ `RedisTemplate` sang `ReactiveRedisTemplate`. Cần chọn client hỗ trợ reactive, thiết lập endpoint/topology và TLS, thống nhất serializer, hiểu cách subscription kích hoạt I/O, xử lý timeout và không nhầm reactive Redis với giao dịch phân tán hoặc cache luôn nhất quán.

## 1. Phân biệt imperative và reactive Redis

Với RedisTemplate đồng bộ:

```java
String status =
        stringRedisTemplate.opsForValue().get("user:42:status");
```

Thread gọi chờ một kết quả được trả về. Với Reactive Redis:

```java
Mono<String> status =
        reactiveStringRedisTemplate.opsForValue()
                .get("user:42:status");
```

`Mono<String>` không phải giá trị String đã được đọc; nó là publisher mô tả một kết quả bất đồng bộ. Khi có subscription, đường xử lý Redis được thực thi và publisher phát dữ liệu, hoàn tất rỗng hoặc phát lỗi.

| Khía cạnh | Imperative | Reactive |
|---|---|---|
| Template | `RedisTemplate`, `StringRedisTemplate` | `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate` |
| Factory | `RedisConnectionFactory` | `ReactiveRedisConnectionFactory` |
| Một kết quả | `String`, `Long`, `Boolean` hoặc `null` | `Mono<T>` |
| Nhiều kết quả | Collection, cursor, callback | `Flux<T>` |
| Phối hợp thao tác | Các lời gọi tuần tự | `map`, `flatMap`, `then`, `zip`... |
| Thông báo lỗi | Exception | Tín hiệu `onError` trong publisher |
| Không có dữ liệu | `null` hoặc collection rỗng tùy API | `Mono.empty()` hoặc `Flux.empty()` |
| Chờ kết quả | Thread có thể bị blocking | Không cần chặn thread request khi dùng đúng reactive end-to-end |

**Reactive không tự khiến Redis nhanh hơn.** Nó giúp ứng dụng sử dụng tài nguyên thread hiệu quả trong khi chờ I/O. Nếu code vẫn gọi JDBC đồng bộ hoặc `Thread.sleep` trên event-loop, lợi ích có thể bị triệt tiêu.

## 2. Luồng kiến trúc từ WebFlux đến Redis

```text
HTTP Client
    |
    v
Spring WebFlux Controller
    |
    v
Service trả Mono/Flux
    |
    v
ReactiveRedisTemplate<K, V>
    |
    +--> SerializationContext: key/value/hash
    |
    v
ReactiveRedisConnectionFactory
    |
    v
Lettuce reactive connection
    |
    v
Redis Standalone / Sentinel / Cluster
```

`ReactiveRedisConnectionFactory` là abstraction về kết nối. Nó không phải một Redis server và cũng không tự thực hiện mapping entity như Repository. `ReactiveRedisTemplate` sử dụng connection factory và serializer để gửi các lệnh Redis.

Trong Spring Data Redis, **Lettuce** là Redis client phổ biến hỗ trợ reactive. `LettuceConnectionFactory` có thể triển khai cả contract imperative và reactive, nên một ứng dụng có thể chạy cả hai nhóm API nếu thực sự cần.

## 3. Dependency và môi trường

Ví dụ Gradle cho Spring Boot WebFlux:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

Starter Redis cung cấp Spring Data Redis cùng client phù hợp theo cơ chế quản lý dependency của Spring Boot. `spring-boot-starter-webflux` cần khi xây dựng HTTP API WebFlux; nếu chỉ muốn gọi reactive Redis bên trong một ứng dụng khác, không bắt buộc phải dùng WebFlux cho toàn bộ ứng dụng.

Các điều kiện:

1. Redis có thể kết nối từ máy chạy ứng dụng.
2. Driver thực sự hỗ trợ `ReactiveRedisConnectionFactory`.
3. Xác định Redis standalone, Sentinel hay Cluster trước khi cấu hình.
4. Authentication/TLS/timeout được quản lý qua environment hoặc secret manager.
5. Spring Data Redis và Lettuce sử dụng version tương thích (nên để BOM của Spring Boot quản lý).
6. Code gọi reactive Redis không biến thành blocking bằng `block()` ở đường xử lý WebFlux.

## 4. Sử dụng Spring Boot auto-configuration

Nếu đã dùng starter Redis và Lettuce, cách đơn giản thường là để Spring Boot tạo `LettuceConnectionFactory` từ `application.yml`.

Ví dụ cho môi trường Redis local:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

Khi triển khai production, các giá trị host, port, mật khẩu và chứng chỉ nên lấy từ cấu hình môi trường/secret manager. Không hard-code password thật trong mã hoặc tệp được commit vào repository.

Trong các phiên bản Spring Boot hiện đại, các thuộc tính Redis thường nằm dưới `spring.data.redis`; cần đối chiếu với version Spring Boot đang sử dụng để tránh một property không được nhận.

Khi connection factory đã được Boot tạo, ứng dụng có thể inject bằng interface reactive:

```java
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.stereotype.Component;

@Component
public class RedisConnectionHolder {
    private final ReactiveRedisConnectionFactory factory;

    public RedisConnectionHolder(
            ReactiveRedisConnectionFactory factory) {
        this.factory = factory;
    }
}
```

Ví dụ chỉ minh họa wiring. Business service nên gọi `ReactiveRedisTemplate` thay vì lấy low-level connection cho mọi lệnh thường dùng.

### 4.1. Một LettuceConnectionFactory cho hai API

```text
LettuceConnectionFactory
    |
    +--> RedisConnectionFactory
    |        |
    |        +--> RedisTemplate
    |
    +--> ReactiveRedisConnectionFactory
             |
             +--> ReactiveRedisTemplate
```

Cùng factory không có nghĩa các lệnh imperative và reactive chia sẻ cùng transaction hoặc cùng thread context. Nếu cần cả hai, hãy tách rõ use case và tránh vô tình blocking trong WebFlux.

### 4.2. Không tự tạo thêm bean nếu Boot đã có

Nếu auto-configuration đã cung cấp factory, thêm một `LettuceConnectionFactory` thủ công có thể khiến injection mơ hồ hoặc dùng hai bộ cấu hình Redis khác nhau. Chỉ tạo factory riêng khi có lý do thực tế như custom connection, nhiều Redis deployment hoặc tùy chọn driver cần điều chỉnh.

## 5. Khai báo LettuceConnectionFactory thủ công

Không dùng auto-configuration hoặc cần cấu hình tường minh:

```java
package example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ManualRedisConnectionConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration standalone =
                new RedisStandaloneConfiguration("localhost", 6379);

        return new LettuceConnectionFactory(standalone);
    }
}
```

Bean do Spring quản lý sẽ thực hiện lifecycle initialization và destruction theo các contract tương ứng của factory.

Đây chỉ là ví dụ **standalone**, không nên áp dụng nguyên xi cho Redis Cluster hay Sentinel:

| Môi trường | Cần cấu hình |
|---|---|
| Standalone | Endpoint, TLS, username/password, timeout |
| Sentinel | Master name và các sentinel endpoints |
| Cluster | Danh sách node, slot routing, topology refresh, failover |
| Managed Redis | Endpoint/ACL/TLS và giới hạn của nhà cung cấp |

Một cấu hình chỉ biết một endpoint standalone không mô tả đầy đủ topology Redis Cluster. Khi có nhiều factory, chọn bean cụ thể bằng `@Qualifier` cho từng template.

## 6. Khai báo ReactiveRedisTemplate<String, String>

Để bắt đầu, chọn key và value dạng chuỗi, tránh phức tạp về converter:

```java
package example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration
public class ReactiveRedisTemplateConfig {

    @Bean("appReactiveStringTemplate")
    public ReactiveRedisTemplate<String, String> appReactiveStringTemplate(
            ReactiveRedisConnectionFactory factory) {

        return new ReactiveRedisTemplate<>(
                factory,
                RedisSerializationContext.string());
    }
}
```

`RedisSerializationContext.string()` cung cấp serialization context phù hợp để làm việc với key/value dạng chuỗi.

Service dùng template:

```java
package example.redis;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class UserStatusCache {

    private final ReactiveRedisTemplate<String, String> redis;

    public UserStatusCache(
            @Qualifier("appReactiveStringTemplate")
            ReactiveRedisTemplate<String, String> redis) {
        this.redis = redis;
    }

    public Mono<Boolean> put(String userId, String status) {
        String key = "user:status:" + userId;
        return redis.opsForValue()
                .set(key, status, Duration.ofMinutes(5));
    }

    public Mono<String> get(String userId) {
        return redis.opsForValue().get("user:status:" + userId);
    }

    public Mono<Long> delete(String userId) {
        return redis.delete("user:status:" + userId);
    }
}
```

`set(...)` phát một kết quả Boolean; `get(...)` phát một String hoặc hoàn tất rỗng nếu key không tồn tại; `delete(...)` cho biết số key được xóa. Các tín hiệu lỗi Redis nằm trong publisher và có thể được xử lý bằng Reactor operators.

### ReactiveStringRedisTemplate

Spring Data Redis còn có shortcut cho dữ liệu chuỗi:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class FeatureFlagReader {
    private final ReactiveStringRedisTemplate redis;

    public FeatureFlagReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> read(String name) {
        return redis.opsForValue().get("feature:" + name);
    }
}
```

Trong cấu hình Spring Boot phù hợp, `ReactiveStringRedisTemplate` có thể được auto-configure. Nếu đã có bean này và chỉ dùng key/value chuỗi, không nhất thiết tạo thêm một typed template tương đương.

## 7. RedisSerializationContext là phần quan trọng của cấu hình

Khi tạo `ReactiveRedisTemplate<K,V>`, constructor cần `RedisSerializationContext<K,V>` để biết cách chuyển các kiểu Java thành byte mà Redis nhận.

| Loại dữ liệu | Java type | Ví dụ serialization |
|---|---|---|
| Key | `String` | UTF-8 string |
| Value | `String` | UTF-8 string |
| Value | `ProductSnapshot` | JSON với schema rõ ràng |
| Hash key | `String` | UTF-8 field name |
| Hash value | String/DTO | String hoặc JSON theo hợp đồng ứng dụng |

Nếu key được tạo bằng `StringRedisSerializer` nhưng template đọc sử dụng JDK serialization, hai phía có thể tạo **byte key khác nhau** cho cùng chuỗi Java. Redis có key nhưng template vẫn trả cache miss.

Ví dụ Redis CLI tạo:

```redis
SET product:42:name Desk
```

Một template có key serializer nhị phân không mặc nhiên đọc được khóa này khi gọi Java `get("product:42:name")`. Cần thống nhất wire format giữa các writer/reader, không sửa Redis key thủ công khi nguyên nhân là serializer.

## 8. Cấu hình template cho DTO JSON

Khi cần lưu object, nên chọn target Java type và serializer tường minh.

DTO:

```java
package example.product;

public record ProductSnapshot(
        String productId,
        String name,
        long priceVnd,
        long sourceVersion
) {}
```

Template JSON:

```java
package example.redis;

import example.product.ProductSnapshot;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductReactiveRedisConfig {

    @Bean("productSnapshotRedisTemplate")
    public ReactiveRedisTemplate<String, ProductSnapshot> productTemplate(
            ReactiveRedisConnectionFactory factory) {

        var keySerializer = new StringRedisSerializer();
        var jsonSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        RedisSerializationContext<String, ProductSnapshot> context =
                RedisSerializationContext
                        .<String, ProductSnapshot>newSerializationContext(
                                keySerializer)
                        .value(jsonSerializer)
                        .hashKey(keySerializer)
                        .hashValue(jsonSerializer)
                        .build();

        return new ReactiveRedisTemplate<>(factory, context);
    }
}
```

Cấu hình trên giữ key là String và value là JSON. Một key như `cache:product:v1:42` chứa payload của `ProductSnapshot`. Tương tự, hash value serializer chỉ đúng khi từng field hash thực sự chứa object định dạng đó; nếu hash field là chuỗi hoặc số, cần lựa chọn serializer riêng cho mô hình dữ liệu thực tế.

API constructor và lựa chọn Jackson serializer có thể thay đổi/deprecate theo các nhánh Spring Data Redis. Khi nâng version, cần đối chiếu dependency đang sử dụng. Nguyên tắc không thay đổi: **serialization context phải tương thích với dữ liệu Redis và kiểu Java mà application mong đợi**.

### Schema migration

Một deployment mới có thể đọc entry do phiên bản cũ tạo. Nếu DTO đổi cấu trúc, lỗi deserialize có thể xảy ra. Có thể dùng prefix version:

```text
cache:product:v1:42
cache:product:v2:42
```

Kết hợp TTL, migration/rebuild có kiểm soát và JSON backward compatibility để xử lý schema cũ. Không giả định đổi Java record rồi Redis tự chuyển mọi entry đang lưu sang format mới.

## 9. Reactive publisher được thực thi khi có subscription

Đoạn sau **không phải lệnh ghi hoàn chỉnh nếu publisher bị bỏ đi**:

```java
public void setFlag() {
    redis.opsForValue().set("flags:checkout", "ENABLED");
    // Mono bị bỏ đi; không có subscriber.
}
```

Nên trả publisher:

```java
public Mono<Boolean> setFlag() {
    return redis.opsForValue().set("flags:checkout", "ENABLED");
}
```

Nếu muốn đảm bảo ghi hoàn tất rồi mới đọc:

```java
public Mono<String> writeThenRead() {
    return redis.opsForValue()
            .set("flags:checkout", "ENABLED")
            .then(redis.opsForValue().get("flags:checkout"));
}
```

`then(...)` tạo thứ tự giữa hai thao tác trong cùng reactive chain, nhưng **không làm chúng nguyên tử**. Client khác vẫn có thể sửa key giữa `SET` và `GET`.

### Không gọi subscribe() bên trong service một cách tùy tiện

```java
public Mono<ProductSnapshot> save(ProductSnapshot product) {
    redis.opsForValue()
            .set("cache:product:v1:" + product.productId(), product)
            .subscribe();  // Fire-and-forget, khó quản lý lỗi.

    return Mono.just(product);
}
```

Lỗi ở đây là subscription tự tạo một công việc phụ ngoài pipeline mà caller quan sát. Response có thể trả trước khi Redis ghi xong; lỗi Redis không còn được truyền theo đường trả về.

Khi việc ghi Redis phải được quan sát:

```java
public Mono<ProductSnapshot> save(ProductSnapshot product) {
    return redis.opsForValue()
            .set("cache:product:v1:" + product.productId(), product)
            .thenReturn(product);
}
```

Nếu Redis chỉ là cache best-effort, ứng dụng có thể quyết định bỏ qua lỗi cache sau khi ghi nguồn chính, nhưng phải có log/metric và quy tắc nhất quán rõ ràng, không đơn giản giải quyết bằng `subscribe()` rời rạc.

## 10. WebFlux controller trả về Mono

```java
package example.redis;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class UserStatusController {
    private final UserStatusCache cache;

    public UserStatusController(UserStatusCache cache) {
        this.cache = cache;
    }

    @GetMapping("/users/{id}/status")
    public Mono<ResponseEntity<String>> read(@PathVariable String id) {
        return cache.get(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

WebFlux subscribe khi cần tạo response. Không cần gọi `block()` hoặc `subscribe()` ở controller.

Nếu Redis key không tồn tại, `Mono.empty()` có thể chuyển thành HTTP 404 theo hợp đồng API. Nếu Redis không kết nối được, lỗi sẽ phát qua `onError` và **không nên mặc nhiên biến lỗi hạ tầng thành 404**.

## 11. Phân biệt Mono.empty và Mono.error

Ba dạng kết quả khác nhau:

- `Mono.just(value)`: có một giá trị;
- `Mono.empty()`: không phát giá trị rồi hoàn tất;
- `Mono.error(exception)`: lỗi trong quá trình thực thi.

Ví dụ giá trị mặc định cho key không tồn tại:

```java
public Mono<String> readOrUnknown(String userId) {
    return redis.opsForValue()
            .get("user:status:" + userId)
            .defaultIfEmpty("UNKNOWN");
}
```

Ví dụ fallback có chủ đích khi Redis lỗi:

```java
public Mono<String> flagOrSafeDefault(String name) {
    return redis.opsForValue()
            .get("feature:" + name)
            .onErrorResume(ex -> Mono.just("DISABLED"));
}
```

Một fallback `DISABLED` có thể phù hợp với feature flag. Nhưng với quyền truy cập, quota hoặc tiền, việc dùng default có thể gây lỗi bảo mật/nghiệp vụ. Phải xác định fail-open hay fail-closed theo yêu cầu, không tùy tiện dùng `onErrorResume` để giấu sự cố.

## 12. Cache-aside reactive với nguồn dữ liệu riêng

Giả sử dữ liệu chuẩn đến từ một nguồn reactive:

```java
public interface ReactiveProductSource {
    Mono<ProductSnapshot> findById(String productId);
}
```

Cache service:

```java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCacheService {

    private final ReactiveRedisTemplate<String, ProductSnapshot> redis;
    private final ReactiveProductSource source;

    public ReactiveProductCacheService(
            @Qualifier("productSnapshotRedisTemplate")
            ReactiveRedisTemplate<String, ProductSnapshot> redis,
            ReactiveProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public Mono<ProductSnapshot> findById(String id) {
        String key = "cache:product:v1:" + id;

        return redis.opsForValue()
                .get(key)
                .switchIfEmpty(Mono.defer(() ->
                        source.findById(id)
                                .flatMap(product ->
                                        redis.opsForValue()
                                                .set(key, product,
                                                        Duration.ofMinutes(5))
                                                .thenReturn(product))));
    }
}
```

Ý nghĩa:

```text
Redis GET
  |
  +-- HIT --> trả ProductSnapshot
  |
  +-- MISS --> source.findById
                  |
                  +-- không có dữ liệu --> Mono.empty()
                  |
                  +-- có dữ liệu --> Redis SET TTL 5 phút
                                       |
                                       v
                                 trả ProductSnapshot
```

`Mono.defer(...)` giúp tạo đường đọc nguồn khi xảy ra cache miss. Ví dụ chờ cache SET hoàn tất mới trả product; có thể thay đổi chính sách nếu Redis chỉ là best-effort cache.

### Cache failure fallback

Nếu nguồn chuẩn vẫn phục vụ được khi Redis mất kết nối, có thể chọn fallback:

```java
public Mono<ProductSnapshot> findByIdWithFallback(String id) {
    String key = "cache:product:v1:" + id;

    return redis.opsForValue().get(key)
            .switchIfEmpty(Mono.defer(() ->
                    source.findById(id).flatMap(product ->
                            redis.opsForValue()
                                    .set(key, product, Duration.ofMinutes(5))
                                    .onErrorResume(error -> Mono.just(false))
                                    .thenReturn(product))))
            .onErrorResume(error -> source.findById(id));
}
```

Mọi fallback cần có metric/log lỗi Redis, vì nếu không ứng dụng có thể âm thầm đẩy toàn bộ cache traffic về database. Không áp dụng fallback khi Redis là nguồn dữ liệu nghiệp vụ duy nhất hoặc tính năng yêu cầu fail-closed.

### Cache stampede

Khi nhiều request đồng thời cache miss, nhiều truy vấn có thể cùng đi về nguồn rồi cùng ghi Redis. Reactive I/O không tự tạo single-flight hoặc chặn stale refill. Các phương án tùy yêu cầu gồm giới hạn concurrency, dedup theo key, TTL jitter, version-aware update và invalidation đáng tin cậy.

## 13. Timeout, retry và xử lý lỗi kết nối

Khi Redis không phản hồi, reactive API không tự bảo đảm thời gian xử lý luôn nằm trong SLA của HTTP request. Cần phân biệt:

- **Connection timeout:** giới hạn thời gian thiết lập kết nối TCP/TLS;
- **Redis command timeout:** thời gian client chờ một command hoàn tất;
- **Pipeline timeout:** giới hạn thời gian mà một publisher được phép chưa phát kết quả theo quy tắc nghiệp vụ.

Ví dụ timeout ở Reactor:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<String> readWithTimeout(String key) {
    return redis.opsForValue()
            .get(key)
            .timeout(Duration.ofSeconds(1));
}
```

Nếu hết hạn, publisher phát lỗi timeout. **Timeout ở phía client không bảo đảm Redis server chưa thực thi lệnh.** Command có thể đã đến Redis và chạy trước khi client hủy việc chờ phản hồi.

### Retry phải xét idempotency

```java
import java.time.Duration;
import reactor.util.retry.Retry;

public Mono<String> readWithRetry(String key) {
    return redis.opsForValue().get(key)
            .timeout(Duration.ofSeconds(1))
            .retryWhen(Retry.backoff(
                    2, Duration.ofMillis(100)));
}
```

Đây chỉ minh họa cấu trúc; production cần giới hạn retry và **lọc lỗi tạm thời**, không thử lại vô điều kiện đối với lỗi xác thực, serializer hoặc permission.

| Redis command | Retry sau timeout | Nguy cơ |
|---|---|---|
| `GET` | Thường tương đối an toàn | Tăng tải và độ trễ; dữ liệu có thể thay đổi giữa các lần |
| `SET key value` | Tùy ngữ nghĩa | Ghi trùng có thể idempotent nhưng TTL có thể bị làm mới |
| `DEL key` | Thường idempotent về trạng thái cuối | Số lượng key xóa được thay đổi |
| `INCR`/`DECR` | Không nên retry mù quáng | Lệnh đầu có thể đã chạy, khiến tăng/giảm hai lần |
| `XADD` | Không nên retry mù quáng | Có thể tạo message trùng |
| Lua có side effect | Tùy nội dung | Nguyên tử không đồng nghĩa với retry an toàn |

Nếu thao tác quan trọng có thể được thực hiện trùng, nên dùng operation ID, idempotency key hoặc version để nhận diện việc đã xử lý.

### Fallback khi Redis chỉ là cache

Có thể đọc lại nguồn chuẩn nếu cache bị lỗi:

```java
return redis.opsForValue().get(key)
        .onErrorResume(error -> source.findById(id));
```

Cần log/metric số lần fallback để tránh outage Redis âm thầm làm quá tải database. Đừng dùng cùng một fallback cho rate limiting, quyền truy cập hoặc giá trị dùng trong quyết định tài chính mà chưa đánh giá fail-open/fail-closed.

## 14. Không block trên WebFlux event-loop

Anti-pattern:

```java
@GetMapping("/users/{id}/status")
public String get(@PathVariable String id) {
    return redis.opsForValue()
            .get("user:status:" + id)
            .block();
}
```

`block()` chờ publisher ngay trên thread hiện tại. Trong ứng dụng WebFlux, điều này có thể làm mất lợi ích non-blocking, tăng latency và gây lỗi nếu được gọi trên thread không cho phép blocking.

Nên giữ publisher xuyên boundary HTTP:

```java
@GetMapping("/users/{id}/status")
public Mono<String> get(@PathVariable String id) {
    return redis.opsForValue().get("user:status:" + id);
}
```

Nếu nguồn dữ liệu còn là JDBC blocking:

```java
return Mono.fromCallable(() -> jdbcDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là cách cô lập tác vụ blocking sang scheduler phù hợp trong giai đoạn chuyển đổi, **không biến JDBC thành API reactive**. Khi cần hiệu năng lớn nên cân nhắc datasource/driver reactive hoặc ranh giới service rõ ràng.

`subscribeOn` và `publishOn` không tự làm lệnh Redis nhanh hơn; thêm scheduler vô lý chỉ tăng context switching. Lettuce đã có cơ chế Redis I/O bất đồng bộ.

## 15. Quản lý connection factory trong production

Một connection factory nên được tái sử dụng và quản lý lifecycle bởi Spring, không tạo client mới cho từng HTTP request.

| Khía cạnh | Cần xác định |
|---|---|
| Topology | Standalone/Sentinel/Cluster và khả năng failover |
| Credentials | Redis ACL user/password, secret rotation, không log secret |
| TLS | Có bắt buộc mã hóa kết nối và xác minh chứng chỉ không |
| Timeout | Connect/command/request timeout và cách retry |
| Connection reuse | Driver có multiplexing/chia sẻ kết nối thế nào |
| Serializer | Key/value wire format thống nhất giữa writer và reader |
| Cluster routing | Client nhận diện slot, topology refresh và resharding |
| Shutdown | Đóng factory/client và tài nguyên nền theo Spring lifecycle |
| Metrics | Command latency, timeout, reconnect, số connections |

Không nên tăng số connection hay thread vô hạn. Với Lettuce, I/O bất đồng bộ có thể phục vụ nhiều command trên tài nguyên kết nối phù hợp; cấu hình tối ưu phải dựa trên throughput, payload size, latency, memory và giới hạn Redis thực tế.

Nếu ứng dụng kết nối hai Redis deployment, cần hai factory và template đặt tên rõ ràng, có `@Qualifier` để tránh thao tác nhầm cluster. Trong môi trường managed Redis, chú ý TLS, ACL và giới hạn số kết nối mỗi tenant.

## 16. Reactive Redis không tự tạo giao dịch phân tán

Một database transaction và một Redis write là các thao tác trên hai tài nguyên:

```text
SQL BEGIN
    |
    +--> UPDATE database
    |
    +--> Reactive Redis SET (nếu đã subscribe)
    |
SQL COMMIT hoặc ROLLBACK
```

Nếu Redis đã ghi xong nhưng SQL rollback, Redis có thể mang trạng thái không còn đúng. Nếu SQL commit rồi Redis lỗi, cache có thể chưa được đồng bộ.

Không đồng nhất các cơ chế:

- `RedisTemplate.setEnableTransactionSupport(true)` của imperative template;
- `ReactiveRedisTemplate` trả Reactor publishers;
- `@Transactional` sử dụng `JpaTransactionManager` hoặc `DataSourceTransactionManager`;
- Reactor transaction context của một `ReactiveTransactionManager`.

Chúng có vòng đời và contract khác nhau. Không mặc định annotation trên Java method khiến toàn bộ publisher Redis nằm trong cùng commit nguyên tử với SQL.

Khi cần đọc rồi cập nhật có điều kiện trên một Redis key, có thể dùng lệnh Redis nguyên tử hoặc Lua script ở phạm vi key/slot hợp lệ. Nhưng atomicity của Redis cũng không biến SQL và Redis thành cùng một giao dịch.

Nếu Redis là cache của database, có thể chọn invalidation sau commit, transactional outbox, version gating hoặc retry/reconciliation theo yêu cầu nhất quán.

## 17. Các nhóm thao tác ReactiveRedisTemplate

Ví dụ string operations:

```java
Mono<Boolean> wrote =
        redis.opsForValue().set("config:mode", "READY");

Mono<String> loaded =
        redis.opsForValue().get("config:mode");

Mono<Boolean> hasExpiry =
        redis.expire("config:mode", Duration.ofMinutes(3));

Mono<Long> removed =
        redis.delete("config:mode");
```

Hash operations được cung cấp qua `opsForHash()`; cần dùng serializer phù hợp cho hash key/value.

```java
Mono<Boolean> wroteField =
        redis.opsForHash()
                .put("user:42", "status", "ACTIVE");

Mono<?> value =
        redis.opsForHash()
                .get("user:42", "status");
```

Các kiểu generic Java của hash operations có thể cần xác định tường minh thông qua `ReactiveHashOperations` để phù hợp với template và compiler. Không giả định DTO serializer của value sẽ đúng cho mọi hash field là string.

### Duyệt key bằng Flux

```java
import org.springframework.data.redis.core.ScanOptions;
import reactor.core.publisher.Flux;

Flux<String> keys =
        redis.scan(ScanOptions.scanOptions()
                .match("cache:product:v1:*")
                .count(100)
                .build());
```

`SCAN` không cung cấp snapshot nguyên tử: trong lúc Redis ghi/xóa, có thể trả key trùng hoặc thấy tập key thay đổi. Trong Redis Cluster phải biết API đang quét node nào và cách bao phủ các primary; không dùng quét toàn bộ keyspace trong đường HTTP request phổ biến.

### Backpressure

`Flux` hỗ trợ demand từ downstream, nhưng **không** có nghĩa mọi Redis command hoặc toàn bộ hệ thống downstream tự có bảo đảm backpressure. Giới hạn độ đồng thời khi cần:

```java
Flux<String> ids = Flux.just("42", "43", "44");

Flux<ProductSnapshot> products =
        ids.flatMap(id -> cacheService.findById(id), 4);
```

Concurrency `4` chỉ minh họa. Số phù hợp phụ thuộc Redis, database, memory và tốc độ downstream. Nếu consumer xử lý chậm, chỉ tăng concurrency có thể khiến hệ thống quá tải.

## 18. Những lỗi cấu hình thường gặp

### Không tìm thấy ReactiveRedisConnectionFactory

Các nguyên nhân có thể gồm thiếu starter/client reactive, connector hiện tại chỉ hỗ trợ imperative, auto-configuration bị loại, hoặc bean nằm ngoài phạm vi Spring scan. Nên kiểm tra dependency và bean thực tế trước khi tạo một factory mới.

### Có nhiều connection factory

Nếu vừa để Boot auto-configure vừa khai báo manual factory, injection có thể mơ hồ hoặc service dùng nhầm Redis deployment. Dùng bean name/qualifier và cấu hình một nguồn cho mỗi topology rõ ràng.

### Redis có key nhưng get() trả empty

Kiểm tra key serializer, database index, prefix, topology, TTL, publisher đã subscribe chưa và operator có chuyển lỗi thành empty không. Không vội kết luận Redis mất dữ liệu.

### Lệnh SET không chạy

Nếu service gọi `set(...)` rồi bỏ qua `Mono`, publisher có thể chưa được subscribe. Trả publisher hoặc nối vào reactive chain bằng `flatMap`/`then`.

### block() trên event-loop

Nếu code gọi `block()` trong WebFlux controller hoặc xử lý JDBC blocking trực tiếp trên event-loop, throughput/latency có thể giảm nghiêm trọng. Giữ luồng non-blocking và chỉ cô lập phần blocking thực sự cần thiết.

### Serializer lỗi sau nâng phiên bản

Đổi DTO/JSON format nhưng Redis còn entry cũ gây deserialize error. Cần key namespace version, migration/TTL và thống nhất codec.

### Timeout rồi retry side effect

`INCR` hoặc `XADD` có thể đã chạy trước khi caller mất phản hồi. Retry không có operation ID có thể làm tăng lặp hoặc message trùng.

### Cache fallback che mất outage

`onErrorResume(ex -> Mono.empty())` có thể biến Redis connection error thành cache miss. Nếu không có metric, hệ thống bị lỗi nhưng API vẫn trả kết quả giả như bình thường. Phân loại lỗi rõ ràng.

## 19. Quan sát và bảo mật

Một ứng dụng reactive có thể chịu tải đồng thời cao, nên cần đo cả Redis và đường xử lý downstream:

| Metric | Ý nghĩa |
|---|---|
| Redis command latency | Thời gian của GET/SET/DELETE theo operation |
| Redis error/timeout rate | Lỗi kết nối, timeout, authentication hoặc command |
| Redis reconnect count | Mức độ bất ổn mạng/failover |
| Cache hit/miss rate | Hiệu quả giảm tải nguồn |
| Fallback-to-source rate | Mức độ traffic quay về database khi Redis lỗi |
| Reactor pipeline timeout | HTTP request vượt ngưỡng chờ I/O |
| Serializer errors | Mismatch giữa dữ liệu Redis và Java DTO |
| Redis memory/eviction | Áp lực RAM, key bị loại do eviction policy |
| Connection/event-loop saturation | Thiếu tài nguyên phía client |
| Downstream datasource latency | Tránh đổ lỗi Redis cho database chậm |

Không ghi password Redis, access token, session secret hoặc payload người dùng vào log. Với tracing, ưu tiên operation name, thời gian, loại lỗi và key namespace đã được làm mờ.

Dùng Redis ACL giới hạn command/keyspace mà service thực sự cần. Nếu yêu cầu TLS, phải xác minh chứng chỉ đúng thay vì tắt certificate validation. Khi có nhiều instance, tính tổng mức kết nối đến Redis, không chỉ số connection của một process đơn lẻ.

## 20. Kiểm thử Reactive Redis bằng StepVerifier

Project Reactor cung cấp `StepVerifier` để xác minh các tín hiệu của `Mono` hoặc `Flux`. Ví dụ:

```java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class UserStatusCacheTest {

    private final UserStatusCache cache;

    UserStatusCacheTest(UserStatusCache cache) {
        this.cache = cache;
    }

    @Test
    void writesAndReadsStatus() {
        StepVerifier.create(cache.put("lab-42", "ACTIVE"))
                .expectNext(true)
                .verifyComplete();

        StepVerifier.create(cache.get("lab-42"))
                .expectNext("ACTIVE")
                .verifyComplete();
    }
}
```

Đây là phần thân test minh họa; muốn chạy dưới Spring cần khởi tạo test context và inject `UserStatusCache`, ví dụ qua `@SpringBootTest`, cùng Redis test instance. Không sử dụng Redis production trong integration test.

Các tình huống nên kiểm thử:

1. `put()` thực thi khi có subscription, rồi `get()` trả dữ liệu.
2. Key không tồn tại làm `Mono` hoàn tất rỗng, không tự phát error.
3. Ghi kèm TTL và xác nhận key hết hạn theo thời gian Redis.
4. JSON value được serialize/deserialize đúng type `ProductSnapshot`.
5. Redis không khả dụng: publisher phát error hoặc chạy fallback theo contract.
6. Timeout có được giới hạn, retry có gây lặp side effect không.
7. Cache miss đồng thời: bao nhiêu request cùng truy vấn source.
8. Hai application versions có cùng key schema/serializer hay không.
9. Keyspace, Redis database index và cluster routing có đúng với config.
10. Khi request bị hủy, có fire-and-forget side effect nào còn hoạt động ngoài dự kiến.

### Kiểm tra bằng Redis CLI

Trong môi trường thực hành riêng:

```bash
redis-cli PING
redis-cli SET user:status:lab-42 ACTIVE
redis-cli GET user:status:lab-42
redis-cli TTL user:status:lab-42
redis-cli TYPE user:status:lab-42
```

Với template JSON hoặc serializer tùy chỉnh, `GET` có thể trả JSON hoặc bytes, không nhất thiết là giá trị String dễ đọc. Cần kết nối đúng Redis instance/database, TLS và auth khi quan sát CLI.

## 21. Bài thực hành có hướng dẫn

### Bài 1 — Kết nối Redis reactive

Dùng Spring Boot starter Redis và WebFlux. Cấu hình endpoint local, inject `ReactiveRedisConnectionFactory`. Khai báo `ReactiveRedisTemplate<String,String>` bằng `RedisSerializationContext.string()`.

Viết ba API trả publisher:

```java
Mono<Boolean> put(String id, String value);
Mono<String> get(String id);
Mono<Long> delete(String id);
```

Kiểm tra `put` có TTL, `get` của key không tồn tại trả empty và `delete` trả số key bị xóa.

### Bài 2 — Cấu hình JSON serializer

Tạo `ProductSnapshot` có `sourceVersion`. Khai báo template với key serializer string và value serializer JSON. Dùng namespace có schema version, ví dụ `cache:product:v1:42`.

Thử ghi, đọc lại, đổi type hoặc bổ sung field rồi xác định phương án migration. So sánh dữ liệu được Redis CLI đọc ra với dữ liệu Java deserialize được.

### Bài 3 — Cache-aside với source reactive

Tạo một nguồn giả `ReactiveProductSource` có bộ đếm số lần gọi. Thử cache miss rồi cache hit và đo số lần đọc nguồn. Gửi nhiều request cùng miss để quan sát cache stampede.

### Bài 4 — Mất kết nối Redis

Trong môi trường test, cho Redis không khả dụng. Thử pipeline có `timeout(...)` và `onErrorResume(...)`. Ghi nhận error signal, fallback count và thời gian phản hồi. Không dùng test cố ý ngắt kết nối trên production.

### Bài 5 — Kiểm tra đường WebFlux không blocking

Viết endpoint GET trả trực tiếp `Mono`. So sánh với phiên bản gọi `block()` và xác định vì sao cách thứ hai không phù hợp với event-loop. Nếu nguồn dữ liệu còn blocking, đặt nó tại boundary được quản lý và theo dõi scheduler saturation.

### Bài 6 — Retry có side effect

Tạo phép `INCR` từ Redis reactive API, mô phỏng client mất phản hồi sau khi command được gửi. Phân tích vì sao retry có thể làm số đếm tăng hai lần. Thiết kế operation ID hoặc script idempotent phù hợp rồi thử lại trong môi trường thực hành.

## 22. Câu hỏi tự đánh giá

**1. `ReactiveRedisConnectionFactory` khác `ReactiveRedisTemplate` như thế nào?**  
Factory cung cấp kết nối reactive; template sử dụng kết nối đó cùng serializer để thao tác Redis ở mức cao.

**2. `LettuceConnectionFactory` có thể cung cấp cả imperative và reactive connection không?**  
Có trong cấu hình được hỗ trợ. Nhưng hai đường API không tự chia sẻ transaction hoặc execution context.

**3. Vì sao gọi `set(...)` rồi bỏ `Mono` có thể không ghi Redis?**  
Publisher thường chỉ thực hiện I/O khi có subscription. Service nên trả `Mono`/`Flux` hoặc hợp thành thành reactive chain được subscribe bởi framework.

**4. Khi nào dùng `ReactiveStringRedisTemplate`?**  
Khi key và value của ứng dụng đều theo hợp đồng chuỗi. Typed `ReactiveRedisTemplate` phù hợp khi cần serializer hoặc cấu hình riêng.

**5. Vì sao RedisSerializationContext quan trọng?**  
Nó quyết định byte của key, value và hash. Hai writer khác serializer có thể nhìn các tên key khác nhau dù String Java giống nhau.

**6. `Mono.empty()` có nghĩa Redis không kết nối được không?**  
Không. Empty nghĩa là publisher hoàn tất mà không có giá trị, chẳng hạn key không tồn tại. Lỗi kết nối thường là `onError`.

**7. Tại sao không dùng `block()` trong WebFlux handler?**  
Nó chặn thread xử lý reactive, có thể gây giảm throughput và lỗi trên event-loop.

**8. Nếu `timeout()` phát lỗi, có chắc command Redis chưa chạy?**  
Không. Command có thể đã được thực thi trước khi client mất phản hồi; retry side effect cần idempotency.

**9. ReactiveRedisTemplate có làm SQL và Redis commit nguyên tử không?**  
Không. Reactive API không thay thế một distributed transaction coordinator.

**10. Reactive giúp tự hết cache stampede và stale data không?**  
Không. Cần chính sách cache, giới hạn concurrency, version-aware write và invalidation/repair phù hợp.

## 23. Ghi nhớ khi triển khai

- `ReactiveRedisConnectionFactory` là abstraction kết nối reactive; `LettuceConnectionFactory` thường được sử dụng để cung cấp implementation.
- `ReactiveRedisTemplate<K,V>` cần factory và `RedisSerializationContext<K,V>` nhất quán với wire format của Redis.
- Dữ liệu chuỗi có thể dùng `ReactiveStringRedisTemplate` hoặc `RedisSerializationContext.string()`.
- DTO cần serializer/schema version rõ ràng; tránh dựa vào default không hiểu được.
- Service WebFlux nên **trả `Mono`/`Flux`**, không gọi `block()` trong event-loop hoặc `subscribe()` tùy tiện.
- Phân biệt cache miss với Redis error; timeout/retry cần xét idempotency và có metric.
- Dùng connection factory singleton có lifecycle, cấu hình Redis topology, TLS, ACL và timeouts đúng môi trường.
- Reactive giúp hiệu quả I/O nhưng **không tạo transaction SQL + Redis**, không xóa race condition hoặc bảo đảm cache luôn mới.
- Kiểm thử publishers bằng `StepVerifier` và Redis test instance, bao gồm schema, timeout, retry và failover.

**Cấu hình reactive Redis thành công** không chỉ là ứng dụng inject được bean: nó còn cần serializer đúng, không chặn luồng WebFlux, xử lý lỗi theo hợp đồng nghiệp vụ và có đường vận hành/khôi phục rõ ràng khi Redis hoặc nguồn dữ liệu gặp sự cố.

## Tài liệu tham khảo

- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): mô hình truy cập Redis reactive.
- [Spring Data Redis — Template API](https://docs.spring.io/spring-data/redis/reference/redis/template.html): cấu hình template và các operation.
- [Spring Data Redis — Serialization](https://docs.spring.io/spring-data/redis/reference/redis/serializer.html): serializer, RedisSerializationContext và wire format.
- [Spring Data Redis — ReactiveRedisTemplate API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ReactiveRedisTemplate.html): các operation và kiểu publisher.
- [Spring Data Redis — ReactiveRedisConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/ReactiveRedisConnectionFactory.html): hợp đồng kết nối reactive.
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html): connection factory Lettuce.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): endpoint non-blocking và reactive HTTP.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, subscription, errors, scheduler và backpressure.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): TTL của Redis key.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): duyệt keyspace bằng cursor.
