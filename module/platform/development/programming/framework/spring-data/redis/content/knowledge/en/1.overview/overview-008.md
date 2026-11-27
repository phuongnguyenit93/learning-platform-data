# Learning Roadmap and Prerequisites for Spring Data Redis

Spring Data Redis is a module in the Spring Data ecosystem that helps Java/Spring applications communicate with Redis in familiar ways: operating directly through `RedisTemplate`, caching via Spring Cache, mapping certain objects with Redis Repositories, and handling other capabilities such as Pub/Sub or Redis Streams. To learn effectively, you need to understand **how Redis works** before deciding **what problem Spring should use Redis to solve**.

This guide lays out a learning sequence, prerequisites, a practice environment, stage-by-stage exercises, and self-assessment criteria. Beginners can start with a local Redis instance and progress to a Spring Boot application with caching, testing, and basic operations.

## 1. Learning Outcomes of the Roadmap

Upon completion, learners should be able to:

1. Explain what Redis is, why it offers low-latency access, and the limitations of keeping data primarily in memory.
2. Distinguish using Redis as a **cache**, **structured key–value store**, **counter**, **temporary state store**, or **event-exchange system**.
3. Choose suitable data structures: String, Hash, List, Set, Sorted Set, Stream; design key names and time-to-live (TTL).
4. Configure Spring Boot connectivity to Redis; use `StringRedisTemplate` or `RedisTemplate` to read and write data.
5. Use `@Cacheable`, `@CachePut`, and `@CacheEvict` when a problem fits Spring Cache; recognize when direct Redis operations are needed.
6. Understand serialization options, risks of changing object schemas, cache misses, stale data, and cache invalidation strategies.
7. Write integration tests against a real Redis instance, inspect keys/TTLs, and verify application behavior on cache hits and misses.
8. Identify deployment issues: security, memory limits, oversized keys, thundering herds when caches expire together, Redis outages, and monitoring.

**Limitation to remember:** Redis does not automatically replace a relational database. For business data requiring transactions, constraints, and complex queries, many systems still use PostgreSQL/MySQL as the primary data source, while Redis holds fast-access data or short-lived state.

## 2. Prerequisites to Prepare

### 2.1. Mandatory Foundational Knowledge

| Area | What to Know Before Starting | Quick Self-Check |
| --- | --- | --- |
| Java | Classes, objects, interfaces, collections, generics, exceptions, and `null`; understanding method calls | Write a Java service that takes parameters and returns an object |
| Spring / Spring Boot | Beans, Dependency Injection, `@Service`, `@Configuration`; configuration via `application.yml` or `application.properties` | Explain how Spring injects a dependency into a constructor |
| REST and JSON | Request/response, HTTP status codes, basic JSON | Build a `GET /products/{id}` API and inspect the output |
| Build and dependencies | Running apps with Maven or Gradle; understanding what a starter does | Add a starter and start the application |
| Data | Key/value concepts, reads/writes, latency, data requiring durable persistence | Give examples of data that is allowed to expire |
| Tools | Terminal, environment variables, logs; Docker is a convenient option | Run commands and read connection error logs |

Examples in this guide target **Spring Boot 3.x, Java 17 or higher**, and Spring Boot-managed dependency versions. If you use a different Spring Boot / Spring Data Redis version, verify the matching configuration property names, APIs, and Java requirements; avoid mixing incompatible versions arbitrarily.

You do not need to memorize all of Spring Framework, Redis Cluster, or asynchronous programming before starting. Beginners only need to be able to build a simple Spring Boot app and understand the request → service → data → response lifecycle.

### 2.2. Helpful Knowledge to Learn Faster

- **SQL databases:** understand primary keys, indexes, transactions, and why a query can be slow. This helps identify where caching belongs.
- **Networking basics:** know `localhost`, host, port, TCP, and timeouts; distinguish services running directly on the host machine vs. inside containers.
- **Concurrency:** know that multiple requests can access the same data concurrently; have a basic grasp of race conditions and atomic operations.
- **Testing:** basic experience with JUnit and Spring Boot Test; familiar with unit tests vs. integration tests.
- **Operations:** familiarity with Docker Compose, logs, health checks, and environment variables is an advantage.

