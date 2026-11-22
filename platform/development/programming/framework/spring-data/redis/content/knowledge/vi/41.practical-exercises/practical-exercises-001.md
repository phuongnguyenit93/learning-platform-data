# Xây dựng cache cho chức năng tra cứu dữ liệu với Spring Data Redis

## 1. Mục tiêu thực hành

Trong bài thực hành này, chúng ta xây dựng một API tra cứu sản phẩm bằng **Spring Boot, Spring Data JPA và Spring Data Redis**. Dữ liệu sản phẩm được lưu trong database; Redis lưu bản sao để giảm số truy vấn database và cải thiện tốc độ đọc.

Ứng dụng minh họa hỗ trợ:

- `GET /api/products/{id}`: tra cứu thông tin sản phẩm theo ID.
- `PUT /api/products/{id}/price`: cập nhật giá sản phẩm.
- **Cache hit**: lấy kết quả tra cứu từ Redis mà không gọi repository.
- **Cache miss**: truy vấn database, trả về DTO và ghi kết quả vào Redis với TTL.
- **Invalidation**: xóa cache của sản phẩm đã cập nhật để những lần đọc sau lấy dữ liệu mới.
- **Quan sát**: kiểm tra key Redis, TTL và phân biệt cache hit/miss.
- **Kiểm thử**: dùng JUnit, Spring Test và Testcontainers để chạy Redis thực trong môi trường test.

Mục tiêu không phải chỉ tạo được key Redis mà là hiểu **đường đi dữ liệu, nguồn dữ liệu chuẩn, vòng đời cache, các giới hạn consistency và cách kiểm chứng hành vi**.

> **Nguyên tắc quan trọng:** Trong ví dụ này, **database là source of truth**. Redis chỉ là bản sao có thể tái tạo. Cache miss hoặc mất cache không đồng nghĩa mất sản phẩm.

## 2. Bài toán và tiêu chí hoàn thành

Giả sử bảng `products` có hai sản phẩm:

| ID | Tên | Giá |
| ---: | --- | ---: |
| 1 | Spring Data Redis Handbook | 129.000 |
| 2 | Java Persistence Guide | 159.000 |

Kỳ vọng:

```text
Lần 1: GET /api/products/1
        -> Redis miss
        -> SELECT FROM products WHERE id = 1
        -> lưu Redis với TTL 5 phút
        -> HTTP 200

Lần 2: GET /api/products/1
        -> Redis hit
        -> không SELECT lại
        -> HTTP 200

PUT /api/products/1/price
        -> UPDATE database
        -> commit thành công
        -> xóa cache sản phẩm 1

Lần 3: GET /api/products/1
        -> Redis miss
        -> SELECT giá mới
        -> cache lại
        -> HTTP 200
```

Tiêu chí kỹ thuật:

1. HTTP response trả JSON có `id`, `name`, `price`.
2. Sản phẩm không tồn tại trả HTTP 404.
3. Redis key có namespace rõ ràng, tránh đè lên các loại dữ liệu khác.
4. Cache entry có TTL.
5. Cập nhật giá không giữ lại cache cũ vô thời hạn.
6. Có bài kiểm thử chứng minh lần đọc thứ hai không truy vấn repository.
7. Có bài kiểm thử xác nhận Redis thực sự lưu DTO và TTL.
8. Có chính sách rõ khi Redis không khả dụng.

Các giá trị cấu hình trong ví dụ phù hợp **môi trường học tập**, không phải một template sản xuất dùng nguyên xi.

## 3. Kiến trúc cache-aside

**Cache-aside** (lazy-loading cache) là chiến lược phổ biến cho tra cứu:

```text
                    Client
                      |
                      v
          GET /api/products/{id}
                      |
                      v
             ProductLookupService
                      |
                Redis Cache
                 /       \
                /         \
             HIT          MISS
              |             |
              v             v
         ProductView    ProductRepository
              |             |
              |             v
              |         Database
              |             |
              |             v
              |         ProductView
              |             |
              |         SET cache + TTL
              |             |
              +-------------+
                      |
                      v
                 HTTP 200 JSON
```

**Đặc điểm:**

- Redis không tự nạp dữ liệu từ database.
- Ứng dụng quyết định khi nào đọc nguồn chuẩn và khi nào ghi cache.
- TTL giới hạn thời gian một snapshot tồn tại nếu không bị xóa trước đó.
- Cache entry có thể biến mất sớm nếu Redis bật eviction.
- Cập nhật database cần có kế hoạch invalidate hoặc cập nhật cache.

Trong Spring, có thể triển khai cache-aside bằng `RedisTemplate` hoặc bằng **Spring Cache Abstraction** (`@Cacheable`, `@CacheEvict`, `RedisCacheManager`). Bài này dùng Spring Cache cho phiên bản chạy được, rồi giới thiệu cách dùng `RedisTemplate` khi cần kiểm soát chi tiết.

## 4. Cấu trúc project

Dùng Java 21, Spring Boot 3.5.x và Maven. Cấu trúc ví dụ:

```text
redis-lookup-demo/
├── pom.xml
├── compose.yaml
├── src/
│   ├── main/
│   │   ├── java/com/example/lookup/
│   │   │   ├── RedisLookupApplication.java
│   │   │   ├── Product.java
│   │   │   ├── ProductRepository.java
│   │   │   ├── ProductView.java
│   │   │   ├── ProductLookupService.java
│   │   │   ├── ProductCommandService.java
│   │   │   ├── ProductChangedEvent.java
│   │   │   ├── ProductCacheInvalidator.java
│   │   │   ├── ProductCacheConfig.java
│   │   │   ├── ProductController.java
│   │   │   ├── ChangePriceRequest.java
│   │   │   ├── ProductNotFoundException.java
│   │   │   └── DemoData.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/
│       └── java/com/example/lookup/
│           └── ProductCacheIntegrationTest.java
```

Để dễ thực hành, các Java classes được đặt chung một package. Dự án thật có thể tổ chức theo `domain`, `application`, `infrastructure` và `web` khi quy mô tăng.

H2 là **database in-memory dành cho bài học**. Production cần dùng database có persistence, migrations, transaction policy và backup thích hợp.

## 5. Khởi tạo dependencies

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>redis-lookup-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Phiên bản Spring Boot được pin để ví dụ có cấu trúc xác định. Khi áp dụng vào repository đang tồn tại, dùng BOM và phiên bản đã được dự án xác nhận; không đổi Spring Boot hoặc Redis version chỉ để sao chép bài học.

Các dependency có vai trò:

| Dependency | Mục đích |
| --- | --- |
| `starter-web` | REST Controller, JSON |
| `starter-validation` | Kiểm tra input cập nhật giá |
| `starter-data-jpa` | Lưu sản phẩm bằng JPA |
| `starter-data-redis` | RedisConnectionFactory/Lettuce |
| `starter-cache` | Spring Cache annotations/CacheManager |
| `starter-actuator` | Health, metrics, telemetry |
| `h2` | Database demo |
| `starter-test` | JUnit, Mockito, AssertJ, Spring Test |
| `testcontainers:junit-jupiter` | Quản lý Redis test container |

## 6. Khởi động Redis cho môi trường thực hành

File `compose.yaml`:

```yaml
services:
  redis:
    image: redis:7.4.2-alpine
    command:
      - redis-server
      - --appendonly
      - "no"
      - --maxmemory
      - 256mb
      - --maxmemory-policy
      - allkeys-lru
    ports:
      - "127.0.0.1:6379:6379"
```

Khởi động:

```bash
docker compose up -d
```

Kiểm tra:

```bash
docker compose exec redis redis-cli PING
```

Kỳ vọng:

```text
PONG
```

Redis trên chỉ dành cho **demo cache có thể tái tạo**:

- Bind port tới localhost để tránh mở Redis không xác thực cho mạng ngoài.
- Tắt AOF để đơn giản hóa bài học; đây không phải lựa chọn mặc định cho mọi loại dữ liệu.
- `allkeys-lru` cho phép cache entries bị eviction khi thiếu RAM.
- Không lưu session, lock, idempotency hoặc thông tin nghiệp vụ quan trọng trên Redis demo này.

**Trong production**, cần authentication/ACL, TLS/network isolation, secrets, topology, memory headroom, backup nếu cần và giám sát tài nguyên.

Nếu máy đã có Redis tại port 6379, điều chỉnh port mapping và cấu hình Spring cho phù hợp.

## 7. Cấu hình Spring Boot

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  application:
    name: redis-lookup-demo

  datasource:
    url: jdbc:h2:mem:products;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ""

  jpa:
    open-in-view: false
    hibernate:
      ddl-auto: create-drop
    show-sql: true

  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s

  cache:
    type: redis

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

logging:
  level:
    org.hibernate.SQL: DEBUG
