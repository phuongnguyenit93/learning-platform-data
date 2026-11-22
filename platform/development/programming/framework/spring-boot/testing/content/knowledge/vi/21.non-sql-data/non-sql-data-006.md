# Khởi tạo dịch vụ thật bằng container và cấu hình kết nối động

## 1. Tổng quan

Trong Spring Boot Testing, việc mock một MongoDB repository, Redis client hoặc message producer giúp unit test nhanh, nhưng **không chứng minh** ứng dụng thật kết nối đúng host/port, serialize đúng dữ liệu, thực thi được MongoDB query, xử lý TTL Redis hoặc tương thích với server version. Dùng một Mongo/Redis cài thủ công ở `localhost` cũng khó tái hiện trong CI và có thể vô tình truy cập dữ liệu không thuộc phạm vi test.

**Testcontainers** khởi tạo các dịch vụ thật trong Docker containers dành cho test. Các dịch vụ được cô lập tương đối với môi trường ngoài, có vòng đời do test quản lý và thường expose **cổng host động**. Spring Boot **3.3.5** hỗ trợ hai cơ chế tích hợp quan trọng:

- **`@ServiceConnection`** từ `spring-boot-testcontainers`: tạo `ConnectionDetails` tương ứng với container rồi để Spring Boot auto-configuration dùng endpoint của dịch vụ.
- **`@DynamicPropertySource`** của Spring TestContext: đăng ký host, mapped port, URI hoặc credentials như các dynamic properties, phù hợp khi cần cấu hình key riêng hoặc backend chưa có service-connection factory.

Đề bài thuộc nhóm **Dữ liệu ngoài SQL**, vì vậy ví dụ thực hành dùng **MongoDB 7.0 và Redis 7.2** thay vì H2. Chúng ta sẽ xây một Spring Boot Java 17+ project, nạp MongoDB bằng `MongoDBContainer + @ServiceConnection`, nạp Redis bằng `GenericContainer + @DynamicPropertySource`, test cả Spring Data MongoDB, `StringRedisTemplate` và một cache-aside service sử dụng hai backend thật.

### Kết quả cần đạt

1. Biết sự khác nhau giữa unit test mock và integration test với container thật.
2. Cài dependencies Testcontainers, Spring Boot testcontainers, JUnit 5 và các Spring Data starters.
3. Hiểu `@Testcontainers`, `@Container`, `MongoDBContainer`, `GenericContainer` và lifecycle static/instance.
4. Biết lấy `getHost()`, `getMappedPort(6379)` sau startup, không hardcode host port.
5. Cấu hình MongoDB thông qua `@ServiceConnection` tạo `MongoConnectionDetails`.
6. Đăng ký Redis `spring.data.redis.host` / `spring.data.redis.port` bằng `DynamicPropertyRegistry`.
7. Kiểm tra thao tác thật trên MongoDB repository, Redis data/TTL và service phối hợp.
8. Dọn fixture đúng cách, phân biệt rollback SQL với dữ liệu NoSQL thực sự được ghi.
9. Xử lý Spring context cache, Docker networking, CI và lỗi startup.
10. Hiểu phương án thay thế Redis `@ServiceConnection(name="redis")`, container beans và những giới hạn khi test cluster/production.

**Phiên bản:** Spring Boot 3.3.5, Java 17+, Testcontainers version được Spring Boot BOM quản lý. Tài liệu Spring Boot 3.3/JUnit/Testcontainers là cơ sở API, không giả định import của Boot 4 giống hoàn toàn.

## 2. Vì sao nên thử trên dịch vụ thật?

```text
JUnit Jupiter + @SpringBootTest
  |
  +-- InventoryRepository
  |       |
  |       +-- MongoDB driver
  |               |
  |               +-- MongoDB 7.0 container (URI động)
  |
  +-- InventoryLookupService
          |
          +-- StringRedisTemplate
                  |
                  +-- Lettuce Redis client
                          |
                          +-- Redis 7.2 container (host + port động)
```

Một mock có thể trả `Optional.of(item)` ngay cả khi query MongoDB production bị sai tên field hoặc không đúng database. Một fake Redis có thể bỏ qua TTL hoặc trả giá trị ngay dù application cấu hình serializer không tương thích. Container thật cho phép test code đi qua client driver → network → server → response.

| Cách test | Backend thật? | Phát hiện được gì? | Giới hạn |
| --- | --- | --- | --- |
| Mockito/mock | Không | Branches, retries, mapping logic quanh dependency | Không xác nhận driver, protocol, DB constraints |
| Fake/in-memory replacement | Một phần | Logic với contract đơn giản | Semantics có thể khác server thật |
| Testcontainers | Có | Kết nối, codec, commands, persistence, TTL, queries | Cần Docker và tài nguyên |
| Shared staging service | Có | Hệ thống chung với nhiều collaborators | Data race, cleanup, quyền, khó lặp lại |
| Production | Có | Quan sát hệ thống đang vận hành | Không phải nơi chạy test ghi/xóa dữ liệu tùy ý |

**Container thật không đồng nghĩa môi trường production hoàn hảo.** Single-node MongoDB không mô phỏng đầy đủ sharded cluster; Redis đơn không thể thay Redis Sentinel/Cluster, TLS/ACL hoặc hạ tầng failover. Phần lớn bài test CRUD/TTL vẫn có giá trị, còn resilience/availability cần hệ thống thử nghiệm riêng.

## 3. Testcontainers lifecycle và networking

Ví dụ khai báo Redis container:

```java
@Testcontainers
class ExampleTest {
    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.2-alpine"))
                    .withExposedPorts(6379);
}
```

Snippet này cần imports `Testcontainers`, `Container`, `GenericContainer` và `DockerImageName`. Khi test có JUnit extension `@Testcontainers`:

- Field `static @Container` thường được start một lần trước các test methods trong class và stop sau class.
- Field instance `@Container` thường có vòng đời theo mỗi test method.
- `withExposedPorts(6379)` yêu cầu Docker publish container port **6379** lên **host port được Docker/Testcontainers cấp động**.
- `redis.getHost()` trả host mà test JVM nên dùng để kết nối container.
- `redis.getMappedPort(6379)` trả port host tương ứng container port 6379.
- `redis.isRunning()` là tín hiệu Docker container đang chạy; **chưa đủ** xác nhận app client đã connect.

