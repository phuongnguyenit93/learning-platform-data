# Xóa cache giữa các ca kiểm thử và kiểm chứng cache provider thực tế

## 1. Vấn đề: unit test xanh nhưng integration test bị dữ liệu cache cũ

Giả sử một Spring Boot service có method:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public String find(String sku) {
    return productSource.load(sku);
}
```

Lần đầu gọi `find("CAM-01")`, method chạy và kết quả được lưu cache. Lần thứ hai cùng key, Spring có thể trả cache hit mà không chạy `productSource.load`. Điều này là hành vi cần kiểm thử.

Nhưng nếu test A vừa lưu `CAM-01`, test B thay dữ liệu nguồn rồi đọc cùng key mà **không xóa cache**, test B có thể nhận kết quả cũ. Test chạy riêng pass, chạy cả suite fail. Một nguyên nhân khác còn nguy hiểm hơn: team nghĩ đang test Redis thật, nhưng Spring Boot tự dùng `ConcurrentMapCacheManager`/Simple cache trong JVM, hoặc bị `spring.cache.type=none`, nên tất cả các assertions về “cache Redis” thực ra chưa từng kết nối Redis.

Bài học giải quyết **hai yêu cầu khác nhau**:

1. **Xóa trạng thái cache giữa các ca kiểm thử** bằng đúng phạm vi: `CacheManager.getCache(...).clear()`, `Cache.evict(key)`, `@CacheEvict`, vùng cache, namespace, isolated provider và test lifecycle.
2. **Kiểm chứng provider thực sự được dùng** bằng bằng chứng nhiều tầng: loại `CacheManager`, hành vi hit/miss và số lần gọi nguồn, **trạng thái key/TTL trên Redis thật**, eviction phản ánh xuống provider.

Chúng không thay thế nhau. Một test có `clear()` hoàn hảo chưa chắc dùng đúng provider; một test xác nhận `RedisCacheManager` thật vẫn có thể flaky vì không reset keys giữa methods.

Ví dụ trọng tâm dùng **Java 17, Spring Boot 3.3.0, Spring Cache, Spring Data Redis, Redis 7 trong Testcontainers, JUnit Jupiter**. Ta cố tình dùng một nguồn dữ liệu Java đếm số lần gọi thay vì database khác để phép thử tập trung vào **provider cache thật**. Các bài nâng cao sẽ chỉ ra khi cần thêm DB, multi-instance, race condition, transaction và CI integration testing.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Spring Cache abstraction không phải một cache store tự thân: cần `CacheManager` + provider.
2. Phân biệt `@Cacheable`, `@CachePut`, `@CacheEvict`, `Cache.evict(key)`, `Cache.clear()` và provider-level reset.
3. Phân biệt cache hit, miss, stale value, eviction, expiration TTL, manual refresh và test fixture mutation.
4. Biết vì sao `@EnableCaching`, AOP proxy và external method invocation là điều kiện quan trọng.
5. Dùng `@BeforeEach`/`@AfterEach` để dọn cache region thuộc test, không làm hỏng những regions khác.
6. Hiểu `@DirtiesContext` reset Spring `ApplicationContext` chứ **không bảo đảm xóa Redis data**.
7. Tách in-memory Caffeine cache và distributed Redis cache theo lifecycle và phạm vi state.
8. Dùng `spring.cache.type=redis` để bắt buộc provider, thay vì dựa vào classpath detection ngầm.
9. Dùng `GenericContainer<?>` + `@ServiceConnection(name="redis")` với Spring Boot 3.3 để tạo Redis thật cho tests.
10. Tránh viết `RedisContainer` từ thư viện bên thứ ba như thể đây là một official Testcontainers core module.
11. Xác minh `RedisCacheManager`, actual Redis key, TTL, cache hit/miss và delete semantics qua `StringRedisTemplate`.
12. Biết vì sao Redis key prefix mặc định thường là `cacheName::key` và khi nào format thay đổi.
13. Hiểu Redis value serialization: Spring Data Redis cache có thể dùng JDK serialization mặc định; đừng đọc binary value bằng String decoder rồi kết luận cache hỏng.
14. Viết các JUnit tests kiểm chứng cache giữ đúng một key, evict một key, evict mọi entries vùng cache, clear ở test setup/teardown và không cache exception.
15. Phân biệt TTL expiration với explicit eviction; không dùng `Thread.sleep` cố định làm oracle chính.
16. Thiết kế namespace/prefix/isolated broker cho concurrent CI jobs, tránh `FLUSHALL`/`FLUSHDB` trên Redis dùng chung.
17. Hiểu `Cache.clear()` có thể dùng Redis `KEYS`/`DEL`, gây scan/latency/race trên keyspace lớn.
18. Cẩn thận với `@Transactional`, commit timing, cache stampede, stale replication, asynchronous/Reactive cache managers.
19. Đọc đúng các lỗi: mock vs real provider, cache proxy bypass, wrong cache name/key, serialization, timeout, context cache, tests chạy song song.
20. Phân biệt **expected results** trong README với **Gradle/JUnit đã thực thi**.

## 3. Tầng Spring Cache và tầng storage là hai thứ khác nhau

```text
ProductCatalog.find("CAM-01")
        |
        v
Spring AOP CacheInterceptor
        |
        +-- Compute cache key: "CAM-01"
        +-- Resolve cache region: "products"
        |
        v
CacheManager
        |
        +-- ConcurrentMapCacheManager (local JVM)
        +-- CaffeineCacheManager     (local JVM with eviction policy)
        +-- RedisCacheManager        (external Redis server)
        +-- JCache/Hazelcast/...     (other provider implementations)
        |
        v
Cache.get(key)
        |
        +-- HIT: return cached value, skip target method
        |
        +-- MISS: invoke ProductSource.load(key)
                  then cache result (subject to policy)