```

Giải thích:

- `spring.datasource`: H2 database chỉ tồn tại trong lần chạy demo.
- `ddl-auto: create-drop`: tạo và xóa schema để thực hành, **không dùng nguyên xi cho production**.
- `spring.data.redis`: địa chỉ Redis server.
- `spring.cache.type: redis`: chọn Redis cache provider cho Spring Cache.
- `show-sql`/`org.hibernate.SQL`: hỗ trợ quan sát lần nào có SQL `SELECT`.
- Actuator được bật giới hạn một số endpoints để xem health/metrics trong demo.

Không mở H2 console, Actuator hoặc Redis port ra Internet chỉ để tiện thử nghiệm.

## 8. Kích hoạt caching

Class chạy ứng dụng:

```java
package com.example.lookup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@EnableCaching
public class RedisLookupApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            RedisLookupApplication.class, args
        );
    }
}
```

`@EnableCaching` kích hoạt infrastructure xử lý `@Cacheable`, `@CachePut`, `@CacheEvict` trong cơ chế Spring Cache.

Điều quan trọng: với chế độ proxy mặc định, lời gọi method phải đi qua Spring-managed proxy để caching advice có hiệu lực. Nếu tự `new ProductLookupService(...)` hoặc gọi `this.findById(...)` nội bộ, không nên mặc định cache annotation được thực thi.

## 9. Tạo Entity Product

File `Product.java`:

```java
package com.example.lookup;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(
        nullable = false,
        precision = 18,
        scale = 2
    )
    private BigDecimal price;

    protected Product() {
    }

    public Product(
            String name,
            BigDecimal price) {
        this.name = name;
        changePrice(price);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null
                || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must be non-negative"
            );
        }

        this.price = newPrice;
    }
}
```

`BigDecimal` phù hợp hơn `double` khi biểu diễn số tiền ở các ứng dụng cần tránh sai số nhị phân. Tuy nhiên demo này vẫn chưa triển khai currency, precision/rounding policy hoặc nghiệp vụ thanh toán.

Với JPA, constructor không tham số có visibility `protected` giúp ORM tạo entity.

## 10. Tạo ProductRepository

File `ProductRepository.java`:

```java
package com.example.lookup;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Spring Data JPA tạo implementation tự động. Đây là đường đọc **nguồn dữ liệu chuẩn** khi Redis cache miss.

Repository không nên biết Redis prefix hoặc TTL. Nếu muốn thay H2 bằng PostgreSQL, thay cấu hình JDBC/driver và migrations; phần cache policy vẫn có thể giữ nguyên.

## 11. Tạo DTO dùng cho API và cache

File `ProductView.java`:

```java
package com.example.lookup;

import java.math.BigDecimal;

public record ProductView(
    Long id,
    String name,
    BigDecimal price
) {
    public static ProductView from(Product product) {
        return new ProductView(
            product.getId(),
            product.getName(),
            product.getPrice()
        );
    }
}
```

Tại sao **cache DTO** thay vì JPA entity?

- DTO không mang Hibernate lazy proxies.
- Hợp đồng JSON rõ ràng, có thể versioning.
- Không vô tình serialize relationship graph quá lớn.
- Tránh đưa persistence internals vào Redis.
- Giảm nguy cơ phụ thuộc vào entity lifecycle.
- Tạo boundary rõ giữa domain persistence và API representation.

Nếu `ProductView` đổi schema, cần xét giá trị cache do phiên bản cũ ghi. Trong bài này, Redis key prefix chứa `v1` để có thể đổi namespace khi cần.

## 12. Tạo dữ liệu mẫu

File `DemoData.java`:

```java
package com.example.lookup;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DemoData {

    @Bean
    CommandLineRunner seedProducts(
            ProductRepository repository) {

        return args -> {
            if (repository.count() == 0) {
                repository.save(new Product(
                    "Spring Data Redis Handbook",
                    new BigDecimal("129000.00")
                ));

                repository.save(new Product(
                    "Java Persistence Guide",
                    new BigDecimal("159000.00")
                ));
            }
        };
    }
}
```

Trong một H2 database trống và auto-increment bắt đầu từ 1, hai sản phẩm thường nhận ID 1 và 2. Kết quả chính xác phụ thuộc dữ liệu đã tồn tại và database strategy; không dựa vào ID 1 cố định khi triển khai trên production.

Seed bằng `CommandLineRunner` dùng cho demo. Trong project thực, dùng Flyway/Liquibase hoặc dữ liệu phát triển được quản lý riêng.

## 13. Cấu hình RedisCacheManager

Spring Boot có thể tự tạo `RedisCacheManager`, nhưng chúng ta khai báo tường minh để hiểu ba thành phần:

1. **Cache name/key namespace**.
2. **TTL**.
3. **Key/value serialization**.

File `ProductCacheConfig.java`:

```java
package com.example.lookup;

import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductCacheConfig {

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory,
            ObjectMapper mapper) {

        Jackson2JsonRedisSerializer<ProductView>
            productSerializer =
                new Jackson2JsonRedisSerializer<>(
                    mapper,
                    ProductView.class
                );

        RedisCacheConfiguration productConfig =
            RedisCacheConfiguration
                .defaultCacheConfig()
                .computePrefixWith(
                    cacheName ->
                        "lookup-demo:v1:"
                            + cacheName
                            + "::"
                )
                .serializeKeysWith(
                    RedisSerializationContext
                        .SerializationPair
                        .fromSerializer(
                            new StringRedisSerializer()
                        )
                )
                .serializeValuesWith(
                    RedisSerializationContext
                        .SerializationPair
                        .fromSerializer(productSerializer)
                )
                .entryTtl(Duration.ofMinutes(5))
                .disableCachingNullValues();

        return RedisCacheManager
            .builder(factory)
            .cacheDefaults(productConfig)
            .withInitialCacheConfigurations(
                Map.of("productLookup", productConfig)
            )
            .build();
    }
}
```

### Tại sao dùng serializer kiểu ProductView?

`Jackson2JsonRedisSerializer<ProductView>` có kiểu đích cụ thể. Như vậy không cần bật deserialization đa hình rộng cho mọi type khi cache này chỉ chứa `ProductView`.

**Giới hạn của ví dụ:** `productConfig` được dùng làm defaults cho CacheManager này. Nếu về sau tạo thêm cache cho kiểu DTO khác, không tái sử dụng serializer `ProductView` một cách mù quáng; hãy cấu hình serializer riêng hoặc phân tách cache configurations phù hợp.

### Key Redis dự kiến

Khi gọi:

```java
findById(1L)
```

với cache name `productLookup`, key định dạng chuỗi thường là:

```text
lookup-demo:v1:productLookup::1
```

`v1` biểu thị phiên bản namespace, không phải Redis protocol version. Nếu thay đổi wire schema không tương thích, có thể chuyển sang `v2` để tránh đọc dữ liệu cache cũ.

### Các lưu ý về serializer

- Đảm bảo cả reader và writer dùng schema tương thích.
- Không cache trực tiếp entity/proxy nếu không có nhu cầu cụ thể.
- Không mở default typing đa hình không giới hạn cho payload không tin cậy.
- Đặt TTL dương theo nhu cầu freshness.
- Khi custom `CacheManager` được tạo, không mặc định mọi `spring.cache.redis.*` property sẽ tự áp dụng lên cấu hình của bạn.

## 14. Service đọc với @Cacheable

File `ProductLookupService.java`:

```java
package com.example.lookup;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductLookupService {

    private final ProductRepository repository;

    public ProductLookupService(
            ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    @Cacheable(
        cacheNames = "productLookup",
        key = "#p0",
        unless = "#result == null"
    )
    public ProductView findById(Long id) {

        Product product = repository.findById(id)
            .orElseThrow(() ->
                new ProductNotFoundException(id)
            );

        return ProductView.from(product);
    }
}
```

Giải thích:

| Thành phần | Ý nghĩa |
| --- | --- |
| `@Cacheable` | Trước khi chạy body, Spring Cache kiểm tra key cache |
| `cacheNames="productLookup"` | Chọn cache cấu hình ở `RedisCacheManager` |
| `key="#p0"` | Lấy tham số đầu tiên làm key; tránh phụ thuộc tên parameter |
| `unless="#result == null"` | Không cache kết quả `null` |
| `@Transactional(readOnly=true)` | Đọc dữ liệu qua transaction read-only khi body chạy |
| `repository.findById` | Chỉ được gọi khi cache miss |
| `ProductView.from` | Cache DTO thay vì JPA entity |

**Đặc điểm:** Trên cache hit, proxy có thể trả DTO từ Redis **mà không thực thi body method**. Vì vậy nếu log `repository.findById` nằm trong method, log đó không xuất hiện ở lần hit.

### Nếu sản phẩm không tồn tại?

Method ném exception `ProductNotFoundException`. Spring Cache không cache một exception như một `ProductView` thành công; lần truy vấn tiếp theo tới ID không tồn tại sẽ lại gọi database.

Đó là chính sách **không negative-cache**. Nếu workload có rất nhiều ID không tồn tại, có thể thiết kế negative caching riêng với TTL ngắn và invalidation phù hợp.

## 15. Exception trả HTTP 404

File `ProductNotFoundException.java`:

```java
package com.example.lookup;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class ProductNotFoundException
        extends RuntimeException {

    public ProductNotFoundException(Long id) {
        super("Product not found: " + id);
    }
}
```

Khi repository không tìm thấy ID, Spring MVC trả HTTP 404.

Trong ứng dụng production, có thể dùng `@RestControllerAdvice` để chuẩn hóa error response, correlation ID và nội dung công bố cho client, tránh lộ thông tin nội bộ.

## 16. Vì sao cập nhật dữ liệu cần invalidation?

Giả sử Redis đã có:

```text
lookup-demo:v1:productLookup::1
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 129000.00
}
```

Database sau đó được cập nhật thành giá `139000.00`. Nếu không xóa hoặc refresh cache:

```text
GET /api/products/1
    -> Redis hit
    -> vẫn trả 129000.00
```