### 2.3. Readiness Self-Assessment

Before moving into Spring Data Redis, try answering:

1. What do `@Service` and constructor injection solve?
2. Why does JSON returned over HTTP not necessarily look identical to the bytes stored inside Redis?
3. If an API reads product details 1,000 times while the product changes only once, where can caching help?
4. If the cache loses all its data, where does the application recover the canonical data from?
5. Why does a value living for 5 minutes need different handling from a value that must be retained for years?

If you cannot answer questions 1–2 yet, review Spring/JSON. For questions 3–5, initial intuition is enough; the roadmap below will fill in the details.

## 3. Concept Map: Redis, Clients, and Spring Data Redis

A common architectural view:

~~~text
HTTP Client
    |
    v
Spring Controller -> Spring Service
                          |
             +------------+-------------+
             |                          |
             v                          v
       Spring Data Redis          JPA/JDBC/DAO
             |                          |
          Lettuce/Jedis                  |
             |                          |
             v                          v
        Redis Server             Primary Database
~~~

Spring Data Redis lives on the application side: it is not Redis Server. Lettuce is a widely used client and Spring Boot's default choice in many configurations; Jedis is also an option. Redis Server processes commands and manages data; Spring provides APIs, configuration, data conversion, and integration with bean management.

| Usage Pattern | Key APIs / Concepts | When to Learn and Use |
| --- | --- | --- |
| Command- and data-structure-level operations | `StringRedisTemplate`, `RedisTemplate`, `opsForValue()`, `opsForHash()`, `opsForSet()`… | Counters, session state, specialized keys, custom TTLs |
| Caching method results | Spring Cache: `@EnableCaching`, `@Cacheable`, `@CacheEvict`, `CacheManager` | Accelerating reusable queries that can tolerate controlled stale data |
| Key-based object/document storage | Spring Data Redis Repository, `@RedisHash`, `@Id` | Relatively simple data models needing a repository API; must understand query limits |
| Sending/receiving messages | Pub/Sub, Redis Streams | Once comfortable with CRUD/caching and message reliability needs |
| Distributed task coordination | Atomic commands, suitable lease/lock mechanisms | Advanced topic: requires accounting for lifetimes, failures, and correctness |

**Two paths that are especially easy to confuse:**

- **Spring Cache** defines *when* to store or evict method results; Redis is only one possible backend. Convenient annotations do not automatically solve stale data.
- **RedisTemplate** lets you pick specific *Redis commands and data types*. It is more flexible, but the application must manage keys, TTLs, serialization, and deletion timing itself.

## 4. Getting Familiar with Redis Before Integrating Spring

### 4.1. Minimal Practice Environment

Prepare a JDK, IDE, Maven/Gradle, Docker (or another local Redis), and the `redis-cli` tool. You can run a practice Redis instance locally with Docker:

~~~bash
docker run --name redis-learning -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-learning redis-cli PING
~~~

A successful `PING` returns `PONG`. The port in this example binds only to your practice machine's loopback interface. That setup is for learning; real deployments require connection protection, access permissions, network configuration, and secret management.

If Redis runs alongside your app in Docker Compose, the hostname inside the app container is usually the **Redis service name**, not `localhost`. If the application runs directly on your host machine with the Docker command above, it can connect to `localhost:6379`.

### 4.2. Commands Worth Practicing by Hand

Open the CLI:

~~~bash
docker exec -it redis-learning redis-cli
~~~

Then run in sequence:

~~~redis
SET demo:greeting "hello" EX 60
GET demo:greeting
TTL demo:greeting
TYPE demo:greeting

HSET demo:user:42 name "Lan" level "beginner"
HGETALL demo:user:42

SADD demo:tags redis spring java
SMEMBERS demo:tags

ZADD demo:leaderboard 100 alice 120 bob
ZREVRANGE demo:leaderboard 0 -1 WITHSCORES

