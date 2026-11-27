# Building a Cache for Data Lookup with Spring Data Redis

## 1. Practice Objectives

In this exercise, we build a product lookup API using **Spring Boot, Spring Data JPA, and Spring Data Redis**. Product data is stored in a database; Redis stores a copy to reduce database queries and improve read speed.

The demo application supports:

- `GET /api/products/{id}`: look up product information by ID.
- `PUT /api/products/{id}/price`: update a product's price.
- **Cache hit**: retrieve the lookup result from Redis without calling the repository.
- **Cache miss**: query the database, return a DTO, and write the result to Redis with a TTL.
- **Invalidation**: delete the cache entry of the updated product so subsequent reads fetch the new data.
- **Observability**: inspect Redis keys, TTL, and distinguish cache hits/misses.
- **Testing**: use JUnit, Spring Test, and Testcontainers to run real Redis in the test environment.

The goal is not merely to create a Redis key, but to understand **the data path, the authoritative data source, the cache lifecycle, consistency limits, and how to verify behavior**.

> **Important principle:** In this example, **the database is the source of truth**. Redis is only a rebuildable copy. A cache miss or cache loss does not mean losing products.

## 2. Problem Statement and Completion Criteria

Suppose the `products` table has two products:

| ID | Name | Price |
| ---: | --- | ---: |
| 1 | Spring Data Redis Handbook | 129.000 |
| 2 | Java Persistence Guide | 159.000 |

Expected flow:

```text
Attempt 1: GET /api/products/1
        -> Redis miss
        -> SELECT FROM products WHERE id = 1
        -> store in Redis with 5-minute TTL
        -> HTTP 200

Attempt 2: GET /api/products/1
        -> Redis hit
        -> no additional SELECT
        -> HTTP 200

PUT /api/products/1/price
        -> UPDATE database
        -> commit succeeds
        -> delete cache for product 1

Attempt 3: GET /api/products/1
        -> Redis miss
        -> SELECT new price
        -> cache again
        -> HTTP 200
```

Technical criteria:

1. The HTTP response returns JSON containing `id`, `name`, `price`.
2. A non-existent product returns HTTP 404.
3. Redis keys have a clear namespace to avoid overwriting other data types.
4. Cache entries have a TTL.
5. Updating the price does not keep stale cache indefinitely.
6. A test proves that the second read does not query the repository.
7. A test confirms Redis actually stores the DTO and TTL.
8. There is a clear policy when Redis is unavailable.

The configuration values in the example are suitable for a **learning environment**, not a copy-paste production template.

## 3. Cache-Aside Architecture

**Cache-aside** (lazy-loading cache) is a common strategy for lookups:

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

**Characteristics:**

- Redis does not automatically load data from the database.
- The application decides when to read the source of truth and when to write to the cache.
- TTL limits how long a snapshot exists if it is not deleted earlier.
- Cache entries may disappear early if Redis enables eviction.
- Database updates require a plan to invalidate or update the cache.

In Spring, cache-aside can be implemented with `RedisTemplate` or with the **Spring Cache Abstraction** (`@Cacheable`, `@CacheEvict`, `RedisCacheManager`). This exercise uses Spring Cache for the runnable version, then introduces how to use `RedisTemplate` when fine-grained control is needed.

## 4. Project Structure

Uses Java 21, Spring Boot 3.5.x, and Maven. Example structure:

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

For ease of practice, the Java classes are placed in a single package. A real project can organize them into `domain`, `application`, `infrastructure`, and `web` as scale grows.

H2 is an **in-memory database for learning purposes**. Production needs a database with appropriate persistence, migrations, transaction policy, and backups.

## 5. Initializing Dependencies

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

The Spring Boot version is pinned so the example has a deterministic structure. When applying this to an existing repository, use the project's validated BOM and versions; do not change the Spring Boot or Redis version just to copy the lesson.

Role of each dependency:

| Dependency | Purpose |
| --- | --- |
| `starter-web` | REST Controller, JSON |
| `starter-validation` | Validate price update input |
| `starter-data-jpa` | Persist products with JPA |
| `starter-data-redis` | RedisConnectionFactory/Lettuce |
| `starter-cache` | Spring Cache annotations/CacheManager |
| `starter-actuator` | Health, metrics, telemetry |
| `h2` | Demo database |
| `starter-test` | JUnit, Mockito, AssertJ, Spring Test |
| `testcontainers:junit-jupiter` | Manage the Redis test container |

## 6. Starting Redis for the Practice Environment

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

Start it:

```bash
docker compose up -d
```

Verify:

```bash
docker compose exec redis redis-cli PING
```

Expected:

```text
PONG
```

The Redis instance above is only for a **rebuildable cache demo**:

- Bind the port to localhost to avoid exposing unauthenticated Redis to external networks.
- Disable AOF to simplify the lesson; this is not the default choice for all data types.
- `allkeys-lru` allows cache entries to be evicted when RAM is low.
- Do not store sessions, locks, idempotency keys, or critical business data on this demo Redis.

**In production**, authentication/ACL, TLS/network isolation, secrets, topology, memory headroom, backups if needed, and resource monitoring are required.

If the machine already has Redis on port 6379, adjust the port mapping and Spring configuration accordingly.

## 7. Configuring Spring Boot

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

Explanation:

- `spring.datasource`: H2 database exists only during the demo run.
- `ddl-auto: create-drop`: creates and drops the schema for practice; **do not use verbatim in production**.
- `spring.data.redis`: Redis server address.
- `spring.cache.type: redis`: selects Redis as the cache provider for Spring Cache.
- `show-sql`/`org.hibernate.SQL`: helps observe which requests issue a SQL `SELECT`.
- Actuator is enabled with a limited set of endpoints to inspect health/metrics in the demo.

Do not expose the H2 console, Actuator, or Redis port to the Internet just for testing convenience.

## 8. Enabling Caching

Application main class:

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

`@EnableCaching` enables the infrastructure that processes `@Cacheable`, `@CachePut`, and `@CacheEvict` in the Spring Cache mechanism.

Important: with the default proxy mode, method calls must go through the Spring-managed proxy for caching advice to take effect. If you instantiate `new ProductLookupService(...)` manually or call `this.findById(...)` internally, you should not assume the cache annotation will execute.

## 9. Creating the Product Entity

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