TTL 5 phút chỉ giới hạn khoảng dữ liệu có thể cũ, không tạo đồng bộ tức thời.

Có ba chiến lược chính:

- **Evict-on-write:** cập nhật database rồi xóa cache; lần đọc kế tiếp nạp lại.
- **Update-on-write:** cập nhật cache bằng giá trị mới khi database đổi.
- **Versioned cache:** dùng version/ETag hoặc key version, thường phức tạp hơn nhưng có ích cho concurrency.

Bài thực hành chọn **evict-on-write sau commit**.

## 17. DTO cập nhật giá

File `ChangePriceRequest.java`:

```java
package com.example.lookup;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;

public record ChangePriceRequest(

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price

) {
}
```

Để nhất quán, entity còn kiểm tra `price` không âm. DTO validation chỉ có hiệu lực khi lời gọi từ Controller dùng `@Valid`; service vẫn cần bảo vệ các invariant quan trọng khi được gọi từ nơi khác.

## 18. Sự kiện thay đổi sản phẩm

File `ProductChangedEvent.java`:

```java
package com.example.lookup;

public record ProductChangedEvent(Long id) {
}
```

Event chỉ mang ID cần invalidation, tránh đưa cả entity JPA hoặc dữ liệu nhạy cảm qua event không cần thiết.

## 19. Service cập nhật giá trong database transaction

File `ProductCommandService.java`:

```java
package com.example.lookup;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public ProductView changePrice(
            Long id,
            BigDecimal newPrice) {

        Product product = repository.findById(id)
            .orElseThrow(() ->
                new ProductNotFoundException(id)
            );

        product.changePrice(newPrice);

        events.publishEvent(
            new ProductChangedEvent(id)
        );

        return ProductView.from(product);
    }
}
```

Vì entity đang được JPA quản lý trong transaction, dirty checking có thể thực hiện update lúc flush/commit. `@Transactional` đảm bảo thao tác ORM theo giao dịch của datasource tương ứng.

**Quan trọng:** `publishEvent` ở đây không tự gửi Redis event bền vững. Đó là event nội bộ trong JVM. Listener ở bước tiếp theo được đăng ký chạy khi transaction đã commit.

## 20. Xóa cache sau transaction commit

File `ProductCacheInvalidator.java`:

```java
package com.example.lookup;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(
            CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void evictAfterCommit(
            ProductChangedEvent event) {

        Cache cache =
            cacheManager.getCache("productLookup");

        if (cache == null) {
            throw new IllegalStateException(
                "Missing productLookup cache"
            );
        }

        cache.evict(event.id());
    }
}
```

Tại sao dùng `AFTER_COMMIT`?

```text
BEGIN database transaction
       |
       v
UPDATE Product entity
       |
       v
publish ProductChangedEvent
       |
       v
COMMIT succeeds
       |
       v
@TransactionalEventListener(AFTER_COMMIT)
       |
       v
Redis cache evict(productId)
```

Nếu database transaction rollback, listener `AFTER_COMMIT` không thực hiện invalidation như một successful update.

### Có bảo đảm database và Redis đồng bộ tuyệt đối không?

**Không.** Sau khi database commit, process vẫn có thể crash trước khi Redis eviction thực hiện. Redis có thể không truy cập được tại thời điểm listener chạy. Một slow cache read cũng có thể điền lại snapshot cũ sau eviction.

Với tra cứu thông thường, TTL 5 phút có thể là lớp giới hạn stale data chấp nhận được. Với consistency yêu cầu nghiêm ngặt, cần cơ chế như **transactional outbox**, version checking hoặc invalidation có khả năng retry/đối soát.

**Một lỗi listener sau commit có thể được phản ánh tới caller dù database đã commit.** Không được retry cập nhật không idempotent theo giả định “API lỗi = DB chưa đổi”. Đó là lý do production cần error handling và reconciliation rõ ràng.

## 21. Tạo REST Controller

File `ProductController.java`:

```java
package com.example.lookup;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductLookupService lookup;
    private final ProductCommandService commands;

    public ProductController(
            ProductLookupService lookup,
            ProductCommandService commands) {
        this.lookup = lookup;
        this.commands = commands;
    }

    @GetMapping("/{id}")
    public ProductView get(
            @PathVariable Long id) {
        return lookup.findById(id);
    }

    @PutMapping("/{id}/price")
    public ProductView changePrice(
            @PathVariable Long id,
            @Valid @RequestBody ChangePriceRequest request) {

        return commands.changePrice(
            id,
            request.price()
        );
    }
}
```

`@Validated` và `ResponseEntity` không cần thiết cho đoạn Controller đơn giản này; nếu IDE báo unused import, có thể bỏ chúng khi triển khai. Ở đây `@Valid` đủ để kiểm tra body.

Lưu ý REST API không phải nơi trực tiếp tạo cache key. Controller gọi service; caching behavior nằm ở application/service layer.

## 22. Chạy thử ứng dụng

Khởi động Redis:

```bash
docker compose up -d
```

Chạy Spring Boot:

```bash
mvn spring-boot:run
```

Với H2 mới, `DemoData` tạo dữ liệu mẫu.

Tra cứu:

```bash
curl -i http://localhost:8080/api/products/1
```

Kết quả ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"name":"Spring Data Redis Handbook","price":129000.00}
```

Gọi lại:

```bash
curl -i http://localhost:8080/api/products/1
```

Lần đầu nên có SQL `SELECT` cho sản phẩm; lần thứ hai có thể không có thêm `SELECT` vì Spring Cache trả value Redis. Những câu SQL từ initialization, transaction khác hoặc Actuator không nên nhầm với chính lệnh tra cứu.

Để chứng minh chính xác không đọc repository ở lần thứ hai, dùng integration test ở phần sau thay vì chỉ đọc log bằng mắt.

## 23. Xem key trong Redis

Mở CLI:

```bash
docker compose exec redis redis-cli
```

Trong Redis CLI:

```redis
SCAN 0 MATCH lookup-demo:v1:productLookup::* COUNT 100
```

Key kỳ vọng khi đã tra cứu sản phẩm ID 1:

```text
lookup-demo:v1:productLookup::1
```

Đọc raw JSON:

```redis
GET lookup-demo:v1:productLookup::1
```

Kiểm tra TTL:

```redis
TTL lookup-demo:v1:productLookup::1
```

Hoặc TTL theo milliseconds:

```redis
PTTL lookup-demo:v1:productLookup::1
```

Diễn giải giá trị `TTL`:

| Kết quả | Ý nghĩa |
| ---: | --- |
| Số dương | Key còn TTL theo seconds |
| `-1` | Key tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại |
| `0` | Thời gian còn lại rất ngắn theo đơn vị seconds |

Sau một lần tra cứu mới, TTL thường xấp xỉ 300 giây và giảm dần. Không đòi chính xác 300 ở mọi thời điểm do latency và thời gian trôi.

**Không dùng `KEYS *` để quét toàn bộ Redis production khi keyspace lớn**. Trong ví dụ chỉ có vài key, nhưng vẫn dùng `SCAN` để hình thành thói quen tốt.

## 24. Kiểm chứng cache hit bằng SQL và Redis

Thực hiện:

```text
1. Mở logs Spring Boot.
2. GET /api/products/1 lần đầu.
3. Ghi nhận SELECT từ JPA.
4. Redis xuất hiện key và TTL.
5. GET /api/products/1 lần hai.
6. So sánh số SELECT của truy vấn tương ứng.
```

Nếu lần thứ hai vẫn gọi database, cần xem:

- `@EnableCaching` đã bật chưa?
- Method được gọi qua Spring proxy chưa?
- Cache name trong annotation có khớp CacheManager không?
- `@Cacheable` nằm ở public method phù hợp chưa?
- Cache key có giống ở hai lần gọi không?
- Redis có đang eviction entry hoặc TTL hết quá nhanh không?
- `ProductView` serializer có lỗi không?
- Custom `CacheManager` có được Spring dùng không?

Đừng mặc định lỗi nằm ở Redis server; một cấu hình AOP/caching chưa bật cũng làm ứng dụng luôn đọc database.

## 25. Cập nhật giá và quan sát invalidation

Gọi:

```bash
curl -i \
  -X PUT http://localhost:8080/api/products/1/price \
  -H "Content-Type: application/json" \
  -d '{"price":139000.00}'
```

Kết quả minh họa:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 139000.00
}
```

Kiểm tra Redis ngay sau update commit:

```redis
EXISTS lookup-demo:v1:productLookup::1
```

Kỳ vọng thông thường: `0`, vì listener đã evict cache sau database commit.

Gọi lại:

```bash
curl http://localhost:8080/api/products/1
```

