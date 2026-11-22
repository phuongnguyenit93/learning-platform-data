# Viết kiểm thử tích hợp và quan sát hành vi khi lỗi

## 1. Mục tiêu của bài thực hành

Một ứng dụng Spring Boot có thể kết nối Redis và ghi/đọc thành công trong môi trường phát triển, nhưng vẫn gặp sự cố khi hoạt động thật:

- Redis tạm ngừng phản hồi hoặc kết nối bị cắt.
- Một khóa tồn tại nhưng value không thể giải mã bằng serializer hiện tại.
- Khóa hết TTL ngay trong lúc ứng dụng đang đọc.
- Lệnh ghi đã được Redis thực thi nhưng phản hồi bị mất, khiến client retry và tạo tác dụng phụ trùng.
- Cơ chế fallback về database chạy khi Redis lỗi, nhưng lại làm tăng tải database quá mức.
- Redis khôi phục, song client chưa reconnect hoặc health check vẫn báo lỗi.
- Metrics đếm Redis timeout thành cache miss, làm số liệu quan sát sai.
- Cả application và driver ghi một exception ở nhiều tầng, tạo log storm.

Nếu chỉ kiểm thử:

```java
assertEquals("value", redis.opsForValue().get("key"));
```

thì chúng ta mới biết một thao tác hoạt động trong tình huống thuận lợi. **Kiểm thử tích hợp có giá trị phải chứng minh ứng dụng phản ứng đúng cả khi Redis hoạt động, khi Redis lỗi và sau khi Redis hồi phục.**

Bài này thuộc phần **Thực hành** trong **Spring Data Redis**. Sau khi hoàn thành, bạn có thể:

1. Dựng Redis thật bằng Testcontainers để kiểm thử `RedisTemplate` và serializer.
2. Viết test cho cache hit, cache miss, TTL và dữ liệu không thể deserialize.
3. Tiêm lỗi kết nối/timeout có kiểm soát.
4. Phân biệt `GET` không có key với lỗi hạ tầng.
5. Kiểm tra fallback, retry và idempotency bằng các tình huống cụ thể.
6. Ghi metrics, logs, correlation ID và đo thời gian phục hồi.
7. Thiết kế các bài test nâng cao cho Redis Streams, Pub/Sub, Sentinel và Cluster.
8. Tích hợp kiểm thử vào CI mà không xóa nhầm dữ liệu của môi trường khác.

Tất cả thao tác phá kết nối, pause, restart hoặc failover trong bài chỉ thực hiện trên **Redis thử nghiệm được tạo riêng**. Không gây fault cho Redis production để chạy bài tập.

## 2. Hiểu rõ khác biệt giữa unit test và integration test

### 2.1. Unit test

Unit test có thể thay `RedisTemplate` bằng mock:

```java
when(valueOperations.get("cache:product:42"))
        .thenReturn("READY");
```

Nó phù hợp để kiểm tra:

- Logic chọn key.
- Quy tắc fallback.
- Mapping lỗi thành response.
- Việc retry có đúng điều kiện hay không.
- Code có gọi đúng dependency không.

Nhưng mock thường không chứng minh được:

- Serializer thực sự tạo/đọc đúng byte.
- TTL được Redis xử lý.
- Spring Boot tạo `RedisConnectionFactory` đúng.
- Redis server trả lỗi `WRONGTYPE`.
- Connection timeout/reconnect xảy ra thế nào.
- Lua script thực sự nguyên tử.
- Redis Cluster có chuyển hướng slot đúng không.

### 2.2. Integration test

Integration test chạy với **Redis thật**, đồng thời dùng phần lớn stack Spring Data Redis mà production sử dụng:

```text
JUnit 5
   |
   v
Spring Boot ApplicationContext
   |
   v
RedisTemplate / RedisCacheManager
   |
   v
LettuceConnectionFactory
   |
   v
Redis container thật
```

Cần làm rõ phạm vi: một Redis container standalone kiểm chứng tốt lệnh, serializer và TTL, nhưng **không thay thế** bài test topology Redis Sentinel/Cluster hoặc hành vi của dịch vụ Redis được quản lý.

### 2.3. Fault-injection integration test

Khi cần xem hành vi lỗi:

```text
Test harness
    |
    +--> Gửi request qua service
    |
    +--> Pause Redis / chặn network / kích hoạt failover
    |
    +--> Quan sát exception, metric, log, retry
    |
    +--> Khôi phục Redis
    |
    +--> Chờ đến khi thao tác thực sự hoạt động trở lại
```

Mục tiêu không phải làm cho tất cả request luôn thành công trong suốt sự cố. Mục tiêu là kiểm tra **hợp đồng hệ thống đã công bố**: lỗi có được nhận biết đúng, fallback có đúng không, recovery diễn ra trong giới hạn và có mất/nhân đôi tác dụng phụ không.

## 3. Kiến trúc bài lab

Chúng ta xây một service cache sản phẩm nhỏ:

```text
ProductController (tùy chọn)
          |
          v
ProductCacheGateway
          |
          +--> RedisTemplate<String, ProductSnapshot>
          |             |
          |             v
          |         Redis thật
          |
          +--> Micrometer counters/timers
          |
          +--> CacheDependencyException
                        |
                        +--> cause gốc được giữ
```

Một số quy ước:

```text
Key prefix: demo:products:v1:
Payload:    JSON của ProductSnapshot
TTL:        do caller đặt
Metrics:    demo.redis.cache.lookup
Outcomes:   hit, miss, error
```

Đối tượng minh họa:

```json
{
  "id": "P-42",
  "name": "Notebook",
  "revision": 5
}
```

Dữ liệu trong bài là giả, không chứa thông tin người dùng thực.

### 3.1. Tiêu chí chấp nhận

| Tình huống | Kết quả mong đợi |
|---|---|
| Key không tồn tại | `Optional.empty()`, tăng metric `miss` |
| Key hợp lệ | Trả object đúng, tăng metric `hit` |
| TTL hết hạn | Đọc trả miss; không phải exception |
| Byte không phải JSON hợp lệ | Giữ lỗi deserialize trong cause, tăng metric `error` |
| Redis không phản hồi | Phát lỗi có cause, không biến thành miss |
| Redis khôi phục | Đọc/ghi lại được bằng cùng ứng dụng |
| Fallback được cho phép | Đọc nguồn có thẩm quyền, ghi nhận fallback |
| Lệnh ghi không idempotent bị timeout | Không retry mù quáng |
| Test lặp lại | Không phụ thuộc thứ tự chạy hoặc key của test khác |

## 4. Chuẩn bị môi trường

Khuyến nghị cho ví dụ:

- JDK 17 trở lên.
- Spring Boot 3.x và Spring Data Redis tương ứng.
- JUnit Jupiter.
- Testcontainers.
- Docker hoặc runtime container được Testcontainers hỗ trợ.
- Redis image được pin theo tag/version phục vụ kiểm thử.
- Micrometer qua Spring Boot Actuator.
- Awaitility để đợi điều kiện thay vì `Thread.sleep` cố định.

Cấu trúc dự án minh họa:

```text
src/
  main/
    java/com/example/redislab/
      RedisLabApplication.java
      ProductSnapshot.java
      ProductRedisConfiguration.java
      CacheDependencyException.java
      ProductCacheGateway.java
  test/
    java/com/example/redislab/
      ProductCacheIntegrationTest.java
      RedisOutageIntegrationTest.java
```

Các đoạn code trong bài là ví dụ cho Spring Boot 3.x. Khi triển khai thực tế, cần dùng phiên bản dependency mà dự án đã pin, không tự trộn phiên bản Spring Data Redis và Lettuce ngoài BOM.

### 4.1. Maven dependencies

Nếu dùng Maven với `spring-boot-starter-parent` hoặc Spring Boot BOM đã được cấu hình:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.awaitility</groupId>
        <artifactId>awaitility</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Nếu dự án không dùng BOM có quản lý các dependency trên, hãy pin versions tương thích theo chính sách build. Không nên sao chép phiên bản cũ từ một bài blog và bỏ qua ma trận hỗ trợ của dự án.

### 4.2. Spring Boot application

```java
package com.example.redislab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedisLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedisLabApplication.class, args);
    }
}
```

Có thể cấu hình timeout dành cho integration test qua `@DynamicPropertySource` hoặc file profile test. **Không trỏ integration test tới Redis production.**

## 5. Định nghĩa model và serializer

### 5.1. ProductSnapshot

```java
package com.example.redislab;

public record ProductSnapshot(
        String id,
        String name,
        long revision
) {
}
```

Record giúp ví dụ gọn. Chúng ta dùng JSON để có thể tạo một payload hỏng có chủ đích và xác minh lỗi deserialize.

### 5.2. RedisTemplate với serializer tường minh

```java
package com.example.redislab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductRedisConfiguration {

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, ProductSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        ProductSnapshot.class
                )
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

Trong ví dụ này:

- Key được encode dạng String UTF-8.
- Value được encode thành JSON theo lớp `ProductSnapshot`.
- Test có thể dùng `StringRedisTemplate` để ghi byte không phải JSON vào **cùng key vật lý**.
- Cả hai template dùng chung `RedisConnectionFactory`, nên kiểm thử vẫn đi qua Lettuce và Redis thật.

Không sử dụng Java native deserialization cho payload không đáng tin. Nếu ứng dụng thật dùng serializer khác, test phải cấu hình đúng serializer production.

### 5.3. Vì sao phải kiểm thử serializer?

Nếu một ứng dụng đổi từ JDK serialization sang JSON, `GET` ở Redis CLI vẫn tìm thấy key nhưng ứng dụng mới có thể không decode được value.

```text
GET key -> raw bytes tồn tại
                  |
                  v
       JSON deserializer
                  |
          +-------+-------+
          |               |
       Hợp lệ           Không hợp lệ
          |               |
        Object       SerializationException