`BigDecimal` is more suitable than `double` when representing monetary amounts in applications that must avoid binary floating-point inaccuracies. However, this demo still does not implement currency, precision/rounding policies, or payment logic.

With JPA, a no-argument constructor with `protected` visibility allows the ORM to instantiate the entity.

## 10. Creating ProductRepository

File `ProductRepository.java`:

```java
package com.example.lookup;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
```

Spring Data JPA generates the implementation automatically. This is the read path to the **authoritative data source** on a Redis cache miss.

The repository should not know about Redis prefixes or TTLs. If you want to replace H2 with PostgreSQL, change the JDBC/driver configuration and migrations; the cache policy can remain unchanged.

## 11. Creating a DTO for the API and Cache

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

Why **cache a DTO** instead of a JPA entity?

- DTOs do not carry Hibernate lazy proxies.
- Clear JSON contract that can be versioned.
- Avoids accidentally serializing overly large relationship graphs.
- Avoids putting persistence internals into Redis.
- Reduces the risk of depending on the entity lifecycle.
- Creates a clear boundary between domain persistence and API representation.

If `ProductView` changes schema, you must consider cached values written by the previous version. In this exercise, the Redis key prefix contains `v1` so the namespace can be changed when needed.

## 12. Creating Sample Data

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

In an empty H2 database with auto-increment starting at 1, the two products usually receive IDs 1 and 2. The exact result depends on existing data and the database strategy; do not rely on a hardcoded ID 1 when deploying to production.

Seeding via `CommandLineRunner` is for demo use. In a real project, use Flyway/Liquibase or separately managed development data.

## 13. Configuring RedisCacheManager

Spring Boot can auto-create a `RedisCacheManager`, but we declare it explicitly to understand three components:

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

### Why Use a Typed ProductView Serializer?

`Jackson2JsonRedisSerializer<ProductView>` has a specific target type. This avoids enabling broad polymorphic deserialization for arbitrary types when this cache only holds `ProductView`.

**Example limitation:** `productConfig` is used as the defaults for this CacheManager. If you later create another cache for a different DTO type, do not blindly reuse the `ProductView` serializer; configure a separate serializer or separate cache configurations appropriately.

### Expected Redis Key

When calling:

```java
findById(1L)
```

with cache name `productLookup`, the string-formatted key is typically:

```text
lookup-demo:v1:productLookup::1
```

`v1` denotes the namespace version, not the Redis protocol version. If you make an incompatible wire schema change, you can switch to `v2` to avoid reading old cached data.

### Serializer Considerations

- Ensure both reader and writer use compatible schemas.
- Do not cache entities/proxies directly unless there is a specific need.
- Do not enable unrestricted polymorphic default typing for untrusted payloads.
- Set a positive TTL according to freshness needs.
- When a custom `CacheManager` is created, do not assume every `spring.cache.redis.*` property will automatically apply to your configuration.

## 14. Read Service with @Cacheable

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

Explanation:

| Component | Meaning |
| --- | --- |
| `@Cacheable` | Before running the body, Spring Cache checks the cache key |
| `cacheNames="productLookup"` | Selects the cache configured in `RedisCacheManager` |
| `key="#p0"` | Uses the first parameter as the key; avoids depending on parameter names |
| `unless="#result == null"` | Does not cache `null` results |
| `@Transactional(readOnly=true)` | Reads data through a read-only transaction when the body runs |
| `repository.findById` | Only called on a cache miss |
| `ProductView.from` | Caches the DTO instead of the JPA entity |

**Characteristic:** On a cache hit, the proxy can return the DTO from Redis **without executing the method body**. Therefore, if a log for `repository.findById` is inside the method, that log will not appear on a hit.

### What If the Product Does Not Exist?

The method throws `ProductNotFoundException`. Spring Cache does not cache an exception as a successful `ProductView`; the next query for that non-existent ID will call the database again.

That is a **no negative-cache** policy. If the workload has a high volume of non-existent IDs, you can design dedicated negative caching with a short TTL and appropriate invalidation.

## 15. Exception Returning HTTP 404

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

When the repository does not find the ID, Spring MVC returns HTTP 404.

In a production application, you can use `@RestControllerAdvice` to standardize error responses, correlation IDs, and client-facing messages while avoiding exposing internal details.

## 16. Why Do Data Updates Require Invalidation?

Suppose Redis already holds:

```text
lookup-demo:v1:productLookup::1
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 129000.00
}
```

The database is then updated to price `139000.00`. Without deleting or refreshing the cache:

```text
GET /api/products/1
    -> Redis hit
    -> still returns 129000.00
```

A 5-minute TTL only bounds how long data can remain stale; it does not provide immediate synchronization.

There are three main strategies:

- **Evict-on-write:** update the database, then delete the cache; the next read reloads it.
- **Update-on-write:** update the cache with the new value when the database changes.
- **Versioned cache:** use a version/ETag or key version, usually more complex but useful for concurrency.

This practice exercise chooses **evict-on-write after commit**.

## 17. Price Update DTO

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

For consistency, the entity also checks that `price` is non-negative. DTO validation only takes effect when the Controller call uses `@Valid`; the service still needs to guard critical invariants when called from elsewhere.

## 18. Product Changed Event

File `ProductChangedEvent.java`:

```java
package com.example.lookup;

public record ProductChangedEvent(Long id) {
}
```

The event carries only the ID needing invalidation, avoiding passing the entire JPA entity or sensitive data unnecessarily through the event.

## 19. Service Updating Price in a Database Transaction

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

Because the entity is managed by JPA within the transaction, dirty checking can perform the update at flush/commit time. `@Transactional` ensures ORM operations follow the corresponding datasource's transaction.

**Important:** `publishEvent` here does not automatically send a durable Redis event. It is an internal in-JVM event. The listener in the next step is registered to run once the transaction has committed.

## 20. Evicting Cache After Transaction Commit

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

Why use `AFTER_COMMIT`?

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

If the database transaction rolls back, the `AFTER_COMMIT` listener does not perform invalidation as a successful update.

### Does This Guarantee Absolute Synchronization Between the Database and Redis?

**No.** After the database commits, the process could still crash before Redis eviction executes. Redis might be unreachable when the listener runs. A slow cache read could also repopulate a stale snapshot after eviction.

For standard lookups, a 5-minute TTL can be an acceptable bound on stale data. When strict consistency is required, mechanisms such as a **transactional outbox**, version checking, or retryable/reconcilable invalidation are needed.