```

Spring's `@Cacheable` annotation không chứa một cache engine. Nó chỉ khai báo **cache operation**; thực thi được giao cho `CacheManager`/`Cache` implementation. Chính provider quyết định cách lưu, serialization, TTL, eviction và phạm vi chia sẻ giữa JVMs.

### 3.1. Cùng annotation nhưng behavior không hoàn toàn như nhau

| Thuộc tính | Simple/ConcurrentMap | Caffeine | Redis |
| --- | --- | --- | --- |
| Vị trí lưu | Heap của JVM | Heap JVM | Redis server/process |
| Dùng chung nhiều app instances | Không | Không | Có nếu dùng cùng Redis namespace |
| Restart JVM | Mất cache | Mất cache | Redis có thể vẫn còn data |
| TTL/LRU | Không tự có đầy đủ policies | Hỗ trợ qua spec/config | TTL từ Redis cache configuration |
| Serialization qua network | Không | Không | Có, theo RedisCache serializer |
| `Cache.clear()` | Clear local map | Invalidate local region | Delete matching Redis keys |
| Test provider-specific errors | Không có network | Không có network | Auth/socket/serialization/TTL/etc |
| Test isolation | Local context/JVM | Local context/JVM | Cần dọn Redis namespace/broker |
| Cần Docker cho lab | Không | Không | Có với Testcontainers |

Không thể lấy một unit test dùng Caffeine/Map rồi tuyên bố đã kiểm tra Redis serialization, Redis key prefix, TTL, network failure hoặc đa instance consistency.

### 3.2. Spring Boot tự chọn provider như thế nào?

Spring Boot có cache auto-configuration, lựa chọn theo classpath và các beans sẵn có. Khi có nhiều provider, thứ tự detection có thể tạo khác biệt giữa máy/test profile.

Ví dụ:

```properties
spring.cache.type=redis
spring.cache.cache-names=products
spring.cache.redis.time-to-live=60s
spring.cache.redis.cache-null-values=false
```

Bằng cách đặt `spring.cache.type=redis`, integration test **không cho phép** ứng dụng âm thầm fallback sang provider khác để làm test xanh. Nếu Redis không kết nối được, test sẽ fail ở provider operation thay vì tiếp tục chạy local map.

Các giá trị trên được đưa trực tiếp vào `@SpringBootTest(properties=...)` trong ví dụ runnable. **Không dùng `spring.cache.type=none`** trong test có mục tiêu chứng minh caching.

## 4. Cache hit, miss, eviction và TTL

### 4.1. Cache miss

Khi key không tồn tại, `CacheInterceptor` gọi target method, lưu kết quả (nếu điều kiện cho phép) và trả value.

```text
GET products["CAM-01"] -> MISS
source.load("CAM-01") -> "CAM-01#load-1"
PUT products["CAM-01"] = "CAM-01#load-1"
return "CAM-01#load-1"
```

### 4.2. Cache hit

Lần sau cùng key:

```text
GET products["CAM-01"] -> HIT
return "CAM-01#load-1"
source.load(...) không chạy
```

Một assertion `assertEquals(result1, result2)` **chưa đủ**: source có thể luôn trả cùng string mà không cache. Phải chứng minh cả **số lần gọi source không tăng** hoặc quan sát provider state.

### 4.3. Eviction một key

`Cache.evict(key)` hoặc `@CacheEvict(cacheNames="products",key="#p0")` xóa mapping của một key. Lần sau gọi `@Cacheable` sẽ miss và nạp lại.

Eviction không phải cập nhật dữ liệu nguồn. Xóa cache key không xóa row database; xóa row database không tự xóa cache entry nếu application không có invalidation policy.

### 4.4. Eviction mọi entry của một cache region

`Cache.clear()` hoặc `@CacheEvict(cacheNames="products",allEntries=true)` xóa mọi entries của vùng `products`, **không phải mọi Redis keys của mọi ứng dụng**. Điều này đúng khi cache config/namespace được thiết kế và provider thực thi đúng.

**Giới hạn:** Trong Redis, default cache writer có thể dùng scanning/deletion theo prefix (một số versions/strategies dùng `KEYS`); thao tác trên keyspace lớn hoặc shared namespace có thể tốn chi phí và không là transaction atomic chống concurrent writers. Bài lab dùng RedisContainer private và chỉ vài keys.

### 4.5. TTL expiration

Một entry có TTL 60 giây tồn tại đến khi hết hạn (trừ khi bị xóa/ghi đè theo provider policy). TTL là **time-based expiration**, không phải việc `@AfterEach` dọn cache. Khi test cần isolation chắc chắn, **không chờ TTL trôi qua**; hãy evict/clear đúng phạm vi.

Đặc biệt Redis TTL có thể là **time to live**, không phải time to idle. Việc GET cached value thường không tự reset TTL khi dùng default RedisCache behavior. Các cấu hình TTI, đặc biệt ở Spring Data Redis versions mới, cần API/Redis server compatibility riêng.

## 5. @Cacheable, @CachePut, @CacheEvict khác nhau

| Annotation/API | Hành vi | Trường hợp test |
| --- | --- | --- |
| `@Cacheable` | Kiểm tra cache trước; hit bỏ qua target method | 2 calls → source count 1 |
| `@CachePut` | Gọi method và cập nhật cache bằng kết quả | Update source rồi read lại |
| `@CacheEvict(key=...)` | Loại một entry | Cache A/B, xóa A, B vẫn hit |
| `@CacheEvict(allEntries=true)` | Clear một cache region | Xóa mọi products entries |
| `Cache.evict(key)` | Evict programmatically qua Cache abstraction | Setup/teardown key-level |
| `Cache.clear()` | Clear toàn region qua Cache abstraction | BeforeEach/AfterEach trên private Redis |
| Redis `DEL` | Xóa một raw Redis key | Provider-level verification |
| Redis `FLUSHDB` | Xóa cả Redis logical DB | Nguy hiểm ở shared database |
| Redis `FLUSHALL` | Xóa tất cả logical DBs trên server | Cực kỳ nguy hiểm ở shared server |

### 5.1. beforeInvocation của @CacheEvict

`@CacheEvict` có `beforeInvocation` mặc định là `false`; eviction diễn ra sau khi method hoàn tất thành công theo synchronous semantics. Nếu method throw exception, eviction có thể không xảy ra. `beforeInvocation=true` yêu cầu eviction trước khi method chạy dù method sau đó có lỗi.

Ví dụ minh họa, **không phải source runnable của lab**:

```java
@CacheEvict(
        cacheNames = "products",
        key = "#p0",
        beforeInvocation = true)
public void invalidateBeforeWork(String sku) {
    doPotentiallyFailingWork(sku);
}
```

Không chọn `beforeInvocation=true` chỉ vì muốn “test dễ pass”: nếu DB update fail mà cache đã xóa, người dùng có thể gặp miss/stampede không cần thiết. Với transaction, phải thiết kế eviction theo commit boundary và test riêng.

### 5.2. @CachePut không thay @Cacheable

`@CachePut` luôn chạy method rồi cập nhật cache, nên không dùng nó để chứng minh cache hit tránh đọc source. `@Cacheable` và `@CachePut` trên cùng method có thể có semantics khó hiểu; nên tách read/update/invalidate methods rõ ràng.

### 5.3. Key expression cần khớp

Trong ví dụ dùng `key="#p0"` thay vì `key="#sku"` để key vẫn được resolve ngay cả khi compiled parameter name metadata không có. Nếu một method dùng `#p0` còn eviction method dùng sai `#p1` hoặc stringify key khác, eviction không xóa entry đã tạo.

## 6. Proxy và @EnableCaching: lý do test nhìn thấy sai số lần gọi

Spring `@Cacheable` thường được AOP proxy thực thi. Với proxy mode mặc định:

- Gọi từ bean khác vào method public có annotation → được intercept.
- Tạo `new ProductCatalog(...)` ngoài Spring → không có cache proxy.
- Gọi `this.find(...)` bên trong chính ProductCatalog (self-invocation) → thường bypass proxy.
- Annotate private/final method hoặc cấu hình proxy không phù hợp → không bảo đảm interceptor áp dụng.
- Quên `@EnableCaching` → annotation không tạo caching behavior.

```java
@Service
class Example {
    @Cacheable(cacheNames = "products")
    public String find(String id) { return "value"; }

    public String insideSameBean(String id) {
        return this.find(id); // thường bypass Spring cache proxy
    }
}
```

Đây là code minh họa. Trong runnable lab, JUnit inject `ProductCatalog` bean từ Spring context và gọi `catalog.find(...)` từ ngoài bean, nên cache interception thực sự xảy ra.

### 6.1. Cách phát hiện caching bị tắt

Một test tốt phải chứa cả:

```java
String first = catalog.find("CAM-01");
String second = catalog.find("CAM-01");

assertEquals(first, second);
assertEquals(1, source.calls());
```

Nếu `@EnableCaching` bị bỏ, số lần gọi source thành 2 và test đỏ, dù giá trị có vẻ giống nhau.

### 6.2. AOP proxy và @MockBean

Trong Boot 3.3, `@MockBean` có thể thay một bean trong ApplicationContext. Nếu mock chính `ProductCatalog` cần test cache annotation, bạn có thể bỏ qua proxy và storage operation. Nên mock **data source/repository collaborator** ở unit test riêng, còn integration test provider giữ **ProductCatalog bean thật**.

Với bài Redis, chính source cũng là một Java component thật đếm invocations để tránh Mockito deep stubbing che side effects. Không có database trong lab vì mục tiêu là xác minh Redis cache layer.

## 7. Xác định mức độ test

| Loại test | Provider | Có thể chứng minh | Chưa thể chứng minh |
| --- | --- | --- | --- |
| Plain unit test | Mockito Cache interface | Business fallback/invalidation choice | Redis key/TTL/network |
| Spring test with Simple cache | ConcurrentMapCacheManager | Annotation/proxy behavior cơ bản | Redis provider |
| Spring test with Caffeine | CaffeineCacheManager | Local eviction/TTL/size policies | Multi-instance Redis state |
| Boot integration + Redis Testcontainers | RedisCacheManager + Redis container | Actual key, TTL, serialization path, eviction | Managed Redis HA/TLS/ACL/cluster |
| 2 application contexts against same Redis | Redis distributed cache | Multi-instance sharing/invalidation | Production topology hoàn chỉnh |
| Deployment/staging test | Managed cache + network | Provider auth/topology/operability | Mọi race/traffic pattern production |

Đừng chỉ assert `cacheManager != null`: mọi CacheManager đều đáp ứng. Muốn Redis thực, assert implementation type **và provider-side key presence**.

## 8. Chiến lược dọn cache giữa các JUnit tests

### 8.1. @BeforeEach

`@BeforeEach` clear cache trước khi test setup/fixture assertions. Nó ngăn state từ test trước làm test sau nhận cache hit. Nếu source là một shared in-memory counter, reset counter **sau khi đã clear cache**, để lần gọi sau bắt đầu từ 1.

```java
@BeforeEach
void beforeEach() {
    Cache cache = cacheManager.getCache("products");
    assertNotNull(cache);
    cache.clear();
    source.reset();
}
```

Đây là snippet minh họa; trong project runnable helper `productsCache()` kiểm tra cache existence và cả phương thức còn dọn một sentinel key thuộc test.

### 8.2. @AfterEach

`@AfterEach` dọn cache sau test (kể cả assertion failure thông thường), giảm rò state sang các lớp/suites sau. Không nên chỉ dựa vào @AfterEach vì nếu test process crash, teardown không được chạy.

```java
@AfterEach
void afterEach() {
    productsCache().clear();
}
```