**Không gọi `getMappedPort` quá sớm:** khi container chưa start, Docker chưa cấp mapped port và accessor có thể báo lỗi. Do đó cấu hình Spring thường đăng ký một `Supplier` rồi resolve khi Spring cần property, như `() -> redis.getMappedPort(6379)`.

```text
Redis internal: redis-container:6379
Host developer: localhost:49153         (chỉ là ví dụ)
Host CI:       192.168.65.2:32778       (chỉ là ví dụ)

App client trên host phải dùng getHost + getMappedPort,
không mặc định localhost:6379.
```

Không nhầm host-to-container với container-to-container networking. Nếu container A gọi container B trên cùng Docker network, thường dùng network alias + internal port; mapped port là cho test JVM/host kết nối tới container. Trên remote Docker hoặc CI-in-Docker, `getHost()` có thể khác `localhost`.

## 4. ServiceConnection và ConnectionDetails

Trong Boot 3.3, có thể khai báo:

```java
@Container
@ServiceConnection
static final MongoDBContainer MONGO =
        new MongoDBContainer(
                DockerImageName.parse("mongo:7.0"));
```

Spring Boot nhận diện type `MongoDBContainer` và tạo `MongoConnectionDetails` phù hợp để auto-configure MongoDB client. `ConnectionDetails` có ưu tiên trước các connection properties thông thường của chính dịch vụ đó.

```text
MongoDBContainer
      |
      | @ServiceConnection
      v
MongoConnectionDetails
      |
      v
MongoAutoConfiguration / MongoClient
      |
      v
MongoRepository / MongoTemplate
```

Điều kiện quan trọng:

- Phải thêm `testImplementation 'org.springframework.boot:spring-boot-testcontainers'`.
- Phải có dependency `org.testcontainers:mongodb` để compile `MongoDBContainer`.
- Phải có Spring Data Mongo starter để Boot tạo Mongo client/repository.
- `@ServiceConnection` **không tự thay thế** quản lý vòng đời Docker; field trong demo có `@Container`, hoặc chọn container beans do Spring Boot quản lý.
- Không khai báo thêm `spring.data.mongodb.uri` cùng container này chỉ để “cho chắc”; connection details đã được Boot chọn và precedence có thể khiến property bạn viết bị bỏ qua.

Danh sách service-connection factories thay đổi theo phiên bản Boot. Spring Boot 3.3 nhận diện các container như MongoDB, Redis theo image name, Neo4j, Cassandra, Elasticsearch, RabbitMQ, Kafka và các dịch vụ khác theo bảng phiên bản. Nếu một custom Docker image không được nhận diện, dùng `name` trên `@ServiceConnection` hoặc `@DynamicPropertySource` theo khả năng hỗ trợ thực.

## 5. @DynamicPropertySource trong Spring Test

Khi cần truyền Redis host/port, viết static method:

```java
@DynamicPropertySource
static void redisProps(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", REDIS::getHost);
    registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
}
```

Spring TestContext chỉ cần `DynamicPropertyRegistry` và các `Supplier<?>`. Nó **không start Redis**; lifecycle phải được quản lý riêng bởi `@Container` hoặc container bean.

Các quy tắc:

1. Method `@DynamicPropertySource` phải **static** và có đúng một tham số `DynamicPropertyRegistry`.
2. `registry.add` nhận supplier, giá trị động được resolve khi property được sử dụng.
3. Dynamic properties có precedence cao hơn test properties, system properties và nhiều property sources thông thường.
4. Dùng keys của Boot 3.3: `spring.data.redis.host` và `spring.data.redis.port`.
5. `getMappedPort(6379)` chỉ có ý nghĩa khi container đã start.
6. Một cấu hình chỉ tự đăng ký host/port chưa chứng minh client đã dùng đúng; test phải gửi lệnh Redis thật.

**Phân biệt:** `@ServiceConnection` đưa details vào auto-configuration, `@DynamicPropertySource` đưa key/value vào Spring Environment. Trong bộ ví dụ, hai cơ chế áp dụng cho **hai backend khác nhau**; không có xung đột giữa Mongo và Redis.

### Ví dụ MongoDB URI theo cách thay thế

Nếu không dùng `@ServiceConnection` cho Mongo, có thể đăng ký:

```java
@DynamicPropertySource
static void mongoProps(DynamicPropertyRegistry registry) {
    registry.add("spring.data.mongodb.uri",
            MONGO::getReplicaSetUrl);
}
```

`MongoDBContainer.getReplicaSetUrl()` tạo URI phù hợp với replica-set container. Đây là **phương án thay thế**, không dùng đồng thời với Mongo `@ServiceConnection` trong project chính. Không tự suy connection string của MongoDB từ `localhost` và một port tự đoán nếu container đã có accessor chuyên biệt.

## 6. Project mẫu Java 17+ Spring Boot 3.3.5

Dự án có hai external services và một application đơn giản:

```text
nosql-containers-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/nosql/
│   ├── NosqlContainersApplication.java
│   ├── InventoryItem.java
│   ├── InventoryRepository.java
│   └── InventoryLookupService.java
└── src/test/java/com/example/nosql/
    └── RealBackendsIntegrationTest.java
```

Không dùng Mongo/Redis credentials của môi trường công ty hoặc một network database. Test sẽ tự khởi tạo MongoDB và Redis containers, không phụ thuộc server đã được ai đó bật sẵn ở port mặc định.

### 6.1. settings.gradle