**A post-commit listener error may be surfaced to the caller even though the database has already committed.** Do not retry non-idempotent updates assuming "API error = DB unchanged". That is why production needs clear error handling and reconciliation.

## 21. Creating the REST Controller

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

`@Validated` and `ResponseEntity` are not needed for this simple Controller snippet; if your IDE reports unused imports, you can remove them during implementation. Here `@Valid` is sufficient to validate the body.

Note that the REST API is not where cache keys are directly built. The Controller calls services; caching behavior belongs in the application/service layer.

## 22. Running the Application

Start Redis:

```bash
docker compose up -d
```

Run Spring Boot:

```bash
mvn spring-boot:run
```

With a fresh H2 database, `DemoData` creates the sample data.

Look up:

```bash
curl -i http://localhost:8080/api/products/1
```

Example output:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"name":"Spring Data Redis Handbook","price":129000.00}
```

Call again:

```bash
curl -i http://localhost:8080/api/products/1
```

The first call should show a SQL `SELECT` for the product; the second call should not have another `SELECT` because Spring Cache returns the Redis value. SQL statements from initialization, other transactions, or Actuator should not be confused with the lookup query itself.

To prove accurately that the repository is not read on the second call, use the integration test in a later section rather than just eyeballing logs.

## 23. Inspecting Keys in Redis

Open CLI:

```bash
docker compose exec redis redis-cli
```

In Redis CLI:

```redis
SCAN 0 MATCH lookup-demo:v1:productLookup::* COUNT 100
```

Expected key after looking up product ID 1:

```text
lookup-demo:v1:productLookup::1
```

Read raw JSON:

```redis
GET lookup-demo:v1:productLookup::1
```

Check TTL:

```redis
TTL lookup-demo:v1:productLookup::1
```

Or TTL in milliseconds:

```redis
PTTL lookup-demo:v1:productLookup::1
```

Interpreting `TTL` values:

| Result | Meaning |
| ---: | --- |
| Positive number | Key has remaining TTL in seconds |
| `-1` | Key exists without an expiration |
| `-2` | Key does not exist |
| `0` | Remaining time is very short in seconds |

After a fresh lookup, TTL is typically around 300 seconds and decreases. Do not expect exactly 300 at every moment due to latency and elapsed time.

**Do not use `KEYS *` to scan all of production Redis when the keyspace is large.** Even though the example only has a few keys, still use `SCAN` to build good habits.

## 24. Verifying Cache Hits via SQL and Redis

Steps:

```text
1. Open Spring Boot logs.
2. GET /api/products/1 the first time.
3. Observe SELECT from JPA.
4. Redis shows the key and TTL.
5. GET /api/products/1 the second time.
6. Compare the number of SELECTs for the corresponding query.
```

If the second call still queries the database, check:

- Is `@EnableCaching` enabled?
- Is the method called through the Spring proxy?
- Does the cache name in the annotation match CacheManager?
- Is `@Cacheable` on an appropriate public method?
- Is the cache key the same across both calls?
- Is Redis evicting the entry or is the TTL expiring too quickly?
- Is there an error in the `ProductView` serializer?
- Is the custom `CacheManager` actually being used by Spring?

Do not assume the bug is on the Redis server; an unenabled AOP/caching configuration will also cause the application to always read from the database.

## 25. Updating Price and Observing Invalidation

Call:

```bash
curl -i \
  -X PUT http://localhost:8080/api/products/1/price \
  -H "Content-Type: application/json" \
  -d '{"price":139000.00}'
```

Sample output:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 139000.00
}
```

Check Redis right after the update commits:

```redis
EXISTS lookup-demo:v1:productLookup::1
```

Expected: `0`, because the listener evicted the cache after the database commit.

Call again:

```bash
curl http://localhost:8080/api/products/1
```

This read queries the database and caches the new result:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 139000.00
}
```

This is **evict-on-write** behavior: it does not push the new value directly into the cache, letting the next read refresh it instead.

In production, crashes between commit and eviction or races with in-flight cache misses require additional measures if accepting stale data is insufficient.

## 26. Querying a Non-Existent Product

Call:

```bash
curl -i http://localhost:8080/api/products/999999
```

Expected HTTP 404.

Because `findById` throws an exception when the repository returns empty, there is no `ProductView` to cache. Subsequent queries for the non-existent ID continue hitting the database.

Advantage: avoids holding a "product not found" result for too long if the product is created afterward.

Drawback: if non-existent IDs are queried heavily, the database may take load. In that case, consider a **negative cache** with a short TTL, while carefully designing a value that clearly represents non-existence and invalidating it when the entity is created.

Do not use an unmanaged null value if the cache manager has `disableCachingNullValues()`.

## 27. Difference Between TTL and Eviction

A 5-minute TTL is not a guarantee that a key will live at least 5 minutes.

The demo Redis uses:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

If Redis runs short on RAM, a key can be **evicted before its TTL expires**. The application will then see a cache miss, read from the database, and cache it again.

Causes of a cache miss can include:

- Key has never been loaded.
- Key TTL expired.
- Key was evicted.
- Application evicted it on data update.
- Cache namespace/version changed.
- Redis restarted without cache persistence.
- Redis failover led to state differences.
- Key was deleted by operational actions.

Redis `expired_keys` and `evicted_keys` in `INFO stats` help distinguish expiration from memory eviction on the server.

## 28. How Should You Choose a TTL?

There is no single optimal TTL for every kind of data.

| Data Type | Question Determining TTL |
| --- | --- |
| Product description | Can it be stale for a few minutes? |
| Product price | At which transaction step must the price be confirmed? |
| Product inventory | Does it require higher freshness or must the source of truth be read at order placement? |
| Category metadata | How infrequently does it change? |
| Public configuration | How quickly must changes take effect? |
| Search results | What are the filters/pagination and recompute cost? |

The exercise uses **5 minutes** solely for practice.

If price is used for checkout, **do not treat cached prices as the final authoritative source**. Checkout must confirm prices and inventory using appropriate transactions/business rules against the source of truth.

TTL is a stale-data safeguard; it does not replace proper transactions/invalidation.

## 29. Configuring TTLs for Multiple Different Caches

When an application has multiple caches:

```text
productLookup     -> 5 minutes
categoryLookup    -> 30 minutes
featureFlags      -> 1 minute
```

You can use `RedisCacheManager` with per-cache-name `RedisCacheConfiguration` instances. Conceptual example:

```java
Map<String, RedisCacheConfiguration> settings =
    Map.of(
        "productLookup",
        baseConfig.entryTtl(Duration.ofMinutes(5)),
        "categoryLookup",
        baseConfig.entryTtl(Duration.ofMinutes(30))
    );
