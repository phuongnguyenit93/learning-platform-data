# @DataRedisTest với cache, TTL và cấu trúc dữ liệu được sử dụng trong Spring Boot

## 1. Vấn đề: “Redis test xanh” phải thật sự kiểm tra Redis

Spring Boot thường dùng Redis cho cache, session, token có hạn sử dụng, rate limit, ranking, giỏ hàng hoặc tập kết quả tạm thời. Một lỗi Redis không nhất thiết là lỗi của code Java: cùng một key có thể được ghi dưới **kiểu dữ liệu sai**, TTL bị quên, cấu hình serializer không tương thích, cache bị vô hiệu hóa trong test hoặc dữ liệu của test trước còn sót lại.

`@DataRedisTest` là **test slice** của Spring Boot dành cho những thành phần **Spring Data Redis**. Nó tập trung cấu hình kết nối, Redis templates và các Redis repositories/entities được phép quét, thay vì nạp toàn bộ controller, HTTP server và service nghiệp vụ. Nhưng cần hiểu ngay ba giới hạn:

1. **`@DataRedisTest` không tự khởi động một Redis server.** Nó cấu hình những thành phần client có điều kiện; để chạy lệnh Redis thật, cần một Redis instance test, chẳng hạn từ **Testcontainers** hoặc một server dành riêng cho CI.
2. **`@DataRedisTest` không mặc nhiên bật cache thật của `@Cacheable`.** Trong Spring Boot 3.5, test slice có `@AutoConfigureCache`, mặc định định hướng đến `NoOpCacheManager`. Nếu muốn xác nhận Redis cache thực, phải bật `@EnableCaching` và cấu hình/kiểm tra `RedisCacheManager` thực trong test phù hợp.
3. **Redis không tự có rollback test như `@DataJpaTest`.** Một khóa đã `SET`/một thành viên đã `SADD` vào Redis server ngoài tiến trình vẫn còn cho đến khi bị xóa hoặc hết TTL, trừ khi ta chủ động cleanup. `@Transactional` của Spring TestContext không nên được xem là cơ chế tự rollback mọi lệnh Redis.

Bài học xây một ví dụ Java 17+ / Spring Boot 3.5 với **Redis thật qua Testcontainers**: kiểm tra `StringRedisTemplate`, TTL, Redis Hash/List/Set/Sorted Set, xử lý WRONGTYPE, và một test riêng chứng minh `@Cacheable` thực sự dùng Redis với TTL. Đồng thời chỉ rõ Spring Data Redis repository `@RedisHash` khác cache và cách nâng phiên bản sang Boot 4.

## 2. Những loại thành phần nào nằm trong @DataRedisTest?

Trên **Spring Boot 3.5.x**, import:

```java
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
```

Một test đơn giản:

```java
@DataRedisTest
class RedisRepositoryTest {
    // @Autowired RedisRepository hoặc StringRedisTemplate;
}
```

`@DataRedisTest` sử dụng Spring TestContext và slice-specific type filters, thường có:
- `RedisAutoConfiguration`: `RedisConnectionFactory`, `RedisTemplate` và `StringRedisTemplate` khi classpath/configuration cho phép.
- `RedisReactiveAutoConfiguration`: thành phần reactive phù hợp khi dependency/reactive connection có mặt.
- `RedisRepositoriesAutoConfiguration`: Spring Data Redis repositories và entity `@RedisHash` được tìm thấy.
- Một số phần SSL, cache auto-config hoặc Testcontainers service connection theo điều kiện/phiên bản.

Bộ lọc component scan mặc định chủ yếu chú ý **Redis repositories và entities `@RedisHash`**; `@Service`, ordinary `@Component` hoặc `@ConfigurationProperties` thông thường **không được quét như trong full application context**. Một adapter/DAO Redis thủ công được đánh dấu `@Repository` nhưng không phải Spring Data repository interface cần được `@Import` nếu test muốn giữ bean đó.

| Bean/thành phần | Trong Redis slice? | Ý nghĩa của test |
|---|---|---|
| `RedisConnectionFactory` | Thường được auto-configure khi có driver | Kết nối tới server Redis đã chỉ định |
| `RedisTemplate<Object,Object>` | Có thể được Boot tạo | Kiểm tra serialization và Redis operations phù hợp template |
| `StringRedisTemplate` | Thường có khi Redis auto-config hoạt động | Key/value dạng String với string serializer |
| `ReactiveRedisTemplate` / `ReactiveStringRedisTemplate` | Có điều kiện theo reactive dependencies | Reactive Redis commands, cần subscribe khi test |
| `CrudRepository` cho entity `@RedisHash` | Được Redis repository auto-config quét | Mapping aggregate, ID, repository TTL/index |
| DAO tự viết `@Repository` | **Không tự được scan mặc định** | `@Import(Dao.class)` để giữ implementation thật |
| Business `@Service` | Không tự nạp | Import/fake cụ thể hoặc viết integration test |
| `CacheManager` thật cho `@Cacheable` | **Không nên mặc nhiên giả định** | Khai báo tường minh `RedisCacheManager` và `@EnableCaching` |
| Redis server | **Không được @DataRedisTest sinh ra** | Testcontainers/server test riêng |
| SQL `DataSource` / JPA `EntityManager` | Không thuộc phạm vi | Các test SQL/JPA riêng |
| HTTP controller / embedded server | Không thuộc phạm vi | MVC/WebFlux/HTTP integration test riêng |

Một application class có `@ComponentScan` tùy biến hoặc test có nhiều `@Import` có thể mở rộng phạm vi bất ngờ. Nếu `ApplicationContext` fail vì thiếu một bean service thì đừng vội chuyển sang `@SpringBootTest`: xem service ấy có thực sự thuộc mục tiêu kiểm chứng Redis slice không.

**Phân biệt “có bean” và “lệnh Redis chạy thành công”:** inject `StringRedisTemplate` mới chứng minh Spring tạo client; cần gọi `set`, `get`, `expire`, `type`, `opsForHash`... để phát hiện sai host/port/auth/TLS hoặc sai data structure.

## 3. Redis lưu những kiểu dữ liệu nào và test gì?

Redis không chỉ là map `String -> String`. Mỗi key có **Redis data type** và chỉ một nhóm lệnh nhất định áp dụng được cho kiểu ấy.