Lần đọc này có thể truy vấn database và cache kết quả mới:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 139000.00
}
```

Đây là hành vi **evict-on-write**: không đẩy value mới trực tiếp vào cache, mà để lần đọc kế tiếp làm mới.

Trong production, các trường hợp crash giữa commit và eviction hoặc race với in-flight cache miss cần biện pháp bổ sung nếu chấp nhận stale data là không đủ.

## 26. Truy vấn sản phẩm không tồn tại

Gọi:

```bash
curl -i http://localhost:8080/api/products/999999
```

Kỳ vọng HTTP 404.

Vì method `findById` ném exception khi repository trả empty, không có `ProductView` để cache. Truy vấn ID không tồn tại lần sau tiếp tục đi tới database.

Điểm mạnh: tránh giữ một kết quả “không có sản phẩm” quá lâu nếu sau đó sản phẩm được tạo.

Điểm yếu: với ID không tồn tại bị truy vấn rất nhiều, database có thể chịu tải. Khi đó có thể cân nhắc **negative cache** với TTL ngắn, nhưng cần thiết kế value biểu diễn rõ tình trạng không tồn tại và invalidation khi entity được tạo.

Không nên dùng một null value không kiểm soát nếu cache manager đã `disableCachingNullValues()`.

## 27. TTL và eviction khác nhau

TTL 5 phút không phải cam kết key phải sống ít nhất 5 phút.

Redis demo đang dùng:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

Nếu Redis thiếu RAM, key có thể bị **eviction trước TTL**. Khi đó ứng dụng thấy cache miss, đọc database và cache lại.

Các nguyên nhân cache miss có thể gồm:

- Chưa từng nạp key.
- Key hết TTL.
- Key bị eviction.
- Application đã evict khi cập nhật dữ liệu.
- Cache namespace/version đổi.
- Redis restart và không có persistence của cache.
- Redis failover dẫn đến khác biệt trạng thái.
- Key bị xóa bởi thao tác vận hành.

Redis `expired_keys` và `evicted_keys` trong `INFO stats` giúp phân biệt hiện tượng expiration và memory eviction trên server.

## 28. TTL nên chọn như thế nào?

Không có một TTL tối ưu cho mọi loại dữ liệu.

| Loại dữ liệu | Câu hỏi quyết định TTL |
| --- | --- |
| Product description | Có thể stale vài phút không? |
| Product price | Giá phải được xác nhận ở bước giao dịch nào? |
| Product inventory | Độ mới cần cao hơn hay phải đọc nguồn chuẩn khi đặt hàng? |
| Category metadata | Tần suất thay đổi thấp đến mức nào? |
| Public configuration | Bao lâu thì thay đổi phải có hiệu lực? |
| Search results | Bộ lọc/phân trang và chi phí recompute ra sao? |

Bài dùng **5 phút** chỉ để thực hành.

Nếu giá dùng để thanh toán, **không nên coi cache price là nguồn có thẩm quyền cuối cùng**. Checkout phải xác nhận giá và tồn kho bằng transaction/business rules phù hợp ở nguồn chuẩn.

TTL là một lớp bảo vệ stale-data; không thay transaction/invalidation đúng.

## 29. Cấu hình TTL cho nhiều cache khác nhau

Khi ứng dụng có nhiều cache:

```text
productLookup     -> 5 phút
categoryLookup    -> 30 phút
featureFlags      -> 1 phút
```

Có thể dùng `RedisCacheManager` với các `RedisCacheConfiguration` theo cache name. Ví dụ ý tưởng:

```java
Map<String, RedisCacheConfiguration> settings =
    Map.of(
        "productLookup",
        baseConfig.entryTtl(Duration.ofMinutes(5)),
        "categoryLookup",
        baseConfig.entryTtl(Duration.ofMinutes(30))
    );
```

**Không tái sử dụng `ProductView` serializer cho `CategoryView` nếu hai cache chứa những type khác nhau.** Mỗi cache cần serializer/schema phù hợp hoặc một cơ chế value serialization được quản lý an toàn và có test compatibility.

Việc có nhiều TTL không tạo memory quota riêng cho từng cache. Redis eviction policy vẫn áp dụng ở cấp server/instance.

## 30. Cách làm tương đương bằng RedisTemplate

Nếu không muốn phụ thuộc Spring Cache annotation, có thể viết cache-aside tường minh.

Ví dụ một service lưu JSON string:

```java
package com.example.lookup;

import java.time.Duration;
import java.util.Optional;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.StringRedisTemplate;

public class ExplicitProductCache {

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public ExplicitProductCache(
            StringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public Optional<ProductView> find(Long id) {
        String json =
            redis.opsForValue().get(key(id));

        if (json == null) {
            return Optional.empty();
        }

        try {
            return Optional.of(
                mapper.readValue(json, ProductView.class)
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Invalid cached product JSON", ex
            );
        }
    }

    public void put(
            ProductView value,
            Duration ttl) {

        try {
            String json = mapper.writeValueAsString(value);
            redis.opsForValue().set(
                key(value.id()),
                json,
                ttl
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot serialize cached product", ex
            );
        }
    }

    public void evict(Long id) {
        redis.delete(key(id));
    }

    private static String key(Long id) {
        return "lookup-demo:manual:v1:product:" + id;
    }
}
```

Lớp trên là **phương án thay thế** cho phần caching bằng annotation, không cần cài đồng thời để hoàn thành demo cơ bản.

Ưu điểm:

- Có thể kiểm soát chính xác key/value/TTL.
- Dễ biểu diễn logic cache-aside với nhiều điều kiện.
- Dễ tách thành port `ProductCache` để unit test business service.
- Có thể dùng Lua/multi-key command khi use case cần.

Nhược điểm:

- Code ứng dụng dài hơn.
- Phải tự viết policy cache miss, error mapping, metrics và invalidation.
- Có nguy cơ dùng serializer/prefix không thống nhất giữa các service.

## 31. Chọn @Cacheable hay RedisTemplate?

| Tiêu chí | Spring Cache annotations | RedisTemplate |
| --- | --- | --- |
| API tra cứu đơn giản | Rất phù hợp | Phù hợp nhưng nhiều code |
| TTL theo cache | CacheManager config | Đặt mỗi write |
| Tự động bỏ qua body khi hit | Có qua Spring proxy | Service tự quyết định |
| Redis data types đặc biệt | Hạn chế ở abstraction | Linh hoạt hơn |
| Lua/atomic operations | Không phải trọng tâm | Thường dùng template/connection |
| Kiểm thử AOP | Cần Spring integration | Không phụ thuộc annotation proxy |
| Fallback policy tùy biến | Cần cấu trúc rõ | Dễ viết tường minh |
| Key/value serialization | CacheManager | RedisTemplate/serializer |
| Multiple caches và invalidation | Có annotation/API | Tự điều phối |

Với chức năng `GET product by ID`, Spring Cache là cách khởi đầu tốt. Khi use case đòi điều kiện nguyên tử, serialization khác nhau hoặc workflow cache phức tạp, có thể cân nhắc service port và Redis adapter tường minh.

## 32. Unit test logic không đồng nghĩa test caching proxy

Nếu tạo trực tiếp:

```java
ProductLookupService service =
    new ProductLookupService(mockRepository);

service.findById(1L);
service.findById(1L);
```

`@Cacheable` **không tự hoạt động**, vì không có Spring proxy. Unit test kiểu này chỉ kiểm tra body Java; gọi hai lần có thể truy vấn repository hai lần.

Để chứng minh caching, cần gọi qua **Spring-managed bean trong ApplicationContext** và có CacheManager thật hoặc cache test adapter được cấu hình đúng.

Đây là lý do bài thực hành dùng Testcontainers integration test ở bước sau.

## 33. Kiểm thử Redis thực bằng Testcontainers

Testcontainers giúp khởi chạy Redis trong môi trường test có Docker-compatible runtime, thay vì kết nối Redis development/production không kiểm soát.

File `ProductCacheIntegrationTest.java`:

```java
package com.example.lookup;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class ProductCacheIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.4.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host",
            REDIS::getHost
        );

        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    ProductLookupService lookup;

    @Autowired
    ProductCommandService commands;

    @Autowired
    CacheManager cacheManager;

    @Autowired
    StringRedisTemplate redis;

    @MockitoSpyBean
    ProductRepository repository;

    @BeforeEach
    void clearCache() {
        Cache cache =
            cacheManager.getCache("productLookup");

        assertThat(cache).isNotNull();
        cache.clear();

        clearInvocations(repository);
    }

    @Test
    void secondLookupUsesCache() {
        ProductView first = lookup.findById(1L);
        ProductView second = lookup.findById(1L);

        assertThat(second).isEqualTo(first);

        verify(repository, times(1))
            .findById(1L);
    }

    @Test
    void cachedProductHasPositiveTtl() {
        lookup.findById(1L);

        Long remainingMs = redis.getExpire(
            "lookup-demo:v1:productLookup::1",
            TimeUnit.MILLISECONDS
        );

        assertThat(remainingMs).isNotNull();
        assertThat(remainingMs).isGreaterThan(0L);
        assertThat(remainingMs)
            .isLessThanOrEqualTo(300_000L);
    }

    @Test
    void changingPriceInvalidatesCache() {
        ProductView before = lookup.findById(1L);

        BigDecimal newPrice =
            before.price().add(new BigDecimal("1.00"));

        commands.changePrice(1L, newPrice);

        Boolean exists = redis.hasKey(
            "lookup-demo:v1:productLookup::1"
        );

        assertThat(exists).isFalse();

        ProductView after = lookup.findById(1L);

        assertThat(after.price())
            .isEqualByComparingTo(newPrice);
    }

    @Test
    void unknownIdIsNotCached() {
        assertThatThrownBy(
            () -> lookup.findById(999_999L)
        ).isInstanceOf(ProductNotFoundException.class);

        assertThat(redis.hasKey(
            "lookup-demo:v1:productLookup::999999"
        )).isFalse();
    }
}
```

### Giải thích từng assertion

- `secondLookupUsesCache`: Spring proxy gọi repository một lần, lần hai dùng cache.
- `cachedProductHasPositiveTtl`: Redis key thực sự có expiration, không chỉ Java truyền một `Duration`.
- `changingPriceInvalidatesCache`: database commit kích hoạt listener và cache key được xóa.
- `unknownIdIsNotCached`: không lưu negative result dưới dạng `ProductView`.

**Lưu ý về test fixture:** ví dụ dựa trên `DemoData` tạo ID 1 khi H2 mới. Trong dự án thực, nên dùng fixture tạo entity và lấy ID thực thay vì hard-code; đồng thời cô lập dữ liệu khi chạy test song song.

`@MockitoSpyBean` dùng cho Spring Framework/Spring Boot đời mới tương ứng. Dự án cũ có thể dùng annotation/cách spy khác, nhưng cần bảo đảm repository là bean do Spring quản lý.

Không coi code ví dụ là đã được chạy kiểm thử chỉ vì xuất hiện trong tài liệu; người học phải thực thi trên môi trường của mình.

## 34. Vì sao không chỉ mock RedisTemplate?

Một test kiểu:

```java
when(valueOperations.get(key)).thenReturn(json);
```

chỉ chứng minh logic xử lý stub, không xác nhận:

- Redis connection thật hoạt động.
- Cache key serialization đúng.
- `RedisCacheManager` có TTL.
- JSON record round-trip.
- Spring AOP proxy thực sự kích hoạt.
- Cache entry tồn tại hoặc bị xóa ở Redis.
- Eviction có làm key mất sớm.
- Exception của Redis driver được map đúng.

Mockito vẫn có giá trị cho **unit test quyết định nghiệp vụ**, nhất là khi service phụ thuộc `ProductCache` port. Nhưng muốn kiểm tra behavior của Redis, cần Redis integration test.

## 35. Kiểm thử cache miss và nguồn chuẩn

Một yêu cầu kiểm thử quan trọng:

1. Redis chưa có key.
2. Database có sản phẩm.
3. `findById` trả DTO đúng.
4. Redis có key mới với TTL.
5. Lần đọc thứ hai không gọi database.

Đó là contract cache-aside cơ bản.

Một yêu cầu khác:

1. Redis chưa có key.
2. Database không có sản phẩm.
3. HTTP trả 404.
4. Redis không bị ghi một JSON null không được quản lý.

Đừng chỉ kiểm tra `GET` lần đầu có response. Nếu không khẳng định lần sau thực sự hit cache, bài thực hành chưa kiểm chứng lợi ích caching.

## 36. Quan sát performance: so sánh có kiểm soát

Mục tiêu của cache là giảm công việc ở database và có thể cải thiện latency. Tuy nhiên một phép đo thủ công nhỏ không chứng minh hiệu năng production.

Một thử nghiệm:

```text
Giai đoạn A: cold cache
  - clear key test
  - gọi GET lần đầu
  - đo latency, DB SELECT, Redis miss