```groovy
rootProject.name = 'nosql-containers-demo'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Lưu ý dependencies:**

- `spring-boot-starter-data-mongodb`: Mongo driver, Spring Data MongoDB và repositories.
- `spring-boot-starter-data-redis`: Spring Data Redis, Lettuce client và `StringRedisTemplate`.
- `spring-boot-starter-test`: JUnit Jupiter, Spring TestContext và test assertions.
- `spring-boot-testcontainers`: `@ServiceConnection` + connection details factories.
- `testcontainers:junit-jupiter`: JUnit integration của Testcontainers.
- `testcontainers:mongodb`: specialized `MongoDBContainer`, core `GenericContainer` được kéo vào.
- `junit-platform-launcher`: hỗ trợ JUnit Platform runtime trong Gradle.

Không cần một Redis-specific Testcontainers module cho `GenericContainer<?>`. Spring Boot quản lý versions cho nhiều dependency qua BOM; đừng ép Testcontainers/Jackson/Mongo client versions khác không tương thích chỉ để chạy demo.

**Điều kiện bên ngoài Java:** Docker daemon hoạt động, test runner có quyền Docker, host có đủ RAM/CPU, images có thể pull. Docker privilege phải được quản lý trong CI; không đưa secret hay host Docker socket vào untrusted image tùy tiện.

## 7. Spring Boot application root

`src/main/java/com/example/nosql/NosqlContainersApplication.java`:

```java
package com.example.nosql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NosqlContainersApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                NosqlContainersApplication.class, args);
    }
}
```

Class root đặt ở `com.example.nosql`, package cha của repository, service và test. `@SpringBootTest` tìm primary `@SpringBootConfiguration` qua package hierarchy và nạp application context thực.

Nếu chạy `bootRun` ngoài test mà chưa cấu hình external backend, app có thể dùng các default connection properties; project này tập trung vào **test** thay vì dựng production deployment. Chỉ trong test class, hai container sẽ cung cấp endpoints.

## 8. MongoDB document mapping

`src/main/java/com/example/nosql/InventoryItem.java`:

```java
package com.example.nosql;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventory_items")
public class InventoryItem {

    @Id
    private String id;

    private String sku;
    private String title;
    private long available;

    public InventoryItem() {
        // Constructor for Spring Data MongoDB.
    }

    public InventoryItem(
            String sku, String title, long available) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (available < 0) {
            throw new IllegalArgumentException(
                    "available cannot be negative");
        }
        this.sku = sku;
        this.title = title;
        this.available = available;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public long getAvailable() {
        return available;
    }

    public void setTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        this.title = title;
    }
}
```

`@Document` định nghĩa MongoDB collection, `@Id` đánh dấu identifier có thể được driver/Spring Data gán khi lưu. Đây **không phải** JPA `@Entity`; MongoDB không có persistence context dirty checking như Hibernate. Để update title, cần gọi `repository.save(...)` hoặc MongoTemplate update API.

Schema MongoDB linh hoạt nhưng không đồng nghĩa data quality tự an toàn. Trong production, cần validation/index policy riêng. Method `findBySku` không tự tạo unique index cho SKU.

## 9. MongoRepository với derived queries

`src/main/java/com/example/nosql/InventoryRepository.java`:

```java
package com.example.nosql;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface InventoryRepository
        extends MongoRepository<InventoryItem, String> {

    Optional<InventoryItem> findBySku(String sku);

    long countByAvailableGreaterThan(long quantity);
}
```

`findBySku` dùng Mongo query trên field `sku`. `countByAvailableGreaterThan` kiểm tra dữ liệu có số lượng tồn lớn hơn một ngưỡng; cả hai đi qua Mongo driver tới container thật.

Đừng viết test vừa mock repository vừa kết luận query MongoDB đúng: mocked response chỉ chứng minh **điều Mockito được bảo trả**, không chạy Mongo query. Test container sẽ tạo fixtures, gọi repository method và assert giá trị thực.

## 10. Redis cache-aside service

`src/main/java/com/example/nosql/InventoryLookupService.java`:

```java
package com.example.nosql;

import java.time.Duration;
import java.util.NoSuchElementException;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookupService {

    private final InventoryRepository repository;
    private final StringRedisTemplate redis;

    public InventoryLookupService(
            InventoryRepository repository,
            StringRedisTemplate redis) {
        this.repository = repository;
        this.redis = redis;
    }

    public String titleBySku(String sku) {
        String key = "inventory:title:" + sku;

        String fromCache = redis.opsForValue().get(key);
        if (fromCache != null) {
            return fromCache;
        }

        String title = repository.findBySku(sku)
                .map(InventoryItem::getTitle)
                .orElseThrow(() ->
                        new NoSuchElementException(
                                "Unknown SKU: " + sku));

        redis.opsForValue().set(
                key, title, Duration.ofMinutes(2));
        return title;
    }
}
```

Code minh họa một **cache-aside** read path: Redis lookup → nếu miss thì query Mongo → ghi cache có TTL hai phút. Trong test, service sẽ sử dụng hai kết nối thật cùng lúc.

**Cảnh báo về production:** cache-aside không tự giải quyết stale cache sau cập nhật Mongo, cache stampede, Redis outage, distributed transaction hoặc authorization. Cần invalidation, retries/fallback và consistency policy theo nghiệp vụ. Không lưu dữ liệu nhạy cảm vào Redis key string chỉ vì tiện debug.

## 11. Bộ test integration hoàn chỉnh

`src/test/java/com/example/nosql/RealBackendsIntegrationTest.java`:

```java
package com.example.nosql;

import java.time.Duration;
import java.util.NoSuchElementException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.core.env.Environment;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest
class RealBackendsIntegrationTest {

    private static final int REDIS_PORT = 6379;

    private static final String VALUE_KEY = "it:redis:value";
    private static final String COUNTER_KEY = "it:redis:count";
    private static final String TTL_KEY = "it:redis:ttl";
    private static final String CACHE_KEY =
            "inventory:title:SKU-CACHE";
    private static final String UNKNOWN_CACHE_KEY =
            "inventory:title:SKU-UNKNOWN";

    @Container
    @ServiceConnection
    static final MongoDBContainer MONGO =
            new MongoDBContainer(
                    DockerImageName.parse("mongo:7.0"));

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.2-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
                "spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @Autowired
    InventoryRepository repository;

    @Autowired
    InventoryLookupService service;

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    Environment environment;

    @BeforeEach
    void prepareData() {
        repository.deleteAll();
        redis.delete(VALUE_KEY);
        redis.delete(COUNTER_KEY);
        redis.delete(TTL_KEY);
        redis.delete(CACHE_KEY);
        redis.delete(UNKNOWN_CACHE_KEY);
    }

    @AfterEach
    void cleanData() {
        repository.deleteAll();
        redis.delete(VALUE_KEY);
        redis.delete(COUNTER_KEY);
        redis.delete(TTL_KEY);
        redis.delete(CACHE_KEY);
        redis.delete(UNKNOWN_CACHE_KEY);
    }

    @Test
    void containersAreRunning() {
        assertTrue(MONGO.isRunning());
        assertTrue(REDIS.isRunning());
        assertTrue(REDIS.getMappedPort(REDIS_PORT) > 0);
    }