```

Không được kết luận “Redis key không tồn tại” chỉ vì serializer không tạo được object.

## 6. Exception an toàn giữ nguyên nguyên nhân gốc

Chúng ta muốn service bọc lỗi Redis thành một lỗi ứng dụng có thông điệp ổn định, nhưng vẫn giữ original cause.

```java
package com.example.redislab;

public final class CacheDependencyException
        extends RuntimeException {

    private final String safeOperation;

    public CacheDependencyException(
            String safeOperation,
            Throwable cause) {

        super("Product cache dependency operation failed", cause);
        this.safeOperation = safeOperation;
    }

    public String safeOperation() {
        return safeOperation;
    }
}
```

`safeOperation` được gán bằng một chuỗi cố định trong code như `product_cache_read`, không lấy trực tiếp từ HTTP request hay raw Redis key.

**Sai:**

```java
throw new RuntimeException(ex.getMessage());
```

Vì nguyên nhân gốc bị mất và message có thể chứa dữ liệu nhạy cảm.

**Đúng hơn:**

```java
throw new CacheDependencyException(
        "product_cache_read",
        ex
);
```

Khi đó:

```java
wrapped.getCause() == originalException
```

Cause chain giúp phân biệt lỗi kết nối, timeout và serializer ngay cả khi API chỉ trả mã lỗi chung cho người dùng.

## 7. ProductCacheGateway: code cần kiểm thử

Gateway có trách nhiệm:

- Tạo key từ ID đã kiểm tra.
- Đọc cache.
- Ghi với TTL.
- Phân biệt hit, miss và error.
- Ghi metric có nhãn hữu hạn.
- Propagate lỗi đúng nguyên nhân.

```java
package com.example.redislab;

import java.time.Duration;
import java.util.Optional;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheGateway {

    private static final String PREFIX = "demo:products:v1:";

    private final RedisTemplate<String, ProductSnapshot> redis;
    private final MeterRegistry metrics;

    public ProductCacheGateway(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis,
            MeterRegistry metrics) {

        this.redis = redis;
        this.metrics = metrics;
    }

    public static String keyFor(String id) {
        if (id == null ||
                !id.matches("[A-Za-z0-9._-]{1,100}")) {
            throw new IllegalArgumentException(
                    "Product ID has invalid format"
            );
        }

        return PREFIX + id;
    }

    public Optional<ProductSnapshot> find(String productId) {
        String key = keyFor(productId);

        Timer.Sample sample = Timer.start(metrics);

        try {
            ProductSnapshot result =
                    redis.opsForValue().get(key);

            if (result == null) {
                count("read", "miss");
                return Optional.empty();
            }

            count("read", "hit");
            return Optional.of(result);

        } catch (DataAccessException | SerializationException ex) {
            count("read", "error");
            throw new CacheDependencyException(
                    "product_cache_read",
                    ex
            );

        } finally {
            sample.stop(metrics.timer(
                    "demo.redis.cache.read.duration",
                    "cache", "products"
            ));
        }
    }

    public void put(
            ProductSnapshot product,
            Duration ttl) {

        if (product == null) {
            throw new IllegalArgumentException(
                    "Product must not be null"
            );
        }

        if (ttl == null || ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException(
                    "TTL must be positive"
            );
        }

        String key = keyFor(product.id());

        try {
            redis.opsForValue().set(key, product, ttl);
            count("write", "success");

        } catch (DataAccessException | SerializationException ex) {
            count("write", "error");

            throw new CacheDependencyException(
                    "product_cache_write",
                    ex
            );
        }
    }

    private void count(String operation, String outcome) {
        metrics.counter(
                "demo.redis.cache.lookup",
                "cache", "products",
                "operation", operation,
                "outcome", outcome
        ).increment();
    }
}
```

### 7.1. Các điểm quan trọng

1. `find()` trả `Optional.empty()` **chỉ khi Redis GET hợp lệ trả null**.
2. Lỗi Redis/serializer được bọc và giữ cause.
3. Metrics có `cache`, `operation`, `outcome` từ **tập cố định**, không dùng product ID hoặc key.
4. `Timer.Sample` đo cả thời gian thành công lẫn thất bại.
5. `put()` kiểm tra TTL trước khi gọi Redis.
6. `put()` không tự retry write trong trường hợp timeout.
7. Không ghi cache value hoặc raw exception message ra log.

Các lệnh Redis có thể ném thêm runtime exceptions tùy serializer/driver và cách ứng dụng sử dụng. Với dự án thật, cần phân loại theo các type phù hợp của stack đang dùng; không thêm `catch (Exception)` rồi biến tất cả thành cache miss.

### 7.2. Vì sao không dùng một counter chung cho mọi sự kiện?

Nếu chỉ đo:

```text
redis_operation_total
```

bạn không phân biệt được:

```text
Read hit
Read miss
Read error
Write success
Write error
```

Khi Redis down, hệ thống có thể có nhiều `error`, nhưng `miss` phải giữ nguyên ý nghĩa về key không tồn tại.

### 7.3. Tên metric và naming convention

Micrometer đặt tên trong Java là:

```text
demo.redis.cache.lookup
demo.redis.cache.read.duration
```

Một Prometheus registry có thể xuất những tên được chuyển đổi như:

```text
demo_redis_cache_lookup_total
demo_redis_cache_read_duration_seconds
```

Tên cụ thể phụ thuộc registry/naming convention. Cần xem endpoint metrics của ứng dụng; không tự đoán rằng mọi môi trường đều xuất đúng một tên.

## 8. Khởi tạo Redis container cho bài integration test

Dùng `@Testcontainers` và `@Container` để JUnit quản lý vòng đời Redis dành riêng cho test.

```java
package com.example.redislab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import org.springframework.data.redis.core.StringRedisTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class RedisConnectionSmokeTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void configureRedis(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379)
        );
        registry.add(
                "spring.data.redis.timeout",
                () -> "700ms"
        );
        registry.add(
                "spring.data.redis.connect-timeout",
                () -> "700ms"
        );
    }

    @Autowired
    StringRedisTemplate rawRedis;

    @Test
    void setAndGetThroughSpring() {
        String key = "it:smoke:product-42";

        try {
            rawRedis.opsForValue().set(key, "READY");

            assertEquals(
                    "READY",
                    rawRedis.opsForValue().get(key)
            );
        } finally {
            rawRedis.delete(key);
        }
    }
}
```

Ở đây `REDIS.getMappedPort(6379)` được sử dụng vì Testcontainers cấp một port host ngẫu nhiên; test không cần hard-code `localhost:6379`.

### 8.1. Tại sao chọn Redis thật?

Lệnh `SET`/`GET` đi qua:

```text
Spring Boot configuration
    -> RedisConnectionFactory
    -> Lettuce
    -> Redis server
    -> Spring serializers
```

Nếu config host/port sai, serializer cấu hình sai hoặc Redis không khởi động, test có khả năng phát hiện.

### 8.2. Tại sao không dùng Redis production?

Một bài test có thể tạo key, thay TTL, gửi payload lỗi hoặc tạm ngắt kết nối. Những thao tác đó chỉ được phép chạy trên môi trường test cô lập.

Dùng Redis container cho test cơ bản giúp:

- Kết quả ít phụ thuộc dữ liệu người khác.
- Không phải gọi `FLUSHALL`.
- Có thể hủy toàn bộ dữ liệu sau test.
- Chạy cùng stack trên máy phát triển và CI.

### 8.3. Test profile

Có thể tạo:

```yaml
# application-it.yml
spring:
  data:
    redis:
      timeout: 700ms
      connect-timeout: 700ms
```

Nếu `@DynamicPropertySource` đã định nghĩa timeout, file này không bắt buộc. Tuy nhiên, trong dự án lớn nên có profile `it` riêng để cấu hình những tính năng không được phép chạy ngoài test, như jobs hoặc listeners background.

## 9. Test cache hit và cache miss

Tạo một test class dùng Redis container, gateway và một `MeterRegistry`.

```java
package com.example.redislab;

import java.time.Duration;
import java.util.UUID;