| Redis type | Lệnh thường gặp | Spring Data API | Kiểm tra quan trọng |
|---|---|---|---|
| String | `SET`, `GET`, `INCR`, `SET ... EX` | `opsForValue()` | Value/serialization, TTL, atomic counter |
| Hash | `HSET`, `HGET`, `HGETALL` | `opsForHash()` | Fields và values, partial update, key-level TTL |
| List | `LPUSH`, `RPUSH`, `LRANGE` | `opsForList()` | Thứ tự và phần tử trùng, bên push/pop |
| Set | `SADD`, `SMEMBERS` | `opsForSet()` | Không trùng, **không cam kết thứ tự** |
| Sorted Set / ZSet | `ZADD`, `ZRANGE`, `ZREVRANGE` | `opsForZSet()` | Score, ranking, thứ tự/tie-breaking |
| Stream | `XADD`, `XREADGROUP` | `opsForStream()` | Event ID, consumer group, ack/retry; cần test riêng |
| HyperLogLog | `PFADD`, `PFCOUNT` | `opsForHyperLogLog()` | Approximate cardinality, **không exact** |
| Geo | `GEOADD`, `GEORADIUS` và biến thể | `opsForGeo()` | Coordinates, radius/unit, thứ tự/khoảng cách |

`StringRedisTemplate` dùng `StringRedisSerializer` cho keys/values thích hợp, giúp test dễ đọc bằng Redis CLI. `RedisTemplate` tổng quát có thể dùng serializers khác, và cache `RedisCacheManager` có key/value serializers riêng. **Cùng key nhìn bằng mắt giống nhau nhưng bytes được lưu có thể khác** nếu serializer khác.

### 3.1. Sai Redis type thường tạo WRONGTYPE

Ví dụ, một key đã được `SET` thành Redis String; nếu sau đó dùng `HSET` trên cùng key thì Redis có thể trả lỗi **WRONGTYPE**. Khi Spring Data Redis dịch lỗi, bạn sẽ thấy một `DataAccessException` phù hợp thay vì một Hash rỗng.

```text
SET demo:stock "5"         -> key có type STRING
HSET demo:stock name "A"   -> WRONGTYPE
TYPE demo:stock            -> string
```

Cách sửa là đặt convention theo namespace (`stock:...`, `cart:...`, `ranking:...`) và đảm bảo code dùng **đúng family thao tác**. Không tự sửa bằng cách xóa key production đang có dữ liệu để ép về kiểu khác.

### 3.2. Đừng nhầm Hash với JSON string

Một key chứa JSON `"{\"name\":\"A\"}"` thông qua `SET` vẫn là **Redis String**, không phải Redis Hash. Muốn dùng `HGET key name`, phải viết bằng Hash operations hoặc chuyển cấu trúc phù hợp. Round-trip của JSON serializer không chứng minh Hash field mapping.

### 3.3. Set và Sorted Set khác List

- **List** giữ thứ tự và cho phép duplicate; phù hợp danh sách sự kiện ngắn khi được quản lý giới hạn độ dài.
- **Set** đảm bảo uniqueness nhưng iteration order không ổn định; không so sánh trực tiếp với `List.of("a","b")`.
- **Sorted Set** kết hợp member duy nhất và score, dùng cho leaderboards. Test phải xác nhận score và hướng sắp xếp; khi score bằng nhau, Redis áp quy tắc tie-breaking cho member nên test cần phản ánh contract hoặc tránh ties không cần thiết.

## 4. TTL là gì và những trường hợp khiến test sai?

TTL (time to live) quy định **thời gian còn sống của một Redis key**. Với lệnh SET có expiration, Redis sẽ tự loại key khi hết hạn (cơ chế expired-key cleanup có lazy/active behavior). Spring Data Redis cung cấp:

```java
redis.opsForValue().set(
        "tokens:abc",
        "value",
        Duration.ofSeconds(60));

Long ttl = redis.getExpire(
        "tokens:abc",
        TimeUnit.SECONDS);
```

Đây là **đoạn minh họa** trong class có `StringRedisTemplate redis`; cần imports `Duration`, `TimeUnit`. Kết quả `ttl` đo **thời gian còn lại tại thời điểm đọc**, không phải lúc nào cũng đúng 60.

Giá trị Redis TTL thường được hiểu như sau:

| Giá trị TTL | Ý nghĩa |
|---|---|
| Số dương | Key tồn tại và có expiration, còn số giây/ms tương ứng |
| `-1` | Key tồn tại **nhưng không có expiration** |
| `-2` | Key **không tồn tại** |
| `0` | Có thể còn dưới một đơn vị TTL được yêu cầu, ví dụ 0 giây do làm tròn; không suy ra vĩnh viễn |
| `null` từ API | Có thể do operation/driver/pipeline context; cần xem hợp đồng và cấu hình |

Để assert TTL, thường dùng một **khoảng** (ví dụ `0 < ttl <= 60`) thay vì `ttl == 60`. Khi TTL rất ngắn, dùng milliseconds hoặc bounded polling, không dùng `Thread.sleep(2000)` rồi hy vọng CI đủ nhanh.

### 4.1. TTL áp lên key, không mặc nhiên áp từng field

Trong cách dùng Redis Hash phổ biến, `expire(hashKey, duration)` đặt TTL cho **toàn bộ key Hash**. Một field `HSET` không tự mang một TTL riêng chỉ vì Hash có nhiều field. Redis phiên bản mới có những lệnh expiration cho hash field riêng, nhưng **không được mặc định** rằng mọi Redis server/phiên bản Spring Data Redis đều có API đó, hoặc rằng `opsForHash().put` tự áp TTL cho field.

### 4.2. Đọc key có gia hạn TTL không?

Với TTL thông thường, **`GET` không tự gia hạn hạn sống**. Nếu nghiệp vụ là “15 phút kể từ lần truy cập cuối”, đó gần với **TTI (time to idle)** và cần một cơ chế cụ thể, chẳng hạn cache implementation hỗ trợ read-and-reset expiration qua `GETEX` trên Redis 6.2+. TTI không tự có chỉ vì đã cấu hình TTL.

Một bài test chỉ kiểm tra key tồn tại ngay sau ghi **không thể** chứng minh expiration. Test nên kiểm tra TTL được đặt đúng **và** một tình huống đã hết hạn khi đó là requirement.

### 4.3. expire, persist, overwrite và update

Một key với expiration có thể được:
- Ghi đè bằng các thao tác thay thế giá trị làm **mất TTL** tùy lệnh; `SET key value` thông thường xóa TTL cũ trừ khi dùng tùy chọn giữ TTL.
- Gia hạn bằng `EXPIRE` hoặc ghi mới với TTL.
- Chuyển thành persistent bằng `PERSIST` nếu operation cho phép.
- Bị loại trước TTL do explicit `DEL`, eviction policy hoặc server reset; TTL không phải cam kết giữ dữ liệu đến đúng giây cuối.

**Test behavior sau update**, không chỉ sau lần ghi đầu, nếu nghiệp vụ phụ thuộc việc update phải gia hạn/giữ nguyên thời hạn.

## 5. Dự án ví dụ: Java 17+, Spring Boot 3.5 và Redis thật

Ví dụ dưới đây kiểm tra Redis với **Testcontainers**, nên cần Docker hoặc container runtime tương thích. Không giả lập Redis bằng Mockito khi mục tiêu là Redis data types và TTL thật.

Cấu trúc:

```text
build.gradle
src/main/java/com/example/redisslice/
    RedisSliceApplication.java
    RedisStructuresStore.java
    CatalogueService.java
    CachedLookupService.java

src/test/java/com/example/redisslice/
    RedisStructuresStoreTest.java
    RedisCacheSliceTest.java
```

### 5.1. build.gradle (Gradle Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cấu hình trên dùng phiên bản patch cụ thể **Boot 3.5.8** cho tính dễ tái tạo trên một repository Maven/Gradle có dependencies tương ứng. Khi dùng dự án thật, đồng bộ các libraries theo Spring Boot BOM và cập nhật phiên bản patch đã được nhóm kiểm thử. Ví dụ này cần **Redis 7.4 container** có thể pull từ registry khi chạy test và một container runtime hoạt động.

`spring-boot-starter-data-redis` đưa Spring Data Redis và driver Lettuce lên classpath. `spring-boot-starter-cache` hỗ trợ cache abstraction/AOP khi được bật. `spring-boot-starter-test` mang JUnit Jupiter/Mockito/Spring Test. `awaitility` giúp test expiration có polling timeout có giới hạn. Testcontainers chạy **Redis thật**, không fake server.

Không cần tự cài `redis-server` tại cổng 6379 trên host; Docker map cổng container sang một cổng host động, và `@DynamicPropertySource` chuyển thông tin đó cho Spring Data Redis.

### 5.2. Application class

Tệp `src/main/java/com/example/redisslice/RedisSliceApplication.java`:

```java
package com.example.redisslice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedisSliceApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisSliceApplication.class, args);
    }
}
```

Lớp application dùng package cha của Redis DAO và service, nhưng `@DataRedisTest` **không kích hoạt full component scan** theo cách `@SpringBootTest` thường làm. Trong ví dụ, các component không thuộc Redis repository scan được import riêng trong test.

### 5.3. Adapter thao tác nhiều Redis data structures

Tệp `src/main/java/com/example/redisslice/RedisStructuresStore.java`:

```java
package com.example.redisslice;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class RedisStructuresStore {

    private final StringRedisTemplate redis;

    public RedisStructuresStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStock(String key, int quantity, Duration ttl) {
        redis.opsForValue().set(
                key, Integer.toString(quantity), ttl);
    }

    public Optional<Integer> readStock(String key) {
        return Optional.ofNullable(
                redis.opsForValue().get(key))
                .map(Integer::parseInt);
    }

    public void putMetadata(
            String key, Map<String, String> fields) {
        redis.opsForHash().putAll(key, fields);
    }

    public String readMetadata(String key, String field) {
        Object value = redis.opsForHash().get(key, field);
        return value == null ? null : value.toString();
    }

    public void appendEvent(String key, String event) {
        redis.opsForList().rightPush(key, event);
    }

    public List<String> events(String key) {
        List<String> values =
                redis.opsForList().range(key, 0, -1);
        return values == null ? List.of() : values;
    }

    public void addTag(String key, String tag) {
        redis.opsForSet().add(key, tag);
    }

    public Set<String> tags(String key) {
        Set<String> values = redis.opsForSet().members(key);
        return values == null ? Set.of() : values;
    }

    public void addRanking(
            String key, String member, double score) {
        redis.opsForZSet().add(key, member, score);
    }

    public List<String> rankedDescending(String key) {
        Set<String> values =
                redis.opsForZSet().reverseRange(key, 0, -1);
        return values == null
                ? List.of()
                : new ArrayList<>(values);
    }
}
```

Đây là **adapter thật**, gọi Redis server qua `StringRedisTemplate`. Những điểm cần quan sát:

- `putStock` tạo Redis **String** với TTL, không tạo Hash.
- `putMetadata` tạo Redis **Hash** gồm field/value, không phải một JSON string.
- `appendEvent` dùng `RPUSH` nên **thứ tự ghi** được giữ trong List; duplicate được phép.
- `addTag` dùng Redis **Set**, member trùng không nhân đôi.
- `addRanking` dùng **Sorted Set** với score; `reverseRange` lấy thứ tự score từ cao xuống thấp.
- `StringRedisTemplate` thuận tiện khi dữ liệu chỉ là String; với object phức tạp cần cấu hình `RedisTemplate<K,V>` và serializer rõ ràng.
- Không có `@Transactional` hoặc SQL database trong adapter; mỗi operation ở đây gửi Redis command tương ứng.

**Các lệnh không nhất thiết tạo một transaction nhiều bước.** Chẳng hạn `HSET` rồi `EXPIRE` là hai command riêng; nếu yêu cầu thao tác atomically, cần cân nhắc Redis `MULTI/EXEC`, Lua script hoặc một command phù hợp, và test riêng behavior khi concurrent access/network failure.

### 5.4. Service nghiệp vụ để chứng minh phạm vi slice

Tệp `src/main/java/com/example/redisslice/CatalogueService.java`:

```java
package com.example.redisslice;

import java.util.Optional;

import org.springframework.stereotype.Service;

@Service
public class CatalogueService {

    private final RedisStructuresStore store;

    public CatalogueService(RedisStructuresStore store) {
        this.store = store;
    }

    public Optional<Integer> stock(String key) {
        return store.readStock(key);
    }
}
```

`@DataRedisTest` thông thường không quét `CatalogueService`. Chúng ta kiểm tra điều đó tường minh trong test. Nếu cần test logic service thật, có thể `@Import` service cùng các dependency liên quan hoặc viết integration test phù hợp, nhưng không nên kéo controller/scheduler vào Redis slice một cách tình cờ.

## 6. Bộ test thật cho String, Hash, List, Set, ZSet và TTL

Tệp `src/test/java/com/example/redisslice/RedisStructuresStoreTest.java`:

```java
package com.example.redisslice;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataRedisTest
@Import(RedisStructuresStore.class)
class RedisStructuresStoreTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    RedisStructuresStore store;

    @Autowired
    ApplicationContext context;

    private final Set<String> keysToDelete = new HashSet<>();

    private String key(String suffix) {
        String key = "learn:redis:" + UUID.randomUUID()
                + ":" + suffix;
        keysToDelete.add(key);
        return key;
    }

    @AfterEach
    void cleanOnlyThisTestsKeys() {
        if (!keysToDelete.isEmpty()) {
            redis.delete(keysToDelete);
        }
    }

    @Test
    void sliceProvidesTemplateAndImportedStoreButNotService() {
        assertNotNull(redis);
        assertNotNull(store);
        assertTrue(context.getBeansOfType(
                CatalogueService.class).isEmpty());
    }

    @Test
    void writesAndReadsStringWithExplicitType() {
        String key = key("stock");

        store.putStock(key, 17, Duration.ofSeconds(90));

        assertEquals(17, store.readStock(key).orElseThrow());
        assertEquals(DataType.STRING, redis.type(key));
    }

    @Test
    void distinguishesExpiringAndPersistentKeys() {
        String temporary = key("temporary");
        String permanent = key("permanent");

        store.putStock(
                temporary, 5, Duration.ofSeconds(60));
        redis.opsForValue().set(permanent, "keep");

        Long ttl = redis.getExpire(
                temporary, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 60);

        assertEquals(
                -1L,
                redis.getExpire(
                        permanent, TimeUnit.SECONDS));
    }

    @Test
    void observesExpirationWithBoundedPolling() {
        String key = key("short-lived");
        redis.opsForValue().set(
                key, "temporary", Duration.ofMillis(300));

        await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(50))
                .untilAsserted(
                        () -> assertFalse(
                                Boolean.TRUE.equals(
                                        redis.hasKey(key))));
    }

    @Test
    void hashHasSeveralFieldsUnderOneRedisKey() {
        String key = key("profile");
        store.putMetadata(
                key,
                Map.of("owner", "linh", "tier", "gold"));

        assertEquals(DataType.HASH, redis.type(key));
        assertEquals("linh",
                store.readMetadata(key, "owner"));
        assertEquals("gold",
                store.readMetadata(key, "tier"));

        assertTrue(
                Boolean.TRUE.equals(
                        redis.expire(
                                key, Duration.ofSeconds(60))));

        Long ttl = redis.getExpire(
                key, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 60);
    }

    @Test
    void listPreservesAppendOrderAndDuplicates() {
        String key = key("events");

        store.appendEvent(key, "opened");
        store.appendEvent(key, "edited");
        store.appendEvent(key, "opened");

        assertEquals(DataType.LIST, redis.type(key));
        assertEquals(
                List.of("opened", "edited", "opened"),
                store.events(key));
    }

    @Test
    void setRemovesDuplicatesWithoutOrderingGuarantee() {
        String key = key("tags");

        store.addTag(key, "java");
        store.addTag(key, "redis");
        store.addTag(key, "java");

        assertEquals(DataType.SET, redis.type(key));
        assertEquals(
                Set.of("java", "redis"),
                store.tags(key));
    }

    @Test
    void sortedSetOrdersByScoreDescending() {
        String key = key("leaderboard");

        store.addRanking(key, "alice", 10.0);
        store.addRanking(key, "bob", 25.0);
        store.addRanking(key, "cara", 5.0);

        assertEquals(DataType.ZSET, redis.type(key));
        assertEquals(
                List.of("bob", "alice", "cara"),
                store.rankedDescending(key));

        assertEquals(
                25.0,
                redis.opsForZSet().score(key, "bob"));
    }

    @Test
    void wrongTypeFailsInsteadOfReturningAnEmptyHash() {
        String key = key("wrong-type");
        redis.opsForValue().set(key, "plain-text");

        assertThrows(
                DataAccessException.class,
                () -> redis.opsForHash().put(
                        key, "owner", "someone"));
    }

    @Test
    void deletingOneOwnedKeyDoesNotTouchAnotherKey() {
        String first = key("first");
        String second = key("second");
        redis.opsForValue().set(first, "one");
        redis.opsForValue().set(second, "two");

        assertTrue(
                Boolean.TRUE.equals(redis.delete(first)));

        assertFalse(
                Boolean.TRUE.equals(redis.hasKey(first)));
        assertEquals("two",
                redis.opsForValue().get(second));
    }
}
```

### 6.1. Tại sao ví dụ phải dùng @Import?

`RedisStructuresStore` là một bean `@Repository` **tự viết**, không phải interface thuộc Spring Data Redis repository scan. Trong Redis slice, nó có thể không tự xuất hiện. `@Import(RedisStructuresStore.class)` đưa đúng implementation cần test vào context mà không mở toàn bộ component scan.

Test `sliceProvidesTemplateAndImportedStoreButNotService` chứng minh `StringRedisTemplate` và adapter có mặt, trong khi `CatalogueService` thường không có. Nếu test khác chủ động `@Import(CatalogueService.class)`, kết luận về service đó phải thay đổi tương ứng; đây là hành vi có chủ đích.

### 6.2. Tại sao test TTL không sleep cố định?

TTL là thời gian **còn lại**, cộng tác với scheduler/server clock/CI load. Test `observesExpirationWithBoundedPolling` dùng Awaitility kiểm tra **điều kiện** key không còn tồn tại trong tối đa 5 giây, với polling interval 50 ms. Nó kết thúc sớm khi key biến mất và báo lỗi khi hết thời gian, thay vì luôn ngủ một số giây cố định.

Kiểm tra TTL nên tách hai khẳng định:
1. Sau khi viết, Redis báo key **có TTL** nằm trong khoảng hợp lý.
2. Sau thời hạn ngắn, key thực sự không còn quan sát được.

Không dùng `getExpire() == 60` làm expectation chính xác: một chút thời gian đã trôi qua giữa write và read; còn TTL có độ phân giải giây nên có thể làm tròn.

### 6.3. Vì sao dùng keys riêng thay vì FLUSHALL?

Mỗi test tạo prefix riêng bằng `UUID`, ghi lại những keys do nó tạo rồi xóa trong `@AfterEach`. Cách này:
- Tránh hai test cùng key.
- Không xóa key của một suite khác trong Redis dùng chung.
- Không yêu cầu lệnh quản trị `FLUSHALL` hoặc `FLUSHDB`.
- Không nhầm `@DataRedisTest` với rollback tự động.

Nếu một test tạo nhiều secondary index keys, phantom copies hoặc cache prefix keys, cleanup phải bao phủ các keys đó; chỉ xóa main key có thể chưa đủ. Với Redis repository, ưu tiên dùng API repository và thiết kế namespace/container isolation phù hợp.

### 6.4. Bằng chứng của từng ca

| Ca test | Điều thực sự kiểm tra | Điều chưa được chứng minh |
|---|---|---|
| Slice context | Redis template, DAO import và loại service thường | Full application context giống hệt production |
| String và stock | SET/GET, String serializer, `TYPE=string` | Database SQL có dữ liệu tương ứng |
| TTL vs persistent | `getExpire` phân biệt positive TTL và `-1` | Đã kiểm tra TTI hoặc mọi trường hợp overwrite |
| Expiration polling | Redis key hết hạn trong cửa sổ hợp lý | Expire event đã được phát tới mọi subscriber |
| Hash | Fields/values, `TYPE=hash`, key-level TTL | Hash field-level TTL |
| List | Order và duplicate | Queue concurrency/consumer acknowledgement |
| Set | Uniqueness, không phụ thuộc thứ tự iteration | Set trả kết quả theo một thứ tự cố định |
| Sorted Set | Score và ranking descending | Tie-breaking/large leaderboard performance |
| WrongType | Redis phản hồi lỗi cho lệnh không đúng type | Mọi lỗi Redis đều là WRONGTYPE |
| Cleanup từng key | Xóa riêng key và không ảnh hưởng key khác | Không còn bất kỳ key phụ nào nếu repository khác tạo |