    @Test
    void environmentReceivesDynamicRedisProperties() {
        assertEquals(
                REDIS.getHost(),
                environment.getProperty("spring.data.redis.host"));
        assertEquals(
                Integer.toString(REDIS.getMappedPort(REDIS_PORT)),
                environment.getProperty("spring.data.redis.port"));
    }

    @Test
    void mongoSavesAndFindsDocumentBySku() {
        InventoryItem saved = repository.save(
                new InventoryItem("SKU-101", "Mongo data", 9));

        assertNotNull(saved.getId());

        InventoryItem loaded = repository
                .findBySku("SKU-101").orElseThrow();

        assertEquals(saved.getId(), loaded.getId());
        assertEquals("Mongo data", loaded.getTitle());
        assertEquals(9, loaded.getAvailable());
    }

    @Test
    void mongoCanUpdateDocument() {
        InventoryItem saved = repository.save(
                new InventoryItem("SKU-102", "Before", 3));

        saved.setTitle("After");
        repository.save(saved);

        InventoryItem updated = repository
                .findById(saved.getId()).orElseThrow();

        assertEquals("After", updated.getTitle());
    }

    @Test
    void mongoCanDeleteDocument() {
        InventoryItem saved = repository.save(
                new InventoryItem("SKU-103", "Delete", 1));

        repository.deleteById(saved.getId());

        assertTrue(repository
                .findById(saved.getId()).isEmpty());
    }

    @Test
    void mongoDerivedQueryCountsMatchingDocuments() {
        repository.save(new InventoryItem(
                "SKU-104", "Small", 2));
        repository.save(new InventoryItem(
                "SKU-105", "Large", 8));
        repository.save(new InventoryItem(
                "SKU-106", "Empty", 0));

        assertEquals(
                1L,
                repository.countByAvailableGreaterThan(4));
    }

    @Test
    void mongoFindReturnsEmptyForUnknownSku() {
        assertTrue(repository
                .findBySku("SKU-DOES-NOT-EXIST").isEmpty());
    }

    @Test
    void redisCanStoreAndReadString() {
        redis.opsForValue().set(VALUE_KEY, "live-redis");

        assertEquals(
                "live-redis",
                redis.opsForValue().get(VALUE_KEY));
    }

    @Test
    void redisIncrementIsAtomicAtServer() {
        assertEquals(
                1L,
                redis.opsForValue().increment(COUNTER_KEY));

        assertEquals(
                2L,
                redis.opsForValue().increment(COUNTER_KEY));
    }

    @Test
    void redisCanAssignKeyTtl() {
        redis.opsForValue().set(
                TTL_KEY, "short-lived", Duration.ofMinutes(5));

        Long seconds = redis.getExpire(
                TTL_KEY, TimeUnit.SECONDS);

        assertNotNull(seconds);
        assertTrue(seconds > 0);
        assertTrue(seconds <= 300);
    }

    @Test
    void redisCanDeleteKey() {
        redis.opsForValue().set(VALUE_KEY, "remove-me");

        assertEquals(Boolean.TRUE, redis.delete(VALUE_KEY));
        assertFalse(Boolean.TRUE.equals(
                redis.hasKey(VALUE_KEY)));
    }

    @Test
    void serviceReadsMongoAndThenCachesInRedis() {
        InventoryItem saved = repository.save(
                new InventoryItem(
                        "SKU-CACHE", "Cached title", 5));

        assertEquals(
                "Cached title",
                service.titleBySku("SKU-CACHE"));

        assertEquals(
                "Cached title",
                redis.opsForValue().get(CACHE_KEY));

        repository.deleteById(saved.getId());

        assertEquals(
                "Cached title",
                service.titleBySku("SKU-CACHE"));
    }

