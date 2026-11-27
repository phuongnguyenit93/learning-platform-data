# Organizing Configuration, Service, and Repository Code

## 1. Goal of Code Organization in Spring Data Redis

When first connecting Redis with Spring Boot, you might put all logic inside one controller: read Redis settings, create a client, assemble key names, issue Redis commands, map data, and return an HTTP response. That works for a tiny demo, but quickly becomes hard to maintain once multiple features access Redis.

With Spring Data Redis, establish three core boundaries:

- **Configuration:** builds and configures infrastructure components such as connections, templates, serializers, and Redis-specific properties.
- **Repository (data access):** provides ways to save, find, and delete data; this can be a Spring Data–implemented repository or a custom adapter built on `RedisTemplate`.
- **Service (business logic):** decides when to read/write, which data is valid, which operations must coordinate, and what result to return to the rest of the application.

Outside these three layers there are usually **domain/model** (data definitions) and **controller/handler** (receives requests and marshals data to/from HTTP or messages).

~~~text
                HTTP / Message / Scheduler
                           |
                           v
                Controller / Handler
                - request / response
                - external protocol
                           |
                           v
                     Service
                - business rules
                - orchestrates operations
                           |
             +-------------+--------------+
             |                            |
             v                            v
    Spring Data Repository       RedisTemplate Adapter
    - object CRUD                 - specific Redis commands
    - @RedisHash mapping          - key / TTL / counter / script
             |                            |
             +-------------+--------------+
                           |
                           v
               ConnectionFactory / Redis
               - connection, auth, topology
               - serialization / driver
~~~

This diagram shows the standard dependency direction. **Services do not need to know the Redis address, Lettuce connection details, or per-value serializers**; those belong in the configuration and data-access layers.

## 2. Separating Configuration, Service, and Repository by Responsibility

| Component | Responsible For | Should Not Be Responsible For |
|---|---|---|
| **Configuration** | Connection factory beans, templates, serializers, connection setup, property binding | Processing orders, checking profile edit permissions, business decisions |
| **Repository** | Persisting and retrieving Redis data under a clear contract | Driving HTTP flow, returning 404 status codes, formatting responses |
| **Service** | Business rules, business-level validation, coordinating repositories | Creating a Redis connection per request, hardcoding Redis URLs or credentials |
| **Domain/Model** | Entity structure, data, and attribute semantics | Calling Redis inside getters/setters |
| **Controller** | Receiving input, delegating to service, returning HTTP responses | Writing Redis commands or managing Redis keys directly |

Business example: "Create a customer profile and save it to Redis."

1. The controller receives **email** and **displayName**.
2. The service validates formatting, generates an ID, and calls the repository to save.
3. The repository converts the entity into Redis data via Spring Data mapping.
4. The connection factory and driver send commands to Redis.
5. The service returns the result and the controller builds the response.

If one day you replace Redis with another store or add a database as the primary source of truth, the main changes stay within storage contracts and the infrastructure layer. Conversely, if the API shifts from HTTP to a message consumer, the service can remain intact.

## 3. Sample Directory Structure for a Spring Boot Application

Example application under package **com.example.customer**:

~~~text
src/main/java/com/example/customer/
├── CustomerApplication.java
├── config/
│   ├── RedisClientConfig.java            # Only when custom template is needed
│   └── RedisKeyNames.java                # Key naming rules for Redis commands
├── domain/
│   └── CustomerProfile.java              # Model stored via Redis Repository
├── repository/
│   └── CustomerProfileRepository.java    # CRUD/query contract
├── service/
│   ├── CustomerProfileService.java       # Profile business logic
│   └── PageViewService.java              # Page view counter logic
└── web/
    └── CustomerProfileController.java   # HTTP API

src/main/resources/
└── application.yml
~~~