INCR demo:page:views
DEL demo:page:views
SCAN 0 MATCH demo:* COUNT 100
~~~

Things to observe: `SET` with `EX 60` creates an expiring key; `TTL` returns remaining time (when the key exists); `INCR` performs an integer increment via a Redis command; Hash stores multiple fields under one key; Set avoids duplicates; Sorted Set maintains scores for ranking.

**Do not use `KEYS *` to explore keys on large systems or in production** because it can hurt responsiveness. `SCAN` iterates incrementally with a cursor; the example above only returns one batch—you must loop using the returned cursor until it returns 0 to finish a full scan. Avoid running `FLUSHDB`/`FLUSHALL` anywhere holding real data.

### 4.3. Six Redis Concepts to Master

| Concept | Question to Answer | Example |
| --- | --- | --- |
| Keys and namespaces | Is the key unique, easy to locate, and collision-free? | `shop:product:42` |
| Data types | Do you need a single value, multiple fields, a set, or a ranking? | String for OTP codes, Hash for small attributes, ZSet for leaderboards |
| TTL and expiration | When does data expire and who is responsible for restoring it? | OTP 5 minutes, catalog cache 10 minutes |
| Persistence | Does Redis data need to survive a restart? | RDB/AOF are options to study; durability depends on config and failure scenarios |
| Eviction | When memory fills up, which keys may Redis remove? | `maxmemory-policy` depends on the system's purpose |
| Atomicity | Does a command keep state consistent under concurrent clients? | `INCR` is better than reading a number and adding in Java |

Do not infer that Redis "never loses data" just because persistence is enabled; durability also depends on write policies, backups, failover, and application error handling.

## 5. Stage-by-Stage Learning Roadmap

The durations below are **relative suggestions** for learners who already know basic Java and Spring Boot; adjust them to your own pace. Each stage should end with something runnable or a technical question you can answer clearly.

| Stage | Core Focus | Exercise / Output | Suggested Duration |
| --- | --- | --- | --- |
| 0. Foundation review | Java, DI, Spring Boot config, REST, Maven/Gradle | Simple GET API without Redis | 2–4 hours if needed |
| 1. Redis fundamentals | String/Hash/Set/ZSet/List, keys, TTL, `redis-cli` | Try commands yourself and describe suitable types | 3–5 hours |
| 2. Connecting Spring Data Redis | Starter, connection config, `StringRedisTemplate`, error handling | Service incrementing views via `INCR` | 3–5 hours |
| 3. Data design | Key prefixes, serialization, TTL, read/write, key inspection | Store a small object and read it back with the right type | 4–6 hours |
| 4. Caching with Spring | `@Cacheable`, `@CacheEvict`, cache hit/miss, stale data | Product read API reducing DB query counts | 4–6 hours |
| 5. Repositories and extensions | `@RedisHash`, entity TTL, indexes; Pub/Sub/Streams overview | Compare Repository vs. Template; try one use case | 3–6 hours |
| 6. Testing and performance | Integration tests, real Redis, hit ratio, TTL, connection failures | Tests for cache miss/hit/invalidation; before/after metrics | 4–6 hours |
| 7. Deployment readiness | Security, memory, persistence, monitoring, topology, recovery | Ops checklist and Redis-outage simulation exercise | 4–6 hours |

### Stage 0 — Master the Request Lifecycle in Spring Boot

Build an API that returns a product by ID, initially backed by a mock repository or a familiar database:

~~~text
GET /products/42
  -> ProductController
  -> ProductService
  -> ProductRepository
  -> ProductDto (JSON)
~~~

Understand where data-reading logic executes and why the service is managed by Spring. This will become the insertion point for caching later. Without understanding this flow first, adding Redis too early can mask architectural flaws.

### Stage 1 — Choose the Right Data Type and TTL

Try designing three use cases yourself:

1. **Article view counter:** String key with `INCR`, possibly with no TTL if metrics are long-lived; if metrics must be durable, decide how to sync/back up.
2. **Short-lived verification code:** String with TTL; account for single-use rules and concurrent access risks.
3. **Score leaderboard:** Sorted Set with scores; add, update, and retrieve top N.