    @Test
    void serviceDoesNotCacheUnknownSku() {
        assertThrows(
                NoSuchElementException.class,
                () -> service.titleBySku("SKU-UNKNOWN"));

        assertFalse(Boolean.TRUE.equals(
                redis.hasKey(UNKNOWN_CACHE_KEY)));
    }
}
```

Có **13 phương thức `@Test`** trong source; `@BeforeEach`/`@AfterEach` không được đếm là tests. Đây là bộ ví dụ dự kiến chạy với Docker khả dụng và đúng dependency, **không phải** báo cáo thực thi Gradle/CI trong phiên này.

### 11.1. Hai luồng cấu hình độc lập

**Mongo:** `@Container MONGO` → `@ServiceConnection` → `MongoConnectionDetails` → Spring Boot Mongo client → repository. Không cần tự viết URI.

**Redis:** `@Container REDIS` → Docker mapped port → `@DynamicPropertySource` cung cấp host/port → RedisConnectionFactory/Lettuce → `StringRedisTemplate`. Không dùng `@ServiceConnection` cho Redis trong class này vì muốn chứng minh manual dynamic configuration.

### 11.2. Vì sao test đọc Environment chưa đủ?

`environmentReceivesDynamicRedisProperties` assert property keys đúng, nhưng một ứng dụng có thể tạo RedisConnectionFactory tùy biến rồi bỏ qua properties này. `redisCanStoreAndReadString` mới là bằng chứng lệnh GET/SET đi qua client bean tới server.

Tương tự, `containersAreRunning` chỉ chứng minh Docker reports running. `mongoSavesAndFindsDocumentBySku` chứng minh Spring Data driver, mapping và server hoạt động thật.

### 11.3. MongoDB thao tác thực

`mongoSavesAndFindsDocumentBySku` kiểm tra ID được tạo, title, available và query theo SKU. `mongoCanUpdateDocument` thực hiện `repository.save` sau khi sửa title. `mongoCanDeleteDocument` kiểm tra delete và absent result. `mongoDerivedQueryCountsMatchingDocuments` chèn ba documents có available khác nhau và assert một document thỏa `available > 4`.

`MongoRepository.findBySku` trả `Optional.empty()` khi không có dữ liệu; lỗi mạng hoặc authentication thất bại sẽ là exception, **không nên** được chuyển bừa thành “not found” nếu chưa xác định policy.

### 11.4. Redis command và TTL

`StringRedisTemplate` dùng string serialization, nên lệnh Redis SET/GET kiểm tra được cả protocol và serializer phù hợp. Redis `increment` chạy atomic increment ở server cho một key; test kiểm tra hai giá trị trả về 1 và 2.

`redisCanAssignKeyTtl` ghi key với TTL năm phút và kiểm tra `getExpire` dương trong khoảng `(0,300]` giây. Không đợi năm phút trong test. TTL return -1 có thể nghĩa là key tồn tại nhưng không có expiry; -2 nghĩa là key không tồn tại. Nếu cần test expiry thực, dùng bounded polling với TTL nhỏ và chấp nhận timing variability thay vì `Thread.sleep` tùy tiện.

### 11.5. Cache-aside case là bằng chứng phối hợp

Lần đọc đầu, service lấy title từ Mongo rồi lưu Redis. Test xác nhận cache key có giá trị. Sau đó xóa Mongo document rồi đọc lại: kết quả vẫn là cached title. Điều đó chứng minh cache hit, **đồng thời** nhắc rằng cache có thể stale khi nguồn dữ liệu thay đổi.

Test `serviceDoesNotCacheUnknownSku` kiểm tra Mongo không có document → service ném `NoSuchElementException`, không ghi cache key sai. Đây là contract của ví dụ; sản phẩm có thể chọn negative caching nhưng cần TTL và invalidation rõ.

## 12. Cleanup và isolation cho NoSQL

`@SpringBootTest` **không tự rollback** những thao tác MongoDB/Redis như `@DataJpaTest` thường rollback JPA test transaction. Mỗi test trong ví dụ:

- Xóa tất cả documents trong collection Mongo của **container test riêng**.
- Xóa các Redis keys thuộc chính bài test trước và sau method.
- Arrange dữ liệu riêng trong từng method, không dựa vào test khác.
- Không cần một Mongo/Redis server shared của công ty hoặc production.
- Không dùng thứ tự test methods để tạo dependency ngầm.

**Cẩn thận:** `repository.deleteAll()` chỉ an toàn vì repository kết nối container test mới. Không copy cleanup này vào database shared/production. Với test data lớn hoặc nhiều suites cùng chạy, tạo database/collection/key prefix riêng và cleanup theo namespace; tránh lệnh Redis `FLUSHALL` hoặc `FLUSHDB` ngoài môi trường hoàn toàn thuộc sở hữu test.

Nếu bật JUnit parallel execution cho tests dùng chung collection và Redis keys, `@BeforeEach` của test A có thể xóa dữ liệu test B. Khi cần parallel, dùng unique fixtures/namespace theo test hoặc chạy những test có state chung tuần tự.

### Không có distributed transaction mặc định

MongoDB có cơ chế transaction trong replica set với manager thích hợp; Redis có transaction/atomic commands riêng. Chúng không tự tham gia một global transaction chỉ vì ứng dụng gắn `@Transactional`. Cache-aside có failure windows, cần idempotency, retry, stale-state policy trong production. Không suy từ integration test thành công rằng cập nhật Mongo và Redis luôn atomic.

## 13. Thay Redis DynamicPropertySource bằng @ServiceConnection

Spring Boot 3.3 nhận diện Redis image name `redis`. Với static `GenericContainer<?>`, có thể thay phần khai báo Redis trong test bằng:

```java
@Container
@ServiceConnection(name = "redis")
static final GenericContainer<?> REDIS =
        new GenericContainer<>(
                DockerImageName.parse("redis:7.2-alpine"))
                .withExposedPorts(6379);
```

Sau khi chọn cách này, **bỏ method `redisProperties(DynamicPropertyRegistry)`**. Spring Boot tạo `RedisConnectionDetails` từ Redis container. Dữ liệu được đưa cho Redis auto-configuration và bạn không phải tự điền host/port properties.

Đây là **phương án thay thế**, không phải một container thứ ba trong project runnable. Khi đổi cách, bỏ/điều chỉnh test `environmentReceivesDynamicRedisProperties` vì Environment keys có thể không còn được đăng ký như trước; thay bằng test kết nối thực và kiểm tra service connection behavior.

### Với @Bean GenericContainer cần name

Trong một `@TestConfiguration`:

```java
@TestConfiguration(proxyBeanMethods = false)
class RedisTestConfiguration {

    @Bean
    @ServiceConnection(name = "redis")
    GenericContainer<?> redisContainer() {
        return new GenericContainer<>(
                DockerImageName.parse("redis:7.2-alpine"))
                .withExposedPorts(6379);
    }
}
```

Đây là snippet cấu hình cần imports `TestConfiguration`/`Bean`/`ServiceConnection`/`GenericContainer`/`DockerImageName`. Boot không gọi bean method sớm để xem image name của `GenericContainer<?>` khi đăng ký connection details; **`name="redis"`** giúp factory chọn đúng Redis. Với static field, Boot thường có container instance để đọc image name; dùng `name` vẫn có thể làm mục đích rõ ràng.

Một container được quản lý như Spring bean thường bắt đầu/dừng theo vòng đời ApplicationContext. Điều này có lợi nếu nhiều test classes dùng chung một cached context. Đừng vừa tạo `@Container` JUnit field vừa tạo `@Bean` mới cho cùng dịch vụ mà không biết container nào đang được app dùng.

## 14. Khi nào chọn cách nào?

| Tiêu chí | `@ServiceConnection` | `@DynamicPropertySource` |
| --- | --- | --- |
| Service có Boot factory hỗ trợ | Rất gọn | Vẫn dùng được |
| Cần property key tùy biến | Không phải mục đích chính | Rất phù hợp |
| Cấu hình endpoint | `ConnectionDetails` | `DynamicPropertyRegistry` |
| Thay đổi tên property Boot | Ít boilerplate hơn | Phải cập nhật đúng keys |
| Có tự khởi động container? | Không nếu thiếu JUnit/bean lifecycle | Không |
| Ưu tiên | ConnectionDetails trước ordinary connection properties | Dynamic property source có precedence cao |
| Dùng GenericContainer không rõ image | Cần `name`/custom factory | Chỉ cần biết endpoint accessor |
| Dùng backend custom API | Có thể chưa hỗ trợ | Tự khai báo `partner.api.base-url` |
| Mức độ test cần có | Assert thao tác client thật | Assert thao tác client thật |

Một phương án tốt là dùng `@ServiceConnection` cho các backend phổ biến mà Boot nhận diện và `@DynamicPropertySource` cho phần không có factory hoặc configuration phức tạp. Không đăng ký hai nguồn cấu hình cạnh tranh cho cùng backend chỉ để “chắc chắn” test chạy.

## 15. Static container, instance container và Spring context cache

### JUnit-managed static @Container

Một static `@Container` sống trong lifecycle test class. Nếu Spring TestContext cache cùng `ApplicationContext` để tái sử dụng giữa nhiều classes, nhưng static container của class trước đã stop, client beans trong context cached có thể vẫn trỏ tới endpoint **không còn hoạt động**.

Hướng xử lý:

- Tổ chức các integration tests dùng cùng container/config trong một test class hoặc một fixture lifecycle thống nhất.
- Dùng container beans được Spring Boot quản lý trong `@TestConfiguration` nếu muốn lifecycle gắn với cached Spring context.
- Dùng `@DirtiesContext` có chủ đích khi dynamic properties thay giữa nhiều classes, không gắn bừa vào mọi test vì rất chậm.
- Không tạo một static container khác nhau trong mỗi class rồi kỳ vọng một cached context cũ tự reconnect sang mapped port mới.
- Nếu bật reusable containers, phải xử lý dữ liệu tồn dư qua nhiều JVM runs, không giả định mỗi lần test là DB sạch.

### Instance @Container

Container instance field có thể restart theo test method, tốt cho isolation nhưng tốn thời gian lớn với Mongo. Nếu app context được dựng một lần nhưng container port đổi mỗi method, `MongoClient`/RedisConnectionFactory có thể giữ endpoint cũ. Vì vậy **không** chỉ đổi `static` thành instance field trong Spring Boot integration test và chờ mọi connection tự cập nhật; cần khớp context/container lifecycle.

### Container reuse

Testcontainers hỗ trợ reusable containers tùy cấu hình và môi trường. Reuse cải thiện tốc độ local nhưng có thể để lại data/indices qua runs và thay đổi giả định isolation. Với CI nhiều users/PRs, nên có policy rõ về reuse và cleanup, không bật reuse toàn cục chỉ để tránh setup code.

## 16. Docker networking và dynamic ports

`getHost()` và `getMappedPort(containerPort)` là **đường test JVM → container**. Khi hai containers trong cùng Docker network cần giao tiếp, dùng Docker network aliases và internal port.

```text
JVM trên host:
  getHost():getMappedPort(6379)