Giai đoạn B: warm cache
  - gọi GET cùng ID nhiều lần
  - đo latency, DB SELECT, Redis hit

Giai đoạn C: cache invalidate
  - PUT đổi giá
  - GET lại
  - đo latency, DB SELECT, value correctness
```

Những biến số cần giữ ổn định:

- Cùng Redis/JVM/database topology.
- Cùng ID và payload.
- HTTP connection reuse hoặc công cụ load test phù hợp.
- JVM warm-up.
- Số request/concurrency.
- Database index và query plan.
- Network latency.
- Logging overhead.

Đọc một lần thấy Redis nhanh hơn không đủ để suy ra p99 latency sẽ tốt hơn trên mọi workload.

## 37. Giám sát memory và eviction

Redis cung cấp:

```bash
docker compose exec redis redis-cli INFO memory
docker compose exec redis redis-cli INFO stats
docker compose exec redis redis-cli INFO keyspace
```

Các trường thường hữu ích:

| Trường | Ý nghĩa |
| --- | --- |
| `used_memory` | Memory Redis allocator đang dùng |
| `used_memory_rss` | Resident memory theo OS |
| `maxmemory` | Ngưỡng được cấu hình |
| `maxmemory_policy` | Policy eviction |
| `keyspace_hits` | Số key lookups thành công theo Redis stats |
| `keyspace_misses` | Số key lookups không tìm thấy |
| `expired_keys` | Keys hết hạn |
| `evicted_keys` | Keys bị loại do memory policy |

Không lấy `used_memory < maxmemory` làm bằng chứng process RSS luôn dưới container limit. Memory buffers, fragmentation và persistence có thể làm RSS cao hơn.

Trong demo `allkeys-lru`, eviction khi dataset lớn là behavior cho phép. Trong production, cần xem nó có làm DB fallback và API latency tăng bất thường hay không.

## 38. Quan sát ở tầng Spring Boot

Actuator có thể cung cấp metrics của JVM, HTTP server và một số integrations tùy cấu hình/instrumentation. Không mặc định mọi version sẽ xuất đúng metric Redis hit/miss theo cache name.

Có thể gọi:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
```

Khi cần đo cache hit/miss nghiệp vụ chính xác:

- Dùng instrumentation ở cache abstraction/adapter phù hợp.
- Gắn cache name thay vì user ID làm label.
- Đo hit/miss, latency, errors và fallback.
- Đếm số DB queries hoặc connection pool pressure.
- Đo thời gian làm nóng cache sau restart.

Không đưa raw Redis password, key nhạy cảm, token hoặc thông tin cá nhân vào metrics/logs.

## 39. Redis mất kết nối: cache miss và lỗi khác nhau

Trong ví dụ `@Cacheable`, nếu Redis server tắt, Redis cache lookup có thể ném exception thay vì tự chạy method để đọc database. Spring Cache không tự hứa “Redis down thì luôn fallback DB” khi chưa cấu hình error handler phù hợp.

Cần chọn chính sách:

| Redis role | Redis unavailable thì sao? |
| --- | --- |
| Cache sản phẩm có nguồn chuẩn ở DB | Có thể fallback database nếu tải được kiểm soát |
| Session bắt buộc | Có thể cần báo lỗi/chuyển flow đăng nhập |
| Rate limit chống abuse | Không mặc định fail-open |
| Distributed lock | Không được bỏ qua lỗi rồi coi như đã có lock |
| Idempotency | Không tự tiếp tục side effect khi chưa kiểm tra chống trùng |

Với cache sản phẩm, có thể cấu hình `CacheErrorHandler` để bỏ qua **một số lỗi cache infrastructure** và cho service chạy body method, nhưng phải cân nhắc cả read errors, write errors, metrics, circuit breaker và tránh che dữ liệu cache corrupt không mong muốn.

## 40. CacheErrorHandler: demo fail-open có giám sát

Ví dụ đơn giản mở rộng qua `CachingConfigurer`:

```java
package com.example.lookup;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cache.Cache;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.annotation.CachingConfigurer;

@Configuration
public class CacheFailurePolicy implements CachingConfigurer {

    private static final Logger log =
        LoggerFactory.getLogger(CacheFailurePolicy.class);

    @Override
    public CacheErrorHandler errorHandler() {
        return new CacheErrorHandler() {

            @Override
            public void handleCacheGetError(
                    RuntimeException ex,
                    Cache cache,
                    Object key) {
                log.warn(
                    "Cache read unavailable: {}",
                    cache.getName(),
                    ex
                );
            }

            @Override
            public void handleCachePutError(
                    RuntimeException ex,
                    Cache cache,
                    Object key,
                    Object value) {
                log.warn(
                    "Cache write unavailable: {}",
                    cache.getName(),
                    ex
                );
            }

            @Override
            public void handleCacheEvictError(
                    RuntimeException ex,
                    Cache cache,
                    Object key) {
                log.warn(
                    "Cache eviction failed: {}",
                    cache.getName(),
                    ex
                );
            }

            @Override
            public void handleCacheClearError(
                    RuntimeException ex,
                    Cache cache) {
                log.warn(
                    "Cache clear failed: {}",
                    cache.getName(),
                    ex
                );
            }
        };
    }
}
```

**Đây là ví dụ policy lựa chọn**, không phải một phần bắt buộc để chạy bài thực hành cơ bản. Nên thêm vào project **sau khi hiểu contract của hệ thống**.

Điểm đáng chú ý:

- Không throw exception từ handler có thể cho phép caching interceptor tiếp tục theo hành vi Spring tương ứng.
- Logging mọi lỗi dưới tải có thể gây bão log; production cần metric và rate-limited logging.
- Bỏ qua lỗi `evict` khiến cache cũ có thể tiếp tục được đọc sau DB commit; TTL chỉ giới hạn thời gian stale, chưa chắc đáp ứng SLA.
- Bỏ qua mọi `RuntimeException` có thể che lỗi serializer/configuration; nên phân loại lỗi và phát cảnh báo phù hợp.
- Không dùng fail-open policy này cho Redis lưu lock, rate limit quan trọng hoặc idempotency state.

Một chính sách cache **best-effort** cần được thiết kế rõ thay vì ngầm định bất kỳ Redis exception nào cũng là cache miss.

## 41. Cache stampede: nhiều request cùng cache miss

Một key nóng bị evict hoặc hết TTL:

```text
               500 clients
                    |
                    v
       GET /api/products/1 cùng lúc
                    |
                    v
          Redis cache miss
                    |
                    v
       Nhiều SELECT cùng ID tại DB
```