This is a layered layout suited for small-to-medium apps; not every project needs these exact directory names. In larger systems, you can group by feature—such as **customer/**, **session/**, **metrics/**—and place **config/** in a shared package. What matters is keeping each component's responsibility consistent.

The **CustomerApplication** class should sit in the root package so Spring Boot's component scanning discovers **@Configuration**, **@Service**, **@RestController**, and repositories in subpackages:

~~~java
package com.example.customer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomerApplication {
    public static void main(String[] args) {
        SpringApplication.run(CustomerApplication.class, args);
    }
}
~~~

Placing packages outside the scan scope without extra configuration is a common reason Spring fails to find beans.

## 4. Initializing Dependencies and Connection Settings

### 4.1. Dependencies

An imperative Spring Boot application using Redis typically declares the starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**spring-boot-starter-data-redis** integrates Spring Data Redis and the Redis driver configured by Spring Boot, commonly Lettuce by default. The web starter is only needed when the example includes HTTP controllers; worker or CLI applications do not necessarily need it.

Do not independently declare multiple mismatched versions of Spring Data Redis, Lettuce, and Spring Boot when using Spring Boot dependency management, unless you have a verified compatibility requirement.

### 4.2. `application.yml`

Example connecting to local Redis:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Settings such as host, port, TLS, credentials, timeouts, and Cluster/Sentinel topology should be injected through the deployment environment or application configuration mechanisms. Never commit real passwords into source files.

In standard setups, Spring Boot automatically supplies **RedisConnectionFactory**, **RedisTemplate**, and **StringRedisTemplate** when auto-configuration conditions hold. Therefore, **you do not need to manually instantiate `LettuceConnectionFactory` just for basic CRUD**.

Cases where adding a dedicated configuration class makes sense include: needing explicit serializers, multiple templates for different data formats, driver/connection customization, or infrastructure rules not covered by properties.

### 4.3. Scope of `RedisConnectionFactory`

~~~text
application.yml
   |
   v
Spring Boot auto-configuration
   |
   v
LettuceConnectionFactory
   |-- RedisTemplate<String, ...>
   |-- StringRedisTemplate
   +-- Spring Data Redis repositories
   |
   v
Redis server
~~~

**RedisConnectionFactory** is the infrastructure abstraction for synchronous Redis access. It supplies connections to templates and repository mapping infrastructure. The factory's lifecycle should be managed by Spring, never recreated on every service call.

**RedisTemplate** provides a high-level API for Redis operations and uses serializers. **StringRedisTemplate** specializes in string keys and values, making it convenient for counters and flags. Injecting a template does not require services to manage or release connections manually.

## 5. Organizing the Domain Model with Redis Repository

Spring Data Redis supports **key-value repositories** for objects mapped via annotations such as **@RedisHash** and **@Id**.

Consider a customer profile entity:

~~~java
package com.example.customer.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customer_profile")
public class CustomerProfile {
    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;

    public CustomerProfile() {
    }

    public CustomerProfile(String id, String email, String displayName) {
        this.id = id;
        this.email = email;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Meaning of the annotations:

| Annotation | Role |
|---|---|
| **@RedisHash("customer_profile")** | Declares that the entity is stored under the Redis keyspace named **customer_profile**. |
| **@Id** | Marks the entity identifier used to construct the storage key. |
| **@Indexed** | Instructs Spring Data Redis to maintain a secondary index for querying by the annotated attribute. |

When saving an object with ID **42**, Spring Data Redis typically uses a key in a keyspace like **customer_profile:42** to store a hash and may create additional metadata/index keys. This is **not** a JSON string saved by a plain **SET** command. Consequently, trying to read the same key via **StringRedisTemplate.opsForValue().get(...)** can hit Redis **WRONGTYPE** errors; to read mapped objects, use the corresponding repository.

Marking **@Indexed** does not enforce a unique constraint. Two objects can still share the same **email** unless the application enforces uniqueness separately. Indexes also generate extra keys and update overhead; create them only when query needs justify them.

A repository model represents storage structure. In larger applications, you can separate **storage entities** from **domain models** and public DTOs so HTTP payloads are not tightly coupled to the Redis schema.

## 6. Creating a Redis Repository: Focusing on Data Access

The repository interface extends a Spring Data contract:

~~~java
package com.example.customer.repository;

import com.example.customer.domain.CustomerProfile;
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, String> {

    List<CustomerProfile> findByEmail(String email);
}
~~~

This is an interface; with proper repository configuration, Spring Data Redis generates the implementation at application startup. Common methods:

- **save(entity)**: saves or updates an entity by ID.
- **findById(id)**: returns **Optional<CustomerProfile>**.
- **existsById(id)**: checks whether an ID exists.
- **deleteById(id)**: deletes an entity.
- **findByEmail(email)**: queries by an indexed attribute.

Note: query derivation in **Redis Repositories** is not equivalent to SQL/JPA query engines. Redis is not a relational database, has no joins, and will not execute arbitrary complex queries just by renaming a method. Attribute queries must be supported by Spring Data Redis's indexing and mapping mechanism.

### When Must You Use `@EnableRedisRepositories`?

In a Spring Boot app with proper package layout and starter dependencies, auto-configuration normally detects and enables Redis repositories. Do not add manual configuration annotations just to make an interface work.

When you need explicit scan packages or have complex multi-module configs, you can declare it explicitly:

~~~java
package com.example.customer.config;

import com.example.customer.repository.CustomerProfileRepository;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(basePackageClasses = CustomerProfileRepository.class)
public class RedisRepositoryConfig {
}
~~~

Add this configuration only when you truly need to control scan boundaries. Avoid declaring overlapping repository configurations that lead to bean conflicts or duplicate registrations.

## 7. Putting Business Rules in the Service

The service receives the repository via constructor injection and provides meaningful application-level behavior:

~~~java
package com.example.customer.service;

import com.example.customer.domain.CustomerProfile;
import com.example.customer.repository.CustomerProfileRepository;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class CustomerProfileService {
    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public CustomerProfile create(String email, String displayName) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Display name is required");
        }

        CustomerProfile profile = new CustomerProfile(
            UUID.randomUUID().toString(),
            email,
            displayName
        );
        return repository.save(profile);
    }

    public Optional<CustomerProfile> findById(String id) {
        return repository.findById(id);
    }

    public CustomerProfile rename(String id, String newDisplayName) {
        if (newDisplayName == null || newDisplayName.isBlank()) {
            throw new IllegalArgumentException("Display name is required");
        }

        CustomerProfile profile = repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Profile not found"));

        profile.setDisplayName(newDisplayName);
        return repository.save(profile);
    }
}
~~~

The service does not need to know how **customer_profile:42** is stored as a Redis hash, does not convert POJOs to bytes, and does not open Redis connections. ID generation, input validation, and coordinating find/modify/save are placed where they can be reused from HTTP controllers, scheduled jobs, or message handlers.

Notice **rename** is a read-then-write sequence, so concurrent updates to the same profile can suffer **lost updates**. Separating service and repository **does not automatically make business operations atomic**; if concurrent updates must be guarded, pick a versioning mechanism or Redis command/script aligned with your data contract. Similarly, checking "email not duplicated" with **findByEmail** followed by **save** has a race condition; **@Indexed** is not a unique constraint.

As services grow more complex, extract business rules into well-named methods or domain objects, rather than turning repositories into dumping grounds for business conditions.

## 8. The Controller Only Accepts Requests and Returns Results

The HTTP layer calls the service, maps **Optional.empty()** to **404**, and builds responses:

~~~java
package com.example.customer.web;

import com.example.customer.domain.CustomerProfile;
import com.example.customer.service.CustomerProfileService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profiles")
public class CustomerProfileController {
    private final CustomerProfileService service;

    public CustomerProfileController(CustomerProfileService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerProfile> create(
            @RequestBody CreateProfileRequest request) {
        CustomerProfile saved = service.create(
            request.email(),
            request.displayName()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }

    @GetMapping("/{id}")
    public ResponseEntity<CustomerProfile> get(@PathVariable String id) {
        return ResponseEntity.of(service.findById(id));
    }

    public record CreateProfileRequest(
        String email,
        String displayName
    ) {}
}
~~~

The controller never touches **RedisTemplate** or calls **repository.save()** directly. When you need extra validation or multi-store coordination, you update the service without turning the HTTP layer into the center of business logic.

This example focuses on layer structure. Real applications should define dedicated response DTOs, proper validation/error handling, and authentication/authorization policies.

## 9. When to Use `RedisTemplate` Instead of Redis Repository

Not all Redis data should be modeled as an entity with **CrudRepository**.

For example, "incrementing page views" is naturally a Redis **INCR** command; creating an entire entity class just to represent a counter adds unnecessary complexity.

Service using **StringRedisTemplate**:

~~~java
package com.example.customer.service;

import com.example.customer.config.RedisKeyNames;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class PageViewService {
    private final StringRedisTemplate redis;

    public PageViewService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long registerView(String pageId) {
        return redis.opsForValue().increment(
            RedisKeyNames.pageViews(pageId)
        );
    }
}
~~~

**INCR** increments atomically in a single Redis command. For counters, this expresses intent much better than **GET → parse long → add one → SET**, which can lose updates under concurrent requests.

Extracting key naming rules:

~~~java
package com.example.customer.config;

public final class RedisKeyNames {
    private RedisKeyNames() {
    }

    public static String pageViews(String pageId) {
        if (pageId == null || pageId.isBlank()) {
            throw new IllegalArgumentException("Page id is required");
        }
        return "page:views:" + pageId;
    }
}
~~~

Centralizing key prefixes prevents services from duplicating string literals like **"page:views:"**, especially when features must share consistent TTLs, namespaces, or ID formatting.

**Note:** key strings managed directly via templates and repository keyspaces do not necessarily share the same layout. Avoid letting two mechanisms write to the same key unless the Redis data type, serializer, and update ownership are explicitly designed.

### Abstraction Selection Table

| Need | Typically Suitable Tool | Reason |
|---|---|---|
| Single-object CRUD by ID | **RedisRepository/CrudRepository** with **@RedisHash** | Built-in entity mapping and persistence operations |
| Lookup by indexed fields | **Redis Repository** with **@Indexed** | Integrates Spring Data Redis secondary indexes |
| Counters, flags, string keys with TTL | **StringRedisTemplate** | Direct invocation of simple Redis commands |
| Lists/sets/zsets, custom-structured hashes | **RedisTemplate** | Full control over Redis commands and data shapes |
| Lua scripts, conditional atomic operations | **RedisTemplate.execute(...)** or dedicated adapter | Executes data-local business steps inside Redis |
| Caching method results by key | **Spring Cache abstraction** when suitable | Cache semantics separated from entity storage |
| Reactive/WebFlux applications | **ReactiveRedisTemplate** / **ReactiveStringRedisTemplate** | **Mono/Flux** publishers and non-blocking I/O path |

Spring Data Redis repositories follow an **imperative** model in standard usage. Do not inject a synchronous **CrudRepository** and call it directly on a WebFlux event loop expecting it to become non-blocking. If the entire application uses Reactor, pick reactive Redis APIs and isolate any remaining blocking sources explicitly.

## 10. Writing a Custom Repository Adapter to Hide `RedisTemplate`

Sometimes business logic needs multiple Redis commands, yet you do not want every service to know key formats. In that case, define a **port/interface** in business terms and implement it using `RedisTemplate`.

Counter example:

~~~java
package com.example.customer.repository;

public interface PageViewCounter {
    long increment(String pageId);
}
~~~

~~~java
package com.example.customer.repository;

import com.example.customer.config.RedisKeyNames;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class RedisPageViewCounter implements PageViewCounter {
    private final StringRedisTemplate redis;

    public RedisPageViewCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public long increment(String pageId) {
        Long result = redis.opsForValue()
            .increment(RedisKeyNames.pageViews(pageId));

        if (result == null) {
            throw new IllegalStateException("Redis returned no counter value");
        }
        return result;
    }
}
~~~

Then **PageViewService** can depend on **PageViewCounter** rather than **StringRedisTemplate** directly:

~~~java
@Service
public class PageViewService {
    private final PageViewCounter counter;

    public PageViewService(PageViewCounter counter) {
        this.counter = counter;
    }

    public long registerView(String pageId) {
        return counter.increment(pageId);
    }
}
~~~

In this final snippet, imports for **PageViewService** include **PageViewCounter** and **org.springframework.stereotype.Service**.

You do not need an interface for every Redis command in a very small application. Custom adapters shine when key/TTL/serialization logic is reused across places, implementations may swap, or you want clear control over how services access Redis. Meanwhile, **Spring Data Redis Repository** is already a framework-implemented abstraction, so avoid wrapping it just to forward **save/findById** calls.

## 11. Keeping Serializers in the Configuration Layer

Redis stores byte sequences. If two services access the same key using different serializers, the reader may fail to decode the data or hit Redis type errors.

When dealing strictly with strings, **StringRedisTemplate** is usually enough. When storing objects with a custom template, define a dedicated bean:

~~~java
package com.example.customer.config;

import com.example.customer.domain.CustomerProfile;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisClientConfig {
    @Bean("profileJsonRedisTemplate")
    public RedisTemplate<String, CustomerProfile> profileJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, CustomerProfile> template =
            new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
            new Jackson2JsonRedisSerializer<>(CustomerProfile.class)
        );
        template.afterPropertiesSet();
        return template;
    }
}
~~~

This is **one way to store `CustomerProfile` as a JSON value via `RedisTemplate`** for keys owned by this template. It **differs from** the **@RedisHash** approach mapping the same class to a Redis hash via Redis Repository earlier. If you choose this JSON approach for a feature, assign a separate keyspace and single ownership mechanism instead of letting a repository and a template update the same key.

At injection points, when multiple templates exist or generic type erasure makes selection ambiguous, naming the bean and using **@Qualifier("profileJsonRedisTemplate")** pinpoints the exact instance and serializer.

### Serializer Checklist Before Going to Production

1. Are keys **String**, binary, or another encoding?
2. Are values strings, hashes, or JSON?
3. If DTO fields change, can newer versions read data written by older versions?
4. Do other clients or languages access the same keys?
5. Are TTLs, data types, and serialization consistent across every write path?

These questions belong to storage infrastructure design; business services should not create an **ObjectMapper** and serialize bytes manually on every request.

## 12. Transaction Boundaries and Atomicity

Organizing code into controller → service → repository provides **separation of concerns**, not automatic Redis transactions.

Example:

~~~java
public void transferPoints(String fromId, String toId, long amount) {
    // Read sender points.
    // Deduct sender points and save.
    // Add receiver points and save.
}
~~~

If the two saves are separate Redis command sequences, a failure midway can leave inconsistent state. Putting all that code inside one service method does not make Redis roll back previously succeeded commands.

Specifically:

- **INCR/DECRBY** are atomic commands for individual counter updates.
- **MULTI/EXEC** executes queued commands sequentially without interleaving from other clients; Redis does not roll back the entire batch after a runtime error in one command.
- **WATCH + MULTI/EXEC** detects key modifications between read and write, but requires bounded retries and executing within the same connection/session.
- **Lua scripts / Redis Functions** combine checks and updates in one server-side execution, yet scripts also do not auto-roll back commands already executed before an error.
- Spring's **@Transactional** does not turn Redis and SQL operations into an atomic distributed transaction. Redis transaction support also depends on template configuration, transaction manager setup, and usage pattern.

When designing services, clarify **which preconditions must hold**, **which keys change**, and **whether partial failures need retries or compensation**. Push atomic primitives down into the data adapter when needed; the service remains responsible for business decisions.

In Redis Cluster, multi-key commands and scripts are generally constrained by **hash slots**. Clean package structure does not fix keys landing on different nodes.

## 13. Organizing TTLs, Keyspaces, and Data Lifecycle

TTL is not a minor detail to tack on after deployment. It governs how long data survives and drives core business behavior.

### Entities with `@RedisHash`

An entity can specify a default lifetime:

~~~java
@RedisHash(value = "login_session", timeToLive = 1800)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    public LoginSession() {
    }

    public LoginSession(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }
}
~~~

In this example, **timeToLive = 1800** is in seconds. Some models use **@TimeToLive** on a property to control TTL per entity instance. If logic requires refreshing the expiration at specific moments, the service defines the refresh rule and the adapter executes the appropriate command.

When using Spring Data Redis secondary indexes and expiration events, index cleanup and expiration notifications depend on Redis and Spring Data Redis configuration; do not treat Redis Pub/Sub events as durable message queues. Expired data may also be purged lazily or actively by Redis, so do not build business logic assuming expiration events arrive on the exact second.

### Keys Managed by `RedisTemplate`

~~~java
redis.opsForValue().set(
    "verification:code:" + requestId,
    code,
    java.time.Duration.ofMinutes(5)
);
~~~

Using **set(key, value, timeout)** to write and set TTL in a single command is preferable to calling **SET** then **EXPIRE** when you want to avoid keys persisting indefinitely if the app crashes between steps.

Keyspace and TTL choices should follow data semantics:

| Data | Example Keyspace | Decisions Required |
|---|---|---|
| Repository-backed profile | **customer_profile** | Is it the source of truth or a temporary copy? |
| Login session | **login_session** | TTL, session renewal, revocation |
| View counter | **page:views:{id}** | Reset periodically or retain long-term? |
| Idempotency marker | **request:dedupe:{id}** | When may a request be retried/reprocessed? |
| Cached computation | **cache:{feature}:{key}** | TTL, cache invalidation, backing data source |

Do not reuse one feature's key prefix for another feature merely because both store the same value type; doing so makes bulk deletion, schema changes, and TTL adjustments difficult to manage.

## 14. Distinguishing Spring Data Repository from Spring Cache

**Repository** defines how entities are stored and retrieved from a data store. When Redis acts as an entity's store, the repository is its data-access interface.

**Spring Cache** defines caching behavior for computed results or method outputs. Redis can act as a cache backend, yet **@Cacheable** is not synonymous with **@RedisHash** or repositories.

~~~java
@Cacheable(cacheNames = "productLookup", key = "#productId")
public ProductDto getProduct(String productId) {
    return productDatabase.load(productId);
}
~~~

This snippet illustrates cache usage; **ProductDto** and **productDatabase** belong to a separate feature. To back it with Redis, enable and configure Spring Cache and a Redis cache manager accordingly.

Once using the cache abstraction, do not manually modify the framework-managed cache keys via a Redis repository. Conversely, repositories do not automatically handle cache invalidation for external databases. Keeping the two concepts separate yields clear lifecycles: caches can be evicted and reloaded, while entities represent domain data with explicit persistence and synchronization rules.

## 15. Testing Across Each Boundary

This architecture makes testing straightforward:

**Service unit tests:** mock **CustomerProfileRepository** and verify business rules such as rejecting blank inputs and invoking the right repository calls. No running Redis is needed to test pure Java logic.

**Repository integration tests:** use a test Redis instance to verify **save/findById**, **findByEmail** with secondary indexes, serializers, TTLs, and real keyspaces. Mocks cannot prove Spring Data mapping or drivers work properly.

**Controller tests:** verify request/response mapping, HTTP status codes, and delegation to the service. Do not duplicate Redis logic inside controller tests.

**End-to-end tests:** verify a full path from HTTP to Redis and inspect system-level behaviors such as key deletion, disconnects, retries, or critical concurrency scenarios.

These tests are part of application development responsibility. Defining a repository interface alone does not prove data mapping, secondary indexes, or serializers align with your live Redis setup.

## 16. Common Code Organization Mistakes

### 16.1. Controllers Calling Redis Directly

~~~java
@GetMapping("/views/{id}")
public Long views(@PathVariable String id) {
    return redis.opsForValue().increment("page:views:" + id);
}
~~~

When anti-spam rules, TTLs, or key prefix changes are introduced later, the controller ends up owning data and business logic. Place those decisions in services and adapters.

### 16.2. Every Service Creating Its Own Redis Connection

~~~java
// Do not create a new factory per request/service call:
LettuceConnectionFactory factory = new LettuceConnectionFactory();
factory.afterPropertiesSet();
~~~

This bypasses Spring Boot's configuration, resource management, and bean lifecycle. Inject a Spring-managed template or repository instead.

### 16.3. Repositories Containing HTTP Logic

Repositories must never return **ResponseEntity**, accept **HttpServletRequest**, or decide HTTP 404 responses. Those are web-adapter details.

### 16.4. Services Assembling Keys and Picking Serializers in Every Method

When prefixes or JSON formats change, edits scattered across many files easily miss spots. Centralize key naming and serialization in configuration or data adapters.

### 16.5. Mixing Repository Mapping and Templates on the Same Key

**@RedisHash** stores entries as Spring Data hashes/mappings. Another template calling **SET** to write a string or JSON to the same key breaks Redis data-type and metadata assumptions. Pick one owner per keyspace, define its schema, and never overwrite framework-managed keys.

### 16.6. Assuming Every Repository Supports JPA-Style Queries

**findByEmail** works only within the query/index mechanisms supported by Spring Data Redis. Do not infer joins, multi-table transactions, or unique constraints just because an interface extends **CrudRepository**.

### 16.7. Treating `@Transactional` as a Guarantee Across All Stores

A method writing to Redis and then SQL can still succeed partially without cross-system consistency design. Services must define the source of truth, idempotency guarantees, and concrete recovery paths.

## 17. Workflow for Adding a New Redis Feature

Suppose a new feature needs to store a **verification code** for five minutes.

1. **Describe data and rules:** key derived from request ID, value is the code, five-minute TTL; define behavior on missing keys or overwrites.
2. **Choose the abstraction:** since this is a small key/value with TTL, use **StringRedisTemplate** or a custom adapter rather than an entity repository if mapping adds no value.
3. **Name keys consistently:** define the **verification:code:** prefix in a key-naming class or adapter.
4. **Write a data adapter when needed:** implement **save(code, ttl)**, **get**, and **consume** matching desired semantics. If "read and delete once" must be atomic, pick an atomic Redis command/mechanism instead of two separate calls.
5. **Write the service:** validate requests, generate codes, verify matches, and enforce attempt limits.
6. **Expose the API:** the controller translates requests/responses without knowing serializers, key prefixes, or Redis commands.
7. **Verify at the right layer:** test real mapping/keys/TTLs and connection failure paths.

The same workflow applies to sessions, rate limiting, counters, and other transient data. For entities needing CRUD and indexed lookups, start with a **@RedisHash** model and **CrudRepository**, then add a service for business rules.

## 18. Practice Questions

**Question 1.** An **OrderController** handles a request and uses **RedisTemplate** to call **HSET** and **EXPIRE**. If the TTL policy changes, where should the edit belong?

**Hint:** Inside the service/adapter owning data persistence, or its configuration, rather than scattering Redis details in the controller. If writing and setting TTL must be atomic, choose an approach suited to the hash data type and Redis behavior.

**Question 2.** Two services read an **@RedisHash** entity via a repository while also calling **StringRedisTemplate.opsForValue().set(...)** to update the underlying key. Is this safe?

**Hint:** It cannot be assumed safe. Repository mapping uses Redis hashes and may maintain metadata/indexes; a template `SET` can change the Redis type or break mapping consistency. Choose a single keyspace owner.

**Question 3.** A **RedisRepository** defines **findByEmail** with an **@Indexed** property. Does that guarantee emails are unique?

**Hint:** No. Secondary indexes support lookups, not unique constraints. Enforce uniqueness with atomic write conditions if concurrent requests require it.

**Question 4.** Why avoid instantiating a **LettuceConnectionFactory** inside each service's constructor?

**Hint:** Services become coupled to Redis connections, configuration, resources, and lifecycle. Spring Boot manages factories and templates centrally; dependency injection is far more consistent.

**Question 5.** A WebFlux application calls a **CrudRepository** directly inside its pipeline. Does the entire pipeline become non-blocking?

**Hint:** No. Imperative repositories can block pipeline threads. For reactive I/O, use reactive Redis APIs or explicitly isolate blocking boundaries.

## 19. Summary

In Spring Data Redis, clean design begins by **placing responsibilities in the right layer**:

- **Configuration** manages connections, templates, serializers, and infrastructure properties.
- **Repository** expresses data access, using **@RedisHash + CrudRepository** for entities or **RedisTemplate** adapters when specific commands are needed.
- **Service** holds business rules and coordinates operations.
- **Controller** accepts and returns protocol-level payloads without containing Redis operations.
- **Domain/Model** describes data and entity lifecycles.

More important than package names is consistency: **a clear keyspace owner, a defined storage format, a single layer for business decisions, and a Spring-managed connection boundary**. Proper layering improves changeability, testability, and operations, while still requiring dedicated design for Redis atomicity, TTLs, and error handling.