Docker container cùng network:
  redis-alias:6379
```

Không dùng hostname `redis-alias` từ host JVM nếu nó chỉ được Docker DNS resolve nội bộ. Không dùng mapped port để container nọ gọi container kia nếu shared network có internal addressing rõ ràng. Trong remote Docker/CI-in-Docker, host có thể không phải `127.0.0.1`.

Nếu ứng dụng cần nhiều service, xem xét `Network.newNetwork()`, `withNetwork(network)` và `withNetworkAliases(...)` khi thực sự có container-to-container traffic. Demo không cần vì test JVM kết nối từng service qua host mapped ports.

## 17. Khởi động không đồng nghĩa sẵn sàng nhận request

Một container Docker có trạng thái running nhưng MongoDB chưa hoàn thành replica-set initialization hoặc Redis chưa sẵn sàng nhận commands. Testcontainers specialized classes thường có cơ chế startup phù hợp; `GenericContainer` có wait strategy mặc định hoặc cấu hình thêm khi cần.

Snippet:

```java
GenericContainer<?> redis =
        new GenericContainer<>(
                DockerImageName.parse("redis:7.2-alpine"))
                .withExposedPorts(6379)
                .waitingFor(Wait.forListeningPort());
```

Cần import `org.testcontainers.containers.wait.strategy.Wait`. Đoạn snippet này không thay thế REDIS field của project chính khi chưa được đưa vào test class đầy đủ.

Đối với HTTP services, có thể dùng wait strategy chờ HTTP health endpoint. Với database, readiness cần phản ánh khả năng driver kết nối/đọc/ghi, không chỉ process đã fork. Hạn chế `Thread.sleep(10000)` cố định vì CI load khác nhau; ưu tiên readiness checks và bounded timeout.

## 18. CI cần gì để chạy test?

Checklist vận hành:

1. Có Java 17+ và Gradle/Gradle Wrapper đúng phiên bản.
2. Docker daemon chạy và runner có quyền gọi Docker API.
3. Có thể pull `mongo:7.0` và `redis:7.2-alpine` từ registry tin cậy.
4. RAM/CPU đủ để start hai services trong cùng job.
5. Docker port forwarding hoạt động cho host/remote runner.
6. Container cleanup được cấu hình phù hợp; chú ý Testcontainers resource reaper/Ryuk và security policy.
7. Không inject production Mongo URI/Redis password vào test.
8. Có cơ chế thu thập Gradle/JUnit test reports và container logs không chứa secrets.
9. Không dùng fixed host ports để tránh race giữa jobs.
10. Khi chạy song song, cô lập data/key namespaces và lifecycle của từng suite.

Ví dụ các bước logic trong CI:

```text
Checkout
  -> Setup JDK / Gradle
  -> Provide Docker access
  -> Testcontainers pulls Mongo + Redis images
  -> Starts two containers, maps host ports
  -> Spring Boot creates clients
  -> JUnit tests run
  -> Gradle writes XML/HTML reports
  -> Containers stop/cleanup