```

**Do not reuse the `ProductView` serializer for `CategoryView` if the two caches hold different types.** Each cache needs an appropriate serializer/schema or a safely managed value serialization mechanism with compatibility tests.

Having multiple TTLs does not create separate memory quotas per cache. The Redis eviction policy still applies at the server/instance level.

## 30. Equivalent Approach Using RedisTemplate

If you do not want to rely on Spring Cache annotations, you can write cache-aside explicitly.

Example of a service storing JSON strings:

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

The class above is an **alternative** to annotation-based caching; it does not need to be installed simultaneously to complete the basic demo.

Pros:

- Exact control over key/value/TTL.
- Easy to express cache-aside logic with multiple conditions.
- Easy to extract into a `ProductCache` port to unit test the business service.
- Can use Lua/multi-key commands when the use case requires them.

Cons:

- Longer application code.
- Must write cache miss policy, error mapping, metrics, and invalidation yourself.
- Risk of using inconsistent serializers/prefixes across services.

## 31. Choosing @Cacheable or RedisTemplate?

| Criterion | Spring Cache annotations | RedisTemplate |
| --- | --- | --- |
| Simple lookup APIs | Very suitable | Suitable but more code |
| Per-cache TTL | CacheManager config | Set per write |
| Automatically skip body on hit | Yes via Spring proxy | Service decides itself |
| Special Redis data types | Limited by abstraction | More flexible |
| Lua/atomic operations | Not the focus | Commonly uses template/connection |
| Testing AOP | Needs Spring integration | Does not depend on annotation proxy |
| Custom fallback policy | Requires clear structure | Easy to write explicitly |
| Key/value serialization | CacheManager | RedisTemplate/serializer |
| Multiple caches and invalidation | Annotations/API available | Coordinate manually |

For `GET product by ID`, Spring Cache is a good starting point. When a use case demands atomic conditions, distinct serialization, or complex cache workflows, consider a service port and an explicit Redis adapter.

## 32. Unit Testing Logic Does Not Mean Testing the Caching Proxy

If instantiated directly:

```java
ProductLookupService service =
    new ProductLookupService(mockRepository);

service.findById(1L);
service.findById(1L);
```

`@Cacheable` **will not work**, because there is no Spring proxy. This kind of unit test only exercises the Java body; calling it twice will query the repository twice.

To prove caching, you must call through a **Spring-managed bean in an ApplicationContext** with a properly configured real CacheManager or cache test adapter.

This is why the exercise uses a Testcontainers integration test in the next step.

## 33. Testing Real Redis with Testcontainers

Testcontainers starts Redis in a test environment with a Docker-compatible runtime, instead of connecting to an uncontrolled development/production Redis.

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

### Explaining Each Assertion

- `secondLookupUsesCache`: the Spring proxy calls the repository once; the second call uses the cache.
- `cachedProductHasPositiveTtl`: the Redis key actually has an expiration, not just Java passing a `Duration`.
- `changingPriceInvalidatesCache`: the database commit triggers the listener and the cache key is deleted.
- `unknownIdIsNotCached`: does not store a negative result as a `ProductView`.

**Test fixture note:** the example relies on `DemoData` creating ID 1 on a fresh H2 database. In a real project, use a fixture that creates an entity and retrieves the actual ID rather than hardcoding; also isolate data when running tests in parallel.

`@MockitoSpyBean` is for corresponding newer Spring Framework/Spring Boot versions. Older projects may use another annotation/spying approach, but ensure the repository is a Spring-managed bean.

Do not assume example code has already been tested simply because it appears in documentation; learners must execute it in their own environment.

## 34. Why Not Just Mock RedisTemplate?

A test like:

```java
when(valueOperations.get(key)).thenReturn(json);
```

only verifies stub handling logic; it does not confirm:

- A real Redis connection works.
- Cache key serialization is correct.
- `RedisCacheManager` applies TTL.
- JSON record round-tripping works.
- The Spring AOP proxy actually activates.
- The cache entry exists or is deleted in Redis.
- Whether eviction removes keys early.
- Redis driver exceptions are mapped properly.

Mockito is still valuable for **unit testing business decisions**, especially when a service depends on a `ProductCache` port. However, to verify Redis behavior, a Redis integration test is needed.

## 35. Testing Cache Miss and the Source of Truth

An important test requirement:

1. Redis does not have the key.
2. The database has the product.
3. `findById` returns the right DTO.
4. Redis receives the new key with a TTL.
5. The second read does not call the database.

That is the basic cache-aside contract.

Another requirement:

1. Redis does not have the key.
2. The database does not have the product.
3. HTTP returns 404.
4. An unmanaged JSON null is not written to Redis.

Do not just check that the first `GET` returns a response. Without asserting that the next call actually hits the cache, the exercise has not verified caching benefits.

## 36. Observing Performance: Controlled Comparison

The goal of caching is to reduce work on the database and potentially improve latency. However, a small manual measurement does not prove production performance.

An experiment:

```text
Phase A: cold cache
  - clear test key
  - call GET the first time
  - measure latency, DB SELECT, Redis miss

Phase B: warm cache
  - call GET with the same ID multiple times
  - measure latency, DB SELECT, Redis hit

Phase C: cache invalidate
  - PUT to change price
  - GET again
  - measure latency, DB SELECT, value correctness