import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
class ProductCacheIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379)
        );
        registry.add("spring.data.redis.timeout", () -> "700ms");
        registry.add(
                "spring.data.redis.connect-timeout",
                () -> "700ms"
        );
    }

    @Autowired
    ProductCacheGateway cache;

    @Autowired
    MeterRegistry metrics;

    @Test
    void distinguishesHitFromMiss() {
        String id = "p-" + UUID.randomUUID();

        double missBefore = count("read", "miss");
        double hitBefore = count("read", "hit");

        assertTrue(cache.find(id).isEmpty());

        ProductSnapshot product =
                new ProductSnapshot(id, "Notebook", 7);

        cache.put(product, Duration.ofMinutes(2));

        assertEquals(
                product,
                cache.find(id).orElseThrow()
        );

        assertEquals(
                missBefore + 1,
                count("read", "miss"),
                0.0001
        );

        assertEquals(
                hitBefore + 1,
                count("read", "hit"),
                0.0001
        );
    }

    private double count(String operation, String outcome) {
        return metrics.counter(
                "demo.redis.cache.lookup",
                "cache", "products",
                "operation", operation,
                "outcome", outcome
        ).count();
    }
}
```

### 9.1. Vì sao kiểm tra delta metric?

Các counter có thể tồn tại từ trước trong cùng `ApplicationContext`. Vì vậy, test lưu `before`, thực hiện một số hành động cụ thể rồi so `after`.

Không giả định counter tổng bằng `1` nếu nhiều test dùng chung registry.

### 9.2. Điều gì chưa được chứng minh?

Test trên chứng minh **Redis-backed gateway** phân biệt hit/miss. Nó chưa chứng minh cache-aside có đọc database khi miss hoặc API endpoint trả response phù hợp; đó là bài test của service/controller ở tầng trên.

## 10. Test TTL: Redis tự xóa khóa khi đến hạn

Một test không nên dựa vào `Thread.sleep` cố định rồi khẳng định TTL đã hết đúng thời điểm.

Ví dụ thêm vào class `ProductCacheIntegrationTest`:

```java
@Test
void expiresAfterTtl() {
    String id = "ttl-" + UUID.randomUUID();

    ProductSnapshot product =
            new ProductSnapshot(id, "Temporary", 1);

    cache.put(product, Duration.ofSeconds(1));

    assertEquals(
            product,
            cache.find(id).orElseThrow()
    );

    org.awaitility.Awaitility.await()
            .atMost(Duration.ofSeconds(8))
            .pollInterval(Duration.ofMillis(100))
            .until(() -> cache.find(id).isEmpty());
}
```

Bài test cần import `Duration`, `UUID` như phần trước. Có thể dùng `await()` static import nếu muốn.

### 10.1. Phân biệt expiration và connection error

Sau TTL, Redis `GET` có thể trả `null`: đó là **miss** hợp lệ.

Nếu Redis đột ngột bị ngắt trong lúc chờ, `cache.find(id)` ném `CacheDependencyException`, test phải thất bại; **không catch rồi xem đó là dấu hiệu hết hạn**.

### 10.2. Kiểm tra TTL ngay sau write

Nếu muốn biết key có TTL thật:

```java
Long ttl = rawRedis.getExpire(
        ProductCacheGateway.keyFor(id),
        java.util.concurrent.TimeUnit.MILLISECONDS
);

assertNotNull(ttl);
assertTrue(ttl > 0);
```

Không assert `ttl == 1000` tuyệt đối vì thời gian trôi giữa `SET` và `PTTL`. Có thể kiểm tra trong một khoảng hợp lý, và `-1`/`-2` có ý nghĩa riêng:

| PTTL | Ý nghĩa |
|---|---|
| Số dương | Key còn hạn |
| `-1` | Key tồn tại nhưng không TTL |
| `-2` | Key không tồn tại |

Lưu ý `TTL`/`PTTL` và dữ liệu có thể thay đổi trong lúc đo; test nên tránh điều kiện quá sát deadline.

## 11. Test dữ liệu lỗi serializer bằng Redis thật

Đây là tình huống quan trọng mà mock dễ bỏ qua.

Chúng ta đã cấu hình:

```text
ProductRedisTemplate:
    String key -> JSON ProductSnapshot
```

Nhưng một client khác có thể ghi trực tiếp một chuỗi không phải JSON hợp lệ dưới cùng key.

### 11.1. Chuẩn bị payload sai định dạng

Thêm `StringRedisTemplate` vào class test:

```java
@Autowired
org.springframework.data.redis.core.StringRedisTemplate rawRedis;
```

Thêm test:

```java
@Test
void preservesSerializationFailure() {
    String id = "corrupt-" + UUID.randomUUID();
    String key = ProductCacheGateway.keyFor(id);

    rawRedis.opsForValue().set(
            key,
            "{this-is-not-valid-json",
            Duration.ofMinutes(2)
    );

    double errorsBefore = count("read", "error");

    CacheDependencyException error = assertThrows(
            CacheDependencyException.class,
            () -> cache.find(id)
    );

    assertEquals(
            "product_cache_read",
            error.safeOperation()
    );

    assertNotNull(error.getCause());

    assertInstanceOf(
            org.springframework.data.redis.serializer
                    .SerializationException.class,
            error.getCause()
    );

    assertEquals(
            errorsBefore + 1,
            count("read", "error"),
            0.0001
    );

    assertFalse(error.getMessage().contains(id));
}
```

Đoạn trên dùng `assertInstanceOf` của JUnit 5. Với đoạn import trong một file Java thật, package `org.springframework.data.redis.serializer.SerializationException` phải được viết trên **một dòng import hoàn chỉnh**; cách xuống dòng minh họa ở đối số `class` chỉ nhằm hiển thị.

Có thể thay bằng cách rõ ràng hơn:

```java
assertTrue(error.getCause()
        instanceof org.springframework.data.redis.serializer.SerializationException);
```

### 11.2. Test phải chứng minh điều gì?

- Key Redis **có tồn tại**.
- Reader JSON không giải mã được payload.
- Gateway không trả `Optional.empty()`.
- Gateway giữ exception deserialize gốc trong `getCause()`.
- Metric `error` tăng.
- Message của wrapper không chứa ID hay raw payload.

Nếu test chỉ kiểm tra response HTTP là 500 nhưng không xem cause, có thể bỏ sót một handler đang cố tình nuốt lỗi serializer rồi ném một exception chung thiếu nguyên nhân.

### 11.3. Không log raw payload

Trong production, đoạn sau có nguy cơ lộ thông tin:

```java
log.error("Bad JSON from Redis: {}", rawValue);
```

Thay bằng những field an toàn, ví dụ:

```text
event=redis_read_failed
operation=product_cache_read
category=SERIALIZATION
schemaVersion=1
traceId=<generated>
```

Không dùng Redis key, tên người dùng, access token hay JSON lỗi làm metric label.

## 12. Kiểm thử lỗi kết nối bằng fault injection

Một Redis container dừng hoặc không trả lời sẽ khiến ứng dụng đi vào error path.

Có hai cách tiếp cận:

1. **Chặn network qua Toxiproxy hoặc network fault injector** để làm đứt kết nối, thêm latency hoặc mất phản hồi trong khi Redis vẫn chạy.
2. **Pause/unpause container Redis** trong môi trường Docker thử nghiệm để mô phỏng Redis không phản hồi mà không đổi port được mapping.

Toxiproxy đặc biệt hữu ích cho các bài test latency/network partition có tính kiểm soát. Phần sau minh họa một cách dùng Docker pause để kiểm tra Redis client timeout và recovery.

### 12.1. Vì sao không stop rồi start lại cùng GenericContainer một cách ngây thơ?

Khi gọi:

```java
redis.stop();
redis.start();
```

Testcontainers có thể tạo container mới với **port mapping mới**. Nhưng `LettuceConnectionFactory` trong Spring context đã được tạo với host/port cũ; việc Redis mới chạy không bảo đảm context tự cập nhật endpoint.

Vì vậy, với test outage và recovery trong cùng Spring context, nên giữ endpoint ổn định hoặc thiết kế lại context/connection factory có chủ đích.

### 12.2. Tạo một class riêng cho fault injection

Không đặt bài test pause Redis trong cùng class với test hit/miss để tránh chúng chạy song song và ảnh hưởng lẫn nhau.

```java
package com.example.redislab;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.annotation.DirtiesContext;

import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@Testcontainers
@Tag("fault-injection")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class RedisOutageIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(6379);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(6379)
        );
        registry.add("spring.data.redis.timeout", () -> "700ms");
        registry.add(
                "spring.data.redis.connect-timeout",
                () -> "700ms"
        );
    }

    @Autowired
    ProductCacheGateway cache;

    @Test
    void reportsFailureAndThenRecovers() {
        String id = "outage-" + UUID.randomUUID();
        ProductSnapshot product =
                new ProductSnapshot(id, "Recovery", 1);

        cache.put(product, Duration.ofMinutes(2));
        assertEquals(product, cache.find(id).orElseThrow());

        String containerId = REDIS.getContainerId();
        var docker = DockerClientFactory.instance().client();

        try {
            docker.pauseContainerCmd(containerId).exec();

            CacheDependencyException error = assertThrows(
                    CacheDependencyException.class,
                    () -> cache.find(id)
            );

            assertNotNull(error.getCause());

        } finally {
            docker.unpauseContainerCmd(containerId).exec();
        }

        await()
                .atMost(Duration.ofSeconds(20))
                .pollInterval(Duration.ofMillis(250))
                .ignoreExceptions()
                .untilAsserted(() -> {
                    cache.put(product, Duration.ofMinutes(2));
                    assertEquals(
                            product,
                            cache.find(id).orElseThrow()
                    );
                });
    }
}
```

**Giới hạn của ví dụ:**

- Docker pause/unpause cần quyền điều khiển Docker và runtime có hỗ trợ.
- Test cần Redis container riêng; không bao giờ pause một Redis service dùng chung.
- Mốc timeout 700 ms, deadline recovery 20 giây là **giá trị minh họa**, không phải SLO khuyến nghị chung.
- Nếu client đang queue commands, lỗi có thể đến dưới dạng timeout hoặc connection failure tùy thời điểm.
- Với test song song hoặc Spring context cache, phải cô lập lớp này khỏi các test dùng cùng Redis endpoint/context.
- `ignoreExceptions()` chỉ thuộc đoạn **poll recovery**; nó không có nghĩa application production được phép nuốt lỗi Redis.
- Nếu Docker/runtime không hỗ trợ pause, dùng một fault-injection proxy thay vì sửa test bằng `Thread.sleep` ngẫu nhiên.

### 12.3. Recovery cần xác nhận bằng thao tác thật

Đừng chỉ kiểm tra:

```text
Container state = running
```

Vì Lettuce có thể vẫn đang reconnect hoặc cache topology chưa cập nhật.

Đoạn `await()` thử lại cả `put` và `find` để xác minh **đường ghi và đường đọc qua Spring Data Redis** đã phục hồi.

### 12.4. Vì sao cần try/finally?

Nếu assertion trong lúc Redis bị pause thất bại, `finally` vẫn cố gắng unpause Redis. Điều này giúp tránh để test environment ở trạng thái không phản hồi.

Với các thao tác phá topology hoặc network phức tạp hơn, test harness còn cần **cleanup độc lập**, chẳng hạn hủy toàn bộ môi trường test sau mỗi run.

## 13. Đo RTO tại tầng ứng dụng

**Recovery Time Objective (RTO)** là mục tiêu về thời gian phục hồi dịch vụ theo một định nghĩa cụ thể.

Một phép đo hữu ích:

```text
T0: Bắt đầu fault
T1: Redis server khôi phục
T2: Lettuce reconnect
T3: Spring service đọc/ghi thành công
T4: API p99 và error rate trở về SLO
```

Không nên đo riêng `T1 - T0` rồi gọi đó là RTO của ứng dụng. Đối với API, mốc `T4` thường có ý nghĩa hơn.

Có thể đo elapsed time bằng đồng hồ monotonic:

```java
long startedNanos = System.nanoTime();