```

**Không giả định Docker socket mounting luôn được phép.** Trong containerized CI, chia sẻ Docker socket có rủi ro quyền host. Cần dùng runner/container service được đội vận hành phê duyệt; khi Docker không khả dụng, báo integration tests chưa chạy thay vì tuyên bố PASS dựa vào unit mocks.

## 19. Chạy và đánh giá kết quả

Với project có Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.nosql.RealBackendsIntegrationTest'
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có Gradle Wrapper nhưng đã cài Gradle tương thích:

```bash
gradle test
```

Docker phải khởi động trước. Lần chạy đầu có thể tốn thời gian pull image, các lần sau có thể dùng cached image layers. Test không in stdout nghiệp vụ cố định. Đọc kết quả thực tại:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**Có 13 phương thức @Test theo source**, nhưng không có execution report trong quá trình soạn bài này, nên không khẳng định có 13 PASS. Nếu một method lỗi, phân biệt lỗi Docker startup, ApplicationContext, mapped port, Mongo mapping, Redis serialization hay assertion logic; không đổi expected data chỉ để che lỗi.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Could not find a valid Docker environment` | Docker daemon chưa chạy/quyền không đủ | `docker info`, runner Docker config |
| Image pull failed | Registry/network/tag/quota | Kiểm tra image version/registry |
| Mongo server selection timeout | Container chưa ready, URI hoặc network sai | Mongo logs, service connection, wait strategy |
| Redis `Connection refused` | Hardcoded localhost:6379 hoặc dynamic port sai | `REDIS.getHost()/getMappedPort(6379)` |
| `@ServiceConnection` không có hiệu lực | Thiếu spring-boot-testcontainers hoặc container type/name sai | Dependency, annotation, factory table |
| MongoRepository bean không có | Scan package/start dependency sai | @SpringBootApplication root, Mongo starter |
| StringRedisTemplate bean không có | Redis starter/auto-config bị loại | Dependency, RedisConnectionFactory |
| Dynamic property null | Method không static, supplier/field sai | Registry method + lifecycle |
| Test pass locally, fail CI | Remote Docker host/port khác | Không hardcode host/ports |
| Mongo query empty bất ngờ | Sai collection/database, fixture chưa tạo | Assert saved id, repository query |
| Test method fail theo thứ tự | Data bị xóa bởi test khác | Cleanup, isolated keys, tránh parallel |
| Context cache giữ endpoint cũ | Container static dừng sau class | Container bean lifecycle hoặc @DirtiesContext |
| Redis TTL -1 | SET không có expiry | Ghi key với `Duration`, assert TTL |
| Redis TTL -2 | Key đã mất | Kiểm tra setup và expiration |
| Test chạy chậm | Mongo image pull/start, full context mỗi method | Static container, context cache phù hợp |
| Container “running” nhưng service unavailable | Service readiness chưa đạt | Wait strategy, driver timeout |
| Redis key rò qua suite khác | Container reused và cleanup sai | Namespace per test và cleanup |
| Wrong Mongo type mapping | BSON/schema khác Java fields | Test document serialization thật |
| Hạ tầng production khác container | Cluster/TLS/ACL/sharding/replication | Bổ sung test environment chuyên biệt |

### Quy trình debug

1. Kiểm tra Docker daemon và image pull.
2. Kiểm tra container `isRunning()`, logs và readiness.
3. Đọc host/mapped port hoặc specialized URI sau startup.
4. Xác minh `@ServiceConnection`/`@DynamicPropertySource` đã tạo connection config đúng.
5. Thử thao tác nhỏ nhất qua actual Spring bean: Mongo save/find, Redis SET/GET.
6. Kiểm tra data fixture, database/collection, cache keys và cleanup.
7. Nếu chỉ lỗi trong CI, kiểm tra remote Docker, resource limits và Spring context reuse.
8. Nếu chỉ lỗi với production database vendor/cluster, không dùng single-node result làm bằng chứng tương đương.

## 21. Testcontainers và những dịch vụ ngoài SQL khác

| Dịch vụ | Container gợi ý | Hạng mục cần kiểm tra |
| --- | --- | --- |
| MongoDB | `MongoDBContainer` | BSON mapping, indexes, queries, transactions tùy replica-set config |
| Redis | `GenericContainer<?>` image redis | Strings, hashes, TTL, cache semantics |
| Cassandra | `CassandraContainer` | CQL/keyspace, consistency, schema |
| Elasticsearch | `ElasticsearchContainer` | Mappings, analyzers, query DSL |
| Neo4j | `Neo4jContainer<?>` | Cypher, relationships, bolt driver |
| Couchbase | `CouchbaseContainer` | Buckets, KV, indexes/query |
| Kafka | `KafkaContainer` / compatible module | Producer/consumer, offsets, serialization |
| RabbitMQ | `RabbitMQContainer` | AMQP routing, acknowledgements |
| External custom HTTP | `GenericContainer<?>` | HTTP client, timeout, JSON/error contract |

Những dịch vụ này không có API hoặc startup configuration giống nhau. Kiểm tra Testcontainers module, supported Spring Boot `ConnectionDetails` factory và Docker image versions theo **phiên bản đang dùng**. Không ngầm tin rằng một custom image sẽ được Boot nhận diện giống một image canonical nếu thiếu `@ServiceConnection(name=...)`.

### Schema/indices và dữ liệu khởi tạo

MongoDB container mới không tự tạo **domain-specific indexes**, Elasticsearch container không tự tạo mapping/application indices, Cassandra container không tự có keyspace của dự án. Khi kiểm tra migration/bootstrap, phải chạy chính cơ chế tạo schema/index của ứng dụng hoặc dựng test fixture tương đương có chủ đích.

Với message brokers, gửi message không đồng nghĩa subscriber đã consume: dùng Awaitility/bounded polling/test utilities phù hợp, không dùng `Thread.sleep` thời gian cố định và mặc định test đã chắc chắn đồng bộ.

## 22. So sánh với Docker Compose

Docker Compose có thể khởi động dịch vụ phụ trợ cho local development. Testcontainers lại giúp lifecycle gắn vào Java test và dynamic endpoint wiring trong JUnit/Spring.

| Khía cạnh | Testcontainers | Docker Compose |
| --- | --- | --- |
| Điều khiển từ Java test | Có | Không trực tiếp như JUnit extension |
| Cấp dynamic test ports | `getMappedPort`/service connection | Theo Compose config/port |
| Isolation theo suite | Dễ thiết kế | Phụ thuộc shared stack/volumes |
| Developer mở stack thủ công | Có thể | Thường tiện |
| Test cleanup tự động | Theo lifecycle/rules | Cần compose teardown |
| CI test nhiều nhánh song song | Thường thuận tiện khi không fix ports | Cần project names/networks riêng |

Không gộp mặc định hai công cụ: nếu đã có Compose stack do developer dùng, một test vẫn cần chứng minh backend nó kết nối thuộc phạm vi test. Testcontainers phù hợp hơn khi mục tiêu là CI repeatability, còn Compose có thể phù hợp với development environment lâu sống.

## 23. An toàn và bảo mật

- Không chạy test ghi/xóa trên production Mongo/Redis.
- Không dùng wildcard Mongo `deleteAll` hoặc Redis `FLUSHALL` trên shared service.
- Không lưu raw tokens, mật khẩu, PII vào Redis cache/key names hoặc test logs.
- Dùng Docker images từ nguồn được phê duyệt và pin versions/digests khi cần reproducibility.
- Không expose mapped ports công khai ra Internet.
- Không cho untrusted CI jobs quyền Docker socket tùy tiện.
- Nếu cần TLS/ACL, dùng secrets/certificates dành riêng cho tests.
- Khi dùng remote Docker, kiểm tra firewall và network isolation.
- Khi tắt Testcontainers resource cleanup vì CI constraint, phải có kế hoạch cleanup thay thế.
- Nếu bật reuse containers, không mặc định database/keys sạch giữa hai lần chạy.
- Trong production-like tests, dùng collection/db/namespace thuộc sở hữu test và cleanup đúng scope.