Trong môi trường Redis private, cả trước và sau mỗi method là phương án đơn giản. Nếu chạy parallel trên **cùng cache namespace**, một test đang dùng key có thể bị `@AfterEach` của test khác xóa: cần unique prefix/region/provider hoặc serialize tests.

### 8.3. Khi nên dùng @BeforeAll/@AfterAll?

- `@BeforeAll`: chuẩn bị dedicated provider/topic/namespace, không thay thế per-test isolation nếu tests cùng key.
- `@AfterAll`: dừng resource/provider class-scoped, cleanup namespace nếu được sở hữu.
- `@Testcontainers @Container static`: Redis container sống suốt một test class, rồi Testcontainers extension dừng container.
- Nếu nhiều classes dùng chung container/Redis namespace, cần policy riêng; không cho rằng JUnit class teardown đã xóa shared provider state.

### 8.4. Không gọi @DirtiesContext là Redis cleanup

`@DirtiesContext` làm Spring TestContext bỏ application context cache và tạo context mới theo mode, nhưng **external Redis keys vẫn nằm trên Redis server** nếu server còn tồn tại. RedisCacheManager bean mới có thể đọc chính những cached keys cũ.

Cũng tương tự: Spring `@Transactional` trên test thường rollback database transaction do test thread quản lý, **không tự rollback Redis SET/DEL**; cache put/evict có thể xảy ra ngoài transaction boundary. Phải cleanup cache riêng.

## 9. Dùng CacheManager, không phá Redis toàn cục

Trong test chỉ cần xóa product cache:

```java
Cache cache = cacheManager.getCache("products");
if (cache == null) {
    throw new IllegalStateException(
            "Missing products cache");
}
cache.clear();
```

**Lợi ích:** không phụ thuộc cách cache provider hiện lưu key/value. Với Caffeine, clear local cache. Với Redis, provider xóa keys thuộc region theo configuration.

**Giới hạn:** `Cache.clear()` vẫn có thể tốn chi phí và không nguyên tử đối với concurrent writes. Nó không tự dọn orphan keys thuộc cache names cũ, các TTL khác hoặc một Redis namespace do bên ngoài tạo.

### 9.1. Dọn key cụ thể

Khi nhiều tests chia sẻ provider, dùng `cache.evict(sku)` có phạm vi hẹp hơn `clear()`. Nếu test đã tạo key "CAM-01", hãy chỉ xóa "CAM-01" thay vì mọi keys của cache region. Tuy nhiên với **parallel tests cùng một key**, cả evict lẫn source counters vẫn có race; cần unique IDs.

### 9.2. FLUSHDB và FLUSHALL: không dùng làm mặc định

Redis `FLUSHDB` xóa mọi key trong logical DB được chọn; `FLUSHALL` xóa mọi logical DBs. Trên shared Redis chúng có thể xóa sessions, rate-limit counters, locks, queues, caches của ứng dụng khác, gây hậu quả nghiêm trọng.

**Trong lab private RedisContainer**, bạn có quyền xóa toàn bộ container sau class, nhưng vẫn nên thực hành cleanup theo region `products`. Điều này giúp viết test có ownership rõ và không vô tình mang `FLUSHALL` sang môi trường chung.

## 10. Dự án runnable — Java 17 + Spring Boot 3.3 + Redis Testcontainers

Project có **một test class** để tránh mismatch giữa Testcontainers class lifecycle và Spring TestContext cache qua nhiều classes. Dùng `GenericContainer<?>` cho Redis image thay vì giả định có một official `RedisContainer` ở Testcontainers 1.x.

### 10.1. Cấu trúc thư mục

```text
redis-cache-integration/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/cache/
    │   ├── CacheLabApplication.java
    │   ├── ProductSource.java
    │   └── ProductCatalog.java
    └── test/java/example/cache/
        └── RedisCacheIsolationTest.java
```

Không liệt kê wrapper binary files; nếu cần tạo Gradle Wrapper, dùng Gradle tương thích (ví dụ 8.7) và commit wrapper vào project thật.

### 10.2. settings.gradle

```groovy
rootProject.name = 'redis-cache-integration'
```

### 10.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao chỉ có những dependencies này?**

- `spring-boot-starter-cache`: Spring Cache abstraction và cấu hình hỗ trợ.
- `spring-boot-starter-data-redis`: Spring Data Redis/Lettuce Redis clients và RedisCacheManager auto-configuration.
- `spring-boot-starter-test`: JUnit Jupiter, AssertJ, Spring Test.
- `spring-boot-testcontainers`: Spring Boot `@ServiceConnection` support.
- `org.testcontainers:junit-jupiter`: Testcontainers JUnit 5 extension; kéo Testcontainers core cần thiết.
- Không cần thêm một Redis Testcontainers module riêng không tồn tại trong bộ official modules đang sử dụng.

Với Spring Boot 3.3 dependency management, các versions được điều phối qua Boot BOM. Nếu muốn nâng Testcontainers major hoặc Spring Data Redis, phải rà breaking changes thay vì copy imports từ version khác.

### 10.4. CacheLabApplication.java

**src/main/java/example/cache/CacheLabApplication.java**

```java
package example.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@EnableCaching
public class CacheLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                CacheLabApplication.class, args);
    }
}
```

`@EnableCaching` bật Spring cache interception. Trong lab không có Web starter: đây là application context phục vụ service/cache tests, không mở HTTP server.

Nếu bỏ `@EnableCaching`, `@Cacheable` không chặn method calls và số lần gọi source sẽ tăng ở cả hai reads; một trong những tests sẽ fail.

### 10.5. ProductSource.java — nguồn giả nhưng đếm được

**src/main/java/example/cache/ProductSource.java**

```java
package example.cache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class ProductSource {

    private final AtomicInteger calls = new AtomicInteger();

    public String load(String sku) {
        int n = calls.incrementAndGet();

        if ("FAIL".equals(sku)) {
            throw new IllegalStateException(
                    "Backend unavailable");
        }

        return sku + "#load-" + n;
    }

    public int calls() {
        return calls.get();
    }

    public void reset() {
        calls.set(0);
    }
}
```

**Tại sao không dùng database thật?** Bài này chỉ nhằm chứng minh Redis cache behavior. `ProductSource` là một **deterministic Java data source simulator**, không phải DB. Với `AtomicInteger`, test kiểm tra số lần tải nguồn chính xác. Khi cần chứng minh cache + JPA consistency, thêm database Testcontainers riêng; không nhầm demo này với DB integration test.

**Vì sao trả String?** Spring Data Redis `RedisCacheManager` mặc định có thể dùng Java/JDK serialization cho values; `String` implement Serializable. Nếu trả custom record/entity mà không Serializable và không tùy chỉnh serializer, có thể gặp `SerializationException`. Bài học Redis storage không phụ thuộc vào việc chọn một DTO serializer phức tạp.

### 10.6. ProductCatalog.java — @Cacheable và @CacheEvict

**src/main/java/example/cache/ProductCatalog.java**

```java
package example.cache;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalog {
    private final ProductSource source;

    public ProductCatalog(ProductSource source) {
        this.source = source;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public String find(String sku) {
        return source.load(sku);
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void invalidate(String sku) {
        // Eviction happens through Spring Cache proxy.
    }

    @CacheEvict(cacheNames = "products", allEntries = true)
    public void invalidateAll() {
        // Clears only the "products" cache region.
    }
}
```

Cả ba methods đều **public** và được gọi từ test qua Spring-managed `ProductCatalog` bean, bảo đảm cache advisor có cơ hội intercept. Không dùng `this.find(...)` bên trong cùng class để giả lập một external call. `#p0` là argument đầu tiên, tránh phụ thuộc metadata tên tham số.

**@CacheEvict void method:** hợp lệ, vì eviction action không cần return value. `beforeInvocation=false` mặc định nên với synchronous void method không throw, eviction được tiến hành sau khi method hoàn tất.

## 11. RedisCacheIsolationTest.java — integration test dùng Redis thật

**src/test/java/example/cache/RedisCacheIsolationTest.java**