triggerFault();
restoreFault();
awaitRecovery();

long elapsedMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedNanos
        );
```

Đoạn này chỉ là cấu trúc đo. Test harness phải xác định `triggerFault`, `restoreFault` và `awaitRecovery` cụ thể và ghi nhận các sự kiện quan sát được. Không báo một giá trị RTO nếu chưa chạy fault injection thật.

### 13.1. Đặt acceptance threshold theo nghiệp vụ

Ví dụ một test môi trường staging có thể yêu cầu:

```text
Redis tạm ngừng phản hồi:
    -> request lỗi được phân loại

Sau restore:
    -> trong một deadline đã công bố,
       application có thể đọc/ghi trở lại

Sau ổn định:
    -> error rate và p99 trở về ngưỡng
```

Ngưỡng phải tương thích hạ tầng, driver timeout, traffic và yêu cầu nghiệp vụ. Một test chạy trên CI CPU bị giới hạn không nên vô tình trở thành thước đo production SLA.

## 14. Quan sát exception type, cause và response

Một integration test tốt cần phân biệt:

```text
Cache MISS
    -> GET trả null
    -> không ném exception

Redis CONNECTION ERROR
    -> Lettuce không kết nối hoặc command timeout
    -> Spring Data Redis bọc/ánh xạ exception
    -> Gateway giữ cause

Serialization ERROR
    -> key có byte không phù hợp
    -> deserializer thất bại
    -> Gateway giữ cause

WRONGTYPE
    -> key là String nhưng code gọi HGETALL
    -> Redis trả lỗi command
    -> Gateway không biến thành miss
```

### 14.1. Giữ cause khi bọc lỗi

Kiểm tra:

```java
CacheDependencyException error = assertThrows(
        CacheDependencyException.class,
        () -> cache.find(id)
);

assertNotNull(error.getCause());
assertEquals(
        "Product cache dependency operation failed",
        error.getMessage()
);
```

Nếu project có policy phân loại nguyên nhân như `CONNECTION`, `TIMEOUT`, `SERIALIZATION`, test có thể kiểm tra category tương ứng nhưng không nên phụ thuộc text message tiếng Anh của driver.

### 14.2. HTTP response không được lộ message Redis

Ví dụ controller advice:

```java
@RestControllerAdvice
public class CacheErrorAdvice {

    @ExceptionHandler(CacheDependencyException.class)
    public ResponseEntity<ApiError> handle(
            CacheDependencyException error) {

        String errorId = java.util.UUID.randomUUID().toString();

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError(
                        "CACHE_DEPENDENCY_UNAVAILABLE",
                        "Dịch vụ tạm thời không khả dụng",
                        errorId
                ));
    }

    public record ApiError(
            String code,
            String message,
            String errorId
    ) {
    }
}
```

Cần các imports từ `org.springframework.http.*` và `org.springframework.web.bind.annotation.*`, cùng `spring-boot-starter-web` nếu dùng REST. Đây là ví dụ mở rộng, không bắt buộc cho core gateway test.

Dùng `MockMvc` hoặc `WebTestClient` để xác nhận response không chứa:

- Full Redis key.
- JSON payload.
- Connection URI.
- Raw `ex.getMessage()`.
- Stack trace.

Không nhất thiết mọi lỗi serializer phải trả 503. Status HTTP phụ thuộc hợp đồng API và nguồn dữ liệu; quan trọng là **không che lỗi và không rò rỉ chi tiết nội bộ**.

## 15. Metrics: không được đếm lỗi thành miss

Với `ProductCacheGateway`, chúng ta muốn có ba kết quả đọc:

```text
hit
miss
error
```

Giả sử trong 5 phút:

```text
hits   = 800
misses = 200
errors = 50
```

Có hai phép đo khác nhau:

**Cache hit ratio trên các lookup có kết quả hợp lệ:**

\[
\frac{800}{800+200} = 80\%
\]

**Redis lookup error ratio trên tổng attempts:**

\[
\frac{50}{800+200+50} \approx 4.76\%
\]

Không gộp `errors` vào `misses`, vì đó là hai dạng sự kiện khác nhau.

### 15.1. Prometheus queries minh họa

Giả sử counter được xuất ra dạng:

```text
demo_redis_cache_lookup_total{
  cache="products",
  operation="read",
  outcome="hit"
}
```

Một truy vấn hit ratio theo cửa sổ 5 phút:

```promql
sum(rate(demo_redis_cache_lookup_total{
  cache="products",
  operation="read",
  outcome="hit"
}[5m]))
/
clamp_min(
  sum(rate(demo_redis_cache_lookup_total{
    cache="products",
    operation="read",
    outcome=~"hit|miss"
  }[5m])),
  0.001
)
```

Tỷ lệ lỗi đọc:

```promql
sum(rate(demo_redis_cache_lookup_total{
  cache="products",
  operation="read",
  outcome="error"
}[5m]))
/
clamp_min(
  sum(rate(demo_redis_cache_lookup_total{
    cache="products",
    operation="read"
  }[5m])),
  0.001
)
```

Các truy vấn phụ thuộc tên metric/labels đã được exporter xuất thật. Với lưu lượng quá thấp, tỷ lệ hit 0% hoặc 100% có thể chỉ dựa trên một vài request; cần điều kiện minimum sample volume để đánh giá cảnh báo.

### 15.2. Timer phải bao gồm lỗi

Nếu chỉ đo thời gian những lệnh `GET` thành công, dashboard có thể nhìn thấy Redis “nhanh” ngay trong lúc timeout tăng hàng loạt.

Đo Timer trong `finally` như gateway mẫu giúp ghi lại:

```text
successful requests latency
timeout requests latency
serializer failure latency
```

Tuy nhiên, khi phân tích latency, có thể cần tag `outcome` vào một Timer riêng hoặc phân rã dữ liệu theo lớp metric, miễn là không tạo nhãn cardinality cao.

## 16. Logging: quan sát lỗi nhưng không in Redis value

Khi Redis down, một hệ thống có thể phát hàng nghìn lỗi mỗi giây. Nếu mọi tầng đều gọi:

```java
log.error("Redis failed", ex);
```

ta có thể gặp:

- Log storm.
- Chi phí lưu log lớn.
- Cùng lỗi bị ghi nhiều lần.
- Stack trace có thể chứa command/key/URI.
- Khó xác định số lỗi thật.

Một event an toàn hơn:

```text
event=redis_dependency_failure
operation=product_cache_read
category=CONNECTION_OR_TIMEOUT
exceptionType=RedisConnectionFailureException
requestTraceId=<generated>
retryAttempt=1
```

Không đưa user ID, raw Redis key, session token, payload hoặc connection password vào các field này.

### 16.1. Ghi một lần ở boundary

Quy tắc thông dụng:

```text
Redis adapter -> giữ exception cause, tăng metric
      |
Service -> chọn retry/fallback theo contract
      |
API/worker boundary -> log sự kiện an toàn một lần
```

Nếu một lỗi đã được xử lý bằng fallback thành công, tầng xử lý fallback cần ghi metric `fallback_total` để vận hành vẫn nhìn thấy Redis outage.

### 16.2. Kiểm thử log redaction

Ở môi trường test, dùng một payload giả có chuỗi sentinel:

```text
DO_NOT_LOG_DEMO_SECRET_123
```

Cho serializer hoặc một dependency ném lỗi có message chứa chuỗi đó, sau đó kiểm tra logging boundary chỉ ghi category/type/operation. Không cần log payload thật.

Nếu dùng Logback `ListAppender` hoặc output capture, test nên xác nhận chuỗi sentinel **không xuất hiện** trong log chính thức được tạo bởi code của bạn.

Lưu ý: thư viện bên thứ ba hoặc tracing auto-instrumentation có thể phát thêm logs/spans; cần xem cấu hình của các kênh này riêng.

## 17. Fallback: chỉ dùng khi có nguồn dữ liệu có thẩm quyền

Giả sử PostgreSQL là nguồn sản phẩm thực, còn Redis chỉ là cache:

```text
API GET /products/42
          |
          v
Redis cache
     +----+-----+----------------+
     |          |                |
    HIT        MISS             ERROR
     |          |                |
     v          v                v
  Return    Read DB         Policy decision
               |                 |
               v                 +--> fallback DB nếu cho phép
          Warm cache