```

Variables to keep stable:

- Same Redis/JVM/database topology.
- Same ID and payload.
- HTTP connection reuse or a suitable load testing tool.
- JVM warm-up.
- Request count/concurrency.
- Database indexes and query plan.
- Network latency.
- Logging overhead.

Seeing one read appear faster in Redis is not enough to infer that p99 latency will be better across all workloads.

## 37. Monitoring Memory and Eviction

Redis provides:

```bash
docker compose exec redis redis-cli INFO memory
docker compose exec redis redis-cli INFO stats
docker compose exec redis redis-cli INFO keyspace
```

Useful fields:

| Field | Meaning |
| --- | --- |
| `used_memory` | Memory used by the Redis allocator |
| `used_memory_rss` | Resident memory as seen by the OS |
| `maxmemory` | Configured limit |
| `maxmemory_policy` | Eviction policy |
| `keyspace_hits` | Number of successful key lookups in Redis stats |
| `keyspace_misses` | Number of key lookups not found |
| `expired_keys` | Expired keys |
| `evicted_keys` | Keys evicted due to memory policy |

Do not take `used_memory < maxmemory` as proof that process RSS is always below the container limit. Memory buffers, fragmentation, and persistence can push RSS higher.

In the `allkeys-lru` demo, eviction when the dataset grows is permitted behavior. In production, check whether it causes abnormal increases in DB fallback and API latency.

## 38. Observing at the Spring Boot Layer

Actuator can expose JVM, HTTP server, and some integration metrics depending on configuration/instrumentation. Do not assume every version exposes exact per-cache-name Redis hit/miss metrics out of the box.

You can call:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
```

When accurate business cache hit/miss measurement is needed:

- Use instrumentation in the appropriate cache abstraction/adapter.
- Attach the cache name rather than user IDs as labels.
- Measure hits/misses, latency, errors, and fallbacks.
- Count DB queries or connection pool pressure.
- Measure cache warm-up time after a restart.

Do not put raw Redis passwords, sensitive keys, tokens, or personal information into metrics/logs.

## 39. Redis Disconnection: Cache Miss and Error Are Different

In the `@Cacheable` example, if the Redis server shuts down, a Redis cache lookup can throw an exception rather than automatically executing the method to read the database. Spring Cache does not promise "always fall back to DB when Redis is down" unless a suitable error handler is configured.

A policy must be chosen:

| Redis Role | What Happens When Redis Is Unavailable? |
| --- | --- |
| Product cache with DB source of truth | Can fall back to the database if load is controlled |
| Mandatory session store | May need to return an error/redirect to login flow |
| Abuse-prevention rate limiter | Do not default to fail-open |
| Distributed lock | Must not ignore errors and assume the lock is held |
| Idempotency | Must not proceed with side effects without duplicate checks |

For a product cache, you can configure a `CacheErrorHandler` to ignore **certain cache infrastructure errors** and let the service run the method body, while still accounting for read errors, write errors, metrics, circuit breakers, and avoiding hiding corrupt cache data unintentionally.

## 40. CacheErrorHandler: Monitored Fail-Open Demo

A simple example extending via `CachingConfigurer`:

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

**This is an optional policy example**, not a required part to run the basic exercise. Add it to a project **only after understanding the system's contract**.

Notable points:

- Not throwing an exception from the handler can allow the caching interceptor to proceed according to Spring's corresponding behavior.
- Logging every error under load can cause a log storm; production needs metrics and rate-limited logging.
- Ignoring `evict` errors allows stale cache entries to continue being read after a DB commit; TTL only bounds staleness, which may not satisfy the SLA.
- Ignoring every `RuntimeException` can hide serializer/configuration bugs; classify errors and emit appropriate alerts.
- Do not use this fail-open policy for Redis storing locks, critical rate limits, or idempotency state.

A **best-effort** cache policy must be explicitly designed instead of implicitly treating every Redis exception as a cache miss.

## 41. Cache Stampede: Multiple Concurrent Cache Misses

A hot key is evicted or its TTL expires:

```text
               500 clients
                    |
                    v
       GET /api/products/1 simultaneously
                    |
                    v
          Redis cache miss
                    |
                    v
       Many SELECTs for the same ID on DB
```

This is a **cache stampede**. By default, `@Cacheable` does not guarantee that only a single request across the entire cluster loads the data.

Some options:

- `@Cacheable(sync = true)` can reduce concurrent loading within what the provider/implementation supports, but check `RedisCacheManager` semantics and do not infer distributed single-flight across multiple pods.
- Request coalescing at the service layer.
- TTL jitter to reduce many keys expiring at the exact same moment.
- Pre-warming hot keys.
- A front-tier local cache with an appropriate consistency policy.
- Rate limiting DB fallback.
- Allowing stale-while-revalidate if business rules permit.
- Distributed locking or job coordination when recompute cost is very high, along with failure handling.

If one pod holds a cache-loading lock and another times out, define clear behavior; do not add locks just to "solve performance" without understanding the complexity.

## 42. TTL Jitter for Many Keys

If thousands of keys are cached by a batch job at 00:00 with the same 300-second TTL, they may expire almost simultaneously at 00:05.

One way to reduce synchronization is adding jitter:

```text
TTL = 300 seconds + random(0..30 seconds)
```

With `RedisTemplate`, each `put` can set its own TTL. With `RedisCacheManager`, Spring Data Redis versions support dynamic expiration mechanisms like `TtlFunction` in the configuration; check the API of the version in use.

**Do not arbitrarily apply TTL jitter to OTPs, locks, sessions, or mandatory business deadlines.** Jitter is better suited to rebuildable caches where acceptable staleness can vary slightly.

TTL jitter does not replace capacity planning; if the working set exceeds RAM, eviction will still occur.

## 43. Concurrency: Stale Cache Can Appear Despite Post-Commit Eviction

An important cache-aside race:

```text
T0 Reader A: cache miss
T1 Reader A: SELECT old price = 129000
T2 Writer B: UPDATE price = 139000, COMMIT
T3 Writer B: EVICT cache key
T4 Reader A: SET cache = 129000 (slow read, late write)
T5 Reader C: cache hit old price
```

Because Reader A read the database before Writer B committed, it can write the old price **after** eviction.

`AFTER_COMMIT` invalidation orders correctly relative to the update transaction itself, but **does not eliminate all races** between readers and writers.

Solutions when consistency requirements are high:

1. Cache payloads with a `version` so a newer version is not overwritten by an older one.
2. Use Lua/conditional updates if the key/version design allows it.
3. Invalidate again using an appropriate delayed/retry mechanism or event processing, while analyzing new races.
4. Use a transactional outbox and replayable invalidation.
5. Short TTLs and authoritative confirmation at critical business points.
6. Choose not to cache certain fields requiring linearizable reads.

Do not claim cache-aside is strongly consistent simply because `@CacheEvict` is present.

## 44. Transactional Outbox for Reliable Invalidation

If missing an invalidation after DB commit is unacceptable, you can use this pattern:

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
Outbox worker reads unprocessed events
    |
    v