```java
package example.cache;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest(properties = {
        "spring.cache.type=redis",
        "spring.cache.cache-names=products",
        "spring.cache.redis.time-to-live=60s",
        "spring.cache.redis.cache-null-values=false"
})
class RedisCacheIsolationTest {

    @Container
    @ServiceConnection(name = "redis")
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.2-alpine"))
                    .withExposedPorts(6379);

    private static final String OTHER_KEY =
            "integration:other-sentinel";

    @Autowired
    CacheManager cacheManager;

    @Autowired
    ProductCatalog catalog;

    @Autowired
    ProductSource source;

    @Autowired
    StringRedisTemplate redis;

    private Cache productsCache() {
        Cache cache = cacheManager.getCache("products");
        assertNotNull(cache);
        return cache;
    }

    private String redisKey(String sku) {
        // Default RedisCache prefix: cacheName + "::".
        return "products::" + sku;
    }

    private boolean exists(String key) {
        return Boolean.TRUE.equals(redis.hasKey(key));
    }

    @BeforeEach
    void resetStateBeforeTest() {
        productsCache().clear();
        redis.delete(OTHER_KEY);
        source.reset();
    }

    @AfterEach
    void clearOwnedStateAfterTest() {
        productsCache().clear();
        redis.delete(OTHER_KEY);
    }

    @Test
    void usesRedisCacheManagerAndStoresActualRedisKey() {
        assertTrue(REDIS.isRunning());
        assertInstanceOf(
                RedisCacheManager.class, cacheManager);

        assertFalse(exists(redisKey("CAM-01")));

        assertEquals(
                "CAM-01#load-1",
                catalog.find("CAM-01"));

        assertTrue(exists(redisKey("CAM-01")));
        assertEquals(1, source.calls());
    }

    @Test
    void cacheHitSkipsCallingSourceAgain() {
        String first = catalog.find("CAM-02");
        String second = catalog.find("CAM-02");

        assertEquals("CAM-02#load-1", first);
        assertEquals(first, second);
        assertEquals(1, source.calls());

        assertNotNull(productsCache().get("CAM-02"));
        assertTrue(exists(redisKey("CAM-02")));
    }

    @Test
    void redisEntryHasConfiguredPositiveTtl() {
        catalog.find("CAM-03");

        Long ttl = redis.getExpire(
                redisKey("CAM-03"),
                TimeUnit.SECONDS);

        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 60,
                "Expected a positive TTL up to 60s; " +
                "actual=" + ttl);
    }

    @Test
    void evictOneKeyLeavesOtherProductCached() {
        assertEquals(
                "A#load-1",
                catalog.find("A"));
        assertEquals(
                "B#load-2",
                catalog.find("B"));

        catalog.invalidate("A");

        assertFalse(exists(redisKey("A")));
        assertTrue(exists(redisKey("B")));

        assertEquals(
                "A#load-3",
                catalog.find("A"));
        assertEquals(
                "B#load-2",
                catalog.find("B"));
        assertEquals(3, source.calls());
    }

    @Test
    void evictAllClearsProductsButKeepsUnrelatedKey() {
        catalog.find("A");
        catalog.find("B");
        redis.opsForValue().set(
                OTHER_KEY, "not-a-product-cache-entry");

        catalog.invalidateAll();

        assertFalse(exists(redisKey("A")));
        assertFalse(exists(redisKey("B")));
        assertTrue(exists(OTHER_KEY));

        assertEquals("A#load-3", catalog.find("A"));
        assertEquals(3, source.calls());
    }

    @Test
    void directCacheClearRemovesUnderlyingRedisEntry() {
        assertEquals(
                "CAM-04#load-1",
                catalog.find("CAM-04"));
        assertTrue(exists(redisKey("CAM-04")));

        productsCache().clear();

        assertFalse(exists(redisKey("CAM-04")));

        assertEquals(
                "CAM-04#load-2",
                catalog.find("CAM-04"));
        assertEquals(2, source.calls());
    }

    @Test
    void exceptionsAreNotStoredAsCachedValues() {
        assertThrows(
                IllegalStateException.class,
                () -> catalog.find("FAIL"));
        assertFalse(exists(redisKey("FAIL")));

        assertThrows(
                IllegalStateException.class,
                () -> catalog.find("FAIL"));
        assertEquals(2, source.calls());
        assertFalse(exists(redisKey("FAIL")));
    }
}
```

**Có 7 phương thức `@Test`** trong class integration. Đây là test có real Redis process trong Testcontainers: vì `StringRedisTemplate` hỏi Redis server về key/TTL nên không chỉ tin một fake `Cache` object.

### 11.1. Vì sao @ServiceConnection(name="redis")?

`GenericContainer<?>` chỉ nói “một Docker container”, không có Java type `RedisContainer` để Spring Boot suy ra dịch vụ. Trong Boot 3.3, `@ServiceConnection(name="redis")` cho biết container này cung cấp `RedisConnectionDetails`, để auto-configured Spring Redis connection trỏ đúng mapped host/port động.

Nếu bỏ `name="redis"` khỏi GenericContainer, Boot có thể không xác định service type mong muốn; test có thể cố kết nối Redis mặc định ở `localhost:6379` và thất bại hoặc, nguy hiểm hơn, kết nối nhầm Redis đang chạy trên host.

**Không hardcode** `localhost:6379` cho Testcontainers. Host port được Docker map ngẫu nhiên; Boot service connection mang thông tin đó vào `LettuceConnectionFactory`/Redis clients.

### 11.2. Vì sao không @DynamicPropertySource?

`@DynamicPropertySource` là một phương án hợp lệ khác để cấp `spring.data.redis.host` và `spring.data.redis.port` từ container. Nhưng ví dụ này đã dùng `@ServiceConnection`, nên không cấu hình cả hai và để precedence trở nên khó hiểu. Chọn một đường kết nối có chủ đích, kiểm tra thật bằng provider-side assertions.

Snippet minh họa thay thế (không thuộc runnable class):

```java
@DynamicPropertySource
static void redisConnection(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.data.redis.host", REDIS::getHost);
    registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
}
```

Đoạn cần imports `DynamicPropertySource`/`DynamicPropertyRegistry`. Nếu dùng cách này, cần bỏ `@ServiceConnection` để tránh cấu hình kép không cần thiết.

### 11.3. Redis image version

`redis:7.2-alpine` là **tag minh họa phục vụ học tập**, không được hiểu là bản vá mới nhất. CI production-quality nên chọn image digest/version được duyệt, có security review và phù hợp architecture. `@ServiceConnection(name="redis")` làm việc với image name khi provider behavior tương thích.

### 11.4. Vì sao project không có RedisContainer module?

Testcontainers 1.x core có `GenericContainer` và module hỗ trợ nhiều dịch vụ. Với Redis, Spring Boot chính thức minh họa `GenericContainer` và `@ServiceConnection(name="redis")`. Có thể có RedisContainer classes từ cộng đồng hoặc các bản thư viện khác, nhưng không giả định chúng thuộc official Testcontainers core. Điều này tránh Gradle dependency/Java import không tìm thấy.

## 12. Phân tích bằng chứng “provider thực tế”

### 12.1. Assert loại CacheManager

```java
assertInstanceOf(
        RedisCacheManager.class, cacheManager);
```

Nếu Spring Boot tự cấu hình `ConcurrentMapCacheManager` hoặc Caffeine cache, assertion fail ngay. Nhưng **assert class thôi chưa đủ**: RedisCacheManager có thể được tạo nhưng không có kết nối đến đúng Redis container hoặc operations lỗi khi truy cập.

### 12.2. Assert key thật trên Redis

```java
catalog.find("CAM-01");
assertTrue(Boolean.TRUE.equals(
        redis.hasKey("products::CAM-01")));
```

`StringRedisTemplate` thực thi Redis query đến server. Nếu chỉ có local cache, Redis key sẽ không xuất hiện. Kết hợp với cache hit count, nó chứng minh cả Spring caching interception **và** provider storage.

**Giới hạn của format key:** `products::CAM-01` là default RedisCache key prefix của cấu hình lab, không phải contract của tất cả ứng dụng. Custom `RedisCacheConfiguration.computePrefixWith(...)`, `disableKeyPrefix()`, CacheKeyPrefix hoặc key generator có thể đổi format. Tests của một ứng dụng thật nên đọc config/lock contract key prefix rõ ràng, không hardcode một value khi setup đã thay đổi.

### 12.3. Assert TTL

```java
Long ttl = redis.getExpire(
        "products::CAM-03",
        TimeUnit.SECONDS);

assertNotNull(ttl);
assertTrue(ttl > 0 && ttl <= 60);
```

Redis TTL reply có các special values như `-1` (key tồn tại nhưng không có expiration) và `-2` (key không tồn tại) ở mức server. Spring Data Redis template trả numeric TTL tương ứng. Test assert positive TTL (và không vượt cấu hình) mà không cần `Thread.sleep(60_000)`.

**Không assert TTL bằng đúng 60**; tại thời điểm test đọc, một ít thời gian đã trôi qua. Nếu chạy cực chậm khiến entry hết hạn ngay, test fail; điều đó phản ánh environment/test limit, không nên tăng timeout vô hạn.

### 12.4. Assert source count

```java
String first = catalog.find("CAM-02");
String second = catalog.find("CAM-02");

assertEquals(first, second);
assertEquals(1, source.calls());
```