`@ServiceConnection` và `@DynamicPropertySource` giúp cấu hình kết nối, **không tự bảo đảm** authorization, secrets handling hoặc data-safety.

## 24. Checklist trước khi merge

1. Test muốn kiểm tra backend thật nào và image/version nào?
2. Docker có hoạt động trên developer machine và CI?
3. Container lifecycle có được quản lý thống nhất bằng JUnit extension hoặc Spring container beans?
4. Static vs instance lifecycle có phù hợp Spring context cache?
5. Không hardcode localhost hoặc host mapped port?
6. `getMappedPort` chỉ được resolve khi container start?
7. `spring-boot-testcontainers` dependency có trong test scope khi dùng `@ServiceConnection`?
8. Container type hoặc Docker image name được Boot 3.3 factory hỗ trợ?
9. `@DynamicPropertySource` có static method và supplier đúng?
10. Host/port/URI property keys đúng version Boot?
11. Có tránh cùng lúc đặt connection details và properties cạnh tranh cho một backend?
12. Test có gửi thao tác **qua Spring bean thật**, không chỉ assert container chạy?
13. Mongo mapping/query/CRUD có positive và not-found cases?
14. Redis SET/GET, INCR, TTL, DELETE có assertion cụ thể?
15. App service dùng nhiều backends có một integration test phối hợp?
16. Fixture cleanup rõ, không dựa vào SQL rollback?
17. Parallel test chạy trên namespace riêng hoặc được tắt?
18. Có tránh dùng Redis FLUSHALL/Mongo delete rộng trên database không thuộc scope test?
19. Cluster/replication/TLS production khác single container có được ghi nhận?
20. CI setup có quyền Docker, pull image và đủ tài nguyên?
21. Test report thật đã được xem, không báo PASS chỉ từ mã nguồn?
22. Khi đổi Boot/Testcontainers version, connection factory/type/key imports đã được kiểm tra?

## 25. Bài tập thực hành

1. Chạy `RealBackendsIntegrationTest` với Docker rồi xác minh các mapped ports khác port 6379/27017 mặc định.
2. Bỏ `@ServiceConnection` của Mongo, giữ Redis dynamic properties. Xem Mongo client lấy URL ở đâu và giải thích lỗi.
3. Thay Mongo `@ServiceConnection` bằng `@DynamicPropertySource` + `mongo::getReplicaSetUrl`.
4. Thay Redis dynamic properties bằng `@ServiceConnection(name="redis")`; sửa test không còn cần assert Environment host/port.
5. Thử cố định `spring.data.redis.port=6379` trong sandbox, giải thích vì sao có thể kết nối sai.
6. Thêm Mongo query `findByTitle` và fixtures để phân biệt trường hợp có/không.
7. Tạo unique index trên `sku` bằng cơ chế index configuration đúng, kiểm tra duplicate key exception.
8. Thử `redis.getExpire` khi key không có expiry và khi key không tồn tại; giải thích -1 và -2.
9. Viết test bounded polling kiểm tra Redis key thật sự hết hạn sau TTL ngắn.
10. Cập nhật Mongo document sau khi Redis cache đã có, quan sát stale title rồi thêm invalidation.
11. Dừng Redis container trong một **test class độc lập** để kiểm tra fallback; không dừng resource dùng chung làm hỏng những test khác.
12. Thử chia hai Spring test classes với static containers khác nhau, quan sát context cache và đề xuất container beans để khớp lifecycle.
13. Dùng Testcontainers cho Elasticsearch/Neo4j/Kafka nếu ứng dụng thực có dependency; đảm bảo schema/topic initialization.
14. Chạy suite trên CI Docker-in-Docker và dùng accessor thật thay vì giả định `localhost`.
15. Đọc Gradle XML/HTML report và xác minh chính xác số tests PASS/FAIL/SKIPPED.
16. Thêm một integration test xử lý connection timeout/error của Redis, nhưng không dùng credential production.
17. Thử phân biệt container-to-container network alias và host mapped port trên một mạng Docker thử nghiệm.

## 26. Tài liệu tham khảo

- [Spring Boot 3.3 — Testcontainers, service connections và dynamic properties](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): lifecycle, `@ServiceConnection`, `MongoConnectionDetails`, Redis image name, `@DynamicPropertySource`.
- [Spring Boot 3.3 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html): MongoDB, Redis starters và auto-configuration.
- [Spring Framework 6.1 — Dynamic Property Sources](https://docs.spring.io/spring-framework/docs/6.1.x/reference/html/testing.html#testcontext-ctx-management-dynamic-property-sources): `DynamicPropertyRegistry` và property precedence.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` và lifecycle.
- [Testcontainers Java — MongoDB](https://java.testcontainers.org/modules/databases/mongodb/): `MongoDBContainer` và replica set.
- [Testcontainers Java — Networking](https://java.testcontainers.org/features/networking/): `getHost`, `getMappedPort`, aliases.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): Mongo documents, repositories và mapping.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): `StringRedisTemplate`, keys và TTL.
- [Spring Framework TestContext — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): Spring cached contexts và lifecycle.

## 27. Kết luận

**Testcontainers** là công cụ kiểm thử tích hợp Spring Boot với **backend thật** nhưng được quản lý bởi Docker/test lifecycle. **`@ServiceConnection`** gắn container chuyên biệt như MongoDBContainer với Spring Boot auto-configuration thông qua `ConnectionDetails`. **`@DynamicPropertySource`** mang các thông tin runtime như host, mapped port và URI vào Spring Environment, thích hợp với GenericContainer hoặc cấu hình backend tùy biến.

Bộ ví dụ MongoDB + Redis cho thấy cách kiểm tra từ Docker container readiness đến Spring Data repository/RedisTemplate và service cache-aside. Giá trị lớn nhất không nằm ở `container.isRunning()` mà là **query và command thật** với assertions rõ, fixture cleanup đúng và khả năng tái hiện trên local/CI. Đừng nhầm container single-node với production cluster, đừng dựa vào SQL rollback để dọn NoSQL data, và đừng công bố số test PASS khi chưa thực thi Gradle cùng Docker thật.
