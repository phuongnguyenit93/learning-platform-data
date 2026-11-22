# Cô lập namespace và dọn dữ liệu kiểm thử an toàn trong Spring Data Redis

## 1. Vì sao phải cô lập dữ liệu khi kiểm thử Redis?

Redis lưu trạng thái bên ngoài JVM. Khác một biến cục bộ chỉ tồn tại trong một test, Redis key có thể tiếp tục tồn tại sau khi test kết thúc, sau khi Spring `ApplicationContext` đóng, hoặc khi một job CI khác bắt đầu sử dụng cùng Redis server.

Giả sử hai integration test dùng chung key:

```text
Test A:
  SET product:SKU-001 "Bút xanh"
  Kiểm tra đọc lại đúng dữ liệu

Test B:
  GET product:SKU-001
  Mong đợi key chưa tồn tại
```

Nếu test A chạy trước, test B thất bại. Nếu chạy song song, kết quả có thể phụ thuộc thứ tự lệnh, tạo **flaky test** — lỗi xuất hiện không ổn định, khó tái hiện. Tệ hơn, một test “dọn dẹp” bằng `FLUSHALL` có thể xóa dữ liệu của test khác, service local hoặc một Redis server ngoài ý muốn.

Vì vậy, với Spring Data Redis, một bộ test đáng tin cậy cần hai tầng bảo vệ:

1. **Cô lập (*isolation*):** key, cache, repository, Stream và các tài nguyên Redis của test không được trùng hoặc can thiệp dữ liệu bên ngoài phạm vi sở hữu.
2. **Dọn dẹp an toàn (*safe cleanup*):** chỉ xóa đúng tài nguyên test đã tạo, không dùng thao tác xóa diện rộng khi chưa xác nhận Redis server hoàn toàn thuộc quyền kiểm soát của test.

Điều quan trọng: **cô lập namespace và cô lập Redis server là hai mức khác nhau**. Prefix riêng ngăn phần lớn xung đột về tên, nhưng không ngăn test khác dùng hết bộ nhớ, chạy `FLUSHDB`, thay đổi `CONFIG` hoặc chiếm hết connection. Khi cần cô lập mạnh, dùng Redis container/instance riêng.

## 2. Mục tiêu sau bài học

Bạn sẽ biết cách:

- Chọn cấp cô lập thích hợp: riêng từng test method, test class, test suite, CI job hoặc Redis container.
- Đặt namespace có định danh duy nhất và phân biệt namespace với Redis logical database.
- Tạo key prefix rõ ràng cho `StringRedisTemplate`, `RedisTemplate` và `RedisCacheManager`.
- Dùng Testcontainers để chạy Redis thật mà không đụng Redis development/production.
- Dọn key theo danh sách đã tạo; xử lý khi một thao tác Redis tạo nhiều key gián tiếp.
- Dùng `SCAN` có giới hạn khi cần dọn theo prefix, tránh `KEYS` và `FLUSHALL` trên Redis chia sẻ.
- Tránh để lại secondary index của Redis Repository, consumer group, shadow copy TTL hoặc subscription Pub/Sub.
- Thiết kế `@BeforeEach`/`@AfterEach`, cleanup sau lỗi, test chạy song song và CI theo nguyên tắc **xóa đúng phần mình sở hữu**.

Bài viết tập trung vào **kiểm thử ứng dụng Spring Data Redis**. Không sử dụng production Redis làm nơi “thử tạm”, kể cả khi dự định xóa sau.

---

## 3. Các cấp độ cô lập Redis

Có nhiều cách cô lập, với mức bảo vệ và chi phí khác nhau:

| Cấp | Ví dụ | Bảo vệ được gì? | Giới hạn |
|---|---|---|---|
| Key riêng | `test:sku:UUID` | Tránh đè một key cụ thể | Key khác, cache index hoặc cấu hình server vẫn chung |
| Namespace riêng cho test method | `it:runId:methodId:*` | Giảm va chạm khi chạy song song | Chia sẻ memory, DB, config, Pub/Sub |
| Namespace riêng cho test class | `it:classId:*` | Dễ tái dùng container/context | Test method vẫn cần key/ID riêng hoặc cleanup |
| Logical Redis DB riêng | DB 1, DB 2 | Tách keyspace ở Redis standalone | Cùng server, cùng tài nguyên; Cluster thường chỉ DB 0 |
| Redis container riêng | Testcontainers với keyspace độc lập | Tách dữ liệu và phần lớn cấu hình | Tốn thời gian khởi động, CPU/RAM; vẫn chia sẻ host |
| Redis deployment chuyên dụng cho job | Redis riêng trong CI | Cô lập giữa job và có thể tái hiện topology | Tốn hạ tầng; phải quản lý lifecycle |

### Lựa chọn thường hợp lý

- **Unit test mock Redis:** không tạo key trên server, không cần cleanup.
- **Integration test đơn giản:** Redis container riêng cho test class hoặc suite, mỗi test dùng prefix/ID riêng.
- **Test Spring Cache và Redis Repository:** container riêng thường an toàn hơn chỉ xóa vài key vì framework có thể sinh key phụ.
- **Test Redis Cluster/Sentinel:** deployment test chuyên dụng với topology đúng, không dùng server Redis chung của nhóm.
- **Test dùng một Redis staging chia sẻ:** namespace riêng, ACL hạn chế quyền xóa, cleanup có kiểm soát, tuyệt đối không mặc định `FLUSHDB`.

**Nguyên tắc lựa chọn:** phạm vi dữ liệu do test có thể tạo càng khó liệt kê, càng nên tiến về cô lập ở cấp container hoặc deployment.

## 4. Namespace là gì?

Trong Redis, một namespace thường là **quy ước đặt tiền tố cho key**, ví dụ:

```text
app:environment:component:resource-id
```

Redis không có thư mục hoặc “schema” vật lý theo dấu `:`. Hai key:

```text
it:run-01:products:SKU-01
it:run-02:products:SKU-01
```

là hai tên key độc lập vì bytes của chúng khác nhau. Dấu `:` chỉ giúp người đọc và công cụ nhận ra các thành phần.

Cấu trúc namespace đề xuất cho integration test:

```text
it:<run-id>:<test-class>:<test-method>:<logical-key>
```

Ví dụ:

```text
it:7f63aa1:ProductCacheIT:cacheMiss:SKU-001
it:7f63aa1:ProductCacheIT:cacheHit:SKU-001
it:7f63aa1:CartRepositoryIT:saveCart:user-31
```

Có thể dùng UUID thay cho tên method nếu test name chứa dấu, ký tự không ổn định hoặc muốn giới hạn độ dài:

```text
it:4fcae0b2-...:8db13f2a-...:SKU-001
```

### Những điều kiện cần có

1. Prefix của test có **ranh giới rõ**, thường kết thúc bằng `:`.
2. Giá trị run/test ID do test runner tạo, không được dựa hoàn toàn vào một timestamp có thể trùng.
3. Key do ứng dụng tạo phải dùng **cùng quy tắc prefix**, không có một nhánh code âm thầm ghi key global.
4. Các test chạy song song không chia sẻ một key mutable nếu không đang kiểm tra chính sự cạnh tranh.
5. Cleanup chỉ được phép tác động tới prefix được cấp cho test.
6. Không chứa mật khẩu, token, email hoặc dữ liệu nhạy cảm trong tên key.

Ví dụ không đủ an toàn:

```text
test*
```

Nếu dùng pattern này để xóa key, có thể khớp `test-a`, `testing-shared` hoặc những namespace ngoài test. Tốt hơn:

```text
it:4fcae0b2:*
```

với định danh đủ mạnh và thuộc quyền sở hữu của lượt chạy hiện tại.

---

## 5. Namespace riêng không phải bảo vệ tuyệt đối

Hai test có prefix khác nhau vẫn dùng chung tài nguyên server:

```text
Redis instance (shared)
  ├── it:run-A:*      <-- Test A
  ├── it:run-B:*      <-- Test B
  └── app:local:*     <-- Ứng dụng khác
```

Những hoạt động sau có thể gây ảnh hưởng chéo dù prefix không trùng:

- Test A chạy `FLUSHALL` hoặc `FLUSHDB`.
- Test A dùng hết memory, làm Redis eviction key của B.
- Test A chạy Lua script rất lâu, khiến lệnh của B bị chậm.
- Test A đổi `notify-keyspace-events` hoặc `maxmemory-policy` ở mức server.
- Test A dùng nhiều blocking clients, tạo áp lực connection.
- Test A chạy `CONFIG SET` để thử nghiệm rồi không hoàn tác.
- Test A gây failover hoặc restart node đang dùng chung.

Vì vậy, **key-prefix isolation bảo vệ logic đặt tên; instance isolation bảo vệ dữ liệu và cấu hình ở mức rộng hơn**. Với thử nghiệm phá hủy, resilience, memory pressure hoặc cấu hình server, hãy dùng Redis riêng hoàn toàn.

## 6. Redis logical database không thay thế namespace

Redis standalone thường hỗ trợ `SELECT` để chuyển logical database:

```redis
SELECT 1
SET it:products:SKU-01 example
```

Key nằm trong DB 1 khác key cùng tên ở DB 0. Spring Boot có thể cấu hình:

```yaml
spring:
  data:
    redis:
      database: 1
```

Nhưng cần nhớ:

- Logical DB chỉ phân tách tên key, không tách tài nguyên process, CPU và memory.
- `FLUSHALL` xóa toàn bộ các logical DB trên server.
- `FLUSHDB` xóa toàn bộ **DB hiện hành**, không chỉ prefix của test.
- Hai test cùng chọn DB 1 vẫn có thể đè key của nhau.
- Redis Cluster chỉ hỗ trợ DB 0 theo mô hình triển khai Cluster phổ biến.
- Một số managed Redis có giới hạn về logical DB hoặc `SELECT`.
- Kết nối nhầm DB có thể khiến test dọn sai dữ liệu.

Do đó, nếu đã chọn DB riêng, vẫn cần namespace và xác định rõ endpoint test. **Không dùng `SELECT 1` làm bằng chứng an toàn để chạy lệnh xóa diện rộng** khi server vẫn được chia sẻ.

---

## 7. Cách đơn giản nhất: Redis container riêng với Testcontainers

Trong integration test, Testcontainers có thể chạy một Redis server tạm chỉ phục vụ test. Container nhận cổng host động, tránh phụ thuộc Redis đang chạy trên máy developer.

### 7.1. Dependencies

Ví dụ Gradle Kotlin DSL cho Spring Boot:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}

tasks.test {
    useJUnitPlatform()
}
```

Nếu dự án dùng Spring Boot BOM hoặc dependency management phù hợp, các version thường được quản lý tập trung. Nếu không, cần khai báo version Testcontainers tương thích.

Testcontainers yêu cầu Docker hoặc container runtime tương thích chạy được trên máy local/CI.

### 7.2. Spring Boot integration test dùng Redis thật

**`RedisNamespaceIsolationIT.java`**

```java
package com.example.redis;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest(
        classes = RedisNamespaceIsolationIT.TestApplication.class
)
class RedisNamespaceIsolationIT {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT)
        );
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Autowired
    StringRedisTemplate redis;

    private String prefix;
    private String key;

    @BeforeEach
    void allocateNamespace() {
        prefix = "it:" + UUID.randomUUID() + ":";
        key = prefix + "product:SKU-1";
    }

    @AfterEach
    void cleanupOnlyMyKey() {
        if (key != null) {
            redis.delete(key);
        }
    }

    @Test
    void eachTestUsesItsOwnRedisKey() {
        redis.opsForValue().set(key, "Notebook");

        assertThat(redis.opsForValue().get(key))
                .isEqualTo("Notebook");
    }

    @Test
    void aFreshNamespaceDoesNotSeePreviousTestData() {
        assertThat(redis.hasKey(key)).isFalse();

        redis.opsForValue().set(key, "Pen");

        assertThat(redis.opsForValue().get(key))
                .isEqualTo("Pen");
    }
}
```

Ở đây:

- `@Container` quản lý Redis cho test class.
- `@DynamicPropertySource` lấy endpoint thực tế từ Testcontainers.
- `@BeforeEach` cấp UUID mới để mỗi test có key độc lập.
- `@AfterEach` chỉ xóa **key mà test đã sở hữu**.
- Không cần `FLUSHDB` vì mỗi test đã có tên key riêng.
- Test không phụ thuộc key còn lại từ test khác.

Dùng version image Redis phù hợp với dự án và kiểm thử tương thích khi nâng version. Tên image là ví dụ; hãy cố định version có chủ đích thay vì luôn lấy `latest`.

### 7.3. Chú ý vòng đời Spring context và container

Spring Test có thể **cache `ApplicationContext`** giữa những test class có cấu hình giống nhau. Nếu container do `@Container static` dừng sau một class nhưng context chứa `RedisConnectionFactory` tiếp tục được tái sử dụng ở class khác, context có thể giữ endpoint của container đã dừng.

Cần lựa chọn lifecycle nhất quán:

- Container và context cùng sống trong phạm vi class; nếu context có khả năng bị chia sẻ không đúng, dùng thiết kế context tách biệt hoặc quản lý context lifecycle phù hợp.
- Một Redis container dùng chung suite có lifecycle thực sự kéo dài tới cuối suite.
- Dùng cơ chế tích hợp Testcontainers của phiên bản Spring Boot hiện tại khi phù hợp, nhưng vẫn cần xác nhận tính tương thích giữa vòng đời container và context.
- Không tạo một container mới cho mỗi method nếu không cần thiết; dùng namespace để cô lập test method trong cùng container.

**Container riêng theo class** giảm va chạm nhưng không đảm bảo các bean Spring luôn được khởi tạo lại theo đúng lifecycle nếu thiết kế test không chú ý context caching.

---

## 8. Đặt namespace tại đúng lớp của ứng dụng

Một sai lầm là chỉ thêm prefix ngay trong test, trong khi mã production vẫn ghi key không có prefix:

```java
// Test muốn dùng "it:UUID:product:SKU-1",
// nhưng service production lại luôn ghi:
String key = "product:" + sku;
```

Kết quả: các test vẫn đụng cùng `product:SKU-1`.

Có thể giải quyết bằng cách tách quy tắc đặt tên key thành một component có thể cấu hình.

### 8.1. Keyspace abstraction nhỏ

**`RedisKeyspace.java`**

```java
package com.example.redis;

public final class RedisKeyspace {

    private final String prefix;

    public RedisKeyspace(String prefix) {
        if (prefix == null || prefix.isBlank()
                || !prefix.endsWith(":")) {
            throw new IllegalArgumentException(
                    "Redis prefix must be non-empty and end with ':'"
            );
        }

        this.prefix = prefix;
    }

    public String key(String namespace, String id) {
        return prefix + namespace + ":" + id;
    }