Nếu annotation `@Cacheable` bị bỏ hoặc proxy bypass, source count thành 2. Nếu cache provider không ghi được, thứ hai có thể miss; test fail, cho biết hành vi caching không đúng.

### 12.5. Assert single-key eviction

Trong `evictOneKeyLeavesOtherProductCached`, source load A rồi B. Sau `catalog.invalidate("A")`:

- Key A mất.
- Key B còn.
- Đọc A sẽ load lại, source count tăng.
- Đọc B vẫn là cached value, source count không tăng.

Đó là bằng chứng eviction **đúng phạm vi key**, không phải chỉ xóa toàn Redis.

### 12.6. Assert allEntries không đụng key ngoài namespace

Test `evictAllClearsProductsButKeepsUnrelatedKey` tạo sentinel key `integration:other-sentinel` trực tiếp trong Redis. `catalog.invalidateAll()` xóa A/B thuộc cache `products`, nhưng sentinel vẫn tồn tại.

Nếu bạn nhầm `@CacheEvict(allEntries=true)` với Redis `FLUSHDB`, sentinel sẽ mất và assertion fail. Điều này giúp kiểm tra region isolation ở mức storage thật.

## 13. Chạy project và expected results

Yêu cầu:

- JDK 17.
- Gradle Wrapper tương thích (ví dụ Gradle 8.7).
- Docker/compatible container runtime.
- Quyền pull image Redis và truy cập Maven repositories/cache.

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.cache.RedisCacheIsolationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.cache.RedisCacheIsolationTest
```

**Dự kiến:** 7 JUnit tests pass khi Redis container start, Spring Boot auto-configure RedisCacheManager đúng, và code được tạo ở đúng đường dẫn. Một lần chạy có thể kéo Redis image qua network. Test không có stdout business cố định. Không in fake Docker logs, random port hay Redis hash như kết quả đã đo.

| Test | Bằng chứng |
| --- | --- |
| `usesRedisCacheManagerAndStoresActualRedisKey` | Provider thực Redis + key Redis tồn tại |
| `cacheHitSkipsCallingSourceAgain` | Hai reads chỉ một source call |
| `redisEntryHasConfiguredPositiveTtl` | Entry có TTL đúng phạm vi |
| `evictOneKeyLeavesOtherProductCached` | Eviction key A không đụng key B |
| `evictAllClearsProductsButKeepsUnrelatedKey` | Region clear không xóa Redis key khác |
| `directCacheClearRemovesUnderlyingRedisEntry` | Cache API clear xóa key thật |
| `exceptionsAreNotStoredAsCachedValues` | Exception không bị cache như value thành công |

**Nếu Docker không tồn tại:** test sẽ fail khi Testcontainers không tìm được runtime; không tự đổi sang Simple cache rồi báo integration Redis test PASS. Nếu CI muốn skip Docker tests có điều kiện, báo rõ executed/skipped, không âm thầm gắn nhãn provider verified.

## 14. Vì sao cleanup đặt cả @BeforeEach và @AfterEach?

Trong test class:

```java
@BeforeEach
void resetStateBeforeTest() {
    productsCache().clear();
    redis.delete(OTHER_KEY);
    source.reset();
}

@AfterEach
void clearOwnedStateAfterTest() {
    productsCache().clear();
    redis.delete(OTHER_KEY);
}
```

**BeforeEach:** loại cache hit do trạng thái method trước; reset source counter sau đó giúp assertions cố định.

**AfterEach:** giảm rò keys sang test kế tiếp hoặc code kiểm tra sau failure. JUnit thường vẫn gọi callback dù `@Test` throw exception/assertion failure, trừ khi process bị kill hoặc runtime thất bại nghiêm trọng.

**Vì sao không xóa mọi Redis keys?** Test chỉ sở hữu region `products` và một sentinel key. Các resources khác không thuộc quyền test, nên không chạm. Redis container trong lab là private, nhưng thói quen đúng sẽ cần khi chuyển sang shared environment.

### 14.1. Test nào chứng minh clear thật?

`directCacheClearRemovesUnderlyingRedisEntry` gọi `productsCache().clear()` ngay trong test, rồi assert `redis.hasKey(...)` là false. Nó **kiểm tra hành vi của thao tác clear**, không chỉ giả định callback @AfterEach đã chạy.

### 14.2. Vì sao không dựa vào thứ tự methods?

JUnit không hứa test methods chạy theo thứ tự khai báo nếu không cấu hình order. Mỗi `@Test` tự seed dữ liệu, kiểm tra behavior của mình và cleanup. Không thiết kế “test B mong test A đã lưu key”. Với cùng cache provider và static container, class mặc định chạy sequential; khi bật JUnit parallel cần isolation tốt hơn.

### 14.3. Mối nguy khi cleanup thất bại

Nếu Redis connection lỗi ở `@AfterEach`, test không thể tuyên bố đã dọn sạch. Đừng viết `catch (Exception ignored) {}` để giấu lỗi. Khi broker là container private và sắp bị hủy, có thể ghi nhận cleanup failure rồi để container removal làm fallback, nhưng kết quả thực phải phản ánh việc dọn per-test không hoàn tất.

## 15. Cache region và Redis namespace

RedisCacheManager mặc định thêm prefix cacheName:

```text
Spring cache "products", key "A"
        -> Redis key "products::A"

Spring cache "prices", key "A"
        -> Redis key "prices::A"
```

Vì vậy hai cache regions không chồng key dù cùng business key. Nếu test gọi `productsCache().clear()`, nó không nên xóa `prices::A`.

**Nhưng nếu hai ứng dụng cùng Redis instance, cùng cache name/key prefix**, region clear vẫn có thể xóa data của nhau. Prefix chỉ có ích khi được phân chia đúng ownership (application/environment/test run).

### 15.1. Khi dùng shared test Redis

Một thiết kế namespace có thể là:

```text
application = inventory
environment = ci
runId = 2026-11-08-build-123

Keys:
inventory:ci:2026-11-08-build-123:products::A
inventory:ci:2026-11-08-build-123:products::B
```

Đây là ví dụ về chiến lược naming, **không phải default key format của lab**. Triển khai cần configure custom RedisCacheConfiguration prefix hoặc CacheKeyPrefix. Không chỉ đổi String trong test rồi hy vọng RedisCacheManager cũng đổi.

Nếu dùng shared Redis, cleanup theo đúng prefix/owned namespace và có TTL retention. Không quét toàn DB bằng wildcard rồi xóa khi không có ownership guarantee.

### 15.2. Redis logical database không phải security isolation hoàn chỉnh

Redis có database indexes trong standalone mode, nhưng đó không phải một authorization/safety boundary đủ mạnh cho multi-tenant production. Redis Cluster chỉ hỗ trợ DB 0 theo mô hình phổ biến. Dùng container/instance riêng hoặc ACL/namespace/network isolation theo yêu cầu, không dựa vào `SELECT 7` như bảo đảm không thể phá dữ liệu ứng dụng khác.

## 16. Caffeine local cache: dọn thế nào?

Caffeine là một provider **in-memory** tốt cho tests về local eviction/expiry. Nếu ứng dụng production dùng Caffeine, integration tests nên xác nhận `CaffeineCacheManager`, không thay bằng Redis.

Gradle dependency:

```groovy
implementation 'com.github.ben-manes.caffeine:caffeine'
```

Configuration ví dụ:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=60s
```

Khi provider là Caffeine:

```java
Cache cache = cacheManager.getCache("products");
assertNotNull(cache);
cache.clear();
```

Lệnh sẽ invalidate local region. Không có Redis key/TTL để quan sát, và không có chia sẻ giữa JVMs. Nếu một test trên Caffeine dùng RedisTemplate để assert Redis key, đó là **sai phạm vi**, không phải provider test hợp lệ.

### 16.1. Caffeine vs Simple provider

Nếu bạn muốn thử **Caffeine eviction by size/TTL**, không dùng ConcurrentMapCacheManager thay thế; Simple provider không có Caffeine policy. Với Caffeine có thể inject/unwrap native cache implementation (API `getNativeCache()`) để quan sát stats/estimated size, nhưng cần version/config phù hợp. Không coi `cache.get(...) != null` là bằng chứng TTL policy đúng nếu chưa test expiration.

### 16.2. Khi nào dùng clock giả?

Để test TTL ngắn tránh `Thread.sleep`, có thể dùng Caffeine `Ticker` giả (nếu cấu hình được) rồi advance fake time, hoặc provider test utilities riêng. Đối với Redis thật, thời gian server là external; thay fake `Clock` của ứng dụng không làm Redis TTL server trôi nhanh. Vì thế lab assert TTL metadata thay vì đợi 60 giây.

## 17. Redis value serialization: kiểm tra đúng thứ cần kiểm