```

### 17.1. Miss khác lỗi kết nối

**Cache miss:**

```java
cache.find(id) -> Optional.empty()
```

**Cache error:**

```java
cache.find(id) -> throws CacheDependencyException
```

Nếu service bắt mọi exception rồi trả `Optional.empty()`, database có thể bị dồn tải trong outage mà metrics cache miss sai hoàn toàn.

### 17.2. Contract fallback

Một chính sách có thể là:

- Khi cache miss: đọc database.
- Khi Redis timeout/mất kết nối: đọc database có giới hạn tải, ghi metric fallback.
- Khi serializer error: fail fast hoặc xử lý theo migration policy; không tự xem như miss.
- Khi database cũng lỗi: trả lỗi, giữ thông tin cả hai nguyên nhân.
- Khi Redis phục hồi: cân nhắc warm cache theo tốc độ giới hạn.

### 17.3. Unit + integration test cho fallback

Có thể unit-test service bằng fake repository:

```text
Given: Redis gateway throws connection failure
And: source repository returns product
When: GET product
Then: product được trả từ source
And: fallback counter tăng
And: không có write bắt buộc vào Redis đang lỗi
```

Và test tích hợp với Redis container bị pause:

```text
Given: source of truth sẵn sàng
When: Redis timeout
Then: API trả đúng kết quả fallback
And: không tính thành cache miss
And: response latency nằm trong timeout budget
```

Nếu dùng database thật, có thể kết hợp PostgreSQL Testcontainers để kiểm tra toàn luồng. Fake chỉ giúp test logic fallback, **không chứng minh transaction/connection của database thật**.

### 17.4. Bảo vệ database khỏi fallback storm

Một Redis outage có thể chuyển toàn bộ cache traffic sang database:

```text
Redis down
   |
   v
10.000 cache reads/s
   |
   v
10.000 DB reads/s
```

Nếu database chỉ chịu được 2.000 requests/s, fallback không có giới hạn lại trở thành nguyên nhân gây outage thứ hai.

Cần test:

- Concurrency limit hoặc bulkhead.
- Circuit breaker.
- Timeout tổng.
- Rate limit.
- Tải của database khi cache miss đồng loạt.
- Khả năng phục hồi khi Redis quay lại.

## 18. Retry: chỉ kiểm thử “thử lại thành công” là chưa đủ

Một lệnh Redis có thể đã được server thực thi nhưng client timeout trước khi nhận reply.

```text
Client                      Redis
    |                          |
    | INCR counter ----------> |
    |                          | counter = 11
    |       [reply lost]       |
    | timeout                  |
    |                          |
    | Retry INCR ------------> | counter = 12
```

Nếu một sự kiện chỉ được phép tăng counter một lần, retry vô điều kiện gây lỗi.

### 18.1. Phân loại theo tính idempotent

| Lệnh | Nguy cơ khi retry sau timeout |
|---|---|
| `GET` | Thường không tạo tác dụng phụ, có thể retry có giới hạn |
| `EXISTS` | Thường đọc, chịu chi phí thêm |
| `SET` cùng value | Có thể idempotent về value; TTL/revision vẫn cần xét |
| `INCR` | Có thể tăng hai lần |
| `LPUSH` | Có thể thêm item trùng |
| `XADD` | Có thể tạo event trùng |
| `ZINCRBY` | Có thể cộng score hai lần |
| Lua script có side effects | Phụ thuộc nội dung script |
| Transaction `EXEC` | Có thể đã commit trước khi mất reply |

Timeout không đồng nghĩa “Redis chắc chắn chưa chạy lệnh”. Một integration test về retry phải kiểm tra **trạng thái cuối cùng**, không chỉ xem lần gọi cuối thành công.

### 18.2. Test idempotency bằng operation ID

Một nghiệp vụ nhận:

```json
{
  "operationId": "demo-order-42-confirm-v1",
  "orderId": "42",
  "action": "CONFIRM"
}
```

Hệ thống nhận thao tác cần ghi nhận `operationId` tại nơi side effect có thẩm quyền xảy ra. Nếu cùng request được replay, nó phải được nhận diện theo protocol idempotency.

Test:

1. Gửi request có operation ID.
2. Gây timeout/mất response sau khi có thể đã xử lý.
3. Gửi lại cùng operation ID.
4. Đọc trạng thái authoritative.
5. Xác nhận không có side effect trùng.
6. Kiểm tra log và metrics ghi nhận retry.

Một Redis `SET NX` với TTL có thể hỗ trợ một phần cơ chế chống trùng, nhưng với tác vụ cực kỳ quan trọng cần xem xét atomicity giữa idempotency record và side effect nghiệp vụ. Không coi `SET NX` tách rời một database write là transaction xuyên hệ thống.

### 18.3. Đừng retry lỗi cố định

Một số lỗi thường không giải quyết bằng retry cùng lệnh:

```text
NOPERM
WRONGTYPE
CROSSSLOT
Serializer không tương thích
Lệnh không được engine hỗ trợ
```

Cần sửa quyền, schema hoặc cách dùng Redis. Retry lặp vô hạn chỉ gây thêm tải và che lỗi thật.

## 19. Test WRONGTYPE bằng Redis thật

Redis có nhiều loại dữ liệu: String, Hash, List, Set, Sorted Set, Stream.

Ví dụ một key đang là String:

```java
rawRedis.opsForValue().set(
        "it:wrongtype:42",
        "string-value"
);
```

Nhưng code gọi Hash command:

```java
rawRedis.opsForHash()
        .entries("it:wrongtype:42");
```

Redis sẽ từ chối vì type không phù hợp.

Một test:

```java
@Test
void redisRejectsWrongType() {
    String key = "it:wrongtype:" + UUID.randomUUID();

    try {
        rawRedis.opsForValue().set(key, "not-a-hash");

        assertThrows(
                org.springframework.dao.DataAccessException.class,
                () -> rawRedis.opsForHash().entries(key)
        );

    } finally {
        rawRedis.delete(key);
    }
}
```

Tùy Spring Data Redis/driver, exception cụ thể có thể là một subtype khác của `DataAccessException`. Mục tiêu là xác nhận **lỗi server thực sự được propagate**, không biến thành Hash rỗng hoặc cache miss.

### 19.1. Vì sao lỗi này thường xuất hiện sau deployment?

Ví dụ:

```text
Version cũ: SET profile:42 "<JSON>"
Version mới: HGETALL profile:42
```

Nếu không đổi namespace hoặc migrate dữ liệu, code mới có thể nhận `WRONGTYPE`.

Test tích hợp với Redis thật giúp phát hiện sự khác biệt Redis type mà một mock `HashOperations` có thể không mô phỏng.

## 20. Test `@Cacheable` và `@CacheEvict` nếu dùng Spring Cache

Không phải ứng dụng nào cũng truy cập Redis qua `RedisTemplate`. Nhiều dự án dùng Spring Cache abstraction.

Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductSnapshot findById(String id) {
    return source.findById(id);
}
```

Các trường hợp cần kiểm thử:

| Trường hợp | Điều mong đợi |
|---|---|
| Gọi cùng ID lần đầu | Source được gọi; cache được điền nếu kết quả được cache |
| Gọi lại cùng ID | Source không bị gọi lại nếu cache hit |
| Gọi ID khác | Key khác, có thể cache miss |
| TTL hết hạn | Source được gọi lại |
| `@CacheEvict(key = "#id")` | Chỉ xóa entry phù hợp |
| Clear cả region | Phạm vi và quyền được kiểm soát |
| Redis down | Hành vi theo `CacheErrorHandler`/fallback policy thực |
| Serializer không tương thích | Không im lặng coi là miss |

### 20.1. Chú ý proxy/AOP

Annotation `@Cacheable` thường được áp dụng qua Spring proxy. Nếu một method tự gọi method khác cùng class (`self-invocation`), caching có thể không được kích hoạt như kỳ vọng.

Một test chỉ gọi trực tiếp method Java bên trong class không chứng minh Spring Cache proxy hoạt động. Nên gọi bean do Spring quản lý qua context.

### 20.2. Đếm số lần gọi source

Một test có thể dùng một `@SpyBean` hoặc cơ chế test spy tương ứng phiên bản Spring Boot để đếm số lần gọi repository/service nguồn:

```text
Call findById("P-42") twice
    |
    v
Expect source called once
```

Lưu ý các annotation mock/spy có thể thay đổi giữa phiên bản Spring Boot. Cần dùng API test đang được hỗ trợ ở dự án.

### 20.3. RedisCacheManager statistics

Spring Data Redis `RedisCacheManager` có thể hỗ trợ bật statistics:

```java
RedisCacheManager.builder(connectionFactory)
        .enableStatistics()
        .build();
```

Các thống kê này thường là **local per application instance**, không phải toàn Redis server. Khi kiểm thử nhiều instance, tổng hit ratio phải được tính từ tổng số hit/miss, không lấy trung bình không trọng số của tỷ lệ từng instance.

## 21. Kiểm thử Redis Streams khi consumer lỗi

Nếu ứng dụng dùng Redis Streams, integration test cần thêm những tình huống mà String cache không có.

Ví dụ các lệnh:

```redis
XGROUP CREATE it:orders billing 0 MKSTREAM
XADD it:orders * type CREATED orderId O-42
XREADGROUP GROUP billing consumer-a COUNT 1 STREAMS it:orders >
```

Sau khi consumer nhận entry nhưng chưa ACK, entry có thể nằm trong **Pending Entries List (PEL)** của group.

### 21.1. Test nhận nhưng chưa ACK

1. Tạo Stream và consumer group riêng cho test.
2. `XADD` một entry có `eventId` duy nhất.
3. Consumer A đọc entry nhưng chưa xử lý xong.
4. Kiểm tra `XPENDING` thấy entry còn pending.
5. Gây lỗi consumer hoặc restart worker.
6. Consumer B claim lại sau ngưỡng idle hợp lệ.
7. Xử lý idempotent theo event ID.
8. Chỉ `XACK` khi business side effect đã hoàn thành.

Ví dụ thao tác claim:

```redis
XAUTOCLAIM it:orders billing consumer-b 60000 0-0 COUNT 10
```

Ngưỡng `60000` ms chỉ là ví dụ. Nếu quá thấp, consumer khác có thể chiếm công việc vẫn đang được xử lý; nếu quá cao, phục hồi chậm.