Đây là **cache stampede**. `@Cacheable` theo mặc định không phải bảo đảm chỉ có một request trên toàn cluster cùng nạp dữ liệu.

Một số phương án:

- `@Cacheable(sync = true)` có thể giảm concurrent loading trong phạm vi provider/implementation hỗ trợ, nhưng phải kiểm tra semantics của RedisCacheManager và không suy ra distributed single-flight trên nhiều pods.
- Request coalescing ở tầng service.
- TTL jitter để giảm nhiều key hết hạn đúng cùng thời điểm.
- Warm-up các key hot.
- Local cache tầng trước với consistency policy phù hợp.
- Rate limit fallback DB.
- Cho phép stale-while-revalidate nếu nghiệp vụ chấp nhận.
- Distributed locking hoặc job coordination khi chi phí recompute rất lớn, kèm failure handling.

Nếu một pod giữ lock nạp cache, pod khác bị timeout, cần xác định behavior rõ; không thêm lock chỉ để “giải quyết performance” mà chưa hiểu độ phức tạp.

## 42. TTL jitter cho nhiều key

Nếu hàng nghìn key cùng được cache khi batch chạy lúc 00:00 và cùng TTL 300 giây, chúng có thể expire gần như đồng loạt lúc 00:05.

Một cách giảm đồng pha là thêm jitter:

```text
TTL = 300 giây + random(0..30 giây)
```

Với `RedisTemplate`, mỗi lần `put` có thể đặt TTL riêng. Với `RedisCacheManager`, các phiên bản Spring Data Redis hỗ trợ cơ chế expiration động như `TtlFunction` trong cấu hình tương ứng; kiểm tra API của version đang dùng.

**Không tùy tiện dùng TTL jitter với OTP, lock, session hoặc các deadline nghiệp vụ bắt buộc.** Jitter phù hợp hơn với cache có thể tái tạo và độ cũ cho phép dao động.

TTL jitter không thay thế capacity planning; nếu working set lớn hơn RAM, eviction vẫn xảy ra.

## 43. Concurrency: stale cache có thể xuất hiện dù evict sau commit

Một race cache-aside quan trọng:

```text
T0 Reader A: cache miss
T1 Reader A: SELECT giá cũ = 129000
T2 Writer B: UPDATE giá = 139000, COMMIT
T3 Writer B: EVICT cache key
T4 Reader A: SET cache = 129000 (đọc chậm, ghi muộn)
T5 Reader C: cache hit giá cũ
```

Vì reader A đã đọc database trước khi writer B commit, nó có thể ghi giá cũ **sau** eviction.

`AFTER_COMMIT` invalidation giúp đúng thứ tự đối với chính transaction update, nhưng **không loại bỏ mọi race** giữa readers và writers.

Các hướng giải quyết khi consistency yêu cầu cao:

1. Cache payload có `version` để không overwrite phiên bản mới bằng phiên bản cũ.
2. Dùng Lua/conditional update nếu thiết kế keys/versions cho phép.
3. Invalidate lần nữa bằng cơ chế delayed/retry hoặc event processing phù hợp, nhưng cần phân tích race mới.
4. Dùng transactional outbox và replayable invalidation.
5. TTL ngắn và xác nhận ở nguồn chuẩn tại điểm nghiệp vụ critical.
6. Chọn không cache một số trường dữ liệu yêu cầu linearizable reads.

Không tuyên bố cache-aside là mạnh nhất quán chỉ vì có `@CacheEvict`.

## 44. Transactional outbox cho invalidation đáng tin

Nếu yêu cầu không bỏ lỡ invalidation sau DB commit, có thể dùng pattern:

```text
BEGIN database transaction
    |
    +-- UPDATE products
    |
    +-- INSERT outbox(productChanged, id, version)
    |
COMMIT
    |
    v
Outbox worker đọc events chưa xử lý
    |
    v
Redis evict/update cache
    |
    v
Mark outbox event processed / retry
```

Lợi ích:

- Nếu application crash sau database commit, outbox event vẫn còn.
- Worker có thể retry.
- Có thể gắn version để xử lý sự kiện đến không đúng thứ tự.
- Redis outage không làm mất business write transaction đã commit.

Giới hạn:

- Cache có thể stale cho tới khi worker xử lý event.
- Phải quản lý duplicate events/idempotency.
- Không phải transaction phân tán nguyên tử giữa DB và Redis.
- Cần monitoring backlog và retry errors.

Với demo tra cứu dữ liệu đơn giản, TTL + after-commit eviction có thể đủ để học. Với giá checkout hoặc hệ thống yêu cầu read consistency chặt, cần thiết kế bổ sung.

## 45. Negative caching: cache kết quả “không tồn tại”

Một API có nhiều request tới ID sai có thể liên tục hit DB.

Giải pháp có thể là một sentinel value:

```text
lookup-demo:v1:productMissing::999999 -> NOT_FOUND
TTL 15 giây
```

Khi dùng negative cache:

- Phải phân biệt “không có sản phẩm” và “Redis lỗi”.
- Không để negative cache cũ che sản phẩm mới tạo.
- Đặt TTL ngắn phù hợp.
- Invalidate negative key khi tạo entity.
- Không dùng `null` mơ hồ nếu serializer/cache manager không hỗ trợ.
- Kiểm tra input validation và bảo vệ API khỏi ID enumeration abuse.

Bài thực hành cơ bản chọn không negative-cache để giữ ví dụ dễ hiểu.

## 46. Redis key naming và versioning

Một key tốt trong demo:

```text
lookup-demo:v1:productLookup::1
```

Các phần:

```text
lookup-demo  -> ứng dụng/namespace
v1           -> schema cache version
productLookup-> cache name
1            -> business key
```

Lợi ích:

- Dễ tìm trên Redis CLI.
- Tránh key collision giữa applications.
- Dễ chuyển phiên bản serializer.
- Dễ tách môi trường.
- Dễ theo dõi theo nhóm cache.

Trong môi trường multi-tenant, key có thể cần tenant scope để không trả nhầm dữ liệu:

```text
app:v1:tenant:{tenant-id}:product:{product-id}
```

Không đặt token, password hoặc dữ liệu nhạy cảm dạng plaintext trong key names; Redis key có thể xuất hiện trong log/metrics hoặc công cụ vận hành.

Prefix **không tạo memory quota**. Nếu Redis chứa cache và idempotency/lock state, một policy eviction cấp server có thể ảnh hưởng cả hai; cần cân nhắc tách Redis instances/deployments.

## 47. Serializer compatibility giữa các bản phát hành

Giả sử bản v1 cache:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 129000.00
}
```

Bản v2 thêm:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 129000.00,
  "currency": "VND"
}
```

Câu hỏi:

- Reader v1 có bỏ qua field mới?
- Reader v2 xử lý cache cũ thiếu `currency` ra sao?
- Có thay đổi kiểu `price` từ số sang chuỗi?
- Có deployment nhiều phiên bản cùng đọc một cache namespace?
- Có cache key versioning hoặc migration strategy không?

Đổi prefix `v1` sang `v2` giúp tránh đọc cache schema cũ khi không thể duy trì backward compatibility, đổi lại sẽ làm warm-up/miss tăng trong giai đoạn chuyển đổi.

Integration tests nên kiểm tra round-trip và khả năng đọc payload mẫu của những version còn được hỗ trợ.

## 48. Không cache trực tiếp dữ liệu chứa bí mật

Mọi caching strategy cần phân loại dữ liệu.

Ví dụ có thể cache:

- Danh mục public.
- Metadata sản phẩm không nhạy cảm.
- Những kết quả truy vấn đã được authorization/filter đúng.
- Dữ liệu có TTL và mức stale chấp nhận được.

Cần thận trọng với:

- Token truy cập hoặc refresh tokens.
- Thông tin cá nhân không cần lưu.
- Credentials.
- Quyền truy cập theo user/tenant.
- Payment state.
- Nội dung phụ thuộc role và authorization.

Nếu kết quả query phụ thuộc người dùng/tenant, cache key phải bao gồm **toàn bộ context cần thiết để phân biệt kết quả**, hoặc phải cache dữ liệu độc lập với quyền rồi lọc truy cập ở lớp phù hợp.

Không dùng cache key chỉ `productId` cho một dữ liệu khác nhau theo tenant nếu điều đó có thể làm rò rỉ giữa tenants.

## 49. Redis Cluster: một cache key thuộc một hash slot

Trong Redis Cluster, Redis phân phối keys theo 16.384 hash slots. `@Cacheable` cho từng sản phẩm là thao tác một key, thường thuận lợi cho cluster-aware client.

Tuy nhiên:

- Bulk cache clear có thể cần duyệt nhiều cluster nodes.
- Một Redis standalone Testcontainers không kiểm tra Cluster routing.
- Lua/multi-key commands có ràng buộc đồng slot.
- `MOVED`/`ASK` redirects có thể xuất hiện trong failover/resharding.
- Replica reads có thể trả snapshot cũ do replication lag.
- Một hot key vẫn nằm trên một shard, không được tự chia tải bằng hash slots.

Nếu production dùng Redis Cluster, cần integration/fault tests trên một Cluster thật khi những tính năng này quan trọng; không suy ra từ demo standalone rằng mọi cluster behavior đã đúng.

## 50. Eviction policy và tính chất dữ liệu