Then explain why you shouldn't just use a single JSON String for every problem. Redis has specialized operations that avoid fetching an entire object into Java just to modify one field or number.

### Stage 2 — Connect Spring Boot to Redis

Maven example with Spring Boot-managed dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
</dependencies>
~~~

This is the `dependencies` snippet of a Spring Boot project, not a complete `pom.xml`. Gradle equivalents work as well. For Spring Boot 3.x talking to the local server from section 4:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Separate parameters by environment; never commit real server passwords to the repository. In deployed networks, consider TLS, ACLs, secret managers, and appropriate timeouts.

Create a String-based service to record views:

~~~java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ArticleViewService {
    private final StringRedisTemplate redis;

    public ArticleViewService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long recordView(String articleId) {
        String key = "demo:article:views:" + articleId;
        Long count = redis.opsForValue().increment(key);
        if (count == null) {
            throw new IllegalStateException("Redis did not return a count");
        }
        return count;
    }
}
~~~

When calling `recordView("42")` repeatedly, Redis increments using its dedicated command; there is no need to read the value into Java and write it back. The example assumes `articleId` is already validated by callers and Redis is connected. If this is a critical business counter, you still need persistence/recovery requirements for Redis outages.

Key takeaways:

- `StringRedisTemplate` suits string keys/values; Redis handles numeric increments on valid numeric strings.
- `RedisTemplate<K,V>` provides multiple operation groups and customizable serializers.
- Timeouts, network errors, authentication, and Redis unavailability must be handled according to feature criticality.
- Configure connection pools, SSL/TLS, or advanced connection tuning only when actually needed; do not tweak numerous settings blindly before measuring.

### Stage 3 — Design Keys, Values, and Lifetimes

Establish a key convention before data grows large:

~~~text
<application>:<entity>:<id>[:<attribute>]
shop:product:42
shop:product:42:views
shop:session:opaque-session-id
~~~

A good key avoids collisions across environments and features, stays reasonably short, excludes passwords or easily exposed sensitive info, and makes ownership of the data lifecycle clear. Prefixes can include the environment name when environments share infrastructure, though isolating resources completely is easier to administer.

When storing objects, choose a serializer deliberately:

| Option | Pros | Considerations |
| --- | --- | --- |
| Plain strings and simple values | Easy to read in CLI, easy to share across languages | Must organize structure manually |
| JSON | Easy to inspect and exchange, less coupled to Java bytecode | Needs compatibility policies for schema changes and type handling |
| Binary/JDK serializer | Can be convenient within existing Java systems | Hard to read manually, compatibility and security risks; avoid on untrusted data |
| Redis Hash | Reads/writes individual fields | No built-in relational semantics; data types must follow conventions |

Avoid relying on default serializers when data must survive across multiple application versions. Decide which data may be deleted, how migrations work, and how footprint is controlled.

TTL addresses part of the data lifecycle, yet does not replace update rules. For example, a product cache with a 10-minute TTL can still serve old prices for 10 minutes if the cache is not deleted after an update. When many keys expire at once, consider TTL jitter and limiting concurrent reloads.

### Stage 4 — Use Spring Cache in the Right Scenarios

Before caching query results, ask: **can the result be recomputed from the primary source, how stale can it be, and which caches must be cleared on updates?**

Spring Cache is usually enabled with `@EnableCaching` in application configuration. To use Redis as the backend, include `spring-boot-starter-data-redis` and `spring-boot-starter-cache` on the classpath, then configure caching appropriately. Example Redis cache TTL setup in Spring Boot 3.x:

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
~~~

The snippet below illustrates placing annotations on **service methods**. `ProductRepository` and `ProductDto` represent the business components from Stage 0:

~~~java
@Service
public class ProductQueryService {
    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductDto getById(Long id) {
        return products.findDtoById(id)
                .orElseThrow(() -> new ProductNotFoundException(id));
    }