### 21.2. Vì sao chỉ đọc `>` không đủ?

```redis
XREADGROUP GROUP billing consumer-b STREAMS it:orders >
```

Dấu `>` thường đọc các entry **chưa được phát cho consumer group**, không tự lấy toàn bộ pending entry của consumer A đã chết.

Integration test cần xác minh logic pending reclaim và việc xử lý lại không tạo side effect trùng.

### 21.3. Không ACK khi nghiệp vụ chưa thành công

Sai:

```text
Receive -> XACK -> Process -> Error
```

Nếu xử lý lỗi sau ACK, message có thể không còn trong pending queue để retry theo cách mong đợi.

Phù hợp hơn:

```text
Receive -> Process successfully -> XACK
              |
              +--> Error -> retry/dead letter theo policy
```

Bản thân Redis Streams không thay thế transaction giữa Stream và database; vẫn cần idempotency hoặc protocol nhất quán phù hợp.

## 22. Kiểm thử Pub/Sub và keyspace notifications

Redis Pub/Sub thông thường không lưu lịch sử message để phát lại cho subscriber offline.

Một test thực tế:

```text
Subscriber online
    |
Publish message A
    |
Subscriber nhận A
    |
Disconnect subscriber
    |
Publish message B
    |
Reconnect subscriber
    |
Publish message C
    |
Subscriber nhận C
```

Test cần xác nhận:

- Listener nhận message mới khi đang kết nối.
- Listener reconnect hoặc resubscribe được sau sự cố.
- Không giả định message B được phát lại khi subscriber offline.
- Không biến Pub/Sub thành luồng “exactly once” khi không có nguồn bền vững.

### 22.1. Keyspace expiration notifications

Ví dụ channel:

```text
__keyevent@0__:expired
```

Cần bật notification config phù hợp trên Redis test và subscription tương ứng. Nhưng sự kiện `expired` có thể được phát khi Redis **thực sự xóa khóa đã hết hạn**, không nhất thiết chính xác tại thời điểm TTL về 0.

Một test không nên:

```java
Thread.sleep(1000);
assertEquals(1, receivedEvents);
```

mà không xét thời gian dọn key, reconnect hoặc khả năng event bị mất.

### 22.2. Redis Cluster có phạm vi node phát notification

Trong Cluster, keyspace notifications có tính **node-local**. Một listener chỉ subscribe một node có thể không nhận event từ khóa thuộc primary khác.

Test toàn topology cần subscribe đúng các node và kiểm tra sau reshard/failover. Không dùng keyevent Pub/Sub làm cơ chế xử lý bắt buộc không mất sự kiện.

## 23. Kiểm thử Lua script và tính nguyên tử

Một bài test phổ biến là release lock đúng owner.

Script:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Tạo lock:

```redis
SET it:lock:42 owner-A NX PX 5000
```

Các test case:

| Tình huống | Kết quả mong đợi |
|---|---|
| Owner A release khi lock vẫn là A | Xóa lock, trả 1 |
| Owner B release khi lock là A | Không xóa, trả 0 |
| Lock đã hết TTL | Không xóa key của owner khác |
| Owner A timeout, B có lock mới | Script A không xóa lock B |
| Redis lỗi khi gọi script | Cause được giữ, kết quả không bị giả định thành công |
| Script cache mất | Client xử lý `NOSCRIPT` theo capability/quyền |

### 23.1. Vì sao không dùng GET rồi DEL hai lệnh?

Nếu code:

```text
GET lock -> owner-A
    |
Lock A hết hạn
    |
Worker B lấy lock
    |
DEL lock
```

thì A có thể xóa lock của B. Lua script kiểm tra và xóa trong một execution boundary phù hợp giúp tránh race kiểu này.

### 23.2. Giới hạn của bài test

Compare-and-delete chỉ bảo vệ **việc release khóa**. Nó không tự ngăn một worker đã hết lease cập nhật database hoặc hệ thống khác. Nếu yêu cầu tính đúng đắn mạnh hơn, cần kiểm thử fencing token tại resource receiver.

## 24. Kiểm thử Sentinel và Redis Cluster: không dùng một container để kết luận

Một Redis standalone container không có:

- Sentinel quorum.
- Primary promotion giữa nhiều Redis nodes.
- Replica lag trong quá trình failover.
- Redis Cluster 16.384 hash slots.
- `MOVED`/`ASK` khi slot owner đổi.
- `CROSSSLOT` trên nhiều key thực sự thuộc nhiều slots.

### 24.1. Sentinel integration test

Tối thiểu nên có topology phù hợp với kịch bản:

```text
Redis primary P
    |
    +--> Replica R1
    |
    +--> Replica R2

Sentinel S1, S2, S3
```

Test:

1. Ghi/đọc qua Spring Data Redis client có cấu hình Sentinel.
2. Xác nhận primary hiện tại.
3. Trong môi trường test, gây failover.
4. Chờ primary mới được công bố.
5. Chờ chính client Spring Boot reconnect.
6. Kiểm tra ghi và đọc sau failover.
7. Đối chiếu dữ liệu theo RPO của topology.

Replication thông thường bất đồng bộ: một write vừa được primary cũ trả `OK` có thể chưa đến replica được promote. Test phải đánh giá theo hợp đồng dữ liệu, không tự giả định không mất mọi write.

### 24.2. Redis Cluster integration test

Cần nhiều primary và replica, có network addresses client truy cập được.

Test:

- Đọc/ghi key trên nhiều hash slots.
- Thử lệnh multi-key cùng slot bằng hash tag.
- Xác nhận lỗi/cách xử lý khi khác slot.
- Reshard một slot trong môi trường cô lập.
- Quan sát `MOVED`/`ASK` và topology refresh của Lettuce.
- Failover một shard và kiểm tra các shard không bị ảnh hưởng.
- Xác nhận app phục hồi và p99/error rate trở về giới hạn.

Chỉ kết nối thành công tới một seed endpoint **không chứng minh** các node công bố trong Cluster đều có thể truy cập.

### 24.3. Managed Redis staging

Nếu production dùng dịch vụ được quản lý, integration tests cần chạy trên môi trường staging có cùng đặc tính quan trọng:

```text
engine version
cluster mode
TLS/auth
ACL restrictions
allowed commands
failover behavior
quotas
```

Testcontainers standalone là cần thiết nhưng chưa đủ để kiểm chứng những hạn chế cụ thể của provider.

## 25. Fault-injection matrix cho một dự án thực

| Mã | Fault | Cách thử | Điều cần khẳng định |
|---|---|---|---|
| F01 | Key không có | Đọc ID mới | Miss, không error |
| F02 | Value hỏng | Ghi malformed JSON | Giữ serialization cause |
| F03 | TTL hết | TTL ngắn + await | Miss hợp lệ sau expire |
| F04 | WRONGTYPE | String key + HGETALL | Error propagate |
| F05 | Redis timeout | Pause/network delay | Error, không miss |
| F06 | Redis phục hồi | Unpause/reconnect | GET/SET hoạt động lại |
| F07 | Redis unavailable + DB healthy | Test fallback | Có kết quả từ source nếu policy cho phép |
| F08 | Redis unavailable + DB down | Test cả hai lỗi | Không mất thông tin nguyên nhân |
| F09 | Reply mất sau INCR | Fault-injection timing | Không có duplicate effect ngoài contract |
| F10 | Retry storm | Nhiều concurrent requests | Bounded retries và tải |
| F11 | NOPERM | Restricted ACL user | Fail rõ, không retry vô hạn |
| F12 | Script cache miss | `NOSCRIPT` trong test | Load/fallback hoặc báo lỗi đúng |
| F13 | Stream consumer crash | Pending + reclaim | Không mất việc/không xử lý trùng ngoài contract |
| F14 | Pub/Sub disconnect | Publish khi offline | Không giả định replay |
| F15 | Sentinel failover | Đổi primary | Client reconnect, RTO/RPO phù hợp |
| F16 | Cluster reshard | Đổi slot owner | Driver theo redirect |
| F17 | Replica lag | Đọc replica sau write | Không giả định read-your-writes |
| F18 | Cache warm storm | Invalidate nhiều keys | DB load được giới hạn |
| F19 | Engine upgrade | Staging regression | Serialization/commands không regress |
| F20 | Credentials rotation | Rotate ACL/secret | Client reconnect đúng credentials |

Không phải mọi dự án phải chạy tất cả scenarios trong mỗi pull request. Có thể chia smoke/integration/fault-injection/nightly theo chi phí và mức độ quan trọng.

## 26. Tránh flaky tests

### 26.1. Mỗi test sử dụng namespace riêng

```java
String id = "it-" + UUID.randomUUID();
```

Không sử dụng một key cố định như `user:42` cho nhiều test chạy song song.

### 26.2. Không gọi FLUSHALL

Một test không nên dọn bằng:

```redis
FLUSHALL
```

nếu nó không sở hữu toàn Redis deployment. Với container riêng hoàn toàn, hủy container cũng giúp dọn mọi dữ liệu.

Nếu test tái sử dụng Redis, xóa **chính xác những key đã tạo** và đặt TTL dự phòng.

### 26.3. Không phụ thuộc thứ tự test

Một test không được dựa vào việc một test khác đã tạo key trước đó:

```text
Test A creates key
Test B reads key
```

Nếu Test B chạy độc lập hoặc CI đổi thứ tự, nó sẽ thất bại.

Mỗi test phải setup đủ dữ liệu và cleanup phạm vi của chính nó.

### 26.4. Dùng Awaitility thay cho sleep cố định

Sai:

```java
Thread.sleep(5000);
assertTrue(redisRecovered());
```

Tốt hơn:

```java
await()
        .atMost(Duration.ofSeconds(20))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
            assertTrue(redisRecovered());
        });
```