**Các test gọi Redis thật qua Testcontainers.** Tuy nhiên, một Redis instance Redis 7.4 cục bộ chưa chứng minh behavior của Redis Cluster, Sentinel, TLS, eviction dưới áp lực RAM hoặc managed Redis production. Những rủi ro ấy cần test cấu hình/triển khai thích hợp.

## 7. @Cacheable trong @DataRedisTest: cẩn thận NoOpCacheManager

Phần data structure test ở trên kiểm tra trực tiếp Redis operations. Nó **không tự chứng minh** Spring cache abstraction hoạt động, vì `@Cacheable` sử dụng interception/proxy và `CacheManager`, không phải chỉ `StringRedisTemplate`.

Trong Spring Boot 3.5, `@DataRedisTest` sử dụng `@AutoConfigureCache` với mặc định hướng về **no-op** để test slice không phụ thuộc cache business logic. Vì vậy:
- Một bean có `@Cacheable` có thể không được scan.
- `@EnableCaching` có thể chưa bật trong context.
- Nếu cache manager là `NoOpCacheManager`, test vẫn chạy nhưng cache **không lưu vào Redis**.
- Chỉ khẳng định cache Redis khi kiểm tra bean `RedisCacheManager` **và** key TTL/response hit/miss thực tế.

Cách rõ ràng: viết một test riêng import đúng service và cấu hình `RedisCacheManager` thật. Ví dụ sau chỉ cache **String values**, nên khai báo `StringRedisSerializer` thay cho mặc định JDK serialization của cache manager. Đối với DTO, cần chọn serializer phù hợp và kiểm thử schema/compatibility riêng.

### 7.1. Service có @Cacheable

Tệp `src/main/java/com/example/redisslice/CachedLookupService.java`:

```java
package com.example.redisslice;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedLookupService {

    private final AtomicInteger calls = new AtomicInteger();

    @Cacheable(cacheNames = "lookups", key = "#p0")
    public String displayName(String sku) {
        return "Item-" + sku + "-" + calls.incrementAndGet();
    }

    public int callCount() {
        return calls.get();
    }
}
```

Sử dụng `key="#p0"` thay vì `key="#sku"` để ví dụ không phụ thuộc vào cách compiler lưu parameter names. Đây là **public method được gọi từ một bean khác (test qua Spring proxy)**. Nếu chính service gọi `this.displayName(...)`, lời gọi nội bộ có thể bỏ qua caching advice trong mô hình proxy mặc định.

### 7.2. Test RedisCacheManager với TTL và hit/miss thật

Tệp `src/test/java/com/example/redisslice/RedisCacheSliceTest.java`:

```java
package com.example.redisslice;

import java.time.Duration;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataRedisTest
@Import({
        CachedLookupService.class,
        RedisCacheSliceTest.TestCacheConfiguration.class
})
class RedisCacheSliceTest {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @TestConfiguration(proxyBeanMethods = false)
    @EnableCaching
    static class TestCacheConfiguration {

        @Bean
        RedisCacheManager cacheManager(
                RedisConnectionFactory factory) {

            RedisCacheConfiguration settings =
                    RedisCacheConfiguration.defaultCacheConfig()
                            .entryTtl(Duration.ofSeconds(90))
                            .disableCachingNullValues()
                            .serializeValuesWith(
                                    RedisSerializationContext
                                            .SerializationPair
                                            .fromSerializer(
                                                    new StringRedisSerializer()));

            return RedisCacheManager.builder(factory)
                    .cacheDefaults(settings)
                    .build();
        }
    }

    @Autowired
    CachedLookupService service;

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    CacheManager cacheManager;

    private final Set<String> cacheKeys = new HashSet<>();

    private String sku() {
        String value = "sku-" + UUID.randomUUID();
        cacheKeys.add("lookups::" + value);
        return value;
    }

    @AfterEach
    void removeOnlyOwnedCacheEntries() {
        if (!cacheKeys.isEmpty()) {
            redis.delete(cacheKeys);
        }
    }

    @Test
    void repeatedLookupUsesRedisAndKeepsPositiveTtl() {
        assertInstanceOf(RedisCacheManager.class, cacheManager);
        String productSku = sku();
        int before = service.callCount();

        String first = service.displayName(productSku);
        String second = service.displayName(productSku);

        assertEquals(first, second);
        assertEquals(before + 1, service.callCount());

        String storedKey = "lookups::" + productSku;
        assertNotNull(redis.opsForValue().get(storedKey));

        Long remaining = redis.getExpire(
                storedKey, TimeUnit.SECONDS);
        assertNotNull(remaining);
        assertTrue(remaining > 0 && remaining <= 90);
    }

    @Test
    void differentKeysComputeDifferentEntries() {
        int before = service.callCount();
        String firstSku = sku();
        String secondSku = sku();

        String first = service.displayName(firstSku);
        String second = service.displayName(secondSku);

        assertTrue(!first.equals(second));
        assertEquals(before + 2, service.callCount());
    }
}
```

### 7.3. Tại sao cấu hình cache phải tường minh?

- `@TestConfiguration` giới hạn cấu hình này cho test, không khiến production bắt buộc dùng Redis cache.
- `@EnableCaching` bật Spring caching AOP infrastructure. Annotation này không tự bảo đảm một `CacheManager` Redis sẽ xuất hiện; ta tạo bean `RedisCacheManager` thực.
- `@Import(CachedLookupService.class)` đưa **service thật** vào slice để kiểm tra interception. Nếu service bị Mockito mock, `@Cacheable` trên implementation có thể không được chạy như mong muốn.
- `entryTtl(Duration.ofSeconds(90))` cấu hình TTL khi **cache ghi một entry**, không phải lời hứa GET luôn reset TTL.
- `StringRedisSerializer` được dùng vì ví dụ cache `String`. Nếu service cache POJO, serializer phải tương thích với payload và contract.
- Key prefix mặc định của `RedisCacheManager` là `cacheName::`; trong ví dụ là `lookups::sku-...`. Đừng hard-code prefix này trong app khi dự án đang cấu hình custom `computePrefixWith` hoặc `prefixCacheNameWith`.
- Hai lần gọi cùng key trả cùng String nhưng `callCount` chỉ tăng một lần; test còn kiểm tra một Redis key có TTL thật để tránh **false positive do NoOpCacheManager**.
- `@Cacheable` là cơ chế cache-aside theo proxy: invocation từ test qua Spring bean khác với `this.displayName` tự gọi trong service.

**Điểm chẩn đoán:** Nếu bài test hit/miss pass nhưng Redis không có key, hãy kiểm tra có đang sử dụng `ConcurrentMapCacheManager`, `NoOpCacheManager` hoặc mock bean khác hay không. Chỉ assert `first.equals(second)` chưa đủ, vì service có thể trả cùng giá trị một cách hoàn toàn deterministic dù cache không hoạt động.

## 8. Cache TTL, TTI và eviction cần test ở đúng mức