Spring Data Redis `RedisCacheManager` lưu values theo serializer configuration. Mặc định theo các versions thông dụng, `RedisCacheConfiguration.defaultCacheConfig()` dùng `StringRedisSerializer` cho keys và `JdkSerializationRedisSerializer` cho values.

Trong lab:

- Cache value là Java `String`, hỗ trợ serialization.
- `StringRedisTemplate.hasKey(...)`/`getExpire(...)` chỉ cần đọc key metadata.
- **Không** dùng `StringRedisTemplate.opsForValue().get("products::A")` rồi mong luôn nhận `"A#load-1"`: bytes có thể là Java serialized format, không phải UTF-8 plain text.
- `productsCache().get("A").get()` dùng đúng Cache implementation/serializer để deserialize.
- Nếu chuyển sang JSON serializer, test phải điều chỉnh configuration và kiểm tra schema/type metadata.

### 17.1. Trả DTO/custom record

Một record Java 17 không mặc nhiên implement Serializable. Nếu dùng JDK serialization và lưu record không Serializable, Redis cache write có thể fail. Có hai lựa chọn:

1. Khai báo implements Serializable cho DTO phù hợp với Java serialization policy (cần cân nhắc security/compatibility).
2. Cấu hình Redis serializer JSON phù hợp (ví dụ generic Jackson serializer với type safety/allowlist), quản lý schema evolution và test round-trip.

Không trộn default JDK value bytes với StringRedisTemplate đọc UTF-8 rồi kết luận “Redis cache hỏng”.

### 17.2. Schema evolution

Một app v1 cache `ProductV1`, app v2 đổi package/class/serialVersionUID và deserialize cache entries cũ có thể fail. Có chiến lược prefix versioned, TTL và cache invalidation khi deploy. Unit tests với simple map không phát hiện serialization compatibility; real Redis tests có thể giúp.

## 18. @DirtiesContext, Spring TestContext cache và container lifecycle

Spring TestContext caches ApplicationContext để tiết kiệm startup. Nếu một class dùng static `@Container` Redis, Testcontainers JUnit extension thường stop container cuối **test class**, nhưng Spring context có thể còn cached cho class kế tiếp.

Kịch bản:

```text
Test A:
    Spring context created
    LettuceConnectionFactory points to Redis A port
    Testcontainers starts Redis A
    methods pass
    JUnit stops Redis A after class

Test B:
    Spring reuses context cached from A
    connection still targets old Redis A port
    Redis B may be on another mapped port
    tests fail with connection refused/timeouts
```

Lab chỉ có **một test class** để tránh vấn đề cross-class context reuse. Với integration suite lớn:

- Dùng Spring-managed container bean có lifecycle gắn với context, nếu framework version hỗ trợ.
- Hoặc singleton container pattern có lifecycle đủ dài cho các contexts.
- Hoặc isolate contexts per class và chấp nhận startup overhead.
- Không cho rằng `@DirtiesContext` là một lệnh xóa Redis keys.
- Không share static container rồi stop nó trước khi cached beans dùng xong.

### 18.1. @DirtiesContext không thay cache.clear()

`@DirtiesContext` chỉ đánh dấu context “dirty” để Spring tạo lại, chứ không phải Redis FLUSHDB. Nếu Redis sống lâu hơn JVM/context, data có thể vẫn còn. Khi mục tiêu là test isolation, dùng cache API hoặc provider namespace cleanup.

### 18.2. @Transactional không rollback Redis

Spring test-managed database transaction có thể rollback JPA writes vào DB, nhưng Redis cache writes không tự thuộc cùng SQL transaction. Nếu app viết cache sau khi DB chưa commit rồi test rollback, cache có thể giữ dữ liệu không có trong DB.

Không cố giải bằng `@DirtiesContext`; cần cache lifecycle/transaction-aware design, invalidation sau commit hoặc test resource cleanup. Nếu công việc quan trọng yêu cầu DB/cache consistency, viết integration tests với cả DB và Redis thật.

## 19. @CacheEvict và database transaction: stale-cache race

Giả sử service:

1. Cập nhật row price trong DB transaction.
2. Xóa Redis cache ngay trước commit.
3. Một thread khác đọc DB cũ và repopulate cache.
4. Transaction commit new price.
5. Cache giữ old price đến TTL.

Đây là **stale repopulation race**; một unit test tuần tự khó phát hiện.

Mitigations tùy yêu cầu:

- Evict sau khi transaction commit thành công (transaction synchronization/domain event).
- Sử dụng cache manager transaction-aware decorators khi phù hợp, hiểu giới hạn semantics.
- TTL hợp lý và versioned keys/explicit version checks.
- Distributed locks hoặc cache-aside update protocol có đánh giá trade-offs.
- Test concurrency có barriers/latches, **không** dùng sleep tùy tiện.
- Khi cần tính nhất quán mạnh, có thể phải tránh cache ở luồng nhạy cảm.

**Lưu ý:** Redis không mặc nhiên tham gia cùng ACID SQL transaction. `@Transactional` không thể bảo đảm atomic update giữa RDBMS và Redis.

## 20. TTL và vấn đề “cache mất” không hoàn toàn giống evict

Redis TTL trả:

- Số giây không âm: thời gian sống còn lại.
- `-1`: key tồn tại nhưng không có expiration.
- `-2`: key không tồn tại.

Một test eviction cần xác minh key biến mất **sau cache clear/evict**. Một test TTL cần xác minh key được tạo với expiration phù hợp. Nếu bạn chỉ đợi TTL rồi key biến mất, bạn chưa chứng minh `@CacheEvict` đúng.

### 20.1. Không assert TTL tuyệt đối

`assertEquals(60, ttl)` có thể fail khi ngay sau cache PUT, một giây đã qua. Thay bằng range hợp lý.

### 20.2. Cẩn thận trong test song song

Nếu test khác clear cùng prefix khi bạn đang đo TTL, `getExpire` có thể trả `-2` dù code đúng. Đây là lỗi isolation, không phải TTL implementation.

### 20.3. Cache reload sau TTL

Để kiểm tra expiry-driven reload mà không chờ 60 giây, dùng một cache region có TTL rất ngắn trong dedicated test, hoặc thiết lập virtual time khi provider hỗ trợ. Redis real-server expiration dựa vào wall clock của server; tránh test timing overly strict. Nếu contract phải chứng minh precise TTL behavior, viết separate slow/integration test có biên thời gian hợp lý.

## 21. Cache stampede và sync=true

Nếu hai threads cùng miss một key, chúng có thể cùng gọi expensive source trước khi một thread populate cache: **cache stampede**. `@Cacheable(sync=true)` yêu cầu provider thực hiện synchronized load semantics phù hợp nếu hỗ trợ; không phải mọi provider/distributed topology đều bảo đảm một lock toàn cluster.

Không kết luận “một source call cho hai sequential reads” chứng minh single-flight trong 100 concurrent requests.

Concurrency test phải:

- Phát đồng thời nhiều calls cùng key.
- Dùng coordination barriers, không cố sleep đo timing.
- Assert policy thực tế (max backend calls, eventual equality, no data corruption).
- Kiểm tra provider implementation hỗ trợ synchronous caching theo version.
- Xác định desired semantics: local single-flight vs distributed lock.
- Test timeout/failure/lock release.

Bài lab tập trung vào deterministic sequential cache semantics; không claim đã test stampede protection.

## 22. Negative scenarios và provider failures

### 22.1. Backend throws exception

Trong lab `ProductSource.load("FAIL")` luôn ném `IllegalStateException`. Hai calls vẫn đi vào source, counter thành 2; không có Redis key cho FAIL. Điều đó chứng minh exception không trở thành cached success value.

### 22.2. Cache down

Nếu Redis bị stop trong lúc `@Cacheable` gọi provider, ứng dụng mặc định có thể fail operation thay vì tự fallback một cách an toàn. Một custom `CacheErrorHandler` có thể quyết định swallow cache exceptions và chạy source; đó là một **business resilience policy cần được test**.

Không sửa integration provider test bằng cách nuốt mọi Redis error rồi báo rằng cache vẫn hoạt động. Nếu mục tiêu là verify real Redis, network/serialization failure phải hiện ra.

### 22.3. Null caching

`spring.cache.redis.cache-null-values=false` yêu cầu không cache null values. Khi mục tiêu test negative caching/missing product, phải quyết định 404/not-found có được cache hay không, bao lâu, và nguy cơ stale negative result sau khi sản phẩm được tạo.

Đừng mặc định mọi `null` được cache giống nhau trên ConcurrentMap, Caffeine và Redis; policy/config khác nhau.

### 22.4. Data race