Phép `redisRecovered()` phải đo một điều kiện thực, không chỉ trả `true` vì container process đã chạy.

### 26.5. Không ép test phụ thuộc race ngẫu nhiên

Ví dụ replica có thể bắt kịp primary rất nhanh. Một test bắt buộc replica trả stale data ngay sau write có thể thất bại bất thường.

Nếu cần đo stale reads, phải tạo điều kiện replication lag có kiểm soát và kiểm tra hợp đồng nhất quán, không đòi race tự nhiên lúc nào cũng xảy ra.

## 27. CI pipeline và Docker

Một pipeline hợp lý có thể gồm:

```text
Compile + unit tests
        |
        v
Redis standalone integration tests
        |
        v
Managed staging contract tests (nếu có)
        |
        v
Nightly/controlled fault injection
        |
        v
Báo cáo kết quả và metrics
```

Ví dụ với Maven:

```bash
mvn test
```

Với Gradle:

```bash
./gradlew test
```

Đây là ví dụ lệnh cho dự án dùng build tool tương ứng, không phải yêu cầu chạy lệnh trong STEP 4 soạn tài liệu.

### 27.1. Điều kiện CI

- Runner có Docker/Testcontainers runtime và quyền cần thiết.
- Không hard-code Redis port, sử dụng mapped port.
- Pin Redis image version phục vụ reproducibility.
- Giới hạn CPU/memory và timeout có cân nhắc.
- Không chia sẻ destructive test topology giữa jobs.
- Không ghi secrets/Redis payload vào CI log.
- Dọn container sau run.
- Tách fault-injection tests nếu môi trường CI không cho Docker pause/network controls.

### 27.2. Spring context caching có thể gây lỗi khi container đổi

JUnit/Spring có thể cache `ApplicationContext` giữa những test classes có cấu hình giống nhau. Nếu class trước đã dừng Redis container còn context giữ `LettuceConnectionFactory` với port cũ, class sau có thể vô tình dùng kết nối lỗi.

Cách kiểm soát:

- Tách test classes dùng endpoint khác.
- Dùng `@DirtiesContext` khi cần.
- Quản lý vòng đời container phù hợp với context.
- Đảm bảo các tests không chạy song song trên topology bị gây lỗi.
- Không stop/start container rồi giữ nguyên factory trừ khi endpoint thật sự ổn định.

## 28. Thu thập bằng chứng từ mỗi lần test

Một báo cáo tốt không chỉ viết:

```text
SUCCESS
```

Nó cần ghi:

```text
Scenario ID
Redis image/engine version
Spring Boot / Spring Data Redis version
Driver version
Topology
Fault start time
Fault duration
Observed exception category
Hit/miss/error counter delta
Retry attempts
Recovery duration
Data consistency outcome
Cleanup status
```

Đây là dữ liệu đo có kiểm soát, không gồm raw cache values hoặc credentials.

Ví dụ báo cáo minh họa:

```text
Scenario: F05 network pause
Redis: standalone test container
Fault: pause Redis process
Expected: read throws CacheDependencyException
Observed: cause is Redis timeout
Expected: no cache miss increment
Observed: error incremented
Restore: unpause Redis
Expected: read/write recover before test deadline
Observed: verified by probe
```

Khi chạy thực tế cần thay các chữ `Observed` bằng số liệu và trạng thái đo thật, không bịa kết quả.

### 28.1. Những assertion có giá trị hơn ping

Kiểm tra:

```text
Can read an existing key?
Can write a new key with TTL?
Does serializer decode the value?
Does an API fallback stay inside timeout budget?
Does idempotency prevent duplicate side effects?
```

`PING -> PONG` chỉ cho biết Redis có trả lời một command nhất định, không chứng minh toàn bộ đường nghiệp vụ đã phục hồi.

## 29. Metrics ở Redis server và metrics ứng dụng

Spring Micrometer đo hành vi của service, nhưng còn cần metrics ở server Redis.

Lệnh quan sát trên Redis thử nghiệm:

```redis
INFO memory
INFO stats
INFO keyspace
```

Những counters hữu ích:

```text
used_memory
used_memory_rss
maxmemory
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
```

### 29.1. Redis `keyspace_hits` không phải hit riêng của ProductCacheGateway

Redis keyspace counters thống kê lookup theo các lệnh/hoạt động tại Redis node. Chúng không tự phân biệt `products` với `sessions` hoặc request của hai services khác nhau.

Nếu cần biết cache `products` có tốt không, dựa trên `demo.redis.cache.lookup` của ứng dụng hoặc thống kê cache region được định nghĩa rõ ràng.

### 29.2. Counters tích lũy cần tính rate

Nếu:

```text
12:00 evicted_keys = 1000
12:05 evicted_keys = 1300
```

tốc độ trung bình:

\[
\frac{1300-1000}{300}=1\ \text{key/giây}
\]

Không lấy `1300` làm số key bị loại trong 5 phút. Redis restart có thể reset counters; hệ thống giám sát phải xử lý trường hợp này.

### 29.3. Khi Redis Cluster dùng nhiều node

`INFO` trên một node không đại diện toàn Cluster. Cần quan sát theo primary/shard và xét replica role, reshard/failover.

Đặc biệt, một primary có thể eviction mạnh dù tổng bộ nhớ các node khác còn dư.

## 30. Cách phân tích kết quả khi bài test lỗi

Một bảng triệu chứng hỗ trợ chẩn đoán:

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Test không kết nối Redis container | Docker chưa ready, mapped port sai | Container logs, actual host/port |
| `Connection refused` | Redis chưa chạy hoặc endpoint sai | `getMappedPort`, port/network |
| Timeout sau pause | Redis không trả lời, client chờ | Timeout configuration, client metrics |
| `NOAUTH` | Thiếu/sai authentication | Credential test configuration |
| `NOPERM` | ACL không cấp command/key | Test user policy và command contract |
| `SerializationException` | Dữ liệu không phù hợp serializer | Đọc bằng writer cũ/raw format trong test |
| `WRONGTYPE` | Key có Redis type khác API đang gọi | `TYPE`, namespace/schema |
| `NOSCRIPT` | Script chưa có trên node | Script lifecycle/fallback |
| `CROSSSLOT` | Multi-key không cùng slot | `CLUSTER KEYSLOT` |
| `READONLY` | Lệnh ghi tới replica hoặc primary cũ | Topology/failover |
| Tăng cache misses khi Redis down | Code nuốt exception thành miss | Gateway/error handler |
| Đếm metric sai | Test dùng counter tích lũy hoặc nhiều requests | Delta trước/sau, tag |
| Test TTL flaky | Sleep sát deadline hoặc request chậm | Awaitility, TTL lớn hơn |
| Docker pause không khả dụng | Runtime/permission chưa hỗ trợ | Dùng Toxiproxy/fault proxy |
| Container restart không reconnect | Mapped port đổi, Spring context cũ | Stable endpoint, context lifecycle |
| Redis trở lại nhưng API vẫn lỗi | Driver reconnect hoặc queue chưa ổn định | End-to-end probe và p99 |

Không khắc phục mọi lỗi bằng cách tăng timeout vô hạn. Phải phân biệt **lỗi bài test**, **lỗi cấu hình**, **giới hạn môi trường** và **lỗi ứng dụng**.

## 31. Những sai lầm phổ biến

### Sai lầm 1: Chỉ mock RedisTemplate

Mock giúp unit test nhưng không kiểm chứng serializer, TTL hoặc protocol thật. Cần integration test với Redis server.

### Sai lầm 2: Gọi một Redis standalone container là Sentinel test

Không có Sentinel quorum hoặc replica thì chưa kiểm chứng failover Sentinel.

### Sai lầm 3: Mọi exception Redis được trả về null

Timeout, NOPERM, serializer error không phải cache miss.

### Sai lầm 4: Chỉ assert exception class, bỏ qua cause

Wrapper có thể che mất lỗi gốc. Kiểm tra `getCause()` khi wrapper được tạo.

### Sai lầm 5: Log toàn bộ payload để debug

Gây nguy cơ lộ dữ liệu; log operation alias, category, trace ID và metrics.

### Sai lầm 6: Kiểm tra metric tổng bằng giá trị tuyệt đối

Counter có thể đã tăng từ test khác. So delta và dùng key riêng.

### Sai lầm 7: Dùng Thread.sleep cho TTL và recovery

Tăng flaky, không chứng minh điều kiện đã đúng. Dùng polling có deadline.

### Sai lầm 8: Stop/start Testcontainers rồi giữ port cũ

Container mới có thể dùng mapped port khác, khiến connection factory trỏ sai.

### Sai lầm 9: Pause Redis container dùng chung

Có thể làm test khác thất bại và gây nhiễu kết quả. Dành topology riêng cho fault injection.

### Sai lầm 10: Retry mọi Redis write sau timeout

Một lệnh có thể đã chạy. Cần idempotency hoặc protocol riêng.

### Sai lầm 11: Coi timeout là Redis chưa ghi

Kết quả timeout có thể mơ hồ; xác minh state nghiệp vụ.

### Sai lầm 12: XACK trước khi xử lý Stream xong

Nếu consumer chết sau ACK, công việc có thể không được retry theo cơ chế pending.

### Sai lầm 13: Cho rằng Pub/Sub phát lại message offline

Redis Pub/Sub thông thường không có replay.

### Sai lầm 14: Dùng FLUSHALL trong cleanup test

Có thể xóa dữ liệu ngoài phạm vi nếu endpoint bị cấu hình sai hoặc Redis chia sẻ.

### Sai lầm 15: Không bảo vệ database khi fallback

Redis outage có thể biến thành database outage do thundering herd.

### Sai lầm 16: Dùng một key Cluster để chứng minh routing