Redis demo đang dùng `allkeys-lru`, phù hợp khi **mọi key trên instance đều là cache có thể tái tạo**.

Không dùng cùng Redis pool cho:

```text
cache:product:42
session:user:1001
lock:order:42
idempotency:payment:req-123
```

rồi mặc định một eviction policy sẽ phân biệt các loại dữ liệu theo prefix.

- `allkeys-*` có thể eviction mọi key.
- `volatile-*` có thể eviction mọi key có TTL, gồm session/lock/idempotency.
- `noeviction` không eviction chủ động nhưng có thể từ chối writes khi đầy.
- TTL không bảo đảm key tồn tại ít nhất tới lúc hết TTL.

Đối với cache tra cứu, chấp nhận miss và tái tạo dữ liệu là chìa khóa để dùng eviction an toàn.

## 51. Redis outage và fallback database dưới tải

Có thể thiết kế fail-open cho cache tra cứu, nhưng giả sử Redis phục vụ 90% trong 20.000 GET/s.

Khi Redis offline, phần lớn requests sẽ chuyển tới DB. Điều này có thể làm database quá tải.

Các biện pháp:

- Circuit breaker cho cache infrastructure.
- Giới hạn concurrency tới database.
- Request coalescing cho key nóng.
- Rate limiting / load shedding.
- Local cache ngắn hạn nếu consistency cho phép.
- Database index và query plan phù hợp.
- Load test fallback scenarios.
- Theo dõi Redis errors, DB query rate, p95/p99 latency.

**Một test chứng minh fallback đọc được DB không có nghĩa hệ thống chịu nổi toàn bộ tải fallback.** Cần capacity planning riêng.

## 52. Kiểm thử khi cache bị xóa đột ngột

Trong Redis demo, sau khi đã GET sản phẩm:

```bash
docker compose exec redis \
  redis-cli DEL 'lookup-demo:v1:productLookup::1'
```

Gọi lại:

```bash
curl http://localhost:8080/api/products/1
```

Kết quả vẫn phải trả sản phẩm từ database và cache lại.

Bài test này chứng minh ứng dụng **không phụ thuộc việc cache entry luôn tồn tại**.

Đừng dùng `FLUSHALL` trên Redis chứa dữ liệu ngoài bài demo. Dù đang thực hành, nên xóa chính key hoặc namespace test riêng.

## 53. Kiểm thử TTL hết hạn

Có thể giảm TTL trong test configuration hoặc dùng TTL vài giây ở một test Redis riêng.

Quy trình:

1. Đảm bảo key test chưa có.
2. Gọi `GET` để tạo cache entry.
3. Xác nhận `PTTL` dương.
4. Poll key với timeout hữu hạn.
5. Khi key hết hạn, gọi `GET` lại.
6. Xác nhận repository được truy vấn lại.
7. Không assert key biến mất chính xác ở cùng mili giây của deadline.

Redis xử lý expiration theo cơ chế của server; keyspace notification có thể đến sau khi TTL logic kết thúc. Test nên dựa vào khả năng đọc key/TTL, không dựa duy nhất vào event timing.

## 54. Test cập nhật dữ liệu và rollback

Demo đã test invalidation sau successful commit. Muốn mở rộng:

- Một transaction cập nhật sản phẩm rồi rollback.
- `ProductChangedEvent` được publish trong transaction đó.
- Listener `AFTER_COMMIT` không chạy cho transaction rollback.
- Redis cache chưa bị xóa chỉ vì thay đổi chưa commit.
- Database vẫn giữ giá cũ.
- Nếu transaction commit rồi eviction lỗi, ứng dụng có chiến lược retry/reconciliation.

Một cách test rollback là viết test service phụ dùng `TransactionTemplate` rồi cố ý throw exception trong transaction. Đừng chỉ mock `@Transactional` và tuyên bố đã chứng minh commit semantics.

## 55. Đừng nhầm cache hit với read-your-writes

Nếu ứng dụng cập nhật database rồi đọc Redis replica, Redis replication có thể chậm. Trong demo standalone, vấn đề này không xuất hiện.

Trong production Redis Sentinel/Cluster:

```text
T0 write cache entry to primary
T1 primary ACK
T2 GET routed to replica
T3 replica chưa áp dụng write mới
```

Tùy client `ReadFrom` policy, kết quả có thể stale. Đối với dữ liệu dùng ở điểm quyết định quan trọng, cần đọc nguồn có thẩm quyền theo consistency policy phù hợp.

Spring Cache không tự bảo đảm linearizability xuyên Redis replicas và database.

## 56. Khi cập nhật giá, nên @CacheEvict hay @CachePut?

Hai lựa chọn phổ biến:

| Tiêu chí | `@CacheEvict` | `@CachePut` |
| --- | --- | --- |
| Sau update | Xóa key | Ghi snapshot mới |
| Lần đọc kế tiếp | Có cache miss/reload | Có thể hit ngay |
| Khả năng stale race | Vẫn có | Vẫn có nếu ordering sai |
| Serialization | Không ghi value mới tại thời điểm evict | Phải serialize DTO mới |
| Transaction timing | Cần after-commit policy | Cần after-commit policy |
| Code/logic | Đơn giản | Cần key và result chính xác |

`@CachePut` có thể chạy method rồi update cache bất kể cache entry trước đó, nhưng khi gắn cùng `@Transactional`, thời điểm cache put so với commit phải được kiểm chứng theo Spring advice/transaction config.

Trong bài, evict sau commit đơn giản hơn cho mục tiêu học và tránh dùng snapshot chưa commit làm cache chuẩn.

## 57. Thực hành thêm: tìm kiếm theo tên

Bài hiện chỉ tra cứu theo ID. Khi mở rộng:

```http
GET /api/products?name=redis&page=0&size=20&sort=name,asc
```

Cache key **phải bao gồm đầy đủ các tham số ảnh hưởng kết quả**, ví dụ:

```text
search:v1:name=redis:page=0:size=20:sort=name_asc
```

Nếu chỉ dùng `name` làm key mà bỏ `page/size/sort`, nhiều truy vấn có thể dùng sai cached result.

Các vấn đề khác:

- Chuẩn hóa filter, hoa/thường và whitespace.
- Ngăn key cardinality bùng nổ từ truy vấn tự do.
- TTL kết quả tìm kiếm thường ngắn hơn dữ liệu ít thay đổi.
- Invalidation của search cache phức tạp hơn một key product ID.
- Không cache phân trang lớn vô giới hạn.
- Tránh lưu kết quả có authorization khác nhau dưới cùng key.

Bài tập tiếp theo có thể xây `SearchCriteria` canonicalization để định danh cache key an toàn.

## 58. Các lỗi thường gặp khi triển khai

| Triệu chứng | Cần kiểm tra |
| --- | --- |
| Gọi hai lần vẫn SELECT | `@EnableCaching`, proxy, CacheManager, key |
| Redis không có key | Service bypass proxy, write lỗi, TTL quá ngắn |
| `ClassCastException` khi đọc cache | Serializer/type config không phù hợp |
| JSON payload không đọc được | DTO/schema/Jackson compatibility |
| Giá vẫn cũ sau update | Chưa evict, listener không chạy, race, Redis lỗi |
| Mọi request lỗi khi Redis down | Chưa thiết kế fail-open/error handler |
| Dữ liệu tenant A trả cho tenant B | Cache key thiếu tenant/auth context |
| TTL là `-1` | Cache key không có expiration |
| TTL là `-2` | Key đã mất/expire/evict/chưa ghi |
| `evicted_keys` tăng | Memory pressure và eviction policy |
| Redis OOM dù còn database | `noeviction`/memory budget hoặc memory overhead |
| Cache stampede | Key hot hết hạn/evict đồng thời |
| Test Mockito xanh nhưng cache không hoạt động | Test không qua Spring proxy/Redis thật |
| Testcontainers không start | Docker runtime, image availability, CI config |
| Cập nhật DB commit mà cache chưa xóa | Process crash/Redis outage sau commit |
| Cache clear chậm trên Cluster | Cache writer và scan strategy, nhiều nodes |

Khi điều tra, dùng log của cả Spring, database và Redis; đừng kết luận chỉ từ HTTP response.

## 59. Checklist trước khi triển khai production

**Data contract**

- Database/source of truth được xác định.
- DTO cache và schema version rõ.
- Không cache dữ liệu nhạy cảm không cần thiết.
- Cache key bao gồm tenant/authorization context nếu ảnh hưởng kết quả.
- TTL dựa trên mức stale chấp nhận được.

**Spring Data Redis**

- `@EnableCaching` và proxy thực sự hoạt động.
- `RedisCacheManager` có prefix, serializer, TTL đúng.
- `@Cacheable` dùng key ổn định.
- Cache invalidation sau commit và xử lý lỗi được thiết kế.
- Không cache exceptions/null ngoài ý định.
- Nếu dùng manual `RedisTemplate`, có port/failure contract phù hợp.

**Redis server**

- Có authentication, TLS/network isolation theo môi trường.
- Giới hạn memory và eviction phù hợp **cache-only**.
- Có capacity/headroom, metrics và alerts.
- Có chiến lược HA khi Redis availability quan trọng.
- Không chung instance với lock/idempotency state cần policy khác.

**Testing/operations**