Mặc định RedisCacheWriter có thể dùng non-locking operations. Clear/putIfAbsent và multi-command sequences không tự có atomicity cho mọi trường hợp. Một Redis key tồn tại trong test sau một PUT chưa chứng minh distributed consistency dưới concurrent load.

## 23. Tại sao không dùng Redis FLUSHALL trong @BeforeEach?

Một anti-pattern nguy hiểm:

```java
// KHÔNG LÀM trên shared Redis:
redis.getConnectionFactory()
        .getConnection()
        .serverCommands()
        .flushAll();
```

Ngoài rủi ro API/lifecycle của raw connection, `FLUSHALL` **xóa toàn bộ logical DBs trên Redis server**. Nếu test vô tình dùng production Redis connection, hậu quả không còn là flakiness mà là data loss.

Thay bằng:

```java
Cache products = cacheManager.getCache("products");
assertNotNull(products);
products.clear();
```

Trong shared environment, ngay cả region clear cũng có thể phá dữ liệu của test khác nếu chung prefix. Mạnh hơn là **test-only isolated container** hoặc prefix theo run ID; cleanup chỉ những key test sở hữu.

### 23.1. Redis SCAN vs KEYS

Spring Data Redis cache writer có thể dùng `KEYS` để tìm cache prefix khi `clear()`. Trên keyspace lớn, `KEYS` có thể tạo latency/blocking đáng kể. Một cấu hình custom có thể dùng `BatchStrategies.scan(...)` với Lettuce cho Redis, nhưng cũng cần đánh giá cluster/driver compatibility. Với lab private 1–3 keys, default clear đủ đơn giản.

Không chọn `SCAN` rồi tuyên bố scan + delete là một atomic transaction; concurrent inserts vẫn có thể tạo race. Ở production shared cache, namespace ownership và cache invalidation strategy quan trọng hơn việc chỉ đổi lệnh.

## 24. Chạy test trên nhiều cache providers

Nếu app hỗ trợ cả Redis và Caffeine, tạo test matrix:

```text
Suite A: spring.cache.type=caffeine
         -> assert CaffeineCacheManager
         -> local cache behavior
         -> memory eviction/expiry policy

Suite B: spring.cache.type=redis
         -> assert RedisCacheManager
         -> Redis Testcontainers
         -> key/TTL/serialization/evict assertions

Suite C: spring.cache.type=none
         -> verify business behavior when cache disabled
         -> expect source invocation every time
```

Đừng chạy cùng assertions “two reads source.calls() == 1” trong `type=none` rồi gọi đó là lỗi sản phẩm: đó chính là semantics của NoOpCacheManager. Điều quan trọng là test expectations **khớp provider contract**.

### 24.1. Caffeine tests cần native statistics nếu là mục tiêu

Nếu muốn hit/miss metrics, Caffeine có `recordStats()` và stats APIs. RedisCacheManager có thể expose statistics tùy version/config nhưng có semantics khác. `CacheManager` abstraction không tự bảo đảm cùng thống kê/eviction policy trên mọi providers.

### 24.2. Different regions and different keys

Test một region `products` không tự chứng minh `prices`/`sessions`/`users` cache đúng. Mỗi region có TTL/serializer/key policy riêng, nên chọn representative cases theo business criticality.

## 25. CI/CD: test isolation ở những mức nào?

### 25.1. Redis-per-test-class

Ví dụ bài lab: một static GenericContainer sống một class. Ưu điểm rõ state ownership, không chạm Redis shared; chi phí là startup Docker.

### 25.2. Redis-per-suite

Có thể chia Redis container cho nhiều test classes để nhanh hơn, nhưng Spring context lifecycle, key prefixes, parallel execution và cleanup phải được thiết kế. Nếu context cached trỏ tới container đã stop, tests sau fail.

### 25.3. Redis-per-CI-job

Một Redis service container cho CI job; test classes dùng prefix mang run ID và clear đúng prefix/region. Khi job kết thúc, container bị destroy. Tránh sharing với CI job khác.

### 25.4. Shared staging Redis

Chỉ dùng khi có môi trường/credentials test-specific, namespace ownership và ACL. Không dùng admin flush hoặc wildcard delete. Tốt hơn là namespace/instance riêng.

### 25.5. Parallel JUnit tests

Trong một class dùng cùng `productsCache().clear()` ở @BeforeEach/@AfterEach, nếu methods chạy parallel, teardown của test A có thể xóa key của B. Source counter bean cũng bị reset cạnh tranh. **Lab mặc định phải chạy tuần tự.** Nếu repository bật parallel globally, dùng JUnit `@Execution(ExecutionMode.SAME_THREAD)` cho class tương ứng (với JUnit imports) hoặc tạo separate provider/namespace per method.

Không giải quyết race bằng cách tăng sleep/timeout; isolation cần giải quyết ở ownership level.

## 26. Bẫy key, serialization và prefix

### 26.1. Key generator không giống nhau

`@Cacheable(key="#p0")` và `@CacheEvict(key="#p0")` phải nhận cùng argument/key representation. Nếu method evict dùng SpEL sai, key vẫn còn, test sẽ trả stale cache.

Một custom KeyGenerator cho composite keys như `(tenantId, sku)` cần test hai tenants cùng SKU không xung đột. Không dùng chỉ SKU làm cache key trong multi-tenant application nếu dữ liệu khác theo tenant.

### 26.2. Không nên disable key prefix tùy tiện

Spring Data Redis mặc định prefix theo cacheName để tránh collisions. `disableKeyPrefix()` có thể khiến các regions dùng cùng key ghi đè value và clear của region này xóa key của region khác. Nếu cần custom prefix, đặt scheme ổn định theo app/env/version và verify raw Redis keys trong test.

### 26.3. Value serializer thay đổi

Nếu dùng JDK serialization, class phải tương thích. Nếu dùng JSON serializer, phải đảm bảo trusted type mapping/allowlists, schema evolution và không deserialize untrusted arbitrary types theo cách unsafe. Một test direct `StringRedisTemplate` GET không phù hợp để assert plain-text value khi cache dùng binary serializer.

### 26.4. Null values

Config null caching cần rõ. Với cache of missing products, một 404 cached quá lâu có thể giữ kết quả sai sau khi product xuất hiện. Test negative caching phải dùng business contract cụ thể, không chỉ “null returned”.

## 27. Database + cache invalidation patterns

| Pattern | Dữ liệu nguồn | Cache update | Rủi ro |
| --- | --- | --- | --- |
| Cache-aside read | DB load khi miss | Put result | Stale khi DB đổi |
| Write-through | Update source + cache | Put/new value | Cần consistency coordination |
| Write-around | Update DB | Evict | Window stale repopulation |
| Read-through | Provider loader | Load/cache | Loader exception/transaction semantics |
| TTL-only | DB writes độc lập | Expire theo thời gian | Dữ liệu cũ cho đến hết TTL |
| Event invalidation | DB update + event | Listener evicts | Delivery delay/duplicate/out-of-order events |

Bài lab là **cache-aside read + explicit eviction** bằng Spring Cache abstraction, không chứng minh một distributed transaction giữa SQL và Redis. Khi test với DB:

1. Seed DB và cache sạch.
2. Đọc lần đầu, xác nhận provider key.
3. Update row trong DB transaction, commit theo contract.
4. Trigger eviction/refresh.
5. Đọc lại và assert new value.
6. Chạy concurrent scenario để bắt stale repopulation.
7. Cleanup cả DB và Redis, không dựa mỗi transaction rollback.

## 28. Bài tập thực hành

### Bài 1 — Bỏ @EnableCaching

Tạm xóa `@EnableCaching` trong main app. `cacheHitSkipsCallingSourceAgain` phải fail vì source.calls() tăng lên 2. Khôi phục. Đây là cách chứng minh test thực sự phát hiện proxy không hoạt động.

### Bài 2 — Đổi cache provider thành none

Trong sandbox, đổi `spring.cache.type=redis` sang `none`. Test provider assertion và Redis key presence phải fail; test business behavior vẫn có thể chạy. Phân biệt cái nào là failure đúng mục tiêu.

### Bài 3 — Kiểm tra Caffeine riêng

Thêm Caffeine dependency và cấu hình `spring.cache.type=caffeine` trong một test suite khác. Assert CaffeineCacheManager/local cache behavior; không dùng Redis key assertion để đo local cache.

### Bài 4 — Xóa @BeforeEach clear

Tạm bỏ clear trước test, giữ test keys trùng nhau rồi chạy suite nhiều lần trên shared Redis sandbox. Quan sát stale value/counter mismatch. Khôi phục per-test cleanup và tách provider/namespace.

### Bài 5 — Xóa @AfterEach clear

Bỏ afterEach cleanup trong nhánh thử, kiểm tra keys còn sau test method. Giải thích vì sao beforeEach vẫn quan trọng khi run trước chết, và vì sao teardown thất bại không thể được coi như success.