    @CacheEvict(cacheNames = "productById", key = "#id")
    public void changePrice(Long id, BigDecimal newPrice) {
        products.updatePrice(id, newPrice);
    }
}
~~~

This is an **integration illustration**, not a standalone compilable class without defining the repository, DTO, exception, and imports. In a real system, updates must obey transactions and consistency rules of the primary source. If multiple caches relate to one product, identify every location needing invalidation.

Observe the basic flow:

~~~text
First call:   Service -> Cache miss -> Repository -> Cache put -> Response
Later call:   Service -> Cache hit ------------------------------> Response
Update:       Service -> Write primary source -> Evict cache
Next call:    Service -> Cache miss -> Repository -> ...
~~~

Common pitfalls:

- Cached methods must be invoked through the Spring proxy. Calling one method from another within the **same bean** generally does not trigger cache annotations under default proxy mode.
- Cache keys must distinguish all inputs that affect the output; if results depend on user, role, or tenant, never share a key lacking that context.
- A cache hit does not mean data is always fresh; eviction and TTL are business decisions.
- Do not cache results containing sensitive data without verifying access controls and cache sharing boundaries.
- Measure repository call counts or cache hit/miss metrics; do not assume caching made things faster just because annotations were added.

### Stage 5 — Understand Redis Repositories and Advanced Extensions

Spring Data Redis provides a mapping model for objects suited to key-based storage. You will encounter `@RedisHash`, `@Id`, `@Indexed`, and `@TimeToLive`. Practice with a simple entity, read it back by ID, and inspect the keys generated by the framework. Then try changing TTLs and exploring query limits.

Redis Repositories do not offer full JPA semantics: there are no built-in joins, foreign keys, SQL queries, or relational transactions. Querying by fields may require secondary indexes and auxiliary data structures; understand index maintenance costs and expiration behavior before choosing it as a primary store.

Only after mastering reads/writes and caching should you expand to:

- **Pub/Sub:** fits instant notifications for online subscribers; offline subscribers have no way to replay missed messages using Pub/Sub alone.
- **Redis Streams:** provides event logs and consumer groups, better suited when tracking progress and resuming reads are needed; applications still must handle acks, retries, idempotency, and data growth.
- **Pipeline/batch:** reduces network round trips for multiple commands, though it does not make all commands an atomic transaction.
- **Lua/transactions and distributed locks:** advanced topics requiring understanding of race conditions, timeouts, failover, and correctness safeguards.
- **Reactive Redis:** only prioritize if the application uses Spring WebFlux and you already know reactive streams; not a prerequisite for learning the synchronous stack.

### Stage 6 — Write Tests and Measure Results

An exercise is not finished at "it works on my machine." You need to inspect actual values in Redis and verify API behavior under changing conditions.

Practical test scenarios:

1. **Write/read:** write data via the service and read it back; confirm format and key.
2. **TTL:** create a short-lived key, check TTL before and after; verify the key disappears after expiration without relying on overly tight timing that makes tests flaky.
3. **Cache miss/hit:** call the API twice with the same key and verify repository calls decrease.
4. **Invalidation:** update origin data, call the API again, and verify the new result.
5. **Key isolation:** two different IDs, tenants, or permission levels never accidentally share cached results.
6. **Redis disconnection:** document or test the failure policy—return an error, bypass cache to read the origin, or reject requests depending on data type.
7. **Serialization:** verify whether data created by an older app version can still be read when DTOs or serializer rules change.

Testcontainers can spin up a Redis container for integration tests, letting you verify commands/TTLs/serializers against real Redis. Unit tests with mocks remain useful for business logic, yet cannot replace integration tests for behavior dependent on Redis Server.

Benchmark performance using a repeatable setup: same dataset, same load level, recording latency (especially p95/p99 under load), requests/sec, cache hit rate, DB query volume, and Redis memory usage. Compare before and after for both hits and misses, because a cache miss adds an extra Redis lookup before hitting the origin.

### Stage 7 — Minimum Knowledge for Safe Deployment