Redis evict/update cache
    |
    v
Mark outbox event processed / retry
```

Benefits:

- If the application crashes after the database commits, the outbox event remains.
- Workers can retry.
- Versions can be attached to handle out-of-order events.
- A Redis outage does not lose committed business write transactions.

Limitations:

- The cache may be stale until the worker processes the event.
- Duplicate events/idempotency must be managed.
- Not an atomic distributed transaction between DB and Redis.
- Requires monitoring backlog and retry errors.

For a simple lookup demo, TTL + after-commit eviction is sufficient for learning. For checkout pricing or systems requiring tight read consistency, additional design is needed.

## 45. Negative Caching: Caching "Not Found" Results

An API receiving many requests for invalid IDs can continuously hit the DB.

A solution can be a sentinel value:

```text
lookup-demo:v1:productMissing::999999 -> NOT_FOUND
TTL 15 seconds
```

When using negative caching:

- Must distinguish "product does not exist" from "Redis error".
- Do not let an old negative cache hide a newly created product.
- Set an appropriately short TTL.
- Invalidate the negative key when the entity is created.
- Do not use an ambiguous `null` if the serializer/cache manager does not support it.
- Enforce input validation and protect the API from ID enumeration abuse.

The basic exercise chooses no negative-cache to keep the example easy to follow.

## 46. Redis Key Naming and Versioning

A good key in the demo:

```text
lookup-demo:v1:productLookup::1
```

Parts:

```text
lookup-demo  -> application/namespace
v1           -> cache schema version
productLookup-> cache name
1            -> business key
```

Benefits:

- Easy to find in Redis CLI.
- Avoids key collisions across applications.
- Easy to transition serializer versions.
- Easy to separate environments.
- Easy to monitor by cache group.

In a multi-tenant environment, keys may need tenant scope to avoid returning the wrong data:

```text
app:v1:tenant:{tenant-id}:product:{product-id}
```

Do not put tokens, passwords, or sensitive plaintext data in key names; Redis keys can appear in logs/metrics or operational tools.

Prefixes **do not create memory quotas**. If Redis holds both cache and idempotency/lock state, an instance-level eviction policy can affect both; consider separating Redis instances/deployments.

## 47. Serializer Compatibility Across Releases

Suppose v1 caches:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 129000.00
}
```

v2 adds:

```json
{
  "id": 1,
  "name": "Spring Data Redis Handbook",
  "price": 129000.00,
  "currency": "VND"
}
```

Questions:

- Does a v1 reader ignore the new field?
- How does a v2 reader handle old cache entries missing `currency`?
- Did `price` change type from number to string?
- Are multiple versions deployed reading the same cache namespace?
- Is there cache key versioning or a migration strategy?

Changing the prefix from `v1` to `v2` avoids reading old-schema cache entries when backward compatibility cannot be maintained, at the trade-off of increased warm-up/misses during the transition.

Integration tests should verify round-tripping and readability of sample payloads from still-supported versions.

## 48. Do Not Directly Cache Data Containing Secrets

Every caching strategy needs data classification.

Examples safe to cache:

- Public catalogs.
- Non-sensitive product metadata.
- Query results that have already been properly authorized/filtered.
- Data with a TTL and acceptable staleness.

Exercise caution with:

- Access tokens or refresh tokens.
- Unnecessary personal data.
- Credentials.
- Per-user/tenant permissions.
- Payment state.
- Role- and authorization-dependent content.

If a query result depends on the user/tenant, the cache key must include **all context needed to distinguish the result**, or you must cache authorization-independent data and filter access at the appropriate layer.

Do not use a cache key of only `productId` for data that varies by tenant if doing so could leak data across tenants.

## 49. Redis Cluster: One Cache Key Belongs to One Hash Slot

In Redis Cluster, Redis distributes keys across 16,384 hash slots. `@Cacheable` per product is a single-key operation, which generally works smoothly with cluster-aware clients.

However:

- Bulk cache clearing may require scanning multiple cluster nodes.
- A standalone Testcontainers Redis does not test Cluster routing.
- Lua/multi-key commands have same-slot constraints.
- `MOVED`/`ASK` redirects can occur during failover/resharding.
- Replica reads may return stale snapshots due to replication lag.
- A hot key still resides on one shard and is not automatically load-balanced by hash slots.

If production uses Redis Cluster, run integration/fault tests against a real Cluster when these behaviors matter; do not infer from a standalone demo that all cluster behavior is correct.

## 50. Eviction Policy and Data Characteristics

The demo Redis uses `allkeys-lru`, which fits when **every key on the instance is rebuildable cache**.

Do not share the same Redis pool for:

```text
cache:product:42
session:user:1001
lock:order:42
idempotency:payment:req-123
```

and assume an eviction policy will distinguish data types by prefix.

- `allkeys-*` can evict any key.
- `volatile-*` can evict any key with a TTL, including sessions/locks/idempotency keys.
- `noeviction` does not proactively evict, but may reject writes when full.
- TTL does not guarantee a key survives until expiration.

For lookup caches, tolerating misses and rebuilding data is the key to using eviction safely.

## 51. Redis Outage and Database Fallback Under Load

You can design fail-open for a lookup cache, but suppose Redis serves 90% of 20,000 GET/s.

When Redis goes offline, most requests shift to the DB. This can overload the database.

Mitigations:

- Circuit breaker for cache infrastructure.
- Concurrency limits to the database.
- Request coalescing for hot keys.
- Rate limiting / load shedding.
- Short-lived local cache if consistency allows.
- Proper database indexes and query plans.
- Load testing fallback scenarios.
- Monitoring Redis errors, DB query rate, and p95/p99 latency.

**A test proving fallback can read from the DB does not mean the system can survive full fallback load.** Separate capacity planning is required.

## 52. Testing Sudden Cache Deletion

In the demo Redis, after calling GET for a product:

```bash
docker compose exec redis \
  redis-cli DEL 'lookup-demo:v1:productLookup::1'
```

Call again:

```bash
curl http://localhost:8080/api/products/1
```

The result must still return the product from the database and re-cache it.

This test proves the application **does not depend on the cache entry always existing**.

Do not run `FLUSHALL` on a Redis instance containing data outside the demo. Even during practice, delete only your specific key or test namespace.

## 53. Testing TTL Expiration

You can shorten the TTL in test configuration or use a few seconds of TTL in a separate Redis test.