### Bài 6 — Key-level eviction

Chạy `evictOneKeyLeavesOtherProductCached`. Đổi SpEL key của `invalidate` sang một key khác, test phải fail. Khôi phục.

### Bài 7 — All entries và sentinel

Chạy `evictAllClearsProductsButKeepsUnrelatedKey`. Nếu thay `@CacheEvict(allEntries=true)` bằng raw `FLUSHDB` (chỉ trong private Redis sandbox), sentinel sẽ mất. Giải thích nguy cơ với shared Redis. Không áp dụng destructive lệnh trong môi trường chung.

### Bài 8 — TTL kiểm tra đúng phạm vi

Chạy `redisEntryHasConfiguredPositiveTtl`, đổi config TTL sang 2s trong riêng một test setup và điều chỉnh expected range. Tránh `Thread.sleep(2000)` làm oracle chính.

### Bài 9 — Serialization

Đổi cached return type thành custom record không Serializable; quan sát Redis serializer error. Sau đó thêm serializer phù hợp/test round-trip. Không mặc định `StringRedisTemplate.opsForValue().get` sẽ decode JDK value bytes.

### Bài 10 — @DirtiesContext không xóa Redis

Tạo hai Spring contexts cùng Redis private trong một suite có kiểm soát. Context A cache key; đóng context A; context B trỏ cùng Redis và kiểm tra key vẫn tồn tại. Không nhầm recreate context với Redis cleanup.

### Bài 11 — Multi-instance caching

Dùng hai Spring contexts hoặc hai application instances trỏ cùng Redis Testcontainers và chung key namespace. Instance A put, B hit. Sau A evict, B miss. Đây mới là bằng chứng distributed shared cache, không chỉ one-JVM test.

### Bài 12 — Parallel race

Bật parallel JUnit tests dùng shared region và source counter; quan sát afterEach của một method xóa key của method khác. Sửa bằng unique cache namespace/provider per method hoặc disable parallel cho class.

### Bài 13 — Failure/circuit-breaker

Dừng Redis trong một test sandbox riêng có cleanup an toàn. Quan sát cache operation failure. Thiết kế optional `CacheErrorHandler` fallback theo business policy và assert provider failure được báo rõ, không âm thầm bỏ qua.

### Bài 14 — Transaction boundary

Kết hợp PostgreSQL Testcontainers, Redis và `@Transactional` update service. Mô phỏng stale repopulation giữa DB write và Redis eviction, dùng latches/barriers. Kiểm tra after-commit invalidation strategy.

### Bài 15 — Key prefix theo tenant

Cùng SKU "A" ở tenant X/Y phải tạo hai distinct keys và hai distinct cached values, không rò dữ liệu giữa tenants. Thử cache key composite và custom prefix; test raw Redis keys.

### Bài 16 — Provider upgrade

Đổi Redis image digest/version, Spring Data Redis/Jedis/Lettuce version ở một branch có review. Chạy full integration suite, theo dõi TTL/serialization/key format changes. Không coi một tag `latest` là môi trường kiểm thử tái hiện chắc chắn.

## 29. Checklist QA trước khi merge

- [ ] Biết test đang dùng CacheManager nào; không chỉ assert bean khác null.
- [ ] Đã bật @EnableCaching; không bypass proxy/self-invocation.
- [ ] Với cache provider Redis, có real Redis server/container, không chỉ Mockito fake.
- [ ] `spring.cache.type=redis` được đặt trong Redis integration test.
- [ ] @ServiceConnection(name="redis")/connection properties trỏ đúng container/host port.
- [ ] Spring CacheManager là RedisCacheManager, không phải Simple/Caffeine/NoOp.
- [ ] Test kiểm tra actual Redis key bằng provider client.
- [ ] Test có cache hit/miss và source call count, không chỉ so 2 Strings.
- [ ] Cache TTL được xác minh ở Redis, không bằng sleep cố định.
- [ ] Cache value serializer được hiểu; không đọc JDK value bytes như UTF-8.
- [ ] @BeforeEach clear đúng region và reset fixture/source state.
- [ ] @AfterEach cleanup đúng region/key dù test throw bình thường.
- [ ] Không dựa vào test method order hoặc shared cached fixture.
- [ ] @CacheEvict(key=...) chỉ xóa intended key.
- [ ] @CacheEvict(allEntries=true) không xóa unrelated Redis key.
- [ ] Có direct Cache.clear test chứng minh key thực biến mất.
- [ ] Negative exception không được cache như success value.
- [ ] Không dùng FLUSHALL/FLUSHDB trên shared cache.
- [ ] Với shared provider, namespace/prefix theo run/tenant/app ownership rõ ràng.
- [ ] Cache clear trên Redis lớn có thể dùng KEYS/SCAN, không gọi vô hạn ở hot path.
- [ ] Không coi @DirtiesContext là Redis cleanup.
- [ ] Không coi @Transactional database rollback là Redis rollback.
- [ ] Spring TestContext cache và Testcontainers lifecycle được phối hợp.
- [ ] Test classes chạy song song không xóa key/source state của nhau.
- [ ] Caffeine/local vs Redis/distributed tests có assertions theo đúng provider.
- [ ] Security: test không có production credentials, không trỏ nhầm shared/production Redis.
- [ ] Không tuyên bố multi-instance/HA/TLS/cluster behavior chỉ từ single RedisContainer.
- [ ] Gradle/JUnit executed/passed/failed/skipped được ghi từ report thực khi chạy.
- [ ] Image/dependency versions được quản lý, không để latest tag đổi test environment bất ngờ.

## 30. Quy tắc quyết định

```text
Cần kiểm thử cache?
       |
       +-- Chỉ business logic/cache disabled?
       |      -> Unit/mock hoặc spring.cache.type=none.
       |
       +-- Cache annotation/proxy semantics?
       |      -> Spring context + CacheManager thực.
       |
       +-- Local Caffeine expiry/size?
       |      -> CaffeineCacheManager + native policy tests.
       |
       +-- Redis provider thật?
       |      -> Redis Testcontainers
       |         + spring.cache.type=redis
       |         + RedisCacheManager type assertion
       |         + Redis raw key/TTL verification.
       |
       +-- Test isolation?
       |      -> BeforeEach/AfterEach scoped cache clear
       |         + unique key/namespace/provider
       |         + container cleanup per test group.
       |
       +-- Multi-instance consistency?
       |      -> Two app contexts/instances sharing Redis
       |         + concurrent/invalidation tests.
       |
       +-- Managed Redis TLS/ACL/cluster/HA?
              -> Provider-specific staging/deployment tests.
```

**Kết luận:** Xóa cache đúng giữa các tests đòi hỏi hiểu **phạm vi state** của CacheManager/provider, không phải chỉ reset một Java mock hoặc Spring context. Kiểm chứng cache provider thật phải dùng nhiều bằng chứng độc lập: Spring RedisCacheManager, key/TTL trong Redis, cache hit/miss qua source call count và eviction phản ánh xuống storage. Trong test tích hợp an toàn, ưu tiên **isolated Redis Testcontainers, key ownership rõ, @BeforeEach/@AfterEach cleanup scoped**, và tuyệt đối không dùng `FLUSHALL` để làm sạch một shared Redis.

## 31. Tài liệu chính thức

- Spring Boot 3.3 — Caching và các cache provider được hỗ trợ: https://docs.spring.io/spring-boot/3.3/reference/io/caching.html
- Spring Boot 3.3 — Testcontainers, Redis GenericContainer và @ServiceConnection(name="redis"): https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Framework — Cache annotations (@Cacheable, @CachePut, @CacheEvict) và proxy caveats: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache abstraction và CacheManager/Cache APIs: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Data Redis — Redis Cache/TTL/prefix/serializer: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
- Spring Data Redis — RedisTemplate/StringRedisTemplate: https://docs.spring.io/spring-data/redis/reference/redis/template.html
- Spring Data Redis — RedisCacheManager API: https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/cache/RedisCacheManager.html
- Testcontainers Java — JUnit Jupiter extension: https://java.testcontainers.org/test_framework_integration/junit_5/
- Testcontainers Java — GenericContainer and network ports: https://java.testcontainers.org/features/creating_container/
- Redis — EXPIRE/TTL commands: https://redis.io/docs/latest/commands/ttl/
- Redis — FLUSHDB (destructive): https://redis.io/docs/latest/commands/flushdb/
- Redis — FLUSHALL (destructive): https://redis.io/docs/latest/commands/flushall/
- Spring Framework — Spring TestContext cache và @DirtiesContext: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- JUnit Jupiter — Lifecycle/parallel execution: https://docs.junit.org/current/user-guide/