| Topic | Decisions / Observations Needed |
| --- | --- |
| Security | Redis reachable only from required networks; use ACLs/auth, TLS when appropriate; never expose port to public Internet |
| Memory | Memory limits, eviction policy, per-key size, keys growing forever without TTL |
| Persistence and backups | Which data can be lost, how RDB/AOF must be configured, whether backups/restores and restore drills are needed |
| Availability and failover | How standalone, Sentinel, and Cluster differ; how the app reacts during node switches |
| Monitoring | Connections, latency, timeouts, memory, evicted keys, expired keys, keyspace, hit/miss, DB load |
| Schema/keys | Prefix conventions, serialization, data versioning, migrations, and cleaning old keys |
| Resource limits | Avoid giant keys, heavy scan queries, hot keys, and chatty sequential network calls |
| Consistency | What is the primary data source, when to invalidate, stale-data handling, and recovery after cache loss |

Topologies like Redis Cluster and Sentinel should not be learned simply by changing a host address. They affect connections, key routing, failover, and certain multi-key commands. For example, with Redis Cluster, multi-key commands can be restricted by hash slots. When moving toward production, consult the documentation matching your exact Redis, Spring Boot, and client versions.

## 6. Sample Four-Week Study Schedule

At roughly 6–8 hours per week, you can allocate time as follows:

| Week | Focus | Proof of Learning |
| --- | --- | --- |
| 1 | Spring Boot review, Redis CLI, data types, and TTL | Create sample keys and explain each command |
| 2 | Spring Data Redis, Templates, key naming, serialization | API incrementing counters and saving/reading data in Redis |
| 3 | Spring Cache, data updates, Repositories, integration tests | Cached product API; tests covering miss/hit/eviction |
| 4 | Benchmarking, Redis failures, security, observability, capstone | Demo with metrics and documented fallback policy |

If you are already solid with Java/Spring Boot, skip the review; if new to Dependency Injection or HTTP, spend extra time on Stage 0. Topics like Redis Streams, distributed locks, and reactive APIs can wait until your first project runs smoothly.

## 7. Capstone Project: Cached Product Catalog API

**Problem:** a store has an endpoint to view product details. The database holds names, prices, and stock quantities. Products are read frequently but updated less often. The system needs faster reads without letting stale cache entries linger indefinitely when prices change.

### 7.1. Minimal Design

~~~text
GET /products/{id}
    -> Redis Cache (productById)
         | hit  -> return ProductDto
         | miss -> read DB -> save to cache with TTL -> return ProductDto

PATCH /products/{id}/price
    -> update DB successfully
    -> evict related cache entry
    -> next GET reloads from DB
~~~

Data rule: **the database is the primary source for products**; Redis holds only a regenerable copy. TTL bounds the lifetime of cached entries, while evicting on price changes addresses updates needed sooner than TTL. The sequence of DB update and cache eviction must be designed to handle transactions and concurrent requests.

### 7.2. Tasks to Complete

1. Create `ProductController`, `ProductService`, and a repository reading/writing from the primary source (database or mock store initially).
2. Add `spring-boot-starter-data-redis` and `spring-boot-starter-cache`; connect to local Redis.
3. Apply `@Cacheable` to the read operation and `@CacheEvict` to the price-update operation.
4. Define a TTL and document why you chose it; inspect keys, memory footprint, and serializers.
5. Write tests for three cases: miss, hit, and update followed by re-read.
6. Record response times or repository call counts before/after caching; test both cold and warm caches.
7. Simulate stopping Redis; decide whether the system should return an error or fall back to reading the DB in this situation.
8. If time permits, add a view counter with `StringRedisTemplate` to compare direct Redis command access against Spring Cache.

### 7.3. Completion Criteria for the Project

- Able to verbally explain which data lives in the DB, which lives in Redis, and what happens when Redis is empty.
- Demonstrate at least one cache hit without calling the repository again.
- After updating a product price, subsequent reads return the accurate result per the chosen rule.
- Keys have sensible names and TTLs; no sensitive data appears in keys or committed config files.
- Integration tests verify Redis behavior, and logs or metrics are sufficient to investigate stale data if it appears.
- Short documentation describes how to start, stop, clean the test environment, and recover from connection errors.