Procedure:

1. Ensure the test key does not exist yet.
2. Call `GET` to create the cache entry.
3. Verify `PTTL` is positive.
4. Poll the key with a finite timeout.
5. Once expired, call `GET` again.
6. Verify the repository is queried again.
7. Do not assert that the key disappears at the exact millisecond of the deadline.

Redis handles expiration via server mechanisms; keyspace notifications may arrive after the logical TTL ends. Tests should rely on key readability/TTL rather than event timing alone.

## 54. Testing Data Updates and Rollbacks

The demo already tested invalidation after a successful commit. To extend it:

- A transaction updates a product and then rolls back.
- `ProductChangedEvent` is published within that transaction.
- The `AFTER_COMMIT` listener does not execute for a rolled-back transaction.
- The Redis cache is not deleted just because of an uncommitted change.
- The database retains the old price.
- If the transaction commits and eviction fails, the application has a retry/reconciliation strategy.

One way to test rollback is writing an auxiliary test service using `TransactionTemplate` and intentionally throwing an exception inside the transaction. Do not just mock `@Transactional` and claim commit semantics are proven.

## 55. Do Not Confuse Cache Hit with Read-Your-Writes

If an application updates the database and then reads from a Redis replica, Redis replication may lag. In the standalone demo, this issue does not appear.

In production Redis Sentinel/Cluster:

```text
T0 write cache entry to primary
T1 primary ACK
T2 GET routed to replica
T3 replica has not applied the new write yet
```

Depending on the client's `ReadFrom` policy, results can be stale. For data used at critical decision points, read the authoritative source under an appropriate consistency policy.

Spring Cache does not automatically guarantee linearizability across Redis replicas and the database.

## 56. When Updating Price, Should You Use @CacheEvict or @CachePut?

Two common choices:

| Criterion | `@CacheEvict` | `@CachePut` |
| --- | --- | --- |
| After update | Deletes key | Writes new snapshot |
| Next read | Cache miss/reload | Can hit immediately |
| Stale race possibility | Still possible | Still possible if ordering is wrong |
| Serialization | Does not write new value at evict time | Must serialize new DTO |
| Transaction timing | Needs after-commit policy | Needs after-commit policy |
| Code/logic | Simple | Requires exact key and result |

`@CachePut` runs the method and updates the cache regardless of prior entries, but when combined with `@Transactional`, the timing of cache put relative to commit must be verified against Spring advice/transaction configuration.

In this exercise, post-commit eviction is simpler for learning and avoids caching uncommitted snapshots as authoritative.

## 57. Additional Practice: Searching by Name

The exercise currently only looks up by ID. When extending to:

```http
GET /api/products?name=redis&page=0&size=20&sort=name,asc
```

The cache key **must include every parameter affecting the result**, for example:

```text
search:v1:name=redis:page=0:size=20:sort=name_asc
```

If only `name` is used as the key while omitting `page/size/sort`, different queries could receive the wrong cached result.

Other considerations:

- Normalize filters, case, and whitespace.
- Prevent key cardinality explosion from free-form queries.
- Search result TTLs are usually shorter than rarely changing data.
- Invalidating search caches is more complex than a single product ID key.
- Do not cache unboundedly large pagination offsets.
- Avoid storing results with different authorizations under the same key.

A follow-up exercise can build `SearchCriteria` canonicalization for safe cache key identification.

## 58. Common Implementation Pitfalls

| Symptom | What to Check |
| --- | --- |
| Calling twice still executes SELECT | `@EnableCaching`, proxy, CacheManager, key |
| Redis has no key | Service bypassed proxy, write failed, TTL too short |
| `ClassCastException` on cache read | Mismatched serializer/type configuration |
| Unreadable JSON payload | DTO/schema/Jackson compatibility |
| Price still stale after update | Not evicted, listener didn't run, race, Redis error |
| All requests fail when Redis is down | Missing fail-open/error handler design |
| Tenant A data returned to Tenant B | Cache key missing tenant/auth context |
| TTL is `-1` | Cache key has no expiration |
| TTL is `-2` | Key missing/expired/evicted/never written |
| `evicted_keys` increasing | Memory pressure and eviction policy |
| Redis OOM despite remaining DB capacity | `noeviction`/memory budget or memory overhead |
| Cache stampede | Hot key expired/evicted concurrently |
| Mockito tests pass but caching doesn't work | Test didn't go through Spring proxy/real Redis |
| Testcontainers fails to start | Docker runtime, image availability, CI config |
| DB update committed but cache not deleted | Process crash/Redis outage after commit |
| Slow cache clear on Cluster | Cache writer and scan strategy, multiple nodes |

When investigating, check logs from Spring, the database, and Redis; do not draw conclusions solely from the HTTP response.

## 59. Pre-Production Checklist

**Data contract**

- Database/source of truth is defined.
- Cache DTO and schema version are clear.
- Sensitive data is not cached unnecessarily.
- Cache keys include tenant/authorization context if it affects results.
- TTL is based on acceptable staleness.

**Spring Data Redis**

- `@EnableCaching` and proxies actually work.
- `RedisCacheManager` has proper prefix, serializer, and TTL.
- `@Cacheable` uses stable keys.
- Post-commit cache invalidation and error handling are designed.
- Unintended exceptions/nulls are not cached.
- If using manual `RedisTemplate`, an appropriate port/failure contract exists.

**Redis server**

- Authentication, TLS/network isolation configured per environment.
- Memory limits and eviction fit **cache-only** usage.
- Capacity/headroom, metrics, and alerts are in place.
- HA strategy exists when Redis availability matters.
- Not sharing instances with lock/idempotency state needing different policies.

**Testing/operations**

- Unit tests cover business behavior.
- Redis integration tests cover serialization, TTL, and eviction.
- Spring integration tests cover annotations/proxies.
- Load tests cover warm/cold cache and DB fallback.
- Update/rollback/race tests exist if consistency is critical.
- Metrics cover hits/misses, Redis errors, DB load, and latency.
- Runbooks exist for Redis outages, eviction spikes, and cache stampedes.

## 60. Exercise A — Complete the Lookup API

Implement the entire project and perform:

1. Start Redis with Docker Compose.
2. Run Spring Boot.
3. Call `GET /api/products/1` the first time.
4. Use Redis CLI to inspect `GET` and `TTL`.
5. Call `GET` a second time.
6. Observe the `SELECT` count.
7. `PUT` to change the price of product 1.
8. Verify the cache key is deleted.
9. Call `GET` again and confirm the new price.
10. Call `GET` for a non-existent ID and confirm 404.