Cần nhiều hash slots và các tình huống reshard/failover.

### Sai lầm 17: Chỉ kiểm tra Redis process chạy sau fault

Spring client có thể chưa phục hồi. Cần end-to-end read/write probe.

### Sai lầm 18: Không ghi lại thông số môi trường test

Kết quả khó tái hiện nếu thiếu version, topology, timeout, fault duration.

### Sai lầm 19: Gắn product ID hoặc Redis key vào metric label

Gây cardinality explosion và có thể lộ dữ liệu nhạy cảm.

### Sai lầm 20: Tăng timeout để “sửa” lỗi ACL hoặc WRONGTYPE

Đây là lỗi không thể giải quyết bằng việc chờ lâu hơn.

### Sai lầm 21: Giả định replication không mất write

Redis replication thông thường bất đồng bộ; test phải có RPO và nguồn dữ liệu có thẩm quyền phù hợp.

### Sai lầm 22: Không kiểm thử khôi phục sau serializer/schema migration

Redis vẫn có key nhưng code mới có thể không deserialize được.

### Sai lầm 23: Coi health check PING là kiểm thử đầy đủ

PING không xác nhận cache hit/miss, write, serializer hay idempotency.

### Sai lầm 24: Retry storm sau failover không được đo

Redis mới phục hồi có thể quá tải bởi hàng nghìn client đồng thời retry.

### Sai lầm 25: Đánh giá bài test chỉ từ số assertion xanh

Cần xem latency, error category, recovery duration và tính đúng đắn dữ liệu, không chỉ “test passed”.

## 32. Bài tập mở rộng

### Bài tập A: Metrics và log của lỗi serializer

Thực hiện test malformed JSON. Thêm một `ListAppender` trong môi trường test để kiểm tra một chuỗi giả bí mật không xuất hiện trong application logs.

Tiêu chí:

```text
read_error tăng một đơn vị
getCause() giữ SerializationException
không tăng read_miss
không log raw payload
```

### Bài tập B: Redis outage dưới nhiều request

Chạy đồng thời một số request đọc qua cache, pause Redis rồi khôi phục. Đo:

- Số request timeout.
- p95/p99 latency.
- Retry count.
- Connection pool/pending commands.
- Thời gian phục hồi sau unpause.

Không chạy workload không giới hạn trên CI hoặc Redis dùng chung.

### Bài tập C: Redis fallback và database protection

Tạo fake source hoặc PostgreSQL test container. Giả lập Redis lỗi và giới hạn concurrency fallback.

Xác nhận:

```text
Redis timeout -> fallback counter tăng
Database chỉ nhận lượng tải trong budget
API trả kết quả hoặc lỗi theo contract
```

### Bài tập D: Retry INCR

Thiết kế một fault injector có thể làm mất response sau khi Redis thực thi `INCR`. Cho client retry theo policy và so sánh cách xử lý trước/sau khi có operation ID.

### Bài tập E: Stream pending recovery

Tạo Stream và consumer group test, để một entry pending, sau đó khôi phục bằng claim. Assert side effect nghiệp vụ chỉ xảy ra một lần.

### Bài tập F: Spring Cache annotations

Tạo `@Cacheable("products")`, một nguồn fake đếm số lần load và kiểm tra hit, miss, invalidation theo ID, TTL và lỗi Redis.

### Bài tập G: Managed Redis contract

Tạo bảng những lệnh ứng dụng thực dùng, kiểm tra quyền trên managed staging và thử lỗi `NOPERM`/unknown command mà không gửi lệnh phá hủy vào production.

### Bài tập H: Redis Cluster failover

Đặt các keys trên nhiều slots, gây failover một shard trong Cluster test riêng rồi đo ảnh hưởng tới nhóm keys thuộc shard đó và các shard còn lại.

## 33. Câu hỏi tự kiểm tra

**1. Vì sao unit test mock RedisTemplate chưa đủ?**

Vì mock không chứng minh Redis protocol, serializer, TTL, connection và lỗi của server thật.

**2. Một `GET` trả null có giống timeout không?**

Không. Null thường là key không tồn tại; timeout là lỗi dependency cần xử lý riêng.

**3. Vì sao phải giữ exception cause khi bọc Redis error?**

Để không mất loại lỗi gốc và hỗ trợ phân loại, retry/fallback, điều tra mà wrapper vẫn có message an toàn.

**4. Lỗi deserialize có được coi là cache miss không?**

Không mặc định. Key có thể tồn tại nhưng payload không tương thích với schema/serializer.

**5. Vì sao không nên dùng Thread.sleep cố định để đợi Redis recovery?**

Vì thời gian phục hồi biến động; sleep không chứng minh app đã reconnect. Dùng polling có deadline.

**6. Stop/start Redis Testcontainer có luôn giữ cùng mapped port không?**

Không. Nếu port thay đổi mà connection factory giữ endpoint cũ, ứng dụng có thể vẫn lỗi.

**7. Redis timeout sau INCR chứng minh counter chưa tăng không?**

Không. Lệnh có thể đã thực thi nhưng reply bị mất; retry có thể tăng hai lần.

**8. Khi nào nên fallback từ Redis sang database?**

Khi Redis chỉ là cache và database thực sự là nguồn có thẩm quyền, với policy loại lỗi, timeout và giới hạn tải phù hợp.

**9. Vì sao cần kiểm thử Metrics `hit`, `miss`, `error` riêng?**

Để không tính outage thành cache miss và có thể đo cache effectiveness cùng dependency reliability.

**10. Redis Streams entry pending có tự xuất hiện lại cho consumer mới bằng `>` không?**

Không. Cần cơ chế pending/reclaim phù hợp như `XAUTOCLAIM` và xử lý idempotent.

**11. Pub/Sub subscriber có nhận lại message phát khi offline không?**

Không theo cơ chế Redis Pub/Sub thông thường; không có replay mặc định.

**12. Redis Cluster có cần test nhiều keys/slots không?**

Có. Một key thành công không chứng minh mọi slot routing và topology redirect hoạt động.

**13. Vì sao test dữ liệu hỏng nên dùng Redis thật?**

Vì nó kiểm tra trọn đường đi từ bytes trong Redis qua serializer của Spring Data Redis đến exception ứng dụng.

**14. Khi Redis đã chạy lại, vì sao chưa thể kết luận API phục hồi?**

Vì client có thể chưa reconnect, pool bị nghẽn, script cache thiếu hoặc retries làm dịch vụ vẫn lỗi.

**15. Vì sao không dùng FLUSHALL để cleanup trong integration test?**

Vì có thể xóa dữ liệu ngoài phạm vi test khi endpoint bị cấu hình sai hoặc môi trường không hoàn toàn cô lập.

**16. Nên đo RTO theo mốc nào?**

Theo định nghĩa nghiệp vụ, thường từ sự cố tới khi ứng dụng thực sự phục vụ trở lại trong SLO, không chỉ tới khi Redis process đã chạy.

**17. Vì sao logging full Redis exception có thể nguy hiểm?**

Exception message/stack trace có thể chứa key, value, URI hoặc thông tin hạ tầng nhạy cảm.

**18. Một test được chạy xanh sau failover có chứng minh không mất dữ liệu không?**

Không. Cần đối chiếu write sequence/revisions và đánh giá theo RPO của topology.

**19. Nếu Redis trả NOPERM, exponential backoff có làm lệnh hợp lệ không?**

Không. Đây thường là vấn đề phân quyền/cấu hình, cần sửa contract và ACL.

**20. Testcontainers standalone có thay thế được managed Redis staging không?**

Không hoàn toàn. Managed service có thể khác TLS, ACL, engine version, topology, quotas và command set.

## 34. Ghi nhớ

- **Kiểm thử tích hợp Redis phải chạy qua Redis thật**, không chỉ mock những API của Spring Data Redis.
- **Tách happy path, lỗi và recovery path:** hit, miss, TTL, malformed payload, connection timeout, reconnect và tính đúng đắn sau retry.
- **Cache miss không phải Redis error.** Ghi metrics `hit`, `miss`, `error` riêng.
- **Giữ original cause** khi bọc lỗi; response/log không nên phát tán key, value hoặc raw exception message.
- **Dùng Testcontainers và mapped port động** cho kiểm thử standalone, bảo đảm test không trỏ Redis production.
- **Dùng Awaitility/condition polling với deadline**, không chỉ `Thread.sleep`, để quan sát expiration và phục hồi.
- **Fault-injection cần môi trường độc lập.** Pause/unpause hoặc proxy giữ endpoint ổn định; không stop/start container rồi giả định port giữ nguyên.
- **Timeout sau lệnh ghi có thể có kết quả mơ hồ.** Retry phải xét idempotency/operation ID.
- **Fallback chỉ dùng khi có nguồn có thẩm quyền và có giới hạn tải.** Không để Redis outage kéo theo database overload.
- **Redis Streams cần pending/reclaim và ACK đúng lúc; Pub/Sub không có replay.**
- **Sentinel/Cluster cần topology integration tests riêng**; một Redis container không kiểm chứng failover hoặc hash-slot routing.
- **Quan sát end-to-end:** exception category, metrics, latency, retry, RTO/RPO và tính đúng đắn dữ liệu sau sự cố.
- **Tạo test lặp lại được:** namespace riêng, TTL, cleanup có giới hạn, không `FLUSHALL`, ghi nhận version/topology và môi trường.

### Tài liệu tham khảo

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Data Redis — Connection modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html).
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html).
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Testcontainers Java — Documentation](https://java.testcontainers.org/).
- [Testcontainers — Redis Module](https://java.testcontainers.org/modules/redis/).
- [Awaitility — Project](https://github.com/awaitility/awaitility).
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/).
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/).
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/).
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