    public String prefix() {
        return prefix;
    }
}
```

Service sử dụng `RedisKeyspace`:

```java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductCacheAdapter {

    private final StringRedisTemplate redis;
    private final RedisKeyspace keyspace;

    public ProductCacheAdapter(
            StringRedisTemplate redis,
            RedisKeyspace keyspace
    ) {
        this.redis = redis;
        this.keyspace = keyspace;
    }

    public void save(String sku, String name) {
        redis.opsForValue().set(
                keyspace.key("products", sku),
                name
        );
    }

    public String get(String sku) {
        return redis.opsForValue().get(
                keyspace.key("products", sku)
        );
    }
}
```

Trong cấu hình môi trường development/production, có thể tạo bean `RedisKeyspace` với prefix cố định do cấu hình ứng dụng quản lý. Trong integration test, tạo một instance `RedisKeyspace("it:UUID:")` gắn với đúng adapter mà test gọi.

Điểm mạnh là **cùng business code** luôn đi qua một quy tắc key, thay vì test sửa tên key theo cách không có trong mã triển khai.

### 8.2. Kiểm soát ký tự trong ID

Nếu test dùng ID do framework sinh, nên chuẩn hóa hoặc encode khi ghép key. Ví dụ trường hợp id chứa `:` không nhất thiết là lỗi Redis nhưng có thể làm các công cụ parsing/log hiểu sai thành phần.

Khi dùng namespace cho cleanup theo pattern, cần đảm bảo **prefix chạy test không chứa ký tự glob** như `*`, `?` hoặc `[` có ý nghĩa đặc biệt trong Redis pattern. UUID/chuỗi hex hoặc chữ–số–gạch ngang là lựa chọn dễ kiểm soát.

## 9. Cô lập ở cấp method, class và test run

Không có một mức prefix luôn phù hợp. Ví dụ:

### 9.1. Một prefix duy nhất cho mỗi test method

```text
it:<run-id>:<class-id>:<method-id>:*
```

Ưu điểm: cho phép các method chạy song song mà không đụng key. Nhược điểm: nếu bean cấu hình prefix được tạo một lần cho cả Spring context, cần thiết kế cách truyền namespace của từng method vào service một cách an toàn.

**Không thay đổi một biến static/global prefix khi test parallel** nếu các method cùng dùng singleton bean; method này có thể ghi vào namespace của method khác.

### 9.2. Một prefix cho cả test class

```text
it:<class-id>:*
```

Phù hợp khi test class tuần tự và làm sạch state giữa các method. Nếu test parallel hoặc có nhiều cache/Redis Repository, cần thêm key ID riêng.

### 9.3. Một prefix cho CI job hoặc test run

```text
it:build-481:*
```

Giúp đối soát dữ liệu còn sót khi job bị hủy trước cleanup. Tuy nhiên, nếu nhiều method cùng dùng chung prefix run, vẫn cần phân tách bên trong.

### 9.4. Bảng lựa chọn

| Phạm vi | Cấu trúc | Khi dùng |
|---|---|---|
| Per method | UUID riêng từng test | Test chạy song song, state độc lập |
| Per class | UUID riêng từng class | Chung Redis container, các method được cleanup tốt |
| Per suite | Run ID + component | Cần chia nhiều class và có cleanup theo suite |
| Per CI job | Build ID + namespace | Theo dõi tài nguyên bị bỏ lại sau job hỏng |
| Per container | Dedicated Redis instance | Framework tạo nhiều key phụ, test cấu hình/server |

**Không để test ID xuất phát chỉ từ tên class/method cố định qua mọi lần chạy.** Nếu lần trước chết bất thường, key cũ có thể làm lần sau thất bại. Thêm run ID ngẫu nhiên hoặc cấp container mới.

---

## 10. Ưu tiên xóa chính xác key test đã tạo

Cách cleanup an toàn nhất khi biết rõ tập key là **xóa theo danh sách**.

Ví dụ helper nhỏ:

**`RedisTestKeys.java`**

```java
package com.example.redis;

import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisTestKeys {

    private final String prefix =
            "it:" + UUID.randomUUID() + ":";

    private final Set<String> created = new LinkedHashSet<>();

    public String newKey(String logicalName) {
        String key = prefix + logicalName;
        created.add(key);
        return key;
    }

    public String prefix() {
        return prefix;
    }

    public void cleanup(StringRedisTemplate redis) {
        if (!created.isEmpty()) {
            redis.delete(created);
            created.clear();
        }
    }
}
```

JUnit dùng:

```java
class ProductRedisIT {

    @Autowired
    StringRedisTemplate redis;

    RedisTestKeys keys;

    @BeforeEach
    void setup() {
        keys = new RedisTestKeys();
    }

    @AfterEach
    void teardown() {
        keys.cleanup(redis);
    }

    @Test
    void storesValue() {
        String key = keys.newKey("product:SKU-1001");
        redis.opsForValue().set(key, "Pen");

        assertThat(redis.opsForValue().get(key))
                .isEqualTo("Pen");
    }
}
```

Đoạn này minh họa phần lifecycle/cleanup; các import JUnit, AssertJ và Spring phụ thuộc cấu hình test tương ứng.

### Vì sao cần đăng ký key trước khi ghi?

`newKey(...)` ghi nhận key vào registry **trước** lệnh Redis `SET`. Nếu lệnh Redis thành công nhưng ứng dụng gặp exception khi nhận response, `@AfterEach` vẫn biết key cần xóa.

Nếu chỉ thêm key vào danh sách **sau khi** `set(...)` trả về thành công, một số key đã được server ghi nhưng exception/timeout có thể khiến chúng không được đăng ký cleanup.

### Xóa nhiều key

`redis.delete(created)` giúp xóa một tập key biết trước. Với Redis Cluster, các lệnh đa key có ràng buộc slot; hành vi hỗ trợ và cách client chia thao tác phụ thuộc Spring Data Redis/driver. Khi key có thể ở nhiều slot, có thể xóa từng key riêng lẻ trong test hoặc dùng phương thức phù hợp với topology.

Lệnh `DEL`/`UNLINK` được thiết kế idempotent ở mức key đã biến mất: xóa key không tồn tại không tạo thêm key mới. Điều này hữu ích cho cleanup khi test thất bại giữa chừng.

**Hạn chế:** registry chỉ biết những key được đăng ký. Nếu một Redis Repository, script, cache writer hoặc listener tạo key phụ, registry này chưa chắc đủ.

## 11. @AfterEach và try/finally giúp cleanup sau assertion lỗi

JUnit Jupiter gọi `@AfterEach` sau test method thông thường ngay cả khi một assertion thất bại hoặc test ném exception. Vì vậy, đặt cleanup trong `@AfterEach` phù hợp hơn đặt ở cuối body của test:

```java
@Test
void unsafeCleanupPlacement() {
    redis.opsForValue().set(key, "test");

    assertThat(redis.opsForValue().get(key))
            .isEqualTo("different-value");

    // Assertion phía trên thất bại, lệnh này không chạy.
    redis.delete(key);
}
```

Cách phù hợp:

```java
@AfterEach
void cleanup() {
    if (key != null) {
        redis.delete(key);
    }
}
```

Với một tài nguyên tạm được tạo trong phương thức helper, dùng `try/finally`:

```java
String key = allocateTestKey();

try {
    redis.opsForValue().set(key, "value");
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("value");
} finally {
    redis.delete(key);
}
```

### Những tình huống cleanup vẫn không thể chạy

Không có cơ chế `@AfterEach` nào đảm bảo chạy khi:

- JVM bị kill đột ngột.
- Máy CI mất điện hoặc runner bị hủy.
- Process crash nghiêm trọng.
- Network đến Redis bị ngắt.
- Redis đã hỏng trong lúc test cleanup.

Vì thế cần **lớp phòng vệ thứ hai**: test data có TTL phù hợp, Redis container có vòng đời hữu hạn, hoặc một job dọn namespace cũ có kiểm soát. Không nên dựa duy nhất vào cleanup code để giữ Redis chia sẻ mãi mãi sạch.

---

## 12. TTL như cơ chế dọn dự phòng, không thay cleanup chủ động

Có thể ghi test key với TTL:

```java
redis.opsForValue().set(
        key,
        "sample",
        java.time.Duration.ofMinutes(10)
);
```

Nếu JVM chết trước `@AfterEach`, key có thể tự hết hạn sau 10 phút.

Tuy nhiên:

- TTL **không** xóa key ngay sau test.
- TTL quá ngắn có thể làm key biến mất khi test chậm, gây false failure.
- TTL quá dài để lại dữ liệu rác nếu có nhiều test.
- Một số lệnh cập nhật hoặc thay thế key có thể thay đổi/loại bỏ TTL; cần hiểu semantics Redis.
- Key phụ của Redis Repository, cache index hoặc Stream có thể không được đặt TTL cùng cách.
- Dữ liệu test bị xóa vì TTL trong khi test còn chạy có thể che giấu bug thật.
- Một listener được subscribe vẫn có tài nguyên riêng, không được giải phóng bằng TTL key.

Vì vậy TTL chỉ là **safety net**, không thay thế việc xóa key đã tạo và không thay cho Redis container riêng.

### Đừng dùng TTL để “chứng minh cleanup”

Một test `@AfterEach` muốn bảo đảm dọn sạch key phải kiểm tra hành vi `delete` hoặc để test harness xác định state phù hợp. Nếu key tự hết hạn, việc key không còn không chứng minh cleanup đã thực thi.

---

## 13. Khi nào cần SCAN để dọn theo prefix?

Có những test không biết chính xác mọi key được tạo, ví dụ:

- Spring Cache sinh Redis key theo `CacheManager`.
- Redis Repository tạo key entity và secondary index.
- Một Lua script tạo nhiều key (trong phạm vi được khai báo).
- Một flow Stream hoặc một component phụ trợ tạo metadata.
- Nhiều thao tác service khác nhau chia cùng một namespace của test.

Khi không có danh sách key, có thể xem xét **duyệt theo prefix bằng `SCAN`**.

Redis CLI:

```redis
SCAN 0 MATCH it:2ec5f83b:* COUNT 200
```

Redis trả cursor và danh sách key theo từng lượt. Tiếp tục cho tới khi cursor trở về `0`.

### Vì sao không nên dùng KEYS?

```redis
KEYS it:2ec5f83b:*
```

`KEYS` có thể tốn O(N) trên keyspace lớn và giữ Redis bận trong một lệnh. Trên Redis riêng rất nhỏ dành cho integration test, sự khác biệt có thể không đáng kể, nhưng code cleanup cần an toàn khi vô tình được tái sử dụng ở môi trường có nhiều dữ liệu.

**Ưu tiên xóa key đã biết; nếu cần dọn prefix, dùng SCAN có giới hạn và ràng buộc phạm vi rõ.**

### SCAN không có nghĩa chỉ quét key của prefix

`SCAN MATCH prefix*` vẫn phải duyệt keyspace Redis theo cơ chế cursor để tìm key khớp. `COUNT` là **hint cho lượng công việc mỗi lượt**, không phải giới hạn tổng key bị xóa.

Cần hiểu:

- Một lượt có thể trả danh sách rỗng mà cursor vẫn khác `0`.
- Một key có thể xuất hiện nhiều lần khi quét; xóa trùng phải an toàn.
- Nếu dữ liệu thay đổi trong lúc quét, không có snapshot nguyên tử.
- Một vòng SCAN có thể không đủ nếu writer khác liên tục tạo key mới.
- Trên Redis Cluster, thao tác quét có thể cần xử lý từng node theo driver/topology.

Do đó, nếu cần bảo đảm dọn một namespace đầy đủ, trước hết phải **ngừng các writer/listener thuộc namespace đó**; sau đó dọn và xác minh trong môi trường riêng.

---

## 14. Ví dụ cleanup theo prefix với Spring Data Redis

Đoạn ví dụ dùng `StringRedisTemplate` để thao tác key dạng UTF-8:

**`RedisPrefixCleaner.java`**

```java
package com.example.redis;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisPrefixCleaner {

    private final StringRedisTemplate redis;

    public RedisPrefixCleaner(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long deleteOwnedPrefix(String ownedPrefix) {
        if (ownedPrefix == null
                || !ownedPrefix.matches(
                        "it:[0-9a-fA-F-]{36}:[A-Za-z0-9:_-]+:"
                )) {
            throw new IllegalArgumentException(
                    "Refusing to scan an unowned or broad prefix"
            );
        }

        ScanOptions options = ScanOptions.scanOptions()
                .match(ownedPrefix + "*")
                .count(200)
                .build();

        long deleted = 0;

        try (Cursor<String> cursor = redis.scan(options)) {
            List<String> batch = new ArrayList<>();

            while (cursor.hasNext()) {
                String key = cursor.next();

                // Phòng vệ bổ sung: chỉ chấp nhận key đúng prefix.
                if (!key.startsWith(ownedPrefix)) {
                    throw new IllegalStateException(
                            "Unexpected key outside owned prefix"
                    );
                }

                batch.add(key);

                if (batch.size() >= 100) {
                    deleted += deleteBatch(batch);
                    batch.clear();
                }
            }

            if (!batch.isEmpty()) {
                deleted += deleteBatch(batch);
            }
        }

        return deleted;
    }

    private long deleteBatch(List<String> keys) {
        // Xóa từng key: không phụ thuộc việc các key
        // thuộc cùng hash slot trong Redis Cluster.
        long deleted = 0;

        for (String key : keys) {
            Boolean existed = redis.delete(key);
            if (Boolean.TRUE.equals(existed)) {
                deleted++;
            }
        }

        return deleted;
    }
}
```

Ví dụ trên giả định phiên bản Spring Data Redis có `StringRedisTemplate.scan(ScanOptions)` và `Cursor<String>`. Nếu dùng API thấp hơn hoặc driver/topology khác, cách duyệt cursor cần điều chỉnh theo phiên bản dự án.

**Giới hạn an toàn của ví dụ:**

- `ownedPrefix` bắt buộc có UUID dạng chuẩn sau `it:` và thành phần namespace cụ thể kết thúc bằng `:`.
- Không cho gọi với prefix rỗng, `*` hoặc `it:` quá rộng.
- Xóa từng key để tránh vấn đề lệnh đa key khác slot.
- Không dùng `FLUSHDB` hoặc `FLUSHALL`.
- Đây là helper dành cho **namespace thử nghiệm đã được cấp riêng**, không phải công cụ quản trị Redis sản xuất.
- `SCAN` trên Redis Cluster có giới hạn tùy client/topology; cần dùng chiến lược quét các node được hỗ trợ khi cluster test thực sự cần dọn toàn bộ keyspace.

### Sự phù hợp với serializer

`StringRedisTemplate` scan và delete key chuỗi theo serializer của nó. Nếu ứng dụng tạo key bằng `RedisTemplate` với key serializer khác (ví dụ JDK serialization), việc nhìn key trong CLI hoặc quét bằng template chuỗi có thể không khớp.

Khi dùng nhiều template, cần xác định bytes thực tế của key. Một prefix Java giống nhau **không có nghĩa raw Redis key bytes giống nhau** nếu serializers khác.

### Cleanup theo prefix nên là phương án cuối

Nếu test biết 5 key vừa tạo, chạy 5 lệnh delete trực tiếp thường rõ ràng và an toàn hơn quét cả keyspace để tìm chúng. Chỉ dùng SCAN khi có lý do vì framework hoặc luồng xử lý tạo key động.

---

## 15. Chống xóa nhầm bằng “ownership guard”

Trước mọi cleanup theo prefix, nên kiểm tra một tập điều kiện:

1. **Endpoint:** Redis server có thực sự là test environment không?
2. **Phạm vi:** prefix có thuộc run/test này không?
3. **Cấu trúc:** prefix có đủ hẹp, có UUID và dấu phân cách cuối không?
4. **Lệnh:** chỉ dùng `DEL`/`UNLINK` trên key khớp chính xác?
5. **Concurrency:** còn writer nào đang ghi vào namespace này không?
6. **Serializer:** key mà cleaner nhìn thấy có cùng encoding với producer không?
7. **Topology:** đang chạy standalone hay Cluster?
8. **Quan sát:** đã biết số key/đối tượng dự kiến và có thể phát hiện trường hợp bất thường không?

Ví dụ guard:

```java
if (!key.startsWith("it:" + runId + ":")) {
    throw new IllegalStateException(
            "Cleanup would touch a key outside this test run"
    );
}
```

Đừng chỉ dùng:

```java
if (key.contains("test")) {
    redis.delete(key);
}
```

Chuỗi `test` có thể xuất hiện trong key bình thường của ứng dụng.

### Dry-run khi viết công cụ dọn rộng

Nếu viết helper dùng cho môi trường shared, có thể hỗ trợ chế độ **liệt kê key dự kiến** mà không xóa. Chỉ cho phép xóa sau khi prefix được xác nhận thuộc quyền sở hữu của job.

Với bài test chạy tự động, một prefix UUID chặt và container riêng thường làm công cụ an toàn hơn nhiều so với xác nhận thủ công.

---

## 16. FLUSHDB và FLUSHALL: chỉ dùng khi Redis thực sự riêng biệt

Redis có lệnh:

```redis
FLUSHDB
FLUSHALL
```

Ý nghĩa:

- `FLUSHDB`: xóa **toàn bộ key trong logical DB hiện hành**.
- `FLUSHALL`: xóa **mọi key của mọi logical DB** trong Redis instance.

Trong test, nhiều người dùng `FLUSHDB` ở `@BeforeEach` để “làm sạch dữ liệu”, vì thao tác đơn giản. Nhưng đó là lựa chọn nguy hiểm nếu endpoint bị cấu hình nhầm hoặc server được chia sẻ.

### Khi nào có thể chấp nhận?

Chỉ khi đồng thời đáp ứng:

- Redis server/container **được cấp riêng cho test**, không có dữ liệu người dùng hoặc test khác cần giữ.
- Endpoint thật sự đã được xác minh là endpoint test.
- Có cơ chế bảo đảm chỉ test được quyền điều khiển server đó.
- Thao tác xóa là một phần có chủ đích của lifecycle test.
- Không có test khác trong cùng container đang cần state của mình khi chạy song song.

Ngay cả ở container riêng, dùng namespace và cleanup có kiểm soát thường giúp phát hiện lỗi test rõ hơn. `FLUSHDB` có thể chấp nhận để reset một Redis container hoàn toàn disposable **giữa các giai đoạn không chạy song song**, không nên trở thành default cho mọi integration test.

### Không dùng “DB 1 nên FLUSHDB an toàn”

Một Redis local chia sẻ có thể có dữ liệu của developer khác hoặc process khác trong DB 1. Không có cơ chế ownership chỉ nhờ số DB. Với Redis Cluster, logical DB thường chỉ là DB 0.

---

## 17. DEL và UNLINK khi dọn dữ liệu

Cả `DEL` và `UNLINK` có thể xóa key theo tên:

```redis
DEL it:abc:product:SKU-1
UNLINK it:abc:product:SKU-1
```

Khác biệt chính:

- `DEL` xóa key theo cơ chế đồng bộ trong lệnh.
- `UNLINK` tách key khỏi keyspace và giải phóng phần bộ nhớ của value bất đồng bộ theo cơ chế server.

Với vài key nhỏ trong integration test, `DEL` đủ đơn giản. Với hàng nghìn key hoặc value lớn, `UNLINK` có thể giảm thời gian chặn Redis khi giải phóng cấu trúc dữ liệu.

Spring Data Redis có API `unlink(...)` tương ứng, nhưng mức hỗ trợ và cách xử lý multi-key phụ thuộc template/driver. Chọn lệnh phù hợp với phiên bản Redis thực tế.

**Không nhầm “UNLINK trả về” với “mọi công việc giải phóng bộ nhớ đã hoàn tất”.** Key đã được tách khỏi keyspace, nhưng việc thu hồi bộ nhớ có thể tiếp tục ở nền.

Trong cleanup test thông thường, điều cần xác minh là **key không còn truy cập được**, không phải RSS/used_memory giảm về đúng một giá trị tức thì.

---

## 18. Spring Cache: prefix của RedisCacheManager có thể khác tên key service

Khi dùng Spring Cache:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductView getProduct(String sku) {
    return gateway.load(sku);
}
```

Redis key không nhất thiết là `products:SKU-1`. `RedisCacheManager` tạo key theo `RedisCacheConfiguration`, prefix và serializer, ví dụ:

```text
products::SKU-1
```

Nếu test chỉ xóa:

```java
redis.delete("SKU-1");
```

thì cache entry thực tế có thể vẫn tồn tại.

### 18.1. Cấu hình prefix riêng của suite

Ví dụ:

```java
@Configuration
@EnableCaching
public class TestRedisCacheConfiguration {

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory
    ) {
        String prefix = "it:01234567-89ab-4cde-8fab-0123456789ab:";

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .computePrefixWith(
                                name -> prefix + "cache:" + name + "::"
                        )
                        .entryTtl(Duration.ofMinutes(5));

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

Prefix ở đây chỉ mang tính minh họa. Trong test thật, nên cấp UUID mới cho **context/container/suite** và truyền vào cấu hình từ một nguồn được kiểm soát; không dùng cùng một UUID cố định cho mọi job CI.

`computePrefixWith(...)` quyết định prefix cache mà writer sử dụng khi ghi/xóa entry. Vì thế, khi dùng `@CacheEvict(allEntries = true)` trong test, vùng xóa cache được giới hạn theo prefix mà cấu hình thực sự tạo.

### 18.2. Chỉ xóa entry hay clear cả cache?

- Nếu test biết key logic, gọi `@CacheEvict(key = ...)` qua Spring proxy hoặc `Cache.evict(key)` phù hợp.
- Nếu cần clear toàn bộ cache, phải bảo đảm **cache prefix thuộc test**; `Cache.clear()` có thể xóa nhiều Redis key bằng batch strategy `KEYS` hoặc `SCAN`.
- Nếu nhiều test dùng chung cache name/prefix, clear của một test có thể xóa entry của test khác đang chạy.

**Cảnh báo:** chỉ thay key trong test mà không thay prefix cache manager không cô lập hoàn toàn `allEntries = true`. Một test gọi clear có thể xóa tất cả entry thuộc cache name chung, kể cả entry có key logic khác.

### 18.3. Prefix động per-method và Spring singleton

`RedisCacheManager` thường là singleton bean, cấu hình prefix khi context khởi tạo. Không nên cho hai test method song song thay cùng một biến global prefix rồi gọi cache manager.

Giải pháp:

- Context/container riêng nếu test cần clear toàn vùng cache.
- Cache name riêng cho từng test khi cấu hình cho phép và test chỉ truy cập tên của mình.
- Key ID riêng và tránh `allEntries = true` khi nhiều test dùng chung cache name.
- Chạy tuần tự những test thật sự cần dùng cùng cache manager/namespace.

---

## 19. Redis Repository: xóa entity không đồng nghĩa xóa mọi key phụ bằng DEL

Redis Repository có thể tạo nhiều loại key:

- Hash của entity.
- Secondary index theo thuộc tính `@Indexed`.
- Mapping/metadata khác tùy repository configuration.
- Key phụ phục vụ xử lý TTL và sự kiện expiration trong một số cấu hình.

Ví dụ:

```java
@RedisHash("orders")
public class Order {

    @Id
    private String id;

    @Indexed
    private String status;

    // ...
}
```

Một entity có ID `test-123` có thể được lưu thành hash, đồng thời được tham chiếu trong secondary index cho `status`.

Nếu test xóa thô:

```java
redis.delete("orders:test-123");
```

thì không chắc mọi index phụ đã được cập nhật như khi gọi repository delete.

### Cách cleanup được ưu tiên

Khi có repository do Spring Data Redis quản lý:

```java
@AfterEach
void cleanupRepositories() {
    for (String id : createdOrderIds) {
        orderRepository.deleteById(id);
    }
}
```

Cleanup qua repository giúp Spring Data Redis thực hiện những công việc cập nhật index theo logic của repository.

Sau đó, nếu test cần bảo đảm không còn bất kỳ metadata/phụ trợ nào, sử dụng **Redis container riêng** hoặc cơ chế đối soát được thiết kế cụ thể cho repository/version đang dùng.

### Vẫn cần ID và namespace riêng

Nếu keyspace của entity được cố định bằng `@RedisHash("orders")`, không nên nghĩ chỉ cần đặt một test prefix ở `StringRedisTemplate` là toàn bộ Redis Repository sẽ tự sử dụng prefix đó.

Có thể tạo ID duy nhất:

```java
String id = "it-" + UUID.randomUUID();
```

nhưng secondary index có thể vẫn là tập key chung cho một keyspace và một giá trị field, ví dụ nhiều test cùng index `status=ACTIVE`. Vì vậy **namespace của ID không đồng nghĩa namespace của mọi key phụ do repository sinh ra**.

Đối với những test cần xác minh index/expiration/cleanup, container Redis riêng hoặc cấu hình repository với keyspace test riêng sẽ có mức cô lập mạnh hơn.

---

## 20. Redis Repository với TTL và shadow copy

Khi entity dùng `@RedisHash(timeToLive = ...)` hoặc `@TimeToLive`, Spring Data Redis có thể đăng ký listener cho key hết hạn và trong một số cấu hình dùng **shadow copy/phantom key** để phục vụ event với nội dung entity.

Điều này có nghĩa:

- Hash entity có thể đã hết hạn nhưng key phụ còn tồn tại trong một thời gian.
- Keyspace event có thể chưa được listener xử lý ngay nếu Redis hoặc ứng dụng đang bị ngắt.
- Index phụ có thể cần cleanup sau expiration.
- Một test chỉ kiểm tra hash chính không còn sẽ không chứng minh mọi key phụ đã được dọn.
- Dựa vào TTL 1 giây để “dọn sạch toàn bộ repository state” là giả định không an toàn.

Khi test TTL Repository:

1. Cấp Redis container/namespace riêng.
2. Dùng entity ID duy nhất.
3. Đặt TTL vừa đủ để test đáng tin.
4. Xác minh đúng kết quả nghiệp vụ của expiration.
5. Không dùng thao tác `DEL` trên một key đoán được để thay repository cleanup.
6. Để teardown của container dọn toàn bộ những key phụ còn lại nếu không cần giữ chúng.
7. Nếu listener hoặc scheduler còn chạy, dừng hoặc đóng lifecycle trước khi tuyên bố namespace đã yên.

**Không thay đổi cấu hình `notify-keyspace-events` trên Redis chung chỉ để thử một annotation TTL.** Nếu test cần bật sự kiện expiration, dùng Redis instance riêng và cấu hình có chủ đích.

---

## 21. Redis Streams: cô lập key và consumer group

Redis Stream chứa record và thông tin về consumer group. Một test Stream thường cần tài nguyên có tên:

```text
Stream key:    it:run-42:orders:events
Group:         integration-test-workers
Consumer:      worker-1
```

Nếu nhiều test chia sẻ Stream key, chúng có thể ảnh hưởng lẫn nhau:

- Test A đọc record do test B ghi.
- Test A trim Stream, làm mất backlog của B.
- Test A tạo group cùng tên, test B gặp lỗi `BUSYGROUP`.
- Một consumer xử lý/ack record không thuộc kịch bản của mình.
- Offset `$` hoặc `0-0` trở nên phụ thuộc lịch sử cũ.

### Cách cô lập

Nên tạo Stream key riêng mỗi test:

```java
String streamKey =
        "it:" + UUID.randomUUID() + ":orders:events";
```

Có thể dùng group name khác nhau, nhưng **chỉ đổi group name không đủ cô lập** nếu cùng Stream key vì cả hai vẫn cùng tập record và retention.

### Cleanup Stream

Nếu Stream key và group chỉ thuộc test, xóa **Stream key** sẽ loại bỏ dữ liệu và metadata group gắn với Stream đó theo semantics Redis. Tuy nhiên:

- Đừng xóa Stream khi listener/container vẫn đang đọc và ghi tiếp.
- Ngừng/cancel consumer, đóng subscription hoặc container trước.
- Khi một job background có thể tạo lại Stream key, việc xóa ngay có thể bị “resurrection” bởi writer còn chạy.
- Nếu kiểm thử cần phân tích pending/ACK, thực hiện assertion trước khi xóa state.

Một chiến lược cleanup an toàn:

```text
1. Ngừng producer test.
2. Ngừng consumer/listener test.
3. Chờ các callback đã được phép chạy hoàn tất.
4. Xóa Stream key thuộc namespace test.
5. Đóng connection/container.
```

Nếu test dùng consumer group trên Stream chung do hệ thống khác sở hữu, tuyệt đối không xóa Stream key đó; chỉ cleanup group do mình tạo khi có ownership rõ và lệnh được hỗ trợ.

---

## 22. Redis Pub/Sub: channel không phải key để xóa

Redis Pub/Sub sử dụng channel:

```text
it:run-42:order-events
```

Channel name giúp định tuyến message, nhưng Pub/Sub channel **không phải một key lưu trữ** để dọn bằng `DEL`. Cleanup đúng ở đây là:

- Hủy subscription.
- Dừng `RedisMessageListenerContainer` hoặc subscription thuộc test.
- Đóng/release connection.
- Đảm bảo không còn callback bất đồng bộ gửi message vào test sau khi kết thúc.
- Dùng channel riêng, không để listener test nhận message của ứng dụng khác.

### Dùng channel/pattern riêng

Ví dụ:

```java
String channel =
        "it:" + UUID.randomUUID() + ":notifications";
```

Nếu dùng `PatternTopic`, tránh pattern quá rộng như `*` hoặc `__keyevent@0__:*` khi không cần. Một pattern rộng có thể nhận dữ liệu từ các test hoặc service khác.

### Pub/Sub không có replay

Một test publish trước khi subscriber sẵn sàng có thể mất message. Nên đồng bộ thời điểm listener bắt đầu bằng signal/latch có timeout, thay vì dựa vào `Thread.sleep(100)`.

Những điều này liên quan đến **lifecycle isolation**, không được giải quyết chỉ bằng prefix Redis key.

---

## 23. Lua script, Redis Functions và tên key phụ

Một script Redis thường được gọi bằng:

```java
redis.execute(
        script,
        List.of(testKey),
        arguments...
);
```

Nếu script chỉ thay đổi `testKey` đã được đăng ký, cleanup đơn giản. Nhưng có những script thao tác nhiều key, ví dụ:

```text
it:run-42:quota:user-1
it:run-42:quota:index
it:run-42:quota:metadata
```

Cần có hợp đồng rõ ràng về **toàn bộ key script có thể thay đổi**.

### Điều cần kiểm soát

- Tất cả key phải nằm trong namespace thuộc test.
- Các key mà script truy cập cần được khai báo phù hợp qua `KEYS` theo quy tắc Redis scripting.
- Khi dùng Redis Cluster, các key cho một script phải tuân thủ hash slot phù hợp.
- Tránh script tự tạo key global ngoài namespace.
- Nếu script tạo metadata phụ, đăng ký các key đó vào cleanup registry hoặc dùng container riêng.
- Lưu ý `SCRIPT LOAD`/script cache và Redis Functions là những tài nguyên server-level khác với key; dọn key không nhất thiết dọn những thành phần này.

Với Redis Functions, việc load/xóa function library có phạm vi ảnh hưởng server. Test thay đổi function library nên dùng Redis instance riêng, không dùng Redis chung với workload khác.

### Thao tác nguy hiểm khi test script

Không để một test Lua chạy vòng lặp rất dài hoặc thao tác lượng key quá lớn trên server chung chỉ để đánh giá khả năng chịu lỗi. Redis script dài có thể ảnh hưởng tất cả client trên node.

---

## 24. Đối tượng khác cũng cần cleanup đúng loại

Redis test có thể tạo nhiều loại tài nguyên ngoài string key:

| Tài nguyên | Cách cô lập | Cách cleanup hợp lý |
|---|---|---|
| String/hash/set/zset | Key prefix + UUID | `DEL`/`UNLINK` key sở hữu |
| Spring Cache | Cache prefix hoặc cache name test | `evict` đúng entry hoặc clear trong namespace riêng |
| Redis Repository | ID/keyspace riêng, container riêng nếu cần | `repository.deleteById`, teardown container cho key phụ |
| Redis Stream | Stream key riêng | Dừng consumer, xóa Stream key |
| Consumer group | Stream riêng + group riêng | Xóa Stream sở hữu hoặc destroy group sở hữu |
| Pub/Sub | Channel riêng | Unsubscribe/stop listener |
| Keyspace notifications | Redis instance riêng nếu chỉnh config | Khôi phục config nếu thật sự có ownership |
| Lua script state | Key được khai báo rõ | Xóa tất cả key script đã tạo |
| Redis Function library | Instance riêng | Teardown instance hoặc xóa library khi chỉ test sở hữu |
| Lock key | Prefix + UUID | Release bằng cơ chế ownership/token phù hợp |
| Rate-limit counter | Subject/policy namespace riêng | Xóa key sau test; TTL dự phòng |
| Transaction/pipeline state | Connection lifecycle riêng | Kết thúc transaction, đóng/release connection |
| Connection pool/listener thread | Bean/context lifecycle phù hợp | Close/stop ở teardown |

**Không xóa một khóa lock của thành phần khác chỉ vì tên giống “test”.** Với lock, việc release nên bảo đảm owner token còn khớp, nhất là khi nhiều thread hoặc worker cùng chạy.

---

## 25. Chạy test song song: những xung đột khó phát hiện

JUnit có thể thực thi test method/class song song tùy cấu hình. Ngay cả khi key mỗi method khác nhau, xung đột vẫn có thể phát sinh qua tài nguyên chung.

Ví dụ:

```text
Test A:
  Cache name = products
  Redis prefix = products::
  @CacheEvict(allEntries = true)

Test B:
  Cache name = products
  Redis prefix = products::
  Đang kiểm tra cache hit của SKU khác
```

Test A clear toàn bộ cache và làm test B gặp cache miss bất ngờ, dù hai method dùng SKU khác nhau.

### Quy tắc parallel test

1. Cấp namespace riêng cho từng test hoặc từng nhóm không giao thoa.
2. Tránh chia cache name/prefix khi test có `clear()`.
3. Không để hai method sửa cùng một biến static chỉ định prefix.
4. Không đổi cấu hình Redis server dùng chung theo thứ tự bất định.
5. Không dùng `FLUSHDB` để chuẩn bị cho test trong một suite chạy song song.
6. Dừng worker/listener nền trước khi cleanup.
7. Nếu state bắt buộc chia sẻ để kiểm tra concurrency, mô tả rõ ranh giới và kết quả mong đợi.
8. Nếu không thể cô lập, chạy nhóm test đó tuần tự hoặc cấp container riêng.

### Spring context caching cũng là trạng thái chia sẻ

Các bean singleton như `RedisCacheManager`, `RedisKeyspace` hoặc listener có thể sống qua nhiều test class khi Spring reuse context. Nếu bean chứa prefix hoặc cache state mutable, việc reuse context có thể gây nhiễu.

Giữ cấu hình bất biến theo vòng đời context hoặc cấp context riêng cho bài test có yêu cầu thay đổi cấu hình.

---

## 26. Test suite bị kill giữa chừng: xử lý dữ liệu mồ côi

Không thể bảo đảm mọi test chạy `@AfterEach`. Với Redis chung phục vụ test, key có thể còn sót khi CI job bị hủy:

```text
it:old-run-1:...
it:old-run-2:...
it:current-run:...
```

Cách xử lý:

### 26.1. Ưu tiên container disposable

Nếu Redis container chỉ thuộc job và có lifecycle đúng, teardown của test runner/CI có thể dọn toàn bộ dữ liệu cùng container. Vẫn cần quản lý trường hợp container bị orphan do lỗi CI runner.

### 26.2. Đặt TTL dự phòng cho key test

Khi tính năng cho phép, cho key test TTL đủ dài để test chạy bình thường nhưng ngắn hơn vòng đời chấp nhận lưu rác.

### 26.3. Job dọn namespace cũ có kiểm soát

Nếu Redis test shared bắt buộc dùng lâu dài, có thể thiết kế job quét namespace `it:<run-id>:*` của những run được xác nhận đã kết thúc.

Điều kiện cần:

- Dữ liệu quản lý run ID được lưu riêng và đáng tin cậy.
- Chỉ dọn run có trạng thái kết thúc/hết hạn được xác minh.
- Không suy ra key “cũ” từ text/UUID nếu không có metadata đáng tin.
- Cleanup dùng prefix chặt, có dry-run và giới hạn tải.
- Không dọn prefix của run đang hoạt động.
- Có log đếm key và cảnh báo khi số lượng khác thường.

Đây là giải pháp vận hành cho **test infrastructure**, không phải lý do để cho mọi test tùy tiện tạo key vĩnh viễn.

---

## 27. Isolation khi kiểm thử @CacheEvict và repository delete

Hai thao tác xóa dễ gây hiểu nhầm:

### 27.1. Cache evict từng entry

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void evictProduct(String sku) {
}
```

Nếu cache manager có prefix riêng, lời gọi evict một key có thể tương đối dễ cô lập.

### 27.2. Cache evict toàn vùng

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void evictAll() {
}
```

Thao tác này có thể làm cache writer xóa **mọi entry có prefix vùng cache**, không chỉ key mà method đã tạo. Nếu cache name chung, test khác có thể bị ảnh hưởng.

### 27.3. Repository delete

`repository.deleteById(id)` có thể cập nhật secondary index. `redis.delete("key")` thô có thể để lại index phụ.

Do đó:

| Test muốn kiểm tra | Cách teardown nên ưu tiên |
|---|---|
| Cache một SKU | Evict key chính xác hoặc delete key thuộc test |
| Clear toàn cache | Cache prefix/context/container riêng |
| Save/update Redis Repository | Repository delete cho các ID đã tạo |
| Secondary index + TTL phức tạp | Container chuyên dụng, không chỉ DEL entity hash |
| Stream consumer group | Dừng consumer rồi xóa stream sở hữu |
| Pub/Sub listener | Stop/unsubscribe, không DEL channel |

---

## 28. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng key `product:1` cố định cho mọi test | Test phụ thuộc thứ tự và chạy song song gây lỗi | Prefix + UUID per test |
| Dùng `FLUSHALL` trong `@BeforeEach` | Xóa toàn bộ Redis instance, có thể xóa dữ liệu ngoài test | Chỉ dùng Redis container disposable có ownership rõ; ưu tiên cleanup key |
| Dùng `FLUSHDB` vì nghĩ DB riêng tuyệt đối | Có thể xóa dữ liệu khác trong DB và không hoạt động như mong muốn ở Cluster | Namespace và container riêng |
| Cleanup bằng `KEYS test*` | Quét nặng và pattern rộng, có thể xóa nhầm | SCAN prefix UUID chặt hoặc registry key |
| Dùng `StringRedisTemplate` scan key được serialize nhị phân bởi template khác | Không tìm/xóa đúng key | Thống nhất key serializer hoặc dọn qua API tạo key |
| Chỉ DEL hash Redis Repository | Index phụ có thể còn | Dùng repository delete hoặc container riêng |
| Dựa vào TTL để cleanup tất cả state | Key phụ/listener có thể còn | Cleanup chủ động và teardown container |
| Dùng UUID trong entity ID nhưng cache prefix chung | `allEntries=true` có thể xóa data test khác | Prefix cache riêng, tránh clear chung |
| Dùng một static mutable namespace trong parallel tests | Các method ghi nhầm prefix của nhau | Namespace bất biến per context hoặc dependency per test |
| Quên dừng Stream listener | Dọn xong key lại được tạo mới | Stop/cancel producer và consumer trước cleanup |
| Cố DEL Pub/Sub channel | Không có state key để xóa | Unsubscribe/close listener |
| Test dùng Redis local thật thay vì container | Có thể đụng ứng dụng đang chạy hoặc dọn sai | Testcontainers/cổng động |
| Context Spring cache bean tới container đã dừng | Test class sau không kết nối được | Căn chỉnh lifecycle context/container |
| `@AfterEach` chỉ chạy nếu test pass | Nhầm cơ chế dọn | Đặt cleanup trong hook/finally; có TTL/container dự phòng |
| Cleanup không ghi nhận key trước lệnh SET | Timeout sau khi server ghi làm key bị bỏ sót | Đăng ký key trước khi gửi lệnh |
| SCAN đang có writer liên tục | Namespace có thể không rỗng sau vòng scan | Stop writers, kiểm soát lifecycle và xác minh |
| Test Redis Cluster bằng cleanup đa key không tương thích slot | Lỗi `CROSSSLOT` hoặc routing | Dọn từng key hoặc dùng API cluster phù hợp |
| Test sửa `CONFIG SET` trên server chung | Ảnh hưởng ứng dụng khác | Redis instance riêng cho test cấu hình |
| Dùng key có API key hoặc email trong prefix | Lộ dữ liệu nhạy cảm trong log/Redis | Opaque ID hoặc hash có kiểm soát |

---

## 29. Quy trình thiết kế một Redis integration test an toàn

Có thể áp dụng tuần tự:

1. **Xác định ranh giới test.** Chỉ cần kiểm tra Redis String, Spring Cache, Redis Repository hay Stream?
2. **Xác định tài nguyên được tạo.** Một key hay nhiều index/metadata/listener?
3. **Chọn mức cô lập.** Prefix per method hoặc container riêng.
4. **Bảo đảm endpoint là Redis test.** Dùng Testcontainers property injection/cổng động.
5. **Cấp namespace UUID.** Không phụ thuộc thời gian chạy hoặc tên cố định.
6. **Truyền namespace vào code thực.** Không tạo một prefix chỉ tồn tại trong test nếu service không dùng.
7. **Đăng ký key trước khi ghi.** Lưu danh sách cần cleanup.
8. **Chạy assertion mong muốn.** Tránh giả định Redis keyspace luôn trống.
9. **Dừng writer/listener.** Nhất là Stream consumer và Pub/Sub.
10. **Cleanup theo ownership.** Xóa exact keys, repository delete, hoặc scoped SCAN nếu thật sự cần.
11. **Không xóa Redis global.** Trừ khi chắc chắn container hoàn toàn disposable và không có test khác sử dụng.
12. **Chuẩn bị phương án khi test bị kill.** TTL, teardown container, job dọn namespace cũ.
13. **Xem xét parallel execution.** Tránh singleton mutable prefix hoặc `allEntries=true` chung.
14. **Đo độ ổn định trong CI.** Test phải tái lập khi thay runner và thay thứ tự chạy.

### Một mẫu hợp đồng test data

```text
Owner       : RedisNamespaceIsolationIT
Run ID      : UUID do test runner tạo
Redis       : Testcontainers dedicated Redis
Namespace   : it:<runId>:product:
Created keys: Được ghi nhận trước mỗi thao tác SET
Cleanup     : @AfterEach gọi delete trên danh sách key
Fallback    : Container teardown
Parallel    : Mỗi method có UUID; không FLUSHDB
Expected    : Không tạo/xóa key ngoài namespace test
```

Việc ghi rõ hợp đồng như trên giúp test có khả năng được người khác bảo trì mà không vô tình mở rộng phạm vi xóa.

---

## 30. Tình huống thực hành

### Tình huống 1 — Hai test cùng đọc sản phẩm

Test A và B dùng chung Redis nhưng đều gọi `GET products::SKU-1`. B mong cache miss trong khi A vừa nạp cache.

**Giải thích:** hai test không cô lập cache key. Cần key riêng hoặc cache namespace/context riêng. Nếu test dùng `@Cacheable`, chỉ đổi ID của object test mà không đổi cache key generator có thể chưa đủ.

### Tình huống 2 — CI chạy song song với FLUSHDB

Hai job CI dùng cùng Redis DB 1. Job A gọi `FLUSHDB` trước test, làm job B mất key.

**Giải thích:** DB index không cấp ownership độc quyền. Cần Redis container per job hoặc namespace riêng và bỏ `FLUSHDB`.

### Tình huống 3 — Test dùng repository.deleteById nhưng index vẫn sai

Một integration test có entity `@Indexed`, sau cleanup vẫn thấy index tham chiếu cũ do listener TTL không chạy như mong đợi.

**Giải thích:** cần xác định cơ chế repository/index, key phụ và event expiration. Container riêng là cách cô lập mạnh cho loại test này; cleanup thô có thể làm tình trạng tệ hơn.

### Tình huống 4 — Test bị kill, không chạy @AfterEach

Một job tạo `it:run-123:*` rồi runner bị hủy. Lần chạy sau có state rác.

**Giải thích:** cần run ID mới cho lần sau để tránh va chạm, cùng TTL/teardown container hoặc job cleanup cũ có kiểm soát.

### Tình huống 5 — SCAN trả một batch rỗng

Cleanup gọi `SCAN` thấy danh sách rỗng ở lượt đầu nhưng cursor chưa về `0`, rồi dừng.

**Giải thích:** dừng quá sớm. SCAN phải tiếp tục bằng cursor cho tới khi hoàn tất. Kết quả rỗng một lượt không có nghĩa không còn key.

### Tình huống 6 — Redis Cluster có key cùng prefix ở nhiều node

Test dùng lệnh đa key để xóa toàn bộ key có prefix, nhưng Redis trả lỗi `CROSSSLOT`.

**Giải thích:** prefix giống nhau không đảm bảo cùng hash slot. Dùng cleanup phù hợp topology hoặc xóa từng key. SCAN trên Cluster cần xử lý những node liên quan, không giả định một cursor quét toàn cụm.

### Tình huống 7 — Stream được xóa rồi lại xuất hiện

`@AfterEach` xóa Stream key, sau đó một background producer tiếp tục `XADD`.

**Giải thích:** producer còn chạy và tạo lại key. Cần dừng mọi producer/consumer thuộc test trước cleanup.

### Tình huống 8 — Pub/Sub listener nhận dữ liệu từ test khác

Hai test subscribe `events:*` nên cùng nhận event của cả hai.

**Giải thích:** pattern quá rộng và channel chưa được cô lập. Dùng channel riêng và stop subscription đúng lifecycle.

### Tình huống 9 — RedisTemplate dùng serializer khác

Test tạo key qua `RedisTemplate<Object,Object>` với key serializer nhị phân, rồi dùng `StringRedisTemplate` để xóa key bằng tên chuỗi tưởng giống hệt.

**Giải thích:** raw bytes có thể khác. Cleanup phải sử dụng API hoặc serializer tương thích với producer.

### Tình huống 10 — Unit test có cần namespace?

Service trong unit test dùng Mockito để giả lập `RedisTemplate` và không kết nối Redis server.

**Giải thích:** unit test không tạo Redis key thật nên không cần Redis cleanup. Chỉ cần đảm bảo mock/stub được reset đúng lifecycle và test không vô tình gọi Redis thật.

---

## 31. Ghi nhớ quan trọng

**Cô lập dữ liệu kiểm thử trong Spring Data Redis** không chỉ là thêm chữ `test` vào tên key. Cần xác định **ai sở hữu tài nguyên**, key được tạo ra như thế nào và tài nguyên nào phải được dọn sau test.

- **Với key biết trước:** dùng UUID namespace, ghi nhận trước khi tạo và xóa chính xác.
- **Với cache hoặc repository sinh key phụ:** dùng prefix cấu hình đúng hoặc Redis container riêng; ưu tiên API cleanup của chính framework.
- **Với Stream:** key riêng, dừng consumer/producer trước khi xóa.
- **Với Pub/Sub:** channel riêng và hủy subscription, không DEL channel.
- **Với test cần thay Redis config hoặc thử lỗi server:** dùng instance hoàn toàn riêng.
- **Với cleanup theo prefix:** SCAN có ràng buộc ownership; không dùng pattern quá rộng hoặc mặc định FLUSHDB/FLUSHALL.
- **Với parallel tests:** không chia prefix mutable hoặc cache manager có thao tác clear toàn vùng.
- **Với CI bị gián đoạn:** kết hợp teardown container, TTL dự phòng và cơ chế dọn run cũ được kiểm soát.

Lựa chọn thường an toàn và dễ vận hành nhất cho integration test là **Redis Testcontainers tách biệt**, kết hợp **namespace/UUID per test** và **cleanup theo đúng tài nguyên đã tạo**. Bằng cách này, kết quả test không phụ thuộc thứ tự chạy và không đe dọa dữ liệu của ứng dụng khác.

### Tài liệu tham khảo

- [Spring Data Redis — Reference Documentation](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers for Java](https://java.testcontainers.org/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/)
- [Redis — FLUSHDB](https://redis.io/docs/latest/commands/flushdb/)
- [Redis — FLUSHALL](https://redis.io/docs/latest/commands/flushall/)