Write down the data flow diagram that the application itself traversed at each step.

## 61. Exercise B — Optimize TTL

Suppose:

```text
productName: changes very rarely
productPrice: changes a few times/day
stockAvailable: changes continuously
```

Do the following:

1. Choose a TTL or decide not to cache each field.
2. Identify which fields must be re-read from the database at checkout.
3. Propose cache names and key prefixes.
4. Check actual TTL using `PTTL`.
5. Explain why a 5-minute TTL does not guarantee a key lives a full 5 minutes under eviction.

## 62. Exercise C — Implement Manual Cache-Aside

Replace `@Cacheable` with a `ProductCache` port and Redis adapter:

```java
public interface ProductCache {
    Optional<ProductView> find(Long id);
    void put(ProductView value, Duration ttl);
    void evict(Long id);
}
```

Do the following:

1. Write a service with explicit hit/miss branches.
2. Unit test the service by mocking `ProductCache` with Mockito.
3. Integration test the adapter using Redis Testcontainers.
4. Compare line counts and custom error handling capabilities.
5. Explain why Mockito alone does not prove TTL/serialization.

## 63. Exercise D — Simulate a Redis Outage

In the demo environment:

```bash
docker compose stop redis
```

Call the API:

```bash
curl -i http://localhost:8080/api/products/1
```

Observe the behavior before adding a cache fail-open policy. Then study and apply `CacheErrorHandler` for the **cache-only use case**, logging the error while still reading the database per policy.

Restart Redis:

```bash
docker compose start redis
```

Check whether the app recovers.

Do not extend fail-open to OTPs/locks/rate limiters without analyzing security/business behavior.

## 64. Exercise E — Stale Data Due to Concurrency

Build a test with two threads:

1. Reader A experiences a cache miss and reads old data from the database.
2. Reader A is paused before writing to the cache.
3. Writer B updates the price and commits.
4. Writer B invalidates the cache.
5. Reader A resumes and writes the old price to the cache.
6. Reader C can now read stale cache data.

Propose how to use versioning, outbox, additional invalidation, or authoritative confirmation to address this per SLA.

A concurrency integration test with barriers and timeouts is more valuable than a single-threaded test that only calls `verify(cache).evict()`.

## 65. Frequently Asked Questions

**What is cache-aside?**

The application reads the cache first; on a miss, it reads the authoritative database and populates the cache.

**Why is the first call slower than the second?**

The first call includes a DB query and a cache write; the second can be served from Redis. Actual results depend on real-world latency/network/load.

**Does @Cacheable automatically create a database transaction?**

No. Caching and transactions are separate concerns; `@Transactional` configures the transaction, and advice ordering can affect timing.

**Can JPA entities be cached directly?**

Possible in some projects, but prone to lazy proxies, schema coupling, and serialization problems; DTOs are usually easier to control.

**Does a 5-minute TTL mean a key cannot be deleted before 5 minutes?**

No. Redis eviction, explicit deletion, failover, or restarts can make a key disappear early.

**Does a cache hit call the repository?**

When the `@Cacheable` interceptor is active and the key hits, the service body is typically skipped, so the repository is not queried on that path.

**Why does instantiating the service directly with `new` not cache?**

Because `@Cacheable` normally runs through a Spring AOP proxy, not a plain Java method call.

**Why is @EnableCaching needed?**

To activate the infrastructure that processes cache annotations in Spring.

**When updating the database, when should the cache be deleted?**

At a minimum, consider doing so after the transaction commits; an `AFTER_COMMIT` event listener can be used. For higher reliability requirements, outbox/retry/reconciliation and race analysis are needed.

**After evicting the cache, will the new price always be read?**

Not strictly guaranteed under all concurrency scenarios; an in-flight reader might write stale cache after eviction, or replica/database reads might not reflect the update as expected.

**Should @CachePut be used?**

It can be used when you want to proactively write a new value into the cache, provided key/result/transaction timing and concurrency consistency are handled properly.

**When Redis is down, does @Cacheable automatically fall back to the DB?**

Not by default. Redis cache lookups may throw exceptions; an explicit error handler/policy is needed when Redis is strictly a cache.

**Is a Testcontainers Redis identical to a production Redis Cluster?**

No. It is standalone Redis only. Cluster-specific behavior requires separate topology tests.

**Should every GET API be cached?**

No. Only cache queries with significant cost, acceptable staleness, and reasonable key cardinality.

**Is the Redis cache the source of truth?**

Not in this example. The database holds authoritative data; Redis only stores rebuildable snapshots.

**Can caching be used for per-tenant data?**

Yes, provided cache keys and authorization accurately isolate results; otherwise data can leak between tenants.

**Should TTL tests use Thread.sleep?**

Avoid relying on sleeping right at the boundary; instead verify positive TTL and poll with a timeout.

**Why is Redis evicted_keys increasing?**

The Redis memory policy may be removing keys to stay within budget. For a cache-only pool, this can be normal behavior, though hit ratio and database load must still be monitored.

## 66. Summary

This exercise designed a data lookup API following the path:

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

And, when updating prices:

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

Key takeaways:

1. **The database is the source of truth; the Redis cache is a copy.**
2. `@Cacheable` simplifies cache-aside but requires a working Spring proxy and CacheManager.
3. **TTL, cache prefix, and serializer** must be configured and tested in practice.
4. **Cache hits** should be proven by skipping the repository, not merely by HTTP 200.
5. **Post-commit invalidation** improves correctness but does not eliminate all races or crash windows.
6. **Redis outages** require an explicit policy; caches can fall back to the DB, but the database must be protected from stampedes.
7. **Integration tests with real Redis** verify keys, DTO serialization, TTL, and eviction.
8. **Redis eviction and TTL are different**; cache loss is a condition the application must handle.
9. For critical business data, design dedicated transactions/idempotency/sources of truth rather than relying blindly on cache.
10. Demo configurations must be replaced with appropriate topology, auth, metrics, and capacity plans in real deployments.

The expected outcome after running it yourself is an API with accurate data, observable cache hits/misses, TTL verified via Redis CLI, invalidation after updates, and an integration test suite that prevents common caching mistakes.

## Official References

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