If you can complete these items, you understand enough core Spring Data Redis to start building a real feature under proper technical oversight.

## 8. Common Misconceptions and Pitfalls

| Misconception / Habit | Consequence | Better Approach |
| --- | --- | --- |
| "Adding Redis makes every API faster" | Adds a network hop and maintenance cost, especially on frequent cache misses | Target hotspots using metrics and read/write ratios |
| "Setting a TTL guarantees data is always right" | Can serve stale prices/state before expiration | Define invalidation rules and acceptable staleness |
| Sharing one key across multiple users/tenants | Data leaks or cross-contamination | Include full access context in key design |
| Storing all objects with the default serializer | Hard to debug, hard to upgrade/migrate | Pick an explicit format and verify compatibility |
| Using Redis as primary source without checking persistence | Data loss or failure to meet business requirements | Evaluate durability, backups, and transactions before choosing |
| Reading, adding in Java, then writing back | Lost updates under concurrent requests | Prefer `INCR` or appropriate atomic operations |
| Using Pub/Sub for queues requiring guaranteed replay | Offline subscribers miss messages | Consider Streams or a dedicated message broker |
| Writing a distributed lock with just `SETNX` | May miss timeouts, delete someone else's lock, or lack correctness guarantees | Study leases, owner tokens, failure modes, and proven libraries |
| Clearing the entire cache when updating one product | Causes mass misses and spikes DB load | Scope keys and cache regions to evict only the affected item |
| No memory limits and no eviction monitoring | Redis consumes excessive RAM or drops keys unexpectedly | Configure per data type and monitor metrics |

**Cache stampede:** many requests see a cache miss and query the DB simultaneously for a hot key. This is why you should study TTL jitter, request coalescing, cache warming, or anti-stampede techniques depending on scale. Avoid slapping distributed locks onto every cache miss without evaluating cost and correctness.

## 9. Order of Deeper Study After Mastering Fundamentals

Choose a track based on the product you are building:

- **Read-heavy web apps:** Spring Cache → cache keys/TTL/invalidation → cache metrics → stampedes and refresh strategies.
- **Counters, rankings, session state:** Redis String/Hash/Set/ZSet → atomic operations → TTL management → memory and persistence.
- **Event processing:** Pub/Sub vs. Streams → consumer groups → ack/retry → idempotency → backlog monitoring.
- **Distributed systems:** concurrent updates → correctness and limits of atomic commands → locks/leases → failover and recovery.
- **High performance or large scale:** load profiling → pipelining/batching → key optimization → Redis Cluster → tracking latency, memory, and hot keys.

Every track begins with a business question: do we need low latency, lower database load, state with TTL, or event exchange? The answer dictates which Spring Data Redis APIs to use; you do not have to learn every API before solving a real problem.

## 10. Self-Review Questions Before Moving to Advanced Lessons

1. How do Redis Server, Redis client, and Spring Data Redis differ in role?
2. How does cache-aside behave when a key already exists versus when it does not?
3. How does `@Cacheable` differ from `StringRedisTemplate.opsForValue().get()` in level of control?
4. When is using String, Hash, Set, or Sorted Set better than storing one large JSON blob?
5. Why does TTL not replace evicting the cache after updates?
6. What happens if a `@Cacheable` method is called from inside the same instance instead of through the Spring proxy?
7. Why should you avoid `KEYS *` when Redis is serving heavy traffic?
8. How can you verify that a second GET was a cache hit rather than merely observing the same HTTP response?
9. When Redis disconnects, which features can bypass cache and which should return an error?
10. For data stored solely in Redis, what questions must the application ask about persistence, backups, memory, and failover?

**Most important milestone:** being able to build a cached read flow yourself, prove a cache hit, handle invalidation after changes, and explain consistency limits. That is the foundation for advancing deeper into Spring Data Redis without relying on memorizing isolated annotations or commands.