Trong `RedisCacheManager`, một cache entry thường được lưu như **Redis String key** với prefix, có TTL theo `RedisCacheConfiguration`. Đây **khác** Spring Data Redis repository `@RedisHash` và một `opsForHash` nhiều fields.

### 8.1. TTL khi cache hit không tự gia hạn

Với TTL 90 giây, gọi `service.displayName(sku)` lần thứ hai trước hạn thường là **cache hit**; không nhất thiết viết lại key hoặc reset expiration. Nếu sản phẩm cần **time-to-idle** thì phải bật cơ chế phù hợp (Spring Data Redis hỗ trợ lựa chọn TTI trong các phiên bản mới qua Redis `GETEX`, yêu cầu Redis 6.2+) và đảm bảo **mọi đường đọc** đồng nhất; một lệnh `GET` thường không gia hạn TTL.

### 8.2. Eviction có nhiều nghĩa

- `@CacheEvict(cacheNames="lookups", key="#p0")` yêu cầu cache manager xóa entry liên quan khi advice thực thi.
- `@CachePut` cập nhật một giá trị vào cache (khác `@Cacheable` có thể bỏ qua method invocation khi hit).
- `TTL expiration` là Redis xóa key sau thời gian sống.
- `Redis maxmemory eviction` là Redis loại key theo eviction policy khi thiếu RAM, có thể xảy ra **trước TTL**.
- `cache.clear()` của `RedisCacheManager` có thể quét key theo prefix; mặc định một số cấu hình dùng `KEYS`/ `DEL`. Với keyspace lớn, kiểm tra tác động hiệu năng và cân nhắc scan-based batch strategy.

Không gộp các hành vi đó thành một expectation “sau 90 giây chắc chắn có CacheEvict event”. Expiration không tự đồng nghĩa một Spring `@CacheEvict` method đã chạy.

### 8.3. Null caching, value serializer và prefix

`RedisCacheConfiguration` hỗ trợ disableCachingNullValues, key prefix và serializers. Mặc định `RedisCache` có thể serialize value theo Java native serialization, vốn có rủi ro/khó tương thích nếu không kiểm soát nguồn dữ liệu; trong môi trường không tin cậy nên thiết kế serializer an toàn như JSON với type allowlist/schema hoặc String cho payload đơn giản.

Một test chỉ đọc lại giá trị bằng **chính serializer đang ghi** có thể pass dù hệ thống khác không hiểu bytes đó. Nếu nhiều ứng dụng chia sẻ Redis keys, cần contract cấp bytes/key-name/prefix và test tương thích giữa các phiên bản.

## 9. @RedisHash repository, @TimeToLive và những key phụ

`@DataRedisTest` không chỉ dành cho templates. Spring Data Redis hỗ trợ Redis repositories trên các entity được chú thích `@RedisHash`.

Ví dụ **mô hình minh họa**:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 120)
public class SessionDocument {
    @Id
    private String id;
    private String owner;

    protected SessionDocument() {}