- Có unit tests cho business behavior.
- Có Redis integration test cho serialization, TTL và evict.
- Có Spring integration test cho annotation/proxy.
- Có load test với warm/cold cache và fallback DB.
- Có test update/rollback/race nếu consistency quan trọng.
- Có metric hit/miss, Redis errors, DB load và latency.
- Có runbook xử lý Redis outage, eviction spike và cache stampede.

## 60. Bài tập A — Hoàn thiện API tra cứu

Triển khai toàn bộ project và thực hiện:

1. Khởi động Redis bằng Docker Compose.
2. Chạy Spring Boot.
3. `GET /api/products/1` lần đầu.
4. Dùng Redis CLI kiểm tra `GET`, `TTL`.
5. `GET` lần thứ hai.
6. Quan sát số lần `SELECT`.
7. `PUT` đổi giá sản phẩm 1.
8. Kiểm tra cache key bị xóa.
9. `GET` lần nữa và xác nhận giá mới.
10. `GET` ID không tồn tại và xác nhận 404.

Viết lại sơ đồ dữ liệu mà chính ứng dụng đã đi qua ở mỗi bước.

## 61. Bài tập B — Tối ưu TTL

Giả sử:

```text
productName: thay đổi rất ít
productPrice: thay đổi vài lần/ngày
stockAvailable: thay đổi liên tục
```

Hãy:

1. Chọn TTL hoặc quyết định không cache theo từng trường.
2. Xác định trường nào phải đọc lại từ database khi checkout.
3. Đề xuất cache names và key prefixes.
4. Kiểm tra TTL thực bằng `PTTL`.
5. Giải thích vì sao TTL 5 phút không bảo đảm key luôn sống đủ 5 phút dưới eviction.

## 62. Bài tập C — Triển khai manual cache-aside

Thay `@Cacheable` bằng một `ProductCache` port và Redis adapter:

```java
public interface ProductCache {
    Optional<ProductView> find(Long id);
    void put(ProductView value, Duration ttl);
    void evict(Long id);
}
```

Hãy:

1. Viết service rõ hai nhánh hit/miss.
2. Unit test service bằng Mockito mock `ProductCache`.
3. Integration test adapter bằng Redis Testcontainers.
4. So sánh số dòng code và khả năng custom error handling.
5. Giải thích vì sao Mockito không tự chứng minh TTL/serializer.

## 63. Bài tập D — Mô phỏng Redis outage

Trong môi trường demo:

```bash
docker compose stop redis
```

Gọi API:

```bash
curl -i http://localhost:8080/api/products/1
```

Quan sát behavior khi chưa có cache fail-open policy. Sau đó nghiên cứu và áp dụng `CacheErrorHandler` cho **cache-only use case**, ghi nhận lỗi nhưng vẫn đọc database theo policy.

Khởi động lại Redis:

```bash
docker compose start redis
```

Kiểm tra app có phục hồi không.

Không mở rộng fail-open sang OTP/lock/rate limiter nếu chưa phân tích security/business behavior.

## 64. Bài tập E — Dữ liệu cũ do concurrency

Dựng một test có hai threads:

1. Reader A cache miss, đọc dữ liệu cũ từ database.
2. Reader A bị giữ trước lúc ghi cache.
3. Writer B thay đổi giá và commit.
4. Writer B invalidate cache.
5. Reader A tiếp tục ghi cache giá cũ.
6. Reader C có thể đọc cache stale.

Hãy đề xuất cách dùng versioning, outbox, invalidation bổ sung hoặc xác nhận nguồn chuẩn để giải quyết theo SLA.

Một integration test concurrency có barrier và timeout sẽ có giá trị hơn test đơn luồng chỉ `verify(cache).evict()`.

## 65. Câu hỏi thường gặp

**Cache-aside là gì?**

Ứng dụng đọc cache trước; khi miss, đọc database nguồn chuẩn và điền lại cache.

**Tại sao lần đầu chậm hơn lần hai?**

Lần đầu có thêm DB query và cache write; lần hai có thể trả từ Redis. Kết quả phụ thuộc latency/network/load thực tế.

**Có phải @Cacheable tự tạo database transaction không?**

Không. Caching và transaction là hai concerns khác nhau; `@Transactional` mới cấu hình transaction tương ứng và cách advice được sắp xếp có thể ảnh hưởng timing.

**Có thể cache JPA entity trực tiếp không?**

Có thể trong một số dự án, nhưng dễ gặp lazy proxies, schema coupling và serialization problems; DTO thường là lựa chọn dễ kiểm soát hơn.

**TTL 5 phút có nghĩa key không bị xóa trước 5 phút không?**

Không. Redis eviction, explicit delete, failover hoặc restart có thể làm key biến mất sớm.

**Cache hit có gọi repository không?**

Khi `@Cacheable` interceptor hoạt động và key hit, body service thường không được gọi, nên repository không bị truy vấn ở đường này.

**Tại sao gọi trực tiếp service bằng new không cache?**

Vì `@Cacheable` thường chạy qua Spring AOP proxy, không phải phương thức Java thuần.

**Tại sao cần @EnableCaching?**

Để kích hoạt infrastructure xử lý cache annotations trong Spring.

**Nếu cập nhật database, nên xóa cache khi nào?**

Ít nhất phải xét sau transaction commit; có thể dùng event listener `AFTER_COMMIT`. Với yêu cầu reliability cao hơn, cần outbox/retry/đối soát và xem xét race.

**Sau khi evict cache có luôn đọc được giá mới không?**

Không bảo đảm tuyệt đối dưới mọi concurrency scenario; có thể có in-flight reader ghi cache cũ sau eviction, hoặc replica/database reads chưa cập nhật theo yêu cầu.

**Có nên dùng @CachePut?**

Có thể khi muốn chủ động ghi giá trị mới vào cache, nhưng phải bảo đảm key/result/transaction timing và concurrency consistency.

**Khi Redis down, @Cacheable có tự fallback DB không?**

Không mặc định. Redis cache lookup có thể ném exception; cần error handler/policy rõ khi Redis chỉ là cache.

**Một Redis Testcontainers có giống Redis Cluster production không?**

Không. Nó chỉ là Redis standalone. Cluster-specific behavior cần topology test riêng.

**Có cần cache mọi API GET không?**

Không. Chỉ cache những truy vấn có chi phí đáng kể, mức dữ liệu stale chấp nhận được và key cardinality hợp lý.

**Redis cache là source of truth không?**

Trong ví dụ này không. Database giữ dữ liệu chuẩn, Redis chỉ lưu snapshot có thể tái tạo.

**Có thể dùng cache cho dữ liệu theo tenant không?**

Có, nhưng cache key và authorization phải phân biệt chính xác các kết quả; nếu không có thể rò rỉ dữ liệu giữa tenants.

**Test TTL có nên dùng Thread.sleep không?**

Tránh phụ thuộc sleep đúng ranh giới; nên kiểm tra TTL còn dương và polling có timeout.

**Tại sao Redis evicted_keys tăng?**

Redis memory policy có thể đang loại key để giữ budget. Với cache-only pool, đây có thể là behavior bình thường nhưng vẫn cần quan sát hit ratio và tải database.

## 66. Tổng kết

Bài thực hành đã thiết kế một API tra cứu dữ liệu theo đường đi:

```text
Spring REST API
    |
    v
ProductLookupService
    |
    v
@Cacheable / RedisCacheManager
    |
    +-- cache HIT -> ProductView
    |
    +-- cache MISS -> JPA repository -> H2
                          |
                          v
                    ProductView
                          |
                          v
                    Redis cache TTL
```

Đồng thời, khi cập nhật giá:

```text
ProductCommandService
    |
    v
Database transaction
    |
    v
COMMIT
    |
    v
@TransactionalEventListener(AFTER_COMMIT)
    |
    v
Evict Redis cache key
```

Các điều cần ghi nhớ:

1. **Database là nguồn chuẩn; Redis cache là bản sao.**
2. `@Cacheable` đơn giản hóa cache-aside nhưng cần Spring proxy và CacheManager đúng.
3. **TTL, cache prefix và serializer** phải được cấu hình và kiểm tra thực tế.
4. **Cache hit** cần được chứng minh bằng việc bỏ qua repository, không chỉ HTTP trả 200.
5. **Invalidation sau commit** cải thiện tính đúng nhưng chưa loại bỏ mọi race hoặc crash window.
6. **Redis outage** cần policy rõ; cache có thể fallback DB nhưng phải bảo vệ database khỏi stampede.
7. **Integration test với Redis thật** là cách kiểm chứng key, DTO serialization, TTL và eviction.
8. **Redis eviction và TTL khác nhau**; mất cache là hiện tượng ứng dụng phải xử lý được.
9. Với dữ liệu nghiệp vụ critical, phải thiết kế transaction/idempotency/source of truth riêng, không dựa vào cache một cách mù quáng.
10. Cấu hình demo cần được thay bằng topology, auth, metrics và capacity plan phù hợp khi triển khai thực tế.

Kết quả mong đợi sau khi tự chạy là một API có dữ liệu đúng, cache hit/miss quan sát được, TTL xác nhận bằng Redis CLI, invalidation sau cập nhật và bộ integration tests giúp ngăn những lỗi caching phổ biến.

## Tài liệu tham khảo chính thức

- [Spring Data Redis – Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – Serialization](https://docs.spring.io/spring-data/redis/reference/redis/template.html#redis:serializer)
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework – Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Boot – Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot – Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis)
- [Spring Boot – Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers for Java](https://java.testcontainers.org/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis – SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis – Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