    public SessionDocument(String id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public String getId() { return id; }
    public String getOwner() { return owner; }
}
```

Đoạn trên là một class độc lập **nếu được lưu tại `SessionDocument.java`** trong package phù hợp và có dependencies Spring Data Redis, nhưng để tổ chức ví dụ chính tránh phát sinh repository keys phụ, ta không đưa class này vào source set ở mục 5. Repository đi kèm có thể là:

```java
interface SessionRepository
        extends CrudRepository<SessionDocument, String> {}
```

Với import `org.springframework.data.repository.CrudRepository`, interface nằm trong package scan của ứng dụng và Redis repository auto-configuration phù hợp sẽ tạo implementation. Dùng `@RedisHash(timeToLive=120)` để cấu hình TTL cho entity repository; `@TimeToLive` còn cho phép TTL động trên property/method trong các trường hợp Spring Data Redis hỗ trợ.

**Nhưng repository TTL không giống StringRedisTemplate TTL hoặc Redis cache TTL:**
- Entity thường được ghi dưới Redis Hash key như `sessions:<id>`, có thể có metadata/index keys.
- Spring Data Redis repository dùng keyspace event listener và trong một số trường hợp **phantom copy/shadow copy** của entity TTL để phát `RedisKeyExpiredEvent`.
- Expiration events dựa trên Redis Pub/Sub/keyspace notifications, **không phải durable event log**; nếu ứng dụng down hoặc notification bị chặn, event có thể bị mất.
- Redis managed services có thể hạn chế lệnh `CONFIG`, nên bật keyspace listener có thể lỗi; phải cấu hình theo môi trường hoặc tắt listener khi yêu cầu không cần.
- Nếu entity có secondary indexes, việc key chính hết hạn và việc dọn index phụ có thể không trùng thời điểm; test cleanup/isolation phải xét toàn bộ keys liên quan.

Bởi vậy, bài test repository TTL không nên chỉ `repo.save(entity); repo.findById(id)` rồi tin rằng mọi index key/expiration event chắc chắn đúng. Hãy kiểm tra key TTL, repository lookup sau expiration, event listener/secondary index behavior **trong một test độc lập trên Redis thật**, với timeout có giới hạn và dữ liệu được dọn.

## 10. Reactive Redis và subscription

Spring Data Redis cung cấp `ReactiveRedisTemplate` và `ReactiveStringRedisTemplate` trên classpath phù hợp. Trong reactive application, thao tác như:

```java
Mono<Boolean> written =
        reactiveRedis.opsForValue().set(
                "test:key", "value");
```

đây là **đoạn minh họa** với `ReactiveStringRedisTemplate reactiveRedis`. Nó tạo reactive publisher, không có nghĩa Redis command đã được thực thi nếu publisher chưa được subscribe.

Một unit/integration test reactive dùng Reactor Test:

```java
StepVerifier.create(written)
        .expectNext(true)
        .verifyComplete();
```

Cần imports `reactor.core.publisher.Mono` và `reactor.test.StepVerifier`, Redis reactive client thực, cùng cleanup. Trong một ứng dụng WebFlux, thường **return publisher** để framework subscribe; đừng gọi `.subscribe()` thủ công trong controller rồi coi command đã thuộc HTTP request lifecycle.

Để kiểm tra TTL reactive, có thể compose `set(key,value,ttl)`, `get`, `getExpire` thành publisher và assert signals qua `StepVerifier`; cần phân biệt lỗi kết nối Redis `onError` với một key not found `Mono.empty()`. `@DataRedisTest` với classpath reactive **không tự bảo đảm** bạn đã kiểm tra reactive execution nếu test chỉ inject template và không subscribe.

## 11. Transaction, atomicity và test isolation ở Redis

Redis có khái niệm `MULTI`/`EXEC` nhưng **không phải rollback transaction kiểu JDBC/JPA**. Một chuỗi lệnh Redis:
- Có thể được thực thi đơn lẻ.
- Có thể gom trong pipeline để giảm round trips (pipelining **không** tự là transaction).
- Có thể sử dụng Redis transaction `MULTI`/`EXEC`, nhưng semantics lỗi/rollback khác SQL.
- Có thể dùng Lua script để yêu cầu nhiều thao tác được xử lý atomically trên Redis instance.

Không dùng `@Transactional` trên test method rồi kết luận mọi Redis writes sẽ biến mất ở cuối test. Ngay cả khi bật `RedisTemplate.setEnableTransactionSupport(true)` và dùng Spring transaction synchronization, Redis không trở thành một SQL database có automatic rollback cho những commands đã thực thi.

### 11.1. Namespace và cleanup an toàn

- Dùng prefix riêng cho test class/run (`learn:redis:<uuid>:`) và ghi danh sách keys do từng test sở hữu.
- Dọn trong `@AfterEach` hoặc `finally`; khi test tạo cache keys hoặc repository shadow/index keys, cần dọn **toàn bộ phạm vi** tương ứng.
- Dùng container/database test cô lập cho suite nếu nhiều công cụ phát sinh keys không thể theo dõi đơn giản.
- **Không gọi `FLUSHALL` trên Redis chia sẻ**, đặc biệt khi host/port lấy từ biến môi trường production.
- Với nhiều keys, tránh `KEYS *` trong production do lệnh quét toàn bộ keyspace có thể gây ảnh hưởng lớn. Dùng `SCAN` có prefix giới hạn khi cần cleanup dạng quét, cùng quyền/cảnh báo phù hợp.
- Test chạy song song không được dùng key cố định như `cache:user:1` trừ khi Redis instance riêng hoặc có cơ chế partition.
- TTL ngắn không phải thay thế cleanup: test có thể fail/abort trước khi key hết hạn, và các data structures khác có thể persistent.

### 11.2. Đừng phụ thuộc thứ tự hoặc thời gian quá chính xác

Một ca test assertion `ttl == 30` hoặc `Thread.sleep(30000)` dễ flaky do scheduling, network latency và Redis expiration granularity. Dùng:
- TTL assertion dạng khoảng.
- Bounded polling khi muốn kiểm tra expired key đã biến mất.
- Unique test keys, không để suite trước sửa cùng key.
- Không bật Redis active expiration notifications rồi mặc định chúng là exactly-once/durable delivery.

### 11.3. Kiểm tra concurrency/race khi nghiệp vụ cần

Ví dụ `GET` sau đó `SET` là **read-modify-write** hai lệnh; nhiều client cùng thực thi có thể làm mất cập nhật. Nếu nghiệp vụ cần counter, dùng `INCR` atomic; nếu cần điều kiện, cân nhắc `SET NX EX`, Lua, optimistic `WATCH` hoặc Redis functions phù hợp.

Một test tuần tự trên Redis thật không chứng minh locking/concurrency khi 100 requests cùng lúc. Thiết kế integration test đa client và theo dõi kết quả cuối cùng nếu rủi ro đó quan trọng. Không gắn `synchronized` Java cục bộ rồi tin nó khóa được các application instances khác nhau.

## 12. Debug những lỗi Redis test thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `Connection refused` localhost:6379 | `@DataRedisTest` không tự tạo Redis server | Khởi động Testcontainers, kiểm tra host/mappedPort |
| Context có RedisTemplate nhưng `get` fail | Client bean tồn tại nhưng network/credentials/TLS sai | Gọi Redis thật, kiểm tra URL/port/auth |
| `NoSuchBeanDefinitionException` cho adapter `@Repository` viết tay | Component bị slice filter loại | Dùng `@Import(YourAdapter.class)` |
| `NoSuchBeanDefinitionException` cho `@Service` | Service không thuộc slice | Test Redis adapter trực tiếp hoặc import service cần thiết |
| `@Cacheable` gọi service hai lần | NoOpCacheManager, chưa `@EnableCaching`, self-invocation, key khác | Assert RedisCacheManager và key Redis thật |
| `@Cacheable` hit nhưng TTL luôn -1 | Cache config chưa đặt TTL hoặc ghi key ngoài cache manager | Kiểm tra `entryTtl`, key prefix và source writer |
| `getExpire` trả -2 | Key chưa tồn tại hoặc đã hết hạn | Kiểm tra key name, serializer và thời điểm đọc |
| `getExpire` trả -1 | Key persistent, TTL chưa được gán hoặc bị mất sau overwrite | Kiểm tra SET/EXPIRE/PERSIST |
| WRONGTYPE trên `opsForHash` | Key đang là Redis String/List/Set/... | `TYPE key`, namespace theo data type |
| Redis CLI thấy key lạ/không đọc được | Serializer nhị phân/JDK serialization | Kiểm tra template key/value/hash serializers |
| Hash field không hết hạn riêng | Expiration đang là key-level TTL | Test toàn key; nếu cần field TTL phải dùng API/server hỗ trợ rõ |
| List test fail thứ tự | Dùng LPUSH thay vì RPUSH hoặc đọc direction khác | Assert đúng command direction và range |
| Set test fail do thứ tự | SMEMBERS không có ordering guarantee | So sánh Set thay vì List |
| ZSet ranking test sai | Nhầm `range` với `reverseRange`, score ties | Assert score, direction và ties contract |
| Test pass dù Redis cache không chạy | NoOp cache hoặc mock service trả giá trị giống nhau | Assert method invocation count + actual Redis key/TTL |
| Dữ liệu test trước xuất hiện | Redis không tự rollback, reuse key cố định | Unique key, cleanup, isolated container |
| TTL test flaky | Assert giây chính xác, sleep cố định, CI chậm | Assert khoảng/poll đến deadline |
| Redis repository expired event không tới | Keyspace notification chưa bật/lost PubSub/CONFIG bị cấm | Kiểm tra event listener và Redis config |
| `@RedisHash` entity không được tìm thấy | Package scan sai hoặc repository auto-config bị tắt | Kiểm tra package, Redis repositories enabled |
| Test Redis thật xanh nhưng production fail | Sentinel/Cluster/TLS/serialization khác | Bổ sung integration test gần topology production |

Nếu build thất bại ở bước khởi tạo Spring context, tìm nguyên nhân gốc ở `Caused by`. Nếu test context khởi động nhưng command fail, kiểm tra client connect tới **server nào**, key serializer và lệnh Redis được gọi. Nếu assertion TTL fail, kiểm tra **có TTL hay không** trước khi nghi scheduling.

## 13. Dòng phiên bản: Boot 3.5 so với Boot 4

Ví dụ đầy đủ ở mục 5–7 dùng **Spring Boot 3.5.x**, với:

```java
org.springframework.boot.test.autoconfigure.data.redis.DataRedisTest
```

Trong Spring Boot **4.x**, Redis test slice được chuyển sang module chuyên biệt `spring-boot-data-redis-test`, với annotation:

```java
org.springframework.boot.data.redis.test.autoconfigure.DataRedisTest
```

Đây là **danh sách tên import**, không phải chương trình Java độc lập. Khi nâng Boot, phải đổi đúng test dependency/module và import theo Boot BOM. Không trộn Spring Boot test 4.x với runtime Spring Boot 3.x để “sửa” lỗi `Cannot resolve symbol DataRedisTest`.

Ở Spring Boot 4, **danh sách auto-config imported** của `@DataRedisTest` có thể khác Boot 3.5 (các nhóm Redis connection, reactive và Redis repositories vẫn là trọng tâm). Đừng bê nguyên kết luận về no-op cache của test 3.5 sang một Boot 4 context không kiểm tra được. Cách chắc chắn hơn là **kiểm tra `CacheManager` thực tế, Redis template/serializer, kết nối Redis và TTL của một key được tạo**.

Khi migration Spring Data Redis:
- Kiểm tra thay đổi trong serializer, DTO schema và key prefix; object round-trip với cùng serializer mới chưa chứng minh các ứng dụng cũ đọc được.
- Kiểm tra `@RedisHash` TTL/index/keyspace notifications và quyền Redis `CONFIG`.
- Kiểm tra topology: standalone vs Sentinel/Cluster vs managed Redis, SSL/TLS, ACL username/password.
- Chạy các contract tests của keys/TTL/cache behavior trên Redis server version đúng.
- Không dùng Redis 7.4 của bài demo làm bằng chứng tự động cho Redis 6.x, Redis 8.x hoặc một managed service với cấu hình chặt hơn.

## 14. Chạy bộ kiểm thử và đọc report

Từ root project có Gradle wrapper, Linux/macOS:

```bash
./gradlew test --tests "com.example.redisslice.RedisStructuresStoreTest"
./gradlew test --tests "com.example.redisslice.RedisCacheSliceTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.redisslice.RedisStructuresStoreTest"
.\gradlew.bat test --tests "com.example.redisslice.RedisCacheSliceTest"
```

Maven wrapper với dependencies tương đương, Linux/macOS:

```bash
./mvnw -Dtest=RedisStructuresStoreTest test
./mvnw -Dtest=RedisCacheSliceTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=RedisStructuresStoreTest test
.\mvnw.cmd -Dtest=RedisCacheSliceTest test
```

Các lệnh giả định project có wrapper, JDK 17+, Docker daemon hoạt động và đủ quyền pull/start Redis container. Trong Gradle, report thường ở `build/reports/tests/test/index.html`, Maven Surefire ở `target/surefire-reports/` (thuộc đúng module). Hãy kiểm tra lớp test được discover và thực thi; Docker unavailable, skipped hoặc `NO-SOURCE` **không** đồng nghĩa PASS.

Bộ code mẫu có **10 test methods** trong `RedisStructuresStoreTest` và **2 test methods** trong `RedisCacheSliceTest`. Không có `System.out.println` cố định, nên không tạo một stdout giả. Đây là tài liệu và ví dụ được biên soạn; phải chạy trên môi trường có Docker và dependencies phù hợp rồi mới khẳng định test runtime thực tế pass.

## 15. Checklist khi review @DataRedisTest

- [ ] Đã xác định rõ Redis test slice tập trung vào **Redis templates/repositories/entities**, không phải controller/service full context.
- [ ] Biết `@DataRedisTest` **không tự khởi động Redis server**; đã kết nối Redis test phù hợp.
- [ ] Nếu test adapter/DAO `@Repository` viết tay, đã `@Import` implementation thật.
- [ ] Không dùng mock RedisTemplate để kết luận SQL/Redis command thật, TTL hay data structure correctness.
- [ ] Mỗi nhóm key có namespace rõ; test `TYPE` khi dữ liệu phải là String/Hash/List/Set/ZSet cụ thể.
- [ ] Hash test kiểm tra field mapping và key-level TTL; không mặc nhiên coi field có TTL riêng.
- [ ] List test bảo vệ order/duplicates; Set test bảo vệ uniqueness; ZSet test bảo vệ score/direction.
- [ ] TTL test phân biệt positive TTL, `-1` persistent và `-2` missing; dùng khoảng và bounded polling.
- [ ] Test ghi Redis có cleanup/namespace riêng; không dựa vào rollback SQL hoặc `FLUSHALL`.
- [ ] Với `@Cacheable`, đã xác định cache manager thực là `RedisCacheManager` và `@EnableCaching` được bật; không bị no-op trong slice.
- [ ] Assert cache hit/miss qua số lần thực thi method **và** kiểm tra Redis key/value/TTL thực tế.
- [ ] Đã kiểm tra serialization, cache key prefix, invalidation/eviction policy nếu API phụ thuộc chúng.
- [ ] Nếu dùng `@RedisHash`, đã xét key phụ/index/phantom copy và độ tin cậy hạn chế của expiry events.
- [ ] Nếu dùng Reactive Redis, đã subscribe qua `StepVerifier` hoặc framework để bảo đảm command chạy.
- [ ] Khi tính đúng phụ thuộc concurrent access, đã test lệnh atomicity/race trên nhiều client; không nhầm pipeline và transaction.
- [ ] Đã chạy đúng JUnit classes trong đúng Boot version, kiểm tra report và Docker container logs khi lỗi.

## 16. Tài liệu chính thức để đối chiếu

- [Spring Boot 3.5 — Auto-configured Data Redis Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): phạm vi `@DataRedisTest` và điều kiện quét `@RedisHash`.
- [Spring Boot 3.5 — Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): những Redis auto-configurations trong slice.
- [Spring Boot 3.5 — AutoConfigureCache API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/core/AutoConfigureCache.html): default `NoOpCacheManager` của testing support.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): templates, operations views, serializers.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): cache manager, key prefix, TTL/TTI, serialization.
- [Spring Data Redis — TTL của Redis repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): `@RedisHash`, `@TimeToLive`, keyspace notification và shadow copy.
- [Spring Boot 4 — Test Slices](https://docs.spring.io/spring-boot/appendix/test-auto-configuration/slices.html): package/module Redis test slice của dòng Boot 4.

**Kết luận:** `@DataRedisTest` giúp kiểm thử **Spring Data Redis thực** mà không cần khởi động toàn ứng dụng, nhưng chính annotation này **không tạo Redis server và không tự bảo đảm cache Redis thật**. Với Redis Testcontainers, hãy kiểm tra data type đang dùng (`String`, `Hash`, `List`, `Set`, `Sorted Set`), TTL/expiration, serializers, key prefix và cleanup. Nếu mục tiêu là `@Cacheable`, bật caching rõ ràng và dùng `RedisCacheManager` thật để tránh no-op; nếu dùng Redis repositories, kiểm tra thêm `@RedisHash`, TTL và key/index phụ. Một bài test xanh chỉ có ý nghĩa khi nó đi qua **đúng data structure và server Redis** mà hợp đồng muốn bảo vệ.